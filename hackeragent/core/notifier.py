"""Webhook notifier — kritik bulgu / finding durumunda Discord/Slack/generic push.

Config:
    notifications:
      enabled: true
      webhook_url: "https://discord.com/api/webhooks/..."
      # veya
      slack_webhook: "https://hooks.slack.com/services/..."
      # veya generic JSON POST
      generic_webhook: "https://example.com/alerts"
      # Ne zaman gönder?
      severities: ["critical", "high"]
      # Rate limiting — aynı başlık 5dk içinde max 1 bildirim
      dedupe_window_seconds: 300

Kullanım:
    from hackeragent.core.notifier import Notifier
    n = Notifier.from_config(cfg)
    n.send_finding(title="SQLi in /login", severity="critical",
                   target="example.com", summary="...")
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

_SEVERITY_EMOJI = {
    "critical": "🚨",
    "high": "🔴",
    "medium": "🟠",
    "low": "🟡",
    "info": "🔵",
}


@dataclass
class Notifier:
    enabled: bool = False
    discord_webhook: str = ""
    slack_webhook: str = ""
    generic_webhook: str = ""
    severities: list[str] = field(default_factory=lambda: ["critical", "high"])
    dedupe_window_seconds: int = 300
    timeout_seconds: int = 5
    _recent_sig: dict[str, float] = field(default_factory=dict, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @classmethod
    def from_config(cls, config: Any) -> "Notifier":
        """Config object'ten Notifier yükle. Config.get('notifications.*')"""
        return cls(
            enabled=bool(config.get("notifications.enabled", False)),
            discord_webhook=config.get("notifications.discord_webhook", "") or config.get("notifications.webhook_url", "") or "",
            slack_webhook=config.get("notifications.slack_webhook", "") or "",
            generic_webhook=config.get("notifications.generic_webhook", "") or "",
            severities=config.get("notifications.severities", ["critical", "high"]) or ["critical", "high"],
            dedupe_window_seconds=int(config.get("notifications.dedupe_window_seconds", 300)),
            timeout_seconds=int(config.get("notifications.timeout_seconds", 5)),
        )

    def _should_send(self, severity: str, title: str) -> bool:
        if not self.enabled:
            return False
        if severity.lower() not in [s.lower() for s in self.severities]:
            return False
        if requests is None:
            log.debug("Notifier: requests modülü yok → gönderilemiyor")
            return False
        # Dedupe
        sig = hashlib.sha1(f"{severity}|{title}".encode()).hexdigest()[:16]
        now = time.time()
        with self._lock:
            last = self._recent_sig.get(sig, 0.0)
            if now - last < self.dedupe_window_seconds:
                log.debug("Notifier dedupe: '%s' daha yeni gönderilmiş", title)
                return False
            self._recent_sig[sig] = now
            # Eski kayıtları temizle
            cutoff = now - (self.dedupe_window_seconds * 2)
            self._recent_sig = {k: v for k, v in self._recent_sig.items() if v > cutoff}
        return True

    def send_finding(
        self,
        title: str,
        severity: str = "high",
        target: str = "",
        summary: str = "",
        session_id: str = "",
    ) -> bool:
        """Finding bildirimini async gönder. True = kuyruğa alındı."""
        if not self._should_send(severity, title):
            return False
        emoji = _SEVERITY_EMOJI.get(severity.lower(), "⚠️")
        text_title = f"{emoji} [{severity.upper()}] {title}"
        body = ""
        if target:
            body += f"**Hedef:** `{target}`\n"
        if summary:
            body += f"**Özet:** {summary[:800]}\n"
        if session_id:
            body += f"**Session:** `{session_id}`\n"

        # Fire-and-forget thread
        t = threading.Thread(
            target=self._dispatch,
            args=(text_title, body, severity),
            daemon=True,
            name="notifier-dispatch",
        )
        t.start()
        return True

    def _dispatch(self, title: str, body: str, severity: str) -> None:
        if self.discord_webhook:
            self._send_discord(title, body)
        if self.slack_webhook:
            self._send_slack(title, body)
        if self.generic_webhook:
            self._send_generic(title, body, severity)

    def _send_discord(self, title: str, body: str) -> None:
        try:
            color = {"critical": 0xFF0000, "high": 0xFF6600, "medium": 0xFFCC00,
                     "low": 0x00AAFF, "info": 0x888888}
            sev_key = next((k for k in color if k in title.lower()), "info")
            payload = {
                "embeds": [{
                    "title": title[:256],
                    "description": body[:4000],
                    "color": color[sev_key],
                }],
            }
            r = requests.post(self.discord_webhook, json=payload, timeout=self.timeout_seconds)
            if r.status_code >= 400:
                log.warning("Discord webhook %d: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.debug("Discord gönderim hatası: %s", e)

    def _send_slack(self, title: str, body: str) -> None:
        try:
            payload = {
                "text": title,
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": body[:3000] or " "}},
                ],
            }
            r = requests.post(self.slack_webhook, json=payload, timeout=self.timeout_seconds)
            if r.status_code >= 400:
                log.warning("Slack webhook %d: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.debug("Slack gönderim hatası: %s", e)

    def _send_generic(self, title: str, body: str, severity: str) -> None:
        try:
            payload = {
                "title": title,
                "body": body,
                "severity": severity,
                "timestamp": int(time.time()),
                "source": "hackeragent",
            }
            r = requests.post(
                self.generic_webhook,
                json=payload,
                timeout=self.timeout_seconds,
                headers={"Content-Type": "application/json"},
            )
            if r.status_code >= 400:
                log.warning("Generic webhook %d: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.debug("Generic webhook hatası: %s", e)
