# 02-Looper 与线程模型：从 main() 到消息循环

上一篇我们建立了 Handler 消息机制的全局观：Android 选择单线程事件循环模型，通过 Handler / Looper / MessageQueue / Message 四个组件协作，将所有 UI 操作、系统回调、生命周期事件串行化处理。

但那只是宏观蓝图。现在我们要回答一个具体问题：**App 进程启动后，消息循环是如何跑起来的？**

这条链路是：

```
Zygote fork 出子进程
    → ActivityThread.main()         // Java 世界的入口
        → Looper.prepareMainLooper()  // 为主线程创建唯一 Looper
        → ActivityThread.attach()     // 向 AMS 注册自己
        → Looper.loop()              // 进入无限循环，永不返回
            → for(;;) {
                  msg = queue.next()       // 可能阻塞在 epoll
                  msg.target.dispatchMessage(msg) // 分发消息
                  msg.recycleUnchecked()   // 回收消息
              }
```

理解这条链路对稳定性架构师至少有三个直接用处：

1. **理解 ANR 的物理位置**：ANR 发生时，主线程一定卡在 `loop()` 的某一次迭代中。你在 ANR trace 里看到的 `Looper.loop()` → `Handler.dispatchMessage()` → 某个耗时方法，就是这个循环的一次执行。
2. **理解线程模型的约束**：为什么主线程 Looper 不能 quit？为什么 HandlerThread 忘记 quit 会导致线程泄漏？这些都来自 Looper 的设计约束。
3. **理解监控入口**：`Looper.loop()` 中的 Printer 回调和 Observer 回调，是所有卡顿监控方案（BlockCanary、Matrix、Sliver）的底层钩子。不理解 loop() 的结构，就无法理解这些监控方案的原理。

---

## 1. ActivityThread.main() — App 的真正入口

### 1.1 为什么要从 main() 说起

每个 Java 程序都有一个 `main()` 方法作为入口。Android App 也不例外——只不过这个 `main()` 不是你写的，而是系统提供的 `ActivityThread.main()`。

当 Zygote 收到 AMS 的 fork 请求后，子进程通过反射调用 `ActivityThread.main()`。这个方法做了三件关键的事：准备主线程 Looper、向 AMS 注册自己、启动消息循环。**如果这三步中任何一步失败，App 进程会直接退出或陷入不可预期的状态。**

### 1.2 源码走读

* **源码路径：** `frameworks/base/core/java/android/app/ActivityThread.java`

```java
// frameworks/base/core/java/android/app/ActivityThread.java（简化）
public static void main(String[] args) {
    // 1. 初始化主线程 Looper
    Looper.prepareMainLooper();

    // 2. 初始化 ActivityThread 实例
    ActivityThread thread = new ActivityThread();

    // 3. 向 AMS 注册（attach = true 表示系统进程自身）
    thread.attach(false, startSeq);

    // 4. 获取主线程 Handler（即 mH，类型为 ActivityThread.H）
    if (sMainThreadHandler == null) {
        sMainThreadHandler = thread.getHandler();
    }

    // 5. 进入消息循环 —— 永不返回
    Looper.loop();

    // 如果走到这里，说明 loop() 异常退出
    throw new RuntimeException("Main thread loop unexpectedly exited");
}
```

**逐行解读：**

| 步骤 | 方法 | 作用 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| 1 | `Looper.prepareMainLooper()` | 创建主线程 Looper，标记为 `sMainLooper`，设置不可 quit | 必须在 loop() 之前调用，否则 NPE |
| 2 | `new ActivityThread()` | 创建 App 的"管家"对象，包含 `mH`（Handler 子类） | `mH` 负责处理四大组件的生命周期消息 |
| 3 | `thread.attach(false)` | 通过 Binder 调用 AMS.attachApplication()，注册当前进程 | attach 失败 → AMS 不认识这个进程 → 无法启动 Activity |
| 4 | `thread.getHandler()` | 获取 `ActivityThread.H` 实例 | H 是 App 内部最重要的 Handler |
| 5 | `Looper.loop()` | 进入无限循环 | 这行代码之后的任何语句**在正常情况下永远不会执行** |

### 1.3 ActivityThread.H — 生命周期的调度中枢

`ActivityThread` 的内部类 `H` 继承自 `Handler`，负责处理系统发过来的生命周期消息。常见的消息类型包括：

```java
// frameworks/base/core/java/android/app/ActivityThread.java（H 内部类，简化）
class H extends Handler {
    public static final int BIND_APPLICATION    = 110;
    public static final int EXIT_APPLICATION    = 111;
    public static final int RECEIVER            = 113;
    public static final int CREATE_SERVICE      = 114;
    public static final int BIND_SERVICE        = 121;
    public static final int EXECUTE_TRANSACTION = 159; // Activity 生命周期事务
    // ...

    public void handleMessage(Message msg) {
        switch (msg.what) {
            case BIND_APPLICATION:
                handleBindApplication((AppBindData) msg.obj);
                break;
            case EXECUTE_TRANSACTION:
                // ClientTransaction 驱动 Activity 生命周期
                final ClientTransaction transaction = (ClientTransaction) msg.obj;
                mTransactionExecutor.execute(transaction);
                break;
            // ...
        }
    }
}
```

