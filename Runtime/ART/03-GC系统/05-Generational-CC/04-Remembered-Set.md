# 5.4 Remembered Set 的 ART 实现

> **本节回答一个根本问题**：除了 Card Table，ART GenCC 还用什么数据结构记录跨代引用？Region 级别的 Remembered Set 是怎么实现的？
>
> **答案**：**Region 级别的 RSet + Card Table** 双重机制，ART GenCC 同时使用两者优化 Minor GC 扫描。
>
> **理解本节，就理解了 ART GenCC 对分代假说的工程优化**。

---

## 一、Remembered Set 的定义

### 5.4.1 RSet 的作用

**Remembered Set（RSet）** = 记录 Region 被哪些其他 Region 引用的数据结构。

```
Region R0（Old Gen）:
  inbound_refs_ = [R5, R12, R23]  ← R5, R12, R23 中有对象引用了 R0 中的对象

含义：
  Minor GC 扫描 R0 时，只需扫描 R5, R12, R23 的对象
  不需要扫描整个堆
```

### 5.4.2 Card Table vs RSet

| 维度 | Card Table | RSet |
|:---|:---|:---|
| **粒度** | 512 byte（粗粒度） | Region 级别（细粒度） |
| **精确度** | 整张 card dirty（可能浪费扫描） | 只标记实际引用的 Region |
| **实现** | 字节数组 | HashMap / 数组 |
| **维护开销** | 低 | 中（每次跨 Region 引用都更新） |
| **扫描开销** | 512 byte/张 card | 仅 inbound_refs_ 中的 Region |

### 5.4.3 ART GenCC 的双重机制

```
ART GenCC 同时使用：
  1. Card Table（粗粒度）→ 1 byte / 512 byte
  2. Region RSet（细粒度）→ 记录 Region 间的引用关系

Minor GC 流程：
  1. 扫描 Card Table 找 dirty card
  2. 扫描每个 Region 的 RSet
  3. 结合两者数据确定需要扫描的对象
```

---

## 二、Region RSet 的实现

### 5.4.4 Region 类的 RSet 字段

```cpp
// art/runtime/gc/space/region_space.h 的 Region 类
class Region {
public:
    // Region 的 Remembered Set
    // 记录这个 Region 被哪些其他 Region 引用
    std::vector<Region*> inbound_refs_;
    
    // 添加 inbound 引用
    void AddInboundRef(Region* from_region) {
        inbound_refs_.push_back(from_region);
    }
    
    // Minor GC 时只扫描 inbound_refs_ 里的 Region
    void ScanInboundRefs() {
        for (Region* region : inbound_refs_) {
            region->ScanReferences();
        }
    }
};
```

### 5.4.5 RSet 的更新时机

```cpp
// PostWriteBarrier 中维护 RSet
void PostWriteBarrier(void* field_addr, mirror::Object* new_value) {
    // 1. 计算 src 和 dst 的 Region
    Region* src_region = heap_->GetRegionOf(field_addr);
    Region* dst_region = heap_->GetRegionOf(new_value);
    
    // 2. 跨 Region 引用 → 更新 RSet
    if (src_region != dst_region) {
        // 3. 把 src_region 加入 dst_region 的 inbound_refs_
        dst_region->AddInboundRef(src_region);
    }
    
    // 4. 同时更新 Card Table
    CardTable::MarkCard(field_addr);
}
```

### 5.4.6 RSet 的存储开销

```
RSet 大小 = O(Region 数量) × O(inbound_refs_)

假设：
  - 1024 个 Region
  - 平均每个 Region 有 10 个 inbound_refs
  - 每个指针 8 byte

RSet 总开销 = 1024 × 10 × 8 = 80 KB

→ 可接受
```

---

## 三、RSet 在 Minor GC 中的应用

### 5.4.7 Minor GC 使用 RSet 的流程

```cpp
void ConcurrentCopying::MinorGc() {
    // 1. STW 暂停所有 mutator 线程
    SuspendAllThreads();
    
    // 2. 扫描 Young Gen 的所有 Root
    ScanYoungGenRoots();
    
    // 3. 遍历 Card Table（粗粒度）
    for (uint8_t* card : dirty_cards) {
        ScanCard(card);
    }
    
    // 4. 遍历 RSet（细粒度补充）
    for (Region* young_region : young_regions_) {
        for (Region* inbound_region : young_region->inbound_refs_) {
            inbound_region->ScanReferences();
        }
    }
    
    // 5. 标记 + 复制活对象
    // ...
    
    // 6. STW 结束
    ResumeAllThreads();
}
```

### 5.4.8 RSet vs Card Table 的协作

```
Card Table 提供：粗粒度的 dirty 信息
RSet 提供：细粒度的 inbound Region 信息

Minor GC 扫描顺序：
  1. 扫描 Card Table 中的 dirty card（512 byte 粒度）
  2. 扫描每个 Region 的 RSet（Region 粒度）
  3. 取并集作为扫描范围

→ 既不漏（Card Table 覆盖），也不冗余（RSet 精确）
```

---

## 四、RSet 的工程价值

### 5.4.9 RSet 的三大价值

**价值 1：减少 Minor GC 扫描范围**
- Card Table 已经减少到 ~1% 的 Old Gen
- RSet 进一步精确到具体 Region

**价值 2：支持更细粒度的 GC 策略**
- 单个 Region 可以独立 GC
- 进一步优化 Minor GC 性能

**价值 3：辅助 Major GC**
- Major GC 时，RSet 标记的 Region 优先扫描
- 减少全堆扫描的冗余

### 5.4.10 RSet 的代价

**代价 1：维护开销**
- 每次跨 Region 引用都更新 RSet
- 比 Card Table 维护更复杂

