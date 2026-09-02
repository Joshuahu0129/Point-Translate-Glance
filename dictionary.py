"""Offline English -> Chinese dictionary (ECDICT subset) in a bundled SQLite DB.

The DB is produced by ``make_dict.py`` and shipped as ``glance-dict.db`` next to
this file / inside the PyInstaller bundle.  If it is missing, every lookup just
returns ``None`` and the app falls back to the online translator.
"""

import os
import re
import sqlite3
import sys
import threading

_DB_NAME = "glance-dict.db"
_conn = None
_lock = threading.Lock()

POS_LABELS = {
    "n": "n.", "pl": "n.", "v": "v.", "vt": "vt.", "vi": "vi.",
    "adj": "adj.", "a": "adj.", "adv": "adv.", "ad": "adv.",
    "prep": "prep.", "conj": "conj.", "pron": "pron.", "art": "art.",
    "num": "num.", "int": "int.", "interj": "int.", "abbr": "abbr.",
    "aux": "aux.", "modal": "aux.", "prefix": "前缀", "suffix": "后缀",
}
POS_ORDER = ["n.", "v.", "vt.", "vi.", "adj.", "adv.", "prep.", "conj.",
             "pron.", "art.", "num.", "int.", "abbr.", "aux.", "前缀", "后缀"]

_SPLIT = re.compile(r"[；;，,、/|]\s*|\s{2,}")
_POS_LINE = re.compile(r"^\s*([a-zA-Z]{1,6})\.\s*(.+)$")
_BRACKET = re.compile(r"^\s*\[[^\]]*\]\s*")
_NET_LINE = re.compile(r"^\s*\[(网络|口|俚|昆|化|医|电|计|经|法|物|数|生|机|军)")
_FORM_NOTE = re.compile(r"(过去式|过去分词|现在分词|三单|第三人称单数|复数形式|"
                        r"进行时|原形|缩写|变形|的.{0,4}形式|abbr)")


def _resource_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def db_path():
    return os.path.join(_resource_dir(), _DB_NAME)


def available():
    return os.path.exists(db_path())


def _get_conn():
    global _conn
    if _conn is None:
        if not available():
            return None
        _conn = sqlite3.connect(db_path(), check_same_thread=False)
    return _conn


class Entry:
    __slots__ = ("word", "phonetic", "translation", "pos_groups", "meanings")

    def __init__(self, word, phonetic, translation):
        self.word = word
        ph = (phonetic or "").strip().strip("/")
        self.phonetic = (ph.replace("'", "ˈ").replace(",", "ˌ")
                         .replace(":", "ː"))
        self.translation = translation or ""
        self.pos_groups = _parse_translation(self.translation)
        # flat list of short meanings, best first (for sentence-side highlight)
        self.meanings = []
        for _, ms in self.pos_groups:
            for m in ms:
                if m not in self.meanings:
                    self.meanings.append(m)

    def primary(self, limit=2):
        if self.pos_groups:
            return "；".join(self.pos_groups[0][1][:limit])
        return "；".join(self.meanings[:limit])


def _clean_parts(body):
    out = []
    for p in _SPLIT.split(body):
        p = (p or "").strip(" .·　")
        if not (1 <= len(p) <= 14):
            continue
        if "…" in p or _FORM_NOTE.search(p):
            continue
        if p.startswith("(") or p.startswith("（"):
            continue
        out.append(p)
    return out


def _parse_translation(text):
    groups = {}
    order = []
    misc = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or _NET_LINE.match(line):
            continue
        m = _POS_LINE.match(line)
        if m and m.group(1).lower() in POS_LABELS:
            label = POS_LABELS[m.group(1).lower()]
            parts = _clean_parts(m.group(2))
        else:
            label = None
            parts = _clean_parts(_BRACKET.sub("", line))
        if not parts:
            continue
        if label is None:
            misc.extend(parts)
            continue
        if label not in groups:
            groups[label] = []
            order.append(label)
        for p in parts:
            if p not in groups[label]:
                groups[label].append(p)

    if not order and misc:
        groups["释义"] = list(dict.fromkeys(misc))
        order.append("释义")

    def rank(lbl):
        return POS_ORDER.index(lbl) if lbl in POS_ORDER else 90

    return [(lbl, groups[lbl][:10])
            for lbl in sorted(order, key=rank)]


def lookup(word):
    if not word:
        return None
    conn = _get_conn()
    if conn is None:
        return None
    key = word.strip().lower()
    with _lock:
        row = conn.execute(
            "SELECT word, phonetic, translation FROM words WHERE word = ?",
            (key,),
        ).fetchone()
        if row is None and key != word.strip():
            row = conn.execute(
                "SELECT word, phonetic, translation FROM words WHERE word = ?",
                (word.strip(),),
            ).fetchone()
    if row is None:
        return None
    entry = Entry(row[0] or word, row[1], row[2])
    if not entry.pos_groups:
        return None
    return entry
