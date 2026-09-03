"""Online translation over a keep-alive session (no API key).

- google   : clients5.google.com "dict-chrome-ex" endpoint - the one the Google
             Dictionary extension uses. Much less rate-limited than the old
             translate_a/single endpoint, and ~150-300 ms once the connection
             is warm.
- mymemory : api.mymemory.translated.net free endpoint, slower fallback with a
             daily character quota.

The shared requests.Session keeps the TLS connection open, so only the first
call per run pays the handshake (call prewarm() at startup to hide it), and it
picks up the system / env HTTP proxy automatically.
"""

import re
import threading
from collections import OrderedDict

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

try:
    import requests
    _sess = requests.Session()
    _sess.headers["User-Agent"] = _UA
except Exception:  # noqa: BLE001
    requests = None
    _sess = None

_TIMEOUT = (3.05, 5)
_cache = OrderedDict()
_CACHE_MAX = 1000
_lock = threading.Lock()


class TranslateError(Exception):
    pass


def _google(text, tl, sl):
    r = _sess.get(
        "https://clients5.google.com/translate_a/t",
        params={"client": "dict-chrome-ex", "sl": sl, "tl": tl, "q": text},
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        raise TranslateError("google HTTP %s" % r.status_code)
    data = r.json()
    if isinstance(data, list):
        out = "".join(p for p in data if isinstance(p, str)).strip()
    elif isinstance(data, dict):
        out = "".join(s.get("trans", "")
                      for s in data.get("sentences", [])).strip()
    else:
        out = ""
    if not out:
        raise TranslateError("google: empty result")
    return out


def _mymemory(text, tl, sl):
    tl_s = {"zh-CN": "zh-CN", "zh-TW": "zh-TW"}.get(tl, tl.split("-")[0])
    r = _sess.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": "%s|%s" % (sl, tl_s)},
        timeout=(3.05, 8),
    )
    d = r.json()
    if d.get("responseStatus") not in (200, "200"):
        raise TranslateError("mymemory: %s" % d.get("responseDetails"))
    out = (d.get("responseData") or {}).get("translatedText", "").strip()
    if not out or out.upper().startswith(("PLEASE SELECT", "INVALID",
                                          "QUERY LENGTH")):
        raise TranslateError("mymemory: no translation")
    return out


ENGINES = {"google": _google, "mymemory": _mymemory}


def translate(text, target_language="zh-CN", engine_order=("google", "mymemory"),
              source_language="en"):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        raise TranslateError("empty text")
    if _sess is None:
        raise TranslateError("requests 未安装")

    key = (text.lower(), target_language)
    with _lock:
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
            res = (out, name)
            with _lock:
                _cache[key] = res
                if len(_cache) > _CACHE_MAX:
                    _cache.popitem(last=False)
            return res
        except Exception as e:  # noqa: BLE001 - try the next engine
            errors.append("%s: %s" % (name, e))
    raise TranslateError("; ".join(errors) or "all engines failed")


def prewarm(target_language="zh-CN", engine_order=("google", "mymemory")):
    """Open the connection and prime the cache in the background at startup."""
    def run():
        try:
            translate("hello", target_language, tuple(engine_order))
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=run, daemon=True).start()
