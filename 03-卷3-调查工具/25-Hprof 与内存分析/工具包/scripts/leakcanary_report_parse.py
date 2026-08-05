#!/usr/bin/env python3
"""
LeakCanary 报告批量解析工具

解析 LeakCanary JSON 报告,提取关键字段,生成 CSV 汇总表
支持批量处理 + 统计 + 已知模式过滤

用法:
    # 批量解析报告目录
    python3 leakcanary_report_parse.py reports/

    # 指定输出文件
    python3 leakcanary_report_parse.py reports/ summary.csv

    # 单文件解析
    python3 leakcanary_report_parse.py report.json

依赖:
    Python 3.6+(无第三方依赖)

配套文档:Android_Framework_Layer/Hprof/05-实战：内存监控体系搭建.md §4.5
"""

import json
import sys
import csv
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict


# ====== 已知泄漏模式(可扩展) ======
KNOWN_PATTERNS = {
    "static_field": "静态字段持有对象",
    "handler_message": "Handler 消息未清空",
    "inner_class": "非静态内部类持有外部类",
    "webview": "WebView 持有 Activity",
    "third_party_sdk": "第三方 SDK 持有 Activity",
    "eventbus": "EventBus 未反注册",
    "register_receiver": "BroadcastReceiver 未反注册",
    "fragment_viewmodel": "Fragment ViewModel 持有 Context",
    "static_collection": "静态集合未清理",
    "thread_leak": "Thread 未关闭",
    "bitmap_cache": "Bitmap 缓存未清理",
    "cursor_not_closed": "Cursor 未关闭",
}


def classify_leak(reference_chain: List[str]) -> List[str]:
    """
    根据引用链分类泄漏模式
    
    Args:
        reference_chain: LeakCanary 报告中的引用链列表
    
    Returns:
        匹配到的模式列表
    """
    chain_text = " → ".join(reference_chain).lower()
    matched = []
    
    # 静态字段
    if "static field" in chain_text or "static " in chain_text:
        matched.append("static_field")
    
    # Handler 消息
    if "handler" in chain_text or "messagequeue" in chain_text or "runnable" in chain_text:
        matched.append("handler_message")
    
    # 内部类
    if "inner class" in chain_text or "$1" in chain_text or "$0" in chain_text:
        matched.append("inner_class")
    
    # WebView
    if "webview" in chain_text:
        matched.append("webview")
    
    # 第三方 SDK
    if "thirdparty" in chain_text or "third_party" in chain_text or "sdk" in chain_text.lower():
        matched.append("third_party_sdk")
    
    # EventBus
    if "eventbus" in chain_text:
        matched.append("eventbus")
    
    # BroadcastReceiver
    if "broadcastreceiver" in chain_text or "intentreceiver" in chain_text:
        matched.append("register_receiver")
    
    # Fragment + ViewModel
    if "viewmodel" in chain_text and "context" in chain_text:
        matched.append("fragment_viewmodel")
    
    # 静态集合
    if "hashmap" in chain_text or "lrucache" in chain_text or "arraylist" in chain_text:
        matched.append("static_collection")
    
    # Thread
    if "thread" in chain_text and "runnable" not in chain_text:
        matched.append("thread_leak")
    
    # Bitmap
    if "bitmap" in chain_text:
        matched.append("bitmap_cache")
    
    # Cursor
    if "cursor" in chain_text:
        matched.append("cursor_not_closed")
    
    return matched if matched else ["unknown"]


def parse_leak_report(report_path: Path) -> List[Dict]:
    """
    解析单个 LeakCanary 报告
    
    支持格式:
    - LeakCanary 2.x 导出的 JSON
    - 包含 leakAnalysis / leaks 字段
    """
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"⚠ JSON 解析失败 {report_path.name}: {e}", file=sys.stderr)
        return []
    
    # LeakCanary 2.x 报告格式
    leaks = data.get("leaks", [])
    if not leaks and "leakAnalysis" in data:
        leaks = data["leakAnalysis"].get("leaks", [])
    
    results = []
    for leak in leaks:
        retained_size = leak.get("retainedSize", 0) or leak.get("retainedHeapSize", 0)
        shallow_size = leak.get("shallowSize", 0) or leak.get("shallowHeapSize", 0)
        reference_chain = leak.get("referenceChain", [])
        
        # 分类
        patterns = classify_leak(reference_chain)
        
        result = {
            "report_file": report_path.name,
            "class_name": leak.get("className", "Unknown"),
            "retained_size_kb": retained_size / 1024,
            "shallow_size_kb": shallow_size / 1024,
            "leak_depth": len(reference_chain),
            "root_chain": " → ".join(reference_chain),
            "patterns": ", ".join(patterns),
            "is_real_leak": retained_size > 1_000_000,  # > 1MB 算真泄漏
            "is_known_pattern": "unknown" not in patterns,
        }
        results.append(result)
    
    return results


