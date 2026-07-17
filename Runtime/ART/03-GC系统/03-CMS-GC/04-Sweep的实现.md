# 3.4 Sweep 的实现：Bitmap 标记 + 空闲链表

> **本节回答一个根本问题**：CMS 的 Concurrent Sweep 阶段是怎么清除死对象的？Free List 是怎么组织的？
>
> **答案**：用 **Mark Bitmap 标记 + RosAlloc Free List 回收** —— 遍历 Run 内所有 slot，未标记的加入 Free List。
>
> **理解本节，就理解了"为什么 CMS 不压缩会碎片化"** —— Free List 的组织方式决定碎片化程度。

---

## 一、Sweep 阶段总览

### 3.4.1 Sweep 的本质

**Sweep** 阶段把 **未标记的对象** 标记为可回收的 **Free List slot**——业务线程下次分配时可以复用。

```
Sweep 前：
  ┌──────────────────────────────────────────────┐
  │  Slot 0 (marked=1, 存活)                     │
  │  Slot 1 (marked=0, 死亡) ← Sweep 目标        │
  │  Slot 2 (marked=1, 存活)                     │
  │  Slot 3 (marked=0, 死亡) ← Sweep 目标        │
  │  Slot 4 (marked=1, 存活)                     │
  └──────────────────────────────────────────────┘

Sweep 后：
  ┌──────────────────────────────────────────────┐
  │  Slot 0 (marked=1)                           │
  │  Slot 1 (marked=0, free list head)           │
  │  Slot 2 (marked=1)                           │
  │  Slot 3 (marked=0, free list -> Slot 1)      │
  │  Slot 4 (marked=1)                           │
  └──────────────────────────────────────────────┘

Free List: Slot 3 → Slot 1 → nullptr
```

### 3.4.2 Sweep 的两步操作

```cpp
// art/runtime/gc/collector/mark_sweep.cc 的 SweepRun
void MarkSweep::SweepRun(Run* run) {
    for (size_t i = 0; i < run->num_slots_; i++) {
        void* slot = run->slots_[i];
        
        if (mark_bitmap_->Test(slot)) {
            // 1. 存活对象：重置 mark bit（下一轮 GC 用）
            mark_bitmap_->Clear(slot);
        } else {
            // 2. 死亡对象：加入 free list
            run->free_list_.Push(slot);
        }
    }
}
```

---

## 二、Mark Bitmap 详解

### 3.4.3 Mark Bitmap 的定义

**Mark Bitmap** 是 ART CMS GC 的核心数据结构 —— 每个对象对应 1 bit，记录是否被标记。

```cpp
// art/runtime/gc/collector/mark_sweep.h 的 MarkBitmap 类
class MarkBitmap {
 public:
    // 1 = 标记（存活）
    // 0 = 未标记（死亡）
    
    bool Set(const mirror::Object* obj) {
        return Set(reinterpret_cast<uintptr_t>(obj));
    }
    
    bool Test(const mirror::Object* obj) {
        return Test(reinterpret_cast<uintptr_t>(obj));
    }
    
    void Clear(const mirror::Object* obj) {
        Clear(reinterpret_cast<uintptr_t>(obj));
    }
    
    // 遍历所有 bit
    void VisitMarkedRange(uintptr_t begin, uintptr_t end, Visitor* visitor);
    
 private:
    // bitmap 数组
    std::unique_ptr<uint8_t[]> bitmap_;
    uintptr_t base_addr_;       // Heap 起始地址
    size_t bitmap_size_;        // bitmap 大小
};
```

### 3.4.4 Mark Bitmap 的内存布局

```
Heap:     [  Obj0  ][  Obj1  ][  Obj2  ][  Obj3  ][  Obj4  ]...
Mark:     [ 0x00  ][ 0x80  ][ 0xC0  ][ 0x80  ][ 0xC0  ]...
            ↓         ↓         ↓         ↓         ↓
            0 0 0 0  1 0 0 0  1 1 0 0  1 0 0 0  1 1 0 0
          (全白)   (黑Obj1) (黑白Obj2) (黑Obj3) (黑白Obj4)

每个字节对应 8 个对象
```

### 3.4.5 Mark Bitmap 的内存开销

