#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
v2 (8卷50章) -> v3 (6卷56章) git mv 迁移脚本

来源：E:\smc-pub\_tmp\卷5-12章扩充规划-v3-6卷重组最终版.md §1.3 / §11.3
作者：Mavis · Stability Matrix Course
最后更新：2026-08-05

使用：
    cd E:\smc-pub
    python scripts/migrate_v2_to_v3.py --dry-run     # 演练，不动文件
    python scripts/migrate_v2_to_v3.py --migrate     # 真正 git mv
    python scripts/migrate_v2_to_v3.py --docs        # 同步 docs 镜像

依赖：Python 3.8+、git
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path("E:/smc-pub")

# 原章号 → 新章号 映射（按 v3 §1.3 路径映射）
CHAPTER_MAP = {
    # 原卷 1 (1-5) → 新卷 1 (1-5)
    "01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17": "01-卷1-平台基础与启动/01-系统全景与 AOSP 17",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统": "01-卷1-平台基础与启动/02-AOSP 源码结构与构建系统",
    "01-卷1-Android系统基础与平台/03-硬件抽象层（HAL）与 Treble 架构": "01-卷1-平台基础与启动/03-硬件抽象层（HAL）与 Treble 架构",
    "01-卷1-Android系统基础与平台/04-Linux Kernel 基础（Android 视角）": "01-卷1-平台基础与启动/04-Linux Kernel 基础（Android 视角）",
    "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）": "01-卷1-平台基础与启动/05-安全基础（SELinux · AVB）",
    # 原卷 2 (6-11) → 新卷 1 (6-11)
    "02-卷2-系统启动/06-Bootloader 到 Kernel": "01-卷1-平台基础与启动/06-Bootloader 到 Kernel",
    "02-卷2-系统启动/07-Init 进程与 init.rc": "01-卷1-平台基础与启动/07-Init 进程与 init.rc",
    "02-卷2-系统启动/08-Zygote 与 ART 启动": "01-卷1-平台基础与启动/08-Zygote 与 ART 启动",
    "02-卷2-系统启动/09-SystemServer 启动": "01-卷1-平台基础与启动/09-SystemServer 启动",
    "02-卷2-系统启动/10-应用启动与首帧": "01-卷1-平台基础与启动/10-应用启动与首帧",
    "02-卷2-系统启动/11-系统启动性能专项": "01-卷1-平台基础与启动/11-系统启动性能专项",
    # 原卷 3 (12-21) → 新卷 2 (12-21)
    "03-卷3-核心机制/12-Binder IPC 深度": "02-卷2-核心机制/12-Binder IPC 深度",
    "03-卷3-核心机制/13-进程与生命周期": "02-卷2-核心机制/13-进程与生命周期",
    "03-卷3-核心机制/14-线程与 Handler 消息机制": "02-卷2-核心机制/14-线程与 Handler 消息机制",
    "03-卷3-核心机制/15-内存管理全链路": "02-卷2-核心机制/15-内存管理全链路",
    "03-卷3-核心机制/16-IO 与存储": "02-卷2-核心机制/16-IO 与存储",
    "03-卷3-核心机制/17-网络与连接": "02-卷2-核心机制/17-网络与连接",
    "03-卷3-核心机制/18-输入系统": "02-卷2-核心机制/18-输入系统",
    "03-卷3-核心机制/19-显示与渲染": "02-卷2-核心机制/19-显示与渲染",
    "03-卷3-核心机制/20-ART 运行时": "02-卷2-核心机制/20-ART 运行时",
    "03-卷3-核心机制/21-电源与续航": "02-卷2-核心机制/21-电源与续航",
    # 原卷 5 (31-36) → 新卷 3 (22-27)
    "05-卷5-调查工具链/31-Perfetto 全栈使用": "03-卷3-调查工具（调试手段）/22-Perfetto 全栈使用",
    "05-卷5-调查工具链/32-Systrace 与 ftrace": "03-卷3-调查工具（调试手段）/23-Systrace 与 ftrace",
    "05-卷5-调查工具链/33-Dumpsys · Bugreport · DropBox": "03-卷3-调查工具（调试手段）/24-Dumpsys · Bugreport · DropBox",
    "05-卷5-调查工具链/34-Hprof 与内存分析": "03-卷3-调查工具（调试手段）/25-Hprof 与内存分析",
    "05-卷5-调查工具链/35-断点与 Native 调试": "03-卷3-调查工具（调试手段）/26-断点与 Native 调试",
    "05-卷5-调查工具链/36-Oncall 与应急响应": "03-卷3-调查工具（调试手段）/27-Oncall 与应急响应",
    # 原卷 4 (22-30) → 新卷 4 (34-42)
    "04-卷4-诊断方法论与稳定性症状/22-稳定性调查方法论": "04-卷4-稳定性症状/34-稳定性调查方法论",
    "04-卷4-诊断方法论与稳定性症状/23-ANR 深度": "04-卷4-稳定性症状/35-ANR 深度",
    "04-卷4-诊断方法论与稳定性症状/24-Java 异常": "04-卷4-稳定性症状/36-Java 异常",
    "04-卷4-诊断方法论与稳定性症状/25-Native 异常": "04-卷4-稳定性症状/37-Native 异常",
    "04-卷4-诊断方法论与稳定性症状/26-内存与 OOM": "04-卷4-稳定性症状/38-内存与 OOM",
    "04-卷4-诊断方法论与稳定性症状/27-系统无响应（SWT · Watchdog）": "04-卷4-稳定性症状/39-系统无响应（SWT · Watchdog）",
    "04-卷4-诊断方法论与稳定性症状/28-HANG 与死锁": "04-卷4-稳定性症状/40-HANG 与死锁",
    "04-卷4-诊断方法论与稳定性症状/29-Kernel Exception": "04-卷4-稳定性症状/41-Kernel Exception",
    "04-卷4-诊断方法论与稳定性症状/30-REBOOT": "04-卷4-稳定性症状/42-REBOOT",
    # 原卷 6 (37-41) → 新卷 5 (43-47)
    "06-卷6-性能工程/37-性能基线与回归防劣化": "05-卷5-性能工程与治理/43-性能基线与回归防劣化",
    "06-卷6-性能工程/38-应用启动性能": "05-卷5-性能工程与治理/44-应用启动性能",
    "06-卷6-性能工程/39-滑动与渲染性能": "05-卷5-性能工程与治理/45-滑动与渲染性能",
    "06-卷6-性能工程/40-低配机适配": "05-卷5-性能工程与治理/46-低配机适配",
    "06-卷6-性能工程/41-WebView 与 Hybrid 性能": "05-卷5-性能工程与治理/47-WebView 与 Hybrid 性能",
    # 原卷 7 (42-46) → 新卷 5 (48-52)
    "07-卷7-APM与工程治理/42-稳定性指标体系（SLI · SLO）": "05-卷5-性能工程与治理/48-稳定性指标体系（SLI · SLO）",
    "07-卷7-APM与工程治理/43-APM 架构与自研实践": "05-卷5-性能工程与治理/49-APM 架构与自研实践",
    "07-卷7-APM与工程治理/44-告警体系与降噪": "05-卷5-性能工程与治理/50-告警体系与降噪",
    "07-卷7-APM与工程治理/45-变更管理与灰度发布": "05-卷5-性能工程与治理/51-变更管理与灰度发布",
    "07-卷7-APM与工程治理/46-AI-Native 调试": "05-卷5-性能工程与治理/52-AI-Native 调试",
    # 原卷 8 (47-50) → 新卷 6 (53-56)
    "08-卷8-案例实战/47-启动性能案例": "06-卷6-案例实战/53-启动性能案例",
    "08-卷8-案例实战/48-ANR 与系统无响应案例": "06-卷6-案例实战/54-ANR 与系统无响应案例",
    "08-卷8-案例实战/49-崩溃与内存案例": "06-卷6-案例实战/55-崩溃与内存案例",
    "08-卷8-案例实战/50-性能与整机稳定性案例": "06-卷6-案例实战/56-性能与整机稳定性案例",
}


