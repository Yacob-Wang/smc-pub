# 01-从 app_process 到第一行 Java 代码：Android 启动全链路

> **本子模块**：07-启动流程（生命周期 · 7/9）
> **本篇定位**：**生命周期**（7/9）——从 init 进程 → Zygote → Runtime 初始化 → 第一行 Java 代码：init → app_process → AndroidRuntime::start() → Runtime::Init → ZygoteInit.main → forkSystemServer → ActivityThread.main

---

## 0. 本篇定位声明

| 维度 | 本篇承担 | 本篇不涉及 |
| :--- | :--- | :--- |
| Android 启动完整链路 | ✓ init → Zygote → ART → App | — |
| ART Runtime 12 个子系统初始化顺序 | ✓ 完整顺序 | [00-总览](../00-总览/) 概览 |
| Zygote fork 机制 | ✓ 完整机制 | — |
| 启动期稳定性风险地图 | ✓ 8 类风险 | — |
| ART 内部 GC 细节 | — | [04-GC 系统](../03-GC系统/) |
| 启动期性能优化（PGO / Baseline Profile） | — | [02-编译与执行](../02-编译与执行/) |

**承接自**：[06-信号与ANR-Trace](../06-信号与ANR-Trace/) 详解运行期异常处理；本篇**深入启动期**——Android 怎么从无到有。

**衔接去**：[08-对比与演进](../08-对比与演进/) 详解 ART vs JVM + Mainline APEX + Hook 框架影响。

---

## 1. 背景与定义：Android 启动全链路

### 1.1 一句话定义

**Android 启动是从 init 进程（PID 1）→ init.zygote64.rc fork 出 Zygote 进程 → Zygote 启动 ART Runtime + 预加载常用类 → 监听 socket 等待 fork App 进程 → 收到 fork 请求 → fork + 启动 ART + 加载 ActivityThread.main → 第一行 Java 代码执行的完整过程。**

### 1.2 启动全链路 ASCII 图

```
┌────────────────────────────────────────────────────────────────┐
│ Android 启动完整链路（从 init 到第一行 Java 代码）                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  T0: 内核启动                                                   │
│    ↓                                                           │
│  T0+2s: init 进程（PID 1）                                       │
│    ├─ 解析 init.rc / init.zygote64.rc                           │
│    └─ fork Zygote 进程                                          │
│        ↓                                                       │
│  T0+5s: Zygote 进程启动                                          │
│    ├─ app_process（AndroidRuntime）                              │
│    ├─ ART Runtime::Init（12 个子系统初始化）                      │
│    ├─ ART Runtime::Start（启动 SignalCatcher / GC 等）            │
│    ├─ ZygoteInit.main                                            │
│    │   ├─ preloadClasses（1000-2000 个类）                        │
│    │   ├─ preloadResources                                       │
│    │   ├─ preloadSharedLibraries                                 │
│    │   ├─ gcAndFinalize                                          │
│    │   └─ forkSystemServer                                      │
│    └─ 进入 Zygote 循环（监听 socket 等待 fork App）              │
│        ↓                                                       │
│  T0+10s: system_server 启动                                      │
│    ├─ fork 出 system_server                                     │
│    ├─ 启动 AMS / WMS / PMS 等 100+ 系统服务                      │
│    └─ 进入 system_server 循环                                    │
│        ↓                                                       │
│  T0+30s: 桌面启动 + 用户可见                                     │
│    ├─ Launcher 启动                                             │
│    └─ 等待用户点击 App                                           │
│        ↓                                                       │
│  用户点击 App                                                   │
│    ↓                                                           │
│  Zygote fork App 进程                                           │
│    ├─ fork 子进程                                               │
│    ├─ 子进程启动 ART Runtime                                    │
│    ├─ 加载 App Dex（PathClassLoader）                            │
│    ├─ ActivityThread.main                                       │
│    │   └─ 第一行 Java 代码：                                    │
│    │       Looper.prepareMainLooper()                            │
│    │       ActivityThread thread = new ActivityThread()          │
│    │       thread.attach(false)                                  │
│    │       Looper.loop()                                        │
│    └─ 进入 App 主循环                                            │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 1.3 关键时间点

| 时间点 | 事件 | 耗时占比 |
| :--- | :--- | :--- |
| T0 | 内核启动 | — |
| T0+2s | init 进程 | — |
| T0+5s | Zygote 启动 + Runtime 初始化 | 3s |
| T0+5s+ | Zygote preloadClasses | 1-3s |
| T0+10s | system_server fork + 启动 100+ 服务 | 5s |
| T0+15s | 系统就绪 + 桌面启动 | 5s |
| T0+30s | 桌面可见，等待用户 | — |
| 用户点击 | Zygote fork App | 200-500ms |
| App 启动 | ActivityThread.main + Application | 500-1500ms |

---

## 2. init 进程到 Zygote

### 2.1 init 进程职责

```cpp
// system/core/init/init.cpp
int main(int argc, char** argv) {
    // 1. 初始化日志
    InitKernelLogging(argv);
    
    // 2. 挂载文件系统
    mount("tmpfs", "/dev", "tmpfs", 0, "mode=0755");
    // ... 挂载 system / vendor / data 等
    
    // 3. 初始化 SELinux
    SelinuxSetupKernelLogging();
    SelinuxInitialize();
    
    // 4. 解析 init.rc
    Parser parser = CreateParser(action_manager, service_list);
    parser.ParseConfig("/init.rc");
    parser.ParseConfig("/system/etc/init/init.rc");
    // ... 解析所有 rc 文件
    
    // 5. 启动 Zygote
    service_list.StartService("zygote");
    service_list.StartService("zygote_secondary");
    
    // 6. 进入 init 主循环（处理 property 变化 / 子进程重启等）
    while (true) {
        // 处理 action 队列
        // 处理 property 变化
    }
}
```

### 2.2 init.zygote64.rc

**Zygote 启动配置**：

```
# system/core/rootdir/init.zygote64.rc

