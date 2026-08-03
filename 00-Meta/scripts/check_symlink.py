from pathlib import Path
import os
REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')
# 看 02-Symptom 是 symlink 还是两个独立目录
p_root = REPO / '02-Symptom'
p_docs = REPO / 'docs' / '02-Symptom'
print(f'  root 02-Symptom is_symlink: {p_root.is_symlink()}')
print(f'  docs 02-Symptom is_symlink: {p_docs.is_symlink()}')
if p_root.is_symlink():
    print(f'  root -> {os.readlink(p_root)}')
print(f'  root stat: {p_root.stat()}')
print(f'  docs stat: {p_docs.stat()}')
# 列出 root 02-Symptom 内容
print()
print('  root 02-Symptom contents:')
for c in sorted(p_root.iterdir())[:20]:
    print(f'    {c.name}')
