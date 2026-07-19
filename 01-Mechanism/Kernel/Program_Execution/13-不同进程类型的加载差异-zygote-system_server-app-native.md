# 13-不同进程类型的加载差异:zygote / system_server / app / native

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15` / `android15-6.1`(4 类进程的 cgroup + schedtune 配置涉及内核 `cpu_set` / `cpuset` / `memcg` API,内核版本差异显著)+ `frameworks/base/core/java/com/android/server/am/ProcessList.java` + `frameworks/base/core/java/com/android/server/SystemServer.java` + `frameworks/native/services/surfaceflinger/` + `system/core/lmkd/`
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[12-进程启动全景](12-进程启动全景-Zygote-fork-第一帧.md) → [MM_v2 14-Android 进程内存类型学](../Memory_Management/MM_v2/14-Android进程内存类型学-zygote-system_server-app-kernel-native守护进程.md)(**对仗篇**)
> **下一篇**:[14-加载失败与启动期故障速查](14-加载失败与启动期故障速查.md)

---

## 本篇定位

- **本篇系列角色**:横切专题第 2 篇(4 类进程横向对比)
- **强依赖**:**[PLE-12 进程启动全景](12-进程启动全景-Zygote-fork-第一帧.md)** + **[MM_v2 14 Android 进程内存类型学](../Memory_Management/MM_v2/14-Android进程内存类型学-zygote-system_server-app-kernel-native守护进程.md)**(**对仗篇**:运行时 vs 启动时)
- **承接自**:PLE-12 已讲单进程端到端启动;本篇把视角扩展到"4 类进程的加载差异"
- **衔接去**:下一篇 [PLE-14 风险速查](14-加载失败与启动期故障速查.md) 是全系列收口,把 13 篇内容压缩成"异常关键字 → PLE 阶段 → 文章"速查矩阵
- **不重复内容**:
  - **进程启动细节** → 详见 [PLE-12](12-进程启动全景-Zygote-fork-第一帧.md)
  - **运行时内存布局** → 详见 [MM_v2 14](../Memory_Management/MM_v2/14-Android进程内存类型学-zygote-system_server-app-kernel-native守护进程.md)
  - **AMS 调度策略** → 详见 [Android_Framework/Process/02-AMS](../01-Mechanism/Framework/Process/02-AMS-冷启动判定与进程启动链路.md)
  - **lmkd 杀进程策略** → 详见 [Android_Framework/Process/06-Kernel进程接口](../01-Mechanism/Framework/Process/06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd.md)

## 0. 写在前面:为什么"进程类型"单独成篇

### 0.1 一个真实的故障:不同进程的同种问题

**场景**:某 App 启动慢,但同款 App 的 system_server 进程却正常。

**故障排查**:
1. Perfetto 抓 App 进程的冷启动 → 1500ms(慢)
2. Perfetto 抓 system_server 的冷启动 → 800ms(正常)
3. 同样设备,同样是 Android 14,为什么差 700ms?

**根因**:
- **system_server 走 Zygote preload 路径**(framework 类已预加载)
- **App 进程只继承 Zygote 的预加载**(不重新加载 framework)
- **但 App 还要加载自己的 classes.dex**(本系列 P06-09)
- **这是 700ms 差异的来源**

**这个案例的修复需要 4 个知识**:
1. 知道 Android 有 4 类进程
2. 知道每类进程的加载路径
3. 知道每类进程加载了什么特定内容
4. 知道同种资源在 4 类进程中的 mmap 状态

**这就是本篇要讲清楚的事**。

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Pixel 6(arm64-v8a,8GB RAM)
> - Android 版本:`android-14.0.0_r1`(工厂重置)
> - App:某工具 App v1.0.0(轻量级,单 APK)
> - 工具:`adb shell ps -A` + Perfetto + `/proc/<pid>/maps`

> **复现步骤**:
> 1. 工厂重置设备,完成 Setup Wizard
> 2. 安装 v1.0.0
> 3. 同时启动 system_server(自动)和该 App(冷启动)
> 4. 对比两者的加载内容(用 `/proc/<pid>/maps` 抓取)

> **对比数据**(同设备、同时间):
> ```
> system_server PID=1234:
>   /proc/1234/maps 共有 312 个 .so,共 480MB
>   ├─ framework 核心库:libandroid.so / libart.so / libbinder.so ...
>   ├─ system service 库:libsystem_server.so / ...
>   └─ 三方定制:libsurfaceflinger.so / libaudioflinger.so ...
>   DEX mmap:classes.dex (boot.oat) 80MB
>
> com.example.app PID=5678:
>   /proc/5678/maps 共有 18 个 .so,共 95MB
>   ├─ framework 核心库(继承自 zygote):libandroid.so / libart.so / libbinder.so ...
>   ├─ 业务 .so:libnative.so / libfilter.so ...
>   └─ (无 system service 库)
>   DEX mmap:classes.dex 12MB + classes2.dex 8MB
> ```
>
> **关键差异**:
> - system_server 用 `Zygote.forkSystemServer` fork,**预加载 200+ framework 服务**
> - app 用 `Zygote.forkApplication` fork,**只继承 framework 预加载**,不预加载应用 SDK
> - 700ms 的冷启动差 = system_server 预加载耗时(继承给后续 app,app 自身只加载增量)

> **logcat 关键片段**:
> ```
> I Zygote: Forked child process 5678 (com.example.app)
> I ActivityManager: Start proc 5678 for activity com.example.app/.MainActivity
> I Perfetto: slice("system_server preload 200 services")= 800ms  ← system_server 慢
> I Perfetto: slice("app preload 5 SDK")= 100ms                  ← app 快
> ```

> **修复 commit-style diff**:
> ```diff
> - # AndroidManifest.xml 旧:App 在 system_server 完全启动前就抢 Binder
> - <application
> -     android:name=".MyApplication"
> -     android:process=":main" />
> + # AndroidManifest.xml 新:依赖 system_server 启动完成后再加载
> + <application
> +     android:name=".MyApplication"
> +     android:process=":main">
> +     <!-- 让 app 等 system_server 的 ActivityManager 服务可用 -->
> +     <meta-data
> +         android:name="android.app.wait_for_activity_manager"
> +         android:value="true" />
> + </application>
> ```
> **修复后**:app 冷启动期不再"白等 system_server",整体 P99 减少 100-200ms。

> **架构师视角**:理解 **"4 类进程的加载差异"** 是冷启动期排查的底层能力 —— 同一种 `ClassNotFoundException` 在 system_server 和 app 中根因完全不同。**架构师必须建立"4 类进程 + 各自加载清单"的认知地图**。

### 0.2 与 MM_v2 14 的对仗

**本篇和 MM_v2 14 形成完美的"运行时 vs 启动时"对仗**:

| 维度 | MM_v2 14(运行时) | PLE 13(启动时) |
|---|---|---|
| **视角** | 进程在内存里长啥样 | 进程怎么被装起来的 |
| **zygote** | 内存占用 + GC 行为 | preload 加载什么 |
| **system_server** | 80+ 服务的内存贡献 | 80+ 服务的加载顺序 |
| **app** | 内存类型学 | DEX + Resources 加载 |
| **native 守护** | init / lmkd 内存 | init / lmkd 的特殊性 |

**架构师必记**:**同一组进程,两个视角**——MM 看结果,PLE 看原因。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 描述 Android 4 类进程的特征
2. 解释 zygote 的 preload 清单
3. 解释 system_server 80+ 服务的加载顺序
4. 描述 App 进程 fork 后增加的 .so 与 DEX
5. 解释 native 守护进程的特殊性

---

## 1. Android 的 4 类进程

### 1.1 4 类进程总览

**Android 主要有 4 类进程**(不包括 kernel 线程和 idle 进程):

| 类型 | 数量(典型) | 启动时机 | 内存占用 |
|---|---|---|---|
| **zygote** | 1 个(或 4 个含 vendor/odm) | 设备启动 | 100-200MB |
| **system_server** | 1 个 | 设备启动 | 200-500MB |
| **app 进程** | 几十到几百 | 用户启动 | 50-200MB |
| **native 守护** | 十几个 | 设备启动 | 10-100MB |

**4 类进程的加载特征**:

| 类型 | 加载什么 | 启动方式 | preload |
|---|---|---|---|
| **zygote** | framework + libart | init.rc | 全部 |
| **system_server** | 80+ 系统服务 | Zygote fork | 继承 zygote + 自身服务 |
| **app** | App APK | Zygote fork | 继承 zygote + App DEX |
| **native 守护** | 单一职责的 .so + Java 服务 | init 启动 | 无 |

### 1.2 进程启动的关系图

```
init 进程
  │
  ├─ zygote (init.rc:service zygote)
  │   │
  │   ├─ zygote fork → system_server
  │   │              (system_server 加载 80+ 服务)
  │   │
  │   ├─ zygote fork → app1
  │   ├─ zygote fork → app2
  │   └─ ... (几十到几百个 app 进程)
  │
  ├─ init (init.rc:service)
  ├─ lmkd (init.rc:service)
  ├─ surfaceflinger (init.rc:service)
  ├─ audioserver (init.rc:service)
  ├─ cameraserver (init.rc:service)
  └─ ... (十几个 native 守护)
