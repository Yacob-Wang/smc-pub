# 04-Message 生命周期：创建、分发、回收与对象池

上一篇我们从 `MessageQueue.next()` 一路下探到 `epoll_wait`，拆解了消息队列的双层架构和阻塞唤醒机制。但我们始终在围绕"队列"本身打转——是时候把目光聚焦到队列里**流动的东西**了：`Message`。

一条 Message 的一生可以用一句话概括：

```
obtain() 从对象池获取
    → 设置 what/arg1/obj/callback 等字段
        → sendMessage / post 发送
            → enqueueMessage 按时间插入队列
                → dispatchMessage 三级分发
                    → recycleUnchecked 清空字段、回归对象池
```

这条链路看似简单，但每个环节都藏着稳定性风险：不用 `obtain()` 而是 `new Message()` 会在高频场景下引发 GC 卡顿；`enqueueMessage` 中的排序逻辑决定了消息的优先级和唤醒时机；`dispatchMessage` 的三级分发优先级如果不清楚，会在拦截器模式中踩坑；`recycleUnchecked` 之后如果仍然持有 Message 引用，会读到被清空或被另一条消息复用的脏数据。

本篇将逐一拆解这些环节，带你看清 Message 从生到死的每一步。

---

## 1. Message 数据结构

### 1.1 为什么需要理解 Message 的每个字段

对于稳定性架构师来说，Message 不是一个"用就行了"的数据载体。**你在 ANR trace 中看到的 `msg.what=159`、在内存泄漏报告中看到的 `msg.obj` 持有 Activity 引用、在卡顿分析中看到的 `msg.when` 与 `dispatchStart` 的时间差——这些都需要你理解 Message 的字段语义才能正确解读。**

### 1.2 字段全景

> Source: `frameworks/base/core/java/android/os/Message.java`

```java
public final class Message implements Parcelable {
    // ===== 业务数据字段 =====
    public int what;           // 消息类型标识（由使用者定义）
    public int arg1;           // 轻量级 int 参数 1
    public int arg2;           // 轻量级 int 参数 2
    public Object obj;         // 任意对象载荷

    // ===== 跨进程通信字段 =====
    public Messenger replyTo;  // 用于跨进程回复的 Messenger
    public int sendingUid = UID_NONE; // 发送者 UID

    // ===== Bundle 数据 =====
    Bundle data;               // 重量级数据容器（懒初始化）

    // ===== 调度字段 =====
    /*package*/ Handler target;     // 目标 Handler（负责分发和处理）
    /*package*/ Runnable callback;  // post(Runnable) 时的 Runnable
    /*package*/ long when;          // 预期执行时间（uptimeMillis）

    // ===== 标志位 =====
    /*package*/ int flags;
    static final int FLAG_IN_USE = 1 << 0;       // 正在使用中
    static final int FLAG_ASYNCHRONOUS = 1 << 1;  // 异步消息

    // ===== 链表指针 =====
    /*package*/ Message next;  // 指向链表中的下一条消息
}
```

### 1.3 字段逐一解析

| 字段 | 类型 | 含义 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| `what` | int | 消息类型标识，由 Handler 使用者定义 | ANR trace 中的 `what=159` 对应 `EXECUTE_TRANSACTION`（Activity 生命周期） |
| `arg1` / `arg2` | int | 轻量级 int 参数，避免使用 Bundle 的开销 | 优先使用 arg1/arg2 替代 Bundle 传递简单数据 |
| `obj` | Object | 任意对象载荷 | **内存泄漏高危字段**：如果 obj 持有 Activity 引用，延迟消息会阻止 Activity 被 GC |
| `data` | Bundle | 重量级数据容器，懒初始化 | Bundle 的序列化/反序列化有开销，不要滥用 |
| `target` | Handler | 目标 Handler，消息最终由它分发和处理 | target 持有 Handler → Handler 可能持有 Activity → 形成引用链 |
| `callback` | Runnable | `post(Runnable)` 时传入的 Runnable | 匿名 Runnable 隐式持有外部类引用 → 内存泄漏 |
| `when` | long | 消息预期执行时间（`SystemClock.uptimeMillis()` 基准） | `dispatchStart - when` = 消息排队等待时间，是 slowDelivery 的衡量指标 |
| `flags` | int | 标志位组合 | `FLAG_IN_USE` 防止重复回收；`FLAG_ASYNCHRONOUS` 标记异步消息（不被同步屏障拦截） |
| `next` | Message | 单链表指针，指向下一条消息 | MessageQueue 和对象池都通过 next 串成链表 |

### 1.4 flags 详解

**FLAG_IN_USE（1 << 0）：** 标记消息正在使用中。`markInUse()` 在 `MessageQueue.next()` 取出消息时调用，`recycleUnchecked()` 回收时检查并重置。作用是防止一条正在被处理的消息被意外回收——如果你手动调用 `msg.recycle()` 但消息还在队列中，`FLAG_IN_USE` 检查会抛出 `IllegalStateException`。

**FLAG_ASYNCHRONOUS（1 << 1）：** 标记为异步消息。当 MessageQueue 中存在同步屏障（`target == null` 的 Message）时，`next()` 会跳过所有同步消息，只取异步消息。Choreographer 的渲染回调就是通过异步消息实现优先调度的。

### 1.5 next 指针形成单链表

`next` 字段在两个场景中被使用：

```
场景 1：MessageQueue 的消息链表（按 when 升序排列）

mMessages → [msg_A, when=100] → [msg_B, when=200] → [msg_C, when=350] → null
              next ─────────►      next ─────────►      next ──► null

场景 2：对象池 sPool（后进先出栈）

sPool → [recycled_1] → [recycled_2] → [recycled_3] → null
          next ──────►    next ──────►    next ──► null
```

同一个 `next` 字段，在消息队列中承载调度顺序，在对象池中承载缓存链路。这是 Android 用最小开销复用数据结构的典型设计。

