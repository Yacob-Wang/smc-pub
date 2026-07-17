# InputChannel 通信机制

## 引言

InputChannel 是 Android Input 系统中用于跨进程传输输入事件的通信机制。它基于 Unix Domain Socket 实现，提供了低延迟、高效率的事件传输。本文将深入分析 InputChannel 的设计与实现。

---

## 1. InputChannel 架构概览

### 1.1 通信模型

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         system_server 进程                              │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │                      InputDispatcher                                ││
│  │  ┌──────────────────────────────────────────────────────────────┐  ││
│  │  │  Connection                                                   │  ││
│  │  │  ├── InputPublisher (发送事件)                               │  ││
│  │  │  └── server InputChannel                                     │  ││
│  │  └──────────────────────────────────────────────────────────────┘  ││
│  └────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       │ Unix Domain Socket
                                       │ (socketpair)
                                       │
┌──────────────────────────────────────┼──────────────────────────────────┐
│                                      │                                  │
│                         应用进程      │                                  │
│  ┌───────────────────────────────────▼────────────────────────────────┐│
│  │                      ViewRootImpl                                   ││
│  │  ┌──────────────────────────────────────────────────────────────┐  ││
│  │  │  WindowInputEventReceiver                                     │  ││
│  │  │  ├── InputConsumer (接收事件)                                │  ││
│  │  │  └── client InputChannel                                     │  ││
│  │  └──────────────────────────────────────────────────────────────┘  ││
│  └────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘

通信流程:
═══════════════════════════════════════════════════════════════════════════

InputDispatcher                              应用进程
     │                                            │
     │  InputPublisher.publishKeyEvent()          │
     │  ────────────────────────────────────────►│
     │             InputMessage (Key)             │
     │                                            │
     │                                            │ InputConsumer.consume()
     │                                            │ → KeyEvent
     │                                            │
     │                                            │ 事件处理
     │                                            │
     │  ◄────────────────────────────────────────│
     │         Finished Signal (seq, handled)    │
     │                                            │
```

### 1.2 为什么使用 Socket 而非 Binder？

| 特性 | Socket | Binder |
|-----|--------|--------|
| 延迟 | 低 (~0.1ms) | 较高 (~0.5ms) |
| 吞吐量 | 高 | 中等 |
| 批处理 | 支持 | 不支持 |
| 双向通信 | 天然支持 | 需要回调 |
| 缓冲区 | 有 | 无 |

---

## 2. 核心数据结构

### 2.1 InputChannel (Java 层)

```java
// frameworks/base/core/java/android/view/InputChannel.java

public final class InputChannel implements Parcelable {
    // Native 指针
    @SuppressWarnings("unused")
    private long mPtr;
    
    // 创建 Socket 对
    public static InputChannel[] openInputChannelPair(String name) {
        return nativeOpenInputChannelPair(name);
    }
    
    // 获取名称
    public String getName() {
        return nativeGetName(mPtr);
    }
    
    // 复制 channel
    public InputChannel dup() {
        InputChannel target = new InputChannel();
        nativeDup(mPtr, target);
        return target;
    }
    
    // 获取 Token
    public IBinder getToken() {
        return nativeGetToken(mPtr);
    }
    
    // 释放
    public void dispose() {
        nativeDispose(mPtr);
        mPtr = 0;
    }
    
    // Parcelable 实现 - 用于跨进程传递
    @Override
    public void writeToParcel(Parcel out, int flags) {
        nativeWriteToParcel(mPtr, out);
    }
    
    private static final Creator<InputChannel> CREATOR = ...;
}
```

### 2.2 InputChannel (Native 层)

```cpp
// frameworks/native/libs/input/InputTransport.cpp

class InputChannel {
public:
    // 创建命名 Channel
    static std::unique_ptr<InputChannel> create(const std::string& name,
                                                 android::base::unique_fd fd,
                                                 sp<IBinder> token);
    
    // 打开 Socket 对
    static status_t openInputChannelPair(const std::string& name,
                                         std::unique_ptr<InputChannel>& outServerChannel,
                                         std::unique_ptr<InputChannel>& outClientChannel);
    
