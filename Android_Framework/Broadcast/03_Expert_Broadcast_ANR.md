# Broadcast ANR 高阶篇：Android 14 现代化队列、PSI 压力分析与系统级治理

## 📋 概述

在掌握了基础和进阶原理后，我们需要面对更复杂的现实问题：为什么有时候 `onReceive` 只有几行代码也会 ANR？Android 14+ 的现代化广播队列是如何实现的？如何从系统级视角（PSI、调度延迟）分析 ANR 根因？本篇将深入这些高级话题。

---

## 一、 Android 14+ ModernizedBroadcastQueue 完整实现

### 1.1 传统队列的弊端与问题

**Android 13 及以前的问题**：

```java
// 传统实现（简化）
class BroadcastQueue {
    ArrayList<BroadcastRecord> mOrderedBroadcasts = new ArrayList<>();
    
    void enqueueBroadcast(BroadcastRecord r) {
        mOrderedBroadcasts.add(r);  // 简单的 FIFO
    }
    
    void processNextBroadcast() {
        BroadcastRecord r = mOrderedBroadcasts.remove(0);
        // 分发...
    }
}
```

**问题**：
1. **全局阻塞**：如果应用 A 发送了 1000 个广播，应用 B 的广播必须等待
2. **无优先级**：无法根据应用重要性调整分发顺序
3. **无合并**：重复广播会全部分发，浪费 CPU
4. **无隔离**：一个应用卡死，影响所有应用

### 1.2 ModernizedBroadcastQueue 的核心数据结构

```java
// BroadcastQueue.java (Android 14+)
public final class BroadcastQueue {
    // 传统队列（保留兼容性）
    final ArrayList<BroadcastRecord> mOrderedBroadcasts = new ArrayList<>();
    
    // ========== 现代化队列：按应用分组 ==========
    // key: packageName, value: 该应用的广播队列
    final ArrayMap<String, AppBroadcastQueue> mAppQueues = new ArrayMap<>();
    
    // 应用队列的优先级队列（用于调度）
    final PriorityQueue<AppBroadcastQueue> mSchedulingQueue = new PriorityQueue<>(
        (a, b) -> Integer.compare(b.getPriority(), a.getPriority())
    );
}

// 每个应用的独立广播队列
class AppBroadcastQueue {
    final String packageName;
    final ArrayList<BroadcastRecord> pendingBroadcasts = new ArrayList<>();
    int priority;  // 动态优先级
    long lastDispatchTime;  // 上次分发时间
    int anrCount;  // ANR 历史次数
    
    int getPriority() {
        // 动态计算优先级
        // 1. 前台应用 > 后台应用
        // 2. 最近 ANR 少的应用 > ANR 多的应用
        // 3. 长时间未分发的应用 > 刚分发过的应用
        return calculateDynamicPriority();
    }
}
```

### 1.3 分应用队列的入队逻辑

```java
// BroadcastQueue.java
void enqueueBroadcastLocked(BroadcastRecord r) {
    // 1. 确定目标应用
    String targetPackage = determineTargetPackage(r);
    
    // 2. 获取或创建应用队列
    AppBroadcastQueue appQueue = mAppQueues.get(targetPackage);
    if (appQueue == null) {
        appQueue = new AppBroadcastQueue(targetPackage);
        mAppQueues.put(targetPackage, appQueue);
    }
    
    // 3. 尝试合并重复广播
    if (shouldMerge(r, appQueue)) {
        mergeBroadcast(r, appQueue);
        return;
    }
    
    // 4. 入队
    appQueue.pendingBroadcasts.add(r);
    
    // 5. 更新调度队列
    if (!mSchedulingQueue.contains(appQueue)) {
        mSchedulingQueue.offer(appQueue);
    }
}
```

### 1.4 广播合并算法详解

