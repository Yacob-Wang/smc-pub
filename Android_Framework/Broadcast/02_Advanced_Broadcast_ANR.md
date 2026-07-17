# Broadcast ANR 进阶篇：BroadcastQueue 源码深度追踪与完整分发流程

## 📋 概述

在基础篇中我们了解了广播的分类体系和超时机制。本篇将深入 Android Framework 源码，完整追踪 `BroadcastQueue` 的广播分发流程，包括进程拉起、Binder 通信、超时检测的精确时机，以及静态注册与动态注册的本质差异。

---

## 一、 BroadcastQueue 的完整架构

### 1.1 核心数据结构

```java
// BroadcastQueue.java
public final class BroadcastQueue {
    // 前台和后台广播队列（在 AMS 中创建）
    final String mQueueName;  // "foreground" 或 "background"
    
    // 三个核心队列
    final ArrayList<BroadcastRecord> mParallelBroadcasts = new ArrayList<>();  // 普通广播
    final ArrayList<BroadcastRecord> mOrderedBroadcasts = new ArrayList<>();   // 有序广播
    final ArrayList<BroadcastRecord> mPendingBroadcast = new ArrayList<>();    // 待分发（当前正在处理）
    
    // 超时相关
    static final int BROADCAST_FG_TIMEOUT = 10 * 1000;  // 10秒
    static final int BROADCAST_BG_TIMEOUT = 60 * 1000;  // 60秒
    static final int BROADCAST_TIMEOUT_MSG = 200;
    
    // Handler 用于超时检测
    final BroadcastHandler mHandler;
    
    // 当前正在处理的广播（用于超时检测）
    BroadcastRecord mPendingBroadcast = null;
    long mPendingBroadcastTimeoutTime;  // 超时时间点
}
```

### 1.2 BroadcastRecord：广播记录的核心字段

```java
// BroadcastRecord.java
final class BroadcastRecord {
    final Intent intent;           // 广播 Intent
    final ComponentName targetComp; // 目标组件（有序广播的最终接收者）
    final List receivers;          // 接收者列表（有序广播已排序）
    int nextReceiver;              // 下一个要分发的 Receiver 索引
    final long enqueueClockTime;   // 入队时间
    long dispatchTime;             // 开始分发时间
    long receiverTime;             // 当前 Receiver 开始接收时间
    long finishTime;               // 完成时间
    
    // 进程信息
    ProcessRecord curApp;          // 当前正在处理的进程
    int curReceiver;               // 当前 Receiver 的索引
    
    // 状态标志
    boolean ordered;               // 是否为有序广播
    boolean sticky;                // 是否为粘性广播
    int state;                     // 状态：IDLE, APP_RECEIVE, DELIVERED 等
}
```

---

## 二、 processNextBroadcast：广播分发的核心流程

`processNextBroadcast` 是 `BroadcastQueue` 的核心方法，负责从队列中取出广播并分发给 Receiver。该方法会被循环调用，直到所有广播分发完毕。

### 2.1 完整执行流程（简化版源码）

