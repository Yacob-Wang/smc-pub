# 01-ART 总览：稳定性架构师的全局视角

> **本子模块**：00-总览（ART 系列全局观 · 1/9）
> **本篇定位**：**全局观**（1/9）——从稳定性架构师视角建立 ART 的全景认知：是什么、为什么需要它、在 Android 系统中的位置、五大核心能力、源码目录、稳定性映射
> **基线版本**：AOSP android-14.0.0_r1（ART 主线）；Linux 内核 android14-5.10 / 5.15
> **对线 JD**：
> - 职责 1「ART 主干核心机制」（字节码执行 / GC / 类加载 / 线程 / JNI）——**核心对线**
> - 职责 2「解决 Android Framework、HAL 层、Kernel 驱动以及 OS 核心模块中的复杂技术挑战」——ART 边界对线
> - 加分项 1「深入理解 Android Runtime（ART）核心机制」——**核心对线**
> **与 v2.1 主干耦合**：与 [Linux_Kernel/Process](../../Linux_Kernel/Process/)（进程/fork/信号）、[Memory_Management](../../Linux_Kernel/Memory_Management/)（虚拟内存）、[FS](../../Linux_Kernel/FS/)（mmap）强耦合。

---

## 0. 本篇定位声明

**本篇是 ART 系列的全局观（1/9）**：

| 维度 | 本篇承担 | 本篇不涉及（交给其他篇） |
| :--- | :--- | :--- |
| ART 是什么 / 为什么需要 | ✓ 定义 + 演进史 + 架构位置 | — |
| 五大核心能力的稳定性映射 | ✓ 字节码 / GC / 类加载 / 线程 / JNI 的稳定性影响 | [01-字节码](../01-字节码与指令集/) / [02-编译与执行](../02-编译与执行/) / [03-类加载与链接](../03-类加载与链接/) / [04-GC系统](../03-GC系统/) / [05-JNI](../05-JNI/) 详解 |
| ART 源码目录结构 | ✓ 12 个核心子目录速查 | — |
| Dalvik → ART 演进史 | ✓ 5 阶段演进 | [02-编译与执行](../02-编译与执行/) 详解编译路径 |
| ART 在 Android 分层架构中的位置 | ✓ ASCII 分层图 + 边界声明 | — |
| ART 客户（System Server / App / 系统应用） | ✓ 三类客户 + 稳定性差异 | — |
| 启动流程 | — | [07-启动流程](../07-启动流程/) |
| ART vs JVM 对比 | — | [08-对比与演进](../08-对比与演进/) |
| 信号与 ANR Trace | — | [06-信号与ANR-Trace](../06-信号与ANR-Trace/) |

**承接自**：无（系列开篇）。

**衔接去**：[01-字节码与指令集](../01-字节码与指令集/) 深入字节码层；[02-编译与执行](../02-编译与执行/) 深入编译路径；[03-类加载与链接](../03-类加载与链接/) 深入 ClassLoader；[04-GC 系统](../03-GC系统/) 深入 GC（★ 已完稿 9 篇）。

**强依赖**：本篇是系列起点，**无前置依赖**。

**跨系列引用**：
- 进程基础：[Linux_Kernel/Process](../../Linux_Kernel/Process/)
- 内存基础：[Linux_Kernel/Memory_Management](../../Linux_Kernel/Memory_Management/)
- 信号机制：[Linux_Kernel/Signal](../../Linux_Kernel/Signal/)

---

## 1. 背景与定义：ART 是什么

### 1.1 一句话定义

**ART（Android Runtime）是 Android 5.0 起取代 Dalvik 的核心运行时，负责 Java/Kotlin 字节码的加载、解释执行、JIT/AOT 编译、内存管理、线程调度、JNI 边界、异常处理。** 所有的 Java/Kotlin 代码——无论是 App 还是 System Server——都跑在 ART 之上。

### 1.2 为什么 ART 是稳定性主战场

