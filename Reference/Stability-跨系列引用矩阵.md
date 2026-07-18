# Stability 系列 → 跨系列引用矩阵

> **目的**：避免 Stability 系列与现有 10+ 系列的重复造内容，明确"哪些内容 Stability 不重复讲，直接引用"。
>
> **使用规则**：
> - Stability 系列每篇文章的"本篇定位"段必须显式声明"不重复内容"边界
> - 涉及已有系列覆盖的内容时，**用 Markdown 链接引用**，不重复展开
> - 每月核查一次链接有效性（v4 §8 强制）

---

## 1. 引用关系总图

```
Stability 系列（症状维度）= 横向问题分类
  ↓ 引用
现有系列（子系统维度）= 纵向机制深挖

现有 8 大相关系列：
  1. [Watchdog](../../Android_Framework/Watchdog/)          ← S04 SWT
  2. [ANR_Detection](../../Android_Framework/ANR_Detection/) ← S01 ANR
  3. [Native_Crash](../../Runtime/Native_Crash/)             ← S03 NE
  4. [Process](../../Android_Framework/Process/)            ← S06 REBOOT
  5. [ART 06 信号与ANR-Trace](../../Runtime/ART/06-信号与ANR-Trace/) ← S02 JE
  6. [Hprof](../../Android_Framework/Hprof/)                 ← S02 JE
  7. [Handler/Looper](../../App/Handler_MessageQueue_Looper/) ← S01 ANR / S05 HANG
  8. [Linux_Kernel/Process](../../Linux_Kernel/Process/)    ← S07 KE / S05 HANG
  9. [Linux_Kernel/Binder](../../Linux_Kernel/Binder/)      ← S05 HANG
  10. [Linux_Kernel/MM_v2](../../Linux_Kernel/Memory_Management/MM_v2/) ← S03 NE
```

---

## 2. 详细引用矩阵

