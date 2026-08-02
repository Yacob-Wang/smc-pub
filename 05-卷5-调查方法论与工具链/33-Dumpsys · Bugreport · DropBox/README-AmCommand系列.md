# AmCommand 系列:Android 稳定性工程师的"瑞士军刀"

> **目录**:`Android_Framework/AmCommand/`
>
> **基线**:AOSP `android-14.0.0_r1` + Android Studio Hedgehog + adb `platform-tools 34+`

---

## 0. 阅读入口

| 角色 | 你应该读什么 |
|------|------------|
| **5 分钟速览 am 命令** | 只读 [01 §1-§3](01-am命令全景与Activity触发.md) |
| **想触发/模拟一次进程崩溃** | [02 进程管理三件套](02-进程管理三件套-kill-crash-restart.md) 全文 |
| **要做性能采样(Method Trace / Sampling Trace)** | [03 profile 命令](03-性能分析入口-profile命令.md) 全文 |
| **要 dump 进程堆内存** | [04 dumpheap 详解](04-堆内存转储-dumpheap详解.md) 全文 |
| **要在桌面触发 ANR / 监控异常** | [05 诊断与监控](05-诊断与监控-hang-monitor.md) 全文 |
| **要把 am 命令集成到 CI / 自动化巡检** | [06 自动化实战](06-自动化实战-脚本与CI集成.md) 全文 |

---

## 1. 为什么要写 am 命令系列

### 1.1 它在稳定性领域的"万能触发器"地位

`am` (Activity Manager) 是 Android `am.jar` 提供的命令行工具,本质是 `ActivityManagerService` (AMS) 的**对外触发入口**。对稳定性工程师而言,它的价值和 hprof / Perfetto / dumpsys 互补:

| 工具 | 触发能力 | 看的维度 | 解决的问题 |
|------|---------|---------|-----------|
| **am** | 触发(Activity/Service/Broadcast/进程死亡/堆 dump) | **控制维度**(让系统做某事) | 模拟用户行为、压测、自动化 |
| **dumpsys** | 无(只读) | 系统状态维度 | Service/Activity/Battery 当前快照 |
| **hprof** | 无(只读) | 空间维度(谁占用内存) | OOM、内存泄漏、Bitmap 暴涨 |
| **Perfetto trace** | 无(只读) | 时间维度 | 卡顿、ANR、启动慢、IO 劣化 |
| **monkey** | 触发(随机) | 控制维度(随机事件流) | 稳定性压测、Crash 复现 |

> **am 决定了你能"做"什么**——和 hprof(看)/ Perfetto(看) 是不同的"做"。

### 1.2 现有教程的两大盲区

| 现有内容 | 盲区 | 本系列的填补 |
|---------|------|------------|
| `am start-activity` 教程 | 只讲启动页面,不讲 AMS 内部触发链路 | [01 §3] 给出 `am → AMS → AT` 的完整调用栈 |
| 散落的 `am dumpheap` 介绍 | 缺版本差异、自动化脚本、坑位 | [04 全文] 给 Android 11/12/14 行为差异 + 5 分钟跑通的脚本 |
| 性能 Profiler 文档 | 讲 Android Studio GUI,不讲命令行触发 | [03 全文] 讲 `am profile` 怎么用、怎么拉 trace 文件 |

### 1.3 对稳定性工程师的核心价值

读完后你能做到的事:
1. **5 分钟内**用 `am` 触发任意 Activity/Service/Broadcast 并带参数
2. 主动模拟一次进程死亡 / 进程 Crash 并保留现场
3. 用 `am profile` 启动/停止 Method Trace,产出可分析 trace 文件
4. 用 `am dumpheap` 触发指定进程的 Java 堆 dump,理解 ART 内部行为
5. 用 `am hang` / `am monitor` 触发 ANR 和监控 GC/Crash
6. 把 am 命令集成为 shell / Python 脚本,做自动巡检和 CI 集成

---

## 2. 系列设计思路

### 2.1 架构师思维链(从触发到自动化)

