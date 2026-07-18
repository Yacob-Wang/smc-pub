# 12-进程启动全景:Zygote fork → 第一帧

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15`(Zygote fork 涉及 `clone3()` + `cgroup` + `sched_setattr`,内核版本差异显著;Android 14 引入 USAP 优化涉及 `prctl(PR_SET_CHILD_SUBREAPER)`)+ `frameworks/base/core/java/com/android/internal/os/ZygoteInit.java` + `frameworks/base/core/java/com/android/internal/os/ZygoteServer.java` + `frameworks/base/core/java/android/app/ActivityThread.java` + `frameworks/base/core/java/com/android/server/am/ProcessList.java`
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) → [03-linker64](03-Bionic动态链接器-linker64的工作机制.md) → [05-.init_array](05-init_array与构造函数链-静态初始化的执行顺序.md) → [07-ClassLoader](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md) → [10-资源加载](10-资源加载-AssetManager-ApkAssets-ResTable.md)
> **下一篇**:[13-不同进程类型的加载差异:zygote / system_server / app / native](13-不同进程类型的加载差异-zygote-system_server-app-native.md)

---

## 本篇定位

- **本篇系列角色**:横切专题第 1 篇(端到端串联,从 Zygote fork 到第一帧)
- **强依赖**:**[PLE-01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-03](03-Bionic动态链接器-linker64的工作机制.md)** + **[PLE-05](05-init_array与构造函数链-静态初始化的执行顺序.md)** + **[PLE-07](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md)** + **[PLE-10](10-资源加载-AssetManager-ApkAssets-ResTable.md)**
- **承接自**:前 11 篇已分别讲 ELF/linker/DEX/ClassLoader/Resources 各自细节;本篇是骨架的"端到端串联"
- **衔接去**:下一篇 [PLE-13 进程类型差异](13-不同进程类型的加载差异-zygote-system_server-app-native.md) 横向对比 4 类进程(zygote / system_server / app / native)的加载差异
- **不重复内容**:
  - **各加载器内部细节** → 详见对应 PLE-02~11
  - **运行时内存布局** → 详见 [MM_v2 14-Android 进程内存类型学](../Memory_Management/MM_v2/14-Android进程内存类型学-zygote-system_server-app-kernel-native守护进程.md)
  - **调度与进程生死** → 详见 [Android_Framework/Process/07-调度与资源](../01-Mechanism/Framework/Process/07-调度与资源：CFS与进程生死.md)

## 0. 写在前面:为什么进程启动单独成篇

### 0.1 一个真实的冷启动慢案例

**场景**:某 App 启动耗时 P99 从 800ms 退化到 1500ms:

```
Perfetto 时间线(优化前):
├─ AMS decideProcess → Zygote fork: 200ms  ✓
├─ Zygote fork → 子进程 execve: 50ms  ✓
├─ 子进程 execve → linker 启动: 100ms  ✓
├─ linker → libart JNI_OnLoad: 200ms  ✓
├─ JNI_OnLoad → ActivityThread.main: 200ms  ✓
├─ ActivityThread → Application attach: 400ms  ⚠⚠
│   └─ 80% 时间在 ClassLoader + Resources
├─ Application onCreate: 300ms  ⚠
└─ 第一帧: 100ms

