"""
build_book_skeleton.py - Step 2: 建 8 卷 50 章空骨架
- 建 8 个卷目录 + 50 个章目录
- 每章一个 index.md（占位，含主旨/章定位/5-6 子节标题/小结）
- 每卷一个 index.md（卷级落地页）
- 不动 prepare_web_docs.py / mkdocs.yml（现有 build 继续工作）
"""
import re
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\deepLife\Documents\GitHub\smc-pub")
OUTLINE_MD = REPO_ROOT / "00-Meta" / "书籍目录-v1.md"

# 8 卷 50 章（与书籍目录-v1.md 完全一致）
VOLUMES = [
    ("01-卷1-Android系统基础与平台", "卷 1　Android 系统基础与平台",
     "地基章节——稳定性架构师必须理解全栈结构、构建系统、HAL 抽象、Kernel 视角、安全模型。",
     [
         (1, "Android 系统全景与 AOSP 17", [
             "1.1 系统分层：Hardware → Kernel → HAL → Native → Runtime → Framework → App",
             "1.2 AOSP 17 主要变化（vs AOSP 14/15/16）：Mainline 模块演进、ART 17 优化、隐私沙箱",
             "1.3 核心组件关系图：AMS/PMS/WMS/SurfaceFlinger/Binder/PackageManager",
             "1.4 进程模型：Zygote 体系、SystemServer、App 进程的生命周期与权限边界",
             "1.5 稳定性视角的系统边界：哪些是稳定性工程师负责的、哪些跨团队",
             "1.6 工程基线：AOSP 17.0.0_r1 + Linux 6.18 + 测试机型",
         ], "稳定性工作边界 = 全栈但有侧重，重点是 Framework / Native / Kernel 三层协同。"),
         (2, "AOSP 源码结构与构建系统", [
             "2.1 源码目录：frameworks/base / system/core / kernel / hardware / vendor / packages",
             "2.2 Soong / Blueprint / Android.bp：现代构建语言",
             "2.3 Makefile / BoardConfig / device.mk：兼容层与传统构建",
             "2.4 镜像生成：system.img / vendor.img / boot.img / vbmeta.img / dtbo.img",
             "2.5 模块化与 GKI：Generic Kernel Image 与模块化架构",
             "2.6 编译/烧录/调试工具链：adb / fastboot / avbtool / lunch / make",
         ], "能从源码定位到机制，能从构建系统追溯到版本来源。"),
         (3, "硬件抽象层（HAL）与 Treble 架构", [
             "3.1 HAL 接口设计：AIDL / HIDL 与 .hal 文件",
             "3.2 Treble 架构：vendor 与 system 解耦、VINTF 兼容性矩阵",
             "3.3 HIDL → AIDL 迁移：AOSP 17 已全面 AIDL",
             "3.4 VINTF 与 CTS：兼容性验证机制",
             "3.5 OEM-BSP 适配要点：哪些必须做、哪些可选",
         ], "vendor 行为是稳定性跨平台问题的根因之一，HAL 抽象让 system 升级不依赖 vendor。"),
         (4, "Linux Kernel 基础（Android 视角）", [
             "4.1 进程调度：CFS / RT / deadline / cgroup",
             "4.2 内存管理：VMA / 页面回收 / OOM / LMK / PSI",
             "4.3 IO 栈：VFS / Page Cache / IO 调度 / f2fs / erofs",
             "4.4 中断与同步：workqueue / RCU / 自旋锁 / 内存屏障",
             "4.5 Binder 驱动：mmap / 引用计数 / 线程池（卷 3 第 12 章展开）",
             "4.6 网络协议栈：TCP/UDP/socket / netfilter（卷 3 第 17 章展开）",
         ], "稳定性问题 30% 根因在 Kernel，ANR / NE / 卡死都从这里找。"),
         (5, "安全基础（SELinux / AVB）", [
             "5.1 Android 安全模型：沙箱 / UID / 权限 / 签名",
             "5.2 SELinux：sepolicy / 域 / 类型 / 强制访问控制",
             "5.3 AVB（Android Verified Boot）：启动验证链",
             "5.4 权限框架：Android Permission / Runtime Permission / AppOps",
             "5.5 权限拒绝类问题的调查方法",
         ], "权限失败 ≠ 应用问题，可能是 SELinux 拒绝或 AVB 校验失败。"),
     ]),
    ("02-卷2-系统启动", "卷 2　系统启动",
     "启动链路是稳定性问题的重灾区——开机卡顿 / 启动崩溃 / 开机黑屏 / 启动耗电都在这里查。本卷按启动时序逐章展开。",
     [
         (6, "Bootloader 到 Kernel", [
             "6.1 Bootloader 类型：LK / ABL / U-Boot",
             "6.2 Bootloader 启动流程：PBL → ABL → Kernel",
             "6.3 Kernel 启动入口：head.S / start_kernel",
             "6.4 早期初始化：setup_arch / sched_init / page_alloc",
             "6.5 Kernel cmdline 与 dtb：设备树 + 内核参数",
             "6.6 启动失败案例：Kernel panic / boot loop",
         ], "Kernel 启动阶段出问题 = boot loop，调查工具是 last_kmsg / pstore。"),
         (7, "Init 进程与 init.rc", [
             "7.1 Init 进程（system/core/init）启动流程",
             "7.2 init.rc 语法：service / action / import / on",
             "7.3 启动阶段：early / init / late-start / post-fs / post-fs-data",
             "7.4 属性服务（Property Service）：跨进程配置传递",
             "7.5 SELinux 上下文加载与策略执行",
             "7.6 init 启动慢的常见原因",
         ], "init 阶段慢 = 整机启动慢的 N 倍影响（gating 后续所有服务）。"),
         (8, "Zygote 与 ART 启动", [
             "8.1 Zygote 启动：fork + 预加载（preload classes/resources）",
             "8.2 ART 启动：libart.so / ClassLinker / OAT 镜像加载",
             "8.3 启动预优化：Profile Guided Compilation / Cloud Profile",
             "8.4 启动类加载优化：deferred class load / lazy verification",
             "8.5 Zygote fork 慢 / Zygote crash 调查",
         ], "Zygote 是 App 启动的瓶颈点，它的健康决定所有 App 启动速度。"),
         (9, "SystemServer 启动", [
             "9.1 SystemServer 启动入口：SystemServer.java",
             "9.2 50+ 服务启动顺序：引导阶段 → 核心阶段 → 其他阶段",
             "9.3 核心服务详解：PMS → AMS → WMS → IMS 启动流程",
             "9.4 ServiceManager 与 Binder 域：服务注册与跨进程查找",
             "9.5 启动阶段统计：bootstat",
             "9.6 SystemServer 启动慢 / 死锁 / crash 调查",
         ], "SystemServer 死 = 整机不响应（SystemUI 也挂）。"),
         (10, "应用启动与首帧", [
             "10.1 Launcher 点击 → ActivityThread：Binder 跨进程调用",
             "10.2 进程创建：Zygote fork（特殊参数 + waiting for debugger）",
             "10.3 Application 初始化：attachBaseContext / onCreate",
             "10.4 视图树构建：measure / layout / draw",
             "10.5 Choreographer 调度：VSYNC 信号与 input/animation/traversal/tick",
             "10.6 第一帧：First Frame / First Image / Cold Start / Warm Start / Hot Start",
             "10.7 启动时间测量：am start -W / logcat / bootchart",
         ], "启动优化必须分段——Application、Activity、Window、View 各自的瓶颈不同。"),
         (11, "启动性能专项", [
             "11.1 启动时间测量工具：bootchart / Perfetto / bootstat / am start -W",
             "11.2 启动阶段拆分：Pre-loader → Application → Activity → Window → First Frame",
             "11.3 启动卡顿定位：主线程 IO / 反射 / 类加载 / 资源加载",
             "11.4 启动优化方法：预加载 / 延迟初始化 / 多阶段 / Jetpack Startup / Baseline Profile",
             "11.5 启动期稳定性保障：白屏 / 闪退 / 黑屏 / 跨进程通信",
             "11.6 启动期内存峰值治理",
         ], "启动优化是综合工程——Application、四大组件、资源、反射、类加载都要管。"),
     ]),
    ("03-卷3-核心机制", "卷 3　核心机制（横跨 AOSP 分层）",
     "打破 AOSP 分层——Binder / 进程 / 内存 / IO / 显示 等主题横跨 Kernel、Native、Runtime、Framework、App。稳定性问题往往需要全链路排查。",
     [
         (12, "Binder IPC 深度", [
             "12.1 Binder 驱动：mmap / 引用计数 / 线程池（红黑树）",
             "12.2 Binder 协议：BC/BR 命令 / Parcel / flat_binder_object",
             "12.3 Java 框架层：AIDL / ServiceManager / deathRecipient",
             "12.4 oneway / parcelable / Binder 池大小",
             "12.5 Binder 调用链路：客户端 → 驱动 → 服务端",
             "12.6 Binder 卡死排查：binder 线程数 / oneway 阻塞 / 死锁",
         ], "ANR 30% 根因是 Binder 阻塞。"),
         (13, "进程与生命周期", [
             "13.1 进程模型：fork / vfork / clone / CGroup",
             "13.2 进程优先级：oom_score_adj / cgroup / ProcessList",
             "13.3 进程间通信总览：Binder / Socket / SharedMemory / Handler / ContentProvider",
             "13.4 进程生命周期：启动 / 优先级 / 杀进程策略 / LMK (Low Memory Killer)",
             "13.5 进程退出：Exit / Tombstone / Process.kill / ANR 杀进程",
             "13.6 进程崩溃与恢复：CrashHandler / 进程拉起策略",
         ], "进程优先级设置错误 = 关键进程被 LMK 误杀。"),
         (14, "线程与 Handler 消息机制", [
             "14.1 pthread / HandlerThread / Java 线程模型",
             "14.2 Handler / Looper / MessageQueue 原理",
             "14.3 消息屏障（Sync Barrier）：Vsync 信号如何优先处理",
             "14.4 IdleHandler / 延迟消息 / 定时器",
             "14.5 卡帧与 ANR 原理：主线程消息处理超时",
             "14.6 IdleHandler 与 Choreographer 协同",
         ], "主线程的一切都走 Handler——卡顿排查先看主线程消息队列。"),
         (15, "内存管理全链路", [
             "15.1 内核分配器：kmalloc / vmalloc / slab / page",
             "15.2 进程虚拟内存：VMA / mmap / 缺页 / 写时复制",
             "15.3 ART 堆：TLAB / Concurrent GC / 引用类型 / 卡片表",
             "15.4 Framework 内存治理：AMS / TrimMemory / ComponentCallbacks2",
             "15.5 OOM 与低内存：LMK / OOM Killer / PSI / memory pressure",
             "15.6 内存泄漏排查：hprof / LeakCanary 原理 / GC roots / MAT",
         ], "内存问题 = 全栈，单独看任何一层都不够。"),
         (16, "IO 与存储", [
             "16.1 VFS 与文件系统：ext4 / f2fs / erofs",
             "16.2 Page Cache 与 IO 调度：CFQ / deadline / bfq",
             "16.3 存储框架：StorageManager / Volume / FUSE / SDCardFS",
             "16.4 ContentProvider 数据访问",
             "16.5 数据库：SQLite / Room / 文件锁",
             "16.6 IO 性能瓶颈定位：iostat / atrace / IO hang",
         ], "启动期 70% 卡顿根因是主线程 IO。"),
         (17, "网络与连接", [
             "17.1 网络协议栈：TCP / UDP / socket",
             "17.2 ConnectivityManager / NetworkAgent / NetworkFactory",
             "17.3 WiFi / 移动数据 / VPN / 代理",
             "17.4 Bluetooth / NFC / GPS",
             "17.5 网络性能与耗电：网络切换 / 信号弱 / DNS 慢",
             "17.6 网络类 ANR 调查：ConnectivityService / DataCall / Socket",
         ], "网络 ANR ≠ 网络慢，可能是 ConnectivityService 阻塞。"),
         (18, "显示与渲染", [
             "18.1 SurfaceFlinger 与 BufferQueue：跨进程 Buffer 传递",
             "18.2 Choreographer 与 VSYNC：60Hz / 90Hz / 120Hz 调度",
             "18.3 View 体系：measure / layout / draw / invalidate",
             "18.4 RenderThread 与 HWUI：硬件加速",
             "18.5 卡顿与掉帧分析：Jank / Slow frame / Stutter",
             "18.6 屏幕闪烁 / 黑屏 / 花屏调查",
         ], "卡顿 50% 根因在主线程，30% 在 RenderThread，20% 在 SurfaceFlinger。"),
         (19, "电源与续航", [
             "19.1 PowerManager 与 WakeLock：保持唤醒与休眠",
             "19.2 Doze 模式：深度休眠机制",
             "19.3 Battery Historian 与耗电分析",
             "19.4 后台限制：JobScheduler / WorkManager / Firebase Job Dispatcher",
             "19.5 异常掉电：内核 / Modem / 电池 / 充电 IC",
             "19.6 续航优化方法",
         ], "续航问题需要硬件 + 软件 + 行为三方联合排查。"),
         (20, "ART 运行时", [
             "20.1 Dex 编译：AOT / JIT / 解释器 / Cloud Profile",
             "20.2 类加载与反射：ClassLoader / Method / Field",
             "20.3 垃圾回收：标记清除 / 并发 / 引用类型 / Finalize",
             "20.4 JNI 与 Native 桥接：JNIEnv / RegisterNatives",
             "20.5 启动类加载优化：Profile / Baseline Profile / dex2oat",
             "20.6 ART 内部崩溃调查（AOSP 17 ART17）",
         ], "ART 是 Java 性能与稳定性的核心——20% 的内容对应 50% 的问题。"),
         (21, "输入系统", [
             "21.1 InputManagerService 架构",
             "21.2 输入事件流：InputReader → InputDispatcher → 窗口",
             "21.3 触摸事件分发：ViewRootImpl → DecorView → ViewGroup → View",
             "21.4 输入 ANR 原理：5s input dispatch timeout",
             "21.5 输入卡顿与延迟",
             "21.6 焦点窗口与无焦点 ANR",
         ], "input ANR 90% 是主线程 / Binder 阻塞，不是 input 系统本身问题。"),
     ]),
    ("04-卷4-稳定性症状诊断", "卷 4　稳定性症状诊断",
     "核心战场——8 大症状，每类从机制到案例到工具全链路。",
     [
         (22, "ANR 深度", [
             "22.1 ANR 类型：input / broadcast / service / contentprovider",
             "22.2 ANR 检测机制：InputManager / AMS / Watchdog",
             "22.3 ANR 现场采集：trace.txt / am_anr / data/anr/ / dropbox",
             "22.4 ANR 调查方法论：主线程阻塞 / Binder 阻塞 / 死锁",
             "22.5 ANR 案例库（5-10 个真实场景）",
             "22.6 ANR 治理：监控、告警、防御",
         ], "ANR 的根因永远不在 input/broadcast 本身——要找主线程为什么阻塞。"),
         (23, "Java 异常", [
             "23.1 常见 Java 异常类型：NPE / ClassCast / ConcurrentModification / OOM / ANR 触发",
             "23.2 Tombstone 与 Java 堆栈解析",
             "23.3 启动期崩溃特殊排查",
             "23.4 主线程异常恢复策略",
             "23.5 第三方库异常的定位与治理",
             "23.6 Java Crash 监控体系",
         ], "90% Java 异常 = 空指针 + 状态错乱 + 第三方库兼容性。"),
         (24, "Native 异常", [
             "24.1 信号处理：SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL",
             "24.2 Tombstone 解析：寄存器 / 栈回溯 / 内存映射 / 共享库",
             "24.3 so 库加载与符号化：addr2line / ndk-stack / symbolicator",
             "24.4 AddressSanitizer / HWASan / UBSan / GWP-ASan",
             "24.5 Native 案例库（5-10 个真实场景）",
             "24.6 Native Crash 治理：crashpad / breakpad",
         ], "Native 崩溃 80% 是内存问题——踩栈 / use-after-free / double-free。"),
         (25, "系统无响应（SWT / Watchdog）", [
             "25.1 Watchdog 原理：30s 主线程 / 60s 总体",
             "25.2 卡死 vs 慢：slow operation 阈值",
             "25.3 调查方法：systrace / stack sampling / Handler sampling",
             "25.4 卡死期间的现场保留",
             "25.5 SWT 案例库（3-5 个）",
             "25.6 SWT 治理",
         ], "SWT 的根因 90% 是 SystemServer 内部某个服务卡死。"),
         (26, "HANG 与死锁", [
             "26.1 死锁类型：自死锁 / 互锁 / 活锁 / 饥饿 / 顺序死锁",
             "26.2 死锁检测：lockdep / 死锁线程 dump",
             "26.3 死锁恢复策略：超时 / watchdog / 强制 kill",
             "26.4 活锁：CPU 跑满但不响应",
             "26.5 HANG 案例库",
         ], "死锁排查需要线程 dump + 锁顺序分析双向验证。"),
         (27, "REBOOT", [
             "27.1 重启类型分类：kernel panic / native restart / 异常掉电 / 用户操作",
             "27.2 kernel panic：分析流程",
             "27.3 native restart：watchdog / panic 重启",
             "27.4 异常掉电：under-voltage / 异常关机 / 死机",
             "27.5 重启栈分析：last_kmsg / pstore / ramoops / console-ramoops",
             "27.6 重启率治理：监控 / 告警 / 防御",
         ], "重启栈是唯一能告诉你为什么重启的证据，必须保留。"),
         (28, "Kernel Exception", [
             "28.1 Kernel panic：触发条件、分析流程",
             "28.2 Oops 与 BUG：模块 bug 的常见形式",
             "28.3 WARN：内核告警机制",
             "28.4 hung_task / RCU stall / softlockup",
             "28.5 内核日志工具：pstore / ramoops / dmesg / syslog",
             "28.6 内核问题调查方法",
         ], "内核异常 = 必须有 last_kmsg，否则无法定位。"),
         (29, "性能退化与稳定性边界", [
             "29.1 性能基线：冷启动 / 滑动帧率 / 内存水位",
             "29.2 性能回归定位",
             "29.3 稳定性指标：ANR 率 / Crash 率 / 用户感知率",
             "29.4 性能与稳定性的张力（取舍）",
             "29.5 性能治理 vs 稳定性治理",
         ], "性能是稳定性的一部分，但治理策略不同。"),
     ]),
    ("05-卷5-调查方法论与工具链", "卷 5　调查方法论与工具链",
     "怎么找问题——方法论 + 工具。稳定性工程师的瑞士军刀。",
     [
         (30, "稳定性调查方法论", [
             "30.1 现象采集：用户反馈 / 监控告警 / 自动化测试",
             "30.2 现场保留：bugreport / logcat / 复现路径",
             "30.3 假设驱动 vs 数据驱动调查",
             "30.4 根因分析：5 Why / Fishbone / Fault Tree",
             "30.5 修复与回归：最小修复 / 测试覆盖 / 灰度",
             "30.6 复盘文化：Postmortem / 知识库 / Runbook",
         ], "方法论比工具更重要——同样的工具，方法不同结论差 10 倍。"),
         (31, "Perfetto 全栈使用", [
             "31.1 Perfetto 架构：Producer / Consumer / daemon",
             "31.2 抓 trace 实战：ftrace / atrace / heap / memory",
             "31.3 trace 解析：SQL / UI / ftrace_decoder",
             "31.4 实战：ANR 30s trace / 启动 trace / 滑动卡顿 trace",
             "31.5 Perfetto 高级用法：自定义事件 / 远程抓取 / 在线分析",
             "31.6 与 Systrace 的差异",
         ], "Perfetto 是 AOSP 17 默认工具——必须掌握。"),
         (32, "Systrace 与 ftrace", [
             "32.1 Systrace 原理",
             "32.2 ftrace 子系统：function / graph / event / probe",
             "32.3 atrace 用户态埋点",
             "32.4 kernel tracepoints",
             "32.5 systrace.py 工具链",
             "32.6 实战场景",
         ], "Systrace 在 AOSP 17 仍有用——分析老 trace 时必备。"),
         (33, "Dumpsys / Bugreport / DropBox", [
             "33.1 dumpsys 子系统全集（30+ 个）",
             "33.2 bugreport 抓取与解析",
             "33.3 dropbox 机制与日志归档",
             "33.4 Oncall 工具链集成",
             "33.5 dumpsys 在稳定性调查中的应用",
             "33.6 自动化 bugreport 与告警",
         ], "dumpsys + bugreport + dropbox 是稳定性工程师的听诊器。"),
         (34, "Hprof 与内存分析", [
             "34.1 Hprof 格式与生成",
             "34.2 内存泄漏分析：MAT / LeakCanary / Android Studio Profiler",
             "34.3 GC Roots 分析",
             "34.4 Native 内存分析：malloc debug / MTE",
             "34.5 实战案例：常见内存泄漏模式",
             "34.6 内存监控体系",
         ], "Hprof 是定位内存问题的第一工具——但要会读。"),
         (35, "断点与 Native 调试", [
             "35.1 Java 断点调试：Android Studio / JDWP / 断点条件",
             "35.2 Native 调试：gdb / lldb / ndk-stack",
             "35.3 反汇编与符号化：objdump / readelf / addr2line",
             "35.4 core dump 采集与分析",
             "35.5 远程调试",
             "35.6 调试技巧与陷阱",
         ], "断点调试是终极大招——前面工具解决不了才用。"),
         (36, "Oncall 与应急响应", [
             "36.1 Oncall 轮值与值班制度",
             "36.2 故障应急响应流程：P0-P3 分级",
             "36.3 故障复盘：Postmortem / RCA 报告",
             "36.4 知识库与 Runbook",
             "36.5 跨团队协作（内核 / Framework / App）",
             "36.6 Oncall 工具链集成",
         ], "Oncall 流程 = 把个人经验沉淀为团队能力。"),
     ]),
    ("06-卷6-性能工程", "卷 6　性能工程",
     "性能作为独立工程——基线、专项、压测、回归。",
     [
         (37, "性能基线与回归测试", [
             "37.1 性能指标体系",
             "37.2 性能基线：冷启动 / 热启动 / 帧率 / 内存",
             "37.3 性能回归测试：自动化 / 灰度 / 阻断",
             "37.4 性能压测：Monkey / 模糊 / 真实场景",
             "37.5 性能实验室与测试机型",
             "37.6 性能趋势分析",
         ], "没有基线的性能优化 = 盲人摸象。"),
         (38, "启动性能", [
             "38.1 启动时间测量与拆分",
             "38.2 启动优化：Application / 四大组件 / 资源 / 反射 / 类加载",
             "38.3 启动期内存峰值治理",
             "38.4 启动期稳定性保障：白屏 / 闪退",
             "38.5 启动优化案例（5-10 个）",
             "38.6 启动性能监控与告警",
         ], "启动优化是综合工程——Application、四大组件、资源、反射、类加载都要管。"),
         (39, "滑动与渲染性能", [
             "39.1 帧率指标：FPS / Jank / Slow frame",
             "39.2 渲染管线：measure / layout / draw / RenderThread",
             "39.3 滑动卡顿定位",
             "39.4 动画与过渡优化",
             "39.5 复杂布局优化：ConstraintLayout / ViewStub / merge",
             "39.6 滑动性能案例",
         ], "卡顿 80% 在主线程，剩下 20% 在 RenderThread / SurfaceFlinger。"),
         (40, "低配机适配", [
             "40.1 低端机性能挑战",
             "40.2 启动加速：多阶段 / 延迟初始化",
             "40.3 内存压缩：ZRAM / SWAP",
             "40.4 用户感知优化：启动器 / 预加载 / 灰度",
             "40.5 低配机特定问题：OOM / 卡顿 / 闪退",
             "40.6 低配机测试方法",
         ], "低配机 = 性能稳定性的试金石——旗舰机跑得动不代表能跑。"),
         (41, "WebView 与 Hybrid 性能", [
             "41.1 WebView 架构",
             "41.2 Hybrid 性能挑战",
             "41.3 WebView 内存与缓存",
             "41.4 JS Bridge 性能",
             "41.5 常见 WebView 问题：白屏 / 卡顿 / 崩溃",
             "41.6 WebView 性能优化",
         ], "WebView 性能 = 另一个 Android——单独方法论。"),
     ]),
    ("07-卷7-APM与工程治理", "卷 7　APM 与工程治理",
     "稳定性从事后救火提升到事前治理——指标、APM、告警、变更、AI 调试。",
     [
         (42, "稳定性指标体系（SLI / SLO）", [
             "42.1 SLI / SLO / SLA 设计",
             "42.2 稳定性核心指标：ANR 率 / Crash 率 / 性能水位",
             "42.3 用户感知指标：NPS / 客诉 / 评分",
             "42.4 指标采集与计算",
             "42.5 指标治理：避免指标好看但实际差",
             "42.6 指标可视化与告警",
         ], "指标 = 治理的语言，没有指标就没有治理。"),
         (43, "APM 架构与自研实践", [
             "43.1 APM 整体架构：采集 / 传输 / 存储 / 分析 / 告警",
             "43.2 自研 APM 关键模块",
             "43.3 第三方 APM 选型：友盟 / Bugly / Firebase / Sentry",
             "43.4 APM 落地实践",
             "43.5 APM 性能开销控制",
             "43.6 APM 数据应用",
         ], "APM 是稳定性团队的眼睛。"),
         (44, "告警体系与降噪", [
             "44.1 告警分级：紧急 / 重要 / 一般",
             "44.2 告警路由与 oncall 联动",
             "44.3 告警降噪：聚合 / 抑制 / 静默",
             "44.4 告警疲劳治理",
             "44.5 告警体系建设",
             "44.6 告警响应 SLA",
         ], "告警少而准 > 告警多而泛。"),
         (45, "变更管理与灰度发布", [
             "45.1 变更分级",
             "45.2 灰度策略：百分比 / 区域 / 用户群",
             "45.3 灰度监控与回滚",
             "45.4 灰度与稳定性指标",
             "45.5 灰度平台建设",
             "45.6 应急回滚与止血",
         ], "没有灰度 = 没有稳定性。"),
         (46, "AI-Native 调试", [
             "46.1 LLM 辅助日志分析",
             "46.2 自动根因定位",
             "46.3 智能告警聚合",
             "46.4 测试用例自动生成",
             "46.5 AI 在稳定性领域的边界",
             "46.6 AI 调试的局限与未来",
         ], "AI 是工具不是答案——最终判断仍要人做。"),
     ]),
    ("08-卷8-案例实战", "卷 8　案例实战",
     "综合实战——4 大类高频案例，每类 2-3 个真实场景，从现象到根因到修复全链路。",
     [
         (47, "冷启动优化案例", [
             "47.1 案例一：Application 反射调用优化（启动时间 -30%）",
             "47.2 案例二：ContentProvider 初始化优化（启动时间 -20%）",
             "47.3 案例三：启动期主线程 IO 优化（启动时间 -15%）",
             "47.4 案例方法论总结：从基线测量 → 瓶颈定位 → 优化方案 → 回归验证",
         ], "案例 = 把方法论转化为肌肉记忆。"),
         (48, "ANR 调查案例", [
             "48.1 案例一：主线程 Binder 阻塞 ANR",
             "48.2 案例二：ContentProvider 死锁 ANR",
             "48.3 案例三：广播超时 ANR",
             "48.4 案例方法论总结：trace 解读 + 锁分析 + 根因修复",
         ], "ANR 案例学习 = 培养 5 秒看 trace 的肌肉记忆。"),
         (49, "Native Crash 调查案例", [
             "49.1 案例一：第三方 so 库崩溃",
             "49.2 案例二：ART 内部崩溃",
             "49.3 案例三：内存踩踏",
             "49.4 案例方法论总结：Tombstone 解读 + 符号化 + 内存模型",
         ], "Native Crash 案例 = 培养看 Tombstone 找根因的能力。"),
         (50, "性能优化案例", [
             "50.1 案例一：滑动卡顿定位与优化",
             "50.2 案例二：内存泄漏定位与优化",
             "50.3 案例三：冷启动慢专项优化",
             "50.4 案例方法论总结：性能分析 + 优化实施 + 回归验证",
         ], "性能案例 = 把第 38-41 章的理论落地。"),
     ]),
]


