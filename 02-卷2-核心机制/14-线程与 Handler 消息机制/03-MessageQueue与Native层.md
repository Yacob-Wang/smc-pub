# 03-MessageQueue 与 Native 层：epoll 驱动的消息引擎

在上一篇中，我们跟随 `Looper.loop()` 的无限循环看到了一行关键调用——`queue.next()`。这个方法是消息调度的真正心脏：它决定了线程何时阻塞、何时唤醒、下一条消息是什么。但如果你只看 Java 层代码，会发现 `next()` 的核心逻辑似乎"消失"在了一个 native 方法调用中：`nativePollOnce(ptr, nextPollTimeoutMillis)`。

这背后是一个精心设计的**双层架构**：Java 层负责消息链表的管理与调度逻辑，Native 层通过 Linux 的 epoll + eventfd 提供高效的阻塞/唤醒能力，同时还承担了 Input 事件、VSync 信号等系统级 fd 的监听职责。

本篇将逐层拆解这个架构：从 Java 层 `MessageQueue.next()` 的调度逻辑，到 JNI 桥接层的 `NativeMessageQueue`，再到 `android::Looper` 中基于 epoll 的事件循环。理解这条完整链路，才能在 ANR trace 中读懂 `nativePollOnce` 到底意味着什么，才能在 fd 泄漏导致消息队列异常时快速定位根因。

---

## 1. 双层架构

### 1.1 为什么需要两层

一个自然的问题是：为什么消息队列需要 Java 和 Native 两层实现？只用 Java 层的 `Object.wait()` / `Object.notify()` 不能实现阻塞唤醒吗？

答案是：**不够**。Android 的消息循环不仅仅处理 Java 层的 `Message`，它还需要监听多个文件描述符（fd）上的事件：

| fd 来源 | 用途 | 对应系统 |
| :--- | :--- | :--- |
| InputChannel fd | 接收触摸、按键等输入事件 | Input 系统 |
| DisplayEventReceiver fd | 接收 VSync 垂直同步信号 | Choreographer / SurfaceFlinger |
| SensorEventQueue fd | 接收传感器数据 | Sensor 系统 |
| 自定义 fd | 第三方库或 Native 组件注册的监听 | 各种 Native 组件 |

`Object.wait()` / `Object.notify()` 是 Java 层的线程同步原语，它只能在"有 Java Message"和"没有 Java Message"之间切换。它**无法同时监听多个 fd**——而 Linux 的 `epoll` 正是为此而生的：一次 `epoll_wait` 调用可以同时等待任意数量的 fd 上的事件。

因此，Android 选择了分层设计：

