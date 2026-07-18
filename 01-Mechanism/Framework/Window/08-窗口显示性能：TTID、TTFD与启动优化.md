# 08-窗口显示性能：TTID、TTFD 与启动优化

## 1. 从窗口视角看应用启动

### 1.1 启动的本质：创建 Window 并上屏第一帧

用户点击 Launcher 图标到看见 App 界面——这段时间里系统在做什么？从窗口视角看，**应用启动的本质就是创建一个 Window 并将其第一帧渲染到屏幕上**。

Activity 启动的完整路径中，窗口相关环节占据了关键路径的绝大部分耗时：

```
用户点击 → startActivity Intent 发出
    → AMS 处理 Intent → fork 进程（冷启动）
        → Application.onCreate()
            → Activity.onCreate() → setContentView()
                → Activity.onResume()
                    → WindowManager.addView() → ViewRootImpl.setView()
                        → WMS.addWindow() → 创建 WindowState
                            → WMS.relayoutWindow() → 创建 Surface
                                → ViewRootImpl.performTraversals()
                                    → measure → layout → draw
                                        → SurfaceFlinger 合成 → 屏幕显示第一帧
                                            → "Displayed" 日志打印 ← TTID 结束点
```

**从窗口系统的角度，启动耗时可以分解为三段：**

| 阶段 | 时间范围 | 窗口系统操作 | 典型耗时 |
|:---|:---|:---|:---|
| **进程准备阶段** | Intent → Application.onCreate 完成 | 无窗口操作，但阻塞了后续 addWindow | 200-3000ms |
| **窗口创建阶段** | addView → Surface 创建完成 | addWindow + openInputChannel + relayoutWindow + createSurface | 10-50ms |
| **首帧绘制阶段** | performTraversals → 第一帧提交 | measure + layout + draw + SurfaceFlinger 合成 | 16-500ms |

### 1.2 冷启动、温启动、热启动的窗口差异

三种启动模式在窗口层面的差异直接决定了用户感知的等待时间：

```
┌─────────────────────────────────────────────────────────────────────────┐
│  冷启动 (Cold Start)                                                     │
│  进程不存在 → fork → Application.onCreate → Activity.onCreate            │
│  → addWindow → createSurface → measure/layout/draw → 第一帧上屏         │
│                                                                         │
│  窗口路径：无进程 → 无 Window → 创建 Window → 创建 Surface → 首帧绘制   │
│  全链路耗时：500ms - 5s+                                                │
│  ANR 风险：★★★★★ （最长的 FocusedWindow 空窗期）                       │
├─────────────────────────────────────────────────────────────────────────┤
│  温启动 (Warm Start)                                                     │
│  进程存在但 Activity 已销毁 → Activity.onCreate → addWindow → 首帧绘制  │
│                                                                         │
│  窗口路径：进程存在 → 无 Window → 创建 Window → 创建 Surface → 首帧绘制│
│  全链路耗时：200ms - 2s                                                 │
│  ANR 风险：★★★☆☆ （跳过进程创建，但仍需 addWindow）                    │
├─────────────────────────────────────────────────────────────────────────┤
│  热启动 (Hot Start)                                                      │
│  进程存在且 Activity 在后台 → Activity.onResume → 窗口已存在            │
│                                                                         │
│  窗口路径：Window 已存在 → Surface 已存在 → 仅需重绘                    │
│  全链路耗时：50-200ms                                                   │
│  ANR 风险：★☆☆☆☆ （Window 和 InputChannel 都已就绪）                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 启动慢与 Input ANR 的因果链

启动速度不仅关乎用户体验，更直接关联到稳定性。如 [07-WMS 与 Input 焦点管理](07-WMS与Input焦点管理.md) 中分析的，Activity 切换时存在一个焦点空窗期：

```
AMS: setFocusedApplication(新 Activity)    ← FocusedApplication 已设置
         │
         │  ← 焦点空窗期：有 FocusedApp 无 FocusedWindow
         │     此时 InputDispatcher 等待 FocusedWindow 出现
         │     如果用户在此期间触摸/按键 → 5 秒后 ANR
         │
WMS: addWindow(新 Activity 窗口) → updateFocusedWindowLocked()
    → InputMonitor.setInputFocusLw()
         ↓
InputDispatcher: setFocusedWindow(新窗口)  ← FocusedWindow 就绪
```

**焦点空窗期 ≈ TTID 的核心耗时。** TTID 越长，焦点空窗期越长，Input ANR 的概率越高。

> **稳定性架构师视角：** 冷启动 TTID > 5s 时，如果用户在等待期间按了返回键或任何 Key 事件，**100% 会触发 "no focused window" ANR**。因为 InputDispatcher 的 `mNoFocusedWindowTimeoutTime` 默认就是 5s。这不是概率问题——只要用户按键了，ANR 必然发生。线上数据表明，冷启动 ANR 占 Input ANR 总量的 15-25%。

---

## 2. TTID（Time To Initial Display）— 首帧显示时间

### 2.1 定义

TTID（Time To Initial Display）是 Android 系统定义的"首帧显示时间"指标：**从 `startActivity` Intent 发出，到窗口的第一帧被绘制完成并提交到 SurfaceFlinger 的时间**。

TTID 是由系统自动检测的——不需要 App 做任何操作。当 WMS 检测到 Activity 的窗口完成首帧绘制时，会自动在 logcat 中输出 `Displayed` 日志。

### 2.2 检测机制源码链

TTID 的检测链路从 `ActivityRecord` 开始，经过 `WindowState` 的绘制状态检测，最终由 `ActivityMetricsLogger` 记录：

```
ActivityRecord.onWindowsDrawn()
    ↓
ActivityRecord.reportLaunchTimeLocked()
    ↓
