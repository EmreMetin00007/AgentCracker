"""Budget / cost guardrail.

OpenRouter her LLM yanıtında `usage.cost` alanı döner (USD). Bu modülu
kümülatif maliyeti toplar ve config'deki limit aşılırsa `BudgetExceeded`
istisnası fırlatır. Orchestrator ona göre durur.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


class BudgetExceeded(RuntimeError):
    """Bütçe limitine ulaşıldığında fırlatılır."""


@dataclass
class BudgetTracker:
    """Session boyunca LLM maliyetini takip eden küçük sayaç."""

    max_cost_usd: float = 0.0  # 0 = sınırsız
    warn_threshold_pct: float = 0.75
    total_cost_usd: float = 0.0
    call_count: int = 0
    _warned: bool = False
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

        # Sert limit
        if self.total_cost_usd >= self.max_cost_usd:
            raise BudgetExceeded(
                f"Maksimum session maliyeti aşıldı: "
                f"${self.total_cost_usd:.4f} >= ${self.max_cost_usd:.2f}. "
                f"Toplam {self.call_count} LLM çağrısı yapıldı. "
                f"Limiti artırmak için --budget flag'i veya config.yaml → llm.max_session_cost_usd."
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
