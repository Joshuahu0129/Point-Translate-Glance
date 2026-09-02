# Glance for macOS — 移植计划

> 状态:**未开始**。Joshua 说要做时再动手。这里先记录方案,方便到时直接开工。

## 现状

跨平台的代码(不用改):

- `dictionary.py` — 纯 SQLite,直接可用
- `translate.py` — 纯 urllib,直接可用
- `config.py` — 只有 `_base_dir()` 里 `sys.executable` 的路径习惯要看一下
- `make_dict.py` — 构建脚本,开发机跑,与运行平台无关

需要 macOS 实现的模块(目前是 Windows 专属):

| 模块 | Windows 现状 | macOS 方案 |
|---|---|---|
| `ocr.py` | `winrt` / `Windows.Media.Ocr` | **Vision.framework**(`VNRecognizeTextRequest`),经 `pyobjc-framework-Vision`;或 `ocrmac` 封装。系统自带,离线,质量好。 |
| `tts.py` | PowerShell + `System.Speech` | `subprocess`(`/usr/bin/say`);或 `AVSpeechSynthesizer`。 |
| `autostart.py` | 注册表 `HKCU\...\Run` | `~/Library/LaunchAgents/com.joshuahu.glance.plist`(`launchctl load`),或用 `SMAppService`(macOS 13+)。 |
| `popup.py` 圆角 | `SetWindowRgn` + `CreateRoundRectRgn` | Tkinter 在 mac 上 overrideredirect 窗口没有窗口区域 API。改用 `-transparent` 属性 + Canvas 画圆角矩形,或换 **PyObjC + NSPanel**(`NSWindowStyleMaskBorderless`,`cornerRadius`,可加原生阴影/毛玻璃)。 |
| `popup.py` 图标字体 | `Segoe MDL2 Assets` | 换 SF Symbols 文本(`􀎬` 等)或内嵌 SVG/PNG 小图标;字体族回退到 `-apple-system` / `PingFang SC`。 |
| `main.py` 屏幕坐标 | `user32.GetSystemMetrics(76..79)` 取虚拟桌面 | `AppKit.NSScreen.screens` 求并集;`Quartz`/`pynput` 取鼠标位置。DPI:mac 用点坐标,截图 `mss` 会给 Retina 物理像素,注意 backing scale。 |
| 截图 | `mss`(可用) | `mss` 在 mac 可用,但要处理 Retina 缩放;或 `Quartz.CGWindowListCreateImage`。需要「屏幕录制」权限。 |
| 全局热键 / 监听 | `pynput`(可用) | `pynput` 在 mac 需要「辅助功能」+「输入监控」权限;首次运行要引导用户去系统设置授权。 |
| 打包 | PyInstaller → `.exe` | PyInstaller / py2app → `.app`,再 `codesign` + `notarize`(否则 Gatekeeper 拦)。 |

## 建议的重构(动手前先做,Windows 版也受益)

1. 抽一个 `platform/` 包:`platform/win.py`、`platform/mac.py`,导出统一接口
   `ocr_image(png) -> lines`、`speak(word)`、`set_autostart(bool)`、
   `screen_bounds()`、`make_popup_window()`。`main.py` 按 `sys.platform` 选。
2. `popup.py` 拆成「布局/内容」(跨平台)和「窗口外壳」(平台相关)。
3. 图标改用内嵌资源,不依赖系统符号字体。

## 权限清单(mac 首次运行要引导)

- 辅助功能(Accessibility)— 全局键盘监听
- 输入监控(Input Monitoring)— 同上
- 屏幕录制(Screen Recording)— 截图取词

## 参考

- Vision OCR: https://developer.apple.com/documentation/vision/vnrecognizetextrequest
- `ocrmac`: https://github.com/straussmaximilian/ocrmac
- LaunchAgents: https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/
