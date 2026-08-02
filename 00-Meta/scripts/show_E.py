"""看 44 篇 E 级具体内容（按卷分布）"""
import json
from pathlib import Path
from collections import Counter, defaultdict

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')
data = json.loads((REPO / '00-Meta' / 'scripts' / '_quality_audit.json').read_text(encoding='utf-8'))

# 只看 E
e_files = [r for r in data if r['grade'] == 'E']
print(f'[E 级] {len(e_files)} 篇')

# 按卷
by_vol = defaultdict(list)
for r in e_files:
    vol = r['path'].split('/')[0]
    by_vol[vol].append(r)

for vol in sorted(by_vol):
    print(f'\n=== {vol} ({len(by_vol[vol])} 篇) ===')
    for r in sorted(by_vol[vol], key=lambda x: x['chars']):
        aosp_label = f'AOSP {r["aosp_major"]}' if r['aosp_major'] > 0 else '未检测'
        print(f'  {r["chars"]:6d} ch  {aosp_label:10s}  {r["path"]}')