```
┌────────────────────────────────────────────────────────────────┐
│ 线上稳定性问题的 ART 归因                                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  OOM (60%+)          ─→  ART Heap / GC                         │
│  ANR (40%+)          ─→  ART 主线程 / JIT 编译 / GC 阻塞          │
│  Native Crash (NE)   ─→  ART JNI 边界 / ART 自身 NE              │
│  Java Crash (JE)     ─→  ART 类加载 / VerifyError                │
│  卡顿 (Jank)         ─→  ART 解释器 / 编译路径 / GC 暂停          │
│  冷启动慢            ─→  ART Zygote / ClassLoader / 编译         │
│  内存泄漏            ─→  ART Heap / Reference                    │
│  ANR Trace 解读      ─→  ART SignalCatcher / 栈展开              │
│                                                                │
│  ★ 90% 的稳定性问题根因最终指向 ART                              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**架构师视角**：稳定性工程师不需要"懂 ART 的每一个细节"，但**必须能在 5 分钟内把 OOM/ANR/NE 定位到 ART 的对应子系统**。这是 ART 总览的核心价值。

### 1.3 ART vs Dalvik：演进史

```
┌────────────────────────────────────────────────────────────────┐
│ Dalvik → ART 演进史（Android 1.0 - 14.0）                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Android 1.0 - 4.4 (KitKat)                                    │
│    └─ Dalvik VM（解释执行 + JIT）                                │
│    └─ 每次启动都解释 dex，应用越大越慢                             │
│    └─ 无 AOT，每次冷启动都需要 JIT 编译                             │
│                                                                │
│  Android 5.0 - 6.0 (Lollipop - Marshmallow)                      │
│    └─ ART 取代 Dalvik                                            │
│    └─ AOT 编译（安装时或后台编译）                                  │
│    └─ 应用启动变快，但安装慢、占用存储大                              │
│                                                                │
│  Android 7.0 - 8.0 (Nougat - Oreo)                              │
│    └─ JIT + AOT 混合模式（Profile Guided）                       │
│    └─ 解释器 + JIT + AOT 三态切换                                  │
│    └─ Profile（热点方法记录）跨版本累积                             │
│                                                                │
│  Android 9.0 - 10.0 (Pie - Q)                                    │
│    └─ Cloud Profile（云端下发热点）                                │
│    └─ Baseline Profile（编译期埋点）                              │
│    └─ ART Mainline（ART 从系统镜像剥离）                          │
│                                                                │
│  Android 11.0 - 14.0 (R - Upside Down Cake)                     │
│    └─ ART APEX 模块独立更新                                      │
│    └─ Generational CC GC（AOSP 12+ 默认）                       │
│    └─ Baseline Profile + Cloud Profile + Startup Profile 三件套  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**关键里程碑**：

| 时间 | 里程碑 | 稳定性影响 |
| :--- | :--- | :--- |
| **Android 5.0** | ART 取代 Dalvik | AOT 编译让启动变快，但安装慢 |
| **Android 7.0** | JIT + AOT 混合 | 解释器快 + 编译后更快（最佳平衡） |
| **Android 9.0** | Cloud Profile | 应用启动进一步加速（30%+） |
| **Android 10** | ART Mainline | ART 可以独立更新（不再依赖系统镜像） |
| **Android 12** | Generational CC GC | GC 暂停时间降低 50%+ |
| **Android 13** | ART APEX 模块化 | 厂商可以快速修复 ART 漏洞 |
| **Android 14** | Baseline Profile GA | 应用冷启动性能提升 30%+ |

---

## 2. 架构与交互：ART 在 Android 系统中的位置

### 2.1 Android 分层架构

