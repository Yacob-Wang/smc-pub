# InputDispatcher 事件分发

## 引言

InputDispatcher 是 Native 层 Input 系统的核心分发组件，负责将 InputReader 处理后的事件分发到正确的目标窗口。本文将深入分析 InputDispatcher 的架构、分发策略和 ANR 检测机制。

---

## 1. InputDispatcher 架构概览

### 1.1 核心组件

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          InputDispatcher                                 │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                   InputDispatcherThread                             │ │
│  │                           │                                         │ │
│  │                           ▼                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────┐   │ │
│  │  │                   dispatchOnce()                             │   │ │
│  │  │  1. dispatchOnceInnerLocked()   ─ 分发逻辑                  │   │ │
│  │  │  2. runCommandsLockedInterruptible()  ─ 执行命令            │   │ │
│  │  │  3. mLooper->pollOnce(timeout)  ─ 等待                      │   │ │
│  │  └─────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                         事件队列                                    │ │
│  │  ┌─────────────────────────────────────────────────────────────┐   │ │
│  │  │ mInboundQueue: std::deque<std::shared_ptr<EventEntry>>     │   │ │
│  │  │ (来自 InputReader 的事件)                                    │   │ │
│  │  └─────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                        窗口连接管理                                  │ │
│  │  ┌─────────────────────────────────────────────────────────────┐   │ │
│  │  │ mConnectionsByToken: <IBinder, Connection>                   │   │ │
│  │  │                                                              │   │ │
│  │  │   Connection                                                 │   │ │
│  │  │   ├── inputChannel      (InputChannel)                      │   │ │
│  │  │   ├── outboundQueue     (待发送事件)                        │   │ │
│  │  │   ├── waitQueue         (等待响应事件)                      │   │ │
│  │  │   └── inputPublisher    (事件发布器)                        │   │ │
│  │  └─────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                         焦点管理                                    │ │
│  │  ┌─────────────────────────────────────────────────────────────┐   │ │
│  │  │ mFocusedWindowHandlesByDisplay: <displayId, windowHandle>  │   │ │
│  │  │ mFocusedApplicationHandlesByDisplay: <displayId, appHandle>│   │ │
│  │  │ mTouchStatesByDisplay: <displayId, TouchState>              │   │ │
│  │  └─────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 数据流

```
  InputReader
      │
      │ notifyKey() / notifyMotion()
      ▼
┌─────────────────┐
│  mInboundQueue  │  ←── 入站队列
└────────┬────────┘
         │ dispatchOnceInnerLocked()
         ▼
┌─────────────────┐
│ 查找目标窗口    │
│ - 焦点窗口      │
│ - 触摸窗口      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Connection      │
│ outboundQueue   │  ←── 出站队列
└────────┬────────┘
         │ InputPublisher::publish*()
         ▼
┌─────────────────┐
│  InputChannel   │  ←── Socket 发送
│    (Socket)     │
└────────┬────────┘
         │
         ▼
     应用进程
```

---

## 2. 核心数据结构

### 2.1 EventEntry

```cpp
// 事件条目基类
struct EventEntry {
    enum class Type {
        CONFIGURATION_CHANGED,
        DEVICE_RESET,
        FOCUS,
        KEY,
        MOTION,
        SENSOR,
        POINTER_CAPTURE_CHANGED,
        DRAG,
    };
    
    int32_t id;
    Type type;
    nsecs_t eventTime;
    uint32_t policyFlags;
    InjectionState* injectionState;
    
    bool dispatchInProgress;
};

// 按键事件
struct KeyEntry : EventEntry {
    int32_t deviceId;
    uint32_t source;
    int32_t displayId;
    int32_t action;         // AKEY_EVENT_ACTION_DOWN/UP
    int32_t flags;
    int32_t keyCode;
    int32_t scanCode;
    int32_t metaState;
    int32_t repeatCount;
    nsecs_t downTime;
    
    InterceptKeyResult interceptKeyResult;
    nsecs_t interceptKeyWakeupTime;
};

// 运动事件
struct MotionEntry : EventEntry {
    int32_t deviceId;
    uint32_t source;
    int32_t displayId;
    int32_t action;
    int32_t actionButton;
    int32_t flags;
    int32_t metaState;
    int32_t buttonState;
    MotionClassification classification;
    int32_t edgeFlags;
    float xPrecision;
    float yPrecision;
    float xCursorPosition;
    float yCursorPosition;
    nsecs_t downTime;
    uint32_t pointerCount;
    PointerProperties* pointerProperties;
    PointerCoords* pointerCoords;
};
```

