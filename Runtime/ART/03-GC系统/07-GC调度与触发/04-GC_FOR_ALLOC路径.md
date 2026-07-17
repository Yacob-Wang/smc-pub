# 7.4 分配触发的 GC：GC_FOR_ALLOC 路径

> **本节回答一个根本问题**：业务线程分配对象失败时，ART 怎么触发 GC？GC_FOR_ALLOC 完整流程是什么？
>
> **答案**：**TLAB 失败 → 全局分配失败 → 触发 kGcCauseForAlloc 同步 GC → 重试分配 → 仍失败则 OOM**。

---

## 一、GC_FOR_ALLOC 的触发流程

### 7.4.1 GC_FOR_ALLOC 完整流程

```
业务线程分配对象：Object obj = new Object()
    │
    ▼
1. TLAB 快速路径
    │
    ├─── TLAB 有空间 → bump pointer 分配（~1 ns）
    │
    └─── TLAB 用完 ↓
2. 申请新 TLAB（TLAB 慢速路径）
    │
    ├─── 申请成功 → 在新 TLAB 分配（~10 ns）
    │
    └─── 申请失败 ↓
3. 触发 Heap::TryToAllocate
    │
    ├─── 全局池有空间 → 分配（~50 ns）
    │
    └─── 全局池空 ↓
4. 触发 kGcCauseForAlloc 同步 GC
    │
    ├─── GC 成功释放内存
    │   │
    │   ▼
    │   5. 重试分配
    │      │
    │      ├─── 成功 → 返回对象指针
    │      │
    │      └─── 失败 ↓
    │   6. OOM
    │
    └─── GC 后仍无内存 ↓
5. OOM
```

### 7.4.2 GC_FOR_ALLOC 的同步特性

```
GC_FOR_ALLOC 的关键特性：

1. 同步阻塞
   - 业务线程调用 Heap::CollectGarbage
   - 业务线程等待 GC 完成
   - GC 在业务线程上执行（不是 HeapTaskDaemon）

2. 必须快速完成
   - 业务线程已经阻塞
   - GC 时间直接影响用户体验
   - ART 选择最快的 GC 算法

3. 触发原因记录
   - GcCause = kGcCauseForAlloc
   - APM 可以精准定位
```

---

## 二、Heap::TryToAllocate 的源码

### 7.4.3 TryToAllocate 的完整实现

```cpp
// art/runtime/gc/heap.cc 的 Heap::TryToAllocate（简化版）
mirror::Object* Heap::TryToAllocate(Thread* self, size_t byte_count, 
                                     bool grow, bool* out_of_memory) {
    *out_of_memory = false;
    
    // 1. 快速路径：尝试在当前堆上分配
    mirror::Object* obj = allocation_space_->Alloc(self, byte_count, ...);
    if (obj != nullptr) return obj;
    
    // 2. 尝试扩展堆（如果允许）
    if (grow) {
        size_t new_footprint = CalculateFootprint();
        if (ChangeSoftReferenceLimit(new_footprint)) {
            obj = allocation_space_->Alloc(self, byte_count, ...);
            if (obj != nullptr) return obj;
        }
    }
    
    // 3. 触发 GC_FOR_ALLOC
    CollectGarbage(kGcCauseForAlloc, false);
    
    // 4. GC 后重试
    obj = allocation_space_->Alloc(self, byte_count, ...);
    if (obj != nullptr) return obj;
    
    // 5. 仍失败 → OOM
    *out_of_memory = true;
    return nullptr;
}
```

### 7.4.4 CollectGarbage (kGcCauseForAlloc)

```cpp
// art/runtime/gc/heap.cc 的 Heap::CollectGarbage（简化版）
void Heap::CollectGarbage(GcCause cause, bool clear_soft_references) {
    // 1. 记录 GC 触发原因
    last_gc_cause_ = cause;
    
    // 2. 暂停所有 mutator 线程（STW 开始）
    SuspendAllThreads();
    
    // 3. 选择 GC 类型
    GcType gc_type = SelectGcTypeForCause(cause);
    
    // 4. 执行 GC
    switch (gc_type) {
        case kMinorGc:
            concurrent_copying_->MinorGc();
            break;
        case kMajorGc:
            concurrent_copying_->RunPhases();
            break;
        default:
            break;
    }
    
    // 5. 处理 Reference（Soft/Weak/Final/Phantom）
    reference_processor_->ProcessReferences(clear_soft_references);
    
    // 6. 恢复 mutator 线程（STW 结束）
    ResumeAllThreads();
}
```

---

## 三、GC_FOR_ALLOC 的 STW 时间

### 7.4.5 STW 时间分布

```
GC_FOR_ALLOC 的 STW 时间：

CMS：
  Initial Mark（STW）~5ms
  + Remark（STW）~50ms
  ───────────────────
  总 STW ~55ms

CC：
  Initialize（STW）~2ms
  + Reclaim（STW）~1ms
  ───────────────────
  总 STW < 5ms

GenCC Minor：
  Minor GC（STW）~0.5ms
  ───────────────────
  总 STW < 0.5ms
```

### 7.4.6 STW 不可控的问题

