# 07-Handler 稳定性风险全景：内存泄漏、消息堆积与卡顿

Handler 消息机制是 Android 的事件驱动引擎，但它同时也是线上稳定性问题的高发地带。**内存泄漏、消息堆积、主线程卡顿、线程资源耗尽**——这些问题在线上 App 中反复出现，表象各不相同，但根因都可以回溯到 Handler 机制的使用不当。

本文是一张完整的"风险地图"。对于每一类 Handler 相关的稳定性问题，你将知道：**它长什么样（现象）、为什么会发生（根因）、如何从日志和 trace 中识别它（诊断特征）、如何修复和预防（治理方向）。**

---

## 1. Handler 内存泄漏的三种模式

### 1.1 为什么 Handler 是内存泄漏的"常客"

Handler 内存泄漏是 Android 中最经典的泄漏模式之一。它的核心在于 **Message 的引用链**：

```
GC Root: Thread "main"
  → Looper.mQueue (MessageQueue)
    → MessageQueue.mMessages (Message 链表头)
      → Message.target (Handler 引用)
        → Handler 持有的外部对象 (Activity / Fragment / View)
```

只要 MessageQueue 中存在未处理的 Message，这条引用链就不会断开。如果 Message 的 `when` 时间很远（延迟消息），或者队列堆积导致消息长时间等待，那么 Handler 及其持有的对象都无法被 GC 回收。

Handler 泄漏有三种典型模式，根因各不相同。

### 1.2 模式一：非静态内部类 Handler + 延迟消息未清理

**这是什么**

最经典也最常见的 Handler 泄漏模式。开发者在 Activity 或 Fragment 中直接创建 Handler 的匿名内部类或非静态内部类，然后发送延迟消息。当 Activity 销毁时，延迟消息仍在队列中等待，导致 Activity 无法被回收。

**为什么会泄漏**

Java 的非静态内部类隐式持有外部类的引用。结合 Handler 消息机制的引用链：

```
MessageQueue.mMessages
  → Message (when = 未来某时刻, 还在队列中等待)
    → Message.target = MyHandler (非静态内部类)
      → MyHandler.this$0 = MainActivity (隐式引用)
        → MainActivity.mBitmapCache (8MB)
        → MainActivity.mRecyclerView → Adapter → ViewHolder → 大量 Bitmap
```

**问题代码**

```java
// ❌ 经典的泄漏代码
public class MainActivity extends AppCompatActivity {

    private static final int MSG_REFRESH = 1;

    // 非静态匿名内部类 → 隐式持有 MainActivity.this
    private final Handler mHandler = new Handler(Looper.getMainLooper()) {
        @Override
        public void handleMessage(@NonNull Message msg) {
            if (msg.what == MSG_REFRESH) {
                refreshUI();  // 引用 MainActivity 的方法
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        // 5 分钟后刷新 → 延迟消息将 Handler 引用"钉"在 MessageQueue 中
        mHandler.sendEmptyMessageDelayed(MSG_REFRESH, 5 * 60 * 1000L);
    }

    // 没有在 onDestroy 中清理消息 → 泄漏
}
```

用户在 5 分钟内反复进出 Activity 3 次，就会产生 3 个无法回收的 MainActivity 实例，每个实例都持有完整的 View 树和 Bitmap 缓存。

**修复方案**

```java
// ✅ 静态内部类 + WeakReference
public class MainActivity extends AppCompatActivity {

    private static class SafeHandler extends Handler {
        private final WeakReference<MainActivity> mActivityRef;

        SafeHandler(MainActivity activity, Looper looper) {
            super(looper);
            mActivityRef = new WeakReference<>(activity);
        }

        @Override
        public void handleMessage(@NonNull Message msg) {
            MainActivity activity = mActivityRef.get();
            if (activity == null || activity.isFinishing() || activity.isDestroyed()) {
                return;
            }
            if (msg.what == MSG_REFRESH) {
                activity.refreshUI();
            }
        }
    }

    private final SafeHandler mHandler = new SafeHandler(this, Looper.getMainLooper());

    @Override
    protected void onDestroy() {
        super.onDestroy();
        // 清除所有消息和回调 —— 断开引用链
        mHandler.removeCallbacksAndMessages(null);
    }
}
```

关键修复两处：

1. **静态内部类**：不持有外部类引用，通过 `WeakReference` 弱引用 Activity。
2. **onDestroy 清理**：`removeCallbacksAndMessages(null)` 会移除 Handler 关联的所有 Message 和 Runnable，从 MessageQueue 中断开引用链。

看 `removeCallbacksAndMessages` 的源码实现：

```java
// frameworks/base/core/java/android/os/Handler.java
public final void removeCallbacksAndMessages(@Nullable Object token) {
    mQueue.removeCallbacksAndMessages(this, token);
}

// frameworks/base/core/java/android/os/MessageQueue.java
void removeCallbacksAndMessages(Handler h, Object object) {
    synchronized (this) {
        Message p = mMessages;
        // 遍历链表，移除所有 target == h 且 obj == object 的 Message
        while (p != null && p.target == h
                && (object == null || p.obj == object)) {
            Message n = p.next;
            mMessages = n;
            p.recycleUnchecked();
            p = n;
        }
        while (p != null) {
            Message n = p.next;
            if (n != null && n.target == h
                    && (object == null || n.obj == object)) {
                Message nn = n.next;
                n.recycleUnchecked();
                p.next = nn;
            } else {
                p = n;
            }
        }
    }
}
```

当 `token` 传 `null` 时，该方法会移除此 Handler 的**所有**消息——这是最彻底的清理。

**稳定性关联：** 这是 LeakCanary 报告中出现频率最高的泄漏类型。在大型 App 中，如果多个页面都存在此问题，可积累数十 MB 无法回收的内存，直接导致 OOM Crash。

### 1.3 模式二：Message.obj 持有大对象

**这是什么**

