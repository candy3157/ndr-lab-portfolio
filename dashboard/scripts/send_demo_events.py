#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def event_for_mode(mode: str) -> dict[str, Any]:
    if mode == "normal":
        return {
            "timestamp": utc_now(),
            "sensor_id": "sensor-01",
            "status": "normal",
            "score": round(random.uniform(0.02, 0.2), 2),
            "src_ip": "10.10.10.20",
            "target_network": "10.10.20.0/24",
            "window_seconds": 10,
            "flow_count": random.randint(12, 42),
            "unique_dst_ips": random.randint(1, 3),
            "unique_dst_ports": random.randint(1, 5),
            "syn_count": random.randint(4, 18),
            "failed_connection_ratio": round(random.uniform(0.0, 0.08), 2),
            "top_dst_ports": [53, 80, 445],
        }
    if mode == "warning":
        return {
            "timestamp": utc_now(),
            "sensor_id": "sensor-01",
            "status": "warning",
            "score": round(random.uniform(0.58, 0.78), 2),
            "src_ip": "10.10.90.10",
            "target_network": "10.10.20.0/28",
            "window_seconds": 10,
            "flow_count": random.randint(80, 160),
            "unique_dst_ips": random.randint(4, 9),
            "unique_dst_ports": random.randint(8, 18),
            "syn_count": random.randint(60, 130),
            "failed_connection_ratio": round(random.uniform(0.25, 0.55), 2),
            "top_dst_ports": [22, 80, 443, 445, 5432],
        }
    if mode == "scanning":
        return {
            "timestamp": utc_now(),
            "sensor_id": "sensor-01",
            "status": "scanning",
            "score": round(random.uniform(0.88, 0.99), 2),
            "src_ip": "10.10.90.10",
            "target_network": "10.10.20.0/24",
            "window_seconds": 10,
            "flow_count": random.randint(320, 720),
            "unique_dst_ips": random.randint(16, 42),
            "unique_dst_ports": random.randint(60, 180),
            "syn_count": random.randint(260, 650),
            "failed_connection_ratio": round(random.uniform(0.68, 0.94), 2),
            "top_dst_ports": [22, 23, 53, 80, 139, 443, 445, 3306, 5432, 8080],
        }
    raise ValueError(f"unsupported mode: {mode}")


def post_event(base_url: str, event: dict[str, Any]) -> None:
    body = json.dumps(event).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/events",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()
        print(f"posted {event['status']} score={event['score']} status={response.status}")


def run_demo(base_url: str) -> None:
    for mode, count, delay in (
        ("normal", 4, 1.0),
        ("warning", 3, 1.0),
        ("scanning", 4, 1.0),
        ("normal", 3, 1.0),
    ):
        for _ in range(count):
            post_event(base_url, event_for_mode(mode))
            time.sleep(delay)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send sample NDR detection events to the dashboard.")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=["normal", "warning", "scanning", "demo"], default="demo")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--delay", type=float, default=1.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "demo":
        run_demo(args.url)
        return 0
    for _ in range(args.count):
        post_event(args.url, event_for_mode(args.mode))
        time.sleep(args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
