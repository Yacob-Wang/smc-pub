# 09-Window 稳定性风险全景：黑屏、Crash 与显示异常

## 1. Window 稳定性风险概览

### 1.1 为什么 Window 系统是稳定性重灾区

Window 系统横跨 App 进程、system_server（WMS）、SurfaceFlinger 三个进程，涉及 Binder IPC、共享内存、socketpair 三种跨进程通信机制。**任何一层出问题，都会直接反映到用户可见的界面上**——这使得 Window 相关问题成为用户感知最强烈、定位最困难的稳定性问题。

```
风险贯穿三层架构：

App 进程                    system_server (WMS)              SurfaceFlinger
┌──────────────────┐       ┌──────────────────────┐       ┌──────────────────┐
│ • BadTokenExc.   │       │ • mGlobalLock 竞争    │       │ • Layer 泄漏      │
│ • WindowLeaked   │ Binder│ • 焦点计算错误        │Binder │ • Buffer 分配失败  │
│ • Dialog 泄漏    │ ────→ │ • Token 清理时序      │ ────→ │ • HWC 合成异常     │
│ • draw 超时      │       │ • Surface 创建失败    │       │ • 显存耗尽         │
│ • Surface 失效   │       │ • 窗口列表同步延迟    │       │ • GPU 驱动 Bug     │
└──────────────────┘       └──────────────────────┘       └──────────────────┘
       ↑                            ↑                            ↑
   App 开发者                   系统框架层                    硬件/驱动层
   代码缺陷                     时序竞争                      环境异常
```

### 1.2 风险分类体系

Window 系统的稳定性风险可以按影响类型分为四大类：

| 类别 | 典型问题 | 用户感知 | 影响范围 | 紧急度 |
|------|---------|---------|---------|-------|
| **Crash 类** | `BadTokenException`、`IllegalArgumentException`（View not attached）、`NullPointerException`（Surface 为 null） | App 闪退 | 单个 App | 高 |
| **ANR 类** | 焦点丢失导致 Input ANR、WMS 锁阻塞导致 App 主线程卡死、`relayoutWindow` 超时 | 界面冻结→弹出 ANR 对话框 | 单个 App（严重时级联） | 高 |
| **显示异常类** | 黑屏（5 种子类型）、白屏、窗口闪烁、窗口不显示、窗口位置错误、触摸穿透 | 界面视觉异常 | 单个窗口 / 全屏 | 中-高 |
| **资源泄漏类** | `WindowLeaked`、Surface 泄漏、InputChannel 泄漏、SurfaceControl 未 release | 内存增长→OOM / 性能劣化 | 渐进式全局影响 | 中 |

### 1.3 各类风险的线上占比参考

```
Window 相关线上问题占比（典型 Android App）：

BadTokenException    ████████████████████  35%    ← 最高频 Crash
WindowLeaked         ██████████            18%    ← 内存泄漏首因
黑屏/白屏            ████████████          22%    ← 用户投诉最多
焦点丢失→ANR         ████████              15%    ← 最难排查
Surface 泄漏         ███                    5%    ← 隐蔽但致命
其他显示异常         ███                    5%
```

> **稳定性架构师视角：** BadTokenException 和 WindowLeaked 合计占 Window 问题的 50% 以上，且两者都有清晰的代码模式可以防御。本文将为每种风险建立"现象 → 根因 → 源码 → 修复"的完整排查链路。

---

## 2. BadTokenException 分类与排查

### 2.1 什么是 BadTokenException

`BadTokenException` 是 Android 应用中**最常见的 Window 相关 Crash**。它的直接触发点在 `ViewRootImpl.setView()` 中——当 `mWindowSession.addToDisplayAsUser()` 跨进程调用到 WMS 的 `addWindow()` 后，WMS 的 Token 校验不通过，返回错误码，ViewRootImpl 将错误码转为异常抛出：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
public void setView(View view, WindowManager.LayoutParams attrs, ...) {
    // ...
    res = mWindowSession.addToDisplayAsUser(mWindow, mWindowAttributes, ...);
    // ...
    if (res < WindowManagerGlobal.ADD_OKAY) {
        // WMS 拒绝添加窗口
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
            case WindowManagerGlobal.ADD_PERMISSION_DENIED:
                throw new WindowManager.BadTokenException(
                    "Unable to add window " + attrs.token
                    + " -- permission denied for window type " + attrs.type);
            // ...
        }
    }
}
```

WMS 端的 Token 校验核心逻辑在 `addWindow()` 中：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
public int addWindow(Session session, IWindow client, LayoutParams attrs, ...) {
    synchronized (mGlobalLock) {
        // 从 DisplayContent 的 token 映射表中查找
        WindowToken token = displayContent.getWindowToken(attrs.token);

        if (token == null) {
            if (attrs.type >= FIRST_APPLICATION_WINDOW
                    && attrs.type <= LAST_APPLICATION_WINDOW) {
                // Application 窗口必须有合法 ActivityRecord token
                return WindowManagerGlobal.ADD_BAD_APP_TOKEN;
            }
            // ...
        }

        // 即使找到 token，还要验证类型匹配
        final ActivityRecord activity = token.asActivityRecord();
        if (attrs.type >= FIRST_APPLICATION_WINDOW
                && attrs.type <= LAST_APPLICATION_WINDOW) {
            if (activity == null) {
                return WindowManagerGlobal.ADD_NOT_APP_TOKEN;
            }
            if (activity.finishing) {
                // Activity 正在 finishing，不再接受新窗口
                return WindowManagerGlobal.ADD_BAD_APP_TOKEN;
            }
        }
        // ...
    }
}
```

### 2.2 四大经典触发场景

#### 场景一：Activity 已销毁，异步回调中调用 Dialog.show()

这是最常见的 BadTokenException 场景，占比约 **60%**。

**触发条件：**

```
时间线：
T=0s    发起网络请求/耗时操作，注册回调
T=1s    用户按返回键 → Activity.finish()
T=1.1s  AMS 通知 WMS → DisplayContent.removeToken(activity.token)
T=1.5s  Activity.onDestroy()
T=3s    回调返回 → Dialog.show() → addView() → addWindow()
        → token 不存在 → ADD_BAD_APP_TOKEN → BadTokenException
```

**异常消息与堆栈模式：**

```
android.view.WindowManager$BadTokenException:
    Unable to add window -- token android.os.BinderProxy@7a3b2c1 is not valid;
    is your activity running?
    at android.view.ViewRootImpl.setView(ViewRootImpl.java:1024)
    at android.view.WindowManagerGlobal.addView(WindowManagerGlobal.java:393)
    at android.view.WindowManagerImpl.addView(WindowManagerImpl.java:109)
    at android.app.Dialog.show(Dialog.java:342)
    at com.example.app.SomeCallback.onResult(SomeCallback.java:xx)
```

**问题代码示例：**

```java
// 典型问题代码
public class OrderActivity extends AppCompatActivity {
    private void loadOrderDetail() {
        apiService.getOrderDetail(orderId, new Callback<Order>() {
            @Override
            public void onSuccess(Order order) {
                runOnUiThread(() -> {
                    // 未检查 Activity 状态
                    new AlertDialog.Builder(OrderActivity.this)
                        .setTitle("订单详情")
                        .setMessage(order.toString())
                        .show();  // Activity 可能已销毁 → Crash
                });
            }
        });
    }
}
```

