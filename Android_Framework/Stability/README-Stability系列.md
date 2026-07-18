# Android 稳定性症状系列（Stability）

> **目标读者**：Android 稳定性架构师
>
> **系列定位**：按"线上症状"维度组织 Android 稳定性问题的完整分类与排查体系
>
> **核心问题**：ANR / JE / NE / SWT / HANG / REBOOT / KE 7 大类症状
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）

---

## 伴生文档（本系列的"路线 + 质量"姐妹篇）

| 文档 | 编号 | 作用 | 何时读 |
|:-----|:----:|:-----|:-------|
| [**学习路线（稳定性架构师 L00）**](README-学习路线-稳定性架构师.md) | L00 | 4 阶段 × 3 角色 × 110 篇文章的阅读路径 | **开始学习前**先看这个 |
| [**系列质量评估报告（Q00）**](README-系列质量评估报告.md) | Q00 | 全仓 ~110 篇按 🟢🟡🟠🔴 4 档评级 | 决定"先补哪个缺口"时看 |
>
> **完成状态**：🚧 撰写中（S00-S07 规划完成，2026-07-18 开干）

---

## 0. 系列总定位（架构师视角）

### 0.1 一句话定位

**Stability 系列是从"线上症状"维度切入的 Android 稳定性完整分类与排查体系——把任何稳定性问题在 30 秒内分类到 7 大症状之一，给出"标准排查路径 + 关键日志关键词 + dump 抓取方式 + 修复模式"。**

### 0.2 与现有系列的关系（关键）

> **重要不重复声明**：本系列**不重复**讲现有系列已深入的机制细节，只从"症状视角"切入并串联。

| 维度 | 现有系列（机制视角） | Stability 系列（症状视角） |
|:-----|:-------------------|:------------------------|
| **Watchdog** | [Watchdog 6 篇](../Watchdog/) 讲透内部状态机 | S04 SWT 只讲"触发 SWT 的症状链 + 排查路径" |
| **ANR** | [ANR_Detection 3 篇专题](../ANR_Detection/) + [Input 8 篇](../Input/) 讲透检测链路 | S01 ANR 只讲"4 类 ANR 的症状区分 + 主线程为啥会卡" |
| **NE** | [Native_Crash 8 篇](../../Runtime/Native_Crash/) 讲透 debuggerd 源码 | S03 NE 只讲"6 种信号 → 症状 → tombstone 解读路径" |
| **Process 治理** | [Process 8 篇](../Process/) 讲透进程生命周期 | S06 REBOOT 只讲"重启源分类法 + cascade 链路" |
| **ART 异常** | [ART 06 信号](../../Runtime/ART/06-信号与ANR-Trace/) 讲透机制 | S02 JE 只讲"Throwable 全景 + 监控盲区" |
| **HANG** | **无对应** | **S05 HANG 是本系列独占视角**（主线程软卡死 / IO hang / binder hang / kernel hung_task 全栈串联） |
| **KE** | [Linux_Kernel/Process](../../Linux_Kernel/Process/) 讲透 Kernel panic | S07 KE 只讲"用户空间能看到的 KE 信号 + 取证" |

> **架构师防混淆口诀**（速记，详见 [Reference/术语表.md §1.1](../../Reference/术语表.md)）：
> - **ANR 主动 / HANG 被动**
> - **SWT 杀的是 SystemServer / ANR 杀的是 App**
> - **NE 在用户态 / KE 在内核态**
> - **REBOOT 是结果，不是原因**

### 0.3 系列对线 JD

| JD 维度 | 本系列对位 |
| :--- | :--- |
| 职责 1「Android 稳定性（Crash/ANR/OOM/性能退化）核心负责人」 | **核心对线**——S00-S07 整体对线 |
| 职责 2「覆盖 Framework + Native + Linux Kernel 层」 | **核心对线**——S01-S07 各占一层 |
| 职责 4「主导稳定性治理体系建设」 | S05 HANG（最难发现）+ S06 REBOOT（结果态） |
| 职责 5「跨团队主导 0→1 项目」 | S00 总览（症状分类法） |
| 职责 6「稳定性治理 / 监控 / APM 体系建设」 | S01-S07 每篇都含"治理"段 |

