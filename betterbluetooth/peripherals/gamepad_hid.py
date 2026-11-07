"""Windows HID / XInput battery readers for mainstream gamepads (Xbox, DualSense/DS4, Switch).

Complements (and can replace) the Nintendo-only SwitchControllerSource for battery display.
Bluetooth Classic gamepads rarely expose GATT Battery; we read from the HID path or XInput.
"""
from __future__ import annotations

import asyncio
import ctypes
import re
import sys
import time
from ctypes import wintypes

import hid

from ..models import Device, DeviceKind, normalize_address
from . import PeripheralSource

NINTENDO = 0x057E
SONY = 0x054C
MICROSOFT = 0x045E

NINTENDO_PRODUCTS = {
    0x2006: "Joy-Con (L)",
    0x2007: "Joy-Con (R)",
    0x2009: "Pro Controller",
    0x200E: "Joy-Con 充电握把",
}
SONY_PRODUCTS = {
    0x05C4: "DualShock 4",
    0x09CC: "DualShock 4",
    0x0BA0: "DualShock 4",
    0x0CE6: "DualSense",
    0x0DF2: "DualSense Edge",
}
# Common Xbox Bluetooth / wireless dongle PIDs (not exhaustive).
XBOX_PRODUCTS = {
    0x02E0: "Xbox Wireless Controller",
    0x02FD: "Xbox Wireless Controller",
    0x0B13: "Xbox Wireless Controller",
    0x0B20: "Xbox Wireless Controller",
    0x0B22: "Xbox Wireless Controller",
}

SUBCMD_GET_VOLTAGE = 0x50
NEUTRAL_RUMBLE = bytes([0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40])
_SWITCH_LEVEL = {8: 100, 6: 70, 4: 40, 2: 15, 0: 0}
_HEX_MAC = re.compile(r"^[0-9a-fA-F]{12}$")
_XINPUT_LEVEL = {0: 5, 1: 30, 2: 60, 3: 100}  # EMPTY/LOW/MED/FULL


def _bt_address(serial: str | None) -> str | None:
    serial = (serial or "").replace(":", "").replace("-", "").strip()
    return normalize_address(serial) if _HEX_MAC.match(serial) else None


def _guess_names(*names: str) -> list[str]:
    out = []
    for n in names:
        n = (n or "").strip()
        if n and n not in out:
            out.append(n)
    return out


def _read_switch_battery(dev: hid.device, counter: int, timeout: float = 0.55) -> tuple[int, bool] | None:
    try:
        dev.write(bytes([0x01, counter & 0x0F]) + NEUTRAL_RUMBLE + bytes([SUBCMD_GET_VOLTAGE]) + bytes(38))
    except OSError:
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = dev.read(64, 80)
        if len(data) < 3 or data[0] not in (0x21, 0x30, 0x31):
            continue
        nibble = data[2] >> 4
        return _SWITCH_LEVEL.get(nibble & 0x0E, 0), bool(nibble & 0x01)
    return None


def _read_sony_battery(dev: hid.device, pid: int) -> tuple[int, bool] | None:
    """Best-effort DualShock 4 / DualSense battery from an input report."""
    try:
        # Prefer feature/input report that carries battery; fall back to a short read.
        if pid in (0x0CE6, 0x0DF2):
            # DualSense BT often uses report 0x31; USB uses 0x01.
            for report_id, offset in ((0x01, 53), (0x31, 53)):
                try:
                    got = dev.get_input_report(report_id, 64)
                    if got and len(got) > offset:
                        raw = got[offset]
                        level = min(100, max(0, (raw & 0x0F) * 10 + 5))
                        charging = bool(raw & 0x10)
                        return level, charging
                except Exception:
                    continue
        else:
            # DualShock 4: USB report 0x01 byte 30; BT report 0x11 byte 30.
            for report_id in (0x01, 0x11):
                try:
                    got = dev.get_input_report(report_id, 64)
                    if got and len(got) > 30:
                        raw = got[30]
                        level = min(100, max(0, (raw & 0x0F) * 10 + 5))
                        charging = bool(raw & 0x10)
                        return level, charging
                except Exception:
                    continue
        data = dev.read(64, 120)
        if not data:
            return None
        if pid in (0x0CE6, 0x0DF2) and len(data) > 53:
            raw = data[53]
            return min(100, max(0, (raw & 0x0F) * 10 + 5)), bool(raw & 0x10)
        if len(data) > 30:
            raw = data[30]
            return min(100, max(0, (raw & 0x0F) * 10 + 5)), bool(raw & 0x10)
    except OSError:
        return None
    return None