### 2.2 Connection

```cpp
class Connection {
public:
    enum class Status {
        NORMAL,     // 正常
        BROKEN,     // 已断开
        ZOMBIE,     // 待清理
    };
    
    Status status;
    sp<InputChannel> inputChannel;
    sp<WindowInfoHandle> inputWindowHandle;
    bool monitor;                           // 是否是监控连接
    
    InputPublisher inputPublisher;          // 事件发布器
    
    // 出站队列 - 待发送的事件
    std::deque<DispatchEntry*> outboundQueue;
    
    // 等待队列 - 已发送等待响应的事件
    std::deque<DispatchEntry*> waitQueue;
    
    // 响应性状态
    bool inputPublisherBlocked;
    
    // 获取 Token
    sp<IBinder> getToken() const { return inputChannel->getToken(); }
};
```

### 2.3 DispatchEntry

```cpp
struct DispatchEntry {
    // 关联的事件
    std::shared_ptr<EventEntry> eventEntry;
    
    // 目标信息
    int32_t targetFlags;
    float xOffset;
    float yOffset;
    float globalScaleFactor;
    float windowXScale;
    float windowYScale;
    
    // 分发状态
    nsecs_t deliveryTime;       // 发送时间
    uint32_t seq;               // 序列号 (用于匹配响应)
    bool inProgress;
};
```

---

## 3. 事件接收

### 3.1 notifyKey

```cpp
void InputDispatcher::notifyKey(const NotifyKeyArgs* args) {
    // 验证参数
    if (!validateKeyEvent(args->action)) {
        return;
    }
    
    uint32_t policyFlags = args->policyFlags;
    
    // 策略拦截 (如系统按键: 电源键, 音量键)
    KeyEvent event;
    event.initialize(args->id, args->deviceId, args->source, ...);
    
    mPolicy->interceptKeyBeforeQueueing(&event, policyFlags);
    
    // 检查是否被策略拦截
    bool needWake;
    { // 临界区
        std::scoped_lock _l(mLock);
        
        // 创建 KeyEntry
        std::unique_ptr<KeyEntry> newEntry = 
            std::make_unique<KeyEntry>(args->id, args->eventTime, ...);
        
        // 加入入站队列
        needWake = enqueueInboundEventLocked(std::move(newEntry));
    }
    
    // 唤醒分发线程
    if (needWake) {
        mLooper->wake();
    }
}
```

### 3.2 notifyMotion

```cpp
void InputDispatcher::notifyMotion(const NotifyMotionArgs* args) {
    // 验证参数
    if (!validateMotionEvent(args->action, args->actionButton,
                             args->pointerCount, args->pointerProperties)) {
        return;
    }
    
    uint32_t policyFlags = args->policyFlags;
    
    // 策略拦截 (触摸事件通常不被策略拦截)
    bool needWake;
    { // 临界区
        std::scoped_lock _l(mLock);
        
        // 创建 MotionEntry
        std::unique_ptr<MotionEntry> newEntry = 
            std::make_unique<MotionEntry>(args->id, args->eventTime, ...);
        
        // 加入入站队列
        needWake = enqueueInboundEventLocked(std::move(newEntry));
    }
    
    if (needWake) {
        mLooper->wake();
    }
}
```

---

## 4. 事件分发

### 4.1 dispatchOnce 主循环

```cpp
void InputDispatcher::dispatchOnce() {
    nsecs_t nextWakeupTime = LONG_LONG_MAX;
    
    { // 临界区
        std::scoped_lock _l(mLock);
        
        // 检查是否需要处理策略
        mDispatcherIsAlive.notify_all();
        
        // 分发事件
        if (!haveCommandsLocked()) {
            dispatchOnceInnerLocked(&nextWakeupTime);
        }
        
        // 执行待处理命令
        if (runCommandsLockedInterruptible()) {
            nextWakeupTime = LONG_LONG_MIN;  // 立即重新分发
        }
        
        // ANR 检测
        processAnrsLocked();
    }
    
    // 等待下一次唤醒
    nsecs_t currentTime = now();
    int timeoutMillis = toMillisecondTimeoutDelay(currentTime, nextWakeupTime);
    mLooper->pollOnce(timeoutMillis);
}
```

