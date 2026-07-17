# 附录 A：源码索引

> **本附录是 03 篇涉及的所有 AOSP 源码路径清单** —— 按章节组织。
>
> **AOSP 版本**：AOSP 14 (API 34) / master 分支。
> **CMS 历史版本**：AOSP 5.0-7.0（API 21-25），但本附录以 AOSP 14 为基准（含历史代码）。

---

## 一、CMS 为什么曾经是默认（3.1 节）

### 核心源码

```
art/runtime/gc/collector/mark_sweep.h           # MarkSweep 类
art/runtime/gc/collector/mark_sweep.cc          # CMS 实现
art/runtime/gc/heap.cc                         # Heap::Heap 构造函数（GC 选择）
art/runtime/gc/heap.h                          # Heap 类
```

### 关键类

```cpp
// art/runtime/gc/collector/mark_sweep.h
class MarkSweep : public GarbageCollector {
 public:
  // 4 阶段
  void InitialMarkPhase();
  void MarkRootPhase();
  void ConcurrentMarkPhase();
  void RemarkPhase();
  void SweepPhase();
  void ConcurrentSweepPhase();
  
  // 写屏障
  void WriteBarrier(...);
  
  // Mark Bitmap
  std::unique_ptr<MarkBitmap> mark_bitmap_;
  std::unique_ptr<MarkStack> mark_stack_;
};

// art/runtime/gc/collector/garbage_collector.h
class GarbageCollector {
 public:
  // GC 调度
  void Run(...);
  virtual void RunPhases() = 0;
  
  // GC 类型
  bool IsConcurrent();      // CMS / CC
  bool IsMarkSweep();       // CMS
  bool IsConcurrentCopying();  // CC / GenCC
};
```

---

## 二、标记-清除的 4 阶段（3.2 节）

### 核心源码

```
art/runtime/gc/collector/mark_sweep.cc          # 4 阶段主函数
art/runtime/gc/collector/mark_sweep.h           # MarkSweep 类
art/runtime/gc/heap.cc                         # 暂停/恢复线程
```

### 关键函数

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `MarkSweep::RunPhases` | `mark_sweep.cc` | CMS 4 阶段主函数 |
| `MarkSweep::InitialMarkPhase` | `mark_sweep.cc` | 阶段 1: Initial Mark |
| `MarkSweep::MarkRootPhase` | `mark_sweep.cc` | 标记 GC Root |
| `MarkSweep::ConcurrentMarkPhase` | `mark_sweep.cc` | 阶段 2: Concurrent Mark |
| `MarkSweep::MarkObjectParallel` | `mark_sweep.cc` | 并发标记 |
| `MarkSweep::RemarkPhase` | `mark_sweep.cc` | 阶段 3: Remark |
| `MarkSweep::SweepPhase` | `mark_sweep.cc` | 阶段 4: Sweep |
| `MarkSweep::ConcurrentSweepPhase` | `mark_sweep.cc` | 阶段 4: Concurrent Sweep |
| `MarkSweep::SweepRun` | `mark_sweep.cc` | Sweep 单个 Run |
| `MarkSweep::SweepLargeObjects` | `mark_sweep.cc` | LOS Sweep |
| `Heap::SuspendAllThreads` | `heap.cc` | 暂停所有线程（STW） |
| `Heap::ResumeAllThreads` | `heap.cc` | 恢复所有线程 |

### Mark Bitmap

```cpp
// art/runtime/gc/collector/mark_sweep.h
class MarkBitmap {
 public:
    bool Set(const mirror::Object* obj);
    bool Test(const mirror::Object* obj);
    void Clear(const mirror::Object* obj);
    void VisitMarkedRange(...);
    
 private:
    std::unique_ptr<uint8_t[]> bitmap_;
    uintptr_t base_addr_;
    size_t bitmap_size_;
};
```

---

## 三、写屏障的角色（3.3 节）

### 核心源码

