"""CircuitBreaker birim testleri."""

from __future__ import annotations

import time

from hackeragent.core.circuit_breaker import CircuitBreaker


def test_initial_state_is_closed():
    cb = CircuitBreaker()
    is_open, _ = cb.is_open("kali-tools__nmap")
    assert is_open is False


def test_single_failure_keeps_closed():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure("kali-tools__nmap", "timeout")
    is_open, _ = cb.is_open("kali-tools__nmap")
    assert is_open is False


def test_threshold_opens_circuit():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    for _ in range(3):
        cb.record_failure("kali-tools__nmap", "err")
    is_open, reason = cb.is_open("kali-tools__nmap")
    assert is_open is True
    assert "CIRCUIT OPEN" in reason


def test_success_resets_consecutive_failures():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure("t", "e1")
    cb.record_failure("t", "e2")
    cb.record_success("t")
    # Şimdi 1 daha fail → eşik aşılmamalı (önceki reset oldu)
    cb.record_failure("t", "e3")
    is_open, _ = cb.is_open("t")
    assert is_open is False


def test_cooldown_expires(monkeypatch):
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=1)
    cb.record_failure("t", "e")
    cb.record_failure("t", "e")
    assert cb.is_open("t")[0] is True
    # Fake time ilerlet
    time.sleep(1.1)
    assert cb.is_open("t")[0] is False


def test_server_restart_signal_after_threshold():
    cb = CircuitBreaker(failure_threshold=10, restart_server_after=3)
    # Aynı server altında farklı tool'larda 3 fail → restart tavsiyesi
    r1 = cb.record_failure("kali-tools__nmap", "e")
    r2 = cb.record_failure("kali-tools__sqlmap", "e")
    r3 = cb.record_failure("kali-tools__ffuf", "e")
    assert r1 is False
    assert r2 is False
    assert r3 is True  # 3. fail'de restart önerildi


def test_server_counter_resets_after_restart_signal():
    cb = CircuitBreaker(failure_threshold=10, restart_server_after=2)
    cb.record_failure("s__a", "e")
    assert cb.record_failure("s__b", "e") is True  # restart önerildi
    # Sayaç sıfırlanmış olmalı
    assert cb.record_failure("s__c", "e") is False  # tekrar 1'den başladı


def test_stats_reports_tool_health():
    cb = CircuitBreaker()
    cb.record_success("t1")
    cb.record_success("t1")
    cb.record_failure("t1", "boom")
    stats = cb.stats()
    assert stats["t1"]["total_calls"] == 3
    assert stats["t1"]["total_failures"] == 1
    assert stats["t1"]["consecutive"] == 1
    assert stats["t1"]["open"] is False
