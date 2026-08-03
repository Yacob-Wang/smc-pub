# D07 · Power 与电量：battery / batterystats / WakeLock

> **系列**：Dumpsys 系列 · 第 7 篇 / 共 12 篇
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）
>
> **目标读者**：Android 性能架构师（耗电 / 后台管控第一线）
>
> **完成时间**：2026-07-18

---

# 本篇定位

- **本篇系列角色**：**症状专题 6/12 · 耗电 / 后台管控 / WakeLock**（Dumpsys 系列第 7 篇）
- **强依赖**：[D02-Activity](02-Activity与AMS视角.md) §3.3 进程调度
- **承接自**：[D01](01-dumpsys总览与架构.md) §3.2.2 C 类（资源类）电量段
- **衔接去**：
  - 下一篇 [D08-Input与IMS视角](08-Input与IMS视角.md)
  - 收口 [D12-实战SOP](12-dumpsys实战SOP.md)
- **本篇贡献**：把 dumpsys battery/batterystats/power 3 大子命令、~20 个关键字段、5 类耗电问题立得住

---

# 校准决策日志

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|:-----|:-----|:-----|:-----|:---------|
| 1 | 结构 | 单篇 500+ 行 | 3 子命令 + 20 字段 + 5 问题 | 仅本篇 |
| 2 | 硬伤 | 关键字段表 | §4 #5 反例 | §4 |
| 3 | 锐度 | 删"建议" | 反例 #5 | 全文 |

---

# 角色设定

我是一名 **Android 性能架构师**，正在用 `dumpsys batterystats` 排查"用户报应用耗电严重"问题。

本篇是 Dumpsys 系列第 7 篇，主题是 **`dumpsys battery` / `batterystats` / `power` 3 件套 + 耗电 / 后台管控的现场取证**。

# 写作标准

- 本规范（[PROMPT-技术系列文章写作指南.md](../../../PROMPT-技术系列文章写作指南.md)）
- 章节编号：# 总章 / # 章 / ## 节 / ### 子节
- 必备：每章配 1 个 ASCII / mermaid 图
- 必备：数据后接"所以呢"段
- 必备：附录 A 源码索引 / B 路径对账【强制】/ C 量化自检 / D 工程基线
- 必备：5 条 Takeaway 收尾（其中 1-2 条指向下一篇）
- 基线：AOSP 17 + 6.18，所有源码路径经 cs.android.com 验证
- 图表：~3-4 张
- 字数：~400-500 行
- 重点：5 类耗电问题模式 + WakeLock 判定 + 阈值表

# 上下文

- **上一篇**：[D06-Package与权限](06-Package与权限.md)
- **下一篇**：[D08-Input与IMS视角](08-Input与IMS视角.md)
- **本系列 README**：[README-Dumpsys系列.md](README-Dumpsys系列.md)

---

# 1. 背景：3 大 power 子命令是什么？

## 1.1 一句话定位

**`dumpsys battery` / `batterystats` / `power` 是 Android 耗电分析的"3 件套"——一个看电池状态、一个看耗电历史、一个看 WakeLock，组合起来能定位 90% 耗电问题**。

## 1.2 3 件套全景

| 工具 | 类型 | 看什么 | 输出 | 典型场景 |
|:-----|:-----|:-------|:-----|:---------|
| **`dumpsys battery`** | 系统服务 | 当前电池状态 + 模拟 | 文本 | 模拟低电 |
| **`dumpsys batterystats`** | 系统服务 | 耗电历史 | 文本/HTML | 找耗电元凶 |
| **`dumpsys batterystats --proto`** | 系统服务 | protobuf 格式 | 二进制 | 程序化分析 |
| **`dumpsys power`** | 系统服务 | PowerManager 状态 + WakeLock | 文本 | WakeLock 诊断 |

## 1.3 与稳定性症状的对应关系

| 症状 | 优先工具 | 关键看哪段 |
|:-----|:---------|:----------|
| **耗电严重** | `dumpsys batterystats` | WakeLock 段 |
| **后台被掐电** | `dumpsys batterystats` | JobScheduler 段 |
| **屏幕不息屏** | `dumpsys power` | WakeLock 数 |
| **充电动画异常** | `dumpsys battery` | level / status |
| **CPU 占用高** | `dumpsys batterystats` | CPU time 段 |

---

# 2. 边界：3 件套 vs Battery Historian

| 工具 | 看什么 | dumpsys 不能给什么 |
|:-----|:-------|:--------------------------|
| **`dumpsys batterystats`** | 文本统计 | 不含可视化 |
| **Battery Historian** | HTML 可视化 | 需上传 bugreport |

---

