"""RAG / memory / attack-graph context enrichment.

Her kullanıcı turundan önce:
  1. `rag-engine.rag_search` ile benzer geçmiş CVE/exploit/writeup bul
  2. `memory-server.get_target_memory` ile aynı hedefte geçmiş bulguları al
  3. `memory-server.suggest_next_action` ile attack graph'ına bakarak
     en yüksek öncelikli sonraki adım önerisini al (NEW — özellik #5)
  4. İlk ~1500 token ile sınırlı bir "Geçmiş bilgi + graph önerisi" system
     mesajı enjekte et

RAG / memory / graph boşsa sessizce atlar. Tool call yapmadan (direct MCP
call) çalışır.
"""

from __future__ import annotations

from hackeragent.core.mcp_manager import MCPManager
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

_MAX_CHARS = 5000  # ~1250 token, system prompt'u şişirmesin


def enrich_from_rag_and_memory(
    mcp: MCPManager,
    user_input: str,
    target: str = "",
) -> str | None:
    """Kullanıcı inputuna bağlı olarak bir `system` bağlam metni üret.

    Return: bağlam metni (str) veya None (bulunmadıysa).
    """
    chunks: list[str] = []

    # 1) RAG search — CVE/exploit/writeup
    try:
        rag_result = mcp.call_tool(
            "rag-engine",
            "rag_search",
            {"query": user_input[:500], "top_k": 3},
            timeout=10,
        )
        if rag_result and not _looks_empty(rag_result):
            chunks.append("### 📚 RAG Bilgi Tabanından İlgili Kayıtlar\n" + rag_result.strip()[:2000])
    except Exception as e:
        log.debug("RAG enrichment failed (ignored): %s", e)

    # 2) Memory — aynı target'ta geçmiş finding'ler
    if target:
        try:
            mem_result = mcp.call_tool(
                "memory-server",
                "get_target_memory",
                {"target": target},
                timeout=10,
            )
            if mem_result and not _looks_empty(mem_result):
                chunks.append(f"### 🧠 '{target}' İçin Geçmiş Kayıtlar\n" + mem_result.strip()[:1500])
        except Exception as e:
            log.debug("Memory enrichment failed (ignored): %s", e)

        # 3) Attack graph — akıllı sonraki adım önerisi
        try:
            suggest_result = mcp.call_tool(
                "memory-server",
                "suggest_next_action",
                {"target": target},
                timeout=10,
            )
            if suggest_result and not _looks_empty(suggest_result):
                chunks.append(
                    f"### 🗡️ Attack Graph Önerisi ({target})\n"
                    + suggest_result.strip()[:1200]
                )
        except Exception as e:
            log.debug("Attack graph enrichment failed (ignored): %s", e)

    if not chunks:
        return None

    combined = "\n\n".join(chunks)
    if len(combined) > _MAX_CHARS:
        combined = combined[:_MAX_CHARS] + "\n\n[... kırpıldı]"
    return combined


def _looks_empty(result: str) -> bool:
    """RAG / memory 'boş' yanıtlarını tespit et."""
    if not result or len(result.strip()) < 10:
        return True
    text = result.lower()
    empty_signals = [
        "boş", "hiç kayıt yok", "hiçbir", "no results", "empty",
        "0 kayıt", "no match", "bulunmadı",
    ]
    return any(sig in text for sig in empty_signals)

