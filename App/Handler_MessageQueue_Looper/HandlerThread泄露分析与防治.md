`HandlerThread 泄漏	/proc/<pid>/fd FD 数量持续增长; ps -T 线程数持续增长; 最终 OOM 或 Too many open files
现在我遇到了一个NE问题，就是systemserver中HandlerThread泄露了，看fdtrace堆栈只有线程创建和MessageQueue的初始化流程，最后就是eventfd eventepoll申请失败，日志也没有什么信息。当然这个已经没有现场了。
我的问题是，没有现场的情况下，如何分析。有现场的情况下又该怎么分析。`

这是一个非常典型且棘手的 **资源耗尽型 Native Crash (NE)**。

`HandlerThread` 泄漏本质上是 **Thread 泄漏 + FD 泄漏** 的双重打击。
*   **Thread 泄漏**：每个 `HandlerThread` 对应一个 Native `pthread`，占用 Pthread 结构体内存和栈空间。
*   **FD 泄漏**：每个 `HandlerThread` 内部维护一个 `Looper`，`Looper` 会创建 `epoll` 实例（1个 FD）和 `eventfd`（1个 FD），至少消耗 2 个 FD。

当 `system_server` 这种常驻进程发生泄漏，FD 达到上限（通常是 1024 或 4096，取决于 `ulimit`），任何涉及 IO 的操作（打开文件、创建 socket、创建 Handler）都会失败，最终导致 `abort()` 或 NE。

针对你的情况，我将分 **“无现场（尸检）”** 和 **“有现场（活体检测）”** 两种情况提供分析思路。

---

### 一、 无现场分析（Post-Mortem Analysis）

既然已经 Crash 且没有现场，我们只能依赖留下的“遗书”：**Tombstone 文件**、**Logcat** 和 **Dropbox**。

#### 1. 挖掘 Tombstone 文件（最关键）
找到对应的 `tombstone_xx` 文件。

*   **看 `Abort Message`**：
    确认死因。如果是 FD 耗尽，通常会看到 `Too many open files` 或者 `Could not create epoll instance`。
*   **看 `threads` 列表（Thread List）**：
    这是破案的金钥匙！Tombstone 会列出 Crash 时进程内**所有存活的线程**。
    *   **搜索线程名**：`HandlerThread` 在创建时通常会传入一个 `name`。
    *   **寻找重复模式**：如果你看到几百个名字一模一样的线程（例如 `WifiScannerThread`、`LocationManager` 或 `Thread-123`），那么**名字就是凶手**。
    *   **无名线程**：如果名字是默认的 `Thread-xx`，则需要结合代码排查哪些模块使用了匿名 `HandlerThread`。

#### 2. 审查 Logcat (History)
虽然 Crash 时日志可能截断，但泄漏是一个**累积过程**。

*   **搜索 `Starting thread`**：
    SystemServer 中启动线程通常会有日志。搜索日志历史，看是否有某个模块在**周期性地、频繁地**启动线程，却从未停止。
*   **搜索 `Looper` 初始化日志**：
    如果开启了 Framework 的某些 Debug 开关，Looper 初始化可能会有打印。

#### 3. 检查 `fdtrace` (如果之前开启了)
你说看 `fdtrace` 只有 `MessageQueue` 初始化流程。这说明你抓到了**分配栈**。
*   **关键点**：`fdtrace` 的堆栈**顶部**是 `epoll_create`，但**底部**（调用者）是谁？
*   **溯源**：沿着堆栈往下找，找到 Java 层的调用起点。是哪个 Service？哪个 Manager？
    *   例如：`com.android.server.am.ActivityManagerService.startHandlerThread`。
    *   一旦找到调用起点，去代码里看：这个 `start` 对应的 `quit` 在哪里？是不是在某个异常流程中 `quit` 被跳过了？或者设计上根本就没写 `quit`？

---

### 二、 有现场分析（Live Analysis / Reproduction）

如果有幸复现了（或者在灰度环境中监控到了 FD 增长），这时候手段就丰富多了。

#### 1. 确认泄漏源（Thread Name & FD）

**Step A: 看线程名 (最快)**
```bash
# 查看 system_server (假设 pid 1000) 的所有线程
adb shell ps -T -p 1000
```
*   **分析**：肉眼观察，哪个名字出现的频率最高？
    *   如果是 `Binder:1000_x` 多，那是 Binder 线程池耗尽（并发请求过多）。
    *   如果是某具体业务名（如 `ConnectivityService`），直接定位到该业务代码。

**Step B: 看 FD 详情**
```bash
# 查看 FD 映射
adb shell ls -l /proc/1000/fd
```
*   **分析**：
    *   如果全是 `anon_inode:[eventfd]` 和 `anon_inode:[eventpoll]`，确诊为 Looper/HandlerThread 泄漏。
    *   如果全是 `/dev/ashmem`，那是内存共享泄漏。
    *   如果全是 `socket`，那是网络连接泄漏。

#### 2. 终极武器：Java Heap Dump (HPROF)

如果线程名是通用的（如 `pool-1-thread-1`），光看名字看不出是谁创建的。这时候必须 **Dump Java Heap**。

**操作步骤：**
1.  **Dump 堆内存**：
    ```bash
    adb shell am dumpheap 1000 /data/local/tmp/heap.hprof
    adb pull /data/local/tmp/heap.hprof
    ```
2.  **转换格式**（如果是 Dalvik/ART 格式需转换）：
    ```bash
    hprof-conv heap.hprof heap_mat.hprof
    ```
