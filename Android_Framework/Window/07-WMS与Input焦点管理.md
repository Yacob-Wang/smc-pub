# 07-WMS 与 Input 焦点管理：焦点应用切换、焦点窗口切换与 Input ANR

> **桥梁文章**：本篇是 Window 系列与 Input 系列的交汇点。Window 系列前 6 篇建立了 WMS 的窗口创建、层级、布局、Surface、动画的完整认知；Input 系列前 6 篇建立了从硬件到 App 的事件流管线。**焦点管理**是两条线的交叉点——WMS 决定"谁该收到事件"，InputDispatcher 执行"把事件发给谁"。焦点管理的时序缺陷，是造成 Input ANR 中最难排查的"无焦点窗口 ANR"的根本原因。

---

## 1. 两种焦点的本质区别 — FocusedApplication vs FocusedWindow

Android 的 Input 焦点系统维护着**两个独立的焦点概念**。混淆它们是导致焦点 ANR 排查方向错误的最常见原因。

### 1.1 概念定义

**FocusedApplication（焦点应用）**：由 AMS 通过 `ActivityRecord` 设置，告诉 InputDispatcher"**哪个 App 应该接收事件**"。它代表的是一个"承诺"——系统认为这个应用即将准备好接收输入。

**FocusedWindow（焦点窗口）**：由 WMS 通过 `updateFocusedWindowLocked()` 计算，告诉 InputDispatcher"**哪个具体窗口接收 KEY 事件**"。它代表的是一个"事实"——这个窗口确实已经添加、可见、可聚焦。

### 1.2 存储位置与设置方

```
InputDispatcher (Native 层)
├── mFocusedApplicationHandlesByDisplay
│     键: displayId
│     值: InputApplicationHandle (来自 ActivityRecord)
│     设置方: AMS → WMS → InputMonitor → InputDispatcher::setFocusedApplication()
│     时机: Activity RESUMING 时（早期）
│
└── mFocusedWindowHandlesByDisplay
      键: displayId
      值: InputWindowHandle (来自 WindowState)
      设置方: WMS → InputMonitor → InputDispatcher::setFocusedWindow()
      时机: Window addWindow + visible + focusable 之后（晚期）
```

### 1.3 两种焦点的核心差异

| 维度 | FocusedApplication | FocusedWindow |
|:---|:---|:---|
| **本质** | "哪个 App **应该**接收事件"（承诺） | "哪个窗口**实际**接收 KEY 事件"（事实） |
| **设置方** | AMS → `ActivityRecord.setResumedActivity()` | WMS → `DisplayContent.updateFocusedWindowLocked()` |
| **存储位置** | `InputDispatcher::mFocusedApplicationHandlesByDisplay` | `InputDispatcher::mFocusedWindowHandlesByDisplay` |
| **设置时机** | Activity **开始 Resume** 时（窗口可能尚未创建） | Window **添加并可见**后（需要 addWindow + relayout + draw） |
| **粒度** | Application 级别（一个 ActivityRecord） | Window 级别（一个 WindowState） |
| **用于** | ANR 裁决时确定"应该归咎于哪个 App" | KEY 事件分发时确定"发给哪个窗口" |
| **Touch 事件** | 不直接使用 | 不直接使用（Touch 使用 Z-order Hit Test） |
| **Key 事件** | 作为 ANR 归属依据 | 作为分发目标 |

### 1.4 Touch vs Key 的焦点使用方式

这是一个关键区分——**触摸事件和按键事件使用完全不同的窗口选择机制**：

```
Touch 事件（ACTION_DOWN / MOVE / UP）:
  InputDispatcher::findTouchedWindowTargetsLocked()
    → 按 Z-order 从高到低遍历所有窗口
    → 命中测试: 触摸坐标是否在窗口 touchableRegion 内
    → 找到第一个命中且非 NOT_TOUCHABLE 的窗口
    → ★ 不使用 FocusedWindow，而是使用 Z-order Hit Test

Key 事件（KEYCODE_BACK / VOLUME_UP / 字符键等）:
  InputDispatcher::findFocusedWindowTargetsLocked()
    → 直接查找 mFocusedWindowHandlesByDisplay[displayId]
    → 如果 FocusedWindow != null → 发给它
    → 如果 FocusedWindow == null:
         → 如果 FocusedApplication != null → 等待（窗口可能正在创建）
         → 等待超过 5 秒 → 触发 ANR，归咎于 FocusedApplication
         → 如果 FocusedApplication == null → 丢弃事件
    → ★ 直接使用 FocusedWindow
```

> **稳定性架构师视角**：理解 Touch 与 Key 的焦点差异至关重要。"无焦点窗口 ANR"只在 **KEY 事件**触发时才会发生——如果 ANR 期间只有 Touch 事件，Touch 会通过 Z-order Hit Test 找到窗口（即使不是焦点窗口），不会触发"no focused window"类型的 ANR。但实际场景中，用户在触摸屏幕后可能按下返回键、音量键或物理键盘键，此时 KEY 事件找不到焦点窗口就会触发 ANR。

### 1.5 时间差：ANR 的根源

```
                 FocusedApplication          FocusedWindow
设置时机:         Activity RESUMING           Window added + visible
                        │                          │
                        ▼                          ▼
时间线: ──────────┬──────┬───────────────────────────┬──────────
                 │      │                           │
                 │  T1: FocusedApplication = B      │
                 │      │                           │
                 │      │  ←── 危险窗口期 ──→        │
                 │      │  FocusedApp = B            │
                 │      │  FocusedWindow = null      │
                 │      │  KEY 事件到达 → 等待...     │
                 │      │  等待 > 5s → ANR!          │
                 │      │                           │
                 │      │                      T7: FocusedWindow = B's window
                 │      │                           │
```

**这个时间差就是"无焦点窗口 ANR"的根本原因。** FocusedApplication 在 Activity 开始 Resume 时就设置了（此时窗口还没创建），而 FocusedWindow 要等到窗口添加、Surface 创建、首帧绘制完成后才设置。如果这个间隔超过 5 秒（例如 Application.onCreate 太慢、Activity.onCreate 太重），任何 KEY 事件都会触发 ANR。

---

## 2. FocusedApplication 的设置与切换

### 2.1 设置链路

FocusedApplication 的设置从 AMS 侧的 Activity 状态变更开始，经过 WMS 中转，最终到达 InputDispatcher：

