# 06-Handler 与 ANR：从消息延迟到系统超时

在前面五篇文章中，我们完整拆解了 Handler 消息机制的内部实现：从 `Looper.loop()` 的无限循环，到 `MessageQueue.next()` 的 epoll 阻塞唤醒，到 `Message` 的对象池生命周期，再到同步屏障保障 UI 渲染优先级。这些机制共同构建了 Android 主线程的"心跳系统"。

但作为稳定性架构师，你最关心的问题可能是：**这个心跳系统什么时候会出问题？出了问题，系统怎么发现？发现之后怎么处理？**

答案是 ANR（Application Not Responding）。

ANR 是 Android 稳定性治理中最重要、也最容易被误解的问题。许多工程师对 ANR 的理解停留在"主线程卡了 5 秒"——这是一个危险的简化。本篇将从消息机制的视角彻底剖析 ANR：它的本质是什么、四种 ANR 各自的超时炸弹如何通过 Handler 运作、ANR 触发后系统如何收集信息、以及最关键的——为什么引起卡顿的消息不一定是引发 ANR 的消息。

---

## 1. ANR 的本质：纠正最常见的误解

### 1.1 ANR 不是"主线程卡死 5 秒"

对 ANR 最普遍的误解是：**"主线程执行某个操作超过 5 秒就会 ANR"**。这个说法不准确，它混淆了两个不同的概念——**卡顿**和 **ANR**。

**卡顿**是指主线程某条消息的处理耗时过长，导致后续消息排队等待。你可以在主线程处理一条消息花 3 秒、4 秒甚至更长时间，只要系统没有在这段时间内发出需要及时回复的请求，就不会 ANR。

**ANR**是指系统发出的特定请求（Input 事件、Broadcast、Service 启动、ContentProvider 发布）在规定时间内没有得到回复。重点在于："**没有得到回复**"——而不是"主线程卡了多久"。

### 1.2 正确的因果链

```
主线程处理消息 A 耗时 3 秒（卡顿，但不一定 ANR）
    ↓
在这 3 秒内，InputDispatcher 向 App 投递了一个触摸事件
    ↓
触摸事件被放入主线程消息队列排队，等待消息 A 处理完毕
    ↓
消息 A 处理完毕，开始处理触摸事件 → 但 InputDispatcher 的计时器已经跑了 3 秒
    ↓
如果触摸事件本身又耗时 2.5 秒 → 总等待时间 5.5 秒 > 5 秒阈值 → ANR
如果触摸事件本身只耗时 0.5 秒 → 总等待时间 3.5 秒 < 5 秒阈值 → 不 ANR
```

这个因果链揭示了三个关键事实：

1. **ANR 是系统视角的超时**，不是应用视角的卡顿。系统（InputDispatcher / AMS）维护自己的计时器，应用不参与计时。
2. **卡顿是 ANR 的必要条件，但不是充分条件**。3 秒的卡顿不一定导致 ANR——取决于卡顿期间系统是否发出了需要及时回复的请求。
3. **ANR trace 中主线程正在执行的代码，不一定是真正的"凶手"**。trace 抓取的是 ANR 触发那一刻的快照，此时主线程可能已经在处理后续消息了。

### 1.3 与稳定性的关联

理解 ANR 的这个本质，直接影响你的治理策略：

- **不能只盯 ANR trace 中的当前栈**。如果 ANR 发生时主线程在执行一段看似无辜的代码，你需要回溯前面的消息——真正耗时的消息可能已经执行完了。
- **消息耗时预算不是 5 秒，而是远低于 5 秒**。一条消息耗时 2 秒，虽然不直接 ANR，但它"偷走"了后续消息的时间预算。对于稳定性治理，单条消息的耗时目标应该是 **< 100ms**，远低于 ANR 阈值。
- **ANR 率下降不等于卡顿问题解决**。你可以通过各种手段（减少 Broadcast 使用、缩短 Service 启动时间）降低 ANR 率，但如果主线程仍然有大量慢消息，用户体验不会改善。

---

## 2. 四种 ANR 与 Handler 的关系

Android 系统中有四种场景会触发 ANR，每一种都与 Handler 消息机制密切相关。但它们的超时检测方式并不完全相同——分为**基于 Handler 超时炸弹**和**基于 InputDispatcher 内部计时**两大类。

### 2.1 全景表

| ANR 类型 | 超时时间 | 检测机制 | 超时炸弹所在进程 | 核心源码 |
| :--- | :--- | :--- | :--- | :--- |
| **Input** | 5s | InputDispatcher 内部计时 | system_server（native 层） | `InputDispatcher.cpp` |
| **Broadcast 前台** | 10s | Handler.sendMessageAtTime | system_server（BroadcastQueue） | `BroadcastQueue.java` |
| **Broadcast 后台** | 60s | Handler.sendMessageAtTime | system_server（BroadcastQueue） | `BroadcastQueue.java` |
| **Service 前台** | 20s | Handler.sendMessageDelayed | system_server（ActiveServices） | `ActiveServices.java` |
| **Service 后台** | 200s | Handler.sendMessageDelayed | system_server（ActiveServices） | `ActiveServices.java` |
| **ContentProvider** | 10s | Handler.sendMessageDelayed | system_server（AMS） | `ActivityManagerService.java` |

### 2.2 Input ANR（5 秒）

Input ANR 是最常见的 ANR 类型（占线上 ANR 的 60%+），也是与 Handler 关系最"间接"的一种。

**超时检测机制：**

Input ANR 的计时不在 Java 层的 Handler 中，而在 Native 层的 `InputDispatcher` 中。流程如下：

```
InputReader 从驱动读取原始事件
    ↓
InputDispatcher 找到目标窗口
    ↓ 通过 InputChannel（socketpair fd）向 App 投递事件
    ↓ 同时记录：waitQueue.enqueue(eventEntry, currentTime)
    ↓
App 主线程 NativeLooper 的 epoll_wait 返回（fd 可读）
    ↓
ViewRootImpl.WindowInputEventReceiver.onInputEvent()
    ↓ 主线程 Looper 处理事件
    ↓ 处理完毕后，通过 InputChannel 回复 finishInputEvent
    ↓
InputDispatcher 收到回复 → 从 waitQueue 中移除 → 计时取消
    ↓
如果 5 秒内未收到回复：
    ↓
InputDispatcher::onAnrLocked() → 通知 AMS → ANR
```

