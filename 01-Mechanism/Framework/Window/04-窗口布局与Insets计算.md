# 04-窗口布局与 Insets 计算

## 1. 布局在 Window 架构中的位置

### 1.1 布局阶段在 Window 生命周期中的定位

窗口布局（Layout）是 Window 管理系统中承上启下的关键环节。上游是窗口的创建与添加（`addWindow`），下游是 Surface 的合成与显示。布局阶段的核心任务是：**确定每个窗口在屏幕上的精确位置和尺寸**。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Window 生命周期全景                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐   ┌───────────────┐   ┌──────────────────────────┐   │
│  │  01-创建阶段  │   │  02-添加阶段   │   │  03-层级组织阶段          │   │
│  │  addView()   │──▶│  addWindow()  │──▶│  WindowContainer 树       │   │
│  │  Token 验证   │   │  InputChannel │   │  Z-order / DisplayArea   │   │
│  └──────────────┘   └───────────────┘   └────────────┬─────────────┘   │
│                                                       │                 │
│                                                       ▼                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ★ 04-布局与 Insets 计算 ← 本篇                                  │   │
│  │                                                                   │   │
│  │  performSurfacePlacement()                                        │   │
│  │    ├── DisplayContent.performLayout()                             │   │
│  │    │     ├── DisplayPolicy: 计算系统装饰区域 (StatusBar, NavBar)  │   │
│  │    │     ├── layoutWindowLw(): 计算每个窗口的 Frame               │   │
│  │    │     └── InsetsStateController: 构建 Insets 信息              │   │
│  │    ├── relayoutWindow(): 同步 Surface 尺寸和位置                  │   │
│  │    └── 配置变更: 屏幕旋转 / 折叠屏展开 → 窗口重建               │   │
│  │                                                                   │   │
│  │  输出: mFrame, InsetsState, Surface bounds                       │   │
│  └──────────────────────────────────────┬────────────────────────────┘   │
│                                          │                               │
│                                          ▼                               │
│  ┌──────────────┐   ┌───────────────┐   ┌──────────────────────────┐   │
│  │  05-动画阶段  │   │  06-渲染阶段   │   │  07-销毁阶段              │   │
│  │  Transition  │◀──│  draw/compose │◀──│  removeWindow()          │   │
│  │  Animation   │   │  SurfaceFlinger│   │  Surface 释放            │   │
│  └──────────────┘   └───────────────┘   └──────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 布局的本质

布局（Layout）回答了一个看似简单的问题：**每个窗口应该出现在屏幕的哪个位置、占多大面积？**

但实际计算远比想象复杂。一块 1080×2400 的屏幕上可能同时存在：

- StatusBar 占据顶部 100px
- NavigationBar 占据底部 132px
- DisplayCutout（刘海/挖孔）侵占额外的安全区域
- IME 软键盘弹出后压缩应用可见区域
- 分屏模式下两个 App 各占一半
- 悬浮窗覆盖在应用之上

布局阶段必须协调所有这些窗口的位置和尺寸关系，计算出每个窗口的最终 Frame（矩形区域），并将 Insets（内边距/安全区域偏移量）传递给应用，让应用知道"哪些区域被系统 UI 占据了"。

### 1.3 布局输出的数据结构

| 输出 | 含义 | 消费方 |
|:---|:---|:---|
| `WindowState.mFrame` | 窗口在屏幕上的最终矩形位置 | SurfaceFlinger（确定 Surface 合成位置） |
| `WindowState.mInsetsState` | 窗口面临的各类 Insets 信息 | ViewRootImpl → View 树（调整内容布局） |
| `SurfaceControl` 的 position/size | Surface 图层的物理尺寸和位置 | SurfaceFlinger（Buffer 分配和合成） |
| `ClientWindowFrames` | 回传给 App 端的窗口 Frame 信息 | ViewRootImpl（驱动 View 的 measure/layout） |

---

## 2. 布局总流程 — performSurfacePlacement

### 2.1 布局的触发入口

WMS 的布局并非实时计算的——它是按需触发、批量执行的。当窗口状态发生变化（添加、移除、大小改变、可见性改变等），WMS 不会立即布局，而是标记 `mLayoutNeeded = true`，等待统一的布局调度。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/WindowSurfacePlacer.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowSurfacePlacer.java（简化）
class WindowSurfacePlacer {

    private boolean mTraversalScheduled;
    private final Runnable mPerformSurfacePlacement = () -> {
        performSurfacePlacement();
    };

    void requestTraversal() {
        if (!mTraversalScheduled) {
            mTraversalScheduled = true;
            // 通过 Handler 延迟到当前消息处理完毕后执行
            mService.mAnimationHandler.post(mPerformSurfacePlacement);
        }
    }

    void performSurfacePlacement() {
        mTraversalScheduled = false;
        performSurfacePlacementLoop();
    }
}
```

### 2.2 布局主循环 — performSurfacePlacementLoop

`performSurfacePlacementLoop()` 是布局的主循环。它最多执行 6 轮迭代——因为每次布局可能导致新的布局请求（比如窗口的大小变化触发了新的 Insets 变化），需要再次布局直到稳定。

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowSurfacePlacer.java（简化）
private void performSurfacePlacementLoop() {
    int loopCount = 6;
    do {
        mTraversalScheduled = false;
        performSurfacePlacementNoTrace();
        loopCount--;
    } while (mTraversalScheduled && loopCount > 0);

    if (mTraversalScheduled) {
        // ★ 稳定性风险：6 轮后仍未收敛 → 布局无限循环
        Slog.e(TAG, "performSurfacePlacementLoop looped too many times");
    }
}
```

> **稳定性架构师视角**：布局循环不收敛是严重的系统级稳定性问题。每轮循环都持有 `mGlobalLock`，如果 6 轮后仍有 `mTraversalScheduled = true`，意味着某个窗口的布局结果不断触发新的布局请求。典型场景：窗口 A 的大小取决于窗口 B 的 Insets，而窗口 B 的 Insets 取决于窗口 A 的大小——形成循环依赖。此时 system_server 的主线程被布局循环占满，导致 Watchdog 超时重启。