---

## 1. 篇章列表（8 篇 · 总 ~5,500 行）

| # | 篇号 | 标题 | 系列角色 | 强依赖 | 行数目标 |
|---|------|------|---------|--------|---------:|
| 1 | **S00** | 稳定性症状总览：7 类问题分类法 + 系统栈映射 | **全局观** | 无 | ~700 |
| 2 | **S01** | ANR：4 类 ANR 的症状区分 + 主线程为啥会卡 | 症状专题 1/7 | S00 | ~900 |
| 3 | **S02** | JE：未捕获 Throwable 全景 + 监控盲区 | 症状专题 2/7 | S00 | ~700 |
| 4 | **S03** | NE：6 种信号 → 症状 → tombstone 解读路径 | 症状专题 3/7 | S00 | ~900 |
| 5 | **S04** | SWT：SystemServer 卡死与 watchdog 触发的症状链 | 症状专题 4/7 | S00 | ~700 |
| 6 | **S05** | HANG：未被捕获的卡死（主线程 / IO / Binder / Kernel） | 症状专题 5/7 | S00 | ~800 |
| 7 | **S06** | REBOOT：重启源分类、cascade 链路、pstore / dump 体系 | 症状专题 6/7 | S00 | ~700 |
| 8 | **S07** | KE：Kernel 异常的用户空间可见信号 + 排查路径 | 症状专题 7/7 | S00 | ~700 |

**合计**：~5,500-6,000 行 · 8 个篇章 · 16 个锚点案例（每篇 2 个：1 典型模式 + 1 公开 bugreport）· 与现有 10+ 系列 30+ 篇文章形成"速查 + 机制"双向引用

---

## 2. 系列设计思路（架构师思维链 5 段展开）

```
定位：7 大症状是什么 / 解决什么问题
  ↓
边界：互相怎么区分 / 系统栈哪一层
  ↓
机制：内部怎么触发（深挖式，每篇 600-900 行）
  ↓
风险：哪些场景会触发 / 典型日志特征
  ↓
治理：怎么抓 dump / 怎么排查 / 修复模式
```

### 2.1 7 大症状系统栈位置（架构图）

```
┌────────────────────────────────────────────────────────────────────┐
│  App 层（Java/Kotlin）                                              │
│  ├─ JE: Throwable 未处理 ──────────────→ Crash 弹窗 + tombstone    │
│  └─ ANR (App 端触发) ─────────────────→ AppNotRespondingDialog   │
├────────────────────────────────────────────────────────────────────┤
│  Framework 层                                                       │
│  ├─ ANR (System 端检测) ─────────────→ AMS 杀进程 + dropbox        │
│  ├─ SWT (Watchdog 检测) ──────────────→ 杀 SystemServer / 重启      │
│  ├─ NE (Framework 自身 native 代码) ──→ debuggerd + Tombstone     │
│  └─ HANG (Service / Provider 卡死) ───→ dropbox(NO_RESPONSE)       │
├────────────────────────────────────────────────────────────────────┤
│  Native 库 / HAL 层                                                  │
│  └─ NE (Native 库崩溃) ──────────────→ debuggerd + Tombstone       │
├────────────────────────────────────────────────────────────────────┤
│  Kernel 层                                                          │
│  ├─ KE (oops/panic) ─────────────────→ 整机重启 / pstore 持久化    │
│  ├─ HANG (hung_task/RCU/softlockup) ─→ 检测 + 可能重启             │
│  └─ REBOOT (Kernel panic 链路) ──────→ 整机重启                    │
├────────────────────────────────────────────────────────────────────┤
│  跨层                                                                │
│  └─ REBOOT: 任何上层症状都可能演变为下层重启（cascade）              │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 7 大症状的触发链（cascade）

```
App 主线程 binder hang（5s）→ 触发 ANR
  ↓
