# 附录 A：源码索引（按文件路径）

> **本附录列出 GC 诊断与治理涉及的全部 AOSP 源码路径**，按文件路径字母序排列，可直接跳转。

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
│   ├── partial_mark_sweep.cc                # 实现
│   ├── generational_cc.h                    # GenCC（ART 14+）
│   ├── generational_cc.cc                   # 实现
│   ├── immune_spaces.h                      # Immune Spaces
│   └── immune_spaces.cc                     # 实现
├── accounting/
│   ├── mod_union_table.h                    # Mod Union Table
│   ├── mod_union_table.cc                   # 实现
│   ├── card_table.h                         # Card Table
│   ├── card_table.cc                        # 实现
│   ├── read_barrier.h                       # Read Barrier（CC GC）
│   ├── read_baranger_table.h                # Read Barrier Table
│   └── read_barrier_table.cc                # 实现
├── reference_queue.h                        # Reference Queue
├── reference_queue.cc                       # 实现
├── reference_processor.h                    # Reference Processor
├── reference_processor.cc                   # 实现
├── heap.h                                   # Heap 主类
├── heap.cc                                  # Heap 实现
├── heap_task_daemon.h                       # HeapTaskDaemon
├── heap_task_daemon.cc                      # 实现
├── finalizer_task.h                         # Finalizer Task（FinalizerDaemon 调度）
├── finalizer_task.cc                        # 实现
├── finalizer_reference.h                    # FinalizerReference
├── finalizer_reference.cc                   # 实现
├── system_weak.h                            # System Weak References
├── system_weak.cc                           # 实现
├── space.h                                  # Space 基类
├── space.cc                                 # 实现
├── visited_objects.h                        # Visited Objects
├── visited_objects.cc                       # 实现
├── verification.h                           # GC 验证
├── verification.cc                          # 实现
├── write_barrier.h                          # Write Barrier（ART 7+）
├── write_barrier.cc                         # 实现
├── scoped_gc_critical_section.h             # GC Critical Section
├── scoped_gc_critical_section.cc            # 实现
├── gc_cause.h                               # GcCause 枚举
├── gc_cause.cc                              # 实现
├── gc_type.h                                # GcType 枚举
└── gc_type.cc                               # 实现
```

### A.2 ART Java 镜像层源码

```
art/runtime/
├── class_linker.h                           # Class Linker（mirror::Class）
├── class_linker.cc                          # 实现
├── thread.h                                 # Thread 主类
├── thread.cc                                # 实现
├── mirror/
│   ├── object.h                             # mirror::Object 基类
│   ├── object.cc                            # 实现
│   ├── object-inl.h                         # inline 实现
│   ├── class.h                              # mirror::Class
│   ├── class.cc                             # 实现
│   ├── array.h                              # mirror::Array
│   ├── array.cc                             # 实现
│   ├── string.h                             # mirror::String
│   ├── string.cc                            # 实现
│   ├── reference.h                          # mirror::Reference
│   ├── reference.cc                         # 实现
│   ├── class_loader.h                       # ClassLoader
│   ├── class_loader.cc                      # 实现
│   ├── iftable.h                            # Interface Table
│   └── iftable.cc                           # 实现
├── indirect_reference_table.h               # JNI Indirect Ref Table
├── indirect_reference_table.cc              # 实现
├── jni/
│   ├── jni_env_ext.h                        # JNIEnvExt
│   ├── jni_env_ext.cc                       # 实现
│   ├── java_vm_ext.h                        # JavaVMExt
│   └── java_vm_ext.cc                       # 实现
├── check_reference_map_visitor.h            # Reference Map 校验
├── check_reference_map_visitor.cc           # 实现
├── fault_handler.h                          # Fault Handler（access fault）
├── fault_handler.cc                         # 实现
├── instrumentation.h                        # Instrumentation（GC hook）
├── instrumentation.cc                       # 实现
├── monitor.h                                # Monitor（synchronized）
├── monitor.cc                               # 实现
├── monitor_pool.h                           # Monitor Pool
├── monitor_pool.cc                          # 实现
├── intern_table.h                           # String Intern Table
├── intern_table.cc                          # 实现
├── thread_pool.h                            # Thread Pool
├── thread_pool.cc                           # 实现
├── barrier.h                                # Barrier
├── barrier.cc                               # 实现
└── gc/
    ├── root_visitor.h                       # GC Root Visitor
    ├── root_visitor.cc                      # 实现
    └── ...
