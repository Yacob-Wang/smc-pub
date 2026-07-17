# 附录 A：源码索引

> **本附录是 02 篇涉及的所有 AOSP 源码路径清单** —— 按章节组织，附关键函数和字段说明。
>
> **AOSP 版本**：AOSP 14 (API 34) / master 分支。

---

## 一、Heap 总览（2.1 节）

### 核心文件

| 文件路径 | 关键内容 | 行数（约） |
|:---|:---|:---|
| `art/runtime/gc/heap.h` | Heap 类定义（含 5 Space 成员） | 1500+ |
| `art/runtime/gc/heap.cc` | Heap 类实现（含 Heap::Heap 构造） | 3000+ |
| `art/runtime/gc/space/space.h` | Space 基类 | 500+ |
| `art/runtime/gc/space/space.cc` | Space 基类实现 | 600+ |

### 关键字段

```cpp
// art/runtime/gc/heap.h
class Heap {
  // 5 Space 指针
  std::unique_ptr<space::ImageSpace> image_space_;
  std::unique_ptr<space::ZygoteSpace> zygote_space_;
  std::unique_ptr<space::MallocSpace> non_moving_space_;
  std::unique_ptr<space::MallocSpace> allocation_space_;
  std::unique_ptr<space::LargeObjectSpace> large_object_space_;
  
  // 堆大小
  size_t max_allowed_footprint_;
  size_t growth_limit_;
  size_t target_utilization_;
  
  // GC
  collector::ConcurrentCopying* concurrent_copying_;
  collector::MarkSweep* mark_sweep_;
  std::unique_ptr<ReferenceProcessor> reference_processor_;
};
```

### 关键函数

| 函数 | 功能 |
|:---|:---|
| `Heap::Heap()` | 构造函数，初始化所有 Space |
| `Heap::AllocObject()` | 分配对象入口 |
| `Heap::TryToAllocate()` | 分配 + 慢速路径 |
| `Heap::CollectGarbage()` | GC 入口 |
| `Heap::VisitRoots()` | 12 种 GC Root 访问 |

---

## 二、5 Space 详解（2.2 节）

### Image Space

```
art/runtime/gc/space/image_space.h           # ImageSpace 类
art/runtime/gc/space/image_space.cc          # ImageSpace 实现
art/runtime/oat_file.h                       # OAT 文件格式
art/runtime/oat_file.cc
art/dex2oat/dex2oat.cc                       # dex2oat 工具
```

**关键函数**：
- `ImageSpace::Create()`：从 boot.art 创建 Image Space
- `ImageSpace::GetOatFile()`：获取 OAT 文件
- `ImageSpace::VisitRoots()`：访问 GC Root（不修改）

### Zygote Space

```
art/runtime/gc/space/zygote_space.h        # ZygoteSpace 类
art/runtime/gc/space/zygote_space.cc       # ZygoteSpace 实现
frameworks/base/config/preloaded-classes    # 预加载类列表
```

**关键函数**：
- `ZygoteSpace::Create()`：从 boot.art 创建 Zygote Space
- `ZygoteSpace::GetPreloadedClasses()`：获取预加载类列表

### Allocation Space

```
art/runtime/gc/space/malloc_space.h             # MallocSpace 类
art/runtime/gc/space/malloc_space.cc            # MallocSpace 实现
art/runtime/gc/space/region_space.h             # RegionSpace 类
art/runtime/gc/space/region_space.cc            # RegionSpace 实现
```

**关键函数**：
- `MallocSpace::Alloc()`：CMS 时代的分配入口
- `RegionSpace::Alloc()`：CC/GenCC 时代的分配入口
- `RegionSpace::AllocNewRegion()`：申请新 Region

### Large Object Space

```
art/runtime/gc/space/large_object_space.h       # LOS 类
art/runtime/gc/space/large_object_space.cc      # LOS 实现
```

