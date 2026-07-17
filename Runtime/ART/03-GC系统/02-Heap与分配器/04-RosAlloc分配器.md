# 2.4 分配器 1：RosAlloc（CMS 时代）

> **本节回答一个根本问题**：CMS GC 时代，ART 是怎么在 Allocation Space 中高效分配对象的？
>
> **答案**：用 **RosAlloc**（Run-of-Slots Allocator）—— 基于 Run-of-Slots + TLAB + 大小分桶的分配器。
>
> **理解本节，就理解了 CMS 时代分配的性能特征 + 碎片化根因**。

---

## 一、RosAlloc 的设计思想

### 2.4.1 为什么需要专门的分配器

如果 ART 用简单的 `malloc/free` 分配 Java 对象，会有以下问题：

| 问题 | 影响 |
|:---|:---|
| `malloc` 慢 | 每次分配 ~100ns，影响性能 |
| 碎片化 | 长期运行后碎片化严重 |
| 多线程竞争 | 共享堆，分配需要加锁 |
| 无 GC 感知 | 与 ART GC 集成困难 |

### 2.4.2 RosAlloc 的三大核心设计

```
┌──────────────────────────────────────────────────────┐
│                  RosAlloc 设计原则                     │
├──────────────────────────────────────────────────────┤
│                                                      │
│  1. Run-of-Slots（槽位运行）                          │
│     - 把空间分成多个 Run，每个 Run 内是连续 slot       │
│     - 同大小对象分配 → 走同一 Run                     │
│     - 减少内部碎片                                   │
│                                                      │
│  2. TLAB（Thread Local Allocation Buffer）            │
│     - 每个线程独立的分配缓冲                           │
│     - 线程分配无锁                                   │
│     - 提升多线程性能                                 │
│                                                      │
│  3. 大小分桶                                         │
│     - 按对象大小分成多个 bin                          │
│     - 同大小对象走同一 bin 的 Run                     │
│     - 减少外部碎片                                   │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 2.4.3 RosAlloc 的内存布局

```
┌──────────────────────────────────────────────────────────┐
│                   Allocation Space (256 MB)               │
│  ┌────────────────────────────────────────────────────┐  │
│  │              RosAlloc 管理                          │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  Free Page Run: 空闲页面                      │  │  │
│  │  │  ┌──────────────────────────────────────┐    │  │  │
│  │  │  │  Thread 1 TLAB (16 KB)                │    │  │  │
│  │  │  └──────────────────────────────────────┘    │  │  │
│  │  │  ┌──────────────────────────────────────┐    │  │  │
│  │  │  │  Thread 2 TLAB (16 KB)                │    │  │  │
│  │  │  └──────────────────────────────────────┘    │  │  │
│  │  │  ┌──────────────────────────────────────┐    │  │  │
│  │  │  │  Run 0 (16B objects): slots × 16    │    │  │  │
│  │  │  │  ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐    │    │  │  │
│  │  │  │ │A│B│C│D│E│ │ │ │ │ │ │ │ │ │ │ │    │    │  │  │
│  │  │  │ └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘    │    │  │  │
│  │  │  └──────────────────────────────────────┘    │  │  │
│  │  │  ┌──────────────────────────────────────┐    │  │  │
│  │  │  │  Run 1 (32B objects): slots × 32    │    │  │  │
│  │  │  │  ┌──┬──┬──┬──┬──┬──┬──┬──┬──┐      │    │  │  │
│  │  │  │ │F │G │H │ │ │ │ │ │ │ │      │    │    │  │  │
│  │  │  │ └──┴──┴──┴──┴──┴──┴──┴──┴──┘      │    │  │  │
│  │  │  └──────────────────────────────────────┘    │  │  │
│  │  │  ┌──────────────────────────────────────┐    │  │  │
│  │  │  │  Run 2 (64B objects): slots × 64    │    │  │  │
│  │  │  │  ┌───┬───┬───┬───┐                  │    │  │  │
│  │  │  │ │ I │ J │   │   │                  │    │  │  │
│  │  │  │ └───┴───┴───┴───┘                  │    │  │  │
│  │  │  └──────────────────────────────────────┘    │  │  │
│  │  │  ...                                          │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 二、Run-of-Slots 详解