service zygote /system/bin/app_process64 -Xzygote /system/bin --zygote --start-system-server
    class main
    priority -20
    user root
    group root readproc
    socket zygote stream 660 root system
    socket usap_pool_primary stream 660 root system
    onrestart write /sys/android_power/request_state wake
    onrestart reboot bootloader
    critical window=${zygote.critical_window.minute:-off} target=zygote-fatal
```

**关键参数**：
- `-Xzygote`：告诉 app_process 以 Zygote 模式启动
- `--zygote`：启动 Zygote 模式（监听 fork 请求）
- `--start-system-server`：启动后 forkSystemServer
- `priority -20`：最高优先级（避免被 OOM kill）
- `socket zygote stream 660 root system`：监听 /dev/socket/zygote socket

---

## 3. app_process 与 AndroidRuntime::start

### 3.1 app_process 入口

```cpp
// frameworks/base/cmds/app_process/app_main.cpp
int main(int argc, char* const argv[]) {
    // 1. 解析参数
    AppRuntime runtime(argv[0], computeArgBlockSize(argc, argv));
    
    // 2. 处理参数
    // 忽略 --zygote / --start-system-server 等（这些是给 Zygote 模式用的）
    
    // 3. 启动 AndroidRuntime
    if (zygote) {
        runtime.start("com.android.internal.os.ZygoteInit", args, zygote);
    } else if (className) {
        runtime.start("com.android.internal.os.RuntimeInit", args, className);
    } else {
        fprintf(stderr, "Error: no class name or --zygote argument.\n");
        return 1;
    }
}
```

### 3.2 AndroidRuntime::start

```cpp
// frameworks/base/core/jni/AndroidRuntime.cpp
void AndroidRuntime::start(const char* className, const Vector<String>& options, bool zygote) {
    // 1. 启动 ART 虚拟机
    JNIEnv* env;
    if (startVm(&mJavaVM, &env, zygote) != 0) {
        return;
    }
    
    // 2. 注册 Android JNI 方法
    if (startReg(env) < 0) {
        return;
    }
    
    // 3. 回调 Java 层（ZygoteInit.main 或 RuntimeInit.main）
    // 找到 className 的 main 方法
    jclass clazz = env->FindClass(className);
    jmethodID methodId = env->GetStaticMethodID(clazz, "main", "([Ljava/lang/String;)V");
    
    // 4. 调用 main 方法
    env->CallStaticVoidMethod(clazz, methodId, strArray);
}
```

### 3.3 startVm：启动 ART 虚拟机

```cpp
// frameworks/base/core/jni/AndroidRuntime.cpp
int AndroidRuntime::startVm(JavaVM** pJavaVM, JNIEnv** pEnv, bool zygote) {
    // 1. 构造启动参数
    JavaVMOption opt[NUM_OPTIONS];
    
    // 2. 关键参数
    addOption("-Xms<size>", "Initial heap size");
    addOption("-Xmx<size>", "Max heap size");
    addOption("-XX:+HeapDumpOnOutOfMemoryError");
    addOption("-Xzygote", zygote ? "true" : "false");
    
    // 3. 调用 JNI_CreateJavaVM
    JavaVMInitArgs args;
    args.version = JNI_VERSION_1_6;
    args.options = opt;
    args.nOptions = optCount;
    
    return JNI_CreateJavaVM(pJavaVM, pEnv, &args);
}
```

**JNI_CreateJavaVM** 是 ART 的入口，触发 Runtime::Init。

---

## 4. ART Runtime 初始化

### 4.1 Runtime::Init 12 个子系统

```cpp
// art/runtime/runtime.cc
bool Runtime::Init(...) {
    // 1. 初始化 Native 桥接
    if (!InitNativeBridge()) return false;
    
    // 2. 初始化信号链
    if (!SignalChain::GetChainSize()) return false;
    
    // 3. 初始化 JavaVMExt
    java_vm_ = new JavaVMExt(this, ...);
    
    // 4. 初始化堆
    heap_ = new gc::Heap(...);
    
    // 5. 初始化 ClassLinker
    class_linker_ = new ClassLinker(this, ...);
    if (!class_linker_->Init(...)) return false;
    
    // 6. 初始化 DexFile 工厂
    dex_file_factory_ = new DexFileFactory(...);
    
    // 7. 初始化 Linus 内存管理
    linear_alloc_ = new LinearAlloc(...);
    
    // 8. 初始化异常系统
    if (!InitExceptions()) return false;
    
    // 9. 初始化线程系统
    thread_list_ = new ThreadList(this);
    Thread::Init();
    
    // 10. 初始化 Monitor（synchronized）
    Monitor::Init();
    
    // 11. 初始化 JNI 引用表
    if (!InitJniEnvTable()) return false;
    
    // 12. 初始化 Image 文件（boot.art）
    if (!image_file_.Load(...)) return false;
    
    // 13. 启动 SignalCatcher
    if (!StartSignalCatcher()) return false;
    
    return true;
}
```

### 4.2 Runtime::Start

```cpp
bool Runtime::Start() {
    // 1. 启动 HeapTaskDaemon（GC 调度）
    heap_->GetHeapTaskDaemon()->StartThread();
    
    // 2. 启动 SignalCatcher
    StartSignalCatcher();
    
    // 3. 启动 JIT 编译器
    if (jit_options_.UseJIT()) {
        CreateJit();
        jit_->Start();
    }
    
    // 4. 启动 Profile Saver（写入 Profile）
    if (profile_saver_options_.IsEnabled()) {
        profile_saver_->Start();
    }
    
    return true;
}
```

---

## 5. ZygoteInit.main 详解

### 5.1 preloadClasses 预加载

```java
// frameworks/base/core/java/com/android/internal/os/ZygoteInit.java
public static void main(String[] argv) {
    // 1. 解析启动参数
    boolean startSystemServer = false;
    String socketName = "zygote";
    
    for (String arg : argv) {
        if ("--start-system-server".equals(arg)) {
            startSystemServer = true;
        } else if ("--socket-name=".startsWith(arg)) {
            socketName = arg.substring("--socket-name=".length());
        }
    }
    
    // 2. 创建 Zygote Server socket
    ZygoteServer zygoteServer = new ZygoteServer(socketName);
    
    // 3. 预加载常用类（1000-2000 个）
    preloadClasses();
    
    // 4. 预加载资源
    preloadResources();
    
    // 5. 预加载共享库
    preloadSharedLibraries();
    
    // 6. GC + Finalize
    gcAndFinalize();
    
    // 7. 启动 system_server（如果需要）
    if (startSystemServer) {
        Zygote.forkSystemServer(...);
    }
    
    // 8. 进入 Zygote 主循环
    zygoteServer.runSelectLoop();
}
```

### 5.2 preloadClasses 实现

```java
private static void preloadClasses() {
    // 1. 读取 /system/etc/zygote-preload-classes（1000-2000 个类名）
    InputStream is = ...;
    BufferedReader reader = new BufferedReader(new InputStreamReader(is));
    
    // 2. Class.forName 加载每个类（触发 ClassLinker::DefineClass）
    int count = 0;
    String line;
    while ((line = reader.readLine()) != null) {
        try {
            Class.forName(line, true, null);  // 触发类加载 + 初始化
            count++;
        } catch (Throwable e) {
            // 加载失败不致命
        }
    }
    
    // 3. 预加载完成
    Log.i(TAG, "Preloaded " + count + " classes");
}
```

### 5.3 gcAndFinalize 强制 GC

```java
private static void gcAndFinalize() {
    // 1. 强制 GC
    System.gc();
    Runtime.getRuntime().runFinalization();
    
    // 2. 等待 GC 完成
    try {
        Thread.sleep(100);
    } catch (InterruptedException e) {}
    
    // 3. 再次强制 GC（清理上一轮未释放的对象）
    System.gc();
    Runtime.getRuntime().runFinalization();
    
    // 4. 等待
    try {
        Thread.sleep(100);
    } catch (InterruptedException e) {}
}
```

### 5.4 Zygote fork App 流程

```java
// frameworks/base/core/java/com/android/internal/os/ZygoteServer.java
Runnable runSelectLoop(String abiList) {
    while (true) {
        // 1. 等待 fork 请求
        StructPollfd[] pollFds = ...;
        Os.poll(pollFds, -1);
        
        // 2. 收到 fork 请求
        ZygoteConnection connection = acceptCommandPeer(absiList);
        
        // 3. 处理 fork 请求
        Runnable forkResult = connection.processOneCommand(this);
        
        // 4. 如果是 fork App → 返回子进程 PID
        if (forkResult != null) {
            return forkResult;
        }
    }
}
```

---

## 6. system_server 启动

### 6.1 Zygote.forkSystemServer

```java
// frameworks/base/core/java/com/android/internal/os/Zygote.java
public static int forkSystemServer(String uid, String gid, int[] gids,
                                    int debugFlags, int[][] rlimits,
                                    long permittedCapabilities, long effectiveCapabilities) {
    // 1. 构造 fork 参数
    ZygoteArguments args = new ZygoteArguments(...);
    
    // 2. 调用 nativeForkSystemServer
    return nativeForkSystemServer(uid, gid, gids, debugFlags, rlimits,
                                   permittedCapabilities, effectiveCapabilities);
}
```

### 6.2 SystemServer 启动 100+ 服务

```java
// frameworks/base/services/java/com/android/server/SystemServer.java
public static void main(String[] args) {
    // 1. 创建 SystemServer
    SystemServer systemServer = new SystemServer();
    
    // 2. 启动引导服务
    systemServer.startBootstrapServices();  // AMS / PMS / WMS / ...
    
    // 3. 启动核心服务
    systemServer.startCoreServices();  // Battery / PowerManager / ...
    
    // 4. 启动其他服务
    systemServer.startOtherServices();  // NetworkManagement / ...
    
    // 5. 进入 Looper.loop()
    Looper.loop();
}
```

**核心服务列表（部分）**：

| 服务 | 角色 |
| :--- | :--- |
| **ActivityManagerService（AMS）** | 四大组件管理 + ANR 检测 |
| **WindowManagerService（WMS）** | 窗口管理 + 输入分发 |
| **PackageManagerService（PMS）** | 包管理 |
| **PowerManagerService** | 电源管理 |
| **BatteryService** | 电池 |
| **InputManagerService** | 输入 |
| **NetworkManagementService** | 网络 |
| **ContentService** | ContentProvider |

---

## 7. App 进程启动

### 7.1 Zygote fork App 流程

```
用户点击 App
  ↓
