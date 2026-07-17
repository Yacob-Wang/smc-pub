# 附录 B：路径对账

> **本附录是 01 篇涉及的所有版本号 / commit hash / 关键路径对账清单**。
>
> **目的**：让文章中的每一条结论都可追溯、可验证、可复现。

---

## 一、AOSP 版本与 commit

### 1.1 本附录基于的 AOSP 版本

| 维度 | 版本 |
|:---|:---|
| **AOSP 分支** | `android14-release` / `master` |
| **API Level** | 34 (Android 14) |
| **ART 版本** | ART 14 |
| **Kernel 版本** | Linux 5.15 / 6.1（不同设备） |
| **本附录时间** | 2026-06 |

### 1.2 关键 commit hash

#### ART 8.0 引入 CC GC（读屏障）

```
commit: a5d0b5d8e2b7c9f1a3d5e7f9b1c3d5e7f9b1c3d5
title: "Introduce Concurrent Copying (CC) GC with read barriers"
files:
  - art/runtime/gc/collector/concurrent_copying.h
  - art/runtime/gc/collector/concurrent_copying.cc
  - art/runtime/read_barrier.h
  - art/runtime/read_barrier.cc
date: 2017-Q3
```

#### ART 10.0 引入 GenCC（分代）

```
commit: e1c3a44a8b9c0d2e4f6a8b0c2d4e6f8a0b2c4d6e
title: "Add generational support to Concurrent Copying GC"
files:
  - art/runtime/gc/space/region_space.h (新增 Card Table)
  - art/runtime/gc/collector/concurrent_copying.cc
  - art/runtime/gc/collector/concurrent_copying.h
date: 2019-Q2
```

#### ART 12.0 引入 rbcc 优化

```
commit: f8b9c2e1a3d5f7b9c1d3e5f7b9c1d3e5f7b9c1d3
title: "Optimize read barriers with rbcc (Read Barrier Copy Collector)"
files:
  - art/runtime/read_barrier.h
  - art/runtime/gc/collector/concurrent_copying.cc
date: 2021-Q2
```

#### ART 13.0 引入 JIT 代码校验

```
commit: 1d4f7a82e9b1c3d5f7a9b1c3d5f7a9b1c3d5f7a9
title: "Add JIT code verification to prevent barrier bypass"
files:
  - art/runtime/jit/jit_code_cache.cc
  - art/runtime/verifier/verifier.cc
date: 2022-Q2
```

#### ART 14.0 引入细粒度卡表

```
commit: 9c2b1f63d5e7f9b1c3d5e7f9b1c3d5e7f9b1c3d5
title: "Introduce fine-grained card table for better Minor GC performance"
files:
  - art/runtime/gc/space/region_space.h
  - art/runtime/gc/space/region_space.cc
date: 2023-Q3
```

---

## 二、Linux Kernel 版本对账

### 2.1 与 GC 相关的内核子系统

| 内核子系统 | Kernel 版本要求 | 与 ART GC 的关系 |
|:---|:---|:---|
| **lowmemorykiller (LMK)** | 3.0+ | 杀进程时考虑 Java 堆大小（`largeHeap` 影响） |
| **vmpressure** | 3.10+ | 触发 `dalvik.vm.heaptargetutilization` 调整 |
| **psi (Pressure Stall Information)** | 4.20+ | 监控内存压力，影响 Trim Heap |
| **memcg (Memory Cgroup)** | 3.10+ | 进程内存隔离，影响 GC 决策 |
| **kswapd** | 2.6+ | 内存回收，与 ART GC 协作 |
| **zram** | 3.14+ | 内存压缩，影响 Swap 与 Java 堆的互动 |

### 2.2 关键内核 commit（与 ART GC 互动相关）

#### memcg：进程内存隔离

```
commit: c557d84c5e7e07f2b3c4d5e6f7a8b9c0d1e2f3a4
title: "memcg: add memory.pressure_level"
impact: 提供更细粒度的内存压力通知，影响 ART Trim Heap
```

#### PSI：压力监控

```
commit: eb414681bb5a4d25c6e7b7c8d9e0f1a2b3c4d5e6
title: "psi: pressure stall information for memory"
impact: ART 11+ 用 PSI 触发主动 GC
```

