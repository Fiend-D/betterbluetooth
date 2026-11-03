from __future__ import annotations

import abc
from typing import Callable

from ..models import AdapterState, Device


class BackendError(Exception):
    pass


class Backend(abc.ABC):
    """Platform Bluetooth backend. All coroutines run on the worker's asyncio loop."""

    name = "base"
    #: subset of {"power", "connect", "pair", "remove", "rename", "scan"}
    capabilities: frozenset[str] = frozenset()

    def __init__(self) -> None:
        self._on_change: Callable[[], None] | None = None
        self._on_message: Callable[[str], None] | None = None

    def set_callbacks(self, on_change: Callable[[], None], on_message: Callable[[str], None]) -> None:
        self._on_change = on_change
        self._on_message = on_message

    def _changed(self) -> None:
        if self._on_change:
            self._on_change()

    def _message(self, text: str) -> None:
        if self._on_message:
            self._on_message(text)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    @abc.abstractmethod
    async def adapter(self) -> AdapterState: ...

    @abc.abstractmethod
    async def devices(self) -> list[Device]:
        """Return paired and/or connected devices."""

    def diagnostics(self, devices: list[Device]) -> list[str]:
        return []

    async def set_powered(self, on: bool) -> None:
        raise BackendError("当前平台不支持切换蓝牙开关")

    async def scan(self, on_found: Callable[[list[Device]], None], duration: float) -> None:
        raise BackendError("当前平台不支持搜索设备")

    async def connect(self, address: str) -> None:
        raise BackendError("当前平台不支持直接连接，请在系统蓝牙设置中操作")

    async def disconnect(self, address: str) -> None:
        raise BackendError("当前平台不支持直接断开，请在系统蓝牙设置中操作")

    async def pair(self, address: str) -> None:
        raise BackendError("当前平台不支持配对")

    async def remove(self, address: str) -> None:
        raise BackendError("当前平台不支持删除设备")

    async def rename(self, address: str, name: str) -> None:
        raise BackendError("当前平台不支持修改系统设备名")
