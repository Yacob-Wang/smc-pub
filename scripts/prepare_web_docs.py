#!/usr/bin/env python3
"""将仓库 Markdown 同步到 docs/，供 MkDocs / GitHub Pages 构建。

- 同步七大模块正文与配图
- 生成博客首页 index.md
- 按系列 README 表格顺序生成 .pages 层级导航
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from content_policy import (  # noqa: E402
    ASSET_SUFFIXES,
    MODULE_SERIES_ORDER,
    MODULE_TITLES,
    PUBLIC_MODULES,
    PUBLIC_ROOT_FILES,
    is_excluded_path,
    is_meta_file,
)
from public_readme import build_public_readme  # noqa: E402

REPO_ROOT = _SCRIPTS.parent
DOCS_DIR = REPO_ROOT / "docs"

# 兼容旧变量名
MODULE_DIRS = PUBLIC_MODULES
ROOT_FILES = [(name, name) for name in PUBLIC_ROOT_FILES]


def is_excluded(rel: Path) -> bool:
    return is_excluded_path(rel)


def should_copy(path: Path) -> bool:
    if path.is_dir():
        return False
    suffix = path.suffix.lower()
    return suffix == ".md" or suffix in ASSET_SUFFIXES


def get_title_from_markdown(content: str, fallback: str) -> str:
    for line in content.splitlines():
        m = re.match(r"^\s*#\s+(.+)$", line)
        if m:
            return m.group(1).strip()
    name = Path(fallback).stem
    m = re.match(r"^\d+-(.+)$", name)
    return m.group(1) if m else name


def parse_series_readme_table(content: str) -> list[str]:
    """从系列 README 表格解析篇章文件名顺序（与 pack-content.ps1 对齐）。"""
    files: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^\|\s*\[(\d+)\]\(\./([^)]+)\)\s*\|", line)
        if not m:
            m = re.match(r"^\|\s*\[(\d+)\]\(([^)]+\.md)\)\s*\|", line)
        if m:
            file_name = m.group(2).lstrip("./")
            if file_name not in files:
                files.append(file_name)
    return files


def natural_key(name: str) -> tuple:
    """数字前缀优先的自然排序键。"""
    stem = Path(name).stem
    m = re.match(r"^(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    if stem.lower().startswith("readme"):
        return (-1, 0, stem.lower())
    # AE01 / R01 / F01 / O01 / PM01 等前缀
    m = re.match(r"^[A-Za-z]+(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    return (1, 0, stem.lower())


def order_md_files(dir_path: Path) -> list[str]:
    """返回目录内 .md 文件的展示顺序（仅文件名）。"""
    md_files = [p.name for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() == ".md"]
    if not md_files:
        return []

    readmes = [f for f in md_files if f.lower().startswith("readme")]
    others = [f for f in md_files if f not in readmes]

    ordered: list[str] = []
    # README 优先
    for r in sorted(readmes, key=lambda x: (0 if x.lower() == "readme.md" else 1, x.lower())):
        ordered.append(r)

    # 若存在系列 README，尝试按表格排序其余文章
    table_order: list[str] = []
    for r in ordered:
        content = (dir_path / r).read_text(encoding="utf-8", errors="replace")
        table_order = parse_series_readme_table(content)
        if table_order:
            break

    remaining = set(others)
    for fname in table_order:
        # 精确匹配或编号前缀模糊匹配
        if fname in remaining:
            ordered.append(fname)
            remaining.discard(fname)
            continue
        m = re.match(r"^(\d{2})-", fname)
        if m:
            prefix = m.group(1)
            hits = sorted([f for f in remaining if f.startswith(prefix + "-")], key=natural_key)
            if hits:
                ordered.append(hits[0])
                remaining.discard(hits[0])

    ordered.extend(sorted(remaining, key=natural_key))
    return ordered


def yaml_quote(text: str) -> str:
    """简单加引号，避免标题中的冒号等破坏 .pages YAML。"""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_pages_file(dir_path: Path, nav_entries: list[tuple[str, str]]) -> None:
    """写入 awesome-pages 的 .pages。entries = [(title, target), ...]。"""
    if not nav_entries:
        return
    lines = ["nav:"]
    for title, target in nav_entries:
        lines.append(f"  - {yaml_quote(title)}: {target}")
    (dir_path / ".pages").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_pages_tree(docs_root: Path) -> None:
    """为 docs/ 下各级目录生成 .pages。"""
    # 顶层
    top_nav: list[tuple[str, str]] = [
        ("首页", "index.md"),
    ]
    for mod in MODULE_DIRS:
        if (docs_root / mod).is_dir():
            title = MODULE_TITLES.get(mod, mod)
            top_nav.append((title, mod))
    write_pages_file(docs_root, top_nav)

    # 各模块目录
    for mod in MODULE_DIRS:
        mod_dir = docs_root / mod
        if not mod_dir.is_dir():
            continue
        generate_dir_pages(mod_dir)


def sort_subdirs(parent: Path, subdirs: list[Path]) -> list[Path]:
    """模块级目录按预定义系列顺序排序。"""
    # parent 相对 docs 根的第一段即 module 名
    try:
        rel = parent.relative_to(DOCS_DIR)
        module = rel.parts[0] if rel.parts else parent.name
    except ValueError:
        module = parent.name
    preferred = MODULE_SERIES_ORDER.get(module, [])
    rank = {name: i for i, name in enumerate(preferred)}

    def key(p: Path) -> tuple:
        if p.name in rank:
            return (0, rank[p.name])
        return (1,) + natural_key(p.name)

    return sorted(subdirs, key=key)


# 侧栏不展开的目录名（杂项 / 桥接，从系列 README 内链进入即可）
NAV_SKIP_DIR_NAMES = {
    "bridge",
    "appendix",
    "appendices",
    "assets",
    "images",
    "img",
    "scripts",
    "_archive",
    "_studio",
}


def _pick_readme(dir_path: Path) -> Path | None:
    for candidate in ("README.md", "readme.md"):
        p = dir_path / candidate
        if p.is_file():
            return p
    readmes = list(dir_path.glob("README*.md")) + list(dir_path.glob("readme*.md"))
    return readmes[0] if readmes else None


def _dir_nav_title(sub: Path) -> str:
    readme = _pick_readme(sub)
    if readme:
        title = get_title_from_markdown(
            readme.read_text(encoding="utf-8", errors="replace"),
            sub.name,
        )
    else:
        title = MODULE_TITLES.get(sub.name, sub.name.replace("_", " "))
    if len(title) > 40:
        title = title[:38] + "…"
    return title


def generate_dir_pages(dir_path: Path) -> None:
    """递归生成 .pages。

    侧栏策略（避免 500+ 篇铺开）：
    - 只挂 README* 作为系列入口
    - 子目录继续递归
    - 单篇正文仍复制进 docs/，可从系列 README 表格链接 / 搜索到达
    """
    subdirs = sort_subdirs(
        dir_path,
        [
            p
            for p in dir_path.iterdir()
            if p.is_dir()
            and not p.name.startswith(".")
            and p.name.lower() not in NAV_SKIP_DIR_NAMES
        ],
    )

    nav: list[tuple[str, str]] = []

    # 仅 README 进侧栏
    for fname in order_md_files(dir_path):
        if not fname.lower().startswith("readme"):
            continue
        title = get_title_from_markdown(
            (dir_path / fname).read_text(encoding="utf-8", errors="replace"),
            fname,
        )
        if len(title) > 48:
            title = title[:46] + "…"
        nav.append((title, fname))

    for sub in subdirs:
        nav.append((_dir_nav_title(sub), sub.name))
        generate_dir_pages(sub)

    write_pages_file(dir_path, nav)


def build_public_index() -> str:
    """面向读者的首页（与 public_readme 同源）。"""
    return build_public_readme(REPO_ROOT)


def copy_tree(src: Path, dst: Path) -> int:
    count = 0
    if not src.is_dir():
        return 0
    for path in src.rglob("*"):
        if not should_copy(path):
            continue
        rel = path.relative_to(REPO_ROOT)
        if is_excluded(rel):
            continue
        target = dst / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
    return count


def main() -> int:
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True)

    total = 0
    skipped_meta = 0
    for module in MODULE_DIRS:
        src = REPO_ROOT / module
        if src.is_dir():
            for p in src.rglob("*.md"):
                if is_meta_file(p.relative_to(REPO_ROOT)):
                    skipped_meta += 1
        n = copy_tree(src, DOCS_DIR / module)
        print(f"  {module}: {n} files")
        total += n

    for src_name, dst_name in ROOT_FILES:
        src = REPO_ROOT / src_name
        if not src.is_file():
            print(f"  skip missing root file: {src_name}", file=sys.stderr)
            continue
        shutil.copy2(src, DOCS_DIR / dst_name)
        total += 1
        print(f"  root: {src_name} -> {dst_name}")

    index = build_public_index()
    (DOCS_DIR / "index.md").write_text(index, encoding="utf-8")
    total += 1
    print("  root: index.md (blog homepage)")

    generate_pages_tree(DOCS_DIR)
    print(f"Prepared docs/ with {total} content files; skipped ~{skipped_meta} meta docs")
    print("Generated hierarchical .pages navigation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
