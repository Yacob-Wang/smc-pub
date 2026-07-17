# Broadcast ANR 基础篇：广播分类体系、Android 14 机制与 dumpsys 解读

## 📋 概述

Broadcast ANR（Broadcast Receiver Timeout）是 Android 开发中常见的一种无响应类型。在深入分析 ANR 之前，我们必须先理解 Android 广播的**分类体系**、**最新版本的机制变化**以及**如何通过系统工具诊断问题**。本篇将从这三个维度构建对 Broadcast ANR 的底层认知。

---

## 一、 广播的分类体系：从分发方式到注册方式

Android 广播可以从多个维度进行分类，不同的分类方式决定了不同的分发机制和超时行为。

### 1.1 按分发方式分类：Normal、Ordered、Sticky

#### 1.1.1 普通广播 (Normal Broadcast)
**特点**：
- 通过 `Context.sendBroadcast(Intent)` 发送
- **并发分发**：所有匹配的 Receiver 同时收到广播，互不干扰
- **无返回值**：Receiver 之间无法传递数据
- **无法中断**：任何 Receiver 都无法阻止其他 Receiver 接收

**源码标识**：
```java
// Intent.java
public static final int FLAG_RECEIVER_REGISTERED_ONLY = 0x40000000;
// 普通广播没有特殊标志，默认就是并发分发
```

**ANR 特点**：由于是并发分发，每个 Receiver 都有独立的超时计时器（10s/60s），一个 Receiver 超时不会直接影响其他 Receiver。

#### 1.1.2 有序广播 (Ordered Broadcast)
**特点**：
- 通过 `Context.sendOrderedBroadcast(Intent, String)` 发送
- **串行分发**：按照 Receiver 的优先级（priority）从高到低依次分发
- **可传递结果**：前一个 Receiver 可以通过 `setResultCode()`、`setResultData()` 传递数据给下一个
- **可中断**：Receiver 可以调用 `abortBroadcast()` 阻止后续 Receiver 接收

**优先级机制**：
```xml
<!-- AndroidManifest.xml -->
<receiver android:name=".MyReceiver">
    <intent-filter android:priority="1000">
        <action android:name="com.example.ACTION" />
    </intent-filter>
</receiver>
```
- 优先级范围：`-1000` 到 `1000`，数值越大优先级越高
- 相同优先级的 Receiver 按注册顺序分发

**ANR 特点**：**这是 Broadcast ANR 的重灾区**。因为串行分发，如果优先级为 1000 的 Receiver 执行了 10 秒，那么优先级为 999 的 Receiver 必须等待 10 秒后才能开始执行。系统会为**整个有序广播链条**设置一个总超时时间，而不是为每个 Receiver 单独计时。

#### 1.1.3 粘性广播 (Sticky Broadcast) ⚠️ 已废弃但需理解

**核心机制**：
粘性广播是 Android 早期版本（API < 21）提供的一种特殊广播，其 `Intent` 会被**持久化存储在系统内存**中。即使广播已经发送完毕，后续注册的 Receiver 也能立即收到最后一次发送的 `Intent`。

**实现原理**：
```java
// ActivityManagerService.java (简化)
public class ActivityManagerService {
    // 粘性广播缓存：key 是 Intent 的 action，value 是 Intent 对象
    final SparseArray<ArrayMap<String, ArrayList<Intent>>> mStickyBroadcasts 
        = new SparseArray<>();
    
    public void sendStickyBroadcast(Intent intent) {
        // 1. 先像普通广播一样分发给当前已注册的 Receiver
        sendBroadcast(intent);
        
        // 2. 将 Intent 存入缓存（按 userId 分组）
        synchronized (mStickyBroadcasts) {
            ArrayMap<String, ArrayList<Intent>> stickies = mStickyBroadcasts.get(userId);
            if (stickies == null) {
                stickies = new ArrayMap<>();
                mStickyBroadcasts.put(userId, stickies);
            }
            // 如果 action 已存在，替换；否则新增
            stickies.put(intent.getAction(), intent);
        }
    }
    
    // 当新 Receiver 注册时，检查是否有匹配的粘性广播
    public Intent registerReceiver(BroadcastReceiver receiver, IntentFilter filter) {
        // ... 注册逻辑 ...
        
        // 检查粘性广播缓存
        synchronized (mStickyBroadcasts) {
            ArrayMap<String, ArrayList<Intent>> stickies = mStickyBroadcasts.get(userId);
            if (stickies != null) {
                for (int i = 0; i < filter.countActions(); i++) {
                    String action = filter.getAction(i);
                    Intent sticky = stickies.get(action);
                    if (sticky != null) {
                        // 立即分发给新注册的 Receiver
                        receiver.onReceive(context, sticky);
                    }
                }
            }
        }
    }
}
```

