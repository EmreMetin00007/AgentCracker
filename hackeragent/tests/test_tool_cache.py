"""ToolCache birim testleri."""

from __future__ import annotations

import time

from hackeragent.core.tool_cache import ToolCache, CACHE_EXCLUDED, TOOL_TTL_OVERRIDES


def test_initial_miss():
    c = ToolCache()
    assert c.get("kali-tools__nmap_scan", {"target": "1.2.3.4"}) is None
    assert c.stats()["hits"] == 0


def test_store_and_hit():
    c = ToolCache()
    args = {"target": "1.2.3.4"}
    c.put("kali-tools__nmap_scan", args, "port 80 open\nport 443 open")
    hit = c.get("kali-tools__nmap_scan", args)
    assert hit == "port 80 open\nport 443 open"
    assert c.stats()["hits"] == 1


def test_args_order_independent():
    c = ToolCache()
    c.put("x__y", {"b": 2, "a": 1}, "result")
    # Farklı sırada aynı arg → aynı hash olmalı
    assert c.get("x__y", {"a": 1, "b": 2}) == "result"


def test_failure_not_cached():
    c = ToolCache()
    c.put("kali-tools__nmap_scan", {"target": "x"}, "HATA: timeout")
    assert c.get("kali-tools__nmap_scan", {"target": "x"}) is None


def test_excluded_tools_not_cached():
    c = ToolCache()
    for excluded in list(CACHE_EXCLUDED)[:3]:
        c.put(excluded, {"x": 1}, "some result")
        assert c.get(excluded, {"x": 1}) is None


def test_disabled_cache():
    c = ToolCache(enabled=False)
    c.put("t__x", {}, "res")
    assert c.get("t__x", {}) is None


def test_ttl_expiration():
    c = ToolCache()
    # Override default TTL for this test
    from hackeragent.core import tool_cache as _tc
    original = _tc.DEFAULT_TTL
    _tc.DEFAULT_TTL = 1
    try:
        c.put("generic__tool", {}, "result")
        assert c.get("generic__tool", {}) == "result"
        time.sleep(1.1)
        assert c.get("generic__tool", {}) is None
    finally:
        _tc.DEFAULT_TTL = original


def test_specific_tool_ttl_override():
    """rag_search için TTL çok uzun, telemetry için kısa olmalı."""
    assert TOOL_TTL_OVERRIDES["rag-engine__rag_search"] > 86400
    assert TOOL_TTL_OVERRIDES["telemetry__get_metrics_dashboard"] < 60


def test_invalidate_all():
    c = ToolCache()
    c.put("a__b", {}, "r1")
    c.put("c__d", {}, "r2")
    n = c.invalidate()
    assert n == 2
    assert c.get("a__b", {}) is None


def test_invalidate_by_prefix():
    c = ToolCache()
    c.put("kali-tools__nmap", {"a": 1}, "r1")
    c.put("kali-tools__sqlmap", {"a": 1}, "r2")
    c.put("memory-server__get", {"a": 1}, "r3")
    n = c.invalidate(qname_prefix="kali-tools")
    assert n == 2
    # memory-server kaldı
    assert c.get("memory-server__get", {"a": 1}) == "r3"


def test_stats_tracking():
    c = ToolCache()
    c.put("x__y", {}, "res")
    c.get("x__y", {})
    c.get("x__y", {})
    c.get("nope__nope", {})  # miss
    stats = c.stats()
    assert stats["lookups"] == 3
    assert stats["hits"] == 2
    assert stats["hit_rate"] > 0.6


def test_top_entries_sorted_by_hits():
    c = ToolCache()
    c.put("hot__t", {"a": 1}, "r")
    c.put("cold__t", {"a": 1}, "r")
    for _ in range(5):
        c.get("hot__t", {"a": 1})
    c.get("cold__t", {"a": 1})
    top = c.top_entries(limit=10)
    assert top[0]["hits"] == 5
    assert top[0]["key"].startswith("hot__t")
