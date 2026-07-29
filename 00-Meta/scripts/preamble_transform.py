#!/usr/bin/env python3
"""公开站文首变换：剥离作者元信息，保留标题 + 短读者元信息 blockquote。

目标形态（读者视图）：
  # 标题
  > 系列 / 基线 / 本篇角色 / 强依赖（2–4 行）
  # 1. 背景与定义

文首过长作者前言（主线索 / 上一篇下一篇 / 目录位置 / 关联系列 / 目标读者 / 写作状态等）
在 prepare_web_docs 时从 lead blockquote 剥离，避免公开站文章页呈「旧版长前言」观感。

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

# 篇中/篇尾作者模板节标题关键词（不含「系列总定位」类读者导航）
_AUTHOR_SECTION_KEYWORDS = (
    "破例决策记录",
    "校准决策日志",
    "作者决策日志",
    "角色设定",
    "写作标准",
    "自检报告",
)

_AUTHOR_SECTION_TITLE = re.compile(
    r"^(?:0\.\s*)?(?:本篇|本附录|附录)定位(?:声明)?(?:[（(].*)?$"
)

_AUTHOR_SECTION_NUM_PREFIX = re.compile(
    r"^#{1,6}\s+(?:[一二三四五六七八九十]+、|\d+(?:[\.、]\d+)*[\.、]?\s*)?(.*)$"
)

# 文首 lead blockquote 中保留的读者元信息（v6：基线/角色/强依赖 + 系列变体）
_READER_META_LABELED = re.compile(
    r"^>\s*\*\*(?:"
    r"系列|本篇角色|强依赖|本子模块|工程基线|"
    r"基线|版本基线|源码基线|"
    r"[^*]*当前基线[^*]*"
    r")\*\*"
)
_READER_META_PLAIN = re.compile(
    r"^>\s*(?:基线\s*[:：]|系列第\s*\d+)"
)
_BLOCKQUOTE_FIELD_LABEL = re.compile(r"^>\s*\*\*[^*]+\*\*")

# 全文安全剥离的作者模板字段（不含正文导航「上一篇/下一篇」、也不含「日志时区」等正文标签）
_BLOCKQUOTE_AUTHOR_LINE = re.compile(
    r"^>\s*(?:"
    r"\*\*(?:本篇定位|本文定位|主线索|目录位置|"
    r"关联已有系列|关联系列|本系列关系|本系列定位|本系列结构|"
    r"承接自|衔接去|承接上[^:：*]*|"
    r"目标读者|读者画像|写作状态|完成时间|"
    r"v2 升级日期|预计篇幅|评估时间|评估基线|评估范围|作者决策日志|"
    r"本版（v2）的核心变化|质量门升级|源码标注说明|设备详)\*\*"
    r"|-\s*\*\*(?:质量门升级|本版（v2）的核心变化)\*\*"
    r")"
)

_BLOCKQUOTE_PROMPT_REF = re.compile(
    r"^>.*(?:PROMPT-|写作指南\.md|本规范的\s*6\s*个硬约束)"
)

_AUTHOR_DECISION_TABLE = re.compile(
    r"^\|\s*轮次\s*\|\s*类别\s*\|\s*决策\s*\|"
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

_AUDIT_BLOCKQUOTE_AUTHOR = re.compile(
    r"(?m)^>\s*\*\*(?:本篇定位|本文定位|主线索|目录位置|上一篇|下一篇|"
    r"关联已有系列|目标读者|读者画像|承接自|衔接去|作者决策日志|"
    r"v2 升级日期|预计篇幅|写作状态|本系列关系)\*\*"
)

_AUDIT_AUTHOR_SECTION = re.compile(
    r"(?m)^#{1,6}\s+.*(?:校准决策日志|作者决策日志|角色设定|写作标准|自检报告|破例决策记录)\b"
)

# 默认对全部公开模块开启（无前言的文章为 no-op）
DEFAULT_STRIP_MODULES: frozenset[str] | None = None  # None = 全部


def heading_level(line: str) -> int:
    m = _ANY_HEADING.match(line)
    return len(m.group(1)) if m else 0


def is_exception_decision_heading(line: str) -> bool:
    return bool(_EXCEPTION_DECISION_HEADING.match(line.rstrip()))


def is_author_template_section_heading(line: str) -> bool:
    s = line.rstrip()
    m = _AUTHOR_SECTION_NUM_PREFIX.match(s)
    if not m:
        return False
    title = m.group(1).strip()
    if any(k in title for k in _AUTHOR_SECTION_KEYWORDS):
        return True
    return bool(_AUTHOR_SECTION_TITLE.match(title))


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
    """首个非作者前言标题；允许文首存在 # 本篇定位 等 pre-title 块。"""
    for i, line in enumerate(lines):
        if _ANY_HEADING.match(line) and not is_preamble_heading(line):
            return i
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


