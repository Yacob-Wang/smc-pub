# 卷 2　系统启动

> **本卷定位**：启动链路是稳定性问题的重灾区——开机卡顿 / 启动崩溃 / 开机黑屏 / 启动耗电都在这里查。**按启动时序逐章展开**，是全书唯一严格按时间顺序组织的卷。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 6 章 | Bootloader 到 Kernel | 🚧 撰写中（6.1–6.6） |
| 第 7 章 | Init 进程与 init.rc | 🚧 撰写中（7.1–7.6） |
| 第 8 章 | Zygote 与 ART 启动 | 🚧 撰写中（8.1–8.6） |
| 第 9 章 | SystemServer 启动 | 🚧 撰写中（9.1–9.6） |
| 第 10 章 | 应用启动与首帧 | 🚧 撰写中（仅 App→首帧；素材 A05/A06；10.x 待拆） |
| 第 11 章 | 系统启动性能专项 | 🚧 撰写中（B/C/D 模块） |

---



## 卷首收口 · 上电到桌面

> **本卷的"卷级收口"**——把 6-11 章的"上电到桌面"全链路用 26 个时间锚点串成 1 张时序图 + 1 张节点表,标注每个阶段的劣化易发点,以安卓模拟器真实启动日志为骨架。

- [0. 上电到桌面: 冷启动 26 锚点全链路时序与劣化分析](0-上电到桌面-冷启动26锚点全链路时序与劣化分析.md)　— 5 大阶段 × 26 锚点 + 5 大劣化位置 + emulator 真实 logcat 串联
  - 阶段 1 硬件+Bootloader(锚点 1-5) → 阶段 2 Kernel(锚点 6-10) → 阶段 3 init+Zygote+ART(锚点 11-17) → 阶段 4 SystemServer+PMS+AMS+WMS(锚点 18-23) → 阶段 5 Launcher+首帧+boot_completed(锚点 24-26)
  - **阶段 4 是最大单一杠杆点**(40% 整机耗时);**5 大劣化易发点**: PMS 扫描(40%)/ Launcher+SDK 自启(25%)/ fs_mgr 挂载(15%)/ Zygote+ART(12%)/ AMS+WMS(8%)
  - emulator 真实启动日志:`logcat -b events | grep boot_progress` + `getprop | grep boottime` + `dumpsys bootstat` + `bootchart` 4 件套
  - 关键产出:emulator 启动对比法 + 劣化定位 3 步法
  - 2 个实战案例:emulator PMS 扫描卡 12s / 真机 SDK 拉起 5s
  - 字数 4500+ / 12 张表 / 6 张 ASCII 大图 / 真实 logcat 4 段

### 26 锚点全链路总表(摘要)

