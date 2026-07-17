# 2.5 分配器 2：Region-based（CC 时代）

> **本节回答一个根本问题**：CC GC / GenCC 时代，ART 是怎么在 Allocation Space 中高效分配对象的？
>
> **答案**：用 **Region-based 分配器** —— 基于 Region 状态机 + Bump Pointer + TLAB 的分配器。
>
> **理解本节，就理解了 CC GC 为什么能实现 STW < 1ms** —— Region-based 是 CC GC 的物理基础。

---

## 一、Region-based 的设计思想

### 2.5.1 为什么需要 Region-based

RosAlloc + CMS 的两个核心问题：

| 问题 | 表现 | 根因 |
|:---|:---|:---|
| **碎片化严重** | 长期运行后 OOM | CMS 不压缩 + 分桶分配 |
| **STW 时间长** | 50ms+ 卡顿 | CMS 全堆扫描 |

CC GC 用 Region-based 解决这两个问题：
1. **碎片化**：CC GC 复制活对象到新 Region → 自动压缩，无碎片
2. **STW**：Region 状态机 + 读屏障 + 自愈指针 → < 1ms

### 2.5.2 Region 的核心思想

**Region**（区域）是一段 **固定大小**（默认 256 KB ~ 4 MB）的连续内存，Region 之间 **独立管理**：

```
┌─────────────────────────────────────────────────────────┐
│             Allocation Space (CC / GenCC)                │
│  ┌───────────────────────────────────────────────────┐   │
│  │  Region 0  │ Region 1  │ Region 2  │ Region 3   │   │
│  │  (Free)    │ (Alloc)   │ (Large)   │ (Old Gen)  │   │
│  │            │ TLAB      │           │            │   │
│  └───────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────┐   │
│  │  Region 4  │ Region 5  │ Region 6  │ Region 7   │   │
│  │  (Young)   │ (Young)   │ (Free)    │ (Alloc)    │   │
│  └───────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2.5.3 Region 的状态机

```cpp
// art/runtime/gc/space/region_space.h 的 RegionState（精简版）
enum RegionState : uint8_t {
  kRegionStateFree,           // 空闲，未分配
  kRegionStateAlloc,          // 正在分配（活跃 Region）
  kRegionStateLarge,          // 大对象（不可移动）
  kRegionStateLargeTail,      // 大对象的剩余部分
  kRegionStateNonMoving,      // 永不移动
  kRegionStateYoungGen,       // Young Gen（GenCC）
  kRegionStateOldGen,         // Old Gen（GenCC）
  kRegionStateLast,           // 哨兵
};
```

### 2.5.4 Region 状态转换图

```
                  ┌────────────┐
                  │   Free     │ ← 初始状态
                  └──────┬─────┘
                         │ Alloc()
                         ▼
                  ┌────────────┐
        ┌─────────│   Alloc    │─────────┐
        │         │  (TLAB)    │         │
        │ TLAB满  └────────────┘ GC完成   │ 大对象分配
        ▼                                  ▼
  ┌────────────┐                    ┌────────────┐
  │   Full     │                    │   Large    │
  │  (等待 GC) │                    │  (不可移动) │
  └────────────┘                    └────────────┘
        │                                  │
        │ GC 标记                           │ 大对象剩余
        ▼                                  ▼
  ┌────────────┐                    ┌────────────┐
  │   Free     │                    │ LargeTail  │
  │  (回收)    │                    │  (剩余部分) │
  └────────────┘                    └────────────┘