**稳定性关联：** 消息在队列中时 `next` 指向下一条消息；回收到对象池后 `next` 指向池中下一个缓存对象。如果出现 bug 导致一条消息同时存在于队列和对象池中（理论上 `FLAG_IN_USE` 防止了这种情况），会导致链表环路——`next()` 方法陷入死循环，主线程永久卡死。

---

## 2. 对象池机制

### 2.1 为什么需要对象池

Android 的主线程每秒处理数百条消息（VSync 回调、Input 事件、Handler.post 任务等）。如果每条消息都 `new Message()`，使用完就等 GC 回收，会带来两个问题：

1. **GC 压力**：高频分配和回收短生命周期对象，触发频繁的 Minor GC。每次 GC 都有暂停时间（即使是并发 GC，也有部分 STW 阶段），叠加起来导致卡顿。
2. **内存碎片**：大量小对象的分配和释放导致堆内存碎片化，降低分配效率。

对象池的思路是：**用完的 Message 不要扔，清空字段后放回池中。下次需要 Message 时直接从池里取，避免 new 操作。** 这在高频场景下能显著降低 GC 压力。

### 2.2 对象池的数据结构

> Source: `frameworks/base/core/java/android/os/Message.java`

```java
public final class Message implements Parcelable {
    // 对象池的头指针（全局静态，所有线程共享）
    private static Message sPool;

    // 当前池中缓存的 Message 数量
    private static int sPoolSize = 0;

    // 池的最大容量
    private static final int MAX_POOL_SIZE = 50;

    // 保护对象池的锁
    private static final Object sPoolSync = new Object();
}
```

对象池是一个**全局静态单链表**，通过 `next` 指针串联。`sPool` 指向链表头，`sPoolSize` 记录当前缓存数量，`MAX_POOL_SIZE = 50` 限制最大缓存数。所有线程共享同一个池，通过 `synchronized(sPoolSync)` 保护并发访问。

```
sPool → [msg_1] → [msg_2] → ... → [msg_50] → null
          next      next              next
         
sPoolSize = 50（已满，后续回收的 Message 不再入池）
```

### 2.3 obtain() — 从池中获取

```java
// frameworks/base/core/java/android/os/Message.java
public static Message obtain() {
    synchronized (sPoolSync) {
        if (sPool != null) {
            Message m = sPool;        // 取池头
            sPool = m.next;           // 头指针后移
            m.next = null;            // 断开链接
            m.flags = 0;              // 清除 FLAG_IN_USE
            sPoolSize--;
            return m;
        }
    }
    return new Message();  // 池空则 new
}
```

**执行流程：**

```
调用 obtain()
    │
    ├── sPool != null（池中有缓存）
    │     ├── 取出 sPool 指向的 Message
    │     ├── sPool 指向 next（池头后移）
    │     ├── 清空 next 和 flags
    │     ├── sPoolSize--
    │     └── 返回复用的 Message
    │
    └── sPool == null（池空）
          └── return new Message()
```

`obtain()` 还有多个重载版本，方便一步到位设置字段：

```java
public static Message obtain(Handler h) {
    Message m = obtain();
    m.target = h;
    return m;
}

public static Message obtain(Handler h, int what) {
    Message m = obtain();
    m.target = h;
    m.what = what;
    return m;
}

public static Message obtain(Handler h, Runnable callback) {
    Message m = obtain();
    m.target = h;
    m.callback = callback;
    return m;
}
// ... 更多重载
```

### 2.4 recycleUnchecked() — 回收到池中

```java
// frameworks/base/core/java/android/os/Message.java
void recycleUnchecked() {
    // 清空所有字段，标记为 FLAG_IN_USE（表示"在对象池中"）
    flags = FLAG_IN_USE;
    what = 0;
    arg1 = 0;
    arg2 = 0;
    obj = null;
    replyTo = null;
    sendingUid = UID_NONE;
    workSourceUid = UID_NONE;
    when = 0;
    target = null;
    callback = null;
    data = null;

    synchronized (sPoolSync) {
        if (sPoolSize < MAX_POOL_SIZE) {
            next = sPool;      // 当前 Message 的 next 指向原池头
            sPool = this;      // 自己成为新池头
            sPoolSize++;
        }
    }
}
```

**关键设计点：**

1. **清空所有字段**：回收时将 `target`、`callback`、`obj`、`data` 全部置 null。这是为了**打断引用链**——如果不清空 `obj`，对象池中的 Message 会一直持有 `obj` 的引用，阻止其被 GC 回收。

2. **`flags = FLAG_IN_USE`**：注意回收时将 flags 设为 `FLAG_IN_USE` 而不是 0。这看起来反直觉——"回收了还标记为 in use？"。实际上，这里的 `FLAG_IN_USE` 含义是"这个 Message 在对象池中，不应该被再次回收"。如果有代码在 Message 被回收后仍然调用 `msg.recycle()`，`isInUse()` 检查会阻止重复回收：

```java
public void recycle() {
    if (isInUse()) {
        // Android P+ 直接检查 FLAG_IN_USE
        // 如果已经在池中，抛异常或忽略
        if (gCheckRecycle) {
            throw new IllegalStateException(
                    "This message cannot be recycled because it is still in use.");
        }
        return;
    }
    recycleUnchecked();
}
```

3. **MAX_POOL_SIZE = 50**：池满后，多余的 Message 不再入池，直接被 GC 回收。50 是一个经验值——覆盖大多数正常场景的消息缓存需求，同时避免对象池本身占用过多内存。

### 2.5 为什么必须用 obtain() 而非 new

在日常编码中，`new Message()` 和 `Message.obtain()` 都能获得一个 Message 对象。但在**高频消息场景**下，差异非常显著：

