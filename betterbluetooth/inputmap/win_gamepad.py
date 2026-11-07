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

# WinRT GameControllerButtonLabel member names → our codes. Labels come from
# the driver; most HID pads report NONE and fall through to the gcdb mapping.
_WGI_LABEL_MAP = {
    "XBOX_A": "BTN_SOUTH", "XBOX_B": "BTN_EAST", "XBOX_X": "BTN_WEST", "XBOX_Y": "BTN_NORTH",
    "CROSS": "BTN_SOUTH", "CIRCLE": "BTN_EAST", "SQUARE": "BTN_WEST", "TRIANGLE": "BTN_NORTH",
    "XBOX_LEFT_BUMPER": "BTN_TL", "XBOX_RIGHT_BUMPER": "BTN_TR",
    "LEFT_BUMPER": "BTN_TL", "RIGHT_BUMPER": "BTN_TR",
    "XBOX_LEFT_TRIGGER": "BTN_TL2", "XBOX_RIGHT_TRIGGER": "BTN_TR2",
    "LEFT_TRIGGER": "BTN_TL2", "RIGHT_TRIGGER": "BTN_TR2",
    "XBOX_LEFT_STICK_BUTTON": "BTN_THUMBL", "XBOX_RIGHT_STICK_BUTTON": "BTN_THUMBR",
    "LEFT_STICK_BUTTON": "BTN_THUMBL", "RIGHT_STICK_BUTTON": "BTN_THUMBR",
    "XBOX_MENU": "BTN_START", "XBOX_START": "BTN_START", "MENU": "BTN_START",
    "START": "BTN_START", "OPTIONS": "BTN_START", "PLUS": "BTN_START",
    "XBOX_VIEW": "BTN_SELECT", "XBOX_BACK": "BTN_SELECT", "VIEW": "BTN_SELECT",
    "BACK": "BTN_SELECT", "SELECT": "BTN_SELECT", "MINUS": "BTN_SELECT",
    "SHARE": "BTN_CAPTURE", "MODE": "BTN_MODE",
    "XBOX_UP": "BTN_DPAD_UP", "XBOX_DOWN": "BTN_DPAD_DOWN",
    "XBOX_LEFT": "BTN_DPAD_LEFT", "XBOX_RIGHT": "BTN_DPAD_RIGHT",
    "UP": "BTN_DPAD_UP", "DOWN": "BTN_DPAD_DOWN", "LEFT": "BTN_DPAD_LEFT", "RIGHT": "BTN_DPAD_RIGHT",
    "XBOX_PADDLE1": "BTN_EXTRA1", "XBOX_PADDLE2": "BTN_EXTRA2",
    "XBOX_PADDLE3": "BTN_EXTRA3", "XBOX_PADDLE4": "BTN_EXTRA4",
    "PADDLE1": "BTN_EXTRA1", "PADDLE2": "BTN_EXTRA2", "PADDLE3": "BTN_EXTRA3", "PADDLE4": "BTN_EXTRA4",
    "LETTER_C": "BTN_C", "LETTER_Z": "BTN_Z",
}

# SDL_GameControllerDB target names → our codes.
_GCDB_TARGET = {
    "a": "BTN_SOUTH", "b": "BTN_EAST", "x": "BTN_WEST", "y": "BTN_NORTH",
    "back": "BTN_SELECT", "start": "BTN_START", "guide": "BTN_MODE",
    "leftshoulder": "BTN_TL", "rightshoulder": "BTN_TR",
    "leftstick": "BTN_THUMBL", "rightstick": "BTN_THUMBR",
    "lefttrigger": "BTN_TL2", "righttrigger": "BTN_TR2",
    "dpup": "BTN_DPAD_UP", "dpdown": "BTN_DPAD_DOWN",
    "dpleft": "BTN_DPAD_LEFT", "dpright": "BTN_DPAD_RIGHT",
    "misc1": "BTN_CAPTURE",
    "paddle1": "BTN_EXTRA1", "paddle2": "BTN_EXTRA2",
    "paddle3": "BTN_EXTRA3", "paddle4": "BTN_EXTRA4",
}
# HID hat switch (WinRT GameControllerSwitchPosition 1..8, clockwise from up).
_HAT_DIRS = {
    1: ("BTN_DPAD_UP",), 2: ("BTN_DPAD_UP", "BTN_DPAD_RIGHT"),
    3: ("BTN_DPAD_RIGHT",), 4: ("BTN_DPAD_DOWN", "BTN_DPAD_RIGHT"),
    5: ("BTN_DPAD_DOWN",), 6: ("BTN_DPAD_DOWN", "BTN_DPAD_LEFT"),
    7: ("BTN_DPAD_LEFT",), 8: ("BTN_DPAD_UP", "BTN_DPAD_LEFT"),
}
_HAT_MASK = {1: 1, 2: 1 | 2, 3: 2, 4: 4 | 2, 5: 4, 6: 4 | 8, 7: 8, 8: 1 | 8}  # SDL h0.N bits


class _PadMapping:
    """Parsed gcdb entry: button index / hat bit → our codes.

    gcdb axis indices are not used: SDL numbers axes by sorted HID usage,
    while WinRT RawGameController keeps report-descriptor order, so "a3" in
    gcdb is a different axis here (seen on ShanWan D-mode 1949:0402).
    """

    def __init__(self, fields: str) -> None:
        self.buttons: dict[int, str] = {}
        self.hats: dict[tuple[int, int], str] = {}
        for item in fields.split(","):
            target, _, src = item.partition(":")
            code = _GCDB_TARGET.get(target)
            if not code or not src:
                continue
            try:
                if src.startswith("b"):
                    self.buttons[int(src[1:])] = code
                elif src.startswith("h"):
                    hat, _, mask = src[1:].partition(".")
                    self.hats[(int(hat), int(mask))] = code
            except ValueError:
                continue


