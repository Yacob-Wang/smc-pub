# 附录 A：源码索引（按文件路径 · v2 升级版）

> **本子模块**：03-GC 系统 / 09-GC 诊断与治理（诊断与治理 · 附录 A）
> **本附录定位**：**GC 诊断与治理涉及的全部 AOSP 源码路径**——按文件路径字母序排列，可直接跳转
> **基线版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS，2024-11-17 发布，EOL 2026-12）
> **v2 升级日期**：2026-07-18（v1 旧文按 v4 规范 + 新基线升级）

---

## 0. 本附录定位声明

| 维度 | 本附录承担 | 本附录不涉及 |
| :--- | :--- | :--- |
| ART Runtime 源码路径 | ✓ A.1 ~ A.2 全部 | — |
| JVMTI / Native Debug 源码 | ✓ A.3 | — |
| Profile / JIT 源码 | ✓ A.4 ~ A.5 | — |
| Compiler / Image 源码 | ✓ A.6 ~ A.8 | — |
| Framework 源码 | ✓ A.9 ~ A.10 | — |
| Native 堆 / Hprof / Perfetto | ✓ A.11 ~ A.13 | — |
| 工具 / 测试 / 常量 | ✓ A.14 ~ A.17 | — |
| **ART 17 新增源码** | ✓ **A.18（GenCC + 类去重 + ART 内部状态 + sheaves）** | — |
| 路径对账 | — | [B-路径对账](B-路径对账.md)（v2 升级版） |
| 工程基线 | — | [D-工程基线](D-工程基线.md)（v2 升级版） |

**承接自**：本附录承接正文 9.1 ~ 9.10 全部章节——每个章节涉及的源码路径都在这里索引。

**衔接去**：[B-路径对账](B-路径对账.md) 提供"已验证路径 vs 错误路径"对照表（重写为 v2 升级版）；[D-工程基线](D-工程基线.md) 提供工程验收基线（重写为 v2 升级版）。

---

## 校准决策日志（v2 升级 · 3 轮全跑）

### 第 1 轮：结构校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| v1 旧稿标记段 | 在（顶部 14 行） | **删**（v1 → v2 实质升级） | 内容已按 v4 规范重写，标记段失效 |
| 本附录定位声明 | 无 | **新增**（v4 §3 强制要求） | v1 后期已按 v4 写但缺本附录定位段 |
| 衔接去 | 无 | **新增 2 篇**（B-路径对账 + D-工程基线） | 跨附录引用矩阵要求显式关联 |
| 4 附录 | A/B/D 完整 | A/B/C/D 完整 | v4 §4.6 强制要求 |

### 第 2 轮：硬伤校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 基线版本号 | AOSP 14 / Linux 5.10 | AOSP 17 / **Linux 6.18** | **2026-07-18 基线升级 |
| API 等级 | API 34 | **API 37** | 与 AOSP 17 配套 |
| **ART 17 新增源码未覆盖** | A.1 ~ A.17 | **新增 A.18（AOSP 17 完整新增源码）** | v2 硬性要求 |
| **Linux 6.18 sheaves / io_uring 源码** | 未涉及 | **新增 A.19 整节** | 跨系列基线一致性 |
| **ART 17 ART 内部状态 API** | 未涉及 | **新增 A.20 整节** | API 37+ dumpsys meminfo 增强 |

### 第 3 轮：锐度校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 原有 A.1 ~ A.17 路径 | 完整 | **保留全部 + 加 ART 17 注释** | v1 精华保留 |
| 总结 | A.18 简单 | **新增 A.21 总览（v2 升级总览）** | 实战可查性 |
| 量化自检 | 无 | **附录 C 量化数据自检表（新增 10 条）** | v2 量化要求 |

---

## A.1 ART Runtime 源码

### GC 实现核心

