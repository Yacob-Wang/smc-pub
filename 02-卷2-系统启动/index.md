# 卷 2　系统启动

> **本卷定位**：启动链路是稳定性问题的重灾区——开机卡顿 / 启动崩溃 / 开机黑屏 / 启动耗电都在这里查。**按启动时序逐章展开**，是全书唯一严格按时间顺序组织的卷。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 6 章 | Bootloader 到 Kernel | 🚧 撰写中 |
| 第 7 章 | Init 进程与 init.rc | 🚧 撰写中 |
| 第 8 章 | Zygote 与 ART 启动 | 📋 待撰写 |
| 第 9 章 | SystemServer 启动 | 📋 待撰写 |
| 第 10 章 | 应用启动与首帧 | 🚧 撰写中 |
| 第 11 章 | 系统启动性能专项 | 🚧 撰写中 |

---

## 章节详细

### 第 6 章　Bootloader 到 Kernel

> 启动链路第一阶段——硬件怎么把控制权移交给 Kernel。

- 6.1 Bootloader 类型：LK / ABL（Android Bootloader）/ U-Boot
- 6.2 Bootloader 启动流程：PBL → ABL → Kernel
- 6.3 Kernel 启动入口：head.S / start_kernel
- 6.4 早期初始化：setup_arch / sched_init / page_alloc
- 6.5 Kernel cmdline 与 dtb：设备树 + 内核参数
- 6.6 启动失败：Kernel panic / boot loop 的现场与分析

**本章小结**：Kernel 启动阶段出问题 = boot loop，唯一证据是 last_kmsg / pstore，抓不到就无法定位。

### 第 7 章　Init 进程与 init.rc

> 第一个用户态进程——整个 Android 系统的「启动管家」。

- 7.1 Init 进程（system/core/init）启动流程
- 7.2 init.rc 语法：service / action / import / on
- 7.3 启动阶段：early-init / init / post-fs / post-fs-data / late-start
- 7.4 属性服务（Property Service）：跨进程配置传递
- 7.5 SELinux 上下文加载与策略执行时机
- 7.6 init 阶段慢与卡死的常见原因

**本章小结**：init 阶段慢会 gating 后续所有服务——这里省 1 秒，整机启动省的往往不止 1 秒。

### 第 8 章　Zygote 与 ART 启动

> Java 进程工厂——所有 App 进程的模板。ART 的完整机制见卷 3 第 20 章，本章只讲**启动阶段**。

- 8.1 Zygote 启动：fork + 预加载（preload classes / resources）
- 8.2 ART 启动：libart.so / ClassLinker / OAT 镜像加载
- 8.3 启动预优化：Profile Guided Compilation / Cloud Profile
- 8.4 启动类加载优化：deferred class load / lazy verification
- 8.5 Zygote fork 慢 / Zygote crash 的调查

**本章小结**：Zygote 是所有 App 启动的公共瓶颈——它慢 1 次，全系统慢 N 次。

### 第 9 章　SystemServer 启动

> 50+ 系统服务的启动编排者——核心服务都在这里孵化。

- 9.1 SystemServer 启动入口：SystemServer.java
- 9.2 服务启动三阶段：引导（Bootstrap）→ 核心（Core）→ 其他（Other）
- 9.3 核心服务详解：PMS → AMS → WMS → IMS 的启动依赖
- 9.4 ServiceManager 与 Binder 域：服务注册与跨进程查找
- 9.5 启动阶段统计：bootstat 与阶段耗时归因
- 9.6 SystemServer 启动慢 / 死锁 / crash 的调查

**本章小结**：SystemServer 死 = 整机不响应，连 SystemUI 一起挂——它是全系统的单点。

### 第 10 章　应用启动与首帧

> 从 Launcher 点击到第一帧显示——App 启动的**机制链路**。优化实践见卷 6 第 38 章。

- 10.1 Launcher 点击 → ActivityThread：Binder 跨进程调用
- 10.2 进程创建：Zygote fork 的特殊参数
- 10.3 Application 初始化：attachBaseContext / onCreate / ContentProvider 初始化
- 10.4 视图树构建：measure / layout / draw
- 10.5 Choreographer 调度：VSYNC 与 input / animation / traversal 回调
- 10.6 首帧定义：First Frame / First Image / Cold / Warm / Hot Start
- 10.7 启动时间测量：am start -W / logcat / Perfetto

**本章小结**：启动优化必须分段——Application、Activity、Window、View 各自的瓶颈成因完全不同。

### 第 11 章　系统启动性能专项

> **开机链路**（上电 → 桌面可用）的性能分析与优化。与卷 6 第 38 章的分工：本章管**系统启动**，第 38 章管**应用启动**。

- 11.1 开机时间的测量与阶段拆分：bootchart / bootstat / Perfetto boot trace
- 11.2 各阶段基线：Bootloader / Kernel / init / Zygote / SystemServer / Launcher
- 11.3 开机慢的定位方法：服务依赖链 / 串行阻塞 / IO 争抢
- 11.4 开机优化手段：并行化 / 延迟启动 / 预编译 / 镜像优化
- 11.5 开机期稳定性：黑屏 / boot loop / 开机 ANR
- 11.6 开机期资源峰值：内存 / IO / CPU 争抢治理

**本章小结**：开机性能是**服务依赖图**的优化问题，不是单点耗时问题——找关键路径比找最慢的服务更重要。