```java
// BroadcastQueue.java
final void processNextBroadcast(boolean fromMsg) {
    synchronized (mService) {
        BroadcastRecord r;
        
        // ========== 阶段 1：选择下一个要处理的广播 ==========
        // 1.1 优先处理普通广播（并发分发，不阻塞）
        while (mParallelBroadcasts.size() > 0) {
            r = mParallelBroadcasts.remove(0);
            r.dispatchTime = SystemClock.uptimeMillis();
            r.dispatchClockTime = System.currentTimeMillis();
            
            // 并发分发给所有 Receiver（不等待）
            for (int i = 0; i < r.receivers.size(); i++) {
                Object target = r.receivers.get(i);
                deliverToRegisteredReceiverLocked(r, target, false, i);
            }
            addToHistory(r);
        }
        
        // 1.2 处理有序广播（串行分发，需要等待）
        if (mOrderedBroadcasts.size() == 0) {
            return;  // 没有待处理的广播
        }
        
        // 如果当前有正在处理的广播，等待它完成
        if (mPendingBroadcast != null) {
            // 检查是否超时
            if (SystemClock.uptimeMillis() > mPendingBroadcastTimeoutTime) {
                broadcastTimeoutLocked(false);  // 触发 ANR
                return;
            }
            return;  // 等待当前广播完成
        }
        
        // 取出下一个有序广播
        r = mOrderedBroadcasts.get(0);
        mOrderedBroadcasts.remove(0);
        mPendingBroadcast = r;
        
        // ========== 阶段 2：分发当前 Receiver ==========
        // 2.1 检查是否所有 Receiver 都已处理完
        if (r.nextReceiver >= r.receivers.size()) {
            // 所有 Receiver 处理完毕，调用最终 Receiver（如果有）
            if (r.resultTo != null) {
                try {
                    r.resultTo.send(r.resultCode, r.resultData, r.resultExtras);
                } catch (RemoteException e) {
                    // 忽略
                }
            }
            addToHistory(r);
            mPendingBroadcast = null;
            // 继续处理下一个广播
            processNextBroadcast(false);
            return;
        }
        
        // 2.2 获取下一个 Receiver
        Object nextReceiver = r.receivers.get(r.nextReceiver);
        r.nextReceiver++;
        
        // 2.3 设置超时计时器（关键：从这里开始计时）
        r.receiverTime = SystemClock.uptimeMillis();
        long timeoutTime = r.receiverTime;
        if (r.curApp != null && r.curApp.processState <= ActivityManager.PROCESS_STATE_TOP) {
            timeoutTime += BROADCAST_FG_TIMEOUT;  // 前台 10s
        } else {
            timeoutTime += BROADCAST_BG_TIMEOUT;  // 后台 60s
        }
        mPendingBroadcastTimeoutTime = timeoutTime;
        setBroadcastTimeoutLocked(timeoutTime);
        
        // 2.4 分发广播
        deliverToRegisteredReceiverLocked(r, nextReceiver, r.ordered, r.nextReceiver - 1);
    }
}
```

**关键点**：
1. **普通广播**：立即并发分发给所有 Receiver，不设置超时（除非进程拉起失败）
2. **有序广播**：串行分发，每个 Receiver 分发前都会设置超时计时器
3. **超时计时起点**：`r.receiverTime = SystemClock.uptimeMillis()`，即分发前的那一刻

---

## 三、 deliverToRegisteredReceiverLocked：分发机制的核心差异

该方法负责将广播实际分发给 Receiver，**静态注册和动态注册的分发路径完全不同**。

### 3.1 方法签名与分支判断

```java
// BroadcastQueue.java
private void deliverToRegisteredReceiverLocked(BroadcastRecord r,
        Object target, boolean ordered, int recIdx) {
    
    // target 可能是两种类型：
    // 1. BroadcastFilter：动态注册的 Receiver
    // 2. ResolveInfo：静态注册的 Receiver（在 Manifest 中声明）
    
    if (target instanceof BroadcastFilter) {
        // ========== 动态注册：直接分发 ==========
        BroadcastFilter filter = (BroadcastFilter) target;
        deliverToRegisteredReceiverLocked(r, filter, ordered, recIdx);
    } else {
        // ========== 静态注册：需要拉起进程 ==========
        ResolveInfo info = (ResolveInfo) target;
        deliverToRegisteredReceiverLocked(r, info, ordered, recIdx);
    }
}
```

### 3.2 动态注册的分发路径

```java
// BroadcastQueue.java
private void deliverToRegisteredReceiverLocked(BroadcastRecord r,
        BroadcastFilter filter, boolean ordered, int recIdx) {
    
    // 1. 检查进程是否存活
    ProcessRecord app = filter.receiverList.app;
    if (app == null || app.thread == null) {
        // 进程已死亡，跳过
        r.receivers.set(recIdx, null);
        return;
    }
    
    // 2. 检查进程是否处于 cached 状态（Android 14+）
    if (app.processState >= ActivityManager.PROCESS_STATE_CACHED_ACTIVITY) {
        if (filter.receiverList.receivers.get(0) instanceof BroadcastFilter) {
            // Context 注册的 Receiver：队列化延迟分发
            queueBroadcastForCachedApp(r, filter);
            return;
        }
        // Manifest 注册的 Receiver：立即唤醒
    }
    
    // 3. 直接通过 Binder 调用应用进程
    try {
        r.curApp = app;
        r.curReceiver = filter;
        r.state = BroadcastRecord.APP_RECEIVE;
        
        // 通过 ApplicationThread 分发（跨进程调用）
        app.thread.scheduleReceiver(
            new Intent(r.intent),
            filter.receiverList.receivers.get(0),
            r.resultCode, r.resultData, r.resultExtras,
            r.ordered, r.sticky, r.userId);
        
        // 注意：这里不会等待 onReceive 执行完，方法立即返回
        // 应用进程会在 onReceive 执行完后通过 Binder 回调通知系统
        
    } catch (RemoteException e) {
        // Binder 调用失败，标记为跳过
        r.receivers.set(recIdx, null);
    }
}
```