# 3. 机制：3 大子命令深挖

## 3.1 `dumpsys battery`（当前电池状态）

### 3.1.1 典型输出

```bash
$ adb shell dumpsys battery
```

```
Current Battery Service State (dumpsys battery):
  AC powered: false
  USB powered: true
  Wireless powered: false
  Max charging current: 500000
  Max charging voltage: 5000000
  Charge type: 1
  status: 2  ← ⭐ 充电状态
  health: 2  ← ⭐ 健康度
  present: true
  level: 75  ← ⭐ 电量百分比
  scale: 100
  voltage: 4200  ← ⭐ 电压 mV
  temperature: 280  ← ⭐ 温度 0.1°C
  technology: Li-ion
```

### 3.1.2 关键字段

| 字段 | 含义 | 异常判定 |
|:-----|:-----|:---------|
| **status** | 充电状态 | 1=未知 2=充电 3=放电 4=充满 5=异常 |
| **health** | 健康度 | 2=良好 3=过热 4=死 5=过压 6=未指定 |
| **level** | 电量 | 0-100 |
| **voltage** | 电压 mV | 异常高/低 |
| **temperature** | 温度（0.1°C）| > 500 (50°C) = 过热 |

### 3.1.3 模拟命令（开发用）

```bash
# 模拟低电（开发测试）
adb shell dumpsys battery set level 10

# 模拟 AC
adb shell dumpsys battery set ac 1

# 模拟没电
adb shell dumpsys battery set level 0

# 恢复真实
adb shell dumpsys battery reset
```

## 3.2 `dumpsys batterystats`（耗电历史）

### 3.2.1 典型输出

```bash
$ adb shell dumpsys batterystats
```

```
Battery History (dumpsys batterystats):
  ...
  
  Statistics since last charge (dumpsys batterystats):
    System starts: 1, "Currently running services":
      Wake lock summary:  ← ⭐ WakeLock 段
        wake lock "AudioMix": 5m 12s (5 times) realtime
        wake lock "Dex2oat": 23s (3 times) realtime
        wake lock "NetworkStats": 12s (1 time) realtime
      
      CPU usage:  ← ⭐ CPU 段
        Foreground: 2h 30m 15s realtime
        Background: 5h 12m 30s realtime
      
      Job Statistics:
        com.example.app: 123 jobs, 12m 30s total
        com.android.systemui: 45 jobs, 5m 12s total
      
      Top wake locks (in ms):  ← ⭐ Top WakeLock
        1523000 ms "Dex2oat" (com.android.providers.media)
        890000 ms "AudioMix" (com.android.server.audio)
        ...
    
    Per-app stats:
      App "com.example.app" (uid 10000):
        Wake lock "MyWakeLock": 1m 23s (5 times)  ← ⭐ 应用 WakeLock
        ...
        CPU: 30m 15s (user) + 5m 12s (kernel)
        ...
        Sensor use:
          accelerometer: 1h 23m 45s  ← ⭐ 传感器
        ...
```

### 3.2.2 关键字段

| 段 | 含义 | 异常判定 |
|:---|:-----|:---------|
| **Wake lock summary** | 全部 WakeLock 汇总 | 长时间 WakeLock = 后台活跃 |
| **CPU usage** | CPU 占用 | > 50%/h 异常 |
| **Top wake locks** | 最大的 WakeLock | 应用在前 10 = 需优化 |
| **Per-app stats** | 单应用详情 | 看应用的 WakeLock + CPU + Sensor |

### 3.2.3 关键判定

| 异常 | dumpsys 表现 |
|:-----|:-------------|
| **应用耗电大** | `Per-app stats` 中 CPU / WakeLock / Sensor 时长 > 10%/h |
| **后台活跃** | WakeLock 时长 > 30min/h |
| **频繁唤起** | Job Statistics 中 jobs > 50/h |
| **传感器耗电** | Sensor use 中 accelerometer / GPS 时长 > 10%/h |

## 3.3 `dumpsys power`（PowerManager 状态 + WakeLock）

### 3.3.1 典型输出

```bash
$ adb shell dumpsys power
```

```
Power Manager State (dumpsys power):
  ...
  
  Wake Locks: size=3  ← ⭐ WakeLock 列表
    Wake Lock #0:
      ...
      tag: "AudioMix"
      owner: com.android.server.audio
      ...
      held: true  ← ⭐ 正在持有
    
    Wake Lock #1:
      tag: "NetworkStats"
      owner: com.android.server.NetworkStatsService
      held: false  ← ⭐ 已释放
    
    Wake Lock #2:
      tag: "MyWakeLock"  ← ⭐ 应用 WakeLock
      owner: com.example.app
      held: true
    
  Display Power: ...
  ...
```

