# L00 · Android 稳定性架构师学习路线：从 0 到胜任的 4 层栈阅读路径

> **系列**：Stability 系列 · 横切文档（与 S00-S07 并列，编号 L00 以"路线 = Learning"区别）
>
> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18` LTS
>
> **目标读者**：资浅 → 资深 Android 稳定性架构师 / 性能架构师
>
> **完成时间**：2026-07-18（v1.0）

---

# 本篇定位

- **本篇系列角色**：**横切路线图**（Stability 系列的伴生文档，不属于 S00-S07 主线）
- **强依赖**：
  - 阅读前**先读** [S00-稳定性症状总览](S00-症状总览.md)（7 大症状的边界立住后再看路线更顺）
  - 也可独立阅读（本篇会自包含所有引用）
- **承接自**：[README-Stability系列.md](../README.md) §0 系列总定位
- **衔接去**：
  - **上层为主**：[S01-S07 症状学](#stability-系列-s00-s07) + [Phase 1 机制学](#phase-2机制学--4-层栈核心子系统) 上半部
  - **需要深挖下层时**：[Phase 4 下层根因](#phase-4按需深挖下层稳定性的根因)
  - **配套质量评估**：[README-系列质量评估报告.md](README-系列质量评估报告.md)（告诉你哪些系列"还不够格"）
- **不重复内容**：
  - **不重复** [Reference/术语表.md](../../Reference/术语表.md) §1.1 防混淆口诀
  - **不重复** S00 §3 7 大症状严格定义 + §4 cascade 链路
  - **不重复** S00 §6 全局排查体系
- **本篇贡献**：把"上层稳定性为主"的阅读顺序、4 阶段路线、5 个关键交叉点、3 个角色差异化路径**全部立住**

---

# 校准决策日志

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|:-----|:-----|:-----|:-----|:---------|
| 1 | 结构 | 单篇 600+ 行（v4 默认 300 行） | §9 破例：横切路线图需覆盖 4 阶段 × 3 角色 + 速查表 | 全文 |
| 1 | 结构 | 图表 4 张（路线总图 / 阶段时序 / 5 交叉点 / 角色路径） | 路线类文档必须可视化 | 全文 |
| 2 | 硬伤 | 每个推荐必带"最低优先级"（⭐必读 / 选读 / 加餐） | 防止读者被 110+ 篇文章淹没 | Phase 1-4 全部 |
| 2 | 硬伤 | 每条路径给"时间预估" | 让读者能排日程 | 3 个角色路径 |
| 3 | 锐度 | 删"建议""可以"等空话，改"必须 / 选读 / 加餐" | 反例 #5 模糊量化 | Phase 1-4 全部 |
| 3 | 锐度 | 每个数据后加"所以呢"（如 ~110 篇 = 4 个月业余读完） | 反例 #11 数据堆砌 | 阅读量预估段 |

---

# 1. 阅读哲学（先对齐，再开读）

整个稳知库按 **3 个视角**组织，你得先知道自己在哪条线上：

| 视角 | 表达 | 代表系列 | 用途 |
|:-----|:-----|:---------|:-----|
| **症状视角** | "线上看到 X，问题在哪" | **Stability（S00-S07）** + **Native_Crash** + **Handler** 7 风险 | 排查速查 |
| **机制视角** | "X 模块内部怎么工作" | Watchdog / Process / Input / Binder / ART | 深度理解 |
| **工具视角** | "怎么抓 dump、怎么量化" | Perfetto / Hprof / AmCommand | 取证落地 |

> **铁律**：症状视角是入口，机制视角是根基，工具视角是手段。**三者必须打通**——只懂症状没有机制就只能 copy-paste 修复，只懂机制不懂症状就解决不了"线上用户报"。
>
> **所以呢**：本路线图 = 症状（S00-S07）+ 机制（Phase 2）+ 工具（Phase 3）的**有序排列**，让你**按图索骥**。

---

# 2. 上层稳定性为主 · 4 阶段路线图

## 总览图

```
                          ┌──────────────────────────────────┐
                          │  你的目标：稳定性架构师 / 性能架构师   │
                          └──────────────────────────────────┘
                                          │
       ┌──────────────────┬───────────────┼───────────────┬──────────────────┐
       ▼                  ▼               ▼               ▼                  ▼
  Phase 0             Phase 1           Phase 2          Phase 3            Phase 4
  全局观              症状学             机制学            工具学            下层深挖
  (2-3h)              (10-15h)          (25-35h)         (10-15h)          (20-30h)
       │                  │               │               │                  │
       │ 4 层栈基础       │ 7 大症状        │ 4 核心子系统    │ 5 类工具          │ 5 类下层根因
       │ + 12 时点        │ + 速查入口      │ + 状态机源码    │ + dump 取证       │ + Kernel/Native
       ▼                  ▼               ▼               ▼                  ▼
  Process 01/08     Stability S00-S07   Watchdog         Perfetto            Binder
  + 术语表          + ANR_Detection     Handler          Hprof               MM_v2
                                          Input           Dumpsys             IO/FS
                                          Native_Crash    AmCommand           epoll
                                          ART(选读)                            Input_Driver
                                          Process(选读)                        AI_Native(选读)
