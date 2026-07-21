# Forensics 系列 → 跨系列引用矩阵

> **目的**：避免 Stability-Forensics 系列与现有 12+ 系列的重复造内容，明确"哪些内容 Forensics 不重复讲，直接引用"。
>
> **使用规则**：
> - Forensics 系列每篇文章的"本篇定位"段必须显式声明"不重复内容"边界
> - 涉及已有系列覆盖的内容时，**用 Markdown 链接引用**，不重复展开
> - 每月核查一次链接有效性（§7 强制）

---

## 1. 引用关系总图

```
Stability-Forensics 系列（取证维度）= 横向"症状 × 抓取链路"
  ↓ 引用
Stability 系列（症状维度）= 纵向"症状 × 机制"（已完结）
  ↓ 引用
现有 12+ 个相关系列
  ├─ [Perfetto 系列](../Perfetto/)  ← F00 / F01 / F02 / F06
  ├─ [Hprof 系列](../Hprof/)        ← F06
  ├─ [Native_Crash 系列](../01-Mechanism/Runtime/Native_Crash/)  ← F04
  ├─ [Watchdog 系列](../Watchdog/)  ← F02
  ├─ [ANR_Detection 系列](../ANR_Detection/) ← F01
  ├─ [Linux_Kernel/FS](../01-Mechanism/Kernel/FS/)  ← F05（pstore）
  ├─ [Tools/Tracing](../06-Foundation/Tools/Tracing/)  ← F06
  ├─ [Tools/Memory_Analysis](../06-Foundation/Tools/Memory_Analysis/)  ← F06
  ├─ [Android_Framework/Dumpsys](../Dumpsys/)  ← F07
  ├─ [Linux_Kernel/Process](../01-Mechanism/Kernel/Process/)  ← F05
  └─ [App/Handler/Looper](../01-Mechanism/App/Handler-MessageQueue-Looper/)  ← F01 / F06
```

> **核心关系**：Forensics 是 Stability 的"取证侧"——Stability 讲"症状怎么发生"，Forensics 讲"症状发生后怎么抓证据"。

---

## 2. 详细引用矩阵