```
art/runtime/gc/
├── allocator/
│   ├── allocator.h                          # Allocator 基类
│   ├── allocator.cc                         # 实现
│   ├── region.h                             # Region 类
│   ├── region.cc                            # Region 实现
│   ├── region_space.h                       # Region Space
│   ├── region_space.cc                      # Region Space 实现
│   ├── rosalloc.h                           # RosAlloc（Region 对象分配器）
│   ├── rosalloc.cc                          # RosAlloc 实现
│   ├── bump_pointer_space.h                 # Bump Pointer Space
│   └── bump_pointer_space.cc                # Bump Pointer Space 实现
├── collector/
│   ├── collector.h                          # Collector 基类
│   ├── collector.cc                         # 实现
│   ├── mark_sweep.h                         # Mark Sweep（基础）
│   ├── mark_sweep.cc                        # 实现
│   ├── concurrent_copying.h                 # CC GC（ART 8+ 默认）
│   ├── concurrent_copying.cc                # 实现
│   ├── partial_mark_sweep.h                 # PMS（ART 11-）
│   ├── partial_mark_sweep.cc                # PMS 实现
│   ├── sticky_mark_sweep.h                  # SMS（AOSP 17 增强）
│   ├── sticky_mark_sweep.cc                 # SMS 实现
│   ├── garbage_collector.h                  # GC 基类
│   └── garbage_collector.cc                 # 实现
├── accounting/
│   ├── read_barrier_table.h                 # Read Barrier Table
│   ├── read_barrier_table.cc                # 实现
│   ├── card_table.h                         # Card Table
│   ├── card_table.cc                        # 实现
│   ├── mod_union_table.h                    # Mod Union Table（分代用）
│   ├── mod_union_table.cc                   # 实现
│   ├── remembered_set.h                     # Remembered Set（分代用）
│   └── remembered_set.cc                    # 实现
├── space/
│   ├── space.h                              # Space 基类
│   ├── space.cc                             # 实现
│   ├── dalvik_space.h                       # Dalvik Space
│   ├── dalvik_space.cc                      # 实现
│   ├── image_space.h                        # Image Space
│   ├── image_space.cc                       # 实现
│   ├── large_object_space.h                 # LOS（大对象空间）
│   ├── large_object_space.cc                # LOS 实现
│   ├── gen_space.h                          # 【AOSP 17 新增】Gen Space（分代用）
│   └── gen_space.cc                         # 【AOSP 17 新增】Gen Space 实现
├── heap.h                                   # Heap 主类
├── heap.cc                                  # Heap 实现
├── heap_info.h                              # Heap Info
├── heap_info.cc                             # 实现
├── reference_processor.h                    # Reference Processor
├── reference_processor.cc                   # 实现
├── reference_queue.h                        # Reference Queue
├── reference_queue.cc                       # 【AOSP 17 强化】Finalizer 池化
├── system_weak.h                            # System Weak（Finalizer / Cleaner）
├── system_weak.cc                           # 实现
└── ...
```

### Heap 关键参数

```
art/runtime/gc/heap.h：
  - kDefaultInitialSize                      # 初始堆（4-8 MB）
  - kDefaultMaximumSize                      # 最大堆（256 MB）
  - kDefaultGrowthLimit                      # 增长限制
  - kMinHeapSize                             # 最小堆
  - kMaxHeapSize                             # 最大堆
  - kTargetUtilization                       # 目标利用率（默认 0.5）
  - kDefaultConcurrentStartingBytes          # 默认并发起始字节
  - kDefaultConcurrency                      # 默认并发度
  -【AOSP 17 新增】kSoftThresholdPercent     # 软阈值（30%）
```

---

## A.2 ART 镜像层 / 编译产物

```
art/runtime/
├── image.h                                  # Image（启动用）
├── image.cc                                 # 实现
├── oat_file.h                               # OAT 文件
├── oat_file.cc                              # 实现
├── oat_quick_method_header.h                # OAT Quick Method Header
├── vdex_file.h                              # VDEX 文件
├── vdex_file.cc                             # 实现
├── dex2oat.h                                # dex2oat 接口
├── dex2oat.cc                               # 实现
├── elf_file.h                               # ELF File
├── elf_file.cc                              # 实现
└── ...
```

---

## A.3 ART JVMTI / Native Debug 源码

```
art/openjdkjvm/
├── OpenjdkJvm.cc                            # JVMTI 主实现
├── ti/
│   ├── ti_env.h                             # JVMTI Env
│   ├── ti_env.cc                            # 实现
│   ├── ti_heap.h                            # JVMTI Heap
│   ├── ti_heap.cc                           # 实现（含 GC 回调）
│   ├── ti_object.h                          # JVMTI Object
│   ├── ti_object.cc                         # 实现
│   ├── ti_thread.h                          # JVMTI Thread
│   ├── ti_thread.cc                         # 实现
│   ├── ti_class.h                           # JVMTI Class
│   ├── ti_class.cc                          # 实现
│   ├── ti_method.h                          # JVMTI Method
│   ├── ti_method.cc                         # 实现
│   ├── ti_field.h                           # JVMTI Field
│   ├── ti_field.cc                          # 实现
│   └── ...
├── include/
│   └── jvmti.h                              # JVMTI 头文件
└── ...
```

---

## A.4 ART Profile / Saver 源码

```
art/profman/
├── profman.cc                               # profman 主程序
├── profile_assistant.h                      # Profile Assistant
├── profile_assistant.cc                     # 实现
└── ...

art/runtime/
├── profile_saver.h                          # Profile Saver
├── profile_saver.cc                         # 实现
└── ...

art/cmdline/
├── cmdline_parser.h                         # Command Line Parser
├── cmdline_parser.cc                        # 实现
├── parsed_options.h                         # Parsed Options
├── parsed_options.cc                        # 实现
├── runtime_options.h                        # Runtime Options
└── runtime_options.cc                       # 实现
```

---

## A.5 ART JIT 源码