ActivityMetricsLogger.notifyActivityLaunched()
    ↓
logcat: "Displayed com.example.app/.MainActivity: +Xms"
```

**Step 1: WindowState 报告绘制完成**

当 App 完成首帧绘制后，通过 `finishDrawingWindow()` 通知 WMS：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java
boolean finishDrawing(SurfaceControl.Transaction
        postDrawTransaction, int
        
        
        
         
         
         
         
         
         syncSeqId) {
    // App 端 ViewRootImpl.reportDrawFinished() 调用到这里
    // 标记窗口绘制完成
    if (mOrientationChanging) {
        mOrientationChanging = false;
    }
    // 通知 WindowToken（ActivityRecord）窗口已绘制
    mWinAnimator.finishDrawingLocked(postDrawTransaction);
    return mToken.onWindowDrawn(this);
}
```

**Step 2: ActivityRecord 检测所有窗口是否已绘制**

```java
// frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java
void onWindowsDrawn(long
        
         
         
         
          
          
          
          
          
          timestamp) {
    // 所有窗口都已绘制完成
    mDrawn = true;

    // 计算启动耗时并报告
    final TransitionInfoSnapshot info = mTaskSupervisor
            .getActivityMetricsLogger().notifyWindowsDrawn(this, timestamp);

    // 触发 logcat "Displayed" 日志
    final long
    
     
     
     
      
      
      
      
      
       curTime = SystemClock.uptimeMillis();
    // "Displayed com.example.app/.MainActivity: +1234ms"
    reportLaunchTimeLocked(curTime);
}
```

**Step 3: reportLaunchTimeLocked 计算并打印 TTID**

```java
// frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java
private void reportLaunchTimeLocked(final long curTime) {
    final long thisTime = curTime - mDisplayedTime;
    final long totalTime = mLaunchStartTime != 0
            ? (curTime - mLaunchStartTime) : thisTime;

    // 打印到 logcat
    // TAG = "ActivityTaskManager"
    // "Displayed com.example.app/.MainActivity: +1234ms (total +1567ms)"
    StringBuilder sb = new StringBuilder(128);
    sb.append("Displayed ");
    sb.append(shortComponentName);
    sb.append(": +");
    TimeUtils.formatDuration(thisTime, sb);
    if (totalTime != thisTime) {
        sb.append(" (total +");
        TimeUtils.formatDuration(totalTime, sb);
        sb.append(")");
    }
    Log.i(TAG, sb.toString());
}
```

> **稳定性架构师视角：** `mLaunchStartTime` 的起点是 `ActivityStarter.startActivityInner()` 调用时的 `SystemClock.uptimeMillis()`。终点是 `onWindowsDrawn()` 被触发时的时间。两个时间点之差就是 TTID。注意 `uptimeMillis()` 不受系统时钟调整影响，确保了测量的准确性。

### 2.3 TTID 的关键里程碑时间线

```
T0: startActivity Intent 发出
│   ActivityStarter.startActivityInner()
│   mLaunchStartTime = SystemClock.uptimeMillis()
│
T1: 进程 fork 完成（仅冷启动）
│   Process.start() → Zygote fork
│   耗时：50-200ms
│
T2: Application.onCreate() 完成
│   ActivityThread.handleBindApplication()
│   → Application.onCreate()
│   耗时：100-3000ms（取决于 SDK 初始化数量）
│
T3: Activity.onCreate() 完成
│   ActivityThread.handleLaunchActivity()
│   → Activity.onCreate() → setContentView()
│   耗时：50-500ms（取决于布局复杂度）
│
T4: Activity.onResume() → addView()
│   ActivityThread.handleResumeActivity()
│   → WindowManager.addView()
│   → ViewRootImpl.setView()
│   → WMS.addWindow() → 创建 WindowState + InputChannel
│   耗时：5-30ms
│
T5: relayoutWindow → Surface 创建
│   ViewRootImpl.performTraversals()
│   → WMS.relayoutWindow()
│   → createSurfaceLocked()
│   耗时：5-15ms
│
T6: measure → layout → draw → 首帧提交
│   performMeasure() + performLayout() + performDraw()
│   → Surface.unlockCanvasAndPost()
│   → SurfaceFlinger 合成
│   耗时：16-200ms
│
T7: "Displayed" 日志打印   ← TTID = T7 - T0
│   ActivityRecord.onWindowsDrawn()
│   → reportLaunchTimeLocked()
│
│   TTID = T1 + T2 + T3 + T4 + T5 + T6
```

### 2.4 如何测量 TTID

**方法 1：adb shell am start -W**

```bash
$ adb shell am start -W -n com.example.app/.MainActivity
Starting: Intent { cmp=com.example.app/.MainActivity }
Status: ok
LaunchState: COLD
Activity: com.example.app/.MainActivity
ThisTime: 1234      ← 当前 Activity 的 TTID（ms）
TotalTime: 1567     ← 包含上一个 Activity pause 的总时间（ms）
WaitTime: 1589      ← AMS 端的总等待时间（ms）
```

`TotalTime` 对应 `reportLaunchTimeLocked()` 中的 `totalTime`，本质上就是 TTID。

**方法 2：logcat 过滤 "Displayed"**

```bash
$ adb logcat -s ActivityTaskManager:I | grep "Displayed"
ActivityTaskManager: Displayed com.example.app/.MainActivity: +1234ms
```

**方法 3：Perfetto / Systrace**

在 Perfetto 中搜索 `android.app.startup` slice，可以看到完整的启动阶段分解。

