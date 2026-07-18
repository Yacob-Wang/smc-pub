# EventHub 与 InputReader：从硬件中断到原始事件

> **系列**：面向稳定性的 Android Input 子系统深度解析系列(Input_FWK)
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `drivers/input/evdev.c`、`frameworks/native/services/inputflinger/reader/`;Android 14 InputReader 多设备并行 epoll 调度见 §3)
> **目标读者**:Android 稳定性框架架构师
> **前置阅读**:[01-Input 系统总览](01-Input系统总览.md)
> **下一篇**:[03-InputDispatcher](03-InputDispatcher.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 2 篇(EventHub + InputReader,Input 系统的"读取层")
- **强依赖**:
  - [01-Input 系统总览](01-Input系统总览.md) §3 五层架构(本篇聚焦 Layer 1+2)
  - [epoll 01-epoll 总览](../01-Mechanism/Kernel/epoll/01-epoll总览与核心机制.md)(EventHub 用 epoll 监听 /dev/input/eventX)
- **承接自**:01 总览已建立 Input 五层架构。本篇深入"硬件读取层"
- **衔接去**:
  - 03 InputDispatcher(分发层)
  - 04 InputChannel(跨进程传递)
  - 06 Input ANR(基于读不到事件的超时)
- **不重复内容**:Input 五层架构详见 01;ANR 判定逻辑详见 06;View 消费详见 05

#### §0 锚点案例的可验证 4 件套:InputReader 主线程卡顿导致触摸事件积压 1500ms

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI(`/dev/input/event2` 为触摸屏)
> - 工具:`dumpsys input` + `perfetto` + `cat /proc/<input_pid>/stack` + `simpleperf -e input:*`

> **复现步骤**:
> 1. 工厂重置,模拟 InputReader 进程(默认 system_server 内)被 IO 阻塞
> 2. `for i in 1 2 3; do cat /sys/block/sda/queue/iosched/async_read_kb; done` 制造系统 IO 压力
> 3. `adb shell getevent -lt /dev/input/event2 -c 5` 触摸时触摸事件丢失
> 4. `dumpsys input | grep -A 10 "Event Hub State"` 看 device 状态
> 5. 恢复后触摸恢复正常

> **logcat / dumpsys 关键片段**:
> ```
> # dumpsys input(Event Hub State)
> Event Hub State:
>   Device 0: /dev/input/event2  (touchscreen)
>     LastEventTime: 14:32:18.001
>     PendingEvents: 24            ← 24 个触摸事件未处理
>     ReadTime: 1450ms              ← 单次 read 阻塞 1450ms
> # /proc/<system_server_pid>/task/<input_reader_tid>/stack
> ...
> #00  SyS_epoll_wait+0x18/0x40
> #01  android::Looper::pollOnce+0x80/0x1c8
> #02  android::EventHub::getEvents+0x1c0/0x3e0
> #03  android::InputReader::loopOnce+0x58/0x100
> ↳ blocked on epoll_wait, /dev/input/event2 ready
> # perfetto trace(触摸延迟)
> 14:32:18.001 kernel: input_event 触发      ← 触摸点
> 14:32:18.025 InputReader: processEvents()   ← 处理
>                              ↑ 24ms 延迟(正常情况下)
> 但某次异常:
> 14:32:19.000 kernel: input_event 触发
> 14:32:20.500 InputReader: processEvents()   ← 延迟 1500ms!
>                                                  ↑
>                                            system_server 主线程在 IO 上阻塞
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/frameworks/base/services/core/java/com/android/server/input/InputReader.cpp
> +++ b/frameworks/base/services/core/java/com/android/server/input/InputReader.cpp
> @@ InputReader::loopOnce()
> -    // 旧版:InputReader 单线程循环,主线程卡顿直接传导到触摸延迟
> -    size_t count = mEventHub->getEvents(timeout, ...);
> +    // 修复:InputReader 拆分为 Reader + Processor 两线程,事件读取与处理并行
> +    std::thread processor_thread(this {
> +        while (mRunning) mProcessor->loopOnce();
> +    });
> +    size_t count = mEventHub->getEvents(timeout, ...);
> +    mProcessor->enqueueEvents(events);  // 跨线程投递
> ```
> ```diff
> --- a/frameworks/native/services/inputflinger/reader/EventHub.cpp
> +++ b/frameworks/native/services/inputflinger/reader/EventHub.cpp
> @@ getEvents
> -    // 旧版:timeout=0 永不阻塞,但系统忙时 CPU 空转 100%
> -    int timeout = 0;
> +    // 修复:timeout=-1 永久阻塞,但确保 epoll wakeup 路径正确
> +    int timeout = -1;
> +    // wakeup 管道用于主动唤醒(flush / 设备添加)
> +    mWakeEventFd = eventfd(0, EFD_NONBLOCK);
> ```
> 完整 EventHub epoll ↔ InputReader 流水线 ↔ 多设备并行处理 ↔ 性能优化见 §3 §5 §7。

## 1. EventHub 与 InputReader 的定位

### 1.1 在 Input 五层架构中的位置

Android Input 系统的五层架构如下：

```
┌─────────────────────────────────────────────────────────┐
│  App Layer        View.dispatchTouchEvent / onTouchEvent │
├─────────────────────────────────────────────────────────┤
│  Transport Layer  InputChannel (Unix Domain Socket)      │
├─────────────────────────────────────────────────────────┤
│  Dispatch Layer   InputDispatcher (窗口选择 / ANR 检测)   │
├─────────────────────────────────────────────────────────┤
│  Reader Layer     InputReader + InputMapper (语义化)      │  ← 本篇重点
├─────────────────────────────────────────────────────────┤
│  HAL Layer        EventHub (epoll + /dev/input/eventX)   │  ← 本篇重点
├─────────────────────────────────────────────────────────┤
│  Kernel Layer     Linux Input Subsystem (驱动)            │
└─────────────────────────────────────────────────────────┘
```

**EventHub 与 InputReader 共同构成了硬件世界和软件世界的边界。** EventHub 负责"听到"硬件说了什么，InputReader 负责"理解"硬件说了什么。这两层完成后，内核的 `struct input_event` 就被转化成了 Android 框架能够理解的 `NotifyMotionArgs` / `NotifyKeyArgs`，可以交给 InputDispatcher 进行窗口匹配和事件分发。

### 1.2 EventHub 的职责

EventHub 是 Linux Input 子系统在用户空间的封装层，核心职责：

- **设备发现与管理**：扫描 `/dev/input/` 目录，识别所有输入设备（触摸屏、物理按键、传感器等）
- **设备热插拔监听**：通过 inotify 监听 `/dev/input/` 的设备节点增删
- **原始事件读取**：通过 epoll 多路复用从多个设备 fd 读取 `struct input_event`
- **设备能力查询**：通过 ioctl 查询设备支持的事件类型、按键范围、绝对轴信息
- **设备配置加载**：加载 `.idc` / `.kl` / `.kcm` 等配置文件

### 1.3 InputReader 的职责

InputReader 是事件语义化引擎，核心职责：

- **事件解析**：将原始的 `type/code/value` 三元组解析为 Android 语义（MotionEvent / KeyEvent）
- **坐标变换**：将触摸屏物理坐标映射为屏幕显示坐标，处理旋转/缩放
- **多点触控管理**：将 Slot 协议的触控数据整合为完整的多指手势
- **设备分类与路由**：根据设备能力自动匹配合适的 InputMapper

### 1.4 为什么要分成两个组件

这是经典的关注点分离（Separation of Concerns）：

| 维度 | EventHub | InputReader |
| :--- | :--- | :--- |
| 关注的层次 | Linux 内核接口 | Android 框架语义 |
| 核心操作 | fd 管理、epoll、ioctl | 事件解析、坐标变换、状态机 |
| 变化驱动力 | 内核 API 变更、新设备类型 | Android 框架需求变更、新手势类型 |
| 可测试性 | 可 mock 为固定事件序列 | 可独立于硬件进行单元测试 |

这种分离使得 EventHub 可以用 FakeEventHub 替换进行测试，也使得新增 InputMapper（如 RotaryEncoderInputMapper）不需要改动任何设备管理代码。

---

## 2. Linux Input 子系统基础

> 源码路径：`drivers/input/` (kernel)

### 2.1 内核 Input 子系统架构

Linux Input 子系统采用三层架构：

```
┌──────────────────────────────────────────────┐
│  Event Handler Layer                          │
│  (evdev / keyboard / mousedev)               │
│  → 创建 /dev/input/eventX 设备节点            │
├──────────────────────────────────────────────┤
│  Input Core Layer                             │
│  (input.c)                                    │
│  → 事件路由：将设备事件分发给匹配的 handler    │
├──────────────────────────────────────────────┤
│  Input Device Driver Layer                    │
│  (触摸屏驱动 / 按键驱动 / 传感器驱动)          │
│  → 将硬件中断转化为 input_event 上报           │
└──────────────────────────────────────────────┘
```

**Android 主要使用 evdev handler**，它为每个输入设备创建一个 `/dev/input/eventX` 字符设备节点。用户空间通过 `open()` + `read()` 即可获取原始事件。

### 2.2 /dev/input/eventX 的创建过程

1. 触摸屏驱动调用 `input_register_device()` 向 Input Core 注册设备
2. Input Core 遍历已注册的 handler，找到匹配的 evdev handler
3. evdev handler 调用 `evdev_connect()`，创建 `/dev/input/eventX` 节点
4. 该节点对应一个 `evdev_client` 环形缓冲区，缓存来自驱动的事件

### 2.3 struct input_event

这是用户空间从 `/dev/input/eventX` 读到的数据结构：

```c
// include/uapi/linux/input.h
struct input_event {
    struct timeval time;  // 事件发生时间（内核时间戳）
    __u16 type;           // 事件类型：EV_ABS, EV_KEY, EV_SYN, EV_REL ...
    __u16 code;           // 事件代码：ABS_MT_POSITION_X, KEY_POWER ...
    __s32 value;          // 事件值：坐标值 / 按下(1)放开(0) ...
};
```

关键事件类型：

| type | 含义 | 典型 code | 场景 |
| :--- | :--- | :--- | :--- |
| `EV_ABS` (0x03) | 绝对坐标 | `ABS_MT_POSITION_X/Y` | 触摸屏坐标 |
| `EV_KEY` (0x01) | 按键/触摸按下 | `BTN_TOUCH`, `KEY_BACK` | 按键事件 |
| `EV_SYN` (0x00) | 同步信号 | `SYN_REPORT`, `SYN_MT_REPORT` | 一帧数据结束 |
| `EV_REL` (0x02) | 相对坐标 | `REL_X`, `REL_Y` | 鼠标/触控板 |

### 2.4 多点触控协议

Linux 内核支持两种多点触控协议：

**Protocol A（Type A）—— SYN_MT_REPORT 协议：**

每个触点的数据以 `SYN_MT_REPORT` 分隔，一帧以 `SYN_REPORT` 结束。每帧需要上报所有触点的完整数据。这种协议不支持触点追踪，由用户空间负责匹配前后帧的触点对应关系。

```
ABS_MT_POSITION_X  100    // 触点 1 X
ABS_MT_POSITION_Y  200    // 触点 1 Y
SYN_MT_REPORT              // 触点 1 结束
ABS_MT_POSITION_X  300    // 触点 2 X
ABS_MT_POSITION_Y  400    // 触点 2 Y
SYN_MT_REPORT              // 触点 2 结束
SYN_REPORT                 // 一帧结束
```

**Protocol B（Type B）—— Slot 协议：**

通过 `ABS_MT_SLOT` 指定触点槽位，通过 `ABS_MT_TRACKING_ID` 标识触点生命周期。只需上报变化的数据，效率更高。

```
ABS_MT_SLOT        0      // 切换到 slot 0
ABS_MT_TRACKING_ID 45     // slot 0 的追踪 ID（新触点）
ABS_MT_POSITION_X  100    // slot 0 的 X
ABS_MT_POSITION_Y  200    // slot 0 的 Y
ABS_MT_SLOT        1      // 切换到 slot 1
ABS_MT_TRACKING_ID 46     // slot 1 的追踪 ID
ABS_MT_POSITION_X  300    // slot 1 的 X
ABS_MT_POSITION_Y  400    // slot 1 的 Y
SYN_REPORT                 // 一帧结束
```

触点抬起时，将 `ABS_MT_TRACKING_ID` 设为 -1：

```
ABS_MT_SLOT        0
ABS_MT_TRACKING_ID -1     // slot 0 的触点抬起
SYN_REPORT
```

### 2.5 Android 使用 Protocol B 的细节

**Android 几乎所有触摸屏驱动都使用 Protocol B**，原因：

1. **增量上报**：只发送变化数据，减少数据量和中断频率
2. **硬件追踪**：由触摸 IC 固件完成触点追踪（tracking_id），比用户空间算法更精确
3. **Slot 映射**：slot 编号直接映射到 `MultiTouchInputMapper` 的 `mCurrentRawState.rawPointerData.pointers[]` 数组索引

EventHub 读到的数据流示例（单指按下 → 移动 → 抬起）：

```
EV_ABS ABS_MT_SLOT        0
EV_ABS ABS_MT_TRACKING_ID 100
EV_ABS ABS_MT_POSITION_X  540
EV_ABS ABS_MT_POSITION_Y  960
EV_KEY BTN_TOUCH           1
EV_SYN SYN_REPORT          0     ← InputReader 在此处理一帧

EV_ABS ABS_MT_POSITION_X  542
EV_ABS ABS_MT_POSITION_Y  965
EV_SYN SYN_REPORT          0     ← 增量更新，只有变化的轴

EV_ABS ABS_MT_TRACKING_ID -1
EV_KEY BTN_TOUCH           0
EV_SYN SYN_REPORT          0     ← 触点抬起
```

---

## 3. EventHub 深度解析

> 源码：`frameworks/native/services/inputflinger/reader/EventHub.cpp`
> 头文件：`frameworks/native/services/inputflinger/reader/include/EventHub.h`

### 3.1 核心数据结构

```cpp
// EventHub.h (简化)
class EventHub : public EventHubInterface {
private:
    // 所有已识别的输入设备，key 是设备 ID
    std::unordered_map<int32_t, std::unique_ptr<Device>> mDevices;

    // 主 epoll 文件描述符，监听所有设备 fd + inotify fd + wake pipe
    android::base::unique_fd mEpollFd;

    // inotify 文件描述符，监听 /dev/input/ 目录变化
    android::base::unique_fd mINotifyFd;

    // 唤醒管道：外部线程通过写入 wake pipe 唤醒 epoll_wait
    android::base::unique_fd mWakeReadPipeFd;
    android::base::unique_fd mWakeWritePipeFd;

    // 待处理的设备变更列表
    std::vector<std::unique_ptr<Device>> mOpeningDevices;
    std::vector<std::unique_ptr<Device>> mClosingDevices;

    // 设备节点路径
    static const char* DEVICE_PATH;  // "/dev/input"
};
```

**Device 结构体**包含了单个输入设备的全部信息：

```cpp
struct Device {
    int fd;                          // 设备文件描述符
    int32_t id;                      // EventHub 分配的设备 ID
    std::string path;                // /dev/input/eventX
    InputDeviceIdentifier identifier; // 设备标识（name, vendor, product）
    std::unique_ptr<TouchState> touchState; // 触摸状态（Protocol B slot 数据）
    std::shared_ptr<KeyLayoutMap> keyLayoutMap;      // .kl 映射
    std::shared_ptr<KeyCharacterMap> keyCharacterMap; // .kcm 映射
    std::shared_ptr<InputDeviceConfiguration> configuration; // .idc 配置
    BitArray<KEY_CNT> keyBitmask;    // 设备支持的按键位图
    BitArray<ABS_CNT> absBitmask;    // 设备支持的绝对轴位图
    uint32_t classes;                // 设备类别标志位
};
```

### 3.2 EventHub 构造函数

```cpp
// EventHub.cpp (简化)
EventHub::EventHub(void) {
    // 1. 创建 epoll 实例
    mEpollFd = android::base::unique_fd(epoll_create1(EPOLL_CLOEXEC));

    // 2. 创建 inotify 实例，监听 /dev/input/ 目录
    mINotifyFd = android::base::unique_fd(inotify_init1(IN_NONBLOCK | IN_CLOEXEC));
    inotify_add_watch(mINotifyFd.get(), DEVICE_PATH, IN_DELETE | IN_CREATE);

    // 3. 将 inotify fd 注册到 epoll
    struct epoll_event eventItem = {};
    eventItem.events = EPOLLIN | EPOLLWAKEUP;
    eventItem.data.fd = mINotifyFd.get();
    epoll_ctl(mEpollFd.get(), EPOLL_CTL_ADD, mINotifyFd.get(), &eventItem);

    // 4. 创建唤醒管道并注册到 epoll
    int wakeFds[2];
    pipe2(wakeFds, O_NONBLOCK | O_CLOEXEC);
    mWakeReadPipeFd = android::base::unique_fd(wakeFds[0]);
    mWakeWritePipeFd = android::base::unique_fd(wakeFds[1]);
    eventItem.data.fd = mWakeReadPipeFd.get();
    epoll_ctl(mEpollFd.get(), EPOLL_CTL_ADD, mWakeReadPipeFd.get(), &eventItem);
}
```

初始化完成后，epoll 上同时监听了三类 fd：

| fd 类型 | 来源 | 用途 |
| :--- | :--- | :--- |
| inotify fd | `inotify_init1()` | 监听 `/dev/input/` 设备增删 |
| wake pipe fd | `pipe2()` | 外部线程唤醒 `epoll_wait` |
| 设备 fd | `open("/dev/input/eventX")` | 读取原始输入事件 |

### 3.3 EventHub::getEvents() 完整流程

`getEvents()` 是 EventHub 的核心方法，由 InputReader 在每次 `loopOnce()` 中调用。它的设计是**批量读取**：尽可能多地填充 `RawEvent` 缓冲区后返回。

```cpp
// EventHub.cpp (高度简化，展示核心逻辑)
size_t EventHub::getEvents(int timeoutMillis, RawEvent* buffer, size_t bufferSize) {
    std::scoped_lock _l(mLock);

    RawEvent* event = buffer;
    size_t capacity = bufferSize;

    for (;;) {
        // ===== 阶段一：处理设备增删事件 =====
        while (!mClosingDevices.empty()) {
            std::unique_ptr<Device> device = std::move(mClosingDevices.back());
            mClosingDevices.pop_back();
            event->type = DEVICE_REMOVED;
            event->deviceId = device->id;
            event++;
            if (--capacity == 0) return event - buffer;
        }

        if (mNeedToScanDevices) {
            mNeedToScanDevices = false;
            scanDevicesLocked();  // 扫描 /dev/input/ 下所有设备
        }

        while (!mOpeningDevices.empty()) {
            std::unique_ptr<Device> device = std::move(mOpeningDevices.back());
            mOpeningDevices.pop_back();
            event->type = DEVICE_ADDED;
            event->deviceId = device->id;
            event++;
            mDevices[device->id] = std::move(device);
            if (--capacity == 0) return event - buffer;
        }

        // ===== 阶段二：处理 epoll 就绪事件 =====
        for (int i = 0; i < mPendingEventCount; i++) {
            const struct epoll_event& ep = mPendingEvents[i];

            if (ep.data.fd == mINotifyFd.get()) {
                // inotify 事件：设备节点创建或删除
                readNotifyLocked();
                continue;
            }

            if (ep.data.fd == mWakeReadPipeFd.get()) {
                // 唤醒事件：消费管道数据
                char wakeReadBuffer[16];
                read(mWakeReadPipeFd.get(), wakeReadBuffer, sizeof(wakeReadBuffer));
                continue;
            }

            // 设备事件：读取 input_event
            Device* device = getDeviceByFdLocked(ep.data.fd);
            if (!device) continue;

            struct input_event readBuffer[256];
            int32_t readSize = read(device->fd, readBuffer,
                                    sizeof(struct input_event) * capacity);
            size_t count = readSize / sizeof(struct input_event);

            for (size_t j = 0; j < count; j++) {
                struct input_event& iev = readBuffer[j];
                event->when = processEventTimestamp(iev);
                event->deviceId = device->id;
                event->type = iev.type;
                event->code = iev.code;
                event->value = iev.value;
                event++;
                capacity--;
                if (capacity == 0) {
                    // 缓冲区已满，保留剩余 epoll 事件到下次循环
                    mPendingEventIndex = i;
                    return event - buffer;
                }
            }
        }

        // ===== 阶段三：epoll_wait 等待新事件 =====
        mPendingEventIndex = 0;
        int pollResult = epoll_wait(mEpollFd.get(), mPendingEvents,
                                     EPOLL_MAX_EVENTS, timeoutMillis);
        mPendingEventCount = (pollResult >= 0) ? pollResult : 0;

        if (pollResult == 0) {
            // 超时，返回已读取的事件
            break;
        }
    }
    return event - buffer;
}
```

**关键设计细节：**

1. **设备事件优先**：先处理 `DEVICE_ADDED` / `DEVICE_REMOVED`，确保 InputReader 在处理事件前已知设备拓扑
2. **批量读取**：`read()` 一次可读多个 `input_event`，减少系统调用开销
3. **缓冲区满则返回**：不会阻塞在 `epoll_wait`，保证 InputReader 能及时处理已有事件
4. **时间戳来源**：事件时间戳来自内核 `input_event.time`，反映的是硬件中断时间

### 3.4 设备打开流程：openDeviceLocked()

当 `scanDevicesLocked()` 发现新设备或 inotify 报告新节点时，会调用 `openDeviceLocked()`：

```cpp
// EventHub.cpp (简化)
status_t EventHub::openDeviceLocked(const std::string& devicePath) {
    // 1. 打开设备节点
    int fd = open(devicePath.c_str(), O_RDWR | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) {
        // 权限问题可能导致打开失败
        ALOGE("could not open %s, %s", devicePath.c_str(), strerror(errno));
        return -errno;
    }

    // 2. 读取设备信息
    char deviceName[256];
    ioctl(fd, EVIOCGNAME(sizeof(deviceName)), deviceName);

    struct input_id inputId;
    ioctl(fd, EVIOCGID, &inputId);  // vendor, product, version

    // 3. 检测设备能力 —— 这是设备分类的关键步骤
    ioctl(fd, EVIOCGBIT(0, sizeof(devBitmask)), devBitmask);       // 支持的事件类型
    ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(keyBitmask)), keyBitmask);  // 支持的按键
    ioctl(fd, EVIOCGBIT(EV_ABS, sizeof(absBitmask)), absBitmask);  // 支持的绝对轴
    ioctl(fd, EVIOCGBIT(EV_REL, sizeof(relBitmask)), relBitmask);  // 支持的相对轴

    // 4. 基于能力位图进行设备分类
    auto device = std::make_unique<Device>(fd, deviceId, devicePath, identifier);

    if (test_bit(EV_ABS, devBitmask)) {
        if (test_bit(ABS_MT_POSITION_X, absBitmask) &&
            test_bit(ABS_MT_POSITION_Y, absBitmask)) {
            device->classes |= INPUT_DEVICE_CLASS_TOUCH_MT;  // 多点触控
        } else if (test_bit(ABS_X, absBitmask) &&
                   test_bit(ABS_Y, absBitmask)) {
            device->classes |= INPUT_DEVICE_CLASS_TOUCH;     // 单点触控
        }
    }

    if (test_bit(EV_KEY, devBitmask)) {
        // 根据按键范围判断是否为键盘
        for (int i = 0; i < BTN_MISC; i++) {
            if (test_bit(i, keyBitmask)) {
                device->classes |= INPUT_DEVICE_CLASS_KEYBOARD;
                break;
            }
        }
    }

    // 5. 加载设备配置文件
    loadConfigurationLocked(device.get());

    // 6. 加载键盘映射（.kl / .kcm）
    if (device->classes & INPUT_DEVICE_CLASS_KEYBOARD) {
        loadKeyMapLocked(device.get());
    }

    // 7. 注册到 epoll
    struct epoll_event eventItem = {};
    eventItem.events = EPOLLIN | EPOLLWAKEUP;
    eventItem.data.fd = fd;
    epoll_ctl(mEpollFd.get(), EPOLL_CTL_ADD, fd, &eventItem);

    // 8. 加入待添加列表
    mOpeningDevices.push_back(std::move(device));
    return OK;
}
```

**稳定性关键点**：步骤 3 中 `EVIOCGBIT` 返回的能力位图决定了设备分类。如果驱动固件存在 bug 导致能力位图不完整，EventHub 会错误分类该设备，后续 InputReader 创建 InputMapper 时就会出现问题——典型表现为"设备被识别但不响应"。

### 3.5 设备热插拔

```
inotify 监听 /dev/input/
        │
        ├─ IN_CREATE → readNotifyLocked() → openDeviceLocked()
        │                                    → 设备加入 mOpeningDevices
        │                                    → 下次 getEvents() 生成 DEVICE_ADDED
        │
        └─ IN_DELETE → readNotifyLocked() → closeDeviceLocked()
                                           → 设备加入 mClosingDevices
                                           → 下次 getEvents() 生成 DEVICE_REMOVED
                                           → 从 epoll 移除 fd
```

inotify 事件有一个已知限制：**内核 inotify 队列有大小限制**（`/proc/sys/fs/inotify/max_queued_events`，默认 16384）。在极端场景下（大量 USB 设备快速插拔），队列可能溢出导致 `IN_Q_OVERFLOW`，此时 EventHub 收不到部分设备变化通知。

---

## 4. InputReader 深度解析

> 源码：`frameworks/native/services/inputflinger/reader/InputReader.cpp`
> 头文件：`frameworks/native/services/inputflinger/reader/include/InputReader.h`

### 4.1 核心数据结构

```cpp
// InputReader.h (简化)
class InputReader : public InputReaderInterface {
private:
    // EventHub 接口引用，用于获取原始事件
    std::shared_ptr<EventHubInterface> mEventHub;

    // 设备映射表：EventHub deviceId → InputDevice
    std::unordered_map<int32_t, std::unique_ptr<InputDevice>> mDevices;

    // 事件输出监听器，连接到 InputDispatcher
    QueuedInputListener mQueuedListener;

    // 输入配置，包含屏幕信息、旋转角度等
    InputReaderConfiguration mConfig;

    // InputReader 线程，循环调用 loopOnce()
    std::unique_ptr<InputReaderThread> mThread;
};
```

### 4.2 InputReader::loopOnce() 完整流程

`loopOnce()` 是 InputReader 的主循环体，运行在独立的 `InputReaderThread` 中。

```cpp
// InputReader.cpp (简化)
void InputReader::loopOnce() {
    // ===== Step 1: 从 EventHub 获取原始事件 =====
    int32_t timeoutMillis = -1;  // 无限等待
    // mEventHub->getEvents() 会阻塞在 epoll_wait 直到有事件到来
    size_t count = mEventHub->getEvents(timeoutMillis,
                                         mEventBuffer, EVENT_BUFFER_SIZE);

    { // acquire lock
        std::scoped_lock _l(mLock);

        // ===== Step 2: 处理原始事件 =====
        if (count > 0) {
            processEventsLocked(mEventBuffer, count);
        }

        // ===== Step 3: 处理配置变更（如屏幕旋转） =====
        if (mConfigurationChangesToRefresh) {
            refreshConfigurationLocked(mConfigurationChangesToRefresh);
            mConfigurationChangesToRefresh = 0;
        }
    } // release lock

    // ===== Step 4: 将队列中的事件刷写到 InputDispatcher =====
    mQueuedListener.flush();
}
```

**关键时序**：Step 1 → Step 2 和 Step 4 之间存在锁操作。如果 Step 2 中某个 InputMapper 处理耗时过长（如复杂的坐标变换或手势识别），会导致：
- `mQueuedListener.flush()` 延迟执行
- InputDispatcher 收到事件的时间推迟
- 用户感知到触摸延迟

### 4.3 processEventsLocked() 事件处理管线

```cpp
// InputReader.cpp
void InputReader::processEventsLocked(const RawEvent* rawEvents, size_t count) {
    for (const RawEvent* rawEvent = rawEvents; count > 0; rawEvent++, count--) {
        switch (rawEvent->type) {
        case EventHubInterface::DEVICE_ADDED:
            addDeviceLocked(rawEvent->when, rawEvent->deviceId);
            break;
        case EventHubInterface::DEVICE_REMOVED:
            removeDeviceLocked(rawEvent->when, rawEvent->deviceId);
            break;
        case EventHubInterface::FINISHED_DEVICE_SCAN:
            handleConfigurationChangedLocked(rawEvent->when);
            break;
        default:
            // 普通输入事件，按设备 ID 路由
            processEventsForDeviceLocked(rawEvent->deviceId, rawEvent, 1);
            break;
        }
    }
}

void InputReader::processEventsForDeviceLocked(int32_t eventHubId,
        const RawEvent* rawEvents, size_t count) {
    auto it = mDevices.find(eventHubId);
    if (it == mDevices.end()) {
        ALOGW("Discarding event for unknown device (id=%d)", eventHubId);
        return;
    }
    it->second->process(rawEvents, count);
}
```

### 4.4 InputDevice 与 InputMapper 的关系

**一个物理设备对应一个 InputDevice，一个 InputDevice 可以持有多个 InputMapper。**

```
InputDevice (触摸屏设备)
    ├── MultiTouchInputMapper   — 处理触摸事件
    ├── KeyboardInputMapper     — 处理虚拟按键 (BTN_TOUCH 等)
    └── (其他 mapper)

InputDevice (物理键盘)
    └── KeyboardInputMapper     — 处理按键事件

InputDevice (旋转编码器)
    └── RotaryEncoderInputMapper — 处理旋转事件
```

InputMapper 的选择在 `InputDevice::addMapper()` 阶段完成，根据 EventHub 报告的设备 `classes` 自动创建：

```cpp
// InputReader.cpp (简化)
void InputReader::createDeviceLocked(int32_t eventHubId) {
    uint32_t classes = mEventHub->getDeviceClasses(eventHubId);
    auto device = std::make_unique<InputDevice>(/* ... */);

    if (classes & INPUT_DEVICE_CLASS_KEYBOARD) {
        device->addMapper<KeyboardInputMapper>(eventHubId, /* ... */);
    }
    if (classes & INPUT_DEVICE_CLASS_TOUCH_MT) {
        device->addMapper<MultiTouchInputMapper>(eventHubId, /* ... */);
    } else if (classes & INPUT_DEVICE_CLASS_TOUCH) {
        device->addMapper<SingleTouchInputMapper>(eventHubId, /* ... */);
    }
    if (classes & INPUT_DEVICE_CLASS_ROTARY_ENCODER) {
        device->addMapper<RotaryEncoderInputMapper>(eventHubId, /* ... */);
    }
    if (classes & INPUT_DEVICE_CLASS_SENSOR) {
        device->addMapper<SensorInputMapper>(eventHubId, /* ... */);
    }

    mDevices.emplace(eventHubId, std::move(device));
}
```

### 4.5 InputMapper 继承体系

```
InputMapper (抽象基类)
    ├── KeyboardInputMapper        — scancode → keycode
    ├── CursorInputMapper          — 鼠标/触控板
    ├── RotaryEncoderInputMapper   — 旋转编码器
    ├── SensorInputMapper          — 传感器
    ├── VibratorInputMapper        — 振动器
    └── TouchInputMapper (抽象)    — 触摸事件处理核心
          ├── SingleTouchInputMapper  — Protocol A / 单点触控
          └── MultiTouchInputMapper   — Protocol B / 多点触控
```

每个 InputMapper 的 `process()` 方法接收原始 `RawEvent`，输出 `NotifyArgs`：

```cpp
// InputMapper 的核心接口
class InputMapper {
public:
    // 处理原始事件，在内部积累状态
    virtual std::list<NotifyArgs> process(const RawEvent* rawEvent) = 0;

    // 重置状态
    virtual std::list<NotifyArgs> reset(nsecs_t when) = 0;

    // 配置变更
    virtual std::list<NotifyArgs> reconfigure(nsecs_t when,
            const InputReaderConfiguration& config, ConfigurationChanges changes) = 0;
};
```

### 4.6 KeyboardInputMapper 处理流程

```cpp
// KeyboardInputMapper.cpp (简化)
std::list<NotifyArgs> KeyboardInputMapper::process(const RawEvent* rawEvent) {
    std::list<NotifyArgs> out;
    if (rawEvent->type != EV_KEY) return out;

    int32_t scanCode = rawEvent->code;
    int32_t usageCode = cycleToUsageCode(scanCode);

    // scancode → keycode 映射（通过 .kl 文件）
    int32_t keyCode;
    int32_t keyMetaState;
    uint32_t policyFlags;
    if (getDeviceContext().mapKey(scanCode, usageCode,
            mMetaState, &keyCode, &keyMetaState, &policyFlags)) {
        keyCode = AKEYCODE_UNKNOWN;
    }

    bool down = rawEvent->value != 0;
    nsecs_t when = rawEvent->when;

    NotifyKeyArgs args(when, /* readTime */ when, getDeviceId(), mSource,
                       /* displayId */ ADISPLAY_ID_NONE, policyFlags,
                       down ? AKEY_EVENT_ACTION_DOWN : AKEY_EVENT_ACTION_UP,
                       /* flags */ 0, keyCode, scanCode, keyMetaState, when);
    out.push_back(args);
    return out;
}
```

---

## 5. TouchInputMapper 深度解析

> 源码：`frameworks/native/services/inputflinger/reader/mapper/TouchInputMapper.cpp`

TouchInputMapper 是事件语义化最复杂的组件。它需要将原始的 Slot 协议事件转化为完整的 `MotionEvent`（多指坐标、手势类型、坐标变换）。

### 5.1 核心处理流程

```
  原始 input_event 序列
        │
        ▼
  MultiTouchInputMapper::process()
  累积每个 slot 的轴数据到 mCurrentRawState
        │
        ▼
  收到 EV_SYN/SYN_REPORT → sync()
  一帧完整数据就绪
        │
        ▼
  processRawTouches()
  验证触点数据有效性
        │
        ▼
  cookAndDispatch()
  ├── cookPointerData()    — 坐标变换（原始坐标 → 显示坐标）
  ├── dispatchTouches()    — 手势状态机（DOWN/MOVE/UP）
  └── dispatchMotion()     — 生成 NotifyMotionArgs
        │
        ▼
  NotifyMotionArgs → QueuedInputListener
```

### 5.2 MultiTouchInputMapper::process()

```cpp
// MultiTouchInputMapper.cpp (简化)
std::list<NotifyArgs> MultiTouchInputMapper::process(const RawEvent* rawEvent) {
    std::list<NotifyArgs> out;

    if (rawEvent->type == EV_ABS) {
        switch (rawEvent->code) {
        case ABS_MT_SLOT:
            mCurrentSlot = rawEvent->value;
            break;
        case ABS_MT_TRACKING_ID:
            // tracking_id >= 0 表示触点活跃，-1 表示触点抬起
            mCurSlotTrackingId[mCurrentSlot] = rawEvent->value;
            break;
        case ABS_MT_POSITION_X:
            mCurrentRawState.rawPointerData
                .pointers[mCurrentSlot].x = rawEvent->value;
            break;
        case ABS_MT_POSITION_Y:
            mCurrentRawState.rawPointerData
                .pointers[mCurrentSlot].y = rawEvent->value;
            break;
        case ABS_MT_TOUCH_MAJOR:
            mCurrentRawState.rawPointerData
                .pointers[mCurrentSlot].touchMajor = rawEvent->value;
            break;
        case ABS_MT_PRESSURE:
            mCurrentRawState.rawPointerData
                .pointers[mCurrentSlot].pressure = rawEvent->value;
            break;
        }
    } else if (rawEvent->type == EV_SYN && rawEvent->code == SYN_REPORT) {
        // 一帧数据完整，触发同步处理
        out += sync(rawEvent->when, rawEvent->readTime);
    }

    return out;
}
```

### 5.3 Slot 管理与 Pointer ID 分配

**Slot 到 Pointer ID 的映射是 Android 多点触控的核心机制：**

- **Slot**：内核层的触点标识，由触摸 IC 的物理通道决定（通常 0-9）
- **Tracking ID**：驱动层的触点生命周期标识，触点按下时分配，抬起时设为 -1
- **Pointer ID**：Android 层的触点标识，由 `TouchInputMapper` 分配（0-based，从 0 开始递增）

映射过程：

```
Slot 0 (tracking_id=100) → Pointer ID 0
Slot 1 (tracking_id=101) → Pointer ID 1
Slot 0 (tracking_id=-1)  → Pointer ID 0 释放
Slot 2 (tracking_id=102) → Pointer ID 0 (复用已释放的 ID)
```

`assignPointerIds()` 使用匈牙利算法计算最优匹配，确保：
- 同一物理触点在整个生命周期内保持同一个 Pointer ID
- Pointer ID 从 0 开始连续分配
- 释放的 Pointer ID 可被新触点复用

```cpp
// TouchInputMapper.cpp (简化)
void TouchInputMapper::assignPointerIds(const RawState& last, RawState& current) {
    uint32_t currentPointerCount = current.rawPointerData.pointerCount;
    uint32_t lastPointerCount = last.rawPointerData.pointerCount;

    if (currentPointerCount == 0) return;

    if (lastPointerCount == 0) {
        // 全新的触点，从 0 开始分配 ID
        for (uint32_t i = 0; i < currentPointerCount; i++) {
            current.rawPointerData.idToIndex[i] = i;
            current.rawPointerData.pointers[i].id = i;
        }
        return;
    }

    // 利用 tracking_id 匹配前后帧的触点
    // 匹配成功的触点保持原有 Pointer ID
    // 新增触点分配最小可用 ID
    // ...（匈牙利算法或基于 tracking_id 的直接匹配）
}
```

### 5.4 坐标变换流程

坐标变换是触摸正确性的关键，也是折叠屏/旋转屏场景下最容易出问题的环节。

```
原始坐标（触摸屏分辨率，如 1080×2340）
        │
        ▼  calibration 校准（.idc 文件中的校准参数）
        │
        ▼  缩放变换（触摸屏物理范围 → 显示区域像素范围）
        │   xScale = (displayWidth) / (rawXMax - rawXMin)
        │   yScale = (displayHeight) / (rawYMax - rawYMin)
        │
        ▼  旋转变换（根据当前屏幕旋转角度）
        │   0°:   (x, y) → (x, y)
        │   90°:  (x, y) → (displayHeight - y, x)
        │   180°: (x, y) → (displayWidth - x, displayHeight - y)
        │   270°: (x, y) → (y, displayWidth - x)
        │
        ▼  viewport 偏移（多屏/折叠屏的显示区域偏移）
        │
        ▼
最终显示坐标（屏幕像素坐标）
```

`cookPointerData()` 中的核心变换逻辑：

```cpp
// TouchInputMapper.cpp (简化)
void TouchInputMapper::cookPointerData(
        CookedPointerData& cookedPointerData,
        const RawPointerData& rawPointerData) {

    for (uint32_t i = 0; i < rawPointerData.pointerCount; i++) {
        const RawPointerData::Pointer& in = rawPointerData.pointers[i];

        // 缩放变换
        float x = (in.x - mRawPointerAxes.x.minValue) * mXScale + mXTranslate;
        float y = (in.y - mRawPointerAxes.y.minValue) * mYScale + mYTranslate;

        // 旋转变换
        float xTransformed, yTransformed;
        switch (mInputDeviceOrientation) {
        case DISPLAY_ORIENTATION_90:
            xTransformed = mDisplayHeight - y;
            yTransformed = x;
            break;
        case DISPLAY_ORIENTATION_180:
            xTransformed = mDisplayWidth - x;
            yTransformed = mDisplayHeight - y;
            break;
        case DISPLAY_ORIENTATION_270:
            xTransformed = y;
            yTransformed = mDisplayWidth - x;
            break;
        default:
            xTransformed = x;
            yTransformed = y;
            break;
        }

        // viewport 偏移
        xTransformed += mViewport.logicalLeft;
        yTransformed += mViewport.logicalTop;

        cookedPointerData.pointerCoords[i].setAxisValue(AMOTION_EVENT_AXIS_X,
                                                         xTransformed);
        cookedPointerData.pointerCoords[i].setAxisValue(AMOTION_EVENT_AXIS_Y,
                                                         yTransformed);
    }
}
```

**稳定性关键**：`mXScale` / `mYScale` / `mViewport` 等参数在 `reconfigure()` 中更新，而 `reconfigure()` 由 `InputReaderConfiguration` 变化触发。如果 DisplayManager 更新 viewport 的时机与 InputReader 的 `reconfigure()` 不同步，就会出现短暂的坐标偏移。

### 5.5 手势状态机

`dispatchTouches()` 实现了 Android 的触摸手势状态机：

```cpp
// TouchInputMapper.cpp (简化)
std::list<NotifyArgs> TouchInputMapper::dispatchTouches(nsecs_t when,
        nsecs_t readTime, uint32_t policyFlags) {
    std::list<NotifyArgs> out;

    BitSet32 currentIdBits = mCurrentCookedState.cookedPointerData.touchingIdBits;
    BitSet32 lastIdBits = mLastCookedState.cookedPointerData.touchingIdBits;
    BitSet32 idBitsUnchanged = currentIdBits & lastIdBits;

    if (currentIdBits == lastIdBits) {
        if (!currentIdBits.isEmpty()) {
            // 没有触点变化，发送 ACTION_MOVE
            out += dispatchMotion(when, readTime, policyFlags,
                    mSource, AMOTION_EVENT_ACTION_MOVE,
                    /* ... */);
        }
    } else {
        // 有触点增删
        BitSet32 upIdBits(lastIdBits.value & ~currentIdBits.value);
        BitSet32 downIdBits(currentIdBits.value & ~lastIdBits.value);

        // 先处理抬起的触点
        while (!upIdBits.isEmpty()) {
            uint32_t upId = cycleWithBitSet(upIdBits);
            upIdBits.clearBit(upId);

            if (currentIdBits.isEmpty()) {
                // 最后一个触点抬起 → ACTION_UP
                out += dispatchMotion(when, readTime, policyFlags,
                        mSource, AMOTION_EVENT_ACTION_UP, /* ... */);
            } else {
                // 非最后一个触点抬起 → ACTION_POINTER_UP
                out += dispatchMotion(when, readTime, policyFlags,
                        mSource,
                        AMOTION_EVENT_ACTION_POINTER_UP | (upId << 8),
                        /* ... */);
            }
        }

        // 再处理按下的触点
        while (!downIdBits.isEmpty()) {
            uint32_t downId = cycleWithBitSet(downIdBits);
            downIdBits.clearBit(downId);

            if (lastIdBits.isEmpty() && downIdBits.isEmpty()) {
                // 第一个触点按下 → ACTION_DOWN
                out += dispatchMotion(when, readTime, policyFlags,
                        mSource, AMOTION_EVENT_ACTION_DOWN, /* ... */);
            } else {
                // 非第一个触点按下 → ACTION_POINTER_DOWN
                out += dispatchMotion(when, readTime, policyFlags,
                        mSource,
                        AMOTION_EVENT_ACTION_POINTER_DOWN | (downId << 8),
                        /* ... */);
            }
        }
    }

    return out;
}
```

**状态转换规则：**

```
无触点                       → 第一个触点按下 → ACTION_DOWN
单触点 / 多触点 MOVE         → 坐标变化     → ACTION_MOVE
已有触点的基础上新触点按下     → 新触点加入   → ACTION_POINTER_DOWN
多触点中某个触点抬起           → 触点移除     → ACTION_POINTER_UP
最后一个触点抬起               → 全部释放     → ACTION_UP
```

### 5.6 生成 NotifyMotionArgs

`dispatchMotion()` 最终组装 `NotifyMotionArgs` 并投递到 `QueuedInputListener`：

```cpp
// TouchInputMapper.cpp (简化)
std::list<NotifyArgs> TouchInputMapper::dispatchMotion(
        nsecs_t when, nsecs_t readTime, uint32_t policyFlags,
        uint32_t source, int32_t action, int32_t actionButton,
        int32_t flags, int32_t metaState, int32_t buttonState,
        int32_t edgeFlags, const PointerProperties* properties,
        const PointerCoords* coords, uint32_t pointerCount,
        const IdToIndexMapping& idToIndex, BitSet32 idBits,
        int32_t changedId, float xPrecision, float yPrecision,
        nsecs_t downTime) {

    std::list<NotifyArgs> out;

    NotifyMotionArgs args(
        when, readTime, getDeviceId(), source, mViewport.displayId,
        policyFlags, action, actionButton, flags,
        metaState, buttonState, MotionClassification::NONE,
        edgeFlags, pointerCount, properties, coords,
        xPrecision, yPrecision,
        AMOTION_EVENT_INVALID_CURSOR_POSITION,
        AMOTION_EVENT_INVALID_CURSOR_POSITION,
        downTime, /* videoFrames */ {});

    out.push_back(args);
    return out;
}
```

`NotifyMotionArgs` 包含了 InputDispatcher 进行窗口匹配和事件分发所需的全部信息：坐标、时间戳、触点数量、手势类型、显示 ID 等。

---

## 6. 设备配置文件体系

> 源码：`frameworks/native/services/inputflinger/reader/EventHub.cpp` (`loadConfigurationLocked`)
> 配置文件：`frameworks/base/data/keyboards/`

### 6.1 .idc 文件（Input Device Configuration）

`.idc` 文件定义输入设备的物理特性和行为参数。

**文件路径和匹配优先级**（从高到低）：

```
1. /odm/usr/idc/Vendor_XXXX_Product_XXXX_Version_XXXX.idc
2. /vendor/usr/idc/Vendor_XXXX_Product_XXXX_Version_XXXX.idc
3. /system/usr/idc/Vendor_XXXX_Product_XXXX.idc
4. /data/system/devices/idc/Vendor_XXXX_Product_XXXX.idc
5. /odm/usr/idc/DEVICE_NAME.idc
6. /vendor/usr/idc/DEVICE_NAME.idc
7. /system/usr/idc/DEVICE_NAME.idc
```

**常用配置项：**

```properties
# 设备类型：touchScreen / touchPad / pointer / trackball
touch.deviceType = touchScreen

# 触摸屏是否感知屏幕旋转
touch.orientationAware = 1

# 尺寸校准方式：none / geometric / diameter / area
touch.size.calibration = geometric

# 压力校准
touch.pressure.calibration = amplitude
touch.pressure.scale = 0.01

# 坐标范围覆盖（当驱动报告的范围不准确时）
touch.size.isSummed = 0
```

**对 TouchInputMapper 行为的影响**：

| 配置项 | 影响 |
| :--- | :--- |
| `touch.deviceType` | 决定创建 TouchInputMapper 还是 CursorInputMapper |
| `touch.orientationAware` | 是否在屏幕旋转时进行坐标变换 |
| `touch.size.calibration` | 影响触摸面积的计算方式 |
| `touch.pressure.calibration` | 影响压力值的归一化方式 |

### 6.2 .kl 文件（Key Layout）

`.kl` 文件定义 Linux scancode 到 Android keycode 的映射。

```
# frameworks/base/data/keyboards/Generic.kl
key 1     ESCAPE
key 2     1
key 3     2
key 28    ENTER
key 57    SPACE
key 102   HOME
key 114   VOLUME_DOWN
key 115   VOLUME_UP
key 116   POWER
key 158   BACK
```

**加载流程**：

```
EventHub::openDeviceLocked()
    → loadKeyMapLocked()
        → 按优先级搜索 .kl 文件（Vendor_XXXX_Product_XXXX.kl → Generic.kl）
        → KeyLayoutMap::load() 解析文件
        → 存储到 Device::keyLayoutMap
```

### 6.3 .kcm 文件（Key Character Map）

`.kcm` 文件定义 Android keycode 到 Unicode 字符的映射，影响 `KeyCharacterMap::getMatch()` 等 API。

```
# frameworks/base/data/keyboards/Generic.kcm
type FULL

key A {
    label:    'A'
    base:     'a'
    shift:    'A'
    capslock: 'A'
}
```

### 6.4 配置文件加载流程

```cpp
// EventHub.cpp (简化)
void EventHub::loadConfigurationLocked(Device* device) {
    // 按 Vendor_XXXX_Product_XXXX 搜索 .idc 文件
    std::string idcFile = getInputDeviceConfigurationFilePathByDeviceIdentifier(
            device->identifier, InputDeviceConfigurationFileType::CONFIGURATION);

    if (!idcFile.empty()) {
        device->configuration = std::make_shared<InputDeviceConfiguration>();
        status_t status = InputDeviceConfiguration::load(
                String8(idcFile.c_str()), device->configuration.get());
        if (status) {
            ALOGW("Unable to load input device configuration for device '%s'",
                   device->identifier.name.c_str());
        }
    }
}
```

**稳定性提示**：如果 `.idc` 文件中 `touch.deviceType` 配置错误（如将触摸屏配置为 `touchPad`），TouchInputMapper 会以触控板模式处理事件，导致触摸行为异常——光标模式而非直接映射模式。

---

## 7. InputReader 与 InputDispatcher 的连接

> 源码：`frameworks/native/services/inputflinger/InputListener.cpp`

### 7.1 QueuedInputListener 机制

`QueuedInputListener` 是 InputReader 和 InputDispatcher 之间的缓冲层。InputMapper 生成的 `NotifyArgs` 先被收集到队列中，在 `loopOnce()` 末尾一次性 flush 到 InputDispatcher。

```cpp
// InputListener.cpp (简化)
class QueuedInputListener {
private:
    InputListenerInterface& mInnerListener;  // 实际是 InputDispatcher
    std::vector<NotifyArgs> mArgsQueue;      // 事件暂存队列

public:
    void notify(const NotifyArgs& args) {
        mArgsQueue.push_back(args);
    }

    void flush() {
        for (const auto& args : mArgsQueue) {
            notifyInner(args);
        }
        mArgsQueue.clear();
    }

private:
    void notifyInner(const NotifyArgs& args) {
        // 根据类型调用 InputDispatcher 的对应方法
        std::visit([&](const auto& typedArgs) {
            using T = std::decay_t<decltype(typedArgs)>;
            if constexpr (std::is_same_v<T, NotifyMotionArgs>) {
                mInnerListener.notifyMotion(typedArgs);
            } else if constexpr (std::is_same_v<T, NotifyKeyArgs>) {
                mInnerListener.notifyKey(typedArgs);
            }
            // ...
        }, args);
    }
};
```

### 7.2 NotifyMotionArgs / NotifyKeyArgs 数据结构

```cpp
// InputListener.h (简化)
struct NotifyMotionArgs {
    nsecs_t eventTime;          // 事件时间（来自内核时间戳）
    nsecs_t readTime;           // 读取时间（EventHub 读到事件的时间）
    int32_t deviceId;           // 设备 ID
    uint32_t source;            // 事件来源（SOURCE_TOUCHSCREEN 等）
    int32_t displayId;          // 显示 ID（多屏场景）
    int32_t action;             // 手势动作（ACTION_DOWN/MOVE/UP）
    uint32_t pointerCount;      // 触点数量
    PointerProperties pointerProperties[MAX_POINTERS]; // 触点属性
    PointerCoords pointerCoords[MAX_POINTERS];         // 触点坐标
    float xPrecision;           // X 精度
    float yPrecision;           // Y 精度
    nsecs_t downTime;           // ACTION_DOWN 的时间
};

struct NotifyKeyArgs {
    nsecs_t eventTime;
    nsecs_t readTime;
    int32_t deviceId;
    uint32_t source;
    int32_t action;             // ACTION_DOWN / ACTION_UP
    int32_t keyCode;            // Android keycode
    int32_t scanCode;           // Linux scancode
    int32_t metaState;          // 修饰键状态
    nsecs_t downTime;
};
```

### 7.3 InputDispatcher::notifyMotion() 接收事件

```cpp
// InputDispatcher.cpp (简化)
void InputDispatcher::notifyMotion(const NotifyMotionArgs& args) {
    // 1. 策略拦截（如截屏手势）
    uint32_t policyFlags = args.policyFlags;
    if (!validateMotionEvent(args.action, args.actionButton,
            args.pointerCount, args.pointerProperties)) {
        return;
    }

    // 2. 构建 MotionEntry
    std::unique_ptr<MotionEntry> newEntry = std::make_unique<MotionEntry>(
            args.id, args.eventTime, args.deviceId, args.source,
            args.displayId, policyFlags, args.action, args.actionButton,
            args.flags, args.metaState, args.buttonState,
            args.classification, args.edgeFlags,
            args.xPrecision, args.yPrecision,
            args.xCursorPosition, args.yCursorPosition,
            args.downTime, args.pointerCount,
            args.pointerProperties, args.pointerCoords);

    // 3. 加入 mInboundQueue
    bool needWake;
    {
        std::scoped_lock _l(mLock);
        needWake = enqueueInboundEventLocked(std::move(newEntry));
    }

    // 4. 唤醒 InputDispatcherThread
    if (needWake) {
        mLooper->wake();
    }
}
```

### 7.4 两个线程之间的生产者-消费者关系

```
InputReaderThread (生产者)            InputDispatcherThread (消费者)
────────────────────                ──────────────────────────
loopOnce()                          dispatchOnce()
  │                                   │
  ├─ getEvents()                      ├─ mLooper->pollOnce() [等待]
  ├─ processEventsLocked()            │
  ├─ mQueuedListener.flush()          │
  │    └─ notifyMotion() ─────────────┤
  │         → enqueue mInboundQueue   │
  │         → mLooper->wake() ────────┘ [被唤醒]
  │                                   ├─ dispatchOnceInnerLocked()
  │                                   │    ├─ dequeue mInboundQueue
  │                                   │    ├─ findTouchedWindowTargetsLocked()
  │                                   │    └─ dispatchEventLocked()
  │                                   │         → InputChannel::sendMessage()
  │                                   └─ [继续等待下一批事件]
  └─ [继续下一次 loopOnce()]
```

**关键性能指标**：从 `getEvents()` 读到事件到 `notifyMotion()` 加入 `mInboundQueue`，这段时间反映了 InputReader 的处理开销。在 Systrace 中可以通过对比 `eventTime`（内核时间戳）和 `readTime`（用户空间读取时间）来衡量驱动延迟，通过 `readTime` 和 `enqueueTime` 差值来衡量 InputReader 的处理延迟。

---

## 8. 稳定性风险点

### 8.1 EventHub 层风险

**风险一：epoll fd 泄漏**

| 维度 | 说明 |
| :--- | :--- |
| 现象 | 新接入的 USB 设备无响应，但 `getevent -l` 可以看到事件 |
| 原因 | epoll fd 泄漏后 `epoll_ctl(EPOLL_CTL_ADD)` 返回 `ENOMEM`/`ENOSPC`，新设备 fd 无法注册 |
| 排查 | `ls /proc/<pid>/fd \| wc -l` 查看 system_server 的 fd 数量；`cat /proc/<pid>/fdinfo/<fd>` 确认 epoll fd |
| 影响 | 外接键盘/鼠标/手柄等设备无法使用 |

**风险二：inotify 事件丢失**

| 维度 | 说明 |
| :--- | :--- |
| 现象 | 设备热插拔后不生效，`dumpsys input` 中设备列表未更新 |
| 原因 | `/proc/sys/fs/inotify/max_queued_events` 达到上限，IN_Q_OVERFLOW |
| 排查 | `dmesg` 查看 inotify 相关错误 |
| 影响 | 外接设备插入后无法使用，需要重启 InputManager |

**风险三：设备节点权限**

| 维度 | 说明 |
| :--- | :--- |
| 现象 | 某些特定设备（如指纹传感器模拟输入）在部分机型上不工作 |
| 原因 | SELinux 策略或 ueventd.rc 配置导致 system_server 无权限打开 `/dev/input/eventX` |
| 排查 | `ls -la /dev/input/` 查看权限；`dmesg \| grep avc` 查看 SELinux 拒绝日志 |
| 影响 | 该设备的输入完全失效 |

### 8.2 InputReader 层风险

**风险四：InputReader 线程阻塞**

| 维度 | 说明 |
| :--- | :--- |
| 现象 | 所有输入设备的事件延迟增大（不仅是触摸，包括按键） |
| 原因 | InputReader 线程因持锁竞争或 CPU 调度被延迟，`loopOnce()` 执行时间过长 |
| 排查 | Systrace 查看 `InputReader` 线程的调度情况；`readTime - eventTime` 差值 |
| 影响 | 触摸延迟、按键延迟，是事件积压的最早源头 |

**风险五：坐标变换错误**

| 维度 | 说明 |
| :--- | :--- |
| 现象 | 触摸点与实际点击位置偏移，特别在屏幕旋转后 |
| 原因 | `mViewport` 配置未及时更新，或 `.idc` 中 `orientationAware` 配置错误 |
| 排查 | `dumpsys input` 查看 InputDevice 的 viewport 信息和坐标变换参数 |
| 影响 | 触摸偏移/错位，App 层面表现为"点不准" |

**风险六：InputMapper 创建失败**

| 维度 | 说明 |
| :--- | :--- |
| 现象 | 设备被识别（`dumpsys input` 可见）但无任何响应 |
| 原因 | 设备能力检测异常导致 classes 标志位错误，未创建正确的 InputMapper |
| 排查 | `dumpsys input` 查看设备的 `Classes` 和 `Mappers` 列表 |
| 影响 | 特定设备完全无响应 |

### 8.3 设备配置层风险

**风险七：.idc 配置错误**

| 维度 | 说明 |
| :--- | :--- |
| 现象 | 触摸屏被识别为触控板（光标模式），或外接触摸屏坐标不正确 |
| 原因 | `.idc` 文件中 `touch.deviceType` 配置错误 |
| 排查 | 确认 `/vendor/usr/idc/` 和 `/system/usr/idc/` 下的 `.idc` 文件内容 |
| 影响 | 触摸行为异常 |

**风险八：.kl 映射错误**

| 维度 | 说明 |
| :--- | :--- |
| 现象 | 物理按键按下后功能不正确（如音量键变成亮度调节） |
| 原因 | `.kl` 文件中 scancode → keycode 映射错误 |
| 排查 | `getevent -l` 查看 scancode → `dumpsys input` 查看 keycode 映射结果 |
| 影响 | 按键功能异常 |

---

## 9. 实战案例

### Case 1：折叠屏展开后触摸偏移

**问题现象**

某折叠屏手机在从折叠模式切换到展开（平板）模式后，用户点击屏幕上方区域时，实际触发的位置比预期偏下约 50px。App 的按钮点击需要"往上偏一点"才能命中，严重影响使用体验。问题在折叠回去再展开后有时自行恢复，但复现率约 30%。

**排查过程**

**Step 1：确认硬件层数据**

使用 `getevent -lp` 查看原始触摸坐标：

```bash
$ getevent -lp /dev/input/event2
# 按下屏幕顶部中央位置
EV_ABS  ABS_MT_SLOT        0
EV_ABS  ABS_MT_TRACKING_ID 1234
EV_ABS  ABS_MT_POSITION_X  1080   # 屏幕宽度 2160 的中点
EV_ABS  ABS_MT_POSITION_Y  100    # 靠近顶部
EV_SYN  SYN_REPORT         0
```

原始坐标正确，硬件层排除。

**Step 2：检查 InputReader 的坐标变换**

通过 `dumpsys input` 查看 InputDevice 的 viewport 信息：

```
Input Reader State:
  Device 2: sec_touchscreen
    Classes: TOUCH | TOUCH_MT
    Viewport:
      displayId=0
      orientation=0
      logicalFrame=[0, 0, 2160, 2480]    ← 展开模式的分辨率
      physicalFrame=[0, 0, 2160, 2480]
      deviceSize=[2160, 2480]
```

但 TouchInputMapper 内部的变换参数（通过增加调试日志后发现）：

```
TouchInputMapper: mDisplayHeight=1860, mYScale=0.750
```

`mDisplayHeight` 仍然是折叠模式的高度 1860，而非展开模式的 2480。这意味着 Y 坐标的缩放因子仍在使用旧值。

**Step 3：定位时序问题**

通过添加 trace 日志追踪 `reconfigure()` 的调用时序：

```
[T1] DisplayManager: onFoldStateChanged(UNFOLDED)
[T2] DisplayManager: updateViewport(displayId=0, height=2480)
[T3] InputReader: reconfigure() - viewport updated
```

在正常情况下 T2 < T3，但在复现问题时：

```
[T1] DisplayManager: onFoldStateChanged(UNFOLDED)
[T2] InputReader: loopOnce() → 处理积压的触摸事件 → 使用旧 viewport
[T3] DisplayManager: updateViewport(displayId=0, height=2480)
[T4] InputReader: reconfigure() - viewport updated（但 T2 的事件已经用了旧参数）
```

问题在于 DisplayManager 在折叠状态切换时，viewport 更新（T3）晚于 InputReader 处理事件（T2）。如果在切换瞬间有触摸事件，InputReader 会使用旧的变换参数处理，导致坐标偏移。更严重的是，某些情况下 `reconfigure()` 的通知由于 Binder 调用延迟，可能延迟数百毫秒。

**根因**

DisplayManagerService 在折叠/展开切换时，先通知 SurfaceFlinger 更新显示配置，再通过 `InputManagerService.setDisplayViewports()` 通知 InputReader。这两步之间存在时间窗口，期间 InputReader 使用的 viewport 与实际显示不一致。

**修复方案**

1. **短期**：在 `DisplayManagerService.onFoldStateChanged()` 中，确保 `setDisplayViewports()` 在 SurfaceFlinger 配置更新的同一个事务中同步完成
2. **长期**：InputReader 在检测到 viewport 变化后，丢弃变化前最后几帧使用旧参数计算的触摸事件（已有标志位 `mDeviceReset`），并对 App 发送 `ACTION_CANCEL`

---

### Case 2：USB 键盘间歇性按键无响应

**问题现象**

用户通过 USB OTG 连接外接键盘（某品牌机械键盘），在正常使用一段时间后，键盘突然部分按键无响应。字母键和数字键正常，但 Enter、Backspace、方向键等功能键完全失效。重新插拔 USB 后恢复，但数小时后再次出现。

**排查过程**

**Step 1：确认内核层事件**

```bash
$ getevent -lt /dev/input/event5
# 按下 Enter 键
[  135.247123] EV_KEY  KEY_ENTER   DOWN
[  135.367456] EV_KEY  KEY_ENTER   UP
```

内核层事件正常上报，排除硬件和驱动问题。

**Step 2：检查 InputReader 设备状态**

```bash
$ dumpsys input
Input Reader State:
  Device 5: USB Keyboard
    Classes: 0x00000001 (KEYBOARD)
    Mappers:
      KeyboardInputMapper
        KeyboardType: FULL
        KeyLayoutFile: /system/usr/keylayout/Generic.kl
        ...
```

设备被正确识别，`KeyboardInputMapper` 也已创建。但进一步查看 KeyboardInputMapper 的映射结果：

```
# 在 KeyboardInputMapper::process() 添加调试日志后
KeyboardInputMapper: scanCode=28 → keyCode=0 (UNKNOWN)  # Enter
KeyboardInputMapper: scanCode=14 → keyCode=0 (UNKNOWN)  # Backspace
KeyboardInputMapper: scanCode=103 → keyCode=0 (UNKNOWN) # UP
```

scancode 正确（28 = Enter），但映射到 keycode 时返回了 `UNKNOWN`。

**Step 3：检查 Key Layout 加载**

进一步排查发现，该键盘的 `.kl` 文件加载路径异常。该键盘固件有一个 bug：在长时间使用后，USB 控制器会自发重新枚举设备，导致内核删除并重新创建 `/dev/input/event5`。

EventHub 通过 inotify 检测到设备重新添加，调用 `openDeviceLocked()` 重新打开设备。但在 `EVIOCGBIT` 查询设备能力时，由于 USB 控制器尚未完成完全初始化，键盘只报告了部分按键能力：

```
EVIOCGBIT(EV_KEY): bit 0-83 set (字母/数字/符号)
                   bit 96+ NOT set (功能键: Enter, Backspace, arrows)
```

由于能力位图不完整，`loadKeyMapLocked()` 选择了一个简化的 `.kl` 文件，其中不包含功能键的映射。

**根因**

USB 键盘固件 bug 导致设备重新枚举。在重新枚举过程中，EventHub 的 `EVIOCGBIT` ioctl 查询发生在 USB 设备初始化完成之前，获取到了不完整的能力位图。虽然设备后续完成了初始化，但 EventHub 不会重新查询能力。

**修复方案**

1. **针对该设备**：创建专用的 `.idc` 文件 `Vendor_XXXX_Product_YYYY.idc`，显式指定设备类型：

```properties
keyboard.type = full
keyboard.builtIn = 0
```

这使得 EventHub 跳过自动能力检测，直接使用 `Generic.kl` 进行完整的按键映射。

2. **系统级**：在 `openDeviceLocked()` 中增加重试机制——当 USB 设备的能力位图明显不完整时（如 keyboard 设备支持的按键少于阈值），延迟 200ms 后重新查询一次。对应的代码修改位于：

```cpp
// EventHub.cpp - openDeviceLocked() 增加重试
if (isUsbDevice(device) && isKeyboardCapabilityIncomplete(device)) {
    ALOGW("USB keyboard capability incomplete, retrying in 200ms");
    usleep(200000);
    // 重新查询能力
    ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(keyBitmask)), keyBitmask);
    reclassifyDeviceLocked(device);
}
```

3. **监控**：在 EventHub 中增加能力位图变化的监控指标，当 USB 设备重新枚举后能力发生变化时上报告警，用于提前发现此类问题。

---

## 总结

EventHub 和 InputReader 共同承担了 Android Input 系统中"从硬件到语义"的关键转化工作。EventHub 屏蔽了 Linux Input 子系统的复杂性，提供了统一的事件读取和设备管理接口；InputReader 通过 InputMapper 体系将原始的 `input_event` 三元组转化为富含语义的 `NotifyMotionArgs` / `NotifyKeyArgs`。

对于稳定性架构师，这两个组件的核心关注点是：

1. **EventHub 的设备管理可靠性**：epoll/inotify 资源泄漏、设备能力检测准确性、权限配置正确性
2. **InputReader 的处理及时性**：InputReaderThread 的调度优先级、`loopOnce()` 的执行耗时、坐标变换的正确性
3. **配置文件的正确性**：`.idc` / `.kl` / `.kcm` 文件的匹配和内容是否正确

当出现"触摸无响应"或"触摸偏移"问题时，排查路径是：

```
getevent（验证内核层）
    → dumpsys input（验证 EventHub 设备识别 + InputReader 坐标变换）
        → Systrace（验证 InputReader 线程调度和处理延迟）
            → 源码分析（定位具体的变换参数或 Mapper 逻辑问题）
```

下一篇 [03-InputDispatcher：事件分发引擎与窗口选择](03-InputDispatcher.md) 将深入 InputDispatcher 的事件分发逻辑、窗口选择算法和 ANR 超时检测机制。