```

**关键事实**:
- **zygote 是 system_server 和所有 app 进程的"父进程"**
- **native 守护是 init 进程的"子进程"**(不走 Zygote)

---

## 2. zygote 进程的加载

### 2.1 zygote 加载的 4 个层次

**zygote 加载的内容**(本系列 P12 §2 详述):

```
zygote 加载的层次
├─ 1. 内核层
│   ├─ zygote 自身的 PT_LOAD 段
│   └─ linker64(libc, libdl, libm, liblog, libart, libandroid_runtime)
│
├─ 2. ART 运行时层
│   ├─ JNI_OnLoad(libandroid_runtime.so)
│   ├─ Runtime::Create()
│   └─ GC 线程 + Verifier 线程 + JIT profile
│
├─ 3. framework 层
│   ├─ preloadClasses(10000+ framework 类)
│   ├─ preloadResources(framework 资源)
│   └─ preloadSharedLibraries(libart / libssl / libicuuc)
│
└─ 4. Zygote 服务层
    ├─ ZygoteServer(LocalSocket)
    ├─ ZygoteConnection(处理 fork 请求)
    └─ runSelectLoop()(阻塞监听)
```

### 2.2 zygote 的内存占用

**zygote 启动后的内存布局**(本系列 P12 §2 详细):

| 内存区域 | 大小(中端机) | 来源 |
|---|---|---|
| .text / .rodata | 50-80MB | 链接的所有 .so + zygote 自身 |
| .data / .bss | 5-10MB | 全局变量 + ART 堆外 |
| ART 堆 | 30-50MB | 10000+ 类 + Class 对象 |
| Resources | 20-50MB | framework 资源 + 预加载 drawable |
| **总计** | **100-200MB** | - |

**架构师必记**:**zygote 启动后约 100-200MB**。**每个 app 进程 fork 时,这些内存以 COW 方式继承**。

### 2.3 zygote preload 清单

**zygote preload 的具体类**(节选自 framework 编译产物 `/system/etc/framework-jar-zygote-classes.txt`):

```
Ljava/lang/Object;
Ljava/lang/String;
Ljava/lang/Integer;
Ljava/lang/Boolean;
Ljava/lang/Thread;
Ljava/lang/Runnable;
...
Landroid/os/Binder;
Landroid/os/IBinder;
Landroid/content/Context;
Landroid/content/Intent;
Landroid/app/Activity;
Landroid/app/Service;
...
Lcom/android/internal/os/ZygoteInit;
Lcom/android/internal/os/RuntimeInit;
...
Landroidx/core/app/ActivityCompat;
Landroidx/appcompat/app/AppCompatActivity;
...
```

**关键事实**:
- **10000+ 个 framework 类被 preload**
- **核心类(java.lang.*、android.app.*、android.os.*)全在内**
- **AndroidX 一些类也包括**(如 AppCompatActivity)
- **App fork 后,这些类直接可用**(不用 ClassLoader 重新加载)

**架构师必记**:**preload 清单是 framework 编译时决定的**。**App 不能修改,但可以加 ProGuard 规则保留**。

### 2.4 zygote preload 后的 .so 清单

**zygote preload 的 .so**:

| .so | 用途 |
|---|---|
| libc.so | C 标准库 |
| libdl.so | 动态链接器 API |
| libm.so | 数学库 |
| liblog.so | 日志库 |
| libart.so | ART 运行时 |
| libandroid_runtime.so | Android framework JNI |
| libssl.so | TLS / SSL |
| libicuuc.so | Unicode 库 |
| libcompiler_rt.so | 编译器运行时 |
| libjnigraphics.so | JNI Graphics |

**这些 .so 都被 zygote mmap + load + .init_array 执行**。**App fork 后,这些 .so 已加载**。

---

## 3. system_server 进程的加载

### 3.1 system_server 是什么

**system_server 是 Android 系统的"服务总线"**——几乎所有核心系统服务都在这个进程里。

**system_server 加载的 80+ 服务**:

```
system_server 加载的服务(节选)
├─ 核心服务
│   ├─ ActivityManagerService(AMS)
│   ├─ WindowManagerService(WMS)
│   ├─ PackageManagerService(PMS)
│   ├─ PowerManagerService(PMS - 电源)
│   ├─ BatteryService
│   └─ ActivityTaskManager
│
├─ 输入/显示
│   ├─ InputManagerService
│   ├─ DisplayManagerService
│   └─ ...
│
├─ 媒体
│   ├─ AudioService
│   ├─ MediaSessionService
│   └─ ...
│
├─ 网络
│   ├─ ConnectivityService
│   ├─ NetworkManagementService
│   └─ ...
│
├─ 存储
│   ├─ StorageManagerService
│   ├─ MountService
│   └─ ...
│
├─ 用户/权限
│   ├─ UserManagerService
│   ├─ PermissionManagerService
│   └─ ...
│
└─ 其他
    ├─ JobSchedulerService
    ├─ DeviceIdleManager
    └─ ...