```
场景：120Hz 设备，主线程每秒处理 ~300 条消息

使用 new Message()：
    300 次 new → 300 个短生命周期对象 → 每 1-2 秒触发一次 Minor GC
    GC 暂停 2-5ms → 每秒可能损失 2-5ms → 掉帧

使用 Message.obtain()：
    300 次 obtain → 大部分从池中复用（池大小 50，循环复用）
    极少触发 new → GC 压力大幅降低 → 流畅
```

**稳定性关联：** 在 APM 监控中，如果发现主线程频繁出现 `GC_FOR_ALLOC` 事件，且分配热点是 `Message` 对象，很可能是某个模块大量使用 `new Message()` 而非 `obtain()`。这种问题在低端设备上尤为明显——内存小、GC 阈值低、GC 暂停时间长。

---

## 3. 消息发送的多种方式

### 3.1 为什么有这么多发送方法

Handler 提供了多种发送消息的方法，看起来令人眼花缭乱。但理解它们的层次关系后就会发现：**所有方式最终汇聚到同一个入口——`sendMessageAtTime()`。** 不同方法只是语法糖，封装了不同的默认参数。

### 3.2 发送方法全景

> Source: `frameworks/base/core/java/android/os/Handler.java`

```java
// ===== sendMessage 系列 =====

public final boolean sendMessage(Message msg) {
    return sendMessageDelayed(msg, 0);
}

public final boolean sendEmptyMessage(int what) {
    return sendEmptyMessageDelayed(what, 0);
}

public final boolean sendEmptyMessageDelayed(int what, long delayMillis) {
    Message msg = Message.obtain();
    msg.what = what;
    return sendMessageDelayed(msg, delayMillis);
}

public final boolean sendMessageDelayed(Message msg, long delayMillis) {
    if (delayMillis < 0) {
        delayMillis = 0;
    }
    return sendMessageAtTime(msg, SystemClock.uptimeMillis() + delayMillis);
}

public boolean sendMessageAtTime(Message msg, long uptimeMillis) {
    MessageQueue queue = mQueue;
    if (queue == null) {
        RuntimeException e = new RuntimeException(
                this + " sendMessageAtTime() called with no mQueue");
        Log.w("Looper", e.getMessage(), e);
        return false;
    }
    return enqueueMessage(queue, msg, uptimeMillis);
}

public final boolean sendMessageAtFrontOfQueue(Message msg) {
    MessageQueue queue = mQueue;
    if (queue == null) {
        RuntimeException e = new RuntimeException(
                this + " sendMessageAtTime() called with no mQueue");
        Log.w("Looper", e.getMessage(), e);
        return false;
    }
    return enqueueMessage(queue, msg, 0);  // when=0 → 插到队列头
}
```

### 3.3 post(Runnable) 系列

```java
// ===== post 系列 =====

public final boolean post(Runnable r) {
    return sendMessageDelayed(getPostMessage(r), 0);
}

public final boolean postDelayed(Runnable r, long delayMillis) {
    return sendMessageDelayed(getPostMessage(r), delayMillis);
}

public final boolean postAtTime(Runnable r, long uptimeMillis) {
    return sendMessageAtTime(getPostMessage(r), uptimeMillis);
}

public final boolean postAtFrontOfQueue(Runnable r) {
    return sendMessageAtFrontOfQueue(getPostMessage(r));
}

// 将 Runnable 包装为 Message
private static Message getPostMessage(Runnable r) {
    Message m = Message.obtain();
    m.callback = r;  // Runnable 存入 Message.callback
    return m;
}
```

`post(Runnable)` 的本质：**通过 `getPostMessage()` 将 Runnable 包装成一个 Message（存入 `callback` 字段），然后走 `sendMessage` 的标准流程。** 这就是为什么 `post(Runnable)` 和 `sendMessage(Message)` 在底层是完全一样的——它们最终都调用 `sendMessageAtTime()`。

### 3.4 调用链汇聚图

```
sendMessage(msg)
    ↓
sendEmptyMessage(what)  →  sendEmptyMessageDelayed(what, 0)
    ↓                           ↓
post(Runnable)  →  getPostMessage(r)  →  sendMessageDelayed(msg, 0)
    ↓                                        ↓
postDelayed(r, delay)  →  getPostMessage(r)  →  sendMessageDelayed(msg, delay)
                                                    ↓
                                              sendMessageAtTime(msg, uptimeMillis)
                                                    ↓
                                              enqueueMessage(queue, msg, when)
                                                    ↓
                                              MessageQueue.enqueueMessage(msg, when)
```

**所有路径最终汇聚到 `sendMessageAtTime()` → `enqueueMessage()`。** 理解这一点后，你在排查消息调度问题时只需要关注这一个入口。

**稳定性关联：** `post(Runnable)` 每次调用都会通过 `Message.obtain()` 获取一个 Message。如果在高频场景（如 `onDraw()` 或 `onScrollChanged()`）中反复调用 `handler.post(runnable)`，会快速消耗对象池，甚至因池满而频繁 `new Message()`。更隐蔽的风险是：匿名 Runnable 隐式持有外部类引用，配合延迟消息可能导致内存泄漏。

---

## 4. enqueueMessage — 入队与唤醒

### 4.1 为什么 enqueueMessage 是关键

`enqueueMessage()` 是消息从"发送"到"进入队列"的转折点。它做了三件关键事情：绑定 Handler、按时间排序插入链表、在必要时唤醒阻塞的线程。每一件事都与稳定性相关。

### 4.2 Handler.enqueueMessage

> Source: `frameworks/base/core/java/android/os/Handler.java`

```java
private boolean enqueueMessage(MessageQueue queue, Message msg, long uptimeMillis) {
    msg.target = this;  // ① 绑定当前 Handler 为消息的目标
    msg.workSourceUid = ThreadLocalWorkSource.getUid();

    if (mAsynchronous) {
        msg.setAsynchronous(true);  // ② 如果 Handler 是异步的，标记消息为异步
    }
    return queue.enqueueMessage(msg, uptimeMillis);  // ③ 交给 MessageQueue
}
```