```
art/jit/
├── jit.h                                    # JIT 主类
├── jit.cc                                   # 实现
├── jit_code_cache.h                         # JIT Code Cache
├── jit_code_cache.cc                        # 实现
├── jit_memory_region.h                      # JIT Memory Region
├── jit_memory_region.cc                     # 实现
├── compiled_method.h                        # Compiled Method
├── compiled_method.cc                       # 实现
├── compiled_method_storage.h                # Compiled Method Storage
├── compiled_method_storage.cc               # 实现
├── debugger_interface.h                     # Debugger Interface
├── debug_interface.cc                       # 实现
├── task_driver.h                            # Task Driver
├── task_driver.cc                           # 实现
├── jit_logger.h                             # JIT Logger
├── jit_logger.cc                            # 实现
├── profile_save_thread.h                    # Profile Save Thread
├── profile_save_thread.cc                   # 实现
└── ...
```

---

## A.6 ART Compiler / Optimizing 源码

```
art/compiler/
├── compiled_method.h                        # Compiled Method
├── compiled_method.cc                       # 实现
├── common_compiler_test.h                   # Common Compiler Test
├── common_compiler_test.cc                  # 实现
├── compiler.h                               # Compiler 主类
├── compiler.cc                              # 实现
├── compiled_class.h                         # Compiled Class
├── compiled_class.cc                        # 实现
├── dex/
│   ├── dex_to_dex_compiler.h                # Dex-to-Dex Compiler
│   ├── dex_to_dex_compiler.cc               # 实现
│   ├── verification_results.h               # Verification Results
│   ├── verification_results.cc              # 实现
│   ├── quick/
│   │   ├── quick_compiler.h                 # Quick Compiler
│   │   ├── quick_compiler.cc                # 实现
│   │   ├── mir_to_lir.h                     # MIR to LIR
│   │   └── mir_to_lir.cc                    # 实现
│   └── ...
├── driver/
│   ├── compiler_driver.h                    # Compiler Driver
│   ├── compiler_driver.cc                   # 实现
│   ├── compiled_method_storage.h            # Compiled Method Storage
│   ├── compiled_method_storage.cc           # 实现
│   ├── dex_compilation_unit.h               # Dex Compilation Unit
│   └── dex_compilation_unit.cc              # 实现
├── optimizing/
│   ├── optimizing_compiler.h                # Optimizing Compiler
│   ├── optimizing_compiler.cc               # 实现
│   ├── code_generator.h                     # Code Generator
│   ├── code_generator.cc                    # 实现
│   ├── intrinsics.h                         # Intrinsics
│   ├── intrinsics.cc                        # 实现
│   ├── nodes.h                              # Optimizing Nodes
│   ├── nodes.cc                             # 实现
│   ├── register_allocator.h                 # Register Allocator
│   └── register_allocator.cc                # 实现
└── ...
```

---

## A.7 ART Dex2oat 源码

```
art/dex2oat/
├── dex2oat.cc                               # dex2oat 主程序
├── dex2oat_options.h                        # dex2oat Options
├── dex2oat_options.cc                       # 实现
├── dex2oat_analysis.h                       # dex2oat Analysis
├── dex2oat_analysis.cc                      # 实现
├── dex2oat_compilation_unit.h               # Compilation Unit
├── dex2oat_compilation_unit.cc              # 实现
├── image_writer.h                           # Image Writer
├── image_writer.cc                          # 实现
├── image_stream.h                           # Image Stream
├── image_stream.cc                          # 实现
├── oat_writer.h                             # Oat Writer
├── oat_writer.cc                            # 实现
├── dex_compilation_unit.h                   # Dex Compilation Unit
├── dex_compilation_unit.cc                  # 实现
├── compiler_driver.h                        # Compiler Driver
├── compiler_driver.cc                       # 实现
├── dex_file_validator.h                     # Dex File Validator
├── dex_file_validator.cc                    # 实现
├── file_writer.h                            # File Writer
├── file_writer.cc                           # 实现
├── linkerdriver.h                           # Linker Driver
├── linkerdriver.cc                          # 实现
└── ...
```

---

## A.8 ART Image 源码

```
art/runtime/
├── image.h                                  # Image
├── image.cc                                 # 实现
├── oat_file.h                               # Oat File
├── oat_file.cc                              # 实现
├── elf_file.h                               # ELF File
├── elf_file.cc                              # 实现
├── dex_file.h                               # Dex File
├── dex_file.cc                              # 实现
├── dex_file_loader.h                        # Dex File Loader
├── dex_file_loader.cc                       # 实现
├── dex_file_verifier.h                      # Dex File Verifier
├── dex_file_verifier.cc                     # 实现
├── dex_file_types.h                         # Dex File Types
├── dex_file_types.cc                        # 实现
├── dex_instruction.h                        # Dex Instruction
├── dex_instruction.cc                       # 实现
├── dex_instruction_list.h                   # Dex Instruction List
├── dex_instruction_list.cc                  # 实现
├── dex_instruction_utils.h                  # Dex Instruction Utils
└── dex_instruction_utils.cc                 # 实现
```

---

## A.9 ART ADB / shell 源码

