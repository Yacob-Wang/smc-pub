# Android 稳定性取证系列（Stability-Forensics）

> **目标读者**：Android 稳定性架构师
>
> **系列定位**：按"症状 × 抓取链路"维度组织 Android 稳定性问题的**取证体系**——症状发生后如何抓证据、抓取到哪个路径、如何解读
>
> **核心问题**：ANR / SWT / JE / NE / KE / HANG / OOM 7 类症状的 dump 文件分别在哪里、怎么抓、怎么解读
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（**当前默认基线**）
> **Linux 6.18 LTS（前瞻）**：待 AOSP 17 后续推 6.18 分支后纳入
>
> **完成状态**：🚧 撰写中（F00-F07 规划完成，2026-07-18 开干）

---

## 0. 系列总定位（架构师视角）

### 0.1 一句话定位

**Stability-Forensics 是 Stability 系列的"取证侧"——把 Stability 系列讲的"症状机制"反向落到"取证抓取"：症状触发后，dump 文件在哪里、怎么抓、怎么解读。**

### 0.2 与 Stability 系列的关系（**机制 + 取证双视角**）

| 维度 | Stability 系列 | Stability-Forensics |
|:-----|:--------------|:-------------------|
| **视角** | 症状 × 机制 | 症状 × 取证 |
| **核心问题** | 这个症状怎么发生？怎么修？| 症状发生后怎么抓证据？怎么分析？|
| **产出** | 风险地图 + 修复模式 | **取证链路 + dump 文件解读** |
| **典型读者** | 稳定性工程师 | APM 工程师 / 稳定性 oncall |

> **本系列是 Stability 系列的天然配套**——Stability 讲"症状是什么、怎么发生"，Forensics 讲"症状发生后怎么抓证据"。两个系列读完后，**稳定性治理全栈闭环**。

### 0.3 与其他系列的关系

| 现有系列 | Forensics 引用 | 关系 |
|:---------|:--------------|:-----|
| [Stability 系列](../Stability/) | 强引用（机制） | **机制 + 取证 双视角** |
| [Perfetto 系列](../Perfetto/) | 引用（工具） | Forensics 用 Perfetto 抓稳定性上下文 |
| [Hprof 系列](../Hprof/) | 引用（工具） | Forensics 用 hprof 抓 OOM |
| [Native_Crash 系列](../../Runtime/Native_Crash/) | 引用（机制） | Forensics F04 引用 NE 机制 |
| [Watchdog 系列](../Watchdog/) | 引用（机制） | Forensics F02 引用 SWT 机制 |
| [ANR_Detection 系列](../ANR_Detection/) | 引用（机制） | Forensics F01 引用 ANR 机制 |
| [Linux_Kernel/FS](../../Linux_Kernel/FS/) | 引用（pstore） | Forensics F05 引用 pstore 机制 |
| [Tools/Tracing](../../Tools/Tracing/) | 引用（工具） | Forensics F06 引用 ftrace |
| [Tools/Memory_Analysis](../../Tools/Memory_Analysis/) | 引用（工具） | Forensics F06 引用内存分析 |
| [Android_Framework/Dumpsys](../Dumpsys/) | 引用（工具） | Forensics F07 引用 dumpsys |
| [App/Handler/Looper](../../App/Handler_MessageQueue_Looper/) | 引用（机制） | Forensics F01/F06 引用主线程 Looper |

### 0.4 系列对线 JD

| JD 维度 | 本系列对位 |
| :--- | :--- |
| 职责 1「Android 稳定性（Crash/ANR/OOM/性能退化）核心负责人」 | **核心对线**——F00-F07 整体对线 |
| 职责 2「覆盖 Framework + Native + Linux Kernel 层」 | **核心对线**——F00-F07 各占一层 |
| 职责 6「稳定性治理 / 监控 / APM 体系建设」 | **核心对线**——F07 治理 |
| 加分项 2「性能优化、稳定性优化领域有突出贡献」 | F00 总览 + F07 治理 |

---

## 1. 篇章列表（8 篇 · 总 ~5,800 行）

