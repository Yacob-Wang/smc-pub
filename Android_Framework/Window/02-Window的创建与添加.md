# 02-Window 的创建与添加：从 addView 到 Surface 诞生

## 1. 在 Window 架构中的位置

### 1.1 Window 创建在 WMS 架构中的定位

Window 的创建与添加是整个窗口管理系统的入口——没有 Window 的诞生，就没有后续的布局、渲染、动画和焦点管理。本篇覆盖的是一个 Window 从"App 调用 `addView()`"到"Surface 在 SurfaceFlinger 中分配 Layer"再到"InputChannel 完成注册、焦点初始化"的完整生命周期。

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WMS 窗口管理全景                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │  App 进程     │    │  system_server    │    │  SurfaceFlinger  │  │
│  │              │    │                  │    │                  │  │
│  │ WindowManager│    │  WMS             │    │  Layer           │  │
│  │  .addView()  │───▶│  .addWindow()    │───▶│  分配 & 合成      │  │
│  │              │    │                  │    │                  │  │
│  │ ViewRootImpl │    │  WindowState     │    │  SurfaceControl  │  │
│  │  .setView()  │    │  WindowToken     │    │  Surface         │  │
│  │              │    │  WindowContainer │    │                  │  │
│  └──────┬───────┘    └────────┬─────────┘    └──────────────────┘  │
│         │                     │                                     │
│         │   Binder IPC        │                                     │
│         │  (IWindowSession)   │                                     │
│         │                     ▼                                     │
│         │            ┌──────────────────┐                           │
│         │            │  InputDispatcher │                           │
│         │            │  焦点管理         │                           │
│         └───────────▶│  InputChannel    │                           │
│           register   │  注册            │                           │
│                      └──────────────────┘                           │
│                                                                     │
│  ════════════════════════════════════════════════════════════════   │
│  本篇覆盖范围：                                                     │
│  App addView() → WMS addWindow() → Surface 创建                    │
│  → InputChannel 注册 → 焦点初始化 → Window 移除                     │
│  ════════════════════════════════════════════════════════════════   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 本篇覆盖的完整流程

一个 Window 从无到有，需要经历以下关键阶段：

```
App 进程                          system_server                    SurfaceFlinger
─────────                        ──────────────                   ──────────────
WindowManager.addView(view, lp)
    │
    ▼
WindowManagerGlobal.addView()
    │ 创建 ViewRootImpl
    ▼
ViewRootImpl.setView()
    │ 创建 InputChannel
    │ Binder 调用
    ▼
Session.addToDisplayAsUser() ───▶ WMS.addWindow()
                                   │ 权限校验
                                   │ WindowToken 验证
                                   │ 创建 WindowState
                                   │ 分配 Layer 层级
                                   │ openInputChannel()
                                   │ updateFocusedWindowLocked()
                                   ▼
                                 返回 ◀──────────────────────────────
    │
    ▼
ViewRootImpl.setView() 继续
    │ 注册 InputEventReceiver
    │ requestLayout()
    ▼
ViewRootImpl.performTraversals()
    │ relayoutWindow()
    ▼
Session.relayout() ──────────────▶ WMS.relayoutWindow()
                                   │ createSurfaceLocked() ──────▶ SurfaceFlinger
                                   │                               分配 Layer
                                   │                               创建 BufferQueue
                                   ▼
                                 返回 Surface ◀──────────────────
    │
    ▼
Surface 就绪，开始绘制
```

这个流程涉及两次关键的跨进程 Binder 调用：**第一次 `addWindow()` 注册窗口元数据和 InputChannel**，**第二次 `relayoutWindow()` 真正创建 Surface**。理解这两步分离的设计是理解后续 Window 生命周期管理的基础。

---

## 2. App 端发起 — WindowManager.addView()

### 2.1 WindowManagerImpl.addView()

当 App 需要添加一个新的 Window（Activity 的 DecorView、Dialog、PopupWindow、Toast 等），最终都会调用到 `WindowManagerImpl.addView()`。

> 源码：`frameworks/base/core/java/android/view/WindowManagerImpl.java`

```java
// frameworks/base/core/java/android/view/WindowManagerImpl.java
public final class WindowManagerImpl implements WindowManager {
    private final WindowManagerGlobal mGlobal = WindowManagerGlobal.getInstance();
    private final Context mContext;
    private final Window mParentWindow;

    @Override
    public void addView(@NonNull View view, @NonNull ViewGroup.LayoutParams params) {
        applyTokenOverride(params);
        mGlobal.addView(view, params, mContext.getDisplayNoVerify(),
                mParentWindow, mContext.getUserId());
    }
}
```

`WindowManagerImpl` 本身只是一个薄包装层，真正的逻辑委托给了全局单例 `WindowManagerGlobal`。每个 `WindowManagerImpl` 实例与一个 `Context`（Activity / Application / Service）绑定，这个关联关系决定了后续 `WindowToken` 的来源。

### 2.2 WindowManagerGlobal.addView() — 核心协调者

> 源码：`frameworks/base/core/java/android/view/WindowManagerGlobal.java`

`WindowManagerGlobal` 是进程级单例，维护着当前进程中所有 Window 的三个核心列表：

```java
// frameworks/base/core/java/android/view/WindowManagerGlobal.java
public final class WindowManagerGlobal {
    // 所有已添加的 DecorView（根 View）
    private final ArrayList<View> mViews = new ArrayList<>();
    // 所有已创建的 ViewRootImpl
    private final ArrayList<ViewRootImpl> mRoots = new ArrayList<>();
    // 所有 Window 的 LayoutParams
    private final ArrayList<WindowManager.LayoutParams> mParams = new ArrayList<>();
    // 正在被移除的 View（等待 die 动画完成）
    private final ArraySet<View> mDyingViews = new ArraySet<>();

    public void addView(View view, ViewGroup.LayoutParams params,
            Display display, Window parentWindow, int userId) {
        // 参数校验
        if (view == null) {
            throw new IllegalArgumentException("view must not be null");
        }
        if (display == null) {
            throw new IllegalArgumentException("display must not be null");
        }
        if (!(params instanceof WindowManager.LayoutParams)) {
            throw new IllegalArgumentException("Params must be WindowManager.LayoutParams");
        }

        final WindowManager.LayoutParams wparams = (WindowManager.LayoutParams) params;

        // 如果有父窗口，调整 LayoutParams（子窗口类型处理）
        if (parentWindow != null) {
            parentWindow.adjustLayoutParamsForSubWindow(wparams);
        }

        ViewRootImpl root;
        View panelParentView = null;

        synchronized (mLock) {
            // ★ 重复添加检测 —— WindowLeaked 的根源之一
            int index = findViewLocked(view, false);
            if (index >= 0) {
                // 如果 view 已在 mDyingViews 中（正在被移除），立即清理
                if (mDyingViews.contains(view)) {
                    mRoots.get(index).doDie();
                } else {
                    throw new IllegalStateException(
                        "View " + view + " has already been added to the window manager.");
                }
            }

            // 对于子窗口（TYPE_APPLICATION_PANEL 等），找到父窗口的 ViewRootImpl
            if (wparams.type >= WindowManager.LayoutParams.FIRST_SUB_WINDOW &&
                    wparams.type <= WindowManager.LayoutParams.LAST_SUB_WINDOW) {
                final int count = mViews.size();
                for (int i = 0; i < count; i++) {
                    if (mRoots.get(i).mWindow.asBinder() == wparams.token) {
                        panelParentView = mViews.get(i);
                    }
                }
            }

            // ★ 创建 ViewRootImpl —— App 与 WMS 之间的桥梁
            root = new ViewRootImpl(view.getContext(), display);

            view.setLayoutParams(wparams);

            mViews.add(view);
            mRoots.add(root);
            mParams.add(wparams);
        }

        // ★ 关键调用：ViewRootImpl.setView() 触发 WMS 注册
        try {
            root.setView(view, wparams, panelParentView, userId);
        } catch (RuntimeException e) {
            synchronized (mLock) {
                final int index = findViewLocked(view, false);
                if (index >= 0) {
                    removeViewLocked(index, true);
                }
            }
            throw e;
        }
    }
}
```

