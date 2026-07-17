# 2.2 5 Space 详解

> **本节是 ART 堆的"详细地图"** —— 把 5 个 Space 每个都讲清楚。
>
> **理解本节，就理解了每种 OOM 的根因**——5 种 OOM 对应 5 种 Space。

---

## 一、5 Space 总览

### 2.2.1 5 Space 对照表

| Space | 内存来源 | 是否可移动 | GC 参与 | 典型大小 | 典型内容 |
|:---|:---|:---|:---|:---|:---|
| **Image Space** | mmap boot.art | 否 | 不参与 | ~50 MB | OAT 镜像、Boot ClassLoader 类 |
| **Zygote Space** | mmap boot.art | 否 | 不参与 | ~30 MB | preloaded-classes |
| **Allocation Space** | mmap（RosAlloc/Region） | 是 | 是 | 256 MB | Young Gen + Old Gen（GenCC） |
| **Large Object Space (LOS)** | mmap | 否 | 是（标记-清除） | dynamic | Bitmap、byte[] ≥ 12KB |
| **Non-Moving Space** | mmap | 否 | 不参与 | dynamic | String 常量池、Class 对象 |

### 2.2.2 5 Space 的物理内存布局

```
┌────────────────────────────────────────────────────────────────┐
│                  Java Heap (default 256 MB)                    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────┐ ┌──────────────────────────┐    │
│  │  Image Space (~50 MB)    │ │ Zygote Space (~30 MB)    │    │
│  │  mmap boot.art           │ │ mmap boot.art            │    │
│  │  只读                    │ │ fork 时共享               │    │
│  └──────────────────────────┘ └──────────────────────────┘    │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │       Allocation Space (default 256 MB)                  │ │
│  │                                                          │ │
│  │  CMS (Android 5-7)        CC / GenCC (Android 8+)      │ │
│  │  ┌──────────┬──────────┐  ┌──────────────────────────┐  │ │
│  │  │ Young    │ Old      │  │ Region Space              │  │ │
│  │  │ (RosA.)  │          │  │  - Region 0 (free)        │  │ │
│  │  └──────────┴──────────┘  │  - Region 1 (allocating)  │  │ │
│  │                          │  - Region 2 (large obj)    │  │ │
│  │                          │  - ...                     │  │ │
│  │                          └──────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌──────────────────────────┐ ┌──────────────────────────┐    │
│  │  Large Object Space      │ │  Non-Moving Space        │    │
│  │  (dynamic, 通常 ~20 MB)  │ │  (CC GC 早期版本)         │    │
│  │  bitmap, byte[1024*1024] │ │  String 常量池            │    │
│  └──────────────────────────┘ └──────────────────────────┘    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 二、Image Space（镜像空间）

### 2.2.3 Image Space 的定义

**Image Space** 是 **只读的 OAT 镜像空间**，存放 Boot ClassLoader 加载的所有预编译类。

```cpp
// art/runtime/gc/space/image_space.h（精简版）
class ImageSpace : public Space {
 public:
  // 从 boot.art / boot.oat 加载
  static ImageSpace* Create(const std::string& image, ...);
  
  // Image Space 的内容：OAT 文件 mmap 后映射的内存
  // - dex2oat 预编译的 AOT 代码
  // - 类对象（String.class、Integer.class 等）
  // - 字符串字面量
};
```

### 2.2.4 Image Space 的特点

| 特性 | 说明 |
|:---|:---|
| **只读** | mmap 时标记为 PROT_READ，永不修改 |
| **不参与 GC** | 不扫描、不标记、不清除 |
| **进程共享** | boot.art 可被多个进程共享（节省内存） |
| **大版本兼容** | boot.art 由 dex2oat 生成，与 ART 版本强绑定 |

### 2.2.5 Image Space 的内容

```
Image Space:
  ┌────────────────────────────────────────────────┐
  │  OAT Header                                   │
  │  - magic: "oat\n"                              │
  │  - checksum                                   │
  │  - instruction set: arm64 / x86_64             │
  │  - dex_file_count                              │
  └────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────┐
  │  OAT Method Table                             │
  │  - Quick Compiled Code                        │
  │  - dex2oat 预编译的 AOT 机器码                │
  └────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────┐
  │  OAT Class Table                              │
  │  - Class 对象 (String.class, Integer.class)   │
  │  - 类元数据 (methods, fields)                  │
  └────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────┐
  │  String Intern Table                          │
  │  - String 常量池 (字面量)                      │
  └────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────┐
  │  DEX File Data                                │
  │  - 原始 dex 数据 (供类查找)                   │
  └────────────────────────────────────────────────┘
