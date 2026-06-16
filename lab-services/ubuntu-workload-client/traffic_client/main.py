from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config.example.json"


@dataclass(frozen=True)
class OperationResult:
    operation: str
    target: str
    ok: bool
    detail: str
    elapsed_ms: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_event(config: dict[str, Any], result: OperationResult) -> None:
    log_path = Path(config.get("log_path", "logs/client-traffic.jsonl"))
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "ts": utc_now(),
        "client_id": config.get("client_id", "ubuntu-client"),
        "operation": result.operation,
        "target": result.target,
        "ok": result.ok,
        "detail": result.detail,
        "elapsed_ms": result.elapsed_ms,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def timed(operation: str, target: str, func: Any) -> OperationResult:
    started = time.monotonic()
    try:
        detail = func()
        ok = True
    except Exception as exc:  # noqa: BLE001 - log and continue to keep traffic loop alive.
        detail = f"{type(exc).__name__}: {exc}"
        ok = False
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return OperationResult(operation, target, ok, str(detail), elapsed_ms)


def dns_lookup(config: dict[str, Any]) -> OperationResult:
    hosts = config.get("dns", {}).get("hosts", [])
    host = random.choice(hosts)
    timeout = float(config.get("timeouts", {}).get("dns", 2))

    def run() -> str:
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        try:
            answers = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        finally:
            socket.setdefaulttimeout(original_timeout)
        addresses = sorted({item[4][0] for item in answers})
        return ",".join(addresses) if addresses else "no-address"

    return timed("dns", host, run)


def http_request(config: dict[str, Any]) -> OperationResult:
    http_config = config.get("http", {})
    base_url = random.choice(http_config.get("base_urls", []))
    request_config = random.choice(http_config.get("requests", []))
    method = request_config.get("method", "GET").upper()
    path = request_config.get("path", "/")
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    timeout = float(config.get("timeouts", {}).get("http", 4))

    def run() -> str:
        body = None
        headers = {
            "User-Agent": random.choice(
                [
                    "Mozilla/5.0 UbuntuClient/1.0",
                    "curl/8.0 ndr-lab",
                    "OfficePortalHealthCheck/1.0",
                ]
            ),
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.5",
        }
        if "json" in request_config:
            body = json.dumps(request_config["json"]).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                response.read(512)
                return f"status={response.status}"
        except urllib.error.HTTPError as exc:
            exc.read(256)
            return f"status={exc.code}"

    return timed("http", f"{method} {url}", run)


def tcp_probe(config: dict[str, Any]) -> OperationResult:
    target = random.choice(config.get("tcp", {}).get("targets", []))
    host = target["host"]
    port = int(target["port"])
    timeout = float(config.get("timeouts", {}).get("tcp", 3))

    def run() -> str:
        with socket.create_connection((host, port), timeout=timeout):
            return "connected"

    return timed("tcp", f"{target.get('name', host)}:{host}:{port}", run)


