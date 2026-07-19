# 附录 A：源码索引（GC 调度与触发 · v2 升级版）

> **本附录定位**：**A 附录 · 源码路径索引**（4 附录之 1/4）——07 子模块 4 篇正文涉及的 AOSP 17 ART 源码完整路径 + 关键函数清单 + ART 17 新增源码 + Linux 6.18 关联源码
> **基线版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS，2024-11-17 发布，EOL 2026-12）
> **v2 升级日期**：2026-07-18（v1 旧文按 v4 规范 + 新基线 + ART 17 硬变化升级）

---

## 一、核心文件（07 子模块全量）

### 1.1 ART 核心源码（AOSP 17）

```
art/runtime/gc/heap.h                                    # Heap 类（含 task_daemon_、gc_cause_）
art/runtime/gc/heap.cc                                   # Heap 实现（含 CollectGarbage、TryToAllocate、RequestConcurrentGC）
art/runtime/gc/gc_cause.h                                # GcCause 枚举（AOSP 17 扩展到 11 种）
art/runtime/gc/gc_cause.cc                               # GcCause 字符串转换（PrettyCause）
art/runtime/gc/heap_task.h                               # HeapTask 抽象类 + ConcurrentGCTask / TrimHeapTask / NativeAllocGCTask
art/runtime/gc/heap_task_daemon.h                        # HeapTaskDaemon 类
art/runtime/gc/heap_task_daemon.cc                       # HeapTaskDaemon 实现（含 ART 17 动态 sleep）
art/runtime/gc/task_processor.h                          # TaskProcessor（多任务处理）
art/runtime/gc/reference_processor.h                     # Reference 处理
art/runtime/gc/reference_processor.cc                    # Reference 处理实现
art/runtime/gc/space/gen_space.h                         # GenCC Space
art/runtime/gc/space/gen_space.cc                        # GenCC Space 实现（Remembered Set + Card Table）
art/runtime/gc/collector/concurrent_copying.h            # CC GC 头文件
art/runtime/gc/collector/concurrent_copying.cc           # CC GC 主循环（兼容保留）
art/runtime/gc/collector/generational_cc.h                # ★ GenCC 头文件（含 kSoftThresholdPercent=30）
art/runtime/gc/collector/generational_cc.cc              # ★ GenCC 实现（Minor / RunPhases / RunBackgroundPhases）
art/runtime/options.h                                    # ★ ART 17 全局选项
```

### 1.2 Linux 6.18 关联源码（跨系列基线）

```
kernel/mm/slab_common.c                                   # Linux 6.18 sheaves 内存分配器
kernel/mm/slub.c                                          # SLUB 分配器（与 ART Native 堆相关）
kernel/sched/core.c                                       # CPU 负载检测（HeapTaskDaemon 动态 sleep 联动）
kernel/fs/io_uring.c                                      # io_uring（heap dump 写盘延迟）
```

---

## 二、关键函数清单（按 4 篇正文分类）

### 2.1 [01-9种GcCause](../01-9种GcCause.md) 相关函数

| 函数 | 文件 | 功能 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `Heap::CollectGarbage` | `heap.cc` | GC 触发入口 | **优先 Minor GC** |
| `Heap::SelectGcTypeForCause` | `heap.cc` | GC 类型选择 | **新增 4 个 cause 分支** |
| `PrettyCause` | `gc_cause.cc` | GcCause 字符串转换 | **新增 4 个 case** |
| `GcCause` 枚举 | `gc_cause.h` | 11 种 GcCause 定义 | **★ 扩展 3 个** |
| `Heap::ShouldTriggerSoftThreshold` ★ | `heap.cc` | 软阈值触发检查 | **AOSP 17 新增** |

### 2.2 [02-HeapTaskDaemon](../02-HeapTaskDaemon.md) 相关函数

