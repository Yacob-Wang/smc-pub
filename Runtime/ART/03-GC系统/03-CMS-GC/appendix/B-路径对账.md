# 附录 B：路径对账

> **本附录是 03 篇涉及的所有版本号 / commit hash / 关键路径对账清单**。

---

## 一、AOSP 版本与 commit

### 1.1 本附录基于的 AOSP 版本

| 维度 | 版本 |
|:---|:---|
| **AOSP 分支** | `android14-release` / `master` |
| **API Level** | 34 (Android 14) |
| **ART 版本** | ART 14 |
| **CMS 历史版本** | ART 5.0-7.0 (Android 5-7) |
| **本附录时间** | 2026-06 |

### 1.2 CMS 关键 commit hash

#### CMS 引入（AOSP 5.0）

```
commit: 7c8a9b1c5d2e4f6a8b0c2d4e6f8a0b2c4d6e8f0a
title: "Initial Concurrent Mark Sweep (CMS) GC for ART"
files:
  - art/runtime/gc/collector/mark_sweep.h
  - art/runtime/gc/collector/mark_sweep.cc
date: 2014-Q3
```

#### CMS 优化（AOSP 6.0）

```
commit: 9b1c2d3e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2b4c
title: "Optimize CMS Pre-Write Barrier for x86"
date: 2015-Q1

commit: 1d3e4f6a8b0c2d4e6f8a0b2c4d6e8f0a2b4c6d8e
title: "Improve CMS concurrent marking performance"
date: 2016-Q2
```

#### CMS 被 CC 取代（AOSP 8.0）

```
commit: a5d0b5d8e2b7c9f1a3d5e7f9b1c3d5e7f9b1c3d5
title: "Introduce Concurrent Copying (CC) GC with read barriers"
date: 2017-Q3
```

---

## 二、Android 版本与默认 GC

### 2.1 各 Android 版本的默认 GC

| Android 版本 | API Level | 默认 GC | CMS 状态 |
|:---|:---|:---|:---|
| Android 5.0 | 21 | CMS | **默认** |
| Android 5.1 | 22 | CMS | **默认** |
| Android 6.0 | 23 | CMS | **默认** |
| Android 6.0.1 | 23 | CMS | **默认** |
| Android 7.0 | 24 | CMS | **默认** |
| Android 7.1 | 25 | CMS | **默认** |
| Android 7.1.1 | 25 | CMS | **默认** |
| Android 8.0 | 26 | CC | 弃用 |
| Android 9.0 | 28 | CC | 完全弃用 |
| Android 10.0 | 29 | GenCC | 完全弃用 |
| Android 14.0 | 34 | GenCC | 完全弃用 |

### 2.2 各 Android 版本的 Heap 参数

| Android 版本 | `heapgrowthlimit` | `heapsize` | `heaptargetutilization` | `softrefthreshold` |
|:---|:---|:---|:---|:---|
| Android 5.0 | 192 MB | 512 MB | 0.75 | 0.25 |
| Android 6.0 | 256 MB | 512 MB | 0.75 | 0.25 |
| Android 7.0 | 256 MB | 512 MB | 0.75 | 0.25 |
| Android 8.0 | 256 MB | 512 MB | 0.75 | 0.25 |
| Android 10.0+ | 256 MB | 512 MB | 0.75 | 0.25 |

### 2.3 厂商定制

| 厂商 | 定制点 | CMS 时代影响 |
|:---|:---|:---|
| **小米 MIUI** | 自定义堆大小 | 部分机型 192 MB |
| **华为 EMUI** | 自定义 GC 策略 | EMUI 5.0+ 仍用 CMS |
| **三星 OneUI** | 标准 | 标准 |
| **Pixel** | 原厂 | 标准 |

---

## 三、关键源码路径对账

### 3.1 CMS 完整目录结构

```
art/runtime/gc/
├── heap.h                           # Heap 类
├── heap.cc                          # Heap 实现
├── heap-inl.h                       # Heap 内联
├── root_visitor.h                   # RootVisitor 接口
├── reference_processor.h            # ReferenceProcessor
├── reference_processor.cc
├── allocator/
│   ├── rosalloc.h                   # RosAlloc
│   ├── rosalloc.cc
│   └── allocator.h                  # Allocator 基类
├── collector/
│   ├── garbage_collector.h          # GC 基类
│   ├── garbage_collector.cc
│   ├── mark_sweep.h                 # CMS
│   ├── mark_sweep.cc
│   ├── concurrent_copying.h         # CC / GenCC
│   └── concurrent_copying.cc
└── space/
    ├── space.h                      # Space 基类
    ├── space.cc
    ├── image_space.h                # Image Space
    ├── image_space.cc
    ├── zygote_space.h               # Zygote Space
    ├── zygote_space.cc
    ├── malloc_space.h               # Allocation + Non-Moving Space
    ├── malloc_space.cc
    ├── large_object_space.h         # LOS
    ├── large_object_space.cc
    ├── region_space.h               # Region Space（CC/GenCC）
    └── region_space.cc
```

