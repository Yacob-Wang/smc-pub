#!/usr/bin/env python3
"""检查构建产物中顶栏下拉与二级 flyout 的 href 是否有效。"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SITE_DIR = REPO_ROOT / "site"

HREF_RE = re.compile(r'href="([^"#]+)"')

# 每个顶层模块至少 1 页；Mechanism 含 flyout 深层页
SAMPLE_PAGES = [
    "index.html",
    "00-Meta/index.html",
    "01-Mechanism/index.html",
    "01-Mechanism/Kernel/index.html",
    "01-Mechanism/Kernel/Memory_Management/index.html",
    "02-Symptom/index.html",
    "02-Symptom/S01-ANR/index.html",
    "03-Forensics/index.html",
    "04-Tool/index.html",
    "05-Governance/index.html",
    "06-Case/index.html",
    "06-Foundation/index.html",
    "06-Foundation/Tools/Tracing/index.html",
]


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


def extract_menu_hrefs(html: str) -> list[str]:
    parser = TabMenuHrefParser()
    parser.feed(html)
    return parser.hrefs


def resolve_href(source: Path, href: str) -> Path:
    href = unquote(href.replace("&amp;", "&"))
    if href.startswith("/"):
        return SITE_DIR / href.lstrip("/")
    return (source.parent / href).resolve()


def target_exists(target: Path, href: str) -> bool:
    if href.endswith("/"):
        return (target / "index.html").is_file()
    return target.is_file() or (target / "index.html").is_file()


def main() -> int:
    if not SITE_DIR.is_dir():
        print("site/ not found; run mkdocs build first", file=sys.stderr)
        return 1

    issues: list[tuple[str, str, str]] = []
    checked = 0
    pages_found = 0

    for rel in SAMPLE_PAGES:
        html_path = SITE_DIR / rel
        if not html_path.is_file():
            print(f"  skip missing sample: {rel}", file=sys.stderr)
            continue
        pages_found += 1
        text = html_path.read_text(encoding="utf-8", errors="replace")
        hrefs = extract_menu_hrefs(text)
        checked += len(hrefs)
        for href in hrefs:
            target = resolve_href(html_path, href)
            if not target_exists(target, href):
                issues.append((rel, href, str(target)))

    print(f"Checked {checked} tab menu href attributes on {pages_found} sample pages")
    print(f"Issues: {len(issues)}")
    for src, href, target in issues[:40]:
        print(f"  {src} -> {href}")
        print(f"    missing: {target}")
    if len(issues) > 40:
        print(f"  ... +{len(issues) - 40} more")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
