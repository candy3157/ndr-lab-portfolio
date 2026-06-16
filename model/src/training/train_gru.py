from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
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
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.sequence_dataset import build_sequences, prepare_frame, split_by_group


DEFAULT_CONFIG = {
    "sequence_length": 6,
    "stride": 1,
    "batch_size": 32,
    "hidden_size": 32,
    "num_layers": 1,
    "dropout": 0.1,
    "learning_rate": 0.001,
    "epochs": 3,
    "early_stopping_patience": 2,
    "test_size": 0.25,
    "validation_size": 0.20,
    "seed": 42,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train GRU binary sequence challenger for NDR features.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/common_ndr_features_smoke.csv"))
    parser.add_argument("--feature-schema", type=Path, default=Path("configs/feature_schema.json"))
    parser.add_argument("--config", type=Path, default=Path("configs/gru_config.yaml"))
    parser.add_argument("--model-output", type=Path, default=Path("models/gru_model.pt"))
    parser.add_argument("--scaler-output", type=Path, default=Path("models/gru_scaler.joblib"))
    parser.add_argument("--feature-list-output", type=Path, default=Path("models/gru_feature_list.json"))
    parser.add_argument("--metrics-output", type=Path, default=Path("reports/gru_metrics.json"))
    parser.add_argument("--confusion-matrix-output", type=Path, default=Path("reports/gru_confusion_matrix.csv"))
    parser.add_argument("--history-output", type=Path, default=Path("reports/gru_training_history.csv"))
    parser.add_argument(
        "--pretrained-model",
        type=Path,
        default=None,
        help="Optional GRU checkpoint to initialize model weights before training.",
    )
    return parser.parse_args()


def main() -> None:
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
        from src.models.gru_model import GRUNDRClassifier
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PyTorch is required for GRU training. Install it in the project venv with "
            "`.venv-wsl/bin/python -m pip install torch` and rerun this command."
        ) from exc

    args = parse_args()
    config = load_config(args.config)
    set_seed(torch, int(config["seed"]))

    df, features = prepare_frame(args.input, args.feature_schema)
    train_val_df, test_df = split_by_group(df, float(config["test_size"]), int(config["seed"]))
    train_df, val_df = split_by_group(train_val_df, float(config["validation_size"]), int(config["seed"]) + 1)

    sequence_length = int(config["sequence_length"])
    stride = int(config["stride"])
    x_train_raw, y_train, _ = build_sequences(train_df, features, sequence_length, stride)
    x_val_raw, y_val, _ = build_sequences(val_df, features, sequence_length, stride)
    x_test_raw, y_test, test_meta = build_sequences(test_df, features, sequence_length, stride)
    if len(x_train_raw) == 0 or len(x_test_raw) == 0:
        raise SystemExit(
            "not enough ordered rows to build GRU train/test sequences; lower sequence_length or collect more data"
        )
    if len(np.unique(y_train)) < 2:
        raise SystemExit("GRU training requires both normal and attack sequences in train split")

    scaler = StandardScaler()
    flat_train = x_train_raw.reshape(-1, x_train_raw.shape[-1])
    scaler.fit(flat_train)
    x_train = scale_sequences(scaler, x_train_raw)
    x_val = scale_sequences(scaler, x_val_raw) if len(x_val_raw) else x_val_raw
    x_test = scale_sequences(scaler, x_test_raw)

    device = torch.device("cpu")
    model = GRUNDRClassifier(
        input_size=len(features),
        hidden_size=int(config["hidden_size"]),
        num_layers=int(config["num_layers"]),
        dropout=float(config["dropout"]),
    ).to(device)
    pretrained_source = ""
    if args.pretrained_model is not None:
        pretrained_source = load_pretrained_weights(torch, model, args.pretrained_model, features)
    positive = max(int(y_train.sum()), 1)
    negative = max(int(len(y_train) - y_train.sum()), 1)
    pos_weight = torch.tensor([negative / positive], dtype=torch.float32, device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
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
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        train_loss = float(np.mean(losses)) if losses else 0.0
        val_loss = evaluate_loss(torch, model, criterion, x_val, y_val, device) if len(x_val) else train_loss
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

    probabilities = predict_probabilities(torch, model, x_test, device)
    predictions = (probabilities >= 0.5).astype(int)
    metrics = build_metrics(
        y_true=y_test,
        probabilities=probabilities,
        predictions=predictions,
        config=config,
        features=features,
        train_sequences=len(x_train),
        validation_sequences=len(x_val),
        test_sequences=len(x_test),
        train_time_s=train_time_s,
        test_meta=test_meta,
        input_path=args.input,
        pretrained_source=pretrained_source,
    )

    ensure_parent(args.model_output)
    ensure_parent(args.scaler_output)
    ensure_parent(args.feature_list_output)
    ensure_parent(args.metrics_output)
    ensure_parent(args.confusion_matrix_output)
    ensure_parent(args.history_output)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": config,
            "features": features,
            "feature_schema_version": "ndr_common_v1",
            "pretrained_source": pretrained_source,
        },
        args.model_output,
    )
    joblib.dump(scaler, args.scaler_output)
    args.feature_list_output.write_text(json.dumps(features, indent=2), encoding="utf-8")
    args.metrics_output.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    matrix = confusion_matrix(y_test, predictions, labels=[0, 1])
    pd.DataFrame(matrix, index=["actual_normal", "actual_attack"], columns=["pred_normal", "pred_attack"]).to_csv(
        args.confusion_matrix_output
    )
    pd.DataFrame(history).to_csv(args.history_output, index=False)

    print(f"wrote {args.model_output}")
    print(f"wrote {args.scaler_output}")
    print(f"wrote {args.metrics_output}")


