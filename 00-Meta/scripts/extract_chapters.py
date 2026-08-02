"""从映射表提取第 22-50 章的所有文件路径。"""
import re
from pathlib import Path
import json

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')
p = REPO / '00-Meta' / '章节-素材映射表-v1.md'
text = p.read_text(encoding='utf-8', errors='replace')

# 找每章
ch_pat = re.compile(r'##\s+第\s+(\d+)\s+章[^\n]+', re.MULTILINE)
matches = list(ch_pat.finditer(text))

result = {}
for i, m in enumerate(matches):
    ch = int(m.group(1))
    if ch < 22 or ch > 50:
        continue
    start = m.end()
    end = matches[i+1].start() if i+1 < len(matches) else len(text)
    chunk = text[start:end]
    # 提取文件路径
    files = re.findall(r'^\s*-\s+`([^`]+)`', chunk, re.MULTILINE)
    title_match = re.search(r'第\s+\d+\s+章[^\n]+', m.group())
    title = title_match.group() if title_match else ''
    result[ch] = {'title': title, 'files': files}

# 写到文件
out = REPO / '00-Meta' / 'scripts' / '_ch_22_50_files.json'
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'[SAVED] {out}')
print()
# 摘要
for ch in sorted(result.keys()):
    info = result[ch]
    print(f'  第 {ch} 章 ({len(info["files"])} 篇): {info["title"][:50]}')
