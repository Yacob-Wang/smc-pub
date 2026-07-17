# 7.2 GC 调度：HeapTaskDaemon 线程

> **本节回答一个根本问题**：ART 怎么调度 GC？HeapTaskDaemon 是什么？怎么提交后台 GC 任务？
>
> **答案**：**HeapTaskDaemon 是单线程 daemon，从 task_queue 取出 GC 任务，按优先级执行**。

---

## 一、HeapTaskDaemon 的定义

### 7.2.1 HeapTaskDaemon 的作用

```
HeapTaskDaemon 的核心职责：

1. 异步执行 GC 任务
   - 不阻塞业务线程
   - 后台线程执行 GC

2. 处理 GC 任务队列
   - 接收 ConCurrentGCTask / TrimHeapTask 等
   - 按顺序执行

3. 触发后台 GC
   - 定时检查堆使用率
   - 满足条件时提交 GC 任务

4. 协调 Native 内存与 Java GC
   - Native 内存压力时触发 Java GC
```

### 7.2.2 HeapTaskDaemon 的源码

```cpp
// art/runtime/gc/heap.h
class Heap {
    // HeapTaskDaemon：单线程 daemon
    std::unique_ptr<HeapTaskDaemon> task_daemon_;
    
    // GC 任务队列
    std::deque<std::unique_ptr<HeapTask>> task_queue_;
    
public:
    void AddTask(std::unique_ptr<HeapTask> task);
    void RunHeapTask(HeapTask* task);
};

class HeapTaskDaemon : public Thread {
    void Run() override;
    
    std::deque<std::unique_ptr<HeapTask>> tasks_;
    std::condition_variable task_queue_condition_;
    std::mutex task_queue_mutex_;
};
```

### 7.2.3 HeapTaskDaemon 的启动

```cpp
// art/runtime/gc/heap.cc
void Heap::CreateHeapTaskDaemon() {
    // 创建 HeapTaskDaemon 线程
    task_daemon_ = std::make_unique<HeapTaskDaemon>(this);
    
    // 启动线程
    task_daemon_->Start();
}
```

---

## 二、HeapTaskDaemon 的工作循环

### 7.2.4 HeapTaskDaemon::Run 的实现

```cpp
// art/runtime/gc/heap_task_daemon.cc
void HeapTaskDaemon::Run() {
    while (true) {
        std::unique_ptr<HeapTask> task;
        
        // 1. 等待任务（阻塞）
        {
            std::lock_guard<std::mutex> lock(task_queue_mutex_);
            while (tasks_.empty() && !shutting_down_) {
                task_queue_condition_.wait(lock);
            }
            if (shutting_down_) return;
            task = std::move(tasks_.front());
            tasks_.pop_front();
        }
        
        // 2. 执行任务
        if (task != nullptr) {
            task->Run(this);
        }
    }
}
```

### 7.2.5 任务的提交

```cpp
// art/runtime/gc/heap.cc
void Heap::AddTask(std::unique_ptr<HeapTask> task) {
    // 1. 加入任务队列
    std::lock_guard<std::mutex> lock(task_daemon_->task_queue_mutex_);
    task_daemon_->tasks_.push_back(std::move(task));
    
    // 2. 唤醒 HeapTaskDaemon
    task_daemon_->task_queue_condition_.notify_one();
}
```

### 7.2.6 HeapTask 抽象类

```cpp
// art/runtime/gc/heap_task.h
class HeapTask {
public:
    // 抽象方法：执行任务
    virtual void Run(ThreadPool* thread_pool) = 0;
};

// 具体任务子类
class ConcurrentGCTask : public HeapTask {
    void Run(ThreadPool* thread_pool) override {
        // 执行后台 GC
    }
};

class TrimHeapTask : public HeapTask {
    void Run(ThreadPool* thread_pool) override {
        // 执行 Trim Heap
    }
};
```

---

## 三、HeapTaskDaemon 的工作流

### 7.2.7 HeapTaskDaemon 的时序图

```
┌────────────────────────────────────────────────────┐
│                  HeapTaskDaemon                    │
├────────────────────────────────────────────────────┤
│                                                    │
│  启动时：                                          │
│    Heap::CreateHeapTaskDaemon()                    │
│    ↓                                               │
│    task_daemon_->Start()                           │
│    ↓                                               │
│    HeapTaskDaemon::Run()                           │
│    ↓                                               │
│    等待 task_queue_condition_.wait()                │
│                                                    │
│  业务触发 GC：                                      │
│    Heap::CollectGarbage()                          │
│    ↓                                               │
│    Heap::AddTask(task)                             │
│    ↓                                               │
│    task_queue_condition_.notify_one()              │
│    ↓                                               │
│  HeapTaskDaemon 线程被唤醒                          │
│    ↓                                               │
│    取出 task                                       │
│    ↓                                               │
│    task->Run(thread_pool)                          │
│    ↓                                               │
│    GC 执行完毕                                      │
│    ↓                                               │
│    继续等待下一个任务                                │
│                                                    │
└────────────────────────────────────────────────────────────┘
```

### 7.2.8 HeapTaskDaemon 的线程模型

