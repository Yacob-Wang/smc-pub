# Hprof 系列:Android 内存稳定性的"黑匣子"

> **目录**:`Android_Framework/Hprof/`
> **基线**:AOSP `android-14.0.0_r1` + Perfetto upstream `v43+` + Kernel `android14-5.15` GKI

---

## 0. 阅读入口

| 角色 | 你应该读什么 |
|------|------------|
| **5 分钟速览 hprof** | 只读 [01 §1-§3](01-hprof原理与文件格式.md) |
| **要快速解析一个 hprof 文件** | [02 §1-§3](02-hprof解析工具链.md) 工具选型 + [§6 命令速查](#) |
| **想了解 Google 新方向(perfetto_hprof)** | [03 全文](03-perfetto_hprof详解.md) |
| **排查线上内存泄漏问题** | [04 §2-§5 案例库](04-内存泄漏典型案例与排查SOP.md) |
| **要在团队搭建内存监控体系** | [05 实战](05-实战：内存监控体系搭建.md) |

---

## 1. 为什么要写 hprof 系列

### 1.1 它在稳定性领域的"事故取证"地位

hprof 是 Android/Java **堆内存转储**(Heap Profile)的标准二进制格式。对稳定性工程师而言,它和 Perfetto trace 一样属于"必选第一现场"——只是分工不同:

| 工具 | 看的维度 | 解决的问题 |
|------|---------|-----------|
| **Perfetto trace** | 时间维度(谁在什么时候做了什么) | 卡顿、ANR、启动慢、IO 劣化 |
| **hprof** | 空间维度(谁占用了多少内存、被谁引用) | **OOM、内存泄漏、Native 增长、Bitmap 暴涨** |
| **logcat** | 事件维度(系统说了什么) | 异常日志、关键事件 |
| **dumpsys** | 系统状态维度 | Service/Activity/Battery 当前快照 |

> **没有 hprof,内存泄漏排查基本等于"猜"** —— 这是它和 Perfetto trace 的本质区别(Perfetto 看时间轴,hprof 看对象图)。

### 1.2 现有教程的三大盲区

| 现有内容 | 盲区 | 本系列的填补 |
|---------|------|------------|
| LeakCanary 使用教程 | 停留在"接入 + 看报告",不讲 hprof 格式、不讲工具差异 | [01 格式] + [02 工具链] 把底层讲透 |
| MAT 离线分析教程 | 只讲"看 dominator tree",不讲实战链路 | [04 SOP] 给完整的"从现象到根因"路径 |
| perfetto_hprof 介绍 | 散落的英文博客,缺中文深度解读 | [03 全文] 给架构视角 + 配置模板 |

### 1.3 对稳定性工程师的核心价值

读完后你能做到的事:
1. **5 分钟内**独立生成 hprof 并用对工具解析(debug / release / 线上不同路径)
2. **20 分钟内**从 hprof 报告定位 Activity/Handler/Static 等典型泄漏
3. 理解 hprof 与 perfetto_hprof 的本质差异,选择正确的工具
4. 搭建一套 LeakCanary + 线上 OOM 上传 + Dashboard 的完整内存监控体系
5. 预判 Google 在内存追踪方向的演进(heapprofd 普及、native sampling、跨进程追踪)

---

## 2. 系列设计思路

### 2.1 架构师思维链(从原理到治理)

```
hprof 是什么?文件格式怎么解析?(底层原理)
    ↓
用啥工具看?工具之间啥差异?(工具方法论)
    ↓
Google 新方向 perfetto_hprof 是什么?(机制演进)
    ↓
典型泄漏长啥样?怎么排?(案例 + SOP)
    ↓
线上监控怎么做?(工程体系)
```

### 2.2 五篇的递进关系

```
        01 原理
         ↓
   ┌─────┴─────┐
   ↓           ↓
  02 工具     03 新机制
   ↓           ↓
   └─────┬─────┘
         ↓
     04 案例
         ↓
     05 实战
```

- **01 → 02/03**:原理是工具和新机制的根
- **02 → 03**:理解传统工具的局限才能理解 perfetto_hprof 为何出现
- **04 是桥梁**:把工具能力映射到真实问题
- **05 是闭环**:把单次排查能力升级为体系化监控

### 2.3 源码密度控制(参考 Perfetto 系列)

| 维度 | 进程系列 02/03/04 | Perfetto 系列 5 篇 | hprof 系列(本系列)|
|------|----------------|------------------|------------------|
| 源码占比 | 42-60% | **~15%** | **~15-20%** |
| 单篇平均行数 | 1700+ | **640** | **600-700** |
| 重点 | 贴源码 + 解读 | **架构图 + 决策树 + 视角** | 同上 |
| 实战案例 | 1-2 个 | **2-3 个** | **2-3 个/篇** |
| 工程资产 | 无 | **配置/脚本/SQL 共 10 个** | **6+ 个** |

---

## 3. 篇目速览

### 篇 01:hprof 原理与文件格式
**角色**:全局观
**核心问题**:hprof 二进制到底长啥样?Android ART 是怎么生成的?
**关键产出**:
- hprof 文件格式的字节级解析(HEADER / RECORD / TAG)
- ART 中 `DumpHprofData` 的生成路径
- hprof 在稳定性工具链的位置
- hprof 的三大局限(性能开销、native 盲区、采样缺失)

### 篇 02:hprof 解析工具链
**角色**:工具方法论
**核心问题**:用什么工具看 hprof?工具之间啥差异?
**关键产出**:
- hprof-conv(格式转换)、LeakCanary、Eclipse MAT、hprof-slice 横向对比
- 工具选型决策树
- 工程坑位图(LeakCanary 误报、MAT 加载大文件 OOM 等)
- **工程资产**:hprof 批处理脚本(Win/Linux/Mac)

### 篇 03:perfetto_hprof 详解
**角色**:新机制
**核心问题**:Google 为啥把 hprof 集成到 Perfetto?heapprofd 是怎么工作的?
**关键产出**:
- heapprofd 守护进程架构
- Native heap sampling 原理
- perfetto_hprof 配置模板
- 与传统 hprof 的对比(开销、采样率、native 覆盖)
- **工程资产**:perfetto_hprof.pbtxt 配置模板

### 篇 04:内存泄漏典型案例与排查 SOP
**角色**:案例库
**核心问题**:常见内存泄漏长啥样?怎么从现象一步步排到根因?
**关键产出**:
- 内存稳定性问题全景图(OOM / Leak / Pressure / Native)
- Activity/Fragment 泄漏 5 大场景
- Handler/Thread/Static 泄漏
- 系统级泄漏(注册未反注册、Cursor 未关闭)
- Native 内存问题(JNI Reference、Bitmap、DirectByteBuffer)
- **工程资产**:LeakCanary 配置模板 + 报告解析脚本

### 篇 05:实战:内存监控体系搭建
**角色**:工程体系
**核心问题**:怎么把单次排查能力变成体系化监控?
**关键产出**:
- 监控整体架构(client / server / dashboard)
- LeakCanary 接入实战(debug + 灰度策略)
- 线上 OOM 监控 + hprof 上传链路
- 内存归因 dashboard 设计
- 与 perfetto_hprof / statsd 的协同
- **工程资产**:OOM log 解析脚本、内存模式分析查询

---

## 4. 工程资产清单

```
Hprof/
├── README-Hprof系列.md                       (本文件)
├── 01-hprof原理与文件格式.md
├── 02-hprof解析工具链.md
├── 03-perfetto_hprof详解.md
├── 04-内存泄漏典型案例与排查SOP.md
├── 05-实战：内存监控体系搭建.md
├── hprof_configs/
│   ├── leakcanary_config.gradle              LeakCanary 接入模板
│   └── perfetto_hprof.pbtxt                  perfetto_hprof 配置模板
├── scripts/
│   ├── hprof_batch_convert.sh                hprof 批处理(Linux/Mac)
│   ├── hprof_batch_convert.ps1               hprof 批处理(Windows)
│   ├── oom_log_analyzer.sh                   OOM log 解析(Linux/Mac)
│   ├── oom_log_analyzer.ps1                  OOM log 解析(Windows)
│   └── leakcanary_report_parse.py            LeakCanary 报告解析
└── trace_analysis_sql/
    └── leak_pattern_match.sql                LeakCanary 报告 SQL 查询
```

---

## 5. 与其他系列的关系

| 系列 | 关系 |
|------|------|
| **Perfetto 系列** | 03 篇会重点引用 Perfetto 的 `heapprofd` 数据源和 trace_processor |
| **ANR_Detection 系列** | 04-05 篇会涉及 ANR 时的内存状态分析 |
| **Process 系列** | 内存稳定性与进程被杀的关联(OOM Adj / LMKD) |
| **Runtime(规划中)** | ART GC 机制是 hprof 生成的底层 |

---

## 6. 风格约束(本系列统一遵守)

1. **源码密度 ≤ 20%**——每篇代码块总行数 / 总行数
2. **架构图优先**——能用 ASCII 图表达的不用文字
3. **决策树替代枚举**——"遇到 X 用 Y" 比 "Y 的源码是…" 更实用
4. **每个工程资产都要"5 分钟跑通"**——可执行、可复用、有注释
5. **案例必须有"现象→分析→根因→修复"四段式**——避免"看图说话"

---

## 7. 配套基线

| 项 | 版本/路径 |
|----|---------|
| AOSP 基线 | `android-14.0.0_r1` |
| Perfetto 基线 | upstream `v43+` |
| Kernel 基线 | `android14-5.15` GKI |
| ART 源码路径 | `art/runtime/hprof/`、`art/runtime/gc/` |
| LeakCanary 版本 | 2.x(基于 Shark 引擎) |
| Android Studio | Hedgehog (2023.1.1) 或更新 |
| 工具下载 | hprof-conv 来自 SDK `platform-tools/` |