# 01-Handler 消息机制总览：Android 的事件驱动引擎

## 1. 消息机制是什么

Android 应用启动后，主线程（UI 线程）并不是执行完一段代码就退出的"脚本"——它是一个**永不停止的事件循环**。这个循环不断从一个消息队列中取出消息、处理消息、再取下一条，直到应用进程被杀死。

这就是 Android 的消息机制：**一个基于单线程事件循环的异步任务调度系统。**

### 1.1 "一切皆消息"

Android 中几乎所有重要的事情，都是以消息（Message）的形式在主线程中被处理的：

| 场景 | 消息来源 | 消息处理 |
| :--- | :--- | :--- |
| Activity 生命周期 | AMS 通过 Binder → ApplicationThread | ActivityThread.H.handleMessage() |
| 触摸事件 | InputDispatcher → InputChannel(fd) | ViewRootImpl.WindowInputEventReceiver |
| UI 渲染 | Choreographer 收到 VSync 信号 | Choreographer.FrameHandler.handleMessage() |
| 定时任务 | Handler.postDelayed() | 到时间后在主线程执行 |
| 广播接收 | AMS 通过 Binder 分发 | ActivityThread.H → handleReceiver() |
| Service 生命周期 | AMS 通过 Binder | ActivityThread.H → handleCreateService() |

用一句话概括：**Android 的主线程就是一个消息处理机器。不存在"直接调用"的说法——系统通过发送消息来驱动一切。**

### 1.2 类比其他事件循环模型

消息机制并非 Android 独创，它是一种经典的事件驱动架构：

```
Windows Message Loop:
  while (GetMessage(&msg, NULL, 0, 0)) {
      TranslateMessage(&msg);
      DispatchMessage(&msg);    // → WindowProc 处理消息
  }

Node.js Event Loop:
  while (true) {
      event = eventQueue.dequeue();
      event.callback();          // → 执行回调
  }

Android Looper:
  for (;;) {
      Message msg = queue.next();   // 阻塞等待下一条消息
      msg.target.dispatchMessage(msg);  // Handler 处理消息
      msg.recycleUnchecked();       // 回收 Message 对象
  }
```

三者的核心思想完全一致：**一个线程，一个队列，一个无限循环。** 区别在于 Android 的消息队列底层由 Linux `epoll` 驱动阻塞唤醒，并且整个 UI 框架、系统服务回调、输入事件分发都建立在这个循环之上。

### 1.3 与稳定性的关联

理解"一切皆消息"，是理解 Android 稳定性问题的第一步：

- **卡顿**：某条消息处理耗时过长 → 后续消息排队等待 → 用户感知到界面不流畅。
- **ANR**：系统发来的"超时检测消息"在规定时间内未被处理 → 触发 Application Not Responding。
- **内存泄漏**：延迟消息持有 Handler 引用 → Handler 持有 Activity 引用 → Activity 无法被 GC 回收。
- **消息丢失**：Looper 退出后继续发送消息 → 消息被静默丢弃 → 功能异常。

---

## 2. 为什么选择单线程模型

Android 的 UI 框架不支持多线程并发访问。所有 View 的测量（measure）、布局（layout）、绘制（draw）都必须在主线程完成。这不是偶然的，而是深思熟虑的设计选择。

### 2.1 多线程操作 UI 的致命问题

假设 Android 允许多个线程同时操作 UI，会发生什么？

**竞态条件（Race Condition）：**

```java
// Thread A: 修改 TextView 文本
textView.setText("Hello");
// 内部: mText = "Hello" → requestLayout() → measure → layout → draw

// Thread B: 同时修改同一个 TextView
textView.setText("World");
// 内部: mText = "World" → requestLayout() → measure → layout → draw

// 结果不确定：可能显示"Hello"、"World"，
// 也可能 measure 用的是"Hello"的宽度，draw 用的是"World"的文本 → 显示错乱
```

**死锁（Deadlock）：**

```
Thread A: 持有 ViewA 锁 → 等待 ViewB 锁（因为 ViewA 的 layout 依赖 ViewB 的尺寸）
Thread B: 持有 ViewB 锁 → 等待 ViewA 锁（因为 ViewB 的 layout 依赖 ViewA 的位置）
→ 两个线程永远等待 → 界面冻结
```

**不确定性（Non-determinism）：**

多线程的执行顺序取决于操作系统调度，同样的代码，每次运行可能产生不同的结果。UI 框架有大量的状态依赖（View 树的遍历顺序、invalidate 区域的合并、动画的帧序列），多线程访问会使 UI 行为完全不可预测。

### 2.2 单线程的设计哲学

Android 选择了一个更优雅的方案：**将"并发"转化为"串行化的异步任务"。**

```
多线程模型:
  Thread A ──修改 View──→ ┐
  Thread B ──修改 View──→ ├→ 竞态！需要锁！可能死锁！
  Thread C ──修改 View──→ ┘

单线程 + 消息队列模型:
  Thread A ──post(修改View)──→ ┐
  Thread B ──post(修改View)──→ ├→ MessageQueue → 主线程按顺序逐条处理 → 无竞态
  Thread C ──post(修改View)──→ ┘
```

