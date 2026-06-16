from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from xgboost import XGBClassifier


DEFAULT_FEATURE_SCHEMA = Path("configs/feature_schema.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train product-shaped XGBoost NDR binary model.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/common_ndr_features_smoke.csv"))
    parser.add_argument("--feature-schema", type=Path, default=DEFAULT_FEATURE_SCHEMA)
    parser.add_argument("--model-output", type=Path, default=Path("models/xgboost_model.joblib"))
    parser.add_argument("--preprocessor-output", type=Path, default=Path("models/xgboost_preprocessor.joblib"))
    parser.add_argument("--feature-list-output", type=Path, default=Path("models/xgboost_feature_list.json"))
    parser.add_argument("--metrics-output", type=Path, default=Path("reports/xgboost_metrics.json"))
    parser.add_argument(
        "--confusion-matrix-output",
        type=Path,
        default=Path("reports/xgboost_confusion_matrix.csv"),
    )
    parser.add_argument(
        "--feature-importance-output",
        type=Path,
        default=Path("reports/xgboost_feature_importance.csv"),
    )
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-estimators", type=int, default=80)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.input)
    if df.empty:
        raise SystemExit("input data is empty")
    features = load_feature_list(args.feature_schema, df)
    feature_schema_version = load_feature_schema_version(args.feature_schema)
    y = df["label"].map(label_to_int).astype(int)
    if y.nunique() < 2:
        raise SystemExit("XGBoost training requires both normal and attack labels")

    train_df, test_df, y_train, y_test = split_data(df, y, args.test_size, args.seed)
    preprocessor = SimpleImputer(strategy="median")
    x_train = preprocessor.fit_transform(to_matrix(train_df, features))
    x_test = preprocessor.transform(to_matrix(test_df, features))

    class_counts = Counter(y_train)
    scale_pos_weight = class_counts.get(0, 1) / max(class_counts.get(1, 1), 1)
    model = XGBClassifier(
        n_estimators=args.n_estimators,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        random_state=args.seed,
        scale_pos_weight=scale_pos_weight,
        n_jobs=2,
    )
    started = time.perf_counter()
    model.fit(x_train, y_train)
    train_time_s = time.perf_counter() - started

    probabilities = model.predict_proba(x_test)[:, 1]
    predictions = (probabilities >= args.threshold).astype(int)
    metrics = build_metrics(
        y_true=np.asarray(y_test),
        probabilities=probabilities,
        predictions=predictions,
        threshold=args.threshold,
        train_rows=len(train_df),
        test_rows=len(test_df),
        train_time_s=train_time_s,
        input_path=args.input,
        features=features,
        feature_schema_version=feature_schema_version,
        df_test=test_df,
    )

    ensure_parent(args.model_output)
    ensure_parent(args.preprocessor_output)
    ensure_parent(args.feature_list_output)
    ensure_parent(args.metrics_output)
    ensure_parent(args.confusion_matrix_output)
    ensure_parent(args.feature_importance_output)
    joblib.dump(model, args.model_output)
    joblib.dump(preprocessor, args.preprocessor_output)
    args.feature_list_output.write_text(json.dumps(features, indent=2), encoding="utf-8")
    args.metrics_output.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

    matrix = confusion_matrix(y_test, predictions, labels=[0, 1])
    pd.DataFrame(matrix, index=["actual_normal", "actual_attack"], columns=["pred_normal", "pred_attack"]).to_csv(
        args.confusion_matrix_output
    )
    importance = pd.DataFrame(
        {
            "feature": features,
            "importance": getattr(model, "feature_importances_", np.zeros(len(features))),
        }
    ).sort_values("importance", ascending=False)
    importance.to_csv(args.feature_importance_output, index=False)

    print(f"wrote {args.model_output}")
    print(f"wrote {args.preprocessor_output}")
    print(f"wrote {args.metrics_output}")


def load_feature_list(schema_path: Path, df: pd.DataFrame) -> list[str]:
    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        features = [feature for feature in schema.get("model_input_features", []) if feature in df.columns]
        if features:
            return features
    excluded = {
        "label",
        "attack_type",
        "dataset_name",
        "data_source",
        "is_synthetic",
        "timestamp",
        "window_start",
        "window_end",
        "session_id",
        "scenario_id",
        "run_id",
        "technique_id",
        "phase",
        "src_entity",
        "_source_file",
        "source_dataset",
    }
    return [column for column in df.columns if column not in excluded and pd.api.types.is_numeric_dtype(df[column])]


def load_feature_schema_version(schema_path: Path) -> str:
    if not schema_path.exists():
        return "ad_hoc_numeric_features"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return str(schema.get("feature_schema_version") or schema_path.stem)


