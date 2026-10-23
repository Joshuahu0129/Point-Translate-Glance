---
title: 版本日志
answers: 已完成的变更，未发版的记在「Unreleased」
not: 计划与进度（ROADMAP）、内部重构细节
sections: Unreleased → 版本号（日期）倒序；每节分新增 / 变更 / 修复
update: 改动完成时记入「Unreleased」；发版时改为版本号和日期
store: git
updated: 2026-10-23
---

# 更新日志 / Changelog

本文件面向开发者,记录每个版本的改动。遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)
与[语义化版本](https://semver.org/lang/zh-CN/)。

版本号在 `config.py` 的 `VERSION` 常量里,发布时改这里 + 打 tag `vX.Y.Z`。

## [Unreleased]

## [1.2.1] - 2026-10-23

### 变更
- **中译英保留原来的行结构,且不加标点**:选区是多行时,逐行翻译,原文原样保留,英文按
  行对应排在原文下面(空行也保留);单行选区仍是"原文 + 空格 + 英文"。某一行中文末尾没有
  标点,对应的英文末尾也不会被加上 `.` / `?` 等。最多 30 行。此前多行会被并成一句、
  接在最后一行后面,还会自动补标点。

## [1.2.0] - 2026-10-23

### 新增
- **中文选区一键译成英文并贴回**:选中一段中文(汉字超过一半),按热键(默认 F2)
  不再弹卡片,而是译成英文,**松开热键后**以"原文 + 空格 + 英文"替换选区(模拟
  Ctrl+V,贴完恢复原剪贴板)。选区上限 400 字;翻译失败会弹 ⚠ 提示。网页 / PDF 等
  只读区域贴不进去,什么都不会发生。`config.json` 的 `zh_to_en` 可关闭(依赖
  `use_selection`)。
- **双击卡片复制**:双击标题里的单词复制该词,双击英文例句 / 中文译文复制整句;
  卡片音标位置会闪一下"已复制 ✓"。需要按住 F2 或先点 📌 钉住才能把鼠标移到卡片上。
  "翻译中…"占位和错误提示不会被复制。

### 变更
- **exe / 快捷方式图标换成托盘里的蓝底白 G**(此前是 PyInstaller 默认的软盘图标)。
  图标由 `appicon.py` 绘制,托盘与 `glance.ico` 共用;改图标后跑 `make_icon.py` 重新生成,
  `build.bat` 打包时用 `--icon glance.ico` 嵌入。

### 修复
- `make_dict.py`:补回缺失的自动下载逻辑。README / `requirements-dev.txt` 一直
  说找不到本地 CSV 时会自动下载 ECDICT,但代码里从没实现,只能手动准备 CSV。
  现在真的会下载 `stardict.7z` 并用 `py7zr` 解压。国内网络到
  `raw.githubusercontent.com` 常限速,实测约 40 分钟,脚本里已提示别以为卡死。
- `NOTICE`:补上遗漏的 `requests` 依赖许可证(Apache-2.0)。

### 已知限制
- 中译英靠模拟 Ctrl+V 写入,网页 / PDF 等只读区域贴不进去,不会有任何反应;选区内的
  加粗、链接、图片会被纯文本覆盖。
- 取词探测与中译英写入只保存 / 恢复剪贴板里的文字,剪贴板里是图片或文件时会被清空。

## [1.1.0] - 2026-09-08

### 变更
- **默认热键 Ctrl → F2**。Ctrl 与复制 / Ctrl+单击冲突;换成基本不被占用的 F2。
  升级时旧配置里的 `hotkey: "ctrl"` 会自动改成 `"f2"`;想用别的键到 `config.json`
  改(`f2` / `ctrl` / `alt` / `shift`)。
- **例句英文原句改用粗体**,与已加粗的中文译文一致;高亮词仍靠蓝色区分。
- **单词标题与主释义之间的行距压到最小**。
- **喇叭 / 图钉图标重画**为几何线条风格(32px 方形按钮、20px 图标);「已钉住」
  为填充图钉 + 蓝底。大小可用 `config.json` 的 `icon_scale` 调。

### 新增
- **卡片自适应大小**:长选区 / 长例句不再截断到 6 行 —— 卡片会先在
  `card_width` ~ `card_width_max` 之间加宽(换行更好读),再向下增高,最多
  `sentence_max_lines`(默认 16)行;贴近屏幕底部时整体上移。
- **指针悬停在卡片上时不再重新查词**,方便把鼠标移上去点 🔊 / 📌,内容不闪。
- 划词剪贴板探测对所有 `hotkey` 都启用(此前仅 `ctrl`);非 Ctrl 时合成一次干净的
  Ctrl+C 读取选区。

### 修复
- 读取 `config.json` 时容忍 BOM(记事本"另存为"会加),此前带 BOM 会导致整个
  配置被忽略、静默回退默认值。

### 已知限制
- F2 在文件管理器 / 表格类控件里是「重命名」;按住 F2 划到这类控件上可能触发重命名。
  换 `hotkey` 或松开即可。
- `hotkey` 为 `shift` 时,划词探测发送的是 Ctrl+Shift+C(物理 Shift 仍按着);少数
  应用绑了该组合。用 `use_selection: false` 关闭探测。

## [1.0.4] - 2026-09-02

翻译从 1–5 秒降到零点几秒。

### 性能
- **换翻译接口**:旧的 `translate_a/single` 已被 Google 限流(HTTP 429),换成
  `clients5.google.com` 的 `dict-chrome-ex` 接口(Google 词典扩展用的那个),
  限流宽松得多。
- **连接复用**:所有请求走同一个 keep-alive 会话,省掉每次的 TLS 握手
  (~100–200ms);自动使用系统 / 环境变量里的代理。
- **启动预热**:开程序时后台先建好连接,第一次查词不再等握手。
- **卡片分两段渲染**:单词 + 音标 + 词性从离线词典**立刻**显示(~50ms),
  整句翻译好了再补进来(其间显示"翻译中…")。
- 去抖 130ms → 70ms(旧配置自动升级)。

实测:单词 ~85ms,整句 ~165ms(热连接);之前是 700–5700ms。

### 依赖
- 新增 `requests`(exe 体积 +1.5MB)。

### 新增
- **已选中文字优先**:取词时如果已经框选了一段文字,翻译的"句子"就用选区,
  不再用 OCR 拼句。背后用一次快速 Ctrl+C 读取选区(与截图/OCR 并行,不加延迟)。
  可在 `config.json` 用 `use_selection` 关闭。

### 变更
- 钉子 / 喇叭图标加重(字号变大、按钮尺寸不变);图标底色、词性标签、释义
  胶囊统一改成小圆角。
- "查询中"文字换成三个跳动的小圆点动画。

### 修复
- **取词只取到半句**:截取区域加大到 1400×120,并新增跨行拼句逻辑
  (`assemble_sentence`)——把换行折行的同一句话拼完整,遇到句号 / 菜单栏 /
  相邻段落自动停下。老配置会在启动时自动升级截取尺寸。
- **音标丢失**:`safeguards` / `studies` 这类变形词 ECDICT 里没有音标 ——
  现在会自动回退到原形(`safeguard` / `study`)借用音标。
- 卡片会随标题(单词 + 长音标)需要自动变宽。

### 变更
- 去掉"常用释义"字样,省一行高度。
- 例句中文翻译改用粗体,不再显得太淡。
- 词性标签(n. / adj.)在释义换行时顶端对齐第一行,不再垂直居中。
- **钉住后内容冻结**:钉住时不再随鼠标刷新翻译,内容保持不动;钉住后可拖动窗口。

## [1.0.1] - 2026-09-02

### 变更
- 卡片去掉关闭按钮(✕):松开热键即消失,钉住状态点 📌 取消。
- 🔊 朗读按钮移到右上角、与 📌 并排;两个图标加大、加底色,视觉更有分量。
- 中文字体较英文缩小 1pt(CJK 字形本就偏大),标题释义加粗以增加重量感;
  例句英文用 Segoe UI、中文用微软雅黑,分别控制字号。
- 托盘默认深色主题(1.0.0 起)。

### 修复
- `docs/preview.png` 之前被 `.gitignore` 误排除,导致 README 预览图裂开。

## [1.0.0] - 2026-09-02

首个版本。

### 新增
- 全局屏幕取词:按住 Ctrl,鼠标指向任意窗口(浏览器 / PDF / 图片 / 程序 /
  视频字幕)里的英文单词即可翻译,基于 Windows 内置 OCR(`Windows.Media.Ocr`)。
- 内置离线英汉词典 `glance-dict.db`(ECDICT 常用词子集,约 24 万条):音标 +
  按词性(n. / v. / adj. …)分组的释义。
- 整句翻译:在线免费接口 `google` → `mymemory` 依次回退。
- Apple 风格圆角卡片弹窗,支持浅色 / 深色主题(默认深色)。
- 例句中的目标词在原文与译文里同色高亮(译文侧为尽力匹配)。
- 📌 钉住:卡片常驻、可拖动,不必一直按住热键。
- 🔊 朗读单词(Windows 语音合成)。
- 托盘菜单:切换翻译来源(本地词典 / Google)、切换主题、朗读开关、开机自启、
  打开配置、重新加载配置、版本信息。
- `config.json` 配置:热键、目标语言、引擎顺序、主题、卡片宽度、圆角、字号、
  不透明度、去抖、停留时长等。

### 已知限制
- 译文侧高亮是启发式匹配,机器翻译换用同义词时会匹配不到(英文侧不受影响)。
- 圆角用 Win32 窗口区域实现,Windows 10 上无原生投影阴影。
- 依赖 Windows 英文 OCR 语言包(首次运行会提示安装)。

[Unreleased]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.0.4...v1.1.0
[1.0.4]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.0.3...v1.0.4
[1.0.3]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Joshuahu0129/Point-Translate-Glance/releases/tag/v1.0.0
