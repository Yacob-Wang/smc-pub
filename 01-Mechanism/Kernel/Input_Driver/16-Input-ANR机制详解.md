# Input ANR 机制详解

## 引言

ANR (Application Not Responding) 是 Android 系统的应用无响应检测机制。Input ANR 是最常见的 ANR 类型之一，发生在应用未能及时处理输入事件时。本文将深入分析 Input ANR 的检测原理、超时机制和问题分析方法。

---

## 1. Input ANR 概述

### 1.1 ANR 类型

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           ANR 类型                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Input ANR (本文重点)                                                   │
│  ├── 窗口无响应 ANR: 应用未在超时内处理输入事件                        │
│  └── 无焦点窗口 ANR: 有焦点应用但无焦点窗口                            │
│                                                                         │
│  其他 ANR 类型:                                                         │
│  ├── Service ANR: 前台 Service 20s, 后台 Service 200s                  │
│  ├── Broadcast ANR: 前台广播 10s, 后台广播 60s                         │
│  └── ContentProvider ANR: 10s                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Input ANR 超时配置

```java
// frameworks/base/core/res/res/values/config.xml

<!-- 输入事件分发超时 (毫秒) -->
<integer name="config_inputEventDispatchTimeout">5000</integer>

<!-- 无焦点窗口超时 (毫秒) - 有焦点应用但没有焦点窗口 -->
<integer name="config_noFocusedWindowTimeout">5000</integer>
```

| 超时类型 | 默认值 | 描述 |
|---------|-------|------|
| 事件分发超时 | 5 秒 | 事件发送后等待处理完成的超时 |
| 无焦点窗口超时 | 5 秒 | 有焦点应用但无焦点窗口的超时 |

---

## 2. ANR 检测机制

### 2.1 InputDispatcher ANR 检测架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        InputDispatcher                                   │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │                       ANR 检测                                      ││
│  │                                                                     ││
│  │  1. 事件分发超时检测                                                ││
│  │     └── 监控 Connection.waitQueue                                  ││
│  │                                                                     ││
│  │  2. 无焦点窗口超时检测                                              ││
│  │     └── 有焦点应用但无焦点窗口时计时                               ││
│  │                                                                     ││
│  │  3. ANR 状态管理                                                   ││
│  │     └── mAnrTracker                                                ││
│  │                                                                     ││
│  └────────────────────────────────────────────────────────────────────┘│
│                              │                                          │
│                              │ notifyNoFocusedWindowAnr()               │
│                              │ notifyWindowUnresponsive()               │
│                              ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │                    InputManagerService                              ││
│  │                           │                                         ││
│  │                           ▼                                         ││
│  │                   ActivityManagerService                           ││
│  │                     appNotResponding()                             ││
│  └────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 事件分发超时检测

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

void InputDispatcher::dispatchOnce() {
    nsecs_t nextWakeupTime = LONG_LONG_MAX;
    
    { // acquire lock
        std::scoped_lock _l(mLock);
        
        // 分发事件
        dispatchOnceInnerLocked(&nextWakeupTime);
        
        // 检查 ANR
        processAnrsLocked();
        
    } // release lock
    
    // 等待下一次唤醒
    nsecs_t currentTime = now();
    int timeoutMillis = toMillisecondTimeoutDelay(currentTime, nextWakeupTime);
    mLooper->pollOnce(timeoutMillis);
}

