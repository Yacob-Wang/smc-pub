# 01-Window 系统总览：从 addView 到屏幕显示的全链路

## 1. Window 系统是什么

Android 设备上用户能看到的一切——Activity 的内容区域、状态栏的时钟与图标、底部导航栏、弹出的 Dialog、Toast 提示、悬浮的 PopupWindow、输入法键盘——在系统层面都是 **Window**。Window 系统是 Android 的"骨骼系统"：它决定了每一块 UI 在屏幕上的位置、大小、层级，以及谁能接收用户的触摸输入。

**用一句话定义：** Window 系统是 Android 中负责管理所有窗口的创建、布局、层级排列、焦点分配、Surface 分配与 Input 事件路由的完整管理框架，其核心服务是运行在 `system_server` 中的 `WindowManagerService`（WMS）。

### 1.1 Window 的三要素

从架构视角看，一个 Window 并非一个单独的类，而是三个核心组件的组合：

```
Window = Surface + WindowManager.LayoutParams + InputChannel

┌─────────────────────────────────────────────────┐
│                   Window                         │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │   Surface    │  │ LayoutParams │  │ Input   │ │
│  │ (绘图画布)   │  │ (窗口属性)    │  │ Channel │ │
│  │             │  │              │  │ (输入通道)│ │
│  │ 由 Surface  │  │ type: 窗口类型│  │ 基于     │ │
│  │ Flinger 分配│  │ flags: 行为  │  │ socket  │ │
│  │ 的 Buffer   │  │ x,y,w,h: 几何│  │ pair    │ │
│  └─────────────┘  └──────────────┘  └─────────┘ │
└─────────────────────────────────────────────────┘
```

- **Surface**：SurfaceFlinger 分配的图形缓冲区，是 Window 在屏幕上"画东西"的画布。没有 Surface，Window 就是一个不可见的逻辑实体。
- **WindowManager.LayoutParams**：描述窗口的类型（`TYPE_APPLICATION`、`TYPE_STATUS_BAR`、`TYPE_INPUT_METHOD` 等）、标志位（`FLAG_NOT_TOUCHABLE`、`FLAG_KEEP_SCREEN_ON` 等）、以及几何参数（位置、大小、gravity）。WMS 依据 LayoutParams 决定窗口的层级和行为。
- **InputChannel**：基于 `socketpair` 的双向通信管道，InputDispatcher 通过它向窗口投递触摸/按键事件，App 通过它回复 `finishInputEvent`。没有 InputChannel 的窗口无法接收任何输入。

### 1.2 WMS 在 Android 系统中的角色

WMS 是 `system_server` 中最核心的系统服务之一，与 AMS（ActivityManagerService）、IMS（InputManagerService）并称"三巨头"。它的职责覆盖了 UI 显示的方方面面：

| 维度 | Window 系统的角色 |
|------|-------------------|
| 硬件抽象 | 屏蔽不同屏幕尺寸、密度、刷新率的差异，为上层提供统一的窗口坐标系和布局模型 |
| 安全隔离 | App 无法直接创建 Surface 或操纵其他 App 的窗口，所有窗口操作必须经过 WMS 权限校验 |
| 多窗口仲裁 | 系统同时存在数十个窗口（Activity、Dialog、StatusBar、NavigationBar、IME、Wallpaper），WMS 决定它们的 Z-order 和可见性 |
| 焦点管理 | WMS 维护 `FocusedWindow`，并通过 `InputMonitor` 同步到 InputDispatcher，决定谁接收 Key 事件 |
| 性能关键路径 | Window 的创建速度直接影响 Activity 启动时间（TTID/TTFD），Surface 的分配和释放直接影响内存和显示稳定性 |

### 1.3 一切皆 Window

Android 上用户可见的每一个 UI 元素，在 WMS 中都对应一个 `WindowState` 对象：

| UI 元素 | Window 类型 | LayoutParams.type | 说明 |
|---------|------------|-------------------|------|
| Activity 主窗口 | Application Window | `TYPE_BASE_APPLICATION` (1) | 每个 Activity 至少有一个 |
| Dialog | Application Window | `TYPE_APPLICATION` (2) | 附属于 Activity 的 token |
| PopupWindow | Sub-Window | `TYPE_APPLICATION_PANEL` (1000) | 必须有父窗口 |
| Toast | System Window | `TYPE_TOAST` (2005) | Android 11+ 改为后台限制 |
| StatusBar | System Window | `TYPE_STATUS_BAR` (2000) | SystemUI 进程持有 |
| NavigationBar | System Window | `TYPE_NAVIGATION_BAR` (2019) | SystemUI 进程持有 |
| 输入法（IME） | System Window | `TYPE_INPUT_METHOD` (2011) | InputMethodService 持有 |
| Wallpaper | System Window | `TYPE_WALLPAPER` (2013) | WallpaperManagerService 管理 |
| 系统弹窗（ANR 对话框） | System Window | `TYPE_APPLICATION_OVERLAY` (2038) | 需要 `SYSTEM_ALERT_WINDOW` 权限 |

### 1.4 Window 系统的历史演进

Window 系统从 Android 1.0 至今经历了多轮重大重构：

| 版本 | 关键变化 | 稳定性影响 |
|------|---------|-----------|
| Android 1.0 | WMS 初始版本，单一 Display，窗口管理逻辑直接写在 WMS 主类中 | 代码单体化，难以维护 |
| Android 4.0 (ICS) | 引入硬件加速渲染，Surface 与 HWC（Hardware Composer）对接 | GPU 驱动 Bug 导致黑屏/花屏 |
| Android 4.4 (KitKat) | 引入 `WindowAnimator`、窗口动画框架初步成型 | 动画卡顿与 Surface 泄漏 |
| Android 5.0 (Lollipop) | 引入 `Task` 和 `ActivityStack` 的窗口容器化雏形 | 多任务管理复杂化 |
| Android 7.0 (Nougat) | 分屏多窗口（Split-Screen），引入 `TaskPositioner` | 分屏切换时窗口状态不一致 |
| Android 8.0 (Oreo) | PiP（画中画）模式，`TYPE_APPLICATION_OVERLAY` 替代旧系统窗口类型 | 权限管控更严格，但兼容性问题增多 |
| Android 10 | `WindowContainer` 层级体系大重构：`DisplayContent` → `TaskDisplayArea` → `Task` → `ActivityRecord` → `WindowState` | 层级模型统一化，排查路径变深 |
| Android 12 | `SplashScreen` 系统化，`TaskFragment` 引入，`WindowManager` 扩展 API | 启动白屏/黑屏问题场景增多 |
| Android 12L | 大屏优化，`TaskDisplayArea` 支持多 root task | 多 Display 场景复杂度上升 |
| Android 13 | 完善 per-app language、Predictive Back Gesture 影响窗口动画 | 手势返回动画与窗口生命周期冲突 |
| Android 14 | `WindowContainer` 层级进一步统一，`BackNavigationController` 重构，窗口转场动画优化 | 转场动画 Surface 泄漏、WMS 锁竞争加剧 |

---

## 2. 为什么需要 WMS

初次接触 Window 系统的工程师可能会疑惑：为什么不让 App 自己管理窗口？答案是：Android 是一个多进程、多窗口操作系统，窗口管理涉及四个必须由系统侧统一解决的核心问题。

### 2.1 多窗口 Z-order 仲裁

Android 屏幕上同时存在数十个窗口，它们按照严格的层级（Z-order）堆叠。以一个典型场景为例：

```
Z-order (从高到低):
  ┌─────────────────────────────────────┐
  │  NavigationBar (TYPE_NAVIGATION_BAR)│  Z = 2019+
  ├─────────────────────────────────────┤
  │  StatusBar (TYPE_STATUS_BAR)        │  Z = 2000+
  ├─────────────────────────────────────┤
  │  IME Window (TYPE_INPUT_METHOD)     │  Z = 2011+
  ├─────────────────────────────────────┤
  │  Dialog (TYPE_APPLICATION)          │  Z = 2
  ├─────────────────────────────────────┤
  │  Activity Window (TYPE_BASE_APP)    │  Z = 1
  ├─────────────────────────────────────┤
  │  Wallpaper (TYPE_WALLPAPER)         │  Z = 2013 (特殊)
  └─────────────────────────────────────┘
```

WMS 必须回答：当用户触摸屏幕时，哪个窗口应该接收事件？当窗口重叠时，谁可见谁被遮挡？如果让 App 自行决定层级，恶意 App 可以把自己的窗口覆盖在银行 App 之上，伪造登录界面窃取密码。

**WMS 通过 `WindowState.mBaseLayer` + `WindowState.mSubLayer` 的二级层级模型统一管理 Z-order**，确保系统窗口（StatusBar、NavigationBar、IME）永远位于应用窗口之上，应用窗口之间按 Task 栈顺序排列。

### 2.2 Surface 资源管控

Surface 是有限的系统资源。每个 Surface 底层对应 SurfaceFlinger 中的一块图形缓冲区（GraphicBuffer），占用 GPU 显存或 ION 内存。典型的 1080p Surface 三缓冲占用约 24MB（1920×1080×4bytes×3buffers）。

如果 App 可以随意创建 Surface，可能出现：
- 恶意 App 创建大量 Surface 耗尽显存 → 其他 App 黑屏
- 泄漏的 Surface 不被回收 → 系统内存持续增长 → Low Memory Killer 频繁杀进程

因此，Surface 的创建权被收归 `system_server`。App 请求创建窗口时，WMS 通过 `WindowStateAnimator.createSurfaceLocked()` 在 SurfaceFlinger 中分配 Surface，并通过 `SurfaceControl` 进行管理。App 只能通过 `lockCanvas()` / `unlockCanvasAndPost()` 间接访问 Surface 的 Buffer。

### 2.3 窗口策略统一管理

Android 的窗口行为受系统策略控制：
- StatusBar 在全屏时隐藏、下拉时显示
- NavigationBar 在手势导航模式下变为透明条
- IME 弹出时，Activity 窗口需要上移（`adjustResize` / `adjustPan`）
- 屏幕旋转时，所有窗口需要重新计算 Insets 和布局