```

### 2.2.6 Image Space 的源码路径

```
art/runtime/gc/space/image_space.h           # ImageSpace 类
art/runtime/gc/space/image_space.cc          # ImageSpace 实现
art/runtime/oat_file.h                       # OAT 文件格式
art/runtime/oat_file.cc
art/dex2oat/dex2oat.cc                       # dex2oat 工具
```

---

## 三、Zygote Space（预加载空间）

### 2.2.7 Zygote Space 的定义

**Zygote Space** 是 **Zygote 进程 fork 时共享的预加载类空间**。所有 App 进程都从 Zygote fork 出来，共享这部分内存，节省启动时间和内存占用。

```cpp
// art/runtime/gc/space/zygote_space.h（精简版）
class ZygoteSpace : public Space {
 public:
  // Zygote Space 是 Image Space 的子集
  // 包含 preloaded-classes 中的所有类
  static ZygoteSpace* Create(const std::string& image, ...);
};
```

### 2.2.8 Zygote Space 的 preloaded-classes

```bash
# AOSP 源码中的 preloaded-classes 列表
# frameworks/base/config/preloaded-classes

# 示例（精简）
android.app.Activity
android.app.Application
android.os.Binder
android.os.Handler
android.view.View
java.lang.Object
java.lang.String
java.util.HashMap
...
```

通常包含 **3000-5000 个预加载类**。

### 2.2.9 Zygote Space 的优势

| 优势 | 说明 |
|:---|:---|
| **节省内存** | 所有 App 共享同一份 Zygote Space 内存 |
| **加快启动** | App 进程 fork 后无需加载预加载类 |
| **保护只读** | fork 时复制内存页（COW），App 进程不修改 |

### 2.2.10 Zygote Space 的 Copy-on-Write（COW）

```
Zygote 进程:
  Zygote Space = 0x1000 - 0x2000 (只读)
                   │
                   ▼ fork()
                   │
  ┌───────────────┼───────────────┐
  │               │               │
App 进程 A       App 进程 B     App 进程 C
  Zygote Space = 0x1000 - 0x2000 (共享)
                   │
                   ▼ 进程 A 第一次写入 0x1500
                   │
  App 进程 A:
    0x1000 - 0x1500 = 共享 (来自 Zygote)
    0x1500 - 0x1600 = 私有副本
    0x1600 - 0x2000 = 共享 (来自 Zygote)
```

→ Zygote Space 通过 **fork + COW** 实现 App 进程间的内存共享。

### 2.2.11 Zygote Space 的源码路径

```
art/runtime/gc/space/zygote_space.h        # ZygoteSpace 类
art/runtime/gc/space/zygote_space.cc       # ZygoteSpace 实现
frameworks/base/config/preloaded-classes    # 预加载类列表
frameworks/base/core/java/android/app/ZygoteInit.java
frameworks/base/core/java/com/android/internal/os/Zygote.java
```

---

## 四、Allocation Space（分配空间）

### 2.2.12 Allocation Space 的定义

**Allocation Space** 是 **常规对象分配的主战场**，所有 `new Object()` 默认从这里分配。

```cpp
// art/runtime/gc/space/malloc_space.h（精简版）
class MallocSpace : public Space {
 public:
  // Allocation Space 是 MallocSpace 的子类
  // CMS 用 RosAlloc
  // CC/GenCC 用 Region-based
  mirror::Object* Alloc(Thread* self, size_t num_bytes, ...);
};
```

### 2.2.13 Allocation Space 的特点

| 特性 | CMS（RosAlloc） | CC / GenCC（Region） |
|:---|:---|:---|
| **内存布局** | 连续内存 + RosAlloc | 多个 Region（1 MB / 4 MB） |
| **分配方式** | TLAB + Run-of-Slots | TLAB + Bump Pointer |
| **GC 算法** | Mark-Sweep | Mark-Copy |
| **对象移动** | 不移动（标记-清除） | 移动（标记-复制） |
| **碎片化** | 高（不压缩） | 低（Region 整体回收） |

### 2.2.14 Allocation Space 的 CMS 时代实现

```
Allocation Space (CMS, RosAlloc):
  ┌────────┬────────┬────────┬────────┬────────┬────────┐
  │ Thread │ Thread │  ...   │ Run 0  │ Run 1  │ Run 2  │
  │ Local  │ Local  │        │ (16B)  │ (32B)  │ (64B)  │
  │ Alloc  │ Alloc  │        │        │        │        │
  │ Buf 1  │ Buf 2  │        │        │        │        │
  └────────┴────────┴────────┴────────┴────────┴────────┘
       ↑        ↑                  ↑
    TLAB 1   TLAB 2            RosAlloc Runs