```
am 命令是什么?AMS 内部怎么接收?(基础原理)
    ↓
am 能触发哪些"系统级事件"?(命令矩阵)
    ↓
模拟进程死亡/崩溃怎么用?(进程管理)
    ↓
采样性能/转储内存怎么用?(性能 & 内存)
    ↓
触发 ANR/监控异常怎么用?(诊断监控)
    ↓
怎么把上面这些做成自动化脚本?(工程实战)
```

### 2.2 六篇的递进关系

```
        01 全景与 Activity 触发(入口)
              ↓
    ┌─────────┼─────────┐
    ↓         ↓         ↓
  02 进程   03 性能   04 内存
  kill/    profile   dumpheap
  crash              (← 本篇核心)
    ↓         ↓         ↓
    └─────────┼─────────┘
              ↓
          05 诊断监控(hang/monitor)
              ↓
          06 自动化实战(脚本/CI)
```

- **01**:全系列入口,讲透 am 命令本质 + 触发 Activity(最高频场景)
- **02-04**:按"对什么操作"的三大维度分篇——杀进程、采性能、dump 内存
- **05**:补齐"主动触发 ANR / 监控异常"两类诊断场景
- **06**:把上面所有能力升级为工程化脚本,串成可复用的工具集

### 2.3 源码密度控制(参考 Hprof 系列)

| 维度 | Hprof 系列 5 篇 | AmCommand 系列(本系列)|
|------|--------------|------------------|
| 源码占比 | 15-20% | **~10-15%**(以命令矩阵和决策树为主) |
| 单篇平均行数 | 600-700 | **500-700** |
| 重点 | 格式图 + 决策树 | **命令矩阵 + 决策树 + 实战脚本** |
| 实战案例 | 2-3 个/篇 | **2-3 个/篇** |
| 工程资产 | 6+ 个 | **6+ 个** |

---

## 3. 篇目速览

### 篇 01:am 命令全景与 Activity 触发
**角色**:全局观
**核心问题**:am 命令本质是什么?AMS 怎么接收?`am start-activity` 怎么用?
**关键产出**:
- am 命令的本质:`ActivityManagerShellCommand` + `IBinder` 跨进程序列化
- AMS 接收 → ApplicationThread 跨进程转发的完整调用栈
- `am start-activity` 的 5 大参数(action / category / data / extras / flags)
- Activity 启动的 4 种 flag(Intent.FLAG_ACTIVITY_*)实战
- 启动延迟(冷启动/热启动)统计命令
- **工程资产**:`am start` 参数模板(activity 启动矩阵)

### 篇 02:进程管理三件套 - kill / crash / restart
**角色**:稳定性触发
**核心问题**:怎么模拟一次进程死亡?怎么让 app 主动 crash?怎么强制重启?
**关键产出**:
- `am kill <pkg>` vs `am kill-all` vs `am force-stop` 三者差异
- `am crash` 的本质:跨进程调用 `IApplicationThread.scheduleCrash()`,生成 native crash
- `am restart` 的使用场景
- 模拟 LMKD 杀进程(配合 `am send-trim-memory`)
- 进程死亡现场保留:`tombstone` / `dropbox` / `anr` 三大位置
- **工程资产**:进程死亡模拟脚本(自动拉 logcat + dropbox)

### 篇 03:性能分析入口 - profile 命令
**角色**:性能触发
**核心问题**:`am profile` 怎么用?和 Android Studio Profiler 的关系?
**关键产出**:
- `am profile start <proc> <file>` 启动 Method Trace
- `am profile stop <proc>` 停止 + 自动 pull trace 文件
- ART Sampling Trace 和 Instrumented Trace 的差异
- trace 文件解析(用 `profcollect` / `simpleperf`)
- 自动化:在压测脚本中嵌入 `am profile` 片段
- **工程资产**:`am profile` 自动化采集脚本