**稳定性关联：** 你在 ANR trace 中经常看到的 `ActivityThread$H.handleMessage` → `handleBindApplication` 或 `TransactionExecutor.execute`，就是 `H` 在处理这些消息。如果某条生命周期消息的处理耗时过长（比如 `Application.onCreate()` 中执行了重量级初始化），就会阻塞后续所有消息——包括 Input 事件的响应消息——从而触发 ANR。

---

## 2. Looper 内部实现

### 2.1 为什么 Looper 要绑定线程

Android 的消息循环模型有一个核心约束：**一个线程只能有一个 Looper，一个 Looper 只属于一个线程。** 这不是可选的设计偏好，而是强制约束——违反它会直接抛异常。

为什么要做这个约束？因为 Looper 持有 MessageQueue，MessageQueue 持有消息链表。如果一个线程绑定了两个 Looper，那消息应该发到哪个队列？如果一个 Looper 被两个线程共享，那谁来消费消息？多线程并发读写链表，不加锁就数据竞争，加锁就丧失了单线程模型的简洁性。

**一个线程一个 Looper** 的约束，消灭了这些歧义。

### 2.2 Looper 与 MessageQueue：一对一且不可更换

**一个 Looper 只能对应一个 MessageQueue，且不能更换。** 源码里体现为：Looper 的成员是 `final MessageQueue mQueue`，在私有构造函数中通过 `mQueue = new MessageQueue(quitAllowed)` 创建并赋值一次，之后没有任何 API 可以替换或注入其他队列。因此对应关系在 Looper 创建时确定，且在整个生命周期内不变。

这样设计的原因与「一线程一 Looper」一致：若一个 Looper 能对应多个队列或可中途换队列，就会产生「消息该进哪个队列、由谁消费」的歧义；允许换队列还要处理未处理完的消息和正在执行的 `loop()`，语义复杂且易出错。把 **一个 Looper 固定对应一个 MessageQueue 且不换** 作为不可变设计，才能让「一线程一 Looper」真正落地，避免多队列、多线程消费带来的竞争和复杂语义。

### 2.3 ThreadLocal 绑定机制

* **源码路径：** `frameworks/base/core/java/android/os/Looper.java`

```java
// frameworks/base/core/java/android/os/Looper.java
public final class Looper {
    // 每个线程独享自己的 Looper 实例
    static final ThreadLocal<Looper> sThreadLocal = new ThreadLocal<Looper>();

    // 主线程 Looper 的全局引用
    private static Looper sMainLooper;

    // 该 Looper 拥有的消息队列
    final MessageQueue mQueue;

    // 该 Looper 所在的线程
    final Thread mThread;

    private Looper(boolean quitAllowed) {
        mQueue = new MessageQueue(quitAllowed);
        mThread = Thread.currentThread();
    }
}
```

`ThreadLocal<Looper>` 的工作原理：每个线程内部持有一个 `ThreadLocalMap`，以 `ThreadLocal` 对象为 key 存取值。调用 `sThreadLocal.set(looper)` 时，looper 被存入**当前线程**的 map 中；调用 `sThreadLocal.get()` 时，从**当前线程**的 map 中取出。不同线程之间互不影响。

```
Thread-A 的 ThreadLocalMap:
    sThreadLocal → Looper-A (mQueue-A)

Thread-B 的 ThreadLocalMap:
    sThreadLocal → Looper-B (mQueue-B)

主线程的 ThreadLocalMap:
    sThreadLocal → sMainLooper (主 MessageQueue)
```

### 2.4 prepare() — 创建 Looper

```java
// frameworks/base/core/java/android/os/Looper.java
public static void prepare() {
    prepare(true); // 普通线程的 Looper 允许 quit
}

private static void prepare(boolean quitAllowed) {
    if (sThreadLocal.get() != null) {
        throw new RuntimeException("Only one Looper may be created per thread");
    }
    sThreadLocal.set(new Looper(quitAllowed));
}

public static void prepareMainLooper() {
    prepare(false); // 主线程 Looper 不允许 quit
    synchronized (Looper.class) {
        if (sMainLooper != null) {
            throw new IllegalStateException("The main Looper has already been prepared.");
        }
        sMainLooper = myLooper();
    }
}
```

**关键设计点：**

| 设计 | 实现 | 原因 |
| :--- | :--- | :--- |
| 一线程一 Looper | `sThreadLocal.get() != null` 时抛异常 | 消灭多 Looper 歧义 |
| 主线程不可 quit | `prepare(false)` → `quitAllowed = false` | 主线程退出 = 进程死亡 |
| 主线程 Looper 全局可达 | `sMainLooper` 静态变量 | 任何线程可通过 `Looper.getMainLooper()` 获取 |

