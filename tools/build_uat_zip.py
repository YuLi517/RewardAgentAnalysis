# -*- coding: utf-8 -*-
"""
build_uat_zip.py
================
Build UAT customer package: source zip, customer runs pip install + python main.py locally.

Excludes:
- tests/        (dev tests, not for customers)
- .git/         (git history)
- .worktrees/   (worktree residue)
- .pytest_cache/
- __pycache__/
- .claude/
- uvi*.log / uvicorn*.log  (server boot logs)
- data/rewarddb.db         (gitignored, auto-created on first launch)
- .env                     (personal key config, customer uses .env.example)
- .env.MiniMax             (historical residue)

Output: outputs/RewardAgentAnalysis-UAT-v0.1.zip
"""
from __future__ import annotations
import sys
import io
import zipfile
from pathlib import Path

# PowerShell GBK encoding fallback (AGENTS.md §5.13)
if sys.stdout.encoding and sys.stdout.encoding.lower().startswith("gbk"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent  # 脚本所在 tools/ 的父目录 (项目根)
OUT_DIR = REPO / "outputs"
OUT_ZIP = OUT_DIR / "RewardAgentAnalysis-UAT-v0.1.zip"

EXCLUDE_DIRS = {
    "tests",
    ".git",
    ".worktrees",
    ".pytest_cache",
    "__pycache__",
    ".claude",
    "data",            # do not bundle old db, customer creates on first launch
    "outputs",         # do not bundle this script's own output
}

EXCLUDE_FILES = {
    ".env",            # personal key
    ".env.MiniMax",
    "uvi.out.log",
    "uvi.err.log",
    "uvicorn.out.log",
    "uvicorn.err.log",
    "uvicorn.out",
    "uvicorn.err",
    "_commit_pr14.py",
}

EXCLUDE_GLOBS = [
    "**/__pycache__",
    "**/.pytest_cache",
    "**/*.pyc",
    "**/*.pyo",
]


def should_exclude(path: Path, src_root: Path) -> bool:
    rel = path.relative_to(src_root)
    parts = rel.parts
    for p in parts:
        if p in EXCLUDE_DIRS:
            return True
    if path.is_file():
        if path.name in EXCLUDE_FILES:
            return True
        for glob in EXCLUDE_GLOBS:
            if path.match(glob):
                return True
    return False


def build():
    if not REPO.exists():
        print("[ERR] Repo not found:", REPO)
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_ZIP.exists():
        OUT_ZIP.unlink()
        print("[DEL] Removed existing", OUT_ZIP.name)

    print("[BUILD] UAT zip from:", REPO)
    print("[OUT]  ", OUT_ZIP)

    included = []
    excluded = []

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(REPO.rglob("*")):
            if not path.exists():
                continue
            if should_exclude(path, REPO):
                excluded.append(path.relative_to(REPO))
                continue
            arcname = path.relative_to(REPO)
            if path.is_file():
                zf.write(path, arcname)
                included.append((arcname, path.stat().st_size))

    size_kb = OUT_ZIP.stat().st_size / 1024
    size_mb = size_kb / 1024

    print()
    print("[OK] Done:", OUT_ZIP.name)
    print("     Size:    %.1f MB (%d KB)" % (size_mb, int(size_kb)))
    print("     Included: %d files" % len(included))
    print("     Excluded: %d paths" % len(excluded))

    print()
    print("[TOP] Top-level structure:")
    top_dirs = set()
    for arc, _ in included:
        s = str(arc).replace("\\", "/")
        if "/" in s:
            top = s.split("/")[0]
            top_dirs.add(top)
        else:
            top_dirs.add(s)
    for d in sorted(top_dirs):
        print("   -", d)

    if excluded:
        print()
        print("[EXCLUDED] %d paths:" % len(excluded))
        for ex in excluded[:20]:
            print("   -", ex)
        if len(excluded) > 20:
            print("   ... and", len(excluded) - 20, "more")

    print()
    print("[KEY] Key included files:")
    key_files = [
        "main.py", "models.py", "repository.py", "database.py",
        "requirements.txt", "start_uvicorn.bat",
        "README.md", "CUSTOMER_GUIDE.md", "CUSTOMER_GUIDE.html",
        ".env.example", "LICENSE", "AGENTS.md",
    ]
    for kf in key_files:
        match = next((arc for arc, _ in included if str(arc).replace("\\", "/") == kf), None)
        if match:
            sz = next(sz for arc, sz in included if arc == match)
            print("   [OK]   %s (%.1f KB)" % (kf, sz/1024))
        else:
            print("   [MISS] %s (NOT INCLUDED)" % kf)

    return OUT_ZIP


if __name__ == "__main__":
    build()