```

## 时序建议

```
第 1-2 周     ████████░░░░░░░░░░░░░░░░░░░  Phase 0（2-3h）+ Phase 1（10-15h）
第 3-6 周     ░░░░░░░░░░████████░░░░░░░░░  Phase 2 上半：Watchdog + Handler + Input
第 7-10 周    ░░░░░░░░░░░░░░░░░░████████░░  Phase 2 下半：Native_Crash + ART + Process
第 11-12 周   ░░░░░░░░░░░░░░░░░░░░░░░░████  Phase 3：Perfetto + Hprof + Dumpsys + AmCommand
第 13 周+     按需深挖                  Phase 4（按症状 / 按场景触发）
```

---

## 📍 Phase 0：建立 4 层栈全局观（2-3 小时）— 必读

> **目标**：把 4 层栈（App / Framework / ART / Kernel）在脑子里画出来，所有后续文章都能定位到具体层。

| 顺序 | 文章 | 为什么放第一位 |
|:-----|:-----|:---------------|
| 1 | [Process/01-进程总览](../Process/01-进程总览：从点图标看app进程的诞生消亡与全栈抽象.md) | 12 个时间点 × 4 层 = 一张图读懂所有稳定性问题都跑在这条链上 |
| 2 | [Process/08-进程稳定性风险全景](../Process/08-进程稳定性风险全景与跨层治理.md) | 4 层风险矩阵 + 24+ 监控指标 + 7 类治理动作（**上层稳定的总览**） |
| 3 | [Reference/术语表.md](../../Reference/术语表.md) §1.1（防混淆口诀） | 4 行口诀背下来：ANR 主动 / HANG 被动、SWT 杀 SystemServer / ANR 杀 App、NE 用户态 / KE 内核态、REBOOT 是结果 |

> **阶段产出**：能对任何稳定性问题说出"它在 4 层栈的哪一层、由哪个子系统负责、超时阈值是什么"。
>
> **所以呢**：跳过 Phase 0 直接读 S00+ 是可以的，但你会在"为什么这层调这层"上反复卡住——这两篇是"基础设施"，性价比最高。

---

## 📍 Phase 1：症状学 · 7 类问题全分类（10-15 小时）— 必读

> **目标**：把 7 大症状（ANR/JE/NE/SWT/HANG/REBOOT/KE）的边界、检测点、dump 取证链路全部打通。  
> **这是稳定性架构师的核心能力**——看到症状就能在 30 秒内归类。

### 1.1 总览先行

| 顺序 | 文章 | 核心抓手 |
|:-----|:-----|:---------|
| 1 | **[S00-稳定性症状总览](S00-症状总览.md)**（✅ 已完成，2026-07-18） | 7 大症状严格定义 + 系统栈映射 + cascade 链路 + 速查表 |

> S00 已写完（46KB / 800+ 行），先精读 §3 边界 + §4 cascade + §6 排查体系。

### 1.2 按"症状易混淆对"成对读

> Stability 系列的核心教学法：**不按字母序读，按混淆度读**。

| 对子 | 必读顺序 | 速读节奏 | 原因 |
|:-----|:---------|:---------|:-----|
| **ANR vs HANG** | S01 → S05 | 必读 + 深读 | 上层最高频 + 最高混淆度，**HANG 是 Stability 独占视角** |
| **崩溃三件套** | S02 JE → S03 NE → S07 KE | 必读 | 3 种空间（用户态 Java / 用户态 Native / 内核态）的崩溃差异 |
| **结果态** | S04 SWT → S06 REBOOT | 必读 | SWT 是过程，REBOOT 是结果——REBOOT 反复=治理没闭环 |

### 1.3 单症状深读的"3 步走"模板

> 读每一篇 Stability 文章时，按这个模板对照：

```
Step 1：先看 §0 本篇定位 + §1 角色设定（建立"这篇要讲什么"的预期）
Step 2：跳到 §2 边界（防混淆对表）+ §3 机制（深挖源码）
Step 3：跳到 §5 治理（dump 取证 + 修复模式）——这才是线上真正要用的
```

### 1.4 ANR 专项 · 必须钻透（最高频 P0 工单）

> ANR 是线上 **80% 的 P0 工单**来源，必须三系列联读：

| 系列 | 文章 | 角度 |
|:-----|:-----|:-----|
| **Stability** | S01 ANR（症状视角） | 4 类 ANR 的症状区分 |
| **ANR_Detection** | [Input_Dispatch_Timeout_ANR_Deep_Dive](../ANR_Detection/Input_Dispatch_Timeout_ANR_Deep_Dive.md) | Input ANR 检测链路源码深挖 |
| **ANR_Detection** | [Service_ANR_Deep_Dive](../ANR_Detection/Service_ANR_Deep_Dive.md) | Service ANR 阈值与机制 |
| **ANR_Detection** | [No_Focus_Window_ANR_Deep_Dive](../ANR_Detection/No_Focus_Window_ANR_Deep_Dive.md) | No Focus 异常路径 |
| **Input** | [Input/06-InputANR](../Input/06-InputANR.md) + [07-Input稳定性风险全景](../Input/07-Input稳定性风险全景.md) | Input ANR 全景 + 治理 |
| **App/Handler** | [06-Handler与ANR](../01-Mechanism/App/Handler-MessageQueue-Looper/06-Handler与ANR.md) | App 侧主线程为什么会卡 |

> **建议读法**：先 Stability S01（症状入口）→ 再挑一类（Input / Service / Broadcast）钻深。
>
> **所以呢**：3 篇 ANR_Detection 是**最小必读集合**——S01 是"症状视角"，这 3 篇是"机制视角"，缺一不可。

---

## 📍 Phase 2：机制学 · 4 层栈核心子系统（25-35 小时）— 必读

> **目标**：把 4 个核心子系统的内部状态机吃透——稳定性问题的根因都在这 4 个里。

### 2.1 推荐顺序（按"出现频次 × 上层依赖度"排）

```
① Watchdog（必读）   → ② Handler（必读）  → ③ Input（必读）
   │                      │                     │
   └─ SWT 杀 SystemServer  └─ 主线程卡死的根因      └─ 5s Input ANR 链路
   │                      │                     │
   ↓                      ↓                     ↓