**修复方案：**

```java
// 修复方案一：显式检查 Activity 状态
@Override
public void onSuccess(Order order) {
    runOnUiThread(() -> {
        if (isFinishing() || isDestroyed()) {
            return;
        }
        new AlertDialog.Builder(OrderActivity.this)
            .setTitle("订单详情")
            .setMessage(order.toString())
            .show();
    });
}

// 修复方案二（推荐）：使用 Lifecycle 感知
@Override
public void onSuccess(Order order) {
    getLifecycle().addObserver(new DefaultLifecycleObserver() {
        @Override
        public void onResume(@NonNull LifecycleOwner owner) {
            owner.getLifecycle().removeObserver(this);
            new AlertDialog.Builder(OrderActivity.this)
                .setTitle("订单详情")
                .setMessage(order.toString())
                .show();
        }

        @Override
        public void onDestroy(@NonNull LifecycleOwner owner) {
            owner.getLifecycle().removeObserver(this);
        }
    });
}
```

#### 场景二：TYPE_APPLICATION 窗口使用了错误的 Token

Dialog 默认使用宿主 Activity 的 token。如果开发者从非 Activity 的 Context（如 Application 或 Service）构建 Dialog，token 不对应任何 `ActivityRecord`。

**异常消息：**

```
android.view.WindowManager$BadTokenException:
    Unable to add window -- token null is not for an application
    at android.view.ViewRootImpl.setView(ViewRootImpl.java:1030)
```

**问题代码：**

```java
// 在 Service 中弹 Dialog（错误）
public class MyService extends Service {
    public void showDialog() {
        AlertDialog dialog = new AlertDialog.Builder(this)  // Service context → token == null
            .setTitle("Alert")
            .show();  // → ADD_NOT_APP_TOKEN → BadTokenException
    }
}
```

**修复方案：**

```java
// 方案一：使用 TYPE_APPLICATION_OVERLAY（需权限）
public void showDialog() {
    AlertDialog dialog = new AlertDialog.Builder(this)
        .setTitle("Alert")
        .create();
    dialog.getWindow().setType(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY);
    dialog.show();
}
// 注意：需要 <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW"/>
// 且用户需在设置中授权

// 方案二：通过 Activity 引用显示（如果有可用的 Activity）
```

#### 场景三：WindowToken 被 WMS 移除（Activity finish 时序竞争）

这种场景比场景一更隐蔽。Activity 尚未调用 `onDestroy()`，甚至 `isFinishing()` 可能刚刚变为 true，但 WMS 侧的 token 已被移除。

**时序分析：**

```
App 主线程                           WMS (system_server)
    │                                     │
    │  Activity.finish() 被调用           │
    │  isFinishing() = true               │
    │       ↓ Binder                      │
    │  ──────────────────────────→   AMS.finishActivity()
    │                                     │
    │                                WMS: removeActivityRecord()
    │                                 → DisplayContent.removeToken()  ← token 被移除
    │                                     │
    │  （主线程还在执行 finish 后的代码）  │
    │  Dialog.show()                      │
    │     → addView() → Binder → addWindow()
    │                                → getWindowToken() == null
    │                                → ADD_BAD_APP_TOKEN
    │  ← BadTokenException ─────────      │
```

**关键点：** `isFinishing()` 返回 true 后，到 WMS 实际移除 token 之间存在一个**不确定的时间窗口**。在这个窗口内弹 Dialog 有可能成功也有可能失败，这就是为什么某些 BadTokenException 难以复现。

**防御代码：**

```java
public static void safeShowDialog(Activity activity, Dialog dialog) {
    if (activity == null || activity.isFinishing() || activity.isDestroyed()) {
        return;
    }
    try {
        dialog.show();
    } catch (WindowManager.BadTokenException e) {
        // 兜底：时序竞争窗口内的防御
        Log.w("WindowSafety", "Dialog show failed due to token race", e);
    }
}
```

#### 场景四：系统窗口缺少 SYSTEM_ALERT_WINDOW 权限

Android 6.0+ 对系统窗口（`TYPE_APPLICATION_OVERLAY` 等）要求 `SYSTEM_ALERT_WINDOW` 权限。

**异常消息：**

```
android.view.WindowManager$BadTokenException:
    Unable to add window android.os.BinderProxy@xxx -- permission denied
    for window type 2038
    at android.view.ViewRootImpl.setView(ViewRootImpl.java:1038)
```

**WMS 侧的权限检查：**

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
// addWindow() 入口的权限校验
int res = mPolicy.checkAddPermission(attrs.type, isRoundedCornerOverlay,
        attrs.packageName, appOp);
if (res != ADD_OKAY) {
    return res;  // ADD_PERMISSION_DENIED
}
```

```java
// frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java
int checkAddPermission(int type, ...) {
    if (type >= FIRST_SYSTEM_WINDOW && type <= LAST_SYSTEM_WINDOW) {
        // 系统窗口需要检查 SYSTEM_ALERT_WINDOW 或 INTERNAL_SYSTEM_WINDOW
        if (!hasSystemAlertWindowPermission) {
            return ADD_PERMISSION_DENIED;
        }
    }
    return ADD_OKAY;
}
```

### 2.3 BadTokenException 防御体系

```
防御层次：

┌────────────────────────────────────────────────────────┐
│  第一层：代码规范（预防）                                │
│  • 所有异步回调中，Dialog.show() 前检查 isFinishing()   │
│  • 禁止在非 Activity Context 中创建 TYPE_APPLICATION    │
│  • Lint 规则：检测异步回调中的 Dialog.show()             │
├────────────────────────────────────────────────────────┤
│  第二层：Lifecycle 感知（机制保障）                      │
│  • 使用 LifecycleOwner 绑定 Dialog 生命周期             │
│  • 封装 SafeDialog 工具类，内部自动检查生命周期          │
│  • RxJava/Coroutine 绑定 Lifecycle scope               │
├────────────────────────────────────────────────────────┤
│  第三层：全局兜底（最后防线）                            │
│  • Application.setUnhandledExceptionHandler 中过滤      │
│  • 封装 safeShowDialog 工具方法，try-catch 兜底          │
│  • 线上监控 BadTokenException 频次，触发告警             │
└────────────────────────────────────────────────────────┘
```

---

## 3. WindowLeaked 与资源泄漏

### 3.1 什么触发了 WindowLeaked

当 Activity 执行 `onDestroy()` 时，`ActivityThread.handleDestroyActivity()` 会检查该 Activity 是否还有未移除的窗口。如果有，就打印 `"Activity has leaked window"` 警告，并强制关闭这些窗口：

```java
// frameworks/base/core/java/android/app/ActivityThread.java
public void handleDestroyActivity(ActivityClientRecord r, boolean finishing, ...) {
    // ... 执行 Activity.onDestroy() ...

    // 检查是否有泄漏的窗口
    WindowManager wm = r.activity.getWindowManager();
    View decor = r.activity.mDecor;
    if (decor != null) {
        wm.removeViewImmediate(decor);
    }

    // WindowManagerGlobal.closeAll() 检查残留窗口
    WindowManagerGlobal.getInstance().closeAll(
            wm.getDefaultDisplay().getDisplayId(),
            r.activity.getClass().getName(),
            "Activity");
}
```

```java
// frameworks/base/core/java/android/view/WindowManagerGlobal.java
public void closeAll(int displayId, String who, String what) {
    synchronized (mLock) {
        for (int i = mViews.size() - 1; i >= 0; i--) {
            // 检查是否有属于该 Activity 但未被移除的窗口
            if (mRoots.get(i).mDisplay.getDisplayId() == displayId) {
                // 发现泄漏窗口！
                Log.e(TAG, "Activity " + who + " has leaked window "
                        + mViews.get(i) + " that was originally added here",
                        mRoots.get(i).mLocation);
                // 强制移除
                removeViewLocked(i, true);
            }
        }
    }
}
```

### 3.2 泄漏链分析

WindowLeaked 不仅仅是一个警告——它标志着一条**真实的内存泄漏链**：

```
泄漏链：

