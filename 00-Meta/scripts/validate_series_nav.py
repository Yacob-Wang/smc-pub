#!/usr/bin/env python3
"""审计叶子系列导航：侧栏只挂系列总览，单篇须 not_in_nav。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from content_policy import PUBLIC_MODULES  # noqa: E402
from prepare_web_docs import NAV_SKIP_DIR_NAMES, _dir_has_content  # noqa: E402


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
    articles = [
        p
        for p in dir_path.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".md"
        and p.name.lower() != "index.md"
        and not p.name.lower().startswith("readme")
    ]
    return bool(articles)


def pages_is_series_overview_only(text: str) -> bool:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
    return lines == [
        "collapse: true",
        "nav:",
        '  - "系列总览": index.md',
    ]


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

    for mod in PUBLIC_MODULES:
        mod_dir = DOCS_DIR / mod
        if not mod_dir.is_dir():
            continue
        for dir_path in [mod_dir, *sorted(mod_dir.rglob("*"))]:
            if not dir_path.is_dir() or not is_leaf_series(dir_path):
                continue
            leaf_count += 1
            pages = dir_path / ".pages"
            raw = pages.read_text(encoding="utf-8") if pages.is_file() else ""
            if not pages_is_series_overview_only(raw):
                bad_pages.append(str(dir_path.relative_to(DOCS_DIR)))
            for p in sorted(dir_path.iterdir()):
                if not p.is_file() or p.suffix.lower() != ".md":
                    continue
                name = p.name.lower()
                if name == "index.md" or name.startswith("readme"):
                    continue
                article_count += 1
                if not has_not_in_nav(p):
                    bad_articles.append(str(p.relative_to(DOCS_DIR)))

    print(f"leaf series: {leaf_count}; articles checked: {article_count}")
    if bad_pages:
        print(f"BAD .pages ({len(bad_pages)}):")
        for p in bad_pages[:40]:
            print(f"  {p}")
        if len(bad_pages) > 40:
            print(f"  ... +{len(bad_pages) - 40}")
    if bad_articles:
        print(f"MISSING not_in_nav ({len(bad_articles)}):")
        for p in bad_articles[:40]:
            print(f"  {p}")
        if len(bad_articles) > 40:
            print(f"  ... +{len(bad_articles) - 40}")

    if bad_pages or bad_articles:
        return 1
    print("OK: all leaf series use series-overview-only nav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