这些策略由 `DisplayPolicy`（Android 14 中替代了旧的 `PhoneWindowManager`）统一管理。如果让每个 App 自行处理这些策略，不仅增加开发负担，还会导致行为不一致。

```
// frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java
// DisplayPolicy 统一管理以下策略：
//   - System Bar 的可见性（StatusBar / NavigationBar）
//   - IME 弹出时的窗口调整策略
//   - 全屏 / 沉浸式模式的切换
//   - 屏幕旋转时的窗口适配
//   - Insets 的计算与分发
```

### 2.4 焦点管理与 Input 事件路由

WMS 是 Input 系统与窗口世界的桥梁。InputDispatcher 需要知道"当前哪个窗口应该接收 Key 事件"，这个信息由 WMS 通过以下链路同步：

```
WMS.updateFocusedWindowLocked()
  → computeFocusedWindow()         // 遍历窗口树，找到最顶层可聚焦窗口
    → InputMonitor.setInputFocusLw()
      → InputMonitor.updateInputWindowsLw()
        → setInputWindows() [Native]
          → InputDispatcher::setFocusedWindow()
```

如果 WMS 更新焦点不及时（如 Activity 切换时 WMS 锁被长时间持有），InputDispatcher 可能使用过期的焦点信息，导致：
- Key 事件发给了旧窗口 → 用户按返回键无反应
- 没有焦点窗口 → InputDispatcher 等待 → 5 秒后 ANR

### 2.5 如果没有 WMS 会怎样

| 缺失的约束 | 后果 |
|-----------|------|
| 无 Z-order 仲裁 | 恶意 App 可覆盖其他 App 窗口，钓鱼攻击、遮挡安全提示 |
| 无 Surface 管控 | Surface 泄漏导致显存耗尽，全屏黑屏或 SurfaceFlinger 崩溃 |
| 无策略统一管理 | 每个 App 自行处理 SystemBar/IME/旋转，行为混乱不一致 |
| 无焦点管理 | Key 事件无法正确路由，所有键盘输入失效或发错窗口 |
| 无权限校验 | 任意 App 可创建悬浮窗覆盖全屏，用户无法关闭 |

---

## 3. WMS 架构全景图

### 3.1 三层架构

WMS 的架构可以从三个层次理解：App 层（ViewRootImpl）→ WMS 层（system_server）→ SurfaceFlinger 层（Native 合成器）。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          App 进程                                           │
│                                                                             │
│  Activity / Dialog / PopupWindow                                            │
│       ↓ addView()                                                           │
│  WindowManagerImpl → WindowManagerGlobal                                    │
│       ↓ new ViewRootImpl() + setView()                                      │
│  ViewRootImpl                                                               │
│    ├── performTraversals() → measure / layout / draw                        │
│    ├── WindowInputEventReceiver → InputChannel (client fd)                  │
│    └── mWindowSession (IWindowSession, Binder proxy)                        │
│              ↓ addToDisplayAsUser() / relayout()                            │
├──────────── Binder IPC ─────────────────────────────────────────────────────┤
│                          system_server 进程                                  │
│                                                                             │
│  Session (IWindowSession stub)                                              │
│       ↓                                                                     │
│  WindowManagerService                                                       │
│    ├── addWindow() → 创建 WindowState                                       │
│    ├── relayoutWindow() → createSurfaceLocked() → SurfaceControl            │
│    ├── performSurfacePlacement() → 计算所有窗口布局                           │
│    ├── updateFocusedWindowLocked() → InputMonitor.setInputFocusLw()         │
│    │                                      ↓                                 │
│    │                               InputMonitor                             │
│    │                                 ↓ updateInputWindows()                 │
│    │                           InputDispatcher.setInputWindows()            │
│    │                           InputDispatcher.setFocusedWindow()           │
│    ├── mGlobalLock (WindowManagerGlobalLock) ← WMS 全局锁                   │
│    └── WindowContainer 层级树:                                               │
│         RootWindowContainer                                                 │
│          └── DisplayContent                                                 │
│               ├── TaskDisplayArea                                           │
│               │    └── Task                                                 │
│               │         └── ActivityRecord                                  │
│               │              └── WindowState ← 一个窗口的核心抽象             │
│               ├── DisplayArea.Tokens (StatusBar, NavBar)                    │
│               └── ImeContainer                                              │
│                                                                             │
│  SurfaceControl (Binder proxy → SurfaceFlinger)                             │
│       ↓ SurfaceControl.Transaction                                          │
├──────────── Binder IPC ─────────────────────────────────────────────────────┤
│                          SurfaceFlinger 进程                                 │
│                                                                             │
│  Layer 树 (对应 SurfaceControl 层级)                                         │
│    ├── 每个 Layer 持有 BufferQueue / GraphicBuffer                           │
│    ├── 硬件合成 (HWC) 或 GPU 合成                                            │
│    └── 最终输出到 Display HAL → 屏幕                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 WMS 与 InputDispatcher 的焦点同步通道

WMS 与 Input 系统的交互是稳定性问题的高发区。焦点同步通过 `InputMonitor` 完成：

```
窗口添加/移除/焦点变化
       ↓
WMS.updateFocusedWindowLocked()
       ↓
DisplayContent.updateFocusedWindowLocked()
       ↓
InputMonitor.setInputFocusLw(WindowState newWindow)
       ↓
InputMonitor.updateInputWindowsLw(boolean force)
  → 遍历所有窗口，收集 InputWindowHandle 数组
  → 通过 SurfaceControl.Transaction 提交给 InputDispatcher
       ↓
InputDispatcher::setInputWindows()
InputDispatcher::setFocusedWindow()
       ↓
InputDispatcher 使用新的窗口列表进行事件路由
```

**稳定性关键点：** 这个链路上任何一步延迟，都会导致 InputDispatcher 使用过期的焦点/窗口信息。最常见的后果是：Activity 已经切换完成，但 InputDispatcher 的焦点还指向旧窗口，Key 事件发错目标，或者焦点为 null 导致 ANR。

### 3.3 各层职责与核心数据结构

| 层 | 核心职责 | 核心数据结构 | 所在进程 |
|----|---------|------------|---------|
| App 层 | 创建 View 树，发起 addView，执行 measure/layout/draw | `ViewRootImpl`, `WindowManager.LayoutParams`, `Surface` | App 进程 |
| WMS 层 | 窗口生命周期管理、Z-order 排列、焦点管理、布局计算 | `WindowState`, `WindowContainer` 层级树, `DisplayContent`, `SurfaceControl` | system_server |
| InputMonitor | 将窗口信息同步到 InputDispatcher，管理焦点窗口 | `InputWindowHandle`, `InputMonitor` | system_server |
| SurfaceFlinger | 图形缓冲区管理、硬件合成、帧提交 | `Layer`, `BufferQueue`, `GraphicBuffer` | surfaceflinger |

**核心数据结构详解：**

**WindowState** — WMS 中一个窗口的核心抽象：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java
class WindowState extends WindowContainer<WindowState> {
    final WindowManager.LayoutParams mAttrs;    // 窗口属性
    final IWindow mClient;                       // App 端的 Binder 回调
    final Session mSession;                      // 与 App 的会话
    InputChannel mInputChannel;                  // 输入通道
    SurfaceControl mSurfaceControl;              // Surface 控制句柄
    WindowStateAnimator mWinAnimator;            // 动画控制器
    boolean mHasSurface;                         // 是否已分配 Surface
    int mBaseLayer;                              // 基础层级（由 type 决定）
    int mSubLayer;                               // 子层级（sub-window 相对父窗口的偏移）
    // ... 200+ 字段
}
```

> **稳定性架构师视角：** `WindowState` 的生命周期是 WMS 稳定性的核心。如果 WindowState 在 App 进程已死后仍然存活（未被正确清理），会导致 Window Leaked 警告、Surface 泄漏、甚至 WMS 内部状态不一致。排查窗口泄漏时，`WindowState.mClient` 的 Binder 死亡通知（`DeathRecipient`）是关键线索。

**WindowContainer 层级树** — Android 10+ 的窗口组织模型：

```
RootWindowContainer
 └── DisplayContent (displayId=0)
      ├── TaskDisplayArea ("DefaultTaskDisplayArea")
      │    ├── Task (taskId=1, 包含 Launcher)
      │    │    └── ActivityRecord (com.android.launcher3/.Launcher)
      │    │         └── WindowState (TYPE_BASE_APPLICATION)
      │    └── Task (taskId=5, 包含当前 App)
      │         └── ActivityRecord (com.example.app/.MainActivity)
      │              ├── WindowState (TYPE_BASE_APPLICATION, 主窗口)
      │              └── WindowState (TYPE_APPLICATION, Dialog 窗口)
      ├── DisplayArea.Tokens ("StatusBar 容器")
      │    └── WindowToken
      │         └── WindowState (TYPE_STATUS_BAR)
      ├── DisplayArea.Tokens ("NavigationBar 容器")
      │    └── WindowToken
      │         └── WindowState (TYPE_NAVIGATION_BAR)
      └── ImeContainer
           └── WindowToken
                └── WindowState (TYPE_INPUT_METHOD)
