from __future__ import annotations

import argparse
import json
import math
import mimetypes
import queue
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .alerting import AlertManager
from .models import normalize_event
from .store import EventStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config.example.json"


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=20)
        with self._lock:
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        message = {"type": event_type, "data": data}
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(message)
            except queue.Full:
                try:
                    subscriber.get_nowait()
                    subscriber.put_nowait(message)
                except queue.Empty:
                    pass


class DashboardContext:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        database_path = Path(config.get("database_path", "data/dashboard.sqlite3"))
        if not database_path.is_absolute():
            database_path = PROJECT_ROOT / database_path
        self.static_dir = Path(config.get("static_dir", "static"))
        if not self.static_dir.is_absolute():
            self.static_dir = PROJECT_ROOT / self.static_dir
        self.store = EventStore(database_path, config.get("status_policy", {}))
        self.broadcaster = Broadcaster()
        self.alerts = AlertManager(config.get("alerts", {}))


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "NDRDashboard/0.1"

    @property
    def context(self) -> DashboardContext:
        return self.server.context  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        print(f"{self.address_string()} - {format % args}")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._send_static_file(self.context.static_dir / "index.html")
        elif path.startswith("/static/"):
            self._send_static_file(self.context.static_dir / path.removeprefix("/static/"))
        elif path == "/api/health":
            self._send_json({"ok": True, "service": "ndr-dashboard"})
        elif path == "/api/status":
            self._send_json(self.context.store.status())
        elif path == "/api/metrics":
            self._send_json(self.context.store.metrics())
        elif path == "/api/events/recent":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["80"])[0])
            self._send_json({"events": self.context.store.recent_events(limit)})
        elif path == "/api/snapshot":
            limit = int(self.context.config.get("display", {}).get("recent_event_limit", 80))
            self._send_json(self.context.store.snapshot(limit))
        elif path == "/api/stream":
            self._send_stream()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/events":
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return

        try:
            payload = self._read_json_body()
            event = normalize_event(payload, self.context.config.get("status_policy", {}))
            saved = self.context.store.insert_event(event)
        except Exception as exc:  # noqa: BLE001 - return API error for malformed sensor input.
            self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        limit = int(self.context.config.get("display", {}).get("recent_event_limit", 80))
        snapshot = self.context.store.snapshot(limit)
        self.context.broadcaster.publish("event", {"event": saved, "snapshot": snapshot})
        self.context.alerts.notify(saved)
        self._send_json({"ok": True, "event": saved, "status": snapshot["status"]}, status=HTTPStatus.CREATED)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("empty request body")
        if length > 1_000_000:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(make_json_safe(payload), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            static_root = self.context.static_dir.resolve()
            if static_root not in resolved.parents and resolved != static_root:
                raise FileNotFoundError
            body = resolved.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "static file not found")
            return

        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_stream(self) -> None:
        self.send_response(HTTPStatus.OK)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        subscriber = self.context.broadcaster.subscribe()
        try:
            self._write_sse("snapshot", self.context.store.snapshot())
            while True:
                try:
                    message = subscriber.get(timeout=15)
                    self._write_sse(message["type"], message["data"])
                except queue.Empty:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.context.broadcaster.unsubscribe(subscriber)

    def _write_sse(self, event_type: str, payload: dict[str, Any]) -> None:
        body = json.dumps(make_json_safe(payload), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        self.wfile.write(f"event: {event_type}\n".encode("utf-8"))
        self.wfile.write(f"data: {body}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")


class DashboardHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], context: DashboardContext) -> None:
        super().__init__(server_address, DashboardHandler)
        self.context = context


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def make_json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the NDR dashboard server.")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    if args.host is not None:
        config["host"] = args.host
    if args.port is not None:
        config["port"] = args.port

    context = DashboardContext(config)
    address = (str(config.get("host", "0.0.0.0")), int(config.get("port", 8000)))
    server = DashboardHTTPServer(address, context)
    print(f"NDR dashboard listening on http://{address[0]}:{address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping NDR dashboard")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
