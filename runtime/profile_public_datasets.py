from __future__ import annotations

import argparse
import json
import math
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


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

FEATURE_COLUMNS = [
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

EXCLUDED_INPUT_COLUMNS = [
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
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile public NDR datasets and build a smoke common feature dataset.",
    )
    parser.add_argument("--datasets-root", type=Path, default=Path("../datasets"))
    parser.add_argument(
        "--simulation-input",
        type=Path,
        default=Path(
            "../ipcam-backdoor-test-environment/data/features/datasets/"
            "seq10s-24h-scan-subtype-10s.csv"
        ),
    )
    parser.add_argument("--max-cse-rows", type=int, default=12000)
    parser.add_argument("--max-simulation-rows", type=int, default=12000)
    parser.add_argument("--chunk-size", type=int, default=5000)
    parser.add_argument("--output-json", type=Path, default=Path("reports/dataset_profile.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/dataset_profile.md"))
    parser.add_argument("--feature-schema", type=Path, default=Path("configs/feature_schema.json"))
    parser.add_argument("--dataset-mapping", type=Path, default=Path("configs/dataset_mapping.json"))
    parser.add_argument(
        "--processed-output",
        type=Path,
        default=Path("data/processed/common_ndr_features_smoke.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.feature_schema.parent.mkdir(parents=True, exist_ok=True)
    args.dataset_mapping.parent.mkdir(parents=True, exist_ok=True)
    args.processed_output.parent.mkdir(parents=True, exist_ok=True)

    cse_zip = args.datasets_root / "cse-cic-ids2018" / "archive.zip"
    uq_zip = (
        args.datasets_root
        / "UQ-iot-ids-dataset-2021"
        / "69897e94e24170c0_UQIOT2022_A7369.zip"
    )

    profile: dict[str, Any] = {
        "profile_mode": "chunked_sample_smoke",
        "notes": [
            "Large CSV files are profiled through bounded chunks by default.",
            "UQ-IoT-IDS2021 is stored as PCAP files here, so row-level feature extraction is documented as a Zeek/tshark follow-up step.",
            "Raw IP and raw port identifiers are excluded from model input features.",
        ],
        "datasets": {},
    }
    processed_frames: list[pd.DataFrame] = []

    if cse_zip.exists():
        cse_profile, cse_rows = profile_cse_zip(cse_zip, args.max_cse_rows, args.chunk_size)
        profile["datasets"]["CSE-CIC-IDS2018"] = cse_profile
        if not cse_rows.empty:
            processed_frames.append(transform_cse(cse_rows))
    else:
        profile["datasets"]["CSE-CIC-IDS2018"] = {"status": "missing", "path": str(cse_zip)}

    if uq_zip.exists():
        profile["datasets"]["UQ-IoT-IDS2021"] = profile_uq_zip(uq_zip)
    else:
        profile["datasets"]["UQ-IoT-IDS2021"] = {"status": "missing", "path": str(uq_zip)}

    if args.simulation_input.exists():
        sim_rows = pd.read_csv(args.simulation_input, nrows=args.max_simulation_rows)
        profile["datasets"]["simulation"] = profile_frame(
            sim_rows,
            dataset_name="simulation",
            path=args.simulation_input,
            full_row_count=None,
            rows_profiled=len(sim_rows),
            unit="window",
        )
        processed_frames.append(transform_simulation(sim_rows, args.simulation_input))
    else:
        profile["datasets"]["simulation"] = {
            "status": "missing",
            "path": str(args.simulation_input),
        }

    if processed_frames:
        processed = pd.concat(processed_frames, ignore_index=True, sort=False)
        processed = normalize_common_frame(processed)
        processed.to_csv(args.processed_output, index=False)
        profile["processed_output"] = {
            "path": str(args.processed_output),
            "rows": int(len(processed)),
            "label_counts": counts(processed["label"]),
            "dataset_counts": counts(processed["dataset_name"]),
            "feature_columns": FEATURE_COLUMNS,
            "excluded_input_columns": EXCLUDED_INPUT_COLUMNS,
        }
    else:
        profile["processed_output"] = {"path": str(args.processed_output), "rows": 0}

    feature_schema = build_feature_schema()
    dataset_mapping = build_dataset_mapping()
    write_json(args.feature_schema, feature_schema)
    write_json(args.dataset_mapping, dataset_mapping)
    write_json(args.output_json, profile)
    args.output_md.write_text(render_profile_md(profile), encoding="utf-8")

    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print(f"wrote {args.feature_schema}")
    print(f"wrote {args.dataset_mapping}")
    print(f"wrote {args.processed_output}")


def profile_cse_zip(path: Path, max_rows: int, chunk_size: int) -> tuple[dict[str, Any], pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    files: list[dict[str, Any]] = []
    remaining = max_rows

    with zipfile.ZipFile(path) as archive:
        csv_infos = [info for info in archive.infolist() if info.filename.lower().endswith(".csv")]
        for info in csv_infos:
            file_profile: dict[str, Any] = {
                "name": info.filename,
                "compressed_size": info.compress_size,
                "uncompressed_size": info.file_size,
            }
            if remaining > 0:
                sampled_parts: list[pd.DataFrame] = []
                with archive.open(info) as handle:
                    reader = pd.read_csv(handle, chunksize=chunk_size, low_memory=False)
                    for chunk in reader:
                        chunk = normalize_columns(chunk)
                        take = min(len(chunk), remaining)
                        sampled_parts.append(chunk.head(take).assign(_source_file=info.filename))
                        remaining -= take
                        if remaining <= 0:
                            break
                sampled = pd.concat(sampled_parts, ignore_index=True) if sampled_parts else pd.DataFrame()
                file_profile.update(
                    profile_frame(
                        sampled,
                        dataset_name="CSE-CIC-IDS2018",
                        path=Path(info.filename),
                        full_row_count=None,
                        rows_profiled=len(sampled),
                        unit="flow",
                    )
                )
                if not sampled.empty:
                    rows.append(sampled)
            files.append(file_profile)

    combined = pd.concat(rows, ignore_index=True, sort=False) if rows else pd.DataFrame()
    profile = profile_frame(
        combined,
        dataset_name="CSE-CIC-IDS2018",
        path=path,
        full_row_count=None,
        rows_profiled=len(combined),
        unit="flow",
    )
    profile.update(
        {
            "status": "profiled_sample",
            "path": str(path),
            "file_count": len(files),
            "files": files,
            "zip_compressed_size": path.stat().st_size,
            "zip_uncompressed_size": sum(item.get("uncompressed_size", 0) for item in files),
            "full_row_count": None,
            "full_row_count_command": (
                "python profile_public_datasets.py --max-cse-rows 0 "
                "# then run a dedicated chunk counter if exact full row counts are required"
            ),
        }
    )
    return profile, combined


def profile_uq_zip(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        pcap_infos = [
            info
            for info in archive.infolist()
            if info.filename.lower().endswith((".pcap", ".pcapng"))
        ]

    label_counts: Counter[str] = Counter()
    attack_counts: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    for info in pcap_infos:
        lowered = info.filename.lower()
        label = "normal" if "benign" in lowered else "attack"
        attack_type = "Benign" if label == "normal" else infer_uq_attack_type(info.filename)
        label_counts[label] += 1
        attack_counts[attack_type] += 1
        if len(samples) < 30:
            samples.append(
                {
                    "name": info.filename,
                    "label": label,
                    "attack_type": attack_type,
                    "uncompressed_size": info.file_size,
                }
            )

    return {
        "status": "profiled_manifest",
        "path": str(path),
        "file_format": "pcap_zip",
        "unit": "pcap",
        "pcap_file_count": len(pcap_infos),
        "zip_compressed_size": path.stat().st_size,
        "pcap_uncompressed_size": sum(info.file_size for info in pcap_infos),
        "label_counts_by_file": dict(label_counts),
        "attack_type_counts_by_file": dict(attack_counts),
        "sample_files": samples,
        "time_column": None,
        "requires_feature_extraction": True,
        "recommended_extraction": "Run Zeek/tshark on PCAPs, then map conn.log windows into configs/feature_schema.json.",
    }


def transform_cse(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df.copy())
    label_col = first_column(df, ["label"])
    timestamp_col = first_column(df, ["timestamp"])
    dst_port = numeric_col(df, ["dst port", "destination port", "dst_port"])
    protocol = numeric_col(df, ["protocol"])
    duration_seconds = numeric_col(df, ["flow duration", "flow_duration"]) / 1_000_000.0
    fwd_pkts = numeric_col(df, ["tot fwd pkts", "total fwd packets", "total_fwd_packets"])
    bwd_pkts = numeric_col(df, ["tot bwd pkts", "total backward packets", "total_bwd_packets"])
    fwd_bytes = numeric_col(df, ["totlen fwd pkts", "total length of fwd packets", "total_fwd_bytes"])
    bwd_bytes = numeric_col(df, ["totlen bwd pkts", "total length of bwd packets", "total_bwd_bytes"])
    flow_bytes_s = numeric_col(df, ["flow byts/s", "flow bytes/s", "flow_byts_s"])
    flow_pkts_s = numeric_col(df, ["flow pkts/s", "flow packets/s", "flow_pkts_s"])
    rst_count = numeric_col(df, ["rst flag cnt", "rst_flag_count"])
    syn_count = numeric_col(df, ["syn flag cnt", "syn_flag_count"])
    ack_count = numeric_col(df, ["ack flag cnt", "ack_flag_count"])

    raw_label = df[label_col].astype(str).str.strip() if label_col else pd.Series(["unknown"] * len(df))
    binary_label = raw_label.map(lambda value: "normal" if value.lower() == "benign" else "attack")
    timestamp = parse_timestamp(df[timestamp_col]) if timestamp_col else pd.Series([pd.NaT] * len(df))
    total_bytes = fwd_bytes + bwd_bytes
    total_packets = fwd_pkts + bwd_pkts
    safe_duration = duration_seconds.replace(0, np.nan)

    out = pd.DataFrame(
        {
            "dataset_name": "CSE-CIC-IDS2018",
            "data_source": "real",
            "is_synthetic": False,
            "label": binary_label,
            "attack_type": raw_label.where(raw_label.str.len() > 0, "unknown"),
            "timestamp": timestamp.astype("string"),
            "window_start": timestamp.astype("string"),
            "window_end": "",
            "sequence_index": np.arange(len(df), dtype=np.int64),
            "session_id": "CSE-CIC-IDS2018:" + df.get("_source_file", pd.Series(["sample"] * len(df))).astype(str),
            "scenario_id": "public-cse-cic-ids2018",
            "run_id": df.get("_source_file", pd.Series(["sample"] * len(df))).astype(str),
            "technique_id": "",
            "phase": "",
            "src_entity": df.get("_source_file", pd.Series(["cse"] * len(df))).astype(str),
            "_source_file": df.get("_source_file", pd.Series([""] * len(df))).astype(str),
            "flow_count": 1.0,
            "unique_dst_count": 1.0,
            "unique_dst_port_count": 1.0,
            "failed_conn_ratio": ((rst_count > 0) | ((syn_count > 0) & (ack_count == 0))).astype(float),
            "avg_duration": duration_seconds,
            "duration_std": 0.0,
            "avg_src_bytes": fwd_bytes,
            "avg_dst_bytes": bwd_bytes,
            "avg_total_bytes": total_bytes,
            "packet_count_mean": total_packets,
            "bytes_per_second": flow_bytes_s.fillna(total_bytes / safe_duration),
            "packets_per_second": flow_pkts_s.fillna(total_packets / safe_duration),
            "src_to_dst_bytes_ratio": fwd_bytes / (bwd_bytes + 1.0),
            "tcp_flow_ratio": (protocol == 6).astype(float),
            "udp_flow_ratio": (protocol == 17).astype(float),
            "icmp_flow_ratio": (protocol == 1).astype(float),
            "dst_port_well_known_ratio": ((dst_port >= 0) & (dst_port <= 1023)).astype(float),
            "dst_port_registered_ratio": ((dst_port >= 1024) & (dst_port <= 49151)).astype(float),
            "dst_port_ephemeral_ratio": (dst_port >= 49152).astype(float),
            "dst_port_entropy": 0.0,
            "service_entropy": 0.0,
            "conn_state_entropy": 0.0,
        }
    )
    return out


def transform_simulation(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    df = normalize_columns(df.copy())
    label_col = first_column(df, ["label", "type", "target", "scan_subtype"])
    raw_label = df[label_col].astype(str).str.strip() if label_col else pd.Series(["unknown"] * len(df))
    binary_label = raw_label.map(normalize_label)
    attack_type_col = first_column(df, ["attack_type", "scan_subtype", "type"])
    attack_type = df[attack_type_col].astype(str) if attack_type_col else raw_label
    timestamp_col = first_column(df, ["timestamp", "window_start", "ts"])
    timestamp = parse_timestamp(df[timestamp_col]) if timestamp_col else pd.Series([pd.NaT] * len(df))
    scenario = text_col(df, ["scenario_id"], "simulation")
    run = text_col(df, ["run_id"], path.stem)
    session = (scenario + ":" + run).astype(str)

    out = pd.DataFrame(
        {
            "dataset_name": "simulation",
            "data_source": text_col(df, ["data_source"], "real"),
            "is_synthetic": bool_col(df, ["is_synthetic"], False),
            "label": binary_label,
            "attack_type": attack_type.where(binary_label == "attack", "Benign"),
            "timestamp": timestamp.astype("string"),
            "window_start": text_col(df, ["window_start", "timestamp", "ts"], ""),
            "window_end": text_col(df, ["window_end"], ""),
            "sequence_index": np.arange(len(df), dtype=np.int64),
            "session_id": session,
            "scenario_id": scenario,
            "run_id": run,
            "technique_id": text_col(df, ["technique_id", "technique_ids"], ""),
            "phase": text_col(df, ["phase", "phases"], ""),
            "src_entity": text_col(df, ["src_entity"], "simulation-window"),
            "_source_file": str(path),
        }
    )
    for feature in FEATURE_COLUMNS:
        out[feature] = simulation_feature(df, feature)
    return out


def simulation_feature(df: pd.DataFrame, feature: str) -> pd.Series:
    aliases = {
        "unique_dst_count": ["unique_dst_count", "unique_dst_host_count", "unique_dst_hosts"],
        "avg_src_bytes": ["avg_src_bytes", "orig_bytes_mean"],
        "avg_dst_bytes": ["avg_dst_bytes", "resp_bytes_mean"],
        "avg_total_bytes": ["avg_total_bytes", "total_bytes_mean"],
        "packet_count_mean": ["packet_count_mean", "avg_pkts", "avg_packets"],
        "bytes_per_second": ["bytes_per_second", "byte_rate_mean"],
        "packets_per_second": ["packets_per_second", "packet_rate_mean"],
        "src_to_dst_bytes_ratio": ["src_to_dst_bytes_ratio", "bytes_out_in_ratio"],
        "icmp_flow_ratio": ["icmp_flow_ratio"],
    }
    candidates = [feature] + aliases.get(feature, [])
    col = first_column(df, candidates)
    if col:
        return pd.to_numeric(df[col], errors="coerce")
    if feature == "packet_count_mean":
        return pd.Series(0.0, index=df.index)
    if feature == "icmp_flow_ratio":
        return pd.Series(0.0, index=df.index)
    return pd.Series(0.0, index=df.index)


def normalize_common_frame(df: pd.DataFrame) -> pd.DataFrame:
    for column in METADATA_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    for column in FEATURE_COLUMNS:
        if column not in df.columns:
            df[column] = 0.0
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df["label"] = df["label"].map(normalize_label)
    df["data_source"] = df["data_source"].replace("", "real").fillna("real")
    df["is_synthetic"] = df["is_synthetic"].map(lambda value: str(value).lower() in {"true", "1", "yes"})
    return df[METADATA_COLUMNS + FEATURE_COLUMNS]


def profile_frame(
    df: pd.DataFrame,
    dataset_name: str,
    path: Path,
    full_row_count: int | None,
    rows_profiled: int,
    unit: str,
) -> dict[str, Any]:
    if df.empty:
        return {
            "dataset_name": dataset_name,
            "path": str(path),
            "unit": unit,
            "rows_profiled": 0,
            "full_row_count": full_row_count,
            "columns": [],
        }
    label_col = first_column(df, ["label", "type", "target", "scan_subtype"])
    time_cols = [col for col in df.columns if norm_key(col) in {"timestamp", "ts", "windowstart", "windowend"}]
    id_cols = [
        col
        for col in df.columns
        if norm_key(col)
        in {
            "srcip",
            "dstip",
            "sourceip",
            "destinationip",
            "idorigh",
            "idresph",
            "srcport",
            "dstport",
            "flowid",
        }
        or "ip" in norm_key(col)
    ]
    numeric = df.select_dtypes(include=[np.number])
    inf_counts = {
        col: int(np.isinf(pd.to_numeric(numeric[col], errors="coerce")).sum()) for col in numeric.columns
    }
    label_counts: dict[str, int] = {}
    attack_type_counts: dict[str, int] = {}
    if label_col:
        labels = df[label_col].astype(str).str.strip()
        binary = labels.map(normalize_label)
        label_counts = counts(binary)
        attack_type_counts = counts(labels)
    return {
        "dataset_name": dataset_name,
        "path": str(path),
        "unit": unit,
        "rows_profiled": int(rows_profiled),
        "full_row_count": full_row_count,
        "columns": list(map(str, df.columns)),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_ratio": {col: float(df[col].isna().mean()) for col in df.columns},
        "inf_counts": inf_counts,
        "label_column": label_col,
        "label_counts": label_counts,
        "attack_type_counts": attack_type_counts,
        "time_columns": time_cols,
        "identifier_columns": id_cols,
        "excluded_input_columns": [col for col in EXCLUDED_INPUT_COLUMNS if col in df.columns],
        "convertible_common_features": FEATURE_COLUMNS,
        "sequence_basis": "timestamp/order within source file or run/session group",
    }


def build_feature_schema() -> dict[str, Any]:
    return {
        "feature_schema_version": "ndr_common_v1",
        "metadata_columns": METADATA_COLUMNS,
        "model_input_features": FEATURE_COLUMNS,
        "excluded_input_columns": EXCLUDED_INPUT_COLUMNS,
        "label": {
            "column": "label",
            "binary_values": ["normal", "attack"],
            "attack_type_column": "attack_type",
        },
        "rules": [
            "Do not use raw src_ip or dst_ip as model input.",
            "Raw ports may be used to derive behavior ratios but are not retained as direct model features.",
            "dataset_name, data_source, and is_synthetic must be preserved for separated evaluation.",
        ],
    }


def build_dataset_mapping() -> dict[str, Any]:
    return {
        "CSE-CIC-IDS2018": {
            "label_column_candidates": ["Label"],
            "time_column_candidates": ["Timestamp"],
            "raw_identifier_columns_excluded": ["Flow ID", "Src IP", "Dst IP", "Src Port", "Dst Port"],
            "feature_mapping": {
                "avg_duration": "Flow Duration / 1_000_000",
                "avg_src_bytes": "TotLen Fwd Pkts",
                "avg_dst_bytes": "TotLen Bwd Pkts",
                "packet_count_mean": "Tot Fwd Pkts + Tot Bwd Pkts",
                "bytes_per_second": "Flow Byts/s",
                "packets_per_second": "Flow Pkts/s",
                "protocol ratios": "Protocol",
                "port range ratios": "Dst Port bucketed into well-known/registered/ephemeral",
            },
        },
        "UQ-IoT-IDS2021": {
            "source_format": "PCAP zip",
            "label_basis": "benign_samples vs attack_samples path",
            "required_preprocessing": "Extract Zeek conn.log or flow CSV from PCAP before schema conversion.",
            "feature_mapping": "Use Zeek/window behavior features matching ndr_common_v1.",
        },
        "simulation": {
            "label_column_candidates": ["label", "type", "target", "scan_subtype"],
            "feature_mapping": "Existing Zeek/window behavior columns are reused directly when names match.",
        },
    }


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {col: str(col).strip() for col in df.columns}
    return df.rename(columns=renamed)


def first_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {norm_key(col): col for col in df.columns}
    for candidate in candidates:
        key = norm_key(candidate)
        if key in normalized:
            return normalized[key]
    return None


def numeric_col(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    col = first_column(df, candidates)
    if col is None:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)


def text_col(df: pd.DataFrame, candidates: list[str], default: str) -> pd.Series:
    col = first_column(df, candidates)
    if col is None:
        return pd.Series([default] * len(df), index=df.index)
    return df[col].fillna(default).astype(str)


def bool_col(df: pd.DataFrame, candidates: list[str], default: bool) -> pd.Series:
    col = first_column(df, candidates)
    if col is None:
        return pd.Series([default] * len(df), index=df.index)
    return df[col].map(lambda value: str(value).lower() in {"true", "1", "yes"})


def parse_timestamp(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    return parsed.dt.strftime("%Y-%m-%dT%H:%M:%SZ").fillna("")


def normalize_label(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"0", "normal", "benign", "false", "none", "clean"}:
        return "normal"
    return "attack"


def infer_uq_attack_type(path: str) -> str:
    parts = [part for part in Path(path).parts if part and part not in {"/", "data", "attack_samples"}]
    if len(parts) >= 2:
        return parts[-2].replace("_", " ")
    return Path(path).stem.replace("_", " ")


def norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def counts(series: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in Counter(series.fillna("")).items()}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return None
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def render_profile_md(profile: dict[str, Any]) -> str:
    lines = [
        "# Dataset Profile",
        "",
        f"- Profile mode: `{profile.get('profile_mode')}`",
        "- Model inputs exclude raw source/destination IP columns.",
        "",
        "## Datasets",
    ]
    for name, data in profile.get("datasets", {}).items():
        lines.extend(
            [
                f"### {name}",
                f"- Status: `{data.get('status', 'profiled')}`",
                f"- Path: `{data.get('path', '')}`",
                f"- Unit: `{data.get('unit', data.get('file_format', 'unknown'))}`",
                f"- Rows profiled: `{data.get('rows_profiled', 'n/a')}`",
                f"- Full row count: `{data.get('full_row_count', 'not counted in smoke profile')}`",
                f"- Label counts: `{data.get('label_counts', data.get('label_counts_by_file', {}))}`",
                f"- Attack types: `{data.get('attack_type_counts', data.get('attack_type_counts_by_file', {}))}`",
                f"- Time columns: `{data.get('time_columns', data.get('time_column', []))}`",
                f"- Identifier columns excluded: `{data.get('identifier_columns', [])}`",
                "",
            ]
        )
    processed = profile.get("processed_output", {})
    lines.extend(
        [
            "## Common Feature Output",
            f"- Path: `{processed.get('path', '')}`",
            f"- Rows: `{processed.get('rows', 0)}`",
            f"- Dataset counts: `{processed.get('dataset_counts', {})}`",
            f"- Label counts: `{processed.get('label_counts', {})}`",
            "",
            "## Notes",
            "- CSE-CIC-IDS2018 is flow CSV data and is mapped directly into `ndr_common_v1` smoke features.",
            "- UQ-IoT-IDS2021 is PCAP data in this workspace, so row-level features require Zeek/tshark extraction before training.",
            "- Public dataset metrics must remain cross-domain reference metrics and must not be merged into simulation operating claims.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