**稳定性架构师视角**：

| 风险点 | 触发条件 | 异常类型 | 影响 |
| :--- | :--- | :--- | :--- |
| 重复 addView | 同一个 View 实例被 add 两次 | `IllegalStateException` | App Crash |
| Activity 泄漏 | Activity destroy 时未 remove Window | `WindowLeaked` (Warning) | 内存泄漏 |
| 错误线程调用 | 非主线程调用 addView | `CalledFromWrongThreadException` | App Crash |

`WindowManagerGlobal` 在 `finalize()` 中会检测是否有未移除的 View，如果发现就输出 `WindowLeaked` 警告。这不是 Crash，但指示了 Activity 泄漏。

### 2.3 ViewRootImpl — App 与 WMS 之间的桥梁

> 源码：`frameworks/base/core/java/android/view/ViewRootImpl.java`

`ViewRootImpl` 是 Android 窗口系统中最核心的类之一，它承担了以下职责：

```
ViewRootImpl
├── 持有 View 树的根节点（DecorView）
├── 持有 IWindowSession（与 WMS 通信的 Binder 代理）
├── 持有 Surface（绘制目标）
├── 持有 InputChannel（接收输入事件）
├── 驱动 View 的 measure / layout / draw 三大流程
├── 处理配置变更（旋转、DPI 变化等）
└── Choreographer 垂直同步信号的接收者
```

`ViewRootImpl` 的构造函数中完成了关键的初始化：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java (简化)
public ViewRootImpl(Context context, Display display) {
    mContext = context;
    // 获取 IWindowSession —— 与 WMS 通信的 Binder 连接
    mWindowSession = WindowManagerGlobal.getWindowSession();
    mDisplay = display;
    // mWindow 是一个 IWindow.Stub —— WMS 回调 App 的通道
    mWindow = new W(this);
    // Choreographer 用于接收 VSYNC 信号
    mChoreographer = Choreographer.getInstance();
    // 当前线程即为 UI 线程，后续 checkThread() 将以此为基准
    mThread = Thread.currentThread();
}
```

### 2.4 ViewRootImpl.setView() — 关键入口

`setView()` 是整个 Window 创建流程中最关键的方法，它完成了 App 端的全部初始化工作，并通过 Binder 向 WMS 注册窗口。

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java (简化)
public void setView(View view, WindowManager.LayoutParams attrs,
        View panelParentView, int userId) {
    synchronized (this) {
        if (mView == null) {
            mView = view;

            // ===== 阶段一：初始化本地状态 =====
            mWindowAttributes.copyFrom(attrs);
            attrs = mWindowAttributes;
            mSoftInputMode = attrs.softInputMode;
            mWindowAttributesChanged = true;

            // 设置 View 树的根
            mAttachInfo.mRootView = view;

            // ===== 阶段二：请求首次布局 =====
            // requestLayout() 最终会触发 performTraversals()
            // performTraversals() 中调用 relayoutWindow() 创建 Surface
            requestLayout();

            // ===== 阶段三：创建 InputChannel =====
            InputChannel inputChannel = null;
            if ((mWindowAttributes.inputFeatures
                    & WindowManager.LayoutParams.INPUT_FEATURE_NO_INPUT_CHANNEL) == 0) {
                inputChannel = new InputChannel();
            }

            // ===== 阶段四：通过 Binder 向 WMS 注册 Window =====
            try {
                mOrigWindowType = mWindowAttributes.type;
                mAttachInfo.mRecomputeGlobalAttributes = true;
                collectViewAttributes();

                // ★ 核心 Binder 调用 —— 跨进程到 WMS
                res = mWindowSession.addToDisplayAsUser(
                        mWindow,           // IWindow 回调接口
                        mWindowAttributes, // LayoutParams
                        getHostVisibility(),
                        mDisplay.getDisplayId(),
                        userId,
                        mInsetsController.getRequestedVisibleTypes(),
                        inputChannel,      // InputChannel（out 参数，WMS 填充）
                        mTempInsets,
                        mTempControls);
            } catch (RemoteException e) {
                // Binder 调用失败
                mAdded = false;
                mView = null;
                throw new RuntimeException("Adding window failed", e);
            }

            // ===== 阶段五：处理 WMS 返回结果 =====
            if (res < WindowManagerGlobal.ADD_OKAY) {
                // addWindow 失败，根据错误码抛出对应异常
                switch (res) {
                    case WindowManagerGlobal.ADD_BAD_APP_TOKEN:
                    case WindowManagerGlobal.ADD_BAD_SUBWINDOW_TOKEN:
                        throw new WindowManager.BadTokenException(
                            "Unable to add window -- token " + attrs.token
                            + " is not valid; is your activity running?");
                    case WindowManagerGlobal.ADD_NOT_APP_TOKEN:
                        throw new WindowManager.BadTokenException(
                            "Unable to add window -- token " + attrs.token
                            + " is not for an application");
                    case WindowManagerGlobal.ADD_DUPLICATE_ADD:
                        throw new WindowManager.BadTokenException(
                            "Unable to add window -- window " + mWindow
                            + " has already been added");
                    case WindowManagerGlobal.ADD_PERMISSION_DENIED:
                        throw new WindowManager.InvalidDisplayException(
                            "Unable to add window -- permission denied"
                            + " for window type " + mWindowAttributes.type);
                    // ... 更多错误码
                }
            }

            // ===== 阶段六：注册 InputEventReceiver =====
            if (inputChannel != null) {
                // WindowInputEventReceiver 处理从 InputDispatcher 发来的事件
                mInputEventReceiver = new WindowInputEventReceiver(
                        inputChannel, Looper.myLooper());
            }

            // 设置 View 的 parent 为 ViewRootImpl
            view.assignParent(this);

            // ===== 阶段七：注册 InputChannel 到 InputDispatcher =====
            // （InputChannel 的 server 端由 WMS 在 addWindow 中注册到 InputDispatcher）
            // App 端的 InputChannel 在创建 WindowInputEventReceiver 时
            // 被关联到当前线程的 Looper（用于接收事件的 fd 注册到 epoll）
        }
    }
}
```

**稳定性架构师视角**：`setView()` 中的六个阶段是严格有序的。任何一个阶段失败都可能导致后续阶段不执行，进而产生资源泄漏或不一致状态。

| 阶段 | 失败后果 | 恢复机制 |
| :--- | :--- | :--- |
| Binder 调用失败 | RemoteException → 清理 mView/mAdded | 异常冒泡到 `WindowManagerGlobal.addView()` 中 catch，执行 removeViewLocked |
| WMS 返回错误码 | BadTokenException / InvalidDisplayException | App Crash，需上层捕获 |
| InputChannel 创建失败 | 窗口无法接收输入事件 | 无自动恢复，窗口"死"了 |
| InputEventReceiver 注册失败 | 事件无法分发到 View 树 | 无自动恢复 |

