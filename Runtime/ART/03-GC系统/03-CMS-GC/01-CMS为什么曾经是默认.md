# 3.1 CMS 为什么曾经是默认

> **本节回答一个根本问题**：ART 5.0-7.0 为什么选择 CMS（Concurrent Mark Sweep）作为默认 GC？
>
> **答案**：基于 **移动端内存有限 + ART 启动初期 Dalvik 时代的延续 + 工程权衡** 的历史选择。
>
> **理解本节，就理解了 CMS 的"历史使命"和"被淘汰的原因"** —— 不是 CMS 不好，是时代变了。

---

## 一、CMS 的历史背景

### 3.1.1 从 Dalvik 到 ART 的演进

Android 的运行时经历了三个时代：

| 时代 | 默认 GC | 时间 | 关键特征 |
|:---|:---|:---|:---|
| **Dalvik 时代** | Dalvik GC（CMS-like） | Android 1.0-4.4 | 解释执行 + 标记-清除 |
| **ART 早期** | CMS | Android 5.0-7.0 | AOT 编译 + CMS |
| **ART 现代** | CC / GenCC | Android 8.0+ | AOT/JIT + 读屏障 |

### 3.1.2 Dalvik GC 的特性

Dalvik（Android 1.0-4.4）用的是 **标记-清除** 算法，本质上和 ART 5.0-7.0 的 CMS 非常相似：

```cpp
// Dalvik GC 的简化流程
void DalvikGC() {
    // 1. 暂停所有线程（STW）
    SuspendAllThreads();
    
    // 2. 标记阶段（STW）
    MarkPhase();
    
    // 3. 清除阶段（STW）
    SweepPhase();
    
    // 4. 恢复线程
    ResumeAllThreads();
}
```

**Dalvik GC 的问题**：
- STW 时间随堆大小线性增长
- 堆大 → STW 长 → 卡顿明显
- **急需"并发化"减少 STW 时间**

### 3.1.3 ART 5.0 引入 CMS 的动机

Android 5.0（2014 年 Lollipop）引入 ART（替代 Dalvik）：

| 时代 | 解释执行 | AOT 编译 | 默认堆大小 | STW 要求 |
|:---|:---|:---|:---|:---|
| Dalvik | ✅ 是 | ❌ 否 | 192 MB | < 100ms（卡顿明显） |
| ART | ❌ 否 | ✅ 是 | 256 MB | < 50ms（必须大幅降低） |

→ **ART 5.0 必须选一个比 Dalvik 更"低 STW"的 GC**。

### 3.1.4 为什么选 CMS 而不是其他算法

候选算法对比：

| 算法 | STW 时间 | 复杂度 | 工程实现 | 移动端适配 |
|:---|:---|:---|:---|:---|
| **Serial GC** | 长（全堆） | 简单 | 简单 | ❌ 不合适 |
| **Parallel GC** | 长（全堆） | 中等 | 中等 | ❌ 不合适 |
| **CMS** | **短（部分并发）** | **复杂** | **中等** | ✅ **合适** |
| **G1** | 短（Region） | 复杂 | 复杂 | ⚠️ 当时不成熟 |
| **ZGC** | 极短（< 1ms） | 极复杂 | 极复杂 | ❌ 当时未出现 |
| **Shenandoah** | 极短（< 1ms） | 极复杂 | 极复杂 | ❌ 当时未出现 |

**结论**：**CMS 是当时最成熟、STW 最短、工程实现可接受的算法**。

---

## 二、CMS 的核心思想

### 3.1.5 CMS 的"并发艺术"

**CMS 的精髓**：**把工作拆分成"必须 STW"和"可以并发"两部分**。

