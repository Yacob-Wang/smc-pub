# 2.1 Heap 总览：为什么 ART 不用一整块内存

> **本节回答一个根本问题**：ART 的 Java 堆为什么不是一整块内存，而是分成多个 Space？
>
> **答案**：基于 **生命周期差异 + GC 效率 + 移动需求** 的工程权衡。
>
> **理解本节，就理解了 ART 堆的"地图"** —— OOM 排查、碎片化分析、GC 调优的全局视角。

---

## 一、为什么不用一整块内存

### 2.1.1 一整块内存的三大问题

如果 ART 把所有 Java 对象都放在一整块连续内存里，会遇到三个根本问题：

#### 问题 1：GC 效率低

```cpp
// 假设一整块内存 256 MB，所有对象混在一起
// CMS 标记：需要遍历 256 MB 的所有对象 → STW 时间极长
// CC GC 复制：需要把活对象复制到 to-space → 256 MB 全部重定位
// GenCC Minor GC：无法只扫描 Young Gen，因为分不清 Young/Old
```

#### 问题 2：移动需求冲突

```cpp
// 不同对象有不同的"是否可移动"需求
// 1. 只读的 OAT 镜像（Image Space）→ 永不移动
// 2. Zygote 预加载的类（Zygote Space）→ 不能移动（其他进程依赖）
// 3. 常规对象（Allocation Space）→ 可移动（GC 复制）
// 4. 大对象（LOS）→ 一般不移动（复制成本高）
// 5. 永久不移动对象（Non-Moving）→ 永不移动（性能考虑）
```

**冲突**：如果所有对象都在一起，CC GC 移动一个对象时要重定位所有引用 → 性能差。

#### 问题 3：生命周期差异

```cpp
// 不同对象的生命周期天差地别
// 1. 镜像类：进程生命周期内永久存在
// 2. Zygote 类：进程 fork 后永久存在
// 3. 常规对象：平均存活时间 ~50ms（Young Gen）
// 4. 大对象：可能存活很久（Bitmap 缓存）
// 5. 系统对象：长期存活（Application、Service）
```

**冲突**：如果所有对象混在一起，GC 无法针对性优化。

### 2.1.2 ART 的解决方案：5 Space 划分

ART 把 Java 堆分成 **5 个 Space**，每个 Space 解决一类问题：

| Space | 生命周期 | 是否可移动 | 分配器 | GC 策略 |
|:---|:---|:---|:---|:---|
| **Image Space** | 永久（只读） | 不可移动 | mmap | 不参与 GC |
| **Zygote Space** | 永久（共享） | 不可移动 | mmap | 不参与 GC |
| **Allocation Space** | Young Gen | 可移动 | RosAlloc / Region | Minor GC + Major GC |
| **Large Object Space** | 长寿 | 不可移动 | LOS Allocator | Major GC 标记清除 |
| **Non-Moving Space** | 永久 | 不可移动 | bump pointer | 不参与 GC |

### 2.1.3 5 Space 的内存布局图

```
┌─────────────────────────────────────────────────────────────┐
│                     Java Heap (256MB / 512MB)                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐  │
│  │ Image Space  │ │Zygote Space  │ │  Allocation Space    │  │
│  │  (~50 MB)    │ │  (~30 MB)    │ │  (default 256 MB)    │  │
│  │  只读 mmap   │ │  fork 时共享 │ │  RosAlloc / Region   │  │
│  │  类镜像      │ │  预加载类    │ │  Young Gen           │  │
│  └──────────────┘ └──────────────┘ └─────────────────────┘  │
│                                                              │
│  ┌──────────────────────────┐ ┌──────────────────────────┐ │
│  │ Large Object Space (LOS) │ │  Non-Moving Space         │ │
│  │  (dynamic)               │ │  (CC GC 早期版本)          │ │
│  │  大对象 (≥ 12KB)         │ │  永不移动的对象            │ │
│  │  bitmap、byte[]          │ │  String.intern 等          │ │
│  └──────────────────────────┘ └──────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、Heap 类的整体架构

### 2.1.4 Heap 类的源码入口

```cpp
// art/runtime/gc/heap.h（精简版）
class Heap {
 public:
  // 5 个 Space 的指针
  std::unique_ptr<space::ImageSpace> image_space_;
  std::unique_ptr<space::ZygoteSpace> zygote_space_;
  std::unique_ptr<space::MallocSpace> non_moving_space_;
  std::unique_ptr<space::MallocSpace> allocation_space_;
  std::unique_ptr<space::LargeObjectSpace> large_object_space_;
  
  // 堆大小
  size_t max_allowed_footprint_;  // Java 堆最大内存
  size_t growth_limit_;          // 增长上限
  size_t target_utilization_;    // 目标使用率
  
