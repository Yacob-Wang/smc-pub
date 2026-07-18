# Broadcast 系列导读

> **作者角色**：Android 稳定性架构师
> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
> **写作规范**：[PROMPT-技术系列文章写作指南-v4.md](../../../PROMPT-技术系列文章写作指南-v4.md)
> **本系列起始**：2026-07-18
> **本系列规划文档**：[三系列重写规划-2026-07-18.md](../三系列重写规划-2026-07-18.md)
> **依赖前序系列**：[Activity 系列](../Activity/README.md)、[Service 系列](../Service/README.md)（已发布）

---

## 一、为什么要写这个系列

Broadcast 是 Android 四大组件中**唯一专门用于"跨进程事件分发"**的组件。从稳定性视角看：

- **占线上 ANR 第三高比例**：Broadcast ANR 占 ANR 总量的 15-25%，前台 10s / 后台 60s 阈值。
- **AOSP 14+ 收紧"重灾区"**：AOSP 14 引入 `RECEIVER_NOT_EXPORTED` / `RECEIVER_EXPORTED` 强制声明，**升级到 AOSP 14 必崩**。
- **隐式广播几乎被废弃**：AOSP 8+ 开始限制隐式广播，**AOSP 14+ 几乎完全废弃**。
- **静态注册机制依赖 PMS 解析**：BOOT_COMPLETED 等系统广播涉及 PMS manifest 解析，**冷启动慢的隐藏原因**。

本系列的目标：让稳定性架构师**能在 30 分钟内**把任意一个"Broadcast 相关线上问题"定位到具体的源码文件、阈值常量、调用栈。

## 二、系列设计思路

### 2.1 架构师思维链

```
[定位]   B01 · Broadcast 全景         → 4 种分类 + 协作组件
   ↓
[边界]   B02-B03 · 注册 / 发送路径     → 静态 / 动态注册 + 发送链路
   ↓
[机制]   B04-B06 · 核心机制三件套
            有序广播 / 粘性演进 / LocalBroadcast
   ↓
[风险]   B07-B08 · 风险地图
            AOSP 14+ 收紧 / Broadcast ANR
   ↓
[治理]   B09 · 系统广播与开机广播
```

### 2.2 依赖关系图

```
B01 全景 (总览篇)
  │
  ▼
B02 注册机制 (核心机制)
  │
  ├──→ B03 发送流程     (基于 B02 注册信息)
  ├──→ B04 有序广播     (独立机制)
  ├──→ B05 粘性广播演进  (演进型)
  ├──→ B06 LocalBroadcast (横切)
  │
  ▼
B07 AOSP 14+ 后台广播限制 (风险)
  │
  ▼
B08 Broadcast ANR (风险)
  │
  ▼
B09 系统广播 (治理)
```

### 2.3 跨系列引用矩阵

| 本篇 | 引用其他系列 | 引用章节 | 引用原因 | 链接有效性最后核查 |
|------|-------------|---------|---------|-------------------|
| B01 | Activity | A01 §2.1 | 四大组件协作图 | 2026-07-18 |
| B01 | Service | S01 §2.1 | Service 协作图 | 2026-07-18 |
| B01 | ContentProvider | C01 §2.1 | 四大组件协作图 | 2026-07-18 |
| B02 | PMS（待建） | — | 静态注册在 PMS 端缓存 | 2026-07-18 |
| B02 | ContentProvider | C02 §3.6 | LoadedApk 共享模式（Receiver + Provider 共用 mReceivers / mProviders 池） | 2026-07-18 |
| B03 | Activity | A02 §3.1 | Activity 发送广播的链路 | 2026-07-18 |
| B03 | Service | S02 §3.1 | Service 发送广播的链路 | 2026-07-18 |
| B03 | ContentProvider | C03 §2.1 | 隐式广播 + 跨 App ContentProvider 共享 PMS 端 IntentFilter 解析 | 2026-07-18 |
| B04 | Activity | A04 §3.2 | 启动模式 vs 优先级（ActivityStarter 复用决策 ↔ Receiver priority 调度） | 2026-07-18 |
| B07 | Service | S04 §3.2 | Android 14+ 后台启动收紧是系列化策略 | 2026-07-18 |
| B07 | Activity | A07 §3.4 | AOSP 14+ 收紧是系列化策略（启动 ANR 5 大根因 ↔ 后台启动 Receiver 限制） | 2026-07-18 |
| B08 | ANR_Detection | 待定 | Broadcast ANR 整体机制（AOSP 16+ 合并到 AnrHelper 异步检测框架） | 2026-07-18 |
| B09 | Process | 04-应用进程首生 §6 | BOOT_COMPLETED 在 zygote fork 后的时序（attachApplicationLocked 握手之后才能下发） | 2026-07-18 |
| B09 | ContentProvider | C02 §3.5 | 冷启动时 ContentProvider 在前（ContentProvider.onCreate 早于 BootReceiver.onReceive） | 2026-07-18 |

