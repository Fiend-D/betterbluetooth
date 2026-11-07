"""Windows gamepad battery: PnP / WinRT / XInput / vendor HID.

Priority (Bluetooth Xbox etc.):
1. Windows PnP DEVPKEY_Bluetooth_BatteryLevel (exact %, Settings source)
2. WinRT Gaming.Input TryGetBatteryReport (cached; rate-limits)
3. XInput coarse buckets (dongle / older firmware)
4. Vendor HID: Switch / Sony / 8BitDo / GameSir / Flydigi
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
FLYDIGI_V1 = 0x04B4
FLYDIGI_V2 = 0x37D7
BETOP = 0x20BC
SHANWAN = 0x2563
SHANWAN_ALT = 0x20BC  # ShanWan "poor mode" / Betop share

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
    0x6012: "8BitDo Ultimate 2", 0x301B: "8BitDo Ultimate 2C",
    0x202F: "8BitDo Ultimate 3",
}
GAMESIR_PRODUCTS = {
    0x100B: "GameSir Cyclone 2", 0x102A: "GameSir Cyclone 2",
    0x101D: "GameSir Cyclone 2", 0x1053: "GameSir Cyclone 2",
    0x10B8: "GameSir G7 Pro", 0x103C: "GameSir Tarantula",
    0x1022: "GameSir G7 Pro",
}
FLYDIGI_PRODUCTS = {
    0x2412: "Flydigi Gamepad",
    0x2501: "Flydigi Apex", 0x2502: "Flydigi Apex 6",
    0x2401: "Flydigi Vader",
}
SHANWAN_HINTS = (
    "ShanWan", "山湾", "Q34U2", "Q34U", "Q42", "Q36", "Q33", "Q39",
)

SUBCMD_GET_VOLTAGE = 0x50
NEUTRAL_RUMBLE = bytes([0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40])
_SWITCH_LEVEL = {8: 100, 6: 70, 4: 40, 2: 15, 0: 0}
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


def _read_8bitdo_battery(dev: hid.device, pid: int) -> tuple[int, bool] | None:
    """Passive read of enhanced report (HaloBattery/SDL). Never enable enhanced mode."""
    try:
        # Pro 3 always uses report 0x04; others 0x01 (BT) / 0x04 (USB) when already enhanced.
        for report_id in (0x01, 0x04):
            try:
                got = dev.get_input_report(report_id, 64)
            except Exception:
                continue
            if not got or len(got) < 15:
                continue
            raw = got[14]
            level = raw & 0x7F
            if level == 0 or level > 100:
                continue
            charging = bool(raw & 0x80)
            return level, charging
        # Opportunistic stream read (already in enhanced mode via Steam etc.)
        data = dev.read(64, 80)
        if data and len(data) >= 15 and data[0] in (0x01, 0x04):
            raw = data[14]
            level = raw & 0x7F
            if 1 <= level <= 100:
                return level, bool(raw & 0x80)
    except OSError:
        return None
    return None


def _read_gamesir_battery(dev: hid.device) -> tuple[int, bool] | None:
    """GameSir Cyclone 2: heartbeat 0F F2 00 → input 0x12 bytes 35/36 (BatteryDeck)."""
    try:
        pkt = bytearray(64)
        pkt[0], pkt[1], pkt[2] = 0x0F, 0xF2, 0x00
        try:
            dev.write(bytes(pkt))
        except OSError:
            try:
                dev.send_feature_report(bytes(pkt))
            except Exception:
                return None
        deadline = time.monotonic() + 0.55
        while time.monotonic() < deadline:
            data = dev.read(64, 80)
            if not data or len(data) <= 36:
                continue
            if data[0] != 0x12:
                continue
            if (data[1] | data[2] | data[3] | data[4]) == 0:
                continue
            charge, level = data[35], data[36]
            if level > 100:
                continue
            charging = charge != 0 and charge != 2
            return int(level), charging
    except OSError:
        return None
    return None


def _read_shanwan_battery(dev: hid.device) -> tuple[int, bool] | None:
    """Probe ShanWan / GamepadSpace HID reports; protocol on PC is undocumented.

    Logs a short hex dump so we can reverse a real battery byte later. Does not
    guess percentages (avoids another fake reading).
    """
    try:
        from ..debuglog import log
        for report_id in (0x05, 0x06, 0x04, 0x01, 0xA1, 0xF1):
            got = None
            try:
                got = dev.get_feature_report(report_id, 64)
            except Exception:
                try:
                    got = dev.get_input_report(report_id, 64)
                except Exception:
                    got = None
            if got and len(got) > 1:
                log("hid", f"shanwan report id=0x{report_id:02x} n={len(got)} "
                    f"hex={bytes(got[:16]).hex()}")
        data = dev.read(64, 40)
        if data:
            log("hid", f"shanwan input n={len(data)} hex={bytes(data[:16]).hex()}")
    except OSError as e:
        try:
            from ..debuglog import log
            log("hid", f"shanwan probe failed: {e}")
        except Exception:
            pass
    return None


def _read_flydigi_battery(dev: hid.device, vid: int) -> tuple[int, bool] | None:
    """Flydigi V2 status cmd 0x10 → byte 11 (SDL_hidapi_flydigi)."""
    try:
        if vid == FLYDIGI_V2:
            pkt = bytearray(32)
            pkt[0], pkt[1], pkt[2], pkt[3] = 0x03, 0x5A, 0xA5, 0x10
            try:
                dev.write(bytes(pkt))
            except OSError:
                try:
                    dev.send_feature_report(bytes(pkt))
                except Exception:
                    return None
        deadline = time.monotonic() + 0.45
        while time.monotonic() < deadline:
            data = dev.read(64, 80)
            if not data or len(data) < 12:
                continue
            raw = data[11]
            status = (raw >> 4) & 0x0F
            level_n = raw & 0x0F
            if status == 0:
                return min(100, level_n * 20), False
            if status == 1:
                return min(100, level_n * 20), True
            if status == 2:
                return 100, True
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


def _winrt_batteries() -> list[Device]:
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
        pads = list(Gamepad.gamepads)
    except Exception:
        pads = []
    for i, pad in enumerate(pads):
        try:
            report = pad.try_get_battery_report()
        except Exception:
            report = None
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
            name = getattr(pad, "display_name", None) or "Wireless Controller"
            if callable(name):
                name = name()
            name = str(name or "Wireless Controller")
        except Exception:
            continue
        if any(d.battery is not None for d in out) and "xbox" in name.lower():
            continue
        dev = _from_report(report, name, f"winrt-raw:{i}", "WinRT Raw")
        if dev:
            out.append(dev)
    return out


def _pnp_as_devices() -> list[Device]:
    """Expose SetupAPI battery readings as mergeable peripheral devices."""
    if sys.platform != "win32":
        return []
    try:
        from ..backends.win_setupapi import read_batteries_detailed
        by_addr, by_name = read_batteries_detailed()
    except Exception:
        return []
    out: list[Device] = []
    for addr, level in by_addr.items():
        out.append(Device(
            address=f"pnp:{addr}",
            name="Xbox Wireless Controller",
            kind=DeviceKind.GAMEPAD,
            connected=True,
            battery=level,
            transport="wireless",
            extra=_pad_extra("PnP", "Xbox Wireless Controller", "Wireless Controller",
                             "Controller", address=addr),
        ))
    for name, level in by_name.items():
        if any(d.extra.get("bt_address") for d in out):
            # Prefer address-keyed; still add distinctive names for fuzzy merge.
            pass
        out.append(Device(
            address=f"pnp-name:{name[:24]}",
            name=name.title() if name.islower() else name,
            kind=DeviceKind.GAMEPAD,
            connected=True,
            battery=level,
            transport="wireless",
            extra=_pad_extra("PnP", name, "Xbox Wireless Controller", "Wireless Controller"),
        ))
    return out


def _hid_xbox_bt_present() -> bool:
    """True when a Microsoft pad with a Bluetooth-only product id is attached."""
    try:
        for entry in hid.enumerate(MICROSOFT, 0):
            if int(entry.get("product_id") or 0) in XBOX_BT_ONLY_PIDS:
                return True
    except Exception:
        return False
    return False


def scan_gamepads(state: dict) -> list[Device]:
    from ..debuglog import log

    result: list[Device] = []
    seen: set[bytes] = set()
    counter = int(state.get("counter", 0))

    # 0) PnP — same source as Windows Settings (exact %). WinRT mWh ratios
    # often bucket to ~10% and must not win after a full charge.
    pnp = _pnp_as_devices()
    log("battery", f"pnp={len(pnp)} " + ", ".join(f"{d.name}:{d.battery}%" for d in pnp[:6]))
    result.extend(pnp)
    pnp_hit = any(d.battery is not None for d in pnp)
    xbox_bt = _hid_xbox_bt_present()

    # 1) WinRT — never for Xbox BT-only PIDs (fake 100/1000 → 10%).
    winrt: list[Device] = []
    if not pnp_hit and not xbox_bt:
        winrt = _winrt_batteries()
    log("battery", f"winrt={len(winrt)} skipped_for_pnp={pnp_hit} xbox_bt={xbox_bt} "
        + ", ".join(f"{d.name}:{d.battery}%" for d in winrt))
    for w in winrt:
        w.extra["battery_via"] = w.extra.get("via") or "WinRT Gamepad"
        w.extra["battery_coarse"] = True
        result.append(w)

    # 2) XInput coarse buckets — prefer over missing/fake WinRT for Xbox BT.
    xinput: list[Device] = []
    if not pnp_hit and (not winrt or xbox_bt):
        xinput = _xinput_batteries()
    log("battery", f"xinput={len(xinput)} " + ", ".join(f"{d.name}:{d.battery}%" for d in xinput))
    for xi in xinput:
        xi.extra["battery_via"] = "XInput"
        xi.extra["battery_coarse"] = True
        result.append(xi)

    # 3) Vendor HID
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
        elif vid == MICROSOFT and (pid in XBOX_PRODUCTS or (pid & 0xFF00) in (0x0200, 0x0B00)):
            family = "xbox"
            name = XBOX_PRODUCTS.get(pid, name or "Xbox Wireless Controller")
        elif vid == EIGHTBITDO and (pid in EIGHTBITDO_PRODUCTS or True):
            family = "8bitdo"
            name = EIGHTBITDO_PRODUCTS.get(pid, name or "8BitDo Controller")
        elif vid == GAMESIR:
            family = "gamesir"
            name = GAMESIR_PRODUCTS.get(pid, name or "GameSir Controller")
        elif vid in (FLYDIGI_V1, FLYDIGI_V2):
            family = "flydigi"
            name = FLYDIGI_PRODUCTS.get(pid, name or "Flydigi Controller")
        elif vid == SHANWAN or (vid == SHANWAN_ALT and "betop" not in name_l):
            family = "shanwan"
            raw = (entry.get("product_string") or name or "").strip()
            # Prefer OEM strings that still carry Q34U / Q42 even in X-mode clones.
            name = raw if raw else "ShanWan Controller"
            if not any(h.lower() in name.lower() for h in ("q34", "q42", "q36", "shan", "山")):
                name = f"ShanWan {name}".strip()
        elif vid == BETOP:
            family = "betop"
            name = name or "BETOP Controller"
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
        log("hid", f"match vid={vid:04x} pid={pid:04x} family={family} "
            f"product={product!r} serial={serial!r}")

        reading: tuple[int, bool] | None = None
        try:
            dev = hid.device()
            dev.open_path(path)
        except OSError as e:
            log("hid", f"open failed {family}: {e}")
            if family not in ("xbox",) or not any("xbox" in (d.name or "").lower() for d in result):
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
            elif family == "8bitdo":
                reading = _read_8bitdo_battery(dev, pid)
            elif family == "gamesir":
                reading = _read_gamesir_battery(dev)
            elif family == "flydigi":
                reading = _read_flydigi_battery(dev, vid)
            elif family == "shanwan":
                reading = _read_shanwan_battery(dev)
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
            for d in result:
                if "xbox" in (d.name or "").lower() and d.battery is None and level is not None:
                    d.battery = level
                    d.charging = charging
            # Still emit a stub so merge can flag X-mode spoof clones (山湾/小鸡/…).
            if pid in XBOX_BT_ONLY_PIDS and not any(
                "xbox" in (d.name or "").lower() for d in result
            ):
                extra = _pad_extra("HID", product, name, address=address)
                extra["product"] = product
                extra["xbox_bt_spoof"] = True
                result.append(Device(
                    address=f"hid:{vid:04x}:{pid:04x}:{serial or path.hex()[:12]}",
                    name=product or "Xbox Wireless Controller",
                    kind=DeviceKind.GAMEPAD,
                    connected=True,
                    battery=None,
                    transport="wireless",
                    extra=extra,
                ))
            elif pid in XBOX_BT_ONLY_PIDS:
                for d in result:
                    if "xbox" in (d.name or "").lower():
                        d.extra = dict(d.extra or {})
                        d.extra["xbox_bt_spoof"] = True
                        if product:
                            d.extra["product"] = product
            continue
        hint_names = [product, name]
        if family == "shanwan":
            hint_names.extend(SHANWAN_HINTS)
            # Q34U2 often spoofs Xbox — keep both so the diagram picks 小肩键+背键.
            if any(t in product.lower() for t in ("q34u2", "q34u 2", "二代")) or "q34u2" in name.lower():
                hint_names.append("Q34U2")
            elif "q34u" in product.lower() or "q34u" in name.lower():
                hint_names.append("Q34U")
        extra = _pad_extra("HID", *hint_names, address=address)
        extra["product"] = product
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
    log("battery", "scan_done=" + ", ".join(f"{d.name}:{d.battery}" for d in result)[:500])
    return result


class GamepadHidSource(PeripheralSource):
    name = "Gamepad HID"

    def __init__(self) -> None:
        self._state: dict = {}

    async def devices(self) -> list[Device]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, scan_gamepads, self._state)