### 4.2 dispatchOnceInnerLocked

```cpp
void InputDispatcher::dispatchOnceInnerLocked(nsecs_t* nextWakeupTime) {
    nsecs_t currentTime = now();
    
    // 检查是否有挂起的事件
    if (!mPendingEvent) {
        if (mInboundQueue.empty()) {
            // 没有事件
            return;
        }
        
        // 取出队首事件
        mPendingEvent = mInboundQueue.front();
        mInboundQueue.pop_front();
    }
    
    // 根据事件类型分发
    switch (mPendingEvent->type) {
        case EventEntry::Type::KEY: {
            std::shared_ptr<KeyEntry> keyEntry = 
                std::static_pointer_cast<KeyEntry>(mPendingEvent);
            
            // 分发按键事件
            bool done = dispatchKeyLocked(currentTime, keyEntry, 
                                          &dropReason, nextWakeupTime);
            if (done) {
                mPendingEvent = nullptr;
            }
            break;
        }
        
        case EventEntry::Type::MOTION: {
            std::shared_ptr<MotionEntry> motionEntry =
                std::static_pointer_cast<MotionEntry>(mPendingEvent);
            
            // 分发运动事件
            bool done = dispatchMotionLocked(currentTime, motionEntry,
                                             &dropReason, nextWakeupTime);
            if (done) {
                mPendingEvent = nullptr;
            }
            break;
        }
        
        // 其他事件类型...
    }
}
```

---

## 5. 按键事件分发

### 5.1 dispatchKeyLocked

```cpp
bool InputDispatcher::dispatchKeyLocked(nsecs_t currentTime,
                                         std::shared_ptr<KeyEntry> entry,
                                         DropReason* dropReason,
                                         nsecs_t* nextWakeupTime) {
    // 1. 策略拦截
    if (entry->interceptKeyResult == KeyEntry::INTERCEPT_KEY_RESULT_UNKNOWN) {
        // 调用策略判断是否拦截
        if (entry->policyFlags & POLICY_FLAG_PASS_TO_USER) {
            sp<IBinder> focusedWindowToken = 
                mFocusedWindowTokenByDisplay.find(displayId);
            
            CommandEntry* commandEntry = postCommandLocked(
                &InputDispatcher::doInterceptKeyBeforeDispatchingLockedInterruptible);
            commandEntry->keyEntry = entry;
            
            return false;  // 等待策略处理结果
        } else {
            entry->interceptKeyResult = KeyEntry::INTERCEPT_KEY_RESULT_CONTINUE;
        }
    }
    
    // 2. 检查策略拦截结果
    if (entry->interceptKeyResult == KeyEntry::INTERCEPT_KEY_RESULT_SKIP) {
        *dropReason = DropReason::POLICY;
        return true;
    }
    
    // 3. 查找焦点窗口
    std::vector<InputTarget> inputTargets;
    int32_t injectionResult = findFocusedWindowTargetsLocked(
            currentTime, entry, inputTargets, nextWakeupTime);
    
    if (injectionResult == INPUT_EVENT_INJECTION_PENDING) {
        return false;  // 等待焦点窗口
    }
    
    // 4. 分发到目标窗口
    dispatchEventLocked(currentTime, entry, inputTargets);
    return true;
}
```

### 5.2 查找焦点窗口

