# 进程调度与 CPU 核心机制

## 📋 目录说明

本目录深入解析 Linux Kernel 进程调度机制及核心内核线程（如 kworker），这是理解系统性能（CPU Usage）、响应速度（Scheduling Latency）和稳定性问题（Watchdog、ANR）的基石。

## 📚 知识体系

### 知识体系完整性

#### 当前覆盖 ✅

1.  **内核工作线程 (kworker)**
    - ✅ **kworker 机制** - Workqueue 架构、Bound/Unbound 区别、CMWQ
    - ✅ **问题定位** - 高 CPU、D 状态、`trace_workqueue_execute_start`
    - ✅ **命名规则** - 如何从进程名推断用途（如 `u16:0`, `blk_crypto`）
    - 文档：[kworker_Deep_Dive.md](kworker_Deep_Dive.md)

#### 建议补充 ⚠️

2.  **CFS 调度器 (Completely Fair Scheduler)**
    - ⚠️ **基本原理** - 虚拟运行时间 (vruntime)、红黑树
    - ⚠️ **调度实体** - `sched_entity`
    - ⚠️ **调度类** - SCHED_NORMAL, SCHED_BATCH
    - ⚠️ **负载均衡** - Load Balance 机制

3.  **实时调度 (RT Scheduling)**
    - ⚠️ **策略** - SCHED_FIFO, SCHED_RR
    - ⚠️ **优先级** - RT Priority vs Nice Value
    - ⚠️ **优先级反转** - Priority Inversion 及其解决

4.  **调度延迟与抢占**
    - ⚠️ **抢占机制** - 用户态抢占、内核态抢占
    - ⚠️ **调度延迟** - `sched_latency`
    - ⚠️ **Context Switch** - 上下文切换开销

5.  **CPU 拓扑与隔离**
    - ⚠️ **CPUset** - Android 中的应用 (Top-app, Foreground, Background)
    - ⚠️ **EAS (Energy Aware Scheduling)** - 涉及能耗的调度（大小核）

## 🔗 核心源码路径

- `kernel/workqueue.c` - Workqueue 机制实现
- `kernel/sched/core.c` - 调度核心框架
- `kernel/sched/fair.c` - CFS 调度器
- `kernel/sched/rt.c` - RT 调度器

## 🛠️ 分析工具

- **ftrace**: `sched_switch`, `sched_wakeup`, `workqueue_execute_start`
- **Systrace/Perfetto**: 图形化分析调度条
- **top/ps**: 基础进程状态查看
- **cat /proc/loadavg**: 系统负载概览
