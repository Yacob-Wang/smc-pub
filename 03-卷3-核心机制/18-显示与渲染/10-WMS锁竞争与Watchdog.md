# 10-WMS 锁竞争与 Watchdog

## 1. mGlobalLock（原 WMS 锁）的本质

### 1.1 从碎片化锁到统一全局锁的演进

Android 10 之前，WMS 和 AMS 各有一把自己的"大锁"：

```
Android 9 及更早版本：

┌──────────────────────┐     ┌──────────────────────┐
│  ActivityManagerService │     │  WindowManagerService  │
│                        │     │                        │
│  synchronized(this) {  │     │  synchronized(mWindowMap)│
│    // AMS 锁           │     │  {                      │
│    // 保护 Activity    │     │    // WMS 锁            │
│    // 生命周期状态     │     │    // 保护 WindowState  │
│  }                     │     │    // Surface / 焦点     │
│                        │     │  }                      │
└──────────┬─────────────┘     └──────────┬─────────────┘
           │                              │
           │  AMS 调 WMS：需先释放 AMS 锁  │
           │  再获取 WMS 锁（或反向）       │
           │                              │
           └──────── 死锁高发区 ──────────┘
```

这种"两把锁"设计带来了 Android 历史上最臭名昭著的死锁模式：

- **Thread A**：持有 AMS 锁 → 调用 WMS 方法 → 等待 mWindowMap
- **Thread B**：持有 mWindowMap → 回调 AMS 方法 → 等待 AMS 锁
- **结果**：经典 ABBA 死锁 → Watchdog 检测到 → system_server 重启

Android 10 的 `ActivityTaskManagerService`（ATMS）重构彻底改变了这一局面：**将 AMS 中 Activity 相关逻辑拆分到 ATMS，并让 ATMS 和 WMS 共享同一把锁 `mGlobalLock`。**

```java
// frameworks/base/services/core/java/com/android/server/wm/ActivityTaskManagerService.java
public class ActivityTaskManagerService extends IActivityTaskManager.Stub {
    /** 全局锁，WMS 和 ATMS 共用 */
    final WindowManagerGlobalLock mGlobalLock = new WindowManagerGlobalLock();
    // ...
}

// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
public class WindowManagerService extends IWindowManager.Stub
        implements Watchdog.Monitor, WindowManagerPolicy.WindowManagerFuncs {
    /** 指向 ATMS 的同一把锁 */
    final WindowManagerGlobalLock mGlobalLock;

    WindowManagerService(..., ActivityTaskManagerService atm, ...) {
        // 直接引用 ATMS 的锁实例
        mGlobalLock = atm.getGlobalLock();
        // ...
    }
}
```

> **稳定性架构师视角：** `WindowManagerGlobalLock` 本身是一个空类，继承自 `Object`，仅作为 `synchronized` 的监视器对象。它的意义不在实现，而在统一——从架构上消灭了 AMS↔WMS 的 ABBA 死锁可能性。这是 Android 系统稳定性演进中最重要的架构决策之一。

### 1.2 mGlobalLock 保护的核心数据

mGlobalLock 保护的数据范围极广，涵盖了 WMS 和 ATMS 的所有核心状态：

| 保护范围 | 具体数据 | 所在类 |
|---------|---------|--------|
| 窗口状态 | 所有 WindowState 的创建、修改、销毁 | `WindowState.java` |
| Activity 状态 | 所有 ActivityRecord 的生命周期状态 | `ActivityRecord.java` |
| 焦点状态 | mCurrentFocus、mFocusedApp | `DisplayContent.java` |
| Display 状态 | DisplayContent 的配置、旋转、Insets | `DisplayContent.java` |
| 窗口层级 | WindowContainer 树的结构与 Z-order | `WindowContainer.java` |
| Surface 操作 | SurfaceControl.Transaction 的构建与提交 | `WindowStateAnimator.java` |
| Task 管理 | Task 的创建、移动、删除 | `Task.java` |
| 窗口布局 | performSurfacePlacement 的全局布局计算 | `WindowSurfacePlacer.java` |

### 1.3 统一锁的代价

统一锁消除了 ABBA 死锁，但引入了新的问题——**更严重的锁竞争**：

```
Android 9:                          Android 10+:
  AMS 锁 → 保护 Activity            mGlobalLock → 保护 Activity
  WMS 锁 → 保护 Window                          + Window
                                                  + Focus
  两把锁可以并行                                   + Display
  死锁风险高                                       + Surface
                                                  + Task
                                      一把锁串行化所有操作
                                      死锁风险低，竞争加剧
```

这是一个典型的工程权衡：**用竞争（可检测、可优化）替代死锁（不可恢复、必须重启）。** 竞争导致的最坏情况是某些操作变慢（ms 级延迟），而死锁导致的最坏情况是 Watchdog 杀 system_server（用户体验灾难）。

---

## 2. mGlobalLock 的竞争者图谱

### 2.1 谁在抢这把锁

mGlobalLock 的竞争者来自 system_server 中的多个服务和线程。以下是完整的竞争者图谱：

