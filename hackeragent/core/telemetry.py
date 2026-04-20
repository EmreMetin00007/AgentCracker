"""Cost-aware telemetry — in-memory session stats + MCP fire-and-forget emitter.

Her optimizasyon olayı (compression, cache hit, plan, reflection, parallel):
  1. `SessionStats`'e eklenir (anlık kayıt)
  2. Opsiyonel: `mcp-telemetry.log_savings_event` ile kalıcı SQLite'a yazılır
     (fire-and-forget — başarısızsa sessizce atla)

Session sonunda `SessionStats.render_report()` ile kullanıcıya
"bu görev $X maliyetle tamamlandı, ~$Y tasarruf, net fayda $Z" özeti.

Tasarruf heuristikleri:
  • cache_hit: saved_tokens ≈ result_chars / 4, saved_usd ≈ saved_tokens × standard_model_output_price
  • compression: saved_tokens = (before - after) / 4; saved_usd = saved_tokens × input_price × remaining_iters
  • planner: ekstra overhead; tasarruf = plan sayesinde ortalama 2-4 iterasyon daha az (empirical)
  • reflection: ekstra nudge maliyeti; tasarruf = aksi halde aynı tool'un tekrar denenmesi
  • parallel: tasarruf = wall-clock time, $ olarak sıfır (LLM maliyeti değişmez)
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# Tahmini model maliyetleri — telemetry server'ınki ile senkron tut
# Bu değerler sadece "tasarruf tahmini" için kullanılır, gerçek maliyet
# OpenRouter usage.cost alanından gelir.
_FALLBACK_INPUT_USD_PER_1M = 0.50
_FALLBACK_OUTPUT_USD_PER_1M = 1.50

# Karakter → token yaklaşık dönüşümü
CHARS_PER_TOKEN = 4


def chars_to_tokens(chars: int) -> int:
    return max(0, chars // CHARS_PER_TOKEN)


@dataclass
class _EventAgg:
    count: int = 0
    cost_usd: float = 0.0
    saved_tokens: int = 0
    saved_usd: float = 0.0

    def add(self, cost_usd: float = 0.0, saved_tokens: int = 0, saved_usd: float = 0.0) -> None:
        self.count += 1
        self.cost_usd += cost_usd
        self.saved_tokens += saved_tokens
        self.saved_usd += saved_usd


@dataclass
class SessionStats:
    """Session boyunca optimizasyon olaylarını biriktirir."""

    session_id: str = ""
    compression: _EventAgg = field(default_factory=_EventAgg)
    cache_hit: _EventAgg = field(default_factory=_EventAgg)
    planner: _EventAgg = field(default_factory=_EventAgg)
    reflection: _EventAgg = field(default_factory=_EventAgg)
    parallel: _EventAgg = field(default_factory=_EventAgg)
    _emitter: "TelemetryEmitter | None" = None

    def attach_emitter(self, emitter: "TelemetryEmitter") -> None:
        self._emitter = emitter

    def record_compression(self, removed_count: int, before_chars: int, after_chars: int,
                           llm_cost_usd: float = 0.0) -> None:
        saved_chars = max(0, before_chars - after_chars)
        saved_tokens = chars_to_tokens(saved_chars)
        # Tasarruf: bu token'lar sonraki her turda tekrar tekrar promptlanmayacaktı
        # Ortalama 3 turda kullanılacağını varsay
        saved_usd = (saved_tokens / 1_000_000) * _FALLBACK_INPUT_USD_PER_1M * 3
        self.compression.add(cost_usd=llm_cost_usd, saved_tokens=saved_tokens, saved_usd=saved_usd)
        self._fire_event("compression", {
            "removed_msgs": removed_count,
            "before_chars": before_chars,
            "after_chars": after_chars,
        }, cost_usd=llm_cost_usd, saved_tokens=saved_tokens, saved_usd=saved_usd)

    def record_cache_hit(self, qname: str, result_chars: int) -> None:
        saved_tokens = chars_to_tokens(result_chars)
        # Cache hit, MCP çağrı maliyetinin yerine geçmez (MCP zaten ücretsiz);
        # ama tool_result'ın LLM'e context olarak tekrar promptlanmasını kurtarır.
        saved_usd = (saved_tokens / 1_000_000) * _FALLBACK_INPUT_USD_PER_1M
        self.cache_hit.add(saved_tokens=saved_tokens, saved_usd=saved_usd)
        self._fire_event("cache_hit", {"qname": qname, "result_chars": result_chars},
                         saved_tokens=saved_tokens, saved_usd=saved_usd)

    def record_planner(self, step_count: int, llm_cost_usd: float = 0.0) -> None:
        # Empirical: iyi plan ~2 fazla tool iterasyonu önler
        # Bir iterasyon ~3000 token input + 500 output tüket
        avoided_tokens = 2 * 3500
        saved_usd = (avoided_tokens / 1_000_000) * _FALLBACK_INPUT_USD_PER_1M
        self.planner.add(cost_usd=llm_cost_usd, saved_tokens=avoided_tokens, saved_usd=saved_usd)
        self._fire_event("planner", {"steps": step_count},
                         cost_usd=llm_cost_usd, saved_tokens=avoided_tokens, saved_usd=saved_usd)

    def record_reflection(self, failed_tools: list[str]) -> None:
        # Reflection nudge 1 fazla ucuz LLM turu ekler ama aynı hatayı tekrarlamayı önler
        # Kötü tool iterasyonu ~3000 token → bunu önleyerek net pozitif
        avoided_tokens = 3000
        saved_usd = (avoided_tokens / 1_000_000) * _FALLBACK_INPUT_USD_PER_1M
        self.reflection.add(saved_tokens=avoided_tokens, saved_usd=saved_usd)
        self._fire_event("reflection", {"failed_tools": failed_tools[:3]},
                         saved_tokens=avoided_tokens, saved_usd=saved_usd)

    def record_parallel(self, parallel_count: int, total_calls: int) -> None:
        """Paralel yürütme — wall-clock tasarrufu ama $ değil."""
        self.parallel.add()
        self._fire_event("parallel", {"parallel": parallel_count, "total": total_calls})

    # ─── Reporting ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "compression": self.compression.__dict__,
            "cache_hit": self.cache_hit.__dict__,
            "planner": self.planner.__dict__,
            "reflection": self.reflection.__dict__,
            "parallel": self.parallel.__dict__,
        }

    def render_report(self, total_llm_cost_usd: float = 0.0, total_llm_calls: int = 0) -> str:
        """Kullanıcıya gösterilecek kısa özet metni."""
        total_overhead = (
            self.compression.cost_usd + self.planner.cost_usd
        )
        total_saved = (
            self.compression.saved_usd
            + self.cache_hit.saved_usd
            + self.planner.saved_usd
            + self.reflection.saved_usd
        )
        net = total_saved - total_overhead

        lines = [
            "╭─────────────────────────────────────────────────────╮",
            "│  💰  Cost-Aware Session Report                      │",
            "╰─────────────────────────────────────────────────────╯",
        ]
        if total_llm_calls:
            lines.append(f"🧠 LLM: {total_llm_calls} çağrı, ${total_llm_cost_usd:.4f}")

        if self.compression.count:
            pct_saved = (
                100 * self.compression.saved_tokens
                / max(1, self.compression.saved_tokens + 10_000)
            )
            lines.append(
                f"📦 Compression: {self.compression.count} sıkıştırma, "
                f"~{self.compression.saved_tokens:,} token kurtardı "
                f"(~%{pct_saved:.0f} context tasarrufu), "
                f"overhead ${self.compression.cost_usd:.4f}"
            )
        if self.cache_hit.count:
            lines.append(
                f"♻️  Cache: {self.cache_hit.count} hit, "
                f"~{self.cache_hit.saved_tokens:,} token context tasarrufu "
                f"(~${self.cache_hit.saved_usd:.4f})"
            )
        if self.planner.count:
            lines.append(
                f"🗺️  Plan: {self.planner.count} üretildi, "
                f"~{self.planner.saved_tokens:,} token iterasyon tasarrufu, "
                f"overhead ${self.planner.cost_usd:.4f}"
            )
        if self.reflection.count:
            lines.append(
                f"🪞 Reflection: {self.reflection.count} nudge, "
                f"~{self.reflection.saved_tokens:,} boşa iterasyon önlendi"
            )
        if self.parallel.count:
            lines.append(f"⚡ Parallel: {self.parallel.count} tur paralel tool yürüttü (wall-clock tasarrufu)")

        if (self.compression.count or self.cache_hit.count or self.planner.count
                or self.reflection.count):
            lines.append("─" * 55)
            lines.append(
                f"Overhead ${total_overhead:.4f}   Tasarruf ~${total_saved:.4f}   "
                + (f"Net +${net:.4f} ✅" if net >= 0 else f"Net ${net:.4f} ⚠️")
            )
        else:
            lines.append("(Henüz optimizasyon olayı tetiklenmedi)")

        return "\n".join(lines)

    def _fire_event(self, event_type: str, details: dict, cost_usd: float = 0.0,
                    saved_tokens: int = 0, saved_usd: float = 0.0) -> None:
        if self._emitter is None:
            return
        self._emitter.emit(
            session_id=self.session_id,
            event_type=event_type,
            details=details,
            cost_usd=cost_usd,
            saved_tokens=saved_tokens,
            saved_usd=saved_usd,
        )


class TelemetryEmitter:
    """Fire-and-forget event emitter — MCP telemetry server'a arka planda yazar."""

    def __init__(self, mcp_call_fn, server_name: str = "telemetry", timeout: int = 5):
        """
        Args:
          mcp_call_fn: (server, tool, args, timeout) → str  (genelde MCPManager.call_tool)
          server_name: Telemetry MCP server adı
        """
        self._call = mcp_call_fn
        self.server = server_name
        self.timeout = timeout

    def emit(
        self,
        session_id: str,
        event_type: str,
        details: dict,
        cost_usd: float = 0.0,
        saved_tokens: int = 0,
        saved_usd: float = 0.0,
    ) -> None:
        """Arka planda telemetry'ye event gönder. Exception YUTULUR."""
        def _send():
            try:
                self._call(
                    self.server,
                    "log_savings_event",
                    {
                        "session_id": session_id,
                        "event_type": event_type,
                        "details_json": json.dumps(details, ensure_ascii=False, default=str),
                        "cost_usd": float(cost_usd),
                        "saved_tokens": int(saved_tokens),
                        "saved_usd": float(saved_usd),
                    },
                    timeout=self.timeout,
                )
            except Exception as e:
                log.debug("Telemetry emit failed (ignored): %s", e)

        # Fire-and-forget — LLM akışını bloklama
        threading.Thread(target=_send, daemon=True, name="tele-emit").start()