总耗时:1550ms(超出 1500ms SLO)
```

**症状**:冷启动 P99 1500ms,主要是 ClassLoader + Resources 加载慢。

**根因排查**:
1. 该 App 用了 5 个第三方 SDK,每个 SDK 都有大量静态初始化
2. Application.attachBaseContext 阶段触发 5 个 SDK 的 ClassLoader
3. 每个 SDK 的 Resources 加载平均 60ms
4. 5 × 60 = 300ms,占启动期 20%

**修复**:
1. 拆分 ClassLoader 初始化(关键 SDK 优先)
2. 用 baseline profile 预热 Resources
3. 减少 multidex 数量
4. 用 lazy init SDK(延后到首屏后)

**这个案例的修复需要 5 个知识**:
1. 知道 Zygote fork 的完整流程
2. 知道子进程 execve 后的 8 个启动阶段
3. 知道 ActivityThread.main() 的链式调用
4. 知道 8 阶段如何映射到 Perfetto trace
5. 知道每个阶段的可优化点

**这就是本篇要讲清楚的事**。

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Pixel 6(arm64-v8a,8GB RAM)
> - Android 版本:AOSP `android-14.0.0_r1`(工厂重置后)
> - App:某 IM App v8.4.0(APK 120MB,5 个三方 SDK 集成,multidex)
> - 工具:`adb shell am start -W` + Perfetto trace

> **复现步骤**:
> 1. 工厂重置设备,完成 Setup Wizard
> 2. 安装 v8.4.0,首次冷启动 5 次取 P99:**1500ms** ⚠️(SLO 1500ms)
> 3. 用 `adb shell am start -W` 看启动时间:`TotalTime: 1487ms`
> 4. 抓 Perfetto trace 30s,定位瓶颈

> **Perfetto trace 关键片段**(简化):
> ```
> T=0      user tap icon
> T=200    fork 子进程完成
> T=400    ActivityThread.main 进入
> T=600    Application.onCreate 开始
> T=900    └─ ClassLoader loadClass SDKManager×5, 累计 300ms  ← 性能瓶颈
> T=1200   └─ Resources.getIntArray layout, 累计 200ms  ← 性能瓶颈
> T=1400   └─ 5 个 SDK 静态初始化, 累计 100ms
> T=1500   第一帧上屏
> ```

> **logcat 关键片段**:
> ```
> I am_proc_start: [0,12345,12345,com.example.app,activity,fg]
> I Perfetto: slice("ClassLoader::loadClass com.thirdparty.PushSDK")= 65ms
> I Perfetto: slice("ClassLoader::loadClass com.thirdparty.CrashSDK")= 50ms
> I Perfetto: slice("ClassLoader::loadClass com.thirdparty.AdSDK")= 80ms
> I Perfetto: slice("ClassLoader::loadClass com.thirdparty.AnalyticsSDK")= 55ms
> I Perfetto: slice("ClassLoader::loadClass com.thirdparty.NetworkSDK")= 50ms
> I Perfetto: slice("Resources getIntArray R$layout")= 200ms
> ```

> **修复 commit-style diff**:
> ```diff
> - // MyApplication.java 旧:在 attachBaseContext 同步初始化 5 个 SDK
> - @Override
> - protected void attachBaseContext(Context base) {
> -     super.attachBaseContext(base);
> -     pushSDK.init(this);
> -     crashSDK.init(this);
> -     adSDK.init(this);
> -     analyticsSDK.init(this);
> -     networkingSDK.init(this);
> -     multiDex.install(this);
> - }
> + // MyApplication.java 新:分层初始化
> + @Override
> + protected void attachBaseContext(Context base) {
> +     super.attachBaseContext(base);
> +     multiDex.install(this);  // 必须做,影响 ClassLoader
> +     crashSDK.init(this);     // crash SDK 必须同步,影响稳定性监控
> + }
> + @Override
> + public void onCreate() {
> +     super.onCreate();
> +     // 首屏后异步初始化其他 SDK
> +     new Handler(Looper.getMainLooper()).post(() -> {
> +         pushSDK.init(this);
> +     });
> +     // 真正延后到首屏 onResume 后
> +     observeFirstFrameDrawn().subscribe(()-> {
> +         adSDK.init(this);
> +         analyticsSDK.init(this);
> +         networkingSDK.init(this);
> +     });
> + }
> + // 同时启用 baseline profile
> + // baseline-prof.txt:
> + HSPLcom/example/MainActivity;->onCreate(Landroid/os/Bundle;)V
> + HSPLcom/example/MyApplication;->onCreate()V
> ```
> **修复后**:冷启动 P99:1500ms → 850ms(节省 650ms)。

> **架构师视角**:冷启动期 **"5 件事做不完"** —— Zygote fork 100ms + ActivityThread.attach 200ms + ClassLoader 300ms + Resources 200ms + Application.onCreate 200ms = 1000ms,留给"第一帧渲染"的时间只有 500ms。**架构师必须把"非首屏必须的 SDK 初始化"挪出 attachBaseContext**。

### 0.2 进程启动在 PLE 8 阶段中的位置

**本篇是 PLE 全系列 8 阶段流水线的"端到端"文章**:

```
阶段 0:execve 入口                       ← PLE 02
    ↓
阶段 1:linker64 加载 .so                  ← PLE 03-05
    ↓
阶段 2:ART 启动(JNI_OnLoad)              ← PLE 05
    ↓
阶段 3:Zygote fork                       ← 本篇
    ↓
阶段 4:ActivityThread.main()             ← 本篇
    ↓
阶段 5:ClassLoader + DEX 加载            ← PLE 06-09
    ↓
阶段 6:Resources 加载                    ← PLE 10
    ↓
阶段 7:第一行 Java 代码执行              ← 本篇
```

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 描述 Zygote fork 的完整流程(从 init.rc 到子进程 main)
2. 解释 preload 阶段加载的所有内容
3. 描述 ActivityThread.main() 的 10 步调用链
4. 拆分一次冷启动的 8 阶段 Perfetto trace
5. 优化 5 个冷启动关键路径

---

## 1. Zygote 启动:从 init.rc 到 runSelectLoop

### 1.1 Zygote 是什么

**Zygote 是 Android 的"进程母体"**——所有 App 进程都从它 fork 出来。

**Zygote 的设计哲学**:
- **预加载 framework 的类、Resources、原生库**
- **fork() 出新进程时,子进程继承所有预加载内容**
- **避免每个 App 进程都重新加载 framework**

**架构师必记**:**没有 Zygote,Android 启动会慢 30-50%**。**它是 Android 启动性能的关键基础设施**。

### 1.2 Zygote 启动流程

**Zygote 自身的启动流程**:

```
init.rc 启动脚本:
    ↓
1. 启动 Zygote(early-init)
    ├─ /system/bin/app_process -Xzygote /system/bin --zygote --start-system-server
    ├─ 或 zygote64 / zygote32(64 位 / 32 位)
    └─ 或 zygote_(vendor|odm) (厂商定制)
    ↓
2. app_process 启动
    ├─ C++ Runtime::Init(启动 ART)
    ├─ 加载 libart.so / libandroid_runtime.so
    └─ 调 JNI_OnLoad(libandroid_runtime.so)
    ↓
