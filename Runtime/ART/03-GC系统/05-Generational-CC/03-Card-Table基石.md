# 5.3 Card Table：分代 GC 的基石

> **本节回答一个根本问题**：Minor GC 不扫描 Old Gen，怎么找到 Old → Young 的跨代引用？
>
> **答案**：**Card Table** —— 用 1 byte / 512 byte 的内存粒度，记录 Old Gen 中的跨代引用。
>
> **理解本节，就理解了 Minor GC 只扫描 Young Gen 的"魔法"**。

---

## 一、Card Table 的定义

### 5.3.1 跨代引用的问题

```
Minor GC 扫描范围 = Young Gen（仅）
但 Old Gen 中的对象可能引用 Young Gen 中的对象

问题：
  Old Gen 中的对象 D 引用 Young Gen 中的对象 A
  → Minor GC 不扫描 D
  → A 被错误判定为不可达
  → 漏标
```

### 5.3.2 Card Table 的解决方案

```
Card Table 是一个字节数组：
  - 每 512 字节 Java Heap 对应 1 byte
  - 1 byte 表示这 512 字节是否有跨代引用
  - dirty = 1（有跨代引用）
  - clean = 0（无跨代引用）

Minor GC 流程：
  1. 扫描 Young Gen 的所有 Root
  2. 遍历 Card Table，找所有 dirty card
  3. 只扫描 dirty card 对应的 512 字节
  4. → 找到所有跨代引用
  5. → 不需要扫描整个 Old Gen
```

### 5.3.3 Card Table 的内存布局

```
Java Heap (256 MB):
┌────────────────────────────────────────────────┐
│  [512B] [512B] [512B] [512B] ... [512B]       │
│  1     2     3     4         N                │
└────────────────────────────────────────────────┘

Card Table:
┌────────────────────────────────────────────────┐
│  [1B]   [1B]   [1B]   [1B]   ... [1B]         │
│  card0  card1  card2  card3      cardN-1      │
└────────────────────────────────────────────────┘

Java Heap 大小 / Card Table 大小 = 512
```

### 5.3.4 Card Table 的内存开销

| Heap 大小 | Card Table 大小 |
|:---|:---|
| 64 MB | 128 KB |
| 256 MB | 512 KB |
| 512 MB | 1 MB |
| 1 GB | 2 MB |

→ **内存开销约 0.2%**，可接受。

---

## 二、Card Table 的实现

### 5.3.5 CardTable 类定义

```cpp
// art/runtime/gc/space/region_space.h 的 CardTable 类
class CardTable {
public:
    static constexpr size_t kCardSize = 512;  // 1 byte / 512 byte
    
    enum CardValue : uint8_t {
        kCardClean = 0,    // 干净（无跨代引用）
        kCardDirty = 0x70, // 脏（有跨代引用）
    };
    
    // 标记 card 为 dirty
    void MarkCard(const void* addr) {
        uint8_t* card = AddressToCard(addr);
        *card = kCardDirty;
    }
    
    // 检查 card 是否 dirty
    bool IsDirty(const void* addr) {
        return *AddressToCard(addr) == kCardDirty;
    }
    
    // addr → card 的映射
    uint8_t* AddressToCard(const void* addr) {
        uintptr_t offset = reinterpret_cast<uintptr_t>(addr) - base_addr_;
        return &card_table_[offset / kCardSize];
    }
    
private:
    std::unique_ptr<uint8_t[]> card_table_;
    uintptr_t base_addr_;
};
```

### 5.3.6 Card Table 的核心操作

| 操作 | 用途 | 时机 |
|:---|:---|:---|
| `MarkCard(addr)` | 标记 card 为 dirty | Post-Write Barrier 触发跨代引用 |
| `IsDirty(addr)` | 检查 card 是否 dirty | Minor GC 扫描 Card Table 时 |
| `Clear(addr)` | 清除 card 的 dirty 标记 | Minor GC 扫描完后 |

### 5.3.7 Card Table 的精确度问题

**粗粒度代价**：
- 1 byte / 512 byte → 每次脏卡扫描的"无辜开销"是 512 字节
- 大对象（> 512 字节）可能浪费大量扫描

**ART 14+ 的优化**：
- 细粒度卡表（256 byte / 128 byte）
- Hot Card 优化（高频脏卡提前扫描）

---

## 三、Post-Write Barrier 维护 Card Table

### 5.3.8 Post-Write Barrier 的实现

```cpp
// art/runtime/gc/collector/concurrent_copying.h 的 PostWriteBarrier
void PostWriteBarrier(void* field_addr, mirror::Object* new_value) {
    // 1. 计算 field_addr 所在的 card
    uint8_t* card = CardTable::AddressToCard(field_addr);
    
    // 2. 检查是否跨代引用
    SpaceType src_space = RegionSpace::GetSpaceTypeOf(field_addr);
    SpaceType dst_space = RegionSpace::GetSpaceTypeOf(new_value);
    
    // 3. 跨代时把 card 标记为 dirty
    if (src_space != dst_space && 
        (src_space == kSpaceTypeYoung || dst_space == kSpaceTypeYoung)) {
        *card = CardTable::kCardDirty;
    }
}
```

