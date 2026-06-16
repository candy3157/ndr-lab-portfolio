from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import choose_display_status


def epoch_to_iso(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class EventStore:
    def __init__(self, database_path: Path, status_policy: dict[str, Any] | None = None) -> None:
        self.database_path = database_path
        self.status_policy = status_policy or {}
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                create table if not exists detection_events (
                    id integer primary key autoincrement,
                    timestamp text not null,
                    received_at text not null,
                    received_at_epoch real not null,
                    sensor_id text not null,
                    status text not null,
                    score real not null,
                    src_ip text,
                    target_network text,
                    primary_dst_ip text,
                    top_dst_ips text,
                    window_seconds integer,
                    flow_count integer,
                    unique_dst_ips integer,
                    unique_dst_ports integer,
                    syn_count integer,
                    failed_connection_ratio real,
                    top_dst_ports text,
                    raw text not null
                )
                """
            )
            self._ensure_column(conn, "primary_dst_ip", "text")
            self._ensure_column(conn, "top_dst_ips", "text")
            conn.execute("create index if not exists idx_detection_events_received on detection_events(received_at_epoch)")
            conn.execute("create index if not exists idx_detection_events_status on detection_events(status)")

    def _ensure_column(self, conn: sqlite3.Connection, column: str, column_type: str) -> None:
        columns = {
            str(row["name"])
            for row in conn.execute("pragma table_info(detection_events)").fetchall()
        }
        if column not in columns:
            conn.execute(f"alter table detection_events add column {column} {column_type}")

    def insert_event(self, event: dict[str, Any]) -> dict[str, Any]:
        received_at_epoch = time.time()
        received_at = epoch_to_iso(received_at_epoch)
        top_dst_ports = json.dumps(event.get("top_dst_ports", []), separators=(",", ":"))
        top_dst_ips = json.dumps(event.get("top_dst_ips", []), separators=(",", ":"))
        raw = json.dumps(event.get("raw", event), ensure_ascii=False, separators=(",", ":"))
        with self.connect() as conn:
            cursor = conn.execute(
                """
                insert into detection_events (
                    timestamp, received_at, received_at_epoch, sensor_id, status, score,
                    src_ip, target_network, primary_dst_ip, top_dst_ips, window_seconds, flow_count,
                    unique_dst_ips, unique_dst_ports, syn_count, failed_connection_ratio,
                    top_dst_ports, raw
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["timestamp"],
                    received_at,
                    received_at_epoch,
                    event["sensor_id"],
                    event["status"],
                    event["score"],
                    event["src_ip"],
                    event["target_network"],
                    event["primary_dst_ip"],
                    top_dst_ips,
                    event["window_seconds"],
                    event["flow_count"],
                    event["unique_dst_ips"],
                    event["unique_dst_ports"],
                    event["syn_count"],
                    event["failed_connection_ratio"],
                    top_dst_ports,
                    raw,
                ),
            )
            event_id = int(cursor.lastrowid)
        saved = dict(event)
        saved.update({"id": event_id, "received_at": received_at, "received_at_epoch": received_at_epoch})
        return saved

    def recent_events(self, limit: int = 80) -> list[dict[str, Any]]:
        limit = max(1, min(500, int(limit)))
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from detection_events
                order by received_at_epoch desc, id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def recent_events_since(self, seconds: float) -> list[dict[str, Any]]:
        cutoff = time.time() - float(seconds)
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from detection_events
                where received_at_epoch >= ?
                order by received_at_epoch desc, id desc
                """,
                (cutoff,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def status(self) -> dict[str, Any]:
        return choose_display_status(self.recent_events(80), self.status_policy)

    def metrics(self) -> dict[str, Any]:
        events = self.recent_events_since(300)
        counts = {"normal": 0, "warning": 0, "scanning": 0}
        by_source: dict[str, int] = {}
        for event in events:
            status = str(event.get("status", "normal"))
            counts[status] = counts.get(status, 0) + 1
            src_ip = str(event.get("src_ip") or "unknown")
            by_source[src_ip] = by_source.get(src_ip, 0) + 1
        top_sources = sorted(by_source.items(), key=lambda item: item[1], reverse=True)[:5]
        return {
            "window_seconds": 300,
            "event_count": len(events),
            "status_counts": counts,
            "top_sources": [{"src_ip": src_ip, "count": count} for src_ip, count in top_sources],
        }

    def snapshot(self, limit: int = 80) -> dict[str, Any]:
        return {
            "status": self.status(),
            "metrics": self.metrics(),
            "events": self.recent_events(limit),
        }

    def _row_to_event(self, row: sqlite3.Row) -> dict[str, Any]:
        event = dict(row)
        event["top_dst_ports"] = json.loads(event.get("top_dst_ports") or "[]")
        event["top_dst_ips"] = json.loads(event.get("top_dst_ips") or "[]")
        event["raw"] = json.loads(event.get("raw") or "{}")
        return event