```
AMS 侧:
  ActivityTaskManagerService.resumeTopActivity()
    → Task.resumeTopActivityInnerLocked()
      → ActivityRecord.completeResumeLocked()
        → RootWindowContainer.updateFocusedAppIfNeeded()    ← 更新焦点 App

WMS 侧:
  DisplayContent.setFocusedApp(ActivityRecord r)
    → mFocusedApp = r
    → InputMonitor.setFocusedAppLw(ActivityRecord newApp)

InputMonitor → Native:
  InputMonitor.setFocusedAppLw()
    → mService.mInputManager.setFocusedApplication(displayId, handle)
      → NativeInputManager::setFocusedApplication()
        → InputDispatcher::setFocusedApplication(displayId, handle)
```

### 2.2 核心源码

```java
// frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java
boolean updateFocusedAppIfNeeded() {
    // 找到应该获得焦点的 Activity
    final ActivityRecord focusedActivity = getTopResumedActivity();
    
    if (focusedActivity != mFocusedApp) {
        mFocusedApp = focusedActivity;
        // 通知 DisplayContent 更新焦点 App
        final DisplayContent dc = focusedActivity != null
                ? focusedActivity.getDisplayContent() : getDefaultDisplay();
        dc.setFocusedApp(focusedActivity);
        return true;
    }
    return false;
}
```

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java
void setFocusedApp(ActivityRecord newFocus) {
    if (newFocus != null) {
        final DisplayContent appDisplay = newFocus.getDisplayContent();
        if (appDisplay != this) {
            // Activity 不在当前 Display 上，忽略
            return;
        }
    }
    
    if (mFocusedApp != newFocus) {
        mFocusedApp = newFocus;
        // 同步到 InputDispatcher
        getInputMonitor().setFocusedAppLw(newFocus);
    }
}
```

```java
// frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java
void setFocusedAppLw(ActivityRecord newApp) {
    InputApplicationHandle handle = newApp != null
            ? newApp.mInputApplicationHandle : null;
    // JNI → NativeInputManager → InputDispatcher::setFocusedApplication
    mService.mInputManager.setFocusedApplication(
            mDisplayContent.getDisplayId(), handle);
}
```

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
void InputDispatcher::setFocusedApplication(
        int32_t displayId,
        const std::shared_ptr<InputApplicationHandle>& inputApplicationHandle) {
    { // acquire lock
        std::scoped_lock _l(mLock);
        
        std::shared_ptr<InputApplicationHandle> oldFocusedApplicationHandle =
                getValueByKey(mFocusedApplicationHandlesByDisplay, displayId);
        
        if (sharedPointersEqual(oldFocusedApplicationHandle, inputApplicationHandle)) {
            return;  // 没有变化
        }
        
        if (inputApplicationHandle != nullptr) {
            mFocusedApplicationHandlesByDisplay[displayId] = inputApplicationHandle;
        } else {
            mFocusedApplicationHandlesByDisplay.erase(displayId);
        }
        
        // 重置"无焦点窗口"的等待超时计时器
        // 新的 FocusedApplication 来了，给它 5 秒时间准备 FocusedWindow
        resetNoFocusedWindowTimeoutLocked();
    } // release lock
    
    // 唤醒 Dispatcher 线程，让它检查是否有待分发事件
    mLooper->wake();
}
```

### 2.3 关键时机分析

**FocusedApplication 的设置发生在 Activity RESUMING 阶段**——此时 Activity 的 `onCreate` / `onStart` / `onResume` 正在执行或刚执行完，但 `ViewRootImpl.setView()` → `addWindow()` 可能尚未调用。

```
Activity 启动时序:
  AMS: startActivity()
    → ActivityRecord 创建
    → pause 前一个 Activity
    → 新 Activity 进程就绪 (或冷启动: fork + Application.onCreate)
    → resumeTopActivity()
      → setFocusedApp(newActivity)         ★ FocusedApplication 在此设置!
      → ActivityThread.scheduleResumeActivity()
        → handleResumeActivity()
          → Activity.onResume()
          → WindowManager.addView(decor)   ★ Window 在此才开始创建!
            → ViewRootImpl.setView()
              → WMS.addWindow()
```

> **稳定性架构师视角**：`setFocusedApp` 在 `resumeTopActivity` 中调用，此时连 `handleResumeActivity` 都还没开始。在冷启动场景下，`Application.onCreate()` 可能正在执行。这意味着 FocusedApplication 的设置和 FocusedWindow 的设置之间，隔着整个 `Application.onCreate()` + `Activity.onCreate()` + `setContentView()` + `addWindow()` + `relayoutWindow()` + 首帧绘制的全链路。**这条链路的总耗时就是焦点空窗期的长度。**

### 2.4 Activity 切换时的 FocusedApplication 更新

Activity 切换场景中，FocusedApplication 的更新时序：

```
Activity A (前台) → Activity B (将要前台)

T=0:   startActivity(B)
T=1:   AMS: pause(A)
T=2:   A.onPause() 完成
T=3:   AMS: resume(B)
T=3.1: setFocusedApp(B)         ← FocusedApplication 切换为 B
       InputDispatcher: mFocusedApplication = B
       InputDispatcher: resetNoFocusedWindowTimeout()  ← 5秒倒计时重置
T=3.2: B.handleResumeActivity() → addView → addWindow
T=4:   B's Window 添加完成
T=5:   updateFocusedWindowLocked() → FocusedWindow = B's Window
```

如果是冷启动（B 的进程不存在）：

```
T=0:   startActivity(B)
T=0.1: AMS: setFocusedApp(B)    ← FocusedApplication 立即设置！
T=0.2: fork 新进程
T=1:   Application.onCreate() 开始
T=3:   Application.onCreate() 结束 (假设 2 秒 SDK 初始化)
T=3.5: Activity.onCreate() → setContentView()
T=4:   ViewRootImpl.setView() → addWindow()
T=5:   relayoutWindow() → createSurface
T=6:   首帧绘制完成
T=6.5: updateFocusedWindowLocked() → FocusedWindow = B's Window

危险窗口期: T=0.1 ~ T=6.5 = 6.4 秒 > 5 秒 → ANR!
```

---

## 3. FocusedWindow 的计算与更新

### 3.1 触发条件

`updateFocusedWindowLocked()` 在以下场景被调用：

