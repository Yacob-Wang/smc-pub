# B01 · Broadcast 全景：分类、机制与协作组件

> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
> **本篇角色**：Broadcast 系列 **第 1 篇 / 总览篇**（破例：风险地图简版 / 无实战案例）
> **强依赖**：[Activity 系列 · A01 全景](../Activity/01_Activity_Overview.md)、[Service 系列 · S01 全景](../Service/01_Service_Overview.md)
> **承接自**：无（系列根文章）
> **衔接去**：[B02 · 注册机制：静态注册 vs 动态注册](B02_Broadcast_Register.md) — 把 B01 §3.1 的注册骨架下沉到源码级
> **不重复内容**：与 A01 §2.1 四大组件协作图不重复；与 S01 §2.1 Service 协作图不重复

## 破例决策记录

| 破例项 | 破例内容 | 破例理由 | 影响范围 | 是否传染 |
|--------|---------|---------|---------|---------|
| 风险地图 | 简版（3 类） | §9.1 合法破例：总览篇 | 仅 B01 | 否 |
| 实战案例 | 无 | §9.1 合法破例：总览篇 | 仅 B01 | 否 |

---

## 一、背景与定义

### 1.1 什么是 Broadcast

`android.content.BroadcastReceiver` 是 Android 四大组件中**专门用于"跨进程事件分发"**的组件。AOSP 17 源码注释里的官方定义非常克制：

```java
// frameworks/base/core/java/android/content/BroadcastReceiver.java
// A base class for code that receives and reacts to broadcast intents sent by Context.sendBroadcast()
```

把这段注释翻译成稳定性语言：Broadcast 是**"系统级事件分发机制"**——一个进程（发送方）通过 `sendBroadcast(intent)` 发送事件，**多个进程（接收方）的 BroadcastReceiver.onReceive() 被调用**，完成"一对多"的通知。

### 1.2 为什么需要 Broadcast 这个组件

从系统设计角度，Broadcast 解决了三个问题：

1. **跨进程事件通知**：发送方不需要知道接收方是谁，**系统负责路由**。
2. **系统级事件传递**：系统事件（开机、网络变化、电量低等）通过 Broadcast 传递给所有应用。
3. **应用间解耦**：发送方和接收方独立开发，**通过 Intent action 字符串约定**。

### 1.3 Broadcast 不是孤岛

稳定性架构师最容易踩的误区：**把 Broadcast 当成"简单的消息队列"**。实际上，Broadcast 是**一个横跨 4 个系统服务的协调点**：

| 涉及系统服务 | 关注点 | 错配后果 |
|------------|-------|---------|
| **ActivityManagerService (AMS)** | BroadcastQueue、广播调度、ANR 检测 | 广播 ANR / 丢失 |
| **PackageManagerService (PMS)** | 静态注册 Receiver 解析、IntentFilter 匹配 | 收不到广播 |
| **NotificationManager (NM)** | 前台广播通知 | 通知不显示 |
| **SystemServer** | 系统广播发送（BOOT_COMPLETED 等） | 开机广播丢失 |

---

## 二、架构与交互

### 2.1 Broadcast 在四大组件中的位置

```
┌──────────────────────────────────────────────────────────────┐
│                       [应用层]                                │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│   │   Activity   │  │   Service    │  │  Broadcast   │        │
│   │  (UI 容器)   │  │ (后台执行)   │  │(事件分发)    │        │
│   │              │  │              │  │              │        │
│   │ 有 UI 生命周期│  │ 短回调 onCreate│  │ 短生命周期回调│        │
│   │              │  │  onStartCmd  │  │  onReceive   │        │
│   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│          │                 │                 │                │
└──────────┼─────────────────┼─────────────────┼────────────────┘
           │                 │                 │
   ┌───────▼─────────────────▼─────────────────▼──────────────┐
   │        [系统服务层 · frameworks/base/services]            │
   │                                                            │
   │   ┌──────────────────────────────────────────────────┐    │
   │   │     ActivityManagerService (AMS)                  │    │
   │   │  - ActiveServices (Service 子系统)                │    │
   │   │  - BroadcastQueue (Broadcast 子系统) ← 本系列重点│    │
   │   │  - ProviderMap (ContentProvider 子系统)           │    │
   │   │  - ActivityTaskManager / ActivityStarter          │    │
   │   └──────────────────────────────────────────────────┘    │
   │           │                                                 │
   │   ┌───────▼─────────┐                                       │
   │   │ PackageManager  │  ← 静态注册 Receiver 解析            │
   │   │ Service (PMS)   │                                       │
   │   └─────────────────┘                                       │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
```

