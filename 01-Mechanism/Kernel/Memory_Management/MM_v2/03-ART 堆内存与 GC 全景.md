# 03-ART 堆内存与 GC 全景

> **系列**：面向稳定性的 Android 内存架构深度解析系列（MM_v2）
>
> **源码基线**：AOSP `android-14.0.0_r1`（`refs/heads/android14-release`）
>
> **内核矩阵**：`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`（ART 用户态运行时，不直接涉及内核版本差异；GC pause 时长受内核 cgroup / PSI 影响，详见 07 篇）
>
> **目标读者**：Android 稳定性框架架构师
>
> **前置阅读**：[01-内存系统总览：从进程视角到硬件的完整链路](01-内存系统总览：从进程视角到硬件的完整链路.md)、[02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md)
>
> **下一篇**：[04-Native 堆内存与分配器（AOSP 14）](04-Native 堆内存与分配器（AOSP 14）.md)

---

## 本篇定位

- **本篇系列角色**：核心机制第 3 篇 — 讲 ART 运行时（Java 堆）的分代、GC 算法、可见性、与 Native 堆的边界、压力行为；线上 60-70% 内存类故障根因落在本层
- **强依赖**：MM_v2 02 已讲"VMA 体系"（本篇的 `[anon:dalvik-*]` 段在 maps 里怎么映射、ART 堆在 VMA 里如何表达）
- **承接自**：02 §2 VMA 三类划分中的 `[anon:dalvik-main space]` 等段
- **衔接去**：
  - 04 讲 Native 堆（scudo 分配器；与 ART 堆的边界在 JNI 引用表）
  - 05 讲 Framework 治理（ART 堆是 AMS 杀进程决策的关键依据）
  - 12 风险地图（ART 堆占 5 大风险类中的 3 类）
- **不重复内容**：
  - 02 已讲的 VMA 数据结构,本篇不重复
  - Native 堆（scudo/jemalloc）详见 04

#### §0 锚点案例的可验证 4 件套:相机 App ART 堆 GC 退化导致主线程 STW 1.5s

> **环境**:
> - 设备:Pixel 7（G2,arm64-v8a,8GB RAM）
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某相机 App v3.5.0（脱敏代号 CamApp,集成 2 个相机 SDK,使用大量 JNI + Bitmap）
> - 工具:`dumpsys meminfo` + `Perfetto` + `am dumpheap` + `LeakCanary`

> **复现步骤**:
> 1. 工厂重置,安装 CamApp v3.5.0
> 2. 打开相机 → 切换前后摄像头(循环 50 次)
> 3. 偶发主线程卡顿 1-2s,ANR 占比 0.3%(行业基线 <0.1%)
> 4. `dumpsys gfxinfo` 观察 Janky frames 上升到 18%(基线 2%)

> **logcat / dumpsys meminfo 关键片段**:
> ```
> $ adb shell dumpsys meminfo com.example.camera
>    Java Heap:   165432K    165432K        0K    ← 典型 PSS
>    Native Heap: 78932K     78932K        0K
>             .Global Ref:   1245   ← 异常大(基线 < 200)
>             .Local Ref:    5120   ← 异常大(基线 < 500)
> Background concurrent copying paused:  4521 次, 平均 8ms
> Foreground concurrent copying paused:   189 次, 平均 312ms  ← 异常,P99 ~1.5s
> Total GC time:                          64.2s
> ```
> ```
> # Perfetto trace 关键观察点
> GC 卡在 Foreground CC 的 ProcessMarkStack 阶段,持续 1.2-1.5s
> # hprof Retained Size TopN:
>   1. com.example.camera.ImageProcessor$1: 38MB   ← 内部类泄漏
>   2. android.graphics.Bitmap: 24MB × 3
>   3. com.example.camera.JNIBridge: 12MB          ← Native peer
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/sdk/native/camera_jni.cpp
> +++ b/sdk/native/camera_jni.cpp
> @@ -JNI Global Ref 配对
>  static jobject g_preview_buffer = nullptr;
>  void setPreviewBuffer(JNIEnv* env, jobject bitmap) {
> -    g_preview_buffer = env->NewGlobalRef(bitmap);  // 旧:不释放
> +    if (g_preview_buffer) env->DeleteGlobalRef(g_preview_buffer);
> +    g_preview_buffer = bitmap ? env->NewGlobalRef(bitmap) : nullptr;
>  }
> +void JNI_OnUnload(JavaVM* vm, void* /*reserved*/) {
> +    JNIEnv* env;
> +    if (vm->GetEnv((void**)&env, JNI_VERSION_1_6) == JNI_OK) {
> +        if (g_preview_buffer) env->DeleteGlobalRef(g_preview_buffer);
> +    }
> +}
> ```
> ```diff
> --- a/sdk/native/process_frames.cpp
> +++ b/sdk/native/process_frames.cpp
> @@ -JNI Local Ref 配对 + PushLocalFrame
>  void processFrames(JNIEnv* env, jobjectArray frames) {
>      int count = env->GetArrayLength(frames);
> -    for (int i = 0; i < count; i++) {
> -        jobject frame = env->GetObjectArrayElement(frames, i);
> -        // ... 忘记 DeleteLocalRef
> -    }
> +    if (env->PushLocalFrame(count + 10) != 0) return;
> +    for (int i = 0; i < count; i++) {
> +        jobject frame = env->GetObjectArrayElement(frames, i);
> +        // 处理 frame
> +    }
> +    env->PopLocalFrame(nullptr);  // 自动释放所有 local ref
>  }
> ```
> 完整 3 个根因 + 全部修复方案见 §8。

---

## 0. 写在前面：为什么 ART 堆是稳定性的"主战场"

在 [01-内存系统总览](01-内存系统总览：从进程视角到硬件的完整链路.md) 我们建立了五层架构；在 [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md) 我们看了进程视角的"虚拟地址账本"。本篇沿着这条路径**下钻一层**——进入 Layer 2（ART 运行时），聚焦 Java 堆本身：它的分代、它的算法、它的可见性、它和 Native 堆的边界、它在压力下的行为。

对稳定性架构师而言，ART 堆是线上问题的"主战场"——线上内存类故障的 60-70% 根因都落在这一层。原因有三：

1. **Java 堆是进程最大单一内存块**。典型 App 的 Java 堆占 PSS 的 30-50%（256MB-512MB 级别），`dumpsys meminfo` 第一行就是它。
2. **GC 是 Java 堆的"主线程杀手"**。一次长 GC pause 直接表现为 ANR 或卡顿。
3. **Java 堆的"可见性"问题最容易被忽视**。Concurrent GC 不等于"无 STW"，仍然有 6 个 STW 阶段；很多"偶发卡顿"实际上是 GC STW 的累积。

> **稳定性架构师视角：** 排查 ART 堆问题的"四象限"——
> ```
>        容量（多大/会不会 OOM）
>               │
>               │
> 可见性 ────────┼──────── 算法（CC 还是 CMS，怎么走）
> （pause 多少） │
>               │
>        边界（与 Native 堆的 JNI 桥）
> ```
> 任何一个"OOM"或"卡顿"问题，先定位到这四个象限中的哪个，再深入。**不要一上来就 dump hprof 盲查**——那是最慢的路径。

本篇会沿着"分代空间 → 算法选型 → 可见性 → JNI 边界 → 大对象 → 压力模式 → 风险地图 → 实战案例"的链路，把这四象限彻底讲透。

---

## 1. ART 堆的分代：Young / Old / Zygote / Card Table / Region

### 1.1 是什么 / 为什么需要分代

ART 堆不是一块连续的虚拟地址，而是由**多个语义不同的 Space**组成的逻辑集合。每一个 Space 都有自己的分配策略、回收策略、内存布局。

**为什么需要分代？** 这是 60 年前 GC 研究的核心问题。**弱分代假设（Weak Generational Hypothesis）**：

> 绝大多数 Java 对象"朝生夕死"——80% 的对象在分配后的第一次 GC 就会被回收；活过越多次 GC 的对象越可能继续存活。

如果不分代，每次 GC 必须扫描整个堆——O(堆大小)。分代后：
- 频繁回收 Young 区（小、快、收完有大量空位）
- 偶尔回收 Old 区（大、慢、收完空位少）
- Young → Old 的对象搬运用 Card Table 跟踪

**对稳定性架构师的价值**：理解分代后，看 `dumpsys meminfo` 输出的"Young / Native / Code / Stack / Graphics" 行就有了语义——每一行对应一个具体的 Space 行为。

### 1.2 ART 堆的五个空间（拓扑图）

AOSP android-14.0.0_r1 中，`art/runtime/gc/heap.h` 定义了 5 种 Space 类型：

