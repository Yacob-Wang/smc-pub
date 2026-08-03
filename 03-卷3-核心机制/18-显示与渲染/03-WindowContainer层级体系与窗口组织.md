# 03-WindowContainer 层级体系与窗口组织

## 1. WindowContainer 层级模型

### 1.1 为什么需要一棵树

Android 的一块屏幕上可能同时存在数十个窗口：Activity 窗口、Dialog、StatusBar、NavigationBar、IME 软键盘、画中画窗口、分屏模式下的两个 Task……这些窗口之间存在严格的层级关系——谁盖在谁上面、谁先获得焦点、谁先收到触摸事件。如果用一个扁平列表来管理这些窗口，每次添加、删除、排序操作都会是 O(n) 的全量遍历；更麻烦的是，窗口之间的"从属关系"（子窗口必须跟随父窗口生命周期）无法自然表达。

WMS 的解决方案是**用一棵树来组织所有窗口**。树的每个节点都是一个 `WindowContainer`，它既是容器（可以持有子节点），又可以代表具体的窗口实体（如 `WindowState`）。树的根是 `RootWindowContainer`，代表整个窗口系统；每一层向下细分，最终叶节点是单个窗口 `WindowState`。

### 1.2 WindowContainer 树的完整层级

以 Android 14（AOSP android-14.0.0_r1）为基准，WindowContainer 树的典型结构如下：

```
RootWindowContainer
 └── DisplayContent (displayId=0, 主屏幕)
      ├── DisplayArea.Root
      │    ├── DisplayArea("HideDisplayCutout")
      │    │    ├── DisplayArea("OneHanded")
      │    │    │    ├── DisplayArea("DefaultTaskDisplayArea")  ← TaskDisplayArea
      │    │    │    │    ├── Task (taskId=1, ActivityType=HOME)
      │    │    │    │    │    └── ActivityRecord (com.android.launcher3/.Launcher)
      │    │    │    │    │         └── WindowState (Application Window)
      │    │    │    │    ├── Task (taskId=5, ActivityType=STANDARD)
      │    │    │    │    │    ├── ActivityRecord (com.example.app/.MainActivity)
      │    │    │    │    │    │    ├── WindowState (主窗口, TYPE_APPLICATION)
      │    │    │    │    │    │    └── WindowState (子窗口, TYPE_APPLICATION_PANEL)
      │    │    │    │    │    └── ActivityRecord (com.example.app/.DetailActivity)
      │    │    │    │    │         └── WindowState (TYPE_APPLICATION)
      │    │    │    │    └── Task (taskId=8, ActivityType=STANDARD, 分屏)
      │    │    │    │         └── ...
      │    │    │    └── DisplayArea("ImeLayers")  ← IME 层
      │    │    │         └── WindowState (TYPE_INPUT_METHOD)
      │    │    └── ...
      │    ├── DisplayArea("WindowedMagnification")
      │    │    └── DisplayArea("OverlayWindows")
      │    │         ├── WindowState (TYPE_STATUS_BAR)
      │    │         ├── WindowState (TYPE_NAVIGATION_BAR)
      │    │         └── WindowState (TYPE_VOLUME_OVERLAY)
      │    └── ...
      └── (其他 DisplayArea 分组)
```

**关键层级含义：**

| 层级                    | 类型          | 职责                                      |
| :-------------------- | :---------- | :-------------------------------------- |
| `RootWindowContainer` | 根节点         | 持有所有 DisplayContent，全局遍历入口              |
| `DisplayContent`      | 一个物理/虚拟屏幕   | 管理该屏幕上的所有窗口、焦点、布局                       |
| `DisplayArea`         | 窗口分区        | 按 Z-order 策略将窗口分组（如系统装饰层、应用层、IME 层）     |
| `TaskDisplayArea`     | 应用 Task 容器  | 持有所有 Task，是 Activity 窗口的根容器             |
| `Task`                | 任务栈         | 一组相关 Activity 的栈，对应"最近任务"中的一个卡片         |
| `ActivityRecord`      | 单个 Activity | 1:1 对应一个 Activity 实例，持有该 Activity 的所有窗口 |
| `WindowState`         | 单个窗口        | 树的叶节点，代表一个具体的窗口                         |

### 1.3 WindowContainer 基类

所有树节点都继承自 `WindowContainer<E extends WindowContainer>`，这是一个泛型基类，定义了树操作的核心方法。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/WindowContainer.java`

`WindowContainer` 的核心职责是管理子节点列表并提供统一的树遍历能力：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowContainer.java（简化）
class WindowContainer<E extends WindowContainer> extends ConfigurationContainer<E> {

    // 子节点列表，有序，索引越大 Z-order 越高
    protected final WindowList<E> mChildren = new WindowList<>();

    // 父节点引用
    private WindowContainer<WindowContainer> mParent = null;

    // SurfaceControl：与 SurfaceFlinger 对应的图层节点
    SurfaceControl mSurfaceControl;

    void addChild(E child, int index) {
        child.setParent(this);
        mChildren.add(index, child);
        onChildAdded(child);
    }

    void removeChild(E child) {
        mChildren.remove(child);
        child.setParent(null);
        onChildRemoved(child);
    }

    // Z-order 赋值：递归地为整棵子树分配层级
    void assignLayer(SurfaceControl.Transaction t, int layer) {
        t.setLayer(mSurfaceControl, layer);
    }

    void assignChildLayers(SurfaceControl.Transaction t) {
        int layer = 0;
        for (int i = 0; i < mChildren.size(); i++) {
            mChildren.get(i).assignLayer(t, layer++);
            mChildren.get(i).assignChildLayers(t);
        }
    }

    // 自顶向下遍历所有 WindowState（用于 Input 焦点计算和窗口信息收集）
    boolean forAllWindows(ToBooleanFunction<WindowState> callback,
                          boolean traverseTopToBottom) {
        if (traverseTopToBottom) {
            for (int i = mChildren.size() - 1; i >= 0; --i) {
                if (mChildren.get(i).forAllWindows(callback, traverseTopToBottom)) {
                    return true;
                }
            }
        } else {
            for (int i = 0; i < mChildren.size(); i++) {
                if (mChildren.get(i).forAllWindows(callback, traverseTopToBottom)) {
                    return true;
                }
            }
        }
        return false;
    }
}
```

> **稳定性架构师视角**：`mChildren` 列表的顺序直接决定了 Z-order——索引越大的子节点越靠近用户（Z-order 越高）。如果 `addChild` 的 `index` 计算错误，窗口将出现在错误的层级位置，导致用户看到窗口被遮挡或触摸事件被错误窗口拦截。`forAllWindows` 的 `traverseTopToBottom` 参数对于 Input 系统至关重要——InputDispatcher 从 WMS 获取的窗口列表就是通过 `forAllWindows(true)` 生成的自顶向下排序，这决定了触摸事件的命中测试顺序。

### 1.4 WindowContainer 的核心能力

| 方法 | 作用 | 稳定性关联 |
|:---|:---|:---|
| `addChild()` / `removeChild()` | 增删子节点 | 增删时机错误 → 窗口闪现/消失 |
| `assignLayer()` / `assignChildLayers()` | 递归赋 Z-order | Z-order 错误 → 窗口遮挡异常 |
| `forAllWindows()` | 遍历所有 WindowState | 遍历顺序错误 → Input 目标错误 |
| `getParent()` / `setParent()` | 父子关系管理 | 父节点被销毁时子节点未清理 → 泄漏 |
| `prepareSurfaces()` | 通知 SurfaceFlinger 更新图层 | Surface 状态不一致 → 画面残留 |
| `onDescendantOverrideConfigurationChanged()` | 配置变更向上传播 | 配置不同步 → 尺寸/旋转异常 |