`msg.target = this` 是消息与 Handler 的绑定点。后续 `Looper.loop()` 中的 `msg.target.dispatchMessage(msg)` 就是通过这个引用回调到正确的 Handler。

**稳定性关联：** `msg.target = this` 建立了一条从 Message → Handler 的强引用。如果 Handler 是 Activity 的非静态内部类，引用链就是 `Message → Handler → Activity`。当这条 Message 是延迟消息（如 `sendMessageDelayed(msg, 60000)`），它会在 MessageQueue 中停留 60 秒。这 60 秒内 Activity 即使调用了 `finish()` 也无法被 GC——**这就是 Handler 内存泄漏的根源。**

### 4.3 MessageQueue.enqueueMessage

> Source: `frameworks/base/core/java/android/os/MessageQueue.java`

```java
boolean enqueueMessage(Message msg, long when) {
    if (msg.target == null) {
        throw new IllegalArgumentException("Message must have a target.");
    }
    if (msg.isInUse()) {
        throw new IllegalStateException(msg + " This message is already in use.");
    }

    synchronized (this) {
        if (mQuitting) {
            IllegalStateException e = new IllegalStateException(
                    msg.target + " sending message to a Handler on a dead thread");
            Log.w(TAG, e.getMessage(), e);
            msg.recycle();
            return false;
        }

        msg.markInUse();       // 标记为使用中
        msg.when = when;       // 设置预期执行时间
        Message p = mMessages; // 当前链表头
        boolean needWake;

        if (p == null || when == 0 || when < p.when) {
            // Case 1: 队列为空 / when=0(插到头部) / 新消息比队列头更早
            msg.next = p;
            mMessages = msg;   // 新消息成为链表头
            needWake = mBlocked;  // 如果线程正在阻塞，需要唤醒
        } else {
            // Case 2: 按 when 排序插入链表中间
            needWake = mBlocked && p.target == null && msg.isAsynchronous();
            Message prev;
            for (;;) {
                prev = p;
                p = p.next;
                if (p == null || when < p.when) {
                    break;  // 找到插入位置
                }
                if (needWake && p.isAsynchronous()) {
                    needWake = false;  // 前面已有异步消息，不需要唤醒
                }
            }
            msg.next = p;
            prev.next = msg;  // 插入到 prev 和 p 之间
        }

        if (needWake) {
            nativeWake(mPtr);  // 唤醒阻塞在 epoll_wait 的线程
        }
    }
    return true;
}
```

### 4.4 排序插入的可视化

```
初始队列:
mMessages → [A, when=100] → [C, when=300] → [D, when=500] → null

插入 [B, when=200]:
    遍历链表，找到 when=200 应该在 A(100) 和 C(300) 之间
    
mMessages → [A, when=100] → [B, when=200] → [C, when=300] → [D, when=500] → null

插入 [E, when=50]:
    when=50 < 队列头 A(100)，直接插到头部

mMessages → [E, when=50] → [A, when=100] → [B, when=200] → [C, when=300] → [D, when=500] → null
    needWake = mBlocked（E 插到头部，如果线程在睡觉就需要唤醒）
```

### 4.5 唤醒条件详解

唤醒（`nativeWake`）不是每次入队都会触发。只有在以下条件下才唤醒：

| 条件 | 场景 | 原因 |
| :--- | :--- | :--- |
| 新消息插到队列头部 && `mBlocked=true` | 新消息比所有已有消息更早到期 | 线程可能在等一个更晚的消息，需要提前唤醒 |
| 队列头是同步屏障 && 新消息是异步的 && `mBlocked=true` | 队列被屏障阻塞，新异步消息可以通过 | 线程因为没有异步消息而阻塞，新异步消息到达需要唤醒 |
| 队列为空 && `mBlocked=true` | 队列空，线程无限期阻塞 | 有新消息到达，唤醒线程处理 |

**稳定性关联：** 高频 `post()` 调用（如在 `onDraw()` 中每帧都 `handler.post()`）会导致频繁的 `nativeWake()` 调用。每次 `nativeWake()` 都是一次 `write(eventfd)` 系统调用，虽然开销不大，但在极端场景（每秒数百次）下会累积 CPU 开销。更严重的是，高频入队意味着队列中消息堆积，排队延迟增加，每条消息的 slowDelivery 指标恶化。

---

## 5. 消息分发

### 5.1 为什么 dispatchMessage 有三级优先级

Handler 提供了三种定义消息处理逻辑的方式：`post(Runnable)`、构造时传入 `Callback`、重写 `handleMessage()`。这三种方式有明确的优先级——理解这个优先级，才能正确使用拦截器模式，避免消息被"吞掉"。

### 5.2 源码走读

> Source: `frameworks/base/core/java/android/os/Handler.java`

```java
public void dispatchMessage(Message msg) {
    if (msg.callback != null) {
        // 优先级 1：Message 自带的 Runnable（post 方式）
        handleCallback(msg);
    } else {
        if (mCallback != null) {
            // 优先级 2：Handler 构造时传入的 Callback
            if (mCallback.handleMessage(msg)) {
                return;  // Callback 返回 true → 消息被拦截，不再往下走
            }
        }
        // 优先级 3：Handler 子类重写的 handleMessage
        handleMessage(msg);
    }
}

private static void handleCallback(Message message) {
    message.callback.run();  // 直接调用 Runnable.run()
}
```

### 5.3 三级分发流程图

```
dispatchMessage(msg)
    │
    ├── msg.callback != null ?
    │       │
    │       ├── 是 → handleCallback(msg)
    │       │         即 msg.callback.run()
    │       │         （post(Runnable) 发送的消息走这条路）
    │       │         → 返回，不再往下
    │       │
    │       └── 否 ↓
    │
    ├── mCallback != null ?
    │       │
    │       ├── 是 → mCallback.handleMessage(msg)
    │       │         │
    │       │         ├── 返回 true → 消息被拦截，返回
    │       │         │
    │       │         └── 返回 false → 继续往下 ↓
    │       │
    │       └── 否 ↓
    │
    └── handleMessage(msg)
            （Handler 子类重写的方法）
```

