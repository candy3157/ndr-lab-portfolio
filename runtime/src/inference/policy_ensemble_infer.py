from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.inference.common import make_prediction_result, read_json, write_json
from src.inference.gru_review_gate import evaluate_gru_review_gate, load_gate_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine XGBoost and GRU outputs with an operating policy."
    )
    parser.add_argument("--xgboost-predictions", type=Path, required=True)
    parser.add_argument("--gru-predictions", type=Path, required=True)
    parser.add_argument(
        "--policy-config",
        type=Path,
        default=Path("configs/ensemble_policy_low_slow_v2.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("reports/policy_ensemble_output.json"))
    parser.add_argument("--feature-input", type=Path, default=None)
    parser.add_argument("--gate-config", type=Path, default=Path("configs/gru_review_gate_low_slow_v1.json"))
    parser.add_argument("--disable-review-gate", action="store_true")
    parser.add_argument(
        "--promote-disagreement",
        action="store_true",
        help="Promote GRU-only attack disagreements to attack labels. Disabled by default.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    policy = read_json(args.policy_config)
    xgb_rows = read_json(args.xgboost_predictions)
    gru_rows = read_json(args.gru_predictions)
    feature_rows = load_feature_rows(args.feature_input)
    gate_config = None if args.disable_review_gate or not args.gate_config.exists() else load_gate_config(args.gate_config)
    count = min(len(xgb_rows), len(gru_rows))
    if count == 0:
        raise SystemExit("prediction files do not contain overlapping rows")

    outputs = [
        apply_policy(
            xgb_rows[index],
            gru_rows[index],
            policy,
            args.promote_disagreement,
            feature_rows[index] if index < len(feature_rows) else None,
            gate_config,
        )
        for index in range(count)
    ]
    write_json(args.output, outputs)
    print(f"wrote {args.output}")


def apply_policy(
    xgb: dict[str, Any],
    gru: dict[str, Any],
    policy: dict[str, Any],
    promote_disagreement: bool,
    feature_row: dict[str, Any] | None = None,
    gate_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    xgb_probability = float(xgb["attack_probability"])
    gru_probability = float(gru["attack_probability"])
    xgb_threshold = float(xgb.get("threshold", policy["thresholds"]["xgboost_low_slow_v2"]))
    gru_threshold = float(gru.get("threshold", policy["thresholds"]["gru_sequence_challenger"]))
    weights = policy.get("weighted_average", {})
    weighted_probability = weighted_score(
        xgb_probability,
        gru_probability,
        float(weights.get("xgboost_weight", 0.7)),
        float(weights.get("gru_weight", 0.3)),
    )

    xgb_attack = is_attack(xgb, xgb_probability, xgb_threshold)
    gru_attack = is_attack(gru, gru_probability, gru_threshold)
    disagreement = bool(gru_attack and not xgb_attack)
    gate_result = evaluate_gate(disagreement, feature_row, gate_config)
    gated_review = bool(disagreement and gate_result["gate_passed"])
    decision_probability = xgb_probability
    decision_threshold = xgb_threshold
    decision_source = "xgboost_low_slow_v2"
    automatic_promotion = False
    if promote_disagreement and gated_review:
        decision_probability = max(xgb_probability, gru_probability, weighted_probability)
        decision_threshold = min(xgb_threshold, gru_threshold)
        decision_source = "gru_sequence_gated_disagreement_promoted"
        automatic_promotion = True

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    row_metadata = {
        "input_window_start": gru.get("input_window_start") or xgb.get("input_window_start"),
        "input_window_end": gru.get("input_window_end") or xgb.get("input_window_end"),
        "dataset_name": gru.get("dataset_name") or xgb.get("dataset_name"),
        "data_source": gru.get("data_source") or xgb.get("data_source"),
    }
    result = make_prediction_result(
        model_name="ensemble_policy",
        model_version=str(policy.get("policy_version", "xgboost-primary-gru-shadow-v1")),
        feature_schema_version=str(policy.get("feature_schema_version", "ndr_common_low_slow_v2")),
        attack_probability=decision_probability,
        threshold=decision_threshold,
        row_metadata=row_metadata,
        elapsed_ms=elapsed_ms,
    )
    result.update(
        {
            "policy_name": policy.get("policy_name", "xgboost_primary_gru_challenger"),
            "decision_mode": "promote_disagreement" if promote_disagreement else "xgboost_primary",
            "decision_source": decision_source,
            "automatic_promotion": automatic_promotion,
            "review_required": gated_review,
            "review_reason": gate_result["gate_reason"] if gated_review else "",
            "gate_required": gate_config is not None,
            "gate_name": gate_result["gate_name"],
            "gate_passed": gate_result["gate_passed"],
            "gate_reason": gate_result["gate_reason"],
            "gate_failed_features": gate_result["gate_failed_features"],
            "raw_gru_xgboost_disagreement": disagreement,
            "xgboost_predicted_label": xgb.get("predicted_label"),
            "gru_predicted_label": gru.get("predicted_label"),
            "xgboost_attack_probability": round(xgb_probability, 8),
            "gru_attack_probability": round(gru_probability, 8),
            "weighted_attack_probability": round(weighted_probability, 8),
            "triage_risk_score": round(max(xgb_probability, gru_probability) * 100.0, 4),
        }
    )
    return {"xgboost": xgb, "gru": gru, "policy_decision": result}


def weighted_score(xgb_probability: float, gru_probability: float, xgb_weight: float, gru_weight: float) -> float:
    total = max(xgb_weight + gru_weight, 1e-9)
    return (xgb_probability * xgb_weight + gru_probability * gru_weight) / total


def is_attack(row: dict[str, Any], probability: float, threshold: float) -> bool:
    return str(row.get("predicted_label", "")).lower() == "attack" or probability >= threshold


def load_feature_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    df = pd.read_csv(path)
    return df.to_dict(orient="records")


def evaluate_gate(
    disagreement: bool,
    feature_row: dict[str, Any] | None,
    gate_config: dict[str, Any] | None,
) -> dict[str, Any]:
    if not disagreement:
        return {
            "gate_name": gate_config.get("gate_name", "") if gate_config else "",
            "gate_passed": False,
            "gate_reason": "",
            "gate_failed_features": [],
        }
    if gate_config is None:
        return {
            "gate_name": "",
            "gate_passed": True,
            "gate_reason": "gru_review_allowed_without_gate",
            "gate_failed_features": [],
        }
    if feature_row is None:
        return {
            "gate_name": gate_config.get("gate_name", ""),
            "gate_passed": False,
            "gate_reason": "gru_review_suppressed_missing_gate_features",
            "gate_failed_features": [],
        }
    result = evaluate_gru_review_gate(feature_row, gate_config)
    return {
        "gate_name": result["gate_name"],
        "gate_passed": bool(result["gate_passed"]),
        "gate_reason": str(result["gate_reason"]),
        "gate_failed_features": [item["feature"] for item in result["failed_conditions"]],
    }


if __name__ == "__main__":
    main()
