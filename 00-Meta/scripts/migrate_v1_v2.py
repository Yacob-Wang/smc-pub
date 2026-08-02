"""
migrate_v1_v2.py - C 第 1 批：卷 1 + 卷 2 物理迁移
用 git mv 保持 git rename detection
不修内部链接（下次）
不改 build 配置（下次）
"""
import subprocess
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")


def g(args: list[str], check=True) -> tuple[int, str]:
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=REPO_ROOT)
    if r.returncode != 0 and check:
        print(f"[FAIL] git {' '.join(args)}")
        print(f"  stderr: {r.stderr.strip()}")
    return r.returncode, r.stdout


def gmv(src_rel: str, dst_rel: str, dry_run: bool = False) -> None:
    """git mv with relative paths."""
    src = REPO_ROOT / src_rel
    dst = REPO_ROOT / dst_rel
    if not src.exists():
        print(f"  [SKIP] {src_rel} (not found)")
        return
    if dry_run:
        # Check for name conflicts
        if dst.exists():
            print(f"  [CONFLICT] {dst_rel} already exists")
        else:
            print(f"  [OK] {src_rel} -> {dst_rel}")
        return
    if dst.exists():
        print(f"  [CONFLICT] {dst_rel} already exists, skipping")
        return
    code, out = g(["mv", src_rel, dst_rel], check=False)
    if code == 0:
        print(f"  [OK] {src_rel} -> {dst_rel}")
    else:
        print(f"  [FAIL] {src_rel} -> {dst_rel}: {out.strip()}")


# ========== 迁移计划 ==========
# 卷 1 第 1 章 Android 系统全景与 AOSP 17
print("=" * 60)
print("Volume 1 / Chapter 1: Android 系统全景与 AOSP 17")
print("=" * 60)
gmv("02-Symptom/S08-AOSP17-K618/01-症状机制.md",
     "01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17/AOSP-17-与-Linux-6.18-入门.md")

# 卷 1 第 2 章 AOSP 源码结构与构建系统
print()
print("=" * 60)
print("Volume 1 / Chapter 2: AOSP 源码结构与构建系统")
print("=" * 60)
import os
build_src = REPO_ROOT / "06-Foundation/Build-System"
build_dst = REPO_ROOT / "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统"
build_dst.mkdir(parents=True, exist_ok=True)
for f in build_src.rglob("*.md"):
    rel = f.relative_to(build_src)
    gmv(str(f.relative_to(REPO_ROOT)),
         str(build_dst / rel).replace(str(REPO_ROOT) + os.sep, ""))

# 卷 1 第 5 章 安全基础（SELinux / AVB）
print()
print("=" * 60)
print("Volume 1 / Chapter 5: 安全基础 (SELinux / AVB)")
print("=" * 60)
sec_dst = REPO_ROOT / "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）"
sec_dst.mkdir(parents=True, exist_ok=True)
for src_name, sub in [("06-Foundation/SELinux", "SELinux"),
                       ("06-Foundation/Dynamic-Updates", "Dynamic-Updates")]:
    src_dir = REPO_ROOT / src_name
    if not src_dir.exists():
        continue
    for f in src_dir.rglob("*.md"):
        rel = f.relative_to(src_dir)
        gmv(str(f.relative_to(REPO_ROOT)),
             str(sec_dst / sub / rel).replace(str(REPO_ROOT) + os.sep, ""))

# 卷 2 第 10 章 应用启动与首帧
print()
print("=" * 60)
print("Volume 2 / Chapter 10: 应用启动与首帧")
print("=" * 60)
ch10_dst = REPO_ROOT / "02-卷2-系统启动/10-应用启动与首帧"
ch10_dst.mkdir(parents=True, exist_ok=True)
# A-启动机制
a_src = REPO_ROOT / "02-Symptom/S11-Startup/A-启动机制"
if a_src.exists():
    for f in a_src.iterdir():
        if f.is_file() and f.suffix == ".md":
            gmv(str(f.relative_to(REPO_ROOT)),
                 str(ch10_dst / f.name).replace(str(REPO_ROOT) + os.sep, ""))
# Old
old_src = REPO_ROOT / "02-Symptom/S11-Startup/Old"
old_dst = ch10_dst / "Old"
if old_src.exists():
    old_dst.mkdir(parents=True, exist_ok=True)
    for f in old_src.iterdir():
        if f.is_file() and f.suffix == ".md":
            gmv(str(f.relative_to(REPO_ROOT)),
                 str(old_dst / f.name).replace(str(REPO_ROOT) + os.sep, ""))

# 卷 2 第 11 章 启动性能专项
print()
print("=" * 60)
print("Volume 2 / Chapter 11: 启动性能专项")
print("=" * 60)
ch11_dst = REPO_ROOT / "02-卷2-系统启动/11-启动性能专项"
ch11_dst.mkdir(parents=True, exist_ok=True)
for src_name in ["02-Symptom/S11-Startup/B-启动性能",
                 "02-Symptom/S11-Startup/C-启动稳定性",
                 "02-Symptom/S11-Startup/D-启动工具"]:
    src_dir = REPO_ROOT / src_name
    if not src_dir.exists():
        continue
    prefix = src_name.split("/")[-1]  # B-启动性能 etc
    sub_dst = ch11_dst / prefix
    sub_dst.mkdir(parents=True, exist_ok=True)
    for f in src_dir.iterdir():
        if f.is_file() and f.suffix == ".md":
            gmv(str(f.relative_to(REPO_ROOT)),
                 str(sub_dst / f.name).replace(str(REPO_ROOT) + os.sep, ""))

# 清扫空目录
print()
print("=" * 60)
print("Cleanup empty source directories")
print("=" * 60)
empty_to_clean = [
    "02-Symptom/S08-AOSP17-K618",
    "02-Symptom/S11-Startup",
    "06-Foundation/Build-System",
    "06-Foundation/SELinux",
    "06-Foundation/Dynamic-Updates",
]
for d in empty_to_clean:
    full = REPO_ROOT / d
    if not full.exists():
        continue
    items = list(full.rglob("*"))
    items = [x for x in items if x.is_file()]
    if not items:
        # Use git rm to remove the empty directory
        code, out = g(["rm", "-r", d], check=False)
        if code == 0:
            print(f"  [OK] removed empty dir: {d}")
    else:
        print(f"  [SKIP] {d} has {len(items)} remaining files (not empty)")

print()
print("Done. Run 'git status --short' to see all changes.")
