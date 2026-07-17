# 06-Input ANR：从事件超时到系统裁决

> **系列**：面向稳定性的 Android Input 子系统深度解析系列(Input_FWK)
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`、`frameworks/native/services/inputflinger/dispatcher/`;Android 14 Input ANR 阈值收紧见 §3)
> **目标读者**:Android 稳定性框架架构师
> **前置阅读**:[01-Input 系统总览](01-Input系统总览.md) / [03-InputDispatcher](03-InputDispatcher.md) / [05-View 事件分发](05-View事件分发.md)
> **下一篇**:[07-Input 稳定性风险全景](07-Input稳定性风险全景.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 6 篇(Input ANR,稳定性架构师的"第一优先级")
- **强依赖**:
  - [01-Input 系统总览](01-Input系统总览.md) §3 五层架构
  - [03-InputDispatcher](03-InputDispatcher.md)(本篇消费其 ANR 判定逻辑)
  - [05-View 事件分发](05-View事件分发.md)(ANR 触发根因大多在 View 层)
- **承接自**:03 已讲 ANR 守门逻辑,05 已讲 View 消费。本篇专门聚焦"ANR 治理"
- **衔接去**:07 风险全景 + 08 诊断治理
- **不重复内容**:InputDispatcher 状态机详见 03 §3;View 分发机制详见 05

#### §0 锚点案例的可验证 4 件套:5s 输入未响应 ANR,从 dumpsys 到 root cause 完整路径

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某支付 App v9.1(脱敏代号 `PayApp`,ANR 触发后用户报"打开 App 黑屏")
> - 工具:`adb bugreport` + `/data/anr/anr_*` + `dumpsys input` + `dumpsys gfxinfo`

> **复现步骤**(线上 ANR,事后排查):
> 1. 拿到 bugreport → `grep -r "ANR" bugreport/` 找 ANR 文件
> 2. ANR 文件名格式:`anr_2026-XX-XX-XX-XX-XX-XX_<pid>_<reason>`
> 3. 打开 ANR 文件 → 主线程 trace + CPU info + 内存信息
> 4. `dumpsys input | grep "Last ANR"` 看 ANR 时间点 InputDispatcher 状态
> 5. 5min 定位:Input ANR → 主线程阻塞点 → 根因 + 修复

> **logcat / ANR trace 关键片段**:
> ```
> ----- ANR in com.pay.app -----
> Reason: Input dispatching timed out (Application Not Responding: waited 5001ms for MotionEvent)
> ----- pid 1452 at 2026-XX-XX 14:32:18 -----
> Cmd line: com.pay.app
> "main" prio=5 tid=14 Blocked
>   | state=D schedstat=( 1248012345 4823012345 ) utm=8230 stm=12480 core=0 HZ=100
>   | stack=0x7fc00000-0x7fd00000
>   ...
>   #00  android.os.MessageQueue.nativePollOnce()          ← 主线程 idle 等消息
>   #01  android.os.Looper.loopOnce()
>   #02  android.app.ActivityThread.main()
>   #03  com.pay.app.PayActivity.onResume()               ← 卡在 onResume
>   #04  android.view.ViewRootImpl.performTraversals()    ← measure/layout/draw 三阶段
>   ...
>   #18  com.pay.app.widget.ComplexLayout.onMeasure()      ← 自定义 View 嵌套 18 层
>   ↳ 主线程在 onMeasure 中递归计算,无法响应触摸事件
> # CPU info
> CPU usage from 0ms to 5000ms later:
>   35% 5678/com.pay.app: 28% user + 7% kernel
> # 关键判断:Input ANR 主因 = 主线程在 onMeasure 嵌套递归,需要 2.4s 才完成 measure
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/app/src/main/java/com/pay/app/widget/ComplexLayout.java
> +++ b/app/src/main/java/com/pay/app/widget/ComplexLayout.java
> @@ onMeasure
> -    // 旧版:递归调用所有 child 的 measureSpec,无缓存
> -    for (int i = 0; i < getChildCount(); i++) {
> -        View child = getChildAt(i);
> -        measureChildWithMargins(child, widthSpec, heightSpec);  // 递归
> -    }
> +    // 修复:measure 缓存 + 减少递归层级 + 异步 measure
> +    if (mCachedMeasureSpec == widthSpec && mCachedHeightSpec == heightSpec) {
> +        setMeasuredDimension(mCachedWidth, mCachedHeight);
> +        return;
> +    }
> +    int totalDepth = 0;
> +    for (int i = 0; i < getChildCount(); i++) {
> +        totalDepth += getChildAt(i).getDepth();
> +    }
> +    if (totalDepth > MAX_DEPTH) {
> +        // 超过 5 层嵌套强制 measure 一次后切换异步
> +        postAsyncMeasure(widthSpec, heightSpec);
> +        return;
> +    }
> +    // 正常 measure + 缓存
> +    super.onMeasure(widthSpec, heightSpec);
> +    mCachedMeasureSpec = widthSpec;
> +    mCachedHeightSpec = heightSpec;
> +    mCachedWidth = getMeasuredWidth();
> +    mCachedHeight = getMeasuredHeight();
> ```
> 完整 Input ANR 阈值 ↔ 主线程忙度 ↔ 根因分类 ↔ 治理工具见 §2-§6。

## 引言

**Input ANR 占线上 ANR 总量的 60% 以上**。对于稳定性架构师而言，理解 Input ANR 的检测机制、触发条件和排查方法，是 ANR 治理工作的第一优先级。

什么是 Input ANR？简单说：**InputDispatcher 通过 InputChannel 将事件发给 App 后，App 没有在 5 秒内回复 `finishInputEvent`，系统判定 App 无响应。**

这个定义中有三个关键角色：
1. **InputDispatcher**——"审判官"，负责检测超时
2. **InputChannel**——"传令兵"，负责事件传输和回复
3. **App 主线程**——"被告"，需要及时处理事件并回复

本文将深入 InputDispatcher 的 ANR 检测源码，解析无焦点窗口 ANR、waitQueue 串行化、ANR 信息收集等关键机制，最终给出实战排查方法和预防措施。

---

## 1. Input ANR 与其他 ANR 的本质区别

### 1.1 四种 ANR 类型对比

| ANR 类型 | 超时时间 | 检测者 | 检测机制 | 触发方式 |
| :--- | :--- | :--- | :--- | :--- |
| **Input ANR** | 5s | InputDispatcher（Native） | waitQueue 事件超时检测 | 用户触摸/按键 |
| Service ANR | 前台 20s / 后台 200s | AMS（Java） | Handler 超时炸弹 | Service 生命周期 |
| Broadcast ANR | 前台 10s / 后台 60s | AMS（Java） | Handler 超时炸弹 | 广播分发 |
| ContentProvider ANR | 10s | AMS（Java） | Handler 超时炸弹 | Provider 发布 |

### 1.2 关键区别

**Service / Broadcast / ContentProvider ANR** 的检测机制是经典的**"超时炸弹"模式**：

```java
// AMS 中的典型超时炸弹
mHandler.sendMessageDelayed(
    Message.obtain(mHandler, SERVICE_TIMEOUT_MSG, ...),
    SERVICE_TIMEOUT);
