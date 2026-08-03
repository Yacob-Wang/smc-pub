#!/usr/bin/env python3
"""8 卷 50 章 v2 结构迁移：卷 / 章目录重命名 + 全库链接修复。

对应《书籍目录-v1.md》v2 附录 E.2 的章号映射表。

章号存在 18→19→21→18 这类循环，直接 git mv 会互相覆盖，
因此所有目录先搬到仓库根的 staging 目录，再从 staging 落到目标位置。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
STAGING = REPO / "__migration_staging__"

V2 = "02-卷2-系统启动"
V3 = "03-卷3-核心机制"
V4_OLD, V4_NEW = "04-卷4-稳定性症状诊断", "04-卷4-诊断方法论与稳定性症状"
V5_OLD, V5_NEW = "05-卷5-调查方法论与工具链", "05-卷5-调查工具链"
V6 = "06-卷6-性能工程"
V8 = "08-卷8-案例实战"

VOLUME_RENAMES = [(V4_OLD, V4_NEW), (V5_OLD, V5_NEW)]

# 卷目录改名之后执行；路径相对仓库根
CHAPTER_MOVES = [
    # 章名调整（章号不变）
    (f"{V2}/11-启动性能专项", f"{V2}/11-系统启动性能专项"),
    (f"{V6}/37-性能基线与回归测试", f"{V6}/37-性能基线与回归防劣化"),
    (f"{V6}/38-启动性能", f"{V6}/38-应用启动性能"),
    (f"{V8}/47-冷启动优化案例", f"{V8}/47-启动性能案例"),
    (f"{V8}/48-ANR 调查案例", f"{V8}/48-ANR 与系统无响应案例"),
    (f"{V8}/49-Native Crash 调查案例", f"{V8}/49-崩溃与内存案例"),
    (f"{V8}/50-性能优化案例", f"{V8}/50-性能与整机稳定性案例"),
    # 卷 3：输入前置到 18，与显示构成「触摸 → 首帧」链路
    (f"{V3}/21-输入系统", f"{V3}/18-输入系统"),
    (f"{V3}/18-显示与渲染", f"{V3}/19-显示与渲染"),
    (f"{V3}/19-电源与续航", f"{V3}/21-电源与续航"),
    # 卷 5 → 卷 4：调查方法论上移为卷 4 开篇
    (f"{V5_NEW}/30-稳定性调查方法论", f"{V4_NEW}/22-稳定性调查方法论"),
    # 卷 4 内部顺移，为第 26 章内存与 OOM 腾位
    (f"{V4_NEW}/22-ANR 深度", f"{V4_NEW}/23-ANR 深度"),
    (f"{V4_NEW}/23-Java 异常", f"{V4_NEW}/24-Java 异常"),
    (f"{V4_NEW}/24-Native 异常", f"{V4_NEW}/25-Native 异常"),
    (f"{V4_NEW}/25-系统无响应（SWT · Watchdog）", f"{V4_NEW}/27-系统无响应（SWT · Watchdog）"),
    (f"{V4_NEW}/26-HANG 与死锁", f"{V4_NEW}/28-HANG 与死锁"),
    (f"{V4_NEW}/28-Kernel Exception", f"{V4_NEW}/29-Kernel Exception"),
    (f"{V4_NEW}/27-REBOOT", f"{V4_NEW}/30-REBOOT"),
]

# 第 29 章「性能退化与稳定性边界」并入第 37 章
MERGE_FILES = [
    (
        f"{V4_NEW}/29-性能退化与稳定性边界/01-症状机制.md",
        f"{V6}/37-性能基线与回归防劣化/06-性能退化与稳定性边界.md",
    ),
]
DROP_DIRS = [f"{V4_NEW}/29-性能退化与稳定性边界"]

NEW_DIRS = [f"{V4_NEW}/26-内存与 OOM"]

# 链接修复：键为迁移前的原始路径，按长度降序应用，卷级前缀最后兜底
LINK_MAP: list[tuple[str, str]] = [
    (f"{V2}/11-启动性能专项", f"{V2}/11-系统启动性能专项"),
    (f"{V6}/37-性能基线与回归测试", f"{V6}/37-性能基线与回归防劣化"),
    (f"{V6}/38-启动性能", f"{V6}/38-应用启动性能"),
    (f"{V8}/47-冷启动优化案例", f"{V8}/47-启动性能案例"),
    (f"{V8}/48-ANR 调查案例", f"{V8}/48-ANR 与系统无响应案例"),
    (f"{V8}/49-Native Crash 调查案例", f"{V8}/49-崩溃与内存案例"),
    (f"{V8}/50-性能优化案例", f"{V8}/50-性能与整机稳定性案例"),
    (f"{V3}/21-输入系统", f"{V3}/18-输入系统"),
    (f"{V3}/18-显示与渲染", f"{V3}/19-显示与渲染"),
    (f"{V3}/19-电源与续航", f"{V3}/21-电源与续航"),
    (f"{V5_OLD}/30-稳定性调查方法论", f"{V4_NEW}/22-稳定性调查方法论"),
    (f"{V4_OLD}/22-ANR 深度", f"{V4_NEW}/23-ANR 深度"),
    (f"{V4_OLD}/23-Java 异常", f"{V4_NEW}/24-Java 异常"),
    (f"{V4_OLD}/24-Native 异常", f"{V4_NEW}/25-Native 异常"),
    (f"{V4_OLD}/25-系统无响应（SWT · Watchdog）", f"{V4_NEW}/27-系统无响应（SWT · Watchdog）"),
    (f"{V4_OLD}/26-HANG 与死锁", f"{V4_NEW}/28-HANG 与死锁"),
    (f"{V4_OLD}/28-Kernel Exception", f"{V4_NEW}/29-Kernel Exception"),
    (f"{V4_OLD}/27-REBOOT", f"{V4_NEW}/30-REBOOT"),
    (
        f"{V4_OLD}/29-性能退化与稳定性边界/01-症状机制.md",
        f"{V6}/37-性能基线与回归防劣化/06-性能退化与稳定性边界.md",
    ),
    (V4_OLD, V4_NEW),
    (V5_OLD, V5_NEW),
]

LINK_SCAN_SKIP = ("docs/", "site/", "_archive/", "00-Meta/reader/", "00-Meta/web/")


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=REPO, check=True)


def move_dir(old_rel: str, new_rel: str) -> None:
    src, dst = REPO / old_rel, REPO / new_rel
    if not src.is_dir():
        raise SystemExit(f"missing source dir: {old_rel}")
    if dst.exists():
        raise SystemExit(f"target already exists: {new_rel}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    git("mv", old_rel, new_rel)


def run_moves() -> None:
    for old, new in VOLUME_RENAMES:
        print(f"  volume  {old} -> {new}")
        move_dir(old, new)

    STAGING.mkdir(exist_ok=True)
    for idx, (old, _new) in enumerate(CHAPTER_MOVES):
        move_dir(old, f"__migration_staging__/{idx}")
    for idx, (old, new) in enumerate(CHAPTER_MOVES):
        print(f"  chapter {old} -> {new}")
        move_dir(f"__migration_staging__/{idx}", new)
    STAGING.rmdir()

    for old, new in MERGE_FILES:
        print(f"  merge   {old} -> {new}")
        (REPO / new).parent.mkdir(parents=True, exist_ok=True)
        git("mv", old, new)


def run_cleanup() -> None:
    for rel in DROP_DIRS:
        target = REPO / rel
        if target.is_dir():
            print(f"  drop    {rel}")
            tracked = subprocess.run(
                ["git", "ls-files", rel],
                cwd=REPO,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            if tracked:
                git("rm", "-r", "-q", "-f", rel)
            shutil.rmtree(target, ignore_errors=True)

    for rel in NEW_DIRS:
        print(f"  create  {rel}")
        (REPO / rel).mkdir(parents=True, exist_ok=True)


def repair_links() -> None:
    pairs = sorted(LINK_MAP, key=lambda kv: len(kv[0]), reverse=True)
    variants: list[tuple[str, str]] = []
    for old, new in pairs:
        variants.append((old, new))
        if " " in old:
            variants.append((old.replace(" ", "%20"), new.replace(" ", "%20")))

    changed = 0
    replacements = 0
    for path in REPO.rglob("*.md"):
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith(LINK_SCAN_SKIP):
            continue
        text = original = path.read_text(encoding="utf-8", errors="replace")
        for old, new in variants:
            if old in text:
                replacements += text.count(old)
                text = text.replace(old, new)
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed += 1
    print(f"  links   {replacements} replacements in {changed} files")


def main(argv: list[str]) -> int:
    # 章号存在循环，中断后无法可靠判断哪些已搬完，故用显式阶段续跑
    skip_moves = "--skip-moves" in argv
    if skip_moves:
        print("[1/3] moving directories (skipped)")
    else:
        print("[1/3] moving directories")
        run_moves()
    print("[2/3] cleanup + new chapters")
    run_cleanup()
    print("[3/3] repairing links")
    repair_links()
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
