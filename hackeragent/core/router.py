"""Akıllı model router.

Her LLM çağrısı için en uygun modeli seçer (maliyet optimizasyonu):

  cheap     → kısa girdi, ilk tur, basit sohbet  (~$0.20/1M token)
  standard  → tool analizi, orkestrasyon          (~$0.50/1M token)
  premium   → exploit kodu, rapor üretimi         (~$2.00/1M token)

Kural tabanlı (ücretsiz, deterministik, hızlı). LLM-tabanlı classifier
eklenebilir ama maliyeti düşüyor → ROI yok.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# Tier tespitinde kullanılan anahtar kelimeler (Türkçe + İngilizce)
_PREMIUM_KEYWORDS = re.compile(
    r"\b(exploit|payload|poc|bypass|shellcode|rop|gadget|canary|rce|"
    r"buffer overflow|format string|heap|use.after.free|"
    r"rapor(?:la|umu)?|report|writeup|"
    r"hermes|generate_exploit_poc)\b",
    re.IGNORECASE,
)

_CHEAP_KEYWORDS = re.compile(
    r"\b(merhaba|selam|teşekkür|thanks|hello|hi|ok|tamam|evet|hayır|"
    r"yes|no|/help|yardım|list|listele)\b",
    re.IGNORECASE,
)


@dataclass
class ModelTiers:
    cheap: str = "qwen/qwen3.6-plus"  # Aynı model fallback olarak
    standard: str = "qwen/qwen3.6-plus"
    premium: str = "qwen/qwen3.6-plus"

    @classmethod
    def from_config(cls, models_config: dict) -> "ModelTiers":
        """config.yaml llm.models bloğundan tier'ları parse et."""
        standard = models_config.get("orchestrator", "qwen/qwen3.6-plus")
        return cls(
            cheap=models_config.get("cheap", standard),
            standard=standard,
            premium=models_config.get("premium") or models_config.get("exploit_gen", standard),
        )


class ModelRouter:
    """Heuristik model seçici."""

    def __init__(self, tiers: ModelTiers, enabled: bool = True):
        self.tiers = tiers
        self.enabled = enabled

    def pick(
        self,
        messages: list[dict],
        iteration: int = 0,
        has_tools: bool = True,
    ) -> str:
        """Mevcut conversation state'e göre model seç."""
        if not self.enabled:
            return self.tiers.standard

        # Son kullanıcı mesajı
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user" and m.get("content")),
            "",
        )
        # Son tool sonucu
        last_tool = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "tool"),
            "",
        )

        text_to_classify = f"{last_user}\n{last_tool[:500]}"
        total_len = sum(len(m.get("content") or "") for m in messages[-6:])

        # 1) Premium tetikleyiciler (exploit, rapor, uzun kod üretimi)
        if _PREMIUM_KEYWORDS.search(text_to_classify):
            return self.tiers.premium

        # 2) Bağlam çok büyük (6+ tool sonucu) → standard (premium pahalı olur)
        if total_len > 8000:
            return self.tiers.standard

        # 3) İlk tur + kısa girdi + tool sonucu yok → cheap
        if iteration == 0 and len(last_user) < 120 and not last_tool:
            if _CHEAP_KEYWORDS.search(last_user) or len(last_user.split()) < 10:
                return self.tiers.cheap

        # 4) Her tool sonucu kısa ise cheap (basit analiz)
        if last_tool and len(last_tool) < 400 and len(last_user) < 200:
            return self.tiers.cheap

        # 5) Varsayılan: standard
        return self.tiers.standard