```
                    ┌─────────────────────────────┐
                    │        mGlobalLock           │
                    │   (WindowManagerGlobalLock)  │
                    └──────────┬──────────────────┘
                               │
        ┌──────────┬──────────┼──────────┬──────────┬──────────┐
        │          │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼          ▼
   ┌─────────┐┌─────────┐┌─────────┐┌─────────┐┌─────────┐┌─────────┐
   │  ATMS   ││   WMS   ││   IMS   ││   DMS   ││ App     ││ System  │
   │         ││         ││  Bridge ││         ││ Binder  ││  UI     │
   │Activity ││ Window  ││ Focus   ││ Display ││ Calls   ││ Calls   │
   │Lifecycle││ Ops     ││ Sync    ││ Events  ││         ││         │
   └─────────┘└─────────┘└─────────┘└─────────┘└─────────┘└─────────┘
   startAct   addWindow  updateInput displayAdd addToDisp  onConfig
   finishAct  removeWin  Windows    displayRem relayout   Change
   resumeAct  relayoutWin setFocus  displayChg remove     rotation
   pauseAct   perfSurf             foldUnfold
              Placement
```

### 2.2 各竞争者的持锁操作与耗时

| 竞争者 | 持锁操作 | 调用入口 | 典型持锁耗时 | 高危场景耗时 |
|--------|---------|---------|------------|------------|
| **ATMS** | Activity 启动 | `startActivity()` → `startActivityInner()` | 2-5ms | 10-50ms（多 Task 重排） |
| **ATMS** | Activity 结束 | `finishActivity()` → `removeActivity()` | 1-3ms | 5-20ms（清理大量窗口） |
| **ATMS** | Resume/Pause | `resumeTopActivity()` / `pauseActivity()` | 1-3ms | 5-15ms（焦点切换+布局） |
| **WMS** | 添加窗口 | `addWindow()` | 1-3ms | 5-10ms（窗口数量多时） |
| **WMS** | 移除窗口 | `removeWindow()` → `removeIfPossible()` | 1-2ms | 3-8ms（Surface 销毁慢） |
| **WMS** | 重新布局 | `relayoutWindow()` | 2-5ms | 10-30ms（触发全局布局） |
| **WMS** | 全局布局 | `performSurfacePlacement()` | 3-10ms | 30-200ms（窗口多+动画） |
| **IMS Bridge** | 焦点同步 | `InputMonitor.updateInputWindowsLw()` | 1-2ms | 3-8ms（窗口多时遍历慢） |
| **DMS** | 屏幕事件 | `handleDisplayAdded/Removed/Changed()` | 2-5ms | 10-50ms（配置变更级联） |
| **App Binder** | 会话调用 | `Session.addToDisplayAsUser/relayout/remove` | 取决于内部操作 | 同上 |

### 2.3 高竞争场景分析

以下场景会导致 mGlobalLock 竞争急剧加剧：

**场景一：快速 Activity 切换**

用户在最近任务列表中快速滑动切换 App，每次切换触发：
1. 旧 Activity `pause` → 持有 mGlobalLock（更新焦点 + 布局）
2. 新 Activity `resume` → 持有 mGlobalLock（创建窗口 + 焦点切换）
3. `performSurfacePlacement` → 持有 mGlobalLock（全局布局计算）
4. 多个 App 的 `relayoutWindow` Binder 调用 → 全部等待 mGlobalLock

```
时间线：
T=0ms   Activity A pause → 获取 mGlobalLock（持有 5ms）
T=5ms   Activity B resume → 获取 mGlobalLock（持有 8ms）
T=13ms  performSurfacePlacement → 获取 mGlobalLock（持有 15ms）
T=28ms  App C relayoutWindow → 等待 mGlobalLock...
T=28ms  App D addWindow → 等待 mGlobalLock...
T=28ms  InputMonitor.updateInputWindows → 等待 mGlobalLock...
        ↑ 三个线程同时阻塞在 mGlobalLock 上
```

**场景二：分屏/多窗口操作**

分屏模式下同时存在两个前台 Activity，窗口操作翻倍：
- 两个 Activity 同时 `relayoutWindow`
- `performSurfacePlacement` 需要计算两套窗口布局
- 分屏边界拖动触发连续的 Configuration 变更

**场景三：折叠屏展开/折叠**

折叠屏状态变化触发 Display 配置变更，级联效应最严重：

```
折叠屏展开事件
  → DisplayManagerService 通知 WMS
    → 持有 mGlobalLock：更新 DisplayContent 配置
      → 触发所有窗口 Configuration 变更
        → 所有 Activity 可能销毁重建
          → 大量 removeWindow + addWindow + relayoutWindow
            → performSurfacePlacement 多次执行
              → mGlobalLock 被连续持有数百毫秒
```

---

## 3. 锁竞争导致的级联效应

mGlobalLock 竞争的危害不仅在于操作变慢，更在于**级联效应**——一个持锁过久的操作会阻塞多个下游服务，形成雪崩。

### 3.1 级联路径一：App Binder 调用阻塞 → Input ANR

这是最常见的级联路径，占 WMS 锁竞争导致的 ANR 的 60% 以上：

```
App 进程 (主线程)              system_server                  InputDispatcher
      │                            │                              │
      │ ViewRootImpl.setView()     │                              │
      │  → Session.addToDisplay    │                              │
      │     AsUser()               │                              │
      │  ────Binder IPC──────→     │                              │
      │                     Binder 线程:                           │
      │                     synchronized(mGlobalLock) {            │
      │                       // 等待 mGlobalLock...               │
      │                       // 另一个线程正在执行                  │
      │                       // performSurfacePlacement           │
      │                       // 已持有锁 50ms+                    │
      │                     }                                      │
      │  App 主线程阻塞                                            │
      │  在 Binder IPC 上                                          │
      │  ← 无法处理 Input 事件                                     │
      │                                                            │
      │                                                     InputDispatcher:
      │                                                     发送触摸事件 → App
      │                                                     等待 finishInputEvent
      │                                                     5000ms 超时...
      │                                                     → ANR!
```

