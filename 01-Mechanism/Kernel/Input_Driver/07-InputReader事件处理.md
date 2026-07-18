# InputReader 事件处理

## 引言

InputReader 是 Native 层 Input 系统的核心处理组件，负责将 EventHub 读取的原始事件转换为 Android 标准输入事件。本文将深入分析 InputReader 的架构和事件处理机制。

---

## 1. InputReader 架构概览

### 1.1 核心组件关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           InputReader                                    │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                      InputReaderThread                              │ │
│  │                           │                                         │ │
│  │                           ▼                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────┐   │ │
│  │  │                     loopOnce()                               │   │ │
│  │  │  1. EventHub->getEvents()                                   │   │ │
│  │  │  2. processEventsLocked()                                   │   │ │
│  │  │  3. mQueuedListener->flush()                                │   │ │
│  │  └─────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                      InputDevice 管理                               │ │
│  │  ┌─────────────────────────────────────────────────────────────┐   │ │
│  │  │ mDevices: std::unordered_map<int32_t, InputDevice*>        │   │ │
│  │  │                                                              │   │ │
│  │  │   InputDevice                                                │   │ │
│  │  │   ├── KeyboardInputMapper    (按键处理)                     │   │ │
│  │  │   ├── TouchInputMapper       (触摸处理)                     │   │ │
│  │  │   ├── CursorInputMapper      (光标处理)                     │   │ │
│  │  │   ├── SwitchInputMapper      (开关处理)                     │   │ │
│  │  │   └── JoystickInputMapper    (游戏手柄处理)                 │   │ │
│  │  └─────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    QueuedInputListener                              │ │
│  │  └── 缓存 NotifyArgs, 调用 flush() 时传递给 InputDispatcher       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ NotifyArgs
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           InputDispatcher                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 InputMapper 继承体系

```
                          InputMapper
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
KeyboardInputMapper    CursorInputMapper    TouchInputMapper
        │                      │                      │
        ▼                      ▼                      ▼
   处理按键事件            处理鼠标事件        处理触摸事件
                                                      │
                                    ┌─────────────────┼─────────────────┐
                                    │                 │                 │
                                    ▼                 ▼                 ▼
                         SingleTouchMapper   MultiTouchMapper   ExternalStylusMapper
```

---

## 2. 核心数据结构

### 2.1 InputReader 类

```cpp
// frameworks/native/services/inputflinger/reader/InputReader.h

class InputReader : public InputReaderInterface {
public:
    InputReader(std::shared_ptr<EventHubInterface> eventHub,
                const sp<InputReaderPolicyInterface>& policy,
                InputListenerInterface& listener);
    
    virtual ~InputReader();
    
    // 主循环
    void loopOnce();
    
    // 设备管理
    void getInputDevices(std::vector<InputDeviceInfo>& outInputDevices);
    
    // 配置变更
    void requestRefreshConfiguration(uint32_t changes);
    
private:
    // 组件
    std::shared_ptr<EventHubInterface> mEventHub;
    sp<InputReaderPolicyInterface> mPolicy;
    QueuedInputListener mQueuedListener;
    
    // 设备列表
    std::unordered_map<int32_t, std::shared_ptr<InputDevice>> mDevices;
    
    // 事件缓冲区
    RawEvent mEventBuffer[EVENT_BUFFER_SIZE];
    
    // 上下文
    InputReaderContext mContext;
    
    // 处理函数
    void processEventsLocked(const RawEvent* rawEvents, size_t count);
    void addDeviceLocked(nsecs_t when, int32_t deviceId);
    void removeDeviceLocked(nsecs_t when, int32_t deviceId);
    void processEventsForDeviceLocked(int32_t deviceId,
                                       const RawEvent* rawEvents, size_t count);
};
```

### 2.2 InputDevice 类

```cpp
class InputDevice {
public:
    InputDevice(InputReaderContext* context, int32_t id, int32_t generation,
                const InputDeviceIdentifier& identifier);
    
    // 处理事件
    void process(const RawEvent* rawEvents, size_t count);
    
    // 配置
    void configure(nsecs_t when, const InputReaderConfiguration* config,
                   uint32_t changes);
    
    // 重置
    void reset(nsecs_t when);
    
    // 获取信息
    void getDeviceInfo(InputDeviceInfo* outDeviceInfo);
    
    inline int32_t getId() const { return mId; }
    inline const std::string& getName() const { return mIdentifier.name; }
    inline uint32_t getClasses() const { return mClasses; }
    inline uint32_t getSources() const { return mSources; }
    
private:
    InputReaderContext* mContext;
    int32_t mId;
    int32_t mGeneration;
    InputDeviceIdentifier mIdentifier;
    
    uint32_t mClasses;      // INPUT_DEVICE_CLASS_*
    uint32_t mSources;      // AINPUT_SOURCE_*
    
    // 该设备的所有 Mapper
    std::vector<std::unique_ptr<InputMapper>> mMappers;
    
    // 添加 Mapper
    void addMapper(std::unique_ptr<InputMapper> mapper);
};
```