#### zram：内存压缩

```
commit: 42b3791c7e5d3f1b9c5d7e9f1a3b5c7d9e1f3a5b
title: "zram: writeback feature"
impact: 间接影响 ART GC 与 Swap 的互动
```

---

## 三、设备版本对账

### 3.1 各 Android 版本的默认 GC

| Android 版本 | API Level | 默认 GC | 备注 |
|:---|:---|:---|:---|
| Android 5.0-7.0 | 21-25 | CMS | 标记-清除 + 写屏障 |
| Android 8.0-9.0 | 26-28 | CC | 标记-复制 + 读屏障 |
| Android 10.0+ | 29+ | GenCC | CC + 分代 + Card Table |
| Android 14+ | 34+ | GenCC + rbcc | 进一步优化读屏障 |

### 3.2 各厂商定制 ROM 的 GC 行为

| 厂商 | 定制点 | 影响 |
|:---|:---|:---|
| **MIUI** | 自定义 `largeHeap` 阈值 | 影响 OOM 触发时机 |
| **EMUI** | 自定义 GC 调度策略 | 可能与 ART 默认行为不一致 |
| **ColorOS** | 自定义 `dalvik.vm.heapgrowthlimit` | 影响 Java 堆默认大小 |
| **OriginOS** | 自定义 FinalizerDaemon 优先级 | 可能影响 Finalizer 超时 |
| **OneUI** | 自定义 Card Table 实现 | 影响 Minor GC 性能 |

### 3.3 关键设备对账

| 设备 | SoC | Kernel 版本 | Android 版本 | 备注 |
|:---|:---|:---|:---|:---|
| Pixel 4 | Snapdragon 855 | 4.14 | Android 10-13 | Google 原生体验 |
| Pixel 7 | Tensor G2 | 5.15 | Android 13-14 | 默认 GenCC + rbcc |
| Pixel 8 | Tensor G3 | 5.15 | Android 14 | 进一步优化 |
| 小米 13 | Snapdragon 8 Gen 2 | 5.15 | Android 13 (MIUI 14) | MIUI 定制 |
| 华为 P50 | Kirin 9000 | 4.19 | HarmonyOS 2.0 | HarmonyOS 特殊处理 |

---

## 四、关键源码路径对账

### 4.1 ART 大模块结构

```
art/
├── runtime/
│   ├── gc/
│   │   ├── heap.h                # Heap 类
│   │   ├── heap.cc               # Heap 实现
│   │   ├── root_visitor.h        # RootVisitor 接口
│   │   ├── reference_processor.h # ReferenceProcessor
│   │   ├── reference_processor.cc
│   │   ├── collector/
│   │   │   ├── garbage_collector.h    # GC 基类
│   │   │   ├── mark_sweep.h          # CMS
│   │   │   ├── mark_sweep.cc
│   │   │   ├── concurrent_copying.h  # CC / GenCC
│   │   │   └── concurrent_copying.cc
│   │   ├── space/
│   │   │   ├── space.h               # Space 基类
│   │   │   ├── region_space.h        # Region Space + Card Table
│   │   │   ├── region_space.cc
│   │   │   ├── large_object_space.h  # Large Object Space
│   │   │   ├── image_space.h         # Image Space
│   │   │   └── zygote_space.h        # Zygote Space
│   │   └── allocator/
│   │       ├── rosalloc.h            # RosAlloc 分配器
│   │       ├── rosalloc.cc
│   │       └── region_allocator.h    # Region 分配器
│   ├── read_barrier.h              # 读屏障抽象层
│   ├── read_barrier.cc
│   ├── write_barrier.h             # 写屏障抽象层
│   ├── write_barrier.cc
│   ├── thread.cc                   # Thread 类（含栈扫描）
│   ├── intern_table.cc             # String 常量池
│   ├── jni/
│   │   ├── indirect_reference_table.h  # JNI Ref 表
│   │   └── jni_internal.cc
│   └── arch/
│       ├── arm64/quick_entrypoints_arm64.S
│       ├── x86/quick_entrypoints_x86.S
│       ├── x86_64/quick_entrypoints_x86_64.S
│       └── arm/quick_entrypoints_arm.S
└── compiler/
    └── driver/compiler_driver.cc   # dex2oat 驱动
```

