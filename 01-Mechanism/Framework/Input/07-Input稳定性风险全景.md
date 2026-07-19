# 07-Input 稳定性风险全景：ANR、延迟与事件丢失

> **系列**：面向稳定性的 Android Input 子系统深度解析系列(Input_FWK)
>
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
>
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇风险涉及 `frameworks/native/services/inputflinger/`、`frameworks/base/services/core/java/com/android/server/input/`;Android 14 input latency 监控增强见 §3)
>
> **目标读者**:Android 稳定性框架架构师
>
> **前置阅读**:本系列 01-06 全篇
>
> **下一篇**:[08-Input 诊断工具与延迟治理体系](08-Input诊断工具与延迟治理体系.md)

---

## 本篇定位

- **本篇系列角色**:系列收口篇(Input 风险地图 + 工具箱 + 治理实践)
- **强依赖**:本系列 01-06 全篇
- **承接自**:01-06 已覆盖 Input 全链路机制。本篇做**风险收口**
- **衔接去**:08 诊断治理 + 工程实践
- **不重复内容**:各篇具体机制由 01-06 承担;本篇只做**风险矩阵 + 排查决策树**

#### §0 锚点案例的可验证 4 件套:某 App 上线后 ANR 率从 0.5% 飙到 4%,5 类症状分类

> **环境**:
> - 设备:某机型线上统计(小米 11 占比 30%,Pixel 6 占比 25%)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某 IM App v7.5(脱敏代号 `ChatApp`,新版上线)
> - 工具:稳定性监控平台 + `bugreport` + ANR 文件分析

> **复现步骤**(线上监控告警后):
> 1. 监控告警:ChatApp ANR 率从 0.5% 飙到 4%(>5 倍)
> 2. 拉取 1000 个 ANR 文件 → 按 `Reason` 字段分类
> 3. 5 类症状分布:
>     - Input ANR(40%)
>     - Service ANR(20%)
>     - Broadcast ANR(15%)
>     - Provider ANR(15%)
>     - 其他(10%)
> 4. 重点分析 Input ANR 这 400 个文件 → 5 类根因:
>     - 主线程阻塞(60%)
>     - 死锁(20%)
>     - InputDispatcher 卡死(10%)
>     - 触摸事件丢失(5%)
>     - 其他(5%)
> 5. 修复 + 灰度验证

> **logcat / ANR 关键片段**:
> ```
> # ANR 监控大盘(线上)
> ChatApp v7.5 ANR rate: 4.2% (上一版本 v7.4: 0.5%)
> ANR 类型分布:
>   - Input: 40.2% (160/400)         ← 主战场
>   - Service: 20.0% (80/400)
>   - Broadcast: 15.0% (60/400)
>   - Provider: 15.0% (60/400)
>   - 其他: 9.8% (40/400)
> # Input ANR 400 个文件根因分类
> 主线程阻塞: 240 (60%)
>   - onMeasure 嵌套递归: 120 (30%)    ← 自定义 View 优化不够
>   - 同步 IO: 60 (15%)
>   - 同步网络: 40 (10%)
>   - 同步 DB: 20 (5%)
> 死锁: 80 (20%)
>   - InputDispatcher ↔ WindowManager 死锁: 50 (12.5%)
>   - App 内自死锁: 30 (7.5%)
> InputDispatcher 卡死: 40 (10%)
> 触摸事件丢失: 20 (5%)
> 其他: 20 (5%)
> ```

> **修复 commit-style diff**(综合修复):
> ```diff
> --- a/gradle.properties
> +++ b/gradle.properties
> @@ lint
> -    # 旧版:无 View 嵌套深度检查
> +    # 修复:开启 lint ViewHierarchyDepth 检查,build 时阻断嵌套 > 10 层
> +    android.lintOptions.check('ViewHierarchyDepth')
> ```
> ```diff
> --- a/app/src/main/java/com/chat/app/ChatApplication.kt
> +++ b/app/src/main/java/com/chat/app/ChatApplication.kt
> @@ AsyncInit
> -    // 旧版:onCreate 同步初始化 12 个 SDK,主线程忙 800ms
> -    SDKManager.initAll(this)
> +    // 修复:异步 SDK 初始化 + 进度回调,主线程忙 < 100ms
> +    AsyncInitRunner.run {
> +        SDKManager.initAll(this@ChatApplication)
> +        handler.post { /* onReady */ }
> +    }
> ```
> ```diff
> --- a/monitor/anr_alert.json
> +++ b/monitor/anr_alert.json
> @@ alerting
> -    { "name": "anr_rate", "threshold": "1%", "page_on": true }
> +    { "name": "anr_rate", "threshold": "1.5%", "page_on": true }
> +    { "name": "input_anr_rate", "threshold": "0.6%", "page_on": true }
> +    { "name": "anr_p99_latency", "threshold": "5500ms", "page_on": true }
> ```
> 完整 5 类症状 ↔ 根因分布 ↔ 治理优先级 ↔ 工具链见 §2-§6。

