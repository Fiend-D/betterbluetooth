from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import APP_DISPLAY_NAME
from ..models import Device
from . import icons
from .tray_render import render_main_icon, render_tray_icon

if TYPE_CHECKING:
    from ..app import Controller

class TrayManager(QObject):
    def __init__(self, ctl: "Controller") -> None:
        super().__init__()
        self.ctl = ctl
        self.main = QSystemTrayIcon(self)
        self.main.setToolTip(APP_DISPLAY_NAME)
        self.main.activated.connect(self._on_activated)
        self._main_menu = QMenu()
        self.main.setContextMenu(self._main_menu)
        self._device_icons: dict[str, QSystemTrayIcon] = {}
        self._device_menus: dict[str, QMenu] = {}
        self._render_keys: dict[str, tuple] = {}
        self.refresh_main_icon()
        self.main.show()

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def refresh_main_icon(self) -> None:
        self.main.setIcon(render_main_icon(self.ctl.theme.taskbar_dark))
        self._render_keys.clear()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.ctl.toggle_flyout()

    def show_message(self, title: str, text: str, warning: bool = False) -> None:
        icon = QSystemTrayIcon.Warning if warning else QSystemTrayIcon.Information
        self.main.showMessage(title, text, icon, 6000)

    def update(self, devices: list[Device]) -> None:
        s = self.ctl.settings
        self._rebuild_main_menu(devices)
        wanted = {
            d.address: d for d in devices
            if d.connected and d.battery is not None and s.show_in_tray(d.address, d.stable_id)
        }
        for address in list(self._device_icons):
            if address not in wanted:
                tray = self._device_icons.pop(address)
                tray.hide()
                tray.deleteLater()
                self._device_menus.pop(address, None)
                self._render_keys.pop(address, None)
        for address, dev in wanted.items():
            tray = self._device_icons.get(address)
            if tray is None:
                tray = QSystemTrayIcon(self)
                tray.activated.connect(self._on_activated)
                menu = QMenu()
                tray.setContextMenu(menu)
                self._device_icons[address] = tray
                self._device_menus[address] = menu
            kind_icon = icons.KIND_ICON[dev.kind]
            charging = bool(dev.charging)
            key = (s.tray_style, dev.battery, kind_icon, self.ctl.theme.taskbar_dark,
                   s.low_battery_threshold, s.tray_colored, charging)
            if self._render_keys.get(address) != key:
                tray.setIcon(render_tray_icon(s.tray_style, dev.battery, kind_icon, self.ctl.theme.taskbar_dark,
                                              s.low_battery_threshold, s.tray_colored, charging))
                self._render_keys[address] = key
            tray.setToolTip(f"{dev.name}：{dev.battery}%" + ("（充电中）" if charging else ""))
            self._rebuild_device_menu(self._device_menus[address], dev)
            if not tray.isVisible():
                tray.show()

    def _rebuild_main_menu(self, devices: list[Device]) -> None:
        m = self._main_menu
        m.clear()
        connected = [d for d in devices if d.connected]
        if connected:
            for d in connected:
                text = f"{d.name}  {d.battery}%" if d.battery is not None else d.name
                a = m.addAction(text)
                a.setEnabled(False)
        else:
            a = m.addAction("没有已连接的设备")
            a.setEnabled(False)
        m.addSeparator()
        m.addAction("打开面板", self.ctl.show_flyout)
        m.addAction("添加设备…", lambda: self.ctl.show_flyout("scan"))
        m.addAction("设置", lambda: self.ctl.show_flyout("settings"))
        m.addSeparator()
        m.addAction("退出", self.ctl.quit)

    def _rebuild_device_menu(self, m: QMenu, dev: Device) -> None:
        m.clear()
        title = m.addAction(f"{dev.name}  {dev.battery}%")
        title.setEnabled(False)
        m.addSeparator()
        if dev.is_bluetooth and "connect" in self.ctl.capabilities:
            m.addAction("断开连接", lambda a=dev.address: self.ctl.disconnect_device(a))
        m.addAction("电量历史", lambda a=dev.address: self.ctl.show_flyout("history", a))
        m.addAction("不在任务栏显示", lambda a=dev.address: self.ctl.set_tray_visible(a, False))
        m.addSeparator()
        m.addAction("打开面板", self.ctl.show_flyout)
        m.addAction("退出", self.ctl.quit)

    def hide_all(self) -> None:
        for tray in self._device_icons.values():
            tray.hide()
        self.main.hide()