```cpp
int32_t InputDispatcher::findFocusedWindowTargetsLocked(
        nsecs_t currentTime,
        const EventEntry& entry,
        std::vector<InputTarget>& inputTargets,
        nsecs_t* nextWakeupTime) {
    
    int32_t displayId = entry.displayId;
    
    // 获取焦点窗口
    sp<WindowInfoHandle> focusedWindowHandle = 
        getFocusedWindowHandleLocked(displayId);
    
    // 获取焦点应用
    std::shared_ptr<InputApplicationHandle> focusedApplicationHandle =
        getValueByKey(mFocusedApplicationHandlesByDisplay, displayId);
    
    // 检查是否有焦点
    if (focusedWindowHandle == nullptr && focusedApplicationHandle == nullptr) {
        // 没有焦点目标
        ALOGI("Dropping event because there is no focused window or focused application.");
        return INPUT_EVENT_INJECTION_FAILED;
    }
    
    // 检查焦点窗口是否可以接收事件
    if (focusedWindowHandle != nullptr) {
        if (!checkWindowReadyForMoreInputLocked(currentTime, focusedWindowHandle)) {
            // 窗口不可用, 等待
            return INPUT_EVENT_INJECTION_PENDING;
        }
        
        // 添加目标
        InputTarget target;
        target.inputChannel = getInputChannelLocked(focusedWindowHandle->getToken());
        target.flags = InputTarget::FLAG_FOREGROUND;
        inputTargets.push_back(target);
        
        return INPUT_EVENT_INJECTION_SUCCEEDED;
    }
    
    // 有焦点应用但没有焦点窗口 - 可能触发 ANR
    if (focusedApplicationHandle != nullptr) {
        // 检查 ANR 超时
        if (currentTime >= mNoFocusedWindowTimeoutTime) {
            onAnrLocked(focusedApplicationHandle);
            return INPUT_EVENT_INJECTION_FAILED;
        }
        return INPUT_EVENT_INJECTION_PENDING;
    }
    
    return INPUT_EVENT_INJECTION_FAILED;
}
```

---

## 6. 触摸事件分发

### 6.1 dispatchMotionLocked

```cpp
bool InputDispatcher::dispatchMotionLocked(nsecs_t currentTime,
                                            std::shared_ptr<MotionEntry> entry,
                                            DropReason* dropReason,
                                            nsecs_t* nextWakeupTime) {
    // 1. 查找目标窗口
    std::vector<InputTarget> inputTargets;
    int32_t injectionResult;
    
    bool isPointerEvent = entry->source & AINPUT_SOURCE_CLASS_POINTER;
    
    if (isPointerEvent) {
        // 触摸/鼠标事件 - 根据坐标查找窗口
        injectionResult = findTouchedWindowTargetsLocked(
                currentTime, *entry, inputTargets, nextWakeupTime);
    } else {
        // 非指针事件 (如轨迹球) - 发送到焦点窗口
        injectionResult = findFocusedWindowTargetsLocked(
                currentTime, *entry, inputTargets, nextWakeupTime);
    }
    
    if (injectionResult == INPUT_EVENT_INJECTION_PENDING) {
        return false;
    }
    
    // 2. 分发到目标窗口
    dispatchEventLocked(currentTime, entry, inputTargets);
    return true;
}
```

### 6.2 查找触摸窗口

```cpp
int32_t InputDispatcher::findTouchedWindowTargetsLocked(
        nsecs_t currentTime,
        const MotionEntry& entry,
        std::vector<InputTarget>& inputTargets,
        nsecs_t* nextWakeupTime) {
    
    int32_t displayId = entry.displayId;
    int32_t action = entry.action;
    int32_t maskedAction = action & AMOTION_EVENT_ACTION_MASK;
    
    // 获取或创建该显示器的触摸状态
    TouchState& state = mTouchStatesByDisplay[displayId];
    
    // DOWN 事件 - 查找命中的窗口
    if (maskedAction == AMOTION_EVENT_ACTION_DOWN ||
        maskedAction == AMOTION_EVENT_ACTION_HOVER_ENTER) {
        
        // 获取触摸坐标
        int32_t x = entry.pointerCoords[0].getX();
        int32_t y = entry.pointerCoords[0].getY();
        
        // 遍历窗口栈, 查找命中的窗口
        sp<WindowInfoHandle> newTouchedWindowHandle = 
            findTouchedWindowAtLocked(displayId, x, y);
        
        if (newTouchedWindowHandle != nullptr) {
            // 检查窗口是否可以接收输入
            const WindowInfo& info = *newTouchedWindowHandle->getInfo();
            
            if (info.inputFeatures.test(WindowInfo::Feature::DROP_INPUT)) {
                // 窗口不接收输入
                return INPUT_EVENT_INJECTION_FAILED;
            }
            
            // 检查是否被遮挡
            if (!checkWindowCanReceiveInputLocked(newTouchedWindowHandle, entry)) {
                return INPUT_EVENT_INJECTION_FAILED;
            }
            
            // 添加到触摸状态
            state.addTouchedWindow(newTouchedWindowHandle, 
                                   InputTarget::FLAG_FOREGROUND);
        }
    }
    
    // 构建输入目标
    for (const TouchedWindow& touchedWindow : state.windows) {
        InputTarget target;
        target.inputChannel = getInputChannelLocked(
            touchedWindow.windowHandle->getToken());
        target.flags = touchedWindow.targetFlags;
        target.pointerIds = touchedWindow.pointerIds;
        
        // 计算坐标偏移
        const WindowInfo& info = *touchedWindow.windowHandle->getInfo();
        target.xOffset = -info.frameLeft;
        target.yOffset = -info.frameTop;
        
        inputTargets.push_back(target);
    }
    
    return INPUT_EVENT_INJECTION_SUCCEEDED;
}
```

