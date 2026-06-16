from __future__ import annotations

import argparse
import json
import sys
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
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tune XGBoost thresholds and run run/time-blocked validation.",
    )
    parser.add_argument("--input", type=Path, default=Path("data/processed/simulation_real_only_24h_common.csv"))
    parser.add_argument("--feature-list", type=Path, default=Path("models/xgboost_feature_list_simulation_real_only_24h.json"))
    parser.add_argument("--output-json", type=Path, default=Path("reports/xgboost_threshold_blocked_validation_simulation_real_only_24h.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/xgboost_threshold_blocked_validation_simulation_real_only_24h.md"))
    parser.add_argument("--sweep-output", type=Path, default=Path("reports/xgboost_threshold_sweep_simulation_real_only_24h.csv"))
    parser.add_argument("--predictions-output", type=Path, default=Path("reports/xgboost_blocked_validation_predictions_simulation_real_only_24h.csv"))
    parser.add_argument("--model-output-dir", type=Path, default=Path("models/blocked_validation"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--recall-floor", type=float, default=0.95)
    parser.add_argument("--n-estimators", type=int, default=120)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.input)
    features = json.loads(args.feature_list.read_text(encoding="utf-8"))
    df["label"] = df["label"].map(label_to_int).astype(int)
    for feature in features:
        df[feature] = pd.to_numeric(df[feature], errors="coerce")

    reports: dict[str, Any] = {}
    sweep_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    for strategy in ["run_blocked", "time_blocked", "scenario_time_blocked"]:
        split = build_split(df, strategy, args.seed)
        result, strategy_sweep, strategy_predictions = evaluate_strategy(
            df=df,
            split=split,
            strategy=strategy,
            features=features,
            seed=args.seed,
            recall_floor=args.recall_floor,
            n_estimators=args.n_estimators,
            model_output_dir=args.model_output_dir,
        )
        reports[strategy] = result
        sweep_rows.extend(strategy_sweep)
        prediction_rows.extend(strategy_predictions)

    final_report = {
        "input": str(args.input),
        "feature_list": str(args.feature_list),
        "recall_floor": args.recall_floor,
        "strategies": reports,
        "recommendation": build_recommendation(reports),
        "notes": [
            "Threshold is selected on validation data and reported on test data.",
            "Run-blocked split keeps run_id groups from crossing train/validation/test.",
            "Time-blocked split trains on earlier windows and tests on later windows.",
            "Scenario-time-blocked split keeps every scenario represented by splitting run_id groups chronologically within each scenario.",
            "Metrics are still simulation-domain results and are not public-dataset operating claims.",
        ],
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.sweep_output.parent.mkdir(parents=True, exist_ok=True)
    args.predictions_output.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(final_report, indent=2, sort_keys=True), encoding="utf-8")
    args.output_md.write_text(render_md(final_report), encoding="utf-8")
    pd.DataFrame(sweep_rows).to_csv(args.sweep_output, index=False)
    pd.DataFrame(prediction_rows).to_csv(args.predictions_output, index=False)
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print(f"wrote {args.sweep_output}")
    print(f"wrote {args.predictions_output}")


def build_split(df: pd.DataFrame, strategy: str, seed: int) -> dict[str, np.ndarray]:
    if strategy == "run_blocked":
        return run_blocked_split(df, seed)
    if strategy == "time_blocked":
        return time_blocked_split(df)
    if strategy == "scenario_time_blocked":
        return scenario_time_blocked_split(df)
    raise ValueError(f"unknown strategy: {strategy}")


def run_blocked_split(df: pd.DataFrame, seed: int) -> dict[str, np.ndarray]:
    groups = df["run_id"].fillna("").astype(str)
    for offset in range(100):
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=seed + offset)
        train_val_idx, test_idx = next(splitter.split(df, df["label"], groups=groups))
        train_val = df.iloc[train_val_idx].reset_index(drop=True)
        train_val_groups = train_val["run_id"].fillna("").astype(str)
        val_splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed + 100 + offset)
        train_local, val_local = next(val_splitter.split(train_val, train_val["label"], groups=train_val_groups))
        train_idx = train_val_idx[train_local]
        val_idx = train_val_idx[val_local]
        split = {"train": train_idx, "validation": val_idx, "test": test_idx}
        if all(has_both_labels(df.iloc[index]["label"]) for index in split.values()):
            return split
    return split