---

## 2. DisplayContent — 每个屏幕的窗口管家

### 2.1 一个屏幕一个 DisplayContent

`DisplayContent` 代表一个物理或虚拟显示屏。每接入一个外接显示器、每创建一个虚拟屏（如 Presentation、DisplayManager.createVirtualDisplay），WMS 都会创建一个对应的 `DisplayContent`。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java（简化）
class DisplayContent extends WindowContainer<DisplayArea> {

    // 显示 ID
    private final int mDisplayId;

    // 显示信息（分辨率、密度、刷新率等）
    private final DisplayInfo mDisplayInfo = new DisplayInfo();

    // 当前获得焦点的窗口
    WindowState mCurrentFocus;

    // 当前获得焦点的 App（用于 InputDispatcher 的 FocusedApplication）
    ActivityRecord mFocusedApp;

    // InputMonitor：负责将窗口信息同步给 InputDispatcher
    final InputMonitor mInputMonitor;

    // 布局需要更新的标志
    boolean mLayoutNeeded;

    // 该 Display 的 DisplayArea 层级策略
    private final DisplayAreaPolicy mDisplayAreaPolicy;
}
```

> **稳定性架构师视角**：`mCurrentFocus` 和 `mFocusedApp` 是 Input 事件路由的关键状态。当 Activity 切换时，如果 `mFocusedApp` 已更新但 `mCurrentFocus` 尚未更新（新窗口还没 `addWindow`），InputDispatcher 就会进入"有 FocusedApplication 无 FocusedWindow"的等待状态，5 秒后触发 ANR。这在 [01-Input 系统总览](../Input/01-Input系统总览.md) 的 Case 1 中有详细分析。

### 2.2 DisplayArea 层级体系

DisplayContent 内部并非直接持有 WindowState，而是通过 `DisplayArea` 进行分层组织。`DisplayArea` 是窗口分区的抽象——它将同一层级范围内的窗口聚合在一起，形成分区策略。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/DisplayArea.java`

Android 14 的 DisplayArea 层级由 `DisplayAreaPolicyBuilder` 构建，典型结构如下：

```
DisplayContent (displayId=0)
 └── DisplayArea.Root
      │
      ├── [Layer 0-14] DisplayArea("WindowedMagnification:0:14")
      │    └── DisplayArea("HideDisplayCutout:0:14")
      │         └── DisplayArea("OneHanded:0:14")
      │              └── TaskDisplayArea("DefaultTaskDisplayArea")
      │                   ├── Task (Home)
      │                   ├── Task (Recent Apps)
      │                   └── Task (Standard App Tasks...)
      │
      ├── [Layer 15] DisplayArea("ImeLayers:15:15")
      │    └── ImeContainer
      │         └── WindowState (TYPE_INPUT_METHOD)
      │
      ├── [Layer 16-23] DisplayArea("WindowedMagnification:16:23")
      │    └── DisplayArea("HideDisplayCutout:16:23")
      │         └── DisplayArea("OneHanded:16:23")
      │              ├── WindowState (TYPE_STATUS_BAR)
      │              └── WindowState (TYPE_NAVIGATION_BAR)
      │
      └── [Layer 24-35] DisplayArea("WindowedMagnification:24:35")
           └── DisplayArea("OverlayWindows")
                ├── WindowState (TYPE_VOLUME_OVERLAY)
                ├── WindowState (TYPE_SYSTEM_ALERT)
                └── WindowState (TYPE_TOAST)
```

**窗口类型与 DisplayArea 层级的映射关系：**

| 窗口类型范围                     | 对应 DisplayArea  | Z-order 含义           |
| :------------------------- | :-------------- | :------------------- |
| TYPE_APPLICATION (1-99)    | TaskDisplayArea | 应用窗口，在系统装饰之下         |
| TYPE_INPUT_METHOD (2011)   | ImeLayers       | IME 窗口，在应用层之上、系统装饰之下 |
| TYPE_STATUS_BAR (2000)     | 系统装饰层           | 状态栏，在 IME 之上         |
| TYPE_NAVIGATION_BAR (2019) | 系统装饰层           | 导航栏                  |
| TYPE_SYSTEM_OVERLAY (2006) | OverlayWindows  | 系统级覆盖层，最高            |

### 2.3 DisplayAreaPolicy — 分区策略的构建

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/DisplayAreaPolicyBuilder.java`

`DisplayAreaPolicyBuilder` 定义了 DisplayArea 树的构建规则。OEM 可以通过实现自定义的 `DisplayAreaPolicy.Provider` 来修改窗口分区策略（如支持自由窗口模式、分屏模式等）。

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayAreaPolicyBuilder.java（简化）
class DisplayAreaPolicyBuilder {

    // 特性（Feature）列表——每个 Feature 对应一种窗口分区策略
    private final ArrayList<Feature> mFeatures = new ArrayList<>();

    Result build(WindowManagerService wmService) {
        // 1. 按 Feature 优先级排序
        // 2. 计算每个 Feature 影响的窗口类型范围
        // 3. 递归构建 DisplayArea 树
        // 4. 将 TaskDisplayArea 作为应用窗口的锚点
        return new Result(/* ... */);
    }

    static class Feature {
        final String mName;
        final int mId;
        // 该 Feature 影响的窗口类型范围
        // 例如 "HideDisplayCutout" 影响 [0, 35] 范围内的窗口
        private final boolean[] mWindowLayers;
    }
}
```

> **稳定性架构师视角**：OEM 自定义 `DisplayAreaPolicy` 是稳定性高风险操作。如果自定义策略将某类窗口放入了错误的 DisplayArea 分区，该窗口的 Z-order 将与预期不符——典型表现是 Dialog 被 StatusBar 遮挡、或 Toast 出现在锁屏下方。在多 OEM 适配场景中，此类问题的排查入口是 `dumpsys window displays` 查看 DisplayArea 层级树。

### 2.4 Z-order 的确定机制

每个 DisplayContent 内部的 Z-order 由两个因素共同决定：

1. **DisplayArea 的层级位置**：定义了窗口类型的大范围 Z-order
2. **同一 DisplayArea 内的 mChildren 索引**：定义了同类型窗口之间的相对顺序

```java
// DisplayContent.java（简化）
void assignChildLayers(SurfaceControl.Transaction t) {
    // 自底向上遍历所有 DisplayArea 子节点
    // 索引越大 → Z-order 越高 → 越靠近用户
    int layer = 0;
    for (int i = 0; i < mChildren.size(); i++) {
        final DisplayArea area = mChildren.get(i);
        area.assignLayer(t, layer++);
        area.assignChildLayers(t);
    }
}
```

### 2.5 多屏支持与焦点管理

Android 10+ 支持多屏焦点——每个 DisplayContent 可以独立持有一个 `mCurrentFocus`。但全局只有一个"顶层焦点 Display"，由 `RootWindowContainer.mTopFocusedDisplayId` 标识。