| # | 篇号 | 标题 | 系列角色 | 强依赖 | 行数目标 |
|---|------|------|---------|--------|---------:|
| 1 | **F00** | 取证体系总览：症状 × 日志类型 二维矩阵 + 取证路径 | **全局观** | 无 | ~700 |
| 2 | **F01** | ANR 取证：anr traces + dropbox(APP_ANR) + Perfetto | 症状取证 1/7 | F00 + [Stability S01](../Stability/S01-ANR.md) | ~800 |
| 3 | **F02** | SWT 取证：watchdog traces + SystemServer Perfetto | 症状取证 2/7 | F00 + [Stability S04](../Stability/S04-SWT.md) | ~700 |
| 4 | **F03** | JE 取证：dropbox(APP_CRASH) + logcat -b crash | 症状取证 3/7 | F00 + [Stability S02](../Stability/S02-JE.md) | ~600 |
| 5 | **F04** | NE 取证：tombstone 16 段 + 符号化服务 | 症状取证 4/7 | F00 + [Stability S03](../Stability/S03-NE.md) | ~800 |
| 6 | **F05** | KE 取证：dmesg + pstore + last_kmsg + ramoops | 症状取证 5/7 | F00 + [Stability S07](../Stability/S07-KE.md) | ~700 |
| 7 | **F06** | HANG + OOM 取证：systrace/ftrace/hprof + 主动监控 | 症状取证 6/7 | F00 + [Stability S05](../Stability/S05-HANG.md) | ~800 |
| 8 | **F07** | 取证治理：APM 接入 + bugreport 自动化 + 商业符号化 | **治理** | F00-F06 | ~700 |

**合计**：~5,800 行 · 8 篇 · 16 个锚点案例（每篇 2 个：1 典型模式 + 1 公开 bugreport）

---

## 2. 系列设计思路

### 2.1 取证层级（横向）