## 引言

前六篇文章从架构到源码，完整解析了 Input 系统的五层架构和核心机制。本篇的目标是**建立一张完整的"风险地图"**——将所有可能出问题的地方、表现形式、排查方向系统性地梳理出来。

Input 系统的稳定性问题可以归为三大类：
1. **Input ANR** — 用户触摸/按键后 App 无响应（最严重，占 ANR 总量 60%+）
2. **触摸延迟** — 用户能操作但感觉"卡"（影响体验，用户留存的隐形杀手）
3. **事件丢失** — 触摸/按键没有反应，但不一定触发 ANR（难排查，用户感知为"偶尔点不动"）

本文将对每一类问题进行系统性的分类、特征描述、日志/dumpsys/trace 特征总结，并提供速查表供线上问题快速定位。

---

## 1. Input ANR 的分类与特征

Input ANR 是 InputDispatcher 检测到事件超过 5 秒未被处理（或无窗口可投递）时触发的。根据根因不同，可以分为以下四个主要类型：

### 1.1 主线程卡顿型

**本质**：App 的焦点窗口存在，InputChannel 正常，事件已发送给 App，但 App 主线程正在执行耗时操作，无法及时调用 `finishInputEvent`。

**典型场景**：
- `onTouchEvent` / `onClick` 中执行数据库查询（SQLite）
- `SharedPreferences.commit()` 同步写磁盘
- 主线程 JSON 解析大数据
- `onBindViewHolder` 中同步加载图片
- 主线程执行复杂布局计算（View 树过深）
- `BroadcastReceiver.onReceive` 中执行耗时操作

**logcat 特征**：
```
Input dispatching timed out (Waiting because the focused window has not
finished processing the previous input event that was delivered to it.
Outbound queue length: N. Wait queue length: M.)
```

**dumpsys input 特征**：
```
Connection: channelName='...MainActivity', status=NORMAL
  outboundQueue length: ≥0
  waitQueue length: ≥1 (wait time > 5000ms)
FocusedWindow: 存在
```

**ANR trace 特征**：
- 主线程 **不是** `nativePollOnce`
- 主线程栈中有明确的业务代码（DB 操作、文件 IO、网络请求等）
- 或者主线程栈显示 Binder.transact（被跨进程调用阻塞）

**排查方向**：
1. 看 ANR trace 主线程堆栈 → 找到耗时操作
2. 看 CPU usage → 判断是 CPU 密集还是 IO 等待
3. 看 dumpsys input waitQueue → 确认事件积压时间

---

### 1.2 无焦点窗口型

**本质**：InputDispatcher 有事件要分发，但没有焦点窗口（FocusedWindow = null）。通常发生在 App 冷启动阶段或 Activity 切换的"焦点真空期"。

**典型场景**：
- Application.onCreate 耗时过长（SDK 初始化、跨进程 ContentProvider 查询）
- Activity 切换时旧窗口已移除、新窗口未添加
- 多进程 App 启动时进程间同步等待
- 启动页（SplashActivity）到主页的跳转耗时

**logcat 特征**：
```
Input dispatching timed out (Waiting because no window has focus but
there is a focused application that may eventually add a window when
it finishes starting up.)
```

**dumpsys input 特征**：
```
FocusedApplications:
  displayId=0, name='...com.example.app/.MainActivity'
FocusedWindows:
  <none>     ← 焦点窗口为空！
```

**ANR trace 特征**：
- 主线程通常在 `Application.onCreate` 或 `Activity.onCreate` 阶段
- 可能看到 `ContentResolver.query` / `BinderProxy.transact` 等跨进程调用
- 也可能看到第三方 SDK 的初始化代码