④ Native_Crash（必读） → ⑤ ART（按需深读）  → ⑥ Process（按需深读）
   │                      │                     │
   └─ NE 6 种信号         └─ GC / 类加载 / 信号    └─ Zygote / cgroup / 调度
       + tombstone
```

### 2.2 每个子系统的"最低必读"清单

#### 🛡️ Watchdog（6 篇，~7 小时）

| 优先级 | 文章 | 原因 |
|:------|:-----|:-----|
| **⭐ 必读** | [01-概述与体系位置](../Watchdog/01-Watchdog概述与体系位置.md) | 多层 watchdog 全景 |
| **⭐ 必读** | [03-Java-Watchdog核心机制](../Watchdog/03-Java-Watchdog核心机制.md) | HandlerChecker 状态机 |
| **⭐ 必读** | [05-超时判定与杀进程链路](../Watchdog/05-Watchdog超时判定与杀进程链路.md) | 杀进程策略三层（线程 → SystemServer → 整机） |
| **⭐ 必读** | [06-实战案例与排查体系](../Watchdog/06-Watchdog实战案例与排查体系.md) | 真实 logcat + 修复模式 |
| 选读 | [02-多层Watchdog架构](../Watchdog/02-多层Watchdog架构.md) | 内核 watchdog 联动 |
| 选读 | [04-内核Watchdog与watchdogd](../Watchdog/04-内核Watchdog与watchdogd.md) | 软/硬死锁检测 |
| **加餐（必读）** | [BinderStarve.md](../Watchdog/BinderStarve.md)（177KB） | Binder 饿死导致 SWT 的全栈分析——**稳定性架构师王牌案例** |

#### ⚙️ Handler / MessageQueue / Looper（8 篇，~6 小时）

| 优先级 | 文章 | 原因 |
|:------|:-----|:-----|
| **⭐ 必读** | [01-Handler消息机制总览](../01-Mechanism/App/Handler-MessageQueue-Looper/01-Handler消息机制总览.md) | 主线程模型的"心脏" |
| **⭐ 必读** | [02-Looper与线程模型](../01-Mechanism/App/Handler-MessageQueue-Looper/02-Looper与线程模型.md) | 线程消息循环 |
| **⭐ 必读** | [05-同步屏障与异步消息](../01-Mechanism/App/Handler-MessageQueue-Looper/05-同步屏障与异步消息.md) | 同步屏障卡死的经典坑 |
| **⭐ 必读** | [06-Handler与ANR](../01-Mechanism/App/Handler-MessageQueue-Looper/06-Handler与ANR.md) | ANR 的主线程根因 |
| **⭐ 必读** | [07-Handler稳定性风险全景](../01-Mechanism/App/Handler-MessageQueue-Looper/07-Handler稳定性风险全景.md) | 11 类风险全梳理 |
| 选读 | [08-诊断工具与监控体系](../01-Mechanism/App/Handler-MessageQueue-Looper/08-消息机制诊断工具与监控体系.md) | LooperPrinter 监控方案 |
| 加餐 | [HandlerThread泄露分析与防治](../01-Mechanism/App/Handler-MessageQueue-Looper/HandlerThread泄露分析与防治.md) | 实战案例 |
| 加餐 | [LooperPrinter是否需要监控？](../01-Mechanism/App/Handler-MessageQueue-Looper/LooperPrinter是否需要监控？.md) | 决策依据 |

#### 🎯 Input（8 篇，~8 小时）

| 优先级 | 文章 | 原因 |
|:------|:-----|:-----|
| **⭐ 必读** | [01-Input系统总览](../Input/01-Input系统总览.md) | 触摸从驱动到 View 的完整链路 |
| **⭐ 必读** | [03-InputDispatcher](../Input/03-InputDispatcher.md) | **5s Input ANR 的核心调度器** |
| **⭐ 必读** | [06-InputANR](../Input/06-InputANR.md) | 5s ANR 触发条件 + 判定逻辑 |
| **⭐ 必读** | [07-Input稳定性风险全景](../Input/07-Input稳定性风险全景.md) | 11 类风险 |
| 选读 | [02-EventHub与InputReader](../Input/02-EventHub与InputReader.md) | 内核 → Framework 边界 |
| 选读 | [04-InputChannel与跨进程投递](../Input/04-InputChannel与跨进程投递.md) | 跨进程链路 |
| 选读 | [05-View事件分发](../Input/05-View事件分发.md) | 客户端分发 |
| 选读 | [08-诊断工具与延迟治理体系](../Input/08-诊断工具与延迟治理体系.md) | 工具链 |

#### 💥 Native_Crash（8 篇，~8 小时）

| 优先级 | 文章 | 原因 |
|:------|:-----|:-----|
| **⭐ 必读** | [01-NativeCrash总览](../01-Mechanism/Runtime/Native_Crash/01-NativeCrash总览.md) | debuggerd 入口 |
| **⭐ 必读** | [02-Linux信号机制](../01-Mechanism/Runtime/Native_Crash/02-Linux信号机制.md) | 6 种致命信号根因 |
| **⭐ 必读** | [04-debuggerd与Tombstone](../01-Mechanism/Runtime/Native_Crash/04-debuggerd与Tombstone.md) | tombstone 抓取链路 |
| **⭐ 必读** | [06-Tombstone深度解读](../01-Mechanism/Runtime/Native_Crash/06-Tombstone深度解读.md) | 16 段结构怎么读 |
| **⭐ 必读** | [08-APM集成与治理](../01-Mechanism/Runtime/Native_Crash/08-APM集成与治理.md) | 监控落地 |
| 选读 | [03-内存管理与保护](../01-Mechanism/Runtime/Native_Crash/03-内存管理与保护.md) | 内存越界原理 |
| 选读 | [05-栈回溯与符号化](../01-Mechanism/Runtime/Native_Crash/05-栈回溯与符号化.md) | unwinding |
| 选读 | [07-检测工具体系](../01-Mechanism/Runtime/Native_Crash/07-检测工具体系.md) | asan / fuzzer / 内存检测 |

#### 🧠 ART（按需深读，~10-15 小时）

> ART 是性能 + 内存稳定的根因层，**不一定要全部读，按症状定位**：

| 场景 | 必读 |
|:-----|:-----|
| **GC 问题 / OOM** | [03-GC系统/01-基础理论](../01-Mechanism/Runtime/ART/03-GC系统/01-基础理论/) 全部 + [02-Heap与分配器](../01-Mechanism/Runtime/ART/03-GC系统/02-Heap与分配器/) 全部 + [05-Generational-CC](../01-Mechanism/Runtime/ART/03-GC系统/05-Generational-CC/) 全部 + [09-GC诊断与治理](../01-Mechanism/Runtime/ART/03-GC系统/09-GC诊断与治理/) 全部 |
| **启动慢** | [07-启动流程](../01-Mechanism/Runtime/ART/07-启动流程/) 全部 + [02-编译与执行](../01-Mechanism/Runtime/ART/02-编译与执行/) 全部 |
| **JNI 崩溃** | [05-JNI](../01-Mechanism/Runtime/ART/05-JNI/) 全部 + [01-字节码与指令集](../01-Mechanism/Runtime/ART/01-字节码与指令集/) 全部 |
| **ANR 信号链路** | [06-信号与ANR-Trace](../01-Mechanism/Runtime/ART/06-信号与ANR-Trace/) 全部 |
| **类加载 / NoClassDefFoundError** | [03-类加载与链接](../01-Mechanism/Runtime/ART/03-类加载与链接/) 全部 |

#### ⚙️ Process（按需深读，~6-8 小时）

| 场景 | 必读 |
|:-----|:-----|
| **冷启动慢** | [01](../Process/01-进程总览：从点图标看app进程的诞生消亡与全栈抽象.md) + [02](../Process/02-AMS-冷启动判定与进程启动链路.md) + [03](../Process/03-Zygote-Android进程工厂.md) + [04](../Process/04-应用进程首生-fork到ActivityThread.md) |
| **OOM / lmkd** | [06-Framework视角的Kernel进程接口](../Process/06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd.md) §9.1 + [07-调度与资源](../Process/07-调度与资源：CFS与进程生死.md) |
| **进程死 / crash 重启** | [08-进程稳定性风险全景](../Process/08-进程稳定性风险全景与跨层治理.md) |

---

## 📍 Phase 3：工具学 · 取证与治理闭环（10-15 小时）— 必读

> **目标**：**线上拿到 bugreport / ANR traces / tombstone，能在 1 小时内定位到根因**。  
> 工具是稳定性的"手术刀"——不懂工具的架构师只能纸上谈兵。

| 工具 | 必读 | 用途 |
|:-----|:-----|:-----|
| **Perfetto** | [Perfetto 系列 5 篇](../Perfetto/) | 抓全栈 trace，**性能 + 稳定性通用** |
| **Hprof** | [Hprof 系列 5 篇](../Hprof/) | Java 堆 dump + LeakCanary 原理 |
| **Dumpsys** | ⚠️ **质量不足**（详见 [质量评估报告](README-系列质量评估报告.md#dumpsys)） | 100+ dumpsys 命令按子系统分类——**当前内容严重不够** |
| **AmCommand** | [AmCommand 系列 6 篇 + scripts](../AmCommand/) | 进程 / Activity / Intent 调试 |
| **AmCommand scripts** | [scripts/](../AmCommand/scripts/) | 可直接运行的批处理脚本 |
| **Perfetto scripts** | [perfetto_configs/](../Perfetto/perfetto_configs/) + [trace_analysis_sql/](../Perfetto/trace_analysis_sql/) | 配置 + SQL 分析模板 |
| **Hprof scripts** | [hprof_configs/](../Hprof/hprof_configs/) + [trace_analysis_sql/](../Hprof/trace_analysis_sql/) | dump 分析模板 |

> **必杀器**：Phase 3 完成后，你能在 1 小时内完成"症状 → 工具 → dump → 根因 → 修复"全链路。
>
> **所以呢**：**Dumpsys 是当前最大的质量缺口**——Phase 3 必读清单里只有它"不合格"。建议优先补 Dumpsys 系列，再走完 Phase 3。

---

## 📍 Phase 4（按需深挖）：下层稳定性的根因

> **上层稳定性的根因 80% 在下层**——但作为架构师，要按需钻深。

| 场景 | 必读 |
|:-----|:-----|
| **Binder hang / 饿死** | [Linux_Kernel/Binder/05-线程模型](../01-Mechanism/Kernel/Binder/05-Binder线程模型.md) + [07-稳定性风险全景](../01-Mechanism/Kernel/Binder/07-Binder稳定性风险全景.md) + [10-oneway限流](../01-Mechanism/Kernel/Binder/10-Binder-oneway限流与防护方案.md) |
| **IO hang / 存储卡顿** | [Linux_Kernel/IO/](../01-Mechanism/Kernel/IO/) 全部 + [Linux_Kernel/FS/](../01-Mechanism/Kernel/FS/) 全部 + [Linux_Kernel/DM/](../01-Mechanism/Kernel/DM/) |
| **Kernel panic / oops** | [Linux_Kernel/Process/13-进程调试与稳定性关联](../01-Mechanism/Kernel/Process/13-进程调试与稳定性关联.md) + [Linux_Kernel/Process/11-信号机制](../01-Mechanism/Kernel/Process/11-信号机制_从产生到投递.md) |
| **内存 / OOM 链路** | [Linux_Kernel/Memory_Management/MM_v2/](../01-Mechanism/Kernel/Memory_Management/MM_v2/) 全部 |
| **epoll 死锁 / socket hang** | [Linux_Kernel/epoll/](../01-Mechanism/Kernel/epoll/) 全部 + [Linux_Kernel/socket/](../01-Mechanism/Kernel/socket/) 全部 |
| **GKI 设备驱动** | [Linux_Kernel/GKI/](../01-Mechanism/Kernel/GKI/) + [Linux_Kernel/Input_Driver/](../01-Mechanism/Kernel/Input_Driver/) |
| **端侧 AI 对 ANR/性能影响** | [AI_Native_X/01-AI_Native_Runtime](../05-Governance/AI-Native/01_AI_Native_Runtime/) + [03-AI_for_Stability](../05-Governance/AI-Native/03_AI_for_Stability/) |

---

# 3. 5 个最关键的"交叉点"（架构师必修）

> 这 5 个交叉点是**症状 + 机制 + 工具**的汇聚点，缺一不可：

| # | 交叉点 | 涉及文章 | 为什么关键 |
|:--|:-------|:---------|:----------|
| **1** | **主线程卡死 → ANR → SWT** | Handler 06 + ANR_Detection/Input + Watchdog 05 | 80% P0 工单的因果链 |
| **2** | **Binder 排队满 → 饿死 → ANR** | Binder 05/07/10 + Watchdog/BinderStarve | 高频 OEM 治理重点 |
| **3** | **GC 频繁 → 性能退化 → ANR** | ART 03-GC 全部 + Process 06-07 + Perfetto | 性能架构师最该懂的链 |
| **4** | **内存泄漏 → OOM → 进程死 → 拉起慢** | ART 09-GC诊断 + Hprof 全部 + Process 02/04 | OOM 是性能 + 稳定性双跨 |
| **5** | **Native 崩溃 → debuggerd → tombstone** | Native_Crash 全部 + Stability S03 + ART 06（SignalCatcher） | NE 全栈取证链路 |

> **所以呢**：把这 5 个交叉点**各自手画一张时序图**画出来，你就能讲清楚"线上问题是怎么发生的"——这是面试稳定性架构师 JD 的必问题。

---

# 4. 3 个角色的差异化路径

## 🎯 角色 A：稳定性架构师 · 入门到胜任（~40 小时，3-4 周）

> **适用**：刚接手稳定性 P0 工单 owner / 准备跳槽稳定性架构岗

```
Phase 0（必读，2-3h）
  → Process/01 → Process/08 → Reference 术语表