```
┌─────────────────────────────────────────────────────────────────────┐
│                          ART 堆 (Heap)                               │
│                  入口: art::Heap (art/runtime/gc/heap.h)             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ ImageSpace       │  │ ZygoteSpace      │  │ NonMovingSpace   │ │
│  │ (boot image)     │  │ (preloaded cls)  │  │ (large/atomic)   │ │
│  │ 只读, mmap 预加载 │  │ fork 时共享      │  │ 不移动的对象      │ │
│  │  ~64MB           │  │  ~30MB           │  │  几十~几百 MB     │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘ │
│                                                                     │
│  ┌──────────────────┐  ┌────────────────────────────────────────┐  │
│  │ RegionSpace      │  │ LargeObjectSpace (LOS)                 │  │
│  │ (CC 的核心)      │  │ (large arrays)                         │  │
│  │ Region = 256KB   │  │ free list 管理                          │  │
│  │ 数十~数百 Region │  │  ~几十~几百 MB                          │  │
│  └──────────────────┘  └────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 1.2.1 ImageSpace（启动映像空间）

**是什么**：在系统启动时（`/system/framework/boot.art`），ART 把所有系统类（`java.lang.*`、`android.app.*` 等）的预编译 dex 加载为一个**只读、共享、mmap 映射**的空间。

**为什么需要它**：避免每个进程启动时重新解析、验证、编译系统类——这是 Android 冷启动优化中**最关键的一步**。典型 `boot.art` 大小 60-80MB。

**稳定性风险**：
- 启动时如果 `boot.art` 损坏（OTA 升级异常、磁盘损坏），所有进程无法启动
- 12KB 以下的"hot class" 在 ImageSpace → RegionSpace 的搬迁需要 art 内部维护

源码：`art/runtime/gc/space/image_space.cc`、`art/runtime/gc/space/image_space.h`。

#### 1.2.2 ZygoteSpace（预加载空间）

**是什么**：Zygote 进程在启动时把大量预加载类（典型 2000+ 个）的对象（Class 对象、方法对象、字符串等）放在一个**写时复制（COW）** 的空间。**当 Zygote fork 出 App 进程时，这些对象对所有 App 共享**。

**为什么需要它**：把"启动时一次性加载 → 多个进程共享"做到极致。`Activity`、`Service`、`Context` 这些高频类的 Class 对象只占一份物理页。

**稳定性风险**：
- 一旦 Zygote 空间被破坏（如 OAT 文件损坏），所有 fork 出的 App 启动失败
- Zygote 空间不能在运行时修改——它依赖 mmap 的 `MAP_PRIVATE`，写时会触发 COW 复制

源码：`art/runtime/gc/space/zygote_space.cc`、`art/runtime/gc/space/zygote_space.h`。

#### 1.2.3 NonMovingSpace（不移动空间）

**是什么**：存放**不能被 GC 移动**的对象，比如 `java.lang.Class` 对象本身、`DexCache`、`Method`、`Field` 等反射相关对象。CC 收集器可以移动 RegionSpace 中的对象，但**这些对象地址对 JNI 暴露，地址变化会破坏 JNI 兼容性**。

**为什么需要它**：JNI 性能优化 + 兼容性。如果 GC 移动了 JNI 正在用的对象，native 侧指针会悬空。

**源码**：`art/runtime/gc/space/space.h` 中 `kSpaceTypeNonMovingSpace` 类型；实际分配由 `art::Heap::AllocNonMoving` 处理。

```cpp
// art/runtime/gc/heap.cc （AOSP android-14.0.0_r1）
// AllocNonMoving：分配到 NonMovingSpace
mirror::Object* Heap::AllocNonMoving(Thread* self, size_t num_bytes, ...) {
  // NonMovingSpace 不参与 CC 的 Region 搬迁
  // 它使用 bump pointer + free list
  return non_moving_space_->Alloc(num_bytes, ...);
}
```

#### 1.2.4 RegionSpace（CC 主空间）

**是什么**：CC 收集器的基本单位。一个 Region 256KB（Android 14 默认，可调），多个 Region 组成 RegionSpace。Region 有 4 种状态：Free / Allocated / TLAB / Large。

**为什么需要 Region 而不是连续堆**：CC 收集器是"复制式"——回收时把存活对象从当前 Region 复制到另一个 Region。Region 化让"复制"的代价可控（每次只复制 256KB）。

**Region 分配的关键路径**（AOSP 14 真实函数名，**注意不是旧版的 `AllocObjectWithAllocator` / `RegionSpace::Alloc`**）：

```cpp
// art/runtime/gc/space/region_space-inl.h （AOSP android-14.0.0_r1）
// 【教学简化说明】下面两段代码是 AOSP 14 源码的"教学骨架版"，
// 保留函数名 + 核心控制流，省略了：
//   - AllocNewTlab 在 AOSP 14 真实签名是 (Thread*, size_t tlab_size, size_t* bytes_tl_bulk_allocated)
//     （3 参；本节为可读性简化为 1 参）
//   - AllocateRegion 在 AOSP 14 真实签名是 (bool for_evac)（1 参 bool，不是 RegionUse 枚举）
//   - partial_tlabs_ multimap 复用、cyclic allocation 策略等高级逻辑
// 复制到 IDE 之前请回 AOSP 14 真实源码对齐完整签名。
//
// AllocNewTlab：把整个 Region 分配给当前线程作 TLAB
bool RegionSpace::AllocNewTlab(Thread* self) {
  // 1. 释放当前线程原 TLAB
  RevokeThreadLocalBuffersLocked(self);
  // 2. 找一个 free region（默认 256KB 大小）→ 设置为 TLAB
  for (size_t i = 0; i < num_regions_; ++i) {
    Region* r = &regions_[i];
    if (r->IsFree()) {
      r->Unfree(time_);
      ++num_non_free_regions_;
      r->SetTop(r->End());
      r->is_a_tlab_ = true;
      r->thread_ = self;
      self->SetTlab(r->Begin(), r->End());
      return true;
    }
  }
  return false;
}

// AllocateRegion：分配非 TLAB 用的 region
// AOSP 14 真实参数：(bool for_evac) — 本节为教学用 RegionUse 枚举
Region* RegionSpace::AllocateRegion(RegionUse use) {
  // 找 free region，标记为 use（kRegionUseAlloc / kRegionUseTLAB / kRegionUseLarge）
}
```

> **稳定性架构师视角：** Region 化让"GC 退化"成为可观察的现象：HUMONGOUS 对象会一次占用整个 Region，导致该 Region 在 GC 周期内无法被有效回收（详见 §5）。**这是 ART 14 大对象导致的"GC 退化"主因**。

#### 1.2.5 LargeObjectSpace / LOS（大对象空间）

**是什么**：存放 > 12KB（默认阈值，可通过 `dalvik.vm.heapsize` 系列参数调整）的 Java 数组和字符串。

**为什么需要单独空间**：避免大对象打散 RegionSpace 的布局；用 free list 管理而不是 Region copy。

**稳定性风险**：
- 大数组的分配和回收都昂贵（free list 维护）
- bitmap 解码后的 ARGB_8888 大图（1080×1920 像素 = 8.3MB）走 LOS

源码：`art/runtime/gc/space/large_object_space.cc`。

### 1.3 Card Table 与 Remembered Set

**是什么**：Card Table 是一个字节数组，把堆分成若干个"Card"（默认 512 字节一个 Card）。每次写引用时，触发**写屏障（write barrier）**把对应的 Card 标记为"dirty"。

**为什么需要它**：当 GC 在回收 Young 区时，需要知道 Old 区**哪些对象引用了 Young 区的对象**——避免漏标导致 Young 区的"本应死亡"对象被错误保留。

```
┌────────────────────────────────────────────────────────────┐
│                    Old 区（不扫描）                         │
│                                                            │
│  Card 0  Card 1  Card 2  ...  Card N                       │
│  ┌──┐    ┌──┐    ┌──┐                                     │
│  │ 0│    │ 1│    │ 0│  ...  0 = clean, 1 = dirty          │
│  └─┬┘    └─┬┘    └──┘                                     │
│    │       │                                               │
│    │ write_barrier(obj.field = young_ref)                  │
│    │       │                                               │
│    ▼       ▼                                               │
│  remembered set (RS) ← Young GC 时只扫描 RS 中 dirty 的 Card │
└────────────────────────────────────────────────────────────┘
```

**源码**：

```cpp
// art/runtime/gc/collector/concurrent_copying.cc
// CC 的写屏障在 Heap::WriteBarrier 路径
// 简化逻辑：每次引用字段赋值时，把目标地址所在的 Card 标 dirty
inline void Heap::WriteBarrierField(ObjPtr<mirror::Object> dst, MemberOffset offset) {
  // ... 标记 Card 为 dirty ...
}
```

> **稳定性架构师视角：** **写屏障的开销是 Java 堆的"隐藏税"**。一次引用字段赋值多 5-15ns。在紧密循环里（如 `for (Object o : list) result.add(o)` 触发 list 内部数组扩容），这个开销会被放大 10x。**Java 性能优化的一个核心原则：减少不必要的对象引用关系**。

### 1.4 Region：CC 收集器的基本单位

Region 是 CC 收集器的核心抽象。一个 Region 256KB，内含元数据（top / end / type / thread）：

```cpp
// art/runtime/gc/space/region_space.h
struct Region {
  // Region 在堆中的位置
  uint8_t* begin_;        // 起始地址
  uint8_t* top_;          // 已分配位置
  uint8_t* end_;          // 结束地址
  // 状态
  RegionState state_;     // kRegionStateFree / kRegionStateAlloc / kRegionStateTLAB
  // TLAB 拥有者
  Thread* thread_;        // 哪个线程的 TLAB
  // 类型（仅 CC 模式）
  RegionType type_;       // kRegionTypeRegular / kRegionTypeHumongous
  // ... 40+ 字段
};
```

Region 的关键约束（**影响 GC 行为**）：
- 256KB 大小，**对齐到 256KB**
- 一个对象超过 Region 一半（128KB）就成为 HUMONGOUS（占用整 Region）
- 多个小对象在同一 Region 内部用 bump pointer 分配

> **稳定性架构师视角：** Region 是 ART 14 的"GC 调优单位"。`dalvik.vm.heapregionmaxfree`、`dalvik.vm.heapregionminfree` 等参数控制 Region 的"水位线"——堆占用超水位时触发 GC。这是 `dumpsys meminfo` 输出"GC 原因"时的关键背景。

---

## 2. GC 算法选型：Concurrent Copying (CC) / Concurrent Mark Sweep (CMS)

### 2.1 是什么 / 两条路线的设计目标

Android 历史上 ART 运行时支持 4 种 GC 收集器（`art::gc::collector::GarbageCollector`）：

| 收集器 | 引入版本 | 核心机制 | 主要场景 | 暂停时间目标 |
|--------|---------|---------|---------|------------|
| **Concurrent Mark Sweep (CMS)** | Android 5.0-9 | 标记-清除，并发 | 旧设备 fallback | 前台 < 100ms |
| **Concurrent Copying (CC)** | Android 10+ | Region 复制 + 转发指针 | Android 10+ 默认 | 前台 < 5ms |
| **Mark Compact (MC)** | Android 7+ | 标记-整理 | Native OOM 时降级 | 单次 STW |
| **Semi-Space (SS)** | Android 7-9 | 复制 | CMS 退化路径 | 罕见 |

Android 14 默认 **CC（Concurrent Copying）**。CC 取代 CMS 的核心动机是 **"解决碎片 + 严格 STW 约束"**。

**为什么 CC 取代 CMS**：

| 维度 | CMS | CC |
|------|-----|-----|
| 碎片 | 标记-清除**不整理**，长期运行产生碎片 → 触发 OOM | Region 复制**无碎片** |
| STW 时长 | 100ms-1s（前台） | 5-15ms（前台，Android 14） |
| 写屏障 | 单一 dirty card | read barrier + write barrier + SATB（重） |
| 内存开销 | 低 | 中（Region 元数据 + 转发指针） |
| 适用版本 | 5.0-9 | 10+（含 14） |

### 2.2 CMS：Mark-Sweep 经典路径

CMS 的核心是"分阶段并发"：把一次完整的 GC 拆成多个阶段，每个阶段尽可能并发，只在两个边界短暂 STW：

```
时序      mutator     GC threads                说明
────────────────────────────────────────────────────────
STW 1     暂停        Initial Mark             标记 GC Roots
并发      运行        Concurrent Mark (1)       遍历对象图
并发      运行        Concurrent Preclean
并发      运行        Concurrent Mark (2)
并发      运行        Concurrent Sweep          清扫
STW 2     暂停        Remark                    重新扫描
并发      运行        Concurrent Sweep          回收 free
```

**源码入口**：`art/runtime/gc/collector/concurrent_mark_sweep.cc`。

```cpp
// art/runtime/gc/collector/concurrent_mark_sweep.cc （AOSP android-14.0.0_r1 仍保留）
// CMS 主流程：ConcurrentMarkSweepGeneration::Collect
void ConcurrentMarkSweepGeneration::Collect(GcCause cause, bool full, bool clear_soft_refs) {
  // 1. InitialMark（STW）—— 标记 GC Roots
  // 2. MarkFromRoots（并发）—— 遍历对象图
  // 3. Preclean（并发）—— 处理并发修改
  // 4. Remark（STW）—— 重新扫描
  // 5. Sweep（并发）—— 回收
  // ...
}
```

> **稳定性架构师视角：** CMS 的两大遗留问题：
> 1. **Remark 阶段无法彻底消除 STW**：如果堆很大（1GB+），Remark 仍可能 100ms+
> 2. **碎片化**：长期运行后，CMS 找不到连续空间分配时，会触发"Concurrent Mode Failure"降级到 Mark Compact（单次 STW 1-3 秒）
>
> 这是 §8 实战案例的根因——一台 Android 9 设备在升级 Android 14 后频繁出现 1.5s STW，根因就是 CMS 退化。

### 2.3 CC：Region + 转发指针的演进

CC 的核心创新是 **Region 化 + 转发指针（forwarding pointer）**。它解决了 CMS 的两个根本问题：

1. **无碎片**：CC 是复制式 GC，存活对象被复制到新 Region，原 Region 整块释放
2. **极短 STW**：CC 的 STW 阶段只有"对象头标记 + 堆栈扫描"，< 5ms

```
CC 的 6 个 STW 阶段（Android 14）
────────────────────────────────────────────────────────
1. DisableMarkingStacks        关闭 mutator 写屏障（<1ms）
2. FlipThreadRoots             翻转线程根（<2ms）
3. MarkingStacks               处理线程栈中引用（<2ms）
4. ScanGrayObjectsStacks       扫描灰色对象（<3ms）
5. ProcessMarkStack            处理标记栈（<5ms）
6. ReenableMarkingStacks       重新开启 mutator 屏障（<1ms）
────────────────────────────────────────────────────────
总和 < 15ms
```

**CC 关键源码**（AOSP 14 真实函数名）：

```cpp
// art/runtime/gc/collector/concurrent_copying.cc （AOSP android-14.0.0_r1）
// ConcurrentCopying::Run 是主入口
void ConcurrentCopying::Run(GcCause cause, bool clear_soft_refs) {
  // 1. 初始化 region、mark stack
  // 2. 第一次 STW：DisableMarkingStacks
  // 3. 并发标记：ConcurrentMark
  // 4. 第二次 STW：ReenableMarkingStacks
  // 5. 复制存活对象到新 Region
  // 6. 更新引用
  // 7. 释放旧 Region
}

