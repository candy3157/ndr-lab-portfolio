from __future__ import annotations

import json
import operator
from pathlib import Path
from typing import Any


OPERATORS = {
    "<=": operator.le,
    "<": operator.lt,
    ">=": operator.ge,
    ">": operator.gt,
    "==": operator.eq,
}


def load_gate_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"gate config is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_gru_review_gate(row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not config.get("enabled", True):
        return {
            "gate_name": config.get("gate_name", ""),
            "gate_passed": True,
            "gate_reason": "gate_disabled",
            "failed_conditions": [],
            "passed_conditions": [],
        }
    failed: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for condition in config.get("conditions", []):
        result = evaluate_condition(row, condition)
        if result["passed"]:
            passed.append(result)
        else:
            failed.append(result)
    mode = str(config.get("mode", "all")).lower()
    gate_passed = not failed if mode == "all" else bool(passed)
    reason = config.get("allowed_review_reason" if gate_passed else "blocked_review_reason", "")
    return {
        "gate_name": config.get("gate_name", ""),
        "gate_passed": bool(gate_passed),
        "gate_reason": reason,
        "failed_conditions": failed,
        "passed_conditions": passed,
    }


def evaluate_condition(row: dict[str, Any], condition: dict[str, Any]) -> dict[str, Any]:
    feature = str(condition["feature"])
    op_text = str(condition["operator"])
    expected = float(condition["value"])
    raw = row.get(feature)
    try:
        actual = float(raw)
    except (TypeError, ValueError):
        actual = float("nan")
    op = OPERATORS.get(op_text)
    passed = bool(op(actual, expected)) if op is not None and actual == actual else False
    return {
        "feature": feature,
        "operator": op_text,
        "value": expected,
        "actual": actual if actual == actual else None,
        "passed": passed,
        "reason": condition.get("reason", ""),
    }
