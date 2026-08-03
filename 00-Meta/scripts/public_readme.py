#!/usr/bin/env python3
"""站点首页文案（Android Developers News 风格 — Hero + Feed 卡片流）。"""

from __future__ import annotations

import html
from pathlib import Path

from content_policy import PROBLEM_INDEX, PUBLIC_MODULES, is_excluded_path, is_meta_file
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

_SKIP_DIR_NAMES = frozenset(
    {
        "bridge",
        "appendix",
        "appendices",
        "assets",
        "images",
        "img",
        "scripts",
        "_archive",
        "_studio",
        "_drafts",
        "old",
    }
)


def _count_public_articles(content_root) -> int:
    """与 generate_article_catalog 一致的正文计数。"""
    total = 0
    for mod in PUBLIC_MODULES:
        mod_dir = content_root / mod
        if not mod_dir.is_dir():
            continue
        for path in mod_dir.rglob("*.md"):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name == "index.md" or name.startswith("readme"):
                continue
            if is_meta_file(path.name):
                continue
            try:
                rel = path.relative_to(content_root)
            except ValueError:
                continue
            if any(part.lower() in _SKIP_DIR_NAMES for part in rel.parts):
                continue
            if is_excluded_path(rel):
                continue
            total += 1
    return total


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
        f'<details class="jk-collapsible" open markdown="0">\n'
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
    # 优先按仓库源统计（与文章总目录一致）；docs 仅作回退
    count_root = repo_root or root
    article_count = _count_public_articles(count_root)
    if article_count == 0 and root != count_root:
        article_count = _count_public_articles(root)

    hero = render_page_hero(
        "稳知库 · Android 稳定性架构师系列",
        "从启动到性能 — 以稳定性问题为中心、横跨 Kernel / Native / Framework 的体系化参考。"
        "按 8 卷 50 章组织：机制、症状、工具、治理一条链路。",
        chips=[
            "AOSP 17 + android17-6.18",
            f"{article_count} 篇文章",
            "8 卷 50 章",
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

    catalog = (
        render_section_title("全站文章目录")
        + '<p class="jk-catalog-cta" markdown="0">'
        + f'共 <strong>{article_count}</strong> 篇文章。'
        + '按 <strong>卷 → 章 → 篇</strong> 浏览，表格支持跳转：'
        + f' <a href="{attr_href(to_site_href("文章总目录.md"))}">打开文章总目录</a>。'
        + "</p>\n\n"
    )

    problem_index = render_problem_index()

    promo = render_promo()
    foot = '<p class="jk-foot">© JacobKing · Stability Matrix Course</p>\n'

    body = hero + modules + catalog + problem_index + latest + promo + foot
    return landing_frontmatter("Home") + body


def build_public_readme(repo_root: Path | None = None, docs_dir: Path | None = None) -> str:
    return build_reader_homepage(repo_root, docs_dir=docs_dir)


def sanitize_readme(src: str) -> str:
    _ = src
    return build_reader_homepage()
