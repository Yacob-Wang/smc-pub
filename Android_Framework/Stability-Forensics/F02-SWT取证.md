# F02 · SWT 取证：watchdog traces + SystemServer Perfetto

> **系列**：Android 稳定性取证系列（Stability-Forensics）· 第 2 篇 / 共 8 篇
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.12`（**当前默认基线**）
> **Linux 6.18 LTS（前瞻）**：待 AOSP 17 后续推 6.18 分支后纳入
>
> **目标读者**：Android 稳定性架构师
>
> **完成时间**：2026-07-18（v1.0 首版）

---

# 本篇定位

- **本篇系列角色**：**症状取证 2/7**
- **强依赖**：必先读 [F00-取证体系总览](F00-取证体系总览.md) + [Stability S04-SWT](../Stability/S04-SWT.md)
- **不重复内容**：
  - **不重复** Stability S04 讲的 SWT 触发机制
  - **不重复** [Watchdog 系列](../Watchdog/) 6 篇对 Watchdog 内部状态机深挖
  - 本篇与之关系：**视角互补**

---

# 校准决策日志

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|:-----|:-----|:-----|:-----|:---------|
| 1 | 结构 | 单篇 700 行 | §9 破例：SWT 取证涉及 SystemServer Perfetto（AOSP 17 新增）| 仅本篇 |
| 1 | 结构 | 5 个取证子节（watchdog traces / dropbox / SystemServer Perfetto / 喂狗链路 / 治理）| F02 主题"SWT 取证"决定 | 仅本篇 |
| 2 | 硬伤 | 源码路径 AOSP 17 全量对账 | 附录 B 强制 | 全文 6+ 处源码引用 |
| 2 | 硬伤 | §3.5 SystemServer Perfetto 标注 `// 待 cs.android.com 确认` | AOSP 17 新增机制待验证 | §3.5 |
| 3 | 锐度 | §1.1 强调"SWT 取证 = watchdog traces + SystemServer Perfetto" | 反例 #9 跨篇重复防御 | §1.1 |

---

# 角色设定

我是一名 **Android 稳定性架构师**，正在系统学习 Android 稳定性问题的"症状 × 取证"完整体系。

本篇是 Forensics 系列第 2 篇，主题是 **SWT 取证**——SystemServer 卡死的取证全链路。

# 上下文

- **上一篇**：[F04-NE 取证](F04-NE取证.md) 已深挖 NE 取证
- **本系列 README**：[README-Forensics系列.md](README-Forensics系列.md)

# 写作标准

> 沿用 v4 一站式模板硬性要求

---

# 1. 背景与定义

## 1.1 SWT 取证 = watchdog traces + dropbox(SYSTEM_SERVER_WATCHDOG) + SystemServer Perfetto 3 件套

> **一句话定义**：SWT 触发后 30 秒内拿到 3 件证据——**watchdog traces**（SystemServer 线程栈）+ **dropbox(SYSTEM_SERVER_WATCHDOG)**（事件元数据）+ **SystemServer Perfetto**（SystemServer 全栈时间线，AOSP 17 新增自动 dump）。

**三件套对应**：

| 文件 | 路径 | 内容 | 作用 |
|:-----|:-----|:-----|:-----|
| **watchdog traces** | `/data/anr/watchdog_*` | SystemServer 全部线程栈 | 看哪个 monitor 卡死 |
| **dropbox(SYSTEM_SERVER_WATCHDOG)** | `/data/system/dropbox/` | 事件元数据 + Watchdog 决策 | 确认 SWT 触发 + 杀进程策略 |
| **SystemServer Perfetto** | `/data/local/traces/`（AOSP 17 自动）| SystemServer 全栈时间线 | 看 SystemServer 哪个带卡住 |

> **所以呢**：**SWT 取证比 ANR 取证更复杂**——涉及到**全栈追踪**（SystemServer 4 大 monitor 全部要查）。

## 1.2 SWT 取证 vs Stability S04 视角