**稳定性关联：** 如果你在工作线程中误调用了两次 `Looper.prepare()`，会得到 `RuntimeException: Only one Looper may be created per thread`。这个 crash 在某些库的初始化逻辑中偶尔出现——尤其是多线程并发初始化时，两个线程可能都在同一个线程池线程上调用 prepare()。

### 2.5 quit() vs quitSafely()

```java
// frameworks/base/core/java/android/os/Looper.java
public void quit() {
    mQueue.quit(false); // 立即退出
}

public void quitSafely() {
    mQueue.quit(true);  // 安全退出
}
```

```java
// frameworks/base/core/java/android/os/MessageQueue.java（简化）
void quit(boolean safe) {
    if (!mQuitAllowed) {
        throw new IllegalStateException("Main thread not allowed to quit.");
    }
    synchronized (this) {
        if (mQuitting) return;
        mQuitting = true;

        if (safe) {
            removeAllFutureMessagesLocked(); // 只移除 when > now 的消息
        } else {
            removeAllMessagesLocked();       // 移除所有消息
        }
        nativeWake(mPtr); // 唤醒可能阻塞在 epoll 的线程
    }
}
```

两者的差异：

```
quit()（非安全退出）：
    ┌─────────────────────────────────────────────┐
    │ Message 链表: [msg1(now)] [msg2(now+1s)] [msg3(now+5s)] │
    │                                                         │
    │ quit(false) → 全部丢弃                                   │
    │ 结果: 链表清空，msg1/msg2/msg3 全部不会被处理               │
    └─────────────────────────────────────────────┘

quitSafely()（安全退出）：
    ┌─────────────────────────────────────────────┐
    │ Message 链表: [msg1(now)] [msg2(now+1s)] [msg3(now+5s)] │
    │                                                         │
    │ quit(true) → 只丢弃 when > now 的消息                    │
    │ 结果: msg1 仍会被处理，msg2/msg3 被丢弃                    │
    └─────────────────────────────────────────────┘
```

**稳定性关联：** 使用 `quit()` 可能导致已经到期但尚未执行的消息被丢弃，引发业务逻辑不完整。例如一条数据库写入消息已经到期，但因为 `quit()` 被直接丢弃，导致数据丢失。**推荐总是使用 `quitSafely()`**，除非你确定不关心任何未处理的消息。

---

## 3. loop() 核心循环

### 3.1 为什么 loop() 是整个消息机制的心脏

如果把 Android 的消息机制比作一台发动机，那 `Looper.loop()` 就是曲轴——它驱动每一条消息从队列中取出、分发、回收。**App 进程从启动到退出，主线程几乎所有的时间都花在 loop() 这个方法里。**

你在 ANR trace、Systrace、Profiler 中看到的每一个主线程调用栈，上溯到顶层一定是 `Looper.loop()` → `MessageQueue.next()` → `Handler.dispatchMessage()`。理解 loop() 的每一行代码，就是理解主线程的"呼吸节律"。

### 3.2 源码走读

```java
// frameworks/base/core/java/android/os/Looper.java（核心循环，简化保留关键逻辑）
public static void loop() {
    final Looper me = myLooper();
    if (me == null) {
        throw new RuntimeException("No Looper; Looper.prepare() wasn't called on this thread.");
    }

    final MessageQueue queue = me.mQueue;
    // 确保当前线程的 identity 是本进程的（Binder 相关）
    Binder.clearCallingIdentity();
    final long ident = Binder.clearCallingIdentity();

    // 慢消息阈值
    final int thresholdOverride =
            SystemProperties.getInt("log.looper."
                    + Process.myUid() + "."
                    + Thread.currentThread().getName()
                    + ".slow", 0);

    me.mSlowDeliveryDetected = false;

    for (;;) {
        // ===== 第一步：取消息（可能阻塞） =====
        Message msg = queue.next(); // 可能阻塞在 nativePollOnce
        if (msg == null) {
            // queue.next() 返回 null 意味着 MessageQueue 正在退出
            return;
        }

        // ===== 第二步：打印分发开始（Printer 回调） =====
        final Printer logging = me.mLogging;
        if (logging != null) {
            logging.println(">>>>> Dispatching to " + msg.target + " "
                    + msg.callback + ": " + msg.what);
        }

        // ===== 第三步：Observer 通知开始 =====
        final Observer observer = sObserver;
        Object token = null;
        if (observer != null) {
            token = observer.messageDispatchStarting();
        }

        // ===== 第四步：记录开始时间 =====
        final long dispatchStart = SystemClock.uptimeMillis();
        final long dispatchEnd;

        try {
            // ===== 第五步：分发消息（核心！）=====
            msg.target.dispatchMessage(msg);
            dispatchEnd = SystemClock.uptimeMillis();

            // ===== 第六步：Observer 通知结束 =====
            if (observer != null) {
                observer.messageDispatched(token, msg);
            }
        } catch (Exception exception) {
            // ===== 异常处理：Observer 通知异常 =====
            if (observer != null) {
                observer.dispatchingThrewException(token, msg, exception);
            }
            throw exception;
        }

        // ===== 第七步：慢消息检测 =====
        final long slowDispatchThresholdMs = me.mSlowDispatchThresholdMs;
        final long slowDeliveryThresholdMs = me.mSlowDeliveryThresholdMs;
        if (slowDispatchThresholdMs > 0) {
            final long time = dispatchEnd - dispatchStart;
            if (time > slowDispatchThresholdMs) {
                Slog.w(TAG, "Drained");
            }
        }

        // ===== 第八步：打印分发结束（Printer 回调） =====
        if (logging != null) {
            logging.println("<<<<< Finished to " + msg.target + " "
                    + msg.callback);
        }

        // ===== 第九步：检查 Binder identity 是否被篡改 =====
        final long newIdent = Binder.clearCallingIdentity();
        if (ident != newIdent) {
            Log.wtf(TAG, "Thread identity changed from 0x"
                    + Long.toHexString(ident) + " to 0x"
                    + Long.toHexString(newIdent)
                    + " while dispatching to " + msg.target.getClass().getName());
        }

        // ===== 第十步：回收消息 =====
        msg.recycleUnchecked();
    }
}
```