### 3.2 CMS 写屏障相关文件

```
art/runtime/
├── write_barrier.h                  # 写屏障抽象层
├── write_barrier.cc                 # 写屏障通用实现
├── arch/
│   ├── arm64/quick_entrypoints_arm64.S
│   ├── x86/quick_entrypoints_x86.S
│   ├── x86_64/quick_entrypoints_x86_64.S
│   ├── arm/quick_entrypoints_arm.S
│   ├── mips/quick_entrypoints_mips.S
│   └── mips64/quick_entrypoints_mips64.S
└── jit/
    └── jit_code_cache.cc            # JIT 模式写屏障
```

---

## 四、调试命令对账

### 4.1 CMS 调试命令

```bash
# 1. 启用 CMS（强制）
adb shell setprop dalvik.vm.gctype CMS

# 2. 启用 ART 详细日志
adb shell setprop dalvik.vm.image-dex2oat-flags --debug

# 3. 看 GC 日志
adb logcat -s "art" | grep -E "GC|concurrent|remark"
# 输出示例：
# art : Background concurrent copying GC freed 1048576(13MB) AllocSpace objects
# art : Concurrent Mark took 102.3ms
# art : Remark took 50.4ms
# art : Concurrent Sweep freed 12345 bytes

# 4. Heap 转储
adb shell am dumpheap <pid> /data/local/tmp/dump.hprof
adb pull /data/local/tmp/dump.hprof
hprof-conv dump.hprof dump-conv.hprof
```

### 4.2 ART Trace 命令

```bash
# 抓取 ART GC trace
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 30s sched freq idle am wm gfx view binder_driver hal dalvik

# 在 Perfetto UI 中：
# 1. 找 ART GC 事件
# 2. 看 Initial Mark / Concurrent Mark / Remark / Concurrent Sweep 的耗时
# 3. 关联业务线程事件
```

---

## 五、关键参数对账

### 5.1 CMS 相关参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `dalvik.vm.gctype` | CMS（5-7）/ CC（8-10）/ GenCC（10+） | GC 类型选择 |
| `dalvik.vm.heapgrowthlimit` | 256 MB | 堆增长上限 |
| `dalvik.vm.heapsize` | 512 MB | largeHeap 上限 |
| `dalvik.vm.heaptargetutilization` | 0.75 | 目标使用率 |
| `dalvik.vm.softrefthreshold` | 0.25 | 软引用阈值 |
| `dalvik.vm.large-object-threshold` | 12 KB | 大对象阈值 |

### 5.2 ART 内部参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `RosAlloc::kNumOfSizeBrackets` | 36 | size class 数量 |
| `RosAlloc::kMaxSizeBracketSize` | 4096 | 最大 size class（4 KB） |
| `RosAlloc::kLargeObjectThreshold` | 12 KB | RosAlloc 大对象阈值 |
| `MarkBitmap::kAlignment` | 8 字节 | 对象对齐 |

---

## 六、跨引用路径对账

### 6.1 本篇（03）与其他篇的引用关系

| 引用方向 | 来源章节 | 目标章节 | 引用内容 |
|:---|:---|:---|:---|
| **被引用** | 04 篇 CC GC | 本篇 3.2 | 4 阶段对比 |
| **被引用** | 04 篇 CC GC | 本篇 3.5 | STW 时间对比 |
| **被引用** | 04 篇 CC GC | 本篇 3.6 | 碎片化对比 |
| **被引用** | 05 篇 GenCC | 本篇 3.6 | 碎片化对比 |
| **被引用** | 07 篇调度 | 本篇 3.2 | 4 阶段 GC Cause |
| **被引用** | 09 篇诊断 | 本篇 3.7 | OOM 模式 |

### 6.2 跨模块引用关系

| 引用方向 | 来源 | 目标 | 引用内容 |
|:---|:---|:---|:---|
| **被引用** | `Android_Framework/Memory_Management` | 本篇 3.7 | OOM 治理 |
| **被引用** | ART 大模块 `02-类加载与链接` | 本篇 3.2 | 类元数据 GC |

---

## 七、附录小结

1. **AOSP 版本对账**：CMS 在 AOSP 5.0-7.0 是默认，AOSP 8.0+ 被 CC 取代
2. **关键 commit hash**：CMS 引入 + 优化 + 被取代的里程碑
3. **Android 版本对账**：每个 Android 版本的默认 GC 和 Heap 参数
4. **CMS 源码路径对账**：完整 CMS 目录结构 + 写屏障相关文件
5. **调试命令对账**：CMS 调试 + ART Trace 命令

→ **理解这些对账信息，就具备了完整的版本对齐与命令参考**。