AMS.startProcessLocked
  ↓
Process.start("android.app.ActivityThread")
  ↓
ZygoteProcess.start
  ↓
向 Zygote socket 发送 fork 请求
  ↓
Zygote 接收 fork 请求
  ↓
fork 子进程
  ↓
子进程 RuntimeInit.applicationInit
  ↓
ActivityThread.main
  ↓
Looper.loop()
```

### 7.2 ActivityThread.main 第一行 Java 代码

```java
// frameworks/base/core/java/android/app/ActivityThread.java
public static void main(String[] args) {
    // 1. 初始化性能统计
    SamplingProfilerIntegration.start();
    
    // 2. 设置 CloseGuard（资源泄漏检测）
    CloseGuard.setEnabled(false);
    
    // 3. 创建主线程 Looper
    Looper.prepareMainLooper();
    
    // 4. 创建 ActivityThread 实例（不是真正的 Thread，仅是绑定）
    ActivityThread thread = new ActivityThread();
    
    // 5. 绑定到 AMS（向 system_server 注册）
    thread.attach(false);  // false = 非系统进程
    
    // 6. 获取主线程 Handler
    if (sMainThreadHandler == null) {
        sMainThreadHandler = thread.getHandler();
    }
    
    // 7. 准备 GC 日志
    RuntimeInit.setApplicationObject(...);
    
    // 8. 主线程消息循环
    Looper.loop();  // 进入 App 主循环
    
    // 永远不会到达（除非主循环退出）
    throw new RuntimeException("Main thread loop unexpectedly exited");
}
```

**关键步骤**：
- `Looper.prepareMainLooper()`：创建主线程 Looper
- `thread.attach(false)`：绑定到 AMS，建立 IPC 通道
- `Looper.loop()`：开始处理 Message（启动 / 调度 Activity）

### 7.3 thread.attach(false) 详解

```java
// frameworks/base/core/java/android/app/ActivityThread.java
private void attach(boolean system) {
    // 1. 获取 AMS 代理
    IActivityManager mgr = ActivityManager.getService();
    
    // 2. 构造 ApplicationThread（IPC 入口）
    ApplicationThread appThread = new ApplicationThread();
    
    // 3. 通过 Binder 调用 AMS.attachApplication
    mgr.attachApplication(mAppThread, ...);
    
    // 4. AMS 收到 attachApplication 后：
    //    - 绑定进程
    //    - 创建 Application 实例
    //    - 启动第一个 Activity
}
```

---

## 8. 启动期稳定性风险地图

```
┌────────────────────────────────────────────────────────────────┐
│ Android 启动期 8 类稳定性风险                                    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. init 启动慢                                                 │
│     └─ 解析 init.rc 慢 / SELinux 初始化慢 / 文件系统挂载慢         │
│     └─ 排查：bootchart / dmesg                                   │
│                                                                │
│  2. Zygote preloadClasses 慢                                     │
│     └─ 类加载 + 初始化慢（1000+ 类 × < 10ms = 10s）              │
│     └─ 优化：preload 数量控制 / 懒加载                            │
│                                                                │
│  3. system_server 服务启动慢                                     │
│     └─ PMS 扫描 / WMS 初始化 / AMS 启动慢                         │
│     └─ 优化：服务懒加载 / 异步初始化                             │
│                                                                │
│  4. Zygote fork 慢                                                │
│     └─ 子进程 copy-on-write 不充分 / JIT 缓存失效                 │
│     └─ 优化：USAP / JIT Zygote cache                              │
│                                                                │
│  5. App 启动慢                                                   │
│     └─ Application.onCreate 慢 / ContentProvider 慢 / Activity 启动慢│
│     └─ 优化：懒加载 / Baseline Profile                          │
│                                                                │
│  6. 启动期 ANR                                                   │
│     └─ Application.onCreate / Service.onCreate 主线程阻塞         │
│     └─ 排查：traces.txt + Baseline Profile                      │
│                                                                │
│  7. 启动期 Crash                                                 │
│     └─ ClassNotFoundException / VerifyError / Native Crash        │
│     └─ 排查：bugreport + Tombstone                              │
│                                                                │
│  8. 启动期 OOM                                                   │
│     └─ preload 类过多 → Zygote 内存大 → fork 后内存压力大          │
│     └─ 优化：preload 数量控制                                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 9. 实战案例：某 App 启动慢 2500ms → 800ms 优化