**典型应用场景**（已废弃，仅作理解）：
- `ACTION_BATTERY_CHANGED`：电池状态变化，新注册的 Receiver 能立即获取当前电量
- `ACTION_SCREEN_ON/OFF`：屏幕状态，应用启动时能立即知道屏幕是否亮着

**废弃原因**：
1. **安全风险**：任何应用都可以发送粘性广播覆盖系统状态
2. **内存泄漏**：粘性 Intent 永久占用内存，无法自动清理
3. **隐私问题**：恶意应用可以读取其他应用发送的粘性广播数据

**替代方案**：
- 使用 `SharedPreferences` 或数据库存储状态，应用启动时主动查询
- 使用 `LocalBroadcastManager`（已废弃）或 `LiveData`、`Flow` 等响应式框架

### 1.2 按注册方式分类：Manifest、Context

#### 1.2.1 Manifest 注册（静态注册）
```xml
<receiver android:name=".BootReceiver"
    android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.BOOT_COMPLETED" />
    </intent-filter>
</receiver>
```

**特点**：
- 应用未启动时也能接收广播（系统会拉起进程）
- **Android 14+ 行为**：即使应用处于 cached 状态，manifest 注册的 Receiver 也能立即被唤醒并接收广播
- 适合接收系统级广播（如开机、网络变化）

#### 1.2.2 Context 注册（动态注册）
```java
IntentFilter filter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
registerReceiver(receiver, filter);
```

**特点**：
- 应用必须处于运行状态才能接收
- 需要手动调用 `unregisterReceiver()` 注销，否则会内存泄漏
- **Android 14+ 行为**：如果应用处于 cached 状态，广播会被**队列化延迟分发**（见下文）

---

## 二、 Android 14+ 的现代化广播机制

Android 14 对广播机制进行了重大重构，核心目标是**减少后台应用的 CPU 唤醒和电池消耗**。

### 2.1 Context 注册广播的队列化机制

**核心变化**：
当应用处于 **cached 状态**（后台且不活跃）时，通过 `registerReceiver()` 动态注册的 Receiver **不会立即接收广播**，而是被系统**队列化存储**。

**触发条件**：
```java
// ActivityManagerService.java (简化逻辑)
if (app.processState == PROCESS_STATE_CACHED_ACTIVITY 
    || app.processState == PROCESS_STATE_CACHED_EMPTY) {
    // 应用处于 cached 状态
    if (receiver.isContextRegistered()) {
        // Context 注册的 Receiver：队列化
        queueBroadcastForCachedApp(broadcast, receiver);
        return; // 不立即分发
    } else {
        // Manifest 注册的 Receiver：立即唤醒应用并分发
        wakeUpAppForManifestReceiver(broadcast, receiver);
    }
}
```

**分发时机**：
- 应用从 cached 状态恢复到 foreground/visible 状态时
- 应用被用户主动打开时
- 系统资源充足时批量处理

**对 ANR 的影响**：
- **正面**：减少了后台应用的 ANR 风险（因为广播被延迟了）
- **负面**：如果应用长时间处于 cached 状态，队列中可能积累大量广播，一旦应用被唤醒，可能面临**广播洪峰**，导致主线程被大量 `onReceive()` 调用阻塞

### 2.2 广播合并机制 (Broadcast Merging)

**核心机制**：
对于**重复的广播**（相同的 action），系统会将多个待分发的广播**合并为一个**。

**典型场景**：
```java
// 应用在 cached 状态时，系统每分钟发送一次 TIME_TICK
// 如果应用 cached 了 10 分钟，理论上应该收到 10 个 TIME_TICK
// 但在 Android 14+，系统会合并为 1 个（只保留最新的）
```

**合并规则**：
- 只合并**相同 action** 的广播
- 只合并发送给**同一个应用**的广播
- 合并时保留**最新的 Intent**（包括 extras）

**源码位置**：
```java
// BroadcastQueue.java
private void mergeBroadcastLocked(BroadcastRecord r) {
    // 查找队列中是否有相同 action 的待分发广播
    for (int i = mParallelBroadcasts.size() - 1; i >= 0; i--) {
        BroadcastRecord existing = mParallelBroadcasts.get(i);
        if (existing.intent.getAction().equals(r.intent.getAction())
            && existing.receivers.contains(r.receivers.get(0))) {
            // 合并：用新的替换旧的
            mParallelBroadcasts.set(i, r);
            return;
        }
    }
    // 没有找到可合并的，正常入队
    mParallelBroadcasts.add(r);
}
```

**对 ANR 的影响**：
- **正面**：减少了主线程的唤醒次数，降低了 ANR 风险
- **注意**：应用需要适应"可能丢失中间状态"的情况（例如电池从 80% 直接跳到 50%）