AMS 检测到 ANR 后 binder call 阻塞（10s）
  ↓
Watchdog 检测到 SystemServer 卡死（30s）→ 触发 SWT
  ↓
SWT 杀 SystemServer → 整机重启
  ↓
Zygote 拉起 SystemServer 失败 → REBOOT 反复
```

**关键洞察**：**1 个根因可触发 4 类症状**，架构师排查时必须能正向推导 + 反向归因。

---

## 3. 每篇文章的章节规划

### 3.1 S00「稳定性症状总览」

| 章节 | 内容 | 核心抓手 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| §1 为什么需要症状分类法 | 从"机制视角"到"问题视角"的范式转移 | 行业数据 + 痛点 | 排查效率 |
| §2 7 大症状的严格定义与边界 | ANR/JE/NE/SWT/HANG/REBOOT/KE 严格定义 + 易混淆对区分 | 术语表 | 分类基础 |
| §3 系统栈映射 | ASCII 架构图（见 §2.1） | 系统栈坐标 | 全局定位 |
| §4 触发链（cascade） | 同一根因如何在 7 类症状间 cascade | 时序图 | 排查思路 |
| §5 风险地图 | 7 大症状的线上占比、用户感知分级 | 行业数据 | 严重性 |
| §6 全局排查体系 | dump 取证 → 症状分类 → 机制定位 → 修复模式 | 工具链 | 治理闭环 |
| §7 与现有系列关系 | 引用矩阵 + 边界声明 | 跨系列 | 不重复 |
| §8 实战案例 | CASE-STAB-00-01 cascade 链路 | 完整还原 | 子系列锚点 |
| 总结 + 附录 A/B/C/D | — | — | — |

### 3.2 S01「ANR：4 类 ANR 的症状区分 + 主线程为啥会卡」

| 章节 | 内容 | 核心源码（AOSP 17） |
| :--- | :--- | :--- |
| §1 定位 | ANR 的本质：主线程 looper 阻塞超阈值 | 概念 |
| §2 边界 | ANR vs HANG vs SWT 区分（最易混淆） | 对比表 |
| §3 机制（深挖） | **5 个子节** | 见下 |
| §3.1 Input ANR | dispatchOnce + waitQueue + 5s 链路 | `frameworks/native/services/inputflinger/InputDispatcher.cpp` |
| §3.2 Broadcast ANR | 串/并行队列 + 10s 超时 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` |
| §3.3 Service ANR | foreground 5s / bg 20s / exec 10s | `frameworks/base/services/core/java/com/android/server/am/ActiveServices.java` |
| §3.4 Provider ANR | publish 10s 超时 | `ActivityManagerService.java` |
| §3.5 AOSP 17 变化 | AppFunctions + AI Agent OS 集成对 ANR 影响 | `frameworks/base/apex/` |
| §4 风险地图 | 5 类触发场景 + logcat 模板 | logcat 关键字 |
| §5 治理 | dump 取证（anr traces.txt）+ 主线程栈解读 + 修复模式 | `/data/anr/` |
| §6 实战案例 | CASE-STAB-01-01/02 | 见 [Reference/Stability-案例索引.md](../../Reference/Stability-案例索引.md) |
| 总结 + 附录 A/B/C/D | — | — |

### 3.3 S02「JE：未捕获 Throwable 全景 + 监控盲区」