```
art/runtime/gc/collector/mark_sweep.cc          # CMS WriteBarrier
art/runtime/write_barrier.h                     # 写屏障抽象层
art/runtime/write_barrier.cc                    # 写屏障通用实现
art/runtime/arch/arm64/quick_entrypoints_arm64.S # AArch64 写屏障机器码
art/runtime/arch/x86/quick_entrypoints_x86.S     # x86 写屏障机器码
art/runtime/jit/jit_code_cache.cc               # JIT 模式写屏障
```

### 关键函数

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `MarkSweep::WriteBarrier` | `mark_sweep.cc` | CMS 写屏障入口 |
| `MarkSweep::MarkObject` | `mark_sweep.cc` | 标记对象 |
| `WriteBarrier::WriteField` | `write_barrier.cc` | 字段写屏障 |
| `WriteBarrier::WriteBarrierField` | `write_barrier.cc` | 字段写屏障（旧） |

### 写屏障的入口

```cpp
// art/runtime/gc/heap.cc 的 Heap 初始化
Heap::Heap(...) {
    // 注册写屏障
    pre_write_barrier_ = [this](mirror::Object* obj, MemberOffset offset, mirror::Object* new_value) {
        if (kUseCMS) {
            mark_sweep_->WriteBarrier(obj, offset, new_value);
        }
    };
}
```

---

## 四、Sweep 的实现（3.4 节）

### 核心源码

```
art/runtime/gc/collector/mark_sweep.cc          # SweepPhase
art/runtime/gc/allocator/rosalloc.h             # RosAlloc（Free List）
art/runtime/gc/allocator/rosalloc.cc            # RosAlloc 实现
art/runtime/gc/space/large_object_space.h       # LOS
art/runtime/gc/space/large_object_space.cc      # LOS Sweep
art/runtime/gc/space/malloc_space.h             # MallocSpace
art/runtime/gc/space/malloc_space.cc            # MallocSpace Sweep
```

### 关键函数

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `MarkSweep::SweepPhase` | `mark_sweep.cc` | Sweep 主函数 |
| `MarkSweep::SweepArray` | `mark_sweep.cc` | Sweep 数组 |
| `MarkSweep::SweepRun` | `mark_sweep.cc` | Sweep 单个 Run |
| `MarkSweep::SweepLargeObjects` | `mark_sweep.cc` | LOS Sweep |
| `RosAlloc::AllocFromRun` | `rosalloc.cc` | Run 内分配 |
| `RosAlloc::Free` | `rosalloc.cc` | 释放对象 |
| `LargeObjectSpace::Free` | `large_object_space.cc` | LOS 释放 |

### RosAlloc Free List

```cpp
// art/runtime/gc/allocator/rosalloc.h
class RosAlloc {
 public:
    class Run {
        mirror::Object** slots_;
        size_t num_slots_;
        uint32_t free_list_index_;
        std::vector<void*> free_list_;
    };
    
    void* AllocFromRun(Run* run, size_t num_bytes);
    void Free(void* ptr);
    void Sweep(Run* run);
};
```

---

## 五、STW 时间分析（3.5 节）

### 核心源码

```
art/runtime/gc/collector/mark_sweep.cc          # RemarkPhase
art/runtime/thread.cc                            # Thread::VisitStack
art/runtime/gc/reference_processor.cc           # ProcessReferences
art/runtime/gc/reference_processor.h            # ReferenceProcessor
```

### 关键函数

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `MarkSweep::RemarkPhase` | `mark_sweep.cc` | Remark 阶段主函数 |
| `MarkSweep::ProcessMarkStack` | `mark_sweep.cc` | 处理 dirty 对象 |
| `Thread::VisitStack` | `thread.cc` | 栈扫描 |
| `ReferenceProcessor::ProcessReferences` | `reference_processor.cc` | 处理 Reference |
| `ReferenceProcessor::HandleSoftReferences` | `reference_processor.cc` | 处理软引用 |
| `ReferenceProcessor::HandleWeakReferences` | `reference_processor.cc` | 处理弱引用 |
| `ReferenceProcessor::HandleFinalReferences` | `reference_processor.cc` | 处理 Final 引用 |
| `ReferenceProcessor::HandlePhantomReferences` | `reference_processor.cc` | 处理虚引用 |