* **源码路径：** `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp（简化）
nsecs_t InputDispatcher::getDispatchingTimeoutLocked(
        const sp<IBinder>& token) {
    // 默认超时 5 秒（DEFAULT_INPUT_DISPATCHING_TIMEOUT = 5000ms）
    return mWindowInfosById[token].dispatchingTimeout;
}

void InputDispatcher::processAnrsLocked() {
    const nsecs_t currentTime = now();

    // 检查 waitQueue 中最老的事件是否超时
    if (!connection->waitQueue.isEmpty()) {
        DispatchEntry* oldestEntry = connection->waitQueue.front();
        nsecs_t waitDuration = currentTime - oldestEntry->deliveryTime;
        if (waitDuration >= timeout) {
            // 超时！触发 ANR
            onAnrLocked(connection);
        }
    }
}
```

**与 Handler 的关系：**

虽然 InputDispatcher 自身的计时不依赖 Handler，但 **App 端对 Input 事件的处理完全在主线程 Looper 中完成**。Input 事件通过 InputChannel fd 注入到 NativeLooper 的 epoll 监听中，当 fd 可读时，`epoll_wait` 返回，事件被传递给 `ViewRootImpl.WindowInputEventReceiver.onInputEvent()`，最终在主线程中完成 View 的事件分发。

如果主线程正在处理其他耗时消息（比如一次重量级的 `SharedPreferences.apply()` 回写），Input 事件的处理就要排队等待。等主线程腾出手来处理时，InputDispatcher 的计时器可能已经快到 5 秒了。

**稳定性关联：** Input ANR 的诊断难点在于——ANR 触发时抓取的 trace 中，主线程可能已经不在处理导致延迟的那条消息了。真正的"凶手"可能已经执行完毕。这就是第 5 节将深入讨论的"间接性"问题。

### 2.3 Broadcast ANR（前台 10 秒 / 后台 60 秒）

Broadcast ANR 是**最典型的 Handler 超时炸弹模式**。

**超时检测机制：**

* **源码路径：** `frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java`

```java
// frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java（简化）

// 超时常量
static final int BROADCAST_FG_TIMEOUT = 10 * 1000;  // 前台广播 10 秒
static final int BROADCAST_BG_TIMEOUT = 60 * 1000;  // 后台广播 60 秒

final void processNextBroadcastLocked(boolean fromMsg, boolean skipOomAdj) {
    // ...
    // 开始向 App 投递有序广播
    BroadcastRecord r = mOrderedBroadcasts.get(0);

    // 埋下超时炸弹
    long timeoutTime = r.receiverTime + mConstants.TIMEOUT;
    setBroadcastTimeoutLocked(timeoutTime);

    // 通过 Binder 调用 App 的 scheduleReceiver
    // → App 主线程的 ActivityThread.H 收到消息
    // → 执行 BroadcastReceiver.onReceive()
    performReceiveLocked(app, ...);
}

final void setBroadcastTimeoutLocked(long timeoutTime) {
    if (!mPendingBroadcastTimeoutMessage) {
        Message msg = mHandler.obtainMessage(BROADCAST_TIMEOUT_MSG, this);
        // 在 system_server 的 Handler 中设置定时消息
        mHandler.sendMessageAtTime(msg, timeoutTime);
        mPendingBroadcastTimeoutMessage = true;
    }
}
```

**炸弹引爆流程：**

```
BroadcastQueue.processNextBroadcastLocked()
    ├── setBroadcastTimeoutLocked(now + timeout)
    │       → mHandler.sendMessageAtTime(BROADCAST_TIMEOUT_MSG, timeoutTime)  // 埋炸弹
    │
    ├── performReceiveLocked()
    │       → Binder 调用 App → App 主线程 onReceive()
    │
    ├── 如果 App 及时完成 onReceive()：
    │       → AMS 收到 finish 通知
    │       → cancelBroadcastTimeoutLocked()
    │           → mHandler.removeMessages(BROADCAST_TIMEOUT_MSG)  // 拆除炸弹
    │
    └── 如果 App 未在限时内完成：
            → BROADCAST_TIMEOUT_MSG 到期，被 system_server 的 Looper 取出
            → broadcastTimeoutLocked()
                → mHandler.post(() -> mService.mAnrHelper.appNotResponding(...))
                    → 收集 trace → 弹出 ANR 对话框
```

**稳定性关联：** Broadcast ANR 的特殊之处在于——超时炸弹运行在 `system_server` 进程的 Handler 中，而不是 App 进程。这意味着即使 App 进程的主线程完全卡死、Looper 停转，system_server 的计时器仍然会正常到期并触发 ANR。这是一种"监督者-被监督者"分离的设计，确保了监控的可靠性。

### 2.4 Service ANR（前台 20 秒 / 后台 200 秒）

Service ANR 的超时炸弹模式与 Broadcast 几乎相同，也是通过 `Handler.sendMessageDelayed()` 在 system_server 中设置定时消息。

* **源码路径：** `frameworks/base/services/core/java/com/android/server/am/ActiveServices.java`