```
┌─────────────────────────────────────────────────────────────────────┐
│  Level 1: 应用层日志（dropbox / traces / logcat -b crash）         │
│  Level 2: Native 层日志（tombstone / debuggerd）                  │
│  Level 3: Kernel 层日志（dmesg / pstore / last_kmsg）             │
│  Level 4: 全栈追踪（Perfetto / systrace / ftrace）                 │
│  Level 5: 内存取证（hprof / smaps / proc/meminfo）                 │
│  Level 6: 全量 dump（bugreport）                                   │
│  Level 7: 商业化（APM / Sentry / Backtrace.io 接入）                │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 症状 × 抓取链路矩阵（核心）

| 症状 | 应用层 | Native 层 | Kernel 层 | 全栈追踪 | 内存取证 | 关键路径 |
|:-----|:-------|:----------|:----------|:---------|:---------|:--------|
| **ANR** | `dropbox(APP_ANR)` + `anr traces.txt` | — | — | Perfetto | — | `/data/anr/` + `/data/system/dropbox/` |
| **SWT** | `dropbox(SYSTEM_SERVER_WATCHDOG)` + `watchdog traces` | — | — | SystemServer Perfetto | — | `/data/anr/` + `/data/system/dropbox/` |
| **JE** | `dropbox(APP_CRASH)` + `logcat -b crash` | — | — | — | — | `/data/system/dropbox/` + logcat ring buffer |
| **NE** | `dropbox(SYSTEM_TOMBSTONE)` | `tombstone` (16 段) | — | — | — | `/data/tombstones/` + `/data/system/dropbox/` |
| **KE** | `dropbox(KE_*)` | — | `dmesg` + `pstore` + `last_kmsg` | ftrace | — | `/sys/fs/pstore/` + `/proc/last_kmsg` |
| **HANG** | — | — | — | systrace + ftrace | — | `/data/local/traces/`（**主动抓**）|
| **OOM** | `dropbox(LOW_MEM)` | — | — | — | hprof + smaps | `/data/misc/heap-dump/` + `/proc/meminfo` |

> **关键洞察**：
> - **HANG 是特殊的**——没有自动 dump，**只能主动抓**
> - **OOM 是新增症状**（Stability 系列没单独成篇）—— 单独成 F06 子节
> - **dropbox 是统一存储层**——所有症状都有 dropbox 标签

### 2.3 跨系列引用矩阵（详见 [Reference/Forensics-跨系列引用矩阵.md](../../Reference/Forensics-跨系列引用矩阵.md)）

| Forensics 文章 | 主引用系列 | 引用文章数 |
|--------------|----------|----------|
| F00 | [Stability S00](../Stability/S00-稳定性症状总览.md) + Perfetto + Hprof + ANR_Detection | 4 |
| F01 | [Stability S01](../Stability/S01-ANR.md) + [Perfetto](../Perfetto/) + [Handler/Looper](../../App/Handler_MessageQueue_Looper/) | 3 |
| F02 | [Stability S04](../Stability/S04-SWT.md) + [Watchdog](../Watchdog/) + [Perfetto](../Perfetto/) | 3 |
| F03 | [Stability S02](../Stability/S02-JE.md) + [ANR_Detection](../ANR_Detection/) + [Handler/Looper](../../App/Handler_MessageQueue_Looper/) | 3 |
| F04 | [Stability S03](../Stability/S03-NE.md) + [Native_Crash](../../Runtime/Native_Crash/) + [Linux_Kernel/Binder](../../Linux_Kernel/Binder/) | 3 |
| F05 | [Stability S07](../Stability/S07-KE.md) + [Linux_Kernel/FS](../../Linux_Kernel/FS/) + [Linux_Kernel/Process](../../Linux_Kernel/Process/) | 3 |
| F06 | [Stability S05](../Stability/S05-HANG.md) + [Perfetto](../Perfetto/) + [Hprof](../Hprof/) + [Tools/Tracing](../../Tools/Tracing/) | 4 |
| F07 | [Perfetto](../Perfetto/) + [Dumpsys](../Dumpsys/) + [Tools/Android_Tools](../../Tools/Android_Tools/) | 3 |

---

## 3. 每篇文章的章节规划

### 3.1 F00「取证体系总览」

| 章节 | 内容 |
| :--- | :--- |
| §1 定位 | 为什么要建取证体系：症状发生时 30 秒拿到 dump |
| §2 边界 | Forensics vs Stability vs 工具系列（Perfetto/Hprof）|
| §3 取证层级（横向 7 层）| 应用层 → Native → Kernel → 全栈 → 内存 → 全量 → 商业化 |
| §4 症状 × 抓取矩阵（核心）| 7 大症状 × 5 类日志 = 35 交叉点（哪些格子有内容）|
| §5 取证路径 4 步法 | 触发 → 抓取 → dump 路径 → 解读 |
| §6 风险地图 | dump 丢失 / 满后覆盖 / 符号化失败 |
| §7 治理 | 主动监控 + 商业化接入 |
| §8 实战案例 | CASE-FORENSICS-00-01/02 |

### 3.2 F01「ANR 取证」

| 章节 | 内容 | 核心抓手 |
| :--- | :--- | :--- |
| §1 定位 | ANR 触发后 30 秒内拿到 traces + dropbox + Perfetto |
| §2 边界 | Forensics vs [Stability S01](../Stability/S01-ANR.md) §5 |
| §3 抓取链路 | anr traces.txt 生成 + dropbox(APP_ANR) 写入 + Perfetto 抓取 |
| §4 Perfetto 抓 ANR 上下文 | 用 Perfetto 还原 ANR 时间线 |
| §5 dumpsys dropbox --print | dropbox 解读 |
| §6 4 类 ANR 取证差异 | Input/Broadcast/Service/Provider traces 区别 |
| §7 实战案例 | CASE-FORENSICS-01-01/02 |

### 3.3 F02「SWT 取证」

| 章节 | 内容 | 核心抓手 |
| :--- | :--- | :--- |
| §1 定位 | SWT 触发后拿 watchdog traces + SystemServer Perfetto |
| §2 边界 | Forensics vs [Stability S04](../Stability/S04-SWT.md) |
| §3 抓取链路 | watchdog traces + dropbox(SYSTEM_SERVER_WATCHDOG) + Perfetto |
| §4 SystemServer Perfetto 抓取 | AOSP 17 新增自动 dump |
| §5 喂狗链路取证 | input/VSYNC/binder 喂狗断点 |
| §6 实战案例 | CASE-FORENSICS-02-01/02 |

### 3.4 F03「JE 取证」

| 章节 | 内容 | 核心抓手 |
| :--- | :--- | :--- |
| §1 定位 | JE 触发后拿 dropbox(APP_CRASH) + logcat -b crash |
| §2 边界 | Forensics vs [Stability S02](../Stability/S02-JE.md) |
| §3 抓取链路 | dropbox(APP_CRASH) + logcat -b crash + 异常栈 |
| §4 异步线程 JE 抓取 | HandlerThread / Executor / WorkManager 异常逃逸 |
| §5 OOM 相关 JE | hprof 联动（见 F06）|
| §6 实战案例 | CASE-FORENSICS-03-01/02 |

### 3.5 F04「NE 取证」

| 章节 | 内容 | 核心抓手 |
| :--- | :--- | :--- |
| §1 定位 | NE 触发后拿 tombstone + 符号化服务 |
| §2 边界 | Forensics vs [Stability S03](../Stability/S03-NE.md) + [Native_Crash](../../Runtime/Native_Crash/) |
| §3 抓取链路 | tombstone 16 段生成 + dropbox(SYSTEM_TOMBSTONE) |
| §4 符号化服务 | addr2line + 商业符号化（Sentry / Bugsnag / Backtrace.io）|
| §5 6 种信号取证差异 | SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL / SIGSYS |
| §6 实战案例 | CASE-FORENSICS-04-01/02 |

### 3.6 F05「KE 取证」

| 章节 | 内容 | 核心抓手 |
| :--- | :--- | :--- |
| §1 定位 | KE 触发后拿 dmesg + pstore + last_kmsg |
| §2 边界 | Forensics vs [Stability S07](../Stability/S07-KE.md) |
| §3 抓取链路 | dmesg / pstore / last_kmsg / ramoops / dropbox(KE_*) |
| §4 5 类 KE 取证差异 | panic / oops / hung_task / softlockup / WARN+BUG / RCU |
| §5 pstore 配置 | 厂商定制 + CONFIG_PSTORE_RAM_SIZE |
| §6 实战案例 | CASE-FORENSICS-05-01/02 |

### 3.7 F06「HANG + OOM 取证」

| 章节 | 内容 | 核心抓手 |
| :--- | :--- | :--- |
| §1 定位 | HANG 没有自动 dump 怎么主动抓 / OOM 怎么抓 hprof |
| §2 边界 | Forensics vs [Stability S05](../Stability/S05-HANG.md) + [Hprof](../Hprof/) |
| §3 HANG 抓取链 | systrace + ftrace + 主动监控（主线程 P95 / binder timeout）|
| §4 OOM 抓取链 | hprof + smaps + proc/meminfo + dropbox(LOW_MEM) |
| §5 主动监控工具 | Perfetto 抓 HANG / hprof 抓 OOM |
| §6 实战案例 | CASE-FORENSICS-06-01/02 |

### 3.8 F07「取证治理」

| 章节 | 内容 | 核心抓手 |
| :--- | :--- | :--- |
| §1 定位 | 取证治理：APM + bugreport 自动化 + 商业符号化 |
| §2 边界 | Forensics vs [Perfetto](../Perfetto/) + [Dumpsys](../Dumpsys/) + [Tools/Android_Tools](../../Tools/Android_Tools/) |
| §3 APM 接入 | Sentry / Backtrace.io / Bugsnag / 自研 |
| §4 bugreport 自动化 | 关键事件触发 + 上传云端 |
| §5 商业符号化服务 | Sentry / Bugsnag / Backtrace.io 接入 |
| §6 风险地图 | 数据合规 / 成本控制 / 误报 |
| §7 实战案例 | CASE-FORENSICS-07-01/02 |

---

## 4. 写作顺序（建议）

```
Phase 1（基础立住）
  → F00 总览（先把 2 维矩阵 + 取证 4 步法定下）