---

## 3. WMS 端处理 — addWindow() 完整流程

### 3.1 addWindow() 概述

`WMS.addWindow()` 是窗口管理系统中最重要、最复杂的单个方法。它完成了从权限校验到窗口状态初始化的所有工作。

> 源码：`frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java (简化)
public int addWindow(Session session, IWindow client, LayoutParams attrs,
        int viewVisibility, int displayId, int requestUserId,
        InsetsVisibilities requestedVisibilities,
        InputChannel outInputChannel, InsetsState outInsetsState,
        InsetsSourceControl[] outActiveControls) {

    // ===== Step 1: 基础参数校验 =====
    int type = attrs.type;
    synchronized (mGlobalLock) {
        // 获取目标 Display
        final DisplayContent displayContent = getDisplayContentOrCreate(displayId, attrs.token);
        if (displayContent == null) {
            return WindowManagerGlobal.ADD_INVALID_DISPLAY;
        }

        // 检查是否重复添加
        if (mWindowMap.containsKey(client.asBinder())) {
            return WindowManagerGlobal.ADD_DUPLICATE_ADD;
        }

        // ===== Step 2: 权限校验 =====
        // 系统窗口（type >= 2000）需要 INTERNAL_SYSTEM_WINDOW 权限
        if (type >= FIRST_SYSTEM_WINDOW && type <= LAST_SYSTEM_WINDOW) {
            if (!hasSystemWindowPermission(session.mPid, session.mUid)) {
                // TYPE_APPLICATION_OVERLAY 需要 SYSTEM_ALERT_WINDOW 权限
                if (type == TYPE_APPLICATION_OVERLAY) {
                    if (!Settings.canDrawOverlays(/* context */)) {
                        return WindowManagerGlobal.ADD_PERMISSION_DENIED;
                    }
                } else {
                    return WindowManagerGlobal.ADD_PERMISSION_DENIED;
                }
            }
        }

        // ===== Step 3: WindowToken 验证 =====
        // 不同窗口类型要求不同的 Token
        WindowToken token = displayContent.getWindowToken(
                attrs.token != null ? attrs.token : client.asBinder());

        final int rootType = isSubWindow(type)
                ? attrs.type & WindowManager.LayoutParams.TYPE_APPLICATION_MEDIA_OVERLAY
                : type;

        if (token == null) {
            // Application 窗口（type 1-99）必须有预先注册的 Token
            if (rootType >= FIRST_APPLICATION_WINDOW
                    && rootType <= LAST_APPLICATION_WINDOW) {
                return WindowManagerGlobal.ADD_BAD_APP_TOKEN;
            }
            // 其他类型可以隐式创建 Token
            token = new WindowToken.Builder(this, client.asBinder(), type)
                    .setDisplayContent(displayContent)
                    .build();
        } else if (rootType >= FIRST_APPLICATION_WINDOW
                && rootType <= LAST_APPLICATION_WINDOW) {
            // Application 窗口的 token 必须是 ActivityRecord
            ActivityRecord activity = token.asActivityRecord();
            if (activity == null) {
                return WindowManagerGlobal.ADD_NOT_APP_TOKEN;
            }
            // 检查 Activity 是否还在运行
            if (activity.finishing) {
                return WindowManagerGlobal.ADD_APP_EXITING;
            }
        }

        // ===== Step 4: 子窗口验证 =====
        WindowState parentWindow = null;
        if (isSubWindow(type)) {
            parentWindow = windowForClientLocked(null, attrs.token, false);
            if (parentWindow == null) {
                return WindowManagerGlobal.ADD_BAD_SUBWINDOW_TOKEN;
            }
            if (parentWindow.mAttrs.type >= FIRST_SUB_WINDOW
                    && parentWindow.mAttrs.type <= LAST_SUB_WINDOW) {
                // 不允许子窗口嵌套子窗口
                return WindowManagerGlobal.ADD_BAD_SUBWINDOW_TOKEN;
            }
        }

        // ===== Step 5: 创建 WindowState =====
        final WindowState win = new WindowState(this, session, client, token,
                parentWindow, attrs, viewVisibility, session.mUid, userId,
                session.mCanAddInternalSystemWindow);

        // 执行 WindowManagerPolicy 的窗口准入策略
        final DisplayPolicy displayPolicy = displayContent.getDisplayPolicy();
        displayPolicy.adjustWindowParamsLw(win, win.mAttrs);

        res = displayPolicy.validateAddingWindowLw(attrs, callingPid, callingUid);
        if (res != ADD_OKAY) {
            return res;
        }

        // ===== Step 6: 打开 InputChannel =====
        final boolean openInputChannels = (outInputChannel != null
                && (attrs.inputFeatures
                    & WindowManager.LayoutParams.INPUT_FEATURE_NO_INPUT_CHANNEL) == 0);
        if (openInputChannels) {
            win.openInputChannel(outInputChannel);
        }

        // ===== Step 7: 将 WindowState 加入 WindowToken 的子节点 =====
        win.mToken.addWindow(win);

        // 注册到全局映射表
        mWindowMap.put(client.asBinder(), win);

        // ===== Step 8: 更新焦点 =====
        boolean focusChanged = false;
        if (win.canReceiveKeys()) {
            focusChanged = updateFocusedWindowLocked(
                    UPDATE_FOCUS_WILL_ASSIGN_LAYERS,
                    false /* updateInputWindows */);
        }

        // ===== Step 9: 更新 InputDispatcher 的窗口信息 =====
        if (focusChanged) {
            mInputMonitor.setInputFocusLw(displayContent.mCurrentFocus, false);
        }
        mInputMonitor.updateInputWindowsLw(false);

        // 对客户端输出 Insets 状态
        win.getCompatInsetsState().toOutInsetsState(outInsetsState);

    } // end synchronized

    return res;
}
```

### 3.2 addWindow() 各步骤的稳定性分析

| 步骤 | 操作 | 失败返回码 | 常见触发场景 | 稳定性影响 |
| :--- | :--- | :--- | :--- | :--- |
| Step 1 | Display 校验 | `ADD_INVALID_DISPLAY` | 外接显示器断开瞬间添加窗口 | App Crash (BadTokenException) |
| Step 2 | 权限校验 | `ADD_PERMISSION_DENIED` | 三方 App 试图添加系统窗口 | App Crash |
| Step 3 | Token 验证 | `ADD_BAD_APP_TOKEN` / `ADD_NOT_APP_TOKEN` | Activity 已销毁但 Dialog 仍在 show | App Crash (BadTokenException) |
| Step 4 | 子窗口验证 | `ADD_BAD_SUBWINDOW_TOKEN` | 父窗口已移除 | App Crash |
| Step 5 | 创建 WindowState | N/A | 内存不足 | OOM → system_server 重启 |
| Step 6 | 打开 InputChannel | N/A | socketpair 失败（fd 耗尽） | 窗口无法接收输入 |
| Step 8 | 更新焦点 | N/A | 焦点切换竞态 | 焦点丢失 → Input ANR |

### 3.3 WMS 全局映射表 mWindowMap