```java
// RootWindowContainer.java（简化）
boolean updateFocusedWindowLocked(int mode, boolean updateInputWindows) {
    // 遍历所有 DisplayContent，更新各自的 mCurrentFocus
    boolean changed = false;
    for (int i = mChildren.size() - 1; i >= 0; --i) {
        final DisplayContent dc = mChildren.get(i);
        changed |= dc.updateFocusedWindowLocked(mode, updateInputWindows);
    }
    // 更新 mTopFocusedDisplayId
    DisplayContent topFocusedDisplay = getTopFocusedDisplayContent();
    if (topFocusedDisplay != null) {
        mTopFocusedDisplayId = topFocusedDisplay.getDisplayId();
    }
    return changed;
}
```

> **稳定性架构师视角**：多屏焦点混淆是多屏设备的高发问题。当外接显示器与主屏同时有用户交互时，`mTopFocusedDisplayId` 可能在两个 Display 之间快速切换。如果 InputDispatcher 使用了过期的 `focusedDisplayId`，KEY 事件（如 BACK 键）会被发送到错误的 Display 上——用户在外接屏幕上按 BACK 键却关闭了主屏的 Activity。排查时应关注 `dumpsys input` 中 `FocusedDisplayId` 和 `dumpsys window displays` 中各 Display 的 `mCurrentFocus`。

---

## 3. Task 与 ActivityRecord

### 3.1 Task — Activity 的任务栈

`Task` 是 ActivityRecord 的容器，对应用户在"最近任务"界面看到的一个卡片。一个 Task 内的 ActivityRecord 按栈序排列——最近打开的 Activity 在栈顶（`mChildren` 列表的末尾）。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/Task.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/Task.java（简化）
class Task extends WindowContainer<WindowContainer> {

    // 任务 ID，全局唯一
    final int mTaskId;

    // 任务亲和性——决定 Activity 被分配到哪个 Task
    String mAffinity;

    // 任务的 Activity 类型
    int mActivityType;  // ACTIVITY_TYPE_STANDARD / HOME / RECENTS / ...

    // 窗口模式
    int mWindowingMode;  // WINDOWING_MODE_FULLSCREEN / MULTI_WINDOW / PINNED / ...

    // 根 Activity 的 Intent
    Intent mRootIntent;

    // 获取栈顶 Activity（最近使用的）
    ActivityRecord topRunningActivity() {
        for (int i = mChildren.size() - 1; i >= 0; --i) {
            WindowContainer child = mChildren.get(i);
            if (child instanceof ActivityRecord) {
                ActivityRecord r = (ActivityRecord) child;
                if (!r.finishing && r.isState(RESUMED, PAUSED, STARTED)) {
                    return r;
                }
            }
        }
        return null;
    }
}
```

### 3.2 Task 的启动模式与窗口组织

Activity 的 `launchMode` 直接影响 Task 的组织方式：

| launchMode | 行为 | 对窗口树的影响 |
|:---|:---|:---|
| `standard` | 每次启动创建新 ActivityRecord 入栈 | 同一 Task 中可能有多个相同 Activity 的实例 |
| `singleTop` | 栈顶已有则复用（调用 onNewIntent） | 不创建新 ActivityRecord，WindowState 不变 |
| `singleTask` | 整个 Task 中已有则复用，并清除其上方 Activity | 目标 Activity 之上的 ActivityRecord 被销毁，对应 WindowState 移除 |
| `singleInstance` | 独占一个 Task | 该 Task 中永远只有一个 ActivityRecord |

```
singleTask 启动前:                    singleTask 启动后:
Task(taskId=5)                       Task(taskId=5)
 ├── ActivityRecord(A)  ← target     ├── ActivityRecord(A)  ← 栈顶
 ├── ActivityRecord(B)                └── (B, C 被清除)
 └── ActivityRecord(C)  ← 栈顶
```

> **稳定性架构师视角**：`singleTask` 模式在清除栈顶 Activity 时，会依次调用 `finish()` → `removeWindow()`。如果 Activity B 的 `onDestroy()` 中执行了耗时操作（如同步保存数据），会延迟整个清除过程。在此期间，Activity A 的窗口虽然已经 RESUMED，但可能还没完成 `relayout`，用户看到的是短暂的黑屏或闪烁。

### 3.3 ActivityRecord — Activity 在 WMS 中的化身

每个 `Activity` 在 WMS 侧对应一个 `ActivityRecord`。`ActivityRecord` 持有该 Activity 的所有窗口（`WindowState`），并作为 AMS 和 WMS 之间的桥梁。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java`

```java
// frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java（简化）
class ActivityRecord extends WindowToken {

    // Activity 组件名
    final ComponentName mActivityComponent;

    // App 进程引用
    WindowProcessController app;

    // Activity 生命周期状态
    ActivityState mState;  // INITIALIZING / STARTED / RESUMED / PAUSING / STOPPED / DESTROYING / DESTROYED

    // 该 ActivityRecord 的 token，也是 InputDispatcher 中 FocusedApplication 的标识
    final ActivityRecord.Token appToken;

    // 该 Activity 的主窗口
    WindowState findMainWindow() {
        WindowState win = findMainWindow(true /* includeStartingApp */);
        return win;
    }

    // 该 Activity 拥有的所有窗口（通过 WindowToken 机制）
    // WindowToken 继承自 WindowContainer<WindowState>
    // mChildren 即为该 Activity 的所有 WindowState
}
```

**一个 Activity 可以拥有多个 WindowState：**

```
ActivityRecord (com.example.app/.MainActivity)
 ├── WindowState (TYPE_BASE_APPLICATION)   ← 主窗口，setContentView 创建
 ├── WindowState (TYPE_APPLICATION_PANEL)  ← PopupWindow
 └── WindowState (TYPE_APPLICATION_SUB_PANEL) ← 子菜单
```

### 3.4 ActivityRecord.token 与 InputDispatcher 的关联

`ActivityRecord.appToken` 是 WMS 通知 InputDispatcher "当前焦点 App 是谁"的凭证。当 Activity 切换时：

```
AMS: resumeTopActivity(ActivityRecord A)
  → WMS: setFocusedApp(A.appToken)
    → DisplayContent.mFocusedApp = A
      → InputMonitor.setFocusedAppLw(A)
        → InputDispatcher.setFocusedApplication(displayId, A.appToken)
```

