"""Append-only diagnostic log so Windows users can send us a file after testing."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from .config import data_dir

_lock = threading.Lock()
_path: Path | None = None


def log_path() -> Path:
    global _path
    if _path is None:
        _path = data_dir() / "debug-input.log"
    return _path


def log(section: str, message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{section}] {message}\n"
    try:
        with _lock:
            p = log_path()
            if p.exists() and p.stat().st_size > 2_000_000:
                p.replace(p.with_suffix(".log.old"))
            with p.open("a", encoding="utf-8") as f:
                f.write(line)
    except OSError:
        pass