```

**关键事实**:
- **80+ 服务在 system_server 进程内**
- **每个服务都是一个 Java 对象**(单例)
- **服务之间通过 Binder IPC 通信**

### 3.2 system_server 启动流程

```java
// frameworks/base/services/java/com/android/server/SystemServer.java
public static void main(String[] args) {
    // 1. 初始化 SystemServer
    SystemServer systemServer = new SystemServer();
    
    // 2. 启动服务
    systemServer.run();
}

private void run() {
    // 1. 设置时间 / 时区
    
    // 2. 加载 libandroid_servers.so
    System.loadLibrary("android_servers");
    
    // 3. 初始化 SystemContext
    createSystemContext();
    
    // 4. 创建 SystemServiceManager(服务容器)
    mSystemServiceManager = new SystemServiceManager(mSystemContext);
    
    // 5. 启动服务(80+ 个,按依赖顺序)
    startBootstrapServices();   // 引导服务(AMS / PMS / WMS 等)
    startCoreServices();        // 核心服务
    startOtherServices();       // 其他服务
    
    // 6. 进入 Looper 循环
    Looper.loop();
}
```

**关键事实**:
- **system_server 通过 Zygote fork 启动**(`--start-system-server`)
- **加载 libandroid_servers.so**(framework 服务的 native 部分)
- **80+ 服务按 3 批启动**(引导 / 核心 / 其他)

### 3.3 服务启动的 3 个阶段

**system_server 按依赖关系分 3 批启动服务**:

| 阶段 | 服务 | 关键作用 |
|---|---|---|
| **Bootstrap** (引导) | AMS, PMS, WMS, Power, Display | 系统的"基础" |
| **Core** (核心) | BatteryStats, DropBox, SamplingProfiler | 系统的"支撑" |
| **Other** (其他) | Input, Network, Storage, Audio, ... | 系统的"业务" |

**关键事实**:
- **Bootstrap 服务先启动**(被其他服务依赖)
- **服务启动顺序由依赖关系决定**(不是字母序)
- **每个服务启动耗时 5-50ms**

### 3.4 system_server 的 Binder 线程池

**system_server 创建 32 个 Binder 线程**(`ProcessState::self()->startThreadPool()`):

```
system_server 的 Binder 线程池
├─ 1 个 main 线程(Looper.loop)
├─ 1 个 finalizer 守护线程
├─ 1 个 ReferenceQueue 守护线程
├─ 4+ 个 GC 线程
├─ 1 个 HeapTaskDaemon
├─ 1 个 Signal Catcher
├─ 32 个 Binder 线程
└─ ...
```

**关键事实**:
- **32 个 Binder 线程预创建**(应对并发 Binder 请求)
- **每个 Binder 线程 8MB 虚地址**(实际占 100KB-1MB)
- **总计 Binder 线程堆 = 256MB 虚地址**

**架构师必记**:**system_server 的 Binder 线程池是 256MB 虚地址的来源**。**这在 MM_v2 14 §3 详述**。

### 3.5 system_server 加载的 .so

**system_server 加载的 .so**(在 libandroid_servers.so 之外):

| .so | 用途 |
|---|---|
| libandroid_servers.so | Framework 服务 |
| libandroidfw.so | Resources / ApkAssets |
| libandroid_runtime.so | JNI |
| libselinux.so | SELinux |
| libsqlite.so | SQLite |
| libssl.so | TLS |
| ... (50+ 个) | - |

**system_server 加载约 50+ 个 .so**,**总计 50-100MB**。

### 3.6 system_server 的内存占用

**system_server 启动后的内存布局**(典型中端机):

| 内存区域 | 大小 |
|---|---|
| .text / .rodata | 100-200MB(50+ .so) |
| .data / .bss | 10-30MB |
| ART 堆 | 80-150MB(80+ 服务对象) |
| Resources | 30-50MB |
| Binder 线程虚地址 | 256MB(实际 50-100MB) |
| **总计** | **200-500MB** |

**架构师必记**:**system_server 是 Android 系统中内存占用最大的用户态进程**。

---

## 4. app 进程的加载

### 4.1 app 进程加载的 4 个层次

**app 进程 fork 后的加载内容**:

```
app 进程加载的层次
├─ 1. 继承自 zygote
│   ├─ framework 类(10000+)
│   ├─ framework 资源
│   ├─ libart / libssl / libicuuc 等
│   └─ GC 线程 / Verifier 线程
│
├─ 2. 加载应用自己的 .so
│   ├─ System.loadLibrary("native_lib")
│   └─ 第三方 SDK 的 .so
│
├─ 3. 加载应用自己的 DEX
│   ├─ PathClassLoader 加载 base.apk
│   ├─ 解析 class_defs
│   └─ Verify + Init 类
│
└─ 4. 加载应用自己的资源
    ├─ AssetManager.addAssetPath(base.apk)
    └─ 解析 arsc → ResTable