InputDispatcher 的 `setFocusedApplication()` 方法：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp（简化）
void InputDispatcher::setFocusedApplication(
        int32_t displayId,
        const std::shared_ptr<InputApplicationHandle>& inputApplicationHandle) {
    std::scoped_lock _l(mLock);

    auto it = mFocusedApplicationHandlesByDisplay.find(displayId);
    if (it != mFocusedApplicationHandlesByDisplay.end()) {
        resetNoFocusedWindowTimeoutLocked();
    }

    if (inputApplicationHandle != nullptr) {
        mFocusedApplicationHandlesByDisplay[displayId] = inputApplicationHandle;
    } else {
        mFocusedApplicationHandlesByDisplay.erase(displayId);
    }
}
```

> **稳定性架构师视角**：`setFocusedApplication` 和 `setFocusedWindow`（窗口获得焦点时调用）是两个独立的调用。存在一个关键时间窗口：`FocusedApplication` 已经设置为新 Activity，但 `FocusedWindow` 还是 null（新窗口尚未添加）。在此期间如果有 KEY 事件到来，InputDispatcher 会进入等待状态——等待 `FocusedWindow` 出现，5 秒后超时触发 ANR。更危险的场景是：旧 Activity 已经 destroy 但 `FocusedApplication` 没有被清除（代码路径遗漏），此时 InputDispatcher 持有一个无效的 `InputApplicationHandle`，任何 KEY 事件都会导致 ANR。排查关键：`dumpsys input` 中检查 `FocusedApplications` 与 `FocusedWindows` 是否匹配。

---

## 4. WindowState — 单个窗口的完整状态

### 4.1 WindowState 的定位

`WindowState` 是 WindowContainer 树的叶节点，代表一个具体的窗口。WMS 中的几乎所有操作——布局、绘制、焦点、Input——最终都会落到 `WindowState` 上。

> 源码路径：`frameworks/base/services/core/java/com/android/server/wm/WindowState.java`

### 4.2 核心字段

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java（简化）
class WindowState extends WindowContainer<WindowState> {

    // ===== 窗口属性 =====
    final WindowManager.LayoutParams mAttrs;  // 窗口布局参数（type, flags, format 等）
    final int mBaseLayer;                      // 基础层级（由 TYPE 决定）
    final int mSubLayer;                       // 子窗口层级（相对于父窗口）

    // ===== 窗口几何 =====
    final Rect mFrame = new Rect();            // 窗口在屏幕上的最终位置和大小
    final Rect mRequestedFrame = new Rect();   // App 请求的窗口位置和大小
    final InsetsState mInsetsState;            // 窗口的 Insets 状态

    // ===== Surface 相关 =====
    WindowSurfaceController mWinAnimator;      // Surface 控制器
    SurfaceControl mSurfaceControl;            // 与 SurfaceFlinger 的图层句柄

    // ===== Input 相关 =====
    InputChannel mInputChannel;                // 与 InputDispatcher 的通信通道
    final InputWindowHandleWrapper mInputWindowHandle;  // Input 窗口信息句柄

    // ===== 会话与身份 =====
    final Session mSession;                    // 与 App 进程的 Binder 会话
    final WindowToken mToken;                  // 所属的 WindowToken（通常是 ActivityRecord）
    final int mOwnerUid;                       // 创建该窗口的 App UID
    final int mOwnerPid;                       // 创建该窗口的 App PID

    // ===== 状态标志 =====
    boolean mHasSurface;                       // 是否已分配 Surface
    boolean mRemoved;                          // 是否已被移除
    boolean mDestroying;                       // 是否正在销毁
    boolean mRelayoutCalled;                   // 是否已完成 relayout
    int mViewVisibility;                       // View 层的可见性

    // ===== 焦点 =====
    boolean mFocusable;                        // 是否可获得焦点
}
```

### 4.3 窗口类型

`WindowManager.LayoutParams.type` 定义了窗口的类型，直接决定其 Z-order 范围：

> 源码路径：`frameworks/base/core/java/android/view/WindowManager.java`

```java
// frameworks/base/core/java/android/view/WindowManager.java（关键常量）
public interface WindowManager {
    class LayoutParams {
        // ===== Application Window (1-99) =====
        public static final int TYPE_BASE_APPLICATION   = 1;   // Activity 主窗口
        public static final int TYPE_APPLICATION        = 2;   // 普通 Activity 窗口
        public static final int TYPE_APPLICATION_STARTING = 3;  // Starting Window
        public static final int TYPE_DRAWN_APPLICATION  = 4;   // 需要先绘制再显示的窗口

        // ===== Sub-window (1000-1999) =====
        public static final int TYPE_APPLICATION_PANEL  = 1000; // Panel（PopupWindow）
        public static final int TYPE_APPLICATION_MEDIA  = 1001; // 媒体内容（SurfaceView）
        public static final int TYPE_APPLICATION_SUB_PANEL = 1002; // 子面板
        public static final int TYPE_APPLICATION_ATTACHED_DIALOG = 1003; // 附着 Dialog

        // ===== System Window (2000+) =====
        public static final int TYPE_STATUS_BAR         = 2000; // 状态栏
        public static final int TYPE_SEARCH_BAR         = 2001; // 搜索栏
        public static final int TYPE_PHONE              = 2002; // 来电窗口
        public static final int TYPE_SYSTEM_ALERT       = 2003; // 系统弹窗
        public static final int TYPE_TOAST              = 2005; // Toast
        public static final int TYPE_SYSTEM_OVERLAY     = 2006; // 系统覆盖层
        public static final int TYPE_INPUT_METHOD       = 2011; // 输入法窗口
        public static final int TYPE_WALLPAPER          = 2013; // 壁纸
        public static final int TYPE_NAVIGATION_BAR     = 2019; // 导航栏
        public static final int TYPE_VOLUME_OVERLAY     = 2020; // 音量条
        public static final int TYPE_BOOT_PROGRESS      = 2021; // 开机画面
        public static final int TYPE_APPLICATION_OVERLAY = 2038; // 悬浮窗（需 SYSTEM_ALERT_WINDOW 权限）
    }
}
```

**三类窗口的 Z-order 范围：**

```
Z-order 高 ───────────────────── Z-order 低
 ┌────────────────────────────────────────────────────────┐
 │  System Window (2000+)                                  │
 │  TYPE_SYSTEM_OVERLAY > TYPE_TOAST > TYPE_STATUS_BAR    │
 ├────────────────────────────────────────────────────────┤
 │  Sub-window (1000-1999)                                 │
 │  附着在父窗口上，Z-order 相对于父窗口偏移              │
 ├────────────────────────────────────────────────────────┤
 │  Application Window (1-99)                              │
 │  TYPE_APPLICATION, TYPE_BASE_APPLICATION                │
 └────────────────────────────────────────────────────────┘
```

### 4.4 LayoutParams flags 与稳定性

`LayoutParams.flags` 控制窗口的行为特征，其中几个标志位直接影响触摸和焦点：

| Flag | 值 | 效果 | 稳定性风险 |
|:---|:---|:---|:---|
| `FLAG_NOT_TOUCHABLE` | 0x00000010 | 窗口不接收触摸事件，事件穿透到下层 | 误设此 flag → 窗口无法点击 |
| `FLAG_NOT_FOCUSABLE` | 0x00000008 | 窗口不获取焦点，KEY 事件不发送到此窗口 | 误设此 flag → 输入框无法输入 |
| `FLAG_NOT_TOUCH_MODAL` | 0x00000020 | 窗口外的触摸事件穿透到下层窗口 | 未设此 flag → Dialog 外部点击被拦截，用户无法操作下层 |
| `FLAG_WATCH_OUTSIDE_TOUCH` | 0x00040000 | 窗口外的触摸发送 `ACTION_OUTSIDE` | 可能导致 App 误处理外部触摸 |
| `FLAG_LAYOUT_NO_LIMITS` | 0x00000200 | 允许窗口超出屏幕边界 | 窗口完全在屏幕外 → 不可见但仍占据 Z-order |
| `FLAG_SECURE` | 0x00002000 | 禁止截屏和屏幕录制 | 不影响稳定性，但影响问题排查（无法截屏复现） |