def time_blocked_split(df: pd.DataFrame) -> dict[str, np.ndarray]:
    work = df.copy()
    work["_sort_time"] = pd.to_datetime(work.get("window_start", work.index), errors="coerce", utc=True)
    work["_sort_time"] = work["_sort_time"].fillna(pd.Timestamp("1970-01-01", tz="UTC"))
    ordered = work.sort_values(["_sort_time", "sequence_index"], kind="mergesort")
    indices = ordered.index.to_numpy()
    train_end = int(len(indices) * 0.60)
    val_end = int(len(indices) * 0.80)
    return {
        "train": indices[:train_end],
        "validation": indices[train_end:val_end],
        "test": indices[val_end:],
    }


def scenario_time_blocked_split(df: pd.DataFrame) -> dict[str, np.ndarray]:
    work = df.copy()
    work["_sort_time"] = pd.to_datetime(work.get("window_start", work.index), errors="coerce", utc=True)
    work["_sort_time"] = work["_sort_time"].fillna(pd.Timestamp("1970-01-01", tz="UTC"))
    train_indices: list[np.ndarray] = []
    val_indices: list[np.ndarray] = []
    test_indices: list[np.ndarray] = []

    for _, scenario_df in work.groupby("scenario_id", dropna=False, sort=True):
        run_order = (
            scenario_df.groupby("run_id", dropna=False)["_sort_time"]
            .min()
            .sort_values(kind="mergesort")
            .index.tolist()
        )
        if len(run_order) >= 5:
            train_count = max(1, int(len(run_order) * 0.60))
            val_count = max(1, int(len(run_order) * 0.20))
            if train_count + val_count >= len(run_order):
                train_count = max(1, len(run_order) - 2)
                val_count = 1
            train_runs = set(run_order[:train_count])
            val_runs = set(run_order[train_count : train_count + val_count])
            test_runs = set(run_order[train_count + val_count :])
            train_indices.append(scenario_df[scenario_df["run_id"].isin(train_runs)].index.to_numpy())
            val_indices.append(scenario_df[scenario_df["run_id"].isin(val_runs)].index.to_numpy())
            test_indices.append(scenario_df[scenario_df["run_id"].isin(test_runs)].index.to_numpy())
        else:
            ordered = scenario_df.sort_values(["_sort_time", "sequence_index"], kind="mergesort")
            indices = ordered.index.to_numpy()
            train_end = max(1, int(len(indices) * 0.60))
            val_end = max(train_end + 1, int(len(indices) * 0.80))
            train_indices.append(indices[:train_end])
            val_indices.append(indices[train_end:val_end])
            test_indices.append(indices[val_end:])

    return {
        "train": np.concatenate(train_indices) if train_indices else np.array([], dtype=int),
        "validation": np.concatenate(val_indices) if val_indices else np.array([], dtype=int),
        "test": np.concatenate(test_indices) if test_indices else np.array([], dtype=int),
    }