### 2.4.4 Run 的定义

```cpp
// art/runtime/gc/allocator/rosalloc.h（精简版）
class RosAlloc {
 public:
  // 一个 Run 是一段连续内存，被分成固定大小的 slot
  // 例如 16B 的 Run 包含 256 个 slot（4 KB 一页）
  class Run {
    mirror::Object** slots_;        // slot 指针数组
    uint32_t free_list_index_;      // 下一个空闲 slot 的索引
    uint32_t size_;                 // slot 大小
    // ...
  };
  
  // 不同 size_class 的 Run
  static constexpr size_t kPageSize = 4 * KB;
  static constexpr size_t kNumOfSizeBrackets = ...;  // ~30 个 size class
};
```

### 2.4.5 Size Class 分桶

```cpp
// RosAlloc 的 size class 列表
static const size_t kSizeClasses[] = {
  16, 24, 32, 40, 48, 56, 64,        // 8 字节对齐：16B ~ 64B
  72, 80, 88, 96, 104, 112, 120, 128, // 128B
  144, 160, 176, 192, 208, 224, 240, 256, // 256B
  // ... 一共 ~30 个 size class
  3072, 4096                          // 最大 4 KB（更大切 LOS）
};
```

**size class 设计原则**：
- 小对象（< 64B）：8 字节对齐
- 中对象（64B ~ 1KB）：8 字节对齐
- 大对象（> 1KB）：256 字节对齐
- 超大对象（≥ 4KB）：走 LOS

### 2.4.6 Run 的工作流程

```
分配 16B 对象：
1. 计算 size class：16B → bin 0
2. 找到 bin 0 的当前 Run
3. 从 Run 分配一个 slot
   - bump pointer：slot_index++
4. 返回 slot 地址

释放对象（CMS 标记-清除）：
1. 找到对象的 size class
2. 找到对象的 Run
3. 把 slot 加入 Run 的 free list
4. CMS Sweep 时统一回收
```

### 2.4.7 Run 的 Free List

每个 Run 维护一个 **free list**（空闲 slot 链表）：

```
Run 0 (16B objects), 256 slots:
  ┌───┬───┬───┬───┬───┬───┬───┬───┬───┬───┐
  │ 0 │ 1 │ 2 │ 3 │ 4 │ 5 │ ... │254│255│  ← slot 索引
  └───┴───┴───┴───┴───┴───┴───┴───┴───┴───┘
   [已用][已用][已用][已用][空闲][空闲]...[空闲]

free_list:
  head → 4 → 5 → 254 → 255 → nullptr
```

分配时从 free_list 头部取，回收时插入头部。

---

## 三、TLAB 详解

### 2.4.8 TLAB 的定义

**TLAB**（Thread Local Allocation Buffer）是 **每个线程独立的分配缓冲**——线程在 TLAB 内分配对象无需加锁。

```cpp
// art/runtime/thread.h 的 Thread 类（精简版）
class Thread {
 public:
  // 线程独立的 TLAB（RosAlloc）
  struct TLAB {
    void* start_;           // TLAB 起始地址
    void* end_;             // TLAB 结束地址
    void* top_;             // 当前分配位置（bump pointer）
    size_t alloc_size_;     // TLAB 总大小
  };
  
  TLAB tlab_;               // 每个 Thread 一个 TLAB
};
```

### 2.4.9 TLAB 的工作流程

```
Thread 1 调用 new Object():
1. 检查 TLAB：
   - TLAB top + obj_size <= TLAB end ?
   - 是 → bump pointer 分配
   - 否 → 走慢速路径
2. bump pointer：返回 top_，top_ += obj_size

```

```
TLAB 分配流程（伪代码）:
  Object* obj = thread.tlab_.top_;
  thread.tlab_.top_ += obj_size;
  return obj;

无需加锁！
```

### 2.4.10 TLAB 满时的慢速路径

