"""Crash reporter — fatal exception'ları local dizine yazar.

Sentry-benzeri ama tamamen local. `~/.hackeragent/crashes/<timestamp>.json`
dosyasına traceback + context kaydeder. Kullanıcı bu dosyayı paylaşarak
bug report açabilir.

Kullanım:
    from hackeragent.core.crash_reporter import report_crash, install_excepthook
    install_excepthook()  # main()'de bir kez çağrılır
    try:
        ...
    except Exception:
        report_crash("orchestrator_ask", extra={"session_id": sid})
        raise
"""

from __future__ import annotations

import json
import os
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hackeragent.utils.logger import get_logger

log = get_logger(__name__)


def _crash_dir() -> Path:
    home = Path(os.environ.get("HACKERAGENT_HOME", Path.home() / ".hackeragent"))
    d = home / "crashes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def report_crash(
    component: str,
    extra: dict | None = None,
    exc: BaseException | None = None,
) -> Path | None:
    """Exception traceback'ini local dosyaya yaz ve path döndür.

    Args:
        component: nereden patladı ("orchestrator_ask", "mcp_start", ...)
        extra: ek context (session_id, target, tool_name, vb.)
        exc: explicit exception; verilmezse sys.exc_info() kullanılır

    Returns:
        Yazılan dosyanın path'i, yazılamazsa None.
    """
    try:
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%d-%H%M%S-%f")
        tb_lines: list[str]
        exc_type: str
        exc_msg: str
        if exc is not None:
            tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
            exc_type = type(exc).__name__
            exc_msg = str(exc)
        else:
            info = sys.exc_info()
            if info[0] is None:
                tb_lines = ["(no active exception)"]
                exc_type = "NoException"
                exc_msg = ""
            else:
                tb_lines = traceback.format_exception(*info)
                exc_type = info[0].__name__ if info[0] else "Unknown"
                exc_msg = str(info[1]) if info[1] else ""

        report: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "component": component,
            "exception_type": exc_type,
            "message": exc_msg,
            "traceback": "".join(tb_lines),
            "extra": extra or {},
            "platform": {
                "python": sys.version.split()[0],
                "system": platform.system(),
                "machine": platform.machine(),
            },
        }
        path = _crash_dir() / f"crash_{ts}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        log.warning("💥 Crash raporu yazıldı: %s", path)
        return path
    except Exception as e:  # crash reporter'ın kendisi çökmesin
        log.error("Crash report yazılamadı: %s", e)
        return None


def install_excepthook() -> None:
    """sys.excepthook'a global handler yükle — unhandled exception'lar da kaydedilir."""
    prev = sys.excepthook

    def _hook(exc_type, exc_value, tb):
        try:
            report_crash("unhandled", exc=exc_value)
        except Exception:
            pass
        prev(exc_type, exc_value, tb)

    sys.excepthook = _hook


def list_crashes(limit: int = 20) -> list[dict]:
    """Son N crash raporunu özet olarak listele (en yeni en üstte)."""
    d = _crash_dir()
    files = sorted(d.glob("crash_*.json"), reverse=True)[:limit]
    out: list[dict] = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({
                "file": f.name,
                "timestamp": data.get("timestamp", ""),
                "component": data.get("component", "?"),
                "exception_type": data.get("exception_type", "?"),
                "message": (data.get("message") or "")[:120],
            })
        except Exception:
            continue
    return out