void InputDispatcher::processAnrsLocked() {
    nsecs_t currentTime = now();
    
    // 检查无响应的连接
    for (auto& [token, connection] : mConnectionsByToken) {
        if (connection->status != Connection::Status::NORMAL) {
            continue;
        }
        
        // 检查等待队列
        if (!connection->waitQueue.empty()) {
            DispatchEntry* entry = connection->waitQueue.front();
            
            // 计算等待时间
            nsecs_t waitDuration = currentTime - entry->deliveryTime;
            nsecs_t timeout = connection->inputChannel->getDispatchingTimeout();
            
            if (waitDuration >= timeout) {
                // 超时! 触发 ANR
                onAnrLocked(connection);
            }
        }
    }
    
    // 检查无焦点窗口超时
    if (mNoFocusedWindowTimeoutTime != LONG_LONG_MAX &&
            currentTime >= mNoFocusedWindowTimeoutTime) {
        
        // 获取焦点应用
        std::shared_ptr<InputApplicationHandle> focusedApp = 
            getValueByKey(mFocusedApplicationHandlesByDisplay, mFocusedDisplayId);
        
        if (focusedApp != nullptr) {
            onAnrLocked(focusedApp);
        }
        
        // 重置超时
        mNoFocusedWindowTimeoutTime = LONG_LONG_MAX;
    }
}
```

### 2.3 窗口无响应 ANR

```cpp
void InputDispatcher::onAnrLocked(const sp<Connection>& connection) {
    // 标记连接状态
    connection->inputPublisherBlocked = true;
    
    // 获取窗口信息
    sp<WindowInfoHandle> windowHandle = 
        getWindowHandleLocked(connection->inputChannel->getToken());
    
    if (windowHandle != nullptr) {
        // 构建 ANR 信息
        std::string reason = "Window not responding";
        
        // 通知策略层
        mPolicy->notifyWindowUnresponsive(
            connection->inputChannel->getToken(),
            reason);
    }
}
```

### 2.4 无焦点窗口 ANR

```cpp
void InputDispatcher::onAnrLocked(
        const std::shared_ptr<InputApplicationHandle>& application) {
    
    // 构建 ANR 信息
    std::string reason = "No focused window";
    
    // 通知策略层
    mPolicy->notifyNoFocusedWindowAnr(application);
}

// 设置无焦点窗口超时
void InputDispatcher::setNoFocusedWindowTimeoutLocked(nsecs_t timeout) {
    if (mFocusedApplicationHandlesByDisplay.empty()) {
        // 没有焦点应用, 不需要超时
        mNoFocusedWindowTimeoutTime = LONG_LONG_MAX;
        return;
    }
    
    mNoFocusedWindowTimeoutTime = now() + timeout;
}
```

---

## 3. ANR 处理流程

### 3.1 NativeInputManager 回调

```cpp
// frameworks/base/services/core/jni/com_android_server_input_InputManagerService.cpp

void NativeInputManager::notifyWindowUnresponsive(
        const sp<IBinder>& token, const std::string& reason) {
    
    JNIEnv* env = jniEnv();
    
    ScopedLocalRef<jstring> reasonStr(env, env->NewStringUTF(reason.c_str()));
    
    // 回调 Java 层
    env->CallVoidMethod(mServiceObj,
        gInputManagerServiceClassInfo.notifyWindowUnresponsive,
        token, reasonStr.get());
}

void NativeInputManager::notifyNoFocusedWindowAnr(
        const std::shared_ptr<InputApplicationHandle>& applicationHandle) {
    
    JNIEnv* env = jniEnv();
    
    jobject tokenObj = applicationHandle->getApplicationToken();
    
    env->CallVoidMethod(mServiceObj,
        gInputManagerServiceClassInfo.notifyNoFocusedWindowAnr,
        tokenObj);
}
```

### 3.2 InputManagerService 处理

```java
// frameworks/base/services/core/java/com/android/server/input/InputManagerService.java

private void notifyWindowUnresponsive(IBinder token, String reason) {
    mWindowManagerCallbacks.notifyWindowUnresponsive(token, reason);
}

private void notifyNoFocusedWindowAnr(IBinder applicationToken) {
    mWindowManagerCallbacks.notifyNoFocusedWindowAnr(applicationToken);
}
```

### 3.3 ActivityManagerService ANR 处理

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

void appNotResponding(ProcessRecord app, 
                      String activityShortComponentName,
                      ApplicationInfo appInfo,
                      String parentShortComponentName,
                      WindowProcessController parentProcess,
                      boolean aboveSystem,
                      String annotation) {
    
    // 1. 记录 ANR 时间
    final long anrTime = SystemClock.uptimeMillis();
    
    // 2. 检查是否应该跳过 ANR
    if (mAtmInternal.isLaunchingActivity(app.getWindowProcessController())) {
        // 正在启动 Activity, 跳过
        return;
    }
    
    // 3. 获取进程信息
    synchronized (this) {
        // 记录 ANR 状态
        app.setNotResponding(true);
        
        // 获取 CPU 使用信息
        updateCpuStatsNow();
    }
    
    // 4. 收集诊断信息
    StringBuilder info = new StringBuilder();
    info.append("ANR in ").append(app.processName);
    if (activityShortComponentName != null) {
        info.append(" (").append(activityShortComponentName).append(")");
    }
    info.append("\n");
    info.append("PID: ").append(app.pid).append("\n");
    info.append("Reason: ").append(annotation).append("\n");
    
    // 5. Dump 各种信息
    // - 主线程堆栈
    // - 内存信息
    // - CPU 信息
    final File tracesFile = dumpStackTraces(pids, ...);
    
    // 6. 显示 ANR 对话框或杀死进程
    if (mAtmInternal.canShowErrorDialogs()) {
        // 显示 ANR 对话框
        Message msg = Message.obtain();
        msg.what = SHOW_NOT_RESPONDING_UI_MSG;
        msg.obj = new AppNotRespondingDialog.Data(app, ...);
        mUiHandler.sendMessage(msg);
    } else {
        // 后台进程, 直接杀死
        app.kill("ANR", ApplicationExitInfo.REASON_ANR, true);
    }
    
    // 7. 记录到 DropBox
    addErrorToDropBox("anr", app, ...);
}
```

