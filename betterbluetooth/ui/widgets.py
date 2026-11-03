from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    Property, QEasingCurve, QEvent, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy,
    QToolButton, QWidget,
)

from . import icons, theme


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


class ElidedLabel(QLabel):
    """Single-line label that elides with '…' instead of clipping."""

    def __init__(self, text: str = "", role: str | None = None):
        super().__init__()
        if role:
            self.setProperty("role", role)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._full = ""
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self._full = text
        self._elide()

    def full_text(self) -> str:
        return self._full

    def _elide(self) -> None:
        elided = self.fontMetrics().elidedText(self._full, Qt.ElideRight, max(10, self.width()))
        super().setText(elided)
        self.setToolTip(self._full if elided != self._full else "")

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._elide()

    def changeEvent(self, e):  # noqa: N802
        super().changeEvent(e)
        if e.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._elide()


def button(text: str, accent: bool = False, flat: bool = False, danger: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    if accent:
        btn.setProperty("accent", True)
    if flat:
        btn.setProperty("flat", True)
    if danger:
        btn.setProperty("danger", True)
    return btn


def make_menu(parent: QWidget | None = None) -> QMenu:
    menu = QMenu(parent)
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


class IconButton(QToolButton):
    """Transparent square button with a themed line icon."""

    def __init__(self, icon_name: str, tooltip: str = "", size: int = 16, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("IconButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setIconSize(QSize(size, size))
        self._icon_name = icon_name
        self._checked_icon_name: str | None = None
        self._color_role = "text"
        self.toggled.connect(lambda _on: self.retheme())
        self.retheme()

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self.retheme()

    def set_checked_icon(self, name: str) -> None:
        self._checked_icon_name = name
        self.retheme()

    def set_color_role(self, role: str) -> None:
        self._color_role = role
        self.retheme()

    def retheme(self) -> None:
        p = theme.palette()
        checked = self.isCheckable() and self.isChecked()
        name = (self._checked_icon_name or self._icon_name) if checked else self._icon_name
        color = p.accent if checked else getattr(p, self._color_role)
        self.setIcon(icons.icon(name, color, self.iconSize().width()))


class ToggleSwitch(QAbstractButton):
    """Fluent-style on/off switch."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 20)
        self._pos = 0.0
        self._hover = False
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        blocked = self.signalsBlocked()
        super().setChecked(checked)
        if blocked or self._anim.state() != QPropertyAnimation.Running:
            self._pos = 1.0 if checked else 0.0
            self.update()

    def set_checked_silent(self, checked: bool) -> None:
        self.blockSignals(True)
        self.setChecked(checked)
        self._pos = 1.0 if checked else 0.0
        self.blockSignals(False)
        self.update()

    def enterEvent(self, e):  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, e):  # noqa: N802
        self._hover = False
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, 20)

    def paintEvent(self, _e):  # noqa: N802
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = r.height() / 2
        on = self._pos > 0.5
        enabled = self.isEnabled()
        if on:
            fill = p.color("accent") if enabled else p.color("disabled")
            if self._hover and enabled:
                fill = QColor(p.accent_hover)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
        else:
            painter.setPen(QPen(p.color("secondary" if enabled else "disabled"), 1))
            painter.setBrush(_rgba(p.subtle_hover) if self._hover else Qt.NoBrush)
        painter.drawRoundedRect(r, radius, radius)
        knob_r = 6 if not self._hover else 7
        x = 10 + self._pos * 20
        knob_color = p.color("accent_text") if on else p.color("secondary" if enabled else "disabled")
        painter.setPen(Qt.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(QRectF(x - knob_r, 10 - knob_r, knob_r * 2, knob_r * 2))


def _rgba(text: str) -> QColor:
    if text.startswith("rgba"):
        r, g, b, a = (int(x) for x in text[5:-1].split(","))
        return QColor(r, g, b, a)
    return QColor(text)


class BatteryBar(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._level: int | None = None
        self._threshold = 20

    def set_level(self, level: int | None, threshold: int) -> None:
        self._level, self._threshold = level, threshold
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        painter.setBrush(p.color("track"))
        painter.drawRoundedRect(r, 2, 2)
        if self._level is not None:
            w = max(r.height(), r.width() * self._level / 100)
            painter.setBrush(theme.battery_color(self._level, self._threshold))
            painter.drawRoundedRect(QRectF(r.x(), r.y(), w, r.height()), 2, 2)


class ProgressRing(QWidget):
    """Indeterminate spinning arc."""

    def __init__(self, size: int = 16, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def showEvent(self, e):  # noqa: N802
        self._timer.start(16)
        super().showEvent(e)

    def hideEvent(self, e):  # noqa: N802
        self._timer.stop()
        super().hideEvent(e)

    def paintEvent(self, _e):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(theme.palette().color("accent"), 2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        span = 100 + 60 * abs(((self._angle * 2) % 360) - 180) / 180
        painter.drawArc(r, int(-self._angle * 16), int(span * 16))


class DeviceAvatar(QWidget):
    """Round tile with a device-type glyph."""

    def __init__(self, icon_name: str = "bluetooth", size: int = 36, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._icon = icon_name
        self._active = True

    def set_state(self, icon_name: str, active: bool) -> None:
        self._icon, self._active = icon_name, active
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bg = p.color("accent")
        bg.setAlpha(40 if self._active else 0)
        if not self._active:
            bg = _rgba(p.subtle_hover)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        r = QRectF(self.rect())
        painter.drawRoundedRect(r, 8, 8)
        s = r.width() * 0.52
        color = p.color("accent") if self._active else p.color("secondary")
        icons.render(painter, self._icon, QRectF((r.width() - s) / 2, (r.height() - s) / 2, s, s), color)


class InfoBar(QFrame):
    """Inline message strip (info / warning / error / success) with optional actions."""

    closed = Signal()

    def __init__(self, text: str, kind: str = "info", closable: bool = True,
                 actions: list[tuple[str, Callable[[], None], bool]] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("InfoBar")
        self.setProperty("kind", kind)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 6, 8)
        lay.setSpacing(8)
        self._icon = QLabel()
        self._kind = kind
        lay.addWidget(self._icon, 0, Qt.AlignTop)
        self.text = label(text, wrap=True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text.setStyleSheet("font-size: 12px;")
        lay.addWidget(self.text, 1)
        for title, fn, accent in actions or []:
            b = button(title, accent=accent)
            b.clicked.connect(fn)
            lay.addWidget(b, 0, Qt.AlignVCenter)
        if closable:
            close = IconButton("close", "关闭", 12)
            close.clicked.connect(self._close)
            lay.addWidget(close, 0, Qt.AlignTop)
        self.retheme()

    def retheme(self) -> None:
        p = theme.palette()
        role = {"info": "accent", "warning": "warning", "error": "danger", "success": "success"}[self._kind]
        name = {"info": "info", "warning": "warning", "error": "error", "success": "success"}[self._kind]
        self._icon.setPixmap(icons.pixmap(name, getattr(p, role), 16))

    def _close(self) -> None:
        self.hide()
        self.closed.emit()
        self.deleteLater()


class Segmented(QFrame):
    changed = Signal(int)

    def __init__(self, items: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Segment")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        for i, text in enumerate(items):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("segment", True)
            b.setCursor(Qt.PointingHandCursor)
            self._group.addButton(b, i)
            lay.addWidget(b)
        self._group.button(0).setChecked(True)
        self._group.idClicked.connect(self.changed.emit)

    def current(self) -> int:
        return self._group.checkedId()

    def set_current(self, index: int) -> None:
        self._group.button(index).setChecked(True)


def retheme_tree(root: QWidget) -> None:
    for w in root.findChildren(QWidget):
        fn = getattr(w, "retheme", None)
        if callable(fn) and w is not root:
            fn()
        QWidget.update(w)
