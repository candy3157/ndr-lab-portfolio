from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any


def make_prediction_result(
    model_name: str,
    model_version: str,
    feature_schema_version: str,
    attack_probability: float,
    threshold: float,
    row_metadata: dict[str, Any] | None = None,
    elapsed_ms: float | None = None,
) -> dict[str, Any]:
    metadata = row_metadata or {}
    probability = clamp(float(attack_probability), 0.0, 1.0)
    predicted_label = "attack" if probability >= threshold else "normal"
    confidence = abs(probability - threshold) / max(threshold, 1.0 - threshold, 1e-9)
    result = {
        "model_name": model_name,
        "model_version": model_version,
        "feature_schema_version": feature_schema_version,
        "input_window_start": clean_text(metadata.get("input_window_start", metadata.get("window_start", ""))),
        "input_window_end": clean_text(metadata.get("input_window_end", metadata.get("window_end", ""))),
        "predicted_label": predicted_label,
        "attack_probability": probability,
        "risk_score": round(probability * 100.0, 4),
        "confidence": round(clamp(confidence, 0.0, 1.0), 4),
        "threshold": threshold,
        "data_source": clean_text(metadata.get("data_source", "")),
        "dataset_name": clean_text(metadata.get("dataset_name", "")),
        "inference_time_ms": round(float(elapsed_ms or 0.0), 4),
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
        if key in metadata:
            result[key] = clean_metadata_value(metadata[key])
    return result


def timed_probability(fn: Any) -> tuple[float, float]:
    started = time.perf_counter()
    probability = float(fn())
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return probability, elapsed_ms


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(make_json_safe(payload), indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def clean_text(value: Any) -> str:
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    text = str(value)
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    return text


def clean_metadata_value(value: Any) -> Any:
    value = unpack_scalar(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else ""
    if isinstance(value, str):
        return clean_text(value)
    return value


def make_json_safe(value: Any) -> Any:
    value = unpack_scalar(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    if hasattr(value, "tolist") and callable(value.tolist):
        return make_json_safe(value.tolist())
    return str(value)


def unpack_scalar(value: Any) -> Any:
    if hasattr(value, "item") and callable(value.item):
        try:
            scalar = value.item()
        except (TypeError, ValueError):
            return value
        if scalar is not value:
            return scalar
    return value