| Heap 大小 | Bitmap 大小 |
|:---|:---|
| 64 MB | 8 MB |
| 256 MB | 32 MB |
| 512 MB | 64 MB |

→ **bitmap 占 Heap 的 1/8**，可接受。

### 3.4.6 Mark Bitmap 的线程安全

CMS 是多线程并发标记，Mark Bitmap 必须线程安全：

```cpp
// 并发标记：CAS 设置 bit
bool MarkBitmap::Set(uintptr_t addr) {
    size_t index = (addr - base_addr_) / kAlignment;
    size_t byte_offset = index / 8;
    uint8_t mask = 1u << (index % 8);
    
    // CAS 设置 bit（并发安全）
    uint8_t old = bitmap_[byte_offset];
    while ((old & mask) == 0) {
        if (CAS(&bitmap_[byte_offset], old, old | mask)) {
            return true;  // 第一次标记成功
        }
        old = bitmap_[byte_offset];
    }
    return false;  // 已被标记
}
```

---

## 三、Free List 详解

### 3.4.7 Free List 的定义

**Free List**（空闲链表）记录 Run 内所有空闲 slot 的位置。

```cpp
// RosAlloc 的 Run 类
class Run {
    mirror::Object** slots_;       // slot 数组（按顺序存储对象指针）
    size_t num_slots_;             // slot 总数
    uint32_t free_list_index_;     // 下一个空闲 slot 的索引
    std::vector<void*> free_list_; // 显式空闲链表
};
```

### 3.4.8 Free List 的组织方式

CMS 用 **索引式 Free List**（不是传统的指针链表）：

```
Run (16B slots, 256 slots):
  slots_: [0][1][2][3][4]...[255]
  
free_list_index_ = 5  // 下一个空闲 slot 是 slot[5]

分配 slot:
  → 返回 slots_[5]
  → free_list_index_++ = 6

回收 slot:
  → slots_[3] 加入 free_list_
  → 显式空闲链表
```

**优势**：
- 顺序分配，连续内存访问
- 缓存友好
- 无碎片化（slot 内连续）

### 3.4.9 Free List 的分配路径

```cpp
// RosAlloc 的分配
void* RosAlloc::AllocFromRun(Run* run, size_t num_bytes) {
    // 1. 优先从索引分配（快速）
    if (run->free_list_index_ < run->num_slots_) {
        return run->slots_[run->free_list_index_++];
    }
    
    // 2. 索引分配完了，从显式 free list 分配
    if (!run->free_list_.empty()) {
        void* slot = run->free_list_.back();
        run->free_list_.pop_back();
        return slot;
    }
    
    // 3. Run 用完
    return nullptr;
}
```

### 3.4.10 Free List 的回收路径

```cpp
// CMS Sweep 时的回收
void MarkSweep::SweepRun(Run* run) {
    for (size_t i = 0; i < run->num_slots_; i++) {
        void* slot = run->slots_[i];
        
        if (mark_bitmap_->Test(slot)) {
            // 存活：重置 mark bit
            mark_bitmap_->Clear(slot);
        } else {
            // 死亡：加入 free list
            run->free_list_.PushBack(slot);
        }
    }
    
    // 重置索引（让所有 slot 重新可用）
    run->free_list_index_ = 0;
}
```

### 3.4.11 Free List 的碎片化分析

**问题**：Free List 组织的 slot 大小固定（size class），但业务对象大小多样。

```
Run A (16B): 100% 满
Run B (32B): 50% 满
Run C (64B): 30% 满

需要分配 32B 对象 → Run B 有空闲
需要分配 64B 对象 → Run C 有空闲
需要分配 100B 对象 → 没有合适的 Run → 申请新 Run 或 OOM
```

→ **Free List 碎片化的根源**：不同 size class 的 Run 不能跨桶使用。

---

## 四、LOS Sweep 详解

### 3.4.12 LOS Sweep 的特殊性

LOS（大对象空间）的 Sweep 与 Allocation Space 不同：