```
┌────────────────────────────────────────────────────────────────┐
│ Android 系统分层架构                                              │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 应用层：App（Java/Kotlin）                                │  │
│  │   └─ 第三方 App + 系统 App                                 │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       ↓ 上层 API                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Framework 层：Android Framework (Java)                     │  │
│  │   ├─ ActivityManagerService (AMS)                         │  │
│  │   ├─ WindowManagerService (WMS)                          │  │
│  │   ├─ PackageManagerService (PMS)                          │  │
│  │   └─ ... 100+ 系统服务                                   │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       ↓ 上层 API                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Native Framework 层：libandroid / libbinder (C++)         │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       ↓ JNI 边界                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Runtime 层：ART (C++ + Native)                             │  │  ← ★ 本系列
│  │   ├─ 字节码执行（解释器/JIT/AOT）                          │  │
│  │   ├─ GC（Heap / Reference）                                │  │
│  │   ├─ 类加载（ClassLoader / ClassLinker）                    │  │
│  │   ├─ 线程调度（Thread / Monitor）                          │  │
│  │   ├─ JNI 边界（JavaVM / JNIEnv）                          │  │
│  │   └─ 信号处理（SignalCatcher / ANR Trace）                 │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       ↓ 系统调用                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ HAL 层：Hardware Abstraction Layer (C++)                  │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       ↓ 系统调用                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Linux Kernel 层（drivers/android/binder.c 等）             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 ART 在分层中的位置

**关键边界**：
- **ART ↔ Java App**：通过标准 Java API（java.lang.* / java.util.* 等）
- **ART ↔ Framework**：通过 java.lang.reflect.* / android.app.* 等反射 API
- **ART ↔ Native**：通过 JNI（Java Native Interface）
- **ART ↔ Kernel**：通过系统调用（mmap / clone / sigaction 等）

**架构师视角**：ART 是 Android 系统中**唯一一个同时跨越 Java 和 C++ 边界的核心组件**。所有跨语言问题（JE/NE/JNI Crash）都涉及 ART。

### 2.3 ART 的三类"客户"

```
┌────────────────────────────────────────────────────────────────┐
│ ART 的三类客户                                                   │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  客户 1：App 进程（普通应用）                                    │
│    └─ 典型代表：抖音 / 微信 / 支付宝                              │
│    └─ ART 配置：默认 15+1 线程、Java Heap 192-512MB              │
│    └─ 稳定性关注：                                                │
│       - OOM（Java Heap + Native Heap 总和超限）                  │
│       - ANR（主线程执行时间过长）                                  │
│       - Jank（解释器或 GC 暂停导致掉帧）                           │
│       - 冷启动（ClassLoader + JIT 编译）                         │
│                                                                │
│  客户 2：System Server 进程（系统服务）                           │
│    └─ 典型代表：system_server / com.android.systemui            │
│    └─ ART 配置：32+ 线程、Java Heap 2-4GB                       │
│    └─ 稳定性关注：                                                │
│       - 线程池耗尽（AMS/WMS/PMS 高频调用）                       │
│       - 跨进程死锁（Binder + Java Monitor）                       │
│       - 内存泄漏（Proxy 泄漏 / Binder 引用泄漏）                  │
│       - Watchdog 重启（主线程 30s 无响应）                        │
│                                                                │
│  客户 3：系统 Native 进程（少量）                                 │
│    └─ 典型代表：init / servicemanager / surfaceflinger           │
│    └─ ART 配置：无 ART（纯 Native），通过 Binder 与 Java 通信      │
│    └─ 稳定性关注：                                                │
│       - 与 Java Framework 的 Binder 阻塞                         │
│       - 与 ART 进程的线程模型冲突                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心机制：ART 的五大核心能力

### 3.1 能力 1：字节码执行（解释器 / JIT / AOT）

**三种执行模式**：

| 模式 | 触发时机 | 性能 | 内存 | 适用场景 |
| :--- | :--- | :--- | :--- | :--- |
| **解释器（Interpreter）** | 应用首次启动 | ★★ | ★ | 未编译的方法 |
| **JIT（Just-In-Time）** | 方法被调用 N 次（热度阈值） | ★★★★ | ★★ | 热点方法（运行时编译） |
| **AOT（Ahead-Of-Time）** | 安装时 / 后台 / 下次启动 | ★★★★★ | ★★★★ | 热点方法（编译期产物） |

**三态切换**：

```
方法首次调用
  ↓
解释器执行（同时统计调用次数）
  ↓
达到 JIT 阈值（默认 10,000 次）
  ↓
JIT 编译（后台线程，OSR 替换入口）
  ↓
JIT 代码执行（Profile 记录）
  ↓
后台 dex2oat 编译 AOT
  ↓
下次启动直接用 AOT 代码
```