`FLAG_NOT_TOUCHABLE` 在 InputDispatcher 的窗口查找中的作用：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp（简化）
int32_t InputDispatcher::findTouchedWindowTargetsLocked(...) {
    for (const sp<WindowInfoHandle>& windowHandle : getWindowHandlesLocked(displayId)) {
        const WindowInfo& info = *windowHandle->getInfo();

        // FLAG_NOT_TOUCHABLE → 跳过该窗口
        if (info.inputConfig.test(WindowInfo::InputConfig::NOT_TOUCHABLE)) {
            continue;
        }

        // 命中测试
        if (!info.touchableRegionContainsPoint(x, y)) {
            continue;
        }

        // FLAG_NOT_FOCUSABLE → 不阻止后续窗口接收焦点
        // FLAG_NOT_TOUCH_MODAL → 窗口外触摸穿透

        addWindowTargetLocked(windowHandle, ...);

        // 如果窗口不是 NOT_TOUCH_MODAL，则停止查找（该窗口拦截了所有触摸）
        if (!info.inputConfig.test(WindowInfo::InputConfig::NOT_TOUCH_MODAL)) {
            break;
        }
    }
}
```

> **稳定性架构师视角**：`FLAG_NOT_TOUCHABLE` 和 `FLAG_NOT_FOCUSABLE` 是悬浮窗场景的常见坑点。第三方 SDK 的悬浮窗（如推送提醒、广告浮窗）如果忘记设置 `FLAG_NOT_TOUCHABLE`，会遮挡住应用窗口的触摸区域。用户表现为"点不到某个按钮"，但屏幕上看不到明显的遮挡物——因为悬浮窗可能是透明的。排查方法：`dumpsys window windows` 查看所有可见窗口的 `flags` 和 `frame`。

### 4.5 WindowState 的生命周期

```
addWindow()                  → WindowState 创建，加入 WindowContainer 树
  ↓
relayoutWindow()             → 分配 Surface，计算布局
  ↓
finishDrawingWindow()        → App 完成首帧绘制
  ↓
(窗口可见，接收事件)
  ↓
removeWindow() / destroy()   → 从树中移除，释放 Surface 和 InputChannel
```

每个阶段的关键操作：

| 阶段 | WMS 操作 | Input 影响 |
|:---|:---|:---|
| `addWindow()` | 创建 WindowState，注册 InputChannel | InputDispatcher 开始知道这个窗口存在 |
| `relayoutWindow()` | 计算 mFrame，创建 Surface | 窗口的 touchableRegion 更新 |
| `finishDrawingWindow()` | 标记窗口可显示 | 窗口进入 Input 的可见窗口列表 |
| `removeWindow()` | 从树中移除 | InputDispatcher 移除该窗口的 InputChannel |

---

## 5. 窗口 Z-order 与 assignLayer

### 5.1 Z-order 的决定因素

窗口的最终 Z-order 由以下四层因素共同决定，优先级从高到低：

```
┌──────────────────────────────────────────────────────────┐
│ 1. DisplayArea 的分区位置                                 │
│    系统装饰层 > IME 层 > 应用层                          │
│    由 DisplayAreaPolicyBuilder 在启动时静态确定          │
├──────────────────────────────────────────────────────────┤
│ 2. 窗口 TYPE 决定基础层级                                │
│    TYPE_STATUS_BAR(2000) > TYPE_APPLICATION(2)           │
│    映射到 DisplayArea 的某个层级范围                      │
├──────────────────────────────────────────────────────────┤
│ 3. 同类型窗口之间的插入顺序                               │
│    后加入的窗口默认在已有窗口之上                         │
│    受 Token 归属和 Activity 栈序影响                      │
├──────────────────────────────────────────────────────────┤
│ 4. 子窗口相对于父窗口的 subLayer                          │
│    正 subLayer → 在父窗口之上                             │
│    负 subLayer → 在父窗口之下（如 SurfaceView 的媒体层） │
└──────────────────────────────────────────────────────────┘
```

### 5.2 WindowState 的 baseLayer 和 subLayer

`WindowState` 的基础层级在创建时根据 TYPE 计算：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java（简化）
// 通过 WindowManagerPolicy 计算基础层级
int getWindowLayerFromTypeLw(int type) {
    if (type >= FIRST_APPLICATION_WINDOW && type <= LAST_APPLICATION_WINDOW) {
        return App;  // 2
    }
    switch (type) {
        case TYPE_WALLPAPER:           return 1;
        case TYPE_STATUS_BAR:          return 15;
        case TYPE_INPUT_METHOD:        return 13;
        case TYPE_NAVIGATION_BAR:      return 17;
        case TYPE_VOLUME_OVERLAY:      return 21;
        case TYPE_SYSTEM_OVERLAY:      return 25;
        case TYPE_APPLICATION_OVERLAY: return 12;
        // ... 其他类型
    }
}
```

子窗口的 `subLayer` 决定了它相对于父窗口的偏移：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerPolicy.java（简化）
int getSubWindowLayerFromTypeLw(int type) {
    switch (type) {
        case TYPE_APPLICATION_PANEL:       return 1;  // 在父窗口之上
        case TYPE_APPLICATION_MEDIA:       return -2; // 在父窗口之下（SurfaceView）
        case TYPE_APPLICATION_SUB_PANEL:   return 2;  // 在 Panel 之上
        case TYPE_APPLICATION_ATTACHED_DIALOG: return 1;
        case TYPE_APPLICATION_MEDIA_OVERLAY:   return -1; // 在 Media 之上，父窗口之下
    }
}
```

### 5.3 assignLayer 的递归机制

`assignLayer()` 和 `assignChildLayers()` 在 `WindowContainer` 中形成递归调用，将整棵树的逻辑顺序转化为 SurfaceFlinger 能理解的 layer 值：

```java
// WindowContainer.java（简化）
void assignChildLayers(SurfaceControl.Transaction t) {
    int layer = 0;
    for (int i = 0; i < mChildren.size(); i++) {
        final WindowContainer child = mChildren.get(i);
        child.assignLayer(t, layer++);
    }
}

// WindowState 覆盖了 assignLayer，处理子窗口的 subLayer
// WindowState.java（简化）
@Override
void assignLayer(SurfaceControl.Transaction t, int layer) {
    // 主窗口使用传入的 layer
    t.setLayer(mSurfaceControl, layer);

    // 子窗口按 subLayer 排序
    for (int i = 0; i < mChildren.size(); i++) {
        WindowState child = mChildren.get(i);
        // subLayer 为负 → 在父窗口之下
        // subLayer 为正 → 在父窗口之上
        child.assignLayer(t, child.mSubLayer);
    }
}
```

最终 `SurfaceControl.Transaction.setLayer()` 将层级值写入 SurfaceFlinger，SurfaceFlinger 据此决定合成顺序。

### 5.4 Z-order 如何影响 InputDispatcher

InputDispatcher 的 `findTouchedWindowTargetsLocked()` 依赖从 WMS 获取的窗口列表，该列表通过 `DisplayContent.forAllWindows(traverseTopToBottom=true)` 生成——这个遍历顺序与 `assignLayer` 的顺序一致（但方向相反：Z-order 高的先遍历）。

```
InputDispatcher 视角的窗口列表（由 InputMonitor 同步）:
  windowHandles = [
    StatusBar        (z=15, NOT_FOCUSABLE, NOT_TOUCH_MODAL),
    NavigationBar    (z=17, NOT_FOCUSABLE, NOT_TOUCH_MODAL),
    Dialog           (z=2,  FOCUSABLE),
    MainActivity     (z=2,  FOCUSABLE),
    Wallpaper        (z=1,  NOT_TOUCHABLE)
  ]

