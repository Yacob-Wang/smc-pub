#!/usr/bin/env python3
"""检查构建产物中顶栏标签与下拉 / 二级 flyout 的 href 是否有效。"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SITE_DIR = REPO_ROOT / "site"

# 意图分组顶栏：唯一合法顶层 Tab 文案（顺序固定）
EXPECTED_TAB_LABELS = ("首页", "总目录", "查问题", "学机制", "性能与治理")

# 意图分组 Tab 点击落点（相对 site/ 的路径前缀）
EXPECTED_TAB_HREFS = {
    "学机制": "03-卷3-核心机制/",
}

# 文件系统回退态特征（出现任一即失败）
FORBIDDEN_TAB_PATTERNS = (
    re.compile(r"^Home$", re.I),
    re.compile(r"^None$", re.I),
    re.compile(r"^About$", re.I),
    re.compile(r"^00\s*Meta", re.I),
    re.compile(r"^0\d\s*卷"),
    re.compile(r"^01-卷"),
    re.compile(r"^02-卷"),
    re.compile(r"^03-卷"),
    re.compile(r"^04-卷"),
    re.compile(r"^05-卷"),
    re.compile(r"^06-卷"),
    re.compile(r"^07-卷"),
    re.compile(r"^08-卷"),
)

# 每个顶层模块至少 1 页；Mechanism 含 flyout 深层页
SAMPLE_PAGES = [
    "index.html",
    "00-Meta/index.html",
    "01-卷1-Android系统基础与平台/index.html",
    "03-卷3-核心机制/index.html",
    "03-卷3-核心机制/15-内存管理全链路/index.html",
    "04-卷4-诊断方法论与稳定性症状/index.html",
    "04-卷4-诊断方法论与稳定性症状/23-ANR 深度/index.html",
    "05-卷5-调查工具链/index.html",
    "06-卷6-性能工程/index.html",
    "07-卷7-APM与工程治理/index.html",
    "08-卷8-案例实战/index.html",
    "02-卷2-系统启动/11-系统启动性能专项/index.html",
]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class TabMenuHrefParser(HTMLParser):
    """提取 jk-tabs__menu / jk-tabs__submenu 区域内的 href。"""

    def __init__(self) -> None:
        super().__init__()
        self._menu_depth = 0
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: v for k, v in attrs if v is not None}
        classes = attr_map.get("class", "")
        if tag == "div" and ("jk-tabs__menu" in classes or "jk-tabs__submenu" in classes):
            self._menu_depth += 1
            return
        if self._menu_depth > 0 and tag == "a" and "href" in attr_map:
            href = attr_map["href"]
            if href and not href.startswith(("#", "mailto:")):
                self.hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._menu_depth > 0:
            self._menu_depth -= 1


class TopTabLabelParser(HTMLParser):
    """提取顶栏 md-tabs__list 内一级 Tab 文案与 href（不含下拉菜单链接）。"""

    def __init__(self) -> None:
        super().__init__()
        self._in_tabs_list = 0
        self._in_menu = 0
        self._capture_link = False
        self._href = ""
        self._buf: list[str] = []
        self.labels: list[str] = []
        self.label_hrefs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: v for k, v in attrs if v is not None}
        classes = attr_map.get("class", "")
        if tag == "ul" and "md-tabs__list" in classes:
            self._in_tabs_list += 1
            return
        if self._in_tabs_list <= 0:
            return
        if tag == "div" and ("jk-tabs__menu" in classes or "jk-tabs__submenu" in classes):
            self._in_menu += 1
            return
        if self._in_menu > 0:
            return
        if tag == "a" and "md-tabs__link" in classes:
            self._capture_link = True
            self._href = attr_map.get("href", "") or ""
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "ul" and self._in_tabs_list > 0:
            self._in_tabs_list -= 1
            return
        if tag == "div" and self._in_menu > 0:
            self._in_menu -= 1
            return
        if tag == "a" and self._capture_link:
            label = _WS_RE.sub(" ", "".join(self._buf)).strip()
            if label:
                self.labels.append(label)
                if self._href:
                    self.label_hrefs[label] = unquote(self._href.replace("&amp;", "&"))
            self._capture_link = False
            self._href = ""
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._capture_link and self._in_menu == 0:
            self._buf.append(data)


def extract_menu_hrefs(html: str) -> list[str]:
    parser = TabMenuHrefParser()
    parser.feed(html)
    return parser.hrefs


def extract_top_tab_labels(html: str) -> list[str]:
    parser = TopTabLabelParser()
    parser.feed(html)
    return parser.labels


def extract_top_tab_hrefs(html: str) -> dict[str, str]:
    parser = TopTabLabelParser()
    parser.feed(html)
    return parser.label_hrefs


def resolve_href(source: Path, href: str) -> Path:
    href = unquote(href.replace("&amp;", "&"))
    if href.startswith("/"):
        return SITE_DIR / href.lstrip("/")
    return (source.parent / href).resolve()


def target_exists(target: Path, href: str) -> bool:
    if href.endswith("/"):
        return (target / "index.html").is_file()
    return target.is_file() or (target / "index.html").is_file()


def validate_tab_labels(rel: str, labels: list[str]) -> list[str]:
    """返回该页顶栏标签问题描述；空列表表示通过。"""
    problems: list[str] = []
    if tuple(labels) != EXPECTED_TAB_LABELS:
        problems.append(
            f"{rel}: top tabs {labels!r} != expected {list(EXPECTED_TAB_LABELS)!r}"
        )
    for label in labels:
        for pat in FORBIDDEN_TAB_PATTERNS:
            if pat.search(label):
                problems.append(f"{rel}: forbidden fallback tab label {label!r}")
                break
    return problems


def validate_tab_landings(
    rel: str, html_path: Path, label_hrefs: dict[str, str]
) -> list[str]:
    """断言意图分组 Tab 点击落点（按解析后的目标路径，兼容相对 ./ ../）。"""
    problems: list[str] = []
    for label, needle in EXPECTED_TAB_HREFS.items():
        href = label_hrefs.get(label, "")
        if not href:
            problems.append(f"{rel}: tab {label!r} missing href")
            continue
        target = resolve_href(html_path, href)
        try:
            rel_target = target.relative_to(SITE_DIR.resolve()).as_posix()
        except ValueError:
            rel_target = target.as_posix()
        needle_dir = needle.strip("/")
        if needle_dir not in rel_target.replace("\\", "/"):
            problems.append(
                f"{rel}: tab {label!r} href {href!r} → {rel_target!r} "
                f"should land under {needle_dir!r}"
            )
    return problems


def main() -> int:
    if not SITE_DIR.is_dir():
        print("site/ not found; run mkdocs build first", file=sys.stderr)
        return 1

    issues: list[tuple[str, str, str]] = []
    label_problems: list[str] = []
    checked = 0
    pages_found = 0

    for rel in SAMPLE_PAGES:
        html_path = SITE_DIR / rel
        if not html_path.is_file():
            print(f"  skip missing sample: {rel}", file=sys.stderr)
            continue
        pages_found += 1
        text = html_path.read_text(encoding="utf-8", errors="replace")
        labels = extract_top_tab_labels(text)
        label_hrefs = extract_top_tab_hrefs(text)
        label_problems.extend(validate_tab_labels(rel, labels))
        label_problems.extend(validate_tab_landings(rel, html_path, label_hrefs))
        hrefs = extract_menu_hrefs(text)
        checked += len(hrefs)
        for href in hrefs:
            target = resolve_href(html_path, href)
            if not target_exists(target, href):
                issues.append((rel, href, str(target)))

    print(f"Checked top-tab labels on {pages_found} sample pages")
    print(f"Checked {checked} tab menu href attributes on {pages_found} sample pages")
    print(f"Label issues: {len(label_problems)}")
    for msg in label_problems[:40]:
        print(f"  {msg}")
    if len(label_problems) > 40:
        print(f"  ... +{len(label_problems) - 40} more")
    print(f"Href issues: {len(issues)}")
    for src, href, target in issues[:40]:
        print(f"  {src} -> {href}")
        print(f"    missing: {target}")
    if len(issues) > 40:
        print(f"  ... +{len(issues) - 40} more")
    return 1 if issues or label_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