**关键点**：
- 动态注册的 Receiver 如果进程已存在，**立即通过 Binder 分发**
- 系统不会等待 `onReceive` 执行完，方法立即返回
- 应用进程执行完 `onReceive` 后，会通过 `finishReceiver()` 回调通知系统

### 3.3 静态注册的分发路径：进程拉起机制

```java
// BroadcastQueue.java
private void deliverToRegisteredReceiverLocked(BroadcastRecord r,
        ResolveInfo info, boolean ordered, int recIdx) {
    
    // 1. 获取目标进程信息
    String targetProcess = info.activityInfo.processName;
    if (targetProcess == null) {
        targetProcess = info.activityInfo.packageName;
    }
    
    // 2. 查找进程是否已存在
    ProcessRecord app = mService.getProcessRecordLocked(
        targetProcess, info.activityInfo.applicationInfo.uid, true);
    
    if (app != null && app.thread != null) {
        // 进程已存在，直接分发（同动态注册）
        app.thread.scheduleReceiver(...);
        return;
    }
    
    // 3. 进程不存在，需要拉起
    // 3.1 检查进程是否正在启动中
    if (mService.mPendingStarts.containsKey(targetProcess)) {
        // 进程正在启动，将广播加入待分发队列
        mService.mPendingStarts.get(targetProcess).add(r);
        return;
    }
    
    // 3.2 启动新进程
    ProcessRecord newApp = mService.startProcessLocked(
        targetProcess, info.activityInfo.applicationInfo,
        true, 0, "broadcast", null, false, false, false);
    
    if (newApp == null) {
        // 启动失败，跳过该 Receiver
        r.receivers.set(recIdx, null);
        return;
    }
    
    // 3.3 将广播加入待分发队列（进程启动完成后分发）
    if (!mService.mPendingStarts.containsKey(targetProcess)) {
        mService.mPendingStarts.put(targetProcess, new ArrayList<>());
    }
    mService.mPendingStarts.get(targetProcess).add(r);
    
    // 注意：超时计时器已经设置，如果进程启动时间过长，可能触发 ANR
}
```

**关键点**：
- 静态注册的 Receiver 如果进程不存在，**必须先拉起进程**
- 进程拉起是异步的，广播会被加入 `mPendingStarts` 队列
- **超时计时器在进程拉起前就已经设置**，如果进程启动时间过长（超过 10s/60s），会触发 ANR
- 进程启动完成后，AMS 会从 `mPendingStarts` 中取出待分发的广播并分发

### 3.4 进程启动完成后的回调

```java
// ActivityManagerService.java
final void attachApplicationLocked(IApplicationThread thread, long startTime) {
    ProcessRecord app = getProcessRecordLocked(processName, pid, true);
    
    // ... 进程绑定逻辑 ...
    
    // 处理待分发的广播
    if (app.pendingStarts.size() > 0) {
        for (BroadcastRecord r : app.pendingStarts) {
            // 分发广播
            mFgBroadcastQueue.deliverToRegisteredReceiverLocked(r, ...);
        }
        app.pendingStarts.clear();
    }
}
```

---

## 四、 超时检测的精确机制

### 4.1 setBroadcastTimeoutLocked：设置超时闹钟

```java
// BroadcastQueue.java
final void setBroadcastTimeoutLocked(long timeoutTime) {
    if (mPendingBroadcast == null) {
        return;
    }
    
    // 移除之前的超时消息（如果有）
    mHandler.removeMessages(BROADCAST_TIMEOUT_MSG, this);
    
    // 发送延迟消息
    Message msg = mHandler.obtainMessage(BROADCAST_TIMEOUT_MSG, this);
    mHandler.sendMessageAtTime(msg, timeoutTime);
}
```

### 4.2 broadcastTimeoutLocked：超时检测与 ANR 触发