`mWindowMap` 是 WMS 的核心数据结构，以 `IBinder`（即 `IWindow.Stub`）为 key 映射到 `WindowState`：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
final HashMap<IBinder, WindowState> mWindowMap = new HashMap<>();
```

每个 App 中的 `ViewRootImpl` 都持有一个唯一的 `IWindow.Stub` 对象（即 `ViewRootImpl.W`），它作为 WMS 回调 App 的通道。这个 `IBinder` 对象同时也是 `mWindowMap` 中定位 `WindowState` 的 key。

```
App 进程                                     system_server
──────────                                  ───────────────
ViewRootImpl
  ├── mWindow (W extends IWindow.Stub) ─── IBinder ──▶ mWindowMap[IBinder] = WindowState
  └── mWindowSession (IWindowSession) ──── Binder ───▶ Session (处理 App 的请求)
```

---

## 4. WindowToken 验证机制

### 4.1 WindowToken 是什么

WindowToken 是 WMS 中用于标识窗口"身份/凭证"的对象。它回答了一个核心问题：**你有什么资格添加这个类型的窗口？**

> 源码：`frameworks/base/services/core/java/com/android/server/wm/WindowToken.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowToken.java (简化)
class WindowToken extends WindowContainer<WindowState> {
    final IBinder token;       // 客户端传入的 Binder token
    final int windowType;      // 窗口类型
    boolean mPersistOnEmpty;   // Token 下没有 WindowState 时是否保留
    boolean mRoundedCornerOverlay;
    // ...
}
```

WindowToken 在 WindowContainer 层级中位于 DisplayContent 之下、WindowState 之上：

```
DisplayContent
  ├── TaskDisplayArea
  │     └── Task
  │           └── ActivityRecord (extends WindowToken)
  │                 └── WindowState (DecorView 对应的窗口)
  ├── WindowToken (TYPE_STATUS_BAR)
  │     └── WindowState (状态栏窗口)
  ├── WindowToken (TYPE_INPUT_METHOD)
  │     └── WindowState (输入法窗口)
  └── WindowToken (TYPE_APPLICATION_OVERLAY)
        └── WindowState (悬浮窗)
```

### 4.2 不同窗口类型的 Token 要求

| 窗口类型范围 | 类型说明 | Token 要求 | Token 来源 |
| :--- | :--- | :--- | :--- |
| `1-99` (FIRST/LAST_APPLICATION_WINDOW) | 应用窗口 | 必须有 `ActivityRecord` 类型的 Token | ActivityStarter 启动 Activity 时创建 |
| `1000-1999` (FIRST/LAST_SUB_WINDOW) | 子窗口 | 必须有父窗口的 `IWindow` Binder | 父窗口的 `ViewRootImpl.mWindow` |
| `2000-2999` (FIRST/LAST_SYSTEM_WINDOW) | 系统窗口 | `INTERNAL_SYSTEM_WINDOW` 权限 | system_server 内部创建 |
| `TYPE_APPLICATION_OVERLAY` (2038) | 应用悬浮窗 | `SYSTEM_ALERT_WINDOW` 权限 | 运行时权限申请 |
| `TYPE_INPUT_METHOD` (2011) | 输入法窗口 | 特殊的 IME Token | `InputMethodManagerService` 分配 |
| `TYPE_WALLPAPER` (2013) | 壁纸窗口 | 特殊的 Wallpaper Token | `WallpaperManagerService` 分配 |

### 4.3 Token 验证源码

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
// addWindow() 中的 Token 验证逻辑（简化）

WindowToken token = displayContent.getWindowToken(attrs.token);

if (token == null) {
    // ---- Token 不存在 ----

    if (rootType >= FIRST_APPLICATION_WINDOW && rootType <= LAST_APPLICATION_WINDOW) {
        // 应用窗口必须有预注册的 Token（来自 ActivityRecord）
        // 如果没有 → Activity 可能已被销毁
        return WindowManagerGlobal.ADD_BAD_APP_TOKEN;
    }

    if (rootType == TYPE_INPUT_METHOD) {
        // IME 窗口必须有 IMMS 预注册的 Token
        return WindowManagerGlobal.ADD_BAD_APP_TOKEN;
    }

    if (rootType == TYPE_WALLPAPER) {
        // 壁纸窗口必须有 WallpaperManagerService 预注册的 Token
        return WindowManagerGlobal.ADD_BAD_APP_TOKEN;
    }

    // 对于其他类型（系统窗口、悬浮窗等），可以隐式创建 Token
    token = new WindowToken.Builder(this, attrs.token, type)
            .setDisplayContent(displayContent)
            .build();

} else if (rootType >= FIRST_APPLICATION_WINDOW && rootType <= LAST_APPLICATION_WINDOW) {
    // ---- Token 存在，但需要验证类型 ----

    ActivityRecord activity = token.asActivityRecord();
    if (activity == null) {
        // Token 存在但不是 ActivityRecord → 类型不匹配
        return WindowManagerGlobal.ADD_NOT_APP_TOKEN;
    }
    if (activity.finishing) {
        // Activity 正在 finish → 窗口来不及了
        return WindowManagerGlobal.ADD_APP_EXITING;
    }
}
```

### 4.4 四个经典的 BadTokenException 场景

**场景一：Activity 已销毁但 Dialog.show() 仍在调用**

这是线上 BadTokenException 中占比最高的场景（60%+）：

```
java.lang.RuntimeException: Unable to add window -- token android.os.BinderProxy@xxxx
  is not valid; is your activity running?
    at android.view.ViewRootImpl.setView(ViewRootImpl.java:1098)
    at android.view.WindowManagerGlobal.addView(WindowManagerGlobal.java:409)
    at android.view.WindowManagerImpl.addView(WindowManagerImpl.java:109)
    at android.app.Dialog.show(Dialog.java:340)
```

根因：异步回调（网络请求、Handler.postDelayed）在 Activity 已经 `onDestroy()` 后触发了 `Dialog.show()`。此时 Activity 对应的 `ActivityRecord` 已从 WMS 中移除，Token 不存在。

**场景二：Token 类型与窗口类型不匹配**

```
java.lang.RuntimeException: Unable to add window -- token XXX is not for an application
```

根因：试图用 Application Context 启动 Dialog。Application 没有 `ActivityRecord` Token，而 Dialog 默认类型是 `TYPE_APPLICATION`，需要 Activity Token。

**场景三：Token 已从 WMS 移除（时序竞态）**

```
java.lang.RuntimeException: Unable to add window -- token XXX is not valid
```

根因：在多线程/多 Activity 切换场景下，Token 在 `addWindow()` 执行前的瞬间被 WMS 移除。这种情况出现在 Activity A 快速启动 Activity B，B 的窗口添加与 A 的 Token 移除发生竞态。

**场景四：系统窗口权限不足**

```
java.lang.RuntimeException: Unable to add window -- permission denied
  for window type 2010
```

根因：三方 App 试图添加 `TYPE_PHONE`、`TYPE_SYSTEM_ALERT` 等系统窗口，但缺少 `SYSTEM_ALERT_WINDOW` 权限。Android 6.0+ 需要运行时权限，Android 8.0+ 要求使用 `TYPE_APPLICATION_OVERLAY`（type=2038）。

---

## 5. Surface 的创建与管理

### 5.1 Surface 不是在 addWindow 中创建的

这是一个常见误解：**Surface 并不在 `addWindow()` 中创建**。`addWindow()` 只注册了窗口元数据（WindowState）和 InputChannel。Surface 的真正创建发生在后续的 `relayoutWindow()` 调用中。

这种"先注册后创建"的两阶段设计有其合理性：