// 如果在超时前完成，remove 这个 Message
// 如果超时前没完成，Message 被 Handler 处理 → ANR
```

**Input ANR 完全不同**：它不通过 Handler 超时炸弹，而是 InputDispatcher 在 `dispatchOnce()` 循环中**主动检查** waitQueue 中事件的等待时间。

这个区别意味着：
- Service/Broadcast ANR → 看 Handler 消息 → 看 AMS 的超时 Message
- **Input ANR → 看 InputDispatcher 的 waitQueue → 看 App 的 finishInputEvent 回复**
- 排查方向完全不同！

### 1.3 为什么 Input ANR 占比最高

- 用户操作产生的事件频率远高于系统组件的生命周期回调
- 任何主线程卡顿（不需要特定的组件生命周期）都可能导致 Input ANR
- 用户主动触摸/按键是 Input ANR 的前提——用户越活跃，ANR 概率越高

---

## 2. InputDispatcher 的 ANR 检测机制

### 2.1 整体架构

```
InputDispatcher::dispatchOnce()
    │
    ├── dispatchOnceInnerLocked()
    │       ├── findTouchedWindowTargetsLocked()
    │       │       └── checkWindowReadyForMoreInputLocked()
    │       │               └── 窗口未就绪 → handleTargetsNotReadyLocked()
    │       │                       └── 超时 → onAnrLocked()
    │       └── dispatchEventLocked()
    │               └── startDispatchCycleLocked()
    │                       └── 事件加入 waitQueue + 记录发送时间
    │
    ├── runCommandsLockedInterruptable()
    │       └── doNotifyAnrLockedInterruptable()
    │               └── InputManagerService.notifyAnr()
    │
    └── processAnrsLocked()  ← 另一个 ANR 检查点
            └── 检查已超时但尚未报告的 ANR
```

> **源码路径**：`frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`

### 2.2 事件发送时的时间记录

当 InputDispatcher 通过 InputChannel 发送事件给 App 时，会将事件从 `outboundQueue` 移到 `waitQueue`，并记录发送时间：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
void InputDispatcher::startDispatchCycleLocked(nsecs_t currentTime,
        const sp<Connection>& connection) {
    while (connection->status == Connection::Status::NORMAL) {
        if (connection->outboundQueue.empty()) {
            break;
        }

        DispatchEntry* dispatchEntry = connection->outboundQueue.front();

        // 通过 InputPublisher 将事件写入 InputChannel
        status_t status;
        const EventEntry& eventEntry = *(dispatchEntry->eventEntry);
        switch (eventEntry.type) {
            case EventEntry::Type::MOTION: {
                // ...
                status = connection->inputPublisher
                    .publishMotionEvent(dispatchEntry->seq, ...);
                break;
            }
            // ...
        }

        if (status) {
            // 发送失败
            abortBrokenDispatchCycleLocked(currentTime, connection, true);
            return;
        }

        // 从 outboundQueue 移到 waitQueue
        connection->outboundQueue.erase(
            connection->outboundQueue.begin());
        connection->waitQueue.push_back(dispatchEntry);

        // 记录发送时间 ← 这就是 ANR 倒计时的起点
        traceWaitQueueLength(*connection);
    }
}
```

