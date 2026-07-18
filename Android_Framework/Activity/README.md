# Activity 系列导读

> **作者角色**：Android 稳定性架构师
> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
> **写作规范**：[PROMPT-技术系列文章写作指南-v4.md](../../../PROMPT-技术系列文章写作指南-v4.md)
> **本系列起始**：2026-07-18
> **本系列规划文档**：[三系列重写规划-2026-07-18.md](../三系列重写规划-2026-07-18.md)

---

## 一、为什么要写这个系列

Activity 是 Android 四大组件中**唯一具备完整 UI 生命周期**的组件。从稳定性视角看：

- **占线上 ANR 比例最高**：Google I/O 历年数据 + 国内大厂稳定性报告均显示，"启动 ANR + 跳转 ANR" 合计占 ANR 总量的 35-50%（剩余为 Broadcast ANR、Service ANR、Input ANR、System Server ANR）。
- **进程模型的"前台代表"**：一个应用前台 Activity 的生死直接决定该进程优先级（OomAdjuster 的 top-app 判定、ProcessList 的 cached/empty 判定），理解 Activity 调度就理解了 Android 进程回收策略。
- **横切其他组件的入口**：Service / Broadcast / ContentProvider 启动的常见父调用都是 `Context.startActivity()`，理解 Activity 启动流程就理解了一半的"组件启动链"。

本系列的目标：让稳定性架构师**能在 30 分钟内**把任意一个"Activity 相关线上问题"定位到具体的源码文件、阈值常量、调用栈。

## 二、系列设计思路

### 2.1 架构师思维链

```
[定位]   A01 · Activity 全景        → 它是什么？与谁协作？
   ↓
[边界]   A02 · 启动流程源码深潜     → 它和 AMS/WMS/Input 怎么配合？
   ↓
[机制]   A03-A05 · 核心机制三件套
            生命周期 / 启动模式 / Intent 解析
   ↓
[风险]   A07 · 启动 ANR 全景        → 什么场景会触发？
   ↓
[横切]   A06 · ConfigChange / A08 · 黑白屏卡顿
   ↓
[治理]   A09 · 内存治理             → 怎么查、怎么防？
```

### 2.2 依赖关系图

```
A01 全景 (总览篇)
  │
  ▼
A02 启动流程 (核心机制)
  │
  ├──→ A03 生命周期        (基于 A02 启动链路的回调机制)
  ├──→ A04 启动模式        (基于 A02 startActivity 的 Task 管理)
  ├──→ A05 Intent 解析     (基于 A02 隐式启动的 PMS 解析)
  │
  ▼
A06 ConfigChange (横切)
  │
  ▼
A07 启动 ANR (风险)
  │
  ▼
A08 黑白屏 (横切)
  │
  ▼
A09 内存治理 (治理)
```

### 2.3 跨系列引用矩阵

| 本篇 | 引用其他系列 | 引用章节 | 引用原因 | 链接有效性最后核查 |
|------|-------------|---------|---------|-------------------|
| A01 | AMS 总览 | — | ActivityManagerService 是本系列的主调度 | 2026-07-18 |
| A02 | Process | 04-应用进程首生 | zygote fork 出 ActivityThread 的链路 | 2026-07-18 |
| A02 | AmCommand | 01-am 命令全景 | `am start` 调用的就是 A02 链路 | 2026-07-18 |
| A03 | Input | 待定 | Activity 焦点变化触发 InputDispatcher 焦点切换 | 2026-07-18 |
| A04 | Window | 待定 | Task 在 WMS 端的 TaskFragment 映射 | 2026-07-18 |
| A05 | PMS | 待定 | IntentFilter 解析在 PMS 端 | 2026-07-18 |
| A07 | ANR_Detection | 待定 | ANR 检测与 Activity 启动 ANR 的关系 | 2026-07-18 |
| A08 | Window | 待定 | 启动窗口（StartingWindow）与 WMS 关系 | 2026-07-18 |
| A09 | MM_v2 | 12-内存稳定性风险全景 | Activity 泄漏与 ART 堆的关系 | 2026-07-18 |

### 2.4 与其他系列的边界声明

- **与 Service 系列的边界**：Service 启动、bindService、onStartCommand 不在本系列展开；只在本系列 A02 中简述"Activity 启动 Service 的父调用"作为完整性兜底。
- **与 Broadcast 系列的边界**：Broadcast 接收器作为 Activity 内部类的场景不展开；只在本系列 A03 生命周期中提到"Activity.onReceive 不属于生命周期方法"。
- **与 Process 系列的边界**：zygote fork 不在本系列展开，引用 Process 04 即可。
- **与 Window 系列的边界**：Activity 在 WMS 端的 Window 创建、Surface 分配不展开；只在本系列 A02 提到"启动完成 → 创建 Window"这一桥接点。

## 三、每篇文章的章节规划

