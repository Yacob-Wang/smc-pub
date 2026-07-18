# 01-am 命令全景与 Activity 触发

> **本篇定位**:系列第 1 篇(全局观)。读完能讲透 am 命令本质,理解 AMS 怎么接收 am 请求,熟练使用 `am start-activity` 启动任意 Activity。
>
> **强依赖**:无(系列入口)
> **承接自**:无
> **衔接去**:[02 进程管理三件套](02-进程管理三件套-kill-crash-restart.md) 讲杀进程 / 模拟 crash, [04 dumpheap 详解](04-堆内存转储-dumpheap详解.md) 讲内存 dump。
>
> **不重复内容**:本篇只讲"am 本质 + Activity 启动",**不讲**:
> - 进程管理(见 02)
> - 性能 profile(见 03)
> - 堆 dump(见 04)
> - 诊断监控 hang/monitor(见 05)
>
> **基线**:AOSP `android-14.0.0_r1` + adb `platform-tools 34.0.0+`
> **风格**:源码密度 ~10%,重点放在"调用栈图 + 命令矩阵 + 决策树"
>
> **目录位置**:`Android_Framework/AmCommand/`
> **上一篇**:无(系列入口)
> **下一篇**:[02-进程管理三件套-kill-crash-restart](02-进程管理三件套-kill-crash-restart.md)

---

## 目录