```
GC_FOR_ALLOC 的 STW 不可控：

1. CMS 时代
   - Remark 阶段可能 50-200ms
   - 用户感知明显卡顿
   - ART-05 时代的主要性能问题

2. CC GC 时代
   - STW < 5ms，几乎不可感知
   - 但仍可能因为 dirty objects 太多而抖动

3. GenCC 时代
   - Minor GC < 0.5ms
   - Major GC 偶发但 < 50ms
   - 大多数 GC_FOR_ALLOC 走 Minor GC
```

---

## 四、GC_FOR_ALLOC 的优化策略

### 7.4.7 优化 1：避免分配失败

```java
// ✅ 好：避免触发 GC_FOR_ALLOC
public class OptimizedClass {
    // 1. 预分配（避免运行时分配）
    private final Object[] cache = new Object[100];
    
    // 2. 复用对象
    private final StringBuilder sb = new StringBuilder(1024);
    
    // 3. 限制缓存大小
    private final LruCache<String, Object> cache = new LruCache<>(100);
}
```

### 7.4.8 优化 2：调大堆

```bash
# 调大 heapgrowthlimit（避免频繁 GC_FOR_ALLOC）
adb shell setprop dalvik.vm.heapgrowthlimit 384m  # 从 256m 调到 384m

# 调大 heapsize（largeHeap）
# AndroidManifest.xml: android:largeHeap="true"
```

### 7.4.9 优化 3：触发后台 GC

```cpp
// 业务层主动触发后台 GC
Runtime.getRuntime().gc();
// ↑ 触发 ConcurrentGCTask（不阻塞业务线程）
// ↑ HeapTaskDaemon 线程执行

// 但 ART 14+ 通常不需要手动触发
// 后台定时 GC 已经足够
```

---

## 五、GC_FOR_ALLOC 的工程监控

### 7.5.10 监控 GC_FOR_ALLOC 频率

```bash
# 1. 看 kGcCauseForAlloc 频率
adb logcat -s "art" | grep "kGcCauseForAlloc" | wc -l
# 1 分钟内的次数

# 2. 看每次 GC_FOR_ALLOC 的堆使用率
adb logcat -s "art" | grep "Cause=kGcCauseForAlloc" -A 5
```

### 7.5.11 异常的诊断

| 频率 | 状态 | 根因 | 修复 |
|:---|:---|:---|:---|
| < 1/分钟 | 正常 | — | — |
| 1-5/分钟 | 警告 | 堆偏小 / 频繁分配 | 调大堆 + 优化分配 |
| 5-20/分钟 | 严重 | 内存泄漏 / 大量临时对象 | 修复泄漏 |
| > 20/分钟 | 紧急 | OOM 即将发生 | 紧急修复 |

### 7.5.12 APM 监控代码

```java
public class GcForAllocMonitor {
    // 监控 GC_FOR_ALLOC 频率
    @Scheduled(fixedRate = 60000)
    public void monitor() {
        // 1. 读取最近 1 分钟的 GC 日志
        int forAllocCount = countForAllocInLastMinute();
        
        // 2. 上报到 APM
        apmClient.report("gc.foralloc.count", forAllocCount);
        
        // 3. 告警
        if (forAllocCount > 10) {
            apmClient.alert("gc.foralloc.high", "GC_FOR_ALLOC > 10/min");
        }
        
        // 4. 触发紧急检查
        if (forAllocCount > 30) {
            triggerMemoryAnalysis();
        }
    }
}
```

---

## 六、GC_FOR_ALLOC 的源码索引

### 7.5.13 核心源码路径

```
art/runtime/gc/heap.h                  # Heap 类
art/runtime/gc/heap.cc                 # Heap::TryToAllocate
art/runtime/gc/heap.cc                 # Heap::CollectGarbage
art/runtime/gc/heap.cc                 # Heap::AllocateInternalWithGc
art/runtime/gc/collector/concurrent_copying.cc # CC GC 主循环
```

### 7.5.14 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Heap::TryToAllocate` | `heap.cc` | 分配入口（快速 + 慢速） |
| `Heap::AllocateInternalWithGc` | `heap.cc` | 触发 GC 的分配 |
| `Heap::CollectGarbage` | `heap.cc` | 触发 GC |
| `ConcurrentCopying::MinorGc` | `concurrent_copying.cc` | Minor GC（GenCC） |
| `ConcurrentCopying::RunPhases` | `concurrent_copying.cc` | Major GC |

---

## 七、本节小结

1. **GC_FOR_ALLOC = 同步阻塞 GC**：业务线程触发并等待
2. **触发流程**：TLAB 失败 → 全局分配失败 → 触发 GC → 重试分配 → OOM
3. **STW 时间**：CMS 55ms / CC 5ms / GenCC Minor 0.5ms
4. **优化方向**：避免分配失败 / 调大堆 / 触发后台 GC
5. **监控**：kGcCauseForAlloc 频率，超过 10/分钟告警

→ **理解 GC_FOR_ALLOC，就理解了"业务线程怎么触发 GC"**。

---

## 跨节引用

**本节被以下章节引用**：
- [7.5 Native 触发 GC](./05-Native触发GC.md) —— Native 触发的 GC_FOR_NATIVE_ALLOC
- 09 篇诊断 —— OOM 排查

**本节引用**：
- [7.1 9 种 GcCause](./01-9种GcCause.md) —— kGcCauseForAlloc
- [7.2 HeapTaskDaemon](./02-HeapTaskDaemon.md) —— HeapTaskDaemon
- 02 篇 2.7 慢速路径 —— 分配失败路径