| Stability 文章 | 引用章节 | 引用系列 | 引用文章 | 引用原因 | 链接有效性最后核查 |
|--------------|---------|---------|---------|---------|------------------|
| **S00 总览** | §2 七大症状边界 | [Watchdog](../../Android_Framework/Watchdog/) | 01-05 全部 | SWT 机制细节 | 2026-07-18 |
| S00 | §2 | [ANR_Detection](../../Android_Framework/ANR_Detection/) | Input_Dispatch_Timeout_ANR_Deep_Dive | ANR 检测链路 | 2026-07-18 |
| S00 | §2 | [Native_Crash](../../Runtime/Native_Crash/) | 01-NativeCrash总览 | NE 整体机制 | 2026-07-18 |
| S00 | §2 | [Process](../../Android_Framework/Process/) | 08-进程稳定性风险全景 | 进程治理 | 2026-07-18 |
| **S01 ANR** | §3.1 Input ANR | [ANR_Detection](../../Android_Framework/ANR_Detection/) | Input_Dispatch_Timeout_ANR_Deep_Dive | Input ANR 检测机制 | 2026-07-18 |
| S01 | §3 全部 | [Handler/Looper](../../App/Handler_MessageQueue_Looper/) | README + 各篇 | 主线程 Looper 机制 | 2026-07-18 |
| S01 | §3.1 | [Linux_Kernel/Input_Driver](../../Linux_Kernel/Input_Driver/) | README + 各篇 | Input 内核路径 | 2026-07-18 |
| S01 | §3.1 | [ART 06](../../Runtime/ART/06-信号与ANR-Trace/) | 全部 | ART 信号机制 | 2026-07-18 |
| **S02 JE** | §3.1 ART 异常分发 | [ART 06](../../Runtime/ART/06-信号与ANR-Trace/) | 全部 | ART 异常处理 | 2026-07-18 |
| S02 | §3.3 dropbox | [ANR_Detection](../../Android_Framework/ANR_Detection/) | BinderStarve | dropbox 机制 | 2026-07-18 |
| S02 | §4 内存相关 JE | [Hprof](../../Android_Framework/Hprof/) | 全部 | 内存异常诊断 | 2026-07-18 |
| **S03 NE** | §3 全部 | [Native_Crash](../../Runtime/Native_Crash/) | 8 篇全部 | NE 机制全栈 | 2026-07-18 |
| S03 | §3.6 SIGSYS | [Linux_Kernel/Process](../../Linux_Kernel/Process/) | README | seccomp 机制 | 2026-07-18 |
| S03 | §3.9 Rust Binder | [Linux_Kernel/Binder](../../Linux_Kernel/Binder/) | 全部 | Binder Rust 改造 | 2026-07-18 |
| S03 | §5 治理 | [Linux_Kernel/MM_v2](../../Linux_Kernel/Memory_Management/MM_v2/) | 12-内存稳定性风险全景 | 内存崩溃诊断 | 2026-07-18 |
| **S04 SWT** | §3 全部 | [Watchdog](../../Android_Framework/Watchdog/) | 6 篇全部 | Watchdog 内部状态机 | 2026-07-18 |
| S04 | §3.5 喂狗 | [ART 06](../../Runtime/ART/06-信号与ANR-Trace/) | 全部 | 喂狗机制 | 2026-07-18 |
| **S05 HANG** | §3.3 Binder HANG | [Linux_Kernel/Binder](../../Linux_Kernel/Binder/) | 全部 | Binder 内核路径 | 2026-07-18 |
| S05 | §3.4 Kernel HANG | [Linux_Kernel/Process](../../Linux_Kernel/Process/) | 全部 | hung_task / RCU stall | 2026-07-18 |
| S05 | §3.1 主线程软卡 | [Handler/Looper](../../App/Handler_MessageQueue_Looper/) | 全部 | 主线程机制 | 2026-07-18 |
| S05 | §3.2 IO HANG | [Linux_Kernel/IO](../../Linux_Kernel/IO/) | 全部 | IO 调度机制 | 2026-07-18 |
| **S06 REBOOT** | §3.2 SystemServer 重启 | [Watchdog](../../Android_Framework/Watchdog/) | 05-Watchdog超时判定与杀进程链路 | 杀进程链路 | 2026-07-18 |
| S06 | §3.1 App 进程重启 | [Process](../../Android_Framework/Process/) | 01-08 全部 | 进程生命周期 | 2026-07-18 |
| S06 | §3.3 Zygote 重启 | [Process](../../Android_Framework/Process/) | 03-Zygote | Zygote 机制 | 2026-07-18 |
| S06 | §3.4 整机重启 | [Linux_Kernel/Process](../../Linux_Kernel/Process/) | 全部 | Kernel panic 路径 | 2026-07-18 |
| **S07 KE** | §3 全部 | [Linux_Kernel/Process](../../Linux_Kernel/Process/) | 全部 | Kernel panic / oops | 2026-07-18 |
| S07 | §3.7 取证链路 | [Linux_Kernel/FS](../../Linux_Kernel/FS/) | pstore 相关 | pstore 机制 | 2026-07-18 |
| S07 | §3.5 WARN/BUG | [Linux_Kernel/MM_v2](../../Linux_Kernel/Memory_Management/MM_v2/) | 全部 | 内存 BUG 触发 | 2026-07-18 |
| **S08 演进全景** | §3 ART 17 硬变化 | [Runtime/ART](../../Runtime/ART/) 142 篇 | 全部 | ART 17 机制深挖 | 2026-07-18 |
| S08 | §4 K 6.18 硬变化 | [Linux_Kernel](../../Linux_Kernel/) 全部 | 各子系统 | K 6.18 机制深挖 | 2026-07-18 |
| S08 | §3.1 GenCC | [Runtime/ART/03-GC系统](../../Runtime/ART/03-GC系统/) 99 篇 | GenCC 相关 | 分代 GC 机制 | 2026-07-18 |
| S08 | §3.6 AppFunctions | [AI_Native_X/03_AI_for_Stability](../../AI_Native_X/03_AI_for_Stability/) | 全部 | AI 协同稳定性 | 2026-07-18 |
| S08 | §3.4 AnrHelper + §3.5 Perfetto | [Stability-Forensics](../Android_Framework/Stability-Forensics/) F01/F02 | 全部 | ANR/SWT 取证机制 | 2026-07-18 |
| **S09 横切专题** | §3 Binder 死锁 | [S01-ANR](../../Android_Framework/Stability/S01-ANR.md) + [S04-SWT](../../Android_Framework/Stability/S04-SWT.md) + [S05-HANG](../../Android_Framework/Stability/S05-HANG.md) | §3 全部 | binder 死锁与 ANR/SWT/HANG 关联 | 2026-07-18 |
| S09 | §4 IO 调度 | [S05-HANG](../../Android_Framework/Stability/S05-HANG.md) + [S07-KE](../../Android_Framework/Stability/S07-KE.md) + [S06-REBOOT](../../Android_Framework/Stability/S06-REBOOT.md) | §3 全部 | IO 卡顿与 HANG/KE/REBOOT 关联 | 2026-07-18 |
| S09 | §5 GC 卡顿 | [S01-ANR](../../Android_Framework/Stability/S01-ANR.md) + [S02-JE](../../Android_Framework/Stability/S02-JE.md) + [Runtime/ART/03-GC系统](../../Runtime/ART/03-GC系统/) | §3 全部 | GC 卡顿与 ANR/JE 关联 + GenCC 机制 | 2026-07-18 |
| S09 | §6 渲染卡顿 | [S01-ANR](../../Android_Framework/Stability/S01-ANR.md) + [S05-HANG](../../Android_Framework/Stability/S05-HANG.md) + [Runtime/ART](../../Runtime/ART/) | 全部 | Choreographer / SurfaceFlinger 机制 | 2026-07-18 |
| S09 | §7 锁竞争 | [S01-ANR](../../Android_Framework/Stability/S01-ANR.md) + [S02-JE](../../Android_Framework/Stability/S02-JE.md) + [S04-SWT](../../Android_Framework/Stability/S04-SWT.md) | §3 全部 | 锁竞争与 ANR/JE/SWT 关联 | 2026-07-18 |

