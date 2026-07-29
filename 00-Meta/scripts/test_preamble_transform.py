#!/usr/bin/env python3
"""preamble_transform 样例断言。"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))

from preamble_transform import strip_author_preamble  # noqa: E402

REPO = _SCRIPTS.parent.parent


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_s01_heavy() -> None:
    raw = (REPO / "02-Symptom/S01-ANR/01-症状机制.md").read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "S01 should strip")
    _assert("**版本基线**" in out or "**系列**" in out, "S01 keep meta")
    _assert("# 1. 背景与定义" in out, "S01 body")
    _assert("# 本篇定位" not in out, "S01 定位 gone")
    _assert("# 写作标准" not in out, "S01 写作标准 gone")


def test_f01_heavy() -> None:
    raw = (REPO / "03-Forensics/F01-ANR/01-取证机制.md").read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "F01 should strip")
    _assert("# 1. 背景与定义" in out, "F01 body")
    _assert("# 本篇定位" not in out, "F01 定位 gone")


def test_dumpsys_heavy() -> None:
    raw = (REPO / "04-Tool/Dumpsys/01-dumpsys总览与架构.md").read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Dumpsys should strip")
    _assert("# 本篇定位" not in out, "Dumpsys 定位 gone")
    _assert("# 写作标准" not in out, "Dumpsys 写作标准 gone")


def test_case_heavy() -> None:
    raw = (REPO / "06-Case/Startup/E01-冷启动8s-1s.md").read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Case E01 should strip")
    _assert("# 本篇定位" not in out, "Case 定位 gone")


def test_watchdog_light_keeps_anchor() -> None:
    raw = (
        REPO / "04-Tool/Watchdog/01-Watchdog概述与体系位置.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Watchdog should strip 本篇定位")
    _assert("## 本篇定位" not in out, "Watchdog 定位 gone")
    _assert("§0 锚点案例" in out or "锚点案例" in out, "Watchdog keep §0 anchor")
    _assert("## 一、背景与定义" in out, "Watchdog body kept")


def test_art_heavy_keeps_body() -> None:
    raw = (
        REPO
        / "01-Mechanism/Runtime/ART/08-对比与演进/04-监控与诊断基础设施.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "ART should strip")
    _assert("本篇定位声明" not in out.split("## 1.")[0], "ART 定位声明 gone from lead")
    _assert("校准决策日志" not in out.split("## 1.")[0], "ART 校准 gone from lead")
    _assert("## 1. 背景与定义" in out, "ART body kept")


def test_noop_plain() -> None:
    sample = "# Hello\n\n> **基线**：x\n\n## 一、背景与定义\n\nbody\n"
    out, changed = strip_author_preamble(sample)
    _assert(not changed, "plain unchanged")
    _assert(out == sample, "plain identity")


def test_process_08_lead_blockquote_compact() -> None:
    """Process 长文首作者前言 → 读者视图只留基线，从 H1/正文切入。"""
    raw = (
        REPO
        / "01-Mechanism/Framework/Process/08-进程稳定性风险全景与跨层治理.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Process 08 should strip lead author blockquote")
    lead = out.split("## 目录")[0] if "## 目录" in out else out.split("## 1.")[0]
    _assert("> **基线**" in lead or "> **基线**:" in lead or "> **基线**：" in lead, "Process 08 keep 基线")
    for needle in (
        "主线索",
        "本篇定位",
        "目录位置",
        "上一篇",
        "下一篇",
        "关联已有系列",
    ):
        _assert(needle not in lead, f"Process 08 lead should drop {needle}")
    _assert("## 1. 背景" in out or "## 目录" in out, "Process 08 body kept")
    # 正文内引用块不应被误伤
    _assert("架构师视角的" in out, "Process 08 body callout kept")


def test_activity_lead_keeps_reader_meta_only() -> None:
    raw = (REPO / "01-Mechanism/Framework/Activity/01_Activity_Overview.md").read_text(
        encoding="utf-8"
    )
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Activity A01 should strip 承接/衔接 from lead")
    lead = out.split("## 一、")[0]
    _assert("> **基线**" in lead, "Activity keep 基线")
    _assert("> **本篇角色**" in lead, "Activity keep 本篇角色")
    _assert("> **强依赖**" in lead, "Activity keep 强依赖")
    _assert("承接自" not in lead, "Activity drop 承接自")
    _assert("衔接去" not in lead, "Activity drop 衔接去")


def test_s01_drops_author_status_fields() -> None:
    raw = (REPO / "02-Symptom/S01-ANR/01-症状机制.md").read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "S01 should strip 目标读者/状态等")
    lead = out.split("# 1. 背景与定义")[0]
    _assert("**系列**" in lead or "**版本基线**" in lead, "S01 keep series/baseline")
    _assert("目标读者" not in lead, "S01 drop 目标读者")
    _assert("完成时间" not in lead, "S01 drop 完成时间")
    _assert("**状态**" not in lead, "S01 drop 状态")


def test_mm_author_only_blocks() -> None:
    raw = (
        REPO
        / "01-Mechanism/Kernel/Memory_Management/07-内存回收子系统：LRU-MGLRU-kswapd-的演进逻辑.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "MM 07 should strip AUTHOR_ONLY")
    _assert("AUTHOR_ONLY" not in out, "MM 07 markers gone")
    _assert("# 本篇定位" not in out, "MM 07 本篇定位 gone")
    _assert("# 校准决策日志" not in out, "MM 07 校准 gone")
    _assert("# 角色设定" not in out, "MM 07 角色设定 gone")
    _assert("# 写作标准" not in out, "MM 07 写作标准 gone")
    _assert("## 章节结构" not in out, "MM 07 章节结构 gone")
    _assert("## 学习目标" in out, "MM 07 keep 学习目标")
    _assert("## 一、内存回收" in out, "MM 07 body kept")
    _assert("## 自检报告" not in out, "MM 07 trailing self-check gone")
    _assert("破例决策记录" not in out, "MM 07 破例决策记录 gone")
    _assert("## 篇尾衔接" in out, "MM 07 keep 篇尾衔接")


def test_cgroup_author_only_lead() -> None:
    raw = (
        REPO
        / "01-Mechanism/Kernel/cgroup/01-cgroup的诞生与历史演进_从2006到Android17.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "cgroup 01 should strip")
    _assert("# 本篇定位" not in out, "cgroup 01 定位 gone")
    _assert("# cgroup 的诞生与历史演进" in out, "cgroup 01 real title kept")


def test_process_exit_author_only_before_title() -> None:
    raw = (
        REPO
        / "01-Mechanism/Framework/Process_Exit/03-杀进程慢的真正根因：诱因-根因-证伪.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Process_Exit 03 should strip")
    _assert(out.lstrip().startswith("# 杀进程慢"), "Process_Exit 03 starts with title")
    _assert("# 本篇定位" not in out, "Process_Exit 03 定位 gone")


def test_art_gc_merged_author_only() -> None:
    """GC 已收官为 11 篇合并单版；旧 appendix/D-工程基线 路径不再存在。"""
    raw = (
        REPO / "01-Mechanism/Runtime/ART/03-GC系统/01-基础理论专题.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "ART GC 01 should strip")
    _assert("校准决策日志" not in out, "ART GC 01 校准 gone")
    _assert("本篇定位声明" not in out, "ART GC 01 定位声明 gone")
    _assert("# 本篇定位" not in out, "ART GC 01 本篇定位 gone")
    _assert("## 一、为什么不用引用计数" in out, "ART GC 01 body kept")
    _assert("## 附录 D:工程基线表" in out, "ART GC 01 附录 D kept")


def test_activity_exception_decision_at_lead() -> None:
    raw = (REPO / "01-Mechanism/Framework/Activity/01_Activity_Overview.md").read_text(
        encoding="utf-8"
    )
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Activity A01 should strip")
    _assert("破例决策记录" not in out, "Activity A01 破例决策记录 gone")
    _assert("## 一、背景与定义" in out, "Activity A01 body kept")


def test_art_gc_blockquote_meta() -> None:
    """原 07-GC调度与触发/01-9种GcCause.md 已并入 07-GC调度与触发专题.md。"""
    raw = (
        REPO / "01-Mechanism/Runtime/ART/03-GC系统/07-GC调度与触发专题.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "ART GcCause should strip")
    _assert("本篇定位声明" not in out, "ART GcCause 定位声明 gone")
    _assert("# 本篇定位" not in out, "ART GcCause 本篇定位 gone")
    _assert("## 一、13 种 GcCause 完整枚举" in out, "ART GcCause body kept")
    _assert("> 基线:" in out, "ART GcCause keep baseline")


def test_mm_blockquote_meta() -> None:
    raw = (
        REPO
        / "01-Mechanism/Kernel/Memory_Management/07-内存回收子系统：LRU-MGLRU-kswapd-的演进逻辑.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "MM 07 should strip blockquote meta")
    _assert("> **本文定位**" not in out, "MM 07 本文定位 gone")
    _assert("> **预计篇幅**" not in out, "MM 07 预计篇幅 gone")
    _assert("> **读者画像**" not in out, "MM 07 读者画像 gone")
    _assert("> **源码基线**" in out, "MM 07 keep 源码基线")
    _assert("## 学习目标" in out, "MM 07 keep 学习目标")


def test_epoll_pre_title_preamble() -> None:
    raw = (
        REPO / "01-Mechanism/Kernel/epoll/01-epoll总览与核心机制.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "epoll should strip pre-title preamble")
    _assert(out.lstrip().startswith("# epoll 深度解析"), "epoll starts with real title")
    _assert("# 本篇定位" not in out.split("## 一、")[0], "epoll pre-title gone")
    _assert("## 一、背景与定义" in out, "epoll body kept")


def test_binder_readme_author_table() -> None:
    raw = (
        REPO / "01-Mechanism/Kernel/Binder/README-Binder系列.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Binder README should strip")
    _assert("| 轮次 | 类别 | 决策 |" not in out, "Binder README decision table gone")
    _assert("## 1. 为什么要写这个系列" in out, "Binder README body kept")


def test_binder_article_calibration_appendix() -> None:
    raw = (
        REPO / "01-Mechanism/Kernel/Binder/01-Binder总览.md"
    ).read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Binder 01 should strip")
    _assert("3 轮校准决策日志" not in out, "Binder 01 calibration appendix gone")
    _assert("## 1. Binder 是什么" in out, "Binder 01 body kept")


def test_symptom_readme_calibration_tail() -> None:
    raw = (REPO / "02-Symptom/README.md").read_text(encoding="utf-8")
    out, changed = strip_author_preamble(raw)
    _assert(changed, "Symptom README should strip calibration tail")
    _assert("校准决策日志" not in out, "Symptom README calibration gone")
    _assert("## 0. 系列总定位" in out, "Symptom README keep series nav")


def main() -> int:
    test_s01_heavy()
    test_f01_heavy()
    test_dumpsys_heavy()
    test_case_heavy()
    test_watchdog_light_keeps_anchor()
    test_art_heavy_keeps_body()
    test_mm_author_only_blocks()
    test_cgroup_author_only_lead()
    test_process_exit_author_only_before_title()
    test_art_gc_merged_author_only()
    test_activity_exception_decision_at_lead()
    test_art_gc_blockquote_meta()
    test_mm_blockquote_meta()
    test_epoll_pre_title_preamble()
    test_binder_readme_author_table()
    test_binder_article_calibration_appendix()
    test_symptom_readme_calibration_tail()
    test_noop_plain()
    test_process_08_lead_blockquote_compact()
    test_activity_lead_keeps_reader_meta_only()
    test_s01_drops_author_status_fields()
    print("test_preamble_transform: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