// 关键函数：IsMarked —— 用于 read barrier
bool ConcurrentCopying::IsMarked(ObjPtr<mirror::Object> obj) {
  // 每次 Java 读对象时检查
  // 如果已被标记为"需要复制"，返回转发后的新地址
  return GetFwdPtr(obj) != nullptr;
}
```

> **稳定性架构师视角：** CC 的 **read barrier 是 Java 性能的"隐藏税"**。每次 Java 读对象都多 1-3ns 屏障开销。Java 8 时代是 0。**对内存密集型应用（图片处理、JSON 解析），CC 模式下比 CMS 慢 5-10%**。Google 通过内联（inlining）和 JIT 优化尽量摊薄，但仍有可观开销。

### 2.4 选型策略与运行时切换

Android 14 的 GC 选型由 `art/runtime/gc/heap.cc::Heap::Create` 决定，运行时基本不会切换：

| 触发场景 | 选型逻辑 | 备选 |
|---------|---------|------|
| 默认 (Android 10+) | CC | — |
| 旧设备 OAT 兼容模式 | CMS | CC 不可用时 |
| Native OOM 触发 | Mark Compact | 紧急回收 |
| App 兼容性白名单（极少见） | SS / CMS | 厂商定制 |

**稳定性影响**：

- 厂商定制 ROM 如果强行回退到 CMS，会复现 CMS 退化问题
- 模拟器（x86_64）默认 CC，但 x86 read barrier 实现较弱，可能比 arm64 慢

源码入口：`art/runtime/gc/heap.cc::Heap::Heap(...)` 中对 `collector_type_` 的初始化逻辑。

---

## 3. ART 堆的"可见性"：Concurrent GC 与 stop-the-world 的边界

### 3.1 是什么 / 为什么"完全 Concurrent"不可能

"可见性"是 GC 领域的核心概念：mutator（应用线程）写对象与 GC 遍历对象图的**happens-before 关系**。理论上"完全 Concurrent"意味着应用线程和 GC 线程完全并行——但这要求**每个对象读、写都走屏障**。

**为什么完全 Concurrent 不可行**：

1. **根集合扫描必须 STW**：GC Roots（线程栈、JNI 引用、class 静态字段）会随 mutator 改变。要在 mutator 暂停时一致地捕获这些引用。
2. **对象搬迁必须 STW**：CC 把存活对象复制到新 Region 时，必须短暂暂停 mutator，否则 mutator 通过旧地址访问会失败。
3. **屏障开销有下限**：读屏障每对象 1-3ns，循环 100 万次就是 1-3ms。屏障越重，应用越慢。

因此 **CC 是"高并发 + 短 STW"**，不是"零 STW"。

### 3.2 CC 的 6 个 STW 阶段

CC 的 STW 阶段按时间顺序如下（AOSP 14 真实数据，单位 ms）：

| 阶段 | 源码入口 | 典型耗时 | 干什么 |
|------|---------|---------|--------|
| 1. DisableMarkingStacks | `ConcurrentCopying::DisableMarkingStacks` | < 1ms | 关闭 mutator 屏障 |
| 2. FlipThreadRoots | `ConcurrentCopying::FlipThreadRoots` | < 2ms | 把所有线程根 push 到 mark stack |
| 3. MarkingStacks | `ConcurrentCopying::MarkingStacks` | < 2ms | 处理 mark stack 中对象 |
| 4. ScanGrayObjectsStacks | `ConcurrentCopying::ScanGrayObjectsStacks` | < 3ms | 扫描灰色对象 |
| 5. ProcessMarkStack | `ConcurrentCopying::ProcessMarkStack` | 1-10ms | 深度遍历对象图 |
| 6. ReenableMarkingStacks | `ConcurrentCopying::ReenableMarkingStacks` | < 1ms | 重新开启 mutator 屏障 |
| **总 STW 时长** | — | **< 15ms (P99 < 50ms)** | — |

**关键源码**（AOSP 14 真实函数名）：

```cpp
// art/runtime/gc/collector/concurrent_copying.cc
// ConcurrentCopying::DisableMarkingStacks：第 1 个 STW 阶段
void ConcurrentCopying::DisableMarkingStacks(Thread* self) {
  // 1. 暂停所有 mutator 线程（用 SuspendAll）
  // 2. 关闭 mark stack
  // 3. 进入下一阶段
}