**因果链详解：**

1. App 的 `ViewRootImpl.setView()` 发起 `addToDisplayAsUser()` Binder 调用
2. Binder 调用到达 system_server，尝试获取 mGlobalLock
3. 此时 mGlobalLock 被 WMS 的 `performSurfacePlacement()` 持有（正在做复杂布局计算）
4. Binder 线程等待锁 → App 主线程等待 Binder 返回 → **App 主线程被间接阻塞**
5. InputDispatcher 此时向 App 发送触摸事件，但 App 主线程卡死无法处理
6. 5000ms 后 InputDispatcher 判定 ANR

```java
// frameworks/base/services/core/java/com/android/server/wm/Session.java
@Override
public int addToDisplayAsUser(IWindow window, WindowManager.LayoutParams attrs,
        int viewVisibility, int displayId, int userId, ...) {
    // 这个调用在 Binder 线程上执行
    // 内部会 synchronized(mGlobalLock)
    return mService.addWindow(this, window, attrs, viewVisibility, displayId, userId, ...);
}
```

> **稳定性架构师视角：** 这条路径隐蔽之处在于——ANR 堆栈显示 App 主线程卡在 Binder 调用上，看起来像是 App 的问题。但根因在 system_server 中 mGlobalLock 的持有者。排查时必须同时分析 App 进程和 system_server 进程的线程栈，找到 mGlobalLock 的实际持有者。

### 3.2 级联路径二：焦点同步延迟 → 触摸穿透/丢失

```
WMS (持有 mGlobalLock)           InputMonitor            InputDispatcher
      │                              │                        │
      │ performSurfacePlacement()    │                        │
      │ (持锁 30ms+)                │                        │
      │                              │                        │
      │ ← 其他线程等待 mGlobalLock   │                        │
      │   包括 InputMonitor 的       │                        │
      │   updateInputWindowsLw()    │                        │
      │                              │                        │
      │ ... 30ms 后释放锁 ...        │                        │
      │                              │                        │
      │                         获取 mGlobalLock              │
      │                         updateInputWindowsLw()       │
      │                           → 遍历所有窗口              │
      │                           → 同步到 InputDispatcher ──→│
      │                                                       │ 收到新窗口列表
      │                                                       │ 但此前 30ms 内
      │                                                       │ 使用的是旧列表!
      │                                                       │
      │                                                       │ 旧列表中：
      │                                                       │   Window A 在 (0,0,500,500)
      │                                                       │ 新列表中：
      │                                                       │   Window A 移到 (0,500,500,1000)
      │                                                       │
      │                                                       │ 用户触摸 (250,250)
      │                                                       │ → 命中 Window A（旧位置）
      │                                                       │ → 实际上应该命中 Window B
      │                                                       │ → 触摸穿透!
```

这个路径在窗口动画期间尤其危险。窗口位置随动画持续变化，但 InputMonitor 的更新被锁竞争延迟，导致 InputDispatcher 的窗口区域与屏幕上的实际窗口位置不一致。

### 3.3 级联路径三：Activity 生命周期阻塞 → Service/Broadcast ANR

```
ATMS (等待 mGlobalLock)           App 进程                   AMS
      │                              │                        │
      │ resumeTopActivity()          │                        │
      │  → synchronized(mGlobalLock) │                        │
      │     等待中...                 │                        │
      │     (WMS 正在持锁做布局)      │                        │
      │                              │                        │
      │                              │                   BroadcastQueue:
      │                              │                   发送广播给 App
      │                              │                   等待 App 返回
      │                              │                   App 的 onReceive
      │                              │                   需要 Activity 状态
      │                              │  ← 但 Activity 的  │
      │                              │     resume 被阻塞   │
      │                              │     在 mGlobalLock  │
      │                              │                     │
      │                              │                10s 超时 → BroadcastANR!
```

**三条路径的时间预算对比：**

| 级联路径 | ANR 类型 | 超时阈值 | 锁持有多久会触发 | 影响范围 |
|---------|---------|---------|---------------|---------|
| App Binder 阻塞 | Input ANR | 5000ms | 锁持有 3000ms+ | 单个 App |
| 焦点同步延迟 | 无 ANR，但触摸异常 | 无硬性阈值 | 锁持有 16ms+ | 所有前台 App |
| Activity 生命周期阻塞 | Broadcast ANR / Service ANR | 10s / 20s | 锁持有 5000ms+ | 广播/服务关联 App |

---

## 4. Watchdog 与 WMS

### 4.1 Watchdog 是什么

Watchdog 是 system_server 的**自我监控机制**——当 system_server 内部的关键线程或关键锁出现长时间无响应时，Watchdog 主动杀死 system_server，触发 Android 系统重启（Zygote 会重新 fork system_server）。

```
Watchdog 的设计哲学：

  "与其让 system_server 成为僵尸进程（活着但不工作），
   不如杀掉重启——至少重启后系统能恢复正常。"

Watchdog 线程（每 30 秒检查一次）:
  ┌─────────────────────────────────────────────────────┐
  │  for (HandlerChecker checker : mHandlerCheckers) {  │
  │      checker.scheduleCheckLocked();                 │
  │  }                                                  │
  │  // 等待 30 秒                                       │
  │  for (HandlerChecker checker : mHandlerCheckers) {  │
  │      int state = checker.getCompletionStateLocked();│
  │      if (state == OVERDUE) {                        │
  │          // 该线程/锁超时 → 报告                      │
  │      }                                              │
  │  }                                                  │
  └─────────────────────────────────────────────────────┘
```