```
┌──────────────────────────────────────────────────────────────────┐
│                        Java 层                                    │
│  MessageQueue                                                     │
│  ├─ mMessages: Message 单链表（按 when 时间排序）                    │
│  ├─ next(): 消息调度核心循环                                        │
│  ├─ enqueueMessage(): 按时间插入消息                                │
│  └─ mPtr → 指向 Native 层 NativeMessageQueue                      │
├──────────────────────────────────────────────────────────────────┤
│                        JNI 桥接层                                  │
│  android_os_MessageQueue.cpp                                      │
│  ├─ nativePollOnce() → NativeMessageQueue::pollOnce()            │
│  ├─ nativeWake()     → NativeMessageQueue::wake()                │
│  └─ nativeInit()     → new NativeMessageQueue()                  │
├──────────────────────────────────────────────────────────────────┤
│                        Native 层                                   │
│  android::Looper (system/core/libutils/Looper.cpp)               │
│  ├─ mEpollFd: epoll 实例                                          │
│  ├─ mWakeEventFd: eventfd，用于 Java 层唤醒                        │
│  ├─ pollOnce() → pollInner() → epoll_wait()                     │
│  ├─ wake() → write(mWakeEventFd, 1)                             │
│  └─ addFd() / removeFd(): 注册/移除 fd 监听                       │
├──────────────────────────────────────────────────────────────────┤
│                        Linux Kernel                               │
│  epoll / eventfd / timerfd 系统调用                                │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 初始化链路

MessageQueue 的构造函数是双层架构连接的起点：

> Source: `frameworks/base/core/java/android/os/MessageQueue.java`

```java
MessageQueue(boolean quitAllowed) {
    mQuitAllowed = quitAllowed;
    mPtr = nativeInit();
}
```

`nativeInit()` 是一个 JNI 方法，它在 Native 层创建了 `NativeMessageQueue` 对象：

> Source: `frameworks/base/core/jni/android_os_MessageQueue.cpp`

```cpp
static jlong android_os_MessageQueue_nativeInit(JNIEnv* env, jclass clazz) {
    NativeMessageQueue* nativeMessageQueue = new NativeMessageQueue();
    // ...
    nativeMessageQueue->incStrong(env);
    return reinterpret_cast<jlong>(nativeMessageQueue);
}
```

`NativeMessageQueue` 的构造函数中会获取或创建 `android::Looper`：

```cpp
NativeMessageQueue::NativeMessageQueue()
        : mPollEnv(NULL), mPollObj(NULL), mExceptionObj(NULL) {
    mLooper = Looper::getForThread();
    if (mLooper == NULL) {
        mLooper = new Looper(false);
        Looper::setForThread(mLooper);
    }
}
```

`android::Looper` 的构造函数中完成了 epoll 和 eventfd 的初始化（详见第 4 节）。

**`mPtr` 的本质：** Java 层 `MessageQueue` 的 `mPtr` 字段是一个 `long` 类型的值，存储的是 Native 层 `NativeMessageQueue` 对象的内存地址。后续所有的 `nativePollOnce(mPtr, ...)` 和 `nativeWake(mPtr)` 调用，都通过这个指针找到对应的 Native 对象。

**稳定性关联：** 如果 `mPtr` 变为 0（MessageQueue 已被 `dispose()`），后续的 `nativePollOnce` 调用会直接返回，消息循环不再阻塞。在某些极端场景下（如 Looper.quit() 后仍有代码尝试使用 Handler），这会导致 CPU 空转——线程在不断循环但不处理任何消息。

---

## 2. MessageQueue.next()：消息调度的核心

### 2.1 为什么 next() 如此重要

`Looper.loop()` 的核心循环只做三件事：`queue.next()` 取消息 → `msg.target.dispatchMessage()` 分发消息 → `msg.recycleUnchecked()` 回收消息。其中 `next()` 决定了**取哪条消息**和**什么时候取**——这是整个消息调度机制的大脑。

### 2.2 源码全流程

> Source: `frameworks/base/core/java/android/os/MessageQueue.java`

```java
Message next() {
    final long ptr = mPtr;
    if (ptr == 0) {
        return null;  // Looper 已退出
    }

    int pendingIdleHandlerCount = -1;
    int nextPollTimeoutMillis = 0;

    for (;;) {
        if (nextPollTimeoutMillis != 0) {
            Binder.flushPendingCommands();
        }

        // ① 阻塞：调用 Native 层等待
        nativePollOnce(ptr, nextPollTimeoutMillis);

        synchronized (this) {
            final long now = SystemClock.uptimeMillis();
            Message prevMsg = null;
            Message msg = mMessages;  // 链表头

            // ② 同步屏障检查：如果头部是屏障消息（target == null），
            //    则跳过所有同步消息，只找异步消息
            if (msg != null && msg.target == null) {
                do {
                    prevMsg = msg;
                    msg = msg.next;
                } while (msg != null && !msg.isAsynchronous());
            }

            if (msg != null) {
                if (now < msg.when) {
                    // ③ 消息未到时间：计算需要等待的时长
                    nextPollTimeoutMillis = (int) Math.min(
                            msg.when - now, Integer.MAX_VALUE);
                } else {
                    // ④ 消息已到时间：取出并返回
                    mBlocked = false;
                    if (prevMsg != null) {
                        prevMsg.next = msg.next;
                    } else {
                        mMessages = msg.next;
                    }
                    msg.next = null;
                    msg.markInUse();
                    return msg;
                }
            } else {
                // ⑤ 没有消息：无限期等待
                nextPollTimeoutMillis = -1;
            }

            // 检查是否正在退出
            if (mQuitting) {
                dispose();
                return null;
            }

            // ⑥ 执行 IdleHandler
            if (pendingIdleHandlerCount < 0
                    && (mMessages == null || now < mMessages.when)) {
                pendingIdleHandlerCount = mIdleHandlers.size();
            }
            if (pendingIdleHandlerCount <= 0) {
                mBlocked = true;
                continue;  // 没有 IdleHandler，回到循环顶部阻塞
            }

            // ... 执行 IdleHandler 的代码 ...
        }

        // 执行 IdleHandler 回调
        for (int i = 0; i < pendingIdleHandlerCount; i++) {
            final IdleHandler idler = mPendingIdleHandlers[i];
            boolean keep = false;
            try {
                keep = idler.queueIdle();
            } catch (Throwable t) {
                Log.wtf(TAG, "IdleHandler threw exception", t);
            }
            if (!keep) {
                synchronized (this) {
                    mIdleHandlers.remove(idler);
                }
            }
        }

        pendingIdleHandlerCount = 0;
        nextPollTimeoutMillis = 0;  // IdleHandler 可能产生了新消息
    }
}
```

### 2.3 六步流程图

```
                    ┌─────────────────┐
                    │  进入 for(;;)    │
                    └────────┬────────┘
                             ▼
              ┌──────────────────────────────┐
         ①   │ nativePollOnce(ptr, timeout) │  阻塞等待
              │ timeout = 0: 立即返回         │
              │ timeout = -1: 无限期等待      │
              │ timeout > 0: 等待指定毫秒     │
              └──────────────┬───────────────┘
                             ▼
              ┌──────────────────────────────┐
         ②   │ 检查链表头是否为同步屏障       │
              │ (msg.target == null)          │
              │ 是 → 遍历找第一个异步消息      │
              │ 否 → msg = 链表头              │
              └──────────────┬───────────────┘
                             ▼
                      ┌─────────────┐
                      │ msg != null? │
                      └──┬───────┬──┘
                    是   │       │ 否
                         ▼       ▼
              ┌────────────┐  ┌──────────────┐
              │ now < when? │  │ timeout = -1  │ ⑤
              └──┬──────┬──┘  │ (无限期等待)   │
            是   │      │ 否  └───────┬────────┘
                 ▼      ▼            │
         ┌─────────┐ ┌────────┐     │
    ③    │计算超时  │ │取出消息 │ ④   │
         │等待时长  │ │return   │     │
         └────┬────┘ └────────┘     │
              │                      │
              ▼                      │
    ┌──────────────────┐            │
    │ 有 IdleHandler?   │◄───────────┘
    └───┬──────────┬───┘
     否 │          │ 是
        ▼          ▼
  ┌──────────┐  ┌──────────────┐
  │mBlocked  │  │执行 IdleHandler│ ⑥
  │= true    │  │设置 timeout=0  │
  │continue  │  │(可能有新消息)   │
  └──────────┘  └──────┬───────┘
                       │
                       ▼
                回到 for(;;) 顶部