1. **分离关注点**：`addWindow()` 负责权限/Token/焦点等逻辑验证；`relayoutWindow()` 负责与 SurfaceFlinger 交互
2. **按需创建**：不是所有窗口都需要 Surface（如 `FLAG_NOT_TOUCHABLE` 的纯输入窗口）
3. **复用机制**：窗口不可见时可以销毁 Surface 释放内存，重新可见时通过 `relayoutWindow()` 再次创建

### 5.2 从 requestLayout 到 Surface 诞生

```
ViewRootImpl.setView()
    │ requestLayout()
    ▼
ViewRootImpl.scheduleTraversals()
    │ 通过 Choreographer 等待下一个 VSYNC
    ▼
ViewRootImpl.doTraversal()
    │
    ▼
ViewRootImpl.performTraversals()
    │
    ▼
ViewRootImpl.relayoutWindow()
    │ Binder 调用
    ▼
Session.relayout() ──▶ WMS.relayoutWindow()
                         │
                         ▼
                      WindowStateAnimator.createSurfaceLocked()
                         │
                         ▼
                      SurfaceControl.Builder
                         │ .setName(windowName)
                         │ .setBufferSize(w, h)
                         │ .setFormat(pixelFormat)
                         │ .setParent(parentSurfaceControl)
                         │ .build()
                         │
                         ▼  Binder → SurfaceFlinger
                      SurfaceFlinger 分配 Layer + BufferQueue
                         │
                         ▼
                      返回 SurfaceControl → 客户端获得 Surface
```

### 5.3 WMS.relayoutWindow() 中的 Surface 创建

> 源码：`frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java (简化)
public int relayoutWindow(Session session, IWindow client,
        WindowManager.LayoutParams attrs, int requestedWidth, int requestedHeight,
        int viewVisibility, int flags, int seq, int lastSyncSeqId,
        ClientWindowFrames outFrames, MergedConfiguration mergedConfiguration,
        SurfaceControl outSurfaceControl, InsetsState outInsetsState,
        InsetsSourceControl.Array outActiveControls, Bundle outSyncSeqIdBundle) {

    synchronized (mGlobalLock) {
        final WindowState win = windowForClientLocked(session, client, false);
        if (win == null) {
            return 0;
        }

        // 更新窗口属性
        if (attrs != null) {
            win.mAttrs.copyFrom(attrs);
        }

        // ★ 核心：创建或更新 Surface
        final boolean shouldRelayout = viewVisibility == View.VISIBLE
                && (win.mViewVisibility != viewVisibility
                    || win.mRelayoutCalled == false
                    || /* 尺寸变化 */);

        if (shouldRelayout) {
            result = createSurfaceControl(outSurfaceControl, result, win, winAnimator);
        }

        // 计算窗口 frame
        displayContent.computeWindowLayout();

        // 更新 Insets
        win.updateInsetsState();
    }
    return result;
}
```

### 5.4 createSurfaceLocked() — Surface 的真正诞生

> 源码：`frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java (简化)
WindowSurfaceController createSurfaceLocked() {
    final WindowState w = mWin;

    if (mSurfaceController != null) {
        return mSurfaceController;
    }

    // 计算 Surface 尺寸
    int width = w.mRequestedWidth;
    int height = w.mRequestedHeight;

    // 通过 SurfaceControl.Builder 创建 Surface
    // 这里最终会通过 Binder 调用到 SurfaceFlinger
    mSurfaceController = new WindowSurfaceController(
            w.makeSurfaceTag(),
            width, height,
            w.mAttrs.format,     // PixelFormat
            0 /* flags */,
            w.mSession,
            w /* windowState */);

    // 设置 Surface 的初始属性
    mSurfaceController.setPosition(/* x */, /* y */);
    mSurfaceController.setLayer(/* z-order */);

    return mSurfaceController;
}
```

### 5.5 SurfaceControl vs Surface vs SurfaceSession

这三个概念经常被混淆，必须区分清楚：

| 概念 | 所在进程 | 生命周期 | 职责 |
| :--- | :--- | :--- | :--- |
| `SurfaceSession` | system_server | 与 App Session 1:1 | 与 SurfaceFlinger 的连接通道，一个 App 进程一个 |
| `SurfaceControl` | system_server (主)、App (副本) | 与 WindowState 绑定 | Surface 的控制句柄，用于设置位置/大小/层级/透明度等属性 |
| `Surface` | App 进程 | 与绘制周期绑定 | 绘制目标，持有 BufferQueue 的 Producer 端，Canvas.lockCanvas() 的底层 |

数据流关系：

```
system_server                              App 进程
─────────────                             ──────────
SurfaceSession ──(Binder)──▶ SurfaceFlinger 连接

SurfaceControl ──(包含)──▶ Layer ID
     │
     │  通过 Binder 传递给 App
     ▼
                                          Surface (从 SurfaceControl 获得)
                                            │
                                            ├── BufferQueue.Producer
                                            │     └── Canvas.lockCanvas()
                                            │     └── Canvas.unlockCanvasAndPost()
                                            │
                                            └── EGLSurface (硬件加速路径)
                                                  └── OpenGL ES 渲染
```

### 5.6 Surface 创建失败的稳定性影响

Surface 创建失败会导致 `OutOfResourcesException`，表现为窗口黑屏：

```
android.view.Surface$OutOfResourcesException: Exception locking surface
    at android.view.Surface.nativeLockCanvas(Native Method)
    at android.view.Surface.lockCanvas(Surface.java:315)
```

常见原因：

| 原因 | 触发条件 | 日志关键字 |
| :--- | :--- | :--- |
| GPU 内存耗尽 | 大量窗口同时存在（特别是大尺寸 Surface） | `GraphicBufferAllocator: alloc failed` |
| fd 耗尽 | 进程 fd 数超过 `ulimit -n`（默认 1024） | `Too many open files` |
| SurfaceFlinger Layer 数量超限 | Layer 泄漏导致 SurfaceFlinger 拒绝新建 | `createLayer failed` |
| Binder 通信失败 | system_server 负载过高 | `TransactionTooLargeException` |

---

## 6. InputChannel 注册与焦点初始化

### 6.1 InputChannel 的创建 — openInputChannel()

> 源码：`frameworks/base/services/core/java/com/android/server/wm/WindowState.java`

在 `addWindow()` 的 Step 6 中，`win.openInputChannel(outInputChannel)` 创建了一对 Unix Domain Socket：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java (简化)
void openInputChannel(InputChannel outInputChannel) {
    if (mInputChannel != null) {
        throw new IllegalStateException("Window already has an input channel.");
    }
    String name = getName();

    // ★ 创建 InputChannel 对 —— 本质是 socketpair
    InputChannel[] inputChannels = InputChannel.openInputChannelPair(name);
    mInputChannel = inputChannels[0];        // server 端 → 留在 WMS
    mInputChannelToken = mInputChannel.getToken();

    // ★ 注册 server 端到 InputDispatcher
    mWmService.mInputManager.registerInputChannel(mInputChannel);

    // ★ client 端通过 Binder 传回 App
    inputChannels[1].transferTo(outInputChannel);
    inputChannels[1].dispose();
}
```

底层实现使用 `socketpair(AF_UNIX, SOCK_SEQPACKET, 0)`：

```
system_server (WMS)                        App 进程
────────────────                          ──────────
InputChannel[0] (server)                  InputChannel[1] (client)
    │                                         │
    │  registerInputChannel()                 │  new WindowInputEventReceiver()
    ▼                                         ▼
