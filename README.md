# Better Bluetooth

Linux / Windows 双平台蓝牙设备管理工具。Fluent 风格弹出面板，每台已连接设备在任务栏（托盘）单独显示电量。

## 功能

- 已连接 / 已配对设备列表，电量条与低电量标记
- 每台设备一个托盘图标，8 种样式（数字、徽章、横向电池、竖向电池、分段、圆环图标、饼图、图标电量条），可按电量着色，可在面板中逐台开关
- 2.4G / USB 无线外设电量（见下方平台说明）
- 面板可拖动（拖动顶部区域），位置会被记住，可在设置中恢复默认
- 连接、断开、搜索并配对新设备、删除设备、重命名
- 电量历史曲线（24 小时 / 7 天 / 30 天）与续航估算
- 低电量通知、连接状态通知、开机自启、浅色 / 深色 / 跟随系统主题
- **按键测试 / 按设备映射**（键盘、手柄，含 Joy-Con）：系统全局生效，默认关闭

## 运行

```bash
uv venv && uv pip install -e .        # 或 pip install -e .
python -m betterbluetooth             # --mock 使用模拟数据，--minimized 启动时不弹出面板
```

## 下载即用（无需安装 Python）

从 [Releases](https://github.com/Fiend-D/betterbluetooth/releases/latest) 下载：

| 文件 | 说明 |
| --- | --- |
| `BetterBluetooth-<版本>-windows-x64.exe` | Windows 10 1809+ / 11 单文件，双击运行 |
| `BetterBluetooth-<版本>-windows-x64-portable.zip` | Windows 便携版，解压后运行 `BetterBluetooth.exe`（启动更快） |
| `BetterBluetooth-<版本>-linux-x86_64.AppImage` | Linux 单文件：`chmod +x` 后直接运行 |
| `BetterBluetooth-<版本>-linux-x86_64.tar.gz` | Linux 目录版，解压后运行 `./install.sh` 安装到当前用户（含菜单图标） |

Linux 包基于 glibc 2.31 构建，支持 Ubuntu 20.04+ / Debian 11+ / Fedora 32+ 等发行版。

## 打包

产物输出到 `release/`：

```bash
docker build -t betterbluetooth-build packaging/linux
docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -e QT_QPA_PLATFORM=offscreen \
    -v "$PWD":/src betterbluetooth-build bash packaging/linux/package.sh

packaging/windows/package-wine.sh          # 在 Linux 上通过 Wine 构建 Windows 包
# 或在 Windows 上：powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
```

## 平台说明

### Linux（BlueZ）

- 通过系统 D-Bus 与 BlueZ 通信，读取 `org.bluez.Battery1` 电量。
- 低功耗设备（鼠标、键盘等）的电量默认可读；**多数耳机**的电量由 PipeWire 通过 BlueZ 的实验接口上报，需要开启实验特性：

  ```ini
  # /etc/bluetooth/main.conf
  [General]
  Experimental = true
  ```

  然后执行 `sudo systemctl restart bluetooth`。
- 2.4G 外设电量来自 UPower：罗技 Unifying / Bolt / Lightspeed、PS / Xbox / Switch 手柄等由内核驱动支持的设备都可显示（`upower -d` 能看到的即可显示）。使用厂商私有协议的接收器（无内核驱动）无法读取。
- GNOME 需要启用 AppIndicator 扩展才能显示托盘图标（Ubuntu 默认已启用）。
- Wayland 会话下程序默认通过 XWayland 运行，以便把面板放到托盘附近；可设置 `QT_QPA_PLATFORM=wayland` 覆盖。

### Windows（10 1809+ / 11）

- 经典蓝牙设备电量读取系统设备属性 `DEVPKEY_Bluetooth_Battery`（与系统设置中显示的电量一致）；低功耗设备额外读取 GATT 电池服务。
- 支持开关蓝牙、搜索配对、删除设备。
- 2.4G 外设：通过 HID++ 协议直接读取罗技 Unifying / Bolt / Lightspeed 接收器下设备的电量。其他品牌私有协议的接收器暂不支持。
- Windows 没有公开的“连接 / 断开已配对经典蓝牙设备”接口，因此该平台不提供连接 / 断开按钮。
- 重命名仅在本程序内生效。

## 按键测试与系统级映射

在设备卡片菜单中打开「按键测试 / 映射」（键盘 / 手柄）。设置页有总开关「系统级按键映射」。

| 能力 | Linux | Windows |
| --- | --- | --- |
| 按键测试 | 读取系统输入设备（依赖已打进安装包） | Raw Input（已打包） |
| 键盘映射 | 独占原设备后发出映射键（真全局） | 低级键盘钩子（多数应用生效） |
| Joy-Con | 可选保活（全速报告）+ 按钮映射到键盘 | 同左 |

安装包已包含全部运行依赖，**不需要**再 `pip install`。  

**权限（Linux）：** 需要能读写 `/dev/input/event*`。把用户加入 `input` 组后重新登录：

```bash
sudo usermod -aG input "$USER"
```

**注意：**

- 映射默认关闭，需在设置中打开总开关，并在设备页对该设备启用。
- 与 PowerToys Keyboard Manager、keyd、SharpKeys、Steam Input 等同时启用可能冲突，建议只开一套。
- Windows 用户态钩子无法覆盖所有独占 Raw Input 的游戏 / 反作弊场景；这些环境需要后续的驱动级方案。
- Joy-Con 保活会占用 HID，可能与 Steam / BetterJoy 抢设备，请勿同时开启。

配置文件：`input_profiles.json`（与 `settings.json` 同目录）。

## 数据位置

| 平台 | 设置 | 电量历史 | 输入映射 |
| --- | --- | --- | --- |
| Linux | `~/.config/betterbluetooth/settings.json` | `~/.local/share/betterbluetooth/history.db` | `~/.config/betterbluetooth/input_profiles.json` |
| Windows | `%APPDATA%\BetterBluetooth\settings.json` | `%LOCALAPPDATA%\BetterBluetooth\history.db` | `%APPDATA%\BetterBluetooth\input_profiles.json` |

## 许可证

[MIT](LICENSE)