```java
// frameworks/base/services/core/java/com/android/server/am/ActiveServices.java（简化）

// 超时常量
static final int SERVICE_TIMEOUT = 20 * 1000;      // 前台 Service 20 秒
static final int SERVICE_BACKGROUND_TIMEOUT = SERVICE_TIMEOUT * 10;  // 后台 200 秒

private void realStartServiceLocked(ServiceRecord r,
        ProcessRecord app, boolean execInFg) throws RemoteException {
    // 埋下超时炸弹
    bumpServiceExecutingNoClearLocked(r, execInFg, "create",
            OomAdjuster.OOM_ADJ_REASON_START_SERVICE);

    // 通过 Binder 通知 App 创建 Service
    app.getThread().scheduleCreateService(r, ...);
}

private void bumpServiceExecutingNoClearLocked(ServiceRecord r,
        boolean fg, String why, int oomAdjReason) {
    long now = SystemClock.uptimeMillis();
    if (r.executeNesting == 0) {
        r.executeFg = fg;
        if (r.app != null) {
            r.app.mServices.startExecutingService(r);
            // 设置超时
            if (r.executeFg) {
                scheduleServiceTimeoutLocked(r.app);
            }
        }
    }
    r.executeFg |= fg;
    r.executeNesting++;
    r.executingStart = now;
}

void scheduleServiceTimeoutLocked(ProcessRecord proc) {
    if (proc.mServices.numberOfExecutingServices() == 0 || proc.getThread() == null) {
        return;
    }
    Message msg = mAm.mHandler.obtainMessage(
            ActivityManagerService.SERVICE_TIMEOUT_MSG);
    msg.obj = proc;
    // 在 AMS 的 Handler 中设置延迟消息
    mAm.mHandler.sendMessageDelayed(msg,
            proc.mServices.shouldExecServicesFg()
                    ? SERVICE_TIMEOUT : SERVICE_BACKGROUND_TIMEOUT);
}
```

**拆除炸弹：**

```java
// frameworks/base/services/core/java/com/android/server/am/ActiveServices.java
void serviceDoneExecutingLocked(ServiceRecord r, int type,
        int startId, int res, boolean enqueueOomAdj) {
    // ...
    r.executeNesting--;
    if (r.executeNesting <= 0) {
        if (r.app != null) {
            r.app.mServices.stopExecutingService(r);
            if (r.app.mServices.numberOfExecutingServices() == 0) {
                // 所有 Service 操作完成，拆除炸弹
                mAm.mHandler.removeMessages(
                        ActivityManagerService.SERVICE_TIMEOUT_MSG, r.app);
            }
        }
    }
}
```

**稳定性关联：** Service ANR 相对 Input ANR 更容易诊断，因为 ANR 触发时主线程通常仍在执行 Service 相关的生命周期方法（`onCreate()` / `onStartCommand()` / `onBind()`）。但要注意：如果主线程在执行 Service 生命周期之前就被其他消息阻塞了（排队等待），ANR trace 中显示的可能是那条阻塞消息的代码，而不是 Service 本身的代码。

### 2.5 ContentProvider ANR（10 秒）

ContentProvider ANR 发生在 Provider 的发布阶段。当 App 进程启动时，需要将 Provider 发布给 AMS。如果发布过程（包括 `ContentProvider.onCreate()`）超过 10 秒，AMS 会触发 ANR。

* **源码路径：** `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java（简化）
private boolean attachApplicationLocked(IApplicationThread thread,
        int pid, int callingUid, long startSeq) {
    // ...
    // 埋超时炸弹
    if (app.mProviders.hasProvider()) {
        Message msg = mHandler.obtainMessage(
                CONTENT_PROVIDER_PUBLISH_TIMEOUT_MSG);
        msg.obj = app;
        mHandler.sendMessageDelayed(msg,
                ContentResolver.CONTENT_PROVIDER_PUBLISH_TIMEOUT_MILLIS); // 10s
    }
    // ...
}
```

**稳定性关联：** Provider ANR 通常发生在 App 冷启动时。如果你在 `ContentProvider.onCreate()` 中做了数据库升级、文件 I/O 等耗时操作，就可能触发此类 ANR。由于 Provider 的 `onCreate()` 在 `Application.onCreate()` **之前**执行，这类 ANR 尤其隐蔽。

---

## 3. 超时炸弹的源码走读：以 Broadcast 为例

### 3.1 为什么选 Broadcast 作为典型

四种 ANR 中，Broadcast ANR 的超时炸弹机制最完整地体现了 Handler 的作用：埋炸弹（`sendMessageAtTime`）、拆炸弹（`removeMessages`）、引爆（`handleMessage`）三个环节全部通过 Handler 完成。Input ANR 的计时在 native 层，不如 Broadcast 直观。

### 3.2 完整链路走读

以一个有序广播的投递和超时检测为例，完整走读从"发送广播"到"ANR 触发"的完整链路。

* **源码路径：** `frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java`

**第一阶段：投递广播 + 埋炸弹**

```java
// BroadcastQueue.processNextBroadcastLocked()（核心调度逻辑，简化）
final void processNextBroadcastLocked(boolean fromMsg, boolean skipOomAdj) {
    BroadcastRecord r;

    // ... 先处理无序广播（并行投递，不设超时）...

    // 处理有序广播
    do {
        r = mOrderedBroadcasts.get(0);
        // ...

        // 检查是否已经超时（可能之前的 receiver 就已经超了）
        int numReceivers = (r.receivers != null) ? r.receivers.size() : 0;
        if (r.resultAbort || r.curFilter == null && r.curReceiver == null
                && numReceivers > 0) {
            // ...
        }

        // 如果当前 receiver 尚未处理
        if (r.state != BroadcastRecord.IDLE) {
            return;
        }

        // ========== 关键：设置超时炸弹 ==========
        r.receiverTime = SystemClock.uptimeMillis();
        long timeoutTime = r.receiverTime + mConstants.TIMEOUT;
        // mConstants.TIMEOUT = 前台 10s / 后台 60s
        setBroadcastTimeoutLocked(timeoutTime);

        // 投递给 App
        performReceiveLocked(r.callerApp, ...);
        // → Binder 调用 → App 主线程 → BroadcastReceiver.onReceive()

    } while (r != null);
}
```

**第二阶段：App 完成处理 → 拆除炸弹**