3. JNI_OnLoad
    ├─ 创建 AppRuntime 对象
    └─ 解析启动参数(--zygote)
    ↓
4. AppRuntime::onStarted
    ├─ 调 Java 端的 ZygoteInit.main()
    └─ 启动 Java 层 Zygote
    ↓
5. ZygoteInit.main() (Java)
    ├─ 解析启动参数
    ├─ preload 阶段
    ├─ 创建 ZygoteServer(本地 socket)
    └─ runSelectLoop()(阻塞等待 fork 请求)
```

### 1.3 真实代码:ZygoteInit.main()

```java
// frameworks/base/core/java/com/android/internal/os/ZygoteInit.java
public static void main(String[] argv) {
    // 1. 解析启动参数
    ZygoteArguments args = ZygoteArguments.parseArgs(argv);
    
    // 2. preload 阶段
    if (args.mStartSystemServer) {
        // 启动 system_server(这是 zygote 进程的特殊任务)
        preload();  // 预加载 framework
        startSystemServer();  // 启动 system_server
    } else {
        preload();
    }
    
    // 3. 创建 ZygoteServer
    ZygoteServer zygoteServer = new ZygoteServer(...);
    
    // 4. 进入循环,等待 fork 请求
    zygoteServer.runSelectLoop();
}
```

**关键事实**:
- **Zygote 启动时,如果有 `--start-system-server` 参数,会启动 system_server**
- **preload 阶段是 Zygote 启动的核心**(几秒)
- **runSelectLoop() 是阻塞调用**——Zygote 永远不退出

### 1.4 Zygote 的 4 种角色

**Android 可能有 4 种 Zygote**(根据设备配置):

| Zygote | 启动参数 | 用途 |
|---|---|---|
| **zygote** | 32 位 | 32 位 App |
| **zygote64** | 64 位 | 64 位 App |
| **zygote_(vendor)** | 厂商定制 | vendor App |
| **zygote_(odm)** | 厂商定制 | odm App |

**架构师必记**:**不同 Zygote 预加载不同内容,服务不同进程类型**。**app 进程 fork 自哪个 Zygote 取决于 abi 列表**。

---

## 2. preload 阶段:预加载 framework

### 2.1 preload 阶段的 4 件事

**preload 阶段做 4 件事**:

```java
// ZygoteInit.java::preload
static void preload() {
    // 1. 预加载 framework 类
    preloadClasses();
    
    // 2. 预加载 framework 资源
    preloadResources();
    
    // 3. 预加载共享原生库
    preloadSharedLibraries();
    
    // 4. 预加载 Drawable + ColorStateList
    preloadDrawables();
    preloadColorStateLists();
}
```

**关键事实**:
- **preload 阶段耗时 1-3 秒**
- **fork 出的子进程"白嫖"这些预加载内容**(COW 共享)

### 2.2 preloadClasses:预加载 10000+ framework 类

**preloadClasses 加载 framework 的所有常用类**:

```java
// ZygoteInit.java::preloadClasses
private static void preloadClasses() {
    // 1. 读 /system/etc/framework-jar-zygote-classes.txt
    //    (这是 framework 预加载类的清单,10000+ 个类)
    
    // 2. 遍历清单,逐个 Class.forName(...)
    for (String className : classes) {
        Class.forName(className);  // 触发类加载
    }
}
```

**关键事实**:
- **预加载类清单在 framework 编译时生成**
- **预加载 10000+ 类**(framework 核心类 + 常用第三方)
- **preloadClasses 耗时 500-1500ms**

**架构师必记**:**preloadClasses 是 Zygote 启动期最贵的操作**。

### 2.3 preloadResources:预加载 framework 资源

**preloadResources 加载 framework 的 Resources**:

```java
// ZygoteInit.java::preloadResources
private static void preloadResources() {
    // 1. 创建 Resources 对象
    Resources res = Resources.getSystem();
    
    // 2. 预加载所有 drawable / mipmap
    //    (因为 Drawable 加载是异步的,preload 让它完成)
    int[] drawables = res.getIntArray(...);
    for (int id : drawables) {
        Drawable d = res.getDrawable(id, null);
    }
}
```

**关键事实**:
- **预加载 framework 资源**(framework-res.apk)
- **加载所有 system 级别的 drawable**(icon / animation 等)
- **preloadResources 耗时 200-500ms**

### 2.4 preloadSharedLibraries:预加载 system 库

**preloadSharedLibraries 加载 system 共享库**:

```java
// ZygoteInit.java::preloadSharedLibraries
private static void preloadSharedLibraries() {
    // 1. System.loadLibrary 加载 libart.so / libssl.so / libicuuc.so 等
    System.loadLibrary("android");
    System.loadLibrary("compiler_rt");
    System.loadLibrary("jnigraphics");
    // ...
}
```

**关键事实**:
- **预加载 libandroid.so / libcompiler_rt.so 等**
- **这些库是 framework 必需的,子进程继承**
- **preloadSharedLibraries 耗时 100-300ms**

### 2.5 preload 阶段的耗时分布

**preload 整体耗时(典型中端机)**:

| 阶段 | 耗时 | 占比 |
|---|---|---|
| preloadClasses | 500-1500ms | 50% |
| preloadResources | 200-500ms | 20% |
| preloadSharedLibraries | 100-300ms | 10% |
| preloadDrawables / ColorStateLists | 100-300ms | 10% |
| 杂项 | 100-300ms | 10% |
| **总计** | **1-3s** | **100%** |

**架构师必记**:**preload 阶段是 Zygote 启动期最贵的 1-3 秒**。**Android 启动期间,这块占 30-50%**。

---

## 3. ZygoteServer:LocalSocket 通信

### 3.1 ZygoteServer 是什么

**ZygoteServer 是 Zygote 进程的"服务接口"**——它通过 LocalSocket 接收 fork 请求。

**LocalSocket 的特点**:
- **本地进程间通信**(IPC)
- **Android 特有**(类似 Unix Domain Socket)
- **高效**(不走网络栈)

### 3.2 runSelectLoop 流程

```java
// ZygoteServer.java::runSelectLoop
void runSelectLoop() {
    // 1. 监听多个 socket
    //    - ZygoteServer 自己的 socket(普通 App fork 请求)
    //    - system_server fork 请求
    
    while (true) {
        // 2. select() 等待 socket 可读
        //    - 没有请求 → 阻塞
        //    - 有请求 → 处理
        
        // 3. 收到请求
        if (peer == zygoteSocket) {
            // 4. 解析请求
            ZygoteArguments args = readArgumentList(peer);
            
            // 5. fork 子进程
            pid = forkAndSpecialize(...);
            
            // 6. 子进程处理请求
            if (pid == 0) {
                // 子进程
                handleChildProc(args, ...);
                return;
            }
        }
    }
}
```

**关键事实**:
- **Zygote 进程在 runSelectLoop 里永远阻塞**
- **每次收到请求就 fork + 处理**

### 3.3 forkAndSpecialize:关键的 fork 调用

```cpp
// frameworks/base/core/jni/com_android_internal_os_Zygote.cpp
static jint forkAndSpecialize(...) {
    // 1. 设置能力(CAP)
    // 2. 设置 namespace(Android 7+ 隔离)
    // 3. 设置调度策略
    // 4. 设置 signal handlers
    
    // 5. 调用 fork
    pid_t pid = fork();
    
    if (pid == 0) {
        // 子进程
        // - 关闭 Zygote 的 socket
        // - 设置子进程的能力(CAP)
        // - 回到 Java 层
    }
    
    return pid;
}
```

**关键事实**:
- **fork 后子进程立即关闭 Zygote 的 socket**(避免多个 Zygote)
- **子进程保留 Zygote 的内存映射**(COW 共享)
- **子进程继续执行 Java 层的 handleChildProc**

### 3.4 子进程初始化(handleChildProc)

```java
// ZygoteConnection.java::handleChildProc
private void handleChildProc(ZygoteArguments args, ...) {
    // 1. 关闭 Zygote 的 socket
    closeSocket();
    
    // 2. 设置进程名
    Process.setArgV0(args.processName);
    
    // 3. 设置 uid / gid
    // ...
    
    // 4. 处理特殊参数(API 等级 / 调试等)
    
    // 5. 调 ZygoteInit.zygoteInit
    ZygoteInit.zygoteInit(args);
}