### 5.4 三种方式的使用场景

| 优先级 | 方式 | 设置方式 | 典型场景 |
| :--- | :--- | :--- | :--- |
| 1（最高） | `msg.callback` | `handler.post(runnable)` | 快速提交一次性任务 |
| 2 | `mCallback` | `new Handler(looper, callback)` | 不需要继承 Handler 时的拦截器/处理器 |
| 3（最低） | `handleMessage()` | 继承 Handler 重写 | 传统的消息处理模式 |

### 5.5 Callback 的拦截模式

`Handler.Callback` 是一个容易被忽视但非常有用的接口：

```java
public interface Callback {
    boolean handleMessage(Message msg);
}
```

返回值的语义：
- **返回 true**：消息已被处理，不再调用 `Handler.handleMessage()`。
- **返回 false**：消息未被完全处理，继续调用 `Handler.handleMessage()`。

这就是拦截器模式——你可以在不修改 Handler 子类的情况下，通过 Callback 拦截和预处理消息。

**稳定性关联：** 需要注意的是，优先级 1（`msg.callback`）是**不可拦截**的——如果消息是通过 `post(Runnable)` 发送的，`mCallback` 根本没有机会拦截它，因为在检查 `mCallback` 之前就已经执行了 `msg.callback.run()` 并返回。这意味着如果你的监控或拦截逻辑依赖 `mCallback`，**它对 `post()` 方式发送的消息无效**。

---

## 6. 回收机制

### 6.1 为什么回收机制需要特别关注

Message 的回收不只是"放回对象池"这么简单。回收时的字段清空逻辑直接关系到内存泄漏防治和野指针风险。如果回收逻辑有缺陷，已释放的 Message 可能仍被外部代码引用，读到脏数据或 null 值。

### 6.2 回收流程

> Source: `frameworks/base/core/java/android/os/Message.java`

回收发生在 `Looper.loop()` 的每次迭代末尾：

```java
// Looper.loop() 中
msg.target.dispatchMessage(msg);  // 分发消息
// ...
msg.recycleUnchecked();           // 回收消息
```

`recycleUnchecked()` 的完整逻辑（前面已展示，此处聚焦清空顺序）：

```java
void recycleUnchecked() {
    // 第一步：清空所有字段
    flags = FLAG_IN_USE;       // 标记"在池中"
    what = 0;
    arg1 = 0;
    arg2 = 0;
    obj = null;                // ★ 打断对 obj 对象的引用
    replyTo = null;
    sendingUid = UID_NONE;
    workSourceUid = UID_NONE;
    when = 0;
    target = null;             // ★ 打断对 Handler 的引用
    callback = null;           // ★ 打断对 Runnable 的引用
    data = null;               // ★ 打断对 Bundle 的引用

    // 第二步：加入对象池（如果池未满）
    synchronized (sPoolSync) {
        if (sPoolSize < MAX_POOL_SIZE) {
            next = sPool;
            sPool = this;
            sPoolSize++;
        }
    }
}
```

### 6.3 回收后的引用断链

```
回收前的引用关系：
    Message
      ├── target ──► Handler ──► Activity（内存泄漏！）
      ├── callback ──► Runnable ──► Activity（内存泄漏！）
      ├── obj ──► SomeLargeObject
      └── data ──► Bundle ──► Parcelable 数据

回收后的引用关系：
    Message（在对象池中）
      ├── target = null     ← 引用断开，Handler 可被 GC
      ├── callback = null   ← 引用断开，Runnable 可被 GC
      ├── obj = null        ← 引用断开，大对象可被 GC
      └── data = null       ← 引用断开，Bundle 可被 GC
```

### 6.4 FLAG_IN_USE 的双重语义

`FLAG_IN_USE` 在 Message 的生命周期中有两个使用时机，语义略有不同：

| 时机 | 设置方式 | 语义 | 目的 |
| :--- | :--- | :--- | :--- |
| `MessageQueue.next()` 取出消息时 | `msg.markInUse()` | "消息正在被处理" | 防止处理中的消息被手动 `recycle()` |
| `recycleUnchecked()` 回收时 | `flags = FLAG_IN_USE` | "消息在对象池中" | 防止池中的消息被再次 `recycle()` |

本质上，`FLAG_IN_USE` 表示"这个 Message 当前不处于可发送的状态"——无论是正在被处理，还是已经在对象池中等待复用。

### 6.5 recycle() vs recycleUnchecked()

```java
// 公开 API：带安全检查
public void recycle() {
    if (isInUse()) {
        if (gCheckRecycle) {
            throw new IllegalStateException(
                    "This message cannot be recycled because it is still in use.");
        }
        return;
    }
    recycleUnchecked();
}

// 内部方法：无检查，由 Looper.loop() 调用
void recycleUnchecked() {
    // ... 直接清空并回收
}
```

`Looper.loop()` 调用的是 `recycleUnchecked()`（不做 `isInUse` 检查），因为此时消息已经被分发完毕，`FLAG_IN_USE` 状态是已知的。而用户代码应该调用 `recycle()`，它会检查 `FLAG_IN_USE` 防止重复回收。

**稳定性关联：** 一个常见的错误是在 `handleMessage()` 中保存了 Message 引用，期望后续使用：

```java
// 危险代码！
Message savedMsg;

@Override
public void handleMessage(Message msg) {
    savedMsg = msg;  // 保存引用
}

// 稍后...
void doSomethingLater() {
    int what = savedMsg.what;  // ← 可能读到 0（字段已被清空）
    Object obj = savedMsg.obj; // ← 可能读到 null 或另一条消息的数据
}
```

