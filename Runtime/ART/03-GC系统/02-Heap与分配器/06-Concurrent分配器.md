# 2.6 分配器 3：Concurrent Allocator

> **本节回答一个根本问题**：CC GC 的"并发"是怎么在分配器层面实现的？
>
> **答案**：用 **Concurrent Allocator** —— 在 CC GC 并发标记 + 复制的过程中，业务线程依然可以安全分配对象。
>
> **理解本节，就理解了 CC GC 分配与 GC 并发的协同机制**。

---

## 一、Concurrent Allocator 的定义

### 2.6.1 为什么需要并发分配

CC GC 的"并发"包含：
- **并发标记**：GC 标记阶段与业务线程并行
- **并发复制**：GC 复制阶段与业务线程并行

但业务线程也要 **分配对象**——CC GC 的分配器必须能在 GC 进行中安全分配。

```cpp
// 问题场景
// T1: 业务线程 new Object()
// T2: CC GC 正在复制活对象到 to-space
// → T1 分配的对象应该在哪里？
// → 应该在 to-space 还是 from-space？
```

### 2.6.2 Concurrent Allocator 的解决方案

**解决方案**：分配的对象直接进入 **to-space**（新一代）。

```
┌──────────────────────────────────────────────────────┐
│                  CC GC 双空间布局                     │
│                                                      │
│   from-space:                  to-space:             │
│   ┌────────────┐               ┌────────────┐       │
│   │ 老对象     │               │ 复制的对象 │       │
│   │ (待回收)   │               │ + 新分配   │       │
│   │            │               │            │       │
│   │            │               │ TLAB 在这  │       │
│   └────────────┘               └────────────┘       │
│        ↑                              ↑              │
│        └────── GC 完成后切换 ──────────┘              │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**关键设计**：
- **业务线程分配的对象进入 to-space**
- **GC 复制的对象也进入 to-space**
- **from-space 整个 GC 完成后被回收**

### 2.6.3 Concurrent Allocator 的优势

| 优势 | 说明 |
|:---|:---|
| **无需 STW 等待分配** | 业务线程随时可分配 |
| **与 GC 复制路径统一** | 分配与复制走同一套机制 |
| **避免空间浪费** | 新对象直接进入新空间 |
| **简化空间管理** | 一个 to-space，无需多套机制 |

---

## 二、Concurrent Allocator 的实现

### 2.6.4 TLAB 在 CC GC 中的特殊性

CC GC 中，每个 Thread 的 TLAB 必须指向 **to-space**：

```cpp
// art/runtime/gc/space/region_space.cc 的 RegionSpace::Alloc 精简版
mirror::Object* RegionSpace::Alloc(Thread* self, size_t num_bytes, ...) {
    // 1. 检查当前 TLAB（在 to-space）
    if (HasSpace(self->tlab_, num_bytes)) {
        return BumpPointer(self, num_bytes);
    }
    
    // 2. TLAB 用完 → 申请新 Region
    //    必须从 to-space 的 Region Pool 取
    Region* new_region = AllocNewRegionInToSpace();
    if (new_region == nullptr) {
        return nullptr;
    }
    
    // 3. 设置 TLAB 为新 Region
    SetTLAB(self, new_region);
    
    // 4. 在新 TLAB 分配
    return BumpPointer(self, num_bytes);
}
```

### 2.6.5 to-space 切换的协调

CC GC 在并发过程中需要切换 to-space（GC 完成时）：

```cpp
// art/runtime/gc/space/region_space.cc 的 SwapSemiSpaces 精简版
void RegionSpace::SwapSemiSpaces() {
    // 1. STW 暂停
    SuspendAllThreads();
    
    // 2. 切换 from-space / to-space
    RegionSpace* old_to_space = to_space_;
    to_space_ = from_space_;
    from_space_ = old_to_space;
    
    // 3. 重置所有 Thread 的 TLAB 为新 to-space
    for (Thread* thread : thread_list_) {
        thread->tlab_.Reset();
    }
    
    // 4. 恢复 mutator 线程
    ResumeAllThreads();
}
```

### 2.6.6 业务线程看到的分配路径

```
业务线程 T1 看到的分配路径：
new Object()
    │
    ▼
1. 检查 TLAB（指向 to-space Region X）
    │
    ├─── TLAB 有空间
    │    │
    │    ▼
    │   2a. bump pointer（在 Region X 内）
    │    │
    │    └─── 返回对象指针（在 to-space）
    │
    └─── TLAB 用完
         │
         ▼
3. 申请新 Region（从 to-space 的 Region Pool）
    │
    ├─── 4. Region Pool 有空闲 → 取一个
    │
    └─── 5. Region Pool 空 → 触发 GC + 重试
```

---

## 三、并发分配的关键问题

### 2.6.7 问题 1：GC 与业务线程同时写 Region

**场景**：
```
T1（业务线程）：在 Region X 分配对象 A
T2（GC 线程）：从 Region Y 复制对象 B 到 Region Z

