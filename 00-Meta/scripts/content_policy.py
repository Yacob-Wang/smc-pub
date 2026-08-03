#!/usr/bin/env python3
"""内容策略——Pages / Reader 打包共用的包含与排除规则。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 8 卷 50 章书籍结构。旧的 7 module 目录（01-Mechanism 等）已于
# 2026-08-03 全部清空并删除，正文迁入各卷，导航类 README 进 _archive。
PUBLIC_MODULES = [
    "00-Meta",
    "01-卷1-Android系统基础与平台",
    "02-卷2-系统启动",
    "03-卷3-核心机制",
    "04-卷4-诊断方法论与稳定性症状",
    "05-卷5-调查工具链",
    "06-卷6-性能工程",
    "07-卷7-APM与工程治理",
    "08-卷8-案例实战",
]

# 卷号 → 章目录前缀，供目录生成与导航使用
VOLUME_CHAPTERS: dict[str, range] = {
    "01-卷1-Android系统基础与平台": range(1, 6),
    "02-卷2-系统启动": range(6, 12),
    "03-卷3-核心机制": range(12, 22),
    "04-卷4-诊断方法论与稳定性症状": range(22, 31),
    "05-卷5-调查工具链": range(31, 37),
    "06-卷6-性能工程": range(37, 42),
    "07-卷7-APM与工程治理": range(42, 47),
    "08-卷8-案例实战": range(47, 51),
}

MODULE_TITLES = {
    "00-Meta": "Map",
    # 8 卷
    "01-卷1-Android系统基础与平台": "卷 1 基础",
    "02-卷2-系统启动": "卷 2 启动",
    "03-卷3-核心机制": "卷 3 机制",
    "04-卷4-诊断方法论与稳定性症状": "卷 4 诊断",
    "05-卷5-调查工具链": "卷 5 工具",
    "06-卷6-性能工程": "卷 6 性能",
    "07-卷7-APM与工程治理": "卷 7 治理",
    "08-卷8-案例实战": "卷 8 案例",
}

# 顶栏按读者意图分组（不搬迁仓库目录）；Tab 文案用中文任务名
TOP_NAV_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "查问题",
        [
            ("诊断", "04-卷4-诊断方法论与稳定性症状"),
            ("取证工具", "05-卷5-调查工具链"),
            ("案例", "08-卷8-案例实战"),
        ],
    ),
    (
        "学机制",
        [
            ("地图", "00-Meta"),
            ("基础", "01-卷1-Android系统基础与平台"),
            ("启动", "02-卷2-系统启动"),
            ("机制", "03-卷3-核心机制"),
        ],
    ),
    (
        "性能与治理",
        [
            ("性能", "06-卷6-性能工程"),
            ("治理", "07-卷7-APM与工程治理"),
        ],
    ),
]

MODULE_BLURBS = {
    "00-Meta": "学习路线 · 阅读指南 · JD 匹配 · 缺口一览 · Reference",
    # 8 卷
    "01-卷1-Android系统基础与平台": "Android 系统全景 · AOSP 源码 · HAL/Treble · Kernel 基础 · 安全基础（SELinux · AVB）",
    "02-卷2-系统启动": "Bootloader · Init · Zygote · SystemServer · 应用启动 · 启动性能",
    "03-卷3-核心机制": "Binder · 进程 · 线程 · 内存 · IO · 网络 · 输入 · 显示 · ART · 电源",
    "04-卷4-诊断方法论与稳定性症状": "调查方法论 · ANR · JE · NE · OOM · SWT · HANG · KE · REBOOT",
    "05-卷5-调查工具链": "Perfetto · Systrace · Dumpsys/Bugreport · Hprof · 断点调试 · Oncall",
    "06-卷6-性能工程": "性能基线 · 应用启动 · 滑动渲染 · 低端机 · WebView",
    "07-卷7-APM与工程治理": "SLI/SLO · APM 自研 · 告警 · 灰度 · AI-Native 调试",
    "08-卷8-案例实战": "启动性能 · ANR 与无响应 · 崩溃与内存 · 整机稳定性",
}

# 侧栏短名：避免把系列 README 长标题整条塞进导航
SERIES_NAV_TITLES: dict[str, dict[str, str]] = {
    "00-Meta": {
        "Reference": "Reference 索引",
        "Industry-Benchmark": "Industry Benchmark",
    },
}

# 各卷内部的「系列」就是章目录（12-Binder IPC 深度 …），目录名本身已经
# 可读，按数字前缀天然有序，不需要再维护短名与顺序表。
MODULE_SERIES_ORDER: dict[str, list[str]] = {
    "00-Meta": ["Reference", "Industry-Benchmark"],
}

# 首页「按问题进入」表格 — 集中维护，供 public_readme 与链接校验共用
PROBLEM_INDEX: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "调查方法论",
        [
            (
                "方法论总纲",
                "04-卷4-诊断方法论与稳定性症状/22-稳定性调查方法论/",
            ),
        ],
    ),
    (
        "ANR",
        [("ANR 深度", "04-卷4-诊断方法论与稳定性症状/23-ANR 深度/")],
    ),
    (
        "Java / Native 崩溃",
        [
            ("Java 异常", "04-卷4-诊断方法论与稳定性症状/24-Java 异常/"),
            ("Native 异常", "04-卷4-诊断方法论与稳定性症状/25-Native 异常/"),
        ],
    ),
    ("Binder / IPC", [("Binder", "03-卷3-核心机制/12-Binder IPC 深度/")]),
    (
        "OOM / 内存",
        [
            ("内存与 OOM", "04-卷4-诊断方法论与稳定性症状/26-内存与 OOM/"),
            ("内存管理", "03-卷3-核心机制/15-内存管理全链路/"),
            ("Hprof", "05-卷5-调查工具链/34-Hprof 与内存分析/"),
        ],
    ),
    (
        "Watchdog / HANG",
        [
            (
                "Watchdog",
                "04-卷4-诊断方法论与稳定性症状/27-系统无响应（SWT · Watchdog）/",
            ),
            ("HANG 与死锁", "04-卷4-诊断方法论与稳定性症状/28-HANG 与死锁/"),
        ],
    ),
    (
        "启动专项",
        [
            ("卷 2 启动", "02-卷2-系统启动/"),
            ("启动案例", "08-卷8-案例实战/47-启动性能案例/"),
            ("Perfetto", "05-卷5-调查工具链/31-Perfetto 全栈使用/"),
        ],
    ),
    (
        "性能与基线",
        [
            ("性能基线", "06-卷6-性能工程/37-性能基线与回归防劣化/"),
            ("低配机", "06-卷6-性能工程/40-低配机适配/"),
        ],
    ),
    (
        "APM / AI 调试",
        [
            ("APM", "07-卷7-APM与工程治理/43-APM 架构与自研实践/"),
            ("AI-Native", "07-卷7-APM与工程治理/46-AI-Native 调试/"),
        ],
    ),
    (
        "安全",
        [
            (
                "SELinux / AVB",
                "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/",
            ),
        ],
    ),
]

PUBLIC_ROOT_FILES: list[str] = [
    "文章总目录.md",
]

PUBLIC_TOOLING_FILES = [
    "mkdocs.yml",
    "00-Meta/scripts/content_policy.py",
    "00-Meta/scripts/prepare_web_docs.py",
    "00-Meta/scripts/public_readme.py",
    "00-Meta/scripts/requirements-docs.txt",
    ".github/workflows/pages.yml",
]

PUBLIC_TOOLING_DIRS = [
    "reader",
]

EXCLUDE_PATH_PREFIXES = [
    "docs/",
    "site/",
    ".cache/",
    "dist/",
    ".cursor/",
    ".claude/",
    ".mavis/",
    ".obsidian/",
    ".opencode/",
    ".vscode/",
    ".idea/",
    "scripts/",
    "reader/",
    ".github/",
    # 阶段 3：00-Meta/ 内构建产物不进 Pages
    "00-Meta/reader/",
    "00-Meta/scripts/",
    "00-Meta/overrides/",
    # web/ 由 prepare 单独拷到 docs/ 根（stylesheets/javascripts/about），勿进 00-Meta 导航
    "00-Meta/web/",
]

PRIVATE_ROOT_NAMES = frozenset(
    {
        "AGENTS.md",
        "TODO.md",
        "PUBLIC_MIRROR.md",
        ".cursorindexingignore",
    }
)

PRIVATE_ROOT_PATTERNS = [
    re.compile(r"^Stability_Architect_Roadmap", re.I),
]

# 00-Meta 模块落地页卡片与侧栏顺序（读者向）
META_HUB_PAGES: list[tuple[str, str]] = [
    ("学习路线", "学习路线-稳定性架构师.md"),
    # 顶栏 / 移动端 chip 用顶层 stub，避免 Material 把 Reference/… 解析成 ../Reference/…（404）
    ("阅读指南", "阅读指南.md"),
    ("JD 匹配矩阵", "JD匹配矩阵.md"),
    ("缺口一览", "缺口一览.md"),
    ("术语表", "术语表.md"),
    ("案例索引", "案例索引.md"),
    ("版本基线", "版本基线.md"),
]

META_NAME_PATTERNS = [
    re.compile(r"^缺项规划", re.I),
    re.compile(r"^OUTLINE", re.I),
    re.compile(r"^PROMPT-", re.I),
    re.compile(r"^AGENTS\.md$", re.I),
    re.compile(r"^TODO\.md$", re.I),
    re.compile(r"^Plan\.md$", re.I),
    re.compile(r".*_Series_Plan\.md$", re.I),
    re.compile(r".*Series_Plan\.md$", re.I),
    re.compile(r"^Perfetto_Series_Plan\.md$", re.I),
    re.compile(r".*写作指南.*\.md$", re.I),
    re.compile(r".*大纲.*\.md$", re.I),
    re.compile(r".*质量评估.*\.md$", re.I),
    re.compile(r".*校准报告.*\.md$", re.I),
]

ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}


def is_meta_file(path: Path | str) -> bool:
    name = Path(path).name
    return any(pat.search(name) for pat in META_NAME_PATTERNS)


def is_excluded_path(rel: Path | str) -> bool:
    """rel 相对仓库根。True = 不进 Pages / Reader 正文。"""
    posix = Path(str(rel).replace("\\", "/")).as_posix().lstrip("./")
    root_name = Path(posix).name

    if posix in PRIVATE_ROOT_NAMES:
        return True

    if any(pat.search(root_name) for pat in PRIVATE_ROOT_PATTERNS):
        return True

    parts_lower = {p.lower() for p in Path(posix).parts}
    if "_archive" in parts_lower or "_studio" in parts_lower:
        return True

    for prefix in EXCLUDE_PATH_PREFIXES:
        root = prefix.rstrip("/")
        if posix == root or posix.startswith(prefix):
            return True

    if posix.endswith(".bak.md"):
        return True

    if is_meta_file(posix):
        return True

    return False


def is_public_content_file(rel: Path | str) -> bool:
    """是否可作为站点/App 正文或配图。"""
    posix = Path(str(rel).replace("\\", "/")).as_posix().lstrip("./")
    if is_excluded_path(posix):
        return False
    suffix = Path(posix).suffix.lower()
    if suffix != ".md" and suffix not in ASSET_SUFFIXES:
        return False
    if posix in PUBLIC_ROOT_FILES:
        return True
    top = posix.split("/", 1)[0]
    return top in PUBLIC_MODULES


def dump_policy_json() -> str:
    return json.dumps(
        {
            "public_modules": PUBLIC_MODULES,
            "public_root_files": PUBLIC_ROOT_FILES,
            "public_tooling_files": PUBLIC_TOOLING_FILES,
            "public_tooling_dirs": PUBLIC_TOOLING_DIRS,
            "exclude_path_prefixes": EXCLUDE_PATH_PREFIXES,
            "private_root_names": sorted(PRIVATE_ROOT_NAMES),
            "meta_name_regexes": [p.pattern for p in META_NAME_PATTERNS],
            "asset_suffixes": sorted(ASSET_SUFFIXES),
        },
        ensure_ascii=False,
        indent=2,
    )


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "--dump-json":
        print(dump_policy_json())
        return 0
    if len(argv) >= 3 and argv[1] == "--check":
        rel = argv[2]
        excluded = is_excluded_path(rel)
        print("exclude" if excluded else "include")
        return 1 if excluded else 0
    print(dump_policy_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