Window (未 dismiss 的 Dialog)
 └── ViewRootImpl (持有 View 树根引用)
      └── DecorView (Dialog 的 DecorView)
           └── View 树 (所有子 View)
                └── onClick / Adapter 等内部类
                     └── Activity 引用 (隐式持有外部类引用)
                          └── Activity 的所有成员变量
                               └── Bitmap / 大数组 / 数据库连接 ...

一个未 dismiss 的 Dialog 可以泄漏整个 Activity 及其引用链上的所有对象！
```

**实际内存影响估算：**

| 泄漏对象 | 直接占用 | 间接引用链 | 典型总泄漏量 |
|---------|---------|-----------|------------|
| Dialog（简单文本） | ~50KB | Activity + View 树 | 2-5MB |
| Dialog（包含图片列表） | ~100KB | Activity + Bitmap 缓存 | 10-50MB |
| PopupWindow | ~30KB | Activity + Anchor View 链 | 2-5MB |
| 自定义 Toast（带复杂布局） | ~20KB | Activity Context | 1-3MB |

### 3.3 常见泄漏模式

#### 模式一：Activity 销毁时未 dismiss Dialog

```java
// 泄漏代码
public class MainActivity extends AppCompatActivity {
    private ProgressDialog loadingDialog;

    private void showLoading() {
        loadingDialog = new ProgressDialog(this);
        loadingDialog.show();
    }

    // onDestroy 中未 dismiss loadingDialog
    // → Activity 销毁时 loadingDialog 仍然 attached → WindowLeaked
}
```

#### 模式二：PopupWindow 未 dismiss

```java
// 泄漏代码
public class SearchActivity extends AppCompatActivity {
    private PopupWindow suggestPopup;

    private void showSuggestions(List<String> items) {
        suggestPopup = new PopupWindow(/* ... */);
        suggestPopup.showAsDropDown(searchView);
    }

    // 用户按返回键退出，suggestPopup 未 dismiss
}
```

#### 模式三：自定义 Toast 使用 Activity Context

```java
// Android 11+ 系统 Toast 已修复此问题，但自定义 Toast 仍有风险
public void showCustomToast() {
    View toastView = LayoutInflater.from(this).inflate(R.layout.custom_toast, null);
    WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
    WindowManager.LayoutParams params = new WindowManager.LayoutParams(
            WindowManager.LayoutParams.TYPE_APPLICATION_PANEL, /* ... */);
    wm.addView(toastView, params);  // 手动 addView
    // 如果忘记 removeView → 泄漏
}
```

### 3.4 检测手段

| 检测工具 | 原理 | 适用场景 |
|---------|------|---------|
| **logcat 关键字** | 搜索 `"has leaked window"` | 开发/测试阶段快速发现 |
| **StrictMode** | `detectLeakedClosableObjects()` 检测未关闭资源 | 开发阶段 |
| **LeakCanary** | 监控 Activity/Fragment 引用，通过弱引用 + GC 判定泄漏 | 开发/测试阶段 |
| **dumpsys window** | 检查 WindowState 列表中是否有已死进程的窗口 | 线上排查 |
| **线上 OOM 监控** | 内存超标时 dump hprof，分析 ViewRootImpl 引用链 | 线上 |

### 3.5 修复模式

```java
// 推荐：在基类 Activity 中统一管理 Dialog 生命周期
public abstract class BaseActivity extends AppCompatActivity {
    private final List<Dialog> managedDialogs = new ArrayList<>();

    protected void showManagedDialog(Dialog dialog) {
        if (isFinishing() || isDestroyed()) return;
        managedDialogs.add(dialog);
        dialog.setOnDismissListener(d -> managedDialogs.remove(d));
        dialog.show();
    }

    @Override
    protected void onDestroy() {
        for (Dialog dialog : managedDialogs) {
            if (dialog.isShowing()) {
                dialog.dismiss();
            }
        }
        managedDialogs.clear();
        super.onDestroy();
    }
}
```

```java
// 更现代的方案：使用 DialogFragment
public class LoadingDialogFragment extends DialogFragment {
    @NonNull
    @Override
    public Dialog onCreateDialog(@Nullable Bundle savedInstanceState) {
        ProgressDialog dialog = new ProgressDialog(requireContext());
        dialog.setMessage("Loading...");
        return dialog;
    }
    // DialogFragment 自动处理生命周期，Activity 销毁时自动 dismiss
}
```

---

## 4. 黑屏问题分类

黑屏是 Window 系统中**用户感知最强烈的问题**。表面看都是"黑屏"，但根因可能完全不同。根据 Surface 生命周期阶段的不同，可以将黑屏分为五种类型。

### 4.1 黑屏分类全景

```
窗口生命周期与黑屏类型的对应关系：

addWindow()    relayoutWindow()    draw()         SurfaceFlinger     Starting Window
    │               │                │                 │                  │
    │   ┌───────────┤                │                 │                  │
    │   │ 类型1     │                │                 │                  │
    │   │ Surface   │                │                 │                  │
    │   │ 未创建    │                │                 │                  │
    │   └───────────┤                │                 │                  │
    │               │   ┌────────────┤                 │                  │
    │               │   │ 类型3      │                 │                  │
    │               │   │ draw 未完成│                 │                  │
    │               │   └────────────┤                 │                  │
    │               │                │    ┌────────────┤                  │
    │               │                │    │ 类型4      │                  │
    │               │                │    │ 合成异常   │                  │
    │               │                │    └────────────┤                  │
    │               │                │                 │     ┌────────────┤
    │               │                │                 │     │ 类型5      │
    │               │                │                 │     │ 启动窗口   │
    │               │                │                 │     │ 过渡间隙   │
    │               │                │                 │     └────────────┤
    ▼               ▼                ▼                 ▼                  ▼

    类型2: Surface 已销毁（任何阶段的 Surface 被意外回收）
```

### 4.2 类型一：Surface 未创建

**症状：** `addWindow()` 成功但 `relayoutWindow()` 尚未调用或 `createSurfaceLocked()` 失败。窗口在 WMS 中有 `WindowState`，但没有对应的 Surface。

**dumpsys 特征：**

```
Window #0 Window{abc1234 u0 com.example.app/MainActivity}:
    mHasSurface=false       ← 关键标志：Surface 未创建
    mShownPosition=[0,0]
    isReadyForDisplay()=false
    mViewVisibility=0x0     (VISIBLE)
