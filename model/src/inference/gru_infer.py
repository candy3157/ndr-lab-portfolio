from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import joblib

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.sequence_dataset import build_sequences, prepare_frame
from src.inference.common import make_prediction_result, timed_probability, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run GRU NDR sequence inference on common feature CSV.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/common_ndr_features_smoke.csv"))
    parser.add_argument("--feature-schema", type=Path, default=Path("configs/feature_schema.json"))
    parser.add_argument("--model", type=Path, default=Path("models/gru_model.pt"))
    parser.add_argument("--scaler", type=Path, default=Path("models/gru_scaler.joblib"))
    parser.add_argument("--output", type=Path, default=Path("data/predictions/gru_predictions.json"))
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to process. Use 0 for all rows.")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Write an empty JSON array instead of failing when there are not enough rows for a GRU sequence.",
    )
    return parser.parse_args()


def main() -> None:
    try:
        import numpy as np
        import torch
        from src.models.gru_model import GRUNDRClassifier
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PyTorch is required for GRU inference. Install it with "
            "`.venv-wsl/bin/python -m pip install torch`."
        ) from exc

    args = parse_args()
    require_file(args.model)
    require_file(args.scaler)
    checkpoint = torch.load(args.model, map_location="cpu")
    config = resolve_config(checkpoint)
    features = checkpoint["features"]
    df, schema_features = prepare_frame(args.input, args.feature_schema)
    missing = [feature for feature in features if feature not in schema_features]
    if missing:
        raise SystemExit(f"feature schema mismatch: missing {missing}")
    if args.limit > 0:
        df = df.head(args.limit)
    x_raw, _, metadata = build_sequences(
        df,
        features,
        int(config["sequence_length"]),
        int(config["stride"]),
    )
    if len(x_raw) == 0:
        if args.allow_empty:
            write_json(args.output, [])
            print(f"wrote {args.output}")
            print("not enough rows to build GRU inference sequences; wrote empty predictions")
            return
        raise SystemExit("not enough rows to build GRU inference sequences")
    scaler_artifact = joblib.load(args.scaler)
    x = transform_sequences(scaler_artifact, x_raw).astype("float32")
    model = GRUNDRClassifier(
        input_size=len(features),
        hidden_size=int(config["hidden_size"]),
        num_layers=int(config["num_layers"]),
        dropout=float(config["dropout"]),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    outputs: list[dict[str, Any]] = []
    for index in range(len(x)):
        probability, elapsed_ms = timed_probability(
            lambda i=index: float(
                torch.sigmoid(model(torch.tensor(x[[i]], dtype=torch.float32))).detach().cpu().numpy()[0]
            )
        )
        outputs.append(
            make_prediction_result(
                model_name="gru",
                model_version=str(checkpoint.get("model_version", "combined-10")),
                feature_schema_version=str(checkpoint.get("feature_schema_version", "ndr_common_low_slow_v2")),
                attack_probability=probability,
                threshold=args.threshold,
                row_metadata=metadata[index],
                elapsed_ms=elapsed_ms,
            )
        )
    write_json(args.output, outputs)
    print(f"wrote {args.output}")


def resolve_config(checkpoint: dict[str, Any]) -> dict[str, Any]:
    config = dict(checkpoint.get("config") or {})
    state_dict = checkpoint.get("model_state_dict") or {}
    config.setdefault("sequence_length", checkpoint.get("sequence_length", 6))
    config.setdefault("stride", checkpoint.get("stride", 1))
    config.setdefault("hidden_size", checkpoint.get("hidden_size", infer_hidden_size(state_dict)))
    config.setdefault("num_layers", checkpoint.get("num_layers", infer_num_layers(state_dict)))
    config.setdefault("dropout", checkpoint.get("dropout", 0.1))
    return config


def infer_hidden_size(state_dict: dict[str, Any]) -> int:
    weight = state_dict.get("gru.weight_hh_l0")
    if weight is not None and hasattr(weight, "shape") and len(weight.shape) == 2:
        return int(weight.shape[1])
    classifier_weight = state_dict.get("classifier.2.weight")
    if classifier_weight is not None and hasattr(classifier_weight, "shape") and len(classifier_weight.shape) == 2:
        return int(classifier_weight.shape[1])
    return 32


def infer_num_layers(state_dict: dict[str, Any]) -> int:
    layer_keys = [key for key in state_dict if key.startswith("gru.weight_ih_l")]
    return max(1, len(layer_keys))


def transform_sequences(scaler_artifact: Any, x_raw: Any) -> Any:
    flat = x_raw.reshape(-1, x_raw.shape[-1])
    if isinstance(scaler_artifact, dict):
        imputer = scaler_artifact.get("imputer")
        scaler = scaler_artifact.get("scaler")
        if imputer is not None:
            flat = imputer.transform(flat)
        if scaler is not None:
            flat = scaler.transform(flat)
        return flat.reshape(x_raw.shape)
    return scaler_artifact.transform(flat).reshape(x_raw.shape)


def require_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"required file is missing: {path}")


if __name__ == "__main__":
    main()
