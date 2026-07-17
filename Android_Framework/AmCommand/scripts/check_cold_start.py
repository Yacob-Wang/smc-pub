"""
check_cold_start.py - 冷启动性能巡检脚本

典型用法:
    python check_cold_start.py \\
        --package com.example.app \\
        --activities .MainActivity .MineActivity .OrderActivity .DetailActivity \\
        --baseline-ms 720 \\
        --threshold-pct 20 \\
        --output-dir ./reports/cold_start

详见 06 篇 §3。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# 让脚本可以单独运行
sys.path.insert(0, str(Path(__file__).parent))

from amlib import Device, AM  # noqa: E402
from amlib.artifact import ArtifactCollector  # noqa: E402
from amlib.report import ColdStartReport  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def check_cold_start(
    package: str,
    activities: list,
    baseline_ms: int,
    threshold_pct: float = 20.0,
    samples: int = 3,
    with_trace: bool = True,
    output_dir: str = "./reports/cold_start",
    device: Device = None,
) -> list:
    """
    对每个 Activity 测 N 次冷启动,对比基线,产出报告。

    Args:
        package: 包名
        activities: Activity 短名列表(如 ['.MainActivity'])
        baseline_ms: 基线耗时(ms)
        threshold_pct: 劣化阈值百分比
        samples: 每个 Activity 测几次(取中位数)
        with_trace: 是否同步采 profile trace
        output_dir: 报告输出目录
        device: 注入的设备(默认选第一台)

    Returns:
        结果列表
    """
    device = device or Device()
    am = AM(device)
    collector = ArtifactCollector(device, output_dir=output_dir)

    results = []

    for activity in activities:
        component = f"{package}/{activity}"
        logger.info("=" * 60)
        logger.info("测试: %s", component)
        logger.info("=" * 60)

        # 1. 强制停止,确保冷启动
        am.force_stop(package)
        time.sleep(2)

        # 2. 测 N 次取中位数
        timings = []
        for i in range(samples):
            t = am.cold_start_time(component)
            wait_time = t.get("WaitTime", 0)
            logger.info("  第 %d 次: WaitTime = %d ms", i + 1, wait_time)
            timings.append(wait_time)
            time.sleep(2)
        median_ms = sorted(timings)[len(timings) // 2]

        # 3. 判定状态
        delta_pct = (median_ms - baseline_ms) / baseline_ms * 100
        if delta_pct > threshold_pct:
            status = "FAIL"
        elif delta_pct > threshold_pct * 0.7:
            status = "WARN"
        else:
            status = "PASS"

        # 4. 同步采 profile(可选)
        trace_path = None
        if with_trace and status != "PASS":
            try:
                pid = am.get_pid(package)
                logger.info("  同步采 profile trace(劣化 %,采 5s)...", f"+{delta_pct:.1f}%")
                trace_path = collector.collect_profile(
                    pid=pid, duration_sec=5, scene=f"cold_start_{activity}"
                )
                logger.info("  trace: %s", trace_path)
            except Exception as e:
                logger.warning("profile 采集失败: %s", e)

        results.append(
            {
                "activity": activity,
                "median_ms": median_ms,
                "baseline_ms": baseline_ms,
                "delta_pct": delta_pct,
                "status": status,
                "trace": str(trace_path) if trace_path else None,
                "samples": timings,
            }
        )
        logger.info("  结果: 中位数 %d ms (基线 %d, +%.1f%%) -> %s",
                    median_ms, baseline_ms, delta_pct, status)

    # 5. 生成报告
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    report_path = output_dir_path / "latest.md"
    ColdStartReport(results, device.get_device_info()).render(report_path)
    logger.info("报告生成: %s", report_path)

    return results


def main():
    parser = argparse.ArgumentParser(description="冷启动性能巡检")
    parser.add_argument("--package", required=True, help="包名,如 com.example.app")
    parser.add_argument(
        "--activities",
        nargs="+",
        required=True,
        help="Activity 短名列表,如 .MainActivity .MineActivity",
    )
    parser.add_argument("--baseline-ms", type=int, required=True, help="基线耗时(ms)")
    parser.add_argument("--threshold-pct", type=float, default=20.0, help="劣化阈值百分比")
    parser.add_argument("--samples", type=int, default=3, help="每个 Activity 测几次(取中位数)")
    parser.add_argument("--with-trace", action="store_true", help="劣化时同步采 trace")
    parser.add_argument("--output-dir", default="./reports/cold_start", help="报告输出目录")
    parser.add_argument("--device-serial", default=None, help="指定设备 serial")

    args = parser.parse_args()

    device = Device(serial=args.device_serial) if args.device_serial else Device()

    try:
        results = check_cold_start(
            package=args.package,
            activities=args.activities,
            baseline_ms=args.baseline_ms,
            threshold_pct=args.threshold_pct,
            samples=args.samples,
            with_trace=args.with_trace,
            output_dir=args.output_dir,
            device=device,
        )
    except Exception as e:
        logger.error("巡检失败: %s", e)
        sys.exit(1)

    # 退出码:有 FAIL 返回 1
    has_fail = any(r["status"] == "FAIL" for r in results)
    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()