| 函数 | 文件 | 功能 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `Heap::CreateHeapTaskDaemon` | `heap.cc` | 创建 HeapTaskDaemon | **InitializeDynamicSleep** |
| `Heap::AddTask` | `heap.cc` | 提交 GC 任务 | 不变 |
| `HeapTaskDaemon::Run` | `heap_task_daemon.cc` | HeapTaskDaemon 主循环 | **动态 sleep 间隔** |
| `HeapTaskDaemon::UpdateSleepInterval` ★ | `heap_task_daemon.cc` | 动态 sleep 调整 | **AOSP 17 新增** |
| `HeapTaskDaemon::ShouldTriggerSoftThreshold` ★ | `heap_task_daemon.cc` | 软阈值触发 | **AOSP 17 新增** |
| `HeapTaskDaemon::InitializeDynamicSleep` ★ | `heap_task_daemon.cc` | 初始化动态 sleep | **AOSP 17 新增** |
| `ConcurrentGCTask::Run` | `heap_task.h` | 后台 GC 任务 | **3 参数 + 5 cause 分支** |
| `BackgroundGenCCTask::Run` ★ | `heap_task.h` | 后台分代 CC 任务 | **AOSP 17 新增** |
| `SoftThresholdGCTask::Run` ★ | `heap_task.h` | 软阈值触发任务 | **AOSP 17 新增** |
| `TrimHeapTask::Run` | `heap_task.h` | Trim Heap 任务 | 不变 |
| `NativeAllocGCTask::Run` | `heap_task.h` | Native 触发的 GC 任务 | 不变 |

### 2.3 [03-ConcurrentGCTask](../03-ConcurrentGCTask.md) 相关函数

| 函数 | 文件 | 功能 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `Heap::RequestConcurrentGC` | `heap.cc` | 请求后台 GC | **3 参数（含 urgency）** |
| `Heap::ConcurrentGC` | `heap.cc` | 执行后台 GC | **新增 BackgroundGenCC 路径** |
| `ConcurrentGCTask::Run` | `heap_task.h` | 后台 GC 任务执行 | **限流 + 5 cause 分支** |
| `Heap::CheckConcurrentGC` | `heap.cc` | 检查并触发后台 GC | 不变 |
| `Heap::OnNativeAllocationPressure` | `heap.cc` | Native 内存压力触发 | 不变 |
| `Heap::OnNativeAllocationPressureThrottled` ★ | `heap.cc` | Native 限流版本 | **AOSP 17 新增** |
| `Heap::ShouldThrottleNativeAllocGC` ★ | `heap.cc` | 限流检查 | **AOSP 17 新增** |
| `Heap::CheckSoftThreshold` ★ | `heap.cc` | 软阈值检查 | **AOSP 17 新增** |
| `Heap::ScheduleBackgroundGenCC` ★ | `heap.cc` | 后台分代 CC 调度 | **AOSP 17 新增** |
| `Heap::ScheduleThrottledNativeGC` ★ | `heap.cc` | 限流后重试 | **AOSP 17 新增** |

### 2.4 [04-GC_FOR_ALLOC路径](../04-GC_FOR_ALLOC路径.md) 相关函数

| 函数 | 文件 | 功能 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `Heap::TryToAllocate` | `heap.cc` | 分配入口（快速 + 慢速） | **新增软阈值检查** |
| `Heap::AllocateInternalWithGc` | `heap.cc` | 触发 GC 的分配 | **优先 Minor GC** |
| `Heap::CollectGarbage` | `heap.cc` | 触发 GC | **优先 Minor + 失败升级 Major** |
| `GenerationalCC::MinorGc` | `generational_cc.cc` | Minor GC | 不变 |
| `GenerationalCC::RunPhases` | `generational_cc.cc` | Major GC（升级路径） | **AOSP 17 罕见** |
| `GenerationalCC::RunBackgroundPhases` ★ | `generational_cc.cc` | 后台分代 CC | **AOSP 17 新增** |
| `Heap::allocation_failed_` ★ | `heap.cc` | Minor 失败标记 | **AOSP 17 新增** |
| `Heap::RecordGcForAllocFailure` ★ | `heap.cc` | 记录分配失败 GC | **AOSP 17 新增** |

### 2.5 跨篇通用函数

| 函数 | 文件 | 功能 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `Heap::Trim` | `heap.cc` | Trim Heap | 不变 |
| `Heap::ChangeSoftReferenceLimit` | `heap.cc` | 调整 SoftReference 阈值 | 不变 |
| `ReferenceProcessor::ProcessReferences` | `reference_processor.cc` | Reference 处理 | 不变 |
| `GenerationalCC::kSoftThresholdPercent` ★ | `generational_cc.h` | 软阈值常量 30% | **AOSP 17 新增** |
| `GenerationalCC::kHardThresholdPercent` | `generational_cc.h` | 硬阈值常量 10% | 不变 |

---

## 三、关键常量（AOSP 17 完整定义）

### 3.1 GcCause 枚举完整定义

