"""Joy-Con / Pro Controller: optional keep-alive (report mode 0x30) and button test events."""
from __future__ import annotations

import threading
from typing import Callable

from .base import InputEvent
from .codes import label as code_label

NINTENDO = 0x057E
PRODUCTS = {0x2006: "L", 0x2007: "R", 0x2009: "Pro", 0x200E: "Grip"}
NEUTRAL_RUMBLE = bytes([0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40])
SUBCMD_SET_INPUT_MODE = 0x03
MODE_FULL = 0x30

# Byte 3–5 button bits for full input reports (simplified shared map).
_PRO_BUTTONS = {
    # (byte_index, bit): code  — based on standard full-report layout
    (3, 0): "JC_Y", (3, 1): "JC_X", (3, 2): "JC_B", (3, 3): "JC_A",
    (3, 6): "JC_R", (3, 7): "JC_ZR",
    (4, 0): "JC_MINUS", (4, 1): "JC_PLUS", (4, 2): "JC_R_STICK", (4, 3): "JC_L_STICK",
    (4, 4): "JC_HOME", (4, 5): "JC_CAPTURE",
    (5, 0): "JC_DOWN", (5, 1): "JC_UP", (5, 2): "JC_RIGHT", (5, 3): "JC_LEFT",
    (5, 6): "JC_L", (5, 7): "JC_ZL",
}


class JoyConKeeper:
    """Keeps selected Joy-Cons in full report mode and optionally emits button test events."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._targets: dict[str, dict] = {}  # device_key → hints
        self._rules: dict[str, dict[str, list[str]]] = {}  # device_key → from→to_codes
        self._test_target: str | None = None
        self._on_event: Callable[[InputEvent], None] | None = None
        self._lock = threading.Lock()
        self._counter = 0
        self._prev: dict[str, set[str]] = {}

    def set_on_event(self, cb: Callable[[InputEvent], None] | None) -> None:
        self._on_event = cb

    def set_targets(self, targets: dict[str, dict], rules: dict[str, dict[str, list[str]]] | None = None) -> None:
        with self._lock:
            self._targets = dict(targets)
            if rules is not None:
                self._rules = dict(rules)

    def set_test_target(self, device_key: str | None) -> None:
        with self._lock:
            self._test_target = device_key

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        try:
            import hid  # noqa: F401
        except ImportError:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="bb-joycon", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self) -> None:
        import hid

        open_devs: dict[bytes, tuple] = {}  # path → (hid.device, key, side)
        while not self._stop.is_set():
            with self._lock:
                targets = dict(self._targets)
                rules = dict(self._rules)
                test = self._test_target
            if not targets and not test:
                for path, (dev, *_rest) in list(open_devs.items()):
                    try:
                        dev.close()
                    except OSError:
                        pass
                open_devs.clear()
                self._stop.wait(0.5)
                continue
            try:
                entries = [e for e in hid.enumerate(NINTENDO, 0) if e.get("product_id") in PRODUCTS]
            except Exception:
                entries = []
            alive = set()
            for entry in entries:
                path = entry["path"]
                alive.add(path)
                key = self._match(entry, targets, test)
                if key is None:
                    continue
                if path not in open_devs:
                    dev = hid.device()
                    try:
                        dev.open_path(path)
                        self._set_mode(dev)
                    except OSError:
                        continue
                    open_devs[path] = (dev, key, PRODUCTS.get(entry.get("product_id", 0), "?"))
                else:
                    open_devs[path] = (open_devs[path][0], key, open_devs[path][2])
            for path in list(open_devs):
                if path not in alive:
                    try:
                        open_devs[path][0].close()
                    except OSError:
                        pass
                    open_devs.pop(path, None)
            for path, (dev, key, _side) in list(open_devs.items()):
                try:
                    data = dev.read(64, 50)
                except OSError:
                    continue
                if not data:
                    # Nudge keep-alive with a no-op rumble packet occasionally.
                    try:
                        self._counter = (self._counter + 1) & 0x0F
                        if self._counter == 0:
                            self._set_mode(dev)
                    except OSError:
                        pass
                    continue
                if data[0] not in (0x30, 0x31, 0x3F) or len(data) < 6:
                    continue
                pressed = self._buttons(data)
                prev = self._prev.get(key, set())
                if key == test and self._on_event:
                    for code in pressed - prev:
                        self._on_event(InputEvent(key, code, True, code_label(code)))
                    for code in prev - pressed:
                        self._on_event(InputEvent(key, code, False, code_label(code)))
                remap = rules.get(key) or {}
                if remap:
                    from .inject import send_key
                    for code in pressed - prev:
                        for to in remap.get(code, []):
                            send_key(to, True)
                    for code in prev - pressed:
                        for to in remap.get(code, []):
                            send_key(to, False)
                self._prev[key] = pressed
            self._stop.wait(0.01)

    def _match(self, entry: dict, targets: dict[str, dict], test: str | None) -> str | None:
        serial = (entry.get("serial_number") or "").replace(":", "").replace("-", "").upper()
        name = PRODUCTS.get(entry.get("product_id", 0), "")
        for key, hint in targets.items():
            addr = (hint.get("address") or key).replace(":", "").upper()
            if serial and serial == addr:
                return key
            hname = (hint.get("name") or "").upper()
            if name and hname and name.upper() in hname:
                return key
            if "JOY-CON" in hname and (
                (name == "L" and "(L)" in hname) or (name == "R" and "(R)" in hname)
            ):
                return key
        if test:
            # Testing: HID serial/name often differs from the Bluetooth list entry.
            # Bind the first unmatched Nintendo pad to the selected device.
            return test
        return None

    def _set_mode(self, dev) -> None:
        self._counter = (self._counter + 1) & 0x0F
        pkt = bytes([0x01, self._counter]) + NEUTRAL_RUMBLE + bytes([SUBCMD_SET_INPUT_MODE, MODE_FULL])
        pkt = pkt.ljust(49, b"\0")
        dev.write(pkt)

    @staticmethod
    def _buttons(data: bytes) -> set[str]:
        out: set[str] = set()
        if data[0] == 0x3F:
            # Simple HID mode: limited buttons in byte 1–2; skip detailed parse.
            return out
        for (idx, bit), code in _PRO_BUTTONS.items():
            if idx < len(data) and data[idx] & (1 << bit):
                out.add(code)
        return out
