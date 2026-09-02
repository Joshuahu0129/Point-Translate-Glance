"""Online translation engines (no API key required).

- google   : translate.googleapis.com free endpoint. Best quality, supports
             words and full sentences. Often blocked in mainland China.
- mymemory : api.mymemory.translated.net free endpoint. Works without a key,
             daily character quota, decent fallback.
"""

import json
import urllib.parse
import urllib.request
from collections import OrderedDict

_TIMEOUT = 6
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_cache = OrderedDict()
_CACHE_MAX = 500


class TranslateError(Exception):
    pass


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8", "replace")


def _google(text, tl, sl="en"):
    url = (
        "https://translate.googleapis.com/translate_a/single"
        "?client=gtx&sl=%s&tl=%s&dt=t&q=%s"
        % (sl, tl, urllib.parse.quote(text))
    )
    data = json.loads(_get(url))
    parts = [seg[0] for seg in data[0] if seg and seg[0]]
    out = "".join(parts).strip()
    if not out:
        raise TranslateError("google: empty result")
    return out


def _mymemory(text, tl, sl="en"):
    # MyMemory wants short region-less codes for some languages.
    tl_short = {"zh-CN": "zh-CN", "zh-TW": "zh-TW"}.get(tl, tl.split("-")[0])
    url = (
        "https://api.mymemory.translated.net/get?q=%s&langpair=%s"
        % (urllib.parse.quote(text), urllib.parse.quote(sl + "|" + tl_short))
    )
    data = json.loads(_get(url))
    status = data.get("responseStatus")
    if status not in (200, "200"):
        raise TranslateError("mymemory: %s" % data.get("responseDetails"))
    out = (data.get("responseData") or {}).get("translatedText", "").strip()
    if not out or out.upper().startswith(("PLEASE SELECT", "INVALID")):
        raise TranslateError("mymemory: no translation")
    return out


ENGINES = {"google": _google, "mymemory": _mymemory}


def translate(text, target_language="zh-CN", engine_order=("google", "mymemory"),
              source_language="en"):
    text = (text or "").strip()
    if not text:
        raise TranslateError("empty text")

    key = (text.lower(), target_language)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

    errors = []
    for name in engine_order:
        fn = ENGINES.get(name)
        if fn is None:
            continue
        try:
            out = fn(text, target_language, source_language)
            result = (out, name)
            _cache[key] = result
            if len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
            return result
        except Exception as e:  # noqa: BLE001 - try the next engine
            errors.append("%s: %s" % (name, e))
    raise TranslateError("; ".join(errors) or "all engines failed")
