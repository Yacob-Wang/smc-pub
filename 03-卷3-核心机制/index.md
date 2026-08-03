# 卷 3　核心机制（横跨 AOSP 分层）

> **本卷定位**：**打破 AOSP 分层**——Binder / 进程 / 内存 / IO / 显示等主题横跨 Kernel、Native、Runtime、Framework、App。本卷是全书的**机制字典**，供后续症状章反查。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 12 章 | Binder IPC 深度 | 🚧 撰写中 |
| 第 13 章 | 进程与生命周期 | 🚧 撰写中 |
| 第 14 章 | 线程与 Handler 消息机制 | 🚧 撰写中 |
| 第 15 章 | 内存管理全链路 | 🚧 撰写中 |
| 第 16 章 | IO 与存储 | 🚧 撰写中 |
| 第 17 章 | 网络与连接 | 🚧 撰写中 |
| 第 18 章 | 输入系统 | 🚧 撰写中 |
| 第 19 章 | 显示与渲染 | 🚧 撰写中 |
| 第 20 章 | ART 运行时 | 🚧 撰写中 |
| 第 21 章 | 电源与续航 | 🚧 撰写中 |

---

## 章节详细

### 第 12 章　Binder IPC 深度

> Android 唯一的通用跨进程通信机制——理解 Binder 才能理解绝大多数跨进程卡死。

- 12.1 Binder 驱动：mmap / 引用计数 / 线程池
- 12.2 Binder 协议：BC / BR 命令 / Parcel / flat_binder_object
- 12.3 Java 框架层：AIDL / ServiceManager / DeathRecipient
- 12.4 调用模式：同步 / oneway / 事务大小限制
- 12.5 完整调用链路：客户端 → 驱动 → 服务端 → 返回
- 12.6 Binder 卡死排查：线程池耗尽 / oneway 堆积 / 跨进程死锁

**本章小结**：Binder 阻塞是 ANR 的头号跨进程根因——看 ANR trace 先确认主线程是否卡在 Binder 上。

### 第 13 章　进程与生命周期

> 进程是 Android 的资源分配单位——理解进程模型才能理解 OOM、LMK 与杀进程。

- 13.1 进程创建：fork / vfork / clone / cgroup 归属
- 13.2 进程优先级：oom_score_adj / ProcessList / cgroup 分组
- 13.3 四大组件与进程生命周期的绑定关系
- 13.4 杀进程策略：LMK / AMS 主动杀 / 用户清理
- 13.5 进程退出：do_exit / Tombstone / 资源回收时序
- 13.6 进程崩溃与恢复：CrashHandler / 拉起策略 / 保活边界

**本章小结**：进程优先级配错 = 关键进程被 LMK 误杀，且现场往往只剩一行 kill 日志。

### 第 14 章　线程与 Handler 消息机制

> Handler 是 Android UI 线程的骨架——理解消息机制才能理解主线程卡顿与 ANR。

- 14.1 线程模型：pthread / Java Thread / HandlerThread
- 14.2 Handler / Looper / MessageQueue 原理
- 14.3 同步屏障（Sync Barrier）：VSYNC 消息如何插队
- 14.4 IdleHandler / 延迟消息 / 定时器
- 14.5 主线程超时如何演变为 ANR
- 14.6 消息队列的可观测性：Looper 监控 / 慢消息采样

**本章小结**：主线程的一切都走 Handler——卡顿排查的第一站永远是主线程消息队列。

### 第 15 章　内存管理全链路

> 内存是最复杂的稳定性领域——Kernel 分配、ART 堆、Framework 治理三层协同。**ART 内部 GC 算法见第 20 章**，本章讲跨层协作。

- 15.1 内核分配器：kmalloc / vmalloc / slab / page
- 15.2 进程虚拟内存：VMA / mmap / 缺页 / 写时复制
- 15.3 Native 堆：bionic / scudo 分配器
- 15.4 ART 堆与系统内存的边界：堆增长如何影响系统水位
- 15.5 Framework 内存治理：AMS / onTrimMemory / ComponentCallbacks2
- 15.6 低内存机制：LMK / OOM Killer / PSI / memory pressure

**本章小结**：内存问题必须跨层看——只看 ART 堆会漏掉 Native 增长，只看进程会漏掉系统水位。

### 第 16 章　IO 与存储

