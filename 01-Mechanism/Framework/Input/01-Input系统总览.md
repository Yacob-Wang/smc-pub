# 01-Input 系统总览：从触摸屏到 App 响应的全链路

> **系列**：面向稳定性的 Android Input 子系统深度解析系列(Input_FWK)
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `drivers/input/evdev.c`、`include/linux/input.h`、`frameworks/native/services/inputflinger/`;Android 14 InputFlinger 重构见 §3)
> **目标读者**:Android 稳定性框架架构师
> **前置阅读**:`Android_Framework/Input/README-Input系列.md`
> **下一篇**:[02-EventHub 与 InputReader](02-EventHub与InputReader.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 1 篇(Input 系统总览,建立"硬件 → InputFlinger → App"全链路认知)
- **强依赖**:
  - [Socket 01-Socket 总览](../01-Mechanism/Kernel/socket/01-Socket总览.md)(UDS socketpair 是 InputChannel 底层,本篇会涉及)
  - [IO 06-IO 与进程](../01-Mechanism/Kernel/IO/06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md)(D 状态 + ANR 判定)
- **承接自**:Input 系列首篇,无前置正文
- **衔接去**:
  - 02 深入 EventHub 与 InputReader(硬件读取层)
  - 03 深入 InputDispatcher(事件分发层)
  - 04 讲 InputChannel(跨进程传递机制)
- **不重复内容**:EventHub 的 epoll 机制详见 02 §2;InputDispatcher 的 ANR 判定详见 06 §3;View 事件分发详见 05

#### §0 锚点案例的可验证 4 件套:滑动列表触摸延迟 200ms 的全链路定位演练

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某 IM App v8.5(脱敏代号 `ChatApp`,聊天列表滑动测试)
> - 工具:`dumpsys input` + `perfetto` + `simpleperf` + `Input latency meter`(`-e input:*`)

> **复现步骤**:
> 1. 工厂重置,安装 ChatApp v8.5
> 2. 进入聊天列表 → 快速上下滑动(每秒 4 次)
> 3. `perfetto -o trace.pftrace -t 10s -c input.pbtx` 抓 Input 全链路 trace
> 4. `adb shell getevent -lt /dev/input/event2 -c 1` 看单次触摸到上报时间
> 5. `dumpsys input | grep -A 5 "Recent Queue Latency"` 看分发延迟

> **logcat / Perfetto 关键片段**:
> ```
> # perfetto trace(单次滑动触摸)
> 14:32:18.001 kernel:  input_event EV_ABS /dev/input/event2  (触摸硬件触发)        +0ms
> 14:32:18.005 EventHub:  read_notify  → InputReader poll 完成                       +4ms
> 14:32:18.012 InputReader:  processEvents → MotionEvent 生成                      +7ms
> 14:32:18.020 InputDispatcher:  findTargetWindow → 选择 ChatApp MainActivity     +8ms
> 14:32:18.025 InputChannel:  send  → 通过 socketpair 发到 App                     +5ms
> 14:32:18.205 ViewRootImpl:  dispatchInputEvent → RecyclerView.onTouchEvent     +180ms  ← 延迟大!
>                                                       ↑
>                                          App 主线程忙(正在 bindViewHolder),触摸事件排队 180ms
> # 总延迟:200ms(用户感知明显卡顿)
> # dumpsys input
> Recent Queue Latency: 12ms (avg)
> Recent Process Latency: 180ms (avg)        ← 进程处理延迟大
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
> +++ b/frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java
> @@ enqueueTouchEvent()
> -    // 旧版:触摸事件发到 App 直接排队等待主线程
> -    inputChannel.sendMotionEvent(event);
> +    // 修复:主线程忙时降级为 INPUT_FEATURE_NO_INPUT_CHANNEL 异步投递
> +    if (mainThreadIsBusy > 50ms) {
> +        inputChannel.sendMotionEventAsync(event);  // 走 InputManager 直送 View
> +    } else {
> +        inputChannel.sendMotionEvent(event);
> +    }
> ```
> ```diff
> --- a/app/src/main/java/com/chat/app/ChatListFragment.kt
> +++ b/app/src/main/java/com/chat/app/ChatListFragment.kt
> @@ onBindViewHolder
> -    // 旧版:RecyclerView 绑定时同步加载图片,主线程卡 180ms
> -    holder.avatar.setImageBitmap(loadAvatarSync(item))
> +    // 修复:图片异步加载 + 占位图 + 缓存复用
> +    holder.avatar.setImageBitmap(avatarCache.get(item.url, holder.avatar))
> ```
> 完整 Input 链路 ↔ 延迟分桶 ↔ ANR 触发 ↔ 优化决策见 §3 §4 §5。

## 1. Input 系统是什么

用户与 Android 设备的一切交互——指尖划过屏幕的触摸、实体按键的按压、蓝牙手柄的摇杆偏移、手写笔的悬浮与压感——都必须经过 Input 系统的处理管线，才能最终到达应用的 `onTouchEvent` 或 `onKeyDown`。**Input 系统是 Android 的"感觉神经系统"**：它负责感知外部世界的物理输入，将其转化为 Android 语义下的事件对象（`MotionEvent`、`KeyEvent`），再精准投递到正确的窗口。

**用一句话定义：** Input 系统是 Android 中负责从硬件设备读取原始输入事件、将其语义化为 Android 事件对象、选择目标窗口并跨进程投递、最终交由 View 树消费的完整处理管线。

### 1.1 Input 系统在 Android 生态中的角色

Input 系统是连接**硬件世界**与**应用世界**的桥梁。它向下对接 Linux Kernel 的 Input 子系统（`/dev/input/eventX`），向上为每个 App 提供标准化的事件流。与 Binder 类似，Input 系统是 Android 系统的基础设施——它自身不可见，但所有用户可感知的交互都依赖它。


| 维度      | Input 系统的角色                                                             |
| ------- | ----------------------------------------------------------------------- |
| 硬件抽象    | 屏蔽不同触摸屏控制器、键盘驱动、传感器协议的差异，为上层提供统一的事件模型                                   |
| 安全隔离    | App 无法直接读取 `/dev/input/`，所有事件由 `system_server` 中的 InputFlinger 组件中转     |
| 多窗口仲裁   | 系统同时存在多个窗口（Activity、Dialog、StatusBar、NavigationBar、IME），Input 系统决定事件发给谁 |
| ANR 守门人 | InputDispatcher 监控 App 是否在 5 秒内处理了事件，是 Input ANR 的唯一裁判                  |
| 性能关键路径  | 从触摸到屏幕响应的总延迟中，Input 管线的处理时间直接影响用户体验                                     |


### 1.2 Input 系统的历史演进

Input 系统并非一成不变。从 Android 1.0 到如今的 Android 14+，它经历了多轮重构：


| 版本                       | 关键演进                                                                         |
| ------------------------ | ---------------------------------------------------------------------------- |
| Android 1.0–2.3          | Input 系统完全运行在 Java 层（`WindowManagerService` 内），单线程处理读取与分发，性能瓶颈明显             |
| Android 4.0 (ICS)        | 将核心逻辑迁移到 Native 层，引入 `InputReader` / `InputDispatcher` 双线程模型（`inputflinger`） |
| Android 4.1 (Jelly Bean) | 配合 Project Butter，引入 Touch Boost 和 VSync 对齐，降低触摸延迟                           |
| Android 10               | 引入 Input Pipeline 的 `InputClassifier`，支持机器学习驱动的手掌误触检测                        |
| Android 12               | 支持多指多窗口分发（Split Touch），同一触摸序列可分发到不同窗口                                        |
| Android 14               | 多设备输入支持（Multi-device Input）、触摸预测（Touch Prediction）、更精细的 ANR 信息               |


理解这些演进有助于在阅读 AOSP 源码时区分"历史遗留"和"当前设计"。

---

## 2. 为什么需要如此复杂的五层架构

初次接触 Input 系统的架构师可能会疑惑：一个触摸事件从硬件到 App，为什么需要穿越五层？直接让 App 读 `/dev/input/eventX` 不好吗？答案是：**不行**。Input 系统的五层架构不是过度设计，而是由四个核心驱动力决定的。

### 2.1 设计驱动力一：安全隔离

`/dev/input/eventX` 包含设备的所有输入事件——触摸坐标、按键码、甚至指纹传感器的原始数据。如果任意 App 能直接读取这些节点，就意味着：

- 恶意 App 可以实时监控用户的所有触摸操作（键盘记录器）
- 恶意 App 可以读取其他 App 窗口上的触摸事件

因此，Android 要求 `/dev/input/eventX` 只有 `system` 或 `input` 用户组才能访问。所有事件必须由 `system_server` 中的 InputFlinger 读取，经过安全策略过滤后，才通过 `InputChannel`（Unix Domain Socket）投递到对应的 App。

### 2.2 设计驱动力二：多窗口仲裁

Android 的屏幕上同时存在多个窗口，它们按 Z-order 层叠：

```
Z-order 从高到低:
  ┌─────────────────────────┐
  │    StatusBar Window      │  ← 最高层
  ├─────────────────────────┤
  │    Dialog Window         │
  ├─────────────────────────┤
  │    Activity Window       │  ← 主要交互窗口
  ├─────────────────────────┤
  │    NavigationBar Window  │  ← 底部导航栏
  └─────────────────────────┘
```

当用户触摸屏幕时，Input 系统必须回答：**这个触摸点落在哪个窗口内？** 这需要知道每个窗口的位置、大小、可见性、是否可穿透（`FLAG_NOT_TOUCHABLE`）、是否遮挡下层（`FLAG_NOT_TOUCH_MODAL`）等信息。只有 `system_server` 中的 InputDispatcher 才拥有完整的窗口信息（来自 WMS），因此窗口选择逻辑必须在系统侧完成。

### 2.3 设计驱动力三：ANR 检测

系统必须保证用户的触摸在合理时间内得到响应。如果 App 无限期阻塞在处理一个触摸事件上，后续事件全部排队，用户体验为"手机死了"。为此，InputDispatcher 实现了 **5 秒超时检测机制**：

1. 向 App 发送事件时，记录发送时间
2. 如果 5 秒内没有收到 App 的 `finishInputEvent` 回复，触发 ANR 流程
3. 通知 AMS → 弹出 ANR 对话框或直接杀进程

这个监控机制必须在系统侧实现——App 自己不可能监控自己是否卡了。

### 2.4 设计驱动力四：性能优化

Input 系统将**事件读取**和**事件分发**分到两个独立线程：

- `InputReaderThread`：从 EventHub 读取原始事件，转化为 Android 事件。这个过程涉及 `epoll_wait` 阻塞等待、坐标变换、手势识别等。
- `InputDispatcherThread`：选择目标窗口，将事件发送到 App。这个过程涉及窗口查询、ANR 检测、跨进程通信等。

两个线程通过 `mInboundQueue`（生产者-消费者队列）解耦。读取慢不会阻塞分发，分发慢不会阻塞读取。这种设计保证了即使 App 处理事件很慢（导致分发端等待），系统仍能继续读取新事件，不会丢失硬件上报的事件。

### 2.5 如果没有这些约束会怎样？


| 缺失的架构约束  | 后果                                     |
| -------- | -------------------------------------- |
| 无安全隔离    | 任意 App 可做键盘记录器，窃取密码和隐私输入               |
| 无多窗口仲裁   | 触摸事件可能发给被遮挡的窗口，或同时发给多个不相关窗口            |
| 无 ANR 检测 | App 卡死时用户只能强制重启设备，无法感知和恢复              |
| 单线程读取分发  | App 处理慢 → 系统无法读取新事件 → 硬件事件缓冲区溢出 → 事件丢失 |


---

## 3. 五层架构全景图

### 3.1 架构全景

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Application Layer (App 进程)                         │
│   ViewRootImpl → InputStage Pipeline → View.dispatchTouchEvent             │
│   WindowInputEventReceiver ← InputChannel (client fd)                      │
│   frameworks/base/core/java/android/view/                                  │
├───────────────────────────────── ↑ InputChannel (socketpair) ──────────────┤
│                        Framework Layer (system_server 进程)                 │
│   InputManagerService ← JNI → NativeInputManager                          │
│   frameworks/base/services/core/java/com/android/server/input/            │
├───────────────────────────────── ↑ JNI ────────────────────────────────────┤
│                        Native Layer (system_server 进程)                    │
│   InputManager → InputReader (Thread) → InputDispatcher (Thread)           │
│   InputClassifier (手掌检测)                                                │
│   frameworks/native/services/inputflinger/                                 │
├───────────────────────────────── ↑ read() ─────────────────────────────────┤
│                        HAL Abstraction Layer (system_server 进程)           │
│   EventHub: epoll 监听 /dev/input/eventX, 封装 Linux Input 子系统          │
│   frameworks/native/services/inputflinger/reader/EventHub.cpp              │
├───────────────────────────────── ↑ /dev/input/eventX ──────────────────────┤
│                        Kernel Driver Layer                                  │
│   Linux Input Subsystem: 触摸屏控制器驱动 → input_event → /dev/input/eventX │
│   drivers/input/ , drivers/hid/                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 各层职责与核心数据结构

**第一层：Kernel Driver — Linux Input 子系统**

Linux Kernel 的 Input 子系统是标准化的输入设备框架。触摸屏控制器驱动（如 Goodix、Synaptics）通过 `input_report_abs()` 等内核 API 上报事件，Input 子系统将其写入 `/dev/input/eventX` 字符设备节点。

核心数据结构：

```c
// include/uapi/linux/input.h
struct input_event {
    struct timeval time;    // 事件时间戳（内核态）
    __u16 type;             // 事件类型：EV_ABS(触摸坐标), EV_KEY(按键), EV_SYN(同步)
    __u16 code;             // 事件码：ABS_MT_POSITION_X, ABS_MT_POSITION_Y, BTN_TOUCH
    __s32 value;            // 事件值：坐标值、按键状态(0/1)
};
```

**第二层：EventHub — HAL 抽象**

EventHub 是 Input 系统中最底层的 C++ 组件，直接与 `/dev/input/eventX` 节点交互。它使用 `epoll` 机制同时监听所有输入设备节点，并通过 `inotify` 检测设备热插拔。

- 源码路径：`frameworks/native/services/inputflinger/reader/EventHub.cpp`
- 核心类：`EventHub`
- 核心方法：`getEvents()` — 阻塞在 `epoll_wait`，返回原始事件数组

**第三层：InputReader / InputDispatcher — Native 核心**

这是 Input 系统的"大脑"，分为两个组件：


| 组件                | 职责                                                                                      | 核心源码路径                                                                   |
| ----------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `InputReader`     | 从 EventHub 读取原始事件，通过 InputMapper 转化为 Android 语义事件（`NotifyMotionArgs` / `NotifyKeyArgs`） | `frameworks/native/services/inputflinger/reader/InputReader.cpp`         |
| `InputDispatcher` | 从 mInboundQueue 取出事件，选择目标窗口，通过 InputChannel 发送给 App，并监控 ANR 超时                          | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` |


核心数据结构：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.h
// InputDispatcher 的三级队列模型
std::deque<std::shared_ptr<EventEntry>> mInboundQueue;     // 入站队列：InputReader 投递的事件
// 每个 Connection（对应一个 InputChannel / 一个窗口）维护：
std::deque<DispatchEntry*> outboundQueue;  // 出站队列：待发送给 App 的事件
std::deque<DispatchEntry*> waitQueue;      // 等待队列：已发送，等待 App finishInputEvent 回复
```

**第四层：InputManagerService / InputChannel — Framework 层**

Java 层的 `InputManagerService`（IMS）是 Input 系统在 `system_server` 中的 Java 侧入口，通过 JNI 桥接 Native 层的 `NativeInputManager`。`InputChannel` 基于 Unix Domain Socket（`socketpair`），是事件跨进程投递的通道。

- IMS 源码路径：`frameworks/base/services/core/java/com/android/server/input/InputManagerService.java`
- InputChannel 源码路径：`frameworks/native/libs/input/InputTransport.cpp`

**第五层：ViewRootImpl / View 树 — Application 层**

App 进程通过 `WindowInputEventReceiver`（继承自 `InputEventReceiver`）监听 InputChannel 的 client fd。事件到达后，经过 ViewRootImpl 的 InputStage 管线（7 个阶段），最终到达 `View.dispatchTouchEvent`。

- 源码路径：`frameworks/base/core/java/android/view/ViewRootImpl.java`
- 事件消费入口：`View.dispatchTouchEvent()` → `View.onTouchEvent()`

### 3.3 每一层的 AOSP 源码目录速查


| 层               | 核心源码目录                                                         | 关键文件                                                                                      |
| --------------- | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Kernel Driver   | `drivers/input/`, `drivers/hid/`                               | 触摸屏厂商驱动（OEM 定制）                                                                           |
| EventHub        | `frameworks/native/services/inputflinger/reader/`              | `EventHub.cpp`, `EventHub.h`                                                              |
| InputReader     | `frameworks/native/services/inputflinger/reader/`              | `InputReader.cpp`, `TouchInputMapper.cpp`, `KeyboardInputMapper.cpp`                      |
| InputDispatcher | `frameworks/native/services/inputflinger/dispatcher/`          | `InputDispatcher.cpp`, `InputDispatcher.h`                                                |
| InputManager    | `frameworks/native/services/inputflinger/`                     | `InputManager.cpp`                                                                        |
| IMS (Java)      | `frameworks/base/services/core/java/com/android/server/input/` | `InputManagerService.java`                                                                |
| InputChannel    | `frameworks/native/libs/input/`                                | `InputTransport.cpp`, `InputTransport.h`                                                  |
| ViewRootImpl    | `frameworks/base/core/java/android/view/`                      | `ViewRootImpl.java`, `InputEventReceiver.java`                                            |
| View 树          | `frameworks/base/core/java/android/view/`                      | `View.java`, `ViewGroup.java`                                                             |
| JNI 桥接          | `frameworks/base/core/jni/`                                    | `android_view_InputEventReceiver.cpp`, `com_android_server_input_InputManagerService.cpp` |


---

## 4. 一次触摸事件的完整旅程

理解 Input 系统最好的方式是追踪一次完整的触摸事件：用户手指按下（DOWN）→ 滑动（MOVE）→ 抬起（UP）。我们以 DOWN 事件为主线，展示它穿越五层的每一步。

### 4.1 第一站：硬件中断 → 驱动写入 /dev/input/eventX

用户手指触摸屏幕，触摸屏控制器（如 Goodix GT9XX）通过 I2C/SPI 总线通知 SoC，触发硬件中断。中断处理函数读取触摸坐标，调用 Linux Input 子系统的 API 上报事件：

```c
// 触摸屏驱动示例（简化）
static irqreturn_t touchscreen_irq_handler(int irq, void *dev_id)
{
    struct input_dev *input = dev_id;
    int x, y, pressure;

    // 从触摸屏控制器读取坐标
    read_touch_data(&x, &y, &pressure);

    // 通过 Linux Input 子系统上报多点触控事件（Type B Slot 协议）
    input_mt_slot(input, finger_id);
    input_mt_report_slot_state(input, MT_TOOL_FINGER, true);
    input_report_abs(input, ABS_MT_POSITION_X, x);
    input_report_abs(input, ABS_MT_POSITION_Y, y);
    input_report_abs(input, ABS_MT_PRESSURE, pressure);
    input_sync(input);  // 发送 EV_SYN/SYN_REPORT，标记一帧事件结束

    return IRQ_HANDLED;
}
```

`input_sync()` 之后，Linux Input 子系统将这些事件写入 `/dev/input/eventX` 的 ring buffer，等待用户态程序读取。

### 4.2 第二站：EventHub::getEvents() — epoll 唤醒

EventHub 在启动时通过 `epoll_ctl` 注册了所有 `/dev/input/eventX` 节点的 fd。当新事件到达时，`epoll_wait` 被唤醒，EventHub 读取原始的 `struct input_event`：

```cpp
// frameworks/native/services/inputflinger/reader/EventHub.cpp（简化）
size_t EventHub::getEvents(int timeoutMillis, RawEvent* buffer, size_t bufferSize) {
    for (;;) {
        // 处理已读取的事件
        while (mPendingEventIndex < mPendingEventCount) {
            const struct epoll_event& eventItem = mPendingEventItems[mPendingEventIndex++];
            Device* device = getDeviceByFdLocked(eventItem.data.fd);

            struct input_event readBuffer[256];
            int32_t readSize = read(device->fd, readBuffer, sizeof(readBuffer));

            for (size_t i = 0; i < count; i++) {
                struct input_event& iev = readBuffer[i];
                // 将 Linux input_event 转换为 Android RawEvent
                event->when = processEventTimestamp(iev);
                event->deviceId = device->id;
                event->type = iev.type;
                event->code = iev.code;
                event->value = iev.value;
                event += 1;  // 移动到 buffer 下一个位置
            }
        }

        // 阻塞等待新事件
        int pollResult = epoll_wait(mEpollFd, mPendingEventItems,
                                     EPOLL_MAX_EVENTS, timeoutMillis);
    }
}
```

**关键点：** EventHub 还通过 `inotify` 监听 `/dev/input/` 目录，当有新设备接入（如蓝牙键盘）时自动识别并加入 epoll 监听。

### 4.3 第三站：InputReader::loopOnce() — 事件语义化

InputReader 在专属线程（`InputReaderThread`）中不断调用 `loopOnce()`，从 EventHub 读取原始事件，通过 InputMapper 将其转化为 Android 语义事件：

```cpp
// frameworks/native/services/inputflinger/reader/InputReader.cpp（简化）
void InputReader::loopOnce() {
    // 1. 从 EventHub 读取原始事件
    size_t count = mEventHub->getEvents(timeoutMillis, mEventBuffer, EVENT_BUFFER_SIZE);

    // 2. 处理原始事件
    if (count) {
        processEventsLocked(mEventBuffer, count);
    }

    // 3. 将处理后的事件刷入 InputDispatcher 的 mInboundQueue
    mQueuedListener.flush();
}

void InputReader::processEventsLocked(const RawEvent* rawEvents, size_t count) {
    for (const RawEvent* rawEvent = rawEvents; count--; rawEvent++) {
        if (rawEvent->type < EventHubInterface::FIRST_SYNTHETIC_EVENT) {
            // 非合成事件：交给对应设备的 InputMapper 处理
            processEventsForDeviceLocked(rawEvent->deviceId, rawEvent, 1);
        } else {
            // 合成事件：设备增加/移除/配置变更
            switch (rawEvent->type) {
                case EventHubInterface::DEVICE_ADDED:
                    addDeviceLocked(rawEvent->when, rawEvent->deviceId);
                    break;
                case EventHubInterface::DEVICE_REMOVED:
                    removeDeviceLocked(rawEvent->when, rawEvent->deviceId);
                    break;
            }
        }
    }
}
```

对于触摸事件，`TouchInputMapper` 负责将 `ABS_MT_POSITION_X` / `ABS_MT_POSITION_Y` 等原始值转换为 `NotifyMotionArgs`（包含 `ACTION_DOWN` / `ACTION_MOVE` / `ACTION_UP`、屏幕坐标、压力值、触点 ID 等）。

### 4.4 第四站：InputDispatcher::dispatchOnce() — 窗口路由

InputDispatcher 在另一个专属线程（`InputDispatcherThread`）中运行，核心方法是 `dispatchOnce()`：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp（简化）
void InputDispatcher::dispatchOnce() {
    nsecs_t nextWakeupTime = LONG_LONG_MAX;

    { // acquire lock
        std::scoped_lock _l(mLock);

        // 1. 如果没有待分发的事件，从 mInboundQueue 取一个
        if (!mPendingEvent) {
            if (mInboundQueue.empty()) {
                // 队列为空，处理 ANR 超时检查
            } else {
                mPendingEvent = mInboundQueue.front();
                mInboundQueue.pop_front();
            }
        }

        // 2. 分发事件
        if (mPendingEvent) {
            switch (mPendingEvent->type) {
                case EventEntry::Type::MOTION: {
                    done = dispatchMotionLocked(currentTime,
                            static_cast<MotionEntry&>(*mPendingEvent),
                            &dropReason, nextWakeupTime);
                    break;
                }
                case EventEntry::Type::KEY: {
                    done = dispatchKeyLocked(currentTime,
                            static_cast<KeyEntry&>(*mPendingEvent),
                            &dropReason, nextWakeupTime);
                    break;
                }
            }
        }
    } // release lock

    // 3. 等待下一个事件或超时
    mLooper->pollOnce(timeoutMillis);
}
```

对于触摸事件，`dispatchMotionLocked` 调用 `findTouchedWindowTargetsLocked`，按 Z-order 从高到低遍历窗口列表，执行命中测试（Hit Test），找到目标窗口后通过 `InputChannel` 的 server 端 fd 发送事件：

```cpp
// 简化的窗口查找逻辑
int32_t InputDispatcher::findTouchedWindowTargetsLocked(
        nsecs_t currentTime, const MotionEntry& entry,
        std::vector<InputTarget>& inputTargets, ...) {

    // 按 Z-order 从高到低遍历所有窗口
    for (const sp<WindowInfoHandle>& windowHandle : getWindowHandlesLocked(displayId)) {
        const WindowInfo& info = *windowHandle->getInfo();

        // 命中测试：触摸点是否在窗口范围内
        if (!info.touchableRegionContainsPoint(x, y)) continue;

        // 检查窗口标志
        if (info.flags.test(WindowInfo::Flag::NOT_TOUCHABLE)) continue;

        // 找到目标窗口
        addWindowTargetLocked(windowHandle, InputTarget::FLAG_FOREGROUND, ..., inputTargets);

        // 如果窗口不允许穿透，停止查找
        if (!info.flags.test(WindowInfo::Flag::NOT_TOUCH_MODAL)) break;
    }
}
```

### 4.5 第五站：InputChannel 跨进程投递

找到目标窗口后，InputDispatcher 通过 `InputPublisher::publishMotionEvent` 将事件序列化为 `InputMessage`，写入 InputChannel 的 server 端 socket fd：

```cpp
// frameworks/native/libs/input/InputTransport.cpp（简化）
status_t InputPublisher::publishMotionEvent(...) {
    InputMessage msg;
    msg.header.type = InputMessage::Type::MOTION;
    msg.body.motion.action = action;
    msg.body.motion.pointerCount = pointerCount;
    // 填充坐标、时间戳、压力等字段...

    return mChannel->sendMessage(&msg);
}

status_t InputChannel::sendMessage(const InputMessage* msg) {
    const size_t msgLength = msg->size();
    ssize_t nWrite;
    do {
        nWrite = ::send(getFd(), msg, msgLength, MSG_DONTWAIT | MSG_NOSIGNAL);
    } while (nWrite == -1 && errno == EINTR);
    return OK;
}
```

同时，InputDispatcher 将该事件放入目标 Connection 的 `waitQueue`，启动 5 秒 ANR 倒计时。

### 4.6 第六站：App 接收与消费

App 进程的主线程 Looper 通过 `epoll` 监听 InputChannel 的 client fd。当 fd 可读时，`NativeInputEventReceiver::handleEvent` 被回调：

```cpp
// frameworks/base/core/jni/android_view_InputEventReceiver.cpp（简化）
int NativeInputEventReceiver::handleEvent(int receiveFd, int events, void* data) {
    if (events & ALOOPER_EVENT_INPUT) {
        // 从 InputChannel 读取事件
        InputEvent* inputEvent;
        status_t status = mInputConsumer.consume(&mInputEventFactory, /*consumeBatches=*/true,
                                                  -1, &seq, &inputEvent);
        // 通过 JNI 回调 Java 层
        // → InputEventReceiver.dispatchInputEvent()
        // → WindowInputEventReceiver.onInputEvent()
    }
}
```

Java 层收到事件后，`ViewRootImpl` 将其送入 InputStage 管线：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java（简化）
final class WindowInputEventReceiver extends InputEventReceiver {
    @Override
    public void onInputEvent(InputEvent event) {
        // 将事件入队到 InputStage 管线
        enqueueInputEvent(event, this, 0, true);
    }
}

void deliverInputEvent(QueuedInputEvent q) {
    // InputStage 管线（链表模式）：
    // NativePreImeInputStage → ViewPreImeInputStage → ImeInputStage
    //   → EarlyPostImeInputStage → NativePostImeInputStage
    //   → ViewPostImeInputStage → SyntheticInputStage
    InputStage stage = q.shouldSkipIme() ? mFirstPostImeInputStage : mFirstInputStage;
    stage.deliver(q);
}
```

最终经过 `ViewPostImeInputStage`，事件到达 `View.dispatchTouchEvent()` → `ViewGroup.dispatchTouchEvent()` → 递归分发到目标 View 的 `onTouchEvent()`。

### 4.7 第七站：finishInputEvent — 关闭 ANR 倒计时

App 处理完事件后（无论是否消费），必须调用 `finishInputEvent` 通知 InputDispatcher：

```java
// InputEventReceiver.java
public final void finishInputEvent(InputEvent event, boolean handled) {
    // 通过 JNI 调用 Native 层
    nativeFinishInputEvent(mReceiverPtr, seq, handled);
}
```

Native 层通过 InputChannel 的 client fd 回复一条确认消息给 InputDispatcher。InputDispatcher 收到回复后，从 `waitQueue` 中移除该事件，取消 ANR 倒计时，并可以继续发送下一个事件。

**完整时序总结：**

```
硬件中断 → 驱动 input_report_abs()
   → /dev/input/eventX (ring buffer)
      → EventHub::getEvents() [epoll_wait 唤醒]
         → InputReader::loopOnce() [InputReaderThread]
            → TouchInputMapper → NotifyMotionArgs
               → QueuedInputListener::flush()
                  → InputDispatcher::notifyMotion() [加入 mInboundQueue]
                     → InputDispatcher::dispatchOnce() [InputDispatcherThread]
                        → findTouchedWindowTargetsLocked() [窗口查找]
                           → InputChannel::sendMessage() [socket write]
                              → App Looper epoll 唤醒 [主线程]
                                 → ViewRootImpl → InputStage 管线
                                    → View.dispatchTouchEvent()
                                       → View.onTouchEvent()
                                          → finishInputEvent()
                                             → InputDispatcher 取消 ANR 倒计时
```

---

## 5. 核心进程与线程模型

### 5.1 system_server 进程中的两个关键线程

Input 系统的核心逻辑运行在 `system_server` 进程中，由两个专属线程承载：

```
system_server 进程
├── main (主线程)
│     └── InputManagerService (Java 层管理入口)
├── InputReader (线程)
│     └── 循环: EventHub::getEvents() → processEventsLocked() → flush()
├── InputDispatcher (线程)
│     └── 循环: dispatchOnce() → findTargets() → sendMessage() → ANR 检测
└── 其他线程 (Binder, Handler, etc.)
```

**InputReaderThread：事件生产者**

```cpp
// frameworks/native/services/inputflinger/reader/InputReader.cpp
void InputReader::loopOnce() {
    // 1. 从 EventHub 读取原始事件（可能阻塞在 epoll_wait）
    size_t count = mEventHub->getEvents(timeoutMillis, mEventBuffer, EVENT_BUFFER_SIZE);

    // 2. 在 InputReader 的锁内处理事件
    { // acquire lock
        std::scoped_lock _l(mLock);
        if (count) {
            processEventsLocked(mEventBuffer, count);
        }
    } // release lock

    // 3. 将已处理的事件刷入 InputDispatcher
    //    这里调用 InputDispatcher::notifyMotion / notifyKey
    //    事件被加入 mInboundQueue
    mQueuedListener.flush();
}
```

**InputDispatcherThread：事件消费者与分发者**

InputDispatcher 在循环中做三件事：

1. 从 `mInboundQueue` 取出事件
2. 查找目标窗口，将事件通过 InputChannel 发送给 App
3. 检查 `waitQueue` 中是否有超时事件，触发 ANR

两个线程之间的连接点是 `InputDispatcher::notifyMotion()`，InputReader 在 `flush()` 时调用它，将 `NotifyMotionArgs` 转换为 `MotionEntry` 放入 `mInboundQueue`，并唤醒 InputDispatcher 线程：

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp（简化）
void InputDispatcher::notifyMotion(const NotifyMotionArgs& args) {
    std::scoped_lock _l(mLock);

    // 构造 MotionEntry
    std::unique_ptr<MotionEntry> newEntry =
            std::make_unique<MotionEntry>(args.id, args.eventTime, args.deviceId,
                                           args.source, args.displayId, ...);

    // 加入 mInboundQueue 尾部
    needWake = enqueueInboundEventLocked(std::move(newEntry));

    if (needWake) {
        mLooper->wake();  // 唤醒 InputDispatcher 线程
    }
}
```

### 5.2 App 进程中的事件接收

App 进程不需要专门的线程接收 Input 事件。InputChannel 的 client fd 被注册到主线程 Looper 的 `epoll` 中（通过 `NativeInputEventReceiver::setFdEvents`），当 fd 可读时，Looper 在 `pollOnce` 中回调 `handleEvent`，整个过程在主线程执行。

```
App 进程 (主线程)
└── Looper::pollOnce()
      ├── MessageQueue 消息处理 (Handler 消息)
      ├── InputChannel fd 可读 → NativeInputEventReceiver::handleEvent()
      │     → InputConsumer::consume()
      │     → JNI → WindowInputEventReceiver::onInputEvent()
      │     → ViewRootImpl → InputStage → View 树分发
      │     → finishInputEvent() → InputChannel 回复
      └── VSync fd 可读 → Choreographer::doFrame()
```

这意味着 **Input 事件的接收和处理完全在主线程上**。任何主线程卡顿（如耗时的 `onBindViewHolder`、同步 Binder 调用、文件 I/O）都会阻塞 Input 事件的处理，进而延迟 `finishInputEvent` 的回复，最终可能触发 ANR。

### 5.3 InputManager::start() — 启动两个线程

两个线程在 `system_server` 启动过程中通过 `InputManager::start()` 启动：

```cpp
// frameworks/native/services/inputflinger/InputManager.cpp
status_t InputManager::start() {
    // 启动 InputDispatcher 线程（先启动消费者）
    status_t result = mDispatcher->start();
    if (result) {
        ALOGE("Could not start InputDispatcher thread. status=%d", result);
        return result;
    }

    // 启动 InputReader 线程（后启动生产者）
    result = mReader->start();
    if (result) {
        ALOGE("Could not start InputReader thread. status=%d", result);
        mDispatcher->stop();
        return result;
    }

    return OK;
}
```

注意启动顺序：先启动 Dispatcher（消费者），再启动 Reader（生产者），确保生产者开始生产时消费者已经就绪。

### 5.4 线程模型与稳定性


| 线程                    | 阻塞原因                            | 稳定性后果                     |
| --------------------- | ------------------------------- | ------------------------- |
| InputReaderThread     | EventHub 设备读取异常、InputMapper 处理慢 | 新事件无法被读取，所有事件延迟           |
| InputDispatcherThread | 窗口查询耗时、锁竞争（mLock）、ANR 回调处理慢     | 事件无法分发，mInboundQueue 堆积   |
| App 主线程               | 任何耗时操作（Binder/IO/计算）            | finishInputEvent 延迟 → ANR |


**核心原则：Input 管线上的每一个线程都不应执行耗时操作。** 任何环节的阻塞都会沿着管线向上游传播，最终被用户感知为"触摸延迟"或"没反应"。

---

## 6. 与其他核心模块的交互

Input 系统不是孤立运行的。它与 WMS、AMS、Choreographer、IME、SurfaceFlinger 等核心模块深度耦合，形成了 Android 系统中最复杂的模块交互网络之一。

### 6.1 WMS（WindowManagerService）— 提供窗口信息

InputDispatcher 要知道"事件该发给哪个窗口"，就必须从 WMS 获取最新的窗口列表和 Z-order。这个交互通过 `InputMonitor` 完成：

```java
// frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java（简化）
void updateInputWindowsLw(boolean force) {
    // 遍历所有 WindowState，收集窗口信息
    // 每个窗口的信息包括：位置、大小、可见性、flags、InputChannel 等
    mService.mRoot.forAllWindows(this::populateInputWindowHandle, true /* traverseTopToBottom */);

    // 将窗口信息数组传给 Native 层的 InputDispatcher
    // 通过 InputManagerService → NativeInputManager → InputDispatcher::setInputWindows()
    nativeSetInputWindows(mInputTransaction, ...);
}
```

**时机：** 每当窗口状态变化（添加/移除/移动/层级改变）时，WMS 调用 `updateInputWindowsLw()`。如果 WMS 更新不及时（如窗口动画期间），InputDispatcher 可能用到过期的窗口信息，导致事件发送到错误窗口。

**稳定性关联：** WMS 的锁竞争（`mGlobalLock`）可能延迟窗口信息更新，导致 InputDispatcher 在窗口切换瞬间找不到目标窗口或找到错误窗口。

### 6.2 AMS（ActivityManagerService）— ANR 裁决

当 InputDispatcher 检测到 5 秒超时，它不会直接弹 ANR 对话框，而是通过回调链上报给 AMS 做最终裁决：

```
InputDispatcher::onAnrLocked()
  → mPolicy->notifyAnr()   (NativeInputManager)
  → InputManagerService.notifyANR()   (Java, JNI 回调)
  → InputManagerCallback.notifyANR()
  → ActivityManagerService.inputDispatchingTimedOut()
```

AMS 在 `inputDispatchingTimedOut()` 中做最终裁决：

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java（简化）
boolean inputDispatchingTimedOut(int pid, boolean aboveSystem, String reason) {
    ProcessRecord proc;
    synchronized (mPidsSelfLocked) {
        proc = mPidsSelfLocked.get(pid);
    }

    if (proc != null) {
        // 检查进程是否正在被调试（调试时不报 ANR）
        if (proc.isDebugging()) return false;

        // 检查进程是否正在执行 instrumentation（测试时不报 ANR）
        if (proc.getActiveInstrumentation() != null) return false;

        // 触发 ANR 处理：收集 traces、弹对话框或直接杀进程
        mAnrHelper.appNotResponding(proc, "Input dispatching timed out (" + reason + ")");
    }
    return true;
}
```

### 6.3 Choreographer — VSync 与 Input 的协同

Choreographer 是 Android 渲染管线的节拍器，负责在 VSync 信号到来时执行 `doFrame()`。**Input 事件的处理被安排在 `doFrame()` 的最早阶段**：

```java
// frameworks/base/core/java/android/view/Choreographer.java（简化）
void doFrame(long frameTimeNanos, int frame) {
    // 按顺序执行回调：
    // 1. CALLBACK_INPUT   — 处理 Input 事件（最高优先级）
    // 2. CALLBACK_ANIMATION — 处理动画
    // 3. CALLBACK_INSETS_ANIMATION — 处理 Insets 动画
    // 4. CALLBACK_TRAVERSAL — 执行 measure/layout/draw
    // 5. CALLBACK_COMMIT — 提交帧

    doCallbacks(Choreographer.CALLBACK_INPUT, frameTimeNanos);
    doCallbacks(Choreographer.CALLBACK_ANIMATION, frameTimeNanos);
    doCallbacks(Choreographer.CALLBACK_INSETS_ANIMATION, frameTimeNanos);
    doCallbacks(Choreographer.CALLBACK_TRAVERSAL, frameTimeNanos);
    doCallbacks(Choreographer.CALLBACK_COMMIT, frameTimeNanos);
}
```

但需要注意：**Input 事件并不是只在 VSync 时才能被处理。** InputChannel fd 可读时，Looper 会立即唤醒主线程处理。`CALLBACK_INPUT` 主要用于处理合成事件（如 fling 惯性滚动的合成 MOVE）。

### 6.4 IME（InputMethodManager）— 输入法事件截获

当软键盘弹出时，按键事件需要先交给输入法处理。ViewRootImpl 的 InputStage 管线中，`ImeInputStage` 负责将事件通过 `InputMethodManager` 转发给 IME 进程：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java（简化）
final class ImeInputStage extends AsyncInputStage {
    @Override
    protected int onProcess(QueuedInputEvent q) {
        if (mLastWasImTarget && !isInLocalFocusMode()) {
            InputMethodManager imm = getInputMethodManager();
            if (imm != null) {
                // 将事件转发给 IME 进程处理
                int result = imm.dispatchInputEvent(q.mEvent, q.mToken,
                        mInputMethodConsumer, mHandler);
                if (result == InputMethodManager.DISPATCH_HANDLED) {
                    return FINISH_HANDLED;  // IME 消费了事件，不再向下传递
                }
                if (result == InputMethodManager.DISPATCH_NOT_HANDLED) {
                    return FORWARD;  // IME 未消费，继续向下传递
                }
            }
        }
        return FORWARD;
    }
}
```

**稳定性关联：** IME 进程如果处理慢（如加载词库），会延迟事件在管线中的流转，间接影响 `finishInputEvent` 的回复时间。

### 6.5 SurfaceFlinger — 触摸到显示的完整延迟

用户感知的"触摸延迟"实际包含三个阶段：

```
触摸到显示的总延迟 = Input 延迟 + 渲染延迟 + 显示延迟

Input 延迟:
  硬件中断 → EventHub → InputReader → InputDispatcher → App 收到事件
  典型值: 8-15ms

渲染延迟:
  App 处理事件 → requestLayout → measure/layout/draw → SurfaceFlinger 合成
  典型值: 16-32ms（1-2 帧）

显示延迟:
  SurfaceFlinger 提交到显示控制器 → 扫描输出到屏幕像素
  典型值: 4-8ms（取决于显示刷新率和扫描方式）

总延迟: 约 28-55ms（理想情况），用户感知阈值约 100ms
```

Android 12+ 引入的 **触摸预测（Touch Prediction）** 通过 `MotionPredictor` 在 InputReader 层对后续触摸位置进行预测，允许 App 提前渲染预测位置的画面，进一步降低感知延迟。

---

## 7. 核心源码目录导航

排查 Input 相关问题时，快速定位到正确的源码文件至关重要。以下是 AOSP 中 Input 系统的核心目录导航：


| 目录                                                             | 职责                     | 关键文件                                                                            |
| -------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------- |
| `frameworks/native/services/inputflinger/`                     | Input 系统 Native 层总入口   | `InputManager.cpp` — 管理 Reader/Dispatcher 的生命周期                                 |
| `frameworks/native/services/inputflinger/reader/`              | EventHub + InputReader | `EventHub.cpp` — 设备节点管理与原始事件读取                                                  |
|                                                                |                        | `InputReader.cpp` — 事件语义化引擎                                                     |
|                                                                |                        | `TouchInputMapper.cpp` — 触摸事件映射（多点触控、坐标变换）                                      |
|                                                                |                        | `KeyboardInputMapper.cpp` — 按键事件映射                                              |
| `frameworks/native/services/inputflinger/dispatcher/`          | InputDispatcher        | `InputDispatcher.cpp` — 事件分发引擎（窗口选择 + ANR 检测）                                   |
|                                                                |                        | `InputDispatcher.h` — 队列模型与数据结构定义                                               |
| `frameworks/native/libs/input/`                                | Input 基础库              | `InputTransport.cpp` — InputChannel 实现（socketpair + sendMessage/receiveMessage） |
|                                                                |                        | `Input.cpp` — InputEvent / MotionEvent / KeyEvent 的 Native 实现                   |
| `frameworks/base/services/core/java/com/android/server/input/` | IMS (Java)             | `InputManagerService.java` — Java 层管理入口，JNI 桥接                                  |
| `frameworks/base/core/java/android/view/`                      | 应用层 Input API          | `ViewRootImpl.java` — InputStage 管线、事件接收与分发                                     |
|                                                                |                        | `InputEventReceiver.java` — InputChannel 的 Java 层封装                             |
|                                                                |                        | `View.java` / `ViewGroup.java` — 事件分发的最终消费                                      |
|                                                                |                        | `MotionEvent.java` / `KeyEvent.java` — 事件对象                                     |
|                                                                |                        | `InputChannel.java` — InputChannel 的 Java 包装                                    |
| `frameworks/base/core/jni/`                                    | JNI 桥接层                | `android_view_InputEventReceiver.cpp` — InputEventReceiver 的 JNI 实现             |
|                                                                |                        | `com_android_server_input_InputManagerService.cpp` — IMS 的 JNI 实现               |


**排查技巧：** 遇到 Input 问题时，根据问题表现定位到对应层的源码目录：

- 设备不识别 / 触摸无响应 → `EventHub.cpp`
- 触摸坐标偏移 → `TouchInputMapper.cpp`
- 事件发给错误窗口 → `InputDispatcher.cpp`（`findTouchedWindowTargetsLocked`）
- Input ANR → `InputDispatcher.cpp`（`onAnrLocked`）
- 事件在 App 内分发异常 → `ViewRootImpl.java`、`ViewGroup.java`

---

## 8. 稳定性总览：Input 系统的风险全景

Input 系统覆盖从硬件到应用的完整链路，每一层都可能成为稳定性问题的发源地。作为稳定性架构师，需要建立对所有风险类型的全局认知。

### 8.1 风险全景图


| 风险类型          | 描述                                                         | 典型占比               | 深入文章                                                    |
| ------------- | ---------------------------------------------------------- | ------------------ | ------------------------------------------------------- |
| **Input ANR** | App 未在 5 秒内回复 finishInputEvent，InputDispatcher 触发 ANR      | 占线上 ANR 的 **60%+** | [06-Input ANR](06-InputANR.md)                          |
| **触摸延迟**      | 从触摸到屏幕响应超过 100ms，用户可感知"不跟手"                                | 体验退化的首要原因          | [08-诊断与治理](08-Input诊断工具与延迟治理体系.md)                      |
| **事件丢失**      | mInboundQueue 满、socket buffer 满、App 未消费 → 触摸"没反应"          | 偶发但影响严重            | [07-风险全景](07-Input稳定性风险全景.md)                           |
| **触摸偏移/错位**   | TouchInputMapper 坐标变换异常 → 触摸点与视觉位置不符                       | OEM 设备适配问题         | [02-EventHub 与 InputReader](02-EventHub与InputReader.md) |
| **输入设备不响应**   | 驱动异常 / EventHub fd 泄漏 → 某个输入设备完全无响应                        | 硬件兼容性问题            | [02-EventHub 与 InputReader](02-EventHub与InputReader.md) |
| **无焦点窗口**     | Activity 启动慢 → InputChannel 未注册 → InputDispatcher 等待 → ANR | 冷启动慢的常见后果          | [06-Input ANR](06-InputANR.md)                          |


### 8.2 各层的典型风险

```
┌────────────────────────────────────────────────────────────────────┐
│ Application 层                                                      │
│  • onTouchEvent 中执行耗时操作 → finishInputEvent 延迟 → ANR        │
│  • ViewGroup 拦截逻辑错误 → 嵌套滑动冲突 → 触摸失效                  │
│  • InputStage 管线中 IME 阶段阻塞 → 按键事件延迟                    │
├────────────────────────────────────────────────────────────────────┤
│ Framework 层                                                        │
│  • InputChannel 未及时注册（窗口未就绪）→ 无焦点窗口 ANR             │
│  • IMS 的 JNI 回调异常 → 事件链路断裂                                │
├────────────────────────────────────────────────────────────────────┤
│ Native 层 (InputDispatcher)                                         │
│  • mInboundQueue 堆积 → 所有事件延迟                                 │
│  • waitQueue 串行化等待 → 一条慢消息阻塞后续所有事件                  │
│  • 窗口信息过期 → 事件发往错误窗口或被 DROP                          │
│  • ANR 超时误报/漏报                                                 │
├────────────────────────────────────────────────────────────────────┤
│ Native 层 (InputReader)                                             │
│  • TouchInputMapper 坐标变换错误 → 触摸偏移                         │
│  • InputMapper 处理慢 → 事件积压                                     │
├────────────────────────────────────────────────────────────────────┤
│ EventHub 层                                                         │
│  • epoll fd 泄漏 → 设备事件无法读取                                  │
│  • 设备热插拔处理异常 → 蓝牙键盘断连后无法重连                       │
├────────────────────────────────────────────────────────────────────┤
│ Kernel 层                                                           │
│  • 触摸屏驱动固件 Bug → 事件丢失或坐标跳变                          │
│  • 中断风暴 → CPU 被中断处理独占 → 其他线程饥饿                     │
└────────────────────────────────────────────────────────────────────┘
```

### 8.3 快速定位速查表


| 问题现象       | 可能的层                  | 排查入口                                              |
| ---------- | --------------------- | ------------------------------------------------- |
| 点击完全无反应    | Kernel / EventHub     | `adb shell getevent` 验证硬件是否上报事件                   |
| 触摸坐标偏移     | InputReader           | `adb shell getevent -l` 对比原始坐标与显示坐标               |
| 事件发给了错误窗口  | InputDispatcher       | `adb shell dumpsys input` 查看窗口列表与 FocusedWindow   |
| Input ANR  | InputDispatcher + App | ANR traces.txt 主线程栈 + `dumpsys input` 的 waitQueue |
| 滑动卡顿 / 不跟手 | App 主线程               | Systrace 分析主线程耗时                                  |
| 软键盘按键无响应   | IME 链路                | `dumpsys input_method` + `dumpsys input`          |


---

## 9. 实战案例

### Case 1：首页频繁 Input ANR — 无焦点窗口

**现象**

线上某版本发布后，首页的 Input ANR 率从 0.3% 飙升到 1.2%。ANR 日志中反复出现：

```
Input dispatching timed out (Waiting because no window has focus
but there is a focused application that may eventually add a window
when it finishes starting up.)
```

**排查过程**

**第一步：分析 ANR 日志关键字段**

```
ANR in com.example.app (com.example.app/.MainActivity)
PID: 12345
Reason: Input dispatching timed out
  (Waiting because no window has focus but there is a focused application
   that may eventually add a window when it finishes starting up.)
Load: 12.3 / 8.1 / 5.5
```

关键信息：`no window has focus` + `focused application may eventually add a window`。这意味着 InputDispatcher 知道哪个 Application 应该接收事件（`FocusedApplication` 已设置），但该 Application 还没有注册任何 InputChannel（`FocusedWindow == null`）。

**第二步：`dumpsys input` 确认 InputDispatcher 状态**

```
FocusedApplications:
  displayId=0, name='ActivityRecord{abc1234 com.example.app/.MainActivity}',
  dispatchingTimeout=5000ms

FocusedWindows: <none>

// mInboundQueue 中堆积了大量 Motion 事件
InboundQueue: length=23
  MotionEvent(action=DOWN, ...), age=5234ms   ← 已超过 5 秒
  MotionEvent(action=MOVE, ...), age=5180ms
  ...
```

确认了问题：Activity 正在启动，但 Window 还没准备好（`addWindow()` 还没调用），InputDispatcher 等待了 5 秒后触发了 ANR。

**第三步：分析 traces.txt 主线程栈**

```
"main" prio=5 tid=1 Runnable
  at com.example.sdk.analytics.AnalyticsEngine.init(AnalyticsEngine.java:89)
  at com.example.sdk.SdkInitializer.initAllSdks(SdkInitializer.java:45)
  at com.example.app.MyApplication.onCreate(MyApplication.java:32)
  at android.app.Instrumentation.callApplicationOnCreate(Instrumentation.java:1211)
  at android.app.ActivityThread.handleBindApplication(ActivityThread.java:6588)
```

**根因定位：** `Application.onCreate()` 中调用了 `SdkInitializer.initAllSdks()`，同步初始化了 15 个 SDK（数据分析、推送、热修复、广告等）。其中 `AnalyticsEngine.init()` 涉及数据库读写和网络请求，在低端设备上耗时超过 5 秒。此时 Activity 的 `onCreate` 尚未执行，`ViewRootImpl.setView()` 尚未调用，`InputChannel` 尚未注册到 InputDispatcher。

**时间线：**

```
T=0s    用户点击 App 图标
T=0.1s  AMS 设置 FocusedApplication = MainActivity
        InputDispatcher 开始等待 FocusedWindow
T=0.1s  Application.onCreate() 开始执行
        → SdkInitializer.initAllSdks() 阻塞主线程
T=0.2s  用户触摸屏幕（DOWN 事件到达 InputDispatcher）
        InputDispatcher: 有 FocusedApplication, 无 FocusedWindow, 开始 5 秒倒计时
T=5.2s  倒计时到期 → InputDispatcher 触发 ANR
T=6.8s  SDK 初始化终于完成 → Activity.onCreate → setContentView → addWindow
        → InputChannel 注册（但为时已晚，ANR 已触发）
```

**修复方案**

```java
// 修复前：所有 SDK 在 Application.onCreate 同步初始化
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        SdkInitializer.initAllSdks();  // 同步，阻塞 5s+
    }
}

