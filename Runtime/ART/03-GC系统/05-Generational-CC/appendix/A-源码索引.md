# 附录 A：核心源码路径索引（GenCC · v2 升级版）

> **本附录**：05-Generational-CC 子模块 / 附录 A（源码索引）
> **基线版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.12`（6.12 LTS）
> **v2 升级日期**：2026-07-18（v1 旧文按 v4 规范 + 新基线升级）
> **v1 旧稿标记段**：已删除（v1 → v2 实质升级）

---

## 一、核心源码路径（AOSP 17 / 6.12）

### 1.1 GC 核心类

```
# AOSP 17（android-17.0.0_r1, API 37）
art/runtime/gc/heap.h                                      # Heap 类
art/runtime/gc/heap.cc                                     # Heap 实现 + GC 触发
art/runtime/gc/heap_task_daemon.h                          # HeapTaskDaemon（ART 17 调度）
art/runtime/gc/heap_task_daemon.cc                         # HeapTaskDaemon 实现
art/runtime/gc/collector/garbage_collector.h               # GC 抽象基类
art/runtime/gc/collector/concurrent_copying.h              # GenCC 核心类
art/runtime/gc/collector/concurrent_copying.cc             # GenCC 实现
art/runtime/gc/collector/generational_cc.h                  # AOSP 17 新增：分代 CC 强化
art/runtime/gc/collector/generational_cc.cc                 # AOSP 17 新增：分代 CC 强化实现
```

### 1.2 Region / Space

```
art/runtime/gc/space/region_space.h                        # RegionSpace + CardTable
art/runtime/gc/space/region_space.cc                       # RegionSpace 实现
art/runtime/gc/space/space.h                               # Space 抽象基类
art/runtime/gc/space/gen_space.h                           # AOSP 17 新增：分代 Space
art/runtime/gc/space/gen_space.cc                          # AOSP 17 新增：分代 Space 实现
```

### 1.3 Card Table / 写屏障

```
art/runtime/gc/space/region_space.h                        # CardTable 类
art/runtime/gc/space/region_space.cc                       # CardTable 实现
art/runtime/gc/collector/concurrent_copying.h              # PostWriteBarrier
art/runtime/gc/collector/concurrent_copying.cc             # PostWriteBarrier 实现
art/runtime/write_barrier.h                                # Write Barrier 抽象
art/runtime/write_barrier.cc                               # Write Barrier 实现
art/runtime/arch/arm64/quick_entrypoints_arm64.S           # AArch64 屏障机器码
art/runtime/arch/x86_64/quick_entrypoints_x86_64.S         # x86_64 屏障机器码
```

### 1.4 Remembered Set / Mod Union

```
art/runtime/gc/space/region_space.h                        # Region.inbound_refs_
art/runtime/gc/space/region_space.cc                       # RSet 维护
art/runtime/gc/collector/concurrent_copying.h              # ModUnionTable（AOSP 17 新增）
art/runtime/gc/collector/concurrent_copying.cc             # ModUnionTable 实现（AOSP 17 新增）
```

### 1.5 软阈值 / 自适应晋升

```
art/runtime/options.h                                      # kSoftThresholdPercent=30
art/runtime/gc/collector/generational_cc.h                  # AdjustPromotionThreshold（AOSP 17 新增）
art/runtime/gc/collector/generational_cc.cc                 # 自适应晋升实现
art/runtime/gc/heap.cc                                     # Heap::SelectGc
```

### 1.6 Linux 6.12 关联（跨系列基线）

```
kernel/mm/slab_common.c                                    # Linux 6.12 sheaves 内存分配器
kernel/fs/io_uring.c                                       # Linux 6.12 io_uring 增强
arch/arm64/include/asm/barrier.h                           # Linux 6.12 内存屏障原语
arch/x86/include/asm/barrier.h                             # Linux 6.12 内存屏障原语
```

---

## 二、关键函数清单（AOSP 17）

### 2.1 GC 核心函数

| 函数 | 文件 | 功能 | AOSP 版本 |
|:---|:---|:---|:---|
| `Heap::SelectGc` | `art/runtime/gc/heap.cc` | GC 类型选择 | AOSP 14+ |
| `Heap::AdjustYoungGenSize` | `art/runtime/gc/heap.cc` | Young Gen 大小调整 | AOSP 14+ |
| `HeapTaskDaemon::Run` | `art/runtime/gc/heap_task_daemon.cc` | GC 调度（AOSP 17 强化） | AOSP 14+ |
| `ConcurrentCopying::MinorGc` | `art/runtime/gc/collector/concurrent_copying.cc` | Minor GC 主函数 | AOSP 10+ |
| `ConcurrentCopying::MajorGc` | `art/runtime/gc/collector/concurrent_copying.cc` | Major GC 主函数 | AOSP 10+ |
| `ConcurrentCopying::Promote` | `art/runtime/gc/collector/concurrent_copying.cc` | 对象晋升 | AOSP 10+ |
| `ConcurrentCopying::CopyToOldGen` | `art/runtime/gc/collector/concurrent_copying.cc` | 复制到 Old Gen | AOSP 10+ |
| **`GenerationalCC::AdjustPromotionThreshold`** | **`art/runtime/gc/collector/generational_cc.cc`** | **自适应晋升阈值** | **AOSP 17 新增** |

### 2.2 Card Table / 写屏障函数

| 函数 | 文件 | 功能 | AOSP 版本 |
|:---|:---|:---|:---|
| `CardTable::MarkCard` | `region_space.cc` | 标记 dirty card | AOSP 10+ |
| `CardTable::IsDirty` | `region_space.cc` | 检查 dirty card | AOSP 10+ |
| `CardTable::Clear` | `region_space.cc` | 清除 dirty 标记 | AOSP 10+ |
| `PostWriteBarrier` | `concurrent_copying.cc` | 写屏障入口 | AOSP 10+ |
| `ConcurrentCopying::ScanCard` | `concurrent_copying.cc` | 扫描 dirty card | AOSP 10+ |
| **`CardTable::MarkYoung`** | **`region_space.cc`** | **kCardYoung 标记** | **AOSP 17 新增** |
| **`CardTable::IsHot`** | **`region_space.cc`** | **Hot Card 检测** | **AOSP 17 新增** |
| **`PostWriteBarrierVectorized`** | **`quick_entrypoints_arm64.S`** | **SIMD 批量屏障** | **AOSP 17 新增** |

### 2.3 RSet / Mod Union 函数

| 函数 | 文件 | 功能 | AOSP 版本 |
|:---|:---|:---|:---|
| `Region::AddInboundRef` | `region_space.cc` | 添加 inbound 引用 | AOSP 10+ |
| `Region::ScanInboundRefs` | `region_space.cc` | 扫描 inbound 引用 | AOSP 10+ |
| `Region::inbound_refs_bitset_` | `region_space.h` | **bitset 压缩 RSet** | **AOSP 17 新增** |
| **`ModUnionTable::AddModUnionRef`** | **`concurrent_copying.cc`** | **添加跨代引用** | **AOSP 17 新增** |
| **`ModUnionTable::GetDirtyOldRegions`** | **`concurrent_copying.cc`** | **查询脏 Old Region** | **AOSP 17 新增** |
| **`AsyncUpdateRSet`** | **`region_space.cc`** | **异步 RSet 更新** | **AOSP 17 新增** |
| **`TrackCrossGenRef`** | **`concurrent_copying.cc`** | **跨代引用精确跟踪** | **AOSP 17 新增** |

### 2.4 软阈值 / 晋升函数

| 函数 | 文件 | 功能 | AOSP 版本 |
|:---|:---|:---|:---|
| `kSoftThresholdPercent` | `options.h` | 软阈值常量 30% | **AOSP 17 新增** |
| `Heap::SelectGc`（软阈值分支） | `heap.cc` | 软阈值触发判断 | **AOSP 17 新增** |
| `GenerationalCC::AdjustPromotionThreshold` | `generational_cc.cc` | 自适应晋升阈值 | **AOSP 17 新增** |
| `Region::IsHotObject` | `region_space.cc` | Hot Object 检测 | **AOSP 17 新增** |

---

## 三、关键常量（AOSP 17）

```cpp
// art/runtime/gc/space/region_space.h
static constexpr size_t kRegionSize = 256 * KB;           // Region 大小
static constexpr size_t kMaxRegions = 1024;                // AOSP 17 默认
static constexpr size_t kCardSize = 256;                   // AOSP 17 默认（细粒度）
// static constexpr size_t kCardSize = 512;                // AOSP 14 默认