**排查方向**：
1. 看 dumpsys input → FocusedWindow 是否为 null
2. 看 ANR trace → Application.onCreate 或 Activity.onCreate 中的耗时操作
3. 用 Systrace 分析启动链路的每一步耗时

---

### 1.3 Binder 阻塞型

**本质**：App 主线程正在等待 Binder 调用返回（跨进程 RPC），导致无法处理 Input 事件。

**典型场景**：
- 主线程调用 `ContentResolver.query()`（跨进程 ContentProvider）
- 主线程调用 `PackageManager.getPackageInfo()`
- 主线程调用自定义 AIDL 接口
- 主线程调用 `ActivityManager.getRunningServices()`
- 对端进程（Service 所在进程）卡顿或 Binder 线程池耗尽 → 调用方主线程被阻塞

**logcat 特征**：
与主线程卡顿型相同（从 InputDispatcher 角度看都是"窗口处理慢"）。

**ANR trace 特征**：
```
"main" prio=5 tid=1 Native
  at android.os.BinderProxy.transactNative(Native Method)
  at android.os.BinderProxy.transact(BinderProxy.java:571)
  at xxx.IMyService$Stub$Proxy.doSomething(...)
  at com.example.app.SomeActivity.onResume(...)
```

**排查方向**：
1. 看 ANR trace 主线程 → 找到 `BinderProxy.transact` 调用
2. 确定目标 Binder 服务和对端进程
3. 检查对端进程是否卡顿 / Binder 线程池是否耗尽
4. 考虑将 Binder 调用移到后台线程

---

### 1.4 同步屏障泄漏型

**本质**：MessageQueue 中存在未移除的同步屏障（Sync Barrier），导致主线程只能处理异步消息，普通同步消息（包括 Input 事件回调）被阻塞。

**背景知识**：
- 同步屏障（`target == null` 的 Message）用于 Choreographer 优先处理渲染消息
- 正常流程：`scheduleTraversals()` 添加屏障 → `doTraversal()` 移除屏障
- 如果 `doTraversal()` 因异常未执行 → 屏障泄漏 → 后续所有同步消息被阻塞

**典型场景**：
- `ViewRootImpl.scheduleTraversals()` 添加了屏障
- 但 `performTraversals()` 过程中抛出异常 / 被中断
- 屏障未通过 `unscheduleTraversals()` 移除
- 后续所有同步消息（包括 Input 事件）被阻塞
- 用户触摸 → 事件到达 App → 但 MessageQueue.next() 跳过该消息（因为它是同步的）→ finishInputEvent 永远不会被调用 → ANR

**logcat 特征**：
与主线程卡顿型相同。

**ANR trace 特征**：
```
"main" prio=5 tid=1 Native
  at android.os.MessageQueue.nativePollOnce(Native Method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  at android.os.Looper.loopOnce(Looper.java:161)
```

关键点：**主线程看起来空闲**（在 `nativePollOnce`），但 dumpsys input 显示 waitQueue 有大量积压。这是同步屏障泄漏的典型"烟雾信号"——主线程不是真空闲，而是在等异步消息，同步消息全被跳过。

**排查方向**：
1. ANR trace 主线程在 `nativePollOnce` + dumpsys input waitQueue 有大量积压 → 怀疑同步屏障泄漏
2. 使用反射检查 `MessageQueue.mMessages` 链表中是否有 `target == null` 的 Message
3. 检查 `ViewRootImpl` 的 traversal 流程是否有异常中断

---

### 1.5 Input ANR 分类速查表

| 类型 | ANR Reason 关键词 | FocusedWindow | waitQueue | 主线程状态 | 排查重点 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 主线程卡顿 | "has not finished processing" | 存在 | 积压 | 业务代码 / IO | 主线程堆栈 |
| 无焦点窗口 | "no focused window" | null | — | onCreate 阶段 | 启动耗时 |
| Binder 阻塞 | "has not finished processing" | 存在 | 积压 | BinderProxy.transact | 对端进程状态 |
| 同步屏障泄漏 | "has not finished processing" | 存在 | 积压 | nativePollOnce（假空闲） | 屏障检查 |

---

## 2. 触摸延迟的分类与排查