```

### 2.2.15 Allocation Space 的 CC / GenCC 实现

```
Allocation Space (CC / GenCC, Region-based):
  ┌─────────┬─────────┬─────────┬─────────┬─────────┐
  │ Region 0│ Region 1│ Region 2│ Region 3│ Region 4│
  │ (Free)  │ (Alloc) │ (Young) │ (Old)   │ (Large) │
  │         │ TLAB    │ 80% full│ 50% full│ 30% full│
  └─────────┴─────────┴─────────┴─────────┴─────────┘
                                                  ↑
                                              1 MB each
```

### 2.2.16 Allocation Space 的源码路径

```
art/runtime/gc/space/malloc_space.h             # MallocSpace 类
art/runtime/gc/space/malloc_space.cc            # MallocSpace 实现
art/runtime/gc/space/region_space.h             # RegionSpace 类
art/runtime/gc/space/region_space.cc            # RegionSpace 实现
art/runtime/gc/allocator/rosalloc.h              # RosAlloc 分配器
art/runtime/gc/allocator/rosalloc.cc
art/runtime/gc/allocator/region_allocator.h     # Region 分配器
```

---

## 五、Large Object Space（大对象空间）

### 2.2.17 LOS 的定义

**Large Object Space (LOS)** 存放 **大对象**（默认阈值 ≥ 12 KB），主要用于 Bitmap、byte[] 等大块内存分配。

```cpp
// art/runtime/gc/space/large_object_space.h（精简版）
class LargeObjectSpace : public Space {
 public:
  // 大对象阈值（默认 12 KB，可配置）
  static constexpr size_t kDefaultLargeObjectThreshold = 12 * 1024;
  
  // LOS 分配
  mirror::Object* Alloc(Thread* self, size_t num_bytes, ...);
  
  // LOS 不移动对象（GC 时只标记-清除，不复制）
};
```

### 2.2.18 LOS 的特点

| 特性 | 说明 |
|:---|:---|
| **大对象阈值** | ≥ 12 KB（3 pages） |
| **不可移动** | CC GC 不会复制 LOS 对象 |
| **GC 策略** | Major GC 时标记-清除 |
| **碎片化** | 高（不压缩、不复制） |
| **典型内容** | Bitmap、byte[]、long[]、List/Map 的大数据 |

### 2.2.19 LOS 的内存布局

```
Large Object Space (LOS):
  ┌────────────────────────────────────────────────┐
  │  LargeObj 0 (4 MB Bitmap)                      │
  │  - 起始地址: 0x10000                            │
  │  - 大小: 4 MB                                  │
  └────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────┐
  │  LargeObj 1 (1 MB byte[])                      │
  │  - 起始地址: 0x510000                           │
  │  - 大小: 1 MB                                  │
  └────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────┐
  │  [FREE]                                        │
  │  - 0x610000 - 0x710000 (1 MB 可用)              │
  └────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────┐
  │  LargeObj 2 (8 MB byte[])                      │
  │  - 起始地址: 0x710000                           │
  │  - 大小: 8 MB                                  │
  └────────────────────────────────────────────────┘
```

**注意**：LOS 对象之间可能有 **空洞**（被回收的对象留下），形成 **外碎片**。

### 2.2.20 LOS 的来源：Bitmap 是大头

```java
// Bitmap 是 LOS 的主要占用者
Bitmap bitmap = Bitmap.createBitmap(1080, 1920, Bitmap.Config.ARGB_8888);
// 大小：1080 × 1920 × 4 = 8.3 MB → 分配到 LOS