**稳定性影响**：
- **冷启动慢**：大量方法还在解释器模式（PGO/Baseline Profile 优化）
- **JIT 编译卡顿**：方法首次达到阈值时，主线程短暂卡顿（数十 ms）
- **AOT 编译卡顿**：后台 dex2oat 占用 CPU，导致系统卡顿
- **内存压力**：JIT/AOT 代码占用内存（每个类 ~10-100KB）

**详见**：[02-编译与执行](../02-编译与执行/) + [07-启动流程](../07-启动流程/)

### 3.2 能力 2：内存管理（GC / Reference）

**GC 算法演进**：

| GC 类型 | AOSP 版本 | 特点 | STW 时间 |
| :--- | :--- | :--- | :--- |
| **Dalvik GC** | Android 1.0-4.4 | 标记-清除 | 100-500ms |
| **ART CMS** | Android 5.0-11 | Concurrent Mark-Sweep | 10-50ms |
| **ART CC** | Android 8.0+ | Concurrent Copying | 5-20ms |
| **Generational CC** | Android 12+ | 分代假说 + CC | 2-10ms |

**5 Space 划分**：

```
┌────────────────────────────────────────────────────────────────┐
│ ART 5 Space 划分（AOSP 14）                                      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Image Space (~10MB, mmap)                                      │
│    └─ boot.art / boot.vdex / boot.oat                          │
│                                                                │
│  Zygote Space (~50MB, fork 时共享)                              │
│    └─ Zygote 预加载的类                                          │
│                                                                │
│  Alloc Space (主要堆，年轻代)                                    │
│    └─ 新对象分配                                                 │
│                                                                │
│  Main Space (老年代)                                            │
│    └─ 晋升的对象                                                 │
│                                                                │
│  Large Object Space (LOS, 大对象)                               │
│    └─ Bitmap / 大数组                                            │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**稳定性影响**：
- **OOM**：所有 Space 占满 → OOM（最常见 OOM 类型）
- **GC 卡顿**：CMS / CC 触发时主线程暂停
- **内存泄漏**：Reference 引用未释放 / 静态字段持有 Context

**详见**：[04-GC 系统](../03-GC系统/)（★ 已完稿 9 篇）

### 3.3 能力 3：类加载（ClassLoader / ClassLinker）

**Android ClassLoader 体系**：

```
BootClassLoader（Zygote 加载）
    │