### 2.3 InputMapper 基类

```cpp
class InputMapper {
public:
    explicit InputMapper(InputDeviceContext& deviceContext);
    virtual ~InputMapper();
    
    // 获取输入源
    virtual uint32_t getSources() = 0;
    
    // 配置
    virtual void configure(nsecs_t when, const InputReaderConfiguration* config,
                          uint32_t changes);
    
    // 重置
    virtual void reset(nsecs_t when);
    
    // 处理原始事件
    virtual void process(const RawEvent* rawEvent) = 0;
    
protected:
    InputDeviceContext& mDeviceContext;
    
    // 上报事件
    void notifyKey(nsecs_t eventTime, int32_t action, int32_t keyCode,
                   int32_t scanCode, int32_t metaState, nsecs_t downTime);
    void notifyMotion(nsecs_t eventTime, int32_t action, int32_t metaState,
                      uint32_t buttonState, MotionClassification classification,
                      const PointerProperties* properties,
                      const PointerCoords* coords, uint32_t pointerCount,
                      nsecs_t downTime);
};
```

---

## 3. 主循环与事件处理

### 3.1 loopOnce 实现

```cpp
void InputReader::loopOnce() {
    int32_t oldGeneration;
    int32_t timeoutMillis;
    bool inputDevicesChanged = false;
    std::vector<InputDeviceInfo> inputDevices;
    
    { // 临界区
        std::scoped_lock _l(mLock);
        
        oldGeneration = mGeneration;
        timeoutMillis = -1;  // 无限等待
        
        // 处理配置变更请求
        uint32_t changes = mConfigurationChangesToRefresh;
        if (changes) {
            mConfigurationChangesToRefresh = 0;
            timeoutMillis = 0;  // 立即返回
            refreshConfigurationLocked(changes);
        }
    }
    
    // 从 EventHub 获取事件 (可能阻塞)
    size_t count = mEventHub->getEvents(timeoutMillis, 
                                        mEventBuffer, EVENT_BUFFER_SIZE);
    
    { // 临界区
        std::scoped_lock _l(mLock);
        
        // 处理事件
        if (count) {
            processEventsLocked(mEventBuffer, count);
        }
        
        // 检查设备变更
        if (oldGeneration != mGeneration) {
            inputDevicesChanged = true;
            getInputDevicesLocked(inputDevices);
        }
    }
    
    // 通知设备变更
    if (inputDevicesChanged) {
        mPolicy->notifyInputDevicesChanged(inputDevices);
    }
    
    // 刷新事件到 Dispatcher
    mQueuedListener.flush();
}
```

### 3.2 processEventsLocked 实现

```cpp
void InputReader::processEventsLocked(const RawEvent* rawEvents, size_t count) {
    for (const RawEvent* rawEvent = rawEvents; count--; rawEvent++) {
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
                // 普通输入事件, 分发给对应设备
                processEventsForDeviceLocked(rawEvent->deviceId, rawEvent, 1);
                break;
        }
    }
}

void InputReader::processEventsForDeviceLocked(int32_t deviceId,
                                                const RawEvent* rawEvents,
                                                size_t count) {
    // 查找设备
    auto deviceIt = mDevices.find(deviceId);
    if (deviceIt == mDevices.end()) {
        ALOGW("Discarding event for unknown device %d", deviceId);
        return;
    }
    
    // 交给设备处理
    std::shared_ptr<InputDevice>& device = deviceIt->second;
    device->process(rawEvents, count);
}
```

### 3.3 InputDevice 事件处理

```cpp
void InputDevice::process(const RawEvent* rawEvents, size_t count) {
    // 将事件分发给所有 Mapper
    for (const RawEvent* rawEvent = rawEvents; count--; rawEvent++) {
        for (std::unique_ptr<InputMapper>& mapper : mMappers) {
            mapper->process(rawEvent);
        }
    }
}
```

---

## 4. KeyboardInputMapper

### 4.1 按键处理流程