`handleMessage()` 返回后，`Looper.loop()` 会立刻调用 `msg.recycleUnchecked()`，清空所有字段并将 Message 放回对象池。如果此后有另一处代码调用 `Message.obtain()` 取到了这个 Message 并设置了新数据，你的 `savedMsg` 引用就会读到完全无关的数据——这就是"野指针"风险。正确做法是在 `handleMessage()` 中立即提取所需数据，不要保留 Message 引用。

---

## 7. 完整生命周期总览

将以上所有环节串联起来，一条 Message 的完整生命周期如下：

```
① obtain() ─────────────────────────────────────────────────────────────────►
   │ 从对象池取（或 new）                                                      │
   │ flags = 0, 所有字段可用                                                   │
   ▼                                                                          │
② 设置字段 ──────────────────────────────────────────────────────────────────► │
   │ msg.what = X; msg.obj = data; ...                                        │
   ▼                                                                          │
③ sendMessage / post ───────────────────────────────────────────────────────► │
   │ post → getPostMessage 包装 Runnable → sendMessageDelayed                 │
   │ → sendMessageAtTime                                                      │
   ▼                                                                          │
④ Handler.enqueueMessage ──────────────────────────────────────────────────► │
   │ msg.target = handler                                                     │
   │ → MessageQueue.enqueueMessage                                            │
   │   msg.markInUse()（flags |= FLAG_IN_USE）                                │
   │   按 when 排序插入链表                                                     │
   │   needWake → nativeWake()                                                │
   ▼                                                                          │
⑤ MessageQueue.next() ─────────────────────────────────────────────────────► │
   │ 从链表头取出到期消息                                                       │
   │ msg.markInUse()                                                          │
   ▼                                                                          │
⑥ Looper.loop() → msg.target.dispatchMessage(msg) ────────────────────────► │
   │ 三级分发：callback → mCallback → handleMessage                            │
   ▼                                                                          │
⑦ msg.recycleUnchecked() ──────────────────────────────────────────────────► │
   │ 清空所有字段（target/callback/obj/data = null）                            │
   │ flags = FLAG_IN_USE                                                      │
   │ 加入 sPool 对象池（如果 sPoolSize < 50）                                  │
   ▼                                                                          │
   回到 ① ── 等待下次 obtain() 复用                                             │
```

---

## 8. 稳定性实战案例

### 案例一：高频 post(Runnable) 导致对象池耗尽与 GC 风暴

**现象：**

某短视频 App 在播放页面滑动切换视频时，用户反馈明显的卡顿掉帧。Systrace 分析发现主线程每 200ms 出现一次 GC 暂停（`HeapTaskDaemon`），每次暂停 3-8ms，导致频繁掉帧。

通过 Android Studio Profiler 的 Memory 面板观察到大量 `android.os.Message` 对象被分配和回收，分配频率约 500 次/秒。

**分析思路：**

1. **定位分配热点**：通过 Allocation Tracking 锁定分配点，发现大量 `Message` 分配来自 `Message.obtain()` 内部的 `new Message()`——说明对象池频繁被耗空。

2. **追查消息来源**：搜索代码中的 `handler.post()` 和 `handler.sendMessage()` 调用，发现视频播放器的进度更新逻辑存在问题：

```java
// 问题代码：视频播放器的进度回调
public class VideoPlayerView extends FrameLayout {
    private Handler mHandler = new Handler(Looper.getMainLooper());

    // 由 Native 层回调，频率约 60 次/秒
    void onProgressUpdate(long currentMs, long totalMs) {
        mHandler.post(() -> {
            mProgressBar.setProgress((int) (currentMs * 100 / totalMs));
            mTimeLabel.setText(formatTime(currentMs));
        });
    }

    // 由 Native 层回调，频率约 30 次/秒
    void onBufferingUpdate(int percent) {
        mHandler.post(() -> {
            mBufferBar.setSecondaryProgress(percent);
        });
    }

    // 弹幕模块：每条弹幕到来时回调，高峰期约 200 次/秒
    void onDanmakuReceived(Danmaku danmaku) {
        mHandler.post(() -> {
            mDanmakuView.addDanmaku(danmaku);
        });
    }
}
```

3. **计算消息频率**：进度更新 60 次/秒 + 缓冲更新 30 次/秒 + 弹幕（高峰期 200 次/秒）+ 系统消息约 50 次/秒 = **峰值约 340 次/秒**。

4. **对象池瓶颈**：对象池大小 `MAX_POOL_SIZE = 50`。每秒 340 次 `obtain()`，每秒 340 次 `recycle()`。由于 `obtain()` 和 `recycle()` 在不同时刻发生（消息需要在队列中停留一段时间），瞬时峰值可能有 100+ 条消息同时在队列中。当队列中的消息数超过 50 条时，`recycle()` 填满池子后，后续 `obtain()` 就会频繁 `new Message()`。

```
时间线（1 秒内）：
T=0ms:     池中 50 条 → obtain 取走 50 条 → 池空
T=0~50ms:  队列中 80 条消息等待处理，每次 obtain 都 new
T=50ms:    最早的消息开始被分发和回收，池子开始回填
T=50~100ms: obtain 有时从池取，有时 new（取决于回收速度是否跟上分配速度）
→ 大量短生命周期 Message 对象被创建 → GC 压力
```

**根因：**

视频播放器的多个 Native 回调（进度、缓冲、弹幕）各自独立地 `post(Runnable)` 到主线程，合计峰值约 340 次/秒。每次 `post` 都通过 `Message.obtain()` 获取 Message，超出对象池 50 条的缓存能力后，频繁触发 `new Message()`。大量短生命周期的 Message 对象导致 GC 频率过高，每次 GC 暂停引发掉帧。

**修复方案：**

1. **合并高频回调**：将进度更新从"每次回调立即 post"改为"采样+合并"：

