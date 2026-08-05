# Input 与其他子系统交互

## 引言

Android Input 系统并非独立工作，它与进程管理、显示系统、电源管理等多个子系统紧密协作。本文将分析 Input 系统与这些关键子系统的交互机制。

---

## 1. 交互关系总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Input 系统                                  │
│                          (InputFlinger/IMS)                              │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│  WindowManager│         │  ActivityManager│        │  PowerManager │
│     (WMS)     │         │     (AMS)     │         │     (PMS)     │
│               │         │               │         │               │
│ - 窗口管理    │         │ - 进程管理    │         │ - 电源管理    │
│ - 焦点管理    │         │ - ANR 处理    │         │ - 唤醒管理    │
│ - 触摸区域    │         │ - 前台应用    │         │ - 屏幕超时    │
└───────────────┘         └───────────────┘         └───────────────┘
        │                           │                           │
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│DisplayManager │         │  进程优先级   │         │  休眠/唤醒    │
│     (DMS)     │         │               │         │               │
│               │         │ - 前台优先    │         │ - 用户活动    │
│ - 显示旋转    │         │ - 事件分发    │         │ - 屏幕亮度    │
│ - 多显示器    │         │ - OOM adj     │         │               │
└───────────────┘         └───────────────┘         └───────────────┘
```

---

## 2. Input 与进程管理 (AMS)

### 2.1 前台进程判定

```java
// frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java

private boolean computeOomAdjLocked(ProcessRecord app, ...) {
    // 输入事件分发目标的进程被视为前台进程
    
    // 焦点 Activity 所在进程
    if (app == mAtmInternal.getTopApp()) {
        adj = ProcessList.FOREGROUND_APP_ADJ;
        procState = PROCESS_STATE_TOP;
        schedGroup = SCHED_GROUP_TOP_APP;
    }
    
    // 接收输入事件的进程
    if (app.hasTopUi()) {
        adj = ProcessList.FOREGROUND_APP_ADJ;
    }
    
    return success;
}
```

### 2.2 ANR 处理

```java
// AMS 处理 Input ANR

void inputDispatchingTimedOut(ProcessRecord proc, 
                               ActivityRecord activity,
                               String reason) {
    // 检查进程状态
    if (proc.isDebugging()) {
        // 正在调试, 不触发 ANR
        return;
    }
    
    // 触发 ANR 处理
    appNotResponding(proc, activity, activity.shortComponentName,
            activity.app, false /* aboveSystem */, reason);
}
```

### 2.3 进程优先级对输入的影响

```java
// 输入事件分发考虑进程优先级

int32_t InputDispatcher::findTouchedWindowTargetsLocked(...) {
    // 检查窗口所属进程的状态
    const WindowInfo& info = *windowHandle->getInfo();
    
    // 被杀死的进程不接收事件
    if (!isWindowReadyForMoreInputLocked(windowHandle)) {
        // 窗口不可用, 跳过
    }
}
```

---

## 3. Input 与电源管理 (PMS)

### 3.1 用户活动通知

```java
// frameworks/base/services/core/java/com/android/server/policy/PhoneWindowManager.java

@Override
public int interceptKeyBeforeQueueing(KeyEvent event, int policyFlags) {
    // 通知用户活动
    if ((policyFlags & WindowManagerPolicy.FLAG_PASS_TO_USER) != 0) {
        // 按键事件表示用户活动
        userActivity(event.getEventTime(), event.getDisplayId());
    }
    
    // 处理电源键
    if (keyCode == KeyEvent.KEYCODE_POWER) {
        // 特殊处理电源键
        if (down) {
            interceptPowerKeyDown(event, interactive);
        } else {
            interceptPowerKeyUp(event, interactive);
        }
    }
}

private void userActivity(long eventTime, int displayId) {
    // 通知 PowerManagerService
    mPowerManagerInternal.userActivity(displayId, eventTime, 
            PowerManager.USER_ACTIVITY_EVENT_OTHER);
}
```

### 3.2 屏幕唤醒

```java
// 输入事件可以唤醒屏幕

@Override
public int interceptKeyBeforeQueueing(KeyEvent event, int policyFlags) {
    boolean isWakeKey = (policyFlags & WindowManagerPolicy.FLAG_WAKE) != 0;
    
    // 特定按键可以唤醒屏幕
    switch (keyCode) {
        case KeyEvent.KEYCODE_POWER:
            isWakeKey = true;
            break;
            
        case KeyEvent.KEYCODE_WAKEUP:
            isWakeKey = true;
            break;
    }
    
    if (isWakeKey && !mInteractive) {
        // 唤醒屏幕
        result |= ACTION_WAKE_UP;
    }
}