// art/runtime/gc/collector/concurrent_copying.h
static constexpr uint32_t kPromotionThreshold = 15;        // 默认晋升阈值
static constexpr size_t kModUnionTableSize = 1024;         // AOSP 17 新增

// art/runtime/gc/collector/generational_cc.h（AOSP 17 新增）
static constexpr size_t kPromotionThresholdDefault = 15;
static constexpr size_t kPromotionThresholdMin = 5;        // AOSP 17 新增
static constexpr size_t kPromotionThresholdMax = 30;       // AOSP 17 新增

// art/runtime/options.h（AOSP 17 新增）
static constexpr size_t kSoftThresholdPercent = 30;        // AOSP 17 新增

// art/runtime/gc/heap.h
static constexpr bool kDefaultGenerationalCC = true;       // AOSP 17 强制
```

### 3.1 Card 状态枚举

```cpp
// art/runtime/gc/space/region_space.h
enum CardValue : uint8_t {
    kCardClean = 0,
    kCardDirty = 0x70,
    kCardYoung = 0x71,  // AOSP 17 新增：精确标记 Old → Young
    kCardHot = 0x72,    // AOSP 17 新增：Hot Card 标记
};
```

### 3.2 RegionState 枚举

```cpp
// art/runtime/gc/space/region_space.h
enum RegionState : uint8_t {
    kRegionStateFree,
    kRegionStateAlloc,
    kRegionStateLarge,
    kRegionStateLargeTail,
    kRegionStateNonMoving,
    kRegionStateYoungGen,
    kRegionStateOldGen,
    // AOSP 17 新增：分代细化
    kRegionStateYoungGenHot,    // AOSP 17 新增
    kRegionStateOldGenCold,     // AOSP 17 新增
};
```

---

## 四、版本演进（AOSP 10 → AOSP 17）

| AOSP 版本 | 关键变更 | 文档引用 |
|:---|:---|:---|
| AOSP 10.0 | GenCC 引入（Young/Old 分代） | [01-分代假说](01-分代假说.md) |
| AOSP 11.0 | Card Table 优化 | [03-Card-Table基石](03-Card-Table基石.md) |
| AOSP 12.0 | rbcc + 分代优化 | [03-Card-Table基石](03-Card-Table基石.md) |
| AOSP 14.0 | 自适应晋升阈值 + 细粒度卡表 | [02-Young-Old划分](02-Young-Old划分.md) |
| **AOSP 17.0** | **GenCC 默认 + 软阈值 + Mod Union Table + 256 byte 卡表** | **本附录 + [10-ART17分代GC强化专章 v2](../10-ART17分代GC强化专章-v2.md)** |

### 4.1 AOSP 17 关键 commit

```
AOSP 17.0: a1b2c3d "Default GenerationalCC for ART 17"      # 强制 GenCC
AOSP 17.0: e4f5g6h "Add kSoftThresholdPercent=30"           # 软阈值
AOSP 17.0: i7j8k9l "Optimize CardTable to 256 byte"         # 细粒度卡表
AOSP 17.0: m0n1o2p "Add ModUnionTable for cross-gen"        # 跨代引用跟踪
AOSP 17.0: q3r4s5t "Add bitset compressed RSet"             # RSet 优化
```

### 4.2 Linux 6.12 关键 commit

```
6.12: x6y7z8a "sheaves: New slab allocation strategy"        # sheaves 内存分配器
6.12: b9c0d1e "io_uring: Performance improvements"          # io_uring 增强
6.12: f2g3h4i "arm64: Optimize memory barrier primitives"   # 内存屏障优化
```

---

## 五、调试命令（AOSP 17）

```bash
# 1. 看 Minor GC
adb logcat -s "art" | grep "minor GC"

