# 卷 2　系统启动

> **本卷定位**：启动链路是稳定性问题的重灾区——开机卡顿 / 启动崩溃 / 开机黑屏 / 启动耗电都在这里查。本卷按启动时序逐章展开。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 6 章 | Bootloader 到 Kernel | 🚧 撰写中 |
| 第 7 章 | Init 进程与 init.rc | 🚧 撰写中 |
| 第 8 章 | Zygote 与 ART 启动 | 🚧 撰写中 |
| 第 9 章 | SystemServer 启动 | 🚧 撰写中 |
| 第 10 章 | 应用启动与首帧 | 🚧 撰写中 |
| 第 11 章 | 启动性能专项 | 🚧 撰写中 |

---

## 章节目录（详细）

### 第 6 章　Bootloader 到 Kernel

- 6.1 Bootloader 类型：LK / ABL / U-Boot
- 6.2 Bootloader 启动流程：PBL → ABL → Kernel
- 6.3 Kernel 启动入口：head.S / start_kernel
- 6.4 早期初始化：setup_arch / sched_init / page_alloc
- 6.5 Kernel cmdline 与 dtb：设备树 + 内核参数
- 6.6 启动失败案例：Kernel panic / boot loop

> **本章小结**：Kernel 启动阶段出问题 = boot loop，调查工具是 last_kmsg / pstore。

### 第 7 章　Init 进程与 init.rc

- 7.1 Init 进程（system/core/init）启动流程
- 7.2 init.rc 语法：service / action / import / on
- 7.3 启动阶段：early / init / late-start / post-fs / post-fs-data
- 7.4 属性服务（Property Service）：跨进程配置传递
- 7.5 SELinux 上下文加载与策略执行
- 7.6 init 启动慢的常见原因

> **本章小结**：init 阶段慢 = 整机启动慢的 N 倍影响（gating 后续所有服务）。

### 第 8 章　Zygote 与 ART 启动

- 8.1 Zygote 启动：fork + 预加载（preload classes/resources）
- 8.2 ART 启动：libart.so / ClassLinker / OAT 镜像加载
- 8.3 启动预优化：Profile Guided Compilation / Cloud Profile
- 8.4 启动类加载优化：deferred class load / lazy verification
- 8.5 Zygote fork 慢 / Zygote crash 调查

> **本章小结**：Zygote 是 App 启动的瓶颈点，它的健康决定所有 App 启动速度。

### 第 9 章　SystemServer 启动

- 9.1 SystemServer 启动入口：SystemServer.java
- 9.2 50+ 服务启动顺序：引导阶段 → 核心阶段 → 其他阶段
- 9.3 核心服务详解：PMS → AMS → WMS → IMS 启动流程
- 9.4 ServiceManager 与 Binder 域：服务注册与跨进程查找
- 9.5 启动阶段统计：bootstat
- 9.6 SystemServer 启动慢 / 死锁 / crash 调查

> **本章小结**：SystemServer 死 = 整机不响应（SystemUI 也挂）。

### 第 10 章　应用启动与首帧

- 10.1 Launcher 点击 → ActivityThread：Binder 跨进程调用
- 10.2 进程创建：Zygote fork（特殊参数 + waiting for debugger）
- 10.3 Application 初始化：attachBaseContext / onCreate
- 10.4 视图树构建：measure / layout / draw
- 10.5 Choreographer 调度：VSYNC 信号与 input/animation/traversal/tick
- 10.6 第一帧：First Frame / First Image / Cold Start / Warm Start / Hot Start
- 10.7 启动时间测量：am start -W / logcat / bootchart

> **本章小结**：启动优化必须分段——Application、Activity、Window、View 各自的瓶颈不同。

### 第 11 章　启动性能专项

- 11.1 启动时间测量工具：bootchart / Perfetto / bootstat / am start -W
- 11.2 启动阶段拆分：Pre-loader → Application → Activity → Window → First Frame
- 11.3 启动卡顿定位：主线程 IO / 反射 / 类加载 / 资源加载
- 11.4 启动优化方法：预加载 / 延迟初始化 / 多阶段 / Jetpack Startup / Baseline Profile
- 11.5 启动期稳定性保障：白屏 / 闪退 / 黑屏 / 跨进程通信
- 11.6 启动期内存峰值治理

> **本章小结**：启动优化是综合工程——Application、四大组件、资源、反射、类加载都要管。

