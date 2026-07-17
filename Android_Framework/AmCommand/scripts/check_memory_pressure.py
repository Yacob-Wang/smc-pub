"""
check_memory_pressure.py - 内存压力巡检脚本

典型用法:
    python check_memory_pressure.py \\
        --package com.example.app \\
        --duration-sec 600 \\
        --dump-interval-sec 120 \\
        --output-dir ./reports/memory_pressure

详见 06 篇 §4。
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
from amlib.report import MemoryReport  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_dumpsys_meminfo(output: str) -> dict:
    """
    解析 dumpsys meminfo 输出,提取关键指标。

    输出样例:
      Total PSS by OOM adjustment:
        482,344K: com.example.app (pid 12345)
      ...
      Objects
        Views: 0         ViewRootImpl: 1
        AppContexts: 4    Activities: 2
    """
    result = {}

    # 找 Total PSS
    m = re.search(r"(\d+(?:,\d+)*)K:\s+com\.example\.app", output)  # 注:实际应该动态拿包名
    # 简化:用 dumpsys meminfo <pkg> 的格式
    m = re.search(r"TOTAL PSS:\s+(\d+)", output)
    if m:
        result["total_pss_kb"] = int(m.group(1))

    m = re.search(r"Java Heap:\s+(\d+)", output)
    if m:
        result["java_heap_kb"] = int(m.group(1))

    m = re.search(r"Native Heap:\s+(\d+)", output)
    if m:
        result["native_heap_kb"] = int(m.group(1))

    m = re.search(r"Graphics:\s+(\d+)", output)
    if m:
        result["graphics_kb"] = int(m.group(1))

    m = re.search(r"Bitmap:\s+(\d+)", output)
    if m:
        result["bitmap_kb"] = int(m.group(1))

    return result


def parse_hprof_top_objects(heap_path: Path) -> list:
    """
    解析 hprof 文件,提取 Top 10 类对象(用 hprof-conv + 自定义解析)。

    这里简化:用 `hprof-conv` 转 + jhat-like 解析。
    实际项目可集成 MAT 的脚本化 API。
    """
    # 简化版本:返回空列表,真实场景可接入 hprof-parser 等工具
    # 推荐用 https://github.com/irockel/hprof-slurp 或类似工具
    return []


def check_memory_pressure(
    package: str,
    duration_sec: int = 600,
    dump_interval_sec: int = 120,
    monkey_events: int = 500,
    output_dir: str = "./reports/memory_pressure",
    device: Device = None,
) -> list:
    """
    压测期间定时 dump heap,产出内存趋势报告。

    Args:
        package: 包名
        duration_sec: 压测总时长
        dump_interval_sec: dump 间隔
        monkey_events: 后台 monkey 触发事件数
        output_dir: 报告输出目录
        device: 注入的设备

    Returns:
        snapshots 列表
    """
    device = device or Device()
    am = AM(device)
    collector = ArtifactCollector(device, output_dir=output_dir)

    # 1. 启动 app
    logger.info("启动 %s...", package)
    am.start(f"{package}/.MainActivity")
    time.sleep(5)

    pid = am.get_pid(package)
    logger.info("PID = %d", pid)

    # 2. 启动后台 monkey 压测
    logger.info("启动后台 monkey 压测 (%d 事件)...", monkey_events)
    monkey_cmd = [
        "adb", "-s", device.serial, "shell",
        "monkey", "-p", package,
        "--pct-touch", "50",
        "--pct-syskeys", "0",
        "--throttle", "200",
        "-v", str(monkey_events),
    ]
    monkey_proc = subprocess.Popen(monkey_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    snapshots = []
    try:
        for i in range(0, duration_sec, dump_interval_sec):
            elapsed = i
            logger.info("=" * 60)
            logger.info("时间: %d/%d 秒", elapsed, duration_sec)
            logger.info("=" * 60)

            # 2.1 dumpsys meminfo
            meminfo_output = device.shell(f"dumpsys meminfo {package}", timeout=30)
            meminfo = parse_dumpsys_meminfo(meminfo_output)

            snapshot = {
                "time_sec": elapsed,
                "total_mb": meminfo.get("total_pss_kb", 0) // 1024,
                "java_mb": meminfo.get("java_heap_kb", 0) // 1024,
                "native_mb": meminfo.get("native_heap_kb", 0) // 1024,
                "bitmap_mb": meminfo.get("bitmap_kb", 0) // 1024,
                "graphics_mb": meminfo.get("graphics_kb", 0) // 1024,
                "top_objects": [],
            }

            # 2.2 dump heap(归档)
            try:
                heap_path = collector.collect_heap(pid, scene=f"memory_t{elapsed}")
                snapshot["top_objects"] = parse_hprof_top_objects(heap_path)
                snapshot["heap_path"] = str(heap_path)
                logger.info("  heap 归档: %s", heap_path)
            except Exception as e:
                logger.warning("  heap dump 失败: %s", e)

            snapshots.append(snapshot)
            logger.info(
                "  内存: 总 %dMB / Java %dMB / Native %dMB",
                snapshot["total_mb"],
                snapshot["java_mb"],
                snapshot["native_mb"],
            )

            # 等下一次 dump
            if i + dump_interval_sec < duration_sec:
                time.sleep(dump_interval_sec)

    finally:
        # 3. 停 monkey
        logger.info("停止 monkey...")
        monkey_proc.terminate()
        try:
            monkey_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            monkey_proc.kill()

    # 4. 生成报告
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    report_path = output_dir_path / "latest.md"
    MemoryReport(snapshots, device.get_device_info()).render(report_path)
    logger.info("报告生成: %s", report_path)

    return snapshots


def main():
    parser = argparse.ArgumentParser(description="内存压力巡检")
    parser.add_argument("--package", required=True, help="包名")
    parser.add_argument("--duration-sec", type=int, default=600, help="压测总时长(秒)")
    parser.add_argument("--dump-interval-sec", type=int, default=120, help="dump 间隔(秒)")
    parser.add_argument("--monkey-events", type=int, default=500, help="后台 monkey 事件数")
    parser.add_argument("--output-dir", default="./reports/memory_pressure", help="报告输出目录")
    parser.add_argument("--device-serial", default=None, help="指定设备 serial")

    args = parser.parse_args()

    device = Device(serial=args.device_serial) if args.device_serial else Device()

    try:
        snapshots = check_memory_pressure(
            package=args.package,
            duration_sec=args.duration_sec,
            dump_interval_sec=args.dump_interval_sec,
            monkey_events=args.monkey_events,
            output_dir=args.output_dir,
            device=device,
        )
    except Exception as e:
        logger.error("巡检失败: %s", e)
        sys.exit(1)

    # 退出码:Java 堆增长 > 50% 返回 1
    if len(snapshots) >= 2:
        first_java = snapshots[0].get("java_mb", 0)
        last_java = snapshots[-1].get("java_mb", 0)
        if first_java > 0 and (last_java - first_java) / first_java > 0.5:
            logger.error("Java 堆增长超 50%,疑似内存泄漏")
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()