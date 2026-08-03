# Input 与 WindowManager 交互

## 引言

Input 系统与 WindowManager 紧密协作，WMS 负责管理窗口的层级、位置和区域，Input 系统需要这些信息来确定事件的分发目标。本文将深入分析两者的交互机制。

---

## 1. 交互概览

### 1.1 交互架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        WindowManagerService                              │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  窗口管理                                                           │ │
│  │  ├── 窗口栈 (Window Stack)                                         │ │
│  │  ├── Z-Order 排序                                                  │ │
│  │  ├── 窗口可见性                                                    │ │
│  │  └── 窗口区域计算                                                  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              │ InputMonitor                             │
│                              ▼                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  InputMonitor                                                       │ │
│  │  ├── collectInputWindowHandles()  收集窗口信息                     │ │
│  │  ├── updateInputWindowsLw()       更新到 Input 系统                │ │
│  │  └── setInputFocusLw()           设置焦点窗口                       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     │ IMS 接口
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       InputManagerService                                │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  setInputWindows()      接收窗口列表                                │ │
│  │  setFocusedWindow()     接收焦点窗口                                │ │
│  │  setFocusedApplication() 接收焦点应用                               │ │
│  │  registerInputChannel() 注册 InputChannel                          │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     │ Native
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         InputDispatcher                                  │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  mWindowHandlesByDisplay   窗口句柄列表                             │ │
│  │  mFocusedWindowHandlesByDisplay  焦点窗口                          │ │
│  │  mTouchStatesByDisplay     触摸状态                                 │ │
│  │  mConnectionsByToken       窗口连接                                 │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 主要交互内容

| 交互方向 | 内容 | 用途 |
|---------|------|------|
| WMS → IMS | 窗口列表 | 触摸事件命中测试 |
| WMS → IMS | 焦点窗口 | 按键事件分发 |
| WMS → IMS | 焦点应用 | ANR 检测 |
| WMS → IMS | InputChannel | 事件传输通道 |
| IMS → WMS | 焦点请求 | 请求移动焦点 |
| IMS → WMS | ANR 通知 | 应用无响应 |

---

## 2. 窗口信息同步

### 2.1 InputMonitor

```java
// frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java

class InputMonitor {
    private final WindowManagerService mService;
    private final InputManagerService mInputManager;
    private final int mDisplayId;
    
    // 窗口句柄列表 (按 Z-Order 排序)
    private final InputWindowHandle[] mInputWindowHandles = 
        new InputWindowHandle[0];
    
    // 焦点窗口
    private WindowState mInputFocus;
    
    // 更新标志
    private boolean mUpdateInputWindowsNeeded = true;
    
    void updateInputWindowsLw(boolean force) {
        if (!force && !mUpdateInputWindowsNeeded) {
            return;
        }
        mUpdateInputWindowsNeeded = false;
        
        // 收集所有窗口信息
        final SparseArray<InputWindowHandle> inputWindowHandles = 
            new SparseArray<>();
        
        // 遍历窗口 (按 Z-Order 从上到下)
        mService.mRoot.forAllWindows(w -> {
            populateInputWindowHandle(inputWindowHandles, w);
        }, true /* traverseTopToBottom */);
        
        // 转换为数组
        InputWindowHandle[] handles = new InputWindowHandle[inputWindowHandles.size()];
        for (int i = 0; i < inputWindowHandles.size(); i++) {
            handles[i] = inputWindowHandles.valueAt(i);
        }
        
        // 发送到 InputDispatcher
        mInputManager.setInputWindows(handles, mDisplayId);
    }
    
    private void populateInputWindowHandle(
            SparseArray<InputWindowHandle> inputWindowHandles,
            WindowState w) {
        
        if (w.mInputChannel == null || w.mRemoved) {
            return;
        }
        
        final InputWindowHandle handle = w.mInputWindowHandle;
        
        // 更新窗口信息
        handle.name = w.getName();
        handle.token = w.mInputChannel.getToken();
        handle.layoutParamsType = w.mAttrs.type;
        handle.layoutParamsFlags = w.mAttrs.flags;
        handle.displayId = mDisplayId;
        
        // 更新窗口区域
        final Rect frame = w.getFrame();
        handle.frameLeft = frame.left;
        handle.frameTop = frame.top;
        handle.frameRight = frame.right;
        handle.frameBottom = frame.bottom;
        
        // 更新可触摸区域
        final Region touchableRegion = w.getTouchableRegion();
        handle.touchableRegion.set(touchableRegion);
        
        // 更新状态标志
        handle.visible = w.isVisibleLw();
        handle.focusable = w.canReceiveKeys();
        handle.hasWallpaper = w.hasWallpaper;
        
        // 更新变换矩阵
        w.getTransformationMatrix(handle.transform);
        
        // 更新 Owner 信息
        handle.ownerPid = w.mSession.mPid;
        handle.ownerUid = w.mSession.mUid;
        
        // 更新输入特性
        handle.inputFeatures = getInputFeatures(w);
        
        inputWindowHandles.put(w.mInputWindowHandle.hashCode(), handle);
    }
}
```