**现象**：某 IM App 冷启动 2500ms，远超行业标准（1500ms）。

**环境**：Android 14 (AOSP 14.0.0_r1) / Kernel 5.10 / 设备 Pixel 6。

### 步骤 1：启动期 trace

```bash
adb shell am start -W com.example.im/.MainActivity
adb shell perfetto --txt -o /data/misc/perfetto-traces/boot.txt \
  -t 30s am wm gfx view binder_driver hal
```

### 步骤 2：定位瓶颈

```
0.000s: App process start
0.300s: ActivityThread.main
0.500s: Application.onCreate（耗时 800ms）
1.500s: MultiDex 加载
2.000s: MainActivity.onCreate（耗时 300ms）
2.500s: 首帧绘制
```

**观察**：
- Application.onCreate 占 800ms（最大）
- MultiDex 加载占 1000ms

### 步骤 3：分析根因

**Application.onCreate 800ms 拆分**：
- SharedPreferences 加载 200ms
- ContentProvider 初始化 300ms
- 第三方 SDK 初始化 200ms
- 业务初始化 100ms

**MultiDex 加载 1000ms 拆分**：
- 12MB Dex mmap：200ms
- Verify：800ms

### 步骤 4：优化方案

**Application.onCreate 优化**：
```java
// 优化前（错误）
public class App extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        // 同步初始化所有 SDK
        SharedPreferences.getInstance().init();  // 200ms
        ContentProvider.init(this);  // 300ms
        ThirdPartySDK.init();  // 200ms
        BusinessLogic.init();  // 100ms
    }
}

// 优化后（正确）
public class App extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        // 仅初始化启动必需
        SharedPreferences.getInstance().init();
        // 其他延迟到首次使用
    }
}
```