```java
// App 执行完 onReceive() 后，通过 Binder 回调 AMS
// → AMS.finishReceiver() → BroadcastQueue.finishReceiverLocked()

public boolean finishReceiverLocked(BroadcastRecord r, int resultCode,
        String resultData, Bundle resultExtras, boolean resultAbort,
        boolean waitForServices) {
    // ...
    r.state = BroadcastRecord.IDLE;
    // 拆除超时炸弹
    cancelBroadcastTimeoutLocked();
    // ...
}

final void cancelBroadcastTimeoutLocked() {
    if (mPendingBroadcastTimeoutMessage) {
        mHandler.removeMessages(BROADCAST_TIMEOUT_MSG, this);
        mPendingBroadcastTimeoutMessage = false;
    }
}
```

**第三阶段：超时未拆除 → 引爆**

```java
// 如果 App 没有在规定时间内完成 onReceive()
// → BROADCAST_TIMEOUT_MSG 到期
// → system_server Looper 取出这条消息
// → BroadcastQueue.BroadcastHandler.handleMessage()

private final class BroadcastHandler extends Handler {
    @Override
    public void handleMessage(Message msg) {
        switch (msg.what) {
            case BROADCAST_TIMEOUT_MSG: {
                synchronized (mService) {
                    broadcastTimeoutLocked(true);
                }
            } break;
            // ...
        }
    }
}

final void broadcastTimeoutLocked(boolean fromMsg) {
    // ...
    long now = SystemClock.uptimeMillis();
    BroadcastRecord r = mOrderedBroadcasts.get(0);

    if (now > r.receiverTime + mConstants.TIMEOUT) {
        // 确认超时，触发 ANR
        broadcastTimeoutAdjustedLocked(r, now);
    }
}

private void broadcastTimeoutAdjustedLocked(BroadcastRecord r, long now) {
    // ...
    if (curApp != null && !curApp.isDebugging()) {
        // 触发 ANR 信息收集
        mService.mAnrHelper.appNotResponding(curApp,
                "Broadcast of " + r.intent.toString());
    }
}
```

### 3.3 用流程图总结

```
processNextBroadcastLocked()
    │
    ├── setBroadcastTimeoutLocked(now + timeout)
    │       │
    │       └── mHandler.sendMessageAtTime(BROADCAST_TIMEOUT_MSG, timeoutTime)
    │                                                    │
    │                                                    ▼
    │                                           ┌──────────────┐
    │                                           │ system_server │
    │                                           │ MessageQueue  │
    │                                           │              │
    │                                           │ [...] → [BROADCAST_TIMEOUT_MSG] → [...]
    │                                           └──────────────┘
    │                                                    │
    │                                                    │ 到期后取出
    │                                                    ▼
    │                                           broadcastTimeoutLocked()
    │                                                    │
    │                                                    ▼
    │                                           appNotResponding() → ANR!
    │
    ├── performReceiveLocked()
    │       │
    │       └── Binder → App 主线程 → onReceive()
    │                                      │
    │                                      │ 完成后
    │                                      ▼
    │                              finishReceiverLocked()
    │                                      │
    │                                      └── cancelBroadcastTimeoutLocked()
    │                                              │
    │                                              └── mHandler.removeMessages(BROADCAST_TIMEOUT_MSG)
    │                                                          拆除炸弹 ✓
    │
    └── 整个过程的关键：App 必须在 timeout 时间内完成 onReceive() 并回调 finish，
        否则超时消息到期 → ANR。
```

**稳定性关联：** 理解这个"埋炸弹-拆炸弹"模式后，你就能理解为什么 `BroadcastReceiver.onReceive()` 中绝对不能做耗时操作——这不是"最佳实践"级别的建议，而是有一个精确的计时器在倒计时。如果你必须在收到广播后执行耗时任务，正确做法是启动一个 `Service` 或 `WorkManager` 任务，让 `onReceive()` 尽快返回。

---

## 4. ANR 信息收集：从触发到 traces.txt

### 4.1 为什么 ANR 信息收集很重要

ANR 触发只是开始。对于稳定性治理来说，真正有价值的是 **ANR 触发后收集的信息**——这些信息决定了你能否定位根因。如果你不理解收集过程，你就不知道 ANR trace 文件中的信息是怎么来的、有什么局限性、以及为什么有时候 trace 中的信息会"误导"你。

### 4.2 收集流程

* **源码路径：** `frameworks/base/services/core/java/com/android/server/am/AppErrors.java`、`frameworks/base/services/core/java/com/android/server/am/ProcessRecord.java`

ANR 触发后，AMS 执行以下收集流程：

```
ANR 触发（Input / Broadcast / Service / Provider）
    ↓
AppErrors.appNotResponding(ProcessRecord app, ...)
    ↓
① 记录 ANR 基本信息：进程名、PID、ANR 原因、当前 Activity
    ↓
② 收集当前进程的 CPU 使用率快照
    ↓
③ 向目标进程发送 SIGQUIT（信号 3）
    │   ↓
    │   ART 的 SignalCatcher 线程响应
    │       ↓ 挂起所有 Java 线程（SuspendAll）
    │       ↓ 遍历每个线程的栈帧
    │       ↓ 输出线程状态、持有的锁、完整调用栈
    │       ↓ 恢复所有线程（ResumeAll）
    │       ↓ 将 dump 结果写入 /data/anr/traces.txt（或 anr_* 文件）
    │
④ 向其他"关键进程"也发送 SIGQUIT（如 system_server、surfaceflinger）
    ↓
⑤ 收集 CPU、内存、IO 统计信息
    ↓
⑥ 写入 DropBox 归档
    ↓
⑦ 如果是前台 ANR → 弹出 ANR 对话框
    如果是后台 ANR → 静默 kill 进程
```

### 4.3 SIGQUIT 与 trace 生成

trace 文件的生成依赖于 ART 虚拟机对 SIGQUIT 的处理。这部分在本系列的 [09-信号机制与 ANR-Trace](../01-Mechanism/Runtime/ART/09-信号机制与ANR-Trace.md) 中有完整的链路分析。这里给出关键要点：

