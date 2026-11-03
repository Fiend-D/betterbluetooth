from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import QApplication

from ..config import IS_LINUX, IS_WINDOWS, Settings


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    footer: str
    card: str
    card_hover: str
    border: str
    text: str
    secondary: str
    disabled: str
    accent: str
    accent_hover: str
    accent_text: str
    control: str
    control_hover: str
    control_pressed: str
    control_border: str
    subtle_hover: str
    subtle_pressed: str
    success: str
    warning: str
    danger: str
    track: str
    scroll: str
    menu_bg: str
    info_bg: str
    warn_bg: str
    error_bg: str

    def color(self, name: str) -> QColor:
        return QColor(getattr(self, name))


LIGHT = Palette(
    dark=False, bg="#F3F3F3", footer="#EBEBEB", card="#FBFBFB", card_hover="#F6F6F6",
    border="#E3E3E3", text="#1B1B1B", secondary="#5F5F5F", disabled="#A0A0A0",
    accent="#005FB8", accent_hover="#1A6EBF", accent_text="#FFFFFF",
    control="#FDFDFD", control_hover="#F7F7F7", control_pressed="#F2F2F2", control_border="#D9D9D9",
    subtle_hover="rgba(0,0,0,14)", subtle_pressed="rgba(0,0,0,9)",
    success="#0F7B0F", warning="#C77800", danger="#C42B1C", track="#D9D9D9",
    scroll="rgba(0,0,0,90)", menu_bg="#F9F9F9",
    info_bg="#EAF3FC", warn_bg="#FFF4CE", error_bg="#FDE7E9",
)

DARK = Palette(
    dark=True, bg="#202020", footer="#1A1A1A", card="#2B2B2B", card_hover="#323232",
    border="#363636", text="#FFFFFF", secondary="#C8C8C8", disabled="#787878",
    accent="#60CDFF", accent_hover="#5ABBEA", accent_text="#000000",
    control="#2D2D2D", control_hover="#333333", control_pressed="#282828", control_border="#3D3D3D",
    subtle_hover="rgba(255,255,255,15)", subtle_pressed="rgba(255,255,255,10)",
    success="#6CCB5F", warning="#FCE100", danger="#FF99A4", track="#4A4A4A",
    scroll="rgba(255,255,255,90)", menu_bg="#2C2C2C",
    info_bg="#1E2B37", warn_bg="#433519", error_bg="#442726",
)

_current: Palette = LIGHT


def palette() -> Palette:
    return _current


def battery_color(level: int | None, threshold: int) -> QColor:
    p = _current
    if level is None:
        return p.color("disabled")
    if level <= threshold:
        return p.color("danger")
    if level <= 50:
        return p.color("warning")
    return p.color("success")


def _windows_accent() -> str | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
            abgr, _ = winreg.QueryValueEx(key, "AccentColor")
        r, g, b = abgr & 0xFF, (abgr >> 8) & 0xFF, (abgr >> 16) & 0xFF
        return f"#{r:02X}{g:02X}{b:02X}"
    except OSError:
        return None


def _windows_reg_light(value: str) -> bool | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return bool(winreg.QueryValueEx(key, value)[0])
    except OSError:
        return None


def _gnome_prefers_dark() -> bool | None:
    try:
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if "prefer-dark" in out:
        return True
    if "prefer-light" in out or "default" in out:
        try:
            gtk = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                                 capture_output=True, text=True, timeout=2).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        return "dark" in gtk.lower()
    return None


def system_is_dark() -> bool:
    if IS_LINUX:
        value = _gnome_prefers_dark()
        if value is not None:
            return value
    if IS_WINDOWS:
        light = _windows_reg_light("AppsUseLightTheme")
        if light is not None:
            return not light
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def taskbar_is_dark() -> bool:
    if IS_WINDOWS:
        light = _windows_reg_light("SystemUsesLightTheme")
        return not light if light is not None else True
    return True


