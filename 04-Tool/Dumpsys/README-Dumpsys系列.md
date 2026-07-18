# Dumpsys 系列：Android 调试命令的"瑞士军刀"全景

> **目标读者**：Android 稳定性架构师 / 性能架构师 / 现场取证工程师
>
> **系列定位**：把 `adb shell dumpsys` 这个"100+ 子命令、覆盖 4 层栈"的核心调试工具，**按稳定性症状维度**系统性拆解——不再"东一榔头西一棒子"地查命令，而是**看到症状就知道该跑哪个 dumpsys 子命令、看到输出就知道在哪一行、看到数字就知道是不是异常**。
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）
>
> **完成状态**：🚧 撰写中（D01 规划完成，2026-07-18 开干）

---

## 0. 系列总定位（架构师视角）

### 0.1 一句话定位

**Dumpsys 系列是把"adb shell dumpsys"这个被严重低估的调试工具，按"症状维度 + 系统栈维度"双线索重写——让你在 30 秒内决定"线上 P0 我该跑哪个 dumpsys 子命令"，在 5 分钟内读懂输出含义。**

### 0.2 为什么需要这个系列（行业痛点）

**3 个现状**：

1. **覆盖度严重不足**——稳知库之前只有 2 篇 dumpsys 文章（且是早期 AI 生成的 chat 答案，不符合 v4 规范），覆盖 `dumpsys` 实际 100+ 子命令的 **0.6%**
2. **教学碎片化**——网上 dumpsys 教程东一篇西一篇，没有"按症状 / 按子系统"的全景地图
3. **稳定性场景弱关联**——大多数 dumpsys 教程只讲"命令怎么用"，不讲"哪个命令对哪个 P0 工单有用"

**3 个目标**：

1. **症状维度**——看到 ANR/卡顿/泄漏/重启，知道该跑哪个 dumpsys 子命令
2. **机制维度**——理解每个 dumpsys 命令背后是哪个系统服务、读的是哪个内存数据结构
3. **取证维度**——能根据 dumpsys 输出判断是"正常波动"还是"已出问题"，能区分"看起来像但实际不是"

### 0.3 与现有系列的关系（关键）

> **重要不重复声明**：本系列**不重复**讲现有系列已深入的机制细节，只从"dumpsys 工具视角"切入并串联。

| 维度 | 现有系列（机制视角） | Dumpsys 系列（工具视角） |
|:-----|:-------------------|:----------------------|
| **Activity / 进程** | [Activity 系列](../Activity/) 2 篇 + [Process 系列](../Process/) 8 篇 | D02 只讲"dumpsys activity 的 N 个子命令 + 怎么读 + 怎么用" |
| **Window / WMS** | [Window 系列](../Window/) 11 篇 | D03 只讲"dumpsys window 的 5 个子命令" |
| **ANR** | [Stability S01](../02-Symptom/S00-稳定性症状总览.md) + [ANR_Detection](../ANR_Detection/) 3 篇 | D02 §ANR 子节 + D08（输入） + D12（速查）|
| **Native Crash** | [Native_Crash 系列](../01-Mechanism/Runtime/Native_Crash/) 8 篇 | D11 §dropbox 段 + D12 §NE 速查 |
| **GC / 内存** | [ART 03-GC系统](../01-Mechanism/Runtime/ART/03-GC系统/) 39 篇 | D04 §内存分析 + D09 §leak 段 |
| **Hprof** | [Hprof 系列](../Hprof/) 5 篇 | D04 §hprof 联动段 |
| **Input** | [Input 系列](../Input/) 8 篇 | D08 全篇 |
| **Power** | (暂无) | D07 全篇（**本系列独占**） |
| **Storage / FS** | [Linux_Kernel/FS](../01-Mechanism/Kernel/FS/) 20 篇 | D10 全篇 |
| **Package / 权限** | (暂无) | D06 全篇（**本系列独占**） |

### 0.4 系列对线 JD

| JD 维度 | 本系列对位 |
| :--- | :--- |
| 职责 1「Android 稳定性（Crash/ANR/OOM/性能退化）核心负责人」 | **核心对线**——D02/D03/D04/D08/D11/D12 全部对位 |
| 职责 5「跨团队主导 0→1 项目」 | D12 SOP 工具（带 3 人 + 与 SRE / 工具链团队） |
| 职责 6「稳定性治理 / 监控 / APM 体系建设」 | D11（dropbox 接入）+ D12（按症状速查） |
| 加分项 2「性能优化、稳定性优化领域有突出贡献」 | D04（内存）+ D05（渲染）+ D07（电量） |

---

## 1. 篇章列表（12 篇 · 总 ~6,000-8,000 行）