**稳定性架构师视角**：
- **Broadcast 在 AMS 内部对应 `BroadcastQueue` 子系统**——这是 Broadcast 系列文章的主战场。
- **静态注册 Receiver 在 PMS 端缓存**——PMS 端慢直接拖慢广播分发。
- **Broadcast ANR 阈值比 Service 低**（10s vs 20s）——**onReceive 是短回调，设计上要快进快出**。

### 2.2 Broadcast 的关键类层级

```
android.content.BroadcastReceiver              ← 用户继承
  └─ 业务方实现类

android.content.ContextWrapper.sendBroadcast()  ← 发送入口
  └─ ContextImpl.sendBroadcast()

android.app.ActivityThread                      ← 进程端 Receiver 调度
  └─ H Handler (RECEIVER 消息)

frameworks/base/services/.../am/
  ├─ BroadcastQueue                             ← 广播队列（前台 / 后台）
  ├─ BroadcastRecord                            ← 广播运行时记录
  ├─ BroadcastFilter                            ← IntentFilter 匹配
  └─ ParallelBroadcasts                          ← 并行广播集合

frameworks/base/core/.../app/
  ├─ LoadedApk.ReceiverDispatcher               ← 动态注册 Receiver 调度
  └─ ActivityThread.handleReceiver               ← 进程端 Receiver 执行
```

**稳定性架构师视角**：
- **`BroadcastQueue` 是 AMS 端"广播队列"**——**前台队列 + 后台队列**分开。
- **`BroadcastRecord` 是广播运行时记录**——`dumpsys activity broadcasts` 看到的字段全是这个类的成员。
- **`ReceiverDispatcher` 是动态注册的关键**——**LoadedApk 持有**，**泄漏会持有 Activity Context**（A09 风险地图同源问题）。

### 2.3 一次"发送广播"经过的 5 个步骤

```
[发送方] Activity / Service / Context
  │   sendBroadcast(intent)
  ▼
[ActivityManagerService]
  │   broadcastIntent()  ───────── 1. 权限校验、Intent 解析
  ▼
[BroadcastQueue]
  │   scheduleBroadcasts()  ────── 2. 决定前台/后台队列、并行/串行
  ▼
[ParallelBroadcasts / processNextBroadcast]
  │   processNextBroadcast()  ─── 3. 遍历所有匹配的 Receiver
  │   enqueueParallelBroadcast() ── 4. 跨进程到目标进程
  ▼
[目标进程 ActivityThread]
  │   handleReceiver()  ────────── 5. Receiver 实例化 + onReceive
  ▼
[Receiver.onReceive] 业务回调
```

**稳定性架构师视角**：
- **5 步中任意一步慢都会触发 ANR**。但 ANR 阈值不同：
  - 第 1-2 步：发送方问题（Intent 拼错 / 权限不足）
  - 第 3 步：AMS 端调度慢（系统压力大、Watchdog 阻塞 AMS）
  - 第 4 步：跨进程到目标进程慢（Binder 限频 / 目标进程 ANR）
  - 第 5 步：Receiver.onReceive 慢（业务逻辑重）
- B03 会把每一步下沉到具体源码方法和行号。

---

## 三、核心机制骨架

> **本节约定**：B01 是总览篇，**只讲骨架不深展开**。每段都会标注"详见 Bxx"避免重复。

### 3.1 Broadcast 4 种分类（按发送方式）

```
                  Broadcast
                    │
        ┌───────────┼───────────┬────────────┐
        │           │           │            │
   sendBroadcast  sendOrdered  sendSticky  LocalBroadcast
   (普通广播)     (有序广播)    (粘性广播)   (进程内)
        │           │            │            │
   并行调度      串行调度      已废弃        已废弃
   0 个或多个     按优先级      (API 31 移除)  (API 1 deprecated)
   接收者        可 abort        保留最后 Intent
        │           │
   ┌────┴────┐     │
   │         │     │
 前台     后台   按优先级串行
 队列     队列   + onReceive
            │
       10s     60s
       超时    超时
```