| 维度 | Stability S04 | Forensics F02 |
|:-----|:--------------|:--------------|
| **视角** | 机制（Watchdog 状态机 / HandlerChecker / 杀进程判定）| 取证（watchdog traces + SystemServer Perfetto）|
| **关注** | 6 个机制子节 | 3 件套 + 喂狗链路取证 |

## 1.3 SWT 取证的 3 个常见误区

| 误区 | 错在哪 | 正确做法 |
|:-----|:-------|:--------|
| "看 watchdog traces 就够了" | watchdog traces 只看到 SystemServer 栈，**看不到 input / kernel IO** | 补抓 SystemServer Perfetto + 喂狗链路取证 |
| "SWT 是 SystemServer bug" | 也可能是 **App binder call 阻塞 SystemServer** | 看 watchdog traces + 远端 binder 栈 |
| "杀 SystemServer 就好" | 频繁杀 SystemServer = 整机反复重启，**数据可能损坏** | 找根因，避免频繁触发 |

---

# 2. 取证 4 步法

## 2.1 触发 → 抓取 → dump 路径 → 解读

### 第 1 步：触发（logcat 关键字）

```bash
adb logcat | grep -E "Watchdog|Killing system server"
```

```logcat
W Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS: Blocked in handler on ActivityManager
W Watchdog: Input event dispatching timed out sending to com.example.camera
I Watchdog: Killing system server due to blocked handler in ActivityManager
```

**关键读法**：
- `WATCHDOG KILLING SYSTEM PROCESS` = SWT 触发
- `Blocked in handler on XXX` = 哪个 monitor 卡死（AM/PM/WM/PMS）
- `Killing system server` = 杀 SystemServer 决策
- `Rebooting device` = 整机重启决策

### 第 2 步：抓取（3 件套）

**watchdog traces 抓取**：
```bash
# 立即抓（SWT 触发后 1 分钟内）
adb pull /data/anr/ ./anr_traces/

# 找 watchdog_ 开头的文件
adb shell ls -la /data/anr/ | grep watchdog
```

**dropbox 抓取**：
```bash
adb shell dumpsys dropbox --print | grep -A 30 "SYSTEM_SERVER_WATCHDOG"
```

**SystemServer Perfetto 抓取**：
```bash
# AOSP 17 新增：SWT 触发时自动 dump（_待 cs.android.com 确认_）
# 事后手动抓：
adb shell perfetto --background --config system_server_perfetto.cfg \
    --out /data/local/traces/systemserver_trace.pftrace

# 关键：config 必须包含 system_server 进程的所有线程
```

**bugreport 兜底**：
```bash
adb bugreport > bugreport_$(date +%Y%m%d_%H%M%S).zip
# 解压后含：
# - data/anr/ (watchdog traces)
# - data/system/dropbox/ (dropbox 事件)
# - data/local/traces/ (SystemServer Perfetto)
# - logcat 全量
```

### 第 3 步：dump 路径

```bash
$ adb shell ls -la /data/anr/ | grep watchdog
-rw------- 1 system system 250K 2026-07-15 10:24 watchdog_2026-07-15_10-24-15

$ adb shell ls -la /data/system/dropbox/ | grep WATCHDOG
-rw-rw---- 1 system system 12K 2026-07-15 10:24 SYSTEM_SERVER_WATCHDOG@1709123456789.txt
```

### 第 4 步：解读

| 文件 | 关键看 |
|:-----|:------|
| **watchdog traces** | `Blocked in handler on XXX` + 全部线程栈 |
| **dropbox(SYSTEM_SERVER_WATCHDOG)** | `Subject` + `Process` + 杀进程决策 |
| **SystemServer Perfetto** | SystemServer 哪个带卡住 + 远端服务在做什么 |

---

# 3. watchdog traces 详解

## 3.1 完整栈解读

```
Blocked in handler on ActivityManager
"ActivityManager" prio=5 tid=12 Blocked
  | group="main" sCount=1 ucsCount=0 flags=1 obj=0x...
  | sysTid=1234 ...
  | state=S schedstat=(...) utm=... stm=... core=...
  at android.os.BinderProxy.transactNative(Native Method)
  at android.os.BinderProxy.transact(BinderProxy.java:540)
  at com.android.server.am.ActivityManagerService.binder...(Native Method)
  at com.example.app.CameraManager.takePicture(CameraManager.java:42)

"WindowManager" prio=5 tid=13 Blocked
  ...

"PowerManager" prio=5 tid=14 Blocked
  ...
```