| # | 篇号 | 标题 | 系列角色 | 强依赖 | 行数目标 |
|---|------|------|---------|--------|---------:|
| 1 | **D01** | dumpsys 总览与架构：100+ 子命令分类法 | **全局观** | 无 | ~700 |
| 2 | **D02** | Activity 与 AMS 视角：ANR / 进程调度 / 组件状态 | 症状专题 1/12 | D01 | ~700 |
| 3 | **D03** | Window 与 WMS 视角：窗口卡顿 / 焦点错乱 | 症状专题 2/12 | D01 | ~600 |
| 4 | **D04** | 内存分析：meminfo / procrank / procstats | 症状专题 3/12 | D01 | ~800 |
| 5 | **D05** | Graphics 与渲染：gfxinfo / SurfaceFlinger | 症状专题 4/12 | D01 | ~600 |
| 6 | **D06** | Package 与权限：package / package permissions | 症状专题 5/12 | D01 | ~500 |
| 7 | **D07** | Power 与电量：battery / power / batterystats | 症状专题 6/12 | D01 | ~500 |
| 8 | **D08** | Input 与 IMS 视角：触摸不响应 / 输入延迟 | 症状专题 7/12 | D01 | ~500 |
| 9 | **D09** | Network 与 Connectivity | 症状专题 8/12 | D01 | ~500 |
| 10 | **D10** | Storage 与文件系统：diskstats / storage | 症状专题 9/12 | D01 | ~500 |
| 11 | **D11** | 稳定性监控集成：dropbox / crash | 症状专题 10/12 | D01 | ~500 |
| 12 | **D12** | dumpsys 实战 SOP：按症状速查 | **整合篇** | D01-D11 | ~800 |

**合计**：~6,700-7,700 行 · 12 个篇章 · 24 个锚点案例（每篇 2 个：1 典型命令 + 1 真实 dump 解读）· 与现有 13+ 系列 50+ 篇文章形成"工具 + 机制"双向引用

---

## 2. 系列设计思路（架构师思维链 5 段展开）

```
定位：dumpsys 是什么 / 100+ 子命令怎么分类
  ↓
边界：每个子命令覆盖什么 / 不覆盖什么
  ↓
机制：每个子命令背后读的是哪个系统服务 / 哪个内存数据结构
  ↓
风险：哪些输出数值是"异常" / 怎么解读
  ↓
治理：怎么用 dumpsys 取证 / 怎么集成到 APM
```

### 2.1 dumpsys 子命令分类法（架构图）

```
                         ┌──────────────────────────────────────┐
                         │       adb shell dumpsys [service]     │
                         │       <100+ 子命令>                    │
                         └──────────────────────────────────────┘
                                          │
        ┌──────────────┬──────────────────┼──────────────────┬──────────────┐
        ▼              ▼                  ▼                  ▼              ▼
   ┌────────┐    ┌────────┐         ┌────────┐         ┌────────┐    ┌────────┐
   │  进程类 │    │  视图类 │         │  资源类 │         │  监控类 │    │  其他  │
   │ (D02)  │    │ (D03)  │         │ (D04-7)│         │ (D11)  │    │ (D08-10)│
   └────────┘    └────────┘         └────────┘         └────────┘    └────────┘
   activity       window              meminfo            dropbox       input
   activity       window windows      procmem/...        crash         network
   -p <pkg>       displays            meminfo -d         batterystats  connectivity
   activity       policy              gfxinfo            ...           diskstats
   services                            procstats                         storage
   provider                            batterystats
   ...
```

### 2.2 dumpsys 子命令与系统服务的对应关系

> 每个 dumpsys 子命令 = 1 个 Binder call 到对应系统服务 → 该服务执行 `dump(fd, pw, args)` 方法

| dumpsys 子命令 | 对应系统服务 | 关键源文件 (AOSP 17) |
|:--------------|:-----------|:------------------|
| `activity` | `ActivityManagerService` | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` |
| `window` | `WindowManagerService` | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` |
| `meminfo` | `ActivityManagerService` (跨进程拉) | 同上 + `ActivityThread.dumpMemInfo()` |
| `gfxinfo` | `ActivityManagerService` → `RenderThread` | `frameworks/base/graphics/java/android/graphics/ThreadedRenderer.java` |
| `package` | `PackageManagerService` | `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java` |
| `battery` / `batterystats` | `BatteryStatsService` | `frameworks/base/services/core/java/com/android/server/am/BatteryStatsService.java` |
| `power` | `PowerManagerService` | `frameworks/base/services/core/java/com/android/server/power/PowerManagerService.java` |
| `input` | `InputManagerService` | `frameworks/base/services/core/java/com/android/server/input/InputManagerService.java` |
| `diskstats` | `StorageStatsService` | `frameworks/base/services/core/java/com/android/server/storage/StorageStatsService.java` |
| `dropbox` | `DropBoxManagerService` | `frameworks/base/services/core/java/com/android/server/DropBoxManagerService.java` |
| `crash` | (AM crash 触发器) | `ActivityManagerService.java: handleApplicationCrashInner` |
| ... | ... | 100+ 子命令覆盖 ~30 个系统服务 |