```

### 2.4 关键参数 nextPollTimeoutMillis

| 值 | 含义 | 场景 |
| :--- | :--- | :--- |
| `0` | 不阻塞，立即返回 | 首次进入循环；执行完 IdleHandler 后（可能有新消息） |
| `-1` | 无限期阻塞，直到被唤醒 | 消息队列为空，没有任何待处理消息 |
| `> 0` | 阻塞指定毫秒数 | 下一条消息的 `when` 还没到，需要等一段时间 |

**稳定性关联：** 在 ANR trace 中看到主线程停在 `nativePollOnce`，并不一定意味着"主线程空闲"。你需要结合 `nextPollTimeoutMillis` 的值来判断：
- 如果 timeout = -1：主线程确实空闲，没有待处理的消息。此时 ANR 的原因通常是**消息没有被投递**（如 Binder 线程池耗尽导致 AMS 的回调发不过来）。
- 如果 timeout > 0：主线程在等待一条延迟消息。ANR 可能是因为**之前的消息耗时过长**，导致后续消息排队超时。
- 如果 timeout = 0：主线程正在正常调度，停在 `nativePollOnce` 只是一个瞬时状态。

### 2.5 同步屏障与 next() 的关系

当消息链表头部存在同步屏障（`target == null` 的 Message）时，`next()` 会跳过所有同步消息，只寻找异步消息。这是 Android 保障 UI 渲染优先的关键机制——Choreographer 在收到 VSync 信号后会插入同步屏障，确保渲染相关的异步消息优先被处理。

**稳定性关联：** 如果同步屏障插入后没有被正确移除（`removeSyncBarrier()` 没有被调用），所有同步消息将被永久阻塞。这会导致主线程看起来"在运行"（因为在不断循环寻找异步消息），但所有普通的 Handler 消息（如生命周期回调）都无法被处理，最终触发 ANR。这种问题极难排查，因为 ANR trace 中主线程并不显示"卡死"，而是在 `MessageQueue.next()` 中正常运行。

---

## 3. Native 层完整链路

### 3.1 从 nativePollOnce 到 epoll_wait

当 Java 层调用 `nativePollOnce(ptr, timeoutMillis)` 时，一条从 Java 到内核的调用链就此展开。理解这条链路，是读懂 ANR trace 中 Native 堆栈的前提。

完整调用链：

```
Java: MessageQueue.next()
  → nativePollOnce(mPtr, nextPollTimeoutMillis)
    │
    ├── JNI: android_os_MessageQueue_nativePollOnce()
    │   Source: frameworks/base/core/jni/android_os_MessageQueue.cpp
    │
    ├── NativeMessageQueue::pollOnce(timeoutMillis)
    │   Source: frameworks/base/core/jni/android_os_MessageQueue.cpp
    │
    ├── android::Looper::pollOnce(timeoutMillis)
    │   Source: system/core/libutils/Looper.cpp
    │
    ├── android::Looper::pollInner(timeoutMillis)
    │   Source: system/core/libutils/Looper.cpp
    │
    └── epoll_wait(mEpollFd, eventItems, EPOLL_MAX_EVENTS, timeoutMillis)
        │   Source: Linux Kernel
        │
        ├── 超时返回（timeout 到期，无 fd 事件）→ 返回 Java 层
        ├── mWakeEventFd 可读 → 被 Java 层唤醒 → 返回 Java 层
        └── 其他 fd 可读（如 InputChannel fd）→ 调用对应回调 → 返回 Java 层
