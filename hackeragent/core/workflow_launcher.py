"""Workflow launcher — workflows/*.md içeriğini system bağlamına enjekte eder.

Kullanım:
    hackeragent --workflow bug-bounty --task "example.com için bounty avı"
    hackeragent --workflow ctf --task "challenge1.com CTF"

`workflows/` dizinindeki md dosyaları LLM'e ek rehber olarak gönderilir.
Mevcut workflow'lar:
  • bug-bounty-workflow.md
  • ctf-workflow.md
  • supervisor-workflow.md
"""

from __future__ import annotations

from pathlib import Path

from hackeragent.core.config import WORKFLOWS_DIR
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

# Kısa ad → dosya adı mapping
_ALIASES = {
    "bug-bounty": "bug-bounty-workflow.md",
    "bugbounty": "bug-bounty-workflow.md",
    "bb": "bug-bounty-workflow.md",
    "ctf": "ctf-workflow.md",
    "supervisor": "supervisor-workflow.md",
    "modern-web": "modern-web-workflow.md",
    "mw": "modern-web-workflow.md",
    "api": "modern-web-workflow.md",
}


def list_workflows() -> list[str]:
    """Mevcut workflow isimlerini döndür (alias olarak)."""
    if not WORKFLOWS_DIR.is_dir():
        return []
    files = [f.name for f in WORKFLOWS_DIR.glob("*.md")]
    aliases = set()
    for alias, fn in _ALIASES.items():
        if fn in files:
            aliases.add(alias)
    return sorted(aliases)


def resolve_workflow(name: str) -> Path | None:
    """Workflow adını dosya path'ine çöz. Bulunamazsa None."""
    key = name.lower().strip()
    fn = _ALIASES.get(key)
    if fn:
        p = WORKFLOWS_DIR / fn
        if p.is_file():
            return p
    # Direkt dosya adı?
    if not key.endswith(".md"):
        key += ".md"
    p = WORKFLOWS_DIR / key
    if p.is_file():
        return p
    # wildcard arama
    for f in WORKFLOWS_DIR.glob("*.md"):
        if name.lower() in f.stem.lower():
            return f
    return None


def load_workflow_prompt(name: str) -> str | None:
    """Workflow md dosyasını oku ve LLM'e system mesajı olarak verilecek
    formata çevir. Bulunamazsa None.
    """
    path = resolve_workflow(name)
    if path is None:
        log.warning("Workflow bulunamadı: %s", name)
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        log.error("Workflow okunamadı %s: %s", path, e)
        return None

    return (
        f"# 📋 AKTİF WORKFLOW: {path.stem}\n\n"
        f"Bu görevde şu workflow'u SIKI şekilde takip et. Her adımı sırayla uygula, "
        f"atlama yapma. Her adım sonunda `memory-server.store_finding` ile ilerlemeyi kaydet.\n\n"
        f"---\n\n{content}\n\n---\n\n"
        f"Yukarıdaki workflow'u kullanıcının görevine uygula."
    )