InputDispatcher                           Looper (epoll 监听 client fd)
    │                                         │
    │  sendMessage() ─── socketpair ──▶      │  receiveMessage()
    │  (MotionEvent/KeyEvent)                 │  → InputEventReceiver.onInputEvent()
    ▼                                         ▼
服务端写入事件                              客户端读取事件 → View 树分发
```

### 6.2 InputDispatcher 注册

> 源码：`frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp (简化)
status_t InputDispatcher::registerInputChannel(
        const std::shared_ptr<InputChannel>& inputChannel) {
    { // acquire lock
        std::scoped_lock _l(mLock);

        sp<IBinder> token = inputChannel->getConnectionToken();

        // 创建 Connection 对象
        std::unique_ptr<Connection> connection =
                std::make_unique<Connection>(inputChannel, /* monitor */ false, mIdGenerator);

        // 注册到 InputDispatcher 的连接映射表
        mConnectionsByToken.emplace(token, std::move(connection));
    } // release lock

    // 将 server 端 fd 加入 InputDispatcher 的 Looper
    // 用于接收 App 发回的事件完成通知（finished signal）
    mLooper->addFd(inputChannel->getFd(), 0, ALOOPER_EVENT_INPUT,
                   handleReceiveCallback, this);

    return OK;
}
```

**稳定性架构师视角**：InputChannel 注册到 InputDispatcher 后，该窗口才具备接收输入事件的能力。如果注册失败（fd 资源耗尽、Binder 通信异常），窗口将永远无法收到触摸或按键事件。

### 6.3 焦点初始化 — updateFocusedWindowLocked()

在 `addWindow()` 的 Step 8 中，如果新添加的窗口可以接收按键输入（`win.canReceiveKeys()` 返回 true），WMS 会尝试更新焦点窗口。

> 源码：`frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java (简化)
boolean updateFocusedWindowLocked(int mode, boolean updateInputWindows) {
    Trace.traceBegin(TRACE_TAG_WINDOW_MANAGER, "wmUpdateFocus");

    boolean changed = false;
    for (int i = mRoot.getChildCount() - 1; i >= 0; i--) {
        final DisplayContent dc = mRoot.getChildAt(i);
        changed |= dc.updateFocusedWindowLocked(mode, updateInputWindows);
    }

    Trace.traceEnd(TRACE_TAG_WINDOW_MANAGER);
    return changed;
}
```

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java (简化)
boolean updateFocusedWindowLocked(int mode, boolean updateInputWindows) {
    // 在整个窗口层级树中找到最顶部的可聚焦窗口
    WindowState newFocus = findFocusedWindowIfNeeded(mode);

    if (mCurrentFocus == newFocus) {
        return false; // 焦点未变化
    }

    WindowState oldFocus = mCurrentFocus;
    mCurrentFocus = newFocus;

    // 通知 InputDispatcher 焦点变化
    if (updateInputWindows) {
        mInputMonitor.setInputFocusLw(newFocus, false /* updateInputWindows */);
    }

    // 通知焦点变化的回调
    // 这会触发 App 的 onWindowFocusChanged()
    if (oldFocus != null) {
        oldFocus.reportFocusChangedSerialized(false /* focused */);
    }
    if (newFocus != null) {
        newFocus.reportFocusChangedSerialized(true /* focused */);
    }

    return true;
}
```

### 6.4 InputDispatcher.setFocusedWindow()

> 源码：`frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`

当 WMS 确定了新的焦点窗口后，通过 `InputManagerService` → `InputDispatcher.setFocusedWindow()` 通知 Native 层：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp (简化)
void InputDispatcher::setFocusedWindow(const FocusRequest& request) {
    { // acquire lock
        std::scoped_lock _l(mLock);

        const int32_t displayId = request.displayId;
        const sp<IBinder>& token = request.token;

        // 查找 Connection
        auto it = mConnectionsByToken.find(token);
        if (it == mConnectionsByToken.end()) {
            // 窗口尚未注册 InputChannel → 延迟设置焦点
            ALOGW("setFocusedWindow: window not found, token=%p", token.get());
            mPendingFocusRequests[displayId] = request;
            return;
        }

        // 更新焦点窗口
        mFocusedWindowTokenByDisplay[displayId] = token;

        // 如果有待分发的 key 事件，现在可以分发了
        // 这也是为什么"焦点窗口未就绪"会导致 Input ANR 的原因
    } // release lock

    // 唤醒 InputDispatcher 线程处理待分发事件
    mLooper->wake();
}
```

**稳定性架构师视角**：`setFocusedWindow()` 中如果 token 对应的 Connection 尚未注册（即 `openInputChannel` 还没完成），焦点请求会被放入 `mPendingFocusRequests`。此时如果有按键事件到达 InputDispatcher，找不到焦点窗口，就会触发 ANR 超时（默认 5000ms）。

```
时序竞态导致焦点丢失 ANR 的典型场景：

T1: WMS.addWindow() → updateFocusedWindowLocked() → setFocusedWindow(tokenA)
T2: InputDispatcher 收到 KeyEvent → 查找焦点窗口 → tokenA 尚未在 mConnectionsByToken
T3: ANR 倒计时开始（5000ms）
T4: openInputChannel() → registerInputChannel(tokenA) → 焦点就绪
    （如果 T4 - T2 > 5000ms → ANR）
```

---

## 7. Window 移除流程

### 7.1 移除的两种路径

Window 的移除有两种触发方式：

| 路径 | 触发场景 | 调用链 |
| :--- | :--- | :--- |
| App 主动移除 | `WindowManager.removeView()` | `ViewRootImpl.die()` → `doDie()` → `dispatchDetachedFromWindow()` → `Session.remove()` → `WMS.removeWindow()` |
| WMS 强制移除 | Activity 销毁、Display 移除 | `WindowState.removeImmediately()` → 清理资源 |

### 7.2 App 端移除流程

> 源码：`frameworks/base/core/java/android/view/ViewRootImpl.java`

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java (简化)
void doDie() {
    // 检查线程
    checkThread();

    synchronized (this) {
        if (mRemoved) {
            return;
        }
        mRemoved = true;

        if (mAdded) {
            // ★ 核心清理逻辑
            dispatchDetachedFromWindow();
        }
        mAdded = false;
    }

    // 从 WindowManagerGlobal 的列表中移除
    WindowManagerGlobal.getInstance().doRemoveView(this);
}

void dispatchDetachedFromWindow() {
    // 1. 通知 View 树 detach
    mView.dispatchDetachedFromWindow();

    // 2. 释放 InputChannel 和 InputEventReceiver
    if (mInputEventReceiver != null) {
        mInputEventReceiver.dispose();
        mInputEventReceiver = null;
    }

    // 3. 通过 Binder 通知 WMS 移除窗口
    try {
        mWindowSession.remove(mWindow);
    } catch (RemoteException e) {
    }

    // 4. 释放 Surface
    if (mInputChannel != null) {
        mInputChannel.dispose();
        mInputChannel = null;
    }
}
```

### 7.3 WMS 端移除流程

