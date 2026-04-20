"""Paralel tool execution planner.

Bir LLM turu birden fazla tool_call döndürürse, bunlardan GÜVENLI olanları
paralel yürütebiliriz. Paralel yürütme kazancı:
  • Recon: nmap + subdomain_enum + shodan lookup paralel → 3x hızlanma
  • RAG + memory + telemetry çağrıları paralel → latency azalır

GÜVENLİ paralel için kurallar (conservative):
  1. exploit, lateral_movement, flag_submit → SIRALI (side effect'li, sırayı koruyalım)
  2. memory-server'a store_* çağrıları → SIRALI (race condition riski, SQLite)
  3. Aynı server'a aynı tool'un birden fazla çağrısı → SIRALI (single process'te
     potansiyel resource collision)
  4. Diğer hepsi → paralel OK

Maks paralellik: 5 (hem bandwidth hem subprocess CPU limitini korur).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

DEFAULT_MAX_WORKERS = 5

# Hiçbir zaman paralel yürütülmeyen tool adları (suffix match, qualified_name'de)
_UNSAFE_FOR_PARALLEL_SUFFIXES = (
    "__request_approval",
    "__generate_exploit_poc",
    "__run_exploit",
    "__submit_flag",
    "__ctfd_submit_flag",
    "__htb_submit_flag",
    "__store_finding",
    "__store_credential",
    "__store_endpoint",
    "__add_relationship",
    "__drop_target_memory",
)


def _is_safe_for_parallel(qname: str) -> bool:
    return not any(qname.endswith(sfx) for sfx in _UNSAFE_FOR_PARALLEL_SUFFIXES)


@dataclass
class _Plan:
    """Bir tool_calls listesini serial+parallel gruplara böl."""
    # ordered segments: her segment ya 1 serial item ya N parallel item
    segments: list[list[dict]]


def _plan_execution(tool_calls: list[dict]) -> _Plan:
    """tool_calls'ı yürütme sırasına sadık kalarak serial/parallel gruplara böl.

    Algoritma:
      • Arka arkaya GÜVENLİ tool'lar → aynı paralel grup (aynı server+tool duplikasyonu yoksa)
      • GÜVENSIZ tool'la karşılaşınca grubu kapat, kendisini solo segment yap
    """
    segments: list[list[dict]] = []
    current_parallel: list[dict] = []
    current_qnames_in_group: set[str] = set()

    def flush():
        nonlocal current_parallel, current_qnames_in_group
        if current_parallel:
            segments.append(current_parallel)
            current_parallel = []
            current_qnames_in_group = set()

    for tc in tool_calls:
        qname = tc.get("name", "")
        if not _is_safe_for_parallel(qname):
            # Solo segment
            flush()
            segments.append([tc])
            continue
        # Aynı qname'den zaten paralel grupta varsa, kapat ve yeni grup başlat
        if qname in current_qnames_in_group:
            flush()
        current_parallel.append(tc)
        current_qnames_in_group.add(qname)
    flush()
    return _Plan(segments=segments)


def execute_tool_calls(
    tool_calls: list[dict],
    executor: Callable[[dict], str],
    max_workers: int = DEFAULT_MAX_WORKERS,
    parallel_enabled: bool = True,
    on_progress: Callable[[dict, str], None] | None = None,
) -> list[tuple[dict, str]]:
    """tool_calls'ı yürüt. Sırası korunur (LLM'in beklediği gibi).

    Args:
      tool_calls: LLM'den gelen sıralı tool_calls listesi
      executor: tek bir tool_call'ı yürüten callable (ToolRouter.execute)
      max_workers: paralel grup başına max thread sayısı
      parallel_enabled: False ise hepsi seri koşar
      on_progress: her tool için (tc, result) geri çağrı

    Returns: [(tool_call, result), ...] — input sırasında
    """
    if not parallel_enabled or len(tool_calls) == 1:
        # Tamamen seri
        results: list[tuple[dict, str]] = []
        for tc in tool_calls:
            r = executor(tc)
            if on_progress:
                try:
                    on_progress(tc, r)
                except Exception:
                    pass
            results.append((tc, r))
        return results

    plan = _plan_execution(tool_calls)
    # tool_call_index -> result
    ordered: dict[int, tuple[dict, str]] = {}
    # index lookup by id(tc)
    id_to_index = {id(tc): i for i, tc in enumerate(tool_calls)}

    for segment in plan.segments:
        if len(segment) == 1:
            tc = segment[0]
            r = executor(tc)
            if on_progress:
                try:
                    on_progress(tc, r)
                except Exception:
                    pass
            ordered[id_to_index[id(tc)]] = (tc, r)
            continue

        # Paralel segment
        workers = min(max_workers, len(segment))
        log.info("Paralel yürütme: %d tool, %d worker", len(segment), workers)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tool-par") as pool:
            futures = {pool.submit(executor, tc): tc for tc in segment}
            for fut in as_completed(futures):
                tc = futures[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    r = f"HATA: paralel yürütmede exception: {e}"
                if on_progress:
                    try:
                        on_progress(tc, r)
                    except Exception:
                        pass
                ordered[id_to_index[id(tc)]] = (tc, r)

    # Orijinal sırada döndür
    return [ordered[i] for i in range(len(tool_calls))]