def smb_action(config: dict[str, Any]) -> OperationResult:
    smb_config = config.get("smb", {})
    host = smb_config["host"]
    share = smb_config["share"]
    command = random.choice(smb_config.get("commands", ["ls"]))
    timeout = float(config.get("timeouts", {}).get("command", 8))

    def run() -> str:
        if shutil.which("smbclient") is None:
            raise RuntimeError("smbclient is not installed")
        subprocess.run(
            [
                "smbclient",
                f"//{host}/{share}",
                "-U",
                f"{smb_config.get('username', '')}%{smb_config.get('password', '')}",
                "-c",
                command,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return f"command={command}"

    return timed("smb", f"//{host}/{share}", run)


def database_query(config: dict[str, Any]) -> OperationResult:
    db_config = config.get("database", {})
    db_type = db_config.get("type", "postgres")
    query = random.choice(db_config.get("queries", ["select 1;"]))
    timeout = float(config.get("timeouts", {}).get("command", 8))

    if db_type == "postgres":
        return postgres_query(config, query, timeout)
    if db_type == "mysql":
        return mysql_query(config, query, timeout)
    raise ValueError(f"unsupported database type: {db_type}")


def postgres_query(config: dict[str, Any], query: str, timeout: float) -> OperationResult:
    db_config = config["database"]
    host = db_config["host"]
    port = str(db_config.get("port", 5432))
    database = db_config["database"]
    username = db_config["username"]

    def run() -> str:
        if shutil.which("psql") is None:
            with socket.create_connection((host, int(port)), timeout=float(config.get("timeouts", {}).get("tcp", 3))):
                return "psql missing; tcp fallback connected"
        env = os.environ.copy()
        env["PGPASSWORD"] = str(db_config.get("password", ""))
        subprocess.run(
            [
                "psql",
                "-h",
                host,
                "-p",
                port,
                "-U",
                username,
                "-d",
                database,
                "-c",
                query,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            env=env,
        )
        return "query=postgres"

    return timed("database", f"postgres://{host}:{port}/{database}", run)


def mysql_query(config: dict[str, Any], query: str, timeout: float) -> OperationResult:
    db_config = config["database"]
    host = db_config["host"]
    port = str(db_config.get("port", 3306))
    database = db_config["database"]
    username = db_config["username"]

    def run() -> str:
        if shutil.which("mysql") is None:
            with socket.create_connection((host, int(port)), timeout=float(config.get("timeouts", {}).get("tcp", 3))):
                return "mysql missing; tcp fallback connected"
        subprocess.run(
            [
                "mysql",
                "-h",
                host,
                "-P",
                port,
                "-u",
                username,
                f"-p{db_config.get('password', '')}",
                database,
                "-e",
                query,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return "query=mysql"

    return timed("database", f"mysql://{host}:{port}/{database}", run)


OPERATIONS = {
    "dns": dns_lookup,
    "http": http_request,
    "tcp": tcp_probe,
    "smb": smb_action,
    "database": database_query,
}


def enabled_operations(config: dict[str, Any]) -> list[str]:
    operations: list[str] = []
    for name in OPERATIONS:
        if config.get(name, {}).get("enabled", False):
            operations.append(name)
    return operations


def choose_operation(config: dict[str, Any], names: list[str]) -> str:
    weights = config.get("weights", {})
    return random.choices(names, weights=[int(weights.get(name, 1)) for name in names], k=1)[0]


def run_once(config: dict[str, Any]) -> OperationResult:
    names = enabled_operations(config)
    if not names:
        raise RuntimeError("no enabled operations in config")
    name = choose_operation(config, names)
    result = OPERATIONS[name](config)
    write_event(config, result)
    return result


def print_result(result: OperationResult) -> None:
    status = "ok" if result.ok else "fail"
    print(f"{utc_now()} {status:4} {result.operation:8} {result.target} ({result.elapsed_ms}ms) {result.detail}")


def run_loop(config: dict[str, Any]) -> None:
    interval = config.get("interval_seconds", {})
    min_sleep = float(interval.get("min", 5))
    max_sleep = float(interval.get("max", 15))
    while True:
        print_result(run_once(config))
        time.sleep(random.uniform(min_sleep, max_sleep))


def check_config(config: dict[str, Any]) -> int:
    failures = 0
    names = enabled_operations(config)
    if not names:
        print("fail no enabled operations")
        return 1
    for name in names:
        result = OPERATIONS[name](config)
        write_event(config, result)
        print_result(result)
        if not result.ok:
            failures += 1
    return 1 if failures else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate normal Ubuntu client traffic for an NDR VM lab.")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Path to JSON config. Default: {DEFAULT_CONFIG}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("once", help="Run one random operation.")
    subparsers.add_parser("loop", help="Run random operations forever.")
    subparsers.add_parser("check", help="Run each enabled operation once.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = load_config(args.config)

    if args.command == "once":
        print_result(run_once(config))
        return 0
    if args.command == "loop":
        run_loop(config)
        return 0
    if args.command == "check":
        return check_config(config)
    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