```cpp
// 慢速路径伪代码
Object* AllocInSlowPath(Thread* thread, size_t obj_size) {
    // 1. TLAB 用完 → 获取新的 TLAB
    void* new_tlab = AllocateNewTLAB(thread, kTLABSize);
    
    // 2. 设置新的 TLAB
    thread->tlab_.start_ = new_tlab;
    thread->tlab_.end_ = new_tlab + kTLABSize;
    thread->tlab_.top_ = new_tlab;
    
    // 3. 重新分配
    Object* obj = thread->tlab_.top_;
    thread->tlab_.top_ += obj_size;
    return obj;
}
```

### 2.4.11 TLAB 大小配置

```cpp
// art/runtime/thread.cc 的 Thread 初始化（精简版）
void Thread::InitTlab() {
    // TLAB 大小：默认 64 KB ~ 256 KB
    // 取决于线程类型
    if (IsMainThread()) {
        tlab_size_ = 256 * KB;  // 主线程更大
    } else {
        tlab_size_ = 64 * KB;   // 子线程较小
    }
}
```

---

## 四、RosAlloc 的完整分配路径

### 2.4.12 分配路径流程图

```
业务代码：new Object()
    │
    ▼
1. JIT/AOT 调用 artAllocObject
    │
    ▼
2. 检查对象大小
    │
    ├─── 大对象 (≥ 12 KB) → LOS
    │
    └─── 普通对象
         │
         ▼
3. Thread::TLAB 分配（快速路径）
    │
    ├─── TLAB 有空间
    │    │
    │    ▼
    │   4a. bump pointer（无需加锁）
    │    │
    │    └─── 返回对象指针
    │
    └─── TLAB 用完
         │
         ▼
4b. 走慢速路径
    │
    ├─── 5. 申请新的 TLAB
    │      │
    │      └─── 需要加锁（全局锁）
    │
    ├─── 6. 尝试 RosAlloc::Alloc
    │      │
    │      ├─── 有空闲 Run → 分配 slot
    │      │
    │      └─── 无空闲 Run → 申请新页 → 分配
    │
    └─── 7. 返回对象指针
```

### 2.4.13 慢速路径详解

```cpp
// art/runtime/gc/space/malloc_space.cc 的 MallocSpace::Alloc 精简版
mirror::Object* MallocSpace::Alloc(Thread* self, size_t num_bytes, ...) {
    RosAlloc* rosalloc = reinterpret_cast<RosAlloc*>(allocator_.get());
    
    // 1. 快速路径：TLAB
    void* obj = rosalloc->AllocTLAB(self, num_bytes);
    if (obj != nullptr) return obj;
    
    // 2. TLAB 用完 → 慢速路径
    void* new_tlab = rosalloc->AllocNewTLAB(self, num_bytes);
    if (new_tlab != nullptr) {
        // 3. 设置新的 TLAB
        self->tlab_.start_ = new_tlab;
        self->tlab_.end_ = (char*)new_tlab + rosalloc->TLABSize();
        self->tlab_.top_ = new_tlab;
        
        // 4. 在新 TLAB 分配
        obj = self->tlab_.top_;
        self->tlab_.top_ = (char*)self->tlab_.top_ + num_bytes;
        return obj;
    }
    
    // 5. RosAlloc 也分配失败
    return nullptr;
}
```

### 2.4.14 RosAlloc::Alloc 详解

```cpp
// art/runtime/gc/allocator/rosalloc.cc 的 RosAlloc::Alloc 精简版
void* RosAlloc::Alloc(Thread* self, size_t num_bytes) {
    // 1. 计算 size class
    size_t size_class = SizeToIndex(num_bytes);
    
    // 2. 找到对应 size class 的 Run
    Run* run = runs_[size_class];
    
    // 3. 从 Run 的 free list 取 slot
    if (run->free_list_index_ < run->num_slots_) {
        void* slot = run->slots_[run->free_list_index_++];
        return slot;
    }
    
    // 4. Run 用完 → 申请新的 Run
    run = AllocRun(size_class);
    if (run == nullptr) return nullptr;
    
    // 5. 从新 Run 分配
    void* slot = run->slots_[run->free_list_index_++];
    return slot;
}
```