---

## 3. 边界声明（Stability 不重复讲的内容）

| 主题 | Stability 边界 | 现有系列深度 |
|------|--------------|------------|
| **Watchdog 内部状态机** | S04 只讲"触发 SWT 的症状链" | [Watchdog](../../Android_Framework/Watchdog/) 6 篇讲透内部实现 |
| **InputDispatcher 完整机制** | S01 只讲"为何会触发 Input ANR" | [Input](../../Android_Framework/Input/) 8 篇讲透 |
| **Native 信号处理** | S03 只讲"信号→症状→tombstone 解读" | [Native_Crash](../../Runtime/Native_Crash/) 8 篇讲透 debuggerd 源码 |
| **ART GC 内部** | S02 只在 OOM 相关 JE 引用 | [ART 03](../../Runtime/ART/03-GC系统/) 9 篇讲透 |
| **Linux 调度** | S07 只在 softlockup/hardlockup 引用 | [Linux_Kernel/Process](../../Linux_Kernel/Process/) 7 篇讲透 CFS |
| **进程内存地图** | S02/S03 只在 OOM 引用 | [MM_v2](../../Linux_Kernel/Memory_Management/MM_v2/) 13 篇讲透 |
| **Binder 通信机制** | S05 只在 binder hang 引用 | [Binder](../../Linux_Kernel/Binder/) 全部讲透 |

---

## 4. 反向引用（现有系列 → Stability）

> 现有系列在写新文章时，如涉及"症状分类"，应引用 Stability 系列：

| 现有系列 | 引用 Stability 的场景 | 引用文章 |
|---------|---------------------|---------|
| [Watchdog](../../Android_Framework/Watchdog/) | 涉及"杀进程后整机重启" | S06 REBOOT |
| [Native_Crash](../../Runtime/Native_Crash/) | 涉及"tombstone 解读路径" | S03 NE |
| [ANR_Detection](../../Android_Framework/ANR_Detection/) | 涉及"主线程 hang 区别于 ANR" | S05 HANG |
| [Process](../../Android_Framework/Process/) | 涉及"REBOOT 链路分类" | S06 REBOOT |
| [AI_Native_X/03_AI_for_Stability](../../AI_Native_X/03_AI_for_Stability/) | 涉及"症状分类法" | S00 总览 |

---

## 5. 治理动作

- **每月核查**：架构师本人（或自动化脚本）点击所有引用链接，确认未 404
- **目标链接删除/移动前**：先在本矩阵找到所有引用方，逐个更新
- **新增 Stability 文章**：在本矩阵对应行加 `【待补】`，写完后填具体章节
- **新增现有系列文章**：如涉及 Stability 范围，反向引用并在本矩阵登记

---

> **版本**：v1.0（2026-07-18 与 Stability 系列同步建立）
>
> **下次维护触发点**：Stability 系列每篇文章撰写完成后，对应行"链接有效性最后核查"日期更新
