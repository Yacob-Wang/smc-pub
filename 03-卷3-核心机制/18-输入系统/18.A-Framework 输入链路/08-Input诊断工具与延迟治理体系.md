# 08-Input 诊断工具与延迟治理体系

> **系列**：面向稳定性的 Android Input 子系统深度解析系列(Input_FWK)
>
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
>
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇工具涉及 `frameworks/native/services/inputflinger/`、`system/core` 工具链;Android 14 perfetto 增强 input event tracing 见 §3)
>
> **目标读者**:Android 稳定性框架架构师
>
> **前置阅读**:本系列 01-07 全篇
>
> **下一篇**:无(系列收官)

---

## 本篇定位

- **本篇系列角色**:系列收官篇(诊断工具 + 监控体系 + 治理实践)
- **强依赖**:本系列 01-07 全篇
- **承接自**:07 风险地图已建立。本篇聚焦"怎么查 + 怎么治 + 怎么防"
- **衔接去**:无(系列收官)
- **不重复内容**:风险的具体机制由 07 承担;本篇只做**工具使用 + 监控告警 + 治理工程化**

#### §0 锚点案例的可验证 4 件套:某支付 App 触摸响应 P99 240ms → 80ms,延迟治理闭环

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某支付 App v8.0(脱敏代号 `PayApp`,灰度 10% 监控告警)
> - 工具:`perfetto` + `dumpsys input` + `simpleperf` + 内部性能监控 SDK

> **复现步骤**(延迟治理闭环演练):
> 1. **0d**:监控告警 → PayApp 触摸响应 P99 = 240ms(目标 < 100ms)
> 2. **1d**:`perfetto` 抓 100 个触摸事件 trace,统计 5 段延迟分布
> 3. **2d**:`simpleperf` 火焰图定位主线程 onTouchEvent 热路径
> 4. **3-7d**:针对性优化:
>     - 自定义 View measure 缓存
>     - 异步图片加载
>     - 主线程移除同步 IO
> 5. **8d**:灰度 10% → P99 = 80ms(-66%),全量发布

> **logcat / Perfetto 关键片段**(优化前):
> ```
> # perfetto trace(优化前 P99=240ms)
> 触摸点 → onTouchEvent 延迟分桶:
>   InputDispatcher: 8ms (avg)
>   InputChannel.send: 4ms (avg)
>   App 主线程处理: 220ms (avg)         ← 主因!
>     - ViewRootImpl: 12ms
>     - dispatchTouchEvent: 8ms
>     - onMeasure 嵌套递归: 180ms       ← 大头
>     - onTouchEvent 业务: 20ms
> # simpleperf 火焰图
> 95%  [user]  com.pay.app.PayActivity.onMeasure
>       ↳ ComplexLayout.onMeasure (递归 8 层)
>       ↳ CostItemView.onMeasure (递归 3 层)
>       ↳ IconView.onMeasure (递归 2 层)
> 优化后:
> # perfetto trace(P99=80ms)
>   InputDispatcher: 8ms
>   InputChannel.send: 4ms
>   App 主线程处理: 65ms (avg)         ← -71%
>     - ViewRootImpl: 12ms
>     - dispatchTouchEvent: 8ms
>     - onMeasure (缓存命中): 25ms     ← 关键优化点
>     - onTouchEvent 业务: 20ms
> ```

> **修复 commit-style diff**(延迟治理闭环):
> ```diff
> --- a/app/src/main/java/com/pay/app/widget/CostItemView.java
> +++ b/app/src/main/java/com/pay/app/widget/CostItemView.java
> @@ onMeasure
> -    // 旧版:无 measure 缓存,每次都重算
> -    super.onMeasure(widthSpec, heightSpec);
> -    if (getLayoutParams().height == WRAP_CONTENT) {
> -        int childHeight = measureAllChildren();  // 50ms+
> -        setMeasuredDimension(getMeasuredWidth(), childHeight);
> -    }
> +    // 修复:measure 缓存 + 异步预计算,主线程首次 measure < 5ms
> +    if (mMeasureCache.isValid(widthSpec, heightSpec)) {
> +        setMeasuredDimension(mMeasureCache.width, mMeasureCache.height);
> +        return;
> +    }
> +    // 异步预计算(下一次 layout 之前)
> +    postAsync(() -> {
> +        mMeasureCache.set(widthSpec, heightSpec, measureAllChildren());
> +        requestLayout();  // 触发重绘
> +    });
> +    setMeasuredDimension(getDefaultSize(widthSpec), getDefaultSize(heightSpec));
> ```
> ```diff
> --- a/monitor/input_latency_dashboard.json
> +++ b/monitor/input_latency_dashboard.json
> @@ alerting
> -    { "name": "input_dispatch_avg", "threshold": "50ms", "page_on": true }
> +    { "name": "input_dispatch_avg", "threshold": "30ms", "page_on": true }
> +    { "name": "input_dispatch_p99", "threshold": "120ms", "page_on": true }
> +    { "name": "input_dispatch_p999", "threshold": "300ms", "page_on": true }
> +    { "name": "input_dispatch_rate", "threshold": "0.5%", "page_on": true }
> ```
> 完整 5 段延迟分布 ↔ 优化决策树 ↔ 监控告警 ↔ 工程闭环见 §2-§10。

