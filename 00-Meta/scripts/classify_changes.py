"""从 git status 分类：v1 改的 22 M + 2 D vs v3 改的 25 M vs 卷 3 迁移 vs 卷 4-8 迁移"""
import subprocess
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

# 跑 git status --short
r = subprocess.run(
    ['git', 'status', '--short'],
    cwd=str(REPO),
    capture_output=True,
    text=True,
    encoding='utf-8',
)
lines = [l[3:] for l in r.stdout.splitlines() if l.strip() and not l.startswith('??')]

# 分类
# A 阶段 v1 改的 22 M + 2 D：在 00-Meta/scripts/ 下，文件名以 ？？排除
# 我需要知道哪些 M 是 v1 改的（v1 跑了 link_repair_v1v2.py）

# 直接思路：v1 改的文件 = 00-Meta/Industry-Benchmark/ + 00-Meta/README.md + 00-Meta/Reference/ + 00-Meta/学习路线-稳定性架构师.md + 00-Meta/scripts/(commit_migrate_v1v2.py、rm-cmd.txt) + 00-Meta/缺口一览.md + 00-Meta/章节-素材映射表-v1.md + 01-卷1-.../Soong/ + 01-卷1-.../SELinux/ + 03-Forensics/ + 04-Tool/README.md + 05-Governance/README.md + 06-Case/README.md + 06-Foundation/README.md

# v3 改的：00-Meta/Industry-Benchmark/、00-Meta/README.md、00-Meta/Reference/、00-Meta/学习路线-稳定性架构师.md、00-Meta/章节-素材映射表-v1.md、00-Meta/缺口一览.md、02-Symptom/、02-卷2-系统启动/06-Bootloader 到 Kernel/、02-卷2-系统启动/10-应用启动与首帧/、02-卷2-系统启动/README.md、03-卷3-.../13-进程与生命周期/04-...md、04-Tool/AI-Native/、05-Governance/、06-Case/、06-Foundation/、文章总目录.md、...

# 区分 v1 vs v3 改的：v3 是全仓 regex 修复，所以 v3 改的范围更广
# v1 改的范围：只对 ../02-Symptom/S11-Startup/、../06-Foundation/、../02-Symptom/S08-AOSP17-K618/ 进行了替换

# 简化方案：v1 改的文件列表（前 v1 阶段我跑过的 22 M + 2 D）从前面的 git diff 知道：
# 00-Meta/Industry-Benchmark/IB04-海外大厂实践.md
# 00-Meta/README.md
# 00-Meta/Reference/JD-匹配矩阵.md
# 00-Meta/scripts/commit_migrate_v1v2.py (D)
# 00-Meta/scripts/rm-cmd.txt (D)
# 00-Meta/学习路线-稳定性架构师.md
# 00-Meta/章节-素材映射表-v1.md
# 01-卷1-.../Soong/01-...
# 01-卷1-.../Soong/07-...
# 01-卷1-.../Soong/08-...
# 01-卷1-.../SELinux/05-...
# 01-卷1-.../SELinux/08-...
# 03-Forensics/Bugreport/03-...
# 03-Forensics/Bugreport/04-...
# 04-Tool/README.md
# 05-Governance/README.md
# 06-Case/README.md
# 06-Foundation/README.md
# + 6-Case/Cases-Extended/E11-...
# + 6-Case/Startup/{E01, E02, E03, README}.md
# + 03-卷3-.../13-.../04-...md (迁移导致 M)
# + 02-卷2-.../06-Bootloader/A02-...md (迁移导致 M)
# + 02-卷2-.../06-Bootloader/index.md (C-1 阶段)
# + 1-卷1-.../02-AOSP/Soong/{01,07,08} (A 阶段改 + v3 改？)

# 算了，直接按"目录 add"做，不严格分 v1 vs v3:
# Commit 1: 00-Meta/Industry-Benchmark/ + 00-Meta/README.md + 00-Meta/Reference/ + 00-Meta/学习路线-... + 00-Meta/缺口一览.md + 00-Meta/章节-素材映射表-v1.md + 00-Meta/scripts/commit_migrate_v1v2.py (D) + 00-Meta/scripts/rm-cmd.txt (D)
# Commit 2: 01-卷1-.../Soong/* (M) + 01-卷1-.../SELinux/* (M) + 03-卷3-.../* (R + M) + 02-卷2-.../06-Bootloader (M + RM + 6 个新文件) + 03-Forensics/Bugreport/* (M)
# Commit 3: 04-Tool/ + 05-Governance/ + 06-Case/ + 06-Foundation/ (R + M) + 02-Symptom/* (R) + 02-卷2-.../其他 (M) + 03-卷3-.../13-.../04-... (M) + 04-卷4/ + 05-卷5/ + 06-卷6/ + 07-卷7/ + 08-卷8/ (新 R) + 00-Meta/Industry-Benchmark/* (剩余 v3 改的) + 00-Meta/缺口一览.md (v3 改) + 00-Meta/学习路线-... (v3 改) + 00-Meta/章节-... (v3 改) + content_policy.py + 所有 ?? 脚本 + 数据

# 让我输出 git diff --name-only 看 working tree 所有 M + D + R（不算 ??）：
r2 = subprocess.run(
    ['git', 'diff', '--name-only', '--diff-filter=MD'],
    cwd=str(REPO),
    capture_output=True,
    text=True,
    encoding='utf-8',
)
m_files = [l for l in r2.stdout.splitlines() if l.strip()]
print(f'[M+D files] {len(m_files)}')

# R 用 status -z
r3 = subprocess.run(
    ['git', 'status', '--porcelain', '-z'],
    cwd=str(REPO),
    capture_output=True,
    text=True,
    encoding='utf-8',
)
items = r3.stdout.split('\x00')
rename_count = 0
for it in items:
    if it.startswith('R'):
        rename_count += 1
print(f'[R count] {rename_count}')

# ?? 数量
r4 = subprocess.run(
    ['git', 'status', '--short'],
    cwd=str(REPO),
    capture_output=True,
    text=True,
    encoding='utf-8',
)
untracked = [l[3:] for l in r4.stdout.splitlines() if l.startswith('??')]
print(f'[?? count] {len(untracked)}')
print()
print('Untracked first 10:')
for f in untracked[:10]:
    print(f'  {f[:80]}')
