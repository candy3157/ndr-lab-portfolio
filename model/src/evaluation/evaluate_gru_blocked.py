from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.sequence_dataset import load_feature_list
from src.evaluation.evaluate_xgboost_threshold_blocked import (
    build_recommendation,
    scenario_time_blocked_split,
    select_threshold,
    split_summary,
    threshold_metrics,
    time_blocked_split,
    run_blocked_split,
)
from src.models.gru_model import GRUNDRClassifier
from src.training.train_gru import load_config, load_pretrained_weights, scale_sequences, set_seed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run GRU blocked validation aligned with XGBoost splits.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/simulation_real_only_24h_common.csv"))
    parser.add_argument("--feature-schema", type=Path, default=Path("configs/feature_schema.json"))
    parser.add_argument("--config", type=Path, default=Path("configs/gru_config.yaml"))
    parser.add_argument("--output-json", type=Path, default=Path("reports/gru_blocked_validation_simulation_real_only_24h.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/gru_blocked_validation_simulation_real_only_24h.md"))
    parser.add_argument("--sweep-output", type=Path, default=Path("reports/gru_threshold_sweep_simulation_real_only_24h.csv"))
    parser.add_argument("--predictions-output", type=Path, default=Path("reports/gru_blocked_validation_predictions_simulation_real_only_24h.csv"))
    parser.add_argument("--model-output-dir", type=Path, default=Path("models/gru_blocked_validation"))
    parser.add_argument("--recall-floor", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pretrained-model", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    args = parse_args()
    config = load_config(args.config)
    config["seed"] = args.seed
    set_seed(torch, int(config["seed"]))

    df = pd.read_csv(args.input)
    df["label"] = df["label"].map(label_to_int).astype(int)
    if "sequence_index" not in df.columns:
        df["sequence_index"] = np.arange(len(df), dtype=np.int64)
    features = load_feature_list(args.feature_schema, df)
    for feature in features:
        df[feature] = pd.to_numeric(df[feature], errors="coerce")
    df[features] = df[features].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    reports: dict[str, Any] = {}
    sweep_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    for strategy in ["run_blocked", "time_blocked", "scenario_time_blocked"]:
        split = build_split(df, strategy, args.seed)
        result, strategy_sweep, strategy_predictions = evaluate_strategy(
            torch=torch,
            nn=nn,
            DataLoader=DataLoader,
            TensorDataset=TensorDataset,
            df=df,
            split=split,
            strategy=strategy,
            features=features,
            config=config,
            recall_floor=args.recall_floor,
            model_output_dir=args.model_output_dir,
            pretrained_model=args.pretrained_model,
        )
        reports[strategy] = result
        sweep_rows.extend(strategy_sweep)
        prediction_rows.extend(strategy_predictions)

    final_report = {
        "input": str(args.input),
        "feature_schema": str(args.feature_schema),
        "feature_count": len(features),
        "config": config,
        "pretrained_model": str(args.pretrained_model or ""),
        "recall_floor": args.recall_floor,
        "strategies": reports,
        "recommendation": build_recommendation(reports),
        "notes": [
            "GRU sequences are grouped by run_id/src_entity and sorted by window_start/sequence_index.",
            "Sequence prediction is aligned to the final window original_index for XGBoost comparison.",
            "Threshold is selected on validation sequences and reported on test sequences.",
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


def evaluate_strategy(
    torch: Any,
    nn: Any,
    DataLoader: Any,
    TensorDataset: Any,
    df: pd.DataFrame,
    split: dict[str, np.ndarray],
    strategy: str,
    features: list[str],
    config: dict[str, Any],
    recall_floor: float,
    model_output_dir: Path,
    pretrained_model: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    train_df = with_original_index(df, split["train"])
    val_df = with_original_index(df, split["validation"])
    test_df = with_original_index(df, split["test"])
    seq_len = int(config["sequence_length"])
    stride = int(config["stride"])
    x_train_raw, y_train, _ = build_sequences_for_eval(train_df, features, seq_len, stride)
    x_val_raw, y_val, val_meta = build_sequences_for_eval(val_df, features, seq_len, stride)
    x_test_raw, y_test, test_meta = build_sequences_for_eval(test_df, features, seq_len, stride)
    if len(x_train_raw) == 0 or len(x_val_raw) == 0 or len(x_test_raw) == 0:
        return {
            "status": "failed",
            "reason": "not enough rows to build train/validation/test sequences",
            "split_summary": split_summary(train_df, val_df, test_df),
        }, [], []
    if len(np.unique(y_train)) < 2:
        return {
            "status": "failed",
            "reason": "train sequences do not contain both labels",
            "split_summary": split_summary(train_df, val_df, test_df),
        }, [], []

    scaler = StandardScaler()
    scaler.fit(x_train_raw.reshape(-1, x_train_raw.shape[-1]))
    x_train = scale_sequences(scaler, x_train_raw)
    x_val = scale_sequences(scaler, x_val_raw)
    x_test = scale_sequences(scaler, x_test_raw)

    device = torch.device("cpu")
    model = GRUNDRClassifier(
        input_size=len(features),
        hidden_size=int(config["hidden_size"]),
        num_layers=int(config["num_layers"]),
        dropout=float(config["dropout"]),
    ).to(device)
    pretrained_source = ""
    if pretrained_model is not None:
        pretrained_source = load_pretrained_weights(torch, model, pretrained_model, features)
    positive = max(int(y_train.sum()), 1)
    negative = max(int(len(y_train) - y_train.sum()), 1)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([negative / positive], dtype=torch.float32, device=device))
    optimizer = torch.optim.Adam(model.parameters(), lr=float(config["learning_rate"]))
    train_loader = DataLoader(
        TensorDataset(torch.tensor(x_train), torch.tensor(y_train, dtype=torch.float32)),
        batch_size=int(config["batch_size"]),
        shuffle=True,
    )
    best_state = None
    best_val_loss = float("inf")
    patience_left = int(config["early_stopping_patience"])
    history: list[dict[str, Any]] = []
    started = time.perf_counter()
    for epoch in range(1, int(config["epochs"]) + 1):
        model.train()
        losses: list[float] = []
        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad()
            loss = criterion(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        val_loss = evaluate_loss(torch, model, criterion, x_val, y_val, device)
        train_loss = float(np.mean(losses)) if losses else 0.0
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            patience_left = int(config["early_stopping_patience"])
        else:
            patience_left -= 1
            if patience_left <= 0:
                break
    train_time_s = time.perf_counter() - started
    if best_state is not None:
        model.load_state_dict(best_state)

    val_prob = predict_probabilities(torch, model, x_val, device)
    test_prob = predict_probabilities(torch, model, x_test, device)
    thresholds = np.round(np.arange(0.05, 0.951, 0.01), 2)
    val_sweep = [threshold_metrics(y_val, val_prob, threshold, strategy, "validation") for threshold in thresholds]
    test_sweep = [threshold_metrics(y_test, test_prob, threshold, strategy, "test") for threshold in thresholds]
    selected = select_threshold(val_sweep, recall_floor)
    selected_threshold = float(selected["threshold"])
    test_at_default = threshold_metrics(y_test, test_prob, 0.50, strategy, "test")
    test_at_selected = threshold_metrics(y_test, test_prob, selected_threshold, strategy, "test")

    model_output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = model_output_dir / f"gru_{strategy}.pt"
    scaler_path = model_output_dir / f"gru_{strategy}_scaler.joblib"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": config,
            "features": features,
            "feature_schema_version": "ndr_common_v1",
            "strategy": strategy,
            "pretrained_source": pretrained_source,
        },
        checkpoint_path,
    )
    joblib.dump(scaler, scaler_path)

    result = {
        "status": "ok",
        "selected_threshold": selected_threshold,
        "selection_rule": f"maximize validation F1 with recall >= {recall_floor}; fallback to max F1",
        "validation_at_selected": selected,
        "test_at_default_threshold": test_at_default,
        "test_at_selected_threshold": test_at_selected,
        "split_summary": split_summary(train_df, val_df, test_df),
        "sequence_counts": {
            "train": int(len(y_train)),
            "validation": int(len(y_val)),
            "test": int(len(y_test)),
        },
        "train_time_s": train_time_s,
        "model_path": str(checkpoint_path),
        "scaler_path": str(scaler_path),
        "pretrained_source": pretrained_source,
        "history": history,
    }
    predictions = build_prediction_rows(strategy, "validation", val_meta, y_val, val_prob, selected_threshold)
    predictions += build_prediction_rows(strategy, "test", test_meta, y_test, test_prob, selected_threshold)
    return result, val_sweep + test_sweep, predictions


def with_original_index(df: pd.DataFrame, indices: np.ndarray) -> pd.DataFrame:
    out = df.iloc[indices].copy()
    out["_original_index"] = indices
    return out.reset_index(drop=True)


def build_sequences_for_eval(
    df: pd.DataFrame,
    features: list[str],
    sequence_length: int,
    stride: int,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    sequences: list[np.ndarray] = []
    labels: list[int] = []
    metadata: list[dict[str, Any]] = []
    group_cols = ["run_id", "src_entity"] if "run_id" in df.columns and "src_entity" in df.columns else ["session_id"]
    for group_key, group in df.groupby(group_cols, dropna=False, sort=False):
        ordered = sort_group(group)
        if len(ordered) < sequence_length:
            continue
        values = ordered[features].to_numpy(dtype=np.float32)
        label_values = ordered["label"].to_numpy(dtype=np.int64)
        for start in range(0, len(ordered) - sequence_length + 1, max(stride, 1)):
            end = start + sequence_length
            seq_labels = label_values[start:end]
            head = ordered.iloc[start]
            tail = ordered.iloc[end - 1]
            sequences.append(values[start:end])
            labels.append(int(seq_labels.max()))
            metadata.append(
                {
                    "group": str(group_key),
                    "original_index": int(tail.get("_original_index", -1)),
                    "label": int(seq_labels.max()),
                    "tail_label": int(tail.get("label", 0)),
                    "scenario_id": str(tail.get("scenario_id", "")),
                    "run_id": str(tail.get("run_id", "")),
                    "src_entity": str(tail.get("src_entity", "")),
                    "session_id": str(tail.get("session_id", "")),
                    "attack_type": str(tail.get("attack_type", "")),
                    "input_window_start": str(head.get("window_start", "")),
                    "input_window_end": str(tail.get("window_end", tail.get("window_start", ""))),
                    "tail_window_start": str(tail.get("window_start", "")),
                    "tail_window_end": str(tail.get("window_end", "")),
                }
            )
    if not sequences:
        return (
            np.empty((0, sequence_length, len(features)), dtype=np.float32),
            np.empty((0,), dtype=np.int64),
            [],
        )
    return np.stack(sequences).astype(np.float32), np.asarray(labels, dtype=np.int64), metadata


def sort_group(group: pd.DataFrame) -> pd.DataFrame:
    sort_cols = []
    if "window_start" in group.columns:
        sort_cols.append("window_start")
    if "sequence_index" in group.columns:
        sort_cols.append("sequence_index")
    if not sort_cols:
        return group.reset_index(drop=True)
    return group.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)


def evaluate_loss(torch: Any, model: Any, criterion: Any, x: np.ndarray, y: np.ndarray, device: Any) -> float:
    model.eval()
    with torch.no_grad():
        loss = criterion(model(torch.tensor(x, device=device)), torch.tensor(y, dtype=torch.float32, device=device))
    return float(loss.detach().cpu())


def predict_probabilities(torch: Any, model: Any, x: np.ndarray, device: Any) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor(x, dtype=torch.float32, device=device))
        return torch.sigmoid(logits).detach().cpu().numpy().astype(float)


def build_prediction_rows(
    strategy: str,
    split_name: str,
    metadata: list[dict[str, Any]],
    labels: np.ndarray,
    probabilities: np.ndarray,
    selected_threshold: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, meta in enumerate(metadata):
        probability = float(probabilities[index])
        label = int(labels[index])
        rows.append(
            {
                "strategy": strategy,
                "split": split_name,
                "sequence_index": index,
                "original_index": int(meta.get("original_index", -1)),
                "label": label,
                "label_name": "attack" if label == 1 else "normal",
                "tail_label": int(meta.get("tail_label", 0)),
                "tail_label_name": "attack" if int(meta.get("tail_label", 0)) == 1 else "normal",
                "attack_probability": probability,
                "pred_default_0_50": int(probability >= 0.50),
                "pred_selected": int(probability >= selected_threshold),
                "selected_threshold": selected_threshold,
                "scenario_id": meta.get("scenario_id", ""),
                "run_id": meta.get("run_id", ""),
                "src_entity": meta.get("src_entity", ""),
                "session_id": meta.get("session_id", ""),
                "attack_type": meta.get("attack_type", ""),
                "input_window_start": meta.get("input_window_start", ""),
                "input_window_end": meta.get("input_window_end", ""),
                "tail_window_start": meta.get("tail_window_start", ""),
                "tail_window_end": meta.get("tail_window_end", ""),
            }
        )
    return rows


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# GRU Blocked Validation",
        "",
        f"- Input: `{report['input']}`",
        f"- Feature schema: `{report['feature_schema']}`",
        f"- Feature count: `{report['feature_count']}`",
        f"- Sequence length: `{report['config'].get('sequence_length')}`",
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
    lines.extend(["", "## Sequence Counts"])
    for strategy, result in report["strategies"].items():
        if result.get("status") == "ok":
            lines.append(f"- {strategy}: `{result['sequence_counts']}`")
    lines.extend(["", "## Notes"])
    for note in report["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def label_to_int(value: Any) -> int:
    return 0 if str(value).strip().lower() in {"normal", "benign", "0", "false"} else 1


if __name__ == "__main__":
    main()