## 引言

前七篇文章建立了 Input 系统的架构认知、机制理解和风险地图。本篇是系列的收官之作，聚焦于**"怎么查"和"怎么治"**：

- **诊断工具**：`getevent`、`dumpsys input`、`dumpsys window`、Systrace/Perfetto、ANR trace — 每个工具能看到什么、怎么看、怎么解读。
- **延迟监控体系**：从被动排查到主动预警 — 如何在线上建立 Input 延迟的监控能力。
- **治理最佳实践**：从"能查"到"能治"到"能防"的完整闭环。

---

## 1. getevent — 硬件层事件诊断

### 1.1 工具定位

`getevent` 直接读取 Linux 内核的 `/dev/input/eventX` 设备节点，是验证**硬件层事件是否正常**的第一工具。

它绕过了 EventHub → InputReader → InputDispatcher 的整个链路，如果 `getevent` 显示事件正常但用户感知不到响应，问题一定在内核层之上。

### 1.2 基本用法

```bash
# 列出所有输入设备
adb shell getevent -pl

# 实时查看所有设备的事件（带时间戳和标签解码）
adb shell getevent -lt

# 指定设备查看
adb shell getevent -lt /dev/input/event2
```

### 1.3 输出解读

```
[   12.345678] /dev/input/event2: EV_ABS  ABS_MT_TRACKING_ID  00000045
[   12.345678] /dev/input/event2: EV_ABS  ABS_MT_POSITION_X   000001f4
[   12.345678] /dev/input/event2: EV_ABS  ABS_MT_POSITION_Y   00000320
[   12.345678] /dev/input/event2: EV_ABS  ABS_MT_PRESSURE     0000003c
[   12.345678] /dev/input/event2: EV_KEY  BTN_TOUCH            DOWN
[   12.345678] /dev/input/event2: EV_SYN  SYN_REPORT           00000000
```

**关键字段**：

| 字段 | 含义 | 关注点 |
| :--- | :--- | :--- |
| 时间戳 `[12.345678]` | 内核时间（秒） | 相邻事件间隔反映采样率 |
| `EV_ABS` | 绝对坐标事件 | 触摸屏的核心事件类型 |
| `ABS_MT_TRACKING_ID` | 触摸点的 tracking ID | 新 ID = 手指按下；-1 = 手指抬起 |
| `ABS_MT_POSITION_X/Y` | 触摸坐标（原始值） | 是触摸屏分辨率，非屏幕分辨率 |
| `ABS_MT_PRESSURE` | 压力值 | 0 通常表示 hover |
| `SYN_REPORT` | 帧分隔符 | 一帧完整触摸数据的结束标记 |

### 1.4 诊断场景

**场景一：验证触摸屏是否正常**

用手指触摸屏幕，观察 getevent 输出：
- 有事件产生 → 硬件正常
- 无事件 → 驱动/硬件问题

**场景二：检测采样率**

```bash
# 快速滑动手指，观察 SYN_REPORT 的时间间隔
# 120Hz 触摸屏：间隔约 8.3ms
# 60Hz 触摸屏：间隔约 16.6ms
```

如果间隔远大于预期 → 驱动或硬件问题。

**场景三：检测坐标是否正确**

触摸屏幕四角，对比 `ABS_MT_POSITION_X/Y` 的值与预期范围（通过 `getevent -pl` 查看设备支持的坐标范围）。

**场景四：检测 ghost touch（幽灵触摸）**

不触摸屏幕时观察 getevent — 如果有事件自动产生，说明触摸屏硬件异常。

---

## 2. dumpsys input — 系统层状态诊断

### 2.1 工具定位

`dumpsys input` 输出 InputManagerService / InputReader / InputDispatcher 的完整状态快照。它是 Input 系统排查的**核心工具**。

```bash
adb shell dumpsys input
```

### 2.2 输出结构

`dumpsys input` 的输出分为几大块：

