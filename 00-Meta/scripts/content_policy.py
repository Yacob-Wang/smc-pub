#!/usr/bin/env python3
"""内容策略——Pages / Reader 打包共用的包含与排除规则。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 6 卷 56 章书籍结构（2026-08-05 v3 重组：原 8 卷 50 章合并）。
PUBLIC_MODULES = [
    "00-Meta",
    "01-卷1-平台基础与启动",
    "02-卷2-核心机制",
    "03-卷3-调查工具",
    "04-卷4-稳定性症状",
    "05-卷5-性能工程与治理",
    "06-卷6-案例实战",
]

VOLUME_CHAPTERS: dict[str, range] = {
    "01-卷1-平台基础与启动": range(1, 12),
    "02-卷2-核心机制": range(12, 22),
    "03-卷3-调查工具": range(22, 34),
    "04-卷4-稳定性症状": range(34, 43),
    "05-卷5-性能工程与治理": range(43, 53),
    "06-卷6-案例实战": range(53, 57),
}

MODULE_TITLES = {
    "00-Meta": "Map",
    "01-卷1-平台基础与启动": "卷 1 平台启动",
    "02-卷2-核心机制": "卷 2 机制",
    "03-卷3-调查工具": "卷 3 工具",
    "04-卷4-稳定性症状": "卷 4 症状",
    "05-卷5-性能工程与治理": "卷 5 性能治理",
    "06-卷6-案例实战": "卷 6 案例",
}

TOP_NAV_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "查问题",
        [
            ("症状", "04-卷4-稳定性症状"),
            ("工具", "03-卷3-调查工具"),
            ("案例", "06-卷6-案例实战"),
        ],
    ),
    (
        "学机制",
        [
            ("地图", "00-Meta"),
            ("平台启动", "01-卷1-平台基础与启动"),
            ("机制", "02-卷2-核心机制"),
        ],
    ),
    (
        "性能与治理",
        [
            ("性能治理", "05-卷5-性能工程与治理"),
        ],
    ),
]

MODULE_BLURBS = {
    "00-Meta": "学习路线 · 阅读指南 · JD 匹配 · 缺口一览 · Reference",
    "01-卷1-平台基础与启动": "平台地基 · Bootloader · Init · Zygote · SystemServer · 应用启动 · 启动性能",
    "02-卷2-核心机制": "Binder · 进程 · 线程 · 内存 · IO · 网络 · 输入 · 显示 · ART · 电源",
    "03-卷3-调查工具": "Perfetto · Systrace · Dumpsys/Bugreport · Hprof · 断点调试 · Oncall · 系统命令/火焰图（扩充中）",
    "04-卷4-稳定性症状": "调查方法论 · ANR · JE · NE · OOM · SWT · HANG · KE · REBOOT",
    "05-卷5-性能工程与治理": "性能基线 · 启动/滑动/低端机/WebView · SLI/SLO · APM · 告警 · 灰度 · AI-Native",
    "06-卷6-案例实战": "启动性能 · ANR 与无响应 · 崩溃与内存 · 整机稳定性",
}

SERIES_NAV_TITLES: dict[str, dict[str, str]] = {
    "00-Meta": {
        "Reference": "Reference 索引",
        "Industry-Benchmark": "Industry Benchmark",
    },
}

MODULE_SERIES_ORDER: dict[str, list[str]] = {
    "00-Meta": ["Reference", "Industry-Benchmark"],
}

PROBLEM_INDEX: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "调查方法论",
        [
            (
                "方法论总纲",
                "04-卷4-稳定性症状/34-稳定性调查方法论/",
            ),
        ],
    ),
    (
        "ANR",
        [("ANR 深度", "04-卷4-稳定性症状/35-ANR 深度/")],
    ),
    (
        "Java / Native 崩溃",
        [
            ("Java 异常", "04-卷4-稳定性症状/36-Java 异常/"),
            ("Native 异常", "04-卷4-稳定性症状/37-Native 异常/"),
        ],
    ),
    ("Binder / IPC", [("Binder", "02-卷2-核心机制/12-Binder IPC 深度/")]),
    (
        "OOM / 内存",
        [
            ("内存与 OOM", "04-卷4-稳定性症状/38-内存与 OOM/"),
            ("内存管理", "02-卷2-核心机制/15-内存管理全链路/"),
            ("Hprof", "03-卷3-调查工具/25-Hprof 与内存分析/"),
        ],
    ),
    (
        "Watchdog / HANG",
        [
            (
                "Watchdog",
                "04-卷4-稳定性症状/39-系统无响应（SWT · Watchdog）/",
            ),
            ("HANG 与死锁", "04-卷4-稳定性症状/40-HANG 与死锁/"),
        ],
    ),
    (
        "启动专项",
        [
            ("卷 1 启动", "01-卷1-平台基础与启动/"),
            ("启动案例", "06-卷6-案例实战/53-启动性能案例/"),
            ("Perfetto", "03-卷3-调查工具/22-Perfetto 全栈使用/"),
        ],
    ),
    (
        "性能与基线",
        [
            ("性能基线", "05-卷5-性能工程与治理/43-性能基线与回归防劣化/"),
            ("低配机", "05-卷5-性能工程与治理/46-低配机适配/"),
        ],
    ),
    (
        "APM / AI 调试",
        [
            ("APM", "05-卷5-性能工程与治理/49-APM 架构与自研实践/"),
            ("AI-Native", "05-卷5-性能工程与治理/52-AI-Native 调试/"),
        ],
    ),
    (
        "安全",
        [
            (
                "SELinux / AVB",
                "01-卷1-平台基础与启动/05-安全基础（SELinux · AVB）/",
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
    # harness 为作者/Agent 控制面，不进公开站
    "00-Meta/harness/",
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