// Native 层处理唤醒
void NativeInputManager::handleInterceptActions(int wmActions, nsecs_t when,
                                                 uint32_t& policyFlags) {
    if (wmActions & WM_ACTION_WAKE_UP) {
        // 设置唤醒标志
        policyFlags |= POLICY_FLAG_WAKE;
        
        // 调用 PowerManager 唤醒
        android_server_PowerManagerService_userActivity(when, 
                POWER_MANAGER_BUTTON_ACTIVITY);
    }
}
```

### 3.3 屏幕超时

```java
// 用户活动重置屏幕超时

// PowerManagerService.java
void userActivity(int displayId, long eventTime, int event) {
    synchronized (mLock) {
        // 重置超时计时器
        if (eventTime > mLastUserActivityTime) {
            mLastUserActivityTime = eventTime;
            mDirty |= DIRTY_USER_ACTIVITY;
            
            // 更新电源状态
            updatePowerStateLocked();
        }
    }
}
```

---

## 4. Input 与显示系统 (DMS)

### 4.1 显示旋转

```java
// 显示旋转影响触摸坐标转换

// InputReader 根据显示方向转换坐标
void TouchInputMapper::configure(...) {
    // 获取显示信息
    DisplayViewport viewport = mDevice->getAssociatedDisplayViewport();
    
    // 根据显示方向设置坐标转换
    mOrientedRanges.x.min = 0;
    mOrientedRanges.y.min = 0;
    
    switch (viewport.orientation) {
        case DISPLAY_ORIENTATION_90:
            mOrientedRanges.x.max = mDisplayHeight;
            mOrientedRanges.y.max = mDisplayWidth;
            break;
        case DISPLAY_ORIENTATION_180:
            mOrientedRanges.x.max = mDisplayWidth;
            mOrientedRanges.y.max = mDisplayHeight;
            break;
        case DISPLAY_ORIENTATION_270:
            mOrientedRanges.x.max = mDisplayHeight;
            mOrientedRanges.y.max = mDisplayWidth;
            break;
        default: // DISPLAY_ORIENTATION_0
            mOrientedRanges.x.max = mDisplayWidth;
            mOrientedRanges.y.max = mDisplayHeight;
            break;
    }
}
```

### 4.2 多显示器支持

```cpp
// 每个显示器独立的输入状态

class InputDispatcher {
    // 每个显示器的焦点窗口
    std::unordered_map<int32_t /*displayId*/, 
                       sp<WindowInfoHandle>> mFocusedWindowHandlesByDisplay;
    
    // 每个显示器的触摸状态
    std::unordered_map<int32_t /*displayId*/, 
                       TouchState> mTouchStatesByDisplay;
    
    // 每个显示器的窗口列表
    std::unordered_map<int32_t /*displayId*/,
                       std::vector<sp<WindowInfoHandle>>> mWindowHandlesByDisplay;
};

// 设置输入设备与显示器的关联
void InputReader::configure(...) {
    // 触摸设备通常关联到特定显示器
    if (mParameters.associatedDisplayId >= 0) {
        // 使用指定的显示器
        mDisplayId = mParameters.associatedDisplayId;
    } else {
        // 使用默认显示器
        mDisplayId = ADISPLAY_ID_DEFAULT;
    }
}
```

### 4.3 显示视口同步

```java
// WMS 更新显示视口到 InputManager

void DisplayContent::updateDisplayInfo() {
    // 获取显示信息
    mDisplayInfo = mDisplay.getDisplayInfo();
    
    // 创建 DisplayViewport
    DisplayViewport viewport = new DisplayViewport();
    viewport.displayId = mDisplayId;
    viewport.orientation = mDisplayInfo.rotation;
    viewport.logicalFrame.set(0, 0, mDisplayInfo.logicalWidth, 
                               mDisplayInfo.logicalHeight);
    viewport.physicalFrame.set(0, 0, mDisplayInfo.getNaturalWidth(),
                               mDisplayInfo.getNaturalHeight());
    
    // 更新到 InputManager
    mWmService.mInputManager.setDisplayViewports(viewports);
}
```

---

## 5. Input 与输入法 (IME)

### 5.1 输入法窗口

```java
// 输入法窗口的特殊处理

// InputMethodManagerService.java
void attachNewInputWindow(...) {
    // 输入法窗口通常设置 FLAG_NOT_FOCUSABLE
    // 因此不接收焦点, 按键事件不直接发送给它
    
    // 输入法通过 InputConnection 与应用通信
    InputConnection ic = mInputConnection;
    ic.commitText("text", 1);
}

