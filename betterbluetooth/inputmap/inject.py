"""Cross-platform synthetic key injection for gamepad → keyboard remaps."""
from __future__ import annotations

import sys

from .codes import KEY_TO_VK


def send_key(code: str, pressed: bool) -> None:
    if code not in KEY_TO_VK and not code.startswith("KEY_"):
        return
    if sys.platform == "win32":
        _win_send(code, pressed)
    elif sys.platform.startswith("linux"):
        _linux_send(code, pressed)


def _win_send(code: str, pressed: bool) -> None:
    import ctypes
    from ctypes import wintypes

    vk = KEY_TO_VK.get(code)
    if vk is None:
        return

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    inp = INPUT()
    inp.type = 1
    inp.union.ki = KEYBDINPUT(vk, 0, 0 if pressed else 2, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


_linux_ui = None


def _linux_send(code: str, pressed: bool) -> None:
    global _linux_ui
    try:
        from evdev import UInput, ecodes
    except ImportError:
        return
    key_code = getattr(ecodes, code, None) or ecodes.ecodes.get(code)
    if key_code is None:
        return
    if _linux_ui is None:
        try:
            _linux_ui = UInput({ecodes.EV_KEY: list(KEY_TO_VK)}, name="BetterBluetooth Gamepad Keys")
        except OSError:
            return
    _linux_ui.write(ecodes.EV_KEY, key_code, 1 if pressed else 0)
    _linux_ui.syn()