Phase 1（必读，10-15h）
  → S00（已写完 800+ 行）→ S01 ANR → S05 HANG
  → S02 JE → S03 NE → S07 KE → S04 SWT → S06 REBOOT
  → ANR_Detection 全部 3 篇（Input + Service + No Focus）

Phase 2 核心四件套（必读，~25h）
  → Watchdog 必读 4 篇 + BinderStarve 加餐
  → Handler 必读 5 篇
  → Input 必读 4 篇
  → Native_Crash 必读 5 篇
  → ART 按需挑 GC / 类加载 / 信号

Phase 3 工具学（必读，~10h）
  → Perfetto 全部 → Hprof 全部 → Dumpsys 全部（⚠️ 需补全）→ AmCommand 全部
```

## 🎯 角色 B：性能架构师 · 入门到胜任（~30 小时，2-3 周）

> **适用**：性能优化 owner / 启动 / 内存 / 流畅度专项

```
Phase 0（必读，2-3h）+ Phase 1 跳过 S04/S06 → Phase 2 偏 ART/Process
  → ART 03-GC系统 全部（性能根因）→ ART 07-启动流程 全部
  → Process 01-04（冷启动）→ Process 06-07（调度/资源）
  → Perfetto 系列（性能 trace 必杀器）→ AmCommand 性能命令
  → Performance monitoring: Hprof 内存 + Dumpsys gfxinfo/cpuinfo