```cpp
// frameworks/native/services/inputflinger/reader/mapper/KeyboardInputMapper.cpp

uint32_t KeyboardInputMapper::getSources() {
    return mSource;  // AINPUT_SOURCE_KEYBOARD 或 AINPUT_SOURCE_DPAD
}

void KeyboardInputMapper::process(const RawEvent* rawEvent) {
    switch (rawEvent->type) {
        case EV_KEY:
            processKey(rawEvent->when, rawEvent->code, rawEvent->value);
            break;
    }
}

void KeyboardInputMapper::processKey(nsecs_t when, int32_t scanCode, int32_t value) {
    // 1. 扫描码转换为 keyCode
    int32_t keyCode;
    int32_t keyMetaState;
    uint32_t policyFlags;
    
    if (!mDeviceContext.mapKey(scanCode, /*usageCode=*/0, mMetaState,
                               &keyCode, &keyMetaState, &policyFlags)) {
        // 未知扫描码
        return;
    }
    
    // 2. 确定 action
    int32_t action;
    if (value == 1) {
        action = AKEY_EVENT_ACTION_DOWN;
    } else if (value == 0) {
        action = AKEY_EVENT_ACTION_UP;
    } else if (value == 2) {
        // 重复按键
        action = AKEY_EVENT_ACTION_DOWN;
        // repeatCount 会在 Java 层处理
    } else {
        return;
    }
    
    // 3. 更新修饰键状态 (Alt, Shift, Ctrl...)
    if (action == AKEY_EVENT_ACTION_DOWN) {
        // 记录按下时间
        if (mDownTime == 0) {
            mDownTime = when;
        }
    } else {
        // 重置按下时间
        mDownTime = 0;
    }
    
    // 4. 更新元状态
    int32_t newMetaState = mMetaState;
    if (action == AKEY_EVENT_ACTION_DOWN) {
        newMetaState = updateMetaState(keyCode, true, newMetaState);
    } else {
        newMetaState = updateMetaState(keyCode, false, newMetaState);
    }
    
    if (newMetaState != mMetaState) {
        mMetaState = newMetaState;
        // 通知元状态变更
        updateLedState(false);
    }
    
    // 5. 生成事件
    NotifyKeyArgs args(mContext.getNextId(), when, 
                       mDeviceContext.getId(), mSource,
                       mDeviceContext.getDisplayId(), policyFlags,
                       action, /*flags=*/0, keyCode, scanCode,
                       mMetaState, when);
    
    // 6. 通知监听器
    getListener().notifyKey(&args);
}
```

### 4.2 扫描码到 keyCode 映射

```cpp
// 键盘映射查找
status_t InputDevice::mapKey(int32_t scanCode, int32_t usageCode,
                             int32_t metaState,
                             int32_t* outKeyCode, int32_t* outMetaState,
                             uint32_t* outFlags) const {
    // 优先使用 Key Layout 文件 (.kl)
    if (mKeyMap.keyLayoutMap) {
        status_t status = mKeyMap.keyLayoutMap->mapKey(scanCode, usageCode,
                                                        outKeyCode, outFlags);
        if (status == NO_ERROR) {
            // 处理 Key Character Map (.kcm)
            if (mKeyMap.keyCharacterMap) {
                *outMetaState = mKeyMap.keyCharacterMap->getMetaState(
                    metaState, *outKeyCode);
            }
            return NO_ERROR;
        }
    }
    
    // 使用默认映射
    *outKeyCode = 0;
    *outMetaState = metaState;
    *outFlags = 0;
    return NAME_NOT_FOUND;
}
```

---

## 5. TouchInputMapper

### 5.1 MultiTouchInputMapper

```cpp
// frameworks/native/services/inputflinger/reader/mapper/TouchInputMapper.cpp

void MultiTouchInputMapper::process(const RawEvent* rawEvent) {
    // 累积触摸数据
    TouchInputMapper::process(rawEvent);
    
    switch (rawEvent->type) {
        case EV_ABS:
            switch (rawEvent->code) {
                case ABS_MT_SLOT:
                    mMultiTouchMotionAccumulator.setCurrentSlot(rawEvent->value);
                    break;
                case ABS_MT_POSITION_X:
                    mMultiTouchMotionAccumulator.getCurrentSlot()->setX(rawEvent->value);
                    break;
                case ABS_MT_POSITION_Y:
                    mMultiTouchMotionAccumulator.getCurrentSlot()->setY(rawEvent->value);
                    break;
                case ABS_MT_TOUCH_MAJOR:
                    mMultiTouchMotionAccumulator.getCurrentSlot()->setTouchMajor(
                        rawEvent->value);
                    break;
                case ABS_MT_TOUCH_MINOR:
                    mMultiTouchMotionAccumulator.getCurrentSlot()->setTouchMinor(
                        rawEvent->value);
                    break;
                case ABS_MT_PRESSURE:
                    mMultiTouchMotionAccumulator.getCurrentSlot()->setPressure(
                        rawEvent->value);
                    break;
                case ABS_MT_TRACKING_ID:
                    mMultiTouchMotionAccumulator.getCurrentSlot()->setTrackingId(
                        rawEvent->value);
                    break;
            }
            break;
            
        case EV_SYN:
            if (rawEvent->code == SYN_REPORT) {
                // 同步事件 - 处理累积的触摸数据
                sync(rawEvent->when);
            }
            break;
    }
}
```

