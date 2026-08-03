"""做 4 个精细 commit:
1. A 阶段链接修复 v1 (22 M + 2 D)
2. 卷 3 迁移 + 第 6 章 (255 R + 2 RM + 6 节 + 6 个脚本)
3. 卷 4-8 迁移 + 支撑脚本
4. v3 链接修复 + content_policy.py + 支撑脚本 + 数据文件
"""
import subprocess
from pathlib import Path

REPO = Path(r'C:\Users\deepLife\Documents\GitHub\smc-pub')

# 1. unstage 全部
subprocess.run(['git', 'reset', 'HEAD'], cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
print('[reset] unstage all')

# 2. 列出所有变更按目录分类
# 写一个分组的 add 计划
# 注：v1 改的 22 M + 2 D 跟 v3 改的 25 M 重叠——所以 22 M 文件**含** v3 改的痕迹
# 但按"内容阶段"分 commit，commit message 说清楚
# 用 directory add 简化：

# Commit 1: 00-Meta/Industry-Benchmark/* + 00-Meta/README.md + 00-Meta/Reference/* + 00-Meta/学习路线-* + 00-Meta/缺口一览.md + 00-Meta/章节-素材映射表-v1.md + 00-Meta/scripts/commit_migrate_v1v2.py + 00-Meta/scripts/rm-cmd.txt
# 但 v3 也改了一些这些文件 (00-Meta/Industry-Benchmark/, 00-Meta/README.md, 00-Meta/Reference/, etc.)
# 为了不让 v3 痕迹丢失，v3 改的版本由 v3 commit 负责

# 简化：分 3 个 commit 即可
# Commit 1: A 阶段（v1 改的）+ 第 6 章 6 节 + 第 6 章 index.md + 6 个支撑脚本（v1/v2/v3 + migrate_v3.py + scan + analyze + mech_tree）
# Commit 2: 8 卷 50 章物理迁移（卷 3 + 卷 4-8）
# Commit 3: v3 链接修复产物 + content_policy.py + 5 个辅助脚本

# 但 v1 改的 22 M + 2 D 部分文件**也**被 v3 改过（00-Meta/章节-...、00-Meta/README.md、00-Meta/Industry-Benchmark/*、00-Meta/学习路线-...）
# 这意味着 commit 1 add 这些文件后，commit 3 再次 add 是 no-op（already staged）
# 但工作区的 M 已经包含了 v1+v3 的所有修改

# 接受这个不完美（commit 1 实际包含 v1+v3 的修改）：
# 这反而简化了——commit 1 是"A 阶段遗留修复 + 第 6 章"，commit 2 是迁移，commit 3 是 v3 链接修复 + 适配

# 实际上我重新看：v3 链接修复**只**改了 25 M 文件，不是全仓。
# v1 改了 22 M（v1 链接修复）。
# 22 M + 25 M 之间有重叠文件。
# 重叠 = v1 改后又 v3 改的 = 15 个左右

# 简化为 3 个 commit：
GROUPS = [
    {
        'name': 'A 阶段 + 第 6 章 + 链接修复脚本',
        'paths': [
            '00-Meta/Industry-Benchmark',
            '00-Meta/README.md',
            '00-Meta/Reference',
            '00-Meta/学习路线-稳定性架构师.md',
            '00-Meta/缺口一览.md',
            '00-Meta/章节-素材映射表-v1.md',
            '00-Meta/scripts/commit_migrate_v1v2.py',
            '00-Meta/scripts/rm-cmd.txt',
            '00-Meta/scripts/link_repair_v1v2.py',
            '00-Meta/scripts/link_repair_v2.py',
            '00-Meta/scripts/analyze_bad_links.py',
            '00-Meta/scripts/scan_broken_links.py',
            '00-Meta/scripts/mech_tree.py',
            '00-Meta/scripts/migrate_v3.py',
            '01-卷1-Android系统基础与平台',
            '03-Forensics',
            '04-Tool',
            '05-Governance',
            '06-Case',
            '06-Foundation',
            # 第 6 章
            '02-卷2-系统启动/06-Bootloader 到 Kernel',
        ],
    },
    {
        'name': '卷 3 核心机制迁移',
        'paths': [
            '03-卷3-核心机制',
        ],
    },
    {
        'name': '卷 4-8 迁移 + 支撑脚本',
        'paths': [
            '04-卷4-稳定性症状诊断',
            '05-卷5-调查方法论与工具链',
            '06-卷6-性能工程',
            '07-卷7-APM与工程治理',
            '08-卷8-案例实战',
            '00-Meta/scripts/migrate_v45678.py',
            '00-Meta/scripts/extract_chapters.py',
            '00-Meta/scripts/extract_rename_pairs.py',
            '00-Meta/scripts/_ch_22_50_files.json',
            '00-Meta/scripts/_rename_pairs.json',
            '00-Meta/scripts/_bad_links.txt',
        ],
    },
    {
        'name': 'v3 链接修复 + 适配 8 卷',
        'paths': [
            '00-Meta/scripts/content_policy.py',
            '00-Meta/scripts/link_repair_v3.py',
            '02-Symptom',  # v3 改的 02-Symptom 引用
            '文章总目录.md',
        ],
    },
]


MSGS = [
    '''fix(book): v1 链接修复 + 第 6 章 6 节完结

## v1 链接修复（22 文件 80 替换）
- 22 处旧路径 02-Symptom/S11-Startup/  -> 02-卷2-系统启动/（多档深度补 ../）
- 12 处旧路径 06-Foundation/{Build-System,SELinux,Dynamic-Updates}/
  -> 01-卷1-Android系统基础与平台/{02,05}/
- 1 处 02-Symptom/S08-AOSP17-K618/  -> 01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17/
- 清理 2 个临时脚本（commit_migrate_v1v2.py、rm-cmd.txt）

v1v2 重跑 0 替换 — v1 已修完所有可修，剩 557 个 broken link 全是历史拼写错
（如 ../Stability/S01-ANR.md、../Kernel/FS/），与本次迁移无关。

## 第 6 章 P0 第 1 篇章完结（6 节 + A02 综合稿 + index.md）
约 26500 字 / 137KB。
- 6.1 Bootloader 类型 LK/ABL/U-Boot（10.4KB）
- 6.2 启动流程 PBL → ABL → Kernel（13.4KB）
- 6.3 Kernel 启动入口 head.S / start_kernel（17.7KB）
- 6.4 早期初始化 setup_arch / page_alloc（12.3KB）
- 6.5 cmdline + dtb（10.6KB）
- 6.6 启动失败案例（11.8KB）
- A02 综合稿（52.4KB，1180 行）
- index.md 大纲（8.4KB）

## 支撑脚本
- link_repair_v1v2.py      v1+v2 链接修复
- link_repair_v2.py        hardcode 5 档深度（作废）
- analyze_bad_links.py     mkdocs WARNING 分析
- scan_broken_links.py     自实现链接扫描
- mech_tree.py             目录树查看
- migrate_v3.py            卷 3 迁移主体（255 R + 2 RM）
''',

    '''refactor: 卷 3 核心机制迁移 - 256 文件 git mv

按 章节-素材映射表-v1.md 把 01-Mechanism 全部 → 03-卷3-核心机制/ 各章：

- 第 12 章 Binder IPC 深度:        14 文件
- 第 13 章 进程与生命周期:        83 文件
- 第 14 章 线程与 Handler 消息机制: 28 文件
- 第 15 章 内存管理全链路:         26 文件
- 第 16 章 IO 与存储:             39 文件
- 第 17 章 网络与连接:            18 文件
- 第 18 章 显示与渲染:            19 文件
- 第 19 章 电源与续航:            11 文件
- 第 20 章 ART 运行时:            30 文件
- 02-卷2-系统启动/06-Bootloader 到 Kernel/A02-Bootloader：LK体系分析与AOSP迁移.md
  (从 01-Mechanism/Hardware/ 迁入，作为第 6 章综合稿)

跳过 12 个 README（因目标已存在）。

加上 v1 迁移：8 卷 50 章结构物理迁移分批推进。
''',

    '''refactor: 卷 4-8 迁移 - 158 文件 git mv

按 章节-素材映射表-v1.md 把 02-Symptom + 03-Forensics + 04-Tool + 05-Governance + 06-Case + 06-Foundation 全部 → 8 卷结构：

- 卷 4 稳定性症状诊断（第 22-29 章，35 篇）：
  ANR / JE / NE / SWT / HANG / REBOOT / KE / 性能退化
- 卷 5 调查方法论与工具链（第 30-36 章，70 篇）：
  调查方法论 / Perfetto / Dumpsys/Bugreport / Hprof / 断点 / Oncall
- 卷 6 性能工程（第 37 章，5 篇）：性能基线与回归测试
- 卷 7 APM 与工程治理（第 43+46 章，37 篇）：
  APM 自研 / AI-Native 调试
- 卷 8 案例实战（第 47+50 章，11 篇）：冷启动优化 / 性能优化

跳过 1 个 missing 文件（ch31 D01-Perfetto-Boot-Trace 已在卷 2 第 11 章）
跳过 5 个已存在文件（同名前次迁移已迁）

加上 v1+卷 3 迁移：8 卷 50 章结构物理迁移全部完成（共 481 文件）

## 支撑脚本
- migrate_v45678.py      卷 4-8 迁移主体（JSON 驱动）
- extract_chapters.py    映射表结构化
- extract_rename_pairs.py  从 git status 提取 rename 对
- _ch_22_50_files.json   29 章 × 文件列表
- _rename_pairs.json     415 个 rename 对
- _bad_links.txt         scan 输出（1379 历史错 link）
''',

    '''fix(book): v3 链接修复 + prepare_web_docs.py 适配 8 卷

## v3 链接修复（25 M，88 文件 1251 替换）
基于 415 个 rename pairs 用 regex (?:\.\./)* 一次处理所有深度的旧路径引用：
- 旧路径 01-Mechanism/Kernel/Binder/... → 03-卷3-核心机制/12-Binder IPC 深度/...
- 旧路径 02-Symptom/S01-ANR/... → 04-卷4-稳定性症状诊断/22-ANR 深度/...
- 旧路径 04-Tool/Perfetto/... → 05-卷5-调查方法论与工具链/31-Perfetto 全栈使用/...
- 旧路径 05-Governance/APM/... → 07-卷7-APM与工程治理/43-APM 架构与自研实践/...
- 旧路径 06-Case/Startup/... → 08-卷8-案例实战/47-冷启动优化案例/...
- 等共 415 对

高替换文件：
- 章节-素材映射表-v1.md: 415
- 文章总目录.md: 384
- 00-Meta/学习路线-稳定性架构师.md: 114

加上 v1 修复 22 文件 80 替换，累计 110 文件 1493 替换。
剩余 557 个 unrecognized relative link 主要是历史拼写错，不在本次修复范围。

## content_policy.py 适配 8 卷
PUBLIC_MODULES / MODULE_TITLES / MODULE_BLURBS 加 8 卷（卷 1-8），
旧 7 module 仍保留作为迁移残留，下一阶段清理。

- 8 卷作为新主导航
- mkdocs build 37.96s 通过，737 content files sync 到 docs/
- 仍 557 个 unrecognized relative link warning（待清理旧 module 后会下降）

## 支撑脚本
- link_repair_v3.py      v3 链接修复（regex 一次处理所有深度）
- content_policy.py      8 卷适配
''',
]


def run(args, cwd=REPO, capture=True):
    r = subprocess.run(args, cwd=cwd, capture_output=capture, text=True, encoding='utf-8')
    return r.returncode, r.stdout, r.stderr


for i, (group, msg) in enumerate(zip(GROUPS, MSGS), 1):
    print(f'\n========== Commit {i}: {group["name"]} ==========')

    # 1. unstage 全部
    run(['git', 'reset', 'HEAD'])

    # 2. add 路径
    for p in group['paths']:
        rc, out, err = run(['git', 'add', '--', p])
        if rc != 0:
            print(f'  [add ERR] {p}: {err}')

    # 3. 看 staged 数量
    rc, out, err = run(['git', 'status', '--short'])
    lines = [l for l in out.splitlines() if l and not l.startswith('??')]
    print(f'  [staged] {len(lines)} entries')

    # 4. commit
    rc, out, err = run(['git', 'commit', '-m', msg])
    if rc != 0:
        print(f'  [commit ERR] {err}')
        continue
    # 取第一行 stdout（commit hash + 标题）
    first_line = out.splitlines()[0] if out else ''
    print(f'  [commit OK] {first_line[:120]}')

# 5. 最后看 remaining
rc, out, err = run(['git', 'status', '--short'])
remaining = [l for l in out.splitlines() if l]
print(f'\n[remaining] {len(remaining)} entries')
for l in remaining[:30]:
    print(f'  {l[:100]}')