### 3.3 loop() 的十步执行流

将上面的源码提炼成流程：

```
┌─────────────────────────────────────────────────────────┐
│                    Looper.loop()                         │
│                                                         │
│  for (;;) {                                             │
│      ① queue.next()          ← 取消息（可能阻塞 epoll） │
│          ↓ (msg == null → return，Looper 退出)          │
│      ② logging.println(">>>>>")  ← Printer 开始回调    │
│      ③ observer.messageDispatchStarting() ← Observer   │
│      ④ 记录 dispatchStart                               │
│      ⑤ msg.target.dispatchMessage(msg)  ← 核心分发     │
│      ⑥ observer.messageDispatched()     ← Observer     │
│      ⑦ 慢消息检测（slowDispatch / slowDelivery）        │
│      ⑧ logging.println("<<<<<")  ← Printer 结束回调    │
│      ⑨ 检查 Binder identity                             │
│      ⑩ msg.recycleUnchecked()   ← 回收到对象池          │
│  }                                                      │
└─────────────────────────────────────────────────────────┘
```

### 3.4 slowDeliveryThresholdMs 与 slowDispatchThresholdMs

loop() 内部有两个慢消息检测维度：

| 指标 | 含义 | 计算方式 |
| :--- | :--- | :--- |
| **slowDelivery** | 消息从 `enqueue` 到**开始执行**的等待时间超标 | `dispatchStart - msg.when` |
| **slowDispatch** | 消息**执行本身**的耗时超标 | `dispatchEnd - dispatchStart` |

```
消息生命周期时间线：

    msg.when        dispatchStart        dispatchEnd
       │                  │                    │
       ▼                  ▼                    ▼
  ─────┬──────────────────┬────────────────────┬─────→ time
       │   delivery time  │   dispatch time    │
       │   (排队等待)      │   (执行耗时)        │
       │                  │                    │
       │← slowDelivery →│← slowDispatch  →│
```

**稳定性关联：** 这两个指标的区分至关重要——

- **slowDelivery 高但 slowDispatch 低**：说明消息队列拥堵，前面的消息处理太慢，导致后面的消息排队等待。根因不在这条消息本身，而在前面的消息。
- **slowDispatch 高**：说明这条消息自身的处理逻辑耗时长，它自己就是卡顿的元凶。

系统可以通过设置 `SystemProperties` 来开启慢消息日志：

```bash
# 开启主线程慢消息日志（阈值 100ms）
adb shell setprop log.looper.1000.main.slow 100
```

### 3.5 Printer 回调 — 最简单的卡顿监控入口

```java
// frameworks/base/core/java/android/os/Looper.java
public void setMessageLogging(@Nullable Printer printer) {
    mLogging = printer;
}
```

loop() 在每条消息分发前后分别调用 `Printer.println()`，输出格式为：

```
>>>>> Dispatching to Handler (android.app.ActivityThread$H) {7e5a37e} android.app.ActivityThread$H@7e5a37e: 159
<<<<< Finished to Handler (android.app.ActivityThread$H) {7e5a37e} android.app.ActivityThread$H@7e5a37e
```

著名的 **BlockCanary** 就是利用这个机制：解析 `>>>>>` 和 `<<<<<` 之间的时间差，如果超过阈值就 dump 主线程调用栈。这是**最低侵入性的卡顿监控方案**，不需要任何 hook，只用一个公开 API。

但它有两个局限：
1. **精度受限**：Printer 的开始/结束只记录字符串，需要解析字符串提取时间，且 Printer 回调本身有开销。
2. **无法获取消息对象**：你知道耗时了，但不知道是哪个 Message、what 值是什么。这个问题在 Android P+ 被 Observer 解决。

---

## 4. 主线程 vs 工作线程 Looper

### 4.1 为什么要区分

