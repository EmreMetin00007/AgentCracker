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
from typing import Any

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# Tier tespitinde kullanılan anahtar kelimeler (Türkçe + İngilizce)
_PREMIUM_KEYWORDS = re.compile(
    r"\b(exploit|payload|poc|bypass|shellcode|rop|gadget|canary|rce|"
    r"buffer overflow|format string|heap|use.after.free|"
    r"rapor\w*|report|writeup|"
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
        standard = models_config.get("orchestrator") or "qwen/qwen3.6-plus"
        # `or` kullanıyoruz ki config'de "" olsa bile fallback tetiklensin
        return cls(
            cheap=models_config.get("cheap") or standard,
            standard=standard,
            premium=models_config.get("premium") or models_config.get("exploit_gen") or standard,
        )


class ModelRouter:
    """Heuristik model seçici.

    `llm_classifier` verilirse (callable: messages -> tier), heuristik yerine
    LLM kararı kullanılır. Sonuç 30sn cache'lenir (aynı mesaj için tekrar
    sorgulanmaz).
    """

    def __init__(
        self,
        tiers: ModelTiers,
        enabled: bool = True,
        llm_classifier: "LLMTierClassifier | None" = None,
    ):
        self.tiers = tiers
        self.enabled = enabled
        self.llm_classifier = llm_classifier

    def pick(
        self,
        messages: list[dict],
        iteration: int = 0,
        has_tools: bool = True,
    ) -> str:
        """Mevcut conversation state'e göre model seç."""
        if not self.enabled:
            return self.tiers.standard

        # LLM classifier aktifse onun kararını kullan
        if self.llm_classifier is not None:
            try:
                tier = self.llm_classifier.classify(messages, iteration)
                if tier == "cheap":
                    return self.tiers.cheap
                if tier == "premium":
                    return self.tiers.premium
                return self.tiers.standard
            except Exception as e:
                log.debug("LLM classifier fail → heuristik fallback: %s", e)

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


class LLMTierClassifier:
    """Opsiyonel LLM-based tier classifier.

    Heuristik yerine ucuz LLM'e "bu görev cheap/standard/premium mi?" diye
    sorar. 30sn TTL cache — aynı mesaj için tekrar sorgu yok.

    Maliyet: her yeni user mesajı için ~50 token cheap çağrı (~$0.00001).
    ROI: bakım karar kalitesi heuristikten daha doğruysa devreye alın.
    """

    _SYSTEM = (
        "Sen bir LLM tier classifier'sın. Kullanıcı mesajını ve bağlamı oku, "
        "şu üçünden birini döndür (sadece tek kelime):\n"
        "  - cheap: basit sohbet, kısa soru, greet, yardım\n"
        "  - standard: orkestrasyon, tool çağrısı, zafiyet analizi\n"
        "  - premium: exploit kodu, rapor yazımı, uzun kod, binary analiz\n"
        "Yalnızca kelimeyi döndür: cheap, standard veya premium."
    )

    def __init__(self, llm_client: Any, cheap_model: str, cache_ttl: int = 30):
        self._llm = llm_client
        self._cheap_model = cheap_model
        self._cache: dict[str, tuple[float, str]] = {}
        self._cache_ttl = cache_ttl

    def classify(self, messages: list[dict], iteration: int = 0) -> str:
        import time
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        if not isinstance(last_user, str) or not last_user:
            return "standard"
        key = last_user[:300]
        now = time.time()
        hit = self._cache.get(key)
        if hit and (now - hit[0]) < self._cache_ttl:
            return hit[1]
        try:
            reply = self._llm.chat(
                messages=[
                    {"role": "system", "content": self._SYSTEM},
                    {"role": "user", "content": last_user[:2000]},
                ],
                model=self._cheap_model,
                max_tokens=5,
                temperature=0.0,
                retries=0,
            )
            decision = (reply.content or "standard").strip().lower().split()[0]
            if decision not in ("cheap", "standard", "premium"):
                decision = "standard"
        except Exception as e:
            log.debug("LLM classifier fail: %s", e)
            decision = "standard"
        self._cache[key] = (now, decision)
        return decision