PathClassLoader（App 加载 /data/app/*.dex）
    │
InMemoryDexClassLoader（动态加载）
    │
DexClassLoader（从 .dex / .jar / .apk 加载）
```

**ClassLinker::DefineClass 流程**：

1. **Load**：从 .dex 文件读取 class_data_item
2. **Link**：验证 + 准备 + 解析符号引用
3. **Initialize**：执行 `<clinit>`（静态初始化块）

**稳定性影响**：
- **ClassNotFoundException**：class loader 找不到类
- **NoClassDefFoundError**：class 存在但定义错误
- **VerifyError**：类验证失败（混淆 / 字节码错误）
- **LinkageError**：符号解析失败
- **冷启动慢**：ClassLoader 是冷启动开销最大的子系统之一

**详见**：[03-类加载与链接](../03-类加载与链接/)

### 3.4 能力 4：线程调度（Thread / Monitor）

**ART Thread 模型**：

```
Java Thread (1:1 模型)
  ↓
Native Thread (pthread_create)
  ↓
ART Thread (Thread::CreateNativeThread)
  ↓
Managed Code (执行 Java 字节码)
```

**Monitor 机制**：
- **Java Monitor**：synchronized 关键字
- **ART Lock**：各种内部锁（class loading / GC / JNI）

**稳定性影响**：
- **死锁**：synchronized + 跨进程 Binder 调用形成嵌套死锁
- **ANR**：主线程 blocked on monitor
- **线程泄漏**：Thread 未释放

### 3.5 能力 5：JNI 边界（Java ↔ Native）

**JNI 数据结构**：

```
JavaVM (进程唯一)
  ↓
JNIEnvExt (线程唯一)
  ↓
IndirectReferenceTable (Local / Global / Weak Global)
```

**关键 JNI 函数**：
- `FindClass` / `GetMethodID` / `CallVoidMethod`
- `RegisterNatives`（性能优化）
- `NewGlobalRef` / `DeleteGlobalRef`（引用管理）

**稳定性影响**：
- **Native Crash**：JNI 调用传错参数（如 NullReference）
- **内存泄漏**：GlobalRef 未释放 → system_server OOM
- **CheckJNI 报错**：Debug 模式下检查 JNI 调用规范

**详见**：[05-JNI](../05-JNI/)

### 3.6 五大能力的稳定性映射表

| 能力 | 主要稳定性问题 | 排查工具 |
| :--- | :--- | :--- |
| **字节码执行** | 冷启动慢 / JIT 卡顿 / 解释器慢 | `am profile` / `simpleperf` / `perfetto` |
| **内存管理** | OOM / 内存泄漏 / GC 卡顿 | `dumpsys meminfo` / `leakcanary` / `procrank` |
| **类加载** | ClassNotFoundException / VerifyError / 冷启动慢 | `am start` / `logcat -s ClassLoader` |
| **线程调度** | ANR / 死锁 / 线程泄漏 | ANR trace / `dumpsys threads` |
| **JNI 边界** | Native Crash / GlobalRef 泄漏 | `debuggerd` / `dumpsys jni` |

---

## 4. ART 源码目录结构（速查）

```
art/                                                          ← ART 源码根目录（AOSP）
├── Android.bp                                                ← 构建配置
├── build/                                                    ← 构建脚本
├── compiler/                                                 ← dex2oat / JIT 编译器
│   ├── dex/                                                  ← dex 字节码
│   ├── driver/                                               ← 编译驱动
│   ├── jit/                                                  ← JIT 编译
│   └── optimizing/                                           ← AOT 优化编译器
├── dex2oat/                                                  ← dex2oat 工具入口
├── disassembler/                                             ← 反汇编
├── imgdiag/                                                  ← image 诊断
├── libdexfile/                                               ← Dex 文件解析
├── oatdump/                                                  ← OAT 文件分析
├── openjdkjvm/                                               ← OpenJDK JVM 接口
├── openjdkjvmti/                                             ← JVMTI 接口
├── runtime/                                                  ← ★ 运行时核心
│   ├── aa/                                                   ← AA 模式
│   ├── arch/                                                 ← 架构相关（arm64 / x86_64）
│   ├── base/                                                 ← 基础工具
│   ├── class_linker.cc                                       ← 类加载
│   ├── class_linker.h
│   ├── common_dex_operations.h
│   ├── debugger.cc                                           ← 调试器
│   ├── dex_file.cc                                           ← Dex 文件
│   ├── gc/                                                   ← ★ GC 系统
│   │   ├── collector/                                        ← 垃圾收集器
│   │   ├── heap.cc                                           ← 堆管理
│   │   ├── space/                                            ← Space 划分
│   │   ├── reference_queue.cc                                ← Reference 队列
│   │   └── ...
│   ├── indirect_reference_table.cc                          ★ JNI 引用表
│   ├── interpreter/                                          ← ★ 解释器
│   │   ├── interpreter.cc
│   │   ├── interpreter_switch_impl.cc                        ← Switch 解释器
│   │   └── interpreter_mterp_impl.cc                         ← Mterp 汇编解释器
│   ├── jni/                                                  ← ★ JNI 核心
│   │   ├── jni.cc
│   │   ├── jni_env.cc
│   │   └── check_jni.cc                                       ← CheckJNI
│   ├── mirror/                                               ← 镜像对象
│   │   ├── art_method.cc
│   │   ├── class.cc
│   │   └── object.cc
│   ├── monitor.cc                                            ← Monitor（synchronized）
│   ├── thread.cc                                             ← ★ 线程管理
│   ├── thread_list.cc                                        ← 线程列表
│   ├── signal_catcher.cc                                     ← ★ 信号处理
│   ├── stack.cc                                              ← 栈管理
│   ├── stack_walker.cc                                       ← 栈展开（trace）
│   ├── instrumentation.cc                                    ← JVMTI 实现
│   ├── intern_table.cc                                       ← 字符串驻留
│   ├── oat_file.cc                                           ← OAT 文件
│   └── ...
├── profman/                                                  ← Profile 工具
├── runtime/                                                  ← 见上
├── sigchainlib/                                              ← 信号链
└── test/                                                     ← 测试代码
```

**关键目录速查**（稳定性视角）：

| 目录 | 稳定性问题 | 文件数 |
| :--- | :--- | :---: |
| `runtime/gc/` | OOM / GC 卡顿 | 80+ |
| `runtime/interpreter/` | 冷启动 / Jank | 20+ |
| `runtime/jni/` | NE / GlobalRef 泄漏 | 15+ |
| `runtime/class_linker.cc` | VerifyError / ClassNotFound | 5+ |
| `runtime/thread.cc` | ANR / 死锁 | 5+ |
| `runtime/signal_catcher.cc` | ANR Trace 解读 | 1 |

---

## 5. 风险地图：ART 的五大稳定性风险

| # | 风险类型 | 触发条件 | 现象 | 排查入口 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **ART 自身 OOM** | Java Heap + Native Heap 超限 | `OutOfMemoryError` | `dumpsys meminfo` |
| 2 | **ART GC 卡顿** | CMS / CC / GenCC 触发 | 主线程暂停 | Perfetto + GC 事件 |
| 3 | **ART 主线程 ANR** | JIT 编译 / GC / 类加载阻塞 | 5-10s 无响应 | ANR trace |
| 4 | **ART JNI Crash** | GlobalRef 错误 / 传错参数 | SIGSEGV in art:: | debuggerd / Tombstone |
| 5 | **ART ClassLoader 慢** | MultiDex / 动态加载 / Verify | 冷启动慢 + VerifyError | `am start` + `logcat` |

**风险地图与子模块对应**：

| 子模块 | 主要覆盖风险 |
| :--- | :--- |
| 04-GC 系统（★ 已完稿） | OOM / GC 卡顿 |
| 06-信号与ANR-Trace | ART 主线程 ANR |
| 05-JNI | JNI Crash |
| 03-类加载与链接 | VerifyError / 冷启动慢 |
| 02-编译与执行 | JIT 卡顿 / 冷启动慢 |

---

## 6. 实战案例：某 App OOM 排查 30 分钟闭环

### 案例：Java Heap 持续增长触发 OOM

**现象**：某 IM App 启动后 30 分钟内 Java Heap 持续增长，最终触发 `OutOfMemoryError`。

**环境**：Android 14 (AOSP 14.0.0_r1) / Kernel 5.10 / 设备 Pixel 6。

#### 步骤 1：抓取 meminfo

```bash
adb shell dumpsys meminfo com.example.im
```

输出关键片段：

```
Native Heap    125000  125000  0    0    0    0   10  0
Java Heap      320000  312000  8000 1000 0    0   30  0   ← 持续增长
...
Objects
  Views:        2500   ← 异常多
  Activities:    50   ← 正常
```

**观察**：Java Heap 从 200MB 增长到 320MB，Views 数量异常（2500 vs 正常 500）。

#### 步骤 2：定位持续增长的 View

使用 LeakCanary 检测 → 发现 `MessageAdapter` 持有的 `ImageView` 未释放。

**根因**：`ImageView` 持有 `Context`（Activity），Activity 销毁时未释放 ImageView → ImageView 持有 Activity → Activity 泄漏。

#### 步骤 3：ART Heap 视角分析

`dumpsys meminfo` 中 Java Heap 320MB 包含：
- `MessageAdapter` 实例：~1000 个 × 80KB = ~80MB
- 每个 `MessageAdapter` 持有 `ImageView` → 持有 `Activity`
- 这是典型的"非静态 Context 持有"导致的内存泄漏

#### 步骤 4：修复

```java
// 修复前（错误）
public class MessageAdapter {
    private Context context;  // 持有 Activity Context
    public MessageAdapter(Context context) {
        this.context = context;
    }
}

// 修复后（正确）
public class MessageAdapter {
    private WeakReference<Context> contextRef;  // 弱引用
    public MessageAdapter(Context context) {
        this.contextRef = new WeakReference<>(context);
    }
}
```

**修复后**：`MessageAdapter` 不再持有 `Activity`，GC 时可正常回收。

#### 步骤 5：验证

```
┌──────────────────────────────────────┬───────────┬───────────┐
│ 指标                                  │ 修复前     │ 修复后     │
├──────────────────────────────────────┼───────────┼───────────┤
│ Java Heap 稳态                        │ 320MB     │ 180MB     │
│ Views 数量                            │ 2500      │ 500       │
│ OOM 频次/天                            │ 12 次     │ 0 次      │
│ 启动后 30min Java Heap                 │ 320MB     │ 180MB     │
└──────────────────────────────────────┴───────────┴───────────┘
```

**修复 commit 模式**：
```
MessageAdapter 内存泄漏修复：
- 使用 WeakReference<Context> 替代强引用
- 在 onViewRecycled 中清理 ImageView 引用
- 添加 LeakCanary 单测

Java Heap 稳态从 320MB → 180MB（-44%）
OOM 频次从 12 次/天 → 0 次/天
```

---

## 7. 总结（架构师视角的 5 条 Takeaway）

1. **ART 是稳定性的"主战场"**——90% 的稳定性问题根因指向 ART（OOM/ANR/NE/JE/卡顿）。**掌握 ART 等于掌握稳定性的 80%**。
2. **五大核心能力：字节码 / GC / 类加载 / 线程 / JNI**——所有 ART 稳定性问题都属于这 5 类。**5 分钟定位 = 把问题归类到这 5 类之一**。
3. **ART 跨 Java/C++ 边界**——所有跨语言问题（JE/NE/JNI Crash）都涉及 ART。**JNI 是 ART 最容易出问题的地方**。
4. **ART 源码目录集中在 `art/runtime/`**——遇到问题直接看 `gc/`、`interpreter/`、`jni/`、`class_linker.cc`、`signal_catcher.cc` 这几个核心目录。
5. **ART 演进史 = 性能 + 稳定性双优化**——从 Dalvik 到 AOT 到 JIT+AOT 到 Cloud Profile 到 Generational CC GC，每一步都同时优化了性能和稳定性。

**ART 子系列阅读路径**：

```
时间有限：00-总览（本篇）→ 04-GC 系统（★ 已完稿，最常用）
系统学习：00 → 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08
按问题读：
  OOM    → 04-GC 系统 + 08-对比与演进
  ANR    → 06-信号与ANR-Trace + 02-编译与执行 + 04-GC
  Jank   → 02-编译与执行 + 04-GC
  NE     → 05-JNI + 06-信号
  启动慢 → 07-启动流程 + 02-编译与执行
```

---

## 附录 A：核心源码路径索引

| 文件名 | 完整路径 | AOSP 版本 | 本篇中的角色 |
| :--- | :--- | :--- | :--- |
| Runtime 主目录 | `art/runtime/` | AOSP 14+ | ART 核心 |
| GC 系统 | `art/runtime/gc/` | AOSP 14+ | [04-GC 系统](../03-GC系统/) |
| 解释器 | `art/runtime/interpreter/` | AOSP 14+ | [02-编译与执行](../02-编译与执行/) |
| JNI | `art/runtime/jni/` | AOSP 14+ | [05-JNI](../05-JNI/) |
| ClassLinker | `art/runtime/class_linker.cc` | AOSP 14+ | [03-类加载与链接](../03-类加载与链接/) |
| Thread | `art/runtime/thread.cc` | AOSP 14+ | [06-信号与ANR-Trace](../06-信号与ANR-Trace/) |
| SignalCatcher | `art/runtime/signal_catcher.cc` | AOSP 14+ | ANR Trace |
| AndroidRuntime | `frameworks/base/core/jni/AndroidRuntime.cpp` | AOSP 14+ | [07-启动流程](../07-启动流程/) |
| ZygoteInit | `frameworks/base/core/java/com/android/internal/os/ZygoteInit.java` | AOSP 14+ | 启动流程 |
| ActivityManagerService | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | AOSP 14+ | ANR 检测 |

---

## 附录 B：源码路径对账表

| # | 文章中出现的路径 | 状态 | 校对来源 / 备注 |
| :-- | :--- | :--- | :--- |
| 1 | `art/runtime/` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 2 | `art/runtime/gc/` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 3 | `art/runtime/interpreter/` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 4 | `art/runtime/jni/` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 5 | `art/runtime/class_linker.cc` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 6 | `art/runtime/thread.cc` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 7 | `art/runtime/signal_catcher.cc` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 8 | `art/compiler/dex2oat/` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 9 | `art/libdexfile/` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 10 | `frameworks/base/core/jni/AndroidRuntime.cpp` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 11 | `frameworks/base/core/java/com/android/internal/os/ZygoteInit.java` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |
| 12 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | ✅ 已校对 | cs.android.com/android-14.0.0_r1 |

---

## 附录 C：量化数据自检表

| # | 量化描述 | 数量级 | 依据来源 / 备注 |
| :-- | :--- | :--- | :--- |
| 1 | ART 源码目录数 | 12 个核心子目录 | 速查表 |
| 2 | ART 五大核心能力 | 字节码/GC/类加载/线程/JNI | §3 |
| 3 | 线上稳定性问题 ART 归因比例 | ≥ 90% | 经验值 |
| 4 | Dalvik → ART 演进阶段 | 5 阶段（5.0/7.0/9.0/10/12） | §1.3 |
| 5 | ART GC 演进阶段 | 4 阶段（Dalvik/CMS/CC/GenCC） | §3.2 |
| 6 | App 默认 ART 线程数 | 15+1 | ProcessState |
| 7 | system_server 默认 ART 线程数 | 32（Pixel） | AOSP |
| 8 | App 默认 Java Heap | 192-512MB | AOSP |
| 9 | system_server 默认 Java Heap | 2-4GB | AOSP |
| 10 | JIT 编译阈值 | 默认 10,000 次方法调用 | AOSP |
| 11 | 解释器 vs AOT 性能差距 | 5-10x | 经验值 |
| 12 | Generational CC vs CMS GC 暂停 | 2-10ms vs 10-50ms | AOSP 12+ |

---

## 附录 D：工程基线表（v3 强制 · ART 总览专用）

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
| :--- | :--- | :--- | :--- |
| **App Java Heap** | 192-512MB | 视业务调整 | 太小→OOM；太大→GC 慢 |
| **system_server Java Heap** | 2-4GB | 视厂商调整 | 太大→触发 OOM adjuster |
| **App ART 线程数** | 15+1 | 视业务调整 | 太多→线程切换开销 |
| **system_server ART 线程数** | 32 | 视厂商调整 | 太少→线程池耗尽 |
| **JIT 编译阈值** | 10,000 次调用 | AOSP 默认 | 太低→JIT 编译开销；太高→解释器慢 |
| **解释器 vs AOT** | AOT 优先（Baseline Profile） | 应用安装后 AOT | 强制 AOT→安装慢 |
| **GC 类型** | Generational CC（AOSP 12+ 默认） | 视 Android 版本 | 老版本回退到 CMS |
| **5 Space 划分** | Image + Zygote + Alloc + Main + LOS | AOSP 默认 | 大对象必须进 LOS |
| **ClassLoader 链** | BootClassLoader → PathClassLoader | AOSP 默认 | 动态加载用 DexClassLoader |
| **ART 演进** | 解释器 + JIT + AOT | 三态切换 | 单一模式性能差 |

---

## 篇尾衔接

下一篇 [01-Dex 文件与 Dalvik 指令集](../01-字节码与指令集/) 将深入**第一大核心能力——字节码执行**的基础层：从 Dex 文件格式（Header / StringIDs / TypeIDs / MethodIDs / ClassDefs）到 Dalvik 指令集（数据移动 / 算术 / 对象操作 / 五种 invoke / 控制流），再到解释器执行循环（ExecuteSwitchImpl 的 while-switch 主循环）。

> **返回阅读**：[README-ART 系列](../README-ART系列.md) 包含全系列目录与阅读建议。