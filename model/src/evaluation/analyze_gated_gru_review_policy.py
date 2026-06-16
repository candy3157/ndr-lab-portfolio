from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.inference.gru_review_gate import evaluate_gru_review_gate, load_gate_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate feature-gated GRU review policy.")
    parser.add_argument("--aligned-predictions", type=Path, default=Path("reports/ctu13_pretraining_impact_aligned_predictions.csv"))
    parser.add_argument("--feature-input", type=Path, default=Path("data/processed/simulation_real_only_24h_low_slow_features.csv"))
    parser.add_argument("--gate-config", type=Path, default=Path("configs/gru_review_gate_low_slow_v1.json"))
    parser.add_argument("--output-json", type=Path, default=Path("reports/gated_gru_review_policy_report.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/gated_gru_review_policy_report.md"))
    parser.add_argument("--aligned-output", type=Path, default=Path("reports/gated_gru_review_policy_predictions.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gate_config = load_gate_config(args.gate_config)
    aligned = pd.read_csv(args.aligned_predictions)
    features = pd.read_csv(args.feature_input)
    feature_rows = features.reset_index().rename(columns={"index": "original_index"})
    merged = aligned.merge(feature_rows, on="original_index", how="left", suffixes=("", "_feature"))
    merged = apply_gate(merged, gate_config)
    report = build_report(args, gate_config, merged)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.aligned_output.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    args.output_md.write_text(render_md(report), encoding="utf-8")
    merged.to_csv(args.aligned_output, index=False)
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print(f"wrote {args.aligned_output}")


def apply_gate(df: pd.DataFrame, gate_config: dict[str, Any]) -> pd.DataFrame:
    gate_passed: list[bool] = []
    gate_reason: list[str] = []
    failed_features: list[str] = []
    for _, row in df.iterrows():
        result = evaluate_gru_review_gate(row.to_dict(), gate_config)
        gate_passed.append(bool(result["gate_passed"]))
        gate_reason.append(str(result["gate_reason"]))
        failed_features.append(",".join(item["feature"] for item in result["failed_conditions"]))
    out = df.copy()
    out["gru_review_gate_passed"] = gate_passed
    out["gru_review_gate_reason"] = gate_reason
    out["gru_review_gate_failed_features"] = failed_features
    out["pretrained_review_default_gated"] = (
        (out["pretrained_review_default"] == 1) & out["gru_review_gate_passed"]
    ).astype(int)
    out["xgb_or_pretrained_default_gated"] = (
        (out["xgb_pred_selected"] == 1) | (out["pretrained_review_default_gated"] == 1)
    ).astype(int)
    return out


def build_report(args: argparse.Namespace, gate_config: dict[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    strategies = {}
    for strategy in sorted(df["strategy"].unique()):
        test = df[(df["strategy"] == strategy) & (df["split"] == "test")].copy()
        if test.empty:
            continue
        strategies[strategy] = summarize_strategy(test)
    return {
        "inputs": {
            "aligned_predictions": str(args.aligned_predictions),
            "feature_input": str(args.feature_input),
            "gate_config": str(args.gate_config),
        },
        "gate": {
            "gate_name": gate_config.get("gate_name"),
            "mode": gate_config.get("mode"),
            "conditions": gate_config.get("conditions", []),
            "notes": gate_config.get("notes", []),
        },
        "aligned_rows": int(len(df)),
        "strategies": strategies,
        "judgement": judge(strategies),
        "notes": [
            "Gate decisions use rolling behavior features only; scenario_id, attack_type, and labels are used only for evaluation.",
            "Gated review rows represent GRU attack while XGBoost low-slow v2 predicts normal and feature gate passes.",
            "Metrics for xgb_or_pretrained_default_gated show the upper-bound effect if gated reviews were promoted to attack.",
        ],
    }


def summarize_strategy(test: pd.DataFrame) -> dict[str, Any]:
    y = test["target"].astype(int)
    review_before = test[test["pretrained_review_default"] == 1]
    review_after = test[test["pretrained_review_default_gated"] == 1]
    summary = {
        "rows": int(len(test)),
        "target_counts": counts(y),
        "scenario_counts": counts(test["scenario_id"]),
        "metrics": {
            "xgboost_low_slow_v2_selected": metrics_for(y, test["xgb_pred_selected"]),
            "gru_ctu_pretrained_default_0_50": metrics_for(y, test["pretrained_pred_default"]),
            "xgb_or_pretrained_default_before_gate": metrics_for(y, test["xgb_or_pretrained_default"]),
            "xgb_or_pretrained_default_after_gate": metrics_for(y, test["xgb_or_pretrained_default_gated"]),
        },
        "review_before_gate": review_summary(review_before),
        "review_after_gate": review_summary(review_after),
        "review_reduction": {
            "rows": int(len(review_before) - len(review_after)),
            "normal_rows": int((review_before["target"] == 0).sum() - (review_after["target"] == 0).sum()),
            "true_attack_rows": int((review_before["target"] == 1).sum() - (review_after["target"] == 1).sum()),
        },
        "low_and_slow_subset": {},
    }
    low = test[test["scenario_id"].astype(str) == "low-and-slow"]
    if not low.empty:
        y_low = low["target"].astype(int)
        low_before = low[low["pretrained_review_default"] == 1]
        low_after = low[low["pretrained_review_default_gated"] == 1]
        summary["low_and_slow_subset"] = {
            "rows": int(len(low)),
            "target_counts": counts(y_low),
            "metrics": {
                "xgboost_low_slow_v2_selected": metrics_for(y_low, low["xgb_pred_selected"]),
                "gru_ctu_pretrained_default_0_50": metrics_for(y_low, low["pretrained_pred_default"]),
                "xgb_or_pretrained_default_before_gate": metrics_for(y_low, low["xgb_or_pretrained_default"]),
                "xgb_or_pretrained_default_after_gate": metrics_for(y_low, low["xgb_or_pretrained_default_gated"]),
            },
            "review_before_gate": review_summary(low_before),
            "review_after_gate": review_summary(low_after),
        }
    return summary


def review_summary(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "review_rows": int(len(df)),
        "true_attack_reviews": int((df["target"] == 1).sum()) if not df.empty else 0,
        "normal_reviews": int((df["target"] == 0).sum()) if not df.empty else 0,
        "by_scenario": counts(df["scenario_id"]) if not df.empty else {},
    }


def judge(strategies: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for strategy, item in strategies.items():
        before = item["review_before_gate"]
        after = item["review_after_gate"]
        low = item.get("low_and_slow_subset", {})
        low_after = low.get("review_after_gate", {})
        output[strategy] = {
            "review_rows_before": before["review_rows"],
            "review_rows_after": after["review_rows"],
            "normal_reviews_before": before["normal_reviews"],
            "normal_reviews_after": after["normal_reviews"],
            "true_attack_reviews_before": before["true_attack_reviews"],
            "true_attack_reviews_after": after["true_attack_reviews"],
            "low_and_slow_reviews_after": low_after.get("true_attack_reviews", 0),
            "interpretation": interpretation(strategy, before, after, low_after),
        }
    return output


def interpretation(strategy: str, before: dict[str, Any], after: dict[str, Any], low_after: dict[str, Any]) -> str:
    normal_drop = before["normal_reviews"] - after["normal_reviews"]
    true_attack_drop = before["true_attack_reviews"] - after["true_attack_reviews"]
    if normal_drop > 0 and true_attack_drop == 0:
        return f"Gate removes {normal_drop} normal reviews while preserving true attack reviews for {strategy}."
    if normal_drop > 0:
        return f"Gate removes {normal_drop} normal reviews but loses {true_attack_drop} true attack reviews for {strategy}."
    if low_after.get("true_attack_reviews", 0) > 0:
        return f"Gate preserves low-and-slow review signals for {strategy}, but does not reduce normal reviews."
    return f"Gate has no useful effect for {strategy}."


def metrics_for(y_true: Any, y_pred: Any) -> dict[str, Any]:
    y_true_arr = np.asarray(y_true, dtype=int)
    y_pred_arr = np.asarray(y_pred, dtype=int)
    matrix = confusion_matrix(y_true_arr, y_pred_arr, labels=[0, 1])
    tn, fp, fn, tp = [int(value) for value in matrix.ravel()]
    return {
        "accuracy": float(accuracy_score(y_true_arr, y_pred_arr)),
        "precision": float(precision_score(y_true_arr, y_pred_arr, zero_division=0)),
        "recall": float(recall_score(y_true_arr, y_pred_arr, zero_division=0)),
        "f1": float(f1_score(y_true_arr, y_pred_arr, zero_division=0)),
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "tp": tp,
    }


def counts(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in series.value_counts().items()}


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Gated GRU Review Policy Report",
        "",
        f"- Aligned rows: `{report['aligned_rows']}`",
        f"- Gate: `{report['gate']['gate_name']}`",
        f"- Mode: `{report['gate']['mode']}`",
        "",
        "## Gate Conditions",
    ]
    for condition in report["gate"]["conditions"]:
        lines.append(
            f"- `{condition['feature']} {condition['operator']} {condition['value']}`: {condition.get('reason', '')}"
        )
    lines.extend(
        [
            "",
            "## Review Before/After",
            "| Strategy | Reviews Before | Reviews After | Normal Before | Normal After | Attack Before | Attack After |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for strategy, item in report["judgement"].items():
        lines.append(
            f"| {strategy} | {item['review_rows_before']} | {item['review_rows_after']} | "
            f"{item['normal_reviews_before']} | {item['normal_reviews_after']} | "
            f"{item['true_attack_reviews_before']} | {item['true_attack_reviews_after']} |"
        )
    lines.extend(
        [
            "",
            "## Metrics If Gated Reviews Are Promoted",
            "| Strategy | Policy | Precision | Recall | F1 | FN | FP |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for strategy, item in report["strategies"].items():
        for policy in ["xgboost_low_slow_v2_selected", "xgb_or_pretrained_default_before_gate", "xgb_or_pretrained_default_after_gate"]:
            metric = item["metrics"][policy]
            lines.append(
                f"| {strategy} | {policy} | {metric['precision']:.4f} | {metric['recall']:.4f} | "
                f"{metric['f1']:.4f} | {metric['fn']} | {metric['fp']} |"
            )
    lines.extend(["", "## Judgement"])
    for strategy, item in report["judgement"].items():
        lines.append(f"- {strategy}: {item['interpretation']}")
    lines.extend(["", "## Notes"])
    for note in report["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
