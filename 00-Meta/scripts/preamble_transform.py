#!/usr/bin/env python3
"""公开站文首变换：剥离 v4 作者元信息，保留标题 + 版本元信息 blockquote。

目标形态对齐 Activity：
  # 标题
  > 系列 / 版本基线 / …
  # 1. 背景与定义

四种作者元信息形态：
- AUTHOR_ONLY：<!-- AUTHOR_ONLY:START -->…<!-- AUTHOR_ONLY:END --> 整段剥离（Memory/IO/cgroup…）
- heavy：含「写作标准」或「校准决策日志」等——从前言起点切到正文起点（Symptom/Forensics/ART…）
- light：仅「本篇定位」等短段——按节切除，遇到读者正文子标题（如 #### §0）即停（Watchdog…）
- exception：「破例决策记录」——文首按 light 前言处理；篇中等任意位置整节剥离至下一同级/更高级标题
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# AUTHOR_ONLY HTML 注释块（可多处出现，含文首前言与篇尾自检）
_AUTHOR_ONLY_BLOCK = re.compile(
    r"<!--\s*AUTHOR_ONLY:START\s*-->.*?<!--\s*AUTHOR_ONLY:END\s*-->",
    re.DOTALL | re.IGNORECASE,
)

# 作者前言标题（文首连续块）
_PREAMBLE_HEADING = re.compile(
    r"^#{1,6}\s+(?:"
    r"本篇定位(?:声明)?(?:[（(].*)?|"
    r"0\.\s*(?:本篇|本附录|附录)定位(?:声明)?(?:[（(].*)?|"
    r"校准决策日志(?:[（(].*)?|"
    r"角色设定|"
    r"上下文|"
    r"写作标准|"
    r"硬性要求|"
    r"章节结构(?:[（(].*)?|"
    r"图表密度(?:[（(].*)?|"
    r"图表格式(?:[（(].*)?|"
    r"跨模块引用(?:规范)?(?:[（(].*)?|"
    r"写作约束(?:[（(].*)?|"
    r"交付标准(?:[（(].*)?|"
    r"验收标准(?:[（(].*)?|"
    r"系列定位(?:[（(].*)?|"
    r"禁止事项(?:[（(].*)?|"
    r"自检报告(?:[（(].*)?"
    r")\s*$"
)

# 破例决策记录（文首前言 + 篇中/篇尾整节剥离）
_EXCEPTION_DECISION_HEADING = re.compile(
    r"^#{1,6}\s+(?:[一二三四五六七八九十]+、|\d+(?:\.\d+)*\s*)?破例决策记录(?:[（(].*)?\s*$"
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
    r"(?m)^#{1,6}\s+(?:"
    r"写作标准|校准决策日志|章节结构|图表密度|跨模块引用|自检报告"
    r")\b"
)

# audit：文首窗口内仍残留的作者-only 信号（排除读者向 README 导航节）
_LEAD_TEMPLATE = re.compile(
    r"(?m)^#{1,6}\s+(?:"
    r"本篇定位|校准决策日志|角色设定|上下文|写作标准|"
    r"0\.\s*(?:本篇|本附录|附录)定位"
    r")\b"
)

# 默认对全部公开模块开启（无前言的文章为 no-op）
DEFAULT_STRIP_MODULES: frozenset[str] | None = None  # None = 全部


def heading_level(line: str) -> int:
    m = _ANY_HEADING.match(line)
    return len(m.group(1)) if m else 0


def is_exception_decision_heading(line: str) -> bool:
    return bool(_EXCEPTION_DECISION_HEADING.match(line.rstrip()))


def is_preamble_heading(line: str) -> bool:
    return bool(_PREAMBLE_HEADING.match(line.rstrip())) or is_exception_decision_heading(
        line
    )


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


def _normalize_after_strip(text: str, newline: str) -> str:
    """剥离后折叠多余空行、清掉标题区尾部孤立分隔线。"""
    lines = text.splitlines()
    out: list[str] = []
    blank_run = 0
    seen_body_heading = False
    for ln in lines:
        if _ANY_HEADING.match(ln) and not is_preamble_heading(ln):
            seen_body_heading = True
        if not seen_body_heading and ln.strip() in ("---", "***"):
            continue
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                out.append("")
            continue
        blank_run = 0
        out.append(ln)
    while out and out[0] == "":
        out.pop(0)
    # 折叠标题/meta 区重复 ---（剥离 AUTHOR_ONLY 后常见）
    compact: list[str] = []
    for ln in out:
        if ln.strip() in ("---", "***"):
            j = len(compact) - 1
            while j >= 0 and compact[j].strip() == "":
                j -= 1
            if j >= 0 and compact[j].strip() in ("---", "***"):
                continue
        compact.append(ln)
    out = compact
    result = newline.join(out)
    if text.endswith(("\n", "\r\n")) and result and not result.endswith(("\n", "\r\n")):
        result += newline
    return result


def _strip_exception_decision_sections(text: str) -> tuple[str, bool]:
    """剥离文中任意位置的「破例决策记录」节（至下一同级或更高级标题）。"""
    newline = "\r\n" if "\r\n" in text else "\n"
    ends_with_nl = text.endswith(("\n", "\r\n"))
    lines = text.splitlines()
    remove: set[int] = set()
    i = 0
    while i < len(lines):
        if is_exception_decision_heading(lines[i]):
            level = heading_level(lines[i])
            j = i + 1
            while j < len(lines):
                nxt = _ANY_HEADING.match(lines[j])
                if nxt and len(nxt.group(1)) <= level:
                    break
                j += 1
            remove.update(range(i, j))
            i = j
        else:
            i += 1
    if not remove:
        return text, False
    new_lines = [ln for idx, ln in enumerate(lines) if idx not in remove]
    new_text = newline.join(new_lines)
    if ends_with_nl and new_text and not new_text.endswith(("\n", "\r\n")):
        new_text += newline
    return new_text, True


def strip_author_only_blocks(text: str) -> tuple[str, bool]:
    """剥离全部 AUTHOR_ONLY 注释块（文首前言 + 篇尾自检等）。"""
    new_text, n = _AUTHOR_ONLY_BLOCK.subn("", text)
    if n == 0:
        return text, False
    newline = "\r\n" if "\r\n" in text else "\n"
    new_text = _normalize_after_strip(new_text, newline)
    return new_text, True


def _strip_heading_preamble(text: str) -> tuple[str, bool]:
    """切除文首 #/## 作者前言栈（不含 AUTHOR_ONLY 块）。"""
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
        new_lines = [ln for idx, ln in enumerate(lines) if idx not in remove]
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


