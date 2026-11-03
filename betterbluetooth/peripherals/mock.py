from __future__ import annotations

from ..models import Device, DeviceKind
from . import PeripheralSource


class MockPeripherals(PeripheralSource):
    name = "mock"

    async def devices(self) -> list[Device]:
        return [
            Device("hidpp:c548:G502 X PLUS", "G502 X PLUS", DeviceKind.MOUSE, connected=True, battery=63,
                   transport="wireless", extra={"via": "Logitech 接收器"}),
            Device("upower:ps-controller", "DualSense", DeviceKind.GAMEPAD, connected=True, battery=88,
                   transport="wireless", charging=True, extra={"via": "USB 无线"}),
        ]
