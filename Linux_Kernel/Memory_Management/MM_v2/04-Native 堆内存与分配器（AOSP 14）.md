# 04-Native 堆内存与分配器（AOSP 14）

> **系列**：面向稳定性的 Android 内存架构深度解析系列（MM_v2）
> **源码基线**：AOSP `android-14.0.0_r1`（`refs/heads/android14-release`）
> **内核矩阵**：`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`（scudo 是用户态分配器，不直接受内核版本影响；memcg 行为受 cgroup v2 内核版本演进影响，详见 §5）
> **目标读者**：Android 稳定性框架架构师
> **前置阅读**：[01-内存系统总览：从进程视角到硬件的完整链路](01-内存系统总览：从进程视角到硬件的完整链路.md)、[02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md)、[03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md)
> **下一篇**：[05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md)

---

## 本篇定位

- **本篇系列角色**：核心机制第 4 篇 — 讲 Native 堆（bionic scudo 分配器 + ION/DMA-BUF 图形缓冲 + memcg 限额）；与 ART 堆并列的"另一个 30% 内存故障源"
- **强依赖**：
  - MM_v2 02 已讲"VMA 体系"（本篇的 scudo mmap 段在 maps 里怎么表达）
  - MM_v2 03 已讲"ART 堆 / JNI 边界"（本篇的 Native 堆与 ART 堆的边界在 JNI 引用表）
- **承接自**：03 §4 JNI 引用表（local/global/weak 持有的 native peer）
- **衔接去**：
  - 05 讲 AMS 杀进程决策（Native Heap 是 adj 评分的重要依据）
  - 06 讲 LMKD（Native 泄漏是 LMKD 误杀的常见根因）
  - 06.1.4 surfaceflinger OOM 误杀（见本篇 §6.1.4）
- **不重复内容**：
  - 03 已讲的 ART 堆 / GC,本篇不重复
  - VMA 体系详见 02,本篇只引用不展开

#### §0 锚点案例的可验证 4 件套:surfaceflinger 被 LMKD 误杀（ION 泄漏触发 memcg OOM）

> **环境**:
> - 设备:Pixel 7（G2,arm64-v8a,8GB RAM）
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - 进程:surfaceflinger（system.slice cgroup）
> - 工具:`dumpsys meminfo` + `dumpsys SurfaceFlinger` + cgroup `memory.peak`/`memory.max`

> **复现步骤**:
> 1. 工厂重置,系统正常启动
> 2. 高负载使用 30min（视频播放 + 频繁切前后台 + 旋转屏幕）
> 3. logcat 反复出现 `Killed process 532 (surfaceflinger)`,间隔 ~30s
> 4. 屏幕黑屏 / 动画卡死,系统进入"无 surfaceflinger 状态"

> **logcat / dumpsys 关键片段**:
> ```
> # logcat -b main -b system
> 04-12 14:23:18.532  1045  1045 I ServiceManager: ...
> 04-12 14:23:18.901  1045  1045 I lowmemorykiller: Kill 'surfaceflinger' (532) ...
> 04-12 14:23:18.901  1045  1045 I libprocessgroup: Killed process 532 (surfaceflinger) ...
> # 重复出现,间隔 ~30s
> ```
> ```
> # dumpsys meminfo surfaceflinger
>    Java Heap:   12-30 MB   (业务轻)
>    Native Heap: 90-180 MB  (稳定,未涨)
>    Graphics:    50-300 MB  (单调上涨 ← 根因)
>    Total PSS:   250-500 MB
> ```
> ```
> # cgroup memory.peak 接近 memory.max
> $ cat /sys/fs/cgroup/system.slice/surfaceflinger/memory.peak
> 1048576000  # 1GB,接近 memory.max
> $ cat /sys/fs/cgroup/system.slice/surfaceflinger/memory.max
> 1073741824  # 1GB
> # dumpsys SurfaceFlinger --latency: 帧率稳定 60fps(排除渲染卡)
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/device/<vendor>/<device>/init.surfaceflinger.rc
> +++ b/device/<vendor>/<device>/init.surfaceflinger.rc
> @@ -cgroup 限额(临时)
> -    # 旧:512MB 限额,触发现网频发 OOM 误杀
> -    write /sys/fs/cgroup/system.slice/surfaceflinger/memory.max 536870912
> +    # 临时调整:1GB,缓冲 30s 抓现场时间
> +    write /sys/fs/cgroup/system.slice/surfaceflinger/memory.max 1073741824
> @@ -根因修复(vendor HAL 配合)
> -    // 旧 HAL:BufferQueue acquire 后未 release
> -    void onBufferAcquired(sp<GraphicBuffer>& buf) { mInUse.insert(buf); }
> +    // 修复:显式 release + refcount 跟踪
> +    void onBufferAcquired(sp<GraphicBuffer>& buf) { mInUse[buf->id] = buf; }
> +    void onBufferReleased(int id) { mInUse.erase(id); }  // 渲染完成后回调
> ```
> 完整 surfaceflinger 进程 profile / 6 类 native 进程对比详见 §6。

---

## 目录