**MultiDex 优化**：
- 启用 R8 minify：Dex 12MB → 8MB
- 上传 Baseline Profile：跳过热点方法 Verify

### 步骤 5：验证

```
┌──────────────────────────────────────┬───────────┬───────────┐
│ 指标                                  │ 修复前     │ 修复后     │
├──────────────────────────────────────┼───────────┼───────────┤
│ 冷启动总时间                           │ 2500ms    │ 800ms     │
│ Application.onCreate                   │ 800ms     │ 100ms     │
│ MultiDex 加载                          │ 1000ms    │ 200ms     │
│ 首帧绘制时间                           │ 2500ms    │ 800ms     │
│ Dex 大小                               │ 12MB      │ 8MB       │
└──────────────────────────────────────┴───────────┴───────────┘
```

---

## 10. 总结（架构师视角的 5 条 Takeaway）

1. **Android 启动是 init → Zygote → ART → App 的 4 阶段链**——每阶段都有明确的耗时和优化点。**全链路可视化是优化的前提**。
2. **Zygote preload 1000-2000 个类是启动的隐性成本**——预加载太多 → Zygote 内存大 → fork 后内存压力；预加载太少 → App 首次类加载慢。**平衡是关键**。
3. **ART Runtime 初始化 12 个子系统**——Heap / ClassLinker / JNI / Thread / Monitor / Image 等都有顺序依赖。**初始化失败 → 进程崩溃**。
4. **App 第一行 Java 代码是 `ActivityThread.main` 的 `Looper.loop()`**——之前的所有工作（native 初始化 / JNI 绑定 / AMS attach）都是为这一刻服务。
5. **启动期稳定性风险集中在 Application.onCreate / ContentProvider / MultiDex**——主线程阻塞会直接导致 ANR。**Application.onCreate 必须 < 100ms**。