```
frameworks/base/
├── core/java/android/os/
│   ├── Debug.java                           # Debug.MemoryInfo
│   ├── Debug.java                           # Debug.getMemoryInfo()
│   ├── Debug.java                           #【AOSP 17 增强】Debug.dumpHeap() Heap Dump API
│   ├── Debug.java                           #【AOSP 17 增强】Debug.getMemoryInfo() 增强（ART 内部状态）
│   ├── StrictMode.java                      # Strict Mode
│   ├── Trace.java                           # Trace（ATRACE）
│   └── ...
├── core/java/android/app/
│   ├── ActivityThread.java                  # ActivityThread（持有 Daemons）
│   ├── Activity.java                        # Activity
│   ├── Application.java                     # Application
│   ├── ApplicationLoaders.java              # ApplicationLoaders
│   ├── LoadedApk.java                       # LoadedApk
│   ├── ContextImpl.java                     # ContextImpl（mResources / mTheme）
│   ├── LoadedApk.java                       # LoadedApk（mResources / mClassLoader）
│   └── ...
├── core/java/android/content/
│   ├── Context.java                         # Context（getApplicationContext）
│   ├── ContextWrapper.java                  # ContextWrapper
│   └── ...
├── core/java/android/content/pm/
│   └── ...
├── core/java/android/content/res/
│   ├── Resources.java                       # Resources（Theme）
│   ├── ResourcesImpl.java                   # ResourcesImpl
│   └── ...
├── core/java/android/view/
│   ├── View.java                            # View（onDetachedFromWindow）
│   ├── ViewRootImpl.java                    # ViewRootImpl（持有 Surface）
│   ├── Window.java                          # Window
│   ├── WindowManagerGlobal.java             # WindowManagerGlobal
│   ├── InputManager.java                    # InputManager
│   ├── Choreographer.java                   # Choreographer
│   └── ...
├── core/java/android/window/
│   ├── WindowManager.java                   # WindowManager
│   └── ...
├── core/java/android/app/
│   ├── ActivityManager.java                 # ActivityManager
│   ├── ActivityManagerService.java          # AMS
│   └── ...
└── core/java/com/android/internal/util/
    └── ...
```

---

## A.10 Framework 服务端源码

```
frameworks/base/services/
├── core/java/com/android/server/
│   ├── SystemServer.java                    # SystemServer（启动 AMS / WMS / PKMS 等）
│   ├── SystemService.java                   # SystemService 基类
│   ├── SystemServiceManager.java            # SystemServiceManager
│   ├── ServiceThread.java                   # ServiceThread
│   ├── HandlerThread.java                   # HandlerThread
│   ├── IntentFirewall.java                  # Intent Firewall
│   ├── IntentResolver.java                  # Intent Resolver
│   ├── IntentFilter.java                    # Intent Filter
│   ├── Intent.java                          # Intent
│   ├── am/
│   │   ├── ActivityManagerService.java      # AMS（dumpsys meminfo 实现）
│   │   ├── ActivityManagerService.java      #【AOSP 17 增强】dumpApplicationMemoryUsage 新增 ART 内部状态
│   │   ├── ProcessList.java                 # ProcessList
│   │   ├── ProcessRecord.java               # ProcessRecord
│   │   ├── ProcessStatsService.java         # Process Stats
│   │   ├── OomAdjuster.java                 # OOM 调整
│   │   ├── LowMemoryDetector.java           # Low Memory Detector
│   │   ├── MemoryStatUtil.java              # Memory Stat Util
│   │   ├── CachedAppOptimizer.java          # Cached App Optimizer
│   │   └── ...
│   ├── wm/
│   │   ├── WindowManagerService.java        # WMS
│   │   ├── ActivityTaskManagerService.java  # ATMS
│   │   └── ...
│   ├── pm/
│   │   ├── PackageManagerService.java       # PKMS
│   │   └── ...
│   └── ...
├── core/jni/
│   ├── com_android_server_am_ActivityManagerService.cpp  # AMS JNI
│   └── ...
└── ...
```

---

## A.11 Native 堆 / dlmalloc

```
bionic/libc/
├── bionic/
│   ├── malloc_limit.cpp                     # malloc 限制（含 sheaves 适配）
│   ├── malloc_hooked.cpp                    # malloc 钩子
│   ├── malloc_debug.cpp                     # malloc 调试
│   ├── malloc_leak.cpp                      # malloc 泄漏检测
│   └── ...
├── stdlib/
│   ├── malloc.cpp                           # dlmalloc 实现
│   ├── free.cpp                             # free 实现
│   └── ...
└── ...

external/jemalloc/                           # jemalloc（部分设备使用）
└── ...
```

---

## A.12 Hprof / Heap Dump

