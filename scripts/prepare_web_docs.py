#!/usr/bin/env python3
"""将仓库 Markdown 同步到 docs/，供 MkDocs / GitHub Pages 构建。

导航策略（分层，避免侧栏一次铺开）：
1. 顶栏 Tab = 七大模块
2. 模块页 = 系列目录（短名）
3. 系列页 = 仅「系列总览」；单篇从总览表格进入
4. 有子目录的系列（如 ART）再展开一层子模块
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
    MODULE_BLURBS,
    MODULE_SERIES_ORDER,
    MODULE_TITLES,
    PUBLIC_MODULES,
    PUBLIC_ROOT_FILES,
    SERIES_NAV_TITLES,
    is_excluded_path,
    is_meta_file,
)
from public_readme import build_public_readme  # noqa: E402

REPO_ROOT = _SCRIPTS.parent
DOCS_DIR = REPO_ROOT / "docs"

MODULE_DIRS = PUBLIC_MODULES
ROOT_FILES = [(name, name) for name in PUBLIC_ROOT_FILES]

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
    stem = Path(name).stem
    m = re.match(r"^(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    if stem.lower().startswith("readme"):
        return (-1, 0, stem.lower())
    m = re.match(r"^[A-Za-z]+(\d+)", stem)
    if m:
        return (0, int(m.group(1)), stem.lower())
    return (1, 0, stem.lower())


def yaml_quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_pages_file(dir_path: Path, nav_entries: list[tuple[str, str]]) -> None:
    if not nav_entries:
        return
    lines = ["nav:"]
    for title, target in nav_entries:
        lines.append(f"  - {yaml_quote(title)}: {target}")
    (dir_path / ".pages").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pick_readme(dir_path: Path) -> Path | None:
    series = sorted(
        [
            p
            for p in dir_path.glob("README*.md")
            if "系列" in p.name or "Series" in p.name
        ],
        key=lambda p: p.name.lower(),
    )
    if series:
        return series[0]
    for candidate in ("README.md", "readme.md"):
        p = dir_path / candidate
        if p.is_file():
            return p
    readmes = list(dir_path.glob("README*.md")) + list(dir_path.glob("readme*.md"))
    return readmes[0] if readmes else None


def _dir_has_content(dir_path: Path) -> bool:
    """目录下是否有可读 Markdown（含嵌套）。"""
    return any(p.suffix.lower() == ".md" for p in dir_path.rglob("*.md"))


def _short_title(module: str | None, dirname: str, dir_path: Path | None = None) -> str:
    if module and dirname in SERIES_NAV_TITLES.get(module, {}):
        return SERIES_NAV_TITLES[module][dirname]
    # 子模块：优先用编号前缀后的短名
    m = re.match(r"^(\d+)[-_](.+)$", dirname)
    if m:
        return m.group(2).replace("_", " ")
    if dir_path is not None:
        readme = _pick_readme(dir_path)
        if readme:
            title = get_title_from_markdown(
                readme.read_text(encoding="utf-8", errors="replace"),
                dirname,
            )
            # 去掉常见冗长前缀
            title = re.sub(r"^面向稳定性的\s*", "", title)
            title = re.sub(r"（共\s*\d+\s*篇）$", "", title)
            title = re.sub(r"\(共\s*\d+\s*篇\)$", "", title)
            title = re.sub(r"\s*—\s*系列总览$", "", title)
            title = re.sub(r"系列文章$", "", title)
            title = title.strip(" ：:")
            if 0 < len(title) <= 24:
                return title
    return dirname.replace("_", " ")


def sort_subdirs(parent: Path, subdirs: list[Path]) -> list[Path]:
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


def _list_nav_subdirs(dir_path: Path) -> list[Path]:
    return sort_subdirs(
        dir_path,
        [
            p
            for p in dir_path.iterdir()
            if p.is_dir()
            and not p.name.startswith(".")
            and p.name.lower() not in NAV_SKIP_DIR_NAMES
            and _dir_has_content(p)
        ],
    )


def _module_name_for(dir_path: Path) -> str | None:
    try:
        rel = dir_path.relative_to(DOCS_DIR)
        return rel.parts[0] if rel.parts else None
    except ValueError:
        return None


def _series_blurb(series_dir: Path) -> str:
    readme = _pick_readme(series_dir)
    if not readme:
        return "打开系列总览，按篇章表阅读"
    text = readme.read_text(encoding="utf-8", errors="replace")
    candidates: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith("---"):
            continue
        if s.startswith("```") or s.startswith("!!!") or s.startswith("- [") or s.startswith("* ["):
            continue
        # 引用块可作简介
        if s.startswith(">"):
            s = s.lstrip("> ").strip()
        s = re.sub(r"\*+", "", s)
        s = re.sub(r"`+", "", s)
        if len(s) < 18 or s.endswith(("：", ":", "、")):
            continue
        if any(k in s for k in ("目录", "TODO", "写作", "基线：", "源码基线")):
            continue
        candidates.append(s)
        if len(candidates) >= 3:
            break
    if not candidates:
        return "打开系列总览，按篇章表阅读"
    s = candidates[0]
    if len(s) > 48:
        s = s[:46] + "…"
    return s


def build_module_index(module: str, mod_dir: Path) -> str:
    title = MODULE_TITLES.get(module, module)
    blurb = MODULE_BLURBS.get(module, "")
    subdirs = _list_nav_subdirs(mod_dir)
    lines = [
        f"# {title}",
        "",
        f"{blurb}。" if blurb else "",
        "",
        "选择下方**系列**进入总览；单篇请在系列总览的目录表中打开。",
        "",
        "## 系列目录",
        "",
        "| 系列 | 说明 |",
        "|------|------|",
    ]
    if not subdirs:
        # 模块本身就是一个系列（如 Hook）
        readme = _pick_readme(mod_dir)
        if readme:
            lines.append(f"| [系列总览]({readme.name}) | {_series_blurb(mod_dir)} |")
        else:
            lines.append("| （暂无系列） | — |")
    else:
        for sub in subdirs:
            short = _short_title(module, sub.name, sub)
            readme = _pick_readme(sub)
            link = f"{sub.name}/" if not readme else f"{sub.name}/{readme.name}"
            # index 优先：链到目录，由 indexes 打开总览
            link = f"{sub.name}/"
            lines.append(f"| [{short}]({link}) | {_series_blurb(sub)} |")
    lines.extend(["", "---", "", "返回 [站点首页](../index.md)。", ""])
    return "\n".join(lines)


def generate_dir_pages(dir_path: Path, *, depth: int = 0) -> None:
    """生成 .pages。

    depth=0 模块层：总览 + 系列短名
    depth=1 系列层：系列总览 +（可选）子模块
    depth>=2 子模块：仅总览/README，不再铺单篇
    """
    module = _module_name_for(dir_path)
    subdirs = _list_nav_subdirs(dir_path)
    nav: list[tuple[str, str]] = []

    if depth == 0:
        # 模块总览
        if (dir_path / "index.md").is_file():
            nav.append(("本模块总览", "index.md"))
        for sub in subdirs:
            nav.append((_short_title(module, sub.name, sub), sub.name))
            generate_dir_pages(sub, depth=1)
        # 模块根上的 README（如 Framework/README.md）收到总览后，不占侧栏
        write_pages_file(dir_path, nav)
        return

    # 系列 / 子模块：只挂一份总览，避免篇章堆叠
    readme = _pick_readme(dir_path)
    if readme:
        nav.append(("系列总览", readme.name))

    # 仅在系列第一层展开子目录（ART 子模块）；更深不再分叉进侧栏
    if depth == 1 and subdirs:
        for sub in subdirs:
            nav.append((_short_title(module, sub.name, sub), sub.name))
            generate_dir_pages(sub, depth=2)
    elif depth >= 2 and subdirs:
        # 更深层（如 GC 九子目录）仍给一层入口，但标题缩短；单篇不进侧栏
        for sub in subdirs:
            nav.append((_short_title(module, sub.name, sub), sub.name))
            generate_dir_pages(sub, depth=3)
    elif depth >= 3:
        # 到底：只保留总览
        pass

    write_pages_file(dir_path, nav)


def generate_pages_tree(docs_root: Path) -> None:
    top_nav: list[tuple[str, str]] = [("首页", "index.md")]
    for mod in MODULE_DIRS:
        mod_dir = docs_root / mod
        if not mod_dir.is_dir():
            continue
        title = MODULE_TITLES.get(mod, mod)
        top_nav.append((title, mod))
        # 模块落地页
        (mod_dir / "index.md").write_text(
            build_module_index(mod, mod_dir),
            encoding="utf-8",
        )
        generate_dir_pages(mod_dir, depth=0)
    write_pages_file(docs_root, top_nav)


def build_public_index() -> str:
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
    print("Generated layered .pages navigation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