触摸延迟是指从用户手指接触屏幕到屏幕上出现视觉反馈之间的时间差。理想值 < 50ms，100ms 以上用户可明显感知。

触摸延迟可能发生在 Input 链路的**每一层**。以下按层分析：

### 2.1 第一层：硬件/驱动层延迟

| 延迟来源 | 典型耗时 | 表现 | 排查方法 |
| :--- | :--- | :--- | :--- |
| 触摸屏采样率低 | 8~16ms（60~120Hz） | 所有触摸都有固定基底延迟 | `getevent -lt` 查看时间间隔 |
| 触摸屏驱动处理慢 | 变量 | 触摸延迟不稳定 | `getevent` 对比硬件中断时间 |
| 触摸屏固件 bug | 变量 | 特定手势延迟 | 更换设备对比 |

**排查工具**：`getevent -lt /dev/input/eventX` — 直接读取内核层事件，观察时间戳间隔。

### 2.2 第二层：EventHub / InputReader 层延迟

| 延迟来源 | 典型耗时 | 表现 | 排查方法 |
| :--- | :--- | :--- | :--- |
| EventHub epoll 唤醒延迟 | < 1ms（通常） | 极端情况下可达数 ms | Systrace: input 标签 |
| InputReader 处理慢 | 通常 < 1ms | 大量设备同时上报时可能增加 | Systrace: InputReader 耗时 |
| 坐标变换计算 | < 1ms | 通常可忽略 | — |

这一层通常不是延迟的瓶颈，但在极端场景下（如大量 USB 设备同时连接）可能成为问题。

### 2.3 第三层：InputDispatcher 层延迟

| 延迟来源 | 典型耗时 | 表现 | 排查方法 |
| :--- | :--- | :--- | :--- |
| 窗口查找（findTargets） | 通常 < 1ms | 窗口数量多时可能增加 | Systrace |
| waitQueue 串行化等待 | **变量（0~5s）** | **最常见的延迟源！** | `dumpsys input` |
| mLock 锁竞争 | 变量 | WMS 更新窗口时持锁 | Systrace: InputDispatcher |
| InputChannel socket write | < 1ms | 通常可忽略 | — |

**waitQueue 串行化等待是最常见的 InputDispatcher 层延迟源**。如果 App 对上一个事件的处理慢（finishInputEvent 延迟），新事件在 outboundQueue 中等待，或者在 InputDispatcher 端就被延迟投递。

### 2.4 第四层：跨进程传输层延迟

| 延迟来源 | 典型耗时 | 表现 | 排查方法 |
| :--- | :--- | :--- | :--- |
| InputChannel socket 传输 | < 1ms | 通常可忽略 | Systrace |
| socket buffer 积压 | 变量 | App 消费慢 → buffer 满 → 新事件写入延迟 | `dumpsys input` 看 outboundQueue |
| NativeLooper epoll 唤醒延迟 | < 1ms | 通常可忽略 | Systrace |

### 2.5 第五层：App 层延迟（最常见的延迟源）

| 延迟来源 | 典型耗时 | 表现 | 排查方法 |
| :--- | :--- | :--- | :--- |
| 主线程消息排队 | **变量（0~数秒）** | **最常见！** | Looper Printer / Systrace |
| InputStage 管线（IME 处理） | 通常 < 5ms | IME 慢时可达数十 ms | Systrace |
| View 树分发（dispatchTouchEvent） | 1~20ms | View 树过深时增加 | Layout Inspector |
| onTouchEvent 业务处理 | **变量** | **直接影响 finishInputEvent** | ANR trace |
| 渲染延迟（非 Input 直接） | 16~100ms | 掉帧导致视觉反馈延迟 | Systrace: Choreographer |

**主线程消息排队**是最常被忽略的延迟源。即使 onTouchEvent 本身很快，如果前面有一个耗时 200ms 的消息正在处理，Input 事件需要在 MessageQueue 中等待 200ms。

### 2.6 触摸延迟排查决策树