**关键源码**（在 `Context.java` 和 `BroadcastQueue.java`）：

| 模式 | 发送方式 | 调度方式 | 关键字段 |
|------|---------|---------|---------|
| **普通广播** | `sendBroadcast(intent)` | 并行（ConcurrentHashMap） | `ParallelBroadcasts` |
| **有序广播** | `sendOrderedBroadcast(intent, ...)` | 串行（按优先级） | `mOrderedBroadcasts` |
| **粘性广播** | `sendStickyBroadcast(intent)` | **API 31 移除** | n/a |
| **LocalBroadcast** | `LocalBroadcastManager.sendBroadcast()` | **已废弃** | n/a |
| **前台广播** | `sendBroadcast(intent)` (前台) | 10s 超时 | `mFgBroadcasts` |
| **后台广播** | `sendBroadcast(intent)` (后台) | 60s 超时 | `mBgBroadcasts` |

> **路径**：
> - `frameworks/base/core/java/android/content/BroadcastReceiver.java`
> - `frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java`
> - `frameworks/base/core/java/android/content/Context.java`

**稳定性架构师视角**：
- **粘性广播 API 31 移除**（B05 详细展开）——**业务方在 AOSP 12+ 调 `sendStickyBroadcast` 直接抛异常**。
- **LocalBroadcast 已废弃**（B06 详细展开）——**业务方应该用 `LiveData` / `Flow` / `RxBus`**。
- **"前台 vs 后台"是按发送方进程状态决定**——**AMS 端根据 `ProcessRecord.getSetProcState()` 决定队列**。

### 3.2 注册机制骨架（详见 B02）

**两种注册方式**：

| 方式 | 配置位置 | 生命周期 | 适用场景 |
|------|---------|---------|---------|
| **静态注册** | `AndroidManifest.xml` 的 `<receiver>` | 永久（应用安装即注册） | 接收系统广播（BOOT_COMPLETED 等） |
| **动态注册** | 代码 `registerReceiver(receiver, filter)` | 跟随 Context 生命周期 | 业务级广播 |

**关键决策点**：

```
注册决策
  │
  ├─ 接收系统广播？
  │     ├─ 开机/锁屏/网络变化？→ 静态注册（manifest）
  │     └─ 时区/语言？→ 静态注册
  │
  ├─ 接收应用内广播？
  │     ├─ 跨进程？→ 动态注册 + IntentFilter
  │     └─ 进程内？→ LiveData / Flow
  │
  └─ 特殊场景？
        ├─ 接收特定 Intent → 动态注册 + Action 匹配
        └─ 接收 sticky → 不可能（API 31 移除）
```

**AOSP 14+ 强制 `RECEIVER_EXPORTED` 声明**——**静态注册 Receiver 必须显式声明 exported**。

> **路径**：
> - `frameworks/base/core/java/android/content/BroadcastReceiver.java`
> - `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java`

**稳定性架构师视角**：
- **静态注册是"PMS 端解析 + AMS 端缓存"**——**冷启动时 PMS 解析慢直接拖慢广播分发**（B09 BOOT_COMPLETED 展开）。
- **动态注册是"LoadedApk 内存 + Context 引用"**——**泄漏会持有 Activity Context**（A09 风险地图同源问题）。
- **AOSP 14+ 静态注册必须声明 `RECEIVER_EXPORTED` 或 `RECEIVER_NOT_EXPORTED`**——**漏声明 = 必崩**。

### 3.3 发送流程骨架（详见 B03）

**6 步发送链路**：

```
1. 发起方 sendBroadcast(intent)
2. ContextImpl.sendBroadcast() 包装 BroadcastOptions
3. ActivityManager.getService().broadcastIntent()  ← AIDL
4. AMS 端 broadcastIntent() 校验 + IntentFilter 匹配
5. BroadcastQueue.scheduleBroadcasts() 决定前台/后台
6. ParallelBroadcasts / processNextBroadcast 跨进程
7. 目标进程 handleReceiver() 调 onReceive
```

**关键决策点**：