    // 发送消息
    status_t sendMessage(const InputMessage* msg);
    
    // 接收消息
    status_t receiveMessage(InputMessage* msg);
    
    // 获取文件描述符
    int getFd() const { return mFd.get(); }
    
    // 获取名称
    const std::string& getName() const { return mName; }
    
    // 获取 Token
    sp<IBinder> getToken() const { return mToken; }
    
    // 复制 channel
    std::unique_ptr<InputChannel> dup() const;
    
private:
    std::string mName;
    android::base::unique_fd mFd;
    sp<IBinder> mToken;
    
    InputChannel(const std::string& name, 
                 android::base::unique_fd fd,
                 sp<IBinder> token);
};
```

### 2.3 InputMessage

```cpp
// frameworks/native/include/input/InputTransport.h

struct InputMessage {
    enum class Type : uint32_t {
        KEY = 1,
        MOTION = 2,
        FINISHED = 3,
        FOCUS = 4,
        CAPTURE = 5,
        DRAG = 6,
        TIMELINE = 7,
        TOUCH_MODE = 8,
    };
    
    struct Header {
        Type type;
        uint32_t seq;  // 序列号
    } header;
    
    union Body {
        struct Key {
            int32_t eventId;
            nsecs_t eventTime;
            int32_t deviceId;
            int32_t source;
            int32_t displayId;
            std::array<uint8_t, 32> hmac;
            int32_t action;
            int32_t flags;
            int32_t keyCode;
            int32_t scanCode;
            int32_t metaState;
            int32_t repeatCount;
            nsecs_t downTime;
        } key;
        
        struct Motion {
            int32_t eventId;
            nsecs_t eventTime;
            int32_t deviceId;
            int32_t source;
            int32_t displayId;
            std::array<uint8_t, 32> hmac;
            int32_t action;
            int32_t actionButton;
            int32_t flags;
            int32_t metaState;
            int32_t buttonState;
            MotionClassification classification;
            int32_t edgeFlags;
            nsecs_t downTime;
            float dsdx;
            float dtdx;
            float dtdy;
            float dsdy;
            float tx;
            float ty;
            float xPrecision;
            float yPrecision;
            float xCursorPosition;
            float yCursorPosition;
            int32_t displayWidth;
            int32_t displayHeight;
            uint32_t pointerCount;
            // 可变长度的指针数据 (最多 MAX_POINTERS)
            struct Pointer {
                PointerProperties properties;
                PointerCoords coords;
            } pointers[MAX_POINTERS];
        } motion;
        
        struct Finished {
            bool handled;
            nsecs_t consumeTime;
        } finished;
        
        struct Focus {
            bool hasFocus;
        } focus;
    } body;
    
    // 获取消息大小
    size_t size() const;
    
    // 验证消息
    bool isValid(size_t actualSize) const;
};
```

---

## 3. InputChannel 创建流程

### 3.1 从 WMS 创建

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java

void openInputChannel(InputChannel outInputChannel) {
    // 生成名称
    String name = getName();
    
    // 创建 Socket 对
    InputChannel[] inputChannels = InputChannel.openInputChannelPair(name);
    
    // Server channel 保留在 system_server
    mInputChannel = inputChannels[0];
    
    // Client channel 传递给应用
    mClientChannel = inputChannels[1];
    
    // 注册到 InputDispatcher
    mWmService.mInputManager.registerInputChannel(mInputChannel);
    
    // 传出 client channel
    if (outInputChannel != null) {
        mClientChannel.transferTo(outInputChannel);
        mClientChannel.dispose();
        mClientChannel = null;
    }
}
```

### 3.2 Native 层 Socket 创建