```
INPUT MANAGER (dumpsys input)

1. Event Hub State:        ← 设备列表和状态
2. Input Reader State:     ← InputReader 的设备和配置
3. Input Dispatcher State: ← 最重要！焦点、队列、连接状态
```

### 2.3 Event Hub State 解读

```
Input Devices:
  1: Touchscreen
    Path: /dev/input/event2
    Descriptors: ...
    Classes: 0x00000015 (TOUCH | TOUCHSCREEN | ...)
    Enabled: true
```

**关注点**：
- 设备是否被识别（`Input Devices` 列表中是否存在）
- 设备的 `Classes` 标志是否正确（TOUCH / KEYBOARD / ...）
- 设备是否 `Enabled`

### 2.4 Input Reader State 解读

```
Device 1: Touchscreen
  Sources: TOUCHSCREEN
  KeyboardType: NON_ALPHABETIC
  Motion Ranges:
    X: min=0.00, max=1079.00, flat=0.00, fuzz=0.00, resolution=0.00
    Y: min=0.00, max=2339.00, flat=0.00, fuzz=0.00, resolution=0.00
```

**关注点**：
- `Motion Ranges` 的 X/Y 范围是否与屏幕分辨率匹配
- `Sources` 是否正确识别

### 2.5 Input Dispatcher State 解读（最重要）

#### 焦点信息

```
FocusedApplications:
  displayId=0, name='AppWindowToken{abc com.example.app/.MainActivity}'

FocusedWindows:
  displayId=0, name='Window{def com.example.app/com.example.app.MainActivity}'
```

**解读规则**：

| 状态 | 含义 | 关联问题 |
| :--- | :--- | :--- |
| FocusedApp 有值 + FocusedWindow 有值 | 正常 | — |
| FocusedApp 有值 + FocusedWindow 为空 | App 启动中/窗口切换中 | 无焦点窗口 ANR |
| 两者都为空 | 系统级异常 | 系统问题 |

#### Connection 与队列状态

```
  Connection 0:
    inputChannel: 'abc...MainActivity (server)'
    status: NORMAL
    outboundQueue: length=2
      0: seq=123, eventId=456, ...
      1: seq=124, eventId=457, ...
    waitQueue: length=3
      0: seq=120, eventId=450, deliveryTime=..., wait=4800.0ms
      1: seq=121, eventId=451, deliveryTime=..., wait=3500.0ms
      2: seq=122, eventId=452, deliveryTime=..., wait=2100.0ms
```

**解读规则**：

| 状态 | 含义 | 风险等级 |
| :--- | :--- | :--- |
| waitQueue 为空 | App 处理正常 | 低 |
| waitQueue length=1, wait < 100ms | 正在处理事件 | 低 |
| waitQueue length ≥ 1, wait > 3000ms | App 处理严重延迟 | **高**（接近 ANR） |
| waitQueue length ≥ 3 | 多个事件积压 | **高** |
| outboundQueue length ≥ 1 | InputDispatcher 端等待 | 中（受 waitQueue 影响） |
| status=BROKEN | InputChannel 断开 | **严重** |

#### PendingEvent 信息

```
  PendingEvent:
    eventId=789, type=MOTION, action=MOVE
    inboundQueue length: 0
```

**关注 inboundQueue length**：如果大于 10，说明 InputReader 生产快于 InputDispatcher 消费。

### 2.6 实际排查示例

**问题：用户反馈触摸无响应**

执行 `dumpsys input`，发现：

```
FocusedWindows:
  displayId=0, name='Window{... StatusBar}'
```

焦点窗口是 StatusBar 而非 App！原因：通知栏下拉导致焦点切换。用户以为自己在操作 App，实际上焦点在 StatusBar 上 → 触摸事件被发给了 StatusBar。

---

## 3. dumpsys window — 窗口状态诊断

### 3.1 工具定位

`dumpsys window` 输出 WindowManagerService 的状态，用于查看窗口 Z-order、焦点窗口、InputChannel 注册情况。

```bash
# 查看所有窗口
adb shell dumpsys window windows

# 查看焦点信息
adb shell dumpsys window displays
```

### 3.2 关键信息

```
Window #3 Window{abc com.example.app/com.example.app.MainActivity}:
  mDisplayId=0 stackId=1 taskId=123
  mBaseLayer=21000 mSubLayer=0
  mAttrs={(0,0)(fillxfill) sim={adjust=resize} ...
    flags=FLAG_LAYOUT_IN_SCREEN ...}
  mHasSurface=true
  isVisible=true
  mInputChannel=InputChannel{...}
  mInputChannelToken=IBinder{...}
```

