"""卷 4-8 迁移脚本：基于 _ch_22_50_files.json 把 02-Symptom / 03-Forensics / 04-Tool / 05-Governance / 06-Case / 06-Foundation 全部迁到 04-卷4-08-卷8 各章。
"""
import json
import subprocess
import os
from pathlib import Path

REPO = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")

# 章号 -> 目标目录
CH_DIR = {
    # 卷 4 稳定性症状诊断
    22: "04-卷4-稳定性症状诊断/22-ANR 深度",
    23: "04-卷4-稳定性症状诊断/23-Java 异常",
    24: "04-卷4-稳定性症状诊断/24-Native 异常",
    25: "04-卷4-稳定性症状诊断/25-系统无响应（SWT · Watchdog）",
    26: "04-卷4-稳定性症状诊断/26-HANG 与死锁",
    27: "04-卷4-稳定性症状诊断/27-REBOOT",
    28: "04-卷4-稳定性症状诊断/28-Kernel Exception",
    29: "04-卷4-稳定性症状诊断/29-性能退化与稳定性边界",
    # 卷 5 调查方法论与工具链
    30: "05-卷5-调查方法论与工具链/30-稳定性调查方法论",
    31: "05-卷5-调查方法论与工具链/31-Perfetto 全栈使用",
    32: "05-卷5-调查方法论与工具链/32-Systrace 与 ftrace",
    33: "05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox",
    34: "05-卷5-调查方法论与工具链/34-Hprof 与内存分析",
    35: "05-卷5-调查方法论与工具链/35-断点与 Native 调试",
    36: "05-卷5-调查方法论与工具链/36-Oncall 与应急响应",
    # 卷 6 性能工程
    37: "06-卷6-性能工程/37-性能基线与回归测试",
    38: "06-卷6-性能工程/38-启动性能",
    39: "06-卷6-性能工程/39-滑动与渲染性能",
    40: "06-卷6-性能工程/40-低配机适配",
    41: "06-卷6-性能工程/41-WebView 与 Hybrid 性能",
    # 卷 7 APM 与工程治理
    42: "07-卷7-APM与工程治理/42-稳定性指标体系（SLI · SLO）",
    43: "07-卷7-APM与工程治理/43-APM 架构与自研实践",
    44: "07-卷7-APM与工程治理/44-告警体系与降噪",
    45: "07-卷7-APM与工程治理/45-变更管理与灰度发布",
    46: "07-卷7-APM与工程治理/46-AI-Native 调试",
    # 卷 8 案例实战
    47: "08-卷8-案例实战/47-冷启动优化案例",
    48: "08-卷8-案例实战/48-ANR 调查案例",
    49: "08-卷8-案例实战/49-Native Crash 调查案例",
    50: "08-卷8-案例实战/50-性能优化案例",
}


def main():
    # 读 JSON
    json_p = REPO / "00-Meta" / "scripts" / "_ch_22_50_files.json"
    data = json.loads(json_p.read_text(encoding="utf-8"))
    print(f"[LOADED] {len(data)} chapters from {json_p.name}")
    print()

    # 1. 校验源文件都存在
    missing = []
    file_to_ch = {}  # src_rel -> ch
    for ch_str, info in data.items():
        ch = int(ch_str)
        for f in info["files"]:
            # 提取纯相对路径
            # files 里可能是 "(1234 字符)" 括号注释，要去掉
            src = f.strip()
            # 移除 (xxx 字符) 注释
            if " (" in src and src.endswith(")"):
                src = src.rsplit(" (", 1)[0]
            p = REPO / src
            if not p.exists():
                missing.append((src, ch))
            file_to_ch[src] = ch
    if missing:
        print(f"[WARN] {len(missing)} source files missing (will skip):")
        for src, ch in missing[:20]:
            print(f"  ch{ch}: {src}")
        if len(missing) > 20:
            print(f"  ... +{len(missing)-20} more")
        # 过滤掉 missing 后的 files
        new_data = {}
        for ch_str, info in data.items():
            ch = int(ch_str)
            valid_files = []
            for f in info["files"]:
                src = f.strip()
                if " (" in src and src.endswith(")"):
                    src = src.rsplit(" (", 1)[0]
                if (REPO / src).exists():
                    valid_files.append(f)
            new_data[ch_str] = {"title": info["title"], "files": valid_files}
        data = new_data
        print(f"[FILTERED] {sum(len(v['files']) for v in data.values())} files to migrate")

    total_files = sum(len(info["files"]) for info in data.values())
    print(f"[OK] All {total_files} source files exist")
    print()

    # 2. 创建目标目录（防御性）
    for ch, dest in CH_DIR.items():
        (REPO / dest).mkdir(parents=True, exist_ok=True)

    # 3. git mv
    total_mv = 0
    skip_count = 0
    by_ch = {}
    for ch_str, info in data.items():
        ch = int(ch_str)
        dest = CH_DIR.get(ch)
        if not dest:
            print(f"  [SKIP-CHAPTER] 第 {ch} 章 no dest dir, skip {len(info['files'])} files")
            continue
        for f in info["files"]:
            src = f.strip()
            if " (" in src and src.endswith(")"):
                src = src.rsplit(" (", 1)[0]
            src_p = REPO / src
            dst_p = REPO / dest / Path(src).name
            if dst_p.exists():
                skip_count += 1
                continue
            rel_src = src.replace("/", os.sep)
            rel_dst = (dest + "/" + Path(src).name).replace("/", os.sep)
            result = subprocess.run(
                ["git", "mv", rel_src, rel_dst],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if result.returncode == 0:
                total_mv += 1
                by_ch[ch] = by_ch.get(ch, 0) + 1
            else:
                print(f"  [ERR] {src} -> {rel_dst}: {result.stderr.strip()}")

    print()
    print(f"[OK] git mv {total_mv} files (skipped {skip_count} already-exists)")

    # 4. 报告
    print()
    print("[SUMMARY]")
    for ch in sorted(by_ch.keys()):
        dest = CH_DIR.get(ch, "?")
        print(f"  第 {ch} 章 -> {dest}: {by_ch[ch]} files")


if __name__ == "__main__":
    main()