| 篇号 | 标题 | 角色 | 核心源码路径（基线 android-17.0.0_r1） | 稳定性关联 |
|------|------|------|--------------------------------------|----------|
| A01 | Activity 全景：四大组件的"前台门面" | 总览篇 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`<br>`frameworks/base/core/java/android/app/Activity.java` | 全局性 |
| A02 | 启动流程源码深潜：launcher → AMS → ActivityThread | 核心机制 | `ActivityManagerService.java`<br>`frameworks/base/services/core/java/com/android/server/wm/ActivityTaskManagerService.java`<br>`frameworks/base/services/core/java/com/android/server/wm/ActivityStarter.java`<br>`frameworks/base/core/java/android/app/ActivityThread.java`<br>`frameworks/base/core/java/android/app/Instrumentation.java` | 启动 ANR / 启动慢 |
| A03 | 生命周期：onCreate → onDestroy 全链路 | 核心机制 | `Instrumentation.java`<br>`Activity.java` (`performCreate`/`performStart`/`performResume`/...)<br>`ActivityThread.handleLaunchActivity()` / `handleResumeActivity()` / `handleDestroyActivity()` | 生命周期错乱 / 状态丢失 |
| A04 | 启动模式与 Task 管理 | 核心机制 | `ActivityStarter.java`<br>`frameworks/base/services/core/java/com/android/server/wm/Task.java`<br>`frameworks/base/services/core/java/com/android/server/wm/TaskFragment.java`<br>`frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java` | Task 错乱 / 启动模式误解 |
| A05 | Intent 与组件匹配 | 核心机制 | `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java`<br>`frameworks/base/core/java/android/content/IntentResolver.java`<br>`frameworks/base/core/java/android/content/IntentFilter.java`<br>`frameworks/base/services/core/java/com/android/server/pm/ComponentResolver.java` | 隐式启动失败 / IntentFilter 漂移 |
| A06 | ConfigurationChange 与 Activity 重建 | 横切专题 | `ActivityThread.handleConfigurationChanged()`<br>`frameworks/base/services/core/java/com/android/server/wm/WindowProcessController.java`<br>`frameworks/base/core/java/android/content/res/ResourcesManager.java` | 重建丢失状态 / 横竖屏闪退 |
| A07 | Activity 启动 ANR 全景 | 风险地图 | `ActivityManagerService.java` (`inputDispatchingTimedOut` / `activityStartTimeout`)<br>`frameworks/base/services/core/java/com/android/server/am/ActiveServices.java` (前台服务启动时限)<br>`frameworks/base/services/core/java/com/android/server/wm/ActivityTaskManagerService.java` | 启动 ANR |
| A08 | 跳转卡顿与黑白屏 | 横切专题 | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java`<br>`frameworks/base/core/java/android/window/SplashScreen.java` (API 31+)<br>`frameworks/base/core/java/android/view/WindowManager.java` | 跳转慢 / 闪屏白屏 |
| A09 | Activity 内存治理 | 诊断治理 | `ActivityThread.mActivities`<br>`frameworks/base/core/java/androidx/lifecycle/ViewModelStore.java`<br>`Activity.java` (`mConfigChangeFlags`) | 内存泄漏 / OOM |

## 四、阅读建议

### 4.1 时间有限优先阅读（30 分钟路径）

如果你只想快速建立"能定位线上 Activity 问题"的最小能力：

1. **A01 全景**（8 分钟）— 建立协作模型
2. **A02 启动流程**（15 分钟）— 启动链路源码地图
3. **A07 启动 ANR**（7 分钟）— 风险图 + 阈值表

### 4.2 系统学习推荐顺序

