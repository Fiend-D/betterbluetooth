"""Windows gamepad battery: WinRT Gaming.Input + XInput + HID (Switch/Sony).

Bluetooth Classic pads rarely expose GATT Battery. Prefer WinRT TryGetBatteryReport
(Xbox / GIP), then XInput coarse levels, then vendor HID reports.
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
_XINPUT_LEVEL = {0: 5, 1: 30, 2: 60, 3: 100}


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


def _pad_extra(via: str, *names: str, address: str | None = None) -> dict:
    names = _guess_names(*names)
    extra: dict = {
        "via": via,
        "bt_name": names[0] if names else "",
        "bt_names": names + [
            "Xbox Wireless Controller", "Xbox Controller", "Wireless Controller",
            "Pro Controller", "DualSense", "DualShock", "Controller",
        ],
    }
    # Deduplicate while preserving order
    seen: set[str] = set()
    cleaned = []
    for n in extra["bt_names"]:
        if n and n not in seen:
            seen.add(n)
            cleaned.append(n)
    extra["bt_names"] = cleaned
    if address:
        extra["bt_address"] = address
    return extra


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
    try:
        if pid in (0x0CE6, 0x0DF2):
            for report_id, offset in ((0x01, 53), (0x31, 53)):
                try:
                    got = dev.get_input_report(report_id, 64)
                    if got and len(got) > offset:
                        raw = got[offset]
                        return min(100, max(0, (raw & 0x0F) * 10 + 5)), bool(raw & 0x10)
                except Exception:
                    continue
        else:
            for report_id in (0x01, 0x11):
                try:
                    got = dev.get_input_report(report_id, 64)
                    if got and len(got) > 30:
                        raw = got[30]
                        return min(100, max(0, (raw & 0x0F) * 10 + 5)), bool(raw & 0x10)
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

    out: list[Device] = []
    for idx in range(4):
        info = XINPUT_BATTERY_INFORMATION()
        if get_bat(idx, 0, ctypes.byref(info)) != 0:
            continue
        # 0=disconnected, 1=wired, 0xFF=unknown — skip those
        if info.BatteryType in (0, 1, 0xFF):
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
            extra=_pad_extra("XInput", "Xbox Wireless Controller"),
        ))
    return out


def _winrt_batteries() -> list[Device]:
    """Xbox / GIP / many XInput pads via Windows.Gaming.Input.TryGetBatteryReport."""
    if sys.platform != "win32":
        return []
    out: list[Device] = []
    try:
        from winrt.windows.gaming.input import Gamepad, RawGameController
    except ImportError:
        return []
    battery_status_charging = None
    try:
        from winrt.windows.system.power import BatteryStatus
        battery_status_charging = BatteryStatus.CHARGING
    except Exception:
        try:
            from winrt.windows.devices.power import BatteryStatus as _BS  # type: ignore
            battery_status_charging = getattr(_BS, "CHARGING", None)
        except Exception:
            pass

    def _from_report(report, name: str, addr: str, via: str) -> Device | None:
        if report is None:
            return None
        try:
            rem = report.remaining_capacity_in_milliwatt_hours
            full = report.full_charge_capacity_in_milliwatt_hours
            status = getattr(report, "status", None)
        except Exception:
            return None
        if rem is None or full is None or full <= 0:
            return None
        level = int(round(max(0, min(100, (rem / full) * 100))))
        charging = bool(battery_status_charging is not None and status == battery_status_charging)
        return Device(
            address=addr,
            name=name or "Gamepad",
            kind=DeviceKind.GAMEPAD,
            connected=True,
            battery=level,
            transport="wireless",
            charging=charging,
            extra=_pad_extra(via, name or "Gamepad", "Xbox Wireless Controller", "Wireless Controller"),
        )

    try:
        pads = list(Gamepad.gamepads)
    except Exception:
        pads = []
    for i, pad in enumerate(pads):
        try:
            report = pad.try_get_battery_report()
        except Exception:
            continue
        dev = _from_report(report, "Xbox Wireless Controller", f"winrt-gamepad:{i}", "WinRT Gamepad")
        if dev:
            out.append(dev)

    try:
        raws = list(RawGameController.raw_game_controllers)
    except Exception:
        raws = []
    for i, pad in enumerate(raws):
        try:
            report = pad.try_get_battery_report()
            name = (getattr(pad, "display_name", None) or "Wireless Controller")
            if callable(name):
                name = name()
            name = str(name or "Wireless Controller")
        except Exception:
            continue
        # Skip if we already have a WinRT Gamepad reading (often the same physical pad).
        if any(d.battery is not None for d in out) and "xbox" in name.lower():
            continue
        dev = _from_report(report, name, f"winrt-raw:{i}", "WinRT Raw")
        if dev:
            out.append(dev)
    return out


def scan_gamepads(state: dict) -> list[Device]:
    from ..debuglog import log

    result: list[Device] = []
    seen: set[bytes] = set()
    counter = int(state.get("counter", 0))

    # 1) WinRT first — most reliable for Xbox Bluetooth on modern Windows.
    winrt = _winrt_batteries()
    log("battery", f"winrt={len(winrt)} " + ", ".join(f"{d.name}:{d.battery}%" for d in winrt))
    result.extend(winrt)

    # 2) XInput coarse levels (often fails on BT Xbox; still useful when it works).
    xinput = _xinput_batteries()
    log("battery", f"xinput={len(xinput)} " + ", ".join(f"{d.name}:{d.battery}%" for d in xinput))
    for xi in xinput:
        if any(d.battery is not None and "xbox" in (d.name or "").lower() for d in result):
            # Already have a better WinRT reading.
            for d in result:
                if d.battery is None and "xbox" in (d.name or "").lower():
                    d.battery = xi.battery
                    d.extra["via"] = "XInput"
            continue
        result.append(xi)

    # 3) HID for Switch / Sony (and Xbox presence without level).
    try:
        entries = list(hid.enumerate(0, 0))
    except Exception as e:  # noqa: BLE001
        log("hid", f"enumerate failed: {e}")
        entries = []
    log("hid", f"enumerate={len(entries)}")

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
        product = (entry.get("product_string") or name or "").strip() or name
        serial = entry.get("serial_number") or ""
        address = _bt_address(serial)
        log("hid", f"match vid={vid:04x} pid={pid:04x} family={family} "
            f"product={product!r} serial={serial!r}")

        reading: tuple[int, bool] | None = None
        try:
            dev = hid.device()
            dev.open_path(path)
        except OSError as e:
            log("hid", f"open failed {family}: {e}")
            # Still publish presence for merge / kind hints.
            if family != "xbox" or not any("xbox" in (d.name or "").lower() for d in result):
                result.append(Device(
                    address=f"hid:{vid:04x}:{pid:04x}:{serial or path.hex()[:12]}",
                    name=product,
                    kind=DeviceKind.GAMEPAD,
                    connected=True,
                    battery=None,
                    transport="wireless",
                    extra=_pad_extra("HID", product, name, address=address),
                ))
            continue
        try:
            if family == "switch":
                counter = (counter + 1) & 0x0F
                reading = _read_switch_battery(dev, counter)
            elif family == "sony":
                reading = _read_sony_battery(dev, pid)
        except OSError as e:
            log("hid", f"read failed {family}: {e}")
            reading = None
        finally:
            try:
                dev.close()
            except Exception:
                pass

        level, charging = reading if reading else (None, None)
        log("hid", f"{family} battery={level} charging={charging}")
        if family == "xbox":
            # Prefer WinRT/XInput levels already collected; only fill gaps.
            for d in result:
                if "xbox" in (d.name or "").lower() and d.battery is None and level is not None:
                    d.battery = level
                    d.charging = charging
            continue
        result.append(Device(
            address=f"hid:{vid:04x}:{pid:04x}:{serial or path.hex()[:12]}",
            name=product,
            kind=DeviceKind.GAMEPAD,
            connected=True,
            battery=level,
            transport="wireless",
            charging=charging,
            extra=_pad_extra("HID", product, name, address=address),
        ))

    state["counter"] = counter
    log("battery", "scan_done=" + ", ".join(f"{d.name}:{d.battery}" for d in result)[:500])
    return result


class GamepadHidSource(PeripheralSource):
    name = "Gamepad HID"

    def __init__(self) -> None:
        self._state: dict = {}

    async def devices(self) -> list[Device]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, scan_gamepads, self._state)