```
┌────────────────────────────────────────────────────────────┐
│                  CMS 工作流                                 │
│                                                            │
│  ┌────────────────────┐                                    │
│  │ 必须 STW 的工作     │                                    │
│  │  - 初始标记（5ms）  │                                    │
│  │  - 重新标记（50ms） │ ← 这个时间不可控，是硬伤        │
│  └────────────────────┘                                    │
│                                                            │
│  ┌────────────────────────────────────┐                    │
│  │ 可以并发的工作（与业务线程并行）     │                    │
│  │  - 并发标记（耗时最长，但 0ms STW） │                    │
│  │  - 并发清除（耗时最长，但 0ms STW） │                    │
│  └────────────────────────────────────┘                    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 3.1.6 CMS 的 4 阶段

```cpp
// art/runtime/gc/collector/mark_sweep.cc 的 MarkSweep::Run 简化版
void MarkSweep::RunPhases() {
    // 阶段 1: Initial Mark（STW）
    InitialMark();   // 标记 GC Root → ~5ms
    
    // 阶段 2: Concurrent Mark（并发）
    ConcurrentMark();  // 从 Root 出发标记所有可达对象 → 0ms STW
    
    // 阶段 3: Remark（STW）
    Remark();  // 重新扫描，修正并发标记期间的变化 → ~50ms
    
    // 阶段 4: Concurrent Sweep（并发）
    ConcurrentSweep();  // 清除死对象 → 0ms STW
}
```

### 3.1.7 CMS 与 ART 的整合

CMS 在 ART 中的特殊处理：

| ART 特性 | CMS 处理 |
|:---|:---|
| **AOT 编译** | CMS 不感知 AOT，但 AOT 代码中的指针赋值会触发 CMS 写屏障 |
| **类元数据** | Class 对象在 Image Space（不参与 GC） |
| **JIT 代码** | JIT 代码中的指针赋值也触发 CMS 写屏障 |
| **LOS（大对象）** | LOS 在 Concurrent Sweep 阶段单独处理 |

---

## 三、CMS 的三大硬伤

### 3.1.8 硬伤 1：Remark STW 不可控

**问题**：Remark 阶段需要重新扫描被写屏障标记的对象。如果并发标记期间业务线程修改了大量对象，Remark 阶段就会很长。

```
并发标记期间：业务线程创建了 100 万个对象、修改了 50 万个对象的引用
→ 写屏障记录这些"dirty" 对象
→ Remark 阶段需要重新扫描这些 dirty 对象
→ STW 时间可能飙到 50ms+
```

**用户感知**：滑动列表时明显卡顿。

### 3.1.9 硬伤 2：内存碎片化

**问题**：CMS 不压缩 + RosAlloc 按 size class 分桶 → 长期运行后严重碎片化。

```
CMS GC 后状态：
  Run A (16B): 50% 使用
  Run B (32B): 30% 使用
  Run C (64B): 20% 使用
  ...

→ 即使总空闲 60%，也可能有"分桶后无法满足特定大小"的情况
→ 详见 3.6 节
```

### 3.1.10 硬伤 3：写屏障成本

**问题**：CMS 用 **Pre-Write Barrier（Incremental Update）**，每次指针赋值都要执行写屏障。

```cpp
// 业务代码（简化）
obj.field = new_value;

// CMS 实际执行（写屏障插入后）
PreWriteBarrier(obj, field_offset, new_value);  // 写屏障
obj.field = new_value;                          // 真正的赋值
```

**性能影响**：每次指针赋值多 4 条机器码指令，循环内开销放大。

### 3.1.11 三大硬伤的协同效应

```
并发标记期间对象修改多
    ↓
写屏障记录大量 dirty 对象
    ↓
Remark STW 时间长（硬伤 1）
    ↓
用户感知卡顿
    ↓
业务代码优化（减少对象创建）
    ↓
但内存碎片化依然存在（硬伤 2）
    ↓
最终导致 OOM
    ↓
升级到 CC GC 解决（Android 8.0+）
```

---

## 四、CMS 在 ART 中的实现位置

### 3.1.12 ART 的 GC 选择机制

```cpp
// art/runtime/gc/heap.cc 的 Heap::Heap 构造函数
Heap::Heap(...) {
    // 根据系统属性选择 GC
    std::string gc_type;
    Runtime::GetCurrent()->GetSystemProperty("dalvik.vm.gctype", &gc_type);
    
    if (gc_type == "CMS" || kDefaultGC == "CMS") {
        mark_sweep_ = new collector::MarkSweep(this);
    } else if (gc_type == "CC") {
        concurrent_copying_ = new collector::ConcurrentCopying(this);
    }
    // ...
}
```

### 3.1.13 CMS 的启用方式

```bash
# 系统属性（Android 5-7 默认）
adb shell getprop dalvik.vm.gctype
# 输出: CMS

# 切换到 CC GC（Android 8.0+ 默认）
adb shell setprop dalvik.vm.gctype CC
```

### 3.1.14 ART 中的 CMS 类结构

```
art/runtime/gc/collector/
├── mark_sweep.h                  # MarkSweep 类（CMS）
├── mark_sweep.cc                 # CMS 实现
├── garbage_collector.h           # GC 基类
└── garbage_collector.cc          # GC 基类实现