```java
// BroadcastQueue.java
boolean shouldMerge(BroadcastRecord newRecord, AppBroadcastQueue appQueue) {
    // 合并条件：
    // 1. 相同的 action
    // 2. 发送给同一个应用
    // 3. 在时间窗口内（例如 5 秒内）
    
    long now = SystemClock.uptimeMillis();
    long mergeWindow = 5 * 1000;  // 5 秒窗口
    
    for (int i = appQueue.pendingBroadcasts.size() - 1; i >= 0; i--) {
        BroadcastRecord existing = appQueue.pendingBroadcasts.get(i);
        
        // 检查时间窗口
        if (now - existing.enqueueClockTime > mergeWindow) {
            break;  // 超出窗口，不再检查
        }
        
        // 检查 action 是否相同
        if (existing.intent.getAction().equals(newRecord.intent.getAction())) {
            // 检查是否发送给同一个应用
            if (isSameTarget(existing, newRecord)) {
                return true;  // 可以合并
            }
        }
    }
    
    return false;
}

void mergeBroadcast(BroadcastRecord newRecord, AppBroadcastQueue appQueue) {
    // 找到可合并的广播，用新的替换旧的
    for (int i = appQueue.pendingBroadcasts.size() - 1; i >= 0; i--) {
        BroadcastRecord existing = appQueue.pendingBroadcasts.get(i);
        if (shouldMerge(newRecord, existing)) {
            // 替换：保留新的 Intent（包括最新的 extras）
            appQueue.pendingBroadcasts.set(i, newRecord);
            return;
        }
    }
}
```

**合并规则总结**：
- **时间窗口**：5 秒内的重复广播会被合并
- **保留最新**：合并时保留最新的 Intent（包括 extras）
- **只合并普通广播**：有序广播不合并（因为需要保证顺序）

### 1.5 动态优先级调度算法

```java
// AppBroadcastQueue.java
int calculateDynamicPriority() {
    int basePriority = 0;
    
    // 1. 应用状态优先级（权重：1000）
    ProcessRecord app = getProcessRecord();
    if (app != null) {
        if (app.processState <= PROCESS_STATE_TOP) {
            basePriority += 1000;  // 前台应用
        } else if (app.processState <= PROCESS_STATE_IMPORTANT_FOREGROUND) {
            basePriority += 500;   // 重要前台
        } else if (app.processState <= PROCESS_STATE_SERVICE) {
            basePriority += 100;   // 后台服务
        }
        // cached 状态：0
    }
    
    // 2. ANR 历史惩罚（权重：-100 per ANR）
    basePriority -= anrCount * 100;
    
    // 3. 等待时间奖励（权重：+1 per second）
    long waitTime = SystemClock.uptimeMillis() - lastDispatchTime;
    basePriority += (int)(waitTime / 1000);
    
    // 4. 队列长度惩罚（权重：-10 per broadcast）
    basePriority -= pendingBroadcasts.size() * 10;
    
    return basePriority;
}
```

**调度策略**：
1. **前台应用优先**：前台应用的广播优先分发
2. **ANR 惩罚**：历史 ANR 多的应用优先级降低
3. **等待时间奖励**：长时间未分发的应用优先级提升（防止饿死）
4. **队列长度惩罚**：队列太长的应用优先级降低（防止一个应用占用太多资源）

### 1.6 现代化队列的分发流程

```java
// BroadcastQueue.java
void processNextBroadcastModernized() {
    // 1. 从优先级队列中取出最高优先级的应用队列
    AppBroadcastQueue appQueue = mSchedulingQueue.poll();
    if (appQueue == null) {
        return;  // 没有待处理的广播
    }
    
    // 2. 从应用队列中取出一个广播
    if (appQueue.pendingBroadcasts.isEmpty()) {
        return;
    }
    
    BroadcastRecord r = appQueue.pendingBroadcasts.remove(0);
    appQueue.lastDispatchTime = SystemClock.uptimeMillis();
    
    // 3. 如果应用队列还有待处理的广播，重新加入调度队列
    if (!appQueue.pendingBroadcasts.isEmpty()) {
        mSchedulingQueue.offer(appQueue);
    }
    
    // 4. 分发广播（同传统流程）
    deliverToRegisteredReceiverLocked(r, ...);
}
```

**优势**：
- **隔离性**：一个应用卡死，不影响其他应用
- **公平性**：通过优先级调度，保证重要应用优先
- **效率**：合并重复广播，减少 CPU 唤醒

---

## 二、 PSI 压力与 Broadcast ANR 的深度关联

### 2.1 PSI (Pressure Stall Information) 基础

PSI 是 Linux 内核提供的压力监控机制，用于量化 CPU、内存、IO 的压力程度。

