"""HackerAgent Orchestrator — OODA Loop motoru.

Kullanıcıdan görev alır, LLM'e gönderir, LLM tool çağırmak isterse bunları
MCP üzerinden yürütür ve sonucu tekrar LLM'e geri besler. Tool çağrısı
kalmayana kadar (veya iterasyon limiti aşılana kadar) döngü devam eder.

Faz-A eklenti özellikleri:
  • Streaming LLM yanıtı (delta callback üzerinden)
  • Bütçe / cost guardrail (BudgetTracker)
  • Session persistence (her turda autosave)
  • Scope enforcement (ToolRouter içinde)

Faz-B eklenti özellikleri:
  • 🧠 Akıllı model router (cheap/standard/premium tier seçimi)
  • 🔄 MCP auto-restart + circuit breaker (ToolRouter içinde)
  • 📚 RAG-enhanced context (her kullanıcı mesajından önce enjekte)
  • 🪞 Self-reflection loop (tool fail'de ucuz "düzelt" nudge'ı)

Faz-C eklenti özellikleri:
  • ♻️  Tool cache (aynı çağrıyı TTL süresince tekrar etmez)
  • 📦 Prompt compression (eski turları ucuz LLM ile özetler)
  • 🗡️  Attack graph enjeksiyonu (RAG enrichment içinde suggest_next_action)
  • 🗺️  Planner-Executor (kompleks görevleri adımlara böler)
  • ⚡ Paralel tool execution (güvenli tool'lar aynı anda koşar)
  • 👁️  Vision / multimodal (browser_screenshot → image LLM'e gider)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from hackeragent.core.budget import BudgetTracker
from hackeragent.core.circuit_breaker import CircuitBreaker
from hackeragent.core.compressor import Compressor
from hackeragent.core.config import Config, get_config
from hackeragent.core.llm_client import LLMClient, LLMReply
from hackeragent.core.mcp_manager import MCPManager, tools_to_openai_schema
from hackeragent.core.parallel_exec import execute_tool_calls
from hackeragent.core.planner import Plan, Planner
from hackeragent.core.prompt_engine import build_system_prompt
from hackeragent.core.rag_context import enrich_from_rag_and_memory
from hackeragent.core.router import ModelRouter, ModelTiers
from hackeragent.core.scope import ScopeGuard
from hackeragent.core.session import Session
from hackeragent.core.telemetry import SessionStats, TelemetryEmitter
from hackeragent.core.tool_cache import ToolCache
from hackeragent.core.tool_router import ToolRouter, _FAILURE_PREFIXES
from hackeragent.core.vision import model_supports_vision, to_multimodal_tool_message
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
    breaker: CircuitBreaker = field(init=False)
    tool_cache: ToolCache = field(init=False)
    compressor: Compressor = field(init=False)
    planner: Planner = field(init=False)
    model_router: ModelRouter = field(init=False)
    stats: SessionStats = field(init=False)
    session: Session = field(init=False)
    tools_schema: list[dict] = field(default_factory=list)
    progress: ProgressCallback | None = None
    stream_callback: StreamCallback | None = None
    streaming_enabled: bool = True
    rag_enrich_enabled: bool = True
    reflection_enabled: bool = True
    compression_enabled: bool = True
    planner_enabled: bool = True
    parallel_tools_enabled: bool = True
    vision_enabled: bool = True
    current_plan: Plan | None = None
    _started: bool = False
    _force_cheap_next: bool = False

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
        # Circuit breaker — ToolRouter ile paylaşılacak tek instance
        self.breaker = CircuitBreaker(
            failure_threshold=int(self.config.get("safety.circuit_failure_threshold", 3)),
            cooldown_seconds=int(self.config.get("safety.circuit_cooldown_seconds", 60)),
            restart_server_after=int(self.config.get("safety.circuit_restart_after", 5)),
        )
        # Tool cache — ToolRouter ile paylaşılacak
        self.tool_cache = ToolCache(
            enabled=bool(self.config.get("llm.tool_cache_enabled", True)),
        )
        # Akıllı model router — config'den tier'ları yükle
        tiers = ModelTiers.from_config(self.config.get("llm.models", {}) or {})
        self.model_router = ModelRouter(
            tiers=tiers,
            enabled=bool(self.config.get("llm.router_enabled", True)),
        )
        # Compressor — eski bağlamı ucuz LLM ile özetler
        self.compressor = Compressor(
            llm=self.llm,
            cheap_model=tiers.cheap,
            threshold_chars=int(self.config.get("llm.compression_threshold_chars", 40_000)),
            keep_tail=int(self.config.get("llm.compression_keep_tail", 10)),
            enabled=bool(self.config.get("llm.compression_enabled", True)),
        )
        # Planner — kompleks görevleri adımlara böler
        self.planner = Planner(
            llm=self.llm,
            cheap_model=tiers.cheap,
            enabled=bool(self.config.get("llm.planner_enabled", True)),
            max_steps=int(self.config.get("llm.planner_max_steps", 6)),
        )
        self.session = Session.new()
        self.streaming_enabled = bool(self.config.get("llm.streaming", True))
        self.rag_enrich_enabled = bool(self.config.get("rag.auto_enrich", True))
        self.reflection_enabled = bool(self.config.get("llm.self_reflection_enabled", True))
        self.compression_enabled = bool(self.config.get("llm.compression_enabled", True))
        self.planner_enabled = bool(self.config.get("llm.planner_enabled", True))
        self.parallel_tools_enabled = bool(self.config.get("safety.parallel_tool_execution", True))
        self.vision_enabled = bool(self.config.get("llm.vision_enabled", True))
        # Cost-aware telemetry — session stats
        self.stats = SessionStats(session_id=self.session.id)
        # ToolCache'e hit callback bağla — cache hit event'i stats'e kaydedilir
        self.tool_cache.on_hit = self.stats.record_cache_hit

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
            breaker=self.breaker,
            cache=self.tool_cache,
        )
        # Telemetry emitter — fire-and-forget MCP telemetry yazımı
        emitter = TelemetryEmitter(self.mcp.call_tool, server_name="telemetry")
        self.stats.attach_emitter(emitter)
        self.stats.session_id = self.session.id
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

        # 📚 RAG-enhanced context — user mesajından ÖNCE ilgili geçmiş kayıtları enjekte et
        if self.rag_enrich_enabled:
            try:
                ctx = enrich_from_rag_and_memory(
                    self.mcp,
                    user_input,
                    target=self.session.target or "",
                )
                if ctx:
                    self.session.messages.append({
                        "role": "system",
                        "content": ctx,
                    })
                    self._emit("rag_enriched", {"chars": len(ctx)})
            except Exception as e:
                log.debug("RAG enrich atlandı: %s", e)

        self.session.messages.append({"role": "user", "content": user_input})
        if not self.session.target and _looks_like_target(user_input):
            self.session.target = _extract_target(user_input)

        # 🗺️ Planner — kompleks görev ise adımlara böl ve system msg olarak enjekte et
        if self.planner_enabled and self.current_plan is None:
            try:
                available_tools = [t.qualified_name for t in self.mcp.list_tools()]
                plan = self.planner.plan(user_input, available_tools=available_tools)
                if plan and not plan.is_empty():
                    self.current_plan = plan
                    plan_msg = plan.to_system_message()
                    self.session.messages.append({"role": "system", "content": plan_msg})
                    self._emit("planner", {"steps": len(plan.steps)})
                    # 💰 Cost-aware: plan LLM maliyetini ve tahmini tasarrufu kaydet
                    self.stats.record_planner(
                        step_count=len(plan.steps),
                        llm_cost_usd=plan.llm_cost_usd,
                    )
                    # Plan maliyetini bütçeye de ekle
                    if plan.llm_cost_usd > 0:
                        self.budget.register(self.model_router.tiers.cheap, plan.llm_cost_usd)
            except Exception as e:
                log.debug("Planner atlandı: %s", e)

        max_iter = self.config.max_tool_iterations
        budget_stopped = False

        for iteration in range(max_iter):
            # Bütçe tamamen bittiyse ve önceki iterasyonda tool'lar da yürüdüyse,
            # burada tur başlatma.
            if self.budget.should_stop:
                budget_stopped = True
                break

            # 📦 Prompt compression — bağlam eşiği aşıldıysa ortadaki mesajları sıkıştır
            if self.compression_enabled and self.compressor.should_compress(self.session.messages):
                try:
                    cr = self.compressor.compress(self.session.messages)
                    if cr.compressed:
                        self._emit("compression", {
                            "removed": cr.removed_count,
                            "before": cr.before_chars,
                            "after": cr.after_chars,
                        })
                        # 💰 Cost-aware: sıkıştırma olayını kaydet
                        self.stats.record_compression(
                            removed_count=cr.removed_count,
                            before_chars=cr.before_chars,
                            after_chars=cr.after_chars,
                            llm_cost_usd=cr.llm_cost_usd,
                        )
                        # Sıkıştırma maliyetini bütçeye ekle
                        if cr.llm_cost_usd > 0:
                            self.budget.register(self.model_router.tiers.cheap, cr.llm_cost_usd)
                        self.session.save()
                except Exception as e:
                    log.warning("Compression hatası (atlandı): %s", e)

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

            # 🧠 Akıllı model router — bu tur için en uygun modeli seç
            if self._force_cheap_next:
                picked_model = self.model_router.tiers.cheap
                self._force_cheap_next = False
                log.debug("Reflection nudge → cheap tier zorlandı: %s", picked_model)
            else:
                picked_model = self.model_router.pick(
                    messages=self.session.messages,
                    iteration=iteration,
                    has_tools=bool(self.tools_schema),
                )
            self._emit("llm_call", {"iter": iteration + 1, "model": picked_model})
            try:
                if self.streaming_enabled:
                    reply = self._stream_once(model=picked_model)
                else:
                    reply = self.llm.chat(
                        messages=self.session.messages,
                        tools=self.tools_schema or None,
                        model=picked_model,
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

            # 2) SONRA bütçeyi kaydet — gerçek kullanılan modelle birlikte
            if reply.cost_usd > 0:
                self.budget.register(picked_model, reply.cost_usd)
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
            any_failed = False
            failed_tools: list[str] = []
            use_vision = self.vision_enabled and model_supports_vision(picked_model)

            def _progress(tc, result, _f=failed_tools):
                self._emit("tool_result", {"name": tc.get("name", "?"), "chars": len(result)})

            # ⚡ Paralel yürütme — güvenli tool'lar aynı anda koşar
            for tc in reply.tool_calls:
                self._emit("tool_call", {"name": tc["name"], "args": tc["arguments"]})
            tool_results = execute_tool_calls(
                reply.tool_calls,
                executor=self.router.execute,
                max_workers=int(self.config.get("safety.parallel_max_workers", 5)),
                parallel_enabled=self.parallel_tools_enabled,
                on_progress=_progress,
            )

            for tc, result in tool_results:
                self.session.tool_calls_count += 1
                # 👁️ Vision: tool sonucu base64 image içeriyorsa multimodal format'a çevir
                trimmed_result = result[:200000] if use_vision else result[:12000]
                tool_msg = to_multimodal_tool_message(
                    tool_call_id=tc.get("id") or "call_0",
                    raw_result=trimmed_result,
                    enabled=use_vision,
                )
                # Eğer multimodal değilse content'i 12k'ya kes
                if isinstance(tool_msg.get("content"), str) and len(tool_msg["content"]) > 12000:
                    tool_msg["content"] = tool_msg["content"][:12000]
                self.session.messages.append(tool_msg)

                # 🪞 Self-reflection detection — fail prefix'i ile başlıyorsa işaretle
                trimmed = (result or "").lstrip()
                if any(trimmed.startswith(p) for p in _FAILURE_PREFIXES):
                    any_failed = True
                    failed_tools.append(tc.get("name", "?"))

            # 🪞 Self-reflection nudge — tool başarısız olduysa bir sonraki turu ucuza al
            if any_failed and self.reflection_enabled:
                self.session.messages.append({
                    "role": "system",
                    "content": (
                        f"🔄 REFLECT: Son tool çağrı(lar)ın başarısız oldu "
                        f"({', '.join(failed_tools[:3])}). "
                        "Hatayı kısaca analiz et ve farklı bir argüman ya da "
                        "farklı bir araç dene. Aynı çağrıyı aynı argümanlarla tekrarlama. "
                        "Kısa tut — uzun açıklamaya gerek yok."
                    ),
                })
                self._force_cheap_next = True
                self._emit("reflection", {"failed_tools": failed_tools})
                # 💰 Cost-aware
                self.stats.record_reflection(failed_tools)

            # 💰 Parallel event — birden fazla tool aynı anda yürüdüyse kaydet
            if self.parallel_tools_enabled and len(reply.tool_calls) > 1:
                self.stats.record_parallel(
                    parallel_count=len(reply.tool_calls),
                    total_calls=len(reply.tool_calls),
                )
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

    def _stream_once(self, model: str | None = None) -> LLMReply:
        """Streaming tek LLM turu — delta'ları stream_callback'e yollar."""
        final_reply = LLMReply()
        for event in self.llm.chat_stream(
            messages=self.session.messages,
            tools=self.tools_schema or None,
            model=model,
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
        self.current_plan = None
        self.tool_cache.invalidate()  # yeni session → cache'i sıfırla
        self._force_cheap_next = False
        # Stats'ı da sıfırla — yeni session yeni raporlanacak
        old_emitter = self.stats._emitter
        self.stats = SessionStats(session_id=self.session.id)
        if old_emitter:
            self.stats.attach_emitter(old_emitter)
        self.tool_cache.on_hit = self.stats.record_cache_hit
        self.session.save()

    def available_tools(self) -> list[tuple[str, str]]:
        return [(t.server, t.name) for t in self.mcp.list_tools()]

    def budget_summary(self) -> str:
        return self.budget.summary()

    def cost_report(self) -> str:
        """Cost-aware session raporu — compression/cache/planner tasarruflarını özetler."""
        return self.stats.render_report(
            total_llm_cost_usd=self.budget.total_cost_usd,
            total_llm_calls=self.budget.call_count,
        )

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
