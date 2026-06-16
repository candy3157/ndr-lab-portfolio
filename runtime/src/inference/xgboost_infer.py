from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.inference.common import make_prediction_result, timed_probability, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run XGBoost NDR inference on common feature CSV.")
    parser.add_argument("--input", type=Path, default=Path("data/processed/common_ndr_features_smoke.csv"))
    parser.add_argument("--model", type=Path, default=Path("models/xgboost_model.joblib"))
    parser.add_argument("--preprocessor", type=Path, default=Path("models/xgboost_preprocessor.joblib"))
    parser.add_argument("--features", type=Path, default=Path("models/xgboost_feature_list.json"))
    parser.add_argument("--output", type=Path, default=Path("data/predictions/xgboost_predictions.json"))
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to process. Use 0 for all rows.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_file(args.model)
    require_file(args.preprocessor)
    require_file(args.features)
    model = joblib.load(args.model)
    preprocessor = joblib.load(args.preprocessor)
    features = json.loads(args.features.read_text(encoding="utf-8"))
    df = pd.read_csv(args.input)
    if args.limit > 0:
        df = df.head(args.limit)
    matrix = df.reindex(columns=features).apply(pd.to_numeric, errors="coerce")
    matrix = matrix.replace([np.inf, -np.inf], np.nan)
    transformed = preprocessor.transform(matrix)
    outputs: list[dict[str, Any]] = []
    for index, row in df.iterrows():
        probability, elapsed_ms = timed_probability(lambda i=index: model.predict_proba(transformed[[i]])[0, 1])
        outputs.append(
            make_prediction_result(
                model_name="xgboost",
                model_version="v1-smoke",
                feature_schema_version="ndr_common_v1",
                attack_probability=probability,
                threshold=args.threshold,
                row_metadata={
                    "window_start": row.get("window_start", ""),
                    "window_end": row.get("window_end", ""),
                    "dataset_name": row.get("dataset_name", ""),
                    "data_source": row.get("data_source", ""),
                    "src_ip": row.get("src_ip", ""),
                    "target_network": row.get("target_network", ""),
                    "primary_dst_ip": row.get("primary_dst_ip", ""),
                    "top_dst_ips": row.get("top_dst_ips", ""),
                    "src_entity": row.get("src_entity", ""),
                    "session_id": row.get("session_id", ""),
                    "scenario_id": row.get("scenario_id", ""),
                    "run_id": row.get("run_id", ""),
                    "attack_type": row.get("attack_type", ""),
                    "flow_count": row.get("flow_count", 0),
                    "unique_dst_count": row.get("unique_dst_count", 0),
                    "unique_dst_port_count": row.get("unique_dst_port_count", 0),
                    "failed_conn_ratio": row.get("failed_conn_ratio", 0),
                    "top_dst_ports": row.get("top_dst_ports", ""),
                    "window_seconds": row.get("window_seconds", ""),
                },
                elapsed_ms=elapsed_ms,
            )
        )
    write_json(args.output, outputs)
    print(f"wrote {args.output}")


def require_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"required file is missing: {path}")


if __name__ == "__main__":
    main()