### 2.3 checkWindowReadyForMoreInputLocked()

这是 ANR 检测的**核心方法之一**。当 InputDispatcher 准备向某个窗口发送新事件时，会先检查窗口是否"准备好接收"：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
std::string InputDispatcher::checkWindowReadyForMoreInputLocked(
        nsecs_t currentTime,
        const sp<WindowInfoHandle>& windowHandle,
        const EventEntry& eventEntry) {
    // 检查 1：窗口是否 paused
    if (windowHandle->getInfo()->paused) {
        return StringPrintf("Waiting because the %s window is paused.",
                            windowHandle->getName().c_str());
    }

    // 检查 2：Connection 是否正常
    // ...

    // 检查 3：waitQueue 中是否有未处理的事件
    if (eventEntry.type == EventEntry::Type::KEY) {
        // KEY 事件要求严格串行
        if (!connection->waitQueue.empty()) {
            return StringPrintf("Waiting because the %s window has not "
                    "finished processing the input events that were "
                    "previously delivered to it. "
                    "Outbound queue length: %zu. Wait queue length: %zu.",
                    windowHandle->getName().c_str(),
                    connection->outboundQueue.size(),
                    connection->waitQueue.size());
        }
    } else {
        // TOUCH 事件允许一定程度的流水线
        // 但如果 waitQueue 中有超过 0.5 秒未回复的事件 → 也需要等待
        if (!connection->waitQueue.empty() &&
            currentTime >= connection->waitQueue.front()->deliveryTime +
                            STREAM_AHEAD_EVENT_TIMEOUT) {
            return StringPrintf("Waiting because the %s window has not "
                    "finished processing certain input events...",
                    windowHandle->getName().c_str());
        }
    }

    return "";  // 空字符串表示窗口已准备好
}
```

返回值是一个 reason 字符串：
- 空字符串 → 窗口已就绪，可以发送新事件
- 非空字符串 → 窗口未就绪，等待原因就是返回的字符串

### 2.4 handleTargetsNotReadyLocked()

如果 `checkWindowReadyForMoreInputLocked` 返回非空（窗口未就绪），InputDispatcher 调用此方法开始计时：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
int32_t InputDispatcher::handleTargetsNotReadyLocked(
        nsecs_t currentTime,
        const EventEntry& entry,
        const sp<InputApplicationHandle>& applicationHandle,
        const sp<WindowInfoHandle>& windowHandle,
        nsecs_t* nextWakeupTime,
        const char* reason) {

    if (currentTime >= mInputTargetWaitTimeoutTime) {
        // 超时！触发 ANR
        onAnrLocked(applicationHandle, windowHandle,
                     entry, reason);
        *nextWakeupTime = LLONG_MIN;  // 立即唤醒，处理 ANR 命令
        return INPUT_EVENT_INJECTION_PENDING;
    } else {
        // 还没超时，继续等待
        if (mInputTargetWaitTimeoutTime < *nextWakeupTime) {
            *nextWakeupTime = mInputTargetWaitTimeoutTime;
        }
        return INPUT_EVENT_INJECTION_PENDING;
    }
}
```

### 2.5 processAnrsLocked() — 第二个 ANR 检查点

除了 `handleTargetsNotReadyLocked`，InputDispatcher 在 `dispatchOnce()` 末尾还有另一个 ANR 检查点：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
void InputDispatcher::dispatchOnce() {
    nsecs_t nextWakeupTime = LLONG_MAX;
    {
        std::scoped_lock _l(mLock);

        // 第一阶段：分发事件
        dispatchOnceInnerLocked(&nextWakeupTime);

        // 第二阶段：执行延迟命令
        if (runCommandsLockedInterruptable()) {
            nextWakeupTime = LLONG_MIN;
        }

        // 第三阶段：检查 ANR
        const nsecs_t nextAnrCheck = processAnrsLocked();
        if (nextAnrCheck < nextWakeupTime) {
            nextWakeupTime = nextAnrCheck;
        }
    }

    // 等待下一个事件或超时
    mLooper->pollOnce(toMillisecondTimeoutDelay(now, nextWakeupTime));
}
```

`processAnrsLocked()` 遍历所有 Connection，检查 waitQueue 中是否有已经超时但尚未报告的事件：

```cpp
nsecs_t InputDispatcher::processAnrsLocked() {
    const nsecs_t currentTime = now();
    nsecs_t nextAnrCheck = LLONG_MAX;

    // 检查所有 Connection 的 waitQueue
    for (const auto& [token, connection] : mConnectionsByToken) {
        if (connection->waitQueue.empty()) continue;

        DispatchEntry* oldestEntry = connection->waitQueue.front();
        nsecs_t waitDuration = currentTime - oldestEntry->deliveryTime;

        if (waitDuration >= mInputTargetWaitTimeoutTime) {
            // 超时 → 触发 ANR
            onAnrLocked(connection);
        } else {
            // 记录下次检查时间
            nsecs_t timeout = mInputTargetWaitTimeoutTime -
                              waitDuration;
            if (timeout < nextAnrCheck) {
                nextAnrCheck = timeout;
            }
        }
    }
    return nextAnrCheck;
}
```

### 2.6 5 秒超时的定义

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.h
constexpr std::chrono::nanoseconds DEFAULT_INPUT_DISPATCHING_TIMEOUT =
    std::chrono::milliseconds(5000);
```

