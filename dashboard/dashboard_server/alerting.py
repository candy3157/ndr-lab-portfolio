from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class AlertManager:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.provider = str(self.config.get("provider") or "").lower()
        self.cooldown_seconds = float(self.config.get("cooldown_seconds", 300))
        self.timeout_seconds = float(self.config.get("timeout_seconds", 5))
        self._last_sent: dict[str, float] = {}
        self._lock = threading.Lock()

    def notify(self, event: dict[str, Any]) -> None:
        if not self._should_send(event):
            return
        thread = threading.Thread(target=self._send, args=(dict(event),), daemon=True)
        thread.start()

    def _should_send(self, event: dict[str, Any]) -> bool:
        if not self.enabled or self.provider != "telegram":
            return False
        if str(event.get("status") or "").lower() != "scanning":
            return False

        key = alert_key(event)
        now = time.time()
        with self._lock:
            last_sent = self._last_sent.get(key, 0.0)
            if now - last_sent < self.cooldown_seconds:
                return False
            self._last_sent[key] = now
        return True

    def _send(self, event: dict[str, Any]) -> None:
        try:
            self._send_telegram(event)
        except Exception as exc:  # noqa: BLE001 - alert failure must not break dashboard ingestion.
            print(f"[alert] failed to send Telegram alert: {exc}")

    def _send_telegram(self, event: dict[str, Any]) -> None:
        telegram = self.config.get("telegram") or {}
        bot_token = resolve_secret(telegram.get("bot_token"))
        chat_id = resolve_secret(telegram.get("chat_id"))
        if not bot_token or not chat_id:
            print("[alert] Telegram alert skipped: missing bot_token or chat_id")
            return

        body = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": render_telegram_message(event),
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            if response.status >= 400:
                details = response.read().decode("utf-8", errors="replace")
                raise urllib.error.HTTPError(
                    request.full_url,
                    response.status,
                    details,
                    response.headers,
                    None,
                )


def alert_key(event: dict[str, Any]) -> str:
    src_ip = str(event.get("src_ip") or "unknown-source")
    return f"scanning:{src_ip}"


def resolve_secret(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("env:"):
        return os.environ.get(text.removeprefix("env:"), "").strip()
    return text


def render_telegram_message(event: dict[str, Any]) -> str:
    target_ips = event.get("top_dst_ips") or []
    if isinstance(target_ips, list) and target_ips:
        target_ip_text = ", ".join(str(item) for item in target_ips[:5])
        if len(target_ips) > 5:
            target_ip_text += f" +{len(target_ips) - 5}"
    else:
        target_ip_text = str(event.get("primary_dst_ip") or "-")

    ports = event.get("top_dst_ports") or []
    if isinstance(ports, list) and ports:
        port_text = ", ".join(str(item) for item in ports[:8])
        if len(ports) > 8:
            port_text += f" +{len(ports) - 8}"
    else:
        port_text = "-"

    return "\n".join(
        [
            "[NDR Alert] Scanning detected",
            f"Source: {event.get('src_ip') or '-'}",
            f"Target network: {event.get('target_network') or '-'}",
            f"Target IPs: {target_ip_text}",
            f"Score: {float(event.get('score') or 0.0):.2f}",
            f"Flows: {event.get('flow_count') or 0}",
            f"Unique dst IPs: {event.get('unique_dst_ips') or 0}",
            f"Unique dst ports: {event.get('unique_dst_ports') or 0}",
            f"Top ports: {port_text}",
            f"Time: {event.get('received_at') or event.get('timestamp') or '-'}",
        ]
    )
