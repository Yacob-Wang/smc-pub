"""看 01-Mechanism 目录结构。"""
from pathlib import Path
import os

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')
m = REPO / '01-Mechanism'

for root, dirs, files in os.walk(m):
    rel = Path(root).relative_to(REPO)
    depth = len(rel.parts) - 1
    if depth > 2:
        continue
    indent = '  ' * depth
    md_files = [f for f in files if f.endswith('.md')]
    print(f'{indent}[{rel}] ({len(md_files)} .md, {len(dirs)} subdirs)')
    if depth == 2:
        for f in sorted(md_files)[:30]:
            print(f'{indent}  F {f[:80]}')
        if len(md_files) > 30:
            print(f'{indent}  ... +{len(md_files)-30} more')