// 修复后：将非必要 SDK 延迟到 IdleHandler 初始化
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        SdkInitializer.initCriticalSdks();  // 只初始化必要 SDK（<500ms）

        // 非必要 SDK 延迟到主线程空闲时初始化
        Looper.myQueue().addIdleHandler(() -> {
            SdkInitializer.initDeferredSdks();
            return false;
        });
    }
}
```

**效果：** 冷启动时间从 6.8s → 1.2s，Input ANR 率从 1.2% → 0.15%。

---

### Case 2：列表页触摸延迟 — 事件积压导致串行化等待

**现象**

用户反馈某电商 App 的商品列表页在快速滑动时，偶尔出现"卡一下"的感觉——手指在滑动中突然不跟手，停顿约 100-200ms 后恢复。这个问题在中低端设备上更明显，但不触发 ANR。

**排查过程**

**第一步：Systrace 分析**

抓取 Systrace 后，观察到以下模式：

```
InputDispatcher 线程:
  |--- dispatchMotion (MOVE) → App [sendMessage] ---| → 等待 finishInputEvent
       |←──────── 38ms ────────→|                       ← App 回复 finish
  |--- dispatchMotion (MOVE) → App [sendMessage] ---|   ← 被串行化延迟
       (上一个 finish 之后才能发送下一个)