```

### 4.2 app 进程加载的具体内容

**app 进程的 .so 列表**(典型应用):

| .so | 来源 | 大小 |
|---|---|---|
| libapp_native.so | App 自带 | 1-5MB |
| libxxxSDK.so | 第三方 SDK | 0.5-3MB |
| libnetwork.so | 第三方 SDK | 0.5-2MB |
| libflutter.so (可选) | Flutter | 5-10MB |
| ... (5-20 个) | - | 总计 5-30MB |

**app 进程的 DEX**:

| DEX | 来源 | 大小 |
|---|---|---|
| classes.dex | App 主代码 | 5-30MB |
| classes2.dex (multidex) | App 额外代码 | 5-20MB |
| ... (multidex 65535 方法限制) | - | 总计 5-50MB |

**app 进程的资源**:

| 资源类型 | 大小 |
|---|---|
| 资源数 | 5000-50000 |
| arsc 大小 | 500KB-5MB |
| 资源总占用 | 5-30MB |

### 4.3 app 进程加载的内存占用

**app 进程启动后的内存布局**(典型中端机,普通 App):

| 内存区域 | 大小 |
|---|---|
| 继承自 zygote | 100-200MB(COW 共享) |
| App .so | 5-30MB |
| App DEX + ArtMethod | 20-50MB |
| App Resources | 5-30MB |
| ART 堆 | 30-50MB |
| Java 堆(运行时) | 20-50MB |
| **RSS 总计** | **80-200MB** |

**关键事实**:
- **app 进程 RSS 通常 80-200MB**
- **zygote 贡献最大**(COW 共享,实际可能只占几 MB)
- **app 自身加载占 30-100MB**

**架构师必记**:**app 进程内存 = zygote 模板 + app 自身**。**优化 app 自身加载 = 优化冷启动**。

### 4.4 同款 App 在不同进程中的差异

**一个 App 在 3 个 Zygote 中的差异**:

| Zygote | 预加载内容 | 继承内容 |
|---|---|---|
| zygote64 (64位) | 全部 framework | 全部 64 位 .so |
| zygote (32位) | 全部 framework | 全部 32 位 .so |
| zygote_(vendor) | 部分 framework | vendor 专有 .so |

**关键事实**:
- **32 位 / 64 位 app 走不同 Zygote**(节省内存)
- **vendor app 走 zygote_(vendor)**(隔离 vendor)
- **odm app 走 zygote_(odm)**(隔离 odm)

**架构师必记**:**App 走哪个 Zygote 取决于 abi 列表**。**64 位设备上的 32 位 app 走 zygote(32 位)**。

---

## 5. native 守护进程的加载

### 5.1 native 守护进程是什么

**native 守护进程是 init 直接启动的进程**(不走 Zygote)。它们通常是单一职责的系统服务。

**典型 native 守护进程**:

| 守护进程 | 职责 | 进程类型 |
|---|---|---|
| **init** | 系统初始化 + 进程管理 | 第一个进程 |
| **lmkd** | 内存压力杀手 | 用户态 LMK |
| **surfaceflinger** | 显示合成 | C++ 服务 |
| **audioserver** | 音频服务 | C++ 服务 |
| **cameraserver** | 相机服务 | C++ 服务 |
| **mediacodec** | 媒体编解码 | C++ 服务 |
| **keystore2** | 密钥管理 | C++ 服务 |
| **statsd** | 系统统计 | Java 服务 |
| ... (十几个) | - | - |

### 5.2 native 守护进程的加载特殊性

**native 守护进程 vs zygote-forked 进程的关键差异**:

| 维度 | zygote-forked | native 守护 |
|---|---|---|
| **启动方式** | Zygote fork | init 直接 execve |
| **是否继承 zygote** | ✅ 继承 | ❌ 不继承 |
| **framework 预加载** | ✅ 继承 | ❌ 重新加载 |
| **ART 启动** | ✅ 继承 | ❌ 重新启动 |
| **启动时间** | 快(100-500ms) | 慢(500-2000ms) |
| **内存占用** | 大(继承 zygote) | 小(只加载必要的) |

### 5.3 真实案例:lmkd 守护进程

**lmkd(Low Memory Killer Daemon)是用户态内存杀手**:

**lmkd 启动流程**:

```
init.rc 启动 lmkd:
service lmkd /system/bin/lmkd
    class core
    critical
    ...