def evaluate_strategy(
    df: pd.DataFrame,
    split: dict[str, np.ndarray],
    strategy: str,
    features: list[str],
    seed: int,
    recall_floor: float,
    n_estimators: int,
    model_output_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    train_df = df.iloc[split["train"]].copy()
    train_df["_original_index"] = split["train"]
    train_df = train_df.reset_index(drop=True)
    val_df = df.iloc[split["validation"]].copy()
    val_df["_original_index"] = split["validation"]
    val_df = val_df.reset_index(drop=True)
    test_df = df.iloc[split["test"]].copy()
    test_df["_original_index"] = split["test"]
    test_df = test_df.reset_index(drop=True)

    y_train = train_df["label"].astype(int).to_numpy()
    y_val = val_df["label"].astype(int).to_numpy()
    y_test = test_df["label"].astype(int).to_numpy()
    if len(np.unique(y_train)) < 2:
        return {
            "status": "failed",
            "reason": "train split does not contain both labels",
            "split_summary": split_summary(train_df, val_df, test_df),
        }, [], []

    preprocessor = SimpleImputer(strategy="median")
    x_train = preprocessor.fit_transform(matrix(train_df, features))
    x_val = preprocessor.transform(matrix(val_df, features))
    x_test = preprocessor.transform(matrix(test_df, features))
    class_counts = Counter(y_train)
    model = XGBClassifier(
        n_estimators=n_estimators,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        random_state=seed,
        scale_pos_weight=class_counts.get(0, 1) / max(class_counts.get(1, 1), 1),
        n_jobs=2,
    )
    model.fit(x_train, y_train)
    val_prob = model.predict_proba(x_val)[:, 1]
    test_prob = model.predict_proba(x_test)[:, 1]
    thresholds = np.round(np.arange(0.05, 0.951, 0.01), 2)
    val_sweep = [threshold_metrics(y_val, val_prob, threshold, strategy, "validation") for threshold in thresholds]
    test_sweep = [threshold_metrics(y_test, test_prob, threshold, strategy, "test") for threshold in thresholds]
    selected = select_threshold(val_sweep, recall_floor)
    selected_threshold = float(selected["threshold"])
    test_at_default = threshold_metrics(y_test, test_prob, 0.50, strategy, "test")
    test_at_selected = threshold_metrics(y_test, test_prob, selected_threshold, strategy, "test")

    model_output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_output_dir / f"xgboost_{strategy}.joblib")
    joblib.dump(preprocessor, model_output_dir / f"xgboost_{strategy}_preprocessor.joblib")

    result = {
        "status": "ok",
        "selected_threshold": selected_threshold,
        "selection_rule": f"maximize validation F1 with recall >= {recall_floor}; fallback to max F1",
        "validation_at_selected": selected,
        "test_at_default_threshold": test_at_default,
        "test_at_selected_threshold": test_at_selected,
        "split_summary": split_summary(train_df, val_df, test_df),
        "model_path": str(model_output_dir / f"xgboost_{strategy}.joblib"),
        "preprocessor_path": str(model_output_dir / f"xgboost_{strategy}_preprocessor.joblib"),
    }
    prediction_rows = build_prediction_rows(
        strategy=strategy,
        split_name="validation",
        df=val_df,
        probabilities=val_prob,
        selected_threshold=selected_threshold,
    ) + build_prediction_rows(
        strategy=strategy,
        split_name="test",
        df=test_df,
        probabilities=test_prob,
        selected_threshold=selected_threshold,
    )
    return result, val_sweep + test_sweep, prediction_rows