```

正常情况下，InputDispatcher 发送 MOVE 事件后，App 应在 <8ms 内回复 `finishInputEvent`。但 Systrace 显示某些 MOVE 事件的处理耗时达到 38ms，导致后续事件被串行化排队。

**第二步：定位 App 主线程卡点**

放大 Systrace 中 App 主线程的时间片，发现：

```
主线程:
  |-- deliverInputEvent --|  (正常, ~2ms)
  |-- deliverInputEvent --|  (正常, ~3ms)
  |-- deliverInputEvent -------- onBindViewHolder → BitmapFactory.decodeFile() ---------|  (38ms!)
  |-- deliverInputEvent --|  (正常, ~2ms, 但被前一个延迟)
```

在 `RecyclerView` 滑动过程中，`onBindViewHolder` 被主线程调用。某些 ViewHolder 的绑定逻辑中包含了同步的图片解码操作（`BitmapFactory.decodeFile()`），耗时 30-40ms。

**第三步：理解串行化机制**

InputDispatcher 的事件投递是**串行化**的——同一个 Connection（窗口）上，前一个事件未被 `finishInputEvent` 确认之前，后续事件只能在 `outboundQueue` 中排队，不会被发送。这是为了保证事件的顺序性和 ANR 检测的正确性。

```cpp
// InputDispatcher.cpp（简化）
// 检查是否可以向窗口发送新事件
std::string InputDispatcher::checkWindowReadyForMoreInputLocked(...) {
    // 如果 waitQueue 非空（前一个事件还没被确认），新事件不能发送
    if (!connection->waitQueue.empty()) {
        // 检查等待时间是否超过 ANR 阈值
        DispatchEntry* waitEntry = connection->waitQueue.front();
        if (currentTime - waitEntry->deliveryTime >= DISPATCHING_TIMEOUT) {
            return "Waiting to send non-key event because the touched window has not "
                   "finished processing certain input events that were delivered to it "
                   "over 5000ms ago.";
        }
    }
    return "";  // 空字符串表示可以发送
}
```

因此，一次 38ms 的 `onBindViewHolder` 不仅延迟了当前事件的处理，还阻塞了后续所有事件的投递。在 120Hz 刷新率（8.3ms/帧）下，38ms 的阻塞意味着约 4-5 帧的 MOVE 事件被积压，用户感知就是"卡一下"。

**根因**

`RecyclerView.Adapter.onBindViewHolder()` 中对商品主图的加载使用了 `BitmapFactory.decodeFile()` 同步解码，阻塞主线程 30-40ms。叠加 InputDispatcher 的串行化投递机制，导致：

1. 一个 MOVE 事件处理耗时 38ms（正常应 <8ms）
2. 后续 MOVE 事件全部排在 outboundQueue 中等待
3. 38ms 后 finish 回复，排队事件才开始逐个发送
4. 用户感知：滑动停顿 → 突然跳跃一大段

**修复方案**

```kotlin
// 修复前：onBindViewHolder 中同步解码图片
override fun onBindViewHolder(holder: ProductViewHolder, position: Int) {
    val product = productList[position]
    // 同步解码，阻塞主线程 30-40ms
    val bitmap = BitmapFactory.decodeFile(product.imageLocalPath)
    holder.imageView.setImageBitmap(bitmap)
    holder.titleView.text = product.title
}