```

## 🎯 角色 C：正在追某个线上问题（应急模式，2-4 小时）

> **适用**：当前 P0 工单 owner / 凌晨 3 点被叫醒

```
症状速查路径（按看到的问题直接跳）：
  ├─ 弹"应用无响应" → S01 ANR + ANR_Detection/Input_Dispatch_Timeout + Handler 06
  ├─ Crash 弹窗 → S02 JE
  ├─ tombstone 文件 → S03 NE + Native_Crash 04/06
  ├─ 系统反复重启 → S06 REBOOT + Watchdog 05
  ├─ last_kmsg 异常 → S07 KE + Linux_Kernel/Process 13
  ├─ 用户报"卡"无 ANR → S05 HANG（重点看 §2 决策树）
  └─ 杀 SystemServer → S04 SWT + Watchdog 05
```

## 🎯 角色 D（加餐）：面试 Android 稳定性架构师 JD（2 周冲刺，~50 小时）

```
全套必读 + 加餐：
  Phase 0 + 1 + 2 全部 + 3 全部
  + Process 8 篇（跨层贯通）
  + Binder 7 篇（最高频被问）
  + ART GC 系列（OOM 必问）
  + Stability S00-S07 全部（这个系列是 JD 命中率最高的）
  + AI_Native_X/03-AI_for_Stability（2026 年新方向）
  + Hook 系列 15 篇（OEM BSP 经验加分项）
