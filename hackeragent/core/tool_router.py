"""LLM tool_calls → MCP tool çağrıları yönlendirici.

Özellikler:
  • Scope guard — host allowlist (safety.scope)
  • Circuit breaker — ardışık fail'lerde tool'u kısa süre bloke et
  • Auto-restart — server-wide fail eşiği aşılırsa MCP server'ı yeniden başlat
"""

from __future__ import annotations

import json

from hackeragent.core.circuit_breaker import CircuitBreaker
from hackeragent.core.mcp_manager import MCPManager
from hackeragent.core.scope import ScopeGuard
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# Başarısızlık sayan çıktı örüntüleri — kali-tools "HATA:" ile başlayan string döndürüyor
_FAILURE_PREFIXES = ("HATA:", "ERROR:", "Error:", "Exception:", "❌", "🚫")


class ToolRouter:
    """LLM'in döndürdüğü tool_calls'ı MCP server'lara yönlendirir."""

    def __init__(
        self,
        mcp: MCPManager,
        tool_timeout: int = 300,
        scope: ScopeGuard | None = None,
        breaker: CircuitBreaker | None = None,
    ):
        self.mcp = mcp
        self.tool_timeout = tool_timeout
        self.scope = scope or ScopeGuard()
        self.breaker = breaker or CircuitBreaker()
        self._map: dict[str, tuple[str, str]] = {}
        self.refresh()

    def refresh(self) -> None:
        self._map = {t.qualified_name: (t.server, t.name) for t in self.mcp.list_tools()}

    def execute(self, tool_call: dict) -> str:
        qname = tool_call.get("name", "")
        args = tool_call.get("arguments", {}) or {}
        if not isinstance(args, dict):
            return f"HATA: '{qname}' için argümanlar dict değil: {args!r}"

        route = self._map.get(qname)
        if route is None:
            if "__" in qname:
                server, tool = qname.split("__", 1)
                route = (server, tool)
            else:
                return f"HATA: Tanımlı olmayan tool: '{qname}'"
        server, tool = route

        # 1) Scope guard
        ok, reason = self.scope.validate_args(qname, args)
        if not ok:
            log.warning("Scope guard blocked %s: %s", qname, reason)
            return reason

        # 2) Circuit breaker
        is_open, reason = self.breaker.is_open(qname)
        if is_open:
            log.warning("Circuit open for %s", qname)
            return reason

        log.info("→ %s.%s %s", server, tool, json.dumps(args)[:200])

        try:
            result = self.mcp.call_tool(server, tool, args, timeout=self.tool_timeout)
        except TimeoutError:
            err = f"HATA: '{qname}' zaman aşımı ({self.tool_timeout}s)."
            self._on_failure(qname, server, err)
            return err
        except Exception as e:
            err = f"HATA: '{qname}' çalıştırılamadı: {e}"
            log.exception("Tool execution failed: %s", qname)
            self._on_failure(qname, server, err)
            return err

        # 3) Sonuç içeriğine göre success/failure
        trimmed = (result or "").lstrip()
        if any(trimmed.startswith(p) for p in _FAILURE_PREFIXES):
            self._on_failure(qname, server, trimmed[:300])
        else:
            self.breaker.record_success(qname)

        return result

    def _on_failure(self, qname: str, server: str, error: str) -> None:
        should_restart = self.breaker.record_failure(qname, error)
        if should_restart:
            log.warning("⚠ Server '%s' çok fazla tool fail → RESTART deneniyor", server)
            if self.mcp.restart_server(server):
                self.refresh()
                log.info("✓ Server '%s' restart + tool map yenilendi", server)