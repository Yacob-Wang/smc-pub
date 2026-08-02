# 卷 3　核心机制（横跨 AOSP 分层）

> **本卷定位**：打破 AOSP 分层——Binder / 进程 / 内存 / IO / 显示 等主题横跨 Kernel、Native、Runtime、Framework、App。稳定性问题往往需要全链路排查。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 12 章 | Binder IPC 深度 | 🚧 撰写中 |
| 第 13 章 | 进程与生命周期 | 🚧 撰写中 |
| 第 14 章 | 线程与 Handler 消息机制 | 🚧 撰写中 |
| 第 15 章 | 内存管理全链路 | 🚧 撰写中 |
| 第 16 章 | IO 与存储 | 🚧 撰写中 |
| 第 17 章 | 网络与连接 | 🚧 撰写中 |
| 第 18 章 | 显示与渲染 | 🚧 撰写中 |
| 第 19 章 | 电源与续航 | 🚧 撰写中 |
| 第 20 章 | ART 运行时 | 🚧 撰写中 |
| 第 21 章 | 输入系统 | 🚧 撰写中 |

---

## 章节目录（详细）

### 第 12 章　Binder IPC 深度

- 12.1 Binder 驱动：mmap / 引用计数 / 线程池（红黑树）
- 12.2 Binder 协议：BC/BR 命令 / Parcel / flat_binder_object
- 12.3 Java 框架层：AIDL / ServiceManager / deathRecipient
- 12.4 oneway / parcelable / Binder 池大小
- 12.5 Binder 调用链路：客户端 → 驱动 → 服务端
- 12.6 Binder 卡死排查：binder 线程数 / oneway 阻塞 / 死锁

> **本章小结**：ANR 30% 根因是 Binder 阻塞。

### 第 13 章　进程与生命周期

- 13.1 进程模型：fork / vfork / clone / CGroup
- 13.2 进程优先级：oom_score_adj / cgroup / ProcessList
- 13.3 进程间通信总览：Binder / Socket / SharedMemory / Handler / ContentProvider
- 13.4 进程生命周期：启动 / 优先级 / 杀进程策略 / LMK (Low Memory Killer)
- 13.5 进程退出：Exit / Tombstone / Process.kill / ANR 杀进程
- 13.6 进程崩溃与恢复：CrashHandler / 进程拉起策略

> **本章小结**：进程优先级设置错误 = 关键进程被 LMK 误杀。

### 第 14 章　线程与 Handler 消息机制

- 14.1 pthread / HandlerThread / Java 线程模型
- 14.2 Handler / Looper / MessageQueue 原理
- 14.3 消息屏障（Sync Barrier）：Vsync 信号如何优先处理
- 14.4 IdleHandler / 延迟消息 / 定时器
- 14.5 卡帧与 ANR 原理：主线程消息处理超时
- 14.6 IdleHandler 与 Choreographer 协同

> **本章小结**：主线程的一切都走 Handler——卡顿排查先看主线程消息队列。

### 第 15 章　内存管理全链路

- 15.1 内核分配器：kmalloc / vmalloc / slab / page
- 15.2 进程虚拟内存：VMA / mmap / 缺页 / 写时复制
- 15.3 ART 堆：TLAB / Concurrent GC / 引用类型 / 卡片表
- 15.4 Framework 内存治理：AMS / TrimMemory / ComponentCallbacks2
- 15.5 OOM 与低内存：LMK / OOM Killer / PSI / memory pressure
- 15.6 内存泄漏排查：hprof / LeakCanary 原理 / GC roots / MAT

> **本章小结**：内存问题 = 全栈，单独看任何一层都不够。

### 第 16 章　IO 与存储

- 16.1 VFS 与文件系统：ext4 / f2fs / erofs
- 16.2 Page Cache 与 IO 调度：CFQ / deadline / bfq
- 16.3 存储框架：StorageManager / Volume / FUSE / SDCardFS
- 16.4 ContentProvider 数据访问
- 16.5 数据库：SQLite / Room / 文件锁
- 16.6 IO 性能瓶颈定位：iostat / atrace / IO hang

> **本章小结**：启动期 70% 卡顿根因是主线程 IO。

### 第 17 章　网络与连接

- 17.1 网络协议栈：TCP / UDP / socket
- 17.2 ConnectivityManager / NetworkAgent / NetworkFactory
- 17.3 WiFi / 移动数据 / VPN / 代理
- 17.4 Bluetooth / NFC / GPS
- 17.5 网络性能与耗电：网络切换 / 信号弱 / DNS 慢
- 17.6 网络类 ANR 调查：ConnectivityService / DataCall / Socket

> **本章小结**：网络 ANR ≠ 网络慢，可能是 ConnectivityService 阻塞。

### 第 18 章　显示与渲染

- 18.1 SurfaceFlinger 与 BufferQueue：跨进程 Buffer 传递
- 18.2 Choreographer 与 VSYNC：60Hz / 90Hz / 120Hz 调度
- 18.3 View 体系：measure / layout / draw / invalidate
- 18.4 RenderThread 与 HWUI：硬件加速
- 18.5 卡顿与掉帧分析：Jank / Slow frame / Stutter
- 18.6 屏幕闪烁 / 黑屏 / 花屏调查

> **本章小结**：卡顿 50% 根因在主线程，30% 在 RenderThread，20% 在 SurfaceFlinger。

### 第 19 章　电源与续航

- 19.1 PowerManager 与 WakeLock：保持唤醒与休眠
- 19.2 Doze 模式：深度休眠机制
- 19.3 Battery Historian 与耗电分析
- 19.4 后台限制：JobScheduler / WorkManager / Firebase Job Dispatcher
- 19.5 异常掉电：内核 / Modem / 电池 / 充电 IC
- 19.6 续航优化方法

> **本章小结**：续航问题需要硬件 + 软件 + 行为三方联合排查。

### 第 20 章　ART 运行时

- 20.1 Dex 编译：AOT / JIT / 解释器 / Cloud Profile
- 20.2 类加载与反射：ClassLoader / Method / Field
- 20.3 垃圾回收：标记清除 / 并发 / 引用类型 / Finalize
- 20.4 JNI 与 Native 桥接：JNIEnv / RegisterNatives
- 20.5 启动类加载优化：Profile / Baseline Profile / dex2oat
- 20.6 ART 内部崩溃调查（AOSP 17 ART17）

> **本章小结**：ART 是 Java 性能与稳定性的核心——20% 的内容对应 50% 的问题。

### 第 21 章　输入系统

- 21.1 InputManagerService 架构
- 21.2 输入事件流：InputReader → InputDispatcher → 窗口
- 21.3 触摸事件分发：ViewRootImpl → DecorView → ViewGroup → View
- 21.4 输入 ANR 原理：5s input dispatch timeout
- 21.5 输入卡顿与延迟
- 21.6 焦点窗口与无焦点 ANR

> **本章小结**：input ANR 90% 是主线程 / Binder 阻塞，不是 input 系统本身问题。