**代价 2：内存开销**
- 每个 Region 有 inbound_refs_ 数组
- 总开销 ~80 KB（256 MB 堆）

**代价 3：并发更新**
- 业务线程和 GC 线程同时更新 RSet
- 需要加锁（影响性能）

### 5.4.11 ART 的 RSet 优化

```cpp
// 优化 1：批量更新
void BatchUpdateRSet(Region* dst, std::vector<Region*>& src_list) {
    // 一次性更新多个 inbound_refs
    MutexLock lock(rset_lock_);
    for (Region* src : src_list) {
        if (std::find(dst->inbound_refs_.begin(), 
                      dst->inbound_refs_.end(), src) == dst->inbound_refs_.end()) {
            dst->inbound_refs_.push_back(src);
        }
    }
}

// 优化 2：异步更新
void AsyncUpdateRSet(Region* dst, Region* src) {
    // 异步加入 RSet 更新队列
    rset_update_queue_.Push({dst, src});
    // 后台线程批量处理
}

// 优化 3：压缩存储
// 用 bitset 替代 vector，节省内存
class Region {
    std::bitset<1024> inbound_refs_bitset_;  // 1024 个 Region 用 128 byte 表示
};
```

---

## 五、ART vs G1 的 RSet 对比

### 5.4.12 G1 GC 的 RSet（Java HotSpot）

```cpp
// G1 的 RSet 是 Hash Table，key 是 Card，value 是 Region
class G1RSet {
public:
    // 每个 Region 一个 RSet
    std::unordered_map<Card*, std::vector<Region*>> rset_;
};
```

**G1 RSet 的特点**：
- 精确度高（按 Card）
- 维护开销大
- 支持 Remembered Set Hashing

### 5.4.13 ART GenCC 的 RSet

```cpp
// ART 的 RSet 是简单的 vector
class Region {
    std::vector<Region*> inbound_refs_;
};
```

**ART RSet 的特点**：
- 实现简单（vector）
- 维护开销小
- 与 Card Table 互补

### 5.4.14 设计哲学对比

| 维度 | G1 GC | ART GenCC |
|:---|:---|:---|
| **RSet 精确度** | 高（按 Card） | 中（按 Region） |
| **RSet 开销** | 高 | 低 |
| **配合 Card Table** | 不使用 | **使用**（双重机制） |
| **适用场景** | 服务端大堆 | 移动端中小堆 |

→ **ART GenCC 用"Card Table + Region RSet"双重机制，比 G1 单 RSet 更适合移动端**。

---

## 六、RSet 的工程影响

### 5.4.15 业务代码的影响

**原则 1：避免大量跨 Region 引用**

```java
// ✅ 好：同一 Region 的对象互相引用
public class RegionFriendlyData {
    private List<Item> items = new ArrayList<>();
    // items 和 item 通常在同一个 Region
}

// ❌ 不好：跨 Region 引用
public class CrossRegionData {
    private Map<String, Object> cache = new HashMap<>();
    // cache 在 Old Gen，value 在 Young Gen → 跨 Region 引用
}
```

**原则 2：批量操作优于细粒度操作**

```java
// ✅ 好：批量插入
public void batchInsert(List<Item> items) {
    for (Item item : items) {
        // 批量操作通常在同一个 Region
        map.put(item.getKey(), item);
    }
}

// ❌ 不好：频繁插入小数据
public void frequentInsert() {
    while (true) {
        Item item = new Item();
        map.put(item.getKey(), item);  // 每次都跨 Region
    }
}
```

### 5.4.16 监控 RSet

```bash
# 1. 看 RSet 大小
adb logcat -s "art" | grep "RSet"
# 输出示例：
# art : Region R0 inbound_refs: 5
# art : Region R1 inbound_refs: 12

# 2. 看 RSet 更新频率
adb logcat -s "art" | grep "RSet.*Update"
```

---

## 七、RSet 的源码索引

### 5.4.17 核心源码路径

```
art/runtime/gc/space/region_space.h        # Region 类（含 inbound_refs_）
art/runtime/gc/space/region_space.cc       # RSet 维护
art/runtime/gc/collector/concurrent_copying.h # Post-Write Barrier（含 RSet 更新）
art/runtime/gc/collector/concurrent_copying.cc # Minor GC（RSet 扫描）
```

### 5.4.18 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Region::AddInboundRef` | `region_space.cc` | 添加 inbound 引用 |
| `Region::ScanInboundRefs` | `region_space.cc` | 扫描 inbound 引用 |
| `PostWriteBarrier` | `concurrent_copying.cc` | 维护 RSet |
| `ConcurrentCopying::MinorGc` | `concurrent_copying.cc` | Minor GC 使用 RSet |

---

## 八、本节小结

1. **RSet = Region 级别的 Remembered Set**，记录 Region 被哪些其他 Region 引用
2. **ART GenCC 用 Card Table + RSet 双重机制**：Card Table 粗粒度 + RSet 细粒度
3. **RSet 减少 Minor GC 扫描范围**：与 Card Table 互补
4. **RSet 的代价**：维护开销 + 内存开销 + 并发更新
5. **业务代码**：避免大量跨 Region 引用

→ **理解 RSet，就理解了 ART GenCC 对分代假说的工程优化**。

---

## 跨节引用

**本节被以下章节引用**：
- [5.5 Minor/Major GC](./05-Minor-Major-GC.md) —— Minor GC 同时使用 Card Table 和 RSet
- 08 篇横切 —— GC × JNI 横切时的 RSet 维护

**本节引用**：
- [5.3 Card Table](./03-Card-Table基石.md) —— Card Table 是 RSet 的补充
- [5.2 Young/Old Gen 划分](./02-Young-Old划分.md) —— Region 物理布局