| 触发场景 | 调用链 | 说明 |
|:---|:---|:---|
| addWindow | `WMS.addWindow()` → `updateFocusedWindowLocked()` | 新窗口添加后，可能成为焦点窗口 |
| removeWindow | `WindowState.removeIfPossible()` → `updateFocusedWindowLocked()` | 焦点窗口移除后，需要重新计算焦点 |
| relayoutWindow | `WMS.relayoutWindow()` → `performSurfacePlacementNoTrace()` → `updateFocusedWindowLocked()` | 窗口可见性变化可能影响焦点 |
| Activity 状态变化 | `ActivityRecord.setVisibility()` → `updateFocusedWindowLocked()` | Activity 可见性变化 |
| 窗口属性变化 | FLAG_NOT_FOCUSABLE 变更 → `updateFocusedWindowLocked()` | 焦点能力变更 |
| Display 变化 | `DisplayContent.configureDisplayPolicy()` → `updateFocusedWindowLocked()` | 屏幕配置变更 |

### 3.2 焦点计算核心算法

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java
boolean updateFocusedWindowLocked(int mode, boolean updateInputWindows) {
    WindowState newFocus = findFocusedWindowIfNeeded(mode);
    
    if (mCurrentFocus == newFocus) {
        return false;
    }
    
    WindowState oldFocus = mCurrentFocus;
    mCurrentFocus = newFocus;
    
    // 通知 InputMonitor 焦点变化
    if (updateInputWindows) {
        getInputMonitor().setInputFocusLw(newFocus, updateInputWindows);
    }
    
    // 通知 App 端 onWindowFocusChanged
    if (oldFocus != null) {
        oldFocus.reportFocusChangedSerialized(false);
    }
    if (newFocus != null) {
        newFocus.reportFocusChangedSerialized(true);
    }
    
    return true;
}
```

焦点窗口的查找逻辑——**从窗口树自顶向下遍历，找到第一个 `canReceiveKeys()` 为 true 的窗口**：

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java
WindowState findFocusedWindow() {
    mTmpWindow = null;
    forAllWindows(w -> {
        if (!w.canReceiveKeys()) {
            return false;  // 继续查找
        }
        mTmpWindow = w;
        return true;  // 找到，停止遍历
    }, true /* traverseTopToBottom */);
    return mTmpWindow;
}
```

### 3.3 canReceiveKeys() — 焦点资格判定

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java
boolean canReceiveKeys() {
    return canReceiveKeys(false /* fromUserTouch */);
}

boolean canReceiveKeys(boolean fromUserTouch) {
    // 条件 1：窗口没有设置 FLAG_NOT_FOCUSABLE
    if (mAttrs.flags & FLAG_NOT_FOCUSABLE) != 0) {
        return false;
    }
    
    // 条件 2：窗口可见（isVisibleRequestedOrAdding）
    if (!isVisibleRequestedOrAdding()) {
        return false;
    }
    
    // 条件 3：所属 Activity 没有在 finishing
    final ActivityRecord activity = getActivityRecord();
    if (activity != null) {
        if (!activity.windowsAreFocusable(fromUserTouch)) {
            return false;
        }
        // Activity 的可见性也必须满足
        if (!activity.isVisibleRequested()) {
            return false;
        }
    }
    
    // 条件 4：Display 允许焦点
    final DisplayContent dc = getDisplayContent();
    if (!dc.canReceiveKeys(this)) {
        return false;
    }
    
    return true;
}
```

**焦点资格的完整条件链：**

```
canReceiveKeys() == true 需要同时满足:
  ├── FLAG_NOT_FOCUSABLE 未设置
  ├── 窗口可见 (isVisibleRequestedOrAdding)
  ├── 所属 ActivityRecord 允许获得焦点 (windowsAreFocusable)
  │     ├── Activity 没有在 finishing
  │     ├── Activity 没有被标记为 NOT_FOCUSABLE
  │     └── Activity 的进程未被标记为 NOT_FOCUSABLE (如 PiP 模式)
  ├── ActivityRecord 可见 (isVisibleRequested)
  └── DisplayContent 允许该窗口获得焦点
```

> **稳定性架构师视角**：`canReceiveKeys()` 返回 false 的情况比想象中多。常见的"焦点丢失"场景包括：① Dialog dismiss 后 Activity 窗口的 `isVisibleRequestedOrAdding` 短暂返回 false（config change 期间）；② 应用进入 PiP 模式后 `windowsAreFocusable` 返回 false；③ 第三方 SDK 创建的悬浮窗设置了 `FLAG_NOT_FOCUSABLE` 但又修改了 `FLAG_NOT_TOUCH_MODAL`，导致触摸穿透但焦点行为异常。排查焦点问题时，`dumpsys window` 中检查 `mCurrentFocus` 和每个窗口的 `focusable` 属性是关键。

### 3.4 从 WMS 到 InputDispatcher 的焦点同步

```java
// frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java
void setInputFocusLw(WindowState newWindow, boolean updateInputWindows) {
    InputWindowHandleWrapper inputWindowHandle = newWindow != null
            ? newWindow.mInputWindowHandle : null;
    
    if (newWindow != null) {
        // 通过 SurfaceControl.Transaction 设置焦点窗口
        // 最终到达 InputDispatcher::setFocusedWindow()
        final IBinder focusToken = newWindow.mInputChannelToken;
        if (focusToken != null) {
            // 设置 FocusedWindow
            mInputFocus = newWindow;
            mService.mInputManager.setFocusedWindow(
                    new FocusRequest(focusToken,
                            newWindow.getDisplayId(),
                            newWindow.mInputWindowHandle.getToken()));
        }
    }
    
    if (updateInputWindows) {
        updateInputWindowsLw(false /* force */);
    }
}
```

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
void InputDispatcher::setFocusedWindow(const FocusRequest& request) {
    { // acquire lock
        std::scoped_lock _l(mLock);
        
        const int32_t displayId = request.displayId;
        const sp<IBinder>& token = request.token;
        
        // 查找窗口是否已注册 InputChannel
        bool hasFocus = mWindowHandlesByDisplay.find(displayId) !=
                mWindowHandlesByDisplay.end();
        
        if (hasFocus) {
            // 窗口已注册，立即设置焦点
            mFocusedWindowHandlesByDisplay[displayId] = 
                    getFocusedWindowHandleLocked(token, displayId);
        } else {
            // 窗口尚未注册（可能 InputChannel 还没创建）
            // 保存为 pending 请求，等窗口注册后再设置
            mPendingFocusRequests[displayId] = request;
        }
    } // release lock
    
    // 唤醒 Dispatcher 线程处理待分发的 KEY 事件
    mLooper->wake();
}
```

---

## 4. 窗口信息同步 — InputMonitor 详解

### 4.1 InputMonitor 的角色

`InputMonitor` 是 WMS 与 InputDispatcher 之间的**唯一桥梁**。它负责两件事：