### 4.2 Watchdog 的两种检测机制

```java
// frameworks/base/services/core/java/com/android/server/Watchdog.java
public class Watchdog extends Thread {
    // 默认超时时间
    static final long DEFAULT_TIMEOUT = DB ? 10 * 1000 : 60 * 1000;  // 60 秒
    static final long CHECK_INTERVAL = DEFAULT_TIMEOUT / 2;           // 30 秒

    final ArrayList<HandlerChecker> mHandlerCheckers = new ArrayList<>();
    // ...
}
```

**机制一：HandlerChecker — 线程响应性检测**

Watchdog 向被监控线程的 Handler 投递一条消息，检查该消息是否在 30 秒内被处理：

```java
// frameworks/base/services/core/java/com/android/server/Watchdog.java
public final class HandlerChecker implements Runnable {
    private final Handler mHandler;
    private final ArrayList<Monitor> mMonitors = new ArrayList<>();
    private boolean mCompleted;
    private long mStartTimeMs;

    public void scheduleCheckLocked() {
        mCompleted = false;
        mStartTimeMs = SystemClock.uptimeMillis();
        // 向目标线程的 Handler 投递消息
        mHandler.postAtFrontOfQueue(this);
    }

    @Override
    public void run() {
        // 在目标线程上执行
        // 1. 先检查所有 Monitor（尝试获取锁）
        for (Monitor m : mMonitors) {
            m.monitor();  // 如果锁被占用，这里会阻塞
        }
        // 2. 标记完成
        synchronized (Watchdog.this) {
            mCompleted = true;
        }
    }
}
```

**机制二：Monitor — 锁可用性检测**

实现 `Watchdog.Monitor` 接口的服务，其 `monitor()` 方法会尝试获取该服务的核心锁。如果锁被长时间持有，`monitor()` 会阻塞 → HandlerChecker 无法完成 → Watchdog 检测到超时。

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
public class WindowManagerService extends IWindowManager.Stub
        implements Watchdog.Monitor {

    @Override
    public void monitor() {
        // Watchdog 调用此方法检测 mGlobalLock 是否可用
        synchronized (mGlobalLock) {
            // 如果能进入这里，说明锁可用 → 正常
            // 如果阻塞在这里 → mGlobalLock 被长时间持有 → Watchdog 将超时
        }
    }
}
```

### 4.3 WMS 的 Watchdog 监控链路

WMS 在初始化时将自己注册到 Watchdog：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
private WindowManagerService(...) {
    // ...
    // 注册到 Watchdog：监控 "android.display" 线程（WMS 主线程）
    Watchdog.getInstance().addMonitor(this);
    // ...
}
```

完整的检测链路：

```
Watchdog 线程 (每 30 秒一轮)
    │
    │ ① 向 "android.display" 线程 post 消息
    │    (HandlerChecker.scheduleCheckLocked)
    │
    ├─→ "android.display" 线程收到消息
    │    │
    │    │ ② 执行 HandlerChecker.run()
    │    │    → 遍历所有 Monitor
    │    │    → 调用 WMS.monitor()
    │    │    → synchronized(mGlobalLock) { }
    │    │
    │    ├─ 情况 A：mGlobalLock 可用
    │    │    → monitor() 立即返回
    │    │    → mCompleted = true
    │    │    → Watchdog 检测正常 ✓
    │    │
    │    └─ 情况 B：mGlobalLock 被其他线程持有
    │         → monitor() 阻塞在 synchronized 上
    │         → HandlerChecker.run() 无法完成
    │         → mCompleted 保持 false
    │
    │ ③ 30 秒后 Watchdog 检查 mCompleted
    │
    ├─ mCompleted == true → 正常，进入下一轮
    │
    └─ mCompleted == false → 超时！
         │
         │ ④ Watchdog 响应序列
         ├─ 30s: WAITED_HALF → 打印警告日志
         │    → dump 所有线程堆栈到 /data/anr/traces.txt
         │
         └─ 60s: OVERDUE → 判定 Watchdog 超时
              → 再次 dump 线程堆栈
              → 调用 Process.killProcess(Process.myPid())
              → system_server 被杀
              → init 进程检测到 → 重启 Zygote → 重启 system_server
              → 用户看到系统重启（类似开机动画）
```

### 4.4 Watchdog 的超时状态机

```java
// frameworks/base/services/core/java/com/android/server/Watchdog.java
public int getCompletionStateLocked() {
    if (mCompleted) {
        return COMPLETED;           // 正常完成
    } else {
        long waitTimeMs = SystemClock.uptimeMillis() - mStartTimeMs;
        if (waitTimeMs < CHECK_INTERVAL / 2) {
            return WAITING;          // < 15s，还在等
        } else if (waitTimeMs < CHECK_INTERVAL) {
            return WAITED_HALF;      // 15-30s，警告
        }
        return OVERDUE;              // > 30s，超时
    }
}
```

Watchdog 的完整响应时间线（默认配置）：

```
T = 0s     Watchdog 投递检查消息
T = 0~30s  等待 HandlerChecker 完成
T = 30s    第一次检查：如果未完成 → WAITED_HALF
           → 打印 "WATCHDOG HALF" 警告
           → dump 所有线程堆栈（第一次 dump）
           → 不杀进程，继续等待
T = 60s    第二次检查：如果仍未完成 → OVERDUE
           → 打印 "WATCHDOG KILLING SYSTEM PROCESS"
           → dump 所有线程堆栈（第二次 dump）
           → dropbox 记录
           → Process.killProcess(myPid()) → system_server 死亡
T = 60s+   init 检测到 system_server 退出
           → 触发 Zygote 重启 → system_server 重启
           → 用户体验：短暂黑屏 + 重启动画 + 所有 App 重新启动
```