### 2.2 窗口信息更新时机

```java
// 窗口状态变化触发更新

// 1. 窗口添加
void addWindow(Session session, IWindow client, ...) {
    // ...
    mInputMonitor.setUpdateInputWindowsNeeded();
    updateFocusedWindowLocked(UPDATE_FOCUS_WILL_PLACE_SURFACES, false);
}

// 2. 窗口移除
void removeWindow(Session session, IWindow client) {
    // ...
    mInputMonitor.setUpdateInputWindowsNeeded();
}

// 3. 窗口属性变化
void relayoutWindow(Session session, IWindow client, ...) {
    // ...
    if (windowChanged) {
        mInputMonitor.setUpdateInputWindowsNeeded();
    }
}

// 4. 焦点变化
void updateFocusedWindowLocked(int mode, boolean updateInputWindows) {
    WindowState newFocus = computeFocusedWindowLocked();
    if (mCurrentFocus != newFocus) {
        // ...
        if (updateInputWindows) {
            mInputMonitor.updateInputWindowsLw(false);
        }
    }
}

// 5. 窗口动画
void performSurfacePlacement() {
    // 动画完成后更新
    if (mInputMonitor.updateInputWindowsNeeded) {
        mInputMonitor.updateInputWindowsLw(false);
    }
}
```

---

## 3. Z-Order 与触摸区域

### 3.1 Z-Order 排序

```
屏幕
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  StatusBar (TYPE_STATUS_BAR)                Z = 2000        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Toast (TYPE_TOAST)                         Z = 1100        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Dialog (TYPE_APPLICATION)                  Z = 2           │   │
│  │  ┌───────────────────────────────────────────────────────┐ │   │
│  │  │                                                       │ │   │
│  │  │                                                       │ │   │
│  │  └───────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Activity Window (TYPE_APPLICATION)         Z = 1           │   │
│  │                                                             │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  NavigationBar (TYPE_NAVIGATION_BAR)        Z = 2100        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

触摸事件命中测试: 从高 Z-Order 到低 Z-Order 遍历
```

### 3.2 触摸区域计算

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java