findTouchedWindowTargetsLocked 遍历顺序:
  1. StatusBar      → 触摸点不在区域内 → skip
  2. NavigationBar  → 触摸点不在区域内 → skip
  3. Dialog         → 触摸点在区域内 → HIT!
     → 不是 NOT_TOUCH_MODAL → 停止查找
     → 事件发给 Dialog
```

> **稳定性架构师视角**：如果 Z-order 与实际视觉不一致（例如 Dialog 的 Surface 在视觉上在 MainActivity 之上，但 WindowContainer 树中 Dialog 的位置在 MainActivity 之下），会导致用户看到 Dialog 却点不到——触摸事件先命中了 MainActivity。这种 Z-order 不一致通常发生在窗口动画过程中：动画改变了 Surface 的视觉位置但未同步更新 WindowContainer 树的顺序。`dumpsys SurfaceFlinger` 和 `dumpsys window windows` 的 Z-order 对比是排查此类问题的关键手段。

---

## 6. WindowContainer 树的遍历与操作

### 6.1 forAllWindows — Input 的核心遍历

`forAllWindows` 是 WMS 中最高频的树遍历方法，它的 `traverseTopToBottom` 参数控制遍历方向：

```java
// WindowContainer.java
boolean forAllWindows(ToBooleanFunction<WindowState> callback,
                      boolean traverseTopToBottom) {
    // 递归遍历，最终只有 WindowState 节点会执行 callback
    // 中间节点（Task, ActivityRecord, DisplayArea）只负责传递遍历
}

// WindowState 覆盖了 forAllWindows
// WindowState.java
@Override
boolean forAllWindows(ToBooleanFunction<WindowState> callback,
                      boolean traverseTopToBottom) {
    if (mChildren.isEmpty()) {
        // 叶节点，执行 callback
        return callback.apply(this);
    }

    // 有子窗口时，需要将主窗口和子窗口混合排序
    // 子窗口的 subLayer > 0 在主窗口之上
    // 子窗口的 subLayer < 0 在主窗口之下
    if (traverseTopToBottom) {
        // 先遍历 subLayer > 0 的子窗口（它们在主窗口之上）
        for (int i = mChildren.size() - 1; i >= 0; --i) {
            WindowState child = mChildren.get(i);
            if (child.mSubLayer >= 0) {
                if (child.forAllWindows(callback, true)) return true;
            }
        }
        // 再遍历主窗口自身
        if (callback.apply(this)) return true;
        // 最后遍历 subLayer < 0 的子窗口（它们在主窗口之下）
        for (int i = mChildren.size() - 1; i >= 0; --i) {
            WindowState child = mChildren.get(i);
            if (child.mSubLayer < 0) {
                if (child.forAllWindows(callback, true)) return true;
            }
        }
    }
    return false;
}
```

**核心使用场景：**

| 调用方 | 遍历方向 | 用途 |
|:---|:---|:---|
| `InputMonitor.updateInputWindows()` | Top-to-Bottom | 生成 InputDispatcher 的窗口列表 |
| `DisplayContent.updateFocusedWindowLocked()` | Top-to-Bottom | 确定哪个窗口获得焦点 |
| `DisplayContent.performLayout()` | Bottom-to-Top | 按依赖关系计算布局 |
| `RootWindowContainer.handleNotObscuredLocked()` | Top-to-Bottom | 确定哪些窗口被遮挡 |

### 6.2 performLayout — 布局遍历

`performLayout()` 遍历所有窗口并计算其 `mFrame`（最终位置和大小）。遍历顺序是自底向上——先布局底层窗口（如 Wallpaper），再布局上层窗口（如 StatusBar），最后布局应用窗口。

```java
// DisplayContent.java（简化）
void performLayout(boolean initial, boolean updateInputWindows) {
    // 1. 标记所有窗口为"待布局"
    clearLayoutNeeded();

    // 2. 第一轮：布局非 App 窗口（StatusBar, NavigationBar 等）
    //    这些窗口的位置通常是固定的
    forAllWindows(w -> {
        if (w.mLayoutAttached) return;  // 跳过附着窗口
        layoutWindowLw(w);
    }, false /* traverseTopToBottom */);

    // 3. 第二轮：布局附着窗口（子窗口跟随父窗口位置）
    forAllWindows(w -> {
        if (!w.mLayoutAttached) return;
        layoutWindowLw(w);
    }, false /* traverseTopToBottom */);

    // 4. 更新 InputMonitor
    if (updateInputWindows) {
        mInputMonitor.updateInputWindowsLw(false /* force */);
    }
}
```

> **稳定性架构师视角**：`performLayout` 执行在 WMS 的锁（`mGlobalLock`）内。如果窗口数量多（如某些 App 创建了大量悬浮窗），`performLayout` 的执行时间会显著增加，加剧 `mGlobalLock` 的锁竞争。极端情况下，WMS 主线程因 `performLayout` 耗时过长被 Watchdog 检测到，触发 system_server 重启。监控指标：单次 `performLayout` 耗时超过 50ms 应告警。

### 6.3 WMS 修改如何传播

WMS 对 WindowContainer 树的修改通常遵循以下传播路径：

```
App 发起请求（如 addView / removeView / relayout）
    │
    ▼
WindowManagerService (持有 mGlobalLock)
    │
    ├── 修改 WindowContainer 树（addChild / removeChild）
    │
    ├── 标记 mLayoutNeeded = true
    │
    ├── 调用 performLayout()
    │   └── 重新计算所有窗口的 mFrame
    │
    ├── 调用 assignChildLayers()
    │   └── 通过 SurfaceControl.Transaction 更新 Z-order
    │
    ├── 调用 mInputMonitor.updateInputWindows()
    │   └── 将最新的窗口列表同步给 InputDispatcher
    │
    └── 提交 SurfaceControl.Transaction → SurfaceFlinger
