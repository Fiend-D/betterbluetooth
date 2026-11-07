"""Eden-style per-device key test + remap (central visual + surrounding bind chips)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QInputDialog, QStackedWidget, QVBoxLayout, QWidget

from ..inputmap import PRESETS, RemapRule, label as code_label, supports_input
from ..inputmap.base import InputEvent
from ..inputmap.codes import qt_key_to_code
from ..models import DeviceKind
from .input_visuals import VisualGamepad, VisualKeyboard
from .pages import _page_header
from .widgets import ToggleSwitch, button, label

if TYPE_CHECKING:
    from ..app import Controller
    from ..inputmap.profile import InputProfile


class InputPage(QWidget):
    def __init__(self, ctl: "Controller", parent: QWidget | None = None):
        super().__init__(parent)
        self.ctl = ctl
        self.address: str | None = None
        self._profile: InputProfile | None = None
        self._kind: DeviceKind = DeviceKind.KEYBOARD
        self._armed_src: str | None = None
        self._grabbing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        header, self.title_lbl = _page_header("按键映射", lambda: self.ctl.show_flyout("devices"))
        root.addLayout(header)
        self.subtitle = label("", "secondary", wrap=True)
        root.addWidget(self.subtitle)

        top = QHBoxLayout()
        top.addWidget(label("启用映射"), 0)
        self.enable = ToggleSwitch()
        self.enable.toggled.connect(self._toggle_enable)
        top.addWidget(self.enable)
        top.addSpacing(12)
        self.keepalive_row = QFrame()
        klay = QHBoxLayout(self.keepalive_row)
        klay.setContentsMargins(0, 0, 0, 0)
        klay.setSpacing(6)
        klay.addWidget(label("Joy-Con 保活"))
        self.keepalive = ToggleSwitch()
        self.keepalive.setToolTip("全速报告，减轻空闲断连（可能与 Steam 冲突）")
        self.keepalive.toggled.connect(self._toggle_keepalive)
        klay.addWidget(self.keepalive)
        top.addWidget(self.keepalive_row)
        top.addStretch(1)
        self.preset = QComboBox()
        self.preset.setMinimumWidth(160)
        top.addWidget(self.preset)
        apply_preset = button("应用", flat=True)
        apply_preset.clicked.connect(self._apply_preset)
        top.addWidget(apply_preset)
        save_preset = button("存为预设", flat=True)
        save_preset.setToolTip("把当前设备的改键方案存成可复用预设（键盘/手柄通用）")
        save_preset.clicked.connect(self._save_preset)
        top.addWidget(save_preset)
        clear_btn = button("清除全部", flat=True)
        clear_btn.clicked.connect(self._clear_all)
        top.addWidget(clear_btn)
        root.addLayout(top)
        self._reload_presets()

        self._hint = label("打开本页后直接按实体键即可测试高亮；点映射框后再按目标键完成改建。", "secondary", wrap=True)
        root.addWidget(self._hint)

        self.visuals = QStackedWidget()
        self.keyboard = VisualKeyboard()
        self.gamepad = VisualGamepad()
        # Only bindRequested — keyPicked is the same click; connecting both
        # armed then immediately cancelled the selection.
        for board in (self.keyboard, self.gamepad):
            board.bindRequested.connect(self._on_bind_source)
        self.visuals.addWidget(self.keyboard)
        self.visuals.addWidget(self.gamepad)
        root.addWidget(self.visuals, 1)

        self.status = label("", "secondary", wrap=True)
        root.addWidget(self.status)

        svc = ctl.inputmap
        svc.eventReceived.connect(self._on_event)
        svc.statusChanged.connect(lambda t: self.status.setText(t))
        self.status.setText(svc.capability.get("message", ""))

    def set_device(self, address: str | None) -> None:
        self.address = address
        self._armed_src = None
        self.keyboard.clear_pressed()
        self.gamepad.clear_pressed()
        self.keyboard.set_armed(None)
        self.gamepad.set_armed(None)
        svc = self.ctl.inputmap
        if not address:
            self._set_grab(False)
            svc.set_test_target(None)
            return
        dev = next((d for d in self.ctl.devices if d.address == address), None)
        if dev is None or not supports_input(dev):
            self.title_lbl.setText("按键映射")
            self.subtitle.setText("当前设备不支持按键测试 / 映射")
            self._set_grab(False)
            svc.set_test_target(None)
            return
        self._profile = svc.profile_for(dev)
        self._kind = dev.kind
        self.title_lbl.setText(dev.name or "设备")
        kind_zh = {"keyboard": "键盘", "gamepad": "手柄", "mouse": "鼠标"}.get(dev.kind.value, dev.kind.value)
        sid = (dev.stable_id or "")[-8:]
        self.subtitle.setText(f"{kind_zh} · {dev.address}" + (f" · 身份 …{sid}" if sid else ""))
        self.enable.set_checked_silent(self._profile.enabled)
        self._reload_presets()
        is_jc = "JOY-CON" in (dev.name or "").upper() or "PRO CONTROLLER" in (dev.name or "").upper()
        self.keepalive_row.setVisible(dev.kind == DeviceKind.GAMEPAD and is_jc)
        self.keepalive.set_checked_silent(self._profile.joycon_keepalive)
        if dev.kind == DeviceKind.GAMEPAD:
            self.visuals.setCurrentWidget(self.gamepad)
            self.gamepad.set_device_name(dev.name)
            self._set_grab(False)
            self._hint.setText("请按手柄按键查看高亮；点示意图按键后再按目标键（可为键盘键）完成改建。")
        else:
            self.visuals.setCurrentWidget(self.keyboard)
            self.keyboard.set_device_name(dev.name)
            self._set_grab(True)
            self._hint.setStyleSheet("")
            self._hint.setText("点键帽选源键 → 再按目标键完成改建；未选中时按键只做高亮测试。系统生效需打开「启用映射」。")
        self._refresh_maps()
        svc.set_test_target(self._profile.device_key)
        # Ensure Joy-Con / HID backends also track this device while testing.
        svc.update_devices(self.ctl.devices)

    def _set_grab(self, on: bool) -> None:
        if on and not self._grabbing:
            self.setFocus(Qt.OtherFocusReason)
            self.grabKeyboard()
            self._grabbing = True
        elif not on and self._grabbing:
            self.releaseKeyboard()
            self._grabbing = False

    def hideEvent(self, e):  # noqa: N802
        self._set_grab(False)
        super().hideEvent(e)

    def keyPressEvent(self, e):  # noqa: N802
        if self._handle_qt_key(e, True):
            e.accept()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):  # noqa: N802
        if self._handle_qt_key(e, False):
            e.accept()
            return
        super().keyReleaseEvent(e)

    def _handle_qt_key(self, e, pressed: bool) -> bool:
        """Reliable keyboard testing while the mapping page has grabbed the keyboard."""
        if self._kind == DeviceKind.GAMEPAD or not self._profile:
            return False
        if e.isAutoRepeat():
            return True
        code = qt_key_to_code(int(e.key()), int(e.modifiers()))
        if not code:
            return False
        self._on_event(InputEvent(self._profile.device_key, code, pressed, code_label(code)))
        return True

    def _board(self):
        return self.gamepad if self._kind == DeviceKind.GAMEPAD else self.keyboard

    def _refresh_maps(self) -> None:
        if not self._profile:
            return
        maps = {}
        for rule in self._profile.rules:
            maps[rule.from_code] = code_label(rule.to_codes[0]) if rule.to_codes else "禁用"
        self._board().set_mappings(maps)

    def _on_bind_source(self, code: str) -> None:
        if not self._profile:
            return
        if self._armed_src == code:
            self._armed_src = None
            self._board().set_armed(None)
            self._hint.setText("已取消改建。再点键帽选择要改的源键。")
            self._hint.setStyleSheet("")
            return
        self._armed_src = code
        self._board().set_armed(code)
        self.ctl.inputmap.set_test_target(self._profile.device_key)
        if self._kind != DeviceKind.GAMEPAD:
            self._set_grab(True)
        self._hint.setText(
            f"改建中：已选「{code_label(code)}」→ 请按目标键；再点该键或按它本身可取消 / 禁用"
        )
        self._hint.setStyleSheet("color: #E8A017; font-weight: 600;")

    def _on_event(self, event: InputEvent) -> None:
        if not self._profile or event.device_key != self._profile.device_key:
            return
        # Ignore absolute-axis spam for remap UI buttons.
        if event.code.startswith("ABS_"):
            return
        if self._kind == DeviceKind.GAMEPAD:
            self.gamepad.set_button(event.code, event.pressed)
        else:
            self.keyboard.set_key_state(event.code, event.pressed)
        if not event.pressed or not self._armed_src:
            return
        src = self._armed_src
        dst = event.code
        to_codes = [] if dst == src else [dst]
        rules = [r for r in self._profile.rules if r.from_code != src]
        rules.append(RemapRule(from_code=src, to_codes=to_codes))
        self._profile.rules = rules
        self.ctl.inputmap.store.profiles[self._profile.device_key] = self._profile
        self.ctl.inputmap.save()
        self._armed_src = None
        self._board().set_armed(None)
        self._refresh_maps()
        self._hint.setStyleSheet("")
        if to_codes:
            msg = f"已改键：{code_label(src)} → {code_label(to_codes[0])}"
            if not self._profile.enabled:
                msg += "（请打开上方「启用映射」后才会在系统中生效）"
            self._hint.setText(msg)
            self.ctl.flyout.toast(msg, "success", 3500)
        else:
            self._hint.setText(f"已禁用：{code_label(src)}")
            self.ctl.flyout.toast(f"已禁用 {code_label(src)}", "info", 2500)

    def _toggle_enable(self, on: bool) -> None:
        if not self._profile:
            return
        if on and not self.ctl.settings.input_remap_enabled:
            self.ctl.settings.input_remap_enabled = True
            self.ctl.inputmap.set_master(True)
            self.ctl.settings.save()
            self.ctl.flyout.settings_page.sync_input_controls()
        self._profile.enabled = on
        self.ctl.inputmap.store.profiles[self._profile.device_key] = self._profile
        self.ctl.inputmap.save()
        cap = self.ctl.inputmap.refresh_capability()
        if on:
            if not cap.get("remap"):
                msg = cap.get("message", "系统改键不可用")
                self.status.setText(msg)
                self.ctl.flyout.toast("面板映射已保存，但系统改键未生效：缺少 /dev/uinput 权限", "warning", 8000)
            else:
                # Give the backend a moment to grab + create uinput.
                QTimer.singleShot(600, self._show_remap_status)
        else:
            self.status.setText(cap.get("message", ""))

    def _show_remap_status(self) -> None:
        text = self.ctl.inputmap.remap_runtime_status()
        self.status.setText(text)
        if "生效中" in text:
            self.ctl.flyout.toast(text, "success", 4000)
        else:
            self.ctl.flyout.toast(text, "warning", 7000)

    def _toggle_keepalive(self, on: bool) -> None:
        if not self._profile:
            return
        self._profile.joycon_keepalive = on
        self.ctl.inputmap.store.profiles[self._profile.device_key] = self._profile
        if on and not self.ctl.settings.input_remap_enabled:
            self.ctl.settings.input_remap_enabled = True
            self.ctl.inputmap.set_master(True)
            self.ctl.settings.save()
            self.ctl.flyout.settings_page.sync_input_controls()
        self.ctl.inputmap.save()

    def _reload_presets(self) -> None:
        current = self.preset.currentData() if self.preset.count() else ""
        self.preset.blockSignals(True)
        self.preset.clear()
        self.preset.addItem("改建预设…", "")
        kind = self._kind.value if self._kind else ""
        for pid, (title, _) in PRESETS.items():
            if kind == "gamepad":
                continue  # built-ins are keyboard-oriented
            self.preset.addItem(title, pid)
        for sp in self.ctl.inputmap.store.presets.values():
            if sp.kind in ("any", kind, "") or not kind:
                self.preset.addItem(f"★ {sp.title}", f"user:{sp.id}")
        self.preset.blockSignals(False)
        if current:
            idx = self.preset.findData(current)
            if idx >= 0:
                self.preset.setCurrentIndex(idx)

    def _apply_preset(self) -> None:
        if not self._profile:
            return
        pid = self.preset.currentData()
        if not pid:
            return
        self.ctl.inputmap.apply_preset(self._profile, pid)
        self._profile = self.ctl.inputmap.store.profiles[self._profile.device_key]
        self._refresh_maps()
        self.ctl.flyout.toast("已应用改建预设", "success", 2500)

    def _save_preset(self) -> None:
        if not self._profile:
            return
        if not self._profile.rules:
            self.ctl.flyout.toast("当前没有可保存的映射", "warning", 2500)
            return
        default = f"{self._profile.name or '设备'} 方案"
        title, ok = QInputDialog.getText(self, "存为预设", "预设名称：", text=default)
        if not ok or not title.strip():
            return
        preset = self.ctl.inputmap.save_user_preset(self._profile, title.strip())
        self._reload_presets()
        idx = self.preset.findData(f"user:{preset.id}")
        if idx >= 0:
            self.preset.setCurrentIndex(idx)
        self.ctl.flyout.toast(f"已保存预设「{preset.title}」", "success", 2500)

    def _clear_all(self) -> None:
        if not self._profile:
            return
        self._profile.rules = []
        self.ctl.inputmap.store.profiles[self._profile.device_key] = self._profile
        self.ctl.inputmap.save()
        self._refresh_maps()
        self._hint.setText("已清除全部映射")