### 2.3 分应用队列 (Per-App Queuing)

**传统机制（Android 13 及以前）**：
- 全局广播队列：所有应用的广播在一个 FIFO 队列中排队
- 问题：如果应用 A 发送了 1000 个广播，会阻塞应用 B 的广播接收

**Android 14+ 机制**：
- **按应用分组**：每个应用有独立的广播队列
- **优先级调度**：系统根据应用的前后台状态动态调整分发优先级
- **隔离性**：一个应用的广播卡死，不会直接影响其他应用

---

## 三、 dumpsys activity broadcasts 深度解读

`dumpsys activity broadcasts` 是诊断 Broadcast ANR 的**核心工具**，它输出系统当前所有广播相关的状态信息。

### 3.1 命令格式与输出结构

```bash
adb shell dumpsys activity broadcasts
# 或只查看历史记录
adb shell dumpsys activity broadcasts history
```

### 3.2 输出结构解析

#### 3.2.1 Registered Receivers（当前注册的 Receiver）

```
Registered Receivers:
  * ReceiverList{42a3c8d8 1234 com.example.app/u0a123/u0 local:false}
    package=com.example.app process=com.example.app
    IntentFilter{actions=[android.intent.action.BATTERY_CHANGED]}
```

**字段含义**：
- `ReceiverList{...}`：Receiver 列表对象的内存地址
- `1234`：进程 PID
- `com.example.app/u0a123/u0`：包名/UID/用户ID
- `local:false`：是否为本地 Receiver（false 表示跨进程）
- `IntentFilter{...}`：该 Receiver 监听的 Intent 过滤器

#### 3.2.2 Receiver Resolver Table（Receiver 解析表）

```
Receiver Resolver Table:
  Non-Data Actions:
    android.intent.action.BOOT_COMPLETED:
      BroadcastFilter{42b1c9e0 u0 ReceiverList{42a3c8d8 1234 com.example.app/u0a123/u0}}
      BroadcastFilter{42b2d0f1 u0 ReceiverList{42c4e1a2 5678 com.other.app/u0a124/u0}}
```

**解读**：
- 按 **action** 分组，列出所有监听该 action 的 Receiver
- `BroadcastFilter{...}`：过滤器的内存地址和用户ID
- 用于快速查找：当系统发送 `BOOT_COMPLETED` 时，直接查表找到所有匹配的 Receiver

#### 3.2.3 Active Broadcasts（活跃广播队列）

```
Active ordered broadcasts [foreground]:
  #0: BroadcastRecord{430d3e20 u0 android.intent.action.BOOT_COMPLETED}
    act=android.intent.action.BOOT_COMPLETED flg=0x50000010
    queueTime=1234567890 dispatchTime=1234567891
    nextReceiver=1 of 5
    state=(SERVING)
    receivers[0]: BroadcastFilter{42a3c8d8 ...} (DELIVERED)
    receivers[1]: BroadcastFilter{42b1c9e0 ...} (PENDING)
```

**关键字段**：
- `BroadcastRecord{...}`：广播记录对象的内存地址和用户ID
- `act=`：Intent 的 action
- `flg=0x...`：Intent 标志位（十六进制）
  - `0x50000010` = `FLAG_RECEIVER_REGISTERED_ONLY | FLAG_RECEIVER_FOREGROUND`
- `queueTime`：广播入队时间（毫秒时间戳）
- `dispatchTime`：开始分发时间
- `nextReceiver=1 of 5`：当前正在处理第 1 个 Receiver，共 5 个
- `state=(SERVING)`：当前状态
  - `IDLE`：空闲，等待分发
  - `SERVING`：正在分发中
  - `APP_RECEIVE`：应用正在接收（onReceive 执行中）
- `receivers[0]: ... (DELIVERED)`：第 0 个 Receiver 已分发
- `receivers[1]: ... (PENDING)`：第 1 个 Receiver 等待中

**ANR 诊断要点**：
- 如果 `state=(APP_RECEIVE)` 且 `dispatchTime` 距离现在超过 10s（前台）或 60s（后台），说明该 Receiver 可能已经超时
- `nextReceiver` 卡在某个位置，说明前面的 Receiver 执行时间过长

#### 3.2.4 Sticky Broadcasts（粘性广播缓存）

```
Sticky broadcasts [user 0]:
  android.intent.action.BATTERY_CHANGED:
    Intent { act=android.intent.action.BATTERY_CHANGED flg=0x60000010 ... }
    extras: Bundle[{level=85, scale=100, ...}]
```

**解读**：
- 列出当前系统中所有缓存的粘性广播
- 格式：`action: Intent{...}`
- `extras: Bundle[...]`：Intent 携带的额外数据

