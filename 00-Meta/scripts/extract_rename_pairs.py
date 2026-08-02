"""从 git status --porcelain -z 提取所有 rename 对"""
import json
import subprocess
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

r = subprocess.run(
    ['git', 'status', '--porcelain', '-z'],
    capture_output=True,
    text=True,
    encoding='utf-8',
    cwd=str(REPO),
)
# 不用 split('\x00') 因为每个 rename 是 2 个 NUL 边界
# 改用 split 但排除空字符串，并跟踪 state
items = r.stdout.split('\x00')

pairs = []
i = 0
while i < len(items):
    it = items[i]
    if not it:
        i += 1
        continue
    if it.startswith('R ') or it.startswith('RM'):
        # 状态行 + 旧名（下一项）
        body = it[2:].strip()  # 去掉 R  和首空格
        new_name = body
        if i + 1 < len(items):
            old_name = items[i + 1]
            pairs.append({'old': old_name, 'new': new_name, 'state': it[:2].strip()})
            i += 2
            continue
    i += 1

# 写到 JSON
out = REPO / '00-Meta' / 'scripts' / '_rename_pairs.json'
out.write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'[SAVED] {len(pairs)} rename pairs to {out}')

# 抽样本
for p in pairs[:3]:
    print(f'  [{p["state"]}] {p["old"]} -> {p["new"]}')
print('  ...')
for p in pairs[-3:]:
    print(f'  [{p["state"]}] {p["old"]} -> {p["new"]}')

# 按源目录分组
from collections import Counter
src_dirs = Counter()
for p in pairs:
    parts = p['old'].split('/')
    if len(parts) > 2:
        src_dirs[parts[0] + '/' + parts[1]] += 1
    else:
        src_dirs[parts[0]] += 1
print('\n[源目录分布 TOP]')
for d, n in src_dirs.most_common(10):
    print(f'  {n:4d}  {d}')