byte[] data = new byte[10 * 1024 * 1024];  // 10 MB → 分配到 LOS
```

### 2.2.21 LOS 的来源：byte[] 是常见大对象

```java
// 常见大 byte[] 场景
byte[] fileData = new byte[1024 * 1024];      // 1 MB 文件
byte[] imageData = new byte[5 * 1024 * 1024];  // 5 MB 图片
byte[] protobufData = new byte[2 * 1024 * 1024];  // 2 MB protobuf

// 这些都会进入 LOS
```

### 2.2.22 LOS 的 GC 策略

```cpp
// art/runtime/gc/collector/mark_sweep.cc 的 SweepLargeObjects 简化版
void MarkSweep::SweepLargeObjects() {
    // 1. 遍历 LOS 中所有对象
    for (LargeObject* obj : large_object_space_->GetObjects()) {
        if (!IsMarked(obj)) {
            // 2. 未标记 → 回收
            large_object_space_->Free(obj);
        }
    }
}
```

### 2.2.23 LOS 阈值配置

```bash
# 设置 LOS 阈值（默认 12 KB，可调到 4 KB / 32 KB）
# 但通常不需要调整，ART 默认值已经过优化
adb shell setprop dalvik.vm.large-object-threshold 12288
```

### 2.2.24 LOS 的源码路径

```
art/runtime/gc/space/large_object_space.h         # LOS 类
art/runtime/gc/space/large_object_space.cc        # LOS 实现
art/runtime/gc/space/large_object_space.h         # LOS Allocator
```

---

## 六、Non-Moving Space（非移动空间）

### 2.2.25 Non-Moving Space 的定义

**Non-Moving Space** 是 **永不移动的对象空间**，主要用于存放那些 CC GC 不应该移动的对象（如 String 常量池、Class 对象）。

```cpp
// art/runtime/gc/space/malloc_space.h 的 NonMovingSpace 子类
class NonMovingSpace : public MallocSpace {
  // 与 Allocation Space 类似，但对象不参与移动
};
```

### 2.2.26 Non-Moving Space 的来源

```cpp
// 哪些对象进入 Non-Moving Space？
// 1. Class 对象（String.class、Integer.class）
// 2. String 常量池对象
// 3. Annotation 对象
// 4. 显式指定 non-moving 的对象（通过反射）

// ART 在创建这些对象时，会主动选择 Non-Moving Space
mirror::Class* AllocateClass(...) {
    return non_moving_space_->Alloc(...);
}
```

### 2.2.27 Non-Moving Space 的特点

| 特性 | 说明 |
|:---|:---|
| **永不移动** | CC GC 不会复制 Non-Moving Space 的对象 |
| **不参与 GC Root 扫描的某些阶段** | 因为地址不变 |
| **用于 JNI 缓存** | JNI 代码可以安全缓存对象指针 |
| **典型大小** | 较小（< 50 MB） |

### 2.2.28 Non-Moving Space 的废弃

**ART 10.0+** 之后，Non-Moving Space **被弃用**——CC GC 通过 **Self-Healing Pointer + 读屏障** 保证所有对象都可以安全移动。

```cpp
// ART 10.0+ 的代码
// CC GC 允许所有对象移动，依赖读屏障保证正确性
// Non-Moving Space 不再需要
```

---

## 七、Space 的协同工作

### 2.2.29 5 Space 的 GC 协同

```cpp
// art/runtime/gc/heap.cc 的 Heap::CollectGarbage 简化版
void Heap::CollectGarbage(GcCause cause, ...) {
    // 1. 暂停所有 mutator 线程
    SuspendAllThreads();
    
    // 2. 访问 GC Roots（详见 01 篇 1.1）
    VisitRoots();
    
    // 3. 标记阶段（不同 GC 算法不同）
    if (kUseCCGC) {
        // CC GC 标记 + 复制
        concurrent_copying_->RunPhases();
    } else {
        // CMS 标记
        mark_sweep_->MarkPhase();
    }
    
    // 4. 处理 Reference（详见 06 篇）
    reference_processor_->ProcessReferences();
    
    // 5. 清除 / 回收
    if (kUseCCGC) {
        // CC GC 清理 from-space
        concurrent_copying_->ReclaimPhase();
    } else {
        // CMS 清除死对象
        mark_sweep_->SweepPhase();
        // LOS 标记-清除
        mark_sweep_->SweepLargeObjects();
    }
    
    // 6. 恢复 mutator 线程
    ResumeAllThreads();
}
```

### 2.2.30 5 Space 的分配协同

```cpp
// art/runtime/gc/heap.cc 的 Heap::AllocObject 简化版
mirror::Object* Heap::AllocObject(Thread* self, size_t byte_count, ...) {
    // 1. 大对象 → LOS
    if (byte_count >= kLargeObjectThreshold) {
        return large_object_space_->Alloc(self, byte_count, ...);
    }
    
    // 2. Non-Moving 对象 → Non-Moving Space
    if (IsNonMoving(...)) {
        return non_moving_space_->Alloc(self, byte_count, ...);
    }
    
    // 3. 常规对象 → Allocation Space（TLAB 优先）
    return allocation_space_->Alloc(self, byte_count, ...);
}
```

---

## 八、Space 与 dumpsys meminfo 的对应

### 2.2.31 dumpsys meminfo 的分类

```bash
$ adb shell dumpsys meminfo com.example.app