```java
// frameworks/base/services/core/java/com/android/server/am/AppErrors.java（简化）
void appNotResponding(ProcessRecord app, String activityShortComponentName,
        ApplicationInfo aInfo, String annotation) {
    // ...

    // 收集需要 dump 的进程列表
    ArrayList<Integer> firstPids = new ArrayList<>();
    firstPids.add(app.getPid());  // ANR 进程优先

    // 也收集 system_server 等关键进程
    if (MY_PID != app.getPid()) {
        firstPids.add(MY_PID);
    }

    // 触发 trace dump
    File tracesFile = ActivityManagerService.dumpStackTraces(
            firstPids, null, null, null,
            SparseBooleanArray(), null);

    // 写入 DropBox
    addErrorToDropBox("anr", app, annotation, null, tracesFile, null);

    // 判断是否弹出 ANR 对话框
    if (app.isForeground()) {
        // 弹出对话框让用户选择"等待"或"关闭"
        Message msg = Message.obtain();
        msg.what = ActivityManagerService.SHOW_NOT_RESPONDING_UI_MSG;
        msg.obj = new AppNotRespondingDialog.Data(app, aInfo, annotation);
        mService.mUiHandler.sendMessage(msg);
    } else {
        // 后台进程直接 kill
        app.killLocked("bg anr", ApplicationExitInfo.REASON_ANR, true);
    }
}
```

### 4.4 trace 文件的结构

一个典型的 ANR trace 文件包含以下信息：

```
----- pid 12345 at 2024-01-15 10:30:45 -----
Cmd line: com.example.app
Build fingerprint: 'google/raven/raven:13/TP1A.221005.002/...'

DALVIK THREADS (25):
"main" prio=5 tid=1 Blocked
  | group="main" sCount=1 ucsCount=0 flags=1 obj=0x72a5a000 self=0xb400007d...
  | sysTid=12345 nice=-10 cgrp=top-app sched=0/0 handle=0x7e0e330...
  | state=S schedstat=( 15234567890 2345678901 12345 ) utm=1234 stm=89 core=3 HZ=100
  | stack=0x7fd5600000-0x7fd5602000 stackSize=8192KB
  | held mutexes=
  at com.example.app.SomeClass.someMethod(SomeClass.java:42)
  - waiting to lock <0x0b5c1234> (a java.lang.Object) held by thread 15
  at com.example.app.MainActivity.onResume(MainActivity.java:128)
  at android.app.Instrumentation.callActivityOnResume(Instrumentation.java:1456)
  at android.app.Activity.performResume(Activity.java:8167)
  ...
  at android.os.Handler.dispatchMessage(Handler.java:106)
  at android.os.Looper.loopOnce(Looper.java:201)
  at android.os.Looper.loop(Looper.java:288)
  at android.app.ActivityThread.main(ActivityThread.java:7842)

"Signal Catcher" daemon prio=10 tid=2 Runnable
  ...

"Binder:12345_1" prio=5 tid=8 Native
  ...
```

### 4.5 trace 中的关键信息

| 信息 | 位置 | 诊断价值 |
| :--- | :--- | :--- |
| 主线程状态 | `"main" ... Blocked/Runnable/Waiting/Native` | 判断主线程当前在做什么 |
| 主线程调用栈 | `at com.example.app.SomeClass...` | 定位当前执行代码 |
| 锁等待 | `waiting to lock <0x...> held by thread N` | 发现死锁或锁竞争 |
| `Looper.loop()` 位置 | 调用栈中 `Handler.dispatchMessage` 之上的帧 | 确认正在处理哪条消息 |
| schedstat | `schedstat=( runnable running switches )` | 判断 CPU 是否受限 |
| held mutexes | `held mutexes=...` | 判断是否持有 ART 内部锁 |

**稳定性关联：** trace 文件是 ANR 诊断的核心依据，但要记住它的局限性：

1. **trace 是快照，不是录像**。它只能告诉你 ANR 触发那一刻主线程在做什么，不能告诉你之前 5 秒发生了什么。
2. **SuspendAll 可能失败**。如果某个线程在 native 代码中无法被挂起（如长时间 I/O），trace 中可能会出现 `"Thread suspension timed out"` 错误，导致该线程的栈信息缺失。
3. **dump 本身需要时间**。从发送 SIGQUIT 到完成 dump 可能需要数百毫秒甚至数秒，期间主线程的状态可能已经发生变化。

---

## 5. 消息调度与 ANR 的"间接性"

### 5.1 为什么这是最关键的洞察

本节是整篇文章中对稳定性架构师最有实战价值的部分。

核心洞察：**引起卡顿的消息（耗时长的消息）不一定是引发 ANR 的消息（导致超时的消息）。ANR trace 中主线程当前执行的代码，不一定是真正的"罪魁祸首"。**

### 5.2 经典场景分析

```
时间线：
    t=0s      t=3s       t=4s       t=5s      t=5.5s
    │         │          │          │          │
    ▼         ▼          ▼          ▼          ▼
    ┌─────────┐┌────────┐│          │          │
    │ Message A ││ Msg B  ││          │          │
    │ (耗时3s)  ││(1.5s)  ││          │          │
    └─────────┘│┌────────┘│          │          │
               ││         │          │          │
               │▼         │          │          │
               │处理 Input │          │          │
               │事件开始   │          │          │
               │          │          │          │
    ─────────────────────────────────────────────→ time
    
    InputDispatcher 视角：
    t=0.5s: 投递 Input 事件给 App（此时 App 在处理 Message A）
    t=0.5s ~ t=3s: 等待 App 回复（App 在处理 Message A）
    t=3s: Message A 完成，主线程开始处理 Message B
    t=3s ~ t=4.5s: 等待 App 回复（App 在处理 Message B）
    t=4.5s: Message B 完成，主线程开始处理 Input 事件
    t=4.5s ~ t=5.5s: App 处理 Input 事件
    t=5.0s: 但 InputDispatcher 从 t=0.5s 开始计时，已经等了 4.5s
            此时 Input 事件才开始被处理 0.5s
    t=5.5s: InputDispatcher 等待了 5s → 超时 → ANR!

    ANR trace 抓取时主线程在：处理 Input 事件（看起来 Input 处理慢）
    真正的罪魁祸首：Message A（耗时 3s 导致 Input 事件排队等待）
```