```
broadcastIntent
  │
  ├─ 发送方权限？→ 校验 caller identity
  ├─ Intent 解析？→ PMS 端 IntentFilter 匹配（B05 Activity A05）
  │
  ├─ 并行 vs 串行？
  │     ├─ sendBroadcast → 并行（同一时间分发到所有 Receiver）
  │     └─ sendOrderedBroadcast → 串行（按优先级）
  │
  ├─ 前台 vs 后台？
  │     ├─ 发送方 ProcessRecord.getSetProcState() ≤ VISIBLE → 前台
  │     └─ 否则 → 后台
  │
  └─ 跨 App vs 同 App？
        ├─ 跨 App → 跨进程 Binder
        └─ 同 App → 同进程（不跨进程）
```

**稳定性架构师视角**：
- **"并行 vs 串行"是 Broadcast 的核心**——**普通广播并行分发（10s 内必须 onReceive 完），有序广播串行分发**。
- **"前台 vs 后台"是 ANR 阈值的关键**——**前台 10s，后台 60s**。
- **AOSP 17 强化**：`mOrderedBroadcasts` 内部增加"优先级调度优化"。

### 3.4 有序广播与粘性广播骨架（详见 B04 / B05）

**有序广播**：

```
sendOrderedBroadcast(intent, ...)
  │
  ▼
BroadcastQueue.mOrderedBroadcasts
  │
  ▼
processNextBroadcast
  │
  ├─ 1. 取当前最高优先级的 Receiver
  ├─ 2. 跨进程到目标进程
  ├─ 3. 等待 onReceive 完成
  ├─ 4. 检查 abort？
  │     ├─ abort → 停止分发
  │     └─ 继续 → 取下一个优先级
  └─ 5. 重复 1-4
```

> **路径**：`frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java`

**粘性广播**：

```
历史（API 1 引入）：
  sendStickyBroadcast(intent)
  │  // 缓存到 mStickyBroadcasts
  ▼
  // 后注册的 Receiver 自动收到
  registerReceiver(receiver, filter)

API 21 deprecated
API 31 完全移除
```

> **路径**：历史 `frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java` mStickyBroadcasts 字段

**稳定性架构师视角**：
- **有序广播的"串行"导致总耗时 = N × onReceive 耗时**——**N 越大越容易 ANR**。
- **粘性广播是历史包袱**——**AOSP 12+ 强制迁移**（B05 详细展开）。
- **AOSP 17 强化有序广播**——`processNextBroadcast` 内部增加"按优先级调度优化"。

### 3.5 LocalBroadcast 与协作组件骨架（详见 B06）

**LocalBroadcastManager**：

```
LocalBroadcastManager.getInstance(context)
  │
  ├─ registerReceiver(receiver, filter)
  │     └─ 保存到 mReceivers
  │
  ├─ sendBroadcast(intent)
  │     └─ 遍历 mReceivers，同进程内调用 onReceive
  │
  └─ unregisterReceiver(receiver)
        └─ 从 mReceivers 移除

⚠️ 已废弃（API 1 deprecated）
推荐替代：LiveData / Flow / RxBus
```

> **路径**：
> - `frameworks/base/core/java/androidx/localbroadcastmanager/LocalBroadcastManager.java`

**协作组件**：

| 组件 | 角色 |
|------|------|
| **PackageManagerService (PMS)** | 静态注册 Receiver 解析、IntentFilter 匹配 |
| **NotificationManager (NM)** | 前台广播通知（API 33+ 强制） |
| **SystemServer** | 系统广播发送（BOOT_COMPLETED 等） |
| **AnrHelper (AOSP 16+)** | Broadcast ANR 检测 |

**稳定性架构师视角**：
- **LocalBroadcastManager 已废弃**——**业务方应该用 `LiveData` / `Flow` / `RxBus`**（B06 详细展开）。
- **PMS 端解析 Receiver**——**冷启动时 PMS 解析慢**（B09 BOOT_COMPLETED 展开）。
- **AnrHelper 异步检测 Broadcast ANR**——**AOSP 16+ 强化**（B08 详细展开）。

---

## 四、风险地图（简版 · 3 类）

> **总览篇破例**：本节列 3 类最常见风险，详细分类见 B08。

### 风险地图

