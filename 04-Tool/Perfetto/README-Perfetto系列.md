# Perfetto 系列:Android 系统级追踪的"瑞士军刀"

> **目录**:`Android_Framework/Perfetto/`
> **基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)+ Kernel `android14-5.15` GKI。

---

## 0. 阅读入口

| 角色 | 你应该读什么 |
|------|------------|
| **5 分钟速览 Perfetto** | 只读 [01 §1-§3](01-Perfetto系统总览与架构设计.md) |
| **要快速抓 trace 解决问题** | [01 §4 数据源速查](#) + [04 完整实战](#) |
| **要理解 Perfetto 为什么这样设计** | [02 核心机制深度解析](#) |
| **要把 Perfetto 接进监控体系** | [03 statsd 联动](#) |
| **要做定制化(ANR 自动抓 / IO 劣化取证)** | [04 定制化实战](#) |
| **想知道 Google 下一步要干嘛** | [05 演进与未来](#) |

---

## 1. 为什么要写 Perfetto 系列

### 1.1 它在稳定性领域的"压舱石"地位

Perfetto 是 Android 10+ 默认的系统级追踪基础设施,已**全面替代 Systrace**。对稳定性工程师而言,它不再是一个"可选工具",而是**线上问题排查的"必选第一现场"**:

- **线上 ANR / 卡顿**:Perfetto trace 是分析主线程 Binder 阻塞、锁竞争、长 IO 的**第一手证据**——比 logcat 更结构化、比 stacktrace 更全栈
- **冷启动耗时退化**:启动链路从 [T0] 点图标到 [T12] 首帧绘制的 12 个时间点,全部能在 Perfetto trace 里"看见"
- **后台进程被杀**:LMKD / cgroup / oom_score_adj 在 trace 里都有专门的事件通道,能反推 kill 时机
- **IO 劣化 / jank**:Block IO / Scheduler / Frame Timeline 三类事件是性能问题的"CT 扫描"

**没有 Perfetto trace,稳定性工程师排查线上问题基本等于"盲人摸象"**——这是它和 ftrace/atrace/systrace 的本质区别(那些只能"碰碰运气",Perfetto 是"必须)。

### 1.2 现有教程的三大盲区

| 现有内容 | 盲区 | 本系列的填补 |
|---------|------|------------|
| 工具使用教程(`perfetto --help`、`simpleperf` 入门) | 停留在"能跑命令",不讲架构、不讲为什么这样设计 | [01 总览] + [02 核心机制] 把设计思想讲透 |
| 散落的 trace 解读博客 | 一次案例一次讲,缺方法论 | [04 实战] 给可复用的"trace 分析 SOP" |
| Google 官方文档 | 只讲 happy path,不讲配置陷阱、性能影响、版本差异 | [02 §6] [03 §6] [04 §6] 给"工程坑位图" |

### 1.3 对稳定性工程师的核心价值

读完后你能做到的事:
1. **5 分钟内**独立配置 Perfetto 抓复杂场景(ANR 后自动抓取 30s trace)
2. **20 分钟内**从 Perfetto trace 定位 Block IO / Binder / Sched 子系统问题
3. 理解 Perfetto 与 ftrace/atrace/statsd 的协作机制,组合成"监控 → 追踪 → 分析"闭环
4. 判断"何时用 Perfetto、何时用其他工具"(避免工具选错浪费时间)
5. 预判 Google 对 Perfetto 的演进方向(eBPF / heapprofd / SQL 查询),提前布局能力

---

## 2. 系列设计思路

### 2.1 架构师思维链(从定位到治理)

```
它是什么?解决什么问题?(定位)
    ↓
Perfetto 是 Android 新一代系统级追踪框架,统一了 ftrace/atrace/systrace 的碎片化工具链,
提供高效二进制格式、SQL 查询能力、长时追踪支持,解决了"传统工具性能开销大、
不可扩展、不能跨进程关联"的核心痛点。
    ↓
它在系统中处于什么位置?和谁协作?(边界与交互)
    ↓
底层:基于 Linux ftrace 子系统,复用内核 tracepoint
中层:traced 守护进程管理数据源(ftrace / atrace / process_stats / heapprofd)
上层:与 statsd 联动(触发器)、与 Dropbox 集成(ANR 自动归档)
横向:与 simpleperf / heapprofd / 网络抓包工具协同
    ↓
它内部是怎么运转的?(核心机制)
    ↓
数据源抽象:linux.ftrace / linux.process_stats / android.heapprofd
配置系统:protobuf TraceConfig(继承 + 覆盖)
数据流:Producer → traced → Consumer,共享内存零拷贝
存储格式:protobuf 二进制 .perfetto-trace,支持流式写入
查询引擎:trace_processor + SQL,支持复杂分析
触发器:statsd 事件触发自动抓取(ANR 后自动 30s)
    ↓
它会在什么地方出问题?(风险地图)
    ↓
配置错误:tracepoint 不存在 / buffer 过小丢事件
权限问题:非 root 设备无法抓内核事件
性能影响:启用所有 sched events → 系统 jank
数据丢失:ANR 时 trace 已被覆盖(需要循环 buffer + 触发器)
版本兼容:Android 9 vs 10+ 的能力差异
    ↓
出了问题我怎么查?怎么防?(诊断与治理)
    ↓
诊断:检查 traced 日志、验证 ftrace events 可用性、分析 trace 完整性
治理:标准化配置模板、自动化抓取脚本、与 CI/CD 集成
预防:建立 Perfetto 配置库、定期回归测试、监控 trace 质量指标
```

### 2.2 依赖关系图

```
[01 总览] ← 全局观,先读
   ↓
[02 核心机制] ← 深入:traced / 共享内存 / 数据源 / 触发器
   ↓
[03 statsd 联动] ← 横向:触发器订阅 / 自动抓取 / Dropbox
   ↓
[04 定制化实战] ← 落地:ANR 后自动抓取的完整配置 + 实战案例
   ↓
[05 演进与未来] ← 前瞻:eBPF / heapprofd / Google Roadmap
```

**强依赖**:02、03、04 都需要 01 的全局观;04 是 02+03 的综合实战。
**可独立读**:05 是独立的前瞻专题,读完前 4 篇再看收益最大,但单独读也能有收获。

### 2.3 跨系列引用矩阵

| 本系列章节 | 引用系列 | 引用文章 | 引用原因 |
|----------|---------|---------|---------|
| [01 §4 数据源] | Kernel_Tools | [ftrace 语法解析](../06-Foundation/Tools/Tracing/ftrace的语法解析.md) | 数据源底层就是 ftrace |
| [02 §3 ftrace 数据源] | Kernel_Tools | [block_bio_complete 与 block_rq_complete 核心区别](../06-Foundation/Tools/Tracing/block_bio_complete%20与%20block_rq_complete%20核心区别.md) | Block IO tracepoint 的语义差异 |
| [03 §3 statsd 触发器] | Tools | [Trace 抓取方法全面指南](../06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto.md) | 与 atrace / systrace 的能力对比 |
| [04 §3 ANR 自动抓] | ANR_Detection | (已有 ANR 系列) | ANR 检测 → 触发 Perfetto 抓取的链路 |
| [04 §4 IO 劣化案例] | IO | (已有 IO 系列) | IO 等待 → 冷启动退化 的 trace 特征 |
| [04 §5 Input ANR 案例] | Input | (已有 Input 系列) | Input ANR 在 trace 中的特征切片 |
| [04 §6 Binder 阻塞案例] | Binder | (已有 Binder 系列) | Binder 阻塞的 trace 视觉特征 |
| [05 §3 eBPF] | Linux_Kernel | (内核层 eBPF 相关) | Perfetto 未来对接 eBPF 的内核基础设施 |

---

## 3. 章节规划

### 3.1 第 1 篇:[01-Perfetto 系统总览与架构设计](01-Perfetto系统总览与架构设计.md)

**本篇定位**:全局观 + 入口。读完能用 Perfetto 抓基本 trace,并理解它在 Android 追踪生态中的位置。

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
|------|------|-------------|-----------|
| §1 | Perfetto 是什么、为什么取代 Systrace | - | 工具链演进的痛点驱动 |
| §2 | 追踪工具演进史:ftrace → atrace → systrace → Perfetto | `kernel/trace/trace.c` | 每个阶段的局限性 |
| §3 | 三层架构:Producer / traced / Consumer | `external/perfetto/src/tracing/` | traced 崩溃 = 抓取瘫痪 |
| §4 | 数据源体系:ftrace / atrace / process_stats / heapprofd 速查表 | `external/perfetto/src/traced/probes/` | 不同数据源的性能开销差异 |
| §5 | TraceConfig protobuf:配置即代码 | `external/perfetto/protos/perfetto/config/` | 配置错误的诊断方法 |
| §6 | 与 ftrace/atrace/simpleperf 的协作矩阵 | - | 工具链组合拳 |
| §7 | 实战:同 ANR 问题 Systrace vs Perfetto 对比 | - | 体现 Perfetto 优势 |

### 3.2 第 2 篇:[02-Perfetto 核心实现深度解析](02-Perfetto核心实现深度解析.md)

**本篇定位**:核心机制。理解 Perfetto "为什么这样设计",能读懂源码、能调性能瓶颈。

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
|------|------|-------------|-----------|
| §1 | traced 守护进程:启动 / IPC / 权限 | `external/perfetto/src/traced/service/` | traced 崩溃的日志定位 |
| §2 | Producer-Consumer 共享内存零拷贝 | `external/perfetto/src/tracing/core/` | 内存泄漏风险 |
| §3 | ftrace 数据源:FtraceController 与 buffer 管理 | `external/perfetto/src/traced/probes/ftrace/` | ftrace buffer 溢出丢事件 |
| §4 | atrace 集成:categories 映射与 trace_marker | `external/perfetto/src/traced/probes/ftrace/atrace_wrapper.cc` | atrace 失效 → 用户态事件缺失 |
| §5 | 配置解析与默认值填充 | `external/perfetto/src/perfetto_cmd/config.cc` | 配置错误的诊断方法 |
| §6 | 触发器机制:Trigger Config 与延迟抓取 | `protos/perfetto/config/trigger_config.proto` | ANR 自动抓取的基础 |
| §7 | 风险地图:6 类常见配置陷阱 | - | 工程坑位图 |

### 3.3 第 3 篇:[03-Perfetto 与 statsd 联动机制](03-Perfetto与statsd联动机制.md)

**本篇定位**:横向集成。把 Perfetto 接进 Android 监控体系,实现"告警 → 自动取证"闭环。

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
|------|------|-------------|-----------|
| §1 | statsd 是什么、为什么需要和 Perfetto 联动 | `frameworks/base/cmds/statsd/` | 监控 + 追踪的闭环 |
| §2 | Perfetto-statsd 集成架构:订阅 / 通知 / 下发 | `external/perfetto/src/android_stats/` | 自动化问题捕获 |
| §3 | 基于 statsd 的自动抓取:ANR/Crash 触发 Perfetto | `protos/perfetto/config/android/` | 线上问题自动留证 |
| §4 | 性能指标联动:CPU/Memory/IO 阈值触发追踪 | - | 性能劣化的预警与取证 |
| §5 | Dropbox 集成:ANR trace 自动上传 | `DropBoxManagerService.java` | ANR 完整证据链 |
| §6 | 配置管理最佳实践:分场景模板 + 动态下发 | - | 避免配置爆炸 |
| §7 | 实战:IO 劣化 statsd 发现 → Perfetto 抓取 → 根因定位 | - | 完整闭环演示 |

### 3.4 第 4 篇:[04-Perfetto 定制化实战:ANR 后自动抓取 trace](04-Perfetto定制化实战:ANR后自动抓取trace.md)

**本篇定位**:落地实战。从"看教程"到"上线用"的关键一步。

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
|------|------|-------------|-----------|
| §1 | ANR 检测链路与触发点 | `ActivityManagerService.java` | ANR 触发的瞬间怎么接住 |
| §2 | ANR 后抓的 3 大挑战:时间窗 / buffer 覆盖 / 性能影响 | - | 为什么必须用循环 buffer + 触发器 |
| §3 | 循环 buffer 配置:RING_BUFFER vs DISCARD | `protos/perfetto/config/trace_config.proto` | 避免关键事件被覆盖 |
| §4 | 触发器配置:STOP_TRACING / 延迟时间 / 多触发器 | `protos/perfetto/config/trigger_config.proto` | ANR 前后 30s 完整 trace |
| §5 | 自定义 ANR 触发器:监听 + 调用 perfetto trigger | `Trace.java` + 自定义 daemon | 应用层集成 |
| §6 | trace 质量保证:完整性检查 / 关键事件验证 | - | 避免抓到无效 trace |
| §7 | 性能优化:减少开销 / 选择性启用 events | - | 追踪本身不能影响系统 |
| §8 | 实战 1:完整实现 ANR 自动抓取 30s trace | - | 端到端配置 + 验证 |
| §9 | 实战 2:Input ANR 从 Perfetto trace 定位到 Binder 阻塞 | - | trace 分析 SOP |

### 3.5 第 5 篇:[05-Perfetto 演进与 Google 未来规划](05-Perfetto演进与Google未来规划.md)

**本篇定位**:前瞻 + Roadmap。判断 Perfetto 演进方向,提前布局能力。

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
|------|------|-------------|-----------|
| §1 | Android 9 → 14 版本能力矩阵 | - | 版本兼容性问题 |
| §2 | 新增数据源:heapprofd / Java heap / 网络 / GPU | `src/profiling/` | 更全面的问题分析 |
| §3 | UI 与 SQL 查询能力增强 | - | 提升分析效率 |
| §4 | 跨平台:Linux / Chrome / Fuchsia 的 Perfetto | - | 统一追踪框架的愿景 |
| §5 | 与 eBPF 集成 | - | 下一代追踪技术 |
| §6 | Google 官方 Roadmap 解读(基于公开资料) | - | 预判工具链演进 |
| §7 | 厂商定制化方向:OEM 如何扩展 Perfetto | - | 差异化能力建设 |
| §8 | Perfetto 的局限性:无法解决的问题、需要其他工具补充 | - | 工具选择的边界 |
| §9 | 实战:heapprofd 分析内存泄漏 | - | 多工具联合分析 |

---

## 4. 工程产出清单

本系列除 5 篇正文外,还产出可直接复用的工程资产:

```
Android_Framework/Perfetto/
├── README-Perfetto系列.md                    ← 本文件
├── 01-Perfetto系统总览与架构设计.md
├── 02-Perfetto核心实现深度解析.md
├── 03-Perfetto与statsd联动机制.md
├── 04-Perfetto定制化实战:ANR后自动抓取trace.md
├── 05-Perfetto演进与Google未来规划.md
├── perfetto_configs/                         ← 配置模板库
│   ├── anr_auto_capture.pbtxt                ← ANR 后自动抓取 30s
│   ├── io_degradation.pbtxt                  ← IO 劣化专项
│   ├── jank_analysis.pbtxt                   ← 卡顿分析
│   └── memory_leak.pbtxt                     ← 内存泄漏
├── scripts/                                  ← 自动化脚本
│   ├── perfetto_anr_trigger.sh               ← ANR 触发抓取
│   ├── trace_quality_check.py                ← trace 完整性校验
│   └── trace_quality_check.ps1               ← Windows 兼容版
└── trace_analysis_sql/                       ← SQL 查询库
    ├── binder_blocked.sql                    ← Binder 阻塞切片
    ├── main_thread_long_task.sql             ← 主线程长任务
    └── io_wait_analysis.sql                  ← IO 等待分析
```

---

## 5. 关键设计原则

本系列刻意区别于其他系列(尤其是进程系列)的两个关键取舍:

### 5.1 源码密度刻意压低

- **进程系列 02/03/04**:源码占比 42-60%(用户反馈"源码太多")
- **本系列**:源码占比 **15-20%**,只贴关键方法签名 + 3-5 行核心逻辑 + 1-2 段"贴代码后的视角分析"
- 重点放在**架构图、时序图、表格、决策树**上——讲清楚"为什么这样设计"远比贴代码重要

### 5.2 配置文件以可复用模板形式产出

Perfetto 配置错误是线上最高频的问题来源(占比 ~40%)。本系列:
- 每个核心配置都以 `perfetto_configs/*.pbtxt` 形式单独存档
- 每个 pbtxt 都有"典型场景 / 参数说明 / 踩坑提醒"三段注释
- README 末尾给"配置选型决策树"

---

## 6. 与现有 Tracing 系列文档的边界声明

`Tools/Tracing/` 目录下已有 4 篇文档,本系列与它们的关系是**"基础 + 进阶"**:

| 现有文档 | 边界声明 | 本系列如何引用 |
|---------|---------|--------------|
| [20-Trace抓取方法全面指南](../06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南:ftrace-atrace-systrace-perfetto.md) | 工具使用入门(命令行、参数) | [01 §6] 引用其能力对比表,本系列不重复命令行基础 |
| [ftrace 的语法解析](../06-Foundation/Tools/Tracing/ftrace的语法解析.md) | ftrace 语法本身 | [02 §3] 引用其语法规则,本系列只讲 Perfetto 怎么读 ftrace |
| [block_bio_complete 与 block_rq_complete 核心区别](../06-Foundation/Tools/Tracing/block_bio_complete%20与%20block_rq_complete%20核心区别.md) | Block IO tracepoint 语义 | [02 §3] 引用其区别,本系列讲怎么在 Perfetto 里看到这两个事件 |
| [Android 设备如何抓取 trace](../06-Foundation/Tools/Tracing/Android设备如何抓取trace.md) | 设备操作基础 | 不重复,本系列默认读者会抓 trace |

**本系列从 01 §6 开始就是"Perfetto 进阶"——默认你会跑 `perfetto` 命令,默认你懂 ftrace 基础语法,默认你会用 trace UI。**

---

## 7. 阅读建议

### 7.1 按时间预算选读

| 时间预算 | 建议路径 |
|---------|---------|
| **1 小时** | [01 §1-§4] + [04 §3 循环 buffer] |
| **半天** | [01 全文] + [04 实战 1] |
| **2 天** | [01-04 全文] |
| **一周** | [01-05 全文] + 跑完所有实战案例 |

### 7.2 按角色选读

| 角色 | 必读 | 选读 |
|------|------|------|
| 稳定性工程师 | 01 / 04 / 03 | 02 / 05 |
| 平台架构师 | 01 / 02 / 03 | 04 / 05 |
| 性能优化工程师 | 01 / 02 / 04 / 05 | 03 |
| 工具链开发者 | 02 / 03 / 05 | 01 / 04 |

---

## 8. 质量基线(本系列横切型参数表)

> Perfetto 涉及大量可调参数(trace buffer 大小、抓取时长、事件采样率等),单篇无法穷举。下表是**横切所有篇的工程默认值基线**,单篇涉及具体场景的调参在该篇的"附录 D"展开。

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| `buffer_size_kb` | 2048 (2MB) | ANR 后抓取建议 8192 (8MB),避免长 trace 被截断 | 太小 → 长 trace 丢事件;太大 → 内核内存压力大 |
| `flush_period_ms` | 1000 | 实时性要求高 → 500;长时间抓 → 5000 | 太频繁 → 性能开销;太慢 → 故障时丢 trace |
| `duration_ms` | 10000 | 启动分析 5000-10000;ANR 前后 30000 | 太短 → 抓不到关键事件;太长 → 性能/存储压力大 |
| `fill_policy` | DISCARD | ANR 场景必须用 RING_BUFFER 循环写 | 默认 DISCARD 在 ANR 时 buffer 已被覆盖 |
| `trigger_mode` | START_TRACING | ANR 自动抓用 STOP_TRACING(由 statsd 触发停止) | 配错 → ANR 触发时根本没在抓 |
| `ftrace_events` | 默认子集 | IO 问题加 block 类;调度问题加 sched 类 | 启用所有 → 系统 jank 5-10% |
| `atrace_categories` | 默认子集 | 启动分析加 `am`/`wm`/`view`/`gfx` | 类目太多 → 单次 trace 体积过大 |
| `heapprofd_sampling_interval_bytes` | 4096 | 内存问题降到 1024;性能敏感保持 65536 | 太频繁 → 应用 jank;太稀 → 漏内存问题 |

---

## 9. 下一步

读本 README 后:
- 想知道 Perfetto **是什么、在哪、怎么开始** → [01-Perfetto系统总览与架构设计](01-Perfetto系统总览与架构设计.md)
- 想直接落地 **ANR 自动抓取** → [04-Perfetto定制化实战:ANR后自动抓取trace](04-Perfetto定制化实战:ANR后自动抓取trace.md)
