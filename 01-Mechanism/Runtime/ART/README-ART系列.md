# ⚠️ v1 旧稿标记

> **本篇性质**：**系列总览**（v1 顶层 README），**不是单篇 v1 旧文** —— 标记是说明性，不影响阅读
>
> - **v1 顶层基线**：AOSP `android-14.0.0_r1`（API 34）+ Linux `android14-5.10/5.15`（**v1 时代基线**）
> - **v2 顶层基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`
> - **v1 总览的"系列设计思路 + 阅读建议"在 ART 17 上仍然适用**，但基线和硬变化已过时
>
> **v2 顶层总览**（已按 本规范 + AOSP 17 + 6.18 写完）：
>
> - [README-ART系列 v2](README-ART系列-v2.md) — 含 9 子模块 v2 规划 + 渐进式升级策略 + 全系列链接
>
> **建议**：本顶层总览**可作为"目录地图"读**（系列设计思路仍然成立），但具体基线和硬变化请**用 v2 顶层 + 9 篇 v2 子模块篇为准**。
>
> **标记时间**：2026-07-17（v2 全系列成稿后批量标）
>
> ---

# 面向稳定性的 ART 架构解析系列

> **作为稳定性架构师，我们日常面对的 OOM、ANR、Native Crash、死锁、内存泄漏、启动超时……90% 的根因最终都指向 ART。** 因为所有的 Java/Kotlin 代码——无论是 App 还是 System Server——都跑在 ART 之上。
>
> 本系列的目标：**让你在遇到任何 ART 相关的线上问题时，能快速定位到对应的子系统、找到对应的源码文件、理解问题的根因机制，并给出治理方案。**

---

## 系列整体架构

本系列按 ART 的**子系统维度**组织为 9 个子模块，每个子模块是一个独立目录：

```
ART/
├── README-ART系列.md                    # 本文档：ART 整体框架与导读
├── _archive/                            # 旧版 10 篇（保留备份，不再维护）
│
├── 00-总览/                             # 全局观
│   └── 01-ART总览：稳定性架构师的全局视角
│
├── 01-字节码与指令集/                    # 字节码层面
│   └── 01-Dex文件与Dalvik指令集
│
├── 02-编译与执行/                       # 编译执行
│   └── 01-编译路径全景：解释器/JIT/AOT/PGO
│
├── 03-类加载与链接/                     # 类加载
│   └── 01-类加载完整流程
│
├── 04-内存与GC/                         # ★ 本轮重点：GC 子模块（9 篇已完稿）
│   ├── README-GC子模块.md
│   ├── 01-GC基础理论
│   ├── 02-Heap与分配器
│   ├── 03-CMS GC
│   ├── 04-CC GC
│   ├── 05-Generational CC
│   ├── 06-Reference与Finalizer
│   ├── 07-GC调度与触发
│   ├── 08-GC与其他子系统
│   └── 09-GC诊断与治理
│
├── 05-JNI/                              # JNI
│   └── 01-JNI完整解析
│
├── 06-信号与ANR-Trace/                  # 信号机制
│   ├── 01-信号机制与SignalCatcher
│   └── 02-ANR Trace完整链路
│
├── 07-启动流程/                         # 启动全流程
│   └── 01-从app_process到第一行Java代码
│
└── 08-对比与演进/                       # 横切对比
    ├── 01-ART与JVM设计哲学
    ├── 02-Mainline与APEX
    ├── 03-Hook框架与ART
    └── 04-监控与诊断基础设施
```

---

## 系列设计思路

架构师看一个系统，遵循的逻辑链是：

```
它是什么？解决什么问题？（定位）
        ↓
它依赖什么底层概念？（理论根基）
        ↓
它的数据结构是什么？（内存布局）
        ↓
它的算法是怎么演进的？（历史脉络）
        ↓
它如何被调度和触发？（机制细节）
        ↓
它与哪些子系统深度交互？（横切专题）
        ↓