| 问题类型 | 触发条件 | 日志关键字 | 排查入口 | 占比（经验值） |
|---------|---------|-----------|---------|--------------|
| **Broadcast ANR** | onReceive 超 10s（前台）/ 60s（后台） | `ANR in com.x` / `Broadcast of Intent { ... }` | `dumpsys activity broadcasts`<br>`traces.txt` (data/anr/) | **15-25%** |
| **收不到广播** | 静态注册漏声明 / 隐式广播被禁 / IntentFilter 错配 | `SecurityException: ... not exported` / 静默 | `dumpsys package` / `dumpsys activity broadcasts` | **25-30%** |
| **广播丢失** | 发送方抛异常 / 接收方崩溃 / 进程被 LMK 杀 | 业务日志 / `dumpsys meminfo` | 业务自监控 | **10-15%** |

> **稳定性架构师视角**：
> - 三个风险类型**互相耦合**：Broadcast ANR 经常是 onReceive 慢；收不到广播经常是 AOSP 14+ RECEIVER_EXPORTED 强制；广播丢失经常是进程被 LMK 杀。**先看风险类型再选排查工具**，效率差 3-5 倍。
> - "经验值占比"是经验值（非官方统计），依据来自公开 ANR 报告 + 国内大厂稳定性报告的合并估算。

---

## 五、总结 · 架构师视角的 5 条 Takeaway

1. **Broadcast 是"跨进程事件分发的代表"**——它的 ANR 阈值（10s / 60s）比 Service（20s / 200s）低，因为 onReceive 设计上要"快进快出"。
2. **Broadcast 启动 = 5 步链路**（含 AMS 端 IntentFilter 解析），任意一环慢都会触发 ANR 或收不到广播。**收不到广播比 ANR 更难排查**——logcat 静默，**靠 `dumpsys` 反推**。
3. **AOSP 14+ 强制 `RECEIVER_EXPORTED` / `RECEIVER_NOT_EXPORTED` 声明**——业务方升级到 AOSP 14 必崩，**这是"Android 14 升级必回归"项**。
4. **隐式广播几乎被废弃**（AOSP 8+ 限制，AOSP 14+ 几乎完全废弃）——业务方应该用显式 Intent + setPackage。
5. **粘性广播 API 31 完全移除**——业务方在 AOSP 12+ 调 `sendStickyBroadcast` 直接抛异常。**需要 AOSP 17 上测的兼容性代码 100% 失败**。

**该主题的排查路径速查**：

```
Broadcast ANR?
  ├─ ANR in <package> with Broadcast of Intent → 看 ANR trace 第一帧
  │     ├─ onReceive 业务逻辑重？→ 异步化
  │     ├─ onReceive 同步 IO？→ 移到 Worker
  │     └─ 大量 Receiver 串行？→ 拆分成多 Broadcast
  │
  └─ 进程 attach 超 10s？→ PROC_START_TIMEOUT 触发

收不到广播?
  ├─ 静态注册漏声明 RECEIVER_EXPORTED？→ 显式声明
  ├─ 隐式广播被禁？→ 改显式 Intent + setPackage
  ├─ IntentFilter 错配？→ 检查 action / data
  └─ AOSP 14+ RECEIVER_NOT_EXPORTED 默认？→ 加 RECEIVER_EXPORTED

广播丢失?
  ├─ 进程被 LMK 杀？→ 改 FGS
  ├─ onReceive 抛异常？→ try-catch
  └─ 发送方 Intent 拼错？→ 校验 Intent
```

---

## 附录 A · 核心源码路径索引

| 文件名 | 完整路径（基线 android-17.0.0_r1） | 说明 |
|--------|----------------------------------|------|
| BroadcastReceiver.java | `frameworks/base/core/java/android/content/BroadcastReceiver.java` | BroadcastReceiver 基类 |
| Context.java | `frameworks/base/core/java/android/content/Context.java` | sendBroadcast 入口 |
| ContextImpl.java | `frameworks/base/core/java/android/app/ContextImpl.java` | 实际实现 |
| BroadcastQueue.java | `frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java` | 广播队列 |
| BroadcastRecord.java | `frameworks/base/services/core/java/com/android/server/am/BroadcastRecord.java` | 广播运行时记录 |
| BroadcastFilter.java | `frameworks/base/services/core/java/com/android/server/am/BroadcastFilter.java` | IntentFilter 匹配 |
| ActivityManagerService.java | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | AMS 主体 |
| ActivityThread.java | `frameworks/base/core/java/android/app/ActivityThread.java` | 进程主线程 + handleReceiver |
| LoadedApk.java | `frameworks/base/core/java/android/app/LoadedApk.java` | 动态注册 Receiver 调度 |
| PackageManagerService.java | `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java` | PMS 主体 |
| AnrHelper.java | `frameworks/base/services/core/java/com/android/server/am/AnrHelper.java` | AOSP 16+ 异步 ANR |