| Forensics 文章 | 引用章节 | 引用系列 | 引用文章 | 引用原因 |
|--------------|---------|---------|---------|---------|
| **F00 总览** | §3 抓取层级 | [Stability S00](../Stability/S00-稳定性症状总览.md) | 7 大症状边界 | 边界对齐 |
| F00 | §4 抓取路径 | [Perfetto](../Perfetto/) | README + 各篇 | Perfetto 抓取 |
| F00 | §4 抓取路径 | [Hprof](../Hprof/) | README + 各篇 | hprof 抓取 |
| F00 | §4 抓取路径 | [ANR_Detection](../ANR_Detection/) | 全部 | anr traces 路径 |
| **F01 ANR 取证** | §3 ANR 抓取链 | [Stability S01](../Stability/S01-ANR.md) | §3 机制 | ANR 触发机制 |
| F01 | §3 抓取链 | [ANR_Detection](../ANR_Detection/) | 全部 | ANR 检测链路 |
| F01 | §4 Perfetto 抓取 | [Perfetto](../Perfetto/) | README + 各篇 | Perfetto 抓取 ANR 上下文 |
| F01 | §5 解读 | [App/Handler/Looper](../01-Mechanism/App/Handler-MessageQueue-Looper/) | README + 各篇 | 主线程 Looper 解读 |
| **F02 SWT 取证** | §3 抓取链 | [Stability S04](../Stability/S04-SWT.md) | §3 机制 | SWT 触发机制 |
| F02 | §3 抓取链 | [Watchdog](../Watchdog/) | 6 篇全部 | Watchdog 内部状态机 |
| F02 | §4 SystemServer Perfetto | [Perfetto](../Perfetto/) | README + 各篇 | Perfetto 抓取 SystemServer |
| F02 | §5 喂狗链路 | [ART 06](../01-Mechanism/Runtime/ART/06-信号与ANR-Trace/) | 全部 | ART 喂狗机制 |
| **F03 JE 取证** | §3 抓取链 | [Stability S02](../Stability/S02-JE.md) | §3 机制 | JE 触发机制 |
| F03 | §3 抓取链 | [ANR_Detection](../ANR_Detection/) | BinderStarve | dropbox 机制 |
| F03 | §4 异步线程 | [App/Handler/Looper](../01-Mechanism/App/Handler-MessageQueue-Looper/) | README + 各篇 | 异步线程机制 |
| F03 | §5 OOM 相关 | [Hprof](../Hprof/) | README + 各篇 | OOM 抓取 |
| **F04 NE 取证** | §3 抓取链 | [Stability S03](../Stability/S03-NE.md) | §3 机制 | NE 触发机制 |
| F04 | §3 抓取链 | [Native_Crash](../01-Mechanism/Runtime/Native_Crash/) | 8 篇全部 | debuggerd 源码 |
| F04 | §4 符号化 | [Native_Crash](../01-Mechanism/Runtime/Native_Crash/) | 5-栈回溯与符号化 | 符号化服务 |
| F04 | §3.9 Rust Binder | [Linux_Kernel/Binder](../01-Mechanism/Kernel/Binder/) | 全部 | Rust 版 Binder |
| F04 | §5 内存 NE | [Linux_Kernel/MM_v2](../01-Mechanism/Kernel/Memory_Management/MM_v2/) | 12-内存稳定性风险全景 | 内存崩溃 |
| **F05 KE 取证** | §3 抓取链 | [Stability S07](../Stability/S07-KE.md) | §3 机制 | KE 触发机制 |
| F05 | §3 pstore | [Linux_Kernel/FS](../01-Mechanism/Kernel/FS/) | pstore 相关 | pstore 机制 |
| F05 | §3 last_kmsg | [Linux_Kernel/FS](../01-Mechanism/Kernel/FS/) | pstore 相关 | last_kmsg 机制 |
| F05 | §3 取证链路 | [Linux_Kernel/Process](../01-Mechanism/Kernel/Process/) | 全部 | Kernel 进程机制 |
| F05 | §3 取证链路 | [Linux_Kernel/MM_v2](../01-Mechanism/Kernel/Memory_Management/MM_v2/) | 全部 | 内存 BUG 触发 |
| **F06 HANG + OOM 取证** | §3 HANG 抓取 | [Stability S05](../Stability/S05-HANG.md) | §3 机制 | HANG 触发机制 |
| F06 | §3 HANG 抓取 | [Perfetto](../Perfetto/) | README + 各篇 | systrace / Perfetto 抓取 HANG |
| F06 | §3 HANG 抓取 | [Tools/Tracing](../06-Foundation/Tools/Tracing/) | 全部 | ftrace 抓取 |
| F06 | §3 HANG 抓取 | [App/Handler/Looper](../01-Mechanism/App/Handler-MessageQueue-Looper/) | README + 各篇 | 主线程机制 |
| F06 | §4 OOM 抓取 | [Stability S02](../Stability/S02-JE.md) | §3.5 OOM | OOM 触发机制 |
| F06 | §4 OOM 抓取 | [Hprof](../Hprof/) | 全部 | hprof 抓取与解读 |
| F06 | §4 OOM 抓取 | [Tools/Memory_Analysis](../06-Foundation/Tools/Memory_Analysis/) | 全部 | 内存分析工具 |
| **F07 治理** | §3 APM | [Android_Framework/Perfetto](../Perfetto/) | 全部 | APM 接入 |
| F07 | §3 bugreport | [Android_Framework/Dumpsys](../Dumpsys/) | 全部 | Dumpsys 工具 |
| F07 | §3 商业符号化 | [Native_Crash](../01-Mechanism/Runtime/Native_Crash/) | 7-检测工具体系 | 商业符号化服务 |
| F07 | §3 bugreport | [Tools/Android_Tools](../06-Foundation/Tools/Android_Tools/) | 全部 | 抓取工具 |

