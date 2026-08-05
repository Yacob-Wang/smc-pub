# ART 大模块总览（Android Runtime）

> **本目录是 `Runtime` 的核心子模块** —— 所有 Android Runtime（ART）相关的深度文章都在这里。
>
> 设计原则：**每个子目录都是独立专题**（含多篇文章），按 ART 子系统拆分，子目录之间通过"跨篇引用"互相串起来。

---

## 一句话定位

**ART = Android 上的 Java/Kotlin 字节码运行时**。从 APK 里的 `classes.dex` 到屏幕上跑的每一个 Java 对象，背后都是 ART 在管：
- 字节码怎么解析（DEX / OAT / VDEX）
- 怎么执行（解释器 / JIT / AOT）
- 类怎么加载（ClassLinker / OatFile）
- 对象怎么分配和回收（GC 系统）← **本轮重写重点**
- 怎么和 Native 互通（JNI）
- 出问题怎么兜底（信号、ANR、Trace）
- 启动流程是怎样的（Zygote / SystemServer）
- 怎么和 JVM 对比、怎么演进
- 怎么被 Hook 框架"反向工程"

---

## 子模块清单（v2 规划）

| 子目录 | 专题 | 状态 | 来源 |
|:---|:---|:---|:---|
| `00-总览与字节码` | ART 整体架构 + DEX 文件格式 + 指令集 | 待写 | 重构自 `v1_00-总览` + `v1_01-字节码与指令集` |
| `01-编译与执行` | 解释器 / JIT / AOT / Profile 引导编译 | 待写 | 重构自 `v1_02-编译与执行` |
| `02-类加载与链接` | ClassLinker / OAT / 类查找 / 验证 | 待写 | 重构自 `v1_03-类加载与链接` |
| **`03-GC系统`** | **GC 9 篇独立系列（本轮主写）** | **进行中** | **完全重写，取代 `v1_04-内存与GC`** |
| `04-JNI` | JNI 桥接 / Critical 区 / Global Ref | 待写 | 重构自 `v1_05-JNI` |
| `05-信号与ANR-Trace` | 信号处理 / ANR 检测 / Trace 机制 | 待写 | 重构自 `v1_06-信号与ANR-Trace` |
| `06-启动流程` | Zygote / SystemServer / 冷启动 | 待写 | 重构自 `v1_07-启动流程` |
| `07-对比与演进` | ART vs JVM / 版本演进史 | 待写 | 重构自 `v1_08-对比与演进` |
| `08-Hook与ART` | 横切专题：SandHook / Epic / 各种 Hook 框架的 ART 适配 | 待写 | 新增（之前散在 ART 多个篇章中） |

`_archive/` 目录保留 **v1 旧版本的所有内容**（00-08 旧编号 + 01-10 的早期版本），做历史快照不删，供对比参考。

---

## 子模块详细规划

### 00 - 总览与字节码（ART 入门）
> **目标**：把"ART 是什么 + 字节码长什么样"一次性讲清

- ART 整体架构图（Runtime / Heap / Thread / ClassLinker / GC / Compiler）
- DEX 文件结构（Header / String IDs / Type IDs / Proto IDs / Field IDs / Method IDs / Class Defs）
- 字节码指令集（invoke-* / new / move / return 的语义）
- DEX / OAT / VDEX 三种文件的区别
- dex2oat 工具链：DEX → OAT 的完整流程

**核心源码**：`art/runtime/dex_file.h`、`art/runtime/dex_file.cc`、`art/libdexfile/`

### 01 - 编译与执行
> **目标**：把"代码怎么变成机器码"讲透

- 解释器（Interpreter）：C++ 解释循环 vs mterp
- Baseline JIT：何时触发、阈值
- AOT 编译：dex2oat 的多阶段流程
- Profile 引导编译（云端配置 / 启动画像）
- OSR（On-Stack Replacement）
- ART 9+ 的 JIT/AOT 混合策略

