# 7.3 ConcurrentGCTask 的提交与执行

> **本节回答一个根本问题**：后台 GC 任务怎么提交？怎么执行？和同步 GC 有什么区别？
>
> **答案**：**后台 GC 通过 ConcurrentGCTask 提交，由 HeapTaskDaemon 异步执行，不阻塞业务线程**。

---

## 一、ConcurrentGCTask 的定义

### 7.3.1 ConcurrentGCTask 的作用

```
ConcurrentGCTask 的核心职责：

1. 异步执行后台 GC
   - 不阻塞业务线程
   - HeapTaskDaemon 线程执行

2. 标识 GC 触发原因
   - GcCause（kGcCauseBackground / kGcCauseForNativeAlloc 等）
   - 决定 GC 策略

3. 传递 GC 参数
   - 目标字节数
   - 软引用处理标志
   - 紧急程度
```

### 7.3.2 ConcurrentGCTask 的源码

```cpp
// art/runtime/gc/heap_task.h
class ConcurrentGCTask : public HeapTask {
public:
    ConcurrentGCTask(uint64_t target_byte_count, GcCause cause)
        : target_byte_count_(target_byte_count),
          cause_(cause) {}
    
    void Run(ThreadPool* thread_pool) override {
        // 1. 获取 Heap 引用
        Heap* heap = Runtime::Current()->GetHeap();
        
        // 2. 执行并发 GC
        if (cause_ == kGcCauseForNativeAlloc) {
            // Native 触发的 GC
            heap->ConcurrentGC(cause_);
        } else {
            // 普通后台 GC
            heap->ConcurrentGC(cause_, target_byte_count_);
        }
    }
    
private:
    uint64_t target_byte_count_;  // 目标字节数
    GcCause cause_;               // GC 原因
};
```

---

## 二、ConcurrentGCTask 的提交

### 7.3.3 提交入口

```cpp
// art/runtime/gc/heap.cc
void Heap::RequestConcurrentGC(GcCause cause, uint64_t target_byte_count) {
    // 1. 检查是否已经有 pending 的并发 GC
    if (concurrent_gc_pending_) {
        return;  // 已经有 pending，不重复提交
    }
    
    // 2. 标记 pending
    concurrent_gc_pending_ = true;
    
    // 3. 创建 ConcurrentGCTask
    auto task = std::make_unique<ConcurrentGCTask>(target_byte_count, cause);
    
    // 4. 提交到 HeapTaskDaemon
    task_daemon_->AddTask(std::move(task));
}
```

### 7.3.4 触发 ConcurrentGC 的场景

```cpp
// 1. 定时后台 GC（最常见）
void Heap::CheckConcurrentGC() {
    // 计算堆使用率
    double usage = GetHeapUsage();
    
    if (usage > concurrent_start_threshold_) {
        // 触发后台 GC
        RequestConcurrentGC(kGcCauseBackground, ...);
    }
}

// 2. Native 内存压力
void Heap::OnNativeAllocationPressure() {
    RequestConcurrentGC(kGcCauseForNativeAlloc, ...);
}

// 3. Trim Heap 后
void Heap::Trim() {
    RequestConcurrentGC(kGcCauseForTrim, ...);
}

// 4. JIT Arena 满
void Heap::OnJitArenaFull() {
    RequestConcurrentGC(kGcCauseJitArenaFull, ...);
}
```

### 7.3.5 HeapTaskDaemon 与 ConcurrentGCTask 的协作

```
业务线程触发后台 GC：

1. 业务线程调用 Heap::RequestConcurrentGC(cause, target)
   │
2. 检查 concurrent_gc_pending_
   │
3. 创建 ConcurrentGCTask
   │
4. HeapTaskDaemon::AddTask(task)
   │  └─ task_queue 接收 task
   │  └─ task_queue_condition_.notify_one()
   │
5. HeapTaskDaemon 线程被唤醒
   │
6. HeapTaskDaemon::Run() 取出 task
   │
7. ConcurrentGCTask::Run(thread_pool) 执行
   │
8. GC 在 HeapTaskDaemon 线程上执行
   │  └─ 与业务线程并行
   │
9. GC 完成 → concurrent_gc_pending_ = false
```

---

## 三、ConcurrentGC 与同步 GC 的对比

### 7.3.6 同步 GC vs 后台 GC

| 维度 | 同步 GC | 后台 GC |
|:---|:---|:---|
| **执行线程** | 业务线程 | HeapTaskDaemon 线程 |
| **阻塞业务** | 是（业务线程等待） | 否（与业务并行） |
| **触发原因** | `kGcCauseForAlloc` / `kGcCauseExplicit` | `kGcCauseBackground` / `kGcCauseForNativeAlloc` / `kGcCauseForTrim` |
| **STW 时间** | 长（业务线程必须等） | 短（基本恒定） |
| **GC 类型** | Major GC | ConcurrentMajorGc |
| **执行方式** | 串行（一次完成） | 分阶段（Initialize / Marking / Reclaim） |

### 7.3.7 后台 GC 的执行流程