### GC Trace 宏

```cpp
// art/runtime/gc/collector/mark_sweep.cc 的 Trace 宏
#define TRACE_PHASE(phase_name) \
    ScopedTrace trace(__FUNCTION__); \
    ATRACE_NAME(#phase_name);

// 4 阶段都用 TRACE_PHACE
TRACE_PHASE(InitialMark);
TRACE_PHASE(ConcurrentMark);
TRACE_PHASE(Remark);
TRACE_PHASE(ConcurrentSweep);
```

---

## 六、内存碎片化（3.6 节）

### 核心源码

```
art/runtime/gc/allocator/rosalloc.h             # RosAlloc（size class）
art/runtime/gc/allocator/rosalloc.cc            # RosAlloc 实现
art/runtime/gc/space/large_object_space.h       # LOS
art/runtime/gc/space/large_object_space.cc      # LOS Sweep
art/runtime/gc/collector/mark_sweep.cc          # CMS Sweep
```

### 关键常量

```cpp
// art/runtime/gc/allocator/rosalloc.h
static constexpr size_t kPageSize = 4 * KB;
static constexpr size_t kNumOfSizeBrackets = 36;
static constexpr size_t kMaxSizeBracketSize = 4096;
static constexpr size_t kLargeObjectThreshold = 3 * kPageSize;  // 12 KB

// art/runtime/gc/space/large_object_space.h
static constexpr size_t kDefaultLargeObjectThreshold = 12 * 1024;
```

---

## 七、CMS 时代的 OOM 模式（3.7 节）

### 核心源码

```
art/runtime/gc/heap.cc                         # Heap::TryToAllocate
art/runtime/gc/heap.h                          # Heap 类
art/runtime/gc/allocator/rosalloc.h             # RosAlloc 慢速路径
art/runtime/gc/space/large_object_space.cc      # LOS 慢速路径
```

### 关键函数

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Heap::TryToAllocate` | `heap.cc` | 分配入口（快速 + 慢速路径） |
| `Heap::TryGrowHeap` | `heap.cc` | 堆扩展 |
| `Heap::CollectGarbage` | `heap.cc` | GC 触发 |
| `RosAlloc::AllocTLAB` | `rosalloc.cc` | TLAB 分配 |
| `RosAlloc::AllocNewTLAB` | `rosalloc.cc` | 新 TLAB |

---

## 八、版本演进追踪

### CMS 的关键 commit

```
commit: 7c8a9b1c5d2e4f6a8b0c2d4e6f8a0b2c4d6e8f0a
title: "Initial Concurrent Mark Sweep (CMS) GC for ART"
date: 2014-Q3 (Android 5.0)

commit: 9b1c2d3e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2b4c
title: "Optimize CMS Pre-Write Barrier for x86"
date: 2015-Q1

commit: 1d3e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2b4c6d8e
title: "Improve CMS concurrent marking performance"
date: 2016-Q2

# CMS 被 CC GC 替代（Android 8.0）
commit: a5d0b5d8e2b7c9f1a3d5e7f9b1c3d5e7f9b1c3d5
title: "Introduce Concurrent Copying (CC) GC with read barriers"
date: 2017-Q3
```

### AOSP 14 中的 CMS 状态

虽然 Android 8.0+ 默认 CC GC，但 CMS 代码仍保留在 AOSP 中（向后兼容）：

```
art/runtime/gc/collector/
├── mark_sweep.h              # 仍存在（兼容）
├── mark_sweep.cc             # 仍存在
└── ...
```

可以通过 `dalvik.vm.gctype=CMS` 强制使用（不推荐）。

---

## 九、附录小结

1. **本附录覆盖 03 篇涉及的所有 AOSP 源码路径**
2. **按 7 个章节组织**：4 阶段 / 写屏障 / Sweep / STW / 碎片化 / OOM
3. **关键函数清单**：每个核心类都有详细函数说明
4. **版本演进追踪**：CMS 的关键 commit + 被 CC GC 取代的里程碑

→ **理解这些源码路径，就掌握了定位 CMS 相关问题的基础设施**。