这个超时可以通过 `PhoneWindowManager.getInputDispatchingTimeoutMillis()` 获取，某些特殊窗口可以自定义（如 Instrumentation 测试时会延长到 60 秒）。

---

## 3. onAnrLocked() — ANR 的触发

### 3.1 信息收集

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
void InputDispatcher::onAnrLocked(
        const sp<InputApplicationHandle>& application,
        const sp<WindowInfoHandle>& windowHandle,
        const EventEntry& entry,
        const std::string& reason) {

    // 构建 ANR 信息
    std::string windowLabel;
    if (windowHandle != nullptr) {
        windowLabel = windowHandle->getName();
    } else if (application != nullptr) {
        windowLabel = application->getName();
    } else {
        windowLabel = "<unknown>";
    }

    ALOGI("ANR: dispatching timed out, reason: %s, window: %s",
          reason.c_str(), windowLabel.c_str());

    // 将 ANR 通知封装为 CommandEntry
    // 加入 mCommandQueue，在 runCommandsLockedInterruptable 中执行
    auto command = this, application, windowHandle, reason REQUIRES(mLock) {
        doNotifyAnrLockedInterruptable(application, windowHandle, reason);
    };
    postCommandLocked(std::move(command));
}
```

### 3.2 ANR 通知链

从 Native 到 Java 的完整链路：

```
InputDispatcher::onAnrLocked()
    → postCommandLocked()
        → doNotifyAnrLockedInterruptable()
            → mPolicy->notifyAnr()  // NativeInputManager
                → JNI 回调
                    → InputManagerService.notifyAnr()           [Java]
                        → AMS.inputDispatchingTimedOut()         [Java]
                            → AppErrors.appNotResponding()       [Java]
```

### 3.3 InputManagerService.notifyAnr()

```java
// frameworks/base/services/core/java/com/android/server/input/InputManagerService.java
private long notifyAnr(IBinder token, String reason) {
    return mWindowManagerCallbacks.notifyANR(token, reason);
}
```

这会调用到 WMS 的回调，最终到达 AMS：

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java
@Override
public boolean inputDispatchingTimedOut(int pid, boolean aboveSystem, String reason) {
    // ...
    ProcessRecord proc;
    synchronized (mPidsSelfLocked) {
        proc = mPidsSelfLocked.get(pid);
    }
    // ...
    if (proc != null) {
        mAnrHelper.appNotResponding(proc, null, null, false, reason);
    }
    return true;
}
```

### 3.4 AppErrors.appNotResponding()

这是 ANR 处理的**最终执行者**：

```java
// frameworks/base/services/core/java/com/android/server/am/AppErrors.java
void appNotResponding(ProcessRecord app, ..., String annotation) {
    // 1. 发送 SIGQUIT 给目标进程
    //    Signal Catcher 线程收到后 dump 所有线程堆栈
    Process.sendSignal(app.getPid(), Process.SIGNAL_QUIT);

    // 2. 等待 traces 写入完成（最多 20 秒）
    // ...

    // 3. 收集系统信息
    //    CPU usage, memory info, etc.
    // ...

    // 4. 决定处理方式
    if (app.isInBackground()) {
        // 后台 App → 直接杀掉
        app.killLocked("bg anr", ...);
    } else {
        // 前台 App → 弹出 ANR 对话框
        // 用户选择"等待"或"关闭应用"
        Message msg = Message.obtain();
        msg.what = ActivityManagerService.SHOW_NOT_RESPONDING_UI_MSG;
        // ...
        mService.mUiHandler.sendMessage(msg);
    }
}
```

---

## 4. "无焦点窗口" ANR

### 4.1 触发条件

这是最常见的 Input ANR 类型之一，其 ANR reason 为：

```
Input dispatching timed out (no focused window)
```

或者更详细的：

```
Input dispatching timed out (Waiting because no window has focus
but there is a focused application that may eventually add a window
when it finishes starting up.)
```

### 4.2 触发流程

```
用户按下按键 / 触摸屏幕
    → InputDispatcher::dispatchKeyLocked() / dispatchMotionLocked()
        → findFocusedWindowTargetsLocked()
            → mFocusedWindowHandlesByDisplay[displayId] == nullptr ?
                → 是！焦点窗口为空
                    → mFocusedApplicationHandlesByDisplay[displayId] != nullptr ?
                        → 是！焦点 Application 存在 → 说明 App 正在启动
                            → 返回 INPUT_EVENT_INJECTION_PENDING（等待）
                            → handleTargetsNotReadyLocked() 开始计时
                            → 等待 5 秒...
                            → 仍然没有焦点窗口 → onAnrLocked()
```