### 6.3 窗口命中测试

```cpp
sp<WindowInfoHandle> InputDispatcher::findTouchedWindowAtLocked(
        int32_t displayId, int32_t x, int32_t y) {
    
    // 获取该显示器的所有窗口
    const std::vector<sp<WindowInfoHandle>>& windowHandles = 
        getWindowHandlesLocked(displayId);
    
    // 从上到下遍历窗口 (Z-order 从高到低)
    for (const sp<WindowInfoHandle>& windowHandle : windowHandles) {
        const WindowInfo& info = *windowHandle->getInfo();
        
        // 检查窗口是否可见
        if (!info.visible) {
            continue;
        }
        
        // 检查窗口是否可以接收触摸
        if (!info.isTouchableRegionAllowed(x, y)) {
            continue;
        }
        
        // 检查坐标是否在窗口区域内
        if (!info.frameContainsPoint(x, y)) {
            continue;
        }
        
        // 检查是否在可触摸区域内
        if (info.touchableRegion.contains(x, y)) {
            return windowHandle;
        }
    }
    
    return nullptr;
}
```

---

## 7. 事件发送

### 7.1 dispatchEventLocked

```cpp
void InputDispatcher::dispatchEventLocked(nsecs_t currentTime,
                                           std::shared_ptr<EventEntry> eventEntry,
                                           const std::vector<InputTarget>& inputTargets) {
    // 遍历所有目标
    for (const InputTarget& inputTarget : inputTargets) {
        sp<Connection> connection = getConnectionLocked(inputTarget.inputChannel);
        
        if (connection != nullptr) {
            prepareDispatchCycleLocked(currentTime, connection, 
                                       eventEntry, inputTarget);
        }
    }
}

void InputDispatcher::prepareDispatchCycleLocked(
        nsecs_t currentTime,
        const sp<Connection>& connection,
        std::shared_ptr<EventEntry> eventEntry,
        const InputTarget& inputTarget) {
    
    // 创建 DispatchEntry
    std::unique_ptr<DispatchEntry> dispatchEntry =
        std::make_unique<DispatchEntry>(eventEntry, inputTarget.flags,
                                        inputTarget.xOffset, inputTarget.yOffset,
                                        inputTarget.globalScaleFactor,
                                        inputTarget.windowXScale,
                                        inputTarget.windowYScale);
    
    // 添加到出站队列
    connection->outboundQueue.push_back(dispatchEntry.release());
    
    // 开始分发周期
    startDispatchCycleLocked(currentTime, connection);
}
```

### 7.2 startDispatchCycleLocked

