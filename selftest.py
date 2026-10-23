"""End-to-end check without the mouse/hotkey: render text -> OCR -> pick word
-> assemble sentence -> dictionary -> sentence translation -> alignment."""

import io
import re

from PIL import Image, ImageDraw, ImageFont

import dictionary
from main import (_clip_get, _clip_set, align_cn, assemble_sentence, pick_word,
                  spans_in)
from ocr import ocr_png_bytes
from translate import translate

# two visual lines = one wrapped sentence, plus a trailing sentence
LINES = ["Diligent students who study hard often achieve",
         "remarkable academic outcomes. Others simply give up."]
TARGET = "academic"

img = Image.new("RGB", (760, 110), "white")
d = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("segoeui.ttf", 26)
except Exception:
    font = ImageFont.load_default()
for i, t in enumerate(LINES):
    d.text((12, 12 + i * 40), t, fill="black", font=font)
buf = io.BytesIO()
img.save(buf, format="PNG")

lines = ocr_png_bytes(buf.getvalue(), "en-US")
print("OCR lines:", [ln["text"] for ln in lines])

tgt = None
for ln in lines:
    for w in ln["words"]:
        if TARGET in w["text"].lower():
            tgt = w
assert tgt, "OCR missed target word"
word, cur_line = pick_word(lines, tgt["x"] + tgt["w"] / 2, tgt["y"] + tgt["h"] / 2)
sentence = assemble_sentence(lines, cur_line, word)
print("picked word :", repr(word))
print("assembled   :", repr(sentence))

entry = dictionary.lookup(word)
print("dict phonetic:", entry.phonetic if entry else None)
print("dict primary :", entry.primary() if entry else None)

st, eng = translate(sentence, "zh-CN", ("google", "mymemory"))
print("sentence CN :", st, " [%s]" % eng)
se = spans_in(sentence, word)
print("span EN     :", se, "->", sentence[slice(*se[0])] if se else None)
sp = align_cn(st, list(entry.meanings) if entry else [])
print("span CN     :", sp, "->", st[slice(*sp[0])] if sp else "(none - best effort)")

# --- exe icon: glance.ico must exist and carry the sizes Windows asks for ---
import os

from PIL import Image as _Image

_ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glance.ico")
_sizes = set(_Image.open(_ico).info.get("sizes", ())) if os.path.exists(_ico) else set()
icon_ok = {(16, 16), (32, 32), (48, 48), (256, 256)} <= _sizes
print("glance.ico  :", sorted(_sizes) if icon_ok else "MISSING or incomplete")

# --- double-click-to-copy on the card (word, English line, Chinese line) ---
import tkinter as tk

import config
from popup import Popup

# real clipboard round-trip; SKIP when the session may not touch the clipboard
# (e.g. a sandboxed shell gets ACCESS_DENIED from OpenClipboard)
saved_clip = _clip_get()
if _clip_set("glance-selftest"):
    assert _clip_get() == "glance-selftest", "clipboard round-trip failed"
    _clip_set(saved_clip or "")
    print("clipboard   : round-trip OK")
else:
    print("clipboard   : SKIP (clipboard not accessible from this session)")

root = tk.Tk()
root.withdraw()
copied = []


def _dbl(widget):
    """Tk refuses to synthesize <Double-...>; two quick press/release pairs
    are recognised as a double-click by the binding system."""
    for _ in range(2):
        widget.event_generate("<ButtonPress-1>", x=5, y=5)
        widget.event_generate("<ButtonRelease-1>", x=5, y=5)


card = Popup(root, config.load(), on_copy=lambda t: copied.append(t))
card.show(None, {"word": word, "phonetic": "x", "pos_groups": [("n.", ["a"])],
                 "sentence_en": sentence, "sentence_cn": st,
                 "spans_en": [], "spans_cn": []})
card.win.update()
for w in (card.l_word, card.t_en, card.t_cn):
    _dbl(w)
    card.win.update()
card.show(None, {"word": word, "sentence_en": sentence, "_translating": True})
card.win.update()
_dbl(card.t_cn)   # "翻译中…" must be ignored
card.win.update()
card.show_message(None, "未识别到单词")
_dbl(card.l_word)  # a message is not a word
card.win.update()
root.destroy()
print("copied      :", copied)
copy_ok = copied == [word, sentence, st]

# --- Chinese selection -> English pasted after it ---
import main as _m
from pynput import keyboard as _kb

zh_ok = True


def _check(name, cond):
    global zh_ok
    if not cond:
        zh_ok = False
        print("zh->en FAIL :", name)


_hr = _m.han_ratio
_check("all Han", _hr("今天天气很好") == 1.0)
_check("mostly English is not Chinese", _hr("你好 hello world") <= 0.5)
_check("exactly 50% is not over 50%", _hr("你好ab") == 0.5 and not _hr("你好ab") > 0.5)
_check("just over 50%", _hr("你好a") > 0.5)
_check("whitespace ignored", _hr(" 你 好 " + chr(10)) == 1.0)
_check("empty / punctuation only", _hr("") == 0.0 and _hr("，。！") == 0.0)
_check("digits count against", _hr("今天是 2026 年") == 0.5)
_CRLF = chr(13) + chr(10)
_check("compose", _m.compose_insert("你好", "Hi") == "你好 Hi")
_check("compose keeps trailing newline",
       _m.compose_insert("你好。" + _CRLF, "Hello.") == "你好。 Hello." + _CRLF)

_zh = "今天天气很好，我们去公园散步吧。"
_out = _m.zh_to_en_text(_zh)
print("zh->en      :", _out)
_en_part = _out[len(_zh):]
_check("original kept + English appended",
       _out.startswith(_zh + " ") and re.search(r"[A-Za-z]{3}", _en_part)
       and not _m._HAN.search(_en_part))
try:
    _m.zh_to_en_text("好" * 401)
    _check("too long is rejected", False)
except ValueError:
    pass

# release-then-paste state logic, with a fake pasting function
_calls = []
_real_start = _m._start_insert
_m._start_insert = _calls.append
_hk = next(iter(_m.hotkey_keys()))
_S = _m._state


def _reset(**kw):
    with _m._lock:
        _S.update(dict(held=False, gen=0, pending_insert=None, inserting=False), **kw)


_reset(held=True, gen=7)
_m.deliver_insert(7, "T")
_check("held -> waits", not _calls and _S["pending_insert"] == (7, "T"))
_m.on_release(_hk)
_check("release -> pastes once", _calls == ["T"] and _S["inserting"]
       and _S["pending_insert"] is None)
_reset(held=True, gen=8, pending_insert=(7, "old"))
_m.on_release(_hk)
_check("stale generation is dropped", _calls == ["T"])
_reset(held=False, gen=9)
_m.deliver_insert(9, "now")
_check("already released -> pastes now", _calls == ["T", "now"])
_reset(held=False, gen=10)
_m.deliver_insert(9, "superseded")
_check("superseded lookup never pastes", _calls == ["T", "now"])
_reset(held=True, gen=11, inserting=True)
_m.on_release(_hk)
_check("echo of our own keys ignored", _S["held"] is True)
_reset()
_m._start_insert = _real_start
print("zh->en logic:", "OK" if zh_ok else "FAILED")

full = "academic outcomes" in sentence and "Others" not in sentence
print("\nPIPELINE OK" if (word == TARGET and entry and entry.phonetic and full and copy_ok and icon_ok and zh_ok)
      else "\nCHECK ABOVE (sentence assembly may need tuning)")
