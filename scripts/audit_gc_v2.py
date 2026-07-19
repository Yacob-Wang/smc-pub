# GC v2 完整审计 - 含附录 / 含 0 旧稿残留
import os
import re

ROOT = r"C:\Users\deepLife\Documents\GitHub\smc-pub\01-Mechanism\Runtime\ART\03-GC系统"
SUBDIRS = [
    "01-基础理论", "02-Heap与分配器", "03-CMS-GC", "04-CC-GC",
    "05-Generational-CC", "06-Reference与Finalizer", "07-GC调度与触发",
    "08-GC与其他子系统", "09-GC诊断与治理",
]

# 1) 真正的"v1 旧稿标记段"是 v1 加的标记块（v2 升级版应删）
#    标志：含 "v1 旧稿标记" + 标题/分段 + 不是升级决策日志里的"删"字
#    简单判断：含 "v1 旧稿标记段" 字符串且后面没有"删"字

# 2) 列出所有正文和附录

total_main = 0
total_appendix = 0
total_size = 0

# 真正残留 v1 旧稿标记段的（应该没有）
v1_residual = []

# 详细分类
all_files_detail = []

for sub in SUBDIRS:
    sub_path = os.path.join(ROOT, sub)
    if not os.path.exists(sub_path):
        continue
    for root_dir, dirs, fnames in os.walk(sub_path):
        is_appendix = "\\appendix" in root_dir.lower() or "/appendix" in root_dir.lower()
        for fname in fnames:
            if not fname.endswith(".md"):
                continue
            full = os.path.join(root_dir, fname)
            size = os.path.getsize(full)
            total_size += size
            with open(full, "r", encoding="utf-8", errors="ignore") as fp:
                text = fp.read()
            has_v1 = "v1 旧稿标记" in text or "v1旧稿标记" in text
            has_v2 = "v2 升级" in text or "v2升级" in text
            is_v2_mark = "（v2 升级版）" in text or "(v2 升级版)" in text

            rel = os.path.relpath(full, ROOT)
            all_files_detail.append((rel, size, is_appendix, has_v1, has_v2, is_v2_mark))

            if is_appendix:
                total_appendix += 1
            else:
                total_main += 1
                if fname.lower() == "readme.md":
                    continue
                # 真正的"v1 旧稿标记段"残留判断：含 "v1 旧稿标记段" 且不含 "删"
                if "v1 旧稿标记段" in text and "删" not in text:
                    v1_residual.append(full)

# 加 10-ART17分代GC强化专章（直接是文件，不在子目录里）
extra_files = []
extra_path = os.path.join(ROOT, "10-ART17分代GC强化专章-v2.md")
if os.path.exists(extra_path) and os.path.isfile(extra_path):
    size = os.path.getsize(extra_path)
    total_size += size
    with open(extra_path, "r", encoding="utf-8", errors="ignore") as fp:
        text = fp.read()
    extra_files.append(("10-ART17分代GC强化专章-v2.md", size))

# 输出
out = []
out.append("==== GC v2 Complete Audit (with appendix) ====")
out.append(f"Total main files: {total_main}")
out.append(f"Total appendix files: {total_appendix}")
out.append(f"Total size: {round(total_size/1024, 1)} KB / {round(total_size/1024/1024, 2)} MB")
out.append(f"v1 mark段 REAL residual (含'v1 旧稿标记段'且不含'删'): {len(v1_residual)}")
out.append(f"Extra v2 chapter: {len(extra_files)}")
out.append("")
out.append("==== Per-file detail (main only) ====")
for rel, size, is_appendix, has_v1, has_v2, is_v2_mark in all_files_detail:
    if is_appendix or rel.endswith("README.md"):
        continue
    flag = ""
    if is_v2_mark:
        flag += " [v2标识]"
    if has_v2:
        flag += " [v2讨论]"
    if has_v1:
        flag += " [v1讨论]"
    out.append(f"  {rel} -> {round(size/1024, 1)} KB {flag}")

out.append("")
out.append("==== Extra v2 chapters ====")
for fname, size in extra_files:
    out.append(f"  {fname} -> {round(size/1024, 1)} KB")

out.append("")
out.append("==== v1 mark段 REAL residual (should be 0) ====")
for f in v1_residual:
    out.append(f"  {os.path.relpath(f, ROOT)}")

# 写文件
out_path = r"C:\Users\deepLife\Documents\GitHub\smc-pub\scripts\audit_out.txt"
with open(out_path, "w", encoding="utf-8") as fp:
    fp.write("\n".join(out))

print("Total main:", total_main)
print("Total appendix:", total_appendix)
print("Total size KB:", round(total_size/1024, 1))
print("v1 residual (real):", len(v1_residual))
print("Extra v2 chapters:", len(extra_files))
print("Wrote:", out_path)