  // GC 调度
  collector::ConcurrentCopying* concurrent_copying_;
  collector::MarkSweep* mark_sweep_;
  std::unique_ptr<ReferenceProcessor> reference_processor_;
  
  // 核心方法
  mirror::Object* AllocObject(Thread* self, ...) {
    // 分配对象的入口（详见 2.4-2.6 节）
  }
  
  void CollectGarbage(GcCause cause, ...) {
    // GC 触发入口（详见 07 篇）
  }
};
```

### 2.1.5 Heap 的初始化流程

```cpp
// art/runtime/gc/heap.cc 的 Heap::Heap 构造函数（精简版）
Heap::Heap(...) {
  // 1. 读取配置参数
  //    dalvik.vm.heapgrowthlimit
  //    dalvik.vm.heapsize
  //    dalvik.vm.heaptargetutilization
  growth_limit_ = ...;
  max_allowed_footprint_ = ...;
  
  // 2. 创建 5 个 Space
  image_space_ = space::ImageSpace::Create("boot.art", ...);
  zygote_space_ = space::ZygoteSpace::Create("boot.art", ...);
  non_moving_space_ = space::MallocSpace::CreateNonMovingSpace(...);
  allocation_space_ = space::MallocSpace::CreateAllocSpace(...);
  large_object_space_ = space::LargeObjectSpace::Create(...);
  
  // 3. 初始化 GC
  if (kUseCCGC) {
    concurrent_copying_ = new collector::ConcurrentCopying(this);
  } else {
    mark_sweep_ = new collector::MarkSweep(this);
  }
  
  // 4. 初始化 ReferenceProcessor
  reference_processor_ = new ReferenceProcessor(this);
}
```

### 2.1.6 Heap 与 GC 的协作

```
┌────────────────────────────────────────────────────────────┐
│                        Heap                                │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐ │
│  │ Image Space  │ │Zygote Space  │ │ Allocation Space    │ │
│  └──────────────┘ └──────────────┘ └────────────────────┘ │
│  ┌──────────────────────────┐ ┌────────────────────────┐ │
│  │ Large Object Space       │ │  Non-Moving Space       │ │
│  └──────────────────────────┘ └────────────────────────┘ │
│                            │                               │
│                            ▼                               │
│               ┌──────────────────────┐                     │
│               │ GarbageCollector     │                     │
│               │  - MarkSweep (CMS)   │                     │
│               │  - ConcurrentCopying │                     │
│               └──────────────────────┘                     │
│                            │                               │
│                            ▼                               │
│               ┌──────────────────────┐                     │
│               │ ReferenceProcessor   │                     │
│               └──────────────────────┘                     │
└────────────────────────────────────────────────────────────┘
```

---

## 三、Heap 的内存管理

### 2.1.7 Heap 内存的分配流程

业务代码调用 `new Object()` 时，ART 的完整分配路径：

```
业务代码：Object obj = new Object();
    │
    ▼
1. JIT/AOT 编译码调用 artAllocObject
    │
    ▼
2. Heap::AllocObject
    │
    ├─── 大对象 (≥ Region Size / 12 KB)
    │    │
    │    └─── LargeObjectSpace::Alloc
    │
    └─── 普通对象
         │
         ├─── 走 TLAB 快速路径
         │    │
         │    ├─── TLAB 有空间 → bump pointer
         │    │
         │    └─── TLAB 用完 → 慢速路径
         │
         └─── 慢速路径
              │
              ├─── 1. 尝试 AllocationSpace->Alloc
              ├─── 2. 失败 → 触发 GC_FOR_ALLOC
              ├─── 3. GC 后重试
              ├─── 4. 仍失败 → 扩展堆
              └─── 5. 仍失败 → OOM
```

### 2.1.8 Heap 内存的回收流程

业务代码释放对象引用后，ART 的完整回收路径：

```
业务代码：obj = null;  // 释放引用
    │
    ▼
1. 对象变成"不可达"（详见 01 篇 1.1 可达性分析）
    │
    ▼
2. GC 触发（详见 07 篇调度）
    │
    ├─── CMS (Android 5.0-7.0)
    │    │
    │    └─── MarkSweep：
    │         1. Initial Mark (STW) → 标记 GC Root
    │         2. Concurrent Mark → 并发标记
    │         3. Remark (STW) → 重新扫描
    │         4. Concurrent Sweep → 清除死对象
    │
    ├─── CC GC (Android 8.0-9.0)
    │    │
    │    └─── ConcurrentCopying：
    │         1. Initialize (STW) → 栈扫描
    │         2. Concurrent Copying → 复制活对象到 to-space
    │         3. Reclaim (STW) → 清理 from-space
    │
    └─── GenCC (Android 10.0+)
         │
         └─── ConcurrentCopying + 分代：
              1. Minor GC → 只扫描 Young Gen（< 0.5ms）
              2. Major GC → 全堆扫描
