"""Windows gamepad battery: PnP / WinRT / XInput / vendor HID.

Priority (Bluetooth Xbox etc.):
1. Windows PnP DEVPKEY_Bluetooth_BatteryLevel (exact %, Settings source)
2. WinRT Gaming.Input TryGetBatteryReport (cached; rate-limits)
3. XInput coarse buckets (dongle / older firmware)
4. Vendor HID: Switch / Sony / 8BitDo / Flydigi

Vendor/product ids and report layouts follow SDL (src/joystick/usb_ids.h and
hidapi/SDL_hidapi_*.c) and usb.ids. Models without a public protocol get no
HID battery reader — they report "unreadable" instead of an invented value.
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
EIGHTBITDO = 0x2DC8
GAMESIR = 0x3537
FLYDIGI_V1 = 0x04B4  # Cypress VID used by Flydigi V1 dongles
FLYDIGI_V2 = 0x37D7
BETOP = 0x11C0       # usb.ids: "Betop"
SHANWAN = 0x2563     # usb.ids: ShenZhen ShanWan Technology
SHANWAN_ALT = 0x20BC  # usb.ids: ShenZhen ShanWan Technology (also many OEM clones)
SHANWAN_ALT2 = 0x25F0  # usb.ids: ShanWan

NINTENDO_PRODUCTS = {
    0x2006: "Joy-Con (L)",
    0x2007: "Joy-Con (R)",
    0x2009: "Pro Controller",
    0x200E: "Joy-Con 充电握把",
}
SONY_PRODUCTS = {
    0x05C4: "DualShock 4",
    0x09CC: "DualShock 4",
    0x0BA0: "DualShock 4",  # Sony wireless adapter
    0x0CE6: "DualSense",
    0x0DF2: "DualSense Edge",
}
SONY_DS5 = frozenset({0x0CE6, 0x0DF2})
XBOX_PRODUCTS = {
    0x02E0: "Xbox One S Controller",
    0x02EA: "Xbox One S Controller",
    0x02FD: "Xbox One S Controller",
    0x0B20: "Xbox One S Controller",
    0x02E3: "Xbox Elite Controller",
    0x0B00: "Xbox Elite Series 2",
    0x0B05: "Xbox Elite Series 2",
    0x0B22: "Xbox Elite Series 2",
    0x0B12: "Xbox Series X|S Controller",
    0x0B13: "Xbox Series X|S Controller",
    0x0B0A: "Xbox Adaptive Controller",
    0x0B0C: "Xbox Adaptive Controller",
    0x0B21: "Xbox Adaptive Controller",
}
# PIDs used ONLY over Bluetooth (SDL usb_ids.h). WinRT TryGetBatteryReport for
# these often returns remain=100 full=1000 → fake "10%". Never trust that ratio.
# Many Chinese pads (ShanWan / GameSir / Flydigi / Betop / EasySMX / …) spoof the
# same VID/PID in X-Input Bluetooth mode — same fake WinRT bucket, same empty
# XInput battery, same missing PnP property. Show "unreadable", never 10%.
XBOX_BT_ONLY_PIDS = frozenset({
    0x02E0,  # Xbox One S Rev1 BT
    0x02FD,  # Xbox One S Rev2 BT (also common ShanWan/GameSir X-mode spoof)
    0x0B05,  # Elite Series 2 BT
    0x0B0C,  # Adaptive BT
    0x0B13,  # Series X BLE
    0x0B20,  # One S Rev2 BLE
    0x0B21,  # Adaptive BLE
    0x0B22,  # Elite Series 2 BLE
})
EIGHTBITDO_PRODUCTS = {
    0x6000: "8BitDo SF30 Pro", 0x6100: "8BitDo SF30 Pro",
    0x6001: "8BitDo SN30 Pro", 0x6101: "8BitDo SN30 Pro",
    0x6003: "8BitDo Pro 2", 0x6006: "8BitDo Pro 2",
    0x6009: "8BitDo Pro 3",
    0x6012: "8BitDo Ultimate 2 Wireless", 0x301B: "8BitDo Ultimate 2C Wireless",
    0x202F: "8BitDo Ultimate 3",
}
# SDL reports 8BitDo power only in its "enhanced" report. Ultimate 3 sends it
# by default; Ultimate 2 Wireless only with v1.03+ firmware (34-byte reports).
# The others need feature report 0x06, which switches the pad's input report
# format for every app (games included) — never sent here.
EIGHTBITDO_PASSIVE_BATTERY = frozenset({0x202F, 0x6012})
GAMESIR_PRODUCTS = {
    # Only ids listed in SDL usb_ids.h; other GameSir pads keep their own name.
    0x10B8: "GameSir G7 Pro 8K",
    0x103C: "GameSir Tarantula 8K",
}
FLYDIGI_PRODUCTS = {
    0x2412: "Flydigi Gamepad",
    0x2501: "Flydigi Apex", 0x2502: "Flydigi Apex 6",
    0x2401: "Flydigi Vader",
}
_HID_READERS = frozenset({"switch", "sony", "8bitdo", "flydigi"})

SUBCMD_GET_VOLTAGE = 0x50
NEUTRAL_RUMBLE = bytes([0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40])
_HEX_MAC = re.compile(r"^[0-9a-fA-F]{12}$")
_XINPUT_LEVEL = {0: 5, 1: 30, 2: 60, 3: 100}
_WINRT_CACHE: dict[str, tuple[float, int, bool]] = {}  # key → (ts, level, charging)
_WINRT_CACHE_TTL = 45.0


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
            "8BitDo", "GameSir", "Flydigi", "BETOP",
        ],
    }
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


def _unwrap_num(v) -> int | None:
    if v is None:
        return None
    if hasattr(v, "value"):
        try:
            v = v.value
        except Exception:
            return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


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
        # SDL_hidapi_switch: level 0..8 in bits 5-7 (step 2), bit 4 = charging.
        b = data[2]
        level = (b & 0xE0) >> 4
        return int(round(level / 8 * 100)), bool(b & 0x10)
    return None


def _sony_percent(raw: int, ds5: bool) -> tuple[int, bool] | None:
    """SDL_hidapi_ps4 / ps5 battery byte → (percent, charging)."""
    level = raw & 0x0F
    if ds5:
        status = (raw >> 4) & 0x0F
        if level == 0x0C:
            return None
        if status == 0:
            return min(level * 10 + 5, 100), False
        if status == 1:
            return min(level * 10 + 5, 100), True
        if status == 2:
            return 100, True
        return None
    if raw & 0x10:
        if level <= 10:
            return min(level * 10 + 5, 100), True
        if level == 11:
            return 100, True
        return None
    return min(level * 10 + 5, 100), False


def _read_sony_battery(dev: hid.device, pid: int, timeout: float = 0.3) -> tuple[int, bool] | None:
    """Passive stream read. Short reports (simple BT 0x01, 10 bytes) carry no battery."""
    ds5 = pid in SONY_DS5
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            data = dev.read(100, 60)
            if not data:
                continue
            rid, n = data[0], len(data)
            if ds5:
                if rid == 0x01 and n >= 64:
                    return _sony_percent(data[53], True)
                if rid == 0x31 and n >= 55:
                    return _sony_percent(data[54], True)
            else:
                if rid == 0x01 and n >= 64:
                    return _sony_percent(data[30], False)
                if 0x11 <= rid <= 0x19 and n >= 33:
                    return _sony_percent(data[32], False)
    except OSError:
        return None
    return None


def _read_8bitdo_battery(dev: hid.device, pid: int, timeout: float = 0.3) -> tuple[int, bool] | None:
    """Enhanced report (0x04 USB / 0x01 BT, byte 14) per SDL_hidapi_8bitdo. Read-only."""
    if pid not in EIGHTBITDO_PASSIVE_BATTERY:
        return None
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            data = dev.read(64, 60)
            if not data or data[0] not in (0x01, 0x04):
                continue
            if pid == 0x6012 and len(data) < 34:
                return None
            if len(data) < 15:
                continue
            raw = data[14]
            level = raw & 0x7F
            if level > 100:
                continue
            return level, bool(raw & 0x80) and level < 100
    except OSError:
        return None
    return None


FLYDIGI_V2_UNNUMBERED = frozenset({0x2401, 0x2502})  # Vader 5 / Apex 6


def _read_flydigi_battery(dev: hid.device, vid: int, pid: int) -> tuple[int, bool] | None:
    """Flydigi V2 GET_INFO (0x01) reply byte 11 per SDL_hidapi_flydigi.

    V1 receivers (04B4:2412) expose no battery in SDL, so none is read.
    """
    if vid != FLYDIGI_V2:
        return None
    try:
        cmd = bytearray(32)
        cmd[0:6] = bytes([0x03, 0x5A, 0xA5, 0x01, 2, 0])
        if pid in FLYDIGI_V2_UNNUMBERED:
            cmd[0] = 0
        dev.write(bytes(cmd))
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            data = dev.read(64, 60)
            if not data:
                continue
            if len(data) > 2 and data[0] != 0x5A:
                data = data[1:]
            if len(data) < 12 or data[0] != 0x5A or data[1] != 0xA5 or data[2] != 0x01:
                continue
            raw = data[11]
            status, level = (raw >> 4) & 0x0F, raw & 0x0F
            step = 10 if pid == 0x2502 else 20
            if status == 0:
                return min(100, level * step), False
            if status == 1:
                return min(100, level * step), True
            if status == 2:
                return 100, True
            return None
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


def _winrt_batteries(skip_microsoft: bool = False) -> list[Device]:
    """Per-controller WinRT battery via RawGameController (covers Gamepad too).

    Xbox Bluetooth-only PIDs always report a fake 100/1000 and are skipped by
    id; when PnP already gave the exact Xbox level, Microsoft pads are skipped.
    """
    if sys.platform != "win32":
        return []
    out: list[Device] = []
    try:
        from winrt.windows.gaming.input import RawGameController
    except ImportError:
        return []
    battery_status_charging = None
    try:
        from winrt.windows.system.power import BatteryStatus
        battery_status_charging = BatteryStatus.CHARGING
    except Exception:
        pass

    def _from_report(report, name: str, addr: str, via: str) -> Device | None:
        now = time.monotonic()
        cached = _WINRT_CACHE.get(addr)
        if report is None:
            if cached and now - cached[0] < _WINRT_CACHE_TTL:
                level, charging = cached[1], cached[2]
            else:
                return None
        else:
            rem = _unwrap_num(getattr(report, "remaining_capacity_in_milliwatt_hours", None))
            full = _unwrap_num(getattr(report, "full_charge_capacity_in_milliwatt_hours", None))
            status = getattr(report, "status", None)
            if rem is None or full is None or full <= 0:
                if cached and now - cached[0] < _WINRT_CACHE_TTL:
                    level, charging = cached[1], cached[2]
                else:
                    return None
            else:
                # HaloBattery #108 / #118: Xbox BT reports remain=100 full=1000
                # (and similar 100-step buckets) — not real milliwatt-hours.
                if full == 1000 and rem % 100 == 0:
                    _WINRT_CACHE.pop(addr, None)
                    return None
                level = int(round(max(0, min(100, (rem / full) * 100))))
                charging = bool(battery_status_charging is not None and status == battery_status_charging)
                _WINRT_CACHE[addr] = (now, level, charging)
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
        raws = list(RawGameController.raw_game_controllers)
    except Exception:
        raws = []
    for pad in raws:
        try:
            vid = int(pad.hardware_vendor_id)
            pid = int(pad.hardware_product_id)
        except Exception:
            vid = pid = 0
        if vid == MICROSOFT and (pid in XBOX_BT_ONLY_PIDS or skip_microsoft):
            continue
        try:
            report = pad.try_get_battery_report()
        except Exception:
            report = None
        try:
            name = str(pad.display_name or "")
        except Exception:
            name = ""
        if vid == MICROSOFT:
            name = XBOX_PRODUCTS.get(pid, name or "Xbox Wireless Controller")
        try:
            key = str(pad.non_roamable_id or "") or f"{vid:04x}:{pid:04x}"
        except Exception:
            key = f"{vid:04x}:{pid:04x}"
        dev = _from_report(report, name or "Wireless Controller", f"winrt-raw:{key}", "WinRT Raw")
        if dev:
            dev.extra["vid"], dev.extra["pid"] = vid, pid
            out.append(dev)
    return out


def _pnp_as_devices() -> list[Device]:
    """Expose SetupAPI battery readings as merge helpers (never standalone 2.4G rows).

    Windows already applies these levels in the Bluetooth backend. We only re-emit
    address-keyed shadows so merge can fill gaps. Name-only Hands-Free / Stereo
    endpoints used to appear under「无线外设」as fake gamepads (seen with AS-J18).
    """
    if sys.platform != "win32":
        return []
    try:
        from ..backends.win_setupapi import read_battery_nodes
        from ..models import kind_from_name, strip_bt_name
        nodes = read_battery_nodes()
    except Exception:
        return []
    out: list[Device] = []
    seen: set[str] = set()
    for node in nodes:
        addr = node.get("address") or ""
        if not addr or addr in seen:
            continue
        seen.add(addr)
        level = int(node["level"])
        raw_name = (node.get("name") or "").strip()
        base = strip_bt_name(raw_name) or raw_name or "Bluetooth device"
        kind = kind_from_name(raw_name) or kind_from_name(base) or DeviceKind.OTHER
        names = [n for n in (base, raw_name) if n]
        if kind == DeviceKind.GAMEPAD:
            extra = _pad_extra("PnP", *names, address=addr)
        else:
            extra = {
                "via": "PnP",
                "battery_via": "PnP",
                "bt_address": addr,
                "bt_name": base,
                "bt_names": names,
                "pnp_shadow": True,  # merge must not append as 2.4G
            }
        out.append(Device(
            address=f"pnp:{addr}",
            name=base,
            kind=kind,
            connected=True,
            battery=level,
            transport="wireless",
            extra=extra,
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
    log("hid", f"enumerate={len(entries)}")
    try:
        from .hid_capture import sample as capture_sample
        capture_sample(entries)
    except Exception as e:  # noqa: BLE001
        log("hid", f"capture failed: {e}")
    xbox_bt = any(
        e.get("vendor_id") == MICROSOFT and e.get("product_id") in XBOX_BT_ONLY_PIDS
        for e in entries
    )

    # 0) PnP — same source as Windows Settings (exact %). WinRT mWh ratios
    # often bucket to ~10% and must not win after a full charge.
    pnp = _pnp_as_devices()
    log("battery", f"pnp={len(pnp)} " + ", ".join(f"{d.name}:{d.battery}%" for d in pnp[:6]))
    result.extend(pnp)
    pnp_hit = any(d.battery is not None for d in pnp)

    # 1) WinRT, filtered per controller (Xbox BT-only PIDs report fake 100/1000).
    winrt = _winrt_batteries(skip_microsoft=pnp_hit)
    log("battery", f"winrt={len(winrt)} pnp_hit={pnp_hit} xbox_bt={xbox_bt} "
        + ", ".join(f"{d.name}[{d.extra.get('vid', 0):04x}:{d.extra.get('pid', 0):04x}]:{d.battery}%"
                    for d in winrt))
    for w in winrt:
        w.extra["battery_via"] = w.extra.get("via") or "WinRT Raw"
        w.extra["battery_coarse"] = True
        result.append(w)

    # 2) XInput coarse buckets for Xbox pads WinRT/PnP couldn't read.
    xinput: list[Device] = []
    if not pnp_hit and not any(w.extra.get("vid") == MICROSOFT for w in winrt):
        xinput = _xinput_batteries()
    log("battery", f"xinput={len(xinput)} " + ", ".join(f"{d.name}:{d.battery}%" for d in xinput))
    for xi in xinput:
        xi.extra["battery_via"] = "XInput"
        xi.extra["battery_coarse"] = True
        result.append(xi)

    # 3) Vendor HID
    emitted: dict[tuple, Device] = {}

    for entry in entries:
        vid = entry.get("vendor_id", 0)
        pid = entry.get("product_id", 0)
        path = entry["path"]
        if path in seen:
            continue
        family = None
        name = entry.get("product_string") or ""
        name_l = name.lower()
        mfg = (entry.get("manufacturer_string") or "").lower()
        # D-mode ShanWan advertises GamepadSpace-* on arbitrary VIDs — catch by name first.
        if any(t in name_l or t in mfg for t in (
            "gamepadspace", "shanwan", "山湾", "q34u", "q42", "q36",
        )) and vid != MICROSOFT:
            family = "shanwan"
            name = (entry.get("product_string") or "").strip() or "ShanWan Controller"
        elif vid == NINTENDO and pid in NINTENDO_PRODUCTS:
            family, name = "switch", NINTENDO_PRODUCTS[pid]
        elif vid == SONY and pid in SONY_PRODUCTS:
            family, name = "sony", SONY_PRODUCTS[pid]
        elif vid == MICROSOFT and pid in XBOX_PRODUCTS:
            family = "xbox"
            name = XBOX_PRODUCTS[pid]
        elif vid == EIGHTBITDO and pid in EIGHTBITDO_PRODUCTS:
            family = "8bitdo"
            name = EIGHTBITDO_PRODUCTS[pid]
        elif vid == GAMESIR:
            family = "gamesir"
            name = GAMESIR_PRODUCTS.get(pid, name or "GameSir Controller")
        elif (vid == FLYDIGI_V1 and pid == 0x2412) or (vid == FLYDIGI_V2 and pid in FLYDIGI_PRODUCTS):
            family = "flydigi"
            name = FLYDIGI_PRODUCTS.get(pid, name or "Flydigi Controller")
        elif vid in (SHANWAN, SHANWAN_ALT2):
            family = "shanwan"
            name = name.strip() or "ShanWan Controller"
        elif vid in (SHANWAN_ALT, BETOP):
            # Shared OEM VIDs (gcdb: Betop, Xiaomi, EasySMX, Sanwa, … on these) —
            # trust the device's own product string, not the vendor id.
            family = "oem"
            name = name.strip() or "Gamepad"
        else:
            # Diagnostics: gamepad usage that we still don't claim.
            usage_page = int(entry.get("usage_page") or 0)
            usage = int(entry.get("usage") or 0)
            if usage_page == 1 and usage in (4, 5):  # joystick / gamepad
                log("hid", f"unmatched vid={vid:04x} pid={pid:04x} "
                    f"product={name!r} mfg={entry.get('manufacturer_string')!r}")
            continue
        seen.add(path)
        product = (entry.get("product_string") or name or "").strip() or name
        serial = entry.get("serial_number") or ""
        address = _bt_address(serial)
        dev_key = f"hid:{vid:04x}:{pid:04x}:{serial or path.hex()[:12]}"
        # Pads expose several HID collections; report each physical pad once.
        group = (vid, pid, serial) if serial else (vid, pid, path)
        prior = emitted.get(group)
        if prior is not None and (prior.battery is not None or family not in _HID_READERS):
            continue
        log("hid", f"match vid={vid:04x} pid={pid:04x} family={family} "
            f"product={product!r} serial={serial!r}")

        reading: tuple[int, bool] | None = None
        if family in _HID_READERS:
            try:
                dev = hid.device()
                dev.open_path(path)
            except OSError as e:
                log("hid", f"open failed {family}: {e}")
                dev = None
            if dev is not None:
                try:
                    if family == "switch":
                        counter = (counter + 1) & 0x0F
                        reading = _read_switch_battery(dev, counter)
                    elif family == "sony":
                        reading = _read_sony_battery(dev, pid)
                    elif family == "8bitdo":
                        reading = _read_8bitdo_battery(dev, pid)
                    elif family == "flydigi":
                        reading = _read_flydigi_battery(dev, vid, pid)
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
        if prior is not None:
            if level is not None:
                prior.battery, prior.charging = level, charging
            continue
        if family == "xbox":
            # Xbox HID has no battery field. Bluetooth-only PIDs are also what
            # X-mode clones (ShanWan / GameSir / …) spoof — flag for the UI.
            if pid not in XBOX_BT_ONLY_PIDS:
                continue
            existing = [d for d in result if "xbox" in (d.name or "").lower()]
            for d in existing:
                d.extra = dict(d.extra or {})
                d.extra["xbox_bt_spoof"] = True
                if product:
                    d.extra["product"] = product
            if existing:
                continue
        hint_names = [product, name]
        if family == "shanwan":
            hint_names.append("ShanWan")
        extra = _pad_extra("HID", *hint_names, address=address)
        extra["product"] = product
        if family == "xbox":
            extra["xbox_bt_spoof"] = True
        dev_out = Device(
            address=dev_key,
            name=product or name,
            kind=DeviceKind.GAMEPAD,
            connected=True,
            battery=level,
            transport="wireless",
            charging=charging,
            extra=extra,
        )
        emitted[group] = dev_out
        result.append(dev_out)

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