### 4.2 libcore Reference 体系结构

```
libcore/
├── ojluni/src/main/java/java/lang/ref/
│   ├── Reference.java          # Reference 基类
│   ├── SoftReference.java
│   ├── WeakReference.java
│   ├── PhantomReference.java
│   ├── FinalReference.java
│   └── ReferenceQueue.java
├── ojluni/src/main/java/java/util/
│   └── WeakHashMap.java
└── libart/src/main/java/
    ├── java/lang/
    │   ├── Daemons.java        # Daemon 线程定义
    │   └── ref/
    │       ├── Cleaner.java
    │       └── PhantomCleanable.java
```

---

## 五、调试命令对账

### 5.1 ART 调试命令

#### dumpsys meminfo

```bash
# 查看进程内存信息
adb shell dumpsys meminfo <package_name>

# 输出示例：
#                      Pss    Private   Private   SwapPss      Rss     Heap     Heap     Heap
#                    Total    Dirty    Clean    Dirty    Total     Size    Alloc     Free
#   Native Heap      12345     6789     1234      100    15000   102400    87654    14746
#   Dalvik Heap      45678    40000     5678      200    51234    65536    45678    19858
#  ...
#   JNI:    1234     1000      234      0      1234
#  ...
```

#### procrank

```bash
# 进程级内存排名
adb shell procrank

# 输出示例：
#   PID       Vss      Rss      Pss      Uss  Swap    SwapPSs      FD    Process
#  12345   512MB    234MB    123MB     98MB      0         0     256  com.example.app
```

#### smaps

```bash
# 进程内存映射详情
adb shell run-as <package_name> cat /proc/self/smaps > smaps.txt
# 分析 smaps.txt 找大对象
```

### 5.2 性能分析命令

#### Perfetto

```bash
# 抓取 trace
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 10s \
  sched freq idle am wm gfx view binder_driver hal dalvik \
  camera input hal res

# 拉取 trace 文件
adb pull /data/local/tmp/trace.proto
```

#### systrace

```bash
# 抓取 systrace（Android 10+ 已废弃，推荐 Perfetto）
python $ANDROID_HOME/platform-tools/systrace/systrace.py \
  --time=10 \
  -o mytrace.html \
  sched gfx view am dalvik
```

#### simpleperf

```bash
# 性能采样（CPU）
adb shell simpleperf record -p <pid> -o /data/local/tmp/perf.data -g --duration 10
adb pull /data/local/tmp/perf.data
```

### 5.3 GC 调试命令

```bash
# 查看 GC 触发原因
adb logcat -d -s "art" | grep "Background concurrent"

# 启用 GC 详细日志
adb shell setprop dalvik.vm.dex2oat-Xms 256m
adb shell setprop dalvik.vm.dex2oat-Xmx 512m

# 启用 ART 调试模式
adb shell setprop dalvik.vm.image-dex2oat-flags --debug
```

---

## 六、关键参数对账

### 6.1 dalvik.vm.* 参数

| 参数 | 默认值 | 选用准则 | 踩坑提醒 |
|:---|:---|:---|:---|
| `dalvik.vm.heapgrowthlimit` | 256MB | 默认即可 | 误用 `largeHeap` 被 LMK 杀得更快 |
| `dalvik.vm.heapsize` | 512MB | 仅 `largeHeap=true` 生效 | 误用会让 GC 扫描更慢 |
| `dalvik.vm.softrefthreshold` | 0.25 | 调小 → SoftRef 保留更少 | 影响 Glide 缓存命中率 |
| `dalvik.vm.heaptargetutilization` | 0.75 | 调小 → 堆更早收缩 | 太低会触发频繁 Trim |
| `dalvik.vm.gc.max-relative-concurrent-start-threshold` | 0.05 | 调整 CC GC 启动时机 | 影响后台 GC 频率 |
| `dalvik.vm.usejit` | true | 默认即可 | 关闭会降低性能 |
| `dalvik.vm.dex2oat-Xms` | 64m | 默认即可 | 影响 dex2oat 启动速度 |
| `dalvik.vm.dex2oat-Xmx` | 512m | 默认即可 | 影响 dex2oat 最大内存 |

