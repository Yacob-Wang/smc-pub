# 5.2 Young Gen vs Old Gen 划分

> **本节回答一个根本问题**：GenCC 怎么把 Java 堆划分成 Young/Old 两代？Region 在两代中怎么分布？
>
> **答案**：**Region-based + 年龄阈值** —— Young Gen 多个小 Region，Old Gen 多个大 Region，对象通过年龄晋升。
>
> **理解本节，就理解了 GenCC 的物理布局** —— 是 Minor GC 只扫描 Young Gen 的基础。

---

## 一、Young/Old Gen 的 Region 划分

### 5.2.1 GenCC 的 Region 状态

```cpp
// art/runtime/gc/space/region_space.h
enum RegionState : uint8_t {
    kRegionStateFree,
    kRegionStateAlloc,
    kRegionStateLarge,
    kRegionStateLargeTail,
    kRegionStateNonMoving,
    kRegionStateYoungGen,    // Young Gen 专用
    kRegionStateOldGen,      // Old Gen 专用
};
```

### 5.2.2 Region 的物理布局

```
┌──────────────────────────────────────────────────────────────┐
│              Java Heap (256 MB 默认)                          │
│                                                              │
│  ┌────────────────────────────┬─────────────────────────┐  │
│  │      Young Gen (~25%)      │     Old Gen (~75%)      │  │
│  │         ~64 MB              │        ~192 MB          │  │
│  │                             │                         │  │
│  │  ┌────┐ ┌────┐ ┌────┐      │  ┌────┐ ┌────┐ ┌────┐  │  │
│  │  │R0  │ │R1  │ │R2  │ ...  │  │R N │ │RN+1│ │RN+2│  │  │
│  │  │Yng │ │Yng │ │Yng │      │  │Old │ │Old │ │Old │  │  │
│  │  └────┘ └────┘ └────┘      │  └────┘ └────┘ └────┘  │  │
│  └────────────────────────────┴─────────────────────────┘  │
│                                                              │
│  R0 ~ R(N-1): Young Gen Regions（~256 个）                  │
│  RN ~ R(M-1): Old Gen Regions（~768 个）                     │
└──────────────────────────────────────────────────────────────┘
```

### 5.2.3 Region 大小配置

```cpp
// art/runtime/gc/space/region_space.h
static constexpr size_t kRegionSize = 256 * KB;

// 默认配置
// Young Gen: ~64 MB / 256 KB = 256 个 Region
// Old Gen: ~192 MB / 256 KB = 768 个 Region
// 总计: ~1024 个 Region
```

---

## 二、Young Gen 的特性

### 5.2.4 Young Gen 的特点

| 特性 | 说明 |
|:---|:---|
| **空间占比** | ~25%（可动态调整） |
| **Region 数量** | ~256 个（256 MB 堆） |
| **分配方式** | bump pointer（TLAB） |
| **GC 策略** | Minor GC（高频） |
| **对象晋升** | 达到年龄阈值晋升 Old Gen |
| **碎片化** | 无（整体回收） |

### 5.2.5 Young Gen 的分配路径

```cpp
// art/runtime/gc/space/region_space.cc 的 RegionSpace::Alloc
mirror::Object* RegionSpace::AllocInYoungGen(Thread* self, size_t num_bytes, ...) {
    // 1. TLAB 快速路径
    if (HasSpace(self->tlab_, num_bytes)) {
        return BumpPointer(self, num_bytes);
    }
    
    // 2. TLAB 用完 → 从 Young Gen Region Pool 申请新 Region
    Region* new_region = AllocNewRegionFromYoungPool(self);
    if (new_region == nullptr) {
        return nullptr;
    }
    
    // 3. 把 Region 设置为 TLAB
    SetTLAB(self, new_region);
    
    // 4. 在新 TLAB 分配
    return BumpPointer(self, num_bytes);
}
```

### 5.2.6 Young Gen 的对象类型

**Young Gen 中的对象**：
- 临时变量（方法栈中的对象）
- 局部数据（for 循环中的对象）
- 临时缓存（HashMap 临时 entries）
- 短生命周期对象

**典型场景**：
```java
public void processData(List<Data> data) {
    // data 列表本身在 Old Gen（长寿）
    // 但循环中的临时对象在 Young Gen
    
    for (Data item : data) {  // item 在 Young Gen
        String formatted = format(item);  // formatted 在 Young Gen
        result.add(formatted);  // 复制到 result
    }
    // formatted 在下次 Minor GC 后死亡
}
```

---

## 三、Old Gen 的特性

### 5.2.7 Old Gen 的特点