```cpp
// Heap::ConcurrentGC（简化版）
void Heap::ConcurrentGC(GcCause cause, uint64_t target_byte_count) {
    // 1. 选择 GC 类型
    GcType gc_type = SelectGcTypeForConcurrent(cause);
    
    // 2. 执行 GC
    switch (gc_type) {
        case kConcurrentMajorGc:
            // 后台全堆 GC
            concurrent_copying_->RunPhases();
            break;
        case kMinorGc:
            // 后台 Minor GC（GenCC）
            concurrent_copying_->MinorGc();
            break;
        default:
            break;
    }
    
    // 3. 标记完成
    concurrent_gc_pending_ = false;
}
```

---

## 四、ConcurrentGC 的工程影响

### 7.3.8 后台 GC 的优势

```
后台 GC 的工程价值：

1. 不阻塞业务线程
   - 业务线程可以继续分配/执行
   - 用户感知不到卡顿

2. STW 时间短
   - Initialize: ~2ms
   - Reclaim: ~1ms
   - 总 STW < 5ms

3. 提前触发
   - 堆使用率 75% 触发
   - 避免 kGcCauseForAlloc 同步 GC
```

### 7.3.9 后台 GC 的代价

```
后台 GC 的代价：

1. CPU 占用
   - GC 线程占用 CPU
   - 与业务线程竞争 CPU

2. 内存占用
   - 双空间（to-space）
   - 临时数据结构

3. 延迟 GC 完成
   - 业务线程仍在分配
   - GC 完成后可能立即又需要 GC
```

### 7.3.10 触发频率的监控

```bash
# 1. 看后台 GC 频率
adb logcat -s "art" | grep "kGcCauseBackground" | wc -l

# 2. 看每次 GC 的目标字节数
adb logcat -s "art" | grep "target_byte_count"
```

---

## 五、ConcurrentGCTask 的工程坑点

### 7.3.11 坑点 1：频繁触发后台 GC

```
问题：堆使用率高 → 频繁触发后台 GC
影响：CPU 占用高，电量消耗大

诊断：
  adb logcat -s "art" | grep "Background"
  # 输出：1 分钟内 ~30 次 → 异常

修复：
  - 调高 concurrent_start_threshold（减少触发频率）
  - 优化内存使用
```

### 7.3.12 坑点 2：后台 GC 与同步 GC 冲突

```
问题：后台 GC 进行中，业务线程触发同步 GC
影响：GC 重复执行，性能浪费

诊断：
  - concurrent_gc_pending_ 检查失效
  - ART 14+ 修复

修复：
  - 检查 ART 版本
  - 升级到 ART 14+
```

### 7.3.13 坑点 3：Native 触发的 GC 不及时

```
问题：Native 内存压力大，但 Java GC 触发慢
影响：系统 OOM

修复：
  - ART 14+ 优化 NativeAlloc 触发 GC
  - 调整 kGcCauseForNativeAlloc 的优先级
```

---

## 六、ConcurrentGCTask 的源码索引

### 7.3.14 核心源码路径

```
art/runtime/gc/heap.h                         # Heap 类（含 RequestConcurrentGC）
art/runtime/gc/heap.cc                        # Heap 实现
art/runtime/gc/heap_task.h                    # ConcurrentGCTask 类
art/runtime/gc/heap_task_daemon.h            # HeapTaskDaemon 类
art/runtime/gc/collector/concurrent_copying.cc # CC GC 主循环
```

### 7.3.15 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Heap::RequestConcurrentGC` | `heap.cc` | 请求后台 GC |
| `Heap::ConcurrentGC` | `heap.cc` | 执行后台 GC |
| `ConcurrentGCTask::Run` | `heap_task.h` | 后台 GC 任务执行 |
| `Heap::CheckConcurrentGC` | `heap.cc` | 检查并触发后台 GC |
| `Heap::OnNativeAllocationPressure` | `heap.cc` | Native 内存压力触发 |

---

## 七、本节小结

1. **ConcurrentGCTask 是后台 GC 的任务封装**：通过 HeapTaskDaemon 异步执行
2. **不阻塞业务线程**：HeapTaskDaemon 线程执行 GC
3. **多种触发方式**：定时 / NativeAlloc / Trim / JIT
4. **后台 GC 优势**：不阻塞 + STW 短
5. **后台 GC 代价**：CPU 占用 + 内存占用

→ **理解 ConcurrentGCTask，就理解了"后台 GC 怎么异步执行"**。

---

## 跨节引用

**本节被以下章节引用**：
- [7.5 Native 触发 GC](./05-Native触发GC.md) —— NativeAllocGCTask
- [7.7 Background vs Foreground](./07-Background-Foreground.md) —— 后台 vs 前台
- [7.8 GC 线程模型](./08-GC线程模型.md) —— 完整线程模型

**本节引用**：
- [7.2 HeapTaskDaemon](./02-HeapTaskDaemon.md) —— HeapTaskDaemon 主循环
- 04/05 篇 —— CC GC / GenCC 算法
