"""Budget / cost guardrail.

OpenRouter her LLM yanıtında `usage.cost` alanı döner (USD). Bu modülu
kümülatif maliyeti toplar; limit aşıldığında `should_stop` bayrağı
true olur. Orchestrator bu bayrağı kontrol ederek mevcut turu
NAZİKÇE bitirir (LLM yanıtı ve tool çağrıları kaybolmaz, session tutarlı kalır).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


class BudgetExceeded(RuntimeError):
    """Bütçe limitine ulaşıldığında fırlatılır (istek bazında değil, döngü bazında)."""


@dataclass
class BudgetTracker:
    """Session boyunca LLM maliyetini takip eden sayaç.

    3 aşamalı davranış:
      • %75 — bir kez uyarı log'u
      • %90 — `wrap_up_hint` true olur (LLM'e "görevi bitir" ipucu enjekte)
      • %100 — `should_stop` true olur (mevcut tur biter, sonraki tur başlamaz)
    """

    max_cost_usd: float = 0.0  # 0 = sınırsız
    warn_threshold_pct: float = 0.75
    wrap_up_threshold_pct: float = 0.90
    total_cost_usd: float = 0.0
    call_count: int = 0
    _warned: bool = False
    _wrap_up_sent: bool = False
    per_model: dict = field(default_factory=dict)

    def register(self, model: str, cost_usd: float) -> None:
        self.total_cost_usd += max(cost_usd, 0.0)
        self.call_count += 1
        self.per_model[model] = self.per_model.get(model, 0.0) + max(cost_usd, 0.0)

        if self.max_cost_usd <= 0:
            return

        # %75 uyarısı (bir kez)
        if (
            not self._warned
            and self.total_cost_usd >= self.max_cost_usd * self.warn_threshold_pct
        ):
            self._warned = True
            log.warning(
                "💰 Bütçe uyarısı: $%.4f / $%.2f kullanıldı (%d%%)",
                self.total_cost_usd,
                self.max_cost_usd,
                int(100 * self.total_cost_usd / self.max_cost_usd),
            )

    @property
    def should_wrap_up(self) -> bool:
        """%90 aşıldı mı? LLM'e sonlandırma talimatı verilsin."""
        if self.max_cost_usd <= 0:
            return False
        return self.total_cost_usd >= self.max_cost_usd * self.wrap_up_threshold_pct

    @property
    def wrap_up_hint_needed(self) -> bool:
        """Bu ipucu daha önce enjekte edildi mi?"""
        return self.should_wrap_up and not self._wrap_up_sent

    def mark_wrap_up_sent(self) -> None:
        self._wrap_up_sent = True

    @property
    def should_stop(self) -> bool:
        """%100 aşıldı mı? Mevcut tur bitsin, yeni tur başlamasın."""
        if self.max_cost_usd <= 0:
            return False
        return self.total_cost_usd >= self.max_cost_usd

    def raise_if_exceeded(self) -> None:
        """Sert kontrol noktası — orchestrator sadece güvenli yerlerde çağırır."""
        if self.should_stop:
            raise BudgetExceeded(
                f"Maksimum session maliyeti aşıldı: "
                f"${self.total_cost_usd:.4f} >= ${self.max_cost_usd:.2f}. "
                f"Toplam {self.call_count} LLM çağrısı yapıldı. "
                f"Devam için: hackeragent --resume last --budget {self.max_cost_usd * 2:.2f}"
            )

    def summary(self) -> str:
        lines = [
            f"💰 Toplam maliyet: ${self.total_cost_usd:.4f} ({self.call_count} çağrı)",
        ]
        for model, cost in sorted(self.per_model.items(), key=lambda x: -x[1]):
            lines.append(f"   └ {model}: ${cost:.4f}")
        if self.max_cost_usd > 0:
            pct = 100 * self.total_cost_usd / self.max_cost_usd
            lines.append(f"   Bütçe kullanımı: %{pct:.1f} / ${self.max_cost_usd:.2f}")
        return "\n".join(lines)