**关键读法**：
- `Blocked in handler on XXX` ← 哪个 monitor 卡死
- `state=S` = Sleeping（等锁/IO）
- **多个 monitor 都 Blocked** = 多米诺效应
- 栈顶 `at` 链 = 阻塞点

> **架构师视角**：**watchdog traces 的关键不是单线程栈**——是**多个 monitor 的 Blocked 状态** + **SystemServer 整体状态**。

## 3.2 喂狗链路取证（**关键**）

**喂狗链路 3 大节点**（详细见 [Stability S04 §3.6](../Stability/S04-SWT.md)）：

| 节点 | 频率 | 来源 | 取证 |
|:-----|:-----|:-----|:-----|
| **input 喂狗** | 1-2s | InputDispatcher.cpp | `adb shell getevent -lt` 看 input 是否活跃 |
| **VSYNC 喂狗** | 16.7ms（60Hz）| SurfaceFlinger | `adb shell dumpsys SurfaceFlinger --latency-clear` |
| **binder 喂狗** | 活跃时高频 | IPCThreadState | `/sys/kernel/debug/binder/stats` |

> **所以呢**：**SWT 触发时，喂狗链路一定断了**——watchdog traces 抓不到喂狗断点，必须**主动看 input/VSYNC 状态**。

## 3.3 与 ANR traces 的差异

| 维度 | anr traces（ANR）| watchdog traces（SWT）|
|:-----|:-----------------|:---------------------|
| 触发 | AMS 检测 App 主线程 | Watchdog 检测 SystemServer |
| 抓的线程 | **App 进程**的主线程 + 部分线程 | **SystemServer** 全部 monitor 线程 |
| 路径 | `/data/anr/anr_*` | `/data/anr/watchdog_*` |
| 监控对象 | 单个 App 进程 | 4 大 monitor（AM/PM/WM/PMS）|

> **架构师视角**：**ANR traces 和 watchdog traces 在同一目录（/data/anr/）**——**取证时别拿错**。

---

# 4. dropbox(SYSTEM_SERVER_WATCHDOG) 详解

## 4.1 抓取与解读

```bash
$ adb shell dumpsys dropbox --print | grep -A 30 "SYSTEM_SERVER_WATCHDOG"
```

```
2026-07-15 10:24:15 SYSTEM_SERVER_WATCHDOG (text, 12K bytes)
  Package: system_server
  Process: system_server
  Subject: Watchdog: Blocked in handler on ActivityManager
  Build: Pixel 6
  ...
  Decision: Killing system server due to blocked handler
```

**关键读法**：
- `Process: system_server` ← 杀的是 SystemServer
- `Subject` = 哪个 monitor 卡死
- `Decision` = 杀进程决策（杀 SystemServer / 整机重启）

## 4.2 保留期

| tag | 保留期 | 备注 |
|:----|:-------|:-----|
| SYSTEM_SERVER_WATCHDOG | 30 天 | SWT 触发 |
| SYSTEM_SERVER_CRASH | 30 天 | SystemServer 自身 crash |

> **所以呢**：dropbox 保留 30 天——比 watchdog traces（保留几个）保留更久。

---

# 5. SystemServer Perfetto（AOSP 17 新增）

> `// 待 cs.android.com 确认`：AOSP 17 新增 Watchdog 自动 dump SystemServer Perfetto trace

## 5.1 为什么 SystemServer Perfetto 重要？

```
问题：watchdog traces 只看到 SystemServer 线程栈，**看不到**：
  1. SystemServer 在等哪个远端服务
  2. SystemServer 哪个带卡住
  3. input / VSYNC / binder 喂狗链路状态

SystemServer Perfetto 解决：
  - **全栈追踪**：user + kernel
  - **SystemServer 全部线程**：包括远端服务
  - **喂狗链路可视化**：input / VSYNC / binder 事件
```

