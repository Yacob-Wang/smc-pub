# -*- coding: utf-8 -*-
"""
delete_e_grade.py - 批量删除 E 级低质/旧基线文件

策略：
- 阶段 1（--stage1）：删除 22 个极短文件（< 1000 字 / 旧 module 占位）
- 阶段 2（--stage2）：标记 1 个重写任务（OEM_Hook 演进，52K AOSP 12）→ 写入 _rewrite_todo.md
- 阶段 3（--stage3）：不删，只生成评估报告 _stage3_eval.md

默认 dry-run 模式：只打印要做什么
--apply：真正执行 git rm
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # smc-pub/
LIST = ROOT / "00-Meta" / "拟删除清单-v1.md"

# 阶段 1：22 个极短 / 立即删
STAGE1_DELETE = [
    "00-Meta/阅读指南.md",                # 308 B - 已迁移占位
    "00-Meta/JD匹配矩阵.md",              # 292 B - 已迁移占位
    "00-Meta/审计-待删清单-v1.md",        # 981 B - 过程产物
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/04_Partition_Size_Calculation.md",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/08_Vendor_Specific_Differences.md",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/07_Partition_Debugging_And_Troubleshooting.md",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/03_Image_Format_And_Tools.md",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/06_Partition_Flashing_And_Tools.md",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/05_AVB_And_Signing.md",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/02_Partition_Table_And_GPT.md",
    "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/04_Update_Verification_And_Rollback.md",
    "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/01_OTA_Update_Mechanism.md",
    "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/03_A_B_Partition_System.md",
    "01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/02_Updatable_Partitions.md",
    "06-Foundation/System-Integration/03_System_Initialization_Flow.md",
    "06-Foundation/System-Integration/02_Partition_Mount_And_Usage.md",
    "01-Mechanism/Kernel/Syscalls/10-系统调用安全机制.md",
    "01-Mechanism/Kernel/Syscalls/11-系统调用调试和追踪.md",
    "01-Mechanism/Kernel/Syscalls/12-系统调用实战案例分析.md",
    "01-Mechanism/Kernel/Syscalls/08-信号和同步类系统调用.md",
    "05-卷5-调查方法论与工具链/35-断点与 Native 调试/Git_Mastery_Guide.md",
    "05-卷5-调查方法论与工具链/35-断点与 Native 调试/抓trace.md",
]

# 阶段 2：1 个待重写（不删，标 todo）
STAGE2_REWRITE = [
    ("03-卷3-核心机制/14-线程与 Handler 消息机制/14-OEM_Hook演进-从运行时到编译期.md",
     "AOSP 12 旧基线，52K 字 - 重写到 AOSP 17 + 6.18 GKI"),
]

# 阶段 3：21 个评估（不删，输出报告）
STAGE3_EVAL = [
    "03-卷3-核心机制/19-电源与续航/readme.md",
    "03-卷3-核心机制/19-电源与续航/traceflag.md",
    "03-卷3-核心机制/19-电源与续航/中断理解1.md",
    "03-卷3-核心机制/19-电源与续航/深度解密：中断的“上半部”与“下半部” (Hard IRQ vs SoftIRQ).md",
    "03-卷3-核心机制/19-电源与续航/Linux 内核中断机制深度剖析：从上下文借用到 DoS 防御.md",
    "04-卷4-稳定性症状诊断/25-系统无响应（SWT · Watchdog）/elapsedRealtime&uptimeMillis区别.md",
    "01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/01_Dynamic_Partitions_Deep_Dive.md",
    "01-Mechanism/Kernel/Syscalls/09-系统调用性能优化.md",
    "05-卷5-调查方法论与工具链/35-断点与 Native 调试/ftrace-QA.md",
    "05-卷5-调查方法论与工具链/35-断点与 Native 调试/Git_Aliases_Reference.md",
    "00-Meta/Reference/Forensics-案例索引.md",
    "05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/am_start_params.md",
    "01-Mechanism/Kernel/GKI/02-Generic-Kernel详解.md",
    "01-Mechanism/Kernel/Syscalls/06-内存管理类系统调用.md",
    "01-Mechanism/Kernel/GKI/08-GKI中的内存管理特殊性.md",
    "01-Mechanism/Kernel/GKI/09-GKI升级与兼容性.md",
    "01-Mechanism/Kernel/GKI/05-KMI-Kernel-Module-Interface详解.md",
    "01-Mechanism/Kernel/GKI/10-GKI实战案例分析.md",
    "01-Mechanism/Kernel/GKI/GKI2.0_vs_Non_GKI_Complete_Guide.md",
    # 已于 2026-08-04 删除：02-卷2-系统启动/10-应用启动与首帧/Old/（含 02-架构演进）
    "01-Mechanism/Kernel/GKI/ACK_Build_And_Flash_Complete_Guide.md",
]


def verify_existence(files):
    """核对文件实际存在情况"""
    existed, missing = [], []
    for p in files:
        full = ROOT / p
        if full.exists():
            existed.append((p, full.stat().st_size))
        else:
            missing.append(p)
    return existed, missing


def stage1_dryrun():
    print("=" * 70)
    print("【阶段 1 - 立即删】 dry-run")
    print("=" * 70)
    existed, missing = verify_existence(STAGE1_DELETE)
    print(f"将删除 {len(existed)} 个文件（缺失 {len(missing)} 个）:")
    total_size = 0
    for p, s in existed:
        total_size += s
        print(f"  [{s:>5} B] {p}")
    print(f"总字节数: {total_size} B")
    if missing:
        print(f"\n⚠️  以下文件实际不存在（跳过）:")
        for p in missing:
            print(f"  - {p}")


def stage2_dryrun():
    print()
    print("=" * 70)
    print("【阶段 2 - 重写 todo】 dry-run")
    print("=" * 70)
    print(f"将标记 {len(STAGE2_REWRITE)} 个重写任务（不删，保留原文件）:")
    for p, note in STAGE2_REWRITE:
        full = ROOT / p
        if full.exists():
            size = full.stat().st_size
            print(f"  [{size:>6} B] {p}")
            print(f"           → {note}")
        else:
            print(f"  [不存在] {p}")


def stage3_dryrun():
    print()
    print("=" * 70)
    print("【阶段 3 - 评估】 dry-run（不删，输出报告）")
    print("=" * 70)
    existed, missing = verify_existence(STAGE3_EVAL)
    print(f"将评估 {len(existed)} 个文件（缺失 {len(missing)} 个）:")
    for p, s in existed:
        print(f"  [{s:>5} B] {p}")


def stage1_apply():
    print("=" * 70)
    print("【阶段 1 - 立即删】 APPLY")
    print("=" * 70)
    existed, missing = verify_existence(STAGE1_DELETE)
    if missing:
        print(f"⚠️  以下文件实际不存在（已跳过）:")
        for p in missing:
            print(f"  - {p}")
    print(f"\n即将 git rm 以下 {len(existed)} 个文件:\n")
    for p, s in existed:
        print(f"  {p}")
    # 用相对路径传给 git
    cmd = ["git", "rm"] + [p for p, _ in existed]
    print(f"\n执行: git rm ({len(existed)} 个文件)")
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="ignore")
    print("STDOUT:", result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        return 1
    print(f"\n✅ 成功删除 {len(existed)} 个文件（git rm）")
    return 0


def stage2_apply():
    print()
    print("=" * 70)
    print("【阶段 2 - 重写 todo】 APPLY（追加到 00-Meta/_rewrite_todo.md）")
    print("=" * 70)
    todo_path = ROOT / "00-Meta" / "_rewrite_todo.md"
    with open(todo_path, "a", encoding="utf-8") as f:
        f.write(f"\n## 自动生成于 {os.popen('date /I').read().strip()}\n\n")
        for p, note in STAGE2_REWRITE:
            f.write(f"- [ ] `{p}`\n  - 备注: {note}\n")
    print(f"✅ 追加 {len(STAGE2_REWRITE)} 条到 {todo_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    do_s1 = "--stage1" in sys.argv or not any(s in sys.argv for s in ["--stage2", "--stage3"])
    do_s2 = "--stage2" in sys.argv
    do_s3 = "--stage3" in sys.argv or not any(s in sys.argv for s in ["--stage1", "--stage2"])

    if do_s1:
        if apply:
            stage1_apply()
        else:
            stage1_dryrun()
    if do_s2:
        if apply:
            stage2_apply()
        else:
            stage2_dryrun()
    if do_s3:
        if not apply:
            stage3_dryrun()
        else:
            pass  # stage3 不动
    if not apply:
        print()
        print("=" * 70)
        print("当前为 dry-run 模式，加 --apply 参数真正执行（git rm / 追加 todo）")
        print("=" * 70)
