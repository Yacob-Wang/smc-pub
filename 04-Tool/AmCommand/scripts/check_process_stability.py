"""
check_process_stability.py - 进程稳定性巡检脚本

典型用法:
    python check_process_stability.py \\
        --package com.example.app \\
        --iterations 1000 \\
        --output-dir ./reports/stability

详见 06 篇 §5。
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from amlib import Device, AM  # noqa: E402
from amlib.artifact import ArtifactCollector  # noqa: E402
from amlib.report import StabilityReport  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def check_process_stability(
    package: str,
    iterations: int = 1000,
    throttle_ms: int = 100,
    with_collect_on_crash: bool = True,
    output_dir: str = "./reports/stability",
    device: Device = None,
) -> dict:
    """
    跑 N 次 monkey,捕获 crash/anr 事件,产出稳定性报告。

    Args:
        package: 包名
        iterations: monkey 事件数
        throttle_ms: 每个事件间隔
        with_collect_on_crash: 每次 crash 是否自动三段式现场保留
        output_dir: 报告输出目录
        device: 注入的设备

    Returns:
        {'crashes': [...], 'anrs': [...], 'crash_rate': %, 'anr_rate': %}
    """
    device = device or Device()
    am = AM(device)
    collector = ArtifactCollector(device, output_dir=output_dir)

    # 1. 启动 am monitor 后台监控
    logger.info("启动 am monitor 后台监控...")
    monitor_session = am.monitor_start()
    time.sleep(2)  # 等 monitor 起来

    # 2. 启动 monkey 压测
    logger.info("启动 monkey 压测 (iterations=%d, throttle=%dms)...", iterations, throttle_ms)
    monkey_cmd = [
        "adb", "-s", device.serial, "shell",
        "monkey",
        "-p", package,
        "--throttle", str(throttle_ms),
        "--pct-touch", "40",
        "--pct-motion", "25",
        "--pct-trackball", "0",
        "--pct-syskeys", "0",
        "--pct-anyevent", "0",
        "--pct-nav", "20",
        "--pct-majornav", "15",
        "-v", str(iterations),
    ]
    monkey_proc = subprocess.Popen(
        monkey_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

    crashes = []
    anrs = []

    try:
        # 3. 持续读 monitor + monkey 输出,捕获事件
        import threading
        import queue
        event_queue: queue.Queue = queue.Queue()

        def monkey_reader():
            """读 monkey 输出,识别 crash/anr"""
            for line in monkey_proc.stdout:
                event_queue.put(("monkey", line.strip()))

        def monitor_poller():
            """定期 poll monitor 事件"""
            while monkey_proc.poll() is None:
                try:
                    events = monitor_session.collect_events(timeout_sec=2)
                    for e in events:
                        event_queue.put(("monitor", e))
                except Exception:
                    pass

        t1 = threading.Thread(target=monkey_reader, daemon=True)
        t2 = threading.Thread(target=monitor_poller, daemon=True)
        t1.start()
        t2.start()

        # 主线程处理事件
        crash_archive_paths = []
        while monkey_proc.poll() is None or not event_queue.empty():
            try:
                source, payload = event_queue.get(timeout=2)
            except queue.Empty:
                continue

            if source == "monitor" and isinstance(payload, dict):
                event_type = payload.get("type")
                if event_type == "crash":
                    logger.warning("⚠️ Crash 事件: %s", payload.get("raw"))
                    crashes.append(
                        {
                            "timestamp": payload.get("timestamp"),
                            "exception": _extract_exception(payload.get("raw", "")),
                            "raw": payload.get("raw"),
                            "archive": None,  # 后面填充
                        }
                    )
                    if with_collect_on_crash:
                        archive = collector.collect_full(
                            pkg=package,
                            scene=f"crash_{int(payload.get('timestamp', time.time()))}",
                            include_profile=False,
                            include_heap=True,
                            include_dumpsys=True,
                            include_logcat=True,
                        )
                        crashes[-1]["archive"] = str(archive)
                        crash_archive_paths.append(archive)

                elif event_type == "anr":
                    logger.warning("⚠️ ANR 事件: %s", payload.get("raw"))
                    anrs.append(
                        {
                            "timestamp": payload.get("timestamp"),
                            "type": "Input ANR",
                            "archive": None,
                            "raw": payload.get("raw"),
                        }
                    )
                    if with_collect_on_crash:
                        archive = collector.collect_anr_traces(
                            scene=f"anr_{int(payload.get('timestamp', time.time()))}"
                        )
                        anrs[-1]["archive"] = str(archive)

            elif source == "monkey" and isinstance(payload, str):
                # monkey 也会直接输出 crash 信息
                if "FATAL EXCEPTION" in payload or "crash" in payload.lower():
                    logger.warning("⚠️ Monkey 检测到 Crash: %s", payload[:200])
                if "ANR" in payload and "not responding" in payload:
                    logger.warning("⚠️ Monkey 检测到 ANR: %s", payload[:200])

        # 收尾
        t1.join(timeout=5)

    finally:
        logger.info("停止 monkey 和 monitor...")
        try:
            monkey_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            monkey_proc.kill()
        monitor_session.stop()

    # 4. 统计
    crash_rate = len(crashes) / max(iterations, 1) * 100
    anr_rate = len(anrs) / max(iterations, 1) * 100

    # 5. 生成报告
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    report_path = output_dir_path / "latest.md"
    StabilityReport(
        crashes=crashes,
        anrs=anrs,
        iterations=iterations,
        device_info=device.get_device_info(),
    ).render(report_path)
    logger.info("报告生成: %s", report_path)
    logger.info("=" * 60)
    logger.info("崩溃率: %.3f%% (%d 次)", crash_rate, len(crashes))
    logger.info("ANR 率: %.3f%% (%d 次)", anr_rate, len(anrs))
    logger.info("=" * 60)

    return {
        "crashes": crashes,
        "anrs": anrs,
        "crash_rate": crash_rate,
        "anr_rate": anr_rate,
        "iterations": iterations,
    }


def _extract_exception(raw: str) -> str:
    """从 crash 事件原始文本提取异常类名"""
    m = re.search(r"([\w.]+(?:Exception|Error))", raw)
    return m.group(1) if m else "Unknown"


def main():
    parser = argparse.ArgumentParser(description="进程稳定性巡检")
    parser.add_argument("--package", required=True, help="包名")
    parser.add_argument("--iterations", type=int, default=1000, help="monkey 事件数")
    parser.add_argument("--throttle-ms", type=int, default=100, help="monkey 事件间隔")
    parser.add_argument("--with-collect-on-crash", action="store_true",
                        help="每次 crash 自动三段式现场保留")
    parser.add_argument("--output-dir", default="./reports/stability", help="报告输出目录")
    parser.add_argument("--crash-threshold-pct", type=float, default=0.1, help="崩溃率阈值")
    parser.add_argument("--anr-threshold-pct", type=float, default=0.05, help="ANR 率阈值")
    parser.add_argument("--device-serial", default=None, help="指定设备 serial")

    args = parser.parse_args()

    device = Device(serial=args.device_serial) if args.device_serial else Device()

    try:
        result = check_process_stability(
            package=args.package,
            iterations=args.iterations,
            throttle_ms=args.throttle_ms,
            with_collect_on_crash=args.with_collect_on_crash,
            output_dir=args.output_dir,
            device=device,
        )
    except Exception as e:
        logger.error("巡检失败: %s", e)
        sys.exit(1)

    # 退出码:超阈值返回 1
    if result["crash_rate"] > args.crash_threshold_pct:
        logger.error("崩溃率 %.3f%% 超阈值 %.3f%%", result["crash_rate"], args.crash_threshold_pct)
        sys.exit(1)
    if result["anr_rate"] > args.anr_threshold_pct:
        logger.error("ANR 率 %.3f%% 超阈值 %.3f%%", result["anr_rate"], args.anr_threshold_pct)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()