---

## 附录 A：核心源码路径索引

| 文件 | 完整路径 | AOSP 版本 |
| :--- | :--- | :--- |
| app_process | `frameworks/base/cmds/app_process/app_main.cpp` | AOSP 14+ |
| AndroidRuntime | `frameworks/base/core/jni/AndroidRuntime.cpp` | AOSP 14+ |
| Runtime::Init | `art/runtime/runtime.cc` | AOSP 14+ |
| ZygoteInit | `frameworks/base/core/java/com/android/internal/os/ZygoteInit.java` | AOSP 14+ |
| ZygoteServer | `frameworks/base/core/java/com/android/internal/os/ZygoteServer.java` | AOSP 14+ |
| Zygote | `frameworks/base/core/java/com/android/internal/os/Zygote.java` | AOSP 14+ |
| RuntimeInit | `frameworks/base/core/java/com/android/internal/os/RuntimeInit.java` | AOSP 14+ |
| ActivityThread | `frameworks/base/core/java/android/app/ActivityThread.java` | AOSP 14+ |
| SystemServer | `frameworks/base/services/java/com/android/server/SystemServer.java` | AOSP 14+ |
| init | `system/core/init/init.cpp` | AOSP 14+ |

---

## 附录 B：源码路径对账表

| # | 路径 | 状态 |
| :-- | :--- | :--- |
| 1 | `frameworks/base/cmds/app_process/app_main.cpp` | ✅ 已校对 |
| 2 | `frameworks/base/core/jni/AndroidRuntime.cpp` | ✅ 已校对 |
| 3 | `art/runtime/runtime.cc` | ✅ 已校对 |
| 4 | `frameworks/base/core/java/com/android/internal/os/ZygoteInit.java` | ✅ 已校对 |
| 5 | `frameworks/base/core/java/com/android/internal/os/ZygoteServer.java` | ✅ 已校对 |
| 6 | `frameworks/base/core/java/com/android/internal/os/Zygote.java` | ✅ 已校对 |
| 7 | `frameworks/base/core/java/android/app/ActivityThread.java` | ✅ 已校对 |
| 8 | `frameworks/base/services/java/com/android/server/SystemServer.java` | ✅ 已校对 |
| 9 | `system/core/init/init.cpp` | ✅ 已校对 |

