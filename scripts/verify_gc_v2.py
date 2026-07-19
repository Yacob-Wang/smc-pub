# GC v2 升级终态验证脚本 (Python UTF-8 编码)
import os
import re

ROOT = r"C:\Users\deepLife\Documents\GitHub\smc-pub\01-Mechanism\Runtime\ART\03-GC系统"
SUBDIRS = [
    "01-基础理论", "02-Heap与分配器", "03-CMS-GC", "04-CC-GC",
    "05-Generational-CC", "06-Reference与Finalizer", "07-GC调度与触发",
    "08-GC与其他子系统", "09-GC诊断与治理",
]

print("==== GC v2 升级终态验证 ====")
print(f"目标根目录: {ROOT}")
print()

total_count = 0
total_size = 0
v1_mark_count = 0
v2_upgrade_count = 0

# 收集 v2 升级标识命中但不包含 "6.18" 的文件
no_618_files = []
# 收集没有 4 附录的文件
no_appendix_files = []
# 收集没有决策日志的文件
no_decision_files = []

for sub in SUBDIRS:
    sub_path = os.path.join(ROOT, sub)
    if not os.path.exists(sub_path):
        print(f"[!] 目录不存在: {sub_path}")
        continue
    files = []
    for root, dirs, fnames in os.walk(sub_path):
        for fname in fnames:
            if not fname.endswith(".md"):
                continue
            full = os.path.join(root, fname)
            if "appendix" in full.lower() or "\\appendix" in full or "/appendix" in full:
                continue
            if fname.lower() == "readme.md":
                continue
            files.append(full)
    sub_count = len(files)
    sub_size = sum(os.path.getsize(f) for f in files)
    total_count += sub_count
    total_size += sub_size

    sub_v1 = 0
    sub_v2 = 0
    for f in files:
        with open(f, "r", encoding="utf-8", errors="ignore") as fp:
            text = fp.read()
        if "v1 旧稿标记" in text or "v1旧稿标记" in text:
            sub_v1 += 1
        if "v2 升级" in text or "v2升级" in text:
            sub_v2 += 1
        # 检查 6.18 基线
        if "6.18" not in text:
            no_618_files.append(f)
        # 检查附录
        if "附录 A" not in text and "附录B" not in text and "附录 B" not in text and "附录C" not in text and "附录 C" not in text and "附录D" not in text and "附录 D" not in text:
            no_appendix_files.append(f)
        # 检查决策日志
        if "决策日志" not in text and "校准决策" not in text:
            no_decision_files.append(f)

    v1_mark_count += sub_v1
    v2_upgrade_count += sub_v2
    size_kb = round(sub_size / 1024, 1)
    print(f"{sub} -> {sub_count} 篇 / {size_kb} KB  (v1旧稿标记={sub_v1}  v2升级={sub_v2})")

print()
print("==== 汇总 ====")
total_kb = round(total_size / 1024, 1)
total_mb = round(total_size / 1024 / 1024, 2)
print(f"GC 系列总文件数: {total_count} 篇 (期望 99)")
print(f"GC 系列总大小: {total_kb} KB / {total_mb} MB")
print(f"v1 旧稿标记段残留: {v1_mark_count} 篇 (期望 0)")
print(f"v2 升级标识: {v2_upgrade_count} 篇 (期望 99)")
print(f"未含 '6.18' 基线: {len(no_618_files)} 篇")
print(f"未含 4 附录标记: {len(no_appendix_files)} 篇")
print(f"未含决策日志: {len(no_decision_files)} 篇")

if no_618_files:
    print()
    print("==== 未含 6.18 基线文件列表 ====")
    for f in no_618_files[:30]:
        print(f"  - {os.path.relpath(f, ROOT)}")
    if len(no_618_files) > 30:
        print(f"  ... 共 {len(no_618_files)} 个")

if no_appendix_files:
    print()
    print("==== 未含 4 附录文件列表 ====")
    for f in no_appendix_files[:30]:
        print(f"  - {os.path.relpath(f, ROOT)}")
    if len(no_appendix_files) > 30:
        print(f"  ... 共 {len(no_appendix_files)} 个")