```
art/runtime/hprof/
├── hprof.h                                  # Hprof 主类
├── hprof.cc                                 # 实现
├── hprof.cc#WriteHeapDump                   #【AOSP 17 增强】新增 Class Extent / GenInfo / GCRootIndex
├── hprof.cc#WriteClassExtent                #【AOSP 17 新增】Class Extent 元数据
├── hprof.cc#WriteGenInfo                    #【AOSP 17 新增】GenCC Young/Old 元数据
├── hprof.cc#WriteGCRootIndex                #【AOSP 17 新增】GC Root 索引

external/robolectric-shadows/hprof-conv/      # hprof-conv 工具
├── src/main/java/                           # Java 实现
└── ...

external/eclipse-memory-analyzer/            # MAT 工具
├── plugins/
│   ├── org.eclipse.mat.api/                 # MAT API
│   ├── org.eclipse.mat.parser/              # MAT 解析器
│   └── ...
└── ...
```

---

## A.13 Perfetto / Trace

```
art/runtime/
├── trace.h                                  # Trace 主类
├── trace.cc                                 # 实现
├── atrace.h                                 # ATRACE
├── atrace.cc                                # 实现

external/perfetto/
├── include/perfetto/                        # Perfetto 头文件
├── src/                                     # Perfetto 实现
└── ...

system/extras/perfetto/
├── perfetto.rc                              # Perfetto 启动配置
└── ...
```

---

## A.14 工具 / Shark / LeakCanary / MAT

```
external/leakcanary/
├── leakcanary-android/                      # LeakCanary Android 模块
├── leakcanary-android-core/                 # 核心
├── leakcanary-android-instrumentation/      # Android Test
├── leakcanary-android-process/              # 进程监控
├── shark/                                   # Shark 引擎
│   ├── src/main/java/shark/                 # Shark 实现
│   ├── AndroidObjectInspectors.kt           #【AOSP 17 适配】类去重、FinalReference
│   └── ...
├── leakcanary-android-utils/                # 工具类
└── ...

external/eclipse-memory-analyzer/            # MAT 工具
└── ...
```

---

## A.15 测试

```
art/test/
├── 003-omnibus-opcodes/                     # 基础测试
├── 004-ThreadStress/                        # 线程压力
├── 051-thread-suspension/                   # 线程挂起
├── 071-dexfile-stress/                      # Dex 压力
├── 100-reflect2/                            # 反射测试
├── 102-fluent-builder/                      # 链式构造
└── ...

art/runtime/gc/heap_test.cc                  # GC 单元测试
art/runtime/gc/collector/concurrent_copying_test.cc  # CC GC 测试
art/runtime/gc/collector/sticky_mark_sweep_test.cc   # SMS 测试

test/
├── 001-Main/                                # 基础测试
├── 002-StaticInstanceField/                 # 静态字段
├── 003-omnibus-opcodes/                     # 全部 opcodes
├── 004-ThreadStress/                        # 线程压力
└── ...
```

---

## A.16 头文件 / 常量

```
art/runtime/
├── globals.h                                # 全局常量
│  - kPageSize                              # 4KB
│  - kArm64StackAlignment                   # 16 bytes
│  - kMips64StackAlignment                  # 16 bytes
│  - kX86_64StackAlignment                  # 16 bytes
│  - kObjectAlignment                       # 8 bytes
│  - kArtMethodAlignment                    # 16 bytes
│  - kJniEnvSize                            # JNIEnv size
│  - kPageByteSize                          # 4096
│  - kWordSize                              # 4 (32-bit) / 8 (64-bit)
├── base/
│   ├── logging.h                            # 日志
│   ├── mutex.h                              # 互斥
│   ├── mem_map.h                            # Memory Map
│   ├── os.h                                 # OS 接口
│   ├── timing_logger.h                      # 时间日志
│   ├── histogram.h                          # 直方图
│   ├── stringprintf.h                       # 字符串格式化
│   ├── casts.h                              # 类型转换
│   ├── endian.h                             # 字节序
│   ├── scoped_flock.h                       # 文件锁
│   ├── unix_file/                           # Unix 文件
│   │   ├── fd_file.h                        # FD File
│   │   └── ...
│   ├── value_object.h                       # Value Object
│   └── ...
└── ...
```

---

## A.17 ART 关键全局变量 / 常量

```
art/runtime/
├── globals.h                                # 全局常量
│  - kPageSize                              # 4KB
│  - kArm64StackAlignment                   # 16 bytes
│  - kMips64StackAlignment                  # 16 bytes
│  - kX86_64StackAlignment                  # 16 bytes
│  - kObjectAlignment                       # 8 bytes
│  - kArtMethodAlignment                    # 16 bytes
│  - kJniEnvSize                            # JNIEnv size
│  - kPageByteSize                          # 4096
│  - kWordSize                              # 4 (32-bit) / 8 (64-bit)
└── ...

art/runtime/gc/
├── heap.h                                   # Heap 常量
│  - kDefaultInitialSize                    # 初始堆
│  - kDefaultMaximumSize                    # 最大堆
│  - kDefaultGrowthLimit                    # 增长限制
│  - kMinHeapSize                           # 最小堆
│  - kMaxHeapSize                           # 最大堆
│  - kTargetUtilization                     # 目标利用率（默认 0.5）
│  - kDefaultConcurrentStartingBytes        # 默认并发起始字节
│  - kDefaultConcurrency                    # 默认并发度
│  -【AOSP 17 新增】kSoftThresholdPercent   # 软阈值（30%）
└── ...
```