```

**根因分析：**

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java
WindowSurfaceController createSurfaceLocked() {
    final WindowState w = mWin;
    if (mSurfaceController != null) {
        return mSurfaceController;
    }

    // 可能失败的原因：
    // 1. SurfaceFlinger 无响应（Binder 调用超时）
    // 2. fd 耗尽（/proc/pid/fd 数量达到上限）
    // 3. 显存不足（SurfaceFlinger 分配 GraphicBuffer 失败）
    try {
        mSurfaceController = new WindowSurfaceController(
                w.mAttrs.getTitle().toString(),
                width, height, format, flags, this, w.getWindowingMode());
        w.mHasSurface = true;
    } catch (OutOfResourcesException e) {
        w.mHasSurface = false;
        // Surface 创建失败 → 窗口将保持黑屏
        Slog.w(TAG, "OutOfResourcesException creating surface");
        return null;
    }
    return mSurfaceController;
}
```

**Systrace 特征：** `relayoutWindow` 标签耗时异常长（>50ms），或在 `createSurfaceLocked` 处出现长时间 Binder 等待。

**排查方向：**
1. 检查 `dumpsys window` 中 `mHasSurface` 字段
2. 检查 `/proc/<pid>/fd` 数量是否接近上限
3. `dumpsys meminfo surfaceflinger` 检查显存使用量
4. Systrace 中搜索 `createSurface` 检查耗时

### 4.3 类型二：Surface 已销毁

**症状：** Activity 进入后台（`onStop()`）后 Surface 被销毁。重新回到前台时，如果 Surface 重建不及时，会出现短暂或持续黑屏。

**触发场景：**

```
场景 A：低内存时 Surface 被主动回收

T=0s    Activity.onStop() → WindowState visibility = GONE
T=0.5s  WMS: destroySurface() 回收后台 Activity 的 Surface（节省显存）
T=3s    用户切回 Activity → Activity.onStart() / onResume()
T=3.1s  relayoutWindow() → createSurfaceLocked()
        如果 SurfaceFlinger 响应慢 → 短暂黑屏

场景 B：Configuration 变更导致 Surface 销毁重建

T=0ms   旋转 / 折叠 / 分屏触发 Configuration 变更
T=10ms  Activity(old).onDestroy() → removeWindow() → destroySurface()
T=50ms  Activity(new).onCreate() → addWindow()
T=80ms  relayoutWindow() → createSurfaceLocked()
        在 10ms~80ms 的间隙内，屏幕没有有效 Surface → 黑屏
```

**dumpsys 特征：**

```
Window #0 Window{abc1234 u0 com.example.app/MainActivity}:
    mHasSurface=false           ← Surface 已销毁
    mViewVisibility=0x0         (VISIBLE, 但 Surface 不可用)
    mDestroying=false
    mRelayoutCalled=true        (曾经有过 Surface)
```

**排查方向：**
1. Systrace 分析 `destroySurface` 到 `createSurface` 的时间间隙
2. 检查是否有 Configuration 变更触发了 Activity 重建
3. 检查低内存场景下系统是否主动回收了 Surface

### 4.4 类型三：draw 未完成

**症状：** Surface 已创建，但 App 的首帧尚未绘制完成。最典型的场景是 Activity 启动时，`onCreate()` / `onResume()` 中有耗时操作（IO、大量 View 初始化、同步网络请求），导致 `performTraversals()` 中的 `performDraw()` 迟迟未执行。

**这是导致"启动白屏/黑屏"的最常见原因。**

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
private void performTraversals() {
    // ...
    // 第一步：relayoutWindow（获取 Surface）
    relayoutResult = relayoutWindow(params, viewVisibility, insetsPending);

    // 第二步：measure（可能因 View 树复杂而耗时）
    performMeasure(childWidthMeasureSpec, childHeightMeasureSpec);

    // 第三步：layout（同上）
    performLayout(lp, mWidth, mHeight);

    // 第四步：draw（如果前面耗时太久，draw 被延迟 → 黑屏持续）
    if (!cancelAndRedraw) {
        performDraw();  // ← 首帧绘制
    }
    // draw 完成后，WMS 收到 finishDrawingWindow() 通知
    // → WMS 将窗口标记为 drawn → 移除 Starting Window
}
```

**dumpsys 特征：**

```
Window #0 Window{abc1234 u0 com.example.app/MainActivity}:
    mHasSurface=true            ← Surface 已创建
    isDrawn()=false             ← 但尚未绘制完成
    mViewVisibility=0x0
    isReadyForDisplay()=false
```

**Systrace 特征：** `performTraversals` 标签的首次出现耗时远超 16ms（可能 >100ms 甚至 >1s）。

**排查方向：**
1. Systrace 分析首次 `performTraversals` 的耗时分解
2. 检查 `onCreate()` / `onResume()` 中是否有同步 IO 或重量级初始化
3. `adb shell am start -W` 查看 `TotalTime`（TTID）是否异常

### 4.5 类型四：SurfaceFlinger 合成异常

**症状：** App 已完成绘制，WMS 侧 WindowState 状态正常，但 SurfaceFlinger 未能正确将该 Layer 合成到屏幕上。

**可能原因：**

| 原因 | 说明 | 诊断方法 |
|------|------|---------|
| GPU 驱动 Bug | 特定设备的 GPU 驱动在某些条件下无法正确渲染 | 检查 `dumpsys SurfaceFlinger`，确认 Layer 存在但合成结果异常 |
| HWC 合成失败回退 | Hardware Composer 拒绝合成特定 Layer（格式/大小不支持），回退到 GPU 合成 | `dumpsys SurfaceFlinger` 中 `compositionType` 字段 |
| Layer 被错误隐藏 | SurfaceControl.Transaction 设置了 `hide()` 但未正确 `show()` | `dumpsys SurfaceFlinger --list` 检查 Layer 可见性 |
| Buffer 未提交 | App 完成 draw 但 `unlockCanvasAndPost()` 失败 | `dumpsys SurfaceFlinger` 中 Buffer 状态 |

**dumpsys SurfaceFlinger 特征：**

```
Layer: com.example.app/MainActivity#0
  activeBuffer: [1080x2400:1080, RGBA_8888]
  
  queued-frames: 0           ← 如果持续为 0，说明 App 未提交帧
  
  compositionType: CLIENT     ← GPU 合成（可能是 HWC 拒绝）
  
  visible: false              ← Layer 被隐藏
```

### 4.6 类型五：Starting Window 移除后真实窗口未就绪

**症状：** 冷启动时，系统先显示 Starting Window（Splash Screen）。当 Activity 的真实窗口准备就绪后，Starting Window 被移除。如果移除和真实窗口首帧之间存在间隙，用户会看到一闪而过的黑屏。

```
冷启动时序：

T=0ms     zygote fork → Application 创建
T=50ms    WMS: 添加 Starting Window（白底/品牌 logo）    ← 用户看到 Splash
T=200ms   Activity.onCreate() 开始
T=500ms   Activity.onResume() → addView() → addWindow()
T=520ms   relayoutWindow() → Surface 创建
T=600ms   performTraversals() → measure/layout/draw

T=610ms   WMS 收到 finishDrawingWindow()               ← 真实窗口首帧就绪
T=612ms   WMS: removeStartingWindow()                   ← 移除 Starting Window

          正常情况：610ms → 612ms 间隙极短（<1 帧），用户无感知

