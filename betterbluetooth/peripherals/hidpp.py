"""Logitech HID++ 2.0 battery reader for Unifying / Bolt / Lightspeed receivers (used on Windows)."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import hid  # hidapi

from ..models import Device, DeviceKind
from . import PeripheralSource

LOGITECH = 0x046D
LONG_REPORT = 0x11
SWID = 0x0A
DIRECT_INDEX = 0xFF

FEATURE_ROOT = 0x0000
FEATURE_NAME = 0x0005
FEATURE_BATTERY_STATUS = 0x1000
FEATURE_BATTERY_VOLTAGE = 0x1001
FEATURE_UNIFIED_BATTERY = 0x1004

_TYPE_KIND = {
    0: DeviceKind.KEYBOARD, 2: DeviceKind.KEYBOARD, 3: DeviceKind.MOUSE, 4: DeviceKind.MOUSE,
    5: DeviceKind.MOUSE, 8: DeviceKind.HEADSET, 11: DeviceKind.GAMEPAD, 12: DeviceKind.GAMEPAD,
}

# Approximate Li-ion discharge curve (mV -> %).
_VOLTAGE_CURVE = [(4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60), (3811, 50),
                  (3778, 40), (3751, 30), (3717, 20), (3671, 10), (3646, 5), (3579, 2), (3500, 0)]


def _voltage_to_percent(mv: int) -> int:
    if mv >= _VOLTAGE_CURVE[0][0]:
        return 100
    for (v_hi, p_hi), (v_lo, p_lo) in zip(_VOLTAGE_CURVE, _VOLTAGE_CURVE[1:]):
        if mv >= v_lo:
            return round(p_lo + (p_hi - p_lo) * (mv - v_lo) / (v_hi - v_lo))
    return 0


@dataclass
class _Info:
    name: str
    kind: DeviceKind
    battery_feature: int
    battery_index: int


class _Channel:
    def __init__(self, path: bytes):
        self.dev = hid.device()
        self.dev.open_path(path)

    def close(self) -> None:
        self.dev.close()

    def request(self, idx: int, feature_index: int, function: int, params: bytes = b"",
                timeout: float = 0.5) -> bytes | None:
        code = (function << 4) | SWID
        msg = bytes([LONG_REPORT, idx, feature_index, code]) + params
        self.dev.write(msg.ljust(20, b"\0"))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.dev.read(20, 100)
            if not data or data[1] != idx:
                continue
            if data[2] in (0x8F, 0xFF) and data[3] == feature_index and data[4] == code:
                return None
            if data[2] == feature_index and data[3] == code:
                return bytes(data[4:])
        return None

    def feature_index(self, idx: int, feature: int) -> int:
        r = self.request(idx, 0, 0, bytes([feature >> 8, feature & 0xFF]))
        return r[0] if r else 0

    def ping(self, idx: int) -> bool:
        return self.request(idx, 0, 1, b"\0\0\xAA", timeout=0.3) is not None


def _read_info(ch: _Channel, idx: int) -> _Info | None:
    battery_feature = battery_index = 0
    for feature in (FEATURE_UNIFIED_BATTERY, FEATURE_BATTERY_STATUS, FEATURE_BATTERY_VOLTAGE):
        i = ch.feature_index(idx, feature)
        if i:
            battery_feature, battery_index = feature, i
            break
    if not battery_index:
        return None
    name, kind = "Logitech 设备", DeviceKind.OTHER
    ni = ch.feature_index(idx, FEATURE_NAME)
    if ni:
        r = ch.request(idx, ni, 0)
        if r:
            length, chars = r[0], b""
            while len(chars) < length:
                part = ch.request(idx, ni, 1, bytes([len(chars)]))
                if not part:
                    break
                chars += part[: length - len(chars)]
            name = chars.decode("utf-8", "ignore").strip("\0 ") or name
        t = ch.request(idx, ni, 2)
        if t:
            kind = _TYPE_KIND.get(t[0], DeviceKind.OTHER)
    return _Info(name, kind, battery_feature, battery_index)


def _read_battery(ch: _Channel, idx: int, info: _Info) -> tuple[int, bool] | None:
    if info.battery_feature == FEATURE_UNIFIED_BATTERY:
        r = ch.request(idx, info.battery_index, 1)
        return (r[0], r[2] in (1, 2)) if r else None
    if info.battery_feature == FEATURE_BATTERY_STATUS:
        r = ch.request(idx, info.battery_index, 0)
        return (r[0], r[2] in (1, 2)) if r else None
    r = ch.request(idx, info.battery_index, 0)
    if not r:
        return None
    return _voltage_to_percent((r[0] << 8) | r[1]), bool(r[2] & 0x80)


def scan_receivers(cache: dict[tuple[bytes, int], _Info]) -> list[Device]:
    result: list[Device] = []
    for entry in hid.enumerate(LOGITECH, 0):
        if entry.get("usage_page") != 0xFF00 or entry.get("usage") != 0x0002:
            continue
        try:
            ch = _Channel(entry["path"])
        except OSError:
            continue
        try:
            indices = [DIRECT_INDEX] if ch.ping(DIRECT_INDEX) else list(range(1, 7))
            for idx in indices:
                key = (entry["path"], idx)
                info = cache.get(key)
                if info is None:
                    if idx != DIRECT_INDEX and not ch.ping(idx):
                        continue
                    info = _read_info(ch, idx)
                    if info is None:
                        continue
                    cache[key] = info
                reading = _read_battery(ch, idx, info)
                if reading is None:
                    cache.pop(key, None)
                    continue
                level, charging = reading
                result.append(Device(
                    address=f"hidpp:{entry.get('product_id', 0):04x}:{info.name}",
                    name=info.name,
                    kind=info.kind,
                    connected=True,
                    battery=max(0, min(100, level)),
                    transport="wireless",
                    charging=charging,
                    extra={"via": "Logitech 接收器"},
                ))
        except OSError:
            pass
        finally:
            ch.close()
    return result


class HidppSource(PeripheralSource):
    name = "Logitech HID++"

    def __init__(self) -> None:
        self._cache: dict[tuple[bytes, int], _Info] = {}

    async def devices(self) -> list[Device]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, scan_receivers, self._cache)
