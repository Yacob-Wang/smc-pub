"""找全仓 md 文件名重复"""
import sys
from collections import defaultdict
from pathlib import Path

TARGET_DIRS = ['00-Meta', '01-Mechanism', '02-Symptom', '03-Forensics', '04-Tool', '05-Governance', '06-Case', '06-Foundation']
name_to_paths = defaultdict(list)
for mod in TARGET_DIRS:
    for fp in Path(mod).rglob('*.md'):
        stem = fp.stem
        if stem.lower() in ('readme', 'index'):
            continue
        if stem.startswith('README-'):
            continue
        name_to_paths[stem].append(str(fp))

with open('scripts/audit_dupes.txt', 'w', encoding='utf-8') as fh:
    for name, paths in name_to_paths.items():
        if len(paths) > 1:
            fh.write(f'\n=== {name}.md ({len(paths)} copies) ===\n')
            for p in paths:
                fh.write(f'  {p}\n')
print(f'Written: scripts/audit_dupes.txt')