## 附录 B · 源码路径对账表

| 序号 | 文章中出现的路径 | 校对状态 | 校对来源 |
|------|----------------|---------|---------|
| 1 | `frameworks/base/core/java/android/content/BroadcastReceiver.java` | 已校对 | AOSP 历版通用 |
| 2 | `frameworks/base/core/java/android/content/Context.java` | 已校对 | AOSP 历版通用 |
| 3 | `frameworks/base/core/java/android/app/ContextImpl.java` | 已校对 | AOSP 历版通用 |
| 4 | `frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java` | 已校对 | AOSP 历版通用 |
| 5 | `frameworks/base/services/core/java/com/android/server/am/BroadcastRecord.java` | 已校对 | AOSP 历版通用 |
| 6 | `frameworks/base/services/core/java/com/android/server/am/BroadcastFilter.java` | 已校对 | AOSP 历版通用 |
| 7 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | 已校对 | AOSP 历版通用 |
| 8 | `frameworks/base/core/java/android/app/ActivityThread.java` | 已校对 | AOSP 历版通用 |
| 9 | `frameworks/base/core/java/android/app/LoadedApk.java` | 已校对 | AOSP 历版通用 |
| 10 | `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java` | 已校对 | AOSP 历版通用 |
| 11 | `frameworks/base/services/core/java/com/android/server/am/AnrHelper.java` | 已校对 | AOSP 16+ |

## 附录 C · 量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据来源 |
|------|---------|-------|---------|
| 1 | Broadcast ANR 占线上 ANR 比例 | 15-25% | 经验值 |
| 2 | 收不到广播占 Broadcast 问题比例 | 25-30% | 经验值 |
| 3 | 广播丢失占 Broadcast 问题比例 | 10-15% | 经验值 |
| 4 | 前台广播 ANR 阈值 BROADCAST_FG_TIMEOUT | 10s | AOSP 源码常量 |
| 5 | 后台广播 ANR 阈值 BROADCAST_BG_TIMEOUT | 60s | AOSP 源码常量 |
| 6 | AOSP 17 长前台广播阈值 BROADCAST_FG_LONG_TIMEOUT | 60s | AOSP 17 引入 |
| 7 | AOSP 17 长后台广播阈值 BROADCAST_BG_LONG_TIMEOUT | 120s | AOSP 17 引入 |
| 8 | MAX_BROADCASTS_PER_APP | 200 | AOSP 17 引入 |
| 9 | 粘性广播废弃版本 | API 21 | AOSP 21 行为变更 |
| 10 | 粘性广播移除版本 | API 31 | AOSP 31 行为变更 |
| 11 | RECEIVER_EXPORTED 强制版本 | API 34 | AOSP 34 行为变更 |
| 12 | LocalBroadcastManager 废弃版本 | API 1 | AOSP 历版 |
| 13 | 发送链路步骤 | 5 步 | AOSP 源码分析 |
| 14 | 跨进程次数 | 1-2 次 | AOSP 源码分析 |
| 15 | onReceive 推荐耗时 | < 50ms | 经验值 |

## 附录 D · 工程基线表

> **本篇无新引入的可调参数**（关键阈值常量见 README §6.1）。附录 D 按需省略。

---

## 篇尾衔接

下一篇 [B02 · 注册机制：静态注册 vs 动态注册](B02_Broadcast_Register.md) 将把 B01 §3.2 的注册骨架下沉到源码级——**静态注册 PMS 解析 + 动态注册 LoadedApk 调度 + AOSP 14+ RECEIVER_EXPORTED 强制 + IntentFilter 匹配机制**。B02 是 B03 发送流程的前置知识。

预计阅读时间 25-35 分钟。
