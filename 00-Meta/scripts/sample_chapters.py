"""看每章第 1 个文件路径"""
import json
from pathlib import Path
REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')
data = json.loads((REPO / '00-Meta' / 'scripts' / '_ch_22_50_files.json').read_text(encoding='utf-8'))
for ch, info in data.items():
    if info['files']:
        first = info['files'][0]
        print(f'  ch{ch}: {first}')