### 5.5.9 编译码中的 Post-Write Barrier

```asm
; AArch64 上 PostWriteBarrier 的机器码
; 入口：x0 = field_addr, x1 = new_value
post_write_barrier_entry:
    ; 1. 计算 field_addr 所在的 card
    ;    ART 用位运算：card_addr = field_addr & ~(kCardSize - 1)
    and x2, x0, #~(kCardSize - 1)    ; x2 = card_addr
    
    ; 2. 检查 new_value 是否在 Young Gen
    bl artIsInYoungGen
    cbz x0, .Lskip                    ; 如果不在，跳过
    
    ; 3. 把 card 标记为 dirty
    mov x3, #0x70
    strb w3, [x2]
    
.Lskip:
    ret
```

### 5.3.10 JIT 模式下的优化

```cpp
// 优化前
for (int i = 0; i < N; i++) {
    PostWriteBarrier(&arr[i], value);  // 每次循环都触发
    arr[i] = value;
}

// 优化后
bool is_young = IsInYoungGen(value);  // 循环外判断
for (int i = 0; i < N; i++) {
    if (is_young) {
        PostWriteBarrier(&arr[i], value);
    }
    arr[i] = value;
}
```

---

## 四、Minor GC 扫描 Card Table

### 5.3.11 Minor GC 的完整流程

```cpp
// art/runtime/gc/collector/concurrent_copying.cc 的 Minor GC
void ConcurrentCopying::MinorGc() {
    // 1. STW 暂停所有 mutator 线程
    SuspendAllThreads();
    
    // 2. 扫描 Young Gen 的所有 Root
    ScanYoungGenRoots();
    
    // 3. 遍历 Card Table，找所有 dirty card
    for (uint8_t* card = card_table_begin_; card < card_table_end_; card++) {
        if (*card == CardTable::kCardDirty) {
            // 4. 扫描这张 card 对应的 512 字节
            ScanCard(card);
            
            // 5. 清除 dirty 标记
            *card = CardTable::kCardClean;
        }
    }
    
    // 6. 恢复 mutator 线程
    ResumeAllThreads();
}
```

### 5.5.12 ScanCard 的实现

```cpp
void ScanCard(uint8_t* card) {
    // 1. 计算 card 对应的 512 字节范围
    void* region_start = (void*)((uintptr_t)card - card_table_base_ + heap_base_);
    void* region_end = (char*)region_start + kCardSize;
    
    // 2. 遍历范围内的所有对象
    for (mirror::Object* obj = (mirror::Object*)region_start; 
         obj < region_end; 
         obj = NextObject(obj)) {
        // 3. 遍历对象的字段，找跨代引用
        obj->VisitReferences([&](mirror::Object* ref) {
            if (ref != nullptr && IsInYoungGen(ref)) {
                // 4. 把 Young Gen 的对象染灰
                MarkObject(ref);
            }
        });
    }
}
```

### 5.5.13 性能对比

**场景**：Old Gen 256 MB，Young Gen 64 MB，1% 的 Old Gen 区域有跨代引用

| 方案 | 扫描范围 | STW 时间（相对值） |
|:---|:---|:---|
| **无卡表**（扫描整个 Old Gen） | 256 MB | 100% |
| **有卡表**（只扫描 dirty cards） | ~2.5 MB（1% × 256 MB） | ~1% |

→ **卡表让 Minor GC 扫描范围减少 99%**。

---

## 五、卡表的精度问题与优化

### 5.5.14 粗粒度代价

```
Dirty card 对应的 512 字节范围：

┌────────────────────────────────────────────────┐
│   Dirty Card                                  │
│   ┌──────────┬──────────┬──────────┬──────────┐│
│   │ 128 B    │ 128 B    │ 128 B    │ 128 B    ││
│   │ Card数据 │ Card数据 │ Card数据 │ Card数据 ││
│   └──────────┴──────────┴──────────┴──────────┘│
└────────────────────────────────────────────────┘

扫描 512 字节，找到所有跨代引用
```

**问题**：
- 1 byte / 512 byte → 每次脏卡扫描"无辜开销"是 512 字节
- 大对象（> 512 字节）浪费大量扫描
- 多个对象的多个引用集中在同一 card → 整张 card 扫描

### 5.5.15 ART 14+ 的细粒度卡表

```cpp
// art/runtime/gc/space/region_space.h 的 FineGrainedCardTable
class FineGrainedCardTable {
public:
    // 两级卡表：
    // - 第一级：1 byte / 8 KB（汇总）
    // - 第二级：1 byte / 1 KB（细粒度）
    
    void MarkCard(const void* addr) {
        uint8_t* coarse_card = CoarseAddressToCard(addr);
        uint8_t* fine_card = FineAddressToCard(addr);
        
        *fine_card = kCardDirty;
        *coarse_card = kCardDirty;  // 汇总标记
    }
};
```

### 5.5.16 ART 14+ 的 Hot Card 优化

