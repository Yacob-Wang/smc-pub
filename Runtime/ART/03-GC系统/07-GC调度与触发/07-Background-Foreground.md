# 7.7 Background GC 与前台 GC 的优先级

> **本节回答一个根本问题**：后台 GC 和前台 GC 的优先级怎么排序？HeapTaskDaemon 怎么协调？
>
> **答案**：**后台 GC 用 HeapTaskDaemon 异步执行，前台 GC 在业务线程同步执行**——两者通过 GcCause 和优先级区分。

---

## 一、Background GC 与 Foreground GC 的对比

### 7.7.1 基本定义

| 维度 | Background GC | Foreground GC |
|:---|:---|:---|
| **执行线程** | HeapTaskDaemon 线程 | 业务线程 |
| **阻塞业务** | 否 | 是 |
| **GC 类型** | ConcurrentMajorGc / kMinorGc | kMajorGc |
| **触发 GcCause** | kGcCauseBackground / kGcCauseForNativeAlloc / kGcCauseForTrim | kGcCauseForAlloc / kGcCauseExplicit |
| **用户感知** | 几乎无感知 | 可能卡顿 |
| **CPU 占用** | 占用业务 CPU | 不占用业务 CPU |

### 7.7.2 Background GC 的优势

```
Background GC 的优势：

1. 不阻塞业务线程
   - HeapTaskDaemon 线程执行
   - 业务线程继续分配对象
   - 用户感知不到

2. STW 时间短
   - Initialize: ~2ms
   - Reclaim: ~1ms
   - 总 STW < 5ms

3. 提前触发
   - 堆使用率 75% 触发
   - 避免 kGcCauseForAlloc 同步 GC
   - 预防 OOM
```

### 7.7.3 Foreground GC 的必要性

```
Foreground GC 的必要性：

1. 业务线程必须分配对象
   - 没有空闲空间
   - 必须立即释放内存
   - 不能等后台 GC 完成

2. kGcCauseForAlloc 必须同步
   - 业务线程阻塞
   - 必须尽快完成
   - 通常用 Minor GC（< 0.5ms）

3. kGcCauseExplicit
   - 业务代码主动调用
   - 同步等待
```

---

## 二、GC 优先级机制

### 7.7.4 优先级排序

```cpp
// ART 中的 GC 优先级（高 → 低）

// 1. kGcCauseForAlloc（最高优先级）
//    业务线程阻塞中，必须尽快 GC

// 2. kGcCauseForNativeAlloc（高优先级）
//    Native 内存压力大，需要释放 Java 堆

// 3. kGcCauseBackground（普通优先级）
//    定时后台 GC

// 4. kGcCauseForTrim（低优先级）
//    主动 Trim Heap

// 5. kGcCauseJitArenaFull（低优先级）
//    JIT 编译触发

// 6. kGcCauseExplicit（最低优先级）
//    业务代码主动调用
```

### 7.7.5 HeapTaskDaemon 的任务调度

```cpp
// art/runtime/gc/heap_task_daemon.cc
void HeapTaskDaemon::ScheduleTask(std::unique_ptr<HeapTask> task) {
    {
        std::lock_guard<std::mutex> lock(task_queue_mutex_);
        
        // 1. 高优先级任务插队
        if (task->IsHighPriority()) {
            tasks_.push_front(std::move(task));
        } else {
            // 2. 普通任务追加到末尾
            tasks_.push_back(std::move(task));
        }
    }
    task_queue_condition_.notify_one();
}
```

### 7.7.6 任务优先级判定

```cpp
// HeapTask 的优先级
class HeapTask {
public:
    virtual bool IsHighPriority() const {
        // 默认普通优先级
        return false;
    }
};

// NativeAllocGCTask 是高优先级
class NativeAllocGCTask : public HeapTask {
    bool IsHighPriority() const override {
        return true;  // NativeAlloc 高优先级
    }
};
```

---

## 三、Background GC 的调度策略

### 7.7.7 定时触发

```cpp
// art/runtime/gc/heap.cc
void Heap::CheckConcurrentGC() {
    // 1. 计算堆使用率
    double usage = GetHeapUsage();
    
    // 2. 触发条件
    if (usage > concurrent_start_threshold_) {
        // 触发后台 GC
        RequestConcurrentGC(kGcCauseBackground, ...);
    }
    
    // 3. ART 14+ 也支持主动调度
    if (needs_concurrent_gc_) {
        RequestConcurrentGC(kGcCauseBackground, ...);
    }
}
```

### 7.7.8 并发度限制

```cpp
// HeapTaskDaemon 同一时间只执行一个 GC 任务
void HeapTaskDaemon::Run() {
    while (true) {
        std::unique_ptr<HeapTask> task;
        {
            std::lock_guard<std::mutex> lock(task_queue_mutex_);
            while (tasks_.empty() && !shutting_down_) {
                task_queue_condition_.wait(lock);
            }
            if (shutting_down_) return;
            task = std::move(tasks_.front());
            tasks_.pop_front();
        }
        
        // 串行执行
        task->Run(this);
        
        // GC 完成 → 唤醒可能等待的线程
        pending_gc_done_.notify_all();
    }
}
```

### 7.7.9 任务优先级冲突的处理

