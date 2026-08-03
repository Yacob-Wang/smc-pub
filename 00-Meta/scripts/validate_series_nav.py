#!/usr/bin/env python3
"""审计叶子系列导航：.pages 须含系列总览与各篇章，单篇不得 not_in_nav。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from content_policy import PUBLIC_MODULES  # noqa: E402
from prepare_web_docs import (  # noqa: E402
    NAV_SKIP_DIR_NAMES,
    _article_files,
    _dir_has_content,
    _series_nav_entries,
)


def is_leaf_series(dir_path: Path) -> bool:
    if not dir_path.is_dir():
        return False
    nested = [
        p
        for p in dir_path.iterdir()
        if p.is_dir()
        and not p.name.startswith(".")
        and p.name.lower() not in NAV_SKIP_DIR_NAMES
        and _dir_has_content(p)
    ]
    if nested:
        return False
    return bool(_article_files(dir_path))


def parse_pages_nav(text: str) -> list[tuple[str, str]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    entries: list[tuple[str, str]] = []
    in_nav = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "nav:":
            in_nav = True
            continue
        if not in_nav or not stripped.startswith("- "):
            continue
        m = re.match(r'-\s+"((?:\\.|[^"\\])*)"\s*:\s*(.+)$', stripped)
        if not m:
            m = re.match(r"-\s+(.+?)\s*:\s*(.+)$", stripped)
        if m:
            title = m.group(1).replace('\\"', '"')
            target = m.group(2).strip()
            entries.append((title, target))
    return entries


def pages_matches_series_nav(dir_path: Path, text: str) -> bool:
    expected = _series_nav_entries(dir_path)
    return parse_pages_nav(text) == expected


def has_not_in_nav(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.lstrip().startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    return bool(re.search(r"(?m)^\s*not_in_nav\s*:\s*true\s*$", parts[1]))


def main() -> int:
    if not DOCS_DIR.is_dir():
        print("docs/ not found; run prepare_web_docs.py first", file=sys.stderr)
        return 1

    bad_pages: list[str] = []
    bad_articles: list[str] = []
    leaf_count = 0
    article_count = 0

    module_roots = {DOCS_DIR / mod for mod in PUBLIC_MODULES}

    for mod in PUBLIC_MODULES:
        mod_dir = DOCS_DIR / mod
        if not mod_dir.is_dir():
            continue
        for dir_path in [mod_dir, *sorted(mod_dir.rglob("*"))]:
            if dir_path in module_roots:
                continue
            if not dir_path.is_dir() or not is_leaf_series(dir_path):
                continue
            leaf_count += 1
            pages = dir_path / ".pages"
            raw = pages.read_text(encoding="utf-8") if pages.is_file() else ""
            if not pages_matches_series_nav(dir_path, raw):
                bad_pages.append(str(dir_path.relative_to(DOCS_DIR)))
            for fname in _article_files(dir_path):
                article_count += 1
                if has_not_in_nav(dir_path / fname):
                    bad_articles.append(str((dir_path / fname).relative_to(DOCS_DIR)))

    print(f"leaf series: {leaf_count}; articles checked: {article_count}")
    if bad_pages:
        print(f"BAD .pages ({len(bad_pages)}):")
        for p in bad_pages[:40]:
            print(f"  {p}")
        if len(bad_pages) > 40:
            print(f"  ... +{len(bad_pages) - 40}")
    if bad_articles:
        print(f"STALE not_in_nav ({len(bad_articles)}):")
        for p in bad_articles[:40]:
            print(f"  {p}")
        if len(bad_articles) > 40:
            print(f"  ... +{len(bad_articles) - 40}")

    if bad_pages or bad_articles:
        return 1
    print("OK: all leaf series list articles in nav (no not_in_nav)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