// 输入法窗口不拦截触摸事件
void setupInputMethodWindow(...) {
    WindowManager.LayoutParams lp = new WindowManager.LayoutParams();
    lp.type = TYPE_INPUT_METHOD;
    lp.flags = FLAG_NOT_FOCUSABLE | FLAG_LAYOUT_IN_SCREEN;
}
```

### 5.2 按键事件与输入法

```java
// ViewRootImpl InputStage 链中的 IME 处理

final class ImeInputStage extends AsyncInputStage {
    @Override
    protected int onProcess(QueuedInputEvent q) {
        if (mLastWasImTarget && !isInLocalFocusMode()) {
            // 发送给输入法处理
            InputMethodManager imm = InputMethodManager.getInstance();
            if (imm != null) {
                // 输入法可能消费按键事件
                int result = imm.dispatchInputEvent(event, ...);
                if (result == InputMethodManager.DISPATCH_HANDLED) {
                    return FINISH_HANDLED;
                }
            }
        }
        return FORWARD;
    }
}
```

---

## 6. Input 与无障碍服务

### 6.1 无障碍事件注入

```java
// AccessibilityService 可以注入输入事件

public abstract class AccessibilityService extends Service {
    // 注入触摸事件
    public final boolean dispatchGesture(GestureDescription gesture,
                                         GestureResultCallback callback,
                                         Handler handler) {
        // 通过系统服务注入触摸事件
        mAccessibilityServiceInfo.getConnection()
            .dispatchGesture(gesture, callback);
    }
    
    // 注入按键事件
    public final boolean performGlobalAction(int action) {
        // 如 GLOBAL_ACTION_BACK, GLOBAL_ACTION_HOME
    }
}
```

### 6.2 触摸探索模式

```java
// 无障碍触摸探索

// AccessibilityInputFilter.java
class TouchExplorer {
    void onMotionEvent(MotionEvent event) {
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                // 单指: 探索模式
                // 双指: 滚动模式
                break;
                
            case MotionEvent.ACTION_MOVE:
                if (mTouchExploring) {
                    // 发送 AccessibilityEvent.TYPE_TOUCH_EXPLORATION_GESTURE_START
                    // 朗读触摸位置的内容
                }
                break;
        }
    }
}
```

---

## 7. Input 与系统 UI

### 7.1 导航栏手势

```java
// 手势导航

// NavigationBarEdgeBackGestureHandler.java
class EdgeBackGestureHandler {
    private InputMonitor mInputMonitor;
    
    void onInputEvent(InputEvent ev) {
        if (ev instanceof MotionEvent) {
            MotionEvent event = (MotionEvent) ev;
            
            // 检测边缘滑动
            if (event.getAction() == MotionEvent.ACTION_DOWN) {
                float x = event.getX();
                
                // 左边缘或右边缘
                if (x < mEdgeWidth || x > mDisplayWidth - mEdgeWidth) {
                    mIsTracking = true;
                }
            }
            
            if (mIsTracking && event.getAction() == MotionEvent.ACTION_MOVE) {
                // 检测是否是返回手势
                float dx = event.getX() - mDownX;
                if (Math.abs(dx) > mSwipeThreshold) {
                    // 触发返回
                    performBack();
                }
            }
        }
    }
}
```

### 7.2 状态栏下拉

```java
// 状态栏下拉手势

// StatusBarTouchHandler.java
void onTouchEvent(MotionEvent event) {
    switch (event.getAction()) {
        case MotionEvent.ACTION_DOWN:
            if (event.getY() < mStatusBarHeight) {
                mTracking = true;
            }
            break;
            
        case MotionEvent.ACTION_MOVE:
            if (mTracking) {
                float dy = event.getY() - mDownY;
                if (dy > mPullDownThreshold) {
                    // 展开通知面板
                    expandNotificationPanel();
                }
            }
            break;
    }
}
```

---

## 8. 本章小结

Input 系统与其他子系统的交互：

| 子系统 | 交互内容 |
|-------|---------|
| ActivityManager | ANR 处理、进程优先级 |
| PowerManager | 用户活动、屏幕唤醒/超时 |
| DisplayManager | 坐标转换、多显示器 |
| 输入法 | InputConnection、按键处理 |
| 无障碍 | 事件注入、触摸探索 |
| 系统 UI | 导航手势、状态栏下拉 |

关键交互点：
1. 输入事件影响进程前台状态和 OOM 优先级
2. 用户活动通知延长屏幕超时
3. 显示旋转需要坐标转换
4. 输入法通过 InputConnection 间接接收按键

下一篇将介绍 Input 性能分析与问题排查。

---

## 参考资料

1. `frameworks/base/services/core/java/com/android/server/power/PowerManagerService.java`
2. `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`
3. `frameworks/base/services/core/java/com/android/server/display/DisplayManagerService.java`