3.  **使用 MAT (Memory Analyzer Tool) 或 Android Studio 分析**：
    *   **查找对象**：搜索 `android.os.HandlerThread` 类的所有实例。
    *   **看数量**：如果有 500 个实例，明显异常。
    *   **看引用链 (GC Roots)**：这是核心！
        *   选中一个泄漏的 `HandlerThread` 对象。
        *   右键 -> `Merge Shortest Paths to GC Roots` -> `exclude all phantom/weak/soft etc.`
        *   **结果**：你会看到**谁**持有了这个 Thread 对象。是某个 `Listener`？还是某个 `Map`？还是某个 `Service` 的成员变量？

#### 3. 动态追踪 (Frida / BPF)

如果你是 Framework 开发，且有 Root 权限，可以用 BPF 或 Frida 实时监控 `pthread_create`。

**脚本逻辑：**
Hook `pthread_create` 或 `new HandlerThread()`，打印当前的 Java 堆栈。
当发现某个堆栈在 1 分钟内出现了 100 次，那个堆栈就是泄漏源。

---

### 三、 常见泄漏场景复盘（经验之谈）

在 SystemServer 中，`HandlerThread` 泄漏通常由以下几种“坏代码”引起，你可以对照检查：

1.  **局部变量误用**：
    在方法内部 `new HandlerThread("temp").start()`，用完后觉得它是局部变量会被 GC，但**没有调用 `quit()`**。
    *   *真相*：Thread 只要在运行（run 方法没结束），本身就是 GC Root，不会被回收！必须显式 `quit()`。

2.  **异常流程逃逸**：
    ```java
    void doWork() {
        HandlerThread t = new HandlerThread("work");
        t.start();
        // ... 执行业务 ...
        if (error) return; // 【漏了 t.quit()】
        t.quit();
    }
    ```

3.  **监听器/回调地狱**：
    注册了一个回调，回调里每次都 `new HandlerThread` 去处理耗时任务，处理完却忘了关。

4.  **Service 重启/热修复**：
    SystemServer 中的某个服务被重启了（虽然少见），旧服务的 `HandlerThread` 没清理，新服务又创建了一份。

---

### 四、正确防治 HandlerThread 泄露

分析是为了定位，**防治**才能从根上避免 FD/线程耗尽。以下是正确用法与规范。

#### 1. 生命周期绑定，必须显式 quit

**原则**：谁创建、谁负责回收。`HandlerThread` 必须在不再使用时调用 `quit()` 或 `quitSafely()`。

```java
// 推荐：与组件/服务生命周期绑定
public class MyService extends Service {
    private HandlerThread mWorkerThread;

    @Override
    public void onCreate() {
        super.onCreate();
        mWorkerThread = new HandlerThread("MyWorker");
        mWorkerThread.start();
    }

    @Override
    public void onDestroy() {
        if (mWorkerThread != null && mWorkerThread.isAlive()) {
            mWorkerThread.quitSafely();  // 或 quit()
            try {
                mWorkerThread.join(1000);
            } catch (InterruptedException ignored) { }
        }
        super.onDestroy();
    }
}
```

#### 2. 异常流程中保证 quit：try-finally

有分支或异常时，必须保证无论哪条路径都会执行 quit。

```java
HandlerThread t = new HandlerThread("work");
t.start();
try {
    // ... 可能抛异常的业务 ...
    doWork();
} finally {
    t.quitSafely();
}
```

#### 3. 避免“局部变量创建即遗忘”

**错误示例**：在方法内 `new HandlerThread().start()`，用完后不 quit，指望 GC 回收。  
**真相**：Thread 在运行中本身就是 GC Root，不会因为“没有引用”而被回收，必须显式 quit。

**正确做法**：要么改为类成员并在合适生命周期里 quit，要么在方法内用 try-finally 在逻辑结束时 quit。

#### 4. 优先复用：单例或共享 HandlerThread

在 SystemServer、单进程单服务等场景，优先**一个模块一个 HandlerThread**（或按业务一个线程），避免“每次请求 new 一个”。

```java
// 单例 Worker，避免重复创建
private static volatile HandlerThread sWorker;
private static Handler sHandler;

static Handler getHandler() {
    if (sWorker == null) {
        synchronized (MyClass.class) {
            if (sWorker == null) {
                sWorker = new HandlerThread("MyModuleWorker");
                sWorker.start();
                sHandler = new Handler(sWorker.getLooper());
            }
        }
    }
    return sHandler;
}
```

（若模块有明确生命周期，应在对应销毁路径上 quit 并置空。）

#### 5. quitSafely() 与 quit() 的选用

* **quit()**：立即退出，当前正在处理的 Message 之后的都不再处理。
* **quitSafely()**：等当前 Message 处理完再退出，更温和，一般推荐用 **quitSafely()**，避免任务执行到一半被中断。

在 `onDestroy` 或“不再使用”的时机调用其一即可，不要既不 quit 也不复用。

#### 6. 监听器/回调里不随意 new HandlerThread

在回调里“每次 new HandlerThread 做耗时任务”且不 quit，是典型泄漏源。应改为：

* 使用**共用的 HandlerThread + Handler**，或
* 使用 **ExecutorService**（有界线程池），由框架管理生命周期。

---

### 总结

1.  **无现场**：死磕 **Tombstone 中的线程列表**。名字是最大的线索。
2.  **有现场**：**Heap Dump** 是王道。找到 `HandlerThread` 实例，看是谁持有了它（GC Root）。
3.  **核心原理**：`HandlerThread` 不调用 `quit()` 就会一直存活，其持有的 `Looper` -> `eventfd` 就一直泄露，直到 FD 爆炸。
4.  **防治要点**：生命周期绑定并显式 **quit/quitSafely**、异常路径用 **try-finally** 保证 quit、避免局部创建不回收、优先复用单例/共享线程、回调中不随意 new HandlerThread。
