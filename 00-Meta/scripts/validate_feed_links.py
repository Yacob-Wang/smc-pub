#!/usr/bin/env python3
"""检查 docs/ 内 Feed 卡片 HTML href 与首页问题索引链接。"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from content_policy import PROBLEM_INDEX  # noqa: E402

HTML_HREF_RE = re.compile(r'href="([^"#]+)"')
MD_LINK_RE = re.compile(r'(?<!!)\[([^\]]*)\]\(([^)]+)\)')


def resolve_href(source: Path, href: str) -> Path:
    if href.startswith("/"):
        return DOCS_DIR / href.lstrip("/")
    return (source.parent / href).resolve()


def target_exists(target: Path, href: str) -> bool:
    if href.endswith("/"):
        if (target / "index.md").is_file():
            return True
        sibling_md = target.parent / f"{target.name}.md"
        if sibling_md.is_file():
            return True
        return target.is_dir()
    if href.endswith(".md"):
        return target.is_file()
    return target.is_file() or (target / "index.md").is_file() or target.is_dir()


def normalize_href(href: str) -> str:
    return unquote(href.replace("&amp;", "&").replace("&quot;", '"').strip())


def is_external(href: str) -> bool:
    return href.startswith(("http://", "https://", "mailto:", "#"))


def validate_html_hrefs(md: Path, text: str) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    rel = str(md.relative_to(DOCS_DIR))
    for href in HTML_HREF_RE.findall(text):
        if is_external(href):
            continue
        href = normalize_href(href)
        target = resolve_href(md, href)
        if not target_exists(target, href):
            issues.append((rel, href, str(target)))
    return issues


def validate_markdown_links(md: Path, text: str) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    rel = str(md.relative_to(DOCS_DIR))
    for _label, raw in MD_LINK_RE.findall(text):
        href = normalize_href(raw.split()[0])
        if is_external(href):
            continue
        target = resolve_href(md, href)
        if not target_exists(target, href):
            issues.append((rel, href, str(target)))
    return issues


def validate_problem_index() -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    for _problem, links in PROBLEM_INDEX:
        for _label, path in links:
            target = DOCS_DIR / path.rstrip("/")
            href = path if path.endswith("/") else path + "/"
            if not target_exists(target, href):
                issues.append(("PROBLEM_INDEX", path, str(target)))
    return issues


def main() -> int:
    if not DOCS_DIR.is_dir():
        print("docs/ not found; run prepare_web_docs.py first", file=sys.stderr)
        return 1

    issues: list[tuple[str, str, str]] = []
    html_count = 0

    for md in DOCS_DIR.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        html_hrefs = [h for h in HTML_HREF_RE.findall(text) if not is_external(h)]
        html_count += len(html_hrefs)
        issues.extend(validate_html_hrefs(md, text))

    index_md = DOCS_DIR / "index.md"
    md_link_count = 0
    if index_md.is_file():
        index_text = index_md.read_text(encoding="utf-8", errors="replace")
        md_issues = validate_markdown_links(index_md, index_text)
        md_link_count = len(
            [
                h
                for _l, h in MD_LINK_RE.findall(index_text)
                if not is_external(normalize_href(h.split()[0]))
            ]
        )
        issues.extend(md_issues)

    issues.extend(validate_problem_index())

    print(f"Checked {html_count} HTML href attributes + {md_link_count} homepage Markdown links")
    print(f"Issues: {len(issues)}")
    for src, href, target in issues[:50]:
        print(f"  {src} -> {href}")
        print(f"    missing: {target}")
    if len(issues) > 50:
        print(f"  ... +{len(issues) - 50} more")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