```

> **稳定性架构师视角：** `WindowContainer` 层级树是 `dumpsys window containers` 输出的核心数据结构。排查窗口层级异常（如 Dialog 被 StatusBar 遮挡、IME 弹不出来）时，首先要通过 `dumpsys` 确认层级树的实际结构是否符合预期。

---

## 4. 一个 Window 的完整生命周期

一个 Window 从创建到销毁，要经历以下关键阶段。我们以 Activity 的主窗口为主线，追踪整个生命周期。

### 4.1 生命周期全景

```
App 进程                               system_server (WMS)              SurfaceFlinger
   │                                         │                              │
   │  (1) WindowManagerGlobal.addView()      │                              │
   │       → new ViewRootImpl()              │                              │
   │       → ViewRootImpl.setView()          │                              │
   │            ↓ Binder IPC                 │                              │
   │  ─────────────────────────────────────→ │                              │
   │                                    (2) Session.addToDisplayAsUser()    │
   │                                         → WMS.addWindow()             │
   │                                         → new WindowState()           │
   │                                    (3) WindowState.openInputChannel() │
   │                                         → InputChannel 注册到          │
   │                                            InputDispatcher            │
   │  ←───────────────────────────────────── │                              │
   │  (拿到 InputChannel client fd)          │                              │
   │                                         │                              │
   │  (4) requestLayout()                    │                              │
   │       → scheduleTraversals()            │                              │
   │            ↓ Binder IPC                 │                              │
   │  ─────────────────────────────────────→ │                              │
   │                                    (5) WMS.relayoutWindow()           │
   │                                         → createSurfaceLocked()       │
   │                                         │  ─────────────────────────→ │
   │                                         │  SurfaceControl.Transaction │
   │                                         │  → 创建 Layer               │
   │                                         │  ←──────────────────────── │
   │  ←───────────────────────────────────── │                              │
   │  (拿到 Surface 引用)                     │                              │
   │                                         │                              │
   │  (6) performTraversals()                │                              │
   │       → measure → layout → draw         │                              │
   │       → Surface.lockCanvas()            │                              │
   │       → Canvas 绘制                     │                              │
   │       → Surface.unlockCanvasAndPost()   │                              │
   │                                         │                              │
   │                                    (7) performSurfacePlacement()      │
   │                                         → 计算所有窗口的最终位置/大小   │
   │                                         │                              │
   │                                    (8) updateFocusedWindowLocked()    │
   │                                         → InputMonitor 同步焦点       │
   │                                         → InputDispatcher 更新        │
   │                                         │                              │
   │  (9) Activity.onDestroy()               │                              │
   │       → WindowManagerGlobal.removeView() │                              │
   │            ↓ Binder IPC                 │                              │
   │  ─────────────────────────────────────→ │                              │
   │                                   (10) WMS.removeWindow()             │
   │                                         → destroySurface()            │
   │                                         → closeInputChannel()         │
   │                                         → 从层级树移除 WindowState    │
   │                                         │  ─────────────────────────→ │
   │                                         │  销毁 Layer                 │
   │                                         │  ←──────────────────────── │
```

### 4.2 阶段一：addView — App 端发起窗口创建

当 `Activity.handleResumeActivity()` 执行到 `wm.addView(decor, l)` 时，窗口创建的旅程开始。

以下代码展示了 `WindowManagerGlobal` 如何创建 `ViewRootImpl` 并调用 `setView()`：

```java
// frameworks/base/core/java/android/view/WindowManagerGlobal.java
public void addView(View view, ViewGroup.LayoutParams params,
        Display display, Window parentWindow, int userId) {
    final WindowManager.LayoutParams wparams = (WindowManager.LayoutParams) params;

    ViewRootImpl root;
    synchronized (mLock) {
        // 创建 ViewRootImpl —— 每个窗口一个
        root = new ViewRootImpl(view.getContext(), display);
        view.setLayoutParams(wparams);

        // 记录到全局列表
        mViews.add(view);
        mRoots.add(root);
        mParams.add(wparams);

        // 关键调用：将 View 与 ViewRootImpl 绑定，并发起与 WMS 的通信
        root.setView(view, wparams, panelParentView, userId);
    }
}
```

> **稳定性架构师视角：** `WindowManagerGlobal` 维护了三个并行数组 `mViews`/`mRoots`/`mParams`，它们记录了当前进程的所有活跃窗口。如果 `removeView()` 没有正确调用（如 Dialog 在 Activity 销毁后未 dismiss），这些列表中的残留项就是 `WindowLeaked` 异常的来源。`ActivityThread.handleDestroyActivity()` 中有检测逻辑，发现残留窗口时会打印 `"Activity has leaked window"` 警告。

`ViewRootImpl.setView()` 是 App 端的核心入口，它做了三件关键事：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
public void setView(View view, WindowManager.LayoutParams attrs,
        View panelParentView, int userId) {
    synchronized (this) {
        if (mView == null) {
            mView = view;

            // 1. 请求首次布局
            requestLayout();

            // 2. 创建 InputChannel 并通过 Binder 调用 WMS.addWindow()
            InputChannel inputChannel = new InputChannel();
            res = mWindowSession.addToDisplayAsUser(mWindow, mWindowAttributes,
                    getHostVisibility(), mDisplay.getDisplayId(),
                    userId, mInsetsController.getRequestedVisibilities(),
                    inputChannel, mTempInsets, mTempControls);

            // 3. 注册 InputChannel 到主线程 Looper
            if (inputChannel != null) {
                mInputEventReceiver = new WindowInputEventReceiver(
                        inputChannel, Looper.myLooper());
            }
        }
    }
}
```

> **稳定性架构师视角：** `mWindowSession.addToDisplayAsUser()` 是一次**同步 Binder 调用**，App 主线程会阻塞直到 WMS 返回。如果此时 WMS 的 `mGlobalLock` 被其他操作长时间持有（如窗口动画计算、Configuration 变更），App 主线程会被阻塞，延迟 Activity 的启动。这是冷启动慢的常见原因之一。

### 4.3 阶段二：addWindow — WMS 创建 WindowState

Binder 调用到达 `system_server` 后，经过 `Session.addToDisplayAsUser()` 转发到 WMS：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
public int addWindow(Session session, IWindow client, LayoutParams attrs,
        int viewVisibility, int displayId, int requestUserId,
        InsetsVisibilities requestedVisibilities, InputChannel outInputChannel,
        InsetsState outInsetsState, InsetsSourceControl[] outActiveControls) {

    synchronized (mGlobalLock) {
        // 1. 权限检查：验证窗口类型是否允许创建
        int res = mPolicy.checkAddPermission(attrs.type, isRoundedCornerOverlay,
                attrs.packageName, appOp);
        if (res != ADD_OKAY) {
            return res;  // 返回错误码，如 ADD_PERMISSION_DENIED
        }

        // 2. 查找 DisplayContent
        final DisplayContent displayContent = getDisplayContentOrCreate(displayId, attrs.token);

        // 3. Token 校验：Application 窗口必须有合法的 ActivityRecord token
        WindowToken token = displayContent.getWindowToken(attrs.token);
        if (token == null) {
            if (attrs.type >= FIRST_APPLICATION_WINDOW
                    && attrs.type <= LAST_APPLICATION_WINDOW) {
                // Application 窗口没有合法 token → BadTokenException
                return WindowManagerGlobal.ADD_BAD_APP_TOKEN;
            }
            // 非 Application 窗口可以自动创建 token
            token = new WindowToken.Builder(this, attrs.token, attrs.type)
                    .setDisplayContent(displayContent).build();
        }

        // 4. 创建 WindowState
        final WindowState win = new WindowState(this, session, client, token,
                parentWindow, appOp, attrs, viewVisibility, session.mUid,
                userId, session.mCanAddInternalSystemWindow);

        // 5. 打开 InputChannel
        win.openInputChannel(outInputChannel);

        // 6. 将 WindowState 插入 WindowContainer 层级树
        win.mToken.addWindow(win);

        // 7. 触发焦点更新
        boolean focusChanged = updateFocusedWindowLocked(UPDATE_FOCUS_WILL_ASSIGN_LAYERS, false);

        // 8. 分配层级
        displayContent.assignWindowLayers(false);
    }
    return res;
}
```

> **稳定性架构师视角：** `addWindow()` 全程持有 `mGlobalLock`，这是一把全局互斥锁。`mGlobalLock` 是 WMS 中竞争最激烈的锁——所有窗口操作（add/remove/relayout/focus/animation）都需要持有它。当 `addWindow()` 执行时间过长（如 `assignWindowLayers` 在窗口数量极多时变慢），会阻塞其他线程的窗口操作，甚至触发 Watchdog 超时。

**Token 校验** 是 `BadTokenException` 的源头。第 3 步中，如果 App 窗口的 `attrs.token` 不对应任何已注册的 `ActivityRecord`，WMS 返回 `ADD_BAD_APP_TOKEN`，ViewRootImpl 收到后抛出：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
// setView() 中检查 addWindow 的返回值
switch (res) {
    case WindowManagerGlobal.ADD_BAD_APP_TOKEN:
    case WindowManagerGlobal.ADD_BAD_SUBWINDOW_TOKEN:
        throw new WindowManager.BadTokenException(
                "Unable to add window -- token " + attrs.token
                + " is not valid; is your activity running?");
}
```

### 4.4 阶段三：openInputChannel — 注册输入通道

WindowState 创建后立即打开 InputChannel，使窗口能够接收输入事件：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java
void openInputChannel(InputChannel outInputChannel) {
    String name = getName();
    // 创建 InputChannel 对（server + client）
    InputChannel[] inputChannels = InputChannel.openInputChannelPair(name);
    mInputChannel = inputChannels[0];  // server 端留在 system_server
    // client 端通过 outInputChannel 传回 App 进程
    inputChannels[1].transferTo(outInputChannel);

    // 将 server 端注册到 InputDispatcher
    mWmService.mInputManager.registerInputChannel(mInputChannel);
}
```

> **稳定性架构师视角：** InputChannel 是基于 `socketpair` 的双向管道。如果 `openInputChannel()` 失败（如 fd 资源耗尽），窗口无法接收任何输入事件。更隐蔽的问题是：如果 `closeInputChannel()` 没有及时调用（如 WindowState 清理异常），InputDispatcher 侧的 Connection 会残留，可能导致事件发送到已不存在的窗口。

### 4.5 阶段四：relayoutWindow — 创建 Surface

App 端 `ViewRootImpl.performTraversals()` 在首次布局时调用 `relayoutWindow()`，WMS 在此阶段为窗口分配 Surface：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
public int relayoutWindow(Session session, IWindow client,
        LayoutParams attrs, int requestedWidth, int requestedHeight,
        int viewVisibility, int flags, int seq, int lastSyncSeqId,
        ClientWindowFrames outFrames, MergedConfiguration mergedConfiguration,
        SurfaceControl outSurfaceControl, InsetsState outInsetsState, ...) {

    synchronized (mGlobalLock) {
        final WindowState win = windowForClientLocked(session, client, false);

        // 如果窗口可见且尚未创建 Surface，创建之
        if (viewVisibility == View.VISIBLE) {
            result = createSurfaceControl(outSurfaceControl, result, win, winAnimator);
        }

        // 执行布局计算
        performSurfacePlacementNoTrace();

        // 填充输出参数：窗口帧、Insets、Configuration
        win.fillClientWindowFramesAndConfiguration(outFrames, mergedConfiguration, ...);
    }
}
```