> IO 影响启动速度、应用响应与卡顿——理解全栈 IO 才能定位 IO 类阻塞。

- 16.1 VFS 与文件系统：ext4 / f2fs / erofs
- 16.2 Page Cache 与 IO 调度
- 16.3 存储框架：StorageManager / Volume / FUSE
- 16.4 数据库：SQLite / Room / 文件锁竞争
- 16.5 ContentProvider 的跨进程数据访问
- 16.6 IO 瓶颈定位：iostat / atrace / IO hang 的特征

**本章小结**：启动期与冷路径的卡顿，主线程 IO 是最高频的单一根因。

### 第 17 章　网络与连接

> 网络是移动端最大的环境变量——弱网导致的 ANR 与卡死需要专门的判定方法。

- 17.1 网络协议栈：TCP / UDP / socket
- 17.2 ConnectivityService / NetworkAgent / 网络选路
- 17.3 WiFi / 移动数据 / VPN / 代理的切换时序
- 17.4 网络与耗电：信号弱 / 频繁重连 / DNS 超时
- 17.5 网络类 ANR 的判定：是网络慢还是服务阻塞
- 17.6 网络问题的现场采集

**本章小结**：网络 ANR ≠ 网络慢——大量案例实际是 ConnectivityService 或应用层锁阻塞。

### 第 18 章　输入系统

> 输入是 ANR 的最高频触发路径——理解 InputDispatcher 才能读懂 input ANR。**与第 19 章构成「触摸 → 首帧」完整交互链路。**

- 18.1 InputManagerService 架构
- 18.2 输入事件流：EventHub → InputReader → InputDispatcher → 窗口
- 18.3 InputChannel 与跨进程投递
- 18.4 触摸事件分发：ViewRootImpl → DecorView → ViewGroup → View
- 18.5 输入 ANR 原理：5s dispatch timeout 的判定条件
- 18.6 焦点窗口与「无焦点窗口」ANR

**本章小结**：input ANR 约 90% 的根因是主线程或 Binder 阻塞，而非输入系统本身——input 只是最先报警的那个。

### 第 19 章　显示与渲染

> 显示是用户感知的终点——本章讲**机制**（帧是怎么产生的），卡顿优化实践见卷 6 第 39 章。

- 19.1 SurfaceFlinger 与 BufferQueue：跨进程 Buffer 传递
- 19.2 VSYNC 与 Choreographer：60 / 90 / 120Hz 调度
- 19.3 View 体系：measure / layout / draw / invalidate
- 19.4 RenderThread 与 HWUI：硬件加速管线
- 19.5 一帧的完整时序：从 input 到 present
- 19.6 显示异常：黑屏 / 闪屏 / 花屏的机制成因

**本章小结**：一帧要穿过 App 主线程、RenderThread、SurfaceFlinger 三个环节——任何一环超时都表现为掉帧。

### 第 20 章　ART 运行时

> Java 应用的运行时——DEX 编译、类加载、GC、JNI 都直接影响性能与稳定性。

- 20.1 Dex 与编译：AOT / JIT / 解释器 / Cloud Profile
- 20.2 类加载与反射：ClassLoader / Method / Field
- 20.3 垃圾回收：CMS / CC / Generational CC / 引用类型
- 20.4 GC 的调度与触发：GcCause 全枚举
- 20.5 JNI 与 Native 桥接：JNIEnv / RegisterNatives / 局部引用表
- 20.6 ART 内部崩溃与 SignalCatcher（ANR trace 的生成者）

**本章小结**：ART 是 Java 侧性能与稳定性的核心——20% 的 ART 知识对应 50% 的 Java 侧问题。

### 第 21 章　电源与续航

> 稳定性的横切主题——后台耗电、待机掉电、充电异常都需要「硬件 + 软件 + 用户行为」三方联合排查。

- 21.1 PowerManager 与 WakeLock
- 21.2 Doze 与 App Standby：深度休眠机制
- 21.3 后台执行限制：JobScheduler / WorkManager / 前台服务
- 21.4 耗电分析：Battery Historian / batterystats
- 21.5 异常掉电：内核 / Modem / 电池 / 充电 IC
- 21.6 续航优化与稳定性的取舍

**本章小结**：续航问题极少是单一原因——必须同时看唤醒源、后台任务与硬件状态。
