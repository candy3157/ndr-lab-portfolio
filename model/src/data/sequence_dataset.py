from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, train_test_split


DEFAULT_GROUP_COLUMNS = ["session_id", "run_id", "scenario_id", "dataset_name"]


def load_feature_list(schema_path: Path, df: pd.DataFrame) -> list[str]:
    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        features = [feature for feature in schema.get("model_input_features", []) if feature in df.columns]
        if features:
            return features
    excluded = {
        "label",
        "attack_type",
        "dataset_name",
        "data_source",
        "is_synthetic",
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
    }
    return [column for column in df.columns if column not in excluded and pd.api.types.is_numeric_dtype(df[column])]


def prepare_frame(input_path: Path, schema_path: Path) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(input_path)
    if df.empty:
        raise ValueError("input data is empty")
    if "label" not in df.columns:
        raise ValueError("input data requires a label column")
    df["label"] = df["label"].map(label_to_int).astype(int)
    if "sequence_index" not in df.columns:
        df["sequence_index"] = np.arange(len(df), dtype=np.int64)
    features = load_feature_list(schema_path, df)
    if not features:
        raise ValueError("no model input features found")
    for feature in features:
        df[feature] = pd.to_numeric(df[feature], errors="coerce")
    df[features] = df[features].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return df, features


def split_by_group(
    df: pd.DataFrame,
    test_size: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_col = first_present(df, DEFAULT_GROUP_COLUMNS)
    if group_col and df[group_col].nunique(dropna=True) >= 3:
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        train_idx, test_idx = next(splitter.split(df, df["label"], groups=df[group_col]))
        return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)
    stratify = df["label"] if df["label"].nunique() > 1 and min(Counter(df["label"]).values()) >= 2 else None
    train, test = train_test_split(df, test_size=test_size, random_state=seed, stratify=stratify)
    return train.reset_index(drop=True), test.reset_index(drop=True)


def build_sequences(
    df: pd.DataFrame,
    features: list[str],
    sequence_length: int,
    stride: int,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    group_col = first_present(df, DEFAULT_GROUP_COLUMNS)
    groups = df.groupby(group_col, dropna=False, sort=False) if group_col else [(None, df)]
    sequences: list[np.ndarray] = []
    labels: list[int] = []
    metadata: list[dict[str, Any]] = []
    for group_key, group in groups:
        ordered = sort_group(group)
        if len(ordered) < sequence_length:
            continue
        values = ordered[features].to_numpy(dtype=np.float32)
        label_values = ordered["label"].to_numpy(dtype=np.int64)
        for start in range(0, len(ordered) - sequence_length + 1, max(stride, 1)):
            end = start + sequence_length
            sequences.append(values[start:end])
            labels.append(int(label_values[start:end].max()))
            tail = ordered.iloc[end - 1]
            head = ordered.iloc[start]
            metadata.append(
                {
                    "group": "" if group_key is None else str(group_key),
                    "input_window_start": str(head.get("window_start", head.get("timestamp", ""))),
                    "input_window_end": str(tail.get("window_end", tail.get("timestamp", ""))),
                    "dataset_name": str(tail.get("dataset_name", "")),
                    "data_source": str(tail.get("data_source", "")),
                    "attack_type": str(tail.get("attack_type", "")),
                    "src_ip": str(tail.get("src_ip", "")),
                    "target_network": str(tail.get("target_network", "")),
                    "primary_dst_ip": str(tail.get("primary_dst_ip", "")),
                    "top_dst_ips": str(tail.get("top_dst_ips", "")),
                    "src_entity": str(tail.get("src_entity", "")),
                    "session_id": str(tail.get("session_id", "")),
                    "scenario_id": str(tail.get("scenario_id", "")),
                    "run_id": str(tail.get("run_id", "")),
                    "flow_count": tail.get("flow_count", 0),
                    "unique_dst_count": tail.get("unique_dst_count", 0),
                    "unique_dst_port_count": tail.get("unique_dst_port_count", 0),
                    "failed_conn_ratio": tail.get("failed_conn_ratio", 0),
                    "top_dst_ports": str(tail.get("top_dst_ports", "")),
                    "window_seconds": tail.get("window_seconds", ""),
                }
            )
    if not sequences:
        return (
            np.empty((0, sequence_length, len(features)), dtype=np.float32),
            np.empty((0,), dtype=np.int64),
            [],
        )
    return np.stack(sequences).astype(np.float32), np.asarray(labels, dtype=np.int64), metadata


def sort_group(group: pd.DataFrame) -> pd.DataFrame:
    sort_cols = []
    if "timestamp" in group.columns:
        sort_cols.append("timestamp")
    if "sequence_index" in group.columns:
        sort_cols.append("sequence_index")
    if not sort_cols:
        return group.reset_index(drop=True)
    return group.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)


def first_present(df: pd.DataFrame, columns: list[str]) -> str | None:
    for column in columns:
        if column in df.columns:
            return column
    return None


def label_to_int(value: Any) -> int:
    text = str(value).strip().lower()
    return 0 if text in {"0", "normal", "benign", "false", "clean"} else 1
