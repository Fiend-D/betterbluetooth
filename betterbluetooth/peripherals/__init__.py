"""Battery sources for non-Bluetooth wireless peripherals (2.4G receivers, USB-wireless gamepads)."""
from __future__ import annotations

import abc
import os
import sys
from typing import Callable

from ..models import Device, DeviceKind


class PeripheralSource(abc.ABC):
    name = "peripheral"

    async def start(self, on_change: Callable[[], None]) -> None:
        pass

    async def stop(self) -> None:
        pass

    @abc.abstractmethod
    async def devices(self) -> list[Device]:
        """Return devices with transport="wireless", or Bluetooth matches with extra["bt_address"] set."""


def create_sources(mock: bool = False) -> list[PeripheralSource]:
    if mock or os.environ.get("BB_BACKEND") == "mock":
        from .mock import MockPeripherals
        return [MockPeripherals()]
    sources: list[PeripheralSource] = []
    if sys.platform.startswith("linux"):
        from .upower import UPowerSource
        sources.append(UPowerSource())
    elif sys.platform == "win32":
        try:
            from .hidpp import HidppSource
        except ImportError:
            pass
        else:
            sources.append(HidppSource())
        # Unified Xbox / DualSense / Switch HID (+ XInput) battery reader.
        try:
            from .gamepad_hid import GamepadHidSource
        except ImportError:
            try:
                from .switch import SwitchControllerSource
            except ImportError:
                pass
            else:
                sources.append(SwitchControllerSource())
        else:
            sources.append(GamepadHidSource())
    return sources


def _name_tokens(name: str) -> set[str]:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in name).split() if len(t) >= 3}


def _names_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    al, bl = a.lower(), b.lower()
    if al == bl or al in bl or bl in al:
        return True
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) >= 1 and (ta <= tb or tb <= ta or len(ta & tb) >= 2)


def merge(bluetooth: list[Device], peripherals: list[Device]) -> list[Device]:
    """Attach peripheral readings to matching Bluetooth devices; append the rest."""
    by_addr = {d.address: d for d in bluetooth}
    connected_bt = [d for d in bluetooth if d.connected]
    by_name: dict[str, list[Device]] = {}
    for d in connected_bt:
        by_name.setdefault(d.name, []).append(d)
    result = list(bluetooth)
    seen: set[str] = set()
    for p in peripherals:
        bt = by_addr.get(p.extra.get("bt_address", ""))
        if bt is None:
            # Exact name, then alias list, then fuzzy gamepad match.
            candidates: list[str] = []
            if p.extra.get("bt_name"):
                candidates.append(p.extra["bt_name"])
            candidates.extend(p.extra.get("bt_names") or [])
            for name in candidates:
                same = by_name.get(name, [])
                if len(same) == 1:
                    bt = same[0]
                    break
            if bt is None and p.kind == DeviceKind.GAMEPAD:
                fuzzy = [d for d in connected_bt
                         if d.kind == DeviceKind.GAMEPAD
                         and any(_names_match(d.name, n) for n in candidates + [p.name])]
                if len(fuzzy) == 1:
                    bt = fuzzy[0]
                elif len(fuzzy) > 1:
                    # Prefer a connected gamepad that still lacks battery.
                    needy = [d for d in fuzzy if d.battery is None]
                    if len(needy) == 1:
                        bt = needy[0]
        if bt is not None:
            if bt.connected:
                if bt.battery is None and p.battery is not None:
                    bt.battery = p.battery
                if bt.charging is None and p.charging is not None:
                    bt.charging = p.charging
                if bt.kind == DeviceKind.OTHER:
                    bt.kind = DeviceKind.GAMEPAD
            continue
        if p.extra.get("bt_address") or p.address in seen:
            continue
        seen.add(p.address)
        result.append(p)
    return result