> **稳定性架构师视角：** Watchdog 杀 system_server 是 Android 系统稳定性中最严重的事件之一，对用户来说相当于"手机重启"。排查时关键在于 T=30s 时的第一次 dump——它比 T=60s 更接近问题发生的现场。在 `traces.txt` 中查找 `- locked <0x...>` 和 `- waiting to lock <0x...>` 来还原锁链。

---

## 5. 死锁场景分析

### 5.1 统一锁后的新型死锁模式

虽然 mGlobalLock 消除了 AMS↔WMS 的 ABBA 死锁，但 mGlobalLock 与**其他服务的锁**之间仍然存在死锁风险。

**死锁模式一：mGlobalLock ↔ PowerManagerService.mLock**

```
Thread A ("Binder:xxx_1"):               Thread B ("PowerManagerInternal"):
  // WMS 操作中需要查询电源状态           // PMS 需要通知 WMS 屏幕状态变化
  synchronized(mGlobalLock) {             synchronized(mLock) {  // PMS.mLock
    // ... WMS 操作 ...                     // ... PMS 操作 ...
    mPowerManager.isScreenOn();             mWindowManager.setScreenState();
    // → 内部需要 mLock                     // → 内部需要 mGlobalLock
    // → 等待 Thread B 释放 mLock           // → 等待 Thread A 释放 mGlobalLock
  }                                       }

  ┌──────────────┐         ┌──────────────┐
  │   Thread A   │ ──────→ │   mLock      │ ← 被 Thread B 持有
  │ 持有 mGlobal │         │  (PMS)       │
  │    Lock      │         └──────────────┘
  └──────────────┘
        ↑                          │
        │                          │
  ┌──────────────┐         ┌──────────────┐
  │ mGlobalLock  │ ←────── │   Thread B   │
  │              │         │ 持有 mLock   │
  └──────────────┘         └──────────────┘

  → 经典 ABBA 死锁！两个线程永远等待对方释放锁
  → 60 秒后 Watchdog 检测到 → 杀 system_server
```

**死锁模式二：mGlobalLock ↔ DisplayManagerService.mSyncRoot**

```
Thread A ("android.display"):            Thread B ("DisplayManager"):
  synchronized(mGlobalLock) {             synchronized(mSyncRoot) {
    // WMS 处理窗口布局                      // DMS 处理 Display 配置变更
    displayContent.updateDisplayInfo();     mWindowManager.onDisplayChanged();
    // → DisplayManagerService              // → 内部 synchronized(mGlobalLock)
    //   .getDisplayInfo()                  // → 等待 Thread A
    // → 需要 mSyncRoot
    // → 等待 Thread B
  }                                       }
```

这种死锁在**外接显示器热插拔**时最易触发：DMS 收到 Display 变化事件后通知 WMS，同时 WMS 可能正在查询 Display 信息。

**死锁模式三：mGlobalLock ↔ ActivityManagerService.mPidsSelfLocked**

```
Thread A ("Binder:xxx_2"):               Thread B ("ActivityManager"):
  synchronized(mGlobalLock) {             synchronized(mPidsSelfLocked) {
    // ATMS 中处理 Activity 启动            // AMS 处理进程死亡
    processRecord.getThread();              mAtmInternal.handleAppDied();
    // → 需要 mPidsSelfLocked              // → 内部需要 mGlobalLock
  }                                       }
```

### 5.2 如何在 Watchdog Traces 中识别死锁

Watchdog 触发时 dump 的 `traces.txt` 是分析死锁的核心数据。关键步骤：

**第一步：定位 Watchdog 杀进程的线程**

```
在 traces.txt 中搜索 "Watchdog" 或 "watchdog"：

"watchdog" prio=5 tid=xxx
  | group="main" sCount=1 uCount=0
  | at com.android.server.Watchdog.run(Watchdog.java:...)
```

**第二步：找到被阻塞的 Monitor 线程**

```
搜索 "Binder" 或 "android.display" 线程中的 "waiting to lock"：

"android.display" prio=5 tid=12 Blocked
  | group="main" sCount=1 uCount=0
  at com.android.server.wm.WindowManagerService.monitor(WMS.java:7826)
  - waiting to lock <0xABCD1234> (a WindowManagerGlobalLock)
                     ↑ mGlobalLock 的对象地址
```

**第三步：找到锁的持有者**

```
搜索 "locked <0xABCD1234>"（同一个地址）：

"Binder:1234_5" prio=5 tid=48 Blocked
  at com.android.server.wm.WindowManagerService.relayoutWindow(WMS.java:2156)
  - locked <0xABCD1234> (a WindowManagerGlobalLock)
                         ↑ 这个线程持有 mGlobalLock
  - waiting to lock <0xEFGH5678> (a Object)
                     ↑ 但它在等另一把锁！
```

**第四步：找到另一把锁的持有者**

```
搜索 "locked <0xEFGH5678>"：

"PowerManagerService" prio=5 tid=25 Blocked
  at com.android.server.power.PowerManagerService.updatePowerStateLocked(PMS.java:...)
  - locked <0xEFGH5678> (a Object)  ← 持有 PMS.mLock
  - waiting to lock <0xABCD1234> (a WindowManagerGlobalLock)  ← 等 mGlobalLock！
```

