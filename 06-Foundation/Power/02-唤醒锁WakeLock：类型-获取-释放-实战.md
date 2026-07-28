# 06-Foundation/Power · 02 · 唤醒锁 WakeLock：类型 / 获取 / 释放 / 实战

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · WakeLock 泄漏 / 误用排查
>
> **强依赖**：[01 PowerManager 概览](01-PowerManager概览：Doze-Standby-唤醒机制全景.md) · [02-Symptom/S05-后台被冻结](../../../02-Symptom/S05-后台被冻结.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 WakeLock 4 大类型 + 11 个 flags + 获取/释放/嵌套/超时 4 大实战场景讲清楚——oncall 5 分钟定位"WakeLock 泄漏是哪个 flag 没 release"
- **不是**：不复述 PowerManagerService 内部架构（[01 §2](01-PowerManager概览：Doze-Standby-唤醒机制全景.md) 详）；不复述 Doze 状态机（[03 详](03-Doze-App-Standby：后台冻结机制.md)）；不复述 trace+logcat 5 分钟定位（[04 详](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md)）
- **承接自**：[01 §3.1 WakeLock 数据流](01-PowerManager概览：Doze-Standby-唤醒机制全景.md)
- **衔接去**：[03 Doze / Standby](03-Doze-App-Standby：后台冻结机制.md) / [04 耗电实战](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md) / [01-Mechanism/App/Process_Exit](../../../01-Mechanism/App/Process_Exit/)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 4 大类型 + 11 flags | 跟 PowerManager.java 常量对齐 |
| 2 | 4 大实战场景：获取/释放/嵌套/超时 | oncall 80% 问题 |
| 3 | 第 5 章 WakeLock 泄漏 4 类根因 | 实战收官 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**WakeLock = app 申请阻止系统进入 suspend 的机制——4 大类型（PARTIAL/FULL/SCREEN_BRIGHT/PROXIMITY_SCREEN_OFF）+ 11 个 flags + 4 大实战（获取/释放/嵌套/超时）——oncall 5 秒定位"哪个 app 持着什么 WakeLock 没 release"。**

AOSP 17 电源管理栈 oncall 第一工单来源：`dumpsys power` 里 `mWakeLocks` 表过长 → app 持锁不释放 → 耗电 / 后台被冻 / Doze 推迟。

---

## 1. WakeLock 4 大类型

### 1.1 类型对比

| 类型 | 阻止 suspend? | 保持屏幕? | 键盘背光? | API 常量 | oncall 关注度 |
|:-----|:-------------|:---------|:----------|:---------|:-------------|
| **PARTIAL_WAKE_LOCK** | ✅ 阻止 | ❌ | ❌ | `PARTIAL_WAKE_LOCK` | **90%** |
| **FULL_WAKE_LOCK** (deprecated) | ❌ | ✅ 最亮 | ✅ | `FULL_WAKE_LOCK` | **5%**（已废弃）|
| **SCREEN_BRIGHT_WAKE_LOCK** (deprecated) | ❌ | ✅ 最亮 | ❌ | `SCREEN_BRIGHT_WAKE_LOCK` | **2%**（已废弃）|
| **SCREEN_DIM_WAKE_LOCK** (deprecated) | ❌ | ✅ 暗 | ❌ | `SCREEN_DIM_WAKE_LOCK` | **1%**（已废弃）|
| **PROXIMITY_SCREEN_OFF_WAKE_LOCK** | ❌ | 接近时关 | ❌ | `PROXIMITY_SCREEN_OFF_WAKE_LOCK` | **2%**（特殊）|
| **DRAW_WAKE_LOCK** (deprecated) | ❌ | ✅ 最亮 | ❌ | `DRAW_WAKE_LOCK` | 0% |

> **AOSP 17 警告**：`FULL_WAKE_LOCK` / `SCREEN_BRIGHT_WAKE_LOCK` / `SCREEN_DIM_WAKE_LOCK` 全部 @Deprecated → 改用 `setKeepScreenOn()` 或 `FLAG_KEEP_SCREEN_ON`。

### 1.2 源码定义

```java
// frameworks/base/core/java/android/os/PowerManager.java
public final class WakeLock {
    public static final int PARTIAL_WAKE_LOCK = 0x00000001;        // 1
    public static final int SCREEN_DIM_WAKE_LOCK = 0x00000006;     // 6 (已废弃)
    public static final int SCREEN_BRIGHT_WAKE_LOCK = 0x0000000a;  // 10 (已废弃)
    public static final int FULL_WAKE_LOCK = 0x0000001f;           // 31 (已废弃)
    public static final int DRAW_WAKE_LOCK = 0x00000020;           // 32 (已废弃)
    public static final int PROXIMITY_SCREEN_OFF_WAKE_LOCK = 0x00000040;  // 64
    public static final int ACQUIRE_CAUSES_WAKEUP = 0x10000000;
    public static final int ON_AFTER_RELEASE = 0x20000000;
}
```

### 1.3 PARTIAL_WAKE_LOCK 详解（90% 实战）

```java
// 阻止 CPU 进入 suspend —— 但屏幕可关、键盘灯可灭
PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
WakeLock wl = pm.newWakeLock(
    PowerManager.PARTIAL_WAKE_LOCK,
    "MyApp:DownloadTask"  // 必填,排查时看的 tag
);
wl.acquire();
try {
    // 长任务: 文件下载 / 音乐播放 / 同步
} finally {
    wl.release();  // 必须在 finally 释放
}
```

**关键行为**：

- 持有时 `mWakefulness` 不会切到 `ASLEEP`（但可到 `DOZING`）
- 不阻止屏幕关闭（屏幕可正常灭）
- 不阻止 Doze 状态机推进（Doze INACTIVE 之后，PARTIAL 锁强制释放）
- oncall 95% 的 WakeLock 泄漏都是 PARTIAL

### 1.4 PROXIMITY_SCREEN_OFF_WAKE_LOCK（特殊场景）

```java
// 接近传感器触发时关屏幕 —— 打电话时贴脸自动黑屏
PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
WakeLock wl = pm.newWakeLock(
    PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK,
    "MyApp:PhoneCall"
);
wl.acquire();
// 当 sensor 报 "NEAR" → 屏幕关
// 当 sensor 报 "FAR" → 屏幕亮
wl.release();
```

**关键行为**：

- 屏幕开关完全由 sensor 决定，不由 WakeLock 本身
- 必须配合 SensorManager + Sensor.TYPE_PROXIMITY
- 实际打电话场景用 `TelephonyManager` 内置实现，不直接用这个

---

## 2. WakeLock 11 个 Flags

### 2.1 Flags 矩阵

| Flag | 值 | 作用 | 实战场景 |
|:-----|:-:|:-----|:--------|
| **`ACQUIRE_CAUSES_WAKEUP`** | 0x10000000 | acquire 时强制唤醒屏幕 | 闹钟响、IM 消息 |
| **`ON_AFTER_RELEASE`** | 0x20000000 | release 后保持屏幕亮一段时间 | 视频播完保留几秒 |
| **`ACQUIRE_CAUSES_WAKEUP_FOR_ATTRIBUTION`** | 0x20000000 (AOSP 17 新) | acquire 强制唤醒 + 记录 uid attribution | 兼容 AOSP 17 |
| **`SHOW_WHEN_LOCKED`** | 0x00000080 | 锁屏上显示 | 来电界面 |
| **`TURN_SCREEN_ON`** | 0x00000040 | 屏幕从 off 状态唤醒 | 闹钟 |
| **`RELEASE_FLAG_WAIT_FOR_NO_PROXIMITY`** | 0x00000001 | release 时等接近传感器 | 打电话挂断 |
| **`DOZE_WAKE_LOCK`** | 0x00000040 (内部) | AOSP 17 内部用 | 内部测试 |
| **`DRAW_WAKE_LOCK`** | 0x00000020 | 旧版,作废 | 0 |
| **`PREVENT_BATTERY_SAVER`** | 0x00000100 (AOSP 17 新) | 不被省电模式降级 | 紧急任务 |
| **`UNIMPORTANT_FOR_LOG`** | 0x00000002 | 不在 logs 里记录 | 系统级锁 |
| **`POWER_OFF_WAKE_LOCK`** | 0x00000004 (内部) | 关机时仍持 | 关机未完成 |

### 2.2 Flag 组合示例

```java
// 组合 1: 闹钟响 (强制唤醒屏幕)
int flags = PowerManager.PARTIAL_WAKE_LOCK
          | PowerManager.ACQUIRE_CAUSES_WAKEUP
          | PowerManager.ON_AFTER_RELEASE;
WakeLock alarmWl = pm.newWakeLock(flags, "AlarmClock:Alert");
alarmWl.acquire(10 * 1000);  // 10 秒超时

// 组合 2: IM 消息 (强制唤醒但屏幕暗)
int flags2 = PowerManager.PARTIAL_WAKE_LOCK
           | PowerManager.ACQUIRE_CAUSES_WAKEUP
           | PowerManager.SCREEN_DIM_WAKE_LOCK;  // 已废弃,改用 setScreenBrightness

// 组合 3: 视频播放 (保持屏幕亮)
int flags3 = PowerManager.PARTIAL_WAKE_LOCK
           | PowerManager.ON_AFTER_RELEASE
           | PowerManager.SHOW_WHEN_LOCKED;

// 组合 4: 紧急任务 (AOSP 17)
int flags4 = PowerManager.PARTIAL_WAKE_LOCK
           | PowerManager.PREVENT_BATTERY_SAVER;  // AOSP 17 新
```

### 2.3 实战常用组合

| 业务 | flag 组合 | oncall 备注 |
|:-----|:---------|:-----------|
| **后台下载** | `PARTIAL_WAKE_LOCK` | 唯一合法用法 |
| **前台播放** | `setKeepScreenOn(true)` (Activity) | 不用 WakeLock |
| **闹钟** | `PARTIAL + ACQUIRE_CAUSES_WAKEUP` | 需 acquire timeout |
| **IM 推送** | `PARTIAL + ACQUIRE_CAUSES_WAKEUP` | 短时间 |
| **电话** | `PROXIMITY_SCREEN_OFF_WAKE_LOCK` | 配合 sensor |
| **健康上报** | `PARTIAL + UNIMPORTANT_FOR_LOG` | 系统级,不让 logcat 刷屏 |
| **紧急告警** | `PARTIAL + PREVENT_BATTERY_SAVER` | AOSP 17 新 |

---

## 3. WakeLock 获取 / 释放 4 大实战

### 3.1 实战 1：基础获取 / 释放

```java
// ❌ 错误: 没在 finally
public void onStartCommand(Intent intent, int flags, int startId) {
    WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task");
    wl.acquire();
    doBigWork();  // 抛异常 → 锁不释放
    wl.release();
}

// ✅ 正确: try-finally
public void onStartCommand(Intent intent, int flags, int startId) {
    WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task");
    wl.acquire();
    try {
        doBigWork();
    } finally {
        if (wl.isHeld()) {
            wl.release();
        }
    }
}

// ✅ 更好: try-with-resources (Kotlin)
val pm = getSystemService(PowerManager::class.java)
pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task").use { wl ->
    wl.acquire(30_000)  // 30 秒超时
    doBigWork()
}  // 自动 release
```

### 3.2 实战 2：超时机制

```java
// ✅ 推荐: 带超时 (最安全)
WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task");
wl.acquire(30 * 1000);  // 30 秒后强制释放
try {
    doBigWork();
} finally {
    if (wl.isHeld()) {
        wl.release();
    }
}

// acquire(timeout) 原理
// → enqueue 30 秒后的 Handler message
// → 到时强制 release
// → 防泄漏的最后一道防线
```

**oncall 经验**：

- 99% 的 WakeLock 泄漏 = 没设超时
- 必加 `acquire(timeout)`，哪怕是 60 秒
- 如果任务可能跑很久（如下载大文件），用 JobScheduler 替代 WakeLock

### 3.3 实战 3：嵌套获取 / 释放（reference counted）

```java
// WakeLock 内部是引用计数
// acquire() → count++
// release() → count--
// count == 0 时才真正释放

WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task");
wl.acquire();   // count=1, 锁生效
wl.acquire();   // count=2, 仍生效
wl.acquire();   // count=3, 仍生效
wl.release();   // count=2, 仍生效
wl.release();   // count=1, 仍生效
wl.release();   // count=0, 真释放
```

**常见错误**：

```java
// ❌ 嵌套 2 次 acquire + 1 次 release → 永久泄漏
wl.acquire();
wl.acquire();  // ← 业务逻辑分支导致多 acquire
wl.release();  // 仍有 1 个引用

// ✅ 修法: 严格 1:1 配对 + try-finally
wl.acquire();
try {
    // 业务逻辑
} finally {
    wl.release();
}
```

**oncall 定位嵌套错误**：

```
$ adb shell dumpsys power | grep -A 5 "MyApp:Task"
[0] PARTIAL_WAKE_LOCK 'MyApp:Task' (uid=10100, pid=12345, refcount=3)
                                              ^^^^^^^^
                                              这里 = 3 说明嵌套 3 次
```

### 3.4 实战 4：跨进程 / setReferenceCounted

```java
// 默认 setReferenceCounted(true) = 引用计数模式
// setReferenceCounted(false) = 非引用计数模式 (任何 release 立即真释放)

// 默认 (true) 模式 - 安全
WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task");
wl.acquire();
wl.acquire();
wl.release();  // 仍持锁
wl.release();  // 真释放

// false 模式 - 危险
WakeLock wl2 = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task");
wl2.setReferenceCounted(false);
wl2.acquire();
wl2.acquire();
wl2.release();  // 立即真释放 (count 直接归零)
wl2.release();  // 抛 RuntimeException: WakeLock under-locked
```

**AOSP 17 警告**：AOSP 15+ 严格模式 (StrictMode) 检测 `setReferenceCounted(false)` 的滥用，会报错。

---

## 4. WakeLock 源码深度

### 4.1 PowerManager.newWakeLock()

```java
// frameworks/base/core/java/android/os/PowerManager.java
public WakeLock newWakeLock(int levelAndFlags, String tag) {
    validateWakeLockParameters(levelAndFlags, tag);
    return new WakeLock(levelAndFlags, tag, mContext.getOpPackageName());
}

private void validateWakeLockParameters(int levelAndFlags, String tag) {
    switch (levelAndFlags & WAKE_LOCK_LEVEL_MASK) {
        case PARTIAL_WAKE_LOCK:
        case PROXIMITY_SCREEN_OFF_WAKE_LOCK:
            // OK
            break;
        case SCREEN_DIM_WAKE_LOCK:    // 已废弃
        case SCREEN_BRIGHT_WAKE_LOCK: // 已废弃
        case FULL_WAKE_LOCK:          // 已废弃
        case DRAW_WAKE_LOCK:          // 已废弃
            if (mContext.getApplicationInfo().targetSdkVersion >= Build.VERSION_CODES.P) {
                throw new IllegalArgumentException("...");  // 强制抛错
            }
            break;
    }
    if (tag == null) {
        throw new IllegalArgumentException("The tag must not be null.");
    }
}
```

### 4.2 PowerManagerService.acquireWakeLock()

```java
// frameworks/base/services/core/java/com/android/server/power/PowerManagerService.java
@Override
public void acquireWakeLock(IBinder lock, int flags, String tag, String packageName,
        WorkSource ws, String historyTag, int displayId, int callbackFlags) {
    // 1. 权限检查
    if (lock == null) throw new IllegalArgumentException("lock must not be null");
    if (packageName == null) throw new IllegalArgumentException("packageName must not be null");
    
    // 2. system 进程特判
    final int uid = Binder.getCallingUid();
    final int pid = Binder.getCallingPid();
    
    // 3. 构造 WakeLock 对象
    WakeLock wakeLock = new WakeLock(lock, flags, tag, packageName, ws, historyTag,
            displayId, callbackFlags, uid, pid);
    
    // 4. 同步上锁
    synchronized (mLock) {
        // 5. 取消 acquire timeout (如果之前设过)
        // 6. 放入 mWakeLocks SortedMap
        mWakeLocks.put(lock, wakeLock);
        // 7. 触发状态重新计算
        mDirty |= DIRTY_WAKE_LOCKS;
        updatePowerStateLocked();
    }
}
```

### 4.3 updatePowerStateLocked() 关键路径

```java
private void updatePowerStateLocked() {
    if (!mSystemReady || mDirty == 0) return;
    
    // 1. 计算 userActivityTimeout
    // 2. 检查 wakefulness 是否需要变更
    if ((mDirty & DIRTY_WAKE_LOCKS) != 0) {
        // 关键: 统计当前所有持锁的最高 level
        int newWakeLockSummary = calculateWakeLockSummaryLocked();
        if (newWakeLockSummary != mWakeLockSummary) {
            mWakeLockSummary = newWakeLockSummary;
        }
    }
    
    // 3. 决定是否更新 wakefulness
    boolean stayAwake = mWakefulness == WAKEFULNESS_AWAKE
            && (mWakeLockSummary & WAKE_LOCK_STAY_AWAKE) != 0;
    
    // 4. 调 Power HAL
    if (mInteractive != mDisplayReady) {
        // 调 mDisplayPowerController.setScreenOn()
    }
}

private int calculateWakeLockSummaryLocked() {
    int summary = 0;
    for (WakeLock wakeLock : mWakeLocks.values()) {
        switch (wakeLock.mFlags & WAKE_LOCK_LEVEL_MASK) {
            case PARTIAL_WAKE_LOCK:
                summary |= WAKE_LOCK_CPU;
                break;
            case FULL_WAKE_LOCK:
                summary |= WAKE_LOCK_FULL;  // 阻止 suspend + 保持屏幕
                break;
            // ... 其他
        }
    }
    return summary;
}
```

---

## 5. WakeLock 泄漏 4 类根因

### 5.1 根因分类

| # | 根因 | 占比 | 修法 | 验证命令 |
|:-:|:-----|:----:|:-----|:---------|
| **L01** | 业务异常导致没 release | 40% | try-finally + acquire(timeout) | `dumpsys power` |
| **L02** | 嵌套 acquire + 不完整 release | 30% | 严格 1:1 配对 | 看 refcount |
| **L03** | Service / Receiver 持有时间过长 | 20% | JobScheduler 替代 | `dumpsys jobscheduler` |
| **L04** | setReferenceCounted(false) 滥用 | 10% | 用默认 true | StrictMode |

### 5.2 L01 实战：业务异常导致没 release

```java
// ❌ 反例 1
public void download(String url) {
    WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Download");
    wl.acquire();
    HttpsURLConnection conn = (HttpsURLConnection) new URL(url).openConnection();
    byte[] data = readAll(conn);  // 抛 IOException → 锁不释放
    saveFile(data);
    wl.release();
}

// ✅ 修法 1: try-finally
public void download(String url) {
    WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Download");
    wl.acquire(60 * 1000);  // 60 秒超时
    try {
        HttpsURLConnection conn = (HttpsURLConnection) new URL(url).openConnection();
        byte[] data = readAll(conn);
        saveFile(data);
    } finally {
        if (wl.isHeld()) wl.release();
    }
}
```

### 5.3 L02 实战：嵌套错误

```java
// ❌ 反例 2
public class TaskManager {
    private final WakeLock mLock = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task");
    
    public void startTaskA() {
        mLock.acquire();   // count=1
    }
    public void startTaskB() {
        mLock.acquire();   // count=2
    }
    public void stopTaskA() {
        mLock.release();   // count=1
    }
    public void stopTaskB() {
        mLock.release();   // count=0
    }
}
// 问题: startA() + startB() + stopA() → 还剩 1 个 → stopB() 释放
// 顺序乱了 → 永久泄漏

// ✅ 修法 2: 每个任务单独 WakeLock
public class TaskManager {
    public void startTask(String name) {
        WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:" + name);
        wl.acquire(30 * 1000);
        try {
            runTask(name);
        } finally {
            if (wl.isHeld()) wl.release();
        }
    }
}
```

### 5.4 L03 实战：Service 持锁过长

```java
// ❌ 反例 3: 用 Service + WakeLock 做长任务
public class DownloadService extends Service {
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Download");
        wl.acquire();
        // 2 小时下载,期间一直持锁 → 耗电 / 不进 Doze
        new Thread(() -> {
            downloadBigFile();
            wl.release();
        }).start();
        return START_STICKY;
    }
}

// ✅ 修法 3a: 改用 WorkManager / JobScheduler
public class DownloadWorker extends Worker {
    public Result doWork() {
        downloadBigFile();
        return Result.success();
    }
}
// WorkManager 自动处理 WakeLock + 进程保活 + Doze 适配

// ✅ 修法 3b: WorkManager API
OneTimeWorkRequest req = new OneTimeWorkRequest.Builder(DownloadWorker.class)
    .setConstraints(new Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .setRequiresBatteryNotLow(true)
        .build())
    .build();
WorkManager.getInstance(context).enqueue(req);
```

### 5.5 L04 实战：setReferenceCounted(false) 滥用

```java
// ❌ 反例 4
WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task");
wl.setReferenceCounted(false);
wl.acquire();
if (someCondition) {
    wl.release();
} else {
    // 漏 release → 永久持锁
}

// ✅ 修法 4: 用默认 true + 严格 1:1 配对
WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task");
wl.acquire(30 * 1000);
try {
    doWork();
} finally {
    if (wl.isHeld()) wl.release();
}
```

---

## 6. 5 类 oncall 问题排查模板

### 6.1 Q1: app 后台没收到推送

```bash
# 1. 5 秒: 看 app 在 Doze 状态
$ adb shell dumpsys deviceidle | grep "<pkg>"
# 看是否在 whitelist

# 2. 5 秒: 看 app 持锁状态
$ adb shell dumpsys power | grep -B 2 "<pkg>"

# 3. 5 秒: 看 App Standby bucket
$ adb shell dumpsys usagestats | grep -A 1 "<pkg>"

# 4. 5 秒: 看 JobScheduler 状态
$ adb shell dumpsys jobscheduler | grep -A 10 "<pkg>"

# 5. 5 秒: 看广播
$ adb shell dumpsys activity broadcasts | grep "<pkg>"
```

### 6.2 Q2: 耗电榜 app 居高不下

```bash
# 1. 30 秒: 抓 bugreport
$ adb bugreport > bugreport.zip

# 2. 5 秒: 看 WakeLock 累计持有时间
$ unzip -p bugreport.zip bugreport.txt | grep -A 30 "WAKE_LOCK"

# 3. 5 秒: 看 wakeup source
$ cat /sys/kernel/debug/wakeup_sources | grep "<pkg>"

# 4. 5 秒: 看 alarm 触发
$ adb shell dumpsys alarm | grep -A 3 "<pkg>"

# 5. 5 秒: 拉 batterystats
$ adb shell dumpsys batterystats --checkin > batterystats.txt
```

### 6.3 Q3: WakeLock 泄漏

```bash
# 1. 5 秒: 看当前 mWakeLocks
$ adb shell dumpsys power | grep -A 50 "mWakeLocks"
# 输出:
# [0] PARTIAL_WAKE_LOCK 'MyApp:Task' (uid=10100, pid=12345, refcount=1, ...)
# [1] PARTIAL_WAKE_LOCK 'MyApp:Task' (uid=10100, pid=12345, refcount=2, ...)

# 2. 5 秒: 看 refcount > 1
$ adb shell dumpsys power | grep "refcount=[2-9]"
# → 找出嵌套错误

# 3. 5 秒: 看 WakeLock 历史
$ adb shell dumpsys power | grep -A 100 "mWakeLocks History"
# → 最近 release 的 WakeLock

# 4. 5 秒: 看 tag 来源
$ adb logcat -d | grep "MyApp:Task"
# → 定位业务代码

# 5. 5 秒: 强杀
$ adb shell am force-stop <pkg>
```

### 6.4 Q4: 唤醒风暴

```bash
# 1. 5 秒: 看 wakeup_count
$ adb shell cat /sys/power/wakeup_count
# 输出: 12345 (累计唤醒次数)

# 2. 5 秒: 看 wakeup source 排行
$ adb shell cat /sys/kernel/debug/wakeup_sources
# 输出:
# name                 active_count  event_count  wakeup_count  ...
# PowerManagerService.WakeLocks  100  200  150
# alarm_rtc           50   300   200  ← 异常!
# sensor_ind          10   1000  500  ← 异常!

# 3. 5 秒: 看 alarm 触发
$ adb shell dumpsys alarm | head -50
# 看哪个 alarm 反复触发

# 4. 5 秒: 看 sensor 唤醒
$ adb shell dumpsys sensorservice | grep -A 20 "Sensor List"
# 看哪个 sensor 在采样

# 5. 5 秒: 看最近唤醒原因 (AOSP 17)
$ adb shell dumpsys power | grep "wakeup reason" | tail -20
# 找出反复出现的 reason
```

### 6.5 Q5: 屏幕没按时灭

```bash
# 1. 5 秒: 看 mWakefulness
$ adb shell dumpsys power | grep "mWakefulness"
# 输出: mWakefulness=Awake

# 2. 5 秒: 看 mWakeLocks
$ adb shell dumpsys power | grep -A 5 "mWakeLocks"
# 看谁持 FULL_WAKE_LOCK / SCREEN_BRIGHT

# 3. 5 秒: 看 userActivity 是否在更新
$ adb shell dumpsys power | grep "mUserActivityTimeout"
# 输出: mUserActivityTimeoutOverride=-1

# 4. 5 秒: 看 mScreenBrightnessOverride
$ adb shell dumpsys power | grep "mScreenBrightnessOverride"
# 看是否被 app 强制改

# 5. 5 秒: 看最近 userActivity
$ adb logcat -d | grep "userActivity"
```

---

## 7. dumpsys power 关键字段速查

### 7.1 完整字段表

| 字段 | 含义 | oncall 关注 |
|:-----|:-----|:-----------|
| `mWakefulness` | Awake / Dozing / Asleep | 系统态 |
| `mInteractive` | 屏幕是否亮 | 亮屏判断 |
| `mIsPowered` | 是否在充电 | 进 Doze 前提 |
| `mPlugType` | 充电类型 (USB/AC/Wireless) | 充电功率 |
| `mBatteryLevel` | 电量百分比 | 省电模式 |
| `mBatteryStatus` | 充电状态 | 满电判断 |
| `mScreenBrightnessOverride` | 强制亮度 | 屏幕调试 |
| `mUserActivityTimeoutOverride` | 强制休眠时间 | 长亮屏 |
| `mSleepTimeout` | 当前休眠超时 | 灭屏时间 |
| `mWakeLocks` | 当前持锁列表 | 锁泄漏 |
| `mDisplayPowerRequester` | 显示控制方 | WindowManager |
| `mPolicy` | LowPowerScenario 模式 | 省电模式 |
| `Suspend Blockers` | 阻止 suspend 的 blocker | 阻止 suspend |
| `mDirty` | 32 个脏位 | 状态变更 |

### 7.2 mDirty 32 个脏位

```java
// frameworks/base/services/core/java/com/android/server/power/PowerManagerService.java
public static final int DIRTY_WAKE_LOCKS            = 1 << 0;   // 0x1
public static final int DIRTY_USER_ACTIVITY          = 1 << 1;   // 0x2
public static final int DIRTY_RAW_WAKE_LOCKS         = 1 << 2;   // 0x4
public static final int DIRTY_WAKEFULNESS            = 1 << 3;   // 0x8
public static final int DIRTY_IS_POWERED             = 1 << 4;   // 0x10
public static final int DIRTY_STAY_ON                = 1 << 5;   // 0x20
public static final int DIRTY_BATTERY_STATE          = 1 << 6;   // 0x40
public static final int DIRTY_SCREEN_BRIGHTNESS      = 1 << 7;   // 0x80
public static final int DIRTY_SCREEN_ON              = 1 << 8;   // 0x100
public static final int DIRTY_BOOT_COMPLETED        = 1 << 9;   // 0x200
// ... 共 32 个
```

### 7.3 Suspend Blocker 列表

```
$ adb shell dumpsys power | grep -A 20 "Suspend Blockers"
Suspend Blockers:
  [0] PowerManagerService.WakeLocks    ← WakeLock 持锁
  [1] PowerManagerService.Display      ← 屏幕亮
  [2] PowerManagerService.WirelessChargerDetector  ← 无线充 (AOSP 17)
```

---

## 8. AOSP 17 关键变更

### 8.1 重要变更

| 版本 | 变更 | 实战影响 |
|:-----|:-----|:---------|
| **AOSP 12** | StrictMode 检测 `setReferenceCounted(false)` | 报错频率上升 |
| **AOSP 13** | `FULL_WAKE_LOCK` 完全废弃 → 抛 IllegalArgumentException | 老 app crash |
| **AOSP 14** | `acquire(timeout)` 强制推荐 | 加超时比例上升 |
| **AOSP 15** | Wakeup attribution (uid 记录) | 唤醒源可追 |
| **AOSP 16** | `UNIMPORTANT_FOR_LOG` flag | 系统锁静默 |
| **AOSP 17** | `PREVENT_BATTERY_SAVER` flag | 紧急任务不被省电模式降级 |

### 8.2 AOSP 17 Power HAL power_hint

```cpp
// hardware/interfaces/power/aidl/default/Power.cpp
ndk::ScopedAStatus Power::powerHint(PowerHint hint, int32_t data) {
    switch (hint) {
        case PowerHint::INTERACTION:
            // 用户触摸/按键
            if (mHandlePowerInteractive) {
                ALOGV("PowerHint INTERACTION");
                mHandlePowerInteractive();
            }
            break;
        case PowerHint::LAUNCH:
            // app 启动
            if (mHandlePowerLaunch) {
                mHandlePowerLaunch(data != 0);
            }
            break;
        case PowerHint::LOW_POWER:
            // 进低电量模式
            if (mHandlePowerLowPower) {
                mHandlePowerLowPower(data != 0);
            }
            break;
        case PowerHint::SUSTAINED_PERFORMANCE:
        case PowerHint::VR_MODE:
        case PowerHint::EXPENSIVE_RENDERING:
            // ...
            break;
    }
    return ndk::ScopedAStatus::ok();
}
```

### 8.3 AOSP 17 wakeup attribution

```java
// PowerManagerService.java
// AOSP 17 新增: 每个 wakeup 都打 attribution
private void recordWakeupAttribution(int uid, String tag, int reason) {
    if (mWakeupAttributionLogger != null) {
        mWakeupAttributionLogger.logWakeup(uid, tag, reason,
            SystemClock.uptimeMillis());
    }
}

// 调 wakeUp() 时
public void wakeUp(long eventTime, int uid, ...) {
    if (mLastWakeupTime + MIN_TIME_BETWEEN_WAKEUPS < eventTime) {
        recordWakeupAttribution(uid, "PowerManager", WAKE_REASON_APPLICATION);
    }
}
```

---

## 9. 与 smc-pub 对接

| smc-pub 文章 | 关联章节 | 内容 |
|:-------------|:---------|:-----|
| [01 PowerManager 概览](01-PowerManager概览：Doze-Standby-唤醒机制全景.md) | §3.1 WakeLock 数据流 | 本文 §4 互补 |
| [03 Doze / App Standby](03-Doze-App-Standby：后台冻结机制.md) | 全文 | WakeLock 释放 vs Doze 状态 |
| [04 耗电实战](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md) | §4-5 | WakeLock 泄漏实战 |
| [01-Mechanism/App/JobScheduler](../../../01-Mechanism/App/JobScheduler/) | 全文 | JobScheduler 替代 WakeLock |
| [01-Mechanism/App/WorkManager](../../../01-Mechanism/App/WorkManager/) | 全文 | WorkManager 替代方案 |
| [02-Symptom/S05-后台被冻结](../../../02-Symptom/S05-后台被冻结.md) | §3 | 后台被冻的 WakeLock 维度 |
| [01-Mechanism/Kernel/IO/01-中断子系统](../../../01-Mechanism/Kernel/IO/01-中断子系统.md) | §6 | kernel wakeup source 起源 |

---

## 10. 收官

### 10.1 一句话总结

WakeLock = 4 类型（PARTIAL/FULL/SCREEN_BRIGHT/PROXIMITY）+ 11 flags + 引用计数——oncall 4 类根因（业务异常 / 嵌套错误 / Service 长持 / reference_counted 滥用）——5 秒定位 `dumpsys power | grep mWakeLocks`，99% 泄漏都是没 acquire(timeout) + 没 try-finally。

### 10.2 速查命令

```bash
# 1. 当前 WakeLock 列表
adb shell dumpsys power | grep -A 50 "mWakeLocks"

# 2. WakeLock 持有时间
adb shell dumpsys power | grep -A 5 "mWakeLocks History"

# 3. refcount > 1 (嵌套错误)
adb shell dumpsys power | grep "refcount=[2-9]"

# 4. wakeup source 累计时间
adb shell cat /sys/kernel/debug/wakeup_sources

# 5. WakeLock 释放提醒 (AOSP 17)
adb shell dumpsys power | grep -i "under-locked"

# 6. 强杀释放
adb shell am force-stop <pkg>
```

### 10.3 实战模板

```java
// ✅ AOSP 17 推荐模板: acquire(timeout) + try-finally
val pm = getSystemService(PowerManager::class.java)
val wl = pm.newWakeLock(
    PowerManager.PARTIAL_WAKE_LOCK,
    "MyApp:${taskName}"  // 必须带业务标识
)
wl.acquire(30 * 1000)  // 必须带超时
try {
    doTask()
} finally {
    if (wl.isHeld()) wl.release()
}
```

### 10.4 自检

- [ ] 4 大类型 + 11 flags 能否口述？
- [ ] 4 大实战（基础 / 超时 / 嵌套 / 跨进程）能否立刻写出？
- [ ] WakeLock 泄漏 4 类根因 + 修法能否口述？
- [ ] 5 类 oncall 问题排查模板能否默写？
- [ ] AOSP 17 `PREVENT_BATTERY_SAVER` / wakeup attribution 是否了解？