异常情况：
T=600ms   performDraw() 执行中（复杂布局，耗时 50ms）
T=610ms   WMS 误判窗口已就绪 → 移除 Starting Window
T=650ms   performDraw() 完成，首帧提交

          610ms → 650ms 之间：Starting Window 已移除，
          但真实窗口首帧未提交 → 40ms 黑屏闪烁
```

**排查方向：**
1. Systrace 中搜索 `removeStartingWindow`，对比真实窗口的首帧提交时间
2. 检查 `reportFullyDrawn()` 的调用时机
3. 确认 Starting Window 主题（`windowBackground`）是否配置正确

### 4.7 黑屏诊断决策树

```
黑屏问题诊断决策树：

                        用户报告黑屏
                            │
                ┌───────────┴───────────┐
                │  dumpsys window 检查   │
                │  目标窗口 WindowState  │
                └───────────┬───────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
        WindowState    WindowState    WindowState
         不存在          存在           存在
              │        mHasSurface    mHasSurface
              │          =false         =true
              │             │             │
        addWindow 失败   Surface 问题    │
        检查 Token       │              │
        检查权限      ┌──┴──┐    ┌──────┴──────┐
                     类型1  类型2  isDrawn()    isDrawn()
                  未创建  已销毁   =false        =true
                                    │             │
                               draw 未完成     App 已绘制
                                 类型3         问题在 SF
                               检查首帧          │
                               耗时        dumpsys SF
                                          检查 Layer
                                              │
                                        ┌─────┴─────┐
                                     Layer 存在   Layer 不存在
                                     合成异常      SurfaceControl
                                      类型4       未正确提交
                                    检查 HWC       类型2 变种
```

---

## 5. 窗口焦点丢失与 Input ANR 的关联

窗口焦点丢失是导致 Input ANR 的**最隐蔽原因之一**。与 App 代码导致的主线程阻塞型 ANR 不同，焦点丢失型 ANR 的 App 主线程通常是空闲的——问题出在 WMS 到 InputDispatcher 的焦点同步链路上。

> 焦点管理的详细机制请参阅 [07-WMS 与 Input 焦点管理](07-WMS与Input焦点管理.md)，本节聚焦于焦点丢失导致 ANR 的因果链和排查方法。

### 5.1 焦点与 ANR 的因果链

```
正常链路：
WMS.updateFocusedWindowLocked()
  → InputMonitor.setInputFocusLw(focusedWindow)
    → InputDispatcher::setFocusedWindow(focusedWindow)
      → Key 事件 → focusedWindow → App 处理 → finishInputEvent

焦点丢失链路：
WMS.updateFocusedWindowLocked()
  → computeFocusedWindow() 返回 null（无可聚焦窗口）
    → InputMonitor.setInputFocusLw(null)
      → InputDispatcher::setFocusedWindow(null)
        → Key 事件到达 → 无目标窗口 → 等待...
          → 5 秒超时 → ANR!

InputDispatcher 的等待逻辑：
  // frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
  // findFocusedWindowTargetLocked() 中
  if (focusedWindowHandle == nullptr) {
      if (focusedApplicationHandle != nullptr) {
          // 有 FocusedApplication 但没有 FocusedWindow
          // → 等待窗口出现，超时 = 5 秒
          return InputEventInjectionResult::PENDING;
      }
      // 没有 FocusedApplication → 丢弃事件
      return InputEventInjectionResult::FAILED;
  }
```

### 5.2 四种焦点丢失场景

#### 场景一：Dialog dismiss 后焦点未及时回到 Activity

```
时序：
T=0ms    Dialog 显示中，Dialog 持有焦点
T=100ms  Dialog.dismiss() → removeWindow()
T=101ms  WMS: updateFocusedWindowLocked()
         → computeFocusedWindow() 遍历窗口树
         
         在极端情况下（WMS 锁竞争激烈），
         焦点更新可能延迟 → 存在短暂的"焦点空窗期"

T=102ms  用户按下 Home 键
         → InputDispatcher: focusedWindow == null
         → 等待 focusedWindow...
         → 如果 5 秒内焦点未恢复 → ANR
```

**排查命令：**

```bash
# 检查当前焦点窗口
adb shell dumpsys window | grep -i "mCurrentFocus"
adb shell dumpsys window | grep -i "mFocusedApp"

# 检查 InputDispatcher 侧的焦点
adb shell dumpsys input | grep -i "FocusedApplications"
adb shell dumpsys input | grep -i "FocusedWindows"
```

#### 场景二：多窗口模式焦点竞争

分屏/自由窗口模式下，多个 Activity 同时可见。焦点在窗口间切换时，如果 WMS 的焦点计算与用户触摸的窗口不一致，会导致 Key 事件路由错误。

```
分屏模式下的焦点竞争：

┌─────────────────────────┐
│   Activity A (顶部)     │  ← mCurrentFocus 可能指向 A
├─────────────────────────┤
│   Activity B (底部)     │  ← 用户触摸 B，但焦点还在 A
└─────────────────────────┘

用户触摸 B → WMS 更新焦点到 B → InputMonitor 同步
→ 但在同步完成之前，Key 事件仍发给 A
```

#### 场景三：Activity 转场焦点间隙

Activity 从 A 切换到 B 时，存在一个关键的焦点间隙：

```
Activity 切换焦点时序：

T=0ms    AMS: pauseActivity(A)
T=5ms    WMS: A 的窗口标记为 not-focusable
T=5ms    WMS: updateFocusedWindowLocked()
         → computeFocusedWindow() = null（B 尚未创建窗口）
         → FocusedWindow = null                              ← 焦点空窗期开始

T=10ms   AMS: resumeActivity(B)
T=50ms   B.onCreate() / B.onResume()
T=60ms   B: addView() → addWindow()
T=65ms   WMS: updateFocusedWindowLocked()
         → computeFocusedWindow() = B 的窗口
         → FocusedWindow = B                                 ← 焦点空窗期结束

焦点空窗期 = T=5ms ~ T=65ms = 60ms
在此期间的 Key 事件将等待 FocusedWindow → 如果启动慢（>5s）→ ANR
```

#### 场景四：IME 窗口焦点干扰

输入法窗口（`TYPE_INPUT_METHOD`）的焦点行为比较特殊。IME 窗口本身不接收 Key 事件（由 IME Service 直接处理），但 IME 的显示/隐藏会触发焦点重新计算：

```
IME 焦点干扰场景：

T=0ms    Activity 持有焦点，用户点击 EditText
T=5ms    IME 弹出 → WMS: addWindow(TYPE_INPUT_METHOD)
T=10ms   WMS: updateFocusedWindowLocked()
         → IME 窗口不可聚焦（FLAG_NOT_FOCUSABLE）
         → 焦点仍在 Activity 窗口 ← 正常

异常场景：
T=0ms    Activity 持有焦点
T=5ms    IME 弹出
T=8ms    Activity 配置变更（如旋转）→ 窗口重建
T=10ms   WMS: 旧 Activity 窗口移除
T=12ms   WMS: updateFocusedWindowLocked()
         → 旧窗口已移除，新窗口未创建
         → FocusedWindow = null                 ← 焦点丢失
