from __future__ import annotations

import asyncio
import concurrent.futures
import sys
import threading
import traceback
from typing import Awaitable, Callable

from PySide6.QtCore import QObject, Signal

from .backends import Backend, BackendError, create_backend
from .peripherals import PeripheralSource, create_sources, merge

DEBOUNCE = 0.4


class BackendWorker(QObject):
    """Owns the platform backend on a dedicated asyncio thread and reports through Qt signals."""

    started = Signal(str, object)              # backend name, capabilities
    failed = Signal(str)
    devicesChanged = Signal(list)
    adapterChanged = Signal(object)
    diagnosticsChanged = Signal(list)
    scanResults = Signal(list)
    scanFinished = Signal()
    operationDone = Signal(str, str, bool, str)   # op, address, ok, error
    message = Signal(str)

    def __init__(self, interval: int, mock: bool = False) -> None:
        super().__init__()
        self.interval = interval
        self._mock = mock
        self.backend: Backend | None = None
        self.sources: list[PeripheralSource] = []
        self.loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None
        self._stopping = False
        self._scan_future: concurrent.futures.Future | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="bluetooth-backend", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(5)

    def stop(self) -> None:
        if not self.loop:
            return
        self._stopping = True
        self.loop.call_soon_threadsafe(self._wake_now)
        self._thread.join(3)

    def _run(self) -> None:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.ole32.CoInitializeEx(None, 0x0)  # COINIT_MULTITHREADED
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._wake = asyncio.Event()
        self._ready.set()
        try:
            self.loop.run_until_complete(self._main())
        finally:
            self.loop.close()

    def _wake_now(self) -> None:
        if self._wake:
            self._wake.set()

    async def _main(self) -> None:
        try:
            self.backend = create_backend(self._mock)
            self.backend.set_callbacks(self._wake_now, self.message.emit)
            await self.backend.start()
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))
            return
        for source in create_sources(self._mock):
            try:
                await source.start(self._wake_now)
            except Exception as e:
                self.message.emit(f"{source.name} 不可用：{e}")
                continue
            self.sources.append(source)
        self.started.emit(self.backend.name, self.backend.capabilities)
        assert self._wake is not None
        while not self._stopping:
            await self._refresh()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(DEBOUNCE)
            self._wake.clear()
        for obj in (self.backend, *self.sources):
            try:
                await obj.stop()
            except Exception:
                pass

    async def _refresh(self) -> None:
        assert self.backend is not None
        try:
            adapter = await self.backend.adapter()
            self.adapterChanged.emit(adapter)
            devices = await self.backend.devices() if adapter.present else []
        except Exception as e:
            traceback.print_exc()
            self.message.emit(f"刷新失败：{e}")
            return
        peripherals: list = []
        for source in self.sources:
            try:
                peripherals += await source.devices()
            except Exception:
                traceback.print_exc()
        diagnostics = self.backend.diagnostics(devices)
        self.devicesChanged.emit(merge(devices, peripherals))
        self.diagnosticsChanged.emit(diagnostics)

    # ---- called from the GUI thread ----

    def refresh(self) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(self._wake_now)

    def set_interval(self, seconds: int) -> None:
        self.interval = max(5, seconds)
        self.refresh()

    def submit(self, op: str, address: str, fn: Callable[[Backend], Awaitable[None]]) -> None:
        if not self.loop or not self.backend:
            self.operationDone.emit(op, address, False, "蓝牙服务尚未就绪")
            return
        asyncio.run_coroutine_threadsafe(self._run_op(op, address, fn), self.loop)

    async def _run_op(self, op: str, address: str, fn: Callable[[Backend], Awaitable[None]]) -> None:
        assert self.backend is not None
        try:
            await fn(self.backend)
        except BackendError as e:
            self.operationDone.emit(op, address, False, str(e))
        except Exception as e:
            traceback.print_exc()
            self.operationDone.emit(op, address, False, str(e) or type(e).__name__)
        else:
            self.operationDone.emit(op, address, True, "")
        finally:
            self._wake_now()

    def start_scan(self, duration: float = 20) -> None:
        if not self.loop or not self.backend:
            self.scanFinished.emit()
            return
        self.stop_scan()

        async def run() -> None:
            assert self.backend is not None
            try:
                await self.backend.scan(self.scanResults.emit, duration)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.message.emit(f"搜索失败：{e}")
            finally:
                self.scanFinished.emit()

        self._scan_future = asyncio.run_coroutine_threadsafe(run(), self.loop)

    def stop_scan(self) -> None:
        if self._scan_future and not self._scan_future.done():
            self._scan_future.cancel()
        self._scan_future = None