### 篇 04:堆内存转储 - dumpheap 详解 ⬅️
**角色**:内存触发
**核心问题**:`am dumpheap` 怎么用?为什么产出的 hprof 还需要 hprof-conv 转换?线上怎么自动化?
**关键产出**:
- `am dumpheap` 的完整调用栈:`am → AMS.dumpHeap() → ApplicationThread.dumpHeap() → Debug.dumpHprofData() → ART`
- Android 11/12/14 行为差异(权限、路径、man pages)
- 关键参数:`-n <userId>`、`-a` 的含义
- dump 期间的 app 卡顿(Stop-The-World 5-30s)
- 自动化脚本:触发 dump + pull 文件 + hprof-conv 转换 + MAT 解析
- 与 hprof 系列 01 篇的呼应(同一条路径,不同入口)
- **工程资产**:`dumpheap_and_analyze.sh` 5 分钟跑通的端到端脚本

### 篇 05:诊断与监控 - hang / monitor
**角色**:诊断触发
**核心问题**:怎么主动触发一次 ANR?怎么监控进程的 GC / Crash 事件?
**关键产出**:
- `am hang` 触发 ANR:让目标进程的 main thread sleep
- `am hang --allow-restart` 的使用场景
- `am monitor`:实时监控 GC 事件、Crash、LowMemory
- `am monitor --gdb` 进入 native 调试
- 与 `dumpsys gfxinfo` / `dumpsys meminfo` 的协同
- **工程资产**:`am monitor` 实时监控脚本

### 篇 06:自动化实战 - 脚本与 CI 集成
**角色**:工程体系
**核心问题**:怎么把 am 命令做成可复用的稳定性工具?怎么集成到 CI?
**关键产出**:
- adb 工具链封装(幂等的 adb push / pull / shell)
- am 命令的 Python 封装(`amlib` mini SDK)
- 典型自动化场景:
  - 冷启动性能巡检(am start + am profile + 解析)
  - 内存压力测试(am dumpheap 定时采集)
  - 进程稳定性巡检(am crash 模拟 + tombstone 拉取)
- CI 集成:GitHub Actions / GitLab CI 的 adb runner
- **工程资产**:`amlib.py`(Python SDK)+ 3 个巡检脚本

---

## 4. 工程资产清单

```
AmCommand/
├── README-AmCommand系列.md                  (本文件)
├── 01-am命令全景与Activity触发.md
├── 02-进程管理三件套-kill-crash-restart.md
├── 03-性能分析入口-profile命令.md          (← 第三批新增)
├── 04-堆内存转储-dumpheap详解.md           (← 第一批重点)
├── 05-诊断与监控-hang-monitor.md
├── 06-自动化实战-脚本与CI集成.md           (← 第三批新增·系列收官)
├── am_command_configs/
│   ├── am_start_params.md                  am start 参数速查表
│   ├── am_dumpheap_workflow.yaml           dumpheap 工作流配置
│   ├── am_profile_params.md                am profile 参数速查表(第三批新增)
│   └── am_command_matrix.md                am 全命令速查矩阵
└── scripts/
    ├── amlib/                              amlib Python SDK(第三批核心)
    │   ├── __init__.py
    │   ├── device.py                       设备管理(自动重连/超时)
    │   ├── am.py                           am 命令封装(覆盖 5 篇所有命令)
    │   ├── artifact.py                     现场保留(三段式归档)
    │   ├── report.py                       报告生成(Markdown)
    │   ├── exceptions.py                   自定义异常
    │   └── utils.py                        adb 命令封装 + 工具函数
    ├── check_cold_start.py                 冷启动巡检脚本(第三批)
    ├── check_memory_pressure.py            内存压力巡检脚本(第三批)
    ├── check_process_stability.py          进程稳定性巡检脚本(第三批)
    ├── requirements.txt                    amlib 依赖清单
    ├── ci/
    │   ├── github_actions_stability.yml    GitHub Actions 模板(第三批)
    │   └── gitlab_ci_stability.yml         GitLab CI 模板(第三批)
    ├── dumpheap_and_analyze.sh             dumpheap 端到端脚本(Linux/Mac)
    ├── dumpheap_and_analyze.ps1            dumpheap 端到端脚本(Windows)
    ├── profile_trace_capture.sh            profile 自动归档(Linux/Mac·第三批)
    ├── profile_trace_capture.ps1           profile 自动归档(Windows·第三批)
    ├── process_crash_capture.sh            进程死亡现场捕获
    ├── process_crash_capture.ps1           进程死亡现场捕获 Windows
    ├── monitor_logcat.sh                   am monitor 脚本化
    └── monitor_logcat.ps1                  am monitor 脚本化 Windows
```

