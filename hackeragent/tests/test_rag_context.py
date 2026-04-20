"""RAG enrichment birim testleri — MCPManager mock'lanır."""

from __future__ import annotations

from unittest.mock import MagicMock

from hackeragent.core.rag_context import enrich_from_rag_and_memory, _looks_empty


def test_looks_empty_detects_various_empty_signals():
    assert _looks_empty("") is True
    assert _looks_empty("   ") is True
    assert _looks_empty("boş") is True
    assert _looks_empty("No results found") is True
    assert _looks_empty("0 kayıt bulundu") is True


def test_looks_empty_returns_false_for_real_content():
    assert _looks_empty("CVE-2023-1234: Apache HTTP Server RCE...") is False


def test_enrich_returns_none_when_both_empty():
    mcp = MagicMock()
    mcp.call_tool.return_value = ""
    result = enrich_from_rag_and_memory(mcp, "test query", target="example.com")
    assert result is None


def test_enrich_combines_rag_and_memory():
    mcp = MagicMock()
    # rag_search ve get_target_memory'ye farklı yanıtlar
    def side_effect(server, tool, args, timeout=10):
        if tool == "rag_search":
            return "CVE-2024-0001: Critical RCE in nginx"
        if tool == "get_target_memory":
            return "Geçmiş finding: 443/tcp https açık, SSL cert expired"
        if tool == "suggest_next_action":
            return "🔴 #1 [CRITICAL] Exploit ara: CVE-2024-0001"
        return ""
    mcp.call_tool.side_effect = side_effect

    result = enrich_from_rag_and_memory(mcp, "nginx exploit var mı", target="example.com")
    assert result is not None
    assert "RAG Bilgi Tabanından" in result
    assert "CVE-2024-0001" in result
    assert "Geçmiş Kayıtlar" in result
    assert "SSL cert expired" in result
    # Attack graph önerisi de enjekte edildi
    assert "Attack Graph Önerisi" in result
    assert "CRITICAL" in result


def test_enrich_skips_memory_when_no_target():
    mcp = MagicMock()
    mcp.call_tool.return_value = "CVE-2024-0001: nginx RCE detected in version 1.20"
    result = enrich_from_rag_and_memory(mcp, "query", target="")
    # rag_search çağrıldı, get_target_memory çağrılmadı
    assert mcp.call_tool.call_count == 1
    assert "RAG" in result


def test_enrich_truncates_long_context():
    mcp = MagicMock()
    # Her üç çağrıya da MAX_CHARS üstünde yanıt ver — birleşim kırpılmalı
    huge = "CVE-DATA-" + ("A" * 10000)
    mcp.call_tool.return_value = huge
    result = enrich_from_rag_and_memory(mcp, "q", target="t")
    # 2000 (rag) + 1500 (memory) + 1200 (graph) + başlıklar ≈ 5200 → kırpılmalı
    # _MAX_CHARS = 5000 + marj 200
    assert len(result) <= 5300
    # Çok uzunsa "kırpıldı" eklenir
    if len(result) >= 5000:
        assert "kırpıldı" in result or len(result) < 5200


def test_enrich_survives_mcp_exceptions():
    mcp = MagicMock()
    mcp.call_tool.side_effect = Exception("MCP down")
    # Exception fırlatmamalı, None dönmeli
    result = enrich_from_rag_and_memory(mcp, "q", target="t")
    assert result is None