开发者通过 `Message.obj` 传递 Bitmap、大 List、数据库查询结果等大对象。消息在队列中等待期间，这些大对象无法被 GC 回收。

**为什么会泄漏**

`Message.obj` 是 `Object` 类型，可以指向任意对象。只要 Message 还在 MessageQueue 中（无论是等待延迟执行，还是因为队列堆积），`obj` 指向的对象就被引用链"钉住"：

```
MessageQueue.mMessages
  → Message (when = 未来某时刻)
    → Message.obj = ArrayList<Bitmap> (100MB)
```

即使没有非静态内部类的问题，大对象本身的生命周期被消息延迟拉长了。

**问题代码**

```java
// ❌ Message.obj 持有大对象
public void onDataLoaded(List<Bitmap> bitmaps) {
    Message msg = Message.obtain();
    msg.what = MSG_UPDATE_GALLERY;
    msg.obj = bitmaps;  // 持有大量 Bitmap 引用
    // 延迟 30 秒处理 → 30 秒内这些 Bitmap 无法被回收
    mHandler.sendMessageDelayed(msg, 30_000);
}
```

如果 `bitmaps` 列表包含 20 张 Bitmap（每张 5MB），这 100MB 内存将被锁定 30 秒。如果用户在此期间切换到其他页面触发了新的图片加载，内存压力急剧上升。

**修复方案**

```java
// ✅ 方案 1：仅传递标识符，使用时再获取
public void onDataLoaded(List<String> bitmapUrls) {
    Message msg = Message.obtain();
    msg.what = MSG_UPDATE_GALLERY;
    msg.obj = new ArrayList<>(bitmapUrls);  // 只传 URL 列表，不传 Bitmap
    mHandler.sendMessageDelayed(msg, 30_000);
}

// handleMessage 中再根据 URL 获取 Bitmap（可能从缓存获取）

// ✅ 方案 2：使用 WeakReference 包装
public void onDataLoaded(List<Bitmap> bitmaps) {
    Message msg = Message.obtain();
    msg.what = MSG_UPDATE_GALLERY;
    msg.obj = new WeakReference<>(bitmaps);
    mHandler.sendMessageDelayed(msg, 30_000);
}
```

**稳定性关联：** 此模式在 hprof 分析中表现为"Message 引用了大量内存"。由于 `Message.obj` 类型是 `Object`，静态分析工具难以检测具体的泄漏大小，需要运行时分析（MAT / Perfetto Memory）才能发现。

### 1.4 模式三：IdleHandler 注册后未移除

**这是什么**

`IdleHandler` 通过 `MessageQueue.addIdleHandler()` 注册，在消息队列空闲时被回调。如果 `queueIdle()` 返回 `true`，它会一直留在 `mIdleHandlers` 列表中，**永远不会被自动移除**。

**为什么会泄漏**

看 `MessageQueue.next()` 中 IdleHandler 的处理逻辑：

```java
// frameworks/base/core/java/android/os/MessageQueue.java
Message next() {
    // ...
    for (;;) {
        // ... 取消息逻辑 ...

        // 如果没有消息要处理，执行 IdleHandler
        for (int i = 0; i < pendingIdleHandlerCount; i++) {
            final IdleHandler idler = mPendingIdleHandlers[i];
            boolean keep = false;
            try {
                keep = idler.queueIdle();  // ← 返回值决定是否保留
            } catch (Throwable t) {
                Log.wtf(TAG, "IdleHandler threw exception", t);
            }
            if (!keep) {
                synchronized (this) {
                    mIdleHandlers.remove(idler);  // 返回 false → 移除
                }
            }
            // 返回 true → 保留在列表中，下次空闲时继续回调
        }
    }
}
```

如果 `queueIdle()` 返回 `true` 并且 IdleHandler 是一个匿名内部类（持有 Activity 引用），那么引用链是：

```
GC Root: Thread "main"
  → Looper.mQueue (MessageQueue)
    → MessageQueue.mIdleHandlers (ArrayList)
      → IdleHandler (匿名内部类)
        → Activity (外部类引用)
```

**问题代码**

```java
// ❌ IdleHandler 返回 true 且持有 Activity 引用
public class DetailActivity extends AppCompatActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Looper.myQueue().addIdleHandler(() -> {
            // 空闲时上报统计数据（引用了 DetailActivity.this）
            reportPageMetrics(getPageData());
            return true;  // ← 永远保留！DetailActivity 永远无法回收
        });
    }
}
```

每次进入 DetailActivity 都注册一个新的 IdleHandler，退出后不会被移除。10 次进出 = 10 个泄漏的 DetailActivity + 10 个永驻的 IdleHandler。

**修复方案**

```java
// ✅ 方案 1：一次性 IdleHandler（返回 false）
Looper.myQueue().addIdleHandler(() -> {
    reportPageMetrics(getPageData());
    return false;  // ← 执行一次后自动移除
});

// ✅ 方案 2：手动管理生命周期
public class DetailActivity extends AppCompatActivity {
    private MessageQueue.IdleHandler mIdleHandler;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        mIdleHandler = () -> {
            reportPageMetrics(getPageData());
            return true;
        };
        Looper.myQueue().addIdleHandler(mIdleHandler);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (mIdleHandler != null) {
            Looper.myQueue().removeIdleHandler(mIdleHandler);
            mIdleHandler = null;
        }
    }
}
```

**稳定性关联：** IdleHandler 泄漏比 Handler 泄漏更隐蔽——LeakCanary 可能不会直接报告它，因为引用路径不涉及 Message.target。需要通过 hprof 分析 `MessageQueue.mIdleHandlers` 列表来发现。在大型 App 中，三方 SDK 的 IdleHandler 注册是常见的泄漏源。

---

## 2. 消息堆积与主线程卡顿

### 2.1 为什么消息堆积直接等于卡顿

Android 主线程是单线程事件循环模型。**所有消息在同一条流水线上串行处理，任何一条消息的延迟都会波及后续所有消息。** 消息堆积意味着 MessageQueue 中积压了大量待处理消息，每条消息都需要等待前面的消息处理完毕才能被执行。

