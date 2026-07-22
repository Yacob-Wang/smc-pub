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
from preamble_transform import (  # noqa: E402
    audit_docs_for_preamble,
    should_strip_module,
    strip_author_preamble,
)
from feed_cards import (  # noqa: E402
    FeedCard,
    card_from_markdown,
    landing_frontmatter,
    render_feed_grid,
    render_page_hero,
    to_site_href,
)
from public_readme import build_public_readme  # noqa: E402

REPO_ROOT = _SCRIPTS.parent.parent  # 适配阶段 3 移到 00-Meta/scripts/（原 _SCRIPTS.parent 是仓库根）
DOCS_DIR = REPO_ROOT / "docs"

# 跨模块累计：文首作者前言剥离数（供 main 打印）
_PREAMBLE_STRIPPED = 0

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


def _count_articles_in_series(series_dir: Path) -> int:
    """统计 series 下的文章数（含子目录的 md，不含 README/index）。"""
    total = 0
    for p in series_dir.rglob("*.md"):
        name = p.name.lower()
        if name.startswith("readme") or name == "index.md":
            continue
        total += 1
    return total


def yaml_quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_pages_file(
    dir_path: Path,
    nav_entries: list[tuple[str, str]],
    collapse: bool = False,
) -> None:
    if not nav_entries and not collapse:
        return
    lines: list[str] = []
    if collapse:
        lines.append("collapse: true")
    if nav_entries:
        lines.append("nav:")
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


def _module_stats(mod_dir: Path, subdirs: list[Path]) -> tuple[int, int]:
    """(series 数, 总文章数)。"""
    series_count = len(subdirs)
    article_count = sum(_count_articles_in_series(sub) for sub in subdirs)
    return series_count, article_count


def _series_feed_cards(
    module: str,
    target_dir: Path,
    *,
    label: str,
    link_prefix: str = "",
) -> list[FeedCard]:
    cards: list[FeedCard] = []
    for sub in _list_nav_subdirs(target_dir):
        short = _short_title(module, sub.name, sub)
        blurb_s = _series_blurb(sub)
        count = _count_articles_in_series(sub)
        cards.append(
            FeedCard(
                href=to_site_href(f"{link_prefix}{sub.name}/"),
                title=short,
                summary=blurb_s,
                label=label,
                date=f"约 {count} 篇",
                media_module=module,
                media_text=short[:1],
            )
        )
    return cards


def _article_feed_cards(
    module: str | None,
    dir_path: Path,
    *,
    label: str,
) -> list[FeedCard]:
    cards: list[FeedCard] = []
    mod = module or _module_name_for(dir_path) or "01-Mechanism"
    for fname in _article_files(dir_path):
        path = dir_path / fname
        cards.append(
            card_from_markdown(
                path,
                href=to_site_href(fname),
                label=label,
                repo_root=REPO_ROOT,
                module=mod,
            )
        )
    return cards


def build_module_index(module: str, mod_dir: Path) -> str:
    """生成 module 落地页（News Feed 卡片式）。"""
    title = MODULE_TITLES.get(module, module)
    blurb = MODULE_BLURBS.get(module, "")
    subdirs = _list_nav_subdirs(mod_dir)
    series_count, article_count = _module_stats(mod_dir, subdirs)

    lead_parts: list[str] = []
    if blurb:
        lead_parts.append(blurb)
    if series_count:
        lead_parts.append(f"本模块共 {series_count} 个系列、约 {article_count} 篇文章。")
    lead = " · ".join(lead_parts)

    hero = render_page_hero(title, lead)
    cards: list[FeedCard] = []

    if not subdirs:
        readme = _pick_readme(mod_dir)
        if readme:
            count = _count_articles_in_series(mod_dir)
            cards.append(
                FeedCard(
                    href=to_site_href(readme.name),
                    title="本系列",
                    summary=_series_blurb(mod_dir),
                    label=title,
                    date=f"约 {count} 篇",
                    media_module=module,
                    media_text="S",
                )
            )
    else:
        cards = _series_feed_cards(module, mod_dir, label=title)

    footer = '\n<p class="jk-foot">返回 <a href="../">站点首页</a>。</p>\n'
    return landing_frontmatter(title) + hero + render_feed_grid(cards) + footer


