"""
commit_migrate_v1v2.py - 提交卷 1+2 物理迁移
"""
import subprocess
from pathlib import Path

REPO = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")


def g(args):
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=REPO)
    return r.returncode, r.stdout, r.stderr


# 用 git add -A 让 git 检测 rename
print("[STEP] git add -A (auto-detect renames)")
code, out, err = g(["add", "-A"])
print(f"  code={code}")

# Commit 1: 物理迁移（69 个 rename）
print()
print("[STEP] git commit 1 (volume 1+2 migration)")
code, out, err = g(["commit", "-m",
    "refactor: migrate volume 1+2 content to 8-volume book structure\n\n"
    "Migrate 69 files into the new 8-volume 50-chapter layout (volume 1+2 only).\n\n"
    "Volume 1 (Android system basics & platform):\n"
    "  Ch 1  Android system panorama: 1 file (from 02-Symptom/S08-AOSP17-K618)\n"
    "  Ch 2  AOSP source & build: 21 files (Build-System + Soong/)\n"
    "  Ch 5  Security basics: 11 files (SELinux + Dynamic-Updates)\n"
    "  Ch 3/4: 0 files (skeleton only, no content yet)\n"
    "  Volume 1 total: 33 files\n\n"
    "Volume 2 (System startup):\n"
    "  Ch 10 App startup & first frame: 21 files (A-启动机制 6 + Old 15)\n"
    "  Ch 11 Startup performance: 13 files (B/C/D-启动*)\n"
    "  Ch 6-9: 0 files (skeleton only, need new content)\n"
    "  Volume 2 total: 34 files\n\n"
    "Source directories removed (emptied by git mv):\n"
    "  - 02-Symptom/S08-AOSP17-K618 (1 file moved out)\n"
    "  - 02-Symptom/S11-Startup (35 files moved out)\n"
    "  - 06-Foundation/Build-System (21 files moved out)\n"
    "  - 06-Foundation/SELinux (8 files moved out)\n"
    "  - 06-Foundation/Dynamic-Updates (4 files moved out)\n\n"
    "Known issue: internal links (../S11-Startup/...) are now broken.\n"
    "Will be repaired in a follow-up commit (link_repair script).\n\n"
    "Verification: mkdocs build --clean passes (38.03s, 0 errors).\n"
    "1288 link warnings are expected and tracked for repair."])
print(out[:500] if out else "")
if err:
    print(f"  stderr: {err[:200]}")
print()

# Commit 2: 4 个迁移脚本
print("[STEP] git commit 2 (migration scripts)")
SCRIPTS = [
    "00-Meta/scripts/migrate_v1_v2.py",
    "00-Meta/scripts/migrate_soong.py",
    "00-Meta/scripts/migrate_remaining.py",
]
code, out, err = g(["add", "--"] + SCRIPTS)
code, out, err = g(["commit", "-m",
    "chore(scripts): add volume 1+2 migration scripts\n\n"
    "- migrate_v1_v2.py: bulk git mv from old 8-module to new 8-volume\n"
    "- migrate_soong.py: complete Soong/ subdir move (Build-System/Soong/ -> volume 1/ch 2/Soong/)\n"
    "- migrate_remaining.py: clean up remaining S11-Startup/README, SELinux, Dynamic-Updates"])
print(out[:300] if out else "")
if err:
    print(f"  stderr: {err[:200]}")
print()

# 状态
print("=== STATUS ===")
code, out, err = g(["log", "--oneline", "-7"])
log_file = REPO / "00-Meta/scripts/commit_migrate.log"
log_file.write_text((out or "") + "\n\n", encoding="utf-8")
print("written to 00-Meta/scripts/commit_migrate.log")