> **所以呢**：**SystemServer Perfetto 是 SWT 取证的核武器**——能看全栈时间线。

## 5.2 配置

```protobuf
# system_server_perfetto.cfg (AOSP 17 默认配置，_待确认_)
data_sources {
  config {
    name: "linux.process_stats"
    process_stats_config {
      scan_all_processes_on_start: true
    }
  }
}
data_sources {
  config {
    name: "android.surfaceflinger"
    surfaceflinger_config {
      enable_layers: true
    }
  }
}
duration_ms: 30000  # 30s 抓取
```

## 5.3 解读

**SystemServer Perfetto 关键看**：
- `system_server` 主线程带
- `system_server` 4 大 monitor 线程带
- input 事件带（喂狗）
- VSYNC 事件带（喂狗）
- binder 远端带（如果是 binder call 阻塞）

**典型 SWT 时间线**：
```
T+0ms    input event received
T+10ms   ActivityManager: takePicture  ← App 端 binder call
T+20ms   CameraService: openCamera
T+30ms   Camera HAL: open camera  ← 开始卡
T+2000ms input event: deliver to ActivityManager  ← 喂狗失败
T+10000ms input event: 累积 10s 未 dispatch
T+30000ms Watchdog: HandlerChecker timeout (30s)
T+30001ms Watchdog: evaluateCheckerCompletionLocked
T+30002ms Watchdog: Killing system server
```

**关键读法**：
- **input 喂狗 30s 未成功** ← 触发 SWT
- **Camera HAL 卡住** ← 根因（在远端，不在 SystemServer）

> **架构师视角**：**没有 SystemServer Perfetto，几乎不可能定位 SWT 根因**——这是 AOSP 17 强化的核心。

---

# 6. 治理

## 6.1 SWT 取证自动化

**4 件必做**：
1. **APM 自动采集**：Sentry / 自研（SWT 触发即上报）
2. **watchdog traces 主动采集**：自动 `adb pull /data/anr/`（防覆盖）
3. **dropbox 主动监控**：定时 `adb shell dumpsys dropbox --print`
4. **SystemServer Perfetto 监控启动**：SWT 触发时自动启动 trace（AOSP 17 增强）

## 6.2 喂狗链路监控（**架构师必修**）

**3 件必做**：
1. **input 喂狗监控**：`adb shell getevent -lt` 定期跑
2. **VSYNC 喂狗监控**：`adb shell dumpsys SurfaceFlinger --latency-clear` 持续监控
3. **binder 喂狗监控**：`/sys/kernel/debug/binder/stats` 接入 APM

## 6.3 预防机制

**5 个必做**：
1. **业务加 timeout**（所有跨进程 binder call）—— **必做**
2. **input 喂狗监控**（推荐）
3. **VSYNC 喂狗监控**（推荐）
4. **SystemServer Perfetto 接入**（AOSP 17 增强）—— 推荐
5. **lockdep 开启**（debug build 必做）—— **必做**

---

# 7. 实战案例

## 7.1 案例 A（CASE-FORENSICS-02-01）：AMS binder call 阻塞 60s → 完整取证 4 步法

> **类型**：典型模式
>
> **环境**：AOSP 14.0.0_r1 / Kernel 5.10 / 设备 Pixel 6（**AOSP 17 / K 6.12 验证版准备中**）
>
> **症状**：App 调用系统服务 60s 后整机重启
>
> **根因**：App binder call 阻塞 AMS，喂狗链路断

### 现象

```
用户操作：
  T+0s   App 调用 ICameraService.takePicture()
  T+30s  AMS binder 队列堆积
  T+30s  **Watchdog 30s 触发**
  T+30.1s HandlerChecker 评估：AM 超时
  T+60s  连续 2 次 30s 失败（DEFAULT_FAILURE_DETECTOR = 3）
  T+90s  杀 SystemServer
  T+120s 整机重启
```

### 取证 4 步法

**第 1 步：触发（logcat）**

```logcat
W Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS: Blocked in handler on ActivityManager
W Watchdog: Input event dispatching timed out
I Watchdog: Killing system server due to blocked handler in ActivityManager
```