### 2.4 与其他系列的边界声明

- **与 Activity 系列的边界**：Activity 内部动态注册 BroadcastReceiver 的场景不展开；只在本系列 B02 提到"Activity 推荐用 Lifecycle 感知"。
- **与 Service 系列的边界**：Service 内部注册 BroadcastReceiver 的场景不展开；只在本系列 B02 提到"Service 在 onDestroy 中解绑"。
- **与 Process 系列的边界**：zygote fork 不在本系列展开，引用 Process 04 即可。

## 三、每篇文章的章节规划

| 篇号 | 标题 | 角色 | 核心源码路径（基线 android-17.0.0_r1） | 稳定性关联 |
|------|------|------|--------------------------------------|----------|
| B01 | Broadcast 全景：分类、机制与协作组件 | 总览篇 | `frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java`<br>`frameworks/base/core/java/android/content/BroadcastReceiver.java` | 全局性 |
| B02 | 注册机制：静态注册 vs 动态注册 | 核心机制 | `PackageManagerService.java collectBroadcastReceivers()`<br>`LoadedApk.ReceiverDispatcher` | 收不到广播 / 静态注册失效 |
| B03 | 发送流程：sendBroadcast → BroadcastQueue → Receiver | 核心机制 | `ActivityManagerService.broadcastIntent()`<br>`BroadcastQueue.scheduleBroadcasts()` | 广播丢失 |
| B04 | 有序广播：优先级 + 串行调度 + abort | 核心机制 | `BroadcastQueue.processNextBroadcast()`<br>`BroadcastRecord.java` | 有序广播不串行 |
| B05 | 粘性广播与 Android 17 演进（演进型） | 演进型 | 历史：API 1 → API 21 deprecated → API 31 移除 | 兼容性问题 |
| B06 | LocalBroadcast 已死，进程内事件总线怎么选（横切） | 横切专题 | `LocalBroadcastManager.java` (已废弃)<br>`LiveData` / `Flow` / `RxBus` | 进程内事件分发 |
| B07 | Android 14+ 后台广播限制：RECEIVER_EXPORTED 与隐式广播收紧 | 风险地图 | `ActivityManagerService.broadcastIntent()`<br>`IntentFilter` 校验 | 收不到广播 / SecurityException |
| B08 | Broadcast ANR 全景：10s/60s 阈值与根因分类 | 风险地图 | `BroadcastQueue.mTimeoutPeriod`<br>`AnrHelper.java` | 广播 ANR |
| B09 | 系统广播与开机广播：BOOT_COMPLETED / LOCALE / 时间广播 | 诊断治理 | `SystemServer.java`<br>`Intent.ACTION_*` 常量 | 开机广播丢失 / 时区广播 |

## 四、阅读建议

### 4.1 时间有限优先阅读（30 分钟路径）

1. **B01 全景**（8 分钟）— 建立 Broadcast 协作模型
2. **B03 发送流程**（10 分钟）— 发送链路
3. **B08 Broadcast ANR**（12 分钟）— 风险图 + 阈值表

### 4.2 系统学习推荐顺序

```
B01 → B02 → B03 → B04 → B05 → B06 → B07 → B08 → B09
```

约 80-100 分钟完成全系列。建议每天 1-2 篇。

### 4.3 每篇文章的设计逻辑

```
背景（是什么、为什么）→ 架构（在哪、和谁）→ 源码（怎么转）→ 风险（哪里坏）→ 案例（怎么修）
```

## 五、破例决策记录

| 破例项 | 破例内容 | 破例理由 | 影响范围 | 是否传染 |
|--------|---------|---------|---------|---------|
| B01 总览篇 | 风险地图简版（3 类）+ 无实战案例 | §9.1 合法破例：总览篇 | 仅 B01 | 否 |
| B05 演进型 | 3 张图 + 2 张对比表（规则 4-6 张） | §9.1 合法破例：演进型 | 仅 B05 | 否 |
| B06 横切专题 | 3 张图（规则 4-6 张） | §9.1 合法破例：横切专题型 | 仅 B06 | 否 |
| B09 诊断治理 | 章节重排为"风险→工具→案例" | §9.1 合法破例：诊断工具型 | 仅 B09 | 否 |