### 3.3.2 关键字段

| 字段 | 含义 | 异常判定 |
|:-----|:-----|:---------|
| **size** | WakeLock 总数 | > 10 异常 |
| **tag** | WakeLock 标签 | 应用持有 = 后台活跃 |
| **owner** | WakeLock 持有者 | — |
| **held** | 是否正在持有 | `true` 长时间 = 异常 |

### 3.3.3 实战命令

```bash
# 1. 看全部 WakeLock
adb shell dumpsys power | grep -A 5 "Wake Lock #"

# 2. 看应用 WakeLock
adb shell dumpsys power | grep -B 1 -A 5 "com.example.app"

# 3. 看 WakeLock 总数
adb shell dumpsys power | grep "Wake Locks: size"
```

---

# 4. 风险地图与解读阈值

## 4.1 5 类耗电问题模式

| 模式 | dumpsys 表现 | 根因 | 修复方向 |
|:-----|:-------------|:-----|:---------|
| **1. WakeLock 持有过长** | `Wake lock tag: ...` 时间长 | 应用没 release WakeLock | 改用 WorkManager |
| **2. 后台 CPU 高** | `Per-app CPU user > 30min/h` | 后台线程在跑 | 排查 Service / Worker |
| **3. JobScheduler 频繁** | `jobs > 50/h` | JobScheduler 滥用 | 减少 Job / 用 Doze 兼容 |
| **4. Sensor 长时间** | `accelerometer > 10%/h` | 传感器没释放 | unregisterListener |
| **5. 充电异常** | `status=5` 或 voltage 异常 | 硬件问题 | 提交 OEM |

## 4.2 关键阈值

| 阈值 | 数值 | 含义 |
|:-----|:-----|:-----|
| **应用 CPU 时间** | < 5min/h | 正常 |
| **应用 CPU 异常** | > 30min/h | 耗电 |
| **应用 WakeLock** | < 5min/h | 正常 |
| **应用 WakeLock 异常** | > 30min/h | 耗电 |
| **Job 数** | < 20/h | 正常 |
| **Job 异常** | > 50/h | 频繁唤起 |
| **Sensor 时间** | < 5%/h | 正常 |
| **电池温度** | < 50°C | 正常 |
| **电池温度异常** | > 60°C | 过热 |

---

# 5. 治理：耗电取证 SOP

## 5.1 通用耗电取证步骤

```bash
# Step 1: 重置电池统计（可选）
adb shell dumpsys batterystats reset

# Step 2: 用户复现耗电场景
# 等待 1 小时正常使用

# Step 3: 抓取耗电历史
adb shell dumpsys batterystats > /tmp/batterystats.txt

# Step 4: 看 Top wake locks
grep "Top wake locks" -A 30 /tmp/batterystats.txt

# Step 5: 看某包详情
grep -A 50 'App "com.example.app"' /tmp/batterystats.txt
```

## 5.2 后台活跃诊断

```bash
# Step 1: 看 WakeLock
adb shell dumpsys power | grep -A 5 "Wake Lock #"

# Step 2: 看 PowerManager Service
adb shell dumpsys power | grep "mWakefulness"

# Step 3: 看 JobScheduler
adb shell dumpsys jobscheduler | grep "com.example.app"
```

## 5.3 dumpsys batterystats 接入 APM

```python
def on_user_report_battery(package_name):
    result = run_adb(f"dumpsys batterystats --proto {package_name}")
    # 解析 protobuf
    cpu_time = parse_cpu_time(result)
    wakelock_time = parse_wakelock(result)
    if cpu_time > THRESHOLD or wakelock_time > THRESHOLD:
        upload_to_server({...})
```

---

# 6. 实战案例

## 6.1 CASE-DUMPSYS-07-01 应用耗电严重

**场景**：用户报"应用后台跑 1 小时耗电 30%"。

**操作时序**：

```bash
# T+0s: 重置
$ adb shell dumpsys batterystats reset

# T+1h: 抓取
$ adb shell dumpsys batterystats | grep -A 30 "com.example.app"
  App "com.example.app" (uid 10000):
    Wake lock "MyWakeLock": 45m 12s (5 times)  ← ⭐ 异常：45 分钟
    CPU: 30m 15s (user) + 5m 12s (kernel)  ← ⭐ 异常
    Sensor use:
      accelerometer: 50m 12s  ← ⭐ 异常：50 分钟
    ...
```

