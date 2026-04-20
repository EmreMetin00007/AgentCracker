"""HackerAgent Orchestrator — OODA Loop motoru.

Kullanıcıdan görev alır, LLM'e gönderir, LLM tool çağırmak isterse bunları
MCP üzerinden yürütür ve sonucu tekrar LLM'e geri besler. Tool çağrısı
kalmayana kadar (veya iterasyon limiti aşılana kadar) döngü devam eder.

Faz-A eklenti özellikleri:
  • Streaming LLM yanıtı (delta callback üzerinden)
  • Bütçe / cost guardrail (BudgetTracker)
  • Session persistence (her turda autosave)
  • Scope enforcement (ToolRouter içinde)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from hackeragent.core.budget import BudgetTracker
from hackeragent.core.config import Config, get_config
from hackeragent.core.llm_client import LLMClient, LLMReply
from hackeragent.core.mcp_manager import MCPManager, tools_to_openai_schema
from hackeragent.core.prompt_engine import build_system_prompt
from hackeragent.core.scope import ScopeGuard
from hackeragent.core.session import Session
from hackeragent.core.tool_router import ToolRouter
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# CLI'dan enjekte edilen callback tipleri
ProgressCallback = Callable[[str, dict], None]
StreamCallback = Callable[[str], None]  # her token/delta için


@dataclass
class Orchestrator:
    """Tek bir session'ı yöneten sınıf. Conversation history'yi tutar."""

    config: Config = field(default_factory=get_config)
    llm: LLMClient = field(init=False)
    mcp: MCPManager = field(init=False)
    router: ToolRouter = field(init=False)
    scope: ScopeGuard = field(init=False)
    budget: BudgetTracker = field(init=False)
    session: Session = field(init=False)
    tools_schema: list[dict] = field(default_factory=list)
    progress: ProgressCallback | None = None
    stream_callback: StreamCallback | None = None
    streaming_enabled: bool = True
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
        self.budget = BudgetTracker(
            max_cost_usd=float(self.config.get("llm.max_session_cost_usd", 0.0) or 0.0),
        )
        scope_list = self.config.get("safety.scope", []) or []
        self.scope = ScopeGuard.from_list(
            list(scope_list),
            enabled=bool(self.config.get("safety.scope_enforcement", True)),
        )
        self.session = Session.new()
        self.streaming_enabled = bool(self.config.get("llm.streaming", True))

    # ─── Lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._started:
            return
        self._emit("boot", {"status": "mcp_starting"})
        self.mcp.start()
        self.router = ToolRouter(
            self.mcp,
            tool_timeout=self.config.get("llm.tool_timeout_seconds", 300),
            scope=self.scope,
        )
        self.tools_schema = tools_to_openai_schema(self.mcp.list_tools())
        self.session.messages = [{"role": "system", "content": build_system_prompt()}]
        self.session.save()
        self._started = True
        self._emit("ready", {
            "servers": self.mcp.active_servers(),
            "tool_count": len(self.tools_schema),
            "session_id": self.session.id,
            "budget": self.budget.max_cost_usd,
            "scope": self.scope.list_raw(),
        })

    def shutdown(self) -> None:
        if not self._started:
            return
        try:
            self.session.total_cost_usd = self.budget.total_cost_usd
            self.session.save()
            self.mcp.stop()
        finally:
            self._started = False

    # ─── Session resume ────────────────────────────────────────────────────
    def resume(self, session_id: str) -> None:
        """Mevcut session'ı yükle (start() öncesinde çağır)."""
        if self._started:
            raise RuntimeError("resume() start()'tan önce çağrılmalı")
        self.session = Session.load(session_id)
        # System prompt'u yeniden üret (rules/skills değişmiş olabilir)
        if self.session.messages and self.session.messages[0].get("role") == "system":
            self.session.messages[0] = {"role": "system", "content": build_system_prompt()}
        log.info("Session yüklendi: %s (%d mesaj)", self.session.id, len(self.session.messages))

    # ─── Public conversation ──────────────────────────────────────────────
    @property
    def messages(self) -> list[dict]:
        return self.session.messages

    def ask(self, user_input: str) -> str:
        """Kullanıcı mesajını işle, tool döngüsünü tamamla, nihai yanıtı döndür.

        Graceful budget handling:
          • Her LLM yanıtı önce session'a kaydedilir (para ödediğimiz çıktı kaybolmaz)
          • %90'da LLM'e "görevi bitir" ipucu enjekte edilir (tek sefer)
          • %100'e ulaşıldığında mevcut tur TAMAMLANIR (bekleyen tool_call'lar dahil),
            sonraki tur başlamaz → session tutarlı kalır, `--resume last` sorunsuz çalışır
        """
        if not self._started:
            self.start()

        self.session.messages.append({"role": "user", "content": user_input})
        if not self.session.target and _looks_like_target(user_input):
            self.session.target = _extract_target(user_input)

        max_iter = self.config.max_tool_iterations
        budget_stopped = False

        for iteration in range(max_iter):
            # Bütçe tamamen bittiyse ve önceki iterasyonda tool'lar da yürüdüyse,
            # burada tur başlatma.
            if self.budget.should_stop:
                budget_stopped = True
                break

            # Wrap-up ipucu: LLM'e "bütçe bitiyor" haberini ver (1 kez)
            if self.budget.wrap_up_hint_needed:
                self.session.messages.append({
                    "role": "system",
                    "content": (
                        "⚠️ BÜTÇE UYARISI: Session maliyet limitinin %90'ına "
                        "ulaştın. Bu turda görevi bitir: özet, raporla, bekleyen "
                        "kritik olmayan tool çağrılarını erteleme. Uzun çıktı üretme."
                    ),
                })
                self.budget.mark_wrap_up_sent()

            self._emit("llm_call", {"iter": iteration + 1})
            try:
                if self.streaming_enabled:
                    reply = self._stream_once()
                else:
                    reply = self.llm.chat(
                        messages=self.session.messages,
                        tools=self.tools_schema or None,
                    )
            except Exception as e:
                # LLM hatası: session'ı temizle (son kullanıcı mesajı düşsün mü?)
                # → Düşürmeyelim, kullanıcı --resume ile tekrar deneyebilsin.
                return f"HATA: LLM çağrısı başarısız: {e}"

            # 1) ÖNCE session'a yaz — ödediğimiz yanıt kayıtlı olsun
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
            self.session.messages.append(assistant_msg)

            # 2) SONRA bütçeyi kaydet
            if reply.cost_usd > 0:
                self.budget.register(self.config.model_orchestrator, reply.cost_usd)
            self.session.total_cost_usd = self.budget.total_cost_usd
            self.session.save()

            if not reply.has_tool_calls():
                # Text-only yanıt — görev tamamlandı
                if self.budget.should_stop:
                    return (
                        (reply.content or "(boş yanıt)")
                        + "\n\n🛑 Bütçe limiti doldu — sonraki tur iptal edildi.\n"
                        + self.budget.summary()
                        + f"\n\n▶ Devam: hackeragent --resume {self.session.id} "
                        + f"--budget {self.budget.max_cost_usd * 2:.2f}"
                    )
                return reply.content or "(LLM boş yanıt döndü)"

            # 3) Tool çağrılarını yürüt — bunlar MCP tarafında çalışır, LLM maliyeti yok.
            # Bütçe bitmiş olsa BİLE bu turdaki tool'ları tamamlamak istiyoruz
            # (yoksa yarım kalır, session tutarsız olur)
            for tc in reply.tool_calls:
                self._emit("tool_call", {"name": tc["name"], "args": tc["arguments"]})
                result = self.router.execute(tc)
                self.session.tool_calls_count += 1
                self._emit("tool_result", {"name": tc["name"], "chars": len(result)})
                self.session.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"] or "call_0",
                    "content": result[:12000],
                })
            self.session.save()

        if budget_stopped:
            return (
                "🛑 BÜTÇE DURDU — mevcut tur tamamlandı, yeni tur başlatılmadı.\n\n"
                + self.budget.summary()
                + f"\n\n▶ Devam: hackeragent --resume {self.session.id} "
                + f"--budget {self.budget.max_cost_usd * 2:.2f}\n"
                "   (Son tool sonuçları session'a kaydedildi, resume'da LLM bunları analiz edecek.)"
            )

        return (
            f"⚠️ Maksimum tool iterasyonu ({max_iter}) aşıldı. "
            f"Görev tam tamamlanamadı. Devam için: --resume {self.session.id}"
        )

    def _stream_once(self) -> LLMReply:
        """Streaming tek LLM turu — delta'ları stream_callback'e yollar."""
        final_reply = LLMReply()
        for event in self.llm.chat_stream(
            messages=self.session.messages,
            tools=self.tools_schema or None,
        ):
            if event["type"] == "delta":
                if self.stream_callback:
                    try:
                        self.stream_callback(event["content"])
                    except Exception:
                        pass
            elif event["type"] == "done":
                final_reply = event["reply"]
        return final_reply

    # ─── Helpers ──────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Yeni session başlat — conversation history'yi temizle."""
        self.session = Session.new()
        if self._started:
            self.session.messages = [{"role": "system", "content": build_system_prompt()}]
        self.budget = BudgetTracker(max_cost_usd=self.budget.max_cost_usd)
        self.session.save()

    def available_tools(self) -> list[tuple[str, str]]:
        return [(t.server, t.name) for t in self.mcp.list_tools()]

    def budget_summary(self) -> str:
        return self.budget.summary()

    def _emit(self, event: str, data: dict) -> None:
        log.debug("event=%s data=%s", event, data)
        if self.progress is not None:
            try:
                self.progress(event, data)
            except Exception:
                pass


# ─── Util ─────────────────────────────────────────────────────────────────
def _looks_like_target(text: str) -> bool:
    from hackeragent.core.scope import _IPV4_RE, _DOMAIN_RE
    return bool(_IPV4_RE.search(text) or _DOMAIN_RE.search(text))


def _extract_target(text: str) -> str:
    from hackeragent.core.scope import _IPV4_RE, _DOMAIN_RE
    m = _IPV4_RE.search(text) or _DOMAIN_RE.search(text)
    return m.group(0) if m else ""