**核心思想：** 不管有多少个线程想要修改 UI，它们都不能直接操作 View，而是将操作封装成一条 Message 发送到主线程的消息队列。主线程按照消息的先后顺序，一条一条地执行这些操作。

这从根本上消除了竞态条件——因为永远只有一个线程在操作 UI。不需要锁，不会死锁，行为完全确定。

### 2.3 代价：单线程的阿喀琉斯之踵

单线程模型消除了并发问题，但引入了一个新的问题：**所有消息共享同一个执行线程，任何一条消息的处理耗时过长，都会阻塞后续所有消息。**

```
消息队列: [消息A: 3ms] [消息B: 800ms!!!] [消息C: 2ms] [消息D: Input事件] [消息E: VSync渲染]
                              ↑
                      消息B 耗时 800ms
                      → 消息C/D/E 全部排队等待
                      → Input 事件无法响应 → 如果超过 5 秒 → Input ANR
                      → VSync 渲染无法执行 → 掉帧 → 用户感知到卡顿
```

**这就是卡顿和 ANR 的根源。** 单线程模型把"并发安全问题"转化为了"消息处理耗时问题"。对于稳定性架构师来说，核心目标就是：**确保每条消息的处理时间尽可能短（通常要求 < 16ms 以保障 60fps 渲染）。**

---

## 3. 四大核心组件

消息机制由四个紧密协作的组件构成：Handler、Looper、MessageQueue、Message。理解它们各自的职责和协作关系，是掌握整个消息机制的基础。

### 3.1 组件职责速览

| 组件 | 角色 | 一句话定义 | 核心源码 |
| :--- | :--- | :--- | :--- |
| **Handler** | 消息的发送者与处理者 | 桥接业务代码与消息队列 | `frameworks/base/core/java/android/os/Handler.java` |
| **Looper** | 消息循环泵 | 从 MessageQueue 取消息并分发给 Handler | `frameworks/base/core/java/android/os/Looper.java` |
| **MessageQueue** | 消息队列 | Java 层按 when 排序的单链表 + Native 层 epoll 阻塞唤醒 | `frameworks/base/core/java/android/os/MessageQueue.java` |
| **Message** | 消息载体 | 携带数据的对象，通过对象池复用减少 GC | `frameworks/base/core/java/android/os/Message.java` |

### 3.2 四者的协作关系

```
                         ┌──────────────────────────────────────────────────┐
                         │              业务代码 / 系统服务                  │
                         │   (Activity / Service / AMS / InputDispatcher)   │
                         └────────────────┬────────────────┬────────────────┘
                                 发送消息  │                │ 处理回调
                                          ▼                ▲
                         ┌─────────────────────────────────────────────────┐
                         │                   Handler                       │
                         │  sendMessage() / post()    dispatchMessage()    │
                         │  sendMessageDelayed()      handleMessage()      │
                         └────────────┬───────────────────▲────────────────┘
                            enqueue   │                   │ dispatch
                                      ▼                   │
                         ┌─────────────────────────────────────────────────┐
                         │               MessageQueue                      │
                         │  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐           │
                         │  │msg1 │→ │msg2 │→ │msg3 │→ │msg4 │→ null     │
                         │  │when │  │when │  │when │  │when │           │
                         │  │=100 │  │=150 │  │=200 │  │=350 │           │
                         │  └─────┘  └─────┘  └─────┘  └─────┘           │
                         │                                                 │
                         │  nativePollOnce()          nativeWake()         │
                         └────────────┬───────────────────▲────────────────┘
                            next()    │                   │ 新消息入队唤醒
                                      ▼                   │
                         ┌─────────────────────────────────────────────────┐
                         │                   Looper                        │
                         │  for (;;) {                                     │
                         │      Message msg = queue.next(); // 阻塞等待    │
                         │      msg.target.dispatchMessage(msg);           │
                         │      msg.recycleUnchecked();                    │
                         │  }                                              │
                         └─────────────────────────────────────────────────┘
```

### 3.3 Handler —— 消息的发送者与处理者

Handler 是应用代码与消息机制交互的唯一入口。它有两个核心职责：

1. **发送消息**：将 Message 放入 MessageQueue
2. **处理消息**：当 Looper 从队列取出消息后，回调 Handler 的处理方法

```java
// frameworks/base/core/java/android/os/Handler.java（关键字段与方法）
public class Handler {
    final Looper mLooper;           // 绑定的 Looper
    final MessageQueue mQueue;      // Looper 关联的 MessageQueue
    final Callback mCallback;       // 可选的回调接口

    // 发送消息（所有 sendMessage 变体最终汇聚于此）
    public boolean sendMessageAtTime(Message msg, long uptimeMillis) {
        MessageQueue queue = mQueue;
        return enqueueMessage(queue, msg, uptimeMillis);
    }

    private boolean enqueueMessage(MessageQueue queue, Message msg, long uptimeMillis) {
        msg.target = this;  // Message 持有发送它的 Handler 的引用（泄漏风险点！）
        return queue.enqueueMessage(msg, uptimeMillis);
    }

    // 消息分发（Looper 调用）—— 三级优先级
    public void dispatchMessage(Message msg) {
        if (msg.callback != null) {         // 优先级 1: Message 自带的 Runnable
            handleCallback(msg);
        } else {
            if (mCallback != null) {        // 优先级 2: Handler 构造时传入的 Callback
                if (mCallback.handleMessage(msg)) {
                    return;
                }
            }
            handleMessage(msg);             // 优先级 3: 子类重写的 handleMessage()
        }
    }
}
```