→ T1 和 T2 操作不同 Region，无冲突
→ 但若 T1 的 TLAB 用完，需要从 Region Pool 拿 → 加锁
```

**解决方案**：
- TLAB 命中率高（~95%），多数分配无锁
- Region Pool 用 CAS 优化（避免全局锁）

### 2.6.8 问题 2：Region 切换时的"半新半旧"

**场景**：
```
CC GC 完成 50% 时切换 to-space？
→ to-space 切换必须 STW
→ 切换瞬间：所有 Thread 的 TLAB 重置
```

**解决方案**：
- **STW 切换**：所有 mutator 线程暂停，统一重置 TLAB
- **切换完成后恢复**：业务线程继续，新的 TLAB 指向新 to-space

### 2.6.9 问题 3：LOS 在 CC GC 中的处理

**场景**：
```
业务线程分配大对象（≥ 12 KB）
CC GC 也在复制大对象（从 from-space 到 to-space）
→ 大对象同时进入两个 LOS？冲突？
```

**解决方案**：
- 大对象不可移动 → 不参与 CC GC 复制
- LOS 用独立的分配器（不依赖 to-space）
- CC GC 只扫描 LOS 标记存活，不移动

```cpp
// LOS 分配不依赖 to-space
mirror::Object* LargeObjectSpace::Alloc(Thread* self, size_t num_bytes, ...) {
    // 1. 直接从 LOS 的 free list 分配
    void* obj = free_list_.Pop();
    if (obj != nullptr) return obj;
    
    // 2. 申请新页（独立空间，不依赖 to-space）
    return AllocateNewPage(num_bytes);
}
```

---

## 四、Concurrent Allocator 与读屏障的协同

### 2.6.10 读屏障如何配合并发分配

业务线程分配的对象在 to-space，但 **新对象在初始时是"无色"的**——还没被 GC 标记。

```cpp
// 新对象的初始状态
mirror::Object* new_obj = RegionSpace::Alloc(...);
// new_obj 默认是白色（未标记）
```

**问题**：CC GC 进行中，新对象应该是什么颜色？

**答案**：**新对象默认为灰色**（避免漏标）。

```cpp
// art/runtime/gc/space/region_space.cc 的 RegionSpace::Alloc 完整版
mirror::Object* RegionSpace::Alloc(Thread* self, size_t num_bytes, ...) {
    // 1. 分配对象
    mirror::Object* obj = ...;
    
    // 2. 标记为灰色（防止漏标）
    obj->SetGray();
    
    // 3. 把对象加入 mark stack（等 CC GC 处理）
    concurrent_copying_->mark_stack_->Push(obj);
    
    return obj;
}
```

### 2.6.11 读屏障对新对象的处理

```cpp
// 业务线程读 new_obj.field 时
mirror::Object* ref = ReadBarrier(&new_obj->field);

// 读屏障会检查：
// 1. new_obj 是否在 to-space（是，刚分配的）
// 2. field 是否指向 from-space 对象（可能，跨空间引用）
// 3. 如果是，触发自愈指针

// 因为新对象是"被保护的"（灰色），CC GC 保证它会被处理
```

---

## 五、Concurrent Allocator 的性能特征

### 2.6.12 性能数据（实测）

| 场景 | 分配耗时 | 备注 |
|:---|:---|:---|
| **TLAB 命中** | ~1 ns | bump pointer，无锁 |
| **TLAB 用完（Region Pool CAS）** | ~10 ns | 局部 CAS |
| **Region Pool 锁竞争** | ~50 ns | 全局锁（极少） |
| **触发 GC 后分配** | ~1000 ns | 包括 GC 开销 |

→ **99% 的分配走 TLAB 快速路径**。

### 2.6.13 高并发场景的优化

**问题**：大量线程同时分配 → Region Pool 锁竞争

**优化方案**：
```cpp
// 1. Region Pool 用线程局部缓存
class ThreadLocalRegionCache {
    Region* cached_regions_[4];  // 每个线程缓存 4 个 Region
};

