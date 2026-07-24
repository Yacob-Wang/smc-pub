#!/usr/bin/env python3
"""内容策略——Pages / Reader 打包共用的包含与排除规则。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PUBLIC_MODULES = [
    "00-Meta",
    "01-Mechanism",
    "02-Symptom",
    "03-Forensics",
    "04-Tool",
    "05-Governance",
    "06-Case",
    "06-Foundation",
]

MODULE_TITLES = {
    "00-Meta": "Map",
    "01-Mechanism": "Mechanism",
    "02-Symptom": "Symptoms",
    "03-Forensics": "Forensics",
    "04-Tool": "Tools",
    "05-Governance": "Governance",
    "06-Case": "Cases",
    "06-Foundation": "Foundation",
}

MODULE_BLURBS = {
    "00-Meta": "项目地图 · Reference · 版本基线 · 迁移日志",
    "01-Mechanism": "Hardware · Kernel · Runtime · Framework · App",
    "02-Symptom": "11 大症状机制（ANR · JE · NE · SWT · HANG · REBOOT · KE 等）",
    "03-Forensics": "8 大取证链（与症状编号一一对应）",
    "04-Tool": "Dumpsys · Watchdog · Perfetto · Hprof · AmCommand · ANR-Detection",
    "05-Governance": "APM · OEM-BSP · 跨平台 · 低端机 · AI Native · AI-Debug · 性能内存 · 安全",
    "06-Case": "启动场景案例 + 跨系列实战",
    "06-Foundation": "Build-System · System-Integration · Dynamic-Updates · Tools",
}

# 侧栏短名：避免把系列 README 长标题整条塞进导航
SERIES_NAV_TITLES: dict[str, dict[str, str]] = {
    "00-Meta": {
        "Reference": "Reference 索引",
    },
    "01-Mechanism": {
        "Hardware": "硬件层",
        "Kernel": "内核层",
        "Runtime": "运行时",
        "Framework": "Framework",
        "App": "应用层",
    },
    "02-Symptom": {
        "S01-ANR": "S01 ANR",
        "S02-JE": "S02 Java 异常",
        "S03-NE": "S03 Native 异常",
        "S04-SWT": "S04 SWT",
        "S05-HANG": "S05 HANG",
        "S06-REBOOT": "S06 REBOOT",
        "S07-KE": "S07 KE",
        "S08-AOSP17-K618": "S08 AOSP 17 + K 6.18",
        "S09-PerfVsStab": "S09 性能 vs 稳定性",
        "S10-Measure": "S10 度量门禁",
        "S11-Startup": "S11 启动专项",
    },
    "03-Forensics": {
        "F00-Overview": "F00 总览",
        "F01-ANR": "F01 ANR 取证",
        "F02-SWT": "F02 SWT 取证",
        "F03-JE": "F03 JE 取证",
        "F04-NE": "F04 NE 取证",
        "F05-KE": "F05 KE 取证",
        "F06-HANG-OOM": "F06 HANG / OOM",
        "F07-Governance": "F07 治理",
    },
    "04-Tool": {
        "Dumpsys": "Dumpsys",
        "Watchdog": "Watchdog",
        "Perfetto": "Perfetto",
        "Hprof": "Hprof",
        "AmCommand": "AmCommand",
        "ANR-Detection": "ANR-Detection",
    },
    "05-Governance": {
        "APM": "APM",
        "OEM-BSP": "OEM-BSP",
        "CrossPlatform": "跨平台",
        "LowEnd": "低端机",
        "AI-Native": "AI Native",
        "AI-Debug": "AI-Debug",
        "PerfMem": "性能 vs 内存",
        "Security": "安全",
    },
    "06-Case": {
        "Startup": "启动案例",
        "Cases-Extended": "扩展案例",
    },
    "06-Foundation": {
        "Build-System": "Build-System",
        "System-Integration": "System-Integration",
        "Dynamic-Updates": "Dynamic-Updates",
        "Tools": "Tools",
    },
}

MODULE_SERIES_ORDER: dict[str, list[str]] = {
    "00-Meta": ["Reference"],
    "01-Mechanism": [
        "Hardware",
        "Kernel",
        "Runtime",
        "Framework",
        "App",
    ],
    "02-Symptom": [
        "S01-ANR",
        "S02-JE",
        "S03-NE",
        "S04-SWT",
        "S05-HANG",
        "S06-REBOOT",
        "S07-KE",
        "S08-AOSP17-K618",
        "S09-PerfVsStab",
        "S10-Measure",
        "S11-Startup",
    ],
    "03-Forensics": [
        "F00-Overview",
        "F01-ANR",
        "F02-SWT",
        "F03-JE",
        "F04-NE",
        "F05-KE",
        "F06-HANG-OOM",
        "F07-Governance",
    ],
    "04-Tool": [
        "Dumpsys",
        "Watchdog",
        "Perfetto",
        "Hprof",
        "AmCommand",
        "ANR-Detection",
    ],
    "05-Governance": [
        "APM",
        "OEM-BSP",
        "CrossPlatform",
        "LowEnd",
        "AI-Native",
        "AI-Debug",
        "PerfMem",
        "Security",
    ],
    "06-Case": ["Startup", "Cases-Extended"],
    "06-Foundation": [
        "Build-System",
        "System-Integration",
        "Dynamic-Updates",
        "Tools",
    ],
}

# 首页「按问题进入」表格 — 集中维护，供 public_readme 与链接校验共用
PROBLEM_INDEX: list[tuple[str, list[tuple[str, str]]]] = [
    ("Native Crash", [("Native Crash", "01-Mechanism/Runtime/Native_Crash/")]),
    (
        "Java 异常 / ANR",
        [
            ("ANR 症状", "02-Symptom/S01-ANR/"),
            ("ANR 取证", "03-Forensics/F01-ANR/"),
            ("ANR-Detection", "04-Tool/ANR-Detection/"),
        ],
    ),
    ("Binder / IPC", [("Binder", "01-Mechanism/Kernel/Binder/")]),
    (
        "OOM / 内存",
        [
            ("内存管理", "01-Mechanism/Kernel/Memory_Management/"),
            ("ART", "01-Mechanism/Runtime/ART/"),
            ("Hprof", "04-Tool/Hprof/"),
        ],
    ),
    (
        "Watchdog / SWT",
        [("Watchdog", "04-Tool/Watchdog/"), ("SWT 取证", "03-Forensics/F02-SWT/")],
    ),
    (
        "Socket / epoll",
        [
            ("Socket", "01-Mechanism/Kernel/socket/"),
            ("epoll", "01-Mechanism/Kernel/epoll/"),
        ],
    ),
    (
        "启动专项",
        [
            ("S11 启动专项", "02-Symptom/S11-Startup/"),
            ("启动案例", "06-Case/Startup/"),
            ("Perfetto Boot Trace", "04-Tool/Perfetto/"),
        ],
    ),
    ("AOSP 17 + K 6.18 演进", [("S08 演进全景", "02-Symptom/S08-AOSP17-K618/")]),
    ("性能 vs 稳定性", [("S09 横切专题", "02-Symptom/S09-PerfVsStab/")]),
    (
        "度量 + 门禁",
        [("S10 度量门禁", "02-Symptom/S10-Measure/"), ("APM", "05-Governance/APM/")],
    ),
    ("OEM 厂商适配", [("OEM-BSP", "05-Governance/OEM-BSP/")]),
    ("跨平台 / HarmonyOS", [("CrossPlatform", "05-Governance/CrossPlatform/")]),
    ("低端机治理", [("LowEnd", "05-Governance/LowEnd/")]),
    (
        "端侧 AI / AI OS",
        [
            ("AI Native", "05-Governance/AI-Native/"),
            ("AI for Stability", "05-Governance/AI-Native/03_AI_for_Stability/"),
        ],
    ),
    ("AI 辅助调试", [("AI-Debug", "05-Governance/AI-Debug/")]),
    ("性能 vs 内存", [("PerfMem", "05-Governance/PerfMem/")]),
    ("安全 + 稳定性", [("Security", "05-Governance/Security/")]),
]

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
    # 阶段 3：00-Meta/ 内构建产物不进 Pages
    "00-Meta/reader/",
    "00-Meta/scripts/",
    "00-Meta/overrides/",
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
