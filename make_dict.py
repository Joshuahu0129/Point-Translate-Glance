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
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "glance-dict.db")
WORD_RE = re.compile(r"^[a-z][a-z .'\-]{0,28}$")
POS_HINT = re.compile(r"(^|\n)\s*[a-z]{1,6}\.\s", re.I)
FREQ_MAX = 60000

STARDICT_URL = "https://raw.githubusercontent.com/skywind3000/ECDICT/master/stardict.7z"
STARDICT_7Z = os.path.join(HERE, "stardict.7z")
STARDICT_CSV = os.path.join(HERE, "stardict.csv")


def find_csv():
    for c in (os.path.join(HERE, "stardict.csv"),
              os.path.join(os.path.dirname(HERE), "stardict.csv"),
              r"C:\Users\admin\mt\stardict.csv"):
        if os.path.exists(c):
            return c
    return None


def download_csv():
    """Fetch ECDICT's stardict.7z and extract stardict.csv from it.
    Needs py7zr (requirements-dev.txt). Returns the path to the extracted CSV."""
    try:
        import py7zr
    except ImportError:
        sys.exit("需要 py7zr 才能解压 ECDICT 归档:  pip install py7zr\n"
                 "(已在 requirements-dev.txt 里,跑一遍 setup-dev.bat 也行)")

    print("本地没找到 stardict.csv,从 ECDICT 下载 stardict.7z(约 10MB 压缩包,"
         "解压后 ~230MB)。")
    print("raw.githubusercontent.com 在国内经常限速,实测可能要几十分钟 - 正常,"
         "别以为卡死了。想更快就去 %s 手动下,存成 %s。" % (STARDICT_URL, STARDICT_7Z))
    try:
        with urllib.request.urlopen(STARDICT_URL, timeout=180) as r, \
                open(STARDICT_7Z, "wb") as f:
            f.write(r.read())
    except Exception as e:  # noqa: BLE001
        sys.exit("下载失败: %s\n可以手动下载 %s 放到 %s,或直接传 CSV 路径给本脚本"
                 % (e, STARDICT_URL, HERE))

    print("解压中...")
    with py7zr.SevenZipFile(STARDICT_7Z, mode="r") as z:
        z.extractall(path=HERE)
    os.remove(STARDICT_7Z)

    if not os.path.exists(STARDICT_CSV):
        sys.exit("解压后没找到 stardict.csv - ECDICT 的归档内容可能变了,"
                 "去 %s 手动看一下" % STARDICT_URL)
    return STARDICT_CSV


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
        src = download_csv()

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