> **稳定性架构师视角：** `am start -W` 返回的 `TotalTime` 是最简单的 TTID 测量方式，但它只能用于开发环境。线上监控需要通过 `ActivityMetricsLogger` 的 hook 或 Perfetto 的 `android.app.startup` trace 获取。Android Vitals 面板也会汇报 TTID 分布。

---

## 3. TTFD（Time To Full Display）— 完整显示时间

### 3.1 定义

TTFD（Time To Full Display）是 Android 系统定义的"完整显示时间"指标：**从 `startActivity` Intent 发出，到 App 主动调用 `Activity.reportFullyDrawn()` 的时间**。

与 TTID 的关键区别：

- **TTID 是系统自动检测的**：WMS 检测到首帧绘制完成即记录
- **TTFD 是 App 主动上报的**：App 需要在数据加载完成、真实内容渲染后，显式调用 `reportFullyDrawn()`

### 3.2 典型场景

```
T0: startActivity
         │
         │  ... 进程创建、Application 初始化、Activity 创建 ...
         │
T_TTID:  首帧上屏 → "Displayed +Xms"
         │  此时屏幕显示的是：
         │  ┌───────────────────┐
         │  │  ████████████████ │ ← 骨架屏 / Skeleton
         │  │  ████████████████ │
         │  │  ████████████████ │
         │  │  ████████████████ │
         │  │   Loading...      │
         │  └───────────────────┘
         │
         │  ... 网络请求 / 数据库查询 / 异步数据加载 ...
         │
T_TTFD:  数据加载完成 → App 调用 reportFullyDrawn()
         │  → "Fully drawn +Yms"
         │  此时屏幕显示的是：
         │  ┌───────────────────┐
         │  │  用户头像  用户名  │ ← 真实内容
         │  │  ──────────────── │
         │  │  推荐商品 1        │
         │  │  推荐商品 2        │
         │  │  推荐商品 3        │
         │  └───────────────────┘
```

### 3.3 源码链

**App 端调用入口：**

```java
// frameworks/base/core/java/android/app/Activity.java
public void reportFullyDrawn() {
    if (mDoReportFullyDrawn) {
        mDoReportFullyDrawn = false;
        try {
            // 通过 Binder 通知 AMS/WMS
            ActivityTaskManager.getService().activityFullyDrawn(
                    mToken, mRestoredFromBundle);
        } catch (RemoteException e) {
            // ignore
        }
    }
}
```

**system_server 端处理：**

```java
// frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java
void reportFullyDrawnLocked(boolean
        
         
         
         
          
          
          
          
          
          restoredFromBundle) {
    final long curTime = SystemClock.uptimeMillis();
    if (mFullyDrawnStartTime != 0) {
        final long thisTime = curTime - mFullyDrawnStartTime;

        // 打印 "Fully drawn" 日志
        // "Fully drawn com.example.app/.MainActivity: +2345ms"
        StringBuilder sb = new StringBuilder(128);
        sb.append("Fully drawn ");
        sb.append(shortComponentName);
        sb.append(": +");
        TimeUtils.formatDuration(thisTime, sb);
        Log.i(TAG, sb.toString());

        // 通知 ActivityMetricsLogger
        mTaskSupervisor.getActivityMetricsLogger()
                .logAppTransitionReportedDrawn(this, restoredFromBundle);
    }
}
```

### 3.4 被忽视的 TTFD

**大多数 App 从未调用 `reportFullyDrawn()`。** 这意味着 TTFD 指标对这些 App 是未知的——系统无法度量用户从看到"Loading..."到看到真实内容的时间。

这是一个严重的监控盲区：

| 情况 | TTID | TTFD | 用户实际体验 |
|:---|:---|:---|:---|
| App 调用了 reportFullyDrawn | 800ms | 2500ms | 看到骨架屏 800ms + 等数据 1700ms |
| App 未调用 reportFullyDrawn | 800ms | **未知** | 看到骨架屏 800ms + 等数据 ?ms |
| 首帧即完整内容（简单页面） | 800ms | ≈ 800ms | 800ms 直接看到完整内容 |

> **稳定性架构师视角：** 建议在所有关键页面的 Activity 中添加 `reportFullyDrawn()` 调用。最佳实践是在 RecyclerView 或列表的首屏数据渲染完成后调用。不调用 `reportFullyDrawn()` 意味着放弃了对用户真实等待时间的度量能力，也让 Google Play Console 的 Android Vitals 面板缺失 TTFD 数据。

---

## 4. TTID 与 TTFD 的对比与量化

### 4.1 对比表

| 维度 | TTID（Time To Initial Display） | TTFD（Time To Full Display） |
|:---|:---|:---|
| **定义** | 从 startActivity 到首帧上屏 | 从 startActivity 到 App 报告内容完全就绪 |
| **触发方式** | 系统自动检测（WindowState 绘制完成） | App 主动调用 `Activity.reportFullyDrawn()` |
| **包含阶段** | 进程创建 + Application init + Activity init + addWindow + 首帧绘制 | TTID 的全部阶段 + 异步数据加载 + 真实内容渲染 |
| **logcat 关键字** | `Displayed com.example.app/.XxxActivity: +Xms` | `Fully drawn com.example.app/.XxxActivity: +Yms` |
| **adb 命令** | `adb shell am start -W`（返回 TotalTime） | 无直接命令，需 logcat 过滤 |
| **Perfetto 指标** | `reportFullyDrawn` slice（起始）+ `Displayed` 事件 | `reportFullyDrawn` slice（完整） |
| **Android Vitals** | Startup time (initial display) | Startup time (full display) |
| **是否必然存在** | 是，系统自动记录 | 否，需 App 主动调用 |
| **衡量对象** | 窗口系统的响应速度 | App 的数据加载+渲染完整度 |
| **稳定性关联** | TTID 过长 → 焦点空窗期过长 → Input ANR | TTFD 过长 → 用户看到空白/骨架屏时间过久 → 体验差 |

