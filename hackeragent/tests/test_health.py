"""Tests for health check."""
from types import SimpleNamespace

from hackeragent.core.health import check_health, format_health_report


class FakeConn:
    def __init__(self, session, tool_count=5):
        self.session = session
        self.tools = list(range(tool_count))  # just count


class FakeMCP:
    def __init__(self, active, configured, connections):
        self._active = active
        self.servers_config = configured
        self._connections = connections

    def active_servers(self):
        return self._active


def test_healthy_server_reports_ok():
    mcp = FakeMCP(
        active=["kali-tools"],
        configured={"kali-tools": {"enabled": True}},
        connections={"kali-tools": FakeConn(session=SimpleNamespace(), tool_count=40)},
    )
    results = check_health(mcp)
    assert results["kali-tools"]["healthy"] is True
    assert results["kali-tools"]["tool_count"] == 40
    assert results["kali-tools"]["error"] is None


def test_closed_session_reports_unhealthy():
    mcp = FakeMCP(
        active=["kali-tools"],
        configured={"kali-tools": {"enabled": True}},
        connections={"kali-tools": FakeConn(session=None)},
    )
    results = check_health(mcp)
    assert results["kali-tools"]["healthy"] is False
    assert "session" in (results["kali-tools"]["error"] or "")


def test_configured_but_inactive_server_included():
    mcp = FakeMCP(
        active=[],
        configured={"telemetry": {"enabled": True}},
        connections={},
    )
    results = check_health(mcp)
    assert "telemetry" in results
    assert results["telemetry"]["healthy"] is False
    assert "başlatılamadı" in results["telemetry"]["error"]


def test_disabled_server_excluded():
    mcp = FakeMCP(
        active=[],
        configured={"browser": {"enabled": False}},
        connections={},
    )
    results = check_health(mcp)
    assert "browser" not in results


def test_format_report_empty():
    assert "yapılandırılmamış" in format_health_report({})


def test_format_report_healthy():
    results = {"kali-tools": {"healthy": True, "latency_ms": 10, "tool_count": 40, "error": None}}
    txt = format_health_report(results)
    assert "1/1" in txt
    assert "kali-tools" in txt
    assert "40 tool" in txt


def test_format_report_mixed():
    results = {
        "kali-tools": {"healthy": True, "latency_ms": 5, "tool_count": 40, "error": None},
        "rag-engine": {"healthy": False, "latency_ms": 0, "tool_count": 0, "error": "timeout"},
    }
    txt = format_health_report(results)
    assert "1/2" in txt
    assert "timeout" in txt
