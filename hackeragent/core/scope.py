"""Scope guard — hedef kapsam kontrolü.

Her tool çağrısından önce argümanlar içindeki IP/hostname/URL'leri çıkarır
ve allow-list'e karşı doğrular. Scope dışı → çağrı bloke edilir ve LLM'e
hatayı geri besler (LLM yeniden yönlendirilebilir).

Scope allow-list formatları:
  - "10.10.10.5"           (tam eşleşme IP)
  - "10.10.10.0/24"        (CIDR)
  - "example.com"          (tam domain)
  - "*.example.com"        (wildcard subdomain)
  - "target.com/admin"     (URL path prefix)

Localhost (127.0.0.0/8, ::1) ve private RFC1918 aralıkları otomatik
güvenli-sayılır mı → HAYIR. Bunlar CTF/lab için istenebilir ama default
bloklanır; kullanıcı açıkça scope'a eklemeli.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# Arg değerlerinde host çıkarmak için yardımcı regex'ler
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DOMAIN_RE = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")

# OSINT/metadata servisleri — scope dışı olsa bile izin verilir
OSINT_ALLOWLIST = {
    "crt.sh", "shodan.io", "censys.io", "virustotal.com", "hackertarget.com",
    "urlscan.io", "whois.iana.org", "rdap.org", "wikipedia.org",
    "github.com", "api.github.com", "gitlab.com", "bitbucket.org",
    "hackerone.com", "bugcrowd.com", "exploit-db.com", "cve.mitre.org",
    "services.nvd.nist.gov", "openrouter.ai",
    "google.com", "duckduckgo.com", "bing.com",
    "archive.org", "web.archive.org", "waybackmachine.org",
}

# Yerel/özel aralıklar scope'a AÇIKÇA eklenmedikçe bloke
# (kullanıcı `scope add 10.0.0.0/8` derse açılır)


@dataclass
class ScopeRule:
    """Parse edilmiş scope entry."""

    raw: str
    cidr: ipaddress.IPv4Network | ipaddress.IPv6Network | None = None
    exact_ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
    domain_suffix: str = ""  # "example.com" matches foo.example.com ve example.com
    exact_domain: str = ""
    url_prefix: str = ""  # "example.com/admin" — path gereksinimi

    @classmethod
    def parse(cls, entry: str) -> "ScopeRule":
        s = entry.strip().lower()
        rule = cls(raw=entry)
        # URL prefix?
        if "/" in s and not re.fullmatch(r"[\d./]+", s):
            # "example.com/admin" gibi
            host, _, path = s.partition("/")
            rule.exact_domain = host
            rule.url_prefix = s
            return rule
        # CIDR?
        try:
            rule.cidr = ipaddress.ip_network(s, strict=False)
            return rule
        except ValueError:
            pass
        # Tekil IP?
        try:
            rule.exact_ip = ipaddress.ip_address(s)
            return rule
        except ValueError:
            pass
        # Wildcard domain?
        if s.startswith("*."):
            rule.domain_suffix = s[2:]
            return rule
        # Düz domain (hem tam eşleşme hem subdomain kabul)
        rule.exact_domain = s
        rule.domain_suffix = s
        return rule

    def matches_ip(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        if self.cidr is not None and ip.version == self.cidr.version:
            try:
                return ip in self.cidr
            except TypeError:
                return False
        if self.exact_ip is not None:
            return ip == self.exact_ip
        return False

    def matches_host(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        if self.exact_domain and host == self.exact_domain:
            return True
        if self.domain_suffix and (host == self.domain_suffix or host.endswith("." + self.domain_suffix)):
            return True
        return False


@dataclass
class ScopeGuard:
    """Scope allowlist ve doğrulayıcı."""

    rules: list[ScopeRule] = field(default_factory=list)
    enabled: bool = True
    # Kullanıcı explicit bir şey söylemediğinde permissive olsun
    # (boş liste = her şey serbest ama warning)
    strict_when_empty: bool = False

    @classmethod
    def from_list(cls, entries: list[str], enabled: bool = True) -> "ScopeGuard":
        rules = [ScopeRule.parse(e) for e in entries if e.strip()]
        return cls(rules=rules, enabled=enabled)

    def add(self, entry: str) -> None:
        self.rules.append(ScopeRule.parse(entry))

    def remove(self, entry: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.raw.strip().lower() != entry.strip().lower()]
        return len(self.rules) < before

    def list_raw(self) -> list[str]:
        return [r.raw for r in self.rules]

    # ─── Host extraction ───────────────────────────────────────────────────
    @staticmethod
    def extract_hosts(value) -> list[str]:
        """Arg değerinden (str/dict/list) IP ve hostname'leri çıkar."""
        hosts: set[str] = set()
        _walk(value, hosts)
        return list(hosts)

    def validate_args(self, tool_name: str, arguments: dict) -> tuple[bool, str]:
        """Tool argümanlarını doğrula. (ok, reason)."""
        if not self.enabled:
            return True, ""

        hosts = self.extract_hosts(arguments)
        if not hosts:
            # Host-bağımsız tool (rag_stats, get_knowledge_graph_summary vs.) → serbest
            return True, ""

        if not self.rules:
            if self.strict_when_empty:
                return False, (
                    "SCOPE BOŞ: Herhangi bir hedef tanımlı değil. Önce "
                    "`/scope add <hedef>` komutuyla scope ekleyin."
                )
            # Permissive: log'la, geç
            log.info("Scope henüz boş, host(lar) serbest bırakılıyor: %s", hosts)
            return True, ""

        for host in hosts:
            if not self._is_host_allowed(host):
                return False, (
                    f"🚫 SCOPE DIŞI: '{host}' (tool: {tool_name}). "
                    f"İzinli scope: {self.list_raw() or '(boş)'}. "
                    f"Gerekliyse önce `/scope add {host}` ile ekleyin."
                )
        return True, ""

    def _is_host_allowed(self, host: str) -> bool:
        host_lower = host.lower()
        if host_lower in OSINT_ALLOWLIST:
            return True
        # Try as IP first
        try:
            ip = ipaddress.ip_address(host)
            for rule in self.rules:
                if rule.matches_ip(ip):
                    return True
            return False
        except ValueError:
            pass
        for rule in self.rules:
            if rule.matches_host(host):
                return True
        return False


def _walk(value, out: set[str]) -> None:
    """Recursive: dict/list/str içindeki tüm host/IP'leri topla."""
    if isinstance(value, str):
        _scan_string(value, out)
    elif isinstance(value, dict):
        for v in value.values():
            _walk(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk(v, out)


def _scan_string(s: str, out: set[str]) -> None:
    # URL?
    for token in re.split(r"[\s,;|]+", s):
        tok = token.strip().rstrip("/.,;)")
        if not tok:
            continue
        # URL scheme var mı?
        if "://" in tok:
            try:
                parsed = urlparse(tok)
                if parsed.hostname:
                    out.add(parsed.hostname)
                    continue
            except Exception:
                pass
        # host:port formu
        host_part = tok.split(":", 1)[0]
        # IPv4 eşleşmesi
        for m in _IPV4_RE.finditer(host_part):
            out.add(m.group(0))
        # Domain eşleşmesi (en az bir nokta + TLD)
        for m in _DOMAIN_RE.finditer(host_part):
            candidate = m.group(0).rstrip(".")
            # salt sayı ise atla (zaten ipv4 regex yakaladı)
            if not _IPV4_RE.fullmatch(candidate):
                out.add(candidate)
