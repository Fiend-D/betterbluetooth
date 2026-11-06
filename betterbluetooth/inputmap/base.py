"""Abstract input backend: test listening + optional system-wide remapping."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Callable

from .profile import InputProfile


@dataclass
class InputEvent:
    device_key: str
    code: str
    pressed: bool
    label: str = ""


OnEvent = Callable[[InputEvent], None]
OnStatus = Callable[[str], None]


class InputBackend(abc.ABC):
    name = "input"

    def __init__(self) -> None:
        self._on_event: OnEvent | None = None
        self._on_status: OnStatus | None = None

    def set_callbacks(self, on_event: OnEvent | None, on_status: OnStatus | None = None) -> None:
        self._on_event = on_event
        self._on_status = on_status

    def _emit(self, event: InputEvent) -> None:
        if self._on_event:
            self._on_event(event)

    def _status(self, text: str) -> None:
        if self._on_status:
            self._on_status(text)

    @abc.abstractmethod
    def capability(self) -> dict:
        """{test: bool, remap: bool, message: str} describing availability."""

    @abc.abstractmethod
    def start(self) -> None:
        ...

    @abc.abstractmethod
    def stop(self) -> None:
        ...

    @abc.abstractmethod
    def sync_devices(self, devices: list[dict]) -> None:
        """devices: [{key, name, kind, connected, address, vid?, pid?, serial?}]"""

    @abc.abstractmethod
    def set_profiles(self, profiles: list[InputProfile], master_enabled: bool) -> None:
        ...

    @abc.abstractmethod
    def set_test_target(self, device_key: str | None) -> None:
        """When set, emit InputEvents for that device (and optionally others)."""