```java
// 修复后：合并进度更新，16ms 内只发一次
private boolean mProgressUpdatePending = false;
private long mPendingCurrentMs;

void onProgressUpdate(long currentMs, long totalMs) {
    mPendingCurrentMs = currentMs;
    mPendingTotalMs = totalMs;
    if (!mProgressUpdatePending) {
        mProgressUpdatePending = true;
        mHandler.post(mProgressUpdateRunnable);
    }
}

private final Runnable mProgressUpdateRunnable = () -> {
    mProgressUpdatePending = false;
    mProgressBar.setProgress((int) (mPendingCurrentMs * 100 / mPendingTotalMs));
    mTimeLabel.setText(formatTime(mPendingCurrentMs));
};
```

2. **弹幕批量处理**：将弹幕回调改为批量模式，每 50ms 批量处理一次：

```java
private final List<Danmaku> mPendingDanmakus = new ArrayList<>();

void onDanmakuReceived(Danmaku danmaku) {
    synchronized (mPendingDanmakus) {
        mPendingDanmakus.add(danmaku);
    }
    if (!mDanmakuBatchPending) {
        mDanmakuBatchPending = true;
        mHandler.postDelayed(mDanmakuBatchRunnable, 50);
    }
}

private final Runnable mDanmakuBatchRunnable = () -> {
    mDanmakuBatchPending = false;
    List<Danmaku> batch;
    synchronized (mPendingDanmakus) {
        batch = new ArrayList<>(mPendingDanmakus);
        mPendingDanmakus.clear();
    }
    mDanmakuView.addDanmakuBatch(batch);
};
```

3. **复用 Runnable**：将匿名 Runnable 改为成员变量，避免每次 `post` 时创建新的 lambda 对象。

```
修复前后对比：
┌──────────────────────────────────────┬────────────┬────────────┐
│ 指标                                  │ 修复前      │ 修复后      │
├──────────────────────────────────────┼────────────┼────────────┤
│ 主线程消息频率（峰值）                 │ ~340/秒    │ ~80/秒     │
│ Message.obtain() 触发 new 的比例       │ ~35%       │ < 2%       │
│ GC 频率                               │ 5 次/秒    │ < 0.5 次/秒│
│ 播放页滑动掉帧率                       │ 18%        │ 2.5%       │
│ 用户卡顿投诉 / 日                     │ 230        │ 12         │
└──────────────────────────────────────┴────────────┴────────────┘
```

**给稳定性架构师的启示：** 对象池大小是固定的（`MAX_POOL_SIZE = 50`），它无法应对无限制的消息频率。当你发现 GC 压力与 `Message` 分配相关时，优先检查是否存在高频 `post()` 调用。治本之策不是增大池子（这需要修改 Framework），而是降低消息频率——通过合并、采样、批处理减少不必要的消息创建。

---

### 案例二：recycleUnchecked 后引用未释放，导致 Activity 泄漏

**现象：**

某社交 App 的内存监控系统检测到"聊天详情页（`ChatDetailActivity`）"存在严重的内存泄漏。LeakCanary 报告了以下引用链：

```
┬───
│ GC Root: Global variable in system class
│
├─ android.os.Message instance
│    ↓ callback
├─ com.example.chat.ChatDetailActivity$2 instance (anonymous Runnable)
│    ↓ this$0
╰─ com.example.chat.ChatDetailActivity instance  ★ LEAKED
```

用户反复进出聊天详情页 10 次后，内存占用从 80MB 增长到 200MB，10 个 `ChatDetailActivity` 实例全部无法被 GC 回收。

**分析思路：**

1. **解读引用链**：LeakCanary 显示泄漏路径是 `Message.callback` → 匿名 Runnable → Activity。但 Message 在 `recycleUnchecked()` 中会将 `callback` 置 null——为什么仍然持有引用？

2. **排查代码**：在 `ChatDetailActivity` 中发现以下逻辑：

```java
public class ChatDetailActivity extends AppCompatActivity {
    private Handler mHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        schedulePollNewMessages();
    }

    private void schedulePollNewMessages() {
        mHandler.postDelayed(() -> {
            pollNewMessages();
            schedulePollNewMessages();  // 递归调度，每 30 秒轮询一次
        }, 30_000);
    }

    private void pollNewMessages() {
        // 网络请求拉取新消息...
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        // 没有调用 mHandler.removeCallbacksAndMessages(null) !
    }
}
```

3. **泄漏机制**：
   - `schedulePollNewMessages()` 通过 `postDelayed` 向主线程 Handler 发送了一条 30 秒延迟的消息。
   - 该消息的 `callback` 字段持有匿名 Runnable，Runnable 隐式引用 `ChatDetailActivity.this`。
   - 用户 30 秒内退出 Activity，调用 `onDestroy()`，但未执行 `removeCallbacksAndMessages(null)`。
   - 这条延迟消息仍在 MessageQueue 的链表中，引用链为 `MessageQueue.mMessages → Message → callback(Runnable) → Activity`。
   - **Message 还没被 dispatch，所以 `recycleUnchecked()` 还没执行**——字段清空根本没有发生。
   - 30 秒后消息被处理，`recycleUnchecked()` 清空了 callback，但 Runnable 内部又调用了 `schedulePollNewMessages()`，创建了新的延迟消息——泄漏持续循环。

4. **为什么 10 个实例都泄漏**：每次进入页面都调用 `schedulePollNewMessages()`，每次退出都不清理。即使前一个消息到期执行了，它又会创建新的延迟消息。只要 Activity 还没被 GC（因为有 Message 引用），递归就不会停止。