def sanitize_dir_name(name: str) -> str:
    """Windows 路径里 / \\ : * ? < > | 都不允许。"""
    for ch in ['/', '\\', ':', '*', '?', '<', '>', '|']:
        name = name.replace(ch, '·')
    return name


def build_chapter_dir_name(ch_num: int, ch_title: str) -> str:
    return f"{ch_num:02d}-{sanitize_dir_name(ch_title)}"


def main():
    created = 0
    for vol_dir, vol_title, vol_lead, chapters in VOLUMES:
        vol_path = REPO_ROOT / vol_dir
        vol_path.mkdir(parents=True, exist_ok=True)
        # 写卷级 index.md
        vol_index = f"""# {vol_title}

> **本卷定位**：{vol_lead}

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
"""
        for ch_num, ch_title, _subs, _summary in chapters:
            vol_index += f"| 第 {ch_num} 章 | {ch_title} | 🚧 撰写中 |\n"
        vol_index += f"""
---

## 章节目录（详细）

"""
        for ch_num, ch_title, subs, summary in chapters:
            vol_index += f"### 第 {ch_num} 章　{ch_title}\n\n"
            for sub in subs:
                vol_index += f"- {sub}\n"
            vol_index += f"\n> **本章小结**：{summary}\n\n"
        (vol_path / "index.md").write_text(vol_index, encoding="utf-8")
        created += 1

        # 建 50 个章目录 + 章级 index.md
        for ch_num, ch_title, subs, summary in chapters:
            ch_dir_name = build_chapter_dir_name(ch_num, ch_title)
            ch_path = vol_path / ch_dir_name
            ch_path.mkdir(parents=True, exist_ok=True)
            ch_index = f"""# 第 {ch_num} 章　{ch_title}

> **所属卷**：{vol_title}
> **章定位**：{summary}
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

"""
            for sub in subs:
                ch_index += f"- {sub}\n"
            ch_index += f"""
## 本章小结

{summary}

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
"""
            (ch_path / "index.md").write_text(ch_index, encoding="utf-8")
            created += 1

    print(f"[OK] created {created} files")
    print(f"     8 volumes: {REPO_ROOT}/01-卷1-.../ to 08-卷8-...")
    print(f"     50 chapters: 01-50 with index.md")
    print(f"     8 volume-level index.md")
    print(f"     50 chapter-level index.md")
    print()
    print("[NOTE] Existing 8 modules (01-Mechanism / 02-Symptom / ...) are NOT touched.")
    print("       prepare_web_docs.py and mkdocs.yml are NOT modified.")
    print("       Run mkdocs build to verify existing build still works.")


if __name__ == "__main__":
    main()