#### 3.2.5 Historical Broadcasts（历史广播记录）

```
Historical broadcasts [foreground]:
  #0: BroadcastRecord{430d3e20 u0 android.intent.action.SCREEN_OFF}
    act=android.intent.action.SCREEN_OFF flg=0x50000010
    enqueueClockTime=2024-01-20 10:30:00
    dispatchClockTime=2024-01-20 10:30:00
    finishClockTime=2024-01-20 10:30:01
    duration=1000ms
    receivers[0]: BroadcastFilter{...} duration=800ms result=0
```

**关键字段**：
- `enqueueClockTime`：入队时间（可读格式）
- `dispatchClockTime`：开始分发时间
- `finishClockTime`：完成时间
- `duration`：总耗时
- `receivers[0]: ... duration=800ms`：第 0 个 Receiver 的执行耗时
- `result=0`：Receiver 设置的结果码（`RESULT_OK = 0`）

**ANR 诊断要点**：
- 查看 `duration`，如果接近 10s（前台）或 60s（后台），说明该广播处理时间接近超时阈值
- 查看各个 Receiver 的 `duration`，找出耗时最长的 Receiver

### 3.3 实战案例：通过 dumpsys 定位 ANR

**场景**：应用在接收 `BOOT_COMPLETED` 时发生 ANR

**步骤 1：查看活跃广播**
```bash
adb shell dumpsys activity broadcasts | grep -A 20 "Active ordered"
```

**输出示例**：
```
Active ordered broadcasts [foreground]:
  #0: BroadcastRecord{430d3e20 u0 android.intent.action.BOOT_COMPLETED}
    state=(APP_RECEIVE)
    nextReceiver=2 of 10
    dispatchTime=1234567890  # 假设这是 10 秒前
    receivers[1]: BroadcastFilter{42a3c8d8 ... com.example.app} (DELIVERING)
```

**分析**：
- `state=(APP_RECEIVE)` 且 `dispatchTime` 是 10 秒前 → 很可能已经超时
- `nextReceiver=2` 卡在第 2 个 Receiver → 第 1 个或第 2 个 Receiver 执行时间过长
- `receivers[1]` 是 `com.example.app` → 问题可能出在这个应用

**步骤 2：查看历史记录确认**
```bash
adb shell dumpsys activity broadcasts history | grep -A 10 "BOOT_COMPLETED"
```

**步骤 3：结合 traces.txt**
- 在 `traces.txt` 中查找 `com.example.app` 的主线程堆栈
- 查看 `onReceive` 方法中正在执行的操作

---

## 四、 Broadcast ANR 的超时机制

### 4.1 超时阈值

| 应用状态 | 超时阈值 | 判断依据 |
| :--- | :--- | :--- |
| **前台应用** | **10 秒** | `PROCESS_STATE_IMPORTANT_FOREGROUND` 或更高 |
| **后台应用** | **60 秒** | `PROCESS_STATE_SERVICE` 及以下 |

**源码位置**：
```java
// ActivityManagerService.java
static final int BROADCAST_FG_TIMEOUT = 10 * 1000;  // 10秒
static final int BROADCAST_BG_TIMEOUT = 60 * 1000;  // 60秒
```

### 4.2 超时计时起点

**关键点**：超时计时不是从广播**发送**时开始，而是从**分发给具体 Receiver** 时开始。

```java
// BroadcastQueue.java
final void processNextBroadcast(boolean fromMsg) {
    // 1. 选择下一个要分发的 Receiver
    BroadcastRecord r = mPendingBroadcast;
    Object nextReceiver = r.receivers.get(r.nextReceiver);
    
    // 2. 设置超时计时器（从这里开始计时）
    setBroadcastTimeoutLocked(now);
    
    // 3. 分发广播给 Receiver
    deliverToRegisteredReceiverLocked(r, nextReceiver, ...);
}
```

**对有序广播的影响**：
- 每个 Receiver 分发时都会**重置计时器**
- 但如果整个有序广播链条的总时间超过阈值，仍会触发 ANR

---

## 五、 本篇总结

1. **广播分类**：Normal（并发）、Ordered（串行）、Sticky（已废弃但需理解其机制）
2. **Android 14+ 变化**：Context 注册的广播在 cached 状态下会被队列化，重复广播会被合并
3. **dumpsys 解读**：通过 `Active Broadcasts` 和 `Historical Broadcasts` 可以定位 ANR 发生的具体 Receiver 和时间点
4. **超时机制**：前台 10s，后台 60s，计时从分发时开始

---
**下一篇：** [进阶篇：BroadcastQueue 深度源码追踪与 ANR 检测机制](02_Advanced_Broadcast_ANR.md)