### 4.2 时间线对比图

```
时间轴 ──────────────────────────────────────────────────────────────→

    T0             T1               T2                T3
    │              │                │                 │
    │  进程创建 +   │  addWindow +   │  数据加载 +    │
    │  App/Activity │  首帧绘制      │  真实内容渲染   │
    │  初始化       │                │                 │
    │              │                │                 │
    ├──────────────┤                │                 │
    │              │                │                 │
    │←─────── TTID ─────────→│     │                 │
    │              │                │                 │
    │←──────────── TTFD ──────────────────────→│     │
    │              │                │                 │

    ┌──────────────┬────────────────┬─────────────────┐
    │  白屏/启动窗口│  骨架屏/占位   │  真实内容        │
    │  (Starting   │  (首帧内容)    │  (数据加载完成)  │
    │   Window)    │                │                  │
    └──────────────┴────────────────┴─────────────────┘
                   ↑                ↑
              TTID 结束点       TTFD 结束点
```

### 4.3 测量工具总览

| 工具 | 可测量指标 | 使用场景 | 精度 |
|:---|:---|:---|:---|
| `adb shell am start -W` | TTID（TotalTime） | 开发阶段快速测量 | ms 级 |
| `adb logcat -s ActivityTaskManager:I` | TTID + TTFD | 开发/测试阶段 | ms 级 |
| Perfetto `android.app.startup` | TTID + TTFD + 阶段分解 | 性能分析 | μs 级 |
| Android Vitals (Play Console) | TTID + TTFD 分布（P50/P90/P99） | 线上监控 | 聚合数据 |
| 自定义埋点（`SystemClock.uptimeMillis()`） | TTID/TTFD + 自定义阶段 | 线上精细化监控 | ms 级 |

### 4.4 稳定性量化关系

```
TTID 与 ANR 风险的量化关系：

TTID < 500ms  → ANR 风险极低（焦点空窗期 < 500ms，用户几乎无法触发 5s 超时）
TTID 1-2s     → ANR 风险低（用户需在 3-4s 后按键才会 ANR，概率 < 1%）
TTID 2-4s     → ANR 风险中（用户在 1-3s 后按键即可 ANR，概率 1-5%）
TTID 4-5s     → ANR 风险高（任何按键几乎都会 ANR，概率 5-15%）
TTID > 5s     → ANR 必然发生（如果用户在等待期间有任何 Key 事件）

公式：ANR 概率 ≈ P(用户在 [5s - TTID] 时间窗内按键)
```

> **稳定性架构师视角：** TTID 和 TTFD 是"启动 ANR 风险"的核心量化指标。TTID 直接决定焦点空窗期长度，TTFD 决定用户可能因不耐烦而反复操作（触发更多 Input 事件）的概率。治理启动 ANR 的本质就是缩短 TTID。

---

## 5. Starting Window（Splash Screen）机制

### 5.1 为什么需要 Starting Window

冷启动时，从 `startActivity` Intent 发出到首帧上屏，可能经历 1-5 秒。如果这段时间屏幕没有任何变化，用户体验极差——"点了没反应"。更危险的是，**没有窗口就没有 InputChannel，InputDispatcher 没有焦点窗口**，用户的任何按键都会导致 ANR。

Starting Window（启动窗口）解决了这两个问题：

1. **视觉反馈**：在真实 Activity 窗口就绪之前，立即显示一个占位窗口（通常是 App 的主题背景色或 Splash Screen）
2. **焦点占位**：Starting Window **拥有 InputChannel**，可以接收 Input 事件，缩短了"无焦点窗口"的危险时间窗

### 5.2 Android 12+ SplashScreen API

Android 12 引入了系统级的 `SplashScreen` API，统一了启动窗口的行为：

```
Android 12 之前：
  Starting Window = 简单的 Theme 背景色
  App 可以通过 windowDisablePreview 禁用 → 无启动窗口 → 长时间黑屏

Android 12+：
  Starting Window = 系统强制的 SplashScreen
  包含 App Icon + 品牌色背景 + 可选的动画图标
  App 无法禁用（只能自定义样式）
```

### 5.3 Starting Window 的创建时机与源码

Starting Window 的创建发生在 AMS 处理 `startActivity` 的过程中，**早于 App 进程的任何操作**：

```
AMS.startActivityInner()
    → ActivityRecord.showStartingWindow()
        → StartingSurfaceController.showStartingWindow()
            → 创建 Starting Window（TYPE_APPLICATION_STARTING）
                → WMS.addWindow() → 创建 WindowState
                    → openInputChannel() → 注册到 InputDispatcher
                        → InputDispatcher 获得了一个可聚焦的窗口！
```

核心源码：

```java
// frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java
void showStartingWindow(ActivityRecord prev, boolean newTask,
        boolean taskSwitch, boolean startActivity,
        ActivityRecord sourceRecord) {
    // 仅在冷启动或温启动时创建 Starting Window
    if (mStartingData != null) {
        return;  // 已有 Starting Window
    }

    final StartingSurfaceController.StartingSurface surface =
            mWmService.mStartingSurfaceController
                    .showStartingWindow(this, prev, newTask, taskSwitch,
                            sourceRecord);

    if (surface != null) {
        mStartingSurface = surface;
    }
}
```