```cpp
status_t InputChannel::openInputChannelPair(const std::string& name,
                                             std::unique_ptr<InputChannel>& outServerChannel,
                                             std::unique_ptr<InputChannel>& outClientChannel) {
    // 创建 Unix Domain Socket 对
    int sockets[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET, 0, sockets)) {
        return -errno;
    }
    
    // 设置缓冲区大小
    int bufferSize = SOCKET_BUFFER_SIZE;  // 32KB
    setsockopt(sockets[0], SOL_SOCKET, SO_SNDBUF, &bufferSize, sizeof(bufferSize));
    setsockopt(sockets[0], SOL_SOCKET, SO_RCVBUF, &bufferSize, sizeof(bufferSize));
    setsockopt(sockets[1], SOL_SOCKET, SO_SNDBUF, &bufferSize, sizeof(bufferSize));
    setsockopt(sockets[1], SOL_SOCKET, SO_RCVBUF, &bufferSize, sizeof(bufferSize));
    
    // 创建 Token (用于标识窗口)
    sp<BBinder> token = new BBinder();
    
    // 创建 server channel
    std::string serverName = name + " (server)";
    outServerChannel = InputChannel::create(serverName, 
                                            android::base::unique_fd(sockets[0]),
                                            token);
    
    // 创建 client channel
    std::string clientName = name + " (client)";
    outClientChannel = InputChannel::create(clientName,
                                            android::base::unique_fd(sockets[1]),
                                            token);
    
    return OK;
}
```

---

## 4. 事件发送 - InputPublisher

### 4.1 InputPublisher 类

```cpp
class InputPublisher {
public:
    explicit InputPublisher(const std::shared_ptr<InputChannel>& channel);
    
    // 发布按键事件
    status_t publishKeyEvent(uint32_t seq,
                             int32_t eventId,
                             int32_t deviceId,
                             int32_t source,
                             int32_t displayId,
                             int32_t action,
                             int32_t flags,
                             int32_t keyCode,
                             int32_t scanCode,
                             int32_t metaState,
                             int32_t repeatCount,
                             nsecs_t downTime,
                             nsecs_t eventTime);
    
    // 发布运动事件
    status_t publishMotionEvent(uint32_t seq,
                                int32_t eventId,
                                int32_t deviceId,
                                int32_t source,
                                int32_t displayId,
                                int32_t action,
                                int32_t actionButton,
                                int32_t flags,
                                int32_t edgeFlags,
                                int32_t metaState,
                                int32_t buttonState,
                                float xOffset,
                                float yOffset,
                                float xPrecision,
                                float yPrecision,
                                float xCursorPosition,
                                float yCursorPosition,
                                nsecs_t downTime,
                                nsecs_t eventTime,
                                uint32_t pointerCount,
                                const PointerProperties* pointerProperties,
                                const PointerCoords* pointerCoords);
    
    // 发布焦点事件
    status_t publishFocusEvent(uint32_t seq, int32_t eventId, bool hasFocus);
    
    // 接收完成信号
    status_t receiveFinishedSignal(uint32_t* outSeq, bool* outHandled,
                                   nsecs_t* outConsumeTime);
    
private:
    std::shared_ptr<InputChannel> mChannel;
};
```

### 4.2 发布按键事件实现

```cpp
status_t InputPublisher::publishKeyEvent(uint32_t seq, ...) {
    InputMessage msg;
    
    // 设置消息头
    msg.header.type = InputMessage::Type::KEY;
    msg.header.seq = seq;
    
    // 设置消息体
    msg.body.key.eventId = eventId;
    msg.body.key.eventTime = eventTime;
    msg.body.key.deviceId = deviceId;
    msg.body.key.source = source;
    msg.body.key.displayId = displayId;
    msg.body.key.action = action;
    msg.body.key.flags = flags;
    msg.body.key.keyCode = keyCode;
    msg.body.key.scanCode = scanCode;
    msg.body.key.metaState = metaState;
    msg.body.key.repeatCount = repeatCount;
    msg.body.key.downTime = downTime;
    
    // 发送
    return mChannel->sendMessage(&msg);
}

// InputChannel::sendMessage
status_t InputChannel::sendMessage(const InputMessage* msg) {
    const size_t msgLength = msg->size();
    
    // 通过 Socket 发送
    ssize_t nWrite = ::send(mFd.get(), msg, msgLength, MSG_DONTWAIT | MSG_NOSIGNAL);
    
    if (nWrite < 0) {
        int error = errno;
        if (error == EAGAIN || error == EWOULDBLOCK) {
            return WOULD_BLOCK;
        }
        return -error;
    }
    
    if (size_t(nWrite) != msgLength) {
        return DEAD_OBJECT;
    }
    
    return OK;
}
```