**稳定性关键点：** `msg.target = this` —— 每条 Message 都持有发送它的 Handler 的引用。如果 Handler 是 Activity 的非静态内部类（持有 Activity 引用），而 Message 是延迟消息（在队列中等待较长时间），就形成了经典的内存泄漏链：`MessageQueue → Message → Handler → Activity`。

### 3.4 Looper —— 消息循环泵

Looper 是消息机制的驱动引擎。它绑定到一个线程上，在一个无限循环中不断从 MessageQueue 取出消息并分发给对应的 Handler。

```java
// frameworks/base/core/java/android/os/Looper.java（核心逻辑）
public final class Looper {
    static final ThreadLocal<Looper> sThreadLocal = new ThreadLocal<>();
    private static Looper sMainLooper;   // 主线程 Looper 的静态引用
    final MessageQueue mQueue;           // 每个 Looper 对应一个 MessageQueue

    // 核心循环
    public static void loop() {
        final Looper me = myLooper();
        final MessageQueue queue = me.mQueue;
        for (;;) {
            Message msg = queue.next();  // 可能阻塞（底层 epoll_wait）
            if (msg == null) {
                return;  // msg == null 表示 MessageQueue 正在退出
            }

            // 分发消息给目标 Handler
            msg.target.dispatchMessage(msg);

            // 回收 Message 到对象池
            msg.recycleUnchecked();
        }
    }
}
```

**稳定性关键点：** `for (;;)` 是一个永不退出的循环（主线程的 Looper 不允许 quit）。`queue.next()` 在没有消息时会通过 `nativePollOnce()` 陷入 `epoll_wait` 阻塞，不消耗 CPU。一旦有新消息到来或定时消息到期，`epoll_wait` 返回，`next()` 取出消息，交给 `msg.target.dispatchMessage()` 处理。

### 3.5 MessageQueue —— 双层架构的消息队列

MessageQueue 不是一个简单的 Java 集合类，它是一个跨越 Java 层和 Native 层的双层架构：

- **Java 层**：维护一个按 `when`（执行时间）排序的 Message 单链表
- **Native 层**：通过 `epoll` + `eventfd` 实现阻塞唤醒机制

```java
// frameworks/base/core/java/android/os/MessageQueue.java（核心字段）
public final class MessageQueue {
    Message mMessages;              // 链表头指针
    private long mPtr;              // Native 层 NativeMessageQueue 的指针

    // 消息入队 —— 按 when 排序插入链表
    boolean enqueueMessage(Message msg, long when) {
        synchronized (this) {
            msg.when = when;
            Message p = mMessages;
            boolean needWake;
            if (p == null || when == 0 || when < p.when) {
                msg.next = p;
                mMessages = msg;
                needWake = mBlocked;  // 如果 Looper 正在阻塞，需要唤醒
            } else {
                // 按 when 找到合适的插入位置
                Message prev;
                for (;;) {
                    prev = p;
                    p = p.next;
                    if (p == null || when < p.when) break;
                }
                msg.next = p;
                prev.next = msg;
            }
            if (needWake) {
                nativeWake(mPtr);   // 唤醒 Native 层的 epoll_wait
            }
        }
    }
}
```

**稳定性关键点：** `enqueueMessage` 的 `synchronized (this)` 是消息机制中少数几个锁之一。高频发送消息时，多个线程竞争此锁可能导致轻微的性能问题。更关键的是 `nativeWake()` —— 每次插入到链表头部时都会唤醒 Native 层，高频唤醒会增加 CPU 开销和功耗。

### 3.6 Message —— 消息载体与对象池

Message 是消息的数据载体，承载了消息的类型、参数、执行时间等所有信息。为了减少频繁创建/销毁 Message 对象带来的 GC 压力，Message 实现了对象池（Object Pool）复用机制。

```java
// frameworks/base/core/java/android/os/Message.java（核心字段）
public final class Message implements Parcelable {
    public int what;          // 消息类型标识
    public int arg1;          // 轻量参数 1
    public int arg2;          // 轻量参数 2
    public Object obj;        // 任意对象参数
    public long when;         // 期望执行时间（SystemClock.uptimeMillis）
    Handler target;           // 目标 Handler（谁来处理这条消息）
    Runnable callback;        // post(Runnable) 时设置的回调
    Message next;             // 链表指针（在 MessageQueue 和对象池中都用到）

    // 对象池 —— 静态单链表，最多缓存 50 个
    private static Message sPool;
    private static int sPoolSize = 0;
    private static final int MAX_POOL_SIZE = 50;

    // 获取 Message（优先从对象池复用）
    public static Message obtain() {
        synchronized (sPoolSync) {
            if (sPool != null) {
                Message m = sPool;
                sPool = m.next;
                m.next = null;
                m.flags = 0;
                sPoolSize--;
                return m;
            }
        }
        return new Message();
    }
}
```

**稳定性关键点：**

