from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_DISPLAY_NAME
from ..config import IS_WINDOWS
from . import icons, theme
from .input_page import InputPage
from .pages import DevicesPage, HistoryPage, ScanPage, SettingsPage
from .widgets import IconButton, InfoBar, button, retheme_tree

if TYPE_CHECKING:
    from ..app import Controller

# On Windows a translucent layered window with QGraphicsDropShadowEffect leaves stale pixels when
# child widgets change, so there the window is opaque and DWM draws the rounded corners and shadow.
NATIVE_FRAME = IS_WINDOWS
SHADOW = 0 if NATIVE_FRAME else 18
WIDTH = 400
HEIGHT = 600
# 108-key realistic keyboard needs a wider canvas (clamped to screen at runtime).
INPUT_WIDTH = 980
INPUT_HEIGHT = 620
EDGE_GAP = 8
DRAG_ZONE = 56


class Flyout(QWidget):
    def __init__(self, ctl: "Controller") -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.ctl = ctl
        self.pinned = False
        self._hidden_at = 0.0
        self._suppress_hide_until = 0.0
        self._user_moving = False
        self._last_user_move = 0.0
        self._manual_drag: QPoint | None = None
        self._save_pos_timer = QTimer(self)
        self._save_pos_timer.setSingleShot(True)
        self._save_pos_timer.setInterval(400)
        self._save_pos_timer.timeout.connect(self._save_position)
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setWindowIcon(icons.app_icon())
        if not NATIVE_FRAME:
            self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WIDTH + SHADOW * 2, HEIGHT + SHADOW * 2)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        self.panel = QFrame()
        self.panel.setObjectName("Panel")
        self.panel.setProperty("native", NATIVE_FRAME)
        self._shadow: QGraphicsDropShadowEffect | None = None
        if not NATIVE_FRAME:
            self._shadow = QGraphicsDropShadowEffect(self.panel)
            self._shadow.setBlurRadius(SHADOW * 1.6)
            self._shadow.setOffset(0, 4)
            self.panel.setGraphicsEffect(self._shadow)
        outer.addWidget(self.panel)

        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.stack = QStackedWidget()
        self.devices_page = DevicesPage(ctl)
        self.scan_page = ScanPage(ctl)
        self.history_page = HistoryPage(ctl)
        self.input_page = InputPage(ctl)
        self.settings_page = SettingsPage(ctl)
        for page in (self.devices_page, self.scan_page, self.history_page, self.input_page, self.settings_page):
            self.stack.addWidget(page)
        lay.addWidget(self.stack, 1)

        self.footer = QFrame()
        self.footer.setObjectName("Footer")
        self.footer.setProperty("native", NATIVE_FRAME)
        foot = QHBoxLayout(self.footer)
        foot.setContentsMargins(12, 10, 12, 10)
        foot.setSpacing(4)
        self.add_btn = button("添加设备", accent=True)
        self.add_btn.clicked.connect(lambda: self.show_page("scan"))
        foot.addWidget(self.add_btn)
        foot.addStretch(1)
        self.history_btn = IconButton("history", "电量历史", 16)
        self.history_btn.clicked.connect(lambda: self.show_page("history"))
        foot.addWidget(self.history_btn)
        self.refresh_btn = IconButton("refresh", "刷新", 16)
        self.refresh_btn.clicked.connect(self.ctl.worker.refresh)
        foot.addWidget(self.refresh_btn)
        self.settings_btn = IconButton("settings", "设置", 16)
        self.settings_btn.clicked.connect(lambda: self.show_page("settings"))
        foot.addWidget(self.settings_btn)
        lay.addWidget(self.footer)

        # Overlay toasts so showing/hiding them never reflows the page (no jump).
        self.toast_host = QWidget(self.panel)
        self.toast_host.setObjectName("ToastHost")
        self.toast_host.setStyleSheet("#ToastHost { background: transparent; }")
        self.toast_host.hide()
        self.toasts = QVBoxLayout(self.toast_host)
        self.toasts.setContentsMargins(12, 0, 12, 8)
        self.toasts.setSpacing(6)
        self.toasts.addStretch(1)

        self.handle = QFrame(self.panel)
        self.handle.setObjectName("DragHandle")
        self.handle.setFixedSize(36, 4)
        self.handle.setToolTip("拖动以移动面板")

        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.setInterval(0)
        self._repaint_timer.timeout.connect(self._repaint_all)

        self.ctl.theme.changed.connect(self.retheme)
        self.retheme()

    # ---- appearance ----

    def retheme(self) -> None:
        p = theme.palette()
        if self._shadow is not None:
            self._shadow.setColor(QColor(0, 0, 0, 110 if p.dark else 55))
        retheme_tree(self)

    def schedule_repaint(self) -> None:
        if self.isVisible():
            self._repaint_timer.start()

    def _repaint_all(self) -> None:
        QApplication.sendPostedEvents(None, QEvent.LayoutRequest)
        if self._shadow is not None:
            self._shadow.update()
        self.panel.update()
        self.update()

    # ---- pages ----

    def show_page(self, name: str = "devices", arg: str | None = None) -> None:
        if self.stack.currentWidget() is self.scan_page and name != "scan":
            self.scan_page.stop()
        if self.stack.currentWidget() is self.input_page and name != "input":
            self.input_page.set_device(None)
        page = {
            "devices": self.devices_page,
            "scan": self.scan_page,
            "history": self.history_page,
            "input": self.input_page,
            "settings": self.settings_page,
        }[name]
        if name == "scan":
            self.scan_page.start()
        elif name == "history":
            self.history_page.set_device(arg or self.history_page.address)
        elif name == "input":
            try:
                self.input_page.set_device(arg)
            except Exception as e:  # noqa: BLE001
                self.toast(f"无法打开按键映射：{e}", "error", 8000)
                name = "devices"
                page = self.devices_page
        self.stack.setCurrentWidget(page)
        self.footer.setVisible(name == "devices")
        self.add_btn.setVisible("scan" in self.ctl.capabilities)
        self._apply_page_size(name == "input")
        self.schedule_repaint()

    def _apply_page_size(self, wide: bool) -> None:
        screen = QGuiApplication.screenAt(self.pos() + QPoint(20, 20)) \
            or QGuiApplication.screenAt(QCursor.pos()) \
            or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
        # Leave a margin so the expanded input page never exceeds the work area.
        max_w = max(360, avail.width() - EDGE_GAP * 2)
        max_h = max(400, avail.height() - EDGE_GAP * 2)
        want_w = (INPUT_WIDTH if wide else WIDTH) + SHADOW * 2
        want_h = (INPUT_HEIGHT if wide else HEIGHT) + SHADOW * 2
        w = min(want_w, max_w)
        h = min(want_h, max_h)
        if self.width() != w or self.height() != h:
            self.setFixedSize(w, h)
            self.handle.move((self.panel.width() - self.handle.width()) // 2, 6)
        self._clamp_on_screen()

    def _clamp_on_screen(self) -> None:
        """Keep the flyout fully (or mostly) inside the current screen."""
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) \
            or QGuiApplication.screenAt(QCursor.pos()) \
            or QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        geo = self.frameGeometry()
        x, y = geo.x(), geo.y()
        if geo.right() > avail.right():
            x = avail.right() - geo.width() + 1
        if geo.bottom() > avail.bottom():
            y = avail.bottom() - geo.height() + 1
        if x < avail.left():
            x = avail.left()
        if y < avail.top():
            y = avail.top()
        if QPoint(x, y) != self.pos():
            self.move(x, y)

    # ---- messages ----

    def _clear_overlay_toasts(self) -> None:
        while self.toasts.count() > 1:
            item = self.toasts.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()

    def _place_toast_host(self) -> None:
        """Pin toast layer above the footer without taking layout space."""
        host = self.toast_host
        has = self.toasts.count() > 1
        if not has:
            host.hide()
            return
        foot_h = self.footer.height() if self.footer.isVisible() else 0
        h = min(120, max(48, self.panel.height() // 5))
        host.setGeometry(0, max(0, self.panel.height() - foot_h - h), self.panel.width(), h)
        host.show()
        host.raise_()

    def toast(self, text: str, kind: str = "info", timeout: int = 4000) -> InfoBar:
        self._clear_overlay_toasts()
        bar = InfoBar(text, kind)
        self.toasts.addWidget(bar)
        self._place_toast_host()
        bar.destroyed.connect(lambda *_: self._place_toast_host())
        if timeout:
            QTimer.singleShot(timeout, bar, bar.deleteLater)
        return bar

    def confirm(self, text: str, action: str, on_yes: Callable[[], None]) -> None:
        holder: list[InfoBar] = []

        def yes() -> None:
            holder[0].deleteLater()
            on_yes()

        self._clear_overlay_toasts()
        bar = InfoBar(text, "warning", closable=False,
                      actions=[(action, yes, True), ("取消", lambda: holder[0].deleteLater(), False)])
        holder.append(bar)
        self.toasts.addWidget(bar)
        self._place_toast_host()
        bar.destroyed.connect(lambda *_: self._place_toast_host())

    # ---- show / hide ----

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        elif time.monotonic() - self._hidden_at > 0.3:
            self.popup()

    def popup(self) -> None:
        self._user_moving = False
        # Avoid the QMenu-close ActivationChange race that auto-hides the flyout
        # right after switching to a wider page (esp. Windows).
        self._suppress_hide_until = time.monotonic() + 0.6
        self.move(self._anchor())
        self._clamp_on_screen()
        self.show()
        if NATIVE_FRAME:
            _apply_dwm_frame(int(self.winId()))
        self.raise_()
        self.activateWindow()
        self.schedule_repaint()

    def _saved_position(self) -> QPoint | None:
        pos = self.ctl.settings.flyout_pos
        if not pos or len(pos) != 2:
            return None
        point = QPoint(int(pos[0]), int(pos[1]))
        center = QRect(point, self.size()).center()
        if any(sc.availableGeometry().contains(center) for sc in QGuiApplication.screens()):
            return point
        return None

    def reset_position(self) -> None:
        self.ctl.settings.flyout_pos = None
        self.ctl.settings.save()
        if self.isVisible():
            self._user_moving = False
            self.move(self._anchor())

    def _anchor(self) -> QPoint:
        saved = self._saved_position()
        if saved is not None:
            return saved
        tray_geo = self.ctl.tray.main.geometry() if self.ctl.tray else QRect()
        screen = QGuiApplication.screenAt(tray_geo.center()) if tray_geo.isValid() else None
        screen = screen or QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        full, avail = screen.geometry(), screen.availableGeometry()
        w, h = self.width(), self.height()
        x = avail.right() - w + SHADOW - EDGE_GAP
        if tray_geo.isValid():
            x = min(x, max(avail.left() - SHADOW, tray_geo.center().x() - w // 2))
        if avail.top() > full.top():
            y = avail.top() - SHADOW + EDGE_GAP
        elif avail.left() > full.left():
            x, y = avail.left() - SHADOW + EDGE_GAP, avail.bottom() - h + SHADOW - EDGE_GAP
        else:
            y = avail.bottom() - h + SHADOW - EDGE_GAP
        return QPoint(x, y)

    def changeEvent(self, e):  # noqa: N802
        if e.type() == QEvent.ActivationChange and not self.isActiveWindow() and self.isVisible():
            QTimer.singleShot(0, self._maybe_hide)
        super().changeEvent(e)

    def _maybe_hide(self) -> None:
        if self.pinned or self.isActiveWindow():
            return
        if time.monotonic() < self._suppress_hide_until:
            return
        if QGuiApplication.mouseButtons() & Qt.LeftButton or time.monotonic() - self._last_user_move < 1.0:
            return
        active = QGuiApplication.focusWindow()
        if active is not None and active is not self.windowHandle():
            return
        self.hide()

    def hideEvent(self, e):  # noqa: N802
        self._hidden_at = time.monotonic()
        if self.stack.currentWidget() is self.scan_page:
            self.scan_page.stop()
            self.show_page("devices")
        elif self.stack.currentWidget() is self.input_page:
            self.input_page.set_device(None)
        super().hideEvent(e)

    # ---- dragging ----

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self.handle.move((self.panel.width() - self.handle.width()) // 2, 6)
        self.handle.raise_()
        self._place_toast_host()

    def mousePressEvent(self, e):  # noqa: N802
        local = self.panel.mapFrom(self, e.position().toPoint())
        if e.button() != Qt.LeftButton or not (0 <= local.y() < DRAG_ZONE) or not self.panel.rect().contains(local):
            return super().mousePressEvent(e)
        self._user_moving = True
        self._last_user_move = time.monotonic()
        handle = self.windowHandle()
        if handle is None or not handle.startSystemMove():
            self._manual_drag = e.globalPosition().toPoint() - self.pos()
        e.accept()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._manual_drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._manual_drag)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._manual_drag is not None:
            self._manual_drag = None
            self._save_position()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def moveEvent(self, e):  # noqa: N802
        super().moveEvent(e)
        if self._user_moving:
            self._last_user_move = time.monotonic()
            self._save_pos_timer.start()

    def _save_position(self) -> None:
        if not self._user_moving:
            return
        self.ctl.settings.flyout_pos = [self.x(), self.y()]
        self.ctl.settings.save()

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() == Qt.Key_Escape:
            if self.stack.currentWidget() is not self.devices_page:
                self.show_page("devices")
            else:
                self.hide()
            return
        super().keyPressEvent(e)


def _apply_dwm_frame(hwnd: int) -> None:
    """Rounded corners (Windows 11) and the system drop shadow for the frameless popup."""
    import ctypes
    from ctypes import wintypes

    class MARGINS(ctypes.Structure):
        _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int),
                    ("top", ctypes.c_int), ("bottom", ctypes.c_int)]

    try:
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(MARGINS)]
        policy = ctypes.c_int(2)  # DWMNCRP_ENABLED
        dwm.DwmSetWindowAttribute(hwnd, 2, ctypes.byref(policy), ctypes.sizeof(policy))  # DWMWA_NCRENDERING_POLICY
        corner = ctypes.c_int(2)  # DWMWCP_ROUND
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))  # CORNER_PREFERENCE
        dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(1, 1, 1, 1)))
    except (AttributeError, OSError):
        pass
