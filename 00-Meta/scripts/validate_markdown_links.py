#!/usr/bin/env python3
"""检查 docs/ 内 Markdown 相对链接是否指向存在的文件或目录。

默认只检查 landing 页与首页（发布关键路径）。
使用 --full 扫描全部 docs/；使用 --fail 在有问题时返回非零退出码。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"

MD_LINK_RE = re.compile(r'(?<!!)\[([^\]]*)\]\(([^)]+)\)')
REF_LINK_RE = re.compile(r'\[[^\]]*\]\: (\S+)')


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
    return unquote(href.split()[0].strip().replace("&amp;", "&"))


def is_skipped(href: str) -> bool:
    return href.startswith(("http://", "https://", "mailto:", "#"))


def is_landing_page(md: Path) -> bool:
    head = md.read_text(encoding="utf-8", errors="replace")[:400]
    return head.startswith("---") and "layout: landing" in head.split("---", 2)[1]


def collect_targets(full: bool) -> list[Path]:
    if full:
        return sorted(DOCS_DIR.rglob("*.md"))
    targets = [DOCS_DIR / "index.md"]
    for md in DOCS_DIR.rglob("*.md"):
        if md == targets[0]:
            continue
        if is_landing_page(md):
            targets.append(md)
    return targets


def validate_file(md: Path) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    rel = str(md.relative_to(DOCS_DIR))
    text = md.read_text(encoding="utf-8", errors="replace")
    for _label, raw in MD_LINK_RE.findall(text):
        href = normalize_href(raw)
        if is_skipped(href):
            continue
        target = resolve_href(md, href)
        if not target_exists(target, href):
            issues.append((rel, href, str(target)))
    for raw in REF_LINK_RE.findall(text):
        href = normalize_href(raw)
        if is_skipped(href):
            continue
        target = resolve_href(md, href)
        if not target_exists(target, href):
            issues.append((rel, href, str(target)))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="扫描 docs/ 下全部 Markdown")
    parser.add_argument("--fail", action="store_true", help="发现问题时返回退出码 1")
    args = parser.parse_args()

    if not DOCS_DIR.is_dir():
        print("docs/ not found; run prepare_web_docs.py first", file=sys.stderr)
        return 1

    targets = collect_targets(args.full)
    issues: list[tuple[str, str, str]] = []
    for md in targets:
        if md.is_file():
            issues.extend(validate_file(md))

    scope = "all docs" if args.full else "homepage + landing pages"
    print(f"Checked Markdown links in {len(targets)} files ({scope})")
    print(f"Issues: {len(issues)}")
    for src, href, target in issues[:50]:
        print(f"  {src} -> {href}")
        print(f"    missing: {target}")
    if len(issues) > 50:
        print(f"  ... +{len(issues) - 50} more")
    if issues and args.fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