```

### 2.5.5 Region 的大小配置

```cpp
// art/runtime/gc/space/region_space.h
static constexpr size_t kRegionSize = 256 * KB;  // 默认 256 KB
// 可通过 system property 调整:
// dalvik.vm.heap.region.size = 256k / 512k / 1m / 2m / 4m
```

**Region 大小的影响**：
- **更小（如 256 KB）**：分配灵活，但 GC 扫描范围小
- **更大（如 4 MB）**：GC 扫描连续，但单 Region 内碎片化

ART 默认 256 KB 是工程权衡。

---

## 二、Bump Pointer 详解

### 2.5.6 Bump Pointer 的定义

**Bump Pointer**（撞针分配器）是 Region 的核心分配方式——比 RosAlloc 的 Run-of-Slots 更简单。

```cpp
// Region 内的分配伪代码
void* Region::Alloc(size_t num_bytes) {
    // 1. 检查 Region 是否还有空间
    if (top_ + num_bytes > end_) {
        return nullptr;  // Region 满了
    }
    
    // 2. bump pointer：返回 top_，top_ += num_bytes
    void* obj = top_;
    top_ += num_bytes;
    return obj;
}
```

**关键**：
- **无 free list**（与 RosAlloc 不同）
- **直接 bump pointer**（碰撞指针）
- **顺序分配**（连续地址）

### 2.5.7 Bump Pointer vs RosAlloc 对比

| 维度 | Bump Pointer | RosAlloc Run-of-Slots |
|:---|:---|:---|
| **分配速度** | ~1 ns（最快） | ~5 ns |
| **实现复杂度** | 极简 | 中等 |
| **碎片化** | 无（顺序） | 有（分桶） |
| **释放速度** | 不单独释放 | 不单独释放 |
| **GC 回收** | 整体回收（Region） | Sweep slot |

### 2.5.8 Region 内的分配路径

```
业务代码：new Object()
    │
    ▼
1. 检查 Thread::TLAB（Region TLAB）
    │
    ├─── TLAB 有空间
    │    │
    │    ▼
    │   2a. bump pointer 分配（无需加锁）
    │    │
    │    └─── 返回对象指针
    │
    └─── TLAB 用完
         │
         ▼
3. 申请新 TLAB（不同 Region）
    │
    ├─── 4. 从 Region Pool 拿一个 Free Region
    │
    ├─── 5. 设置为当前 Thread 的 TLAB
    │
    └─── 6. bump pointer 分配
```

---

## 三、Region TLAB 详解

### 2.5.9 Region TLAB 的定义

**Region TLAB** 是基于 Region 的 TLAB——每个 Thread 可以从一个 Free Region 中划出一段作为自己的 TLAB。

```cpp
// art/runtime/gc/space/region_space.h 的 RegionSpace::Alloc 精简版
mirror::Object* RegionSpace::Alloc(Thread* self, size_t num_bytes, ...) {
    // 1. 检查当前 Region 的 TLAB
    void* obj = self->tlab_.top_;
    if (obj + num_bytes <= self->tlab_.end_) {
        self->tlab_.top_ += num_bytes;
        return obj;  // TLAB 快速路径
    }
    
    // 2. TLAB 用完 → 申请新 Region 作为 TLAB
    Region* new_region = AllocateRegion(self);
    if (new_region == nullptr) {
        return nullptr;  // 没有空闲 Region
    }
    
    // 3. 设置 TLAB 为新 Region 的全部空间
    self->tlab_.start_ = new_region->Begin();
    self->tlab_.end_ = new_region->End();
    self->tlab_.top_ = new_region->Begin();
    
    // 4. 在新 TLAB 分配
    obj = self->tlab_.top_;
    self->tlab_.top_ += num_bytes;
    return obj;
}
```

### 2.5.10 Region Pool 的管理

```cpp
// Region Pool 的核心结构
class RegionPool {
    // 空闲 Region 链表
    std::vector<Region*> free_regions_;
    
    // 所有 Region 数组
    std::vector<Region> regions_;
    
public:
    Region* AllocateRegion() {
        // 1. 从空闲 Region 链表取
        if (!free_regions_.empty()) {
            Region* region = free_regions_.back();
            free_regions_.pop_back();
            return region;
        }
        
        // 2. 分配新 Region（向系统申请内存）
        Region* new_region = AllocateNewRegion();
        if (new_region == nullptr) return nullptr;
        
        regions_.push_back(new_region);
        return new_region;
    }
};
```

### 2.5.11 Region 分配的多线程协调

```cpp
// 多线程分配时，Region Pool 需要加锁
Region* RegionSpace::AllocateRegion(Thread* self) {
    MutexLock lock(region_lock_);  // 全局锁
    
    if (!free_regions_.empty()) {
        Region* region = free_regions_.back();
        free_regions_.pop_back();
        return region;
    }
    
    // ...
}
```

**优化**：ART 用 **CAS（Compare-And-Swap）** 减少锁竞争。

---

## 四、Region-based 的释放

### 2.5.12 CC GC 的释放：标记-复制

CC GC **不单独释放**——用 **标记-复制** 算法：

```
CC GC 释放流程：
1. 标记阶段：
   - 标记所有存活对象
   - 通过 mark bitmap 记录