### 5.3 如何从 trace 中识别"间接性"

当你看到 ANR trace 中主线程在执行一段"看似正常"的代码时（比如一次普通的 View 布局），要考虑以下线索：

**线索一：schedstat 分析**

```
"main" ... schedstat=( 12345678000 234567000 5000 )
                       ^walltime    ^iowait   ^switches
```

- `walltime` 值很大但 `iowait` 很小：主线程一直在执行代码（可能前面的消息占用了大量时间）
- `switches` 值很大：主线程被频繁调度，可能是 CPU 资源紧张

**线索二：消息队列状态**

通过 `dumpsys activity` 或 ANR 信息中的 MessageQueue 状态，检查是否有大量待处理消息：

```
MessageQueue:
  Message 0: { when=-2s500ms what=0 target=Handler callback=com.example.DataSync$1 }
  Message 1: { when=-1s200ms what=159 target=Handler (android.app.ActivityThread$H) }
  Message 2: { when=-800ms what=0 target=Handler callback=android.view.ViewRootImpl }
  ... (20+ messages queued)
```

`when` 为负值表示消息已经到期但尚未执行——消息队列有严重积压。

**线索三：CPU 使用率**

ANR 信息中通常包含 CPU 使用率：

```
CPU usage from 0ms to 5000ms later:
  80% 12345/com.example.app: 75% user + 5% kernel
  15% 678/system_server: 10% user + 5% kernel
  ...
100% TOTAL: 85% user + 10% kernel + 5% iowait
```

- **CPU 使用率高（80%+）**：App 在计算密集型操作，某条消息大量消耗 CPU → 后续消息排队。
- **CPU 使用率低但有大量 iowait**：App 在做 I/O 操作（数据库查询、文件读写、网络请求），主线程被阻塞在 I/O 等待。
- **CPU 使用率很低（< 10%）**：主线程可能在等锁、等 Binder 回复，或者系统整体负载高导致主线程得不到 CPU 时间片。

### 5.4 实战识别策略

建立以下诊断决策树：

```
ANR trace 中主线程当前代码是否明显耗时？
    │
    ├── 是（如数据库操作、网络 I/O、大量计算）
    │       → 这条消息本身就是根因
    │       → 优化这段代码
    │
    └── 否（如普通 View 布局、简单回调）
            │
            ├── 检查消息队列是否积压（when 为负值）
            │       │
            │       ├── 是 → 前面有耗时消息，当前消息是"受害者"
            │       │       → 需要找到之前的耗时消息
            │       │
            │       └── 否 → 可能是锁竞争或 Binder 等待
            │
            ├── 检查是否在等锁
            │       → trace 中有 "waiting to lock <0x...> held by thread N"
            │       → 找到持锁线程，分析它在做什么
            │
            └── 检查 CPU 使用率
                    │
                    ├── CPU 整体使用率很高 → 系统负载高，主线程抢不到时间片
                    │
                    └── iowait 高 → 主线程被 I/O 阻塞
```

**稳定性关联：** 理解"间接性"后，你的 ANR 治理策略应该从"只优化 ANR trace 中的代码"转变为"全面监控主线程消息耗时"。消息维度的监控（如每条消息的 dispatch 时间和 delivery 时间）比 ANR 率更能反映主线程健康度。关于监控方案的实现细节，参见本系列的 [08-消息机制诊断工具与监控体系](08-消息机制诊断工具与监控体系.md)。

---

## 6. 稳定性实战案例

### 案例一：SharedPreferences.apply() 阻塞主线程导致 Input ANR

**背景：**

某社交 App 在 Android 8.0+ 设备上出现大量 Input ANR，集中在用户退出聊天页面时。ANR trace 中主线程显示停在 `QueuedWork.waitToFinish()`。

**现象：**

```
"main" prio=5 tid=1 Waiting
  at java.lang.Object.wait(Native method)
  at java.lang.Object.wait(Object.java:442)
  at android.app.QueuedWork.waitToFinish(QueuedWork.java:164)
  at android.app.ActivityThread.handleStopActivity(ActivityThread.java:4608)
  at android.app.ActivityThread.access$1200(ActivityThread.java:221)
  at android.app.ActivityThread$H.handleMessage(ActivityThread.java:2028)
  at android.os.Handler.dispatchMessage(Handler.java:106)
  at android.os.Looper.loopOnce(Looper.java:201)
  at android.os.Looper.loop(Looper.java:288)
  at android.app.ActivityThread.main(ActivityThread.java:7842)
```

**分析：**

从 trace 中可以看到：主线程在 `handleStopActivity()` 中调用了 `QueuedWork.waitToFinish()`。这个方法的作用是等待所有未完成的 `SharedPreferences.apply()` 写操作完成。

`SharedPreferences.apply()` 的设计意图是"异步写入"——先把数据写入内存，然后在后台线程将数据持久化到磁盘。但 Android 在 Activity 的 `onStop()` 和 Service 的 `onDestroy()` 中会调用 `QueuedWork.waitToFinish()`，强制等待所有 pending 的 apply 操作完成。这是为了保证数据不丢失——但如果 apply 的数据量很大或磁盘 I/O 很慢，这个等待可能耗时数秒。

```
时间线：
t=0s:    用户按返回键 → InputDispatcher 投递 KEY_EVENT
t=0.1s:  App 主线程处理按键 → 触发 Activity.finish() → onPause()
t=0.2s:  AMS 调度 handleStopActivity()
t=0.2s:  handleStopActivity() 调用 QueuedWork.waitToFinish()
t=0.2s:  等待 3 个 SharedPreferences.apply() 操作完成
         → apply 操作需要写 2MB 数据到磁盘
         → 磁盘 I/O 繁忙（其他进程也在写入）
t=0.2s ~ t=4.8s: 主线程阻塞在 waitToFinish()
t=1s:    InputDispatcher 投递新的触摸事件（用户尝试点击屏幕）
t=1s ~ t=6s: InputDispatcher 等待 App 回复...
t=4.8s:  apply 操作完成 → waitToFinish() 返回
t=4.8s:  主线程继续处理后续消息 → 开始处理 t=1s 投递的触摸事件
t=6s:    InputDispatcher 已等待 5 秒 → 超时 → Input ANR!
```