`createSurfaceControl` 最终调用到 `WindowStateAnimator.createSurfaceLocked()`：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java
WindowSurfaceController createSurfaceLocked() {
    final WindowState w = mWin;

    // 通过 SurfaceControl.Builder 创建 Surface
    mSurfaceController = new WindowSurfaceController(w.mAttrs.getTitle().toString(),
            width, height, format, flags, this, w.getWindowingMode());

    w.mHasSurface = true;
    // ...
    return mSurfaceController;
}
```

> **稳定性架构师视角：** Surface 的创建是重量级操作，涉及 SurfaceFlinger 侧的 Layer 分配和 GraphicBuffer 预分配。`createSurfaceLocked()` 执行时间在 3-10ms 级别（取决于 GPU 驱动和系统负载）。如果这个过程失败（如 SurfaceFlinger 无响应、fd 耗尽），窗口将没有 Surface → 屏幕上该窗口区域黑屏。`w.mHasSurface` 标志位是排查黑屏问题的关键检查点。

### 4.6 阶段五：performSurfacePlacement — 全局布局

WMS 的布局计算不是针对单个窗口，而是对当前 Display 上所有窗口进行全局布局：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowSurfacePlacer.java
final void performSurfacePlacementNoTrace() {
    // 循环执行布局，直到没有窗口需要重新布局
    // 最多循环 6 次防止无限循环
    int loopCount = 6;
    do {
        mTraversalScheduled = false;
        performSurfacePlacementLoop();
        loopCount--;
    } while (mTraversalScheduled && loopCount > 0);
}
```

这个过程包括：
1. 计算每个窗口的最终位置、大小（考虑 Insets、SystemBar、IME）
2. 确定每个窗口的可见性
3. 分配 Z-order 层级
4. 通过 `SurfaceControl.Transaction` 将变化提交到 SurfaceFlinger

### 4.7 阶段六：performTraversals — App 端绘制

App 端收到 Surface 后，`ViewRootImpl.performTraversals()` 执行经典的 measure → layout → draw 三步：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
private void performTraversals() {
    // 1. relayoutWindow() — 获取 Surface（如果是首次）
    relayoutResult = relayoutWindow(params, viewVisibility, insetsPending);

    // 2. performMeasure() — 测量 View 树
    performMeasure(childWidthMeasureSpec, childHeightMeasureSpec);

    // 3. performLayout() — 布局 View 树
    performLayout(lp, mWidth, mHeight);

    // 4. performDraw() — 绘制 View 树到 Surface
    performDraw();
}
```

> **稳定性架构师视角：** `performTraversals()` 是 App 主线程中最重要的方法之一。它在一帧内完成窗口大小协商、View 树测量布局、绘制三大操作。如果 `performTraversals()` 耗时超过 16ms（60Hz 下），就会掉帧。如果严重超时（超过 5 秒），叠加用户触摸输入，就会触发 Input ANR。Systrace 中搜索 `performTraversals` 是分析 UI 卡顿的第一步。

### 4.8 阶段七：updateFocusedWindowLocked — 焦点更新

窗口创建和可见性变化后，WMS 更新焦点窗口：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
boolean updateFocusedWindowLocked(int mode, boolean updateInputWindows) {
    // 对每个 Display 计算焦点窗口
    boolean changed = mRoot.updateFocusedWindowLocked(mode, updateInputWindows);
    if (changed) {
        // 通知 InputMonitor 更新焦点
        mInputMonitor.setInputFocusLw(mRoot.getTopFocusedDisplayContent().mCurrentFocus,
                updateInputWindows);
    }
    return changed;
}
```

焦点窗口的计算逻辑在 `DisplayContent.findFocusedWindow()` 中，核心算法是从窗口树自顶向下遍历，找到第一个可聚焦（`canReceiveKeys()` 返回 true）的窗口：

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java
WindowState findFocusedWindow() {
    // 自顶向下遍历 WindowContainer 树
    // 找到第一个 canReceiveKeys() == true 的 WindowState
    mTmpWindow = null;
    forAllWindows(w -> {
        if (w.canReceiveKeys()) {
            mTmpWindow = w;
            return true;  // 找到了，停止遍历
        }
        return false;
    }, true /* traverseTopToBottom */);
    return mTmpWindow;
}
```

> **稳定性架构师视角：** 焦点丢失是导致 ANR 的常见原因。`canReceiveKeys()` 返回 false 的条件包括：窗口不可见（`isVisibleLw()` == false）、窗口设置了 `FLAG_NOT_FOCUSABLE`、窗口的 Activity 正在 finishing 等。排查焦点异常时，`dumpsys window` 中的 `mCurrentFocus` 和 `mFocusedApp` 字段是第一排查入口。

### 4.9 阶段八：removeWindow — 窗口销毁

当 Activity 销毁时，窗口的清理流程从 App 端发起：

```java
// frameworks/base/core/java/android/view/WindowManagerGlobal.java
void removeView(View view, boolean immediate) {
    synchronized (mLock) {
        int index = findViewLocked(view, true);
        View curView = mRoots.get(index).getView();
        removeViewLocked(index, immediate);
    }
}

// 最终调用到 ViewRootImpl.die()
void removeViewLocked(int index, boolean immediate) {
    ViewRootImpl root = mRoots.get(index);
    root.die(immediate);
}
```

App 端 `ViewRootImpl.doDie()` 通过 Binder 调用 WMS 的 `removeWindow()`：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
void removeWindow(Session session, IWindow client) {
    synchronized (mGlobalLock) {
        WindowState win = windowForClientLocked(session, client, false);
        if (win != null) {
            win.removeIfPossible();
        }
    }
}

// WindowState.removeIfPossible() 最终执行：
void removeImmediately() {
    // 1. 关闭 InputChannel
    if (mInputChannel != null) {
        mWmService.mInputManager.unregisterInputChannel(mInputChannel);
        mInputChannel.dispose();
        mInputChannel = null;
    }

    // 2. 销毁 Surface
    destroySurface(false, false);

    // 3. 从 WindowContainer 层级树移除
    // ... WindowToken 清理 ...
}
```

> **稳定性架构师视角：** `removeWindow()` 的异常处理至关重要。如果 App 进程崩溃（被 LMK 杀死或 Crash），`removeWindow()` 不会被正常调用。此时 WMS 依赖 `WindowState.mClient` 的 Binder `DeathRecipient` 回调来清理残留窗口。如果 DeathRecipient 回调延迟或遗漏，就会出现"僵尸窗口"——WindowState 存在但 App 已死，Surface 和 InputChannel 泄漏。

### 4.10 生命周期时序总结

```
App 主线程                           WMS (mGlobalLock 内)             InputDispatcher
    │                                      │                              │
    │ ① addView()                          │                              │
    │  → new ViewRootImpl()                │                              │
    │  → setView()                         │                              │
    │     ↓ Binder                         │                              │
    │ ──────────────────────────────→  ② addWindow()                     │
    │                                   → new WindowState()               │
    │                               ③ openInputChannel()                  │
    │                                   → registerInputChannel() ────→    │ InputChannel 注册
    │ ←──────────────────────────────      │                              │
    │                                      │                              │
    │ ④ requestLayout()                    │                              │
    │  → scheduleTraversals()              │                              │
    │     ↓ Binder                         │                              │
    │ ──────────────────────────────→  ⑤ relayoutWindow()                │
    │                                   → createSurfaceLocked()           │
    │                               ⑥ performSurfacePlacement()          │
    │ ←──────────────────────────────      │                              │
    │                                      │                              │
    │ ⑦ performTraversals()                │                              │
    │  → measure → layout → draw           │                              │
    │                                 ⑧ updateFocusedWindowLocked()      │
    │                                   → InputMonitor.setInputFocus()   │
    │                                      │ ──────────────────────→      │ 焦点更新
    │                                      │                              │
    │ ... (窗口正常使用中) ...              │                              │
    │                                      │                              │
    │ ⑨ removeView()                       │                              │
    │     ↓ Binder                         │                              │
    │ ──────────────────────────────→  ⑩ removeWindow()                  │
    │                                   → closeInputChannel() ────────→   │ InputChannel 注销
    │                                   → destroySurface()                │
    │                                   → 从层级树移除                     │
```

---

## 5. 核心进程与线程模型

### 5.1 system_server 中的 WMS 线程模型

WMS 的代码主要运行在 `system_server` 的以下线程上：

```
system_server 进程
├── main (主线程, "android.display")
│     ├── WindowManagerService (所有窗口管理操作)
│     ├── DisplayPolicy (系统栏策略)
│     ├── InputMonitor (窗口信息同步到 InputDispatcher)
│     └── 注意: WMS 主线程与 AMS 共享 "android.display" Handler
│
├── "android.anim" (AnimationThread)
│     └── 窗口动画相关操作
│         过渡动画 tick、WindowAnimator.animate()
│
├── "android.anim.lf" (SurfaceAnimationThread)
│     └── SurfaceControl 级别的动画
│         SurfaceAnimationRunner 执行 Leash 动画
│
├── InputReader (线程)
│     └── EventHub::getEvents() → InputReader::loopOnce()
│
├── InputDispatcher (线程)
│     └── dispatchOnce() → 事件路由 + ANR 检测
│
└── Binder 线程池
      └── App 的 addWindow/relayout/removeWindow 调用入口
          → 获取 mGlobalLock 后转到主线程逻辑
```

**关键点：** App 通过 Binder 调用 `addWindow()` / `relayoutWindow()` 时，调用直接在 Binder 线程上执行（不切换到主线程），但需要获取 `mGlobalLock`。这意味着多个 App 同时发起窗口操作时，它们的 Binder 线程会竞争同一把锁。

### 5.2 App 进程中的窗口管理

App 进程中，窗口管理相关的操作全部在主线程执行：