```java
// frameworks/base/services/core/java/com/android/server/wm/StartingSurfaceController.java
StartingSurface showStartingWindow(ActivityRecord target,
        ActivityRecord prev, boolean newTask,
        boolean taskSwitch, ActivityRecord sourceRecord) {

    // 决定 Starting Window 的类型
    if (shouldShowSplashScreen(target)) {
        // Android 12+：使用 SplashScreen
        mStartingData = new SplashScreenStartingData(
                mService, target, theme, compatInfo);
    } else if (shouldShowSnapshot(target)) {
        // 使用 Task 快照（温启动）
        mStartingData = new SnapshotStartingData(
                mService, target, taskSnapshot);
    }

    // 在 App 进程创建之前就添加 Starting Window
    target.addStartingWindow(mStartingData);
    return surface;
}
```

> 源码路径：
> - `frameworks/base/services/core/java/com/android/server/wm/StartingSurfaceController.java`
> - `frameworks/base/services/core/java/com/android/server/wm/SplashScreenStartingData.java`
> - `frameworks/base/services/core/java/com/android/server/wm/SnapshotStartingData.java`

### 5.4 Starting Window 的 InputChannel

关键点：**Starting Window 是一个真正的 Window，拥有完整的 InputChannel。**

```java
// Starting Window 的创建最终走到 WMS.addWindow()
// 窗口类型为 TYPE_APPLICATION_STARTING (3)
// addWindow 过程中会调用：
win.openInputChannel(outInputChannel);
// → InputDispatcher 注册该窗口
// → 如果 Starting Window 获得焦点，InputDispatcher 的焦点空窗期结束
```

这意味着 Starting Window 可以：
1. 接收 Key 事件（如 BACK 键）
2. 接收 Touch 事件（虽然通常不处理）
3. **作为 FocusedWindow 存在**，防止 InputDispatcher 进入 "no focused window" 等待状态

### 5.5 Starting Window → 真实 Activity Window 的切换

当真实 Activity 的窗口完成首帧绘制后，Starting Window 被移除，真实窗口接管显示：

```
T0: Starting Window 显示（拥有焦点 + InputChannel）
         │
         │  用户看到启动画面（SplashScreen / 主题背景）
         │  InputDispatcher 焦点 = Starting Window
         │  → 用户按键不会 ANR（有焦点窗口）
         │
T1: 真实 Activity Window addWindow() 完成
         │
T2: 真实 Activity Window 首帧绘制完成
         │
T3: 窗口切换：
         │  ActivityRecord.onFirstWindowDrawn()
         │    → removeStartingWindow()
         │      → WMS.removeWindow(Starting Window)
         │    → updateFocusedWindowLocked()
         │      → 焦点切换到真实 Activity Window
         │
T4: 用户看到真实 Activity 内容
```

```java
// frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java
void onFirstWindowDrawn(WindowState win) {
    // 真实窗口首帧绘制完成
    // 移除 Starting Window
    removeStartingWindow();

    // 更新焦点
    if (mWmService.updateFocusedWindowLocked(
            UPDATE_FOCUS_WILL_ASSIGN_LAYERS, false)) {
        mWmService.mInputMonitor.setInputFocusLw(
                mWmService.mRoot.getTopFocusedDisplayContent().mCurrentFocus,
                false);
    }
}
```

### 5.6 Starting Window 对稳定性的关键作用

```
无 Starting Window 时的焦点时间线：
──────────────────────────────────────────────────────
  T0                                T_TTID
  │←── FocusedWindow = null ────────→│
  │    5 秒内按键 → 必然 ANR          │
  │                                  │ FocusedWindow = 真实窗口
──────────────────────────────────────────────────────

有 Starting Window 时的焦点时间线：
──────────────────────────────────────────────────────
  T0    T_SW                        T_TTID
  │←──→│←── FocusedWindow ──────────→│
  │null │    = Starting Window       │ FocusedWindow = 真实窗口
  │     │    按键不会 ANR             │
  │50ms │                            │
──────────────────────────────────────────────────────
```

Starting Window 的焦点占位将"无焦点窗口"的危险时间从 `TTID 全长`（可能 1-5 秒）缩短到 `Starting Window 创建时间`（通常 50-100ms）。**这是冷启动 ANR 最有效的系统级缓解机制。**

> **稳定性架构师视角：** 如果 App 在 AndroidManifest 中设置了 `android:windowDisablePreview="true"` 禁用了 Starting Window，就主动放弃了焦点占位保护，冷启动 ANR 率会显著升高。Android 12+ 系统强制显示 SplashScreen 的设计决策，很大程度上就是为了解决这个问题。如果线上 ANR 数据显示冷启动 "no focused window" ANR 占比高，首先检查是否禁用了 Starting Window。

---

## 6. 启动性能优化最佳实践与实战案例

### 6.1 优化策略全景

从窗口系统的视角，启动优化的核心目标就是**缩短 TTID**（减少焦点空窗期→降低 ANR 风险）和**缩短 TTFD**（减少用户等待真实内容的时间→改善用户体验）。

```
TTID 组成分解与优化策略：

┌──────────────────────────────────────────────────────────┐
│  T0 → T1: 进程创建                                       │
│  优化：减少冷启动（预热进程、保活策略）                   │
│  效果：直接减少 200-500ms                                │
├──────────────────────────────────────────────────────────┤
│  T1 → T2: Application.onCreate()                         │
│  优化：SDK 懒初始化、ContentProvider 延迟加载             │
│  效果：这是最大的优化空间，可减少 500-3000ms             │
├──────────────────────────────────────────────────────────┤
│  T2 → T3: Activity.onCreate() + setContentView()         │
│  优化：View 层级扁平化、ViewStub 延迟加载                │
│  效果：减少 50-300ms                                     │
├──────────────────────────────────────────────────────────┤
│  T3 → T4: addWindow + relayoutWindow                     │
│  优化：减少 WMS 锁竞争（系统侧优化）                    │
│  效果：减少 5-30ms（App 侧无法直接优化）                 │
├──────────────────────────────────────────────────────────┤
│  T4 → T5: measure + layout + draw（首帧）                │
│  优化：首帧只渲染骨架屏、减少首帧 View 数量              │
│  效果：减少 16-200ms                                     │
└──────────────────────────────────────────────────────────┘
```