```

---

## 四、ART 堆的演进历史

### 2.1.9 Android 版本对应的 Heap 实现

| Android 版本 | Heap 实现 | 关键变化 |
|:---|:---|:---|
| Android 5.0 | CMS + RosAlloc | 默认引入 ART |
| Android 6.0 | CMS + RosAlloc | 同上 |
| Android 7.0 | CMS + RosAlloc | 同上 |
| Android 8.0 | CC GC + Region-based | STW < 1ms |
| Android 9.0 | CC GC + Region-based | 同上 |
| Android 10.0 | GenCC + Region-based | Minor GC 引入 |
| Android 11.0 | GenCC + Region-based | Card Table 优化 |
| Android 12.0 | GenCC + rbcc | 读屏障优化 |
| Android 13.0 | GenCC + rbcc | JIT 校验 |
| Android 14.0 | GenCC + 细粒度卡表 | 进一步优化 |

### 2.1.10 关键演进驱动力

**驱动力 1：减少 STW 时间**
- CMS 的 50ms STW → CC 的 < 1ms STW
- 通过 Region-based + 读屏障实现

**驱动力 2：减少 GC 频率**
- 全堆 GC → Minor GC（只扫描 Young Gen）
- 通过 Card Table + 分代假说实现

**驱动力 3：减少运行时开销**
- 朴素读屏障 1.5-3x 开销 → rbcc 优化 1.1-1.6x 开销
- 通过对象头状态机 + 自愈指针实现

---

## 五、Heap 的内存回收策略

### 2.1.11 堆扩展（Grow Heap）

当分配失败时，ART 会尝试扩展堆：

```cpp
// art/runtime/gc/heap.cc 的 Heap::TryToAllocate 精简版
mirror::Object* Heap::TryToAllocate(...) {
    // 1. 尝试在当前堆上分配
    mirror::Object* obj = allocation_space_->Alloc(...);
    if (obj != nullptr) return obj;
    
    // 2. 尝试扩展堆
    if (growth_limit_ < max_allowed_footprint_) {
        size_t new_footprint = ...;  // 按 utilization 计算
        if (ChangeSoftReferenceLimit(new_footprint)) {
            // 3. 扩展后重试
            obj = allocation_space_->Alloc(...);
            if (obj != nullptr) return obj;
        }
    }
    
    // 4. 已达上限 → 触发 GC
    CollectGarbage(kGcCauseForAlloc, ...);
    
    // 5. GC 后重试
    obj = allocation_space_->Alloc(...);
    if (obj != nullptr) return obj;
    
    // 6. 仍失败 → OOM
    return nullptr;
}
```

### 2.1.12 堆收缩（Trim Heap）

当系统内存压力高时，ART 会主动收缩堆：

```cpp
// art/runtime/gc/heap.cc 的 Heap::Trim 精简版
void Heap::Trim() {
    // 1. 计算目标堆大小
    size_t target = ...;
    
    // 2. 收缩堆
    if (current_footprint_ > target) {
        // 3. 调整 SoftReference 阈值
        ChangeSoftReferenceLimit(target);
        
        // 4. 触发 GC 释放内存
        CollectGarbage(kGcCauseTrim, ...);
        
        // 5. 归还内存给系统
        allocation_space_->Trim();
    }
}
```

### 2.1.13 堆大小对调

```bash
# 系统属性配置
adb shell setprop dalvik.vm.heapgrowthlimit 256m
adb shell setprop dalvik.vm.heapsize 512m
adb shell setprop dalvik.vm.heaptargetutilization 0.75
```

| 参数 | 含义 | 默认值 |
|:---|:---|:---|
| `dalvik.vm.heapgrowthlimit` | 普通堆大小 | 256MB |
| `dalvik.vm.heapsize` | `largeHeap` 时的堆大小 | 512MB |
| `dalvik.vm.heaptargetutilization` | 目标使用率 | 0.75 |
| `dalvik.vm.heapminfree` | 最小空闲 | 2MB |
| `dalvik.vm.heapmaxfree` | 最大空闲 | 8MB |

---

## 六、稳定性关联

### 2.1.14 OOM 的 5 种类型

ART 的 OOM 实际上是 **5 种不同的 OOM**，每种对应不同的 Space：

| OOM 类型 | 触发条件 | 排查方向 |
|:---|:---|:---|
| **Allocation Space OOM** | 常规分配失败 | 检查 Java 堆泄漏、大对象占用 |
| **Large Object Space OOM** | 大对象分配失败 | 检查 Bitmap、byte[]、Native 内存 |
| **Image Space OOM** | 镜像加载失败 | 检查 boot.art / boot.oat 损坏 |
| **Zygote Space OOM** | Zygote fork 失败 | 检查 preloaded-classes |
| **Non-Moving Space OOM** | 永久对象分配失败 | 检查 String.intern、Class 对象 |

### 2.1.15 OOM 的排查路径

```
Java heap OOM
    │
    ▼