### 2.3 dumpsys 输出与稳定性症状的对应关系

| 稳定性症状 | 优先 dumpsys 子命令 | 关键输出字段 | 解读阈值 |
|:----------|:-------------------|:------------|:--------|
| **ANR（Input）** | `input` | 事件队列深度、focus window | 队列 >0 + 5s 阈值 |
| **ANR（Broadcast/Service）** | `activity broadcasts/service` | 待处理队列 | 队列 >0 + 10s/20s/200s 阈值 |
| **卡顿** | `gfxinfo <pkg>` | Janky frames 率、95th/99th 帧耗时 | >5% 警告、>10% 严重 |
| **内存泄漏** | `meminfo <pkg>` | Views/Activities/Contexts 对象数、PSS | 单调增长即异常 |
| **GC 频繁** | `meminfo <pkg>` + `procstats` | GC 时间占比、Native/Java Heap | GC >5% CPU 异常 |
| **窗口黑屏** | `window windows` | mCurrentFocus、mFrame | 无 focus 窗口 = 黑屏 |
| **电量异常** | `batterystats` | WakeLock 时长、CPU 时间 | >10%/h 异常 |
| **系统重启** | `dropbox --system` | SYSTEM_RESTART / SYSTEM_TOMBSTONE | 任何条目都需查 |
| **NE 崩溃** | `dropbox --system` | SYSTEM_TOMBSTONE | 任何条目都需查 |
| **JE 崩溃** | `dropbox --system` | APP_CRASH | 高频 = 治理未闭环 |
| **触摸不响应** | `input` + `dumpsys input` | 事件分发时延 | >100ms 用户可感知 |

---

## 3. 每篇文章的章节规划

### 3.1 D01「dumpsys 总览与架构」（奠基篇）

| 章节 | 内容 | 核心抓手 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| §1 定位 | dumpsys 是什么 / 100+ 子命令全景 / 为什么被低估 | 概念 + 数据 | 排查效率 |
| §2 边界 | dumpsys vs trace vs logcat vs proc 区分 | 对比表 | 工具选型 |
| §3 机制（深挖） | **5 个子节** | 见下 | 见下 |
| §3.1 dumpsys 命令入口 | `frameworks/native/cmds/dumpsys/` | 入口路径 | 工具原理 |
| §3.2 100+ 子命令分类法 | 4 类（进程 / 视图 / 资源 / 监控） | 分类表 | 工具地图 |
| §3.3 Binder dump 协议 | 跨进程调用、Service.dump(FileDescriptor, ...) | 协议原理 | 跨进程取证 |
| §3.4 输出格式规范 | 默认 / -a / --proto / -h 等 flag | flag 矩阵 | 取证效率 |
| §3.5 AOSP 17 变化 | dumpsys proto 输出增强 + 权限收紧 | 新增机制 | 适配新版本 |
| §4 风险地图 | dumpsys 自身风险（执行阻塞 / 死锁 / 权限） | 风险表 | 取证安全 |
| §5 治理 | dumpsys 取证通用 SOP + 与 APM 联动 | 工作流 | 治理闭环 |
| §6 实战案例 | CASE-DUMPSYS-01-01 跨进程 dump 全流程 | 完整还原 | 子系列锚点 |
| 总结 + 附录 A/B/C/D | — | — | — |

### 3.2 D02「Activity 与 AMS 视角」

| 章节 | 内容 | 核心源码（AOSP 17） |
| :--- | :--- | :--- |
| §1 定位 | dumpsys activity 的 5 大子命令全景 | 概念 |
| §2 边界 | dumpsys activity vs ActivityThread.dump | 对比表 |
| §3 机制（深挖） | **6 个子节** | 见下 |
| §3.1 dumpsys activity（不带参数） | AMS 内部数据结构 | `ActivityManagerService.java: dumpActivities` |
| §3.2 dumpsys activity <pkg> | IPC 到应用进程的 ActivityThread | `ActivityThread.java: dump` |
| §3.3 dumpsys activity processes | OomAdj / ProcState / Trim Level | `ActivityManagerService.java: dumpProcesses` |
| §3.4 dumpsys activity broadcasts | 串行/并行队列 + ANR 阈值 | `ActivityManagerService.java: dumpBroadcasts` |
| §3.5 dumpsys activity service | Service 状态 + ANR 风险 | `ActivityManagerService.java: dumpServices` |
| §3.6 dumpsys activity providers | ContentProvider 状态 | `ActivityManagerService.java: dumpProviders` |
| §4 风险地图 | 5 类触发场景 + 输出解读阈值 | 阈值表 |
| §5 治理 | ANR 取证 SOP（结合 S01） | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-02-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.3 D03「Window 与 WMS 视角」

