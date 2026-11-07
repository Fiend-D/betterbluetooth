"""Nintendo Switch controller (Joy-Con / Pro Controller) battery reader over raw HID (used on Windows).

A subcommand is sent and the battery nibble is taken from the reply (report 0x21) or from a
full-mode input report (0x30); the controller's input report mode is left untouched.
"""
from __future__ import annotations

import asyncio
import re
import time

import hid  # hidapi

from ..models import Device, DeviceKind, normalize_address
from . import PeripheralSource

NINTENDO = 0x057E
PRODUCTS = {
    0x2006: "Joy-Con (L)",
    0x2007: "Joy-Con (R)",
    0x2009: "Pro Controller",
    0x200E: "Joy-Con 充电握把",
}
SUBCMD_GET_VOLTAGE = 0x50
NEUTRAL_RUMBLE = bytes([0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40])
_HEX_MAC = re.compile(r"^[0-9a-fA-F]{12}$")


def _read_battery(dev: hid.device, counter: int, timeout: float = 0.6) -> tuple[int, bool] | None:
    dev.write(bytes([0x01, counter & 0x0F]) + NEUTRAL_RUMBLE + bytes([SUBCMD_GET_VOLTAGE]) + bytes(38))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = dev.read(64, 100)
        if len(data) < 3 or data[0] not in (0x21, 0x30, 0x31):
            continue
        # SDL_hidapi_switch: level 0..8 in bits 5-7 (step 2), bit 4 = charging.
        level = (data[2] & 0xE0) >> 4
        return int(round(level / 8 * 100)), bool(data[2] & 0x10)
    return None


def _bt_address(serial: str | None) -> str | None:
    serial = (serial or "").replace(":", "").replace("-", "").strip()
    return normalize_address(serial) if _HEX_MAC.match(serial) else None


def scan_controllers(state: dict) -> list[Device]:
    result: list[Device] = []
    seen: set[bytes] = set()
    for entry in hid.enumerate(NINTENDO, 0):
        pid = entry.get("product_id", 0)
        path = entry["path"]
        if pid not in PRODUCTS or path in seen:
            continue
        seen.add(path)
        dev = hid.device()
        try:
            dev.open_path(path)
        except OSError:
            continue
        try:
            state["counter"] = (state.get("counter", 0) + 1) & 0x0F
            reading = _read_battery(dev, state["counter"])
        except OSError:
            reading = None
        finally:
            dev.close()
        if reading is None:
            continue
        level, charging = reading
        name = PRODUCTS[pid]
        serial = entry.get("serial_number") or ""
        extra: dict = {"via": "Switch 手柄", "bt_name": name}
        address = _bt_address(serial)
        if address:
            extra["bt_address"] = address
        result.append(Device(
            address=f"switch:{serial or path.hex()}",
            name=name,
            kind=DeviceKind.GAMEPAD,
            connected=True,
            battery=level,
            transport="wireless",
            charging=charging,
            extra=extra,
        ))
    return result


class SwitchControllerSource(PeripheralSource):
    name = "Nintendo Switch"

    def __init__(self) -> None:
        self._state: dict = {}

    async def devices(self) -> list[Device]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, scan_controllers, self._state)