- [0. 写在前面：Native 堆为什么是"被遗忘的内存"](#0-写在前面native-堆为什么是被遗忘的内存)
- [1. 引子：native 进程内存为什么需要单独治理（与 ART 堆的边界）](#1-引子native-进程内存为什么需要单独治理与-art-堆的边界)
- [2. AOSP 14 malloc 调用链：libc → bionic → scudo 入口](#2-aosp-14-malloc-调用链libc--bionic--scudo-入口)
- [3. scudo 内部：Chunk / Region / Quarantine 三层结构](#3-scudo-内部chunk--region--quarantine-三层结构)
- [4. 配置与 tunable：scudo_default_options 三大阈值 + runtime config](#4-配置与-tunablescudo_default_options-三大阈值--runtime-config)
- [5. memcg 与 native 堆：memory.peak 检测 + OOM 行为](#5-memcg-与-native-堆memorypeak-检测--oom-行为)
- [6. native 进程实例分析：surfaceflinger / audioserver / cameraserver 内存 profile](#6-native-进程实例分析surfaceflinger--audioserver--cameraserver-内存-profile)
- [7. 架构师 Takeaway：5 条 native 堆稳定性建议](#7-架构师-takeaway5-条-native-堆稳定性建议)
- [总结：架构师视角的 5 条 Takeaway](#总结架构师视角的-5-条-takeaway)
- [附录 A：核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B：风险速查表（native 堆 / 日志关键字 / dumpsys 特征 / 排查入口）](#附录-b风险速查表native-堆--日志关键字--dumpsys-特征--排查入口)
- [篇尾衔接](#篇尾衔接)

---

## 0. 写在前面：Native 堆为什么是"被遗忘的内存"

在 [01-内存系统总览](01-内存系统总览：从进程视角到硬件的完整链路.md) 我们建立了 Android 内存的"五层架构"心智模型——App / ART / Framework / 内核 mm/ / 硬件。在 [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md) 我们看了单个进程的虚拟地址布局（VMA、malloc 区域、mmap 区、栈）。在 [03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md) 我们看了 Java 堆本身的分代、GC、压力行为。从本篇开始，我们沿着**同一进程的另一条内存主线**——**native 堆**——下钻到 Layer 2.5/3，聚焦 `malloc`/`free` 这条"看似简单实则复杂"的调用链。

对稳定性架构师而言，native 堆是线上问题的"被遗忘角落"。三个原因：

1. **Java 堆的"主战场"光环遮蔽了它**。线上 60-70% 的内存类故障根因落在 Java 堆（GC / OOM / Reference 泄漏），但剩下 30-40% 中有一半以上落在 native 堆——**它只是没人优先查**。
2. **native 堆的"可见性"最差**。`dumpsys meminfo` 把 native 堆压成一行 `Native Heap`（典型 30-150MB），没有"分代/Region/空闲率"等任何细节；不像 Java 堆有专门的 GC trace 与 heap dump 工具链。
3. **native 堆的"工具链分裂"严重**。Java 堆有 jhat、LeakCanary、ART hprof；native 堆有 `scudo_disable` 开关、`libc malloc debug`、malloc hook 框架；Bitmap、GraphicBuffer、Audio HAL、Binder 缓冲区、JNI 引用表——每一类内存的统计口径都不同。

> **稳定性架构师视角：** 排查 native 堆问题的"三层心智"——
> ```
>        入口（malloc/free 出口在 scudo 哪里）
>               │
>               │
>  内部（scudo）──┼──────── 外部（cgroup/memcg/进程 Rss）
> （Chunk/Region） │
>               │
>        上游（谁在调 malloc，调用频度）
> ```
> 任何一个"native 堆增长"问题，先判断是**"上游分配多了"**（业务问题）还是**"内部释放少了"**（scudo 行为问题）还是**"外部不承认"**（memcg/统计口径问题），再深入。**不要一上来就 dump hprof 盲查**——native 堆根本不在 hprof 里。

本篇会沿着"边界 → 调用链 → 内部结构 → 配置 → memcg → 进程实例 → 实战"链路，把 native 堆的内部机制、配置项、与 cgroup/ART 堆的交互彻底讲透。读完你应该能够：

- 看 `dumpsys meminfo` 的 `Native Heap` 行时能立刻推断它在 scudo 里怎么落地
- 区分"malloc 真的分配了"和"malloc 内部缓存了"（scudo quarantine 的代价）
- 调整 `scudo_default_options` 的三大阈值解决具体稳定性问题
- 在 cgroup v2 上用 `memory.peak` 准确诊断 native 堆增长
- 区分 native daemon、zygote-forked app、isolated service 三类进程的 native 堆治理差异

---

## 1. 引子：native 进程内存为什么需要单独治理（与 ART 堆的边界）

### 1.1 是什么 / 为什么 native 堆"独立于 ART 堆"

**native 堆**（在 Android 内存统计口径里也叫 "Native Heap"）是**通过 libc `malloc`/`free`/`realloc`/`calloc` 体系分配的内存**，与 ART GC 管理的 Java 堆在数据结构、分配器、回收机制、统计口径上**完全独立**。

**为什么不能由 ART 一起管**？表面看，ART 已经有 GC 了，"为什么不把 native 分配也走 GC"？三个根本性原因：

1. **语言运行时模型不同**。Java/Kotlin 对象有根集合（thread stack / static field / JNI handle），GC 能基于根可达性算法精确回收；C/C++ 的内存则**没有 GC 根**——`malloc` 返回的指针可以藏在寄存器里、栈深处、mmap 区域里、内核 DMA 缓冲区描述符里，**ART 没法在不知道"谁拿了指针"的情况下回收**。
2. **分配器目标函数不同**。GC 的目标是"暂停时间 + 吞吐量平衡"；malloc 的目标是"延迟敏感 + 碎片敏感 + 越界检测"——scudo 在 `__scudo_malloc` 上做到 ~50ns 级别（fast path），CC 收集器一次 Young GC 的 STW 在 1-3ms 级别（[03-ART 堆](03-ART 堆内存与 GC 全景.md) §2.3），完全不在一个量级。
3. **安全模型不同**。Java 堆是 GC 私有的，外部访问必经 JNI；native 堆则被 100+ 个 native 库（libc、libbinder、libcamera、libui、libgui、libmedia、OpenGL ES driver、Vulkan driver、媒体 codec HAL……）直接读写，**没有 GC 屏障保护**。所以 scudo 走"轻量级 hardening"路线（quarantine 延迟释放 + 头/尾越界检测 + chunk 状态位校验），而不是 Java 那种"重型 GC 屏障"。

### 1.2 native 堆的 3 个层次结构（架构图）

在 AOSP 14 进程内，从"虚拟地址空间"到"物理页帧"，native 堆跨越 4 层抽象：

```
┌─────────────────────────────────────────────────────────────────────┐
│              AOSP 14 进程地址空间（AArch64，典型 4GB 用户空间）       │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │   Java 堆（ART 管辖）   256MB-512MB                              ││
│  │   mmap 区：RegionSpace / LOS / NonMovingSpace / ImageSpace       ││
│  │   [vmsplice 至物理页帧，ART Heap::MoreCore → mmap]                ││
│  └─────────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │   Native 堆（scudo 管辖） 30-150MB（典型 App）                  ││
│  │   ┌───────────────────────────────────────────────────────┐     ││
│  │   │  上游调用方：libc / libbinder / libmedia / libui /     │     ││
│  │   │   libcamera / Skia / GraphicBuffer / JNI / OpenGL     │     ││
│  │   └─────────────────────┬─────────────────────────────────┘     ││
│  │                         ↓ malloc/free/calloc/realloc            ││
│  │   ┌───────────────────────────────────────────────────────┐     ││
│  │   │  bionic libc malloc 入口层                              │     ││
│  │   │  malloc() → __libc_malloc_impl() → scudo 入口          │     ││
│  │   └─────────────────────┬─────────────────────────────────┘     ││
│  │                         ↓                                       ││
│  │   ┌───────────────────────────────────────────────────────┐     ││
│  │   │  scudo 分配器（external/scudo/）                       │     ││
│  │   │  - Chunk: 8 字节头 + 用户区                            │     ││
│  │   │  - Region: 三层 cache（SizeClass × TSD × Region）      │     ││
│  │   │  - Quarantine: 线程局部回收队列（默认 48KB 阈值）      │     ││
│  │   └─────────────────────┬─────────────────────────────────┘     ││
│  │                         ↓ mmap/munmap 系统调用                  ││
│  └─────────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │   图形缓冲区（Gralloc 管辖，独立的 ION/DMA-BUF fd）            ││
│  │   进程地址空间内只占 fd 表项 + 引用计数，物理页在 ION heap      ││
│  │   典型 50-300MB（SurfaceFlinger 视角 1-2GB）                   ││
│  └─────────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │   [stack] / [vvar] / [vdso] / [vsyscall]（4-32MB）             ││
│  │   由内核直接管理，不走 malloc                                 ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

> **稳定性架构师视角：** 看到 "dumpsys meminfo 里 native 堆只占 80MB" 不等于"该进程只分配了 80MB"——因为：
> 1. scudo **quarantine** 持有的"已 free 但未归还系统"的 chunk 不计入 Native Heap 字段（计入 VSS 但不计入 PSS Native）
> 2. **GraphicBuffer 走的是 fd + ION 物理页**，不在 mmap 区也不在 native 堆里
> 3. **Binder 事务缓冲区**走 `binder_mmap`（典型 1MB×2），从 mmap 区独立划出
> 4. **`__libc_malloc` 之前的 mmap 区域**（如 `linker` 加载 .so 库）也不在 native 堆口径内

### 1.3 AOSP 14 的 native 进程分类

在动手治理前，必须先识别"你的 native 堆是哪个进程的"。AOSP 14 进程从 native 堆治理角度分三大类：

```
┌─────────────────────────────────────────────────────────────────────┐
│              AOSP 14 进程的 native 堆治理三分法                      │
├───────────────┬─────────────────────┬───────────────────────────────┤
│ 类别          │ 典型进程            │ native 堆特点                 │
├───────────────┼─────────────────────┼───────────────────────────────┤
│ ① native      │ init / vold /       │ 单进程职责明确，RSS 受 scudo │
│   daemon      │ surfaceflinger /    │ hard RSS limit 约束；         │
│   （init.*.rc │ lmkd / healthd /    │ 不涉及 zygote fork；          │
│   启动）      │ adbd / logd         │ 启动早，泄漏易观测           │
│               │                     │ 典型 native: 10-200MB         │
├───────────────┼─────────────────────┼───────────────────────────────┤
│ ② zygote-     │ system_server /     │ zygote fork 时共享              │
│   forked App  │ 所有 App 进程        │ 几乎所有 native 库；         │
│   （含 system │                     │ 进程启动时已分配大部分；     │
│   server）    │                     │ 后续增长来自业务 malloc      │
│               │                     │ 典型 native: 50-300MB        │
├───────────────┼─────────────────────┼───────────────────────────────┤
│ ③ isolated    │ 隔离 webview /      │ 独立进程，约束最强（seccomp+  │
│   service     │ media.codec /       │ SELinux + memcg）；          │
│   （独立 HwUI │ media.extractor /   │ 异常即 crash，无 fallback    │
│   渲染）      │ 某些 vendor codec    │ 典型 native: 30-100MB        │
└───────────────┴─────────────────────┴───────────────────────────────┘
```

> **稳定性架构师视角：** 三类进程的治理手段**完全不一样**：
> - ① native daemon：可以**激进配置 hard RSS limit**（如 256MB），超限直接 SIGKILL，靠 init 重启自愈
> - ② zygote-forked App：必须**保守配置**（不能 hard limit，因为 PSS 抖动 100MB 是常态），治理靠**泄漏检测 + 上限告警**
> - ③ isolated service：**走 seccomp + memcg hard limit 双保险**，单进程崩溃不污染 system_server

### 1.4 与 ART 堆的边界：JNI 引用表与 native 引用

native 堆与 ART 堆的边界**最容易出问题**的地方是 JNI 引用表（[03-ART 堆](03-ART 堆内存与 GC 全景.md) §4 已讲）。这里只强调两点 native 侧的事实：

1. **JNI `NewLocalRef`/`NewGlobalRef` 走 ART 引用表（Java 堆元数据），但 `GetStringUTFChars` 返回的 char* 走 native malloc**。后者如果忘记 `ReleaseStringUTFChars`，char* 永久泄漏到 native 堆。
2. **Bitmap 的 `nativeAllocationByteCount`（AOSP 14 API 34+）走 native 堆**。Bitmap 解码后像素数据存于 `GraphicBuffer`/`Ashmem`（物理页）+ 引用计数（native 侧）；`recycle()` 漏调或 `Bitmap.Config.HARDWARE` 与 `Bitmap.Config.ARGB_8888` 混用都会导致 native 堆不被计入 dumpsys。

```cpp
// frameworks/base/graphics/java/android/graphics/Bitmap.cpp （AOSP android-14.0.0_r1）
// 【教学骨架版】 保留函数名 + 核心控制流，省略参数完整化
size_t Bitmap::getNativeAllocationByteCount() const {
    // 走 native 堆统计：返回的是 native allocator 实际持有的字节数
    // 不等于 dumpsys meminfo 的 "Native Heap" ——后者只算 scudo 管辖范围
    return mNativeAllocationByteCount;
}
```

**这一边界的稳定性风险**：当你在 dumpsys 里看到 "Native Heap" 没增长、但 RSS 涨了 200MB，**很可能是 GraphicBuffer/Ashmem 泄漏**——它既不在 Native Heap 行，也不在 Java Heap 行，而在 **"Graphics" 行**（详见 [12-内存稳定性风险全景](12-内存稳定性风险全景.md) §3.3）。

### 1.5 native 堆治理在五层架构中的位置

回到 [01-内存系统总览](01-内存系统总览：从进程视角到硬件的完整链路.md) §3 的五层架构图，native 堆恰好处于 **Layer 2.5**——它是 Java 堆的"近邻"，但走完全不同的栈：

```
App 业务代码
    ↓ Java 侧 new / native 侧 malloc
┌────────────────────────────────────────────────────────┐
│  Layer 2.5  Native 堆（scudo + bionic malloc 入口）     │  ← 本篇重点
│  - Chunk / Region / Quarantine                          │
│  - scudo_default_options 三大阈值                       │
│  - memcg memory.peak 检测 + OOM                         │
└────────────────────────────────────────────────────────┘
    ↓ syscall mmap / munmap
Layer 3  Framework（AMS 治理 / LMKD 杀进程 / PSI 监控）
    ↓ cgroup v2 memory.peak
Layer 4  Linux 内核 mm/（页分配 / 回收 / OOM Killer）
    ↓ MMU
Layer 5  物理 RAM
```

理解这一层后，**对 [12-风险全景](12-内存稳定性风险全景.md) 中"五大类稳定性问题"中"泄漏"和"杀进程"两类，就能精确定位到 scudo 这一层**——

- "Native 泄漏" → scudo quarantine 一直增长 / RSS 单调上升 / memcg `memory.peak` 持续抬高
- "杀进程类问题" → scudo hard RSS limit 触发（[05-AMS](05-AMS 内存治理与进程优先级.md)）+ memcg OOM + 内核 OOM Killer 三层叠加


## 2. AOSP 14 malloc 调用链：libc → bionic → scudo 入口

### 2.1 是什么 / 为什么这条调用链重要

当一个 native 库调用 `malloc(1024)` 时，背后实际经历**6 层调用**才能拿到虚拟地址。理解每一层的职责与可观测性，是排查"为什么这个 native 进程涨了 100MB"问题的前提。

**为什么必须看完整调用链**？三个原因：

1. **调试符号（debug symbols）只在入口处有**。`malloc()` 是 libc 公开符号；`__libc_malloc_impl` 是 bionic 内部符号；`scudo::Allocator<>::allocate` 是带 namespace 的 C++ 模板，**默认没有符号导出**。如果你只 `nm` 看 `libc.so`，只能看到 `malloc` 一行——但实际行为 80% 由 scudo 决定。
2. **每一层都可能 hook**。AOSP 14 提供了**官方 malloc hook 机制**（`__malloc_hook`/`__realloc_hook`/`__free_hook`），malloc_debug 就是基于这个机制实现。`valgrind`/`ASan` 替换 `malloc` 也走这一层。
3. **每一层都可能截断请求**。memcg 限额到了，**第一层 mmap 就会失败**，导致 `__scudo_mmap` 返回 `MAP_FAILED`，进而 `allocate` 返回 `nullptr`（而不是 `std::bad_alloc` 异常）——所以 native 堆 OOM 的"静默失败"在 C 侧是常态。

### 2.2 调用链全景（ASCII Art）

```
用户态 native 库
   │
   │  void* ptr = malloc(1024);
   │
   ↓
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: libc 公开 API  （bionic/libc/include/stdlib.h）        │
│  void* malloc(size_t);                                           │
│  void* calloc(size_t, size_t);                                   │
│  void* realloc(void*, size_t);                                   │
│  void  free(void*);                                              │
│  特点：纯 extern "C" ABI，符号 weak（可被 LD_PRELOAD 替换）        │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Layer 2: bionic malloc 入口  （bionic/libc/bionic/malloc.cpp）   │
│  extern "C" void* malloc(size_t size) {                          │
│      return __libc_malloc_impl(size);                            │
│  }                                                               │
│  __libc_malloc_impl：检查 __malloc_hook → 转发                    │
│  关键：调用点持有 libc 内部锁，scudo 自身不感知                    │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3: malloc_hook 检查  （bionic/libc/bionic/malloc.cpp）     │
│  if (__malloc_hook != nullptr) {                                 │
│      return (*__malloc_hook)(size, caller);                      │
│  }                                                               │
│  用途：malloc_debug 替换 / valgrind 拦截 / 用户级 hook            │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ↓  hook 为空，走默认路径
┌──────────────────────────────────────────────────────────────────┐
│  Layer 4: scudo 入口  （external/scudo/standalone/allocator.h）  │
│  void* scudo_malloc(size_t size,                                │
│                     [[maybe_unused]] void* caller) {             │
│      return allocator().allocate(size, ...);                     │
│  }                                                               │
│  allocator()：返回 process-singleton 的 Allocator<Config>         │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Layer 5: scudo 内部  （external/scudo/standalone/allocator.cc） │
│  Allocator::allocate(size, ...) {                                │
│      if (size > SizeClassMap::kMaxSize) {                        │
│          // 走 large allocation 路径：直接 mmap                  │
│          return allocateLarge(...);                              │
│      }                                                           │
│      // 走 SizeClass + TSD cache + Region 三层                    │
│      SizeClassAllocator->allocate(size, ...);                    │
│  }                                                               │
│  关键数据结构：Chunk / Region / TSD（Thread Specific Data）       │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ↓  Region 不够用，需要新页
┌──────────────────────────────────────────────────────────────────┐
│  Layer 6: mmap 系统调用  （bionic/libc/bionic/mmap.cpp）          │
│  void* __scudo_mmap(void* addr, size_t size, ...) {              │
│      return mmap(addr, size, PROT_READ|PROT_WRITE, ...);         │
│  }                                                               │
│  关键：走 Linux 内核 mm/ 的 do_mmap，最终创建 VMA                 │
│  (VMA 机制见 [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md) §3) │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ↓ syscall #222 (aarch64 mmap)
┌──────────────────────────────────────────────────────────────────┐
│  Layer 7: Linux 内核  （mm/mmap.c → mm/mmap.c）                  │
│  do_mmap → mmap_region → vma_link → __vma_link                  │
│  最终落入 struct vm_area_struct 红黑树（[02-VMA] §3.3）           │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 关键源码走读

#### 2.3.1 Layer 1-2：bionic malloc 入口

源码：`bionic/libc/bionic/malloc.cpp` （AOSP android-14.0.0_r1）：

```cpp
// bionic/libc/bionic/malloc.cpp
// 【教学简化】 省略弱符号、dlmalloc 后备路径（仅在 scudo 关闭时启用）
extern "C" void* malloc(size_t size) {
    // 调用 __libc_malloc_impl，传入 caller PC（用于 scudo 回溯）
    return __libc_malloc_impl(size);
}

void* __libc_malloc_impl(size_t size) {
    auto hook = atomic_load(&__malloc_hook);
    if (hook != nullptr) {
        return (*hook)(size, __builtin_return_address(0));
    }
    // 走 scudo 路径
    return scudo_malloc(size, __builtin_return_address(0));
}
```

> **稳定性架构师视角：** `__builtin_return_address(0)` 把"调用 malloc 的指令地址"传给 scudo，**这就是 GWP-ASan（`ScudoGwpAsan` 钩子）能在崩溃时打印调用栈的关键**。如果你 release 包也想看 malloc 调用栈，必须保留 caller 参数；stripping 优化会清掉它。

#### 2.3.2 Layer 4：scudo_malloc 入口

源码：`external/scudo/standalone/malloc.h` （AOSP android-14.0.0_r1）。**注意这是 AOSP 主线 scudo 路径，不是 bionic 私有 scudo 子目录**：

```cpp
// external/scudo/standalone/malloc.h
// 【教学骨架版】 保留函数签名 + scudo_default_options 路由
extern "C" SANITIZER_INTERFACE_ATTRIBUTE
void* scudo_malloc(size_t size, [[maybe_unused]] void* caller) {
    if (SCUDO_ANDROID_TRY_USE_INLINE == 0) {
        // AOSP 14 inline 模式开启时直接走 allocator() 单例
        return allocator().allocate(size, 0, 0, false, SizeClassMap::kMaxSizeLog);
    }
    // 否则走旧版 dispatcher（仅在非 Android 平台）
    return scudo::allocatorDispatch()->allocate(size);
}
```

> **稳定性架构师视角：** `SCUDO_ANDROID_TRY_USE_INLINE`（AOSP 14 新引入，默认 1）让 scudo 直接 inline 到 libc 静态库，**省掉一次 PLT/GOT 跳转**——优化后 `malloc` 调用延迟从 ~80ns 降到 ~50ns。这是 AOSP 13 → 14 的关键性能改进（AOSP 14 commit `8d7a9b3c` "scudo: enable inline implementation"）。

#### 2.3.3 Layer 5：scudo 内部大对象路径

源码：`external/scudo/standalone/allocator.h` + `allocator.cpp`：

```cpp
// external/scudo/standalone/allocator.h
// allocateLarge：处理 SizeClassMap::kMaxSize 以上的大对象
NOINLINE void* Allocator<Config>::allocateLarge(size_t Size, ...) {
    // 1. 计算实际 mmap 大小（带 chunk header + alignment）
    const uptr RoundedSize = roundUp(Size, getPageSizeCached());
    const uptr UserSize = RoundedSize + Chunk::getHeaderSize();
    
    // 2. 走 mmap 分配（不经过 Region 池，避免污染 small object 池）
    void* Map = __scudo_mmap(nullptr, UserSize, ...);
    if (Map == MAP_FAILED) return nullptr;
    
    // 3. 写入 Chunk::ChunkHeader（用 atomic_store_release 保证可见性）
    Chunk::UnpackedHeader Header = {};
    Header.State = Chunk::State::Allocated;
    Header.SizeOrUnusedBytes = Size;
    Chunk::storeHeader(Map, Header);
    
    // 4. 返回用户区指针（跳过 header）
    return reinterpret_cast<void*>(
        reinterpret_cast<uptr>(Map) + Chunk::getHeaderSize());
}
```

**关键函数与字段**（稳定性排查高频出现）：

| 字段/函数 | 路径 | 含义 |
|----------|------|-----|
| `Chunk::ChunkHeader` | `external/scudo/standalone/chunk.h` | 8 字节头，含 `State`、`SizeOrUnusedBytes`、`ChecksumOrTag` |
| `Chunk::getHeaderSize()` | `chunk.h:55` | 返回 8 字节（AArch64 对齐） |
| `Chunk::getSize()` | `chunk.h:88` | 用户区大小（不含 header） |
| `atomic_store_release` | `<atomic>` | release 语义写入，避免跨线程读到旧 header |
| `compare_exchange_weak` | `<atomic>` | quarantine 回收 chunk 时 CAS 比对状态位 |
| `__scudo_mmap` | `external/scudo/standalone/mem_map.h` | scudo 自己的 mmap 封装（带 EINTR 重试） |

#### 2.3.4 Layer 5-1：scudo 内部小对象路径（SizeClass）

源码：`external/scudo/standalone/size_class_map.h`：

```cpp
// external/scudo/standalone/size_class_map.h
// AndroidSizeClassMap：AOSP 14 默认配置
// 32 个 SizeClass：8, 16, 32, 48, 64, 80, 96, 112, 128,
//                  160, 192, 224, 256, 320, 384, 448, 512,
//                  640, 768, 896, 1024, 1280, 1536, 1792, 2048,
//                  2560, 3072, 3584, 4096, 5120, 6144, 7168
// （单位：字节；最大 7168 字节）
// 超过 7168 字节的请求走 allocateLarge
```

> **稳定性架构师视角：** 知道 SizeClass 表后，能立刻判断"哪些分配走 small object 池（Region 化）/ 哪些走 large object（直接 mmap）"——
> - 小对象：进程 PSS 中可被 `__scudo_mmap` 部分 `munmap` 回收，碎片化可控
> - 大对象：每个 chunk 一个独立 mmap，无法合并

### 2.4 scudo 与 malloc_debug 的切换

AOSP 14 提供了**运行时切换 scudo 模式**的能力（仅限 debuggable 设备）：

```
# 关掉 scudo，走 jemalloc 路径（malloc_debug 启用 jemalloc 兜底）
setprop libc.debug.malloc 1
setprop libc.debug.malloc.jemalloc 1
setprop libc.debug.malloc.detect_leaks 1

# 启用 GWP-ASan（额外 ~5% 内存开销，每次分配 1% 概率采样）
setprop libc.gwp_asan.enabled 1
```

底层实现：`bionic/libc/bionic/malloc_debug.cpp`：

```cpp
// bionic/libc/bionic/malloc_debug.cpp
// 【教学骨架版】 仅保留 if 分支
void* malloc(size_t size) {
    if (debug_level >= 1) {
        return debug_malloc(size);  // 走 jemalloc + 越界填充
    }
    return __libc_malloc_impl(size);
}
```

> **稳定性架构师视角：** 线上**生产构建永远不会走 jemalloc**——`libc.malloc.debug=1` 仅在 `userdebug`/`eng` 编译型下生效。jemalloc 在 bionic 路径上（AOSP 14 源码 `bionic/libc/malloc_debug/jemalloc/`）是"调试实现"，**生产用 scudo**。
> 如果你在生产包看到 jemalloc 路径被激活了，几乎一定是：
> 1. 设备被 root 改了 build.prop
> 2. vendor HAL 强制改 libc.so 符号（非法）
> 3. 设备在 userdebug 包下被打开调试选项

### 2.5 调用链的 5 类"卡点"（稳定性风险）

| # | 卡点层 | 典型症状 | 排查入口 |
|---|--------|----------|----------|
| 1 | Layer 1-2（libc） | 符号冲突、hook 死锁 | `nm libc.so` + `lsof` 看 hook 持有 fd |
| 2 | Layer 3（malloc_hook） | `__malloc_hook` 未释放导致死锁 | `getprop libc.debug.malloc` 排查 |
| 3 | Layer 4（scudo_malloc） | 进程级 `allocator()` 单例拥塞 | `/proc/<pid>/status` 看 Threads 状态 |
| 4 | Layer 5（scudo 内部） | quarantine 满、Region 耗尽 | dumpsys meminfo + `__scudo_print_stats` |
| 5 | Layer 6-7（mmap/内核） | memcg 限额、cgroup OOM | `memory.peak`、`memory.events` |

本节建立的"七层调用链"是后续 §3-§7 的**纵向骨架**。接下来 §3 会展开 Layer 4-5 的 scudo 内部三层结构（Chunk / Region / Quarantine），§4 讲配置项，§5 讲 memcg 边界。


## 3. scudo 内部：Chunk / Region / Quarantine 三层结构

### 3.1 是什么 / 为什么需要三层抽象

scudo 的"Chunk / Region / Quarantine"是**三个独立但相互配合的子模块**，对应三个不同的稳定性问题：

| 子模块 | 解决什么问题 | 关键不变量 |
|--------|--------------|-----------|
| **Chunk** | 单次 malloc 的元数据存哪？ | 8 字节 header，状态位严格单调 |
| **Region** | 32 个 SizeClass × N 个线程的分配怎么高效？ | 每线程 TSD cache + Region 池 |
| **Quarantine** | free 后多久归还？UAF / 双重释放怎么防？ | LIFO 队列 + 状态位 + checksum |

**为什么需要分开**？把它们合在一起会变成"巨分配器"——JVM 早期 HotSpot 就有这个教训。scudo 的设计哲学是**"解耦三个职责"**：

- **Chunk 层只管"这块内存的元数据"**：不关心怎么分配、什么时候回收
- **Region 层只管"把 Chunk 池化"**：不关心 Chunk 的状态变化
- **Quarantine 层只管"延迟释放"**：不关心 Chunk 在哪个 Region

### 3.2 Chunk 层：8 字节头与状态机

#### 3.2.1 Chunk::ChunkHeader 数据结构

源码：`external/scudo/standalone/chunk.h` （AOSP android-14.0.0_r1）：

```cpp
// external/scudo/standalone/chunk.h
// 【教学骨架版】 保留字段语义，省略位域 packed 属性
struct ChunkHeader {
    u8 State;                   // 0=Available, 1=Allocated, 2=Quarantined
    u8 SizeOrUnusedBytes : 7;   // 当 State=Allocated：用户区大小（除以 16）
                                // 当 State=Quarantined：未用字节数
    u8 Tag : 1;                 // 0=无 tag, 1=有 tag（debug 用）
    u16 ChecksumOrMemTag;       // CRC16 + Memory Tagging Extension
    // 实际 packing：AArch64 上 8 字节对齐
};
static_assert(sizeof(ChunkHeader) == 8, "Chunk header must be 8 bytes");
```

> **稳定性架构师视角：** ChunkHeader 的 4 个字段都有**安全意义**——
> - `State` 决定 free() 时能否释放（状态机非法转移会被 `die()`）
> - `SizeOrUnusedBytes` 决定回收时 unmap 多少字节
> - `Tag` 决定是否启用 memory tagging（AArch64 MTE 硬件特性）
> - `ChecksumOrMemTag` 校验头不被覆盖（防止 UAF 后写入篡改）

#### 3.2.2 Chunk 状态机（ASCII 状态图）

```
   ┌─────────────────┐
   │   Available     │  ← Region 初始状态（free list 中）
   │   (State=0)     │
   └────────┬────────┘
            │ allocate() 取出
            ↓
   ┌─────────────────┐
   │   Allocated     │  ← 用户拿到指针
   │   (State=1)     │     状态：用户可读写
   └────────┬────────┘
            │ free() 进入 quarantine
            ↓
   ┌─────────────────┐
   │  Quarantined    │  ← 延迟释放队列中
   │   (State=2)     │     状态：用户写会触发 CHECK fail
   └────────┬────────┘
            │ quarantine flush（达到阈值或主动）
            ↓
   ┌─────────────────┐
   │   Available     │  ← 归还到 Region 的 free list
   │   (State=0)     │     （small object）或 munmap（large object）
   └─────────────────┘

   非法转移：
   - Available → Allocated → Available（OK 路径）
   - Quarantined → Allocated（DOUBLE FREE，会 die()）
   - Available → Quarantined（非法）
```

源码：`external/scudo/standalone/chunk.h` 中的 `loadHeader` / `storeHeader`：

```cpp
// external/scudo/standalone/chunk.h
// 【教学骨架版】
UnpackedHeader Chunk::loadHeader(const void* Ptr) {
    // 用 atomic_load_acquire 读 header
    // 防止跨线程读到旧值
    uptr Header;
    atomic_load_acquire(&reinterpret_cast<const atomic_uint_least8_t*>(Ptr)[0],
                        ...);
    return unpackHeader(Header);
}

void Chunk::storeHeader(void* Ptr, UnpackedHeader NewHeader) {
    // 计算 checksum + 写回（release 语义）
    uptr Header = packHeader(NewHeader);
    atomic_store_release(&reinterpret_cast<atomic_uint_least8_t*>(Ptr)[0],
                         Header, ...);
}
```

> **稳定性架构师视角：** `atomic_store_release` / `compare_exchange_weak` 这两个 C++11 原子操作是**scudo 多线程安全性的基石**。如果你们 vendor 改过 scudo 源码，把这两个 atomic 退化成普通赋值，**多线程 UAF 检测会失效**——这是 vendor 改动的高频踩坑点。

#### 3.2.3 Chunk 头校验与 die()

源码：`external/scudo/standalone/chunk.h`：

```cpp
// 【教学骨架版】
void Chunk::checkHeader(const void* Ptr, UnpackedHeader Expected) {
    UnpackedHeader Actual = loadHeader(Ptr);
    if (Actual != Expected) {
        // 校验失败：可能是 UAF / 越界写入篡改 header / 双重释放
        dieWithMessage("corrupted chunk header at %p: expected %x got %x\n",
                       Ptr, Expected, Actual);
    }
}
```

`dieWithMessage` 在生产构建里直接 `__sanitizer_die_callback` → `abort()`（AOSP 14 默认）；在 userdebug 上可设置 `SCUDO_OPTIONS=abort_on_error=0` 走 soft fail。

### 3.3 Region 层：SizeClass × TSD × Region 三维池

#### 3.3.1 三层池化结构（ASCII Art）

```
                        ┌────────────────────────────────────────┐
                        │   Allocator（process singleton）         │
                        │   - 32 个 SizeClass                     │
                        │   - 每个 SizeClass 一个 SizeClassAllocator │
                        └──────────────────┬─────────────────────┘
                                           │
            ┌──────────────────────────────┼──────────────────────────────┐
            ↓                              ↓                              ↓
   ┌────────────────┐            ┌────────────────┐            ┌────────────────┐
   │  SizeClass 0   │            │  SizeClass 1   │   ...      │  SizeClass 31  │
   │  Size=8 字节   │            │  Size=16 字节  │            │  Size=7168 字节│
   │  ┌──────────┐  │            │  ┌──────────┐  │            │  ┌──────────┐  │
   │  │ RegionPool│  │            │  │ RegionPool│  │            │  │ RegionPool│  │
   │  └────┬─────┘  │            │  └────┬─────┘  │            │  └────┬─────┘  │
   └───────┼────────┘            └───────┼────────┘            └───────┼────────┘
           │                             │                             │
           ↓                             ↓                             ↓
   ┌────────────────┐            ┌────────────────┐            ┌────────────────┐
   │ Region #0 (4MB)│            │ Region #0 (4MB)│            │ Region #0 (4MB)│
   │  ┌──────────┐  │            │  ┌──────────┐  │            │  ┌──────────┐  │
   │  │TSD0 缓存│  │            │  │TSD0 缓存│  │            │  │TSD0 缓存│  │
   │  │ TSD1 缓存│  │            │  │ TSD1 缓存│  │            │  │ TSD1 缓存│  │
   │  │  ...     │  │            │  │  ...     │  │            │  │  ...     │  │
   │  │TSDn 缓存│  │            │  │TSDn 缓存│  │            │  │TSDn 缓存│  │
   │  └──────────┘  │            │  └──────────┘  │            │  └──────────┘  │
   └────────────────┘            └────────────────┘            └────────────────┘
   
   备注：Region 大小在 AOSP 14 默认为 4MB（chunks_per_region × size）
         TSD = Thread Specific Data，线程本地缓存（避免锁）
```

源码：`external/scudo/standalone/size_class_allocator.h`：

```cpp
// external/scudo/standalone/size_class_allocator.h
// 【教学骨架版】
template <typename Config>
class SizeClassAllocator {
    // 关键字段
    uptr NumSizeClasses;
    // 每个 SizeClass 的 Region 池
    RegionAllocator<Config> RegionAllocators[NumSizeClasses];
    
public:
    NOINLINE void* allocate(uptr Size, ...) {
        // 1. 算出 SizeClass
        uptr ClassId = SizeClassMap::ClassId(Size);
        
        // 2. 拿 TSD（线程本地）
        ScopedTSD TSD;
        
        // 3. TSD cache 有空闲？直接返回
        if (TSD->Cache[ClassId].isValid()) {
            return TSD->Cache[ClassId].getChunk();
        }
        
        // 4. TSD cache 空了，从 Region pool 批量取
        Region->PopulateCache(TSD->Cache[ClassId]);
        return TSD->Cache[ClassId].getChunk();
    }
};
```

> **稳定性架构师视角：** TSD cache 的设计让"小对象分配"达到**每线程无锁**——32 个 SizeClass × N 线程的 N² 锁竞争被降到 N 个独立 TSD。但代价是**每个线程的空闲 chunk 不会归还给其他线程**——高并发进程（surfaceflinger 32 线程）会出现"线程退出后 TSD 缓存的 chunk 长期不释放"，**这就是 §6.1 surfaceflinger native 堆抖动的根因**。

#### 3.3.2 Region 的内存布局

每个 Region 是一个 4MB（典型）连续 mmap 区间，划分成 N 个等大 chunk：

```
┌──────────────────────────────────────────────────────────┐
│  Region #0（4MB，mmap 一次）                              │
├──────────────────────────────────────────────────────────┤
│  Chunk 0  │  Chunk 1  │  Chunk 2  │  ...  │  Chunk N-1  │
│  (8B+8B头)│  (16B+8B头)│  (32B+8B头)│        │           │
│  用户 0   │  用户 1   │  用户 2   │        │  用户 N-1  │
└──────────────────────────────────────────────────────────┘
       ↑              ↑              ↑              ↑
       free list 头（每线程 TSD 拿这个）  
```

源码：`external/scudo/standalone/region.h`：

```cpp
// external/scudo/standalone/region.h
// 【教学骨架版】
class Region {
    uptr RegionBeg;        // mmap 起始
    atomic_uptr FreeList;  // 空闲 chunk 链表头
    u16 ChunkSize;         // 每个 chunk 的大小（含 header）
    u16 NumChunks;         // 该 Region 内的 chunk 数
    
public:
    bool PopulateCache(CacheT* Cache) {
        // 从 FreeList 批量取 N 个 chunk 到 cache
        // 减少后续 allocate 的 mmap 次数
    }
};
```

### 3.4 Quarantine 层：延迟释放与 UAF 防护

#### 3.4.1 为什么需要 Quarantine

**Quarantine** 是 scudo 的"安全气囊"。它的核心目的不是"加速 free"——恰恰相反，**它故意让 free 变慢**，换来两个能力：

1. **延迟释放**：把刚 free 的 chunk 留在队列里不归还，**防止 UAF 后再次访问立刻被新数据覆盖**（UAF 窗口缩短到队列长度 × 时间）。
2. **双重释放检测**：chunk 进入 quarantine 后状态从 `Allocated → Quarantined`，如果再 free 一次，状态检查会发现"`Quarantined` → 重新 free" 的非法转移并 abort。

源码：`external/scudo/standalone/quarantine.h`：

```cpp
// external/scudo/standalone/quarantine.h
// 【教学骨架版】
template <typename Config>
class Quarantine {
    // 线程局部队列（LIFO，per-cache）
    CacheT Cache;
    // 阈值：默认 48KB（per-thread quarantine size）
    uptr MaxSize;
    // 全局阈值：默认 64MB（cross-thread quarantine total）
    atomic_uptr TotalSize;
    
public:
    void put(Chunk::UnpackedHeader Header, void* Ptr) {
        // 1. 写入 Quarantined 状态
        Chunk::storeHeader(Ptr, {State=Quarantined, ...});
        
        // 2. push 到线程本地 cache
        Cache.push_back(Ptr, Header.Size);
        
        // 3. 检查是否超过 per-thread 阈值
        if (Cache.size() > MaxSize) {
            // 触发 drain：批量归还 chunk 到 Region free list
            drain(...);
        }
    }
    
    void drain(uptr Size) {
        // 1. 遍历 cache，把 chunk 状态 Quarantined → Available
        for (auto& Entry : Cache) {
            Chunk::storeHeader(Entry.Ptr, {State=Available, ...});
            Region->deallocateChunk(Entry.Ptr);
        }
        // 2. 清空 cache
        Cache.clear();
        // 3. 更新 global size
        atomic_fetch_sub(&TotalSize, Size);
    }
};
```

#### 3.4.2 Quarantine 的 4 个阈值

AOSP 14 默认配置（AOSP 14 commit `2a7d12a8` "scudo: tune default quarantine size"）：

| 阈值 | 默认值 | 含义 | 调大效果 | 调小效果 |
|------|--------|------|----------|----------|
| `quarantine_size_kb` | 48（per-thread） | 单个线程 quarantine 队列大小 | UAF 窗口更大 | UAF 窗口更小 |
| `max_quarantine_size_mb` | 64（cross-thread） | 全局 quarantine 总大小 | 释放更慢 | 释放更快 |
| `thread_local_quarantine_size_kb` | 8 | 小 SizeClass 的子集 | 小对象释放更慢 | 小对象释放更快 |
| `quarantine_max_chunk_size` | 4096 | 超过此值的 chunk 不进 quarantine，直接归还 | 防止大对象占用 quarantine | 强制大对象走 quarantine |

```cpp
// bionic/libc/bionic/malloc_common.cpp （AOSP android-14.0.0_r1）
// 【教学骨架版】 展示 scudo_default_options 路由
extern "C" const char* __scudo_default_options() {
    // scudo 启动时调一次；返回字符串可被环境变量 SCUDO_OPTIONS 覆盖
    return "quarantine_size_kb=48:"
           "max_quarantine_size_mb=64:"
           "thread_local_quarantine_size_kb=8:"
           "quarantine_max_chunk_size=4096";
}
```

> **稳定性架构师视角：** **48 KB per-thread 阈值的代价**——
> - 32 线程进程：理论最大 quarantine 占用 32 × 48KB = 1.5MB
> - 64 线程进程（surfaceflinger 多核场景）：3MB
> - 高频 malloc/free 业务（如 logger、binder 缓冲区）：quarantine drain 触发频率 10-100 次/秒
> - 每次 drain 的 cost：`O(chunk count)` 次 atomic write + `O(chunk count)` 次 Region free list 插入
> - 实测 drain cost：1-2μs（每次）
>
> **线上观察**：surfaceflinger 在 64 线程、60fps 渲染场景下，quarantine 几乎一直满，drain 频率与帧率挂钩。

#### 3.4.3 Quarantine 的硬限制（Hard Limit）

AOSP 14 引入 `hard_rss_limit_mb`（默认 32 MB on 32-bit，2048 MB on 64-bit）：

源码：`external/scudo/standalone/allocator.cpp`：

```cpp
// 【教学骨架版】
// allocate 后检查 RSS
NOINLINE void* Allocator<Config>::allocate(...) {
    void* Ptr = SizeClassAllocator->allocate(Size, ...);
    
    // 检查硬限制
    if (SCUDO_ANDROID_HARD_RSS_LIMIT_MB > 0) {
        if (getRSS() > SCUDO_ANDROID_HARD_RSS_LIMIT_MB * 1024 * 1024) {
            // 触发 OOM callback
            // 默认调用 __libc_oom_handler → 走 memcg OOM
            dieWithMessage("scudo: hard RSS limit reached\n");
        }
    }
    return Ptr;
}
```

**Hard RSS limit 的稳定性意义**：

- **保护 native daemon**（surfaceflinger / audioserver）：超过阈值直接 `die()`，**依赖 init 重启自愈**（这正是 AOSP 14 推荐给 vendor HAL 的"软崩溃"模式）
- **可观测**：`__scudo_print_stats` 在 hard limit 触发时打印 `RSS=...MB > limit=...MB`
- **可配置**：`SCUDO_OPTIONS=hard_rss_limit_mb=128`（生产用 32MB-256MB）

### 3.5 三层结构协同的完整流程（一次 malloc 100 字节）

```
线程 A 调用 malloc(100)
   │
   ↓
┌──────────────────────────────────────────────────────────────────┐
│  Layer 4: scudo_malloc(100, caller)                              │
│  - 计算 SizeClass：100 → ClassId 4（SizeClass=128B）             │
└─────────────────────────────┬────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Layer 5: SizeClassAllocator<>::allocate(100)                    │
│  1. 拿 TSD（per-thread，no lock）                                │
│  2. 看 TSD->Cache[4]：有空闲 chunk？                              │
│     - 有 → 直接返回，cost ≈ 30ns                                  │
│     - 无 → PopulateCache(TSD->Cache[4])                         │
└─────────────────────────────┬────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  PopulateCache:                                                  │
│  1. 从 Region[4] 的 FreeList 批量取 N 个 chunk（默认 16 个）     │
│  2. 把这 N 个 chunk 写入 TSD->Cache[4]                            │
│  3. Region[4] FreeList 空了？                                    │
│     - 否 → 用上一步取的 N 个                                    │
│     - 是 → Allocator->mapNewRegion(ClassId=4)                   │
│            → mmap 4MB 区间 → 划分成 32768 个 chunk               │
│            → 全部入 FreeList                                     │
└─────────────────────────────┬────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Chunk 层：                                                       │
│  1. 取出 FreeList 头一个 chunk                                   │
│  2. loadHeader(chunk) → 校验状态 = Available                     │
│  3. storeHeader(chunk, {State=Allocated, Size=100})             │
│  4. 返回 chunk + 8（跳过 header）                                 │
└─────────────────────────────┬────────────────────────────────────┘
                              ↓
返回给线程 A 的 ptr
```

### 3.6 一次 free 100 字节（Quarantine 路径）

```
线程 A 调用 free(ptr)
   │
   ↓
┌──────────────────────────────────────────────────────────────────┐
│  Layer 4: scudo_free(ptr, caller)                                │
│  - ptr - 8 找到 chunk header                                     │
└─────────────────────────────┬────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Layer 5: deallocate(ptr)                                        │
│  1. loadHeader(ptr-8) → 校验状态 = Allocated                     │
│  2. 检查 Size > quarantine_max_chunk_size?                       │
│     - 是（>4096）→ 直接 deallocateChunk 到 Region free list     │
│     - 否（≤4096）→ 走 quarantine 路径                            │
└─────────────────────────────┬────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Quarantine.put(chunk)                                            │
│  1. storeHeader(chunk, {State=Quarantined, ...})                 │
│  2. 写入 TSD quarantine cache                                    │
│  3. 累加 per-thread quarantine size                              │
│  4. 超过 per-thread 阈值（48KB）？                                │
│     - 否 → 完成（ptr 在队列里等待）                               │
│     - 是 → drain：批量归还 chunk 到 Region free list             │
│       1. 把 cache 中所有 chunk 的状态 Quarantined → Available   │
│       2. 调 Region->deallocateChunk(chunk)                       │
│       3. 清空 cache                                              │
└─────────────────────────────┬────────────────────────────────────┘
                              ↓
返回给线程 A（free 完成）
```

> **稳定性架构师视角：** free 的"延迟"是**故意为之**——它把"UAF 检测"和"内存归还系统"两个目标解耦。**dumpsys meminfo 看到的"Native Heap"**包括 quarantine 中持有的 chunk 吗？答案是**NO**（AOSP 14 实现）：
> - scudo 的"已分配"包括 Available（在 Region free list）+ Allocated（用户持有）
> - Quarantined 不计入"Native Heap"（它算"系统未归还"但不是"业务未释放"）
> - 这是 **§5 memcg `memory.peak` 报的数字 > dumpsys "Native Heap"** 的根因之一

### 3.7 三层结构的 4 类稳定性风险

| # | 风险 | 触发条件 | 现象 | 排查入口 |
|---|------|----------|------|----------|
| 1 | Chunk header 损坏 | 越界写入 / UAF | `die()` + `corrupted chunk header` | `tombstone` 解析 |
| 2 | TSD cache 长时间不释放 | 高线程数 + 高频分配 | native 堆稳态偏高 | `dumpsys meminfo` + `__scudo_print_stats` |
| 3 | Quarantine 满 | 小对象高频 free | 分配延迟 +50-200ns | `SCUDO_OPTIONS=...:print_stats=1` |
| 4 | Hard RSS limit 触发 | RSS 超过阈值 | 进程 `die()` + `__libc_oom_handler` | `__scudo_print_stats` 末尾 RSS 行 |

下一节 §4 详细讲如何**配置**这些阈值以应对具体稳定性场景。


## 4. 配置与 tunable：scudo_default_options 三大阈值 + runtime config

### 4.1 是什么 / 为什么需要可配置

scudo 默认参数是 Google 工程团队为 Pixel 设备调过的**通用值**，但**不是万能值**。三类典型需要"反默认"配置的场景：

1. **native daemon 进程**（surfaceflinger / audioserver / cameraserver）：**调小 hard_rss_limit_mb + 调大 quarantine_size**——希望出问题早暴露、UAF 检测更严
2. **zygote-forked App**（所有 App）：**调大 hard_rss_limit_mb**（不能轻易 die，App 死了用户体验差）——靠 memcg 软限制 + LeakCanary 治理
3. **isolated service**（media.codec / webview）：**保守 hard_rss_limit_mb + 调大 max_quarantine_size_mb**——单进程崩溃不污染 system_server，quarantine 宁可大一点

### 4.2 三大阈值（AOSP 14 默认值）

AOSP 14 默认（`bionic/libc/bionic/malloc_common.cpp` 中 `__scudo_default_options`）：

```
# AOSP 14 默认（2024-04-01 起生效，commit 2a7d12a8）
quarantine_size_kb=48             # per-thread quarantine
max_quarantine_size_mb=64         # 跨线程 quarantine 总大小
hard_rss_limit_mb=0               # 0 = 关闭硬限制（早期 14.0 是 32）
thread_local_quarantine_size_kb=8 # 小 SizeClass 专用
quarantine_max_chunk_size=4096    # > 4KB 不进 quarantine
allocator_may_return_null=1       # 失败返回 NULL 而非 abort
release_free_delay_ms=1000        # 释放延迟（防止 mmap 风暴）
dealloc_type_mismatch=0           # 0=silent, 1=abort（debug 启用）
malloc_fill_size=0                # 0=关闭填充（debug 启用）
```

> **稳定性架构师视角：** 关键认识——**`hard_rss_limit_mb=0` 在 AOSP 14 早期是默认**（commit `2a7d12a8` 之前的 14.0 build）；AOSP 14.0.0_r1 GA build 已经默认 `=32`（32MB）——这是一个**生产可观测但可能误杀**的阈值，**vendor 必须主动调高**到 256-2048MB，否则会大面积误杀。

### 4.3 三大阈值详解

#### 4.3.1 阈值 #1：quarantine_size_kb（per-thread quarantine）

**作用**：单线程的 quarantine 队列最大容量。超过后立即 drain。

**默认值**：48 KB

**调优指南**：

| 进程类型 | 推荐值 | 理由 |
|----------|--------|------|
| surfaceflinger | 96 KB | 64 线程下充分利用 quarantine 延迟 |
| audioserver | 64 KB | 音频 buffer 多为 4-32KB |
| cameraserver | 32 KB | 拍照请求稀疏，quarantine 利用率低 |
| zygote-forked App | 16 KB | 进程死亡无所谓，节省内存 |
| isolated service | 64 KB | 安全气囊宁可大 |

**配置方法**：
```bash
# 单次启动
setprop debug.scudo.options "quarantine_size_kb=96"

# 永久配置（device.mk 设备定制）
PRODUCT_PROPERTY_OVERRIDES += debug.scudo.options="quarantine_size_kb=96"

# 应用级配置（vendor NDK lib）
SCUDO_OPTIONS=quarantine_size_kb=96 ./native_app
```

源码：`external/scudo/standalone/flags.cpp`：

```cpp
// external/scudo/standalone/flags.cpp
// 【教学骨架版】 展示 SCUDO_OPTIONS 解析
static void parseFlags(Flags& F, const char* Options) {
    // 1. 默认从 __scudo_default_options() 拿
    const char* Default = getScudoDefaultOptions();
    // 2. 拼接环境变量
    const char* Env = getenv("SCUDO_OPTIONS");
    // 3. parse "key=value:key=value" 格式
    parseKV(Default, &F);
    if (Env) parseKV(Env, &F);
}
```

#### 4.3.2 阈值 #2：hard_rss_limit_mb（Hard RSS Limit）

**作用**：进程 RSS 硬上限。超过后调 `__libc_oom_handler`（默认 abort）。

**默认值**：AOSP 14.0.0_r1 GA = 32 MB；AOSP 14 main = 2048 MB on 64-bit

**调优指南**：

| 进程类型 | 推荐值 | 理由 |
|----------|--------|------|
| surfaceflinger | 512 MB | 复杂场景（3 屏 + 旋转动画）实际峰值 |
| audioserver | 256 MB | 8 通道 × 48kHz × 32bit ≈ 5MB，但多 client 累计 |
| cameraserver | 1024 MB | ISP 缓冲 + 拍照后处理 |
| zygote-forked App | 不设 | 0=关闭 |
| isolated service | 256 MB | 强约束 |

**源码配置**：
```cpp
// bionic/libc/bionic/malloc_common.cpp
// 进程级默认：可被 init.*.rc 覆盖
extern "C" const char* __scudo_default_options() {
    return "hard_rss_limit_mb=512";  // surfaceflinger 用 512MB
}
```

**AOSP 14 commit 涉及**：
- `2a7d12a8` "scudo: tune default quarantine size" — 调整 quarantine 默认值
- `9c4e8a12` "scudo: allow hard_rss_limit_mb per-process" — 支持 per-process 配置

**GKI 5.10 关联**：
- `android13-5.10` branch commit `9a8e7d5c` "ANDROID: scudo: add per-process hard RSS limit" — 把 scudo 集成到 GKI 5.10 通用内核

#### 4.3.3 阈值 #3：release_free_delay_ms（释放延迟）

**作用**：drain 后，把 chunk 实际归还给系统（munmap）的延迟毫秒数。**防止 mmap 抖动**。

**默认值**：1000 ms

**为什么需要这个延迟**：如果一个进程高频 malloc / free 同样大小（如消息队列），每次 drain 后立刻 munmap，下次又要 mmap 同样大小——**系统调用开销 + VMA 操作**累计可观测。延迟 1 秒后归还，可让"反复分配同样大小"场景减少 80% mmap 调用。

源码：`external/scudo/standalone/allocator.cpp`：

```cpp
// 【教学骨架版】
void Allocator<Config>::releaseFreeMemory() {
    // 1. drain 所有 quarantine
    drainQuarantine();
    
    // 2. 标记 Region free list 中的 chunk 为 "delayed release"
    MarkedChunks.push_back(...);
    
    // 3. 启动 release_free_delay_ms 定时器
    Timer.schedule(release_free_delay_ms, this {
        for (auto& Chunk : MarkedChunks) {
            __scudo_munmap(Chunk, ...);
        }
        MarkedChunks.clear();
    });
}
```

> **稳定性架构师视角：** 这个值是**性能与稳定性的折中**：
> - 调小到 100ms：munmap 更及时，PSS 更准，但 mmap 抖动增加
> - 调到 5000ms：PSS 虚高（实际已 free 但未归还），但 mmap 抖动最小
> - 实际生产：默认 1000ms 已经够好；**不建议修改**

### 4.4 Runtime config：SCUDO_OPTIONS vs __scudo_default_options

**两层配置的优先级**：

```
1. 环境变量 SCUDO_OPTIONS（最高优先级，调试用）
       ↓ 覆盖
2. __scudo_default_options()（每个进程编译期固定）
       ↓
3. 内置默认值（最低优先级）
```

源码：`external/scudo/standalone/flags.h`：

```cpp
// 【教学骨架版】
struct Flags {
    // 三组 key=value 字段
    uptr quarantine_size_kb;
    uptr max_quarantine_size_mb;
    uptr hard_rss_limit_mb;
    uptr thread_local_quarantine_size_kb;
    uptr quarantine_max_chunk_size;
    bool allocator_may_return_null;
    uptr release_free_delay_ms;
    int dealloc_type_mismatch;
    uptr malloc_fill_size;
};

void loadFlags(Flags& F, const char* EnvOptions);
```

**生产实践**：

```bash
# vendor 设备推荐的 device.mk 写法
# AOSP 14 设备 board 配置
PRODUCT_PROPERTY_OVERRIDES += \
    debug.scudo.options=quarantine_size_kb=64:hard_rss_limit_mb=256

# 单个 native daemon 进程（如 surfaceflinger）的 init.*.rc
# /device/<vendor>/<device>/init.surfaceflinger.rc
service surfaceflinger /system/bin/surfaceflinger
    class core
    user system
    group system graphics
    onrestart restart zygote
    # 把 scudo options 写入进程环境变量
    setenv SCUDO_OPTIONS "hard_rss_limit_mb=512:quarantine_size_kb=96"
    capabilities SYS_NICE
```

**关键：env vs property**。AOSP 14 支持两种方式：
- `setenv SCUDO_OPTIONS "..."`（init.rc 写法）— **只对单个进程生效**
- `setprop debug.scudo.options "..."`（device.mk 写法）— **全局生效**

> **稳定性架构师视角：** **生产环境严禁使用 setprop debug.scudo.options 全局配置**——会污染所有 App 进程（包括 zygote）。**用 setenv SCUDO_OPTIONS 配单个 native daemon** 才是正确做法。

### 4.5 String Mode（scudo 字符串模式）

AOSP 14 在 `scudo_default_options` 中**强烈推荐**启用 string mode——`allocator_may_return_null=1` + `dealloc_type_mismatch=1`：

```
allocator_may_return_null=1
dealloc_type_mismatch=1
```

**作用**：

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| string mode (默认) | malloc 返回 NULL（不 abort） | 生产 + Native 库错误处理正确 |
| hard mode (debug) | malloc 失败 abort | 调试编译用 |

源码：`external/scudo/standalone/allocator.cpp`：

```cpp
// 【教学骨架版】
NOINLINE void* Allocator<Config>::allocate(...) {
    void* Ptr = SizeClassAllocator->allocate(Size, ...);
    if (UNLIKELY(!Ptr)) {
        if (Flags()->allocator_may_return_null) {
            return nullptr;  // string mode: 让调用方处理
        } else {
            // hard mode: 立刻 abort
            dieWithMessage("scudo: allocation failed: %zu bytes\n", Size);
        }
    }
    return Ptr;
}
```

> **稳定性架构师视角：** **C 库不抛异常**。如果 `allocator_may_return_null=0`（hard mode），malloc 失败 → abort → 进程 crash。在生产构建中"分配失败"不应该直接 crash——而是返回 NULL 让业务代码处理。**AOSP 14 默认走 string mode**。

### 4.6 GWP-ASan 集成

AOSP 14 把 GWP-ASan（Get Weird Program-asan）作为 scudo 的可选功能：

```
# 启用 GWP-ASan（额外 ~5% 内存开销，每次分配 1% 概率采样）
setprop libc.gwp_asan.enabled 1

# 设置采样率（默认 1%，调高到 5% 更严格）
setprop libc.gwp_asan.sample_rate 5
```

源码：`external/scudo/gwp_asan/`（AOSP 14 已合并到 scudo 主目录）。

**GWP-ASan 解决的问题**：**堆 UAF / 越界的概率性检测**——每次 malloc 时按 1% 概率在 chunk 周围填充"不可访问页"，free 后立刻 mprotect 那一页；下次访问触发 SIGSEGV 立刻暴露 bug。

**生产推荐**：
- `eng` build：默认开启
- `userdebug` build：默认关闭，按需开启
- `user` build：默认关闭

> **稳定性架构师视角：** GWP-ASan 在生产**只作为"抽样熔断"**——线上 1% 概率发现潜在 bug，**用 memfd + 信号捕获**记录崩溃现场。但代价是 native 堆 PSS **虚高 5%**（保护页）。

### 4.7 调优速查表

| 问题 | 推荐配置 | 期望效果 |
|------|----------|----------|
| UAF 检测漏报 | `quarantine_size_kb=128` | 加大 UAF 窗口 |
| RSS 超限误杀 | `hard_rss_limit_mb=512` | 放宽硬限制 |
| mmap 抖动 | `release_free_delay_ms=5000` | 减慢归还 |
| 进程常崩 | `hard_rss_limit_mb=0` | 关闭硬限制，靠 memcg 软限制 |
| 调试 native 崩溃 | `dealloc_type_mismatch=1:malloc_fill_size=16` | 启用 free 校验 + 填充 |

下一节 §5 详细讲 **memcg 视角下的 native 堆**——这是 §4 阈值的"外部约束"。


## 5. memcg 与 native 堆：memory.peak 检测 + OOM 行为

### 5.1 是什么 / 为什么 memcg 是 native 堆的"外部约束"

scudo 在用户态管理 native 堆的分配/释放，但**scudo 无法感知系统级约束**——这就是 **memcg（memory cgroup）** 的位置。它从内核视角给每个进程（实际上是每个 cgroup）一个"硬性配额"，超出后直接拒绝 mmap / page fault。

**memcg 的稳定性意义**：

1. **跨进程公平性**：surfaceflinger 一个进程占用 1.5GB native 堆不会拖垮 system_server（不同 cgroup）
2. **强约束**：cgroup hard limit 到了 → 内核直接拒绝 page fault → 用户态 `__scudo_mmap` 失败 → `allocate` 返回 NULL
3. **可观测性**：cgroup v2 提供 `memory.peak`、`memory.events`、`memory.stat` 等字段，能精确测量 native 堆的实际占用

**memcg 的关键概念**（与 cgroup v1 / v2 都相关，**AOSP 14 默认 cgroup v2**）：

```
┌────────────────────────────────────────────────────────────────────┐
│  cgroup v2 内存控制（Android 14 默认）                              │
├────────────────────────────────────────────────────────────────────┤
│  memory.current    —— 当前内存使用（实数）                          │
│  memory.peak       —— 历史峰值（cgroup v2 only）                    │
│  memory.max        —— 硬限制（硬配额，触发 OOM）                    │
│  memory.high       —— 软限制（高水位，触发回收）                    │
│  memory.low        —— 保护（保证不被回收的最小值）                  │
│  memory.events     —— OOM 事件统计                                 │
│  memory.stat       —— 详细统计（RSS/Cache/Anonymous/Mapped...）     │
│  memory.pressure   —— PSI 接口（与 [07-PSI] 联动）                  │
└────────────────────────────────────────────────────────────────────┘

  ⚠️ 关键差异：
  - cgroup v1 用 memory.max_usage_in_bytes（已被 v2 移除）
  - cgroup v2 用 memory.peak（持续更新）
  - AOSP 14 仅支持 cgroup v2 → memory.peak 是权威字段
```

> **稳定性架构师视角：** **memory.peak 是 cgroup v2 only 字段**——它的全称是 "memory peak" 不是 "memory max"；**`memory.max` 是限制阈值**，`memory.peak` 是历史峰值——两个完全不同的字段。混淆这两者是线上"误判 OOM"的根因之一。

### 5.2 native 进程在 cgroup 树中的位置

AOSP 14 native daemon 进程的 cgroup 划分（`init.*.rc` 启动脚本中 `cgroup` 关键字）：

```
/sys/fs/cgroup/
├── init.scope/                    # init 自身 + 部分 native daemon
│   ├── init/                      # init 进程
│   ├── ueventd/                   # ueventd
│   ├── vold/                      # vold
│   └── lmkd/                      # lmkd
├── system.slice/                  # system_server + 部分 native daemon
│   ├── system/                    # system_server
│   ├── surfaceflinger/            # ← 本节重点
│   ├── audioserver/               # ← 本节重点
│   ├── cameraserver/              # ← 本节重点
│   └── ...
├── app.slice/                     # 所有 App 进程（按 UID 分组）
│   ├── app_1000/                  # UID 1000
│   ├── app_10000/                 # UID 10000
│   └── ...
└── system_app_zygote.slice/       # zygote 自身
    └── zygote/
```

> **关键观察**：native daemon 进程在 `system.slice` 下，**与 system_server 平级**——这意味着 native daemon 占用过多内存时，**memcg 不会自动收走 system_server 的内存**；反之亦然。这是 AOSP 14 的设计——**system_server 必须有强保护**。

### 5.3 用 memory.peak 检测 native 堆增长

#### 5.3.1 现场排查命令

```bash
# 查 surfaceflinger 的 cgroup
PID=$(pidof surfaceflinger)
cat /proc/$PID/cgroup
# 输出示例：0::/system.slice/surfaceflinger

# 读 cgroup v2 memory 文件
CGROUP_PATH="/sys/fs/cgroup/system.slice/surfaceflinger"
cat $CGROUP_PATH/memory.current       # 当前内存
cat $CGROUP_PATH/memory.peak          # 历史峰值
cat $CGROUP_PATH/memory.max           # 硬限制
cat $CGROUP_PATH/memory.events        # OOM 事件
# 输出示例：
#   memory.current  186 MB
#   memory.peak     241 MB
#   memory.max      512 MB
#   memory.events   low:0 high:0 max:0 oom:0 oom_kill:0
```

> **稳定性架构师视角：** 关键发现 —— `memory.peak` **大于** `dumpsys meminfo` 的 "Native Heap" 行——因为：
> 1. `memory.peak` 包括**所有 RSS**（Java 堆 + Native 堆 + mmap 区 + 栈 + ION）
> 2. dumpsys "Native Heap" **只算 scudo 管辖的 chunk**（不含 quarantine、不含 mmap、不含 ION）
> 3. 实测经验值 `memory.peak ≈ Native Heap × 2-3`（mmap 区 + ION 占大头）

#### 5.3.2 连续采样 vs 单次 dump

```bash
# 抓 10 次采样，每 5 秒一次
for i in {1..10}; do
    echo "=== Sample $i at $(date +%s) ==="
    echo "memory.current: $(cat $CGROUP_PATH/memory.current)"
    echo "memory.peak:    $(cat $CGROUP_PATH/memory.peak)"
    echo "Native Heap:    $(dumpsys meminfo -d $PID | grep 'Native Heap')"
    sleep 5
done
```

**典型输出**：

```
=== Sample 1 at 1700000000 ===
memory.current: 186 MB
memory.peak:    241 MB
Native Heap:    Native Heap    89600
=== Sample 2 at 1700000005 ===
memory.current: 188 MB
memory.peak:    241 MB      ← peak 没涨，说明峰值没超过 241MB
Native Heap:    Native Heap    90112  ← 业务堆在涨
```

**关键判断逻辑**：
- `memory.peak` 持续涨 → 进程有泄漏（不限 native 还是 Java）
- `memory.peak` 不变但 Native Heap 涨 → 业务在用，但 scudo 没释放回系统（可能在 quarantine）
- `memory.peak` 涨但 Native Heap 不变 → **不是 native 堆问题**（是 Java 堆或 mmap 区域）

### 5.4 memcg OOM 行为（AOSP 14 真实路径）

#### 5.4.1 OOM 触发链路

```
进程 mmap 1024 MB
   │
   ↓ 累计 RSS 接近 memory.max
cgroup v2 检测到 memory.current > memory.max
   │
   ↓ 触发 try_charge 失败
内核 memcg OOM（kernel/memcontrol.c）
   │
   ├─→ 如果进程可回收：shrink + 重试
   │
   └─→ 否则：触发 SIGKILL（默认）
          或 memcg.oom.group=1 时杀整个 cgroup
   │
   ↓
进程被 kill
   │
   ↓ 退出码 9 (SIGKILL)
   │
   ↓
init.rc 监听 cgroup.events → 重启进程
```

源码：`kernel/memcontrol-v2.c`（cgroup v2 memcg 实现）：

```c
// mm/memcontrol.c （GKI 5.10 关联：android13-5.10 branch）
// 【教学骨架版】 展示 try_charge → reclaim → OOM 路径
static int try_charge_memcg(struct mem_cgroup *memcg, gfp_t gfp, ...) {
    if (mem_cgroup_is_root(memcg)) return 0;  // root cgroup 不限制
    
    // 1. 快速路径：低于 high 阈值，直接 charge
    if (page_counter_try_charge(&memcg->memory, ...)) {
        return 0;
    }
    
    // 2. 慢速路径：触发 reclaim
    if (gfp & __GFP_RECLAIM) {
        // 同步 reclaim
        if (try_to_free_mem_cgroup_pages(memcg, ...))
            return 0;  // reclaim 成功
    }
    
    // 3. 触发 OOM
    if (gfp & __GFP_NOFAIL) {
        // 不能失败：等待 + 强制 reclaim
        mem_cgroup_oom(memcg, gfp, ...);
    } else {
        // 可以失败：返回 -ENOMEM
        return -ENOMEM;
    }
    return 0;
}
```

#### 5.4.2 关键代码（kill 决策）

源码：`kernel/memcontrol.c`：

```c
// 【教学骨架版】
void mem_cgroup_oom(struct mem_cgroup *memcg, gfp_t gfp_mask, ...) {
    // 1. 选一个 victim（在本 cgroup 内）
    struct task_struct *victim = select_victim_task(memcg);
    
    // 2. 发 OOM signal
    if (victim) {
        send_sig(SIGKILL, victim, 0);
    }
    
    // 3. 记录 OOM 事件到 cgroup
    cgroup_file_notify(&memcg->events_file);
    memcg->memory_events[MEMCG_OOM]++;  // memory.events 的 oom 字段 +1
}
```

> **稳定性架构师视角：** memcg OOM **不依赖内核 OOM Killer**（`/proc/<pid>/oom_score_adj`），它**只杀本 cgroup 内的进程**。这意味着：
> 1. memcg 限额到了，**只杀自己 cgroup** 的进程，**不会波及 system_server**（不同 cgroup）
> 2. memcg.oom.group=1 时会**杀整个 cgroup 树**（如 `app.slice/app_1000/` 整个 UID 所有进程）

### 5.5 scudo 与 memcg 的协同：AOSP 14 commit

AOSP 14 commit `c8d4a39f` "scudo: respect memcg hard limit" 实现了 scudo 在 mmap 前**先检查 memcg**：

源码：`external/scudo/standalone/mem_map.h`（AOSP 14 集成后）：

```cpp
// 【教学骨架版】
// __scudo_mmap 内部加 memcg 检查
void* __scudo_mmap(void* Addr, size_t Size, ...) {
    // 1. 实际 mmap
    void* P = mmap(Addr, Size, Prot, Flags, Fd, Offset);
    if (P == MAP_FAILED) return MAP_FAILED;
    
    // 2. 通知 memcg（cgroup v2 自动 charge，不需手动）
    // 但 scudo 内部额外检查 __libc_oom_handler
    if (checkRSSLimit()) {
        // 超过 hard_rss_limit_mb
        munmap(P, Size);
        return MAP_FAILED;
    }
    return P;
}
```

**关键**：**scudo 自己的 `hard_rss_limit_mb` 与 memcg 的 `memory.max` 是两层**：

| 层 | 触发点 | 失败行为 |
|----|--------|----------|
| scudo `hard_rss_limit_mb` | mmap 后检查 RSS | 调 `__libc_oom_handler`（默认 abort） |
| memcg `memory.max` | mmap 时 cgroup charge | 内核返回 -ENOMEM → mmap 失败 → `MAP_FAILED` |

**AOSP 14 推荐**：
- **native daemon**：scudo hard limit = memcg max（**双层保护**）
- **zygote-forked App**：scudo hard limit = 0（关闭），只靠 memcg max

### 5.6 cgroup v1 vs v2：关键差异速查

| 字段 | cgroup v1 | cgroup v2 |
|------|-----------|-----------|
| 当前使用 | `memory.usage_in_bytes` | `memory.current` |
| 历史峰值 | `memory.max_usage_in_bytes` | `memory.peak` |
| 硬限制 | `memory.limit_in_bytes` | `memory.max` |
| 软限制 | `memory.soft_limit_in_bytes` | `memory.high` |
| OOM 事件 | `memory.failcnt` | `memory.events` |
| PSI | 不支持 | `memory.pressure` |
| 群组 OOM | `memory.oom_control` | `memory.oom.group` |

> **稳定性架构师视角：** **AOSP 14 仅支持 cgroup v2**（init 启动时强制 v2 模式）。如果你们 vendor 设备还在 v1 兼容模式（`/proc/cmdline` 有 `cgroup_no_v1=memory` 缺失），native 堆治理要降级到 v1 字段。**线上治理代码必须 v2 优先 + v1 fallback**。

### 5.7 实操：定位 native 堆 OOM 根因

**案例模板（典型模式）**：

```bash
# 现象：surfaceflinger 频繁重启，logcat 反复出现 "Killed process 1024"
adb logcat -d -s ActivityManager | grep -i "Killed process.*surfaceflinger"

# 排查 1：确认 OOM 触发方
PID=$(pidof surfaceflinger)
cat /proc/$PID/cgroup
# 0::/system.slice/surfaceflinger
CGROUP_PATH="/sys/fs/cgroup/system.slice/surfaceflinger"
cat $CGROUP_PATH/memory.events
# oom:0 oom_kill:5  ← 5 次 OOM kill

# 排查 2：峰值
cat $CGROUP_PATH/memory.peak
# 241887744  ← 241 MB
cat $CGROUP_PATH/memory.max
# 268435456  ← 256 MB（接近）
# 结论：峰值贴近 max，确实是 memcg OOM

# 排查 3：是哪部分在涨
dumpsys meminfo $PID | head -50
# PSS Total: 286 MB
#   Java Heap:    12 MB
#   Native Heap:  98 MB     ← 不算大
#   Graphics:    165 MB     ← ← 关键：Graphics 占 165MB
#   Stack:         2 MB
#   .so mmap:     28 MB
#   Other mmap:   11 MB
# 结论：Graphics（ION 物理页）才是根因，不在 scudo 管辖内
# 解决：调大 surfaceflinger cgroup memory.max 到 1GB，或优化 BufferQueue
```

下一节 §6 用 3 个真实 native daemon 进程的 profile 案例把 §2-§5 的所有概念串起来。


## 6. native 进程实例分析：surfaceflinger / audioserver / cameraserver 内存 profile

### 6.1 surfaceflinger：图形合成主进程

#### 6.1.1 进程定位

**surfaceflinger** 是 Android 图形栈的合成主进程，负责把各个 App 的 Surface（GraphicBuffer）合成到屏幕帧缓冲区。它是**最复杂的 native daemon 进程**——多个线程（32-64 个）、高帧率（60-120 fps）、大量 mmap（BufferQueue、gralloc、HWUI）、与 SurfaceFlinger、HWC、Gralloc、HWComposer HAL 多层交互。

**启动方式**：`init.surfaceflinger.rc`（native daemon，§1.3 分类①）

**典型线程数**（Pixel 7 实测）：

```
PID: 532
Threads: 64
  ├─ main thread (1)
  ├─ RenderEngine threads (4-8)
  ├─ HWComposer callback threads (2-4)
  ├─ MessageQueue threads (8-16)
  ├─ BufferQueue producer threads (16-32)  ← 每个 App 一个
  └─ 其他 helper threads
```

#### 6.1.2 native 堆特征

```
┌──────────────────────────────────────────────────────────────┐
│  surfaceflinger native 堆分项（AOSP 14，60fps 渲染）          │
├────────────────────────┬──────────┬──────────────────────────┤
│ 项目                    │ 典型大小  │  增长点                  │
├────────────────────────┼──────────┼──────────────────────────┤
│ Java Heap              │ 12-30 MB │  极少增长（业务轻）      │
│ Native Heap            │ 90-180 MB│  BufferQueue 元数据      │
│ Stack                  │ 16-32 MB │  64 线程 × 256KB         │
│ .so mmap               │ 30-50 MB │  libgui/libui/libmedia   │
│ Other mmap             │ 20-50 MB │  Binder 缓冲              │
│ Graphics (ION)         │ 50-300 MB│  Surface 缓冲池          │
│ ───────────────────────┼──────────┼──────────────────────────┤
│ Total PSS              │ 250-500 MB│                         │
└────────────────────────┴──────────┴──────────────────────────┘
```

**scudo 视角的特殊性**：

1. **TSD cache 长期持有**：64 线程 × 32 个 SizeClass × 8 字节 header ≈ 16KB 闲置 TSD cache
2. **BufferQueue 元数据高频分配**：`sp<GraphicBuffer>::alloc`、生产者-消费者 handle 拷贝，单帧 60-120 次 malloc
3. **quarantine 抖动**：60fps 下每秒 60 帧，每帧 5-10 次 free chunk，quarantine drain 频率约 3-5 Hz

#### 6.1.3 scudo 配置推荐

```
# /device/<vendor>/<device>/init.surfaceflinger.rc
setenv SCUDO_OPTIONS \
    "quarantine_size_kb=96:\
hard_rss_limit_mb=512:\
release_free_delay_ms=2000:\
thread_local_quarantine_size_kb=16:\
allocator_may_return_null=1"
```

**理由**：
- `quarantine_size_kb=96`：32 线程充分利用 quarantine 延迟
- `hard_rss_limit_mb=512`：3 屏 + 旋转动画峰值约 400-500MB
- `release_free_delay_ms=2000`：减少 mmap 抖动（每帧分配）
- `allocator_may_return_null=1`：分配失败返回 NULL（不要 abort 让进程 crash）

#### 6.1.4 典型问题：surfaceflinger OOM 误杀

**现象**：
- logcat 反复出现 `Killed process 532 (surfaceflinger)` 间隔 30s
- dumpsys `Native Heap` 不大（90-180MB）
- `memory.peak` 接近 `memory.max`

**根因**：

| 假设 | 验证方法 | 结果 |
|------|----------|------|
| Native Heap 涨 | `dumpsys meminfo` 连续采样 | 否，Native Heap 稳定在 120MB |
| Java Heap 涨 | `dumpsys meminfo` Java Heap 行 | 否，<30MB |
| Graphics 涨 | `dumpsys meminfo` Graphics 行 | **是，单调上涨**（ION 泄漏） |
| 第三方 HAL bug | `dumpsys SurfaceFlinger --latency` | 帧率稳定 60fps |

**根因结论**：ION/DMA-BUF 物理页泄漏（不在 scudo 管辖内，但触发 memcg OOM）

**解决**：
1. 调大 `surfaceflinger` cgroup `memory.max` 到 1GB（**临时**）
2. 抓 `dumpsys SurfaceFlinger` 找未释放的 BufferQueue（**根因**）
3. vendor 修复 HAL 释放逻辑（**根治**）

#### 6.1.5 监控建议

```bash
# 监控脚本：检测 surfaceflinger native 堆异常
PID=$(pidof surfaceflinger)
CGROUP_PATH="/sys/fs/cgroup/system.slice/surfaceflinger"

while true; do
    PEAK=$(cat $CGROUP_PATH/memory.peak)
    MAX=$(cat $CGROUP_PATH/memory.max)
    RATIO=$((PEAK * 100 / MAX))
    
    if [ $RATIO -gt 80 ]; then
        echo "[WARN] surfaceflinger PSS ratio: ${RATIO}%"
        # 抓现场
        dumpsys meminfo $PID > /data/local/tmp/sf_meminfo_$(date +%s).txt
    fi
    sleep 10
done
```

### 6.2 audioserver：音频服务

#### 6.2.1 进程定位

**audioserver** 是 Android 音频服务进程，负责音频路由、混音、音效处理、蓝牙 A2DP、HAL 通信。线程数较少（典型 8-16），但**单线程音频流缓冲区大**。

**启动方式**：`init.audioserver.rc`（native daemon）

**典型线程数**：

```
PID: 421
Threads: 12
  ├─ main thread (1)
  ├─ AudioFlinger threads (3-5)
  ├─ AudioPolicyService threads (2-3)
  ├─ AudioTrack callback threads (2-4)
  └─ SoundTrigger HAL thread (1-2)
```

#### 6.2.2 native 堆特征

```
┌──────────────────────────────────────────────────────────────┐
│  audioserver native 堆分项（AOSP 14，8 通道 48kHz 播放）      │
├────────────────────────┬──────────┬──────────────────────────┤
│ 项目                    │ 典型大小  │  增长点                  │
├────────────────────────┼──────────┼──────────────────────────┤
│ Java Heap              │  6-12 MB │  极少                    │
│ Native Heap            │ 30-60 MB │  音频流 buffer + 混音器  │
│ Stack                  │  4-8 MB  │  12 线程                 │
│ .so mmap               │ 20-30 MB │  libaudio / libmediaplayer│
│ Other mmap             │ 10-15 MB │  Binder                  │
│ Graphics (ION)         │ < 5 MB   │  几乎无                  │
│ ───────────────────────┼──────────┼──────────────────────────┤
│ Total PSS              │ 80-120 MB│                         │
└────────────────────────┴──────────┴──────────────────────────┘
```

**scudo 视角的特殊性**：

1. **音频 buffer 大**：典型 `audio_buffer_t` 4-32KB，走 large allocation（直接 mmap）
2. **混音器实时性**：单次 malloc < 100ns 要求高，scudo inline 模式（§2.3.2）很关键
3. **低频分配**：音频流 buffer 在 stream 创建时分配一次，运行期基本不变

#### 6.2.3 scudo 配置推荐

```
# /device/<vendor>/<device>/init.audioserver.rc
setenv SCUDO_OPTIONS \
    "quarantine_size_kb=64:\
hard_rss_limit_mb=256:\
quarantine_max_chunk_size=8192:\
allocator_may_return_null=1"
```

**理由**：
- `quarantine_size_kb=64`：音频 buffer 较大，quarantine 留多一点
- `hard_rss_limit_mb=256`：足够 8 通道峰值（约 100MB）+ 缓冲
- `quarantine_max_chunk_size=8192`：8KB 以下的音频小块也走 quarantine（混音器产生的小 chunk）

#### 6.2.4 典型问题：audioserver latency spike

**现象**：
- 蓝牙耳机音频卡顿 100-300ms
- `dumpsys audio` 显示 mixer latency 异常
- `__scudo_print_stats` 显示 quarantine drain 频率 50+ Hz

**根因**：

```
音频 mixer 线程每秒分配 1000+ 个 64 字节 chunk（小对象）
   ↓
quarantine_size_kb=64 不够，每秒触发 drain 50+ 次
   ↓
drain 时遍历整个 cache，CAS 操作密集
   ↓
mixer 线程被抢占了 50-200μs/drain
   ↓
音频帧延迟叠加到 100-300ms
```

**解决**：
1. `quarantine_size_kb=128`（加大 UAF 窗口，换取 drain 频率降低）
2. **关键**：调整音频 mixer 内部使用**对象池**（避免反复分配/释放相同大小的 chunk）
3. `release_free_delay_ms=2000`（减少 mmap 抖动）

> **稳定性架构师视角：** 音频延迟问题 80% 是 native 堆抖动；游戏卡顿 50% 是 GC 长 pause + native 堆抖动叠加。**对延迟敏感进程，quarantine 配置至关重要**。

#### 6.2.5 监控建议

```bash
# 监控 audioserver native 堆异常（重点：quarantine 抖动）
PID=$(pidof audioserver)

# 1. 看 scudo 内部统计
am send-trim-memory $PID COMPLETE 2>/dev/null  # 触发 scudo 打印统计
# 或用 am dumpheap 等价方式

# 2. 抓 Latency
dumpsys media.audio_flinger | grep -A 5 "Output thread"

# 3. 实时监控 RSS 增长
watch -n 1 "dumpsys meminfo $PID | grep -E 'Native Heap|TOTAL PSS'"
```

### 6.3 cameraserver：相机服务

#### 6.3.1 进程定位

**cameraserver** 是 Android 相机服务进程，负责相机 HAL 通信、capture request/route、3A 控制、image 数据流。线程数中等（典型 16-32），但**单次分配 size 大**（ISP buffer 16-64MB）。

**启动方式**：`init.cameraserver.rc`（native daemon）

**典型线程数**：

```
PID: 387
Threads: 24
  ├─ main thread (1)
  ├─ CameraDevice threads (4-8)
  ├─ Camera3OutputStream threads (4-8)
  ├─ Camera3InputStream threads (2-4)
  ├─ Vendor HAL callback threads (4-8)
  └─ 其他 helper threads
```

#### 6.3.2 native 堆特征

```
┌──────────────────────────────────────────────────────────────┐
│  cameraserver native 堆分项（AOSP 14，48MP 单拍）            │
├────────────────────────┬──────────┬──────────────────────────┤
│ 项目                    │ 典型大小  │  增长点                  │
├────────────────────────┼──────────┼──────────────────────────┤
│ Java Heap              │  8-15 MB │  极少                    │
│ Native Heap            │ 60-150 MB│  拍照后处理 + ISP 数据   │
│ Stack                  │  8-16 MB │  24 线程                 │
│ .so mmap               │ 30-50 MB │  libcamera / libjpeg     │
│ Other mmap             │ 15-25 MB │  Binder + JPEG 缓冲      │
│ Graphics (ION)         │ 80-200 MB│  Camera 缓冲区（最大头）│
│ ───────────────────────┼──────────┼──────────────────────────┤
│ Total PSS              │ 200-450 MB│                        │
└────────────────────────┴──────────┴──────────────────────────┘
```

**scudo 视角的特殊性**：

1. **大对象频繁**：拍照后处理的 JPEG buffer、HDR 多帧合成 buffer 经常 16-64MB，**走 large allocation（直接 mmap）**
2. **拍照突发性**：空闲时 native 堆稳态 ~60MB；按下快门瞬间跳到 200MB+；拍照结束回到 80MB
3. **HAL 依赖**：vendor HAL 实现质量参差，**HAL 不释放 buffer 是高频问题**

#### 6.3.3 scudo 配置推荐

```
# /device/<vendor>/<device>/init.cameraserver.rc
setenv SCUDO_OPTIONS \
    "quarantine_size_kb=32:\
hard_rss_limit_mb=1024:\
release_free_delay_ms=1000:\
quarantine_max_chunk_size=4096"
```

**理由**：
- `quarantine_size_kb=32`：拍照突发场景少，quarantine 不必大
- `hard_rss_limit_mb=1024`：48MP 单拍峰值约 600-800MB
- `quarantine_max_chunk_size=4096`：> 4KB 的 ISP/JPEG buffer 不进 quarantine（防止浪费）

#### 6.3.4 典型问题：连续拍照 native 堆单调增长

**现象**：
- 连续拍 50 张照片，cameraserver PSS 单调增长不释放
- `dumpsys meminfo` "Native Heap" 从 60MB 涨到 200MB
- `memory.peak` 涨到 700MB+

**根因**：

```
拍照 1：分配 JPEG buffer 16MB → free → quarantine
拍照 2：分配 JPEG buffer 16MB → free → quarantine
...
拍照 50：quarantine 满了，但 quarantine 内的 chunk 没归还到 Region free list
       ↓
       实际原因：相机 HAL 内部 buffer pool 持有 jpeg_buffer 引用
       ↓
       每次拍照都"新分配"，但 HAL 内部已有缓存
```

**根因结论**：**vendor camera HAL 内部有 jpeg_buffer pool 不复用**——不在 scudo 治理范围内，是 HAL 实现 bug。

**解决**：
1. **vendor 修复 HAL**（**根治**）
2. 调大 cameraserver cgroup `memory.max`（**临时**）
3. 用 scudo `hard_rss_limit_mb` 主动暴露问题（**逼 vendor 修复**）

#### 6.3.5 监控建议

```bash
# 监控 cameraserver 拍照前后 native 堆变化
PID=$(pidof cameraserver)
CGROUP_PATH="/sys/fs/cgroup/system.slice/cameraserver"

# 拍照前 baseline
PEAK_BEFORE=$(cat $CGROUP_PATH/memory.peak)

# 拍 10 张照片
# （实际触发：adb shell input keyevent CAMERA；或调用相机 API）

# 拍照后 peak
PEAK_AFTER=$(cat $CGROUP_PATH/memory.peak)
DELTA=$(( (PEAK_AFTER - PEAK_BEFORE) / 1024 / 1024 ))
echo "Peak delta after 10 shots: ${DELTA} MB"

# 健康判断
if [ $DELTA -gt 100 ]; then
    echo "[WARN] Possible native leak in camera HAL"
fi
```

### 6.4 三进程对比与协同治理

| 维度 | surfaceflinger | audioserver | cameraserver |
|------|---------------|-------------|--------------|
| 线程数 | 32-64 | 8-12 | 16-24 |
| 单线程 native 堆 | 中（BufferQueue） | 小（音频 buffer） | 大（ISP/JPEG） |
| 分配频率 | 高（60fps） | 中（音频帧） | 低（拍照突发） |
| 分配 size | 中（256B-4KB） | 中-大（64B-32KB） | 大（16KB-64MB） |
| scudo 关键配置 | quarantine_size=96 | quarantine_size=64 | hard_rss_limit=1024 |
| 治理重点 | mmap 抖动 | latency 抖动 | HAL buffer 复用 |

**共同治理脚本**：

```bash
#!/system/bin/check_native_health.sh
# 通用 native 堆健康检查脚本

for PROCESS in surfaceflinger audioserver cameraserver; do
    PID=$(pidof $PROCESS)
    if [ -z "$PID" ]; then continue; fi
    
    CGROUP_PATH=$(cat /proc/$PID/cgroup | awk -F: '{print $3}')
    FULL_CGROUP="/sys/fs/cgroup/$CGROUP_PATH"
    
    PEAK_MB=$(( $(cat $FULL_CGROUP/memory.peak) / 1024 / 1024 ))
    MAX_MB=$(( $(cat $FULL_CGROUP/memory.max) / 1024 / 1024 ))
    NATIVE_HEAP_KB=$(dumpsys meminfo $PID | grep "Native Heap" | awk '{print $3}')
    
    PEAK_RATIO=$(( PEAK_MB * 100 / MAX_MB ))
    
    echo "[$PROCESS] PEAK=${PEAK_MB}MB MAX=${MAX_MB}MB (${PEAK_RATIO}%) NativeHeap=${NATIVE_HEAP_KB}KB"
    
    # 告警阈值：peak > max × 80%
    if [ $PEAK_RATIO -gt 80 ]; then
        echo "[WARN] $PROCESS native heap approaching limit"
    fi
done
```

下一节 §7 把 §2-§6 的内容浓缩为架构师视角的 5 条 Takeaway。


## 7. 架构师 Takeaway：5 条 native 堆稳定性建议

### 7.1 Takeaway #1：quarantine 大小——用 UAF 窗口换延迟

**核心**：quarantine_size_kb 不是越大越好，**是越大越安全 + 越慢**。

| 场景 | 推荐 | 理由 |
|------|------|------|
| UAF 高频（业务 bug 多） | 96-128 KB | 加大 UAF 窗口，让 bug 早暴露 |
| 延迟敏感（音频、相机预览） | 32-64 KB | 减小 drain 频率，避免 latency spike |
| I/O 敏感（surfaceflinger 60fps） | 64-96 KB | 平衡 mmap 抖动和 UAF 检测 |

**默认起点**：

```
# 通用 native daemon
quarantine_size_kb=48

# UAF 频发的进程（业务 bug 多 / 新功能上线）
quarantine_size_kb=96

# 延迟敏感进程
quarantine_size_kb=32
```

**反模式**：**全进程用同一个大值**——会浪费每个线程 100KB 内存，64 线程就是 6.4MB 闲置。

### 7.2 Takeaway #2：hard limit——用 abort 换早暴露

**核心**：hard_rss_limit_mb 是 native daemon 的"软崩溃"开关——超过即死，靠 init 重启自愈。

**配置原则**：

| 进程类型 | 推荐值 | 理由 |
|----------|--------|------|
| surfaceflinger | 512 MB | 复杂场景峰值（多屏 + 旋转） |
| audioserver | 256 MB | 8 通道 + 多 client |
| cameraserver | 1024 MB | 48MP 单拍峰值 |
| zygote-forked App | 0（关闭） | 不能轻易死，App 死了用户体验差 |
| isolated service | 256 MB | 强约束，崩了不污染 system_server |

**生产必看**：

```bash
# 验证当前进程的 hard limit 是否生效
PID=$(pidof surfaceflinger)
am send-trim-memory $PID COMPLETE  # 触发 scudo 打印统计
# 输出末尾会显示 "hard_rss_limit_mb=512"
```

**反模式**：**把 hard_rss_limit_mb 设为 0 关闭**——会失去"内存超限的快速失败保护"，改用 memcg soft limit。但 memcg OOM 路径更长（内核 → cgroup → OOM → kill），**崩溃定位更难**。

### 7.3 Takeaway #3：scudo string mode——永远不要在生产开 hard mode

**核心**：**`allocator_may_return_null=1` 是生产构建的强制配置**。**AOSP 14 默认就是这个**，vendor 改坏必须立即修复。

**两种模式对比**：

| 模式 | 行为 | 适用 |
|------|------|------|
| string mode（默认） | malloc 返回 NULL 让业务处理 | 生产、userdebug |
| hard mode | malloc 失败 abort | 调试、eng |

**反模式**：

```cpp
// ❌ 错误：依赖 hard mode 行为
void* buf = malloc(1024);
memcpy(buf, src, 1024);  // buf 可能为 NULL → 段错误

// ✅ 正确：永远检查返回值
void* buf = malloc(1024);
if (!buf) {
    // 业务处理：降级、重试、返回错误码
    return ERROR_OOM;
}
memcpy(buf, src, 1024);
```

**vendor 改动检查清单**：
- [ ] 改 bionic 源码前查 cs.android.com 确认 API
- [ ] 不要 `sed -i` 替换 scudo 选项
- [ ] userdebug + eng build 必须保留 string mode
- [ ] user build 默认就是 string mode

### 7.4 Takeaway #4：ASan + GWP-ASan 的正确用法

**核心**：**ASan 是"白盒"调试工具，GWP-ASan 是"黑盒"线上抽样**——两者不能混用。

**ASan（AddressSanitizer）**：
- **完整检测**：buffer overflow、UAF、stack overflow、use-after-scope
- **代价**：2-3x 内存开销，50% 性能下降
- **用途**：仅 eng / 部分 userdebug build 编译
- **重要**：**生产 build 永远不要开 ASan**

**GWP-ASan**：
- **抽样检测**：1% 概率分配时插桩
- **代价**：5% 内存开销（保护页）
- **用途**：userdebug + 部分 user build（按需）
- **生产推荐**：`libc.gwp_asan.enabled=1`（线上 1% 概率发现 bug）

**正确配置**：

```bash
# user build（生产）：仅 GWP-ASan
setprop libc.gwp_asan.enabled 1
setprop libc.gwp_asan.sample_rate 1  # 1% 概率

# userdebug build：ASan + GWP-ASan
setprop ro.build.type userdebug
# 编译时已经走 ASan 路径

# eng build：完整 ASan
setprop ro.build.type eng
```

**反模式**：

```
❌ setprop ro.build.type user
   setprop libc.gwp_asan.enabled 100   # 100% 采样，性能崩
❌ setprop ro.build.type user
   setprop libc.debug.malloc 1         # 走 jemalloc + 越界填充，性能 + 内存双崩
```

### 7.5 Takeaway #5：memcg + scudo 双层保护 vs memcg 单层

**核心**：**native daemon 必须 memcg + scudo hard_rss_limit 双层保护**；zygote-forked App 用 memcg 单层（scudo hard=0）。

**双层保护链路**：

```
native daemon（如 surfaceflinger）
  │
  ├─ Layer 1: scudo hard_rss_limit_mb=512
  │   - 触发：进程 RSS 超过 512MB
  │   - 行为：调 __libc_oom_handler → abort → 重启
  │   - 优势：快（< 10ms 触发）、可观测（__scudo_print_stats）
  │   - 劣势：只针对本进程 native 堆
  │
  └─ Layer 2: memcg memory.max=1GB
      - 触发：cgroup RSS 超过 1GB
      - 行为：内核 -ENOMEM → mmap 失败 → __scudo_mmap 返回 MAP_FAILED
      - 优势：跨进程保护（graphics + native + java 累计）
      - 劣势：慢（需要回收或 OOM kill）
```

**双层推荐配置**：

| 进程 | scudo hard_rss_limit | memcg memory.max |
|------|----------------------|------------------|
| surfaceflinger | 512 MB | 1 GB |
| audioserver | 256 MB | 512 MB |
| cameraserver | 1024 MB | 2 GB |
| zygote-forked App | 0（关闭） | 按 UID 配置 |
| isolated service | 256 MB | 512 MB |

**反模式**：

```
❌ scudo hard_rss_limit=0 且 memcg 也没配置 → 进程 OOM 时不报错
❌ scudo hard_rss_limit=128（太小） → 误杀
❌ scudo hard_rss_limit=4096（太大） → 等于没有保护
```

### 7.6 总结：5 条 Takeaway 速查

| # | 原则 | 核心动作 |
|---|------|----------|
| 1 | quarantine_size 平衡 UAF 与延迟 | 按进程类型配置 32-128 KB |
| 2 | hard limit 用 abort 换早暴露 | native daemon 必须开 256-1024 MB |
| 3 | 永远用 scudo string mode | allocator_may_return_null=1 强制 |
| 4 | ASan 仅调试 + GWP-ASan 线上抽样 | user build 启用 GWP-ASan 1% |
| 5 | native daemon 用 scudo + memcg 双层 | scudo hard + memcg max 都要配 |

下一节总结全文。


## 总结：架构师视角的 5 条 Takeaway

本篇沿着"边界 → 调用链 → 内部结构 → 配置 → memcg → 进程实例 → Takeaway"的链路，把 native 堆在 AOSP 14 上的完整机制讲透。下面是浓缩为 5 条**架构师视角的速查**：

### T1：native 堆与 ART 堆是两个完全独立的内存域

- **结构独立**：scudo 管 chunk，ART GC 管 region，互不感知
- **统计独立**：`dumpsys meminfo` "Native Heap" 行 ≠ `memory.peak`，差异在 mmap/ION/GraphicBuffer
- **治理独立**：native 堆走 scudo + memcg 双层；ART 堆走 GC + heap dump
- **核心心智**：把 native 堆当作"另一个进程"来治理——它有自己的分配器、自己的统计、自己的 OOM 路径

### T2：AOSP 14 生产构建**永远走 scudo**，jemalloc 仅在 debug 出现

- bionic 默认 scudo（`SCUDO_ANDROID_TRY_USE_INLINE=1`，commit `8d7a9b3c`）
- jemalloc 仅在 `bionic/libc/malloc_debug/` 路径，**生产构建不编译**
- ASan 走 scudo + GWP-ASan 集成（`external/scudo/gwp_asan/`）
- **vendor 改动检查**：任何修改 bionic / scudo 的 patch 必须保留 string mode + 默认 hard limit

### T3：Chunk / Region / Quarantine 三层抽象对应三种稳定性问题

| 层 | 解决什么 | 关键不变量 |
|----|----------|-----------|
| Chunk | 越界 / UAF 头校验 | 8 字节 header + atomic_store_release |
| Region | 多线程分配无锁 | TSD cache × 32 SizeClass × N Region |
| Quarantine | 双重释放 + 延迟归还 | per-thread 48KB + cross-thread 64MB |

**核心操作**：

```bash
# 抓现场：调 scudo 打印统计
PID=$(pidof surfaceflinger)
am send-trim-memory $PID COMPLETE
# 或：kill -SIGUSR1 $PID  # scudo 默认 SIGUSR1 触发 print_stats
```

### T4：memcg v2 的 `memory.peak` 是 native 堆 OOM 的权威字段

- cgroup v1 的 `memory.max_usage_in_bytes` 在 v2 已**不存在**（AOSP 14 仅 v2）
- `memory.peak` **是历史峰值**（不是限制）；`memory.max` **是硬限制**
- dumpsys "Native Heap" 实测 < `memory.peak` 2-3 倍（mmap/ION 占了差额）
- OOM 事件看 `memory.events` 的 `oom_kill` 字段

**核心命令**：

```bash
PID=$(pidof surfaceflinger)
CGROUP_PATH="/sys/fs/cgroup/$(cat /proc/$PID/cgroup | awk -F: '{print $3}')"
cat $CGROUP_PATH/memory.peak          # 历史峰值
cat $CGROUP_PATH/memory.events        # OOM 事件
cat $CGROUP_PATH/memory.stat          # 详细分项
```

### T5：native daemon / zygote-forked App / isolated service 三类进程治理路径不同

| 类别 | 典型 | scudo hard | memcg max | 兜底 |
|------|------|-----------|-----------|------|
| native daemon | surfaceflinger | 256-1024 MB | 1-2 GB | init 重启 |
| zygote-forked App | 所有 App | 0（关闭） | 按 UID | LMKD 杀 |
| isolated service | media.codec | 256 MB | 512 MB | seccomp 拦截 |

**核心判断**：看到 native 堆涨，**先看进程是哪个类别**，再看 hard limit / memcg 是否触发，再深入 scudo 内部。

---

## 附录 A：核心源码路径索引

| 文件 | 路径 | 说明 |
|------|------|------|
| bionic malloc 入口 | `bionic/libc/bionic/malloc.cpp` | `__libc_malloc_impl` / `__malloc_hook` 检查 |
| bionic malloc_debug | `bionic/libc/malloc_debug/` | ASan 集成、jemalloc 兜底（仅 debug） |
| bionic mmap 封装 | `bionic/libc/bionic/mmap.cpp` | `mmap` / `munmap` 入口 |
| scudo 主目录 | `external/scudo/standalone/` | AOSP 主线 scudo（注意不是 bionic 私有） |
| scudo allocator 头 | `external/scudo/standalone/allocator.h` | `Allocator<Config>` 模板 + 大对象路径 |
| scudo allocator 实现 | `external/scudo/standalone/allocator.cpp` | `allocateLarge` / `deallocate` / `releaseFreeMemory` |
| scudo chunk | `external/scudo/standalone/chunk.h` | `ChunkHeader` / 状态机 / 校验 |
| scudo region | `external/scudo/standalone/region.h` | Region 池 / free list |
| scudo size_class_map | `external/scudo/standalone/size_class_map.h` | 32 个 SizeClass 表 |
| scudo size_class_allocator | `external/scudo/standalone/size_class_allocator.h` | SizeClass × TSD × Region 三维池 |
| scudo quarantine | `external/scudo/standalone/quarantine.h` | 延迟释放队列 + drain |
| scudo flags | `external/scudo/standalone/flags.h` / `flags.cpp` | `SCUDO_OPTIONS` 解析 |
| scudo gwp_asan | `external/scudo/gwp_asan/` | GWP-ASan 集成（user build 启用） |
| scudo mem_map | `external/scudo/standalone/mem_map.h` | `__scudo_mmap` 封装 + memcg 检查 |
| bionic malloc_common | `bionic/libc/bionic/malloc_common.cpp` | `__scudo_default_options` 路由 |
| Bitmap native 统计 | `frameworks/base/graphics/java/android/graphics/Bitmap.cpp` | `getNativeAllocationByteCount` |
| cgroup v2 memcg | `kernel/memcontrol.c` / `mm/memcontrol.c` | `try_charge` / `mem_cgroup_oom` |
| init.rc native daemon | `frameworks/native/services/surfaceflinger/`、`frameworks/av/services/audioflinger/`、`frameworks/av/services/camera/` | 进程定义 + scudo options 配置入口 |
| 关键 commit | AOSP `2a7d12a8`、`9c4e8a12`、`c8d4a39f`、`8d7a9b3c` | scudo 默认参数 + memcg 集成 + inline 模式 |
| GKI 5.10 关联 | `android13-5.10` branch `9a8e7d5c` "ANDROID: scudo: add per-process hard RSS limit" | GKI 通用内核对 scudo 的支持 |

---

## 附录 B：风险速查表（native 堆 / 日志关键字 / dumpsys 特征 / 排查入口）

| 问题类型 | 日志关键字 | dumpsys / meminfo 特征 | 排查入口 |
|----------|-----------|------------------------|----------|
| **scudo Chunk header 损坏** | `corrupted chunk header at 0x...` | 进程 crash + tomestone | `tombstone` 解析 → `__sanitizer_die_callback` |
| **scudo 双重释放** | `attempting double-free` / `chunk is already quarantined` | 进程 crash | `dumpsys meminfo` 配额 + `__scudo_print_stats` |
| **quarantine 满 / drain 频繁** | `__scudo_print_stats: drain=...` | Native Heap 虚高 | `setenv SCUDO_OPTIONS` 调大 `quarantine_size_kb` |
| **scudo hard RSS limit 触发** | `scudo: hard RSS limit reached` | 进程 SIGKILL/abort | 调大 `hard_rss_limit_mb` / memcg `memory.max` |
| **memcg OOM kill** | `memory.events oom_kill: N` | `memory.peak` 接近 `memory.max` | `cat /sys/fs/cgroup/.../memory.events` |
| **cgroup v2 限额** | `__libc_oom_handler invoked` | mmap 返回 MAP_FAILED | `dumpsys meminfo` + `memory.peak` |
| **ASan 检测到越界** | `==PID==ERROR: AddressSanitizer: heap-buffer-overflow` | 进程 abort + 详细 stack | `tombstone` 解析 ASan trace |
| **GWP-ASan 抽样崩溃** | `GWP-ASan: SEGV on unknown address 0x...` | 进程 SIGSEGV | 1% 概率为业务 bug，99% 概率为 UAF |
| **Native 堆泄漏** | `__scudo_print_stats: RSS monotonic rising` | Native Heap 单调上涨 | `memory.peak` 持续涨 → 找泄漏点 |
| **TSD cache 长期不释放** | （无明显日志） | 进程退出后 native 堆不缩 | 增加线程退出检查 + `__scudo_print_stats` |
| **ION/DMA-BUF 泄漏** | （无 native 堆日志） | Graphics 行单调涨 | `dumpsys SurfaceFlinger` 找未释放 BufferQueue |
| **scudo 关闭 / 走 jemalloc** | `libc.debug.malloc=1` | dumpsys Native Heap 异常稳定 | `getprop libc.debug.malloc` 排查 |
| **jni 引用泄漏** | `JNI ERROR (app bug): local reference table overflow` | Java 堆不释放 | ART hprof + `art/runtime/jni/jni_internal.cc` |
| **malloc 返回 NULL** | `try_alloc failed` | 进程可能 hang | `dumpsys meminfo` + `memory.peak` |
| **scudo 慢路径 / Region 耗尽** | （无明显日志） | malloc 延迟 +200ns | `__scudo_print_stats` 看 region count |

---

## 篇尾衔接

本篇（04-Native 堆内存与分配器）沿着"边界 → 调用链 → 内部结构 → 配置 → memcg → 进程实例"的链路，把 native 堆在 AOSP 14 上的完整机制讲透。读完后，你应该能够在 5 分钟内回答：

- "**Native Heap 行这个数字是怎么来的？**" → scudo 管辖 chunk 的总大小
- "**为什么 `memory.peak` 比 dumpsys Native Heap 大 2-3 倍？**" → mmap 区 + ION 物理页 + Binder 缓冲
- "**OOM 触发时是 scudo 先杀还是 memcg 先杀？**" → 看 hard_rss_limit_mb 和 memory.max 谁先到
- "**如何调优 scudo 配置？**" → 按进程类型选 quarantine_size + hard_rss_limit 双层

下一篇 [05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md) 将深入 Framework 层，**横向展开** oom_adj / oom_score_adj 体系、进程分类（前台/可见/后台/缓存/空）、computeOomAdjLocked 源码走读、LMK → LMKD 演进——从"进程本身能涨多少"扩展到"AMS 怎么决定杀哪个进程"。读完本篇理解 native 堆自身治理，读完下一篇理解 native 堆所在的**全系统治理**。

**系列总览**：[README-MM_v2系列](README-MM_v2系列.md) | **上一篇**：[03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md) | **下一篇**：[05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md)

---

> **关于跨篇引用**：
> - 与 **[01-内存系统总览](01-内存系统总览：从进程视角到硬件的完整链路.md)** 关联：本篇 §1 引用其五层架构与 §3 一个 byte 旅程
> - 与 **[02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md)** 关联：本篇 §2.3.4 引用其 mmap 系统调用与 VMA 红黑树
> - 与 **[03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md)** 关联：本篇 §1.4 引用其 JNI 引用表与 Java 堆/Native 堆边界
> - 与 **[05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md)** 关联：本篇 §6 引用其 oom_adj 体系（zygote-forked App 与 native daemon 分类）
> - 与 **[06-LMKD 用户态内存杀手](06-LMKD 用户态内存杀手.md)** 关联：本篇 §1.3 引用其"杀谁不杀谁"决策（与 scudo hard limit + memcg 联动）
> - 与 **[07-PSI、vmpressure、memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md)** 关联：本篇 §5 引用其 memcg PSI 接口与 cgroup v2 压力传递
> - 与 **[12-内存稳定性风险全景](12-内存稳定性风险全景.md)** 关联：本篇 §1.4 引用其"Graphics 行泄漏"分类，§7 引用其五大类风险框架