### 6.2 策略一：Application.onCreate 瘦身

**问题：** `Application.onCreate()` 是冷启动中最大的耗时来源。大型 App 通常在此阶段同步初始化 10-20 个 SDK（推送、统计、广告、Crash 上报、网络框架等），每个 SDK 初始化耗时 50-500ms，累计可达 2-5 秒。

**窗口影响：** `Application.onCreate()` 完成之前，`Activity.onCreate()` 无法执行 → `addView()` 无法调用 → 没有窗口 → 没有 InputChannel → 焦点空窗期持续。

**优化方案：**

```java
// 优化前：同步初始化所有 SDK
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        PushSDK.init(this);           // 200ms
        AnalyticsSDK.init(this);      // 150ms
        AdSDK.init(this);             // 300ms
        CrashSDK.init(this);          // 100ms
        NetworkSDK.init(this);        // 180ms
        ImageSDK.init(this);          // 120ms
        // ... 总计 1050ms
    }
}

// 优化后：仅同步初始化必要 SDK，其余延迟到首帧后
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        CrashSDK.init(this);          // 100ms — 必须立即初始化
        // 其余 SDK 延迟初始化
        postFirstFrameInit();
    }

    private void postFirstFrameInit() {
        // 在首帧绘制后的空闲时段初始化
        Looper.myQueue().addIdleHandler(() -> {
            PushSDK.init(this);
            AnalyticsSDK.init(this);
            AdSDK.init(this);
            NetworkSDK.init(this);
            ImageSDK.init(this);
            return false;  // 只执行一次
        });
    }
}
```

**TTID 改善：** Application.onCreate 从 1050ms → 100ms，直接减少 950ms。

### 6.3 策略二：ContentProvider 延迟初始化

**问题：** 许多第三方库通过 `ContentProvider.onCreate()` 实现"无侵入式"自动初始化（如 Firebase、WorkManager、LeakCanary）。所有 ContentProvider 的 `onCreate()` 在 `Application.onCreate()` **之前**执行，且是同步阻塞的。

```
进程启动 → installContentProviders() → 所有 ContentProvider.onCreate()
    → Application.onCreate()
    → Activity.onCreate()
    → ... 窗口创建
```

**优化方案：** 使用 App Startup 库合并 ContentProvider 初始化，或延迟非关键库的初始化：

```xml
<!-- AndroidManifest.xml -->
<!-- 禁用自动初始化的 ContentProvider -->
<provider
    android:name="com.example.sdk.SdkInitProvider"
    android:authorities="${applicationId}.sdk-init"
    tools:node="remove" />
```

### 6.4 策略三：View 层级扁平化

**问题：** `setContentView()` 中 inflate 的布局复杂度直接影响 `measure/layout/draw` 的耗时。嵌套层级每增加一层，measure 的递归深度增加一层，耗时近似线性增长。

**窗口影响：** 首帧的 `performTraversals()` 耗时 = measure + layout + draw。View 数量越多、嵌套越深，首帧耗时越长 → TTID 越大。

```
优化前：8 层嵌套，120 个 View
  └── FrameLayout
       └── LinearLayout
            └── RelativeLayout
                 └── ScrollView
                      └── LinearLayout
                           └── ... 更多嵌套
首帧 measure/layout/draw: 180ms

优化后：3 层嵌套，40 个 View（使用 ConstraintLayout 扁平化）
  └── ConstraintLayout
       ├── ImageView
       ├── TextView
       └── RecyclerView
首帧 measure/layout/draw: 45ms
```

### 6.5 策略四：异步数据加载（改善 TTFD）

**问题：** 如果在 `Activity.onCreate()` 中同步加载数据（网络请求/数据库查询），整个操作会阻塞在首帧之前 → TTID 包含了数据加载时间。

**优化方案：** 首帧只渲染骨架屏/占位内容（改善 TTID），数据加载完成后更新真实内容并调用 `reportFullyDrawn()`（改善 TTFD）。

```java
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // 首帧：显示骨架屏（TTID 只包含骨架屏渲染时间）
        showSkeleton();

        // 异步加载数据
        viewModel.loadData().observe(this, data -> {
            hideSkeleton();
            bindData(data);
            // 数据渲染完成，报告 TTFD
            reportFullyDrawn();
        });
    }
}
```

### 6.6 策略五：预创建与预热

**问题：** 冷启动的主要耗时在进程创建。如果能将冷启动转化为温启动或热启动，TTID 可以大幅缩短。

| 预热策略 | 实现方式 | TTID 改善 | 适用场景 |
|:---|:---|:---|:---|
| 进程预创建 | 启动时预 fork 进程，不创建 Activity | 减少 200-500ms（跳过 fork） | 核心页面的目标进程 |
| Activity 预创建 | 提前 create Activity 但不 resume | 减少 50-300ms（跳过 onCreate） | 确定性跳转路径 |
| Fragment 预加载 | 提前 inflate Fragment 的 View 树 | 减少 50-150ms（跳过 inflate） | Tab 页预加载 |
| 数据预加载 | 在上一个页面就开始加载目标页面的数据 | 改善 TTFD | 可预测的用户路径 |

### 6.7 各策略与 TTID/TTFD 的映射

