"""Windows gamepad poller: XInput + WinRT RawGameController for the test / remap UI.

X-mode pads usually appear on XInput. D-mode (GamepadSpace-Q34U etc.) is often
HID-only — XInput is empty, so we also poll RawGameController by display name.
"""
from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Callable

from .base import InputEvent
from .codes import KEY_TO_VK, label as code_label

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

# WinRT GameControllerButtonLabel name fragments → our codes.
_WGI_LABEL_MAP = {
    "xboxa": "BTN_SOUTH", "a": "BTN_SOUTH", "cross": "BTN_SOUTH",
    "xboxb": "BTN_EAST", "b": "BTN_EAST", "circle": "BTN_EAST",
    "xboxx": "BTN_WEST", "x": "BTN_WEST", "square": "BTN_WEST",
    "xboxy": "BTN_NORTH", "y": "BTN_NORTH", "triangle": "BTN_NORTH",
    "leftshoulder": "BTN_TL", "l1": "BTN_TL",
    "rightshoulder": "BTN_TR", "r1": "BTN_TR",
    "lefttrigger": "BTN_TL2", "l2": "BTN_TL2",
    "righttrigger": "BTN_TR2", "r2": "BTN_TR2",
    "leftthumbstick": "BTN_THUMBL", "l3": "BTN_THUMBL",
    "rightthumbstick": "BTN_THUMBR", "r3": "BTN_THUMBR",
    "menu": "BTN_START", "start": "BTN_START", "options": "BTN_START",
    "view": "BTN_SELECT", "select": "BTN_SELECT", "share": "BTN_SELECT", "back": "BTN_SELECT",
    "mode": "BTN_MODE", "guide": "BTN_MODE", "home": "BTN_MODE",
    "dpadup": "BTN_DPAD_UP", "dpaddown": "BTN_DPAD_DOWN",
    "dpadleft": "BTN_DPAD_LEFT", "dpadright": "BTN_DPAD_RIGHT",
}


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
    """Poll XInput + RawGameController; emit edges for test UI and optional key inject."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._test_target: str | None = None
        self._device_names: dict[str, str] = {}  # device_key → display name
        self._remap_rules: dict[str, list[str]] = {}
        self._remap_on = False
        self._on_event: Callable[[InputEvent], None] | None = None
        self._lock = threading.Lock()
        self._prev: dict[str, set[str]] = {}
        self._prev_sticks: dict[str, tuple[float, float, float, float]] = {}
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
                self._prev_sticks.clear()

    def set_device_names(self, names: dict[str, str]) -> None:
        with self._lock:
            self._device_names = dict(names)

    def set_remap(self, rules: dict[str, list[str]] | None, enabled: bool) -> None:
        with self._lock:
            self._remap_rules = dict(rules or {})
            self._remap_on = bool(enabled and self._remap_rules)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="bb-gamepad", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                test = self._test_target
                names = dict(self._device_names)
                remap_on = self._remap_on
                rules = dict(self._remap_rules)
            if not test and not remap_on:
                self._stop.wait(0.2)
                continue
            target = test
            # Remap without an open test page still needs a device key — use sole name.
            if target is None and remap_on and len(names) == 1:
                target = next(iter(names))
            if target:
                seen = self._poll_xinput(target, remap_on, rules)
                if not seen:
                    self._poll_raw(target, names.get(target) or "", remap_on, rules)
            self._stop.wait(0.016)

    def _emit(self, key: str, code: str, pressed: bool, remap_on: bool, rules: dict) -> None:
        if self._on_event:
            self._on_event(InputEvent(key, code, pressed, code_label(code)))
        if remap_on and code in rules:
            from .inject import send_key
            for to in rules[code]:
                if to in KEY_TO_VK or to.startswith("KEY_"):
                    send_key(to, pressed)

    def _poll_xinput(self, test: str, remap_on: bool, rules: dict) -> bool:
        if self._get_state is None:
            return False
        any_slot = False
        for idx in range(4):
            state = XINPUT_STATE()
            if self._get_state(idx, ctypes.byref(state)) != 0:
                self._prev.pop(f"xi:{idx}", None)
                continue
            any_slot = True
            slot = f"xi:{idx}"
            pressed = self._decode_xinput(state.Gamepad)
            prev = self._prev.get(slot, set())
            for code in pressed - prev:
                self._emit(test, code, True, remap_on, rules)
            for code in prev - pressed:
                self._emit(test, code, False, remap_on, rules)
            lx = max(-1.0, min(1.0, state.Gamepad.sThumbLX / 32767.0))
            ly = max(-1.0, min(1.0, -state.Gamepad.sThumbLY / 32767.0))
            rx = max(-1.0, min(1.0, state.Gamepad.sThumbRX / 32767.0))
            ry = max(-1.0, min(1.0, -state.Gamepad.sThumbRY / 32767.0))
            sticks = (lx, ly, rx, ry)
            prev_s = self._prev_sticks.get(slot)
            if self._on_event and (prev_s is None or any(abs(a - b) > 0.04 for a, b in zip(sticks, prev_s))):
                self._on_event(InputEvent(test, "ABS_X", True, f"{lx:.3f}"))
                self._on_event(InputEvent(test, "ABS_Y", True, f"{ly:.3f}"))
                self._on_event(InputEvent(test, "ABS_RX", True, f"{rx:.3f}"))
                self._on_event(InputEvent(test, "ABS_RY", True, f"{ry:.3f}"))
                self._prev_sticks[slot] = sticks
            self._prev[slot] = pressed
        return any_slot

    def _poll_raw(self, test: str, want_name: str, remap_on: bool, rules: dict) -> None:
        """D-mode / HID pads (GamepadSpace-*) show up here, not on XInput."""
        if sys.platform != "win32":
            return
        try:
            from winrt.windows.gaming.input import RawGameController
            import winrt.system
        except ImportError:
            return
        try:
            pads = list(RawGameController.raw_game_controllers)
        except Exception:
            return
        want = (want_name or "").lower().strip()
        for i, pad in enumerate(pads):
            try:
                name = getattr(pad, "display_name", None) or ""
                if callable(name):
                    name = name()
                name = str(name or "")
            except Exception:
                name = ""
            name_l = name.lower()
            if want and want not in name_l and name_l not in want:
                # Allow GamepadSpace when the BT alias is GamepadSpace-Q34U.
                if not (
                    "gamepadspace" in want and "gamepadspace" in name_l
                    or "xbox" in want and "xbox" in name_l
                ):
                    if len(pads) != 1:
                        continue
            slot = f"raw:{i}:{name_l[:24]}"
            try:
                n_btn = int(pad.get_button_count())
                n_sw = int(pad.get_switch_count())
                n_ax = int(pad.get_axis_count())
            except Exception:
                continue
            try:
                buttons = winrt.system.Array[bool](n_btn) if n_btn else None
                switches = None
                axes = winrt.system.Array[float](n_ax) if n_ax else None
                if n_sw:
                    from winrt.windows.gaming.input import GameControllerSwitchPosition
                    switches = winrt.system.Array[GameControllerSwitchPosition](n_sw)
                pad.get_current_reading(buttons, switches, axes)
            except Exception:
                continue
            pressed: set[str] = set()
            if buttons is not None:
                for bi in range(n_btn):
                    try:
                        if not buttons[bi]:
                            continue
                        label = ""
                        try:
                            label = str(pad.get_button_label(bi) or "")
                        except Exception:
                            label = ""
                        code = self._label_to_code(label, bi)
                        if code:
                            pressed.add(code)
                    except Exception:
                        continue
            prev = self._prev.get(slot, set())
            for code in pressed - prev:
                self._emit(test, code, True, remap_on, rules)
            for code in prev - pressed:
                self._emit(test, code, False, remap_on, rules)
            self._prev[slot] = pressed
            if axes is not None and n_ax >= 4 and self._on_event:
                try:
                    lx = max(-1.0, min(1.0, float(axes[0]) * 2 - 1))
                    ly = max(-1.0, min(1.0, float(axes[1]) * 2 - 1))
                    rx = max(-1.0, min(1.0, float(axes[2]) * 2 - 1))
                    ry = max(-1.0, min(1.0, float(axes[3]) * 2 - 1))
                    sticks = (lx, ly, rx, ry)
                    prev_s = self._prev_sticks.get(slot)
                    if prev_s is None or any(abs(a - b) > 0.04 for a, b in zip(sticks, prev_s)):
                        self._on_event(InputEvent(test, "ABS_X", True, f"{lx:.3f}"))
                        self._on_event(InputEvent(test, "ABS_Y", True, f"{ly:.3f}"))
                        self._on_event(InputEvent(test, "ABS_RX", True, f"{rx:.3f}"))
                        self._on_event(InputEvent(test, "ABS_RY", True, f"{ry:.3f}"))
                        self._prev_sticks[slot] = sticks
                except Exception:
                    pass

    @staticmethod
    def _label_to_code(label: str, index: int) -> str | None:
        key = "".join(ch for ch in (label or "").lower() if ch.isalnum())
        if key in _WGI_LABEL_MAP:
            return _WGI_LABEL_MAP[key]
        # Fallback Xbox-ish index order used by many HID pads.
        fallback = (
            "BTN_SOUTH", "BTN_EAST", "BTN_WEST", "BTN_NORTH",
            "BTN_TL", "BTN_TR", "BTN_TL2", "BTN_TR2",
            "BTN_SELECT", "BTN_START", "BTN_THUMBL", "BTN_THUMBR",
            "BTN_MODE",
        )
        if 0 <= index < len(fallback):
            return fallback[index]
        return f"BTN_{index}"

    @staticmethod
    def _decode_xinput(pad: XINPUT_GAMEPAD) -> set[str]:
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