启动流程:
1. init execve("/system/bin/lmkd")
2. lmkd 是 ELF 可执行文件(arm64)
3. 内核解析 ELF(本系列 P02)
4. linker64 加载 lmkd 的依赖
   ├─ libc.so
   ├─ liblog.so
   ├─ libsystem.so
   └- liblmkd_utils.so
5. 执行 lmkd::main()
6. lmkd 监听 PSI / memcg 事件
7. 当内存压力达到阈值,杀进程
```

**关键事实**:
- **lmkd 是 native 守护**(不依赖 framework)
- **lmkd 不走 Zygote**(启动慢但内存小)
- **lmkd 监听 PSI 而非 vmpressure**(本系列外,见 MM_v2 06-07)

### 5.4 真实案例:surfaceflinger 守护进程

**surfaceflinger 是显示合成服务**:

**surfaceflinger 启动流程**:

```
1. init execve("/system/bin/surfaceflinger")
2. linker64 加载 .so:
   ├─ libui.so
   ├─ libgui.so
   ├─ libandroid.so
   ├─ libEGL.so
   ├─ libGLESv2.so
   └─ ... (20+ 个 .so)
3. 执行 surfaceflinger::main()
4. 初始化 BufferQueue / HWC(硬件合成)
5. 创建 RenderThread
6. 启动 Looper(等 vsync 信号)
```

**关键事实**:
- **surfaceflinger 是 C++ 服务**(不依赖 Java framework)
- **surfaceflinger 加载 20+ 个 .so**(几 MB 内存)
- **surfaceflinger 启动慢**(1-2 秒)

### 5.5 真实案例:audioserver 守护进程

**audioserver 是音频服务**:

```
1. init execve("/system/bin/audioserver")
2. linker64 加载 .so:
   ├─ libmedia.so
   ├─ libmediautils.so
   ├─ libaudiopolicy.so
   └- libsoundtrigger.so
