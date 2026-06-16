#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Combined 10 ensemble predictions into dashboard event JSON."
    )
    parser.add_argument("--ensemble", type=Path, required=True, help="Path to ensemble_predictions.json")
    parser.add_argument("--features", type=Path, required=True, help="Path to the feature CSV used for inference")
    parser.add_argument("--output", type=Path, required=True, help="Path to write dashboard events JSON")
    parser.add_argument("--sensor-id", default="sensor-01")
    parser.add_argument("--src-ip", default="")
    parser.add_argument("--target-network", default="")
    parser.add_argument("--window-seconds", type=int, default=10)
    parser.add_argument("--warning-threshold", type=float, default=0.55)
    parser.add_argument("--scanning-threshold", type=float, default=0.85)
    parser.add_argument("--include-raw", action="store_true", help="Include source rows and model outputs in raw payload")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensemble_rows = read_json(args.ensemble)
    feature_rows = index_feature_rows(args.features)

    events: list[dict[str, Any]] = []
    for index, item in enumerate(ensemble_rows):
        xgb = item.get("xgboost") or {}
        gru = item.get("gru") or {}
        ensemble = item.get("ensemble") or {}
        window_end = first_prediction_value("input_window_end", ensemble, gru, xgb)
        dataset_name = first_prediction_value("dataset_name", ensemble, gru, xgb)
        data_source = first_prediction_value("data_source", ensemble, gru, xgb)
        source_key = (
            first_prediction_value("src_entity", ensemble, gru, xgb)
            or first_prediction_value("src_ip", ensemble, gru, xgb)
        )
        feature_row = feature_rows.get(row_key(window_end, dataset_name, data_source, source_key))
        if feature_row is None:
            feature_row = feature_rows.get(row_key(window_end, dataset_name, data_source, ""))

        score = clamp_probability(ensemble.get("attack_probability", 0.0))
        status = status_from_score(
            score=score,
            predicted_label=str(ensemble.get("predicted_label") or ""),
            warning_threshold=args.warning_threshold,
            scanning_threshold=args.scanning_threshold,
        )

        timestamp = (
            get_value(feature_row, "window_end")
            or window_end
            or utc_now()
        )
        window_seconds = int(
            get_value(feature_row, "window_seconds")
            or first_prediction_value("window_seconds", ensemble, gru, xgb)
            or args.window_seconds
        )
        event = {
            "timestamp": timestamp,
            "sensor_id": args.sensor_id,
            "status": status,
            "score": score,
            "src_ip": args.src_ip or first_prediction_value("src_ip", ensemble, gru, xgb) or get_value(feature_row, "src_ip") or "",
            "target_network": args.target_network or first_prediction_value("target_network", ensemble, gru, xgb) or get_value(feature_row, "target_network") or "",
            "primary_dst_ip": first_row_value(feature_row, "primary_dst_ip", ensemble, gru, xgb),
            "top_dst_ips": parse_ips(first_row_value(feature_row, "top_dst_ips", ensemble, gru, xgb)),
            "window_seconds": window_seconds,
            "flow_count": to_int(first_row_value(feature_row, "flow_count", ensemble, gru, xgb)),
            "unique_dst_ips": to_int(first_row_value(feature_row, "unique_dst_count", ensemble, gru, xgb)),
            "unique_dst_ports": to_int(first_row_value(feature_row, "unique_dst_port_count", ensemble, gru, xgb)),
            "syn_count": to_int(get_value(feature_row, "syn_count")),
            "failed_connection_ratio": to_float(first_row_value(feature_row, "failed_conn_ratio", ensemble, gru, xgb)),
            "top_dst_ports": parse_ports(first_row_value(feature_row, "top_dst_ports", ensemble, gru, xgb)),
            "ensemble_probability": score,
            "ensemble_pred": int(ensemble.get("predicted_label") == "attack"),
            "xgboost_probability": clamp_probability(xgb.get("attack_probability", 0.0)),
            "gru_probability": clamp_probability(gru.get("attack_probability", 0.0)),
            "source_dataset": get_value(feature_row, "source_dataset") or "",
            "dataset_name": get_value(feature_row, "dataset_name") or dataset_name,
            "data_source": get_value(feature_row, "data_source") or data_source,
            "session_id": first_row_value(feature_row, "session_id", ensemble, gru, xgb),
            "scenario_id": first_row_value(feature_row, "scenario_id", ensemble, gru, xgb),
            "run_id": first_row_value(feature_row, "run_id", ensemble, gru, xgb),
            "src_entity": first_row_value(feature_row, "src_entity", ensemble, gru, xgb),
            "attack_type": first_row_value(feature_row, "attack_type", ensemble, gru, xgb),
            "original_index": get_value(feature_row, "original_index") or str(index),
        }
        if not event["primary_dst_ip"] and event["top_dst_ips"]:
            event["primary_dst_ip"] = event["top_dst_ips"][0]
        if args.include_raw:
            event["raw"] = {"xgboost": xgb, "gru": gru, "ensemble": ensemble, "feature_row": feature_row or {}}
        events.append(event)

    write_json(args.output, events)
    print(f"wrote {args.output}")
    print(f"converted {len(events)} ensemble rows into dashboard events")
    return 0


def read_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"{path} must contain a JSON array")
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        rows.append(item)
    return rows


def index_feature_rows(path: Path) -> dict[tuple[str, str, str, str], dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        indexed: dict[tuple[str, str, str, str], dict[str, str]] = {}
        for row in reader:
            key = row_key(
                row.get("window_end", ""),
                row.get("dataset_name", ""),
                row.get("data_source", ""),
                row.get("src_entity", "") or row.get("src_ip", ""),
            )
            if key[0]:
                indexed.setdefault(key, row)
                indexed.setdefault(row_key(key[0], key[1], key[2], ""), row)
        return indexed


def row_key(window_end: str, dataset_name: str, data_source: str, source: str) -> tuple[str, str, str, str]:
    return (
        normalize_text(window_end),
        normalize_text(dataset_name),
        normalize_text(data_source),
        normalize_text(source),
    )


def normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    return text


def get_value(row: dict[str, str] | None, key: str) -> str:
    if not row:
        return ""
    return normalize_text(row.get(key, ""))


def first_prediction_value(key: str, *rows: dict[str, Any]) -> str:
    for row in rows:
        value = normalize_text(row.get(key, ""))
        if value:
            return value
    return ""


def first_row_value(feature_row: dict[str, str] | None, key: str, *prediction_rows: dict[str, Any]) -> str:
    value = get_value(feature_row, key)
    if value:
        return value
    return first_prediction_value(key, *prediction_rows)


def clamp_probability(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def status_from_score(score: float, predicted_label: str, warning_threshold: float, scanning_threshold: float) -> str:
    if predicted_label == "attack" and score >= scanning_threshold:
        return "scanning"
    if score >= warning_threshold:
        return "warning"
    return "normal"


def to_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_ports(value: str) -> list[int]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        loaded = [item.strip() for item in value.split(",") if item.strip()]
    ports: list[int] = []
    if isinstance(loaded, list):
        for item in loaded[:20]:
            try:
                port = int(float(item))
            except (TypeError, ValueError):
                continue
            if 0 <= port <= 65535:
                ports.append(port)
    return ports


def parse_ips(value: str) -> list[str]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        loaded = [item.strip() for item in value.split(",") if item.strip()]
    ips: list[str] = []
    if isinstance(loaded, list):
        for item in loaded[:20]:
            text = normalize_text(item)
            if text:
                ips.append(text)
    return ips


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