---

## 4. ANR Traces 分析

### 4.1 traces.txt 文件

```
----- pid 12345 at 2024-01-15 10:30:45 -----
Cmd line: com.example.app
Build fingerprint: 'google/sunfish/sunfish:13/TQ1A.230105.002/...'

DALVIK THREADS (18):
"main" prio=5 tid=1 Sleeping
  | group="main" sCount=1 dsCount=0 flags=1 obj=0x73a0b0a8 self=0x7a...
  | sysTid=12345 nice=-10 cgrp=default sched=0/0 handle=0x7a...
  | state=S schedstat=( 1234567890 234567890 1234 ) utm=100 stm=23 core=2 HZ=100
  | stack=0x7ffc000000-0x7ffc002000 stackSize=8192KB
  | held mutexes=
  at java.lang.Thread.sleep(Native method)
  - sleeping on <0x0a1b2c3d> (a java.lang.Object)
  at java.lang.Thread.sleep(Thread.java:450)
  at java.lang.Thread.sleep(Thread.java:355)
  at com.example.app.MainActivity.onTouchEvent(MainActivity.java:123)
  at android.view.View.dispatchTouchEvent(View.java:14309)
  at android.view.ViewGroup.dispatchTransformedTouchEvent(ViewGroup.java:3118)
  at android.view.ViewGroup.dispatchTouchEvent(ViewGroup.java:2799)
  ...
  at android.app.Activity.dispatchTouchEvent(Activity.java:4084)
  at android.view.Window$Callback.dispatchTouchEvent(Window.java:3057)
  at android.view.ViewRootImpl$ViewPostImeInputStage.processPointerEvent(ViewRootImpl.java:6123)
  at android.view.ViewRootImpl$ViewPostImeInputStage.onProcess(ViewRootImpl.java:5926)
  at android.view.ViewRootImpl$InputStage.deliver(ViewRootImpl.java:5397)
  ...
  at android.view.ViewRootImpl$WindowInputEventReceiver.onInputEvent(ViewRootImpl.java:6291)
  at android.view.InputEventReceiver.dispatchInputEvent(InputEventReceiver.java:220)
  at android.os.MessageQueue.nativePollOnce(Native method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  at android.os.Looper.loop(Looper.java:183)
  at android.app.ActivityThread.main(ActivityThread.java:7656)
  at java.lang.reflect.Method.invoke(Native method)
  at com.android.internal.os.RuntimeInit$MethodAndArgsCaller.run(RuntimeInit.java:592)
  at com.android.internal.os.ZygoteInit.main(ZygoteInit.java:947)

"Binder:12345_1" prio=5 tid=8 Native
  ...
```

### 4.2 关键信息解读

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      ANR Traces 关键信息                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  线程状态                                                               │
│  ├── Sleeping: 线程休眠 (Thread.sleep)                                 │
│  ├── Waiting: 等待锁 (Object.wait)                                     │
│  ├── Blocked: 被阻塞 (等待获取锁)                                      │
│  ├── Native: 执行 Native 代码                                          │
│  └── Runnable: 可运行状态                                              │
│                                                                         │
│  关键标识                                                               │
│  ├── "main" prio=5 tid=1: 主线程                                       │
│  ├── sysTid=12345: 系统线程 ID                                         │
│  ├── state=S: 内核线程状态 (S=Sleep, R=Running)                        │
│  └── held mutexes: 持有的锁                                            │
│                                                                         │
│  调用栈分析                                                             │
│  ├── 从下往上读: 调用链路                                              │
│  ├── at xxx.xxx: 执行位置                                              │
│  ├── - waiting on <addr>: 等待的对象                                   │
│  └── - locked <addr>: 持有的锁                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 常见 Input ANR 原因

### 5.1 主线程阻塞

