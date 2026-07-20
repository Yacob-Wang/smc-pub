#!/usr/bin/env python3
"""公开站文首变换：剥离 v4 作者前言，保留标题 + 版本元信息 blockquote。

目标形态对齐 Activity：
  # 标题
  > 系列 / 版本基线 / …
  # 1. 背景与定义

两种前言形态：
- heavy：含「写作标准」或「校准决策日志」——从前言起点切到正文起点（Symptom/Forensics/ART…）
- light：仅「本篇定位」等短段——按节切除，遇到读者正文子标题（如 #### §0）即停（Watchdog…）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 作者前言标题（文首连续块）
_PREAMBLE_HEADING = re.compile(
    r"^#{1,6}\s+(?:"
    r"本篇定位(?:声明)?(?:[（(].*)?|"
    r"0\.\s*本篇定位(?:声明)?(?:[（(].*)?|"
    r"校准决策日志(?:[（(].*)?|"
    r"角色设定|"
    r"上下文|"
    r"写作标准|"
    r"硬性要求|"
    r"(?:[一二三四五六七八九十]+、|\d+(?:\.\d+)*\s*)?破例决策记录(?:[（(].*)?"
    r")\s*$"
)

# 校准日志下的轮次小标题（仍属前言）
_CALIBRATION_SUB = re.compile(
    r"^#{1,6}\s+(?:第\s*[一二三四五六七八九十\d]+\s*轮|结构校准|硬伤校准|锐度校准)\b"
)

# 正文起点：一、… / 1. … / 1、…
_BODY_START = re.compile(
    r"^#{1,6}\s+(?:"
    r"[一二三四五六七八九十]+、|"
    r"\d+[\.、]\s*"
    r")"
)

_ANY_HEADING = re.compile(r"^(#{1,6})\s+\S")
_HEAVY_MARKER = re.compile(
    r"(?m)^#{1,6}\s+(?:写作标准|校准决策日志)\b"
)

# 默认对全部公开模块开启（无前言的文章为 no-op）
DEFAULT_STRIP_MODULES: frozenset[str] | None = None  # None = 全部


def heading_level(line: str) -> int:
    m = _ANY_HEADING.match(line)
    return len(m.group(1)) if m else 0


def is_preamble_heading(line: str) -> bool:
    return bool(_PREAMBLE_HEADING.match(line.rstrip()))


def is_body_start(line: str) -> bool:
    # 「0. 本篇定位声明」也会命中 \d+. 模式，必须先排除前言标题
    if is_preamble_heading(line):
        return False
    return bool(_BODY_START.match(line.rstrip()))


def is_calibration_sub(line: str) -> bool:
    return bool(_CALIBRATION_SUB.match(line.rstrip()))


def _skip_meta_after_title(lines: list[str], title_idx: int) -> int:
    i = title_idx + 1
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or s in ("---", "***") or lines[i].lstrip().startswith(">"):
            i += 1
            continue
        break
    return i


def _find_title_idx(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        if _ANY_HEADING.match(line) and not is_preamble_heading(line):
            return i
        if is_preamble_heading(line):
            return None
    return None


def _heavy_cut(lines: list[str], preamble_start: int) -> int | None:
    """切到正文起点（含校准子节）。"""
    for j in range(preamble_start, len(lines)):
        if is_body_start(lines[j]):
            return j
        if (
            j > preamble_start
            and _ANY_HEADING.match(lines[j])
            and not is_preamble_heading(lines[j])
            and not is_calibration_sub(lines[j])
        ):
            return j
    return None


def _light_strip_ranges(lines: list[str], start: int) -> list[tuple[int, int]]:
    """逐节剥离 light 前言，返回待删 [start, end) 区间列表。"""
    ranges: list[tuple[int, int]] = []
    i = start
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or s in ("---", "***"):
            i += 1
            continue
        if not is_preamble_heading(lines[i]):
            break
        j = i + 1
        while j < len(lines):
            if not _ANY_HEADING.match(lines[j]):
                j += 1
                continue
            if is_preamble_heading(lines[j]) or is_body_start(lines[j]):
                break
            if is_calibration_sub(lines[j]):
                j += 1
                continue
            # light：任何非前言标题都结束本节（保留 #### §0 等读者正文）
            break
        ranges.append((i, j))
        i = j
    return ranges


def strip_author_preamble(text: str) -> tuple[str, bool]:
    """切除文首作者前言栈。返回 (新正文, 是否改过)。"""
    bom = text.startswith("\ufeff")
    body = text[1:] if bom else text
    newline = "\r\n" if "\r\n" in body else "\n"
    ends_with_nl = body.endswith(("\n", "\r\n"))
    lines = body.splitlines()

    if not lines:
        return text, False

    title_idx = _find_title_idx(lines)
    if title_idx is None:
        return text, False

    i = _skip_meta_after_title(lines, title_idx)
    if i >= len(lines) or not is_preamble_heading(lines[i]):
        return text, False

    preamble_start = i
    # 扫描文首窗口判断 heavy / light
    window = "\n".join(lines[preamble_start : preamble_start + 120])
    heavy = bool(_HEAVY_MARKER.search(window))

    if heavy:
        body_idx = _heavy_cut(lines, preamble_start)
        if body_idx is None:
            return text, False
        head = lines[:preamble_start]
        while head and head[-1].strip() in ("", "---", "***"):
            head.pop()
        new_lines = head + [""] + lines[body_idx:]
    else:
        ranges = _light_strip_ranges(lines, preamble_start)
        if not ranges:
            return text, False
        remove = set()
        for a, b in ranges:
            remove.update(range(a, b))
        # 删掉前言块后，清掉夹在中间的孤立 ---
        new_lines = [ln for idx, ln in enumerate(lines) if idx not in remove]
        # 标题区尾部清理
        # 找到原 preamble_start 在新列表中的位置约等于 title 后
        # 简单规范化：压缩标题后多余 ---
        out: list[str] = []
        seen_title_meta = False
        blank_run = 0
        for ln in new_lines:
            if _ANY_HEADING.match(ln) and not is_preamble_heading(ln) and not seen_title_meta:
                out.append(ln)
                seen_title_meta = True
                blank_run = 0
                continue
            if not seen_title_meta:
                out.append(ln)
                continue
            # 已过标题：折叠连续空行 / ---
            if ln.strip() in ("", "---", "***"):
                blank_run += 1
                if blank_run == 1:
                    out.append("")
                continue
            blank_run = 0
            out.append(ln)
        new_lines = out

    new_text = newline.join(new_lines)
    if ends_with_nl and not new_text.endswith(("\n", "\r\n")):
        new_text += newline
    if bom:
        new_text = "\ufeff" + new_text
    if new_text == text:
        return text, False
    return new_text, True


def should_strip_module(module: str) -> bool:
    """None 哨兵 = 全部模块；否则按白名单。"""
    if DEFAULT_STRIP_MODULES is None:
        return True
    return module in DEFAULT_STRIP_MODULES


def audit_docs_for_preamble(docs_root: Path) -> list[str]:
    """扫描 docs/ 中仍残留文首作者前言的页面（用于构建后告警）。"""
    offenders: list[str] = []
    if not docs_root.is_dir():
        return offenders
    for path in docs_root.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        tidx = _find_title_idx(lines)
        if tidx is None:
            continue
        scan = _skip_meta_after_title(lines, tidx)
        if scan < len(lines) and is_preamble_heading(lines[scan]):
            offenders.append(str(path.relative_to(docs_root)).replace("\\", "/"))
    return offenders


if __name__ == "__main__":
    # python preamble_transform.py audit [docs_dir]
    if len(sys.argv) >= 2 and sys.argv[1] == "audit":
        root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs")
        left = audit_docs_for_preamble(root)
        if left:
            print(f"FAIL: {len(left)} docs still have author preamble near top:")
            for p in left[:40]:
                print(" -", p)
            if len(left) > 40:
                print(f" ... +{len(left) - 40} more")
            raise SystemExit(1)
        print(f"OK: no author preamble left in {root}/ leads")
        raise SystemExit(0)
    print("Usage: python preamble_transform.py audit [docs_dir]", file=sys.stderr)
    raise SystemExit(2)
