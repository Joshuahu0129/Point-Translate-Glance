"""Glance - hover an English word, see the translation.

Hold the configured hotkey (default F2) and point at a word: an
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
from concurrent.futures import ThreadPoolExecutor

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

import appicon
import autostart
import config as cfg_mod
import dictionary
import tts
from config import APP_NAME
from ocr import ocr_available, ocr_png_bytes
from popup import Popup
import translate as _tr
from translate import TranslateError, translate

_kbd = keyboard.Controller()

# --- reading the current text selection (via a quick clipboard round-trip) ---
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_u32 = ctypes.windll.user32
_k32 = ctypes.windll.kernel32
_k32.GlobalLock.restype = ctypes.c_void_p
_k32.GlobalLock.argtypes = [ctypes.c_void_p]
_k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
_k32.GlobalAlloc.restype = ctypes.c_void_p
_k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
_u32.GetClipboardData.restype = ctypes.c_void_p
_u32.GetClipboardData.argtypes = [ctypes.c_uint]
_u32.SetClipboardData.restype = ctypes.c_void_p
_u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

_SENTINEL = "\x00glance-probe\x00"


def _open_clipboard():
    for _ in range(6):
        if _u32.OpenClipboard(0):
            return True
        time.sleep(0.01)
    return False


def _clip_get():
    if not _open_clipboard():
        return None
    try:
        h = _u32.GetClipboardData(_CF_UNICODETEXT)
        if not h:
            return None
        p = _k32.GlobalLock(h)
        try:
            return ctypes.c_wchar_p(p).value if p else None
        finally:
            _k32.GlobalUnlock(h)
    finally:
        _u32.CloseClipboard()


def _clip_set(text):
    """Replace the clipboard text. Returns False if the clipboard stayed busy."""
    if not _open_clipboard():
        return False
    try:
        _u32.EmptyClipboard()
        if text:
            buf = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(buf)
            h = _k32.GlobalAlloc(_GMEM_MOVEABLE, size)
            dst = _k32.GlobalLock(h)
            ctypes.memmove(dst, buf, size)
            _k32.GlobalUnlock(h)
            _u32.SetClipboardData(_CF_UNICODETEXT, h)
        return True
    finally:
        _u32.CloseClipboard()


def _selection_probe_begin():
    """Drop a sentinel on the clipboard and fire a copy; the copy lands while
    the screenshot + OCR run. Returns the saved clipboard text (or None).

    F2 / Alt aren't modifiers, so we synthesize a clean Ctrl+C. With hotkey
    "shift" the physical Shift is still down, so it's really Ctrl+Shift+C -
    harmless in normal text fields but a few apps bind it; config
    `use_selection` turns the whole probe off.
    """
    if not CFG.get("use_selection", True):
        return False
    hk = str(CFG.get("hotkey", "f2")).lower()
    try:
        saved = _clip_get()
        _clip_set(_SENTINEL)
        if hk == "ctrl":
            _kbd.press("c")
            _kbd.release("c")
        else:
            _kbd.press(keyboard.Key.ctrl)
            _kbd.press("c")
            _kbd.release("c")
            _kbd.release(keyboard.Key.ctrl)
        return saved if saved is not None else ""
    except Exception:  # noqa: BLE001
        return False


def _selection_probe_end(saved):
    """Restore the clipboard; return the raw selected text ('' if none)."""
    if saved is False:
        return ""
    try:
        time.sleep(0.02)
        cur = _clip_get()
        _clip_set(saved or "")
        if cur and cur != _SENTINEL and cur.strip():
            return cur
    except Exception:  # noqa: BLE001
        pass
    return ""


def _english_selection(raw):
    """The selection as a one-line English sentence, or '' if it isn't one."""
    t = re.sub(r"\s+", " ", raw or "").strip()
    if 2 <= len(t) <= 400 and re.search(r"[A-Za-z]", t):
        return t
    return ""


# --- Chinese selection -> English pasted after it ---------------------------
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")  # Han + ext A + compat
ZH_RATIO = 0.5       # strictly more than this share of non-space chars = Chinese
ZH_MAX = 400


def han_ratio(text):
    chars = re.sub(r"\s+", "", text or "")
    if not chars:
        return 0.0
    return len(_HAN.findall(chars)) / len(chars)


ZH_MAX_LINES = 30
_LINE_SPLIT = re.compile(r"\r\n|\r|\n")
_END_MARKS = "。．.！!？?…；;，,、：:"
_TRAIL_PUNCT = re.compile(r"[.!?;:,…。！？，]+$")


def _newline_of(text):
    for nl in ("\r\n", "\n", "\r"):
        if nl in text:
            return nl
    return "\n"


def mirror_end(src, en):
    """Don't add end punctuation the source line doesn't have (translation
    engines love to append '.' / '?')."""
    s = src.rstrip()
    if s and s[-1] not in _END_MARKS:
        return _TRAIL_PUNCT.sub("", en.rstrip())
    return en


