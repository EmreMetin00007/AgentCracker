"""MCP Manager — stdio transport üzerinden MCP server'ları başlatır ve kontrol eder.

MCP Python SDK'nın client ClientSession / stdio_client yardımcılarını kullanır.
Her server ayrı bir subprocess'tir; tool listeleri ve çağrıları asyncio ile yönetilir.

Senkron sarmalayıcı (`MCPManager`) REPL'den kolayca kullanılabilsin diye
asyncio event loop'u arka planda tutar.
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class ToolInfo:
    """Tek bir MCP tool'unun metadata'sı."""

    server: str
    name: str
    description: str
    input_schema: dict

    @property
    def qualified_name(self) -> str:
        """LLM'e sunulan benzersiz ad: '<server>__<tool>'."""
        return f"{self.server}__{self.name}"


class _Connection:
    """Tek bir MCP server'a canlı bağlantı (ClientSession)."""

    def __init__(self, name: str, params: StdioServerParameters):
        self.name = name
        self.params = params
        self.session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None
        self.tools: list[ToolInfo] = []

    async def start(self) -> None:
        self._stack = AsyncExitStack()
        try:
            stdio = await self._stack.enter_async_context(stdio_client(self.params))
            read, write = stdio
            self.session = await self._stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            tools_resp = await self.session.list_tools()
            self.tools = [
                ToolInfo(
                    server=self.name,
                    name=t.name,
                    description=(t.description or "").strip(),
                    input_schema=dict(t.inputSchema or {"type": "object", "properties": {}}),
                )
                for t in tools_resp.tools
            ]
            log.info("MCP server '%s' hazır (%d tool)", self.name, len(self.tools))
        except Exception as e:
            log.error("MCP server '%s' başlatılamadı: %s", self.name, e)
            await self.stop()
            raise

    async def call(self, tool_name: str, arguments: dict) -> str:
        if self.session is None:
            raise RuntimeError(f"MCP server '{self.name}' bağlı değil.")
        result = await self.session.call_tool(tool_name, arguments or {})
        # result.content: list of TextContent/ImageContent
        parts: list[str] = []
        for item in result.content or []:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(str(item))
        return "\n".join(parts) if parts else "(boş sonuç)"

    async def stop(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception as e:  # pragma: no cover
                log.debug("MCP '%s' stop hatası: %s", self.name, e)
        self._stack = None
        self.session = None


class MCPManager:
    """Senkron sarmalayıcı — arka planda kendi asyncio event loop'u çalıştırır."""

    def __init__(self, servers_config: dict[str, dict]):
        self.servers_config = servers_config
        self._connections: dict[str, _Connection] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    # ─── Loop lifecycle ───────────────────────────────────────────────────
    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="mcp-loop")
        self._thread.start()
        self._ready.wait(timeout=5)
        # Tüm server'ları paralel başlat
        self._run(self._start_all())

    def stop(self) -> None:
        if self._loop is None:
            return
        try:
            self._run(self._stop_all(), timeout=10)
        except Exception as e:
            log.debug("MCP stop hatası: %s", e)
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    # ─── Internal coroutines ──────────────────────────────────────────────
    async def _start_all(self) -> None:
        for name, cfg in self.servers_config.items():
            if not cfg.get("enabled", True):
                continue
            params = StdioServerParameters(
                command=cfg.get("command", "python3"),
                args=list(cfg.get("args", [])),
                env={**cfg.get("env", {})} if cfg.get("env") else None,
            )
            conn = _Connection(name, params)
            try:
                await conn.start()
                self._connections[name] = conn
            except Exception as e:
                log.warning("MCP server '%s' atlanıyor: %s", name, e)

    async def _stop_all(self) -> None:
        for conn in list(self._connections.values()):
            await conn.stop()
        self._connections.clear()

    async def _call(self, server: str, tool: str, arguments: dict) -> str:
        conn = self._connections.get(server)
        if conn is None:
            return f"HATA: MCP server '{server}' bulunamadı / başlatılamadı."
        try:
            return await conn.call(tool, arguments)
        except Exception as e:
            log.exception("MCP call failed: %s.%s", server, tool)
            return f"HATA: {server}.{tool} çağrısı başarısız: {e}"

    # ─── Sync facade ──────────────────────────────────────────────────────
    def _run(self, coro, timeout: int | None = None):
        assert self._loop is not None, "MCPManager.start() önce çağrılmalı"
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    def list_tools(self) -> list[ToolInfo]:
        all_tools: list[ToolInfo] = []
        for conn in self._connections.values():
            all_tools.extend(conn.tools)
        return all_tools

    def active_servers(self) -> list[str]:
        return list(self._connections.keys())

    def call_tool(self, server: str, tool: str, arguments: dict, timeout: int = 300) -> str:
        return self._run(self._call(server, tool, arguments or {}), timeout=timeout)


# ─── OpenAI-schema adapter ───────────────────────────────────────────────────
def tools_to_openai_schema(tools: list[ToolInfo]) -> list[dict]:
    """MCP tool listesini OpenAI function-calling şemasına çevir."""
    out: list[dict] = []
    for t in tools:
        params = t.input_schema or {"type": "object", "properties": {}}
        if "type" not in params:
            params = {"type": "object", "properties": params}
        out.append({
            "type": "function",
            "function": {
                "name": t.qualified_name,
                "description": (t.description or t.name)[:1024],
                "parameters": params,
            },
        })
    return out