| 章节 | 内容 | 核心源码（AOSP 17） |
| :--- | :--- | :--- |
| §1 定位 | JE 的本质：Throwable 沿调用栈冒泡未被 catch | 概念 |
| §2 边界 | JE vs ANR vs NE | 对比表 |
| §3 机制（深挖） | **5 个子节** | 见下 |
| §3.1 ART 异常分发 | throw → 栈展开 → catch → 兜底 | `art/runtime/interpreter/interpreter.cc` |
| §3.2 进程死亡链路 | KillApplicationHandler → appDiedLocked | `ActivityManagerService.java` |
| §3.3 Crash 弹窗与 dropbox | ApplicationErrorReport + dropbox(APP_CRASH) | `DropBoxManagerService.java` |
| §3.4 异步线程的 JE | HandlerThread / Executor / WorkManager 逃逸 | 各框架 |
| §3.5 常见 JE 全景 | OOM / NPE / ClassCast / ConcurrentModification | 综合 |
| §4 风险地图 | 监控盲区（异步线程 JE 不弹窗） | dropbox 特征 |
| §5 治理 | Crashlytics / Sentry / 自研 APM + 修复模式 | dropbox 抓取 |
| §6 实战案例 | CASE-STAB-02-01/02 | 案例索引 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.4 S03「NE：6 种信号 → 症状 → tombstone 解读路径」

| 章节 | 内容 | 核心源码（AOSP 17 / K 6.18） |
| :--- | :--- | :--- |
| §1 定位 | NE 的本质：kernel 投递致命信号 → debuggerd → tombstone | 概念 |
| §2 边界 | NE vs KE | 对比表 |
| §3 机制（深挖） | **9 个子节** | 见下 |
| §3.1 SIGSEGV | 空指针/越界/已释放 | `kernel/signal.c` |
| §3.2 SIGABRT | abort()/断言/fortify/malloc 检测 | abort() 实现 |
| §3.3 SIGBUS | 内存对齐/mmap/Binder 错误 | mmap 路径 |
| §3.4 SIGFPE | 除零/整数溢出 | FPE 触发 |
| §3.5 SIGILL | 非法指令/栈破坏 | 段保护 |
| §3.6 SIGSYS | seccomp 拦截 | seccomp 路径 |
| §3.7 tombstone 16 段结构 | registers → memory map | `system/core/debuggerd/libdebuggerd/tombstone.cpp` |
| §3.8 栈回溯与符号化 | FP/PC/CFI unwind + addr2line | unwind 原理 |
| §3.9 AOSP 17 / K 6.18 变化 | Rust Binder 上主线 | `drivers/android/binder_alloc_rust.rs` |
| §4 风险地图 | 高频场景 + 关键字 | 关键字表 |
| §5 治理 | dropbox(TOMBSTONE) + 符号化 + APM | 监控链路 |
| §6 实战案例 | CASE-STAB-03-01/02 | 案例索引 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.5 S04「SWT：SystemServer 卡死与 watchdog 触发的症状链」

| 章节 | 内容 | 核心源码（AOSP 17） |
| :--- | :--- | :--- |
| §1 定位 | SWT 的本质：SystemServer 卡死超 watchdog 阈值 | 概念 |
| §2 边界 | SWT vs ANR vs HANG | 对比表（**最易混淆**） |
| §3 机制（深挖） | **6 个子节** | 见下 |
| §3.1 Watchdog 线程 | 30s 周期 + monitor 列表 | `frameworks/base/services/core/java/com/android/server/Watchdog.java` |
| §3.2 HandlerChecker 机制 | 每 monitor 30s + 连续 N 次 | HandlerChecker |
| §3.3 杀进程判定 | 完成度检查 + 杀 SystemServer | `Watchdog.java: evaluateCheckerCompletionLocked` |
| §3.4 三层杀进程策略 | 杀线程 → 杀 SystemServer → 整机重启 | 状态机 |
| §3.5 PerfettoTrace 集成 | AOSP 17 新增自动 dump | 新增机制 |
| §3.6 喂狗机制 | input/vsync/binder | input 路径 |
| §4 风险地图 | 高频场景 + logcat 字段 | logcat 模板 |
| §5 治理 | watchdog traces + 主线程栈 + 喂狗链路 | 排查路径 |
| §6 实战案例 | CASE-STAB-04-01/02 | 案例索引 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.6 S05「HANG：未被捕获的卡死」（**本系列独占视角**）

