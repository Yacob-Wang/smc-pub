# Service 系列导读

> **作者角色**：Android 稳定性架构师
> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
> **写作规范**：[PROMPT-技术系列文章写作指南-v4.md](../../../PROMPT-技术系列文章写作指南-v4.md)
> **本系列起始**：2026-07-18
> **本系列规划文档**：[三系列重写规划-2026-07-18.md](../三系列重写规划-2026-07-18.md)
> **依赖前序系列**：[Activity 系列](../Activity/README.md)（已发布）

---

## 一、为什么要写这个系列

Service 是 Android 四大组件中**唯一专门用于"后台执行"**的组件。从稳定性视角看：

- **占线上 ANR 第二高比例**：Service ANR 占 ANR 总量的 20-30%（仅次于 Activity 启动 ANR），Service `onCreate` / `onStartCommand` 默认阈值 20s。
- **Android 14+ 后台启动收紧的"重灾区"**：前台服务（FGS）类型化、后台启动限制、ForegroundServiceTypeException 等都是 AOSP 14 引入的，**升级到 AOSP 14 必崩**。
- **跨进程通信的核心桥梁**：bindService 是 AIDL / Messenger 等 IPC 机制的基础，**Service 死亡链路**直接决定 IPC 稳定性。
- **进程保活的关键战场**：`onTrimMemory` / `onTaskRemoved` / `START_STICKY` 等行为差异巨大，**AOSP 12+ 行为变化多次**。

本系列的目标：让稳定性架构师**能在 30 分钟内**把任意一个"Service 相关线上问题"定位到具体的源码文件、阈值常量、调用栈。

## 二、系列设计思路

### 2.1 架构师思维链

```
[定位]   S01 · Service 全景           → 4 种 Service 分类 + 进程模型 + 协作组件
   ↓
[边界]   S02-S03 · 启动 / 绑定路径     → startService / bindService 全链路
   ↓
[机制]   S04-S06 · 核心机制三件套
            FGS 类型化 / WorkManager / 死亡链路
   ↓
[风险]   S07 · Service ANR 全景      → 5s/10s/20s 阈值 + 根因分类
   ↓
[横切]   S08 · 进程保活与 onTrimMemory
   ↓
[治理]   S09 · 跨进程 Binder 限制与 Service 上限
```

### 2.2 依赖关系图

```
S01 全景 (总览篇)
  │
  ▼
S02 startService 路径 (核心机制)
  │
  ├──→ S03 bindService 路径    (独立机制)
  ├──→ S04 前台服务 FGS        (AOSP 14+ 重头戏)
  ├──→ S05 WorkManager 演进     (替代方案)
  ├──→ S06 多客户端与死亡链路  (基于 S03)
  │
  ▼
S07 Service ANR (风险)
  │
  ▼
S08 进程保活 (横切)
  │
  ▼
S09 Service 上限 (治理)
```

### 2.3 跨系列引用矩阵

| 本篇 | 引用其他系列 | 引用章节 | 引用原因 | 链接有效性最后核查 |
|------|-------------|---------|---------|-------------------|
| S01 | Activity | A01 §2.1 | 四大组件协作图 | 2026-07-18 |
| S01 | Activity | A02 | startService 是从 Activity 启动的父调用 | 2026-07-18 |
| S02 | Activity | A02 | startService 链路 | 2026-07-18 |
| S03 | Binder 系列 | 待定 | bindService 走跨进程 Binder | 2026-07-18 |
| S04 | Window | 待定 | FGS 通知在 NotificationManager | 2026-07-18 |
| S05 | Process | 04-应用进程首生 | WorkManager 涉及进程优先级 | 2026-07-18 |
| S06 | Binder | 待定 | 死亡通知是 Binder 能力 | 2026-07-18 |
| S07 | Activity | A07 | ANR 整体机制（Service ANR 是子类） | 2026-07-18 |
| S08 | Process | 04-应用进程首生 | onTrimMemory 与进程优先级 | 2026-07-18 |
| S09 | Activity | A09 | 内存治理与 Service 上限 | 2026-07-18 |

### 2.4 与其他系列的边界声明