**根因：**

聊天页面在退出前会调用多次 `SharedPreferences.apply()` 保存聊天状态、未读数、草稿等信息。每次 `apply()` 都会向 `QueuedWork` 队列中添加一个写操作。当 `handleStopActivity()` 调用 `waitToFinish()` 时，需要等待所有这些写操作完成。在低端设备或磁盘 I/O 繁忙时，等待时间可达数秒。

```java
// 问题代码（聊天页面 onPause 中频繁 apply）
@Override
protected void onPause() {
    super.onPause();
    // 每次 apply 都向 QueuedWork 添加一个 pending 任务
    prefs.edit().putString("draft", draftText).apply();
    prefs.edit().putInt("unread_count", count).apply();
    prefs.edit().putLong("last_read_time", time).apply();
    prefs.edit().putString("chat_state", serializeState()).apply(); // 大数据！
}
```

**修复：**

1. **合并 apply 调用**：将多次 apply 合并为一次：

```java
@Override
protected void onPause() {
    super.onPause();
    prefs.edit()
        .putString("draft", draftText)
        .putInt("unread_count", count)
        .putLong("last_read_time", time)
        .putString("chat_state", serializeState())
        .apply(); // 只调用一次 apply
}
```

2. **大数据使用 commit + 异步**：对于大数据（如 chat_state），不要通过 SharedPreferences 存储，改用数据库或文件 I/O 在后台线程完成：

```java
@Override
protected void onPause() {
    super.onPause();
    prefs.edit()
        .putString("draft", draftText)
        .putInt("unread_count", count)
        .putLong("last_read_time", time)
        .apply();

    // 大数据异步写入文件，不经过 QueuedWork
    executor.execute(() -> {
        FileUtils.writeToFile(chatStateFile, serializeState());
    });
}
```

3. **Hook QueuedWork（高级方案）**：通过反射清空 `QueuedWork` 的 pending 队列，绕过 `waitToFinish()` 的阻塞。微信 Matrix 和字节 Sliver 等 APM 框架采用此方案：

```java
// 在 Application.onCreate() 中 Hook
try {
    Class<?> clazz = Class.forName("android.app.QueuedWork");
    Field field = clazz.getDeclaredField("sPendingWorkFinishers");
    field.setAccessible(true);
    // 替换为不阻塞的空实现
    ConcurrentLinkedQueue<?> original = (ConcurrentLinkedQueue<?>) field.get(null);
    // ... 用代理替换，异步执行写操作
} catch (Exception e) {
    // 降级：不 hook
}
```

**经验总结：** `SharedPreferences.apply()` 看似是"异步无害"的操作，实际上在 Activity/Service 生命周期切换时会被 `QueuedWork.waitToFinish()` 强制同步等待。这是 Android 框架层的一个已知设计缺陷（Google 在 Android 12 中做了部分优化但未完全解决）。对于稳定性架构师，规则是：**避免在主线程中高频或大数据量地使用 apply()，尤其是在 onPause / onStop 之前。** 建议使用 MMKV 等替代方案来规避此问题。

---

### 案例二：BroadcastReceiver 中执行网络请求导致 Broadcast ANR

**背景：**

某电商 App 的推送模块注册了一个静态 BroadcastReceiver，用于接收推送消息。线上出现大量 Broadcast ANR，ANR 原因为 `"Broadcast of Intent { act=com.example.push.RECEIVE }"`.

**现象：**

```
"main" prio=5 tid=1 Native
  at android.os.BinderProxy.transactNative(Native method)
  at android.os.BinderProxy.transact(BinderProxy.java:540)
  at com.example.push.IPushService$Stub$Proxy.reportReceived(IPushService.java:245)
  at com.example.push.PushReceiver.onReceive(PushReceiver.java:58)
  at android.app.ActivityThread.handleReceiver(ActivityThread.java:4139)
  at android.app.ActivityThread$H.handleMessage(ActivityThread.java:2028)
  at android.os.Handler.dispatchMessage(Handler.java:106)
  at android.os.Looper.loopOnce(Looper.java:201)
  at android.os.Looper.loop(Looper.java:288)
  at android.app.ActivityThread.main(ActivityThread.java:7842)

CPU usage from 0ms to 10000ms later:
  5% 12345/com.example.app: 2% user + 3% kernel / faults: 1234 minor
  ...
  10% TOTAL: 5% user + 3% kernel + 2% iowait + 0% softirq
```

**分析：**

从 trace 中可以看到：

1. 主线程在 `PushReceiver.onReceive()` 中通过 Binder 调用 `IPushService.reportReceived()`。
2. CPU 使用率极低（5%），说明主线程不是在计算——而是在**等待**。
3. Binder 调用是同步阻塞的（`transactNative` 是同步调用），主线程在等待远端 Service 返回。

进一步排查发现，`IPushService.reportReceived()` 的远端实现在另一个进程中，该方法内部执行了一次 HTTP 请求向推送服务器确认消息已收到。在网络条件差（弱网、运营商重定向）时，HTTP 请求可能耗时 10 秒以上。

**根因：**

```java
// 问题代码
public class PushReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String pushId = intent.getStringExtra("push_id");
        String pushContent = intent.getStringExtra("content");

        // 同步 Binder 调用 → 远端执行网络请求 → 阻塞主线程！
        IPushService service = IPushService.Stub.asInterface(
                ServiceManager.getService("push_service"));
        service.reportReceived(pushId);  // 内部执行 HTTP 请求

        // 显示通知
        showNotification(context, pushContent);
    }
}

// 远端 Service 实现
class PushServiceImpl extends IPushService.Stub {
    @Override
    public void reportReceived(String pushId) {
        // 在 Binder 线程中执行同步 HTTP 请求！
        HttpClient.post("https://push.example.com/ack", pushId);  // 可能耗时 10s+
    }
}
```