// 修复后：使用 Glide 异步加载
override fun onBindViewHolder(holder: ProductViewHolder, position: Int) {
    val product = productList[position]
    // 异步加载，主线程零阻塞
    Glide.with(holder.imageView)
        .load(product.imageUrl)
        .placeholder(R.drawable.placeholder)
        .into(holder.imageView)
    holder.titleView.text = product.title
}
```

额外优化：在 `RecyclerView` 的 `OnScrollListener` 中，滑动速度超过阈值时暂停图片加载，进一步减少主线程负担：

```kotlin
recyclerView.addOnScrollListener(object : RecyclerView.OnScrollListener() {
    override fun onScrollStateChanged(recyclerView: RecyclerView, newState: Int) {
        when (newState) {
            RecyclerView.SCROLL_STATE_IDLE -> Glide.with(context).resumeRequests()
            RecyclerView.SCROLL_STATE_SETTLING,
            RecyclerView.SCROLL_STATE_DRAGGING -> Glide.with(context).pauseRequests()
        }
    }
})
```

**效果：** `onBindViewHolder` 平均耗时从 35ms → 2ms，MOVE 事件的 `finishInputEvent` 回复延迟从 38ms → 5ms，触摸掉帧率下降 90%，用户反馈的"滑动卡顿"投诉清零。

---

## 参考与延伸

- 后续文章将按本系列目录逐篇深入：从 EventHub 到 InputReader（02），从 InputDispatcher 到窗口选择（03），从 InputChannel 到跨进程投递（04），从 ViewRootImpl 到 View 事件分发（05），从 Input ANR 机制到系统裁决（06），直到诊断工具与治理体系（07-08）。
- 排查工具速查：`adb shell getevent`（硬件层验证）、`adb shell dumpsys input`（系统层状态）、Systrace/Perfetto（端到端延迟分析）、ANR traces.txt（主线程栈分析）。
- AOSP 在线阅读：[Android Code Search](https://cs.android.com/) 可在线浏览 `frameworks/native/services/inputflinger/` 下的所有源码。