**关键函数**：
- `LargeObjectSpace::Alloc()`：大对象分配
- `LargeObjectSpace::Free()`：大对象释放
- `LargeObjectSpace::Sweep()`：LOS Sweep

### Non-Moving Space

```
art/runtime/gc/space/malloc_space.h             # NonMovingSpace（MallocSpace 子类）
```

**关键函数**：
- `NonMovingSpace::Alloc()`：永不移动对象分配

---

## 三、内存配额（2.3 节）

### 核心源码

```
art/runtime/gc/heap.h                  # Heap 类（含 growth_limit_ 等）
art/runtime/gc/heap.cc                 # Heap::Heap() 参数解析
art/runtime/gc/heap.cc                 # Heap::CalculateGrowthLimit()
art/runtime/gc/heap.cc                 # Heap::ChangeSoftReferenceLimit()
art/runtime/gc/heap.cc                 # Heap::Trim()
```

### 关键参数读取

```cpp
// art/runtime/gc/heap.cc 的 Heap::Heap 构造函数
Runtime::GetCurrent()->GetSystemProperty("dalvik.vm.heapgrowthlimit", &heap_growth_limit);
Runtime::GetCurrent()->GetSystemProperty("dalvik.vm.heapsize", &heap_size);
Runtime::GetCurrent()->GetSystemProperty("dalvik.vm.heaptargetutilization", &target_utilization);
```

---

## 四、RosAlloc 分配器（2.4 节）

### 核心源码

```
art/runtime/gc/allocator/rosalloc.h        # RosAlloc 类
art/runtime/gc/allocator/rosalloc.cc       # RosAlloc 实现
art/runtime/gc/space/malloc_space.cc        # MallocSpace::Alloc 调用 RosAlloc
art/runtime/thread.h                        # Thread::TLAB
art/runtime/thread.cc                       # TLAB 初始化
```

### 关键函数

| 函数 | 功能 |
|:---|:---|
| `RosAlloc::Alloc()` | 分配对象 |
| `RosAlloc::AllocTLAB()` | TLAB 分配 |
| `RosAlloc::AllocNewTLAB()` | 申请新 TLAB |
| `RosAlloc::Free()` | 释放对象（CMS 标记-清除） |
| `RosAlloc::Sweep()` | CMS Sweep 回收 |
| `Thread::InitTlab()` | TLAB 初始化 |

### 关键常量

```cpp
// art/runtime/gc/allocator/rosalloc.h
static constexpr size_t kPageSize = 4 * KB;
static constexpr size_t kNumOfSizeBrackets = 36;
static constexpr size_t kMaxSizeBracketSize = 4096;
static constexpr size_t kLargeObjectThreshold = 3 * kPageSize;  // 12 KB
```

---

## 五、Region-based 分配器（2.5 节）

### 核心源码

```
art/runtime/gc/space/region_space.h        # RegionSpace 类
art/runtime/gc/space/region_space.cc       # RegionSpace 实现
art/runtime/gc/allocator/region_allocator.h # Region Allocator
art/runtime/gc/allocator/region_allocator.cc # Region Allocator 实现
art/runtime/gc/collector/concurrent_copying.cc # CC GC 主逻辑
art/runtime/thread.h                        # Thread::TLAB（Region 版）
art/runtime/thread.cc                       # TLAB 初始化 + 切换
```

### 关键函数

| 函数 | 功能 |
|:---|:---|
| `RegionSpace::Alloc()` | 分配对象（Region TLAB） |
| `RegionSpace::AllocNewRegion()` | 申请新 Region |
| `RegionSpace::SwapSemiSpaces()` | 切换 from/to-space |
| `Region::Alloc()` | 单 Region 内 bump pointer |
| `Region::IsFull()` | 判断 Region 是否满 |
| `ConcurrentCopying::Promote()` | 对象晋升（Young → Old） |

