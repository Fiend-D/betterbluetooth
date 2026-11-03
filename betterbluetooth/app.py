from __future__ import annotations

import argparse
import os
import signal
import sys

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import APP_DISPLAY_NAME, APP_NAME, __version__, autostart
from .config import IS_LINUX, Settings, data_dir
from .history import BatteryHistory
from .models import AdapterState, Device
from .ui import theme
from .ui.flyout import Flyout
from .ui.icons import app_icon
from .ui.tray import TrayManager
from .worker import BackendWorker

OP_DONE_TEXT = {
    "connect": "已连接",
    "disconnect": "已断开",
    "pair": "已配对",
    "remove": "已删除",
    "power": "",
    "rename": "",
}
OP_FAIL_TEXT = {
    "connect": "连接失败",
    "disconnect": "断开失败",
    "pair": "配对失败",
    "remove": "删除失败",
    "power": "切换蓝牙开关失败",
    "rename": "重命名失败",
}


class Controller(QObject):
    def __init__(self, app: QApplication, mock: bool) -> None:
        super().__init__()
        self.app = app
        self.settings = Settings.load()
        self.history = BatteryHistory(data_dir() / "history.db")
        self.history.prune(self.settings.history_days)
        self.theme = theme.ThemeManager(self.settings)
        self.devices: list[Device] = []
        self.adapter: AdapterState | None = None
        self.capabilities: frozenset[str] = frozenset()
        self.backend_name = ""
        self.pending: dict[str, str] = {}
        self._first_update = True
        self._low_notified: set[str] = set()
        self._prev_connected: dict[str, bool] = {}

        self.worker = BackendWorker(self.settings.refresh_interval, mock)
        self.tray: TrayManager | None = None
        self.flyout = Flyout(self)
        self.tray = TrayManager(self)
        self.theme.changed.connect(self._on_theme)

        w = self.worker
        w.started.connect(self._on_started)
        w.failed.connect(self._on_failed)
        w.devicesChanged.connect(self._on_devices)
        w.adapterChanged.connect(self._on_adapter)
        w.diagnosticsChanged.connect(self.flyout.devices_page.set_diagnostics)
        w.scanResults.connect(self.flyout.scan_page.on_results)
        w.scanFinished.connect(self.flyout.scan_page.on_finished)
        w.operationDone.connect(self._on_op_done)
        w.message.connect(lambda text: self._notify_user(text, "info"))
        self.flyout.settings_page.changed.connect(self._on_settings_changed)

        if self.settings.autostart != autostart.is_enabled():
            self.settings.autostart = autostart.is_enabled()
            self.flyout.settings_page.autostart.set_checked_silent(self.settings.autostart)

        self._prune_timer = QTimer(self)
        self._prune_timer.timeout.connect(lambda: self.history.prune(self.settings.history_days))
        self._prune_timer.start(6 * 3600 * 1000)
        self.flyout.show_page("devices")
        w.start()

    # ---- worker events ----

    def _on_started(self, name: str, caps) -> None:
        self.backend_name = name
        self.capabilities = frozenset(caps)
        self.flyout.show_page(self._current_page())
        self.flyout.settings_page.set_backend_info(
            f"后端：{name}　平台：{sys.platform}　配置目录：{Settings.path().parent}")

    def _current_page(self) -> str:
        f = self.flyout
        return {f.devices_page: "devices", f.scan_page: "scan", f.history_page: "history",
                f.settings_page: "settings"}.get(f.stack.currentWidget(), "devices")

    def _on_failed(self, error: str) -> None:
        self.adapter = AdapterState()
        self.flyout.devices_page.set_adapter(self.adapter)
        self.flyout.devices_page.set_diagnostics([f"蓝牙服务启动失败：{error}"])
        self.flyout.devices_page.set_devices([])

    def _on_adapter(self, adapter: AdapterState) -> None:
        self.adapter = adapter
        self.flyout.devices_page.set_adapter(adapter)

    def _on_devices(self, devices: list[Device]) -> None:
        s = self.settings
        for d in devices:
            alias = s.aliases.get(d.address)
            if alias:
                d.system_name = d.system_name or d.name
                d.name = alias
        if s.history_enabled:
            for d in devices:
                if d.connected and d.battery is not None:
                    self.history.record(d.address, d.battery)
        self._notify_changes(devices)
        self.devices = devices
        self.flyout.devices_page.set_devices(devices)
        if self.flyout.stack.currentWidget() is self.flyout.history_page:
            self.flyout.history_page.reload()
        if self.tray:
            self.tray.update(devices)

    def _notify_changes(self, devices: list[Device]) -> None:
        s = self.settings
        for d in devices:
            was = self._prev_connected.get(d.address)
            if not self._first_update and s.notify_connection and was is not None and was != d.connected:
                self._tray_message(d.name, "已连接" if d.connected else "已断开连接")
            if d.connected and d.battery is not None:
                if d.battery <= s.low_battery_threshold and not d.charging:
                    if d.address not in self._low_notified and s.notify_low_battery:
                        self._tray_message("电量低", f"{d.name} 剩余电量 {d.battery}%，请及时充电", True)
                    self._low_notified.add(d.address)
                elif d.battery > s.low_battery_threshold + 3:
                    self._low_notified.discard(d.address)
        self._prev_connected = {d.address: d.connected for d in devices}
        self._first_update = False

    def _on_op_done(self, op: str, address: str, ok: bool, error: str) -> None:
        if self.pending.get(address) == op:
            self.pending.pop(address, None)
        name = next((d.name for d in self.devices if d.address == address), address)
        if op == "pair":
            name = next((r.name.full_text() for a, r in self.flyout.scan_page._rows.items() if a == address), name)
            self.flyout.scan_page.refresh_pending()
            if ok:
                self.flyout.scan_page.remove_row(address)
        if ok:
            if OP_DONE_TEXT.get(op):
                self._notify_user(f"{OP_DONE_TEXT[op]}：{name}", "success")
            if op == "pair":
                self.flyout.show_page("devices")
        else:
            self._notify_user(f"{OP_FAIL_TEXT.get(op, '操作失败')}：{error}", "error")
        self.flyout.devices_page.set_devices(self.devices)

    def _notify_user(self, text: str, kind: str) -> None:
        if self.flyout.isVisible():
            self.flyout.toast(text, kind, 8000 if kind == "error" else 4000)
        elif kind in ("error", "info"):
            self._tray_message(APP_DISPLAY_NAME, text, kind == "error")

    def _tray_message(self, title: str, text: str, warning: bool = False) -> None:
        if self.tray:
            self.tray.show_message(title, text, warning)

    # ---- settings / theme ----

    def _on_settings_changed(self) -> None:
        s = self.settings
        if s.autostart != autostart.is_enabled():
            try:
                autostart.set_enabled(s.autostart)
            except OSError as e:
                self._notify_user(f"设置开机启动失败：{e}", "error")
        self.worker.set_interval(s.refresh_interval)
        self.theme.apply()
        s.save()
        if self.tray:
            self.tray.update(self.devices)
        self.flyout.devices_page.set_devices(self.devices)

    def _on_theme(self) -> None:
        if self.tray:
            self.tray.refresh_main_icon()
            self.tray.update(self.devices)

    # ---- actions used by the UI ----

    def show_flyout(self, page: str = "devices", arg: str | None = None) -> None:
        self.flyout.show_page(page, arg)
        self.flyout.popup()

    def reset_flyout_position(self) -> None:
        self.flyout.reset_position()
        self.flyout.toast("面板已恢复到默认位置", "success", 2500)

    def toggle_flyout(self) -> None:
        self.flyout.toggle()

    def _submit(self, op: str, address: str, fn) -> None:
        self.pending[address] = op
        self.flyout.devices_page.set_devices(self.devices)
        self.flyout.scan_page.refresh_pending()
        self.worker.submit(op, address, fn)

    def connect_device(self, address: str) -> None:
        self._submit("connect", address, lambda b: b.connect(address))

    def disconnect_device(self, address: str) -> None:
        self._submit("disconnect", address, lambda b: b.disconnect(address))

    def pair_device(self, address: str) -> None:
        self._submit("pair", address, lambda b: b.pair(address))

    def remove_device(self, address: str) -> None:
        self.settings.aliases.pop(address, None)
        self.settings.tray_devices.pop(address, None)
        self.settings.save()
        self._submit("remove", address, lambda b: b.remove(address))

    def rename_device(self, address: str, name: str) -> None:
        if name:
            self.settings.aliases[address] = name
        else:
            self.settings.aliases.pop(address, None)
        self.settings.save()
        if name and "rename" in self.capabilities:
            self.worker.submit("rename", address, lambda b: b.rename(address, name))
        else:
            self.worker.refresh()

    def set_tray_visible(self, address: str, visible: bool) -> None:
        self.settings.tray_devices[address] = visible
        self.settings.save()
        if self.tray:
            self.tray.update(self.devices)
        self.flyout.devices_page.set_devices(self.devices)

    def set_powered(self, on: bool) -> None:
        self.worker.submit("power", "", lambda b: b.set_powered(on))

    def quit(self) -> None:
        self.flyout.hide()
        if self.tray:
            self.tray.hide_all()
        self.worker.stop()
        self.settings.save()
        theme.cleanup()
        self.app.quit()