```

---

# 5. 阅读量预估

| 阶段 | 文章数 | 字数 | 时间 | 难度 |
|:-----|:------:|:----:|:----:|:----:|
| Phase 0 | 3 | ~3 万字 | 2-3 h | ⭐⭐ |
| Phase 1（症状学） | ~20 | ~30 万字 | 10-15 h | ⭐⭐⭐ |
| Phase 2（机制学） | ~30 | ~50 万字 | 25-35 h | ⭐⭐⭐⭐ |
| Phase 3（工具学） | ~20 | ~20 万字 | 10-15 h | ⭐⭐⭐ |
| Phase 4（按需） | ~40 | ~70 万字 | 20-30 h | ⭐⭐⭐⭐⭐ |
| **合计** | **~110** | **~170 万字** | **~70-100 h** | — |

> 按每天 2-3 小时业余读，**3-4 个月能吃透上层稳定性核心 + 大半下层**。  
> 按工作日集中 6-8 小时，**2-3 周能完成角色 A 路径**。

---

# 6. 总结

## 6.1 核心要诀（背下来）

1. **症状入口 → 机制根基 → 工具手段**：三者缺一不可，但**入口是症状**
2. **4 层栈贯穿**：所有问题都在 App / Framework / ART / Kernel 4 层中穿行
3. **5 个交叉点**：主线程卡死 / Binder 饿死 / GC 退化 / 内存泄漏 / NE 崩溃——这是面试必问
4. **4 阶段路线**：全局观 → 症状学 → 机制学 → 工具学，**不要跳阶段**
5. **4 个 8 篇**：Stability 8 篇 + Process 8 篇 + Handler 8 篇 + Native_Crash 8 篇 = **32 篇 = 你的能力矩阵**

## 6.2 给你（架构师）的额外建议

1. **别贪多，先打通一条线**——建议先走**角色 A 路径**（稳定性架构师主线），别的角色都从这条线衍生。
2. **Stability S00-S07 是核心资产**——优先写完它，整个库就形成了"症状 → 机制 → 工具"的三向交叉引用。
3. **质量评估先行**——开始阅读前先看 [README-系列质量评估报告.md](README-系列质量评估报告.md)，避免读到"质量不足"的系列浪费时间。
4. **Dumpsys 系列是最大缺口**——Phase 3 必读里只有它不合格，**建议优先补完**（补完后整个库的工具链才算闭环）。
5. **AI_Native_X/03-AI_for_Stability 是 2026 年新方向**——稳定性架构师 + AI 治理 = 简历稀缺项，建议加进 Phase 4 选读。
6. **dump 案例库（Stability 16 个案例）优先补齐**——架构师面试最有说服力的就是"我解过这个 bug，定位链路是 X Y Z"。

---

# 7. 附录 A · 速查表（按症状直接跳）

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

# 8. 附录 B · 引用对账表

| 本路线图引用 | 实际路径 | 状态 |
|:------------|:---------|:-----|
| Process/01-进程总览 | `Android_Framework/Process/01-进程总览：从点图标看app进程的诞生消亡与全栈抽象.md` | ✅ 存在 |
| Process/08-进程稳定性风险全景 | `Android_Framework/Process/08-进程稳定性风险全景与跨层治理.md` | ✅ 存在 |
| Watchdog/01-概述 | `Android_Framework/Watchdog/01-Watchdog概述与体系位置.md` | ✅ 存在 |
| Watchdog/BinderStarve.md | `Android_Framework/Watchdog/BinderStarve.md` | ✅ 存在（177KB 加餐） |
| Handler/06-Handler与ANR | `App/Handler_MessageQueue_Looper/06-Handler与ANR.md` | ✅ 存在 |
| Input/06-InputANR | `Android_Framework/Input/06-InputANR.md` | ✅ 存在 |
| Native_Crash/01-NativeCrash总览 | `Runtime/Native_Crash/01-NativeCrash总览.md` | ✅ 存在 |
| ANR_Detection/Input_Dispatch_Timeout | `Android_Framework/ANR_Detection/Input_Dispatch_Timeout_ANR_Deep_Dive.md` | ✅ 存在 |
| Stability S00 | `Android_Framework/Stability/S00-稳定性症状总览.md` | ✅ 已完成 |
| Stability S01-S07 | `Android_Framework/Stability/S0X-*.md` | 🚧 撰写中（README 规划 8 篇） |
| Stability 跨系列引用矩阵 | `Reference/Stability-跨系列引用矩阵.md` | ✅ 存在 |
| Stability 案例索引 | `Reference/Stability-案例索引.md` | ✅ 存在 |
| Reference 术语表 | `Reference/术语表.md` | ✅ 存在 |
| Perfetto 系列 | `Android_Framework/Perfetto/` 5 篇 | ✅ 存在 |
| Hprof 系列 | `Android_Framework/Hprof/` 5 篇 | ✅ 存在 |
| AmCommand 系列 | `Android_Framework/AmCommand/` 6 篇 | ✅ 存在 |
| **Dumpsys 系列** | `Android_Framework/Dumpsys/` **2 篇（质量不足）** | ⚠️ 需补全 |
| Linux_Kernel/Binder | `Linux_Kernel/Binder/` 12 篇 | ✅ 存在 |
| Linux_Kernel/IO | `Linux_Kernel/IO/` 11 篇 | ✅ 存在 |
| Linux_Kernel/FS | `Linux_Kernel/FS/` 20 篇 | ✅ 存在 |
| Linux_Kernel/Process | `Linux_Kernel/Process/` 13 篇 + Stability_README | ✅ 存在 |
| Linux_Kernel/MM_v2 | `Linux_Kernel/Memory_Management/MM_v2/` 14 篇 | ✅ 存在 |
| Linux_Kernel/epoll | `Linux_Kernel/epoll/` 2 篇 | ✅ 存在（简短但精） |
| Linux_Kernel/socket | `Linux_Kernel/socket/` 9 篇 | ✅ 存在 |
| AI_Native_X/01-04 | `AI_Native_X/{01,02,03,04}_*/` 4 个子系列 | ✅ 存在 |
| Hook 系列 | `Hook/` 15 篇 + README | ✅ 存在 |

---

# 9. 附录 C · 量化自检表

| 维度 | 数据 | 来源 |
|:-----|:-----|:-----|
| 仓库系列总数 | 13 个子系列 | `Android_Framework` (8) + `Runtime` (2) + `Linux_Kernel` (12) + `App` (1) + `AI_Native_X` (4) + `Hook` (1) + `Tools` (4) |
| 仓库文章总数 | **~110 篇**（含 Stability 8 篇规划中） | 当前全仓统计 |
| 总字数 | **~170 万字** | 估算（平均 ~1.5 万字/篇） |
| 全部读完 | 70-100 小时（业余） / 2-3 周（集中） | 3 角色路径测算 |
| Stability 系列 S00 | 800+ 行 / 46KB | S00 实际文件 |
| S01-S07 规划 | ~5,500-6,000 行 | README §1 |
| 最大单篇 | Watchdog/BinderStarve.md 177KB | 实测 |
| 4 个 8 篇系列 | Stability + Process + Handler + Native_Crash = 32 篇 | 仓库扫描 |
| 角色 A 路径 | ~40 小时 | 测算 |
| 角色 B 路径 | ~30 小时 | 测算 |
| 角色 C 路径 | 2-4 小时（应急） | 测算 |
| 角色 D 路径 | ~50 小时（面试冲刺） | 测算 |

---

# 10. 附录 D · 工程基线表

| 参数 | 值 | 备注 |
|:-----|:---|:-----|
| **AOSP 版本** | `android-17.0.0_r1`（API 37） | 新基线（2026-07-17 决策） |
| **Linux 内核** | `android17-6.18`（6.18 LTS） | EOL 2030-07-01 |
| **AOSP manifest 分支** | `android-latest-release` | AOSP 官方 2026+ 推荐 |
| **ART 17 关键变化** | 分代 GC 强化、无锁 MessageQueue（API 37+）、static final 不可变、AppFunctions / AI Agent OS 集成 | 写文章时主动覆盖 |
| **Linux 6.18 关键变化** | Rust Binder 上主线、sheaves 内存分配、eBPF 加密签名、exFAT 16x 加速、bcachefs 移除 | 写文章时主动覆盖 |
| **存量旧文章基线** | AOSP 14 + 5.10/5.15 现状 | 不强制升级（等单点触发） |
| **稳定性阈值（Input ANR）** | 5s | 不可调 |
| **稳定性阈值（Watchdog 周期）** | 30s | AOSP 默认 |
| **稳定性阈值（hung_task）** | 120s | `/proc/sys/kernel/hung_task_timeout_secs` |
| **稳定性阈值（softlockup）** | 20s | `/proc/sys/kernel/watchdog_thresh` |

---

# 11. 校准迭代计划（v4 §7 强制 · 占位）

| 轮次 | 类别 | 计划 | 触发条件 |
|:-----|:-----|:-----|:---------|
| 1 | 结构 | 等 S01-S07 全部写完后，回看本路线图是否漏掉新增系列 | S08（最后一篇）完成 |
| 2 | 硬伤 | 把所有"⚠️ 质量不足"链接替换为合格内容链接 | Dumpsys 等系列补完后 |
| 3 | 锐度 | 根据读者反馈砍掉"加餐"中性价比低的文章 | 收集 10+ 读者反馈 |

---

> **系列导航**：
> - **本文档**：[README-学习路线-稳定性架构师.md](README-学习路线.md)（L00）
> - **症状入口**：[S00-稳定性症状总览](S00-症状总览.md) · [README-Stability系列.md](../README.md)
> - **质量评估**：[README-系列质量评估报告.md](README-系列质量评估报告.md)
> - **机制入口**：[Process 系列](../Process/) · [Watchdog 系列](../Watchdog/) · [Handler 系列](../01-Mechanism/App/Handler-MessageQueue-Looper/)
> - **工具入口**：[Perfetto](../Perfetto/) · [Hprof](../Hprof/) · [AmCommand](../AmCommand/)
> - **下层根因**：[Linux_Kernel/Binder](../01-Mechanism/Kernel/Binder/) · [Linux_Kernel/Process](../01-Mechanism/Kernel/Process/)

---

**最后更新**：2026-07-18（v1.0，与 S00 同步落库）  
**基线**：AOSP 17 + android17-6.18  
**作者**：Mavis · Stability Matrix Course 路线图