```

### A.3 JVMTI / Native Debug 源码

```
art/openjdkjvm/
├── OpenjdkJvm.cc                            # OpenjdkJvm 主类（注册 JVMTI 事件）
├── dlmalloc.cc                              # dlmalloc 实现（Native 分配）
└── ...

art/runtime/
├── ti/
│   ├── ti_env.h                             # JVMTI Env 封装
│   ├── ti_env.cc                            # 实现
│   ├── ti_class.h                           # JVMTI Class
│   ├── ti_class.cc                          # 实现
│   ├── ti_method.h                          # JVMTI Method
│   ├── ti_method.cc                         # 实现
│   ├── ti_monitor.h                         # JVMTI Monitor
│   ├── ti_monitor.cc                        # 实现
│   ├── ti_thread.h                          # JVMTI Thread
│   ├── ti_thread.cc                         # 实现
│   ├── ti_heap.h                            # JVMTI Heap
│   ├── ti_heap.cc                           # 实现
│   ├── ti_search.h                          # JVMTI Search
│   ├── ti_search.cc                         # 实现
│   ├── ti_stack.h                           # JVMTI Stack
│   ├── ti_stack.cc                          # 实现
│   ├── ti_phase.h                           # JVMTI Phase
│   ├── ti_phase.cc                          # 实现
│   ├── ti_redefine.h                        # JVMTI Redefine
│   └── ti_redefine.cc                       # 实现
├── debug/
│   ├── debug.h                              # Debug 工具
│   ├── debug.cc                             # 实现
│   ├── deopt.h                              # Deoptimization
│   ├── deopt.cc                             # 实现
│   ├── elf_debug_writer.h                   # ELF Debug Writer
│   ├── elf_debug_writer.cc                  # 实现
│   ├── jit_debugger_interface.h             # JIT Debugger Interface
│   └── jit_debugger_interface.cc            # 实现
├── trace.h                                  # Trace 主类
├── trace.cc                                 # 实现
└── ...
```

### A.4 Profile / Heapsnapper 源码

```
art/profman/
├── profman.cc                               # profman 主程序
├── profile_boot_info.h                     # Boot Profile Info
├── profile_boot_info.cc                    # 实现
├── profile_compilation_info.h               # Compilation Info
├── profile_compilation_info.cc              # 实现
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

### A.5 ART JIT 源码

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

### A.6 ART Compiler / Optimizing 源码

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

### A.7 ART Dex2oat 源码

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

### A.8 ART Image 源码

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

### A.9 ART ADB / shell 源码

```
frameworks/base/
├── core/java/android/os/
│   ├── Debug.java                           # Debug.MemoryInfo
│   ├── Debug.java                           # Debug.getMemoryInfo()
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

### A.10 Framework 服务端源码

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
│   ├── Process.java                         # Process
│   ├── ProcessList.java                     # ProcessList
│   ├── ProcessRecord.java                   # ProcessRecord（AMS）
│   ├── ActivityRecord.java                  # ActivityRecord（AMS）
│   ├── TaskRecord.java                      # TaskRecord（AMS）
│   ├── ActivityStack.java                  # ActivityStack（AMS）
│   ├── ActivityTaskSupervisor.java          # ActivityTaskSupervisor
│   ├── AppErrors.java                       # AppErrors（Crash / ANR）
│   ├── ErrorDialogs.java                    # ErrorDialogs
│   ├── Watchdog.java                        # Watchdog（10 秒超时）
│   ├── InputManagerService.java             # InputManagerService
│   ├── ActivityManagerService.java          # ActivityManagerService
│   ├── WindowManagerService.java            # WindowManagerService
│   ├── SurfaceFlinger.cpp / .h              # SurfaceFlinger
│   ├── DisplayPowerController.java          # DisplayPowerController
│   ├── Looper.java                          # Looper
│   └── ...
└── ...
```

### A.11 Native 层 / dlmalloc 源码