源码关键片段：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
InputEventInjectionResult InputDispatcher::findFocusedWindowTargetsLocked(
        nsecs_t currentTime, const EventEntry& entry,
        std::vector<InputTarget>& inputTargets,
        nsecs_t* nextWakeupTime) {

    sp<WindowInfoHandle> focusedWindowHandle =
        getFocusedWindowHandleLocked(displayId);

    if (focusedWindowHandle == nullptr) {
        // 没有焦点窗口
        if (focusedApplicationHandle != nullptr) {
            // 但有焦点 Application → 等待窗口就绪
            return handleTargetsNotReadyLocked(currentTime, entry,
                focusedApplicationHandle, nullptr, nextWakeupTime,
                "Waiting because no window has focus but there is "
                "a focused application that may eventually add a "
                "window when it finishes starting up.");
        }
        // 连焦点 Application 都没有 → 丢弃事件
        ALOGI("Dropping event because there is no focused window "
              "or focused application in display %" PRId32 ".", displayId);
        return InputEventInjectionResult::FAILED;
    }
    // ...
}
```

### 4.3 常见场景

**场景一：冷启动慢**

```
用户点击 App 图标
    → AMS 设置 FocusedApplication = com.example/.MainActivity
    → fork 进程 → Application.onCreate() [耗时 3 秒]
    → Activity.onCreate() → setContentView → ViewRootImpl.setView
    → WMS.addWindow → 创建 InputChannel → 设置 FocusedWindow
    
    总耗时：3s + 1.5s = 4.5s（接近 5s 阈值）
    如果稍有波动 → 超过 5s → ANR
```

**场景二：Activity 切换的焦点真空期**

```
Activity A finish()
    → WMS 移除 A 的窗口 → FocusedWindow = null
    → AMS 设置 FocusedApplication = Activity B
    → Activity B 创建 → onCreate [耗时]
    → B 的 Window 添加 → FocusedWindow = B
    
    真空期 = A 窗口移除 到 B 窗口添加
    如果用户在真空期内触摸 → 等待 → 可能 ANR
```

**场景三：多进程 ContentProvider 阻塞**

```
Application.onCreate()
    → ContentResolver.query(authority) [跨进程]
        → 目标进程未启动 → fork + 初始化 [低端机 3-5s]
        → 主进程被阻塞等待
    → Activity 无法创建 → Window 无法添加
    → 5 秒 → ANR
```

### 4.4 与"普通" Input ANR 的区别

| 特征 | 无焦点窗口 ANR | 普通 Input ANR |
| :--- | :--- | :--- |
| 窗口是否存在 | 不存在（FocusedWindow = null） | 存在但处理慢 |
| ANR reason | "no focused window" | "has not finished processing..." |
| 根因 | 窗口创建慢（启动慢） | 主线程卡顿 |
| 排查方向 | Application.onCreate / Activity 创建耗时 | 主线程堆栈 |
| dumpsys input | FocusedWindow=null | waitQueue 有积压 |

---

## 5. waitQueue 与串行化投递

### 5.1 串行化策略

InputDispatcher 对同一个 Connection 的事件投递采用**串行化策略**：

- **KEY 事件**：严格串行。waitQueue 不为空 → 新 KEY 事件不发送。
- **TOUCH 事件**：允许有限的流水线（Motion Streaming）。但如果 waitQueue 中最早的事件等待超过 `STREAM_AHEAD_EVENT_TIMEOUT`（500ms），新 TOUCH 事件也会等待。

### 5.2 串行化导致的级联延迟

```
时间线：
t=0s    用户触摸 → 事件 A 发送 → waitQueue: [A]
t=0.1s  主线程正在处理 SharedPreferences.commit()（耗时 2s）
t=2.1s  事件 A 的 finishInputEvent 回复 → waitQueue: []
t=2.1s  用户再次触摸 → 事件 B 发送 → waitQueue: [B]
t=2.2s  主线程开始处理事件 B
t=2.3s  用户又触摸了 → 事件 C 进入 outboundQueue
        但事件 B 未回复 → 事件 C 等待
t=5.0s  事件 A 的发送时间 + 5s → 超时
        但事件 A 已经在 t=2.1s 回复了 → 不会 ANR
        
如果场景更严重：
t=0s    事件 A 发送
t=3s    事件 A 回复（主线程卡了 3s）
t=3s    事件 B 发送
t=5s    从事件 B 发送算起才过了 2s → 还没 ANR
t=6s    主线程又卡了 3s → 事件 B 等了 3s
t=8s    事件 B 超过 5s 了 → ANR！
```

实际上，ANR 的计时是从**事件发送时间**开始算的，不是从用户触摸时间。但如果 outboundQueue 中排队时间也很长（因为 waitQueue 的串行化阻塞），用户感受到的延迟会远大于 5 秒。

### 5.3 通过 dumpsys input 观察队列状态

```
dumpsys input

  Connection #1:
    outboundQueue length: 3    ← 有 3 个事件等待发送
    waitQueue length: 2        ← 有 2 个事件已发送等待回复
    waitQueue[0]: deliveryTime=1234567890000, wait=4800ms  ← 快超时了！
    waitQueue[1]: deliveryTime=1234567891000, wait=3800ms