T=15ms   IME 窗口仍显示，但焦点为空
         → Key 事件（包括软键盘输入）无法送达
```

### 5.3 焦点丢失诊断核心命令

```bash
# 命令组合：同时检查 WMS 和 InputDispatcher 两侧的焦点状态

# 1. WMS 侧焦点
adb shell dumpsys window | grep -E "mCurrentFocus|mFocusedApp|mLastFocus"
# 预期输出：
#   mCurrentFocus=Window{xxx com.example.app/MainActivity}
#   mFocusedApp=ActivityRecord{xxx com.example.app/.MainActivity}

# 2. InputDispatcher 侧焦点
adb shell dumpsys input | grep -E "FocusedApplications|FocusedWindows"
# 预期输出：
#   FocusedApplications:
#     displayId=0, name='ActivityRecord{xxx com.example.app/.MainActivity}'
#   FocusedWindows:
#     displayId=0, name='xxx com.example.app/MainActivity'

# 3. 对比两侧焦点是否一致
# 如果 WMS 侧有焦点但 InputDispatcher 侧没有 → InputMonitor 同步延迟
# 如果两侧都没有焦点 → computeFocusedWindow 返回 null
```

**焦点不一致时的进一步排查：**

```bash
# 检查所有窗口的 focusable 属性
adb shell dumpsys window windows | grep -E "Window #|mAttrs.flags|canReceiveKeys"

# 检查 InputMonitor 最近的更新时间
adb shell dumpsys window | grep -i "inputMonitor"
```

---

## 6. 模式识别速查表

以下表格覆盖了 Window 系统中最常见的 14 种问题现象，帮助在**5 分钟内定位问题类型和排查方向**。

| 问题现象 | 问题类型 | logcat 特征 | dumpsys window 特征 | dumpsys input 特征 | 排查方向 |
|---------|---------|------------|--------------------|--------------------|---------|
| `BadTokenException` Crash（token not valid） | Crash 类 | `Unable to add window -- token ... is not valid; is your activity running?` | 目标 Activity 的 WindowToken 不存在 | — | 检查 `isFinishing()/isDestroyed()`；异步回调时序 |
| `BadTokenException` Crash（not for an application） | Crash 类 | `Unable to add window -- token ... is not for an application` | — | — | 检查 Context 类型：是否用了 Application/Service Context 创建 Dialog |
| `BadTokenException` Crash（permission denied） | Crash 类 | `Unable to add window ... permission denied for window type` | — | — | 检查 `SYSTEM_ALERT_WINDOW` 权限；Android 版本兼容 |
| `WindowLeaked` 警告 | 资源泄漏 | `Activity xxx has leaked window DecorView@xxx` | — | — | `onDestroy()` 中未 dismiss Dialog/PopupWindow；用 LeakCanary 确认泄漏链 |
| 黑屏（Surface 未创建） | 显示异常 | 可能有 `OutOfResourcesException` | `mHasSurface=false`, `isReadyForDisplay()=false` | — | 检查 fd 数量、显存；`relayoutWindow` 是否被调用 |
| 黑屏（Surface 已销毁） | 显示异常 | — | `mHasSurface=false`, `mRelayoutCalled=true` | — | 检查 Configuration 变更；低内存 Surface 回收；Systrace 时序 |
| 黑屏（draw 未完成） | 显示异常 | `Displayed` 日志延迟或缺失 | `mHasSurface=true`, `isDrawn()=false` | — | Systrace 分析 `performTraversals` 耗时；`onCreate` 重量级操作 |
| 黑屏（SF 合成异常） | 显示异常 | 可能有 `HWC` 或 `SurfaceFlinger` 错误 | `mHasSurface=true`, `isDrawn()=true` | — | `dumpsys SurfaceFlinger`：Layer 可见性、合成类型、Buffer 状态 |
| 黑屏（Starting Window 间隙） | 显示异常 | `removeStartingWindow` 时间早于 `Displayed` | — | — | Systrace 对比 `removeStartingWindow` 与首帧提交时间 |
| 焦点丢失（界面正常但无响应） | ANR 类 | `no focused window` 或 `Waiting because no window has focus` | `mCurrentFocus=null` | `FocusedWindows: <none>` | 对比 WMS 与 InputDispatcher 焦点；检查 Activity 切换时序 |
| 窗口闪烁 | 显示异常 | 频繁的 `relayoutWindow` / `addWindow` / `removeWindow` | 短时间内窗口频繁添加/移除 | — | 检查是否有循环创建/销毁窗口的逻辑；Configuration 变更循环 |
| 触摸穿透 | 显示异常 | — | 顶层窗口的 `mAttrs.flags` 包含 `FLAG_NOT_TOUCHABLE` | `touchableRegion` 为空或不覆盖窗口区域 | 检查 `LayoutParams.flags`；`touchableRegion` 设置；`InputMonitor` 同步 |
| 窗口不显示（无黑屏，窗口区域透明） | 显示异常 | — | `mViewVisibility=0x8` (GONE) 或 `mViewVisibility=0x4` (INVISIBLE) | — | 检查 `setVisibility()` 调用；`WindowManager.LayoutParams` 的 `alpha` 值 |
| Surface 泄漏（内存持续增长） | 资源泄漏 | — | 已死进程的 WindowState 仍存在 | — | `dumpsys SurfaceFlinger --list` 对比 Layer 数量变化；`dumpsys meminfo surfaceflinger` |

**使用方法：**

1. 根据用户报告的现象，在"问题现象"列定位
2. 查看"logcat 特征"和"dumpsys 特征"进行初步确认
3. 按"排查方向"深入分析

---

## 7. 实战案例

### Case 1：线上 BadTokenException 突增 — SDK 升级导致异步回调时序变化

**背景：** 某电商 App 在一次版本发布后，线上 BadTokenException 日均量从 200 次激增到 5000 次。异常堆栈指向支付结果 Dialog 的 `show()` 调用。

**异常堆栈：**

```
android.view.WindowManager$BadTokenException:
    Unable to add window -- token android.os.BinderProxy@e3f4a5b is not valid;
    is your activity running?
    at android.view.ViewRootImpl.setView(ViewRootImpl.java:1024)
    at android.view.WindowManagerGlobal.addView(WindowManagerGlobal.java:393)
    at android.app.Dialog.show(Dialog.java:342)
    at com.example.pay.PayResultHandler.showResultDialog(PayResultHandler.java:87)
    at com.example.pay.PayResultHandler.onPayResult(PayResultHandler.java:63)
    at com.example.pay.PaySDK$CallbackWrapper.lambda$onResult$0(PaySDK.java:156)
    at android.os.Handler.handleCallback(Handler.java:938)
```

**排查过程：**

**第一步：对比版本差异**

本次发版升级了支付 SDK（v2.3 → v3.0）。对比两个版本的回调行为：

```java
// v2.3 的支付回调（同步，在主线程直接回调）
public class PaySDK_v2 {
    void startPay(PayParams params, PayCallback callback) {
        // ... 支付流程 ...
        // 支付结果直接在主线程回调（Activity 生命周期内）
        callback.onResult(result);
    }
}

