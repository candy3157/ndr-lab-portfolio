from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from profile_public_datasets import FEATURE_COLUMNS, METADATA_COLUMNS


FAILED_STATES = {"S0", "REJ", "RSTO", "RSTR", "RSTOS0", "RSTRH"}
EXTRA_METADATA_COLUMNS = [
    "src_ip",
    "target_network",
    "primary_dst_ip",
    "top_dst_ips",
    "top_dst_ports",
    "window_seconds",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Zeek conn.log rows into ndr_common_v1 window features.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Zeek conn.log in JSONL or ASCII TSV format.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-name", default="UQ-IoT-IDS2021")
    parser.add_argument("--label", choices=["normal", "attack"], required=True)
    parser.add_argument("--attack-type", default="unknown")
    parser.add_argument("--scenario-id", default="public-uq-iot")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--window-seconds", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = read_zeek_conn(args.input)
    if df.empty:
        raise SystemExit("input Zeek conn.log is empty")
    output = convert_conn_windows(df, args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(f"wrote {args.output}")


def read_zeek_conn(path: Path) -> pd.DataFrame:
    first = first_data_line(path)
    if first.startswith("{"):
        return pd.read_json(path, lines=True)
    if first.startswith("#") or "\t" in first:
        return read_zeek_ascii(path)
    return pd.read_csv(path)


def first_data_line(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                return stripped
    return ""


def read_zeek_ascii(path: Path) -> pd.DataFrame:
    fields: list[str] | None = None
    data_lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            if line.startswith("#fields"):
                fields = line.strip().split("\t")[1:]
                continue
            if line.startswith("#"):
                continue
            if line.strip():
                data_lines.append(line)
    if fields is None:
        return pd.read_csv(path, sep="\t", comment="#")
    rows = [line.rstrip("\n").split("\t") for line in data_lines]
    return pd.DataFrame(rows, columns=fields)


def convert_conn_windows(df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    df = df.rename(columns={column: str(column).strip() for column in df.columns})
    ts = numeric(df, ["ts", "timestamp"])
    if ts.isna().all():
        ts = pd.Series(np.arange(len(df)), index=df.index, dtype=float)
    window_start_epoch = (np.floor(ts / args.window_seconds) * args.window_seconds).astype("int64")
    df["_window_epoch"] = window_start_epoch
    df["_duration"] = numeric(df, ["duration"]).fillna(0.0)
    df["_orig_bytes"] = numeric(df, ["orig_bytes", "orig_ip_bytes"]).fillna(0.0)
    df["_resp_bytes"] = numeric(df, ["resp_bytes", "resp_ip_bytes"]).fillna(0.0)
    df["_orig_pkts"] = numeric(df, ["orig_pkts"]).fillna(0.0)
    df["_resp_pkts"] = numeric(df, ["resp_pkts"]).fillna(0.0)
    df["_dst_port"] = numeric(df, ["id.resp_p", "dst_port", "destination_port"]).fillna(-1)
    df["_src_host"] = text(df, ["id.orig_h", "src_ip", "source_ip"], "")
    df["_dst_host"] = text(df, ["id.resp_h", "dst_ip", "destination_ip"], "")
    df["_proto"] = text(df, ["proto", "protocol"], "")
    df["_service"] = text(df, ["service"], "")
    df["_conn_state"] = text(df, ["conn_state"], "")

    rows: list[dict[str, Any]] = []
    group_columns = ["_window_epoch", "_src_host"]
    for sequence_index, ((window_epoch, src_host), group) in enumerate(df.groupby(group_columns, dropna=False, sort=True)):
        src_ip = str(src_host or "").strip()
        src_entity = src_ip or args.input.stem
        duration = group["_duration"]
        orig_bytes = group["_orig_bytes"]
        resp_bytes = group["_resp_bytes"]
        total_bytes = orig_bytes + resp_bytes
        packet_count = group["_orig_pkts"] + group["_resp_pkts"]
        dst_port = group["_dst_port"]
        window_start = pd.to_datetime(window_epoch, unit="s", utc=True)
        window_end = window_start + pd.Timedelta(seconds=args.window_seconds)
        row = {
            "dataset_name": args.dataset_name,
            "data_source": "real",
            "is_synthetic": False,
            "label": args.label,
            "attack_type": "Benign" if args.label == "normal" else args.attack_type,
            "timestamp": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_start": window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sequence_index": sequence_index,
            "session_id": f"{args.dataset_name}:{args.run_id or args.input.stem}:{src_entity}",
            "scenario_id": args.scenario_id,
            "run_id": args.run_id or args.input.stem,
            "technique_id": "",
            "phase": "",
            "src_entity": src_entity,
            "_source_file": str(args.input),
            "src_ip": src_ip,
            "target_network": "",
            "primary_dst_ip": primary_value(group["_dst_host"]),
            "top_dst_ips": top_values(group["_dst_host"]),
            "top_dst_ports": top_ports(dst_port),
            "window_seconds": args.window_seconds,
            "flow_count": float(len(group)),
            "unique_dst_count": float(group["_dst_host"].replace("", np.nan).nunique(dropna=True)),
            "unique_dst_port_count": float(dst_port[dst_port >= 0].nunique(dropna=True)),
            "failed_conn_ratio": float(group["_conn_state"].isin(FAILED_STATES).mean()),
            "avg_duration": float(duration.mean()),
            "duration_std": float(duration.std(ddof=0)),
            "avg_src_bytes": float(orig_bytes.mean()),
            "avg_dst_bytes": float(resp_bytes.mean()),
            "avg_total_bytes": float(total_bytes.mean()),
            "packet_count_mean": float(packet_count.mean()),
            "bytes_per_second": safe_rate(total_bytes.sum(), duration.sum()),
            "packets_per_second": safe_rate(packet_count.sum(), duration.sum()),
            "src_to_dst_bytes_ratio": float(orig_bytes.sum() / (resp_bytes.sum() + 1.0)),
            "tcp_flow_ratio": ratio(group["_proto"], "tcp"),
            "udp_flow_ratio": ratio(group["_proto"], "udp"),
            "icmp_flow_ratio": ratio(group["_proto"], "icmp"),
            "dst_port_well_known_ratio": float(((dst_port >= 0) & (dst_port <= 1023)).mean()),
            "dst_port_registered_ratio": float(((dst_port >= 1024) & (dst_port <= 49151)).mean()),
            "dst_port_ephemeral_ratio": float((dst_port >= 49152).mean()),
            "dst_port_entropy": entropy(dst_port[dst_port >= 0].astype(str)),
            "service_entropy": entropy(group["_service"]),
            "conn_state_entropy": entropy(group["_conn_state"]),
        }
        rows.append(row)
    out = pd.DataFrame(rows)
    for column in METADATA_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    for column in EXTRA_METADATA_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    for column in FEATURE_COLUMNS:
        if column not in out.columns:
            out[column] = 0.0
    return out[METADATA_COLUMNS + EXTRA_METADATA_COLUMNS + FEATURE_COLUMNS]


def numeric(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    column = first_present(df, candidates)
    if column is None:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column].replace("-", np.nan), errors="coerce")


def text(df: pd.DataFrame, candidates: list[str], default: str) -> pd.Series:
    column = first_present(df, candidates)
    if column is None:
        return pd.Series([default] * len(df), index=df.index)
    return df[column].replace("-", default).fillna(default).astype(str).str.lower()


def first_present(df: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {column.lower(): column for column in df.columns}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return None


def ratio(series: pd.Series, value: str) -> float:
    if len(series) == 0:
        return 0.0
    return float((series.fillna("").astype(str).str.lower() == value).mean())


def safe_rate(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator / denominator)


def entropy(series: pd.Series) -> float:
    values = series.fillna("").astype(str)
    counts = values.value_counts()
    total = counts.sum()
    if total == 0:
        return 0.0
    probabilities = counts / total
    return float(-(probabilities * np.log2(probabilities)).sum())


def top_ports(series: pd.Series) -> str:
    ports = pd.to_numeric(series, errors="coerce")
    ports = ports[(ports >= 0) & ports.notna()].astype(int)
    if ports.empty:
        return "[]"
    return json.dumps(ports.value_counts().head(20).index.tolist(), separators=(",", ":"))


def top_values(series: pd.Series) -> str:
    values = series.fillna("").astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return "[]"
    return json.dumps(values.value_counts().head(20).index.tolist(), separators=(",", ":"))


def primary_value(series: pd.Series) -> str:
    values = series.fillna("").astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return ""
    return str(values.value_counts().index[0])


if __name__ == "__main__":
    main()
