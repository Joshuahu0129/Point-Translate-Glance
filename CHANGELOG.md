# 更新日志 / Changelog

本文件面向开发者,记录每个版本的改动。遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)
与[语义化版本](https://semver.org/lang/zh-CN/)。

版本号在 `config.py` 的 `VERSION` 常量里,发布时改这里 + 打 tag `vX.Y.Z`。

## [Unreleased]

## [1.0.2] - 2026-09-02

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

[Unreleased]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.0.2...HEAD
[1.0.2]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/Joshuahu0129/Point-Translate-Glance/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Joshuahu0129/Point-Translate-Glance/releases/tag/v1.0.0
