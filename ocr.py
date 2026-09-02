"""Windows built-in OCR (Windows.Media.Ocr) wrapper.

Requires the Windows language pack for the target language with the optional
"Optical character recognition" feature installed
(Settings -> Time & Language -> Language & region -> <language> -> Language
options -> Optical character recognition).
"""

import asyncio

from winsdk.windows.globalization import Language
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

_engine = None
_engine_lang = None


def _create_engine(lang_tag):
    eng = None
    if lang_tag:
        try:
            if OcrEngine.is_language_supported(Language(lang_tag)):
                eng = OcrEngine.try_create_from_language(Language(lang_tag))
        except Exception:
            eng = None
    if eng is None:
        eng = OcrEngine.try_create_from_user_profile_languages()
    return eng


def get_engine(lang_tag="en-US"):
    global _engine, _engine_lang
    if _engine is None or _engine_lang != lang_tag:
        _engine = _create_engine(lang_tag)
        _engine_lang = lang_tag
    return _engine


def ocr_available(lang_tag="en-US"):
    try:
        return get_engine(lang_tag) is not None
    except Exception:
        return False


async def _bytes_to_software_bitmap(png_bytes):
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(bytes(png_bytes))
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    return await decoder.get_software_bitmap_async()


async def _ocr(png_bytes, lang_tag):
    engine = get_engine(lang_tag)
    if engine is None:
        raise RuntimeError(
            "找不到可用的 OCR 引擎。请在 Windows 设置中为目标语言安装"
            "\"光学字符识别 (OCR)\" 语言功能。"
        )
    bitmap = await _bytes_to_software_bitmap(png_bytes)
    result = await engine.recognize_async(bitmap)
    lines = []
    for line in result.lines:
        words = []
        for w in line.words:
            r = w.bounding_rect
            words.append(
                {
                    "text": w.text,
                    "x": float(r.x),
                    "y": float(r.y),
                    "w": float(r.width),
                    "h": float(r.height),
                }
            )
        lines.append({"text": line.text, "words": words})
    return lines


def ocr_png_bytes(png_bytes, lang_tag="en-US"):
    """Run OCR on PNG bytes. Returns a list of {text, words:[{text,x,y,w,h}]}."""
    return asyncio.run(_ocr(png_bytes, lang_tag))
