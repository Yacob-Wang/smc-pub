# 7.6 Trim Heap：系统低内存时的主动缩容

> **本节回答一个根本问题**：系统低内存时，ART 怎么主动收缩 Java 堆？Trim Heap 的工作原理是什么？
>
> **答案**：**Heap::Trim() 主动收缩堆**，释放内存给系统，调整 SoftReference 阈值。

---

## 一、Trim Heap 的定义

### 7.6.1 Trim Heap 的作用

```
Trim Heap 的核心职责：

1. 主动收缩 Java 堆
   - 释放未使用的堆空间
   - 把内存归还给系统

2. 调整 SoftReference 阈值
   - 在低内存时，让更多 SoftReference 被回收
   - 释放更多 Java 堆空间

3. 配合系统低内存管理
   - 监听系统 onLowMemory / onTrimMemory
   - 系统内存压力时主动收缩
```

### 7.6.2 Trim Heap 的触发场景

```
Trim Heap 的触发场景：

1. 系统内存压力
   - onTrimMemory(TRIM_MEMORY_RUNNING_LOW)
   - onTrimMemory(TRIM_MEMORY_RUNNING_CRITICAL)
   - onLowMemory()

2. 后台进入空闲状态
   - 应用进入后台
   - ART 主动 Trim Heap

3. Native 内存压力
   - kGcCauseForNativeAlloc 触发后
   - ART 主动 Trim Heap

4. 定时 Trim
   - ART 14+ 可定时 Trim
   - 保持堆大小合理
```

---

## 二、Heap::Trim 的实现

### 7.6.3 Trim 的完整流程

```cpp
// art/runtime/gc/heap.cc 的 Heap::Trim（简化版）
void Heap::Trim() {
    // 1. 计算当前堆使用量
    size_t current_footprint = GetCurrentFootprint();
    
    // 2. 计算目标堆大小
    size_t target = current_footprint * target_utilization_;
    
    // 3. 收缩堆（调整 SoftReference 阈值）
    if (ChangeSoftReferenceLimit(target)) {
        // 4. 触发 GC 释放内存
        CollectGarbage(kGcCauseForTrim, true);  // clear_soft_references = true
        
        // 5. 归还未使用的堆空间给系统
        if (allocation_space_ != nullptr) {
            allocation_space_->Trim();  // 释放 Region Pool 中的空闲 Region
        }
        
        if (zygote_space_ != nullptr) {
            zygote_space_->Trim();
        }
    }
}
```

### 7.6.4 ChangeSoftReferenceLimit 的实现

```cpp
// art/runtime/gc/heap.cc 的 ChangeSoftReferenceLimit
bool ChangeSoftReferenceLimit(size_t new_footprint) {
    // 1. 检查是否需要收缩
    if (new_footprint >= growth_limit_) {
        return false;  // 已经够小
    }
    
    // 2. 计算新的 SoftReference 阈值
    //    SoftReference 的保留率：
    //    retain_ratio = (heap_used / heap_max - threshold) / (1 - threshold)
    //    调低 threshold → 保留率降低 → 更多 SoftReference 被回收
    
    // 3. 调整 SoftReference 阈值
    soft_ref_threshold_ = std::min(soft_ref_threshold_, new_threshold);
    
    // 4. 调整 growth_limit
    growth_limit_ = new_footprint;
    
    return true;
}
```

### 7.6.5 AllocationSpace::Trim

```cpp
// art/runtime/gc/space/region_space.cc 的 RegionSpace::Trim
void RegionSpace::Trim() {
    // 1. 找出空闲的 Region
    std::vector<Region*> free_regions;
    for (Region& region : regions_) {
        if (region.IsFree() && region.live_bytes_ == 0) {
            free_regions.push_back(&region);
        }
    }
    
    // 2. 释放 Region 的物理内存（madvise + madvise）
    for (Region* region : free_regions) {
        region->MadiseFree();  // 告诉内核可以回收这些页
    }
    
    // 3. 调整 Region Pool
    //    释放多余的 Region（如果有大量空闲）
    while (free_regions_.size() > kMinFreeRegions) {
        Region* region = free_regions_.back();
        free_regions_.pop_back();
        region->ReleaseMemory();  // 归还内存给系统
    }
}
```

---

## 三、Trim Heap 的触发方式

### 7.6.6 系统 onTrimMemory 回调

```java
// 业务代码
public class MyApplication extends Application {
    @Override
    public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        
        switch (level) {
            case TRIM_MEMORY_RUNNING_MODERATE:
                // 系统内存压力中
                System.gc();
                break;
            case TRIM_MEMORY_RUNNING_LOW:
                // 系统内存压力低
                System.gc();
                break;
            case TRIM_MEMORY_RUNNING_CRITICAL:
                // 系统内存压力危急
                System.gc();
                // 主动清理缓存
                clearCaches();
                break;
            case TRIM_MEMORY_UI_HIDDEN:
                // UI 隐藏（应用进入后台）
                System.gc();
                break;
            case TRIM_MEMORY_BACKGROUND:
                // 进入后台
                System.gc();
                break;
            case TRIM_MEMORY_MODERATE:
                // 中等压力
                System.gc();
                break;
            case TRIM_MEMORY_COMPLETE:
                // 即将被杀死
                System.gc();
                // 紧急清理
                emergencyCleanup();
                break;
        }
    }
}
```

### 7.6.7 ART 主动 Trim