- **始终使用 `Message.obtain()` 而非 `new Message()`**：直接 new 会绕过对象池，导致频繁 GC，在高频消息场景下引发卡顿。
- **`target` 字段**：Message 通过 `target` 引用 Handler，这是内存泄漏链的关键一环。
- **`when` 字段**：使用 `SystemClock.uptimeMillis()`（不包含深度睡眠时间），而非 `System.currentTimeMillis()`。深度睡眠后唤醒，不会导致大量定时消息同时到期。

---

## 4. 四层架构全景图

消息机制不仅是 Java 层的几个类，它贯穿了从应用层到 Linux 内核的四个层次。理解这个分层结构，在排查问题时才能精确定位故障点在哪一层。

### 4.1 架构全景

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Application Layer                                │
│                                                                         │
│   Activity          Fragment         Service          BroadcastReceiver │
│      │                  │                │                    │         │
│      └──── Handler.sendMessage() / Handler.post() ──────────┘         │
│                              │                                          │
├──────────────────────────────┼──────────────────────────────────────────┤
│                     Java Framework Layer                                │
│                              │                                          │
│   Handler.java ──── enqueueMessage() ────→ MessageQueue.java           │
│                                                   │                     │
│   Looper.java ←── queue.next() ──────────────────┘                     │
│       │                                                                 │
│       └── msg.target.dispatchMessage(msg)                              │
│                              │                                          │
├──────────────────────────────┼──────────────────────────────────────────┤
│                        JNI Bridge Layer                                  │
│                              │                                          │
│   android_os_MessageQueue.cpp                                           │
│       nativePollOnce()  ──→  NativeMessageQueue::pollOnce()            │
│       nativeWake()      ──→  NativeMessageQueue::wake()                │
│                              │                                          │
├──────────────────────────────┼──────────────────────────────────────────┤
│                        Native Layer                                     │
│                              │                                          │
│   system/core/libutils/Looper.cpp                                       │
│       pollOnce() ──→ pollInner() ──→ epoll_wait()   ← 阻塞等待事件     │
│       wake()     ──→ write(mWakeEventFd, ...)        ← 写 eventfd 唤醒  │
│                              │                                          │
├──────────────────────────────┼──────────────────────────────────────────┤
│                     Linux Kernel                                        │
│                              │                                          │
│   epoll  ──  eventfd  ──  timerfd                                       │
│   (I/O 多路复用)  (唤醒通知)  (定时器)                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 各层关键文件

| 层级 | 关键文件 | 职责 |
| :--- | :--- | :--- |
| Java Framework | `frameworks/base/core/java/android/os/Handler.java` | 消息发送与分发 |
| Java Framework | `frameworks/base/core/java/android/os/Looper.java` | 消息循环驱动 |
| Java Framework | `frameworks/base/core/java/android/os/MessageQueue.java` | 消息队列管理 |
| Java Framework | `frameworks/base/core/java/android/os/Message.java` | 消息数据载体 |
| JNI Bridge | `frameworks/base/core/jni/android_os_MessageQueue.cpp` | Java↔Native 桥接 |
| Native | `system/core/libutils/Looper.cpp` | epoll 驱动的事件循环 |
| Native | `system/core/libutils/include/utils/Looper.h` | Native Looper 头文件 |

### 4.3 为什么需要 Native 层

一个自然的问题是：Java 层已经有了 `MessageQueue` 和 `Looper`，为什么还需要 Native 层？

原因有三：

1. **高效阻塞唤醒**：Java 的 `Object.wait()` / `notify()` 只能等待 Java 层事件。而 `epoll_wait()` 可以同时等待多种事件源——消息到期、Input 事件（fd）、VSync 信号（fd）、Binder 回调（fd）。这是单纯 Java 层无法做到的。

2. **统一事件模型**：Native Looper 通过 `addFd()` 可以将任意文件描述符注入事件循环。InputDispatcher 通过 InputChannel（本质是 socketpair 的 fd）向应用投递输入事件，Choreographer 通过 VSync 的 fd 接收垂直同步信号——都通过同一个 `epoll` 实例统一管理。

3. **Native 消息支持**：Native 层的 Looper 也有自己的消息队列（`MessageEnvelope`），C++ 代码可以直接向 Native Looper 发送消息，不必绕道 Java 层。

**稳定性视角：** 当你在 ANR trace 中看到主线程停在 `nativePollOnce()` 时，这意味着主线程正在 `epoll_wait()` 中阻塞，等待新消息或 fd 事件。这通常是正常的——说明消息队列为空，主线程处于空闲状态。但如果此时有大量待处理消息却仍然阻塞，则可能是 `nativeWake()` 失败或 epoll fd 异常。

---

## 5. 消息机制在系统中的核心角色

消息机制不是一个孤立的工具类——它是 Android 系统的"神经系统"，连接着几乎所有重要的子系统。以下是五个最关键的场景。

### 5.1 Activity 生命周期驱动

Activity 的 `onCreate()`、`onResume()`、`onPause()` 等生命周期回调，并不是由 AMS 直接调用的。它们经过一条精确的消息传递链路：

```
AMS (system_server 进程)
    ↓ Binder 调用（跨进程）
ApplicationThread (App 进程的 Binder 线程)
    ↓ Handler.sendMessage()（切换到主线程）
ActivityThread.H (Handler 子类, 主线程)
    ↓ handleMessage()
handleLaunchActivity() / handleResumeActivity() / handlePauseActivity()
    ↓
Activity.onCreate() / onResume() / onPause()
```