```

### 3.2 JNI 桥接层

> Source: `frameworks/base/core/jni/android_os_MessageQueue.cpp`

```cpp
static void android_os_MessageQueue_nativePollOnce(
        JNIEnv* env, jobject obj, jlong ptr, jint timeoutMillis) {
    NativeMessageQueue* nativeMessageQueue =
            reinterpret_cast<NativeMessageQueue*>(ptr);
    nativeMessageQueue->pollOnce(env, obj, timeoutMillis);
}
```

JNI 层做的事情非常简单：将 `mPtr`（long 类型）强转回 `NativeMessageQueue*` 指针，然后调用其 `pollOnce` 方法。

`NativeMessageQueue::pollOnce` 的实现：

```cpp
void NativeMessageQueue::pollOnce(
        JNIEnv* env, jobject pollObj, int timeoutMillis) {
    mPollEnv = env;
    mPollObj = pollObj;
    mLooper->pollOnce(timeoutMillis);
    mPollObj = NULL;
    mPollEnv = NULL;

    if (mExceptionObj) {
        env->Throw(mExceptionObj);
        env->DeleteLocalRef(mExceptionObj);
        mExceptionObj = NULL;
    }
}
```

它将调用转发给 `android::Looper::pollOnce()`，并在返回后检查是否有 Native 层抛出的异常需要传播到 Java 层。

### 3.3 android::Looper::pollOnce

> Source: `system/core/libutils/Looper.cpp`

```cpp
int Looper::pollOnce(int timeoutMillis, int* outFd, int* outEvents,
        void** outData) {
    int result = 0;
    for (;;) {
        // 先处理之前 pollInner 中积攒的 response
        while (mResponseIndex < mResponses.size()) {
            const Response& response = mResponses.itemAt(mResponseIndex++);
            int ident = response.request.ident;
            if (ident >= 0) {
                // 返回 ident，让调用者自行处理
                if (outFd != NULL) *outFd = response.request.fd;
                if (outEvents != NULL) *outEvents = response.events;
                if (outData != NULL) *outData = response.request.data;
                return ident;
            }
        }

        if (result != 0) {
            if (outFd != NULL) *outFd = 0;
            if (outEvents != NULL) *outEvents = 0;
            if (outData != NULL) *outData = NULL;
            return result;
        }

        result = pollInner(timeoutMillis);
    }
}
```

`pollOnce` 是一个外层循环，它的核心逻辑在 `pollInner` 中。外层循环的作用是处理 `pollInner` 返回后积攒的 response（fd 事件回调的结果）。

### 3.4 android::Looper::pollInner——真正的核心

> Source: `system/core/libutils/Looper.cpp`

```cpp
int Looper::pollInner(int timeoutMillis) {
    // 调整超时值
    if (timeoutMillis != 0 && mNextMessageUptime != LLONG_MAX) {
        nsecs_t now = systemTime(SYSTEM_TIME_MONOTONIC);
        int messageTimeoutMillis = toMillisecondTimeoutDelay(
                now, mNextMessageUptime);
        if (messageTimeoutMillis >= 0
                && (timeoutMillis < 0
                    || messageTimeoutMillis < timeoutMillis)) {
            timeoutMillis = messageTimeoutMillis;
        }
    }

    int result = POLL_WAKE;
    mResponses.clear();
    mResponseIndex = 0;
    mPolling = true;

    // ★ 核心：epoll_wait 阻塞等待
    struct epoll_event eventItems[EPOLL_MAX_EVENTS];
    int eventCount = epoll_wait(mEpollFd, eventItems,
            EPOLL_MAX_EVENTS, timeoutMillis);

    mPolling = false;

    // 重新获取锁
    mLock.lock();

    // 处理 epoll 返回的事件
    for (int i = 0; i < eventCount; i++) {
        int fd = eventItems[i].data.fd;
        uint32_t epollEvents = eventItems[i].events;

        if (fd == mWakeEventFd) {
            if (epollEvents & EPOLLIN) {
                // wakeEventFd 被写入 → 读出数据以重置
                awoken();
            }
        } else {
            // 其他 fd 的事件 → 找到对应的 Request，生成 Response
            ssize_t requestIndex = mRequests.indexOfKey(fd);
            if (requestIndex >= 0) {
                int events = 0;
                if (epollEvents & EPOLLIN) events |= EVENT_INPUT;
                if (epollEvents & EPOLLOUT) events |= EVENT_OUTPUT;
                if (epollEvents & EPOLLERR) events |= EVENT_ERROR;
                if (epollEvents & EPOLLHUP) events |= EVENT_HANGUP;
                pushResponse(events, mRequests.valueAt(requestIndex));
            }
        }
    }

    // 处理 Native 层的 MessageEnvelope（Native Message）
    // ...

    // 处理所有带 callback 的 Response
    for (size_t i = 0; i < mResponses.size(); i++) {
        Response& response = mResponses.editItemAt(i);
        if (response.request.ident == POLL_CALLBACK) {
            int fd = response.request.fd;
            int events = response.events;
            void* data = response.request.data;
            int callbackResult = response.request.callback->handleEvent(
                    fd, events, data);
            if (callbackResult == 0) {
                removeFd(fd, response.request.seq);
            }
            response.request.callback.clear();
            result = POLL_CALLBACK;
        }
    }

    mLock.unlock();
    return result;
}
```

**核心要点：**

1. **`epoll_wait` 是真正的阻塞点**——线程在这里挂起，直到超时或有 fd 事件。
2. **wakeEventFd 事件**：如果是 `mWakeEventFd` 触发，说明 Java 层调用了 `nativeWake()`，调用 `awoken()` 读出数据以重置 eventfd。
3. **其他 fd 事件**：遍历 epoll 返回的事件，匹配已注册的 fd，生成 Response 并调用对应的 callback。

**稳定性关联：** `epoll_wait` 的返回值 `eventCount` 为 -1 时表示出错。常见的错误是 `EBADF`（mEpollFd 被意外关闭）或 `EINTR`（被信号中断）。在 Native Crash 的 Tombstone 中，如果看到崩溃发生在 `Looper::pollInner` 附近，通常与 fd 状态异常有关。

---

## 4. epoll + eventfd 阻塞唤醒机制

### 4.1 为什么选择 epoll + eventfd

这是 Android 消息机制最精妙的设计之一。先理解两个 Linux 原语：

| 原语 | 作用 | 特点 |
| :--- | :--- | :--- |
| **epoll** | I/O 多路复用，同时监听多个 fd 上的事件 | O(1) 事件通知（相比 select/poll 的 O(n)）；内核态维护红黑树，高效管理大量 fd |
| **eventfd** | 进程/线程间的事件通知 | 本质是一个内核维护的 64 位计数器；write 增加计数，read 读出并清零；可被 epoll 监听 |

Android 用 `eventfd` 作为 Java 层与 Native 层之间的"信号灯"：
- **阻塞**：`epoll_wait` 同时监听 `eventfd` 和其他 fd，没有任何事件时线程挂起。
- **唤醒**：向 `eventfd` 写入一个值，`epoll_wait` 立即返回。

为什么不用 `Object.wait()` / `Object.notify()`？

1. **wait/notify 无法监听 fd**：Input 事件、VSync 信号都是通过 fd 传递的，wait/notify 做不到。
2. **wait/notify 有 JNI 边界开销**：Native 层唤醒 Java 层需要先 `AttachCurrentThread`，再 `CallVoidMethod`，再 `notify()`——链路太长。
3. **epoll 是 Linux 世界的标准方案**：与内核的事件通知机制天然对齐，性能最优。

### 4.2 初始化过程

> Source: `system/core/libutils/Looper.cpp`

```cpp
Looper::Looper(bool allowNonCallbacks)
    : mAllowNonCallbacks(allowNonCallbacks),
      mSendingMessage(false),
      mPolling(false),
      mEpollRebuildRequired(false),
      mNextRequestSeq(0),
      mResponseIndex(0),
      mNextMessageUptime(LLONG_MAX) {

    // ① 创建 eventfd
    mWakeEventFd.reset(eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC));
    LOG_ALWAYS_FATAL_IF(mWakeEventFd.get() < 0,
            "Could not make wake event fd: %s", strerror(errno));

    AutoMutex _l(mLock);
    rebuildEpollLocked();
}
```

`rebuildEpollLocked()` 完成 epoll 的初始化：

```cpp
void Looper::rebuildEpollLocked() {
    if (mEpollFd >= 0) {
        close(mEpollFd);  // 关闭旧的 epoll（如果有）
    }

    // ② 创建 epoll 实例
    mEpollFd.reset(epoll_create1(EPOLL_CLOEXEC));

    // ③ 将 eventfd 注册到 epoll
    struct epoll_event eventItem;
    memset(&eventItem, 0, sizeof(epoll_event));
    eventItem.events = EPOLLIN;
    eventItem.data.fd = mWakeEventFd.get();
    int result = epoll_ctl(mEpollFd.get(), EPOLL_CTL_ADD,
            mWakeEventFd.get(), &eventItem);

    // ④ 将已注册的所有 fd 也重新注册到新的 epoll
    for (size_t i = 0; i < mRequests.size(); i++) {
        const Request& request = mRequests.valueAt(i);
        struct epoll_event eventItem;
        request.initEventItem(&eventItem);
        int epollResult = epoll_ctl(mEpollFd.get(), EPOLL_CTL_ADD,
                request.fd, &eventItem);
    }
}
```

初始化后的状态：

```
mEpollFd (epoll 实例)
  │
  ├── 监听: mWakeEventFd (eventfd)  — 用于 Java 层唤醒
  ├── 监听: InputChannel fd          — 如果已注册
  ├── 监听: VSync fd                 — 如果已注册
  └── 监听: 其他已注册 fd             — 如果有