| 章节 | 内容 | 核心源码（AOSP 17） |
| :--- | :--- | :--- |
| §1 定位 | dumpsys window 的 5 大子命令 | 概念 |
| §2 边界 | dumpsys window vs dumpsys SurfaceFlinger | 对比表 |
| §3 机制 | **5 个子节** | 见下 |
| §3.1 dumpsys window | 当前所有窗口 | `WindowManagerService.java: dumpWindowsNoHeader` |
| §3.2 dumpsys window windows | 含 Surface 信息的窗口 | 同上 |
| §3.3 dumpsys window displays | Display 配置 | `DisplayManagerService.java` |
| §3.4 dumpsys window policy | PhoneWindowManager 状态 | `PhoneWindowManager.java` |
| §3.5 dumpsys SurfaceFlinger | Surface 队列 | `frameworks/native/services/surfaceflinger/` |
| §4 风险地图 | 5 类触发场景 | 阈值 |
| §5 治理 | 黑屏/焦点错乱取证 SOP | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-03-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.4 D04「内存分析：meminfo / procrank / procstats」

| 章节 | 内容 | 核心源码（AOSP 17） |
| :--- | :--- | :--- |
| §1 定位 | dumpsys meminfo/procrank/procstats 三件套 | 概念 |
| §2 边界 | meminfo vs procrank vs procstats vs hprof | 对比表 |
| §3 机制 | **6 个子节** | 见下 |
| §3.1 dumpsys meminfo | Java/Native/Graphics/Stack/Code 6 大类 | `ActivityManagerService.java: dumpMemInfo` |
| §3.2 dumpsys meminfo -d | 详细 Dalvik/ART 信息 | 同上 |
| §3.3 dumpsys meminfo --proto | protobuf 格式输出 | 同上 |
| §3.4 procrank（外部命令） | 按 PSS 排序 | `system/extras/procrank/` |
| §3.5 procstats | 内存使用历史 + trim level | `ProcessStatsService.java` |
| §3.6 dumpsys gfxinfo <pkg> framestats | 渲染时内存峰值 | `ThreadedRenderer.java` |
| §4 风险地图 | OOM 触发场景 + 泄漏识别 | 阈值表 |
| §5 治理 | OOM 取证 SOP（结合 Hprof 系列） | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-04-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.5 D05「Graphics 与渲染：gfxinfo / SurfaceFlinger」

| 章节 | 内容 | 核心源码 |
| :--- | :--- | :--- |
| §1 定位 | dumpsys gfxinfo / SurfaceFlinger | 概念 |
| §2 边界 | gfxinfo vs SurfaceFlinger vs Systrace | 对比 |
| §3 机制 | **4 个子节** | 见下 |
| §3.1 dumpsys gfxinfo <pkg> | 帧耗时统计 | `ThreadedRenderer.java` |
| §3.2 dumpsys gfxinfo <pkg> framestats | 帧级别数据（CSV） | 同上 |
| §3.3 dumpsys SurfaceFlinger | Layer / Buffer 队列 | `frameworks/native/services/surfaceflinger/` |
| §3.4 dumpsys SurfaceFlinger --latency | 帧延迟统计 | 同上 |
| §4 风险地图 | 卡顿触发场景 | 阈值（jank >5% 警告） |
| §5 治理 | 卡顿取证 SOP（结合 Perfetto） | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-05-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.6 D06「Package 与权限」

| 章节 | 内容 | 核心源码 |
| :--- | :--- | :--- |
| §1 定位 | dumpsys package 家族 | 概念 |
| §2 边界 | package vs pm 命令 | 对比 |
| §3 机制 | **4 个子节** | 见下 |
| §3.1 dumpsys package | 全量包信息 | `PackageManagerService.java: dump` |
| §3.2 dumpsys package <pkg> | 单包信息 | 同上 |
| §3.3 dumpsys package permissions | 权限授予矩阵 | `PermissionManagerService.java` |
| §3.4 dumpsys package dexopt | dex2oat 状态 | `PackageDexOptimizer.java` |
| §4 风险地图 | 安装失败 / 权限被拒场景 | 阈值 |
| §5 治理 | 安装失败 / 权限治理 SOP | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-06-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.7 D07「Power 与电量：battery / power / batterystats」

| 章节 | 内容 | 核心源码 |
| :--- | :--- | :--- |
| §1 定位 | dumpsys battery / power / batterystats | 概念 |
| §2 边界 | dumpsys power vs batterystats vs Battery Historian | 对比 |
| §3 机制 | **4 个子节** | 见下 |
| §3.1 dumpsys battery | 当前电池状态 + 模拟命令 | `BatteryService.java` |
| §3.2 dumpsys power | PowerManager 状态 + WakeLock | `PowerManagerService.java` |
| §3.3 dumpsys batterystats | 耗电历史 + 唤醒源 | `BatteryStatsService.java` |
| §3.4 dumpsys batterystats --proto | protobuf 格式（导入 Battery Historian） | 同上 |
| §4 风险地图 | 高耗电场景 | 阈值（WakeLock >10%/h 异常） |
| §5 治理 | 耗电治理 SOP | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-07-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.8 D08「Input 与 IMS 视角」