**核心源码**：`art/compiler/`、`art/runtime/interpreter/`、`art/runtime/jit/`

### 02 - 类加载与链接
> **目标**：把"类怎么找到、怎么校验、怎么初始化"讲清

- ClassLinker 的整体架构
- 类查找路径（PathClassLoader / DexClassLoader / InMemoryDexClassLoader）
- OAT 文件结构（OatHeader / OatMethod / OatClass）
- 类验证（VerifyClass）
- 类初始化（`<clinit>` 与 `<init>` 的区别）
- 父类加载委派
- **多 DEX 加载**：65536 方法数限制的根源
- **DEX 加载失败案例分析**（来自 `_archive/DEX_Loading_Failure_Analysis_Guide.md`）

**核心源码**：`art/runtime/class_linker.h`、`art/runtime/oat_file.h`

### 03 - GC 系统（**本轮重写**）
> **目标**：9 篇独立成体系，从理论到实战完整覆盖 ART 的 GC

- 详见 `03-GC系统/README.md`

### 04 - JNI
> **目标**：把 Java ↔ Native 的桥讲透

- JNI 整体架构（Invocation API / Native Method 接口）
- JNI 引用类型（Local / Global / Weak Global）
- Critical 区（GetPrimitiveArrayCritical 的 GC 阻塞）
- JNI 调用性能（cost）
- JNI 常见崩溃（LocalRef 超限 / Invalid Signature / UnsatisfiedLinkError）
- ART 与 JNI 的特殊点（`@FastNative` / `@CriticalNative`）

**核心源码**：`art/runtime/jni/`、`art/runtime/entrypoints/`

### 05 - 信号与 ANR-Trace
> **目标**：把 ART 层的"异常兜底"讲清

- ART 的信号处理架构（SIGSEGV / SIGBUS / SIGFPE / SIGILL）
- Stack Overflow 的检测（`stack overflow` 机制）
- ANR 检测（SIGQUIT + traces.txt）
- Trace 机制（method trace / sampling trace）
- 崩溃日志的解析（tombstone / dropbox）

**核心源码**：`art/runtime/signal_handler.h`、`art/runtime/thread.cc` 的 `DeliverSignal`

### 06 - 启动流程
> **目标**：把"按下电源键到第一个 Activity"的全流程讲透

- Bootloader → Kernel → Init → Zygote → SystemServer → Launcher
- Zygote fork 的 fork 模型
- ART 启动流程（Runtime::Start 详解）
- 冷启动 / 暖启动 / 热启动的性能差异
- 启动优化的工具（Macrobenchmark / StartupTracer）

**核心源码**：`art/runtime/runtime.cc` 的 `Runtime::Start`、`frameworks/base/core/java/android/app/ActivityThread.java`

### 07 - 对比与演进
> **目标**：把"ART 是怎么来的、要到哪里去"讲清

- Dalvik vs ART 的核心差异
- ART 5.0 → 14 的版本演进（每版本的关键特性）
- ART 与 JVM 的对比（字节码 / GC / 内存模型）
- Android 8+ 的 Mainline（com.android.art 模块）
- Android 14+ 的 ART GC 演进（GenCC 优化）

**核心源码**：每个 ART 版本的 Release Notes

### 08 - Hook 与 ART
> **目标**：把"ART 被各种 Hook 框架怎么反向工程"讲透

- Hook 框架总览（Xposed / Frida / SandHook / Epic / Whalebook / YAHFA）
- ART Method 结构（ArtMethod 内存布局）
- Hook 的实现原理（替换 entrypoint / inline hook）
- CC GC 下的 Hook 兼容性问题
- Inline Hook 的 ART 适配
- 反 Hook / 反调试技术

**核心源码**：`art/runtime/art_method.h`、`art/runtime/entrypoints/entrypoint_utils.h`

---

## 跨子模块引用关系