**引用链：** 主线程 `onReceive()` → 同步 Binder 调用 → 远端 Binder 线程 → 同步 HTTP 请求 → 弱网超时 10s+ → 主线程阻塞 10s+ → 前台 Broadcast 超时 10s → ANR。

```
系统时间线：
t=0s:    BroadcastQueue 投递广播 + 埋下超时炸弹（10s）
t=0.1s:  App 主线程开始执行 onReceive()
t=0.1s:  onReceive() 发起同步 Binder 调用
t=0.1s:  远端 Service 开始 HTTP 请求
t=0.1s ~ t=12s: HTTP 请求因弱网超时（connect timeout 12s）
t=10s:   BroadcastQueue 超时消息到期 → 引爆 → ANR!
t=12s:   HTTP 请求超时返回 → Binder 调用返回 → onReceive() 继续执行
         但 ANR 已经在 t=10s 触发了
```

**修复：**

1. **将耗时操作移出 onReceive()**：

```java
public class PushReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String pushId = intent.getStringExtra("push_id");
        String pushContent = intent.getStringExtra("content");

        // 先显示通知（轻量操作，快速完成）
        showNotification(context, pushContent);

        // 将确认操作委托给后台任务
        PushAckWorker.enqueue(context, pushId);
    }
}

// 使用 WorkManager 异步处理
public class PushAckWorker extends Worker {
    @NonNull
    @Override
    public Result doWork() {
        String pushId = getInputData().getString("push_id");
        try {
            HttpClient.post("https://push.example.com/ack", pushId);
            return Result.success();
        } catch (IOException e) {
            return Result.retry();
        }
    }

    public static void enqueue(Context context, String pushId) {
        OneTimeWorkRequest request = new OneTimeWorkRequest.Builder(PushAckWorker.class)
                .setInputData(new Data.Builder().putString("push_id", pushId).build())
                .setConstraints(new Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build())
                .build();
        WorkManager.getInstance(context).enqueue(request);
    }
}
```

2. **如果必须在 onReceive() 期间保活进程**：使用 `goAsync()` 延长 BroadcastReceiver 的生命周期（但仍有超时限制）：

```java
public class PushReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        final PendingResult pendingResult = goAsync();

        // 在后台线程处理
        Executors.newSingleThreadExecutor().execute(() -> {
            try {
                String pushId = intent.getStringExtra("push_id");
                HttpClient.post("https://push.example.com/ack", pushId);
            } finally {
                pendingResult.finish(); // 通知 AMS 处理完毕 → 拆除炸弹
            }
        });

        showNotification(context, intent.getStringExtra("content"));
    }
}
```

> **注意：** `goAsync()` 只是将 `onReceive()` 的执行权从主线程释放，允许你在后台线程完成处理并手动调用 `finish()`。但**超时限制不变**——你仍然需要在 10 秒（前台）或 60 秒（后台）内调用 `finish()`。

3. **防御性措施——Binder 调用超时保护**：

```java
// 如果必须同步调用 Binder，设置超时保护
IBinder binder = ServiceManager.getService("push_service");
if (binder != null) {
    try {
        binder.linkToDeath(() -> {/* Service 死亡回调 */}, 0);
        // Android 没有提供 Binder 调用超时 API，
        // 需要通过 Future + timeout 模式包装：
        Future<Void> future = executor.submit(() -> {
            service.reportReceived(pushId);
            return null;
        });
        future.get(3, TimeUnit.SECONDS); // 最多等 3 秒
    } catch (TimeoutException e) {
        Log.w(TAG, "reportReceived timed out, will retry later");
        // 降级：放入重试队列
    }
}
```

**经验总结：** `BroadcastReceiver.onReceive()` 是一个严格限时的回调。在 `onReceive()` 中发起同步 Binder 调用，等于把超时控制权交给了远端进程——如果远端进程执行慢或死锁，你的进程就会 ANR。原则是：**onReceive() 中只做轻量操作（显示通知、更新内存状态、启动后台任务），所有可能耗时的操作都必须异步化。** 对于需要网络请求的场景，使用 `WorkManager` + 网络约束是最安全的方案。

---

## 总结

本篇从消息机制的视角完整剖析了 ANR 的本质、检测机制、信息收集流程和诊断方法。

| 维度 | 核心认知 |
| :--- | :--- |
| **ANR 本质** | 不是"主线程卡了 5 秒"，而是"系统请求在规定时间内未得到回复" |
| **四种 ANR** | Input(5s) / Broadcast(10s/60s) / Service(20s/200s) / Provider(10s)，每种都有 Handler 超时炸弹 |
| **超时炸弹** | sendMessageDelayed 埋炸弹 → 完成后 removeMessages 拆炸弹 → 超时则 handleMessage 引爆 |
| **信息收集** | SIGQUIT → SignalCatcher → SuspendAll → dump traces → /data/anr/ → DropBox |
| **间接性** | 引起卡顿的消息 ≠ 引发 ANR 的消息；trace 中的栈可能是"受害者"而非"凶手" |
| **诊断策略** | 不能只看 trace 当前栈；结合 schedstat、消息队列状态、CPU 使用率综合判断 |

**对于稳定性架构师的核心建议：**

1. **消息耗时预算**：单条消息 < 100ms（而非 5s），给后续消息留足时间预算。
2. **全面监控**：不仅监控 ANR 率，更要监控每条消息的 dispatch 时间和 delivery 时间。
3. **根因回溯**：ANR 治理不能只修 trace 中看到的代码——要分析整个消息队列的调度历史。
4. **异步化原则**：在限时回调（onReceive / onCreate 等）中，所有可能耗时的操作必须异步化。

在后续两篇文章中，我们将继续深入 Handler 的稳定性治理：

- **07-Handler 稳定性风险全景**：内存泄漏、消息堆积、HandlerThread 泄漏等风险的系统性梳理。
- **08-消息机制诊断工具与监控体系**：从 Printer/Observer 到 Systrace/Perfetto，建立完整的卡顿监控与 ANR 治理体系。
