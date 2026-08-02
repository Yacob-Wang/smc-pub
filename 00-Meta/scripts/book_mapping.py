"""
book_mapping.py - 现有 652 篇 md -> 50 章映射表生成
输出：00-Meta/章节-素材映射表-v1.md
"""
import re
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")
OUTPUT_MD = REPO_ROOT / "00-Meta" / "章节-素材映射表-v1.md"

EXCLUDE_PARTS = {"00-Meta/overrides", "00-Meta/reader", "00-Meta/web", "docs", "site", ".git", "_archive"}

# 8 卷 50 章标题
VOLUMES = [
    ("卷1", "Android 系统基础与平台", "01-卷1-Android系统基础与平台", 5, [
        (1, "Android 系统全景与 AOSP 17"),
        (2, "AOSP 源码结构与构建系统"),
        (3, "硬件抽象层（HAL）与 Treble 架构"),
        (4, "Linux Kernel 基础（Android 视角）"),
        (5, "安全基础（SELinux / AVB）"),
    ]),
    ("卷2", "系统启动", "02-卷2-系统启动", 6, [
        (6, "Bootloader 到 Kernel"),
        (7, "Init 进程与 init.rc"),
        (8, "Zygote 与 ART 启动"),
        (9, "SystemServer 启动"),
        (10, "应用启动与首帧"),
        (11, "启动性能专项"),
    ]),
    ("卷3", "核心机制（横跨 AOSP 分层）", "03-卷3-核心机制", 10, [
        (12, "Binder IPC 深度"),
        (13, "进程与生命周期"),
        (14, "线程与 Handler 消息机制"),
        (15, "内存管理全链路"),
        (16, "IO 与存储"),
        (17, "网络与连接"),
        (18, "显示与渲染"),
        (19, "电源与续航"),
        (20, "ART 运行时"),
        (21, "输入系统"),
    ]),
    ("卷4", "稳定性症状诊断", "04-卷4-稳定性症状诊断", 8, [
        (22, "ANR 深度"),
        (23, "Java 异常"),
        (24, "Native 异常"),
        (25, "系统无响应（SWT / Watchdog）"),
        (26, "HANG 与死锁"),
        (27, "REBOOT"),
        (28, "Kernel Exception"),
        (29, "性能退化与稳定性边界"),
    ]),
    ("卷5", "调查方法论与工具链", "05-卷5-调查方法论与工具链", 7, [
        (30, "稳定性调查方法论"),
        (31, "Perfetto 全栈使用"),
        (32, "Systrace 与 ftrace"),
        (33, "Dumpsys / Bugreport / DropBox"),
        (34, "Hprof 与内存分析"),
        (35, "断点与 Native 调试"),
        (36, "Oncall 与应急响应"),
    ]),
    ("卷6", "性能工程", "06-卷6-性能工程", 5, [
        (37, "性能基线与回归测试"),
        (38, "启动性能"),
        (39, "滑动与渲染性能"),
        (40, "低配机适配"),
        (41, "WebView 与 Hybrid 性能"),
    ]),
    ("卷7", "APM 与工程治理", "07-卷7-APM与工程治理", 5, [
        (42, "稳定性指标体系（SLI / SLO）"),
        (43, "APM 架构与自研实践"),
        (44, "告警体系与降噪"),
        (45, "变更管理与灰度发布"),
        (46, "AI-Native 调试"),
    ]),
    ("卷8", "案例实战", "08-卷8-案例实战", 4, [
        (47, "冷启动优化案例"),
        (48, "ANR 调查案例"),
        (49, "Native Crash 调查案例"),
        (50, "性能优化案例"),
    ]),
]

