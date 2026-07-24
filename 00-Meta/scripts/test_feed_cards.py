#!/usr/bin/env python3
"""feed_cards 与 series landing 列表渲染断言。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from feed_cards import (  # noqa: E402
    ArticleListItem,
    article_item_from_markdown,
    extract_index_from_filename,
    render_article_list,
)
from prepare_web_docs import (  # noqa: E402
    DOCS_DIR,
    build_module_index,
    build_series_landing_index,
    build_subcategory_index,
)

REPO = _SCRIPTS.parent.parent


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_extract_index_from_filename() -> None:
    _assert(extract_index_from_filename("01-背景.md") == "01", "numeric prefix")
    _assert(extract_index_from_filename("12-cgroup-v2.md") == "12", "two-digit prefix")
    _assert(extract_index_from_filename("overview.md") == "", "no prefix")


def test_render_article_list_structure() -> None:
    html = render_article_list(
        [
            ArticleListItem(
                href="01-first/",
                title="First Article",
                index="01",
                summary="Short intro",
                date="Updated Jul 1, 2026",
            ),
            ArticleListItem(
                href="02-second/",
                title="Second Article",
                index="02",
            ),
        ]
    )
    _assert("jk-article-list" in html, "list wrapper")
    _assert("jk-article-list__index" in html, "index chip")
    _assert('href="01-first/"' in html, "article href")
    _assert("First Article" in html, "title")
    _assert("Short intro" in html, "summary meta")
    _assert("jk-feed-grid" not in html, "not feed grid")


def test_article_item_from_markdown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "03-demo-topic.md"
        path.write_text("# Demo Title\n\nThis is a compact summary line.\n", encoding="utf-8")
        item = article_item_from_markdown(path, href="03-demo-topic.md")
    _assert(item.title == "Demo Title", "title from h1")
    _assert(item.index == "03", "index from filename")
    _assert("summary" in item.summary.lower() or "compact" in item.summary.lower(), "summary")


def test_series_landing_uses_list_not_cards() -> None:
    cgroup = REPO / "01-Mechanism/Kernel/cgroup"
    if not cgroup.is_dir():
        return
    html = build_series_landing_index("01-Mechanism", cgroup)
    _assert("jk-article-list" in html, "series uses article list")
    _assert("jk-feed-grid" not in html, "series no feed grid")


def test_module_index_still_uses_cards() -> None:
    kernel = DOCS_DIR if (DOCS_DIR / "01-Mechanism/Kernel").is_dir() else REPO / "01-Mechanism/Kernel"
    if not kernel.is_dir():
        return
    html = build_module_index("01-Mechanism", kernel)
    _assert("jk-feed-grid" in html, "module keeps feed grid")
    _assert("jk-article-list" not in html, "module no article list")


def test_subcategory_index_still_uses_cards() -> None:
    art = REPO / "01-Mechanism/Runtime/ART"
    if not art.is_dir():
        return
    html = build_subcategory_index("01-Mechanism", art)
    _assert("jk-feed-grid" in html, "subcategory keeps feed grid")
    _assert("jk-article-list" not in html, "subcategory no article list")


def main() -> int:
    tests = [
        test_extract_index_from_filename,
        test_render_article_list_structure,
        test_article_item_from_markdown,
        test_series_landing_uses_list_not_cards,
        test_module_index_still_uses_cards,
        test_subcategory_index_still_uses_cards,
    ]
    for fn in tests:
        fn()
        print(f"ok {fn.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