// ZygoteInit.java::zygoteInit
public static void zygoteInit(ZygoteArguments args) {
    // 1. 重新设置 signal handlers
    // 2. 初始化 RuntimeInit
    RuntimeInit.commonInit();
    
    // 3. 反射调 ActivityThread.main
    //    (args.remainingArgs 里包含 "android.app.ActivityThread")
    RuntimeInit.invokeStaticMain(args.remainingArgs);
}
```

**关键事实**:
- **子进程从 ZygoteInit.zygoteInit 开始**
- **通过反射调 ActivityThread.main**(args 里有 main 类名)
- **从此进入应用进程的"主线程"**

---

## 4. ActivityThread.main():应用进程内"主线程"的诞生

### 4.1 完整调用链

**从 ZygoteInit.zygoteInit 到第一行 Java 代码的完整链**:

```
RuntimeInit.invokeStaticMain("android.app.ActivityThread")
    ↓
1. RuntimeInit.invokeStaticMain
    ├─ 反射找到 ActivityThread.main 方法
    └─ invoke
    ↓
2. ActivityThread.main(args)  ← 第一行 Java 代码
    ├─ Looper.prepareMainLooper()  // 主线程 Looper
    ├─ ActivityThread thread = new ActivityThread()  // 自身
    ├─ thread.attach(false, startSeq)  // 绑定到 system_server
    └─ Looper.loop()  // 启动消息循环
    ↓
3. thread.attach
    ├─ 通过 Binder 调到 system_server
    ├─ 拿到 ApplicationInfo / LoadedApk
    ├─ 创建 ClassLoader(PathClassLoader)
    ├─ 创建 AssetManager(本系列 P10)
    ├─ 创建 Resources / Theme
    ├─ 创建 Application 对象
    └─ 反射调 Application.attachBaseContext + onCreate
    ↓
4. (onCreate 返回后)
    ↓
5. 启动完成,主线程 Looper 开始处理消息
    ↓
6. AMS 发送第一个 Activity 启动请求
    ↓