def split_data(
    df: pd.DataFrame,
    y: pd.Series,
    test_size: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    group_col = next((column for column in ["session_id", "run_id", "scenario_id"] if column in df.columns), None)
    if group_col and df[group_col].nunique(dropna=True) >= 3:
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        train_idx, test_idx = next(splitter.split(df, y, groups=df[group_col]))
        train_df = df.iloc[train_idx].reset_index(drop=True)
        test_df = df.iloc[test_idx].reset_index(drop=True)
        return train_df, test_df, y.iloc[train_idx].reset_index(drop=True), y.iloc[test_idx].reset_index(drop=True)
    stratify = y if y.nunique() > 1 and min(Counter(y).values()) >= 2 else None
    train_df, test_df, y_train, y_test = train_test_split(
        df,
        y,
        test_size=test_size,
        random_state=seed,
        stratify=stratify,
    )
    return train_df.reset_index(drop=True), test_df.reset_index(drop=True), y_train.reset_index(drop=True), y_test.reset_index(drop=True)


def to_matrix(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    matrix = df.reindex(columns=features).apply(pd.to_numeric, errors="coerce")
    return matrix.replace([np.inf, -np.inf], np.nan)


def build_metrics(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    predictions: np.ndarray,
    threshold: float,
    train_rows: int,
    test_rows: int,
    train_time_s: float,
    input_path: Path,
    features: list[str],
    feature_schema_version: str,
    df_test: pd.DataFrame,
) -> dict[str, Any]:
    matrix = confusion_matrix(y_true, predictions, labels=[0, 1])
    tn, fp, fn, tp = [int(value) for value in matrix.ravel()]
    metrics: dict[str, Any] = {
        "model_name": "xgboost",
        "model_role": "operating_candidate",
        "feature_schema_version": feature_schema_version,
        "input": str(input_path),
        "threshold": threshold,
        "train_rows": train_rows,
        "test_rows": test_rows,
        "feature_count": len(features),
        "train_time_s": train_time_s,
        "accuracy": float(accuracy_score(y_true, predictions)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "confusion_matrix": matrix.tolist(),
        "confusion_matrix_labels": ["normal", "attack"],
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "true_positive": tp,
        "false_positive_rate": safe_divide(fp, fp + tn),
        "false_negative_rate": safe_divide(fn, fn + tp),
        "classification_report": classification_report(y_true, predictions, output_dict=True, zero_division=0),
        "dataset_breakdown": grouped_metrics(df_test, y_true, probabilities, predictions, "dataset_name"),
        "data_source_breakdown": grouped_metrics(df_test, y_true, probabilities, predictions, "data_source"),
        "source_dataset_breakdown": grouped_metrics(df_test, y_true, probabilities, predictions, "source_dataset"),
    }
    if len(np.unique(y_true)) > 1:
        metrics["roc_auc"] = float(roc_auc_score(y_true, probabilities))
        metrics["pr_auc"] = float(average_precision_score(y_true, probabilities))
    else:
        metrics["roc_auc"] = None
        metrics["pr_auc"] = None
    return metrics


def grouped_metrics(
    df: pd.DataFrame,
    y_true: np.ndarray,
    probabilities: np.ndarray,
    predictions: np.ndarray,
    group_col: str,
) -> dict[str, Any]:
    if group_col not in df.columns:
        return {}
    output: dict[str, Any] = {}
    groups = df[group_col].fillna("").astype(str).reset_index(drop=True)
    for group in sorted(groups.unique()):
        mask = groups == group
        if mask.sum() == 0:
            continue
        group_true = y_true[mask.to_numpy()]
        group_pred = predictions[mask.to_numpy()]
        group_prob = probabilities[mask.to_numpy()]
        matrix = confusion_matrix(group_true, group_pred, labels=[0, 1])
        tn, fp, fn, tp = [int(value) for value in matrix.ravel()]
        item = {
            "rows": int(mask.sum()),
            "accuracy": float(accuracy_score(group_true, group_pred)),
            "precision": float(precision_score(group_true, group_pred, zero_division=0)),
            "recall": float(recall_score(group_true, group_pred, zero_division=0)),
            "f1": float(f1_score(group_true, group_pred, zero_division=0)),
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
            "true_positive": tp,
            "false_positive_rate": safe_divide(fp, fp + tn),
            "false_negative_rate": safe_divide(fn, fn + tp),
        }
        if len(np.unique(group_true)) > 1:
            item["roc_auc"] = float(roc_auc_score(group_true, group_prob))
            item["pr_auc"] = float(average_precision_score(group_true, group_prob))
        output[group] = item
    return output


def label_to_int(value: Any) -> int:
    return 0 if str(value).strip().lower() in {"normal", "benign", "0", "false"} else 1


def safe_divide(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main()