---

## 3. 边界声明（Forensics 不重复讲的内容）

| 主题 | Forensics 边界 | 现有系列深度 |
|------|--------------|------------|
| **ANR 机制** | F01 只讲"ANR 触发后怎么抓 traces / dropbox / Perfetto" | [Stability S01](../Stability/S01-ANR.md) §3 讲透 ANR 机制 |
| **NE 信号机制** | F04 只讲"信号触发后 tombstone 怎么生成 + 怎么符号化" | [Stability S03](../Stability/S03-NE.md) + [Native_Crash](../01-Mechanism/Runtime/Native_Crash/) 8 篇讲透 |
| **SWT 机制** | F02 只讲"SystemServer 触发 SWT 后怎么抓 watchdog traces + Perfetto" | [Stability S04](../Stability/S04-SWT.md) + [Watchdog](../Watchdog/) 6 篇讲透 |
| **KE 机制** | F05 只讲"KE 触发后怎么从 pstore / last_kmsg 取证" | [Stability S07](../Stability/S07-KE.md) + [Linux_Kernel/Process](../01-Mechanism/Kernel/Process/) 讲透 |
| **HANG 机制** | F06 只讲"HANG 没有自动 dump 怎么主动抓 systrace/ftrace" | [Stability S05](../Stability/S05-HANG.md) 讲透 HANG 机制 |
| **OOM 机制** | F06 只讲"OOM 触发后怎么抓 hprof + smaps" | [Hprof](../Hprof/) 讲透 hprof 解读 |
| **Perfetto 工具本身** | F01/F02/F06 只讲"怎么用 Perfetto 抓稳定性上下文" | [Perfetto](../Perfetto/) 全部讲透工具 |
| **dropbox 系统** | F01-F05 只讲"对应症状的 dropbox tag + 抓取命令" | [ANR_Detection](../ANR_Detection/) + [Watchdog](../Watchdog/) 讲透 dropbox 机制 |
| **bugreport 工具** | F07 只讲"稳定性场景的 bugreport 自动化" | [Tools/Android_Tools](../06-Foundation/Tools/Android_Tools/) 讲透工具 |

---

## 4. 反向引用（Stability 系列 → Forensics）

> 现有 Stability 系列涉及"取证 / 抓取"时应引用 Forensics：

| 现有系列 | 引用 Forensics 的场景 | 引用文章 |
|---------|---------------------|---------|
| Stability S01 ANR | ANR traces 怎么生成 / 解读 | F01 ANR 取证 |
| Stability S02 JE | dropbox(APP_CRASH) 怎么抓 | F03 JE 取证 |
| Stability S03 NE | tombstone 怎么生成 / 符号化 | F04 NE 取证 |
| Stability S04 SWT | watchdog traces 怎么生成 | F02 SWT 取证 |
| Stability S05 HANG | HANG 没有 dump 怎么主动抓 | F06 HANG + OOM |
| Stability S07 KE | KE 怎么从 pstore 取证 | F05 KE 取证 |
| AI_Native_X/03_AI_for_Stability | 涉及"取证"全栈 | F07 治理 |

---

## 5. 治理动作

- **每月核查**：架构师本人（或自动化脚本）点击所有引用链接，确认未 404
- **目标链接删除/移动前**：先在本矩阵找到所有引用方，逐个更新
- **新增 Forensics 文章**：在本矩阵对应行加 `【待补】`，写完后填具体章节
- **新增现有系列文章**：如涉及 Stability 范围，反向引用并在本矩阵登记

---

> **版本**：v1.0（2026-07-18 与 Stability-Forensics 系列同步建立）
>
> **下次维护触发点**：Forensics 系列每篇文章撰写完成后，对应行"链接有效性最后核查"日期更新