表现为：
- 用户触摸事件响应延迟 → "界面不跟手"
- VSync 渲染消息被延迟 → 掉帧 → "界面卡顿"
- 系统超时检测消息到期 → ANR

消息堆积有四种典型场景。

### 2.2 场景一：主线程执行耗时操作

**这是什么**

在主线程执行磁盘 I/O（SharedPreferences commit、数据库查询）、网络请求、大量计算等耗时操作，直接阻塞 `Looper.loop()` 的 `dispatchMessage()` 调用。

**为什么会阻塞**

回顾 `Looper.loop()` 的核心逻辑：

```java
// frameworks/base/core/java/android/os/Looper.java
public static void loop() {
    for (;;) {
        Message msg = queue.next();          // 取出消息
        msg.target.dispatchMessage(msg);     // ← 在这里执行消息的处理逻辑
        msg.recycleUnchecked();              // 回收
    }
}
```

`dispatchMessage()` 是同步调用。如果某条消息的处理耗时 800ms，那么 `loop()` 就被阻塞 800ms，期间所有新到的消息只能在 MessageQueue 中排队等待：

```
时间线：
  0ms      100ms     200ms     800ms    801ms    802ms
  |--------|---------|---...----|--------|--------|
  消息A(3ms) 消息B(800ms!!)        消息C(2ms) InputEvent  VSync
            ↑ 开始处理              ↑ 等了 600ms  ↑ 等了 601ms → 掉帧
                                            ↑ 如果等待超过 5s → Input ANR
```

**典型问题代码**

```java
// ❌ 主线程执行数据库查询
mHandler.post(() -> {
    // 这条 Runnable 在主线程执行
    Cursor cursor = db.rawQuery(
        "SELECT * FROM messages WHERE thread_id = ? ORDER BY date DESC",
        new String[]{threadId}
    );
    // 如果表有 10 万行，可能耗时数百毫秒
    while (cursor.moveToNext()) {
        // 逐行处理...
    }
    cursor.close();
    updateUI(results);
});
```

**诊断特征**

ANR trace 中主线程的堆栈不在 `nativePollOnce()`，而是在业务代码中：

```
"main" prio=5 tid=1 Native
  at android.database.sqlite.SQLiteConnection.nativeExecuteForCursorWindow(Native)
  at android.database.sqlite.SQLiteSession.executeForCursorWindow(SQLiteSession.java:836)
  at android.database.sqlite.SQLiteQuery.fillWindow(SQLiteQuery.java:62)
  at com.example.app.ChatActivity.loadMessages(ChatActivity.java:156)  ← 业务代码
  at com.example.app.ChatActivity$1.run(ChatActivity.java:89)
  at android.os.Handler.handleCallback(Handler.java:938)
  at android.os.Handler.dispatchMessage(Handler.java:99)
  at android.os.Looper.loop(Looper.java:223)
```

**稳定性关联：** 这是最直接也最好修的卡顿类型。将耗时操作移到后台线程（HandlerThread / Executor / Coroutines），仅在结果就绪后 post 到主线程更新 UI。Android StrictMode 可以在开发阶段检测主线程 I/O。

### 2.3 场景二：高频 post 导致消息风暴

**这是什么**

短时间内向主线程大量 post 消息（例如传感器数据回调、动画帧计算、实时日志刷新），即使每条消息的处理时间很短（1-2ms），但消息的入队和唤醒本身也有开销。

**为什么会有性能问题**

每次 `enqueueMessage()` 插入到队列**头部时**，都会调用 `nativeWake()`：

```java
// frameworks/base/core/java/android/os/MessageQueue.java
boolean enqueueMessage(Message msg, long when) {
    synchronized (this) {
        // ... 插入逻辑 ...
        if (needWake) {
            nativeWake(mPtr);  // → write(mWakeEventFd, &inc, sizeof(uint64_t))
        }
    }
}
```

`nativeWake()` 底层是对 `eventfd` 的 `write()` 系统调用。高频唤醒意味着：

1. **频繁系统调用**：每次 `write()` 和对应的 `epoll_wait()` 返回都是 user↔kernel 切换。
2. **synchronized 锁竞争**：多个线程同时 post → 竞争 `MessageQueue` 的锁。
3. **CPU 开销**：大量短消息的调度开销（取出、分发、回收）累积起来不可忽视。
4. **GC 压力**：如果消息 obtain 速度超过 recycle 速度，对象池耗尽 → 大量 new Message → GC。

**典型问题代码**

```java
// ❌ 传感器高频回调直接 post 到主线程
sensorManager.registerListener(new SensorEventListener() {
    @Override
    public void onSensorChanged(SensorEvent event) {
        // 加速度传感器默认回调频率可达 100Hz+
        mainHandler.post(() -> {
            updateAccelerationUI(event.values[0], event.values[1], event.values[2]);
        });
    }
    // ...
}, accelerometer, SensorManager.SENSOR_DELAY_GAME);
```

100Hz 意味着每秒 100 条消息 → 100 次 enqueue + wake + dequeue + dispatch + recycle。

**修复方案**

```java
// ✅ 采样/合并策略：降低消息频率
private final AtomicReference<float[]> mLatestValues = new AtomicReference<>();
private boolean mUpdateScheduled = false;

@Override
public void onSensorChanged(SensorEvent event) {
    mLatestValues.set(event.values.clone());
    if (!mUpdateScheduled) {
        mUpdateScheduled = true;
        mainHandler.post(() -> {
            mUpdateScheduled = false;
            float[] values = mLatestValues.get();
            if (values != null) {
                updateAccelerationUI(values[0], values[1], values[2]);
            }
        });
    }
}
```

核心思想：**合并多次数据变更为一次 UI 更新**，将 100Hz 降为约 60Hz（跟随主线程消息处理速度）。