**关注点**：
- `mHasSurface=true` + `isVisible=true` → 窗口可见
- `mInputChannel` 是否存在 → InputChannel 是否注册
- `flags` 中的 `FLAG_NOT_TOUCHABLE` / `FLAG_NOT_TOUCH_MODAL` → 影响触摸事件投递
- 窗口的 Z-order（`mBaseLayer`）→ 决定哪个窗口在最上面

### 3.3 常见排查场景

**场景：事件发给了错误窗口**

通过 `dumpsys window windows` 查看窗口 Z-order：
```
Window #0: StatusBar (layer=21000)           ← 最上层
Window #1: NavigationBar (layer=20000)
Window #2: com.example.app/.MainActivity (layer=10000)
Window #3: com.other.app/.OtherActivity (layer=9000)   ← 底层
```

如果有一个透明的系统窗口覆盖在 App 上方（如第三方悬浮窗），触摸事件可能被它拦截。

---

## 4. Systrace / Perfetto — 性能可视化分析

### 4.1 工具定位

Systrace（旧版）和 Perfetto（新版）是 Android 性能分析的主力工具，能够**可视化 Input 事件从 InputReader → InputDispatcher → App 的完整链路**。

### 4.2 抓取 Input 相关 Systrace

```bash
# 使用 perfetto（推荐）
adb shell perfetto \
  -c - --txt \
  -o /data/misc/perfetto-traces/input.perfetto-trace \
<<EOF
buffers: {
  size_kb: 63488
  fill_policy: RING_BUFFER
}
data_sources: {
  config {
    name: "linux.ftrace"
    ftrace_config {
      ftrace_events: "sched/sched_switch"
      ftrace_events: "power/suspend_resume"
      atrace_categories: "input"
      atrace_categories: "view"
      atrace_categories: "wm"
      atrace_categories: "am"
      atrace_apps: "com.example.app"
    }
  }
}
duration_ms: 10000
EOF
```

关键 atrace categories：
- `input` — InputReader / InputDispatcher 事件处理
- `view` — View 的 measure / layout / draw
- `wm` — WindowManager 操作
- `am` — ActivityManager（ANR 相关）

### 4.3 Systrace 中的 Input 事件分析

在 Perfetto UI 中，展开 `system_server` 进程：

```
InputReader:
  ├── loopOnce [0.2ms]    ← 读取一批事件
  ├── loopOnce [0.1ms]
  └── ...

InputDispatcher:
  ├── dispatchOnce [0.3ms]    ← 分发事件
  │   ├── findTouchedWindowTargets [0.05ms]
  │   └── dispatchEventLocked [0.1ms]
  └── ...
```

展开 App 进程：

```
MainThread:
  ├── input [deliverInputEvent]   ← 接收并处理事件
  │   ├── ViewPostImeInputStage [0.5ms]
  │   │   └── dispatchTouchEvent [0.3ms]
  │   └── finishInputEvent [0.01ms]   ← 回复 InputDispatcher
  └── ...
```

### 4.4 关键分析点

**端到端延迟测量**：
- 从 InputReader.loopOnce 的开始 → App 的 finishInputEvent → 计算总延迟
- 理想值 < 20ms，> 50ms 用户可感知

**延迟分段定位**：

| 阶段 | Systrace 中的标记 | 正常耗时 | 异常判断 |
| :--- | :--- | :--- | :--- |
| InputReader | `loopOnce` | < 2ms | > 5ms 异常 |
| InputDispatcher | `dispatchOnce` | < 2ms | > 5ms 异常（锁竞争？） |
| 跨进程传输 | InputReader 结束 → App input 开始 | < 2ms | > 10ms 异常 |
| App 处理 | `deliverInputEvent` / `dispatchTouchEvent` | < 10ms | > 16ms 有掉帧风险 |
| 主线程排队 | 前一个消息结束 → input 事件开始 | 越小越好 | > 16ms 有排队延迟 |

**掉帧与触摸延迟的关系**：
- Choreographer 的 `doFrame` 应该在 16ms（60fps）或 8ms（120fps）内完成
- 如果 `doFrame` 超时 → 下一帧延迟渲染 → 即使 Input 处理及时，视觉反馈也延迟

### 4.5 Perfetto SQL 查询

Perfetto 支持 SQL 查询来精确分析 Input 延迟：

```sql
-- 查找所有 Input 事件处理耗时 > 16ms 的实例
SELECT
  ts,
  dur / 1000000.0 as dur_ms,
  name
FROM slice
WHERE name LIKE '%deliverInputEvent%'
  AND dur > 16000000  -- 16ms in nanoseconds
ORDER BY dur DESC
LIMIT 20;
```