```cpp
void InputDispatcher::startDispatchCycleLocked(nsecs_t currentTime,
                                                const sp<Connection>& connection) {
    // 循环发送出站队列中的事件
    while (!connection->outboundQueue.empty()) {
        DispatchEntry* dispatchEntry = connection->outboundQueue.front();
        
        // 尝试发送
        status_t status;
        const EventEntry& eventEntry = *dispatchEntry->eventEntry;
        
        switch (eventEntry.type) {
            case EventEntry::Type::KEY: {
                const KeyEntry& keyEntry = static_cast<const KeyEntry&>(eventEntry);
                
                // 通过 InputPublisher 发送
                status = connection->inputPublisher.publishKeyEvent(
                        dispatchEntry->seq,
                        keyEntry.id,
                        keyEntry.deviceId,
                        keyEntry.source,
                        keyEntry.displayId,
                        keyEntry.action,
                        keyEntry.flags,
                        keyEntry.keyCode,
                        keyEntry.scanCode,
                        keyEntry.metaState,
                        keyEntry.repeatCount,
                        keyEntry.downTime,
                        keyEntry.eventTime);
                break;
            }
            
            case EventEntry::Type::MOTION: {
                const MotionEntry& motionEntry = 
                    static_cast<const MotionEntry&>(eventEntry);
                
                // 应用坐标偏移
                PointerCoords scaledCoords[motionEntry.pointerCount];
                for (uint32_t i = 0; i < motionEntry.pointerCount; i++) {
                    scaledCoords[i] = motionEntry.pointerCoords[i];
                    scaledCoords[i].setAxisValue(AMOTION_EVENT_AXIS_X,
                            scaledCoords[i].getX() + dispatchEntry->xOffset);
                    scaledCoords[i].setAxisValue(AMOTION_EVENT_AXIS_Y,
                            scaledCoords[i].getY() + dispatchEntry->yOffset);
                }
                
                status = connection->inputPublisher.publishMotionEvent(
                        dispatchEntry->seq,
                        motionEntry.id,
                        // ... 其他参数
                        scaledCoords);
                break;
            }
        }
        
        // 检查发送结果
        if (status == WOULD_BLOCK) {
            // Socket 缓冲区满, 稍后重试
            connection->inputPublisherBlocked = true;
            return;
        }
        
        if (status != OK) {
            // 发送失败
            ALOGE("Failed to publish event: %s", strerror(-status));
            abortBrokenDispatchCycleLocked(currentTime, connection, true);
            return;
        }
        
        // 移动到等待队列
        dispatchEntry->deliveryTime = currentTime;
        connection->outboundQueue.pop_front();
        connection->waitQueue.push_back(dispatchEntry);
    }
}
```

---

## 8. 事件响应处理

### 8.1 接收完成回调

```cpp
// 当应用处理完事件后, 会发送 finish 信号
void InputDispatcher::handleReceiveCallback(int fd, int events, void* data) {
    sp<Connection> connection = static_cast<Connection*>(data);
    
    if (events & ALOOPER_EVENT_INPUT) {
        // 读取完成信号
        uint32_t seq;
        bool handled;
        nsecs_t consumeTime;
        
        status_t status = connection->inputPublisher.receiveFinishedSignal(
                &seq, &handled, &consumeTime);
        
        if (status == OK) {
            finishDispatchCycleLocked(systemTime(), connection, seq, handled);
        }
    }
}

void InputDispatcher::finishDispatchCycleLocked(nsecs_t currentTime,
                                                 const sp<Connection>& connection,
                                                 uint32_t seq,
                                                 bool handled) {
    // 在等待队列中查找对应的事件
    for (auto it = connection->waitQueue.begin(); 
         it != connection->waitQueue.end(); ++it) {
        DispatchEntry* dispatchEntry = *it;
        
        if (dispatchEntry->seq == seq) {
            // 找到, 移除
            connection->waitQueue.erase(it);
            
            // 计算响应时间
            nsecs_t responseTime = currentTime - dispatchEntry->deliveryTime;
            
            // 清理
            delete dispatchEntry;
            
            // 继续发送队列中的其他事件
            startDispatchCycleLocked(currentTime, connection);
            return;
        }
    }
}
```

---

## 9. 本章小结

InputDispatcher 是事件分发的核心组件：

| 功能 | 实现 |
|-----|------|
| 事件队列 | mInboundQueue 接收事件 |
| 目标查找 | findFocusedWindowTargetsLocked / findTouchedWindowTargetsLocked |
| 事件发送 | InputPublisher 通过 Socket 发送 |
| 响应处理 | receiveFinishedSignal 处理完成回调 |
| ANR 检测 | 监控 waitQueue 超时 |

关键流程：
1. InputReader 调用 notifyKey/notifyMotion
2. 事件加入 mInboundQueue
3. dispatchOnce 取出事件并分发
4. 查找目标窗口 (焦点或触摸命中)
5. 通过 InputChannel 发送到应用
6. 等待应用返回 finish 信号

下一篇将详细介绍 InputChannel 通信机制。

---

## 参考资料

1. `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`
2. `frameworks/native/services/inputflinger/dispatcher/Entry.h`
3. Android Input Dispatcher 源码分析