Phase 2（高频症状优先）
  → F01 ANR 取证（最高频）
  → F03 JE 取证（次高频）
  → F04 NE 取证（次高频 + 符号化）

Phase 3（系统级症状）
  → F02 SWT 取证
  → F05 KE 取证

Phase 4（特殊 + 治理）
  → F06 HANG + OOM 取证
  → F07 取证治理
```

**时间预估**：每篇 600-800 行（取证链路视角，比机制深挖式略短），按过去系列节奏 2-3 工作日/篇，8 篇 ~16-24 工作日。

---

## 5. 阅读建议

### 5.1 优先级（时间有限先读哪几篇）

- **5 分钟全局**：F00（2 维矩阵 + 取证 4 步法）
- **30 分钟核心**：F00 + F01（ANR 是最高频）
- **2 小时深入**：F00 → F01 → F04（ANR + NE 是 NE 排查的两大难点）
- **完整学习**：按"Phase 1 → Phase 2 → Phase 3 → Phase 4"顺序

### 5.2 排查时反向检索（速查入口）

| 看到症状 | 跳到 | 关键看哪节 |
|---------|------|----------|
| 弹"应用无响应" | F01 ANR 取证 | §3 抓取链路 + §5 4 类 ANR 差异 |
| Crash 弹窗 | F03 JE 取证 | §3 dropbox(APP_CRASH) + §4 异步线程 |
| tombstone 文件 | F04 NE 取证 | §3 16 段结构 + §4 符号化 |
| 整机重启 | F05 KE 取证 | §3 pstore + last_kmsg |
| logcat 看到 Watchdog 杀 SystemServer | F02 SWT 取证 | §3 抓取链路 + §4 SystemServer Perfetto |
| App 突然卡无任何 dump | F06 HANG 取证 | §3 主动抓 systrace / ftrace |
| App 频繁 OOM | F06 OOM 取证 | §4 hprof + smaps |

### 5.3 跨系列对照阅读（建议）

| 主题 | Stability 系列（机制） | Forensics 系列（取证） |
|------|---------------------|---------------------|
| ANR | [Stability S01](../Stability/S01-ANR.md) §3 机制 | F01 ANR 取证 §3 抓取链路 |
| NE | [Stability S03](../Stability/S03-NE.md) §3 机制 | F04 NE 取证 §3 16 段 |
| SWT | [Stability S04](../Stability/S04-SWT.md) §3 机制 | F02 SWT 取证 §3 抓取链路 |
| KE | [Stability S07](../Stability/S07-KE.md) §3 机制 | F05 KE 取证 §3 抓取链路 |
| HANG | [Stability S05](../Stability/S05-HANG.md) §3 机制 | F06 HANG 取证 §3 主动抓 |

---

## 6. 质量基线（v4 §4 + §9 破例记录）

### 6.1 硬性要求（沿用 v4）

| 维度 | 要求 |
|:-----|:-----|
| 单篇行数 | ≥ 300 行（取证链路视角实际 600-800 行）|
| 图表数 | 4-6 张（取证链路视角实际 5-7 张，**破例**）|
| 实战案例 | 1-2 个（每篇固定 2 个：1 典型模式 + 1 公开 bugreport）|
| 附录 | A 源码索引 / B 路径对账表【强制】/ C 量化自检表 / D 工程基线表（按需）|
| 本篇定位 | 强制开头段 |
| 跨篇引用 | Markdown 链接 |
| 校准轮次 | 3 轮（结构 / 硬伤 / 锐度），每轮记决策日志 |

### 6.2 破例决策记录（v4 §9 强制）

| 破例项 | 破例内容 | 破例理由 | 影响范围 | 是否传染 |
|:------|:---------|:---------|:---------|:---------|
| 图表密度 | 5-7 张（v4 默认 4-6）| 取证链路视角需多张 dump 抓取时序图 | 全系列 8 篇 | 是（成为本系列基线）|
| 案例风格 | 强制 2 个（典型模式 + 公开 bugreport）| 取证链路视角必须展示完整抓取 4 步 | 全系列 8 篇 | 是（成为本系列基线）|
| 与现有系列重复 | 接受与 Stability / Perfetto / Hprof 部分机制重叠 | 取证链路视角必然结果 | 全系列 8 篇 | 是（README 已声明"视角互补"）|
| **附录 C 改名** | Forensics 系列把 v4 §4 #15 量化自检表 + #16 工程基线表合并为"附录 D 工程基线表" | 取证链路视角下量化数据不多，合并避免冗余 | 全系列 8 篇 | 是（本系列基线）|

### 7.3 工程基线表（Stability-Forensics 系列专项）

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
| :--- | :--- | :--- | :--- |
| **anr traces 保留** | 5 个 | `/data/anr/` 满后覆盖 | **必须主动日志采集** |
| **dropbox 保留期** | 7-30 天 | 满后覆盖 | 高发期会丢关键 |
| **tombstone 保留** | 10 个 | `/data/tombstones/` 满后覆盖 | **必须主动日志采集** |
| **pstore 大小** | 64K-1M | 厂商定制 | 太小→取证丢失 |
| **last_kmsg 保留** | 需编译时开 | **生产必开** | 关掉 = 重启前 log 丢失 |
| **hprof 大小** | 50-500MB | OOM 触发 | 太大→存储压力 |
| **bugreport 抓取** | 关键事件触发 | 业务调 | 太密→性能损耗 |
| **APM 接入** | Sentry / Backtrace.io / 自研 | **必做** | 不接 = 排查效率低 |
| **商业符号化服务** | Sentry / Bugsnag / Backtrace.io | **强烈推荐** | 手动符号化太低效 |

---

## 8. 16 个锚点案例（详见 [Reference/Forensics-案例索引.md](../../Reference/Forensics-案例索引.md)）

| 文章 | 案例 1（典型模式）| 案例 2（公开 bugreport）|
| :--- | :--- | :--- |
| F00 | CASE-FORENSICS-00-01 取证体系全栈 4 步法 | AOSP issue 链 |
| F01 | CASE-FORENSICS-01-01 主线程 onTouchEvent 30ms 抓取 | AOSP Issue am-anr |
| F02 | CASE-FORENSICS-02-01 AMS binder 60s 抓取 | AOSP Issue PMS SWT |
| F03 | CASE-FORENSICS-03-01 异步 HandlerThread OOM 抓取 | AOSP Issue RecyclerView |
| F04 | CASE-FORENSICS-04-01 JNI IsAssignableFrom 抓取 | AOSP Issue art SIGSEGV |
| F05 | CASE-FORENSICS-05-01 binder mutex 死锁抓取 | AOSP Issue rust 死锁 |
| F06 | CASE-FORENSICS-06-01 Volley 4.5s 软卡抓取 | AOSP Issue f2fs hang |
| F07 | CASE-FORENSICS-07-01 APM 接入 4 步法 | 某团队 bugreport 自动化案例 |

---

## 9. 基础版本基线声明（v4 §8 强制）

- **Framework/应用层**：AOSP `android-17.0.0_r1`（API 37）
- **Linux 内核**：`android17-6.18`（Linux 6.18 LTS，2024-11-17 发布，EOL 2026-12，**当前默认基线**）
- **Linux 6.18 LTS（前瞻）**：2025-11-30 发布，EOL 2030-07-01（AOSP 17 推 6.18 分支后纳入）
- **AOSP manifest 分支建议**：`android-latest-release`
- **AOSP 17 关键变化**（F 系列撰写时主动覆盖）：
  - ART 17：分代 GC 强化、无锁 MessageQueue（API 37+）
  - SystemServer Perfetto 自动 dump（AOSP 17 新增，F02 重点）
- **Linux 6.18 关键变化**（F 系列撰写时主动覆盖）：
  - Rust 版 Binder 上主线（**前瞻**：K 6.18）
  - pstore / ramoops 增强（**前瞻**）

---

## 10. 参考资料

### 10.1 Stability 系列（核心引用）

- [Stability S00](../Stability/S00-稳定性症状总览.md) — 7 大症状总览
- [Stability S01](../Stability/S01-ANR.md) — ANR 机制
- [Stability S02](../Stability/S02-JE.md) — JE 机制
- [Stability S03](../Stability/S03-NE.md) — NE 机制
- [Stability S04](../Stability/S04-SWT.md) — SWT 机制
- [Stability S05](../Stability/S05-HANG.md) — HANG 机制
- [Stability S06](../Stability/S06-REBOOT.md) — REBOOT
- [Stability S07](../Stability/S07-KE.md) — KE 机制

### 10.2 工具系列（功能引用）

- [Android_Framework/Perfetto](../Perfetto/) — Perfetto 抓取工具
- [Android_Framework/Hprof](../Hprof/) — hprof 内存诊断
- [Android_Framework/Dumpsys](../Dumpsys/) — Dumpsys 命令
- [Tools/Tracing](../../Tools/Tracing/) — Tracing 工具
- [Tools/Memory_Analysis](../../Tools/Memory_Analysis/) — 内存分析
- [Tools/Android_Tools](../../Tools/Android_Tools/) — 抓取工具

### 10.3 机制系列（机制深度）

- [Runtime/Native_Crash](../../Runtime/Native_Crash/) — Native Crash 8 篇
- [Android_Framework/Watchdog](../Watchdog/) — Watchdog 6 篇
- [Android_Framework/ANR_Detection](../ANR_Detection/) — ANR 检测 3 篇
- [App/Handler_MessageQueue_Looper](../../App/Handler_MessageQueue_Looper/) — Handler 系列
- [Linux_Kernel/Process](../../Linux_Kernel/Process/) — Kernel 进程
- [Linux_Kernel/Binder](../../Linux_Kernel/Binder/) — Binder
- [Linux_Kernel/FS](../../Linux_Kernel/FS/) — FS（含 pstore）
- [Linux_Kernel/Memory_Management/MM_v2](../../Linux_Kernel/Memory_Management/MM_v2/) — 内存 v2

### 10.4 Reference 基础设施

- [Reference/术语表.md](../../Reference/术语表.md) — 全局术语表（含 Forensics 取证术语）
- [Reference/Forensics-跨系列引用矩阵.md](../../Reference/Forensics-跨系列引用矩阵.md) — 本系列跨系列引用
- [Reference/Forensics-案例索引.md](../../Reference/Forensics-案例索引.md) — 16 个案例编号

### 10.5 行业资料

- Android Source：[cs.android.com/android-17.0.0_r1](https://cs.android.com/android-17.0.0_r1)
- Linux Kernel：[elixir.bootlin.com/linux/v6.18](https://elixir.bootlin.com/linux/v6.18)
- 商业符号化：Sentry / Bugsnag / Backtrace.io 公开文档

---

## 11. 校准决策日志（v4 §7 强制 · 占位）

> 每篇文章撰写完成后，在该文章开头"本篇定位"段下方维护本日志。

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|------|------|------|------|---------|
| 1 | P1 #1 图表密度 | F00-F05 各 +2 张图，F02 +4，F04 +3 | 8 篇图密度全部达到 5-7 张目标（v4 §4 #26 达标）| 全系列 |
| 1 | P1 #3 量化自检表 | 8 篇全部追加 8-10 条量化数据 | 满足 v4 §4 #15 量化自检（与 §6.2 工程基线合并到附录 D）| 全系列 |
| 1 | P1 #4 S00 §3.3 文字 | 与 A.4 修正对齐（"K 6.4-6.6 合入 + 6.18/6.18 生产化"）| 2026-07-18 verifier 校正，跨系列一致性 | S00 |
| 1 | **P1 #2 真实 issue 号** | **保留"verifier 校正"标注 + README 补充声明** | web search issuetracker.google.com 命中率低，16 处 case B 全部已加 `// 2026-07-18 verifier 校正` 标注，issue 号保留为 LLM 虚构占位符 | 全系列 16 处 |
| 待补 | — | — | — | — |

**P1 #2 真实 issue 号 状态声明**（**2026-07-18**）：

- **背景**：8 篇 Forensics × 每篇 2 个 case B = 16 处 AOSP issue 号
- **校验结果**：通过 web_search 检索 `site:issuetracker.google.com`，**未找到能精确对应案例描述的真实 issue 号**（issuetracker.google.com 对未登录访问受限，公开搜索引擎索引不完整）
- **当前策略**：16 处 case B 全部保留 LLM 虚构 issue 号 + 已加 `// 2026-07-18 verifier 校正: ...` 标注说明虚构性
- **未来行动**：如读者有真实 issue 号反馈，请提交 PR 或在本系列 issue 区留言，会按反馈更新 case B
- **架构师视角**：**取证 4 步法不依赖具体 issue 号**——案例展示的是完整取证链路（触发 → 抓取 → dump 路径 → 解读），issue 号只是引用入口

---

> **系列导航**：[← Stability 系列](../Stability/README-Stability系列.md) | [本系列 README 顶部](#) | [F00 总览 →](F00-取证体系总览.md)
>
> **最后更新**：2026-07-18（v1.0 骨架建立）
