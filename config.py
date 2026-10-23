"""Configuration loading / saving for Glance.

``config.json`` is created next to the executable (or this script) on first run.
Edit it and use the tray menu "重新加载配置" to apply most changes.
"""

import json
import os
import sys

APP_NAME = "Glance"
VERSION = "1.2.1"
AUTHOR = "Joshua Hu"
AUTHOR_TIP = "Made by Joshua Hu"
VERSION_LINE = "Version %s · by %s" % (VERSION, AUTHOR)

DEFAULT = {
    # Key you hold while pointing at a word: "f2" | "ctrl" | "alt" | "shift"
    "hotkey": "f2",
    # Target language for online translation (Google language code).
    "target_language": "zh-CN",
    # OCR language / BCP-47 tag. The matching Windows language pack with the
    # "Optical character recognition" feature must be installed.
    "ocr_language": "en-US",
    # Order in which online translation engines are tried (sentence + fallback).
    #   available: "google", "mymemory"
    # In mainland China "google" is usually unreachable -> put "mymemory" first.
    "engine_order": ["google", "mymemory"],
    # Where a word's meaning comes from:
    #   "local"  - offline ECDICT dictionary (phonetics + meanings by part of
    #              speech); falls back to online only when the word is missing.
    #   "google" - the online translator gives the headline meaning; the offline
    #              dictionary still supplies phonetics and the POS chips.
    # Full sentences always use the online translator either way.
    "translate_source": "local",
    # Size (physical pixels) of the screen area grabbed around the cursor.
    # Wider / taller = full wrapped sentences, slightly slower OCR.
    "capture_width": 1400,
    "capture_height": 120,
    # UI theme: "light" | "dark"
    "theme": "dark",
    # Popup card content width, px. The card starts at card_width and widens
    # toward card_width_max when a long sentence would otherwise wrap a lot.
    "card_width": 400,
    "card_width_max": 560,
    # A translated sentence stops growing the card after this many lines
    # (it then just gets clipped with a scrollbarless overflow - rare).
    "sentence_max_lines": 16,
    # Base font size of the popup.
    "font_size": 12,
    # Popup opacity, 0.85 - 1.0 (1.0 = fully opaque).
    "opacity": 1.0,
    # Corner radius of the popup card, px.
    "corner_radius": 16,
    # Speaker / pin icon-button size, as a fraction of the 1.0 baseline
    # (baseline ~= one line of the primary-meaning text).
    "icon_scale": 1.0,
    # How long the mouse must be still (ms) before a lookup fires.
    "debounce_ms": 70,
    # Keep the card on screen this many ms after the hotkey is released
    # (0 = vanish immediately). Pin (📌) always keeps it regardless.
    "linger_ms": 500,
    # Also speak the word automatically when the popup shows.
    "auto_speak": False,
    # If text is already selected when you trigger a lookup, translate the
    # selection as the sentence. Uses a quick Ctrl+C behind the scenes; turn
    # off if it interferes with an app that copies on empty selection.
    "use_selection": True,
    # Chinese text selected (more than half Han characters) + hotkey ->
    # translate it to English and paste it right after the selection instead
    # of showing a card. Needs use_selection (it reads the selection the same
    # way); set false to turn it off.
    "zh_to_en": True,
}


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def config_path():
    return os.path.join(_base_dir(), "config.json")


def load():
    cfg = dict(DEFAULT)
    p = config_path()
    if os.path.exists(p):
        try:
            # utf-8-sig: tolerate a BOM (Notepad adds one when you "save as")
            with open(p, "r", encoding="utf-8-sig") as f:
                user = json.load(f)
            if isinstance(user, dict):
                cfg.update(user)
        except Exception as e:  # noqa: BLE001 - keep running with defaults
            print("config.json 读取失败, 使用默认配置:", e)
        if _migrate(cfg):
            save(cfg)
    else:
        save(cfg)
    return cfg


def _migrate(cfg):
    """Bring an older config.json forward. Returns True if it changed."""
    changed = False
    # 1.0.2: capture area widened for full wrapped sentences
    if int(cfg.get("capture_width", 0)) < 1200:
        cfg["capture_width"] = DEFAULT["capture_width"]
        changed = True
    if int(cfg.get("capture_height", 0)) < 100:
        cfg["capture_height"] = DEFAULT["capture_height"]
        changed = True
    # 1.0.4: faster translation - shorter debounce is fine now
    if int(cfg.get("debounce_ms", 0)) >= 120:
        cfg["debounce_ms"] = DEFAULT["debounce_ms"]
        changed = True
    # 1.1.0: default hotkey moved to F2. Ctrl collided with copy / Ctrl+click;
    # Shift (tried mid-development) collided too. Rewrite the earlier defaults.
    if str(cfg.get("hotkey", "")).lower() in ("ctrl", "shift"):
        cfg["hotkey"] = "f2"
        changed = True
    return changed


def save(cfg):
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        print("无法写入 config.json:", e)