### 2.3 performSurfacePlacementNoTrace 的核心步骤

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java（简化）
void performSurfacePlacementNoTrace() {
    // Step 1: 遍历所有 Display，执行布局
    for (int displayNdx = mChildren.size() - 1; displayNdx >= 0; --displayNdx) {
        final DisplayContent dc = mChildren.get(displayNdx);
        if (dc.mLayoutNeeded) {
            dc.performLayout(true /* initial */, false /* updateInputWindows */);
        }
    }

    // Step 2: 遍历所有窗口，处理 Surface 状态
    //         包括创建/销毁 Surface、更新可见性
    mWmService.openSurfaceTransaction();
    try {
        applySurfaceChangesTransaction();
    } finally {
        mWmService.closeSurfaceTransaction("
                performLayoutAndPlaceSurfaces");
    }

    // Step 3: 更新 InputDispatcher 的窗口信息
    for (int displayNdx = mChildren.size() - 1; displayNdx >= 0; --displayNdx) {
        final DisplayContent dc = mChildren.get(displayNdx);
        dc.getInputMonitor().updateInputWindowsLw(false /* force */);
    }

    // Step 4: 检查是否有窗口需要再次布局
    //         如果有，标记 mTraversalScheduled = true
    checkForNewLayoutNeeded();
}
```

**布局触发条件汇总：**

| 触发源 | 说明 | 标记方式 |
|:---|:---|:---|
| `addWindow()` | 新窗口添加 | `mLayoutNeeded = true` |
| `removeWindow()` | 窗口移除 | `mLayoutNeeded = true` |
| `relayoutWindow()` | App 请求重新布局 | `mLayoutNeeded = true` |
| 屏幕旋转 | Display 属性变化 | `mLayoutNeeded = true` |
| IME 显示/隐藏 | 软键盘状态变化 | Insets 变化 → `mLayoutNeeded = true` |
| StatusBar/NavBar 显示/隐藏 | 系统 UI 可见性变化 | Insets 变化 → `mLayoutNeeded = true` |
| 分屏/画中画模式变化 | Task bounds 变化 | `mLayoutNeeded = true` |

### 2.4 布局流程全景图

```
WindowSurfacePlacer.requestTraversal()
    │
    ▼
performSurfacePlacementLoop()  ← 最多 6 轮
    │
    ▼
performSurfacePlacementNoTrace()
    │
    ├── [Step 1] DisplayContent.performLayout()
    │       │
    │       ├── DisplayPolicy.beginLayoutLw()
    │       │     └── 确定 StatusBar / NavBar 的位置
    │       │         → 计算出 systemDecorRect (系统装饰区域)
    │       │
    │       ├── forAllWindows(w -> layoutWindowLw(w))
    │       │     └── 对每个窗口计算 mFrame / mDisplayFrame
    │       │
    │       └── DisplayPolicy.finishLayoutLw()
    │             └── 最终调整与校验
    │
    ├── [Step 2] applySurfaceChangesTransaction()
    │       │
    │       ├── WindowStateAnimator.commitFinishDrawingLocked()
    │       ├── WindowState.prepareSurfaces()
    │       │     └── 更新 SurfaceControl 的 position / size / crop
    │       └── assignChildLayers()
    │             └── 更新 Z-order
    │
    ├── [Step 3] InputMonitor.updateInputWindowsLw()
    │       └── 将最新窗口信息同步给 InputDispatcher
    │
    └── [Step 4] checkForNewLayoutNeeded()
            └── 如有新的布局需求 → mTraversalScheduled = true → 再循环
```

---

## 3. DisplayPolicy 与窗口 Frame 计算

### 3.1 DisplayPolicy 的角色

`DisplayPolicy` 是每个 `DisplayContent` 的策略引擎，负责管理系统装饰窗口（StatusBar、NavigationBar）的行为，以及确定应用窗口的可用区域。它是布局计算的核心参与者。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java（简化）
class DisplayPolicy {

    // 系统装饰窗口引用
    WindowState mStatusBar;
    WindowState mNavigationBar;

    // 各种区域的矩形定义
    private final Rect mUnrestrictedScreenRect = new Rect();   // 整个屏幕（含刘海）
    private final Rect mRestrictedScreenRect = new Rect();     // 排除系统装饰后的可用区域
    private final Rect mSystemRect = new Rect();               // 系统装饰占据的区域
    private final Rect mStableRect = new Rect();               // 稳定区域（不受 IME 影响）
    private final Rect mContentRect = new Rect();              // 内容区域（受 IME 影响）

    // 关联的 DisplayContent
    private final DisplayContent mDisplayContent;

    // 关联的 InsetsStateController
    // 管理该 Display 上所有 Insets 源
    InsetsStateController getInsetsStateController() {
        return mDisplayContent.getInsetsStateController();
    }
}
```

### 3.2 系统装饰区域的确定

布局的第一步是确定系统装饰窗口占据了屏幕的哪些区域。这些区域直接影响应用窗口的可用空间。

```
┌────────────────────────────────────────────┐
│  StatusBar (TYPE_STATUS_BAR)               │ ← 高度 ~100px
│  ┌───────┐                                 │    系统装饰区域
│  │cutout │                                 │    (DisplayCutout 可能额外侵占)
├──┴───────┴─────────────────────────────────┤
│                                            │
│                                            │
│     App 可用区域                            │ ← mRestrictedScreenRect
│     (mContentRect / mStableRect)           │
│                                            │
│                                            │
│                                            │
├────────────────────────────────────────────┤
│  NavigationBar (TYPE_NAVIGATION_BAR)       │ ← 高度 ~132px
│  (手势导航时为 ~66px)                       │    系统装饰区域
└────────────────────────────────────────────┘

全屏: 1080 × 2400
StatusBar: [0, 0, 1080, 100]
NavBar:    [0, 2268, 1080, 2400]
可用区域:  [0, 100, 1080, 2268]
```

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java（简化）
void beginLayoutLw(DisplayFrames displayFrames, int uiMode) {
    // 获取整个屏幕尺寸（含 cutout）
    final Rect unrestricted = displayFrames.mUnrestricted;

    // 1. 计算 StatusBar 区域
    if (mStatusBar != null && mStatusBar.isVisibleLw()) {
        final Rect statusBarFrame = mStatusBar.getFrame();
        // StatusBar 固定在屏幕顶部
        displayFrames.mStable.top = Math.max(
                displayFrames.mStable.top, statusBarFrame.bottom);
        displayFrames.mContent.top = displayFrames.mStable.top;
    }

    // 2. 计算 NavigationBar 区域
    if (mNavigationBar != null && mNavigationBar.isVisibleLw()) {
        final Rect navBarFrame = mNavigationBar.getFrame();
        // NavigationBar 位置取决于屏幕方向
        switch (mNavigationBarPosition) {
            case NAV_BAR_BOTTOM:
                displayFrames.mStable.bottom = Math.min(
                        displayFrames.mStable.bottom, navBarFrame.top);
                break;
            case NAV_BAR_RIGHT:
                displayFrames.mStable.right = Math.min(
                        displayFrames.mStable.right, navBarFrame.left);
                break;
            case NAV_BAR_LEFT:
                displayFrames.mStable.left = Math.max(
                        displayFrames.mStable.left, navBarFrame.right);
                break;
        }
    }

    // 3. 处理 DisplayCutout（刘海/挖孔/水滴屏）
    final DisplayCutout cutout = displayFrames.mDisplayCutout;
    if (!cutout.isEmpty()) {
        displayFrames.mStable.top = Math.max(
                displayFrames.mStable.top,
                cutout.getSafeInsetTop());
    }
}
```

### 3.3 layoutWindowLw() — 单个窗口的 Frame 计算

`DisplayPolicy.layoutWindowLw()` 负责计算每个窗口的最终 Frame。不同类型的窗口有不同的计算逻辑。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java（简化）
void layoutWindowLw(WindowState win, WindowState attached,
        DisplayFrames displayFrames) {
    final WindowManager.LayoutParams attrs = win.mAttrs;
    final int type = attrs.type;
    final int fl = attrs.flags;

    // 根据窗口类型和 flags 确定参考 Frame
    final Rect parentFrame;   // 父窗口/可用区域
    final Rect displayFrame;  // 显示区域
    final Rect contentFrame;  // 内容区域（排除 SystemBar）
    final Rect visibleFrame;  // 可见区域（排除 SystemBar + IME）

    if (type == TYPE_STATUS_BAR) {
        // StatusBar 使用整个屏幕宽度，高度由自身决定
        parentFrame = displayFrames.mUnrestricted;
        displayFrame = displayFrames.mUnrestricted;
        contentFrame = displayFrames.mUnrestricted;
        visibleFrame = displayFrames.mUnrestricted;

    } else if (type == TYPE_NAVIGATION_BAR) {
        // NavigationBar 位置由 mNavigationBarPosition 决定
        parentFrame = displayFrames.mUnrestricted;
        displayFrame = displayFrames.mUnrestricted;
        contentFrame = displayFrames.mUnrestricted;
        visibleFrame = displayFrames.mUnrestricted;

    } else if (type == TYPE_INPUT_METHOD) {
        // IME 窗口在 stable 区域内，但不受自身 Insets 影响
        parentFrame = displayFrames.mStable;
        displayFrame = displayFrames.mStable;
        contentFrame = displayFrames.mStable;
        visibleFrame = displayFrames.mStable;

    } else if (attached != null) {
        // 子窗口：跟随父窗口的 Frame
        parentFrame = attached.getFrame();
        displayFrame = attached.getDisplayFrame();
        contentFrame = attached.getContentFrame();
        visibleFrame = attached.getVisibleFrame();

    } else {
        // 普通应用窗口
        if ((fl & FLAG_LAYOUT_IN_SCREEN) != 0) {
            if ((fl & FLAG_LAYOUT_NO_LIMITS) != 0) {
                // 无限制：使用整个屏幕（甚至可以超出屏幕）
                parentFrame = displayFrames.mUnrestricted;
            } else {
                // 全屏但不超出
                parentFrame = displayFrames.mRestricted;
            }
        } else {
            // 常规应用：使用排除系统装饰后的区域
            parentFrame = displayFrames.mContent;
        }
        displayFrame = displayFrames.mRestricted;
        contentFrame = displayFrames.mContent;
        visibleFrame = displayFrames.mCurrent;
    }

    // 最终计算 mFrame
    win.computeFrame(parentFrame, displayFrame, contentFrame, visibleFrame);
}
```

### 3.4 窗口 Frame 的多种类型

Android 的窗口系统中有多种 Frame 概念，各有不同的用途：

| Frame 类型 | 字段 | 含义 | 计算基准 |
|:---|:---|:---|:---|
| Parent Frame | `mParentFrame` | 窗口可用空间的外边界 | 由窗口类型和 flags 决定 |
| Display Frame | `mDisplayFrame` | 窗口在屏幕上的可显示区域 | 排除被强制遮挡的区域 |
| Content Frame | `mContentFrame` | 窗口中可放置内容的区域 | 排除 StatusBar + NavigationBar |
| Visible Frame | `mVisibleFrame` | 窗口中当前可见的区域 | 排除所有遮挡物（含 IME） |
| Frame | `mFrame` | 窗口的最终位置和大小 | `computeFrame()` 综合计算结果 |
| Requested Frame | `mRequestedWidth/Height` | App 请求的窗口大小 | App 通过 `relayoutWindow()` 请求 |

```
以一个全屏 App 窗口为例（IME 弹出状态）:

                        mDisplayFrame
┌───────────────────────────────────────────┐ top=0
│  StatusBar                                │
├───────────────────────────────────────────┤ top=100
│                                           │
│  mContentFrame                            │ ← 排除 SystemBar
│  ┌───────────────────────────────────┐    │
│  │                                   │    │
│  │  App 内容区域                      │    │
│  │                                   │    │
│  │                                   │    │
│  │  mVisibleFrame                    │    │ ← 排除 SystemBar + IME
│  │  ┌───────────────────────────┐    │    │
│  │  │                           │    │    │
│  │  │  当前可见的内容             │    │    │
│  │  │                           │    │    │
│  │  └───────────────────────────┘    │    │
│  │                                   │    │
│  └───────────────────────────────────┘    │
│                                           │
├───────────────────────────────────────────┤ bottom=IME.top
│  IME (输入法窗口)                          │
├───────────────────────────────────────────┤
│  NavigationBar                            │
└───────────────────────────────────────────┘ bottom=2400

mFrame          = [0, 0, 1080, 2400]    ← 窗口的完整矩形
mContentFrame   = [0, 100, 1080, 2268]  ← 排除 StatusBar + NavBar
mVisibleFrame   = [0, 100, 1080, 1400]  ← 排除 StatusBar + NavBar + IME
```

### 3.5 computeFrame() — Frame 的最终计算

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/WindowState.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java（简化）
void computeFrame(Rect parentFrame, Rect displayFrame,
        Rect contentFrame, Rect visibleFrame) {
    // gravity 处理：根据 LayoutParams.gravity 在 parentFrame 内定位
    Gravity.apply(mAttrs.gravity,
            mRequestedWidth, mRequestedHeight,
            parentFrame,
            mAttrs.x, mAttrs.y,
            mFrame /* 输出 */);

    // 确保不超出 displayFrame
    if (mFrame.left < displayFrame.left) {
        mFrame.left = displayFrame.left;
    }
    if (mFrame.top < displayFrame.top) {
        mFrame.top = displayFrame.top;
    }

    // 计算 contentFrame 和 visibleFrame
    mContentFrame.set(
            Math.max(contentFrame.left, mFrame.left),
            Math.max(contentFrame.top, mFrame.top),
            Math.min(contentFrame.right, mFrame.right),
            Math.min(contentFrame.bottom, mFrame.bottom));

    mVisibleFrame.set(
            Math.max(visibleFrame.left, mFrame.left),
            Math.max(visibleFrame.top, mFrame.top),
            Math.min(visibleFrame.right, mFrame.right),
            Math.min(visibleFrame.bottom, mFrame.bottom));

    // 计算 Insets（Frame 与 ContentFrame 的差值）
    mContentInsets.set(
            mContentFrame.left - mFrame.left,
            mContentFrame.top - mFrame.top,
            mFrame.right - mContentFrame.right,
            mFrame.bottom - mContentFrame.bottom);
}
```

> **稳定性架构师视角**：`computeFrame()` 中的 `Gravity.apply()` 是窗口定位的核心。如果 `mRequestedWidth` 或 `mRequestedHeight` 为 0 或负值（App 端 measure 异常），`Gravity.apply()` 可能计算出零面积的 Frame——窗口存在但不可见。更隐蔽的是，当 `displayFrame` 因为 DisplayCutout 不规则而出现异常矩形时，`mFrame` 可能被裁剪成意想不到的形状，导致部分内容被隐藏在刘海后面。

---

## 4. WindowInsets 体系

### 4.1 Insets 的本质

Insets（内边距）是窗口系统中最容易被误解的概念之一。简单来说，Insets 描述了**屏幕上被系统 UI 占据的区域**，告诉 App："这些地方已经被系统 UI（StatusBar、NavigationBar、IME、DisplayCutout 等）占据了，你的内容需要避开。"

```
没有 Insets 概念时:                      有 Insets 概念时:
┌──────────────────────┐              ┌──────────────────────┐
│StatusBar(遮住了标题)  │              │StatusBar             │
│itle: Hello Wor│      │              ├──────────────────────┤
│Content starts here   │              │  Title: Hello World  │ ← 内容下移
│                      │              │  Content starts here │    避开 Insets
│                      │              │                      │
│                      │              │                      │
│                      │              │                      │
│end of page───────────│              │  end of page         │
│NavigationBar(遮住尾部)│              ├──────────────────────┤
└──────────────────────┘              │NavigationBar         │
  App 内容被遮挡 ✗                     └──────────────────────┘
                                        App 内容完整可见 ✓
```

### 4.2 Android 11+ WindowInsets API 革新

Android 11（API 30）对 WindowInsets API 做了重大重构，引入了类型化 Insets 系统：

```java
// Android 11+ 新 API
public final class WindowInsets {

    // 获取指定类型的 Insets
    public Insets getInsets(@InsetsType int typeMask) { ... }

    // Insets 类型定义
    public static final class Type {
        public static int statusBars()      { return 1 << 0; }  // 状态栏
        public static int navigationBars()  { return 1 << 1; }  // 导航栏
        public static int captionBar()      { return 1 << 2; }  // 标题栏（自由窗口模式）
        public static int ime()             { return 1 << 3; }  // 输入法
        public static int systemGestures()  { return 1 << 4; }  // 手势导航区域
        public static int mandatorySystemGestures() { return 1 << 5; }
        public static int tappableElement() { return 1 << 6; }  // 可点击的系统元素
        public static int displayCutout()   { return 1 << 7; }  // 刘海/挖孔屏

        // 组合类型
        public static int systemBars() {
            return statusBars() | navigationBars() | captionBar();
        }
    }
}
```

**各类 Insets 的物理含义：**

| Insets 类型 | 物理对应 | 典型值（1080×2400 屏幕） | 动态性 |
|:---|:---|:---|:---|
| `statusBars()` | StatusBar 占据的区域 | top=100 | StatusBar 显示/隐藏时变化 |
| `navigationBars()` | NavigationBar 占据的区域 | bottom=132（三键模式）/ bottom=66（手势模式） | 模式切换时变化 |
| `ime()` | 软键盘占据的区域 | bottom=800～1200 | IME 弹出/收起时变化 |
| `displayCutout()` | 刘海/挖孔屏安全区域 | top=100（与 StatusBar 重合时为 0） | 屏幕旋转时变化 |
| `systemGestures()` | 手势导航的边缘区域 | left=44, right=44, bottom=66 | 手势模式切换时变化 |
| `mandatorySystemGestures()` | 必须由系统处理的手势区域 | bottom=66 | 随导航模式变化 |

### 4.3 InsetsState — Insets 信息的容器

`InsetsState` 是 WMS 端用于存储所有 Insets 信息的容器。每个窗口都持有一份 `InsetsState`，描述该窗口面临的所有 Insets 状况。

> 源码路径：`frameworks/base/core/java/android/view/InsetsState.java`

```java
// frameworks/base/core/java/android/view/InsetsState.java（简化）
public class InsetsState implements Parcelable {

    // 所有 Insets 源的数组
    // 索引对应 InsetsSource 的 ID（如 STATUS_BAR = 0, NAV_BAR = 1 ...）
    private final SparseArray<InsetsSource> mSources = new SparseArray<>();

    // DisplayFrame：窗口的显示区域（用于 Insets 计算的参考系）
    private final Rect mDisplayFrame = new Rect();

    // DisplayCutout：刘海/挖孔屏信息
    private DisplayCutout mDisplayCutout = DisplayCutout.NO_CUTOUT;

    // 计算指定类型的 Insets
    public Insets calculateInsets(Rect frame, @InsetsType int typeMask,
            boolean ignoreVisibility) {
        int left = 0, top = 0, right = 0, bottom = 0;
        for (int i = mSources.size() - 1; i >= 0; i--) {
            final InsetsSource source = mSources.valueAt(i);
            if ((toPublicType(source.getType()) & typeMask) == 0) {
                continue;
            }
            if (!ignoreVisibility && !source.isVisible()) {
                continue;
            }
            // 计算该 source 对 frame 的 insets 影响
            Insets insets = source.calculateInsets(frame, ignoreVisibility);
            left = Math.max(left, insets.left);
            top = Math.max(top, insets.top);
            right = Math.max(right, insets.right);
            bottom = Math.max(bottom, insets.bottom);
        }
        return Insets.of(left, top, right, bottom);
    }
}
```

### 4.4 InsetsSource 与 InsetsSourceProvider

每个系统 UI 元素（StatusBar、NavigationBar、IME 等）在 Insets 系统中都被抽象为一个 `InsetsSource`。WMS 端对应的管理者是 `InsetsSourceProvider`。

> 源码路径：`frameworks/base/core/java/android/view/InsetsSource.java`
> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/InsetsSourceProvider.java`

```java
// frameworks/base/core/java/android/view/InsetsSource.java（简化）
public class InsetsSource implements Parcelable {

    private final int mId;           // Source ID
    private final int mType;         // Insets 类型（STATUS_BAR / NAV_BAR / IME ...）
    private final Rect mFrame;       // Source 占据的屏幕区域
    private boolean mVisible;        // Source 当前是否可见

    // 计算该 Source 对目标 Frame 的 Insets 影响
    public Insets calculateInsets(Rect relativeFrame, boolean ignoreVisibility) {
        if (!ignoreVisibility && !mVisible) {
            return Insets.NONE;
        }
        // 计算 mFrame 与 relativeFrame 的交集
        // 交集区域即为 Insets 值
        if (mFrame.isEmpty()) {
            return Insets.NONE;
        }
        // 判断 source 在目标 frame 的哪个方向
        // 例如：StatusBar 在顶部 → top inset
        // NavigationBar 在底部 → bottom inset
        return calculateInsetsForSide(relativeFrame);
    }
}
```

```java
// frameworks/base/services/core/java/com/android/server/wm/InsetsSourceProvider.java（简化）
class InsetsSourceProvider {

    protected final InsetsSource mSource;
    protected WindowState mWindowContainer;  // 提供 Insets 的窗口（如 StatusBar 窗口）

    // 当窗口位置或大小变化时更新 Source
    void updateSourceFrame(Rect newFrame) {
        mSource.setFrame(newFrame);
        // 通知所有消费该 Insets 的窗口更新
        mStateController.notifyInsetsChanged();
    }

    void setWindowContainer(WindowState win) {
        mWindowContainer = win;
        if (win != null) {
            // 窗口可见性决定 Insets 是否生效
            updateVisibility();
        }
    }

    void updateVisibility() {
        boolean visible = mWindowContainer != null
                && mWindowContainer.wouldBeVisibleIfPolicyIgnored()
                && mWindowContainer.isVisibleByPolicy();
        mSource.setVisible(visible);
    }
}
```

### 4.5 InsetsStateController — 每个 Display 的 Insets 中控

`InsetsStateController` 是每个 `DisplayContent` 上的 Insets 管理中枢，它持有该 Display 上所有 `InsetsSourceProvider`，并负责将 `InsetsState` 分发给各窗口。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/InsetsStateController.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/InsetsStateController.java（简化）
class InsetsStateController {

    private final DisplayContent mDisplayContent;

    // 该 Display 上的所有 Insets 源
    private final SparseArray<InsetsSourceProvider> mProviders = new SparseArray<>();

    // 全局 InsetsState（包含所有 Source 的状态）
    private final InsetsState mLastState = new InsetsState();

    // 获取指定窗口的 InsetsState
    InsetsState getInsetsForWindow(WindowState target) {
        InsetsState state = new InsetsState();
        state.set(mLastState);

        // 窗口不应该看到自己提供的 Insets
        // 例如 StatusBar 窗口不应该受自己的 statusBar insets 影响
        for (int i = mProviders.size() - 1; i >= 0; i--) {
            InsetsSourceProvider provider = mProviders.valueAt(i);
            if (provider.getWindowContainer() == target) {
                state.removeSource(provider.getSource().getId());
            }
        }

        return state;
    }

    // 当任何 Insets Source 变化时通知所有窗口
    void notifyInsetsChanged() {
        mDisplayContent.forAllWindows(w -> {
            if (!w.isVisible()) return;
            w.notifyInsetsChanged();
        }, true /* traverseTopToBottom */);
    }

    // 注册 Insets Source Provider
    InsetsSourceProvider getOrCreateSourceProvider(int id, int type) {
        InsetsSourceProvider provider = mProviders.get(id);
        if (provider != null) return provider;

        final InsetsSource source = new InsetsSource(id, type);
        if (type == ITYPE_IME) {
            provider = new ImeInsetsSourceProvider(source, this, mDisplayContent);
        } else {
            provider = new InsetsSourceProvider(source, this, mDisplayContent);
        }
        mProviders.put(id, provider);
        return provider;
    }
}
```

### 4.6 Insets 从 WMS 到 View 的传递链路

```
WMS (system_server)                         App 进程
──────────────────                         ──────────
InsetsSourceProvider                        
  │ updateSourceFrame()                    
  ▼                                        
InsetsStateController                      
  │ notifyInsetsChanged()                  
  ▼                                        
WindowState.notifyInsetsChanged()          
  │ 通过 IWindow.Stub Binder 回调          
  ▼                                        ▼
                                           ViewRootImpl.dispatchInsetsChanged()
                                             │
                                             ▼
                                           InsetsController.onStateChanged(InsetsState)
                                             │
                                             ├── 计算各类型 Insets 值
                                             │
                                             ├── 触发 WindowInsets 分发
                                             │     ▼
                                             │   View.onApplyWindowInsets()
                                             │     │
                                             │     ▼
                                             │   WindowInsetsCompat.getInsets(Type.systemBars())
                                             │     → 应用根据 Insets 调整 padding/margin
                                             │
                                             └── 如果启用了 Insets 动画
                                                   ▼
                                                 WindowInsetsAnimation.Callback
                                                   .onProgress(insets, runningAnimations)
                                                   → 应用实时响应 Insets 动画
```

> **稳定性架构师视角**：Insets 回调链条中的每一环都可能出问题。`notifyInsetsChanged()` 通过 Binder 从 system_server 发送到 App 进程，如果 App 主线程阻塞（如 I/O 操作），Insets 更新会延迟——用户看到的是 IME 已经弹出但内容还没有上移，出现短暂的遮挡。更严重的是，如果 `View.onApplyWindowInsets()` 的自定义实现抛出异常，会导致 Insets 链路断裂——后续所有 Insets 更新都不再生效，内容永久被 SystemBar 遮挡。

### 4.7 IME Insets 的特殊处理

IME（输入法）是最复杂的 Insets 源。与 StatusBar/NavigationBar 不同，IME 的显示/隐藏具有动画过程，且其高度在运行时动态变化。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/ImeInsetsSourceProvider.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/ImeInsetsSourceProvider.java（简化）
class ImeInsetsSourceProvider extends InsetsSourceProvider {

    private boolean mImeShowing;
    private int mImeTargetWindowToken;  // IME 服务的目标窗口

    @Override
    void updateSourceFrame(Rect newFrame) {
        super.updateSourceFrame(newFrame);
        // IME 特殊处理：需要确定 IME 的目标窗口
        // IME 的 Insets 只影响 IME target 窗口及其之下的窗口
    }

    void scheduleShowImePostLayout(WindowState imeTarget) {
        mImeTargetWindowToken = imeTarget.mToken.asBinder();
        // IME 显示需要等待目标窗口布局完成后再执行
        // 避免 IME 动画与窗口布局动画冲突
    }
}
```

**IME Insets 的时序问题：**

```
T1: 用户点击 EditText → 请求显示 IME
T2: IMMS 通知 IME 服务显示 → IME 窗口 addWindow
T3: IME 窗口 relayoutWindow → 获得 Surface → 开始绘制
T4: IME 绘制完成 → finishDrawingWindow
T5: WMS 更新 IME InsetsSource → notifyInsetsChanged → App 收到新 Insets
T6: App 调整布局 → 内容上移 → 避开 IME

    ★ T3-T5 之间的时间窗口内，IME 可能已经部分可见但 Insets 还未更新
    → 用户看到 IME 遮住了输入框的瞬间闪烁
```

---

## 5. relayoutWindow — Surface 尺寸与位置同步

### 5.1 relayoutWindow 的定位

`relayoutWindow()` 是 App 与 WMS 之间最频繁的 Binder 调用之一。每当 App 需要更新窗口的大小、可见性、Surface 状态时，都需要通过 `relayoutWindow()` 与 WMS 同步。

```
App 进程                                    system_server
──────────                                 ──────────────
ViewRootImpl.performTraversals()           
    │ 检测到窗口属性变化                     
    │ (大小/可见性/flags 变化)              
    ▼                                      
ViewRootImpl.relayoutWindow()              
    │ 构建请求参数                          
    ▼                                      
mWindowSession.relayout(                   
    mWindow,          // IWindow Binder    
    mWindowAttributes,// LayoutParams      
    requestedWidth,   // 请求的宽度         
    requestedHeight,  // 请求的高度         
    viewVisibility,   // 可见性            
    flags,            // 标志位            
    outFrames,        // [OUT] 新的 Frame  
    outConfig,        // [OUT] 配置信息    
    outSurfaceControl,// [OUT] Surface     
    outInsetsState,   // [OUT] Insets 状态 
    outInsetsControls // [OUT] Insets 控制 
) ─── Binder IPC ──▶ WMS.relayoutWindow()
                         │
                         ├── 获取 mGlobalLock
                         │
                         ├── 更新 WindowState 属性
                         │     (mAttrs, mRequestedWidth/Height)
                         │
                         ├── 创建或更新 Surface
                         │     (createSurfaceControl)
                         │
                         ├── 执行 performLayout()
                         │     → 重新计算所有窗口的 Frame
                         │
                         ├── 构建返回信息
                         │     (outFrames, outInsetsState)
                         │
                         └── 释放 mGlobalLock
                     ◀── Binder 返回 ────
    │
    ▼
ViewRootImpl 使用新的 Frame/Surface/Insets
    ├── 更新 Surface 尺寸
    ├── 执行 measure → layout → draw
    └── 应用新的 Insets
```

### 5.2 WMS.relayoutWindow() 的核心实现

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java（简化）
public int relayoutWindow(Session session, IWindow client,
        WindowManager.LayoutParams attrs,
        int requestedWidth, int requestedHeight,
        int viewVisibility, int flags, int seq,
        int lastSyncSeqId,
        ClientWindowFrames outFrames,
        MergedConfiguration mergedConfiguration,
        SurfaceControl outSurfaceControl,
        InsetsState outInsetsState,
        InsetsSourceControl.Array outActiveControls,
        Bundle outSyncSeqIdBundle) {

    int result = 0;
    synchronized (mGlobalLock) {
        // Step 1: 查找 WindowState
        final WindowState win = windowForClientLocked(session, client, false);
        if (win == null) return 0;

        final DisplayContent displayContent = win.getDisplayContent();

        // Step 2: 更新窗口属性
        if (attrs != null) {
            win.mAttrs.copyFrom(attrs);
        }
        win.setRequestedSize(requestedWidth, requestedHeight);

        // Step 3: 处理可见性变化
        final boolean visibilityChanged =
                (win.mViewVisibility != viewVisibility);
        win.mViewVisibility = viewVisibility;

        // Step 4: 创建或更新 Surface
        final boolean shouldRelayout = viewVisibility == View.VISIBLE
                && (win.mRelayoutCalled == false
                    || win.mViewVisibility != View.VISIBLE
                    || requestedWidth != win.mLastRequestedWidth
                    || requestedHeight != win.mLastRequestedHeight);

        if (shouldRelayout) {
            result = createSurfaceControl(outSurfaceControl, result,
                    win, win.mWinAnimator);
        } else {
            // 不需要创建 Surface，但可能需要更新位置/大小
            win.mWinAnimator.updateSurfacePosition();
        }

        // Step 5: 执行布局计算
        if (displayContent.mLayoutNeeded) {
            displayContent.performLayout(false /* initial */,
                    false /* updateInputWindows */);
        }

        // Step 6: 填充返回信息
        outFrames.frame.set(win.getFrame());
        outFrames.displayFrame.set(win.getDisplayFrame());
        outFrames.parentFrame.set(win.getParentFrame());

        // 返回 InsetsState
        win.getInsetsState().toOutInsetsState(outInsetsState);

        // 返回 MergedConfiguration
        win.getMergedConfiguration(mergedConfiguration);

        win.mRelayoutCalled = true;
        win.mLastRequestedWidth = requestedWidth;
        win.mLastRequestedHeight = requestedHeight;

        result |= RELAYOUT_RES_IN_TOUCH_MODE
                ? WindowManagerGlobal.RELAYOUT_RES_IN_TOUCH_MODE : 0;
    }
    return result;
}
```

### 5.3 Binder 调用的代价

`relayoutWindow()` 的 Binder 调用是一个完整的同步往返（round-trip），涉及以下开销：

| 开销项 | 典型耗时 | 说明 |
|:---|:---|:---|
| Binder 序列化/反序列化 | 0.1-0.5ms | LayoutParams + Frame + InsetsState |
| `mGlobalLock` 获取 | 0-50ms+ | 取决于锁竞争程度 |
| `performLayout()` | 1-10ms | 取决于窗口数量 |
| Surface 创建（如需要） | 1-5ms | SurfaceFlinger 通信 |
| 总计 | 2-65ms+ | 轻负载 ~5ms，重负载可达数十毫秒 |

```
performTraversals() 中的 relayoutWindow 调用时序:

┌────────────────────── App 主线程 ──────────────────────┐
│ performTraversals                                      │
│   ├── relayoutWindow()                                 │
│   │     ├── Binder 序列化        [0.3ms]               │
│   │     ├── ━━━ 等待 WMS ━━━━━  [2-50ms]              │ ← 主线程阻塞！
│   │     └── Binder 反序列化      [0.2ms]               │
│   ├── measure()                  [varies]              │
│   ├── layout()                   [varies]              │
│   └── draw()                     [varies]              │
└────────────────────────────────────────────────────────┘
                                     │
                            Binder 到 WMS │
                                     ▼
┌────── system_server WMS 线程 ─────────────────────────┐
│ relayoutWindow()                                       │
│   ├── acquire mGlobalLock         [0-50ms]             │ ← 锁竞争热点
│   ├── createSurfaceControl()      [1-5ms]              │
│   ├── performLayout()             [1-10ms]             │
│   └── release mGlobalLock                              │
└────────────────────────────────────────────────────────┘
```

> **稳定性架构师视角**：`relayoutWindow()` 期间 App 主线程完全阻塞，等待 WMS 端处理完成。如果 WMS 端 `mGlobalLock` 被其他操作长时间持有（如另一个 App 的 `addWindow` 或 Display 配置变更），App 的 `performTraversals()` 将被延迟数十毫秒甚至数百毫秒——在 Systrace 中表现为 `relayoutWindow` 占据了整个 VSYNC 周期，导致掉帧。更严重的场景：如果 App 在短时间内频繁调用 `requestLayout()`（如动画中每帧都触发 `relayoutWindow`），会造成 `mGlobalLock` 的严重竞争，影响整个系统的所有窗口操作。

### 5.4 过度 relayout 的典型模式

以下模式会导致不必要的 `relayoutWindow()` 调用：

| 过度 relayout 模式 | 触发原因 | 影响 |
|:---|:---|:---|
| 动画中每帧改变窗口大小 | `LayoutParams.width/height` 在动画回调中不断变化 | 每帧一次 Binder 往返 |
| IME 弹出/收起过程中连续 relayout | Insets 动画触发多次 `requestLayout()` | 高频 `mGlobalLock` 竞争 |
| 软键盘高度变化 | 键盘切换布局导致 IME 高度多次变化 | 连续的 Insets 更新 + relayout |
| `WRAP_CONTENT` 窗口内容变化 | 内容大小变化 → 请求新的窗口大小 | 每次内容更新都触发 relayout |

---

## 6. 配置变更与窗口重建

### 6.1 配置变更的触发源

Android 系统的 Configuration 变更会直接影响窗口布局。以下事件都是配置变更的触发源：

| 触发事件 | Configuration 变化 | 窗口影响 |
|:---|:---|:---|
| 屏幕旋转 | `orientation`, `screenWidthDp`, `screenHeightDp` | 所有窗口重新布局 |
| 分辨率变化 | `densityDpi`, `screenWidthDp`, `screenHeightDp` | 所有窗口重新布局 + Activity 可能重建 |
| 折叠屏展开/折叠 | `screenWidthDp`, `screenHeightDp`, `smallestScreenWidthDp` | Display 尺寸变化 → 大规模重建 |
| 字体大小变化 | `fontScale` | 不影响窗口 Frame，但触发 Activity 重建 |
| Locale 变化 | `locale` | 不影响窗口 Frame，但触发 Activity 重建 |
| 深色模式切换 | `uiMode` | 触发 Activity 重建 |
| 多窗口模式切换 | `screenWidthDp`, `screenHeightDp`, `smallestScreenWidthDp` | Task bounds 变化 → 窗口 Frame 变化 |

### 6.2 配置变更的传播路径

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java`
> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java`
> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/ConfigurationContainer.java`

```
屏幕旋转为例:

DisplayManagerService: 检测到传感器旋转事件
    │
    ▼
DisplayContent.updateRotationUnchecked()
    │ 计算新的屏幕方向和尺寸
    ▼
DisplayContent.updateDisplayOverrideConfigurationLocked()
    │ 更新 DisplayContent 的 Configuration
    │
    ├── ConfigurationContainer.onConfigurationChanged()
    │     │ 自顶向下传播到整棵 WindowContainer 树
    │     ▼
    │   DisplayArea.onConfigurationChanged()
    │     └── Task.onConfigurationChanged()
    │           └── ActivityRecord.onConfigurationChanged()
    │                 │
    │                 ├── [情况 A] Activity 声明了 configChanges 包含 orientation
    │                 │     → 调用 Activity.onConfigurationChanged()
    │                 │     → 不重建 Activity，只更新配置
    │                 │     → 窗口执行 relayoutWindow() 更新大小
    │                 │
    │                 └── [情况 B] Activity 未声明 configChanges
    │                       → ActivityRecord.relaunchActivityLocked()
    │                       → Activity.onDestroy() → onCreate()
    │                       → 旧窗口销毁，新窗口创建
    │                       → 新窗口 addWindow → relayoutWindow
    │
    └── DisplayContent.performLayout()
          └── 重新计算所有窗口的 Frame
```

### 6.3 Activity 重建 vs onConfigurationChanged

```java
// AndroidManifest.xml 中的 configChanges 声明决定了 Activity 的行为

// 情况 A：声明了 orientation → 不重建
<activity android:name=".MainActivity"
          android:configChanges="orientation|screenSize|screenLayout|smallestScreenSize" />

// 情况 B：未声明 → 重建（默认行为）
<activity android:name=".DetailActivity" />
```

**两种路径的时序对比：**

```
情况 A: onConfigurationChanged (快路径)        情况 B: Activity 重建 (慢路径)
──────────────────────────────             ───────────────────────────────
T=0    配置变更通知                          T=0    配置变更通知
T=5ms  onConfigurationChanged()             T=5ms  onPause()
T=8ms  View 树 measure/layout/draw          T=20ms onStop()
T=16ms 新帧显示 ✓                           T=40ms onDestroy()
                                            T=45ms removeWindow() → 旧 Surface 销毁
                                            T=50ms onCreate() (新配置)
                                            T=70ms setContentView() → addWindow()
                                            T=90ms relayoutWindow() → 新 Surface 创建
                                            T=110ms onResume()
                                            T=120ms 首帧绘制完成
                                            T=130ms 新帧显示 ✓

快路径: ~16ms                                慢路径: ~130ms
```

### 6.4 配置变更期间的 Surface 生命周期

```
配置变更前:
WindowState(old) ── SurfaceControl(old) ── Layer(old) in SurfaceFlinger

情况 A (onConfigurationChanged):
WindowState 不变 → relayoutWindow() → SurfaceControl 更新大小
                    → SurfaceFlinger resize Layer
                    → Buffer 重新分配
                    → App 使用新大小 Surface 绘制

情况 B (Activity 重建):
WindowState(old) → removeImmediately() → SurfaceControl(old).destroy()
                                          → SurfaceFlinger remove Layer(old)
                   同时
WindowState(new) → addWindow() → relayoutWindow()
                   → SurfaceControl(new).create()
                   → SurfaceFlinger create Layer(new)
                   → App 在新 Surface 上绘制

★ 危险窗口期: old Surface 已销毁，new Surface 尚未就绪
  → 屏幕上该区域暂时无内容 → 用户看到黑色闪烁
```

### 6.5 折叠屏设备的特殊挑战

折叠屏设备在展开/折叠时触发的配置变更尤为复杂：

```
折叠态                    展开过程                    展开态
┌─────────┐              ┌──────────────────────┐    ┌──────────────────────┐
│ 1080×   │              │ Display 尺寸从        │    │ 2200×               │
│ 2400    │    fold ───▶ │ 1080×2400 变为        │──▶ │ 2480                │
│ (内屏)   │   event     │ 2200×2480            │    │ (内屏展开)           │
└─────────┘              │                      │    └──────────────────────┘
                         │ ★ 关键变化:           │
                         │   screenWidthDp 变化  │
                         │   screenHeightDp 变化 │
                         │   density 可能变化     │
                         │   smallestScreenWidthDp│
                         │   变化                │
                         └──────────────────────┘
```

> **稳定性架构师视角**：折叠屏展开/折叠是最容易暴露配置变更问题的场景。常见问题包括：（1）Activity 重建过程中 ViewModel 数据丢失——开发者忘记在 `onSaveInstanceState` 中保存关键状态；（2）old Surface 销毁到 new Surface 就绪之间的黑屏闪烁——在低端折叠屏设备上可能持续 200ms+；（3）`smallestScreenWidthDp` 的变化可能触发完全不同的资源限定符（如从 layout-sw600dp 切换到 layout-sw800dp），导致布局剧烈变化；（4）如果 App 在 `onConfigurationChanged` 中执行了耗时操作（如重新加载图片资源），主线程阻塞 → 折叠/展开过程中出现明显卡顿。

---

## 7. 稳定性风险总结

### 7.1 布局与 Insets 相关的风险速查表

| 风险类型 | 根因 | 典型现象 | 日志/排查关键字 | 影响等级 |
|:---|:---|:---|:---|:---|
| 布局循环不收敛 | 两个窗口的布局相互依赖 | system_server CPU 100%，系统全局卡顿 | `performSurfacePlacementLoop looped too many times` | P0：系统级 |
| 内容被 StatusBar 遮挡 | Insets 未正确消费 | 顶部内容被状态栏遮盖 | 检查 `View.onApplyWindowInsets()` | P1：用户可见 |
| 内容被 NavigationBar 遮挡 | 手势导航 Insets 处理不当 | 底部按钮被导航栏覆盖 | `fitSystemWindows` / `WindowInsetsCompat` | P1：用户可见 |
| IME 弹出后内容未上移 | IME Insets 回调异常 | 输入框被键盘遮挡 | `View.getRootWindowInsets()` 检查 IME insets | P1：用户可见 |
| DisplayCutout 适配错误 | 未处理 `displayCutout()` Insets | 内容显示在刘海/挖孔区域 | `LAYOUT_IN_DISPLAY_CUTOUT_MODE_*` | P2：特定设备 |
| relayoutWindow 耗时过长 | mGlobalLock 竞争严重 | 帧率下降，卡顿 | Systrace 中 `relayoutWindow` 耗时 | P1：性能 |
| 过度 relayout | 动画中频繁改变窗口属性 | 系统级 jank，WMS 线程繁忙 | Systrace 中高频 `relayout` 调用 | P1：性能 |
| 配置变更黑屏 | Activity 重建期间 Surface 空窗期 | 旋转屏幕/展开折叠屏时黑屏闪烁 | `Configuration changed` + Surface 生命周期 | P2：用户体验 |
| 配置变更 Crash | `onSaveInstanceState` 未正确保存状态 | 旋转后 App Crash | `NullPointerException` in `onCreate()` | P1：App Crash |
| IME 动画闪烁 | Insets 动画与布局动画不同步 | IME 弹出/收起时界面闪烁 | `WindowInsetsAnimation` 回调时序 | P2：用户体验 |
| 折叠屏 Surface 泄漏 | 旧 Surface 未正确释放 | 内存持续增长 | `dumpsys SurfaceFlinger` Layer 数量 | P1：内存 |

### 7.2 排查路径决策树

```
窗口布局异常排查:

内容被系统 UI 遮挡?
  │
  ├── 被 StatusBar 遮挡
  │     → 检查 App 是否消费了 systemBars() insets
  │     → dumpsys window <package> 检查 mFrame 和 mContentFrame
  │     → 确认 LAYOUT_IN_DISPLAY_CUTOUT_MODE 设置
  │
  ├── 被 NavigationBar 遮挡
  │     → 检查手势导航 vs 三键导航的 Insets 差异
  │     → dumpsys window 检查 NavigationBar 的 Frame
  │     → 确认 App 是否正确处理 navigationBars() insets
  │
  └── 被 IME 遮挡
        → 确认 softInputMode 设置 (adjustResize / adjustPan / adjustNothing)
        → dumpsys input_method 检查 IME 状态
        → 确认 View 是否在 IME Insets 变化时调整布局

系统级卡顿?
  │
  ├── performSurfacePlacement 循环
  │     → Systrace 检查 performLayout 调用次数和耗时
  │     → dumpsys window 检查 mLayoutNeeded 状态
  │
  └── relayoutWindow 锁竞争
        → Systrace 检查 mGlobalLock 持有时间
        → 统计单位时间内 relayoutWindow 调用频次
        → 确认是否存在过度 relayout 模式
```

---

## 8. 实战案例

### Case 1：Android 版本升级后内容被 StatusBar 遮挡——Insets API 迁移问题

**（典型模式）**

**问题现象**

某 App 从 targetSdkVersion 29 升级到 30 后，用户反馈首页的标题栏被 StatusBar 遮挡。在 Android 11+ 设备上 100% 复现，Android 10 及以下设备无此问题。

**分析思路**

**Step 1：确认窗口 Frame 和 Insets**

```bash
$ adb shell dumpsys window <package>
  Window #3 Window{abc1234 u0 com.example.app/com.example.app.MainActivity}:
    mFrame=[0,0][1080,2400]
    mContentInsets=Rect(0, 0 - 0, 0)     ← 异常：ContentInsets 全为 0
    mVisibleInsets=Rect(0, 0 - 0, 0)
    InsetsState:
      StatusBar: visible=true, frame=[0,0][1080,100]
      NavigationBar: visible=true, frame=[0,2268][1080,2400]
```

关键发现：`mContentInsets` 全为 0，说明系统认为 App 自己处理了 Insets——不再为 App 自动添加 padding。

**Step 2：分析 Android 11 的行为变化**

Android 11（API 30）引入了 `Window.setDecorFitsSystemWindows(false)` 作为默认行为的变更。当 `targetSdkVersion >= 30` 时：

```java
// Android 11+ 的行为变化
// targetSdkVersion 29: 系统自动通过 fitSystemWindows 消费 Insets
// targetSdkVersion 30: 系统不再自动消费，App 需要自行处理

// 旧的自动处理链路 (targetSdk 29):
// DecorView.fitSystemWindows() → 自动设置 padding → 内容不会被遮挡

// 新的行为 (targetSdk 30):
// 系统不再调用 fitSystemWindows()
// App 需要通过 setOnApplyWindowInsetsListener 自行处理
```

**Step 3：确认 App 代码中的 Insets 处理**

```java
// 问题代码：App 使用了已废弃的 API
@Override
protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.activity_main);

    // 在 targetSdk 29 时有效，targetSdk 30 时不再生效
    getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
}
```

App 使用了 `SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN` 让内容延伸到 StatusBar 下方，但依赖 `DecorView` 的自动 `fitSystemWindows` 来为 Toolbar 添加 padding。升级到 targetSdk 30 后，自动处理失效。

**根因**

targetSdkVersion 升级到 30 后，系统不再通过 `fitSystemWindows` 自动消费 Insets。App 依赖的旧 API（`SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN` + 自动 `fitSystemWindows`）失效，导致内容直接绘制在 StatusBar 下方。

**修复方案**

```java
// 修复方案：迁移到 Android 11+ 的 WindowInsets API
@Override
protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.activity_main);

    // 使用新 API 替代已废弃的 SystemUiVisibility
    WindowCompat.setDecorFitsSystemWindows(getWindow(), false);

    // 手动处理 Insets
    View toolbar = findViewById(R.id.toolbar);
    ViewCompat.setOnApplyWindowInsetsListener(toolbar, (view, insets) -> {
        Insets systemBarInsets = insets.getInsets(
                WindowInsetsCompat.Type.systemBars());
        view.setPadding(
                systemBarInsets.left,
                systemBarInsets.top,      // StatusBar 高度作为 top padding
                systemBarInsets.right,
                0);
        return WindowInsetsCompat.CONSUMED;
    });

    // 底部内容区域处理 NavigationBar insets
    View content = findViewById(R.id.content);
    ViewCompat.setOnApplyWindowInsetsListener(content, (view, insets) -> {
        Insets systemBarInsets = insets.getInsets(
                WindowInsetsCompat.Type.systemBars());
        Insets imeInsets = insets.getInsets(
                WindowInsetsCompat.Type.ime());
        int bottomInset = Math.max(systemBarInsets.bottom, imeInsets.bottom);
        view.setPadding(0, 0, 0, bottomInset);
        return WindowInsetsCompat.CONSUMED;
    });
}
```

**防御建议**：在 targetSdkVersion 升级前，应在 Android 11+ 设备上全量回归 Insets 相关场景。检查清单包括：StatusBar 区域内容是否可见、NavigationBar 区域按钮是否可点击、IME 弹出后输入框是否被遮挡、横屏模式下 DisplayCutout 处理是否正确。

---

### Case 2：performSurfacePlacement 无限循环导致 system_server CPU 100%

**（典型模式）**

**问题现象**

用户反馈设备整体卡顿、无响应。通过 `adb shell top` 发现 `system_server` 进程 CPU 占用率持续 100%。约 30-60 秒后，Watchdog 杀死 system_server，设备重启。

**分析思路**

**Step 1：Systrace 分析 system_server**

```
Systrace 中 system_server 主线程:

|---performSurfacePlacement---|---performSurfacePlacement---|---perform...
   6轮循环, 耗时 120ms            6轮循环, 耗时 115ms          6轮...
   
每轮循环的 performLayout 都触发了新的 mLayoutNeeded = true
→ 6 轮后仍未收敛 → 函数返回 → 但立即被再次触发
→ 形成无限循环
```

**Step 2：分析布局循环的参与者**

```bash
$ adb shell dumpsys window windows | grep "mLayoutNeeded"
  Window #5 Window{... StatusBar}: mLayoutNeeded=true
  Window #12 Window{... com.example.app/.MainActivity}: mLayoutNeeded=true
```

每轮布局后，StatusBar 和 MainActivity 都被标记为 `mLayoutNeeded = true`。

**Step 3：分析循环依赖**

通过在 `performLayout` 中添加日志追踪（仅调试环境），发现循环模式如下：

```
Round 1:
  layoutWindowLw(StatusBar) → StatusBar.mFrame = [0,0,1080,100]
  layoutWindowLw(MainActivity) → 检测到 StatusBar Insets = top:100
    → 请求 relayout(height = screenHeight - 100 = 2300)
    → mLayoutNeeded = true ★

Round 2:
  layoutWindowLw(StatusBar) → 检测到 App 窗口尺寸变化
    → StatusBar 高度因沉浸模式计算变化 → mFrame = [0,0,1080,80]
    → mLayoutNeeded = true ★
  layoutWindowLw(MainActivity) → 检测到 StatusBar Insets 变化 = top:80
    → 请求 relayout(height = screenHeight - 80 = 2320)
    → mLayoutNeeded = true ★

Round 3:
  layoutWindowLw(StatusBar) → 又检测到 App 窗口尺寸变化
    → StatusBar 恢复高度 → mFrame = [0,0,1080,100]
    → mLayoutNeeded = true ★

→ Round 3 的状态与 Round 1 相同 → 进入 2-3 循环
```

**根因**

App 使用了自定义的沉浸式状态栏方案。该方案在 `View.onApplyWindowInsets()` 中根据 StatusBar 的 Insets 值动态调整了窗口的 `LayoutParams.height`。但 StatusBar 的高度又受到 App 窗口是否全屏的影响（某些 OEM 的 `DisplayPolicy` 在 App 全屏时缩小 StatusBar 高度）。两者形成循环依赖：

```
App 窗口高度 ──依赖──▶ StatusBar Insets (top)
      ▲                        │
      │                        ▼
      └────依赖──── StatusBar 高度（受 App 全屏状态影响）
```

**修复方案**

```java
// 修复前：在 onApplyWindowInsets 中动态修改窗口高度
ViewCompat.setOnApplyWindowInsetsListener(rootView, (v, insets) -> {
    int statusBarHeight = insets.getInsets(
            WindowInsetsCompat.Type.statusBars()).top;
    // ✗ 错误：修改窗口 LayoutParams 会触发 relayoutWindow
    WindowManager.LayoutParams lp = getWindow().getAttributes();
    lp.height = getScreenHeight() - statusBarHeight;
    getWindow().setAttributes(lp);
    return insets;
});

// 修复后：使用 padding 而非修改窗口大小
ViewCompat.setOnApplyWindowInsetsListener(rootView, (v, insets) -> {
    int statusBarHeight = insets.getInsets(
            WindowInsetsCompat.Type.statusBars()).top;
    // ✓ 正确：修改 View padding 不会触发 relayoutWindow
    v.setPadding(
            v.getPaddingLeft(),
            statusBarHeight,
            v.getPaddingRight(),
            v.getPaddingBottom());
    return WindowInsetsCompat.CONSUMED;
});
```

**关键教训**：永远不要在 `onApplyWindowInsets` 回调中修改窗口的 `LayoutParams`（尤其是 `width`、`height`、`x`、`y`）。这会触发 `relayoutWindow()`，进而触发新的布局循环。应使用 View 级别的 `padding` / `margin` 调整来响应 Insets 变化。

---

## 总结

窗口布局与 Insets 计算是 WMS 中连接"窗口逻辑状态"与"屏幕物理像素"的桥梁。对于稳定性架构师，以下关键点必须掌握：

1. **布局是批量延迟执行的**：`performSurfacePlacementLoop()` 最多执行 6 轮迭代。布局循环不收敛是 P0 级系统问题——它会独占 `mGlobalLock`，使所有窗口操作停滞，最终触发 Watchdog 杀死 system_server。排查入口是 Systrace 中 `performSurfacePlacement` 的调用频率和单次耗时。

2. **Insets 是窗口与系统 UI 的沟通协议**：`InsetsState` → `InsetsSource` → `InsetsSourceProvider` → `InsetsStateController` 构成了完整的 Insets 管理链路。Insets 回调异常（未消费、异常中断、重复消费）会导致内容被系统 UI 遮挡。Android 11+ 的 `WindowInsets` API 是新标准，旧的 `fitSystemWindows` / `SYSTEM_UI_FLAG_*` 在高版本中行为不一致。

3. **relayoutWindow 是性能瓶颈**：每次 `relayoutWindow()` 都是一次 Binder 同步往返 + `mGlobalLock` 竞争。过度 relayout（动画中改变窗口大小、Insets 回调中修改 LayoutParams）是系统级 jank 的常见根因。黄金法则：**Insets 变化只修改 View 的 padding/margin，不修改窗口的 LayoutParams**。

4. **配置变更是窗口稳定性的试金石**：屏幕旋转和折叠屏展开/折叠会触发大规模的窗口重建和布局计算。Surface 空窗期（旧 Surface 已销毁、新 Surface 未就绪）是黑屏闪烁的根源。声明 `android:configChanges` 可以走快路径避免 Activity 重建，但必须在 `onConfigurationChanged()` 中正确处理所有配置变化。

5. **DisplayCutout 和手势导航增加了 Insets 的复杂度**：不同设备的 Cutout 形状不同（水滴、药丸、挖孔、刘海），手势导航与三键导航的 Insets 区域不同。App 必须使用 `WindowInsetsCompat` 而非硬编码系统 UI 高度值，否则在特定设备上必然出现布局异常。

---

## 附录：核心源码路径索引

| 文件名 | 完整路径 | 说明 |
|:---|:---|:---|
| `WindowSurfacePlacer.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowSurfacePlacer.java` | 布局调度器，`requestTraversal()` / `performSurfacePlacementLoop()` |
| `DisplayContent.java` | `frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java` | `performLayout()` 所在，每个 Display 的布局入口 |
| `DisplayPolicy.java` | `frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java` | 系统装饰策略，`beginLayoutLw()` / `layoutWindowLw()` / `finishLayoutLw()` |
| `WindowState.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | `computeFrame()` 所在，单个窗口 Frame 计算 |
| `WindowManagerService.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | `relayoutWindow()` 所在，Surface 尺寸同步入口 |
| `RootWindowContainer.java` | `frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java` | `performSurfacePlacementNoTrace()` 所在 |
| `InsetsState.java` | `frameworks/base/core/java/android/view/InsetsState.java` | Insets 信息容器，`calculateInsets()` |
| `InsetsSource.java` | `frameworks/base/core/java/android/view/InsetsSource.java` | 单个 Insets 源的数据结构 |
| `InsetsStateController.java` | `frameworks/base/services/core/java/com/android/server/wm/InsetsStateController.java` | 每个 Display 的 Insets 管理中枢 |
| `InsetsSourceProvider.java` | `frameworks/base/services/core/java/com/android/server/wm/InsetsSourceProvider.java` | Insets 源的 WMS 端管理者 |
| `ImeInsetsSourceProvider.java` | `frameworks/base/services/core/java/com/android/server/wm/ImeInsetsSourceProvider.java` | IME 专用的 Insets Provider |
| `ViewRootImpl.java` | `frameworks/base/core/java/android/view/ViewRootImpl.java` | `relayoutWindow()` App 端调用点 |
| `InsetsController.java` | `frameworks/base/core/java/android/view/InsetsController.java` | App 端 Insets 控制器 |
| `WindowInsets.java` | `frameworks/base/core/java/android/view/WindowInsets.java` | App 端 Insets API，`Type` 定义 |
| `ActivityRecord.java` | `frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java` | `onConfigurationChanged()` / `relaunchActivityLocked()` |
| `ConfigurationContainer.java` | `frameworks/base/services/core/java/com/android/server/wm/ConfigurationContainer.java` | 配置变更传播基类 |
| `DisplayFrames.java` | `frameworks/base/services/core/java/com/android/server/wm/DisplayFrames.java` | 各类 Frame 区域定义 |

---

下一篇 [05-窗口动画与 Transition 机制](05-窗口动画与Transition机制.md) 将深入 WMS 的窗口动画系统，分析 WindowAnimator、Transition 动画框架、以及动画过程中 Surface 与 InputDispatcher 的同步机制，以及动画异常导致的稳定性问题。