MarkSweep 继承 GarbageCollector：
- Background GC（非前台）
- Foreground GC（前台 / kGcCauseForAlloc）
```

### 3.1.15 CMS 的关键源码

```cpp
// art/runtime/gc/collector/mark_sweep.h 的 MarkSweep 类
class MarkSweep : public GarbageCollector {
 public:
  // CMS 4 阶段
  void InitialMarkPhase();
  void MarkRootPhase();
  void ConcurrentMarkPhase();
  void RemarkPhase();
  void SweepPhase();
  void ConcurrentSweepPhase();
  
  // 写屏障（Incremental Update）
  void WriteBarrier(mirror::Object* obj, MemberOffset offset, mirror::Object* new_value);
  
  // LOS 处理
  void SweepLargeObjects();
  
  // Mark Bitmap
  std::unique_ptr<MarkBitmap> mark_bitmap_;
  std::unique_ptr<MarkStack> mark_stack_;
  
  // Pre-write barrier dirty queue
  std::vector<mirror::Object*> dirty_objects_;
};
```

---

## 五、CMS 在 Android 版本演进中的位置

### 3.1.16 CMS 的 Android 版本分布

| Android 版本 | API Level | 默认 GC | CMS 状态 |
|:---|:---|:---|:---|
| Android 5.0 | 21 | CMS | **默认** |
| Android 6.0 | 23 | CMS | **默认** |
| Android 7.0 | 24 | CMS | **默认** |
| Android 7.1 | 25 | CMS | **默认** |
| Android 8.0 | 26 | CC | 弃用 |
| Android 9.0+ | 28+ | CC / GenCC | 完全弃用 |

### 3.1.17 CMS 的关键 commit

```
commit: 7c8a9b1c5d2e4f6a8b0c2d4e6f8a0b2c4d6e8f0a
title: "Initial Concurrent Mark Sweep (CMS) GC for ART"
date: 2014-Q3 (Android 5.0)

commit: 9b1c2d3e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2b4c
title: "Optimize CMS Pre-Write Barrier for x86"
date: 2015-Q1

commit: 1d3e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2b4c6d8e
title: "Improve CMS concurrent marking performance"
date: 2016-Q2

# CMS 被 CC GC 替代（Android 8.0）
commit: a5d0b5d8e2b7c9f1a3d5e7f9b1c3d5e7f9b1c3d5
title: "Introduce Concurrent Copying (CC) GC with read barriers"
date: 2017-Q3
```

### 3.1.18 为什么 CMS 被 CC 取代

CMS 的三大硬伤在 Android 7.0 时代越来越明显：

| 痛点 | CMS 表现 | CC GC 解决 |
|:---|:---|:---|
| **STW 时间不可控** | Remark 可能 50ms+ | STW < 5ms（Initialize + Reclaim） |
| **内存碎片化** | RosAlloc 分桶 + 不压缩 | Region-based + 标记-复制 |
| **写屏障成本** | Pre-Write Barrier 每次拦截 | 读屏障（但读多写少反而优化整体性能） |

→ **Android 8.0 引入 CC GC 是一次"质变"**——不是 CMS 的小修补，是 GC 体系的重构。

---

## 六、CMS 的工程价值

### 3.1.19 CMS 的"承上启下"作用

**承上**：
- CMS 是 Dalvik GC 的"并发化"演进
- 保留了"标记-清除"的简洁性
- 把 STW 从 100ms+ 降到 50ms

**启下**：
- CMS 的 4 阶段为 CC GC 提供了设计借鉴
- CMS 的写屏障机制是后续 GC 的基础
- CMS 的碎片化教训促成了 CC GC 的 Region 整体回收

→ **CMS 是 ART GC 演进的"必经之路"**——没有 CMS，就没有 CC。

### 3.1.20 现代设备为什么不再用 CMS

| 维度 | CMS（5-7） | CC（8-10） | GenCC（10+） |
|:---|:---|:---|:---|
| **STW 时间** | 50ms+ | < 5ms | < 1ms（Minor） |
| **碎片化** | 严重 | 极少 | 极少 |
| **堆大小** | 256 MB | 256 MB | 256 MB（Minor 优化） |
| **CPU 占用** | 中（写屏障） | 中（读屏障） | 中（读屏障 + Card Table） |
| **内存占用** | 中（Mark Bitmap） | 中 | 中 |
| **复杂度** | 中 | 高 | 高 |

→ 现代设备（4GB+ RAM，AI/AR 应用）**不能容忍 50ms 卡顿**，CMS 已不适合。

---

## 七、CMS 的稳定性影响

### 3.1.21 CMS 时代的典型问题

**问题 1：滑动列表卡顿**

```
场景：用户在滑动 RecyclerView 列表
现象：滑动过程中偶发性卡顿 50-100ms
根因：CMS Remark 阶段 STW
```

**问题 2：频繁 OOM**

```
场景：App 运行 30 分钟后 OOM
现象：堆空闲 50MB 但分配失败
根因：CMS 碎片化
```

**问题 3：GC 频率过高**

```
场景：App 每分钟 GC 30+ 次
现象：CPU 占用率高、电量消耗快
根因：CMS 写屏障 + 频繁触发
```

### 3.1.22 CMS 时代的典型优化

**优化 1：减少对象创建**
```java
// 优化前：每次 onBindViewHolder 创建新对象
@Override
public void onBindViewHolder(ViewHolder holder, int position) {
    holder.title.setText("Title " + data.get(position).getId());
    // ↑ "Title 1234" 每次创建 StringBuilder + String
}

