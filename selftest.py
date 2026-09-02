"""End-to-end check without the mouse/hotkey: render text -> OCR -> pick word
-> dictionary -> sentence translation -> alignment.  Verifies everything the
worker does in do_lookup()."""

import io

from PIL import Image, ImageDraw, ImageFont

import dictionary
from main import align_cn, pick_word, spans_in
from ocr import ocr_png_bytes
from translate import translate

SENT = "The team proved remarkably resilient under enormous pressure."
TARGET = "resilient"

img = Image.new("RGB", (900, 70), "white")
d = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("segoeui.ttf", 30)
except Exception:
    font = ImageFont.load_default()
d.text((12, 16), SENT, fill="black", font=font)
buf = io.BytesIO()
img.save(buf, format="PNG")

lines = ocr_png_bytes(buf.getvalue(), "en-US")
print("OCR:", [ln["text"] for ln in lines])

tgt = None
for ln in lines:
    for w in ln["words"]:
        if TARGET in w["text"].lower():
            tgt = w
assert tgt, "OCR missed target word"
cx, cy = tgt["x"] + tgt["w"] / 2, tgt["y"] + tgt["h"] / 2
word, sentence = pick_word(lines, cx, cy)
print("picked word :", repr(word))
print("picked line :", repr(sentence))

entry = dictionary.lookup(word)
print("dict phonetic:", entry.phonetic if entry else None)
print("dict primary :", entry.primary() if entry else None)
print("dict groups  :", entry.pos_groups if entry else None)

st, eng = translate(sentence, "zh-CN", ("google", "mymemory"))
print("sentence CN  :", st, "  [%s]" % eng)
print("span EN      :", spans_in(sentence, word), "->",
      sentence[slice(*spans_in(sentence, word)[0])] if spans_in(sentence, word) else None)
cands = list(entry.meanings) if entry else []
sp = align_cn(st, cands)
print("span CN      :", sp, "->", st[slice(*sp[0])] if sp else "(none - best effort)")
ok = word == TARGET and entry and entry.phonetic and st
print("\nPIPELINE OK" if ok else "\nCHECK ABOVE")