**死锁确认：** Thread A 持有 mGlobalLock、等 mLock；Thread B 持有 mLock、等 mGlobalLock → ABBA 死锁。

```
死锁链可视化：

  ┌────────────────────┐     waiting for     ┌────────────────────┐
  │ Binder:1234_5      │ ──────────────────→ │ PMS.mLock          │
  │ holds: mGlobalLock │                     │ held by:           │
  │                    │                     │ PowerManagerService│
  └────────────────────┘                     └─────────┬──────────┘
         ↑                                             │
         │                 waiting for                 │
         └─────────────────────────────────────────────┘
                    → 死锁确认 ←
```

### 5.3 Android 中的死锁防御策略

AOSP 中采用多种策略来防御死锁：

| 防御策略 | 说明 | 示例 |
|---------|------|------|
| **锁序规则** | 定义全局锁获取顺序，所有代码必须遵守 | mGlobalLock 必须在 PMS.mLock 之前获取 |
| **减小锁粒度** | 将大锁拆分为多个小锁 | Android 14 中部分布局计算从 mGlobalLock 中剥离 |
| **异步回调** | 避免在持锁时同步调用其他服务 | 使用 Handler.post() 替代同步调用 |
| **tryLock + 超时** | 使用带超时的锁获取 | 部分非关键路径使用 ReentrantLock.tryLock(timeout) |
| **锁检测工具** | 编译期或运行期检测锁顺序违规 | `@GuardedBy` 注解 + 静态分析 |

---

## 6. 实战案例

### Case 1：快速切换 Activity 引发 Watchdog Kill（典型模式）

**现象**

某自动化测试场景中，连续快速启动/销毁 Activity（模拟用户在最近任务列表中快速滑动），运行约 3 分钟后 system_server 被 Watchdog 杀死，设备重启。

logcat 中的关键日志：

```
W Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS: Blocked in monitor
                com.android.server.wm.WindowManagerService on foreground thread
                (android.display), Blocked in handler on display thread (android.display)
I Watchdog: Dumping to /data/anr/traces.txt
E Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS: Blocked in monitor
                com.android.server.wm.WindowManagerService
W Watchdog: *** GOODBYE!
I Process : Sending signal. PID: 1234 SIG: 9
```

**排查过程**

**第一步：分析 traces.txt — 定位锁持有者**

```
// traces.txt 中 "android.display" 线程（WMS 主线程）：
"android.display" prio=5 tid=12 Blocked
  at com.android.server.wm.WindowManagerService.monitor(WMS.java:7826)
  - waiting to lock <0x0f2a3b4c> (a com.android.server.wm.WindowManagerGlobalLock)
```

WMS 的 `monitor()` 方法无法获取 mGlobalLock → 说明 mGlobalLock 被某个线程长时间持有。

**第二步：找到 mGlobalLock 的持有者**

```
// 搜索 "locked <0x0f2a3b4c>"：
"Binder:1234_8" prio=5 tid=56 Runnable
  at com.android.server.wm.RootWindowContainer.performSurfacePlacementNoTrace(RWC.java:850)
  at com.android.server.wm.WindowSurfacePlacer.performSurfacePlacementLoop(WSP.java:178)
  at com.android.server.wm.WindowSurfacePlacer.performSurfacePlacement(WSP.java:126)
  at com.android.server.wm.WindowManagerService.relayoutWindow(WMS.java:2286)
  at com.android.server.wm.Session.relayout(Session.java:235)
  - locked <0x0f2a3b4c> (a com.android.server.wm.WindowManagerGlobalLock)
```

**根因定位：** Binder 线程在执行 `relayoutWindow()` 时触发了 `performSurfacePlacement()`，该方法在遍历窗口树做布局计算。

**第三步：分析 performSurfacePlacement 为什么慢**

进一步分析发现，快速 Activity 切换导致：
1. 大量 WindowState 处于过渡状态（有些正在添加，有些正在移除）
2. `performSurfacePlacementLoop` 的循环次数达到上限（6 次），每次都发现有窗口需要重新布局
3. 单次循环需要遍历 100+ 个 WindowState，每个 WindowState 的布局计算涉及 Insets、Frame、Visibility 多步操作
4. 总持锁时间：6 次循环 × 50ms/次 = 300ms+

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowSurfacePlacer.java
final void performSurfacePlacementNoTrace() {
    int loopCount = 6;  // 防止无限循环
    do {
        mTraversalScheduled = false;
        performSurfacePlacementLoop();
        // 每次循环后，如果有新的布局请求，继续循环
        loopCount--;
    } while (mTraversalScheduled && loopCount > 0);
    // 如果达到 6 次上限仍有请求 → 日志警告
    if (mTraversalScheduled) {
        Slog.e(TAG, "performSurfacePlacement looped too many times");
    }
}
```

在快速切换场景下，每次循环完成后又有新的 Activity 状态变化触发重新布局 → 循环无法收敛 → 持锁时间 300ms+ → 叠加多轮快速切换 → 锁被连续持有 → Watchdog 60s 超时。

**时间线还原：**

```
T = 0s      Watchdog 投递检查消息
T = 0-60s   mGlobalLock 被频繁获取-释放-获取-释放...
            但每次释放后立即被下一个 relayoutWindow 抢走
            → WMS.monitor() 一直抢不到锁