1. **窗口列表同步**：将 WMS 中所有窗口的位置、大小、flags、InputChannel 等信息打包传给 InputDispatcher
2. **焦点窗口同步**：通知 InputDispatcher 当前哪个窗口是焦点窗口

```
WMS                         InputMonitor                    InputDispatcher
 │                               │                              │
 │  addWindow / removeWindow     │                              │
 │  relayoutWindow               │                              │
 │  updateFocusedWindowLocked    │                              │
 │          │                    │                              │
 │          ▼                    │                              │
 │  setInputFocusLw() ────────▶  │                              │
 │  updateInputWindowsLw() ──▶   │                              │
 │                               │  1. forAllWindows()          │
 │                               │     遍历所有窗口              │
 │                               │     收集 InputWindowHandle   │
 │                               │                              │
 │                               │  2. setInputWindows() ─────▶ │
 │                               │     [Native 调用]            │ 更新窗口列表
 │                               │                              │
 │                               │  3. setFocusedWindow() ───▶  │
 │                               │     [Native 调用]            │ 更新焦点窗口
 │                               │                              │
```

### 4.2 updateInputWindowsLw() 完整流程

```java
// frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java
void updateInputWindowsLw(boolean force) {
    if (!force && !mUpdateInputWindowsNeeded) {
        return;
    }
    mUpdateInputWindowsNeeded = false;
    
    // ★ 以下代码执行在 mGlobalLock 内！
    
    // Step 1: 遍历所有窗口，自顶向下收集 InputWindowHandle
    mDisplayContent.forAllWindows(this::populateInputWindowHandle,
            true /* traverseTopToBottom */);
    
    // Step 2: 通过 SurfaceControl.Transaction 批量提交窗口信息
    // Transaction 最终到达 SurfaceFlinger → InputDispatcher
    mDisplayContent.getInputMonitor().setUpdateInputWindowsNeededLw();
    
    // Step 3: 更新焦点窗口
    if (mInputFocus != mDisplayContent.mCurrentFocus) {
        setInputFocusLw(mDisplayContent.mCurrentFocus, false);
    }
}
```

```java
// InputMonitor.java - 每个窗口的信息收集
private void populateInputWindowHandle(WindowState w) {
    final InputWindowHandleWrapper inputWindowHandle = w.mInputWindowHandle;
    
    // 填充窗口信息
    inputWindowHandle.setToken(w.mInputChannelToken);
    inputWindowHandle.setName(w.getName());
    inputWindowHandle.setLayoutParamsFlags(w.mAttrs.flags);
    inputWindowHandle.setLayoutParamsType(w.mAttrs.type);
    inputWindowHandle.setDispatchingTimeoutMillis(w.getInputDispatchingTimeoutMillis());
    inputWindowHandle.setOwnerPid(w.mSession.mPid);
    inputWindowHandle.setOwnerUid(w.mSession.mUid);
    
    // 窗口的可触摸区域
    inputWindowHandle.setTouchableRegion(w.getTouchableRegion());
    
    // 窗口是否可见
    inputWindowHandle.setVisible(w.isVisibleLw());
    
    // 窗口是否可聚焦
    inputWindowHandle.setFocusable(w.canReceiveKeys());
    
    // 将 InputWindowHandle 关联到 SurfaceControl.Transaction
    // 确保窗口位置更新和 Input 区域更新原子性一致
    mInputTransaction.setInputWindowInfo(w.mSurfaceControl, inputWindowHandle.getInfo());
}
```

### 4.3 InputWindowHandle 传递的关键信息

| 字段 | 来源 | InputDispatcher 用途 |
|:---|:---|:---|
| `token` | `WindowState.mInputChannelToken` | 标识窗口，关联 InputChannel Connection |
| `name` | `WindowState.getName()` | 日志输出，dumpsys 显示 |
| `layoutParamsFlags` | `WindowManager.LayoutParams.flags` | 判断 NOT_TOUCHABLE / NOT_FOCUSABLE / NOT_TOUCH_MODAL |
| `layoutParamsType` | `WindowManager.LayoutParams.type` | 判断窗口类型（Application / System / IME） |
| `touchableRegion` | `WindowState.getTouchableRegion()` | Touch Hit Test：触摸点是否在区域内 |
| `frame` | `WindowState.mFrame` | 窗口的屏幕坐标 |
| `ownerPid` / `ownerUid` | `Session.mPid` / `Session.mUid` | ANR 时确定目标进程 |
| `visible` | `WindowState.isVisibleLw()` | 不可见窗口不接收事件 |
| `focusable` | `WindowState.canReceiveKeys()` | 不可聚焦窗口不接收 KEY 事件 |
| `dispatchingTimeout` | 通常 5000ms | ANR 超时阈值 |

### 4.4 锁竞争与信息延迟

**关键稳定性问题**：`updateInputWindowsLw()` 执行在 `mGlobalLock` 内——它需要遍历整个 WindowContainer 树来收集所有窗口信息。

```
mGlobalLock 持有期间的 updateInputWindowsLw():

T=0ms    获取 mGlobalLock
T=0ms    开始 forAllWindows() 遍历
         ... 遍历 N 个窗口，每个窗口执行 populateInputWindowHandle ...
T=Xms    遍历完成（X 取决于窗口数量）
T=Xms    构建 SurfaceControl.Transaction
T=X+1ms  setInputFocusLw()
T=X+2ms  释放 mGlobalLock

锁持有时间 = X + 2 ms

如果窗口数量 = 50：X ≈ 5-10ms
如果窗口数量 = 200（某些场景）：X ≈ 20-50ms
```

当 `mGlobalLock` 被长时间持有时，其他需要该锁的操作（`addWindow`、`relayoutWindow`、`removeWindow`）全部阻塞。更严重的是，如果 `updateInputWindowsLw()` 本身被延迟（因为锁被其他操作持有），InputDispatcher 就会使用**过期的窗口信息**：

```
时序问题：WMS 锁竞争导致 Input 信息延迟

T=0ms    窗口 A 的位置从 [0,0,540,960] 变为 [0,0,1080,1920]（全屏）
T=0ms    WMS: performLayout() 持有 mGlobalLock
T=5ms    WMS: performLayout() 完成
T=5ms    WMS: 准备调用 updateInputWindowsLw()
         但 mGlobalLock 被动画线程抢占...
T=15ms   用户触摸 [800, 1200]
         InputDispatcher: 使用旧的窗口信息
         旧信息中窗口 A 的区域是 [0,0,540,960]
         [800, 1200] 不在区域内 → 触摸事件"穿透"了！
T=25ms   mGlobalLock 释放，updateInputWindowsLw() 执行
         InputDispatcher 拿到新的窗口信息
T=25ms+  后续触摸正常
```