**稳定性关联：** Systrace/Perfetto 中表现为主线程密密麻麻的短消息，几乎没有空闲间隙。CPU 使用率偏高但单条消息耗时不长。通过 `Looper.Printer` 可以统计消息频率，发现异常的高频 Handler。

### 2.4 场景三：同步屏障未移除——主线程的"隐形死锁"

**这是什么**

同步屏障（Sync Barrier）是 `target == null` 的特殊 Message，插入后会阻塞所有同步消息，只放行异步消息。正常情况下由 `Choreographer` 在渲染流程中成对使用（`postSyncBarrier` / `removeSyncBarrier`）。但如果屏障被插入后没有被正确移除，**所有同步消息将被永久阻塞**。

**为什么表现为"假死"**

回顾 `MessageQueue.next()` 中屏障的处理：

```java
// frameworks/base/core/java/android/os/MessageQueue.java
Message next() {
    for (;;) {
        nativePollOnce(ptr, nextPollTimeoutMillis);
        synchronized (this) {
            Message msg = mMessages;
            if (msg != null && msg.target == null) {
                // 遇到同步屏障 → 跳过所有同步消息，只找异步消息
                do {
                    msg = msg.next;
                } while (msg != null && !msg.isAsynchronous());
            }
            if (msg != null) {
                // 找到异步消息 → 正常处理
            } else {
                // 没有异步消息 → 进入 nativePollOnce 阻塞
                nextPollTimeoutMillis = -1;  // ← 无限等待！
            }
        }
    }
}
```

当屏障存在且没有异步消息时：
- `nativePollOnce(-1)` → `epoll_wait(-1)` → 无限阻塞
- 队列中可能有几十条同步消息（生命周期回调、Input 事件、Broadcast 处理）
- 但它们全被屏障挡住，无法被取出

ANR trace 显示主线程在 `nativePollOnce()`——看起来像是消息队列空了，但实际上队列中消息满满。

**诊断方法**

必须通过`adb shell dumpsys activity pkgname` 查看应用进程目标package下 MessageQueue 状态：

```
Message Queue (has barrier):    ← 关键标志！
  Message 0: { when=-8s barrier=42 }               ← 屏障已经存在 8 秒了
  Message 1: { when=-7s what=159 target=H }         ← 被阻塞的同步消息
  Message 2: { when=-6s what=0 target=MyHandler }   ← 被阻塞的同步消息
  ... (更多被阻塞的消息)
```
![img_1.png](img_1.png)

所以在dumpsys的时候如果，队列中有同步屏障，那么就可以直接看到。所以ANR得时候，应该通过`dumpsys activity com.android.chrome > dumppkg.txt`
dumpsys应用进程的队列。
如果在 ANR trace 中看到 `nativePollOnce` 但 `dumpsys` 显示 `has barrier` 加上大量 pending 消息，基本确认是屏障泄漏。

**稳定性关联：** 同步屏障泄漏是最难排查的 Handler 问题之一。它通常出现在自定义 View 动画、反射调用 `ViewRootImpl` 内部方法、或三方 SDK 操作渲染流水线的场景中。修复的核心是**确保 `postSyncBarrier()` 和 `removeSyncBarrier()` 严格配对**，并在异常路径（Fragment detach、Activity finish、异常抛出）中添加清理逻辑。

### 2.5 场景四：WebView / 三方 SDK 的主线程"入侵"

**这是什么**

WebView 和部分三方 SDK 会通过 Handler 向主线程 post 大量任务。由于这些组件的代码不可控，它们占用的主线程时间往往超出预期。

**为什么难以控制**

WebView 的 JavaScript 执行、DOM 操作回调、网络请求回调等都需要切回主线程。一个复杂的 H5 页面可能导致每帧数十条消息 post 到主线程。广告 SDK、推送 SDK、埋点 SDK 同理——它们的代码在主线程执行，但耗时不受 App 开发者控制。

**诊断方法**

通过 `Looper.Printer` 监控可以看到非业务 Handler 的消息：

```
>>>>> Dispatching to Handler (android.webkit.WebViewChromium$...) ...
<<<<< Finished to Handler (android.webkit.WebViewChromium$...) cost=45ms

>>>>> Dispatching to Handler (com.third.party.sdk.internal.Handler) ...
<<<<< Finished to Handler (com.third.party.sdk.internal.Handler) cost=120ms  ← 三方 SDK 耗时
```

**治理方向**

1. **WebView 隔离进程**：使用多进程 WebView（`android:process=":webview"`），WebView 的主线程消息不会影响 App 主线程。
2. **SDK 治理**：通过 ASM/Transform 字节码插桩，拦截三方 SDK 的 `Handler.post()` 调用，统计耗时并上报。对于耗时超标的 SDK 操作，可以包装一层 Handler 进行限流。
3. **消息审计**：建立主线程消息白名单/黑名单机制，对异常来源的消息进行告警。

**稳定性关联：** 在大型 App 中，三方 SDK 贡献的主线程耗时可占 30%-50%。SDK 版本升级后引入新的主线程操作是常见的线上卡顿回归原因。

---

## 3. Handler.post(Runnable) 的隐藏风险

### 3.1 为什么 post(Runnable) 不是"免费"的

`Handler.post(Runnable)` 是 Android 开发中最常用的方法之一，它将一个 Runnable 封装为 Message 发送到消息队列。看似简单，但在高频场景下隐藏着两个风险：**对象池耗尽** 和 **匿名类泄漏**。

### 3.2 每次 post 都会创建 Message

看 `Handler.post()` 的实现：

```java
// frameworks/base/core/java/android/os/Handler.java
public final boolean post(@NonNull Runnable r) {
    return sendMessageDelayed(getPostMessage(r), 0);
}

private static Message getPostMessage(Runnable r) {
    Message m = Message.obtain();  // 从对象池获取（池空则 new）
    m.callback = r;                // Runnable 赋给 Message.callback
    return m;
}
```