```java
// BroadcastQueue.java
final void broadcastTimeoutLocked(boolean fromMsg) {
    if (mPendingBroadcast == null) {
        return;
    }
    
    BroadcastRecord r = mPendingBroadcast;
    long now = SystemClock.uptimeMillis();
    
    // 1. 检查是否真的超时（排除 Handler 调度延迟）
    if (fromMsg) {
        // 从 Handler 消息触发
        if (now < mPendingBroadcastTimeoutTime) {
            // 还没到超时时间，重新设置（可能是 Handler 提前触发了）
            setBroadcastTimeoutLocked(now);
            return;
        }
    }
    
    // 2. 确认超时，收集 ANR 信息
    String anrMessage = null;
    if (r.nextReceiver > 0) {
        Object curReceiver = r.receivers.get(r.nextReceiver - 1);
        anrMessage = "Broadcast of " + r.intent.toString();
        
        if (curReceiver instanceof BroadcastFilter) {
            BroadcastFilter bf = (BroadcastFilter) curReceiver;
            anrMessage += " to " + bf.receiverList.packageName 
                + "/" + bf.receiverList.app.processName;
        } else {
            ResolveInfo ri = (ResolveInfo) curReceiver;
            anrMessage += " to " + ri.activityInfo.packageName 
                + "/" + ri.activityInfo.name;
        }
    } else {
        anrMessage = "Broadcast of " + r.intent.toString();
    }
    
    // 3. 调用 AMS 的 ANR 处理
    if (r.curApp != null) {
        mService.mAnrHelper.appNotResponding(r.curApp, anrMessage);
    }
    
    // 4. 清理当前广播（不再继续分发）
    finishReceiverLocked(r, r.resultCode, r.resultData, r.resultExtras,
        r.resultAbort, false);
    scheduleBroadcastsLocked();
}
```

**关键点**：
- 超时检测通过 `Handler.sendMessageAtTime` 实现，可能存在**几毫秒的调度延迟**
- 系统会二次确认是否真的超时（`now < mPendingBroadcastTimeoutTime`）
- ANR 信息包含：Intent、目标包名、进程名、Receiver 名称

### 4.3 cancelBroadcastTimeoutLocked：清除超时闹钟

```java
// BroadcastQueue.java
final void cancelBroadcastTimeoutLocked() {
    if (mPendingBroadcast == null) {
        return;
    }
    
    // 移除超时消息
    mHandler.removeMessages(BROADCAST_TIMEOUT_MSG, this);
}
```

**调用时机**：
1. Receiver 执行完毕（`finishReceiverLocked`）
2. 有序广播被中断（`abortBroadcast`）
3. 广播被取消

---

## 五、 finishReceiver：Receiver 执行完成的回调

应用进程执行完 `onReceive` 后，会通过 Binder 调用 `finishReceiver` 通知系统。

### 5.1 应用进程侧：onReceive 执行完成

```java
// ActivityThread.java
private void handleReceiver(ReceiverData data) {
    // 1. 创建 Receiver 实例
    BroadcastReceiver receiver = (BroadcastReceiver) cl.loadClass(data.info.name)
        .newInstance();
    
    // 2. 设置 Context
    ContextImpl context = (ContextImpl) data.context;
    context.setOuterContext(receiver);
    
    // 3. 执行 onReceive
    receiver.onReceive(context.getReceiverRestrictedContext(), data.intent);
    
    // 4. 通知系统执行完成
    if (receiver.getPendingResult() != null) {
        receiver.getPendingResult().finish();
    }
}
```

### 5.2 系统进程侧：finishReceiverLocked

```java
// BroadcastQueue.java
public void finishReceiver(IBinder who, int resultCode, String resultData,
        Bundle resultExtras, boolean resultAbort, boolean async) {
    
    synchronized (mService) {
        BroadcastRecord r = mPendingBroadcast;
        if (r == null || r.curReceiver.asBinder() != who) {
            return;  // 不是当前正在处理的广播
        }
        
        // 1. 保存结果（有序广播）
        if (r.ordered) {
            r.resultCode = resultCode;
            r.resultData = resultData;
            r.resultExtras = resultExtras;
            if (resultAbort) {
                r.resultAbort = true;
            }
        }
        
        // 2. 清除超时计时器
        cancelBroadcastTimeoutLocked();
        
        // 3. 清理当前 Receiver
        r.curApp = null;
        r.curReceiver = null;
        r.state = BroadcastRecord.IDLE;
        
        // 4. 继续处理下一个 Receiver（有序广播）
        if (r.ordered && !r.resultAbort && r.nextReceiver < r.receivers.size()) {
            processNextBroadcast(false);
        } else {
            // 所有 Receiver 处理完毕
            addToHistory(r);
            mPendingBroadcast = null;
            processNextBroadcast(false);
        }
    }
}
```

---

## 六、 goAsync() 的底层实现机制

`goAsync()` 允许 Receiver 在子线程中异步处理广播，但**系统依然在计时**。

### 6.1 PendingResult 的实现