| 特性 | 说明 |
|:---|:---|
| **空间占比** | ~75% |
| **Region 数量** | ~768 个（256 MB 堆） |
| **分配方式** | bump pointer（晋升）+ 偶尔直接分配 |
| **GC 策略** | Major GC（低频） |
| **对象稳定性** | 长寿对象 |
| **碎片化** | 无（整体回收） |

### 5.2.8 Old Gen 的对象来源

**Old Gen 中的对象来源**：
1. **晋升**：Young Gen 中活过一定次数的对象晋升
2. **预分配**：大对象直接进入 LOS（不属 Old Gen 但相邻）
3. **直接分配**：长寿对象从一开始就分配在 Old Gen

### 5.2.9 Old Gen 的分配路径

```cpp
// Old Gen 中的分配（罕见）
mirror::Object* RegionSpace::AllocInOldGen(Thread* self, size_t num_bytes, ...) {
    // 1. Old Gen 中是否有空闲 Region
    Region* free_region = old_gen_pool_.AllocateRegion();
    if (free_region == nullptr) {
        return nullptr;  // Old Gen 满
    }
    
    // 2. 转换 Region 状态
    free_region->state_ = kRegionStateOldGen;
    
    // 3. 在 Region 中分配
    return free_region->Alloc(num_bytes);
}
```

---

## 四、对象晋升机制

### 5.2.10 对象年龄的定义

```cpp
// art/runtime/obj_ptr-inl.h
class Object {
    uint32_t age_;  // 对象年龄（每次 Minor GC +1）
    
    // 检查是否达到晋升阈值
    bool ShouldPromote() {
        return age_ >= kPromotionThreshold;  // 默认 15
    }
};
```

### 5.2.11 晋升阈值

```cpp
// art/runtime/gc/collector/concurrent_copying.h
static constexpr uint32_t kPromotionThreshold = 15;

// 含义：对象活过 15 次 Minor GC 就晋升到 Old Gen
```

### 5.2.12 晋升的实现

```cpp
// art/runtime/gc/collector/concurrent_copying.cc 的 Promote
void ConcurrentCopying::Promote(mirror::Object* obj) {
    // 1. 检查对象年龄
    if (!obj->ShouldPromote()) {
        // 2. 未达阈值 → 复制到 Young Gen 新 Region
        CopyToYoungGen(obj);
        return;
    }
    
    // 3. 达到阈值 → 晋升到 Old Gen
    CopyToOldGen(obj);
    
    // 4. 更新对象状态
    obj->age_ = 0;  // 重置年龄
    obj->SetInOldGen();  // 标记为 Old Gen
}
```

### 5.2.13 晋升策略

| 策略 | 阈值 | 适用场景 |
|:---|:---|:---|
| **固定阈值** | 15 次 Minor GC | 默认 |
| **自适应阈值** | 根据 Old Gen 占用率动态调整 | ART 14+ |

---

## 五、Young/Old Gen 的协作

### 5.2.14 Minor GC 流程

```
1. 触发条件：Young Gen 满
2. STW：暂停所有 mutator 线程（< 0.5ms）
3. 扫描 Young Gen 的所有 Root
4. 扫描 Card Table 找 Old → Young 跨代引用
5. 从 Root 出发，递归标记所有可达对象
6. 复制活对象：
   - 年龄 < 阈值 → 复制到 Young Gen 新 Region
   - 年龄 >= 阈值 → 晋升到 Old Gen
7. 回收 Young Gen 死对象
8. 重置 TLAB
9. STW 结束
```

### 5.2.15 Major GC 流程

```
1. 触发条件：Old Gen 满
2. STW：暂停所有 mutator 线程（< 50ms）
3. 扫描全堆（Young + Old + LOS）
4. 从 Root 出发，递归标记所有可达对象
5. 复制活对象：
   - Young Gen 对象 → 留在 Young Gen（晋升阈值后到 Old Gen）
   - Old Gen 对象 → 复制到 Old Gen 新 Region
   - LOS 对象 → 标记存活
6. 回收死对象
7. 重置 TLAB
8. STW 结束
```

### 5.2.16 GenCC 的 GC 触发决策

```cpp
// art/runtime/gc/heap.cc 的 Heap::SelectGc
GcType Heap::SelectGc() {
    // 1. 计算 Young Gen 使用率
    double young_usage = GetYoungGenUsage();
    
    // 2. 计算 Old Gen 使用率
    double old_usage = GetOldGenUsage();
    
    // 3. 决策
    if (young_usage > 0.8) {
        return kMinorGc;  // Young Gen 满了 → Minor GC
    } else if (old_usage > 0.8) {
        return kMajorGc;  // Old Gen 满了 → Major GC
    } else {
        return kConcurrentMajorGc;  // 后台 GC
    }
}
```

