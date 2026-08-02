"""
migrate_soong.py - 补移 Build-System/Soong/ 剩余 8 篇 + 删空目录
"""
import subprocess
from pathlib import Path

REPO = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")


def g(args, check=True):
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=REPO)
    return r.returncode, r.stdout, r.stderr


# 1) 补移 Build-System/Soong/ 8 个文件 -> 卷 1/02/Soong/
code, out, err = g([
    "mv",
    "06-Foundation/Build-System/Soong",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/Soong"
], check=False)
print(f"[Soong mv] code={code} err={err[:100] if err else 'none'}")

# 2) 删 4 个空源目录
import os
empty_dirs = [
    "02-Symptom/S11-Startup",
    "06-Foundation/Build-System",
    "06-Foundation/SELinux",
    "06-Foundation/Dynamic-Updates",
]
for d in empty_dirs:
    full = REPO / d
    if not full.exists():
        continue
    items = [f for f in full.rglob("*") if f.is_file()]
    if items:
        print(f"  [SKIP] {d} has {len(items)} files left")
        continue
    code, out, err = g(["rm", "-r", d], check=False)
    if code == 0:
        print(f"  [OK] git rm -r {d}")
    else:
        print(f"  [FAIL] {d}: {err[:100] if err else 'none'}")
