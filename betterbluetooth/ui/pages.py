from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QScrollArea, QSizePolicy, QSpinBox,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import APP_DISPLAY_NAME, __version__
from ..history import estimate_remaining_hours
from ..inputmap import supports_input
from ..models import AdapterState, Device
from . import icons
from .chart import BatteryChart
from .tray_render import TRAY_STYLES, render_pixmap
from .widgets import (
    BatteryBar, DeviceAvatar, ElidedLabel, IconButton, InfoBar, ProgressRing, Segmented, ToggleSwitch, button,
    label, make_menu, repolish,
)

if TYPE_CHECKING:
    from ..app import Controller

OP_TEXT = {
    "connect": "正在连接…",
    "disconnect": "正在断开…",
    "pair": "正在配对…",
    "remove": "正在删除…",
}


def _scroll(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(content)
    return area


def _page_header(title: str, on_back: Callable[[], None]) -> tuple[QHBoxLayout, QWidget]:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    back = IconButton("back", "返回", 16)
    back.clicked.connect(on_back)
    row.addWidget(back)
    title_lbl = label(title, "pageTitle")
    row.addWidget(title_lbl, 1)
    return row, title_lbl


def _fmt_age(ts: int) -> str:
    delta = int(time.time()) - ts
    if delta < 3600:
        return f"{max(1, delta // 60)} 分钟前"
    if delta < 86400:
        return f"{delta // 3600} 小时前"
    return f"{delta // 86400} 天前"


class _EscFilter(QObject):
    def __init__(self, on_escape: Callable[[], None]):
        super().__init__()
        self._on_escape = on_escape

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self._on_escape()
            return True
        return False


class DeviceCard(QFrame):
    def __init__(self, ctl: "Controller", address: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctl = ctl
        self.address = address
        self.device: Device | None = None
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_Hover)

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 10, 8, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(3)

        self.avatar = DeviceAvatar()
        grid.addWidget(self.avatar, 0, 0, 3, 1, Qt.AlignVCenter)

        self.name = ElidedLabel("", "name")
        self.name_edit = QLineEdit()
        self.name_edit.hide()
        self.name_edit.returnPressed.connect(self._commit_rename)
        self._esc = _EscFilter(self._cancel_rename)
        self.name_edit.installEventFilter(self._esc)
        name_box = QHBoxLayout()
        name_box.setContentsMargins(0, 0, 0, 0)
        name_box.addWidget(self.name)
        name_box.addWidget(self.name_edit)
        grid.addLayout(name_box, 0, 1)

        self.status = ElidedLabel("", "secondary")
        grid.addWidget(self.status, 1, 1)
        self.bar = BatteryBar()
        grid.addWidget(self.bar, 2, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(2)
        self.tray_btn = IconButton("tray-off", "在任务栏显示电量", 16)
        self.tray_btn.setCheckable(True)
        self.tray_btn.set_checked_icon("tray")
        self.tray_btn.clicked.connect(self._toggle_tray)
        actions.addWidget(self.tray_btn)
        self.busy = ProgressRing(18)
        self.busy.hide()
        actions.addWidget(self.busy)
        self.action_btn = button("连接", flat=True)
        self.action_btn.clicked.connect(self._primary)
        actions.addWidget(self.action_btn)
        self.more_btn = IconButton("more", "更多", 16)
        self.more_btn.clicked.connect(self._show_menu)
        actions.addWidget(self.more_btn)
        grid.addLayout(actions, 0, 2, 3, 1, Qt.AlignVCenter)
        grid.setColumnStretch(1, 1)

    def event(self, e):
        if e.type() in (QEvent.HoverEnter, QEvent.HoverLeave):
            self.setProperty("hover", e.type() == QEvent.HoverEnter)
            repolish(self)
        return super().event(e)

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        if self.device:
            self.ctl.show_flyout("history", self.address)

    def update_device(self, dev: Device, pending: str | None) -> None:
        self.device = dev
        s = self.ctl.settings
        if not self.name_edit.isVisible():
            self.name.set_text(dev.name)
        self.setToolTip(f"{dev.name}\n{dev.address}")
        self.avatar.set_state(icons.KIND_ICON[dev.kind], dev.connected)
        self.setProperty("dim", not dev.connected)

        if pending:
            text = OP_TEXT.get(pending, "处理中…")
        elif not dev.is_bluetooth:
            text = dev.extra.get("via", "无线外设")
            if dev.battery is not None:
                text += f" · 电量 {dev.battery}%"
            if dev.charging:
                text += " · 充电中"
            elif dev.battery is not None and dev.battery <= s.low_battery_threshold:
                text += " · 电量低"
        elif dev.connected:
            if dev.battery is not None:
                text = f"已连接 · 电量 {dev.battery}%"
            elif dev.kind.value == "gamepad":
                text = "已连接 · 电量不可读"
            else:
                text = "已连接"
            if dev.charging:
                text += " · 充电中"
            elif dev.battery is not None and dev.battery <= s.low_battery_threshold:
                text += " · 电量低"
        else:
            text = "未连接"
            last = self.ctl.history.last_level(dev.address) if s.history_enabled else None
            if last:
                text += f" · {_fmt_age(last[0])} {last[1]}%"
        self.status.set_text(text)

        has_battery = dev.connected and dev.battery is not None
        self.bar.setVisible(has_battery)
        self.bar.set_level(dev.battery, s.low_battery_threshold)

        self.tray_btn.setVisible(has_battery)
        shown = s.show_in_tray(dev.address, getattr(dev, "stable_id", "") or "")
        self.tray_btn.setChecked(shown)
        self.tray_btn.setToolTip("已在任务栏显示电量（点击隐藏）" if shown else "在任务栏显示电量")

        can_connect = dev.is_bluetooth and "connect" in self.ctl.capabilities
        self.busy.setVisible(bool(pending))
        self.action_btn.setVisible(can_connect and not pending)
        self.action_btn.setText("断开" if dev.connected else "连接")
        repolish(self)

    def retheme(self) -> None:
        if self.device:
            self.update_device(self.device, self.ctl.pending.get(self.address))

    def _primary(self) -> None:
        if not self.device:
            return
        if self.device.connected:
            self.ctl.disconnect_device(self.address)
        else:
            self.ctl.connect_device(self.address)

    def _toggle_tray(self) -> None:
        self.ctl.set_tray_visible(self.address, self.tray_btn.isChecked())

    def _show_menu(self) -> None:
        dev = self.device
        if not dev:
            return
        menu = make_menu(self)
        if dev.is_bluetooth and "connect" in self.ctl.capabilities and not self.ctl.pending.get(self.address):
            menu.addAction("断开连接" if dev.connected else "连接", self._primary)
        menu.addAction("重命名", self.start_rename)
        addr = self.address
        menu.addAction("电量历史", lambda checked=False, a=addr: self.ctl.show_flyout("history", a))
        if supports_input(dev):
            menu.addAction("按键测试 / 映射", lambda checked=False, a=addr: self.ctl.show_flyout("input", a))
        tray = menu.addAction("在任务栏显示电量")
        tray.setCheckable(True)
        sid = self.device.stable_id if self.device else ""
        tray.setChecked(self.ctl.settings.show_in_tray(self.address, sid))
        tray.toggled.connect(lambda on: self.ctl.set_tray_visible(self.address, on))
        if dev.is_bluetooth and "remove" in self.ctl.capabilities:
            menu.addSeparator()
            menu.addAction("删除设备", self._confirm_remove)
        menu.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def _confirm_remove(self) -> None:
        if self.device:
            self.ctl.flyout.confirm(f"删除“{self.device.name}”？删除后需要重新配对才能使用。",
                                    "删除", lambda: self.ctl.remove_device(self.address))

    def start_rename(self) -> None:
        if not self.device:
            return
        self.name.hide()
        self.name_edit.setText(self.device.name)
        self.name_edit.show()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _commit_rename(self) -> None:
        text = self.name_edit.text().strip()
        self._cancel_rename()
        if self.device and text != self.device.name:
            self.ctl.rename_device(self.address, text)
            self.name.set_text(text or self.device.system_name or self.device.name)

    def _cancel_rename(self) -> None:
        self.name_edit.hide()
        self.name.show()


class DevicesPage(QWidget):
    def __init__(self, ctl: "Controller", parent: QWidget | None = None):
        super().__init__(parent)
        self.ctl = ctl
        self._cards: dict[str, DeviceCard] = {}
        self._diag_bars: dict[str, InfoBar] = {}
        self._dismissed: set[str] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 8)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.logo = QWidget()
        self.logo.setFixedSize(32, 32)
        self.logo_avatar = DeviceAvatar("bluetooth", 32, self.logo)
        header.addWidget(self.logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("蓝牙", "title"))
        self.adapter_lbl = label("正在启动…", "secondary")
        titles.addWidget(self.adapter_lbl)
        header.addLayout(titles, 1)
        self.pin_btn = IconButton("pin", "固定面板（失去焦点时不自动隐藏）", 16)
        self.pin_btn.setCheckable(True)
        self.pin_btn.set_checked_icon("pin-on")
        self.pin_btn.toggled.connect(self._pin)
        header.addWidget(self.pin_btn)
        self.power = ToggleSwitch()
        self.power.setToolTip("蓝牙开关")
        self.power.toggled.connect(self.ctl.set_powered)
        header.addWidget(self.power)
        root.addLayout(header)

        self.diag_box = QVBoxLayout()
        self.diag_box.setSpacing(6)
        root.addLayout(self.diag_box)

        self.list_widget = QWidget()
        self.list = QVBoxLayout(self.list_widget)
        self.list.setContentsMargins(0, 0, 4, 0)
        self.list.setSpacing(6)
        self.connected_lbl = label("已连接", "section")
        self.paired_lbl = label("已配对", "section")
        self.wireless_lbl = label("无线外设（2.4G / USB）", "section")
        self.empty = QWidget()
        empty_lay = QVBoxLayout(self.empty)
        empty_lay.setContentsMargins(0, 40, 0, 0)
        self.empty_lbl = label("", "empty")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setWordWrap(True)
        empty_lay.addWidget(self.empty_lbl)
        self.empty_btn = button("", accent=True)
        self.empty_btn.clicked.connect(self._empty_action)
        empty_lay.addWidget(self.empty_btn, 0, Qt.AlignHCenter)
        root.addWidget(_scroll(self.list_widget), 1)

    def _pin(self, on: bool) -> None:
        self.ctl.flyout.pinned = on
        self.pin_btn.setToolTip("已固定：点击取消固定" if on else "固定面板（失去焦点时不自动隐藏）")
        self.ctl.flyout.toast("面板已固定，点击其他窗口不会自动隐藏" if on else "已取消固定", "info", 2500)

    def _empty_action(self) -> None:
        adapter = self.ctl.adapter
        if adapter and adapter.present and not adapter.powered:
            self.ctl.set_powered(True)
        else:
            self.ctl.show_flyout("scan")

    def set_adapter(self, adapter: AdapterState) -> None:
        if not adapter.present:
            self.adapter_lbl.setText("未找到蓝牙适配器")
        else:
            state = "已开启" if adapter.powered else "已关闭"
            self.adapter_lbl.setText(f"{adapter.name} · {state}" if adapter.name else state)
        self.power.setEnabled(adapter.present and "power" in self.ctl.capabilities)
        self.power.set_checked_silent(adapter.powered)
        self.logo_avatar.set_state("bluetooth", adapter.powered)

    def set_diagnostics(self, hints: list[str]) -> None:
        for text in list(self._diag_bars):
            if text not in hints:
                bar = self._diag_bars.pop(text)
                bar.deleteLater()
        for text in hints:
            if text in self._diag_bars or text in self._dismissed:
                continue
            bar = InfoBar(text, "info")
            bar.closed.connect(lambda t=text: (self._dismissed.add(t), self._diag_bars.pop(t, None)))
            self._diag_bars[text] = bar
            self.diag_box.addWidget(bar)

    def set_devices(self, devices: list[Device]) -> None:
        while self.list.count():
            item = self.list.takeAt(0)
            if item.widget():
                item.widget().setParent(self.list_widget)
                item.widget().hide()

        alive = {d.address for d in devices}
        for address in list(self._cards):
            if address not in alive:
                self._cards.pop(address).deleteLater()

        def key(d: Device) -> str:
            return (d.name or "").lower()

        bluetooth = [d for d in devices if d.is_bluetooth]
        connected = sorted((d for d in bluetooth if d.connected), key=key)
        paired = sorted((d for d in bluetooth if not d.connected), key=key)
        wireless = sorted((d for d in devices if not d.is_bluetooth), key=key)

        adapter = self.ctl.adapter
        empty: tuple[str, str | None] | None = None
        if adapter is None:
            empty = ("正在读取蓝牙设备…", None)
        elif not adapter.present:
            empty = ("未检测到蓝牙适配器", None)
        elif not adapter.powered:
            empty = ("蓝牙已关闭", "打开蓝牙" if "power" in self.ctl.capabilities else None)
        elif not bluetooth:
            empty = ("还没有配对的蓝牙设备", "添加设备" if "scan" in self.ctl.capabilities else None)
        if empty:
            self.empty_lbl.setText(empty[0])
            self.empty_btn.setText(empty[1] or "")
            self.empty_btn.setVisible(bool(empty[1]))
            self.empty.layout().setContentsMargins(0, 40 if not devices else 8, 0, 8)
            self.list.addWidget(self.empty)
            self.empty.show()

        groups = ((self.connected_lbl, connected), (self.wireless_lbl, wireless), (self.paired_lbl, paired))
        for title, group in groups:
            if not group:
                continue
            self.list.addWidget(title)
            title.show()
            for dev in group:
                card = self._cards.get(dev.address)
                if card is None:
                    card = DeviceCard(self.ctl, dev.address, self.list_widget)
                    self._cards[dev.address] = card
                card.update_device(dev, self.ctl.pending.get(dev.address))
                self.list.addWidget(card)
                card.show()
        self.list.addStretch(1)
        flyout = getattr(self.ctl, "flyout", None)
        if flyout is not None:
            flyout.schedule_repaint()

    def card(self, address: str) -> DeviceCard | None:
        return self._cards.get(address)


class ScanRow(QFrame):
    def __init__(self, ctl: "Controller", dev: Device, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctl = ctl
        self.address = dev.address
        self.setObjectName("Card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(12)
        self.avatar = DeviceAvatar(icons.KIND_ICON[dev.kind], 32)
        lay.addWidget(self.avatar)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.name = ElidedLabel(dev.name, "name")
        self.detail = ElidedLabel("", "secondary")
        col.addWidget(self.name)
        col.addWidget(self.detail)
        lay.addLayout(col, 1)
        self.busy = ProgressRing(18)
        self.busy.hide()
        lay.addWidget(self.busy)
        self.pair_btn = button("配对")
        self.pair_btn.clicked.connect(lambda: self.ctl.pair_device(self.address))
        lay.addWidget(self.pair_btn)
        self.update_device(dev)

    def update_device(self, dev: Device) -> None:
        self.name.set_text(dev.name)
        self.avatar.set_state(icons.KIND_ICON[dev.kind], True)
        signal = ""
        if dev.rssi is not None:
            strength = "强" if dev.rssi > -60 else "中" if dev.rssi > -75 else "弱"
            signal = f" · 信号{strength}"
        self.detail.set_text(dev.address + signal)
        pairing = self.ctl.pending.get(self.address) == "pair"
        self.busy.setVisible(pairing)
        self.pair_btn.setVisible(not pairing)


class ScanPage(QWidget):
    def __init__(self, ctl: "Controller", parent: QWidget | None = None):
        super().__init__(parent)
        self.ctl = ctl
        self._rows: dict[str, ScanRow] = {}
        self._scanning = False
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        header, _ = _page_header("添加设备", lambda: self.ctl.show_flyout("devices"))
        self.ring = ProgressRing(16)
        header.addWidget(self.ring)
        self.scan_btn = button("重新搜索", flat=True)
        self.scan_btn.clicked.connect(self.toggle_scan)
        header.addWidget(self.scan_btn)
        root.addLayout(header)
        tip = label("请确保设备已开机并进入配对模式（通常长按电源键或配对键）。", "secondary", wrap=True)
        root.addWidget(tip)

        self.list_widget = QWidget()
        self.list = QVBoxLayout(self.list_widget)
        self.list.setContentsMargins(0, 0, 4, 0)
        self.list.setSpacing(6)
        self.empty = label("正在搜索附近的设备…", "empty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.list.addWidget(self.empty)
        self.list.addStretch(1)
        root.addWidget(_scroll(self.list_widget), 1)

    def toggle_scan(self) -> None:
        if self._scanning:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        self._scanning = True
        self.ring.show()
        self.scan_btn.setText("停止")
        self.empty.setText("正在搜索附近的设备…")
        self.ctl.worker.start_scan(25)

    def stop(self) -> None:
        if self._scanning:
            self.ctl.worker.stop_scan()

    def on_finished(self) -> None:
        self._scanning = False
        self.ring.hide()
        self.scan_btn.setText("重新搜索")
        if not self._rows:
            self.empty.setText("没有发现设备")

    def on_results(self, devices: list[Device]) -> None:
        paired = {d.address for d in self.ctl.devices if d.paired}
        devices = [d for d in devices if d.address not in paired]
        alive = {d.address for d in devices}
        for address in list(self._rows):
            if address not in alive and self.ctl.pending.get(address) != "pair":
                self._rows.pop(address).deleteLater()
        for i, dev in enumerate(devices):
            row = self._rows.get(dev.address)
            if row is None:
                row = ScanRow(self.ctl, dev, self.list_widget)
                self._rows[dev.address] = row
            else:
                row.update_device(dev)
            self.list.insertWidget(i, row)
        self.empty.setVisible(not self._rows)

    def refresh_pending(self) -> None:
        for row in self._rows.values():
            pairing = self.ctl.pending.get(row.address) == "pair"
            row.busy.setVisible(pairing)
            row.pair_btn.setVisible(not pairing)

    def remove_row(self, address: str) -> None:
        row = self._rows.pop(address, None)
        if row:
            row.deleteLater()
        self.empty.setVisible(not self._rows)


class HistoryPage(QWidget):
    RANGES = [(24 * 3600, "24 小时"), (7 * 86400, "7 天"), (30 * 86400, "30 天")]

    def __init__(self, ctl: "Controller", parent: QWidget | None = None):
        super().__init__(parent)
        self.ctl = ctl
        self.address: str | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)
        header, _ = _page_header("电量历史", lambda: self.ctl.show_flyout("devices"))
        root.addLayout(header)

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._combo_changed)
        root.addWidget(self.combo)

        self.range = Segmented([t for _, t in self.RANGES])
        self.range.changed.connect(lambda _: self.reload())
        root.addWidget(self.range, 0, Qt.AlignLeft)

        card = QFrame()
        card.setObjectName("Card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(8, 12, 12, 8)
        self.chart = BatteryChart()
        card_lay.addWidget(self.chart)
        root.addWidget(card)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.stat_now = self._stat(stats, "当前")
        self.stat_min = self._stat(stats, "最低")
        self.stat_eta = self._stat(stats, "预计续航")
        root.addLayout(stats)
        root.addStretch(1)

        clear = button("清除此设备记录", flat=True, danger=True)
        clear.clicked.connect(self._clear)
        root.addWidget(clear, 0, Qt.AlignRight)

    def _stat(self, row: QHBoxLayout, title: str):
        box = QFrame()
        box.setObjectName("Card")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(0)
        lay.addWidget(label(title, "secondary"))
        value = label("—", "pageTitle")
        lay.addWidget(value)
        row.addWidget(box, 1)
        return value

    def set_device(self, address: str | None) -> None:
        devices = sorted(self.ctl.devices, key=lambda d: (not d.connected, (d.name or "").lower()))
        self.combo.blockSignals(True)
        self.combo.clear()
        for d in devices:
            self.combo.addItem(d.name, d.stable_id or d.address)
        want = None
        if address:
            want = next((d.stable_id or d.address for d in devices
                         if d.address == address or d.stable_id == address), address)
        idx = self.combo.findData(want) if want else 0
        self.combo.setCurrentIndex(max(0, idx))
        self.combo.blockSignals(False)
        self.address = self.combo.currentData()
        self.reload()

    def _combo_changed(self, _i: int) -> None:
        self.address = self.combo.currentData()
        self.reload()

    def reload(self) -> None:
        span = self.RANGES[max(0, self.range.current())][0]
        now = int(time.time())
        keys = self.ctl.history_keys_for(self.address) if self.address else []
        points = self.ctl.history.query_keys(keys, now - span) if keys else []
        self.chart.set_data(points, now - span, now)
        dev = next((d for d in self.ctl.devices
                    if d.stable_id == self.address or d.address == self.address), None)
        current = dev.battery if dev and dev.connected else None
        self.stat_now.setText(f"{current}%" if current is not None else "—")
        self.stat_min.setText(f"{min(l for _, l in points)}%" if points else "—")
        eta = estimate_remaining_hours(points) if current is not None else None
        if eta is None:
            self.stat_eta.setText("—")
        elif eta >= 48:
            self.stat_eta.setText(f"{eta / 24:.0f} 天")
        else:
            self.stat_eta.setText(f"{eta:.1f} 小时" if eta < 10 else f"{eta:.0f} 小时")

    def _clear(self) -> None:
        if self.address:
            name = self.combo.currentText()
            keys = self.ctl.history_keys_for(self.address)

            def _do():
                self.ctl.history.clear_keys(keys)
                self.reload()

            self.ctl.flyout.confirm(f"清除“{name}”的全部电量记录？", "清除", _do)


class TrayStylePicker(QWidget):
    """Grid of tray-icon style tiles with live previews."""

    changed = Signal()
    COLUMNS = 4

    def __init__(self, ctl: "Controller", parent: QWidget | None = None):
        super().__init__(parent)
        self.ctl = ctl
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self._group = QButtonGroup(self)
        self._tiles: dict[str, QToolButton] = {}
        for i, (style, title) in enumerate(TRAY_STYLES):
            tile = QToolButton()
            tile.setObjectName("StyleTile")
            tile.setCheckable(True)
            tile.setCursor(Qt.PointingHandCursor)
            tile.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            tile.setText(title)
            tile.setIconSize(QSize(40, 40))
            tile.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            tile.setProperty("style_id", style)
            self._group.addButton(tile, i)
            self._tiles[style] = tile
            grid.addWidget(tile, i // self.COLUMNS, i % self.COLUMNS)
        tile = self._tiles.get(ctl.settings.tray_style) or self._tiles["number"]
        tile.setChecked(True)
        self._group.idClicked.connect(lambda _i: self.changed.emit())
        self.retheme()

    def current(self) -> str:
        btn = self._group.checkedButton()
        return btn.property("style_id") if btn else "number"

    def retheme(self) -> None:
        s = self.ctl.settings
        dark_bar = self.ctl.theme.taskbar_dark
        samples = [(72, "headphones", False), (18, "mouse", False), (55, "gamepad", True)]
        for i, (style, tile) in enumerate(self._tiles.items()):
            level, kind, charging = samples[i % len(samples)]
            px = QPixmap(80, 80)
            px.setDevicePixelRatio(2)
            px.fill(Qt.transparent)
            painter = QPainter(px)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#1F1F1F" if dark_bar else "#EDEDED"))
            painter.drawRoundedRect(QRectF(0, 0, 40, 40), 6, 6)
            icon_px = render_pixmap(style, level, kind, dark_bar, s.low_battery_threshold,
                                    s.tray_colored, charging, 48)
            icon_px.setDevicePixelRatio(2)
            painter.drawPixmap(8, 8, icon_px)
            painter.end()
            tile.setIcon(QIcon(px))


class SettingsPage(QWidget):
    changed = Signal()

    def __init__(self, ctl: "Controller", parent: QWidget | None = None):
        super().__init__(parent)
        self.ctl = ctl
        s = ctl.settings
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        header, _ = _page_header("设置", lambda: self.ctl.show_flyout("devices"))
        root.addLayout(header)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(6)

        self.theme_combo = self._combo([("跟随系统", "system"), ("浅色", "light"), ("深色", "dark")], s.theme)
        self.tray_picker = TrayStylePicker(ctl)
        self.colored_switch = self._switch(s.tray_colored)
        reset_pos = button("恢复默认")
        reset_pos.clicked.connect(self.ctl.reset_flyout_position)
        self._group(lay, "外观", [
            ("主题", "", self.theme_combo),
            ("面板位置", "拖动面板顶部可移动，位置会被记住", reset_pos),
        ])
        self._group(lay, "任务栏电量图标", [
            ("", "", self.tray_picker),
            ("按电量着色", "绿 / 黄 / 红显示电量高低；关闭时仅低电量变红", self.colored_switch),
        ])

        self.low_switch = self._switch(s.notify_low_battery)
        self.threshold = self._spin(5, 50, s.low_battery_threshold, "%")
        self.conn_switch = self._switch(s.notify_connection)
        self._group(lay, "通知", [
            ("低电量提醒", "电量低于阈值时发送系统通知", self.low_switch),
            ("低电量阈值", "", self.threshold),
            ("连接状态通知", "设备连接或断开时通知", self.conn_switch),
        ])

        self.interval = self._spin(5, 600, s.refresh_interval, " 秒")
        self.autostart = self._switch(s.autostart)
        self.input_remap = self._switch(s.input_remap_enabled)
        self.input_status = label("", "secondary", wrap=True)
        self._group(lay, "常规", [
            ("刷新间隔", "设备状态变化会实时更新，此项为轮询兜底", self.interval),
            ("开机自动启动", "", self.autostart),
        ])
        self._group(lay, "输入映射", [
            ("系统级按键映射", "按设备改键；默认关闭。与 PowerToys / keyd / Steam Input 同时启用可能冲突",
             self.input_remap),
            ("", "", self.input_status),
        ])

        self.history_switch = self._switch(s.history_enabled)
        self.history_days = self._spin(1, 365, s.history_days, " 天")
        clear = button("清除全部")
        clear.clicked.connect(lambda: self.ctl.flyout.confirm(
            "清除所有设备的电量历史记录？", "清除", lambda: self.ctl.history.clear()))
        self._group(lay, "电量历史", [
            ("记录电量历史", "", self.history_switch),
            ("保留时长", "", self.history_days),
            ("清除历史记录", "", clear),
        ])

        self.about = label("", "secondary", wrap=True)
        quit_btn = button("退出程序", danger=True)
        quit_btn.clicked.connect(self.ctl.quit)
        self._group(lay, "关于", [(f"{APP_DISPLAY_NAME} {__version__}", "", quit_btn)])
        lay.addWidget(self.about)
        lay.addStretch(1)
        root.addWidget(_scroll(content), 1)

        self.tray_picker.changed.connect(self._save)
        for w in (self.low_switch, self.conn_switch, self.autostart, self.history_switch,
                  self.colored_switch, self.input_remap):
            w.toggled.connect(self._save)
        for w in (self.threshold, self.interval, self.history_days):
            w.valueChanged.connect(self._save)
        self.theme_combo.currentIndexChanged.connect(self._save)
        self.sync_input_controls()

    def sync_input_controls(self) -> None:
        s = self.ctl.settings
        self.input_remap.set_checked_silent(s.input_remap_enabled)
        cap = getattr(self.ctl, "inputmap", None)
        if cap is not None:
            self.input_status.setText(cap.capability.get("message", ""))

    def set_backend_info(self, text: str) -> None:
        self.about.setText(text)

    @staticmethod
    def _combo(items: list[tuple[str, str]], current: str) -> QComboBox:
        c = QComboBox()
        for title, value in items:
            c.addItem(title, value)
        c.setCurrentIndex(max(0, c.findData(current)))
        return c

    @staticmethod
    def _spin(lo: int, hi: int, value: int, suffix: str) -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(value)
        sp.setSuffix(suffix)
        sp.setFixedWidth(96)
        return sp

    @staticmethod
    def _switch(on: bool) -> ToggleSwitch:
        sw = ToggleSwitch()
        sw.set_checked_silent(on)
        return sw

    @staticmethod
    def _group(parent: QVBoxLayout, title: str, rows: list[tuple[str, str, QWidget]]) -> None:
        parent.addWidget(label(title, "section"))
        box = QFrame()
        box.setObjectName("SettingsGroup")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        for i, (name, desc, control) in enumerate(rows):
            row = QFrame()
            row.setObjectName("SettingsRow")
            row.setProperty("first", i == 0)
            h = QHBoxLayout(row)
            h.setContentsMargins(14, 10, 12, 10)
            if not name:
                h.addWidget(control, 1)
                lay.addWidget(row)
                continue
            text = QVBoxLayout()
            text.setSpacing(1)
            text.addWidget(label(name))
            if desc:
                text.addWidget(label(desc, "secondary", wrap=True))
            h.addLayout(text, 1)
            h.addWidget(control, 0, Qt.AlignVCenter)
            lay.addWidget(row)
        parent.addWidget(box)

    def _save(self) -> None:
        s = self.ctl.settings
        s.theme = self.theme_combo.currentData()
        s.tray_style = self.tray_picker.current()
        s.tray_colored = self.colored_switch.isChecked()
        s.notify_low_battery = self.low_switch.isChecked()
        s.low_battery_threshold = self.threshold.value()
        s.notify_connection = self.conn_switch.isChecked()
        s.refresh_interval = self.interval.value()
        s.history_enabled = self.history_switch.isChecked()
        s.history_days = self.history_days.value()
        s.autostart = self.autostart.isChecked()
        s.input_remap_enabled = self.input_remap.isChecked()
        self.tray_picker.retheme()
        self.changed.emit()


class PageStack(QStackedWidget):
    pass