1. dumpsys meminfo 看 Dalvik Heap Size
    │
    ▼
2. 是哪个 Space 满了？
    │
    ├─── Allocation Space
    │    │
    │    ▼
    │   2.1 检查泄漏（LeakCanary / heap dump）
    │   2.2 检查分配器碎片化（详见 2.7）
    │   2.3 检查大对象占用（详见 2.2 LOS）
    │
    ├─── Large Object Space
    │    │
    │    ▼
    │   3.1 检查 Bitmap 缓存（Glide / Fresco）
    │   3.2 检查大 byte[] 数组
    │   3.3 检查 Native 内存映射
    │
    └─── Image Space / Zygote Space
         │
         ▼
        4.1 检查 boot.art / boot.oat
        4.2 检查 preloaded-classes
```

---

## 七、Heap 在系统中的位置

### 2.1.16 Heap 在 Android 内存体系中的位置

```
┌────────────────────────────────────────────────────────────┐
│                    Linux Process                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  Native Memory                        │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐     │  │
│  │  │ libc malloc │  │  .so mmap  │  │ DirectBuf  │     │  │
│  │  └────────────┘  └────────────┘  └────────────┘     │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  Java Memory (ART)                    │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │              Java Heap (5 Space)                │  │  │
│  │  │  Image + Zygote + Allocation + LOS + NonMoving │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │           JIT Code Cache                         │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │           Thread Stack                           │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### 2.1.17 Heap 与 Native 内存的互动

ART 的 Java 堆是 **Native 内存** 的子集（ART 用 mmap 分配堆内存）：

```cpp
// art/runtime/gc/space/space.cc 的 Space::Init 简化版
void Space::Init(size_t size, ...) {
    // 1. mmap 一段连续内存
    mem_map_ = MemMap::MapAnonymous("dalvik-alloc space", nullptr, size, ...);
    
    // 2. 记录基址
    Begin_ = mem_map_->Begin();
    End_ = mem_map_->End();
    
    // 3. 初始化分配器
    allocator_ = RosAlloc::Create(this, ...);  // 或 RegionAllocator
}
```

→ **Java 堆用得越多，Native 内存也用得越多**，最终都会被 LMK 看到。

---

## 八、ART Heap 关键源码

### 2.1.18 核心源码路径

```
art/runtime/gc/heap.h                # Heap 类定义
art/runtime/gc/heap.cc               # Heap 类实现
art/runtime/gc/space/space.h         # Space 基类
art/runtime/gc/space/space.cc        # Space 基类实现
art/runtime/gc/space/image_space.h   # Image Space
art/runtime/gc/space/zygote_space.h  # Zygote Space
art/runtime/gc/space/malloc_space.h  # Allocation + Non-Moving Space
art/runtime/gc/space/large_object_space.h  # LOS
art/runtime/gc/allocator/rosalloc.h  # RosAlloc 分配器
art/runtime/gc/allocator/region_allocator.h  # Region 分配器
```

---

## 九、本节小结

1. **ART Java 堆分成 5 个 Space**：Image / Zygote / Allocation / LOS / Non-Moving
2. **每个 Space 有独立的生命周期、可移动性、分配器、GC 策略**
3. **Heap 是 ART GC 的核心数据枢纽**：所有分配 / 回收 / 调度都围绕 Heap 进行
4. **OOM 排查必须先看哪个 Space 满了**：5 种 OOM 对应 5 种排查路径

→ **不理解 5 Space，就无法精准定位 OOM 的根本原因**。

---

## 跨节引用

**本节被以下章节引用**：
- [2.2 5 Space 详解](./02-5Space详解.md) —— 详细讲每个 Space
- [2.3 内存配额](./03-内存配额.md) —— `growth_limit` 等参数如何影响 Space 大小
- [2.4 RosAlloc](./04-RosAlloc分配器.md) —— Allocation Space 的 CMS 时代分配器
- [2.5 Region-based](./05-Region-based分配器.md) —— Allocation Space 的 CC 时代分配器
- 03/04/05 篇（CMS/CC/GenCC）—— 三种 GC 算法如何在 5 Space 上运作
- [09 篇诊断](../09-GC诊断与治理/) —— 5 种 OOM 的 dumpsys meminfo 解读

**本节引用**：
- [01 篇 1.1 可达性分析](../01-基础理论/01-可达性分析.md) —— GC Root 来源依赖 Heap 布局
- ART 大模块的 `02-类加载与链接` —— Image Space 的来源（OAT 文件）
