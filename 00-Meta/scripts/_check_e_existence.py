# -*- coding: utf-8 -*-
"""核查 E 级清单 44 个文件实际存在情况 + 按 size/AOSP 分类"""
import os
import re

LIST_PATH = "00-Meta/拟删除清单-v1.md"

# 解析 markdown 表格里的路径
files = []
with open(LIST_PATH, "r", encoding="utf-8") as f:
    in_table = False
    for line in f:
        if "| #" in line and "字数" in line:
            in_table = True
            continue
        if in_table and re.match(r"^\|---", line.strip()):
            continue
        if in_table and line.startswith("| "):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 5 and cells[0].isdigit():
                path = cells[4].strip().strip("`")
                files.append(path)
        if in_table and line.strip() == "":
            in_table = False

print(f"清单总数：{len(files)}")

# 分类
existed = []
missing = []
short_or_old = []
need_rewrite = []
need_eval = []

for p in files:
    if not os.path.exists(p):
        missing.append(p)
        continue
    existed.append(p)
    size = os.path.getsize(p)
    # 读前 3KB 找 AOSP 版本
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(3000)
    except Exception:
        content = ""
    # 判断 AOSP 版本
    aosp = None
    for v in ["AOSP 12", "AOSP 13", "AOSP 14", "AOSP 15", "AOSP 4", "android-12", "android-13", "android-14"]:
        if v in content:
            aosp = v
            break
    if size < 3500:
        short_or_old.append((p, size, aosp))
    elif aosp in ("AOSP 12", "AOSP 13", "AOSP 4", "android-12", "android-13"):
        need_rewrite.append((p, size, aosp))
    else:
        need_eval.append((p, size, aosp))

print(f"实际存在：{len(existed)}")
print(f"已不存在（误删/已迁）: {len(missing)}")
print()
print("=" * 70)
print("【阶段 1 - 立即删】(< 1000 字 / 极短)")
print("=" * 70)
for p, s, a in short_or_old:
    print(f"  [{s:>5} B] {p}")
print(f"小计: {len(short_or_old)} 篇")
print()
print("=" * 70)
print("【阶段 2 - 重写】(3000+ 字 + AOSP 12-13)")
print("=" * 70)
for p, s, a in need_rewrite:
    print(f"  [{s:>6} B] {a}] {p}")
print(f"小计: {len(need_rewrite)} 篇")
print()
print("=" * 70)
print("【阶段 3 - 评估】(1000-3000 字 简短)")
print("=" * 70)
for p, s, a in need_eval:
    print(f"  [{s:>5} B] {p}")
print(f"小计: {len(need_eval)} 篇")
print()
print("=" * 70)
print("【已不存在的】（清单残留 / 已迁）:")
print("=" * 70)
for p in missing:
    print(f"  - {p}")
print(f"小计: {len(missing)} 篇")
