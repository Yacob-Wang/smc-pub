#!/usr/bin/env python3
"""以《书籍目录-v1.md》为唯一事实源，同步各卷 / 各章的 index.md。

只重写骨架页；已经写入正文的 index.md（有 frontmatter 或体量较大）保持不动，
避免同步动作覆盖真实内容。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
OUTLINE = REPO / "00-Meta" / "书籍目录-v1.md"

BASELINE = "AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8"
SKELETON_MARK = "sync_book_index.py"
LEGACY_MARK = "build_book_skeleton.py"
# 超过这个体量说明 index.md 已经承载正文，不再当骨架处理
SKELETON_MAX_BYTES = 2000

VOL_RE = re.compile(r"^# 卷 (\d+)　(.+)$")
CH_RE = re.compile(r"^## 第 (\d+) 章　(.+)$")
BULLET_RE = re.compile(r"^- \*\*(.+?)\*\*：(.*)$")
SUB_RE = re.compile(r"^  - (\d+\.\d+ .+)$")


@dataclass
class Chapter:
    number: int
    title: str
    positioning: str = ""
    subsections: list[str] = field(default_factory=list)
    summary: str = ""
    extras: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Volume:
    number: int
    title: str
    positioning: str = ""
    chapters: list[Chapter] = field(default_factory=list)


def parse_outline(text: str) -> list[Volume]:
    volumes: list[Volume] = []
    vol: Volume | None = None
    ch: Chapter | None = None
    in_subsections = False

    for line in text.splitlines():
        m = VOL_RE.match(line)
        if m:
            vol = Volume(number=int(m.group(1)), title=m.group(2).strip())
            volumes.append(vol)
            ch = None
            in_subsections = False
            continue

        if vol is not None and ch is None and line.startswith("> **本卷定位**："):
            vol.positioning = line.split("：", 1)[1].strip()
            continue

        m = CH_RE.match(line)
        if m and vol is not None:
            ch = Chapter(number=int(m.group(1)), title=m.group(2).strip())
            vol.chapters.append(ch)
            in_subsections = False
            continue

        if ch is None:
            continue

        m = SUB_RE.match(line)
        if m and in_subsections:
            ch.subsections.append(m.group(1).strip())
            continue

        m = BULLET_RE.match(line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            in_subsections = key == "核心子节"
            if key == "章定位":
                ch.positioning = value
            elif key == "本章小结":
                ch.summary = value
            elif key != "核心子节":
                ch.extras.append((key, value))
            continue

        if line.strip() and not line.startswith(" "):
            in_subsections = False

    return volumes


def volume_dir(number: int) -> Path | None:
    # 仓库根还留着 01-Mechanism 等旧 module 目录，只认 0N-卷N- 前缀
    prefix = f"{number:02d}-卷{number}-"
    for child in sorted(REPO.iterdir()):
        if child.is_dir() and child.name.startswith(prefix):
            return child
    return None


def chapter_dir(vol_dir: Path, number: int) -> Path | None:
    prefix = f"{number:02d}-"
    for child in sorted(vol_dir.iterdir()):
        if child.is_dir() and child.name.startswith(prefix):
            return child
    return None


def is_skeleton(path: Path) -> bool:
    if not path.is_file():
        return True
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.lstrip().startswith("---"):
        return False
    if path.stat().st_size > SKELETON_MAX_BYTES:
        return False
    return SKELETON_MARK in text or LEGACY_MARK in text


def article_count(chapter_dir: Path) -> int:
    return sum(
        1
        for p in chapter_dir.rglob("*.md")
        if p.name.lower() != "index.md" and not p.name.lower().startswith("readme")
    )


def chapter_status(chapter_dir: Path) -> str:
    return "🚧 撰写中" if article_count(chapter_dir) else "📋 待撰写"


def render_chapter_index(vol: Volume, ch: Chapter, ch_dir: Path) -> str:
    lines = [
        f"# 第 {ch.number} 章　{ch.title}",
        "",
        f"> **所属卷**：卷 {vol.number}　{vol.title}",
        f"> **章定位**：{ch.positioning}",
        f"> **工程基线**：{BASELINE}",
    ]
    for key, value in ch.extras:
        lines.append(f"> **{key}**：{value}")
    lines += ["", "## 核心子节", ""]
    lines += [f"- {s}" for s in ch.subsections]
    lines += ["", "## 本章小结", "", ch.summary, "", "---", ""]
    n = article_count(ch_dir)
    lines.append(
        f"**状态**：🚧 已有 {n} 篇，撰写中" if n else "**状态**：📋 骨架完成，待撰写"
    )
    lines.append(f"**生成**：{SKELETON_MARK}（源：00-Meta/书籍目录-v1.md）")
    return "\n".join(lines) + "\n"


def render_volume_index(vol: Volume, vol_dir: Path) -> str:
    lines = [
        f"# 卷 {vol.number}　{vol.title}",
        "",
        f"> **本卷定位**：{vol.positioning}",
        "",
        "## 章节目录",
        "",
        "| 章号 | 标题 | 状态 |",
        "|---|---|---|",
    ]
    for ch in vol.chapters:
        ch_dir = chapter_dir(vol_dir, ch.number)
        status = chapter_status(ch_dir) if ch_dir else "📋 待撰写"
        lines.append(f"| 第 {ch.number} 章 | {ch.title} | {status} |")

    lines += ["", "---", "", "## 章节详细", ""]
    for ch in vol.chapters:
        lines.append(f"### 第 {ch.number} 章　{ch.title}")
        lines.append("")
        lines.append(f"> {ch.positioning}")
        lines.append("")
        lines += [f"- {s}" for s in ch.subsections]
        lines.append("")
        lines.append(f"**本章小结**：{ch.summary}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    volumes = parse_outline(OUTLINE.read_text(encoding="utf-8"))
    total_ch = sum(len(v.chapters) for v in volumes)
    print(f"outline: {len(volumes)} volumes, {total_ch} chapters")
    if total_ch != 50:
        print(f"WARNING: expected 50 chapters, parsed {total_ch}", file=sys.stderr)

    written, skipped, missing = 0, [], []
    for vol in volumes:
        vol_dir = volume_dir(vol.number)
        if vol_dir is None:
            missing.append(f"volume {vol.number}")
            continue

        for ch in vol.chapters:
            ch_dir = chapter_dir(vol_dir, ch.number)
            if ch_dir is None:
                missing.append(f"chapter {ch.number} ({ch.title})")
                continue
            index = ch_dir / "index.md"
            if not is_skeleton(index):
                skipped.append(f"{ch.number} {ch.title}")
                continue
            index.write_text(
                render_chapter_index(vol, ch, ch_dir), encoding="utf-8"
            )
            written += 1

        (vol_dir / "index.md").write_text(
            render_volume_index(vol, vol_dir), encoding="utf-8"
        )
        written += 1

    print(f"written: {written} index.md")
    if skipped:
        print(f"preserved (has content): {len(skipped)}")
        for s in skipped:
            print(f"  第 {s}")
    if missing:
        print(f"MISSING dirs ({len(missing)}):", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