```cpp
// art/runtime/gc/collector/mark_sweep.cc 的 SweepLargeObjects
void MarkSweep::SweepLargeObjects() {
    // 遍历 LOS 中所有对象
    for (LargeObject* obj : large_object_space_->GetObjects()) {
        if (!mark_bitmap_->Test(obj)) {
            // 死亡 → 释放
            large_object_space_->Free(obj);
            // ❌ LOS 不压缩 → 留下空洞
        } else {
            // 存活
            mark_bitmap_->Clear(obj);
        }
    }
}
```

### 3.4.13 LOS 碎片化的具体表现

```
LOS 初始状态：
  [4 MB Bitmap] [8 MB Bitmap] [4 MB Bitmap]

CMS GC 后（中间 Bitmap 被回收）：
  [4 MB alive] [FREE 8 MB] [4 MB alive]
              ↑ 外碎片 8 MB

新分配请求：5 MB Bitmap
  → LOS 没有连续 5 MB
  → 即使总空闲 8 MB，仍分配失败
  → OOM
```

### 3.4.14 LOS 碎片化的解决方案

**方案 1：及时 recycle() Bitmap**（最佳实践）
```java
// 业务代码
public void removeBitmap(Bitmap bitmap) {
    if (bitmap != null && !bitmap.isRecycled()) {
        bitmap.recycle();  // 立即释放 native 像素
    }
}
```

**方案 2：使用 inBitmap 复用**
```java
// 复用 Bitmap，避免分配新 Bitmap
BitmapFactory.Options options = new BitmapFactory.Options();
options.inBitmap = reusableBitmap;  // 复用已有 Bitmap
Bitmap bitmap = BitmapFactory.decodeFile(path, options);
```

**方案 3：分块大 Bitmap**
```java
// 避免单个大 Bitmap，分成多个小块
Bitmap[] tiles = new Bitmap[16];
for (int i = 0; i < 16; i++) {
    tiles[i] = Bitmap.createBitmap(256, 256, Bitmap.Config.ARGB_8888);
}
```

**方案 4：ART 14+ 的 LOS Compaction**（实验性）
- 内核态的 LOS 压缩
- 移动存活对象，合并空洞

---

## 五、Alloc-During-Sweep 处理

### 3.4.15 Alloc-During-Sweep 的定义

**Alloc-During-Sweep**（ADS）= 业务线程在 Sweep 阶段继续分配对象。

```
时间线：
T1: CMS 开始 Concurrent Sweep
T2: 业务线程 new Object() → 触发分配
T3: 业务线程需要从 Free List 拿 slot
    → 但部分 Run 还没 Sweep
    → 那些 Run 的 Free List 还没建立
```

### 3.4.16 ART 处理 ADS 的策略

```cpp
// 业务线程 new Object() 时的分配路径
void* RosAlloc::Alloc(Thread* thread, size_t num_bytes) {
    // 1. 从当前活跃 Run 分配
    Run* current_run = thread->current_run_;
    if (current_run != nullptr && current_run->HasSpace()) {
        return current_run->AllocSlot(num_bytes);
    }
    
    // 2. 找一个已 Sweep 的 Run
    Run* swept_run = FindSweptRun(num_bytes);
    if (swept_run != nullptr) {
        thread->current_run_ = swept_run;
        return swept_run->AllocSlot(num_bytes);
    }
    
    // 3. 没有已 Sweep 的 Run → 慢速路径
    //    触发 GC 或申请新 Run
    return SlowPath(thread, num_bytes);
}
```

### 3.4.17 Sweep 的增量策略

CMS Sweep 不是一次完成所有 Run，而是 **增量 Sweep**：

```cpp
// CMS Sweep 的增量调度
void MarkSweep::ConcurrentSweepPhase() {
    while (!AllRunsSwept()) {
        // 1. Sweep 一个 Run
        Run* run = GetNextUnsweptRun();
        SweepRun(run);
        
        // 2. 让业务线程跑一段时间
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
}
```

**优势**：
- 业务线程有机会从已 Sweep 的 Run 分配
- Sweep 不阻塞业务线程
- 平滑分配延迟

### 3.4.18 ADS 的边界问题

**问题 1：野指针**

```
Sweep 把 Slot A 加入 free list
业务线程拿到 Slot A 写入新对象
但其他对象还引用着旧 Slot A 的对象
→ 旧对象被覆盖，新对象类型不同
→ 业务线程访问旧引用 → 类型错误
```

