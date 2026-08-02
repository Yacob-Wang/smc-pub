# 03-性能分析入口 - profile 命令

> **本篇定位**:系列第 3 篇(性能触发核心)。读完能用 `am profile` 命令行启动/停止 Method Trace、产出 ART Sampling Trace 文件、用 `simpleperf` / `traceview` 解析,并理解它和 Perfetto / Android Studio Profiler 的取舍关系。
>
> **强依赖**:
> - [01-am 命令全景](01-am命令全景与Activity触发.md)(理解 am 本质)
> - [02 进程管理三件套](02-进程管理三件套-kill-crash-restart.md)(杀进程前先采 profile)
>
> **承接自**:[02 进程管理](02-进程管理三件套-kill-crash-restart.md)
> **衔接去**:
> - [04 dumpheap 详解](04-堆内存转储-dumpheap详解.md)(profile 后保留现场先 dump heap)
> - [05 诊断与监控-hang-monitor](05-诊断与监控-hang-monitor.md)(profile 期间监控事件)
> - [06 自动化实战-脚本与 CI 集成](06-自动化实战-脚本与CI集成.md)(profile 接入巡检脚本)
>
> **不重复内容**:本篇只讲"命令行触发 Method Trace + 解析",**不讲**:
> - Perfetto trace 内部原理(见 Perfetto 系列)
> - SimplePerf 命令全功能(见 Tools 系列)
> - 性能瓶颈分析方法论(性能专题文章)
>
> **基线**:AOSP `android-14.0.0_r1` + adb `platform-tools 34.0+`
> **风格**:源码密度 ~10%,重点放在"trace 类型矩阵 + 命令模板 + 解析工具链"
>
> **目录位置**:`Android_Framework/AmCommand/`
> **上一篇**:[02-进程管理三件套-kill-crash-restart](02-进程管理三件套-kill-crash-restart.md)
> **下一篇**:[04-堆内存转储-dumpheap 详解](04-堆内存转储-dumpheap详解.md)

---

## 目录