# 关键字段解读
                       Pss    Private   Private   SwapPss      Rss     Heap     Heap     Heap
                     Total    Dirty    Clean    Dirty    Total     Size    Alloc     Free
  Native Heap      12345     6789     1234      100    15000   102400    87654    14746
  Dalvik Heap      45678    40000     5678      200    51234    65536    45678    19858  ← 5 Space 都在这里
   .so mmap         6789     5000     1789        0     8500
   .jar mmap         500      400      100        0      600
   .apk mmap        1200      800      400        0     1500
   .ttf mmap         200      150       50        0      250
   .dex mmap        3000     2000     1000        0     3500
   Other mmap        800      500      300        0      900
   Stack            1500     1400      100        0     1700
   Cursor             50       40       10        0       60
   Ashmem           2000     1500      500        0     2300
   Other dev         300      200      100        0      350
    .so mmap        6789     5000     1789        0     8500
   TOTAL           81701    63879    17822      300   96684  102400    87654    14746
```

### 2.2.32 Dalvik Heap 的细分

dumpsys meminfo 的 **Dalvik Heap** 字段实际包含 5 Space 的总和：

```
Dalvik Heap (DalvikPss) =
    Image Space +
    Zygote Space +
    Allocation Space +
    LOS +
    Non-Moving Space
```

→ **要细分 5 Space，需要用更细粒度的工具**：
- `dumpsys meminfo --package <pkg> -d`（详细模式）
- ART 调试：`am dumpheap <pid> <file>`（生成 hprof）

---

## 九、稳定性关联：5 种 OOM 的根因

### 2.2.33 案例 1：Allocation Space OOM（最常见）

**场景**：
```java
// 频繁创建对象导致 Allocation Space 满
for (int i = 0; i < 1000000; i++) {
    list.add(new Object());  // 1M 个 Object，每个 16 字节 → 16 MB
}
```

**排查**：
```bash
# 1. dumpsys meminfo 看 Dalvik Heap Size
$ adb shell dumpsys meminfo com.example.app | grep "Dalvik Heap"
# Dalvik Heap    45678    40000     5678      200    51234    65536    45678    19858
#                                                              ↑         ↑
#                                                              Heap Size  Alloc
#                                                              65 MB     46 MB（使用中）

# 2. 触发 GC 前后对比
$ adb shell am gc   # 手动触发 GC
# 如果 GC 后 Alloc 不下降 → 内存泄漏
```

**修复**：
- 检查泄漏（LeakCanary / heap dump）
- 减小堆使用（对象池 / 复用）

### 2.2.34 案例 2：LOS 满导致 OOM（Bitmap 重度）

**场景**：
```java
// Glide 缓存大量 Bitmap
Glide.with(context)
    .load(url)
    .into(imageView);

// 每个 Bitmap 都进入 LOS
// 100 个全屏 Bitmap = 100 × 8 MB = 800 MB → OOM
```

**排查**：
```bash
# dumpsys meminfo 看 Graphics + Dalvik Heap Alloc
$ adb shell dumpsys meminfo com.example.app | grep -E "Dalvik Heap|Graphics"
# Dalvik Heap    45678    40000     5678      200    51234    65536    45678    19858
# Graphics      234567   200000    34567      500  280000