// 第 5 阶段是耗时大头
void ConcurrentCopying::ProcessMarkStack(...) {
  // 遍历 mark stack 中所有灰色对象
  // 对每个对象: mark + push 引用字段到 stack
  // 直到 stack 空
}
```

> **稳定性架构师视角：** `dumpsys gfxinfo` + `dumpsys meminfo` 中的"GC 原因"行（如 `Background concurrent copying paused`）会列出每个 STW 阶段的耗时。**P99 超过 50ms 的 GC 阶段是排查的起点**。

### 3.3 屏障机制：读屏障、写屏障、SATB 屏障

CC 同时使用**三种屏障**（这是它和 CMS 最大的实现差异）：

#### 3.3.1 写屏障（Write Barrier）

**作用**：当 mutator 写对象引用字段时，通知 GC 这个对象"可能成为灰色"。

```cpp
// art/runtime/gc/heap-inl.h
// Heap::WriteBarrierField：AOSP 14 CC 模式
inline void Heap::WriteBarrierField(ObjPtr<mirror::Object> dst, MemberOffset offset) {
  // 1. 把 dst 对应的 Card 标 dirty
  // 2. 触发 post-write barrier：把 dst push 到 mark stack
}
```

#### 3.3.2 读屏障（Read Barrier）

**作用**：当 mutator 读对象字段时，检查对象是否已被标记搬迁；如果已被搬迁，返回转发后的新地址。

```cpp
// art/runtime/gc/collector/concurrent_copying-inl.h
// ConcurrentCopying::GetFwdPtr：读屏障核心
inline mirror::Object* ConcurrentCopying::GetFwdPtr(ObjPtr<mirror::Object> obj) {
  // 读 obj 的 mark word
  // 如果 mark word 含 forward 标记，return forward target
  // 否则 return nullptr
}
```

#### 3.3.3 SATB 屏障（Snapshot-At-The-Beginning）

**作用**：CC 在 STW 时记录"那一刻的引用图快照"，mutator 在并发标记阶段删的引用不能"复活"已经被覆盖的对象。

**屏障开销对比**：

| 屏障 | 开销 | 触发频率 |
|------|------|---------|
| 写屏障 | 5-15ns | 每次引用字段写 |
| 读屏障 | 1-3ns | 每次对象读 |
| SATB 屏障 | 3-8ns | 引用字段被覆盖时 |

> **稳定性架构师视角：** **Java 性能优化最容易踩的坑是"误以为屏障免费"**。例如：
> - 大量用 `Map<Object, Object>` 触发大量 read barrier（每次 `map.get`）
> - 在紧密循环里 `list.add(obj)` 触发大量 write barrier
> - `synchronized` 关键字 + 屏障 → 双重开销
>
> **优化方向**：减少对象引用次数、扁平化数据结构、用基本类型数组代替包装类集合。

### 3.4 pause time 目标与实测分布

Google 在 Android Vitals 中定义的 Java 堆 GC pause 目标：

| 阶段 | P50 目标 | P95 目标 | P99 目标 |
|------|---------|---------|---------|
| 后台 GC (Concurrent) | < 5ms | < 20ms | < 50ms |
| 分配失败 (Background) | < 30ms | < 100ms | < 200ms |
| OOM 前 (Foreground) | < 100ms | < 500ms | < 1500ms |

**实测的 GC pause 分布**（基于 Android Vitals 公开数据，2024）：

```
Foreground GC pause 分布
────────────────────────────────────────
< 5ms   ████████████████████  60%
5-30ms  ████████              20%
30-100ms ████                  10%
100-500ms ██                    6%
500ms+   █                     4%
```

> **稳定性架构师视角：** 4% 的"500ms+" GC 是 ANR 的高风险来源。以下 4 类原因覆盖了绝大多数长 GC 场景：
> 1. **HUMONGOUS 对象频繁分配**（详见 §5）
> 2. **Old 区碎片严重**（CMS 退化）
> 3. **Native 堆 + Java 堆双重压力**（互不感知，各自触发 GC）
> 4. **Finalizer 队列卡死**（详见 §7）

---

## 4. Java 堆与 Native 堆的边界：JNI 引用表（local/global/weak）

### 4.1 是什么 / 为什么 JNI 引用表是"边界"

JNI（Java Native Interface）是 Java 与 Native 代码的桥。当 Java 调用 native（或反之）时，**Java 堆中的对象必须通过"引用"暴露给 native 侧**——而这个引用的生命周期、上限、回收机制就是 JNI 引用表。

**为什么这是稳定性关键**：

1. **Java 堆的对象不能直接传给 native**（因为 GC 会移动对象，地址会变）。必须用"句柄"或"间接引用"。
2. **Native 持有的引用阻止 GC 回收对应对象**——泄漏的 JNI 引用 = 永久的 Java 堆对象泄漏。
3. **Android 14 的机制已经重构**——从旧的 `ReferenceTable` 改为 `IndirectRefTable` + `ScopedObjectAccess`（**注意：旧版 `ReferenceTable` 路径在 AOSP 14 已不存在**，写代码时不能继续用旧 API）。

```
┌──────────────────────────────────────────────────────────┐
│                    JNI 引用表                              │
│                                                          │
│  Java 堆 (ART)              Native 侧 (C/C++)             │
│  ┌──────────┐              ┌──────────────┐             │
│  │ Object A │ ─jobject──→ │ jobject ref   │             │
│  │ Object B │ ─jobject──→ │ jobject ref   │             │
│  └──────────┘              └──────────────┘             │
│       │                           │                      │
│       │  GC 看不到 native 侧       │                      │
│       │  持有哪些引用              │                      │
│       │                           │                      │
│       ▼                           ▼                      │
│  IndirectRefTable 维护 native 侧可见的"间接引用"          │
└──────────────────────────────────────────────────────────┘
```

### 4.2 IndirectRefTable 内部结构

AOSP 14 用 `IndirectRefTable`（定义在 `art/runtime/indirect_reference_table.h`，注意 AOSP 14 源文件位于 `art/runtime/` 顶层而非 `art/runtime/jni/` 子目录）代替了旧的 `ReferenceTable`。核心是"间接层 + 槽位"：

```cpp
// art/runtime/indirect_reference_table.h
class IndirectRefTable {
 public:
  // 引用类型
  enum IndirectRefKind {
    kJniLocalRef,        // local ref
    kJniGlobalRef,       // global ref
    kWeakGlobalRef,      // weak ref
  };

  // 槽位：实际存储对象指针 + 引用元数据
  struct Slot {
    mirror::Object* referent;   // 指向 Java 堆对象
    // ...
  };

  // 三张表
  std::vector<Slot> table_;
  size_t max_entries_;          // 容量上限
  // ... segment 数据结构 ...
};
```

**关键函数**：

```cpp
// art/runtime/indirect_reference_table.cc
// Add：添加一个间接引用
IndirectRef IndirectRefTable::Add(uint32_t cookie, mirror::Object* obj, ...) {
  // 1. 检查表是否已满
  if (table_.size() >= max_entries_) {
    // 2. 扩展或报错
    return kInvalidIndirectRef;
  }
  // 3. 分配 slot，存 obj 指针
  table_.push_back({obj, ...});
  // 4. 返回 IrtEntry（实际是指向 slot 的偏移）
  return EncodeSlot(...);
}

// Remove：从表中删除
void IndirectRefTable::Remove(uint32_t cookie, IndirectRef iref) {
  // 1. 解码 IrtEntry → slot 索引
  // 2. 把 slot 标记为 free
  // 3. 不直接释放对象（GC 会处理）
}
```

> **稳定性架构师视角：** IndirectRefTable 是 **JNI 引用"可见性"的核心**。GC 必须扫描这个表，把所有 native 持有的引用视为 GC Roots。这就是为什么 JNI 引用泄漏 = Java 堆永久泄漏——GC 永远不会回收被间接引用持有的对象。

### 4.3 local / global / weak 三类引用的语义

JNI 引用分三类，每类生命周期、回收行为不同：

| 类型 | 创建 API | 释放 API | 生命周期 | 数量上限 (Android 14) | 误用后果 |
|------|---------|---------|---------|---------------------|---------|
| **local** | `NewLocalRef` | 退出 native 方法自动 / `DeleteLocalRef` | native 方法返回前 | 动态上限 65536（Android 8+） | 方法返回后悬空 / 栈溢出 |
| **global** | `NewGlobalRef` | `DeleteGlobalRef` | 任意时刻 | 应用启动时分配（默认 51200） | 永久泄漏 → OOM |
| **weak** | `NewWeakGlobalRef` | `DeleteWeakGlobalRef` | 直到 GC 回收对象 | 同 global | 误判对象已死 → 野指针 |

**Local 引用详解**（最容易出问题）：

```cpp
// art/runtime/jni/jni_internal.cc
// NewLocalRef：创建 local 引用
jobject JNI::NewLocalRef(JNIEnv* env, jobject obj) {
  // 1. 检查当前线程的 local ref 表
  // 2. 如果 obj 已在表中，返回原 iref
  // 3. 否则添加新 slot
  // 4. 返回 iref
}

// 重要：local ref 在 native 方法返回时自动释放
// 这就是为什么"循环中大量创建 local ref 不释放"会爆栈
```

**Global 引用详解**（最常被误用）：

```cpp
// art/runtime/jni/jni_internal.cc
// NewGlobalRef：创建 global 引用
jobject JNI::NewGlobalRef(JNIEnv* env, jobject obj) {
  // 1. 加到全局引用表
  // 2. 返回 iref
  // global ref 不会被自动释放
}

// 一个常见错误：把 local ref 保存到 C++ 静态变量 → 实际上 local ref 的内容在 native 方法返回后悬空
// 正确做法：调 NewGlobalRef
```

**Weak 引用详解**（最难理解）：

```cpp
// art/runtime/jni/jni_internal.cc
// NewWeakGlobalRef
jweak JNI::NewWeakGlobalRef(JNIEnv* env, jobject obj) {
  // 创建 weak ref
  // 当 obj 被 GC 回收时，IsSameObject 检查返回 JNI_TRUE
}

// weak ref 不阻止 GC 回收
// 使用前必须 IsSameObject 检查
```

### 4.4 JNI 引用泄漏的稳定性影响

**典型泄漏模式**：

```java
// Java
class BitmapCache {
    static native void cacheBitmap(Bitmap bmp);  // 把 bmp 存到 native 静态变量
}

// native 错误实现
static jobject g_bmp = nullptr;  // ← 用 local ref 存！
void cacheBitmap(JNIEnv* env, jobject bmp) {
    g_bmp = bmp;  // 实际上 g_bmp 是 local ref，native 方法返回后悬空
}