我该怎么诊断、监控、治理？（落地工具链）
```

本系列按照这条逻辑链分为 **9 个子模块**：

| 子模块 | 角色 | 核心问题 | 文章数 | 状态 |
|:---|:---|:---|:---:|:---:|
| **00-总览** | 全局观 | ART 是什么、在哪里、怎么启动 | 1 | **✓ 完稿** |
| **01-字节码与指令集** | 基础层 | ART 执行的字节码长什么样 | 1 | **✓ 完稿** |
| **02-编译与执行** | 核心机制 | 字节码怎么变成机器码并执行 | 1 | **✓ 完稿** |
| **03-类加载与链接** | 核心机制 | 类从磁盘到内存的完整路径 | 1 | **✓ 完稿** |
| **04-内存与GC** | 核心机制 | 内存怎么管理、对象怎么回收 | **9** | **✓ 完稿** |
| **05-JNI** | 边界 | Java 与 Native 的边界战争 | 1 | **✓ 完稿** |
| **06-信号与ANR-Trace** | 横切 | ANR 时堆栈怎么 dump 出来 | 2 | **✓ 完稿** |
| **07-启动流程** | 生命周期 | ART 怎么从无到有 | 1 | **✓ 完稿** |
| **08-对比与演进** | 横切对比 | ART 怎么走到今天、未来去哪 | 4 | **✓ 完稿** |


---

## 各子模块的章节规划

### 00-总览：ART 是什么

- ART 的定义与职责边界
- Dalvik → AOT → 混合编译 → Cloud Profile → Mainline 的演进史
- ART 在 Android 分层架构中的位置（Framework 之下、Native 库之上）
- System Server / App 进程 / 系统应用 —— ART 的三类"客户"
- 五大核心能力（字节码执行 / GC / 类加载 / 线程 / JNI）的稳定性映射
- ART 源码目录结构（`art/` 下 12 个核心子目录）

### 01-字节码与指令集：Dex 文件的骨骼

- Dex vs Class 的本质区别
- Dex 文件结构（Header / StringIDs / TypeIDs / ProtoIDs / FieldIDs / MethodIDs / ClassDefs / Data Section）
- CodeItem 与方法体（`registers_size_` / `ins_size_` / `insns_[]`）
- Dalvik 指令集（数据移动 / 算术 / 对象操作 / 五种 invoke / 控制流）
- 解释器执行循环（`ExecuteSwitchImpl` 的 while-switch 主循环）

### 02-编译与执行：从字节码到机器码的三条路

- 三种执行模式的全景（解释器 / JIT / AOT）
- Mterp 汇编优化 vs Switch Interpreter
- JIT 编译链路（热度计数 → 阈值 → 编译任务 → 入口替换）
- AOT 与 dex2oat 流程（OAT / Vdex / Odex / Art 四件套）
- PGO 与 Baseline Profile（Cloud Profile 下发机制）
- 蹦床机制（Trampolines）：`art_quick_*` 系列
- OSR（On-Stack Replacement）

### 03-类加载与链接：ClassNotFoundException 到 VerifyError

- Android ClassLoader 体系（BootClassLoader / PathClassLoader / DexClassLoader）
- `ClassLinker::DefineClass` 的 Native 流程
- 链接三步骤：Verify / Prepare / Resolve
- 类初始化与 `<clinit>` 触发时机
- MultiDex 与 OAT 加载策略

### 04-内存与GC：稳定性架构师的主战场（★ 本轮重点）

> 见 [`04-内存与GC/README-GC子模块.md`](04-内存与GC/README-GC子模块.md) 获取完整大纲。

9 篇深潜，涵盖：
- **01 基础理论**：可达性 / 三色标记 / 写屏障 / 读屏障 / 记忆集 / Reference 体系
- **02 Heap 与分配器**：5 Space 划分 / RosAlloc / Region-based / TLAB
- **03 CMS GC**：标记-清除 / SATB 写屏障 / 并发标记 4 阶段
- **04 CC GC**：并发复制 / 读屏障 / Region Space / Invariant
- **05 Generational CC**：分代假说 / Card Table / RSet / Young/Old
- **06 Reference 与 Finalizer**：4 种引用 / FinalizerDaemon / Cleaner
- **07 GC 调度与触发**：HeapTaskDaemon / 9 种触发原因 / Native GC / Trim
- **08 GC 与其他子系统**：JNI Critical / Zygote fork / Hook 框架 / APEX
- **09 GC 诊断与治理**：dumpsys meminfo / MAT / LeakCanary / Perfetto / 监控

### 05-JNI：Java 与 Native 的边界战争

- JavaVM 与 JNIEnv 的数据结构（JavaVMExt 进程唯一 / JNIEnvExt 线程唯一）
- 引用管理（IndirectReferenceTable，Local / Global / Weak Global）
- 关键 JNI 函数源码（FindClass / GetMethodID / CallVoidMethod / RegisterNatives）
- CheckJNI 机制
- 线程状态切换（kRunnable ↔ kNative）与 SafePoint

### 06-信号与ANR-Trace：从 SIGQUIT 到 traces.txt

- SIGQUIT 语义与 ART 的 `sigwait` 选择
- SignalCatcher 线程（创建 / 信号掩码 / 等待循环）
- ANR 完整链路（AMS 四种超时 → sendSignal(SIGQUIT) → SignalCatcher → Runtime::DumpForSigQuit）
- 线程挂起机制（SuspendAll / SafePoint 三种模式）
- Java 栈 dump 实现（StackVisitor / dex_pc → 源码行号）
- traces.txt 格式解读

### 07-启动流程：从 app_process 到第一行 Java 代码

- 从 init 到 Zygote（`init.zygote64_32.rc` / `app_process`）
- `AndroidRuntime::start()`（startVm / startReg / ZygoteInit.main）
- `Runtime::Init` 详解（12 个子系统初始化顺序）
- `Runtime::Start`（Boot Image / 守护线程 / SignalCatcher）
- `ZygoteInit.main()`（preloadClasses / preloadResources / gcAndFinalize / forkSystemServer）
- fork 后的世界（PreZygoteFork / DidForkFromZygote）
- 启动阶段稳定性风险地图

### 08-对比与演进：ART 为什么长成今天这样

- **ART 与 JVM**：指令集 / 内存管理 / 编译策略 / 类加载 / 监控工具的全面对比
- **Mainline 与 APEX**：ART 从固件剥离为 APEX 模块的演进
- **Hook 框架与 ART**：Epic / SandHook / Pine 的实现原理 + CC GC 读屏障的全面影响
- **监控与诊断基础设施**：JVMTI 能力边界 / ART Method Hook 三种流派 / Systrace & Perfetto 埋点

---

## 跨系列引用

ART 系列在写作时会引用：

| 引用系列 | 引用主题 | 引用方式 |
|:---|:---|:---|
| **Linux_Kernel / Process** | 进程创建 / fork / 信号 | 跨进程机制 |
| **Linux_Kernel / Memory_Management** | 虚拟内存 / VMA / 伙伴系统 | 堆的物理基础 |
| **Linux_Kernel / FS** | 文件系统 / mmap | Dex / OAT 文件加载 |
| **Linux_Kernel / Binder** | Binder 跨进程 | ART Service 通信 |
| **Android_Framework / AMS** | ANR 检测 / 进程管理 | 启动流程 / ANR 链路 |
| **Runtime / Native_Crash** | Native 信号 / Tombstone | 与 ART Java 异常的边界 |
| **App** | App 层实践 | 真实案例背景 |

ART 系列**不重复**上述系列已覆盖的内容，引用时通过 Markdown 链接跳转。

---

## 阅读建议

### 时间有限，按排查场景读

| 你要排查的问题 | 推荐阅读路径 |
|:---|:---|
| **OOM** | 04-GC（全部 9 篇）+ 08-对比与演进 |
| **ANR** | 06-信号与ANR-Trace + 02-编译与执行（解释器） + 04-GC 08 横切（GC 阻塞主线程） |
| **冷启动慢** | 07-启动流程 + 02-编译与执行（PGO / Baseline） + 04-GC（启动期 GC） |
| **Hook 崩溃** | 08-对比与演进（Hook 框架篇） + 04-GC 04（CC GC 读屏障） + 05-JNI |
| **内存泄漏** | 04-GC 01（可达性） + 04-GC 06（Reference） + 04-GC 09（LeakCanary） |
| **GC 卡顿** | 04-GC 01-05（基础理论 + 算法） + 04-GC 07（调度） + 04-GC 08（与 JNI Critical） |

### 系统学习，按子模块读

按编号顺序 00 → 08。每个子模块内部按"基础 → 机制 → 演进 → 交互 → 治理"的逻辑展开。

### 每篇文章的设计逻辑

```
背景与定义（是什么、为什么需要它）
    → 架构与交互（在系统中的位置、上下游依赖）
        → 核心机制与源码（关键数据结构、核心流程、源码走读）
            → 风险地图（这个机制会在哪些场景下出问题）
                → 实战案例（1-2 个线上问题的完整排查过程）
                    → 总结（架构师视角的关键 Takeaway）
                        → 附录 A 源码索引 / B 路径对账 / C 量化自检 / D 工程基线