```java
// BroadcastReceiver.java
public final class BroadcastReceiver {
    private PendingResult mPendingResult;
    
    public final PendingResult goAsync() {
        PendingResult res = mPendingResult;
        mPendingResult = null;  // 防止重复调用
        return res;
    }
}

// BroadcastReceiver.PendingResult
public static final class PendingResult {
    final BroadcastRecord mBroadcastRecord;
    final IBinder mToken;
    boolean mFinished = false;
    
    public final void finish() {
        if (mFinished) {
            throw new IllegalStateException("Broadcast already finished");
        }
        mFinished = true;
        
        // 通过 Binder 通知系统
        try {
            ActivityManager.getService().finishReceiver(
                mToken, mResultCode, mResultData, mResultExtras,
                mResultAbort, false);
        } catch (RemoteException e) {
            // 忽略
        }
    }
}
```

### 6.2 goAsync() 的超时机制

**关键点**：
- `goAsync()` **不会延长超时时间**，系统依然使用 10s/60s 的阈值
- 如果子线程执行时间超过阈值，仍会触发 ANR
- `finish()` 必须在所有代码路径（包括异常路径）中调用

---

## 七、 有序广播的完整分发流程

有序广播的串行分发是 Broadcast ANR 的重灾区，理解其完整流程至关重要。

### 7.1 有序广播的排序

```java
// ActivityManagerService.java
private List<Object> collectReceiverComponents(Intent intent, String resolvedType,
        int callingUid, int[] users) {
    
    List<ResolveInfo> receivers = new ArrayList<>();
    
    // 1. 收集所有匹配的 Receiver（静态注册）
    List<ResolveInfo> newReceivers = queryIntentReceivers(intent, resolvedType, ...);
    receivers.addAll(newReceivers);
    
    // 2. 收集所有匹配的 Receiver（动态注册）
    List<BroadcastFilter> registeredReceivers = mReceiverResolver.queryIntent(...);
    for (BroadcastFilter filter : registeredReceivers) {
        // 转换为 ResolveInfo 格式
        receivers.add(createReceiverResolveInfo(filter));
    }
    
    // 3. 按优先级排序
    Collections.sort(receivers, new Comparator<ResolveInfo>() {
        @Override
        public int compare(ResolveInfo a, ResolveInfo b) {
            int pa = a.priority;
            int pb = b.priority;
            if (pa != pb) {
                return pb - pa;  // 优先级高的在前
            }
            // 相同优先级按注册顺序
            return a.registerOrder - b.registerOrder;
        }
    });
    
    return receivers;
}
```

### 7.2 有序广播的分发循环

```java
// BroadcastQueue.java
// processNextBroadcast 的简化流程（有序广播部分）

while (true) {
    // 1. 检查是否所有 Receiver 都已处理
    if (r.nextReceiver >= r.receivers.size()) {
        // 完成
        break;
    }
    
    // 2. 获取下一个 Receiver
    Object nextReceiver = r.receivers.get(r.nextReceiver);
    r.nextReceiver++;
    
    // 3. 设置超时计时器（每个 Receiver 都会重置）
    setBroadcastTimeoutLocked(now + timeout);
    
    // 4. 分发广播
    deliverToRegisteredReceiverLocked(r, nextReceiver, true, r.nextReceiver - 1);
    
    // 5. 等待 Receiver 执行完成（通过 finishReceiver 回调）
    // 注意：这里会 return，等待 finishReceiver 再次调用 processNextBroadcast
    return;
}

// finishReceiver 中会再次调用 processNextBroadcast，形成循环
```

**关键点**：
- 每个 Receiver 分发前都会**重置超时计时器**
- 但如果**整个有序广播链条的总时间**超过阈值，仍可能触发 ANR
- 如果某个 Receiver 调用 `abortBroadcast()`，后续 Receiver 不会收到广播

---

## 八、 总结

1. **分发流程**：`processNextBroadcast` → `deliverToRegisteredReceiverLocked` → 应用进程 `onReceive` → `finishReceiver` → 循环
2. **超时计时**：每个有序广播的 Receiver 分发前设置计时器，从 `receiverTime` 开始计时
3. **静态 vs 动态**：静态注册需要拉起进程，动态注册直接分发（进程必须已存在）
4. **goAsync()**：不会延长超时时间，系统依然使用 10s/60s 阈值

---
**下一篇：** [高阶篇：Android 14 现代化广播队列与性能治理](03_Expert_Broadcast_ANR.md)
