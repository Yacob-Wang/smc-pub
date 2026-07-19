# 05-View 事件分发：从 ViewRootImpl 到触摸响应

> **系列**：面向稳定性的 Android Input 子系统深度解析系列(Input_FWK)
>
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
>
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `frameworks/base/core/java/android/view/ViewRootImpl.java`、`frameworks/base/core/java/android/view/ViewGroup.java`;Android 14 NestedScrolling 优化见 §4)
>
> **目标读者**:Android 稳定性框架架构师
>
> **前置阅读**:[01-Input 系统总览](01-Input系统总览.md) / [04-InputChannel](04-InputChannel与跨进程投递.md)
>
> **下一篇**:[06-Input ANR](06-InputANR.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 5 篇(View 事件分发,App 消费侧)
- **强依赖**:
  - [01-Input 系统总览](01-Input系统总览.md) §3 五层架构(本篇聚焦 Layer 5)
  - [04-InputChannel](04-InputChannel与跨进程投递.md)(本篇消费 InputChannel 投递的事件)
- **承接自**:04 已讲跨进程传输。本篇深入 App 内 View 树
- **衔接去**:06 ANR 触发 + 07 风险全景
- **不重复内容**:InputChannel 传输细节详见 04;ANR 判定详见 06

#### §0 锚点案例的可验证 4 件套:自定义 ViewGroup dispatchTouchEvent 死循环导致 ANR

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某 IM App v6.5(脱敏代号 `ChatApp`,自定义 NestedScrollingParent)
> - 工具:`dumpsys gfxinfo` + `simpleperf -e sched:sched_blocked_reason` + `dumpsys input` + `traceView`

> **复现步骤**:
> 1. 工厂重置,安装 ChatApp v6.5,打开聊天列表
> 2. 上下快速滑动列表 → 5s 后触发 ANR
> 3. `adb shell input swipe 500 1000 500 200 100` 复现
> 4. `simpleperf record -g -e sched:sched_blocked_reason --duration 10` 抓 trace
> 5. `/data/anr/anr_*.txt` 看堆栈

> **logcat / ANR trace 关键片段**:
> ```
> # ANR dump
> ANR in com.chat.app
> Reason: Input dispatching timed out (Application Not Responding)
> "main" prio=5 tid=14 Blocked
>   | state=D schedstat=( 1248012345 4823012345 ) utm=8230 stm=12480 core=0
>   | stack=0x7fc00000-0x7fd00000
>   ...
>   #00  android.view.ViewGroup.dispatchTouchEvent()
>   #01  android.view.ViewGroup.dispatchTouchEvent()
>   #02  android.view.ViewGroup.dispatchTouchEvent()    ← 递归 200 层
>   #03  android.view.ViewGroup.dispatchTouchEvent()
>   ...
>   #198 android.view.ViewGroup.dispatchTouchEvent()
>   #199 android.view.ViewGroup.dispatchTouchEvent()
>   ↳ StackOverflowError 风险
> # 根因:自定义 NestedScrollingParent 在 onNestedScroll 中反向 dispatchTouchEvent 导致递归
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/app/src/main/java/com/chat/app/widget/NestedScrollContainer.java
> +++ b/app/src/main/java/com/chat/app/widget/NestedScrollContainer.java
> @@ onInterceptTouchEvent
> -    // 旧版:父 View 拦截后又 dispatch 给子 View,造成递归
> -    @Override
> -    public boolean onInterceptTouchEvent(MotionEvent ev) {
> -        if (shouldIntercept(ev)) {
> -            return dispatchTouchEvent(ev);  // ❌ 错误!递归调用
> -        }
> -        return false;
> -    }
> +    // 修复:正确实现 onInterceptTouchEvent,只在需要时返回 true,不递归 dispatch
> +    @Override
> +    public boolean onInterceptTouchEvent(MotionEvent ev) {
> +        if (shouldIntercept(ev)) {
> +            return true;   // 标记拦截,事件将传给 onTouchEvent
> +        }
> +        return false;
> +    }
> +    @Override
> +    public boolean onTouchEvent(MotionEvent ev) {
> +        // 处理拦截到的事件
> +        handleScroll(ev);
> +        return true;
> +    }
> ```
> 完整 View 分发机制 ↔ dispatchTouchEvent ↔ onInterceptTouchEvent ↔ ANR 触发链路见 §2 §3 §4 §6。

## 引言

在 Input 五层架构中，View 事件分发是**最后一站**——事件已经穿越了 Kernel Driver、EventHub、InputReader、InputDispatcher、InputChannel，终于抵达 App 进程。此刻，它面对的不再是系统组件，而是一棵由数十乃至数百个 View 组成的视图树。

**事件分发解决的核心问题**：
- 一个触摸坐标 (x, y) 应该交给哪个 View 处理？
- 父 View（ViewGroup）和子 View 之间如何协商事件的归属？
- 一个完整的事件序列（DOWN → MOVE → UP）如何保持接收者的一致性？

对稳定性架构师而言，这一层的重要性在于：
- `onTouchEvent` 中的耗时操作 → 阻塞主线程 → `finishInputEvent` 延迟 → **Input ANR**
- 事件拦截冲突 → 滑动失效 / 点击无响应 → **用户体验**
- View 树过深 → `dispatchTouchEvent` 递归层级过深 → **分发耗时增大**

本文将从 ViewRootImpl 接收事件开始，逐步深入到 View 树分发的核心三方法，解析事件序列、TouchTarget、滑动冲突解决方案，并最终关联稳定性风险。

---

## 1. 从 InputChannel 到 ViewRootImpl：事件入口

### 1.1 WindowInputEventReceiver：事件的第一站

事件通过 InputChannel（Unix Domain Socket）到达 App 进程后，由 `WindowInputEventReceiver` 接收。这个类定义在 ViewRootImpl 内部：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
final class WindowInputEventReceiver extends InputEventReceiver {
    @Override
    public void onInputEvent(InputEvent event) {
        enqueueInputEvent(event, this, 0, true);
    }

    @Override
    public void onBatchedInputEventPending(int source) {
        if (mUnbufferedInputDispatch) {
            // 不合并，立即消费
            consumeBatchedInputEvents(-1);
        } else {
            // 安排在下一帧消费
            scheduleConsumeBatchedInput();
        }
    }
}
```

> **源码路径**：`frameworks/base/core/java/android/view/ViewRootImpl.java`

两个关键入口：
- `onInputEvent`：单个事件到达时调用
- `onBatchedInputEventPending`：多个 MOVE 事件合并（batching）时调用，通常会安排到下一个 VSync 帧统一消费

### 1.2 enqueueInputEvent：事件入队

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
void enqueueInputEvent(InputEvent event, InputEventReceiver receiver,
        int flags, boolean processImmediately) {
    QueuedInputEvent q = obtainQueuedInputEvent(event, receiver, flags);

    QueuedInputEvent last = mPendingInputEventTail;
    if (last == null) {
        mPendingInputEventHead = q;
        mPendingInputEventTail = q;
    } else {
        last.mNext = q;
        mPendingInputEventTail = q;
    }
    mPendingInputEventCount += 1;

    if (processImmediately) {
        doProcessInputEvents();
    } else {
        scheduleProcessInputEvents();
    }
}
```

事件被包装为 `QueuedInputEvent` 加入链表。如果 `processImmediately` 为 true（通常是），立即调用 `doProcessInputEvents()`。

### 1.3 doProcessInputEvents → deliverInputEvent

```java
void doProcessInputEvents() {
    while (mPendingInputEventHead != null) {
        QueuedInputEvent q = mPendingInputEventHead;
        mPendingInputEventHead = q.mNext;
        if (mPendingInputEventHead == null) {
            mPendingInputEventTail = null;
        }
        q.mNext = null;
        mPendingInputEventCount -= 1;
        deliverInputEvent(q);
    }
    // ...
}
```

`deliverInputEvent` 是将事件送入 **InputStage 管线** 的入口。

---

## 2. InputStage 管线：责任链模式

### 2.1 管线架构

ViewRootImpl 在初始化时构建了一条 InputStage 管线，采用**责任链模式**（Chain of Responsibility）：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java — setView()
mSyntheticInputStage = new SyntheticInputStage();
InputStage viewPostImeStage = new ViewPostImeInputStage(mSyntheticInputStage);
InputStage nativePostImeStage = new NativePostImeInputStage(viewPostImeStage, ...);
InputStage earlyPostImeStage = new EarlyPostImeInputStage(nativePostImeStage);
InputStage imeStage = new ImeInputStage(earlyPostImeStage, ...);
InputStage viewPreImeStage = new ViewPreImeInputStage(imeStage);
InputStage nativePreImeStage = new NativePreImeInputStage(viewPreImeStage, ...);
mFirstInputStage = nativePreImeStage;
mFirstPostImeInputStage = earlyPostImeStage;
```

### 2.2 七个 Stage 的职责

| Stage | 职责 | 稳定性关联 |
| :--- | :--- | :--- |
| **NativePreImeInputStage** | Native 层预处理（无障碍等） | 通常耗时极短 |
| **ViewPreImeInputStage** | 在 IME 处理前给 View 一次机会（`dispatchKeyEventPreIme`） | 仅处理 KEY 事件 |
| **ImeInputStage** | 输入法处理：将按键事件发给 IME | IME 响应慢 → 按键延迟 |
| **EarlyPostImeInputStage** | IME 处理后的早期处理（系统快捷键如 Back/Home） | 系统手势拦截 |
| **NativePostImeInputStage** | Native 层后处理 | 通常耗时极短 |
| **ViewPostImeInputStage** | **核心**：调用 `mView.dispatchPointerEvent()` 开始 View 树分发 | 事件分发的主战场 |
| **SyntheticInputStage** | 合成事件（TrackBall → Touch 转换等） | 边缘场景 |

### 2.3 ViewPostImeInputStage — 事件进入 View 树的入口

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
final class ViewPostImeInputStage extends InputStage {
    @Override
    protected int onProcess(QueuedInputEvent q) {
        if (q.mEvent instanceof KeyEvent) {
            return processKeyEvent(q);
        } else {
            final int source = q.mEvent.getSource();
            if ((source & InputDevice.SOURCE_CLASS_POINTER) != 0) {
                return processPointerEvent(q);
            }
            // ...
        }
    }

    private int processPointerEvent(QueuedInputEvent q) {
        final MotionEvent event = (MotionEvent) q.mEvent;
        // mView 就是 DecorView
        boolean handled = mView.dispatchPointerEvent(event);
        // ...
        return handled ? FINISH_HANDLED : FORWARD;
    }
}
```

`mView` 是 `DecorView`（Activity 窗口的根 View），`dispatchPointerEvent` 最终调用 `dispatchTouchEvent`。

### 2.4 每个 Stage 的处理结果

每个 Stage 返回三种状态之一：
- `FINISH_HANDLED`：事件已被消费，停止传递
- `FINISH_NOT_HANDLED`：事件未被消费，停止传递
- `FORWARD`：事件未被当前 Stage 处理，传递给下一个 Stage

当所有 Stage 处理完后（或某个 Stage 返回 FINISH），ViewRootImpl 调用 `finishInputEvent`，通过 InputChannel 告知 InputDispatcher 事件已处理。**这个回复直接关联 ANR 检测——回复越慢，ANR 风险越高。**

---

## 3. View 树的事件分发机制

### 3.1 核心三方法

View 事件分发围绕三个核心方法展开：

| 方法 | 所在类 | 职责 |
| :--- | :--- | :--- |
| `dispatchTouchEvent(MotionEvent)` | ViewGroup / View | 分发入口 |
| `onInterceptTouchEvent(MotionEvent)` | ViewGroup | 决定是否拦截事件 |
| `onTouchEvent(MotionEvent)` | View | 消费事件 |

调用关系的伪代码：

```
ViewGroup.dispatchTouchEvent(event):
    if onInterceptTouchEvent(event) == true:
        return self.onTouchEvent(event)  // 拦截，自己处理
    else:
        for child in children (reverse Z-order):
            if child.dispatchTouchEvent(event) == true:
                return true  // 子 View 消费了
        return self.onTouchEvent(event)  // 没有子 View 消费，自己处理
```

### 3.2 ViewGroup.dispatchTouchEvent() 完整逻辑

这是事件分发中**最核心、最复杂**的方法。以下是简化的源码分析：

```java
// frameworks/base/core/java/android/view/ViewGroup.java
@Override
public boolean dispatchTouchEvent(MotionEvent ev) {
    boolean handled = false;
    final int action = ev.getAction();
    final int actionMasked = action & MotionEvent.ACTION_MASK;

    // ① ACTION_DOWN 时重置状态
    if (actionMasked == MotionEvent.ACTION_DOWN) {
        cancelAndClearTouchTargets(ev);
        resetTouchState();  // 清除 FLAG_DISALLOW_INTERCEPT
    }

    // ② 判断是否拦截
    final boolean intercepted;
    if (actionMasked == MotionEvent.ACTION_DOWN || mFirstTouchTarget != null) {
        final boolean disallowIntercept =
                (mGroupFlags & FLAG_DISALLOW_INTERCEPT) != 0;
        if (!disallowIntercept) {
            intercepted = onInterceptTouchEvent(ev);
        } else {
            intercepted = false;  // 子 View 禁止父 View 拦截
        }
    } else {
        intercepted = true;  // 没有 TouchTarget 且不是 DOWN → 直接拦截
    }

    // ③ ACTION_DOWN 时寻找接收子 View
    if (!intercepted && actionMasked == MotionEvent.ACTION_DOWN) {
        for (int i = childrenCount - 1; i >= 0; i--) {  // 倒序遍历（Z-order 从上到下）
            final View child = getAndVerifyPreorderedView(...);
            if (!child.canReceivePointerEvents() ||
                !isTransformedTouchPointInView(x, y, child, null)) {
                continue;  // 不可见 or 不在触摸范围内 → 跳过
            }
            if (dispatchTransformedTouchEvent(ev, false, child, ...)) {
                // 子 View 消费了 → 建立 TouchTarget
                newTouchTarget = addTouchTarget(child, idBitsToAssign);
                break;
            }
        }
    }

    // ④ 分发事件给 TouchTarget 或自身
    if (mFirstTouchTarget == null) {
        // 没有 TouchTarget → 自己处理
        handled = dispatchTransformedTouchEvent(ev, canceled, null, ...);
    } else {
        // 分发给 TouchTarget 链表中的目标
        TouchTarget target = mFirstTouchTarget;
        while (target != null) {
            if (intercepted) {
                // 中途拦截 → 给子 View 发 CANCEL
                cancelChild = true;
            }
            handled = dispatchTransformedTouchEvent(ev, cancelChild,
                    target.child, target.pointerIdBits);
            target = target.next;
        }
    }

    // ⑤ ACTION_UP / ACTION_CANCEL 时清理
    if (actionMasked == MotionEvent.ACTION_UP
            || actionMasked == MotionEvent.ACTION_CANCEL) {
        resetTouchState();
    }

    return handled;
}
```

> **源码路径**：`frameworks/base/core/java/android/view/ViewGroup.java`

### 3.3 关键设计决策

**为什么在 ACTION_DOWN 时重置状态？**
- 每个事件序列（DOWN → MOVE → UP）是独立的。DOWN 是"握手"：决定整个序列的接收者。
- `resetTouchState()` 会清除 `FLAG_DISALLOW_INTERCEPT`，确保父 View 在每个新序列的开始都有拦截的机会。

**为什么倒序遍历子 View？**
- 后添加的子 View 在 Z-order 上更靠前（更接近用户）。
- 倒序遍历确保最上层的 View 优先接收事件。

**为什么 dispatchTransformedTouchEvent 需要坐标变换？**
- 子 View 的坐标系相对于父 View 有偏移（translation、scroll、scale）。
- 必须将 MotionEvent 的坐标从父 View 坐标系变换到子 View 坐标系。

### 3.4 View.dispatchTouchEvent() 的逻辑

```java
// frameworks/base/core/java/android/view/View.java
public boolean dispatchTouchEvent(MotionEvent event) {
    boolean result = false;

    // 先检查 OnTouchListener
    if (mOnTouchListener != null
            && (mViewFlags & ENABLED_MASK) == ENABLED
            && mOnTouchListener.onTouch(this, event)) {
        result = true;
    }

    // OnTouchListener 没消费 → 调用 onTouchEvent
    if (!result && onTouchEvent(event)) {
        result = true;
    }

    return result;
}
```

**优先级**：`OnTouchListener.onTouch()` > `onTouchEvent()` > `OnClickListener.onClick()`

### 3.5 View.onTouchEvent() 的核心逻辑

```java
// frameworks/base/core/java/android/view/View.java
public boolean onTouchEvent(MotionEvent event) {
    final int action = event.getAction();

    if (clickable || (viewFlags & TOOLTIP) == TOOLTIP) {
        switch (action) {
            case MotionEvent.ACTION_DOWN:
                // 设置按压状态、启动长按检测
                setPressed(true, x, y);
                checkForLongClick(
                    ViewConfiguration.getLongPressTimeout(), x, y,
                    TOUCH_GESTURE_CLASSIFIED__CLASSIFICATION__LONG_PRESS);
                break;

            case MotionEvent.ACTION_MOVE:
                // 检查是否滑出了 View 范围 → 取消按压状态
                if (!pointInView(x, y, touchSlop)) {
                    removeTapCallback();
                    removeLongPressCallback();
                    setPressed(false);
                }
                break;

            case MotionEvent.ACTION_UP:
                // 触发 performClick() → OnClickListener.onClick()
                if (!mHasPerformedLongPress && !mIgnoreNextUpEvent) {
                    performClickInternal();
                }
                setPressed(false);
                break;

            case MotionEvent.ACTION_CANCEL:
                // 取消所有状态
                setPressed(false);
                removeTapCallback();
                removeLongPressCallback();
                break;
        }
        return true;
    }
    return false;
}
```

> **源码路径**：`frameworks/base/core/java/android/view/View.java`

关键点：
- `ACTION_DOWN` 启动**长按检测**（默认 500ms）
- `ACTION_UP` 触发 `performClick()` → `OnClickListener.onClick()`
- 如果 View 是 CLICKABLE 或 LONG_CLICKABLE，`onTouchEvent` 返回 true（消费事件）

---

## 4. 事件序列与 TouchTarget

### 4.1 事件序列的概念

一次完整的触摸交互是一个**事件序列**：

```
ACTION_DOWN → ACTION_MOVE (× N) → ACTION_UP
```

事件序列的关键规则：
- `ACTION_DOWN` 是"握手"——决定了整个序列的接收者（TouchTarget）
- 后续的 `MOVE` / `UP` 直接发给 `DOWN` 时确定的 TouchTarget，**不再做命中测试**
- 如果 `DOWN` 没有被任何子 View 消费 → `mFirstTouchTarget = null` → 后续所有事件由 ViewGroup 自身处理

### 4.2 TouchTarget 链表

```java
// frameworks/base/core/java/android/view/ViewGroup.java
private static final class TouchTarget {
    public View child;           // 目标子 View
    public int pointerIdBits;    // 负责的 pointer ID
    public TouchTarget next;     // 链表下一个节点
}
```

- 单点触控：链表只有一个节点
- 多点触控：每个手指可以指向不同的子 View，形成多节点链表
- `pointerIdBits` 是位掩码，标记当前 TouchTarget 负责的 pointer ID

### 4.3 ACTION_CANCEL 的作用

CANCEL 事件在以下场景产生：

| 场景 | 触发条件 | 目的 |
| :--- | :--- | :--- |
| 父 View 中途拦截 | `onInterceptTouchEvent` 在 MOVE 阶段返回 true | 告诉子 View 事件被抢走 |
| 窗口焦点丢失 | Activity 切换 / Dialog 弹出 | 告诉 View 触摸序列中断 |
| InputDispatcher ANR | ANR 发生时取消事件 | 防止事件状态不一致 |

子 View 收到 `CANCEL` 后应该：
- 取消长按计时
- 恢复按压效果（`setPressed(false)`）
- 清理所有触摸相关状态

### 4.4 DOWN 未消费的后果

如果 `ACTION_DOWN` 没有被任何子 View 消费（所有子 View 的 `dispatchTouchEvent` 返回 false）：

1. `mFirstTouchTarget` 保持 null
2. 后续 `MOVE` / `UP` 事件到达时，`dispatchTouchEvent` 中直接走 `mFirstTouchTarget == null` 分支
3. ViewGroup 自己的 `onTouchEvent` 被调用
4. 如果 ViewGroup 的 `onTouchEvent` 也返回 false → 事件继续向上传递

这是**"点击没有反应"的常见原因之一**：某个 View 应该在 DOWN 时返回 true 以消费事件，但因为 `clickable = false` 或其他原因返回了 false。

---

## 5. 触摸事件冲突与解决方案

### 5.1 冲突的本质

嵌套可滑动 View 是 Android 开发中最常见的场景之一：
- ScrollView 内嵌 RecyclerView
- ViewPager 内嵌 RecyclerView
- CoordinatorLayout + AppBarLayout + RecyclerView

冲突的本质：**父 View 和子 View 都想消费 MOVE 事件**。谁先拦截，谁就获得后续所有事件。

### 5.2 方案一：外部拦截法（父 View 控制）

父 View 在 `onInterceptTouchEvent` 中根据手势判断是否拦截：

```java
// 自定义 ScrollView
@Override
public boolean onInterceptTouchEvent(MotionEvent ev) {
    switch (ev.getAction()) {
        case MotionEvent.ACTION_DOWN:
            mLastY = ev.getY();
            return false;  // DOWN 不拦截，让子 View 有机会响应

        case MotionEvent.ACTION_MOVE:
            float dy = Math.abs(ev.getY() - mLastY);
            float dx = Math.abs(ev.getX() - mLastX);
            if (dy > dx && dy > mTouchSlop) {
                return true;  // 垂直滑动 → 拦截
            }
            return false;

        case MotionEvent.ACTION_UP:
            return false;
    }
    return false;
}
```

**核心原则**：
- `DOWN` 不拦截（否则子 View 收不到 DOWN，无法建立 TouchTarget）
- `MOVE` 时根据方向/距离决定
- 一旦拦截 → 子 View 收到 `CANCEL` → 后续事件全部由父 View 处理

### 5.3 方案二：内部拦截法（子 View 控制）

子 View 通过 `requestDisallowInterceptTouchEvent` 阻止父 View 拦截：

```java
// 子 View（如水平滑动的 RecyclerView）
@Override
public boolean dispatchTouchEvent(MotionEvent ev) {
    switch (ev.getAction()) {
        case MotionEvent.ACTION_DOWN:
            getParent().requestDisallowInterceptTouchEvent(true);
            break;

        case MotionEvent.ACTION_MOVE:
            float dx = Math.abs(ev.getX() - mLastX);
            float dy = Math.abs(ev.getY() - mLastY);
            if (dy > dx) {
                // 垂直方向 → 放行给父 View
                getParent().requestDisallowInterceptTouchEvent(false);
            }
            break;
    }
    return super.dispatchTouchEvent(ev);
}
```

**核心原则**：
- `DOWN` 时设置 `disallowIntercept = true`（先占住事件）
- `MOVE` 时判断方向，如果不是自己想处理的方向 → 取消 disallow → 父 View 恢复拦截能力

### 5.4 方案三：NestedScrolling 协议（标准化方案）

Android 5.0 引入了 `NestedScrollingChild` / `NestedScrollingParent` 接口，提供了标准化的嵌套滑动协商机制：

```
子 View 开始滑动
    → startNestedScroll(axes) → 找到支持 NestedScrolling 的父 View
        → dispatchNestedPreScroll(dx, dy, consumed, offset)
            → 父 View 先消费一部分（consumed[0], consumed[1]）
        → 子 View 消费剩余部分
        → dispatchNestedScroll(dxConsumed, dyConsumed, dxUnconsumed, dyUnconsumed, ...)
            → 父 View 消费子 View 未消费的部分
```

**RecyclerView** 默认实现了 `NestedScrollingChild`。**CoordinatorLayout** 实现了 `NestedScrollingParent`。

> **源码路径**：`frameworks/base/core/java/android/view/NestedScrollingChild.java`、`frameworks/base/core/java/android/view/NestedScrollingParent.java`

### 5.5 GestureDetector

`GestureDetector` 封装了常见手势识别逻辑：

```java
// 在 onTouchEvent 中使用
private GestureDetector mDetector = new GestureDetector(context,
    new GestureDetector.SimpleOnGestureListener() {
        @Override
        public boolean onFling(MotionEvent e1, MotionEvent e2,
                float velocityX, float velocityY) {
            // 处理快速滑动
            return true;
        }

        @Override
        public boolean onLongPress(MotionEvent e) {
            // 处理长按
        }
    });

@Override
public boolean onTouchEvent(MotionEvent event) {
    return mDetector.onTouchEvent(event);
}
```

> **源码路径**：`frameworks/base/core/java/android/view/GestureDetector.java`

---

## 6. finishInputEvent 与 ANR 的关联

### 6.1 完整的事件处理到回复链路

```
InputChannel fd 可读
  → NativeInputEventReceiver.handleEvent()
    → consumeEvents()
      → InputEventReceiver.dispatchInputEvent()
        → ViewRootImpl.WindowInputEventReceiver.onInputEvent()
          → enqueueInputEvent()
            → doProcessInputEvents()
              → deliverInputEvent()
                → InputStage 管线（7 个 Stage）
                  → ViewPostImeInputStage.processPointerEvent()
                    → DecorView.dispatchTouchEvent()
                      → View 树分发
                        → onTouchEvent() 处理
                          → finishInputEvent(event, handled)
```

**从 InputChannel 可读到 finishInputEvent 回复，整个过程在主线程同步执行。** 任何一步耗时过长，都会延迟 `finishInputEvent` 的回复，增加 ANR 风险。

### 6.2 耗时预算

InputDispatcher 的 ANR 超时为 5 秒，但实际的耗时预算远不止这么简单：

| 阶段 | 典型耗时 | 说明 |
| :--- | :--- | :--- |
| InputStage 管线传递 | < 1ms | 几乎可忽略 |
| View 树分发（dispatchTouchEvent 递归） | 1~10ms | 取决于 View 树深度 |
| onTouchEvent 业务处理 | **变量** | **这是 ANR 风险的主要来源** |
| finishInputEvent 回复 | < 1ms | socket write |

关键：**如果主线程在处理前一个消息（如 onBindViewHolder / BroadcastReceiver.onReceive），Input 事件需要在 MessageQueue 中排队等待**。这意味着即使 onTouchEvent 本身很快，如果前面的消息很慢，ANR 仍然会发生。

---

## 7. 稳定性风险点总结

| 风险 | 原因 | 后果 | 排查方向 |
| :--- | :--- | :--- | :--- |
| onTouchEvent 耗时 | 在触摸回调中执行 DB/网络/文件 IO | 主线程阻塞 → Input ANR | ANR trace 主线程栈 |
| onClick 耗时 | performClick 触发的业务逻辑过重 | 同上 | 同上 |
| View 树过深 | 嵌套层级过多 → dispatchTouchEvent 递归深 | 分发耗时增大 → 触摸延迟 | Layout Inspector / Systrace |
| 事件拦截冲突 | 父子 View 同时处理 MOVE | 滑动失效 / 点击无响应 | 添加 touch event 日志 |
| DOWN 未消费 | View 的 clickable=false / onTouchEvent 返回 false | 后续 MOVE/UP 全部丢失 | 检查 View 属性 |
| IME Stage 拦截 | 输入法消费了事件 | 按键事件无法到达 View | ImeInputStage 日志 |
| dispatchTouchEvent 异常 | onTouchEvent 中抛异常 | 事件序列中断 → 状态不一致 | Crash 日志 |
| 主线程消息积压 | Input 事件在 MessageQueue 中排队 | finishInputEvent 延迟 → ANR | Looper Printer / Systrace |

---

## 8. 实战案例

### Case 1：RecyclerView + ViewPager2 嵌套滑动失效

**现象**：
水平 ViewPager2 内嵌垂直 RecyclerView。用户在 RecyclerView 上斜向滑动时，RecyclerView 无法垂直滑动——事件被 ViewPager2 拦截。

**排查过程**：

1. **添加 onInterceptTouchEvent 日志**：在 ViewPager2 的父 View 中发现 `onInterceptTouchEvent` 在 `MOVE` 阶段返回了 true。

2. **分析 ViewPager2 拦截逻辑**：ViewPager2 内部使用 `RecyclerView`，其 `onInterceptTouchEvent` 在水平位移 > `touchSlop` 时就会拦截，不考虑垂直位移是否更大。

3. **Systrace 确认**：事件从 InputDispatcher 到 ViewPager2 的 `dispatchTouchEvent` 正常 → ViewPager2 拦截后，内部 RecyclerView 收到 `CANCEL` → 垂直滑动中断。

**根因**：
ViewPager2 的默认拦截策略在检测到水平位移超过 `touchSlop` 时就拦截，没有与垂直位移做比较。在斜向滑动场景下，水平分量先达到 `touchSlop` → 立即拦截 → 垂直方向的 RecyclerView 失去事件。

**修复方案**：

```java
// 在 RecyclerView 的 onAttachedToWindow 中
recyclerView.addOnItemTouchListener(new RecyclerView.OnItemTouchListener() {
    @Override
    public boolean onInterceptTouchEvent(@NonNull RecyclerView rv, @NonNull MotionEvent e) {
        if (e.getAction() == MotionEvent.ACTION_DOWN) {
            rv.getParent().requestDisallowInterceptTouchEvent(true);
        }
        int action = e.getActionMasked();
        if (action == MotionEvent.ACTION_MOVE) {
            float dx = Math.abs(e.getX() - mInitialX);
            float dy = Math.abs(e.getY() - mInitialY);
            if (dx > dy) {
                // 水平方向为主 → 放行给 ViewPager2
                rv.getParent().requestDisallowInterceptTouchEvent(false);
            }
        }
        return false;
    }
    // ...
});
```

**关键收获**：使用内部拦截法，让 RecyclerView 在 `ACTION_DOWN` 时先禁止 ViewPager2 拦截，在 `MOVE` 时根据滑动方向决定是否放行。

---

### Case 2：直播间 onClick 导致 Input ANR

**现象**：
直播间页面，用户点击"送礼物"按钮后偶发 ANR，频率约 0.5%。

**logcat**：
```
Input dispatching timed out (Waiting because the focused window has not
finished processing the previous input event that was delivered to it.
Outbound queue length: 2. Wait queue length: 5.)
```

**ANR trace 主线程堆栈**：
```
"main" prio=5 tid=1 Runnable
  at android.database.sqlite.SQLiteConnection.nativeExecuteForString(Native)
  at android.database.sqlite.SQLiteConnection.executeForString(SQLiteConnection.java:779)
  at android.database.sqlite.SQLiteDatabase.rawQueryWithFactory(SQLiteDatabase.java:1697)
  at com.example.live.gift.GiftManager.queryGiftInfo(GiftManager.java:156)
  at com.example.live.gift.GiftDialogFragment.onGiftClicked(GiftDialogFragment.java:89)
  at android.view.View.performClick(View.java:7448)
  at android.view.View$PerformClick.run(View.java:28187)
  at android.os.Handler.handleCallback(Handler.java:938)
```

**排查过程**：

1. **从 ANR trace 看**：主线程在 `onClick` 回调中执行 `GiftManager.queryGiftInfo()` → 同步数据库查询。
2. **从 dumpsys input 看**：waitQueue 有 5 个事件积压，outboundQueue 有 2 个等待发送。最早的事件等待了 5.2 秒。
3. **从 Systrace 看**：`onClick` 处理耗时 1.5~3 秒（磁盘 IO 抖动）+ 之前 MessageQueue 中排队的其他消息 2 秒 = 总阻塞 > 5 秒。

**根因**：
`GiftDialogFragment.onGiftClicked` → `GiftManager.queryGiftInfo` 在主线程同步执行 SQLite 查询。当数据库文件较大或磁盘 IO 繁忙时，查询耗时从几十 ms 飙升到 1.5~3 秒。叠加 MessageQueue 中其他消息的耗时，总主线程阻塞超过 5 秒 → Input ANR。

**修复方案**：

```kotlin
// Before: 主线程同步查询
fun onGiftClicked(giftId: Int) {
    val info = giftManager.queryGiftInfo(giftId)  // 阻塞主线程！
    showGiftAnimation(info)
}

// After: 切换到 IO 协程
fun onGiftClicked(giftId: Int) {
    showLoadingIndicator()
    lifecycleScope.launch {
        val info = withContext(Dispatchers.IO) {
            giftManager.queryGiftInfo(giftId)
        }
        showGiftAnimation(info)
    }
}
```

**关键收获**：
- `onClick` / `onTouchEvent` 中**绝对不能**执行数据库、网络、文件 IO 操作
- 使用 `StrictMode.ThreadPolicy.detectDiskReads().detectDiskWrites()` 在开发阶段检测主线程 IO
- waitQueue 长度 > 1 是一个危险信号，说明 App 处理事件的速度跟不上事件产生的速度

---

## 附录：核心源码路径索引

| 文件 | 路径 | 说明 |
| :--- | :--- | :--- |
| ViewRootImpl.java | `frameworks/base/core/java/android/view/ViewRootImpl.java` | InputStage 管线、事件入口 |
| ViewGroup.java | `frameworks/base/core/java/android/view/ViewGroup.java` | dispatchTouchEvent、onInterceptTouchEvent |
| View.java | `frameworks/base/core/java/android/view/View.java` | onTouchEvent、dispatchTouchEvent |
| InputEventReceiver.java | `frameworks/base/core/java/android/view/InputEventReceiver.java` | 事件接收与 finishInputEvent |
| GestureDetector.java | `frameworks/base/core/java/android/view/GestureDetector.java` | 手势识别封装 |
| NestedScrollingChild.java | `frameworks/base/core/java/android/view/NestedScrollingChild.java` | 嵌套滑动子接口 |
| NestedScrollingParent.java | `frameworks/base/core/java/android/view/NestedScrollingParent.java` | 嵌套滑动父接口 |

