#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send dashboard event JSON to the NDR dashboard.")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--input", type=Path, required=True, help="Path to dashboard events JSON")
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum events to send")
    parser.add_argument("--start-index", type=int, default=0, help="Skip events before this zero-based index")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    events = read_events(args.input)
    if args.start_index > 0:
        events = events[args.start_index :]
    if args.limit > 0:
        events = events[: args.limit]
    if not events:
        raise SystemExit("no events found")

    sent = 0
    for event in events:
        post_event(args.url, event)
        sent += 1
        if args.delay > 0:
            time.sleep(args.delay)

    print(f"sent {sent} events to {args.url.rstrip('/')}/api/events")
    return 0


def read_events(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"{path} must contain a JSON array")
    events: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            events.append(item)
    return events


def post_event(base_url: str, event: dict[str, Any]) -> None:
    body = json.dumps(event, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/events",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8", errors="replace")
            print(f"posted status={response.status} payload={payload}")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"dashboard rejected event: {exc.code} {details}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