---

## A.18 【AOSP 17 新增】ART 17 核心新增源码

> **本节为 v2 升级新增**——列出 AOSP 17 相对 AOSP 14 的核心新增源码。

### A.18.1 分代 GC（GenCC）核心

```
art/runtime/gc/
├── collector/
│   ├── sticky_mark_sweep.h                  # 【AOSP 17 强化】SMS（Sticky Mark Sweep）
│   ├── sticky_mark_sweep.cc                 # SMS 实现
│   ├── concurrent_copying.h                 # 【AOSP 17 强化】CC GC 强化分代
│   ├── concurrent_copying.cc                # CC GC 实现（含 GenCC）
├── accounting/
│   ├── mod_union_table.h                    # 【AOSP 17 新增】Mod Union Table
│   ├── mod_union_table.cc                   # 实现
│   ├── remembered_set.h                     # 【AOSP 17 新增】Remembered Set
│   └── remembered_set.cc                    # 实现
├── space/
│   ├── gen_space.h                          # 【AOSP 17 新增】Gen Space（分代用）
│   └── gen_space.cc                         # 【AOSP 17 新增】Gen Space 实现
├── heap.h                                   # 【AOSP 17 强化】kSoftThresholdPercent
├── heap.cc                                  # 【AOSP 17 强化】ShouldConcurrentCollect 软阈值判断
└── options.h                                # 【AOSP 17 新增】kSoftThresholdPercent=30
```

### A.18.2 类去重（Class Deduplication）

```
art/runtime/gc/
├── class_linker.h                           # 【AOSP 17 强化】类去重接口
├── class_linker.cc                          # 【AOSP 17 强化】ClassDeduplication 实现
└── ...
```

### A.18.3 Finalizer 池化

```
art/runtime/gc/
├── reference_queue.h                        # 【AOSP 17 强化】Finalizer 池化（4 线程）
├── reference_queue.cc                       # 实现
├── thread.h                                 # 【AOSP 17 强化】CreateFinalizerThread
├── thread.cc                                # 【AOSP 17 强化】多 Finalizer 线程
└── ...
```

### A.18.4 Hprof 新增元数据

```
art/runtime/hprof/
├── hprof.cc#WriteHeapDump                   # 【AOSP 17 增强】整合所有新增元数据
├── hprof.cc#WriteClassExtent                # 【AOSP 17 新增】Class Extent 元数据
├── hprof.cc#WriteGenInfo                    # 【AOSP 17 新增】GenCC Young/Old 元数据
├── hprof.cc#WriteGCRootIndex                # 【AOSP 17 新增】GC Root 索引
└── ...
```

### A.18.5 ART 内部状态 API（dumpsys meminfo 增强）

```
art/runtime/gc/
├── heap.h#GetGcStats                        # 【AOSP 17 新增】GC 统计接口
├── heap.cc#GetGcStats                       # 实现
├── jit/jit_code_cache.h#GetCodeCacheStats   # 【AOSP 17 新增】JIT Code Cache 状态
├── jni/jni_env_ext.h#GetJNIRefsStats        # 【AOSP 17 新增】JNI refs 统计

frameworks/base/core/java/android/os/
├── Debug.java#dumpHeap                      # 【AOSP 17 增强】Heap Dump API 优化
└── ...

frameworks/base/services/core/java/com/android/server/am/
├── ActivityManagerService.java#dumpApplicationMemoryUsage  # 【AOSP 17 增强】输出 ART Internal State
└── ...
```

---

## A.19 【Linux 6.18 新增】sheaves / io_uring 源码

> **本节为 v2 升级新增**——列出 Linux 6.18 的核心新增源码（与 ART 17 配套）。

### A.19.1 sheaves 内存分配器

```
kernel/mm/
├── slab_common.c                            # 【Linux 6.18 新增】sheaves slab 实现
├── slab.h                                   # sheaves 数据结构
├── slub.c                                   # SLUB 适配 sheaves
└── ...
```

### A.19.2 io_uring 增强

```
kernel/
├── io_uring.c                               # 【Linux 6.18 增强】io_uring 性能优化
├── io_uring.h                               # io_uring 接口
└── ...
```

### A.19.3 smaps_rollup

```
fs/proc/
├── task_mmu.c                               # 【Linux 6.18 新增】smaps_rollup 实现
└── ...
```

---

## A.20 【AOSP 17 + Linux 6.18 关联】ART 内部状态 API

### A.20.1 GC 状态 API

```
art/runtime/gc/
├── heap.h                                   # GetGcStats 接口
│   struct GcStats {
│     uint64_t cumulative_gc_count;          // 累计 GC 次数
│     uint64_t cumulative_gc_time_ns;        // 累计 GC 耗时（纳秒）
│     uint64_t last_gc_time_ns;              // 上次 GC 耗时
│     const char* last_gc_type;              // 上次 GC 类型（Young/Old/Full）
│   };
└── ...
```