**根因定位**：
- WakeLock "MyWakeLock" 持有 45 分钟
- accelerometer 传感器注册了但没释放
- 配合 ProGuard / 代码扫描找到：
  ```java
  // 问题代码
  public class MyService extends Service {
      PowerManager.WakeLock wakeLock;
      
      @Override
      public void onCreate() {
          // 申请 WakeLock 但从不释放
          wakeLock = powerManager.newWakeLock(PARTIAL_WAKE_LOCK, "MyWakeLock");
          wakeLock.acquire();
      }
  }
  ```

**修复方案**：
```java
// 修复：用 WorkManager
public class MyWorker extends Worker {
    public Result doWork() {
        // 短任务，< 10min
        return Result.success();
    }
}
```

## 6.2 CASE-DUMPSYS-07-02 充电状态异常

**场景**：OEM 设备 status 一直是 "Unknown"。

**操作时序**：

```bash
# T+0s: 看电池状态
$ adb shell dumpsys battery
  status: 1  ← ⭐ 异常：Unknown
  level: 50
  ...

# T+10s: 看 logcat
$ adb logcat -d BatteryService:E *:S
  # 有 BatteryService 报错
```

**根因定位**：
- 硬件报告问题
- OEM 驱动没正确响应充电状态

**修复方案**：
- 提交 bugreport 给 OEM

---

# 7. 总结

## 7.1 核心要诀（背下来）

1. **耗电 80% 走 `dumpsys batterystats`**——WakeLock / CPU / Sensor 是关键
2. **3 件套**：`battery`（状态）/ `batterystats`（历史）/ `power`（WakeLock）
3. **WakeLock 持有 > 30min/h = 耗电元凶**
4. **Sensor use 时间长 = 传感器没释放**
5. **Job 频繁 = 频繁唤起**

## 7.2 5 条 Takeaway

1. **`dumpsys batterystats` 是耗电分析的入口**
2. **WakeLock 长时间 = 耗电元凶**
3. **Sensor 长时间 = 传感器泄漏**
4. **Job 数 > 50/h = 频繁唤起**
5. **`dumpsys battery set level X` 可模拟低电**

---

# 附录 A · 源码索引

| 章节 | 源码路径 |
|:-----|:---------|
| §3.1 | `frameworks/base/services/core/java/com/android/server/BatteryService.java` |
| §3.2 | `frameworks/base/services/core/java/com/android/server/am/BatteryStatsService.java` |
| §3.3 | `frameworks/base/services/core/java/com/android/server/power/PowerManagerService.java` |

---

# 附录 B · 路径对账表

| 引用源 | 路径 | 验证 URL |
|:-------|:-----|:---------|
| BatteryService.java | `frameworks/base/services/core/java/com/android/server/BatteryService.java` | `https://cs.android.com/android-17.0.0_r1/platform/frameworks/base/+/refs/heads/android17-release:services/core/java/com/android/server/BatteryService.java` |
| BatteryStatsService.java | `frameworks/base/services/core/java/com/android/server/am/BatteryStatsService.java` | `https://cs.android.com/android-17.0.0_r1/platform/frameworks/base/+/refs/heads/android17-release:services/core/java/com/android/server/am/BatteryStatsService.java` |
| PowerManagerService.java | `frameworks/base/services/core/java/com/android/server/power/PowerManagerService.java` | `https://cs.android.com/android-17.0.0_r1/platform/frameworks/base/+/refs/heads/android17-release:services/core/java/com/android/server/power/PowerManagerService.java` |

---

# 附录 C · 量化自检表

| 维度 | 数据 |
|:-----|:-----|
| 3 大子命令 | battery/batterystats/power |
| 关键字段数 | ~20 |
| 5 类耗电模式 | 见 §4.1 |

---

# 附录 D · 工程基线表

| 参数 | 典型默认 | 踩坑提醒 |
|:-----|:--------|:---------|
| **应用 CPU 时间** | < 5min/h | > 30min/h 异常 |
| **应用 WakeLock** | < 5min/h | > 30min/h 异常 |
| **Job 数** | < 20/h | > 50/h 异常 |
| **Sensor 时间** | < 5%/h | > 10%/h 异常 |
| **电池温度** | < 50°C | > 60°C 异常 |
| **充电状态** | 2/3/4 | 1 (Unknown) = 异常 |

---

> **系列导航**：
> - **上一篇**：[D06-Package与权限](06-Package与权限.md)
> - **下一篇**：[D08-Input与IMS视角](08-Input与IMS视角.md)
> - **本系列 README**：[README-Dumpsys系列.md](README-Dumpsys系列.md)

---

**最后更新**：2026-07-18（D07 v1.0）  
**基线**：AOSP 17 + android17-6.18  
**作者**：Mavis · Stability Matrix Course Dumpsys 系列
