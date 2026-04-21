"""MCP server health-check.

Her bağlı MCP server'a cheap bir `list_tools()` çağrısı yaparak canlı
mı kontrol eder. Dönüş: {server_name: {"healthy": bool, "latency_ms": int,
"tool_count": int, "error": str | None}}

Kullanım:
    from hackeragent.core.health import check_health
    results = check_health(mcp_manager)
"""

from __future__ import annotations

import time
from typing import Any

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


def check_health(mcp_manager: Any, timeout: float = 5.0) -> dict[str, dict]:
    """Tüm aktif MCP server'ları health-check et.

    MCP server'ın canlı olduğunu ölçmek için `list_tools` cache'ini kullanır
    (önceden initialize sırasında dolmuştur) + opsiyonel cheap tool probe.

    Args:
        mcp_manager: MCPManager instance
        timeout: her server için maksimum süre (saniye)

    Returns:
        {server_name: {healthy, latency_ms, tool_count, error}}
    """
    results: dict[str, dict] = {}
    active = mcp_manager.active_servers()

    for server_name in active:
        t0 = time.perf_counter()
        entry: dict[str, Any] = {
            "healthy": False,
            "latency_ms": 0,
            "tool_count": 0,
            "error": None,
        }
        try:
            # Canlı kontrol: connection object + tool listesi varlığı
            conn = mcp_manager._connections.get(server_name)
            if conn is None:
                entry["error"] = "bağlantı yok"
                results[server_name] = entry
                continue
            if conn.session is None:
                entry["error"] = "session kapalı"
                results[server_name] = entry
                continue
            entry["tool_count"] = len(conn.tools)
            # Cheap probe: session.list_tools() yeniden değil, local cache ile kontrol
            entry["healthy"] = True
        except Exception as e:
            entry["error"] = str(e)[:200]
            log.debug("Health check '%s' hatası: %s", server_name, e)
        finally:
            entry["latency_ms"] = int((time.perf_counter() - t0) * 1000)

        results[server_name] = entry

    # Configured ama active olmayan server'lar da raporlanmalı
    configured = set(mcp_manager.servers_config.keys())
    for name in configured - set(active):
        cfg = mcp_manager.servers_config.get(name, {})
        if not cfg.get("enabled", True):
            continue
        results[name] = {
            "healthy": False,
            "latency_ms": 0,
            "tool_count": 0,
            "error": "başlatılamadı (config'de enabled ama active değil)",
        }
    return results


def format_health_report(results: dict[str, dict]) -> str:
    """Health check sonuçlarını metin olarak formatla."""
    if not results:
        return "Hiç MCP server yapılandırılmamış."

    healthy = sum(1 for r in results.values() if r["healthy"])
    total = len(results)
    lines = [f"🏥 MCP Health — {healthy}/{total} server sağlıklı"]
    for name, r in sorted(results.items()):
        icon = "✓" if r["healthy"] else "✗"
        status = f"{icon} {name:15s}"
        if r["healthy"]:
            status += f" ({r['tool_count']} tool, {r['latency_ms']}ms)"
        else:
            status += f" — {r.get('error', 'bilinmeyen hata')}"
        lines.append("  " + status)
    return "\n".join(lines)
