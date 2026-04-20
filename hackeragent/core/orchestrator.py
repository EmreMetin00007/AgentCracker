"""HackerAgent Orchestrator — OODA Loop motoru.

Kullanıcıdan görev alır, LLM'e gönderir, LLM tool çağırmak isterse bunları
MCP üzerinden yürütür ve sonucu tekrar LLM'e geri besler. Tool çağrısı
kalmayana kadar (veya iterasyon limiti aşılana kadar) döngü devam eder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from hackeragent.core.config import Config, get_config
from hackeragent.core.llm_client import LLMClient, LLMReply
from hackeragent.core.mcp_manager import MCPManager, tools_to_openai_schema
from hackeragent.core.prompt_engine import build_system_prompt
from hackeragent.core.tool_router import ToolRouter
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# İsteğe bağlı streaming callback — CLI'dan enjekte edilir (tool çalışırken UX)
ProgressCallback = Callable[[str, dict], None]


@dataclass
class Orchestrator:
    """Tek bir session'ı yöneten sınıf. Conversation history'yi tutar."""

    config: Config = field(default_factory=get_config)
    llm: LLMClient = field(init=False)
    mcp: MCPManager = field(init=False)
    router: ToolRouter = field(init=False)
    messages: list[dict] = field(default_factory=list)
    tools_schema: list[dict] = field(default_factory=list)
    progress: ProgressCallback | None = None
    _started: bool = False

    def __post_init__(self) -> None:
        self.llm = LLMClient(
            api_key=self.config.openrouter_api_key,
            model=self.config.model_orchestrator,
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        self.mcp = MCPManager(self.config.mcp_servers)

    # ─── Lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._started:
            return
        self._emit("boot", {"status": "mcp_starting"})
        self.mcp.start()
        self.router = ToolRouter(
            self.mcp,
            tool_timeout=self.config.get("llm.tool_timeout_seconds", 300),
        )
        self.tools_schema = tools_to_openai_schema(self.mcp.list_tools())
        self.messages = [{"role": "system", "content": build_system_prompt()}]
        self._started = True
        self._emit("ready", {
            "servers": self.mcp.active_servers(),
            "tool_count": len(self.tools_schema),
        })

    def shutdown(self) -> None:
        if not self._started:
            return
        try:
            self.mcp.stop()
        finally:
            self._started = False

    # ─── Public API ───────────────────────────────────────────────────────
    def ask(self, user_input: str) -> str:
        """Kullanıcı mesajını işle, tool döngüsünü tamamla, nihai yanıtı döndür."""
        if not self._started:
            self.start()

        self.messages.append({"role": "user", "content": user_input})
        max_iter = self.config.max_tool_iterations

        for iteration in range(max_iter):
            self._emit("llm_call", {"iter": iteration + 1})
            reply: LLMReply = self.llm.chat(
                messages=self.messages,
                tools=self.tools_schema or None,
            )

            # LLM mesajını geçmişe ekle (tool_calls dahil)
            assistant_msg: dict = {"role": "assistant", "content": reply.content or ""}
            if reply.has_tool_calls():
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"] or f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                        },
                    }
                    for i, tc in enumerate(reply.tool_calls)
                ]
            self.messages.append(assistant_msg)

            if not reply.has_tool_calls():
                return reply.content or "(LLM boş yanıt döndü)"

            # Tool çağrılarını sıralı yürüt → sonuçları LLM'e geri besle
            for tc in reply.tool_calls:
                self._emit("tool_call", {"name": tc["name"], "args": tc["arguments"]})
                result = self.router.execute(tc)
                self._emit("tool_result", {"name": tc["name"], "chars": len(result)})
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"] or "call_0",
                    "content": result[:12000],  # çok büyük sonuçları kırp
                })

        return (
            f"⚠️ Maksimum tool iterasyonu ({max_iter}) aşıldı. Görev tam tamamlanamadı."
        )

    # ─── Helpers ──────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Yeni session başlat — conversation history'yi temizle."""
        if self._started:
            self.messages = [{"role": "system", "content": build_system_prompt()}]
        else:
            self.messages = []

    def available_tools(self) -> list[tuple[str, str]]:
        return [(t.server, t.name) for t in self.mcp.list_tools()]

    def _emit(self, event: str, data: dict) -> None:
        log.debug("event=%s data=%s", event, data)
        if self.progress is not None:
            try:
                self.progress(event, data)
            except Exception:
                pass
