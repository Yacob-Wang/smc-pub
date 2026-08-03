# 02-进程管理三件套 - kill / crash / restart

> **本篇定位**:系列第 2 篇(稳定性触发核心)。读完能讲透 `am kill` / `am force-stop` / `am crash` / `am restart` 的差异,主动模拟一次进程死亡并保留完整现场(tombstone / dropbox / anr)。
>
> **强依赖**:
> - [01-am 命令全景](01-am命令全景与Activity触发.md)(理解 am 本质)
> - [Hprof 系列 04-内存泄漏典型案例与排查 SOP](../Hprof/04-内存泄漏典型案例与排查SOP.md)(进程死亡前的现场保留)
>
> **承接自**:[01 am 全景](01-am命令全景与Activity触发.md)
> **衔接去**:
> - [03 性能分析-profile 命令](03-性能分析入口-profile命令.md)(杀进程前先采 profile)
> - [04 dumpheap 详解](04-堆内存转储-dumpheap详解.md)(杀进程前先 dump heap)
> - [05 诊断与监控-hang-monitor](05-诊断与监控-hang-monitor.md)(监控进程死亡)
>
> **不重复内容**:本篇只讲"主动让进程死亡",**不讲**:
> - am 本质(见 01)
> - 性能 profile(见 03)
> - 堆 dump(见 04)
> - ANR 触发 hang(见 05)
>
> **基线**:AOSP `android-14.0.0_r1` + adb `platform-tools 34.0.0+`
> **风格**:源码密度 ~10%,重点放在"命令矩阵 + 死亡链路图 + 现场保留 SOP"
>
> **目录位置**:`Android_Framework/AmCommand/`
> **上一篇**:[01-am 命令全景与 Activity 触发](01-am命令全景与Activity触发.md)
> **下一篇**:[03-性能分析入口-profile 命令](03-性能分析入口-profile命令.md)

---

## 目录