> **稳定性架构师视角**：WMS 锁竞争导致 `updateInputWindowsLw()` 延迟，是**触摸穿透**（Touch Pass-Through）和**事件丢失**的重要原因。这类问题最难复现、最难排查——因为它依赖于精确的时序竞态。在 Systrace/Perfetto 中，搜索 `updateInputWindows` 标签可以看到每次同步的时间点和耗时。如果某次同步与窗口位置变化之间有明显的时间差（>10ms），就是潜在的 Input 路由错误窗口。

---

## 5. Activity 切换全链路中的焦点变化时序

### 5.1 从 Activity A 切换到 Activity B — 完整时序

以下是最常见的 Activity 切换场景（A 在前台，用户启动 B）的完整焦点变化时序。**这个时序图是理解焦点 ANR 的核心工具。**

```
时间   AMS/ActivityRecord        WMS/InputMonitor         InputDispatcher         App 进程
─────  ─────────────────────     ─────────────────        ──────────────          ──────────
T=0    startActivity(B)
       │
T=1    resumeTopActivity(B)
       setFocusedApp(B)  ─────▶ setFocusedAppLw(B) ─────▶ setFocusedApplication(B)
       │                                                   mFocusedApp = B
       │                                                   ★ 重置 5s 倒计时
       │
T=2    pause(A)          ─────▶                            
       │                                                   此时焦点状态:
       │                                                   FocusedApp    = B (新)
       │                                                   FocusedWindow = A's window (旧!)
       │
T=3    A.onPause() 完成
       │
T=4    schedule resume(B)                                                          B.onCreate()
       │                                                                           setContentView()
       │
T=5                                                                                B.onResume()
       │                                                                           wm.addView(decor)
       │                                                                           └ ViewRootImpl.setView()
       │                                                                              └ Binder: addToDisplay
       │
T=6                        addWindow(B's window)
                           openInputChannel(B)  ──────────▶ registerInputChannel(B)
                           updateFocusedWindow
                           │                               此时焦点状态:
                           │                               FocusedApp    = B
                           │                               FocusedWindow = ?
                           │                               (可能仍是 A 或变为 B)
                           │
T=7                        relayoutWindow(B)
                           createSurfaceLocked()
                           │
T=8                                                                                performTraversals()
                                                                                   measure → layout → draw
T=9                        B's window 可见
                           updateFocusedWindowLocked()
                           ─ FocusedWindow = B's Window ──▶ setFocusedWindow(B)
                                                           mFocusedWindow = B's window
                                                           ★ 焦点就绪，可分发 KEY
```

### 5.2 焦点空窗期分析

```
焦点空窗期 (Focus Gap):
  起点: T=1  → FocusedApplication = B (但 B 的 Window 还不存在)
  终点: T=9  → FocusedWindow = B's Window

  空窗期长度 = T9 - T1

  在此期间:
  ┌─────────────────────────────────────────────────┐
  │ FocusedApplication = B                           │
  │ FocusedWindow = null (或仍指向 A 的已 pause 窗口) │
  │                                                  │
  │ 如果 KEY 事件到达:                                 │
  │   → findFocusedWindowTargetsLocked()             │
  │   → FocusedWindow == null                        │
  │   → FocusedApplication == B                      │
  │   → "等待 B 的窗口出现"                            │
  │   → 等待超过 5 秒 → ANR!                          │
  │                                                  │
  │ 如果 Touch 事件到达:                               │
  │   → findTouchedWindowTargetsLocked()             │
  │   → Z-order Hit Test → 可能命中 A 的窗口           │
  │   → Touch 事件不会触发"no focused window" ANR      │
  └─────────────────────────────────────────────────┘
```

### 5.3 ASCII 时序全景图

```
       AMS                    WMS                   InputDispatcher              App (B)
        │                      │                         │                         │
   T=0  │ startActivity(B)     │                         │                         │
        │─────────────────────▶│                         │                         │
   T=1  │ setFocusedApp(B) ───▶│ setFocusedAppLw(B) ───▶│ setFocusedApplication   │
        │                      │                         │  (B)                    │
        │                      │                         │ [reset 5s timer]        │
        │                      │                         │                         │
   T=2  │ pause(A) ──────────▶│                         │                         │
        │                      │                         │ ◄── KEY event ──┐       │
        │                      │                         │   FocusedApp=B  │       │
        │                      │                         │   FocusedWin=?  │       │
        │                      │                         │   "等待..."     │       │
   T=3  │ A.onPause() done     │                         │   5s 倒计时中   │       │
        │                      │                         │                 │       │
   T=4  │ schedule resume(B)   │                         │                         │
        │                      │                         │                    B.onCreate()
        │                      │                         │                    setContentView()
   T=5  │                      │                         │                    B.onResume()
        │                      │                         │                    addView(decor)
   T=6  │                      │ addWindow(B)            │                         │
        │                      │  openInputChannel ─────▶│ register(B)             │
        │                      │                         │                         │
   T=7  │                      │ relayoutWindow(B)       │                         │
        │                      │  createSurface           │                         │
   T=8  │                      │                         │                    performTraversals()
        │                      │                         │                    draw first frame
   T=9  │                      │ updateFocusedWindow ───▶│ setFocusedWindow(B)     │
        │                      │  = B's Window           │ [焦点就绪!]              │
        │                      │                         │ 分发之前等待的 KEY        │
        │                      │                         │                         │
        ▼                      ▼                         ▼                         ▼

  ├──────── 焦点空窗期 (T=1 ~ T=9) ────────┤
  如果空窗期 > 5 秒 → ANR
```

### 5.4 空窗期长度的决定因素

| 阶段 | 耗时因素 | 典型耗时 | 极端耗时 |
|:---|:---|:---|:---|
| T=1→T=3 | Activity A 的 onPause | 10-50ms | 500ms+（同步保存数据） |
| T=3→T=4 | 进程调度 + IPC | 5-20ms | 100ms+（CPU 争抢） |
| T=4→T=5 | Application.onCreate（冷启动） | 0ms（热启动） | 3000-8000ms（SDK 初始化） |
| T=4→T=5 | Activity.onCreate + setContentView | 50-200ms | 1000ms+（复杂布局） |
| T=5→T=6 | addView → addWindow（Binder 调用） | 5-20ms | 100ms+（WMS 锁竞争） |
| T=6→T=9 | relayoutWindow + 首帧绘制 | 50-200ms | 500ms+（复杂 View 树） |
| **总空窗期** | | **120-500ms** | **5000ms+ → ANR** |