```
当多个 GC 任务同时在队列时：

任务队列：
  [Foreground GC（业务线程直接执行，不在队列）]
  [NativeAllocGCTask（高优先级，前插）]
  [ConcurrentGCTask（普通优先级，追加）]
  [TrimHeapTask（普通优先级，追加）]

HeapTaskDaemon 处理顺序：
  1. NativeAllocGCTask（先执行，因为高优先级）
  2. ConcurrentGCTask
  3. TrimHeapTask
```

---

## 四、Background GC 的工程影响

### 7.7.10 后台 GC 的优势利用

```java
// ✅ 好：让后台 GC 触发而不是同步 GC
public class OptimizedClass {
    // 1. 主动释放资源（在生命周期结束时）
    public void close() {
        // 显式释放资源
        // 让 HeapTrim 生效
    }
}

// ✅ 好：监听 onTrimMemory
public class MyApplication extends Application {
    @Override
    public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        // 主动清理
    }
}
```

### 7.7.11 同步 GC 的优化

```java
// ❌ 避免：频繁触发同步 GC
public class BadClass {
    private static Object obj;  // 强引用，长寿对象
    
    public void allocate() {
        obj = new Object();  // 每次调用都在 Young Gen
        // 频繁分配 → 触发 Minor GC
        // → 触发 Major GC（Old Gen 满）
    }
}

// ✅ 优化：减少对象分配
public class GoodClass {
    private final Object obj = new Object();  // 一次性创建
    
    public void allocate() {
        // 不分配新对象，复用
    }
}
```

### 7.7.12 后台 GC 的限制

```
后台 GC 的限制：

1. CPU 占用
   - 与业务线程竞争 CPU
   - 可能影响业务线程性能

2. 内存占用
   - 双空间（to-space）
   - 临时数据结构

3. 触发延迟
   - 定时触发，不能立即 GC
   - 如果业务分配很快，可能来不及
```

---

## 五、Background GC 的监控

### 7.7.13 监控 Background GC 频率

```bash
# 1. 看 Background GC 频率
adb logcat -s "art" | grep "kGcCauseBackground" | wc -l
# 1 小时内的次数

# 2. 看 Foreground GC 频率（kGcCauseForAlloc）
adb logcat -s "art" | grep "kGcCauseForAlloc" | wc -l
# 1 分钟内的次数

# 3. 比例计算
# Foreground GC 比例 = kGcCauseForAlloc / (Background GC + Foreground GC)
# 期望：< 10%（大部分是后台 GC）
```

### 7.7.14 异常诊断

| 指标 | 期望 | 警告 | 严重 |
|:---|:---|:---|:---|
| Foreground GC 比例 | < 10% | 10-30% | > 30% |
| Background GC 频率 | 5-10/分钟 | 10-30/分钟 | > 30/分钟 |
| Background GC STW | < 5ms | 5-20ms | > 20ms |
| HeapTaskDaemon 队列 | < 5 个 | 5-20 个 | > 20 个 |

### 7.7.15 APM 监控代码

```java
public class GcPriorityMonitor {
    @Scheduled(fixedRate = 60000)
    public void monitor() {
        // 1. 统计 Background GC 和 Foreground GC 频率
        int bgCount = countBackgroundGcInLastMinute();
        int fgCount = countForegroundGcInLastMinute();
        
        // 2. 计算比例
        double fgRatio = (double) fgCount / (bgCount + fgCount);
        
        // 3. 上报
        apmClient.report("gc.fg.ratio", fgRatio);
        
        // 4. 告警
        if (fgRatio > 0.3) {
            apmClient.alert("gc.fg.high", "Foreground GC ratio > 30%");
        }
    }
}
```

---

## 六、Background vs Foreground 的源码索引

### 7.7.16 核心源码路径

```
art/runtime/gc/heap.h                  # Heap 类
art/runtime/gc/heap.cc                 # Heap::CollectGarbage
art/runtime/gc/heap_task.h            # HeapTask 抽象类
art/runtime/gc/heap_task_daemon.cc    # HeapTaskDaemon
art/runtime/gc/heap_task_daemon.h     # HeapTaskDaemon
```

### 7.7.17 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Heap::CollectGarbage` | `heap.cc` | GC 入口 |
| `Heap::RequestConcurrentGC` | `heap.cc` | 请求后台 GC |
| `Heap::CheckConcurrentGC` | `heap.cc` | 检查后台 GC |
| `HeapTaskDaemon::ScheduleTask` | `heap_task_daemon.cc` | 调度任务 |
| `HeapTask::IsHighPriority` | `heap_task.h` | 优先级判定 |

---

## 七、本节小结

1. **Background GC = 异步 GC**：HeapTaskDaemon 执行，不阻塞业务
2. **Foreground GC = 同步 GC**：业务线程执行，必须快速完成
3. **优先级**：kGcCauseForAlloc > kGcCauseForNativeAlloc > kGcCauseBackground > 其他
4. **HeapTaskDaemon 串行执行**：同一时间一个 GC 任务
5. **监控**：Foreground GC 比例 < 10% 为健康

→ **理解 Background/Foreground，就理解了"GC 调度策略"**。

---

## 跨节引用

**本节被以下章节引用**：
- [7.8 GC 线程模型](./08-GC线程模型.md) —— 完整线程模型
- 09 篇诊断 —— GC 频率监控

**本节引用**：
- [7.1 9 种 GcCause](./01-9种GcCause.md) —— GC 触发原因
- [7.2 HeapTaskDaemon](./02-HeapTaskDaemon.md) —— HeapTaskDaemon 调度
- [7.3 ConcurrentGCTask](./03-ConcurrentGCTask.md) —— 后台 GC 任务