| 优化策略 | 优化目标 | TTID 改善 | TTFD 改善 | 稳定性改善 |
|:---|:---|:---|:---|:---|
| Application.onCreate 瘦身 | 进程启动阶段 | ★★★★★ | ★★★★★ | 焦点空窗期大幅缩短 |
| ContentProvider 延迟初始化 | 进程启动阶段 | ★★★★☆ | ★★★★☆ | 减少 Binder 阻塞 |
| View 层级扁平化 | 首帧绘制阶段 | ★★★☆☆ | ★★☆☆☆ | 减少 performTraversals 耗时 |
| 异步数据加载 | 数据加载阶段 | ★★★★☆ | ★★★★★ | TTID 不包含数据加载时间 |
| 预创建/预热 | 进程准备阶段 | ★★★★★ | ★★★☆☆ | 冷启动→温启动 |
| 确保 Starting Window 未被禁用 | 焦点占位 | ☆☆☆☆☆ | ☆☆☆☆☆ | ★★★★★ 防止焦点空窗 ANR |

### 6.8 实战案例：冷启动从 3.5s 优化到 800ms

**现象**

某电商 App 线上数据显示：
- 冷启动 TTID P50 = 3.5s，P90 = 5.2s
- 冷启动 Input ANR 率 = 1.5%
- ANR 类型：100% 为 "Waiting because no window has focus but there is a focused application"

**分析**

**Step 1：Perfetto 启动阶段分解**

使用 Perfetto 抓取冷启动 trace，分解各阶段耗时：

```
阶段分解（P50 值）：
┌──────────────────────────────────────────────────────┐
│ 进程 fork                              │  180ms      │
├──────────────────────────────────────────────────────┤
│ ContentProvider.onCreate() (共 8 个)    │  520ms      │
├──────────────────────────────────────────────────────┤
│ Application.onCreate()                  │  1400ms     │
│   ├── PushSDK.init()                    │    320ms    │
│   ├── AnalyticsSDK.init()              │    180ms    │
│   ├── AdSDK.init()                     │    280ms    │
│   ├── MapSDK.init()                    │    250ms    │
│   ├── IMSDK.init()                     │    200ms    │
│   └── 其他 10 个 SDK                   │    170ms    │
├──────────────────────────────────────────────────────┤
│ Activity.onCreate() + setContentView()  │  480ms      │
│   └── XML inflate (嵌套 8 层, 150 View) │    350ms    │
├──────────────────────────────────────────────────────┤
│ addWindow + relayoutWindow              │   25ms      │
├──────────────────────────────────────────────────────┤
│ measure + layout + draw                 │  380ms      │
│   └── 首帧渲染 150 个 View              │    320ms    │
├──────────────────────────────────────────────────────┤
│ 总 TTID                                │  2985ms ≈ 3s│
└──────────────────────────────────────────────────────┘
```

**Step 2：ANR 关联分析**

```
TTID ≈ 3s → 焦点空窗期 ≈ 3s（Starting Window 在 100ms 后就绪）
实际焦点空窗期 ≈ 100ms（Starting Window 提供了焦点占位）

但为什么 ANR 率 = 1.5%？

检查 ANR trace：
Input dispatching timed out (Waiting because no window has focus
    but there is a focused application that will eventually add a window.)

进一步分析发现：该 App 在 AndroidManifest 中设置了
    android:windowDisablePreview="true"
→ 禁用了 Starting Window
→ 整个 TTID 期间没有焦点窗口
→ TTID P90 = 5.2s > 5s
→ P90 用户如果按键 → 必然 ANR
```

**根因**

两个核心问题：

1. **Application.onCreate 耗时 1400ms**：15 个 SDK 同步初始化
2. **Starting Window 被禁用**：整个 TTID 期间无焦点窗口
3. **布局嵌套 8 层、150 个 View**：首帧绘制耗时 380ms
4. **ContentProvider 同步初始化 520ms**：8 个第三方库通过 ContentProvider 自动初始化

**修复方案**

| 优化项 | 修复措施 | TTID 减少 |
|:---|:---|:---|
| Application.onCreate | 仅同步初始化 CrashSDK + NetworkSDK（必须），其余全部 IdleHandler 延迟 | -1200ms |
| ContentProvider | 使用 App Startup 合并为 1 个 ContentProvider，非关键库延迟初始化 | -400ms |
| View 层级 | ConstraintLayout 扁平化：8 层→3 层，150 View→60 View | -200ms |
| 首帧内容 | 首帧只渲染骨架屏（20 个简单 View），数据加载后更新 | -280ms |
| Starting Window | 移除 `windowDisablePreview="true"`，启用系统 SplashScreen | 0ms（但消除 ANR 根因） |

**优化后数据**

```
优化后阶段分解：
┌──────────────────────────────────────────────────────┐
│ 进程 fork                              │  180ms      │
├──────────────────────────────────────────────────────┤
│ ContentProvider.onCreate() (合并为 1 个) │  80ms       │
├──────────────────────────────────────────────────────┤
│ Application.onCreate()                  │  200ms      │
│   ├── CrashSDK.init()                  │    100ms    │
│   └── NetworkSDK.init()               │    100ms    │
├──────────────────────────────────────────────────────┤
│ Activity.onCreate() + setContentView()  │  150ms      │
│   └── XML inflate (3 层, 20 View 骨架屏)│    80ms     │
├──────────────────────────────────────────────────────┤
│ addWindow + relayoutWindow              │   25ms      │
├──────────────────────────────────────────────────────┤
│ measure + layout + draw                 │   60ms      │
│   └── 首帧渲染 20 个 View 骨架屏        │    45ms     │
├──────────────────────────────────────────────────────┤
│ 总 TTID                                │  695ms ≈ 0.7s│
└──────────────────────────────────────────────────────┘

TTFD（数据加载完成）: 1.8s（网络请求 + 真实内容渲染）
```

**效果对比：**