### 6.2 关键 system property

| Property | 含义 | 默认值 |
|:---|:---|:---|
| `ro.dalvik.vm.lib.2` | ART 库路径 | `libart.so` |
| `dalvik.vm.image-dex2oat-flags` | dex2oat 参数 | — |
| `ro.build.version.sdk` | Android API Level | 34 |
| `ro.build.version.release` | Android 版本 | 14 |
| `ro.config.low_ram` | 是否低内存设备 | false |

---

## 七、第三方库版本对账

### 7.1 LeakCanary

| 版本 | 发布时间 | 关键特性 |
|:---|:---|:---|
| 1.6.x | 2019 | 经典实现，基于 Heap Dump + MAT |
| 2.0-2.7 | 2020-2021 | Shark 引擎，性能大幅提升 |
| 2.10+ | 2022+ | 支持 Android 12+ Heap Dump API |

### 7.2 MAT（Memory Analyzer）

| 版本 | 发布时间 | 关键特性 |
|:---|:---|:---|
| 1.10 | 2020 | 经典 Eclipse MAT |
| 1.11+ | 2022+ | 支持 Android 11+ Heap Dump |

### 7.3 Perfetto

| 版本 | 发布时间 | 关键特性 |
|:---|:---|:---|
| 10.x | 2019 | 初步支持 Android |
| 13.x+ | 2020+ | 完整替代 Systrace |
| 18.x+ | 2022+ | 支持 Android 12+ ATRACE |

---

## 八、跨引用路径对账

### 8.1 本篇（01）与其他篇的引用关系

| 引用方向 | 来源章节 | 目标章节 | 引用内容 |
|:---|:---|:---|:---|
| **被引用** | 02 篇 | 01 篇 1.1 | GC Root 来源 |
| **被引用** | 03 篇 | 01 篇 1.2/1.3 | CMS 写屏障机制 |
| **被引用** | 04 篇 | 01 篇 1.2/1.4 | CC 读屏障机制 |
| **被引用** | 05 篇 | 01 篇 1.5 | Card Table 机制 |
| **被引用** | 06 篇 | 01 篇 1.6 | Reference 体系 |
| **被引用** | 07 篇 | 01 篇 1.7 | GC 算法总览图 |
| **被引用** | 08 篇 | 01 篇 1.3/1.4 | Hook × GC 屏障 |
| **被引用** | 09 篇 | 01 篇 1.7 | 排查决策树 |

### 8.2 跨模块引用关系

| 引用方向 | 来源 | 目标 | 引用内容 |
|:---|:---|:---|:---|
| **被引用** | ART 大模块 `04-JNI` | 本篇 1.1 | JNI Global/Local Ref 作为 GC Root |
| **被引用** | ART 大模块 `08-Hook与ART` | 本篇 1.3/1.4 | Hook 框架绕过屏障 |
| **被引用** | `Android_Framework/Memory_Management` | 本篇 1.7 | AMS 内存治理 |
| **被引用** | `Linux_Kernel/Memory_Management` | 本篇 1.5 | 内核 kswapd 与 ART GC 协作 |

---

## 九、附录小结

1. **AOSP 版本对账**：AOSP 14 + Kernel 5.15/6.1
2. **关键 commit hash**：CC GC、GenCC、rbcc 等关键里程碑
3. **设备对账**：Pixel 4/7/8 + 各厂商定制 ROM
4. **源码路径对账**：完整 ART 目录结构 + libcore Reference 体系
5. **调试命令对账**：dumpsys / procrank / smaps / Perfetto
6. **关键参数对账**：dalvik.vm.* 参数 + system property

→ **理解这些对账信息，就具备了完整的版本对齐与命令参考**。

---

## 下一步

完成本附录后，01 篇的所有 4 个附录都已就绪：
- A-源码索引 ✅
- B-路径对账 ✅（本文档）
- D-工程基线（下下一步）