```cpp
// art/runtime/gc/heap.cc
void Heap::OnTrimMemory(int level) {
    // 系统 onTrimMemory 触发
    // 1. 主动 Trim Heap
    Trim();
    
    // 2. 触发 GC_FOR_ALLOC（如果需要）
    if (need_more_memory_) {
        CollectGarbage(kGcCauseForTrim, true);
    }
}
```

### 7.6.8 定时 Trim

```cpp
// ART 14+ 引入定时 Trim
void Heap::CheckPeriodicTrim() {
    // 1. 计算上次 Trim 到现在的间隔
    auto duration = std::chrono::system_clock::now() - last_trim_time_;
    
    // 2. 如果超过 30 分钟
    if (duration > std::chrono::minutes(30)) {
        // 3. 主动 Trim
        Trim();
        last_trim_time_ = std::chrono::system_clock::now();
    }
}
```

---

## 四、Trim Heap 的工程影响

### 7.6.9 Trim Heap 的性能影响

```
Trim Heap 的影响：

1. 主动收缩堆
   - 释放未使用的堆空间
   - 归还内存给系统
   - 系统有更多内存可用

2. SoftReference 调整
   - 低内存时更多 SoftReference 被回收
   - Glide Bitmap 缓存等内存敏感缓存被清理
   - 业务代码可能需要重新加载

3. GC 频率影响
   - Trim 后堆变小
   - 更容易触发 GC
   - 但释放了物理内存
```

### 7.6.10 Trim Heap 的局限性

```
Trim Heap 的局限：

1. 只能收缩到一定大小
   - 不能小于 min_heap_size
   - 不能回收 Long-lived 对象

2. 收缩后可能需要扩展
   - 业务代码继续分配
   - 触发堆扩展
   - 再次 GC

3. SoftReference 调整是全局的
   - 不区分不同的 SoftReference
   - Glide 缓存和其他 SoftReference 一视同仁
```

### 7.6.11 Trim Heap 的工程建议

```java
// ✅ 业务代码配合 Trim Heap
public class MyApplication extends Application {
    @Override
    public void onTrimMemory(int level) {
        super.onTrimMemory(level);
        
        if (level >= TRIM_MEMORY_RUNNING_LOW) {
            // 主动清理非必要缓存
            clearNonEssentialCaches();
        }
        
        if (level >= TRIM_MEMORY_COMPLETE) {
            // 紧急清理所有缓存
            clearAllCaches();
        }
    }
}
```

---

## 五、Trim Heap 的监控

### 7.6.12 监控 Trim Heap 频率

```bash
# 1. 看 Trim Heap 频率
adb logcat -s "art" | grep "kGcCauseForTrim" | wc -l
# 1 小时内的次数

# 2. 看 Trim 释放的内存
adb logcat -s "art" | grep "Cause=kGcCauseForTrim" -A 5
# 输出示例：
# art : Cause=kGcCauseForTrim freed 52428800(50MB) AllocSpace objects
```

### 7.6.13 监控 onTrimMemory 回调

```java
public class TrimMemoryMonitor {
    @Override
    public void onTrimMemory(int level) {
        apmClient.report("trim.memory.level", level);
        
        if (level >= TRIM_MEMORY_RUNNING_LOW) {
            apmClient.report("trim.memory.low", 1);
        }
    }
}
```

### 7.6.14 异常诊断

| 频率 | 状态 | 根因 | 修复 |
|:---|:---|:---|:---|
| < 5/小时 | 正常 | — | — |
| 5-20/小时 | 警告 | 系统内存压力 | 优化内存 |
| > 20/小时 | 严重 | 内存泄漏 | 紧急修复 |

---

## 六、Trim Heap 的源码索引

### 7.6.15 核心源码路径

```
art/runtime/gc/heap.h                  # Heap 类
art/runtime/gc/heap.cc                 # Heap::Trim
art/runtime/gc/heap.cc                 # Heap::ChangeSoftReferenceLimit
art/runtime/gc/space/region_space.cc  # RegionSpace::Trim
art/runtime/gc/space/space.cc         # Space::Trim
art/runtime/gc/heap_task.h            # TrimHeapTask
frameworks/base/core/java/android/app/Application.java # onTrimMemory
```

### 7.6.16 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Heap::Trim` | `heap.cc` | Trim 堆 |
| `Heap::ChangeSoftReferenceLimit` | `heap.cc` | 调整 SoftReference 阈值 |
| `RegionSpace::Trim` | `region_space.cc` | Region Space Trim |
| `Application.onTrimMemory` | `Application.java` | 系统回调 |
| `TrimHeapTask::Run` | `heap_task.h` | Trim Heap 任务 |

---

## 七、本节小结

1. **Trim Heap 主动收缩堆**：释放内存给系统
2. **触发场景**：onTrimMemory / Native 压力 / 定时
3. **调整 SoftReference**：低内存时更多回收
4. **业务层配合**：onTrimMemory 主动清理缓存
5. **监控**：Trim 频率 + 释放内存

→ **理解 Trim Heap，就理解了"系统低内存时 ART 怎么应对"**。

---

## 跨节引用

**本节被以下章节引用**：
- 09 篇诊断 —— 内存治理

**本节引用**：
- [7.1 9 种 GcCause](./01-9种GcCause.md) —— kGcCauseForTrim
- [7.5 Native 触发 GC](./05-Native触发GC.md) —— Native 压力后的 Trim
- 02 篇 2.3 内存配额 —— growth_limit 与 heaptargetutilization
