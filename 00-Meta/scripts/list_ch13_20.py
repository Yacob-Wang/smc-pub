"""列 13/20 章所有 .md 文件"""
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

for ch in ['13-进程与生命周期', '20-ART 运行时']:
    p = REPO / '03-卷3-核心机制' / ch
    print(f'\n=== {ch} ({len(list(p.glob("*.md")))} files) ===')
    for f in sorted(p.glob('*.md')):
        print(f'  {f.name[:80]}')