```
bionic/
├── libc/
│   ├── malloc_debug/                        # malloc debug 实现
│   ├── dlmalloc/                            # dlmalloc 源码
│   │   ├── dlmalloc.c                       # dlmalloc 主文件
│   │   ├── malloc.c                         # malloc 实现
│   │   └── ...
│   ├── bionic/
│   │   ├── malloc.cpp                       # bionic malloc 封装
│   │   ├── malloc.h                         # malloc 头
│   │   ├── heap.cpp                         # heap 实现
│   │   └── ...
│   └── stdlib/
│       └── ...
└── libc/                                   # libc 头文件
    ├── include/
    │   ├── malloc.h                         # malloc 头
    │   ├── jni.h                            # JNI 头
    │   └── ...
    └── ...
```

### A.12 Hprof / Heap Dump 源码

```
art/runtime/
├── hprof/
│   ├── hprof.h                              # Hprof 主类
│   ├── hprof.cc                             # Hprof 实现
│   └── ...
├── heap.cc (DumpHeap)                       # Heap::DumpHeap 实现
├── heap.h (DumpHeap)                        # 头文件
└── ...

frameworks/base/
├── core/java/android/os/
│   └── Debug.java (dumpHprofData)           # Debug.dumpHprofData
└── ...

system/core/
├── shmem/                                   # shmem 实现
└── ...
```

### A.13 Perfetto / Trace 源码

```
system/extras/
├── perfetto/                                # Perfetto 主项目
│   ├── protos/                              # Perfetto Protobuf
│   ├── src/                                 # Perfetto 源码
│   └── ...
├── simpleperf/                              # simpleperf（CPU 采样）
└── ...

art/runtime/
├── trace.h                                  # Trace 主类
├── trace.cc                                 # 实现
├── atrace.h                                 # ATRACE
├── atrace.cc                                # 实现
└── ...
```

### A.14 工具源码

```
external/
├── shark/                                   # LeakCanary Shark 引擎
│   ├── shark/
│   │   ├── Shark.kt                         # Shark 主类
│   │   ├── HeapAnalyzer.kt                  # HeapAnalyzer
│   │   ├── HprofReader.kt                   # HprofReader
│   │   ├── ObjectInspector.kt               # ObjectInspector
│   │   ├── LeakingObjectFinder.kt           # LeakingObjectFinder
│   │   ├── ShortestPathFinder.kt            # ShortestPathFinder
│   │   └── ...
│   └── ...
├── leakcanary/                              # LeakCanary 主项目
│   ├── leakcanary-android/
│   │   ├── AndroidManifest.xml              # Manifest
│   │   └── src/
│   │       └── ...
│   ├── leakcanary-android-instrumentation/  # LeakCanary Android Test
│   └── ...
├── eclipse-memory-analyzer/                 # MAT（Eclipse）
├── hprof-conv/                              # hprof-conv 工具
└── ...
```

### A.15 测试 / Mock 源码

```
art/test/
├── 003-omnibus-opcodes/
├── 004-StackWalk/
├── 005-annotations/
├── 021-string2/
├── 070-nio-pipe-direct-buffer/              # NIO DirectByteBuffer 测试
├── 096-array-concat/
├── 099-vmdebug/
├── 100-reflect2/
├── 109-suspend-check/
├── 116-nio-bytebuffer/                      # DirectByteBuffer 测试
├── 133-static-invoke/
├── 137-cfi/
├── 138-duplicate-class/
├── 139-register-type-conflict/
├── 141-class-unload/
├── 142-classloader/
├── 143-string-compress/
├── 144-static-field-suspend/
├── 145-alloc-stress/
├── 146-resizable-array/
├── 147-stripped-dex-file/
├── 148-multithread-gc/
├── 149-stillborn-gc/
├── 150-allocator-stress/                    # 分配器压力测试
├── 151-OpenJdksTest/                        # OpenJDK 测试
├── 152-dead-object-stack-walk/
├── 153-monitor-stress/
├── 154-gc-shrink/                           # GC 收缩测试
├── 155-java-stack-shrink/
├── 156-jvmti-shim/
├── 157-MethodHandle/
├── 158-does-jar-contain-class/
├── 159-app-image/
├── 160-read-barrier-stress/
├── 161-clinit/
├── 162-agent-instance/
├── 163-final-field/
├── 164-resizable-jni/
├── 165-instance-of/
├── 166-getsibling/
├── 167-unloading/
├── 168-vmstate-suspend/
├── 169-threadgroup-interrupt/
├── 170-initializing-arrays/
├── 171-suspend-all-threads/
├── 172-suspend-empty-stack/
├── 173-suspend-list-order/
├── 174-busy-alloc/                          # 忙分配测试
├── 175-stack-overflow/
├── 176-app-alloc-tracking/                  # 应用分配追踪
├── 177-visibly-initialized/
├── 178-app-objects-moved/
├── 179-app-image-class-table/
├── 180-array-store/
├── 181-null-array-store/
├── 182-invoke-direct-method/
├── 183-compiler-references/
├── 184-stress-compiler/
├── 185-monitor-info/
├── 186-java-annotations/
├── 187-jit-zygote/
├── 188-jit-write-barrier/
├── 189-miranda/
├── 190-hello-arch/
├── 191-dex2oat-cl-init/
├── 192-jvmti-assertion/
├── 193-mirror-string/
├── 194-closed-range/
├── 195-zero-arg-gc-paused-thread/
├── 196-mutator-on-alloc/
├── 1973-multi-attachment-races/
├── 1974-jvmti-force-early-return/
├── 1975-resizable-stack/
├── 1976-thread-attach-race/
├── 1977-jvmti-stack-extend/
├── 1978-allocate-during-jit/
├── 1979-jvmti-alloc-trace/
└── ...

art/runtime/jit/
├── jit_test.cc                              # JIT 测试
└── ...

art/compiler/
├── common_compiler_test.cc                  # Compiler 测试
└── ...

art/runtime/gc/
├── collector/
│   ├── concurrent_copying_test.cc           # CC GC 测试
│   ├── generational_cc_test.cc              # GenCC 测试
│   ├── mark_sweep_test.cc                   # Mark Sweep 测试
│   └── ...
├── heap_test.cc                             # Heap 测试
└── ...
```