```cpp
// art/runtime/gc/gc_cause.h（AOSP 17 完整定义）
enum GcCause {
    kGcCauseNone,                       // 默认（哨兵）
    kGcCauseForAlloc,                   // 分配失败触发
    kGcCauseForNativeAlloc,             // Native 分配触发
    kGcCauseBackground,                 // 后台 GC
    kGcCauseExplicit,                   // 显式 System.gc()
    kGcCauseForTrim,                    // Trim Heap
    kGcCauseForInspect,                 // 调试用
    kGcCauseJitArenaFull,               // JIT Arena 满
    // ★ ART 17 新增 4 个
    kGcCauseForNativeAllocThrottled,    // Native 分配限流触发
    kSoftThreshold,                     // 软阈值触发（30%）
    kYoungGenerationCollect,            // 年轻代主动收集
    kBackgroundGenCC,                   // 后台分代 CC
    kGcCauseMax,                        // 哨兵
};
```

### 3.2 软阈值参数（★ ART 17 新增）

```cpp
// art/runtime/gc/collector/generational_cc.h（节选，AOSP 17）
class GenerationalCC : public GarbageCollector {
    // ★ ART 17 新增
    static constexpr size_t kSoftThresholdPercent = 30;  // 软阈值（剩余空间 30% 触发）
    static constexpr size_t kHardThresholdPercent = 10;  // 硬阈值

    // ★ ART 17 新增
    static constexpr size_t kMinSleepMs = 500;   // CPU 闲时 sleep
    static constexpr size_t kMaxSleepMs = 2000;  // CPU 忙时 sleep
    static constexpr size_t kDefaultSleepMs = 1000;

    // ★ ART 17 新增
    static constexpr int kUrgencyLow = 0;
    static constexpr int kUrgencyNormal = 1;
    static constexpr int kUrgencyHigh = 2;
    static constexpr int kUrgencyCritical = 3;
};
```

### 3.3 Heap 默认参数

```cpp
// art/runtime/gc/heap.h（AOSP 17 完整定义）
static constexpr size_t kMinHeapSize = 2 * MB;
static constexpr size_t kMaxHeapSize = 256 * MB;
static constexpr double kDefaultTargetUtilization = 0.75;
static constexpr size_t kDefaultYoungSize = 8 * MB;       // ★ ART 17 调大
static constexpr size_t kMaxYoungSize = 16 * MB;          // ★ ART 17 调大

// ★ ART 17 新增
static constexpr size_t kDefaultHeapTaskQueueLength = 5;
static constexpr size_t kMaxHeapTaskQueueLength = 20;
static constexpr int kDefaultHeapTaskDaemonPriority = -19;
```

---

## 四、ART 17 新增源码完整清单

### 4.1 GcCause 扩展（4 个新增）

| GcCause | 触发条件 | 对应文件 |
|:---|:---|:---|
| `kGcCauseForNativeAllocThrottled` | Native 限流 | `gc_cause.h` |
| `kSoftThreshold` | 软阈值 30% 触发 | `gc_cause.h` |
| `kYoungGenerationCollect` | 年轻代主动收集 | `gc_cause.h` |
| `kBackgroundGenCC` | 后台分代 CC | `gc_cause.h` |

### 4.2 HeapTask 扩展（2 个新增）

| HeapTask | 功能 | 文件 |
|:---|:---|:---|
| `BackgroundGenCCTask` | 后台分代 CC 任务 | `heap_task.h` |
| `SoftThresholdGCTask` | 软阈值触发任务 | `heap_task.h` |

### 4.3 Heap 方法扩展（8 个新增）

| 方法 | 功能 | 文件 |
|:---|:---|:---|
| `Heap::ShouldTriggerSoftThreshold` | 软阈值触发检查 | `heap.cc` |
| `Heap::CheckSoftThreshold` | 软阈值检查 | `heap.cc` |
| `Heap::ScheduleBackgroundGenCC` | 后台分代 CC 调度 | `heap.cc` |
| `Heap::OnNativeAllocationPressureThrottled` | Native 限流版本 | `heap.cc` |
| `Heap::ShouldThrottleNativeAllocGC` | 限流检查 | `heap.cc` |
| `Heap::ScheduleThrottledNativeGC` | 限流后重试 | `heap.cc` |
| `Heap::InitializeDynamicSleep` | 初始化动态 sleep | `heap_task_daemon.cc` |
| `Heap::UpdateSleepInterval` | 动态 sleep 调整 | `heap_task_daemon.cc` |
| `Heap::RecordGcForAllocFailure` | 记录分配失败 GC | `heap.cc` |

### 4.4 GenCC 方法扩展（1 个新增）

| 方法 | 功能 | 文件 |
|:---|:---|:---|
| `GenerationalCC::RunBackgroundPhases` | 后台分代 CC 主循环 | `generational_cc.cc` |