# 路径规则 -> 章号（按优先级匹配，从上到下）
# 关键：子主题规则优先于通配规则
PATH_RULES = [
    # --- 卷 2 启动：S11-Startup 单独识别 ---
    ("02-Symptom/S11-Startup/A-启动机制/A0", 10),  # A01-A06 -> 应用启动
    ("02-Symptom/S11-Startup/A-启动机制/B", 11),  # B01-B04 -> 启动性能
    ("02-Symptom/S11-Startup/A-启动机制/C", 11),  # C01-C05 -> 启动性能
    ("02-Symptom/S11-Startup/A-启动机制/D", 11),  # D01-D04 -> 启动性能
    ("02-Symptom/S11-Startup/Old/", 10),  # Old 归档归到应用启动
    ("A-启动机制", 10),

    # --- 卷 3 核心机制：Kernel 子主题优先 ---
    ("Kernel/Binder", 12),
    ("Kernel/Memory_Management", 15),
    ("Kernel/Process", 13),
    ("Kernel/Process_Exit", 13),
    ("Kernel/FileSystem", 16),
    ("Kernel/IO", 16),
    ("Kernel/socket", 17),
    ("Kernel/Input_Driver", 21),
    ("Kernel/Input/", 21),
    ("Kernel/Program_Execution", 11),  # 程序执行 → 启动
    ("Kernel/Partition", 2),  # 分区 → 构建
    ("Kernel/Interrupt", 19),  # 中断 → 电源
    ("Kernel/Syscalls", 4),
    ("Kernel/cgroup", 4),
    ("Kernel/GKI", 4),
    ("Kernel/DM", 4),
    ("Kernel/epoll", 4),
    ("Kernel/Cgroup", 4),

    # --- Kernel 通用（兜底）---
    ("Kernel/", 4),

    # --- 卷 3 Framework 子主题 ---
    ("Framework/Activity", 13),
    ("Framework/Broadcast", 13),
    ("Framework/ContentProvider", 13),
    ("Framework/Input", 21),
    ("Framework/Memory_Management", 15),
    ("Framework/Process", 13),
    ("Framework/Process_Exit", 13),
    ("Framework/Service", 13),
    ("Framework/Signing", 5),
    ("Framework/Window", 18),
    ("Framework/", 13),  # Framework 通用兜底

    # --- 卷 3 Runtime ---
    ("Runtime/ART", 20),
    ("Runtime/Native_Crash", 24),
    ("Runtime/", 20),

    # --- 卷 3 App ---
    ("App/Handler", 14),
    ("App/Hook", 14),
    ("App/", 14),

    # --- 卷 4 症状：S01-S10 ---
    ("S01-ANR", 22),
    ("S02-JE", 23),
    ("S03-NE", 24),
    ("S04-SWT", 25),
    ("S05-HANG", 26),
    ("S06-REBOOT", 27),
    ("S07-KE", 28),
    ("S08-AOSP17", 1),
    ("S09-PerfVsStab", 29),
    ("S10-Measure", 37),

    # --- 卷 5 取证 ---
    ("F00-Overview", 30),
    ("F01-ANR", 22),
    ("F02-SWT", 25),
    ("F03-JE", 23),
    ("F04-NE", 24),
    ("F05-KE", 28),
    ("F06-HANG", 26),
    ("F07-Governance", 30),
    ("Oncall", 36),
    ("Bugreport", 33),

    # --- 卷 5 工具 ---
    ("Dumpsys", 33),
    ("AmCommand", 33),
    ("Watchdog", 25),
    ("Perfetto", 31),
    ("Hprof", 34),
    ("ANR-Detection", 22),

    # --- 卷 7 治理 ---
    ("AI-Native", 46),
    ("APM", 43),
    ("AI-Debug", 46),
    ("CrossPlatform", 3),  # 跨平台 → HAL/Treble
    ("LowEnd", 40),  # 低配机
    ("OEM-BSP", 3),  # OEM-BSP → HAL
    ("PerfMem", 15),  # 性能内存 → 内存
    ("Security", 5),  # Security → 安全基础

    # --- 卷 8 案例 ---
    ("06-Case/Startup", 47),
    ("Cases-Extended", 50),  # 性能优化案例

    # --- 卷 1/2 基础 ---
    ("Build-System", 2),
    ("Dynamic-Updates", 5),
    ("SELinux", 5),
    ("System-Integration", 11),  # 系统集成 → 启动
    ("06-Foundation/Tools", 35),  # 工具 → 断点
    ("06-Foundation/Power", 19),
    ("06-Foundation/Network", 17),
    ("06-Foundation/Graphics", 18),
]


