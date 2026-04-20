"""Paralel tool execution birim testleri."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from hackeragent.core.parallel_exec import (
    _is_safe_for_parallel,
    _plan_execution,
    execute_tool_calls,
)


def test_safe_tools_detected_as_safe():
    assert _is_safe_for_parallel("kali-tools__nmap_scan") is True
    assert _is_safe_for_parallel("rag-engine__rag_search") is True
    assert _is_safe_for_parallel("memory-server__get_target_memory") is True


def test_unsafe_tools_detected():
    assert _is_safe_for_parallel("kali-tools__request_approval") is False
    assert _is_safe_for_parallel("kali-tools__generate_exploit_poc") is False
    assert _is_safe_for_parallel("memory-server__store_finding") is False
    assert _is_safe_for_parallel("ctf-platform__submit_flag") is False


def test_plan_all_safe_one_segment():
    tcs = [
        {"name": "kali-tools__nmap", "arguments": {"t": "1"}},
        {"name": "rag-engine__rag_search", "arguments": {"q": "x"}},
        {"name": "memory-server__get_target_memory", "arguments": {"target": "t"}},
    ]
    plan = _plan_execution(tcs)
    # Hepsi farklı qname → tek paralel grup
    assert len(plan.segments) == 1
    assert len(plan.segments[0]) == 3


def test_plan_unsafe_creates_serial_segment():
    tcs = [
        {"name": "kali-tools__nmap", "arguments": {}},
        {"name": "memory-server__store_finding", "arguments": {}},  # UNSAFE
        {"name": "rag-engine__rag_search", "arguments": {}},
    ]
    plan = _plan_execution(tcs)
    # [parallel_1, serial_store, parallel_2]
    assert len(plan.segments) == 3
    assert len(plan.segments[0]) == 1  # nmap solo (sonraki grupta aynı qname yok)
    assert plan.segments[1][0]["name"] == "memory-server__store_finding"
    assert plan.segments[2][0]["name"] == "rag-engine__rag_search"


def test_plan_same_qname_splits_group():
    tcs = [
        {"name": "kali-tools__nmap", "arguments": {"t": "1"}},
        {"name": "kali-tools__nmap", "arguments": {"t": "2"}},  # Aynı tool
        {"name": "rag-engine__rag_search", "arguments": {}},
    ]
    plan = _plan_execution(tcs)
    # İlk nmap grup, ikinci nmap + search yeni grup
    assert len(plan.segments) == 2


def test_execute_sequential_when_parallel_disabled():
    tcs = [
        {"name": "kali-tools__nmap", "arguments": {}, "id": "a"},
        {"name": "rag-engine__rag_search", "arguments": {}, "id": "b"},
    ]
    executor = MagicMock(side_effect=lambda tc: f"result_{tc['id']}")
    results = execute_tool_calls(tcs, executor, parallel_enabled=False)
    assert len(results) == 2
    assert results[0][1] == "result_a"
    assert results[1][1] == "result_b"


def test_execute_preserves_order_in_parallel():
    """Paralel koşsalar bile sonuç orijinal sırada dönmeli."""
    tcs = [
        {"name": "tool__a", "arguments": {}, "id": "1"},
        {"name": "tool__b", "arguments": {}, "id": "2"},
        {"name": "tool__c", "arguments": {}, "id": "3"},
    ]

    def slow_executor(tc):
        # Sıralanmış olarak farklı süreler
        delays = {"1": 0.1, "2": 0.02, "3": 0.05}
        time.sleep(delays[tc["id"]])
        return f"result_{tc['id']}"

    results = execute_tool_calls(tcs, slow_executor, parallel_enabled=True, max_workers=3)
    # Orijinal sırayı koru
    assert [r[1] for r in results] == ["result_1", "result_2", "result_3"]


def test_execute_parallel_faster_than_sequential():
    """Paralel yürütme gerçekten hızlı mı?"""
    tcs = [
        {"name": f"tool__t{i}", "arguments": {}, "id": str(i)}
        for i in range(4)
    ]

    def slow(tc):
        time.sleep(0.1)
        return "ok"

    t0 = time.time()
    execute_tool_calls(tcs, slow, parallel_enabled=True, max_workers=4)
    parallel_time = time.time() - t0

    t0 = time.time()
    execute_tool_calls(tcs, slow, parallel_enabled=False)
    sequential_time = time.time() - t0

    # Paralel en az yarı kadar hızlı olmalı (gerçekte daha fazla ama CI jitter)
    assert parallel_time < sequential_time * 0.7


def test_execute_exception_captured():
    tcs = [
        {"name": "tool__ok", "arguments": {}, "id": "1"},
        {"name": "tool__bad", "arguments": {}, "id": "2"},
    ]

    def exec_fn(tc):
        if tc["id"] == "2":
            raise RuntimeError("boom")
        return "ok"

    results = execute_tool_calls(tcs, exec_fn, parallel_enabled=True, max_workers=2)
    assert results[0][1] == "ok"
    assert "HATA" in results[1][1]
    assert "boom" in results[1][1]


def test_execute_progress_callback_fires():
    tcs = [{"name": "tool__a", "arguments": {}, "id": "1"}]
    seen = []
    execute_tool_calls(
        tcs,
        executor=lambda tc: "r",
        parallel_enabled=False,
        on_progress=lambda tc, r: seen.append((tc["id"], r)),
    )
    assert seen == [("1", "r")]