每次 `post()` 都调用 `Message.obtain()` 获取一个 Message 对象。对象池 `sPool` 的大小上限是 50：

```java
// frameworks/base/core/java/android/os/Message.java
private static final int MAX_POOL_SIZE = 50;
```

高频 post 场景下（如每帧 post 多条、传感器回调、RecyclerView 滚动中频繁刷新），obtain 速度可能超过 recycle 速度：

```
正常: obtain → dispatch → recycle → 回到池中 → 下次 obtain 复用
高频: obtain obtain obtain ... → 池空 → new Message → GC 压力 → jank
```

**稳定性关联：** 对象池耗尽不会导致崩溃（会退化为 `new Message()`），但大量的短生命周期 Message 对象会增加 GC 频率。在 Android 5.0-7.0（ART 的 Concurrent Copying GC 之前），GC 暂停仍可达数毫秒，高频 GC 会导致掉帧。

### 3.3 匿名 Runnable 的泄漏风险

```java
// ❌ 匿名 Runnable 隐式持有外部类引用
public class ProfileActivity extends AppCompatActivity {

    void scheduleRefresh() {
        mHandler.postDelayed(new Runnable() {  // 匿名内部类
            @Override
            public void run() {
                loadProfile();  // 引用 ProfileActivity.this
            }
        }, 60_000);
    }
}
```

匿名 `Runnable` 是非静态内部类，持有 `ProfileActivity` 的引用。通过 `Message.callback` 字段引用链：

```
MessageQueue → Message → Message.callback (Runnable 匿名类) → ProfileActivity
```

与模式一完全相同的泄漏机制，只是路径从 `Message.target → Handler → Activity` 变为 `Message.callback → Runnable → Activity`。

**修复方案**

```java
// ✅ 使用静态方法引用或确保清理
void scheduleRefresh() {
    mHandler.postDelayed(this::loadProfile, 60_000);
    // 注意：方法引用在 lambda 层面仍然捕获 this！
    // 仍需要在 onDestroy 中清理
}

@Override
protected void onDestroy() {
    super.onDestroy();
    mHandler.removeCallbacksAndMessages(null);
}
```

**稳定性关联：** 由于 Java Lambda / 方法引用在捕获 `this` 时等同于匿名内部类，仅靠语法糖无法消除泄漏。关键在于 **onDestroy 中调用 `removeCallbacksAndMessages(null)`**。
```java
    /**
     * Remove any pending posts of callbacks and sent messages whose
     * <var>obj</var> is <var>token</var>.  If <var>token</var> is null,
     * all callbacks and messages will be removed.
     */
    public final void removeCallbacksAndMessages(@Nullable Object token) {
        mQueue.removeCallbacksAndMessages(this, disallowNullArgumentIfShared(token));
    }
```
---

## 4. HandlerThread 生命周期管理

### 4.1 为什么 HandlerThread 泄漏很危险

`HandlerThread` 是自带 Looper 的工作线程，常用于后台串行任务（如数据库操作、文件写入）。它的危险在于：**如果不显式调用 `quit()` 或 `quitSafely()`，线程将永远存活。**

### 4.2 HandlerThread 的启动与阻塞

```java
// frameworks/base/core/java/android/os/HandlerThread.java
public class HandlerThread extends Thread {

    @Override
    public void run() {
        Looper.prepare();
        synchronized (this) {
            mLooper = Looper.myLooper();
            notifyAll();  // 唤醒等待 getLooper() 的线程
        }
        onLooperPrepared();
        Looper.loop();  // ← 进入无限循环，线程不会退出
    }

    public boolean quit() {
        Looper looper = getLooper();
        if (looper != null) {
            looper.quit();   // 让 Looper.loop() 退出 → 线程 run() 返回 → 线程结束
            return true;
        }
        return false;
    }
}
```

`Looper.loop()` 是一个 `for(;;)` 无限循环。如果没有调用 `quit()`，线程会永远阻塞在 `nativePollOnce()` 中（等待新消息），即使没有任何任务需要执行。

### 4.3 资源消耗

一个"空闲"的 HandlerThread 消耗的资源：

| 资源 | 消耗 | 说明 |
| :--- | :--- | :--- |
| **线程栈** | 默认 1MB | 每个线程分配独立的栈空间 |
| **文件描述符** | 2 个 (epoll fd + eventfd) | Looper 的 Native 层创建 |
| **内核线程** | 1 个 task_struct | 占用内核线程表项 |
| **内存映射** | 若干 VMA | 线程栈、TLS 等 |

单个 HandlerThread 的开销看似不大。但在 Activity 反复创建/销毁的场景中（如屏幕旋转、页面进出），每次 `onCreate()` 创建新的 HandlerThread 且不在 `onDestroy()` 中 quit：

```
第 1 次进入: 创建 HandlerThread-1 (2 FD)
第 2 次进入: 创建 HandlerThread-2 (2 FD)  — HandlerThread-1 仍存活
第 3 次进入: 创建 HandlerThread-3 (2 FD)  — 1、2 仍存活
...
第 500 次: 创建 HandlerThread-500 (2 FD) — 累计 1000 FD、500 线程
→ FD 耗尽 (Linux 默认进程上限 1024) → 新的 Socket/File/Pipe 创建失败
→ 或线程数耗尽 → pthread_create 失败 → OOM/Crash
```

### 4.4 问题代码与修复

```java
// ❌ 每次 onCreate 创建 HandlerThread，但没有 quit
public class UploadActivity extends AppCompatActivity {
    private HandlerThread mWorkerThread;
    private Handler mWorkerHandler;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        mWorkerThread = new HandlerThread("upload-worker");
        mWorkerThread.start();
        mWorkerHandler = new Handler(mWorkerThread.getLooper());
    }

    // 没有 onDestroy 中的清理！→ 线程泄漏
}
```

