"""Commit 1: A 阶段链接修复 v1 - 22 M + 2 D"""
import subprocess
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

# 22 M + 2 D - 在 00-Meta/ + 01-卷1/ + 03-Forensics/ + 04-Tool/ + 05-Governance/ + 06-Case/ + 06-Foundation/
# 不含 02-卷2/ 03-卷3/ 04-卷4/ 05-卷5/ 06-卷6/ 07-卷7/ 08-卷8/ (那些留给后续 commit)

DIRS_COMMIT_1 = [
    '00-Meta',
    '01-卷1-Android系统基础与平台',
    '03-Forensics',
    '04-Tool',
    '05-Governance',
    '06-Case',
    '06-Foundation',
]

# 1. git add 路径
for d in DIRS_COMMIT_1:
    result = subprocess.run(
        ['git', 'add', '-A', '--', d],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    print(f'  [add] {d}: rc={result.returncode}')

# 2. 看 staged 状态
result = subprocess.run(
    ['git', 'status', '--short'],
    cwd=str(REPO),
    capture_output=True,
    text=True,
    encoding='utf-8',
)
lines = [l for l in result.stdout.splitlines() if l and not l.startswith('??') and not l.startswith(' R') and not l.startswith(' RM')]
print(f'\n  [staged] {len(lines)} entries (first 5):')
for l in lines[:5]:
    print(f'    {l}')

# 3. git commit
msg = '''fix(book): v1 链接修复 - 22 文件 80 替换

- 22 处旧路径 02-Symptom/S11-Startup/  -> 02-卷2-系统启动/（多档深度补 ../）
- 12 处旧路径 06-Foundation/{Build-System,SELinux,Dynamic-Updates}/
  -> 01-卷1-Android系统基础与平台/{02,05}/
- 1 处 02-Symptom/S08-AOSP17-K618/  -> 01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17/
- 清理 2 个临时脚本（commit_migrate_v1v2.py、rm-cmd.txt）

v1v2 重跑 0 替换 — v1 已修完所有可修，剩 557 个 broken link 全是历史拼写错
（如 ../Stability/S01-ANR.md、../Kernel/FS/），与本次迁移无关。'''

result = subprocess.run(
    ['git', 'commit', '-m', msg],
    cwd=str(REPO),
    capture_output=True,
    text=True,
    encoding='utf-8',
)
print(f'\n  [commit] rc={result.returncode}')
print(f'  stdout: {result.stdout[:500]}')
if result.stderr:
    print(f'  stderr: {result.stderr[:500]}')
