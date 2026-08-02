"""v3 链接修复：处理 415 个 rename 对造成的所有深度的内部断链。
基于 regex (?:\.\./)* 模式一次性覆盖所有 src 深度。
"""
import json
import re
import os
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

# 1. 加载 rename pairs
pairs = json.loads((REPO / '00-Meta' / 'scripts' / '_rename_pairs.json').read_text(encoding='utf-8'))
print(f'[LOADED] {len(pairs)} rename pairs')

# 2. 构造 regex 模式
# 对每个 (old, new) 对，regex = (../)* + old
# 替换为 ../(n+1) + new
# 按 old 长度倒序（先匹配长的，避免短路径匹配到长路径的前缀）
pairs_sorted = sorted(pairs, key=lambda p: -len(p['old']))

# 编译一个大 regex
escaped = []
for p in pairs_sorted:
    # regex 转义
    old = re.escape(p['old'])
    pattern = rf'(?:\.\./)*{old}'
    escaped.append((pattern, p['new']))

# 合并到一个 regex（用命名函数实现）
def make_replacer(new_name: str):
    def repl(m):
        n = m.group(0).count('../')  # 原始 ../ 数量
        new_dot = '../' * (n + 1)     # 加一档（因为 src 深度少一档）
        return new_dot + new_name
    return repl

# 3. 扫描所有 md 文件
exclude_prefixes = [
    '00-Meta/overrides', '00-Meta/reader', '00-Meta/web',
    'docs', 'site', '_archive',  # docs/ 由 mkdocs 自己处理
]

all_md = []
for p in REPO.rglob('*.md'):
    rel = p.relative_to(REPO).as_posix()
    if any(rel.startswith(d) for d in exclude_prefixes):
        continue
    all_md.append(p)
print(f'[TARGET] {len(all_md)} md files')

# 4. 修复
total_files = 0
total_replacements = 0
sample_changes = []

for p in all_md:
    try:
        text = p.read_text(encoding='utf-8')
    except Exception:
        continue
    original = text
    file_count = 0
    for pattern_str, new_name in escaped:
        # 每次重新 compile 保持单次扫描
        new_text, n = re.subn(
            pattern_str,
            make_replacer(new_name),
            text,
        )
        if n > 0:
            text = new_text
            file_count += n
    if text != original:
        p.write_text(text, encoding='utf-8')
        total_files += 1
        total_replacements += file_count
        if len(sample_changes) < 10:
            sample_changes.append((p.relative_to(REPO), file_count))

print(f'\n[OK] changed {total_files} files, {total_replacements} replacements')

print('\n[Sample changes]')
for f, n in sample_changes:
    print(f'  {n:4d}  {f}')