def match_chapter(rel: str) -> tuple[int, str] | tuple[None, None]:
    """根据相对路径匹配章号。"""
    for pattern, ch in PATH_RULES:
        if pattern in rel:
            return ch, ""
    return None, None


def main():
    # 扫所有 md（排除 00-Meta/overrides 等）
    all_md: list[Path] = []
    for p in REPO_ROOT.rglob("*.md"):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if any(rel.startswith(d) for d in EXCLUDE_PARTS):
            continue
        if "00-Meta/scripts/" in rel:
            continue
        all_md.append(p)

    # 初始化 50 个章 bucket
    buckets: dict[int, list[tuple[str, int]]] = {i: [] for i in range(1, 51)}
    unmatched: list[tuple[str, int]] = []

    for p in all_md:
        rel = p.relative_to(REPO_ROOT).as_posix()
        size = p.stat().st_size
        ch, _ = match_chapter(rel)
        if ch is None:
            unmatched.append((rel, size))
        else:
            buckets[ch].append((rel, size))

    # 输出 markdown
    lines: list[str] = []
    lines.append("# 现有 652 篇 md → 8 卷 50 章 映射表 v1\n\n")
    lines.append(f"**生成时间**：{Path(__file__).stat().st_mtime}  \n")
    lines.append(f"**总文件数**：{len(all_md)} 篇（审计后）\n\n")
    lines.append("---\n\n")
    lines.append("## 映射统计\n\n")
    lines.append("| 章号 | 章标题 | 篇数 |\n|---|---|---|\n")
    for vol_tag, vol_name, _, _, chs in VOLUMES:
        for ch_num, ch_title in chs:
            count = len(buckets[ch_num])
            lines.append(f"| {ch_num} | {ch_title} | {count} |\n")
    lines.append("\n")

    total_mapped = sum(len(v) for v in buckets.values())
    lines.append(f"**已映射**：{total_mapped} 篇  \n")
    lines.append(f"**未匹配**：{len(unmatched)} 篇  \n\n")

    if unmatched:
        lines.append("## 未匹配的 md（需要人工归类）\n\n")
        for rel, size in sorted(unmatched):
            lines.append(f"- `{rel}` ({size} 字符)\n")
        lines.append("\n")

    # 详细列表
    lines.append("---\n\n")
    lines.append("## 详细映射（每章现有素材）\n\n")
    for vol_tag, vol_name, _, _, chs in VOLUMES:
        lines.append(f"### {vol_tag}　{vol_name}\n\n")
        for ch_num, ch_title in chs:
            lines.append(f"#### 第 {ch_num} 章　{ch_title} ({len(buckets[ch_num])} 篇)\n\n")
            if not buckets[ch_num]:
                lines.append("*(空 — 需要补写)*\n\n")
                continue
            for rel, size in sorted(buckets[ch_num]):
                lines.append(f"- `{rel}` ({size} 字符)\n")
            lines.append("\n")

    OUTPUT_MD.write_text("".join(lines), encoding="utf-8")
    print(f"[OK] mapping table written: {OUTPUT_MD}")
    print(f"    total files: {len(all_md)}")
    print(f"    mapped: {total_mapped}")
    print(f"    unmatched: {len(unmatched)}")
    if unmatched:
        print(f"    unmatched files (first 10):")
        for r, _ in unmatched[:10]:
            print(f"      - {r}")


if __name__ == "__main__":
    main()
