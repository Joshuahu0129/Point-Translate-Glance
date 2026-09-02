"""Glance - hover an English word, see the translation.

Hold the configured modifier (default Ctrl) and point at a word: an
Apple-flavoured card shows its phonetics, part-of-speech meanings and, for a
full line, the sentence translation with the word highlighted on both sides.
Click the pin to keep the card without holding the key.

Pipeline:  hotkey held -> grab a strip of screen around the cursor ->
Windows OCR -> pick the word under the cursor -> offline dictionary (ECDICT)
+ online sentence translation -> popup card near the cursor.
"""

import ctypes
import os
import queue
import re
import string
import sys
import threading
import time
import tkinter as tk

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    import mss
    import mss.tools
    from pynput import keyboard, mouse
except Exception as e:  # noqa: BLE001
    print("缺少依赖, 请先运行:  pip install -r requirements.txt")
    print(e)
    sys.exit(1)

import autostart
import config as cfg_mod
import dictionary
import tts
from config import APP_NAME
from ocr import ocr_available, ocr_png_bytes
from popup import Popup
from translate import TranslateError, translate

CFG = cfg_mod.load()

HOTKEY_MAP = {
    "ctrl": {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl},
    "alt": {keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt,
            getattr(keyboard.Key, "alt_gr", keyboard.Key.alt_r)},
    "shift": {keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift},
}


def hotkey_keys():
    return HOTKEY_MAP.get(str(CFG.get("hotkey", "ctrl")).lower(), HOTKEY_MAP["ctrl"])


job_q = queue.Queue()
result_q = queue.Queue()
_lock = threading.Lock()
_state = {"held": False, "gen": 0, "last_move": 0.0, "released_at": 0.0}

mouse_ctl = mouse.Controller()
_PUNCT = "".join(set(string.punctuation) | {"“", "”", "‘", "’", "—", "…", "·", "，", "。"})


# --- input --------------------------------------------------------------
def request_translation():
    try:
        x, y = mouse_ctl.position
    except Exception:
        return
    with _lock:
        _state["gen"] += 1
        gen = _state["gen"]
        held = _state["held"]
    if not held:
        return
    result_q.put(("loading", gen, (x, y), None))
    job_q.put((gen, x, y))


def on_press(key):
    if key in hotkey_keys():
        with _lock:
            if _state["held"]:
                return
            _state["held"] = True
        request_translation()


def on_release(key):
    if key in hotkey_keys():
        with _lock:
            _state["held"] = False
            _state["released_at"] = time.time()
        if int(CFG.get("linger_ms", 500)) <= 0:
            result_q.put(("hide", None, None, None))


def on_move(x, y):
    with _lock:
        if _state["held"]:
            _state["last_move"] = time.time()


def debounce_loop():
    handled = 0.0
    while True:
        time.sleep(0.03)
        with _lock:
            held, lm = _state["held"], _state["last_move"]
        if held and lm > handled and (time.time() - lm) * 1000 >= CFG["debounce_ms"]:
            handled = lm
            request_translation()


# --- OCR word picking -------------------------------------------------
def clean_word(w):
    return w.strip(_PUNCT + " \t\r\n")


def pick_word(lines, cx, cy):
    best, best_line, best_d = None, None, float("inf")
    for ln in lines:
        for wd in ln["words"]:
            x0, y0 = wd["x"], wd["y"]
            x1, y1 = x0 + wd["w"], y0 + wd["h"]
            inside = x0 <= cx <= x1 and y0 <= cy <= y1
            cxx, cyy = x0 + wd["w"] / 2, y0 + wd["h"] / 2
            d = -1.0 if inside else (cxx - cx) ** 2 + (cyy - cy) ** 2
            if d < best_d:
                best, best_line, best_d = wd, ln, d
    if best is None:
        return None, None
    if best_d > 0 and best_d > (max(best["h"], 24) * 2.5) ** 2:
        return None, None
    return clean_word(best["text"]), (best_line["text"] if best_line else None)


# --- CN alignment heuristic -----------------------------------------
def spans_in(text, needle):
    if not text or not needle:
        return []
    low = text.lower()
    n = needle.lower()
    out, i = [], low.find(n)
    while i >= 0:
        out.append((i, i + len(needle)))
        i = low.find(n, i + len(needle))
    return out[:1]