---

## 六、Young/Old Gen 的内存管理

### 5.2.17 Young Gen 大小的动态调整

```cpp
// art/runtime/gc/heap.cc 的 Heap::AdjustYoungGenSize
void Heap::AdjustYoungGenSize() {
    // 1. 统计最近的 Minor GC 数据
    double minor_gc_frequency = minor_gc_count_ / uptime_;
    double minor_gc_avg_time = minor_gc_total_time_ / minor_gc_count_;
    
    // 2. 决策
    if (minor_gc_frequency > 10 && minor_gc_avg_time < 0.5) {
        // Minor GC 频繁但耗时短 → 增大 Young Gen
        young_gen_size_ = std::min(young_gen_size_ * 1.2, max_young_size_);
    } else if (minor_gc_frequency < 1) {
        // Minor GC 频率低 → 减小 Young Gen
        young_gen_size_ = std::max(young_gen_size_ * 0.8, min_young_size_);
    }
}
```

### 5.2.18 Old Gen 的回收策略

```
Old Gen 满时：
  1. 优先触发 Major GC
  2. 如果 Major GC 后还满 → 触发 OOM

Major GC 时的考虑：
  - Old Gen 占用率（不能超 max_allowed_footprint）
  - Young Gen 中的对象（不能全部晋升）
  - LOS 中的对象（不复制）
```

---

## 七、Young/Old Gen 的工程影响

### 5.2.19 业务代码的影响

**原则 1：长寿对象应该一次性分配在 Old Gen**

```java
// ✅ 好：单例对象一次性创建
public class AppManager {
    private static final AppManager INSTANCE = new AppManager();
    // INSTANCE 在 Old Gen（如果用静态字段）
}

// ❌ 不好：每次都创建新实例
public AppManager getInstance() {
    return new AppManager();  // 每次都在 Young Gen
}
```

**原则 2：缓存应该在 Old Gen**

```java
// ✅ 好：缓存使用线程安全容器
private static final ConcurrentHashMap<String, Object> cache = 
    new ConcurrentHashMap<>();
// cache 在 Old Gen

// ❌ 不好：缓存在 Young Gen，会被 Minor GC 回收
private static final HashMap<String, Object> cache = new HashMap<>();
```

**原则 3：避免 Young Gen 中的长寿对象**

```java
// ✅ 好：临时对象不持有外部引用
public void process() {
    Object temp = new Object();  // temp 在 Young Gen
    // process(temp);
    // temp 在下次 Minor GC 后死亡
}

// ❌ 不好：临时对象被静态字段持有
private static Object temp;  // temp 被提升到 Old Gen
public void process() {
    temp = new Object();  // temp 在 Young Gen 但会被提升
}
```

### 5.2.20 监控 Young/Old Gen

```bash
# 1. 看 Young Gen 使用率
adb shell dumpsys meminfo <package> | grep -E "Young Gen|Old Gen"

# 2. 看晋升速率
adb logcat -s "art" | grep "Promote"

# 3. 看 Minor GC 频率
adb logcat -s "art" | grep "Minor GC"
```

---

## 八、本节小结

1. **Young/Old Gen 划分**：Young Gen ~25%，Old Gen ~75%
2. **Region 在两代中的角色**：Young Gen ~256 个 Region，Old Gen ~768 个 Region
3. **对象晋升**：年龄阈值 15 次 Minor GC
4. **Minor GC 只扫描 Young Gen**：< 0.5ms STW
5. **Major GC 扫描全堆**：< 50ms STW
6. **Young Gen 大小动态调整**：ART 14+ 自适应

→ **理解 Young/Old Gen 划分，就理解了 GenCC 的物理布局**。

---

## 跨节引用

**本节被以下章节引用**：
- [5.3 Card Table](./03-Card-Table基石.md) —— 跨代引用的记录器
- [5.5 Minor/Major GC](./05-Minor-Major-GC.md) —— 两代 GC 的分工
- [5.6 对象晋升](./06-对象晋升.md) —— 晋升机制详解

**本节引用**：
- [5.1 分代假说](./01-分代假说.md) —— 分代假说
- [02 篇 2.5 Region-based](../02-Heap与分配器/05-Region-based分配器.md) —— Region 分配器
- [04 篇 CC GC](./../04-CC-GC/README.md) —— CC 在分代中的应用