| 章节 | 内容 | 核心源码（AOSP 17 / K 6.18） |
| :--- | :--- | :--- |
| §1 定位 | HANG 的本质：功能失效但未被任何超时机制捕获 | 概念 |
| §2 边界 | HANG vs ANR vs SWT 决策树 | **详细决策树** |
| §3 机制（深挖） | **5 个子节** | 见下 |
| §3.1 App 主线程软卡死 | 阈值 5-10s 但未到 ANR 阈值 | 实测路径 |
| §3.2 IO HANG | 文件系统/Socket/块设备 hang 30s+ | `fs/io_uring.c`, `fs/f2fs/` |
| §3.3 Binder HANG | binder 死锁/排队/transaction 满 | `IPCThreadState.cpp`, `kernel/drivers/android/binder.c` |
| §3.4 Kernel HANG | hung_task/RCU stall/softlockup/hardlockup | `kernel/hung_task.c`, `kernel/rcu/`, `kernel/watchdog.c` |
| §3.5 HANG 监测盲区 | 主线程到 5s 但 ANR 阈值未到的"灰色地带" | 实测时间线 |
| §4 风险地图 | 高频场景 + 监控难度 | 行业经验 |
| §5 治理 | ANR traces + systrace + ftrace + dropbox + Perfetto | 工具链 |
| §6 实战案例 | CASE-STAB-05-01/02 | 案例索引 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.7 S06「REBOOT：重启源分类、cascade 链路、pstore / dump 体系」

| 章节 | 内容 | 核心源码（AOSP 17 / K 6.18） |
| :--- | :--- | :--- |
| §1 定位 | REBOOT 的本质：非预期的进程或系统重启 | 概念 |
| §2 边界 | REBOOT vs SWT（结果 vs 原因） | 对比表 |
| §3 机制（深挖） | **5 个子节** | 见下 |
| §3.1 App 进程重启 | Crash 后 Zygote fork 链路 | Zygote + Process |
| §3.2 SystemServer 重启 | kill → restart | Watchdog 杀进程 |
| §3.3 Zygote 重启 | Zygote 死 → system_server 死 → 整机重启 | init.rc |
| §3.4 整机重启 | Kernel panic / reboot 命令 | `kernel/reboot.c`, `kernel/panic.c` |
| §3.5 cascade 链路 | 上层症状演变为下层重启的链路 | 全文串联 |
| §4 风险地图 | 高频重启源 + 误判 | bootstat 数据 |
| §5 治理 | 重启溯源：last_kmsg + pstore + dropbox + bootstat | 取证链路 |
| §6 实战案例 | CASE-STAB-06-01/02 | 案例索引 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.8 S07「KE：Kernel 异常的用户空间可见信号 + 排查路径」

| 章节 | 内容 | 核心源码（K 6.18） |
| :--- | :--- | :--- |
| §1 定位 | KE 的本质：kernel 检测到不可恢复/可恢复错误 | 概念 |
| §2 边界 | KE vs NE（内核空间 vs 用户空间） | 对比表 |
| §3 机制（深挖） | **7 个子节** | 见下 |
| §3.1 Kernel Panic | panic() + 整机重启 | `kernel/panic.c` |
| §3.2 Kernel Oops | 可恢复 + 杀进程 | `kernel/oops.c` |
| §3.3 hung_task | 进程 D 状态超阈值 | `kernel/hung_task.c` |
| §3.4 softlockup / hardlockup | CPU 软/硬死锁 | `kernel/watchdog.c` |
| §3.5 WARN / BUG | 警告与断言 | `kernel/bug.c` |
| §3.6 RCU stall | RCU 读侧长时间不退出 | rcu 路径 |
| §3.7 用户空间能看到的 KE 信号 | dmesg / pstore / ramoops 取证 | 取证链路 |
| §4 风险地图 | KE 在用户空间通常已演变为整机重启/ANR/SWT | 现象学 |
| §5 治理 | dmesg + pstore + ramoops + kmsg dump | 工具链 |
| §6 实战案例 | CASE-STAB-07-01/02 | 案例索引 |
| 总结 + 附录 A/B/C/D | — | — |

