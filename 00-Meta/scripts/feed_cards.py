#!/usr/bin/env python3
"""Feed 卡片 HTML 生成 — 对齐 developer.android.com/news 卡片结构。"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from content_policy import MODULE_TITLES, PUBLIC_MODULES, is_excluded_path, is_meta_file
from preamble_transform import strip_author_preamble

MODULE_MEDIA: dict[str, str] = {
    "00-Meta": "meta",
    "01-Mechanism": "mechanism",
    "02-Symptom": "symptom",
    "03-Forensics": "forensics",
    "04-Tool": "tool",
    "05-Governance": "governance",
    "06-Case": "case",
    "06-Foundation": "foundation",
}

# 系列卡片调色板：复用首页模块色，保证对比度与视觉语言一致
SERIES_PALETTE: tuple[str, ...] = (
    "mechanism",
    "symptom",
    "forensics",
    "tool",
    "governance",
    "case",
    "foundation",
    "meta",
)

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


@dataclass
class FeedCard:
    href: str
    title: str
    summary: str = ""
    label: str = ""
    date: str = ""
    media_module: str = "01-Mechanism"
    media_color: str = ""  # 可选 CSS slug 覆盖（系列卡片多色）
    media_text: str = ""
    variant: str = "default"  # default | series | module


@dataclass
class ArticleListItem:
    href: str
    title: str
    index: str = ""
    summary: str = ""
    date: str = ""
    label: str = ""  # 模块 / 分类短标签（用于最新更新等导航列表）


def to_site_href(path: str) -> str:
    """将 docs 相对路径转为 MkDocs directory URL（use_directory_urls=true）。"""
    href = path.replace("\\", "/").strip()
    if not href or href.startswith(("#", "http://", "https://", "mailto:")):
        return href
    if href.endswith(".md"):
        stem = href[:-3]
        if stem.endswith("/index"):
            stem = stem[: -len("index")]
        return f"{stem}/" if stem else "./"
    if not href.endswith("/"):
        href = f"{href}/"
    return href


def attr_href(url: str) -> str:
    """HTML 属性中的 href（保留中文与 % 等 URL 字符）。"""
    return html.escape(url, quote=False).replace('"', "&quot;")


def landing_frontmatter(title: str, *, hide_nav: bool = True) -> str:
    lines = ["---", f"title: {title}", "layout: landing"]
    if hide_nav:
        lines.extend(["hide:", "  - navigation", "  - toc"])
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def format_updated(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    dt = datetime.fromtimestamp(ts)
    return f"Updated {_MONTHS[dt.month - 1]} {dt.day}, {dt.year}"


def get_title_from_markdown(content: str, fallback: str) -> str:
    for line in content.splitlines():
        m = re.match(r"^\s*#\s+(.+)$", line)
        if m:
            return m.group(1).strip()
    name = Path(fallback).stem
    m = re.match(r"^\d+-(.+)$", name)
    return m.group(1) if m else name


def extract_summary(content: str, *, max_len: int = 120) -> str:
    text, _ = strip_author_preamble(content)
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith("---"):
            continue
        if s.startswith("```") or s.startswith("!!!") or s.startswith("- [") or s.startswith("* ["):
            continue
        if s.startswith(">"):
            s = s.lstrip("> ").strip()
        s = re.sub(r"\*+", "", s)
        s = re.sub(r"`+", "", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        if len(s) < 12:
            continue
        if any(k in s for k in ("目录", "TODO", "写作", "基线：", "源码基线", "返回 [")):
            continue
        if len(s) > max_len:
            s = s[: max_len - 1].rstrip() + "…"
        return s
    return ""


def module_for_path(path: Path, repo_root: Path | None = None) -> str:
    parts = path.parts
    if "docs" in parts:
        idx = parts.index("docs")
        if idx + 1 < len(parts) and parts[idx + 1] in PUBLIC_MODULES:
            return parts[idx + 1]
    for mod in PUBLIC_MODULES:
        if mod in parts:
            return mod
    if repo_root:
        try:
            rel = path.relative_to(repo_root)
            if rel.parts:
                first = rel.parts[0]
                if first == "docs" and len(rel.parts) > 1:
                    return rel.parts[1]
                if first in PUBLIC_MODULES:
                    return first
        except ValueError:
            pass
    return "01-Mechanism"


def module_media_slug(module: str) -> str:
    return MODULE_MEDIA.get(module, "mechanism")


def series_media_slug(key: str) -> str:
    """按系列目录名稳定映射到调色板色块（同系列跨页颜色一致）。"""
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(SERIES_PALETTE)
    return SERIES_PALETTE[idx]


def card_from_markdown(
    path: Path,
    *,
    href: str,
    label: str = "",
    repo_root: Path | None = None,
    module: str | None = None,
) -> FeedCard:
    content = path.read_text(encoding="utf-8", errors="replace")
    title = get_title_from_markdown(content, path.name)
    summary = extract_summary(content)
    mod = module or module_for_path(path, repo_root)
    if not label:
        label = MODULE_TITLES.get(mod, mod)
    return FeedCard(
        href=href,
        title=title,
        summary=summary,
        label=label,
        date=format_updated(path),
        media_module=mod,
        media_text=label[:1].upper() if label else "·",
    )


def render_page_hero(title: str, lead: str = "", *, chips: list[str] | None = None) -> str:
    chips_html = ""
    if chips:
        chips_html = '<div class="jk-page-hero__meta">\n'
        for i, chip in enumerate(chips):
            cls = "jk-chip jk-chip--accent" if i == 0 else "jk-chip"
            chips_html += f'  <span class="{cls}">{html.escape(chip)}</span>\n'
        chips_html += "</div>\n"
    lead_html = ""
    if lead:
        lead_html = f'  <p class="jk-page-hero__lead">{html.escape(lead)}</p>\n'
    return (
        f'<div class="jk-page-hero" markdown="0">\n'
        f"  <h1>{html.escape(title)}</h1>\n"
        f"{lead_html}"
        f"{chips_html}"
        f"</div>\n\n"
    )


def render_section_title(text: str) -> str:
    return f'<p class="jk-section-title"><strong>{html.escape(text)}</strong></p>\n\n'


def render_feed_card(card: FeedCard) -> str:
    media_slug = card.media_color or module_media_slug(card.media_module)
    is_nav_card = card.variant in ("series", "module")
    if is_nav_card:
        media_text = html.escape(card.media_text or card.title)
    else:
        media_text = html.escape(card.media_text or card.label[:1] or "·")
    title = html.escape(card.title)
    href = attr_href(to_site_href(card.href))
    card_mod = f" jk-feed-card--{card.variant}" if is_nav_card else ""
    card_class = f"jk-feed-card{card_mod}"
    label_html = ""
    if card.label and not is_nav_card:
        label_html = f'    <p class="jk-feed-label">{html.escape(card.label)}</p>\n'
    if is_nav_card:
        title_html = f'    <h3 class="jk-feed-card__title jk-sr-only">{title}</h3>\n'
    else:
        title_html = f'    <h3 class="jk-feed-card__title">{title}</h3>\n'
    summary_html = ""
    if card.summary and not is_nav_card:
        summary_html = f'    <p class="jk-feed-card__summary">{html.escape(card.summary)}</p>\n'
    date_html = ""
    if card.date and not is_nav_card:
        date_html = f'    <p class="jk-feed-card__date">{html.escape(card.date)}</p>\n'
    return (
        f'  <a class="{card_class}" href="{href}" title="{title}">\n'
        f'    <div class="jk-feed-card__media jk-feed-card__media--{media_slug}">'
        f'<span class="jk-feed-card__media-text">{media_text}</span></div>\n'
        f"{label_html}"
        f"{title_html}"
        f"{date_html}"
        f"{summary_html}"
        f"  </a>"
    )


def render_feed_grid(cards: list[FeedCard], *, grid_class: str = "") -> str:
    if not cards:
        return ""
    body = "\n".join(render_feed_card(c) for c in cards)
    extra_class = f" {grid_class}" if grid_class else ""
    return f'<div class="jk-feed-grid{extra_class}" markdown="0">\n{body}\n</div>\n\n'


def extract_index_from_filename(filename: str) -> str:
    """从文件名提取序号前缀（如 01-xxx.md → 01）。"""
    stem = Path(filename).stem
    m = re.match(r"^(\d+)", stem)
    return m.group(1) if m else ""


def article_item_from_markdown(
    path: Path,
    *,
    href: str,
    repo_root: Path | None = None,
) -> ArticleListItem:
    content = path.read_text(encoding="utf-8", errors="replace")
    title = get_title_from_markdown(content, path.name)
    summary = extract_summary(content, max_len=88)
    return ArticleListItem(
        href=href,
        title=title,
        index=extract_index_from_filename(path.name),
        summary=summary,
        date=format_updated(path),
    )


def render_article_list_item(item: ArticleListItem) -> str:
    href = attr_href(to_site_href(item.href))
    title = html.escape(item.title)
    index_html = ""
    if item.index:
        index_html = (
            f'      <span class="jk-article-list__index">{html.escape(item.index)}</span>\n'
        )
    elif item.label:
        index_html = (
            f'      <span class="jk-article-list__label">{html.escape(item.label)}</span>\n'
        )
    meta_parts: list[str] = []
    if item.date:
        meta_parts.append(html.escape(item.date))
    if item.summary and not item.label:
        meta_parts.append(html.escape(item.summary))
    meta_html = ""
    if meta_parts:
        meta_html = (
            f'        <span class="jk-article-list__meta">'
            f'{" · ".join(meta_parts)}</span>\n'
        )
    return (
        f'    <li class="jk-article-list__item">\n'
        f'      <a class="jk-article-list__link" href="{href}">\n'
        f"{index_html}"
        f'        <span class="jk-article-list__body">\n'
        f'          <span class="jk-article-list__title">{title}</span>\n'
        f"{meta_html}"
        f"        </span>\n"
        f"      </a>\n"
        f"    </li>"
    )


def render_article_list(
    items: list[ArticleListItem],
    *,
    aria_label: str = "系列篇章",
    list_class: str = "",
) -> str:
    if not items:
        return ""
    body = "\n".join(render_article_list_item(item) for item in items)
    extra_class = f" {list_class}" if list_class else ""
    return (
        f'<nav class="jk-article-list{extra_class}" aria-label="{html.escape(aria_label)}" markdown="0">\n'
        f'  <ol class="jk-article-list__items">\n'
        f"{body}\n"
        f"  </ol>\n"
        f"</nav>\n\n"
    )


def render_promo(
    *,
    title: str = "获取稳知库更新",
    lead: str = "Star 仓库或在 GitHub 上关注 Issues，跟踪 AOSP 17 稳定性系列更新。",
    button_label: str = "在 GitHub 上 Star",
    button_href: str = "https://github.com/yacob-wang/smc-pub",
) -> str:
    return (
        f'<div class="jk-promo" markdown="0">\n'
        f'  <div class="jk-promo__body">\n'
        f"    <h2 class=\"jk-promo__title\">{html.escape(title)}</h2>\n"
        f'    <p class="jk-promo__lead">{html.escape(lead)}</p>\n'
        f"  </div>\n"
        f'  <a class="jk-promo__button" href="{html.escape(button_href, quote=True)}" '
        f'target="_blank" rel="noopener">{html.escape(button_label)}</a>\n'
        f"</div>\n\n"
    )


def _is_article_file(path: Path) -> bool:
    if path.suffix.lower() != ".md":
        return False
    name = path.name.lower()
    if name == "index.md" or name.startswith("readme"):
        return False
    if is_meta_file(path.name):
        return False
    rel = path.as_posix()
    if is_excluded_path(Path(rel)):
        return False
    return True


def _collect_latest_article_paths(content_root: Path) -> list[Path]:
    paths: list[Path] = []
    for mod in PUBLIC_MODULES:
        mod_dir = content_root / mod
        if not mod_dir.is_dir():
            continue
        for path in mod_dir.rglob("*.md"):
            if not _is_article_file(path):
                continue
            try:
                rel = path.relative_to(content_root)
            except ValueError:
                continue
            if is_excluded_path(rel):
                continue
            paths.append(path)
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths


def collect_latest_articles(content_root: Path, *, limit: int = 12) -> list[FeedCard]:
    cards: list[FeedCard] = []
    for path in _collect_latest_article_paths(content_root)[:limit]:
        try:
            rel = path.relative_to(content_root)
        except ValueError:
            continue
        module = rel.parts[0] if rel.parts else "01-Mechanism"
        cards.append(
            card_from_markdown(
                path,
                href=to_site_href(str(rel).replace("\\", "/")),
                label=MODULE_TITLES.get(module, module),
                repo_root=content_root,
                module=module,
            )
        )
    return cards


def collect_latest_article_items(content_root: Path, *, limit: int = 12) -> list[ArticleListItem]:
    items: list[ArticleListItem] = []
    for path in _collect_latest_article_paths(content_root)[:limit]:
        try:
            rel = path.relative_to(content_root)
        except ValueError:
            continue
        module = rel.parts[0] if rel.parts else "01-Mechanism"
        content = path.read_text(encoding="utf-8", errors="replace")
        items.append(
            ArticleListItem(
                href=to_site_href(str(rel).replace("\\", "/")),
                title=get_title_from_markdown(content, path.name),
                date=format_updated(path),
                label=MODULE_TITLES.get(module, module),
            )
        )
    return items


def build_module_feed_cards() -> list[FeedCard]:
    cards: list[FeedCard] = []
    for mod in PUBLIC_MODULES:
        title = MODULE_TITLES.get(mod, mod)
        cards.append(
            FeedCard(
                href=to_site_href(f"{mod}/"),
                title=title,
                label="",
                date="",
                media_module=mod,
                media_text=title,
                variant="module",
            )
        )
    return cards
