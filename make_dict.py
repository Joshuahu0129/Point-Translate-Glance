"""Build the bundled offline dictionary ``glance-dict.db`` from ECDICT.

    python make_dict.py [path-to-stardict.csv]

Downloads stardict.7z if no CSV path is given and none is found locally.
Keeps only entries that are (a) a plain English word/phrase and (b) common
enough to actually be pointed at - judged by corpus-frequency rank, exam tags,
or Collins/Oxford markers.  Result is ~10-18 MB.
"""

import csv
import io
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "glance-dict.db")
WORD_RE = re.compile(r"^[a-z][a-z .'\-]{0,28}$")
POS_HINT = re.compile(r"(^|\n)\s*[a-z]{1,6}\.\s", re.I)
FREQ_MAX = 60000


def find_csv():
    for c in (os.path.join(HERE, "stardict.csv"),
              os.path.join(os.path.dirname(HERE), "stardict.csv"),
              r"C:\Users\admin\mt\stardict.csv"):
        if os.path.exists(c):
            return c
    return None


def _int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def keep(word, translation, collins, oxford, tag, bnc, frq):
    if not translation or not WORD_RE.match(word):
        return False
    if word.endswith(".") or "  " in word:
        return False
    if 1 <= _int(frq) <= FREQ_MAX or 1 <= _int(bnc) <= FREQ_MAX:
        return True
    if _int(collins) >= 1 or oxford == "1" or tag.strip():
        return True
    # short, clearly-lexical words with a part-of-speech tag
    if len(word) <= 10 and " " not in word and POS_HINT.search(translation):
        return len(translation) <= 120
    return False


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else find_csv()
    if not src or not os.path.exists(src):
        sys.exit("找不到 stardict.csv,请传入路径:  python make_dict.py <csv>")

    if os.path.exists(OUT):
        os.remove(OUT)
    db = sqlite3.connect(OUT)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("CREATE TABLE words (word TEXT PRIMARY KEY, phonetic TEXT, "
               "translation TEXT)")

    csv.field_size_limit(1 << 24)
    n_in = n_out = 0
    with io.open(src, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        buf = []
        for row in reader:
            n_in += 1
            if len(row) < 10:
                continue
            word = row[0].strip().lower()
            phonetic, translation = row[1].strip(), row[3].replace("\\n", "\n")
            collins, oxford, tag, bnc, frq = row[5], row[6], row[7], row[8], row[9]
            if not keep(word, translation, collins, oxford, tag, bnc, frq):
                continue
            buf.append((word, phonetic, translation))
            n_out += 1
            if len(buf) >= 5000:
                db.executemany("INSERT OR IGNORE INTO words VALUES (?,?,?)", buf)
                buf.clear()
        if buf:
            db.executemany("INSERT OR IGNORE INTO words VALUES (?,?,?)", buf)
    db.commit()
    db.execute("VACUUM")
    db.commit()
    db.close()
    size = os.path.getsize(OUT) / 1e6
    print("读取 %d 条,保留 %d 条 -> %s (%.1f MB)" % (n_in, n_out, OUT, size))


if __name__ == "__main__":
    main()