def check_pretable():
    """启动前自检 5 项（v3 §11.1）"""
    print("=" * 60)
    print("启动前自检 5 项")
    print("=" * 60)

    checks = []

    # 1. 仓库干净
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT, capture_output=True, text=True
    )
    if result.stdout.strip() == "":
        print("✅ 1. 仓库干净 (working tree clean)")
        checks.append(True)
    else:
        print(f"❌ 1. 仓库不干净:\n{result.stdout}")
        checks.append(False)

    # 2. ahead/behind
    subprocess.run(["git", "fetch", "origin"], cwd=ROOT, capture_output=True)
    result = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", "origin/master...master"],
        cwd=ROOT, capture_output=True, text=True
    )
    parts = result.stdout.strip().split()
    if len(parts) == 2 and parts[0] == "0":
        print(f"✅ 2. ahead=0 ({result.stdout.strip()})")
        checks.append(True)
    else:
        print(f"⚠️ 2. ahead={parts[0] if parts else '?'} (建议 push 后再迁)")
        checks.append(False)

    # 3. 大文件无未跟踪
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True
    )
    untracked_count = len([l for l in result.stdout.strip().split("\n") if l])
    if untracked_count == 0:
        print("✅ 3. 无未跟踪文件")
        checks.append(True)
    else:
        print(f"⚠️ 3. 有 {untracked_count} 个未跟踪文件")
        checks.append(False)

    # 4. v2 GA 切换记录
    v6_record = ROOT / "00-Meta" / "v6.0-GA-切换记录.md"
    if v6_record.exists():
        print("✅ 4. v6.0 GA 切换记录存在")
        checks.append(True)
    else:
        print("❌ 4. v6.0 GA 切换记录不存在")
        checks.append(False)

    # 5. 1h 内无并发 commit
    result = subprocess.run(
        ["git", "log", "--since=1 hour ago", "--oneline"],
        cwd=ROOT, capture_output=True, text=True
    )
    recent = [l for l in result.stdout.strip().split("\n") if l]
    if not recent:
        print("✅ 5. 1h 内无新 commit（无并发风险）")
        checks.append(True)
    else:
        print(f"⚠️ 5. 1h 内有 {len(recent)} 个 commit:\n{result.stdout}")
        checks.append(False)

    print("=" * 60)
    if all(checks):
        print("✅ 5/5 全过，可以进入备份阶段")
        return True
    else:
        print(f"❌ {sum(1 for c in checks if not c)} 项不通过，请先修复")
        return False


