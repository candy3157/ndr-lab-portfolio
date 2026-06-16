from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare simulation-only GRU with CTU-pretrained simulation fine-tuned GRU.")
    parser.add_argument("--baseline-gru", type=Path, default=Path("reports/gru_blocked_validation_predictions_simulation_baseline_compare.csv"))
    parser.add_argument(
        "--pretrained-gru",
        type=Path,
        default=Path("reports/gru_blocked_validation_predictions_ctu13_pretrained_simulation_finetuned.csv"),
    )
    parser.add_argument("--xgb", type=Path, default=Path("reports/xgboost_blocked_validation_predictions_low_slow_v2.csv"))
    parser.add_argument("--output-json", type=Path, default=Path("reports/ctu13_pretraining_impact_report.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/ctu13_pretraining_impact_report.md"))
    parser.add_argument("--aligned-output", type=Path, default=Path("reports/ctu13_pretraining_impact_aligned_predictions.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    baseline = load_gru(args.baseline_gru, "baseline")
    pretrained = load_gru(args.pretrained_gru, "pretrained")
    xgb = load_xgb(args.xgb)
    aligned = align(baseline, pretrained, xgb)
    if aligned.empty:
        raise SystemExit("no aligned predictions found")
    report = build_report(args, aligned)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.aligned_output.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    args.output_md.write_text(render_md(report), encoding="utf-8")
    aligned.to_csv(args.aligned_output, index=False)
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print(f"wrote {args.aligned_output}")


def load_gru(path: Path, prefix: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    keep = [
        "strategy",
        "split",
        "original_index",
        "tail_label",
        "attack_probability",
        "pred_default_0_50",
        "pred_selected",
        "selected_threshold",
        "scenario_id",
        "run_id",
        "src_entity",
        "attack_type",
        "tail_window_start",
        "tail_window_end",
    ]
    df = df[keep].copy()
    return df.rename(
        columns={
            "tail_label": f"{prefix}_tail_label",
            "attack_probability": f"{prefix}_prob",
            "pred_default_0_50": f"{prefix}_pred_default",
            "pred_selected": f"{prefix}_pred_selected",
            "selected_threshold": f"{prefix}_threshold",
        }
    )


def load_xgb(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    keep = [
        "strategy",
        "split",
        "original_index",
        "label",
        "attack_probability",
        "pred_default_0_50",
        "pred_selected",
        "selected_threshold",
    ]
    return df[keep].rename(
        columns={
            "label": "xgb_label",
            "attack_probability": "xgb_prob",
            "pred_default_0_50": "xgb_pred_default",
            "pred_selected": "xgb_pred_selected",
            "selected_threshold": "xgb_threshold",
        }
    )


def align(baseline: pd.DataFrame, pretrained: pd.DataFrame, xgb: pd.DataFrame) -> pd.DataFrame:
    keys = ["strategy", "split", "original_index"]
    aligned = baseline.merge(
        pretrained[
            keys
            + [
                "pretrained_tail_label",
                "pretrained_prob",
                "pretrained_pred_default",
                "pretrained_pred_selected",
                "pretrained_threshold",
            ]
        ],
        on=keys,
        how="inner",
    ).merge(xgb, on=keys, how="inner")
    aligned["target"] = aligned["baseline_tail_label"].astype(int)
    aligned["xgb_or_pretrained_default"] = (
        (aligned["xgb_pred_selected"] == 1) | (aligned["pretrained_pred_default"] == 1)
    ).astype(int)
    aligned["xgb_or_pretrained_selected"] = (
        (aligned["xgb_pred_selected"] == 1) | (aligned["pretrained_pred_selected"] == 1)
    ).astype(int)
    aligned["pretrained_review_default"] = (
        (aligned["xgb_pred_selected"] == 0) & (aligned["pretrained_pred_default"] == 1)
    ).astype(int)
    aligned["pretrained_review_selected"] = (
        (aligned["xgb_pred_selected"] == 0) & (aligned["pretrained_pred_selected"] == 1)
    ).astype(int)
    return aligned


def build_report(args: argparse.Namespace, aligned: pd.DataFrame) -> dict[str, Any]:
    strategies = {}
    for strategy in sorted(aligned["strategy"].unique()):
        test = aligned[(aligned["strategy"] == strategy) & (aligned["split"] == "test")].copy()
        if test.empty:
            continue
        strategies[strategy] = summarize_strategy(test)
    return {
        "inputs": {
            "baseline_gru": str(args.baseline_gru),
            "pretrained_gru": str(args.pretrained_gru),
            "xgboost_low_slow_v2": str(args.xgb),
        },
        "aligned_rows": int(len(aligned)),
        "strategies": strategies,
        "judgement": judge(strategies),
        "notes": [
            "CTU-13 is cross-domain botnet/C2 data and is not merged into IPCAM operating metrics.",
            "Selected-threshold metrics use validation-selected thresholds; default metrics use threshold 0.50.",
            "Review counts show GRU attack while XGBoost low-slow v2 predicts normal.",
        ],
    }


def summarize_strategy(test: pd.DataFrame) -> dict[str, Any]:
    y = test["target"].astype(int)
    summary = {
        "rows": int(len(test)),
        "target_counts": counts(y),
        "scenario_counts": counts(test["scenario_id"]),
        "metrics": {
            "gru_baseline_default_0_50": metrics_for(y, test["baseline_pred_default"]),
            "gru_baseline_selected": metrics_for(y, test["baseline_pred_selected"]),
            "gru_ctu_pretrained_default_0_50": metrics_for(y, test["pretrained_pred_default"]),
            "gru_ctu_pretrained_selected": metrics_for(y, test["pretrained_pred_selected"]),
            "xgboost_low_slow_v2_selected": metrics_for(y, test["xgb_pred_selected"]),
            "xgb_or_pretrained_default": metrics_for(y, test["xgb_or_pretrained_default"]),
            "xgb_or_pretrained_selected": metrics_for(y, test["xgb_or_pretrained_selected"]),
        },
        "review_signal": {
            "default_0_50": review_summary(test, "pretrained_review_default"),
            "selected": review_summary(test, "pretrained_review_selected"),
        },
        "low_and_slow_subset": {},
    }
    low = test[test["scenario_id"].astype(str) == "low-and-slow"]
    if not low.empty:
        y_low = low["target"].astype(int)
        summary["low_and_slow_subset"] = {
            "rows": int(len(low)),
            "target_counts": counts(y_low),
            "metrics": {
                "gru_baseline_default_0_50": metrics_for(y_low, low["baseline_pred_default"]),
                "gru_baseline_selected": metrics_for(y_low, low["baseline_pred_selected"]),
                "gru_ctu_pretrained_default_0_50": metrics_for(y_low, low["pretrained_pred_default"]),
                "gru_ctu_pretrained_selected": metrics_for(y_low, low["pretrained_pred_selected"]),
                "xgboost_low_slow_v2_selected": metrics_for(y_low, low["xgb_pred_selected"]),
                "xgb_or_pretrained_default": metrics_for(y_low, low["xgb_or_pretrained_default"]),
                "xgb_or_pretrained_selected": metrics_for(y_low, low["xgb_or_pretrained_selected"]),
            },
            "review_signal": {
                "default_0_50": review_summary(low, "pretrained_review_default"),
                "selected": review_summary(low, "pretrained_review_selected"),
            },
        }
    return summary


def review_summary(df: pd.DataFrame, column: str) -> dict[str, Any]:
    review = df[df[column] == 1]
    return {
        "review_rows": int(len(review)),
        "true_attack_reviews": int((review["target"] == 1).sum()),
        "normal_reviews": int((review["target"] == 0).sum()),
        "by_scenario": counts(review["scenario_id"]) if not review.empty else {},
    }


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


def judge(strategies: dict[str, Any]) -> dict[str, Any]:
    judgement: dict[str, Any] = {}
    for strategy, item in strategies.items():
        base = item["metrics"]["gru_baseline_default_0_50"]
        pre = item["metrics"]["gru_ctu_pretrained_default_0_50"]
        selected_pre = item["metrics"]["gru_ctu_pretrained_selected"]
        xgb = item["metrics"]["xgboost_low_slow_v2_selected"]
        review = item["review_signal"]["default_0_50"]
        judgement[strategy] = {
            "default_threshold_f1_delta_vs_gru_baseline": pre["f1"] - base["f1"],
            "default_threshold_recall_delta_vs_gru_baseline": pre["recall"] - base["recall"],
            "selected_threshold_f1": selected_pre["f1"],
            "xgboost_selected_f1": xgb["f1"],
            "default_review_rows": review["review_rows"],
            "default_review_true_attack_rows": review["true_attack_reviews"],
            "default_review_normal_rows": review["normal_reviews"],
            "interpretation": interpretation(strategy, base, pre, selected_pre, review),
        }
    return judgement


def interpretation(
    strategy: str,
    baseline: dict[str, Any],
    pretrained_default: dict[str, Any],
    pretrained_selected: dict[str, Any],
    review: dict[str, Any],
) -> str:
    f1_delta = pretrained_default["f1"] - baseline["f1"]
    recall_delta = pretrained_default["recall"] - baseline["recall"]
    if recall_delta > 0.05 and review["normal_reviews"] == 0:
        return f"CTU pretraining materially improves default-threshold recall/F1 for {strategy} with clean review signals."
    if f1_delta > 0:
        return f"CTU pretraining improves default-threshold F1 for {strategy}, but threshold policy still needs validation."
    if pretrained_selected["f1"] < pretrained_default["f1"]:
        return f"CTU pretraining helps only with threshold 0.50 in {strategy}; validation-selected threshold is unstable."
    return f"CTU pretraining does not clearly improve {strategy}."


def counts(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in series.value_counts().items()}


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# CTU-13 Pretraining Impact Report",
        "",
        f"- Aligned rows: `{report['aligned_rows']}`",
        "",
        "## Metrics",
        "| Strategy | Model/Policy | Precision | Recall | F1 | FN | FP |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    order = [
        "gru_baseline_default_0_50",
        "gru_baseline_selected",
        "gru_ctu_pretrained_default_0_50",
        "gru_ctu_pretrained_selected",
        "xgboost_low_slow_v2_selected",
        "xgb_or_pretrained_default",
        "xgb_or_pretrained_selected",
    ]
    for strategy, item in report["strategies"].items():
        for model in order:
            metric = item["metrics"][model]
            lines.append(
                f"| {strategy} | {model} | {metric['precision']:.4f} | {metric['recall']:.4f} | "
                f"{metric['f1']:.4f} | {metric['fn']} | {metric['fp']} |"
            )
    lines.extend(["", "## Review Signal"])
    for strategy, item in report["strategies"].items():
        default_review = item["review_signal"]["default_0_50"]
        selected_review = item["review_signal"]["selected"]
        lines.append(
            f"- {strategy}: default review `{default_review}`, selected review `{selected_review}`"
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