并不是所有 Looper 都一样。主线程 Looper 和工作线程 Looper 在创建方式、生命周期、退出策略上都有本质差异。混淆这两者会导致严重的稳定性问题。

| 维度 | 主线程 Looper | 工作线程 Looper |
| :--- | :--- | :--- |
| 创建方式 | `Looper.prepareMainLooper()` | `Looper.prepare()` |
| 能否 quit | 不能（抛 `IllegalStateException`） | 能 |
| 谁来调用 loop() | 系统（`ActivityThread.main()`） | 开发者自己 |
| 生命周期 | 与进程同生共死 | 需要手动管理 |
| 典型代表 | 主线程 | HandlerThread |

### 4.2 主线程 Looper 不能 quit 的原因

```java
// frameworks/base/core/java/android/os/MessageQueue.java
void quit(boolean safe) {
    if (!mQuitAllowed) {
        throw new IllegalStateException("Main thread not allowed to quit.");
    }
    // ...
}
```

主线程 Looper 在 `prepareMainLooper()` 中以 `quitAllowed = false` 创建。如果主线程 Looper 退出了，`loop()` 方法返回，`ActivityThread.main()` 会抛出 `RuntimeException("Main thread loop unexpectedly exited")`，进程崩溃。

**主线程 Looper 退出 = 进程死亡。** 这不是可选的。

### 4.3 HandlerThread — 工作线程 Looper 的标准封装

如果你需要一个带有消息循环的后台线程，Android 提供了 `HandlerThread`。

* **源码路径：** `frameworks/base/core/java/android/os/HandlerThread.java`

```java
// frameworks/base/core/java/android/os/HandlerThread.java（简化）
public class HandlerThread extends Thread {
    Looper mLooper;
    private @Nullable Handler mHandler;
    int mPriority;

    public HandlerThread(String name, int priority) {
        super(name);
        mPriority = priority;
    }

    @Override
    public void run() {
        mTid = Process.myTid();
        Looper.prepare();
        synchronized (this) {
            mLooper = Looper.myLooper();
            notifyAll(); // 通知 getLooper() 的等待者
        }
        Process.setThreadPriority(mPriority);
        onLooperPrepared(); // 回调钩子
        Looper.loop(); // 进入循环，直到 quit 被调用
        mTid = -1;
    }

    public Looper getLooper() {
        if (!isAlive()) {
            return null;
        }
        synchronized (this) {
            while (isAlive() && mLooper == null) {
                try {
                    wait(); // 等待 run() 中 Looper 创建完成
                } catch (InterruptedException e) {
                }
            }
        }
        return mLooper;
    }

    public boolean quit() {
        Looper looper = getLooper();
        if (looper != null) {
            looper.quit();
            return true;
        }
        return false;
    }

    public boolean quitSafely() {
        Looper looper = getLooper();
        if (looper != null) {
            looper.quitSafely();
            return true;
        }
        return false;
    }
}
```

**关键设计点：**

1. **`getLooper()` 中的 `wait()`**：HandlerThread 的 `run()` 在新线程中执行，而 `getLooper()` 通常在创建线程中调用。由于 Looper 在 `run()` 中创建，存在竞态——`getLooper()` 可能在 Looper 创建前被调用。`wait() / notifyAll()` 解决了这个同步问题。
2. **`onLooperPrepared()` 回调**：在 Looper 准备好、loop() 启动前调用，子类可以在这里做初始化工作。

### 4.4 HandlerThread 的典型使用模式

```java
// 创建并启动
HandlerThread handlerThread = new HandlerThread("worker-thread");
handlerThread.start();

// 基于它的 Looper 创建 Handler
Handler workerHandler = new Handler(handlerThread.getLooper());

// 发送任务到工作线程
workerHandler.post(() -> {
    // 这段代码在 worker-thread 中执行
    performHeavyWork();
});

// 生命周期结束时必须退出
handlerThread.quitSafely();
```

### 4.5 IntentService — 基于 HandlerThread 的一次性服务

* **源码路径：** `frameworks/base/core/java/android/app/IntentService.java`

```java
// frameworks/base/core/java/android/app/IntentService.java（简化）
public abstract class IntentService extends Service {
    private volatile Looper mServiceLooper;
    private volatile ServiceHandler mServiceHandler;

    private final class ServiceHandler extends Handler {
        public ServiceHandler(Looper looper) {
            super(looper);
        }

        @Override
        public void handleMessage(Message msg) {
            onHandleIntent((Intent) msg.obj);
            stopSelf(msg.arg1); // 处理完自动停止
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        HandlerThread thread = new HandlerThread("IntentService[" + mName + "]");
        thread.start();
        mServiceLooper = thread.getLooper();
        mServiceHandler = new ServiceHandler(mServiceLooper);
    }

    @Override
    public void onDestroy() {
        mServiceLooper.quit();
    }
}
```

IntentService 的核心思路：`onCreate()` 时启动一个 HandlerThread，每次 `onStartCommand()` 将 Intent 封装为 Message 发送到工作线程处理，处理完毕后 `stopSelf()`。`onDestroy()` 时退出 Looper。

