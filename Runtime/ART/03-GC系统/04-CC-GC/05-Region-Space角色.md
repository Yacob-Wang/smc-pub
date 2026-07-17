# 4.5 Region Space 的角色

> **本节回答一个根本问题**：CC GC 在 Region Space 上是怎么工作的？Region 状态机如何与 CC GC 协作？
>
> **答案**：**Region 是 CC GC 的物理基础**——每个 Region 可以独立管理，CC GC 按 Region 复制活对象。
>
> **理解本节，就理解了 CC GC 为什么无碎片化** —— Region 整体回收。

---

## 一、Region Space 的定义

### 4.5.1 Region Space 的引入

ART 8.0+ 用 **Region Space** 替代 RosAlloc，成为 CC GC 的物理基础：

| 维度 | RosAlloc（CMS） | Region Space（CC GC） |
|:---|:---|:---|
| **空间划分** | 36 个 size class | 多个固定大小 Region（256 KB） |
| **分配方式** | Run-of-Slots + TLAB | Bump Pointer + Region TLAB |
| **回收方式** | Sweep slot | Region 整体回收 |
| **碎片化** | 高（分桶不合并） | **无**（整体回收） |

### 4.5.2 Region 的物理布局

```
┌─────────────────────────────────────────────────────┐
│            Java Heap (default 256 MB)                │
│  ┌───────────────────────────────────────────────┐  │
│  │           Region Space                         │  │
│  │                                                │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐          │  │
│  │  │Region 0 │ │Region 1 │ │Region 2 │ ...      │  │
│  │  │256 KB   │ │256 KB   │ │256 KB   │          │  │
│  │  │(Free)   │ │(Alloc)  │ │(Large)  │          │  │
│  │  └─────────┘ └─────────┘ └─────────┘          │  │
│  └───────────────────────────────────────────────┘  │
│                                                        │
│  ┌──────────────────────────┐                         │
│  │  Large Object Space (LOS)│                         │
│  │  大对象（≥ 12 KB）       │                         │
│  └──────────────────────────┘                         │
└─────────────────────────────────────────────────────┘
```

### 4.5.3 Region 大小配置

```cpp
// art/runtime/gc/space/region_space.h
static constexpr size_t kRegionSize = 256 * KB;  // 默认 256 KB

// 可通过 system property 调整：
// dalvik.vm.heap.region.size = 256k / 512k / 1m / 2m / 4m
```

---

## 二、Region 状态机

### 4.5.4 Region 状态枚举

```cpp
// art/runtime/gc/space/region_space.h
enum RegionState : uint8_t {
    kRegionStateFree,           // 空闲
    kRegionStateAlloc,          // 正在分配
    kRegionStateLarge,          // 大对象
    kRegionStateLargeTail,      // 大对象剩余
    kRegionStateNonMoving,      // 永不移动
    kRegionStateLast,           // 哨兵
};
```

### 4.5.5 Region 状态转换图

```
                        ┌────────────┐
                        │   Free     │ ← 初始状态
                        └──────┬─────┘
                               │ Alloc
                               ▼
                        ┌────────────┐
              ┌─────────│   Alloc    │─────────┐
              │         │ (TLAB)     │         │
              │ TLAB 满 └────────────┘ GC 复制  │ 大对象
              ▼                                  ▼
        ┌────────────┐                    ┌────────────┐
        │   Full     │                    │   Large    │
        │ 等待 GC    │                    │ (不可移动) │
        └────────────┘                    └────────────┘
              │                                  │
              │ GC 标记                          │ 大对象剩余
              ▼                                  ▼
        ┌────────────┐                    ┌────────────┐
        │   Free     │                    │ LargeTail  │
        │ (回收)     │                    │ (剩余)     │
        └────────────┘                    └────────────┘
```

### 4.5.6 Region 状态详细说明

| 状态 | 含义 | 分配器 | GC 参与 |
|:---|:---|:---|:---|
| **Free** | 空闲 Region，未分配 | — | 是 |
| **Alloc** | 正在分配（TLAB 活跃） | bump pointer | 是 |
| **Large** | 大对象占用的 Region | — | 是（不复制） |
| **LargeTail** | 大对象的剩余 Region | — | 是（不复制） |
| **NonMoving** | 永不移动的对象 | bump pointer | 否 |

---

## 三、Region 在 CC GC 中的工作流

