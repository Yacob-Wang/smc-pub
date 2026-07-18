# 05-诊断与监控 - hang / monitor

> **本篇定位**:系列第 5 篇(诊断触发核心)。读完能主动触发一次 ANR(用 `am hang`),实时监控进程的 GC / Crash / LMK 事件(用 `am monitor`),并和 `dumpsys` 工具链配合做完整诊断。
>
> **强依赖**:
> - [01-am 命令全景](01-am命令全景与Activity触发.md)(理解 am 本质)
> - [02 进程管理三件套](02-进程管理三件套-kill-crash-restart.md)(进程死亡现场保留)
>
> **承接自**:[04 dumpheap 详解](04-堆内存转储-dumpheap详解.md)
> **衔接去**:
> - [Hprof 系列 04-内存泄漏典型案例与排查 SOP](../Hprof/04-内存泄漏典型案例与排查SOP.md)(ANR 现场的内存分析)
> - [ANR_Detection 系列](../ANR_Detection/)(ANR 检测原理深入)
> - [06 自动化实战-脚本与 CI 集成](06-自动化实战-脚本与CI集成.md)
>
> **不重复内容**:本篇只讲"主动触发 ANR + 实时监控",**不讲**:
> - ANR 检测原理(见 ANR_Detection 系列)
> - dumpsys 工具链细节(见 Dumpsys 系列)
> - 自动化集成(见 06)
>
> **基线**:AOSP `android-14.0.0_r1` + adb `platform-tools 34.0.0+`
> **风格**:源码密度 ~10%,重点放在"触发链路图 + 监控输出解读 + dumpsys 协同"
>
> **目录位置**:`Android_Framework/AmCommand/`
> **上一篇**:[04-堆内存转储-dumpheap 详解](04-堆内存转储-dumpheap详解.md)
> **下一篇**:[06-自动化实战-脚本与 CI 集成](06-自动化实战-脚本与CI集成.md)

---

## 目录