def do_backup():
    """备份策略：git worktree + tag（v3 §11.2）"""
    print("\n" + "=" * 60)
    print("备份阶段")
    print("=" * 60)

    from datetime import datetime
    date = datetime.now().strftime("%Y-%m-%d")
    worktree_path = ROOT / "_archive" / "snapshots" / f"{date}-v2-8卷50章-迁移前快照"
    tag_name = "v2-8卷50章-迁移前-基线"

    # 1. git worktree add
    print(f"\n[1/4] git worktree add → {worktree_path}")
    result = subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "master"],
        cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"✅ worktree 已建: {worktree_path}")
    elif "already exists" in result.stderr:
        print(f"⚠️ worktree 已存在，跳过")
    else:
        print(f"❌ {result.stderr}")
        return False

    # 2. git tag
    print(f"\n[2/4] git tag → {tag_name}")
    result = subprocess.run(
        ["git", "tag", "-a", tag_name, "master", "-m", "v2 8卷50章 迁移前最后基线"],
        cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"✅ tag 已建: {tag_name}")
    else:
        print(f"⚠️ {result.stderr}")

    # 3. git push tag
    print(f"\n[3/4] git push origin {tag_name}")
    result = subprocess.run(
        ["git", "push", "origin", tag_name],
        cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode == 0:
        print("✅ tag 已推 origin")
    else:
        print(f"⚠️ {result.stderr}")

    # 4. 验证
    print(f"\n[4/4] 验证")
    result = subprocess.run(["git", "worktree", "list"], cwd=ROOT, capture_output=True, text=True)
    print(result.stdout)
    result = subprocess.run(["git", "tag", "--list", tag_name], cwd=ROOT, capture_output=True, text=True)
    print(f"tag: {result.stdout.strip()}")
    worktree_exists = worktree_path.exists()
    print(f"snapshot 存在: {worktree_exists}")

    return worktree_exists


def do_migrate(dry_run=False):
    """迁移主目录（v3 §11.4 步骤 4）"""
    print("\n" + "=" * 60)
    print(f"主目录迁移 {'（演练 dry-run）' if dry_run else '（执行）'}")
    print("=" * 60)

    moved = 0
    failed = []
    skipped = []

    for old, new in CHAPTER_MAP.items():
        old_path = ROOT / old
        new_path = ROOT / new

        if not old_path.exists():
            print(f"❌ 源不存在: {old}")
            failed.append(old)
            continue

        if new_path.exists():
            print(f"⚠️ 目标已存在，跳过: {new}")
            skipped.append(new)
            continue

        if dry_run:
            print(f"🔍 [dry-run] {old}\n        → {new}")
            moved += 1
            continue

        # 创建目标父目录
        new_path.parent.mkdir(parents=True, exist_ok=True)

        # git mv
        result = subprocess.run(
            ["git", "mv", str(old_path), str(new_path)],
            cwd=ROOT, capture_output=True, text=True
        )

        if result.returncode == 0:
            moved += 1
            print(f"✅ {old} → {new}")
        else:
            print(f"❌ {result.stderr}")
            failed.append(old)

    print(f"\n=== 主目录迁移结果 ===")
    print(f"成功: {moved}/{len(CHAPTER_MAP)}")
    print(f"失败: {len(failed)}")
    if failed:
        print(f"失败清单: {failed}")
    if skipped:
        print(f"跳过清单: {skipped}")

    return moved, failed


def do_migrate_docs(dry_run=False):
    """docs 镜像同步（v3 §11.4 步骤 5）"""
    print("\n" + "=" * 60)
    print(f"docs 镜像同步 {'（演练 dry-run）' if dry_run else '（执行）'}")
    print("=" * 60)

    docs_map = {f"docs/{old}": f"docs/{new}" for old, new in CHAPTER_MAP.items()}

    moved = 0
    failed = []
    skipped = []

    for old, new in docs_map.items():
        old_path = ROOT / old
        new_path = ROOT / new

        if not old_path.exists():
            # docs 镜像里某些章可能没有，不算失败
            skipped.append(old)
            continue

        if new_path.exists():
            skipped.append(new)
            continue

        if dry_run:
            print(f"🔍 [dry-run] {old}\n        → {new}")
            moved += 1
            continue

        new_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "mv", str(old_path), str(new_path)],
            cwd=ROOT, capture_output=True, text=True
        )

        if result.returncode == 0:
            moved += 1
            print(f"✅ {old} → {new}")
        else:
            print(f"❌ {result.stderr}")
            failed.append(old)

    print(f"\n=== docs 镜像迁移结果 ===")
    print(f"成功: {moved}/{len(docs_map)}")
    print(f"跳过: {len(skipped)}")
    if failed:
        print(f"失败清单: {failed}")

    return moved, failed