- [1. 一句话定位:稳定性工程师的"主动制造事故"工具集](#1-一句话定位稳定性工程师的主动制造事故工具集)
  - [1.1 为什么要主动杀进程](#11-为什么要主动杀进程)
  - [1.2 四个杀进程命令的能力矩阵](#12-四个杀进程命令的能力矩阵)
- [2. am kill:模拟"被 LMKD 杀"](#2-am-kill模拟被-lmkd-杀)
  - [2.1 命令语法](#21-命令语法)
  - [2.2 完整调用栈](#22-完整调用栈)
  - [2.3 与 LMKD 的关系](#23-与-lmkd-的关系)
  - [2.4 实战场景](#24-实战场景)
- [3. am force-stop:模拟"用户从最近任务滑掉"](#3-am-force-stop模拟用户从最近任务滑掉)
  - [3.1 命令语法](#31-命令语法)
  - [3.2 与 am kill 的本质差异](#32-与-am-kill-的本质差异)
  - [3.3 force-stop 期间会触发什么回调](#33-force-stop-期间会触发什么回调)
  - [3.4 实战场景](#34-实战场景)
- [4. am crash:模拟"应用崩了"](#4-am-crash模拟应用崩了)
  - [4.1 命令语法](#41-命令语法)
  - [4.2 完整调用栈](#42-完整调用栈)
  - [4.3 Crash 的两种类型:Java Crash vs Native Crash](#43-crash-的两种类型java-crash-vs-native-crash)
  - [4.4 tombstone 文件结构与位置](#44-tombstone-文件结构与位置)
  - [4.5 实战场景](#45-实战场景)
- [5. am restart:重启 system_server(慎用)](#5-am-restart重启-system_server慎用)
  - [5.1 命令语法](#51-命令语法)
  - [5.2 重启过程会怎样](#52-重启过程会怎样)
  - [5.3 实战场景(很少)](#53-实战场景很少)
- [6. 进程死亡现场保留 SOP](#6-进程死亡现场保留-sop)
  - [6.1 进程死亡后,系统会留下哪些痕迹](#61-进程死亡后系统会留下哪些痕迹)
  - [6.2 五大现场位置速查表](#62-五大现场位置速查表)
  - [6.3 死亡现场采集脚本:process_crash_capture.sh](#63-死亡现场采集脚本process_crash_capture)
  - [6.4 死亡现场分析四步法](#64-死亡现场分析四步法)
- [7. 关键坑位图](#7-关键坑位图)
  - [7.1 am kill 后立即 pull 文件会失败](#71-am-kill-后立即-pull-文件会失败)
  - [7.2 am crash 后 ANR 告警风暴](#72-am-crash-后-anr-告警风暴)
  - [7.3 am restart 误用导致设备失联](#73-am-restart-误用导致设备失联)
  - [7.4 多用户设备 kill 错 user](#74-多用户设备-kill-错-user)
  - [7.5 死亡后启动 -W 测的"冷启动"会偏长](#75-死亡后启动--w-测的冷启动会偏长)
- [8. 案例库:3 个真实场景](#8-案例库3-个真实场景)
  - [8.1 案例 1:验证后台保活方案](#81-案例-1验证后台保活方案)
  - [8.2 案例 2:Native 崩溃定位(配合 addr2line)](#82-案例-2native-崩溃定位配合-addr2line)
  - [8.3 案例 3:复现"打开 5 次就崩"的偶发问题](#83-案例-3复现打开-5-次就崩的偶发问题)
- [9. 总结:架构师视角的 5 条 Takeaway](#9-总结架构师视角的-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:进程死亡回调矩阵](#附录-b进程死亡回调矩阵)
- [附录 C:工程资产清单](#附录-c工程资产清单)
- [附录 D:工程基线表](#附录-d工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. 一句话定位:稳定性工程师的"主动制造事故"工具集

### 1.1 为什么要主动杀进程

稳定性工程师 80% 的时间在"等线上事故",但 20% 的关键价值在"主动制造事故"——主动复现偶发问题、验证保活方案、压测边界场景。

| 痛点 | 主动杀进程的价值 |
|------|---------------|
| "用户反馈 app 偶尔崩" | `am crash` 主动触发 100 次,看统计 |
| "后台保活方案有没有效" | `am force-stop` 后,看多久自己拉起 |
| "复现'打开 5 次就崩'的偶发" | `am kill` + `am start` 循环 50 次 |
| "Native 崩溃怎么定位" | `am crash` 触发 + 拉 tombstone + addr2line |
| "系统低内存下 app 表现" | `am send-trim-memory` + `am kill` 组合 |

> **"主动杀" + "保留现场" + "复现规律"** = 稳定性工程师的核心能力闭环。

### 1.2 四个杀进程命令的能力矩阵

| 命令 | 模拟场景 | 系统行为 | 现场保留位置 | 实战频率 |
|------|---------|---------|------------|---------|
| `am kill <pkg>` | LMKD 杀后台 | 进程被 SIGKILL,**无回调** | dropbox `system_server` 日志 | ⭐⭐⭐⭐ |
| `am kill-all` | 系统低内存 | 同 am kill | 同上 | ⭐⭐ |
| `am force-stop <pkg>` | 用户滑掉任务 | 走完 onStop/onDestroy,**有回调** | dropbox + ams 状态 | ⭐⭐⭐⭐⭐ |
| `am crash <pkg>` | 应用崩了 | 触发 native crash,**生成 tombstone** | `/data/tombstones/` | ⭐⭐⭐⭐ |
| `am restart` | 设备软重启 | 重启 system_server | system logcat | ⭐(慎用) |

**关键区分**:
- `am kill` = 软杀(等同 LMKD,**无回调**)
- `am force-stop` = 强杀(**有回调**,清任务栈)
- `am crash` = 触发 native crash(**生成 tombstone**)
- `am restart` = 重启 system_server(**慎用**)

---

## 2. am kill:模拟"被 LMKD 杀"

### 2.1 命令语法

```bash
# 杀单个进程
adb shell am kill com.example.app

# 杀所有后台进程
adb shell am kill-all

# 指定 user
adb shell am kill --user 0 com.example.app
```

### 2.2 完整调用栈

```
adb shell am kill com.example.app
        │ 跳 1
        ▼
[am.jar 进程]  ActivityManagerShellCommand.runKill()
   └─ IActivityManager.killBackgroundProcesses()
        │ 跳 2:Binder IPC
        ▼
[system_server 进程]  AMS.killBackgroundProcesses()
   └─ 检查:进程是否在后台(backgroundAppId < 0 || 进程已 cache)
   └─ ProcessList.killProcessesWhenRemoved() ← ★ 真正杀进程
        └─ Process.kill()  →  ProcessList.removeProcessLocked()
              └─ Process.killGroup()  →  Process.sendSignal(SIGKILL)
                    │
                    │ 跳 3:内核信号
                    ▼
[kernel]  signal.c: __send_signal()
   └─ target_process 收到 SIGKILL
        └─ do_exit()  → 释放所有资源
        └─ 进程消失
```

### 2.3 与 LMKD 的关系

**LMKD(Low Memory Killer)** 是 Android 的低内存杀手,通常在 `lmkd` 守护进程内运行。`am kill` 走的是和 LMKD **几乎相同**的代码路径:

```
LMKD 检测到内存压力
   └─ 通过 cgroup 或 netlink 选目标进程
   └─ ProcessList.killProcessesWhenRemoved()  ← ★ 同一个方法
         └─ Process.kill() → SIGKILL

am kill com.example.app
   └─ IActivityManager.killBackgroundProcesses()
         └─ ProcessList.killProcessesWhenRemoved()  ← ★ 同一个方法
               └─ Process.kill() → SIGKILL
```

> **关键洞察**:`am kill` 是用 AMS 的 API 来模拟 LMKD 行为,所以杀进程时**不会**走 `onDestroy` 等回调——这正是 LMKD 的"软杀"语义。

### 2.4 实战场景

**场景 1:验证后台保活方案**

```bash
# 1. 启动 app
adb shell am start-activity -n com.example.app/.ui.MainActivity

# 2. 退到后台
adb shell input keyevent KEYCODE_HOME
sleep 2

# 3. am kill(等同 LMKD)
adb shell am kill com.example.app

# 4. 立刻看进程
adb shell ps -A | grep com.example.app
# (空 → 被杀了)

# 5. 等 5 秒,看是否被保活方案拉起
sleep 5
adb shell ps -A | grep com.example.app
# (有 → 保活生效)
# (空 → 保活失败)
```

**场景 2:压测冷启动 + 内存**

```bash
# 循环 50 次,模拟"被 LMKD 后冷启动"
for i in {1..50}; do
  adb shell am start-activity -n com.example.app/.ui.MainActivity
  sleep 2
  adb shell input keyevent KEYCODE_HOME
  sleep 1
  adb shell am kill com.example.app
  sleep 1
done
```

---

## 3. am force-stop:模拟"用户从最近任务滑掉"

### 3.1 命令语法

```bash
# 强杀单个 app
adb shell am force-stop com.example.app

# 指定 user
adb shell am force-stop --user 0 com.example.app
```

### 3.2 与 am kill 的本质差异

| 维度 | `am kill` | `am force-stop` |
|------|----------|-----------------|
| **调用入口** | `killBackgroundProcesses` | `forceStopPackage` |
| **触发条件** | 进程必须在后台 | 无限制(前台也行) |
| **进程回调** | 无(SIGKILL) | **有**(onStop / onDestroy) |
| **任务栈** | 保留 | **清空** |
| **闹钟/JobScheduler** | 保留 | **清空** |
| **PendingIntent** | 保留 | **清空** |
| **典型模拟** | LMKD 杀 | 用户滑掉任务 / 设置里"强行停止" |
| **进程死亡** | 软杀 | 强杀 + 清状态 |

> **实战选型**:
> - 想测"后台被回收" → `am kill`
> - 想测"用户从最近任务滑掉" → `am force-stop`

### 3.3 force-stop 期间会触发什么回调

```
am force-stop com.example.app
        ▼
AMS.forceStopPackage()
   ├─ 1. 清理 PendingIntent
   ├─ 2. 清理 AlarmManager
   ├─ 3. 清理 JobScheduler
   ├─ 4. 清理 ContentProvider 客户端
   ├─ 5. 清理 Activity 任务栈
   ├─ 6. ActivityManagerService.handleAppDiedLocked()
   │      └─ 触发 Application.onTerminate()(如果实现了)
   │      └─ 触发所有 Service / Receiver / Provider 的 onDestroy
   ├─ 7. ProcessList.killPackageProcesses()  →  Process.kill()  →  SIGKILL
   └─ 8. 进程退出
```

**应用层能观察到的回调**:

```java
// 1. Activity 回调(force-stop 时会触发)
onPause() → onStop() → onDestroy()

// 2. Service 回调
onDestroy()

// 3. Application.onTerminate()(只有 force-stop 会调,am kill 不会)
// ⚠️ Android 官方说 onTerminate 永远不会被调用,但 am force-stop 是个例外

// 4. ContentProvider 客户端
// 全部断开
```

### 3.4 实战场景

**场景:验证"强行停止"后能否自启动**

```bash
# 1. force-stop(模拟用户从设置里"强行停止")
adb shell am force-stop com.example.app

# 2. 检查 PendingIntent / Alarm 是否被清
adb shell dumpsys alarm | grep com.example.app
# 预期:无(被清了)

# 3. 5 秒后,看 app 是否被系统 / 第三方 / 自身拉起
sleep 5
adb shell ps -A | grep com.example.app
# (空 → 彻底死了,这是 Android 7+ 的设计)
```

> **关键设计**:Android 7+ 引入 force-stop 后,**所有** PendingIntent / Alarm / Job 都被清,系统也不会主动拉起。第三方推送只有"白名单通道"(小米推送 / 华为 Push)能恢复。

---

## 4. am crash:模拟"应用崩了"

### 4.1 命令语法

```bash
# 触发 native crash
adb shell am crash com.example.app

# 指定 user
adb shell am crash --user 0 com.example.app
```

### 4.2 完整调用栈

```
adb shell am crash com.example.app
        │ 跳 1
        ▼
[am.jar 进程]  ActivityManagerShellCommand.runCrash()
   └─ IActivityManager.crashApplicationWithType()
        │ 跳 2:Binder IPC
        ▼
[system_server 进程]  AMS.crashApplicationWithType()
   └─ 检查权限
   └─ 找到目标进程的 IApplicationThread
   └─ IApplicationThread.scheduleCrash()  ★ 跨进程
        │ 跳 3
        ▼
[目标 app 进程]  ApplicationThread.scheduleCrash()
   └─ 跨进程参数序列化
   └─ sendMessage(H.CRASH_APP, ...)
        │ 跳 4:主线程
        ▼
[app 主线程]  ActivityThread.handleCrashApplication()
   └─ 主动 throw RuntimeException
        └─ 进程退出,生成 tombstone
```

**关键源码(精简版)**:

```java
// frameworks/base/core/java/android/app/ActivityThread.java
private class ApplicationThread extends IApplicationThread.Stub {
    public void scheduleCrash(String message) {
        // ★ 不做参数校验,直接投递到主线程
        sendMessage(H.CRASH_APP, message);
    }
}

// 主线程 Handler
case H.CRASH_APP:
    throw new RuntimeException(message);  // ★ 主动抛异常
```

> **注意**:`am crash` 触发的 crash **不是 native crash**(虽然命令名叫 crash),而是**主线程主动抛 Java RuntimeException**。如果要测 native crash,需要别的方式(见 [§4.3](#43-crash-的两种类型java-crash-vs-native-crash))。

### 4.3 Crash 的两种类型:Java Crash vs Native Crash

| 维度 | Java Crash(am crash) | Native Crash |
|------|---------------------|--------------|
| **触发方式** | `throw RuntimeException` | SIGSEGV / SIGABRT / SIGBUS |
| **栈格式** | Java 栈(JVM 字节码) | Native 栈(机器码) |
| **现场文件** | dropbox `system_app_crash` | `/data/tombstones/tombstone_XX` |
| **分析工具** | logcat + 源码对照 | tombstone + addr2line / ndk-stack |
| **影响范围** | 单线程崩溃,可恢复 | 进程立即死亡 |
| **am 触发** | ✅ `am crash` | ❌(需其他工具) |

**怎么触发 native crash?(无内置 am 命令)**

```bash
# 方案 1:用 debuggerd(后续支持)
adb shell debuggerd com.example.app  # Android 14+ 实验性

# 方案 2:用 debug-only 工具
adb shell am start-activity -a android.intent.action.VIEW \
  --es forceNativeCrash true  # 需要 app 配合

# 方案 3:Monkey 随机触发
adb shell monkey -p com.example.app --throttle 1000 -v 1000

# 方案 4:代码层面 throw new RuntimeException
```

### 4.4 tombstone 文件结构与位置

**位置**:`/data/tombstones/`(需要 root 读取)

```
$ adb shell ls /data/tombstones/
tombstone_00
tombstone_01
...
```

**文件结构**:

```
*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
Build fingerprint: 'Xiaomi/odin/odin:14/UQK1.240524.001/...'
Revision: '0'
ABI: 'arm64'
Timestamp: 2024-06-22 14:32:15.123456+0800
Process uptime: 0:00:23.456
Cmdline: com.example.app
pid: 12345, tid: 12346, name: Signal Catcher  >>> com.example.app <<<

signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
    r0  0x0000000000000000  r1  0x0000007fffffffff
    r2  0x0000000000000000  r3  0xffffffffffffffff
    ...
    x19 0x0000007f12345678  x20 0x0000007f12345690

backtrace:
      #00 pc 0x0000000000123456  /data/app/.../libexample.so (Java_com_example_app_NativeHelper_crash+24)
      #01 pc 0x0000000000234567  /data/app/.../libexample.so (SomeOtherNativeFunc+96)
      #02 pc 0x0000000000345678  /system/lib64/libc.so (abort+120)

memory map:
    0x7f12345000-0x7f12346000 r-xp  /data/app/.../libexample.so
    0x7f23456000-0x7f23457000 rw-p  [stack]
    ...
```

**关键字段**:
- `signal 11 (SIGSEGV)`:段错误
- `signal 6 (SIGABRT)`:abort,常见于 assert 失败
- `backtrace`:栈,核心定位点
- `Cmdline`:哪个进程

### 4.5 实战场景

**场景 1:压测 Crash 后能否自愈**

```bash
# 触发 crash 100 次,看统计
for i in {1..100}; do
  adb shell am start-activity -n com.example.app/.ui.MainActivity
  sleep 5
  adb shell am crash com.example.app
  sleep 3  # 等 crash 处理 + 系统恢复
done

# 统计 dropbox
adb shell dumpsys dropbox --print | grep "system_app_crash" | wc -l
```

**场景 2:验证 CrashHandler 是否生效**

```java
// app 内部
public class MyCrashHandler implements Thread.UncaughtExceptionHandler {
    @Override
    public void uncaughtException(Thread t, Throwable e) {
        // 上报崩溃
        CrashReport.report(t, e);
        // 让系统处理(进程退出)
        defaultHandler.uncaughtException(t, e);
    }
}
```

```bash
# 触发后检查
adb shell am crash com.example.app
adb logcat -d | grep "MyCrashHandler"
# 看到 "CrashHandler.uncaughtException" → 生效
```

**场景 3:触发 native crash(配合 am crash 之外的工具)**

```bash
# 1. 装一个 native crash 测试 app
adb install test-native-crash.apk

# 2. 启动后用 jdb 触发 native crash
adb shell am start-activity -n com.test.crash/.MainActivity
# 然后 app 内部调 nativeFunctionThatCrashes()
# 产生 /data/tombstones/tombstone_00

# 3. 拉 tombstone
adb pull /data/tombstones/tombstone_00 ./
```

---

## 5. am restart:重启 system_server(慎用)

### 5.1 命令语法

```bash
# 重启 system_server
adb shell am restart

# 带原因(写到 log)
adb shell am restart --reason "stability_test"
```

### 5.2 重启过程会怎样

```
am restart
   ▼
AMS.restart()
   └─ Process.killProcess(Process.myPid())  ← ★ system_server 杀自己
        └─ init 进程看 system_server 死,会重新启动它
              └─ 整个 Android 框架重启
                    └─ 所有 app 进程都被 Zygote 一起杀掉
                          └─ 设备"卡顿" 10-30 秒
```

**会发生什么**:
1. system_server 死亡 → Zygote 收到信号 → 重启 system_server
2. 期间所有 app 进程都被杀(包括前台 app)
3. ActivityManagerService、WindowManager、PackageManager 等全部重启
4. 用户的 app 全部被关闭(类似"软重启")
5. 期间设备会卡顿 10-30 秒

### 5.3 实战场景(很少)

```bash
# 场景 1:测试 framework 修改后的回归
# (改 framework 代码后,需要重启 system_server 让新代码生效)

# 场景 2:测试系统状态恢复
# (在持续运行 24 小时后,模拟 system_server 死亡,看 app 状态如何恢复)
```

**强烈不建议**:
- ❌ 线上设备跑 am restart(用户感知 100% 卡顿)
- ❌ 压测期间跑(所有压测数据归零)
- ❌ 自动化脚本里跑(会卡后续步骤)

---

## 6. 进程死亡现场保留 SOP

### 6.1 进程死亡后,系统会留下哪些痕迹

```
am kill / am force-stop / am crash
   │
   ├─ kernel: process_struct 被释放,但保留 coredump(默认关闭)
   │
   ├─ system_server:
   │    ├─ dropbox 记录事件(系统日志归档)
   │    ├─ activity / ams 状态变更
   │    └─ 如果是 Crash:写 ANR / Crash 日志
   │
   ├─ logd: logcat 保留(默认 buffer 256KB / 4MB)
   │
   ├─ tombstone (仅 native crash): /data/tombstones/
   │
   └─ anr traces (仅 ANR): /data/anr/anr_*
```

### 6.2 五大现场位置速查表

| 位置 | 内容 | 适用命令 | 路径 | 是否需要 root |
|------|------|---------|------|-------------|
| **dropbox** | 系统事件归档(am_proc_died / am_proc_start / system_app_crash 等) | 所有 | `/data/system/dropbox/` | 通常需要 |
| **tombstone** | Native crash 现场 | Native crash | `/data/tombstones/tombstone_*` | 需要 root |
| **ANR traces** | ANR 现场 | 触发 ANR 后 | `/data/anr/anr_*` | 部分 OEM 可读 |
| **logcat** | 实时事件流 | 所有 | `adb logcat -d` | 否(直接 adb) |
| **dumpsys** | 系统状态快照 | 所有 | `adb shell dumpsys` | 否(直接 adb) |

**实战拉取命令**:

```bash
# 1. dropbox(需要 root 或 debug 包)
adb shell su -c "dumpsys dropbox --print" 2>/dev/null
# 或
adb shell dumpsys dropbox --print  # debug 包可以

# 2. tombstone
adb shell su -c "ls /data/tombstones/"
adb pull /data/tombstones/ ./tombstones/

# 3. ANR
adb shell ls /data/anr/
adb pull /data/anr/ ./anr/

# 4. logcat(最方便)
adb logcat -d -b all > ./logcat_full.txt

# 5. dumpsys
adb shell dumpsys > ./dumpsys_full.txt
```

### 6.3 死亡现场采集脚本:process_crash_capture.sh

见 `scripts/process_crash_capture.sh`:

```bash
#!/bin/bash
# process_crash_capture.sh
# 主动触发 crash 并采集完整现场
# 流程:拉 logcat → 触发 crash → 拉 dropsbox → 拉 tombstone → 拉 ANR

set -e
PKG="$1"
OUT_DIR="${2:-./crash_capture_$(date +%Y%m%d_%H%M%S)}"

[ -z "$PKG" ] && { echo "用法: $0 <package> [output_dir]"; exit 1; }

mkdir -p "$OUT_DIR"
echo "=== 现场输出目录: $OUT_DIR ==="

# 1. 拉当前 logcat
echo "[1/5] 拉当前 logcat..."
adb logcat -d -b all > "$OUT_DIR/logcat_before.log"

# 2. 触发 crash
echo "[2/5] 触发 am crash $PKG ..."
adb shell am crash "$PKG"
sleep 3  # 等 dropbox 写入

# 3. 拉 crash 后 logcat
echo "[3/5] 拉 crash 后 logcat..."
adb logcat -d -b all > "$OUT_DIR/logcat_after.log"

# 4. 拉 dropbox
echo "[4/5] 拉 dropbox..."
adb shell dumpsys dropbox --print 2>/dev/null > "$OUT_DIR/dropbox.log" || \
  echo "  (dropbox 需要 root 或 debug 包)"

# 5. 拉 tombstone / anr
echo "[5/5] 拉 tombstone / anr ..."
mkdir -p "$OUT_DIR/tombstones" "$OUT_DIR/anr"
adb pull /data/tombstones/ "$OUT_DIR/tombstones/" 2>/dev/null || echo "  (tombstone 需要 root)"
adb pull /data/anr/ "$OUT_DIR/anr/" 2>/dev/null || echo "  (anr 不存在或需要 root)"

# 6. 生成简要报告
cat > "$OUT_DIR/REPORT.md" <<EOF
# Crash 现场报告

- 包名: $PKG
- 时间: $(date)
- 触发命令: am crash $PKG

## 关键文件
- logcat_before.log: crash 前的全 buffer logcat
- logcat_after.log: crash 后的全 buffer logcat
- dropbox.log: dropbox 事件(am_proc_died, system_app_crash 等)
- tombstones/: native crash 现场
- anr/: ANR 现场

## 快速分析步骤
1. grep "FATAL" logcat_after.log
2. grep "AndroidRuntime" logcat_after.log
3. grep "$PKG" dropbox.log
4. 看 tombstones/ 里的栈
EOF

echo ""
echo "========================================"
echo "Crash 现场已采集到: $OUT_DIR"
echo "看 REPORT.md 了解快速分析步骤"
echo "========================================"
```

(Windows 版本见 `scripts/process_crash_capture.ps1`)

### 6.4 死亡现场分析四步法

**Step 1:确认死亡原因**

```bash
# 1. 看 logcat 关键词
grep -E "FATAL|AndroidRuntime|am_proc_died" logcat_after.log

# 典型输出:
# E AndroidRuntime: FATAL EXCEPTION: main
# E AndroidRuntime: Process: com.example.app, PID: 12345
# E AndroidRuntime: java.lang.NullPointerException: ...
# I ActivityManager: Process com.example.app has died
```

**Step 2:定位根因**

```bash
# 看 Java 栈
grep -A 30 "FATAL EXCEPTION" logcat_after.log

# 典型栈:
# java.lang.NullPointerException: Attempt to invoke virtual method '...' on a null object reference
#   at com.example.app.ui.MainActivity.onCreate(MainActivity.java:42)
#   at android.app.Activity.performCreate(Activity.java:8095)
#   ...
```

**Step 3:看 dropbox 上下文**

```bash
grep "$PKG" dropbox.log

# 典型:
# 2024-06-22 14:32:15 system_app_crash (text, 4523 bytes)
# Process: com.example.app
# ...
```

**Step 4:看 tombstone(如果是 native)**

```bash
# 看每个 tombstone 顶部
head -20 tombstones/tombstone_00

# 关键字段:
# signal 11 (SIGSEGV)
# backtrace:
#   #00 pc 0x...  /data/app/.../libexample.so (crash+24)
```

---

## 7. 关键坑位图

### 7.1 am kill 后立即 pull 文件会失败

**坑**:

```bash
adb shell am kill com.example.app
adb pull /data/data/com.example.app/files/state.json ./
# failed to stat: No such file or directory
```

**根因**:进程被 kill,内部 fd 关闭,文件被释放。

**修**:kill 前先 pull。

### 7.2 am crash 后 ANR 告警风暴

**坑**:线上跑了 `am crash` 压测脚本,告警系统收到 100 个 "主线程 5 秒无响应"。

**根因**:`am crash` 触发的 RuntimeException 在主线程,导致主线程 5s+ 无响应(被 ANR 监测误判)。

**修**:

```bash
# 1. 压测期间关闭 ANR 监测
adb shell settings put global anr_show_background 0

# 2. 或在 app 端做 CrashHandler 时立即退出
# 不要在 CrashHandler 里做耗时操作
```

### 7.3 am restart 误用导致设备失联

**坑**:自动化脚本误加 `am restart`,所有设备 30 秒无响应。

**根因**:`am restart` 让 system_server 自杀,所有 app 死。

**修**:
- 自动化脚本中**禁用** `am restart`
- 写一个"沙箱"命令检查清单

### 7.4 多用户设备 kill 错 user

**坑**:多用户设备上,`am kill com.example.app` 只杀 user 0 的进程,user 10 的 app 还活着。

**修**:

```bash
# 显式指定 user
adb shell am kill --user 0 com.example.app
adb shell am kill --user 10 com.example.app

# 或循环所有 user
for u in 0 10; do
  adb shell am kill --user $u com.example.app
done
```

### 7.5 死亡后启动 -W 测的"冷启动"会偏长

**坑**:

```bash
# 1. 杀进程
adb shell am force-stop com.example.app

# 2. 立刻测冷启动
adb shell am start-activity -W -n com.example.app/.ui.MainActivity
# TotalTime: 1847ms
```

**实际不是纯冷启动**——因为 `am force-stop` 后系统状态还没完全回收(任务栈 / PendingIntent)。

**修**:kill 后等 1-2 秒,或用 `am kill`(更接近 LMKD 行为)。

---

## 8. 案例库:3 个真实场景

### 8.1 案例 1:验证后台保活方案

**现象**:产品说"我们用了 X 厂商推送,可以保活",需要验证。

**用 am 解决**:

```bash
#!/bin/bash
# 保活方案验证脚本
PKG=com.example.app
START=$(date +%s)
SURVIVED=0
TOTAL=20

for i in $(seq 1 $TOTAL); do
  # 1. 启动
  adb shell am start-activity -n $PKG/.ui.MainActivity >/dev/null 2>&1
  sleep 2

  # 2. 退后台
  adb shell input keyevent KEYCODE_HOME
  sleep 1

  # 3. am kill(模拟 LMKD)
  adb shell am kill $PKG
  sleep 5  # 5 秒内能否被保活

  # 4. 检查
  if adb shell pidof $PKG >/dev/null 2>&1; then
    SURVIVED=$((SURVIVED + 1))
  fi

  # 5. 清理
  adb shell am force-stop $PKG
  sleep 1
done

END=$(date +%s)
DURATION=$((END - START))
RATE=$(echo "scale=1; $SURVIVED * 100 / $TOTAL" | bc)

echo "========================================"
echo "保活率: $SURVIVED / $TOTAL ($RATE%)"
echo "总耗时: ${DURATION}s"
echo "========================================"
```

**判断标准**:
- 保活率 > 80%:方案有效
- 保活率 50-80%:方案部分有效
- 保活率 < 50%:方案无效

### 8.2 案例 2:Native 崩溃定位(配合 addr2line)

**现象**:线上反馈"Native 崩溃,看 tombstone 不知道是哪个函数"。

**完整流程**:

```bash
# 1. 触发 native crash(配合 monkey 或 jdb)
adb shell am start-activity -n com.example.app/.ui.MainActivity
adb shell monkey -p com.example.app --throttle 1000 -v 1000

# 2. 拉 tombstone
adb pull /data/tombstones/ ./tombstones/

# 3. 找到关键地址
cat tombstones/tombstone_00 | grep "backtrace"
# backtrace:
#   #00 pc 0x0000000000123456  /data/app/.../libexample.so
#   #01 pc 0x0000000000234567  /data/app/.../libexample.so

# 4. 用 addr2line 解析
addr2line -e ./libexample.so -f 0x1234 0x5678

# 输出:
# Java_com_example_app_NativeHelper_crash
# /workspace/src/main/cpp/native_helper.cpp:42
```

### 8.3 案例 3:复现"打开 5 次就崩"的偶发问题

**现象**:QA 反馈"反复打开关闭 5 次,app 必崩"。

**用 am 复现**:

```bash
#!/bin/bash
# 5 次必崩复现脚本
PKG=com.example.app
ACT=$PKG/.ui.MainActivity

for i in {1..10}; do
  echo "=== 第 $i 轮 ==="
  for j in {1..5}; do
    echo "  打开第 $j 次"
    adb shell am start-activity -n $ACT
    sleep 2
    adb shell input keyevent KEYCODE_BACK
    sleep 1
  done
  sleep 2

  # 检查是否崩
  if ! adb shell pidof $PKG >/dev/null 2>&1; then
    echo "  ★ app 崩了,捕获现场"
    adb logcat -d -b all > crash_$i.log
    adb shell dumpsys dropbox --print > dropbox_$i.log 2>/dev/null
    break
  fi
done
```

**定位**:dumpheap + 复现 + 差集分析(详见 [Hprof 系列 04](../Hprof/04-内存泄漏典型案例与排查SOP.md))。

---

## 9. 总结:架构师视角的 5 条 Takeaway

1. **杀进程的 4 个命令对应 4 种"事故"**:`am kill`(LMKD 软杀)/ `am force-stop`(用户强杀)/ `am crash`(Java 崩)/ `am restart`(系统级重启,慎用)。
2. **am kill 不走回调,am force-stop 走完整 onDestroy 链**——这是 90% 测试脚本效果不符合预期的根因。
3. **am crash 触发的是 Java RuntimeException,不是 native crash**——要测 native crash 需用 monkey / jdb / debuggerd。
4. **死亡现场保留靠 5 大位置**——dropbox / tombstone / anr / logcat / dumpsys,**触发死亡前就要把 logcat 拉一份**。
5. **保活方案验证 = am kill + 看是否能 5 秒内被拉起**——保活率 > 80% 才算有效,这是行业基线。

---

## 附录 A:核心源码路径索引

| 模块 | 路径 |
|------|------|
| am.jar kill/crash 入口 | `frameworks/base/cmds/am/src/com/android/commands/am/Am.java` |
| AMS killBackgroundProcesses | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` |
| AMS forceStopPackage | 同上 |
| AMS crashApplicationWithType | 同上 |
| ProcessList.killProcessesWhenRemoved | `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` |
| Process.kill | `frameworks/base/core/java/android/os/Process.java` |
| ApplicationThread.scheduleCrash | `frameworks/base/core/java/android/app/ActivityThread.java` |
| LMKD 用户态守护 | `system/lmkd/lmkd.cpp` |
| debuggerd | `system/core/debuggerd/` |

---

## 附录 B:进程死亡回调矩阵

| 命令 | Activity onDestroy | Service onDestroy | Application.onTerminate | onTrimMemory |
|------|------------------|------------------|------------------------|--------------|
| `am kill` | ❌ | ❌ | ❌ | ❌(进程被 SIGKILL) |
| `am force-stop` | ✅ | ✅ | ✅(实际会调) | ❌ |
| `am crash` | ❌(抛异常中断) | ❌ | ❌ | ❌ |
| `am restart` | ✅(系统级) | ✅ | ✅ | ✅(TRIM_MEMORY_COMPLETE) |

---

## 附录 C:工程资产清单

```
AmCommand/
└── scripts/
    ├── process_crash_capture.sh         ← 主动 crash + 现场采集(本文 §6.3)
    ├── process_crash_capture.ps1        ← Windows 版
    └── (后续)survival_rate_test.sh      ← 保活率测试(本文 §8.1)
```

---

## 附录 D:工程基线表

| 项 | 版本/路径 |
|----|---------|
| AOSP 基线 | `android-14.0.0_r1` |
| adb 工具 | `platform-tools 34.0.0+` |
| Android Studio | Hedgehog (2023.1.1) 或更新 |
| AMS 源码 | `frameworks/base/services/core/java/com/android/server/am/` |
| ProcessList 源码 | `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` |
| debuggerd | `system/core/debuggerd/` |
| addr2line | NDK `toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-addr2line` |

---

## 篇尾衔接

**下一篇**:[03-性能分析入口-profile 命令](03-性能分析入口-profile命令.md)——`am profile` 启动/停止 Method Trace,产出 trace 文件怎么解析。

**回到系列目录**:[README-AmCommand系列](README-AmCommand系列.md)
