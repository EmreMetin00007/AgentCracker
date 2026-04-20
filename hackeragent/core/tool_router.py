"""LLM tool_calls → MCP tool çağrıları yönlendirici."""

from __future__ import annotations

import json

from hackeragent.core.mcp_manager import MCPManager
from hackeragent.core.scope import ScopeGuard
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


class ToolRouter:
    """LLM'in döndürdüğü tool_calls'ı MCP server'lara yönlendirir."""

    def __init__(
        self,
        mcp: MCPManager,
        tool_timeout: int = 300,
        scope: ScopeGuard | None = None,
    ):
        self.mcp = mcp
        self.tool_timeout = tool_timeout
        self.scope = scope or ScopeGuard()
        # name → (server, tool_name) lookup (hızlı çözümleme)
        self._map: dict[str, tuple[str, str]] = {}
        self.refresh()

    def refresh(self) -> None:
        self._map = {t.qualified_name: (t.server, t.name) for t in self.mcp.list_tools()}

    def execute(self, tool_call: dict) -> str:
        """Bir tool_call'ı çalıştır. Hata durumunda metin döner (LLM'e iletilir)."""
        qname = tool_call.get("name", "")
        args = tool_call.get("arguments", {}) or {}
        if not isinstance(args, dict):
            return f"HATA: '{qname}' için argümanlar dict değil: {args!r}"

        route = self._map.get(qname)
        if route is None:
            # Fallback: direkt '<server>__<tool>' parse
            if "__" in qname:
                server, tool = qname.split("__", 1)
                route = (server, tool)
            else:
                return f"HATA: Tanımlı olmayan tool: '{qname}'"

        server, tool = route

        # Scope guard — her tool çağrısından önce
        ok, reason = self.scope.validate_args(qname, args)
        if not ok:
            log.warning("Scope guard blocked %s: %s", qname, reason)
            return reason

        log.info("→ %s.%s %s", server, tool, json.dumps(args)[:200])
        try:
            result = self.mcp.call_tool(server, tool, args, timeout=self.tool_timeout)
            return result
        except TimeoutError:
            return f"HATA: '{qname}' zaman aşımı ({self.tool_timeout}s)."
        except Exception as e:
            log.exception("Tool execution failed: %s", qname)
            return f"HATA: '{qname}' çalıştırılamadı: {e}"