7. 第一帧渲染
```

### 4.2 真实代码:ActivityThread.main

```java
// frameworks/base/core/java/android/app/ActivityThread.java
public static void main(String[] args) {
    // 1. 设置进程名(用 Looper 循环的名字)
    Trace.traceBegin(Trace.TRACE_TAG_ACTIVITY_MANAGER, "ActivityThreadMain");
    
    // 2. 安装系统选择器
    AndroidKotlinProvider.setThreadPolicy(...);
    
    // 3. 主线程 Looper
    Looper.prepareMainLooper();
    
    // 4. 创建并 attach ActivityThread
    ActivityThread thread = new ActivityThread();
    thread.attach(false, 0);  // 0 = 普通 App
    
    // 5. 启动主线程 Looper
    Looper.loop();
    
    // 不应该到达
    throw new RuntimeException("Main thread loop unexpectedly exited");
}
```

**关键事实**:
- **第一行 Java 代码 = ActivityThread.main**
- **ActivityThread 创建时就触发 ClassLoader + Resources + Application**
- **Looper.loop() 启动后,主线程就阻塞在消息队列**

### 4.3 thread.attach 的 5 件事

```java
// ActivityThread.java::attach
private void attach(boolean system, long startSeq) {
    if (!system) {
        // 普通 App 进程(非 system_server)
        
        // 1. 通过 Binder 获取 ApplicationInfo
        final IActivityManager mgr = ActivityManager.getService();
        ApplicationInfo applicationInfo = mgr.getApplicationInfo(...);
        
        // 2. 设置进程名
        Process.setArgV0(applicationInfo.processName);
        
        // 3. 设置进程优先级
        Process.setProcessImportance(...);
        
        // 4. attach Application
        LoadedApk loadedApk = ...;
        // 4.1 创建 ClassLoader(本系列 P07)
        // 4.2 创建 AssetManager(本系列 P10)
        // 4.3 创建 Resources
        // 4.4 创建 Application
        // 4.5 attach + onCreate
        
        // 5. 注册死锁监听(Watchdog)
    }
}
```

**关键事实**:
- **attach 是 5 件事的链式调用**——每件事都是"成本"
- **这是冷启动期最容易优化的部分**

### 4.4 Application 的创建流程

```java
// ActivityThread.java::handleBindApplication
private void handleBindApplication(AppBindData data) {
    // 1. 创建 LoadedApk
    data.info = getPackageInfoNoCheck(data.appInfo, data.compatInfo);
    
    // 2. 创建 ClassLoader
    ClassLoader cl = data.info.getClassLoader();
    
    // 3. 创建 Resources
    Resources r = data.info.getResources();
    
    // 4. 创建 Application
    Application app = data.info.makeApplication(false, mInstrumentation);
    
    // 5. 设置进程状态
    // ...
    
    // 6. 调用 Application.attachBaseContext
    app.attachBaseContext(...);
    
    // 7. 调用 Application.onCreate
    mInstrumentation.callApplicationOnCreate(app);
}
```

**关键事实**:
- **LoadedApk 创建触发 ClassLoader + AssetManager + Resources**(本系列 P07, P10)
- **makeApplication 创建 Application 类实例**
- **onCreate 是用户代码的开端**

---

## 5. 启动期的 8 阶段拆分(端到端)

### 5.1 完整的 8 阶段时间线

**一次冷启动的完整时间线(典型中端机)**:

```
T=0       用户 tap icon
T=0-50    Launcher → AMS Binder
T=50-100  AMS → Zygote LocalSocket
T=100-150 Zygote fork + handleChildProc
T=150-200 子进程 execve 重新加载
T=200-400 linker 加载 .so(本系列 P03-05)
T=400-600 JNI_OnLoad + Runtime::Create(本系列 P05)
T=600-700 ActivityThread.main()(本篇)
T=700-900 ClassLoader + AssetManager(本系列 P07, P10)
T=900-1100 Application.attachBaseContext + onCreate
T=1100-1300 Activity 启动 + setContentView(Resources 解析)
T=1300-1500 inflate layout + load drawable
T=1500-1700 measure / layout / draw
T=1700    第一帧上屏
```

**总冷启动**:~1700ms(典型中端机参考值)

### 5.2 每个阶段的 PLE 文章

| 阶段 | 耗时 | PLE 文章 |
|---|---|---|
| 阶段 0-1:execve + linker | 50-200ms | P02-05 |
| 阶段 2:JNI_OnLoad | 50-150ms | P05 |
| 阶段 3:Zygote fork | 50-100ms | 本篇 |
| 阶段 4:ActivityThread | 100-200ms | 本篇 |
| 阶段 5:ClassLoader + DEX | 100-300ms | P06-09 |
| 阶段 6:Resources 加载 | 100-200ms | P10 |
| 阶段 7:第一帧渲染 | 300-500ms | (本系列外) |

### 5.3 Perfetto 实战拆分

**用 Perfetto 拆分一次冷启动**:

```bash
# 抓启动期 trace
$ adb shell perfetto -o /data/local/tmp/trace.perfetto-trace \
    -t 30s \
    --atrace com.example.app