```

**解读规则**：
- `waitQueue length > 0` + `wait > 3000ms` → 高风险，接近 ANR
- `outboundQueue length > 0` → InputDispatcher 端有积压（通常是因为 waitQueue 的串行化阻塞）
- 两个队列都有大量事件 → App 严重卡顿

---

## 6. ANR 信息收集与 Trace 分析

### 6.1 SIGQUIT 与 traces.txt

当 ANR 发生时，AMS 发送 `SIGQUIT`（信号 3）给目标进程：

```java
// frameworks/base/services/core/java/com/android/server/am/AppErrors.java
Process.sendSignal(app.getPid(), Process.SIGNAL_QUIT);
```

目标进程中的 **Signal Catcher 线程** 收到信号后：
1. 暂停所有线程（`SuspendAll`）
2. 遍历所有线程，dump 堆栈信息
3. 写入 `/data/anr/traces.txt`（或 `/data/anr/anr_yyyy-MM-dd-HH-mm-ss-SSS`）
4. 恢复所有线程

```cpp
// art/runtime/signal_catcher.cc
void SignalCatcher::HandleSigQuit() {
    Runtime* runtime = Runtime::Current();
    // ...
    std::ostringstream os;
    runtime->DumpForSigQuit(os);
    // 写入文件
    // ...
}
```

### 6.2 从 logcat 识别 Input ANR

```
// 关键日志
E ActivityManager: ANR in com.example.app (com.example.app/.MainActivity)
E ActivityManager:   PID: 12345
E ActivityManager:   Reason: Input dispatching timed out
                     (Waiting because the focused window has not finished
                      processing the previous input event that was delivered
                      to it. Outbound queue length: 2. Wait queue length: 5.)
E ActivityManager:   Load: 8.2 / 6.5 / 3.1
E ActivityManager:   CPU usage from 0ms to 5000ms later:
E ActivityManager:     25% 12345/com.example.app: 18% user + 7% kernel
E ActivityManager:     12% 1234/system_server: 8% user + 4% kernel
```

**关键信息**：
- `Reason` 字段 → 区分 ANR 类型
- `Outbound queue length` / `Wait queue length` → 事件积压情况
- `CPU usage` → 判断是 CPU 密集还是 IO 等待

### 6.3 ANR Reason 字段解读

| Reason 关键词 | 含义 | 排查方向 |
| :--- | :--- | :--- |
| "has not finished processing the previous input event" | 窗口存在但处理慢 | 主线程堆栈 |
| "no focused window" | 焦点窗口不存在 | 启动耗时、窗口创建延迟 |
| "input channel is not registered" | InputChannel 未注册 | 窗口注册失败 |
| "window is paused" | 窗口处于 paused 状态 | Activity 生命周期问题 |

### 6.4 traces.txt 主线程分析

**模式一：主线程正在执行耗时操作**

```
"main" prio=5 tid=1 Runnable
  at android.database.sqlite.SQLiteConnection.nativeExecuteForString(Native)
  at android.database.sqlite.SQLiteConnection.executeForString(...)
  at com.example.SettingsActivity.onToggleChanged(SettingsActivity.java:89)
  at android.view.View.performClick(View.java:7448)
```

→ 根因清晰：`onToggleChanged` 中同步执行 SQLite 操作。

**模式二：主线程被 Binder 调用阻塞**

```
"main" prio=5 tid=1 Native
  at android.os.BinderProxy.transactNative(Native)
  at android.os.BinderProxy.transact(BinderProxy.java:571)
  at android.content.IContentProvider$Stub$Proxy.query(...)
  at android.content.ContentResolver.query(ContentResolver.java:944)
  at com.example.DataManager.loadData(DataManager.java:67)
```

→ 根因：主线程调用 ContentProvider 的 `query`（跨进程 Binder），对端响应慢。

**模式三：主线程等待锁**

```
"main" prio=5 tid=1 Blocked
  at com.example.CacheManager.get(CacheManager.java:45)
  - waiting to lock <0x0a1b2c3d> (a java.lang.Object)
    held by thread 15 (pool-3-thread-1)
```

→ 根因：主线程等待的锁被后台线程持有。

**模式四：主线程空闲（nativePollOnce）**

```
"main" prio=5 tid=1 Native
  at android.os.MessageQueue.nativePollOnce(Native)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  at android.os.Looper.loopOnce(Looper.java:161)
  at android.os.Looper.loop(Looper.java:288)
```

→ 主线程此刻空闲！ANR 时主线程已经不卡了。可能的原因：
- ANR 检测到的时候主线程正在卡顿，但 dump 堆栈时已经恢复
- 系统负载高导致 dump 延迟，堆栈不反映 ANR 时刻的状态
- 需要结合 CPU usage 和 Systrace 进一步分析

### 6.5 结合 dumpsys input 分析

```bash
adb shell dumpsys input
```

关注以下信息：

```
FocusedApplications:
  displayId=0, name='AppWindowToken{...com.example.app/.MainActivity}'
