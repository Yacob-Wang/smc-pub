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
    FeedCard,
    article_item_from_markdown,
    extract_index_from_filename,
    render_article_list,
    render_feed_card,
    series_media_slug,
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


def test_render_series_feed_card_is_minimal() -> None:
    html = render_feed_card(
        FeedCard(
            href="Activity/",
            title="Activity 系列导读",
            media_module="01-Mechanism",
            media_color="forensics",
            media_text="Activity 系列导读",
            variant="series",
        )
    )
    _assert("jk-feed-card--series" in html, "series modifier class")
    _assert("jk-feed-card__media--forensics" in html, "series uses palette color")
    _assert("Activity 系列导读" in html, "title in media text")
    _assert("jk-feed-label" not in html, "no module label")
    _assert("jk-feed-card__summary" not in html, "no summary")
    _assert("jk-feed-card__date" not in html, "no date")
    _assert("作者角色" not in html, "no author blurb")
    _assert("jk-sr-only" in html, "sr-only title for a11y")


def test_series_media_slug_is_stable_and_varied() -> None:
    a = series_media_slug("Kernel")
    b = series_media_slug("Kernel")
    c = series_media_slug("Framework")
    _assert(a == b, "stable hash for same series")
    _assert(a != c, "different series get different colors")
    _assert(len(a) > 0, "non-empty slug")


def test_module_index_series_cards_use_varied_colors() -> None:
    mod_dir = REPO / "01-Mechanism"
    if not mod_dir.is_dir():
        return
    html = build_module_index("01-Mechanism", mod_dir)
    _assert("jk-feed-grid" in html, "module keeps feed grid")
    _assert("jk-article-list" not in html, "module no article list")
    _assert("jk-feed-card--series" in html, "module landing uses series cards")
    _assert("jk-feed-card__summary" not in html, "module landing no card summaries")
    colors = {
        slug
        for slug in (
            "mechanism",
            "symptom",
            "forensics",
            "tool",
            "governance",
            "case",
            "foundation",
            "meta",
        )
        if f"jk-feed-card__media--{slug}" in html
    }
    _assert(len(colors) >= 2, "module landing uses multiple series colors")


def test_subcategory_index_still_uses_cards() -> None:
    art = REPO / "01-Mechanism/Runtime/ART"
    if not art.is_dir():
        return
    html = build_subcategory_index("01-Mechanism", art)
    _assert("jk-feed-grid" in html, "subcategory keeps feed grid")
    _assert("jk-article-list" not in html, "subcategory no article list")
    _assert("jk-feed-card--series" in html, "subcategory uses series cards")
    _assert("jk-feed-card__summary" not in html, "subcategory no summaries")


def test_render_module_feed_card_is_minimal() -> None:
    html = render_feed_card(
        FeedCard(
            href="01-Mechanism/",
            title="Mechanism",
            media_module="01-Mechanism",
            media_text="Mechanism",
            variant="module",
        )
    )
    _assert("jk-feed-card--module" in html, "module modifier class")
    _assert("Mechanism" in html, "title in media text")
    _assert("jk-feed-label" not in html, "no module label")
    _assert("jk-feed-card__summary" not in html, "no summary")
    _assert("jk-feed-card__date" not in html, "no date")
    _assert("jk-sr-only" in html, "sr-only title for a11y")


def test_render_problem_index_html() -> None:
    from public_readme import render_problem_index  # noqa: E402

    html = render_problem_index()
    _assert("jk-problem-index" in html, "problem index wrapper")
    _assert("| **" not in html, "no raw markdown table")
    _assert("](02-Symptom/S01-ANR/" not in html, "no raw markdown links")
    _assert('href="02-Symptom/S01-ANR/"' in html, "ANR link href")
    _assert("ANR 症状" in html, "ANR link label")
    _assert("按问题进入" in html, "summary text")


def test_homepage_uses_list_for_latest() -> None:
    from public_readme import build_reader_homepage  # noqa: E402

    html = build_reader_homepage(REPO)
    _assert("jk-article-list--latest" in html, "latest uses article list")
    _assert("最新更新" in html, "latest section title")
    _assert("jk-feed-card__summary" not in html, "homepage no card summaries")
    _assert("Author · JacobKing" not in html, "no author chip")
    _assert("jk-feed-card--module" in html, "module nav cards")
    modules_start = html.find("模块导览")
    problem_start = html.find("按问题进入")
    latest_start = html.find("jk-article-list--latest")
    _assert(
        modules_start != -1 and problem_start != -1 and latest_start != -1,
        "sections present",
    )
    _assert(
        modules_start < problem_start < latest_start,
        "section order: modules, problem, latest",
    )
    modules_slice = html[modules_start:problem_start]
    _assert("jk-feed-grid" in modules_slice, "modules section uses feed grid")
    problem_slice = html[problem_start:latest_start]
    _assert("jk-problem-index" in problem_slice, "problem index section")
    latest_slice = html[latest_start:]
    _assert("jk-feed-grid" not in latest_slice, "latest section no feed grid")
    _assert("jk-article-list--latest" in latest_slice, "latest section uses list")


def test_meta_module_index_has_hub_cards() -> None:
    mod_dir = REPO / "00-Meta"
    if not mod_dir.is_dir():
        return
    html = build_module_index("00-Meta", mod_dir)
    _assert("稳定性架构师知识库导航" in html, "meta hero title")
    _assert("jk-feed-grid" in html, "meta hub uses feed grid")
    _assert('href="学习路线-稳定性架构师/"' in html, "learning path card")
    _assert('href="阅读指南/"' in html, "reading guide card")
    _assert('href="JD匹配矩阵/"' in html, "jd matrix card")
    _assert('href="缺口一览/"' in html, "gap overview card")
    _assert('href="Reference/"' in html, "reference card")


def main() -> int:
    tests = [
        test_extract_index_from_filename,
        test_render_article_list_structure,
        test_article_item_from_markdown,
        test_render_series_feed_card_is_minimal,
        test_series_media_slug_is_stable_and_varied,
        test_render_module_feed_card_is_minimal,
        test_render_problem_index_html,
        test_homepage_uses_list_for_latest,
        test_series_landing_uses_list_not_cards,
        test_module_index_series_cards_use_varied_colors,
        test_subcategory_index_still_uses_cards,
        test_meta_module_index_has_hub_cards,
    ]
    for fn in tests:
        fn()
        print(f"ok {fn.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