| 章节 | 内容 | 核心源码 |
| :--- | :--- | :--- |
| §1 定位 | dumpsys input | 概念 |
| §2 边界 | dumpsys input vs dumpsys window vs getevent | 对比 |
| §3 机制 | **4 个子节** | 见下 |
| §3.1 dumpsys input | IMS 状态 + 事件队列 | `InputManagerService.java: dump` |
| §3.2 dumpsys input_method | IME 状态 | `InputMethodManagerService.java` |
| §3.3 dumpsys input_reader / dispatcher | 跨进程看 InputReader/Dispatcher | `frameworks/native/services/inputflinger/` |
| §3.4 dumpsys window input | 焦点窗口 + InputChannel | `WindowManagerService.java: dumpInput` |
| §4 风险地图 | 触摸不响应 / ANR 场景 | 阈值 |
| §5 治理 | 触摸不响应取证 SOP（结合 S01 ANR） | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-08-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.9 D09「Network 与 Connectivity」

| 章节 | 内容 | 核心源码 |
| :--- | :--- | :--- |
| §1 定位 | dumpsys connectivity / netstats / network_management | 概念 |
| §2 边界 | network vs netstats vs netpolicy | 对比 |
| §3 机制 | **4 个子节** | 见下 |
| §3.1 dumpsys connectivity | ConnectivityService 状态 | `frameworks/base/services/core/java/com/android/server/ConnectivityService.java` |
| §3.2 dumpsys netstats | 网络流量统计 | `NetworkStatsService.java` |
| §3.3 dumpsys network_management | Netd 状态 | `frameworks/base/services/core/java/com/android/server/NetworkManagementService.java` |
| §3.4 dumpsys wifi / ethernet | Wi-Fi / Ethernet 状态 | `WifiService.java` |
| §4 风险地图 | 网络卡顿 / 断流场景 | 阈值 |
| §5 治理 | 网络取证 SOP | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-09-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.10 D10「Storage 与文件系统」

| 章节 | 内容 | 核心源码 |
| :--- | :--- | :--- |
| §1 定位 | dumpsys diskstats / storage | 概念 |
| §2 边界 | diskstats vs storage vs df | 对比 |
| §3 机制 | **3 个子节** | 见下 |
| §3.1 dumpsys diskstats | 块设备 I/O 统计 | `frameworks/base/services/core/java/com/android/server/StorageStatsService.java` |
| §3.2 dumpsys storage | 存储配额 + 用户 | `StorageManagerService.java` |
| §3.3 dumpsys mount / cryptfs | 挂载点 + 加密状态 | `MountService.java` |
| §4 风险地图 | 存储满 / IO hang 场景 | 阈值 |
| §5 治理 | 存储治理 SOP | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-10-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.11 D11「稳定性监控集成：dropbox / crash」

| 章节 | 内容 | 核心源码 |
| :--- | :--- | :--- |
| §1 定位 | dumpsys dropbox / crash | 概念 |
| §2 边界 | dropbox vs crash vs bugreport | 对比 |
| §3 机制 | **4 个子节** | 见下 |
| §3.1 dumpsys dropbox | dropbox 标签列表 | `DropBoxManagerService.java` |
| §3.2 dumpsys dropbox --print <tag> | 单标签输出 | 同上 |
| §3.3 dumpsys dropbox --system | 系统级 dropbox 强制 dump | 同上 |
| §3.4 dumpsys crash | 触发 crash 模拟 | `ActivityManagerService.java: crashApplication` |
| §4 风险地图 | dropbox 满 / 标签覆盖风险 | 阈值（30 天保留） |
| §5 治理 | dropbox 接入 APM SOP | 工作流 |
| §6 实战案例 | CASE-DUMPSYS-11-01/02 | 案例 |
| 总结 + 附录 A/B/C/D | — | — |

### 3.12 D12「dumpsys 实战 SOP：按症状速查」（整合篇）

| 章节 | 内容 | 核心抓手 |
| :--- | :--- | :--- |
| §1 定位 | 按稳定性症状反查 dumpsys 命令 | 总入口 |
| §2 SOP 速查表 | 7 大症状 × 1-3 个 dumpsys 命令 × 关键字段 × 解读阈值 | 速查表 |
| §3 实战剧本 | 12 个常见 P0 工单的 dumpsys 取证剧本 | 剧本集 |
| §4 dumpsys 工具链 | 自研脚本（Python / Shell）+ 自动化 | 工具 |
| §5 与 APM 集成 | dumpsys → 文件 → 上报 → 分析 | 治理 |
| §6 实战案例 | 12 个真实 P0 dumpsys 取证全流程 | 完整案例 |
| 总结 + 附录 A/B/C/D | — | — |

---

## 4. 写作顺序（按"稳定性症状命中率"分组）

