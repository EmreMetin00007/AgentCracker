"""Prompt compression / context pruning.

OODA döngüsünde conversation history sürekli büyür. Bir noktada:
  • Maliyet şişer (her turda N*N token)
  • LLM context window'u dolar (32k/64k/128k limit)
  • LLM "dikkati dağılır" (haystack problem)

Çözüm: Belirli bir karakter eşiği aşılınca (default ~40k char ≈ 10k token),
ESKİ tool sonuçlarını ucuz LLM ile özetle. Orijinal system prompt, user
mesajları ve son N turu olduğu gibi bırak.

Politika:
  • Son K mesajı (default 10) ASLA sıkıştırma — yakın bağlam önemli
  • İlk `system` prompt'u ASLA sıkıştırma
  • Ortadaki 'tool' ve uzun 'assistant' mesajlarını grupla → tek özet mesaja çevir
  • Özeti 'system' role ile enjekte et (LLM için netlik)
"""

from __future__ import annotations

from dataclasses import dataclass

from hackeragent.core.llm_client import LLMClient
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


def _msg_chars(msg: dict) -> int:
    c = msg.get("content") or ""
    if isinstance(c, str):
        return len(c)
    # Multimodal (list of dicts) — sadece text parçalarını say
    if isinstance(c, list):
        return sum(len(p.get("text", "")) for p in c if isinstance(p, dict))
    return 0


def total_chars(messages: list[dict]) -> int:
    return sum(_msg_chars(m) for m in messages)


@dataclass
class CompressionResult:
    compressed: bool
    removed_count: int
    summary_chars: int
    before_chars: int
    after_chars: int
    llm_cost_usd: float = 0.0


class Compressor:
    """Conversation history'yi cheap LLM ile özetler."""

    # Compression trigger'ı aşan bağlam
    DEFAULT_THRESHOLD_CHARS = 40_000

    # Sıkıştırmadan korunacak son N mesaj (en güncel bağlam)
    DEFAULT_KEEP_TAIL = 10

    def __init__(
        self,
        llm: LLMClient,
        cheap_model: str | None = None,
        threshold_chars: int = DEFAULT_THRESHOLD_CHARS,
        keep_tail: int = DEFAULT_KEEP_TAIL,
        enabled: bool = True,
    ):
        self.llm = llm
        self.cheap_model = cheap_model
        self.threshold_chars = threshold_chars
        self.keep_tail = keep_tail
        self.enabled = enabled

    def should_compress(self, messages: list[dict]) -> bool:
        if not self.enabled:
            return False
        # Korunan mesajları çıkardıktan sonra sıkıştırılabilir mi?
        if len(messages) <= 2 + self.keep_tail:
            return False
        return total_chars(messages) >= self.threshold_chars

    def compress(self, messages: list[dict]) -> CompressionResult:
        """messages listesini yerinde değiştirir. CompressionResult döner."""
        before = total_chars(messages)

        if not self.should_compress(messages):
            return CompressionResult(False, 0, 0, before, before)

        # İlk system prompt (index 0) + son keep_tail mesaj korunur
        # Ortadaki segment sıkıştırılır
        head_end = 1 if messages and messages[0].get("role") == "system" else 0
        tail_start = len(messages) - self.keep_tail
        if tail_start <= head_end:
            return CompressionResult(False, 0, 0, before, before)

        middle = messages[head_end:tail_start]
        if not middle:
            return CompressionResult(False, 0, 0, before, before)

        summary_text, llm_cost = self._summarize(middle)
        if not summary_text:
            log.warning("Compression skipped: özet üretilemedi")
            return CompressionResult(False, 0, 0, before, before, 0.0)

        summary_msg = {
            "role": "system",
            "content": (
                "📦 SIKIŞTIRILMIŞ GEÇMİŞ (önceki "
                f"{len(middle)} mesaj özetlendi, ham veri artık bağlamda değil):\n\n"
                + summary_text
            ),
        }

        # Yerinde değiştir
        messages[head_end:tail_start] = [summary_msg]
        after = total_chars(messages)
        log.warning(
            "Compression: %d mesaj → 1 özet | %d → %d char (%.1f%% azalma)",
            len(middle), before, after, 100 * (1 - after / max(before, 1)),
        )
        return CompressionResult(True, len(middle), len(summary_text), before, after, llm_cost)

    def _summarize(self, segment: list[dict]) -> tuple[str, float]:
        """Cheap LLM ile mesaj segmentini özetle. (text, llm_cost_usd) döner."""
        # Hazır özet prompt'u
        raw_transcript_parts = []
        for m in segment:
            role = m.get("role", "?")
            content = m.get("content") or ""
            # Multimodal → metin parçalarını birleştir
            if isinstance(content, list):
                content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
            # Tool çağrısı varsa onu da yaz
            if m.get("tool_calls"):
                tc_summary = ", ".join(
                    tc.get("function", {}).get("name", "?") for tc in m["tool_calls"]
                )
                content = f"{content}\n[tool_calls: {tc_summary}]"
            # Çok uzun sonuçları kes — özet için detay gerekmez
            if len(content) > 4000:
                content = content[:4000] + "\n…(kesildi)"
            raw_transcript_parts.append(f"[{role}]\n{content}")

        transcript = "\n\n---\n\n".join(raw_transcript_parts)
        # LLM çok büyük segment aldıysa kes — cheap model bağlam sınırını aşmayalım
        if len(transcript) > 60_000:
            transcript = transcript[:60_000] + "\n…[transcript kesildi]"

        sum_messages = [
            {
                "role": "system",
                "content": (
                    "Sen bir pentest ajan loglarını özetleyen asistansın. Aşağıdaki "
                    "mesaj geçmişini (tool çağrıları ve sonuçları dahil) aşağıdaki "
                    "yapıda çok kısa markdown ile özetle:\n\n"
                    "### Hedefler\n- (taranmış IP/domain)\n\n"
                    "### Keşfedilen\n- portlar, servisler, teknolojiler\n\n"
                    "### Bulgular\n- zafiyetler, credentials, findings (severity ile)\n\n"
                    "### Denenmiş/Başarısız\n- hangi tool hangi argümanla fail oldu\n\n"
                    "### Sonraki Muhtemel Adım\n- 1-2 cümle\n\n"
                    "KURAL: Uzun yazma. Toplam 600 kelimeyi aşma. Spesifik "
                    "IP/port/CVE numaralarını KAYBETME. Tekrarlardan kaçın."
                ),
            },
            {"role": "user", "content": transcript},
        ]

        try:
            reply = self.llm.chat(
                messages=sum_messages,
                tools=None,
                model=self.cheap_model,
                max_tokens=1500,
                temperature=0.2,
            )
            return (reply.content or "").strip(), float(reply.cost_usd or 0.0)
        except Exception as e:
            log.error("Compression LLM hata: %s", e)
            return "", 0.0

    # Diğer yerlerde should_compress check ve compress çağrılıyor — compress() artık
    # llm_cost_usd da içeren CompressionResult döndürüyor.
