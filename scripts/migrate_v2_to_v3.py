#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 (8卷50章) → v3 (6卷56章) 目录迁移 + 路径改写。

用法:
  py -3.12 scripts/migrate_v2_to_v3.py           # 迁移章目录
  py -3.12 scripts/migrate_v2_to_v3.py --rewrite # 仅改写正文旧路径
  py -3.12 scripts/migrate_v2_to_v3.py --all     # 迁移 + 改写
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHAPTER_MAP: dict[str, str] = {
    # 原卷 1 (1-5) → 新卷 1
    "01-卷1-Android系统基础与平台/01-Android 系统全景与 AOSP 17": "01-卷1-平台基础与启动/01-系统全景与 AOSP 17",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统": "01-卷1-平台基础与启动/02-AOSP 源码结构与构建系统",
    "01-卷1-Android系统基础与平台/03-硬件抽象层（HAL）与 Treble 架构": "01-卷1-平台基础与启动/03-硬件抽象层（HAL）与 Treble 架构",
    "01-卷1-Android系统基础与平台/04-Linux Kernel 基础（Android 视角）": "01-卷1-平台基础与启动/04-Linux Kernel 基础（Android 视角）",
    "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）": "01-卷1-平台基础与启动/05-安全基础（SELinux · AVB）",
    # 原卷 2 (6-11) → 新卷 1
    "02-卷2-系统启动/06-Bootloader 到 Kernel": "01-卷1-平台基础与启动/06-Bootloader 到 Kernel",
    "02-卷2-系统启动/07-Init 进程与 init.rc": "01-卷1-平台基础与启动/07-Init 进程与 init.rc",
    "02-卷2-系统启动/08-Zygote 与 ART 启动": "01-卷1-平台基础与启动/08-Zygote 与 ART 启动",
    "02-卷2-系统启动/09-SystemServer 启动": "01-卷1-平台基础与启动/09-SystemServer 启动",
    "02-卷2-系统启动/10-应用启动与首帧": "01-卷1-平台基础与启动/10-应用启动与首帧",
    "02-卷2-系统启动/11-系统启动性能专项": "01-卷1-平台基础与启动/11-系统启动性能专项",
    # 原卷 3 (12-21) → 新卷 2
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
    "05-卷5-调查工具链/31-Perfetto 全栈使用": "03-卷3-调查工具/22-Perfetto 全栈使用",
    "05-卷5-调查工具链/32-Systrace 与 ftrace": "03-卷3-调查工具/23-Systrace 与 ftrace",
    "05-卷5-调查工具链/33-Dumpsys · Bugreport · DropBox": "03-卷3-调查工具/24-Dumpsys · Bugreport · DropBox",
    "05-卷5-调查工具链/34-Hprof 与内存分析": "03-卷3-调查工具/25-Hprof 与内存分析",
    "05-卷5-调查工具链/35-断点与 Native 调试": "03-卷3-调查工具/26-断点与 Native 调试",
    "05-卷5-调查工具链/36-Oncall 与应急响应": "03-卷3-调查工具/27-Oncall 与应急响应",
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

# 卷根零散文件（非章目录）
EXTRA_FILES: dict[str, str] = {
    "02-卷2-系统启动/0-上电到桌面-冷启动26锚点全链路时序与劣化分析.md": "01-卷1-平台基础与启动/0-上电到桌面-冷启动26锚点全链路时序与劣化分析.md",
    "02-卷2-系统启动/README.md": "01-卷1-平台基础与启动/README-原卷2启动.md",
    "04-卷4-诊断方法论与稳定性症状/00-取证体系总览.md": "04-卷4-稳定性症状/00-取证体系总览.md",
    "04-卷4-诊断方法论与稳定性症状/00-症状体系总览.md": "04-卷4-稳定性症状/00-症状体系总览.md",
}

OLD_VOLUME_DIRS = [
    "01-卷1-Android系统基础与平台",
    "02-卷2-系统启动",
    "03-卷3-核心机制",
    "04-卷4-诊断方法论与稳定性症状",
    "05-卷5-调查工具链",
    "06-卷6-性能工程",
    "07-卷7-APM与工程治理",
    "08-卷8-案例实战",
]

# 卷名级回退替换（章级替换之后仍残留的路径）
VOLUME_FALLBACK: list[tuple[str, str]] = [
    ("01-卷1-Android系统基础与平台", "01-卷1-平台基础与启动"),
    ("02-卷2-系统启动", "01-卷1-平台基础与启动"),
    ("03-卷3-核心机制", "02-卷2-核心机制"),
    ("04-卷4-诊断方法论与稳定性症状", "04-卷4-稳定性症状"),
    ("05-卷5-调查工具链", "03-卷3-调查工具"),
    ("06-卷6-性能工程", "05-卷5-性能工程与治理"),
    ("07-卷7-APM与工程治理", "05-卷5-性能工程与治理"),
    ("08-卷8-案例实战", "06-卷6-案例实战"),
]

SKIP_REWRITE_DIRS = {
    ".git",
    "docs",
    "site",
    "_archive",
    "_tmp",
    "tmp",
    "node_modules",
    ".cache",
    "scripts",  # 迁移脚本自身保留旧路径作对照
}


def _git_tracked(rel: str) -> bool:
    r = subprocess.run(
        ["git", "ls-files", "--", rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return bool(r.stdout.strip())


def _move_path(old_rel: str, new_rel: str) -> str:
    old = ROOT / old_rel
    new = ROOT / new_rel
    if not old.exists():
        return f"MISS {old_rel}"
    if new.exists():
        return f"EXISTS {new_rel}"
    new.parent.mkdir(parents=True, exist_ok=True)
    if _git_tracked(old_rel):
        r = subprocess.run(
            ["git", "mv", "--", old_rel, new_rel],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            # 未跟踪子文件混在目录里时 git mv 可能失败，退回文件系统移动 + 对跟踪文件记 rename
            shutil.move(str(old), str(new))
            return f"FS {old_rel} → {new_rel} (git mv failed: {r.stderr.strip()})"
        return f"GIT {old_rel} → {new_rel}"
    shutil.move(str(old), str(new))
    return f"FS {old_rel} → {new_rel}"


def migrate() -> tuple[int, list[str]]:
    moved = 0
    failed: list[str] = []
    print("=== Step 1: 章目录迁移 ===")
    for old, new in CHAPTER_MAP.items():
        msg = _move_path(old, new)
        print(msg)
        if msg.startswith(("GIT", "FS")):
            moved += 1
        elif msg.startswith("MISS"):
            failed.append(old)
        elif msg.startswith("EXISTS"):
            failed.append(old)

    print("\n=== Step 2: 卷根零散文件 ===")
    for old, new in EXTRA_FILES.items():
        msg = _move_path(old, new)
        print(msg)
        if msg.startswith(("GIT", "FS")):
            moved += 1

    print("\n=== Step 3: 清理旧卷目录残留 ===")
    for vol in OLD_VOLUME_DIRS:
        p = ROOT / vol
        if not p.exists():
            continue
        leftovers = list(p.rglob("*"))
        files = [x for x in leftovers if x.is_file()]
        if files:
            print(f"KEEP leftovers in {vol}: {[str(f.relative_to(ROOT)) for f in files[:20]]}")
            # 把残留 index.md 归档后删空目录
            archive = ROOT / "_archive" / "vol-reorg-v3-leftovers" / vol
            archive.mkdir(parents=True, exist_ok=True)
            for f in files:
                rel = f.relative_to(p)
                dest = archive / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(dest))
                print(f"  archived {f.relative_to(ROOT)}")
        shutil.rmtree(p, ignore_errors=True)
        print(f"REMOVED {vol}")

    return moved, failed


def rewrite_links() -> int:
    """把正文 / 元文档中的旧卷章路径改成新路径。"""
    replacements: list[tuple[str, str]] = []
    # 章级（最长优先）
    for old, new in sorted(CHAPTER_MAP.items(), key=lambda kv: -len(kv[0])):
        replacements.append((old, new))
        replacements.append((old.replace("\\", "/"), new))
    for old, new in VOLUME_FALLBACK:
        replacements.append((old, new))

    # 去重保序
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for old, new in replacements:
        if old in seen or old == new:
            continue
        seen.add(old)
        uniq.append((old, new))

    changed_files = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".mdc", ".py", ".yml", ".yaml", ".txt", ".html"}:
            continue
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            continue
        if any(part in SKIP_REWRITE_DIRS for part in rel.parts):
            continue
        # 跳过本脚本
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new_text = text
        for old, new in uniq:
            if old in new_text:
                new_text = new_text.replace(old, new)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8", newline="\n")
            changed_files += 1
            print(f"REWRITE {rel}")
    return changed_files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rewrite", action="store_true", help="仅改写路径")
    ap.add_argument("--all", action="store_true", help="迁移 + 改写")
    args = ap.parse_args()

    if args.rewrite:
        n = rewrite_links()
        print(f"\n改写文件数: {n}")
        return 0

    moved, failed = migrate()
    print(f"\n迁移成功条目: {moved}/{len(CHAPTER_MAP) + len(EXTRA_FILES)}")
    if failed:
        print(f"失败: {failed}")
        return 1

    if args.all:
        print("\n=== Step 4: 路径改写 ===")
        n = rewrite_links()
        print(f"改写文件数: {n}")

    # 快速对账
    print("\n=== 新卷目录 ===")
    for vol in sorted(ROOT.glob("0*-卷*")):
        chapters = [p.name for p in sorted(vol.iterdir()) if p.is_dir()]
        print(f"{vol.name}: {len(chapters)} 章")
        for c in chapters:
            print(f"  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