def _xinput_batteries() -> list[Device]:
    if sys.platform != "win32":
        return []
    dll = None
    for name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            dll = ctypes.WinDLL(name)
            break
        except OSError:
            continue
    if dll is None:
        return []

    class XINPUT_BATTERY_INFORMATION(ctypes.Structure):
        _fields_ = [("BatteryType", ctypes.c_ubyte), ("BatteryLevel", ctypes.c_ubyte)]

    get_bat = dll.XInputGetBatteryInformation
    get_bat.argtypes = [wintypes.DWORD, ctypes.c_ubyte, ctypes.POINTER(XINPUT_BATTERY_INFORMATION)]
    get_bat.restype = wintypes.DWORD

    # BATTERY_DEVTYPE_GAMEPAD = 0; BATTERY_TYPE_DISCONNECTED = 0; WIRED = 1; ALKALINE = 2; NIMH = 3; UNKNOWN = 0xFF
    out: list[Device] = []
    for idx in range(4):
        info = XINPUT_BATTERY_INFORMATION()
        if get_bat(idx, 0, ctypes.byref(info)) != 0:
            continue
        if info.BatteryType in (0, 0xFF):  # disconnected / unknown
            continue
        if info.BatteryType == 1:  # wired — no wireless battery to show
            continue
        level = _XINPUT_LEVEL.get(info.BatteryLevel)
        if level is None:
            continue
        out.append(Device(
            address=f"xinput:{idx}",
            name="Xbox Wireless Controller",
            kind=DeviceKind.GAMEPAD,
            connected=True,
            battery=level,
            transport="wireless",
            charging=False,
            extra={"via": "XInput", "bt_name": "Xbox Wireless Controller",
                   "bt_names": ["Xbox Wireless Controller", "Xbox Controller", "Controller"]},
        ))
    return out


def scan_gamepads(state: dict) -> list[Device]:
    from ..debuglog import log

    result: list[Device] = []
    seen: set[bytes] = set()
    counter = int(state.get("counter", 0))
    try:
        entries = list(hid.enumerate(0, 0))
    except Exception as e:  # noqa: BLE001
        log("hid", f"enumerate failed: {e}")
        entries = []
    log("hid", f"enumerate={len(entries)} known_scan…")

    for entry in entries:
        vid = entry.get("vendor_id", 0)
        pid = entry.get("product_id", 0)
        path = entry["path"]
        if path in seen:
            continue
        if vid == NINTENDO and pid in NINTENDO_PRODUCTS:
            family = "switch"
            name = NINTENDO_PRODUCTS[pid]
        elif vid == SONY and pid in SONY_PRODUCTS:
            family = "sony"
            name = SONY_PRODUCTS[pid]
        elif vid == MICROSOFT and (pid in XBOX_PRODUCTS or (pid & 0xFF00) in (0x0200, 0x0B00)):
            family = "xbox"
            name = XBOX_PRODUCTS.get(pid, entry.get("product_string") or "Xbox Wireless Controller")
        else:
            continue
        seen.add(path)
        log("hid", f"match vid={vid:04x} pid={pid:04x} family={family} "
            f"product={entry.get('product_string')!r} serial={entry.get('serial_number')!r}")

        product = (entry.get("product_string") or name or "").strip() or name
        serial = entry.get("serial_number") or ""
        address = _bt_address(serial)
        reading: tuple[int, bool] | None = None
        try:
            dev = hid.device()
            dev.open_path(path)
        except OSError:
            # Device present but exclusive (Steam etc.) — still advertise name for merge hints.
            result.append(Device(
                address=f"hid:{vid:04x}:{pid:04x}:{serial or path.hex()[:12]}",
                name=product,
                kind=DeviceKind.GAMEPAD,
                connected=True,
                battery=None,
                transport="wireless",
                extra={"via": "HID", "bt_name": product,
                       "bt_names": _guess_names(product, name),
                       **({"bt_address": address} if address else {})},
            ))
            continue
        try:
            if family == "switch":
                counter = (counter + 1) & 0x0F
                reading = _read_switch_battery(dev, counter)
            elif family == "sony":
                reading = _read_sony_battery(dev, pid)
            elif family == "xbox":
                # Prefer XInput for level; HID open just confirms presence.
                reading = None
        except OSError:
            reading = None
        finally:
            try:
                dev.close()
            except Exception:
                pass

        level, charging = reading if reading else (None, None)
        extra = {
            "via": "HID",
            "bt_name": product,
            "bt_names": _guess_names(product, name),
        }
        if address:
            extra["bt_address"] = address
        result.append(Device(
            address=f"hid:{vid:04x}:{pid:04x}:{serial or path.hex()[:12]}",
            name=product,
            kind=DeviceKind.GAMEPAD,
            connected=True,
            battery=level,
            transport="wireless",
            charging=charging,
            extra=extra,
        ))

    state["counter"] = counter
    # XInput fills Xbox battery when HID path has no level.
    xinput = _xinput_batteries()
    if xinput:
        # If we already have an Xbox HID entry without battery, attach level.
        for xi in xinput:
            attached = False
            for d in result:
                if "xbox" in (d.name or "").lower() and d.battery is None:
                    d.battery = xi.battery
                    d.extra["via"] = "XInput"
                    attached = True
                    break
            if not attached:
                result.append(xi)
    return result


class GamepadHidSource(PeripheralSource):
    name = "Gamepad HID"

    def __init__(self) -> None:
        self._state: dict = {}

    async def devices(self) -> list[Device]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, scan_gamepads, self._state)