def _strip_section_blocks(
    text: str, is_section_heading
) -> tuple[str, bool]:
    """剥离文中任意位置的作者模板节（至下一同级或更高级标题）。"""
    newline = "\r\n" if "\r\n" in text else "\n"
    ends_with_nl = text.endswith(("\n", "\r\n"))
    lines = text.splitlines()
    remove: set[int] = set()
    i = 0
    while i < len(lines):
        if is_section_heading(lines[i]):
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


def _strip_author_template_sections(text: str) -> tuple[str, bool]:
    """剥离篇中/篇尾作者模板节（校准日志、本篇定位、角色设定等）。"""
    return _strip_section_blocks(text, is_author_template_section_heading)


def _strip_exception_decision_sections(text: str) -> tuple[str, bool]:
    """剥离「破例决策记录」节（兼容旧调用）。"""
    return _strip_section_blocks(text, is_exception_decision_heading)


def _strip_pre_title_preamble(text: str) -> tuple[str, bool]:
    """剥离真实标题之前的 # 本篇定位 等前言块（epoll / socket bridge）。"""
    bom = text.startswith("\ufeff")
    body = text[1:] if bom else text
    newline = "\r\n" if "\r\n" in body else "\n"
    ends_with_nl = body.endswith(("\n", "\r\n"))
    lines = body.splitlines()
    title_idx = _find_title_idx(lines)
    if title_idx is None or title_idx == 0:
        return text, False
    if not any(
        _ANY_HEADING.match(lines[j]) and is_preamble_heading(lines[j])
        for j in range(title_idx)
    ):
        return text, False
    new_lines = lines[title_idx:]
    new_text = newline.join(new_lines)
    if ends_with_nl and new_text and not new_text.endswith(("\n", "\r\n")):
        new_text += newline
    if bom:
        new_text = "\ufeff" + new_text
    new_text = _normalize_after_strip(new_text, newline)
    return new_text, True


def _is_blockquote_line(line: str) -> bool:
    return line.lstrip().startswith(">")


def _is_reader_meta_bq_line(line: str) -> bool:
    s = line.rstrip()
    return bool(_READER_META_LABELED.match(s) or _READER_META_PLAIN.match(s))


def _lead_zone_end(lines: list[str], title_idx: int) -> int:
    """标题后元信息区终点：首个非空/非分隔线/非 blockquote 内容（含正文标题）。"""
    i = title_idx + 1
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or s in ("---", "***") or _is_blockquote_line(lines[i]):
            i += 1
            continue
        return i
    return len(lines)


def _strip_lead_blockquote_to_reader_meta(text: str) -> tuple[str, bool]:
    """文首 blockquote 只保留读者元信息行，剥离主线索/导航/读者画像等作者前言。"""
    bom = text.startswith("\ufeff")
    body = text[1:] if bom else text
    newline = "\r\n" if "\r\n" in body else "\n"
    ends_with_nl = body.endswith(("\n", "\r\n"))
    lines = body.splitlines()
    title_idx = _find_title_idx(lines)
    if title_idx is None:
        return text, False

    lead_end = _lead_zone_end(lines, title_idx)
    meta = lines[title_idx + 1 : lead_end]
    if not any(_is_blockquote_line(ln) for ln in meta):
        return text, False

    kept_bq: list[str] = []
    mode: str | None = None  # keep_cont | skip_cont
    changed = False
    for ln in meta:
        if not _is_blockquote_line(ln):
            mode = None
            continue
        s = ln.rstrip()
        if s.strip() in (">", ""):
            # 空引用行：不输出，并中断「读者续行」以免吞掉后续作者段之间的孤儿行
            if mode == "keep_cont":
                mode = None
            continue
        if _is_reader_meta_bq_line(ln):
            kept_bq.append(ln)
            mode = "keep_cont"
            continue
        if _BLOCKQUOTE_FIELD_LABEL.match(s) or _BLOCKQUOTE_PROMPT_REF.match(s):
            changed = True
            mode = "skip_cont"
            continue
        # 无标签续行：紧跟读者元信息则保留（如基线下一行的源码验证说明）
        if mode == "keep_cont":
            kept_bq.append(ln)
            continue
        changed = True
        mode = "skip_cont"

    # 只要 lead 里存在非读者 blockquote，或读者行集合发生变化，即视为变更
    original_bq = [ln for ln in meta if _is_blockquote_line(ln) and ln.rstrip().strip() not in (">", "")]
    if kept_bq == original_bq and not changed:
        return text, False

    had_hr = any(ln.strip() in ("---", "***") for ln in meta)
    spaced_bq: list[str] = []
    for idx, ln in enumerate(kept_bq):
        if idx:
            spaced_bq.append(">")
        spaced_bq.append(ln)

    new_lines = list(lines[: title_idx + 1])
    if spaced_bq:
        new_lines.append("")
        new_lines.extend(spaced_bq)
        new_lines.append("")
    elif title_idx + 1 < lead_end:
        new_lines.append("")
    if had_hr:
        new_lines.append("---")
        new_lines.append("")
    new_lines.extend(lines[lead_end:])

    new_text = newline.join(new_lines)
    if ends_with_nl and new_text and not new_text.endswith(("\n", "\r\n")):
        new_text += newline
    if bom:
        new_text = "\ufeff" + new_text
    return new_text, True