### 5.2 触摸数据同步与合成

```cpp
void TouchInputMapper::sync(nsecs_t when) {
    // 1. 收集当前帧的触摸点
    std::vector<RawPointerData::Pointer> currentPointers;
    mMultiTouchMotionAccumulator.getPointers(&currentPointers);
    
    // 2. 计算变化
    std::vector<uint32_t> downPointers;
    std::vector<uint32_t> upPointers;
    std::vector<uint32_t> movePointers;
    
    calculatePointerChanges(&downPointers, &upPointers, &movePointers);
    
    // 3. 坐标转换
    for (auto& pointer : currentPointers) {
        // 设备坐标 -> 显示坐标
        float displayX, displayY;
        rotateAndScale(pointer.x, pointer.y, &displayX, &displayY);
        
        // 应用校准
        applyCalibration(&pointer);
    }
    
    // 4. 生成 MotionEvent
    if (!downPointers.empty()) {
        // 新触摸点按下
        int32_t action = currentPointerCount == 1 
            ? AMOTION_EVENT_ACTION_DOWN 
            : AMOTION_EVENT_ACTION_POINTER_DOWN | 
              (downPointerIndex << AMOTION_EVENT_ACTION_POINTER_INDEX_SHIFT);
        
        dispatchMotion(when, action, ...);
    }
    
    if (!movePointers.empty()) {
        // 触摸点移动
        dispatchMotion(when, AMOTION_EVENT_ACTION_MOVE, ...);
    }
    
    if (!upPointers.empty()) {
        // 触摸点抬起
        int32_t action = currentPointerCount == 0
            ? AMOTION_EVENT_ACTION_UP
            : AMOTION_EVENT_ACTION_POINTER_UP |
              (upPointerIndex << AMOTION_EVENT_ACTION_POINTER_INDEX_SHIFT);
        
        dispatchMotion(when, action, ...);
    }
    
    // 5. 更新状态
    mLastRawPointerData = mCurrentRawPointerData;
}
```

### 5.3 坐标转换

```cpp
void TouchInputMapper::rotateAndScale(float x, float y, 
                                      float* outX, float* outY) const {
    // 获取设备尺寸
    int32_t rawWidth = mRawAxes.x.maxValue - mRawAxes.x.minValue + 1;
    int32_t rawHeight = mRawAxes.y.maxValue - mRawAxes.y.minValue + 1;
    
    // 归一化
    float normalizedX = (x - mRawAxes.x.minValue) / rawWidth;
    float normalizedY = (y - mRawAxes.y.minValue) / rawHeight;
    
    // 根据显示方向旋转
    float rotatedX, rotatedY;
    switch (mDisplayOrientation) {
        case DISPLAY_ORIENTATION_90:
            rotatedX = normalizedY;
            rotatedY = 1.0f - normalizedX;
            break;
        case DISPLAY_ORIENTATION_180:
            rotatedX = 1.0f - normalizedX;
            rotatedY = 1.0f - normalizedY;
            break;
        case DISPLAY_ORIENTATION_270:
            rotatedX = 1.0f - normalizedY;
            rotatedY = normalizedX;
            break;
        default: // DISPLAY_ORIENTATION_0
            rotatedX = normalizedX;
            rotatedY = normalizedY;
            break;
    }
    
    // 缩放到显示尺寸
    *outX = rotatedX * mDisplayWidth;
    *outY = rotatedY * mDisplayHeight;
}
```

---

## 6. 事件通知机制

### 6.1 QueuedInputListener