**PSI 指标**：
```bash
# /proc/pressure/cpu
some avg10=2.5 avg60=1.8 avg300=1.2 total=12345678

# /proc/pressure/memory
some avg10=5.2 avg60=3.1 avg300=2.0 total=23456789
full avg10=1.5 avg60=0.8 avg300=0.5 total=34567890

# /proc/pressure/io
some avg10=10.5 avg60=8.2 avg300=6.5 total=45678901
full avg10=3.2 avg60=2.1 avg300=1.5 total=56789012
```

**字段含义**：
- `some`：至少一个任务因资源不足而阻塞的时间百分比
- `full`：所有任务都因资源不足而阻塞的时间百分比
- `avg10/60/300`：过去 10 秒/60 秒/300 秒的平均值
- `total`：累计阻塞时间（微秒）

### 2.2 IO Pressure 对 Broadcast ANR 的影响

**场景**：`onReceive` 中只有一行 `SharedPreferences` 读取，但触发了 ANR。

**根因分析**：

```java
// 应用代码
public void onReceive(Context context, Intent intent) {
    // 只有一行代码，理论上很快
    SharedPreferences sp = context.getSharedPreferences("config", MODE_PRIVATE);
    String value = sp.getString("key", "default");
}
```

**底层执行路径**：
```
onReceive()
  → getSharedPreferences()
    → ContextImpl.getSharedPreferences()
      → FileInputStream.open()  // 打开 /data/data/包名/shared_prefs/config.xml
        → VFS open()
          → F2FS file system
            → Block I/O
              → 如果 IO 压力大，这里可能阻塞数秒
```

**PSI IO 压力监控**：
```bash
# 查看 IO 压力
cat /proc/pressure/io

# 如果 some avg10 > 10%，说明 IO 压力较大
# 如果 full avg10 > 5%，说明 IO 严重阻塞
```

**诊断方法**：
1. **查看 traces.txt**：主线程堆栈显示在 `FileInputStream.read()` 或 `nativePollOnce()`
2. **查看 PSI**：`/proc/pressure/io` 显示高压力
3. **查看系统日志**：`dmesg | grep -i "i/o error"` 或 `logcat | grep -i "slow operation"`

### 2.3 Memory Pressure 对 Broadcast ANR 的影响

**场景**：`onReceive` 执行简单逻辑，但触发了 ANR。

**根因分析**：

```
onReceive()
  → 执行代码
    → Page Fault（代码页不在内存中）
      → 从 swap 读取
        → 如果内存压力大，swap 读取可能耗时数秒
```

**PSI Memory 压力监控**：
```bash
# 查看内存压力
cat /proc/pressure/memory

# 如果 some avg10 > 20%，说明内存压力较大
# 如果 full avg10 > 10%，说明内存严重不足，大量 swap
```

**诊断方法**：
1. **查看 traces.txt**：主线程状态为 `S`（Sleeping），可能在等待内存页
2. **查看 PSI**：`/proc/pressure/memory` 显示高压力
3. **查看系统内存**：`cat /proc/meminfo | grep -i swap` 查看 swap 使用情况

### 2.4 CPU Pressure 与调度延迟

**场景**：`onReceive` 代码很简单，但系统判定超时。

**根因分析**：

```
时间线：
T0: 系统发送广播
T1: 应用主线程变为 Runnable（等待 CPU 时间片）
T2: 主线程获得 CPU，开始执行 onReceive（耗时 1ms）
T3: onReceive 执行完成，通知系统

问题：T1 到 T2 之间，主线程可能等待了 9 秒（CPU 负载高）
系统视角：T0 到 T3 总共 10 秒 → 触发 ANR
```

**PSI CPU 压力监控**：
```bash
# 查看 CPU 压力
cat /proc/pressure/cpu

# 如果 some avg10 > 50%，说明 CPU 负载很高
```

**诊断方法**：
1. **查看 traces.txt**：主线程状态为 `R`（Runnable），但长时间未执行
2. **查看 PSI**：`/proc/pressure/cpu` 显示高压力
3. **查看系统负载**：`top` 或 `uptime` 查看系统负载

### 2.5 综合诊断：PSI 三指标联合分析

**诊断流程**：

```bash
# 1. 查看 PSI 三指标
cat /proc/pressure/cpu
cat /proc/pressure/memory
cat /proc/pressure/io

# 2. 查看 traces.txt 中的主线程状态
# - state=R: CPU 调度延迟
# - state=S + 堆栈在 IO: IO 压力
# - state=S + 堆栈在内存操作: 内存压力

# 3. 查看系统日志
dmesg | tail -100
logcat -d | grep -i "slow\|anr\|pressure"
```

