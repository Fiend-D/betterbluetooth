from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from . import APP_DISPLAY_NAME, APP_NAME
from .config import IS_WINDOWS


def _command() -> list[str]:
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return [appimage]
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = sys.executable
    if IS_WINDOWS:
        pyw = Path(exe).with_name("pythonw.exe")
        if pyw.exists():
            exe = str(pyw)
    return [exe, str(Path(__file__).resolve().parent / "__main__.py")]


def _desktop_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / f"{APP_NAME.lower()}.desktop"


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_enabled() -> bool:
    if IS_WINDOWS:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_NAME)
                return True
        except OSError:
            return False
    return _desktop_file().exists()


def set_enabled(enabled: bool) -> None:
    cmd = _command()
    if IS_WINDOWS:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                value = " ".join(f'"{c}"' for c in cmd) + " --minimized"
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return
    path = _desktop_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_DISPLAY_NAME}\n"
            f"Exec={shlex.join(cmd)} --minimized\n"
            "Icon=bluetooth\n"
            "X-GNOME-Autostart-enabled=true\n"
            "X-GNOME-Autostart-Delay=5\n",
            "utf-8",
        )
    elif path.exists():
        path.unlink()