### 4.5.7 CC GC 在 Region 上的分配

```cpp
// art/runtime/gc/space/region_space.cc 的 RegionSpace::Alloc
mirror::Object* RegionSpace::Alloc(Thread* self, size_t num_bytes, ...) {
    // 1. TLAB 快速路径
    if (HasSpace(self->tlab_, num_bytes)) {
        return BumpPointer(self, num_bytes);
    }
    
    // 2. TLAB 用完 → 申请新 Region 作为 TLAB
    Region* new_region = AllocNewRegionInToSpace(self);
    if (new_region == nullptr) {
        return nullptr;  // 没有空闲 Region
    }
    
    // 3. 把整个 Region 设置为 TLAB
    SetTLAB(self, new_region);
    
    // 4. 在新 TLAB 分配
    return BumpPointer(self, num_bytes);
}
```

### 4.5.8 CC GC 在 Region 上的复制

```cpp
// art/runtime/gc/collector/concurrent_copying.cc
mirror::Object* ConcurrentCopying::CopyObject(mirror::Object* obj) {
    // 1. 在 to-space 分配新对象
    size_t obj_size = obj->SizeOf();
    mirror::Object* new_obj = to_space_->Alloc(obj_size);
    
    // 2. 复制对象内容
    memcpy(new_obj, obj, obj_size);
    
    // 3. 设置 forwarding address
    obj->SetForwardingAddress(new_obj);
    
    return new_obj;
}
```

### 4.5.9 Region 整体回收

```cpp
// art/runtime/gc/collector/concurrent_copying.cc 的 ReclaimPhase
void ConcurrentCopying::ReclaimPhase() {
    // 1. 切换 from/to-space
    SwapSemiSpaces();
    
    // 2. 把 from-space 的所有 Region 加入 Region Pool
    for (Region* region : from_space_->GetRegions()) {
        region->state_ = kRegionStateFree;
        region_pool_->free_regions_.push_back(region);
    }
    
    // 3. from-space 整个标记为可用
    //    无需 Sweep，无需逐对象回收
    //    → 整块释放
}
```

**关键**：整个 Region 一次性回收，**无碎片化**！

---

## 四、Region 的数据结构

### 4.5.10 Region 类定义

```cpp
// art/runtime/gc/space/region_space.h 的 Region 类
class Region {
 public:
    // Region 状态
    RegionState state_;
    
    // Region 内存范围
    uint8_t* Begin();     // Region 起始地址
    uint8_t* End();       // Region 结束地址
    size_t Size();        // Region 大小（256 KB）
    
    // TLAB 相关
    uint8_t* top_;         // bump pointer
    size_t live_bytes_;    // 存活字节数（用于 GC 决策）
    
    // Region 在 Region Space 中的索引
    size_t idx_;
};
```

### 4.5.11 RegionSpace 类定义

```cpp
// art/runtime/gc/space/region_space.h 的 RegionSpace 类
class RegionSpace : public ContinuousSpace {
 public:
    // 所有 Region 数组
    std::vector<Region> regions_;
    
    // 空闲 Region 链表
    std::vector<Region*> free_regions_;
    
    // 分配函数
    mirror::Object* Alloc(Thread* self, size_t num_bytes, ...);
    mirror::Object* AllocLarge(Thread* self, size_t num_bytes, ...);
    
    // GC 相关
    Region* AllocRegion();   // 申请新 Region
    void FreeRegion(Region* region);  // 释放 Region
};
```

### 4.5.12 Region Pool 的管理

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

---

## 五、Region 与 GC 的协同

### 4.5.13 Region 的 Live Bytes 追踪

每个 Region 维护 `live_bytes_`（存活字节数）：

```cpp
// CC GC 复制对象时更新 live_bytes
void CopyObjectToRegion(Region* region, mirror::Object* obj) {
    // 1. 在 Region 中分配
    uint8_t* new_addr = region->top_;
    region->top_ += obj->SizeOf();
    
    // 2. 更新 live_bytes
    region->live_bytes_ += obj->SizeOf();
    
    // 3. 复制对象
    memcpy(new_addr, obj, obj->SizeOf());
}
```

### 4.5.14 Region 的 GC 决策依据

CC GC 用 `live_bytes_` 决定 GC 策略：