| 阶段 | 锚点 | 名称 | 关键 logcat 事件 | 关键源码 | 详见 |
|------|------|------|------------------|----------|------|
| 1 硬件+Bootloader | 1 | power-on | (硬件) | PMIC | §6.1 |
| | 2 | PBL 启动 | (Boot ROM) | PBL | §6.2 |
| | 3 | ABL 启动 | (OEM log) | aboot.c | §6.2 |
| | 4 | Kernel 加载 | "Loading kernel..." | aboot.c | §6.2 |
| | 5 | Kernel 启动 | "Uncompressing Linux..." | aboot.c | §6.3 |
| 2 Kernel 启动 | 6 | start_kernel | `boot_progress_start` | init/main.c | §6.3 |
| | 7 | setup_arch | (内核 log) | arch/arm64/kernel/setup.c | §6.4 |
| | 8 | page_alloc_init | "Memory: ..." | mm/page_alloc.c | §6.4 |
| | 9 | sched_init | "SMP: Total ... processors" | kernel/sched/core.c | §6.4 |
| | 10 | rest_init | "Run /init as process 1" | init/main.c | §6.3 |
| 3 init+Zygote+ART | 11 | init 进程启动 | "init: starting service 'init'" | system/core/init/init.cpp | §7.1 |
| | 12 | init.rc 解析 | "init: Parsing file /init.rc" | init.cpp | §7.2 |
| | 13 | early-init 触发 | "init: early-init" trigger | init.cpp | §7.3 |
| | 14 | vold 启动 | "init: starting service 'vold'" | system/vold/main.cpp | §7.3 |
| | 15 | fs_mgr 挂载 | "fs_mgr: mount /system OK" | fs_mgr/fs_mgr.cpp | §7.3 |
| | 16 | Zygote 启动 | "init: starting service 'zygote'" | app_main.cpp | §8.1 |
| | 17 | ART 启动 | "art: starting runtime" | art/runtime/runtime.cc | §8.2 |
| 4 SystemServer+核心服务 | 18 | SystemServer 入口 | "SystemServer: Starting system server" | SystemServer.java | §9.1 |
| | 19 | Bootstrap 服务 | "ActivityManager: System now booting" | SystemServer.java | §9.2 |
| | 20 | PMS 启动 | `boot_progress_pms_start` | PackageManagerService.java | §9.3 |
| | 21 | PMS 扫描 | `boot_progress_pms_scan_end` | PackageManagerService.java | §9.3 |
| | 22 | AMS ready | `boot_progress_ams_ready` | ActivityManagerService.java | §9.3 |
| | 23 | WMS 亮屏 | `boot_progress_enable_screen` | WindowManagerService.java | §9.3 |
| 5 Launcher+首帧+boot_completed | 24 | boot anim 结束 | "SurfaceFlinger: Boot animation finished" | SurfaceFlinger.cpp | §10.0 |
| | 25 | Launcher 首帧 | "ActivityTaskManager: START u0 {act=android.intent.action.MAIN...}" | ActivityTaskManager.java | §10.0 / §10.6 |
| | 26 | boot_completed | `boot_progress_boot_completed` | ActivityManagerService.java | §10.0 |

> **boot_progress_xxx 事件来自 AOSP 17 EventLogTags.logtags 真实定义**,可在 emulator 上 `adb logcat -b events | grep boot_progress` 直接验证。
> **完整 26 锚点详细分析 + 时序图 + 真实 logcat 串联**:见 [0-上电到桌面](0-上电到桌面-冷启动26锚点全链路时序与劣化分析.md)

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
> **章级覆盖**：Zygote fork 机制 / ART 启动（libart.so / ClassLinker / OAT）/ PGC + Cloud Profile / deferred class load / Zygote fork 慢与 crash 调查 / Zygote 内存治理（fork COW 与 RSS）

- 8.1 [Zygote 启动：从 app_process64 到 runSelectLoop](08-Zygote%20与%20ART%20启动/8.1-Zygote启动-fork与预加载.md) — 章首节，全局观 + 核心机制
- 8.2 [ART 启动：libart.so / ClassLinker / OAT 镜像加载](08-Zygote%20与%20ART%20启动/8.2-ART启动-libart与ClassLinker.md) — Runtime::Init 4 大步 + OAT 损坏 3 类自愈
- 8.3 [启动预优化：PGC + Cloud Profile](08-Zygote%20与%20ART%20启动/8.3-启动预优化-PGC与Cloud-Profile.md) — dex2oat 触发链 + Cloud Profile 3 类来源
- 8.4 [启动类加载优化：deferred class load / lazy verification](08-Zygote%20与%20ART%20启动/8.4-启动类加载优化-deferred-class-load.md) — preload vs lazy 判定准则
- 8.5 [Zygote fork 慢 / Zygote crash 调查](08-Zygote%20与%20ART%20启动/8.5-Zygote-fork慢与crash调查.md) — 风险地图 + 诊断治理（Zygote 内部视角）
- 8.6 [Zygote 内存治理：fork copy-on-write 与 RSS 控制](08-Zygote%20与%20ART%20启动/8.6-Zygote内存治理-fork-copy-on-write.md) — 本卷新增节，3 类压力点 + LMKD 联动

**本章小结**：Zygote 是所有 App 启动的公共瓶颈——它慢 1 次，全系统慢 N 次。**全章 6 节，复合等效约 25000 字**，20 张图，10+ 案例。

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

> 从 Launcher 点击到第一帧显示——App 启动的**机制链路**。  
> **不重复**第 6–9 章整机启动（Bootloader / Init / Zygote / SystemServer）。优化实践见卷 6 第 38 章。

- 10.1 Launcher 点击 → ActivityThread：Binder 跨进程调用
- 10.2 进程创建：Zygote fork 的特殊参数（应用侧；机制见第 8 章）
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