```java
// 错误示例: 在主线程进行耗时操作

@Override
public boolean onTouchEvent(MotionEvent event) {
    // 网络请求 - 绝对不能在主线程!
    HttpURLConnection connection = ...;
    InputStream is = connection.getInputStream();  // ANR!
    
    // 数据库操作
    Cursor cursor = db.rawQuery(...);  // 可能 ANR
    
    // 文件操作
    FileInputStream fis = new FileInputStream(largeFile);  // 可能 ANR
    
    // 复杂计算
    for (int i = 0; i < 10000000; i++) { ... }  // ANR!
}
```

### 5.2 死锁

```java
// 死锁示例

class DeadlockExample {
    private final Object lockA = new Object();
    private final Object lockB = new Object();
    
    // 线程 1
    void method1() {
        synchronized (lockA) {
            Thread.sleep(100);
            synchronized (lockB) {
                // ...
            }
        }
    }
    
    // 线程 2 (可能是主线程)
    void method2() {
        synchronized (lockB) {
            Thread.sleep(100);
            synchronized (lockA) {  // 死锁!
                // ...
            }
        }
    }
}
```

### 5.3 Binder 调用阻塞

```java
// Binder 调用可能阻塞主线程

@Override
public boolean onTouchEvent(MotionEvent event) {
    // 同步 Binder 调用
    IBinder service = ServiceManager.getService("some_service");
    ISomeService someService = ISomeService.Stub.asInterface(service);
    
    // 如果服务端阻塞, 这里也会阻塞
    someService.doSomething();  // 可能 ANR
}
```

### 5.4 SharedPreferences commit

```java
// SharedPreferences.commit() 是同步的

@Override
public boolean onTouchEvent(MotionEvent event) {
    SharedPreferences.Editor editor = prefs.edit();
    editor.putString("key", value);
    editor.commit();  // 同步写入, 可能 ANR
    
    // 应该使用 apply()
    editor.apply();  // 异步写入
}
```

---

## 6. ANR 预防最佳实践

### 6.1 异步处理

```java
// 使用线程池处理耗时操作
ExecutorService executor = Executors.newCachedThreadPool();

@Override
public boolean onTouchEvent(MotionEvent event) {
    if (event.getAction() == MotionEvent.ACTION_UP) {
        executor.execute(() -> {
            // 耗时操作
            doHeavyWork();
            
            // 回到主线程更新 UI
            runOnUiThread(() -> updateUI());
        });
    }
    return true;
}
```

### 6.2 StrictMode 检测

```java
// 在开发阶段启用 StrictMode
if (BuildConfig.DEBUG) {
    StrictMode.setThreadPolicy(new StrictMode.ThreadPolicy.Builder()
            .detectDiskReads()
            .detectDiskWrites()
            .detectNetwork()
            .penaltyLog()
            .penaltyDeath()  // 违规时崩溃, 强制修复
            .build());
    
    StrictMode.setVmPolicy(new StrictMode.VmPolicy.Builder()
            .detectLeakedClosableObjects()
            .detectLeakedSqlLiteObjects()
            .penaltyLog()
            .build());
}
```

### 6.3 监控主线程消息队列

```java
// 监控主线程消息处理时间
Looper.getMainLooper().setMessageLogging(msg -> {
    if (msg.startsWith(">>>>> Dispatching")) {
        mMessageStartTime = SystemClock.elapsedRealtime();
    } else if (msg.startsWith("<<<<< Finished")) {
        long duration = SystemClock.elapsedRealtime() - mMessageStartTime;
        if (duration > 100) {
            Log.w(TAG, "Message took " + duration + "ms: " + msg);
        }
    }
});
```

---

## 7. 本章小结

Input ANR 机制的核心要点：

| 要点 | 描述 |
|-----|------|
| 超时时间 | 默认 5 秒 |
| 检测位置 | InputDispatcher |
| 触发条件 | 事件发送后未及时收到 finish 信号 |
| 处理流程 | InputDispatcher → IMS → AMS → 弹框/杀进程 |

常见原因：
1. 主线程执行耗时操作
2. 死锁
3. Binder 调用阻塞
4. 同步 IO 操作

预防措施：
1. 耗时操作放到后台线程
2. 使用 StrictMode 检测
3. 监控主线程消息处理时间
4. 避免同步 Binder 调用

下一篇将介绍 Input 与其他子系统的交互。

---

## 参考资料

1. `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`
2. `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`
3. Android ANR 分析指南