T = 30s     Watchdog 第一次检查 → WAITED_HALF → dump traces
T = 60s     Watchdog 第二次检查 → OVERDUE → 杀 system_server
```

**修复方案**

1. **限流**：对快速 Activity 切换场景，在 ATMS 层面增加切换频率限制（两次切换之间至少间隔 100ms）
2. **布局优化**：减少 `performSurfacePlacementLoop` 的单次耗时——对不可见窗口跳过布局计算
3. **锁粒度优化**：将 `performSurfacePlacement` 中的 SurfaceControl.Transaction 构建移到锁外执行

```java
// 优化前（伪代码）：
synchronized(mGlobalLock) {
    // 计算布局（5ms）
    // 构建 Transaction（3ms）
    // apply Transaction（2ms）   ← 这步不需要锁保护
}
// 总持锁时间：10ms

// 优化后（伪代码）：
SurfaceControl.Transaction t;
synchronized(mGlobalLock) {
    // 计算布局（5ms）
    // 构建 Transaction（3ms）
    t = pendingTransaction;
}
t.apply();  // 锁外执行（2ms）
// 总持锁时间：8ms（节省 20%）
```

> **稳定性架构师视角：** 这个案例的核心教训是——`performSurfacePlacement` 的循环机制在窗口状态高频变化时可能无法收敛。监控建议：在 `performSurfacePlacementLoop` 中埋点统计循环次数和总耗时，当循环次数达到上限或总耗时超过 100ms 时上报告警。

---

### Case 2：外接显示器导致 system_server 死锁（典型模式）

**现象**

某设备连接 USB-C 外接显示器时，偶发 system_server 重启。频率约 1/20（每 20 次连接/断开外接显示器触发 1 次）。

traces.txt 中的关键信息：

```
// 系统事件日志
I watchdog: Blocked in monitor com.android.server.wm.WindowManagerService
E watchdog: *** WATCHDOG KILLING SYSTEM PROCESS ***
```

**排查过程**

**第一步：从 traces.txt 还原锁链**

```
// Thread A：Binder 线程执行 WMS 操作
"Binder:1234_3" prio=5 tid=42 Blocked
  at com.android.server.display.DisplayManagerService.getDisplayInfoInternal(DMS.java:1203)
  - waiting to lock <0x0a1b2c3d> (a com.android.server.display.DisplayManagerService$SyncRoot)
  at com.android.server.wm.DisplayContent.updateDisplayInfo(DC.java:1856)
  at com.android.server.wm.DisplayContent.sendNewConfiguration(DC.java:1892)
  at com.android.server.wm.ActivityRecord.ensureActivityConfiguration(AR.java:5423)
  at com.android.server.wm.ActivityTaskManagerService.startActivity(ATMS.java:1102)
  - locked <0x0f2a3b4c> (a com.android.server.wm.WindowManagerGlobalLock)

// Thread B：DMS 线程处理 Display 热插拔
"DisplayManager" prio=5 tid=28 Blocked
  at com.android.server.wm.WindowManagerService.onDisplayChanged(WMS.java:4523)
  - waiting to lock <0x0f2a3b4c> (a com.android.server.wm.WindowManagerGlobalLock)
  at com.android.server.display.DisplayManagerService.handleDisplayDeviceChanged(DMS.java:890)
  - locked <0x0a1b2c3d> (a com.android.server.display.DisplayManagerService$SyncRoot)
```

**第二步：死锁链可视化**

```
Thread A (Binder:1234_3):                Thread B (DisplayManager):
  持有 mGlobalLock                         持有 DMS.mSyncRoot
  │                                        │
  │ startActivity()                        │ handleDisplayDeviceChanged()
  │  → ensureActivityConfiguration()       │  → onDisplayChanged()
  │    → sendNewConfiguration()            │    → synchronized(mGlobalLock)
  │      → updateDisplayInfo()             │       等待 Thread A 释放 mGlobalLock
  │        → getDisplayInfoInternal()      │
  │          → synchronized(mSyncRoot)     │
  │             等待 Thread B 释放         │
  │             mSyncRoot                  │
  │                                        │

  死锁确认：
  Thread A: 持有 mGlobalLock → 等待 mSyncRoot
  Thread B: 持有 mSyncRoot  → 等待 mGlobalLock
```

**根因**

这是一个典型的锁顺序违规：

- **正常锁序**：先获取 mGlobalLock，再获取 mSyncRoot（因为 WMS 是 DMS 的调用方）
- **Thread B 的锁序**：先获取 mSyncRoot（DMS 内部操作），再尝试获取 mGlobalLock（通知 WMS）→ 违反了锁顺序

**触发条件**：Thread A 在 Activity 启动过程中需要查询 Display 信息，同时 Thread B 在处理 Display 热插拔事件。两者时间窗口重叠时（约 50ms 的竞争窗口），死锁发生。

**修复方案**

修复锁顺序违规，确保 DMS 在通知 WMS 时不持有 mSyncRoot：

```java
// 修复前 (DisplayManagerService.java, 伪代码)：
private void handleDisplayDeviceChanged(int displayId) {
    synchronized (mSyncRoot) {
        // 更新 Display 内部状态
        updateLogicalDisplayLocked(displayId);
        // ❌ 在持有 mSyncRoot 时调用 WMS
        mWindowManager.onDisplayChanged(displayId);
    }
}