```

### 4.3 唤醒流程

当 Java 层有新消息入队时，需要唤醒可能正在 `epoll_wait` 中阻塞的线程。

> Source: `frameworks/base/core/java/android/os/MessageQueue.java`

```java
boolean enqueueMessage(Message msg, long when) {
    // ...
    synchronized (this) {
        // 插入消息到链表...

        if (needWake) {
            nativeWake(mPtr);  // 唤醒 Native 层
        }
    }
    return true;
}
```

`nativeWake` 的调用链：

> Source: `system/core/libutils/Looper.cpp`

```cpp
void Looper::wake() {
    uint64_t inc = 1;
    ssize_t nWrite = TEMP_FAILURE_RETRY(
            write(mWakeEventFd.get(), &inc, sizeof(uint64_t)));
    if (nWrite != sizeof(uint64_t)) {
        if (errno != EAGAIN) {
            LOG_ALWAYS_FATAL("Could not write wake signal to fd %d: %s",
                    mWakeEventFd.get(), strerror(errno));
        }
    }
}
```

唤醒后的清除（`awoken`）：

```cpp
void Looper::awoken() {
    uint64_t counter;
    TEMP_FAILURE_RETRY(read(mWakeEventFd.get(), &counter, sizeof(uint64_t)));
}
```

完整流程：

```
Java 层                              Native 层                    Kernel
  │                                    │                            │
  │ enqueueMessage()                   │                            │
  │   needWake = true                  │                            │
  │   nativeWake(mPtr) ──────────────► │                            │
  │                                    │ Looper::wake()             │
  │                                    │   write(mWakeEventFd, 1) ─►│
  │                                    │                            │ eventfd 计数器 +1
  │                                    │                            │ epoll_wait 返回
  │                                    │ ◄──────── eventCount > 0   │
  │                                    │ 检测到 mWakeEventFd 可读    │
  │                                    │ awoken()                   │
  │                                    │   read(mWakeEventFd) ────►│
  │                                    │                            │ eventfd 计数器清零
  │                                    │ pollInner 返回              │
  │ ◄──────── nativePollOnce 返回      │                            │
  │ 继续 next() 循环，检查消息链表      │                            │
```

**什么时候需要唤醒（needWake 的判断）：**

```java
// MessageQueue.enqueueMessage() 中的判断逻辑（简化）
boolean needWake;
if (p == null || when == 0 || when < p.when) {
    // 新消息插入到链表头部
    msg.next = p;
    mMessages = msg;
    needWake = mBlocked;  // 如果线程正在阻塞，则需要唤醒
} else {
    // 新消息插入到链表中间
    // 只有当队列头是同步屏障且新消息是最早的异步消息时才唤醒
    needWake = mBlocked && p.target == null && msg.isAsynchronous();
    // ... 插入逻辑
}
```

**稳定性关联：** `mBlocked` 标志位的正确管理至关重要。如果 `mBlocked` 状态不一致（比如线程实际在阻塞但 `mBlocked` 为 false），新消息入队后不会触发 `nativeWake()`，导致消息延迟处理。虽然 AOSP 的实现非常严谨，但在某些自定义 ROM 或魔改 Framework 中，对 `mBlocked` 的修改可能引入此类 bug。

---

## 5. fd 监听能力

### 5.1 为什么 Looper 需要监听 fd

Android 的消息循环不仅仅是"取 Message → 处理 Message"这么简单。系统中有大量事件是通过文件描述符（fd）传递的——Input 事件、VSync 信号、Sensor 数据等。这些事件需要被注入到消息循环中，才能在正确的线程上被处理。

`android::Looper` 通过 `addFd()` 提供了将 fd 注册到 epoll 的能力，使得消息循环可以同时等待 Java Message 和 Native fd 事件。

### 5.2 addFd / removeFd

> Source: `system/core/libutils/Looper.cpp`

```cpp
int Looper::addFd(int fd, int ident, int events,
        Looper_callbackFunc callback, void* data) {
    return addFd(fd, ident, events,
            callback ? new SimpleLooperCallback(callback) : NULL, data);
}