---

## 4. 写作顺序（按"症状易混淆对"分组）

```
Phase 1（症状分类法立住）
  → S00 总览（先把 7 类的边界和易混淆点立住）

Phase 2（最易混淆的对：ANR vs HANG）
  → S01 ANR（机制深挖）
  → S05 HANG（机制深挖，**独占视角**）

Phase 3（崩溃类：JE / NE / KE）
  → S02 JE
  → S03 NE
  → S07 KE（**单独成篇，因为 Kernel 是另一条栈**）

Phase 4（结果类：SWT / REBOOT）
  → S04 SWT（ANR/HANG 的升级版）
  → S06 REBOOT（所有症状的最终态）
```

**时间预估**：每篇 700-900 行（机制深挖式），按过去系列节奏（2-3 工作日/篇），8 篇 ~16-24 工作日。

---

## 5. 跨系列引用矩阵（详见 [Reference/Stability-跨系列引用矩阵.md](../../Reference/Stability-跨系列引用矩阵.md)）

| Stability 文章 | 主引用系列 | 引用文章数 |
|--------------|----------|----------|
| S00 | Watchdog / ANR_Detection / Native_Crash / Process | 4 |
| S01 ANR | ANR_Detection / Handler / Input_Driver / ART 06 | 4 |
| S02 JE | ART 06 / ANR_Detection / Hprof | 3 |
| S03 NE | Native_Crash / Linux_Kernel/Process / Linux_Kernel/Binder / MM_v2 | 4 |
| S04 SWT | Watchdog / ART 06 | 2 |
| S05 HANG | Linux_Kernel/Binder / Linux_Kernel/Process / Handler / Linux_Kernel/IO | 4 |
| S06 REBOOT | Watchdog / Process / Linux_Kernel/Process | 3 |
| S07 KE | Linux_Kernel/Process / Linux_Kernel/FS / MM_v2 | 3 |

---

## 6. 阅读建议

### 6.1 优先级（时间有限先读哪几篇）

- **5 分钟全局**：S00（7 类症状的边界 + 系统栈映射）
- **30 分钟核心**：S00 + S01（ANR 是最高频症状）
- **2 小时深入**：S00 → S01 → S05（最易混淆对）
- **完整学习**：按"Phase 1 → Phase 2 → Phase 3 → Phase 4"顺序

### 6.2 排查时反向检索（速查入口）

| 看到症状 | 跳到 | 关键看哪节 |
|---------|------|----------|
| 弹"应用无响应" | S01 ANR | §2 边界 + §5 治理 |
| Crash 弹窗 | S02 JE | §2 边界 + §5 治理 |
| 应用静默退出 | S02 JE（异步线程） | §3.4 异步线程 JE |
| tombstone 文件 | S03 NE | §3.7 16 段结构 + §5 治理 |
| 系统反复重启 | S06 REBOOT | §3.5 cascade + §5 治理 |
| last_kmsg 异常 | S07 KE | §3.1-3.6 + §5 治理 |
| 用户报"卡"但无 ANR | **S05 HANG** | §2 决策树 + §3 各层 HANG |
| 杀 SystemServer | S04 SWT | §3 状态机 + §5 治理 |

---

## 7. 质量基线（v4 §4 + §9 破例记录）

### 7.1 硬性要求（沿用 v4）