---

## 5. ANR trace 中的 Input 信息解读

### 5.1 获取 ANR trace

```bash
# 实时抓取
adb shell am hang  # 或等待自然发生的 ANR

# 获取 traces 文件
adb pull /data/anr/
```

### 5.2 主线程状态分析决策树

```
查看主线程 tid=1 的堆栈
    │
    ├── 栈底是 nativePollOnce ?
    │   ├── 是 → 主线程空闲
    │   │   ├── dumpsys input waitQueue 有积压 → 同步屏障泄漏（见第 07 篇）
    │   │   └── dumpsys input waitQueue 无积压 → 瞬时卡顿已恢复
    │   │       └── 需要 Systrace 回溯分析
    │   │
    │   └── 否 → 主线程正在执行代码 ↓
    │
    ├── 栈中有 BinderProxy.transact ?
    │   └── 是 → Binder 阻塞型
    │       → 确定对端服务 → 检查对端状态
    │
    ├── 栈中有 Object.wait / Lock.lock / synchronized ?
    │   └── 是 → 锁竞争
    │       → 查看锁持有者（trace 中的 "held by thread X"）
    │
    ├── 栈中有 SQLite / SharedPreferences / File ?
    │   └── 是 → 磁盘 IO
    │       → commit → apply / 查询异步化
    │
    ├── 栈中有业务代码（自定义类）?
    │   └── 是 → 业务逻辑耗时
    │       → 分析该方法是否应该在主线程执行
    │
    └── 栈中有 Application.onCreate ?
        └── 是 → 冷启动阶段（通常配合"no focused window"）
            → 启动优化
```

### 5.3 关键线程分析

除了主线程，还应关注以下线程：

| 线程名 | 关注点 |
| :--- | :--- |
| `Signal Catcher` | dump 堆栈的线程，确认 trace 是否完整 |
| `Binder:pid_X` | Binder 线程是否全部被占满 → 可能导致主线程 Binder 调用阻塞 |
| `RenderThread` | 渲染线程状态 → 如果 RenderThread 卡顿可能导致 `dequeueBuffer` 阻塞主线程 |
| `FinalizerDaemon` | 如果 Finalizer 超时 → 可能触发 GC 卡顿 |
| `HeapTaskDaemon` | GC 线程 → 频繁 GC 可能导致主线程 STW |

### 5.4 结合 logcat / dumpsys / trace 的三合一分析

```
排查 Input ANR 的标准流程：

1. logcat → 确认 ANR 类型（reason 字段）
   ├── "no focused window" → 跳到步骤 3a
   └── "has not finished processing" → 跳到步骤 2

2. dumpsys input → 确认事件积压情况
   ├── waitQueue wait > 5000ms → 确认 App 处理慢 → 跳到步骤 3b
   └── FocusedWindow=null → 跳到步骤 3a

3a. 无焦点窗口：
   → traces.txt 主线程 → 应该在 Application.onCreate / Activity.onCreate
   → 找到启动阶段的耗时操作
   → 优化启动

3b. 主线程处理慢：
   → traces.txt 主线程堆栈 → 定位耗时操作
   → 结合 CPU usage 判断 CPU/IO/锁
   → 异步化耗时操作

4. 如果 trace 主线程为 nativePollOnce：
   → 检查同步屏障 / 使用 Systrace 回溯
```

---

## 6. Input 延迟监控体系

从被动的"出了问题再排查"转向主动的"实时监控 + 预警"。

### 6.1 Choreographer.FrameCallback 掉帧监控

```java
public class FrameMonitor implements Choreographer.FrameCallback {
    private long mLastFrameTimeNanos = 0;

    @Override
    public void doFrame(long frameTimeNanos) {
        if (mLastFrameTimeNanos != 0) {
            long intervalMs = (frameTimeNanos - mLastFrameTimeNanos) / 1_000_000;
            if (intervalMs > 32) {
                // 掉帧（超过 2 帧 @60fps）
                reportJank(intervalMs);
            }
        }
        mLastFrameTimeNanos = frameTimeNanos;
        Choreographer.getInstance().postFrameCallback(this);
    }
}

// 注册
Choreographer.getInstance().postFrameCallback(new FrameMonitor());
```

**局限性**：掉帧不等于 Input 延迟。但掉帧是 Input 延迟的间接指标——如果频繁掉帧，触摸响应一定不流畅。

### 6.2 自定义 InputEventReceiver 统计事件处理耗时

通过 Hook 或继承 `InputEventReceiver`，在事件接收和 finishInputEvent 之间统计耗时：