```
HeapTaskDaemon 线程：
- 单线程 daemon
- 由 ART 创建并启动
- 与业务线程隔离
- 优先级：后台

业务线程：
- 用户 UI 线程 + 子线程
- 触发 GC 时提交 task
- 不直接执行 GC

HeapTaskDaemon + 业务线程：
- 通过 task_queue 通信
- 业务线程 → task_queue → HeapTaskDaemon
```

---

## 四、HeapTask 的分类

### 7.2.9 主要 HeapTask 类型

```cpp
// art/runtime/gc/heap_task.h

// 1. 后台 GC 任务
class ConcurrentGCTask : public HeapTask {
    GcCause cause_;
    uint64_t target_byte_count_;
    
    void Run(ThreadPool* thread_pool) override {
        // 触发后台 GC
        heap_->ConcurrentGC(cause_);
    }
};

// 2. Trim Heap 任务
class TrimHeapTask : public HeapTask {
    void Run(ThreadPool* thread_pool) override {
        // 收缩堆
        heap_->Trim();
    }
};

// 3. 触发 NativeAlloc 触发的 GC
class NativeAllocGCTask : public HeapTask {
    void Run(ThreadPool* thread_pool) override {
        // 触发 GC 释放 Java 堆
        heap_->CollectGarbage(kGcCauseForNativeAlloc, false);
    }
};
```

### 7.2.10 任务的优先级

```
HeapTask 的执行顺序：

1. NativeAllocGCTask（最高优先级）：native 内存压力大
2. ConcurrentGCTask（普通优先级）：定时后台 GC
3. TrimHeapTask（低优先级）：系统低内存

→ HeapTaskDaemon 按 FIFO 顺序执行
→ 但 ART 可以根据 GcCause 决定 GC 类型
```

---

## 五、HeapTaskDaemon 的工程监控

### 7.2.11 HeapTaskDaemon 监控

```bash
# 1. 看 HeapTaskDaemon 线程状态
adb shell ps -T -p <pid> | grep "HeapTaskDaemon"
# 输出示例：
# 12345 12346 12345 1 -19 0 0 0 HeapTaskDaemon

# 2. 看 task queue 长度（debug 模式）
adb shell dumpsys meminfo <package> | grep -i "heap task"

# 3. 看 HeapTaskDaemon 执行任务历史
adb logcat -s "art" | grep "HeapTaskDaemon"
```

### 7.2.12 HeapTaskDaemon 的性能影响

```
HeapTaskDaemon 的性能特征：

优点：
  - 异步执行，不阻塞业务
  - 单线程简单实现
  - 与业务线程隔离

缺点：
  - 单线程 → GC 任务串行执行
  - 不能并行多个 GC 任务
  - 大量任务堆积 → 内存占用
```

### 7.2.13 HeapTaskDaemon 的调优

```cpp
// 调整 HeapTaskDaemon 的优先级
// 默认是后台优先级
// ART 14+ 可调高（但可能影响业务线程）

// 调整任务提交策略
// 频繁 GC 任务 → 合并执行
// 一次性 GC 大对象 → 拆成多次
```

---

## 六、HeapTaskDaemon 的源码索引

### 7.2.14 核心源码路径

```
art/runtime/gc/heap.h                         # Heap 类（含 task_daemon_）
art/runtime/gc/heap.cc                        # Heap 实现
art/runtime/gc/heap_task.h                    # HeapTask 抽象类
art/runtime/gc/heap_task_daemon.h            # HeapTaskDaemon 类
art/runtime/gc/heap_task_daemon.cc           # HeapTaskDaemon 实现
art/runtime/gc/task_processor.h              # TaskProcessor（多任务处理）
```

### 7.2.15 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Heap::CreateHeapTaskDaemon` | `heap.cc` | 创建 HeapTaskDaemon |
| `Heap::AddTask` | `heap.cc` | 提交 GC 任务 |
| `HeapTaskDaemon::Run` | `heap_task_daemon.cc` | HeapTaskDaemon 主循环 |
| `HeapTaskDaemon::Stop` | `heap_task_daemon.cc` | 停止 HeapTaskDaemon |
| `ConcurrentGCTask::Run` | `heap_task.h` | 后台 GC 任务 |

---

## 七、本节小结

1. **HeapTaskDaemon 是单线程 daemon**：异步执行 GC 任务
2. **任务队列**：通过 task_queue 与业务线程通信
3. **3 种主要任务**：ConcurrentGCTask / TrimHeapTask / NativeAllocGCTask
4. **优先级**：NativeAllocGCTask > ConcurrentGCTask > TrimHeapTask
5. **工程监控**：HeapTaskDaemon 线程状态 + task queue 长度

→ **理解 HeapTaskDaemon，就理解了"GC 怎么异步执行"**。

---

## 跨节引用

**本节被以下章节引用**：
- [7.3 ConcurrentGCTask](./03-ConcurrentGCTask.md) —— 后台 GC 任务详解
- [7.7 Background vs Foreground](./07-Background-Foreground.md) —— 调度优先级
- [7.8 GC 线程模型](./08-GC线程模型.md) —— 完整线程模型

**本节引用**：
- [7.1 9 种 GcCause](./01-9种GcCause.md) —— GC 触发原因
- 02 篇 2.1 Heap 总览 —— Heap 类