```java
// ✅ 正确管理 HandlerThread 生命周期
public class UploadActivity extends AppCompatActivity {
    private HandlerThread mWorkerThread;
    private Handler mWorkerHandler;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        mWorkerThread = new HandlerThread("upload-worker");
        mWorkerThread.start();
        mWorkerHandler = new Handler(mWorkerThread.getLooper());
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        // quitSafely: 处理完队列中已有消息后退出（推荐）
        // quit: 立即退出，丢弃队列中的消息
        mWorkerThread.quitSafely();
        mWorkerHandler.removeCallbacksAndMessages(null);
    }
}
```

`quit()` 与 `quitSafely()` 的区别在源码中：

```java
// frameworks/base/core/java/android/os/MessageQueue.java
void quit(boolean safe) {
    synchronized (this) {
        if (mQuitting) return;
        mQuitting = true;
        if (safe) {
            removeAllFutureMessagesLocked();  // 只移除 when > now 的消息
        } else {
            removeAllMessagesLocked();        // 移除所有消息
        }
        nativeWake(mPtr);  // 唤醒 nativePollOnce → next() 返回 null → loop() 退出
    }
}
```

`quitSafely()` 会让已经到期的消息正常处理完毕再退出，是更安全的选择。

**稳定性关联：** HandlerThread 泄漏在长时间运行的 App 中（如社交、音乐、导航类应用）尤其危险。用户可能一天内切换页面数百次，FD 和线程资源悄然耗尽。诊断方法：通过 `/proc/<pid>/fd` 统计 FD 数量，或 `adb shell ps -T -p <pid>` 查看线程数。

---

## 5. 风险速查表

以下是 Handler 相关稳定性问题的完整对照表，用于在出现问题时快速定位类型和排查方向。

### 5.1 问题类型、日志特征与排查方向

| 问题类型 | 日志/Trace 特征 | 诊断方法 | 修复方向 |
| :--- | :--- | :--- | :--- |
| **非静态内部类 Handler 泄漏** | LeakCanary: `MessageQueue → Message → Handler → Activity`; hprof 中 Activity retained count > 1 | LeakCanary / MAT / Android Studio Profiler Memory | 静态内部类 + WeakReference + onDestroy removeCallbacksAndMessages |
| **Message.obj 大对象** | hprof 分析发现 Message.obj 持有 Bitmap/List; Retained size 异常大 | MAT 按 Retained Heap 排序查找 Message 实例 | 传递标识符代替大对象; WeakReference 包装; 缩短延迟时间 |
| **IdleHandler 泄漏** | hprof 中 `MessageQueue.mIdleHandlers` 列表异常增长 | MAT 查看 `mIdleHandlers` 的 size; 逐条检查引用链 | queueIdle 返回 false（一次性）; onDestroy 中 removeIdleHandler |
| **主线程耗时操作** | ANR trace 主线程堆栈在业务代码 (I/O / DB / 网络); StrictMode 告警 | Systrace/Perfetto; ANR trace 分析; StrictMode | 耗时操作移至后台线程 |
| **高频 post 消息风暴** | Systrace 中主线程密集短消息; CPU 使用率偏高; Printer 日志显示高频 Handler | Looper.Printer 统计消息频率; Systrace 消息密度 | 消息合并/采样; 降低 post 频率 |
| **同步屏障泄漏** | ANR trace: `nativePollOnce` 但 dumpsys 显示 `has barrier` + 大量 pending 消息 | `dumpsys activity` 查看 MessageQueue 状态 | 确保 postSyncBarrier/removeSyncBarrier 配对; 异常路径清理 |
| **HandlerThread 泄漏** | `/proc/<pid>/fd` FD 数量持续增长; `ps -T` 线程数持续增长; 最终 OOM 或 `Too many open files` | `adb shell ls /proc/<pid>/fd \| wc -l`; Thread dump | onDestroy 中 quitSafely(); 复用全局 HandlerThread |
| **Handler.post(Runnable) 匿名类泄漏** | LeakCanary: `Message.callback → Runnable → Activity` | LeakCanary | onDestroy removeCallbacksAndMessages; 避免长延迟 post |
| **WebView/SDK 主线程入侵** | Looper.Printer 显示非业务 Handler 消息耗时高 | Printer 监控 + 消息来源分类 | WebView 多进程隔离; SDK 字节码插桩监控 |

### 5.2 快速诊断流程

```
线上问题出现
    ↓
判断类型：OOM? ANR? 卡顿? FD 耗尽?
    ↓
┌── OOM ──────────────────────────────────────────────┐
│ 1. 获取 hprof                                       │
│ 2. MAT: Leak Suspects → Dominator Tree              │
│ 3. 搜索 Activity retained > 1 或 Message 大对象      │
│ 4. 定位引用链 → 对应上表的泄漏模式                    │
└─────────────────────────────────────────────────────┘
    ↓
┌── ANR ──────────────────────────────────────────────┐
│ 1. 获取 traces.txt                                   │
│ 2. 看主线程堆栈:                                     │
│    - 在业务代码 → 场景一（耗时操作）                   │
│    - 在 nativePollOnce → 检查 dumpsys:               │
│      · has barrier → 场景三（屏障泄漏）               │
│      · 无消息 → 可能被其他进程 CPU 抢占               │
│      · 有消息但无 barrier → 可能是 binder 阻塞等      │
└─────────────────────────────────────────────────────┘
    ↓
┌── 卡顿 ─────────────────────────────────────────────┐
│ 1. Systrace/Perfetto 分析主线程消息                   │
│ 2. 单条慢消息 → 场景一                               │
│ 3. 密集短消息 → 场景二                               │
│ 4. 非业务 Handler → 场景四                            │
└─────────────────────────────────────────────────────┘
    ↓
┌── FD/线程耗尽 ──────────────────────────────────────┐
│ 1. 统计 FD 数: /proc/<pid>/fd                        │
│ 2. 统计线程数: /proc/<pid>/task                      │
│ 3. 增长趋势 → 定位创建源:                            │
│    - Thread dump 搜索 HandlerThread                  │
│    - 按名称匹配创建位置                              │
└─────────────────────────────────────────────────────┘
```

