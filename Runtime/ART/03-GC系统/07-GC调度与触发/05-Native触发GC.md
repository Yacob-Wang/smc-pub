# 7.5 Native 内存触发的 GC

> **本节回答一个根本问题**：Native 内存压力怎么触发 Java GC？"Native 内存高时 Java 堆 GC 也变多"的根因是什么？
>
> **答案**：**NativeAlloc 触发 Java GC**，释放 Java 堆空间，让出物理内存给 Native。

---

## 一、Native 内存与 Java GC 的关系

### 7.5.1 进程的内存结构

```
┌──────────────────────────────────────────────────────┐
│                  Linux Process                       │
│  ┌────────────────────────────────────────────────┐  │
│  │              Native Memory                      │  │
│  │  - libc malloc (Native Heap)                    │  │
│  │  - .so mmap                                    │  │
│  │  - DirectByteBuffer (native pixels)            │  │
│  │  - Bitmap native pixels                        │  │
│  │  - 其他 native 分配                              │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │              Java Memory (ART)                  │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │  Java Heap (ART GC 管理)                  │  │  │
│  │  │  - Image + Zygote + Allocation + LOS      │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │  JIT Code Cache                           │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │  Thread Stack                             │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  → Native 和 Java 都使用物理内存                     │
│  → 总内存超过 RSS 上限 → 系统 OOM killer              │
└──────────────────────────────────────────────────────┘
```

### 7.5.2 为什么 Native 内存压力要触发 Java GC

```
Native 内存高时触发 Java GC 的原因：

1. Java 堆也占用物理内存
   - Java 堆 256 MB + Native 100 MB = 356 MB
   - Native 增长到 200 MB → 总 456 MB
   - 接近 LMK 阈值

2. Java 堆可以"让出"内存
   - Java 堆有 SoftReference 可以回收
   - Java 堆也可以 trim 收缩
   - 释放后让给 Native

3. 协同优化
   - Native 和 Java 不能互相抢占
   - 主动 GC Java 堆，腾出物理内存
   - 让 Native 有更多空间
```

---

## 二、Native 内存压力检测

### 7.5.3 ART 的 Native 内存监控

```cpp
// art/runtime/gc/heap.cc
void Heap::CheckNativeMemoryPressure() {
    // 1. 获取 Native 内存使用量
    size_t native_used = GetNativeMemoryUsage();
    size_t native_limit = GetNativeMemoryLimit();
    
    // 2. 计算使用率
    double usage = (double)native_used / native_limit;
    
    // 3. 判断是否压力大
    if (usage > kNativePressureThreshold) {
        // 4. 触发 Java GC 释放 Java 堆
        OnNativeAllocationPressure();
    }
}
```

### 7.6.4 Android 系统级别的 Native 内存监控

```cpp
// system/core/libcutils/native_handle.cpp
// Android 14+ 的 Native 内存压力 API

void ReportNativePressure(size_t allocation_size) {
    // 1. 通知系统 native 内存压力大
    system_properties_->Set("dalvik.vm.native.pressure", "true");
    
    // 2. ART 收到通知
    // 3. ART 触发 Java GC（释放 Java 堆）
}
```

### 7.5.5 ART 14+ 的 NativeAlloc 监控 API

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public static void trackNativeAllocation(long size) {
    // 1. 累计 Native 分配
    native_allocated_bytes_.addAndGet(size);
    
    // 2. 检查是否触发 NativeAllocGCTask
    if (native_allocated_bytes_.get() > native_threshold_) {
        // 3. 触发 Java GC
        VMRuntime.getRuntime().concurrentGC();
    }
}
```

---

## 三、NativeAlloc 触发的 Java GC

### 7.5.6 NativeAllocGCTask

```cpp
// art/runtime/gc/heap_task.h
class NativeAllocGCTask : public HeapTask {
public:
    void Run(ThreadPool* thread_pool) override {
        // 1. 触发 ConcurrentGC（不阻塞业务线程）
        Heap* heap = Runtime::Current()->GetHeap();
        heap->ConcurrentGC(kGcCauseForNativeAlloc);
    }
};
```

### 7.5.7 Native 触发的 GC 流程

```
Native 内存压力检测：

1. Native 分配累计 > 阈值
   │
2. 创建 NativeAllocGCTask
   │
3. HeapTaskDaemon::AddTask(task)
   │
4. HeapTaskDaemon 线程执行
   │
5. NativeAllocGCTask::Run()
   │
6. Heap::ConcurrentGC(kGcCauseForNativeAlloc)
   │
7. 后台 GC（不阻塞业务线程）
   │
8. 释放 Java 堆空间（特别是 SoftReference）
   │
9. Java 堆让出物理内存
   │