- **与 Activity 系列的边界**：Activity 启动 Service 的父调用链路不展开；只在本系列 S02 中简述"Activity 启动 Service 的入口"。
- **与 Broadcast 系列的边界**：Service 内部注册 BroadcastReceiver 的场景不展开；只在本系列 S08 提到"Service 应该 onDestroy 中解绑 Receiver"。
- **与 Process 系列的边界**：zygote fork 不在本系列展开，引用 Process 04 即可。
- **与 Binder 系列的边界**：bindService 跨进程 Binder 调用细节不展开；只在本系列 S03 提到"AIDL 接口注册"。

## 三、每篇文章的章节规划

| 篇号 | 标题 | 角色 | 核心源码路径（基线 android-17.0.0_r1） | 稳定性关联 |
|------|------|------|--------------------------------------|----------|
| S01 | Service 全景：分类、进程模型与协作组件 | 总览篇 | `frameworks/base/services/core/java/com/android/server/am/ActiveServices.java`<br>`frameworks/base/core/java/android/app/Service.java` | 全局性 |
| S02 | startService 路径：onCreate → onStartCommand → onDestroy | 核心机制 | `Service.java`<br>`ActivityManagerService.java` (`startService`)<br>`ActiveServices.java`<br>`ServiceRecord.java` | Service 启动失败 |
| S03 | bindService 路径：Connection 池与跨进程 Binder | 核心机制 | `ServiceConnection`<br>`LoadedApk.java`<br>`IServiceConnection.aidl` | 解绑失败 / Binder 泄漏 |
| S04 | 前台服务 FGS：Android 14+ 后台启动限制与类型化 | 风险地图 | `ActiveServices.java`<br>`ForegroundServiceTypeException` (API 34+)<br>`ServiceInfo.java FOREGROUND_SERVICE_TYPE_*` | FGS 启动崩溃 / 后台 ANR |
| S05 | WorkManager 演进：JobScheduler 之上的后台任务最佳实践 | 核心机制 | `frameworks/base/services/core/java/com/android/server/job/JobSchedulerService.java`<br>`androidx.work:work-runtime-ktx` | 后台任务丢失 / 限频 |
| S06 | 多客户端与死亡链路：unbindService 与 binderDied | 核心机制 | `LoadedApk$ServiceDispatcher`<br>`DeathRecipient` | 死亡回调未触发 |
| S07 | Service ANR 全景：20s/10s/5s 阈值与根因分类 | 风险地图 | `ActiveServices.java` (`serviceTimeout` / `foregroundServiceTimeout`)<br>`AnrHelper.java` | Service ANR |
| S08 | 进程保活与 onTrimMemory（横切专题） | 横切专题 | `ActivityThread.handleLowMemory()`<br>`ProcessList.java`<br>`OomAdjuster.java` | 进程被回收 |
| S09 | 跨进程 Binder 限制与 Service 上限 | 诊断治理 | `ProcessList.java MAX_CACHED_PROCESSES`<br>`IActivityManager.broadcastIntent` 链路 | Binder 限制 / Service 数量超限 |

## 四、阅读建议

### 4.1 时间有限优先阅读（30 分钟路径）

1. **S01 全景**（8 分钟）— 建立 Service 协作模型
2. **S02 startService**（10 分钟）— startService 链路
3. **S07 Service ANR**（12 分钟）— 风险图 + 阈值表

### 4.2 系统学习推荐顺序

```
S01 → S02 → S03 → S04 → S05 → S06 → S07 → S08 → S09
```

约 80-100 分钟完成全系列。建议每天 1-2 篇，留足消化源码的时间。

### 4.3 每篇文章的设计逻辑

```
背景（是什么、为什么）→ 架构（在哪、和谁）→ 源码（怎么转）→ 风险（哪里坏）→ 案例（怎么修）
```

每篇都按这个五段式写，源码前必有上下文，源码后必有"稳定性架构师视角"分析。

## 五、破例决策记录