> **稳定性架构师视角**：**空窗期 > 5 秒就必然 ANR**。而空窗期的最大贡献者通常是 `Application.onCreate()`（冷启动 SDK 初始化）和 `Activity.onCreate()`（复杂布局 inflate）。优化这两个阶段是降低焦点 ANR 率的最有效手段。使用 `dumpsys input` 查看 `FocusedApplications` 和 `FocusedWindows` 的差异可以确认是否处于空窗期；使用 Systrace 的 `activityStart` 标签可以精确测量空窗期的长度。

---

## 6. 焦点异常的四种典型场景与实战案例

### 场景一：冷启动慢 → 无焦点窗口 ANR

**问题模式**

```
触发条件: Application.onCreate() 或 Activity.onCreate() 耗时 > 5 秒
焦点状态: FocusedApplication = X, FocusedWindow = <none>
ANR 信息: "Waiting because no window has focus but there is a focused application
           that may eventually add a window when it finishes starting up."
```

**dumpsys input 特征**

```
FocusedApplications:
  displayId=0, name='ActivityRecord{abc com.example.app/.MainActivity}',
  dispatchingTimeout=5000ms

FocusedWindows: <none>                    ← 关键：焦点窗口为空

InboundQueue: length=15
  KeyEvent(action=DOWN, keyCode=BACK), age=5823ms    ← 超时
  MotionEvent(action=DOWN, ...), age=5100ms
  ...
```

**实战案例**

某金融 App 冷启动 Input ANR 率高达 1.8%。排查过程：

**Step 1**：ANR traces.txt 主线程栈：

```
"main" prio=5 tid=1 Runnable
  at com.thirdparty.security.SecurityEngine.init(SecurityEngine.java:156)
    - 执行安全 SDK 初始化，涉及设备指纹采集和加解密
  at com.example.app.SdkManager.initAll(SdkManager.java:89)
  at com.example.app.MyApplication.onCreate(MyApplication.java:45)
  at android.app.Instrumentation.callApplicationOnCreate(...)
```

**Step 2**：Systrace 测量各阶段耗时：

```
Application.onCreate() 总耗时: 6200ms
  ├── SecurityEngine.init():     2800ms (设备指纹采集 + RSA 加密)
  ├── AnalyticsSDK.init():       1500ms (数据库初始化 + 网络请求)
  ├── PushSDK.init():            800ms  (Service 绑定)
  ├── HotfixSDK.init():          600ms  (DEX 加载)
  └── 其他初始化:                 500ms

Activity.onCreate() 总耗时: 1200ms
  └── setContentView(): 800ms (复杂布局 inflate)

焦点空窗期 = 6200 + 1200 + addWindow + 首帧 ≈ 8000ms >> 5000ms → ANR!
```

**修复方案**

```java
// 修复前: 所有 SDK 同步初始化
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        SdkManager.initAll();  // 6200ms 阻塞主线程
    }
}

// 修复后: 分级初始化策略
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        
        // P0: 必须在 Application.onCreate 完成的（<300ms）
        SdkManager.initCritical();  // 仅 Crash 上报 + 日志
        
        // P1: Activity.onCreate 之前完成（子线程）
        ThreadPool.execute(() -> {
            SdkManager.initSecondary();  // Security + Analytics
        });
        
        // P2: 首帧之后空闲时初始化
        Looper.myQueue().addIdleHandler(() -> {
            SdkManager.initDeferred();  // Push + Hotfix
            return false;
        });
    }
}
```

**效果**：Application.onCreate 从 6200ms 降至 280ms，焦点空窗期从 8000ms 降至 1800ms，Input ANR 率从 1.8% 降至 0.12%。

---

### 场景二：Dialog 弹出/关闭时焦点切换竞态

**问题模式**

Dialog 是一个独立的 Window，有自己的 WindowState。当 Dialog 弹出时：

```
Dialog.show() 前:
  焦点窗口: Activity's Window (TYPE_BASE_APPLICATION)

Dialog.show() 后:
  addWindow(Dialog's Window, TYPE_APPLICATION)
  updateFocusedWindowLocked()
  焦点窗口: Dialog's Window  ← Dialog 在 Z-order 上高于 Activity Window
```

当 Dialog 关闭时：

```
Dialog.dismiss() → removeWindow(Dialog's Window)
  updateFocusedWindowLocked()
  焦点窗口: Activity's Window  ← 焦点应该回到 Activity
```

**竞态场景**：如果 Dialog dismiss 和 Activity configuration change 同时发生：

```
T=0    Dialog.dismiss() → removeWindow(dialog)
T=1    updateFocusedWindowLocked()
       → 寻找下一个焦点窗口
       → Activity's Window: canReceiveKeys()?
         → isVisibleRequestedOrAdding() ?
         → 此时 Activity 正在经历 config change
         → Activity Window 被标记为不可见（正在重建）
         → canReceiveKeys() == false!
       → 找不到可聚焦窗口
       → FocusedWindow = null                ← 焦点丢失!

T=2    KEY 事件到达 InputDispatcher
       → FocusedWindow = null
       → FocusedApplication = 当前 App
       → 等待...

T=3    Activity 重建完成，新 Window 添加
       → updateFocusedWindowLocked()
       → FocusedWindow = 新 Activity Window
       （如果 T3 - T2 < 5s → 无事；> 5s → ANR）
```

**症状**：用户 dismiss Dialog 后短暂地无法使用返回键或按键导航。极端情况下如果 Activity 重建慢（如 Fragment 状态恢复复杂），会触发 ANR。

**排查方法**

```bash
# 确认焦点状态
adb shell dumpsys window | grep -E "mCurrentFocus|mFocusedApp"

# 如果 mCurrentFocus=null 但 mFocusedApp 有值 → 焦点空窗期
mCurrentFocus=null
mFocusedApp=ActivityRecord{... com.example.app/.MainActivity}
```

**防御方案**

```java
@Override
public void onConfigurationChanged(@NonNull Configuration newConfig) {
    super.onConfigurationChanged(newConfig);
    // 如果有 Dialog 在显示，先 dismiss 再处理 config change
    if (mDialog != null && mDialog.isShowing()) {
        mDialog.dismiss();
    }
}
```

---

### 场景三：多窗口模式下焦点争抢

**问题模式**

在分屏（Split-Screen）模式下，屏幕上同时存在两个 Activity，但**只有一个能拥有焦点**：