```
App 进程 (主线程)
└── Looper::pollOnce()
      ├── Handler 消息处理
      │     ├── ActivityThread.H: RESUME_ACTIVITY → addView
      │     ├── ActivityThread.H: DESTROY_ACTIVITY → removeView
      │     └── ViewRootImpl.mHandler: MSG_RESIZED → relayoutWindow
      │
      ├── InputChannel fd 可读
      │     → WindowInputEventReceiver.onInputEvent()
      │     → ViewRootImpl → InputStage → View 树分发
      │
      ├── Choreographer VSYNC 回调
      │     → CALLBACK_INPUT (输入事件合成)
      │     → CALLBACK_ANIMATION (属性动画)
      │     → CALLBACK_TRAVERSAL (performTraversals)
      │
      └── Surface 回调
            → SurfaceHolder.Callback (SurfaceView 专用)
```

**Choreographer 与窗口的协作：** `performTraversals()` 是通过 Choreographer 的 `CALLBACK_TRAVERSAL` 调度的。当 `ViewRootImpl.requestLayout()` 被调用时，它通过 `scheduleTraversals()` 向 Choreographer 注册一个 traversal 回调，等待下一个 VSYNC 信号到来时执行。这保证了布局和绘制与屏幕刷新同步。

### 5.3 SurfaceFlinger 中的线程模型

SurfaceFlinger 是独立进程，负责将所有窗口的 Surface 合成为最终的屏幕画面：

```
surfaceflinger 进程
├── main (主线程)
│     ├── 接收来自 App / WMS 的 SurfaceControl.Transaction
│     ├── 执行合成 (composite): 遍历 Layer 树 → HWC 或 GPU 合成
│     └── 提交帧到 Display HAL
│
├── EventThread (app)
│     └── 为 App 分发 VSYNC-app 信号（触发 Choreographer）
│
├── EventThread (sf)
│     └── 为 SurfaceFlinger 自身分发 VSYNC-sf 信号（触发合成）
│
└── Binder 线程池
      └── 处理 createSurface / destroySurface / Transaction 等调用
```

### 5.4 线程交互全景

```
App 主线程           Binder 线程         WMS (mGlobalLock)       InputDispatcher      SurfaceFlinger
    │                    │                     │                      │                    │
    │ ─setView()────→    │                     │                      │                    │
    │                    │ ──addWindow()────→   │                      │                    │
    │                    │                     │ ──registerInput()──→  │                    │
    │                    │ ←─────────────────   │                      │                    │
    │ ←──────────────    │                     │                      │                    │
    │                    │                     │                      │                    │
    │ ─relayout()────→   │                     │                      │                    │
    │                    │ ──relayoutWindow()─→ │                      │                    │
    │                    │                     │ ──createSurface()─────────────────────→   │
    │                    │                     │ ←──────────────────────────────────────   │
    │                    │ ←─────────────────   │                      │                    │
    │ ←──────────────    │                     │                      │                    │
    │                    │                     │                      │                    │
    │ ─draw()──→ Surface.lockCanvas()          │                      │                    │
    │            Canvas 绘制                    │                      │                    │
    │            unlockCanvasAndPost() ──────────────────────────────────────────────→     │
    │                                          │                      │              合成 → 显示
```

### 5.5 线程与稳定性

| 线程                         | 阻塞原因                                    | 稳定性影响                                                |
| -------------------------- | --------------------------------------- | ---------------------------------------------------- |
| WMS Binder 线程              | 等待 `mGlobalLock`（被动画/布局/其他窗口操作持有）       | App 的 addView/relayout 调用阻塞 → Activity 启动慢 → 冷启动 ANR |
| WMS 主线程（"android.display"） | `performSurfacePlacement` 计算量大、窗口数量多    | Watchdog 超时 → system_server 重启                       |
| AnimationThread            | 动画帧计算耗时、SurfaceControl Transaction 提交慢  | 窗口转场卡顿、动画掉帧                                          |
| App 主线程                    | performTraversals 耗时、同步 Binder 调用、IO 操作 | finishInputEvent 延迟 → Input ANR                      |
| InputDispatcher 线程         | `mLock` 被窗口更新操作占用                       | 事件分发延迟 → 触摸不跟手                                       |
| SurfaceFlinger 主线程         | GPU 合成慢、Layer 数量过多、HWC 驱动超时             | 全局掉帧、SurfaceFlinger 超时触发 Watchdog                    |

---

## 6. 与其他模块的交互全景

### 6.1 AMS（ActivityManagerService）— Activity 生命周期与焦点应用

AMS 是 WMS 最重要的合作伙伴。Activity 的生命周期变化直接驱动 Window 的创建和销毁：

```
AMS                              WMS                           InputDispatcher
 │                                │                                │
 │ startActivity()                │                                │
 │  → ActivityRecord.create()     │                                │
 │  → setFocusedActivity()        │                                │
 │     ↓                          │                                │
 │  setFocusedApp(ActivityRecord) │                                │
 │  ───────────────────────────→  │                                │
 │                                │ mFocusedApp = activityRecord   │
 │                                │  → setFocusedApplication() ──→ │
 │                                │                                │ FocusedApplication 更新
 │                                │                                │ (开始等待 FocusedWindow)
 │                                │                                │
 │ resumeActivity()               │                                │
 │  → App.handleResumeActivity()  │                                │
 │     → addView() → addWindow()  │                                │
 │     ───────────────────────→   │ addWindow()                    │
 │                                │  → openInputChannel()          │
 │                                │  → updateFocusedWindowLocked() │
 │                                │     → setInputFocus() ───────→ │ FocusedWindow 更新
 │                                │                                │ (可以开始分发 Key 事件)
```

**稳定性关键点：** AMS 设置 `FocusedApplication` 和 WMS 设置 `FocusedWindow` 之间有时间差。如果 Activity 启动慢（Application.onCreate 耗时、首帧绘制慢），这个时间差内 InputDispatcher 有 `FocusedApplication` 但没有 `FocusedWindow`，用户触摸会触发 "Waiting because no window has focus" ANR。这个时间差就是 TTID（Time To Initial Display）的核心组成部分。

### 6.2 IMS / InputDispatcher — 焦点同步与 InputChannel 注册

WMS 与 Input 系统的交互通过两个关键路径实现：

**路径一：InputChannel 注册/注销**

```
Window 创建时:
  WMS.addWindow() → WindowState.openInputChannel()
    → InputManagerService.registerInputChannel(inputChannel)
      → NativeInputManager → InputDispatcher::registerInputChannel()
        → 创建 Connection 对象，关联 InputChannel

Window 销毁时:
  WMS.removeWindow() → WindowState.closeInputChannel()
    → InputManagerService.unregisterInputChannel(inputChannel)
      → InputDispatcher::unregisterInputChannel()
        → 移除 Connection，清理 waitQueue
```

**路径二：窗口列表与焦点同步（通过 InputMonitor）**

```java
// frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java
void updateInputWindowsLw(boolean force) {
    // 收集所有窗口的 InputWindowHandle
    // 包括：位置、大小、flags、InputChannel、可见性、touchableRegion
    mDisplayContent.forAllWindows(this::populateInputWindowHandle,
            true /* traverseTopToBottom */);

    // 通过 SurfaceControl.Transaction 提交窗口信息
    // → 最终到达 InputDispatcher::setInputWindows()
    mDisplayContent.getInputMonitor().setUpdateInputWindowsNeededLw();
}
```

> **稳定性架构师视角：** InputMonitor 的更新频率直接影响 Input 系统的正确性。如果窗口位置变化（如窗口动画）但 InputMonitor 没有及时更新，InputDispatcher 用旧的窗口区域做 Hit Test，触摸事件可能发给错误窗口或被丢弃。Android 14 中，InputMonitor 的更新被绑定到 `SurfaceControl.Transaction`，保证窗口位置和输入区域原子性更新。

### 6.3 SurfaceFlinger — Surface 创建与合成

WMS 通过 `SurfaceControl` API 与 SurfaceFlinger 交互：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowSurfaceController.java
WindowSurfaceController(String name, int w, int h, int format,
        int flags, WindowStateAnimator animator, int windowingMode) {
    // 创建 SurfaceControl（Binder 代理 → SurfaceFlinger）
    mSurfaceControl = animator.mWin.makeSurface()
            .setName(name)
            .setBufferSize(w, h)
            .setFormat(format)
            .setFlags(flags)
            .setCallsite("WindowSurfaceController")
            .build();
}
```

SurfaceFlinger 侧收到请求后创建对应的 `Layer` 对象。WMS 通过 `SurfaceControl.Transaction` 批量提交窗口变化（位置、大小、可见性、Z-order）：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java
void prepareSurfaces() {
    // 构建 SurfaceControl.Transaction
    SurfaceControl.Transaction t = getSyncTransaction();
    if (isVisibleRequested()) {
        t.show(mSurfaceControl);
        t.setPosition(mSurfaceControl, mWindowFrames.mFrame.left, mWindowFrames.mFrame.top);
        t.setBufferSize(mSurfaceControl, mWindowFrames.mFrame.width(),
                mWindowFrames.mFrame.height());
    } else {
        t.hide(mSurfaceControl);
    }
    // Transaction 最终在 performSurfacePlacement 结束时 apply()
}
```

> **稳定性架构师视角：** Surface 泄漏是 WMS 稳定性的高频问题。当 WindowState 被移除但 SurfaceControl 没有正确 release 时，SurfaceFlinger 侧的 Layer 和 GraphicBuffer 残留，持续占用显存。排查 Surface 泄漏的关键命令：`dumpsys SurfaceFlinger --list` 列出所有 Layer，`dumpsys meminfo surfaceflinger` 查看显存占用。

### 6.4 DisplayManagerService — 多屏管理

Android 支持多 Display（外接显示器、虚拟 Display）。WMS 通过 `DisplayContent` 为每个 Display 维护独立的窗口层级树：

```
RootWindowContainer
 ├── DisplayContent (displayId=0, 主屏)
 │    └── TaskDisplayArea → Task → ActivityRecord → WindowState
 ├── DisplayContent (displayId=1, 外接屏)
 │    └── TaskDisplayArea → Task → ActivityRecord → WindowState
 └── DisplayContent (displayId=2, 虚拟屏)
      └── TaskDisplayArea → Task → ActivityRecord → WindowState
```