```java
public class MonitoredInputEventReceiver extends InputEventReceiver {
    @Override
    public void onInputEvent(InputEvent event) {
        long startTime = SystemClock.uptimeMillis();
        // ... 正常处理
        long duration = SystemClock.uptimeMillis() - startTime;
        if (duration > 100) {
            reportSlowInputEvent(event, duration);
        }
    }
}
```

更精确的方案：在 `ViewRootImpl` 的 `deliverInputEvent` 前后插入计时（需要 Hook）。

### 6.3 Looper Printer 监控主线程消息耗时

```java
Looper.getMainLooper().setMessageLogging(new Printer() {
    private long startTime;
    private String startMsg;

    @Override
    public void println(String msg) {
        if (msg.startsWith(">>>>> Dispatching")) {
            startTime = SystemClock.uptimeMillis();
            startMsg = msg;
        }
        if (msg.startsWith("<<<<< Finished")) {
            long duration = SystemClock.uptimeMillis() - startTime;
            if (duration > 100) {
                // 慢消息
                reportSlowMessage(startMsg, msg, duration);
                // 可以在这里采集主线程堆栈
            }
        }
    }
});
```

**进阶方案**：使用 `Looper.Observer`（Android 10+）或 `MessageQueue.IdleHandler` 实现更低开销的监控。

### 6.4 dispatchTouchEvent 耗时统计

通过 Hook `ViewGroup.dispatchTouchEvent` 统计 View 树分发耗时：

```java
// 使用 ASM/ByteBuddy 插桩方案
public aspect TouchDispatchMonitor {
    Object around(ViewGroup vg, MotionEvent ev):
        execution(boolean ViewGroup.dispatchTouchEvent(MotionEvent))
        && args(ev) && this(vg) {
        long start = System.nanoTime();
        Object result = proceed(vg, ev);
        long duration = (System.nanoTime() - start) / 1_000_000;
        if (duration > 16) {
            // View 树分发耗时超过一帧
            reportSlowDispatch(vg.getClass().getName(), duration);
        }
        return result;
    }
}
```

### 6.5 线上监控指标设计

| 指标 | 采集方式 | 阈值 | 告警级别 |
| :--- | :--- | :--- | :--- |
| Input ANR 率 | ANR 日志上报 | > 0.1% | P0 |
| 触摸事件处理 P99 耗时 | InputEventReceiver Hook | > 100ms | P1 |
| 主线程消息 P99 耗时 | Looper Printer | > 200ms | P1 |
| 掉帧率（> 2 帧） | FrameCallback | > 5% | P2 |
| 触摸到渲染端到端延迟 | Perfetto（线下） | > 100ms | P1 |
| 同步屏障存活时间 | MessageQueue 检查 | > 5s | P0 |

---

## 7. 治理最佳实践

### 7.1 onTouchEvent / onClick 中禁止耗时操作

这是最基本的规则，但线上违反的比例极高。

**治理手段**：
- **StrictMode**（开发阶段）：检测主线程 IO
- **Lint 规则**（编译阶段）：自定义 Lint 检查 onClick / onTouchEvent 中的 DB / File / Network 调用
- **字节码插桩**（CI 阶段）：在 onClick 方法入口/出口插入耗时检测
- **线上监控**（运行阶段）：Looper Printer + InputEventReceiver Hook

```kotlin
// 自定义 Lint 规则示例伪代码
class MainThreadIoDetector : Detector(), SourceCodeScanner {
    override fun getApplicableMethodNames(): List<String> =
        listOf("onClick", "onTouchEvent", "onTouch")

    override fun visitMethodCall(context: JavaContext, node: UCallExpression,
                                  method: PsiMethod) {
        if (isIoCall(method)) {
            context.report(ISSUE, node, context.getLocation(node),
                "IO operation in touch/click callback may cause ANR")
        }
    }
}
```

### 7.2 嵌套滑动冲突的标准化解决方案

| 场景 | 推荐方案 |
| :--- | :--- |
| ViewPager + RecyclerView | NestedScrollView + ViewPager2（内置嵌套滑动支持） |
| ScrollView + RecyclerView | 替换为 RecyclerView（不嵌套），使用多类型 ViewHolder |
| CoordinatorLayout + AppBar + RecyclerView | 使用标准 Behavior，不自定义拦截逻辑 |
| 自定义手势 + 系统滑动 | requestDisallowInterceptTouchEvent 内部拦截法 |

**原则**：优先使用系统标准组件和 NestedScrolling API，避免自定义 onInterceptTouchEvent。

### 7.3 冷启动优化 — 确保窗口快速就绪

防止"无焦点窗口" ANR 的核心是让 Window 在 5 秒内就绪（越快越好）。