def show_status():
    """git status 摘要"""
    print("\n" + "=" * 60)
    print("git status 摘要")
    print("=" * 60)

    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT, capture_output=True, text=True
    )
    lines = [l for l in result.stdout.strip().split("\n") if l]

    renames = [l for l in lines if l.startswith("R ")]
    added = [l for l in lines if l.startswith("??") or l.startswith("A ")]
    deleted = [l for l in lines if l.startswith("D ")]
    modified = [l for l in lines if l.startswith("M ")]

    print(f"总变更: {len(lines)}")
    print(f"  重命名 (R): {len(renames)}")
    print(f"  新增   (A/?): {len(added)}")
    print(f"  删除   (D): {len(deleted)}")
    print(f"  修改   (M): {len(modified)}")

    if renames[:5]:
        print(f"\n前 5 个 rename 示例:")
        for r in renames[:5]:
            print(f"  {r}")


def main():
    parser = argparse.ArgumentParser(description="v2→v3 6 卷大迁移")
    parser.add_argument("--precheck", action="store_true", help="只跑启动前自检")
    parser.add_argument("--backup", action="store_true", help="执行备份")
    parser.add_argument("--dry-run", action="store_true", help="演练模式（不动文件）")
    parser.add_argument("--migrate", action="store_true", help="迁移主目录")
    parser.add_argument("--docs", action="store_true", help="同步 docs 镜像")
    parser.add_argument("--status", action="store_true", help="git status 摘要")
    parser.add_argument("--all", action="store_true", help="完整执行：precheck + backup + migrate + docs")
    args = parser.parse_args()

    if not any([args.precheck, args.backup, args.dry_run, args.migrate, args.docs, args.status, args.all]):
        parser.print_help()
        return

    if args.precheck or args.all:
        if not check_pretable():
            sys.exit(1)

    if args.backup or args.all:
        if not do_backup():
            sys.exit(1)

    if args.dry_run:
        do_migrate(dry_run=True)
        do_migrate_docs(dry_run=True)
        return

    if args.migrate or args.all:
        moved, failed = do_migrate(dry_run=False)
        if failed:
            print(f"\n❌ 主目录有 {len(failed)} 个失败，停止 docs 同步")
            sys.exit(1)

    if args.docs or args.all:
        moved, failed = do_migrate_docs(dry_run=False)

    if args.status or args.all:
        show_status()


if __name__ == "__main__":
    main()