```
A01 → A02 → A03 → A04 → A05 → A06 → A07 → A08 → A09
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
| A01 总览篇 | 风险地图简版（3 类）+ 无实战案例 | §9.1 合法破例：总览篇 | 仅 A01 | 否 |
| A06 横切专题 | 3 张图（规则 4-6 张） | §9.1 合法破例：横切专题型 | 仅 A06 | 否 |
| A08 横切专题 | 3 张图（规则 4-6 张） | §9.1 合法破例：横切专题型 | 仅 A08 | 否 |
| A09 诊断治理 | 章节重排为"风险→工具→案例" | §9.1 合法破例：诊断工具型 | 仅 A09 | 否 |

## 六、质量基线（本系列特征）

### 6.1 关键阈值常量（本系列高频引用）

| 常量名 | 路径 | 值 | 说明 |
|--------|------|----|------|
| `ACTIVITY_STARTING_STATE_CHANGE_TIMEOUT` | ActivityManagerService.java | 5s | Activity onCreate/onStart/onResume 整体时限 |
| `BROADCAST_FG_TIMEOUT` | ActivityManagerService.java | 10s | 前台广播 onReceive 时限 |
| `BROADCAST_BG_TIMEOUT` | ActivityManagerService.java | 60s | 后台广播 onReceive 时限 |
| `SERVICE_TIMEOUT` | ActiveServices.java | 20s | 前台 Service 启动/onStartCommand 时限 |
| `SERVICE_BACKGROUND_TIMEOUT` | ActiveServices.java | 200s | 后台 Service 启动时限 |
| `CONTENT_PROVIDER_PUBLISH_TIMEOUT` | ActivityManagerService.java | 10s | ContentProvider publish 时限 |
| `KEY_DISPATCHING_TIMEOUT` | ActivityManagerService.java | 5s | 输入事件分发时限（被 ANR 误判为"启动 ANR"的常见原因） |

> **稳定性架构师视角**：Activity 启动 ANR 不是单一阈值，是**"启动链路上任意一环超时 → 上报到 AMS → 触发 ANR"** 的复合结果。表里 7 个阈值任意一个超时都会触发 ANR，但根因可能完全不同——这是 A07 的核心论点。

### 6.2 跨版本基线（多版本矩阵）

| 主题 | Android 13 (T, API 33) | Android 14 (U, API 34) | Android 15 (V, API 35) | Android 16 (Baklava, API 36) | Android 17 (API 37) |
|------|------------------------|------------------------|------------------------|------------------------------|---------------------|
| 隐式 Intent 启动 | 警告 | 限制 | 强制 `Intent.setPackage()` | 强制 | 强制 |
| Foreground Service 类型化 | 引入 | 强制声明 | 强化 | 强化 | 强化 |
| SplashScreen | 可选 | 强制 | 强化 | 强化 | 强化 |
| onBackPressed | 默认回退 | 启用预测式返回 | 强化 | 强化 | 强化 |
| 后台 Activity 启动 | 限制 | 限制 | 收紧 | 收紧 | 收紧 |

> **本系列基线**：以 **android-17.0.0_r1** 为主线，差异点在文章中显式标注（如"// API 35+ 变化点"）。

## 七、版本与基线声明

- **AOSP 基线**：`android-17.0.0_r1`（API 37）
- **Linux 内核基线**：`android17-6.18` LTS（**AOSP 17 官方 GKI 内核**）
- **生效日期**：2026-07-18
- **基线升级规则**：按 [PROMPT v4 §8.3](../../PROMPT-技术系列文章写作指南-v4.md) 升级流程执行
- **路径对账**：每篇附录 B 必填，标注【已校对/待确认】+ 校对来源

## 八、2026-07-18 M5.5 校验后状态

### 8.1 跨系列引用回灌

本系列 9 篇正文完成 **20 条跨系列 inline 引用**回灌（v4 §6.1 规范 `[系列名-文章名](相对路径) §章节号`）：

| 引用方 | 被引用 | 引用原因 |
|--------|--------|---------|
| A01 | S01/B01/C01 §2.1 | 四大组件协作图 |
| A02 | Process 04 / AmCommand 01 / C02 | 启动流程 / zygote fork / 冷启动时序 |
| A03 | B05 | onReceive 与 Activity 生命周期无关 |
| A04 | S03 / Window | 启动模式 vs Service 跨进程 / TaskFragment |
| A05 | PMS / C04 | IntentFilter 解析 / 隐式 Intent + 跨 App CP |
| A06 | B07 | AOSP 14+ 收紧是系列化策略 |
| A07 | S04 / B08 / C07 | FGS 类型化 / AnrHelper / ContentProvider ANR 10s |
| A08 | Window | 启动窗口与 WMS 关系 |
| A09 | MM_v2 12 / S03 / B02 / C03 | 内存治理 / 泄漏类比 |

### 8.2 案例 ID 锚点回灌

本系列 9 篇正文完成 **13 个 `**【CASE-ACT-NN】**` 锚点**回灌（标题匹配精度 100%）：

- A02 → CASE-ACT-01（启动 ANR）/ CASE-ACT-02（冷启动白屏）
- A03 → CASE-ACT-03（横竖屏状态丢失）/ CASE-ACT-04（onPause 慢）
- A04 → CASE-ACT-05（singleTask 配错）/ CASE-ACT-06（推送 SDK 抢 Task）
- A05 → CASE-ACT-07（AOSP 11+ 隐式启动失败）/ CASE-ACT-08（IntentFilter mimeType 错配）
- A06 → CASE-ACT-09（横竖屏 UI 错乱）/ CASE-ACT-10（configChanges 漏字段）
- A08 → CASE-ACT-11（SplashScreen 闪烁）
- A09 → CASE-ACT-12（单例持 Activity 泄漏）/ CASE-ACT-13（Handler 内部类持 Activity）

### 8.3 图表密度破例

本系列 3 篇（A02 / A04 / A05）图表密度 < 3 张（实际各 2 张），**接受为 v4 §9 破例**——理由是这些文章以"源码/路径对账"为主，**表格信息密度更高**（60-130 表格行/篇）。破例仅本系列 3 篇，不传染。决策记录见 [Reference/版本基线.md §二](../Reference/版本基线.md) 2026-07-18 行。