### 4.5 HeapTaskDaemon 方法扩展（2 个新增）

| 方法 | 功能 | 文件 |
|:---|:---|:---|
| `HeapTaskDaemon::UpdateSleepInterval` | 动态 sleep 调整 | `heap_task_daemon.cc` |
| `HeapTaskDaemon::ShouldTriggerSoftThreshold` | 软阈值触发 | `heap_task_daemon.cc` |

### 4.6 总计

- **GcCause**：9 → **11**（+2，新增 kSoftThreshold / kBackgroundGenCC 等）
- **HeapTask**：3 → **5**（+2）
- **Heap 方法**：+9 新增
- **GenCC 方法**：+1 新增
- **HeapTaskDaemon 方法**：+2 新增

---

## 五、版本演进（AOSP 5.0 → AOSP 17）

| 版本 | 关键变更 | 本附录章节 |
|:---|:---|:---|
| AOSP 5.0 | GC 调度基础（CMS 时代） | §3.1 |
| AOSP 8.0 | HeapTaskDaemon 引入 | §2.2 |
| AOSP 9.0 | CC GC 引入 | §1.1 |
| AOSP 10.0 | GenCC 引入（Minor / Major 分工） | §1.1 |
| AOSP 12.0 | Concurrent GC 优化 | §2.3 |
| AOSP 14.0 | kGcCauseForNativeAlloc 引入 | §3.1 |
| AOSP 16.0 | GenCC 强化（CPU 占用降低） | §1.1 |
| **AOSP 17.0** | **★ 软阈值 / 动态 sleep / BackgroundGenCC / 限流** | §4.1-4.6 |

---

## 六、跨系列源码引用

### 6.1 ART ↔ Linux Kernel 6.18 关联

| 维度 | ART 17 端 | Linux 6.18 端 | 关联路径 |
|:---|:---|:---|:---|
| **Native 内存** | NativeAllocationRegistry | sheaves 分配器 | `kernel/mm/slab_common.c` |
| **CPU 负载** | HeapTaskDaemon 动态 sleep | `kernel/sched/core.c` | `loadavg` / `cpu_util` |
| **io_uring** | heap dump 写盘 | `kernel/fs/io_uring.c` | 写盘延迟 -30% |

### 6.2 跨子模块引用

| 引用方向 | 来源 | 目标 | 关联内容 |
|:---|:---|:---|:---|
| 来自 | [02-HeapTaskDaemon](../02-HeapTaskDaemon.md) | `heap_task_daemon.cc` | HeapTaskDaemon 主循环 |
| 来自 | [03-ConcurrentGCTask](../03-ConcurrentGCTask.md) | `heap_task.h` | ConcurrentGCTask |
| 来自 | [04-GC_FOR_ALLOC路径](../04-GC_FOR_ALLOC路径.md) | `heap.cc` | Heap::TryToAllocate |
| 被引用 | [10-ART17分代GC强化专章 v2](../../10-ART17分代GC强化专章-v2.md) | `generational_cc.h` | kSoftThresholdPercent |
| 被引用 | [05-Generational-CC](../../05-Generational-CC/) | `generational_cc.cc` | GenCC 完整算法 |
| 被引用 | [01-可达性分析](../../01-基础理论/01-可达性分析.md) | `concurrent_copying.cc` | 可达性分析 |

---

## 七、源码阅读优先级（架构师视角）

| 优先级 | 文件 | 理由 |
|:---|:---|:---|
| ★★★★★ | `art/runtime/gc/heap.cc` | 整个 GC 系统的"总指挥" |
| ★★★★★ | `art/runtime/gc/collector/generational_cc.h` | ★ ART 17 软阈值定义 |
| ★★★★ | `art/runtime/gc/heap_task_daemon.cc` | ★ ART 17 动态 sleep 强化 |
| ★★★★ | `art/runtime/gc/heap_task.h` | ConcurrentGCTask / BackgroundGenCCTask / SoftThresholdGCTask |
| ★★★ | `art/runtime/gc/gc_cause.h` | 11 种 GcCause 完整定义 |
| ★★★ | `art/runtime/gc/collector/generational_cc.cc` | GenCC 完整实现 |
| ★★ | `art/runtime/gc/space/gen_space.cc` | Remembered Set + Card Table |
| ★★ | `art/runtime/gc/reference_processor.cc` | Reference 处理 |

---

> **下一篇**：[B-路径对账](B-路径对账.md) 详述 AOSP 版本对账、关键 commit、调试命令、跨引用矩阵。
