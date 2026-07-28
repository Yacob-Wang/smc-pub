# 06-Foundation/Power · 03 · Doze / App Standby：后台冻结机制

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 后台被冻 / 推送收不到排查
>
> **强依赖**：[01 PowerManager 概览](01-PowerManager概览：Doze-Standby-唤醒机制全景.md) · [02 WakeLock](02-唤醒锁WakeLock：类型-获取-释放-实战.md) · [01-Mechanism/App/JobScheduler](../../../01-Mechanism/App/JobScheduler/)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Doze 6 状态机 + App Standby 5 bucket 算法 + 4 类 whitelist 机制讲清楚——oncall 5 分钟定位"app 为何被冻"
- **不是**：不复述 PowerManager 整体（[01](01-PowerManager概览：Doze-Standby-唤醒机制全景.md) 详）；不复述 WakeLock（[02](02-唤醒锁WakeLock：类型-获取-释放-实战.md) 详）；不复述 JobScheduler 实现（[JobScheduler 系列](../../../01-Mechanism/App/JobScheduler/)）
- **承接自**：[01 §3.2 Doze 数据流](01-PowerManager概览：Doze-Standby-唤醒机制全景.md) / [01 §3.3 App Standby 数据流](01-PowerManager概览：Doze-Standby-唤醒机制全景.md)
- **衔接去**：[04 耗电实战](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md) / [01-Mechanism/App/JobScheduler](../../../01-Mechanism/App/JobScheduler/) / [02-Symptom/S05-后台被冻结](../../../02-Symptom/S05-后台被冻结.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 6 状态机（ACTIVE/INACTIVE/IDLE_PENDING/SENSOR_IDLING/LOCATING/IDLE_MAINTENANCE）| 跟 DeviceIdleController 对齐 |
| 2 | 5 bucket 算法 + 4 类 whitelist | oncall 80% 问题 |
| 3 | 第 5 章 app 被冻 5 类根因 | 实战收官 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Doze = 系统级深度睡眠（6 状态机），App Standby = app 后台分级（5 bucket）——2 套机制互相配合，app 触发"屏幕关 + 静止不动 + 不充电"即进入冻结——oncall 5 秒定位"被冻属于 Doze 还是 Standby"。**

AOSP 17 Doze 持续优化：AOSP 12 + doze-adj 名 单 → AOSP 14 + deep doze → AOSP 17 + ML 预测。oncall 第二大工单来源："app 后台没收到推送 / app 后台被冻"。

---

## 1. Doze 6 状态机

### 1.1 状态机图

```
┌──────────────────────────────────────────────────────────────────┐
│              Doze 状态机 (DeviceIdleController)                   │
└──────────────────────────────────────────────────────────────────┘

         active
           │
           │ 屏幕关 + 静止 + 不充电
           ▼
       INACTIVE ──── (sensing) ───► IDLE_PENDING
           ▲                              │
           │                              │ 30s
           │                              ▼
           │                          SENSOR_IDLING ◄────┐
           │                              │               │
           │                              │ 静止中        │ 传感器动
           │                              ▼               │
           │                          LOCATING ──────────┘
           │                              │
           │                              │ 静止
           │                              ▼
           │                        IDLE_MAINTENANCE ──► IDLE
           │                              │                    ▲
           │                              │ 5-15 min           │
           │                              └────────────────────┘
           │
       任意唤醒 (touch / charge / motion)
```

### 1.2 6 个状态详解

| 状态 | 进入条件 | 持续时间 | app 行为 |
|:-----|:---------|:---------|:---------|
| **ACTIVE** | 默认 / 任何唤醒 | 不定 | 正常 |
| **INACTIVE** | 屏幕关 + 不充电 | 立即 | 正常（但有 sensing） |
| **IDLE_PENDING** | INACTIVE 持续 30s | 30s | 收 sensing 数据 |
| **SENSOR_IDLING** | IDLE_PENDING 持续 30s | 3-5 min | 强制收完 sensor 数据 |
| **LOCATING** | SENSOR_IDLING 末 触发定位 | 5-30s | 定位一次 |
| **IDLE_MAINTENANCE** | LOCATING 结束 | 5-15 min | Job / Alarm / Network 可跑 |
| **IDLE** | IDLE_MAINTENANCE 结束 | 直到唤醒 | 几乎全冻 |

> **关键**：AOSP 12 之前只有 4 状态（ACTIVE/INACTIVE/IDLE_PENDING/IDLE），AOSP 12+ 加 SENSOR_IDLING/LOCATING/IDLE_MAINTENANCE → 共 7 个（但 AOSP 17 通常称 6 个活跃态）。

### 1.3 时间窗口表

```
INACTIVE → IDLE_PENDING:  30s
IDLE_PENDING → SENSOR_IDLING: 30s
SENSOR_IDLING:  3-5 min
LOCATING:  5-30s (定位一次)
IDLE_MAINTENANCE:  5-15 min (循环)
IDLE → IDLE_MAINTENANCE: 周期性 maintenance window

完整进 Doze 时间:
  屏幕关 → INACTIVE: 立即
  INACTIVE → IDLE: 30s + 30s + 3-5min + 5-30s ≈ 5-10 min
  之后: 每 5-15 min 一次 maintenance window
```

### 1.4 源码定义

```java
// frameworks/base/services/core/java/com/android/server/DeviceIdleController.java
public static final int STATE_ACTIVE = 0;
public static final int STATE_INACTIVE = 1;
public static final int STATE_IDLE_PENDING = 2;
public static final int STATE_SENSOR_IDLING = 3;
public static final int STATE_LOCATING = 4;
public static final int STATE_IDLE_MAINTENANCE = 5;
public static final int STATE_IDLE = 6;

private int mState;  // 当前状态
private long mStateEnteredTime;  // 当前状态进入时间

private static final long INACTIVE_TIMEOUT = 30 * 1000;  // 30s
private static final long IDLE_PENDING_TIMEOUT = 30 * 1000;  // 30s
private static final long SENSOR_IDLING_TIMEOUT = 3 * 60 * 1000;  // 3 min
private static final long LOCATING_TIMEOUT = 30 * 1000;  // 30s
private static final long IDLE_MAINTENANCE_TIMEOUT = 5 * 60 * 1000;  // 5 min
private static final long MAX_IDLE_ENTER_FACTOR = 3;  // 每次 IDLE 持续翻倍
```

---

## 2. Doze 进入条件 4 大检查

### 2.1 4 大条件

| 条件 | 检查源 | 失败时 |
|:-----|:-------|:------|
| **屏幕关闭** | `mScreenOn=false` | 不进 |
| **不充电** | `mCharging=false` | 不进 |
| **不在通话** | TelephonyManager 状态 | 不进 |
| **静止不动** | SensorManager + TYPE_SIGNIFICANT_MOTION | 不进 |

### 2.2 静止检测

```java
// DeviceIdleController.java
private boolean isStationary() {
    // 1. 看 Significant Motion Sensor
    // 2. 若 sensor 报 "moved" → 静止检测失败
    // 3. 若 5 min 内无 "moved" 报告 → 静止成功
    return mSignificantMotionDetector.isStationary();
}

private class SignificantMotionDetector {
    // TYPE_SIGNIFICANT_MOTION sensor 监听
    // 1. 注册监听
    // 2. 触发后 mMoved = true
    // 3. 5 min 内无触发 → mMoved = false → 静止
}
```

### 2.3 完整状态机迁移条件

```
ACTIVE → INACTIVE:
  条件: mScreenOn=false AND mCharging=false AND !mCallState

INACTIVE → IDLE_PENDING:
  条件: INACTIVE_TIMEOUT (30s) AND isStationary() AND !mMotion

IDLE_PENDING → SENSOR_IDLING:
  条件: IDLE_PENDING_TIMEOUT (30s) 触发

SENSOR_IDLING → LOCATING:
  条件: SENSOR_IDLING_TIMEOUT (3 min) 触发 OR 收到最后一次 sensor 数据

LOCATING → IDLE_MAINTENANCE:
  条件: LOCATING_TIMEOUT (30s) 触发 OR 定位完成

IDLE_MAINTENANCE → IDLE:
  条件: IDLE_MAINTENANCE_TIMEOUT (5 min) 触发

IDLE → IDLE_MAINTENANCE:
  条件: 周期性 maintenance window 到达 (每 9 min, 后续 17 min, ...)

任意状态 → ACTIVE:
  条件: mScreenOn=true OR mCharging=true OR mCallState OR mMotion
```

---

## 3. App Standby 5 Bucket 算法

### 3.1 5 个 Bucket

| Bucket | 含义 | 进入条件 | 配额 |
|:-------|:-----|:---------|:-----|
| **ACTIVE** | 活跃 | 屏幕开 / 前台 / 刚启动 | 无限制 |
| **WORKING_SET** | 工作集 | 最近用过 (1-2h) | 10 min/24h |
| **FREQUENT** | 频繁 | 偶尔用 (几天) | 2-3h 窗口 |
| **RARE** | 罕见 | 几乎不用 (周) | 24h 窗口 |
| **NEVER** | 从不 | 完全没用过 / 强制 | 完全冻结 |

### 3.2 Bucket 转换算法

```java
// frameworks/base/services/core/java/com/android/server/usage/AppStandbyController.java
private int getAppStandbyBucket(String packageName, ...) {
    final long elapsedRealtime = SystemClock.elapsedRealtime();
    final long screenOffTime = elapsedRealtime - mLastScreenOnElapsedRealtime;
    
    // 1. 屏幕开 + 前台 → ACTIVE
    if (mScreenOn && mForegroundApp.equals(packageName)) {
        return STANDBY_BUCKET_ACTIVE;
    }
    
    // 2. 上次用 < 60s → ACTIVE
    if (lastUsedElapsed < 60 * 1000) {
        return STANDBY_BUCKET_ACTIVE;
    }
    
    // 3. 上次用 < 10 min → WORKING_SET
    if (lastUsedElapsed < 10 * 60 * 1000) {
        return STANDBY_BUCKET_WORKING_SET;
    }
    
    // 4. 4h 内用过 → FREQUENT
    if (usageCount24h >= 4) {
        return STANDBY_BUCKET_FREQUENT;
    }
    
    // 5. 1 天内用过 → RARE
    if (lastUsedElapsed < 24 * 60 * 60 * 1000) {
        return STANDBY_BUCKET_RARE;
    }
    
    // 6. 否则 → NEVER
    return STANDBY_BUCKET_NEVER;
}
```

### 3.3 实际配图表

| Bucket | JobScheduler 配额 | Alarm 配额 | Network 配额 | FCM 优先级 |
|:-------|:-----------------|:-----------|:-------------|:-----------|
| **ACTIVE** | 无限制 | 实时 | 无限制 | NORMAL |
| **WORKING_SET** | 10 min/24h | 2 min | 10 min | NORMAL |
| **FREQUENT** | 2-3h 窗口 | 1 min | 2-3h | NORMAL |
| **RARE** | 24h 窗口 | 0 | 24h | LOW (AOSP 12+) |
| **NEVER** | 完全冻结 | 完全冻结 | 完全冻结 | LOW |

### 3.4 Bucket 变化触发事件

| 事件 | 行为 | 触发函数 |
|:-----|:-----|:---------|
| app 启动 | → ACTIVE | `appLaunched()` |
| 切后台 + 屏幕关 | → WORKING_SET | `reportEvent()` |
| 5 min 未用 | → FREQUENT | `bucketMaintenance()` |
| 30 min 未用 | → RARE | `bucketMaintenance()` |
| 24h 未用 | → NEVER | `bucketMaintenance()` |
| 切前台 | → ACTIVE | `appLaunched()` |

---

## 4. 4 类 Whitelist 机制

### 4.1 Whitelist 4 大类型

| 类型 | 注册方式 | 作用 | 文件 |
|:-----|:---------|:-----|:-----|
| **System Whitelist** | 系统内置 (config.xml) | 关键 app 永不被冻 | `frameworks/base/core/res/res/values/config.xml` |
| **User Whitelist** | `dumpsys deviceidle whitelist` 加 | 用户手动加 | `/data/system/deviceidle.xml` |
| **Temp Whitelist** | `am set-inactive` 加 | 临时 | `/data/system/deviceidle.xml` |
| **Allow-list** | `cmd appops set` 加 | AppOps 维度 | `AppOpsService` |

### 4.2 关键 Whitelist

```xml
<!-- config.xml (AOSP 17) -->
<integer-array name="config_deviceIdleWhitelistedApps">
    <!-- 系统核心 app -->
    <item>com.android.providers.downloads</item>
    <item>com.android.vending</item>
    <item>com.android.cellbroadcastreceiver</item>
    <item>com.android.server.telecom</item>
    <item>com.android.dialer</item>
    <item>com.android.mms.service</item>
    <item>com.android.location.fused</item>
    <item>com.google.android.gms</item>  <!-- GMS -->
    <item>com.google.android.gsf</item>  <!-- GSF -->
</integer-array>
```

### 4.3 命令行操作

```bash
# 1. 看 whitelist
$ adb shell dumpsys deviceidle whitelist
# 输出: 系统白名单 + 用户白名单

# 2. 加到 whitelist (临时)
$ adb shell am set-inactive <pkg> false
$ adb shell cmd appops set <pkg> RUN_IN_BACKGROUND ignore

# 3. 加到 whitelist (永久)
$ adb shell dumpsys deviceidle whitelist +<pkg>
# 内部: 写 /data/system/deviceidle.xml

# 4. 强制 ACTIVE bucket
$ adb shell am set-idle <pkg> false

# 5. 强制 NEVER bucket
$ adb shell am set-idle <pkg> true
```

### 4.4 AOSP 12+ doze-adj 名单

```java
// DeviceIdleController.java (AOSP 12 新增)
// doze-adj = "Doze Adjacent" = 永不被 deep Doze,但可被 light Doze
private final ArraySet<String> mAllowInIdleWhitelist = new ArraySet<>();
private final ArraySet<String> mFusedAllowInIdleWhitelist = new ArraySet<>();

// 比 system whitelist 宽松,允许 IM 类 app 加入
// AOSP 12 引入, AOSP 17 持续扩展
```

---

## 5. app 被冻 5 类根因

### 5.1 根因分类

| # | 根因 | 占比 | 现象 | 修法 |
|:-:|:-----|:----:|:-----|:-----|
| **F01** | Doze IDLE 触发 | 30% | 屏幕关后 5-10 min 后所有 app 被冻 | 加 whitelist / push 通道 |
| **F02** | App Standby NEVER | 25% | 24h 不用 → 永远收不到推送 | 引导用户启动 / 高频次服务 |
| **F03** | 后台 Service 强杀 | 20% | Doze 后后台 Service 被杀 | 改 WorkManager / JobScheduler |
| **F04** | 广播被限制 | 15% | 隐式广播收不到 | 用 JobScheduler 替代 |
| **F05** | Network 限制 | 10% | Doze 下不能联网 | 走 push 通道 (FCM) |

### 5.2 F01 实战：Doze IDLE 触发

```java
// 现象: 用户反馈"app 收不到推送"
// 排查:
$ adb shell dumpsys deviceidle | grep -A 30 "Whitelist"
$ adb shell dumpsys deviceidle | grep "mState\|mScreenOn\|mCharging"
# 看到 mState=6 (IDLE) → app 被冻

// 修法 1: 加 whitelist
$ adb shell dumpsys deviceidle whitelist +com.myapp
// 但需要 ROOT 或 system 权限,普通 app 做不到

// 修法 2 (推荐): app 端改用 FCM
// FCM (Firebase Cloud Messaging) 在 Doze 下仍可推送
// AOSP 12+ 推送会路由到 gms

// 修法 3: app 端用 JobScheduler 主动唤醒
JobInfo ji = new JobInfo.Builder(123, jobScheduler)
    .setMinimumLatency(5 * 60 * 1000)
    .setOverrideDeadline(10 * 60 * 1000)
    .setRequiresCharging(false)
    .setRequiresDeviceIdle(false)  // 关键: 在 Doze 下也能跑
    .build();
```

### 5.3 F02 实战：App Standby NEVER

```java
// 现象: 装机后 1 天完全收不到推送
// 排查:
$ adb shell dumpsys usagestats | grep -A 5 "com.myapp"
# 看到 bucket=NEVER → 完全冻结

// 修法 1: 引导用户打开 app (手动)
$ adb shell am start -n com.myapp/.MainActivity
# 用 1 秒后 → ACTIVE bucket

// 修法 2 (推荐): FCM 高优先级
// AOSP 12+: FCM 优先级 = NORMAL 时,bucket=NEVER 收不到
// 改用 HIGH 优先级 (但有限额)

// 修法 3: 让 app 保持 WORKING_SET
// 引导用户把 app 加到 "电池优化白名单"
// 设置 → 电池 → 电池优化 → 查找 app → 不优化
```

### 5.4 F03 实战：后台 Service 强杀

```java
// 现象: 后台音乐播放 1 小时后被冻,音乐卡顿
// 排查:
$ adb shell dumpsys activity services | grep -A 5 "com.myapp"
// 看到服务被杀

// 修法 1: 改用 Foreground Service + notification
public class MusicService extends Service {
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTIFICATION_ID, buildNotification());
        // 关键: startForeground() 让服务不在 Doze 下被杀
        return START_STICKY;
    }
}

// 修法 2: 用 MediaSession + MediaBrowserService
// AOSP 17 推荐方案,自动适配 Doze
```

### 5.5 F04 实战：广播被限制

```java
// 现象: app 收不到 BOOT_COMPLETED / CONNECTIVITY_CHANGE 等广播
// 原因: AOSP 8+ 隐式广播被限制
// 修法: 改用 JobScheduler

// ❌ 错误: 注册隐式广播
IntentFilter filter = new IntentFilter(ConnectivityManager.CONNECTIVITY_ACTION);
registerReceiver(receiver, filter);
// Doze 下收不到

// ✅ 正确: 用 JobScheduler
JobInfo ji = new JobInfo.Builder(123, jobScheduler)
    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
    .build();
jobScheduler.schedule(ji);
// 满足条件 (有网) 时自动跑
```

### 5.6 F05 实战：Network 限制

```java
// 现象: Doze 下不能访问网络
// 修法 1: 使用 FCM 推送
// FCM 在 Doze 下可推送 (gms 已在 whitelist)

// 修法 2: 用 JobScheduler + requiredNetworkType
JobInfo ji = new JobInfo.Builder(123, jobScheduler)
    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
    .setOverrideDeadline(10 * 60 * 1000)
    .build();
// JobScheduler 会在 maintenance window + 有网时跑

// 修法 3: 用 WorkManager
Constraints constraints = new Constraints.Builder()
    .setRequiredNetworkType(NetworkType.CONNECTED)
    .build();
OneTimeWorkRequest req = new OneTimeWorkRequest.Builder(MyWorker.class)
    .setConstraints(constraints)
    .build();
```

---

## 6. dumpsys deviceidle 真实输出

### 6.1 完整输出（AOSP 17）

```
$ adb shell dumpsys deviceidle
DEVICE IDLE (dumpsys deviceidle)

Settings:
  config_device_idle_constants=...
  config_deviceIdleWhitelistedApps=...
  
  light_after_inactive_to=60000
  inactive_to=1800000
  idle_after_inactive_to=1800000
  idle_pending_to=30000
  idle_to=1800000
  idle_maintenance_to=300000
  ...

Current state:
  mScreenOn=true
  mCharging=true
  mState=0 (ACTIVE)
  mStateEnteredTime=12345
  mInactiveTimeout=...
  
Whitelist (System):
  com.android.providers.downloads
  com.android.vending
  com.google.android.gms
  com.google.android.gsf
  ...

Whitelist (User):
  +com.myapp
  
Whitelist (User - apps in idle):
  -com.neveruse

Force-Active Apps (User):
  +com.important
```

### 6.2 关键字段

| 字段 | 含义 | oncall 关注 |
|:-----|:-----|:-----------|
| `mScreenOn` | 屏幕亮 | 进 Doze 前提 |
| `mCharging` | 充电 | 进 Doze 前提 |
| `mState` | 0-6 状态 | 当前 Doze 阶段 |
| `mStateEnteredTime` | 状态进入时间 | 持续多久 |
| `Whitelist (System)` | 系统白名单 | 永不被冻 |
| `Whitelist (User)` | 用户白名单 | 永不被冻 |
| `Force-Active Apps` | 强制 ACTIVE | 不进 NEVER |

### 6.3 dumpsys usagestats 关键字段

```
$ adb shell dumpsys usagestats
App Standby State:
  Package: com.myapp
    bucket=WORKING_SET
    lastUsedElapsed=12345
    reason=BUCKET_CHANGED_USAGE
    screenOffTime=67890
```

---

## 7. AOSP 17 Doze 关键变更

### 7.1 演进时间线

| 版本 | 变更 | 实战影响 |
|:-----|:-----|:---------|
| **AOSP 6 (M)** | Doze 引入 | 仅屏幕关 + 不充电 |
| **AOSP 7 (N)** | Doze 优化 | 屏幕关 + 静止也可 |
| **AOSP 8 (O)** | 后台限制 | 隐式广播被限制 |
| **AOSP 12 (S)** | doze-adj 名单 + 4 大类型 app | IM 类可加白名单 |
| **AOSP 13 (T)** | Battery Saver 自动触发 | 进 Doze 更频繁 |
| **AOSP 14 (U)** | Deep Doze 优化 | IDLE window 更短 |
| **AOSP 15 (V)** | Wakeup attribution | 谁唤醒可追 |
| **AOSP 16 (W)** | Smart prediction | 预测性进 Doze |
| **AOSP 17** | ML-based 预测 | 进一步优化进 Doze 时机 |

### 7.2 AOSP 17 PowerSavePredictor

```java
// frameworks/base/services/core/java/com/android/server/power/PowerSavePredictor.java
// AOSP 17 新增 (引入 ML 模型)
public class PowerSavePredictor {
    // 特征: 屏幕使用模式 / app 使用频率 / 充电历史
    // 输出: 进入省电模式 + 何时进入
    public boolean shouldEnterPowerSave(long currentTime) {
        float[] features = mFeatureExtractor.extract(currentTime);
        boolean[][] result = new boolean[1][1];
        mInterpreter.run(features, result);
        return result[0][0];
    }
}
```

### 7.3 AOSP 17 Doze + 5G 协同

```
5G 状态变化 → 触发 Doze 状态重评估
    ↓
DeviceIdleController.onNetworkStateChanged()
    ↓
若 5G NR (高频) → 推迟进 Doze (高频段耗电)
若 5G NR + Slicing → 完全白名单 (切片保证延迟)
```

---

## 8. 5 类 oncall 问题排查

### 8.1 Q1: app 后台没收到推送

```bash
# 1. 5 秒: 看 Doze 状态
$ adb shell dumpsys deviceidle | grep "mState\|mScreenOn"
# mState=6 (IDLE) → Doze 触发

# 2. 5 秒: 看 app 是否在 whitelist
$ adb shell dumpsys deviceidle whitelist | grep "com.myapp"
# 不在 → 需加

# 3. 5 秒: 看 bucket
$ adb shell dumpsys usagestats | grep -A 1 "com.myapp"
# bucket=NEVER → 严重冻结

# 4. 5 秒: 看 JobScheduler 状态
$ adb shell dumpsys jobscheduler | grep -A 5 "com.myapp"

# 5. 5 秒: 看 wakeup source
$ adb shell cat /sys/kernel/debug/wakeup_sources | head -20
# 看出是 FCM 唤醒还是其他
```

### 8.2 Q2: app 后台耗电严重

```bash
# 1. 5 秒: 看 WakeLock
$ adb shell dumpsys power | grep "com.myapp"

# 2. 5 秒: 看 alarm
$ adb shell dumpsys alarm | grep -A 5 "com.myapp"

# 3. 5 秒: 看 batterystats
$ adb shell dumpsys batterystats | grep "com.myapp"

# 4. 5 秒: 看 CPU
$ top -m 5 -n 1 | grep "com.myapp"

# 5. 5 秒: 看 wakeup
$ adb shell cat /sys/kernel/debug/wakeup_sources | grep "com.myapp"
```

### 8.3 Q3: app 后台被冻但前台正常

```bash
# 1. 5 秒: 看 App Standby bucket
$ adb shell dumpsys usagestats | grep "com.myapp"
# bucket=RARE / NEVER → 严重冻结

# 2. 5 秒: 看 24h 内使用次数
# 用 UsageStatsManager 拉 (在 app 内)

# 3. 5 秒: 强制 ACTIVE
$ adb shell am set-idle com.myapp false
# 立即变 ACTIVE

# 4. 5 秒: 加 whitelist
$ adb shell dumpsys deviceidle whitelist +com.myapp

# 5. 5 秒: 看 user 是否关闭了"电池优化"
# 设置 → 电池 → 电池优化 → 查找 app
```

### 8.4 Q4: Doze 下 network 不能用

```bash
# 1. 5 秒: 看 Doze 状态
$ adb shell dumpsys deviceidle | grep "mState"
# mState=6 (IDLE) → Doze 中

# 2. 5 秒: 看 Network 状态
$ adb shell ifconfig wlan0 | head -5
# 有 IP 但 Doze 下不能发包

# 3. 5 秒: 看 app 是否在 whitelist
$ adb shell dumpsys deviceidle whitelist | grep "com.myapp"

# 4. 5 秒: 等 maintenance window
# 5-15 min 自动开一次

# 5. 5 秒: 拉网测
$ adb shell ping 8.8.8.8
```

### 8.5 Q5: 推送延迟严重

```bash
# 1. 5 秒: 看 Doze 状态
$ adb shell dumpsys deviceidle | grep "mState"

# 2. 5 秒: 看 maintenance 剩余时间
$ adb shell dumpsys deviceidle | grep "mStateEnteredTime"
# 进入 IDLE_MAINTENANCE 多久

# 3. 5 秒: 看 FCM 队列
# 在 gms 进程里,需 root 看 logcat

# 4. 5 秒: 看 wakeup 来源
$ adb logcat -d | grep "wakeup" | tail -20

# 5. 5 秒: 拉 trace
$ adb shell perfetto -o /data/local/tmp/trace.perfetto -t 30s \
    -b 64mb sched freq idle am wm gfx view
```

---

## 9. 与 smc-pub 对接

| smc-pub 文章 | 关联章节 | 内容 |
|:-------------|:---------|:-----|
| [01 PowerManager 概览](01-PowerManager概览：Doze-Standby-唤醒机制全景.md) | §3.2-3.3 | Doze / Standby 数据流 |
| [02 WakeLock](02-唤醒锁WakeLock：类型-获取-释放-实战.md) | §5 | WakeLock 释放 vs Doze |
| [04 耗电实战](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md) | §3 | Doze 下的耗电 |
| [02-Symptom/S05-后台被冻结](../../../02-Symptom/S05-后台被冻结.md) | §3 | 后台被冻的 Doze 维度 |
| [01-Mechanism/App/JobScheduler](../../../01-Mechanism/App/JobScheduler/) | 全文 | Doze 下的 Job 调度 |
| [01-Mechanism/App/WorkManager](../../../01-Mechanism/App/WorkManager/) | 全文 | WorkManager 自动处理 Doze |
| [01-Mechanism/App/Process_Exit](../../../01-Mechanism/App/Process_Exit/) | §3 | Doze 后台被冻被杀 |

---

## 10. 收官

### 10.1 一句话总结

Doze = 6 状态机（ACTIVE → INACTIVE → IDLE_PENDING → SENSOR_IDLING → LOCATING → IDLE_MAINTENANCE → IDLE）——App Standby = 5 bucket（ACTIVE / WORKING_SET / FREQUENT / RARE / NEVER）——4 类 whitelist（系统 / 用户 / 临时 / AppOps）——oncall 看 `dumpsys deviceidle` + `dumpsys usagestats` + `dumpsys power` 3 套命令，5 秒定位"app 被冻属于 Doze 还是 Standby"。

### 10.2 速查命令

```bash
# 1. Doze 状态
adb shell dumpsys deviceidle

# 2. App Standby 状态
adb shell dumpsys usagestats

# 3. PowerManager 状态
adb shell dumpsys power

# 4. 加 whitelist
adb shell dumpsys deviceidle whitelist +<pkg>

# 5. 强制 ACTIVE bucket
adb shell am set-idle <pkg> false

# 6. 强制 NEVER bucket (测试用)
adb shell am set-idle <pkg> true

# 7. 看 job
adb shell dumpsys jobscheduler | grep -A 5 "<pkg>"

# 8. 跑 Doze 状态机
adb shell dumpsys deviceidle force-idle
```

### 10.3 实战模板

```java
// ✅ AOSP 17 app 端推荐方案
// 1. 推送: 用 FCM (Doze 下可推送)
// 2. 长任务: 用 WorkManager (自动适配 Doze)
// 3. 即时任务: 用 Foreground Service + startForeground()
// 4. 网络: 用 JobScheduler + setRequiredNetworkType()

// 5. 引导用户加电池优化白名单
Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
intent.setData(Uri.parse("package:" + getPackageName()));
startActivity(intent);
```

### 10.4 自检

- [ ] Doze 6 状态机迁移条件 + 时间窗口能否口述？
- [ ] App Standby 5 bucket 算法 + 配额能否口述？
- [ ] 4 类 whitelist 机制 + 命令能否口述？
- [ ] app 被冻 5 类根因 + 修法能否口述？
- [ ] AOSP 12 doze-adj + AOSP 17 PowerSavePredictor 是否了解？
