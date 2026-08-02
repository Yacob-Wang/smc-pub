"""
migrate_remaining.py - 补移剩余文件
"""
import subprocess
from pathlib import Path

REPO = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")


def g(args, check=False):
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=REPO)
    return r.returncode, r.stdout, r.stderr


# 1) S11-Startup/README.md -> 02-卷2-系统启动/README.md
code, out, err = g([
    "mv", "02-Symptom/S11-Startup/README.md",
    "02-卷2-系统启动/README.md"
])
print(f"[README] code={code} err={err[:100] if err else 'none'}")

# 2) 06-Foundation/SELinux/* -> 01-卷1/05-安全基础（SELinux · AVB）/
sec_dst = "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/SELinux"
code, out, err = g(["mv", "06-Foundation/SELinux", sec_dst])
print(f"[SELinux] code={code} err={err[:100] if err else 'none'}")

# 3) 06-Foundation/Dynamic-Updates/* -> 01-卷1/05-安全基础（SELinux · AVB）/Dynamic-Updates
du_dst = "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates"
code, out, err = g(["mv", "06-Foundation/Dynamic-Updates", du_dst])
print(f"[Dynamic-Updates] code={code} err={err[:100] if err else 'none'}")

# 4) 清空 3 个源目录
for d in ["02-Symptom/S11-Startup", "06-Foundation/SELinux", "06-Foundation/Dynamic-Updates"]:
    full = REPO / d
    if not full.exists():
        print(f"  [OK] {d} not exist (cleaned)")
        continue
    items = [f for f in full.rglob("*") if f.is_file()]
    if items:
        print(f"  [SKIP] {d} still has {len(items)} files")
        continue
    code, out, err = g(["rm", "-r", d])
    if code == 0:
        print(f"  [OK] git rm -r {d}")
    else:
        print(f"  [INFO] {d}: {err[:100] if err else 'none'} (may already be removed)")

# 5) 02-Symptom 剩余目录
print()
print("=== 02-Symptom remaining dirs ===")
import os
symptom_dir = REPO / "02-Symptom"
if symptom_dir.exists():
    for d in sorted(symptom_dir.iterdir()):
        if d.is_dir():
            n = sum(1 for _ in d.rglob("*.md"))
            print(f"  {d.name}: {n} md")
