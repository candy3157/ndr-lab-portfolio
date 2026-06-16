from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-analyze GRU and XGBoost predictions and ensemble value.")
    parser.add_argument("--xgb-v1", type=Path, default=Path("reports/xgboost_blocked_validation_predictions_simulation_real_only_24h.csv"))
    parser.add_argument("--xgb-v2", type=Path, default=Path("reports/xgboost_blocked_validation_predictions_low_slow_v2.csv"))
    parser.add_argument("--gru", type=Path, default=Path("reports/gru_blocked_validation_predictions_simulation_real_only_24h.csv"))
    parser.add_argument("--output-json", type=Path, default=Path("reports/gru_xgb_cross_analysis_report.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/gru_xgb_cross_analysis_report.md"))
    parser.add_argument("--aligned-output", type=Path, default=Path("reports/gru_xgb_aligned_predictions.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    xgb_v1 = load_xgb(args.xgb_v1, "xgb_v1")
    xgb_v2 = load_xgb(args.xgb_v2, "xgb_v2")
    gru = load_gru(args.gru)
    aligned = align_predictions(xgb_v1, xgb_v2, gru)
    if aligned.empty:
        raise SystemExit("no aligned XGBoost/GRU predictions found")
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


def load_xgb(path: Path, prefix: str) -> pd.DataFrame:
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
        "scenario_id",
        "run_id",
        "src_entity",
        "attack_type",
        "window_start",
        "window_end",
    ]
    df = df[keep].copy()
    return df.rename(
        columns={
            "label": f"{prefix}_label",
            "attack_probability": f"{prefix}_prob",
            "pred_default_0_50": f"{prefix}_pred_default",
            "pred_selected": f"{prefix}_pred_selected",
            "selected_threshold": f"{prefix}_threshold",
        }
    )


def load_gru(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    keep = [
        "strategy",
        "split",
        "original_index",
        "label",
        "tail_label",
        "attack_probability",
        "pred_default_0_50",
        "pred_selected",
        "selected_threshold",
        "scenario_id",
        "run_id",
        "src_entity",
        "attack_type",
        "input_window_start",
        "input_window_end",
        "tail_window_start",
        "tail_window_end",
    ]
    df = df[keep].copy()
    return df.rename(
        columns={
            "label": "gru_sequence_label",
            "attack_probability": "gru_prob",
            "pred_default_0_50": "gru_pred_default",
            "pred_selected": "gru_pred_selected",
            "selected_threshold": "gru_threshold",
        }
    )


def align_predictions(xgb_v1: pd.DataFrame, xgb_v2: pd.DataFrame, gru: pd.DataFrame) -> pd.DataFrame:
    keys = ["strategy", "split", "original_index"]
    xgb = xgb_v1.merge(
        xgb_v2[
            keys
            + [
                "xgb_v2_label",
                "xgb_v2_prob",
                "xgb_v2_pred_default",
                "xgb_v2_pred_selected",
                "xgb_v2_threshold",
            ]
        ],
        on=keys,
        how="inner",
    )
    aligned = xgb.merge(gru, on=keys, how="inner", suffixes=("", "_gru"))
    aligned["tail_label"] = aligned["tail_label"].astype(int)
    aligned["sequence_label"] = aligned["gru_sequence_label"].astype(int)
    aligned["or_v1_gru_tail_pred"] = ((aligned["xgb_v1_pred_selected"] == 1) | (aligned["gru_pred_selected"] == 1)).astype(int)
    aligned["or_v2_gru_tail_pred"] = ((aligned["xgb_v2_pred_selected"] == 1) | (aligned["gru_pred_selected"] == 1)).astype(int)
    aligned["weighted_v2_gru_prob"] = 0.7 * aligned["xgb_v2_prob"].astype(float) + 0.3 * aligned["gru_prob"].astype(float)
    aligned["weighted_v2_gru_pred_0_50"] = (aligned["weighted_v2_gru_prob"] >= 0.50).astype(int)
    return aligned


def build_report(args: argparse.Namespace, aligned: pd.DataFrame) -> dict[str, Any]:
    strategy_reports: dict[str, Any] = {}
    for strategy in sorted(aligned["strategy"].unique()):
        test = aligned[(aligned["strategy"] == strategy) & (aligned["split"] == "test")].copy()
        if test.empty:
            continue
        strategy_reports[strategy] = summarize_strategy(test)
    report = {
        "inputs": {
            "xgb_v1": str(args.xgb_v1),
            "xgb_v2": str(args.xgb_v2),
            "gru": str(args.gru),
        },
        "aligned_rows": int(len(aligned)),
        "test_rows_by_strategy": {
            strategy: int(len(aligned[(aligned["strategy"] == strategy) & (aligned["split"] == "test")]))
            for strategy in sorted(aligned["strategy"].unique())
        },
        "strategies": strategy_reports,
        "ensemble_value_judgement": judge_ensemble_value(strategy_reports),
        "notes": [
            "Aligned comparison uses GRU sequence predictions at the final window original_index.",
            "Tail-label metrics compare all models against the final window label, matching XGBoost row-level output.",
            "Sequence-label metrics are not used for XGBoost operating judgement because XGBoost is not a sequence model.",
        ],
    }
    return report


def summarize_strategy(test: pd.DataFrame) -> dict[str, Any]:
    target = test["tail_label"].astype(int).to_numpy()
    metrics = {
        "xgb_v1": metrics_for(target, test["xgb_v1_pred_selected"]),
        "xgb_v2": metrics_for(target, test["xgb_v2_pred_selected"]),
        "gru": metrics_for(target, test["gru_pred_selected"]),
        "or_xgb_v1_gru": metrics_for(target, test["or_v1_gru_tail_pred"]),
        "or_xgb_v2_gru": metrics_for(target, test["or_v2_gru_tail_pred"]),
        "weighted_xgb_v2_gru_0_50": metrics_for(target, test["weighted_v2_gru_pred_0_50"]),
    }
    xgb_v1_fn = xgb_fn_analysis(test, "xgb_v1")
    xgb_v2_fn = xgb_fn_analysis(test, "xgb_v2")
    low_slow = test[test["scenario_id"].astype(str) == "low-and-slow"]
    return {
        "aligned_test_rows": int(len(test)),
        "tail_label_counts": counts(test["tail_label"]),
        "scenario_counts": counts(test["scenario_id"]),
        "metrics": metrics,
        "xgb_v1_false_negative_analysis": xgb_v1_fn,
        "xgb_v2_false_negative_analysis": xgb_v2_fn,
        "low_and_slow_subset": {
            "rows": int(len(low_slow)),
            "tail_label_counts": counts(low_slow["tail_label"]) if not low_slow.empty else {},
            "metrics": {
                "xgb_v1": metrics_for(low_slow["tail_label"], low_slow["xgb_v1_pred_selected"]) if not low_slow.empty else {},
                "xgb_v2": metrics_for(low_slow["tail_label"], low_slow["xgb_v2_pred_selected"]) if not low_slow.empty else {},
                "gru": metrics_for(low_slow["tail_label"], low_slow["gru_pred_selected"]) if not low_slow.empty else {},
                "or_xgb_v2_gru": metrics_for(low_slow["tail_label"], low_slow["or_v2_gru_tail_pred"]) if not low_slow.empty else {},
            },
        },
    }


def xgb_fn_analysis(test: pd.DataFrame, prefix: str) -> dict[str, Any]:
    pred_col = f"{prefix}_pred_selected"
    fn = test[(test["tail_label"] == 1) & (test[pred_col] == 0)].copy()
    if fn.empty:
        return {
            "false_negatives": 0,
            "caught_by_gru": 0,
            "caught_by_gru_default": 0,
            "by_scenario": {},
        }
    return {
        "false_negatives": int(len(fn)),
        "caught_by_gru": int((fn["gru_pred_selected"] == 1).sum()),
        "caught_by_gru_default": int((fn["gru_pred_default"] == 1).sum()),
        "caught_by_or_ensemble": int((((fn[pred_col] == 1) | (fn["gru_pred_selected"] == 1))).sum()),
        "by_scenario": counts(fn["scenario_id"]),
        "caught_by_gru_by_scenario": {
            str(key): int(value)
            for key, value in fn[fn["gru_pred_selected"] == 1]["scenario_id"].value_counts().items()
        },
        "probability_summary": {
            "xgb_mean": float(fn[f"{prefix}_prob"].mean()),
            "gru_mean": float(fn["gru_prob"].mean()),
            "gru_min": float(fn["gru_prob"].min()),
            "gru_max": float(fn["gru_prob"].max()),
        },
    }


def metrics_for(y_true: Any, y_pred: Any) -> dict[str, Any]:
    y_true_arr = np.asarray(y_true, dtype=int)
    y_pred_arr = np.asarray(y_pred, dtype=int)
    if len(y_true_arr) == 0:
        return {}
    matrix = confusion_matrix(y_true_arr, y_pred_arr, labels=[0, 1])
    tn, fp, fn, tp = [int(value) for value in matrix.ravel()]
    return {
        "rows": int(len(y_true_arr)),
        "accuracy": float(accuracy_score(y_true_arr, y_pred_arr)),
        "precision": float(precision_score(y_true_arr, y_pred_arr, zero_division=0)),
        "recall": float(recall_score(y_true_arr, y_pred_arr, zero_division=0)),
        "f1": float(f1_score(y_true_arr, y_pred_arr, zero_division=0)),
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "tp": tp,
    }


def judge_ensemble_value(strategy_reports: dict[str, Any]) -> dict[str, Any]:
    judgement: dict[str, Any] = {}
    for strategy, report in strategy_reports.items():
        xgb_v2 = report["metrics"]["xgb_v2"]
        or_v2 = report["metrics"]["or_xgb_v2_gru"]
        fn_analysis = report["xgb_v2_false_negative_analysis"]
        f1_delta = or_v2.get("f1", 0.0) - xgb_v2.get("f1", 0.0)
        recall_delta = or_v2.get("recall", 0.0) - xgb_v2.get("recall", 0.0)
        fp_delta = or_v2.get("fp", 0) - xgb_v2.get("fp", 0)
        judgement[strategy] = {
            "valuable": bool(fn_analysis.get("caught_by_gru", 0) > 0 or recall_delta > 0),
            "xgb_v2_f1": xgb_v2.get("f1"),
            "or_ensemble_f1": or_v2.get("f1"),
            "f1_delta": f1_delta,
            "recall_delta": recall_delta,
            "false_positive_delta": int(fp_delta),
            "xgb_v2_false_negatives": fn_analysis.get("false_negatives", 0),
            "xgb_v2_fns_caught_by_gru": fn_analysis.get("caught_by_gru", 0),
            "interpretation": interpret(strategy, f1_delta, recall_delta, fp_delta, fn_analysis),
        }
    return judgement


def interpret(strategy: str, f1_delta: float, recall_delta: float, fp_delta: int, fn_analysis: dict[str, Any]) -> str:
    caught = fn_analysis.get("caught_by_gru", 0)
    total = fn_analysis.get("false_negatives", 0)
    if caught > 0 and fp_delta <= 5:
        return f"GRU catches {caught}/{total} XGBoost v2 false negatives with limited FP increase; ensemble is useful for {strategy}."
    if caught > 0:
        return f"GRU catches {caught}/{total} XGBoost v2 false negatives but adds {fp_delta} false positives; use with policy constraints."
    if f1_delta >= 0 and recall_delta >= 0:
        return f"Ensemble does not hurt aggregate metrics, but GRU does not cover XGBoost v2 misses in {strategy}."
    return f"Ensemble is not justified for {strategy} without additional tuning."


def counts(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in series.value_counts().items()}


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# GRU vs XGBoost Cross Analysis",
        "",
        f"- Aligned rows: `{report['aligned_rows']}`",
        f"- Test rows by strategy: `{report['test_rows_by_strategy']}`",
        "",
        "## Tail-Window Metrics",
        "| Strategy | Model/Policy | Precision | Recall | F1 | FN | FP |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for strategy, strategy_report in report["strategies"].items():
        for model_name in ["xgb_v1", "xgb_v2", "gru", "or_xgb_v2_gru", "weighted_xgb_v2_gru_0_50"]:
            item = strategy_report["metrics"][model_name]
            lines.append(
                "| {strategy} | {model} | {precision:.4f} | {recall:.4f} | {f1:.4f} | {fn} | {fp} |".format(
                    strategy=strategy,
                    model=model_name,
                    precision=item["precision"],
                    recall=item["recall"],
                    f1=item["f1"],
                    fn=item["fn"],
                    fp=item["fp"],
                )
            )
    lines.extend(["", "## XGBoost v2 False Negatives Caught By GRU"])
    for strategy, strategy_report in report["strategies"].items():
        fn = strategy_report["xgb_v2_false_negative_analysis"]
        lines.append(
            f"- {strategy}: GRU caught `{fn.get('caught_by_gru', 0)}` / `{fn.get('false_negatives', 0)}` "
            f"XGBoost v2 FNs; by scenario `{fn.get('by_scenario', {})}`"
        )
    lines.extend(["", "## Ensemble Value Judgement"])
    for strategy, item in report["ensemble_value_judgement"].items():
        lines.append(f"- {strategy}: {item['interpretation']}")
    lines.extend(["", "## Notes"])
    for note in report["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