---

## 6. 稳定性实战案例

### 案例一：HandlerThread 泄漏导致线上 FD 耗尽 Crash

**现象**

某社交 App 版本更新后，线上出现大量 Crash，错误类型为 `java.io.IOException: Too many open files` 和 `java.lang.OutOfMemoryError: pthread_create`。Crash 集中在使用 App 2 小时以上的用户群体中，且与页面切换次数正相关。

Crash 堆栈：

```
java.lang.OutOfMemoryError: pthread_create (1040KB stack) failed: Try again
  at java.lang.Thread.nativeCreate(Native Method)
  at java.lang.Thread.start(Thread.java:733)
  at android.os.HandlerThread.start(HandlerThread.java)
  at com.example.app.chat.ChatFragment.initWorker(ChatFragment.java:89)
```

以及：

```
android.system.ErrnoException: socket failed: EMFILE (Too many open files)
  at libcore.io.Linux.socket(Native Method)
  at com.android.okhttp.internal.Platform.connectSocket(Platform.java:location)
```

**分析**

`EMFILE` 和 `pthread_create failed` 同时出现，指向 FD 和线程资源耗尽。通过复现环境执行监控：

```bash
# 监控 FD 数量变化
adb shell "while true; do ls /proc/$(pidof com.example.app)/fd | wc -l; sleep 5; done"
# 结果: 每次进出 ChatFragment，FD 数 +2，线程数 +1
# 2 小时后: FD 数 > 900 (接近默认上限 1024)
```

Thread dump 显示大量同名线程：

```
"chat-db-worker" prio=5 tid=102 Native
  at android.os.MessageQueue.nativePollOnce(Native method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  at android.os.Looper.loop(Looper.java:206)
  at android.os.HandlerThread.run(HandlerThread.java:67)

"chat-db-worker" prio=5 tid=103 Native    ← 同名！不同 tid
  at android.os.MessageQueue.nativePollOnce(Native method)
  ...

"chat-db-worker" prio=5 tid=104 Native    ← 又一个！
  ...

(共计 200+ 个 "chat-db-worker" 线程)
```

**根因**

定位到 `ChatFragment.initWorker()`:

```java
// 问题代码
public class ChatFragment extends Fragment {
    private HandlerThread mDbWorker;
    private Handler mDbHandler;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        mDbWorker = new HandlerThread("chat-db-worker");
        mDbWorker.start();  // 每次 onCreate 创建新线程
        mDbHandler = new Handler(mDbWorker.getLooper());
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        // 原本有 quit 调用，但被 guard 条件跳过了
        if (mDbHandler != null && mDbHandler.hasMessages(MSG_PENDING_WRITE)) {
            // 如果还有待写入消息，不 quit（等消息处理完）
            // ← BUG: 没有延迟 quit 机制，直接跳过了！线程永远不会退出
            return;
        }
        mDbWorker.quitSafely();
    }
}
```

问题在于 `onDestroy` 中的 guard 条件：如果有待写入的消息（几乎每次退出聊天页面时都有），`quitSafely()` 就被跳过了。开发者的意图是"等消息处理完再退出"，但没有实现对应的延迟退出逻辑。

**修复**

```java
@Override
public void onDestroy() {
    super.onDestroy();
    if (mDbWorker != null) {
        // quitSafely 已经保证了当前到期消息会处理完毕后再退出
        mDbWorker.quitSafely();
    }
    if (mDbHandler != null) {
        mDbHandler.removeCallbacksAndMessages(null);
    }
}
```

`quitSafely()` 的语义就是"处理完已到期的消息，丢弃未到期的延迟消息，然后退出"——不需要自己实现 guard 逻辑。

**后续防御措施**

1. **FD 监控**：App 启动后定期（每 5 分钟）采集 `/proc/self/fd` 的 FD 数量，超过阈值（如 800）上报告警。
2. **线程审计**：通过 `Thread.getAllStackTraces()` 定期审计线程数量和名称，相同名称的线程数 > 3 触发告警。
3. **全局 HandlerThread 复用**：提供 `AppExecutors.serialIO()` 等全局共享的 HandlerThread，避免各页面各自创建。

```java
// 全局 HandlerThread 管理
public final class AppWorkers {
    private static volatile HandlerThread sDbThread;

    public static Handler dbHandler() {
        if (sDbThread == null) {
            synchronized (AppWorkers.class) {
                if (sDbThread == null) {
                    sDbThread = new HandlerThread("app-db-worker");
                    sDbThread.start();
                }
            }
        }
        return new Handler(sDbThread.getLooper());
    }
}
```

---

### 案例二：高频 post + 匿名 Runnable 导致严重卡顿与内存抖动

**现象**

某电商 App 的商品详情页在快速滑动时出现严重卡顿，掉帧率达 40%+。同时线上 OOM 率在进入该页面后明显上升。用户反馈："滑动商品图片时非常卡，有时候直接闪退。"

Perfetto 分析显示主线程特征：

```
主线程时间线:
  ┌─1ms─┐┌─2ms─┐┌─1ms─┐┌─1ms─┐┌─1ms─┐┌─2ms─┐┌─1ms─┐ ...
  │post ││post ││post ││post ││post ││post ││post │ ... × 120/frame
  └─────┘└─────┘└─────┘└─────┘└─────┘└─────┘└─────┘

  每帧 120+ 条 Handler 消息，来自同一个 Handler
  单条消息耗时 1-2ms，但总和 > 16ms → 掉帧
```

同时 Memory Profiler 显示 GC 活动频繁：

```
GC: Alloc 2.1MB → Free 1.8MB  (间隔 200ms)
GC: Alloc 2.3MB → Free 2.0MB  (间隔 180ms)
GC: Alloc 1.9MB → Free 1.6MB  (间隔 210ms)
```

**分析**