```

---

## 技术基线

- **版本基线**：AOSP `android-14.0.0_r1` 为主线；Linux 内核涉及 GKI `5.10/5.15/6.1/6.6` 多版本矩阵
- **源码路径**：每段源码标注 AOSP / 内核路径 + 版本基线，文末附路径对账表
- **工程参数**：涉及可调参数给出工程默认值表
- **案例可验证**：含 logcat / dmesg / systrace 片段 + Android+内核版本 + 复现步骤 + 修复 diff
- **本篇定位**：每篇开头声明系列角色、强依赖、衔接、不重复内容

---

## 当前进度

| 子模块 | 状态 | 完成日期 |
|:---|:---:|:---:|
| **00-总览** | **✓ 完稿** | **2026-06-26** |
| **01-字节码与指令集** | **✓ 完稿** | **2026-06-26** |
| **02-编译与执行** | **✓ 完稿** | **2026-06-26** |
| **03-类加载与链接** | **✓ 完稿** | **2026-06-26** |
| **04-内存与GC** | **✓ 完稿** | **2026-06-22** |
| **05-JNI** | **✓ 完稿** | **2026-06-26** |
| **06-信号与ANR-Trace** | **✓ 完稿** | **2026-06-26** |
| **07-启动流程** | **✓ 完稿** | **2026-06-26** |
| **08-对比与演进** | **✓ 完稿** | **2026-06-26** |

> 旧版 10 篇已归档至 `_archive/`，仅作历史参考。

---

### 本轮新增文章清单

| 文章 | 行数 | 核心主题 |
|:---|---:|:---|
| 00-总览/01-ART总览 | 668 | 全局观、ART 在 Android 分层中的位置、5 大核心能力 |
| 01-字节码/01-Dex与指令集 | 639 | Dex 文件结构、Dalvik 指令集、解释器循环 |
| 02-编译/01-编译路径全景 | 510+ | 解释器/JIT/AOT 三种执行模式、dex2oat、PGO |
| 03-类加载/01-类加载完整流程 | 640 | ClassLoader / ClassLinker / Verify / Resolve |
| 05-JNI/01-JNI完整解析 | 731 | JavaVM / JNIEnv / 引用管理 / CheckJNI |
| 06-信号/01-SignalCatcher | 532 | SIGQUIT / SignalCatcher 线程 / 信号掩码 |
| 06-信号/02-ANR_Trace完整链路 | 536 | AMS → SIGQUIT → traces.txt 全链路 |
| 07-启动/01-app_process到第一行Java | 791 | Zygote 启动全流程 12 步 |
| 08-对比/01-ART_vs_JVM | 518 | 5 维设计哲学对比 |
| 08-对比/02-Mainline与APEX | 540 | Mainline 演进、APEX 挂载、独立更新机制 |
| 08-对比/03-Hook框架与ART | 500 | Epic/SandHook/Frida、CC GC 读屏障影响 |
| 08-对比/04-监控与诊断 | 545 | JVMTI/Perfetto/Simpleperf/字节码插桩 |

---

**全系列完稿**。下一篇（不在本系列内）：[Linux_Kernel/Memory_Management](../01-Mechanism/Kernel/Memory_Management/) —— 堆的物理基础。