- [1. 一句话定位:稳定性的"性能采样触发器"](#1-一句话定位稳定性的性能采样触发器)
  - [1.1 为什么需要命令行 profile](#11-为什么需要命令行-profile)
  - [1.2 am profile 的能力边界](#12-am-profile-的能力边界)
- [2. am profile 完整命令族](#2-am-profile-完整命令族)
  - [2.1 命令语法总览](#21-命令语法总览)
  - [2.2 am profile start - 启动采样](#22-am-profile-start---启动采样)
  - [2.3 am profile stop - 停止采样并 pull 文件](#23-am-profile-stop---停止采样并-pull-文件)
  - [2.4 am profile dumpheap - profile 期间的辅助 dump](#24-am-profile-dumpheap---profile-期间的辅助-dump)
  - [2.5 --attach / --detach / -user 的含义](#25---attach----detach---user-的含义)
- [3. ART Trace 类型深度对比](#3-art-trace-类型深度对比)
  - [3.1 Sampling Trace vs Instrumented Trace](#31-sampling-trace-vs-instrumented-trace)
  - [3.2 trace 文件格式:traceview binary vs profcollect](#32-trace-文件格式traceview-binary-vs-profcollect)
  - [3.3 性能开销矩阵](#33-性能开销矩阵)
  - [3.4 与 Perfetto/atrace 的取舍](#34-与-perfettoatrace-的取舍)
  - [3.5 与 SimplePerf 的取舍](#35-与-simpleperf-的取舍)
- [4. 5 分钟跑通的端到端流程](#4-5-分钟跑通的端到端流程)
  - [4.1 启动 profile + 执行场景 + 停止 profile](#41-启动-profile--执行场景--停止-profile)
  - [4.2 pull trace 文件](#42-pull-trace-文件)
  - [4.3 解析工具链速查](#43-解析工具链速查)
  - [4.4 traceview / studio 打开 trace](#44-traceview--studio-打开-trace)
- [5. 进阶用法](#5-进阶用法)
  - [5.1 后台守护 profile(适用于长周期采样)](#51-后台守护-profile适用于长周期采样)
  - [5.2 多进程 profile(选 PID 而不是包名)](#52-多进程-profile选-pid-而不是包名)
  - [5.3 profile 与 dumpheap 串联(性能问题现场保留)](#53-profile-与-dumpheap-串联性能问题现场保留)
  - [5.4 profile 与 hang 串联(ANR 期间采 trace)](#54-profile-与-hang-串联anr-期间采-trace)
- [6. 关键坑位图](#6-关键坑位图)
  - [6.1 am profile stop 后文件没自动 pull](#61-am-profile-stop-后文件没自动-pull)
  - [6.2 trace 文件是空文件(没采到采样)](#62-trace-文件是空文件没采到采样)
  - [6.3 采样导致 app 卡顿,反而影响线上](#63-采样导致-app-卡顿反而影响线上)
  - [6.4 trace 文件太大,Studio 打不开](#64-trace-文件太大studio-打不开)
  - [6.5 多个 profile 并发,文件覆盖](#65-多个-profile-并发文件覆盖)
  - [6.6 profile 与 dumpheap 顺序错误导致 heap 无 profile 上下文](#66-profile-与-dumpheap-顺序错误导致-heap-无-profile-上下文)
- [7. 案例库:3 个真实场景](#7-案例库3-个真实场景)
  - [7.1 案例 1:定位冷启动慢的根因函数](#71-案例-1定位冷启动慢的根因函数)
  - [7.2 案例 2:压测期间捕获 CPU 热点函数](#72-案例-2压测期间捕获-cpu-热点函数)
  - [7.3 案例 3:线上偶发卡顿的 profile+ANR 联动](#73-案例-3线上偶发卡顿的-profileanr-联动)
- [8. 总结:架构师视角的 5 条 Takeaway](#8-总结架构师视角的-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:Trace 工具矩阵](#附录-btrace-工具矩阵)
- [附录 C:am profile 参数矩阵](#附录-cam-profile-参数矩阵)
- [附录 D:工程资产清单](#附录-d工程资产清单)
- [附录 E:工程基线表](#附录-e工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. 一句话定位:稳定性的"性能采样触发器"

### 1.1 为什么需要命令行 profile

| 痛点 | 命令行 profile 的价值 |
|------|---------------------|
| "Android Studio Profiler 只能连真机,线上海量设备用不上" | `am profile` 是 Android 自带命令,**任何 root/debuggable 设备都能跑** |
| "线上要捕获偶发卡顿,但 Studio 不可能常驻" | `am profile` 可通过 adb / 脚本触发,适合自动化场景 |
| "想采某次冷启动的完整方法栈,但 Studio profiler 的 attach 太重" | `am profile start` 一行命令启动,**开销 < 5%** |
| "想看某段代码的 CPU 热点,但又不能改 app 代码" | `am profile` 无需修改 app,**ART 内部采样**,app 无感知 |
| "要分析某个 PID 的方法栈,但 app 多进程" | `am profile start <pid> <file>`,**精确到 PID** |

> **am profile 决定了你能"采样什么"**——它是 Android 自带的 **Method Trace 触发器**,不需要 Studio、不需要改代码、不需要 root(debuggable 即可)。

### 1.2 am profile 的能力边界

| 能力 | am profile 是否能做 | 替代方案 |
|------|------------------|---------|
| Method Trace(方法级 CPU 占用)| ✅ **核心能力** | Studio Profiler / Perfetto with atrace |
| Sampling Trace(采样式方法栈)| ✅ Android 7.0+ 默认 | - |
| Instrumented Trace(插桩式方法栈)| ✅ Android 9.0+ | - |
| Syscall Trace | ❌ | strace / SimplePerf |
| Native 函数 CPU 占用 | ❌(只看 Java 层) | SimplePerf / Perfetto |
| 内存分配 Trace | ❌ | `am dumpheap` / Studio Memory Profiler |
| ANR / 卡顿事件 | ❌ | `am hang` / `am monitor` / Perfetto |

> **am profile 只解决"方法级 CPU 占用"**——这是稳定性工程师最常用的"谁烧了 CPU"的根因分析维度。

### 1.3 与 02/04 篇的衔接

```
02 杀进程  ─┐
03 profile ─┼─→ 04 dumpheap(杀/采/dump 三段式现场保留)
05 hang    ─┘
```

> **最佳实践**:遇到线上问题,**先 `am profile` 采一段 → 再 `am dumpheap` 抓内存 → 最后 `am kill` / `am crash` 复现**。三段式现场保留是稳定性工程师的标配。

---

## 2. am profile 完整命令族

### 2.1 命令语法总览

```
am profile [sub-command] [options]
```

| 子命令 | 作用 | 关键参数 |
|--------|------|---------|
| `am profile start <PROCESS> <FILE>` | 启动 Method Trace,采样写入 `<FILE>` | `--user <userId>`(多用户)、`-s`(sampling 模式) |
| `am profile stop <PROCESS>` | 停止采样,自动 pull `<FILE>` 到本地 | `--user <userId>` |
| `am profile dumpheap <PROCESS> <FILE>` | profile 期间触发 Java 堆 dump(辅助) | 同 04 篇 |
| `am profile list` | (隐藏)列出正在运行的 profile | - |

> **最常用**:90% 场景下只用 `start` + `stop` 两个子命令。

### 2.2 am profile start - 启动采样

**基本语法**:

```bash
am profile start <PROCESS> <FILE>
```

**参数说明**:

| 参数 | 必填 | 说明 |
|------|------|------|
| `<PROCESS>` | ✅ | 进程标识,**支持包名(com.example.app)或 PID** |
| `<FILE>` | ✅ | 设备上的 trace 输出路径,**必须是 `/data/local/tmp/` 或 `/sdcard/` 开头** |
| `--user <userId>` | ❌ | 多用户设备上指定 userId(默认 0) |
| `-s` | ❌ | 强制使用 sampling 模式(默认 Android 10+ 默认 sampling) |

**实战模板**:

```bash
# 1. 找 PID
adb shell pidof com.example.app
# 假设输出 12345

# 2. 启动 profile,采样 30s 后手动 stop
adb shell am profile start 12345 /data/local/tmp/trace.trace

# 3. 这期间操作 app 模拟场景(冷启动/滑动/进入页面)

# 4. 停止采样(下节)
adb shell am profile stop 12345
```

### 2.3 am profile stop - 停止采样并 pull 文件

**基本语法**:

```bash
am profile stop <PROCESS>
```

**行为**:

1. 通知目标进程停止采样
2. ART 把内存中的采样数据 flush 到 `<FILE>`
3. **自动把 `<FILE>` pull 到执行 adb 的主机当前目录**(注意:不会保留设备原文件)

**实战模板**:

```bash
adb shell am profile stop 12345
# 等待几秒,会自动 pull 到当前目录
ls -la trace.trace
```

**关键注意**:

- **stop 后的 trace 文件在主机当前目录**,不是设备 `/data/local/tmp/`(该路径已被清空)
- 如果 stop 失败,trace 文件可能为空或不生成——见 §6.2 坑位

### 2.4 am profile dumpheap - profile 期间的辅助 dump

**基本语法**:

```bash
am profile dumpheap <PROCESS> <FILE>
```

**作用**:在 profile 采样的同时,触发 Java 堆 dump——产出的 hprof 文件可关联到 profile 的采样时间段,**做"那段时刻谁占内存"的关联分析**。

**典型场景**:profile 发现 CPU 飙高期间,想同步看内存是谁在涨。

```bash
# 1. 启动 profile
adb shell am profile start 12345 /data/local/tmp/trace.trace

# 2. CPU 飙高时刻,同步触发堆 dump
adb shell am profile dumpheap 12345 /data/local/tmp/heap.hprof

# 3. 停止 profile
adb shell am profile stop 12345

# 4. 同时拿到 trace + hprof,做时间对齐分析
```

> 这个命令把"性能 + 内存"两个维度的现场保留串联起来,是稳定性工程师的高级用法。

### 2.5 --attach / --detach / -user 的含义

| 参数 | 含义 | 使用场景 |
|------|------|---------|
| `--user <userId>` | 指定 userId,适用于多用户设备(Work Profile、访客模式) | `adb shell am profile start --user 10 <pid> <file>` |
| `--sampling` | 显式指定 sampling 模式(默认) | Android 7.0+ 默认就是 sampling,几乎不需要手动指定 |
| `--instrumented` | 显式指定 instrumented 模式 | Android 9.0+ 支持,精度高但开销大,谨慎用 |
| `--wall-clock` / `--cpu-clock` | 时钟源选择 | 默认 `--cpu-clock`,对采样方法栈意义不大 |

**多用户实战**:

```bash
# 查看当前 userId(普通用户 0,Work Profile 10)
adb shell pm list users

# 在 Work Profile(用户 10)里 profile 某个 app
adb shell am profile start --user 10 <pid_in_work_profile> /data/local/tmp/trace.trace
```

### 2.6 完整调用栈(am → ART)

```
shell> am profile start 12345 /data/local/tmp/trace.trace
   ↓
am.jar: ActivityManagerShellCommand.runProfile()
   ↓
IBinder.transact(PROFILE_CONTROL)
   ↓
AMS: ActivityManagerService.profileControl()           [frameworks/base/services/.../am/AMS.java]
   ↓
ProcessRecord.thread.getApplicationThread()             ← 跨进程拿目标进程的 AT 引用
   ↓
IApplicationThread.profilerControl()                   ← Binder IPC 到 app 进程
   ↓
ActivityThread.profilerControl()                       [frameworks/base/core/.../ActivityThread.java]
   ↓
   ├─ START: Profile.startSampling(...) / Profile.start(...)   ← 调 ART API
   │           ↓
   │   ART: Profile::Profile() / ProfileSampler::Start()       [art/runtime/.../profile_saver.cc]
   │           ↓
   │   ART 每 N ms 采样一次线程栈,写入 mmap 的 trace buffer
   │
   └─ STOP:  Profile.writeSample(...) / Profile.stop(...)
              ↓
          ART 把 mmap buffer flush 到 <FILE>
              ↓
          am.jar 拉文件到主机
```

**关键路径索引**:

| 层 | 关键文件 |
|----|---------|
| am.jar 入口 | `frameworks/base/cmds/am/src/com/android/commands/am/Am.java` |
| AMS 接收 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`(`profileControl()`) |
| AT 跨进程 | `frameworks/base/core/java/android/app/ActivityThread.java`(`profilerControl()`) |
| ART 采样 | `art/runtime/jit/profile_saver.cc`、`art/runtime/profman/profile_assistant.cc` |
| ART API | `frameworks/base/core/java/android/os/Profile.java`(Java 层 API) |

---

## 3. ART Trace 类型深度对比

### 3.1 Sampling Trace vs Instrumented Trace

**两类 Trace 的本质差异**:

```
Sampling Trace(默认)
   ART 后台线程定期(默认 1ms / 10ms)对所有 Java 线程采栈快照
   → 低开销(2-5% CPU),看热点方法比例
   → 不精确(只看到采到的方法)

Instrumented Trace
   ART 在方法进入/退出时插入回调,记录每个方法的耗时
   → 高开销(20-50% CPU),看精确耗时
   → 完整方法栈
```

**决策矩阵**:

| 维度 | Sampling Trace(默认) | Instrumented Trace |
|------|---------------------|-------------------|
| **采样频率** | 每 1ms(高精度)或 10ms(默认) | 每个方法进入/退出 |
| **CPU 开销** | 2-5%(可线上使用) | 20-50%(严禁线上) |
| **精度** | 看"比例",不能看绝对耗时 | 看"绝对耗时" |
| **方法栈完整性** | 采到啥就记啥(可能漏) | 完整记录所有方法 |
| **适合场景** | 线上偶发卡顿、长时间采样 | 实验室定位、debug 构建 |
| **Android 版本** | 7.0+ | 9.0+ |

**采样频率怎么选**(Android 14 默认 1ms,但支持通过 ART 选项调整):

```bash
# 通过 setprop 调整采样率(需要 root 或 debuggable)
adb shell setprop dalvik.vm.profiler.sampling-interval 1   # 1ms 高精度
adb shell setprop dalvik.vm.profiler.sampling-interval 10  # 10ms 低开销(默认)
```

> **90% 场景用默认 sampling 即可**——线上性能问题不需要绝对耗时,看热点函数已经够用。

### 3.2 trace 文件格式:traceview binary vs profcollect

**两种 trace 文件格式**:

| 格式 | 后缀 | 内容 | 解析工具 |
|------|------|------|---------|
| **traceview binary** | `.trace` | ART 原始采样数据 + 方法符号表 | `traceview`(SDK tools) / Android Studio |
| **profcollect binary** | `.profcollect` / `.profile` | 简化的热点方法统计(供 ART 优化用) | `profcollect-cli` / `profman` |

**日常用哪个**:**用 `.trace` 格式**——它包含完整方法栈,可用 Studio 打开。

**trace 文件内部结构**(简化):

```
trace.trace
├── Header
│   ├── version
│   ├── start_time (ns)
│   └── pid
├── ThreadRecords[]         ← 每个线程一条
│   ├── thread_id
│   ├── thread_name
│   └── Sample[]            ← 采样点数组
│       ├── timestamp (ns)
│       ├── method_id
│       ├── method_name
│       └── stack_depth
└── MethodRecords[]         ← 方法符号表
    ├── method_id
    ├── class_name
    ├── method_name
    └── dex_file_index
```

### 3.3 性能开销矩阵

| Trace 类型 | CPU 开销 | 内存开销 | 线程栈大小限制 | 适合场景 |
|-----------|---------|---------|---------------|---------|
| **Sampling(1ms)** | 3-5% | ~10MB / 10s 采样 | 1024 帧 | 线上偶发问题 |
| **Sampling(10ms)** | 1-2% | ~5MB / 10s 采样 | 1024 帧 | 长期后台采样 |
| **Instrumented** | 20-50% | ~50MB / 10s 采样 | 完整 | 实验室精确定位 |
| **Perfetto atrace** | 5-10% | < 1MB / 10s 采样 | 256 帧 | 系统级 trace |

**关键认知**:

- **采样频率越低,CPU 开销越小,但采样越稀疏,容易漏方法**
- **Instrumented 不能上线上**——会把 5ms 的方法采成 50ms,数据失真
- **采样 trace 没有"绝对耗时",只有"被采样次数的比例"**——分析时不能用时间,要数次数

### 3.4 与 Perfetto/atrace 的取舍

| 维度 | am profile(Method Trace) | Perfetto + atrace |
|------|------------------------|------------------|
| **看什么** | Java 方法栈(进程内) | 系统调用 + Kernel 事件 + atrace 标注点 |
| **CPU 开销** | 2-5% | 5-10% |
| **方法栈深度** | 深(1024 帧) | 浅(256 帧,系统调用为主) |
| **Native 函数** | ❌ | ✅ |
| **Binder/锁/IO** | ❌(只看到调用方) | ✅(看到系统层细节) |
| **跨进程** | ❌(单进程) | ✅ |
| **解析工具** | Studio Profiler / traceview | ui.perfetto.dev |
| **典型场景** | "我的 App 哪个方法慢" | "我的 App 调系统调用卡了" |

**协同用法**:**am profile + Perfetto 同时开**——前者看 Java 层热点,后者看系统层细节,时间对齐后联合分析。

```bash
# 同时触发(用后台进程)
adb shell am profile start 12345 /data/local/tmp/trace.trace &
adb shell perfetto -o /data/local/tmp/trace.perfetto -t 30s sched freq idle am binder_driver &
sleep 30

# 同时 stop
adb shell am profile stop 12345
adb shell perfetto --stop
```

### 3.5 与 SimplePerf 的取舍

| 维度 | am profile | SimplePerf |
|------|-----------|-----------|
| **看什么** | Java 方法 | Native 函数 + Java 函数(符号化后) |
| **采样原理** | ART 内部采样 | perf_event_open(Linux 内核采样) |
| **Native 库** | ❌ | ✅ |
| **符号化** | 自动(ART 持有 dex 符号) | 需要 `simpleperf report --symfs` |
| **CPU 开销** | 2-5% | 1-3% |
| **典型场景** | "Java 层哪个 Activity / Fragment 慢" | "我的 so 库哪个 native 函数慢" |

**协同用法**:

```bash
# am profile 定位到某个 Java 方法是热点
adb shell am profile start 12345 /data/local/tmp/trace.trace
# 假设发现 com.example.MyNativeBridge.nativeCall() 占比 30%

# 用 simpleperf 进一步定位 native 层
adb shell simpleperf record -p 12345 -o /data/local/tmp/perf.data --duration 10
# pull 后用 simpleperf report 打开
```

---

## 4. 5 分钟跑通的端到端流程

### 4.1 启动 profile + 执行场景 + 停止 profile

**完整 5 分钟流程**:

```bash
# ===== 步骤 1:找 PID(15 秒)=====
adb shell pidof com.example.app
# 假设输出:12345
PID=12345

# ===== 步骤 2:启动 profile(5 秒)=====
adb shell am profile start $PID /data/local/tmp/trace.trace
# 输出:Profiling started, file=/data/local/tmp/trace.trace
PROFILE_TIME=$(date +%s)

# ===== 步骤 3:执行你要分析的场景(30-120 秒)=====
# 比如:打开 app → 进入主页 → 滑动列表 → 退出
# 这里手动操作,或者用 monkey 触发
adb shell input keyevent KEYCODE_HOME
adb shell am start -n com.example.app/.MainActivity
sleep 5
adb shell input swipe 500 1000 500 200 500
sleep 3

# ===== 步骤 4:停止 profile(10 秒)=====
adb shell am profile stop $PID
# 几秒后,trace.trace 会被自动 pull 到主机当前目录

# ===== 步骤 5:确认文件(5 秒)=====
ls -la trace.trace
# 大小应该在 1-50MB(看采样时长和方法数)
```

### 4.2 pull trace 文件

**自动 pull(默认行为)**:

`am profile stop` 执行后,**adb 会自动把设备上的 `/data/local/tmp/trace.trace` 拉到主机**——但有几个关键注意:

1. **路径是"当前目录"**——执行 adb 的目录(`pwd` 那条)
2. **文件名不变**——设备上是 `trace.trace`,主机上也是 `trace.trace`
3. **如果当前目录没写权限,文件丢失**——建议先 `cd` 到确定可写的目录

**手动 pull(备份)**:

```bash
# 如果自动 pull 没成功,可以手动再拉一次
adb pull /data/local/tmp/trace.trace ./trace_$(date +%Y%m%d_%H%M%S).trace
```

**多个 trace 归档**(自动化场景必备):

```bash
TRACE_DIR=./traces/$(date +%Y%m%d_%H%M%S)
mkdir -p $TRACE_DIR
adb pull /data/local/tmp/trace.trace $TRACE_DIR/
```

### 4.3 解析工具链速查

| 工具 | 用途 | 适用对象 | 安装 |
|------|------|---------|------|
| **traceview** | 命令行解析 trace,生成调用树 | `.trace` | Android SDK `tools/traceview` |
| **Android Studio Profiler** | GUI 看方法栈热点 | `.trace` | Studio Hedgehog+ |
| **simpleperf** | Native 函数 CPU 采样 | `.perf.data` | `adb shell simpleperf` |
| **Perfetto UI** | 系统级 trace 可视化 | `.perfetto` | https://ui.perfetto.dev |
| **profcollect-cli** | ART profile 文件分析 | `.profcollect` | AOSP `art/cmdline/profcollect` |

**traceview 命令行用法**:

```bash
# SDK tools 路径(需要 ANDROID_HOME 或 SDK_ROOT)
traceview trace.trace
# 输出 Top N 方法 + 调用树
```

**Studio Profiler 看 trace**:

1. Studio → Profiler → 左上角 `+` → Profileable APK(选你的 app)
2. 启动后 `Profiler` → CPU → 顶栏 `Sampled (Java/Kotlin Method Trace)`
3. 加载 trace 文件:`Profiler` → `...` → `Load from file`

### 4.4 traceview / studio 打开 trace

**traceview 实战命令**:

```bash
# 标准调用
traceview trace.trace

# 只看 top 20 方法
traceview --limit 20 trace.trace

# 输出到 HTML(便于分享)
traceview --html trace.trace > trace_report.html
```

**Studio 看 trace 的 3 个关键视图**:

| 视图 | 看什么 | 典型用途 |
|------|-------|---------|
| **Top Down** | 从 main 往下的调用树 | "main → onCreate → initView 占比 30%" |
| **Bottom Up** | 从叶子往上的反向树 | "BitmapFactory.decodeStream 被哪些方法调用最多" |
| **Flame Chart** | 按时间维度的火焰图 | "冷启动 1.5s 中 initView 占 800ms" |

### 4.5 完整流程的"时间对齐"问题

**坑位预警**:trace 文件的"时间戳"是 **device uptime**,不是 Unix 时间戳。如果同时开 Perfetto/ANR,要做时间对齐:

```bash
# adb shell date 是设备 Unix 时间
adb shell date +%s.%N

# am profile start 的时间转成 uptime
# uptime = unix_time - boot_time
adb shell cat /proc/uptime
# 第一个数字是 uptime(秒)
```

> **做"profile + ANR + dumpheap"三段联动时,一定要先记下 `adb shell date +%s.%N` 作为基准时间**。

---

## 5. 进阶用法

### 5.1 后台守护 profile(适用于长周期采样)

**场景**:压测期间要持续采样 10 分钟,但 shell 终端会断。

```bash
# 在目标设备后台启动 profile
adb shell "am profile start $PID /data/local/tmp/long_trace.trace &"
# ↑ & 让 am 命令在后台跑,即使 adb shell 退出也不影响

# 10 分钟后手动 stop
adb shell am profile stop $PID
```

**关键**:am profile 命令**自带保活机制**——它在目标进程内 fork 一个采样线程,不依赖 am 命令本身。

### 5.2 多进程 profile(选 PID 而不是包名)

**场景**:app 有 3 个进程(:main, :push, :web),要分别采样。

```bash
# 列出所有 PID
adb shell pidof com.example.app
adb shell ps -A | grep com.example.app
# 12345  com.example.app (main)
# 12346  com.example.app:push
# 12347  com.example.app:web

# 分别采样
adb shell am profile start 12345 /data/local/tmp/trace_main.trace
adb shell am profile start 12346 /data/local/tmp/trace_push.trace
adb shell am profile start 12347 /data/local/tmp/trace_web.trace

# 注意:不能同时对同一进程 start 多次,会覆盖
# 同一时刻,一个进程只能有一个 profile 在跑
```

**坑位预警**:**Android 9.0+ 同时只能有一个 profile session per process**——见 §6.5。

### 5.3 profile 与 dumpheap 串联(性能问题现场保留)

**三段式现场保留的标准动作**:

```bash
# 1. 启动 profile(开始采样 CPU 热点)
adb shell am profile start $PID /data/local/tmp/trace.trace

# 2. 执行要分析的场景(冷启动 / 滑动 / 页面进入)

# 3. 在关键时刻 dump heap(同步拿内存现场)
adb shell am dumpheap $PID /data/local/tmp/heap.hprof

# 4. 停止 profile(自动 pull trace)
adb shell am profile stop $PID

# 5. 手动 pull heap(am dumpheap 不会自动 pull)
adb pull /data/local/tmp/heap.hprof ./

# 6. 现在同时拿到 trace + heap,做关联分析
```

**关键时间点**:

| 时刻 | 动作 | 产出 |
|------|------|------|
| T0 | profile start | 开始采样 |
| T1 (场景启动) | 场景开始 | - |
| T2 (CPU 飙升) | dumpheap | 拿到 CPU 飙升时刻的内存快照 |
| T3 | profile stop | trace 文件自动 pull |
| T4 | pull heap.hprof | 内存文件归档 |

### 5.4 profile 与 hang 串联(ANR 期间采 trace)

**场景**:线上偶发 ANR,想看 ANR 发生时的方法栈。

```bash
# 1. 启动 profile(长周期采样,10 分钟)
adb shell am profile start $PID /data/local/tmp/long_trace.trace

# 2. 触发 ANR
adb shell am hang $PID

# 3. 等待 ANR 发生(默认 6s)
sleep 8

# 4. 停止 profile,自动 pull trace
adb shell am profile stop $PID

# 5. 用 Studio 打开 trace,定位 ANR 期间哪个方法占用栈帧最多
```

> **关键**:trace 文件里的"时间戳"和 ANR 的 traces.txt 时间戳要做对齐——`adb shell date +%s.%N` 记一下基准。

### 5.5 自动化嵌入(在压测脚本中)

**典型用法**:压测工具跑 30 分钟,每 5 分钟采一段 trace,自动归档。

```bash
# 伪代码
PID=$(adb shell pidof com.example.app)
for i in 1 2 3 4 5 6; do
    adb shell am profile start $PID /data/local/tmp/trace_$i.trace
    sleep 240   # 采 4 分钟
    adb shell am profile stop $PID
    mv trace_$i.trace ./traces/  # 归档
done
```

**完整脚本见 `scripts/profile_trace_capture.sh`**——支持自动归档 + 元信息记录(场景描述、时间戳、设备型号、Android 版本)。

---

## 6. 关键坑位图

### 6.1 am profile stop 后文件没自动 pull

**症状**:`am profile stop` 执行后,当前目录没有 `trace.trace` 文件。

**根因**:

1. 执行 adb 的当前目录无写权限(常见:`/root/` 或 CI runner 临时目录)
2. trace 文件太大,adb pull 失败(> 2GB)
3. 设备 storage 满,trace 写入失败

**解决**:

```bash
# 方案 1:明确指定 pull 目录
cd /tmp && adb shell am profile stop $PID

# 方案 2:手动 pull
adb pull /data/local/tmp/trace.trace ./

# 方案 3:加 -a(归档)参数确保权限
adb pull -a /data/local/tmp/trace.trace ./
```

### 6.2 trace 文件是空文件(没采到采样)

**症状**:`trace.trace` 只有几 KB,打开 Studio 是空白。

**根因**:

1. **采样时间太短**(< 1s):ART 没来得及采到有效数据
2. **进程已死**:`start` 后目标进程立刻被 `am kill` / OOM,采样线程没启动
3. **profile start 路径不在 `/data/local/tmp/`**——Android 14 SELinux 限制
4. **app 没启用 JIT**(debuggable=false 且未优化):ART 关闭了采样

**解决**:

```bash
# 方案 1:加长采样时间(至少 5s)
sleep 5

# 方案 2:确认路径
adb shell am profile start $PID /data/local/tmp/trace.trace  # ✅
adb shell am profile start $PID /sdcard/trace.trace         # ❌ SELinux 拒绝

# 方案 3:确认 app 可调试
adb shell dumpsys package com.example.app | grep debuggable
# flags 应包含 DEBUGGABLE

# 方案 4:确认进程存活
adb shell pidof com.example.app  # 执行 start 后立即确认
```

### 6.3 采样导致 app 卡顿,反而影响线上

**症状**:profile start 后 app 明显变慢,采样本身影响了被分析的场景。

**根因**:**采样频率设太高**(`sampling-interval 1`)或**采样线程与主线程抢 CPU**。

**解决**:

```bash
# 方案 1:降低采样率(默认 10ms 已经够用)
adb shell setprop dalvik.vm.profiler.sampling-interval 10

# 方案 2:缩短采样时长(5 分钟足够看热点)
sleep 300 && adb shell am profile stop $PID

# 方案 3:不在主线程敏感时段采样(如冷启动期间)
# 冷启动期间 ART 已经在做大量 JIT/编译,采样会显著影响启动时间
```

> **金标准**:线上 profile 开销控制在 **CPU +3% 以内**,内存 +10MB 以内。

### 6.4 trace 文件太大,Studio 打不开

**症状**:`trace.trace` 超过 500MB,Studio 加载卡死。

**根因**:

1. **采样时间太长**(> 10 分钟)
2. **采样频率太高**(1ms)
3. **app 方法数爆炸**(> 50 万方法,常见于大型 app + 多 dex)

**解决**:

```bash
# 方案 1:缩短采样时长
sleep 60   # 1 分钟足够

# 方案 2:降低采样率
adb shell setprop dalvik.vm.profiler.sampling-interval 10

# 方案 3:用 traceview 命令行(Studio 之外的方案)
traceview --limit 100 trace.trace > top100.txt

# 方案 4:压缩归档
gzip trace.trace   # 通常压缩到原大小 10-20%
```

### 6.5 多个 profile 并发,文件覆盖

**症状**:对同一进程连续两次 `am profile start`,文件被覆盖。

**根因**:**Android 9.0+ ART 限制**:一个进程同时只能跑一个 profile session。

**解决**:

```bash
# 方案 1:先 stop 再 start(确保只有一个 session)
adb shell am profile start $PID /data/local/tmp/t1.trace
sleep 30
adb shell am profile stop $PID
adb shell am profile start $PID /data/local/tmp/t2.trace

# 方案 2:不同进程并发(主进程 + push 进程)
adb shell am profile start 12345 /data/local/tmp/t1.trace
adb shell am profile start 12346 /data/local/tmp/t2.trace  # ✅ 不同 PID 没问题
```

### 6.6 profile 与 dumpheap 顺序错误导致 heap 无 profile 上下文

**症状**:做了 profile + dumpheap 联动,但打开 heap 时找不到对应的 trace 时间点。

**根因**:**顺序反了**——先 dumpheap 再 profile,heap 快照时 profile 还没开始采样,没有 CPU 上下文关联。

**解决**:

```bash
# ✅ 正确顺序:先 profile start,场景中 dumpheap,最后 profile stop
adb shell am profile start $PID /data/local/tmp/trace.trace
sleep 5  # 场景触发
adb shell am dumpheap $PID /data/local/tmp/heap.hprof  # 此时 profile 正在采
adb shell am profile stop $PID

# ❌ 错误顺序:先 dumpheap 再 profile
# heap 抓的是 profile 还没启动时的内存,无 CPU 上下文
```

---

## 7. 案例库:3 个真实场景

### 7.1 案例 1:定位冷启动慢的根因函数

**现象**:某 App 冷启动从 800ms 劣化到 1.5s,需要定位根因函数。

**分析步骤**:

```bash
# 1. 找 PID(冷启动前 app 不在,先启动)
adb shell am start -W -n com.example.app/.MainActivity
# WaitTime: 1500ms ← 劣化值
PID=$(adb shell pidof com.example.app)

# 2. 启动 profile
adb shell am profile start $PID /data/local/tmp/cold_start.trace
sleep 8   # 等冷启动结束

# 3. 停止 profile,自动 pull
adb shell am profile stop $PID

# 4. 打开 Studio Profiler,看 Top Down 调用树
# Studio → Profiler → Load trace → Top Down
```

**关键发现**(典型 trace):

```
main (100%)
└─ ActivityThread.handleLaunchActivity (98%)
   └─ MainActivity.onCreate (95%)
      └─ initView() (60%)            ← 根因!
         └─ BitmapFactory.decodeResource() (45%)
            └─ nativeDecode() (40%)
```

**根因**:`initView()` 在 onCreate 里同步加载了 5 张大图 Bitmap,**没有异步 / 懒加载**。

**修复**:

```java
// ❌ 修复前:onCreate 里同步加载
@Override
protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.activity_main);
    initView();  // 加载 5 张 Bitmap
}

// ✅ 修复后:懒加载 + 后台线程
@Override
protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.activity_main);
}

@Override
protected void onResume() {
    super.onResume();
    new AsyncTask<Void, Void, Bitmap>() {
        @Override
        protected Bitmap doInBackground(Void... voids) {
            return BitmapFactory.decodeResource(getResources(), R.drawable.bg);
        }
        @Override
        protected void onPostExecute(Bitmap b) {
            imageView.setImageBitmap(b);
        }
    }.execute();
}
```

**修复后验证**:

```bash
adb shell am start -W -n com.example.app/.MainActivity
# WaitTime: 850ms ← 恢复
```

### 7.2 案例 2:压测期间捕获 CPU 热点函数

**现象**:App 压测 30 分钟,期间 CPU 从 30% 飙到 80%,需要定位是哪个方法。

**分析步骤**:

```bash
# 1. 压测启动(用 monkey 模拟用户操作)
adb shell monkey -p com.example.app --pct-touch 50 --pct-syskeys 0 \
    --throttle 200 -v 1000 &
MONKEY_PID=$!

# 2. 启动 profile 采样 60 秒
PID=$(adb shell pidof com.example.app)
adb shell am profile start $PID /data/local/tmp/stress_60s.trace
sleep 60

# 3. 停止 profile
adb shell am profile stop $PID
kill $MONKEY_PID  # 同时停 monkey

# 4. Studio Profiler → Bottom Up 视图
# 找被采样次数最多的方法
```

**关键发现**(典型 trace):

```
Bottom Up (按采样次数倒序):
1. MessageQueue.nativePollOnce() - 38%   ← 主线程在等消息(正常)
2. BitmapFactory.decodeStream() - 18%   ← 列表项里 decode Bitmap
3. JSON.parse() - 12%                  ← 大 JSON 解析
4. SQLiteDatabase.query() - 8%         ← DB 查询
5. SystemClock.sleep() - 5%            ← 故意 sleep?
```

**根因**:**列表项里同步 decode 大图**(典型场景:RecyclerView onBindViewHolder 里直接 decode),导致列表滑动时 CPU 飙高。

**修复**:

```java
// ❌ 修复前:onBindViewHolder 同步 decode
@Override
public void onBindViewHolder(ViewHolder holder, int position) {
    Bitmap bmp = BitmapFactory.decodeFile(item.imagePath);
    holder.imageView.setImageBitmap(bmp);
}

// ✅ 修复后:异步加载 + 缓存
@Override
public void onBindViewHolder(ViewHolder holder, int position) {
    ImageLoader.load(holder.imageView, item.imageUrl);
}
```

### 7.3 案例 3:线上偶发卡顿的 profile+ANR 联动

**现象**:线上收到 ANR 报告(`am hang` 自动触发),想看 ANR 期间方法栈。

**分析步骤**:

```bash
# 1. 启动长周期 profile
PID=$(adb shell pidof com.example.app)
adb shell am profile start $PID /data/local/tmp/long_trace.trace

# 2. 记下基准时间
echo "Profile start time: $(adb shell date +%s.%N)"

# 3. 触发 ANR
adb shell am hang $PID --allow-restart

# 4. 等 ANR 发生
sleep 8

# 5. ANR 现场采集(dumpsys / traces.txt)
adb pull /data/anr/anr_*.txt ./anr_traces.txt

# 6. 停止 profile
adb shell am profile stop $PID

# 7. 时间对齐:trace 文件里找 ANR 时间附近的方法栈
```

**关键发现**:

- traces.txt 里有 ANR 时刻的"主线程栈"(系统层捕获的 5 秒栈帧)
- trace 文件里有"ANR 前后 30 秒"的所有方法采样
- **两者时间对齐后,可以回答:ANR 之前主线程在干什么?**(trace 给答案)

**根因分析模板**:

| 维度 | 数据源 |
|------|--------|
| ANR 时刻主线程栈 | `/data/anr/anr_*.txt`(traces.txt) |
| ANR 前后 30s 方法热点 | `trace.trace`(am profile 产出) |
| ANR 时刻内存状态 | `am dumpheap` 产出(联动) |
| ANR 时刻锁竞争 | `simpleperf` / systrace |

---

## 8. 总结:架构师视角的 5 条 Takeaway

1. **`am profile` 是稳定性的"性能采样触发器"**——它不开 GUI、不改代码、不依赖 Studio,**任何 debuggable 设备都能跑**。线上场景首选。

2. **默认 Sampling Trace,慎用 Instrumented**——Sampling 2-5% 开销可上线上,Instrumented 20-50% 开销只适合实验室。线上性能问题不需要"绝对耗时",看"方法被采样次数比例"就够。

3. **profile + dumpheap + hang 是三段式现场保留的标配**——遇到问题**先 profile start → 场景中 dumpheap → profile stop**,同时拿到 CPU 热点和内存现场,做关联分析。顺序错了 heap 无 profile 上下文。

4. **和 Perfetto/SimplePerf 是互补,不是替代**——am profile 看 Java 方法栈,Perfetto 看系统调用,SimplePerf 看 Native 函数。**同时开三段做时间对齐**,才是完整的性能分析。

5. **5 个经典坑位提前规避**——文件没自动 pull(明确执行目录)、trace 是空文件(路径要在 `/data/local/tmp/`、进程要存活)、采样让 app 更卡(降低采样率到 10ms)、trace 太大 Studio 打不开(限制采样时长到 1 分钟内)、并发 profile 同进程覆盖(先 stop 再 start)。

---

## 附录 A:核心源码路径索引

| 层 | 文件路径 |
|----|---------|
| am.jar profile 入口 | `frameworks/base/cmds/am/src/com/android/commands/am/Am.java`(`runProfile()`) |
| AMS profileControl | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`(`profileControl()`) |
| AT profilerControl | `frameworks/base/core/java/android/app/ActivityThread.java`(`profilerControl()`) |
| ART Sampling 实现 | `art/runtime/jit/profile_saver.cc`、`art/runtime/jit/profile_collection.cc` |
| ART Profile API | `frameworks/base/core/java/android/os/Profile.java`(Java 层 API) |
| profman 工具 | `art/cmdline/profman/`(profile 文件分析) |
| traceview 工具 | `tools/traceview/`(SDK tools) |
| 简单测试入口 | `frameworks/base/cmds/am/tests/src/com/android/commands/am/tests/AmProfileTest.java` |

---

## 附录 B:Trace 工具矩阵

| 工具 | 适用场景 | 看什么 | 开销 | 解析器 |
|------|---------|--------|------|--------|
| **am profile** | Java 方法栈热点 | 被采样方法的比例 | 2-5% CPU | Studio / traceview |
| **Perfetto + atrace** | 系统调用 + Kernel 事件 | sched / freq / Binder / Lock | 5-10% CPU | ui.perfetto.dev |
| **SimplePerf** | Native 函数 CPU 占用 | so 库内的 native 函数 | 1-3% CPU | simpleperf report |
| **dumpsys cpuinfo** | 进程 CPU 占用趋势 | 进程级别的 CPU% | < 1% | dumpsys 命令 |
| **dumpsys gfxinfo** | 渲染帧耗时 | Choreographer / doFrame | < 1% | dumpsys 命令 |
| **Studio Profiler** | GUI 全功能分析 | 上述所有 | 高 | Studio 内置 |

---

## 附录 C:am profile 参数矩阵

| 参数 | Android 版本 | 含义 |
|------|------------|------|
| `start <proc> <file>` | 7.0+ | 启动 sampling trace |
| `stop <proc>` | 7.0+ | 停止并 pull 文件 |
| `dumpheap <proc> <file>` | 7.0+ | profile 期间触发堆 dump |
| `--user <userId>` | 7.0+ | 多用户设备指定 userId |
| `--sampling` | 7.0+ | 显式 sampling(默认) |
| `--instrumented` | 9.0+ | 显式 instrumented(慎用) |
| `--wall-clock` | 7.0+ | 时钟源(几乎不用) |

---

## 附录 D:工程资产清单

| 资产 | 路径 | 作用 |
|------|------|------|
| `profile_trace_capture.sh` | `scripts/` | profile + 自动归档脚本(Linux/Mac) |
| `profile_trace_capture.ps1` | `scripts/` | profile + 自动归档脚本(Windows) |
| `am_profile_params.md` | `am_command_configs/` | profile 参数速查表 |

---

## 附录 E:工程基线表

| 项 | 版本/路径 |
|----|---------|
| am profile API | AOSP `frameworks/base/cmds/am` |
| ART Profile 实现 | AOSP `art/runtime/jit/profile_saver.cc` |
| 默认采样率 | Android 14: 1ms(`dalvik.vm.profiler.sampling-interval`) |
| 解析工具 | `traceview`(SDK tools)、Android Studio Profiler |
| 典型 trace 大小 | 1-50MB / 60s 采样(取决于方法数) |
| 兼容性 | Android 7.0+(Nougat)以上,所有采样 API |

---

## 篇尾衔接

**本篇回答的问题**:

- `am profile` 怎么用?(§2)
- Sampling 和 Instrumented 怎么选?(§3.1)
- 5 分钟跑通的端到端流程?(§4)
- 怎么和 dumpheap / hang / Perfetto 串联?(§5)

**留给下一篇的问题**:

- `am dumpheap` 怎么用?和 profile 怎么联动?(→ [04 dumpheap 详解](04-堆内存转储-dumpheap详解.md))

**留给其他系列的问题**:

- Perfetto atrace 内部原理(→ Perfetto 系列)
- SimplePerf 全功能(→ Tools 系列)
- am 命令怎么工程化、串成自动化巡检脚本(→ [06 自动化实战](06-自动化实战-脚本与CI集成.md))

---

---