def strip_author_preamble(text: str) -> tuple[str, bool]:
    """切除作者元信息：AUTHOR_ONLY 块 + 文首前言 + 破例决策记录节。返回 (新正文, 是否改过)。"""
    text, changed_ao = strip_author_only_blocks(text)
    text, changed_head = _strip_heading_preamble(text)
    text, changed_exc = _strip_exception_decision_sections(text)
    if changed_ao or changed_head or changed_exc:
        newline = "\r\n" if "\r\n" in text else "\n"
        text = _normalize_after_strip(text, newline)
        return text, True
    return text, False


def should_strip_module(module: str) -> bool:
    """None 哨兵 = 全部模块；否则按白名单。"""
    if DEFAULT_STRIP_MODULES is None:
        return True
    return module in DEFAULT_STRIP_MODULES


def audit_docs_for_preamble(docs_root: Path) -> list[str]:
    """扫描 docs/ 中仍残留作者元信息的页面（用于构建后告警）。"""
    offenders: list[str] = []
    if not docs_root.is_dir():
        return offenders
    for path in docs_root.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(docs_root)).replace("\\", "/")
        if _AUTHOR_ONLY_BLOCK.search(text):
            offenders.append(rel)
            continue
        lines = text.splitlines()
        tidx = _find_title_idx(lines)
        if tidx is None:
            continue
        scan = _skip_meta_after_title(lines, tidx)
        if scan < len(lines) and is_preamble_heading(lines[scan]):
            offenders.append(rel)
            continue
        lead = "\n".join(lines[tidx : min(len(lines), tidx + 200)])
        if _LEAD_TEMPLATE.search(lead):
            offenders.append(rel)
            continue
        if any(is_exception_decision_heading(ln) for ln in lines):
            offenders.append(rel)
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