def align_cn(sentence_cn, candidates):
    """Best-effort: highlight the Chinese run that matches the word's meaning.
    Machine translation often picks a context synonym, so this can miss."""
    if not sentence_cn:
        return []
    forms = set()
    for c in candidates:
        c = re.sub(r"[（(].*?[)）]", "", (c or "")).strip()
        for f in (c, c.rstrip("的地得"), c.lstrip("使被"), c.rstrip("地")):
            if 2 <= len(f) <= 10:
                forms.add(f)
    # exact substring, longest first
    for f in sorted(forms, key=len, reverse=True):
        idx = sentence_cn.find(f)
        if idx >= 0:
            return [(idx, idx + len(f))]
    # partial: any >=2-char slice of a candidate present in the sentence
    best = ""
    for f in forms:
        for i in range(len(f)):
            for j in range(i + 2, len(f) + 1):
                sub = f[i:j]
                if len(sub) > len(best) and sub in sentence_cn:
                    best = sub
    if best:
        idx = sentence_cn.find(best)
        return [(idx, idx + len(best))]
    return []


# --- worker ------------------------------------------------------------
def worker_loop():
    sct = (getattr(mss, "MSS", None) or mss.mss)()
    while True:
        gen, x, y = job_q.get()
        with _lock:
            if gen != _state["gen"] or not _state["held"]:
                continue
        try:
            data = do_lookup(sct, x, y)
        except Exception as e:  # noqa: BLE001
            result_q.put(("error", gen, (x, y), str(e)))
            continue
        result_q.put(("show" if data else "none", gen, (x, y), data))


def _vscreen():
    u = ctypes.windll.user32
    return (u.GetSystemMetrics(76), u.GetSystemMetrics(77),
            u.GetSystemMetrics(78), u.GetSystemMetrics(79))