```
启动链路：
fork → Application.onCreate → Activity.onCreate → setContentView
     → ViewRootImpl.setView → WMS.addWindow → InputChannel 创建
     → FocusedWindow 就绪
     
优化方向：
├── Application.onCreate 轻量化（< 500ms）
│   ├── 延迟非关键 SDK 初始化
│   ├── 使用 AppStartup 按需初始化
│   └── 禁止跨进程同步调用
├── Activity.onCreate 轻量化
│   ├── 布局简化（减少 View 层级）
│   ├── 数据加载异步化
│   └── 使用 ViewStub 延迟加载
└── 使用 SplashScreen API（Android 12+）
    └── 系统在进程启动时就显示 SplashScreen → 窗口提前就绪
```

### 7.4 主线程 Binder 调用管控

```kotlin
// 线上 Hook Binder.transact 统计
// 使用 Epic / SandHook 等 Hook 框架
fun hookBinderTransact() {
    XposedHelpers.findAndHookMethod(
        BinderProxy::class.java, "transact",
        Int::class.java, Parcel::class.java, Parcel::class.java, Int::class.java,
        object : XC_MethodHook() {
            override fun beforeHookedMethod(param: MethodHookParam) {
                if (Looper.getMainLooper() == Looper.myLooper()) {
                    val startTime = SystemClock.uptimeMillis()
                    param.extra = startTime
                }
            }
            override fun afterHookedMethod(param: MethodHookParam) {
                val startTime = param.extra as? Long ?: return
                val duration = SystemClock.uptimeMillis() - startTime
                if (duration > 50) {
                    reportMainThreadBinder(
                        param.thisObject.toString(), duration)
                }
            }
        }
    )
}
```

### 7.5 同步屏障泄漏防护

```kotlin
// 定期检查 MessageQueue 中是否有长时间存在的同步屏障
class SyncBarrierMonitor : Runnable {
    override fun run() {
        try {
            val queue = Looper.getMainLooper().queue
            val messagesField = MessageQueue::class.java
                .getDeclaredField("mMessages")
            messagesField.isAccessible = true
            val nextField = Class.forName("android.os.Message")
                .getDeclaredField("next")
            nextField.isAccessible = true
            val targetField = Class.forName("android.os.Message")
                .getDeclaredField("target")
            targetField.isAccessible = true

            var msg = messagesField.get(queue)
            while (msg != null) {
                val target = targetField.get(msg)
                if (target == null) {
                    // 发现同步屏障！
                    reportSyncBarrierLeak()
                    break
                }
                msg = nextField.get(msg)
            }
        } catch (e: Exception) {
            // ignore
        }
        // 每 5 秒检查一次
        handler.postDelayed(this, 5000)
    }
}
```

### 7.6 控制主线程消息耗时预算

```
目标：每条主线程消息执行时间 < 16ms（一帧）

实施：
├── 大任务拆分：将耗时 > 16ms 的操作拆成多个小任务
│   └── 使用 Handler.post / postDelayed 分帧执行
├── IO 异步化：所有磁盘/网络操作移到后台线程
├── 计算异步化：复杂计算使用 Dispatchers.Default
└── 监控告警：Looper Printer 监控 > 100ms 的消息并上报
```

---

## 8. 实战案例

### Case 1：游戏 App — Systrace 定位触摸延迟

**现象**：
一款手游在中低端设备上，用户反馈操控角色时"手感延迟"。通过用户端测试，触摸到角色移动的延迟约 80~120ms。

**排查过程**：

1. **getevent 检测**：硬件层事件正常，采样率 120Hz（间隔约 8ms）。

2. **Perfetto 抓取**：使用 `input` + `view` + App atrace 标签录制 10 秒操作。

3. **Perfetto 分析**：

```
[InputReader] loopOnce: 0.3ms                     ← 正常
[InputDispatcher] dispatchOnce: 0.8ms              ← 正常
                 ┌── gap: 12ms ──┐                 ← 跨进程延迟偏大
[App MainThread] deliverInputEvent: 2ms            ← 正常
                 ┌── gap: 45ms ──┐                 ← 异常！
[App MainThread] Choreographer.doFrame: 32ms       ← 掉帧！
                 └── ViewRootImpl.performDraw: 28ms ← 渲染耗时
```

4. **定位**：触摸事件处理本身很快（2ms），但渲染帧耗时 32ms（超过 16ms 一帧），导致视觉反馈延迟一帧（+16ms）。加上事件从处理到下一帧渲染的等待时间（45ms），总视觉延迟 = 事件传输(~15ms) + 事件处理(2ms) + 等待下一帧(~45ms) + 渲染(32ms) ≈ 94ms。