```java
// frameworks/base/core/java/android/app/ActivityThread.java（简化）
class H extends Handler {
    public static final int EXECUTE_TRANSACTION = 159;

    public void handleMessage(Message msg) {
        switch (msg.what) {
            case EXECUTE_TRANSACTION:
                final ClientTransaction transaction = (ClientTransaction) msg.obj;
                mTransactionExecutor.execute(transaction);
                break;
        }
    }
}

// ApplicationThread（Binder 线程）收到 AMS 调用后
private class ApplicationThread extends IApplicationThread.Stub {
    @Override
    public void scheduleTransaction(ClientTransaction transaction) {
        // 将 transaction 封装为 Message，发送到主线程的 Handler
        ActivityThread.this.scheduleTransaction(transaction);
    }
}
```

**稳定性关联：** 生命周期消息在消息队列中排队。如果主线程正在处理耗时操作，`EXECUTE_TRANSACTION` 消息无法及时被处理 → Activity 启动缓慢 → 用户感知白屏。在极端情况下（如主线程死锁），AMS 等待超时 → 触发 ANR。

### 5.2 Input 事件分发

用户的每一次触摸、滑动、按键操作，都通过消息机制送达应用：

```
硬件中断 → Linux Input 子系统 → /dev/input/event*
    ↓
InputReader (读取原始事件)
    ↓
InputDispatcher (找到目标窗口)
    ↓ 通过 InputChannel (Unix Domain Socket pair) 发送
NativeLooper.addFd(inputChannel.fd)  ← 将 fd 注册到应用主线程的 epoll
    ↓ epoll_wait 返回，fd 可读
ViewRootImpl.WindowInputEventReceiver.onInputEvent()
    ↓
View 事件分发: dispatchTouchEvent → onTouchEvent
```

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java（简化）
final class WindowInputEventReceiver extends InputEventReceiver {
    @Override
    public void onInputEvent(InputEvent event) {
        // 在主线程中处理输入事件
        enqueueInputEvent(event, this, 0, true);
    }
}
```

**稳定性关联：** InputDispatcher 发送事件后会启动一个 5 秒计时器。如果应用的主线程 Looper 在 5 秒内没有处理完这个事件（通过 InputChannel 回复"已处理"），InputDispatcher 就会判定为 Input ANR。这是最常见的 ANR 类型。

### 5.3 UI 渲染驱动

Android 的 UI 渲染由 `Choreographer`（编舞者）通过 VSync 信号驱动，整个流程都建立在消息机制之上：

```
SurfaceFlinger 发出 VSync 信号
    ↓ 通过 fd 传递
Choreographer 收到 VSync
    ↓ 插入同步屏障（阻止普通消息，优先处理渲染）
FrameHandler.sendMessage(MSG_DO_FRAME)  ← 异步消息，不受屏障阻挡
    ↓ 主线程 Looper 分发
Choreographer.doFrame()
    ↓ 按顺序执行回调
    ├── INPUT      (处理输入事件)
    ├── ANIMATION  (处理动画)
    ├── TRAVERSAL  (View 的 measure/layout/draw)
    └── COMMIT     (提交帧数据)
    ↓ 移除同步屏障
```

```java
// frameworks/base/core/java/android/view/Choreographer.java（简化）
void doFrame(long frameTimeNanos, int frame) {
    // 处理各类回调
    doCallbacks(Choreographer.CALLBACK_INPUT, frameTimeNanos);
    doCallbacks(Choreographer.CALLBACK_ANIMATION, frameTimeNanos);
    doCallbacks(Choreographer.CALLBACK_TRAVERSAL, frameTimeNanos);
    doCallbacks(Choreographer.CALLBACK_COMMIT, frameTimeNanos);
}
```

**稳定性关联：** 如果同步屏障被插入但忘记移除（`removeSyncBarrier` 未被调用），所有普通同步消息将被永远阻塞 → 生命周期回调、广播接收等全部卡死 → 触发 ANR。这是一个隐蔽但致命的稳定性问题。

### 5.4 ANR 检测：超时炸弹机制

ANR（Application Not Responding）的检测机制，本质上就是 Handler 的 `sendMessageDelayed()`：

```
AMS 发起请求（如启动 Service）
    ↓
同时: Handler.sendMessageDelayed(SERVICE_TIMEOUT_MSG, 20*1000)  ← 埋下超时炸弹
    ↓
App 执行 Service.onCreate()
    ↓ 完成后
AMS 移除超时消息: Handler.removeMessages(SERVICE_TIMEOUT_MSG)   ← 拆除炸弹
    ↓
如果 20 秒内未完成:
    ↓ 超时消息被 Looper 取出并分发
serviceTimeout() → 收集 ANR 信息 → 弹出 ANR 对话框
```

```java
// frameworks/base/services/core/java/com/android/server/am/ActiveServices.java（简化）
private void realStartServiceLocked(ServiceRecord r, ProcessRecord app) {
    // 埋超时炸弹
    bumpServiceExecutingNoClearLocked(r, "create");
    // → 内部调用 mAm.mHandler.sendMessageDelayed(msg, timeout)

    // 通过 Binder 通知 App 启动 Service
    app.thread.scheduleCreateService(r, ...);
}