def compose_insert(raw, en):
    """Selection followed by its English: after a space on the same line when
    the selection is one line, else on new lines below (en then has one line
    per source line). A trailing newline stays last (Word selects whole
    paragraphs including the paragraph mark)."""
    head = raw.rstrip()
    sep = _newline_of(head) if _LINE_SPLIT.search(head) else " "
    return head + sep + en + raw[len(head):]


def zh_to_en_text(raw):
    """Chinese selection -> the text to paste over it (original + English).
    Each non-empty line is translated on its own so the line structure
    survives; blank lines are kept in place. Raises ValueError (too long /
    too many lines) or TranslateError."""
    head = raw.strip()
    if len(head) > ZH_MAX:
        raise ValueError("选区过长(最多 %d 字)" % ZH_MAX)
    src = [ln.strip() for ln in _LINE_SPLIT.split(head)]
    todo = [ln for ln in src if ln]
    if len(todo) > ZH_MAX_LINES:
        raise ValueError("行数过多(最多 %d 行)" % ZH_MAX_LINES)
    order = tuple(CFG.get("engine_order", ["google", "mymemory"]))

    def one(line):
        en, _ = translate(line, "en", order, source_language="zh-CN")
        return mirror_end(line, re.sub(r"\s+", " ", en).strip())

    if len(todo) > 1:
        with ThreadPoolExecutor(max_workers=4) as pool:
            done = list(pool.map(one, todo))
    else:
        done = [one(todo[0])]
    it = iter(done)
    out = [next(it) if ln else "" for ln in src]
    return compose_insert(raw, _newline_of(head).join(out))


def _insert_text(text):
    """Paste text over the current selection via the clipboard, then put the
    clipboard back. Replacing (not arrow-key + paste) means a read-only page
    or PDF just ignores it instead of scrolling / turning a page."""
    saved = _clip_get()
    try:
        if not _clip_set(text):
            return
        time.sleep(0.03)
        _kbd.press(keyboard.Key.ctrl)
        _kbd.press("v")
        _kbd.release("v")
        _kbd.release(keyboard.Key.ctrl)
        time.sleep(0.35)         # let the target app read it before we restore
    finally:
        _clip_set(saved or "")
        with _lock:
            _state["inserting"] = False


def _start_insert(text):
    threading.Thread(target=_insert_text, args=(text,), daemon=True).start()


def deliver_insert(gen, text):
    """Paste now if the hotkey is already up, else when it is released: a
    synthesized Ctrl+V on top of a physically held Ctrl/Alt/Shift is a
    different shortcut."""
    with _lock:
        if gen != _state["gen"]:
            return
        if _state["held"]:
            _state["pending_insert"] = (gen, text)
            return
        _state["inserting"] = True
    _start_insert(text)

CFG = cfg_mod.load()

HOTKEY_MAP = {
    "f2": {keyboard.Key.f2},
    "ctrl": {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl},
    "alt": {keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt,
            getattr(keyboard.Key, "alt_gr", keyboard.Key.alt_r)},
    "shift": {keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift},
}


def hotkey_keys():
    return HOTKEY_MAP.get(str(CFG.get("hotkey", "f2")).lower(),
                          HOTKEY_MAP["f2"])


job_q = queue.Queue()
result_q = queue.Queue()
_lock = threading.Lock()
_state = {"held": False, "gen": 0, "last_move": 0.0, "released_at": 0.0,
          "pinned": False, "popup_rect": None,
          "pending_insert": None,   # (gen, text) waiting for the hotkey release
          "inserting": False}       # our own synthesized keys are in flight

mouse_ctl = mouse.Controller()
_PUNCT = "".join(set(string.punctuation) | {"“", "”", "‘", "’", "—", "…", "·", "，", "。"})


# --- input --------------------------------------------------------------
def set_pinned(pinned):
    with _lock:
        _state["pinned"] = bool(pinned)


def request_translation():
    try:
        x, y = mouse_ctl.position
    except Exception:
        return
    with _lock:
        if _state["pinned"]:          # frozen while pinned
            return
        r = _state["popup_rect"]      # frozen while the pointer is over the card
        if r is not None:
            rx, ry, rw, rh = r
            m = 6                     # small margin so edge buttons stay reachable
            if rw > 1 and rx - m <= x <= rx + rw + m \
                    and ry - m <= y <= ry + rh + m:
                return
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
            if _state["held"] or _state["inserting"]:
                return
            _state["held"] = True
            _state["pending_insert"] = None
        request_translation()