通过 `Looper.Printer` 拦截消息，发现大量消息来自图片加载组件：

```
>>>>> Dispatching to Handler (com.example.app.image.ImageLoadHandler) callback=...$$Lambda$23
<<<<< Finished to Handler (...ImageLoadHandler...) cost=1ms

>>>>> Dispatching to Handler (com.example.app.image.ImageLoadHandler) callback=...$$Lambda$24
<<<<< Finished to Handler (...ImageLoadHandler...) cost=2ms
... (每秒 300+ 条)
```

**根因**

商品详情页有一个自定义的图片预加载管理器，在 ViewPager 滑动监听中高频 post：

```java
// 问题代码
public class ImagePreloader implements ViewPager2.OnPageScrolledListener {
    private final Handler mMainHandler = new Handler(Looper.getMainLooper());

    @Override
    public void onPageScrolled(int position, float offset, int offsetPixels) {
        // ViewPager2 滑动时每帧回调多次
        // 每次回调都 post 一个 Runnable 到主线程
        for (int i = -2; i <= 2; i++) {
            final int targetPos = position + i;
            mMainHandler.post(new Runnable() {  // ← 匿名内部类
                @Override
                public void run() {
                    updateImagePriority(targetPos, offset);
                }
            });
        }
    }
}
```

问题叠加：

1. **高频 post**：`onPageScrolled` 每帧回调 2-3 次，每次 post 5 条消息 → 每帧 10-15 条 → 每秒 180+ 条。
2. **匿名 Runnable**：每次 `new Runnable()` 创建新对象 → 每秒 180+ 个短命对象 → 对象池耗尽 → 额外 180+ 个 `new Message()` → GC 压力。
3. **不必要的重复工作**：同一个 `targetPos` 在同一帧内被 post 多次，实际上只需要最后一次的结果。

**修复**

```java
// ✅ 合并 + 去重 + 避免匿名类
public class ImagePreloader implements ViewPager2.OnPageScrolledListener {
    private final Handler mMainHandler = new Handler(Looper.getMainLooper());
    private volatile int mPendingPosition = -1;
    private volatile float mPendingOffset = 0f;
    private boolean mUpdateScheduled = false;

    private final Runnable mUpdateRunnable = this::doUpdate;  // 复用同一个 Runnable

    @Override
    public void onPageScrolled(int position, float offset, int offsetPixels) {
        mPendingPosition = position;
        mPendingOffset = offset;
        if (!mUpdateScheduled) {
            mUpdateScheduled = true;
            mMainHandler.post(mUpdateRunnable);  // 一帧只 post 一次
        }
    }

    private void doUpdate() {
        mUpdateScheduled = false;
        int pos = mPendingPosition;
        float offset = mPendingOffset;
        for (int i = -2; i <= 2; i++) {
            updateImagePriority(pos + i, offset);
        }
    }
}
```

关键优化：

1. **消息合并**：通过 `mUpdateScheduled` 标志实现"一帧最多一条消息"，消息数量从 180+/s 降到 ≤60/s。
2. **Runnable 复用**：`mUpdateRunnable` 是成员变量，不是匿名类，避免重复创建对象。
3. **最新值覆盖**：多次 `onPageScrolled` 回调只保留最新的 position 和 offset，避免重复计算。

**效果**

| 指标 | 修复前 | 修复后 |
| :--- | :--- | :--- |
| 消息频率 | 180+/s | ≤60/s |
| 掉帧率 | 40%+ | <5% |
| GC 频率 | 每 200ms | 每 2s+ |
| Message 对象创建 | 180+/s (池外 new) | ≤60/s (池内复用) |
| 商详页 OOM 率 | 0.3% | 0.02% |

**后续治理**

1. **消息频率监控**：在 `Looper.Printer` 监控中增加"同一 Handler 消息频率"维度，超过 100/s 触发告警。
2. **Lint 规则**：检测在 `onPageScrolled`、`onScrolled`、`onSensorChanged` 等高频回调中直接 `Handler.post()` 的代码模式。
3. **团队编码规范**：所有高频回调场景必须使用"合并 + 去重 + 复用"三原则。

---

## 总结

本文梳理了 Handler 消息机制的五大类稳定性风险：

| 风险类型 | 核心机制 | 最终表现 |
| :--- | :--- | :--- |
| **内存泄漏（三种模式）** | Message 引用链阻止 GC 回收 | OOM Crash |
| **消息堆积与卡顿（四种场景）** | 单线程串行处理，一条慢全局慢 | 掉帧 / ANR |
| **post(Runnable) 隐藏风险** | 高频 post → 对象池耗尽 + 匿名类引用链 | GC 抖动 + 泄漏 |
| **HandlerThread 泄漏** | 忘记 quit → 线程永不退出 → FD 和线程累积 | FD 耗尽 / 线程耗尽 / OOM |
| **三方 SDK 主线程入侵** | 不可控代码占用主线程时间片 | 卡顿 / ANR |

**对于稳定性架构师，关键认知是：**

1. Handler 的引用链（`MessageQueue → Message → Handler/Runnable → 外部对象`）是内存泄漏的根源。**断链的时机在 `onDestroy`，断链的手段是 `removeCallbacksAndMessages(null)`。**
2. 主线程 Looper 是单点瓶颈。**任何试图在主线程做"哪怕一点点"耗时操作的代码，都在为整个应用的流畅性埋雷。**
3. HandlerThread 是重量级资源。**不要按页面创建，要全局复用。不要忘记 quit，要绑定到生命周期。**
4. 高频 post 是隐形杀手。**合并、采样、复用**——三个词概括高频消息场景的治理方向。
5. 诊断工具是必需品。**LeakCanary 查泄漏、Systrace/Perfetto 查卡顿、Looper.Printer 查消息、dumpsys 查屏障、/proc 查资源。**

下一篇 [08-消息机制诊断工具与监控体系](08-消息机制诊断工具与监控体系.md) 将深入这些诊断工具的原理与实战用法。
