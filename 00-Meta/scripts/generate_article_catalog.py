#!/usr/bin/env python3
"""扫描公开模块，生成根目录「文章总目录.md」，并刷新 README 中的目录统计标记块。

用法:
  python 00-Meta/scripts/generate_article_catalog.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from content_policy import (  # noqa: E402
    MODULE_BLURBS,
    MODULE_TITLES,
    PUBLIC_MODULES,
    is_excluded_path,
    is_meta_file,
)
from feed_cards import extract_index_from_filename, get_title_from_markdown  # noqa: E402

REPO_ROOT = _SCRIPTS.parent.parent
CATALOG_PATH = REPO_ROOT / "文章总目录.md"
README_PATH = REPO_ROOT / "README.md"

STATS_START = "<!-- CATALOG-STATS:START -->"
STATS_END = "<!-- CATALOG-STATS:END -->"
SERIES_START = "<!-- CATALOG-SERIES:START -->"
SERIES_END = "<!-- CATALOG-SERIES:END -->"

SKIP_DIR_NAMES = frozenset(
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

MODULE_CN = {
    "00-Meta": "元信息 / 地图",
    "01-Mechanism": "机制（AOSP 分层）",
    "02-Symptom": "症状",
    "03-Forensics": "取证",
    "04-Tool": "工具",
    "05-Governance": "治理",
    "06-Case": "案例",
    "06-Foundation": "基础",
}

ROOT_SERIES_LABEL = "（模块根）"


@dataclass
class Article:
    rel_posix: str
    title: str
    index: str
    filename: str


@dataclass
class Series:
    path: str  # relative to module, e.g. Kernel/Binder；空串 = 模块根
    articles: list[Article] = field(default_factory=list)

    @property
    def display(self) -> str:
        return self.path.replace("/", " / ") if self.path else ROOT_SERIES_LABEL

    @property
    def folder_link(self) -> str:
        if self.path:
            return f"{self.module}/{self.path}/"
        return f"{self.module}/"

    module: str = ""


@dataclass
class ModuleCatalog:
    name: str
    series: list[Series] = field(default_factory=list)

    @property
    def article_count(self) -> int:
        return sum(len(s.articles) for s in self.series)

    @property
    def series_count(self) -> int:
        return len(self.series)


def natural_key(name: str) -> tuple:
    stem = Path(name).stem
    m = re.match(r"^(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    m = re.match(r"^[A-Za-z]+(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    return (1, 0, stem.lower())


def series_sort_key(path: str) -> tuple:
    if not path:
        return (-1, ())
    parts = path.split("/")
    return (0, tuple(natural_key(p) for p in parts))


def _path_has_skipped_dir(rel: Path) -> bool:
    return any(part.lower() in SKIP_DIR_NAMES for part in rel.parts)


def is_article_file(path: Path, repo_root: Path) -> bool:
    if path.suffix.lower() != ".md":
        return False
    name = path.name.lower()
    if name == "index.md" or name.startswith("readme"):
        return False
    if is_meta_file(path.name):
        return False
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return False
    if _path_has_skipped_dir(rel):
        return False
    if is_excluded_path(rel):
        return False
    return True


def collect_modules(repo_root: Path) -> list[ModuleCatalog]:
    modules: list[ModuleCatalog] = []
    for mod in PUBLIC_MODULES:
        mod_dir = repo_root / mod
        if not mod_dir.is_dir():
            continue
        by_series: dict[str, list[Article]] = defaultdict(list)
        for path in mod_dir.rglob("*.md"):
            if not is_article_file(path, repo_root):
                continue
            rel = path.relative_to(repo_root)
            rel_posix = rel.as_posix()
            parent_rel = path.parent.relative_to(mod_dir)
            series_path = "" if parent_rel == Path(".") else parent_rel.as_posix()
            content = path.read_text(encoding="utf-8", errors="replace")
            title = get_title_from_markdown(content, path.name)
            by_series[series_path].append(
                Article(
                    rel_posix=rel_posix,
                    title=title,
                    index=extract_index_from_filename(path.name),
                    filename=path.name,
                )
            )

        series_list: list[Series] = []
        for series_path, articles in by_series.items():
            articles.sort(key=lambda a: natural_key(a.filename))
            series_list.append(
                Series(path=series_path, articles=articles, module=mod)
            )
        series_list.sort(key=lambda s: series_sort_key(s.path))
        modules.append(ModuleCatalog(name=mod, series=series_list))
    return modules


def module_anchor(mod: str) -> str:
    return mod.lower()


def build_catalog_md(modules: list[ModuleCatalog]) -> str:
    total_articles = sum(m.article_count for m in modules)
    total_series = sum(m.series_count for m in modules)
    lines: list[str] = [
        "# 文章总目录",
        "",
        "> **自动生成，请勿手改。** 更新命令：",
        "> ```bash",
        "> py -3.12 00-Meta/scripts/generate_article_catalog.py",
        "> ```",
        ">",
        f"> 当前收录：**{total_articles}** 篇正文 · **{total_series}** 个二级系列 · "
        f"**{len(modules)}** 个一级模块。",
        "",
        "## 快速导航",
        "",
        "| 一级模块 | 中文 | 二级系列 | 文章数 | 跳转 |",
        "|:---------|:-----|--------:|-------:|:-----|",
    ]
    for m in modules:
        cn = MODULE_CN.get(m.name, MODULE_TITLES.get(m.name, m.name))
        anchor = module_anchor(m.name)
        lines.append(
            f"| [`{m.name}`]({m.name}/) | {cn} | {m.series_count} | {m.article_count} "
            f"| [↓](#{anchor}) |"
        )

    lines.extend(["", "---", ""])

    for m in modules:
        cn = MODULE_CN.get(m.name, "")
        title = MODULE_TITLES.get(m.name, m.name)
        blurb = MODULE_BLURBS.get(m.name, "")
        lines.append(f'<a id="{module_anchor(m.name)}"></a>')
        lines.append("")
        lines.append(f"## {m.name} · {cn or title}")
        lines.append("")
        if blurb:
            lines.append(f"> {blurb}")
            lines.append("")
        lines.append(
            f"共 **{m.series_count}** 个二级系列、**{m.article_count}** 篇文章 · "
            f"[打开模块目录]({m.name}/) · [返回快速导航](#快速导航)"
        )
        lines.append("")

        for s in m.series:
            folder = f"{m.name}/{s.path}/" if s.path else f"{m.name}/"
            lines.append(f"### {s.display}")
            lines.append("")
            lines.append(f"[打开系列目录]({folder}) · {len(s.articles)} 篇")
            lines.append("")
            lines.append("| 序号 | 标题 | 链接 |")
            lines.append("|:-----|:-----|:-----|")
            for art in s.articles:
                idx = art.index or "—"
                # Escape pipe in titles for markdown tables
                title_safe = art.title.replace("|", "\\|")
                link = f"[`{art.filename}`]({art.rel_posix})"
                lines.append(f"| {idx} | {title_safe} | {link} |")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"*生成脚本：`00-Meta/scripts/generate_article_catalog.py` · "
        f"共 {total_articles} 篇*"
    )
    lines.append("")
    return "\n".join(lines)


def build_stats_block(modules: list[ModuleCatalog]) -> str:
    total = sum(m.article_count for m in modules)
    lines = [
        STATS_START,
        "",
        f"| 一级模块 | 角色 | 二级系列 | 文章数 | 目录 |",
        f"|:---------|:-----|--------:|-------:|:-----|",
    ]
    for m in modules:
        cn = MODULE_CN.get(m.name, MODULE_TITLES.get(m.name, m.name))
        blurb = MODULE_BLURBS.get(m.name, "")
        role = blurb if blurb else cn
        lines.append(
            f"| **{m.name}** | {role} | {m.series_count} | {m.article_count} "
            f"| [{m.name}/]({m.name}/) |"
        )
    lines.append(f"| **合计** | | | **{total}** | [文章总目录](文章总目录.md) |")
    lines.extend(["", STATS_END])
    return "\n".join(lines)


def build_series_block(modules: list[ModuleCatalog]) -> str:
    lines = [SERIES_START, ""]
    for m in modules:
        cn = MODULE_CN.get(m.name, MODULE_TITLES.get(m.name, m.name))
        lines.append(f"### {m.name} · {cn}")
        lines.append("")
        lines.append("| 二级系列 | 文章数 | 目录 |")
        lines.append("|:---------|-------:|:-----|")
        for s in m.series:
            folder = f"{m.name}/{s.path}/" if s.path else f"{m.name}/"
            lines.append(
                f"| {s.display} | {len(s.articles)} | [{folder}]({folder}) |"
            )
        lines.append("")
    lines.append(SERIES_END)
    return "\n".join(lines)


def replace_marked_block(text: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    if not pattern.search(text):
        raise RuntimeError(f"README 缺少标记块 {start} … {end}")
    return pattern.sub(lambda _m: replacement, text, count=1)


def update_readme(modules: list[ModuleCatalog], readme_path: Path) -> None:
    if not readme_path.is_file():
        raise RuntimeError(f"找不到 README: {readme_path}")
    text = readme_path.read_text(encoding="utf-8")
    text = replace_marked_block(text, STATS_START, STATS_END, build_stats_block(modules))
    text = replace_marked_block(text, SERIES_START, SERIES_END, build_series_block(modules))
    # Refresh article count chip-like mentions if present
    total = sum(m.article_count for m in modules)
    text = re.sub(
        r"(<!-- CATALOG-TOTAL:START -->).*?(<!-- CATALOG-TOTAL:END -->)",
        rf"\g<1>{total}\g<2>",
        text,
        count=1,
        flags=re.DOTALL,
    )
    readme_path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    modules = collect_modules(REPO_ROOT)
    catalog = build_catalog_md(modules)
    CATALOG_PATH.write_text(catalog, encoding="utf-8", newline="\n")
    total = sum(m.article_count for m in modules)
    print(f"Wrote {CATALOG_PATH.relative_to(REPO_ROOT)} ({total} articles)")

    if README_PATH.is_file() and STATS_START in README_PATH.read_text(encoding="utf-8"):
        update_readme(modules, README_PATH)
        print(f"Updated catalog blocks in {README_PATH.relative_to(REPO_ROOT)}")
    else:
        print("README markers not found; skipped README update", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