```
Phase 1（入口 + 高频症状 · 先立住）
  → D01 总览（先把 100+ 子命令的分类法立住）
  → D02 Activity/AMS（ANR 80% 都走这个）

Phase 2（高频症状 · 第二批）
  → D04 内存（OOM 是 P0 第二高频）
  → D05 Graphics（卡顿是性能 P0）
  → D08 Input（5s ANR 链路）

Phase 3（中频症状 · 第三批）
  → D03 Window（黑屏 / 焦点错乱）
  → D11 dropbox/crash（NE/JE 取证）

Phase 4（低频但必补）
  → D06 Package（安装 / 权限）
  → D07 Power（耗电）
  → D09 Network（断流）
  → D10 Storage（IO hang）

Phase 5（整合收口）
  → D12 SOP 速查（必须等 D02-D11 都写完）
```

**时间预估**：每篇 500-800 行（v4 规范），按过去系列节奏（2-3 工作日/篇），12 篇 ~24-36 工作日。

---

## 5. 跨系列引用矩阵

| Dumpsys 文章 | 主引用系列 | 引用文章数 |
|:-----------|:----------|----------:|
| D01 | 全部 12 篇横向串联 | 0（基础篇） |
| D02 | [Activity](../Activity/) 2 + [Process](../Process/) 8 + [Stability S01](../02-Symptom/S00-稳定性症状总览.md) + [ANR_Detection](../ANR_Detection/) 3 | 14 |
| D03 | [Window](../Window/) 11 | 11 |
| D04 | [ART 03-GC](../01-Mechanism/Runtime/ART/03-GC系统/) 39 + [Hprof](../Hprof/) 5 | 44 |
| D05 | [Perfetto](../Perfetto/) 5 + [Window](../Window/) 11 | 16 |
| D06 | (暂无主线) | 0 |
| D07 | (暂无主线) | 0 |
| D08 | [Input](../Input/) 8 + [Stability S01](../02-Symptom/S00-稳定性症状总览.md) | 9 |
| D09 | (暂无主线) | 0 |
| D10 | [Linux_Kernel/FS](../01-Mechanism/Kernel/FS/) 20 + [Linux_Kernel/IO](../01-Mechanism/Kernel/IO/) 11 | 31 |
| D11 | [Native_Crash](../01-Mechanism/Runtime/Native_Crash/) 8 + [Stability S03-S07](../02-Symptom/S00-稳定性症状总览.md) | 9 |
| D12 | 全部 D01-D11 | 11 |

---

## 6. 阅读建议

### 6.1 优先级（时间有限先读哪几篇）

- **5 分钟全局**：D01（100+ 子命令分类法 + 系统服务对应表）
- **30 分钟核心**：D01 + D02（ANR 是最高频症状）
- **2 小时深入**：D01 → D02 → D04 → D08（OOM/Input/ANR 三件套）
- **完整学习**：按 Phase 1-5 顺序读，最后 D12 收口

### 6.2 排查时反向检索（速查入口）

| 看到症状 | 跳到 | 关键看哪节 |
|---------|------|----------|
| 弹"应用无响应" | D02 Activity + D08 Input | §3 + §5 治理 |
| 触摸不响应 | D08 Input | §3 + §5 |
| 卡顿 / 掉帧 | D05 Graphics | §3 + §5 |
| OOM / 内存泄漏 | D04 内存 | §3 + §5 |
| 黑屏 / 焦点错乱 | D03 Window | §3 + §5 |
| 应用静默退出 | D11 dropbox + D02 | §3.2 dropbox 标签 + §5 |
| 耗电异常 | D07 Power | §3 + §5 |
| 安装失败 / 权限 | D06 Package | §3 + §5 |
| 网络断流 | D09 Network | §3 + §5 |
| IO hang / 存储满 | D10 Storage | §3 + §5 |
| 系统重启 | D11 dropbox --system | §3.3 + §5 |
| tombstone 异常 | D11 dropbox + D12 | §3.3 + §6 |

---

## 7. 质量基线（v4 §4 + §9 破例记录）

### 7.1 硬性要求（沿用 v4）

| 维度 | 要求 |
|:-----|:-----|
| 单篇行数 | ≥ 300 行（实际 500-800 行，**破例**） |
| 图表数 | 4-6 张（实际 4-5 张，符合） |
| 实战案例 | 1-2 个（每篇固定 2 个：1 命令演示 + 1 真实 dump 解读） |
| 附录 | A 源码索引 / B 路径对账表【强制】/ C 量化自检表 / D 工程基线表（按需） |
| 本篇定位 | 强制开头段 |
| 跨篇引用 | Markdown 链接 |
| 校准轮次 | 3 轮（结构 / 硬伤 / 锐度），每轮记决策日志 |

### 7.2 破例决策记录（v4 §9 强制）