| live_bytes_ 状态 | GC 决策 |
|:---|:---|
| live_bytes_ = 0 | Region 完全空闲，直接回收 |
| live_bytes_ < 50% | Region 内有大量空洞，需要 GC |
| live_bytes_ = 100% | Region 满，下次 GC 必须复制活对象 |

### 4.5.15 Region 的并发安全

```cpp
// Region Pool 的多线程安全
Region* RegionSpace::AllocateRegion(Thread* self) {
    MutexLock lock(region_lock_);  // 全局锁
    
    if (!free_regions_.empty()) {
        Region* region = free_regions_.back();
        free_regions_.pop_back();
        return region;
    }
    
    // ...
}

// ART 14+ 用 CAS 优化
Region* RegionSpace::AllocateRegionCAS(Thread* self) {
    while (true) {
        if (free_regions_.empty()) break;
        
        Region* region = free_regions_.back();
        if (CAS(&free_regions_, region, /* next */)) {
            return region;
        }
        // CAS 失败 → 重试
    }
}
```

---

## 六、Region 与 LOS 的协作

### 4.5.16 Region Space vs LOS

```cpp
// 大对象（≥ 12 KB）走 LOS
mirror::Object* Heap::AllocObject(Thread* self, size_t byte_count, ...) {
    if (byte_count >= kLargeObjectThreshold) {
        return large_object_space_->Alloc(self, byte_count, ...);
    }
    return region_space_->Alloc(self, byte_count, ...);
}
```

### 4.5.17 LOS 在 CC GC 中的特殊性

- LOS 对象 **不可移动**（CC GC 不复制 LOS）
- LOS 标记-清除，**仍然碎片化**
- 大 Bitmap / byte[] 仍需 recycle / inBitmap

### 4.5.18 Region Space 的内存布局

```
Region Space 内存布局（256 MB 默认）：
┌────────────────────────────────────┐
│  ┌─────────┬─────────┬─────...───┐│
│  │Region 0 │Region 1 │Region N-1 ││
│  │(256 KB) │(256 KB) │(256 KB)   ││
│  └─────────┴─────────┴─────...───┘│
│                                    │
│  Region 数量：256MB / 256KB = 1024 │
└────────────────────────────────────┘
```

---

## 七、Region 的工程影响

### 4.5.19 Region 大小的影响

| Region Size | 优点 | 缺点 |
|:---|:---|:---|
| **256 KB** | 分配灵活 | Region 数量多，状态机开销大 |
| **1 MB** | 平衡 | 默认值（部分设备） |
| **4 MB** | Region 数量少 | 内部碎片多 |

### 4.5.20 Region 状态机的开销

```cpp
// 每个对象的状态都在 Region 中追踪
// Region 状态机开销 = O(Region 数量) × O(每 Region 状态转换)

// 1024 个 Region × 平均 10 次状态转换 = 10240 次
// 在 Copying 阶段持续发生 → 总开销 ~100ms
```

### 4.5.21 Region 的调优策略

```bash
# 调大 Region Size（减少状态机开销）
adb shell setprop dalvik.vm.heap.region.size 1m

# 调小 Region Size（增加分配灵活性）
adb shell setprop dalvik.vm.heap.region.size 128k
```

---

## 八、本节小结

1. **Region 是 CC GC 的物理基础**——每个 Region 独立管理
2. **Region 状态机**：Free / Alloc / Large / LargeTail / NonMoving
3. **CC GC 按 Region 复制活对象**：Copying 阶段按 Region 处理
4. **Region 整体回收无碎片化**：Reclaim 阶段整块释放
5. **Region 大小可调**：影响分配灵活性与状态机开销

→ **理解 Region Space，就理解了 CC GC 为什么无碎片化**。

---

## 跨节引用

**本节被以下章节引用**：
- [4.6 Thread Roots 与栈扫描](./06-Thread-Roots栈扫描.md) —— GC Root 在 Region 上的处理
- 05 篇 GenCC —— Young/Old Gen 在 Region 上的布局
- [02 篇 2.5 Region-based](../02-Heap与分配器/05-Region-based分配器.md) —— Region 分配器详解

**本节引用**：
- [4.1 核心思想](./01-CC核心思想.md) —— Region 是 CC 的物理基础
- [4.2 3 阶段详解](./02-3阶段详解.md) —— Region 在 Copying/Reclaim 阶段的应用
