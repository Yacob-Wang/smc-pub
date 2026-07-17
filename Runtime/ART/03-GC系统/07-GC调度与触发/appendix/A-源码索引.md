# 附录 A：源码索引（GC 调度与触发）

## 一、核心文件

```
art/runtime/gc/heap.h                  # Heap 类（含 task_daemon_、gc_cause_）
art/runtime/gc/heap.cc                 # Heap 实现
art/runtime/gc/gc_cause.h              # GcCause 枚举
art/runtime/gc/heap_task.h             # HeapTask 抽象类
art/runtime/gc/heap_task_daemon.h     # HeapTaskDaemon 类
art/runtime/gc/heap_task_daemon.cc    # HeapTaskDaemon 实现
art/runtime/gc/heap_task.h             # ConcurrentGCTask / TrimHeapTask
art/runtime/gc/collector/concurrent_copying.cc # CC GC 主循环
```

## 二、关键函数

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Heap::CollectGarbage` | `heap.cc` | GC 触发入口 |
| `Heap::TryToAllocate` | `heap.cc` | 分配 + 慢速路径 |
| `Heap::RequestConcurrentGC` | `heap.cc` | 请求后台 GC |
| `Heap::ConcurrentGC` | `heap.cc` | 执行后台 GC |
| `Heap::Trim` | `heap.cc` | Trim Heap |
| `Heap::ChangeSoftReferenceLimit` | `heap.cc` | 调整 SoftReference 阈值 |
| `Heap::OnNativeAllocationPressure` | `heap.cc` | Native 压力回调 |
| `HeapTaskDaemon::Run` | `heap_task_daemon.cc` | HeapTaskDaemon 主循环 |
| `ConcurrentGCTask::Run` | `heap_task.h` | 后台 GC 任务 |
| `TrimHeapTask::Run` | `heap_task.h` | Trim Heap 任务 |
| `NativeAllocGCTask::Run` | `heap_task.h` | Native 触发的 GC 任务 |
| `ConcurrentCopying::MinorGc` | `concurrent_copying.cc` | Minor GC |
| `ConcurrentCopying::RunPhases` | `concurrent_copying.cc` | Major GC |

## 三、关键常量

```cpp
// art/runtime/gc/gc_cause.h
enum GcCause {
    kGcCauseNone,
    kGcCauseForAlloc,
    kGcCauseForNativeAlloc,
    kGcCauseBackground,
    kGcCauseExplicit,
    kGcCauseForTrim,
    kGcCauseForInspect,
    kGcCauseJitArenaFull,
    kGcCauseMax,
};

// 默认参数
static constexpr size_t kMinHeapSize = 2 * MB;
static constexpr size_t kMaxHeapSize = 256 * MB;
static constexpr double kDefaultTargetUtilization = 0.75;
```

## 四、版本演进

| 版本 | 变更 |
|:---|:---|
| AOSP 5.0 | GC 调度基础 |
| AOSP 8.0 | HeapTaskDaemon 引入 |
| AOSP 10.0 | GenCC 引入（Minor/Major 分工） |
| AOSP 14.0 | kGcCauseForNativeAlloc / rbcc |