| 维度 | 要求 |
|:-----|:-----|
| 单篇行数 | ≥ 300 行（机制深挖式实际 700-900 行，**破例**） |
| 图表数 | 4-6 张（机制深挖式实际 5-7 张，**破例**） |
| 实战案例 | 1-2 个（每篇固定 2 个：1 典型模式 + 1 公开 bugreport） |
| 附录 | A 源码索引 / B 路径对账表【强制】/ C 量化自检表 / D 工程基线表（按需） |
| 本篇定位 | 强制开头段 |
| 跨篇引用 | Markdown 链接 |
| 校准轮次 | 3 轮（结构 / 硬伤 / 锐度），每轮记决策日志 |

### 7.2 破例决策记录（v4 §9 强制）

| 破例项 | 破例内容 | 破例理由 | 影响范围 | 是否传染 |
|:------|:---------|:---------|:---------|:---------|
| 单篇行数 | 700-900 行（v4 默认 300-1500） | 机制深挖式需详细源码走读 | 全系列 8 篇 | 是（成为本系列基线） |
| 图表数 | 5-7 张（v4 默认 4-6） | 机制深挖式需多张时序图/栈图 | 全系列 8 篇 | 是（成为本系列基线） |
| 与现有系列重复 | 接受部分机制重叠 | 机制深挖式必然结果，从症状视角讲 | 全系列 8 篇 | 是（README 已声明"视角互补"） |

### 7.3 工程基线表（Stability 系列专项）

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
| :--- | :--- | :--- | :--- |
| **ANR 阈值（Input）** | 5s | 不可调 | 高频事件会偶发 |
| **ANR 阈值（Broadcast）** | 10s（前台）/ 60s（后台） | 不可调 | 串行队列会累积 |
| **ANR 阈值（Service）** | 20s（前台）/ 200s（后台） | 不可调 | startService 易踩 |
| **ANR 阈值（Provider）** | 10s | 不可调 | 启动期 publish 阻塞 |
| **Watchdog 周期** | 30s | AOSP 默认 | 太短→误杀；太长→响应慢 |
| **hung_task 超时** | 120s | `/proc/sys/kernel/hung_task_timeout_secs` | 太短→误报；太长→响应慢 |
| **softlockup 阈值** | 20s | `/proc/sys/kernel/watchdog_thresh` | 同上 |
| **hardlockup 阈值** | 10s | NMI 中检测，不可配 | — |
| **tombstone 保留** | `/data/tombstones/` 10 个 | 满了覆盖最早的 | 高发期会被覆盖 |
| **pstore 大小** | 厂商定制（通常 64K-1M） | ramoops/pstore 配置 | 太小→取证丢失 |
| **dropbox 保留期** | 7 天（APP_CRASH）/ 30 天（SYSTEM_TOMBSTONE） | `/data/system/dropbox/` 满后覆盖 | 高发期会丢关键 |
| **ANR traces 保留** | 5 个 | `/data/anr/` 满后覆盖 | 必须有日志采集 |

---

## 8. 16 个锚点案例（详见 [Reference/Stability-案例索引.md](../../Reference/Stability-案例索引.md)）

| 文章 | 案例 1（典型模式） | 案例 2（公开 bugreport） |
| :--- | :--- | :--- |
| S00 | CASE-STAB-00-01 cascade 链路 | AOSP issue 链 |
| S01 | CASE-STAB-01-01 主线程 onTouchEvent 30ms | AOSP Issue 2314383 |
| S02 | CASE-STAB-02-01 异步 HandlerThread OOM | AOSP Issue 240112930 |
| S03 | CASE-STAB-03-01 JNI IsAssignableFrom | AOSP Issue 268068355 |
| S04 | CASE-STAB-04-01 AMS binder 阻塞 60s | AOSP Issue 290873281 |
| S05 | CASE-STAB-05-01 Volley 4.5s 软卡 | AOSP Issue 264150921 |
| S06 | CASE-STAB-06-01 SystemServer 反复重启 | AOSP Issue 260500213 |
| S07 | CASE-STAB-07-01 binder mutex 死锁 | AOSP Issue 252354175 |

