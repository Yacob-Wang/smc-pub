"""分析 build 报告里 unrecognized relative link 的来源 + 模式。"""
import re
from pathlib import Path
from collections import Counter

LOG = Path(r"C:\Users\deepLife\AppData\Local\Temp\mkdocs_build2.log")

text = LOG.read_text(encoding="utf-8", errors="replace")
print(f"[LOG SIZE] {len(text)} chars")

# 用 -A 0 + cut 到 WARNING 行
PATTERN = re.compile(r"WARNING -  Doc file '([^']+)' contains an unrecognized relative link '([^']+)'")
matches = PATTERN.findall(text)
print(f"[TOTAL] {len(matches)} bad links")

by_file = Counter()
by_link = Counter()
for f, link in matches:
    by_file[f] += 1
    by_link[link] += 1

print("\n[Top 30 SOURCE FILES with most bad links]")
for f, n in by_file.most_common(30):
    print(f"  {n:4d}  {f}")

print("\n[Top 40 BROKEN LINKS (full)]")
for link, n in by_link.most_common(40):
    print(f"  {n:4d}  {link}")