**判断标准**：
- **IO Pressure > 10%** + 堆栈在 IO → IO 阻塞导致 ANR
- **Memory Pressure > 20%** + 堆栈在内存操作 → 内存压力导致 ANR
- **CPU Pressure > 50%** + 主线程 Runnable → CPU 调度延迟导致 ANR

---

## 三、 系统级治理方案

### 3.1 广播分发监控与拦截

#### 3.1.1 Hook ActivityThread.mH

```java
// 使用 Xposed 或类似框架
public class BroadcastMonitor {
    public void hookActivityThread() {
        XposedHelpers.findAndHookMethod(
            ActivityThread.class,
            "handleReceiver",
            ReceiverData.class,
            new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) {
                    ReceiverData data = (ReceiverData) param.args[0];
                    long startTime = SystemClock.uptimeMillis();
                    param.thisObject.setTag("broadcast_start_time", startTime);
                }
                
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    long startTime = (Long) param.thisObject.getTag("broadcast_start_time");
                    long duration = SystemClock.uptimeMillis() - startTime;
                    
                    if (duration > 1000) {  // 超过 1 秒
                        Log.w("BroadcastMonitor", 
                            "Slow broadcast: " + data.intent.getAction() 
                            + " duration=" + duration + "ms");
                    }
                }
            }
        );
    }
}
```

#### 3.1.2 静态代码分析

```java
// 使用 Android Lint 自定义规则
public class BroadcastReceiverAnalyzer extends Detector {
    @Override
    public void visitMethod(MethodInvocation node) {
        // 检测 onReceive 中是否调用了耗时 API
        if (isInOnReceiveMethod(node)) {
            String methodName = node.getMethodName();
            if (isBlockingMethod(methodName)) {
                reportIssue(node, "不要在 onReceive 中调用阻塞方法: " + methodName);
            }
        }
    }
    
    private boolean isBlockingMethod(String methodName) {
        return methodName.equals("getSharedPreferences")
            || methodName.equals("openFileInput")
            || methodName.equals("query")
            || methodName.equals("execSQL");
    }
}
```

### 3.2 广播削峰与限流

#### 3.2.1 系统级限流

```java
// ActivityManagerService.java (ROM 定制)
public class BroadcastThrottler {
    private final Map<String, ThrottleInfo> mThrottleMap = new HashMap<>();
    
    public boolean shouldThrottle(String action, String packageName) {
        ThrottleInfo info = mThrottleMap.get(action);
        if (info == null) {
            return false;
        }
        
        long now = SystemClock.uptimeMillis();
        if (now - info.lastSendTime < info.minInterval) {
            // 限流：丢弃广播
            return true;
        }
        
        info.lastSendTime = now;
        return false;
    }
}

// 配置限流规则
mThrottleMap.put("com.example.FREQUENT_ACTION", 
    new ThrottleInfo(1000));  // 最小间隔 1 秒
```

#### 3.2.2 应用级削峰

```java
// 应用代码
public class ThrottledBroadcastReceiver extends BroadcastReceiver {
    private final Map<String, Long> mLastReceiveTime = new HashMap<>();
    private static final long MIN_INTERVAL = 1000;  // 1 秒
    
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        long now = SystemClock.uptimeMillis();
        
        Long lastTime = mLastReceiveTime.get(action);
        if (lastTime != null && now - lastTime < MIN_INTERVAL) {
            // 忽略重复广播
            return;
        }
        
        mLastReceiveTime.put(action, now);
        
        // 处理广播
        processBroadcast(context, intent);
    }
}
```

### 3.3 异步化改造最佳实践

#### 3.3.1 使用 WorkManager（推荐）

```java
public class MyReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        // 立即返回，不阻塞
        OneTimeWorkRequest workRequest = new OneTimeWorkRequest.Builder(MyWorker.class)
            .setInputData(new Data.Builder()
                .putString("action", intent.getAction())
                .putAll(intent.getExtras())
                .build())
            .build();
        
        WorkManager.getInstance(context).enqueue(workRequest);
    }
}
```

#### 3.3.2 使用 goAsync()（谨慎使用）