**第 2 步：抓取**

```bash
# watchdog traces 抓取
$ adb pull /data/anr/watchdog_2026-07-15_10-24-15
./watchdog_2026-07-15_10-24-15

# dropbox 抓取
$ adb shell dumpsys dropbox --print | grep -A 30 "SYSTEM_SERVER_WATCHDOG"
2026-07-15 10:24:15 SYSTEM_SERVER_WATCHDOG (text, 12K bytes)
  Process: system_server
  Subject: Watchdog: Blocked in handler on ActivityManager
  Decision: Killing system server

# SystemServer Perfetto 抓取
$ adb shell perfetto --background --config system_server_perfetto.cfg \
    --out /data/local/traces/swt_trace.pftrace
```

**第 3 步：dump 路径**

```bash
$ adb shell ls -la /data/anr/ | grep watchdog
-rw------- 1 system system 250K 2026-07-15 10:24 watchdog_2026-07-15_10-24-15
```

**第 4 步：解读**

**watchdog traces 关键段**：
```
Blocked in handler on ActivityManager
"ActivityManager" prio=5 tid=12 Blocked
  | state=S schedstat=(...) utm=... stm=... core=...
  at android.os.BinderProxy.transactNative(Native Method)
  at android.os.BinderProxy.transact(BinderProxy.java:540)
  at com.android.server.am.ActivityManagerService.binder...(Native Method)
  at com.example.app.CameraManager.takePicture(CameraManager.java:42)
```

**SystemServer Perfetto 关键**：
```
T+0ms    input event received
T+10ms   ActivityManager: takePicture
T+30s    Watchdog: HandlerChecker timeout
T+30.1s  Watchdog: Killing system server
```

**关键读法**：
- `Blocked in handler on ActivityManager` ← **AM 30s 卡死**
- `state=S` ← 主线程在等 binder 远端
- 栈顶 `BinderProxy.transact` ← **远端服务卡死**

> **关键发现**：**根因在 App 端**（`CameraManager.takePicture`），不在 SystemServer——这就是 cascade 链路（App → SystemServer → REBOOT）。

### 修复

**短期**：
```java
// 业务加 timeout
try {
    Future<?> future = executor.submit(() -> cameraManager.takePicture());
    future.get(5, TimeUnit.SECONDS);  // 5s 超时
} catch (TimeoutException e) {
    // 降级
    showRetryDialog();
}
```

**长期**：
- 全局 binder call timeout（2-3s）
- SystemServer Perfetto 接入（自动 dump）
- 喂狗链路监控

### 验证

1. 复现：CameraService 模拟卡死
2. 应用 hotfix：业务加 5s timeout
3. 验证：binder 超时立即降级，不触发 SWT
4. APM：binder call 失败率 < 0.1%

---

## 7.2 案例 B（CASE-FORENSICS-02-02）：AOSP Issue 公开 bugreport 模式