def build_subcategory_index(module: str, sub_dir: Path) -> str:
    """生成子分类落地页（News Feed 卡片式）。"""
    short = _short_title(module, sub_dir.name, sub_dir)
    subdirs = _list_nav_subdirs(sub_dir)
    series_count, article_count = _module_stats(sub_dir, subdirs)
    module_title = MODULE_TITLES.get(module, module)

    lead = ""
    if series_count:
        lead = f"本层共 {series_count} 个系列、约 {article_count} 篇文章。"

    hero = render_page_hero(short, lead)
    cards = _series_feed_cards(module, sub_dir, label=short)
    try:
        rel = sub_dir.relative_to(DOCS_DIR)
        if len(rel.parts) > 2:
            parent = sub_dir.parent
            back_label = _short_title(module, parent.name, parent)
        else:
            back_label = f"{module_title} 模块总览"
    except ValueError:
        back_label = f"{module_title} 模块总览"
    footer = f'\n<p class="jk-foot">返回 <a href="../">{back_label}</a>。</p>\n'
    return landing_frontmatter(short) + hero + render_feed_grid(cards) + footer


def build_series_landing_index(module: str | None, dir_path: Path) -> str:
    """系列总览 landing 页：Hero + 篇章 Feed。"""
    short = _short_title(module, dir_path.name, dir_path)
    blurb = _series_blurb(dir_path)
    label = short
    if module:
        label = MODULE_TITLES.get(module, module)
    hero = render_page_hero(short, blurb or "本系列篇章如下。点开单篇阅读。")
    cards = _article_feed_cards(module, dir_path, label=label)
    if not cards:
        cards = [
            FeedCard(
                href="#",
                title="（暂无篇章）",
                summary="该系列尚未收录文章。",
                label=label,
                media_module=module or "01-Mechanism",
            )
        ]
    return landing_frontmatter(short) + hero + render_feed_grid(cards)


def ensure_subcategory_landing_pages(mod_dir: Path, module: str) -> None:
    """为含嵌套系列的子分类生成 index.md + .pages（任意深度，如 Runtime/ART）。"""
    for sub in _list_nav_subdirs(mod_dir):
        nested = _list_nav_subdirs(sub)
        if not nested:
            continue
        index_path = sub / "index.md"
        index_path.write_text(
            build_subcategory_index(module, sub),
            encoding="utf-8",
        )
        nav: list[tuple[str, str]] = [("本层总览", "index.md")]
        for series in nested:
            nav.append((_short_title(module, series.name, series), series.name))
        write_pages_file(sub, nav, collapse=True)
        ensure_subcategory_landing_pages(sub, module)


def _article_files(dir_path: Path) -> list[str]:
    """目录内可作为篇章的 md（排除 README / index）。"""
    files = [
        p.name
        for p in dir_path.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".md"
        and not p.name.lower().startswith("readme")
        and p.name.lower() != "index.md"
    ]
    return sorted(files, key=natural_key)


def _ensure_series_overview(dir_path: Path, module: str | None) -> str:
    """保证系列有总览页；生成 Feed 式 index.md，侧栏只挂这一页。"""
    index_path = dir_path / "index.md"
    index_path.write_text(
        build_series_landing_index(module, dir_path),
        encoding="utf-8",
    )
    return "index.md"


def generate_module_pages(mod_dir: Path, module: str) -> None:
    """module 层 .pages：本模块总览（卡片式 index.md） + 子分类列表。

    系列层不写 .pages —— 让 awesome-pages plugin 自动递归列出该系列单篇
    （用户进入某系列时，侧栏只显示本系列的内容 + 子分类）。

    `collapse: true` —— 侧栏默认折叠所有 AOSP 分层下的子分类，
    用户点顶部 tab 回 module 落地页时侧栏不会铺满 500+ 篇。
    """
    nav: list[tuple[str, str]] = []

    # 1) 模块总览：强制 index.md（卡片式落地页）
    if (mod_dir / "index.md").is_file():
        nav.append(("本模块总览", "index.md"))

    # 2) 子分类（按 MODULE_SERIES_ORDER 排序）
    subdirs = _list_nav_subdirs(mod_dir)
    for sub in subdirs:
        nav.append((_short_title(module, sub.name, sub), sub.name))

    write_pages_file(mod_dir, nav, collapse=True)


