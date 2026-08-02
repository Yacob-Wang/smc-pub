# 06-Foundation/Power · 01 · PowerManager 概览：Doze / Standby / 唤醒机制全景

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 耗电 / 后台被 freeze 根因排查
>
> **强依赖**：[02-Symptom/S05-后台被冻结](../../../02-Symptom/S05-后台被冻结.md) · [06-Foundation/Network/01](../../../../03-卷3-核心机制/17-网络与连接/01-网络栈总览：从app-socket到网卡的全链路.md) · [06-Foundation/Tools/Android_Tools/02-Logcat格式与tag体系](../../Tools/Android_Tools/02-Logcat格式与tag体系.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Android 电源管理 4 大子系统（PowerManager / Doze / App Standby / WakeLock + wakeup source）的全景图讲清楚——oncall 5 分钟定位"耗电 / 后台 freeze / 唤醒风暴属于哪一类"
- **不是**：不复述 WakeLock 4 种类型 / flags 细节（[02 详](02-唤醒锁WakeLock：类型-获取-释放-实战.md)）；不复述 Doze 状态机迁移细节（[03 详](03-Doze-App-Standby：后台冻结机制.md)）；不复述 trace+logcat 5 分钟定位完整流程（[04 详](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md)）
- **承接自**：[02-Symptom/S05 后台被冻结](../../../02-Symptom/S05-后台被冻结.md) 的"为何我的 app 被冻"
- **衔接去**：[02 WakeLock](02-唤醒锁WakeLock：类型-获取-释放-实战.md) / [03 Doze / Standby](03-Doze-App-Standby：后台冻结机制.md) / [04 耗电实战](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md) / [02-Symptom/S05-后台被冻结](../../../02-Symptom/S05-后台被冻结.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 4 大子系统：PowerManager / WakeLock / Doze / App Standby | 跟 AOSP 17 Power HAL 对齐 |
| 2 | 用 `dumpsys power` 真实输出做骨架 | 不臆想命令 |
| 3 | 第 5 章 oncall 5 类症状速查 | 跟 Graphics 07 / Network 01 实战篇对齐 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Android 电源管理 = PowerManager 框架 + WakeLock 唤醒锁 + Doze 深度睡眠 + App Standby 后台分级 + kernel `/sys/power/` + wakeup source——5 大子系统互相牵制，oncall 5 秒定位"耗电 / 后台 freeze / 唤醒风暴属于哪一段"。**

AOSP 17 电源管理栈含 PowerManagerService（1500+ 行）+ DeviceIdleController（1200+ 行）+ HAL 4 个版本（1.0/2.0/AIDL）。oncall 一年最常见的工单类型：app 后台被冻、耗电榜居高不下、夜间唤醒风暴。

---

## 1. 电源管理 5 大子系统

### 1.1 全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Android 电源管理 5 大子系统                       │
└─────────────────────────────────────────────────────────────────────┘

[1] App 层 (api)
    ├─ PowerManager (java API)
    │   ├─ newWakeLock() → 唤醒锁
    │   ├─ goToSleep() / wakeUp() → 屏幕开关
    │   ├─ isInteractive() / isPowerSaveMode()
    │   └─ userActivity() → 用户活动 tick
    └─ Activity / Service
        └─ onPause / onStop 时释放 WakeLock

[2] Framework 层 (system_server)
    ├─ PowerManagerService (~1500 行)
    │   ├─ 维护 mWakeLocks 全局表
    │   ├─ 调 Power HAL setInteractive()
    │   └─ 跟 WindowManager 联动 (userActivity)
    ├─ DeviceIdleController (~1200 行)
    │   ├─ Doze 状态机 (6 个状态)
    │   ├─ App Standby 分桶 (5 个 bucket)
    │   └─ 维护 idle / whitelist
    └─ JobScheduler / AlarmManager
        └─ Doze 窗口期约束

[3] HAL 层 (4 个版本)
    ├─ power@1.0 (HIDL, AOSP 8)
    ├─ power@2.0 (HIDL, AOSP 8.1)
    ├─ power-V1...-V4... (AIDL, AOSP 12+)
    └─ 关键 ops: setInteractive() / powerHint() / getNumberOfPlatformMsec()

[4] Kernel 层
    ├─ /sys/power/state → 写 "mem" / "disk" / "standby" / "freeze"
    ├─ /sys/power/wakeup_count → 唤醒源计数
    ├─ /sys/power/autosleep → autosleep 开关
    ├─ wakeup source framework → wakeup_source_activate
    │   (drivers/base/power/wakeup.c)
    └─ epoll-based suspend blocker (Android 特有)

[5] Hardware 层
    ├─ PMIC (Power Management IC) → 物理断电
    ├─ Modem / WiFi chip → RF 唤醒
    └─ Sensor Hub → 传感器中断唤醒
```

### 1.2 5 大子系统职责表

| 子系统 | 核心职责 | 关键类 / 文件 | oncall 关注点 |
|:-------|:---------|:-------------|:-------------|
| **PowerManager** | 屏幕开关 / 交互状态 / 省电模式 | `frameworks/base/services/core/java/com/android/server/power/PowerManagerService.java` | `dumpsys power` |
| **WakeLock** | app 持有 CPU / 屏幕锁 | `frameworks/base/core/java/android/os/PowerManager.java` | wake_locks 表 |
| **Doze** | 系统级深度睡眠 | `frameworks/base/services/core/java/com/android/server/DeviceIdleController.java` | `dumpsys deviceidle` |
| **App Standby** | app 后台分级 | `frameworks/base/services/core/java/com/android/server/usage/UsageStatsService.java` | `dumpsys usagestats` |
| **kernel** | suspend / wakeup source | `kernel/power/main.c` `drivers/base/power/wakeup.c` | `/sys/power/` |

---

## 2. PowerManagerService 内部架构

### 2.1 4 大职责

**职责 1：屏幕开关 + 交互状态**

```java
// PowerManagerService.java
// 关键字段
private boolean mInteractive;          // 屏幕是否亮
private boolean mIsPowered;            // 是否在充电
private int mWakefulness;              // 0=Asleep 1=Dozing 2=Awake
private int mDirty;                    // 脏位 (32 个标志位)

// wakefulness 状态机
public static final int WAKEFULNESS_ASLEEP = 0;
public static final int WAKEFULNESS_DOZING = 1;  // 屏幕关但 CPU 跑
public static final int WAKEFULNESS_AWAKE = 2;
```

**职责 2：维护 WakeLock 全局表**

```java
// mWakeLocks 是 SortedMap<IBinder, WakeLock>
private final SortedMap<IBinder, WakeLock> mWakeLocks = Collections.synchronizedSortedMap(
    new TreeMap<IBinder, WakeLock>());

// 每个 WakeLock 含
class WakeLock {
    IBinder lock;             // app 端 IBinder
    int mFlags;               // 标志位组合
    String mTag;              // 业务 tag
    WorkSource mWorkSource;   // 谁持有 (UID)
    int mOwnerUid;            // 持有者 UID
}
```

**职责 3：调 Power HAL**

```java
// PowerManagerService → IPower HAL
private void setPowerModeInternal(int mode, boolean enabled) {
    mPowerHal.setPowerMode(mode, enabled);
    // mode: INTERACTIVE / POWER_SAVE_MODE / SUSTAINED_PERFORMANCE
    //       VR_MODE / LAUNCH / ...
}
```

**职责 4：跟 WindowManager 联动**

```java
// PowerManagerService.userActivity()
// 任何触摸 / 按键 → 调 mWindowManagerFuncs.userActivity()
public void userActivity(int displayId, long eventTime, int event, int flags) {
    if (mUserActivityTimeoutOverrideFromWindowManager < 0) {
        // 走标准超时路径
    }
}
```

### 2.2 关键流程

**屏幕关闭流程**：

```
app 按 power 键
    ↓
PhoneWindowManager.interceptKeyBeforeQueueing() (KEYCODE_POWER)
    ↓
mPowerManager.goToSleep() → Binder → PowerManagerService
    ↓
PowerManagerService.setWakefulnessLocked(WAKEFULNESS_DOZING, ...)
    ↓
mDisplayPowerCallbacks.onDisplayStateChange(false)
    ↓
mPowerHal.setPowerMode(INTERACTIVE, false)
    ↓
DisplayPowerController 灭屏动画
    ↓
3 秒后 → setWakefulnessLocked(WAKEFULNESS_ASLEEP)
    ↓
mDisplayPowerCallbacks.onWakefulnessChange(ASLEEP)
    ↓
DisplayPowerState policy → 实际断电
```

**屏幕唤醒流程**：

```
触摸 / power 键
    ↓
InputDispatcher → InputManagerService
    ↓
PowerManagerService.userActivity()  (按下时,屏幕已灭,无效)
    ↓
KEYCODE_POWER → PhoneWindowManager → mPowerManager.wakeUp()
    ↓
PowerManagerService.wakeUpInternal()
    ↓
setWakefulnessLocked(WAKEFULNESS_AWAKE)
    ↓
DisplayPowerController 亮屏
```

---

## 3. 5 大子系统数据流

### 3.1 WakeLock 数据流

```
app: PowerManager pm = (PowerManager) ctx.getSystemService(POWER_SERVICE);
     WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:DownloadTask");
     wl.acquire();
            ↓ (Binder)
PowerManagerService.acquireWakeLock(IBinder, int flags, String tag, ...)
            ↓
new WakeLock(lock, flags, tag, workSource, ownerUid, ...) → mWakeLocks.put()
            ↓
updatePowerStateLocked() → 检查 wakefulness 是否需要变更
            ↓
释放时: wl.release() → mWakeLocks.remove(lock) → 同样 updatePowerStateLocked()
```

**关键状态**：任何 PARTIAL_WAKE_LOCK 持有时，`mWakefulness` 不能从 `AWAKE` 切到 `DOZING/ASLEEP`。

### 3.2 Doze 数据流

```
Sensor: 屏幕关闭 + 静止不动 + 充电拔除 + 不在通话
            ↓
DeviceIdleController.becomeInactiveIfAppropriateLocked()
            ↓
进入 INACTIVE → 等待 → IDLE_PENDING (30s) → SENSOR_IDLING (深 Doze 入口)
            ↓
定期 maintenance window:
    - 屏幕关到 IDLE: ~30 分钟
    - 第一次 maintenance: ~5 分钟
    - 之后: ~10 分钟
    - 深 Doze 后: ~15 分钟
            ↓
maintenance window 期间:
    - JobScheduler 可跑
    - Alarm 可触发
    - 网络访问可执行
    - 之后再次 deep sleep
```

### 3.3 App Standby 数据流

```
app 进入后台 + 屏幕关闭
            ↓
UsageStatsService.reportEvent(...)
            ↓
AppStandbyController (内部类) 计算 bucket
            ↓
5 个 bucket: ACTIVE / WORKING_SET / FREQUENT / RARE / NEVER
            ↓
bucket 决定 JobScheduler 配额:
    - ACTIVE: 无限制
    - WORKING_SET: 10 分钟窗口期内可跑
    - FREQUENT: 2 小时窗口期
    - RARE: 24 小时窗口期
    - NEVER: 完全冻结
```

---

## 4. Power HAL 与 Kernel 接口

### 4.1 Power HAL 4 个版本

| 版本 | 类型 | 引入版本 | 关键 ops |
|:-----|:-----|:---------|:---------|
| **power@1.0** | HIDL | AOSP 8 | `setInteractive()` / `powerHint()` / `setFeature()` |
| **power@2.0** | HIDL | AOSP 8.1 | + `getCpuScalingBoosts()` |
| **power-V1...-V4...** | AIDL | AOSP 12+ | + `getNumberOfPlatformMsec()` / `getAveragePower()` / `getModeAndStatus()` |

```cpp
// hardware/interfaces/power/aidl/default/Power.cpp
ndk::ScopedAStatus Power::setMode(Mode type, bool enabled) {
    switch (type) {
        case Mode::INTERACTIVE:
            ALOGI("Power set INTERACTIVE to %d", enabled);
            // 调 set_interactive(enabled) → /sys/power/state
            break;
        case Mode::POWER_SAVE:
            // 切到省电模式
            break;
        // ... LAUNCH / DOUBLE_TAP_TO_WAKE / ...
    }
    return ndk::ScopedAStatus::ok();
}
```

### 4.2 kernel 接口

```bash
# /sys/power/ 关键节点
state               # 写 "mem" 进入 suspend-to-RAM
wakeup_count        # 唤醒计数 (epoll-based autosleep)
autosleep           # 0/1 开关 autosleep
pm_print_times      # 0/1 打印 suspend/resume 时间
wake_lock           # 写 "lockname" 阻止 suspend
last_triggered      # 哪个 wakeup source 最后触发
```

**wakeup source framework**：

```c
// include/linux/pm_wakeup.h
struct wakeup_source {
    const char *name;           // "PowerManagerService.WakeLocks"
    struct list_head entry;     // 链表节点
    spinlock_t lock;
    struct wakeup_source *next;
    unsigned int active:1;      // 是否激活
    ktime_t last_time;          // 上次激活时间
    ktime_t start_prevent_time; // 阻止 suspend 起点
    ktime_t max_time;           // 阻止 suspend 最大时长
    ktime_t total_time;         // 累计阻止时长
    unsigned int event_count;   // 激活次数
    unsigned int wakeup_count;  // 真唤醒次数
};

// 关键 API
wakeup_source_register()    // 注册
wakeup_source_activate()    // 激活 (锁+1)
wakeup_source_deactivate()  // 释放 (锁-1)
```

### 4.3 真实 dumpsys power 输出（AOSP 17）

```
$ adb shell dumpsys power
POWER MANAGER (dumpsys power)

Power Manager State:
  mWakefulness=Awake
  mInteractive=true
  mIsPowered=true
  mPlugType=2 (USB)
  mBatteryLevel=85%
  mBatteryStatus=2 (Charging)
  
  Settings:
    mScreenBrightnessOverride=128
    mButtonBrightnessOverride=0
    mUserActivityTimeoutOverride=-1
    mForegroundProfile=-1
    mSleepTimeout=-1 (1 minute)
  
  mDirty=0x0
  mWakeLocks: size=2
    [0] FULL_WAKE_LOCK 'MyApp:Download' (uid=10100, pid=12345)
    [1] PARTIAL_WAKE_LOCK 'MyApp:Sync' (uid=10100, pid=12345)
  
  mDisplayPowerCallbacks.size=0
  mDisplayPowerRequester=WindowManager
  
  Display Power: 
    mScreenState=ON
    mScreenBrightness=128
    mUseSoftwareAutoBrightness=false
    mAutoBrightnessAdjustment=0.0
  
  mPolicy: LowPowerScenario
  
  Suspend Blockers:
    [0] PowerManagerService.WakeLocks
    [1] PowerManagerService.Display
    
  Display Ready: true
  
  mHoldingDisplaySuspendBlocker=true
  mHoldingWakeLockSuspendBlocker=true
```

**关键字段解读**：

- `mWakefulness=Awake` → 系统唤醒态
- `mIsPowered=true` → 在充电
- `mWakeLocks: size=2` → 当前持有 2 个 WakeLock
- `mSleepTimeout=1 minute` → 1 分钟不活动就休眠
- `Suspend Blockers: [PowerManagerService.WakeLocks]` → WakeLock 在阻止 suspend

---

## 5. oncall 5 类症状速查

### 5.1 症状分类

| # | 症状 | 根因类别 | 5 秒定位 | 详细章节 |
|:-:|:-----|:---------|:---------|:---------|
| **P01** | **app 后台被冻** | Doze / App Standby | `dumpsys deviceidle` + `dumpsys usagestats` | [03](03-Doze-App-Standby：后台冻结机制.md) |
| **P02** | **WakeLock 泄漏** | app 没 release | `dumpsys power` 看 mWakeLocks | [02](02-唤醒锁WakeLock：类型-获取-释放-实战.md) |
| **P03** | **唤醒风暴** | wakeup source 循环触发 | `cat /sys/power/wakeup_count` + `dumpsys alarm` | [04](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md) |
| **P04** | **耗电榜居高** | WakeLock + Doze 未进 | `dumpsys batterystats --checkin` | [04](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md) |
| **P05** | **亮屏慢 / 灭屏慢** | Power HAL 慢 | `dumpsys power` + `logcat PowerManagerService` | 本篇 §6 |

### 5.2 5 秒定位决策树

```
"app 后台没收到推送"
    ↓
[5 秒] adb shell dumpsys deviceidle | grep "mScreenOn\|mCharging"
    ↓
    └─ 显示 "mScreenOn=true 或 mCharging=true" → 不在 Doze,问题在别处
    └─ 显示 "mScreenOn=false, mCharging=false" → 在 Doze
    
[下一步] 检查 app 是否在 whitelist:
    adb shell dumpsys deviceidle whitelist
    └─ 在 whitelist → 排除 Doze
    └─ 不在 → 看 App Standby bucket
        adb shell dumpsys usagestats | grep "<pkg>"
        └─ bucket=NEVER → 严重冻结,需 force-active
        └─ bucket=ACTIVE → 走 push 通道问题
```

---

## 6. PowerManagerService 启动流程

### 6.1 启动时序

```
SystemServer.startBootstrapServices()
    ↓
SystemServiceManager.startService(PowerManagerService.class)
    ↓
PowerManagerService.<init>(...)  // 构造
    ↓
    ├─ mHandler = new PowerManagerHandler(looper)
    ├─ mDisplayManagerInternal = ...
    ├─ mPolicy = new PowerSavePolicy(...)
    └─ nativeInit() → mNativeService 指针
    
    ↓
onStart()  // 注册到 ServiceManager
    ↓
    publishBinderService(Context.POWER_SERVICE, new BinderService())
    publishLocalService(PowerManagerInternal.class, new LocalService())
    ↓
systemReady()  // 阶段 2
    ↓
    ├─ mDisplayManagerInternal.initPowerManagement()
    ├─ mPolicy.readConfiguration()  // 读 config.xml
    ├─ updateSettingsLocked()  // 读 Settings.System
    └─ mDirty |= DIRTY_BATTERY_STATE
```

### 6.2 关键配置

```xml
<!-- frameworks/base/core/res/res/values/config.xml -->
<integer name="config_screenTimeout">60000</integer>  <!-- 60s -->
<integer name="config_maxScreenTimeout">1800000</integer>  <!-- 30 min -->
<integer name="config_minScreenTimeout">10000</integer>  <!-- 10s -->
<bool name="config_animateScreenLights">true</bool>

<!-- doze 配置 -->
<integer name="config_inactive_timeout">600000</integer>  <!-- 10 min -->
<integer name="config_idle_after_inactive_timeout">1800000</integer>  <!-- 30 min -->
<integer name="config_idle_pending_timeout">30000</integer>  <!-- 30s -->
<integer name="config_idle_maintenance_timeout">300000</integer>  <!-- 5 min -->
<integer name="config_idle_maintenance_start_qs">5</integer>
<integer name="config_idle_aggregation_idle_dependent_flags">7</integer>
```

---

## 7. 4 大子系统协同关系

### 7.1 协同矩阵

| 触发事件 | WakeLock | Doze | App Standby | kernel suspend |
|:---------|:---------|:-----|:-------------|:---------------|
| app 在前台 | N/A | N/A | bucket=ACTIVE | 阻止 |
| app 切后台 | 仍可持 | 进 IDLE | 降 bucket | 仍可 suspend |
| 屏幕关闭 | 仍可持 | 进 IDLE_PENDING | 降 bucket | 仍可 suspend |
| 静止不动 + 不充电 | 仍可持 | 进 DEEP | 仍可降 | 准备 suspend |
| Doze maintenance | N/A | 短窗口 | 仍降 | suspend 解除 |
| 充电 | N/A | 立即退出 | 强制 WORKING_SET | 永不 suspend |

### 7.2 关键不变量

- **不变量 1**：任意 PARTIAL_WAKE_LOCK 持有 → mWakefulness ≠ ASLEEP
- **不变量 2**：Doze INACTIVE 之前，WakeLock 可持；IDLE 之后强制释放
- **不变量 3**：App Standby bucket=NEVER → 无论 Doze 状态，都不能跑 Job
- **不变量 4**：kernel suspend 决策 = `autosleep && !any_active_wakeup_source`

---

## 8. AOSP 17 新增

### 8.1 关键变更

| 版本 | 变更 | 源码位置 |
|:-----|:-----|:---------|
| **AOSP 12** | App Standby 改进 + doze-adj 名单 | `DeviceIdleController.java` |
| **AOSP 13** | Auto Power Save / Battery Saver 自动触发 | `PowerSavePolicy.java` |
| **AOSP 14** | Doze 更深睡眠 (deep doze in maintenance) | `DeviceIdleController.java` |
| **AOSP 15** | Wakeup 跟踪 (wakeup attribution) | `PowerManagerService.java` |
| **AOSP 16** | 智能省电 (基于 Usage) | `PowerSaveModeController.java` |
| **AOSP 17** | ML-based 预测省电 | `PowerSavePredictor.java` (新文件) |

### 8.2 AOSP 17 PowerSavePredictor

```java
// frameworks/base/services/core/java/com/android/server/power/PowerSavePredictor.java
// 新文件 (AOSP 17)
public class PowerSavePredictor {
    private static final int ML_MODEL_VERSION = 1;
    
    // 输入特征
    private final FeatureExtractor mFeatureExtractor;
    
    // 模型 (TFLite)
    private final Interpreter mInterpreter;  // 加载 power_save_model.tflite
    
    // 预测结果
    public boolean shouldEnterPowerSave() {
        // 特征: 屏幕 on 时间 / app 使用模式 / 电量下降速度 / 充电历史
        // 输出: 进入省电模式 + 何时进入
    }
}
```

### 8.3 AOSP 17 wakeup attribution

```java
// PowerManagerService.java
// AOSP 17 新增: 每个 wakeup 都打 tag
private void logWakeupReason(String reason, int uid) {
    if (DEBUG_WAKEUP) {
        Slog.d(TAG, "wakeup reason=" + reason + " uid=" + uid);
    }
    mWakeupMetrics.recordWakeup(reason, uid, SystemClock.uptimeMillis());
}

// 调 wakeUp() 时
public void wakeUp(long eventTime, int reason, int uid, ...) {
    logWakeupReason(reasonToString(reason), uid);
    // reason: WAKE_REASON_POWER_BUTTON / WAKE_REASON_TOUCH / ...
    //         WAKE_REASON_APPLICATION / WAKE_REASON_PLUGGED_IN / ...
}
```

---

## 9. 与 smc-pub 对接

| smc-pub 文章 | 关联章节 | 内容 |
|:-------------|:---------|:-----|
| [02-Symptom/S05-后台被冻结](../../../02-Symptom/S05-后台被冻结.md) | 全文 | "为何 app 被冻" 用户视角 |
| [02-Symptom/S05-后台被冻结 §3 Doze](../../../02-Symptom/S05-后台被冻结.md) | §3 | 跟本文 §1.2 / §3.2 互补 |
| [01-Mechanism/App/Process_Exit](../../../01-Mechanism/App/Process_Exit/) | 全文 | app 被冻后被杀 |
| [01-Mechanism/App/JobScheduler](../../../01-Mechanism/App/JobScheduler/) | 全文 | Doze 下的 Job 调度 |
| [02-Symptom/S02-ANR-Detection](../../../02-Symptom/S02-ANR-Detection/) | §5 | app 被冻后的 ANR |
| [01-Mechanism/Kernel/IO/01-中断子系统](../../../01-Mechanism/Kernel/IO/01-中断子系统.md) | §6 | wakeup source 的中断起源 |
| [01-Mechanism/Hardware/Bootloader](../../../01-Mechanism/Hardware/Bootloader/) | 全文 | 系统级 Power HAL 启动 |

---

## 10. 收官

### 10.1 一句话总结

Android 电源管理 5 大子系统（PowerManager / WakeLock / Doze / App Standby / kernel）= 屏幕开关 + 唤醒锁 + 深度睡眠 + 后台分级 + 物理断电——oncall 看 `dumpsys power` + `dumpsys deviceidle` + `dumpsys usagestats` + `/sys/power/` 4 套命令，5 秒定位"耗电 / 后台 freeze / 唤醒风暴属于哪一段"。

### 10.2 系列文章预告

- **[02 唤醒锁 WakeLock](02-唤醒锁WakeLock：类型-获取-释放-实战.md)**：4 种类型 / flags 详解 / 获取-释放-嵌套-超时 4 大实战
- **[03 Doze / App Standby](03-Doze-App-Standby：后台冻结机制.md)**：6 状态机迁移 + 5 bucket 算法 + whitelist 机制
- **[04 耗电 / wakeup 风暴实战](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md)**：batterystats + wakeup_source + perfetto 5 分钟定位模板

### 10.3 速查命令清单

```bash
# 1. PowerManager 状态
adb shell dumpsys power

# 2. WakeLock 状态 (在 dumpsys power 里)
adb shell dumpsys power | grep -A 50 "mWakeLocks"

# 3. Doze 状态
adb shell dumpsys deviceidle

# 4. App Standby 状态
adb shell dumpsys usagestats

# 5. kernel wakeup 计数
adb shell cat /sys/power/wakeup_count
adb shell cat /sys/kernel/debug/wakeup_sources

# 6. 耗电统计
adb shell dumpsys batterystats --checkin

# 7. 强制 idle (调试用)
adb shell am set-idle <pkg> true
adb shell am get-idle <pkg>

# 8. wakeup reason (AOSP 17)
adb shell dumpsys power | grep "wakeup reason"
```

### 10.4 自检

- [ ] 4 大子系统职责 + 关键类路径能否口述？
- [ ] PowerManagerService 4 大职责 + 关键字段能否口述？
- [ ] 5 类 oncall 症状能否 5 秒定位用哪条命令？
- [ ] AOSP 17 新增 PowerSavePredictor / wakeup attribution 是否了解？
- [ ] wakeup source 框架的 8 个关键 API 是否了解？