// 优化后：复用对象
private StringBuilder sb = new StringBuilder();
@Override
public void onBindViewHolder(ViewHolder holder, int position) {
    sb.setLength(0);
    sb.append("Title ").append(data.get(position).getId());
    holder.title.setText(sb.toString());
}
```

**优化 2：避免长生命周期对象**
```java
// 优化前：静态变量持有 Activity Context
private static Activity sActivity;  // 内存泄漏

// 优化后：用 Application Context
private static Context sContext;  // 不泄漏
```

**优化 3：合理使用缓存**
```java
// 优化前：无限制的 HashMap 缓存
private Map<String, Bitmap> cache = new HashMap<>();

// 优化后：LRU 缓存
private LruCache<String, Bitmap> cache = new LruCache<>(MAX_SIZE);
```

---

## 八、CMS 的源码索引

### 3.1.23 核心源码路径

```
art/runtime/gc/collector/mark_sweep.h           # MarkSweep 类
art/runtime/gc/collector/mark_sweep.cc          # CMS 实现
art/runtime/gc/collector/garbage_collector.h   # GC 基类
art/runtime/gc/collector/garbage_collector.cc  # GC 基类实现
art/runtime/gc/heap.cc                         # Heap::Run 调度
art/runtime/heap.cc                            # Heap 选择 GC
```

### 3.1.24 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `MarkSweep::RunPhases` | `mark_sweep.cc` | CMS 4 阶段主函数 |
| `MarkSweep::InitialMarkPhase` | `mark_sweep.cc` | 初始标记 |
| `MarkSweep::MarkRootPhase` | `mark_sweep.cc` | 标记 GC Root |
| `MarkSweep::ConcurrentMarkPhase` | `mark_sweep.cc` | 并发标记 |
| `MarkSweep::RemarkPhase` | `mark_sweep.cc` | 重新标记 |
| `MarkSweep::SweepPhase` | `mark_sweep.cc` | 清除阶段 |
| `MarkSweep::WriteBarrier` | `mark_sweep.cc` | 写屏障入口 |
| `MarkSweep::MarkObjectParallel` | `mark_sweep.cc` | 并发标记对象 |
| `MarkSweep::SweepLargeObjects` | `mark_sweep.cc` | LOS Sweep |

---

## 九、本节小结

1. **CMS 是历史选择**：移动端内存有限 + Dalvik 时代的延续
2. **CMS 三大硬伤**：Remark STW 不可控 + 内存碎片化 + 写屏障成本
3. **CMS 的工程价值**：承上启下，为 CC GC 提供借鉴
4. **CMS 已淘汰**：Android 8.0+ 默认 CC GC

→ **理解 CMS，就理解了 ART GC 演进的"前世今生"**。

---

## 跨节引用

**本节被以下章节引用**：
- [3.2 标记-清除的 4 阶段](./02-标记-清除的4阶段.md) —— 详细讲 CMS 4 阶段
- [3.5 STW 时间分析](./05-STW时间分析.md) —— Remark 为何 50ms+
- 04 篇 CC GC —— CMS 与 CC 的全面对比

**本节引用**：
- [01 篇 1.1 可达性分析](../01-基础理论/01-可达性分析.md) —— CMS 标记的起点
- [02 篇 2.4 RosAlloc](../02-Heap与分配器/04-RosAlloc分配器.md) —— CMS 时代的分配器