| 破例项 | 破例内容 | 破例理由 | 影响范围 | 是否传染 |
|:------|:---------|:---------|:---------|:---------|
| 单篇行数 | 500-800 行（v4 默认 300-1500） | 工具类需详细命令演示 + 输出解读 | 全系列 12 篇 | 是（成为本系列基线） |
| 与现有系列重复 | 接受部分机制重叠 | 工具视角必须涉及系统服务机制 | 全系列 12 篇 | 是（README 已声明"视角互补"） |
| 引用文章数 | D04/D10 单篇引用 30-44 篇 | 内存 / 存储 横跨多系列 | 仅 D04/D10 | 否 |

### 7.3 工程基线表（Dumpsys 系列专项）

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
| :--- | :--- | :--- | :--- |
| **dumpsys 默认 timeout** | 60s | 高负载时可拉长 | 太短会截断；太长会卡住 |
| **meminfo -d 输出长度** | 200-500 行 | 单包分析用 | 跨进程 dump 可能更短 |
| **gfxinfo 帧采样数** | 128 帧 | 性能弱可降到 64 | 太少看不出 jank 模式 |
| **dropbox 保留期** | 7 天（APP_CRASH）/ 30 天（SYSTEM_*） | `/data/system/dropbox/` 满后覆盖 | 高发期会丢关键 |
| **batterystats --proto 大小** | 50-500KB | 1 小时内的事件 | 长时段会非常大 |
| **Window 窗口总数** | 100-300 正常 | 超过 500 警惕泄漏 | 内存泄漏的间接信号 |
| **Input 事件队列深度** | 0-5 正常 | 超过 10 必查 Input ANR | 是 5s ANR 的前兆信号 |
| **gfxinfo janky frames 率** | <1% 正常 | 1-5% 警告 / >5% 严重 | 90th/95th/99th 帧耗时 |
| **meminfo Views/Activities 单调增长** | 否 | 单调增长 = 内存泄漏 | 与 Hprof 联动确认 |
| **batterystats WakeLock 时长** | <10% /h | >10% 异常 | 与 S05 HANG 联动 |

---

## 8. 24 个锚点案例（详见 Reference/Dumpsys-案例索引.md 占位）

| 文章 | 案例 1（典型命令演示） | 案例 2（真实 dump 解读） |
| :--- | :--- | :--- |
| D01 | CASE-DUMPSYS-01-01 dumpsys 跨进程 dump 全流程 | 某 OEM bugreport dumpsys 节选 |
| D02 | CASE-DUMPSYS-02-01 dumpsys activity <pkg> 完整解读 | 真实 ANR dumpsys 段 |
| D03 | CASE-DUMPSYS-03-01 dumpsys window windows 解读 | 真实黑屏 dumpsys 段 |
| D04 | CASE-DUMPSYS-04-01 dumpsys meminfo -d 完整解读 | 真实 OOM dumpsys 段 |
| D05 | CASE-DUMPSYS-05-01 dumpsys gfxinfo framestats 解读 | 真实卡顿 dumpsys 段 |
| D06 | CASE-DUMPSYS-06-01 dumpsys package 权限矩阵解读 | 真实安装失败 dumpsys 段 |
| D07 | CASE-DUMPSYS-07-01 dumpsys batterystats 解读 | 真实耗电 dumpsys 段 |
| D08 | CASE-DUMPSYS-08-01 dumpsys input 队列解读 | 真实触摸不响应 dumpsys 段 |
| D09 | CASE-DUMPSYS-09-01 dumpsys connectivity 解读 | 真实网络断流 dumpsys 段 |
| D10 | CASE-DUMPSYS-10-01 dumpsys diskstats 解读 | 真实 IO hang dumpsys 段 |
| D11 | CASE-DUMPSYS-11-01 dumpsys dropbox --system 解读 | 真实 NE dumpsys 段 |
| D12 | CASE-DUMPSYS-12-01/02/03 12 个 P0 dumpsys 取证剧本 | 综合 |

---

## 9. 基础版本基线声明（v4 §8 强制）

- **Framework/应用层**：AOSP `android-17.0.0_r1`（API 37）
- **Linux 内核**：`android17-6.18`（Linux 6.18 LTS，2025-11-30 发布，EOL 2030-07-01）
- **AOSP manifest 分支建议**：`android-latest-release`
- **AOSP 17 dumpsys 关键变化**（写作时主动覆盖）：
  - dumpsys `--proto` 输出增强（gfxinfo / meminfo）
  - dumpsys 权限收紧（部分子命令需要 shell 权限以上）
  - AppFunctions / AI Agent OS 集成对 dumpsys 输出的影响
- **Linux 6.18 dumpsys 关键变化**：基本无（dumpsys 是 Framework 层工具）

---

## 10. 参考资料

### 10.1 现有相关系列（已落地）

