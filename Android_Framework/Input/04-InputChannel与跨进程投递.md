# InputChannel 与跨进程投递：从 system_server 到 App 的事件通道

> **系列**：面向稳定性的 Android Input 子系统深度解析系列(Input_FWK)
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `net/unix/af_unix.c`、`frameworks/native/libs/input/InputTransport.cpp`;Android 14 InputChannel mmap 优化见 §4)
> **目标读者**:Android 稳定性框架架构师
> **前置阅读**:[01-Input 系统总览](01-Input系统总览.md) / [03-InputDispatcher](03-InputDispatcher.md)
> **下一篇**:[05-View 事件分发](05-View事件分发.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 4 篇(InputChannel,跨进程传输层)
- **强依赖**:
  - [01-Input 系统总览](01-Input系统总览.md) §3 五层架构(本篇聚焦 Layer 4)
  - [03-InputDispatcher](03-InputDispatcher.md)(本篇消费 InputDispatcher 产出)
  - [Socket 06-UDS](../../Linux_Kernel/socket/06-Unix_Domain_Socket与Android使用.md)(InputChannel 底层是 socketpair)
- **承接自**:03 已讲分发层。本篇深入"跨进程传输"
- **衔接去**:05 View 消费 + 06 ANR 触发
- **不重复内容**:UDS socketpair 详见 06;ANR 判定详见 06 §3

#### §0 锚点案例的可验证 4 件套:App 端 InputChannel socketpair 关闭后触摸丢失 8s

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某浏览器 v110(脱敏代号 `WebApp`,WebView 频繁创建/销毁)
> - 工具:`dumpsys input` + `lsof -p <pid>` + `cat /proc/<tid>/stack` + `perfetto`

> **复现步骤**:
> 1. 工厂重置,安装 WebApp v110
> 2. 反复打开/关闭 WebView Activity 200 次(模拟页面切换)
> 3. `adb shell input tap 500 500` → App 无响应
> 4. `dumpsys input | grep "Connection to WebApp"` 看连接状态
> 5. `cat /proc/<webapp_pid>/fd | wc -l` 看 fd 数量

> **logcat / dumpsys 关键片段**:
> ```
> # dumpsys input
> Input Channel State:
>   com.web.app/.WebViewActivity (broken)    ← 连接断开
>   Last touch: 14:32:18.001 (8s ago)
> # lsof -p $(pidof com.web.app) | grep unix
> com.web.app 1234 ... 148u unix 0xffff... 24513 @input_dispatcher_8   ← InputChannel 一边残留
> # /proc/<system_server_pid>/net/unix
> ffff880123456789 5 ... @input_dispatcher_8      ← 引用计数 5,但本应 1(泄漏)
> # perfetto trace
> 14:32:18.001 kernel: input_event
> 14:32:18.025 InputDispatcher: findTargetWindow → com.web.app/.WebViewActivity
> 14:32:18.030 InputDispatcher: send → /dev/null (broken pipe)
> 14:32:26.001 InputDispatcher: ANR check → 8s 未消费 → ANR!
> # ANR dump
> ANR in com.web.app
> Reason: Input dispatching timed out
>   no input events received in 8000ms
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/frameworks/base/services/core/java/com/android/server/input/InputManagerService.java
> +++ b/frameworks/base/services/core/java/com/android/server/input/InputManagerService.java
> @@ unregisterInputChannel
> -    // 旧版:unregister 只断开连接,不主动 close socketpair
> -    mInputChannels.remove(channel.getToken());
> +    // 修复:dispose 阶段双向 close,确保 fd 引用计数归零
> +    channel.dispose();   // 内部 close server + client 两端
> +    mInputChannels.remove(channel.getToken());
> ```
> ```diff
> --- a/frameworks/base/core/java/android/view/InputChannel.java
> +++ b/frameworks/base/core/java/android/view/InputChannel.java
> @@ dispose
> -    // 旧版:dispose 只是空实现
> +    // 修复:dispose 关闭 native FD 并清空 mPtr
> +    public void dispose() {
> +        if (mPtr != 0) {
> +            nativeDispose(mPtr);
> +            mPtr = 0;
> +        }
> +    }
> ```
> 完整 InputChannel ↔ socketpair ↔ fd passing ↔ 引用计数管理见 §3 §5 §7。

## 1. InputChannel 的定位与设计意图

### 1.1 在 Input 五层架构中的位置

InputChannel 处于 Input 系统的**传输层**，是连接 system_server 进程（InputDispatcher）与 App 进程的唯一事件通道：

```
┌────────────────────────────────────────────────────────────────┐
│  App Layer        View.dispatchTouchEvent / onTouchEvent        │
│                   WindowInputEventReceiver                      │
│                   ← InputChannel (client fd) ←                  │
├─────────────────────── ↑ Unix Domain Socket ───────────────────┤
│  Transport Layer  InputChannel / InputPublisher / InputConsumer  │  ← 本篇重点
│                   → InputChannel (server fd) →                  │
├────────────────────────────────────────────────────────────────┤
│  Dispatch Layer   InputDispatcher (窗口选择 / ANR 检测)          │
├────────────────────────────────────────────────────────────────┤
│  Reader Layer     InputReader + InputMapper (语义化)             │
├────────────────────────────────────────────────────────────────┤
│  HAL Layer        EventHub (epoll + /dev/input/eventX)          │
├────────────────────────────────────────────────────────────────┤
│  Kernel Layer     Linux Input Subsystem (驱动)                   │
└────────────────────────────────────────────────────────────────┘
```

InputChannel 解决的核心问题：**如何将 system_server 中 InputDispatcher 选好的目标事件，以低延迟、高可靠的方式跨进程投递到 App，并接收 App 的处理回执。**

### 1.2 为什么不用 Binder

Binder 是 Android IPC 的"瑞士军刀"，但 Input 事件投递没有选择它，原因在于语义和性能的根本不匹配：

| 维度 | Binder | InputChannel (Unix Domain Socket) |
| :--- | :--- | :--- |
| 通信语义 | RPC（request-response），调用方阻塞等待返回值 | 单向流式数据 + 异步回复 |
| 延迟开销 | 一次 Binder 调用涉及 copy_from_user + 内核空间拷贝 + copy_to_user，约 10-50μs | socket send/recv 直接在内核缓冲区操作，约 1-5μs |
| 序列化 | 需要 Parcel 序列化/反序列化，涉及对齐、类型标记等额外开销 | 直接发送 C 结构体（InputMessage），零拷贝语义 |
| epoll 集成 | Binder fd 虽然可 epoll，但 Binder 线程池模型与主线程 Looper 不兼容 | socket fd 天然集成到 NativeLooper 的 epoll 机制 |
| 吞吐场景 | 适合低频 RPC（每秒几十次） | 120Hz 触摸屏每秒可产生 120+ 个 MOVE 事件 |

触摸事件投递是**单向流式数据**——InputDispatcher 持续向 App 推送事件，App 异步回复 `finishInputEvent`。Binder 的 request-response 模式会让每次事件投递都阻塞在等待返回值上，这在 120Hz 刷新率（每帧 8.3ms）下是无法接受的。

### 1.3 为什么选择 Unix Domain Socket

Unix Domain Socket（UDS）是 InputChannel 的底层传输机制，具体使用 `socketpair(AF_UNIX, SOCK_SEQPACKET, 0)` 创建。选择 UDS 的原因：

- **双向通信**：server 端发事件，client 端回复 `finishInputEvent`，一对 fd 即可满足
- **epoll 友好**：socket fd 可以直接注册到 Looper 的 epoll，与 Handler 消息、VSync 信号共享同一个 epoll 循环
- **低延迟**：无需 Parcel 序列化，InputMessage 是一个固定布局的 C 结构体，直接通过 `send()` / `recv()` 传输
- **消息边界保持**：`SOCK_SEQPACKET` 保证每次 `send()` 的数据在 `recv()` 端作为完整的一条消息被读取，不会出现粘包问题

### 1.4 InputChannel 的两端

一个 InputChannel pair 由 `socketpair()` 创建，生成两个 fd：

```
system_server 进程                          App 进程
┌──────────────────────┐                 ┌──────────────────────┐
│  InputDispatcher     │                 │  ViewRootImpl        │
│       │              │                 │       │              │
│  Connection          │                 │  InputEventReceiver  │
│       │              │                 │       │              │
│  InputPublisher      │    socketpair   │  InputConsumer       │
│       │              │   ┌─────────┐   │       │              │
│  InputChannel ───────┼──→│ server  │   │  InputChannel        │
│  (server fd)         │   │   fd    │←──┼── (client fd)        │
│                      │   └─────────┘   │                      │
└──────────────────────┘                 └──────────────────────┘
```

- **Server Channel**：注册到 InputDispatcher 的 Looper，用于发送事件和接收 `finishInputEvent` 回复
- **Client Channel**：通过 Binder 返回给 App 进程，注册到 App 主线程 Looper，用于接收事件和发送回复

### 1.5 与 Binder 的互补关系

InputChannel 和 Binder 并非替代关系，而是分工协作：

| 职责 | 通信机制 | 频率 |
| :--- | :--- | :--- |
| 事件投递（MotionEvent / KeyEvent） | InputChannel (UDS) | 高频（120Hz+） |
| finishInputEvent 回复 | InputChannel (UDS) | 高频（与事件 1:1） |
| 注册 InputChannel（addWindow） | Binder (WMS ↔ App) | 低频（窗口生命周期） |
| 注销 InputChannel（removeWindow） | Binder (WMS ↔ IMS) | 低频（窗口生命周期） |
| ANR 回调通知 | Binder (IMS → AMS) | 极低频（异常场景） |

**InputChannel 负责高频数据面，Binder 负责低频控制面。** 这种分离确保了事件投递路径上没有 Binder 锁竞争和序列化开销。

---

## 2. InputChannel 的创建流程

### 2.1 创建时机

InputChannel 在 **App 添加窗口时** 创建。完整的触发链始于 `ViewRootImpl.setView()`，终于 InputChannel pair 被分别注册到 InputDispatcher 和 App 主线程 Looper。

### 2.2 完整调用链

```
App 进程                                    system_server 进程
─────────                                  ────────────────────
ViewRootImpl.setView()
  → mWindowSession.addToDisplayAsUser()
       │  (Binder IPC)
       └───────────────────────────────────→ Session.addToDisplayAsUser()
                                                → WMS.addWindow()
                                                    → win.openInputChannel()
                                                        → InputChannel.openInputChannelPair(name)
                                                           底层: socketpair(AF_UNIX, SOCK_SEQPACKET, 0)
                                                           生成 serverChannel + clientChannel
                                                    → IMS.registerInputChannel(serverChannel)
                                                        → native: InputDispatcher::registerInputChannel()
                                                           创建 Connection + addFd 到 Looper
                                                    → 将 clientChannel 写入 outInputChannel
       ←───────────────────────────────────  (Binder 返回, outInputChannel 携带 client fd)
  ← 收到 clientChannel
  → new WindowInputEventReceiver(clientChannel, Looper.myLooper())
       → JNI: NativeInputEventReceiver::initialize()
           → InputConsumer 初始化
           → Looper.addFd(clientChannel.fd, ALOOPER_EVENT_INPUT)
```

### 2.3 Step 1: ViewRootImpl.setView()

> 源码：`frameworks/base/core/java/android/view/ViewRootImpl.java`

```java
// ViewRootImpl.java (简化)
public void setView(View view, WindowManager.LayoutParams attrs, View panelParentView) {
    synchronized (this) {
        if (mView == null) {
            mView = view;

            // 创建 InputChannel 占位对象，用于接收 WMS 返回的 client channel
            InputChannel inputChannel = new InputChannel();

            // 通过 Binder 调用 WMS.addWindow()，传入 inputChannel 作为输出参数
            res = mWindowSession.addToDisplayAsUser(mWindow, mWindowAttributes,
                    getHostVisibility(), mDisplay.getDisplayId(),
                    userId, mInsetsController.getRequestedVisibleTypes(),
                    inputChannel, mTempInsets, mTempControls);

            // 用返回的 client channel 创建事件接收器
            if (inputChannel != null) {
                mInputEventReceiver = new WindowInputEventReceiver(
                        inputChannel, Looper.myLooper());
            }
        }
    }
}
```

### 2.4 Step 2: WMS.addWindow() 创建 InputChannel Pair

> 源码：`frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java`

```java
// WindowManagerService.java (简化)
public int addWindow(Session session, IWindow client, LayoutParams attrs,
        int viewVisibility, int displayId, int requestUserId,
        InsetsVisibilities requestedVisibilities,
        InputChannel outInputChannel, InsetsState outInsetsState,
        InsetsSourceControl[] outActiveControls) {

    // ... 权限检查、窗口策略验证 ...

    final WindowState win = new WindowState(this, session, client, token, parentWindow,
            appOp, attrs, viewVisibility, session.mUid, userId,
            session.mCanAddInternalSystemWindow);

    // 为窗口创建 InputChannel pair
    final boolean openInputChannels = (outInputChannel != null
            && (attrs.inputFeatures & INPUT_FEATURE_NO_INPUT_CHANNEL) == 0);
    if (openInputChannels) {
        win.openInputChannel(outInputChannel);
    }

    // ... 窗口布局、焦点更新 ...

    return res;
}
```

### 2.5 Step 3: openInputChannel() 底层实现

> 源码：`frameworks/base/services/core/java/com/android/server/wm/WindowState.java`

```java
// WindowState.java (简化)
void openInputChannel(InputChannel outInputChannel) {
    String name = getName();
    // 创建 socketpair，生成 server + client 两个 InputChannel
    InputChannel[] inputChannels = InputChannel.openInputChannelPair(name);
    mInputChannel = inputChannels[0];  // server channel 留在 WMS
    inputChannels[1].transferTo(outInputChannel);  // client channel 返回给 App
    inputChannels[1].dispose();

    // 将 server channel 注册到 InputDispatcher
    mWmService.mInputManager.registerInputChannel(mInputChannel);
}
```

`InputChannel.openInputChannelPair()` 的 Native 实现：

> 源码：`frameworks/native/libs/input/InputTransport.cpp`

```cpp
// InputTransport.cpp (简化)
status_t InputChannel::openInputChannelPair(const std::string& name,
        std::unique_ptr<InputChannel>& outServerChannel,
        std::unique_ptr<InputChannel>& outClientChannel) {

    int sockets[2];
    // SOCK_SEQPACKET: 有序、可靠、保持消息边界的数据报
    if (socketpair(AF_UNIX, SOCK_SEQPACKET, 0, sockets)) {
        ALOGE("Could not create input channel pair: %s", strerror(errno));
        return -errno;
    }

    // 设置缓冲区大小
    int bufferSize = SOCKET_BUFFER_SIZE;  // 通常 32KB - 256KB
    setsockopt(sockets[0], SOL_SOCKET, SO_SNDBUF, &bufferSize, sizeof(bufferSize));
    setsockopt(sockets[0], SOL_SOCKET, SO_RCVBUF, &bufferSize, sizeof(bufferSize));
    setsockopt(sockets[1], SOL_SOCKET, SO_SNDBUF, &bufferSize, sizeof(bufferSize));
    setsockopt(sockets[1], SOL_SOCKET, SO_RCVBUF, &bufferSize, sizeof(bufferSize));

    // 生成唯一 token（用于 InputDispatcher 中的 Connection 查找）
    sp<IBinder> token = sp<BBinder>::make();

    outServerChannel = InputChannel::create(name + " (server)", sockets[0], token);
    outClientChannel = InputChannel::create(name + " (client)", sockets[1], token);

    return OK;
}
```

### 2.6 SOCK_SEQPACKET 的特性

`socketpair()` 第二个参数使用 `SOCK_SEQPACKET` 而非常见的 `SOCK_STREAM` 或 `SOCK_DGRAM`，这是一个深思熟虑的选择：

| 特性 | SOCK_STREAM | SOCK_DGRAM | SOCK_SEQPACKET |
| :--- | :--- | :--- | :--- |
| 可靠性 | 可靠 | 不可靠 | 可靠 |
| 有序性 | 有序 | 无序 | 有序 |
| 消息边界 | 无（字节流） | 有 | 有 |
| 连接模式 | 面向连接 | 无连接 | 面向连接 |

`SOCK_SEQPACKET` 结合了 TCP 的可靠性和 UDP 的消息边界特性。对于 InputChannel 而言：

- **可靠性**：保证事件不丢失（除非 socket buffer 满导致 `EWOULDBLOCK`）
- **有序性**：保证事件按发送顺序到达
- **消息边界**：一个 `InputMessage` 通过一次 `send()` 发送，对端一次 `recv()` 即可完整接收，无需处理粘包/拆包

### 2.7 Step 4: 注册到 InputDispatcher

> 源码：`frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`

```cpp
// InputDispatcher.cpp (简化)
status_t InputDispatcher::registerInputChannel(
        const std::shared_ptr<InputChannel>& inputChannel) {

    { // acquire lock
        std::scoped_lock _l(mLock);

        // 检查是否已注册
        sp<IBinder> token = inputChannel->getConnectionToken();
        if (getConnectionIndexLocked(token) >= 0) {
            ALOGW("Attempted to register already registered input channel '%s'",
                    inputChannel->getName().c_str());
            return BAD_VALUE;
        }

        // 创建 Connection 对象
        std::unique_ptr<Connection> connection =
                std::make_unique<Connection>(inputChannel, /*monitor=*/false,
                                              mIdGenerator);
        int fd = inputChannel->getFd();

        // 将 server channel 的 fd 注册到 InputDispatcher 的 Looper
        // 当 App 端回复 finishInputEvent 时，此 fd 变为可读
        mLooper->addFd(fd, 0, ALOOPER_EVENT_INPUT,
                        handleReceiveCallback, this);

        mConnectionsByToken.emplace(token, std::move(connection));
    } // release lock

    // 唤醒 InputDispatcher 线程
    mLooper->wake();
    return OK;
}
```

### 2.8 Step 5–6: Client Channel 返回 App 并创建 Receiver

Client channel 通过 Binder 返回给 App 后，`ViewRootImpl` 使用它创建 `WindowInputEventReceiver`。接收器在构造时将 client fd 注册到主线程 Looper：

> 源码：`frameworks/base/core/jni/android_view_InputEventReceiver.cpp`

```cpp
// android_view_InputEventReceiver.cpp (简化)
status_t NativeInputEventReceiver::initialize() {
    // 将 InputChannel 的 fd 注册到 NativeLooper
    // ALOOPER_EVENT_INPUT: 当 fd 可读时回调 handleEvent
    setFdEvents(ALOOPER_EVENT_INPUT);
    return OK;
}

void NativeInputEventReceiver::setFdEvents(int events) {
    if (events) {
        mMessageQueue->getLooper()->addFd(
                mInputConsumer.getChannel()->getFd(),
                0, events, this, nullptr);
    } else {
        mMessageQueue->getLooper()->removeFd(
                mInputConsumer.getChannel()->getFd());
    }
}
```

至此，InputChannel 的创建流程完成。Server fd 在 InputDispatcher 的 Looper 中监听 App 回复，Client fd 在 App 主线程 Looper 中监听事件到达。

---

## 3. 事件的序列化与传输

### 3.1 InputMessage 结构体

> 源码：`frameworks/native/libs/input/include/input/InputTransport.h`

`InputMessage` 是 InputChannel 上传输的底层消息格式，它是一个联合体（union），包含不同类型的消息体：

```cpp
// InputTransport.h (简化)
struct InputMessage {
    struct Header {
        uint32_t type;   // 消息类型：MOTION / KEY / FINISHED / FOCUS / ...
        uint32_t seq;    // 序列号，用于回复匹配
    } header;

    union Body {
        struct Motion {
            int32_t eventId;
            uint32_t pointerCount;
            nsecs_t eventTime;
            nsecs_t downTime;
            int32_t source;
            int32_t displayId;
            int32_t action;
            int32_t actionButton;
            int32_t flags;
            int32_t metaState;
            int32_t buttonState;
            int32_t classification;
            int32_t edgeFlags;
            float xPrecision;
            float yPrecision;
            float xCursorPosition;
            float yCursorPosition;
            uint32_t empty3;
            // 变长部分：每个触点的坐标数据
            struct Pointer {
                PointerProperties properties;
                PointerCoords coords;
            } pointers[MAX_POINTERS];
        } motion;

        struct Key {
            int32_t eventId;
            nsecs_t eventTime;
            nsecs_t downTime;
            int32_t source;
            int32_t displayId;
            int32_t action;
            int32_t flags;
            int32_t keyCode;
            int32_t scanCode;
            int32_t metaState;
            int32_t repeatCount;
        } key;

        struct Finished {
            uint32_t seq;
            uint32_t handled;  // App 是否消费了该事件
            nsecs_t consumeTime;
        } finished;
    } body;

    size_t size() const;
};
```

消息大小取决于类型和触点数量：

| 消息类型 | 大小估算 |
| :--- | :--- |
| Key | ~100 bytes（固定） |
| Motion（单指） | ~200 bytes |
| Motion（双指） | ~300 bytes |
| Motion（最大 16 指） | ~1600 bytes |
| Finished（回复） | ~24 bytes |

### 3.2 InputPublisher：Server 端发送

> 源码：`frameworks/native/libs/input/InputTransport.cpp`

InputPublisher 负责将 `MotionEvent` / `KeyEvent` 序列化为 `InputMessage` 并发送：

```cpp
// InputTransport.cpp (简化)
status_t InputPublisher::publishMotionEvent(
        uint32_t seq, int32_t eventId, int32_t deviceId, int32_t source,
        int32_t displayId, std::array<uint8_t, 32> hmac,
        int32_t action, int32_t actionButton, int32_t flags,
        int32_t edgeFlags, int32_t metaState, int32_t buttonState,
        MotionClassification classification,
        const ui::Transform& transform, float xPrecision, float yPrecision,
        float xCursorPosition, float yCursorPosition,
        uint32_t displayOrientation, int32_t displayWidth, int32_t displayHeight,
        nsecs_t downTime, nsecs_t eventTime,
        uint32_t pointerCount,
        const PointerProperties* pointerProperties,
        const PointerCoords* pointerCoords) {

    InputMessage msg;
    msg.header.type = InputMessage::Type::MOTION;
    msg.header.seq = seq;

    msg.body.motion.eventId = eventId;
    msg.body.motion.pointerCount = pointerCount;
    msg.body.motion.eventTime = eventTime;
    msg.body.motion.downTime = downTime;
    msg.body.motion.action = action;
    msg.body.motion.source = source;
    msg.body.motion.displayId = displayId;
    // ... 填充其余字段 ...

    for (uint32_t i = 0; i < pointerCount; i++) {
        msg.body.motion.pointers[i].properties = pointerProperties[i];
        msg.body.motion.pointers[i].coords = pointerCoords[i];
    }

    return mChannel->sendMessage(&msg);
}
```

### 3.3 InputChannel::sendMessage() / receiveMessage()

```cpp
// InputTransport.cpp
status_t InputChannel::sendMessage(const InputMessage* msg) {
    const size_t msgLength = msg->size();
    ssize_t nWrite;
    do {
        nWrite = ::send(getFd(), msg, msgLength, MSG_DONTWAIT | MSG_NOSIGNAL);
    } while (nWrite == -1 && errno == EINTR);

    if (nWrite < 0) {
        int error = errno;
        if (error == EAGAIN || error == EWOULDBLOCK) {
            // socket buffer 满，无法发送
            return WOULD_BLOCK;
        }
        // socket 异常
        return -error;
    }

    if (size_t(nWrite) != msgLength) {
        // SOCK_SEQPACKET 保证原子写入，部分写入表示异常
        return DEAD_OBJECT;
    }
    return OK;
}

status_t InputChannel::receiveMessage(InputMessage* msg) {
    ssize_t nRead;
    do {
        nRead = ::recv(getFd(), msg, sizeof(InputMessage), MSG_DONTWAIT);
    } while (nRead == -1 && errno == EINTR);

    if (nRead < 0) {
        int error = errno;
        if (error == EAGAIN || error == EWOULDBLOCK) {
            return WOULD_BLOCK;
        }
        return -error;
    }

    if (nRead == 0) {
        // 对端关闭了 socket
        return DEAD_OBJECT;
    }

    if (!msg->isValid(nRead)) {
        return BAD_VALUE;
    }
    return OK;
}
```

`MSG_DONTWAIT` 表示非阻塞模式——如果 socket buffer 满（无法写入）或空（无数据可读），立即返回 `EAGAIN` / `EWOULDBLOCK` 而不阻塞线程。

### 3.4 InputConsumer：Client 端接收

> 源码：`frameworks/native/libs/input/InputTransport.cpp`

InputConsumer 负责从 InputChannel 读取 `InputMessage` 并反序列化为 `InputEvent`：

```cpp
// InputTransport.cpp (简化)
status_t InputConsumer::consume(InputEventFactoryInterface* factory,
        bool consumeBatches, nsecs_t frameTime,
        uint32_t* outSeq, InputEvent** outEvent) {

    *outSeq = 0;
    *outEvent = nullptr;

    // 读取新消息
    while (!*outEvent) {
        // 先检查是否有可合并的 batch
        if (consumeBatches && !mBatches.empty()) {
            // Motion Batching: 多个 MOVE 合并为一个
            *outEvent = consumeBatchLocked(factory, frameTime, outSeq);
            if (*outEvent) return OK;
        }

        // 从 socket 读取新消息
        InputMessage msg;
        status_t result = mChannel->receiveMessage(&msg);
        if (result) return result;

        switch (msg.header.type) {
        case InputMessage::Type::KEY: {
            KeyEvent* keyEvent = factory->createKeyEvent();
            initializeKeyEvent(keyEvent, &msg);
            *outSeq = msg.header.seq;
            *outEvent = keyEvent;
            break;
        }

        case InputMessage::Type::MOTION: {
            // 检查是否可以与现有 batch 合并
            ssize_t batchIndex = findBatch(msg.body.motion.deviceId,
                                            msg.body.motion.source);
            if (batchIndex >= 0 && canAppendToBatch(msg)) {
                // 合并到已有 batch
                mBatches[batchIndex].samples.push_back(msg);
            } else {
                MotionEvent* motionEvent = factory->createMotionEvent();
                initializeMotionEvent(motionEvent, &msg);
                *outSeq = msg.header.seq;
                *outEvent = motionEvent;
            }
            break;
        }
        }
    }

    return OK;
}
```

### 3.5 Motion Batching：事件合并

Motion Batching 是 InputConsumer 的核心优化机制。在 120Hz 触摸屏上，每帧可能有多个 `ACTION_MOVE` 事件到达 App 端。如果逐个分发，每个 MOVE 都要走一遍 View 树分发和 `onTouchEvent` 回调，开销巨大。

合并策略：**同一设备、同一 source、相同 pointerCount 的连续 MOVE 事件合并为一个 MotionEvent，历史坐标数据保留在 `MotionEvent.getHistoricalX()` / `getHistoricalY()` 中。**

```
socket buffer 中的 MOVE 事件:
  MOVE(t=1ms, x=100, y=200)
  MOVE(t=3ms, x=102, y=203)
  MOVE(t=5ms, x=105, y=207)

合并后的 MotionEvent:
  action = ACTION_MOVE
  current: (t=5ms, x=105, y=207)
  historical[0]: (t=1ms, x=100, y=200)
  historical[1]: (t=3ms, x=102, y=203)
```

App 层可以通过 `event.getHistorySize()` 和 `event.getHistoricalX(pointerIndex, historyIndex)` 访问合并前的原始数据，用于绘制平滑的笔画轨迹。

### 3.6 finishInputEvent 回复机制

App 处理完事件后必须回复 `finishInputEvent`，否则 InputDispatcher 的 `waitQueue` 会持续堆积，最终触发 ANR。

**回复流程（App → InputDispatcher）：**

```cpp
// InputTransport.cpp (简化)
status_t InputConsumer::sendFinishedSignal(uint32_t seq, bool handled) {
    InputMessage msg;
    msg.header.type = InputMessage::Type::FINISHED;
    msg.header.seq = seq;
    msg.body.finished.handled = handled ? 1 : 0;
    msg.body.finished.consumeTime = systemTime(SYSTEM_TIME_MONOTONIC);

    return mChannel->sendMessage(&msg);
}
```

**接收回复（InputDispatcher 端）：**

```cpp
// InputTransport.cpp (简化)
status_t InputPublisher::receiveFinishedSignal(uint32_t* outSeq, bool* outHandled) {
    InputMessage msg;
    status_t result = mChannel->receiveMessage(&msg);
    if (result) return result;

    if (msg.header.type != InputMessage::Type::FINISHED) {
        return UNKNOWN_ERROR;
    }

    *outSeq = msg.header.seq;
    *outHandled = msg.body.finished.handled != 0;
    return OK;
}
```

**seq 序列号匹配**：每个事件在发送时被分配一个唯一的 `seq`，App 回复时携带相同的 `seq`。InputDispatcher 通过 `seq` 将回复与 `waitQueue` 中的事件一一对应，确保不会错误地取消 ANR 倒计时。

---

## 4. App 端事件接收机制

### 4.1 WindowInputEventReceiver 的创建

> 源码：`frameworks/base/core/java/android/view/InputEventReceiver.java`、`frameworks/base/core/jni/android_view_InputEventReceiver.cpp`

`WindowInputEventReceiver` 是 `ViewRootImpl` 中的内部类，继承自 `InputEventReceiver`：

```java
// ViewRootImpl.java (简化)
final class WindowInputEventReceiver extends InputEventReceiver {
    public WindowInputEventReceiver(InputChannel inputChannel, Looper looper) {
        super(inputChannel, looper);
    }

    @Override
    public void onInputEvent(InputEvent event) {
        enqueueInputEvent(event, this, 0, true);
    }

    @Override
    public void onBatchedInputEventPending(int source) {
        if (mUnbufferedInputSource != 0) {
            // 对于需要低延迟的 source，立即消费 batch
            if (mBatchedInputEventPending) {
                consumeBatchedInputEvents(-1);
            }
        } else {
            scheduleConsumeBatchedInput();
        }
    }
}
```

`InputEventReceiver` 构造函数中完成 JNI 初始化：

```java
// InputEventReceiver.java (简化)
public InputEventReceiver(InputChannel inputChannel, Looper looper) {
    mInputChannel = inputChannel;
    mMessageQueue = looper.getQueue();
    // JNI: 创建 NativeInputEventReceiver 并注册 fd
    mReceiverPtr = nativeInit(new WeakReference<>(this),
            inputChannel, mMessageQueue);
}
```

### 4.2 NativeInputEventReceiver 初始化

```cpp
// android_view_InputEventReceiver.cpp (简化)
NativeInputEventReceiver::NativeInputEventReceiver(
        JNIEnv* env, jobject receiverWeak,
        const std::shared_ptr<InputChannel>& inputChannel,
        const sp<MessageQueue>& messageQueue)
    : mReceiverWeakGlobal(env->NewGlobalRef(receiverWeak)),
      mInputConsumer(inputChannel),
      mMessageQueue(messageQueue),
      mBatchedInputEventPending(false),
      mFdEvents(0) {
}

status_t NativeInputEventReceiver::initialize() {
    setFdEvents(ALOOPER_EVENT_INPUT);
    return OK;
}
```

`setFdEvents(ALOOPER_EVENT_INPUT)` 将 InputChannel 的 client fd 注册到 NativeLooper。此后，当 InputDispatcher 向 socket 写入事件时，该 fd 变为可读，NativeLooper 的 `epoll_wait` 被唤醒。

### 4.3 事件到达时的唤醒与分发

完整的事件到达处理链：

```
InputDispatcher                        App 主线程 Looper
──────────────                        ──────────────────
InputChannel::sendMessage()           NativeLooper::pollOnce()
  → socket send() ──────────────────→   epoll_wait 唤醒 (fd 可读)
                                        → NativeInputEventReceiver::handleEvent()
                                           → consumeEvents()
                                              → InputConsumer::consume()
                                                 → socket recv()
                                                 → 构建 InputEvent 对象
                                              → JNI: dispatchInputEvent()
                                                 → Java: InputEventReceiver.dispatchInputEvent()
                                                    → WindowInputEventReceiver.onInputEvent()
                                                       → ViewRootImpl.enqueueInputEvent()
                                                          → InputStage 管线分发
                                                             → View.dispatchTouchEvent()
```

`handleEvent()` 的具体实现：

```cpp
// android_view_InputEventReceiver.cpp (简化)
int NativeInputEventReceiver::handleEvent(int receiveFd, int events, void* data) {
    if (events & (ALOOPER_EVENT_ERROR | ALOOPER_EVENT_HANGUP)) {
        // socket 异常或对端关闭
        return 0;  // 移除 fd 监听
    }

    if (events & ALOOPER_EVENT_INPUT) {
        JNIEnv* env = AndroidRuntime::getJNIEnv();
        status_t status = consumeEvents(env, /*consumeBatches=*/false,
                                         /*frameTime=*/-1, /*outConsumedBatch=*/nullptr);
        if (status == DEAD_OBJECT) {
            return 0;  // InputChannel 已关闭
        }
    }

    return 1;  // 继续监听
}
```

`consumeEvents()` 是核心的事件消费方法：

```cpp
// android_view_InputEventReceiver.cpp (简化)
status_t NativeInputEventReceiver::consumeEvents(JNIEnv* env,
        bool consumeBatches, nsecs_t frameTime,
        bool* outConsumedBatch) {

    for (;;) {
        uint32_t seq;
        InputEvent* inputEvent;
        status_t status = mInputConsumer.consume(&mInputEventFactory,
                consumeBatches, frameTime, &seq, &inputEvent);

        if (status == WOULD_BLOCK) {
            // 没有更多事件可读
            return OK;
        }

        if (!inputEvent) continue;

        // 将 Native InputEvent 转为 Java 对象
        jobject inputEventObj;
        switch (inputEvent->getType()) {
        case AINPUT_EVENT_TYPE_KEY:
            inputEventObj = android_view_KeyEvent_fromNative(env,
                    static_cast<KeyEvent&>(*inputEvent));
            break;
        case AINPUT_EVENT_TYPE_MOTION:
            inputEventObj = android_view_MotionEvent_obtainAsCopy(env,
                    static_cast<MotionEvent&>(*inputEvent));
            break;
        }

        if (inputEventObj) {
            // 通过 JNI 回调 Java 层
            env->CallVoidMethod(receiverObj,
                    gInputEventReceiverClassInfo.dispatchInputEvent,
                    seq, inputEventObj);
            env->DeleteLocalRef(inputEventObj);
        }
    }
}
```

### 4.4 与 Looper/Handler 的集成

InputChannel fd 与 Handler 消息共享同一个 `epoll` 实例。这意味着 Input 事件和 Handler 消息在同一个线程循环中被处理：

```
NativeLooper.pollOnce()
  └── epoll_wait(epollFd, ...)
         │
         ├── MessageQueue pipe fd 可读 → 处理 Handler 消息
         ├── InputChannel fd 可读     → NativeInputEventReceiver.handleEvent()
         ├── VSync fd 可读            → Choreographer.doFrame()
         └── 其他 fd 事件...
```

**稳定性含义**：如果主线程的 Handler 消息处理耗时过长（如 `onBindViewHolder` 中执行同步 I/O），它不仅延迟了 Handler 消息，还延迟了 Input 事件的处理。这是因为 `epoll_wait` 返回后，Looper 必须顺序处理所有就绪的 fd callback 和消息——一个阻塞，全部排队。

### 4.5 finishInputEvent 的回复流程（App 端）

View 事件分发完成后，调用链如下：

```java
// InputEventReceiver.java
public final void finishInputEvent(InputEvent event, boolean handled) {
    if (mReceiverPtr == 0) {
        // Receiver 已销毁
    } else {
        int index = mSeqMap.indexOfKey(event.getSequenceNumber());
        if (index >= 0) {
            int seq = mSeqMap.valueAt(index);
            mSeqMap.removeAt(index);
            // JNI 调用
            nativeFinishInputEvent(mReceiverPtr, seq, handled);
        }
    }
}
```

JNI 层：

```cpp
// android_view_InputEventReceiver.cpp (简化)
status_t NativeInputEventReceiver::finishInputEvent(uint32_t seq, bool handled) {
    // 通过 InputConsumer 发送回复
    status_t status = mInputConsumer.sendFinishedSignal(seq, handled);

    if (status == WOULD_BLOCK) {
        // socket buffer 满，将回复暂存到 mFinishQueue 中延迟发送
        mFinishQueue.push_back(std::make_pair(seq, handled));
        // 监听 fd 可写事件
        setFdEvents(ALOOPER_EVENT_INPUT | ALOOPER_EVENT_OUTPUT);
        return OK;
    }

    return status;
}
```

当 `sendFinishedSignal` 返回 `WOULD_BLOCK`（socket buffer 满），回复消息被暂存到 `mFinishQueue`。同时切换 fd 监听模式为 `INPUT | OUTPUT`，当 socket buffer 有空间时（fd 可写），再从 `mFinishQueue` 中取出积压的回复发送出去。

---

## 5. Connection 对象与事件队列管理

### 5.1 InputDispatcher 中的 Connection

> 源码：`frameworks/native/services/inputflinger/dispatcher/InputDispatcher.h`

每个注册到 InputDispatcher 的 InputChannel 对应一个 `Connection` 对象。Connection 是事件投递状态的核心载体：

```cpp
// InputDispatcher.h (简化)
class Connection {
public:
    enum class Status {
        NORMAL,   // 连接正常
        BROKEN,   // 连接断开（socket 异常关闭）
    };

    Status status;
    std::shared_ptr<InputChannel> inputChannel;

    // InputPublisher: 用于通过 InputChannel 发送事件
    InputPublisher inputPublisher;

    // outboundQueue: 已准备好但尚未发送的事件队列
    // 当 waitQueue 非空（前一个事件还未被 finish）时，新事件暂存在此
    std::deque<DispatchEntry*> outboundQueue;

    // waitQueue: 已发送但等待 App finishInputEvent 回复的事件队列
    // ANR 超时检测就是基于此队列中最早事件的发送时间
    std::deque<DispatchEntry*> waitQueue;

    // 标识是否正处于 streaming 模式（连续 MOVE 事件合并传输）
    bool inputState;

    // 上一次事件回复信息
    nsecs_t lastEventTime;
    nsecs_t lastDispatchTime;
};
```

### 5.2 outboundQueue 与 waitQueue 的关系

```
事件到达 InputDispatcher
        │
        ▼
 dispatchEventLocked()
  → prepareDispatchCycleLocked()
     → enqueueDispatchEntriesLocked()
        │
        ▼
 DispatchEntry 加入 outboundQueue
        │
        ▼
 startDispatchCycleLocked()
  → 检查 waitQueue 是否为空
     │
     ├── waitQueue 为空：
     │     → InputPublisher::publishMotionEvent()
     │     → DispatchEntry 从 outboundQueue 移到 waitQueue
     │     → 启动 ANR 倒计时
     │
     └── waitQueue 非空（串行化等待）：
           → DispatchEntry 留在 outboundQueue
           → 等待 App 回复最早的事件后再发送
```

### 5.3 串行化投递策略

InputDispatcher 对同一个 Connection 采用**严格串行化投递**。核心逻辑在 `startDispatchCycleLocked()` 中：

```cpp
// InputDispatcher.cpp (简化)
void InputDispatcher::startDispatchCycleLocked(nsecs_t currentTime,
        const std::shared_ptr<Connection>& connection) {

    while (connection->status == Connection::Status::NORMAL) {
        if (connection->outboundQueue.empty()) break;

        DispatchEntry* dispatchEntry = connection->outboundQueue.front();

        // 对于 non-streaming 模式：如果 waitQueue 非空，则不发送新事件
        // 这保证了事件的顺序性和 ANR 检测的准确性
        EventEntry& eventEntry = *(dispatchEntry->eventEntry);
        if (!connection->waitQueue.empty()
                && !canStreamLocked(connection, eventEntry)) {
            break;  // 等待 App 回复后再继续
        }

        // 发送事件
        status_t status;
        switch (eventEntry.type) {
        case EventEntry::Type::MOTION: {
            MotionEntry& motionEntry = static_cast<MotionEntry&>(eventEntry);
            status = connection->inputPublisher.publishMotionEvent(
                    dispatchEntry->seq,
                    motionEntry.id,
                    motionEntry.action,
                    // ... 其余参数 ...
                    );
            break;
        }
        case EventEntry::Type::KEY: {
            // ... publishKeyEvent ...
            break;
        }
        }

        if (status) {
            // 发送失败
            if (status == WOULD_BLOCK) {
                // socket buffer 满，稍后重试
                break;
            }
            // 连接断开
            connection->status = Connection::Status::BROKEN;
            removeInputChannelLocked(connection->inputChannel->getConnectionToken());
            return;
        }

        // 发送成功：从 outboundQueue 移到 waitQueue
        connection->outboundQueue.erase(connection->outboundQueue.begin());
        connection->waitQueue.push_back(dispatchEntry);

        traceWaitQueueLength(*connection);
    }
}
```

**Motion Streaming 例外**：对于连续的 `ACTION_MOVE` 事件，InputDispatcher 允许在 `waitQueue` 非空时继续发送，这就是 **streaming mode**。`canStreamLocked()` 方法判断是否可以流式发送：

```cpp
bool InputDispatcher::canStreamLocked(
        const std::shared_ptr<Connection>& connection,
        const EventEntry& eventEntry) const {
    if (eventEntry.type != EventEntry::Type::MOTION) return false;

    const MotionEntry& motionEntry = static_cast<const MotionEntry&>(eventEntry);
    // 只有 ACTION_MOVE 和 ACTION_HOVER_MOVE 可以流式发送
    if (motionEntry.action != AMOTION_EVENT_ACTION_MOVE
            && motionEntry.action != AMOTION_EVENT_ACTION_HOVER_MOVE) {
        return false;
    }

    // waitQueue 中最后一个事件必须也是相同类型的 MOVE
    // 这样新 MOVE 可以在 App 端被合并（Motion Batching）
    return true;
}
```

### 5.4 事件积压的检测

通过 `dumpsys input` 可以直接观察 Connection 的队列状态：

```
Connection Status:
  0: channelName='com.example.app/MainActivity (server)', windowName='Window{abc}',
     status=NORMAL,
     outboundQueue length=3,       ← InputDispatcher 端积压
     waitQueue length=8,           ← App 端处理慢
     inputPublisher focusTransferInProgress=false
```

| 指标 | 正常值 | 异常阈值 | 含义 |
| :--- | :--- | :--- | :--- |
| outboundQueue length | 0 | > 5 | InputDispatcher 无法发送事件（socket buffer 满 / 串行化等待） |
| waitQueue length | 0-1 | > 3 | App 处理事件慢，`finishInputEvent` 延迟 |
| waitQueue 最早事件 age | < 100ms | > 3000ms | 接近 ANR 阈值（5000ms） |

---

## 6. InputChannel 的生命周期管理

### 6.1 注册

注册流程已在第 2 章详述。核心步骤：

1. `InputChannel.openInputChannelPair()` 创建 socketpair
2. Server channel → `InputDispatcher::registerInputChannel()` → 创建 Connection → `Looper.addFd()`
3. Client channel → Binder 返回给 App → `NativeInputEventReceiver::initialize()` → `Looper.addFd()`

### 6.2 注销

> 源码：`frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`

```cpp
// InputDispatcher.cpp (简化)
status_t InputDispatcher::removeInputChannel(const sp<IBinder>& connectionToken) {
    { // acquire lock
        std::scoped_lock _l(mLock);

        auto it = mConnectionsByToken.find(connectionToken);
        if (it == mConnectionsByToken.end()) return BAD_VALUE;

        std::shared_ptr<Connection> connection = it->second;

        // 1. 从 Looper 移除 fd 监听
        mLooper->removeFd(connection->inputChannel->getFd());

        // 2. 清理 outboundQueue 和 waitQueue 中的所有事件
        while (!connection->outboundQueue.empty()) {
            DispatchEntry* entry = connection->outboundQueue.front();
            connection->outboundQueue.erase(connection->outboundQueue.begin());
            releaseDispatchEntry(entry);
        }
        while (!connection->waitQueue.empty()) {
            DispatchEntry* entry = connection->waitQueue.front();
            connection->waitQueue.erase(connection->waitQueue.begin());
            releaseDispatchEntry(entry);
        }

        // 3. 从 Connection 表中移除
        mConnectionsByToken.erase(it);

    } // release lock

    mLooper->wake();
    return OK;
}
```

### 6.3 窗口销毁时的清理

当窗口被移除时，WMS 触发完整的清理链：

```
WMS.removeWindow(WindowState)
  → WindowState.removeIfPossible()
     → WindowState.removeImmediately()
        → InputMonitor.updateInputWindowsLw()
           → InputDispatcher 发送 ACTION_CANCEL（确保触摸序列完整）
        → IMS.unregisterInputChannel(serverChannel)
           → InputDispatcher::removeInputChannel()
              → 清理 Connection, outboundQueue, waitQueue
              → Looper.removeFd()
        → serverChannel.dispose()
           → close(fd)
```

**ACTION_CANCEL 的重要性**：如果一个窗口在触摸序列中途被销毁（如用户正在滑动时 Activity finish），InputDispatcher 必须先向 App 发送 `ACTION_CANCEL`，让 App 有机会清理触摸状态（如取消长按定时器、重置滑动速度追踪器等）。如果直接关闭 socket 而不发送 CANCEL，App 侧可能残留不一致的触摸状态。

### 6.4 InputChannel 泄漏的风险

InputChannel 泄漏本质上是 **fd 泄漏**。每个 InputChannel pair 占用 2 个 fd（server + client），外加 socketpair 的内核 buffer 内存。

**泄漏的典型原因**：

1. **窗口泄漏**：Activity / Dialog / PopupWindow 未正确销毁（如 Activity 泄漏导致其持有的 Window 也泄漏）
2. **removeWindow 被跳过**：某些异常路径下 WMS 的 `removeWindow()` 未被调用
3. **App 侧 InputEventReceiver 未 dispose**：`InputEventReceiver.dispose()` 未在窗口关闭时调用

**泄漏的后果**：

```
正常 App: ~50 fd (包括 socket, pipe, file, epoll 等)
泄漏 App: 500-900+ fd

当 fd 接近进程上限 (通常 1024 或 4096):
  → socketpair() 失败 → InputChannel 无法创建
  → 新窗口无法注册 InputChannel → 该窗口的所有 Input 事件无法投递
  → 后续所有新窗口都受影响 → 系统级触摸失效
```

检测手段：

```bash
# 查看进程 fd 数量
ls /proc/<pid>/fd | wc -l

# 查看 socket 类型 fd
ls -la /proc/<pid>/fd | grep socket

# 通过 dumpsys input 查看注册的 InputChannel 数量
dumpsys input | grep "Connection Status" | wc -l
```

---

## 7. 稳定性风险点

### 7.1 Socket Buffer 满

| 维度 | 说明 |
| :--- | :--- |
| **触发条件** | App 主线程卡顿 → 无法 `recv()` → socket 接收缓冲区满 → InputDispatcher `send()` 失败 |
| **错误码** | `send()` 返回 `-1`，`errno = EAGAIN / EWOULDBLOCK` |
| **后果** | `InputPublisher::publishMotionEvent()` 返回 `WOULD_BLOCK` → 事件留在 `outboundQueue` → InputDispatcher 无法投递新事件 |
| **表现** | 触摸无响应 / 事件丢失（非 MOVE 事件会被丢弃） |
| **阈值** | socket buffer 默认约 128KB ~ 256KB（因内核版本而异），约可容纳 500-1000 个 Motion 事件 |

```cpp
// InputDispatcher.cpp 中对 WOULD_BLOCK 的处理
if (status == WOULD_BLOCK) {
    if (connection->waitQueue.empty()) {
        ALOGE("Channel '%s' ~ Could not publish event because the pipe is full. "
              "This is unexpected because the wait queue is empty, so the pipe "
              "should be empty too.",
              connection->getInputChannelName().c_str());
        abortBrokenDispatchCycleLocked(currentTime, connection, true /*notify*/);
    } else {
        // 等待 App 消费事件腾出 buffer 空间
        connection->inputPublisherBlocked = true;
    }
}
```

### 7.2 finishInputEvent 延迟

| 维度 | 说明 |
| :--- | :--- |
| **触发条件** | App 的 `onTouchEvent` / `onKeyDown` 等回调中执行了耗时操作 |
| **影响链** | `finishInputEvent` 延迟 → `waitQueue` 堆积 → 串行化阻塞 → `outboundQueue` 堆积 → 新事件全部延迟 |
| **ANR 阈值** | `waitQueue` 中最早事件超过 5000ms 未被 finish → 触发 Input ANR |
| **量化** | 单个事件处理耗时 T → 后续 N 个事件累计延迟 = N × T（串行化放大效应） |

这是 Input ANR 最常见的根因。**串行化投递策略意味着一条慢消息会阻塞所有后续事件。** 在 120Hz 屏幕上，1 秒内会有 ~120 个 MOVE 事件，如果某次 `onTouchEvent` 执行了 50ms，则后续 6 个事件都会被延迟。

### 7.3 InputChannel 泄漏（fd 泄漏）

| 维度 | 说明 |
| :--- | :--- |
| **触发条件** | 窗口泄漏（Activity / Dialog / PopupWindow 未 dismiss） |
| **检测信号** | `/proc/<pid>/fd` 数量持续增长；logcat 出现 "Too many open files" |
| **后果** | fd 耗尽 → `socketpair()` 失败 → 新窗口无法创建 InputChannel → 系统级触摸失效 |
| **恢复** | 只能杀进程重启（fd 泄漏无法回收） |

### 7.4 Connection 状态异常（BROKEN）

| 维度 | 说明 |
| :--- | :--- |
| **触发条件** | App 进程崩溃 → socket 对端关闭 → `recv()` / `send()` 返回 `DEAD_OBJECT` |
| **处理** | InputDispatcher 将 Connection 状态设为 BROKEN → 清理 outboundQueue / waitQueue → 从 Looper 移除 fd |
| **后果** | 该窗口后续所有事件被丢弃，直到窗口被正式移除并重建 |
| **连锁反应** | 如果 BROKEN 状态的 Connection 未被及时清理，其持有的 fd 和内存不会被释放 |

```cpp
// InputDispatcher.cpp 中处理连接断开
void InputDispatcher::abortBrokenDispatchCycleLocked(nsecs_t currentTime,
        const std::shared_ptr<Connection>& connection, bool notify) {
    ALOGI("channel '%s' ~ abortBrokenDispatchCycle - Loss of connection",
          connection->getInputChannelName().c_str());

    // 标记连接状态为 BROKEN
    connection->status = Connection::Status::BROKEN;

    // 清理 outboundQueue
    drainOutboundQueueLocked(connection);

    // 如果 waitQueue 非空，对所有等待中的事件触发 finish 超时处理
    if (connection->monitor) {
        // Monitor channel 的特殊处理
    }
}
```

---

## 8. 实战案例

### Case 1：WebView 页面触摸卡顿

**现象**

某资讯类 App 的 WebView 详情页在加载复杂 H5 活动页后，用户触摸滑动明显卡顿——手指快速上下滑动时，页面有 200-300ms 的"停顿感"，不跟手。偶发 Input ANR（ANR 率约 0.08%），集中在中低端设备。用户投诉集中表述为"页面加载完后滑不动"。

**排查过程**

**Step 1: dumpsys input 抓取 Connection 状态**

在复现设备上执行 `adb shell dumpsys input`，关注目标窗口的 Connection：

```
Connection Status:
  channelName='com.example.news/WebViewActivity (server)',
  status=NORMAL,
  outboundQueue length=2,
  waitQueue length=12           ← 异常：12 个事件等待 App 回复
    DispatchEntry: seq=1024, eventTime=12345678000, deliveryTime=12345689000,
                   age=890ms, action=MOVE
    DispatchEntry: seq=1025, eventTime=12345686000, deliveryTime=12345700000,
                   age=820ms, action=MOVE
    ...
    DispatchEntry: seq=1035, eventTime=12345780000, deliveryTime=12345791000,
                   age=105ms, action=MOVE
```

`waitQueue length=12` 且最早事件已等待 890ms。这说明 App 端处理 Input 事件极慢——正常情况下 `waitQueue` 最多 1-2 个事件。

**Step 2: 主线程 Trace 分析**

抓取 Systrace，定位主线程在 Input 事件处理阶段的耗时：

```
Thread: main (tid=12345)
  deliverInputEvent                                  [0ms - 215ms]  ← 单个 MOVE 处理 215ms
    └── ViewPostImeInputStage.processPointerEvent    [2ms - 215ms]
         └── DecorView.dispatchTouchEvent            [3ms - 214ms]
              └── WebView.onTouchEvent               [5ms - 213ms]
                   └── WebViewChromium.onTouchEvent   [6ms - 212ms]
                        └── nativeOnTouchEvent        [8ms - 210ms]  ← JNI 调用 Chromium
```

单个 `ACTION_MOVE` 事件在 `WebView.onTouchEvent` 中耗时 210ms。进一步查看 Chromium renderer 线程的 Trace 日志，发现 H5 页面的 `touchmove` JavaScript 事件处理器执行了 ~200ms 的计算：

```
Blink Renderer:
  EventHandler::handleTouchEvent
    └── V8::ScriptController::executeScript
         └── touchMoveHandler()     [200ms]
              → 实时计算活动页排行榜数据
              → DOM 操作：更新 50+ 个排名元素
```

**Step 3: 串行化放大效应分析**

由于 InputDispatcher 的串行化投递策略，单次 `onTouchEvent` 的 210ms 阻塞了整个 Connection 的事件流：

```
Timeline:
T=0ms    MOVE(seq=1024) 到达 App，开始处理
T=210ms  MOVE(seq=1024) 处理完成，finishInputEvent
         → InputDispatcher 收到回复，从 waitQueue 移除
         → 开始发送 outboundQueue 中积压的下一个 MOVE
T=210ms  MOVE(seq=1025) 到达 App...
T=420ms  MOVE(seq=1025) 处理完成...
...

120Hz 屏幕每 8.3ms 一个 MOVE，210ms 内积压了 ~25 个 MOVE 事件
用户感知：滑动时反复出现 200ms 的"卡顿-跳跃"循环
```

**根因**

H5 活动页的 `touchmove` 事件处理器中执行了耗时的 JavaScript 计算（排行榜数据计算 + 大量 DOM 更新），这些操作通过 Chromium 的 renderer 线程回调到主线程的 `WebView.onTouchEvent()`，阻塞了 `finishInputEvent` 的回复。

**修复方案**

1. **H5 侧：使用 passive 事件监听器**

```javascript
// 修复前：非 passive 监听器会阻塞 touchmove 的默认行为
element.addEventListener('touchmove', handleTouchMove, { passive: false });

// 修复后：passive: true 告诉浏览器不会调用 preventDefault()
// 浏览器可以立即执行默认滚动行为，无需等待 JS 回调完成
element.addEventListener('touchmove', handleTouchMove, { passive: true });
```

当 `passive: true` 时，Chromium 的 compositor 线程可以直接处理滚动，无需等待主线程的 JavaScript 回调。这意味着即使 JS 执行了 200ms，页面滚动仍然是流畅的。

2. **H5 侧：将耗时计算移到 Web Worker**

```javascript
// 修复前：排行榜计算在主线程
function handleTouchMove(event) {
    const rankings = computeRankings(data);  // 200ms
    updateDOM(rankings);
}

// 修复后：计算在 Web Worker，结果异步更新
const worker = new Worker('ranking-worker.js');
function handleTouchMove(event) {
    worker.postMessage({ type: 'compute', data });
}
worker.onmessage = function(e) {
    requestAnimationFrame(() => updateDOM(e.data.rankings));
};
```

3. **Native 侧：限制 WebView 的 touchmove 事件频率**

在 WebView 容器层添加事件节流逻辑，确保传递给 H5 的 `touchmove` 频率不超过 60Hz（即使触摸屏上报 120Hz）。

**效果**

修复后 `WebView.onTouchEvent()` 平均耗时从 210ms → 3ms（passive 模式下 compositor 线程直接处理滚动），`waitQueue` 长度稳定在 0-1，Input ANR 率从 0.08% → 0.005%，触摸卡顿投诉清零。

---

### Case 2：多窗口场景下的 fd 泄漏

**现象**

某社交 App 在长时间运行后（通常 4-8 小时），新打开的页面无法响应任何触摸操作。用户描述为"打开新页面后点什么都没反应，只能杀进程重启"。logcat 中出现大量错误：

```
E/InputTransport: socketpair failed: Too many open files (errno=24)
E/WindowManager: Failed to create input channel for Window{xyz}
```

该问题在用户活跃度高的场景下更容易复现（频繁打开/关闭聊天窗口、查看朋友圈动态弹窗）。

**排查过程**

**Step 1: fd 泄漏确认**

```bash
# 查看进程 fd 数量
$ adb shell ls /proc/12345/fd | wc -l
923    ← 异常：正常 App 约 50-150

# 查看 fd 上限
$ adb shell cat /proc/12345/limits | grep "Max open files"
Max open files  1024

# 统计 socket 类型 fd
$ adb shell ls -la /proc/12345/fd | grep socket | wc -l
742    ← 绝大多数泄漏的 fd 是 socket
```

进程 fd 已达 923，接近上限 1024。742 个 socket fd 是泄漏的主体。

**Step 2: dumpsys input 分析 InputChannel 数量**

```bash
$ adb shell dumpsys input | grep "Connection Status" -A 2
# 输出超过 300 个 Connection，大量名称类似：
Connection Status:
  channelName='PopupWindow:com.example.social/ChatActivity#12 (server)', status=NORMAL
  channelName='PopupWindow:com.example.social/ChatActivity#13 (server)', status=NORMAL
  channelName='PopupWindow:com.example.social/ChatActivity#14 (server)', status=NORMAL
  ... (共 350+ 个 PopupWindow 的 Connection)
```

350+ 个 `PopupWindow` 类型的 InputChannel 仍然注册在 InputDispatcher 中。每个 InputChannel pair 占用 2 个 socket fd（server + client），合计 700+ 个 fd。

**Step 3: 定位泄漏源**

通过 Hprof dump 分析 Java 堆，发现大量存活的 `PopupWindow` 对象：

```
Class: android.widget.PopupWindow
  Live instances: 358
  GC Root Path:
    com.example.social.chat.EmojiPickerPopup$1 (anonymous OnClickListener)
      → com.example.social.chat.EmojiPickerPopup (PopupWindow 子类)
         → mDecorView → mAttachInfo → mViewRootImpl → mInputChannel (泄漏!)
```

业务代码中 `EmojiPickerPopup`（表情选择弹窗）在每次用户点击表情按钮时创建一个新实例，但从未调用 `dismiss()`。当 Activity 返回时，PopupWindow 的 `mDecorView` 通过 `OnClickListener` 持有 Activity 的引用，导致整条链路无法被 GC 回收。

**根因**

聊天页面的表情选择弹窗 `EmojiPickerPopup` 存在两个问题：

1. 每次点击表情按钮都 `new EmojiPickerPopup()` 而非复用
2. 弹窗的 `dismiss()` 从未被调用——既没有在用户选择表情后关闭，也没有在 Activity `onDestroy` 中清理

每个 `PopupWindow.showAsDropDown()` 都会触发 `WMS.addWindow()` → 创建 InputChannel pair → 注册到 InputDispatcher。由于 `dismiss()` 未调用，`WMS.removeWindow()` 从未执行，InputChannel 永远不会被注销，socket fd 持续泄漏。

**修复方案**

1. **复用 PopupWindow 实例**

```java
// 修复前：每次创建新实例
emojiButton.setOnClickListener(v -> {
    EmojiPickerPopup popup = new EmojiPickerPopup(this);
    popup.showAsDropDown(v);
});

// 修复后：复用单例
private EmojiPickerPopup mEmojiPopup;

emojiButton.setOnClickListener(v -> {
    if (mEmojiPopup == null) {
        mEmojiPopup = new EmojiPickerPopup(this);
    }
    if (!mEmojiPopup.isShowing()) {
        mEmojiPopup.showAsDropDown(v);
    }
});
```

2. **在 Activity.onDestroy 中强制清理**

```java
@Override
protected void onDestroy() {
    super.onDestroy();
    if (mEmojiPopup != null && mEmojiPopup.isShowing()) {
        mEmojiPopup.dismiss();
    }
    mEmojiPopup = null;
}
```

3. **全局 PopupWindow 泄漏监控**

在 Application 层注册 `ActivityLifecycleCallbacks`，在 `onActivityDestroyed` 中检查是否有未 dismiss 的 PopupWindow：

```java
registerActivityLifecycleCallbacks(new SimpleActivityLifecycleCallbacks() {
    @Override
    public void onActivityDestroyed(Activity activity) {
        Window window = activity.getWindow();
        View decorView = window.getDecorView();
        // 使用 WindowManager 检查是否有未移除的子窗口
        WindowManager wm = activity.getWindowManager();
        // 通过反射获取 mViews 列表，检查是否有残留的 PopupWindow DecorView
        List<View> leakedViews = WindowLeakDetector.detect(wm, activity);
        if (!leakedViews.isEmpty()) {
            // 上报泄漏信息并强制清理
            for (View view : leakedViews) {
                wm.removeViewImmediate(view);
            }
            reportLeak(activity, leakedViews);
        }
    }
});
```

**效果**

修复后 App 长时间运行的 fd 数量稳定在 80-120，不再增长。PopupWindow 泄漏监控上线后首月拦截了 3 处类似泄漏，提前消除了潜在的 fd 耗尽风险。触摸失效的用户投诉从每日 ~50 单降为 0。

---

## 参考与延伸

- **核心源码路径速查**

| 组件 | 路径 |
| :--- | :--- |
| InputChannel / InputPublisher / InputConsumer | `frameworks/native/libs/input/InputTransport.cpp` |
| InputChannel (Java) | `frameworks/base/core/java/android/view/InputChannel.java` |
| InputEventReceiver (Java) | `frameworks/base/core/java/android/view/InputEventReceiver.java` |
| NativeInputEventReceiver (JNI) | `frameworks/base/core/jni/android_view_InputEventReceiver.cpp` |
| InputDispatcher (Connection / 队列管理) | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` |
| ViewRootImpl (WindowInputEventReceiver) | `frameworks/base/core/java/android/view/ViewRootImpl.java` |
| WindowState (openInputChannel) | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` |
| WMS (addWindow) | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` |

- **排查工具**：`dumpsys input`（Connection 队列状态）、Systrace/Perfetto（主线程 Input 处理耗时）、`/proc/<pid>/fd`（fd 泄漏检测）、ANR traces.txt（主线程栈分析）
- **系列文章导航**：[01-Input 系统总览](01-Input系统总览.md) → [02-EventHub 与 InputReader](02-EventHub与InputReader.md) → [03-InputDispatcher](03-InputDispatcher.md) → **04-InputChannel 与跨进程投递**（本篇）→ [05-ViewRootImpl 与事件分发](05-ViewRootImpl与事件分发.md)