def do_lookup(sct, x, y):
    w, h = int(CFG["capture_width"]), int(CFG["capture_height"])
    vx, vy, vw, vh = _vscreen()
    left = max(vx, min(x - w // 2, vx + vw - w))
    top = max(vy, min(y - h // 2, vy + vh - h))
    shot = sct.grab({"left": left, "top": top, "width": w, "height": h})
    png = mss.tools.to_png(shot.rgb, shot.size)
    lines = ocr_png_bytes(png, CFG.get("ocr_language", "en-US"))
    word, sentence = pick_word(lines, x - left, y - top)
    if not word or not re.search(r"[A-Za-z]", word):
        return None

    order = tuple(CFG.get("engine_order", ["google", "mymemory"]))
    tl = CFG.get("target_language", "zh-CN")
    source = str(CFG.get("translate_source", "local")).lower()

    entry = dictionary.lookup(word)
    data = {"word": word, "phonetic": "", "primary": "", "pos_groups": [],
            "sentence_en": None, "sentence_cn": None, "spans_en": [], "spans_cn": []}

    def online_word():
        try:
            return re.sub(r"\s+", " ", translate(word, tl, order)[0]).strip()
        except TranslateError:
            return ""

    cn_candidates = []
    if entry:  # phonetics + POS chips always come from the offline dictionary
        data["phonetic"] = entry.phonetic
        data["pos_groups"] = entry.pos_groups
        cn_candidates = list(entry.meanings)

    if source == "google":
        wt = online_word()
        data["primary"] = wt or (entry.primary() if entry else "(在线翻译失败)")
        if wt:
            cn_candidates = re.split(r"[；;，,、\s]+", wt) + cn_candidates
    else:  # local
        if entry:
            data["primary"] = entry.primary()
        else:
            wt = online_word()
            data["primary"] = wt or "(词典未收录, 在线翻译失败)"
            cn_candidates = re.split(r"[；;，,、\s]+", wt)

    if sentence and len(sentence.split()) > 1 \
            and sentence.strip().lower() != word.strip().lower():
        data["sentence_en"] = sentence
        data["spans_en"] = spans_in(sentence, word)
        try:
            st, _ = translate(sentence, tl, order)
            data["sentence_cn"] = st
            if entry and source != "google":  # help the CN-side alignment
                cn_candidates = cn_candidates + re.split(r"[；;，,、\s]+",
                                                         online_word())
            data["spans_cn"] = align_cn(st, cn_candidates)
        except TranslateError:
            data["sentence_cn"] = None
    return data


# --- Tk poll loop -----------------------------------------------------
def _active(popup):
    with _lock:
        held, rel = _state["held"], _state["released_at"]
    linger = int(CFG.get("linger_ms", 500))
    return (held or popup.pinned
            or (linger > 0 and rel and (time.time() - rel) * 1000 < linger))


def poll(root, holder):
    popup = holder["popup"]
    try:
        while True:
            kind, gen, anchor, payload = result_q.get_nowait()
            with _lock:
                cur = _state["gen"]
            if kind == "hide" or not _active(popup):
                popup.hide()
                continue
            if gen != cur:
                continue
            if kind == "loading":
                popup.show_loading(anchor)
            elif kind == "show":
                popup.show(anchor, payload)
                if CFG.get("auto_speak") and payload and payload.get("word"):
                    tts.speak(payload["word"])
            elif kind == "none":
                popup.hide()
            elif kind == "error":
                popup.show_message(anchor, "⚠ " + str(payload)[:110])
    except queue.Empty:
        pass
    if not _active(popup):
        popup.hide()
    root.after(25, poll, root, holder)


# --- tray -----------------------------------------------------------
def _tray_icon(Image, ImageDraw):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, 60, 60], radius=16, fill=(10, 132, 255, 255))
    d.arc([15, 13, 49, 51], start=20, end=315, fill="white", width=6)
    d.line([46, 32, 46, 40], fill="white", width=6)   # stub at the opening
    d.line([36, 36, 47, 36], fill="white", width=6)   # inward bar of the G
    return img


def make_tray(root, holder):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        print("未安装 pystray/Pillow, 跳过托盘图标")
        return None

    icon_img = _tray_icon(Image, ImageDraw)

    def rebuild_popup():
        holder["popup"].win.destroy()
        holder["popup"] = Popup(root, CFG, on_speak=tts.speak)

    def toggle_theme(icon, item):
        CFG["theme"] = "light" if CFG.get("theme") == "dark" else "dark"
        cfg_mod.save(CFG)
        root.after(0, rebuild_popup)

    def toggle_source(icon, item):
        CFG["translate_source"] = ("google"
                                   if str(CFG.get("translate_source")) == "local"
                                   else "local")
        cfg_mod.save(CFG)

    def toggle_speak(icon, item):
        CFG["auto_speak"] = not CFG.get("auto_speak")
        cfg_mod.save(CFG)

    def toggle_autostart(icon, item):
        autostart.toggle()

    def open_cfg(icon, item):
        try:
            os.startfile(cfg_mod.config_path())
        except Exception as e:  # noqa: BLE001
            print(e)

    def reload_cfg(icon, item):
        global CFG
        CFG = cfg_mod.load()
        root.after(0, rebuild_popup)
        print("配置已重新加载")

    def do_quit(icon, item):
        icon.stop()
        root.after(0, root.destroy)

    M = pystray.MenuItem
    menu = pystray.Menu(
        M("按住 %s 划词 · 点 📌 钉住" % CFG.get("hotkey", "ctrl").capitalize(),
          None, enabled=False),
        pystray.Menu.SEPARATOR,
        M(lambda i: "切换为 Google 翻译"
          if str(CFG.get("translate_source")) == "local"
          else "切换为本地词典", toggle_source),
        M(lambda i: "切换为浅色界面" if CFG.get("theme") == "dark"
          else "切换为深色界面", toggle_theme),
        M("朗读单词", toggle_speak, checked=lambda i: CFG.get("auto_speak", False)),
        M("开机自启", toggle_autostart, checked=lambda i: autostart.is_enabled()),
        pystray.Menu.SEPARATOR,
        M("打开配置文件", open_cfg),
        M("重新加载配置", reload_cfg),
        M("退出 Glance", do_quit),
        pystray.Menu.SEPARATOR,
        M(cfg_mod.VERSION_LINE, None, enabled=False),
    )
    icon = pystray.Icon(APP_NAME, icon_img, "%s · 鼠标取词翻译" % APP_NAME, menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon


# --- main ----------------------------------------------------------
def main():
    root = tk.Tk()
    root.withdraw()
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(root.winfo_id())
        if dpi:
            root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass

    holder = {"popup": Popup(root, CFG, on_speak=tts.speak)}

    if not ocr_available(CFG.get("ocr_language", "en-US")):
        from tkinter import messagebox
        messagebox.showwarning(
            "缺少 OCR 语言包",
            "未检测到可用的 Windows OCR 引擎。\n\n"
            "请打开: 设置 → 时间和语言 → 语言和区域 → 添加/选择 English → "
            "语言选项 → 安装 “光学字符识别” 功能, 然后重启本程序。",
        )
    if not dictionary.available():
        print("提示: 未找到 glance-dict.db, 将只用在线翻译(无音标/词性)。")

    threading.Thread(target=worker_loop, daemon=True).start()
    threading.Thread(target=debounce_loop, daemon=True).start()

    kl = keyboard.Listener(on_press=on_press, on_release=on_release)
    ml = mouse.Listener(on_move=on_move)
    kl.daemon = ml.daemon = True
    kl.start()
    ml.start()

    make_tray(root, holder)
    print("%s 已启动。按住 %s 指向英文单词即可翻译。"
          % (APP_NAME, CFG.get("hotkey", "ctrl").capitalize()))

    root.after(25, poll, root, holder)
    try:
        root.mainloop()
    finally:
        kl.stop()
        ml.stop()


if __name__ == "__main__":
    main()