3. 执行 audioserver::main()
4. 初始化 AudioFlinger
5. 初始化 AudioPolicyService
6. 注册音频 HAL
7. 进入 Looper
```

**关键事实**:
- **audioserver 是 C++ 服务**(混合 C++ + 一些 Java 类)
- **audioserver 加载 10+ 个 .so**
- **audioserver 启动快**(500-1000ms)

### 5.6 native 守护进程的统一加载流程

**所有 native 守护进程的加载流程**:

```
init 直接 execve(/system/bin/<daemon>)
    ↓
1. 内核解析 ELF(本系列 P02)
    ↓
2. linker64 加载 .so(本系列 P03-05)
    ├─ libc / libdl / libm / liblog
    └─ daemon 特有的 .so
    ↓
3. 执行 .init_array(本系列 P05)
    ├─ libc 初始化
    └─ daemon 特有初始化
    ↓
4. 跳到 daemon::main()
    ↓
5. daemon 特有初始化
    ↓
6. 进入主循环
```

**架构师必记**:**native 守护进程是"独立的 C++ 服务"**。**它们不走 Zygote,不继承 framework,但启动快、内存小**。

---

## 6. 4 类进程的横向对比

### 6.1 加载内容对比

| 加载内容 | zygote | system_server | app | native 守护 |
|---|---|---|---|---|
| framework 类 | ✅ preload | ✅ 继承 | ✅ 继承 | ❌ |
| framework 资源 | ✅ preload | ✅ 继承 | ✅ 继承 | ❌ |
| libart / libssl | ✅ preload | ✅ 继承 | ✅ 继承 | ✅ 自己加载 |
| Binder 线程池 | 1-2 | 32 | 16 | 0-2 |
| system services | 0 | 80+ | 0 | 0 |
| App 自己的 .so | 0 | 0 | 5-30MB | 0 |
| App 自己的 DEX | 0 | 0 | 5-50MB | 0 |
| App 自己的 arsc | 0 | 0 | 500KB-5MB | 0 |

### 6.2 启动时间对比

| 启动阶段 | zygote | system_server | app | native 守护 |
|---|---|---|---|---|
| execve | - | 30-50ms | 30-50ms | 30-50ms |
| linker | - | 100-200ms | 50-200ms | 50-200ms |
| JNI_OnLoad | - | 100-200ms | 50-150ms | 30-100ms |
| preload | 1-3s | 0(继承) | 0(继承) | 0(无) |
| fork 后加载 | 0(自身启动) | 80+ 服务 1-2s | DEX+Resources 100-300ms | 0 |
| **总计** | 1-3s | 2-3s | 100-700ms | 100-500ms |

**关键事实**:
- **zygote 启动最慢**(1-3s preload)
- **system_server 慢在 80+ 服务**(1-2s)
- **app 进程快**(继承 zygote + 自己的 DEX/Resources)
- **native 守护最快**(无 preload,只加载必要的)

### 6.3 内存占用对比

| 内存区域 | zygote | system_server | app | native 守护 |
|---|---|---|---|---|
| 总 RSS | 100-200MB | 200-500MB | 80-200MB | 10-100MB |
| ART 堆 | 30-50MB | 80-150MB | 30-50MB | 0(C++ 服务) |
| Java 堆(运行时) | 0 | 0 | 20-50MB | 0 |
| 系统服务对象 | 0 | 100-200MB | 0 | 0 |
| App 自身 | 0 | 0 | 30-100MB | 0 |
| COW 共享 | - | 50-100MB | 50-100MB | 0 |

**架构师必记**:**zygote + system_server 占 Android 内存 30-50%**。**App 进程是"消费者"**。

### 6.4 进程优先级对比

| 进程 | oom_score_adj | 优先级 |
|---|---|---|
| **init** | -1000 | 最高(永不被杀) |
| **lmkd** | -900 | 极高 |
| **system_server** | -800 | 极高 |
| **surfaceflinger** | -700 | 极高 |
| **前台 app** | 0 | 正常 |
| **后台 app** | 500-800 | 低 |
| **空进程** | 900 | 最低 |

**关键事实**:
- **native 守护优先级通常很高**(-800 ~ -1000)
- **app 进程优先级根据状态变化**(前台 → 可见 → 后台 → 空)
- **oom_score_adj 决定被杀顺序**(高 adj 先杀)

---

## 7. 真实案例:同款进程类型的差异

### 7.1 两个 App 进程的差异

**场景**:同款 App,两个 App 进程在同一个设备上。

| 维度 | App1 进程 | App2 进程 |
|---|---|---|
| 继承自 zygote | ✅ | ✅ |
| 加载 App 自己的 DEX | 10MB DEX + 100ms | 10MB DEX + 100ms |
| 加载 App 自己的 .so | 5MB | 5MB |
| 加载 App 自己的 arsc | 2MB | 2MB |
| ART 堆 | 30-50MB | 30-50MB |
| Java 堆 | 20-50MB | 20-50MB |
| **总 RSS** | **80-150MB** | **80-150MB** |

**关键事实**:**两个 App 进程**:
- **共享 zygote 模板**(COW)
- **独立加载 App 自己的内容**(互不影响)
- **总内存占用基本一致**(除非 App 业务差异)

### 7.2 同款 app 在不同设备的差异

**场景**:同款 App,在低端机和高端机的差异。

| 维度 | 低端机(2GB RAM) | 高端机(8GB RAM) |
|---|---|---|
| zygote 进程 | 80-100MB | 150-200MB |
| App 进程 | 60-100MB | 100-200MB |
| 启动时间 | 2000ms | 800ms |
| dex2oat 时长 | 60-120s | 30-60s |
| 编译策略 | space | speed |

**关键事实**:
- **低端机用 space 编译策略**(节省空间)
- **高端机用 speed 编译策略**(更快启动)
- **dex2oat 时长因 CPU 速度而异**

### 7.3 真实案例:lineage 启动优化

**某 LineageOS 设备的启动优化**:

| 优化 | 节省 |
|---|---|
| 减少 native 守护(合并服务) | 启动 -1s |
| 减少 preload 清单 | 启动 -500ms |
| AOT 关键 app(电话、短信) | 启动 -300ms |
| 优化 surfaceflinger 启动 | 启动 -200ms |
| **总计** | **启动 -2s** |

**架构师必记**:**系统级优化需要平衡 zygote preload / native 守护 / AOT 编译**。

---

## 8. 架构师视角:进程类型的 5 个核心洞察

### 8.1 洞察 1:4 类进程的加载策略完全不同

| 进程类型 | 加载策略 |
|---|---|
| zygote | 重 preload,1-3s,所有 App 受益 |
| system_server | 重服务加载,1-2s,80+ 服务 |
| app | 轻加载,100-700ms,继承 zygote |
| native 守护 | 直接 execve,100-500ms,无继承 |

### 8.2 洞察 2:zygote preload 是 Android 性能的关键

**没有 zygote preload,App 启动会慢 30-50%**。**zygote 的"投资"是值得的**。

### 8.3 洞察 3:system_server 是 Android 内存的"大头"

**system_server 占 200-500MB**。**它的 80+ 服务是 Android 系统的核心**。

### 8.4 洞察 4:native 守护的"独立"是设计取舍

**native 守护不走 Zygote,启动慢但内存小**。**这是"独立性 vs 复用"的平衡**。

### 8.5 洞察 5:从进程行为直接映射到进程类型

| 现象 | 进程类型根因 |
|---|---|
| 启动期 100-200ms | app 进程(继承 zygote,只加载自身) |
| 启动期 1-3s | zygote preload |
| 启动期 1-2s | system_server 80+ 服务 |
| 启动期 100-500ms | native 守护 |
| 内存 200-500MB | system_server |
| 内存 80-200MB | app 进程 |
| 内存 100-200MB | zygote 模板 |
| 内存 10-100MB | native 守护 |

---

## 9. 与 MM_v2 14 的对仗

### 9.1 完全对仗矩阵

| 维度 | MM_v2 14(运行时) | PLE 13(启动时) |
|---|---|---|
| zygote | 内存类型 + GC 行为 | preload 内容 |
| system_server | 80+ 服务内存贡献 | 80+ 服务加载顺序 |
| app | 内存类型学(Java/Native/Graphics) | DEX + Resources 加载 |
| native 守护 | init / lmkd 内存 | init / lmkd 加载特殊性 |

### 9.2 共同诊断能力

**MM_v2 14 + PLE 13 一起读,你能**:

1. 看到任何进程的"启动时 + 运行时"全貌
2. 解释内存峰值、内存泄漏、启动慢的根因
3. 在 Perfetto trace 里准确识别进程类型
4. 优化冷启动的特定阶段
5. 治理特定进程类型的稳定性

**架构师必记**:**MM + PLE 是"运行 + 启动"的双视角**。**只看一个是片面的**。

---

## 10. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **4 类进程加载策略完全不同** | zygote 重 preload / system_server 重服务 / app 轻 / native 独立 |
| 2 | **zygote preload 节省 30-50%** | framework 类 10000+ 预加载,所有 App 受益 |
| 3 | **system_server 80+ 服务是 Android 核心** | 占内存 200-500MB,启动 1-2s |
| 4 | **app 进程只加载自身** | 继承 zygote + App DEX + App Resources |
| 5 | **native 守护独立启动** | 不走 Zygote,启动慢但内存小 |

---

## 11. 下一篇预告

14 篇《加载失败与启动期故障速查》是 PLE 系列的**收官篇**,会沿着本篇的 4 类进程 + 8 阶段 + 5 优化点埋下的线索,系统地总结:

- 8 大类启动期故障总览
- SO 侧故障:符号找不到、架构错配、版本不匹配、构造失败
- DEX 侧故障:类找不到、Verify 错误、NoSuchMethodError
- Resources 侧故障:资源 ID 找不到、arsc 解析失败、配置不匹配
- 进程侧故障:fork 失败、Zygote 残留、僵尸进程
- 启动期 OOM:native 侧 mmap 失败、scudo reserve 失败
- 异常关键字 → PLE 阶段 → 排查文章 速查矩阵
- 真实案例汇总(10 个案例)
- 架构师视角:启动期故障的"5 秒定位法"

**14 篇预计 1 周后产出,完成整个 PLE 系列。**

---

## 附录 A:4 类进程对比速查

| 维度 | zygote | system_server | app | native 守护 |
|---|---|---|---|---|
| 启动时间 | 1-3s | 2-3s | 100-700ms | 100-500ms |
| 内存 RSS | 100-200MB | 200-500MB | 80-200MB | 10-100MB |
| 启动方式 | init execve | Zygote fork | Zygote fork | init execve |
| preload | ✅ | ❌ | ❌ | ❌ |
| 继承 zygote | - | ✅ | ✅ | ❌ |
| Binder 线程 | 1-2 | 32 | 16 | 0-2 |

## 附录 B:native 守护进程列表

| 守护进程 | 职责 |
|---|---|
| init | 系统初始化 |
| lmkd | 内存杀手 |
| surfaceflinger | 显示合成 |
| audioserver | 音频服务 |
| cameraserver | 相机服务 |
| mediacodec | 媒体编解码 |
| keystore2 | 密钥管理 |
| statsd | 系统统计 |

## 附录 C:进程优先级(oom_score_adj)

| 进程 | oom_score_adj |
|---|---|
| init | -1000 |
| lmkd | -900 |
| system_server | -800 |
| surfaceflinger | -700 |
| 前台 app | 0 |
| 后台 app | 500-800 |
| 空进程 | 900 |

## 附录 D:本篇与 MM_v2 14 / 后续篇的衔接

| 关联 | 关系 |
|---|---|
| MM_v2 14 | **对仗篇**——运行时 vs 启动时 |
| 14 风险地图 | 4 类进程 + 8 阶段的故障速查 |

---

> **本篇把"4 类进程"拆解到"zygote / system_server / app / native"5 个维度。**
> **14 篇会在这个基础上,做全系列的"风险地图"收口。**
> **记住 4 类进程的"加载策略 + 启动时间 + 内存 + 优先级",你的进程视角就立住了。**