void serviceDoneExecutingLocked(ServiceRecord r, ...) {
    // App 完成后拆除炸弹
    mAm.mHandler.removeMessages(ActivityManagerService.SERVICE_TIMEOUT_MSG, r);
}
```

**稳定性关联：** 四种 ANR 都基于同一机制：

| ANR 类型 | 超时时间 | 超时消息 |
| :--- | :--- | :--- |
| Input 事件 | 5 秒 | InputDispatcher 内部计时 |
| Broadcast 前台 | 10 秒 | `BROADCAST_TIMEOUT_MSG` |
| Broadcast 后台 | 60 秒 | `BROADCAST_TIMEOUT_MSG` |
| Service 前台 | 20 秒 | `SERVICE_TIMEOUT_MSG` |
| Service 后台 | 200 秒 | `SERVICE_TIMEOUT_MSG` |
| ContentProvider | 10 秒 | `CONTENT_PROVIDER_PUBLISH_TIMEOUT_MSG` |

### 5.5 Binder 回调转线程

Binder 调用的回调在 Binder 线程池中执行，不能直接操作 UI。消息机制提供了标准的线程切换方案：

```
Binder 线程收到回调（如 AMS 通知）
    ↓
Handler.sendMessage()  ← 将任务封装为 Message 发到主线程队列
    ↓
主线程 Looper 取出消息
    ↓
