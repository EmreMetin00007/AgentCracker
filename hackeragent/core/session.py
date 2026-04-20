"""Session persistence — her turda JSON dump.

~/.hackeragent/sessions/<session_id>.json dosyasına yazar. Çökme sonrası
`hackeragent --resume <id>` ile devam edilebilir. `--resume last` en son
session'ı açar.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from hackeragent.core.config import HACKERAGENT_HOME
from hackeragent.utils.logger import get_logger

log = get_logger(__name__)

SESSIONS_DIR = HACKERAGENT_HOME / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s.strip())
    return s[:40].strip("-") or "session"


@dataclass
class Session:
    """Kaydedilebilir session state."""

    id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: list[dict] = field(default_factory=list)
    total_cost_usd: float = 0.0
    tool_calls_count: int = 0
    target: str = ""
    # İstenirse ek metadata
    metadata: dict = field(default_factory=dict)

    @classmethod
    def new(cls, label: str = "") -> "Session":
        stamp = time.strftime("%Y%m%d-%H%M%S")
        slug = _slugify(label) if label else "session"
        return cls(id=f"{stamp}-{slug}")

    @property
    def path(self) -> Path:
        return SESSIONS_DIR / f"{self.id}.json"

    def save(self) -> None:
        self.updated_at = time.time()
        try:
            self.path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # pragma: no cover
            log.warning("Session kaydedilemedi %s: %s", self.path, e)

    @classmethod
    def load(cls, session_id: str) -> "Session":
        path = SESSIONS_DIR / f"{session_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Session bulunamadı: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    @classmethod
    def load_last(cls) -> "Session | None":
        files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not files:
            return None
        return cls.load(files[-1].stem)

    @classmethod
    def list_all(cls, limit: int = 20) -> list[dict]:
        files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        out: list[dict] = []
        for p in files[:limit]:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                out.append({
                    "id": data.get("id", p.stem),
                    "updated_at": data.get("updated_at", p.stat().st_mtime),
                    "target": data.get("target", ""),
                    "turns": len([m for m in data.get("messages", []) if m.get("role") == "user"]),
                    "cost_usd": data.get("total_cost_usd", 0.0),
                })
            except Exception:
                continue
        return out