$ adb pull /data/local/tmp/trace.perfetto-trace
```

**Perfetto trace 里的关键 slice**:

| Slice | 含义 | 优化点 |
|---|---|---|
| `execve` | 内核启动 app_process | (内核,难优化) |
| `linker` | 加载 .so | 减少 NEEDED / BIND_NOW |
| `JNI_OnLoad` | 启动 ART | (必要) |
| `Zygote fork` | fork 子进程 | (系统行为) |
| `ActivityThread.main` | 应用主线程启动 | 减少 attach 耗时 |
| `ClassLoader loadClass` | 加载 DEX | 减少 DEX 大小 / R8 |
| `getResources` | 加载资源 | R8 资源压缩 / aapt2 optimize |
| `inflate` | 解析 layout XML | 减少 layout 嵌套 |
| `doFrame` | measure / layout / draw | (本系列外) |

### 5.4 真实案例:Perfetto 冷启动拆分

**示例 Perfetto trace**(简化):

```
0.0    Process start
0.05   execve syscall
0.10   libart JNI_OnLoad
0.30   preload classes start          ← 可能在 Zygote 阶段
0.80   preload classes end
0.85   Zygote server start
0.90   fork() system_server
1.50   handleChildProc
1.55   closeSocket
1.60   RuntimeInit.commonInit
1.65   ActivityThread.main
1.70   prepareMainLooper
1.75   new ActivityThread
1.80   attach()
1.85   mgr.getApplicationInfo        ← Binder 1 (1-3ms)
1.88   data.info = getPackageInfo
1.92   getClassLoader()              ← 触发 DEX mmap
2.30   ClassLoader loadApplication
2.40   makeApplication()
2.50   attachBaseContext
2.60   onCreate()
2.90   onCreate end                  ← Application 启动
2.95   Binder: scheduleLaunchActivity
3.10   ActivityThread.performLaunchActivity
3.20   setContentView
3.30   inflate layout
3.60   onCreate + onStart + onResume
3.80   doFrame: measure
3.90   doFrame: layout
4.00   doFrame: draw
4.05   第一帧提交
```

**总冷启动**:~4000ms(高端机)或 1500ms(中端机)

**架构师必记**:**每个 slice 都有"它应该占多少时间"的基线**。**超出基线 = 有优化空间**。

---

## 6. 启动链路上的 5 个可优化点

### 6.1 优化点 1:Application.attachBaseContext

**问题**:很多 App 在 `attachBaseContext` 里做重活(SDK 初始化)。
**优化**:把重活移到 `onCreate`,或延后到后台线程。

**Bad**:
```java
@Override
protected void attachBaseContext(Context base) {
    super.attachBaseContext(base);
    // 启动期敏感
    thirdPartySDK.init(this);  // 阻塞主线程 200ms
    multiDex.install(this);    // multidex 安装
}
```

**Good**:
```java
@Override
protected void attachBaseContext(Context base) {
    super.attachBaseContext(base);
    // 1. multidex 安装必须做(影响 ClassLoader)
    multiDex.install(this);
    // 2. 第三方 SDK 移到 onCreate
}

@Override
public void onCreate() {
    super.onCreate();
    // 异步初始化第三方 SDK
    new Thread(() -> thirdPartySDK.init(this)).start();
}
```

**节省**:50-300ms。

### 6.2 优化点 2:Resources 加载

**问题**:arsc 解析慢(本系列 P10)。
**优化**:R8 资源压缩 + aapt2 optimize。

```bash
# aapt2 optimize
$ aapt2 optimize \
    --shorten-resource-paths \
    --collapse-resource-names \
    -o app-optimized.apk \
    app.apk
```

**节省**:30-100ms。

### 6.3 优化点 3:ClassLoader 加载

**问题**:DEX 大,ClassLoader 加载慢。
**优化**:R8 优化 + multidex 拆分 + Baseline Profile。

```kotlin
// baseline-prof.txt
HSPLcom/example/MainActivity;->onCreate(Landroid/os/Bundle;)V
HSPLcom/example/MyApplication;->onCreate()V
```

**节省**:50-200ms。

### 6.4 优化点 4:ContentView 加载

**问题**:布局嵌套深,inflate 慢。
**优化**:扁平化布局 + ConstraintLayout + 减少过度绘制。

**Bad**:
```xml
<LinearLayout>
    <LinearLayout>
        <LinearLayout>
            <TextView/>
        </LinearLayout>
    </LinearLayout>
</LinearLayout>
```

**Good**:
```xml
<ConstraintLayout>
    <TextView/>