def _strip_blockquote_author_meta(text: str) -> tuple[str, bool]:
    """全文安全剥离已知作者模板字段行（含其 bullet 续行）。"""
    newline = "\r\n" if "\r\n" in text else "\n"
    ends_with_nl = text.endswith(("\n", "\r\n"))
    lines = text.splitlines()
    out: list[str] = []
    changed = False
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.rstrip()
        if _BLOCKQUOTE_AUTHOR_LINE.match(s) or _BLOCKQUOTE_PROMPT_REF.match(s):
            changed = True
            i += 1
            while i < len(lines):
                nxt = lines[i].rstrip()
                if not _is_blockquote_line(lines[i]):
                    break
                if nxt.strip() in (">", ""):
                    i += 1
                    continue
                if _BLOCKQUOTE_FIELD_LABEL.match(nxt):
                    break
                # 作者字段下的 bullet / 无标签续行
                i += 1
            continue
        out.append(ln)
        i += 1
    if not changed:
        return text, False
    new_text = newline.join(out)
    if ends_with_nl and new_text and not new_text.endswith(("\n", "\r\n")):
        new_text += newline
    return new_text, True


def _strip_author_decision_tables(text: str) -> tuple[str, bool]:
    """剥离作者决策/校准 Markdown 表格（含 orphan 表头 | 轮次 | 类别 | 决策 |）。"""
    newline = "\r\n" if "\r\n" in text else "\n"
    ends_with_nl = text.endswith(("\n", "\r\n"))
    lines = text.splitlines()
    remove: set[int] = set()
    i = 0
    while i < len(lines):
        start_table = False
        if "作者决策日志" in lines[i] and not lines[i].lstrip().startswith("#"):
            start_table = True
        elif _AUTHOR_DECISION_TABLE.match(lines[i].lstrip()):
            start_table = True
        if start_table:
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if _AUTHOR_DECISION_TABLE.match(lines[i].lstrip()):
                k = i + 1
                while k < len(lines):
                    if lines[k].strip() == "":
                        k += 1
                        continue
                    if lines[k].lstrip().startswith("|"):
                        k += 1
                        continue
                    break
                remove.update(range(i, k))
                i = k
                continue
            if j < len(lines) and lines[j].lstrip().startswith("|"):
                k = j
                while k < len(lines):
                    if lines[k].strip() == "":
                        k += 1
                        continue
                    if lines[k].lstrip().startswith("|"):
                        k += 1
                        continue
                    break
                remove.update(range(i, k))
                i = k
                continue
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
    """切除作者元信息：AUTHOR_ONLY + pre-title/heading 前言 + lead/全文 blockquote + 篇中作者节。"""
    original = text
    text, changed_ao = strip_author_only_blocks(text)
    text, changed_pre = _strip_pre_title_preamble(text)
    text, changed_head = _strip_heading_preamble(text)
    text, changed_lead = _strip_lead_blockquote_to_reader_meta(text)
    text, changed_bq = _strip_blockquote_author_meta(text)
    text, changed_tbl = _strip_author_decision_tables(text)
    text, changed_sec = _strip_author_template_sections(text)
    changed = (
        changed_ao
        or changed_pre
        or changed_head
        or changed_lead
        or changed_bq
        or changed_tbl
        or changed_sec
    )
    if changed:
        newline = "\r\n" if "\r\n" in original else "\n"
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
        lead_end = _lead_zone_end(lines, tidx)
        lead = "\n".join(lines[tidx:lead_end])
        if _LEAD_TEMPLATE.search(lead):
            offenders.append(rel)
            continue
        # 上一篇/下一篇等只审计文首；正文篇尾导航允许保留
        if _AUDIT_BLOCKQUOTE_AUTHOR.search(lead):
            offenders.append(rel)
            continue
        if _AUDIT_AUTHOR_SECTION.search(text):
            offenders.append(rel)
            continue
        if _AUTHOR_DECISION_TABLE.search(text):
            offenders.append(rel)
            continue
        if any(is_author_template_section_heading(ln) for ln in lines):
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