- [1. am 命令的本质:AMS 的"shell 外壳"](#1-am-命令的本质ams-的shell-外壳)
  - [1.1 一句话定位](#11-一句话定位)
  - [1.2 am 工具的归属:am.jar 是什么](#12-am-工具的归属amjar-是什么)
  - [1.3 am 命令的版本演进](#13-am-命令的版本演进)
- [2. am 命令的完整调用栈](#2-am-命令的完整调用栈)
  - [2.1 跨进程通信全景图](#21-跨进程通信全景图)
  - [2.2 shell 端:ActivityManagerShellCommand 怎么解析](#22-shell-端activitymanagershellcommand-怎么解析)
  - [2.3 system_server 端:AMS 怎么分发](#23-system_server-端ams-怎么分发)
  - [2.4 app 端:ApplicationThread 怎么接收](#24-app-端applicationthread-怎么接收)
- [3. am 全命令矩阵](#3-am-全命令矩阵)
  - [3.1 进程管理类](#31-进程管理类)
  - [3.2 组件启动类](#32-组件启动类)
  - [3.3 诊断监控类](#33-诊断监控类)
  - [3.4 内存与性能类](#34-内存与性能类)
  - [3.5 选型决策树](#35-选型决策树)
- [4. am start-activity 详解](#4-am-start-activity-详解)
  - [4.1 最简单的启动](#41-最简单的启动)
  - [4.2 五大参数矩阵](#42-五大参数矩阵)
  - [4.3 Intent Flags 实战:启动模式的命令行化](#43-intent-flags-实战启动模式的命令行化)
  - [4.4 启动延迟测量:start-activity -W](#44-启动延迟测量start-activity--w)
  - [4.5 启动指定包名/组件的两种写法](#45-启动指定包名组件的两种写法)
- [5. 实战:稳定性工程师的 am start 用法集锦](#5-实战稳定性工程师的-am-start-用法集锦)
  - [5.1 场景 1:深链路直达(测试任意页面)](#51-场景-1深链路直达测试任意页面)
  - [5.2 场景 2:冷启动性能压测](#52-场景-2冷启动性能压测)
  - [5.3 场景 3:主动进入低内存状态](#53-场景-3主动进入低内存状态)
  - [5.4 场景 4:灰度包冷启动数据采集](#54-场景-4灰度包冷启动数据采集)
- [6. 关键坑位图](#6-关键坑位图)
  - [6.1 权限不足:Android 11+ 强制使用 `-n`](#61-权限不足android-11-强制使用--n)
  - [6.2 黑屏/白屏:Dumpsys activity activities 不一致](#62-黑屏白屏dumpsys-activity-activities-不一致)
  - [6.3 隐式 Intent 启动失败](#63-隐式-intent-启动失败)
  - [6.4 Android 14 的安全策略收紧](#64-android-14-的安全策略收紧)
- [7. 总结:架构师视角的 5 条 Takeaway](#7-总结架构师视角的-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:am 全命令速查表](#附录-bam-全命令速查表)
- [附录 C:Intent Flag 矩阵](#附录-cintent-flag-矩阵)
- [附录 D:工程基线表](#附录-d工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. am 命令的本质:AMS 的"shell 外壳"

### 1.1 一句话定位

**`am` 是 `ActivityManagerService` (AMS) 的命令行触发器,本质是把 shell 字符串打包成 `Intent` / `Bundle`,通过 `IBinder` 跨进程交给 AMS 执行的 IPC 客户端。**

它不直接操作 app,只负责"传达指令"。所有真正的逻辑都在:
- `system_server` 进程里的 AMS
- 或者被操作 app 进程里的 `ApplicationThread` / ART

### 1.2 am 工具的归属:am.jar 是什么

am 工具的源码在 AOSP `frameworks/base/cmds/am/`,核心类只有一个:

```
frameworks/base/cmds/am/
├── Android.bp
└── src/com/android/commands/am/Am.java       ← 入口类,继承 BaseCommand
```

构建产物是 `/system/framework/am.jar`,在设备上以 `app_process` 启动一个独立进程执行。**它和 app 进程、system_server 进程都是分开的**——典型的"三进程"模型。

```
adb shell am start ...
        ↓ (进程 A: adb shell)
[am.jar 启动为 app_process 进程]
        ↓ (进程 B: am 进程,跨进程调用)
[IBinder: ActivityManagerNative → AMS]
        ↓ (进程 C: system_server)
[AMS 在 system_server 进程]
        ↓ (进程 D: 目标 app)
[ApplicationThread.scheduleXXX()]
        ↓
[app 主线程 Looper 处理]
```

> **4 个进程层级**:adb shell → am → system_server → app。从你按回车到 Activity 真正显示,中间跳了 4 次进程边界。

### 1.3 am 命令的版本演进

| Android 版本 | 关键变化 | 对稳定性工程师的影响 |
|------------|---------|---------------------|
| **Android 4.4** | 引入 `--user 0` 指定 user | 多用户场景的设备开始可用 |
| **Android 5.0** | 引入 `--receiver-permission` | 发送受保护广播的语法变化 |
| **Android 7.0** | 引入 `--display 0` | 多屏/折叠屏场景支持 |
| **Android 8.0** | 隐式广播限制(后台不能发) | 部分 `am broadcast` 在后台失败 |
| **Android 10** | 引入 `--task-lock` 等 task 操作 | 锁屏场景的 task 控制 |
| **Android 11** | **强制限制定向启动** | 第三方 app 不能直接 `am start <pkg>/<cls>`,必须用 `-n` |
| **Android 12** | `am dumpheap` 默认路径限制 | `/data/local/tmp` 之外需要 root |
| **Android 14** | PACKAGE_USAGE_STATS 权限收紧 | `am stack` 等子命令需要授权 |

> **本次重点讲 Android 11+ 的行为**——这是当前线上设备的主要版本。

---

## 2. am 命令的完整调用栈

### 2.1 跨进程通信全景图

```
$ adb shell am start -n com.example/.MainActivity
        │
        ▼
[adb server]    ← 本地 5037 端口
        │ (USB / TCP)
        ▼
[adb daemon on device]
        │
        ▼
[shell 用户空间]  ← adb shell 启动的 sh 进程
        │
        ▼
[am.jar 进程]    ← app_process 启动 com.android.commands.am.Am
        │
        │ ActivityManagerShellCommand.run()
        │   ├─ 解析 start 子命令
        │   ├─ 构造 Intent
        │   └─ 调用 ActivityManagerNative.getDefault().startActivityAsUser()
        │
        │ ★ 第一次跨进程(am → system_server)
        ▼
[system_server 进程]
        │
        │ AMS.startActivityAsUser()
        │   ├─ 检查权限(callingUid / intent filter)
        │   ├─ 构造 ActivityRecord
        │   ├─ ActivityTaskSupervisor 调度
        │   └─ 找到目标 app 进程的 IApplicationThread
        │
        │ ★ 第二次跨进程(system_server → app)
        ▼
[com.example app 进程]
        │
        │ ApplicationThread.scheduleLaunchActivity()
        │   ├─ 跨进程写入 ActivityClientRecord
        │   └─ 通过 H(Handler) post 到主线程
        │
        ▼
[app 主线程 Looper]
        │
        ▼
ActivityThread.handleLaunchActivity()
   └─ 真正执行 Activity.onCreate() / onStart() / onResume()
```

### 2.2 shell 端:ActivityManagerShellCommand 怎么解析

`Am.java` 内部使用 `ActivityManagerShellCommand` 来解析命令行。Android 11+ 后,该类被移到了 `frameworks/base/services/core/java/com/android/server/am/`,成为 AMS 内部类(因为和 AMS 共享数据)。

核心逻辑(精简版):

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerShellCommand.java
public int onCommand(String cmd) {
    switch (cmd) {
        case "start":  case "start-activity":
            return runStartActivity();
        case "startservice":
            return runStartService();
        case "broadcast":
            return runSendBroadcast();
        case "kill":   case "kill-all":
            return runKill();
        case "dumpheap":
            return runDumpHeap();
        // ... 30+ 个子命令
    }
}
```

**关键点**:`am` 不直接 IPC,而是通过 `IActivityManager` 这个 AIDL 接口把 Intent / 各种参数打包送过去。

### 2.3 system_server 端:AMS 怎么分发

AMS 接收到请求后,会根据子命令类型走不同分支:

```
IActivityManager.startActivityAsUser(intent, userId)
   ↓
AMS.startActivityAsUser()
   ├─ UserController.checkCallingPermission()
   ├─ ActivityStarter.startActivityInner()
   │    ├─ 解析 Intent(显式/隐式)
   │    ├─ 检查 IntentFilter
   │    ├─ 校验 intent flags
   │    └─ 找到目标 ActivityRecord
   └─ 转到 ActivityTaskSupervisor
        └─ 找到 app 进程的 IApplicationThread
             └─ IApplicationThread.scheduleLaunchActivity()
```

**稳定性视角的"陷阱位"**:
- `ActivityStarter.startActivityInner` 是 90% ANR 的起点(等 lock / 等 app 启动)
- `ActivityTaskSupervisor` 持有 mServiceLock,跨多个调用栈同步——卡 5s 就有 ANR
- `startActivityAsUser` 不等于 `startActivity`——多 user 场景行为完全不同

### 2.4 app 端:ApplicationThread 怎么接收

`IApplicationThread` 是 app 进程提供给 system_server 调用的"反相" Binder 接口。AMS 通过它把指令送到 app 主线程:

```java
// frameworks/base/core/java/android/app/ActivityThread.java
private class ApplicationThread extends IApplicationThread.Stub {
    public void scheduleLaunchActivity(ActivityClientRecord r, ...) {
        // 跨进程参数序列化
        sendMessage(H.LAUNCH_ACTIVITY, r);
    }
}
```

app 主线程的 `H` Handler 处理 `LAUNCH_ACTIVITY` 消息后,真正调 `ActivityThread.performLaunchActivity()` → 反射 `Activity.onCreate()`。

> **am 命令的"4 跳"总结**:adb shell → am 进程 → system_server(AMS)→ app 主线程。

---

## 3. am 全命令矩阵

am 一共提供 **30+** 个子命令,按用途归为 4 类。完整速查见 [附录 B](#附录-bam-全命令速查表),这里先给决策视图。

### 3.1 进程管理类

| 命令 | 作用 | Android 版本 | 实战场景 |
|------|------|------------|---------|
| `am kill <pkg>` | 杀进程(等同 LMKD) | 5.0+ | 模拟后台被回收 |
| `am kill-all` | 杀所有后台进程 | 5.0+ | 批量压测前清场 |
| `am force-stop <pkg>` | 强制停止(强杀 + 清任务栈) | 1.0+ | 模拟用户从最近任务滑掉 |
| `am crash <pkg>` | 触发 native crash | 8.0+ | 模拟 Crash 现场 |
| `am crash --user 0 <pkg>` | 指定 user 触发 crash | 8.0+ | 多用户设备 |
| `am restart` | 重启 system_server | 1.0+ | **慎用**,会让所有 app 死亡 |
| `am send-trim-memory <pid> <level>` | 主动触发 trimMemory 回调 | 4.4+ | 模拟系统低内存 |

### 3.2 组件启动类

| 命令 | 作用 | 实战场景 |
|------|------|---------|
| `am start <intent>` | 启动 Activity | **最高频** |
| `am start-activity <intent>` | 同上(显式写法) | 同上,推荐 |
| `am startservice <intent>` | 启动 Service | 验证后台服务保活 |
| `am stopservice <intent>` | 停止 Service | 验证服务清理路径 |
| `am broadcast <intent>` | 发送广播 | 测试广播接收器、模拟系统广播 |
| `am start-foreground-service <intent>` | 启动前台 Service | Android 8+ 限制下验证 |

### 3.3 诊断监控类

| 命令 | 作用 | 实战场景 |
|------|------|---------|
| `am hang [--allow-restart]` | 触发主线程 sleep 模拟 ANR | ANR 现场测试 |
| `am monitor` | 实时监控 GC / Crash / LMK | 压测期间后台观察 |
| `am monitor --gdb` | 进入 native 调试 | 死锁排查 |
| `am stack list` | 列出所有 task stack | 任务栈异常排查 |
| `am task lock / unlock` | 锁定 task(锁屏变种) | 后台保活验证 |
| `am compat enable <change-id> <pkg>` | 启用 platform compat 行为 | 平台行为切换测试 |
| `am compat reset <pkg>` | 重置 compat 行为 | 同上 |

### 3.4 内存与性能类

| 命令 | 作用 | 系列篇目 |
|------|------|---------|
| `am dumpheap <pid> <file>` | **Java 堆转储** | [04 dumpheap 详解](04-堆内存转储-dumpheap详解.md) ⬅️ |
| `am profile start <proc> <file>` | 启动 Method Trace | [03 profile 命令](03-性能分析入口-profile命令.md) |
| `am profile stop <proc>` | 停止 + pull trace | 同上 |
| `am profile start-sampling <proc> <file> <interval>` | Sampling Trace | 同上 |
| `am set-isolated-process <pkg>` | 设置 isolated process | 进程隔离验证 |
| `am get-config` | 获取 device config | 平台参数验证 |

### 3.5 选型决策树

```
要做什么?
├─ 让 app 行为改变(模拟用户)
│  ├─ 启动页面?     → am start-activity / am start
│  ├─ 启动服务?     → am startservice
│  ├─ 发广播?       → am broadcast
│  └─ 切后台/拉起?  → am start-activity + FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY
│
├─ 让 app 死亡/崩溃
│  ├─ 软杀(等同 LMKD)?  → am kill <pkg>
│  ├─ 强杀(清任务栈)?    → am force-stop <pkg>
│  └─ 主动 crash?        → am crash <pkg>
│
├─ 采集数据
│  ├─ Java 堆?         → am dumpheap (见 04)
│  ├─ Method Trace?    → am profile start (见 03)
│  └─ ANR 现场?        → am hang (见 05)
│
└─ 观察运行状态
   └─ → am monitor (见 05)
```

---

## 4. am start-activity 详解

### 4.1 最简单的启动

```bash
# 显式启动(Android 11+ 强制)
adb shell am start-activity -n com.example.app/.ui.MainActivity

# 隐式启动
adb shell am start-activity -a android.intent.action.VIEW -d "https://example.com"

# 用包名启动 launcher
adb shell am start-activity -n com.example.app/com.example.app.MainActivity
```

### 4.2 五大参数矩阵

| 参数 | 含义 | 典型值 |
|------|------|--------|
| `-a <action>` | Intent action | `android.intent.action.MAIN` / `android.intent.action.VIEW` |
| `-c <category>` | Intent category | `android.intent.category.LAUNCHER` |
| `-d <data>` | data URI | `https://example.com/page` / `tel:10086` |
| `-t <type>` | MIME type | `text/plain` / `image/*` |
| `-n <component>` | 显式 component | `com.example.app/.MainActivity` |
| `-e <key> <value>` | string extra | `-e userId 12345` |
| `--es <key> <value>` | string extra(同 -e) | 同上 |
| `--ei <key> <value>` | int extra | `--ei retry 3` |
| `--ez <key> <bool>` | boolean extra | `--ez debug true` |
| `--esn <key>` | 值为 null 的 string extra | |
| `-f <flags>` | Intent flags | `0x10000000` (NEW_TASK) |
| `-W` | wait,等启动完成返回启动耗时 | 见 §4.4 |
| `--user <uid>` | 指定 user | `0` / `10` |
| `--display <id>` | 指定 display | `0` / `1` |
| `--activity-clear-task` | 启动前清空 task | |
| `--activity-clear-top` | 清空目标之上的所有 Activity | |
| `--activity-single-top` | 类似 launchMode=singleTop | |

**一个完整示例**(稳定性测试用,带多参数):

```bash
adb shell am start-activity \
  -n com.example.app/.ui.OrderDetailActivity \
  --es orderId "ORDER_20240622_001" \
  --ei fromPush 1 \
  --ez isVip true \
  -f 0x14000000 \
  -W
```

含义:
- 显式启动 `OrderDetailActivity`
- 三个 extras:`orderId=ORDER_20240622_001`、`fromPush=1`、`isVip=true`
- flags = `0x14000000` = `FLAG_ACTIVITY_NEW_TASK | FLAG_ACTIVITY_CLEAR_TOP`
- `-W`:等启动完成,返回启动耗时(下面展开)

### 4.3 Intent Flags 实战:启动模式的命令行化

把 Java 里 `Intent.addFlags()` 的 flag 用 `-f <hex>` 写出来:

| Hex | Flag | 实战场景 |
|-----|------|---------|
| `0x10000000` | `FLAG_ACTIVITY_NEW_TASK` | 新 task 启动(必须,否则非 Activity 上下文会崩) |
| `0x04000000` | `FLAG_ACTIVITY_CLEAR_TOP` | 清掉目标之上的页面(模拟"返回"逻辑) |
| `0x20000000` | `FLAG_ACTIVITY_SINGLE_TOP` | 等同 launchMode=singleTop |
| `0x08000000` | `FLAG_ACTIVITY_MULTIPLE_TASK` | 多 task 启动(异常场景) |
| `0x00800000` | `FLAG_ACTIVITY_RESET_TASK_IF_NEEDED` | 必要时重置 task |
| `0x00400000` | `FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY` | 标记从历史启动 |

**实战组合**:

```bash
# 场景:从 launcher 直接进入"我的订单详情",清掉中间所有页面
adb shell am start-activity \
  -n com.example.app/.ui.OrderDetailActivity \
  --es orderId "123" \
  -f 0x14000000
# 0x14000000 = 0x10000000 (NEW_TASK) | 0x04000000 (CLEAR_TOP)
```

### 4.4 启动延迟测量:start-activity -W

加 `-W` 后,am 会**同步等启动完成**并返回耗时(单位:ms):

```bash
$ adb shell am start-activity -n com.example.app/.ui.MainActivity -W
Starting: Intent { cmp=com.example.app/.ui.MainActivity }
Status: ok
LaunchState: COLD
Activity: com.example.app/.ui.MainActivity
TotalTime: 847
ThisTime: 723
WaitTime: 891
```

字段含义:

| 字段 | 含义 | 稳定性意义 |
|------|------|----------|
| `Status: ok` | 是否成功 | 失败可能是权限/manifest 问题 |
| `LaunchState` | `COLD` / `WARM` / `HOT` | 冷/温/热启动 |
| `TotalTime` | 从 am 发出到首帧绘制总耗时 | **核心 KPI** |
| `ThisTime` | 从 Activity onCreate 到 onResume | 应用自己的耗时 |
| `WaitTime` | am 发出到系统调度完成 | 系统调度开销 |

> **稳定性视角**:冷启动超过 3s 用户可感知,超过 5s 算劣化,超过 8s 会被记为"启动慢"工单。`am start -W` 是离线采冷启动最轻量的方法。

### 4.5 启动指定包名/组件的两种写法

```bash
# 写法 A:显式 component(Android 11+ 必须)
adb shell am start-activity -n com.example.app/com.example.app.MainActivity
adb shell am start-activity -n com.example.app/.ui.MainActivity   # 缩写

# 写法 B:从 launcher category 启动(显式启动主入口,Android 8+ 受限)
adb shell am start-activity -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -n com.example.app/.MainActivity
```

**关键约束**(Android 11+):
- 第三方 app **不能**用 `am start <pkg>/<cls>` 不带 `-n` 的写法
- 必须用 `-n` 显式 component,否则 `SecurityException`
- 详见 §6.1 坑位

---

## 5. 实战:稳定性工程师的 am start 用法集锦

### 5.1 场景 1:深链路直达(测试任意页面)

**现象**:QA 想直接进入"我的-订单详情-退款详情-客服聊天"四级页面,但正常用户操作需要 6 次点击 + 2 个网络请求。

**用 am 解决**:

```bash
# 假设最终页面是 ChatActivity
adb shell am start-activity \
  -n com.example.app/.ui.chat.ChatActivity \
  --es orderId "123" \
  --es refundId "RF_001" \
  --es sessionId "CHAT_001" \
  -f 0x10000000
```

**前提条件**(开发侧配合):
- `ChatActivity` 在 `AndroidManifest.xml` 暴露 `android:exported="true"`
- 或在 debug 包打开 `android:debuggable="true"` 后通过 `-W` 绕过

### 5.2 场景 2:冷启动性能压测

**现象**:想知道灰度包冷启动 P50 / P99。

**用 am 解决**:

```bash
#!/bin/bash
# 冷启动压测脚本
for i in {1..20}; do
  # 1. 杀进程
  adb shell am force-stop com.example.app

  # 2. 等 1s 确保完全死亡
  sleep 1

  # 3. 启动 + 测耗时
  TIME=$(adb shell am start-activity -W -n com.example.app/.ui.MainActivity | grep "TotalTime" | awk '{print $2}')
  echo "[$i] Cold start: ${TIME}ms"
done
```

**输出示例**:

```
[1] Cold start: 1247ms
[2] Cold start: 1189ms
[3] Cold start: 1213ms
...
[20] Cold start: 1198ms
```

**判断标准**(线上基线):
- P50 ≤ 1500ms:合格
- P50 ≤ 1000ms:优秀
- P99 > 2500ms:需优化

### 5.3 场景 3:主动进入低内存状态

**现象**:要测试 app 在 `onTrimMemory(TRIM_MEMORY_RUNNING_LOW)` 时的行为,但等系统 LMKD 太慢。

**用 am 解决**:

```bash
# 触发 TRIM_MEMORY_RUNNING_LOW(level=10)
adb shell am send-trim-memory <pid> RUNNING_LOW

# 触发 TRIM_MEMORY_RUNNING_CRITICAL(level=15)
adb shell am send-trim-memory <pid> RUNNING_CRITICAL

# 触发 TRIM_MEMORY_BACKGROUND(level=40)
adb shell am send-trim-memory <pid> BACKGROUND

# 触发 TRIM_MEMORY_COMPLETE(level=80)
adb shell am send-trim-memory <pid> COMPLETE
```

**对应关系**(level 数字 vs 名字):

| level | 名字 | 触发场景 |
|-------|------|---------|
| 5 | `TRIM_MEMORY_RUNNING_MODERATE` | 系统内存吃紧,app 还在前台 |
| 10 | `TRIM_MEMORY_RUNNING_LOW` | 系统内存告警 |
| 15 | `TRIM_MEMORY_RUNNING_CRITICAL` | 系统濒临 LMK |
| 40 | `TRIM_MEMORY_BACKGROUND` | app 在后台,系统内存开始紧 |
| 60 | `TRIM_MEMORY_MODERATE` | app 在后台且低优先级 |
| 80 | `TRIM_MEMORY_COMPLETE` | app 在后台,即将被回收 |
| 80+ | `TRIM_MEMORY_UI_HIDDEN` | UI 已隐藏(无 trim 内存效果) |

### 5.4 场景 4:灰度包冷启动数据采集

**现象**:灰度期间需要采集 1000 个真实用户的冷启动数据,但 SDK 上报有 20% 漏报率。

**用 am 解决**:在测试设备上手动采集 + 上传。

```bash
# 1. 清空 logcat
adb logcat -c

# 2. 拉起 + 测时
adb shell am start-activity -W -n com.example.app/.ui.MainActivity

# 3. 从 logcat 抓 ActivityTaskManager 的启动日志
adb logcat -d ActivityTaskManager:I "*:S" | grep "Displayed"
```

**日志示例**:

```
I/ActivityTaskManager: Displayed com.example.app/.ui.MainActivity for user 0: +1s247ms
```

> **冷启动"金标准"指标**:`Displayed` 行的 +Xms。这个值 = `TotalTime` 但来源更可靠(系统直接打,无 app 篡改)。

---

## 6. 关键坑位图

### 6.1 权限不足:Android 11+ 强制使用 `-n`

**坑**:

```bash
# Android 11 之前可以这样写
adb shell am start com.example.app/.MainActivity

# Android 11+ 报错
Starting: Intent { ... }
Exception type 0: SecurityException
  Calling package ... has no access to ...
```

**修**:

```bash
# 必须显式带 -n
adb shell am start-activity -n com.example.app/.MainActivity
```

**根因**:Android 11 的 [package visibility](https://developer.android.com/training/package-visibility) 限制,shell 命令也受约束。

### 6.2 黑屏/白屏:Dumpsys activity activities 不一致

**坑**:`am start` 返回 `Status: ok`,但屏幕没变。

**排查**:

```bash
# 1. 看 activity stack 状态
adb shell dumpsys activity activities | grep -A 2 "Hist #"

# 2. 看窗口焦点
adb shell dumpsys window windows | grep "mCurrentFocus"

# 3. 看 app 进程是否 alive
adb shell ps -A | grep com.example.app
```

**常见原因**:
- Activity 在 onCreate 抛异常(看 logcat)
- 显式 Intent 缺 extras(看 logcat 的 IllegalArgumentException)
- 启动方向不对(横屏 app 在竖屏启动失败)

### 6.3 隐式 Intent 启动失败

**坑**:

```bash
adb shell am start -a android.intent.action.VIEW -d "myapp://page/123"
# 返回 Status: ok
# 但应用没启动
```

**根因**:目标 app 没在 `AndroidManifest.xml` 注册 `intent-filter` 匹配 `myapp://`。

**排查**:

```bash
# 1. 看目标 app 的 manifest 导出
adb shell dumpsys package com.example.app | grep -A 5 "Activity Resolver Table"

# 2. 看系统能解析的 intent
adb shell pm query-activities -a android.intent.action.VIEW -d "myapp://page/123"
```

### 6.4 Android 14 的安全策略收紧

**坑**:Android 14 上 `am stack list` / `am compat enable` 等命令需要新权限。

**表现**:

```
Exception type 0: SecurityException
  Permission Denial: ... requires android.permission.PACKAGE_USAGE_STATS
```

**修**:

```bash
# 1. 授权
adb shell appops set --uid <uid> GET_USAGE_STATS allow

# 2. 或用 --user 0 跑
adb shell am stack list --user 0
```

---

## 7. 总结:架构师视角的 5 条 Takeaway

1. **am 是"做"的工具,不是"看"的工具**——和 hprof/Perfetto/dumpsys 互补,组合使用才是稳定性工程师的完整工具集。
2. **4 跳进程,3 个 IPC**——am 命令看似简单,实际跨了 4 个进程边界(adb shell → am → system_server → app),3 次 Binder 调用。任何一环卡顿都会反映在用户感知上。
3. **am start-activity -W 是冷启动最轻量采法**——比 Android Studio Profiler 更接近线上真实值,且可脚本化。
4. **Android 11+ 必须显式 component**——这是 90% "am 命令在 Android 11 突然不工作"的根因。
5. **命令矩阵替代记忆**——30+ 子命令,记不住正常;用 [§3.5 决策树](#35-选型决策树) 按"想做什么"反查。

---

## 附录 A:核心源码路径索引

| 模块 | 路径 |
|------|------|
| am.jar 入口 | `frameworks/base/cmds/am/src/com/android/commands/am/Am.java` |
| ActivityManagerShellCommand | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerShellCommand.java` |
| AMS 核心 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` |
| ActivityStarter | `frameworks/base/services/core/java/com/android/server/am/ActivityStarter.java` |
| ApplicationThread | `frameworks/base/core/java/android/app/ActivityThread.java` (内部类) |
| IActivityManager AIDL | `frameworks/base/core/java/android/app/IActivityManager.aidl` |
| Intent | `frameworks/base/core/java/android/content/Intent.java` |

---

## 附录 B:am 全命令速查表

| 命令 | 用途 | 系列篇目 |
|------|------|---------|
| `start` / `start-activity` | 启动 Activity | 01(本文) |
| `startservice` | 启动 Service | 01 |
| `stopservice` | 停止 Service | 01 |
| `broadcast` | 发送广播 | 01 |
| `start-foreground-service` | 启动前台 Service | 01 |
| `kill` / `kill-all` | 杀进程(等同 LMKD) | 02 |
| `force-stop` | 强杀(清任务栈) | 02 |
| `crash` | 触发 crash | 02 |
| `restart` | 重启 system_server | 02 |
| `send-trim-memory` | 触发 trimMemory | 01 |
| `profile` / `profile start/stop` | 性能采样 | 03 |
| `dumpheap` | Java 堆转储 | **04(下一篇核心)** |
| `hang` | 触发 ANR | 05 |
| `monitor` | 监控 GC/Crash | 05 |
| `stack` | Task stack 管理 | 05 |
| `task` | Task 锁/解锁 | 05 |
| `compat` | 平台行为开关 | 01 |
| `get-config` | 设备配置 | 01 |
| `set-isolated-process` | 进程隔离 | 01 |
| `grant` / `revoke` | 权限授予/撤销 | 01 |
| `switch-user` | 切换 user | 01 |
| `stop-user` | 停止 user | 01 |

---

## 附录 C:Intent Flag 矩阵

| Hex | Flag | 说明 |
|-----|------|------|
| `0x00000001` | `FLAG_GRANT_READ_URI_PERMISSION` | 读 URI 授权 |
| `0x00000002` | `FLAG_GRANT_WRITE_URI_PERMISSION` | 写 URI 授权 |
| `0x00000004` | `FLAG_GRANT_PERSISTABLE_URI_PERMISSION` | 持久化授权 |
| `0x00000008` | `FLAG_GRANT_PREFIX_URI_PERMISSION` | 前缀授权 |
| `0x00100000` | `FLAG_ACTIVITY_NO_HISTORY` | 不进历史栈 |
| `0x00200000` | `FLAG_ACTIVITY_SINGLE_TOP` | 同 singleTop |
| `0x00400000` | `FLAG_ACTIVITY_NEW_TASK` | 新 task |
| `0x00800000` | `FLAG_ACTIVITY_MULTIPLE_TASK` | 多 task |
| `0x01000000` | `FLAG_ACTIVITY_CLEAR_TASK` | 清 task |
| `0x02000000` | `FLAG_ACTIVITY_TASK_ON_HOME` | task 置 home 之上 |
| `0x04000000` | `FLAG_ACTIVITY_CLEAR_TOP` | 清目标之上 |
| `0x08000000` | `FLAG_ACTIVITY_RESET_TASK_IF_NEEDED` | 必要时 reset |
| `0x10000000` | `FLAG_ACTIVITY_LAUNCH_ADJACENT` | 分屏模式启动 |
| `0x10000000` | `FLAG_ACTIVITY_NEW_DOCUMENT` | 新 document(API 21+) |
| `0x20000000` | `FLAG_ACTIVITY_NO_USER_ACTION` | 不算 onUserLeaveHint |
| `0x40000000` | `FLAG_ACTIVITY_REORDER_TO_FRONT` | reorder 到前面 |
| `0x80000000` | `FLAG_ACTIVITY_NO_ANIMATION` | 无动画 |

> 实战常用组合 `0x14000000` = `0x10000000 | 0x04000000` = NEW_TASK | CLEAR_TOP

---

## 附录 D:工程基线表

| 项 | 版本/路径 |
|----|---------|
| AOSP 基线 | `android-14.0.0_r1` |
| adb 工具 | `platform-tools 34.0.0+` |
| Android Studio | Hedgehog (2023.1.1) 或更新 |
| am.jar 路径 | `/system/framework/am.jar` |
| am.jar 源码 | `frameworks/base/cmds/am/` |
| AMS 源码路径 | `frameworks/base/services/core/java/com/android/server/am/` |
| IActivityManager AIDL | `frameworks/base/core/java/android/app/IActivityManager.aidl` |
| Intent 常量 | `frameworks/base/core/java/android/content/Intent.java` |

---

## 篇尾衔接

**下一篇**:[02-进程管理三件套-kill-crash-restart](02-进程管理三件套-kill-crash-restart.md)——`am kill` / `am crash` / `am restart` 怎么用,模拟一次"进程死亡"时怎么保留现场(tombstone / dropbox / anr)。

**回到系列目录**:[README-AmCommand系列](README-AmCommand系列.md)