void getTouchableRegion(Region outRegion) {
    // 初始为窗口框架
    final Rect frame = getFrame();
    outRegion.set(frame);
    
    // 裁剪到父窗口
    if (mAttrs.surfaceInsets.left != 0 || mAttrs.surfaceInsets.right != 0 ||
            mAttrs.surfaceInsets.top != 0 || mAttrs.surfaceInsets.bottom != 0) {
        // 处理阴影等边距
        outRegion.intersect(
            frame.left + mAttrs.surfaceInsets.left,
            frame.top + mAttrs.surfaceInsets.top,
            frame.right - mAttrs.surfaceInsets.right,
            frame.bottom - mAttrs.surfaceInsets.bottom);
    }
    
    // 应用用户指定的触摸区域
    if (mGivenTouchableRegion.isEmpty()) {
        // 使用完整框架
    } else {
        // 与用户指定区域相交
        outRegion.op(mGivenTouchableRegion, Region.Op.INTERSECT);
    }
    
    // 裁剪到显示边界
    outRegion.op(getDisplayFrame(), Region.Op.INTERSECT);
    
    // 处理圆角
    if (mWindowFrames.hasRoundedCorners()) {
        cropRegionForRoundedCorners(outRegion);
    }
}
```

### 3.3 Native 层命中测试

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

sp<WindowInfoHandle> InputDispatcher::findTouchedWindowAtLocked(
        int32_t displayId, int32_t x, int32_t y, bool* outIsTouchModal) {
    
    // 获取该显示器的窗口列表 (已按 Z-Order 排序)
    const std::vector<sp<WindowInfoHandle>>& windowHandles = 
        getWindowHandlesLocked(displayId);
    
    // 从上到下遍历
    for (const sp<WindowInfoHandle>& windowHandle : windowHandles) {
        const WindowInfo& info = *windowHandle->getInfo();
        
        // 检查窗口是否可见
        if (!info.visible) {
            continue;
        }
        
        // 检查是否在窗口框架内
        if (!info.frameContainsPoint(x, y)) {
            continue;
        }
        
        // 检查是否在可触摸区域内
        if (!info.touchableRegionContainsPoint(x, y)) {
            // 不在可触摸区域, 但可能是 modal 窗口
            if (isWindowObscuredAtPointLocked(windowHandle, x, y)) {
                // 被遮挡
                continue;
            }
        }
        
        // 检查输入特性
        if (info.inputFeatures.test(WindowInfo::Feature::DROP_INPUT)) {
            // 窗口不接收输入
            continue;
        }
        
        // 找到目标窗口
        return windowHandle;
    }
    
    return nullptr;
}

// 检查点是否被其他窗口遮挡
bool InputDispatcher::isWindowObscuredAtPointLocked(
        const sp<WindowInfoHandle>& windowHandle,
        int32_t x, int32_t y) const {
    
    int32_t displayId = windowHandle->getInfo()->displayId;
    const std::vector<sp<WindowInfoHandle>>& windowHandles = 
        getWindowHandlesLocked(displayId);
    
    for (const sp<WindowInfoHandle>& otherHandle : windowHandles) {
        if (otherHandle == windowHandle) {
            // 遍历到目标窗口, 停止
            break;
        }
        
        const WindowInfo& otherInfo = *otherHandle->getInfo();
        
        if (otherInfo.visible && 
            otherInfo.frameContainsPoint(x, y) &&
            otherInfo.touchableRegionContainsPoint(x, y)) {
            // 被其他窗口遮挡
            return true;
        }
    }
    
    return false;
}
```

---

## 4. InputChannel 管理

### 4.1 创建 InputChannel

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java

void openInputChannel(InputChannel outInputChannel) {
    if (mInputChannel != null) {
        throw new IllegalStateException("Already has an input channel");
    }
    
    // 创建名称
    String name = getName();
    
    // 创建 Socket 对
    InputChannel[] inputChannels = InputChannel.openInputChannelPair(name);
    
    // Server channel 保留在 system_server
    mInputChannel = inputChannels[0];
    mClientChannel = inputChannels[1];
    
    // 创建 InputWindowHandle
    mInputWindowHandle = new InputWindowHandle(
        mInputChannel.getToken(), this);
    
    // 注册到 InputDispatcher
    mWmService.mInputManager.registerInputChannel(mInputChannel);
    
    // 传出 client channel 给应用
    if (outInputChannel != null) {
        mClientChannel.transferTo(outInputChannel);
        mClientChannel.dispose();
        mClientChannel = null;
    }
}
```

### 4.2 注销 InputChannel

```java
void removeInputChannel() {
    if (mInputChannel != null) {
        // 从 InputDispatcher 注销
        mWmService.mInputManager.unregisterInputChannel(mInputChannel);
        
        mInputChannel.dispose();
        mInputChannel = null;
    }
    
    mInputWindowHandle = null;
}
```

### 4.3 Native 层注册

```cpp
// com_android_server_input_InputManagerService.cpp

static void nativeRegisterInputChannel(JNIEnv* env, jclass clazz,
        jlong ptr, jobject inputChannelObj) {
    
    NativeInputManager* im = reinterpret_cast<NativeInputManager*>(ptr);
    
    // 获取 InputChannel
    sp<InputChannel> inputChannel = 
        android_view_InputChannel_getInputChannel(env, inputChannelObj);
    
    // 注册到 InputDispatcher
    status_t status = im->getInputManager()->getDispatcher()
        ->registerInputChannel(inputChannel);
}
```

```cpp
// InputDispatcher.cpp

status_t InputDispatcher::registerInputChannel(
        const std::shared_ptr<InputChannel>& inputChannel) {
    
    { // acquire lock
        std::scoped_lock _l(mLock);
        
        // 检查是否已注册
        sp<IBinder> token = inputChannel->getToken();
        if (getConnectionLocked(token) != nullptr) {
            return BAD_VALUE;
        }
        
        // 创建 Connection
        sp<Connection> connection = new Connection(inputChannel, false);
        
        // 添加到映射表
        mConnectionsByToken[token] = connection;
        
        // 注册到 Looper 以接收完成信号
        mLooper->addFd(inputChannel->getFd(), 0, ALOOPER_EVENT_INPUT,
                       handleReceiveCallback, this);
        
    } // release lock
    
    // 唤醒分发线程
    mLooper->wake();
    return OK;
}
```

---

## 5. 特殊窗口处理

### 5.1 系统窗口

```java
// 状态栏、导航栏等系统窗口的特殊处理