```java
public class MyReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        final PendingResult pendingResult = goAsync();
        
        // 设置超时保护
        Handler handler = new Handler(Looper.getMainLooper());
        handler.postDelayed(() -> {
            if (!pendingResult.isFinished()) {
                Log.w("MyReceiver", "Broadcast timeout, force finish");
                pendingResult.finish();
            }
        }, 8000);  // 8 秒超时保护（前台 10s）
        
        new Thread(() -> {
            try {
                // 执行任务（确保在 8 秒内完成）
                doWork();
            } finally {
                handler.removeCallbacksAndMessages(null);
                pendingResult.finish();
            }
        }).start();
    }
}
```

---

## 四、 实际案例深度分析

### 4.1 案例一：IO 压力导致的 ANR

**现象**：
- ANR Reason: `Broadcast of Intent { act=android.intent.action.BOOT_COMPLETED }`
- traces.txt 显示主线程在 `FileInputStream.read()`

**分析**：
```bash
# 1. 查看 PSI
cat /proc/pressure/io
# some avg10=15.2 avg60=12.5 avg300=10.1

# 2. 查看 traces.txt
"main" prio=5 tid=1 Blocked
  at java.io.FileInputStream.read(FileInputStream.java:123)
  at com.example.BootReceiver.onReceive(BootReceiver.java:45)

# 3. 查看系统 IO
iostat -x 1
# %util > 90%，说明 IO 设备繁忙
```

**根因**：
- 系统启动时，大量应用同时读取文件（SharedPreferences、数据库等）
- F2FS 文件系统 IO 压力大，导致单个文件读取耗时数秒

**解决方案**：
1. **延迟初始化**：不在 `BOOT_COMPLETED` 中读取文件，延迟到应用启动时
2. **异步读取**：使用 `goAsync()` 或 `WorkManager`
3. **系统优化**：调整 F2FS 参数，优化 IO 调度

### 4.2 案例二：内存压力导致的 ANR

**现象**：
- ANR Reason: `Broadcast of Intent { act=android.intent.action.MEDIA_MOUNTED }`
- traces.txt 显示主线程状态为 `S`（Sleeping）

**分析**：
```bash
# 1. 查看 PSI
cat /proc/pressure/memory
# some avg10=25.3 avg60=20.1 avg300=15.5
# full avg10=8.2 avg60=5.1 avg300=3.2

# 2. 查看内存
cat /proc/meminfo | grep -i swap
# SwapTotal: 2097152 kB
# SwapFree: 512000 kB  # 大量 swap 被使用

# 3. 查看 traces.txt
"main" prio=5 tid=1 Sleeping
  at java.lang.Object.wait(Object.java:422)
  # 可能在等待内存页从 swap 读取
```

**根因**：
- 系统内存不足，应用代码页被 swap 到磁盘
- 执行 `onReceive` 时触发 Page Fault，需要从 swap 读取，耗时数秒

**解决方案**：
1. **减少内存占用**：优化应用内存使用
2. **系统优化**：调整 LMKD 参数，减少 swap 使用
3. **延迟处理**：不在内存压力大时处理广播

### 4.3 案例三：CPU 调度延迟导致的 ANR

**现象**：
- ANR Reason: `Broadcast of Intent { act=com.example.ACTION }`
- traces.txt 显示主线程状态为 `R`（Runnable），但长时间未执行

**分析**：
```bash
# 1. 查看 PSI
cat /proc/pressure/cpu
# some avg10=65.2 avg60=58.1 avg300=52.3

# 2. 查看系统负载
uptime
# load average: 8.5, 7.2, 6.1  # 负载很高

# 3. 查看 traces.txt
"main" prio=5 tid=1 Runnable
  # 主线程在等待 CPU 时间片
```

**根因**：
- 系统 CPU 负载极高（大量后台任务）
- 主线程虽然变为 Runnable，但无法获得 CPU 时间片
- 等待时间超过 10 秒，触发 ANR

**解决方案**：
1. **降低 CPU 负载**：减少后台任务
2. **提高进程优先级**：使用 `setProcessPriority()`
3. **系统优化**：调整 CPU 调度策略

---

## 五、 总结与展望

1. **Android 14+ 现代化队列**：分应用队列、动态优先级调度、广播合并，大幅提升分发效率
2. **PSI 压力分析**：IO、Memory、CPU 压力都会导致 ANR，需要综合诊断
3. **系统级治理**：监控、限流、异步化改造，多管齐下
4. **根因分析**：不能只看代码，必须结合系统环境（PSI、调度、IO）综合判断

---
**本系列完结。**