// v3.0 的支付回调（异步，通过 Handler.post 延迟回调）
public class PaySDK_v3 {
    void startPay(PayParams params, PayCallback callback) {
        // ... 支付流程 ...
        // 支付结果通过 Handler.post 异步回调
        new Handler(Looper.getMainLooper()).post(() -> {
            callback.onResult(result);  // ← 延迟执行
        });
    }
}
```

**第二步：还原时序问题**

```
v2.3 时序（安全）：
T=0s    用户点击支付
T=2s    支付结果返回
T=2s    onResult() 直接回调 → showResultDialog()
        此时 Activity 一定存活（因为同步回调在 Activity 的 Binder 调用链中）

v3.0 时序（危险）：
T=0s    用户点击支付
T=2s    支付结果返回
T=2s    Handler.post(onResult)    ← 消息入队
T=2.1s  用户按返回键 → Activity.finish()
T=2.2s  AMS → WMS: 清理 ActivityRecord token
T=2.3s  Handler 处理消息 → onResult() → showResultDialog()
        → addWindow() → token 不存在 → BadTokenException!
```

**根因：** SDK 从同步回调改为异步回调（`Handler.post`），引入了 Activity 生命周期与回调执行之间的时序窗口。在这个窗口内用户退出 Activity，就会触发 BadTokenException。

**业务代码缺陷：**

```java
// com.example.pay.PayResultHandler.java（问题代码）
public class PayResultHandler {
    private final Activity activity;

    public void onPayResult(PayResult result) {
        // 缺少 Activity 状态检查
        showResultDialog(result);
    }

    private void showResultDialog(PayResult result) {
        new AlertDialog.Builder(activity)
            .setTitle(result.isSuccess() ? "支付成功" : "支付失败")
            .setMessage(result.getMessage())
            .setPositiveButton("确定", null)
            .show();  // Activity 可能已销毁 → Crash
    }
}
```

**修复方案：**

```java
// 修复后
public class PayResultHandler implements DefaultLifecycleObserver {
    private final AppCompatActivity activity;
    private PayResult pendingResult;

    public PayResultHandler(AppCompatActivity activity) {
        this.activity = activity;
        activity.getLifecycle().addObserver(this);
    }

    public void onPayResult(PayResult result) {
        if (activity.getLifecycle().getCurrentState().isAtLeast(
                Lifecycle.State.RESUMED)) {
            showResultDialog(result);
        } else {
            pendingResult = result;
        }
    }

    @Override
    public void onResume(@NonNull LifecycleOwner owner) {
        if (pendingResult != null) {
            showResultDialog(pendingResult);
            pendingResult = null;
        }
    }

    @Override
    public void onDestroy(@NonNull LifecycleOwner owner) {
        pendingResult = null;
        activity.getLifecycle().removeObserver(this);
    }

    private void showResultDialog(PayResult result) {
        if (activity.isFinishing() || activity.isDestroyed()) return;
        new AlertDialog.Builder(activity)
            .setTitle(result.isSuccess() ? "支付成功" : "支付失败")
            .setMessage(result.getMessage())
            .setPositiveButton("确定", null)
            .show();
    }
}
```

**治理措施：**

1. **代码审查规则**：所有 SDK 升级需检查回调线程模型是否变化
2. **Lint 规则**：检测 `Dialog.show()` 前是否有 `isFinishing()` 检查
3. **自动化测试**：在 Dialog 显示的异步路径上，模拟 Activity 销毁场景
4. **线上监控**：BadTokenException 按 Activity 和调用栈聚合，突增时自动告警

---

### Case 2：折叠屏展开后黑屏 — Configuration 变更与 Surface 重建时序

**背景：** 某 App 在三星 Galaxy Z Fold 系列设备上，用户从折叠态展开到平板态时，约 3% 的概率出现黑屏。黑屏持续 2-5 秒后自行恢复。

**现象：**
- 折叠→展开时黑屏
- 展开→折叠不出现
- logcat 无 Crash 日志
- `dumpsys window` 显示 `mHasSurface=true` 但 `isDrawn()=false`

**排查过程：**

**第一步：理解折叠屏的 Configuration 变更链路**

```
折叠屏展开触发的 Configuration 变更链：

DisplayManagerService
  → 检测到屏幕变化（密度、尺寸、方向可能同时改变）
    → WMS: onDisplayChanged()
      → DisplayContent: 更新 DisplayInfo
        → AMS: updateConfiguration()
          → Activity: 根据 configChanges 声明决定是否重建

如果 Activity 未声明 configChanges="screenSize|screenLayout|smallestScreenSize|density"：
  → Activity 销毁 → 窗口销毁 → Surface 销毁
  → Activity 重建 → 窗口创建 → Surface 创建 → draw
  → 在此过程中，屏幕无有效内容 → 黑屏
```

**第二步：Systrace 时序分析**

通过 Perfetto 抓取折叠屏展开过程的 Trace：

```
T=0ms      屏幕状态变更事件
T=5ms      DisplayManagerService: onDisplayChanged
T=10ms     WMS: handleDisplayChanged → 新的 DisplayInfo (宽/高/密度变化)
T=15ms     AMS: updateConfiguration → 触发 Activity 重建

T=20ms     Activity(old).onPause()
T=25ms     Activity(old).onStop()
T=30ms     Activity(old).onSaveInstanceState()
T=35ms     Activity(old).onDestroy()
T=40ms     WMS: removeWindow() → destroySurface()       ← 旧 Surface 销毁

T=45ms     Activity(new).onCreate()
           → setContentView() → 复杂布局 inflate（耗时 200ms!）
T=245ms    Activity(new).onStart()
T=250ms    Activity(new).onResume()
T=255ms    addView() → addWindow()                      ← 窗口创建
T=260ms    relayoutWindow() → createSurfaceLocked()     ← 新 Surface 创建

T=265ms    performTraversals() 开始
           → performMeasure(): 复杂布局测量（耗时 150ms!）
T=415ms    → performLayout(): 布局计算（耗时 50ms）
T=465ms    → performDraw(): 首帧绘制（耗时 80ms）
T=545ms    finishDrawingWindow()                        ← 首帧完成

黑屏持续时间 = T=40ms(旧 Surface 销毁) ~ T=545ms(新首帧完成) = 505ms!
```

**第三步：根因定位**

黑屏 505ms 的组成分析：

```
黑屏时间分解：

40ms~45ms     Surface 销毁到 Activity 重建开始         5ms   (系统开销)
45ms~245ms    Activity.onCreate() 中布局 inflate     200ms  ← 主因 1
245ms~265ms   onResume → addWindow → Surface 创建    20ms   (系统开销)
265ms~545ms   performTraversals (measure+layout+draw) 280ms ← 主因 2
                                                     ─────
                                                     505ms  总黑屏时间
```

**问题根因：**

1. **布局 inflate 耗时过长（200ms）：** Activity 的 XML 布局包含深层嵌套的 RecyclerView + 复杂 ItemView，折叠屏展开后屏幕面积翻倍，View 数量也翻倍
2. **首帧 measure/layout/draw 耗时过长（280ms）：** 展开态分辨率从 840×2080 变为 1812×2176，渲染面积大幅增加
3. **Activity 未声明 `configChanges`：** 导致完整的销毁→重建流程

**dumpsys 确认：**

```bash
# 黑屏期间执行
adb shell dumpsys window | grep -A 5 "com.example.app/MainActivity"
```

```
Window #0 Window{def5678 u0 com.example.app/MainActivity}:
    mHasSurface=true
    isDrawn()=false          ← Surface 已创建但首帧未完成
    isReadyForDisplay()=false
    mViewVisibility=0x0      (VISIBLE)
    mLastFrameNumber=0       ← 尚未提交任何帧