| 指标 | 优化前 | 优化后 | 改善 |
|:---|:---|:---|:---|
| TTID P50 | 3.5s | 0.7s | **-80%** |
| TTID P90 | 5.2s | 1.1s | **-79%** |
| 冷启动 ANR 率 | 1.5% | 0.05% | **-97%** |
| Starting Window | 禁用 | 启用（SplashScreen） | 焦点空窗期从 TTID 全长降为 80ms |

> **稳定性架构师视角：** 这个案例的核心教训是——**TTID 优化的最大收益不是用户体验改善，而是 ANR 率下降。** 将 TTID 从 3.5s 降到 0.7s，ANR 率从 1.5% 降到 0.05%。同时启用 Starting Window 作为"保险"——即使优化后 TTID 偶尔波动，Starting Window 的焦点占位也能防止 ANR。永远不要禁用 Starting Window。

---

## 总结

从窗口视角审视应用启动性能，以下 5 条 Takeaway 是排查和治理启动问题时需要记住的：

1. **TTID = 焦点空窗期**。TTID 越长，InputDispatcher 等待焦点窗口的时间越长，用户触发 "no focused window" ANR 的概率越高。TTID > 5s 时任何 Key 事件必然 ANR。治理冷启动 ANR 的本质就是缩短 TTID。

2. **Application.onCreate 是 TTID 的最大瓶颈**。大型 App 的 `Application.onCreate()` 可能占 TTID 的 40-70%。SDK 懒初始化是投入产出比最高的优化手段——只同步初始化 Crash 和网络框架，其余全部延迟到首帧后。

3. **Starting Window 是系统级 ANR 保险**。Starting Window 拥有 InputChannel，能在 50-100ms 内就绪并接管焦点，将焦点空窗期从"TTID 全长"缩短到"Starting Window 创建时间"。永远不要设置 `windowDisablePreview="true"`，Android 12+ 的系统 SplashScreen 正是为此设计。

4. **TTID 和 TTFD 是两个不同维度的指标**。TTID 衡量系统响应速度（首帧上屏），TTFD 衡量内容就绪速度（App 调用 reportFullyDrawn）。优化策略不同：TTID 靠减少初始化+扁平化布局，TTFD 靠异步数据加载+骨架屏。所有关键页面都应调用 `reportFullyDrawn()` 以获得 TTFD 数据。

5. **启动优化的排查路径是：Perfetto 分解 → 定位瓶颈阶段 → 针对性优化。** 不要盲目优化——先用 Perfetto 的 `android.app.startup` slice 分解各阶段耗时，找到占比最大的阶段（通常是 Application.onCreate），再针对性施策。

**排查路径速查：**

```
冷启动慢？
  → adb shell am start -W → 获取 TotalTime（TTID）
  → Perfetto android.app.startup → 分解各阶段耗时
  → 定位瓶颈：Application.onCreate? Activity.onCreate? 首帧绘制?

冷启动 ANR？
  → 检查 ANR 类型：是否为 "no focused window"
  → 检查 Starting Window：是否被 windowDisablePreview 禁用
  → 检查 TTID：是否 > 5s（P90/P99）
  → 优先启用 Starting Window + 缩短 TTID

TTFD 过长？
  → 检查是否调用了 reportFullyDrawn()
  → logcat 过滤 "Fully drawn" 获取 TTFD
  → 优化数据加载（异步化、预加载、缓存）
```

---

## 附录：核心源码路径索引

| 文件名 | 完整路径 | 说明 |
|:---|:---|:---|
| `ActivityRecord.java` | `frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java` | 启动时间检测核心：`onWindowsDrawn()`、`reportLaunchTimeLocked()`、`reportFullyDrawnLocked()` |
| `ActivityMetricsLogger.java` | `frameworks/base/services/core/java/com/android/server/wm/ActivityMetricsLogger.java` | 启动指标记录：TTID/TTFD 的统计与上报 |
| `WindowState.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | 窗口绘制完成检测：`finishDrawing()` |
| `Activity.java` | `frameworks/base/core/java/android/app/Activity.java` | App 端 API：`reportFullyDrawn()` |
| `StartingSurfaceController.java` | `frameworks/base/services/core/java/com/android/server/wm/StartingSurfaceController.java` | Starting Window 创建控制器 |
| `SplashScreenStartingData.java` | `frameworks/base/services/core/java/com/android/server/wm/SplashScreenStartingData.java` | Android 12+ SplashScreen 数据 |
| `SnapshotStartingData.java` | `frameworks/base/services/core/java/com/android/server/wm/SnapshotStartingData.java` | Task 快照型启动窗口数据 |
| `ViewRootImpl.java` | `frameworks/base/core/java/android/view/ViewRootImpl.java` | App 端窗口核心：`performTraversals()`、`reportDrawFinished()` |
| `WindowManagerService.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | WMS 主入口：`addWindow()`、`relayoutWindow()` |
| `WindowManagerGlobal.java` | `frameworks/base/core/java/android/view/WindowManagerGlobal.java` | App 端窗口管理：`addView()` |
| `InputMonitor.java` | `frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java` | WMS→InputDispatcher 焦点同步 |
| `InputDispatcher.cpp` | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` | 焦点窗口等待与 ANR 检测 |
| `ActivityStarter.java` | `frameworks/base/services/core/java/com/android/server/wm/ActivityStarter.java` | Activity 启动入口：`startActivityInner()` 设置 `mLaunchStartTime` |

---

下一篇 [09-Window 稳定性风险全景](09-Window稳定性风险全景.md) 将系统梳理 Window 系统的全类型稳定性问题——BadTokenException、WindowLeaked、黑屏、焦点丢失 ANR、Surface 泄漏等，建立从"问题现象"到"根因定位"的速查体系。
