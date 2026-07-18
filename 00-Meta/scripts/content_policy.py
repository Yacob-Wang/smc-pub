#!/usr/bin/env python3
"""内容策略——Pages / Reader 打包共用的包含与排除规则。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PUBLIC_MODULES = [
    "Linux_Kernel",
    "Runtime",
    "Android_Framework",
    "App",
    "Tools",
    "Hook",
    "AI_Native_X",
]

MODULE_TITLES = {
    "Linux_Kernel": "Linux 内核",
    "Runtime": "运行时",
    "Android_Framework": "Framework",
    "App": "应用层",
    "Tools": "工具",
    "Hook": "Hook",
    "AI_Native_X": "AI Native",
}

MODULE_BLURBS = {
    "Linux_Kernel": "进程 · 内存 · IO · Binder · Socket · 分区",
    "Runtime": "ART · Native Crash",
    "Android_Framework": "进程 · ANR · Watchdog · Input · Window",
    "App": "Handler · MessageQueue · Looper",
    "Tools": "调试 · 追踪 · 内存分析 · Git",
    "Hook": "OEM Hook 专题",
    "AI_Native_X": "端侧 Runtime · AI OS · 稳定性 · 工程实践",
}

# 侧栏短名：避免把系列 README 长标题整条塞进导航
SERIES_NAV_TITLES: dict[str, dict[str, str]] = {
    "Linux_Kernel": {
        "Process": "进程",
        "Memory_Management": "内存管理",
        "IO": "IO",
        "Binder": "Binder",
        "socket": "Socket",
        "epoll": "epoll",
        "FS": "文件系统",
        "Partition": "分区",
        "Program_Execution": "程序加载",
        "Input_Driver": "输入驱动",
        "GKI": "GKI",
        "DM": "Device Mapper",
        "Interrupt": "中断",
        "Syscalls": "系统调用",
    },
    "Runtime": {
        "ART": "ART",
        "Java_Crash": "Java Crash",
        "Native_Crash": "Native Crash",
    },
    "Android_Framework": {
        "Process": "进程",
        "ANR_Detection": "ANR 检测",
        "Watchdog": "Watchdog",
        "Input": "Input",
        "Window": "Window",
        "Broadcast": "Broadcast",
        "Service": "Service",
        "PKMS": "PKMS",
        "AOSP_Startup": "启动",
        "Partition_System": "分区系统",
        "Build_System": "编译系统",
        "Dumpsys": "dumpsys",
        "AmCommand": "am 命令",
        "Hprof": "Hprof",
        "Perfetto": "Perfetto",
        "Dynamic_Updates": "动态更新",
        "System_Integration": "系统集成",
    },
    "App": {
        "Handler_MessageQueue_Looper": "Handler / MQ / Looper",
    },
    "Tools": {
        "Tracing": "追踪",
        "Memory_Analysis": "内存分析",
        "Debugging": "调试",
        "Android_Tools": "Android 工具",
        "Kernel_Tools": "内核工具",
        "Git_Mastery": "Git",
        "Automation": "自动化",
    },
    "AI_Native_X": {
        "01_AI_Native_Runtime": "AI Runtime",
        "02_AI_Native_OS": "AI OS",
        "03_AI_for_Stability": "AI for Stability",
        "04_AI_Engineering": "AI 工程",
    },
}

MODULE_SERIES_ORDER: dict[str, list[str]] = {
    "Linux_Kernel": [
        "Process",
        "Memory_Management",
        "IO",
        "Binder",
        "socket",
        "epoll",
        "FS",
        "Partition",
        "Program_Execution",
        "Input_Driver",
        "GKI",
        "DM",
        "Interrupt",
        "Syscalls",
    ],
    "Runtime": ["ART", "Java_Crash", "Native_Crash"],
    "Android_Framework": [
        "Process",
        "ANR_Detection",
        "Watchdog",
        "Input",
        "Window",
        "Broadcast",
        "Service",
        "PKMS",
        "AOSP_Startup",
        "Partition_System",
        "Build_System",
        "Dumpsys",
        "AmCommand",
        "Hprof",
        "Perfetto",
        "Dynamic_Updates",
        "System_Integration",
    ],
    "App": ["Handler_MessageQueue_Looper"],
    "Tools": [
        "Tracing",
        "Memory_Analysis",
        "Debugging",
        "Android_Tools",
        "Kernel_Tools",
        "Git_Mastery",
        "Automation",
    ],
    "Hook": [],
    "AI_Native_X": [
        "01_AI_Native_Runtime",
        "02_AI_Native_OS",
        "03_AI_for_Stability",
        "04_AI_Engineering",
    ],
}

PUBLIC_ROOT_FILES: list[str] = []

PUBLIC_TOOLING_FILES = [
    "mkdocs.yml",
    "scripts/content_policy.py",
    "scripts/prepare_web_docs.py",
    "scripts/public_readme.py",
    "scripts/requirements-docs.txt",
    "scripts/pack-content.ps1",
    "scripts/pack-content.cmd",
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

META_NAME_PATTERNS = [
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
