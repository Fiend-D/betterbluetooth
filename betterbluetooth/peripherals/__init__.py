"""Battery sources for non-Bluetooth wireless peripherals (2.4G receivers, USB-wireless gamepads)."""
from __future__ import annotations

import abc
import os
import sys
from typing import Callable

from ..models import Device


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
        try:
            from .switch import SwitchControllerSource
        except ImportError:
            pass
        else:
            sources.append(SwitchControllerSource())
    return sources


def merge(bluetooth: list[Device], peripherals: list[Device]) -> list[Device]:
    """Attach peripheral readings to matching Bluetooth devices; append the rest."""
    by_addr = {d.address: d for d in bluetooth}
    by_name: dict[str, list[Device]] = {}
    for d in bluetooth:
        if d.connected:
            by_name.setdefault(d.name, []).append(d)
    result = list(bluetooth)
    seen: set[str] = set()
    for p in peripherals:
        bt = by_addr.get(p.extra.get("bt_address", ""))
        if bt is None and p.extra.get("bt_name"):
            same = by_name.get(p.extra["bt_name"], [])
            bt = same[0] if len(same) == 1 else None
        if bt is not None:
            if bt.battery is None and bt.connected:
                bt.battery = p.battery
                bt.charging = p.charging
            continue
        if p.extra.get("bt_address") or p.address in seen:
            continue
        seen.add(p.address)
        result.append(p)
    return result