---

## 5. 事件接收 - InputConsumer

### 5.1 InputConsumer 类

```cpp
class InputConsumer {
public:
    explicit InputConsumer(const std::shared_ptr<InputChannel>& channel);
    
    // 消费事件
    status_t consume(InputEventFactoryInterface* factory,
                     bool consumeBatches,
                     nsecs_t frameTime,
                     uint32_t* outSeq,
                     InputEvent** outEvent);
    
    // 发送完成信号
    status_t sendFinishedSignal(uint32_t seq, bool handled);
    
    // 是否有挂起的批处理
    bool hasPendingBatch() const;
    
    // 获取挂起的批处理样本数
    int32_t getPendingBatchSource() const;
    
private:
    std::shared_ptr<InputChannel> mChannel;
    
    // 消息池 (复用消息对象)
    InputMessage mMsg;
    
    // 批处理
    std::vector<Batch> mBatches;
    
    struct Batch {
        std::vector<InputMessage> samples;
    };
    
    // 触摸状态
    std::vector<TouchState> mTouchStates;
};
```

### 5.2 消费事件实现

```cpp
status_t InputConsumer::consume(InputEventFactoryInterface* factory,
                                 bool consumeBatches,
                                 nsecs_t frameTime,
                                 uint32_t* outSeq,
                                 InputEvent** outEvent) {
    *outSeq = 0;
    *outEvent = nullptr;
    
    // 检查是否有批处理的事件需要处理
    while (!mBatches.empty()) {
        Batch& batch = mBatches.front();
        if (consumeBatches || batch.samples.back().body.motion.eventTime <= frameTime) {
            // 合并批处理的事件
            MotionEvent* motionEvent = factory->createMotionEvent();
            initializeMotionEvent(motionEvent, batch.samples);
            
            *outSeq = batch.samples.front().header.seq;
            *outEvent = motionEvent;
            mBatches.erase(mBatches.begin());
            return OK;
        }
        break;
    }
    
    // 接收新消息
    while (true) {
        status_t result = mChannel->receiveMessage(&mMsg);
        
        if (result != OK) {
            if (result == WOULD_BLOCK) {
                // 没有更多消息
                if (!mBatches.empty() && consumeBatches) {
                    // 返回批处理的事件
                    Batch& batch = mBatches.front();
                    MotionEvent* motionEvent = factory->createMotionEvent();
                    initializeMotionEvent(motionEvent, batch.samples);
                    *outSeq = batch.samples.front().header.seq;
                    *outEvent = motionEvent;
                    mBatches.erase(mBatches.begin());
                    return OK;
                }
            }
            return result;
        }
        
        // 处理消息
        switch (mMsg.header.type) {
            case InputMessage::Type::KEY: {
                // 按键事件 - 直接返回
                KeyEvent* keyEvent = factory->createKeyEvent();
                initializeKeyEvent(keyEvent, &mMsg);
                *outSeq = mMsg.header.seq;
                *outEvent = keyEvent;
                return OK;
            }
            
            case InputMessage::Type::MOTION: {
                // 运动事件 - 可能需要批处理
                if (shouldBatch(&mMsg)) {
                    // 添加到批处理
                    addToBatch(&mMsg);
                } else {
                    // 直接返回
                    MotionEvent* motionEvent = factory->createMotionEvent();
                    initializeMotionEvent(motionEvent, mMsg);
                    *outSeq = mMsg.header.seq;
                    *outEvent = motionEvent;
                    return OK;
                }
                break;
            }
            
            case InputMessage::Type::FOCUS: {
                FocusEvent* focusEvent = factory->createFocusEvent();
                focusEvent->initialize(mMsg.body.focus.hasFocus);
                *outSeq = mMsg.header.seq;
                *outEvent = focusEvent;
                return OK;
            }
        }
    }
}
```