Handler.handleMessage()  ← 在主线程安全地执行 UI 操作
```

这是 Android 中最基本的线程切换模式。`ActivityThread.H` 就是这个模式的典型实现：Binder 线程通过 `ApplicationThread`（Stub）收到系统调用，然后通过 `H`（Handler）切换到主线程执行。

**稳定性关联：** 如果 Binder 线程直接向主线程 post 大量消息（如连续的数据变更通知），可能导致消息队列堆积 → 主线程处理不过来 → 卡顿甚至 ANR。

---

## 6. 核心源码目录导航

排查消息机制相关问题时，以下文件和目录是必须熟悉的"地图"：

### 6.1 Java Framework 层

| 文件路径 | 核心内容 |
| :--- | :--- |
| `frameworks/base/core/java/android/os/Handler.java` | 消息发送（sendMessage 系列）、消息分发（dispatchMessage）、消息移除（removeMessages / removeCallbacks） |
| `frameworks/base/core/java/android/os/Looper.java` | prepare() / loop() / quit() / myLooper()；ThreadLocal 绑定；Printer 和 Observer 监控钩子 |
| `frameworks/base/core/java/android/os/MessageQueue.java` | 消息入队（enqueueMessage）、消息出队（next）、同步屏障（postSyncBarrier / removeSyncBarrier）、IdleHandler |
| `frameworks/base/core/java/android/os/Message.java` | 消息字段定义、对象池（obtain / recycle）、Parcelable 序列化 |
| `frameworks/base/core/java/android/os/HandlerThread.java` | 自带 Looper 的工作线程封装 |

### 6.2 系统服务层

| 文件路径 | 核心内容 |
| :--- | :--- |
| `frameworks/base/core/java/android/app/ActivityThread.java` | App 主线程入口 main()；内部类 H (Handler)；ApplicationThread (Binder Stub) |
| `frameworks/base/core/java/android/view/ViewRootImpl.java` | UI 渲染入口；scheduleTraversals() 插入同步屏障；WindowInputEventReceiver 接收输入事件 |
| `frameworks/base/core/java/android/view/Choreographer.java` | VSync 驱动的帧调度；doFrame()；FrameCallback |
| `frameworks/base/services/core/java/com/android/server/am/ActiveServices.java` | Service ANR 超时炸弹的埋设与拆除 |
| `frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java` | Broadcast ANR 超时机制 |

### 6.3 JNI 桥接层

| 文件路径 | 核心内容 |
| :--- | :--- |
| `frameworks/base/core/jni/android_os_MessageQueue.cpp` | nativePollOnce / nativeWake 的 JNI 实现；NativeMessageQueue 类 |
| `frameworks/base/core/jni/android_os_MessageQueue.h` | NativeMessageQueue 头文件 |

### 6.4 Native 层

| 文件路径 | 核心内容 |
| :--- | :--- |
| `system/core/libutils/Looper.cpp` | Native Looper 实现：pollOnce / pollInner（epoll_wait）/ wake（eventfd write）/ addFd / removeFd |
| `system/core/libutils/include/utils/Looper.h` | Native Looper 头文件：MessageHandler / MessageEnvelope / Request 等数据结构 |

### 6.5 快速定位指南

| 问题场景 | 首先查看 |
| :--- | :--- |
| ANR trace 中主线程在处理什么消息 | `Looper.java` loop() 循环 |
| 消息队列是否堆积 | `MessageQueue.java` mMessages 链表 |
| 为什么主线程阻塞在 nativePollOnce | `android_os_MessageQueue.cpp` + `Looper.cpp` |
| 同步屏障是否泄漏 | `MessageQueue.java` postSyncBarrier / removeSyncBarrier |
| Activity 生命周期回调延迟 | `ActivityThread.java` 内部类 H |
| Input ANR | `ViewRootImpl.java` WindowInputEventReceiver |
| 渲染掉帧 | `Choreographer.java` doFrame() |

---

## 7. 稳定性实战案例

### 案例一：同步屏障泄漏导致主线程"假死"

**现象：**

线上监控平台收到大量 ANR 上报，集中在某个特定页面。ANR trace 显示主线程停在 `nativePollOnce()`，看起来像是主线程空闲——但用户反馈界面完全卡死，点击无响应。

```
"main" prio=5 tid=1 Native
  | group="main" sCount=1 ucsCount=0 flags=1 obj=0x72a5a000 self=0xb400007d...
  | sysTid=12345 nice=-10 cgrp=top-app sched=0/0 handle=0x7e0e330...
  at android.os.MessageQueue.nativePollOnce(Native method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  at android.os.Looper.loop(Looper.java:206)
  at android.app.ActivityThread.main(ActivityThread.java:8110)
```

**分析：**

主线程在 `nativePollOnce()` 阻塞，通常意味着消息队列为空。但 ANR 说明系统发来的消息（如 Input 事件）没有被处理。这个矛盾指向一个特殊情况：**同步屏障（Sync Barrier）未被移除。**

同步屏障是 `target == null` 的特殊 Message，一旦存在，`MessageQueue.next()` 会跳过所有普通同步消息，只处理异步消息。如果队列中没有异步消息，`next()` 就会进入 `nativePollOnce()` 阻塞——即使队列中有大量同步消息等待处理。

通过 dumpsys 获取更详细的 MessageQueue 状态：

```
Message Queue (has barrier):
  Message 0: { when=-5s23ms barrier=42 }    ← 同步屏障！token=42
  Message 1: { when=-4s988ms what=159 target=Handler (android.app.ActivityThread$H) }
  Message 2: { when=-4s500ms what=0 target=Handler (com.example.app.MainActivity$1) }
  ... (30+ pending messages blocked behind the barrier)
```

**根因：**

定位到问题页面的代码，发现一个自定义动画控制器在 `onAnimationStart()` 中调用了 `ViewRootImpl.scheduleTraversals()`（通过反射），该方法会插入同步屏障。但动画在异常路径下（Fragment detach）取消后，`unscheduleTraversals()` 没有被调用，导致 `removeSyncBarrier()` 遗漏。

```java
// 问题代码（简化）
public class CustomAnimController {
    private int mBarrierToken;

    void startCustomTraversal() {
        // 通过反射调用了 ViewRootImpl 的内部方法
        mBarrierToken = mQueue.postSyncBarrier();  // 插入屏障
        // ... 发送异步消息执行自定义渲染逻辑
    }

    void onAnimationEnd() {
        mQueue.removeSyncBarrier(mBarrierToken);   // 正常路径：移除屏障
    }

    // BUG: Fragment detach 时 onAnimationEnd 不会被调用！
    // → 屏障永远留在队列中 → 所有同步消息被阻塞
}
```

**修复：**

1. **直接修复**：在 Fragment 的 `onDestroyView()` 中确保移除同步屏障：

```java
@Override
public void onDestroyView() {
    super.onDestroyView();
    if (mAnimController != null) {
        mAnimController.forceCleanup();  // 内部调用 removeSyncBarrier
    }
}
```

2. **防御性措施**：添加同步屏障的超时保护机制：

```java
void startCustomTraversal() {
    mBarrierToken = mQueue.postSyncBarrier();
    // 10 秒后如果屏障还在，强制移除（防止泄漏）
    mHandler.postDelayed(() -> {
        try {
            mQueue.removeSyncBarrier(mBarrierToken);
            Log.w(TAG, "Sync barrier leaked! Force removed.");
        } catch (IllegalStateException e) {
            // 已经被正常移除，忽略
        }
    }, 10_000);
}
```

3. **监控建设**：在消息监控 SDK 中加入同步屏障检测——如果检测到屏障存在超过 3 秒，上报异常日志。

---

### 案例二：Handler 内存泄漏导致 OOM Crash

**现象：**

线上 OOM（OutOfMemoryError）Crash 率在某版本上升 15%。Crash 堆栈显示是 Bitmap 分配失败，但 hprof 分析后发现大量已 finish 的 Activity 实例无法被 GC 回收。

```
java.lang.OutOfMemoryError: Failed to allocate a 4194316 byte allocation
    with 2097152 free bytes and 3MB until OOM
  at android.graphics.Bitmap.nativeCreate(Native Method)
  at android.graphics.Bitmap.createBitmap(Bitmap.java:1113)
  ...
```

**分析：**

使用 LeakCanary + MAT 分析 hprof，发现泄漏链路：

```
GC Root: Thread "main"
  → MessageQueue.mMessages (Message 链表)
    → Message.next → ... → Message (when = uptimeMillis + 300000, 5 分钟后)
      → Message.target = MainActivity$InnerHandler
        → InnerHandler.this$0 = MainActivity (已 finish，无法回收！)
          → MainActivity.mBitmap (8MB)
          → MainActivity.mAdapter → 大量 ViewHolder → 大量 Bitmap
```

关键发现：有一个 `Message` 被设置为 5 分钟后执行（`Handler.sendMessageDelayed(msg, 300_000)`），在 Activity finish 之后，这条消息仍然在 MessageQueue 中等待，其 `target` 引用了一个非静态内部类 Handler，进而引用了已销毁的 Activity 及其所有成员变量。

**为何会泄露？** 容易产生的误解是：「Handler 是 Activity 的成员，Activity 销毁时 Handler 自然就销毁，引用就断了。」实际上泄露时的引用方向恰恰相反：**MessageQueue（主线程，与进程同寿）→ 队列里的 Message → Message.target（你的 Handler）→ Handler 的 this$0（非静态内部类隐式持有 Activity）→ Activity**。Activity 调用 `finish()` 后，没有任何逻辑会自动把这条尚未触发的 Message 从主线程的 MessageQueue 里移除，因此只要 Message 还在队列里，Handler 就被强引用着、无法被 GC，Handler 又强引用着 Activity，所以 Activity 也无法被回收。也就是说：不是「Handler 销毁了 Activity 才销毁」，而是「Message 一直不丢，Handler 就一直活着，Activity 就永远达不到可回收状态」。

**根因：**

问题代码使用了匿名内部类 Handler + 长延迟消息：

```java
// 问题代码
public class MainActivity extends AppCompatActivity {
    private final Handler mHandler = new Handler() {   // 非静态匿名内部类！
        @Override
        public void handleMessage(Message msg) {
            // 引用了 MainActivity.this
            refreshData();
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // 每 5 分钟刷新一次数据
        mHandler.sendEmptyMessageDelayed(MSG_REFRESH, 5 * 60 * 1000);
    }

    // 没有在 onDestroy 中清理消息！
}
```

引用链：`MessageQueue → Message(delayed 5min) → Handler(匿名内部类) → MainActivity → 所有 View 和 Bitmap`

**单次进入 vs 多次进出：** 若用户只进入一次该 Activity 然后 finish，5 分钟后这条消息被 Looper 取出并执行完毕，Message 不再被队列引用，Handler 和 Activity 随后都可被 GC，严格说是「延迟约 5 分钟释放」而非永久泄露。真正导致 OOM 的是**在延迟时间内反复进入、退出**：每次进入都会新建一个 Activity 实例并再发一条 5 分钟延迟消息，而之前发出的消息仍在队列里，对应的旧 Activity 仍被引用无法回收，多颗已 finish 的 Activity 同时在内存中堆积（且每颗可能持有 Bitmap、Adapter 等），内存持续增长直至 OOM。因此：单次顶多是 5 分钟内不释放；多次进出则会在同一时段内积压多实例，形成泄露导致的 OOM。

**修复：**

1. **使用静态内部类 + WeakReference**：

```java
public class MainActivity extends AppCompatActivity {
    private static class SafeHandler extends Handler {
        private final WeakReference<MainActivity> mActivity;

        SafeHandler(MainActivity activity) {
            mActivity = new WeakReference<>(activity);
        }

        @Override
        public void handleMessage(Message msg) {
            MainActivity activity = mActivity.get();
            if (activity == null || activity.isFinishing()) {
                return;  // Activity 已销毁，安全跳过
            }
            activity.refreshData();
        }
    }

    private final SafeHandler mHandler = new SafeHandler(this);

    @Override
    protected void onDestroy() {
        super.onDestroy();
        mHandler.removeCallbacksAndMessages(null);  // 清除所有消息和回调
    }
}
```

2. **Lifecycle 感知方案（推荐）**：

```java
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Handler handler = new Handler(Looper.getMainLooper());
        getLifecycle().addObserver(new DefaultLifecycleObserver() {
            @Override
            public void onDestroy(LifecycleOwner owner) {
                handler.removeCallbacksAndMessages(null);
            }
        });
    }
}
```

3. **代码规范与检测**：
   - Lint 规则：禁止非静态内部类 Handler（`HandlerLeak` 检查）
   - CI 流水线：集成 LeakCanary 的自动化测试，检测 Activity 泄漏
   - Code Review Checklist：所有 `Handler.sendMessageDelayed()` 和 `Handler.postDelayed()` 必须有对应的 `removeCallbacksAndMessages(null)` 清理

---

## 总结

本文建立了 Handler 消息机制的全局视图：

| 维度 | 核心认知 |
| :--- | :--- |
| **本质** | 单线程事件循环——所有 UI 操作、系统回调、定时任务通过消息队列串行化处理 |
| **设计哲学** | 用串行化消除并发竞态，代价是单条消息阻塞会影响全局 |
| **核心组件** | Handler（发送+处理）、Looper（循环泵）、MessageQueue（双层队列）、Message（数据载体） |
| **架构分层** | Application → Java Framework → JNI Bridge → Native（epoll）→ Linux Kernel |
| **系统角色** | 驱动生命周期、输入事件、UI 渲染、ANR 检测、Binder 回调转线程 |
| **稳定性核心** | 卡顿 = 消息处理慢；ANR = 超时炸弹未拆除；泄漏 = Message 引用链未断开 |

在后续文章中，我们将逐层深入：

- **02-Looper 与线程模型**：从 `ActivityThread.main()` 到 `Looper.loop()` 的完整链路
- **03-MessageQueue 与 Native 层**：`epoll` + `eventfd` 的阻塞唤醒机制
- **04-Message 生命周期**：创建、分发、回收与对象池
- **05-同步屏障与异步消息**：UI 渲染的优先级保障
- **06-Handler 与 ANR**：从消息延迟到系统超时