`DisplayManagerService` 负责 Display 的热插拔检测和属性管理（分辨率、刷新率、DPI），WMS 负责在每个 Display 上管理窗口。当 Display 配置变化（如旋转、分辨率切换）时，DMS 通知 WMS → WMS 触发 Configuration 变更 → 所有相关窗口重新布局。

### 6.5 Choreographer — VSYNC 对齐

Choreographer 是 App 端渲染的节拍器。窗口的布局（`performTraversals`）和绘制通过 Choreographer 与 VSYNC 同步：

```
VSYNC-app 信号到达
  → Choreographer.doFrame()
    → CALLBACK_INPUT (处理输入事件)
    → CALLBACK_ANIMATION (执行动画)
    → CALLBACK_TRAVERSAL
      → ViewRootImpl.doTraversal()
        → performTraversals()
          → relayoutWindow() (如需要)
          → measure → layout → draw
    → CALLBACK_COMMIT (提交帧)
```

> **稳定性架构师视角：** `performTraversals()` 的执行时间必须在一个 VSYNC 周期内完成（60Hz = 16.6ms，120Hz = 8.3ms）。如果 `relayoutWindow()` 因为 WMS 锁竞争而阻塞（如等待 `mGlobalLock` 10ms），叠加 measure/layout/draw 的时间，很容易超过 16.6ms 导致掉帧。在 Systrace 中，这表现为 `performTraversals` 块跨越了 VSYNC 边界。

### 6.6 各模块交互风险汇总

| 交互路径 | 正常耗时 | 风险场景 | 稳定性后果 |
|---------|---------|---------|-----------|
| WMS ↔ AMS（FocusedApp 设置） | <1ms | Activity 启动慢，FocusedApp 设置后长时间无 FocusedWindow | ANR（no focused window） |
| WMS → InputDispatcher（焦点同步） | 1-3ms | WMS 锁竞争导致同步延迟 | Key 事件发错窗口或 ANR |
| WMS → SurfaceFlinger（Surface 创建） | 3-10ms | SurfaceFlinger 无响应、fd 耗尽 | 窗口黑屏 |
| App → WMS（addWindow Binder） | 1-5ms | mGlobalLock 被长时间持有 | App 主线程阻塞 → 启动慢 |
| App → WMS（relayout Binder） | 2-8ms | performSurfacePlacement 耗时 | 首帧延迟 → TTID 增大 |
| Choreographer → performTraversals | <16ms | 布局复杂、Binder 阻塞 | 掉帧、卡顿 |

---

## 7. 核心源码目录导航

排查 Window 相关问题时，快速定位到正确的源码文件至关重要。以下是 AOSP Android 14 中 Window 系统的核心目录导航：

| 目录                                                          | 职责                | 关键文件                                                             |
| ----------------------------------------------------------- | ----------------- | ---------------------------------------------------------------- |
| `frameworks/base/services/core/java/com/android/server/wm/` | WMS 核心实现          | `WindowManagerService.java` — WMS 主入口，窗口管理核心逻辑                   |
|                                                             |                   | `WindowState.java` — 单个窗口的核心抽象（200+ 字段）                          |
|                                                             |                   | `WindowContainer.java` — 窗口容器层级基类                                |
|                                                             |                   | `DisplayContent.java` — 单个 Display 的窗口管理                         |
|                                                             |                   | `DisplayPolicy.java` — SystemBar/IME 策略管理（替代 PhoneWindowManager） |
|                                                             |                   | `InputMonitor.java` — WMS→InputDispatcher 窗口信息同步                 |
|                                                             |                   | `WindowSurfacePlacer.java` — 全局布局计算协调器                           |
|                                                             |                   | `WindowStateAnimator.java` — 窗口动画与 Surface 创建                    |
|                                                             |                   | `WindowToken.java` — 窗口 Token 管理                                 |
|                                                             |                   | `Task.java` — 任务栈管理                                              |
|                                                             |                   | `ActivityRecord.java` — Activity 在 WMS 中的表示                      |
|                                                             |                   | `RootWindowContainer.java` — 窗口容器树根节点                            |
|                                                             |                   | `TaskDisplayArea.java` — Task 的 Display 区域                       |
|                                                             |                   | `Session.java` — App ↔ WMS 的 Binder 会话                           |
| `frameworks/base/core/java/android/view/`                   | App 端窗口 API       | `ViewRootImpl.java` — App 端窗口管理核心（setView/performTraversals）     |
|                                                             |                   | `WindowManagerGlobal.java` — 进程级窗口管理（addView/removeView）         |
|                                                             |                   | `WindowManagerImpl.java` — 上下文级 WindowManager 实现                 |
|                                                             |                   | `Window.java` — PhoneWindow 的抽象基类                                |
|                                                             |                   | `SurfaceControl.java` — Surface 操作的 Java 封装                      |
|                                                             |                   | `Surface.java` — 图形缓冲区的 Java 封装                                  |
|                                                             |                   | `InputChannel.java` — 输入通道的 Java 封装                              |
| `frameworks/base/core/java/com/android/internal/policy/`    | 窗口策略              | `PhoneWindow.java` — Activity 的默认 Window 实现                      |
|                                                             |                   | `DecorView.java` — 顶层 DecorView                                  |
| `frameworks/native/libs/gui/`                               | Surface Native 实现 | `SurfaceControl.cpp` — SurfaceControl 的 Native 实现                |
|                                                             |                   | `Surface.cpp` — Surface 的 Native 实现                              |
|                                                             |                   | `BufferQueue.cpp` — 图形缓冲区队列                                      |
| `frameworks/native/services/surfaceflinger/`                | SurfaceFlinger    | `SurfaceFlinger.cpp` — 合成引擎                                      |
|                                                             |                   | `Layer.cpp` — 对应一个 SurfaceControl                                |
| `frameworks/native/services/inputflinger/dispatcher/`       | InputDispatcher   | `InputDispatcher.cpp` — 事件分发与焦点管理                                |

**排查技巧速查：**

| 问题类型              | 首要排查目录/文件                                                 |
| ----------------- | --------------------------------------------------------- |
| BadTokenException | `WindowManagerService.java` → `addWindow()` 中的 token 校验   |
| WindowLeaked      | `WindowManagerGlobal.java` → `removeView()` 是否调用          |
| 窗口黑屏              | `WindowStateAnimator.java` → `createSurfaceLocked()` 是否成功 |
| 焦点丢失 → ANR        | `InputMonitor.java` → `updateInputWindowsLw()` 的时序        |
| WMS Watchdog      | `WindowManagerService.java` → `mGlobalLock` 竞争分析          |
| 窗口层级异常            | `DisplayContent.java` → `assignWindowLayers()` 的层级计算      |
| IME 遮挡/不弹出        | `DisplayPolicy.java` → `layoutWindowLw()` 的 IME 处理        |
|                   |                                                           |

---

## 8. 稳定性总览：Window 系统的风险全景

### 8.1 风险全景图

| 风险类型 | 描述 | 典型占比 | 深入文章 |
|---------|------|---------|---------|
| **BadTokenException** | addWindow 时 token 无效（Activity 已 finish 但仍调用 Dialog.show） | Java Crash 中占比 5-10% | [02-Window 的创建与添加](02-Window的创建与添加.md) |
| **WindowLeaked** | Activity 销毁时未 dismiss 的 Dialog/PopupWindow，WindowState 残留 | 内存泄漏隐患 | [02-Window 的创建与添加](02-Window的创建与添加.md) |
| **黑屏** | Surface 创建失败或时序异常（屏幕旋转/Configuration 变更/App 切换） | 用户投诉高频项 | [05-Surface 与 SurfaceFlinger](05-Surface与SurfaceFlinger.md) |
| **焦点丢失 → ANR** | Activity 启动慢导致 FocusedWindow 为 null，InputDispatcher 5 秒超时 | 占 Input ANR 的 30%+ | [07-WMS 与 Input 焦点管理](07-WMS与Input焦点管理.md) |
| **WMS 锁竞争 → Watchdog** | mGlobalLock 被长时间持有（动画/布局/窗口数量多），Watchdog 检测到 60 秒未释放 | system_server 重启的重要原因 | [10-WMS 锁与 Watchdog](10-WMS锁与Watchdog.md) |
| **Surface 泄漏** | WindowState 清理异常导致 SurfaceControl 未 release，显存持续增长 | OOM / SurfaceFlinger 崩溃 | [05-Surface 与 SurfaceFlinger](05-Surface与SurfaceFlinger.md) |
| **窗口动画卡顿** | 转场动画帧率低、动画期间 Surface 状态不一致 | 用户感知体验差 | [06-动画与转场](06-动画与转场.md) |
| **Insets 计算错误** | SystemBar/IME/Cutout 的 Insets 计算异常，导致内容被遮挡或布局错位 | 兼容性问题高发 | [04-布局与 Insets](04-布局与Insets.md) |

### 8.2 快速诊断速查表

| 问题现象                            | 可能的层                   | 排查入口                                                                                |
| ------------------------------- | ---------------------- | ----------------------------------------------------------------------------------- |
| `BadTokenException` Crash       | App 层 / WMS 层          | 检查 `Activity.isFinishing()` / `isDestroyed()`，堆栈中定位 `addWindow` 返回码                 |
| "Activity has leaked window" 日志 | App 层                  | `WindowManagerGlobal.mViews` 残留项，Activity.onDestroy 中是否 dismiss 了所有 Dialog          |
| 窗口打开后黑屏                         | WMS 层 / SurfaceFlinger | `dumpsys window` 查看 `mHasSurface`，`dumpsys SurfaceFlinger --list` 查看 Layer 是否存在     |
| 点击/按键无反应但不 ANR                  | WMS 层 / Input          | `dumpsys input` 检查 `FocusedWindow`，`dumpsys window` 检查 `mCurrentFocus`              |
| ANR: no focused window          | WMS 层                  | `dumpsys window` 中 `mFocusedApp` vs `mCurrentFocus`，检查 Activity 启动耗时                |
| system_server Watchdog 重启       | WMS 锁                  | `data/anr/traces.txt` 中 `system_server` 主线程和 Binder 线程的锁等待栈                         |
| 屏幕旋转后黑屏/闪烁                      | Surface 重建时序           | Systrace 查看 Configuration 变更 → Surface destroy → Surface create 的时序                 |
| IME 弹不出来                        | DisplayPolicy / IMS    | `dumpsys window` 查看 `TYPE_INPUT_METHOD` 窗口状态，`dumpsys input_method` 检查 IME 连接       |
| 窗口层级异常（被意外遮挡）                   | WMS 层级计算               | `dumpsys window containers` 查看 WindowContainer 树，确认 Z-order                         |
| Surface 泄漏导致内存增长                | SurfaceFlinger         | `dumpsys SurfaceFlinger --list` 对比 Layer 数量变化，`dumpsys meminfo surfaceflinger` 查看显存 |