```
分屏模式:
┌─────────────────────┐
│   Activity A         │  ← 触摸此区域 → A 获得焦点
│  (Task 1, 上半屏)    │
├─────────────────────┤
│   Activity B         │  ← 触摸此区域 → B 获得焦点
│  (Task 2, 下半屏)    │
└─────────────────────┘

焦点规则：
  - 最后被触摸的那一侧 Activity 获得焦点
  - 另一侧 Activity 失去焦点 → onWindowFocusChanged(false)
  - KEY 事件只发给获得焦点的 Activity
```

**问题场景一**：应用悬浮窗（TYPE_APPLICATION_OVERLAY）意外抢走焦点：

```
某 App 在分屏模式下创建了一个悬浮窗用于显示通知：
  WindowManager.LayoutParams params = new LayoutParams();
  params.type = TYPE_APPLICATION_OVERLAY;
  // 忘记设置 FLAG_NOT_FOCUSABLE!
  windowManager.addView(overlayView, params);

结果：
  悬浮窗在 Z-order 上高于两个分屏 Activity
  → updateFocusedWindowLocked()
  → canReceiveKeys(overlayView) == true（未设置 NOT_FOCUSABLE）
  → FocusedWindow = 悬浮窗
  → 两个分屏 Activity 都失去焦点
  → 物理键盘输入、BACK 键都被悬浮窗拦截
```

**修复**：为悬浮窗设置正确的 flags：

```java
WindowManager.LayoutParams params = new LayoutParams();
params.type = TYPE_APPLICATION_OVERLAY;
params.flags = FLAG_NOT_FOCUSABLE | FLAG_NOT_TOUCH_MODAL;
windowManager.addView(overlayView, params);
```

**问题场景二**：分屏切换时焦点抖动：

当用户拖动分屏分界线调整两个 App 的大小比例时，由于连续的 `setBounds()` → `performLayout()` → `updateFocusedWindowLocked()`，焦点可能在两个 Activity 之间快速切换，导致两个 App 的 `onWindowFocusChanged` 被频繁回调。如果 App 在 `onWindowFocusChanged(true)` 中执行了重量级操作（如恢复播放、重新加载数据），会导致明显的性能问题。

---

### 场景四：IME 窗口获取焦点

**问题模式**

IME（输入法）窗口的类型是 `TYPE_INPUT_METHOD`，它有特殊的焦点规则：

```
IME 焦点规则:
  - IME 窗口默认设置 FLAG_NOT_FOCUSABLE
  - 因此 IME 窗口本身不会成为 FocusedWindow
  - KEY 事件仍然发给 App 的焦点窗口
  - 但 App 焦点窗口的 InputStage 管线中:
    ImeInputStage 会将 KEY 事件转发给 IME 进程处理
    → 如果 IME 消费了事件 → App 不会看到
    → 如果 IME 未消费 → 事件继续在 App 管线中传递
```

**BACK 键的特殊处理**：

```
用户按 BACK 键时（IME 显示中）:

1. InputDispatcher → App's FocusedWindow（KeyEvent BACK）
2. ViewRootImpl → ImeInputStage
3. ImeInputStage → InputMethodManager.dispatchKeyEvent()
4. InputMethodManager → IME 进程
5. IME 进程: "我正在显示，BACK 键应该关闭我"
   → 返回 HANDLED → IME 隐藏
   → App 不会收到 BACK 键事件!

用户再次按 BACK 键时（IME 已隐藏）:
1. InputDispatcher → App's FocusedWindow（KeyEvent BACK）
2. ViewRootImpl → ImeInputStage
3. ImeInputStage → InputMethodManager: IME 未显示
   → 返回 NOT_HANDLED → 事件继续传递
4. ViewPostImeInputStage → Activity.onBackPressed()
```

**稳定性风险**：如果 IME 进程无响应（挂起或 ANR），`ImeInputStage` 的事件转发会阻塞。由于 `ImeInputStage` 是 `AsyncInputStage`，它会将事件异步发送到 IME 并等待回复。如果 IME 长时间不回复，事件在 App 管线中"卡住"，后续事件全部排队。虽然这不直接触发 InputDispatcher 的 ANR（因为 `finishInputEvent` 是在事件进入 App 管线后就回复的），但会导致用户感知的按键无响应。

**排查方法**：

```bash
# 检查 IME 状态
adb shell dumpsys input_method

# 检查 IME 窗口在 Input 系统中的状态
adb shell dumpsys input | grep -A 5 "InputMethod"

# 检查 App 焦点窗口的 ImeInputStage 是否卡住
# Systrace 中搜索 "ImeInputStage"
```

---

## 7. 与 Input 系列的交叉引用

本篇是 Window 系列与 Input 系列的桥梁，以下是关键的交叉引用关系：

### 7.1 InputDispatcher 的焦点处理 — 详见 Input 系列 03

[Input 系列-03-InputDispatcher](../Input/03-InputDispatcher.md) 详细分析了 `findFocusedWindowTargetsLocked()` 和 `findTouchedWindowTargetsLocked()` 的完整实现。关键要点：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
int32_t InputDispatcher::findFocusedWindowTargetsLocked(
        nsecs_t currentTime, const EventEntry& entry,
        std::vector<InputTarget>& inputTargets, nsecs_t* nextWakeupTime) {
    
    // 获取当前 Display 的焦点窗口
    sp<InputWindowHandle> focusedWindowHandle =
            getFocusedWindowHandleLocked(entry.displayId);
    
    if (focusedWindowHandle == nullptr) {
        // 没有焦点窗口
        if (mFocusedApplicationHandlesByDisplay.count(entry.displayId) != 0) {
            // 有焦点 App → 等待窗口出现
            // 这就是"no focused window but has focused application" ANR 的触发逻辑
            if (currentTime > mNoFocusedWindowTimeoutTime) {
                // 等待超时 → ANR!
                onAnrLocked(mFocusedApplicationHandlesByDisplay[entry.displayId]);
                return INPUT_EVENT_INJECTION_PENDING;
            }
            // 还没超时 → 继续等待
            *nextWakeupTime = mNoFocusedWindowTimeoutTime;
            return INPUT_EVENT_INJECTION_PENDING;
        }
        // 连焦点 App 都没有 → 直接丢弃
        return INPUT_EVENT_INJECTION_FAILED;
    }
    
    // 有焦点窗口 → 添加到目标列表
    addWindowTargetLocked(focusedWindowHandle, ..., inputTargets);
    return INPUT_EVENT_INJECTION_SUCCEEDED;
}
```

### 7.2 Input ANR 的无焦点窗口检测 — 详见 Input 系列 06

[Input 系列-06-Input ANR](../Input/06-InputANR.md) 详细分析了 ANR 的超时检测机制。与本篇相关的核心逻辑：

```
ANR 超时检测的两条路径:

