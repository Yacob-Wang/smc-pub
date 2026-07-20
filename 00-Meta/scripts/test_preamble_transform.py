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


def main() -> int:
    test_s01_heavy()
    test_f01_heavy()
    test_dumpsys_heavy()
    test_case_heavy()
    test_watchdog_light_keeps_anchor()
    test_art_heavy_keeps_body()
    test_noop_plain()
    print("test_preamble_transform: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