### A.20.2 JIT 状态 API

```
art/runtime/jit/
├── jit_code_cache.h                         # GetCodeCacheStats 接口
│   struct CodeCacheStats {
│     size_t code_cache_size;                // Code Cache 大小
│     size_t code_cache_used;                // 已使用
│     size_t num_compiled_methods;           // 已编译方法数
│   };
└── ...
```

### A.20.3 JNI refs 状态 API

```
art/runtime/jni/
├── jni_env_ext.h                            # GetJNIRefsStats 接口
│   struct JNIRefsStats {
│     size_t global_refs;                    // Global refs 数
│     size_t local_refs;                     // Local refs 数
│     size_t weak_global_refs;               // Weak global refs 数
│   };
└── ...
```

### A.20.4 ClassLoader 状态 API

```
art/runtime/
├── class_linker.h                           # GetClassLoaderStats 接口
│   struct ClassLoaderStats {
│     size_t num_class_loaders;              // ClassLoader 数
│     size_t num_loaded_classes;             // 已加载类数
│     size_t num_deduplicated_classes;       // 【AOSP 17 新增】去重后类数
│   };
└── ...
```

---

## A.21 总结（v2 升级总览）

### A.21.1 v1 → v2 增补总览

```
A.1 ~ A.2：ART Runtime GC + 镜像层（核心，保留 + ART 17 注释）
A.3：JVMTI + Native Debug（诊断，保留）
A.4 ~ A.5：Profile + JIT（GC 触发，保留 + ART 17 增强注释）
A.6 ~ A.8：Compiler + Image（GC 关联，保留）
A.9 ~ A.10：Framework（Activity / AMS，保留 + ART 17 dumpsys meminfo 增强注释）
A.11：dlmalloc（Native 堆，保留 + sheaves 适配注释）
A.12：Hprof（Heap Dump，保留 + ART 17 新增元数据注释）
A.13：Perfetto / Trace（保留）
A.14：工具（Shark / LeakCanary / MAT，保留 + LeakCanary 3.x 注释）
A.15：测试（保留）
A.16 ~ A.17：头文件 / 常量（保留 + ART 17 新增 kSoftThresholdPercent）

【v2 新增】
A.18：ART 17 核心新增源码（GenCC + 类去重 + Finalizer 池化 + Hprof 新增元数据 + ART 内部状态 API）
A.19：Linux 6.18 新增源码（sheaves + io_uring + smaps_rollup）
A.20：ART 内部状态 API（GC / JIT / JNI / ClassLoader）
A.21：v2 升级总览（本节）
```

### A.21.2 跨系列引用

- **本附录引用**：
  - A.1 ~ A.2：正文 9.1 - 9.10 全部章节
  - A.3：JVMTI 部分（[06-JVMTI监控GC](../06-JVMTI监控GC.md) 衔接）
  - A.11：Native 堆 / dlmalloc / sheaves
  - A.12：Heap Dump + ART 17 新增元数据
  - A.13：Perfetto / Trace（[05-Perfetto中的GC事件](../05-Perfetto中的GC事件.md) 衔接）
  - A.14：工具章节（[03-LeakCanary原理](../03-LeakCanary原理.md) / [04-MAT使用指南](../04-MAT使用指南.md) 衔接）
  - A.15：测试场景
  - A.16 ~ A.17：头文件 / 常量

- **本附录被引用**：
  - 正文 9.1 - 9.10 全部章节
  - 附录 B（路径对账）—— 验证本附录路径
  - 附录 D（工程基线）—— 本附录作为工程基线参考

---

## 附录 B：核心源码路径速查（精简版）

> **本节为 v2 升级新增**——将 A.1 ~ A.20 的核心路径整理为速查表，方便快速定位。

### B.1 GC 诊断最常用的 10 个源文件

| # | 文件 | 完整路径 | 用途 |
| :-- | :--- | :--- | :--- |
| 1 | heap.h | `art/runtime/gc/heap.h` | Heap 主类 + kSoftThresholdPercent |
| 2 | heap.cc | `art/runtime/gc/heap.cc` | Heap 实现 + ShouldConcurrentCollect |
| 3 | concurrent_copying.cc | `art/runtime/gc/collector/concurrent_copying.cc` | CC GC + GenCC |
| 4 | reference_queue.cc | `art/runtime/gc/reference_queue.cc` | Reference + Finalizer 池化 |
| 5 | class_linker.cc | `art/runtime/gc/class_linker.cc` | ClassDeduplication |
| 6 | hprof.cc | `art/runtime/hprof/hprof.cc` | Heap Dump + Class Extent |
| 7 | ActivityManagerService.java | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | dumpsys meminfo + ART 内部状态 |
| 8 | Debug.java | `frameworks/base/core/java/android/os/Debug.java` | Debug.MemoryInfo + Heap Dump API |
| 9 | options.h | `art/runtime/options.h` | kSoftThresholdPercent=30 |
| 10 | slab_common.c | `kernel/mm/slab_common.c` | sheaves 内存分配器 |