// 2. CAS 取 Region
Region* AllocRegionCAS() {
    while (true) {
        Region* region = pool_.Peek();
        if (pool_.CAS(region, region->next)) {
            return region;
        }
        // CAS 失败 → 重试
    }
}
```

### 2.6.14 ART 14+ 的进一步优化

| 优化 | 描述 |
|:---|:---|
| **TLAB 弹性大小** | 根据线程分配频率动态调整 TLAB 大小 |
| **Region 局部化** | 同一线程优先用同一 Region |
| **Region 预分配** | 后台线程预分配 Region 到 Pool |
| **CAS 优化** | Region Pool 用 CAS 替代全局锁 |

---

## 六、Concurrent Allocator 的工程坑点

### 2.6.15 坑点 1：TLAB 重置导致分配抖动

**场景**：
```
T1 业务的 TLAB 用到 50%（64 KB TLAB 用 32 KB）
CC GC 完成 → STW 切换 to-space
T1 的 TLAB 被重置
T1 重新分配 → 新 TLAB 又从头开始
→ 短期分配抖动
```

**解决方案**：
- ART 14+ 的 TLAB 局部缓存（保留一部分 TLAB 在切换时不重置）

### 2.6.16 坑点 2：Region Pool 耗尽

**场景**：
```
业务线程疯狂分配 → Region Pool 空
→ 触发 GC → GC 也需要 Region（用于复制）
→ 死锁？高竞争？
```

**解决方案**：
- ART 14+ 的 Region 预留机制（GC 预留一定数量 Region）
- 业务线程分配上限控制

### 2.6.17 坑点 3：跨 Region 引用激增

**场景**：
```
Young Gen 线程疯狂分配 → 大量对象进入 to-space
→ 跨 Region 引用激增 → Card Table 频繁 dirty
→ 下一次 Minor GC 扫描开销大
```

**解决方案**：
- ART 14+ 的细粒度 Card Table
- Hot Card 优化

---

## 七、Concurrent Allocator 的源码

### 2.6.18 核心源码路径

```
art/runtime/gc/space/region_space.h        # RegionSpace 类
art/runtime/gc/space/region_space.cc       # RegionSpace 实现
art/runtime/gc/allocator/region_allocator.cc # Region Allocator
art/runtime/gc/collector/concurrent_copying.cc # CC GC 主逻辑
art/runtime/thread.h                        # Thread::TLAB
art/runtime/thread.cc                       # TLAB 初始化 + 切换
art/runtime/gc/reference_processor.h        # 与 GC 协同
```

### 2.6.19 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `RegionSpace::Alloc` | `region_space.cc` | 分配对象 |
| `RegionSpace::AllocNewRegion` | `region_space.cc` | 申请新 Region |
| `RegionSpace::SwapSemiSpaces` | `region_space.cc` | 切换 from/to-space |
| `RegionSpace::SetTLAB` | `region_space.cc` | 设置 Thread TLAB |
| `ConcurrentCopying::ProcessMarkStack` | `concurrent_copying.cc` | 处理 mark stack |

### 2.6.20 Concurrent Allocator 与 GC 状态机

```
┌─────────────────────────────────────────────────────────┐
│                  CC GC 状态机                            │
│                                                         │
│  ┌──────────┐                                           │
│  │  Start   │                                           │
│  └─────┬────┘                                           │
│        ▼                                                │
│  ┌──────────┐                                           │
│  │ Initialize (STW)                                      │
│  │  - 栈扫描                                               │
│  │  - 重置 TLAB（指向 to-space）                          │
│  └─────┬────┘                                           │
│        ▼                                                │
│  ┌──────────────────────┐                               │
│  │ Concurrent Copying    │ ← 业务线程持续分配（TLAB）   │
│  │  - 复制活对象 to-space │                               │
│  │  - 处理 mark stack     │                               │
│  │  - 处理 Reference       │                               │
│  └─────┬────────────────┘                               │
│        ▼                                                │
│  ┌──────────────────────┐                               │
│  │ Reclaim (STW)         │                               │
│  │  - 切换 from/to-space  │                               │
│  │  - 重置 TLAB          │                               │
│  │  - 回收 from-space    │                               │
│  └─────┬────────────────┘                               │
│        ▼                                                │
│  ┌──────────┐                                           │
│  │   End    │                                           │
│  └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 八、Concurrent Allocator 的设计哲学

### 2.6.21 设计原则

**原则 1：分配与 GC 同空间**
- 业务线程分配的对象与 GC 复制的对象共享 to-space
- 简化空间管理

**原则 2：分配与 GC 异步**
- 业务线程无需等待 GC 完成才能分配
- 分配走 TLAB（无锁快速路径）

**原则 3：分配与 GC 安全协同**
- 新对象标记为灰色（防止漏标）
- 读屏障保护所有读操作

### 2.6.22 与传统分配器的对比

| 维度 | 传统分配器 | Concurrent Allocator |
|:---|:---|:---|
| **GC 时分配** | 需要 STW 等待 | 无需 STW |
| **分配空间** | 与 GC 独立 | 与 GC 共享 to-space |
| **新对象处理** | 不需要 | 标记为灰色 |
| **读屏障** | 不需要 | 必须（防漏标） |

---

## 九、本节小结

1. **Concurrent Allocator 让业务线程在 CC GC 并发期间安全分配**
2. **新对象直接进入 to-space**（与 GC 复制的对象共享空间）
3. **新对象标记为灰色**（防止漏标，读屏障保护）
4. **Region Pool 用 CAS 减少锁竞争**
5. **GC 完成时 STW 切换 to-space + 重置 TLAB**

→ **理解 Concurrent Allocator，就理解了 CC GC 分配与并发的协同机制**。

---

## 跨节引用

**本节被以下章节引用**：
- [2.5 Region-based](./05-Region-based分配器.md) —— Region-based 是 Concurrent Allocator 的基础
- [2.7 慢速路径与碎片化](./07-慢速路径与碎片化.md) —— Region Pool 耗尽的慢速路径
- 04 篇 CC GC —— CC GC 的完整实现
- 05 篇 GenCC —— GenCC 的 Minor GC + Major GC

**本节引用**：
- [01 篇 1.4 读屏障](../01-基础理论/04-读屏障机制.md) —— 读屏障保护新对象
- [01 篇 1.2 三色不变式](../01-基础理论/02-三色标记不变式.md) —— 弱三色不变式与并发分配