| 破例项 | 破例内容 | 破例理由 | 影响范围 | 是否传染 |
|--------|---------|---------|---------|---------|
| S01 总览篇 | 风险地图简版（3 类）+ 无实战案例 | §9.1 合法破例：总览篇 | 仅 S01 | 否 |
| S04 风险地图 | 4-6 张图（标准） | 风险地图本身需要图 | 仅 S04 | 否 |
| S07 风险地图 | 4-6 张图（标准） | 风险地图本身需要图 | 仅 S07 | 否 |
| S08 横切专题 | 3 张图（规则 4-6 张） | §9.1 合法破例：横切专题型 | 仅 S08 | 否 |
| S09 诊断治理 | 章节重排为"风险→工具→案例" | §9.1 合法破例：诊断工具型 | 仅 S09 | 否 |

## 六、质量基线（本系列特征）

### 6.1 关键阈值常量（本系列高频引用）

| 常量名 | 路径 | 值 | 说明 |
|--------|------|----|------|
| `SERVICE_TIMEOUT` | ActiveServices.java | 20s | 前台 Service 启动/onStartCommand 时限 |
| `SERVICE_BACKGROUND_TIMEOUT` | ActiveServices.java | 200s | 后台 Service 启动时限 |
| `SERVICE_START_FOREGROUND_TIMEOUT` | ActiveServices.java | 10s | 前台服务启动时限（AOSP 14+） |
| `KEY_DISPATCHING_TIMEOUT` | ActivityManagerService.java | 5s | 输入事件分发时限 |
| `PROC_START_TIMEOUT` | ActivityManagerService.java | 10s | 进程启动时限 |
| `MAX_CACHED_PROCESSES` | ProcessList.java | 系统级常量 | 缓存进程数上限 |
| `MAX_ACTIVE_SERVICES` | ActiveServices.java | 系统级常量 | 单进程最大 Service 数 |

> **稳定性架构师视角**：Service ANR 不是单一阈值，是**"Service 启动 / onStartCommand 链路上任意一环超时 → 上报到 AMS → 触发 ANR"** 的复合结果。

### 6.2 跨版本基线（多版本矩阵）

| 主题 | Android 13 (T, API 33) | Android 14 (U, API 34) | Android 15 (V, API 35) | Android 16 (API 36) | Android 17 (API 37) |
|------|------------------------|------------------------|------------------------|---------------------|---------------------|
| FGS 类型化 | 引入 | 强制声明 | 强化 | 强化 | 强化 |
| 后台启动 FGS | 限制 | 限制 | 收紧 | 收紧 | 收紧 |
| `ForegroundServiceTypeException` | n/a | 引入 | 强化 | 强化 | 强化 |
| Service onCreate 阈值 | 20s | 20s | 20s | 20s | 20s |
| 后台 Service 阈值 | 200s | 200s | 200s | 200s | 200s |
| Service 限频 | 弱 | 强 | 强 | 强 | 强 |
| `startServiceInForeground` | n/a | 引入 | 强化 | 强化 | 强化 |
| `startForegroundService` 后台启动 | 限制 | 严格限制 | 严格 | 严格 | 严格 |
| WorkManager 长任务 | 推荐 | 强化 | 强化 | 强化 | 强化 |
| onTrimMemory 行为 | 标准 | 强化 | 强化 | 强化 | 强化 |

> **本系列基线**：以 **android-17.0.0_r1** 为主线，差异点在文章中显式标注（如"// API 34+ 变化点"）。

## 七、版本与基线声明

- **AOSP 基线**：`android-17.0.0_r1`（API 37）
- **Linux 内核基线**：`android17-6.18` LTS
- **生效日期**：2026-07-18
- **基线升级规则**：按 [PROMPT v4 §8.3](../../PROMPT-技术系列文章写作指南-v4.md) 升级流程执行
- **路径对账**：每篇附录 B 必填，标注【已校对/待确认】+ 校对来源

## 八、Service 系列与 Activity / Broadcast 系列的协同