## 六、质量基线（本系列特征）

### 6.1 关键阈值常量（本系列高频引用）

| 常量名 | 路径 | 值 | 说明 |
|--------|------|----|------|
| `BROADCAST_FG_TIMEOUT` | ActivityManagerService.java | 10s | 前台广播 onReceive 时限 |
| `BROADCAST_BG_TIMEOUT` | ActivityManagerService.java | 60s | 后台广播 onReceive 时限 |
| `BROADCAST_FG_LONG_TIMEOUT` | AOSP 17 | 60s | AOSP 17 引入的长前台广播时限 |
| `BROADCAST_BG_LONG_TIMEOUT` | AOSP 17 | 120s | AOSP 17 引入的长后台广播时限 |
| `MAX_BROADCAST_HISTORY` | BroadcastQueue.java | 50 | Broadcast 历史记录上限 |
| `MAX_BROADCASTS_PER_APP` | AOSP 17 | 200 | AOSP 17 引入的每 App 广播数上限 |

> **稳定性架构师视角**：Broadcast ANR 不是单一阈值，是**"onReceive 回调 + 跨进程分发"**的复合结果。

### 6.2 跨版本基线（多版本矩阵）

| 主题 | Android 13 (T, API 33) | Android 14 (U, API 34) | Android 15 (V, API 35) | Android 16 (API 36) | Android 17 (API 37) |
|------|------------------------|------------------------|------------------------|---------------------|---------------------|
| 隐式广播 | 限制 | 几乎废弃 | 几乎废弃 | 几乎废弃 | 废弃 |
| `RECEIVER_EXPORTED` 强制 | 引入 | 强制 | 强制 | 强制 | 强制 |
| `RECEIVER_NOT_EXPORTED` 默认 | 可选 | 默认 | 默认 | 默认 | 默认 |
| 静态注册 BOOT_COMPLETED | 可选 | 收紧 | 收紧 | 收紧 | 收紧 |
| 后台广播限制 | 限制 | 收紧 | 收紧 | 收紧 | 收紧 |
| 粘性广播 | 已移除 | 已移除 | 已移除 | 已移除 | 已移除 |
| 跨 App 广播 | 限制 | 严格限制 | 严格 | 严格 | 严格 |
| `MAX_BROADCASTS_PER_APP` | n/a | n/a | n/a | 引入 | 强化 |
| LocalBroadcastManager | 已废弃 | 已废弃 | 已废弃 | 已废弃 | 已废弃 |
| `BROADCAST_FG_LONG_TIMEOUT` | n/a | n/a | n/a | 引入 | 强化 |

> **本系列基线**：以 **android-17.0.0_r1** 为主线，差异点在文章中显式标注。

## 七、版本与基线声明

- **AOSP 基线**：`android-17.0.0_r1`（API 37）
- **Linux 内核基线**：`android17-6.18` LTS
- **生效日期**：2026-07-18
- **基线升级规则**：按 [PROMPT v4 §8.3](../../PROMPT-技术系列文章写作指南-v4.md) 升级流程执行
- **路径对账**：每篇附录 B 必填，标注【已校对/待确认】+ 校对来源

## 八、Broadcast 系列与 Activity / Service 系列的协同

| 维度 | Activity | Service | Broadcast |
|------|----------|---------|-----------|
| UI | 有完整 UI 生命周期 | 无 UI | 无 UI |
| 启动方式 | startActivity + Intent | startService / bindService | sendBroadcast + Intent |
| ANR 主阈值 | 5s (启动) | 20s (前台) / 200s (后台) | 10s (前台) / 60s (后台) |
| 跨进程能力 | 通过 Intent flag | 通过 bindService (Binder) | 通过 sendBroadcast (Binder) |
| 注册方式 | manifest declare | manifest declare | manifest declare + 动态 register |
| 死亡通知 | 无 | 有 (binderDied) | 有 (Receiver unregister) |
| 内存泄漏高发区 | 静态引用 / Handler 内部类 | bindService 未解绑 | Receiver 未注销 |
| Android 14 收紧 | 后台启动 | FGS 类型化 | RECEIVER_EXPORTED 强制 |
| 进程保活 | 无 | FGS 强 | 静态注册 BOOT_COMPLETED |

**稳定性架构师视角**：三个组件的稳定性问题是**高度耦合的**——Activity 启动 Service，Service 发送 Broadcast，Broadcast 启动 Activity（受限）。**理解一个组件必须理解另外两个**。