### 8.3 各层风险分布

```
┌────────────────────────────────────────────────────────────────────────┐
│  App 层                                                                │
│   • BadTokenException: Activity 已 finish 但调用 Dialog.show()         │
│   • WindowLeaked: Activity 销毁时未 dismiss Dialog/PopupWindow         │
│   • performTraversals 耗时 → 掉帧 / ANR                               │
│   • Surface.lockCanvas 失败 → IllegalStateException                    │
├────────────────────────────────────────────────────────────────────────┤
│  WMS 层                                                                │
│   • mGlobalLock 竞争 → Binder 调用阻塞 → App 启动慢 / Watchdog 超时    │
│   • 焦点计算错误 → Key 事件发错窗口 / 焦点丢失 → ANR                    │
│   • performSurfacePlacement 循环超限 → 布局计算死循环                   │
│   • WindowContainer 层级树状态不一致 → 窗口显示异常                      │
├────────────────────────────────────────────────────────────────────────┤
│  Surface/SurfaceFlinger 层                                             │
│   • Surface 创建失败（fd 耗尽/显存不足）→ 窗口黑屏                       │
│   • Surface 泄漏（未正确 release）→ 显存持续增长 → OOM                   │
│   • GraphicBuffer 分配超时 → dequeueBuffer ANR                         │
│   • HWC 合成失败 → 回退 GPU 合成 → 性能下降                             │
├────────────────────────────────────────────────────────────────────────┤
│  Input 交互层                                                          │
│   • InputChannel 注册延迟 → 窗口创建后短暂无法接收触摸                   │
│   • InputMonitor 更新不及时 → 触摸事件发错窗口                           │
│   • InputChannel fd 泄漏 → 窗口销毁后 InputDispatcher Connection 残留   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 9. 实战案例

### Case 1：BadTokenException — Activity 销毁后弹 Dialog（典型模式）

**现象**

线上频繁收到以下 Crash 堆栈：

```
android.view.WindowManager$BadTokenException:
    Unable to add window -- token android.os.BinderProxy@a1b2c3d is not valid;
    is your activity running?
    at android.view.ViewRootImpl.setView(ViewRootImpl.java:1024)
    at android.view.WindowManagerGlobal.addView(WindowManagerGlobal.java:393)
    at android.view.WindowManagerImpl.addView(WindowManagerImpl.java:109)
    at android.app.Dialog.show(Dialog.java:342)
    at com.example.app.NetworkCallback.onError(NetworkCallback.java:56)
```

**排查过程**

**第一步：分析堆栈**

Crash 发生在 `Dialog.show()` → `addView()` → `setView()` 中。`setView()` 调用 `mWindowSession.addToDisplayAsUser()`（Binder 到 WMS），WMS 的 `addWindow()` 返回了 `ADD_BAD_APP_TOKEN`。

**第二步：理解 Token 校验机制**

WMS 在 `addWindow()` 中做了以下校验：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
// addWindow() 中的 token 校验逻辑（简化）
WindowToken token = displayContent.getWindowToken(attrs.token);
if (token == null) {
    if (attrs.type >= FIRST_APPLICATION_WINDOW
            && attrs.type <= LAST_APPLICATION_WINDOW) {
        // Application 窗口的 token 必须是已注册的 ActivityRecord
        // 如果 Activity 已经 finish/destroy，其 token 已从 DisplayContent 移除
        return WindowManagerGlobal.ADD_BAD_APP_TOKEN;
    }
}
```

Dialog 的 `WindowManager.LayoutParams.type` 是 `TYPE_APPLICATION`（Application 窗口），它的 `token` 是所属 Activity 的 `ActivityRecord.token`。当 Activity 进入 `finishing` 状态后，AMS 会通知 WMS 清理对应的 `ActivityRecord`，其 token 从 `DisplayContent` 移除。此后任何使用该 token 创建的窗口都会得到 `ADD_BAD_APP_TOKEN`。

**第三步：定位业务代码**

```java
// com.example.app.NetworkCallback.java (问题代码)
public class NetworkCallback {
    private Activity mActivity;

    public void onError(String error) {
        // 网络回调在后台线程，通过 Handler post 到主线程
        mActivity.runOnUiThread(() -> {
            // 问题：未检查 Activity 是否仍然存活
            new AlertDialog.Builder(mActivity)
                    .setMessage("Network error: " + error)
                    .show();  // 如果 Activity 已 finish → BadTokenException
        });
    }
}
```

**根因**

异步网络请求发出后，用户在等待期间按了返回键退出 Activity。Activity 进入 `finishing` 状态并最终被 `destroy`。随后网络回调返回，`onError()` 在 Activity 已销毁的情况下调用了 `Dialog.show()`。此时 Dialog 的 token 指向的 `ActivityRecord` 已从 WMS 中移除 → `ADD_BAD_APP_TOKEN` → `BadTokenException`。

**时间线：**

```
T=0s    用户触发网络请求，NetworkCallback 注册
T=1s    用户按返回键 → Activity.finish()
T=1.1s  AMS 通知 WMS 清理 ActivityRecord
        WMS: DisplayContent.removeToken(activityRecord.token)
T=1.5s  Activity.onDestroy() 执行
T=3s    网络请求返回 → onError() 回调
T=3.1s  runOnUiThread → Dialog.show() → addView() → setView()
        → addToDisplayAsUser() → WMS.addWindow()
        → token 已不存在 → ADD_BAD_APP_TOKEN
        → BadTokenException!
```

**修复方案**

```java
// 修复后
public void onError(String error) {
    mActivity.runOnUiThread(() -> {
        // 修复：检查 Activity 是否仍然存活
        if (mActivity.isFinishing() || mActivity.isDestroyed()) {
            return;
        }
        new AlertDialog.Builder(mActivity)
                .setMessage("Network error: " + error)
                .show();
    });
}
```

更彻底的修复方案是使用 `Lifecycle` 感知组件，在 Activity 销毁时自动取消回调：

```java
// 使用 Lifecycle 的修复方案
public void onError(String error) {
    if (mActivity.getLifecycle().getCurrentState().isAtLeast(Lifecycle.State.STARTED)) {
        mActivity.runOnUiThread(() -> {
            if (mActivity.getLifecycle().getCurrentState().isAtLeast(Lifecycle.State.STARTED)) {
                new AlertDialog.Builder(mActivity)
                        .setMessage("Network error: " + error)
                        .show();
            }
        });
    }
}
```

> **稳定性架构师视角：** `BadTokenException` 是 Android 应用中 Top 5 的 Crash 类型。根因永远是"在 Activity 生命周期结束后仍试图操作其窗口"。防御手段有三个层次：① 在 UI 操作前检查 `isFinishing()/isDestroyed()`；② 使用 `Lifecycle` 感知组件自动管理回调；③ 在 `Activity.onDestroy()` 中取消所有异步任务。对于框架层面的治理，可以在 `Dialog.show()` 中封装 try-catch，但这只是兜底，根本方案是修正生命周期管理。

---

### Case 2：屏幕旋转后黑屏 — Surface 重建时序问题（典型模式）

**现象**

某 App 在特定页面旋转屏幕后，整个窗口变为黑屏。logcat 无 Crash 日志，但 `dumpsys window` 显示窗口的 `mHasSurface=false`。问题在中端设备上复现率约 2%，高端设备几乎不复现。

**排查过程**

**第一步：理解屏幕旋转时的 Surface 生命周期**

屏幕旋转触发 Configuration 变更，如果 Activity 未声明 `configChanges="orientation|screenSize"`，则会经历销毁→重建的完整流程：

```
旋转前:
  Activity(old).onPause()
  Activity(old).onStop()
  Activity(old).onDestroy()
    → ViewRootImpl.die()
      → WMS.removeWindow()
        → destroySurface() ← 旧 Surface 销毁

旋转后:
  Activity(new).onCreate()
  Activity(new).onStart()
  Activity(new).onResume()
    → addView() → addWindow()
      → relayoutWindow()
        → createSurfaceLocked() ← 新 Surface 创建
    → performTraversals() → draw
```

**第二步：Systrace 分析关键时序**

在 Systrace 中，正常情况下旧 Surface 销毁与新 Surface 创建之间的间隔应在 50-100ms 级别。但在问题设备上，发现以下异常：

```
T=0ms     旋转开始，Configuration 变更
T=10ms    Activity(old).onPause()
T=15ms    Activity(old).onStop()
T=30ms    Activity(old).onDestroy()
T=35ms    WMS.removeWindow() → destroySurface()
          → SurfaceFlinger 释放旧 Layer

T=40ms    Activity(new).onCreate()
T=80ms    Activity(new).onResume()
T=85ms    addView() → addWindow() [成功]
T=90ms    relayoutWindow() → createSurfaceLocked()
          → SurfaceFlinger.createLayer() [请求发出]

T=90ms    App 端 performTraversals() 开始
T=92ms    relayoutWindow() 返回，但 Surface 尚未就绪
          → Surface.isValid() == false  ← 异常！
T=95ms    performDraw() 跳过（Surface 无效）
T=100ms   SurfaceFlinger 完成 Layer 创建（异步）

          → 此后 App 未再收到触发 performTraversals 的信号
          → 窗口保持黑屏
```

**第三步：根因分析**

