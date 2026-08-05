#!/usr/bin/env python3
"""扫描 6 卷结构，生成根目录「文章总目录.md」，并刷新 README 的标记块。

2026-08-03 重写：原先按「模块 → 系列」两层组织，对应已删除的 7 module
目录。现在按书的实际结构走「卷 → 章 → 子章」三层。
2026-08-05：8 卷 50 章 → 6 卷 56 章（v3 重组）。

章目录名形如 `12-Binder IPC 深度`，前缀数字即章号；子章形如
`13.A-Android四大组件`，也有 `A-启动机制`、`工具包` 这类不带编号的，
一律按目录名原样显示。00-Meta 不是卷，仍按「目录 → 文件」两层处理。

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

META_MODULE = "00-Meta"
ROOT_GROUP_LABEL = "（目录根）"

VOLUME_CN = {
    "01-卷1-平台基础与启动": "卷 1 · 平台基础与启动",
    "02-卷2-核心机制": "卷 2 · 核心机制",
    "03-卷3-调查工具": "卷 3 · 调查工具",
    "04-卷4-稳定性症状": "卷 4 · 稳定性症状",
    "05-卷5-性能工程与治理": "卷 5 · 性能工程与治理",
    "06-卷6-案例实战": "卷 6 · 案例实战",
    META_MODULE: "地图 · 元信息",
}

CHAPTER_RE = re.compile(r"^(\d+)-(.+)$")


@dataclass
class Article:
    rel_posix: str
    title: str
    index: str
    filename: str


@dataclass
class Chapter:
    """卷下的一章；00-Meta 下则是一个子目录。"""

    dirname: str  # 空串 = 模块根
    module: str
    direct: list[Article] = field(default_factory=list)
    subgroups: dict[str, list[Article]] = field(default_factory=dict)

    @property
    def number(self) -> int | None:
        m = CHAPTER_RE.match(self.dirname)
        return int(m.group(1)) if m else None

    @property
    def display(self) -> str:
        if not self.dirname:
            return ROOT_GROUP_LABEL
        m = CHAPTER_RE.match(self.dirname)
        if m and self.module != META_MODULE:
            return f"第 {int(m.group(1))} 章　{m.group(2)}"
        return self.dirname

    @property
    def folder(self) -> str:
        return f"{self.module}/{self.dirname}/" if self.dirname else f"{self.module}/"

    @property
    def article_count(self) -> int:
        return len(self.direct) + sum(len(v) for v in self.subgroups.values())


@dataclass
class Volume:
    name: str
    chapters: list[Chapter] = field(default_factory=list)

    @property
    def article_count(self) -> int:
        return sum(c.article_count for c in self.chapters)

    @property
    def chapter_count(self) -> int:
        return len([c for c in self.chapters if c.dirname])


def natural_key(name: str) -> tuple:
    stem = Path(name).stem
    m = re.match(r"^(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    m = re.match(r"^[A-Za-z]+(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    return (1, 0, stem.lower())


def chapter_sort_key(c: Chapter) -> tuple:
    if not c.dirname:
        return (-1, 0, "")
    n = c.number
    if n is not None:
        return (0, n, "")
    return (1, 0, c.dirname.lower())


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


def collect_volumes(repo_root: Path) -> list[Volume]:
    volumes: list[Volume] = []
    for mod in PUBLIC_MODULES:
        mod_dir = repo_root / mod
        if not mod_dir.is_dir():
            continue

        direct: dict[str, list[Article]] = defaultdict(list)
        subs: dict[str, dict[str, list[Article]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for path in mod_dir.rglob("*.md"):
            if not is_article_file(path, repo_root):
                continue
            rel = path.relative_to(repo_root)
            parts = path.parent.relative_to(mod_dir).parts
            chapter = parts[0] if parts else ""
            sub = "/".join(parts[1:]) if len(parts) > 1 else ""
            art = Article(
                rel_posix=rel.as_posix(),
                title=get_title_from_markdown(
                    path.read_text(encoding="utf-8", errors="replace"), path.name
                ),
                index=extract_index_from_filename(path.name),
                filename=path.name,
            )
            if sub:
                subs[chapter][sub].append(art)
            else:
                direct[chapter].append(art)

        names = set(direct) | set(subs)
        chapters: list[Chapter] = []
        for name in names:
            ch = Chapter(dirname=name, module=mod)
            ch.direct = sorted(direct.get(name, []), key=lambda a: natural_key(a.filename))
            for sub_name in sorted(subs.get(name, {}), key=natural_key):
                ch.subgroups[sub_name] = sorted(
                    subs[name][sub_name], key=lambda a: natural_key(a.filename)
                )
            chapters.append(ch)
        chapters.sort(key=chapter_sort_key)
        volumes.append(Volume(name=mod, chapters=chapters))
    return volumes


def anchor(mod: str) -> str:
    """卷目录名含中文与数字，取 volN / meta 作为稳定锚点。"""
    if mod == META_MODULE:
        return "meta"
    m = re.match(r"^(\d+)-卷", mod)
    return f"vol{int(m.group(1))}" if m else mod.lower()


def render_article_table(articles: list[Article], lines: list[str]) -> None:
    lines.append("| 序号 | 标题 | 链接 |")
    lines.append("|:-----|:-----|:-----|")
    for art in articles:
        idx = art.index or "—"
        title_safe = art.title.replace("|", "\\|")
        lines.append(f"| {idx} | {title_safe} | [`{art.filename}`]({art.rel_posix}) |")
    lines.append("")


def build_catalog_md(volumes: list[Volume]) -> str:
    total_articles = sum(v.article_count for v in volumes)
    total_chapters = sum(v.chapter_count for v in volumes if v.name != META_MODULE)

    lines: list[str] = [
        "# 文章总目录",
        "",
        "> **自动生成，请勿手改。** 更新命令：",
        "> ```bash",
        "> py -3.12 00-Meta/scripts/generate_article_catalog.py",
        "> ```",
        ">",
        f"> 当前收录 **{total_articles}** 篇正文，分布在 **6 卷 {total_chapters} 章**。",
        ">",
        "> 想看全书的章节规划（含尚未撰写的章节），见 "
        "[书籍目录](00-Meta/书籍目录-v1.md)。",
        "",
        "## 快速导航",
        "",
        "| 卷 | 内容 | 章数 | 文章数 | 跳转 |",
        "|:---|:-----|-----:|-------:|:-----|",
    ]
    for v in volumes:
        cn = VOLUME_CN.get(v.name, MODULE_TITLES.get(v.name, v.name))
        blurb = MODULE_BLURBS.get(v.name, "")
        n_ch = v.chapter_count if v.name != META_MODULE else "—"
        lines.append(
            f"| [{cn}]({v.name}/) | {blurb} | {n_ch} | {v.article_count} "
            f"| [↓](#{anchor(v.name)}) |"
        )
    lines.append(f"| **合计** | | **{total_chapters}** | **{total_articles}** | |")
    lines.extend(["", "---", ""])

    for v in volumes:
        cn = VOLUME_CN.get(v.name, v.name)
        blurb = MODULE_BLURBS.get(v.name, "")
        lines.append(f'<a id="{anchor(v.name)}"></a>')
        lines.append("")
        lines.append(f"## {cn}")
        lines.append("")
        if blurb:
            lines.append(f"> {blurb}")
            lines.append("")
        n_ch = v.chapter_count if v.name != META_MODULE else len(v.chapters)
        unit = "章" if v.name != META_MODULE else "个目录"
        lines.append(
            f"共 **{n_ch}** {unit}、**{v.article_count}** 篇 · "
            f"[打开目录]({v.name}/) · [返回快速导航](#快速导航)"
        )
        lines.append("")

        for ch in v.chapters:
            lines.append(f"### {ch.display}")
            lines.append("")
            lines.append(f"[打开目录]({ch.folder}) · {ch.article_count} 篇")
            lines.append("")
            if ch.direct:
                render_article_table(ch.direct, lines)
            for sub_name, arts in ch.subgroups.items():
                lines.append(f"**{sub_name}** · {len(arts)} 篇")
                lines.append("")
                render_article_table(arts, lines)

    lines.append("---")
    lines.append("")
    lines.append(
        f"*生成脚本：`00-Meta/scripts/generate_article_catalog.py` · "
        f"共 {total_articles} 篇*"
    )
    lines.append("")
    return "\n".join(lines)


def build_stats_block(volumes: list[Volume]) -> str:
    total = sum(v.article_count for v in volumes)
    total_ch = sum(v.chapter_count for v in volumes if v.name != META_MODULE)
    lines = [
        STATS_START,
        "",
        "| 卷 | 内容 | 章数 | 文章数 |",
        "|:---|:-----|-----:|-------:|",
    ]
    for v in volumes:
        cn = VOLUME_CN.get(v.name, v.name)
        blurb = MODULE_BLURBS.get(v.name, "")
        n_ch = v.chapter_count if v.name != META_MODULE else "—"
        lines.append(f"| [**{cn}**]({v.name}/) | {blurb} | {n_ch} | {v.article_count} |")
    lines.append(f"| **合计** | [文章总目录](文章总目录.md) | **{total_ch}** | **{total}** |")
    lines.extend(["", STATS_END])
    return "\n".join(lines)


def build_series_block(volumes: list[Volume]) -> str:
    lines = [SERIES_START, ""]
    for v in volumes:
        if v.name == META_MODULE:
            continue
        cn = VOLUME_CN.get(v.name, v.name)
        lines.append(f"### {cn}")
        lines.append("")
        lines.append("| 章 | 文章数 | 目录 |")
        lines.append("|:---|-------:|:-----|")
        for ch in v.chapters:
            lines.append(
                f"| {ch.display} | {ch.article_count} | [{ch.folder}]({ch.folder}) |"
            )
        lines.append("")
    lines.append(SERIES_END)
    return "\n".join(lines)


def replace_marked_block(text: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        raise RuntimeError(f"README 缺少标记块 {start} … {end}")
    return pattern.sub(lambda _m: replacement, text, count=1)


def update_readme(volumes: list[Volume], readme_path: Path) -> None:
    if not readme_path.is_file():
        raise RuntimeError(f"找不到 README: {readme_path}")
    text = readme_path.read_text(encoding="utf-8")
    text = replace_marked_block(text, STATS_START, STATS_END, build_stats_block(volumes))
    text = replace_marked_block(
        text, SERIES_START, SERIES_END, build_series_block(volumes)
    )
    total = sum(v.article_count for v in volumes)
    text = re.sub(
        r"(<!-- CATALOG-TOTAL:START -->).*?(<!-- CATALOG-TOTAL:END -->)",
        rf"\g<1>{total}\g<2>",
        text,
        count=1,
        flags=re.DOTALL,
    )
    readme_path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    volumes = collect_volumes(REPO_ROOT)
    CATALOG_PATH.write_text(build_catalog_md(volumes), encoding="utf-8", newline="\n")
    total = sum(v.article_count for v in volumes)
    total_ch = sum(v.chapter_count for v in volumes if v.name != META_MODULE)
    print(f"Wrote {CATALOG_PATH.relative_to(REPO_ROOT)} ({total} 篇 / {total_ch} 章)")

    if README_PATH.is_file() and STATS_START in README_PATH.read_text(encoding="utf-8"):
        update_readme(volumes, README_PATH)
        print(f"Updated catalog blocks in {README_PATH.relative_to(REPO_ROOT)}")
    else:
        print("README markers not found; skipped README update", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
