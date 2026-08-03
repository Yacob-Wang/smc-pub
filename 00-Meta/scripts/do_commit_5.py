"""Commit 5: 删除 8 卷迁移的旧路径（01-Mechanism/、02-Symptom/、03-Forensics/、04-Tool/、05-Governance/、06-Case/、06-Foundation/）"""
import subprocess
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

# unstage
subprocess.run(['git', 'reset', 'HEAD'], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')

# add 旧路径（让 git 知道删除）
OLD_DIRS = [
    '01-Mechanism',
    '02-Symptom',
    '03-Forensics',
    '04-Tool',
    '05-Governance',
    '06-Case',
    '06-Foundation',
]

for d in OLD_DIRS:
    r = subprocess.run(['git', 'add', '-A', '--', d], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
    print(f'  [add] {d}: rc={r.returncode}')

# commit
msg = '''chore(repo): 删除 8 卷迁移后的旧 module 残留

v1+卷 3+卷 4-8 迁移把 01-Mechanism/、02-Symptom/、03-Forensics/、04-Tool/、05-Governance/、06-Case/、06-Foundation/ 下
的 481 个文件全部 → 03-卷3-核心机制/、04-卷4-...、05-卷5-...、06-卷6-...、07-卷7-...、08-卷8-... 等 8 卷结构。

本 commit 清理 8 卷迁移后的旧 module 残留（working tree 中已删除的文件）：
- 01-Mechanism/ 全部清空
- 02-Symptom/ 部分残留（S11-Startup 之前已迁到 02-卷2-系统启动/11-启动性能专项/）
- 03-Forensics/ 全部清空
- 04-Tool/ 全部清空
- 05-Governance/ 全部清空
- 06-Case/ 全部清空
- 06-Foundation/ 全部清空

旧 module 全部从 git 跟踪移除。docs/ 下的副本由 prepare_web_docs.py 同步处理
（仍保留旧 module 让 mkdocs 看到完整内容），下一阶段清理。
'''

r = subprocess.run(['git', 'commit', '-m', msg], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
print(f'\n  [commit] rc={r.returncode}')
if r.stdout:
    print(f'  stdout: {r.stdout[:1000]}')
if r.stderr:
    print(f'  stderr: {r.stderr[:500]}')

# 看 remaining
r = subprocess.run(['git', 'status', '--short', '-z'], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
items = r.stdout.split('\x00')
from collections import Counter
stages = Counter()
for it in items:
    if not it: continue
    stages[it[:2]] += 1
print(f'\n[remaining]')
for s, n in sorted(stages.items()):
    print(f'  {s}: {n}')
