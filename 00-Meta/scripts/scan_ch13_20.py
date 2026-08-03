"""看 13/20 章目录树"""
from pathlib import Path
import os

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

for ch in ['13-进程与生命周期', '20-ART 运行时']:
    p = REPO / '03-卷3-核心机制' / ch
    print(f'\n=== {ch} ===')
    if not p.exists():
        print('  MISSING')
        continue
    for root, dirs, files in os.walk(p):
        rel = Path(root).relative_to(p)
        depth = len(rel.parts) - 1
        if depth > 2:
            continue
        indent = '  ' * depth
        md_files = [f for f in files if f.endswith('.md')]
        print(f'{indent}[{rel}] ({len(md_files)} .md, {len(dirs)} subdirs)')
        if depth == 1:
            for f in sorted(md_files)[:30]:
                print(f'{indent}  F {f[:80]}')
            if len(md_files) > 30:
                print(f'{indent}  ... +{len(md_files)-30} more')