// TYPE_STATUS_BAR
if (attrs.type == TYPE_STATUS_BAR) {
    // 状态栏窗口
    // - 始终在最上层
    // - 需要接收触摸事件 (下拉展开)
    handle.inputFeatures = 0;
}

// TYPE_NAVIGATION_BAR
if (attrs.type == TYPE_NAVIGATION_BAR) {
    // 导航栏窗口
    // - 需要接收触摸事件 (手势导航)
    // - 可能是透明区域
    handle.inputFeatures = 0;
}

// TYPE_INPUT_METHOD
if (attrs.type == TYPE_INPUT_METHOD) {
    // 输入法窗口
    // - 通常不可聚焦 (FLAG_NOT_FOCUSABLE)
    // - 事件通过 InputConnection 传递
    handle.focusable = false;
}
```

### 5.2 壁纸窗口

```java
// TYPE_WALLPAPER - 壁纸窗口通常不接收输入
if (attrs.type == TYPE_WALLPAPER) {
    handle.inputFeatures |= WindowInfo.Feature.DROP_INPUT;
}
```

### 5.3 窗口标志处理

```java
private int getInputFeatures(WindowState w) {
    int features = 0;
    
    // FLAG_NOT_TOUCHABLE - 不接收触摸事件
    if ((w.mAttrs.flags & FLAG_NOT_TOUCHABLE) != 0) {
        features |= WindowInfo.Feature.DROP_INPUT;
    }
    
    // FLAG_NOT_TOUCH_MODAL - 允许触摸穿透
    if ((w.mAttrs.flags & FLAG_NOT_TOUCH_MODAL) != 0) {
        // 触摸区域外的事件传递给下层窗口
    }
    
    // FLAG_WATCH_OUTSIDE_TOUCH - 接收区域外触摸
    if ((w.mAttrs.flags & FLAG_WATCH_OUTSIDE_TOUCH) != 0) {
        // ACTION_OUTSIDE 事件
    }
    
    return features;
}
```

---

## 6. 多显示器支持

### 6.1 每个显示器的 InputMonitor

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java

class DisplayContent {
    // 每个显示器有独立的 InputMonitor
    InputMonitor mInputMonitor;
    
    DisplayContent(Display display, ...) {
        mInputMonitor = new InputMonitor(mWmService, mDisplayId);
    }
}
```

### 6.2 跨显示器焦点

```java
// 焦点在不同显示器间切换

void updateFocusedWindowLocked(int mode, boolean updateInputWindows) {
    // 遍历所有显示器
    for (int i = mRoot.getChildCount() - 1; i >= 0; i--) {
        final DisplayContent dc = mRoot.getChildAt(i);
        
        // 更新每个显示器的焦点窗口
        dc.updateFocusedWindowLocked();
    }
    
    // 确定全局焦点显示器
    final DisplayContent focusedDisplay = determineFocusedDisplayLocked();
    
    if (mFocusedDisplayId != focusedDisplay.mDisplayId) {
        // 焦点显示器变化
        mFocusedDisplayId = focusedDisplay.mDisplayId;
        
        // 通知 InputDispatcher
        mInputManager.setFocusedDisplay(mFocusedDisplayId);
    }
}
```

---

## 7. 本章小结

Input 与 WindowManager 的交互是事件分发的基础：

| 交互内容 | 方法 | 作用 |
|---------|------|------|
| 窗口列表 | setInputWindows() | 触摸命中测试 |
| 焦点窗口 | setFocusedWindow() | 按键分发目标 |
| InputChannel | registerInputChannel() | 事件传输通道 |
| 窗口区域 | touchableRegion | 限制触摸范围 |

关键机制：
1. InputMonitor 负责收集和同步窗口信息
2. Z-Order 决定触摸事件的优先级
3. touchableRegion 决定窗口的可触摸范围
4. 每个显示器独立管理输入状态

下一篇将详细介绍按键事件的处理流程。

---

## 参考资料

1. `frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java`
2. `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`
3. Android WindowManager 与 Input 源码分析