2. 复制阶段：
   - 把存活对象从 from-space 复制到 to-space
   - 设置 forwarding address
   - 读屏障自愈指针

3. 回收阶段：
   - 整个 from-space Region 变为 Free
   - 整块归还 Region Pool
```

### 2.5.13 Region 整体回收

```cpp
// art/runtime/gc/collector/concurrent_copying.cc 的 ReclaimPhase 精简版
void ConcurrentCopying::ReclaimPhase() {
    // 1. 切换 from-space / to-space
    heap_->SwapSemiSpaces();
    
    // 2. 把 from-space 的所有 Region 标记为 Free
    for (Region* region : from_space_->GetRegions()) {
        region->state_ = kRegionStateFree;
        region_pool_->free_regions_.push_back(region);
    }
}
```

**关键**：整个 Region 一次性回收，**无碎片化**！

### 2.5.14 Region 回收与 LOS 的差异

| Space | 释放方式 | 碎片化 |
|:---|:---|:---|
| **Allocation Space (Region)** | 整体回收 Region | **无** |
| **LOS** | 单独释放对象 | **有**（外碎片） |

→ **CC GC 用 Region 整体回收解决了碎片化，但 LOS 仍有碎片化问题**（详见 2.7）。

---

## 五、GenCC 的 Region 分代

### 2.5.15 GenCC 的 Region 分类

```cpp
// GenCC 的 Region 分类（art/runtime/gc/space/region_space.h）
enum RegionState : uint8_t {
  kRegionStateFree,           // 空闲
  kRegionStateAlloc,          // 正在分配（年轻代）
  kRegionStateLarge,          // 大对象（不可移动）
  kRegionStateLargeTail,      // 大对象剩余
  kRegionStateNonMoving,      // 永不移动
  kRegionStateYoungGen,       // 年轻代（GenCC）
  kRegionStateOldGen,         // 老年代（GenCC）
};
```

### 2.5.16 Young Gen 与 Old Gen 的 Region

```
GenCC 的 Allocation Space:
  ┌─────────────────────────────────────────────┐
  │  Young Gen Regions                          │
  │  ┌────────┬────────┬────────┬────────┐     │
  │  │Region 0│Region 1│Region 2│Region 3│     │
  │  │ (Young)│ (Young)│ (Young)│ (Young)│     │
  │  │80% full│50% full│30% full│10% full│     │
  │  └────────┴────────┴────────┴────────┘     │
  └─────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────┐
  │  Old Gen Regions                            │
  │  ┌────────┬────────┬────────┬────────┐     │
  │  │Region 4│Region 5│Region 6│Region 7│     │
  │  │ (Old)  │ (Old)  │ (Old)  │ (Old)  │     │
  │  │90% full│70% full│50% full│20% full│     │
  │  └────────┴────────┴────────┴────────┘     │
  └─────────────────────────────────────────────┘
```

### 2.5.17 对象晋升（Promotion）

GenCC 把 Young Gen 中"活过一定次数 GC"的对象晋升到 Old Gen：

```cpp
// art/runtime/gc/collector/concurrent_copying.cc 的 Promote 简化版
void ConcurrentCopying::Promote(mirror::Object* obj) {
    // 1. 检查对象年龄（每次 Young GC +1）
    int age = obj->GetAge();
    if (age < kPromotionThreshold) {
        // 2. 未达阈值 → 复制到 Young Gen 新 Region
        CopyToYoungGen(obj);
    } else {
        // 3. 达到阈值 → 晋升到 Old Gen
        CopyToOldGen(obj);
    }
}
```

### 2.5.18 Minor GC vs Major GC

| GC 类型 | 扫描范围 | STW 时间 | 频率 |
|:---|:---|:---|:---|
| **Minor GC** | 只扫描 Young Gen | < 0.5ms | 高（每次 Young Gen 满） |
| **Major GC** | 扫描全堆 | < 50ms | 低（Old Gen 满时） |

→ **Minor GC 只扫描 Young Gen，通过 Card Table 找跨代引用**（详见 01 篇 1.5）。

---

## 六、Region-based 的完整分配路径

### 2.5.19 CC GC 的分配流程

```
业务代码：new Object()
    │
    ▼