def _single_instance(server_name: str) -> QLocalServer | None:
    sock = QLocalSocket()
    sock.connectToServer(server_name)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        return None
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.listen(server_name)
    return server


def _self_test() -> int:
    """Import every platform module a packaged build needs; exit code reports the result."""
    import importlib

    modules = ["PySide6.QtSvg", "PySide6.QtNetwork", "betterbluetooth.backends.mock"]
    if sys.platform == "win32":
        modules += ["betterbluetooth.backends.windows", "betterbluetooth.backends.win_setupapi",
                    "betterbluetooth.peripherals.hidpp", "betterbluetooth.peripherals.switch"]
    else:
        modules += ["betterbluetooth.backends.bluez", "betterbluetooth.peripherals.upower"]
    failed = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name}: {e}")
    if failed:
        (data_dir() / "self-test.log").write_text("\n".join(failed), "utf-8")
        return 1
    return 0


def _redirect_output() -> None:
    """Windowed builds have no console (sys.stderr is None); keep tracebacks in a log file instead."""
    if sys.stderr is not None and sys.stdout is not None:
        return
    log_path = data_dir() / "betterbluetooth.log"
    try:
        if log_path.exists() and log_path.stat().st_size > 1_000_000:
            log_path.replace(log_path.with_suffix(".log.old"))
        stream = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    except OSError:
        stream = open(os.devnull, "w")  # noqa: SIM115
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream


def main(argv: list[str] | None = None) -> int:
    _redirect_output()
    parser = argparse.ArgumentParser(prog=APP_NAME.lower(), description=APP_DISPLAY_NAME)
    parser.add_argument("--mock", action="store_true", help="使用模拟设备数据（界面调试）")
    parser.add_argument("--minimized", action="store_true", help="启动时不弹出面板")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    if IS_LINUX and os.environ.get("WAYLAND_DISPLAY") and "QT_QPA_PLATFORM" not in os.environ \
            and os.environ.get("DISPLAY"):
        # Wayland forbids client-side window positioning; XWayland lets the flyout sit next to the tray.
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    if IS_LINUX:
        # Qt >= 6.9 tries to register an app ID with xdg-desktop-portal; it fails harmlessly when
        # launched from a terminal whose session connection already carries another app ID.
        rules = os.environ.get("QT_LOGGING_RULES", "")
        os.environ["QT_LOGGING_RULES"] = ";".join(filter(None, [rules, "qt.qpa.services.warning=false"]))

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_NAME.lower())
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    app.setFont(theme.app_font())
    app.setStyle("Fusion")

    server_name = f"{APP_NAME}-{os.environ.get('USER') or os.environ.get('USERNAME') or 'user'}"
    if args.mock:
        server_name += "-mock"
    server = _single_instance(server_name)
    if server is None:
        return 0

    ctl = Controller(app, args.mock)

    def on_connection() -> None:
        conn = server.nextPendingConnection()
        conn.readyRead.connect(lambda: (conn.readAll(), ctl.show_flyout()))

    server.newConnection.connect(on_connection)

    if not TrayManager.available():
        ctl.flyout.pinned = True
        ctl.flyout.toast("未检测到系统托盘。GNOME 需要启用 AppIndicator 扩展才能在顶栏显示电量。",
                         "warning", 0)
        ctl.show_flyout()
    elif not args.minimized:
        QTimer.singleShot(300, ctl.show_flyout)

    signal.signal(signal.SIGINT, lambda *_: ctl.quit())
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(500)
    return app.exec()