# Bitmap 占用 LOS，LOS 占用 Dalvik Heap
# 但 Bitmap 的 native 像素占用 Graphics（GL mtrack / EGL mtrack）
```

**修复**：
- 限制 Glide 缓存大小（`MemoryCache`）
- 用 inBitmap 复用 Bitmap
- 减小 Bitmap 分辨率

### 2.2.35 案例 3：Zygote fork 失败（极少但严重）

**场景**：
```bash
# 设备多次启动后 preloaded-classes 损坏
# App 进程 fork 失败 → 黑屏
```

**排查**：
```bash
adb logcat | grep -i "zygote"
# 看到 "Failed to load preloaded-classes" 或 "Cannot fork"
```

**修复**：
- 清除 dalvik-cache：`adb shell rm -rf /data/dalvik-cache`
- 重启设备

### 2.2.36 案例 4：LOS 碎片化导致大 Bitmap 分配失败

**场景**（详见 2.7 节）：
```
LOS 中间状态：
  [4 MB Bitmap] [FREE 2 MB] [8 MB Bitmap] [FREE 1 MB]

新分配请求：5 MB Bitmap
→ LOS 没有连续 5 MB 空间 → OOM

虽然 LOS 总空闲 3 MB，但都是碎片
```

**修复**：
- 用 inBitmap 复用 Bitmap
- 减小 Bitmap 大小
- 主动触发 GC + LOS 整理

---

## 十、5 Space 的源码索引

### 2.2.37 核心源码路径

```
art/runtime/gc/heap.h                           # Heap 类
art/runtime/gc/heap.cc                          # Heap 实现
art/runtime/gc/space/space.h                    # Space 基类
art/runtime/gc/space/image_space.h              # Image Space
art/runtime/gc/space/image_space.cc
art/runtime/gc/space/zygote_space.h             # Zygote Space
art/runtime/gc/space/zygote_space.cc
art/runtime/gc/space/malloc_space.h             # Allocation + Non-Moving Space
art/runtime/gc/space/malloc_space.cc
art/runtime/gc/space/large_object_space.h       # LOS
art/runtime/gc/space/large_object_space.cc
art/runtime/gc/space/region_space.h             # Region Space (CC/GenCC)
art/runtime/gc/space/region_space.cc
art/runtime/gc/allocator/rosalloc.h             # RosAlloc
art/runtime/gc/allocator/rosalloc.cc
art/runtime/gc/allocator/region_allocator.h     # Region Allocator
art/runtime/gc/allocator/region_allocator.cc
```

---

## 十一、本节小结

1. **5 Space 各有定位**：Image（只读）/ Zygote（共享）/ Allocation（主战场）/ LOS（大对象）/ NonMoving（不移动）
2. **每个 Space 的 GC 策略不同**：Image/Zygote 不参与 GC，Allocation 频繁 GC，LOS 仅 Major GC
3. **OOM 排查必须先定位哪个 Space 满了**：5 种 OOM 对应 5 种排查路径
4. **dumpsys meminfo 的 Dalvik Heap = 5 Space 总和**：要细分需要 ART 调试工具

→ **理解 5 Space，就掌握了 OOM 排查的"地图"**。

---

## 跨节引用

**本节被以下章节引用**：
- [2.3 内存配额](./03-内存配额.md) —— 配额如何分配到各 Space
- [2.4 RosAlloc](./04-RosAlloc分配器.md) —— Allocation Space 的 CMS 时代分配器
- [2.5 Region-based](./05-Region-based分配器.md) —— Allocation Space 的 CC 时代分配器
- [2.7 慢速路径与碎片化](./07-慢速路径与碎片化.md) —— LOS 碎片化根因
- [2.8 实战案例](./08-实战案例.md) —— LOS 碎片化导致大 Bitmap 分配失败
- 03/04/05 篇（CMS/CC/GenCC）—— 各 Space 的具体 GC 行为
- [09 篇诊断](../09-GC诊断与治理/) —— 5 Space 的 dumpsys meminfo 解读

**本节引用**：
- [01 篇 1.1 可达性分析](../01-基础理论/01-可达性分析.md) —— GC Root 来源
- ART 大模块的 `02-类加载与链接` —— Image Space 的 OAT 文件来源