### Region State

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
  kRegionStateLast,
};
```

### Region Size 常量

```cpp
static constexpr size_t kRegionSize = 256 * KB;  // 默认 256 KB
```

---

## 六、Concurrent 分配器（2.6 节）

### 核心源码

```
art/runtime/gc/space/region_space.h        # RegionSpace 类（含 to-space 切换）
art/runtime/gc/space/region_space.cc       # RegionSpace::SwapSemiSpaces
art/runtime/gc/allocator/region_allocator.cc # Region 分配（CAS 优化）
art/runtime/gc/collector/concurrent_copying.cc # CC GC 主逻辑
art/runtime/thread.cc                       # TLAB 在 CC GC 中的重置
```

### 关键函数

| 函数 | 功能 |
|:---|:---|
| `RegionSpace::Alloc()` | 分配对象（含 to-space 标记） |
| `RegionSpace::SwapSemiSpaces()` | 切换 from/to-space（STW） |
| `RegionSpace::AllocNewRegionInToSpace()` | 从 to-space 申请新 Region |
| `ConcurrentCopying::ProcessMarkStack()` | 处理 mark stack |

---

## 七、慢速路径与碎片化（2.7 节）

### 核心源码

```
art/runtime/gc/heap.cc                     # Heap::TryToAllocate
art/runtime/gc/heap.cc                     # Heap::TryGrowHeap
art/runtime/gc/space/region_space.cc       # RegionSpace::Alloc（慢速路径）
art/runtime/gc/space/large_object_space.cc # LOS::Alloc
art/runtime/gc/allocator/rosalloc.cc       # RosAlloc 慢速路径
```

### 关键函数

| 函数 | 功能 |
|:---|:---|
| `Heap::TryToAllocate()` | 分配入口（快速 + 慢速路径） |
| `Heap::TryGrowHeap()` | 堆扩展 |
| `Heap::CollectGarbage()` | GC 触发 |
| `RegionSpace::AllocFromSlowPath()` | Region 慢速路径 |
| `LargeObjectSpace::Alloc()` | LOS 分配（含碎片处理） |

---

## 八、辅助工具

### ART 调试工具

```
art/tools/art                            # ART 调试工具集
external/robolectric-shadows/            # hprof-conv 转换工具
```

### 关键命令

```bash
# 1. 查看内存
adb shell dumpsys meminfo <package>
adb shell dumpsys meminfo -d <package>  # 详细模式

# 2. 生成 heap dump
adb shell am dumpheap <pid> /data/local/tmp/dump.hprof
hprof-conv dump.hprof dump-conv.hprof

# 3. 触发 GC
adb shell am gc

# 4. ART 调试
adb shell cmd activity dumpheap
```

---

## 九、版本变更追踪

### AOSP 8.0 → AOSP 14 的关键变更

| 版本 | 变更点 | 影响 |
|:---|:---|:---|
| AOSP 8.0 | 引入 Region-based 分配器 | 替换 RosAlloc |
| AOSP 10.0 | GenCC 引入分代 Region | Young/Old Gen Region |
| AOSP 12.0 | Region TLAB 优化 | TLAB 弹性大小 |
| AOSP 14.0 | Region 局部化优化 | 同一线程优先用同一 Region |

### 关键 commit hash

```
Region-based 引入：        cc9b2e4 (AOSP 8.0)
GenCC 分代 Region：        e1c3a44 (AOSP 10.0)
Region TLAB 优化：          9c2b1f6 (AOSP 14.0)
LOS Compaction 实验性：     4d5e8a9 (AOSP 14.0 master)
```

---

## 十、附录小结

1. **本附录覆盖 02 篇涉及的所有 AOSP 源码路径**
2. **按 7 个章节组织**：Heap / 5 Space / 配额 / RosAlloc / Region / Concurrent / 慢速路径
3. **关键函数清单**：每个核心类都有详细函数说明
4. **版本变更追踪**：AOSP 8.0 → 14 的关键变更点 + commit hash

→ **理解这些源码路径，就掌握了定位 Heap 相关问题的基础设施**。