int Looper::addFd(int fd, int ident, int events,
        const sp<LooperCallback>& callback, void* data) {
    {
        AutoMutex _l(mLock);

        Request request;
        request.fd = fd;
        request.ident = ident;
        request.events = events;
        request.seq = mNextRequestSeq++;
        request.callback = callback;
        request.data = data;

        struct epoll_event eventItem;
        request.initEventItem(&eventItem);

        ssize_t requestIndex = mRequests.indexOfKey(fd);
        if (requestIndex < 0) {
            // 新 fd → epoll_ctl ADD
            int epollResult = epoll_ctl(mEpollFd.get(), EPOLL_CTL_ADD,
                    fd, &eventItem);
        } else {
            // 已有 fd → epoll_ctl MOD
            int epollResult = epoll_ctl(mEpollFd.get(), EPOLL_CTL_MOD,
                    fd, &eventItem);
        }

        mRequests.replaceValueFor(fd, request);
    }
    return 1;
}
```

### 5.3 系统中的 fd 监听实例

#### Input 事件

Input 系统通过 `InputChannel`（基于 Unix Domain Socket）将触摸、按键事件传递到应用进程。应用端的 `ViewRootImpl` 在初始化时创建 `WindowInputEventReceiver`，它通过 Native 层将 InputChannel 的 fd 注册到 Looper 的 epoll 中：

```
InputDispatcher (system_server 进程)
  │
  │ 通过 InputChannel (socket pair) 传递事件
  ▼
InputChannel fd (应用进程)
  │
  │ Looper::addFd(inputChannelFd, callback)
  ▼
epoll_wait 返回 → NativeInputEventReceiver::handleEvent()
  │
  │ 回调 Java 层
  ▼
WindowInputEventReceiver.onInputEvent() → View 事件分发
```

#### VSync 信号

Choreographer 通过 `DisplayEventReceiver` 接收来自 SurfaceFlinger 的 VSync 信号。其 Native 层实现也是将 fd 注册到 Looper：

```
SurfaceFlinger
  │
  │ 通过 BitTube (socket pair) 发送 VSync 事件
  ▼
DisplayEventReceiver fd (应用进程)
  │
  │ Looper::addFd(vsyncFd, callback)
  ▼
epoll_wait 返回 → NativeDisplayEventReceiver::handleEvent()
  │
  │ 回调 Java 层
  ▼
Choreographer.onVsync() → doFrame() → 执行渲染
```

### 5.4 fd 事件的处理流程

当 `epoll_wait` 返回时，`pollInner` 会遍历所有触发的事件：

```
epoll_wait 返回 eventCount 个事件
  │
  ├── fd == mWakeEventFd → awoken()（Java 层唤醒信号）
  │
  └── fd != mWakeEventFd → 在 mRequests 中查找匹配的 Request
      │
      ├── 有 callback → pushResponse() → 稍后调用 callback->handleEvent()
      │
      └── 无 callback → pushResponse() → 通过 ident 返回给调用者
```

**稳定性关联：** 每个注册到 Looper 的 fd 都会占用 epoll 的监控槽位和进程的 fd 配额。如果存在 fd 泄漏（fd 被创建但从不关闭和移除），会导致：
1. 进程的 fd 数量逐渐增加，最终触及 `/proc/pid/limits` 中的上限（通常 1024 或更多），触发 `Too many open files` 错误。
2. `epoll_ctl` 调用 `EPOLL_CTL_ADD` 失败，新的 fd 无法被监听。
3. 严重时 `epoll_create1` 本身也会失败——此时 `rebuildEpollLocked()` 触发 `LOG_ALWAYS_FATAL`，进程直接崩溃。

---

## 6. 稳定性实战案例

### 案例一：fd 泄漏导致 InputChannel 注册失败，用户触摸无响应

**现象：**

某资讯类 App 在长时间使用后（通常 2-3 小时），用户反馈"页面能正常加载，但触摸没有任何反应"。重启 App 后恢复正常。Logcat 中发现大量以下错误：

```
E/Looper: epoll_ctl(EPOLL_CTL_ADD) failed: Too many open files
W/InputTransport: Failed to register input channel
E/ViewRootImpl: Failed to set up input channel: Status(-1)
```

同时在 `/proc/<pid>/fd` 目录下观察到 fd 数量持续增长：

```
$ adb shell ls /proc/12345/fd | wc -l
启动时:     287
运行 1h:    512
运行 2h:    843
运行 3h:   1019  ← 接近上限 1024
```

**分析思路：**

1. **定位 fd 来源**：通过 `ls -la /proc/<pid>/fd` 查看 fd 指向的文件类型，发现大量 fd 指向 `socket:[xxxxx]` 和 `anon_inode:[eventpoll]`。

2. **关联代码**：排查 App 中所有创建 socket 和 epoll 的路径，发现一个自研的长连接 SDK 在网络重连时：
   - 创建新的 `Looper`（用于监听网络事件）
   - 通过 `Looper::addFd()` 注册 socket fd
   - 但在断开连接时，只 `close(socket_fd)`，没有调用 `Looper::removeFd()` 将 fd 从 epoll 中移除
   - 更严重的是，旧的 `Looper` 对象本身也没有被销毁，其内部的 `mEpollFd` 和 `mWakeEventFd` 没有被关闭

3. **连锁反应**：
   ```
   网络重连（频率：每次断网后立即重连，弱网环境可达每分钟数次）
     → 创建新 Looper（epoll fd + eventfd = 2 个 fd）
     → 注册新 socket fd（+1 个 fd）
     → 旧 Looper 的 3 个 fd 泄漏
     → 长时间后 fd 数量达到进程上限（1024）
     → InputChannel 注册时 epoll_ctl(EPOLL_CTL_ADD) 失败
     → 新打开的 Activity 无法接收 Input 事件
     → 用户看到页面但触摸无响应
   ```

4. **为什么只影响触摸不影响页面加载**：页面加载走的是 HTTP 请求 + Handler.post() 流程，不依赖 fd 注册。而触摸事件通过 InputChannel fd 注入，必须注册到 epoll 才能被接收。

**根因：**

自研长连接 SDK 在网络重连时存在 fd 泄漏——旧的 `android::Looper` 实例和 socket fd 没有被正确清理。当 fd 泄漏累积到进程上限时，系统无法为新 Activity 的 InputChannel 注册 fd，导致触摸事件无法被接收。

**修复方案：**

1. **短期修复**：
   - 修复长连接 SDK 的资源清理逻辑：断开连接时先 `removeFd(socket_fd)`，再 `close(socket_fd)`，最后销毁 `Looper` 对象
   - 重连时复用已有的 `Looper` 实例，而非每次创建新实例

```cpp
// 修复前（泄漏）
void NetworkManager::reconnect() {
    // 直接创建新 Looper，旧的泄漏
    mLooper = new Looper(false);
    int newSocketFd = createSocket();
    mLooper->addFd(newSocketFd, ...);
}