10. Native 有更多空间可用
```

### 7.5.8 ConcurrentGC 的特殊处理

```cpp
// Heap::ConcurrentGC(kGcCauseForNativeAlloc)
void Heap::ConcurrentGC(GcCause cause) {
    if (cause == kGcCauseForNativeAlloc) {
        // 1. 强制处理 SoftReference
        //    释放尽可能多的 Java 堆
        //    让 Native 有更多空间
        ProcessReferences(true);  // clear_soft_references = true
    }
}
```

---

## 四、Native 内存触发的 GC 监控

### 7.6.9 监控 kGcCauseForNativeAlloc

```bash
# 1. 看 Native 触发的 GC 频率
adb logcat -s "art" | grep "kGcCauseForNativeAlloc" | wc -l
# 1 小时内的次数

# 2. 看每次 GC 释放的 Java 堆空间
adb logcat -s "art" | grep "Cause=kGcCauseForNativeAlloc" -A 5
# 输出示例：
# art : Cause=kGcCauseForNativeAlloc freed 52428800(50MB) AllocSpace objects
```

### 7.5.10 异常的诊断

| 频率 | 状态 | 根因 | 修复 |
|:---|:---|:---|:---|
| < 5/小时 | 正常 | — | — |
| 5-20/小时 | 警告 | Native 内存压力 | 优化 Native 内存 |
| > 20/小时 | 严重 | Native 内存泄漏 | 紧急修复 |

### 7.5.11 Native 内存优化的工程建议

```
Native 内存优化的工程建议：

1. DirectByteBuffer
   - 用对象池复用
   - 及时手动释放 native

2. Bitmap
   - 用 Glide / Fresco 自动管理
   - 及时 recycle() 释放 native 像素

3. 大 byte[]
   - 用文件 IO 替代内存
   - 分块处理

4. JNI 调用
   - 减少跨 JNI 调用
   - 缓存常用对象

5. 第三方 .so
   - 检查 native 内存泄漏
   - 使用最新版 .so
```

---

## 五、Native 触发的 GC 的局限

### 7.5.12 局限 1：Android 14+ 才完善

```
Native 触发的 GC 是 Android 14+ 的新特性：

1. Android 13 及之前
   - Native 内存压力 → 触发 GC 的机制不完善
   - 主要靠 Lowmemorykiller 杀进程

2. Android 14+
   - Native 内存监控 + 自动触发 GC
   - 更优雅的内存管理
```

### 7.5.13 局限 2：Java 堆释放有限

```
Java 堆可以释放的空间：

1. 死对象（GC 主要目标）
2. SoftReference 对象（内存压力时释放）
3. 可以 trim 的堆空间

但 Java 堆还有：
1. 长寿对象（不能释放）
2. 业务代码强引用的对象
3. 系统占用的对象

→ Native 触发的 GC 不能解决所有问题
```

### 7.5.14 局限 3：业务层 Native 内存不可控

```
业务层的 native 内存：

1. 第三方 .so 分配
   - 无法直接控制
   - 只能等 .so 自己释放

2. JNI 库分配
   - 需要手动释放
   - 容易泄漏

3. 第三方库的 native 内存
   - OkHttp / Retrofit / Glide 等
   - 大多数管理良好，但仍有泄漏风险
```

---

## 六、Native 触发的 GC 的源码索引

### 7.5.15 核心源码路径

```
art/runtime/gc/heap.h                  # Heap 类
art/runtime/gc/heap.cc                 # Heap::OnNativeAllocationPressure
art/runtime/gc/heap_task.h            # NativeAllocGCTask
art/runtime/gc/heap_task_daemon.cc    # HeapTaskDaemon
libcore/libart/src/main/java/java/lang/Daemons.java # trackNativeAllocation
system/core/libcutils/native_handle.cpp              # Native 内存监控
```

### 7.5.16 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Heap::CheckNativeMemoryPressure` | `heap.cc` | 检查 Native 内存压力 |
| `Heap::OnNativeAllocationPressure` | `heap.cc` | Native 压力回调 |
| `NativeAllocGCTask::Run` | `heap_task.h` | Native 触发的 GC 任务 |
| `Daemons.trackNativeAllocation` | `Daemons.java` | 跟踪 Native 分配 |

---

## 七、本节小结

1. **Native 内存压力大时触发 Java GC**：释放 Java 堆让出物理内存
2. **Android 14+ 完善 NativeAlloc 监控**：自动检测 + 自动触发
3. **触发的 GC 是后台的**：不阻塞业务线程
4. **强制处理 SoftReference**：释放尽可能多的 Java 堆
5. **优化方向**：优化 Native 内存（DirectByteBuffer / Bitmap 等）

→ **理解 Native 触发的 GC，就理解了"Native 与 Java 内存的协同管理"**。

---

## 跨节引用

**本节被以下章节引用**：
- [7.6 Trim Heap](./06-Trim-Heap.md) —— Trim Heap 配合 Native 压力
- 09 篇诊断 —— Native 内存诊断

**本节引用**：
- [7.1 9 种 GcCause](./01-9种GcCause.md) —— kGcCauseForNativeAlloc
- [7.3 ConcurrentGCTask](./03-ConcurrentGCTask.md) —— 后台 GC 任务
- 02 篇 2.2 5 Space 详解 —— LOS 占用 Native 内存