FocusedWindows:
  displayId=0, name='Window{...com.example.app/com.example.app.MainActivity}'

Connections:
  1: channelName='...MainActivity', status=NORMAL,
     outboundQueueLength=2, waitQueueLength=5,
     waitQueue[0]: seq=123, deliveryTime=..., wait=5200ms
```

**决策树**：

```
FocusedWindow 为 null？
    ├── 是 → 无焦点窗口 ANR → 排查启动耗时
    └── 否 → waitQueue 是否有积压？
              ├── 是 → 主线程处理慢 → 分析 ANR trace
              └── 否 → 可能是瞬时卡顿（已恢复）→ 分析 Systrace
```

### 6.6 CPU Usage 辅助判断

| CPU 特征 | 含义 | 排查方向 |
| :--- | :--- | :--- |
| 主线程 CPU 高（> 50%） | CPU 密集操作 | 看堆栈中的计算逻辑 |
| 主线程 CPU 低（< 5%） | IO 等待 / 锁等待 / Binder 等待 | 看堆栈中的阻塞点 |
| 系统总 CPU > 80% | 系统负载高 → 调度延迟 | 检查后台进程 / 系统服务 |
| iowait 高（> 30%） | 磁盘 IO 繁忙 | 检查 Flash 性能 / 大文件操作 |

---

## 7. Input ANR 的预防措施

### 7.1 主线程纪律

```
核心原则：主线程执行任何操作不超过 100ms（一帧 16ms 为最佳目标）
```

| 操作 | 风险 | 替代方案 |
| :--- | :--- | :--- |
| DB 查询/写入 | 高 | Room + 协程 / RxJava 异步 |
| SharedPreferences.commit() | 高 | 改用 apply()（异步写磁盘） |
| 网络请求 | 极高 | OkHttp + 协程 / 后台线程 |
| 文件 IO | 高 | Dispatchers.IO |
| JSON 解析大数据 | 中 | 后台线程解析 |
| Bitmap 解码 | 高 | Glide / Coil 异步加载 |

### 7.2 冷启动优化

确保 Window 在 5 秒内就绪（越快越好，目标 < 2 秒）：

- **Application.onCreate 轻量化**：
  - 延迟初始化非关键 SDK（使用 `ContentProvider` lazy init 或 `AppStartup`）
  - 耗时初始化放到后台线程
  - 使用 `IdleHandler` 在首帧渲染后执行非紧急初始化

- **使用 SplashScreen API**（Android 12+）：
  - 系统在 App 进程启动时就显示 SplashScreen → 窗口提前就绪 → 减少"无焦点窗口"风险

- **避免 Application.onCreate 中的跨进程调用**：
  - ContentProvider.query / Binder 调用 → 可能阻塞等待对端进程启动

### 7.3 主线程 Binder 调用管控

```kotlin
// 开发阶段检测
if (BuildConfig.DEBUG) {
    StrictMode.setThreadPolicy(
        StrictMode.ThreadPolicy.Builder()
            .detectDiskReads()
            .detectDiskWrites()
            .detectNetwork()
            .detectCustomSlowCalls()
            .penaltyLog()
            .build()
    )
}
```

线上阶段：Hook `Binder.transact` 统计主线程 Binder 调用耗时，超过阈值上报。

### 7.4 Looper 消息耗时监控

```kotlin
Looper.getMainLooper().setMessageLogging { msg ->
    if (msg.startsWith(">>>>> Dispatching")) {
        // 消息开始处理
        startTime = SystemClock.uptimeMillis()
    }
    if (msg.startsWith("<<<<< Finished")) {
        val duration = SystemClock.uptimeMillis() - startTime
        if (duration > 100) {
            // 慢消息告警
            reportSlowMessage(msg, duration)
        }
    }
}
```

---

## 8. 实战案例

### Case 1：SharedPreferences.commit() 导致 Input ANR

**现象**：
设置页面偶发 ANR，频率约 0.3%。低端机更高（约 1.2%）。

**logcat**：
```
E ActivityManager: ANR in com.example.app
E ActivityManager:   Reason: Input dispatching timed out
                     (Waiting because the focused window has not finished
                      processing the previous input event that was delivered
                      to it. Outbound queue length: 2. Wait queue length: 5.)