### 5.3 批处理机制

```cpp
// 是否应该批处理
bool InputConsumer::shouldBatch(const InputMessage* msg) {
    // 只有 MOVE 事件才批处理
    if (msg->body.motion.action != AMOTION_EVENT_ACTION_MOVE) {
        return false;
    }
    
    // 查找是否有相同 source 的批处理
    for (const Batch& batch : mBatches) {
        if (batch.samples[0].body.motion.source == msg->body.motion.source) {
            return true;
        }
    }
    
    return false;
}

// 添加到批处理
void InputConsumer::addToBatch(const InputMessage* msg) {
    // 查找或创建批处理
    for (Batch& batch : mBatches) {
        if (batch.samples[0].body.motion.source == msg->body.motion.source) {
            batch.samples.push_back(*msg);
            return;
        }
    }
    
    // 创建新批处理
    Batch batch;
    batch.samples.push_back(*msg);
    mBatches.push_back(std::move(batch));
}

// 合并批处理事件到 MotionEvent
void InputConsumer::initializeMotionEvent(MotionEvent* event,
                                          const std::vector<InputMessage>& batch) {
    const InputMessage& head = batch.front();
    
    // 初始化基本属性
    event->initialize(head.body.motion.eventId,
                      head.body.motion.deviceId,
                      head.body.motion.source,
                      head.body.motion.displayId,
                      head.body.motion.action,
                      // ...
                      );
    
    // 添加历史数据 (所有批处理的样本)
    for (size_t i = 0; i < batch.size() - 1; i++) {
        const InputMessage& sample = batch[i];
        
        event->addSample(sample.body.motion.eventTime,
                        sample.body.motion.pointers,
                        sample.body.motion.pointerCount);
    }
}
```

---

## 6. 完成信号

### 6.1 发送完成信号

```cpp
// 应用处理完事件后发送
status_t InputConsumer::sendFinishedSignal(uint32_t seq, bool handled) {
    InputMessage msg;
    
    msg.header.type = InputMessage::Type::FINISHED;
    msg.header.seq = seq;
    msg.body.finished.handled = handled;
    msg.body.finished.consumeTime = systemTime(SYSTEM_TIME_MONOTONIC);
    
    return mChannel->sendMessage(&msg);
}
```

### 6.2 接收完成信号

```cpp
// InputDispatcher 接收完成信号
status_t InputPublisher::receiveFinishedSignal(uint32_t* outSeq, 
                                                bool* outHandled,
                                                nsecs_t* outConsumeTime) {
    InputMessage msg;
    
    status_t result = mChannel->receiveMessage(&msg);
    if (result != OK) {
        return result;
    }
    
    if (msg.header.type != InputMessage::Type::FINISHED) {
        return UNKNOWN_ERROR;
    }
    
    *outSeq = msg.header.seq;
    *outHandled = msg.body.finished.handled;
    *outConsumeTime = msg.body.finished.consumeTime;
    
    return OK;
}
```

---

## 7. 应用层集成

### 7.1 WindowInputEventReceiver

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java

final class WindowInputEventReceiver extends InputEventReceiver {
    public WindowInputEventReceiver(InputChannel inputChannel, Looper looper) {
        super(inputChannel, looper);
    }
    
    @Override
    public void onInputEvent(InputEvent event) {
        // 接收到输入事件
        Trace.traceBegin(Trace.TRACE_TAG_VIEW, "processInputEvent");
        try {
            // 加入处理队列
            enqueueInputEvent(event, this, 0, true);
        } finally {
            Trace.traceEnd(Trace.TRACE_TAG_VIEW);
        }
    }
    
    @Override
    public void onFocusEvent(boolean hasFocus) {
        // 接收到焦点事件
        windowFocusChanged(hasFocus);
    }
}
```

### 7.2 InputEventReceiver (Native 层)

```cpp
// frameworks/base/core/jni/android_view_InputEventReceiver.cpp