---

## 五、RosAlloc 的释放路径

### 2.4.15 CMS 的释放：标记-清除

RosAlloc **不主动释放**——CMS 用 **标记-清除** 算法：

```
CMS GC 释放流程：
1. 标记阶段：
   - 标记所有存活对象
   - 通过 mark bitmap 记录

2. 清除阶段（Sweep）：
   - 遍历 Allocation Space 的所有 Run
   - 未标记的 slot → 加入 Run 的 free list
   - 完全空闲的 Run → 归还内存
```

### 2.4.16 Sweep 的实现

```cpp
// art/runtime/gc/collector/mark_sweep.cc 的 MarkSweep::Sweep 精简版
void MarkSweep::Sweep(space::MallocSpace* space) {
    // 1. 遍历空间内所有页
    for (Page* page : space->GetPages()) {
        // 2. 遍历页内的所有 Run
        for (Run* run : page->GetRuns()) {
            // 3. 遍历 Run 内所有 slot
            for (size_t i = 0; i < run->num_slots_; i++) {
                void* slot = run->slots_[i];
                if (!IsMarked(slot)) {
                    // 4. 未标记 → 加入 free list
                    run->free_list_.Push(slot);
                }
            }
        }
    }
}
```

### 2.4.17 RosAlloc 与 CMS 的协同

```
┌────────────────────────────────────────────────────────┐
│                  CMS + RosAlloc 协同                    │
│                                                        │
│  分配：                                                │
│  业务代码 → TLAB → RosAlloc::Alloc → Run free list    │
│      (快速)    (无锁)      (有锁)      (快速)          │
│                                                        │
│  释放：                                                │
│  CMS Sweep → 遍历 Run → 未标记 slot → 加入 free list  │
│  (STW)        (遍历)    (扫描)        (回收)            │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## 六、RosAlloc 的性能特征

### 2.4.18 分配性能对比

| 路径 | 耗时 | 加锁 |
|:---|:---|:---|
| TLAB 快速路径 | ~5 ns | 无 |
| RosAlloc 慢速路径 | ~50 ns | 有 |
| malloc 模拟 | ~100 ns | 有 |

→ **TLAB 让分配性能接近无锁分配**。

### 2.4.19 碎片化分析

RosAlloc 的碎片化有两个来源：

**内部碎片**：
- 对象实际大小 vs size class 分配大小 的差距
- 例：对象 17B → 分配 24B → 浪费 7B

**外部碎片**：
- 释放的 slot 不能跨 Run 复用
- 例：Run A（16B slot）释放了 100 个 slot，但其他对象需要 32B slot → 这些 slot 没用

### 2.4.20 碎片化的根本原因

**CMS 不压缩 + RosAlloc 按 size class 分桶** = 碎片化必然

```
CMS GC 后状态：
  Run A (16B): 50% 使用
  Run B (32B): 30% 使用
  Run C (64B): 20% 使用
  Run D (16B): 10% 使用
  ...