```
用户反馈"触摸卡顿"
    │
    ├── getevent -lt 检查硬件层事件是否正常（时间戳间隔、坐标）
    │       ├── 异常 → 硬件/驱动问题
    │       └── 正常 ↓
    │
    ├── Systrace 检查 InputReader → InputDispatcher → App 各阶段耗时
    │       ├── InputDispatcher 端延迟大 → dumpsys input 检查 waitQueue
    │       │       ├── waitQueue 积压 → App 处理前一个事件慢
    │       │       └── mLock 竞争 → WMS 频繁更新窗口
    │       └── App 端延迟大 ↓
    │
    ├── Looper Printer / Systrace 检查主线程消息耗时
    │       ├── 有慢消息 → 定位慢消息内容
    │       └── 无慢消息 → View 树分发耗时
    │               ├── Layout Inspector 检查 View 层级
    │               └── onTouchEvent / onClick 业务耗时
    │
    └── 以上都正常 → 渲染延迟（掉帧）→ Choreographer doFrame 分析
```

---

## 3. 事件丢失的场景与排查

事件丢失是指用户的触摸/按键没有被 App 收到或处理。与 ANR 不同，事件丢失不一定触发系统级别的警告，用户感知为"偶尔点不动"或"滑动断续"。

### 3.1 InputDispatcher 端丢弃

**场景一：mInboundQueue 满**