def _make_array(system, types: tuple, size: int):
    """winrt.system.Array(type, size); accepted type spellings vary across pywinrt releases."""
    last: Exception | None = None
    for t in types:
        if t is None:
            continue
        try:
            return system.Array(t, max(size, 0))
        except Exception as e:  # noqa: BLE001
            last = e
    raise last or TypeError("no array type")


def _lookup_mapping(vid: int, pid: int) -> _PadMapping | None:
    try:
        from .gcdb_windows import MAPPINGS
    except ImportError:
        return None
    entry = MAPPINGS.get(f"{vid:04x}:{pid:04x}")
    return _PadMapping(entry[1]) if entry else None


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
        self._remap_target: str | None = None
        self._on_event: Callable[[InputEvent], None] | None = None
        self._lock = threading.Lock()
        self._prev: dict[str, set[str]] = {}
        self._prev_sticks: dict[str, tuple[float, float, float, float]] = {}
        self._mappings: dict[tuple[int, int], _PadMapping | None] = {}
        self._read_errors: set[str] = set()
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

    def set_remap(self, rules: dict[str, list[str]] | None, enabled: bool,
                  target: str | None = None) -> None:
        with self._lock:
            self._remap_rules = dict(rules or {})
            self._remap_on = bool(enabled and self._remap_rules)
            self._remap_target = target

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
                remap_target = self._remap_target
            if not test and not remap_on:
                self._stop.wait(0.2)
                continue
            target = test or (remap_target if remap_on else None)
            if target:
                want = names.get(target) or ""
                # D-mode GamepadSpace is HID-only; don't let a leftover X-mode
                # Xbox slot steal the highlight while testing the D-mode device.
                if "gamepadspace" in want.lower():
                    self._poll_raw(target, want, remap_on, rules)
                else:
                    seen = self._poll_xinput(target, remap_on, rules)
                    if not seen:
                        self._poll_raw(target, want, remap_on, rules)
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
                n_btn = int(pad.button_count)
                n_sw = int(pad.switch_count)
                n_ax = int(pad.axis_count)
            except Exception:
                continue
            try:
                vid, pid = int(pad.hardware_vendor_id), int(pad.hardware_product_id)
            except Exception:
                vid = pid = 0
            if (vid, pid) not in self._mappings:
                mapping = _lookup_mapping(vid, pid)
                self._mappings[(vid, pid)] = mapping
                from ..debuglog import log
                log("pad", f"raw controller {name!r} vid={vid:04x} pid={pid:04x} "
                    f"buttons={n_btn} switches={n_sw} axes={n_ax} gcdb={'yes' if mapping else 'no'}")
            mapping = self._mappings[(vid, pid)]
            try:
                from winrt.windows.gaming.input import GameControllerSwitchPosition
                buttons = _make_array(winrt.system, (bool, "?"), n_btn)
                switches = _make_array(winrt.system, (GameControllerSwitchPosition, "i"), n_sw)
                axes = _make_array(winrt.system, (getattr(winrt.system, "Double", None), "d", float), n_ax)
                pad.get_current_reading(buttons, switches, axes)
            except Exception as e:
                if slot not in self._read_errors:
                    self._read_errors.add(slot)
                    from ..debuglog import log
                    log("pad", f"raw reading failed {name!r}: {e}")
                continue
            pressed: set[str] = set()
            if buttons is not None:
                for bi in range(n_btn):
                    try:
                        if not buttons[bi]:
                            continue
                        try:
                            raw_label = pad.get_button_label(bi)
                            label = getattr(raw_label, "name", "") or ""
                        except Exception:
                            label = ""
                        pressed.add(self._button_code(label, bi, mapping))
                    except Exception:
                        continue
            if switches is not None:
                for si in range(n_sw):
                    try:
                        pos = int(switches[si])
                    except Exception:
                        continue
                    if mapping and mapping.hats:
                        bits = _HAT_MASK.get(pos, 0)
                        for (hat, mask), code in mapping.hats.items():
                            if hat == si and bits & mask:
                                pressed.add(code)
                    elif si == 0:
                        pressed.update(_HAT_DIRS.get(pos, ()))
            prev = self._prev.get(slot, set())
            for code in pressed - prev:
                self._emit(test, code, True, remap_on, rules)
            for code in prev - pressed:
                self._emit(test, code, False, remap_on, rules)
            self._prev[slot] = pressed
            if axes is not None and n_ax >= 2 and self._on_event:
                # WinRT keeps descriptor order. Gamepad descriptors list the
                # sticks first (X, Y, then Z/Rz or Rx/Ry for the right stick)
                # with triggers after — confirmed on ShanWan D-mode (6 axes:
                # 0/1 left, 2/3 right, 4/5 triggers).
                def _axis(i: int) -> float:
                    if i >= n_ax:
                        return 0.0
                    return max(-1.0, min(1.0, float(axes[i]) * 2 - 1))

                try:
                    sticks = (_axis(0), _axis(1), _axis(2) if n_ax >= 4 else 0.0,
                              _axis(3) if n_ax >= 4 else 0.0)
                    lx, ly, rx, ry = sticks
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
    def _button_code(label: str, index: int, mapping: _PadMapping | None) -> str:
        """OS button label → gcdb mapping by index → generic BTN_<n>."""
        if label in _WGI_LABEL_MAP:
            return _WGI_LABEL_MAP[label]
        if mapping and index in mapping.buttons:
            return mapping.buttons[index]
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