→ Run A 和 Run D 都是 16B slot，但被碎片化分隔，无法合并
→ 即使总空闲很多，也无法满足 32B 的连续分配
```

→ **这是 CMS 时代的硬伤，CC GC 的 Region-based 才解决**。

---

## 七、RosAlloc 的源码

### 2.4.21 核心源码路径

```
art/runtime/gc/allocator/rosalloc.h        # RosAlloc 类
art/runtime/gc/allocator/rosalloc.cc       # RosAlloc 实现
art/runtime/gc/space/malloc_space.h        # MallocSpace（包含 RosAlloc）
art/runtime/gc/space/malloc_space.cc
art/runtime/thread.h                        # Thread::TLAB
art/runtime/thread.cc                       # TLAB 初始化
```

### 2.4.22 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `RosAlloc::Alloc` | `rosalloc.cc` | 分配对象 |
| `RosAlloc::AllocTLAB` | `rosalloc.cc` | TLAB 分配 |
| `RosAlloc::AllocNewTLAB` | `rosalloc.cc` | 新 TLAB |
| `RosAlloc::Free` | `rosalloc.cc` | 释放对象 |
| `RosAlloc::Sweep` | `rosalloc.cc` | CMS Sweep 回收 |
| `Thread::InitTlab` | `thread.cc` | TLAB 初始化 |
| `Thread::AllocTlab` | `thread.cc` | 线程 TLAB 分配 |

### 2.4.23 RosAlloc 的关键常量

```cpp
// art/runtime/gc/allocator/rosalloc.h
static constexpr size_t kPageSize = 4 * KB;  // 4 KB 一页
static constexpr size_t kNumOfSizeBrackets = 36;  // 36 个 size class
static constexpr size_t kMaxSizeBracketSize = 4096;  // 最大 4 KB
static constexpr size_t kLargeObjectThreshold = 3 * kPageSize;  // 12 KB 大对象阈值
```

---

## 八、RosAlloc 的工程坑点

### 2.4.24 坑点 1：TLAB 浪费内存

**问题**：
```cpp
// TLAB 大小 64 KB
// 但某个线程分配大量 24 字节对象
// TLAB 内的 64 KB 中，可能只有 16 KB 被有效使用
// 剩余 48 KB 浪费（TLAB 没满但不释放）
```

**解决方案**：
- ART 8+ 的 ThreadLocalCardTable 优化（详见 05 篇）
- 减小 TLAB 大小（增加 GC 频率，但减少浪费）

### 2.4.25 坑点 2：Size Class 不匹配

**问题**：
```java
// 对象实际 17 字节
class MyObject {
    int x;        // 4 字节
    byte y;       // 1 字节
    Object z;     // 4 字节（引用）
    // padding: 8 字节
}
// 总大小：约 24 字节 → 分配 24 字节（实际 17，浪费 7）
```

**解决方案**：
- 优化字段顺序（避免 padding）
- 用基本类型替代包装类

### 2.4.26 坑点 3：多线程 TLAB 竞争

**问题**：
```cpp
// 主线程和子线程都在分配对象
// 各线程有独立 TLAB，但新 TLAB 申请需要全局锁
// 高并发场景下，全局锁成为瓶颈
```

**解决方案**：
- ART 8+ 的 Region-based 分配器（每个线程独立 Region）
- CC GC 的并发分配（详见 2.6）

---

## 九、RosAlloc vs Region-based

### 2.4.27 对比表

| 维度 | RosAlloc | Region-based |
|:---|:---|:---|
| **适用 GC** | CMS | CC / GenCC |
| **TLAB** | 线程独立 | 线程独立 |
| **Run / Region** | 固定 size class | 动态大小 |
| **碎片化** | 高 | 低 |
| **对象移动** | 不移动 | 移动（CC） |
| **STW 时间** | 长（CMS） | 短（CC < 1ms） |
| **分配速度** | 快（TLAB） | 快（bump pointer） |

---

## 十、本节小结

1. **RosAlloc = Run-of-Slots + TLAB + 大小分桶**
2. **TLAB 让分配性能接近无锁分配**（~5 ns）
3. **CMS 不压缩 + 分桶 = 碎片化必然**（CC GC 的根本动机）
4. **TLAB 浪费 + Size Class 不匹配是主要性能损耗**

→ **理解 RosAlloc，就理解了 CMS 时代的分配特征 + 为什么需要 CC GC**。

---

## 跨节引用

**本节被以下章节引用**：
- [2.5 Region-based](./05-Region-based分配器.md) —— CC 时代的分配器，对比 RosAlloc
- [2.6 Concurrent 分配器](./06-Concurrent分配器.md) —— Region-based 的并发分配
- [2.7 慢速路径与碎片化](./07-慢速路径与碎片化.md) —— RosAlloc 碎片化的根因
- 03 篇 CMS —— RosAlloc + CMS 的协同

**本节引用**：
- [2.1 Heap 总览](./01-Heap总览.md) —— Allocation Space 在 Heap 中的位置
- [2.3 内存配额](./03-内存配额.md) —— `growth_limit` 对 RosAlloc 的影响