1. JIT/AOT 调用 artAllocObject
    │
    ▼
2. Heap::AllocObject
    │
    ├─── 大对象 (≥ Region Size / 12 KB) → LOS
    │
    └─── 普通对象
         │
         ▼
3. RegionSpace::Alloc
    │
    ├─── 4. Thread::TLAB 分配（Region TLAB）
    │      │
    │      ├─── TLAB 有空间 → bump pointer（无需加锁）
    │      │
    │      └─── TLAB 用完 → 申请新 Region 作为 TLAB
    │
    ├─── 5. 申请新 Region（需要 Region Pool 锁）
    │
    └─── 6. 返回对象指针
```

### 2.5.20 Region 申请的慢速路径

```cpp
mirror::Object* RegionSpace::Alloc(Thread* self, size_t num_bytes, ...) {
    // 1. TLAB 快速路径
    if (HasSpace(self->tlab_, num_bytes)) {
        return BumpPointer(self, num_bytes);
    }
    
    // 2. TLAB 用完 → 申请新 Region
    Region* new_region = AllocNewRegion(self);
    if (new_region == nullptr) {
        // 3. 没有空闲 Region → 触发 GC
        self->GetHeap()->CollectGarbage(kGcCauseForAlloc, ...);
        
        // 4. GC 后重试
        new_region = AllocNewRegion(self);
        if (new_region == nullptr) {
            // 5. 仍失败 → OOM
            return nullptr;
        }
    }
    
    // 6. 设置 TLAB 为新 Region
    SetTLAB(self, new_region);
    
    // 7. 在新 TLAB 分配
    return BumpPointer(self, num_bytes);
}
```

---

## 七、Region-based 的性能特征

### 2.5.21 分配性能对比

| 分配器 | 快速路径耗时 | 备注 |
|:---|:---|:---|
| **Region TLAB（CC）** | ~1 ns | bump pointer |
| **RosAlloc TLAB（CMS）** | ~5 ns | Run slot |
| **Region TLAB + 跨 Region** | ~10 ns | 触发 PostWriteBarrier |
| **malloc 模拟** | ~100 ns | libc malloc |

### 2.5.22 碎片化分析

**Region-based 无碎片化**：
- 整个 Region 一次性回收
- 不存在 slot 级别的外碎片
- 对象是连续分配的（bump pointer）

**但有"Region 内部碎片"**：
- Region 大小 256 KB，对象 100 KB → 剩 156 KB 浪费
- 通常 < 1%，可接受

### 2.5.23 STW 时间对比

| GC | 标记 STW | 复制 STW | 清理 STW | 总 STW |
|:---|:---|:---|:---|:---|
| **CMS** | ~5ms | 0 | ~50ms | **~50ms** |
| **CC (Region)** | ~2ms | 0 | ~1ms | **< 5ms** |
| **GenCC Minor** | ~0.3ms | 0 | ~0.1ms | **< 0.5ms** |
| **GenCC Major** | ~5ms | 0 | ~2ms | **< 10ms** |

→ **GenCC Minor GC < 0.5ms STW 是用户体验的飞跃**。

---

## 八、Region-based 的源码

### 2.5.24 核心源码路径

```
art/runtime/gc/space/region_space.h        # RegionSpace 类
art/runtime/gc/space/region_space.cc       # RegionSpace 实现
art/runtime/gc/allocator/region_allocator.h # Region Allocator
art/runtime/gc/allocator/region_allocator.cc
art/runtime/gc/collector/concurrent_copying.cc # CC GC 主逻辑
art/runtime/thread.h                        # Thread::TLAB
art/runtime/thread.cc                       # TLAB 初始化
```

### 2.5.25 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `RegionSpace::Alloc` | `region_space.cc` | 分配对象 |
| `RegionSpace::AllocNewRegion` | `region_space.cc` | 申请新 Region |
| `RegionSpace::SwapSemiSpaces` | `region_space.cc` | 切换 from/to-space |
| `Region::Alloc` | `region_space.h` | 单 Region 内 bump pointer |
| `Region::IsFull` | `region_space.h` | 判断 Region 是否满 |
| `ConcurrentCopying::Promote` | `concurrent_copying.cc` | 对象晋升 |

### 2.5.26 Region 大小的影响

| Region Size | 优点 | 缺点 |
|:---|:---|:---|
| **256 KB** | 分配灵活，Minor GC 扫描快 | Region 数量多，状态机开销大 |
| **1 MB** | 平衡 | 默认值 |
| **4 MB** | Region 数量少，状态机开销小 | 内部碎片多，Minor GC 扫描慢 |

---

## 九、Region-based 的工程坑点

### 2.5.27 坑点 1：跨 Region 引用 + Card Table

**问题**：
```cpp
// Young Gen 的对象 A 引用 Old Gen 的对象 D
// → 跨 Region 引用 → 触发 PostWriteBarrier
// → 标记 Card Table
// → Minor GC 扫描这张 Card
```

**性能影响**：跨 Region 引用频繁时，Card Table 频繁 dirty → Minor GC 扫描开销大。

**解决方案**：
- ART 14+ 的细粒度 Card Table（详见 01 篇 1.5）
- Hot Card 优化

### 2.5.28 坑点 2：对象晋升失败

**问题**：
```cpp
// Old Gen 没有空闲 Region
// Young Gen 对象需要晋升 → 失败 → 触发 Major GC
```

**解决方案**：
- 调整 Old Gen / Young Gen 比例
- 减小对象晋升阈值

### 2.5.29 坑点 3：Region 内部碎片

**问题**：
```cpp
// 256 KB Region 内分配 100 KB 对象
// 剩余 156 KB 浪费
// → 长期运行后，Region 内部碎片累积
```

**解决方案**：
- 调整 Region Size
- 用 LOS 替代大对象（避免浪费 Region 内部空间）

---

## 十、Region-based vs RosAlloc 综合对比

### 2.5.30 设计哲学对比

| 维度 | RosAlloc（CMS） | Region-based（CC/GenCC） |
|:---|:---|:---|
| **设计目标** | 在固定堆内高效分配 | 为并发复制服务 |
| **核心思想** | 分桶 + 槽位 | 区域 + 碰撞 |
| **GC 策略** | 标记-清除 | 标记-复制 |
| **对象移动** | 不移动 | 移动（CC） |
| **碎片化** | 高 | 极低 |
| **回收粒度** | Slot | Region |

### 2.5.31 性能对比

| 指标 | RosAlloc | Region-based |
|:---|:---|:---|
| **分配速度** | ~5 ns | ~1 ns |
| **碎片化率** | ~20% | < 1% |
| **GC STW** | ~50ms | < 1ms |
| **适用 GC** | CMS | CC / GenCC |

---

## 十一、本节小结

1. **Region-based = Region + Bump Pointer + TLAB**
2. **Region 整体回收无碎片化**（CC GC 的关键优势）
3. **GenCC 的 Young/Old 分代让 Minor GC 只扫描 Young Gen**（STW < 0.5ms）
4. **Bump Pointer 比 RosAlloc 的 Run-of-Slots 更快**（~1 ns vs ~5 ns）

→ **理解 Region-based，就理解了 CC / GenCC 的物理基础**。

---

## 跨节引用

**本节被以下章节引用**：
- [2.6 Concurrent 分配器](./06-Concurrent分配器.md) —— Region-based 的并发分配
- [2.7 慢速路径与碎片化](./07-慢速路径与碎片化.md) —— LOS 仍有的碎片化
- 04 篇 CC GC —— Region-based + 读屏障
- 05 篇 GenCC —— Young/Old Gen + Card Table

**本节引用**：
- [2.4 RosAlloc](./04-RosAlloc分配器.md) —— 对比 RosAlloc
- [01 篇 1.4 读屏障](../01-基础理论/04-读屏障机制.md) —— CC GC 的读屏障依赖 Region
- [01 篇 1.5 卡表](../01-基础理论/05-记忆集与卡表.md) —— GenCC 的 Card Table