class NativeInputEventReceiver : public LooperCallback {
public:
    NativeInputEventReceiver(JNIEnv* env, jobject receiverWeak,
                             const std::shared_ptr<InputChannel>& inputChannel,
                             const sp<MessageQueue>& messageQueue);
    
    status_t initialize();
    status_t finishInputEvent(uint32_t seq, bool handled);
    
    // Looper 回调
    virtual int handleEvent(int fd, int events, void* data);
    
private:
    jobject mReceiverWeakGlobal;
    std::shared_ptr<InputChannel> mInputChannel;
    sp<MessageQueue> mMessageQueue;
    InputConsumer mInputConsumer;
    
    status_t consumeEvents(JNIEnv* env, bool consumeBatches, 
                          nsecs_t frameTime, bool* outConsumedBatch);
};

int NativeInputEventReceiver::handleEvent(int fd, int events, void* data) {
    if (events & ALOOPER_EVENT_INPUT) {
        JNIEnv* env = AndroidRuntime::getJNIEnv();
        
        // 消费事件
        bool consumedBatch;
        status_t status = consumeEvents(env, false, -1, &consumedBatch);
    }
    return 1;  // 继续监听
}

status_t NativeInputEventReceiver::consumeEvents(JNIEnv* env, 
                                                  bool consumeBatches,
                                                  nsecs_t frameTime,
                                                  bool* outConsumedBatch) {
    InputEvent* inputEvent;
    uint32_t seq;
    
    while (true) {
        // 从 InputConsumer 获取事件
        status_t status = mInputConsumer.consume(&mInputEventFactory,
                                                  consumeBatches, frameTime,
                                                  &seq, &inputEvent);
        
        if (status != OK) {
            if (status == WOULD_BLOCK) {
                return OK;
            }
            return status;
        }
        
        // 回调 Java 层
        if (inputEvent->getType() == AINPUT_EVENT_TYPE_KEY) {
            KeyEvent* keyEvent = static_cast<KeyEvent*>(inputEvent);
            
            // 创建 Java KeyEvent
            jobject keyEventObj = android_view_KeyEvent_fromNative(env, keyEvent);
            
            // 调用 onInputEvent
            env->CallVoidMethod(mReceiverWeakGlobal, 
                               gInputEventReceiverClassInfo.onInputEvent,
                               keyEventObj);
        } else if (inputEvent->getType() == AINPUT_EVENT_TYPE_MOTION) {
            MotionEvent* motionEvent = static_cast<MotionEvent*>(inputEvent);
            
            jobject motionEventObj = android_view_MotionEvent_obtainAsCopy(
                env, motionEvent);
            
            env->CallVoidMethod(mReceiverWeakGlobal,
                               gInputEventReceiverClassInfo.onInputEvent,
                               motionEventObj);
        }
    }
}
```

---

## 8. 本章小结

InputChannel 是 Input 系统的关键通信机制：

| 组件 | 职责 |
|-----|------|
| InputChannel | Unix Domain Socket 封装 |
| InputPublisher | 事件发送 (Dispatcher 端) |
| InputConsumer | 事件接收 (应用端) |
| InputMessage | 消息格式定义 |

关键特性：
1. **低延迟**: Unix Domain Socket 直接通信
2. **批处理**: MOVE 事件批量处理减少回调次数
3. **双向通信**: 事件发送 + 完成信号返回
4. **序列号**: 用于匹配事件和响应

通信流程：
1. WMS 创建 InputChannel 对
2. Server channel 注册到 InputDispatcher
3. Client channel 传递给应用
4. Dispatcher 通过 InputPublisher 发送事件
5. 应用通过 InputConsumer 接收事件
6. 应用处理后发送 finish 信号

下一篇将介绍 InputManagerService 的实现。

---

## 参考资料

1. `frameworks/native/libs/input/InputTransport.cpp`
2. `frameworks/base/core/java/android/view/InputChannel.java`
3. `frameworks/base/core/jni/android_view_InputEventReceiver.cpp`
