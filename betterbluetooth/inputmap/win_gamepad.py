"""Windows XInput poller: emit gamepad button/stick events for the test UI.

Xbox (and many DualSense/Switch setups via the Microsoft stack) never reach our
keyboard Raw Input path — without this, the remap page shows no highlight.
"""
from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Callable

from .base import InputEvent
from .codes import label as code_label

# XINPUT_GAMEPAD button bits → our codes (Xbox layout; matches Linux BTN_* names).
_BUTTON_MAP = (
    (0x0001, "BTN_DPAD_UP"),
    (0x0002, "BTN_DPAD_DOWN"),
    (0x0004, "BTN_DPAD_LEFT"),
    (0x0008, "BTN_DPAD_RIGHT"),
    (0x0010, "BTN_START"),
    (0x0020, "BTN_SELECT"),
    (0x0040, "BTN_THUMBL"),
    (0x0080, "BTN_THUMBR"),
    (0x0100, "BTN_TL"),
    (0x0200, "BTN_TR"),
    (0x0400, "BTN_MODE"),
    (0x1000, "BTN_SOUTH"),  # A
    (0x2000, "BTN_EAST"),   # B
    (0x4000, "BTN_WEST"),   # X
    (0x8000, "BTN_NORTH"),  # Y
)
_TRIGGER_THRESHOLD = 30  # 0..255


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


class WinGamepadPoller:
    """Poll XInput slots 0–3; when test_target is set, emit button edge events."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._test_target: str | None = None
        self._on_event: Callable[[InputEvent], None] | None = None
        self._lock = threading.Lock()
        self._prev: dict[int, set[str]] = {}
        self._prev_sticks: dict[int, tuple[float, float, float, float]] = {}
        self._dll = None
        self._get_state = None
        if sys.platform == "win32":
            for name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
                try:
                    self._dll = ctypes.WinDLL(name)
                    break
                except OSError:
                    continue
            if self._dll is not None:
                fn = self._dll.XInputGetState
                fn.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
                fn.restype = wintypes.DWORD
                self._get_state = fn

    def set_on_event(self, cb: Callable[[InputEvent], None] | None) -> None:
        self._on_event = cb

    def set_test_target(self, device_key: str | None) -> None:
        with self._lock:
            self._test_target = device_key
            if device_key is None:
                self._prev.clear()

    def start(self) -> None:
        if self._get_state is None:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="bb-xinput", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self) -> None:
        assert self._get_state is not None
        while not self._stop.is_set():
            with self._lock:
                test = self._test_target
            if not test:
                self._stop.wait(0.2)
                continue
            for idx in range(4):
                state = XINPUT_STATE()
                if self._get_state(idx, ctypes.byref(state)) != 0:
                    self._prev.pop(idx, None)
                    continue
                pressed = self._decode(state.Gamepad)
                prev = self._prev.get(idx, set())
                if self._on_event:
                    for code in pressed - prev:
                        self._on_event(InputEvent(test, code, True, code_label(code)))
                    for code in prev - pressed:
                        self._on_event(InputEvent(test, code, False, code_label(code)))
                lx = max(-1.0, min(1.0, state.Gamepad.sThumbLX / 32767.0))
                ly = max(-1.0, min(1.0, -state.Gamepad.sThumbLY / 32767.0))
                rx = max(-1.0, min(1.0, state.Gamepad.sThumbRX / 32767.0))
                ry = max(-1.0, min(1.0, -state.Gamepad.sThumbRY / 32767.0))
                sticks = (lx, ly, rx, ry)
                prev_s = self._prev_sticks.get(idx)
                if self._on_event and (prev_s is None or any(abs(a - b) > 0.04 for a, b in zip(sticks, prev_s))):
                    self._on_event(InputEvent(test, "ABS_X", True, f"{lx:.3f}"))
                    self._on_event(InputEvent(test, "ABS_Y", True, f"{ly:.3f}"))
                    self._on_event(InputEvent(test, "ABS_RX", True, f"{rx:.3f}"))
                    self._on_event(InputEvent(test, "ABS_RY", True, f"{ry:.3f}"))
                    self._prev_sticks[idx] = sticks
                self._prev[idx] = pressed
            self._stop.wait(0.016)

    @staticmethod
    def _decode(pad: XINPUT_GAMEPAD) -> set[str]:
        out: set[str] = set()
        buttons = int(pad.wButtons)
        for bit, code in _BUTTON_MAP:
            if buttons & bit:
                out.add(code)
        if pad.bLeftTrigger >= _TRIGGER_THRESHOLD:
            out.add("BTN_TL2")
        if pad.bRightTrigger >= _TRIGGER_THRESHOLD:
            out.add("BTN_TR2")
        return out
