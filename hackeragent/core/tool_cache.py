"""Tool call dedup cache — aynı hedefe aynı taramayı tekrar yapmayı önler.

Her qualified tool çağrısı `(qname, args)` için hash üretir ve sonucu TTL'li
bir in-memory dict'te tutar. LLM aynı tool'u tekrar isterse cache'den döner
(MCP çağrısı yapılmaz) ve LLM'e `[CACHED]` işareti ile dönülür.

TTL stratejisi:
  • Hızla değişen veriler kısa TTL (telemetry: 10s)
  • Yavaş değişen keşif (nmap: 1 saat)
  • Sabit veriler uzun TTL (CVE lookup: 1 hafta)
  • Tüm diğerleri için default 600s (10 dk)

Persistent cache değil — session-scoped. --resume ile yeniden başlayınca
temiz başlar (doğru davranış: belki hedefin durumu değişmiştir).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

DEFAULT_TTL = 600  # 10 dk

# Tool-spesifik TTL override'ları (saniye)
TOOL_TTL_OVERRIDES: dict[str, int] = {
    # Hızlı değişen
    "telemetry__get_metrics_dashboard": 10,
    "telemetry__get_session_stats": 10,
    # Keşif — 1 saat makul
    "kali-tools__nmap_scan": 3600,
    "kali-tools__nmap_scan_structured": 3600,
    "kali-tools__subdomain_enum": 3600,
    "kali-tools__dns_enum": 3600,
    "kali-tools__ffuf_directory": 1800,
    "kali-tools__nikto_scan": 3600,
    "kali-tools__nuclei_scan": 1800,
    # CVE lookup — 1 hafta
    "rag-engine__rag_search": 86400 * 7,
    # Memory / graph — sonuç sürekli değişebilir, kısa tut
    "memory-server__get_target_memory": 60,
    "memory-server__suggest_next_action": 60,
    "memory-server__query_attack_paths": 120,
}

# Cache EDİLMEYECEK tool'lar (her zaman taze çalışmalı)
CACHE_EXCLUDED: set[str] = {
    # Yazma işlemleri — cache anlamsız
    "memory-server__store_finding",
    "memory-server__store_credential",
    "memory-server__store_endpoint",
    "memory-server__add_relationship",
    "memory-server__drop_target_memory",
    # Onay + exploit — ASLA cache'lenmemeli
    "kali-tools__request_approval",
    "kali-tools__generate_exploit_poc",
    "kali-tools__run_exploit",
    # CTF submit
    "ctf-platform__submit_flag",
    "ctf-platform__ctfd_submit_flag",
    "ctf-platform__htb_submit_flag",
}


@dataclass
class _Entry:
    result: str
    stored_at: float
    ttl: int
    hit_count: int = 0


@dataclass
class ToolCache:
    """Session-scoped, TTL-based tool result cache."""

    _entries: dict[str, _Entry] = field(default_factory=dict)
    enabled: bool = True
    total_lookups: int = 0
    total_hits: int = 0
    total_stores: int = 0
    # Cache hit olduğunda çağrılan opsiyonel callback: (qname, result_chars) → None
    on_hit: object = None

    def _key(self, qname: str, args: dict) -> str:
        """Kararlı hash — dict sırasından bağımsız."""
        canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        h = hashlib.sha1(f"{qname}|{canonical}".encode("utf-8")).hexdigest()[:16]
        return f"{qname}:{h}"

    def is_cacheable(self, qname: str) -> bool:
        if not self.enabled:
            return False
        return qname not in CACHE_EXCLUDED

    def get(self, qname: str, args: dict) -> str | None:
        """Cache hit varsa sonucu döndür, yoksa None."""
        if not self.is_cacheable(qname):
            return None
        self.total_lookups += 1
        key = self._key(qname, args)
        entry = self._entries.get(key)
        if entry is None:
            return None
        age = time.time() - entry.stored_at
        if age > entry.ttl:
            # Süresi dolmuş — sil
            del self._entries[key]
            return None
        entry.hit_count += 1
        self.total_hits += 1
        log.info("Cache HIT: %s (age=%.0fs, ttl=%ds, hits=%d)",
                 qname, age, entry.ttl, entry.hit_count)
        # Callback — session stats için
        if callable(self.on_hit):
            try:
                self.on_hit(qname, len(entry.result))
            except Exception as e:
                log.debug("on_hit callback failed (ignored): %s", e)
        return entry.result

    def put(self, qname: str, args: dict, result: str) -> None:
        """Başarılı sonucu cache'e yaz. Failure prefix'li sonuçlar cache'lenmez."""
        if not self.is_cacheable(qname):
            return
        # HATA/ERROR ile başlayan sonuçları cache'leme — bir dahaki sefere tekrar dene
        trimmed = (result or "").lstrip()
        if any(trimmed.startswith(p) for p in ("HATA:", "ERROR:", "Error:", "Exception:", "❌", "🚫")):
            return
        ttl = TOOL_TTL_OVERRIDES.get(qname, DEFAULT_TTL)
        key = self._key(qname, args)
        self._entries[key] = _Entry(result=result, stored_at=time.time(), ttl=ttl)
        self.total_stores += 1
        log.debug("Cache STORE: %s (ttl=%ds, size=%d chars)", qname, ttl, len(result))

    def invalidate(self, qname_prefix: str = "") -> int:
        """Prefix ile eşleşen tüm entry'leri sil. Count dönder."""
        if not qname_prefix:
            n = len(self._entries)
            self._entries.clear()
            return n
        keys = [k for k in self._entries if k.startswith(qname_prefix)]
        for k in keys:
            del self._entries[k]
        return len(keys)

    def stats(self) -> dict:
        hit_rate = (self.total_hits / self.total_lookups) if self.total_lookups else 0.0
        return {
            "enabled": self.enabled,
            "entries": len(self._entries),
            "lookups": self.total_lookups,
            "hits": self.total_hits,
            "hit_rate": round(hit_rate, 3),
            "stores": self.total_stores,
        }

    def top_entries(self, limit: int = 10) -> list[dict]:
        """En çok hit alan entry'ler — debug için."""
        items = sorted(self._entries.items(), key=lambda kv: kv[1].hit_count, reverse=True)
        out = []
        for key, e in items[:limit]:
            age = time.time() - e.stored_at
            out.append({
                "key": key,
                "age_s": round(age, 1),
                "ttl_s": e.ttl,
                "hits": e.hit_count,
                "size_chars": len(e.result),
            })
        return out