**Hot Card 问题**：某些 card 被频繁标脏（如高并发线程）。

```cpp
// Hot Card 优化（ART 14+）
void PostWriteBarrier(void* field_addr, Object* new_value) {
    uint8_t* card = AddressToCard(field_addr);
    
    // 检查 card 是否被频繁标脏
    if (card_hotness_[card] > kHotCardThreshold) {
        // Hot Card：直接扫描，不等 Minor GC
        ScanCardImmediately(card);
    }
    
    *card = kCardDirty;
}
```

---

## 六、Card Table 的工程影响

### 5.5.17 Card Table 的开销

**内存开销**：约 0.2%（512 byte 粒度）
**Post-Write Barrier 开销**：每次跨代指针赋值 ~5ns
**Minor GC 扫描开销**：与 dirty card 数成正比

### 5.5.18 Card Table 优化的工程建议

**建议 1：减少跨代引用**

```java
// ✅ 好：减少 Old Gen 持有 Young Gen 对象
public class Cache {
    private final Map<String, WeakReference<Object>> cache = new HashMap<>();
    // 缓存中不持有强引用，cache 本身在 Old Gen，value 在 Young Gen
}

// ❌ 不好：Old Gen 持有大量 Young Gen 对象
public class Cache {
    private final Map<String, Object> cache = new HashMap<>();
    // cache 中所有对象都会"晋升"到 Old Gen 的 Card Table 视角
}
```

**建议 2：避免大量小对象的跨代引用**

```java
// ✅ 好：批量数据放在 Old Gen
public class DataStore {
    private final List<Data> data = new ArrayList<>();
    // data 一次性加载到 Old Gen
}

// ❌ 不好：大量小对象频繁跨代引用
public void process() {
    for (int i = 0; i < 10000; i++) {
        // 每次循环都创建临时对象 → 大量跨代引用
        Object temp = new Object();
    }
}
```

### 5.5.19 监控 Card Table

```bash
# 1. 看 dirty card 数量
adb logcat -s "art" | grep "Card"
# 输出示例：
# art : Dirty card count: 12345 / 524288 (2.3%)

# 2. 看 Post-Write Barrier 触发次数
adb logcat -s "art" | grep "WriteBarrier"
# 输出示例：
# art : WriteBarrier called 12345 times
```

---

## 七、Card Table 的源码索引

### 5.5.20 核心源码路径

```
art/runtime/gc/space/region_space.h        # RegionSpace（含 CardTable）
art/runtime/gc/space/region_space.cc       # CardTable 实现
art/runtime/gc/collector/concurrent_copying.h  # Post-Write Barrier
art/runtime/gc/collector/concurrent_copying.cc # Minor GC 扫描
art/runtime/arch/arm64/quick_entrypoints_arm64.S # AArch64 Post-Write Barrier 机器码
```

### 5.5.21 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `CardTable::MarkCard` | `region_space.cc` | 标记 card 为 dirty |
| `CardTable::IsDirty` | `region_space.cc` | 检查 card 是否 dirty |
| `PostWriteBarrier` | `concurrent_copying.cc` | Post-Write Barrier 入口 |
| `ConcurrentCopying::MinorGc` | `concurrent_copying.cc` | Minor GC 主函数 |
| `ConcurrentCopying::ScanCard` | `concurrent_copying.cc` | 扫描 dirty card |

### 5.5.22 关键常量

```cpp
// art/runtime/gc/space/region_space.h
static constexpr size_t kCardSize = 512;  // 1 byte / 512 byte

// Card 状态
enum CardValue : uint8_t {
    kCardClean = 0,
    kCardDirty = 0x70,
};
```

---

## 八、本节小结

1. **Card Table = 1 byte / 512 byte 粒度记录跨代引用**
2. **Post-Write Barrier 维护 Card Table**：每次跨代引用都更新
3. **Minor GC 扫描 Card Table**：只扫描 dirty card 对应的 512 字节
4. **精度问题 + 优化**：细粒度卡表（256/128 byte）+ Hot Card 优化
5. **业务建议**：减少跨代引用，避免大量小对象的跨代引用

→ **理解 Card Table，就理解了 Minor GC 只扫描 Young Gen 的"魔法"**。

---

## 跨节引用

**本节被以下章节引用**：
- [5.4 Remembered Set](./04-Remembered-Set.md) —— RSet 是 Card Table 的补充
- [5.5 Minor/Major GC](./05-Minor-Major-GC.md) —— Minor GC 扫描 Card Table
- [5.7 写屏障双重角色](./07-写屏障双重角色.md) —— Post-Write Barrier 维护 Card Table
- 08 篇横切 —— GC × JNI 横切时 Card Table 的维护

**本节引用**：
- [01 篇 1.5 卡表](../01-基础理论/05-记忆集与卡表.md) —— 卡表原理
- [5.2 Young/Old Gen 划分](./02-Young-Old划分.md) —— 两代 Region
- [01 篇 1.3 写屏障](../01-基础理论/03-写屏障机制.md) —— Post-Write Barrier