```cpp
class QueuedInputListener : public InputListenerInterface {
public:
    explicit QueuedInputListener(InputListenerInterface& innerListener);
    
    // 缓存通知
    virtual void notifyConfigurationChanged(const NotifyConfigurationChangedArgs* args);
    virtual void notifyKey(const NotifyKeyArgs* args);
    virtual void notifyMotion(const NotifyMotionArgs* args);
    virtual void notifySwitch(const NotifySwitchArgs* args);
    virtual void notifyDeviceReset(const NotifyDeviceResetArgs* args);
    
    // 刷新到内部监听器
    void flush();
    
private:
    InputListenerInterface& mInnerListener;
    std::vector<std::unique_ptr<NotifyArgs>> mArgsQueue;
};

// 刷新实现
void QueuedInputListener::flush() {
    for (const std::unique_ptr<NotifyArgs>& args : mArgsQueue) {
        args->notify(mInnerListener);
    }
    mArgsQueue.clear();
}
```

### 6.2 NotifyArgs 类型

```cpp
// 按键事件通知
struct NotifyKeyArgs : public NotifyArgs {
    int32_t deviceId;
    uint32_t source;
    int32_t displayId;
    uint32_t policyFlags;
    int32_t action;
    int32_t flags;
    int32_t keyCode;
    int32_t scanCode;
    int32_t metaState;
    nsecs_t downTime;
    
    void notify(InputListenerInterface& listener) const override {
        listener.notifyKey(this);
    }
};

// 运动事件通知
struct NotifyMotionArgs : public NotifyArgs {
    int32_t deviceId;
    uint32_t source;
    int32_t displayId;
    uint32_t policyFlags;
    int32_t action;
    int32_t actionButton;
    int32_t flags;
    int32_t metaState;
    int32_t buttonState;
    MotionClassification classification;
    int32_t edgeFlags;
    uint32_t pointerCount;
    PointerProperties pointerProperties[MAX_POINTERS];
    PointerCoords pointerCoords[MAX_POINTERS];
    float xPrecision;
    float yPrecision;
    float xCursorPosition;
    float yCursorPosition;
    nsecs_t downTime;
    
    void notify(InputListenerInterface& listener) const override {
        listener.notifyMotion(this);
    }
};
```

---

## 7. 配置与策略

### 7.1 InputReaderPolicy

```cpp
class InputReaderPolicyInterface {
public:
    virtual ~InputReaderPolicyInterface() {}
    
    // 获取阅读器配置
    virtual void getReaderConfiguration(InputReaderConfiguration* outConfig) = 0;
    
    // 通知设备变更
    virtual void notifyInputDevicesChanged(
        const std::vector<InputDeviceInfo>& inputDevices) = 0;
    
    // 获取键盘布局
    virtual std::shared_ptr<KeyCharacterMap> getKeyboardLayoutOverlay(
        const InputDeviceIdentifier& identifier) = 0;
    
    // 获取设备别名
    virtual std::string getDeviceAlias(const InputDeviceIdentifier& identifier) = 0;
};
```

### 7.2 InputReaderConfiguration

```cpp
struct InputReaderConfiguration {
    // 触摸设备配置
    int32_t pointerGestureZoomSpeedRatio;
    int32_t pointerGestureSwipeMaxWidthRatio;
    float pointerGestureMovementSpeedRatio;
    
    // 键盘配置
    int32_t defaultPointerSpeed;
    bool showTouches;
    
    // 显示配置
    bool setDisplayViewports(const std::vector<DisplayViewport>& viewports);
    std::optional<DisplayViewport> getDisplayViewportByType(ViewportType type) const;
    std::optional<DisplayViewport> getDisplayViewportByUniqueId(
        const std::string& uniqueId) const;
    
    // 禁用的设备
    std::vector<std::string> excludedDeviceNames;
    
    // 关联的显示
    std::vector<InputDeviceAssociation> deviceAssociations;
};
```

---

## 8. 本章小结

InputReader 是 Input 系统的核心处理组件：

| 组件 | 职责 |
|-----|------|
| InputReaderThread | 主循环，协调事件读取和处理 |
| InputDevice | 设备抽象，管理该设备的所有 Mapper |
| InputMapper | 事件处理器，转换原始事件 |
| QueuedInputListener | 事件缓存，批量发送到 Dispatcher |

关键流程：
1. loopOnce() 从 EventHub 获取原始事件
2. 分发事件到对应 InputDevice
3. InputDevice 分发给所有 InputMapper
4. Mapper 处理并生成 NotifyArgs
5. flush() 刷新事件到 InputDispatcher

下一篇将介绍 InputDispatcher 的事件分发机制。

---

## 参考资料

1. `frameworks/native/services/inputflinger/reader/InputReader.cpp`
2. `frameworks/native/services/inputflinger/reader/mapper/`
3. Android Input Reader 源码分析