### A.16 ART 头文件索引

```
art/runtime/
├── base/
│   ├── atomic.h                             # 原子操作
│   ├── bit_utils.h                          # Bit Utils
│   ├── casts.h                              # 类型转换
│   ├── common_art_test.h                    # 通用 ART Test 头
│   ├── compiler_filter.h                    # Compiler Filter
│   ├── cstring.h                            # C 字符串
│   ├── endian.h                             # 字节序
│   ├── enum_cast.h                          # Enum Cast
│   ├── globals.h                            # 全局宏
│   ├── hex_dump.h                           # Hex Dump
│   ├── histogram.h                          # Histogram
│   ├── iteration_range.h                    # Iteration Range
│   ├── leb128.h                             # LEB128 编码
│   ├── logging.h                            # Logging
│   ├── macros.h                             # 宏
│   ├── mem_map.h                            # Mem Map
│   ├── mutex.h                              # Mutex
│   ├── nullable.h                           # Nullable
│   ├── operator_equals.h                    # operator== 宏
│   ├── os.h                                 # OS 抽象
│   ├── pointer_size.h                       # Pointer Size
│   ├── profiler_options.h                   # Profiler Options
│   ├── quota.h                              # Quota
│   ├── scoped_flock.h                       # Scoped Flock
│   ├── strlcpy.h                            # strlcpy
│   ├── stringprintf.h                       # String Printf
│   ├── stubs.h                              # Stubs
│   ├── syscall_mman.h                       # Syscall mman
│   ├── syscall_mman_inl.h                   # inline
│   ├── time.h                               # Time
│   ├── transform_referee.h                  # Transform Referee
│   ├── tristate.h                           # Tri-state
│   ├── unix_file/fd_file.h                  # FD File
│   ├── value_object.h                       # Value Object
│   └── ...
├── ...
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
└── ...
```

---

## A.18 总结

- **A.1 ~ A.2**：ART Runtime GC + 镜像层（核心）
- **A.3**：JVMTI + Native Debug（诊断）
- **A.4 ~ A.5**：Profile + JIT（GC 触发）
- **A.6 ~ A.8**：Compiler + Image（GC 关联）
- **A.9 ~ A.10**：Framework（Activity / AMS）
- **A.11**：dlmalloc（Native 堆）
- **A.12**：Hprof（Heap Dump）
- **A.13**：Perfetto / Trace
- **A.14**：工具（Shark / LeakCanary / MAT）
- **A.15**：测试
- **A.16 ~ A.17**：头文件 / 常量

---

## 跨节引用

**本附录引用**：
- A.1 ~ A.2：正文 9.1 - 9.10 全部章节
- A.3：JVMTI 部分
- A.11：Native 堆 / dlmalloc
- A.12：Heap Dump
- A.14：工具章节
- A.15：测试场景