```

**修复方案：**

```java
// 方案一：声明 configChanges，避免 Activity 重建
// AndroidManifest.xml
<activity
    android:name=".MainActivity"
    android:configChanges="screenSize|screenLayout|smallestScreenSize|density|orientation"
/>

// Activity 中处理配置变更
@Override
public void onConfigurationChanged(@NonNull Configuration newConfig) {
    super.onConfigurationChanged(newConfig);
    // 手动调整布局，无需销毁重建
    adjustLayoutForConfiguration(newConfig);
}
```

```java
// 方案二：优化布局 inflate 和首帧渲染
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 先设置一个轻量级占位布局
        setContentView(R.layout.activity_main_skeleton);

        // 延迟加载复杂内容
        getWindow().getDecorView().post(() -> {
            ViewStub contentStub = findViewById(R.id.content_stub);
            contentStub.inflate();
            bindData();
        });
    }
}
```

```java
// 方案三：保持 Starting Window 直到首帧就绪
// 在 styles.xml 中配置窗口背景，与 App 主色调一致
// 这样即使黑屏期间，用户看到的也是品牌色而非纯黑
<style name="AppTheme" parent="Theme.MaterialComponents.DayNight">
    <item name="android:windowBackground">@color/brand_primary</item>
</style>
```

**复盘总结：**

| 维度 | 分析 |
|------|------|
| **直接原因** | 折叠屏展开触发 Activity 重建，旧 Surface 销毁到新首帧完成之间的 505ms 间隙导致黑屏 |
| **根本原因** | 布局复杂度过高 + 未声明 `configChanges` |
| **为什么 3% 复现率** | 取决于设备性能和系统负载；高负载时 inflate 和 measure 更慢，黑屏时间更长，超过用户感知阈值（~200ms）才会报告 |
| **预防措施** | 折叠屏适配检查清单 + 布局复杂度 Lint + 首帧耗时监控 |

---

## 总结

Window 系统的稳定性风险贯穿 App → WMS → SurfaceFlinger 三层架构。作为稳定性工程师，排查 Window 问题的核心方法论：

**1. 分层定位：确定问题在哪一层**

```
表现层（用户看到什么）
  → Crash？黑屏？ANR？闪烁？
    → 对应 App 层 / WMS 层 / SurfaceFlinger 层

排查入口：
  Crash  → logcat 异常堆栈 → 源码 Token 校验逻辑
  黑屏   → dumpsys window (mHasSurface/isDrawn)
         → dumpsys SurfaceFlinger (Layer 状态)
  ANR    → dumpsys input (FocusedWindow)
         → dumpsys window (mCurrentFocus)
  泄漏   → dumpsys SurfaceFlinger --list (Layer 数量)
         → LeakCanary / hprof 分析
```

**2. 核心诊断命令**

| 场景 | 命令 |
|------|------|
| 窗口状态全景 | `adb shell dumpsys window windows` |
| 焦点检查 | `adb shell dumpsys window \| grep -i focus` |
| 窗口层级树 | `adb shell dumpsys window containers` |
| Input 侧焦点 | `adb shell dumpsys input \| grep -i focus` |
| Surface/Layer 状态 | `adb shell dumpsys SurfaceFlinger --list` |
| 显存占用 | `adb shell dumpsys meminfo surfaceflinger` |
| 时序分析 | `perfetto` / `systrace -t 5 wm view input gfx` |

**3. 风险防御优先级**

```
高优先级治理（覆盖 80% 的问题）：
├── BadTokenException 防御
│     → isFinishing()/isDestroyed() 检查 + Lifecycle 感知
├── WindowLeaked 防御
│     → onDestroy() 中 dismiss 所有 Dialog + 基类封装
└── 焦点丢失监控
      → dumpsys input 焦点状态定期采集 + ANR 聚合分析

中优先级治理：
├── 黑屏防御
│     → 首帧耗时监控 (TTID) + configChanges 声明
└── Surface 泄漏检测
      → Layer 数量定期采集 + 异常增长告警
```

---

## 附录：核心源码路径索引

| 文件 | 完整路径 | 与本文的关联 |
|------|---------|-------------|
| WindowManagerService.java | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | `addWindow()` Token 校验逻辑（BadTokenException 根因） |
| ViewRootImpl.java | `frameworks/base/core/java/android/view/ViewRootImpl.java` | `setView()` 中抛出 BadTokenException；`performTraversals()` 首帧绘制 |
| WindowManagerGlobal.java | `frameworks/base/core/java/android/view/WindowManagerGlobal.java` | `closeAll()` WindowLeaked 检测逻辑 |
| ActivityThread.java | `frameworks/base/core/java/android/app/ActivityThread.java` | `handleDestroyActivity()` 触发 WindowLeaked 检查 |
| WindowState.java | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | `mHasSurface` 字段（黑屏排查关键） |
| WindowStateAnimator.java | `frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java` | `createSurfaceLocked()` Surface 创建（类型一黑屏） |
| WindowToken.java | `frameworks/base/services/core/java/com/android/server/wm/WindowToken.java` | Token 管理与校验 |
| ActivityRecord.java | `frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java` | Activity 的 WMS 表示；`finishing` 状态与 Token 清理 |
| DisplayContent.java | `frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java` | `findFocusedWindow()` 焦点计算；`removeToken()` Token 移除 |
| DisplayPolicy.java | `frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java` | `checkAddPermission()` 权限校验 |
| InputMonitor.java | `frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java` | WMS→InputDispatcher 焦点同步 |
| InputDispatcher.cpp | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` | `findFocusedWindowTargetLocked()` 焦点 ANR 判定 |
| SurfaceFlinger.cpp | `frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp` | Layer 创建与合成（类型四黑屏） |
| SurfaceControl.java | `frameworks/base/core/java/android/view/SurfaceControl.java` | Surface 操作 Java 封装 |
| Activity.java | `frameworks/base/core/java/android/app/Activity.java` | `isFinishing()` / `isDestroyed()` 生命周期状态 |

---

**跨系列引用：**

- 焦点管理的详细机制，详见 [07-WMS 与 Input 焦点管理](07-WMS与Input焦点管理.md)
- WMS 锁竞争与 Watchdog 超时，详见 [10-WMS 锁竞争与 Watchdog](10-WMS锁竞争与Watchdog.md)
- Surface 生命周期与 SurfaceFlinger 交互，详见 [05-Surface 管理与 SurfaceFlinger 交互](05-Surface管理与SurfaceFlinger交互.md)
- Input ANR 的触发与裁决流程，详见 [Input 系列-06-Input ANR](../Input/06-InputANR.md)

---

下一篇 [10-WMS 锁竞争与 Watchdog](10-WMS锁竞争与Watchdog.md) 将深入分析 WMS 的 `mGlobalLock` 竞争问题——这是导致 system_server 被 Watchdog 杀死的首要原因之一。我们将剖析锁的持有者图谱、级联阻塞效应、死锁场景，以及如何从 `traces.txt` 中还原锁链并定位根因。
