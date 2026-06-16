from __future__ import annotations

import argparse
import json
import random
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config.example.json"


USERS = [
    {"id": 1, "username": "demo", "role": "analyst"},
    {"id": 2, "username": "ops", "role": "operator"},
    {"id": 3, "username": "audit", "role": "viewer"},
]

ORDERS = [
    {"id": 1001, "customer": "north-branch", "status": "paid", "total": 138.50},
    {"id": 1002, "customer": "south-branch", "status": "processing", "total": 94.20},
    {"id": 1003, "customer": "east-branch", "status": "shipped", "total": 217.75},
]


class AppHandler(BaseHTTPRequestHandler):
    server_version = "NDRAppDB/0.1"

    @property
    def config(self) -> dict[str, Any]:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        self._maybe_delay()
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html("Internal Portal", "App/DB demo service is running.")
        elif parsed.path == "/dashboard":
            self._send_html("Dashboard", "Daily business summary is available.")
        elif parsed.path == "/api/users":
            self._send_json({"users": USERS})
        elif parsed.path == "/api/orders":
            self._send_json({"orders": ORDERS})
        elif parsed.path == "/api/reports/daily":
            self._send_json(
                {
                    "report": "daily",
                    "active_users": len(USERS),
                    "order_count": len(ORDERS),
                    "revenue": round(sum(float(order["total"]) for order in ORDERS), 2),
                }
            )
        elif parsed.path == "/health":
            self._send_json({"ok": True, "service": self.config.get("service_name", "demo-app-db")})
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        self._maybe_delay()
        parsed = urlparse(self.path)
        if parsed.path != "/api/login":
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        payload = self._read_json_body()
        username = str(payload.get("username") or "")
        ok = username in {"demo", "ops", "audit"}
        self._send_json({"ok": ok, "token": "demo-token" if ok else ""}, status=HTTPStatus.OK if ok else HTTPStatus.UNAUTHORIZED)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 100_000))
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return {}
        return payload

    def _maybe_delay(self) -> None:
        delay = self.config.get("api_delay_ms", {})
        min_ms = int(delay.get("min", 0))
        max_ms = int(delay.get("max", min_ms))
        if max_ms > 0:
            time.sleep(random.uniform(min_ms, max_ms) / 1000.0)

    def _send_html(self, title: str, body: str) -> None:
        payload = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{title}</title></head><body><h1>{title}</h1><p>{body}</p></body></html>"
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AppServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], config: dict[str, Any]) -> None:
        super().__init__(address, AppHandler)
        self.config = config


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the demo App/DB HTTP server.")
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
    address = (str(config.get("host", "0.0.0.0")), int(config.get("port", 80)))
    server = AppServer(address, config)
    print(f"App/DB HTTP server listening on http://{address[0]}:{address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping App/DB HTTP server")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