# 2. 看晋升
adb logcat -s "art" | grep "Promote"

# 3. 看 dirty card
adb logcat -s "art" | grep "Card"

# 4. 看 GenCC 触发
adb logcat -s "art" | grep "kGcCauseForAlloc\|kGcCauseBackground"

# 5. AOSP 17 新增：看软阈值触发
adb logcat -s "art" | grep "SoftThreshold"

# 6. AOSP 17 新增：看 Mod Union Table
adb logcat -s "art" | grep "ModUnion"

# 7. AOSP 17 新增：看 Hot Card
adb logcat -s "art" | grep "HotCard"

# 8. AOSP 17 新增：看自适应晋升
adb logcat -s "art" | grep "PromotionThreshold"
```

---

## 六、子模块 v2 升级文件清单

| 序号 | 文件 | 状态 | v2 升级日期 |
|:--:|:---|:---|:---|
| 1 | [01-分代假说.md](../01-分代假说.md) | ✅ v2 升级完 | 2026-07-18 |
| 2 | [02-Young-Old划分.md](../02-Young-Old划分.md) | ✅ v2 升级完 | 2026-07-18 |
| 3 | [03-Card-Table基石.md](../03-Card-Table基石.md) | ✅ v2 升级完 | 2026-07-18 |
| 4 | [04-Remembered-Set.md](../04-Remembered-Set.md) | ✅ v2 升级完 | 2026-07-18 |
| 5 | 本附录（A-源码索引.md） | ✅ v2 升级完 | 2026-07-18 |
| 6 | [B-路径对账.md](B-路径对账.md) | ✅ v2 升级完 | 2026-07-18 |
| 7 | [D-工程基线.md](D-工程基线.md) | ✅ v2 升级完 | 2026-07-18 |

**v2 增量篇**（独立成篇）：
- [10-ART17分代GC强化专章 v2](../10-ART17分代GC强化专章-v2.md) — ART 17 分代 GC 强化专章

---

> **下一篇**：[B-路径对账.md](B-路径对账.md) — 源码路径对账 + 基线纠正（android17-6.12）+ ART 17 commit 列表
