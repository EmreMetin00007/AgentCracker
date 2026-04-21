"""Tests for notifier."""
from unittest.mock import MagicMock, patch

from hackeragent.core.notifier import Notifier


class FakeConfig:
    def __init__(self, data):
        self._data = data

    def get(self, path, default=None):
        node = self._data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def test_disabled_notifier_returns_false():
    n = Notifier(enabled=False)
    assert n.send_finding("test") is False


def test_severity_filter_blocks_info():
    n = Notifier(
        enabled=True, discord_webhook="http://test",
        severities=["critical", "high"],
    )
    assert n.send_finding("test", severity="info") is False
    assert n.send_finding("test", severity="low") is False


def test_dedupe_blocks_duplicate():
    n = Notifier(
        enabled=True, discord_webhook="http://test",
        severities=["critical"], dedupe_window_seconds=60,
    )
    with patch("hackeragent.core.notifier.requests") as mock_req:
        mock_req.post = MagicMock()
        assert n.send_finding("duplicate", severity="critical") is True
        # İkinci gönderim dedupe edilmeli
        assert n.send_finding("duplicate", severity="critical") is False


def test_different_title_not_deduped():
    n = Notifier(
        enabled=True, discord_webhook="http://test",
        severities=["critical"], dedupe_window_seconds=60,
    )
    with patch("hackeragent.core.notifier.requests"):
        assert n.send_finding("title1", severity="critical") is True
        assert n.send_finding("title2", severity="critical") is True


def test_from_config_loads_fields():
    cfg = FakeConfig({
        "notifications": {
            "enabled": True,
            "discord_webhook": "https://discord/x",
            "severities": ["critical"],
            "dedupe_window_seconds": 120,
        }
    })
    n = Notifier.from_config(cfg)
    assert n.enabled is True
    assert n.discord_webhook == "https://discord/x"
    assert n.severities == ["critical"]
    assert n.dedupe_window_seconds == 120


def test_no_webhook_configured_still_ok():
    n = Notifier(enabled=True, severities=["critical"])
    with patch("hackeragent.core.notifier.requests"):
        # Dispatch çalışır ama hiçbir webhook'a gitmez
        result = n.send_finding("test", severity="critical")
        # _should_send True; dedupe/should_send False değil
        assert result is True


def test_requests_missing_blocks_send():
    n = Notifier(enabled=True, discord_webhook="http://test", severities=["critical"])
    with patch("hackeragent.core.notifier.requests", None):
        assert n.send_finding("test", severity="critical") is False