def batch_parse(report_dir: Path, output_csv: Path) -> Dict:
    """批量解析报告目录,返回统计信息"""
    
    if report_dir.is_file():
        # 单文件模式
        report_files = [report_dir]
    else:
        # 目录模式
        report_files = list(report_dir.glob("*.json")) + list(report_dir.glob("*.hprof.json"))
    
    if not report_files:
        print(f"⚠ 目录中未找到 .json 报告: {report_dir}", file=sys.stderr)
        return {}
    
    all_results = []
    parse_stats = {
        "total_files": len(report_files),
        "parsed_files": 0,
        "failed_files": 0,
        "total_leaks": 0,
        "real_leaks": 0,
        "known_pattern_leaks": 0,
        "total_retained_mb": 0.0,
        "patterns_distribution": defaultdict(int),
    }
    
    print(f"开始解析 {len(report_files)} 个报告文件...")
    print("-" * 60)
    
    for report_file in report_files:
        try:
            results = parse_leak_report(report_file)
            all_results.extend(results)
            parse_stats["parsed_files"] += 1
            print(f"✓ {report_file.name}: {len(results)} 个泄漏")
        except Exception as e:
            parse_stats["failed_files"] += 1
            print(f"✗ {report_file.name}: {e}", file=sys.stderr)
    
    if not all_results:
        print("\n⚠ 所有报告都解析失败", file=sys.stderr)
        return parse_stats
    
    # 统计
    parse_stats["total_leaks"] = len(all_results)
    parse_stats["real_leaks"] = sum(1 for r in all_results if r["is_real_leak"])
    parse_stats["known_pattern_leaks"] = sum(1 for r in all_results if r["is_known_pattern"])
    parse_stats["total_retained_mb"] = sum(r["retained_size_kb"] / 1024 for r in all_results)
    
    for r in all_results:
        for pattern in r["patterns"].split(", "):
            parse_stats["patterns_distribution"][pattern] += 1
    
    # 写 CSV
    if output_csv:
        with output_csv.open("w", newline="", encoding="utf-8") as f:
            if sys.version_info >= (3, 7):
                writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
            else:
                # Python 3.6 兼容
                from collections import OrderedDict
                writer = csv.DictWriter(f, fieldnames=list(all_results[0].keys()))
            writer.writeheader()
            writer.writerows(all_results)
        print(f"\n✓ CSV 输出: {output_csv}")
    
    return parse_stats


def print_summary(stats: Dict):
    """打印统计汇总"""
    print("\n" + "=" * 60)
    print("=== 汇总统计 ===")
    print("=" * 60)
    print(f"解析文件数:       {stats['parsed_files']} / {stats['total_files']}")
    print(f"解析失败:         {stats['failed_files']}")
    print(f"总泄漏数:         {stats['total_leaks']}")
    print(f"真泄漏(>1MB):    {stats['real_leaks']}")
    print(f"已知模式泄漏:     {stats['known_pattern_leaks']}")
    print(f"累计 retained:    {stats['total_retained_mb']:.1f} MB")
    
    print("\n=== 泄漏模式分布 ===")
    for pattern, count in sorted(stats["patterns_distribution"].items(), key=lambda x: -x[1]):
        pattern_desc = KNOWN_PATTERNS.get(pattern, pattern)
        print(f"  {count:4d}  {pattern} ({pattern_desc})")
    
    print("\n=== 建议 ===")
    if stats["real_leaks"] > 0:
        print(f"⚠ 检测到 {stats['real_leaks']} 个真泄漏,建议:")
        print("  1. 按 retained_size 降序排序,优先修大泄漏")
        print("  2. 已知模式泄漏可对照 04-内存泄漏典型案例与排查SOP.md")
        print("  3. 未知模式泄漏需要人工分析引用链")
    else:
        print("✓ 未检测到真泄漏(retained > 1MB)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_csv = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    
    if not input_path.exists():
        print(f"✗ 路径不存在: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    stats = batch_parse(input_path, output_csv)
    if stats:
        print_summary(stats)


if __name__ == "__main__":
    main()