---

## 9. 基础版本基线声明（v4 §8 强制）

- **Framework/应用层**：AOSP `android-17.0.0_r1`（API 37）
- **Linux 内核**：`android17-6.18`（Linux 6.18 LTS，2025-11-30 发布，EOL 2030-07-01）
- **AOSP manifest 分支建议**：`android-latest-release`
- **AOSP 17 关键变化**（写作时主动覆盖）：
  - ART 17：分代 GC 强化、无锁 MessageQueue（API 37+）
  - AppFunctions / AI Agent OS 集成对 ANR 的新影响
- **Linux 6.18 关键变化**（写作时主动覆盖）：
  - Rust 版 Binder 上主线（与 C 版并存）
  - sheaves 内存分配
  - eBPF 加密签名
  - exFAT 16x 加速

---

## 10. 参考资料

### 10.1 现有相关系列（已落地）

- [Android_Framework/Watchdog](../Watchdog/) — Watchdog 6 篇
- [Android_Framework/ANR_Detection](../ANR_Detection/) — ANR 检测 3 篇专题
- [Android_Framework/Process](../Process/) — 进程架构演进 8 篇
- [Android_Framework/Input](../Input/) — Input 8 篇
- [Android_Framework/Hprof](../Hprof/) — Hprof 系列
- [Android_Framework/Perfetto](../Perfetto/) — Perfetto 系列
- [Runtime/Native_Crash](../../Runtime/Native_Crash/) — Native Crash 8 篇
- [Runtime/ART/06-信号与ANR-Trace](../../Runtime/ART/06-信号与ANR-Trace/) — ART 信号子系列
- [App/Handler_MessageQueue_Looper](../../App/Handler_MessageQueue_Looper/) — Handler 系列
- [Linux_Kernel/Binder](../../Linux_Kernel/Binder/) — Binder 系列
- [Linux_Kernel/Process](../../Linux_Kernel/Process/) — Kernel 进程
- [Linux_Kernel/Memory_Management/MM_v2](../../Linux_Kernel/Memory_Management/MM_v2/) — 内存 v2
- [Linux_Kernel/IO](../../Linux_Kernel/IO/) — IO 系列
- [Linux_Kernel/FS](../../Linux_Kernel/FS/) — FS 系列
- [AI_Native_X/03_AI_for_Stability](../../AI_Native_X/03_AI_for_Stability/) — AI 治理稳定性

### 10.2 Reference 基础设施

- [Reference/术语表.md](../../Reference/术语表.md) — 全局术语表（含本系列 7 大症状定义）
- [Reference/Stability-跨系列引用矩阵.md](../../Reference/Stability-跨系列引用矩阵.md) — 本系列跨系列引用
- [Reference/Stability-案例索引.md](../../Reference/Stability-案例索引.md) — 16 个案例编号

### 10.3 行业资料

- Android Source：[cs.android.com/android-17.0.0_r1](https://cs.android.com/android-17.0.0_r1)
- Linux Kernel：[elixir.bootlin.com/linux/v6.18](https://elixir.bootlin.com/linux/v6.18)
- AOSP Issue Tracker：[issuetracker.google.com/issues?q=componentid:190923](https://issuetracker.google.com/)

---

## 11. 校准决策日志（v4 §7 强制 · 占位）

> 每篇文章撰写完成后，在该文章开头"本篇定位"段下方维护本日志。

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|------|------|------|------|---------|
| 待补 | — | — | — | — |

---

> **系列导航**：[← 进程架构演进系列](../Process/README-进程架构演进系列.md) | [本系列 README 顶部](#)
>
> **最后更新**：2026-07-18（v1.0 骨架建立）
