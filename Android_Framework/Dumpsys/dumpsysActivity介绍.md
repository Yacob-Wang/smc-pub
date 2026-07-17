你这个问题问得非常深入，触及了 Android `dumpsys` 命令的分发机制和 `ActivityManagerService` (AMS) 的设计哲学。

**你的观察是完全正确的：**
1.  `dumpsys activity <package>` **包含** `MessageQueue` 信息。
2.  `dumpsys activity` (不带参数) **不包含** `MessageQueue` 信息。

**你的理解偏差在于：** 你认为 `dumpsys activity` 是“获取所有信息（包含子集）”，但实际上，这两个命令在源码层面走的逻辑分支 **完全不同**。

简单来说：
*   **不带参数**：打印的是 **AMS（系统服务）自己** 的内部状态（比如有多少个 Activity 栈、哪些 Service 在运行、内存概况）。它是“上帝视角”的统计数据。
*   **带包名参数**：AMS 会**远程调用（IPC）** 目标应用进程，命令那个应用：“把你自己内部的详细情况（包括 Looper/MessageQueue）打印出来传给我”。

下面我基于 **AOSP (Android Open Source Project)** 源码（以 Android 13/14 逻辑为例）为你详细剖析根本原因。

---

### 1. 入口：ActivityManagerService.java

所有的 `dumpsys activity` 命令最终都会进入 `ActivityManagerService.java` 的 `dump` 方法。

```java
// ActivityManagerService.java

@Override
protected void dump(FileDescriptor fd, PrintWriter pw, String[] args) {
    // ... 权限检查 ...
    
    // 【关键点 1】解析参数
    // 如果 args 不为空，且包含包名，就会进入 dumpPackage 逻辑
    if (args != null && args.length > 0) {
        // ... 解析逻辑 ...
        if (dumpPackage(fd, pw, ...)) { 
            // 如果成功 dump 了指定包，直接返回！
            return; 
        }
    }

    // 【关键点 2】如果没有指定包名（或者参数是 -a 等通用参数）
    // 这里只 dump AMS 自己的数据结构
    dumpActivities(fd, pw, args, opti, dumpAll, dumpClient, null);
    dumpServices(fd, pw, args, opti, dumpAll, dumpClient, null);
    dumpRecents(fd, pw, args, opti, dumpAll, dumpClient, null);
    dumpProcesses(fd, pw, args, opti, dumpAll, dumpClient, null);
    // ...
}
```

#### 分支 A：不带包名 (`dumpsys activity`)
当你不传包名时，代码执行的是下方的一系列 `dumpXxx` 方法（如 `dumpProcesses`）。
这些方法打印的是 **AMS 在 System Server 进程内存中维护的数据**。
*   它知道有哪些进程在运行（`ProcessRecord`）。
*   它知道进程的 PID、UID、OOM adj。
*   **但是！它无法直接读取应用进程内部的 `MessageQueue` 对象。** 因为 `MessageQueue` 在应用进程的堆内存里，AMS 在系统进程，内存是隔离的。

#### 分支 B：带包名 (`dumpsys activity com.android.chrome`)
当你传入包名时，会进入 `dumpPackage` 方法（或者类似的查找逻辑）。一旦找到目标进程，AMS 会发起跨进程调用。

```java
// ActivityManagerService.java -> dumpPackageForUser()

// 找到目标进程的 ProcessRecord
ProcessRecord r = getProcessRecordLocked(packageName, ...);

// 【核心差异】发起 IPC 调用！
// thread 是 IApplicationThread 接口，对应目标应用进程
r.thread.dump(fd.getFileDescriptor(), args); 
```

---

### 2. 客户端响应：ActivityThread.java

当 AMS 调用 `r.thread.dump(...)` 时，代码执行流就从系统进程跨越到了 **Chrome 的应用进程**。
在应用进程中，`ActivityThread` 会响应这个请求：

```java
// ActivityThread.java (应用进程)

@Override
public void dump(FileDescriptor fd, PrintWriter pw, String[] args) {
    // ...
    // 1. Dump Activity 状态
    // 2. Dump Service 状态
    
    // 3. 【终于找到你】Dump Looper 和 MessageQueue！
    if (mLooper != null) {
        pw.println("Looper (main, tid " + android.os.Process.myTid() + ") {");
        // 这里就是你看到的 MessageQueue dump 输出
        mLooper.dump(new PrintWriterPrinter(pw), ""); 
        pw.println("}");
    }
}
```

### 3. 为什么不设计成“默认打印所有”？

你可能会问：*“为什么 `dumpsys activity` 不自动遍历所有进程，把它们的 MessageQueue 都抓回来呢？”*

基于源码和系统设计，主要有以下三个原因：

1.  **性能灾难 (Performance)**：
    *   Android 系统中通常运行着几十甚至上百个应用进程。
    *   Dump `MessageQueue` 需要应用主线程 **暂停处理消息** 并遍历链表。
    *   如果 `dumpsys activity` 遍历所有进程，会导致**所有应用的主线程同时被阻塞**几百毫秒甚至更久，整个手机会瞬间卡死。

2.  **输出爆炸 (Noise)**：
    *   一个繁忙的应用 `MessageQueue` 可能有几十行。
    *   100 个进程就是几千上万行日志。
    *   在庞大的日志海洋中，你根本找不到你关心的那个 Activity 的状态。

3.  **死锁风险 (Deadlock Risk)**：
    *   `dumpsys` 操作是持有 AMS 全局锁（AMS Lock）或者其他系统锁的。
    *   如果为了抓取 `MessageQueue` 而去同步等待所有应用进程响应，只要有一个应用进程处于死锁或挂起状态（Uninterruptible Sleep），整个 `dumpsys` 命令就会超时失败，甚至导致 System Server 看门狗（Watchdog）超时重启。

### 总结

*   **`adb shell dumpsys activity`**：
    *   **视角**：管理者（AMS）。
    *   **内容**：宏观调控数据（谁在运行、内存分级、组件状态）。
    *   **源码路径**：只在 `ActivityManagerService.java` 内部打转。

*   **`adb shell dumpsys activity <package>`**：
    *   **视角**：具体的打工仔（App）。
    *   **内容**：微观执行细节（Looper、MessageQueue、ViewRootImpl）。
    *   **源码路径**：AMS -> **IPC** -> `ActivityThread.java` -> `Looper.dump()`.

所以，如果你想看消息队列，**必须**指定包名，这是为了告诉系统：“我就要查这个特定的家伙，别的人不要动。”