def build_prediction_rows(
    strategy: str,
    split_name: str,
    df: pd.DataFrame,
    probabilities: np.ndarray,
    selected_threshold: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for local_index, (_, row) in enumerate(df.iterrows()):
        probability = float(probabilities[local_index])
        label = int(row["label"])
        rows.append(
            {
                "strategy": strategy,
                "split": split_name,
                "local_index": local_index,
                "original_index": int(row.get("_original_index", local_index)),
                "label": label,
                "label_name": "attack" if label == 1 else "normal",
                "attack_probability": probability,
                "pred_default_0_50": int(probability >= 0.50),
                "pred_selected": int(probability >= selected_threshold),
                "selected_threshold": selected_threshold,
                "scenario_id": row.get("scenario_id", ""),
                "run_id": row.get("run_id", ""),
                "src_entity": row.get("src_entity", ""),
                "session_id": row.get("session_id", ""),
                "attack_type": row.get("attack_type", ""),
                "window_start": row.get("window_start", ""),
                "window_end": row.get("window_end", ""),
            }
        )
    return rows


def matrix(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    return df.reindex(columns=features).apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)


def threshold_metrics(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
    strategy: str,
    split_name: str,
) -> dict[str, Any]:
    y_pred = (probabilities >= threshold).astype(int)
    output = {
        "strategy": strategy,
        "split": split_name,
        "threshold": float(threshold),
        "rows": int(len(y_true)),
        "positive_rows": int(y_true.sum()),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }
    matrix_values = confusion_matrix(y_true, y_pred, labels=[0, 1])
    output["tn"], output["fp"], output["fn"], output["tp"] = [int(value) for value in matrix_values.ravel()]
    if len(np.unique(y_true)) > 1:
        output["roc_auc"] = float(roc_auc_score(y_true, probabilities))
        output["pr_auc"] = float(average_precision_score(y_true, probabilities))
    else:
        output["roc_auc"] = None
        output["pr_auc"] = None
    return output


def select_threshold(rows: list[dict[str, Any]], recall_floor: float) -> dict[str, Any]:
    eligible = [row for row in rows if row["recall"] >= recall_floor]
    candidates = eligible if eligible else rows
    return sorted(candidates, key=lambda row: (row["f1"], row["precision"], row["threshold"]), reverse=True)[0]


def split_summary(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame) -> dict[str, Any]:
    return {
        "train": frame_summary(train_df),
        "validation": frame_summary(val_df),
        "test": frame_summary(test_df),
    }


def frame_summary(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": int(len(df)),
        "label_counts": label_counts(df["label"]),
        "run_count": int(df["run_id"].nunique()) if "run_id" in df else 0,
        "scenario_counts": value_counts(df, "scenario_id"),
        "time_min": str(df["window_start"].min()) if "window_start" in df and len(df) else "",
        "time_max": str(df["window_start"].max()) if "window_start" in df and len(df) else "",
    }


def label_counts(series: pd.Series) -> dict[str, int]:
    names = {0: "normal", 1: "attack"}
    return {names.get(int(key), str(key)): int(value) for key, value in Counter(series).items()}


def value_counts(df: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in df:
        return {}
    return {str(key): int(value) for key, value in Counter(df[column].fillna("").astype(str)).items()}


def has_both_labels(series: pd.Series) -> bool:
    return len(set(series.astype(int).tolist())) >= 2


def label_to_int(value: Any) -> int:
    return 0 if str(value).strip().lower() in {"normal", "benign", "0", "false"} else 1


def build_recommendation(reports: dict[str, Any]) -> dict[str, Any]:
    recommendation: dict[str, Any] = {}
    for strategy, report in reports.items():
        if report.get("status") != "ok":
            continue
        selected = report["test_at_selected_threshold"]
        default = report["test_at_default_threshold"]
        recommendation[strategy] = {
            "recommended_threshold": report["selected_threshold"],
            "test_f1_at_recommended": selected["f1"],
            "test_precision_at_recommended": selected["precision"],
            "test_recall_at_recommended": selected["recall"],
            "default_threshold_f1": default["f1"],
            "default_threshold_precision": default["precision"],
            "default_threshold_recall": default["recall"],
            "interpretation": interpret_threshold(default, selected),
        }
    return recommendation


def interpret_threshold(default: dict[str, Any], selected: dict[str, Any]) -> str:
    precision_gain = selected["precision"] - default["precision"]
    recall_delta = selected["recall"] - default["recall"]
    return (
        f"Recommended threshold changes precision by {precision_gain:.4f} and recall by {recall_delta:.4f} "
        "against threshold 0.50 on the blocked test split."
    )


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# XGBoost Threshold and Blocked Validation",
        "",
        f"- Input: `{report['input']}`",
        f"- Recall floor: `{report['recall_floor']}`",
        "",
        "## Summary",
        "| Strategy | Threshold | Test Precision | Test Recall | Test F1 | Default Precision | Default Recall | Default F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy, result in report["strategies"].items():
        if result.get("status") != "ok":
            lines.append(f"| {strategy} | failed | | | | | | |")
            continue
        selected = result["test_at_selected_threshold"]
        default = result["test_at_default_threshold"]
        lines.append(
        "| {strategy} | {threshold:.2f} | {sp:.4f} | {sr:.4f} | {sf:.4f} | {dp:.4f} | {dr:.4f} | {df:.4f} |".format(
                strategy=strategy,
                threshold=result["selected_threshold"],
                sp=selected["precision"],
                sr=selected["recall"],
                sf=selected["f1"],
                dp=default["precision"],
                dr=default["recall"],
                df=default["f1"],
            )
        )
    lines.extend(["", "## Split Details"])
    for strategy, result in report["strategies"].items():
        lines.append(f"### {strategy}")
        if result.get("status") != "ok":
            lines.append(f"- Failed: {result.get('reason')}")
            continue
        for split_name, summary in result["split_summary"].items():
            lines.append(
                f"- {split_name}: rows={summary['rows']}, labels={summary['label_counts']}, "
                f"runs={summary['run_count']}, time={summary['time_min']}..{summary['time_max']}"
            )
    lines.extend(["", "## Notes"])
    for note in report["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
