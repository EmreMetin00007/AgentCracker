"""System prompt üretici.

`system_prompt.md` (ana persona) + `rules/` içindeki kuralları + mevcut skill
index'ini birleştirerek OpenRouter'a gönderilecek system message'ı üretir.
"""

from __future__ import annotations

from pathlib import Path

from hackeragent.core.config import (
    RULES_DIR,
    SKILLS_DIR,
    SYSTEM_PROMPT_PATH,
    WORKFLOWS_DIR,
)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _collect_skills() -> str:
    """skills/*/SKILL.md dosyalarının başlıklarını toplar."""
    if not SKILLS_DIR.is_dir():
        return ""
    lines: list[str] = []
    for skill_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            first_lines = skill_md.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        # İlk başlık + ilk description satırı
        title = ""
        desc = ""
        for line in first_lines[:20]:
            s = line.strip()
            if s.startswith("#") and not title:
                title = s.lstrip("# ").strip()
            elif s and not s.startswith("#") and title and not desc:
                desc = s
                break
        lines.append(f"- **{skill_dir.name}**: {title or skill_dir.name} — {desc[:140]}")
    return "\n".join(lines)


def _collect_rules() -> str:
    if not RULES_DIR.is_dir():
        return ""
    parts: list[str] = []
    for rule in sorted(p for p in RULES_DIR.iterdir() if p.suffix == ".md"):
        content = _read(rule)
        if content:
            parts.append(f"### {rule.stem}\n{content}")
    return "\n\n".join(parts)


def _collect_workflows() -> str:
    if not WORKFLOWS_DIR.is_dir():
        return ""
    names = sorted(p.stem for p in WORKFLOWS_DIR.glob("*.md"))
    if not names:
        return ""
    return "Mevcut iş akışları (workflows/): " + ", ".join(names)


def build_system_prompt() -> str:
    """Tüm bileşenleri birleştirip tek system prompt döner."""
    persona = _read(SYSTEM_PROMPT_PATH)
    rules = _collect_rules()
    skills = _collect_skills()
    workflows = _collect_workflows()

    sections: list[str] = []
    if persona:
        sections.append(persona)
    else:
        sections.append(
            "Sen HackerAgent — otonom bir penetrasyon test uzmanısın. "
            "MCP araçlarını kullanarak hedef sistemler üzerinde yetkili güvenlik testi yap."
        )

    if skills:
        sections.append("## Mevcut Skill'ler\n" + skills)
    if workflows:
        sections.append("## İş Akışları\n" + workflows)
    if rules:
        sections.append("## Operasyonel Kurallar\n" + rules)

    sections.append(
        "## Araç Kullanımı\n"
        "MCP server'ları üzerinden sana 'function' adıyla sunulan araçları kullan. "
        "Araç adları '<server>__<tool>' formatındadır (örn. 'kali-tools__nmap_scan'). "
        "Her araç çağrısından sonra sonucu analiz et, OODA Loop'a göre bir sonraki adımı seç."
    )

    return "\n\n".join(sections)
