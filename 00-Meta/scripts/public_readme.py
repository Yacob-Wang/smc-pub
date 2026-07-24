#!/usr/bin/env python3
"""站点首页文案（Android Developers News 风格 — Hero + Feed 卡片流）。"""

from __future__ import annotations

import html
from pathlib import Path

from content_policy import PROBLEM_INDEX, PUBLIC_MODULES
from feed_cards import (
    attr_href,
    build_module_feed_cards,
    collect_latest_article_items,
    landing_frontmatter,
    render_article_list,
    render_feed_grid,
    render_page_hero,
    render_promo,
    render_section_title,
    to_site_href,
)


def _render_problem_index_row(problem: str, links: list[tuple[str, str]]) -> str:
    link_html = "".join(
        f'        <a class="jk-problem-index__link" href="{attr_href(to_site_href(path))}">'
        f"{html.escape(label)}</a>\n"
        for label, path in links
    )
    return (
        f'    <li class="jk-problem-index__item">\n'
        f'      <span class="jk-problem-index__label">{html.escape(problem)}</span>\n'
        f'      <span class="jk-problem-index__links">\n'
        f"{link_html}"
        f"      </span>\n"
        f"    </li>"
    )


def render_problem_index() -> str:
    rows = "\n".join(_render_problem_index_row(problem, links) for problem, links in PROBLEM_INDEX)
    return (
        f'<details class="jk-collapsible" markdown="0">\n'
        f'  <summary>按问题进入</summary>\n'
        f'  <div class="jk-collapsible__body">\n'
        f'    <nav class="jk-problem-index" aria-label="按问题进入">\n'
        f'      <ul class="jk-problem-index__items">\n'
        f"{rows}\n"
        f"      </ul>\n"
        f"    </nav>\n"
        f"  </div>\n"
        f"</details>\n\n"
    )


def build_reader_homepage(repo_root: Path | None = None, docs_dir: Path | None = None) -> str:
    root = docs_dir or repo_root or Path(__file__).resolve().parent.parent.parent
    article_count = sum(
        1
        for mod in PUBLIC_MODULES
        for path in (root / mod).rglob("*.md")
        if path.is_file() and not path.name.lower().startswith("readme") and path.name.lower() != "index.md"
    )

    hero = render_page_hero(
        "稳知库 · Android 稳定性架构师系列",
        "从 Linux 内核到 Framework、从 ART 到应用层 — 按 AOSP 系统分层与 oncall 工作流组织，"
        "覆盖 Crash / ANR / OOM / 性能退化等 11 大症状。",
        chips=[
            "AOSP 17 + android17-6.18",
            f"{article_count} 篇文章",
            "8 大分类",
        ],
    )

    latest = render_section_title("最新更新") + render_article_list(
        collect_latest_article_items(root, limit=12),
        aria_label="最新更新",
        list_class="jk-article-list--latest",
    )
    modules = render_section_title("模块导览") + render_feed_grid(
        build_module_feed_cards(),
        grid_class="jk-feed-grid--modules",
    )

    problem_index = render_problem_index()

    promo = render_promo()
    foot = '<p class="jk-foot">© JacobKing · Stability Matrix Course</p>\n'

    body = hero + modules + problem_index + latest + promo + foot
    return landing_frontmatter("Home") + body


def build_public_readme(repo_root: Path | None = None, docs_dir: Path | None = None) -> str:
    return build_reader_homepage(repo_root, docs_dir=docs_dir)


def sanitize_readme(src: str) -> str:
    _ = src
    return build_reader_homepage()
