"""End-to-end check without the mouse/hotkey: render text -> OCR -> pick word
-> assemble sentence -> dictionary -> sentence translation -> alignment."""

import io

from PIL import Image, ImageDraw, ImageFont

import dictionary
from main import align_cn, assemble_sentence, pick_word, spans_in
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

full = "academic outcomes" in sentence and "Others" not in sentence
print("\nPIPELINE OK" if (word == TARGET and entry and entry.phonetic and full)
      else "\nCHECK ABOVE (sentence assembly may need tuning)")