def load_pretrained_weights(torch: Any, model: Any, checkpoint_path: Path, features: list[str]) -> str:
    if not checkpoint_path.exists():
        raise SystemExit(f"pretrained model is missing: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    pretrained_features = checkpoint.get("features")
    if pretrained_features != features:
        raise SystemExit(
            "pretrained feature list does not match current feature list; refusing to load incompatible GRU weights"
        )
    try:
        model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    except RuntimeError as exc:
        raise SystemExit(f"pretrained GRU architecture is incompatible: {exc}") from exc
    return str(checkpoint_path)


def load_config(path: Path) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        return config
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return config
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        loaded = parse_simple_yaml(raw)
    config.update(loaded)
    return config


def parse_simple_yaml(raw: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        output[key.strip()] = parse_scalar(value.strip())
    return output


def parse_scalar(value: str) -> Any:
    value = value.strip().strip('"').strip("'")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def set_seed(torch: Any, seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)


def scale_sequences(scaler: StandardScaler, x: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return x.astype(np.float32)
    original_shape = x.shape
    scaled = scaler.transform(x.reshape(-1, original_shape[-1]))
    return scaled.reshape(original_shape).astype(np.float32)


def evaluate_loss(
    torch: Any,
    model: Any,
    criterion: Any,
    x: np.ndarray,
    y: np.ndarray,
    device: Any,
) -> float:
    if len(x) == 0:
        return 0.0
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor(x, device=device))
        loss = criterion(logits, torch.tensor(y, dtype=torch.float32, device=device))
    return float(loss.detach().cpu())


def predict_probabilities(torch: Any, model: Any, x: np.ndarray, device: Any) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor(x, device=device))
        probabilities = torch.sigmoid(logits).detach().cpu().numpy()
    return probabilities.astype(float)


def build_metrics(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    predictions: np.ndarray,
    config: dict[str, Any],
    features: list[str],
    train_sequences: int,
    validation_sequences: int,
    test_sequences: int,
    train_time_s: float,
    test_meta: list[dict[str, Any]],
    input_path: Path,
    pretrained_source: str = "",
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "model_name": "gru",
        "model_role": "sequence_challenger",
        "feature_schema_version": "ndr_common_v1",
        "input": str(input_path),
        "pretrained_source": pretrained_source,
        "config": config,
        "feature_count": len(features),
        "train_sequences": train_sequences,
        "validation_sequences": validation_sequences,
        "test_sequences": test_sequences,
        "train_time_s": train_time_s,
        "accuracy": float(accuracy_score(y_true, predictions)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "classification_report": classification_report(y_true, predictions, output_dict=True, zero_division=0),
        "dataset_breakdown": grouped_metrics(test_meta, y_true, probabilities, predictions, "dataset_name"),
        "data_source_breakdown": grouped_metrics(test_meta, y_true, probabilities, predictions, "data_source"),
    }
    if len(np.unique(y_true)) > 1:
        metrics["roc_auc"] = float(roc_auc_score(y_true, probabilities))
        metrics["pr_auc"] = float(average_precision_score(y_true, probabilities))
    else:
        metrics["roc_auc"] = None
        metrics["pr_auc"] = None
    return metrics


def grouped_metrics(
    metadata: list[dict[str, Any]],
    y_true: np.ndarray,
    probabilities: np.ndarray,
    predictions: np.ndarray,
    group_key: str,
) -> dict[str, Any]:
    if not metadata:
        return {}
    groups = np.asarray([str(item.get(group_key, "")) for item in metadata])
    output: dict[str, Any] = {}
    for group in sorted(set(groups)):
        mask = groups == group
        if not mask.any():
            continue
        group_true = y_true[mask]
        group_pred = predictions[mask]
        group_prob = probabilities[mask]
        item = {
            "sequences": int(mask.sum()),
            "accuracy": float(accuracy_score(group_true, group_pred)),
            "precision": float(precision_score(group_true, group_pred, zero_division=0)),
            "recall": float(recall_score(group_true, group_pred, zero_division=0)),
            "f1": float(f1_score(group_true, group_pred, zero_division=0)),
        }
        if len(np.unique(group_true)) > 1:
            item["roc_auc"] = float(roc_auc_score(group_true, group_prob))
            item["pr_auc"] = float(average_precision_score(group_true, group_prob))
        output[group] = item
    return output


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main()
