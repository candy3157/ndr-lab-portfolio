from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any


VALID_STATUSES = {"normal", "warning", "scanning"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_status(payload: dict[str, Any], policy: dict[str, Any]) -> str:
    raw_status = str(payload.get("status", "")).strip().lower()
    if raw_status in VALID_STATUSES:
        return raw_status

    score = clamp_score(payload.get("score"))
    scanning_threshold = float(policy.get("scanning_score_threshold", 0.85))
    warning_threshold = float(policy.get("warning_score_threshold", 0.55))
    if score >= scanning_threshold:
        return "scanning"
    if score >= warning_threshold:
        return "warning"
    return "normal"


def normalize_ports(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    ports: list[int] = []
    for item in value[:20]:
        port = to_int(item, -1)
        if 0 <= port <= 65535:
            ports.append(port)
    return ports


def normalize_strings(value: Any, limit: int = 20) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [item.strip() for item in value.split(",") if item.strip()]
        value = parsed
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value[:limit]:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def clean_text(value: Any) -> str:
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    text = str(value or "").strip()
    if text.lower() in {"nan", "nat", "none", "null"}:
        return ""
    return text


def make_json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    return value


def normalize_event(payload: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("event payload must be a JSON object")

    policy = policy or {}
    status = normalize_status(payload, policy)
    score = clamp_score(payload.get("score", 0.0))
    event = {
        "timestamp": clean_text(payload.get("timestamp")) or utc_now_iso(),
        "sensor_id": clean_text(payload.get("sensor_id")) or "sensor-unknown",
        "status": status,
        "score": score,
        "src_ip": clean_text(payload.get("src_ip")),
        "target_network": clean_text(payload.get("target_network")),
        "primary_dst_ip": clean_text(payload.get("primary_dst_ip")),
        "top_dst_ips": normalize_strings(payload.get("top_dst_ips")),
        "window_seconds": to_int(payload.get("window_seconds"), 0),
        "flow_count": to_int(payload.get("flow_count"), 0),
        "unique_dst_ips": to_int(payload.get("unique_dst_ips"), 0),
        "unique_dst_ports": to_int(payload.get("unique_dst_ports"), 0),
        "syn_count": to_int(payload.get("syn_count"), 0),
        "failed_connection_ratio": max(0.0, min(1.0, to_float(payload.get("failed_connection_ratio"), 0.0))),
        "top_dst_ports": normalize_ports(payload.get("top_dst_ports")),
    }
    event["raw"] = make_json_safe(dict(payload))
    return event


def choose_display_status(events: list[dict[str, Any]], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or {}
    hold_seconds = float(policy.get("hold_seconds", 30))
    now_epoch = datetime.now(timezone.utc).timestamp()

    recent = []
    for event in events:
        received_at_epoch = float(event.get("received_at_epoch", 0.0))
        if now_epoch - received_at_epoch <= hold_seconds:
            recent.append(event)

    selected = None
    status = "normal"
    for candidate_status in ("scanning", "warning"):
        matches = [event for event in recent if event.get("status") == candidate_status]
        if matches:
            selected = max(matches, key=lambda item: float(item.get("score", 0.0)))
            status = candidate_status
            break

    if selected is None and events:
        selected = events[0]
        if selected.get("status") in VALID_STATUSES:
            status = str(selected["status"])

    return {
        "status": status,
        "score": float(selected.get("score", 0.0)) if selected else 0.0,
        "src_ip": selected.get("src_ip", "") if selected else "",
        "target_network": selected.get("target_network", "") if selected else "",
        "primary_dst_ip": selected.get("primary_dst_ip", "") if selected else "",
        "top_dst_ips": selected.get("top_dst_ips", []) if selected else [],
        "sensor_id": selected.get("sensor_id", "") if selected else "",
        "last_seen": selected.get("received_at", "") if selected else "",
        "evidence": {
            "flow_count": to_int(selected.get("flow_count"), 0) if selected else 0,
            "unique_dst_ips": to_int(selected.get("unique_dst_ips"), 0) if selected else 0,
            "unique_dst_ports": to_int(selected.get("unique_dst_ports"), 0) if selected else 0,
            "syn_count": to_int(selected.get("syn_count"), 0) if selected else 0,
            "failed_connection_ratio": to_float(selected.get("failed_connection_ratio"), 0.0) if selected else 0.0,
            "top_dst_ports": selected.get("top_dst_ports", []) if selected else [],
            "top_dst_ips": selected.get("top_dst_ips", []) if selected else [],
        },
    }