---

## 附录 C：量化数据自检表

| # | 量化描述 | 数量级 |
| :-- | :--- | :--- |
| 1 | init 启动到 Zygote fork | 2-5s |
| 2 | Zygote preload 类数 | 1000-2000 |
| 3 | system_server 服务数 | 100+ |
| 4 | ART Runtime 初始化子系统数 | 12 |
| 5 | Zygote fork 耗时 | 200-500ms |
| 6 | App 启动到 Looper.loop() | 500-1500ms |
| 7 | Application.onCreate 推荐上限 | < 100ms |
| 8 | ActivityThread.main 之前的耗时 | 300ms |

---

## 附录 D：工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
| :--- | :--- | :--- | :--- |
| **Zygote preload 类数** | 1000-2000 | 业务调整 | 太多→内存大 |
| **system_server 启动耗时** | 5-10s | 视服务数 | 太慢→ANR |
| **Zygote fork 耗时** | 200-500ms | AOSP 默认 | USAP 优化可降至 100ms |
| **App 冷启动上限** | 1500ms | 行业标准 | 超 2s→用户流失 |
| **Application.onCreate 上限** | 100ms | 行业标准 | 超 200ms→ANR 风险 |
| **MultiDex 加载上限** | 500ms | 行业标准 | 超 1s→启动崩 |
| **Baseline Profile 上传** | 必须 | Play Store | 不上传→启动慢 |
| **首帧绘制上限** | 1000ms | 行业标准 | 超 1500ms→白屏明显 |

---

> **下一篇**：[01-ART vs JVM 设计哲学](../08-对比与演进/) 将深入 **ART vs JVM 对比**——指令集、内存管理、编译策略、类加载、监控工具的全面差异,以及 ART 演进史（Dalvik → AOT → JIT+AOT → Cloud Profile → Mainline APEX）。