**ART 的处理**：Sweep 不立即复用 slot，而是延迟一轮 GC。

**问题 2：并发修改**

```
Sweep 阶段读 Mark Bitmap
业务线程修改对象引用（可能触发写屏障）
```

**ART 的处理**：Sweep 阶段不修改 Mark Bitmap，只读。

---

## 六、Sweep 的工程影响

### 3.4.19 Sweep 的耗时分析

| Sweep 范围 | 耗时 |
|:---|:---|
| Allocation Space（256 MB） | ~100ms |
| LOS（20 MB） | ~5ms |
| 全部 | ~105ms |

→ Sweep 耗时主要在 Allocation Space 的全 Run 遍历。

### 3.4.20 Sweep 的 CPU 影响

Sweep 占用单核 ~50% CPU 资源（业务线程并行时）。

**优化**：CMS 用后台线程做 Sweep，不占用业务线程 CPU。

### 3.4.21 Sweep 与 Sweep 之间的间隔

```
一次 CMS GC:
  Initial Mark (5ms STW)
  + Concurrent Mark (100ms 并发)
  + Remark (50ms STW)
  + Concurrent Sweep (100ms 并发)
  = 总计 ~255ms

两次 CMS GC 间隔：
  由 Java 堆使用率决定
  默认 GC 触发阈值 = heapgrowthlimit * 0.75
```

---

## 七、Sweep 的源码索引

### 3.4.22 核心源码路径

```
art/runtime/gc/collector/mark_sweep.h           # MarkSweep 类
art/runtime/gc/collector/mark_sweep.cc          # Sweep 实现
art/runtime/gc/allocator/rosalloc.h             # RosAlloc（Free List）
art/runtime/gc/allocator/rosalloc.cc            # RosAlloc 实现
art/runtime/gc/space/large_object_space.h       # LOS
art/runtime/gc/space/large_object_space.cc      # LOS Sweep
art/runtime/gc/space/malloc_space.h             # MallocSpace
art/runtime/gc/space/malloc_space.cc            # MallocSpace Sweep
```

### 3.4.23 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `MarkSweep::SweepPhase` | `mark_sweep.cc` | Sweep 阶段主函数 |
| `MarkSweep::SweepRun` | `mark_sweep.cc` | Sweep 单个 Run |
| `MarkSweep::SweepLargeObjects` | `mark_sweep.cc` | LOS Sweep |
| `MarkSweep::MarkBitmap` | `mark_sweep.h` | Mark Bitmap 类 |
| `RosAlloc::AllocFromRun` | `rosalloc.cc` | Run 内分配 |
| `LargeObjectSpace::Free` | `large_object_space.cc` | LOS 释放 |

---

## 八、本节小结

1. **Sweep = 遍历 Mark Bitmap + 回收未标记对象到 Free List**
2. **Mark Bitmap 占 Heap 的 1/8**，线程安全（CAS）
3. **Free List 用索引 + 显式链表混合组织**
4. **LOS Sweep 不压缩**，导致外碎片
5. **Alloc-During-Sweep 由 ART 自动处理**（增量 Sweep + 延迟复用）

→ **理解 Sweep，就理解了"为什么 CMS 时代要特别注意 LOS 碎片化"**。

---

## 跨节引用

**本节被以下章节引用**：
- [3.5 STW 时间分析](./05-STW时间分析.md) —— Sweep 耗时影响 GC 总耗时
- [3.6 内存碎片化](./06-内存碎片化.md) —— Sweep 后碎片化的根因
- [3.7 CMS 时代的 OOM 模式](./07-CMS时代的OOM模式.md) —— LOS 碎片化导致 OOM

**本节引用**：
- [01 篇 1.3 写屏障机制](../01-基础理论/03-写屏障机制.md) —— Sweep 与写屏障协同
- [02 篇 2.4 RosAlloc](../02-Heap与分配器/04-RosAlloc分配器.md) —— Free List 组织
- [02 篇 2.7 慢速路径与碎片化](../02-Heap与分配器/07-慢速路径与碎片化.md) —— Sweep 后的碎片化
- [3.2 标记-清除的 4 阶段](./02-标记-清除的4阶段.md) —— Sweep 在 4 阶段中的位置