```

这个传播路径中，任何一步延迟都会导致不一致状态：

| 步骤延迟 | 后果 |
|:---|:---|
| `performLayout` 延迟 | 窗口位置未更新 → 显示与实际不符 |
| `assignChildLayers` 延迟 | Z-order 未更新 → 视觉遮挡错误 |
| `updateInputWindows` 延迟 | InputDispatcher 使用过期窗口信息 → 触摸发送到错误窗口 |
| Transaction 提交延迟 | SurfaceFlinger 不知道新状态 → 画面残留 |

---

## 7. 稳定性风险总结

### 7.1 风险速查表

| 问题类型 | 根因 | 日志关键字 | 排查入口 |
|:---|:---|:---|:---|
| Activity 启动后不可见 | Task affinity 错误导致窗口在后台 Task | `dumpsys activity activities` 中 Task 位置 | `dumpsys window windows` 检查 WindowState 所属 Task |
| 窗口被意外遮挡 | Z-order 异常（DisplayArea 分区错误） | `dumpsys window displays` 中 DisplayArea 层级 | 对比 `dumpsys SurfaceFlinger` 的 layer 值 |
| 触摸穿透 / 无法点击 | `FLAG_NOT_TOUCHABLE` 被误设 | `dumpsys window windows` 中 `flags=` | 搜索所有窗口的 flags，确认无意外标志 |
| 焦点丢失 → KEY 事件异常 | `FLAG_NOT_FOCUSABLE` 被误设 | `dumpsys input` 中 `FocusedWindows: <none>` | 检查当前窗口的 `focusable` 属性 |
| Input ANR: no focus window | `FocusedApp` 已设但 `FocusedWindow` 为 null | `Input dispatching timed out (Waiting because no window has focus...)` | 检查 Activity 启动耗时和 `addWindow` 时机 |
| Input ANR: FocusedApp stale | ActivityRecord 销毁后 `setFocusedApplication` 未清除 | `FocusedApplications` 指向已销毁 Activity | `dumpsys input` 对比 `dumpsys activity` |
| 多屏焦点混淆 | `mTopFocusedDisplayId` 切换不及时 | KEY 事件到达错误 Display | `dumpsys input` 检查 `FocusedDisplayId` |
| 子窗口残留 | 父 WindowState 移除但子 WindowState 未清理 | `dumpsys window windows` 中 orphan WindowState | 检查 `mParent == null` 的 WindowState |
| performLayout Watchdog | 窗口数量过多导致布局耗时 | `Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS` | Systrace 检查 `performLayout` 耗时 |
| 窗口出现在错误 Display | `addWindow` 时 displayId 指定错误 | `dumpsys window windows` 中 `displayId=` | 检查 WindowToken 的 Display 归属 |

### 7.2 dumpsys 输出模式解读

**模式 1：正常的焦点状态**

```
mCurrentFocus=Window{abc1234 u0 com.example.app/com.example.app.MainActivity}
mFocusedApp=ActivityRecord{def5678 u0 com.example.app/.MainActivity t5}
```

`mCurrentFocus` 和 `mFocusedApp` 指向同一个 Activity，焦点状态正常。

**模式 2：焦点空窗期（高风险 ANR）**

```
mCurrentFocus=null
mFocusedApp=ActivityRecord{def5678 u0 com.example.app/.MainActivity t5}
```

`mFocusedApp` 已设置但 `mCurrentFocus` 为 null——Activity 正在启动但窗口还没添加。此时如果有 KEY 事件，5 秒后会 ANR。

**模式 3：Task 堆叠异常**

```
Task{taskId=5 ...}
  ActivityRecord{... com.example.app/.MainActivity visible=false}
Task{taskId=8 ...}  ← 在 Task 5 之上
  ActivityRecord{... com.other.app/.OtherActivity visible=true}
```

目标 Activity 在后台 Task 中（visible=false），被前台 Task 遮挡。如果此时 Intent 错误地将 Activity 启动到了后台 Task，用户将看不到它。

**模式 4：Z-order 不一致**

```
Window #3 Window{... com.example.app/.Dialog}:
  mBaseLayer=21000 mSubLayer=0
  mFrame=[100,200][800,1000]
Window #4 Window{... StatusBar}:
  mBaseLayer=171000 mSubLayer=0
  mFrame=[0,0][1080,100]
```

检查 `mBaseLayer` 的大小关系。如果 Dialog 的 `mBaseLayer` 大于 StatusBar，说明 Dialog 在 StatusBar 之上，这通常不是预期行为。

---

## 8. 实战案例

### Case 1：Activity 启动后不可见——错误的 Task affinity 导致窗口在后台 Task（典型模式）

**现象**

用户点击 App 内的某个入口页面跳转到 `DetailActivity`，但屏幕上什么都没有变化——仍然显示原来的页面。从"最近任务"中可以看到 `DetailActivity` 出现在一个新的 Task 卡片中，但它被原来的 Task 遮挡了。

**分析思路**

**Step 1：确认 Activity 状态**

```bash
$ adb shell dumpsys activity activities | grep -A 5 "DetailActivity"
  * Task{taskId=12 ...}
    * ActivityRecord{abc1234 u0 com.example.app/.DetailActivity t12}
      state=RESUMED
      visible=true (from AM perspective)
```

Activity 确实已经 RESUMED，AMS 认为它是可见的。但用户看不到。

**Step 2：确认窗口在 WindowContainer 树中的位置**

```bash
$ adb shell dumpsys window windows | grep -B 2 "DetailActivity"
  Window #5 Window{def5678 u0 com.example.app/com.example.app.DetailActivity}:
    mDisplayId=0
    mOwnerUid=10086
    ...
    Task=Task{taskId=12}
```

```bash
$ adb shell dumpsys window displays
  DefaultTaskDisplayArea
    Task{taskId=5 ...}     ← Z-order 高（在上面）
      ActivityRecord{... MainActivity}
    Task{taskId=12 ...}    ← Z-order 低（在下面）
      ActivityRecord{... DetailActivity}
```

关键发现：`DetailActivity` 所在的 Task(12) 在 `MainActivity` 所在的 Task(5) **下方**。

**Step 3：分析 Task 创建原因**

查看 `DetailActivity` 的 `AndroidManifest.xml`：

```xml
<activity android:name=".DetailActivity"
          android:taskAffinity="com.example.app.detail"
          android:launchMode="standard" />
```

`taskAffinity` 被设置为 `com.example.app.detail`，与 `MainActivity` 的默认 affinity（包名 `com.example.app`）不同。当 `startActivity` 未指定 `FLAG_ACTIVITY_NEW_TASK` 时，按照 `standard` 模式，Activity 本应在当前 Task 中启动。但由于代码中使用了 `Context`（非 Activity Context）启动 Activity，系统自动添加了 `FLAG_ACTIVITY_NEW_TASK`：

```java
// 问题代码：使用 ApplicationContext 启动 Activity
getApplicationContext().startActivity(intent);
// 系统自动添加 FLAG_ACTIVITY_NEW_TASK
// → 由于 taskAffinity 不同，创建了新 Task
// → 新 Task 被放在已有 Task 的下方
```

**根因**

两个因素叠加：
1. `DetailActivity` 的 `taskAffinity` 被设置为非默认值
2. 使用 `ApplicationContext.startActivity()` 导致系统添加了 `FLAG_ACTIVITY_NEW_TASK`

当 `FLAG_ACTIVITY_NEW_TASK` 遇上不同的 `taskAffinity` 时，系统创建新 Task。新创建的 Task 默认被放在 `TaskDisplayArea` 的 `mChildren` 列表的最前面（Z-order 最低），被已有的前台 Task 遮挡。

**修复方案**

```java
// 修复方案 1：使用 Activity Context 启动
activity.startActivity(intent);

// 修复方案 2：如果必须用 ApplicationContext，添加 FLAG_ACTIVITY_CLEAR_TOP | FLAG_ACTIVITY_SINGLE_TOP
intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
getApplicationContext().startActivity(intent);

// 修复方案 3：移除不必要的 taskAffinity 声明
// AndroidManifest.xml 中删除 android:taskAffinity
```

---

### Case 2：多窗口 Resize 后触摸事件发送到错误窗口——Z-order 未及时更新（典型模式）

**现象**

在分屏模式下，用户拖动分屏分界线调整两个 App 的大小比例。Resize 操作完成后，点击上方 App 的按钮时，触摸事件被下方 App 响应——用户明明点击的是上方区域，但下方 App 的按钮被触发了。问题在 Resize 结束 200-500ms 后自行恢复。

**分析思路**

**Step 1：Systrace 分析时序**

```
T=0ms    用户松手（Resize 操作结束）
T=5ms    WMS: Task.setBounds() → 更新 Task 的 bounds
T=8ms    WMS: performLayout() → 重新计算所有窗口的 mFrame
T=12ms   WMS: assignChildLayers() → 更新 Z-order
T=15ms   WMS: SurfaceFlinger Transaction 提交 → 画面更新
T=18ms   用户触摸上方 App 区域
T=???ms  WMS: mInputMonitor.updateInputWindows() → 窗口信息同步给 InputDispatcher
```

关键发现：在 Systrace 中，`updateInputWindows()` 的调用时间为 T=220ms——远远晚于用户触摸时间（T=18ms）。

**Step 2：确认 InputDispatcher 使用的窗口信息**

```bash
$ adb shell dumpsys input
  Windows:
    0: name='com.example.bottomApp/com.example.bottomApp.BottomActivity'
       frame=[0,960,1080,1920]     ← 旧的 frame（Resize 前的位置）
    1: name='com.example.topApp/com.example.topApp.TopActivity'
       frame=[0,0,1080,960]        ← 旧的 frame