**稳定性关联：HandlerThread 忘记 quit 是一个经典的资源泄漏问题。** 每个 HandlerThread 占用一个 Linux 线程和一个 epoll fd。如果你创建了 HandlerThread 但没有在适当的生命周期中调用 `quit()` 或 `quitSafely()`，这个线程会一直阻塞在 `epoll_wait` 中，直到进程被杀死。在长时间运行的 App 中，这会逐渐耗尽线程数和 fd 数量。

```
HandlerThread 泄漏的资源占用：

每个未退出的 HandlerThread 占用：
    ├── 1 个 Linux 线程（默认栈大小 1MB）
    ├── 1 个 epoll fd
    ├── 1 个 eventfd
    ├── 1 个 Looper 对象
    └── 1 个 MessageQueue 对象

假设 App 中有一个页面每次打开都创建 HandlerThread 但不 quit：
    打开 10 次 → 10 个线程泄漏 → 10MB 栈内存 + 20 个 fd
    打开 100 次 → 100 个线程泄漏 → 100MB 栈内存 + 200 个 fd
    → 最终触发 /proc/sys/kernel/threads-max 限制或 fd 耗尽
```

---

## 5. Looper.Observer — 系统级消息监控钩子

### 5.1 为什么需要 Observer

在第 3 节中我们看到，`Looper.loop()` 在每条消息分发前后会调用 Printer 回调。Printer 方案虽然简单，但有几个痛点：

1. **只能拿到字符串**：Printer 回调传入的是格式化后的字符串，需要解析才能提取信息。
2. **无法拿到 Message 对象**：你不知道当前消息的 `what`、`target`、`callback` 是什么。
3. **无法捕获异常**：如果消息处理过程中抛异常，Printer 的结束回调不会被触发。
4. **性能开销**：字符串拼接和 `println()` 调用在高频消息场景下有可观的 GC 压力。

Android P（API 28）引入了 `Looper.Observer` 接口来解决这些问题。

### 5.2 Observer 接口定义

```java
// frameworks/base/core/java/android/os/Looper.java
/** @hide */
public interface Observer {
    /**
     * 消息开始分发时调用。
     * @return 一个 token，后续 messageDispatched / dispatchingThrewException 会带上这个 token
     */
    Object messageDispatchStarting();

    /**
     * 消息正常分发完成时调用。
     * @param token messageDispatchStarting 返回的 token
     * @param msg 被分发的 Message 对象
     */
    void messageDispatched(Object token, Message msg);

    /**
     * 消息分发过程中抛出异常时调用。
     * @param token messageDispatchStarting 返回的 token
     * @param msg 被分发的 Message 对象
     * @param exception 抛出的异常
     */
    void dispatchingThrewException(Object token, Message msg, Exception exception);
}
```

### 5.3 Observer 在 loop() 中的调用时机

回顾 loop() 的源码，Observer 的三个回调在以下位置触发：

```
for (;;) {
    Message msg = queue.next();

    // ① messageDispatchStarting() ← 分发前
    Object token = observer.messageDispatchStarting();

    try {
        msg.target.dispatchMessage(msg);

        // ② messageDispatched(token, msg) ← 分发后（正常完成）
        observer.messageDispatched(token, msg);

    } catch (Exception exception) {
        // ③ dispatchingThrewException(token, msg, exception) ← 分发异常
        observer.dispatchingThrewException(token, msg, exception);
        throw exception;
    }
}
```

### 5.4 Observer 相比 Printer 的优势

| 维度 | Printer | Observer |
| :--- | :--- | :--- |
| 获取 Message 对象 | 不能（只有字符串） | 能（`messageDispatched` 参数） |
| 异常捕获 | 不能 | 能（`dispatchingThrewException`） |
| 性能 | 字符串拼接开销 | 无字符串开销 |
| token 机制 | 无 | 有（可以关联开始和结束） |
| API 访问性 | 公开 API | `@hide`（需要反射或系统权限） |

### 5.5 系统内部如何使用 Observer

Android 系统内部使用 Observer 来实现 **LooperStats**（消息统计）：

```java
// frameworks/base/core/java/com/android/internal/os/LooperStats.java（简化）
public class LooperStats implements Looper.Observer {
    @Override
    public Object messageDispatchStarting() {
        // 记录开始时间和线程 CPU 时间
        Entry entry = new Entry();
        entry.startTime = SystemClock.uptimeMillis();
        entry.startCpuTime = getThreadCpuTimeMillis();
        return entry;
    }

    @Override
    public void messageDispatched(Object token, Message msg) {
        Entry entry = (Entry) token;
        long dispatchTime = SystemClock.uptimeMillis() - entry.startTime;
        long cpuTime = getThreadCpuTimeMillis() - entry.startCpuTime;

        // 按 Handler 类名 + what 值聚合统计
        String key = msg.target.getClass().getName() + "#" + msg.what;
        aggregate(key, dispatchTime, cpuTime);
    }

    @Override
    public void dispatchingThrewException(Object token, Message msg, Exception exception) {
        // 记录异常消息
        Entry entry = (Entry) token;
        recordException(msg, exception);
    }
}
```

