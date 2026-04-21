"""Session replay — eski session'ın kullanıcı mesajlarını yeni session'da
tekrar oynatır. Regression testing / prompt tuning için kullanışlı.

Kullanım:
    hackeragent --replay <session-id>

Orijinal session'daki her 'user' mesajı sıraya girer, orkestratör bunları
taze bir bağlamda işler. Assistant/tool mesajları YENİDEN ÜRETİLİR
(LLM + MCP aktif olarak çalışır). Bu, promptlardaki/kurallar değişikliğinin
eski görevlerde nasıl performans gösterdiğini görmek için tasarlandı.

Maliyet: orijinal session'ın yaklaşık %100'ü (LLM tekrar çağrılır).
Sadece test/debug için öneririz.
"""

from __future__ import annotations

from hackeragent.core.session import Session
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


def extract_user_messages(session: Session) -> list[str]:
    """Session'dan sırayla user mesajlarını al."""
    msgs: list[str] = []
    for m in session.messages:
        if m.get("role") != "user":
            continue
        content = m.get("content") or ""
        if isinstance(content, list):
            # Multimodal mesajları: text parçalarını birleştir
            text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
            content = "\n".join(text_parts)
        if content.strip():
            msgs.append(content)
    return msgs


def replay_summary(original: Session) -> str:
    """Replay öncesi özet metni."""
    users = extract_user_messages(original)
    return (
        f"🔁 Replay — orijinal session: {original.id}\n"
        f"  Tur sayısı: {len(users)}\n"
        f"  Hedef: {original.target or '—'}\n"
        f"  Orijinal maliyet: ${original.total_cost_usd:.4f}\n"
        f"  İlk mesaj: {users[0][:100] if users else '—'}"
    )
