# GC v2 升级终态验证脚本 v2 - 详细诊断
import os
import re

ROOT = r"C:\Users\deepLife\Documents\GitHub\smc-pub\01-Mechanism\Runtime\ART\03-GC系统"
SUBDIRS = [
    "01-基础理论", "02-Heap与分配器", "03-CMS-GC", "04-CC-GC",
    "05-Generational-CC", "06-Reference与Finalizer", "07-GC调度与触发",
    "08-GC与其他子系统", "09-GC诊断与治理",
]

# 写 UTF-8 BOM 格式给 PowerShell 用
out_lines = []
out_lines.append("==== GC v2 Final Status Verification ====")
out_lines.append(f"Root: {ROOT}")
out_lines.append("")

total_count = 0
total_size = 0
v1_mark_count = 0
v2_upgrade_count = 0

no_618_files = []
no_appendix_files = []
no_decision_files = []
v1_v2_both = []  # 既含 v1 旧稿标记又含 v2 升级

for sub in SUBDIRS:
    sub_path = os.path.join(ROOT, sub)
    if not os.path.exists(sub_path):
        out_lines.append(f"[!] Directory missing: {sub_path}")
        continue
    files = []
    for root, dirs, fnames in os.walk(sub_path):
        for fname in fnames:
            if not fname.endswith(".md"):
                continue
            full = os.path.join(root, fname)
            if "appendix" in full.lower():
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
        has_v1 = ("v1 旧稿标记" in text) or ("v1旧稿标记" in text)
        has_v2 = ("v2 升级" in text) or ("v2升级" in text)
        if has_v1:
            sub_v1 += 1
        if has_v2:
            sub_v2 += 1
        if has_v1 and has_v2:
            v1_v2_both.append(f)
        if "6.18" not in text:
            no_618_files.append(f)
        if "附录 A" not in text and "附录B" not in text and "附录 B" not in text and "附录C" not in text and "附录 C" not in text and "附录D" not in text and "附录 D" not in text:
            no_appendix_files.append(f)
        if "决策日志" not in text and "校准决策" not in text:
            no_decision_files.append(f)

    v1_mark_count += sub_v1
    v2_upgrade_count += sub_v2
    size_kb = round(sub_size / 1024, 1)
    out_lines.append(f"  {sub}: {sub_count} files / {size_kb} KB  (v1_mark={sub_v1}  v2_upgrade={sub_v2})")

out_lines.append("")
out_lines.append("==== Summary ====")
total_kb = round(total_size / 1024, 1)
total_mb = round(total_size / 1024 / 1024, 2)
out_lines.append(f"Total GC files: {total_count} (expected 99)")
out_lines.append(f"Total size: {total_kb} KB / {total_mb} MB")
out_lines.append(f"v1 mark residual: {v1_mark_count} (expected 0)")
out_lines.append(f"v2 upgrade mark: {v2_upgrade_count} (expected 99)")
out_lines.append(f"Files BOTH v1 mark AND v2 upgrade: {len(v1_v2_both)} (SHOULD be 0)")
out_lines.append(f"Files without 6.18 baseline: {len(no_618_files)} (expected 0)")
out_lines.append(f"Files without 4-appendix: {len(no_appendix_files)} (expected 0)")
out_lines.append(f"Files without decision log: {len(no_decision_files)} (expected 0)")

out_lines.append("")
out_lines.append("==== Files BOTH v1_mark AND v2_upgrade (anomaly) ====")
for f in v1_v2_both[:10]:
    out_lines.append(f"  {os.path.relpath(f, ROOT)}")
if len(v1_v2_both) > 10:
    out_lines.append(f"  ... {len(v1_v2_both)} total")

# 检查 v1 旧稿标记段落位置（是开头还是中间）
out_lines.append("")
out_lines.append("==== v1 旧稿标记段位置检查（前 5 篇）====")
count = 0
for f in v1_v2_both[:5]:
    with open(f, "r", encoding="utf-8", errors="ignore") as fp:
        text = fp.read()
    idx = text.find("v1 旧稿标记")
    if idx < 0:
        idx = text.find("v1旧稿标记")
    if idx < 0:
        continue
    # 找出段落在文件中的位置比例
    total = len(text)
    rel = idx / total * 100 if total > 0 else 0
    # 段落开始的标题
    snippet = text[max(0,idx-30):idx+200]
    out_lines.append(f"  {os.path.relpath(f, ROOT)} - pos {rel:.1f}%")
    out_lines.append(f"    snippet: {snippet[:200].replace(chr(10),' / ')}")

# 写文件
out_path = r"C:\Users\deepLife\Documents\GitHub\smc-pub\scripts\verify_out.txt"
with open(out_path, "w", encoding="utf-8") as fp:
    fp.write("\n".join(out_lines))

# 直接 print 关键行（ASCII only 防止乱码）
print("Total GC files:", total_count, "(expected 99)")
print("Total size KB:", total_kb)
print("v1 mark residual:", v1_mark_count)
print("v2 upgrade mark:", v2_upgrade_count)
print("Files BOTH v1+v2:", len(v1_v2_both))
print("No 6.18:", len(no_618_files))
print("No appendix:", len(no_appendix_files))
print("No decision log:", len(no_decision_files))
print("Output written to:", out_path)
