"""End-to-end check without the mouse/hotkey: render text -> OCR -> pick word
-> assemble sentence -> dictionary -> sentence translation -> alignment."""

import io

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

full = "academic outcomes" in sentence and "Others" not in sentence
print("\nPIPELINE OK" if (word == TARGET and entry and entry.phonetic and full and copy_ok)
      else "\nCHECK ABOVE (sentence assembly may need tuning)")