- [1. 一句话定位:稳定性的"主动制造 ANR + 实时观测"双引擎](#1-一句话定位稳定性的主动制造-anr--实时观测双引擎)
  - [1.1 为什么需要 am hang 和 am monitor](#11-为什么需要-am-hang-和-am-monitor)
  - [1.2 两个命令的能力边界](#12-两个命令的能力边界)
- [2. am hang:主动触发 ANR](#2-am-hang主动触发-anr)
  - [2.1 命令语法](#21-命令语法)
  - [2.2 完整调用栈](#22-完整调用栈)
  - [2.3 ANR 的三种类型:Input / Broadcast / Service](#23-anr-的三种类型input--broadcast--service)
  - [2.4 am hang 触发的是哪种 ANR](#24-am-hang-触发的是哪种-anr)
  - [2.5 --allow-restart 的作用](#25---allow-restart-的作用)
  - [2.6 ANR 现场保留:traces 文件 + dropbox](#26-anr-现场保留traces-文件--dropbox)
  - [2.7 实战场景](#27-实战场景)
- [3. am monitor:实时监控进程事件](#3-am-monitor实时监控进程事件)
  - [3.1 命令语法](#31-命令语法)
  - [3.2 监控事件类型](#32-监控事件类型)
  - [3.3 典型输出解读](#33-典型输出解读)
  - [3.4 --gdb 进入 native 调试](#34---gdb-进入-native-调试)
  - [3.5 实战场景](#35-实战场景)
- [4. 联动 dumpsys:am 触发 + dumpsys 诊断](#4-联动-dumpsysam-触发--dumpsys-诊断)
  - [4.1 dumpsys 工具链速查](#41-dumpsys-工具链速查)
  - [4.2 典型组合用法](#42-典型组合用法)
  - [4.3 ANR 现场分析模板](#43-anr-现场分析模板)
- [5. 关键坑位图](#5-关键坑位图)
  - [5.1 am hang 后主线程死锁,需要手动恢复](#51-am-hang-后主线程死锁需要手动恢复)
  - [5.2 am monitor 输出被 logcat 噪声淹没](#52-am-monitor-输出被-logcat-噪声淹没)
  - [5.3 ANR 现场文件被自动清理](#53-anr-现场文件被自动清理)
  - [5.4 dumpsys 输出太长,grep 关键词不完整](#54-dumpsys-输出太长grep-关键词不完整)
- [6. 案例库:3 个真实场景](#6-案例库3-个真实场景)
  - [6.1 案例 1:触发 ANR 验证 App ANR 防护](#61-案例-1触发-anr-验证-app-anr-防护)
  - [6.2 案例 2:压测期间实时监控 GC + LMK](#62-案例-2压测期间实时监控-gc--lmk)
  - [6.3 案例 3:结合 ANR + dumpheap 定位真因](#63-案例-3结合-anr--dumpheap-定位真因)
- [7. 总结:架构师视角的 5 条 Takeaway](#7-总结架构师视角的-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:ANR 类型矩阵](#附录-banr-类型矩阵)
- [附录 C:am monitor 输出字段表](#附录-cam-monitor-输出字段表)
- [附录 D:工程资产清单](#附录-d工程资产清单)
- [附录 E:工程基线表](#附录-e工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. 一句话定位:稳定性的"主动制造 ANR + 实时观测"双引擎

### 1.1 为什么需要 am hang 和 am monitor

| 痛点 | 主动制造 + 实时观测的价值 |
|------|-------------------------|
| "线上 ANR 偶发,QA 复现不出来" | `am hang` 主动触发 ANR,采集 traces 文件 |
| "压测期间看不到 GC / LMK 趋势" | `am monitor` 后台实时观察事件流 |
| "想看进程被 kill 前的状态" | `am monitor` 看到 `Process died` + 立即 `dumpsys meminfo` |
| "主线程被卡死,想 attach gdb 调试" | `am monitor --gdb` |
| "想看 system_server 内部的 ANR 检测" | `am hang` 触发,看 `dumpsys activity processes` |

> **am hang 是"制造问题",am monitor 是"观察问题"——两者合起来才是完整的"主动诊断"工具链。**

### 1.2 两个命令的能力边界

| 维度 | `am hang` | `am monitor` |
|------|----------|--------------|
| **作用** | 主动触发 ANR | 实时监控进程事件 |
| **触发/被动** | **触发** | **被动** |
| **输出** | traces 文件 + dropbox | 实时事件流 |
| **影响** | 让 app 主线程 sleep 6s | 无 |
| **典型场景** | ANR 现场测试 | 压测期间后台观察 |
| **运行模式** | 一次性,触发即结束 | 长驻,持续输出 |

---

## 2. am hang:主动触发 ANR

### 2.1 命令语法

```bash
# 触发 ANR
adb shell am hang com.example.app

# 触发 ANR + 允许重启
adb shell am hang --allow-restart com.example.app

# 指定 user
adb shell am hang --user 0 com.example.app
```

### 2.2 完整调用栈

```
adb shell am hang com.example.app
        │ 跳 1
        ▼
[am.jar 进程]  ActivityManagerShellCommand.runHang()
   └─ IActivityManager.hang()
        │ 跳 2:Binder IPC
        ▼
[system_server 进程]  AMS.hang()
   └─ 找到目标进程的 IApplicationThread
   └─ IApplicationThread.scheduleApplicationInfoChanged()
        │ 跳 3
        ▼
[目标 app 进程]  ApplicationThread.scheduleHang()
   └─ sendMessage(H.HANG, ...)
        │ 跳 4:主线程
        ▼
[app 主线程]  ActivityThread.handleHang()
   └─ 主动让主线程 sleep 6s
        │
        ▼
[6 秒后]
   │
   ├─ AMS 监测到主线程 5s+ 无响应 → 触发 ANR
   ├─ 收集 traces
   ├─ 写 /data/anr/anr_*
   └─ dropbox 记录 system_server_anr
```

**关键源码(精简版)**:

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java
public boolean hang(IBinder who, int allowRestart) {
    if (checkCallingPermission(android.Manifest.permission.DUMP) != PERMISSION_GRANTED) {
        throw new SecurityException("Permission Denial: ...");
    }
    final int uid = Binder.getCallingUid();
    // 找到 caller 进程并 hang
    synchronized (this) {
        final ProcessRecord proc = mProcessNames.get(...);
        if (proc != null && proc.thread != null) {
            proc.thread.scheduleHang(allowRestart != 0);  // ★ 跨进程
        }
    }
    return true;
}
```

```java
// frameworks/base/core/java/android/app/ActivityThread.java
private class ApplicationThread extends IApplicationThread.Stub {
    public void scheduleHang(boolean allowRestart) {
        sendMessage(H.HANG, allowRestart ? 1 : 0);
    }
}

// H handler 处理 HANG 消息
case H.HANG:
    if (msg.arg1 != 0) {
        // allow-restart 模式
        SystemClock.sleep(6 * 1000);  // 6s
        Process.killProcess(Process.myPid());
    } else {
        // 默认模式
        SystemClock.sleep(6 * 1000);  // 6s,会触发 ANR
    }
    break;
```

### 2.3 ANR 的三种类型:Input / Broadcast / Service

Android 框架会检测 3 种 ANR:

| 类型 | 触发条件 | 默认超时 | am hang 触发? |
|------|---------|---------|--------------|
| **Input ANR**(输入事件) | 主线程 5s 内未处理完输入事件 | 5s | ✅ **触发** |
| **Broadcast ANR**(广播) | onReceive 运行 10s+ | 10s | ❌ |
| **Service ANR** | Service 生命周期 20s+ | 20s | ❌ |
| **Provider ANR** | ContentProvider 10s+ | 10s | ❌ |

> **am hang 触发的是 Input ANR**——主线程 sleep 6s,系统判定主线程卡死。

### 2.4 am hang 触发的是哪种 ANR

am hang 让主线程 sleep 6s,期间:

```
主线程正在 sleep
   │
   ├─ InputManager 投递触摸事件
   │   └─ InputDispatcher 等主线程读取
   │   └─ 5s 超时 → Input ANR
   │
   ├─ WindowManager 投递动画事件
   │   └─ 同样等待
   │
   ▼
[6s 后 sleep 结束]
   │
   ▼
ANR 弹框 / 写入 traces
```

**典型 logcat**:

```
W/InputDispatcher: Window ... is not responding. Waited 5000ms
I/ActivityManager: ANR in com.example.app
I/ActivityManager: Reason: Input dispatching timed out
E/ActivityManager: 100% CPU usage:
E/ActivityManager:    0% user + 100% kernel
```

### 2.5 --allow-restart 的作用

```bash
# 不带 --allow-restart(默认)
adb shell am hang com.example.app
# 行为:主线程 sleep 6s → ANR → ANR 弹框 → 用户选择"等待"或"关闭"
# 后果:app 死锁,需要手动 kill

# 带 --allow-restart
adb shell am hang --allow-restart com.example.app
# 行为:主线程 sleep 6s → Process.killProcess(自己) → 进程自杀
# 后果:app 干净退出,方便自动化
```

**实战选型**:
- 手动测试、用户场景模拟 → 不带 `--allow-restart`
- 自动化脚本、压测 → 带 `--allow-restart`(避免死锁卡住后续步骤)

### 2.6 ANR 现场保留:traces 文件 + dropbox

**位置**:

```
/data/anr/anr_*  (traces.txt 文件)
```

**traces.txt 结构**:

```
----- pid 12345 at 2024-06-22 14:32:15 -----
Cmd line: com.example.app

DALVIK THREADS (38):
"main" prio=5 tid=11 Sleeping
  | group="main" sCount=1 ucsCount=0 flags=1 obj=0x71d7c000 self=0x...
  | sysTid=12345 nice=0 cgrp=default sched=0/0 handle=0x...
  | state=S schedstat=( 0 0 0 ) utm=0 stm=0 core=0 HZ=100
  | stack=0x7fdc4b4000-0x7fdc4b6000 stackSize=8MB
  | held mutexes=
  at java.lang.Thread.sleep!(Native method)
  - sleeping on <0x...> 
  at java.lang.Thread.sleep(Thread.java:1234)
  - locked <0x...> 
  at android.os.SystemClock.sleep(SystemClock.java:131)
  at android.app.ActivityThread.handleHang(ActivityThread.java:3456)  ← ★ 关键
  at android.app.ActivityThread$H.handleMessage(ActivityThread.java:2083)
  at android.os.Looper.loopOnce(Looper.java:161)
  at android.os.Looper.loop(Looper.java:288)
  at android.app.ActivityThread.main(ActivityThread.java:7891)
  at com.android.internal.os.ZygoteInit.main(ZygoteInit.java:987)

...
```

**拉取 traces**:

```bash
# Android 14
adb pull /data/anr/ ./anr/

# 通用(需要 root 或 debug 包)
adb shell su -c "cat /data/anr/anr_*" > anr.txt
```

**dropbox 记录**:

```bash
adb shell dumpsys dropbox --print | grep "anr"
# 2024-06-22 14:32:15 system_server_anr (text, 12345 bytes)
#   Process: com.example.app
#   Reason: Input dispatching timed out
#   ...
```

### 2.7 实战场景

**场景 1:验证 App 是否有 ANR 防护**

```bash
# 1. 启动 app
adb shell am start-activity -n com.example.app/.ui.MainActivity

# 2. 触发 ANR
adb shell am hang com.example.app
# 等待 6 秒,主线程 sleep

# 3. 检查:
#    - ANR 弹框是否出现
#    - 用户的 ANR 防护 Watchdog 是否触发
#    - 是否能在 ANR 后自动恢复
```

**场景 2:自动化压测(避免死锁)**

```bash
#!/bin/bash
# ANR 压测(用 --allow-restart,避免卡死)
for i in {1..50}; do
  adb shell am start-activity -n com.example.app/.ui.MainActivity
  sleep 2
  adb shell am hang --allow-restart com.example.app
  sleep 3
done
```

**场景 3:采集 traces 文件做线下分析**

```bash
#!/bin/bash
# ANR 现场采集
adb shell am hang com.example.app
sleep 7  # 等 ANR 处理完

# 拉 traces
mkdir -p anr_capture
adb pull /data/anr/ anr_capture/

# 拉 dropbox
adb shell dumpsys dropbox --print > anr_capture/dropbox.log 2>/dev/null

# 拉 logcat
adb logcat -d -b all > anr_capture/logcat.log
```

---

## 3. am monitor:实时监控进程事件

### 3.1 命令语法

```bash
# 实时监控(长驻)
adb shell am monitor

# 监控 + gdb 调试入口
adb shell am monitor --gdb <pid>
```

### 3.2 监控事件类型

am monitor 监听 5 类事件,全部从 logcat 的 `ActivityManager` tag 解析:

| 事件 | logcat 来源 | 用途 |
|------|-----------|------|
| **GC** | `ActivityManager: Process ... (pid) has died` + GC 信息 | 看 GC 频率 |
| **Crash** | `FATAL EXCEPTION` / `signal 11` 等 | 实时发现 crash |
| **ANR** | `ANR in ...` | 实时发现 ANR |
| **LowMemory** | `Low on memory:` | 看内存压力 |
| **Process died** | `Process ... has died` | 看进程死亡 |

### 3.3 典型输出解读

```bash
$ adb shell am monitor
** Activity Manager: Monitoring activity manager...  available commands:
  (q)uit: finish monitoring
  (h)elp: show this help text

# 输入 h 看更多命令
h
** Activity Manager: Available commands:
  q: quit
  h: help
  d: dump current state
  ...
```

**实际触发事件时的输出**:

```
# 场景:某 app 触发 GC
** Activity Manager: GC: Concurrent mark-sweep GC ...
   freed 12345 (456MB) / 98765 (890MB), 23% free
   paused 1.5ms total 234ms

# 场景:进程死亡
** Activity Manager: Process com.example.app (pid 12345) has died

# 场景:ANR
** Activity Manager: ANR in com.example.app
   Reason: Input dispatching timed out

# 场景:LowMemory
** Activity Manager: Low on memory:
   System has 234MB available memory
   ...
```

### 3.4 --gdb 进入 native 调试

```bash
# 1. 启动 monitor
adb shell am monitor --gdb 12345
# 输出:Waiting for debugger... pid: 12345
# gdbserver 启动,gdb 可连接

# 2. 在另一终端连接
adb forward tcp:5039 tcp:5039
$ANDROID_HOME/ndk/.../gdb client
```

> 实战较少用——更多用 Android Studio 的 debugger。

### 3.5 实战场景

**场景 1:压测期间后台观察**

```bash
# 终端 1:启动 monitor
adb shell am monitor
# 持续输出事件流

# 终端 2:跑压测
for i in {1..100}; do
  adb shell am start-activity -n com.example.app/.ui.MainActivity
  sleep 2
  adb shell input keyevent KEYCODE_BACK
  sleep 1
done

# 终端 1 看到实时事件:
# - GC 频率
# - 是否 ANR
# - 进程是否死亡
# - LMK 是否触发
```

**场景 2:压测完成后,统计 GC 频率**

```bash
# 把 monitor 输出重定向到文件
adb shell am monitor > monitor.log 2>&1 &
MONITOR_PID=$!
sleep 60  # 跑 1 分钟压测
kill $MONITOR_PID 2>/dev/null

# 统计 GC 次数
grep -c "GC:" monitor.log
# 38  (1 分钟 38 次 GC,频率 0.63/s,正常)
```

**场景 3:看 LMKD 触发频率**

```bash
# 跑压测,后台 monitor
adb shell am monitor | tee monitor.log &
for i in {1..50}; do
  adb shell am start-activity -n com.example.app/.ui.MainActivity
  sleep 5
  adb shell input keyevent KEYCODE_HOME
  sleep 3
done

# 统计 LMK
grep -c "Low on memory" monitor.log
# 5  (50 轮触发 5 次 LMK,约 10% 频率)
```

---

## 4. 联动 dumpsys:am 触发 + dumpsys 诊断

### 4.1 dumpsys 工具链速查

| 命令 | 看的维度 | ANR 排查 |
|------|---------|---------|
| `dumpsys activity processes` | 进程状态 | ★ |
| `dumpsys activity activities` | Activity 栈 | ★ |
| `dumpsys meminfo <pkg>` | 内存 | ★ |
| `dumpsys gfxinfo <pkg>` | 渲染 | - |
| `dumpsys cpuinfo` | CPU | ★ |
| `dumpsys batterystats` | 电池 | - |
| `dumpsys window` | 窗口 | ★ |
| `dumpsys input` | 输入 | - |

### 4.2 典型组合用法

**组合 1:ANR 触发 → traces + meminfo**

```bash
# 1. 触发 ANR
adb shell am hang --allow-restart com.example.app
sleep 8

# 2. 拉 traces
adb pull /data/anr/ ./anr_capture/

# 3. 拉 meminfo
adb shell dumpsys meminfo com.example.app > ./anr_capture/meminfo.log

# 4. 拉 activity 状态
adb shell dumpsys activity activities > ./anr_capture/activities.log
```

**组合 2:进程死亡 → 死亡前状态**

```bash
# 1. 触发死亡
adb shell am kill com.example.app
sleep 2

# 2. 看 dropbox
adb shell dumpsys dropbox --print 2>/dev/null > dropbox.log

# 3. 看最近进程历史
adb shell dumpsys activity processes | grep "ProcessRecord" | head -20
```

**组合 3:压测 → monitor + dumpsys 双轨**

```bash
#!/bin/bash
# 双轨压测
PKG=com.example.app

# 后台:实时 monitor
(adb shell am monitor | tee monitor.log) &
MONITOR_PID=$!

# 前台:跑压测
for i in {1..50}; do
  adb shell am start-activity -n $PKG/.ui.MainActivity
  sleep 2
  adb shell input keyevent KEYCODE_BACK
  sleep 1
done

# 停 monitor
kill $MONITOR_PID 2>/dev/null

# 收尾:dumpsys
adb shell dumpsys meminfo $PKG > meminfo_final.log
adb shell dumpsys activity processes > processes_final.log
```

### 4.3 ANR 现场分析模板

**Step 1:看 traces.txt 主线程**

```bash
# 关键:主线程停在哪个函数
grep -A 5 '"main"' anr_capture/anr_*.txt | head -30
```

**Step 2:看 CPU 占用**

```bash
# 看哪个线程占 CPU 最高
grep "CPU usage" -A 30 anr_capture/anr_*.txt
# 典型输出:
# 99% 12345/com.example.app: 99% user + 0% kernel
# 0% 12346/GC: 0% user + 0% kernel
# 0% 12347/HeapTaskDaemon: 0% user + 0% kernel
```

**Step 3:看锁情况**

```bash
# 看哪个锁被持有
grep "held mutexes" -A 2 anr_capture/anr_*.txt
```

**Step 4:结合 dumpsys meminfo**

```bash
# 看 OOM 是否在临界
cat anr_capture/meminfo.log | grep -E "TOTAL PSS|Java Heap|Native Heap"
# 输出:
#   TOTAL PSS:   823456 kB
#   Java Heap:   234567 kB
#   Native Heap: 456789 kB
```

---

## 5. 关键坑位图

### 5.1 am hang 后主线程死锁,需要手动恢复

**坑**:

```bash
adb shell am hang com.example.app
# 弹 ANR 弹框,用户必须点"关闭"或"等待"
# 自动化脚本卡住
```

**修**:

```bash
# 用 --allow-restart
adb shell am hang --allow-restart com.example.app
# 6s 后进程自杀,无死锁
```

### 5.2 am monitor 输出被 logcat 噪声淹没

**坑**:

```bash
adb shell am monitor
# 输出和 logcat 混在一起,看不清
```

**修**:

```bash
# 用 logcat tag 过滤
adb logcat -s ActivityManager:I "*:S" | tee monitor.log
# 只看 ActivityManager 的输出
```

### 5.3 ANR 现场文件被自动清理

**坑**:

```bash
# ANR 触发 30 分钟后,发现 traces 文件没了
adb pull /data/anr/
# (空)
```

**根因**:Android 框架会自动清理旧的 traces 文件。

**修**:

```bash
# 1. ANR 触发后立即拉
adb shell am hang --allow-restart com.example.app
sleep 8
adb pull /data/anr/ ./  # 立即拉

# 2. 或在 settings 关闭清理
adb shell settings put global anr_show_background 0
```

### 5.4 dumpsys 输出太长,grep 关键词不完整

**坑**:

```bash
adb shell dumpsys meminfo com.example.app | head -50
# 输出截断,看不到关键数据
```

**修**:

```bash
# 用 grep 精准定位
adb shell dumpsys meminfo com.example.app | grep -A 1 "Java Heap"
# 完整输出
adb shell dumpsys meminfo com.example.app > meminfo.log
grep -A 50 "App Summary" meminfo.log
```

---

## 6. 案例库:3 个真实场景

### 6.1 案例 1:触发 ANR 验证 App ANR 防护

**现象**:用户反馈"app 偶发卡住 5 秒后闪退",想看是 ANR 防护生效还是真的崩了。

**用 am hang 验证**:

```bash
# 1. 启动 app
adb shell am start-activity -n com.example.app/.ui.MainActivity

# 2. 触发 ANR(不带 --allow-restart,模拟用户场景)
adb shell am hang com.example.app

# 3. 看弹框 + 等待用户选择
# 选项 1:用户点"等待" → app 恢复
# 选项 2:用户点"关闭" → app 被系统 kill
# 选项 3:app 有 ANR Watchdog → 自动上报 + 退出

# 4. 看 dropbox
adb shell dumpsys dropbox --print | grep "anr"
```

**判断**:
- app 有 ANR Watchdog 且能自动恢复 → 防护有效
- app 被系统 kill → 无防护,需要加 Watchdog

### 6.2 案例 2:压测期间实时监控 GC + LMK

**场景**:跑冷启动压测,想知道 GC 频率和 LMK 触发情况。

```bash
#!/bin/bash
PKG=com.example.app

# 后台 monitor
(adb logcat -c; adb logcat -s ActivityManager:I "*:S" | tee monitor.log) &
MONITOR_PID=$!
sleep 2  # 等 monitor 启动

# 压测:50 轮冷启动
for i in {1..50}; do
  adb shell am start-activity -n $PKG/.ui.MainActivity
  sleep 3
  adb shell input keyevent KEYCODE_BACK
  sleep 1
  adb shell am force-stop $PKG
  sleep 2
done

# 停 monitor
kill $MONITOR_PID 2>/dev/null

# 统计
echo "========================================"
echo "GC 次数: $(grep -c "GC:" monitor.log)"
echo "LMK 次数: $(grep -c "Low on memory" monitor.log)"
echo "ANR 次数: $(grep -c "ANR" monitor.log)"
echo "进程死亡: $(grep -c "has died" monitor.log)"
echo "========================================"
```

**输出示例**:

```
========================================
GC 次数: 187
LMK 次数: 3
ANR 次数: 0
进程死亡: 0
========================================
```

**判断标准**:
- GC < 5/s:健康
- GC 5-10/s:偏高
- GC > 10/s:异常,可能内存泄漏
- LMK > 5%:内存压力过大

### 6.3 案例 3:结合 ANR + dumpheap 定位真因

**现象**:app 在某个页面停留 5 秒必崩,logcat 只看到 "Input dispatching timed out"。

**联合排查**:

```bash
# 1. 复现 ANR
adb shell am start-activity -n com.example.app/.TargetActivity
sleep 2
adb shell am hang com.example.app
sleep 8

# 2. 拉 traces
adb pull /data/anr/ ./

# 3. 看主线程栈
head -100 anr/anr_*.txt
# 输出:
#   at android.app.ActivityThread.handleHang(ActivityThread.java:3456)  ← am hang 触发
#   at android.os.Looper.loop(Looper.java:288)

# 4. 退出 ANR(选"等待")后,立刻 dump heap
adb shell am dumpheap <pid> /data/local/tmp/heap.hprof
adb pull /data/local/tmp/heap.hprof ./

# 5. MAT 看是否有大对象
# (用 hprof-conv 转换后看 Dominator Tree)
```

**根因**:发现内存里有个 200MB 的 Bitmap 对象,触发了 GC 暂停,导致主线程卡 6s。

**修复**:Bitmap 压缩后使用 + 缓存复用。

---

## 7. 总结:架构师视角的 5 条 Takeaway

1. **am hang 是 ANR 测试的"最简触发器"**——6 秒 sleep 模拟 5s+ 主线程卡死,直接生成 traces 文件。
2. **am hang 默认不死进程,--allow-restart 主动自杀**——自动化场景必须带 `--allow-restart`,否则会卡死后续脚本。
3. **am monitor 是压测期间的最佳观测工具**——比 logcat 单独看更聚焦,事件流更干净。
4. **ANR 现场保留靠 3 个位置**:`/data/anr/`(traces.txt)、dropbox、logcat——触发后**立即**拉,Android 框架会自动清理。
5. **am 触发 + dumpsys 诊断是"双轨"**——am hang 触发 ANR,dumpsys 查状态;am monitor 看事件流,dumpsys 拉快照。组合使用才是完整的诊断链路。

---

## 附录 A:核心源码路径索引

| 模块 | 路径 |
|------|------|
| am.jar hang 入口 | `frameworks/base/cmds/am/src/com/android/commands/am/Am.java` :: `runHang()` |
| AMS hang | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` :: `hang()` |
| ApplicationThread.scheduleHang | `frameworks/base/core/java/android/app/ActivityThread.java` |
| ActivityThread.H.HANG | 同上 |
| InputDispatcher (ANR 检测) | `frameworks/base/services/core/java/com/android/server/input/InputDispatcher.cpp` |
| ANR traces 写入 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` :: `appNotResponding()` |
| debuggerd | `system/core/debuggerd/` |

---

## 附录 B:ANR 类型矩阵

| 类型 | 触发条件 | 超时 | am hang 触发? | 现场文件 |
|------|---------|------|--------------|---------|
| **Input ANR** | 主线程 5s 内未处理完输入事件 | 5s | ✅ | traces.txt |
| **Broadcast ANR** | onReceive > 10s | 10s | ❌ | traces.txt |
| **Service ANR** | Service 生命周期 > 20s | 20s | ❌ | traces.txt |
| **Provider ANR** | ContentProvider > 10s | 10s | ❌ | traces.txt |

> **am hang 只能测 Input ANR**——测其他类型 ANR 需要构造对应的应用层操作。

---

## 附录 C:am monitor 输出字段表

| 事件 | 字段 | 含义 |
|------|------|------|
| **GC** | `Concurrent mark-sweep GC` | GC 类型 |
| | `freed X (Y) / Z (W)` | 释放 X (Y 字节) / 总共 Z (W 字节) |
| | `paused Xms` | 暂停时间 |
| **Crash** | `FATAL EXCEPTION` | Java Crash |
| | `signal 11 (SIGSEGV)` | Native Crash |
| **ANR** | `Reason: Input dispatching timed out` | ANR 原因 |
| | `ANR in <pkg>` | ANR 包名 |
| **LowMemory** | `Low on memory:` | 内存告警 |
| | `XX MB available memory` | 剩余内存 |
| **Process died** | `Process <pkg> (pid) has died` | 死亡包名 + pid |

---

## 附录 D:工程资产清单

```
AmCommand/
└── scripts/
    ├── anr_capture.sh                   ← ANR 触发 + 现场采集(本文 §2.7.3)
    ├── anr_capture.ps1                  ← Windows 版
    ├── monitor_logcat.sh                ← monitor 替代方案(本文 §3.5)
    └── monitor_logcat.ps1               ← Windows 版
```

---

## 附录 E:工程基线表

| 项 | 版本/路径 |
|----|---------|
| AOSP 基线 | `android-14.0.0_r1` |
| adb 工具 | `platform-tools 34.0.0+` |
| Android Studio | Hedgehog (2023.1.1) 或更新 |
| AMS 源码 | `frameworks/base/services/core/java/com/android/server/am/` |
| InputDispatcher | `frameworks/base/services/core/java/com/android/server/input/InputDispatcher.cpp` |
| ANR 默认超时 | Input 5s / Broadcast 10s / Service 20s / Provider 10s |
| ANR 现场位置 | `/data/anr/` + dropbox `system_server_anr` |

---

## 篇尾衔接

**下一篇**:[06-自动化实战-脚本与 CI 集成](06-自动化实战-脚本与CI集成.md)——把前 5 篇的 am 命令做成可复用的工具集,集成到 CI 自动化巡检。

**回到系列目录**:[README-AmCommand系列](README-AmCommand系列.md)