问题出在 `relayoutWindow()` 返回后，`SurfaceControl` 对应的 SurfaceFlinger Layer 尚未完成初始化。在高负载设备上，SurfaceFlinger 的 Binder 线程可能延迟处理 `createLayer` 请求。App 端的 `performTraversals()` 发现 Surface 无效，跳过了 `performDraw()`。正常情况下，`relayoutWindow()` 返回时 Surface 应该是就绪的，因为 `createSurfaceLocked()` 是同步操作。但在极端情况下，`SurfaceControl.build()` 返回的句柄在 SurfaceFlinger 侧的 Layer 初始化存在微小延迟。

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
// performTraversals() 中的关键逻辑
private void performTraversals() {
    // ...
    if (mFirst || windowShouldResize || viewVisibilityChanged || ...) {
        relayoutResult = relayoutWindow(params, viewVisibility, insetsPending);
    }

    // 关键检查：Surface 是否有效
    if (!mSurface.isValid()) {
        // Surface 无效，跳过绘制
        // 如果后续没有再触发 requestLayout()，窗口将保持黑屏
        return;
    }

    // ... measure → layout → draw
}
```

**修复方案**

在 `performTraversals()` 中，如果检测到 Surface 无效但窗口应该可见，主动 `scheduleTraversals()` 触发重试：

```java
// 业务层防御方案：在 onResume 后延迟检查窗口状态
@Override
protected void onResume() {
    super.onResume();
    // 旋转后延迟检查，如果窗口黑屏则强制 requestLayout
    getWindow().getDecorView().postDelayed(() -> {
        View decorView = getWindow().getDecorView();
        if (decorView.getWidth() == 0 || decorView.getHeight() == 0) {
            decorView.requestLayout();
        }
    }, 100);
}
```

系统层面的根本修复（Android 14 中已优化）：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
// Android 14 的改进：Surface 无效时自动重试
if (!mSurface.isValid() && isVisibleRequested) {
    // Surface 还没就绪，但窗口应该可见 → 重新调度 traversal
    scheduleTraversals();
    return;
}
```

> **稳定性架构师视角：** 屏幕旋转黑屏是一个典型的"时序竞争"问题。Surface 的销毁和重建涉及 App 进程、system_server（WMS）、surfaceflinger 三个进程的协作，任何一步延迟都可能导致状态不一致。排查此类问题的关键工具是 Systrace/Perfetto：通过 `wm` 和 `view` 标签可以追踪 `relayoutWindow` 和 `performTraversals` 的时序，通过 `SurfaceFlinger` 标签可以追踪 Layer 的创建和销毁。`dumpsys window` 中 `mHasSurface` 字段的值（true/false）是判断 Surface 状态的关键。

---

## 总结

作为稳定性架构师，排查 Window 系统问题时需要记住以下关键点：

1. **Window = Surface + LayoutParams + InputChannel**。三者缺一不可。Surface 缺失 → 黑屏；InputChannel 缺失 → 无法接收输入；LayoutParams 错误 → 窗口行为异常。排查时先确定哪个组件出了问题。

2. **mGlobalLock 是 WMS 的命门**。几乎所有窗口操作都需要持有这把锁。锁竞争是 WMS Watchdog 超时、App 启动慢、窗口操作卡顿的最常见原因。排查时关注 `system_server` 线程栈中 `mGlobalLock` 的持有者和等待者。

3. **焦点同步是 WMS 与 Input 系统的关键交互**。WMS 通过 `InputMonitor` 将焦点信息同步到 InputDispatcher。焦点更新延迟 → Key 事件发错窗口；焦点为 null → Input ANR。`dumpsys input` 中的 `FocusedApplications` 和 `FocusedWindows` 是排查 ANR 的第一入口。

4. **Window 生命周期中的每个 Binder 调用都是同步阻塞的**。`addWindow()`、`relayoutWindow()`、`removeWindow()` 都是 App 主线程到 system_server 的同步调用。WMS 侧的任何延迟都会直接阻塞 App 主线程，影响 Activity 启动速度和 UI 响应性。

5. **Surface 的创建和销毁是跨三个进程的协作**。App → WMS → SurfaceFlinger 的链路中，时序问题会导致黑屏、Surface 泄漏、显存增长。排查工具链：`dumpsys window`（WMS 侧）→ `dumpsys SurfaceFlinger`（SF 侧）→ Systrace/Perfetto（时序分析）。

**排查路径速查：**

```
问题现象 → 排查入口
─────────────────────────
BadTokenException     → Activity 生命周期 + Dialog.show() 调用时机
WindowLeaked          → Activity.onDestroy() 中是否 dismiss 所有窗口
黑屏                  → dumpsys window (mHasSurface) + dumpsys SurfaceFlinger
焦点 ANR              → dumpsys input (FocusedWindow) + dumpsys window (mCurrentFocus)
WMS Watchdog          → traces.txt 中 mGlobalLock 的持有者
触摸发错窗口          → dumpsys input (InputWindows) + dumpsys window containers
启动慢                → Systrace (addWindow/relayoutWindow 耗时)
```

---

## 附录：核心源码路径索引

| 文件名 | 完整路径 | 说明 |
|--------|---------|------|
| WindowManagerService.java | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | WMS 主入口，addWindow/relayoutWindow/removeWindow |
| WindowState.java | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | 窗口核心抽象，生命周期管理 |
| WindowContainer.java | `frameworks/base/services/core/java/com/android/server/wm/WindowContainer.java` | 窗口容器层级基类 |
| DisplayContent.java | `frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java` | 单 Display 窗口管理，焦点计算 |
| DisplayPolicy.java | `frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java` | SystemBar/IME 策略 |
| InputMonitor.java | `frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java` | WMS→InputDispatcher 焦点同步 |
| WindowSurfacePlacer.java | `frameworks/base/services/core/java/com/android/server/wm/WindowSurfacePlacer.java` | 全局布局计算协调 |
| WindowStateAnimator.java | `frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java` | Surface 创建与动画 |
| Session.java | `frameworks/base/services/core/java/com/android/server/wm/Session.java` | App↔WMS Binder 会话 |
| Task.java | `frameworks/base/services/core/java/com/android/server/wm/Task.java` | 任务栈管理 |
| ActivityRecord.java | `frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java` | Activity 在 WMS 中的表示 |
| RootWindowContainer.java | `frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java` | 窗口容器树根节点 |
| TaskDisplayArea.java | `frameworks/base/services/core/java/com/android/server/wm/TaskDisplayArea.java` | Task 的 Display 区域 |
| ViewRootImpl.java | `frameworks/base/core/java/android/view/ViewRootImpl.java` | App 端窗口核心，setView/performTraversals |
| WindowManagerGlobal.java | `frameworks/base/core/java/android/view/WindowManagerGlobal.java` | 进程级窗口管理 |
| PhoneWindow.java | `frameworks/base/core/java/com/android/internal/policy/PhoneWindow.java` | Activity 默认 Window 实现 |
| SurfaceControl.java | `frameworks/base/core/java/android/view/SurfaceControl.java` | Surface 操作 Java 封装 |
| SurfaceControl.cpp | `frameworks/native/libs/gui/SurfaceControl.cpp` | Surface 操作 Native 实现 |
| InputDispatcher.cpp | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` | Input 事件分发与焦点管理 |
| SurfaceFlinger.cpp | `frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp` | 图形合成引擎 |

---

## 参考与延伸

本文作为 Window 系列的总览篇，建立了从 `addView` 到屏幕显示的全链路认知框架。后续文章将逐篇深入：

| 篇目 | 标题 | 核心内容 |
|------|------|---------|
| 02 | [Window 的创建与添加](02-Window的创建与添加.md) | addView → addWindow 全流程源码走读，Token 机制，BadTokenException 根因 |
| 03 | [WindowContainer 层级体系](03-WindowContainer层级体系.md) | WindowContainer 树结构，Z-order 计算，层级异常排查 |
| 04 | [布局与 Insets](04-布局与Insets.md) | performSurfacePlacement、Insets 计算、IME 适配、Cutout 处理 |
| 05 | [Surface 与 SurfaceFlinger](05-Surface与SurfaceFlinger.md) | Surface 生命周期、BufferQueue、SurfaceFlinger 合成、黑屏排查 |
| 06 | [动画与转场](06-动画与转场.md) | 窗口动画框架、Activity 转场、SurfaceAnimationRunner |
| 07 | [WMS 与 Input 焦点管理](07-WMS与Input焦点管理.md) | InputMonitor、焦点同步、焦点丢失 → ANR 排查 |
| 08 | [TTID/TTFD 与启动优化](08-TTID与TTFD.md) | Window 视角的启动耗时分解、优化策略 |
| 09 | [稳定性风险全景](09-稳定性风险全景.md) | Window 系统全类型稳定性问题的分类与治理 |
| 10 | [WMS 锁与 Watchdog](10-WMS锁与Watchdog.md) | mGlobalLock 竞争分析、Watchdog 超时、死锁排查 |
| 11 | [诊断工具与实战](11-诊断工具与实战.md) | dumpsys window、Systrace/Perfetto、SurfaceFlinger 诊断 |

**工具速查：**

| 工具 | 用途 | 命令示例 |
|------|------|---------|
| `dumpsys window` | WMS 状态、窗口列表、焦点信息 | `adb shell dumpsys window windows` |
| `dumpsys window containers` | WindowContainer 层级树 | `adb shell dumpsys window containers` |
| `dumpsys input` | InputDispatcher 状态、焦点窗口 | `adb shell dumpsys input` |
| `dumpsys SurfaceFlinger` | Layer 列表、显存占用 | `adb shell dumpsys SurfaceFlinger --list` |
| Systrace/Perfetto | 端到端时序分析 | `python systrace.py -t 5 wm view input gfx` |
| traces.txt | ANR/Watchdog 线程栈 | `adb pull /data/anr/traces.txt` |

**跨系列引用：**

- Input 事件从 InputDispatcher 到 App 的投递链路，详见 [Input 系列-01-Input 系统总览](../Input/01-Input系统总览.md)
- InputChannel 的创建与注册机制，详见 [Input 系列-04-InputChannel](../Input/04-InputChannel与跨进程通信.md)
- Input ANR 的触发与裁决流程，详见 [Input 系列-06-Input ANR](../Input/06-InputANR.md)

---

下一篇 [02-Window 的创建与添加](02-Window的创建与添加.md) 将深入 `addView()` → `addWindow()` 的完整源码流程，详细分析 Token 校验机制、WindowState 的创建过程、以及 `BadTokenException` / `WindowLeaked` 等稳定性问题的根因与治理方案。