def generate_pages_tree(docs_root: Path) -> None:
    """导航策略：

    1. 顶层 .pages：8 大分类 tab（按 MODULE_TITLES 排序）
    2. module 层强制生成 index.md（Material grid cards 卡片式落地页）
       —— 无论仓库里有没有 README.md；README.md 仍会复制到 docs/ 作为扩展
       —— 从 index.md 链过去，但不进侧栏
    3. module 层 .pages：「本模块总览」指向 index.md + 子分类列表
    4. series 层不写 .pages：让 awesome-pages 自动递归列出所有单篇
    """
    top_nav: list[tuple[str, str]] = [("Home", "index.md")]
    for mod in MODULE_DIRS:
        mod_dir = docs_root / mod
        if not mod_dir.is_dir():
            continue
        title = MODULE_TITLES.get(mod, mod)
        top_nav.append((title, mod))
        # 强制生成 index.md（卡片式）—— 覆盖可能存在的手写 README 索引
        (mod_dir / "index.md").write_text(
            build_module_index(mod, mod_dir),
            encoding="utf-8",
        )
        generate_module_pages(mod_dir, mod)
        ensure_subcategory_landing_pages(mod_dir, mod)
    write_pages_file(docs_root, top_nav)


def build_public_index() -> str:
    return build_public_readme(REPO_ROOT, docs_dir=DOCS_DIR)


def sanitize_filename(name: str) -> str:
    """把文件名中的特殊字符替换为安全字符（避免 mkdocs 当目录分隔符）。

    - 中文冒号 ： → 连字符 -
    - 其他 URL 不安全字符 → 保持原样
    """
    return name.replace("：", "-")


def collect_renamed_files(src_root: Path) -> dict[str, str]:
    """收集所有被改名的文件 (旧名 → 新名)，用于修复 docs 内的引用链接。"""
    mapping: dict[str, str] = {}
    for path in src_root.rglob("*"):
        if not path.is_file() or not should_copy(path):
            continue
        new_name = sanitize_filename(path.name)
        if new_name != path.name:
            mapping[path.name] = new_name
    return mapping


def fix_links_in_docs(docs_root: Path, name_map: dict[str, str]) -> int:
    """根据 name_map 修复 docs 内所有 md 的引用链接（](old.md) → ](new.md)）。

    同时处理全角：与半角：变体（源 README 可能用半角冒号引用全角冒号文件名）。
    """
    if not name_map:
        return 0
    # 展开 name_map：每个 old 名生成全角/半角两种变体
    expanded_map: dict[str, str] = {}
    for old, new in name_map.items():
        expanded_map[old] = new
        if "：" in old:
            expanded_map[old.replace("：", ":")] = new
        if ":" in old:
            expanded_map[old.replace(":", "：")] = new
    fixed_files = 0
    # 按名字长度倒序排
    for old, new in sorted(expanded_map.items(), key=lambda kv: -len(kv[0])):
        old_escaped = re.escape(old)
        for pattern, repl in [
            (r"\]\(\.\./" + old_escaped, r"](" + new),
            (r"\]\(\./" + old_escaped, r"](" + new),
            (r"\]\(" + old_escaped, r"](" + new),
        ]:
            for md in docs_root.rglob("*.md"):
                text = md.read_text(encoding="utf-8", errors="replace")
                if re.search(pattern, text):
                    new_text = re.sub(pattern, repl, text)
                    md.write_text(new_text, encoding="utf-8")
                    fixed_files += 1
    return fixed_files


def _write_stripped_md(src: Path, dst: Path) -> bool:
    """写入 md；若命中作者前言则剥离。返回是否发生剥离。"""
    global _PREAMBLE_STRIPPED
    raw = src.read_text(encoding="utf-8", errors="replace")
    new_text, changed = strip_author_preamble(raw)
    if changed:
        dst.write_text(new_text, encoding="utf-8", newline="\n")
        _PREAMBLE_STRIPPED += 1
        return True
    shutil.copy2(src, dst)
    return False


