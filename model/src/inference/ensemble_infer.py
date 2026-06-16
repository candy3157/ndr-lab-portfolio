from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.inference.common import make_prediction_result, read_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine XGBoost and GRU NDR predictions.")
    parser.add_argument("--xgboost-predictions", type=Path, required=True)
    parser.add_argument("--gru-predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/inference_sample_output.json"))
    parser.add_argument("--xgboost-weight", type=float, default=0.7)
    parser.add_argument("--gru-weight", type=float, default=0.3)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument(
        "--include-xgboost-fallback",
        action="store_true",
        help="Emit XGBoost-only rows when no aligned GRU tail-window prediction exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    xgb_rows = read_json(args.xgboost_predictions)
    gru_rows = read_json(args.gru_predictions)
    paired_rows = pair_predictions(xgb_rows, gru_rows, args.include_xgboost_fallback)
    if not paired_rows:
        raise SystemExit("prediction files do not contain overlapping rows")
    total_weight = max(args.xgboost_weight + args.gru_weight, 1e-9)
    outputs: list[dict[str, Any]] = []
    aligned_count = 0
    fallback_count = 0
    for xgb, gru in paired_rows:
        started = time.perf_counter()
        if gru is None:
            probability = float(xgb["attack_probability"])
            model_version = "xgboost-fallback-until-gru-ready"
            fallback_count += 1
        else:
            probability = (
                float(xgb["attack_probability"]) * args.xgboost_weight
                + float(gru["attack_probability"]) * args.gru_weight
            ) / total_weight
            model_version = "combined-10-soft-vote"
            aligned_count += 1
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        ensemble = make_prediction_result(
            model_name="ensemble",
            model_version=model_version,
            feature_schema_version=(gru or {}).get("feature_schema_version") or xgb.get("feature_schema_version") or "ndr_common_low_slow_v2",
            attack_probability=probability,
            threshold=args.threshold,
            row_metadata=merged_metadata(xgb, gru),
            elapsed_ms=elapsed_ms,
        )
        outputs.append({"xgboost": xgb, "gru": gru, "ensemble": ensemble})
    write_json(args.output, outputs)
    print(f"wrote {args.output}")
    print(f"aligned {aligned_count} GRU tail-window rows with XGBoost rows")
    if fallback_count:
        print(f"emitted {fallback_count} XGBoost fallback rows")


def pair_predictions(
    xgb_rows: list[dict[str, Any]],
    gru_rows: list[dict[str, Any]],
    include_xgboost_fallback: bool,
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    gru_by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in gru_rows:
        key = prediction_key(row)
        if key[0]:
            gru_by_key.setdefault(key, []).append(row)

    paired: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for xgb in xgb_rows:
        key = prediction_key(xgb)
        matches = gru_by_key.get(key, [])
        if matches:
            paired.append((xgb, matches.pop(0)))
        elif include_xgboost_fallback:
            paired.append((xgb, None))
    if paired:
        return paired

    aligned_rows = align_predictions_by_order(xgb_rows, gru_rows)
    if aligned_rows:
        return aligned_rows
    if include_xgboost_fallback:
        return [(xgb, None) for xgb in xgb_rows]
    return []


def align_predictions_by_order(
    xgb_rows: list[dict[str, Any]],
    gru_rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    xgb_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in xgb_rows:
        key = legacy_prediction_key(row)
        if key[0]:
            xgb_by_key.setdefault(key, []).append(row)

    aligned: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for gru in gru_rows:
        key = legacy_prediction_key(gru)
        matches = xgb_by_key.get(key, [])
        if matches:
            aligned.append((matches.pop(0), gru))
    if aligned:
        return aligned

    count = min(len(xgb_rows), len(gru_rows))
    return [(xgb_rows[index], gru_rows[index]) for index in range(count)]


def prediction_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    source = str(row.get("src_entity") or row.get("src_ip") or "")
    return (
        str(row.get("input_window_end") or ""),
        str(row.get("dataset_name") or ""),
        str(row.get("data_source") or ""),
        source,
    )


def legacy_prediction_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("input_window_end") or ""),
        str(row.get("dataset_name") or ""),
        str(row.get("data_source") or ""),
    )


def merged_metadata(xgb: dict[str, Any], gru: dict[str, Any] | None) -> dict[str, Any]:
    primary = gru or xgb
    metadata: dict[str, Any] = {
        "input_window_start": primary.get("input_window_start") or xgb.get("input_window_start"),
        "input_window_end": primary.get("input_window_end") or xgb.get("input_window_end"),
        "dataset_name": primary.get("dataset_name") or xgb.get("dataset_name"),
        "data_source": primary.get("data_source") or xgb.get("data_source"),
    }
    for key in (
        "src_ip",
        "target_network",
        "primary_dst_ip",
        "top_dst_ips",
        "src_entity",
        "session_id",
        "scenario_id",
        "run_id",
        "attack_type",
        "flow_count",
        "unique_dst_count",
        "unique_dst_port_count",
        "failed_conn_ratio",
        "top_dst_ports",
        "window_seconds",
    ):
        metadata[key] = primary.get(key, xgb.get(key, ""))
    return metadata


if __name__ == "__main__":
    main()