> 源码：`frameworks/base/services/core/java/com/android/server/wm/WindowState.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java (简化)
void removeImmediately() {
    if (mRemoved) {
        return;
    }
    mRemoved = true;

    // 1. 从 mWindowMap 中移除
    mWmService.mWindowMap.remove(mClient.asBinder());

    // 2. 释放 InputChannel
    disposeInputChannel();

    // 3. 释放 Surface
    mWinAnimator.destroySurfaceLocked();

    // 4. 从 WindowToken 的子节点中移除
    // （自动触发 WindowContainer 层级结构更新）
    final WindowToken token = mToken;
    removeFromParent();

    // 5. 如果 Token 下没有 Window 了，移除 Token
    if (token.isEmpty() && !token.mPersistOnEmpty) {
        token.removeImmediately();
    }

    // 6. 更新焦点
    mWmService.updateFocusedWindowLocked(
            UPDATE_FOCUS_NORMAL, true /* updateInputWindows */);
}
```

```java
// 释放 InputChannel
void disposeInputChannel() {
    if (mInputChannel != null) {
        // 从 InputDispatcher 注销
        mWmService.mInputManager.unregisterInputChannel(mInputChannel);
        mInputChannel.dispose();
        mInputChannel = null;
        mInputChannelToken = null;
    }
}
```

### 7.4 Window 未正确移除的后果

| 泄漏资源 | 表现 | 检测方法 |
| :--- | :--- | :--- |
| WindowState 泄漏 | `mWindowMap` 持续增长 | `dumpsys window windows \| wc -l` |
| Surface 泄漏 | GPU 内存持续上升 | `dumpsys SurfaceFlinger --latency` |
| InputChannel 泄漏 | fd 数量持续增长 | `ls /proc/<pid>/fd \| wc -l` |
| ViewRootImpl 泄漏 | Java 堆内存上升 | LeakCanary / MAT 分析 |
| WindowToken 泄漏 | WMS 层级树节点增多 | `dumpsys window tokens` |

---

## 8. 稳定性风险总结

### 8.1 Window 创建阶段风险地图

| 风险类型 | 异常/日志 | 触发条件 | 排查入口 | 影响等级 |
| :--- | :--- | :--- | :--- | :--- |
| BadTokenException | `token is not valid` | Activity 已销毁 + Dialog.show() | `adb logcat -s WindowManager` | App Crash |
| BadTokenException | `token is not for an application` | Application Context + Dialog | 检查 Context 类型 | App Crash |
| WindowLeaked | `Activity has leaked window` | Activity.onDestroy() 前未 dismiss Dialog | LeakCanary | 内存泄漏 |
| CalledFromWrongThreadException | `Only the original thread` | 非 UI 线程操作 View | Thread.currentThread() | App Crash |
| Permission Denied | `ADD_PERMISSION_DENIED` | 缺少 SYSTEM_ALERT_WINDOW | `AndroidManifest.xml` | App Crash |
| OutOfResourcesException | `Exception locking surface` | GPU 内存/fd 耗尽 | `dumpsys meminfo` | 黑屏 |
| Input ANR | `no focused window` | InputChannel 注册延迟 | `dumpsys input` | ANR |
| Surface 创建失败 | `createLayer failed` | Layer 数量超限 | `dumpsys SurfaceFlinger` | 黑屏 |
| fd 泄漏 | `Too many open files` | InputChannel/Surface 未正确释放 | `/proc/<pid>/fd` | 系统不稳定 |

### 8.2 Window 移除阶段风险地图

| 风险类型 | 异常/日志 | 触发条件 | 排查入口 | 影响等级 |
| :--- | :--- | :--- | :--- | :--- |
| 焦点丢失 | `no focused window ANR` | 移除焦点窗口后新焦点未及时设置 | `dumpsys window` | ANR |
| Surface 泄漏 | GPU 内存持续增长 | `destroySurfaceLocked()` 未执行 | `dumpsys SurfaceFlinger` | OOM |
| WindowState 泄漏 | mWindowMap 增长 | `removeImmediately()` 未执行 | `dumpsys window windows` | 系统变慢 |
| Binder 死亡通知延迟 | App 进程 Crash 后窗口残留 | Binder death recipient 延迟 | `dumpsys window` | 残留窗口 |

---

## 9. 实战案例

### Case 1：BadTokenException — Activity 生命周期竞态导致 Dialog Crash

**（典型模式）**

**问题现象**

线上监控显示某页面的 `BadTokenException` 崩溃率约 0.3%。崩溃堆栈如下：

```
android.view.WindowManager$BadTokenException:
  Unable to add window -- token android.os.BinderProxy@a8b3c2d is not valid;
  is your activity running?
    at android.view.ViewRootImpl.setView(ViewRootImpl.java:1098)
    at android.view.WindowManagerGlobal.addView(WindowManagerGlobal.java:409)
    at android.view.WindowManagerImpl.addView(WindowManagerImpl.java:109)
    at android.app.Dialog.show(Dialog.java:340)
    at com.example.app.PaymentActivity.showResultDialog(PaymentActivity.java:245)
    at com.example.app.PaymentActivity$PaymentCallback.onSuccess(PaymentActivity.java:180)
```

**分析思路**

1. 从堆栈可见 `showResultDialog()` 是在 `PaymentCallback.onSuccess()` 中调用的 —— 异步回调
2. `BadTokenException` 说明 `ActivityRecord` 的 Token 已从 WMS 中移除
3. 典型场景：用户在支付等待过程中按了返回键，Activity 进入 `onDestroy()`。支付 SDK 回调时 Activity 已销毁

**时序重构**：

```
T1: 用户点击支付 → 发起网络请求 → 等待支付结果
T2: 用户按返回键 → Activity.onPause() → onStop() → onDestroy()
T3: WMS 移除 ActivityRecord Token（Activity 的窗口已不存在）
T4: 支付 SDK 回调 onSuccess() → showResultDialog() → Dialog.show()
T5: addView() → setView() → addToDisplayAsUser() → WMS.addWindow()
T6: WMS: token 不存在 → 返回 ADD_BAD_APP_TOKEN
T7: ViewRootImpl: throw BadTokenException → App Crash
```

**根因**

异步回调（支付 SDK）没有检查 Activity 的生命周期状态，在 Activity 已销毁后仍然调用 `Dialog.show()`。

**修复方案**

```java
// 修复前
public void onSuccess(PaymentResult result) {
    showResultDialog(result);  // 不安全：Activity 可能已销毁
}

// 修复后
public void onSuccess(PaymentResult result) {
    if (isFinishing() || isDestroyed()) {
        Log.w(TAG, "Activity already destroyed, skip showing dialog");
        return;
    }
    showResultDialog(result);
}
```

更彻底的防护：在 `Dialog.show()` 的封装方法中统一检查：

```java
public static void safeShowDialog(Activity activity, Dialog dialog) {
    if (activity == null || activity.isFinishing() || activity.isDestroyed()) {
        return;
    }
    if (dialog == null || dialog.isShowing()) {
        return;
    }
    try {
        dialog.show();
    } catch (WindowManager.BadTokenException e) {
        Log.e(TAG, "BadTokenException caught", e);
    }
}
```

---

### Case 2：WindowLeaked 导致 Activity 内存泄漏

**（典型模式）**

**问题现象**

LeakCanary 报告 `PaymentActivity` 泄漏。GC Root 路径：

```
┌─ GC Root: Thread (main)
│   ├─ Looper.mQueue
│   │   ├─ MessageQueue.mMessages
│   │   │   ├─ Message.callback (ViewRootImpl$TraversalRunnable)
│   │   │   │   ├─ ViewRootImpl.this
│   │   │   │   │   ├─ ViewRootImpl.mView → DecorView
│   │   │   │   │   │   └─ DecorView.mContext → PaymentActivity (LEAKED)
│   │   │   │   │   │       ├─ PaymentActivity.mPaymentViewModel
│   │   │   │   │   │       ├─ PaymentActivity.mOrderList (size=1200)
│   │   │   │   │   │       └─ ... (total retained: 8.5MB)
```