// 修复后：
private void handleDisplayDeviceChanged(int displayId) {
    boolean changed;
    synchronized (mSyncRoot) {
        // 更新 Display 内部状态
        changed = updateLogicalDisplayLocked(displayId);
    }
    // ✅ 释放 mSyncRoot 后再通知 WMS
    if (changed) {
        mWindowManager.onDisplayChanged(displayId);
    }
}
```

> **稳定性架构师视角：** 死锁问题的排查核心在于**锁链还原**——在 traces.txt 中找到所有 `locked <addr>` 和 `waiting to lock <addr>` 的线程，画出锁的持有-等待关系图。如果形成环路 → 死锁确认。修复方向始终是**统一锁序**或**缩小持锁范围**（释放锁后再调用其他服务）。建议在代码中通过 `@GuardedBy` 注解标注每个锁保护的字段，并在 Code Review 中检查锁序一致性。

---

## 总结

作为稳定性架构师，排查 WMS 锁竞争与 Watchdog 问题时需要记住以下关键点：

1. **mGlobalLock 是 system_server 中竞争最激烈的锁。** 它同时保护 WMS（窗口状态）和 ATMS（Activity 状态）的所有核心数据。锁竞争的严重程度与窗口数量、Activity 切换频率、Display 配置变更频率正相关。性能优化的核心方向是**减少持锁时间**和**缩小锁保护范围**。

2. **锁竞争的危害不在于锁本身，在于级联效应。** mGlobalLock 被长时间持有 → App Binder 调用阻塞 → App 主线程卡死 → Input ANR；或 → 焦点同步延迟 → 触摸异常；或 → Activity 生命周期阻塞 → Broadcast/Service ANR。排查 ANR 时如果发现 App 主线程卡在 system_server 的 Binder 调用上，必须检查 mGlobalLock 的竞争状况。

3. **Watchdog 是 system_server 的最后防线。** WMS 通过实现 `Watchdog.Monitor` 接口，让 Watchdog 定期检测 mGlobalLock 的可用性。超时阈值为 60 秒（30 秒警告 + 30 秒等待），超时后 Watchdog 杀 system_server → 系统重启。**traces.txt 中 T=30s 的第一次 dump 最接近问题现场**，是排查的首要数据。

4. **mGlobalLock 与其他服务锁之间的死锁仍然存在。** 虽然统一锁消除了 AMS↔WMS 死锁，但 mGlobalLock 与 PMS.mLock、DMS.mSyncRoot 等锁之间的 ABBA 死锁仍需防范。排查方法：在 traces.txt 中搜索 `locked` 和 `waiting to lock`，还原锁链，检查是否成环。

5. **监控先于排查。** 建议在以下点位建立监控：① `performSurfacePlacement` 的单次耗时和循环次数；② mGlobalLock 的单次持有时长（超过 50ms 告警）；③ Watchdog 的 WAITED_HALF 事件（超时 30s 的早期信号）；④ system_server 的 Binder 线程池利用率（接近满载时锁竞争加剧）。

**排查路径速查：**

```
问题现象                → 排查入口
────────────────────────────────────────────────────────────────
system_server 重启      → /data/anr/traces.txt：搜索 Watchdog
                          → 找到 mGlobalLock 持有者
                          → 分析持锁代码路径

ANR + Binder 阻塞       → App traces：主线程卡在 Binder
                          → system_server traces：对应 Binder 线程等锁
                          → mGlobalLock 持有者分析

触摸异常/穿透           → dumpsys input：窗口区域 vs 实际位置
                          → InputMonitor 更新延迟
                          → mGlobalLock 竞争分析

Activity 切换卡顿       → Systrace：WMS 相关 trace
                          → relayoutWindow / performSurfacePlacement 耗时
                          → 锁等待时间占比
```

---

## 附录：核心源码路径索引

| 文件名 | 完整路径 | 说明 |
|--------|---------|------|
| WindowManagerService.java | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | WMS 主入口，实现 Watchdog.Monitor |
| ActivityTaskManagerService.java | `frameworks/base/services/core/java/com/android/server/wm/ActivityTaskManagerService.java` | ATMS，mGlobalLock 的定义所在 |
| WindowManagerGlobalLock.java | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerGlobalLock.java` | 全局锁类定义（空类，仅作监视器） |
| Watchdog.java | `frameworks/base/services/core/java/com/android/server/Watchdog.java` | Watchdog 主逻辑，HandlerChecker/Monitor 机制 |
| WindowSurfacePlacer.java | `frameworks/base/services/core/java/com/android/server/wm/WindowSurfacePlacer.java` | 全局布局计算，mGlobalLock 持锁热点 |
| RootWindowContainer.java | `frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java` | 窗口树根节点，performSurfacePlacement 的实际执行 |
| DisplayContent.java | `frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java` | Display 窗口管理，焦点计算 |
| InputMonitor.java | `frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java` | WMS→InputDispatcher 焦点同步 |
| Session.java | `frameworks/base/services/core/java/com/android/server/wm/Session.java` | App↔WMS Binder 会话入口 |
| WindowState.java | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | 窗口核心抽象 |
| ActivityRecord.java | `frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java` | Activity 在 WMS/ATMS 中的表示 |
| DisplayManagerService.java | `frameworks/base/services/core/java/com/android/server/display/DisplayManagerService.java` | Display 管理服务，mSyncRoot 锁 |
| PowerManagerService.java | `frameworks/base/services/core/java/com/android/server/power/PowerManagerService.java` | 电源管理服务，mLock 锁 |
| ViewRootImpl.java | `frameworks/base/core/java/android/view/ViewRootImpl.java` | App 端窗口核心，发起 Binder 调用 |

---

下一篇 [11-Window 诊断工具与治理体系](11-Window诊断工具与治理体系.md) 将深入 `dumpsys window`、`dumpsys SurfaceFlinger`、Systrace/Perfetto、winscope 等诊断工具的实战用法，以及 Window 系统稳定性的监控与治理最佳实践。