> **类型**：公开 bugreport
>
> **来源**：[AOSP Issue Tracker](https://issuetracker.google.com/)
>
> **检索关键词**：`"Watchdog" "PMS installPackage timed out"`

> **撰写时验证**：具体 issue 编号将在 F02 校准时通过 [issuetracker.google.com](https://issuetracker.google.com/) 检索确认。

---

# 8. 总结

## 8.1 架构师视角 5 条 Takeaway

1. **SWT 取证 3 件套**：watchdog traces + dropbox(SYSTEM_SERVER_WATCHDOG) + SystemServer Perfetto（AOSP 17 增强）。
2. **watchdog traces 在 `/data/anr/`（与 ANR traces 同目录）**——别拿错。
3. **SystemServer Perfetto 是 SWT 取证的核武器**：能看全栈时间线。
4. **喂狗链路断了必触发 SWT**：必须主动监控 input / VSYNC / binder。
5. **杀 SystemServer 是严重事件**：找根因，避免频繁触发。

## 8.2 排查路径速查

| 看到症状 | 抓什么 | 跳到 |
|:---------|:-------|:-----|
| logcat `Watchdog ... KILLING` | watchdog traces + dropbox + SystemServer Perfetto | §2 / §3 / §5 |
| 整机频繁重启 | `last_kmsg` + pstore + dropbox(SYSTEM_SERVER_WATCHDOG) | [F05](F05-KE取证.md) / S06 |
| App 端 binder 阻塞 SystemServer | 抓 App 端 binder 超时 | §7 案例 A |

---

# 附录 A：核心源码路径索引

> **版本基线**：AOSP `android-17.0.0_r1`（API 37）

| 文件 | 完整路径 | 版本基线 | 说明 |
|:-----|:---------|:---------|:-----|
| Watchdog.java | `frameworks/base/services/core/java/com/android/server/Watchdog.java` | AOSP 17.0.0_r1 | Watchdog 主类（30s 循环）|
| WatchdogMonitor.java | `frameworks/base/services/core/java/com/android/server/WatchdogMonitor.java` | AOSP 17.0.0_r1 | Monitor 接口 |
| ActivityManagerService.java | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | AOSP 17.0.0_r1 | AM 监控对象 |
| InputDispatcher.cpp | `frameworks/native/services/inputflinger/InputDispatcher.cpp` | AOSP 17.0.0_r1 | input 喂狗源 |
| SurfaceFlinger.cpp | `frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp` | AOSP 17.0.0_r1 | VSYNC 喂狗源 |

---

# 附录 B：dump 路径对账表

| 路径 | 抓取命令 | 大小 | 保留 |
|:-----|:---------|:-----|:-----|
| `/data/anr/watchdog_*` | `adb pull /data/anr/` | 100-500KB | 几个 |
| `/data/system/dropbox/SYSTEM_SERVER_WATCHDOG*` | `adb shell dumpsys dropbox --print` | 10-30KB | 30 天 |
| `/data/local/traces/*.pftrace` | `adb pull /data/local/traces/` | 几 MB | 几 MB |

---

# 附录 C：取证 4 步法检查表（SWT 专项）

| 步骤 | 关键 | 工具 | 验证 |
|:-----|:-----|:-----|:-----|
| **第 1 步：触发** | logcat 看到 `WATCHDOG KILLING` | `adb logcat \| grep Watchdog` | 关键字命中 |
| **第 2 步：抓取** | watchdog traces + dropbox + SystemServer Perfetto | `adb pull` + `dumpsys dropbox` + `adb shell perfetto` | 3 个文件都存在 |
| **第 3 步：dump 路径** | 确认 watchdog traces 存在 | `ls -la /data/anr/` | 文件 > 0KB |
| **第 4 步：解读** | watchdog traces 看 monitor 阻塞 + Perfetto 看喂狗链路 | vi + Perfetto UI | 找到根因 |

---

# 附录 D：工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|:-----|:---------|:---------|:---------|
| **watchdog traces 保留** | 几个 | 满后覆盖 | **必须主动采集** |
| **dropbox(SYSTEM_SERVER_WATCHDOG) 保留** | 30 天 | 满后覆盖 | 主动采集 |
| **SystemServer Perfetto** | AOSP 17 新增（_待确认_）| **强烈推荐** | 自动 dump |
| **APM 接入** | Sentry / 自研 | **必做** | 不接 = 排查效率低 |
| **业务 binder call timeout** | 2-3s | 业务调 | 太短→误失败；太长→SWT 风险 |

---

# 篇尾衔接

本篇 F02 深挖了 SWT 取证全链路（watchdog traces + SystemServer Perfetto）。

**剩余 3 篇**：
- [F05-KE 取证](F05-KE取证.md)：Kernel 异常
- [F06-HANG + OOM 取证](F06-HANG与OOM取证.md)：HANG 主动抓 + OOM hprof
- [F07-取证治理](F07-取证治理.md)：APM + bugreport + 商业符号化

**写作顺序**：F00 → F01 → F03 → F04 → F02 → F05 → F06 → F07

---

> **系列导航**：[← F04-NE 取证](F04-NE取证.md) | [本系列 README](README-Forensics系列.md) | [F05-KE 取证 →](F05-KE取证.md)
>
> **最后更新**：2026-07-18（F02 v1.0 首版）
