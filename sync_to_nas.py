"""Refresh the read-only GitHub mirror on the NAS. Run after `git push`.

The NAS copy (G:\\03-开发中心\\03-活跃 active\\Point-Translate-Glance) is a plain
clone kept in lock-step with origin/main + all tags - a backup, not a working
copy. `MIRROR.txt` records which version it currently holds.
"""

import datetime
import pathlib
import subprocess
import sys

NAS = pathlib.Path(r"G:\03-开发中心\03-活跃 active\Point-Translate-Glance")
REPO = "https://github.com/Joshuahu0129/Point-Translate-Glance.git"
HERE = pathlib.Path(__file__).parent

# Files that are git-ignored (never pushed to GitHub) but must still be backed
# up. They are copied into the NAS mirror on every sync.
KEEP_LOCAL = ["AGENTS.md", "CLAUDE.md", "DECISIONS.md"]


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def main():
    if not (NAS / ".git").exists():
        print("first run - cloning the mirror to the NAS (slow over RaiDrive) ...")
        NAS.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", REPO, str(NAS)], check=True)
    else:
        git("fetch", "--all", "--tags", "--prune", cwd=NAS)
        git("reset", "--hard", "origin/main", cwd=NAS)

    # back up the git-ignored local-only docs
    copied = []
    for name in KEEP_LOCAL:
        src = HERE / name
        if src.exists():
            (NAS / name).write_bytes(src.read_bytes())
            copied.append(name)

    ver = git("describe", "--tags", "--always", cwd=NAS)
    short = git("rev-parse", "--short", "HEAD", cwd=NAS)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    (NAS / "MIRROR.txt").write_text(
        "Point-Translate-Glance - GitHub 镜像备份 (只读, 勿在此开发)\n\n"
        f"版本:   {ver}\n"
        f"提交:   {short}\n"
        f"同步于: {now}\n"
        "源:     https://github.com/Joshuahu0129/Point-Translate-Glance\n"
        "开发在: E:\\dev\\point-translate-glance\n"
        + (("本地文件备份: " + ", ".join(copied) + "\n") if copied else ""),
        encoding="utf-8-sig",
    )
    print(f"[ok] mirror synced -> {ver} ({short})"
          + (f"  + local: {', '.join(copied)}" if copied else ""))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.stderr.write((e.stderr or str(e)) + "\n")
        sys.exit(1)
