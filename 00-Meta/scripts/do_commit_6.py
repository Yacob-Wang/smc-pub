"""Commit 6: 4 M (v1 链接修复漏的 02-卷2-系统启动/) + 9 调试脚本"""
import subprocess
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

# unstage
subprocess.run(['git', 'reset', 'HEAD'], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')

# add 4 M
PATHS = [
    '02-卷2-系统启动/10-应用启动与首帧/A01-启动链路总览.md',
    '02-卷2-系统启动/10-应用启动与首帧/A02-Bootloader到Kernel.md',
    '02-卷2-系统启动/10-应用启动与首帧/A03-Init进程与init.rc.md',
    '02-卷2-系统启动/README.md',
]
for p in PATHS:
    r = subprocess.run(['git', 'add', '--', p], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
    print(f'  [add] {p}: rc={r.returncode}')

# add 9 调试脚本
SCRIPTS = [
    '00-Meta/scripts/check_R_format.py',
    '00-Meta/scripts/check_locs.py',
    '00-Meta/scripts/check_symlink.py',
    '00-Meta/scripts/classify_changes.py',
    '00-Meta/scripts/do_commit_1.py',
    '00-Meta/scripts/do_commit_5.py',
    '00-Meta/scripts/do_commits_4.py',
    '00-Meta/scripts/find_public_modules.py',
    '00-Meta/scripts/sample_chapters.py',
]
for p in SCRIPTS:
    r = subprocess.run(['git', 'add', '--', p], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
    print(f'  [add] {p}: rc={r.returncode}')

# commit
msg = '''fix(book): v1 链接修复补漏 + 调试辅助脚本

## v1 链接修复补漏（4 M）
commit 1 (v1 链接修复) 漏了 02-卷2-系统启动/ 下 4 个 M 文件：
- 02-卷2-系统启动/10-应用启动与首帧/A01-启动链路总览.md
- 02-卷2-系统启动/10-应用启动与首帧/A02-Bootloader到Kernel.md
- 02-卷2-系统启动/10-应用启动与首帧/A03-Init进程与init.rc.md
- 02-卷2-系统启动/README.md

链接修复内容：从 02-Symptom/S11-Startup/ 旧路径替换为卷 2 新路径
（v1 跑了 link_repair_v1v2.py 但当时未 commit）

## 调试辅助脚本（9 ??）
v3 链接修复和迁移过程中产生的辅助调试脚本：
- check_R_format.py      检查 git status R 行格式
- check_locs.py          检查 02-Symptom 实际位置（根 vs docs/）
- check_symlink.py       检查 02-Symptom 是否 symlink
- classify_changes.py    按目录分类 v1/v3 改的文件
- do_commit_1.py         第 1 次 commit 准备（已用过）
- do_commit_5.py         commit 5 (删除旧 module) 准备
- do_commits_4.py        4 个精细 commit 准备
- find_public_modules.py 找 PUBLIC_MODULES 定义位置
- sample_chapters.py     抽样看每章文件路径

保留这些脚本以备后用，可视情况删除。
'''

r = subprocess.run(['git', 'commit', '-m', msg], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
print(f'\n  [commit] rc={r.returncode}')
if r.stdout:
    print(f'  stdout: {r.stdout[:500]}')
if r.stderr:
    print(f'  stderr: {r.stderr[:300]}')

# remaining
r = subprocess.run(['git', 'status', '--short'], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
remaining = [l for l in r.stdout.splitlines() if l]
print(f'\n[remaining] {len(remaining)} entries')
for l in remaining[:30]:
    print(f'  {l}')
