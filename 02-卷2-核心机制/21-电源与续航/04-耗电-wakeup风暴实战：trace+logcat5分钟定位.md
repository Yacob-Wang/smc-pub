# 06-Foundation/Power · 04 · 耗电 / wakeup 风暴实战：trace + logcat 5 分钟定位

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 耗电 / 唤醒风暴实战
>
> **强依赖**：[01 PowerManager 概览](01-PowerManager概览：Doze-Standby-唤醒机制全景.md) · [02 WakeLock](02-唤醒锁WakeLock：类型-获取-释放-实战.md) · [03 Doze / App Standby](03-Doze-App-Standby：后台冻结机制.md) · [06-Foundation/Graphics/07 卡顿实战](../19-显示与渲染/07-卡顿-jank实战：trace+logcat5分钟定位.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把耗电 / wakeup 风暴 4 大真实案例（WakeLock 泄漏 / alarm 风暴 / sensor 风暴 / Doze 推迟）的完整排查流程讲清楚——oncall 5 分钟定位"耗电源头"
- **不是**：不复述 WakeLock 类型 / flags（[02 §1](02-唤醒锁WakeLock：类型-获取-释放-实战.md) 详）；不复述 Doze 状态机（[03 §1](03-Doze-App-Standby：后台冻结机制.md) 详）；不复述 perfetto 基础（[Graphics 07 §2](../19-显示与渲染/07-卡顿-jank实战：trace+logcat5分钟定位.md) 详）
- **承接自**：[02 §6 5 类 oncall 排查](02-唤醒锁WakeLock：类型-获取-释放-实战.md) + [03 §8 5 类 oncall 排查](03-Doze-App-Standby：后台冻结机制.md)
- **衔接去**：[01-Mechanism/App/Process_Exit](../../../01-Mechanism/App/Process_Exit/) / [02-Symptom/S06-耗电](../../../02-Symptom/S06-耗电.md)（待写） / [01-Mechanism/Kernel/IO/01-中断子系统](../../../01-Mechanism/Kernel/IO/01-中断子系统.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 5-step 模板：抓现场 → 5 grep → 5 分钟定位 → fix 方向 → 报告模板 | 跟 Graphics 07 实战篇对齐 |
| 2 | 4 大真实 case：WakeLock 泄漏 / alarm 风暴 / sensor 风暴 / Doze 推迟 | oncall 80% 工单 |
| 3 | 第 6 章 AOSP 17 PowerStats HAL 整合 | 系列收官 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**耗电 / wakeup 风暴 = wakeup_source 累计事件 / WakeLock 长持 / alarm 反复触发 / sensor 高频采样——4 大真实 case + 5-step 模板（抓现场 → 5 grep → 5 分钟定位 → fix 方向 → 报告模板）——oncall 5 秒定位"谁在偷偷唤醒 + 谁在偷偷耗电"。**

AOSP 17 电源管理栈 oncall 第三大工单来源：用户反馈"昨晚没插电,早上一看 30% 电没了" → 几乎必是 wakeup 风暴 + WakeLock 泄漏组合拳。

---

## 1. 5-step 通用模板

### 1.1 5-step 总览

```
[Step 1] 抓现场 (30s)
    ↓
[Step 2] 5 grep 必跑 (5 × 5s = 25s)
    ↓
[Step 3] 5 分钟定位 (5 min)
    ↓
[Step 4] fix 方向 (5 min)
    ↓
[Step 5] 报告模板 (10 min)
```

### 1.2 Step 1: 抓现场（30 秒）

```bash
# 1. 抓 bugreport (含 dumpsys + logcat)
$ adb bugreport /tmp/bugreport.zip
# 或后台抓
$ adb shell bugreport > /tmp/bugreport.zip &

# 2. 抓 wakeup source 实时
$ adb shell "cat /sys/kernel/debug/wakeup_sources" > /tmp/wakeup.txt

# 3. 抓 batterystats
$ adb shell dumpsys batterystats --checkin > /tmp/batterystats.txt

# 4. 抓 perfetto trace (30s)
$ adb shell perfetto -o /data/local/tmp/trace.perfetto \
    -t 30s -b 64mb sched freq idle am wm gfx view power

# 5. 抓 logcat (后台)
$ adb logcat -v time > /tmp/logcat.txt &
```

### 1.3 Step 2: 5 grep 必跑（25 秒）

```bash
# grep 1: 找 WakeLock 列表
$ adb shell dumpsys power | grep -A 50 "mWakeLocks"
# 看哪个 app 持锁, 持多久, refcount

# grep 2: 找 wakeup 排行
$ adb shell "cat /sys/kernel/debug/wakeup_sources" | sort -k4 -n -r | head -10
# 看哪个 wakeup source 事件数最多

# grep 3: 找 alarm 触发排行
$ adb shell dumpsys alarm | head -100
# 看哪个 alarm 反复触发

# grep 4: 找 sensor 采样排行
$ adb shell dumpsys sensorservice | head -100
# 看哪个 sensor 采样率高

# grep 5: 找 batterystats app 排行
$ adb shell dumpsys batterystats | grep "Estimated" | head -20
# 看哪个 app 耗电占比最高
```

### 1.4 Step 3: 5 分钟定位

```
[1min] 看 wakeup source → 找出 TOP 5
[1min] 看 WakeLock 列表 → 找出长持
[1min] 看 alarm → 找出反复触发的
[1min] 看 sensor → 找出高频采样的
[1min] 看 batterystats → 找耗电 TOP 5
   ↓
交叉对照 → 找出"元凶"
```

### 1.5 Step 4: fix 方向

| 类型 | 修法 |
|:-----|:-----|
| **WakeLock 泄漏** | try-finally + acquire(timeout) |
| **alarm 风暴** | setExact → setAndAllowWhileIdle / 用 JobScheduler |
| **sensor 风暴** | 降低采样率 + 用 batching / 加 debounce |
| **Doze 推迟** | 加 whitelist / 改 push 通道 / 改 JobScheduler |
| **后台 Service 长持** | 改 Foreground Service + notification / WorkManager |

### 1.6 Step 5: 报告模板

```markdown
# 耗电 / Wakeup 风暴 oncall 报告

## 1. 现象
- 用户反馈：[XXX]
- 影响版本：[XXX]
- 出现频率：[XXX]

## 2. 现场
- bugreport: [附件]
- 抓取时间: [XXX]
- 设备: [XXX]

## 3. 定位过程
### 3.1 5 grep 结果
- WakeLock TOP 1: [com.xxx, tag=xxx, refcount=N]
- wakeup_source TOP 1: [name, event_count=N, wakeup_count=M]
- alarm TOP 1: [com.xxx, count=N, intent=xxx]
- sensor TOP 1: [name, rate=N Hz]
- batterystats TOP 1: [com.xxx, 30%]

### 3.2 交叉对照
- [com.xxx] 持有 WakeLock [tag] 没释放 → 同时 alarm 反复触发 → wakeup_count 暴涨
- 根因: [业务代码 X 类 Y 函数 acquire 没 release]

## 4. fix 方案
- 代码层: [具体修改]
- 验证方法: [test case]
- 风险评估: [XXX]

## 5. 预防
- 门禁: [XXX 静态扫描 + 动态检测]
- 监控: [XXX metric]
- 复盘: [XXX]
```

---

## 2. Case 1: WakeLock 泄漏导致整夜耗电

### 2.1 现象

- 用户反馈：昨晚 100% 电睡觉,今早 30% 电
- 影响：所有 app / 系统待机耗电
- 频率：100% 必现

### 2.2 抓现场

```bash
# 1. 抓 bugreport
$ adb bugreport > /tmp/case1_bugreport.zip

# 2. 抓 wakeup source
$ adb shell "cat /sys/kernel/debug/wakeup_sources" > /tmp/case1_wakeup.txt
# 输出 (节选):
# name                          active_count  event_count  wakeup_count  expire_count  active_since  total_time  max_time  prevent_suspend_time
# PowerManagerService.WakeLocks  100  200  150  50  0  0  12345678  0
# alarm_rtc                      50  300  200  100  0  0  5000000  0
# sensor_ind                     10  1000 500  200  0  0  8000000  0  ← 异常!
```

### 2.3 5 grep 必跑

```bash
# grep 1: WakeLock 列表
$ adb shell dumpsys power | grep -A 20 "mWakeLocks"
# [0] PARTIAL_WAKE_LOCK 'MyApp:Download' (uid=10100, pid=12345, refcount=1, ...)
# [1] PARTIAL_WAKE_LOCK 'MyApp:Sync' (uid=10100, pid=12345, refcount=1, ...)
# [2] PARTIAL_WAKE_LOCK 'MyApp:Download' (uid=10100, pid=67890, refcount=1, ...)
# ↑ 看到 3 个 WakeLock, 其中 2 个相同 tag → 嵌套错误

# grep 2: wakeup source
$ adb shell "cat /sys/kernel/debug/wakeup_sources" | sort -k3 -n -r | head -5
# PowerManagerService.WakeLocks  100  200  150
# sensor_ind                       10  1000 500  ← 异常: 1000 事件

# grep 3: alarm
$ adb shell dumpsys alarm | head -50
# 看到 MyApp:Sync alarm 触发 100+ 次

# grep 4: sensor
$ adb shell dumpsys sensorservice | head -50
# 看到 accelerometer 在 200 Hz 采样

# grep 5: batterystats
$ adb shell dumpsys batterystats | grep "Estimated" | head -5
# com.myapp 30% ← 耗电 TOP 1
```

### 2.4 5 分钟定位

```
[1min] 看 wakeup source → sensor_ind 事件 1000 → 异常
[1min] 看 WakeLock → MyApp:Download 持有 2 个 refcount=1 → 泄漏
[1min] 看 alarm → MyApp:Sync 触发 100+ 次 → 风暴
[1min] 看 sensor → accelerometer 200Hz → 风暴
[1min] 看 batterystats → com.myapp 30% → 耗电 TOP 1
   ↓
[交叉对照] com.myapp 三个问题同时:
- WakeLock 泄漏 (Download 没 release)
- alarm 风暴 (Sync 反复触发)
- sensor 风暴 (accelerometer 高频)
   ↓
[定位根因] com.myapp 三个 bug → 整夜耗电
```

### 2.5 fix 方向

```java
// Fix 1: WakeLock 加 try-finally + acquire(timeout)
public void onStartCommand(Intent intent, int flags, int startId) {
    WakeLock wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Download");
    wl.acquire(60 * 1000);  // 60s 超时
    try {
        doDownload();
    } finally {
        if (wl.isHeld()) wl.release();
    }
}

// Fix 2: alarm 改 JobScheduler
// ❌ 错误: 反复 setExact
alarmManager.setExact(RTC_WAKEUP, time, pendingIntent);
// 修法: 改 JobScheduler
JobInfo ji = new JobInfo.Builder(123, js)
    .setMinimumLatency(5 * 60 * 1000)
    .build();
js.schedule(ji);

// Fix 3: sensor 降低采样率 + batching
// ❌ 错误: 200 Hz 采样
sensorManager.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_FASTEST);
// 修法: 50 Hz + batching
sensorManager.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_GAME);
sensorManager.registerListener(listener, sensor, 20000, 1000000);  // 20ms, 1s batching
```

### 2.6 预防

- **门禁**: Lint 规则禁止 bare `acquire()` (必须有 timeout)
- **监控**: 上报每个 WakeLock 持有时长
- **复盘**: 接入 PowerStats HAL (AOSP 17 新)

---

## 3. Case 2: alarm 风暴导致 Doze 推迟

### 3.1 现象

- 用户反馈：插着电手机烫手
- 影响：充电慢、耗电大
- 频率：100% 必现

### 3.2 抓现场

```bash
# 1. 抓 dumpsys alarm
$ adb shell dumpsys alarm | head -200 > /tmp/case2_alarm.txt
# 输出 (节选):
# Batch{...} num=15
#   RTC_WAKEUP #0: Alarm{... type=RTC_WAKEUP tag=MyApp:Sync}
#       operation=PendingIntent{... com.myapp}
#       when=+30s
#       listenerTag=MyApp:Sync
#   RTC_WAKEUP #1: Alarm{... type=RTC_WAKEUP tag=MyApp:Sync}
#       when=+1m
#   ... 100+ alarms
# ↑ 看到 100+ 相同 tag 的 alarm

# 2. 抓 wakeup_count
$ adb shell cat /sys/power/wakeup_count
# 12345  ← 整夜累积 1.2 万次唤醒
```

### 3.3 5 grep 必跑

```bash
# grep 1: alarm 按 tag 排行
$ adb shell dumpsys alarm | grep "tag=" | sort | uniq -c | sort -rn | head -10
# 100 MyApp:Sync  ← 异常: 100 个相同 tag
# 5 com.system
# 3 com.other

# grep 2: alarm 触发频率
$ adb shell dumpsys alarm | grep "when=" | head -20
# when=+30s  ← 30 秒一次
# when=+1m   ← 1 分钟一次
# when=+2m   ← 2 分钟一次
# 每次都被 setExact() 重置 → 整夜触发

# grep 3: Doze 状态
$ adb shell dumpsys deviceidle | grep "mState"
# mState=2 (IDLE_PENDING)  ← 卡在 IDLE_PENDING 进不去 IDLE
# 原因: alarm 反复触发,每次都唤醒系统

# grep 4: wakeup_count
$ adb shell cat /sys/power/wakeup_count
# 12345  ← 1.2 万次
# 整夜 (8h) 平均 1.5 次/分钟

# grep 5: batterystats alarm 排行
$ adb shell dumpsys batterystats | grep -A 2 "Alarm" | head -50
# com.myapp 100 次 → TOP 1
```

### 3.4 5 分钟定位

```
[1min] 看 dumpsys alarm → MyApp:Sync 100+ 个 → 异常
[1min] 看 alarm 频率 → 30s / 1m / 2m → 高频
[1min] 看 Doze → mState=IDLE_PENDING → 进不去 IDLE
[1min] 看 wakeup_count → 1.2 万次
[1min] 看 batterystats → com.myapp alarm 100 次 → TOP 1
   ↓
[根因] com.myapp 反复 setExact → 100+ alarm → 整夜唤醒 1.2 万次
   ↓
[修法] 改用 JobScheduler
```

### 3.5 fix 方向

```java
// ❌ 错误: 反复 setExact
public void scheduleNext() {
    alarmManager.setExact(RTC_WAKEUP, nextTime, pendingIntent);
    // 业务代码每隔几分钟重置一次
    // → 100+ alarm 同时存在
    // → 整夜唤醒
}

// ✅ 修法 1: 改用 JobScheduler (Doze 兼容)
public void scheduleNext() {
    JobInfo ji = new JobInfo.Builder(JOB_ID, jobScheduler)
        .setMinimumLatency(5 * 60 * 1000)  // 5 min
        .setOverrideDeadline(10 * 60 * 1000)  // 10 min
        .build();
    jobScheduler.schedule(ji);
    // JobScheduler 自动合并相同 job
    // Doze 下也能跑
}

// ✅ 修法 2: 合并 alarm (oneShot 替代 repeating)
public void scheduleNext() {
    alarmManager.set(AlarmManager.ELAPSED_REALTIME_WAKEUP, nextTime, pendingIntent);
    // set() 替代 setExact() → Doze 下会被合并
}

// ✅ 修法 3: 取消所有 alarm
public void cleanup() {
    // app 进入后台时取消
    Intent intent = new Intent("com.myapp.SYNC");
    PendingIntent pi = PendingIntent.getBroadcast(this, 0, intent, FLAG_IMMUTABLE);
    alarmManager.cancel(pi);
}
```

### 3.6 预防

- **门禁**: 静态扫描禁止 `setExact()` (除日历/闹钟)
- **监控**: 上报每个 app 的 alarm 总数
- **复盘**: Doze 状态机卡 IDLE_PENDING 是典型 alarm 风暴

---

## 4. Case 3: sensor 风暴导致 Doze 进不去

### 4.1 现象

- 用户反馈：手机睡眠时唤醒屏 (亮屏)
- 影响：耗电 + 用户体验差
- 频率：100% 必现

### 4.2 抓现场

```bash
# 1. 抓 dumpsys sensorservice
$ adb shell dumpsys sensorservice > /tmp/case3_sensor.txt
# 输出 (节选):
# Sensor List:
#   0x00000001: BMA2x2 Accelerometer Non-wakeup | continuous | 200 Hz  ← 异常!
#   0x00000010: BMM150 Magnetometer Non-wakeup | continuous | 50 Hz
#   0x00000100: BMI160 Gyroscope Non-wakeup | continuous | 200 Hz  ← 异常!
#   ...
#   0x00010000: Significant Motion Detector Wakeup | one-shot | on-demand

# 2. 抓 wakeup source
$ adb shell "cat /sys/kernel/debug/wakeup_sources" | sort -k3 -n -r | head -10
# sensor_ind 10 1000 500  ← 1000 事件
```

### 4.3 5 grep 必跑

```bash
# grep 1: sensor 采样率
$ adb shell dumpsys sensorservice | grep "Hz\|Hz" | head -20
# 200 Hz  ← 异常: 200 Hz 是非常高的采样率

# grep 2: sensor 连接数
$ adb shell dumpsys sensorservice | grep "connections" | head -5
# connections: 5  ← 5 个 app 连 accelerometer

# grep 3: wakeup source
$ adb shell "cat /sys/kernel/debug/wakeup_sources" | sort -k3 -n -r | head -5
# sensor_ind 1000  ← 异常

# grep 4: Doze 状态
$ adb shell dumpsys deviceidle | grep "mState"
# mState=2 (IDLE_PENDING)  ← 静止检测失败
# 原因: accelerometer 200Hz 采样 → 持续被判定为"动"

# grep 5: Significant Motion
$ adb shell dumpsys sensorservice | grep "Significant"
# Significant Motion: 0 events in last hour  ← 没动
# 但 accelerometer 1000 事件 → 是 app 主动采样
```

### 4.4 5 分钟定位

```
[1min] 看 sensor 采样率 → accelerometer 200 Hz → 异常
[1min] 看 sensor 连接数 → 5 个 app 连 accelerometer
[1min] 看 wakeup source → sensor_ind 1000 事件
[1min] 看 Doze → mState=IDLE_PENDING → 静止检测失败
[1min] 看 Significant Motion → 0 事件 → 实际没动
   ↓
[根因] 5 个 app 主动采样 accelerometer 200Hz → sensor 持续上报 → 静止检测失败
```

### 4.5 fix 方向

```java
// Fix 1: 降低采样率 (200Hz → 50Hz)
sensorManager.registerListener(listener, accelerometer,
    SensorManager.SENSOR_DELAY_GAME);  // 50 Hz

// Fix 2: 加 batching
sensorManager.registerListener(listener, accelerometer,
    SensorManager.SENSOR_DELAY_NORMAL,  // 200 ms
    1000 * 1000);  // 1 s batching
// batching 让 sensor 在 1 秒内合并上报

// Fix 3: 用 on-change sensor 替代 continuous
Sensor onChangeSensor = sensorManager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER);
sensorManager.registerListener(listener, onChangeSensor,
    SensorManager.SENSOR_DELAY_NORMAL);
// on-change sensor 只在数据变化时上报

// Fix 4: app 切后台时反注册
@Override
protected void onStop() {
    super.onStop();
    sensorManager.unregisterListener(listener);
    // 切后台时立即停止采样
}
```

### 4.6 预防

- **门禁**: Lint 规则禁止 `SENSOR_DELAY_FASTEST` 在 background
- **监控**: 上报 sensor 连接数
- **复盘**: 静止检测失败 = sensor 风暴

---

## 5. Case 4: Doze 推迟导致整夜耗电

### 5.1 现象

- 用户反馈：关屏放一晚掉电 50%
- 影响：电池续航
- 频率：100% 必现

### 5.2 抓现场

```bash
# 1. 抓 dumpsys deviceidle
$ adb shell dumpsys deviceidle > /tmp/case4_idle.txt
# 输出 (节选):
# Current state:
#   mScreenOn=false
#   mCharging=false
#   mState=1 (INACTIVE)  ← 6 小时了还卡在 INACTIVE
#   mStateEnteredTime=21600000  ← 6 小时前进入
#   mInactiveTimeout=1800000  ← 30 min 应进 IDLE_PENDING
# ↑ 6 小时还没进 IDLE_PENDING → 异常

# 2. 抓 wakeup source
$ adb shell "cat /sys/kernel/debug/wakeup_sources" | sort -k7 -n -r | head -10
# 按 total_time 排序
# PowerManagerService.WakeLocks  100  200  150  0  0  5000000  12345678  ← 8h 累计阻止 suspend
# 0  0  0
```

### 5.3 5 grep 必跑

```bash
# grep 1: Doze 状态
$ adb shell dumpsys deviceidle | grep "mState\|mStateEnteredTime"
# mState=1 (INACTIVE)  ← 6 小时了
# mStateEnteredTime=21600000  ← 6 小时前

# grep 2: WakeLock 列表
$ adb shell dumpsys power | grep -A 20 "mWakeLocks"
# [0] PARTIAL_WAKE_LOCK 'MyApp:Sync' (uid=10100, pid=12345, refcount=1, ...)
# [1] PARTIAL_WAKE_LOCK 'MyApp:Heartbeat' (uid=10100, pid=12345, refcount=1, ...)
# ↑ 2 个 WakeLock 阻止进 Doze

# grep 3: wakeup source
$ adb shell "cat /sys/kernel/debug/wakeup_sources" | sort -k3 -n -r | head -5
# PowerManagerService.WakeLocks  200  ← 高

# grep 4: 阻止 suspend 时间
$ adb shell "cat /sys/kernel/debug/wakeup_sources" | sort -k7 -n -r | head -5
# PowerManagerService.WakeLocks  12345678  ← 8h 累计

# grep 5: alarm 触发
$ adb shell dumpsys alarm | grep "MyApp" | head -20
# 看到 30+ MyApp:Sync alarm 触发
```

### 5.4 5 分钟定位

```
[1min] 看 Doze → mState=INACTIVE 6 小时 → 异常
[1min] 看 WakeLock → 2 个长持 → 阻止进 IDLE
[1min] 看 wakeup source → WakeLocks 8h 累计阻止 suspend
[1min] 看 alarm → 30+ MyApp:Sync → 反复触发
[1min] 看 WakeLock history
   ↓
[根因] com.myapp 2 个 WakeLock 长持 + 30+ alarm 反复触发 → Doze 永远进不去
```

### 5.5 fix 方向

```java
// Fix 1: 释放 WakeLock
// ❌ 错误: 长持 WakeLock
wl.acquire();  // 整夜持锁
// 修法: 短持 + acquire(timeout)
wl.acquire(30 * 1000);  // 30s 超时

// Fix 2: alarm 改 set() 替代 setExact()
alarmManager.set(ELAPSED_REALTIME_WAKEUP, time, pi);
// set() 会被 Doze 合并
// setExact() 会反复触发

// Fix 3: app 切后台时清理
@Override
protected void onStop() {
    super.onStop();
    if (wl != null && wl.isHeld()) wl.release();
    alarmManager.cancel(pi);
    sensorManager.unregisterListener(listener);
}
```

### 5.6 预防

- **门禁**: 静态扫描禁止 acquire() 配 acquire(timeout)
- **监控**: Doze 进 INACTIVE 6h 未进 IDLE_PENDING → 告警
- **复盘**: WakeLocks total_time > 4h → 必有问题

---

## 6. AOSP 17 PowerStats HAL（系列收官）

### 6.1 PowerStats HAL 引入

```cpp
// hardware/interfaces/power/stats/aidl/default/PowerStats.cpp
// AOSP 12 引入, AOSP 17 完善
// 整合所有耗电数据源 → 提供统一查询接口
ndk::ScopedAStatus PowerStats::getPowerData(std::vector<PowerData>* _aidl_return) {
    // 1. 从多个 Power Entity 收集数据
    //    - CPU freq / time
    //    - GPU freq / time
    //    - Display power
    //    - Modem power
    //    - WiFi power
    //    - Sensor power
    // 2. 整合后返回
    for (auto& entity : mPowerEntities) {
        PowerData data;
        data.entityName = entity->getName();
        data.entityId = entity->getId();
        data.energyUWs = entity->getEnergyUWs();
        _aidl_return->push_back(data);
    }
    return ndk::ScopedAStatus::ok();
}
```

### 6.2 5 大 Power Entity

| Entity | 数据源 | 关键 metric |
|:-------|:-------|:-----------|
| **CPU** | `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq` | freq × time |
| **GPU** | `/sys/class/devfreq/<gpu>/cur_freq` | freq × time |
| **Display** | `/sys/class/backlight/.../brightness` | brightness × time |
| **Modem** | IPA (QCOM) / RILJ | TX/RX power |
| **WiFi** | `/sys/class/net/wlan0/...` | TX/RX power |

### 6.3 用法

```bash
# 1. 拉 PowerStats
$ adb shell cmd power stats get-data
# 输出: 5 大 Entity 实时耗电

# 2. 拉指定 app 耗电
$ adb shell cmd power stats get-app-power com.myapp
# 输出: CPU + GPU + Display + Modem + WiFi 分项
```

### 6.4 5 大 oncall 工具对比

| 工具 | 维度 | 精度 | 适用 |
|:-----|:-----|:-----|:-----|
| `dumpsys power` | 实时 WakeLock / 状态 | 高 | 当前耗电 |
| `dumpsys batterystats` | 累计 (含 uid) | 中 | 历史耗电 |
| `dumpsys deviceidle` | Doze 状态 | 高 | Doze 推迟 |
| `/sys/power/wakeup_count` | wakeup 计数 | 高 | 唤醒风暴 |
| `cmd power stats` (AOSP 17) | 5 Entity 实时 | 最高 | 整夜耗电 |

---

## 7. oncall 5 大工具箱

### 7.1 5 大工具速查

| # | 工具 | 用途 | 关键命令 |
|:-:|:-----|:-----|:---------|
| 1 | `dumpsys power` | PowerManager / WakeLock | `dumpsys power` |
| 2 | `dumpsys batterystats` | 耗电统计 | `dumpsys batterystats --checkin` |
| 3 | `dumpsys deviceidle` | Doze 状态 | `dumpsys deviceidle` |
| 4 | `dumpsys usagestats` | App Standby | `dumpsys usagestats` |
| 5 | `dumpsys jobscheduler` | Job 状态 | `dumpsys jobscheduler` |
| 6 | `dumpsys alarm` | Alarm 触发 | `dumpsys alarm` |
| 7 | `dumpsys sensorservice` | Sensor 采样 | `dumpsys sensorservice` |
| 8 | `cat /sys/power/wakeup_count` | wakeup 计数 | `cat /sys/power/wakeup_count` |
| 9 | `cat /sys/kernel/debug/wakeup_sources` | wakeup source 详情 | 同上 |
| 10 | `cmd power stats` (AOSP 17) | 5 Entity 实时 | `cmd power stats get-data` |

### 7.2 5 大工具交叉对照

```
"耗电严重"
    ↓
[1] dumpsys batterystats → 找耗电 TOP 5
    ↓
[2] cat /sys/kernel/debug/wakeup_sources → 找 wakeup TOP 5
    ↓
[3] dumpsys power | grep mWakeLocks → 找长持 WakeLock
    ↓
[4] dumpsys alarm | head -100 → 找反复 alarm
    ↓
[5] dumpsys sensorservice | head -100 → 找高频 sensor
    ↓
交叉对照 → 定位根因
```

---

## 8. AOSP 17 新增能力

### 8.1 关键新增

| 能力 | 用途 | 命令 |
|:-----|:-----|:-----|
| **PowerStats HAL** | 5 Entity 实时耗电 | `cmd power stats` |
| **wakeup attribution** | 每个 wakeup 打 uid | `dumpsys power | grep "wakeup reason"` |
| **PowerSavePredictor** | ML 预测进省电 | `dumpsys power | grep "predictor"` |
| **PREVENT_BATTERY_SAVER** flag | 紧急任务不被省电 | 代码层 |
| **force-idle** | 调试用强制进 Doze | `dumpsys deviceidle force-idle` |

### 8.2 wakeup attribution 详解

```java
// PowerManagerService.java
// AOSP 17 wakeup attribution
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

// 调 userActivity() 时
public void userActivity(...) {
    if (DEBUG_WAKEUP) {
        Slog.d(TAG, "userActivity event=" + event + " uid=" + uid);
    }
}
```

### 8.3 AOSP 17 + 5G 协同

```
5G NR (高频段) + Doze
    ↓
AOSP 17 PowerStats 监测 Modem power 异常
    ↓
若 5G 切片 (Slicing) → 自动加 whitelist
```

---

## 9. 与 smc-pub 对接

| smc-pub 文章 | 关联章节 | 内容 |
|:-------------|:---------|:-----|
| [01 PowerManager 概览](01-PowerManager概览：Doze-Standby-唤醒机制全景.md) | §1-7 | 5 大子系统全景 |
| [02 WakeLock](02-唤醒锁WakeLock：类型-获取-释放-实战.md) | §5-6 | WakeLock 泄漏 + 5 类 oncall 模板 |
| [03 Doze / App Standby](03-Doze-App-Standby：后台冻结机制.md) | §5 + §8 | app 被冻 5 类 + 5 oncall 模板 |
| [06-Foundation/Graphics/07 卡顿实战](../19-显示与渲染/07-卡顿-jank实战：trace+logcat5分钟定位.md) | 全文 | 同样的 5-step 模板 (trace + logcat + dumpsys) |
| [06-Foundation/Network/08 诊断工具](../17-网络与连接/08-网络栈诊断工具：tcpdump-ss-netstat-ping.md) | 全文 | 网络诊断对照 |
| [01-Mechanism/App/Process_Exit](../../../01-Mechanism/App/Process_Exit/) | §3 | 后台被冻被杀 |
| [01-Mechanism/Kernel/IO/01-中断子系统](../../../01-Mechanism/Kernel/IO/01-中断子系统.md) | §6 | wakeup source 的中断起源 |
| [02-Symptom/S05-后台被冻结](../../../02-Symptom/S05-后台被冻结.md) | 全文 | "为何 app 被冻" 用户视角 |
| [02-Symptom/S06-耗电](../../../02-Symptom/S06-耗电.md) | 待写 | 耗电症状 (后续补) |

---

## 10. 收官

### 10.1 系列总结

4 篇 PowerManager / 唤醒锁系列收官——oncall 视角的电源管理全景：

- **[01 PowerManager 概览](01-PowerManager概览：Doze-Standby-唤醒机制全景.md)** (612 行) — 5 大子系统全景
- **[02 WakeLock](02-唤醒锁WakeLock：类型-获取-释放-实战.md)** (850 行) — 4 类型 + 11 flags + 4 类泄漏根因
- **[03 Doze / App Standby](03-Doze-App-Standby：后台冻结机制.md)** (743 行) — 6 状态机 + 5 bucket + 5 类冻根因
- **[04 耗电 / wakeup 风暴实战](04-耗电-wakeup风暴实战：trace+logcat5分钟定位.md)** (本篇) — 5-step 模板 + 4 真实 case

### 10.2 一句话总结

耗电 / wakeup 风暴 = 4 大真实 case（WakeLock 泄漏 / alarm 风暴 / sensor 风暴 / Doze 推迟）+ 5-step 模板（抓现场 / 5 grep / 5 分钟定位 / fix 方向 / 报告模板）+ 10 大工具（5 dumpsys + 5 sysfs）——oncall 5 秒定位"谁在偷偷唤醒 + 谁在偷偷耗电"。

### 10.3 速查命令

```bash
# 1. 5 dumpsys 必跑
adb shell dumpsys power
adb shell dumpsys batterystats --checkin
adb shell dumpsys deviceidle
adb shell dumpsys usagestats
adb shell dumpsys jobscheduler

# 2. 5 sysfs 必跑
adb shell cat /sys/power/wakeup_count
adb shell cat /sys/kernel/debug/wakeup_sources
adb shell cat /sys/power/state
adb shell cat /sys/power/autosleep
adb shell cat /sys/power/pm_print_times

# 3. AOSP 17 新增
adb shell cmd power stats get-data
adb shell dumpsys power | grep "wakeup reason"

# 4. 强制 / 调试
adb shell dumpsys deviceidle force-idle
adb shell dumpsys deviceidle step
adb shell am set-idle <pkg> true|false
adb shell dumpsys deviceidle whitelist +<pkg>
```

### 10.4 实战模板

```java
// ✅ AOSP 17 app 端终极防耗电模板

// 1. 推送: FCM (Doze 兼容)
FirebaseMessaging.getInstance().subscribeToTopic("news");

// 2. 长任务: WorkManager
val req = OneTimeWorkRequestBuilder<SyncWorker>()
    .setConstraints(
        Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .setRequiresBatteryNotLow(true)
            .build()
    )
    .build()
WorkManager.getInstance(this).enqueue(req)

// 3. 短任务: WakeLock (必带 timeout + try-finally)
val wl = pm.newWakeLock(PARTIAL_WAKE_LOCK, "MyApp:Task")
wl.acquire(30_000)
try { doTask() } finally { if (wl.isHeld()) wl.release() }

// 4. 切后台立即清理
override fun onStop() {
    super.onStop()
    if (::wl.isInitialized && wl.isHeld) wl.release()
    sensorManager.unregisterListener(listener)
    alarmManager.cancel(pi)
}
```

### 10.5 自检

- [ ] 5-step 模板（抓现场 / 5 grep / 5 分钟定位 / fix / 报告）能否口述？
- [ ] 4 大真实 case 的现象 / 抓现场 / 5 grep / 定位 / 修法能否默写？
- [ ] 10 大工具（5 dumpsys + 5 sysfs）能否默写？
- [ ] AOSP 17 PowerStats HAL / wakeup attribution 是否了解？
- [ ] AOSP 17 app 端防耗电 4 套方案（FCM / WorkManager / WakeLock / cleanup）能否默写？

### 10.6 系列预告

- **下个 P0 系列**：S10-Measure (剩余 S10-03 / S10-04 / S10-05) 或 Industry-Benchmark (IB01-04) → 用户选择
- **可选 P1 系列**：Hardware HAL (剩余 A03-A07)、Native (N01-N05)、CrossPlatform (CP01-CP05)
