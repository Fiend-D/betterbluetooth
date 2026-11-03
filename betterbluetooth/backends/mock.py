from __future__ import annotations

import asyncio
import random
from typing import Callable

from ..models import AdapterState, Device, DeviceKind
from .base import Backend, BackendError


class MockBackend(Backend):
    """In-memory backend used for UI development (`--mock`)."""

    name = "mock"
    capabilities = frozenset({"power", "connect", "pair", "remove", "rename", "scan"})

    def __init__(self) -> None:
        super().__init__()
        self._powered = True
        self._devices = {
            d.address: d for d in [
                Device("AC:80:0A:11:22:33", "WH-1000XM5", DeviceKind.HEADPHONES, True, True, 72),
                Device("D4:3B:04:44:55:66", "MX Master 3S", DeviceKind.MOUSE, True, True, 18),
                Device("98:B6:E9:77:88:99", "Xbox Wireless Controller", DeviceKind.GAMEPAD, True, True, 45),
                Device("F0:5C:77:AA:BB:CC", "Keychron K3", DeviceKind.KEYBOARD, True, False, None),
                Device("40:4E:36:DD:EE:FF", "Pixel 8", DeviceKind.PHONE, True, False, None),
            ]
        }
        self._nearby = [
            Device("12:34:56:78:9A:BC", "JBL Flip 6", DeviceKind.SPEAKER, rssi=-58),
            Device("22:34:56:78:9A:BD", "AirPods Pro", DeviceKind.HEADSET, rssi=-47),
            Device("32:34:56:78:9A:BE", "HUAWEI WATCH GT 4", DeviceKind.WATCH, rssi=-76),
            Device("42:34:56:78:9A:BF", "Surface Pen", DeviceKind.PEN, rssi=-83),
        ]

    async def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._drain())

    async def stop(self) -> None:
        self._task.cancel()

    async def _drain(self) -> None:
        while True:
            await asyncio.sleep(20)
            for d in self._devices.values():
                if d.connected and d.battery and random.random() < 0.5:
                    d.battery = max(1, d.battery - 1)
            self._changed()

    async def adapter(self) -> AdapterState:
        return AdapterState(True, self._powered, "Mock Adapter")

    async def devices(self) -> list[Device]:
        if not self._powered:
            return [Device(d.address, d.name, d.kind, d.paired, False, None) for d in self._devices.values()]
        return [Device(**{**d.__dict__, "extra": {}}) for d in self._devices.values()]

    def diagnostics(self, devices: list[Device]) -> list[str]:
        return ["模拟模式：设备数据为演示用途。"]

    async def set_powered(self, on: bool) -> None:
        await asyncio.sleep(0.4)
        self._powered = on

    async def scan(self, on_found: Callable[[list[Device]], None], duration: float) -> None:
        found: list[Device] = []
        for d in self._nearby:
            if d.address in self._devices:
                continue
            await asyncio.sleep(1.2)
            found.append(d)
            on_found(list(found))
        await asyncio.sleep(max(0.0, duration - 1.2 * len(found)))

    def _get(self, address: str) -> Device:
        if address not in self._devices:
            raise BackendError("设备不存在")
        return self._devices[address]

    async def connect(self, address: str) -> None:
        await asyncio.sleep(1.5)
        d = self._get(address)
        d.connected = True
        d.battery = random.randint(30, 100)

    async def disconnect(self, address: str) -> None:
        await asyncio.sleep(0.6)
        d = self._get(address)
        d.connected = False
        d.battery = None

    async def pair(self, address: str) -> None:
        await asyncio.sleep(2.5)
        src = next((d for d in self._nearby if d.address == address), None)
        if src is None:
            raise BackendError("设备不存在")
        self._devices[address] = Device(src.address, src.name, src.kind, True, True, random.randint(40, 100))

    async def remove(self, address: str) -> None:
        await asyncio.sleep(0.5)
        self._devices.pop(address, None)

    async def rename(self, address: str, name: str) -> None:
        self._get(address).name = name