同时 Logcat 中有警告：

```
E/WindowManager: android.view.WindowLeaked: Activity com.example.app.PaymentActivity
  has leaked window DecorView@a8b3c2d[PaymentActivity] that was originally added here
    at android.view.ViewRootImpl.<init>(ViewRootImpl.java:755)
    at android.view.WindowManagerGlobal.addView(WindowManagerGlobal.java:393)
    at android.view.WindowManagerImpl.addView(WindowManagerImpl.java:109)
    at android.app.Dialog.show(Dialog.java:340)
    at com.example.app.PaymentActivity.showLoadingDialog(PaymentActivity.java:120)
```

**分析思路**

1. LeakCanary 显示 GC Root 是 `ViewRootImpl.mView`（DecorView），指向 `PaymentActivity`
2. `WindowLeaked` 日志指明泄漏窗口是 Dialog 的 DecorView
3. GC Root 路径中 `ViewRootImpl$TraversalRunnable` 在 `MessageQueue` 中 —— ViewRootImpl 未被释放

**根因**

`PaymentActivity` 在 `onCreate()` 中 `showLoadingDialog()` 添加了一个 Loading Dialog。Activity 在 `onDestroy()` 时没有调用 `dialog.dismiss()`。这导致：

1. Dialog 的 `ViewRootImpl` 仍然持有 `DecorView` 的引用
2. `DecorView` 持有 Activity Context（即 `PaymentActivity`）的引用
3. `ViewRootImpl` 中的 `TraversalRunnable` 被 post 到 `MessageQueue` 中，阻止了 GC 回收

**泄漏链路**：

```
MessageQueue → TraversalRunnable → ViewRootImpl → DecorView (Dialog's)
    → Dialog.mContext → PaymentActivity → 8.5MB retained heap
```

**修复方案**

```java
// PaymentActivity.java

private Dialog mLoadingDialog;

@Override
protected void onDestroy() {
    super.onDestroy();
    // ★ 确保在 Activity 销毁时 dismiss Dialog
    if (mLoadingDialog != null && mLoadingDialog.isShowing()) {
        mLoadingDialog.dismiss();
    }
    mLoadingDialog = null;
}
```

更规范的做法——使用 Lifecycle 观察者自动管理 Dialog 生命周期：

```java
public class LifecycleAwareDialog extends Dialog implements LifecycleObserver {

    public LifecycleAwareDialog(@NonNull Activity activity) {
        super(activity);
        if (activity instanceof LifecycleOwner) {
            ((LifecycleOwner) activity).getLifecycle().addObserver(this);
        }
    }

    @OnLifecycleEvent(Lifecycle.Event.ON_DESTROY)
    void onActivityDestroyed() {
        if (isShowing()) {
            dismiss();
        }
    }
}
```

---

## 总结

Window 的创建与添加是 Android 窗口管理系统的核心入口流程。对于稳定性架构师，以下是必须掌握的关键要点：

1. **两阶段创建**：Window 的创建分为 `addWindow()`（注册元数据 + InputChannel）和 `relayoutWindow()`（创建 Surface）两个阶段。理解这两步分离的设计是排查窗口显示异常的基础。

2. **Token 是窗口的身份凭证**：`BadTokenException` 占 Window 相关 Crash 的绝对多数。核心防护策略是：在任何异步回调中操作 UI 前，必须检查 Activity 生命周期（`isFinishing()` / `isDestroyed()`）。

3. **InputChannel 是窗口接收输入的命脉**：`openInputChannel()` 创建的 socketpair 连接了 InputDispatcher 和 App。InputChannel 注册延迟或失败会导致"无焦点窗口 ANR"。

4. **焦点更新是 addWindow 的副作用**：新窗口添加后，`updateFocusedWindowLocked()` 可能改变系统焦点。焦点切换的时序与 InputChannel 注册的时序竞态是 Input ANR 的常见根因。

5. **Window 移除必须彻底**：未正确移除的 Window 会导致 Surface 泄漏（GPU 内存）、InputChannel 泄漏（fd）、ViewRootImpl 泄漏（Java 堆内存）。在 Dialog、PopupWindow、Toast 等场景中，务必在 Activity `onDestroy()` 前完成清理。

**排查路径速查**：

```
Window 创建异常排查路径：
  BadTokenException → 检查 Activity 生命周期 → 检查 Token 类型匹配
      → dumpsys window tokens → 确认 Token 在 WMS 中的状态
  
  窗口不显示 → dumpsys window windows → 确认 WindowState 存在
      → dumpsys SurfaceFlinger → 确认 Surface/Layer 存在
      → 确认 relayoutWindow 是否成功
  
  窗口无法接收输入 → dumpsys input → 确认 InputChannel 注册
      → 确认 Focused Window → 确认 InputDispatcher 连接状态
  
  内存泄漏 → LeakCanary / MAT → 追踪 ViewRootImpl → DecorView → Activity 引用链
      → 检查 Dialog/PopupWindow 的 dismiss 调用
```

---

## 附录：核心源码路径索引

| 文件名 | 完整路径 | 说明 |
| :--- | :--- | :--- |
| `WindowManagerImpl.java` | `frameworks/base/core/java/android/view/WindowManagerImpl.java` | App 端 WindowManager 实现 |
| `WindowManagerGlobal.java` | `frameworks/base/core/java/android/view/WindowManagerGlobal.java` | 进程级 Window 管理单例 |
| `ViewRootImpl.java` | `frameworks/base/core/java/android/view/ViewRootImpl.java` | View 树与 WMS 的桥梁 |
| `WindowManagerService.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | WMS 核心服务，`addWindow()` / `relayoutWindow()` 所在 |
| `WindowState.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | 单个窗口的完整状态，`openInputChannel()` 所在 |
| `WindowToken.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowToken.java` | 窗口身份凭证 |
| `DisplayContent.java` | `frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java` | 单个 Display 的窗口管理，`updateFocusedWindowLocked()` 所在 |
| `WindowStateAnimator.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java` | `createSurfaceLocked()` 所在 |
| `Session.java` | `frameworks/base/services/core/java/com/android/server/wm/Session.java` | App 与 WMS 的 Binder 会话 |
| `SurfaceControl.java` | `frameworks/base/core/java/android/view/SurfaceControl.java` | Surface 控制句柄 |
| `InputChannel.java` | `frameworks/base/core/java/android/view/InputChannel.java` | 输入事件传输通道 |
| `InputDispatcher.cpp` | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` | 输入事件分发引擎，`registerInputChannel()` / `setFocusedWindow()` 所在 |
| `InputMonitor.java` | `frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java` | WMS 与 InputDispatcher 的桥接层 |
| `DisplayPolicy.java` | `frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java` | 窗口策略（导航栏/状态栏行为、窗口准入） |

---

下一篇 [03-WindowContainer 层级体系与窗口组织](03-WindowContainer层级体系与窗口组织.md) 将深入 WMS 内部的 WindowContainer 层级树结构，分析 DisplayContent → TaskDisplayArea → Task → ActivityRecord → WindowState 的完整层级关系，以及窗口 Z-Order 的计算机制和层级变更对稳定性的影响。
