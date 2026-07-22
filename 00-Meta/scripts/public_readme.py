#!/usr/bin/env python3
"""站点首页文案（Android Developers News 风格 — Hero + Feed 卡片流）。"""

from __future__ import annotations

from pathlib import Path

from content_policy import MODULE_BLURBS, MODULE_TITLES, PROBLEM_INDEX, PUBLIC_MODULES
from feed_cards import (
    build_module_feed_cards,
    collect_latest_articles,
    landing_frontmatter,
    render_feed_grid,
    render_page_hero,
    render_promo,
    render_section_title,
)


def render_problem_index() -> str:
    rows: list[str] = []
    for problem, links in PROBLEM_INDEX:
        link_parts = " · ".join(f"[{label}]({path})" for label, path in links)
        rows.append(f"| **{problem}** | {link_parts} |")
    table = "\n".join(rows)
    return f"""
<details class="jk-collapsible" markdown="0">
  <summary>按问题进入</summary>
  <div class="jk-collapsible__body" markdown="1">

| 问题 | 入口 |
|------|------|
{table}

  </div>
</details>
"""


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
        "面向 Android 稳定性架构师的技术博客。从 Linux 内核到 Framework、从 ART 运行时到应用层，"
        "按 AOSP 系统分层 + oncall 工作流双轴组织 — 覆盖 Crash / ANR / OOM / 性能退化全部 11 大症状。",
        chips=[
            "Author · JacobKing",
            "AOSP 17 + android17-6.18",
            f"{article_count} 篇 · 8 大分类",
        ],
    )

    latest = render_section_title("最新更新") + render_feed_grid(
        collect_latest_articles(root, limit=12)
    )
    modules = render_section_title("模块导览") + render_feed_grid(build_module_feed_cards())

    problem_index = render_problem_index()

    promo = render_promo()
    foot = '<p class="jk-foot">© JacobKing · Stability Matrix Course</p>\n'

    body = hero + latest + modules + problem_index + promo + foot
    return landing_frontmatter("Home") + body


def build_public_readme(repo_root: Path | None = None, docs_dir: Path | None = None) -> str:
    return build_reader_homepage(repo_root, docs_dir=docs_dir)


def sanitize_readme(src: str) -> str:
    _ = src
    return build_reader_homepage()