InputDispatcher 的 `mInboundQueue` 有容量限制。如果 InputReader 生产事件过快（如自动化测试 / 事件注入）或 InputDispatcher 消费过慢（锁竞争 / 窗口查找慢），队列可能溢出。

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
void InputDispatcher::notifyMotion(const NotifyMotionArgs* args) {
    // ...
    if (mInboundQueue.size() >= MAX_INBOUND_QUEUE_SIZE) {
        ALOGI("Dropping motion event because inbound queue is full.");
        return;  // 丢弃事件
    }
    // ...
}
```

**表现**：logcat 中出现 "Dropping motion event" 日志。

**场景二：touched nothing**

```cpp
// InputDispatcher::findTouchedWindowTargetsLocked
if (newTouchedWindowHandle == nullptr) {
    // 没有找到目标窗口
    if (mFocusedApplicationHandlesByDisplay.count(displayId) == 0) {
        ALOGI("Dropping event because there is no focused window "
              "or focused application.");
        return INPUT_EVENT_INJECTION_FAILED;  // 丢弃
    }
}
```

**表现**：触摸在没有窗口覆盖的区域（如 StatusBar 与 App 窗口之间的缝隙），事件被丢弃。

### 3.2 InputChannel 层丢弃

**场景：socket buffer 满**

当 App 主线程严重卡顿 → 无法消费 InputChannel 的数据 → socket buffer 写满 → InputDispatcher 的 `send()` 返回 `EWOULDBLOCK`。

```cpp
// frameworks/native/libs/input/InputTransport.cpp
status_t InputChannel::sendMessage(const InputMessage* msg) {
    ssize_t nWrite;
    do {
        nWrite = ::send(mFd.get(), msg, msgLength, MSG_DONTWAIT | MSG_NOSIGNAL);
    } while (nWrite == -1 && errno == EINTR);

    if (nWrite < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return WOULD_BLOCK;  // buffer 满
        }
        // ...
    }
    return OK;
}
```

**表现**：InputDispatcher 无法发送事件 → 事件堆积在 outboundQueue → 最终可能导致 ANR 或事件被丢弃。

### 3.3 App 层丢弃

**场景一：ACTION_DOWN 未被消费**

如果 `ACTION_DOWN` 在 View 树分发中没有被任何 View 消费（所有 `dispatchTouchEvent` 返回 false）：
- `mFirstTouchTarget = null`
- 后续 `MOVE` / `UP` 事件由 ViewGroup 自身处理
- 如果 ViewGroup 也不消费 → 整个事件序列被"静默丢弃"

**表现**：用户点击某个区域没有反应，但没有 ANR。

**场景二：事件拦截导致丢失**

父 View 在 MOVE 阶段拦截事件 → 子 View 收到 CANCEL → 子 View 的点击/滑动逻辑中断。

**表现**：滑动过程中突然"断掉"，需要重新触摸才能继续。

**场景三：事件合并（Motion Batching）**

多个连续的 `ACTION_MOVE` 事件可能被合并为一个带 historical data 的 MotionEvent。这不是真正的"丢失"，但如果 App 只处理最新坐标而忽略 historical data，就会表现为"滑动不流畅"。

```java
// 正确处理 batched events
@Override
public boolean onTouchEvent(MotionEvent event) {
    // 先处理历史数据
    for (int i = 0; i < event.getHistorySize(); i++) {
        float hx = event.getHistoricalX(i);
        float hy = event.getHistoricalY(i);
        handleTouch(hx, hy);
    }
    // 再处理当前数据
    handleTouch(event.getX(), event.getY());
    return true;
}
```

### 3.4 事件丢失排查速查表

| 丢失位置 | 日志特征 | dumpsys 特征 | 排查工具 |
| :--- | :--- | :--- | :--- |
| mInboundQueue 满 | "Dropping motion event" | — | logcat |
| touched nothing | "Dropping event because there is no focused window" | FocusedWindow=null | dumpsys input |
| socket buffer 满 | — | outboundQueue 大量积压 | dumpsys input |
| DOWN 未消费 | — | — | 添加 touch log / Layout Inspector |
| 事件拦截 | — | — | onInterceptTouchEvent 日志 |
| Motion Batching | — | — | 检查 historical data 处理 |

---

## 4. 综合问题速查表

### 4.1 按现象分类

| 用户感知 | 可能的问题类型 | 优先排查方向 |
| :--- | :--- | :--- |
| 弹出 ANR 对话框 | Input ANR | logcat + traces.txt + dumpsys input |
| 点击没反应（无 ANR） | 事件丢失 | dumpsys input + touch log |
| 滑动卡顿 | 触摸延迟 | Systrace + Looper Printer |
| 滑动断续 | 事件拦截冲突 | onInterceptTouchEvent log |
| 触摸偏移 | 坐标变换异常 | getevent + dumpsys input |
| 外接设备不响应 | EventHub 问题 | getevent + dumpsys input devices |

### 4.2 按 dumpsys input 输出分类

| dumpsys input 特征 | 问题诊断 | 下一步 |
| :--- | :--- | :--- |
| FocusedWindow = null, FocusedApp 存在 | 无焦点窗口 ANR | 查启动耗时 |
| waitQueue length > 0, wait > 3000ms | App 处理慢 | 查 ANR trace 主线程 |
| outboundQueue length > 5 | InputDispatcher 端积压 | 查 waitQueue 串行化 |
| Connection status = BROKEN | InputChannel 异常断开 | 查 App 是否崩溃 |
| 无 FocusedApp 且无 FocusedWindow | 系统级问题 | 查 AMS / WMS 状态 |

### 4.3 按 ANR trace 主线程状态分类

| 主线程栈特征 | 诊断 | 修复方向 |
| :--- | :--- | :--- |
| SQLite / SharedPreferences | 主线程 IO | 异步化 |
| BinderProxy.transact | 主线程 Binder | 移到后台线程 |
| Object.wait / Lock.lock | 锁竞争 | 优化锁粒度 |
| nativePollOnce（空闲） | 瞬时卡顿已恢复 / 同步屏障泄漏 | 查 Systrace / 查屏障 |
| Bitmap.decode / Canvas.draw | 主线程渲染耗时 | 图片异步加载 |
| Application.onCreate | 冷启动阶段 | 启动优化 |

---

## 5. 实战案例

### Case 1：电商 App 商品详情页 — 同步屏障泄漏导致 ANR

**现象**：
商品详情页偶发 ANR，频率约 0.1%。但 ANR trace 主线程显示 `nativePollOnce`——主线程空闲？

**logcat**：
```
E ActivityManager: ANR in com.example.shop
E ActivityManager:   Reason: Input dispatching timed out
                     (Waiting because the focused window has not finished
                      processing the previous input event that was delivered
                      to it. Wait queue length: 8.)
```

**ANR trace**：
```
"main" prio=5 tid=1 Native
  at android.os.MessageQueue.nativePollOnce(Native Method)
  at android.os.MessageQueue.next(MessageQueue.java:335)
  at android.os.Looper.loopOnce(Looper.java:161)