```
时间线：
T=0s:    进入 ChatDetailActivity-1，postDelayed 30s
T=5s:    退出，onDestroy（未 removeCallbacks）
         MessageQueue 中仍有 30s 延迟消息 → Activity-1 泄漏
T=10s:   进入 ChatDetailActivity-2，postDelayed 30s
T=15s:   退出，Activity-2 泄漏
...
T=30s:   Activity-1 的延迟消息到期，执行 pollNewMessages
         → schedulePollNewMessages 又 postDelayed 30s
         → Activity-1 继续泄漏（新消息再次引用它）
```

**根因：**

`ChatDetailActivity` 使用 `postDelayed` 实现周期性轮询，但在 `onDestroy()` 中没有清理未执行的延迟消息。延迟消息在 MessageQueue 中持有 `Message.callback`（匿名 Runnable），Runnable 隐式引用 Activity，形成泄漏。同时递归调度导致泄漏永不终止。

**修复方案：**

1. **短期修复**：在 `onDestroy()` 中清理所有待处理的消息和回调：

```java
@Override
protected void onDestroy() {
    super.onDestroy();
    mHandler.removeCallbacksAndMessages(null);
}
```

2. **根治方案**：使用静态内部类 + WeakReference，从根本上避免 Handler/Runnable 隐式持有 Activity：

```java
public class ChatDetailActivity extends AppCompatActivity {
    private final Handler mHandler = new Handler(Looper.getMainLooper());
    private final Runnable mPollRunnable = new PollRunnable(this);

    private static class PollRunnable implements Runnable {
        private final WeakReference<ChatDetailActivity> mActivityRef;

        PollRunnable(ChatDetailActivity activity) {
            mActivityRef = new WeakReference<>(activity);
        }

        @Override
        public void run() {
            ChatDetailActivity activity = mActivityRef.get();
            if (activity == null || activity.isDestroyed()) {
                return;
            }
            activity.pollNewMessages();
            activity.mHandler.postDelayed(this, 30_000);
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        mHandler.postDelayed(mPollRunnable, 30_000);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        mHandler.removeCallbacks(mPollRunnable);
    }
}
```

3. **长期治理**：
   - 在 CI 中引入 Lint 规则检测非静态内部类 Handler 和匿名 Runnable 与 `postDelayed` 的组合。
   - 在 APM 中监控 MessageQueue 中停留超过 30 秒的延迟消息，结合 `target` 和 `callback` 的类名上报。

```
修复前后对比：
┌──────────────────────────────────────┬────────────┬────────────┐
│ 指标                                  │ 修复前      │ 修复后      │
├──────────────────────────────────────┼────────────┼────────────┤
│ 反复进出聊天页 10 次后内存占用         │ 200MB      │ 85MB       │
│ ChatDetailActivity 泄漏实例数         │ 10         │ 0          │
│ LeakCanary 告警次数 / 天              │ 350        │ 0          │
│ 后台 OOM Crash 率                     │ 1.2%       │ 0.15%      │
└──────────────────────────────────────┴────────────┴────────────┘
```

**给稳定性架构师的启示：**

1. **`recycleUnchecked()` 的字段清空只发生在消息被分发之后**。延迟消息在队列中等待期间，所有字段（尤其是 `target` 和 `callback`）保持原样，引用链完整存在。因此，Handler 内存泄漏的防线不能依赖回收机制，必须在 `onDestroy()` 中主动调用 `removeCallbacksAndMessages(null)` 清理。
2. **匿名 Runnable 是隐式引用的温床**。Lambda 表达式和匿名内部类会自动捕获外部类的 `this` 引用。在需要与 Handler 配合使用的场景中，优先使用静态类 + `WeakReference` 的模式。
3. **递归调度的消息是泄漏的"永动机"**。如果一条消息的处理逻辑中会创建新的延迟消息，即使前一条消息被回收，新消息又会重新建立引用链。这种模式必须有明确的终止条件（如检查 Activity 是否已销毁）。

---

## 总结

本篇沿着 Message 的完整生命周期，从数据结构到对象池、从发送入队到三级分发、从回收清空到池中复用，逐一拆解了每个环节的实现细节和稳定性风险。

核心要点：

1. **Message 数据结构**：`target` 建立与 Handler 的引用关系（内存泄漏源头），`callback` 承载 `post(Runnable)` 的任务，`when` 决定调度时间，`next` 在队列和对象池中复用，`flags` 的 `FLAG_IN_USE` 防止重复回收、`FLAG_ASYNCHRONOUS` 支持优先调度。
2. **对象池 sPool**：全局静态单链表，`MAX_POOL_SIZE = 50`。`obtain()` 从池头取或 `new`，`recycleUnchecked()` 清空字段后加入池头。在高频消息场景下，使用 `obtain()` 代替 `new` 能显著降低 GC 压力。
3. **消息发送**：所有方式（`sendMessage` / `post` / `postDelayed` / `sendMessageAtFrontOfQueue`）最终汇聚到 `sendMessageAtTime()` → `enqueueMessage()`。`post(Runnable)` 通过 `getPostMessage()` 将 Runnable 包装为 `Message.callback`。
4. **enqueueMessage**：`msg.target = this` 绑定 Handler → `msg.markInUse()` 标记使用中 → 按 `when` 排序插入链表 → 满足条件时 `nativeWake()` 唤醒。高频入队导致频繁唤醒和消息排队延迟。
5. **dispatchMessage 三级优先级**：`msg.callback`（Runnable.run）> `mCallback.handleMessage`（可拦截）> `handleMessage`（Handler 子类重写）。`post()` 方式发送的消息无法被 `mCallback` 拦截。
6. **回收机制**：`recycleUnchecked()` 清空所有字段（打断引用链）→ `flags = FLAG_IN_USE` 标记在池中 → 加入 `sPool`。回收后仍持有 Message 引用会读到脏数据。延迟消息在队列中等待期间引用链完整存在，是 Handler 内存泄漏的直接原因。

下一篇我们将深入**同步屏障与异步消息**——理解 Choreographer 如何利用同步屏障保障 16.6ms 的渲染优先级，以及屏障未移除时的灾难性后果。