LooperStats 通过 `dumpsys looper_stats` 可以查看统计结果：

```bash
adb shell dumpsys looper_stats
```

输出示例：

```
Handler class                          what    count   total_time  avg_time  max_time
android.app.ActivityThread$H           159     1234    45678ms     37ms      1200ms
android.view.Choreographer$FrameHandler 0      60000   120000ms    2ms       32ms
android.os.AsyncTask$InternalHandler   1       500     25000ms     50ms      800ms
```

**稳定性关联：** Observer 是系统级卡顿监控的核心入口。虽然它是 `@hide` API，但许多 APM 框架（如微信 Matrix、字节 Sliver）通过反射设置自定义 Observer 来实现精确的消息耗时监控。相比 Printer 方案，Observer 能提供更丰富的信息（Message 对象、异常捕获）和更低的性能开销。

### 5.6 使用 Observer 的注意事项

1. **`@hide` API 的风险**：Observer 不是公开 API，不同 Android 版本的接口可能变化。使用反射设置时需要做好版本兼容和降级。
2. **Observer 是全局唯一的**：`Looper.sObserver` 是一个静态变量，设置新的 Observer 会覆盖旧的。如果系统已经设置了 LooperStats，你的自定义 Observer 会把它覆盖掉。
3. **Observer 回调运行在消息循环线程**：回调中执行耗时操作会影响消息分发本身，形成"观测影响实验"的问题。回调实现必须极轻量。

---

## 6. 稳定性案例

### 案例一：HandlerThread 泄漏导致 FD 耗尽，触发大面积 Crash

**背景：** 某电商 App 线上出现大量 `Too many open files` Crash，Crash 率在特定版本突增了 5 倍。

**现象：**

```
java.io.IOException: Too many open files
    at android.os.MessageQueue.nativeInit(Native Method)
    at android.os.MessageQueue.<init>(MessageQueue.java:75)
    at android.os.Looper.<init>(Looper.java:195)
    at android.os.Looper.prepare(Looper.java:82)
    at android.os.HandlerThread.run(HandlerThread.java:67)
```

Crash 堆栈显示：新建 `HandlerThread` 时，`MessageQueue.nativeInit()` 创建 epoll fd 失败，因为进程的 fd 数量已经达到上限（通常是 1024）。

**排查过程：**

1. **复现路径**：反复打开/关闭 App 中的"直播间"页面 50 次后必现。
2. **fd 监控**：在 debug 模式下通过 `/proc/self/fd` 统计 fd 数量，发现每次打开直播间页面，fd 数量增加 2（一个 epoll fd + 一个 eventfd），关闭页面后不释放。
3. **线程监控**：打印 `Thread.getAllStackTraces()` 发现大量名为 `DanmakuThread` 的线程阻塞在 `nativePollOnce`。

**根因：** 直播间页面的弹幕模块在 `onResume()` 中创建了一个 `HandlerThread("DanmakuThread")` 用于处理弹幕消息，但在 `onPause()` / `onDestroy()` 中没有调用 `quitSafely()`。每次页面重建都会创建新的 HandlerThread，旧的线程永远阻塞在 `epoll_wait`，线程和 fd 只增不减。

```java
// 问题代码
public class DanmakuManager {
    private HandlerThread mThread;
    private Handler mHandler;

    public void start() {
        mThread = new HandlerThread("DanmakuThread");
        mThread.start();
        mHandler = new Handler(mThread.getLooper());
    }

    // 没有 stop() 方法！没有调用 quitSafely()！
}
```

**修复：**

```java
public class DanmakuManager {
    private HandlerThread mThread;
    private Handler mHandler;

    public void start() {
        stop(); // 先清理旧的
        mThread = new HandlerThread("DanmakuThread");
        mThread.start();
        mHandler = new Handler(mThread.getLooper());
    }

    public void stop() {
        if (mThread != null) {
            mThread.quitSafely();
            mThread = null;
        }
        mHandler = null;
    }
}

// 在 Activity/Fragment 中：
@Override
protected void onDestroy() {
    super.onDestroy();
    danmakuManager.stop();
}
```

**治理措施：**

1. **线程泄漏监控**：在 debug 模式下定期扫描所有线程，对同名线程数量 > 1 的发出告警。
2. **fd 监控**：APM 定时读取 `/proc/self/fd` 下的文件数量，超过阈值（如 800）上报预警。
3. **Code Review 规范**：所有 `HandlerThread` 必须有配对的 `quitSafely()` 调用，在页面或组件的 `onDestroy()` 中执行。

**经验总结：** HandlerThread 的创建和销毁必须成对出现。任何"创建但不销毁"的 HandlerThread 都是一颗定时炸弹。在 fd 数量到达上限之前，你看不到任何异常——直到某一刻突然雪崩。

---