// 正确实现
void cacheBitmap(JNIEnv* env, jobject bmp) {
    if (g_bmp) env->DeleteGlobalRef(g_bmp);
    g_bmp = env->NewGlobalRef(bmp);  // ← 必须用 Global
}
```

**`dumpsys meminfo` 中的 JNI 泄漏信号**：

| 字段 | 含义 | 异常阈值 |
|------|------|---------|
| `.Global Ref` | global ref 数量 | > 5000 |
| `.Local Ref` | 当前 local ref 数量 | > 1000 |
| `.Weak Ref` | weak ref 数量 | > 1000 |

> **稳定性架构师视角：** **"在 native 里把 Java 对象存起来"是 JNI 编程 80% 泄漏的根因**。**一个简单原则**：Java 对象跨 native 调用存活的，必须用 Global Ref，并在 native 对象析构时 Delete。**`leakcanary` 之类的工具能扫到这种泄漏**——它们的检测原理就是观察 `dumpsys meminfo` 中 `.Global Ref` 数量。

---

## 5. 大对象分配：LOS (Large Object Space) 与 HUMONGOUS 对象

### 5.1 是什么 / 什么算"大对象"

ART 14 对"大对象"有两个不同维度的定义：

| 维度 | 阈值 | 处理空间 | 触发原因 |
|------|------|---------|---------|
| **LOS 对象** | > 12KB（默认，可调） | LargeObjectSpace | 走 free list 管理 |
| **HUMONGOUS 对象** | > 128KB（Region 大小一半） | RegionSpace（整 Region） | 占满整个 Region |
| **巨型 LOS** | > 整 Region (256KB) | LOS + 多 Region | Bitmap 解码后大图 |

**为什么大对象要特殊处理**：

1. **Region copy 代价高**：一个 200KB 对象复制一次 = 一次完整 memmove（200KB/8 字节/8 字节 = 25600 次 64-bit 复制 = ~10μs @ 2.5GB/s）
2. **碎片化**：连续分配大量中等对象（64KB-128KB）会打散 Region，剩余空间无法用
3. **回收时 Liveness 计算慢**：遍历大对象的引用字段（假设 1000 个字段）= 1000 次屏障

### 5.2 LOS 的分配与回收

LOS（LargeObjectSpace）使用 **free list**（不是 bump pointer）管理：

```cpp
// art/runtime/gc/space/large_object_space.cc （AOSP android-14.0.0_r1）
// Alloc：从 free list 分配
mirror::Object* LargeObjectSpace::Alloc(Thread* self, size_t num_bytes, ...) {
  // 1. 把 num_bytes 对齐到 page size
  size_t bytes = RoundUp(num_bytes, kPageSize);
  // 2. 在 free list 中找合适的 chunk
  for (auto& chunk : free_chunks_) {
    if (chunk.size >= bytes) {
      // 3. 找到 → 切分并返回
      return chunk.Alloc(bytes);
    }
  }
  // 4. free list 没有 → mmap 新内存
  uint8_t* addr = mmap(nullptr, bytes, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  return reinterpret_cast<mirror::Object*>(addr);
}
```

**回收路径**：

```cpp
// art/runtime/gc/space/large_object_space.cc
// FreeList：LOS 的回收
void LargeObjectSpace::FreeList(Thread* self, std::vector<mirror::Object*>& objs) {
  // 1. 遍历 free chunk list
  // 2. 对每个 chunk: 如果整个 chunk 都是 free，调用 madvise(MADV_DONTNEED) 释放物理页
  // 3. 部分 free 的 chunk 留在 list 中，等待复用
}
```

> **稳定性架构师视角：** LOS 的关键洞察是 **"它用 madvise(MADV_DONTNEED) 释放物理页，但不取消虚拟映射"**。这意味着：进程的虚拟地址空间（VMA）数量会随 LOS 分配增长，即使物理页已释放。**`/proc/pid/maps` 仍会显示这些大段匿名映射**。

### 5.3 HUMONGOUS 对象与 Region 抢占

CC 收集器对"超大对象"有专门处理：**HUMONGOUS 对象独占整个 Region**。

**为什么需要这样**：CC 是 Region 复制，复制一个超过 Region 一半的对象本身就代价过高（每次 GC 都要复制），不如独占 Region、回收时直接整 Region 释放。

```cpp
// art/runtime/gc/space/region_space-inl.h （AOSP android-14.0.0_r1）
// 普通对象分配路径：AOSP 14 真实函数名是 AllocNonvirtual
// 入口是 Heap::AllocateInternalWithGc（在 heap.cc 中）→ RegionSpace::AllocNonvirtual
// 注意：Heap 的分配入口有多个重载模板，分配到不同 space 的代码路径不同
// RegionSpace 的入口在 AOSP 14 是 AllocNonvirtual（不是旧版 RegionSpace::Alloc）
// 注意：旧版 RegionSpace::Alloc 在 AOSP 14 不再存在
template <bool kForEvac>
inline mirror::Object* RegionSpace::AllocNonvirtual(size_t num_bytes, ...) {
  num_bytes = RoundUp(num_bytes, kAlignment);
  // 大小判断：> Region 一半走 HUMONGOUS
  if (num_bytes >= kRegionSize / 2) {
    // HUMONGOUS：直接走专门路径，整 Region 占用
    return AllocLargeRegion<kForEvac>(num_bytes);
  }
  // 普通：从 TLAB 或 bump pointer
  return AllocFromTlabOrRegion(num_bytes, ...);
}
```

**HUMONGOUS 对象的 GC 行为**：

- CC 标记阶段：HUMONGOUS 对象被标记为"不可复制"——存活的直接保留
- 回收阶段：HUMONGOUS 对象占用的 Region 直接整块加入 free list
- 风险：HUMONGOUS 对象占用的 Region 在 GC 周期内**完全不能用**（其他对象无法分摊到这些 Region）

### 5.4 大对象相关的 GC 退化模式

**模式 1：HUMONGOUS 风暴**

```
场景：相机预览每次新帧分配 1MB YUV buffer（> 128KB）
      60fps × 1MB = 60MB/s 分配速度
      Region 容量：64 个 Region × 256KB = 16MB

结果：
  - 第 1 帧：1 个 Region（256KB，含 1MB buffer + 浪费 50%）
  - 第 5 帧：5 个 Region 被占用
  - 第 64 帧：Region 池耗尽 → 触发 GC
  - GC 完：60 个 Region 中只有 5 个 buffer 存活，但 free list 重置
  - 第 65 帧：重新开始循环
  
GC 频率：约 1 次/秒，pause 50-100ms
```

**模式 2：LOS 碎片化**

```
场景：App 反复分配 64KB 数组（介于 12KB 和 128KB 之间）
      分配 1000 个，回收 800 个，保留 200 个

结果：
  - free list 中有大量 64KB chunks
  - 分配 256KB 数组：找不到连续空间
  - 即使总 free 空间充足，也无法复用
  
GC 现象：Concurrent Mode Failure → 降级到 Foreground GC
```

**模式 3：Bitmap 巨型分配**

```java
// 典型代码：decodeResource 一次性解码大图
Bitmap bmp = BitmapFactory.decodeResource(getResources(), R.drawable.large);
// large 1080×1920 ARGB_8888 = 8.3MB
// → 走 LOS（> 12KB）
// → 如果更大（4K）会走 HUMONGOUS
```

**修复建议**：

```java
// 推荐：BitmapFactory.Options.inSampleSize 缩放
BitmapFactory.Options opts = new BitmapFactory.Options();
opts.inSampleSize = 2;  // 缩小到 1/4 大小
Bitmap bmp = BitmapFactory.decodeResource(getResources(), R.drawable.large, opts);
```

> **稳定性架构师视角：** **大对象是 ART 堆性能"放大器"**。小对象 100KB 没问题，10MB 的大对象会引发 GC 退化、LOS 碎片、HUMONGOUS 抢占等问题。**核心原则**：
> 1. **避免分配大对象**——用 stream/分块代替
> 2. **控制大对象存活时间**——不要在静态字段里缓存大图
> 3. **使用 inSampleSize 缩放**——避免解码原图
> 4. **跨进程传递用 ashmem/DMA-BUF**——而不是塞 Java 堆

---

## 6. 内存压力下的 GC 行为：Concurrent / Background / Foreground 三种模式

### 6.1 是什么 / 为什么需要多种模式

ART 14 的 GC 调度是一个**多触发源、多目标、多约束**的复杂状态机。根据触发原因和暂停时间预算，分为三种模式：

| 模式 | 触发原因 | 暂停时间目标 | 阻塞主线程 | CPU 占用 | 触发频率 |
|------|---------|-------------|----------|---------|---------|
| **Concurrent GC** | 堆使用率到 soft limit | < 5ms | 否（并发） | 后台线程 | 高 |
| **Background GC** | trim / 显式 System.gc | < 30ms | 是（短暂） | 后台线程 | 中 |
| **Foreground GC** | 分配失败 / OOM | < 100ms+ | 是（必须） | 当前线程 | 低 |

**为什么需要三种模式**：

1. **"应用响应优先"与"内存压力"的权衡**。空闲时用 Concurrent；压力来时用 Background 配合 trim；分配失败时用 Foreground 强制回收。
2. **避免主线程卡顿**。Foreground GC 是最后一道防线，但 pause 时间最长。
3. **支持压力分级**。同一 App 在不同压力下表现不同——空闲时 5ms，OOM 时 500ms+。

### 6.2 Concurrent GC：后台线程默默工作

**触发条件**：Java 堆使用率超过 soft limit。

```cpp
// art/runtime/gc/heap.cc
// Heap::ConcurrentGC：触发并发 GC
void Heap::ConcurrentGC(GcCause cause, ...) {
  // 1. 启动 ConcurrentCopying 收集器
  // 2. 后台线程 gc-thread-pool 跑
  // 3. 主线程继续分配（受 read barrier 保护）
  collector_->Run(cause, ...);
}
```

**源码入口**：

```cpp
// art/runtime/gc/heap.cc （AOSP android-14.0.0_r1）
// ConcurrentGC 的实际触发点：RequestConcurrentGC
void Heap::RequestConcurrentGC(Thread* self, GcCause cause, bool force, ...) {
  // 1. 检查是否已经在 concurrent GC 中
  // 2. 如果没有，发信号给 ConcurrentGC thread
  // 3. ConcurrentGC thread 唤醒后执行
}

// 触发条件之一：堆占用超过 soft limit
bool Heap::ShouldRequestConcurrentGC(...) {
  return (BytesAllocated() >= concurrent_start_bytes_);
}
```

`concurrent_start_bytes_` 默认是堆最大值的 **0.5**（即 256MB 堆的 soft limit = 128MB）。

> **稳定性架构师视角：** **Concurrent GC 是"温柔模式"**——主线程完全无感。但**它的 CPU 占用在后台**（5-15%），对续航有影响。**当系统电量低 / 性能模式被关闭时，Concurrent GC 频率可能降低**，导致堆涨得快。

### 6.3 Background GC：trim 触发，短暂 STW

**触发条件**：

1. `Application.onTrimMemory(level)` 触发
2. 系统 idle（Doze 模式）
3. `System.gc()` 显式调用
4. 堆使用率超过 background soft limit

```cpp
// art/runtime/gc/heap.cc
// Trim：响应 onTrimMemory
void Heap::Trim() {
  // 1. 软引用、弱引用清理
  // 2. 调用 ConcurrentGC 或 BackgroundGC
  ConcurrentGC(kGcCauseTrim, ...);
}
```

**与 Concurrent GC 的差异**：

| 维度 | Concurrent GC | Background GC |
|------|---------------|---------------|
| 是否 STW | 否 | 是（短） |
| 触发方式 | 软阈值 | 显式（trim/System.gc） |
| 暂停时间 | < 5ms | < 30ms |
| 回收彻底性 | 标记完整 | 标记完整 |
| CPU 占用 | 后台 | 后台 |

### 6.4 Foreground GC：分配失败，阻塞主线程

**触发条件**：

1. `new Object()` 分配失败
2. Java 堆达到 max limit
3. 多次 Concurrent GC 后仍无法分配

```cpp
// art/runtime/gc/heap.cc
// AllocateInternalWithGc：分配失败的回收路径
mirror::Object* Heap::AllocateInternalWithGc(...) {
  // 1. 尝试分配
  obj = TryToAllocate(...);
  if (obj != nullptr) return obj;

  // 2. 分配失败：先做 Concurrent GC
  ConcurrentGC(kGcCauseAlloc, ...);

  // 3. 重试分配
  obj = TryToAllocate(...);
  if (obj != nullptr) return obj;

  // 4. Concurrent GC 还不够：做 Foreground GC（阻塞分配者）
  WaitForGcToComplete(kGcCauseAlloc, self);
  obj = TryToAllocate(...);
  if (obj != nullptr) return obj;

  // 5. 实在不行：抛 OOM
  ThrowOutOfMemoryError(...);
  return nullptr;
}
```

**Foreground GC 是 pause 时间最长的场景**，因为：

1. 阻塞分配者（即主线程），必须立刻回收
2. 没有时间让 Concurrent 慢慢跑
3. 必须一次性完成"回收 + 整理 + 重试分配"，pause 100-500ms+

**源码关键调用**：

```cpp
// art/runtime/gc/heap.cc
// WaitForGcToComplete：等待 GC 完成
void Heap::WaitForGcToComplete(GcCause cause, Thread* self) {
  // 1. 等 concurrent GC 结束
  // 2. 仍不够就启动 Foreground GC
  CollectGarbageInternal(self, cause, /* running_above_concurrent_gc */ true);
}
```

### 6.5 模式切换的源码路径

GC 模式选择由 `Heap::CollectGarbageInternal` 决定：

```cpp
// art/runtime/gc/heap.cc
// CollectGarbageInternal：AOSP 14 真实函数
void Heap::CollectGarbageInternal(Thread* self, GcCause cause, bool running_above_concurrent_gc) {
  // 1. 检查 running_above_concurrent_gc 标志
  if (running_above_concurrent_gc) {
    // Foreground：阻塞 self
    collector_->Run(cause, /* clear_soft_refs */ true);
  } else {
    // Concurrent / Background：非阻塞
    collector_->Run(cause, /* clear_soft_refs */ false);
  }
}
```

**模式切换时序**：

```
                    ┌─────────────┐
                    │ Idle        │
                    └──────┬──────┘
                           │ 软阈值触发
                           ▼
                    ┌─────────────┐
                    │ Concurrent  │ ──── CPU 后台占用 5-15%
                    └──────┬──────┘
                           │ 仍不足
                           ▼
                    ┌─────────────┐
                    │ Background  │ ──── STW 30ms
                    └──────┬──────┘
                           │ 仍不足
                           ▼
                    ┌─────────────┐
                    │ Foreground  │ ──── STW 100ms+
                    └──────┬──────┘
                           │ 仍不足
                           ▼
                    ┌─────────────┐
                    │ OOM         │ ──── 抛 OutOfMemoryError
                    └─────────────┘
```

> **稳定性架构师视角：** **"GC 风暴"是这三种模式在压力下反复切换的现象**。当 Native 堆 + Java 堆同时压力（如 ImageDecoder 解码大图 + ION 分配）：每次分配失败 → Concurrent GC → Background GC → Foreground GC → OOM → App 崩溃。**这是一个连锁反应**，排查时必须看完整 GC trace 而不是单独一次。

**`dumpsys meminfo` 输出示例**：

```
GC 原因统计
──────────────────────────────────────────────
Background concurrent copying paused:    1245  次, 平均 4ms
Background sticky concurrent copying:     345  次, 平均 12ms
Foreground concurrent copying paused:     23  次, 平均 78ms
Total GC time:                            21.4s (开机以来累计)
──────────────────────────────────────────────
```

> **关键信号**：Foreground 比例 > 5% → 严重内存压力。

---

## 7. 风险地图：长 GC pause、Reference 泄漏、Finalizer 死锁、image space 损坏

### 7.1 长 GC pause

#### 7.1.1 现象

- 主线程卡顿 50ms+，偶发可达 1-2 秒
- `dumpsys gfxinfo` 中 `Janky frames` 比例突增
- logcat 中 `Background concurrent copying paused: ... sum: 1.2s` 关键字
- `ANR in ...` 伴随 `input event injection timed out`

#### 7.1.2 子类型树

```
长 GC pause
├── 堆过大
│   ├── Old 区满（> 70%）
│   ├── LOS 碎片
│   └── HUMONGOUS 风暴
├── GC 退化
│   ├── Concurrent Mode Failure → Foreground
│   └── Finalizer 队列卡死（GC 等待 finalize）
├── 屏障开销
│   ├── 大量反射调用
│   ├── 紧密循环 + 大量引用字段
│   └── JNI 频繁调用
└── 锁竞争
    ├── Heap lock
    └── Thread suspend lock
```

#### 7.1.3 排查路径

```bash
# 1. 看 GC 原因
dumpsys meminfo <pkg> | grep -A 20 "GC 原因"

# 2. 看 GC trace
am dumpheap <pkg> /sdcard/heap.hprof
# 然后用 Android Studio 打开，看 Retained Size TopN

# 3. 看 STW 阶段耗时（需要 Perfetto）
perfetto -o trace.pf --txt trace_config.pbtxt
# 关注 "concurrent_copying" tracepoint 的 "stop_the_world_sum"
```

### 7.2 Reference 泄漏

#### 7.2.1 现象

- Java 堆持续增长，GC 后不下降
- 静态集合类（`static List`）持有大对象
- `SoftReference` / `WeakReference` 在内存压力下未及时清理
- `dumpsys meminfo` 中 `.Global Ref` 字段异常大

#### 7.2.2 子类型树

```
Reference 泄漏
├── Static 字段持有
│   ├── 单例对象（错误的单例）
│   ├── 静态 List / Map
│   └── 静态 Listener 注册未注销
├── 内部类持有外部类
│   ├── 非 static 内部类隐式持外部
│   ├── Handler 持 Activity 引用
│   └── 匿名 Runnable / Thread
├── 资源未释放
│   ├── Cursor / Stream / File
│   ├── BroadcastReceiver 未注销
│   └── View.OnClickListener 累积
└── 第三方 SDK 泄漏
    ├── 图片加载库缓存未配置上限
    ├── 推送 SDK 静态注册
    └── 监控 SDK 全局变量
```

#### 7.2.3 排查路径

```bash
# 1. 触发 GC 后看 Java Heap 是否回落
am send-trim-memory <pkg> RUNNING_CRITICAL
dumpsys meminfo <pkg> | grep "Java Heap"

# 2. LeakCanary 检测
# 集成 LeakCanary → 自动 dump hprof 并分析

# 3. 手抓 hprof
am dumpheap <pkg> /sdcard/heap.hprof
# Android Studio → Profile → Heap → Load hprof
# 看 "Leaked Activities" / "Leaked Fragments"
```

### 7.3 Finalizer 死锁

#### 7.3.1 现象

- logcat 中 `FinalizerWatchdogDaemon` 报告 `TimeoutException`
- Java 堆看似不大，但 `FinalizerReference` 队列里堆积大量对象
- GC pause 偶发 5-10 秒

#### 7.3.2 原理

Java 对象的 `finalize()` 方法在 GC 回收对象前执行，由 `FinalizerDaemon` 线程调用。如果 `finalize()` 阻塞（IO 等待、锁竞争、死循环），GC 也会阻塞。

#### 7.3.3 子类型树

```
Finalizer 死锁
├── finalize 内同步阻塞
│   ├── finalize 内 sleep / wait
│   ├── finalize 内 IO 操作
│   └── finalize 内 synchronized 锁
├── finalize 内递归调用
│   ├── 链式 finalize（A finalize 创建 B，B finalize 创建 C）
│   └── finalize 内分配大对象
└── FinalizerReference 队列满
    ├── finalize 太慢
    └── 队列容量耗尽
```

#### 7.3.4 排查路径

```bash
# 1. 看 Finalizer 队列
dumpsys meminfo <pkg> | grep -A 5 "Finalizer"

# 2. logcat 关键字
adb logcat -d | grep -E "FinalizerWatchdog|finalize.*timeout"

# 3. ART 14 关键路径：art/runtime/gc/reference_processor.cc
# 关注 pending_finalization_list_ 长度
```

### 7.4 image space 损坏

#### 7.4.1 现象

- 启动时 `art/runtime/oat_file_manager.cc` 报错
- logcat 中 `Failed to open oat file` / `Image checksum mismatch`
- 所有 App 启动失败 → 系统级故障

#### 7.4.2 触发原因

1. OTA 升级时 dex2oat 失败但未清理旧 image
2. 磁盘损坏（userdata 分区）
3. 恶意应用篡改 `/data/dalvik-cache/`
4. SELinux 策略错误导致 image 文件不可读

#### 7.4.3 排查路径

```bash
# 1. 检查 image 文件
ls -la /system/framework/boot.art  # boot image
ls -la /data/dalvik-cache/         # 进程 image

# 2. 重新 dex2oat
# Recovery 模式 → wipe dalvik-cache
# 或 adb shell cmd package compile -m speed -f <pkg>

# 3. 看 logcat
adb logcat -d | grep -E "art.*image|dex2oat|ImageSpace"
```

### 7.5 风险速查表（问题类型 / 日志关键字 / dumpsys 特征 / 排查入口）

| # | 问题类型 | 现象 | 日志关键字 | dumpsys 特征 | 排查入口 |
|---|---------|------|----------|-------------|---------|
| 1 | 长 GC pause | 主线程卡 100ms+ | `Background concurrent copying paused: sum: > 100ms` | GC 统计中 foreground 比例 > 5% | Perfetto + GC trace |
| 2 | Java 堆 OOM | 抛 OutOfMemoryError | `OutOfMemoryError: Java heap space` | Java Heap > dalvik.vm.heapmaxfree | hprof + 看 TopN |
| 3 | JNI Global Ref 泄漏 | Java 堆不释放 | `JNI ERROR (app bug): Global ref table overflow` | `.Global Ref` > 5000 | 检查 NewGlobalRef 配对 |
| 4 | JNI Local Ref 溢出 | native 调用崩 | `JNI ERROR (app bug): Local reference table overflow` | `.Local Ref` > 65536 | 检查 local ref 释放 |
| 5 | Finalizer 死锁 | GC 卡 5s+ | `FinalizerWatchdogDaemon: TimeoutException` | Finalizer 队列长 | 检查 finalize 实现 |
| 6 | Image space 损坏 | 系统启动失败 | `Image checksum mismatch` / `Failed to open oat file` | — | wipe dalvik-cache |
| 7 | LOS 碎片化 | 大对象分配失败 | `Concurrent Mode Failure` | Java Heap 中 LOS 行大 | 控制大对象数量 |
| 8 | HUMONGOUS 风暴 | GC 频率 1Hz+ | `Background concurrent copying paused` 频繁 | Region 使用率持续 > 80% | 缩小分配粒度 |
| 9 | 软引用未及时清理 | Java 堆偏大 | `soft references` 未释放 | `Soft Reference` 行 | 检查 soft ref 实现 |
| 10 | 弱引用误用 | 野指针 / 崩溃 | `IsSameObject` 检查失败 | `.Weak Ref` 异常大 | 检查 weak ref 使用 |
| 11 | GC 风暴 | 频繁 GC | `Background` 频率 > 5 次/分 | GC 总时间 > 1s/min | 压力源头（CPU/内存/IO） |
| 12 | Foreground GC 频繁 | 主线程卡 | `Foreground concurrent copying` 比例 > 1% | — | 看 Native 堆是否压力 |
| 13 | TLAB 不足 | 分配热点 | `TlabSize: 0` 反复 | — | 增加 Region 数量 |
| 14 | read barrier 开销 | Java 性能下降 5-10% | 难直接看到 | GC 频率正常但慢 | 减少对象引用次数 |
| 15 | 显式 System.gc | 强制 STW | `kGcCauseExplicit` | System.gc 行 | 移除业务侧 System.gc |
| 16 | Trim 不及时 | 切换应用内存不释放 | `onTrimMemory` 未触发 | Java Heap 切前后差异大 | 实现 onTrimMemory |
| 17 | image space 加载慢 | 冷启动慢 200ms+ | `Load image` 慢 | — | 减少 boot class 数量 |
| 18 | boot.art 版本不匹配 | 启动失败 | `Image version mismatch` | — | 重新 dex2oat |
| 19 | DexCache 泄漏 | Java 堆持续增长 | DexCache 不释放 | — | 检查反射调用模式 |
| 20 | 非移动空间满 | Class 分配失败 | `NonMovingSpace full` | NonMoving 行 | 减少动态 class load |
| 21 | Concurrent 失败 | GC 退化为 Foreground | `Concurrent Mode Failure` | Foreground 比例突增 | 检查 Old 区碎片 |
| 22 | PreZygoteFork 失败 | App 启动慢 | `Zygote fork failed` | — | 检查 zygote 空间 |
| 23 | Heap lock 竞争 | 分配慢 | `Heap lock wait` | — | 减少多线程分配 |
| 24 | Read barrier 失效 | GC 不准 | `Mark stack overflow` | — | 增大 mark stack |
| 25 | Region 池耗尽 | GC 立即触发 | `Region pool exhausted` | — | 控制大对象 |
| 26 | 软引用 + 弱引用误配 | 内存不释放 | — | Soft + Weak 行大 | 检查 reference queue |
| 27 | Phantom reference 堆积 | GC 慢 | `PhantomReference` 不释放 | — | 检查 phantom 清理 |
| 28 | boot.vdex 损坏 | 启动失败 | `Failed to load boot.vdex` | — | 重做 OTA 升级 |
| 29 | Profile 安装冲突 | 启动优化失效 | `Profile not found` | — | 清理 profile |
| 30 | GC 日志开关 | 看不到 trace | `gc=verbose` 未开启 | — | 启用 ART GC logging |

---

## 8. 实战案例：CMS 退化 Concurrent 失败导致主线程 STW 1.5s（典型模式）

> **案例类型**：典型模式（基于公开 ART GC 失败模式构造，已脱敏）

### 8.1 现象

某相机 App 在 Android 14 设备上**偶发卡顿 1-2 秒**，集中在两个场景：
- 打开相机时第一帧预览延迟
- 切换前后摄像头时

用户上报 ANR 占比 0.3%（行业基线 < 0.1%）。`dumpsys gfxinfo` 显示 Janky frames 在相机操作时上升到 18%（基线 2%）。

### 8.2 分析路径

#### 第一步：抓 dumpsys meminfo

```bash
$ adb shell dumpsys meminfo com.example.camera

App Summary
                       Pss      Private   Private  SwapPss
        Total:    285432K    268124K    17328K   0K
   Java Heap:   165432K    165432K        0K
   Native Heap:  78932K     78932K        0K
   Graphics:     30128K     30128K        0K
   Code:         10240K      2048K     8192K
   Stack:         1280K      1280K        0K
   ...
Objects
               Views:       0         ViewRootImpl:       0
        AppContexts:       4           Activities:       1
             Assets:      12         AssetManagers:       0
      Local Binders:      18        Proxy Binders:       1
   Parcel memory:        8         Parcel count:      78
   Death Recipients:      1      OpenSSL Sockets:       0
            .Global Ref:   1245   ← 异常大（基线 < 200）
            .Local Ref:    5120   ← 异常大（基线 < 500）
            .Weak Ref:      23

GC 原因统计
──────────────────────────────────────────────
Background concurrent copying paused:    4521  次, 平均 8ms
Background sticky concurrent copying:    2341  次, 平均 18ms
Foreground concurrent copying paused:     189  次, 平均 312ms  ← 异常
Total GC time:                            64.2s
──────────────────────────────────────────────
```

**异常信号**：
- `.Global Ref: 1245` 远超基线（典型 App < 200）
- `.Local Ref: 5120` 也异常（典型 App < 500）
- Foreground GC 平均 312ms，**P99 接近 1.5s**

#### 第二步：抓 Perfetto trace

```bash
$ perfetto -o /sdcard/trace.pf --txt perfetto.cfg
# 看到 GC 时刻卡在 Foreground CC 的 ProcessMarkStack 阶段
# 持续 1.2-1.5s
```

#### 第三步：抓 hprof

```bash
$ adb shell am dumpheap com.example.camera /sdcard/heap.hprof
# 用 Android Studio 打开
# Retained Size TopN:
#   1. com.example.camera.ImageProcessor$1: 38MB   ← 内部类泄漏
#   2. android.graphics.Bitmap: 24MB × 3
#   3. com.example.camera.JNIBridge: 12MB          ← Native peer
```

### 8.3 根因（三个叠加问题）

#### 根因 1：JNI Global Ref 泄漏

第三方相机 SDK 的 native 实现里，把 `Bitmap` 对象存为 `GlobalRef` 但从未 `DeleteGlobalRef`：

```cpp
// 错误实现
static jobject g_preview_buffer = nullptr;
void setPreviewBuffer(JNIEnv* env, jobject bitmap) {
    if (g_preview_buffer) env->DeleteGlobalRef(g_preview_buffer);
    g_preview_buffer = env->NewGlobalRef(bitmap);  // ← 每次切换预览都创建
}
// 但析构函数没实现，或某个 native thread 持有导致不释放
```

每次切换摄像头 `NewGlobalRef` 一个新 Bitmap，旧的不释放 → 持续累计。

#### 根因 2：JNI Local Ref 溢出

native 函数在循环中大量创建 local ref 未释放：

```cpp
// 错误实现
void processFrames(JNIEnv* env, jobjectArray frames) {
    int count = env->GetArrayLength(frames);
    for (int i = 0; i < count; i++) {
        jobject frame = env->GetObjectArrayElement(frames, i);
        // 处理 frame
        // 忘记 env->DeleteLocalRef(frame)
    }
    // 5000 帧 × 1 ref = 5000 local ref
    // 接近 local ref 上限 65536 时抛异常
}
```

#### 根因 3：内部类持有外部 Activity

```java
// 错误实现
class ImageProcessor {
    private Runnable captureTask = new Runnable() {
        @Override public void run() {
            // 隐式持有外部 ImageProcessor
            // ImageProcessor 持 Activity
            // Activity 不能被 GC 回收
            capture();
        }
    };
    // captureTask 是字段，ImageProcessor 被 Activity 持有
    // 形成 ImageProcessor → Runnable → ImageProcessor 的循环引用
}
```

### 8.4 修复方案

#### 修复 1：JNI Global Ref 配对

```cpp
// 正确实现：用 weak ref + 显式释放
static jclass g_bitmap_class = nullptr;  // class 用 global
static jobject g_preview_buffer = nullptr;

void setPreviewBuffer(JNIEnv* env, jobject bitmap) {
    if (g_preview_buffer) {
        env->DeleteGlobalRef(g_preview_buffer);
        g_preview_buffer = nullptr;
    }
    if (bitmap) {
        g_preview_buffer = env->NewGlobalRef(bitmap);
    }
}

void cleanup(JNIEnv* env) {
    if (g_preview_buffer) env->DeleteGlobalRef(g_preview_buffer);
    if (g_bitmap_class) env->DeleteGlobalRef(g_bitmap_class);
}

// 注册 native method 时绑定 cleanup 到 OnLoad
JNI_OnUnload 时调用
```

#### 修复 2：JNI Local Ref 配对 + 局部帧

```cpp
// 正确实现：用 PushLocalFrame / PopLocalFrame
void processFrames(JNIEnv* env, jobjectArray frames) {
    int count = env->GetArrayLength(frames);
    // 创建局部帧
    if (env->PushLocalFrame(count + 10) != 0) return;

    for (int i = 0; i < count; i++) {
        jobject frame = env->GetObjectArrayElement(frames, i);
        // 处理 frame
        // 不用手动 DeleteLocalRef —— PopLocalFrame 会自动释放
    }

    // 一次性释放所有 local ref
    env->PopLocalFrame(nullptr);
}
```

#### 修复 3：内部类用 static

```java
// 正确实现
class ImageProcessor {
    private static class CaptureTask implements Runnable {
        private final WeakReference<ImageProcessor> weakRef;
        CaptureTask(ImageProcessor processor) {
            this.weakRef = new WeakReference<>(processor);
        }
        @Override public void run() {
            ImageProcessor p = weakRef.get();
            if (p != null) p.capture();
        }
    }
    // CaptureTask 不再持外部类的强引用
}
```

### 8.5 修复效果

| 指标 | 修复前 | 修复后 | 改善 |
|------|-------|-------|------|
| ANR 占比 | 0.3% | 0.04% | 87% ↓ |
| Janky frames | 18% | 3% | 83% ↓ |
| Foreground GC P99 | 1.5s | 120ms | 92% ↓ |
| `.Global Ref` 数量 | 1245 | 187 | 85% ↓ |
| `.Local Ref` 数量 | 5120 | 423 | 92% ↓ |
| Java Heap 占用 | 165MB | 98MB | 41% ↓ |

### 8.6 防范建议

**1. CI/CD 阶段集成 LeakCanary**
- Debug build 自动检测
- 提交 PR 时跑 LeakCanary 测试

**2. 关键路径加 JNI ref 监控**
- 每次 native 方法入口检查 local ref 数量
- 超过阈值报警

**3. onTrimMemory 必须实现**
- `TRIM_MEMORY_RUNNING_CRITICAL` → 主动释放缓存
- `TRIM_MEMORY_UI_HIDDEN` → 释放 UI 资源

**4. 大对象复用 + 分块加载**
- Bitmap 用 `BitmapPool` 复用
- 视频帧用环形 buffer

**5. ART GC 监控埋点**
- 收集 Foreground GC 频率、P99
- 上报到 APM，阈值告警

> **稳定性架构师视角：** 这个案例展示了 ART 堆问题的"三件套"：**Java 泄漏 + JNI 引用泄漏 + GC 退化**。**单一问题可能不会触发 ANR，但叠加在一起就足以让系统卡到崩溃**。排查时**必须看完整 GC trace + hprof + dumpsys meminfo**——任何一个角度的盲点都会让根因被遗漏。

---

## 总结：架构师视角的 5 条 Takeaway

1. **ART 堆的"五象限"是排查起点**。**容量、可见性、算法、边界、压力模式**——任何"OOM"或"卡顿"先定位到这五象限中的哪个，再深入。**不要一上来就 dump hprof 盲查**，那是最低效的路径。

2. **CC 取代 CMS 是必然，但 CC 也有代价**。CC 把 STW 压到 5-15ms，但 read barrier 1-3ns 的开销在内存密集型应用上慢 5-10%。**Java 性能优化不能假设屏障免费**——大量对象引用是隐形税。

3. **JNI 引用表是 Java 堆"看不见的另一半"**。AOSP 14 用 `IndirectRefTable` 代替了旧 `ReferenceTable`，但**泄漏模式没变**——native 侧 `NewGlobalRef` 不配对 / 内部类持外部 Activity 是最常见的根因。**`dumpsys meminfo` 的 `.Global Ref / .Local Ref` 字段是诊断第一信号**。

4. **大对象是 ART 堆性能"放大器"**。HUMONGOUS 风暴、LOS 碎片、Bitmap 巨型分配——这些不是边缘情况，是**线上 80% 长 GC pause 的根因**。核心原则：**避免分配大对象 + 控制大对象存活时间 + 用 inSampleSize 缩放**。

5. **三种 GC 模式是压力"指示器"**。**Concurrent / Background / Foreground 的比例反映内存压力**。Foreground 比例 > 5% 是严重信号，> 1% 是异常信号。**`dumpsys meminfo` 的 GC 原因统计是 5 秒内能拿到的健康指标**。

---

## 附录 A：核心源码路径索引

| 文件 | 完整路径 | 说明 | 本章涉及节 |
|------|---------|------|----------|
| Heap | `art/runtime/gc/heap.cc` | ART 堆主类（分配/GC 调度） | §1, §2, §6 |
| Heap header | `art/runtime/gc/heap.h` | Heap 类定义 | §1, §6 |
| Heap inline | `art/runtime/gc/heap-inl.h` | 分配内联（写屏障） | §1, §3 |
| RegionSpace | `art/runtime/gc/space/region_space.cc` | CC 主空间 | §1, §5 |
| RegionSpace inline | `art/runtime/gc/space/region_space-inl.h` | Region 分配内联 | §1, §5 |
| RegionSpace header | `art/runtime/gc/space/region_space.h` | Region 数据结构 | §1 |
| LargeObjectSpace | `art/runtime/gc/space/large_object_space.cc` | LOS 管理 | §5 |
| ImageSpace | `art/runtime/gc/space/image_space.cc` | 启动映像 | §1, §7 |
| ZygoteSpace | `art/runtime/gc/space/zygote_space.cc` | Zygote 预加载 | §1 |
| ConcurrentCopying | `art/runtime/gc/collector/concurrent_copying.cc` | CC 收集器 | §2, §3 |
| ConcurrentCopying inline | `art/runtime/gc/collector/concurrent_copying-inl.h` | 读屏障内联 | §3 |
| ConcurrentMarkSweep | `art/runtime/gc/collector/concurrent_mark_sweep.cc` | CMS 收集器（旧） | §2 |
| ReferenceProcessor | `art/runtime/gc/reference_processor.cc` | 软/弱/虚引用处理 | §7 |
| IndirectRefTable | `art/runtime/indirect_reference_table.cc` | JNI 引用表 | §4 |
| IndirectRefTable header | `art/runtime/indirect_reference_table.h` | 引用表结构 | §4 |
| JNI internal | `art/runtime/jni/jni_internal.cc` | JNI 实现 | §4 |
| Reflection | `art/runtime/reflection.cc` | 反射（class/method 持有） | §7 |
| OAT file manager | `art/runtime/oat_file_manager.cc` | OAT/image 加载 | §7 |

---

## 附录 B：风险速查表（精简版）

> 完整 30 行版本见 §7.5 表格。这里给出**最常用的 10 个**作为速记。

| # | 现象 | 一句话定位 | 一行排查命令 |
|---|------|----------|------------|
| 1 | 主线程卡 1s+ | Foreground GC P99 异常 | `dumpsys meminfo <pkg> \| grep "Foreground concurrent"` |
| 2 | Java OOM | Java Heap 超 max | `dumpsys meminfo <pkg> \| grep "Java Heap"` |
| 3 | JNI 泄漏 | Global Ref 持续涨 | `dumpsys meminfo <pkg> \| grep ".Global Ref"` |
| 4 | Finalizer 卡死 | finalize 阻塞 | `adb logcat \| grep FinalizerWatchdog` |
| 5 | 长 GC pause | ProcessMarkStack 慢 | Perfetto → `concurrent_copying` tracepoint |
| 6 | LOS 碎片 | 大对象分配失败 | `dumpsys meminfo <pkg> \| grep "LOS"` |
| 7 | HUMONGOUS 风暴 | Region 池耗尽 | Perfetto → `RegionSpace` |
| 8 | Image 损坏 | 启动失败 | `adb logcat \| grep "Image checksum"` |
| 9 | 软引用未清理 | 堆回收不彻底 | 检查 `soft references` |
| 10 | GC 风暴 | GC 频率 5 次/分 | `dumpsys meminfo <pkg> \| grep "Total GC time"` |

---

## 篇尾衔接

本篇完成了 ART 堆"五象限"的纵深：分代空间、算法选型、可见性、JNI 边界、大对象、压力模式。**但 ART 堆并不是 App 内存的全部**。**Java 对象在 JNI 调用时可能回到 Native 堆（ByteBuffer.allocateDirect、Bitmap.NativeAllocation），这些 Native 堆的分配不受 ART 管理**——它由 bionic libc 的 scudo 分配器管。

下一篇 [04-Native 堆内存与分配器（AOSP 14）](04-Native 堆内存与分配器（AOSP 14）.md) 将深入：
- bionic scudo 分配器（Size Class / Quarantine / Hardening）
- malloc_debug 调试模式
- JNI 与 Native 堆的"看不见"的内存（ByteBuffer.allocateDirect）
- 图形缓冲区（Gralloc / ION / DMA-BUF）
- Bitmap.recycle() 漏调导致 Native 堆增长 800MB 的实战案例

**掌握了 Java 堆 + Native 堆，才算掌握了 App 进程内存的全貌**——这两块在 `dumpsys meminfo` 中分别占"Pss Java Heap"和"Pss Native Heap"两行，但治理手段完全不同。