```
┌────────────────────────────────────────────────────────┐
│                       ART 大模块                        │
├────────────────────────────────────────────────────────┤
│                                                        │
│   00-总览  ──┬─→  01-编译执行  ──┬─→  02-类加载        │
│             │                    │                     │
│             ↓                    ↓                     │
│         04-JNI  ←────  03-GC系统  ←────  06-启动       │
│             │            │                               │
│             ↓            ↓                               │
│        05-信号  ────  08-Hook                              │
│                                                        │
│         07-对比与演进（贯穿全篇的演进时间线）              │
└────────────────────────────────────────────────────────┘
```

---

## 与其他大模块的协作

| 协作模块 | 协作点 | 引用方向 |
|:---|:---|:---|
| `Android_Framework/` | ART 上层的 Framework（AMS / WMS / PMS）依赖 ART 的类加载、JNI、GC | Framework → ART |
| `AI_Layer/` | AI 推理（NNAPI / TFLite）作为 Native 库通过 JNI 调用 | AI → ART（JNI） |
| `App/` | App 的崩溃 / ANR / OOM 经常追溯到 ART 层 | App → ART |
| `Linux_Kernel/Memory_Management/` | ART GC 与内核内存回收（kswapd / LMK）的互动 | ART → Kernel |
| `Linux_Kernel/IO/` | ART 启动 / 类加载的 IO 性能 | ART → Kernel |
| `Native_Crash/` | Native 崩溃的栈回溯经常穿到 ART 层 | Native → ART |

---

## 本轮计划（本目录将完成的内容）

**当前任务**：完成 `03-GC系统/` 全部 9 篇（参见 `03-GC系统/README.md`）

**后续任务**（按用户节奏）：
1. `00-总览与字节码/` —— 重写自 `_archive/v1_00-总览` + `_archive/v1_01-字节码与指令集`
2. `01-编译与执行/` —— 重写自 `_archive/v1_02-编译与执行`
3. `02-类加载与链接/` —— 重写自 `_archive/v1_03-类加载与链接`（含 `_archive/DEX_Loading_Failure_Analysis_Guide.md` 的整合）
4. `04-JNI/` —— 重写自 `_archive/v1_05-JNI`
5. `05-信号与ANR-Trace/` —— 重写自 `_archive/v1_06-信号与ANR-Trace`
6. `06-启动流程/` —— 重写自 `_archive/v1_07-启动流程`
7. `07-对比与演进/` —— 重写自 `_archive/v1_08-对比与演进`
8. `08-Hook与ART/` —— 新增（之前散在 ART 多个篇章中）

---

## 阅读建议

- **ART 新手**：00 → 01 → 02 → 03 → 06（自上而下走完主流程）
- **排查 OOM / 内存泄漏**：00（基础）→ 03（GC）→ `Android_Framework/Memory_Management/`（系统侧）
- **排查 ANR**：00 → 06（启动）→ 05（信号）→ `Android_Framework/ANR-Analysis/`
- **排查 Native Crash**：00 → 04（JNI）→ 08（Hook）→ `Native_Crash/`
- **逆向 / Hook**：00 → 02（类加载）→ 08（Hook）

---

## 归档说明

| 归档位置 | 内容 | 状态 |
|:---|:---|:---|
| `_archive/v1_00-总览` 到 `v1_08-对比与演进` | v1 旧版本的 9 个子目录 | 历史快照，保留 |
| `_archive/01-ART总览.md` 等单文件 | v0 早期版本的 10 篇编号文章 | 历史快照，保留 |
| `_archive/DEX_Loading_Failure_Analysis_Guide.md` | 早期 DEX 加载失败案例（计划整合进 `02-类加载与链接/`） | 待整合 |
| `Runtime/ART_backup/` | 早期备份 | 历史快照，保留 |
| `Runtime/ART_v1_backup/` | 重构前完整快照 | 历史快照，保留 |