### 案例二：主线程 Looper Printer 回调引发 GC 风暴，导致全局卡顿

**背景：** 某社交 App 上线了自研的卡顿监控 SDK，使用 `Looper.setMessageLogging(Printer)` 方案（类似 BlockCanary）。上线后，用户反馈列表滑动明显变卡。

**现象：**

- Systrace 显示主线程出现大量 GC 事件（`GC_FOR_ALLOC`）。
- GC 之间间隔非常短（约 2-5ms），说明短时间内产生了大量临时对象。
- Perfetto 的 heap 分析显示大量 `StringBuilder` 和 `String` 对象被分配。

**排查过程：**

1. 将问题版本与上一版本对比，唯一的差异是卡顿监控 SDK 的引入。
2. 关闭 SDK 后卡顿消失，确认 SDK 是根因。
3. 分析 SDK 代码，发现 `Printer.println()` 的实现中做了字符串解析和正则匹配。

**根因：** `Looper.loop()` 在每条消息分发前后各调用一次 `Printer.println()`。在系统内部，loop() 的实现会先拼接字符串再传递给 Printer：

```java
// loop() 内部（这段代码每条消息执行两次）
logging.println(">>>>> Dispatching to " + msg.target + " "
        + msg.callback + ": " + msg.what);
```

这行代码涉及：
- `msg.target.toString()`：Handler 的 toString 会创建新字符串
- `msg.callback.toString()`：Runnable 的 toString
- 字符串拼接：编译器生成 `StringBuilder.append()` 链
- 最终的 `String` 对象

主线程每秒处理数百条消息（尤其是触摸事件、Choreographer VSync 回调等），每条消息两次 Printer 回调，每次回调产生多个临时字符串对象。**在高帧率场景（120Hz 设备），每秒最多产生 240 次字符串拼接**，加上 SDK 内部的正则解析，GC 压力剧增。

```
消息频率估算：

VSync 回调：        120 次/秒（120Hz 设备）
Input 事件：         60-120 次/秒（快速滑动）
其他系统消息：       ~50 次/秒
─────────────────────────────
合计：              ~300 次/秒

每条消息 2 次 Printer 回调 → 600 次/秒的字符串拼接
每次拼接约产生 3 个临时对象 → 1800 个临时对象/秒
→ 触发频繁 Minor GC → 每次 GC 暂停 2-5ms → 帧率下降
```

**修复方案：**

1. **短期**：将 Printer 方案替换为 Observer 方案（Android P+），避免字符串拼接开销。
2. **兼容方案**（P 以下版本）：在 Printer 回调中只记录时间戳，不解析字符串。仅当时间差超过阈值时才进行解析和 dump：

```java
public class LowOverheadPrinter implements Printer {
    private long mStartTime;
    private static final long THRESHOLD = 100; // ms

    @Override
    public void println(String x) {
        if (x.charAt(0) == '>') {
            mStartTime = SystemClock.uptimeMillis();
        } else {
            long cost = SystemClock.uptimeMillis() - mStartTime;
            if (cost > THRESHOLD) {
                // 只在超过阈值时才做耗时操作
                reportSlowMessage(x, cost);
            }
        }
    }
}
```

3. **长期**：在线上通过采样控制（如 10% 用户开启）降低全量开启的风险。

**经验总结：** 监控代码本身也会影响被监控系统的行为——这在物理学中叫"观察者效应"。在消息循环这样的高频热路径上插入监控逻辑时，必须极度关注性能开销。Printer 方案的字符串拼接开销在低端设备和高帧率场景下可能成为性能瓶颈。**好的监控方案应该在"不影响性能"和"获取足够信息"之间找到平衡。**

---

## 小结

本篇从 `ActivityThread.main()` 出发，逐层拆解了 Looper 的完整机制：

| 主题 | 核心要点 | 稳定性关联 |
| :--- | :--- | :--- |
| **ActivityThread.main()** | prepareMainLooper → attach → loop()，永不返回 | main() 是所有生命周期的调度起点 |
| **Looper 绑定** | ThreadLocal 实现一线程一 Looper | 违反约束直接 crash |
| **prepare / quit** | prepare 创建 Looper+MQ；quit vs quitSafely 的丢弃策略差异 | quitSafely 保护已到期消息 |
| **loop() 十步流** | next → Printer → Observer → dispatch → 慢检测 → recycle | 所有主线程行为都在这个循环中 |
| **慢消息检测** | slowDelivery（排队等待） vs slowDispatch（执行耗时） | 区分"拥堵"和"自身慢" |
| **HandlerThread** | 封装 prepare+loop，getLooper 有 wait 同步 | 不 quit → 线程和 fd 泄漏 |
| **Observer** | Android P+ 的 @hide API，提供 Message 级监控能力 | 系统级卡顿监控的核心入口 |

下一篇我们将深入 `MessageQueue` 的内部实现，从 Java 层的消息链表管理，到 Native 层的 epoll 驱动机制——理解消息循环的"阻塞与唤醒"是如何工作的。