```

**矛盾点**：
- dumpsys input 显示 waitQueue 有 8 个事件积压 → App 确实没有处理事件
- 但主线程在 `nativePollOnce` → 看起来空闲

**深入排查**：

1. 使用反射检查 MessageQueue 中的 Message 链表：
```java
Field messagesField = MessageQueue.class.getDeclaredField("mMessages");
messagesField.setAccessible(true);
Message msg = (Message) messagesField.get(Looper.getMainLooper().getQueue());
while (msg != null) {
    Log.d("MQ", "msg: target=" + msg.getTarget() + ", what=" + msg.what);
    Field nextField = Message.class.getDeclaredField("next");
    nextField.setAccessible(true);
    msg = (Message) nextField.get(msg);
}
```

2. 发现 MessageQueue 头部有一个 `target == null` 的 Message — 这就是**同步屏障**！

3. 追溯屏障来源：`ViewRootImpl.scheduleTraversals()` 添加了屏障，但由于商品详情页中一个自定义 View 的 `onMeasure` 抛出了未捕获的异常（被外层 try-catch 吞掉），导致 `performTraversals()` 提前返回 → `unscheduleTraversals()` 未执行 → 屏障未移除。

**根因**：
自定义 View 的 `onMeasure` 在特定数据下抛出 `NumberFormatException`。外层 `try-catch` 捕获了异常但没有正确处理，导致 `performTraversals` 的后续步骤被跳过。同步屏障泄漏后，所有同步消息（包括 Input 事件回调）被阻塞。

**修复**：
1. 修复 `onMeasure` 中的数据校验，防止异常
2. 添加同步屏障泄漏监控：定期检查 MessageQueue 中是否有长时间存在的同步屏障

---

### Case 2：视频播放器 — 全屏切换时的事件丢失

**现象**：
视频播放器从竖屏切换到横屏全屏时，用户快速点击暂停按钮无响应。需要等待约 1 秒后才能点击。

**排查过程**：

1. **不是 ANR**：没有 ANR 对话框，logcat 无 ANR 日志。

2. **getevent 确认**：硬件层事件正常产生。

3. **dumpsys input 分析**：
```
FocusedWindow: Window{... com.example.player/...VideoActivity}
Connection: status=NORMAL, outboundQueue=0, waitQueue=0
```
窗口正常、队列无积压 — 事件确实发给了 App。

4. **添加 touch log**：在 `ViewGroup.dispatchTouchEvent` 添加日志 → 发现 `ACTION_DOWN` 到达了 DecorView，但**没有被任何子 View 消费**。

5. **深入分析**：全屏切换时，Activity 触发了 `configurationChanged` → 重新布局 → 旧的 View 树被移除 → 新的 View 树正在 inflate → 此时用户点击 → `ACTION_DOWN` 到达已清空的 View 树 → 无 View 命中 → `mFirstTouchTarget = null` → 事件被静默丢弃。

**根因**：
全屏切换过程中存在约 200~500ms 的 View 树重建期。在此期间触摸屏幕，`ACTION_DOWN` 无法被任何 View 消费 → 后续事件序列全部无效。

**修复**：
1. 使用 `TransitionManager` 实现平滑过渡，避免完全重建 View 树
2. 在全屏切换期间保持暂停按钮的 View 不被移除（使用 `ViewStub` 延迟加载其他元素）
3. 添加一个透明的"事件缓冲层"，在切换期间捕获事件并在切换完成后重新投递

---

## 6. 风险全景总结图

```
Input 稳定性风险全景
│
├── Input ANR（最严重，60%+ ANR 来源）
│   ├── 主线程卡顿型 — onTouchEvent/onClick 中耗时操作
│   ├── 无焦点窗口型 — 冷启动慢 / Activity 切换真空期
│   ├── Binder 阻塞型 — 主线程跨进程调用
│   └── 同步屏障泄漏型 — 同步消息被阻塞
│
├── 触摸延迟（影响体验）
│   ├── 硬件/驱动层 — 采样率低 / 驱动慢
│   ├── InputDispatcher 层 — waitQueue 串行化等待
│   ├── 跨进程传输层 — socket buffer 积压
│   └── App 层 — 主线程消息排队 / View 树过深 / 渲染掉帧
│
└── 事件丢失（难排查）
    ├── InputDispatcher 端 — mInboundQueue 满 / touched nothing
    ├── InputChannel 层 — socket buffer 满
    └── App 层 — DOWN 未消费 / 事件拦截 / View 树重建
```

理解这张风险地图，就能在遇到 Input 相关问题时快速定位方向，而不是盲目排查。下一篇将介绍具体的诊断工具和延迟治理体系。