def _lighten(hex_color: str, factor: float) -> str:
    c = QColor(hex_color)
    h, s, l, a = c.getHslF()
    return QColor.fromHslF(h, s, min(1.0, l + (1 - l) * factor), a).name()


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._system_dark = system_is_dark()
        self._taskbar_dark = taskbar_is_dark()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self._poll())
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(10_000)
        self.apply()

    @property
    def taskbar_dark(self) -> bool:
        return self._taskbar_dark

    def _poll(self) -> None:
        dark, taskbar = system_is_dark(), taskbar_is_dark()
        if (dark, taskbar) != (self._system_dark, self._taskbar_dark):
            self._system_dark, self._taskbar_dark = dark, taskbar
            self.apply()

    def is_dark(self) -> bool:
        if self.settings.theme == "dark":
            return True
        if self.settings.theme == "light":
            return False
        return self._system_dark

    def apply(self) -> None:
        global _current
        base = DARK if self.is_dark() else LIGHT
        accent = _windows_accent() if IS_WINDOWS else None
        if accent:
            if base.dark:
                acc = _lighten(accent, 0.45)
                base = replace(base, accent=acc, accent_hover=QColor(acc).darker(110).name())
            else:
                base = replace(base, accent=accent, accent_hover=QColor(accent).lighter(112).name())
        _current = base
        _write_arrows(base)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(stylesheet(base))
        self.changed.emit()


_ARROW_DIR = Path(tempfile.gettempdir()) / f"betterbluetooth-{os.getpid()}"
_ARROWS = {
    "down": "M6 9l6 6 6-6",
    "up": "M6 15l6-6 6 6",
}


def _arrow_path(name: str, p: Palette) -> str:
    return (_ARROW_DIR / f"{name}-{'dark' if p.dark else 'light'}.svg").as_posix()


def _write_arrows(p: Palette) -> None:
    _ARROW_DIR.mkdir(parents=True, exist_ok=True)
    for name, d in _ARROWS.items():
        Path(_arrow_path(name, p)).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{p.secondary}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="{d}"/></svg>')


def cleanup() -> None:
    shutil.rmtree(_ARROW_DIR, ignore_errors=True)


def app_font() -> QFont:
    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI",
                      "Noto Sans CJK SC", "Cantarell", "Ubuntu", "sans-serif"])
    font.setPixelSize(14)
    return font


def _soft(hex_color: str, alpha: int) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def stylesheet(p: Palette) -> str:
    accent_soft = _soft(p.accent, 46 if p.dark else 34)
    accent_soft_hover = _soft(p.accent, 64 if p.dark else 50)
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {p.text}; font-size: 14px; }}
#Panel {{ background: {p.bg}; border: 1px solid {p.border}; border-radius: 10px; }}
#Footer {{ background: {p.footer}; border-top: 1px solid {p.border};
          border-bottom-left-radius: 10px; border-bottom-right-radius: 10px; }}
#Panel[native="true"] {{ border: none; border-radius: 0; }}
#Footer[native="true"] {{ border-bottom-left-radius: 0; border-bottom-right-radius: 0; }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 18px; font-weight: 600; }}
QLabel[role="pageTitle"] {{ font-size: 16px; font-weight: 600; }}
QLabel[role="name"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="secondary"] {{ color: {p.secondary}; font-size: 12px; }}
QLabel[role="section"] {{ color: {p.secondary}; font-size: 12px; font-weight: 600; padding: 6px 2px 0 2px; }}
QLabel[role="big"] {{ font-size: 26px; font-weight: 600; }}
QLabel[role="empty"] {{ color: {p.secondary}; font-size: 13px; }}
#Card {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 8px; }}
#Card[hover="true"] {{ background: {p.card_hover}; }}
#Card[dim="true"] QLabel[role="name"] {{ color: {p.secondary}; }}
QPushButton {{ background: {p.control}; color: {p.text}; border: 1px solid {p.control_border};
              border-radius: 5px; padding: 5px 14px; min-height: 20px; }}
