"""Paket-genelinde yapılandırılmış logger."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_configured = False


def setup_logging(level: str = "INFO", file: str | None = None) -> None:
    global _configured
    if _configured:
        return

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # stderr handler — REPL stdout'unu kirletmez
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(logging.Formatter(fmt))
    root.addHandler(stream)

    if file:
        try:
            Path(file).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(file, encoding="utf-8")
            fh.setFormatter(logging.Formatter(fmt))
            root.addHandler(fh)
        except Exception:
            pass

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