def _ensure_series_index_md(src_sub: Path, dst_sub: Path) -> None:
    """递归确保 leaf series 目录有 Feed 式 index.md。

    含嵌套子系列的目录（Kernel / Framework 等）由 ensure_subcategory_landing_pages
    生成子分类落地页，此处跳过以免覆盖为空的「暂无篇章」页。
    """
    if not dst_sub.exists():
        return
    if _list_nav_subdirs(dst_sub):
        for sub in src_sub.iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                _ensure_series_index_md(sub, dst_sub / sub.name)
        return
    module = _module_name_for(dst_sub)
    index_md = dst_sub / "index.md"
    try:
        index_md.write_text(
            build_series_landing_index(module, dst_sub),
            encoding="utf-8",
        )
    except OSError:
        pass
    for sub in src_sub.iterdir():
        if sub.is_dir() and not sub.name.startswith("."):
            _ensure_series_index_md(sub, dst_sub / sub.name)


def copy_tree(src: Path, dst: Path) -> int:
    """复制模块树到 docs/；对开启剥离的模块，.md 写入前切除 v4 作者前言。"""
    global _PREAMBLE_STRIPPED
    count = 0
    if not src.is_dir():
        return 0
    module = src.name
    strip = should_strip_module(module)
    for path in src.rglob("*"):
        if not should_copy(path):
            continue
        rel = path.relative_to(REPO_ROOT)
        if is_excluded(rel):
            continue
        # 文件名清洗：避免 mkdocs 把 ： 当作目录分隔符
        new_name = sanitize_filename(path.name)
        target = dst / path.relative_to(src).parent / new_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if strip and path.suffix.lower() == ".md":
            _write_stripped_md(path, target)
        else:
            shutil.copy2(path, target)
        count += 1
    # 阶段 4：递归确保每个有 README.md 的 series 目录都有 index.md
    for sub in src.iterdir():
        if sub.is_dir() and not sub.name.startswith("."):
            _ensure_series_index_md(sub, dst / sub.name)
    return count


def main() -> int:
    global _PREAMBLE_STRIPPED
    _PREAMBLE_STRIPPED = 0

    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True)

    # 阶段 3+：收集被改名的文件（避免 mkdocs 把 ： 当目录分隔符）
    name_map = collect_renamed_files(REPO_ROOT)
    if name_map:
        print(f"  sanitized {len(name_map)} filenames: 冒号 → 连字符")

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

    # 站点静态资源（顶栏 / 首页样式等）
    # 阶段 3：web/ 和 overrides/ 都在 00-Meta/ 下
    web_src = REPO_ROOT / "00-Meta" / "web"
    if web_src.is_dir():
        for path in web_src.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(web_src)
            dst = DOCS_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
            total += 1
        print("  00-Meta/web/: assets copied into docs/")

    overrides_src = REPO_ROOT / "00-Meta" / "overrides"
    if overrides_src.is_dir():
        # 保留 overrides/ 子目录结构（mkdocs.yml 用 custom_dir: overrides，
        # 需要 docs/overrides/partials/header.html）
        for path in overrides_src.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(overrides_src.parent)  # 保留 overrides/ 前缀
            dst = DOCS_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
            total += 1
        print("  00-Meta/overrides/: header/footer copied into docs/overrides/")

    # 修复 docs 内所有 md 的链接（同步新文件名）
    if name_map:
        n_fixed = fix_links_in_docs(DOCS_DIR, name_map)
        print(f"  fixed links in {n_fixed} files (synced renamed files)")

    generate_pages_tree(DOCS_DIR)
    print(f"Prepared docs/ with {total} content files; skipped ~{skipped_meta} meta docs")
    if _PREAMBLE_STRIPPED:
        print(
            f"  stripped author preamble from {_PREAMBLE_STRIPPED} pages "
            f"(public site → Activity-style lead)"
        )
    leftovers = audit_docs_for_preamble(DOCS_DIR)
    if leftovers:
        print(
            f"  WARN: {len(leftovers)} docs/ pages still have author preamble near top:",
            file=sys.stderr,
        )
        for p in leftovers[:20]:
            print(f"    - {p}", file=sys.stderr)
        if len(leftovers) > 20:
            print(f"    ... +{len(leftovers) - 20} more", file=sys.stderr)
    print("Generated layered .pages navigation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
