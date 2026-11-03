from __future__ import annotations

import os
import sys

from .base import Backend, BackendError


def create_backend(mock: bool = False) -> Backend:
    if mock or os.environ.get("BB_BACKEND") == "mock":
        from .mock import MockBackend
        return MockBackend()
    if sys.platform == "win32":
        from .windows import WindowsBackend
        return WindowsBackend()
    if sys.platform.startswith("linux"):
        from .bluez import BluezBackend
        return BluezBackend()
    raise RuntimeError(f"不支持的平台: {sys.platform}")


__all__ = ["Backend", "BackendError", "create_backend"]