QPushButton:hover {{ background: {p.control_hover}; }}
QPushButton:pressed {{ background: {p.control_pressed}; color: {p.secondary}; }}
QPushButton:disabled {{ color: {p.disabled}; }}
QPushButton[accent="true"] {{ background: {p.accent}; color: {p.accent_text}; border: 1px solid {p.accent}; }}
QPushButton[accent="true"]:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton[accent="true"]:disabled {{ background: {p.track}; border-color: {p.track}; color: {p.disabled}; }}
QPushButton[flat="true"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[flat="true"]:hover {{ background: {p.subtle_hover}; }}
QPushButton[danger="true"] {{ color: {p.danger}; }}
QPushButton[segment="true"] {{ border-radius: 5px; padding: 4px 12px; background: transparent;
                               border: 1px solid transparent; color: {p.secondary}; }}
QPushButton[segment="true"]:hover {{ background: {p.subtle_hover}; }}
QPushButton[segment="true"]:checked {{ background: {p.control}; color: {p.text};
                                       border: 1px solid {p.control_border}; font-weight: 600; }}
#Segment {{ background: {p.subtle_pressed}; border-radius: 7px; }}
QToolButton#IconButton {{ background: transparent; border: none; border-radius: 5px; padding: 5px; }}
QToolButton#IconButton:hover {{ background: {p.subtle_hover}; }}
QToolButton#IconButton:pressed {{ background: {p.subtle_pressed}; }}
QToolButton#IconButton:checked {{ background: {accent_soft}; }}
QToolButton#IconButton:checked:hover {{ background: {accent_soft_hover}; }}
QToolButton#StyleTile {{ background: {p.control}; border: 1px solid {p.control_border}; border-radius: 6px;
                         padding: 6px 2px 4px 2px; font-size: 12px; color: {p.secondary}; }}
QToolButton#StyleTile:hover {{ background: {p.control_hover}; }}
QToolButton#StyleTile:checked {{ border: 2px solid {p.accent}; background: {accent_soft}; color: {p.text}; }}
#DragHandle {{ background: {p.track}; border-radius: 2px; }}
QToolButton#IconButton::menu-indicator {{ image: none; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ width: 6px; background: transparent; margin: 2px 0 2px 0; }}
QScrollBar::handle:vertical {{ background: {p.scroll}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QLineEdit, QSpinBox, QComboBox {{ background: {p.control}; border: 1px solid {p.control_border};
              border-radius: 5px; padding: 4px 8px; color: {p.text};
              selection-background-color: {p.accent}; selection-color: {p.accent_text}; min-height: 20px; }}
QLineEdit:focus, QSpinBox:focus {{ border-bottom: 2px solid {p.accent}; }}
QComboBox:hover, QSpinBox:hover {{ background: {p.control_hover}; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{_arrow_path('down', p)}"); width: 12px; height: 12px; }}
QSpinBox {{ padding-right: 20px; }}
QSpinBox::up-arrow {{ image: url("{_arrow_path('up', p)}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{_arrow_path('down', p)}"); width: 10px; height: 10px; }}
QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; margin: 3px 3px 0 0; }}
QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; margin: 0 3px 3px 0; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {p.subtle_hover}; border-radius: 3px; }}
QComboBox QAbstractItemView {{ background: {p.menu_bg}; color: {p.text}; border: 1px solid {p.border};
              selection-background-color: {p.subtle_hover}; selection-color: {p.text}; padding: 4px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}
QMenu {{ background: {p.menu_bg}; border: 1px solid {p.border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 5px; color: {p.text}; background: transparent; }}
QMenu::item:selected {{ background: {p.subtle_hover}; }}
QMenu::item:disabled {{ color: {p.secondary}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 6px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 6px; }}
QToolTip {{ background: {p.menu_bg}; color: {p.text}; border: 1px solid {p.border}; padding: 4px 8px; }}
#InfoBar {{ border-radius: 6px; border: 1px solid {p.border}; }}
#InfoBar[kind="info"] {{ background: {p.info_bg}; }}
#InfoBar[kind="warning"] {{ background: {p.warn_bg}; }}
#InfoBar[kind="error"] {{ background: {p.error_bg}; }}
#InfoBar[kind="success"] {{ background: {p.card}; }}
#SettingsGroup {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 8px; }}
#SettingsRow {{ border-top: 1px solid {p.border}; }}
#SettingsRow[first="true"] {{ border-top: none; }}
"""
