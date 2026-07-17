"""
amlib.report - 报告生成

将巡检结果渲染为 Markdown 报告。
可用 Jinja2 模板,缺省时使用内置默认模板。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class ColdStartReport:
    """冷启动性能巡检报告"""

    def __init__(self, results: List[dict], device_info: Optional[dict] = None):
        self.results = results
        self.device_info = device_info or {}

    def render(self, output_path: str | Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 计算总览
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        warn = sum(1 for r in self.results if r["status"] == "WARN")

        lines = [
            f"# 冷启动性能巡检 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## 概述",
            "",
            f"- 设备: {self.device_info.get('model', 'unknown')} (Android {self.device_info.get('android_version', 'unknown')})",
            f"- 结果: ✅ {passed} 通过 / ⚠️ {warn} 警告 / ❌ {failed} 失败",
            "",
            "## 结果明细",
            "",
            "| Activity | 中位数 | 基线 | 变化 | 状态 |",
            "|---------|--------|------|------|------|",
        ]

        for r in self.results:
            status_icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(r["status"], "?")
            lines.append(
                f"| {r['activity']} | {r['median_ms']}ms | "
                f"{r['baseline_ms']}ms | {r['delta_pct']:+.1f}% | {status_icon} {r['status']} |"
            )

        lines.extend(
            [
                "",
                "## 失败定位",
                "",
            ]
        )

        for r in self.results:
            if r["status"] == "FAIL":
                lines.extend(
                    [
                        f"### {r['activity']} +{r['delta_pct']:.1f}%",
                        "",
                        f"- 中位数: {r['median_ms']}ms (基线 {r['baseline_ms']}ms)",
                        f"- 归档: `{r.get('trace', 'N/A')}`",
                        "",
                        "**建议**:",
                        "",
                        "1. 查看 trace 文件,定位启动慢的根因函数",
                        "2. 对比上次发版的 git diff",
                        "3. 修复后回归测试",
                        "",
                    ]
                )

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("冷启动报告生成: %s", output_path)
        return output_path


class MemoryReport:
    """内存压力巡检报告"""

    def __init__(self, snapshots: List[dict], device_info: Optional[dict] = None):
        """
        Args:
            snapshots: [{time_sec, total_mb, java_mb, native_mb, top_objects: [...]}, ...]
        """
        self.snapshots = snapshots
        self.device_info = device_info or {}

    def render(self, output_path: str | Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# 内存压力巡检 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## 概述",
            "",
            f"- 设备: {self.device_info.get('model', 'unknown')}",
            f"- 采样次数: {len(self.snapshots)}",
            "",
            "## 内存趋势",
            "",
            "| 时间 | 总内存 | Java 堆 | Native 堆 | Bitmap |",
            "|------|--------|---------|-----------|--------|",
        ]

        for s in self.snapshots:
            lines.append(
                f"| {s['time_sec'] // 60}min | {s.get('total_mb', '-')}MB | "
                f"{s.get('java_mb', '-')}MB | {s.get('native_mb', '-')}MB | "
                f"{s.get('bitmap_mb', '-')}MB |"
            )

        # 增长告警
        if len(self.snapshots) >= 2:
            first = self.snapshots[0]
            last = self.snapshots[-1]
            java_delta = (last.get("java_mb", 0) - first.get("java_mb", 0)) / max(
                first.get("java_mb", 1), 1
            )
            lines.extend(
                [
                    "",
                    f"## 增长告警",
                    "",
                    f"- Java 堆增长: {java_delta * 100:+.1f}%",
                ]
            )
            if java_delta > 0.5:
                lines.append("- ⚠️ **疑似内存泄漏** —— 增长超过 50%")
            else:
                lines.append("- ✅ Java 堆增长在正常范围(< 50%)")

        # Top 对象
        if self.snapshots and self.snapshots[-1].get("top_objects"):
            lines.extend(
                [
                    "",
                    f"## 对象增长 Top 5(末次采样)",
                    "",
                    "| 类名 | 数量 |",
                    "|------|------|",
                ]
            )
            for obj in self.snapshots[-1]["top_objects"][:5]:
                lines.append(f"| {obj['class_name']} | {obj['count']} |")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("内存报告生成: %s", output_path)
        return output_path


class StabilityReport:
    """进程稳定性巡检报告"""

    def __init__(
        self,
        crashes: List[dict],
        anrs: List[dict],
        iterations: int,
        device_info: Optional[dict] = None,
    ):
        self.crashes = crashes
        self.anrs = anrs
        self.iterations = iterations
        self.device_info = device_info or {}

    def render(self, output_path: str | Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        crash_rate = len(self.crashes) / max(self.iterations, 1) * 100
        anr_rate = len(self.anrs) / max(self.iterations, 1) * 100

        crash_status = "❌ FAIL" if crash_rate > 0.1 else "✅ PASS"
        anr_status = "❌ FAIL" if anr_rate > 0.05 else "✅ PASS"

        lines = [
            f"# 进程稳定性巡检 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## 概述",
            "",
            f"- 设备: {self.device_info.get('model', 'unknown')}",
            f"- 压测次数: {self.iterations}",
            "",
            "## 关键指标",
            "",
            "| 指标 | 本次 | 阈值 | 状态 |",
            "|------|------|------|------|",
            f"| 崩溃率 | {crash_rate:.3f}% ({len(self.crashes)}/{self.iterations}) | < 0.1% | {crash_status} |",
            f"| ANR 率 | {anr_rate:.3f}% ({len(self.anrs)}/{self.iterations}) | < 0.05% | {anr_status} |",
            "",
            "## Crash 事件",
            "",
        ]

        if self.crashes:
            lines.extend(
                [
                    "| 时间 | 异常 | 归档 |",
                    "|------|------|------|",
                ]
            )
            for c in self.crashes:
                lines.append(
                    f"| {c.get('timestamp', '-')} | {c.get('exception', '-')} | "
                    f"{c.get('archive', '-')} |"
                )
        else:
            lines.append("无 Crash 事件")

        lines.extend(
            [
                "",
                "## ANR 事件",
                "",
            ]
        )

        if self.anrs:
            lines.extend(
                [
                    "| 时间 | 类型 | traces 文件 |",
                    "|------|------|-----------|",
                ]
            )
            for a in self.anrs:
                lines.append(
                    f"| {a.get('timestamp', '-')} | {a.get('type', '-')} | "
                    f"{a.get('archive', '-')} |"
                )
        else:
            lines.append("无 ANR 事件")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("稳定性报告生成: %s", output_path)
        return output_path