---

## 5. 与其他系列的关系

| 系列 | 关系 |
|------|------|
| **Hprof 系列** | **04 dumpheap 详解** 是 Hprof 系列的"触发入口篇"——hprof 讲"看",am dumpheap 讲"做" |
| **Dumpsys 系列** | 05 篇会联动 `dumpsys meminfo` / `dumpsys gfxinfo` 做诊断 |
| **Perfetto 系列** | 03 篇会讲 `am profile` 与 Perfetto atrace 的取舍 |
| **Process 系列** | 02 篇会引用 OOM Adj / LMKD 机制(模拟杀进程) |
| **ANR_Detection 系列** | 05 篇会讲 `am hang` 触发的 ANR 现场采集 |
| **Tools 系列** | 06 篇的 adb / Python 工具链是 Tools 的应用案例 |

---

## 6. 风格约束(本系列统一遵守)

1. **源码密度 ≤ 15%**——本系列以命令矩阵和决策树为主,代码少而精
2. **命令矩阵优先**——能用表格说清楚的,不用文字段落
3. **决策树替代枚举**——"遇到 X 用 Y" 比 "Y 的源码是…" 更实用
4. **每个工程资产都要"5 分钟跑通"**——可执行、可复用、有注释
5. **案例必须有"现象→分析→根因→修复"四段式**——避免"看图说话"
6. **版本敏感**——am 命令在 Android 11/12/14 上行为有差异,必须标注

---

## 7. 配套基线

| 项 | 版本/路径 |
|----|---------|
| AOSP 基线 | `android-14.0.0_r1` |
| adb 工具 | `platform-tools 34.0.0+` |
| Android Studio | Hedgehog (2023.1.1) 或更新 |
| AMS 源码路径 | `frameworks/base/services/core/java/com/android/server/am/` |
| `am.jar` 路径 | `frameworks/base/cmds/am/` |
| ART `Debug.dumpHprofData` | `art/runtime/debug.cc` |
| 工具链 | `hprof-conv`(SDK `platform-tools/`)、`simpleperf` |

---

## 8. 交付状态

| 批 | 状态 | 篇目 |
|----|------|------|
| **第一轮**(已交付) | ✅ | README + 01-am 全景 + 04-dumpheap 详解 + 工程资产(2 脚本 + 3 配置) |
| **第二轮**(已交付) | ✅ | 02-进程管理三件套 + 05-诊断与监控 hang/monitor + 工程资产(2 脚本) |
| **第三轮**(已交付) | ✅ | 03-性能分析 profile + 06-自动化实战 CI 集成 + 工程资产(amlib.py 6 模块 + 3 巡检脚本 + 2 CI yml + 2 profile 脚本 + 1 配置) |
| **系列总进度** | 🎉 | **6/6 篇全部交付,AmCommand 系列完结** |

### 8.1 系列完结总结

```
AmCommand 系列(6 篇) —— 已 100% 交付
├── 01-am 全景(基础原理 + Activity 触发)
├── 02-进程三件套(kill/crash/restart + 现场保留)
├── 03-profile(Sampling vs Instrumented + 工具矩阵)
├── 04-dumpheap(4 跳调用栈 + hprof 转换 + 5 分钟跑通)
├── 05-hang/monitor(主动 ANR + 实时事件流)
└── 06-自动化实战(amlib.py + 3 巡检 + 2 CI 模板)
```

**核心工程资产**:
- **amlib.py**:覆盖前 5 篇所有 am 命令的 Python SDK
- **3 个巡检脚本**:冷启动 / 内存压力 / 进程稳定性
- **2 个 CI 模板**:GitHub Actions + GitLab CI
- **5 个 shell/ps1 脚本**:dumpheap / profile / monitor / crash_capture
- **3 个配置文件**:am_start_params / am_dumpheap_workflow / am_profile_params

**总产出**:6 篇主文(总行数 ~4500+) + 13 个工程资产(脚本/SDK/配置/CI)