路径一: 无焦点窗口 ANR (本篇重点)
  条件: FocusedApplication != null && FocusedWindow == null
  超时: 5000ms (从 setFocusedApplication 开始计时)
  信息: "Waiting because no window has focus but there is a focused application..."
  根因: Activity 启动慢 → Window 未及时添加

路径二: 窗口无响应 ANR
  条件: FocusedWindow != null && waitQueue 超时
  超时: 5000ms (从事件发送给 App 开始计时)
  信息: "Input dispatching timed out (Waiting to send key event because..."
  根因: App 主线程阻塞 → finishInputEvent 未及时回复
```

### 7.3 InputChannel 注册与焦点的关系 — 详见 Input 系列 04

[Input 系列-04-InputChannel 与跨进程投递](../Input/04-InputChannel与跨进程投递.md) 详细分析了 `openInputChannel()` 和 `registerInputChannel()` 的过程。与本篇焦点管理的关联：

```
窗口必须完成 InputChannel 注册后，才能成为有效的焦点窗口:

addWindow()
  → openInputChannel()
    → InputDispatcher::registerInputChannel()
      → Connection 创建完成
  → updateFocusedWindowLocked()
    → setFocusedWindow(token)
      → InputDispatcher::setFocusedWindow()
        → 查找 token 对应的 Connection
        → 如果 Connection 存在 → 焦点设置成功
        → 如果 Connection 不存在 → 放入 mPendingFocusRequests
```

如果 `registerInputChannel` 和 `setFocusedWindow` 的时序出现竞态——`setFocusedWindow` 先于 `registerInputChannel` 执行（极罕见），焦点请求会被 pending，直到 `registerInputChannel` 完成后自动激活。

---

## 总结

焦点管理是 WMS 与 Input 系统交互的核心，也是 Input ANR 中最复杂的问题类型的根源。作为稳定性架构师，以下五个要点必须掌握：

1. **FocusedApplication ≠ FocusedWindow**。前者是"承诺"（Activity 开始 Resume 时设置），后者是"事实"（Window 添加且可见后设置）。两者之间的时间差是"无焦点窗口 ANR"的根本原因。混淆这两个概念是焦点 ANR 排查方向错误的最常见原因。

2. **Touch 事件不使用 FocusedWindow**。Touch 事件通过 Z-order Hit Test 选择目标窗口，不依赖焦点。只有 KEY 事件（BACK、音量键、字符键等）才使用 FocusedWindow。因此"无焦点窗口 ANR"只会被 KEY 事件触发。

3. **焦点空窗期的长度 = Activity 启动的总耗时**。从 `setFocusedApplication` 到 `setFocusedWindow` 的间隔，等于 `Application.onCreate` + `Activity.onCreate` + `addWindow` + 首帧绘制的总时间。缩短这条链路是降低焦点 ANR 的根本手段。

4. **InputMonitor 是 WMS→InputDispatcher 的唯一桥梁**。`updateInputWindowsLw()` 执行在 `mGlobalLock` 内，锁竞争会导致窗口信息同步延迟。延迟的后果是 InputDispatcher 使用过期信息——Touch 事件发错窗口、KEY 事件找不到焦点窗口。

5. **排查焦点 ANR 的第一步永远是 `dumpsys input`**。检查 `FocusedApplications` 和 `FocusedWindows` 的值：如果 FocusedApp 有值但 FocusedWindows 为 `<none>`，就是焦点空窗期问题；如果两者都有值但 waitQueue 超时，就是 App 主线程阻塞问题。

**排查速查：**

```
焦点 ANR 排查路径:

Step 1: adb shell dumpsys input
  → 检查 FocusedApplications 和 FocusedWindows

Step 2: 判断 ANR 类型
  → FocusedApp=X, FocusedWindow=<none>
    → "无焦点窗口 ANR"
    → 检查 Application.onCreate / Activity.onCreate 耗时
    → traces.txt 主线程栈定位阻塞点
    → 优化启动链路

  → FocusedApp=X, FocusedWindow=Y
    → "窗口无响应 ANR"
    → 检查 App 主线程是否阻塞
    → traces.txt 主线程栈定位阻塞点
    → 详见 Input 系列 06

Step 3: adb shell dumpsys window | grep -E "mCurrentFocus|mFocusedApp"
  → 交叉验证 WMS 侧的焦点状态

Step 4: Systrace / Perfetto
  → 搜索 "updateFocusedWindow" / "setFocusedApplication"
  → 测量焦点空窗期的精确长度
  → 定位链路上的瓶颈阶段
```

---

## 附录：核心源码路径索引

| 文件名 | 完整路径 | 说明 |
|:---|:---|:---|
| `InputMonitor.java` | `frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java` | WMS→InputDispatcher 的桥梁，焦点同步与窗口信息同步 |
| `DisplayContent.java` | `frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java` | `updateFocusedWindowLocked()` / `findFocusedWindow()` / `setFocusedApp()` |
| `WindowManagerService.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | `updateFocusedWindowLocked()` 总入口 |
| `WindowState.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | `canReceiveKeys()` 焦点资格判定 |
| `ActivityRecord.java` | `frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java` | FocusedApplication 的源头，`mInputApplicationHandle` |
| `RootWindowContainer.java` | `frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java` | `updateFocusedAppIfNeeded()` 全局焦点 App 计算 |
| `ActivityTaskManagerService.java` | `frameworks/base/services/core/java/com/android/server/wm/ActivityTaskManagerService.java` | Activity 启动入口，触发 `setFocusedApp` |
| `InputDispatcher.cpp` | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` | `setFocusedApplication()` / `setFocusedWindow()` / `findFocusedWindowTargetsLocked()` |
| `InputDispatcher.h` | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.h` | `mFocusedApplicationHandlesByDisplay` / `mFocusedWindowHandlesByDisplay` 定义 |
| `ViewRootImpl.java` | `frameworks/base/core/java/android/view/ViewRootImpl.java` | `setView()` → `addWindow()` → Window 创建入口；`ImeInputStage` IME 事件截获 |

---

下一篇 [08-窗口显示性能：TTID、TTFD 与启动优化](08-窗口显示性能TTID与TTFD.md) 将从窗口视角分析启动性能指标 TTID / TTFD 的测量、首帧绘制的关键路径、Starting Window 机制，以及从 Window 层面优化启动速度的实战策略。