def on_release(key):
    if key in hotkey_keys():
        paste = None
        with _lock:
            if _state["inserting"]:       # echo of our own synthesized Ctrl
                return
            _state["held"] = False
            _state["released_at"] = time.time()
            pend, _state["pending_insert"] = _state["pending_insert"], None
            if pend and pend[0] == _state["gen"]:
                _state["inserting"] = True
                paste = pend[1]
        if int(CFG.get("linger_ms", 500)) <= 0:
            result_q.put(("hide", None, None, None))
        if paste is not None:
            _start_insert(paste)


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
    return clean_word(best["text"]), best_line


_SENT_END = re.compile(r"[.!?。！？…][\"'”’)\]]*\s*$")


def _l_top(ln):
    return min((w["y"] for w in ln["words"]), default=0)


def _l_bot(ln):
    return max((w["y"] + w["h"] for w in ln["words"]), default=0)


def _is_prose(text):
    t = (text or "").strip()
    if len(t.split()) < 2 or len(t) < 6:
        return False
    good = sum(c.isalpha() or c.isspace() or c in ",.;:'\"-" for c in t)
    return good >= 0.75 * len(t)


def assemble_sentence(lines, cur_line, word):
    """Join the OCR lines that make up the sentence the word sits in - handles
    text that wraps across visual lines. Stops at menu bars / other paragraphs
    by requiring tight line spacing and prose-looking neighbours."""
    if not cur_line or not cur_line["words"]:
        return None
    ordered = sorted((l for l in lines if l["words"]), key=_l_top)
    try:
        i = ordered.index(cur_line)
    except ValueError:
        return cur_line["text"].strip()
    hs = sorted(w["h"] for l in ordered for w in l["words"])
    lh = hs[len(hs) // 2] if hs else 20

    def adjacent(a, b):  # b sits directly under a, normal line spacing
        return 0 <= _l_top(b) - _l_bot(a) <= lh * 0.8

    parts = [cur_line["text"].strip()]
    j = i - 1
    while j >= 0 and _is_prose(ordered[j]["text"]) \
            and not _SENT_END.search(ordered[j]["text"]) \
            and adjacent(ordered[j], ordered[j + 1]):
        parts.insert(0, ordered[j]["text"].strip())
        if len(" ".join(parts)) > 340:
            break
        j -= 1
    k = i + 1
    while k < len(ordered) and not _SENT_END.search(" ".join(parts)) \
            and _is_prose(ordered[k]["text"]) \
            and adjacent(ordered[k - 1], ordered[k]):
        parts.append(ordered[k]["text"].strip())
        if len(" ".join(parts)) > 340:
            break
        k += 1

    joined = re.sub(r"\s+", " ", " ".join(parts)).strip()
    for s in re.split(r"(?<=[.!?。！？])\s+", joined):
        if re.search(r"(?i)\b%s\b" % re.escape(word), s):
            return s.strip()
    return joined


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
def _is_current(gen):
    with _lock:
        return gen == _state["gen"]


def worker_loop():
    sct = (getattr(mss, "MSS", None) or mss.mss)()
    while True:
        gen, x, y = job_q.get()
        with _lock:
            if gen != _state["gen"] or not _state["held"]:
                continue
        try:
            data, finish = do_lookup_fast(sct, x, y)
        except Exception as e:  # noqa: BLE001
            result_q.put(("error", gen, (x, y), str(e)))
            continue
        if data is None:
            result_q.put(("none", gen, (x, y), None))
            continue
        if "_zh_src" in data:
            try:
                text = zh_to_en_text(data["_zh_src"])
            except (TranslateError, ValueError) as e:
                result_q.put(("error", gen, (x, y), "中译英失败: %s" % e))
                continue
            result_q.put(("hide", gen, (x, y), None))
            deliver_insert(gen, text)
            continue
        # stage 1: word + phonetics + POS + the original sentence, right away
        result_q.put(("show", gen, (x, y), data))
        # stage 2: the online translation streams in
        if finish and _is_current(gen):
            try:
                finish()
            except Exception:  # noqa: BLE001
                data["_translating"] = False
            result_q.put(("show", gen, (x, y), data))


def _vscreen():
    u = ctypes.windll.user32
    return (u.GetSystemMetrics(76), u.GetSystemMetrics(77),
            u.GetSystemMetrics(78), u.GetSystemMetrics(79))


def do_lookup_fast(sct, x, y):
    """Everything that doesn't touch the network (~35 ms). Returns
    (data, finish) where finish() runs the online translation in place, or
    (None, None) when there's nothing under the cursor."""
    w, h = int(CFG["capture_width"]), int(CFG["capture_height"])
    vx, vy, vw, vh = _vscreen()
    left = max(vx, min(x - w // 2, vx + vw - w))
    top = max(vy, min(y - h // 2, vy + vh - h))

    _sel_saved = _selection_probe_begin()
    shot = sct.grab({"left": left, "top": top, "width": w, "height": h})
    png = mss.tools.to_png(shot.rgb, shot.size)
    lines = ocr_png_bytes(png, CFG.get("ocr_language", "en-US"))
    word, cur_line = pick_word(lines, x - left, y - top)
    raw_sel = _selection_probe_end(_sel_saved)
    if CFG.get("zh_to_en", True) and han_ratio(raw_sel) > ZH_RATIO:
        return {"_zh_src": raw_sel}, None
    selection = _english_selection(raw_sel)

    if not word or not re.search(r"[A-Za-z]", word):
        if selection:
            word = re.split(r"\s+",
                            re.sub(r"[^A-Za-z\s'-]", " ", selection).strip())[0]
        if not word or not re.search(r"[A-Za-z]", word):
            return None, None
        cur_line = None

    sentence = selection or assemble_sentence(lines, cur_line, word)

    order = tuple(CFG.get("engine_order", ["google", "mymemory"]))
    tl = CFG.get("target_language", "zh-CN")
    source = str(CFG.get("translate_source", "local")).lower()
    entry = dictionary.lookup(word)

    data = {"word": word, "phonetic": entry.phonetic if entry else "",
            "primary": "", "pos_groups": entry.pos_groups if entry else [],
            "sentence_en": None, "sentence_cn": None,
            "spans_en": [], "spans_cn": [], "_translating": False}

    cn_candidates = list(entry.meanings) if entry else []
    if entry and source != "google":
        data["primary"] = entry.primary()

    has_sentence = bool(sentence and len(sentence.split()) > 1
                        and sentence.strip().lower() != word.strip().lower())
    if has_sentence:
        data["sentence_en"] = sentence
        data["spans_en"] = spans_in(sentence, word)

    need_word_online = (source == "google") or not entry
    if need_word_online or has_sentence:
        data["_translating"] = True

    def finish():
        wt = ""
        if need_word_online:
            try:
                wt = re.sub(r"\s+", " ", translate(word, tl, order)[0]).strip()
            except TranslateError:
                wt = ""
        if source == "google":
            data["primary"] = wt or data["primary"] or (
                entry.primary() if entry else "(在线翻译失败)")
        elif not entry:
            data["primary"] = wt or "(词典未收录, 在线翻译失败)"
        cands = cn_candidates + (re.split(r"[；;，,、\s]+", wt) if wt else [])

        if has_sentence:
            try:
                st, _ = translate(sentence, tl, order)
                data["sentence_cn"] = st
                data["spans_cn"] = align_cn(st, cands)
            except TranslateError:
                data["sentence_cn"] = "(整句翻译失败)"
        data["_translating"] = False

    return data, (finish if data["_translating"] else None)


# --- Tk poll loop -----------------------------------------------------
def _active(popup):
    with _lock:
        held, rel = _state["held"], _state["released_at"]
    linger = int(CFG.get("linger_ms", 500))
    return (held or popup.pinned
            or (linger > 0 and rel and (time.time() - rel) * 1000 < linger))


def poll(root, holder):
    popup = holder["popup"]
    rect = None
    try:
        if popup.win.winfo_viewable():
            rect = (popup.win.winfo_rootx(), popup.win.winfo_rooty(),
                    popup.win.winfo_width(), popup.win.winfo_height())
    except tk.TclError:
        rect = None
    with _lock:
        _state["pinned"] = popup.pinned
        _state["popup_rect"] = rect
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
def make_tray(root, holder):
    try:
        import pystray
    except Exception:
        print("未安装 pystray/Pillow, 跳过托盘图标")
        return None

    icon_img = appicon.render(64)

    def rebuild_popup():
        holder["popup"].win.destroy()
        holder["popup"] = Popup(root, CFG, on_speak=tts.speak, on_pin=set_pinned,
                                on_copy=_clip_set)

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
        M("按住 %s 划词 · 点 📌 钉住" % CFG.get("hotkey", "f2").capitalize(),
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

    holder = {"popup": Popup(root, CFG, on_speak=tts.speak, on_pin=set_pinned,
                             on_copy=_clip_set)}

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

    _tr.prewarm(CFG.get("target_language", "zh-CN"),
                CFG.get("engine_order", ["google", "mymemory"]))

    threading.Thread(target=worker_loop, daemon=True).start()
    threading.Thread(target=debounce_loop, daemon=True).start()

    kl = keyboard.Listener(on_press=on_press, on_release=on_release)
    ml = mouse.Listener(on_move=on_move)
    kl.daemon = ml.daemon = True
    kl.start()
    ml.start()

    make_tray(root, holder)
    print("%s 已启动。按住 %s 指向英文单词即可翻译。"
          % (APP_NAME, CFG.get("hotkey", "f2").capitalize()))

    root.after(25, poll, root, holder)
    try:
        root.mainloop()
    finally:
        kl.stop()
        ml.stop()


if __name__ == "__main__":
    main()