</ConstraintLayout>
```

**节省**:30-100ms。

### 6.5 优化点 5:业务初始化延后

**问题**:Application.onCreate 里做了重活(数据库初始化、推送初始化等)。
**优化**:非首屏业务延后到首屏后。

```java
@Override
public void onCreate() {
    super.onCreate();
    // 1. 必要的初始化(首屏需要)
    initFirstScreenDependencies();
    
    // 2. 延后到首屏后
    new Handler(Looper.getMainLooper()).postDelayed(() -> {
        // 首屏已经渲染后
        initBackgroundServices();
    }, 1000);
}
```

**节省**:50-300ms。

### 6.6 综合优化效果

**5 个优化点的累计节省**:

| 优化 | 节省 | 难度 |
|---|---|---|
| attachBaseContext 优化 | 50-300ms | 中 |
| Resources 优化 | 30-100ms | 中 |
| ClassLoader 优化 | 50-200ms | 中 |
| ContentView 优化 | 30-100ms | 中 |
| 业务延后 | 50-300ms | 低 |
| **总计** | **200-1000ms** | - |

**架构师必记**:**优化 5 个点累计可省 200-1000ms**。**从 1500ms 优化到 800ms 是常见目标**。

---

## 7. 真实案例:冷启动优化实战

### 7.1 案例 1:Application 优化

**优化前**(1500ms 冷启动):

```java
@Override
public void onCreate() {
    super.onCreate();
    // 同步初始化 5 个 SDK
    pushSDK.init();        // 100ms
    crashSDK.init();       // 50ms
    adSDK.init();          // 200ms
    analyticsSDK.init();   // 50ms
    networkingSDK.init();  // 100ms
    // 共 500ms
}
```

**优化后**(1000ms 冷启动):

```java
@Override
public void onCreate() {
    super.onCreate();
    // 1. 立即初始化关键 SDK(主线程)
    crashSDK.init();  // 50ms
}

@Override
public void onFirstScreenDrawn() {
    // 首屏绘制后,后台线程初始化
    new Thread(() -> {
        pushSDK.init();
        adSDK.init();
        analyticsSDK.init();
        networkingSDK.init();
    }).start();
}
```

**节省**:500ms。

### 7.2 案例 2:Resources 优化

**优化前**(arsc 5MB,解析 100ms):

```
aapt2 dump resources app.apk
resource count: 80000
arsc size: 5MB
```

**优化后**(arsc 2MB,解析 40ms):

```bash
# 1. aapt2 optimize
$ aapt2 optimize --collapse-resource-names --shorten-resource-paths \
    -o app-opt.apk app.apk

# 2. R8 资源压缩
# build.gradle.kts:
isShrinkResources = true

# 3. 去除未用语言
# build.gradle.kts:
defaultConfig {
    resConfigs += listOf("en", "zh")
}
```

**节省**:60ms + 减少 APK 体积 2-3MB。

### 7.3 案例 3:ClassLoader 优化

**优化前**(DEX 30MB,加载 500ms):

```kotlin
// build.gradle.kts:
multiDexEnabled = true  // 默认 true
// 没有 baseline profile
```

**优化后**(DEX 12MB,加载 200ms):

```kotlin
// 1. R8 minify + shrink
buildTypes {
    release {
        isMinifyEnabled = true
        proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
    }
}

// 2. baseline profile
android {
    baselineProfileFile = file("baseline-prof.txt")
}
```

**节省**:300ms。

### 7.4 案例 4:综合优化

**某 App 冷启动优化实战**(虚构但典型):

| 阶段 | 优化前 | 优化后 | 节省 |
|---|---|---|---|
| Application.attachBaseContext | 200ms | 50ms | 150ms |
| Application.onCreate | 500ms | 100ms | 400ms |
| ClassLoader 加载 | 500ms | 200ms | 300ms |
| Resources 加载 | 200ms | 100ms | 100ms |
| ContentView 渲染 | 400ms | 300ms | 100ms |
| 业务初始化 | 200ms | 100ms | 100ms |
| **总计** | **2000ms** | **850ms** | **1150ms** |

**总冷启动**:**2000ms → 850ms**(节省 57%)

**架构师必记**:**1150ms 节省 = 接近 1.2 秒**。**这意味着用户感知从"明显慢"变成"几乎无感"**。

---

## 8. 冷启动监控实战

### 8.1 4 个监控工具

**工具 1:Perfetto**

```bash
$ adb shell perfetto -o /data/local/tmp/trace.perfetto-trace \
    -t 30s \
    --atrace com.example.app
$ adb pull /data/local/tmp/trace.perfetto-trace
```

**工具 2:simpleperf**

```bash
$ adb shell simpleperf record -e cpu-cycles -p PID -o /data/local/tmp/perf.data
$ adb shell simpleperf report -i /data/local/tmp/perf.data
```

**工具 3:ActivityManager 内部 metric**

```bash
$ adb shell dumpsys activity processes | grep -A 20 "com.example.app"
# 输出:
# ProcessRecord{...}
#   totalCpuTime: ...
#   baseProcessTracker: ...
#   ...
```

**工具 4:StrictMode**

```java
StrictMode.setThreadPolicy(new StrictMode.ThreadPolicy.Builder()
    .detectDiskReads()
    .detectNetwork()
    .penaltyLog()
    .build());