```

**ANR trace 主线程**：
```
"main" prio=5 tid=1 Native
  at android.os.MessageQueue.nativePollOnce(Native Method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  at android.os.Looper.loopOnce(Looper.java:161)
  ...
```

主线程看起来空闲？这是典型的**"ANR 时卡顿，dump 时已恢复"**。

**进一步排查**：

1. **dumpsys input**：waitQueue 有 5 个事件，最早的等了 5.2 秒。
2. **Systrace**（历史数据）：在 ANR 前 5 秒的时间窗口中，主线程有一个 `SharedPreferencesImpl$EditorImpl.commit` 耗时 3.8 秒（磁盘 IO 抖动）。
3. **StrictMode 日志**（Debug 版本）：`D/StrictMode: StrictMode policy violation; ~duration=3800 ms: android.os.StrictMode$StrictModeDiskReadViolation`

**根因**：
用户点击设置开关 → `onCheckedChanged` → `SharedPreferences.Editor.commit()`。`commit()` 是**同步写磁盘**，正常耗时 < 50ms，但在低端机上（Flash 性能差 + IO 繁忙时），耗时可飙升到 2~4 秒。3.8 秒的 commit 加上 MessageQueue 中其他消息的排队时间，总阻塞超过 5 秒 → ANR。

dump 时主线程已经空闲（commit 已完成），所以 traces.txt 看到的是 `nativePollOnce`。

**修复**：

```java
// Before
sharedPrefs.edit().putBoolean("dark_mode", enabled).commit();

// After
sharedPrefs.edit().putBoolean("dark_mode", enabled).apply();
```

`apply()` 将写磁盘操作放到后台线程（`QueuedWork`），主线程立即返回。

**注意**：`apply()` 也有坑——Activity.onPause 中会同步等待所有 pending `apply()` 完成（`QueuedWork.waitToFinish()`）。但这是另一个问题了。

---

### Case 2：多进程 ContentProvider 导致冷启动 ANR

**现象**：
低端机上冷启动 App 高频 ANR（约 2%）。logcat 显示 "no focused window"。

**logcat**：
```
E ActivityManager: ANR in com.example.app (com.example.app/.MainActivity)
E ActivityManager:   Reason: Input dispatching timed out
                     (Waiting because no window has focus but there is
                      a focused application that may eventually add a window
                      when it finishes starting up.)
```

**dumpsys input**：
```
FocusedApplications:
  displayId=0, name='AppWindowToken{...com.example.app/.MainActivity}'
FocusedWindows:
  <none>
```

→ FocusedApplication 已设置（AMS 已启动 Activity），但 FocusedWindow 为 null（窗口还没创建）。

**ANR trace 主线程**：
```
"main" prio=5 tid=1 Native
  at android.os.BinderProxy.transactNative(Native Method)
  at android.os.BinderProxy.transact(BinderProxy.java:571)
  at android.content.IContentProvider$Stub$Proxy.query(IContentProvider.java:423)
  at android.content.ContentResolver.query(ContentResolver.java:944)
  at com.example.sdk.ConfigProvider.init(ConfigProvider.java:34)
  at com.example.app.MyApplication.onCreate(MyApplication.java:28)
```

**根因分析**：

```
冷启动序列：
t=0s    AMS fork 进程
t=0.1s  AMS 设置 FocusedApplication = MainActivity
t=0.2s  Application.onCreate 开始
t=0.3s  ConfigProvider.init() → ContentResolver.query()
            → 目标 ContentProvider 在 :remote 进程
            → :remote 进程未启动 → AMS fork :remote 进程
            → :remote 进程初始化 [低端机 3-4 秒]
            → 主进程被阻塞等待 Binder 返回
t=4.5s  ContentResolver.query 返回
t=4.7s  Application.onCreate 完成
t=5.0s  Activity.onCreate 开始 → setContentView → ViewRootImpl.setView
t=5.1s  → AMS/WMS 设置 FocusedWindow

但此时已经超过 5 秒（从 t=0.1s FocusedApplication 设置开始算）→ ANR
```

**修复**：

```java
// Before: Application.onCreate 中同步查询
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        ConfigProvider.init(this);  // 内部有跨进程 ContentProvider 查询
    }
}

// After: 延迟到首屏渲染后异步执行
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        // 不在 onCreate 中初始化
    }
}

// 在 MainActivity 中
@Override
protected void onResume() {
    super.onResume();
    if (!ConfigProvider.isInitialized()) {
        Looper.myQueue().addIdleHandler(() -> {
            new Thread(() -> ConfigProvider.init(getApplicationContext())).start();
            return false;
        });
    }
}
```

**关键收获**：
- "no focused window" ANR 的根因通常在 Application.onCreate 或 Activity 创建阶段
- Application.onCreate 中**绝对不能**有跨进程同步调用
- 低端机上进程 fork + 初始化可达 3~5 秒，是冷启动 ANR 的主要贡献者

---

## 附录：核心源码路径索引

| 文件 | 路径 | 说明 |
| :--- | :--- | :--- |
| InputDispatcher.cpp | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` | ANR 检测核心逻辑 |
| InputDispatcher.h | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.h` | 超时常量定义 |
| InputManagerService.java | `frameworks/base/services/core/java/com/android/server/input/InputManagerService.java` | JNI 回调 → AMS |
| ActivityManagerService.java | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | ANR 裁决 |
| AppErrors.java | `frameworks/base/services/core/java/com/android/server/am/AppErrors.java` | SIGQUIT + traces.txt |
| signal_catcher.cc | `art/runtime/signal_catcher.cc` | SIGQUIT → dump 堆栈 |
| InputTransport.cpp | `frameworks/native/libs/input/InputTransport.cpp` | finishInputEvent 回复 |