5. **根因**：游戏的自定义 View 在 `onDraw` 中执行了过多的 Canvas 操作，且没有使用硬件加速的一些 API → 每帧渲染耗时 > 16ms → 掉帧 → 触摸反馈延迟。

**修复**：
1. 开启硬件加速（`android:hardwareAccelerated="true"`）
2. 将复杂绘制操作移到 RenderThread（使用 `RenderNode`）
3. 使用 `MotionEvent.getHistoricalX/Y` 处理 batched events，减少位置更新的不连贯感
4. 修复后延迟降至 40~60ms（接近系统底线）

---

### Case 2：社交 App — 建立 Input 延迟监控体系

**背景**：
一款社交 App 在版本迭代中，触摸延迟问题逐渐恶化，但因为没有监控，直到用户大量投诉才发现。决定建立系统性的 Input 延迟监控。

**实施过程**：

**第一阶段：建立基础指标**

```kotlin
// 1. 掉帧监控
class JankMonitor : Choreographer.FrameCallback {
    private var lastFrameTime = 0L
    override fun doFrame(frameTimeNanos: Long) {
        if (lastFrameTime > 0) {
            val jankMs = (frameTimeNanos - lastFrameTime) / 1_000_000 - 16
            if (jankMs > 0) {
                MetricsReporter.report("input_jank", jankMs)
            }
        }
        lastFrameTime = frameTimeNanos
        Choreographer.getInstance().postFrameCallback(this)
    }
}

// 2. 主线程消息耗时监控
Looper.getMainLooper().setMessageLogging { msg ->
    // ... 见前文 Looper Printer 实现
}

// 3. Input ANR 率上报
Thread.setDefaultUncaughtExceptionHandler { _, e ->
    // 捕获 ANR 相关信息
}
```

**第二阶段：建立告警规则**

| 指标 | 黄色告警 | 红色告警 |
| :--- | :--- | :--- |
| Input ANR 率 | > 0.05% | > 0.1% |
| 掉帧率 (>2帧) | > 3% | > 5% |
| 主线程消息 P99 | > 150ms | > 300ms |
| Touch 处理 P99 | > 80ms | > 150ms |

**第三阶段：归因与治理**

当指标超过阈值时，自动采集：
- 主线程堆栈（通过后台线程采样）
- 当前页面和 View 树深度
- 内存使用和 GC 频率
- 慢消息的 Message.what / Handler 类名

```kotlin
// 慢消息归因
fun parseSlowMessage(msg: String): MessageInfo {
    // ">>>>> Dispatching to Handler (android.app.ActivityThread$H) {abc}
    //  null: 100"
    val handlerPattern = Regex("Handler \\((.*?)\\)")
    val handler = handlerPattern.find(msg)?.groupValues?.get(1) ?: "unknown"
    val whatPattern = Regex("null: (\\d+)")
    val what = whatPattern.find(msg)?.groupValues?.get(1)?.toInt() ?: -1
    return MessageInfo(handler, what)
}
```

**效果**：
- 上线监控后 2 周内，发现 3 个新增的主线程 IO 操作（来自新版本代码），在造成大范围 ANR 前修复
- Input ANR 率从 0.15% 降至 0.03%
- 掉帧率从 8% 降至 2.5%

---

## 9. 治理体系总结

```
Input 稳定性治理的"三能"体系

能查 → 诊断工具矩阵
├── getevent          — 硬件层验证
├── dumpsys input     — 系统层状态
├── dumpsys window    — 窗口层状态
├── Systrace/Perfetto — 性能可视化
└── ANR trace         — 根因定位

能治 → 问题修复模式
├── 主线程 IO → 异步化（apply/协程/后台线程）
├── 主线程 Binder → 移到后台线程
├── 冷启动慢 → Application.onCreate 轻量化 + SplashScreen
├── 滑动冲突 → NestedScrolling API
├── View 树过深 → ConstraintLayout 扁平化
├── 同步屏障泄漏 → 定期检测 + 异常保护
└── 渲染掉帧 → 硬件加速 + RenderThread + 减少 overdraw

能防 → 监控预警闭环
├── 线上指标：ANR 率 / 掉帧率 / 慢消息 P99 / Touch 处理 P99
├── 告警规则：黄色/红色分级
├── 归因能力：自动采集堆栈 + 页面 + 上下文
├── CI 检测：Lint 规则 + 字节码插桩
└── 质量门禁：版本发布前性能回归测试
```

从"出了问题再排查"到"版本发布前就能防住"，这就是 Input 稳定性治理的完整闭环。

