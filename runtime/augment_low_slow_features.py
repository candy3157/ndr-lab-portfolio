from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROLLING_WINDOWS = [6, 12, 30, 60]
BASE_FEATURES = [
    "flow_count",
    "unique_dst_count",
    "unique_dst_port_count",
    "failed_conn_ratio",
    "avg_duration",
    "duration_std",
    "avg_src_bytes",
    "avg_dst_bytes",
    "avg_total_bytes",
    "packet_count_mean",
    "bytes_per_second",
    "packets_per_second",
    "src_to_dst_bytes_ratio",
    "tcp_flow_ratio",
    "udp_flow_ratio",
    "icmp_flow_ratio",
    "dst_port_well_known_ratio",
    "dst_port_registered_ratio",
    "dst_port_ephemeral_ratio",
    "dst_port_entropy",
    "service_entropy",
    "conn_state_entropy",
]
METADATA_COLUMNS = [
    "dataset_name",
    "data_source",
    "is_synthetic",
    "label",
    "attack_type",
    "timestamp",
    "window_start",
    "window_end",
    "sequence_index",
    "session_id",
    "scenario_id",
    "run_id",
    "technique_id",
    "phase",
    "src_entity",
    "_source_file",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add low-and-slow rolling behavior features to common NDR feature rows.",
    )
    parser.add_argument("--input", type=Path, default=Path("data/processed/simulation_real_only_24h_common.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/simulation_real_only_24h_low_slow_features.csv"))
    parser.add_argument("--schema-output", type=Path, default=Path("configs/feature_schema_low_slow_v2.json"))
    parser.add_argument("--feature-list-output", type=Path, default=Path("models/xgboost_feature_list_low_slow_v2.json"))
    parser.add_argument("--report-json", type=Path, default=Path("reports/low_slow_feature_augmentation_report.json"))
    parser.add_argument("--report-md", type=Path, default=Path("reports/low_slow_feature_augmentation_report.md"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.input)
    if df.empty:
        raise SystemExit("input data is empty")
    augmented, new_features = augment(df)
    feature_list = [feature for feature in BASE_FEATURES if feature in augmented.columns] + new_features
    for feature in feature_list:
        augmented[feature] = pd.to_numeric(augmented[feature], errors="coerce")
    augmented[feature_list] = augmented[feature_list].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.schema_output.parent.mkdir(parents=True, exist_ok=True)
    args.feature_list_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    augmented.to_csv(args.output, index=False)
    args.feature_list_output.write_text(json.dumps(feature_list, indent=2), encoding="utf-8")

    schema = build_schema(feature_list, new_features)
    args.schema_output.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")
    report = build_report(args, augmented, feature_list, new_features)
    args.report_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    args.report_md.write_text(render_report(report), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"wrote {args.schema_output}")
    print(f"wrote {args.feature_list_output}")
    print(f"wrote {args.report_json}")
    print(f"wrote {args.report_md}")


def augment(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    out = df.copy()
    out["_window_time"] = pd.to_datetime(out["window_start"], errors="coerce", utc=True)
    out = out.sort_values(["run_id", "src_entity", "_window_time", "sequence_index"], kind="mergesort")
    out["_time_delta_seconds"] = (
        out.groupby(["run_id", "src_entity"], dropna=False)["_window_time"]
        .diff()
        .dt.total_seconds()
        .fillna(0.0)
        .clip(lower=0.0, upper=3600.0)
    )
    out["_failed_flow_estimate"] = numeric(out, "flow_count") * numeric(out, "failed_conn_ratio")
    new_features: list[str] = []

    for window in ROLLING_WINDOWS:
        prefix = f"rolling_{window}"
        add_feature(out, new_features, f"{prefix}_flow_count_sum", rolling_group(out, "flow_count", window, "sum"))
        add_feature(out, new_features, f"{prefix}_flow_count_mean", rolling_group(out, "flow_count", window, "mean"))
        add_feature(out, new_features, f"{prefix}_unique_dst_count_max", rolling_group(out, "unique_dst_count", window, "max"))
        add_feature(out, new_features, f"{prefix}_unique_dst_port_count_max", rolling_group(out, "unique_dst_port_count", window, "max"))
        add_feature(out, new_features, f"{prefix}_unique_dst_count_growth", numeric(out, "unique_dst_count") - rolling_group(out, "unique_dst_count", window, "min"))
        add_feature(out, new_features, f"{prefix}_unique_dst_port_count_growth", numeric(out, "unique_dst_port_count") - rolling_group(out, "unique_dst_port_count", window, "min"))
        add_feature(out, new_features, f"{prefix}_failed_conn_ratio_mean", rolling_group(out, "failed_conn_ratio", window, "mean"))
        add_feature(out, new_features, f"{prefix}_failed_flow_estimate_sum", rolling_group(out, "_failed_flow_estimate", window, "sum"))
        flow_sum = rolling_group(out, "flow_count", window, "sum")
        failed_sum = rolling_group(out, "_failed_flow_estimate", window, "sum")
        add_feature(out, new_features, f"{prefix}_failed_flow_ratio_weighted", failed_sum / (flow_sum + 1.0))
        add_feature(out, new_features, f"{prefix}_avg_duration_mean", rolling_group(out, "avg_duration", window, "mean"))
        add_feature(out, new_features, f"{prefix}_avg_total_bytes_mean", rolling_group(out, "avg_total_bytes", window, "mean"))
        add_feature(out, new_features, f"{prefix}_dst_port_entropy_mean", rolling_group(out, "dst_port_entropy", window, "mean"))
        add_feature(out, new_features, f"{prefix}_inter_window_seconds_mean", rolling_group(out, "_time_delta_seconds", window, "mean"))
        add_feature(out, new_features, f"{prefix}_inter_window_seconds_std", rolling_group(out, "_time_delta_seconds", window, "std"))
        add_feature(out, new_features, f"{prefix}_flow_count_per_dst", flow_sum / (rolling_group(out, "unique_dst_count", window, "max") + 1.0))
        add_feature(out, new_features, f"{prefix}_flow_count_per_dst_port", flow_sum / (rolling_group(out, "unique_dst_port_count", window, "max") + 1.0))
        low_volume = 1.0 / np.log1p(flow_sum.clip(lower=0.0) + 1.0)
        diversity = rolling_group(out, "unique_dst_count", window, "max") + rolling_group(out, "unique_dst_port_count", window, "max")
        add_feature(out, new_features, f"{prefix}_low_slow_scan_score", diversity * (failed_sum / (flow_sum + 1.0)) * low_volume)

    out = out.drop(columns=["_window_time", "_time_delta_seconds", "_failed_flow_estimate"])
    out = out.sort_index(kind="mergesort")
    return out, new_features


def rolling_group(df: pd.DataFrame, column: str, window: int, agg: str) -> pd.Series:
    values = numeric(df, column)
    grouped = values.groupby([df["run_id"].fillna(""), df["src_entity"].fillna("")], sort=False)
    rolled = grouped.rolling(window=window, min_periods=1)
    if agg == "sum":
        result = rolled.sum()
    elif agg == "mean":
        result = rolled.mean()
    elif agg == "max":
        result = rolled.max()
    elif agg == "min":
        result = rolled.min()
    elif agg == "std":
        result = rolled.std(ddof=0)
    else:
        raise ValueError(f"unsupported rolling aggregation: {agg}")
    return result.reset_index(level=[0, 1], drop=True).reindex(df.index).fillna(0.0)


def add_feature(df: pd.DataFrame, feature_names: list[str], name: str, values: pd.Series) -> None:
    df[name] = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    feature_names.append(name)


def numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[column], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)


def build_schema(feature_list: list[str], new_features: list[str]) -> dict[str, Any]:
    return {
        "feature_schema_version": "ndr_common_low_slow_v2",
        "based_on": "ndr_common_v1",
        "metadata_columns": METADATA_COLUMNS,
        "model_input_features": feature_list,
        "low_slow_added_features": new_features,
        "excluded_input_columns": [
            "src_ip",
            "dst_ip",
            "id.orig_h",
            "id.resp_h",
            "source_ip",
            "destination_ip",
            "src_port",
            "dst_port",
            "source_port",
            "destination_port",
            "flow_id",
            "timestamp",
            "window_start",
            "window_end",
            "scenario_id",
            "run_id",
            "technique_id",
            "phase",
            "label",
            "attack_type",
            "dataset_name",
            "data_source",
            "is_synthetic",
            "session_id",
            "src_entity",
            "_source_file",
        ],
        "rules": [
            "Rolling features use current and previous windows only within run_id/src_entity groups.",
            "Raw IP addresses and raw ports are not model input features.",
            "Features target low-and-slow temporal behavior: repeated sparse connections, long-window failed ratios, and slow destination/port diversity growth.",
        ],
    }


def build_report(
    args: argparse.Namespace,
    df: pd.DataFrame,
    feature_list: list[str],
    new_features: list[str],
) -> dict[str, Any]:
    low_slow = df[df.get("scenario_id", "") == "low-and-slow"]
    return {
        "input": str(args.input),
        "output": str(args.output),
        "schema_output": str(args.schema_output),
        "feature_list_output": str(args.feature_list_output),
        "rows": int(len(df)),
        "feature_count": len(feature_list),
        "base_feature_count": len([feature for feature in BASE_FEATURES if feature in df.columns]),
        "added_feature_count": len(new_features),
        "rolling_windows": ROLLING_WINDOWS,
        "label_counts": df["label"].value_counts().to_dict() if "label" in df else {},
        "scenario_counts": df["scenario_id"].value_counts().to_dict() if "scenario_id" in df else {},
        "low_and_slow_rows": int(len(low_slow)),
        "low_and_slow_feature_summary": summarize_features(low_slow, new_features[: min(12, len(new_features))]),
        "notes": [
            "This is a feature augmentation step only; operating value must be proven by blocked validation.",
            "Rolling features are behavior aggregates and do not include raw source or destination IP addresses.",
        ],
    }


def summarize_features(df: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if df.empty:
        return summary
    for feature in features:
        values = pd.to_numeric(df[feature], errors="coerce")
        summary[feature] = {
            "mean": float(values.mean()),
            "p50": float(values.quantile(0.5)),
            "p95": float(values.quantile(0.95)),
            "max": float(values.max()),
        }
    return summary


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "# Low-And-Slow Feature Augmentation Report",
        "",
        f"- Input: `{report['input']}`",
        f"- Output: `{report['output']}`",
        f"- Schema: `{report['schema_output']}`",
        f"- Rows: `{report['rows']}`",
        f"- Feature count: `{report['feature_count']}`",
        f"- Added features: `{report['added_feature_count']}`",
        f"- Rolling windows: `{report['rolling_windows']}`",
        f"- Label counts: `{report['label_counts']}`",
        f"- Low-and-slow rows: `{report['low_and_slow_rows']}`",
        "",
        "## Notes",
    ]
    for note in report["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