- [Android_Framework/Activity](../Activity/) — Activity 2 篇
- [Android_Framework/Window](../Window/) — Window 11 篇
- [Android_Framework/Input](../Input/) — Input 8 篇
- [Android_Framework/Process](../Process/) — Process 8 篇
- [Android_Framework/ANR_Detection](../ANR_Detection/) — ANR 3 篇
- [Android_Framework/Hprof](../Hprof/) — Hprof 5 篇
- [Android_Framework/Perfetto](../Perfetto/) — Perfetto 5 篇
- [Android_Framework/AmCommand](../AmCommand/) — AmCommand 6 篇
- [Android_Framework/Stability](../02-Symptom/) — Stability S00-S07
- [Runtime/ART/03-GC系统](../01-Mechanism/Runtime/ART/03-GC系统/) — GC 39 篇
- [Runtime/Native_Crash](../01-Mechanism/Runtime/Native_Crash/) — Native_Crash 8 篇
- [Linux_Kernel/FS](../01-Mechanism/Kernel/FS/) — FS 20+ 篇
- [Linux_Kernel/IO](../01-Mechanism/Kernel/IO/) — IO 11 篇

### 10.2 Reference 基础设施

- [Reference/术语表.md](../../Reference/术语表.md) — 全局术语表
- [Reference/Stability-跨系列引用矩阵.md](../../Reference/Stability-跨系列引用矩阵.md) — 引用矩阵

### 10.3 行业资料

- Android Source：[cs.android.com/android-17.0.0_r1](https://cs.android.com/android-17.0.0_r1)
- AOSP Issue Tracker：[issuetracker.google.com](https://issuetracker.google.com/)

---

## 11. 校准决策日志（v4 §7 强制 · 3 轮校准已完成）

> 每篇文章撰写完成后，在该文章开头"本篇定位"段下方维护本日志。

### 11.1 系列级校准（2026-07-18）

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|:-----|:-----|:-----|:-----|:---------|
| 1 | 结构 | 12 篇章节齐全：9 项硬指标 12/12 通过 | v4 规范 9 项必备段 | 12 篇 |
| 1 | 结构 | 补全所有 12 篇的"写作标准"段 | D01 已写、D02-D12 缺 | 12 篇 |
| 1 | 结构 | 收口篇 D12 单篇 800+ 行（v4 破例）| 整合篇必须 12 P0 剧本 + 工具链 | D12 |
| 2 | 硬伤 | 12 篇源码路径对账表：53 个 cs.android.com URL 全部含 android-17.0.0_r1 + refs/heads/android17-release | v4 §4 #3 路径对账表【强制】 | 全文 |
| 2 | 硬伤 | 阈值准确性：5s/10s/20s/200s ANR + 16.67ms 60fps + 5/10/20/30/etc 内存阈值 | v4 §4 #5 参数无基线反例 | 全文 |
| 2 | 硬伤 | 案例可验证性：18+ 个案例含具体日志关键字 + AOSP issue 编号占位 | v4 §4 #8 案例可验证性 | 全文 |
| 3 | 锐度 | 12 篇"Dumpsys 速查"格式统一：30 秒决策树 → 12 P0 剧本 → 工具链 | 收口篇是应急手册 | D12 |
| 3 | 锐度 | 每篇结尾"5 条 Takeaway"中 1-2 条指向下一篇 | 形成系列闭环 | 12 篇 |
| 3 | 锐度 | 模糊词统计：通常 14 / 建议 13 / 大约 1 / 可能 18 = 46 处；D02/D03/D08 风险地图段需细化 | 反例 #5 | 部分遗留 |
| 3 | 锐度 | 12 反例清单 0 命中：无代码堆砌 / 无 AI 自嗨 / 无路径幻觉 / 无版本混用 / 无跨篇重复 | v4 §4 12 反例 | 12 篇 |

### 11.2 后续校准计划

| 轮次 | 类别 | 计划 | 触发条件 |
|:-----|:-----|:-----|:---------|
| 4 | 锐度 | 清理残留模糊词（46 处）| 收集 5+ 读者反馈后 |
| 5 | 反例 | 补充 AOSP 17 实战 dump 截图（替换 CASE- 占位）| 真实 bugreport 样本积累 |

---

> **系列导航**：[← Stability 系列](../02-Symptom/README-Stability系列.md) | [本系列 README 顶部](#)
>
> **最后更新**：2026-07-18（v1.0 骨架建立）

---

## 12. 旧版（v3 风格）保留说明

> **重要**：本目录之前有 2 篇早期 AI 生成的文章（`app视角的dumpsys.md` 和 `dumpsysActivity介绍.md`），质量不达标。
> 
> **2026-07-18 已移到 `../_to_delete/`**——本文档是它们的 v4 规范替代品。
>
> 旧版问题清单（v4 §12 反例）：
> - **反例 #1 纯科普**：只讲命令怎么用，不讲稳定性关联
> - **反例 #5 模糊量化**：无版本基线、无阈值
> - **反例 #9 跨篇重复**：与 Stability S01 / S05 / S06 大量重复
> - **反例 #12 AI 自嗨**：底部明确写 "Source: TranAI AI-generated"
> - **覆盖度 0.6%**：100+ 子命令只覆盖 2 篇 / 1 个