```

InputDispatcher 仍在使用 Resize 前的窗口位置信息。用户触摸的坐标 (540, 800)——按新的布局应该命中上方 App（新 bounds 为 [0,0,1080,1200]），但按旧布局这个坐标落在上方 App 的 frame 内，不过由于 bounds 更新不一致，可能被重新映射到下方 App 的区域。

**Step 3：分析 updateInputWindows 延迟原因**

在 `performLayout()` 的代码中：

```java
void performLayout(boolean initial, boolean updateInputWindows) {
    // ...布局逻辑...

    if (updateInputWindows) {
        mInputMonitor.updateInputWindowsLw(false);
    }
}
```

问题在于某些 Resize 路径调用 `performLayout(false, false)` ——第二个参数 `updateInputWindows=false`。这意味着布局完成后没有立即同步窗口信息给 InputDispatcher。同步被推迟到下一次 `performSurfacePlacement()` 调用时才执行。

```java
// RootWindowContainer.java
void performSurfacePlacement() {
    // ...
    // 在所有 Surface 操作完成后，统一更新 InputWindows
    mWmService.mInputMonitor.updateInputWindowsLw(false);
}
```

当系统负载较高时，`performSurfacePlacement()` 可能被延迟到下一个 VSync 周期甚至更晚，导致 InputDispatcher 在 200ms+ 内使用过期的窗口信息。

**根因**

分屏 Resize 路径中，`performLayout()` 未立即触发 `updateInputWindows()`，导致 InputDispatcher 的窗口位置信息在 200ms+ 内与实际布局不一致。在此时间窗口内的触摸事件会被路由到错误的窗口。

**修复方案**

```java
// 在 Task.setBounds() 之后强制同步 InputWindows
// Task.java
@Override
void setBounds(Rect bounds) {
    super.setBounds(bounds);
    // 确保 InputDispatcher 立即获取最新的窗口信息
    final DisplayContent dc = getDisplayContent();
    if (dc != null) {
        dc.getInputMonitor().updateInputWindowsLw(true /* force */);
    }
}
```

同时，在 `InputMonitor` 中增加"脏标记"机制——当窗口 bounds 变化时立即标记 dirty，并在 InputDispatcher 的下一次 `dispatchOnce()` 循环中强制刷新窗口列表：

```java
// InputMonitor.java
void setUpdateInputWindowsNeededLw() {
    mUpdateInputWindowsNeeded = true;
    // 唤醒 InputDispatcher，使其尽快检查窗口更新
    mService.mInputManager.requestRefreshConfiguration();
}
```

---

## 总结

WindowContainer 层级体系是 Android WMS 的骨架，从 `RootWindowContainer` 到 `WindowState`，每一层都承担着特定的窗口管理职责。对于稳定性架构师，需要记住以下关键点：

1. **WindowContainer 树的顺序即 Z-order**：`mChildren` 列表的索引直接决定了窗口的前后关系。`forAllWindows(traverseTopToBottom=true)` 生成的窗口顺序是 InputDispatcher 进行触摸命中测试的依据。任何 Z-order 错误都会导致触摸事件路由异常。

2. **FocusedApp 与 FocusedWindow 的时间差是 ANR 高发区**：Activity 切换时，`setFocusedApplication` 先于 `addWindow` 执行，形成"有焦点 App、无焦点窗口"的危险窗口期。冷启动慢或 `Application.onCreate` 耗时是此类 ANR 的主要触发因素。

3. **updateInputWindows 的时机至关重要**：WMS 对窗口的任何修改（位置、大小、可见性、Z-order）如果不及时同步给 InputDispatcher，就会出现"用户看到的"与"InputDispatcher 认为的"不一致，导致触摸发送到错误窗口。

4. **LayoutParams.flags 是触摸问题的常见根因**：`FLAG_NOT_TOUCHABLE`、`FLAG_NOT_FOCUSABLE`、`FLAG_NOT_TOUCH_MODAL` 三个标志位直接控制窗口的触摸和焦点行为。第三方 SDK 的悬浮窗是此类问题的高发区。

5. **多屏场景引入额外的焦点维度**：每个 DisplayContent 独立管理焦点，但全局只有一个 `TopFocusedDisplay`。KEY 事件的路由依赖 `FocusedDisplayId`，如果切换不及时会导致按键发送到错误 Display。

**排查路径速查：**

```
窗口不可见?
  → dumpsys window displays → 检查 Task 位置和 Z-order
  → dumpsys activity activities → 检查 Activity 状态和 Task affinity

触摸无响应?
  → dumpsys window windows → 检查 flags (NOT_TOUCHABLE?)
  → dumpsys input → 检查 InputDispatcher 窗口列表和 touchableRegion

焦点异常?
  → dumpsys input → 检查 FocusedApplications 和 FocusedWindows
  → dumpsys window → 检查 mCurrentFocus 和 mFocusedApp

Z-order 异常?
  → dumpsys window displays → 检查 DisplayArea 层级树
  → dumpsys SurfaceFlinger → 检查实际 layer 值
  → 对比两者是否一致
```

---

## 附录：核心源码路径索引

| 文件名 | 完整路径 | 说明 |
|:---|:---|:---|
| `WindowContainer.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowContainer.java` | 树节点基类，定义 addChild/removeChild/forAllWindows/assignLayer |
| `RootWindowContainer.java` | `frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java` | 树根节点，持有所有 DisplayContent |
| `DisplayContent.java` | `frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java` | 屏幕管理器，持有 DisplayArea 层级和焦点状态 |
| `DisplayArea.java` | `frameworks/base/services/core/java/com/android/server/wm/DisplayArea.java` | 窗口分区容器 |
| `DisplayAreaPolicyBuilder.java` | `frameworks/base/services/core/java/com/android/server/wm/DisplayAreaPolicyBuilder.java` | DisplayArea 层级构建策略 |
| `Task.java` | `frameworks/base/services/core/java/com/android/server/wm/Task.java` | 任务栈，持有 ActivityRecord |
| `ActivityRecord.java` | `frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java` | Activity 在 WMS 中的映射 |
| `WindowState.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | 单个窗口的完整状态 |
| `WindowManager.java` | `frameworks/base/core/java/android/view/WindowManager.java` | LayoutParams 定义（type, flags） |
| `InputMonitor.java` | `frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java` | WMS 向 InputDispatcher 同步窗口信息 |
| `InputDispatcher.cpp` | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` | 触摸命中测试和事件分发 |
| `WindowManagerService.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | WMS 入口，addWindow/removeWindow |

---

下一篇 [04-窗口布局与 Insets 机制](04-窗口布局与Insets机制.md) 将深入 WMS 的布局计算流程、Insets（状态栏/导航栏/刘海屏）的管理机制，以及布局异常导致的稳定性问题。