| 维度 | Activity | Service | Broadcast |
|------|----------|---------|-----------|
| UI | 有完整 UI 生命周期 | 无 UI | 无 UI |
| 启动方式 | startActivity + Intent | startService / bindService | sendBroadcast + Intent |
| ANR 主阈值 | 5s (启动) | 20s (前台) / 200s (后台) | 10s (前台) / 60s (后台) |
| 跨进程能力 | 通过 Intent flag | 通过 bindService (Binder) | 通过 sendBroadcast (Binder) |
| 死亡通知 | 无 | 有 (binderDied) | 有 (BroadcastReceiver 注销) |
| 内存泄漏高发区 | 静态引用 / Handler 内部类 | bindService 未解绑 | Receiver 未注销 |
| Android 14 收紧 | 后台启动 | FGS 类型化 | 隐式广播 / RECEIVER_NOT_EXPORTED |

**稳定性架构师视角**：三个组件的稳定性问题是**高度耦合的**——Activity 启动 Service，Service 发送 Broadcast，Broadcast 启动 Activity（受限）。**理解一个组件必须理解另外两个**。

## 九、跨系列引用矩阵

> **本节目的**：把 9 篇正文中所有 inline 跨系列引用汇总到一张矩阵，**便于读者从"外部视角"反查**。每条引用都已在正文章节末尾以 blockquote 形式落地，**此处只做索引，不重复解释**。

| 序号 | 源文章 | 跨系列目标 | 章节定位 | 说明 |
|------|--------|-----------|---------|------|
| R01 | S01 §2.1 | [Activity A01 全景](../Activity/01_Activity_Overview.md) | §2.1 | 四大组件在系统中的位置 |
| R02 | S01 §2.1 | [Broadcast B01 全景](../Broadcast/B01_Broadcast_Overview.md) | §2.1 | Broadcast 在四大组件中的位置 |
| R03 | S01 §2.1 | [ContentProvider C01 全景](../ContentProvider/C01_ContentProvider_Overview.md) | §2.1 | ContentProvider 在四大组件中的位置 |
| R04 | S02 §2.3 | [Activity A02 启动流程源码深潜](../Activity/02_Activity_Start_SourceCode.md) | §2.1 | startService 与 startActivity 共用 AMS 调度入口 |
| R05 | S03 §2.3 | Binder 系列（路径待定：Linux_Kernel/Binder/） | — | bindService 走跨进程 Binder |
| R06 | S04 §3.5 | Window 系列（路径待定：Android_Framework/Window/） | — | FGS 通知在 NotificationManagerService |
| R07 | S05 §3.6 | [Process 04 应用进程首生](../Process/04-应用进程首生-fork到ActivityThread.md) | §1.2 | WorkManager 涉及进程优先级 |
| R08 | S06 §3.6 | Binder 系列（路径待定：Linux_Kernel/Binder/） | — | 死亡通知是 Binder 框架能力 |
| R09 | S07 §3.5 | [Activity A07 启动 ANR](../Activity/07_Activity_Launch_ANR.md) | §2.1 | ANR 整体机制，Service 是子类 |
| R10 | S07 §3.5 | [Broadcast B08 广播 ANR 全景](../Broadcast/B08_Broadcast_ANR_Landscape.md) | §3.3 | ANR 检测 AnrHelper 强化 |
| R11 | S08 §3.6 | [Process 04 应用进程首生](../Process/04-应用进程首生-fork到ActivityThread.md) | §1.2 | onTrimMemory 与进程优先级 |
| R12 | S08 §3.6 | [Activity A09 内存治理](../Activity/09_Activity_Memory_Governance.md) | §1 | 内存治理，onTrimMemory 回调 |
| R13 | S09 §3.4 | [Activity A09 内存治理](../Activity/09_Activity_Memory_Governance.md) | §1 | 内存治理与 Service 上限 |
| R14 | S09 §3.4 | [Process 04 应用进程首生](../Process/04-应用进程首生-fork到ActivityThread.md) | §1.2 | 进程上限与 Service 数量 |
| R15 | S09 §3.4 | [ContentProvider C04 跨进程通信](../ContentProvider/C04_ContentProvider_CrossProcess.md) | §3.1 | 跨进程 Binder 限制 |

> **路径待定说明**：Binder 系列目标目录 `Linux_Kernel/Binder/` 与 Window 系列目标目录 `Android_Framework/Window/` 暂未发布，对应 3 条引用（R05 / R06 / R08）在正文中以"路径待定"形式标记，待对应系列文章发布后回填具体路径。