### B.2 AOSP 17 新增源文件 10 个

| # | 文件 | 完整路径 | 用途 |
| :-- | :--- | :--- | :--- |
| 1 | gen_space.h/cc | `art/runtime/gc/space/gen_space.{h,cc}` | Gen Space（分代用） |
| 2 | mod_union_table.h/cc | `art/runtime/gc/accounting/mod_union_table.{h,cc}` | Mod Union Table |
| 3 | remembered_set.h/cc | `art/runtime/gc/accounting/remembered_set.{h,cc}` | Remembered Set |
| 4 | sticky_mark_sweep.h/cc | `art/runtime/gc/collector/sticky_mark_sweep.{h,cc}` | SMS（Sticky Mark Sweep） |
| 5 | WriteClassExtent | `art/runtime/hprof/hprof.cc#WriteClassExtent` | Class Extent 元数据 |
| 6 | WriteGenInfo | `art/runtime/hprof/hprof.cc#WriteGenInfo` | GenCC Young/Old 元数据 |
| 7 | WriteGCRootIndex | `art/runtime/hprof/hprof.cc#WriteGCRootIndex` | GC Root 索引 |
| 8 | CreateFinalizerThread | `art/runtime/thread.cc#CreateFinalizerThread` | Finalizer 池化（4 线程） |
| 9 | GetGcStats | `art/runtime/gc/heap.h#GetGcStats` | GC 状态 API |
| 10 | ClassDeduplication | `art/runtime/gc/class_linker.cc#ClassDeduplication` | 类去重 |

### B.3 Linux 6.18 新增源文件 5 个

| # | 文件 | 完整路径 | 用途 |
| :-- | :--- | :--- | :--- |
| 1 | slab_common.c | `kernel/mm/slab_common.c` | sheaves 内存分配器 |
| 2 | io_uring.c | `kernel/io_uring.c` | io_uring 性能优化 |
| 3 | task_mmu.c | `fs/proc/task_mmu.c` | smaps_rollup |
| 4 | slab.h | `kernel/mm/slab.h` | sheaves 数据结构 |
| 5 | slub.c | `kernel/mm/slub.c` | SLUB 适配 sheaves |

---

## 附录 C：量化数据自检表

| # | 量化描述 | 数量级 | 备注 |
| :-- | :--- | :--- | :--- |
| 1 | 本附录索引的源文件 | 300+ 文件 | A.1 ~ A.20 |
| 2 | **AOSP 17 新增源文件** | **10 个** | 见 B.2 |
| 3 | **Linux 6.18 新增源文件** | **5 个** | 见 B.3 |
| 4 | ART 17 新增元数据 | 3 类（Class Extent / GenInfo / GCRootIndex） | hprof 增强 |
| 5 | ART 17 内部状态 API | 4 类（GC / JIT / JNI / ClassLoader） | dumpsys meminfo 增强 |
| 6 | Finalizer 线程数 | 1 线程（AOSP 14）→ 4 线程（AOSP 17） | 池化 |
| 7 | 类去重 Class 节省 | 30-50% | metaspace 节省 |
| 8 | sheaves Native 堆节省 | 15-20% | Linux 6.18 + AOSP 17 |
| 9 | hprof-conv 转换加速 | 3 倍 | io_uring 优化 |
| 10 | GC Root 路径查找加速 | 5-10 倍 | GCRootIndex 索引 |

---

## 附录 D：工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 | AOSP 17 变化 |
| :--- | :--- | :--- | :--- | :--- |
| ART 源码路径 | `art/runtime/` | 通用 | 注意子目录分类 | AOSP 17 新增 gen_space 等 |
| Framework 源码 | `frameworks/base/` | 通用 | 注意 services vs core | AOSP 17 dumpsys 增强 |
| Native 堆 | `bionic/libc/` | 通用 | 注意 malloc_debug | AOSP 17 sheaves 适配 |
| Hprof 工具 | `art/runtime/hprof/` | 通用 | 注意 AOSP 17 新元数据 | **AOSP 17 新增** |
| Perfetto | `external/perfetto/` | 通用 | 注意版本兼容性 | 不变 |
| LeakCanary | `external/leakcanary/` | 必须 3.x | 2.x 在 AOSP 17 误报 | **必须升级 3.x** |
| MAT | `external/eclipse-memory-analyzer/` | 必须 1.14.0+ | 1.13 解析 AOSP 17 报错 | **必须升级 1.14.0+** |
| Linux 6.18 源码 | `kernel/mm/` + `kernel/io_uring.c` | AOSP 17 配套 | 注意版本 | **基线纠正** |

---

> **下一篇附录**：[B-路径对账](B-路径对账.md) 提供"已验证路径 vs 错误路径"对照表（重写为 v2 升级版）。