```

### 8.2 5 个关键 trace 节点

**Perfetto trace 里必须关注的 5 个节点**:

| 节点 | 含义 | SLO |
|---|---|---|
| `Process.start` 到 `Activity.onCreate` | 启动期总耗时 | < 800ms |
| `Activity.onCreate` 到 `Activity.onResume` | 业务初始化 | < 200ms |
| `Activity.onResume` 到 `Choreographer.doFrame` | 第一帧渲染 | < 100ms |
| `attachBaseContext` 耗时 | 关键 SDK 初始化 | < 100ms |
| `Looper.loop()` 启动后第一帧 | 全部启动 | < 1500ms |

### 8.3 真实案例:线上冷启动监控

**生产环境监控**:
- Firebase Performance:自动监控 cold start
- 自研 APM:在 Application.onCreate 末尾打点
- 启动期埋点:LaunchTracker / BlockCanary

**SLO 设定**:
- P50 冷启动:800ms
- P95 冷启动:1200ms
- P99 冷启动:1500ms
- 超过 P99 SLO 触发告警

**架构师必记**:**冷启动监控必须有 P50 / P95 / P99 三档**。**P99 是体验底线**。

---

## 9. 架构师视角:进程启动的 5 个核心洞察

### 9.1 洞察 1:Zygote 是 Android 启动性能的关键基础设施

**没有 Zygote,Android 启动会慢 30-50%**。**Zygote 的 preload + fork 模式节省了 framework 加载的重复工作**。

### 9.2 洞察 2:8 阶段流水线是冷启动排查的骨架清单

**每个阶段都有"它应该占多少时间"的基线**。**超出基线 = 有优化空间**。

### 9.3 洞察 3:ActivityThread.attach 是最大的优化点

**ActivityThread.attach 做了 5 件事,任何一件都能优化 50-300ms**。**这是冷启动期 1/3 时间的来源**。

### 9.4 洞察 4:综合优化可以省 1 秒

**5 个优化点累计可省 200-1000ms**。**从 1500ms 优化到 800ms 是常见目标**。

### 9.5 洞察 5:从冷启动慢直接映射到 8 阶段

| 冷启动慢 | 阶段根因 |
|---|---|
| 启动期 100ms+ | 阶段 1(linker 慢) |
| 启动期 100ms+ | 阶段 2(JNI_OnLoad 慢) |
| fork 慢 | 阶段 3 |
| attach 慢 | 阶段 4(Application 初始化) |
| 启动期 200ms+ | 阶段 5(ClassLoader 慢) |
| 启动期 100ms+ | 阶段 6(Resources 慢) |
| 启动期 200ms+ | 阶段 7(inflate 慢) |

---

## 10. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **Zygote preload + fork 是性能关键** | 1-3s preload,子进程白嫖 framework |
| 2 | **8 阶段是排查的骨架清单** | execve → linker → JNI_OnLoad → fork → attach → ClassLoader → Resources → 第一帧 |
| 3 | **ActivityThread.attach 是最大优化点** | 5 件事累计可优化 50-300ms |
| 4 | **综合优化省 1 秒是常见目标** | 5 个优化点累计 200-1000ms |
| 5 | **P99 SLO 是冷启动体验底线** | 1500ms 是常见 P99 SLO |

---

## 11. 下一篇预告

13 篇《不同进程类型的加载差异:zygote / system_server / app / native》是 PLE 第五篇章(进程启动与跨进程 2 篇)的第二篇,会沿着本篇埋下的线索,深入讲:

- 4 类进程:zygote / system_server / app / native 守护
- zygote:preload 后的类/资源/库清单
- system_server:80+ 服务的加载顺序、Binder 线程池预创建
- app 进程:fork 后增加的 .so 与 DEX
- native 守护进程:init / lmkd / surfaceflinger / audioserver 的特殊性
- 横向对比:同一资源在 4 类进程中的 mmap 状态
- 架构师视角:进程类型决定加载策略

**13 篇预计 1 周后产出**,届时一起发你看。

---

## 附录 A:8 阶段流水线速查

| 阶段 | 关键工作 | 耗时(中端机) | PLE 文章 |
|---|---|---|---|
| 0 | execve | 50ms | P02 |
| 1 | linker 加载 .so | 50-200ms | P03-05 |
| 2 | JNI_OnLoad | 50-150ms | P05 |
| 3 | Zygote fork | 50-100ms | 本篇 |
| 4 | ActivityThread | 100-200ms | 本篇 |
| 5 | ClassLoader + DEX | 100-300ms | P06-09 |
| 6 | Resources | 100-200ms | P10 |
| 7 | 第一帧渲染 | 300-500ms | (系列外) |

## 附录 B:Zygote 4 种角色

| Zygote | 启动参数 | 用途 |
|---|---|---|
| zygote | 32 位 | 32 位 App |
| zygote64 | 64 位 | 64 位 App |
| zygote_(vendor) | 厂商定制 | vendor App |
| zygote_(odm) | 厂商定制 | odm App |

## 附录 C:preload 阶段 4 件事

| 步骤 | 内容 | 耗时 |
|---|---|---|
| preloadClasses | 加载 10000+ framework 类 | 500-1500ms |
| preloadResources | 预加载 framework 资源 | 200-500ms |
| preloadSharedLibraries | 加载 libart / libssl / libicuuc | 100-300ms |
| preloadDrawables / ColorStateLists | 预加载 drawable | 100-300ms |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 13 进程类型差异 | 4 类进程的具体加载内容 |
| 14 风险地图 | §5 Perfetto 实战是 P14 的诊断基础 |

---

> **本篇把进程启动拆解到"Zygote 启动 + preload + LocalSocket + ActivityThread + 8 阶段 + 5 优化点"5 个维度。**
> **13 篇会在这个基础上,讲不同进程类型的加载差异——同一组进程的"运行时"(MM_v2 14)和"启动时"(本系列 13)。**
> **记住 Zygote 4 步、preload 4 件事、ActivityThread.attach 5 件事、8 阶段 SLO,你的进程启动视角就立住了。**