// 修复后（正确清理 + 复用）
void NetworkManager::disconnect() {
    if (mSocketFd >= 0) {
        mLooper->removeFd(mSocketFd);
        close(mSocketFd);
        mSocketFd = -1;
    }
}

void NetworkManager::reconnect() {
    disconnect();
    if (mLooper == nullptr) {
        mLooper = new Looper(false);
    }
    mSocketFd = createSocket();
    mLooper->addFd(mSocketFd, ...);
}
```

2. **长期治理**：
   - 在 APM 框架中添加 fd 数量监控，定期读取 `/proc/self/fd` 的 fd 计数，超过阈值（如 800）时触发告警并上报 fd 类型分布
   - 在 Debug 版本中 hook `open()` / `close()` / `socket()` 系统调用，记录 fd 的创建和关闭配对，检测泄漏

```
修复前后对比：
┌──────────────────────────────────┬────────────┬────────────┐
│ 指标                              │ 修复前      │ 修复后      │
├──────────────────────────────────┼────────────┼────────────┤
│ 运行 3h 后 fd 数量                │ 1019       │ 305        │
│ "触摸无响应" 用户投诉 / 日        │ 45         │ 0          │
│ InputChannel 注册失败率           │ 2.3%       │ 0%         │
│ 长连接重连 fd 泄漏 / 次           │ 3          │ 0          │
└──────────────────────────────────┴────────────┴────────────┘
```

---

### 案例二：ANR trace 中 nativePollOnce 的误判——"主线程空闲"的假象

**现象：**

某电商 App 在大促期间 ANR 率突增。ANR trace 中主线程的堆栈如下：

```
"main" prio=5 tid=1 Native
  | group="main" sCount=1 dsCount=0 flags=1 obj=0x72c44e58 self=0xb400007a1a210800
  | sysTid=18432 nice=-10 cgrp=default sched=0/0 handle=0x7b54321020
  | state=S schedstat=( 185032841356 52847123456 312478 ) utm=14250 stm=4253 core=4 HZ=100
  | stack=0x7ffc123000-0x7ffc125000 stackSize=8192KB
  | held mutexes=
  at android.os.MessageQueue.nativePollOnce(Native method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  at android.os.Looper.loop(Looper.java:183)
  at android.app.ActivityThread.main(ActivityThread.java:7656)
  at java.lang.reflect.Method.invoke(Native method)
  at com.android.internal.os.RuntimeInit$MethodAndArgsCaller.run(RuntimeInit.java:592)
  at com.android.internal.os.ZygoteInit.main(ZygoteInit.java:947)
```

开发团队最初的判断是"主线程空闲，在 `nativePollOnce` 中等待消息，ANR 可能是系统问题"，遂标记为"非我方问题"并关闭了工单。

然而 ANR 率持续上升，用户投诉大量增加。

**分析思路：**

1. **nativePollOnce 不等于"主线程空闲"**：这是一个极其常见的误判。`nativePollOnce` 意味着主线程正在 `MessageQueue.next()` 的循环中，调用 Native 层的 `epoll_wait` 等待。但这有多种可能：
   - 主线程确实空闲，等待新消息（timeout = -1）
   - 主线程在等待一条延迟消息到期（timeout > 0）
   - 主线程刚从 `nativePollOnce` 返回，马上又进入了下一次循环（timeout = 0）
   - **关键：ANR dump 的时刻恰好捕获到线程在 `nativePollOnce`，不代表线程一直在这里**

2. **查看完整的 ANR 日志**：

   在 ANR 日志的 `ActivityManager` 部分找到了关键信息：
   ```
   ANR in com.example.shop (com.example.shop/.MainActivity)
   PID: 18432
   Reason: Input dispatching timed out (Waiting to send non-key event
           because the touched window has not finished processing certain
           input events that were delivered to it over 500.0ms ago.
           Wait queue length: 28. Head age: 8123.4ms.)
   ```

   **Wait queue length: 28，Head age: 8123.4ms**——InputDispatcher 的等待队列中积压了 28 个事件，最早的事件已经等待了 8.1 秒。这说明应用进程**之前**有一段长时间没有处理 Input 事件。

3. **回溯卡顿源头**：通过 Systrace 分析发现，在 ANR 前 8 秒，主线程处理了一个 `BroadcastReceiver.onReceive()` 消息，该消息中执行了同步数据库查询（大促期间数据量暴增，查询耗时约 6 秒）。

4. **还原时间线**：

   ```
   T=0s:   主线程正在处理 BroadcastReceiver.onReceive()（同步数据库查询）
   T=0~6s: 数据库查询阻塞主线程，期间所有 Input 事件在 InputDispatcher 排队
   T=6s:   onReceive() 执行完毕，主线程返回 Looper.loop()
   T=6s:   queue.next() → nativePollOnce → epoll_wait 返回
           （InputChannel fd 上积压了大量事件）
   T=6~8s: 主线程开始处理积压的 Input 事件，但 InputDispatcher 判定
           超时（>5s），开始 ANR 流程
   T=8.1s: ANR dump 采集 → 此时主线程恰好在 nativePollOnce 中
           （刚处理完一个事件，准备取下一条消息）
   ```

5. **"假象"的本质**：ANR dump 是一个**时间点快照**。在 dump 的那个精确时刻，主线程确实在 `nativePollOnce` 中——但这不意味着 ANR 的原因是"主线程空闲"。真正的原因是 6 秒前的数据库阻塞导致了 Input 事件积压超时。

**根因：**

`BroadcastReceiver.onReceive()` 中执行了同步数据库查询，大促期间数据量暴增导致查询耗时 6 秒。主线程被阻塞期间，InputDispatcher 的事件队列持续积压，最终触发 Input ANR（5 秒超时）。ANR trace 中看到的 `nativePollOnce` 是 dump 时刻的瞬时状态，是一个"快照假象"。

**修复方案：**

1. **短期修复**：
   - 将 BroadcastReceiver 的数据库操作移到工作线程（`IntentService` 或 `WorkManager`）
   - 对大促场景的数据库查询添加索引优化和分页查询

2. **长期治理**：
   - 在 APM 框架中基于 `Looper.Printer` 监控每条消息的耗时，超过 500ms 的消息上报堆栈和耗时信息
   - 建立 ANR 归因系统：不只看 dump 时刻的主线程堆栈，还要回溯 dump 前 10 秒内的消息调度记录（通过 Looper.Observer 或 Systrace 标记收集）
   - 在 CI 中加入 StrictMode 检查，禁止 BroadcastReceiver 中的磁盘 I/O 和网络操作

```
修复前后对比：
┌───────────────────────────────────────┬────────────┬────────────┐
│ 指标                                   │ 修复前      │ 修复后      │
├───────────────────────────────────────┼────────────┼────────────┤
│ 大促期间日均 ANR 次数                   │ 1850       │ 120        │
│ Input ANR 占比                         │ 72%        │ 15%        │
│ BroadcastReceiver 主线程耗时 > 1s 次数  │ 3200/天    │ 45/天      │
│ 主线程消息最大耗时                      │ 6200ms     │ 380ms      │
└───────────────────────────────────────┴────────────┴────────────┘
```

**给稳定性架构师的启示：**

1. **永远不要仅凭 ANR dump 的堆栈下结论**。`nativePollOnce` 出现在 ANR trace 中是非常常见的——因为主线程大部分时间确实在这个方法中。关键是要看 ANR 的 **Reason** 字段和 InputDispatcher 的 **Wait queue** 信息。
2. **ANR 归因需要"时间维度"**：单点快照（dump 时刻的堆栈）不够，需要时间线（dump 前数秒的消息调度记录）。这就是为什么 Looper.Printer / Looper.Observer / Systrace 等持续监控手段至关重要。
3. **消息耗时的"连锁效应"**：单条消息耗时 6 秒，不仅仅是这条消息本身的问题——它会导致后续所有消息排队延迟，引发 Input ANR、Broadcast ANR 等多种超时。这就是为什么卡顿治理的核心目标是**控制每条消息的耗时在合理范围内**。

---

## 总结

本篇沿着 `nativePollOnce` 的调用链，从 Java 层的 `MessageQueue.next()` 一路下探到 Linux 内核的 `epoll_wait`，完整拆解了 Android 消息队列的双层架构。

核心要点：

1. **双层分工**：Java 层 `MessageQueue` 管理 Message 单链表（按 when 排序、同步屏障、IdleHandler），Native 层 `android::Looper` 通过 epoll 提供高效的阻塞/唤醒和 fd 监听能力。
2. **`MessageQueue.next()` 是消息调度的核心**：无限循环中的六个步骤（nativePollOnce 阻塞 → 同步屏障检查 → 时间判断 → 取出消息 → 计算超时 → IdleHandler）决定了线程的每一次睡眠和唤醒。
3. **epoll + eventfd 是阻塞唤醒的底层实现**：`eventfd` 作为 Java 层与 Native 层之间的"信号灯"，`epoll` 同时监听 eventfd 和其他 fd（Input、VSync 等），一次 `epoll_wait` 解决所有等待。
4. **fd 监听是消息循环的扩展能力**：Input 事件、VSync 信号等通过 `addFd()` 注册到 Looper 的 epoll，使消息循环能够感知系统级事件。fd 泄漏会破坏这个能力。
5. **ANR trace 中的 `nativePollOnce` 需要结合上下文判断**：它可能是主线程空闲，也可能是卡顿恢复后的瞬时状态。单独的堆栈快照不足以归因 ANR，需要结合 Reason 字段、InputDispatcher 状态和历史消息调度记录。

在下一篇中，我们将聚焦 Message 本身——它的数据结构、对象池机制、从创建到回收的完整生命周期，以及 `dispatchMessage` 的三级分发优先级。
