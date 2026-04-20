"""Cost-aware telemetry birim testleri."""

from __future__ import annotations

from unittest.mock import MagicMock

from hackeragent.core.telemetry import (
    SessionStats,
    TelemetryEmitter,
    chars_to_tokens,
)


def test_chars_to_tokens_approx():
    assert chars_to_tokens(400) == 100
    assert chars_to_tokens(0) == 0
    assert chars_to_tokens(3) == 0


def test_empty_stats_report():
    s = SessionStats(session_id="s1")
    report = s.render_report()
    assert "Henüz optimizasyon" in report or "Session Report" in report


def test_compression_event_recorded():
    s = SessionStats(session_id="s1")
    s.record_compression(removed_count=10, before_chars=50_000, after_chars=10_000, llm_cost_usd=0.002)
    assert s.compression.count == 1
    assert s.compression.cost_usd == 0.002
    # saved_tokens ≈ 40000/4 = 10000
    assert s.compression.saved_tokens == 10_000
    # saved_usd > 0
    assert s.compression.saved_usd > 0


def test_cache_hit_event_recorded():
    s = SessionStats(session_id="s1")
    s.record_cache_hit(qname="kali-tools__nmap_scan", result_chars=4000)
    assert s.cache_hit.count == 1
    assert s.cache_hit.saved_tokens == 1000  # 4000/4
    assert s.cache_hit.saved_usd > 0


def test_planner_event_recorded():
    s = SessionStats(session_id="s1")
    s.record_planner(step_count=5, llm_cost_usd=0.001)
    assert s.planner.count == 1
    assert s.planner.cost_usd == 0.001
    assert s.planner.saved_tokens > 0


def test_reflection_event_recorded():
    s = SessionStats(session_id="s1")
    s.record_reflection(failed_tools=["nmap", "sqlmap"])
    assert s.reflection.count == 1
    assert s.reflection.saved_tokens > 0


def test_parallel_event_recorded():
    s = SessionStats(session_id="s1")
    s.record_parallel(parallel_count=3, total_calls=3)
    assert s.parallel.count == 1
    # Parallel → $ tasarruf yok, sadece wall-clock
    assert s.parallel.saved_usd == 0


def test_render_report_contains_all_sections():
    s = SessionStats(session_id="s1")
    s.record_compression(5, 40000, 10000, 0.001)
    s.record_cache_hit("k__t", 2000)
    s.record_planner(4, 0.002)
    s.record_reflection(["nmap"])
    s.record_parallel(3, 3)
    report = s.render_report(total_llm_cost_usd=0.05, total_llm_calls=10)
    assert "Compression" in report
    assert "Cache" in report
    assert "Plan" in report
    assert "Reflection" in report
    assert "Parallel" in report
    assert "0.05" in report  # total cost
    assert "Net" in report


def test_render_report_shows_net_benefit_positive():
    s = SessionStats(session_id="s1")
    # Büyük cache saving, küçük plan overhead → pozitif net
    s.record_cache_hit("k__t", 50_000)
    s.record_planner(3, llm_cost_usd=0.0001)
    report = s.render_report()
    assert "Net +$" in report


def test_emitter_fire_and_forget_calls_mcp():
    """Emitter MCP call fonksiyonunu arka planda çağırmalı."""
    import time
    call_fn = MagicMock(return_value="ok")
    emitter = TelemetryEmitter(mcp_call_fn=call_fn, server_name="telemetry")
    emitter.emit("s1", "cache_hit", {"qname": "x__y"}, saved_tokens=100, saved_usd=0.001)
    # Arka plan thread'in bitmesini bekle
    time.sleep(0.3)
    assert call_fn.called
    args = call_fn.call_args
    assert args[0][0] == "telemetry"  # server name
    assert args[0][1] == "log_savings_event"  # tool name
    payload = args[0][2]
    assert payload["event_type"] == "cache_hit"
    assert payload["session_id"] == "s1"
    assert payload["saved_tokens"] == 100


def test_emitter_exceptions_swallowed():
    """Emitter MCP exception fırlatırsa ana akışı bozmamalı."""
    import time
    call_fn = MagicMock(side_effect=RuntimeError("MCP down"))
    emitter = TelemetryEmitter(call_fn)
    # Exception fırlatmamalı
    emitter.emit("s1", "compression", {})
    time.sleep(0.2)
    # Hata thread'de yutuldu


def test_stats_with_emitter_fires_on_record():
    """SessionStats emitter bağlıysa her record event emit etmeli."""
    import time
    call_fn = MagicMock(return_value="ok")
    emitter = TelemetryEmitter(call_fn)
    s = SessionStats(session_id="s42")
    s.attach_emitter(emitter)
    s.record_compression(5, 20000, 5000, 0.001)
    s.record_cache_hit("x__y", 1000)
    time.sleep(0.3)
    # İki emit yapıldı
    assert call_fn.call_count >= 2
    event_types = [c[0][2]["event_type"] for c in call_fn.call_args_list]
    assert "compression" in event_types
    assert "cache_hit" in event_types
