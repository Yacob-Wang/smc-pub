# EventHub 与设备管理

## 引言

EventHub 是 Android Native 层 Input 系统的入口，负责与 Kernel 层交互，管理输入设备并读取原始事件。本文将深入分析 EventHub 的实现机制。

---

## 1. EventHub 架构概览

### 1.1 在 Input 系统中的位置

```
┌─────────────────────────────────────────────────────────────────────┐
│                        InputFlinger                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      InputManager                            │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │   │
│  │  │ InputReader │  │InputClassifier│  │InputDispatcher│       │   │
│  │  │   Thread    │  │   (可选)    │  │   Thread    │         │   │
│  │  └──────┬──────┘  └─────────────┘  └─────────────┘         │   │
│  │         │                                                    │   │
│  │         │ getEvents()                                       │   │
│  │         ▼                                                    │   │
│  │  ┌─────────────────────────────────────────────────────┐    │   │
│  │  │                    EventHub                          │    │   │
│  │  │  ┌─────────────────────────────────────────────────┐│    │   │
│  │  │  │  设备管理                                        ││    │   │
│  │  │  │  - 设备发现 (inotify)                           ││    │   │
│  │  │  │  - 设备打开 (open /dev/input/eventX)           ││    │   │
│  │  │  │  - 设备能力读取 (ioctl)                         ││    │   │
│  │  │  └─────────────────────────────────────────────────┘│    │   │
│  │  │  ┌─────────────────────────────────────────────────┐│    │   │
│  │  │  │  事件读取                                        ││    │   │
│  │  │  │  - epoll_wait()                                 ││    │   │
│  │  │  │  - read(fd, input_event)                        ││    │   │
│  │  │  │  - 转换为 RawEvent                              ││    │   │
│  │  │  └─────────────────────────────────────────────────┘│    │   │
│  │  └─────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼ /dev/input/eventX
┌─────────────────────────────────────────────────────────────────────┐
│                          Kernel Layer                                │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心职责

| 职责 | 描述 |
|-----|------|
| 设备发现 | 监控 /dev/input/ 目录，发现新设备 |
| 设备管理 | 打开设备、读取设备能力、维护设备列表 |
| 事件读取 | 使用 epoll 监听设备，读取原始事件 |
| 热插拔处理 | 响应设备添加和移除事件 |

---

## 2. EventHub 数据结构

### 2.1 核心类定义

```cpp
// frameworks/native/services/inputflinger/reader/EventHub.h

class EventHub : public EventHubInterface {
public:
    EventHub();
    virtual ~EventHub();
    
    // 获取事件
    virtual size_t getEvents(int timeoutMillis, RawEvent* buffer, 
                             size_t bufferSize);
    
    // 设备信息查询
    virtual uint32_t getDeviceClasses(int32_t deviceId) const;
    virtual InputDeviceIdentifier getDeviceIdentifier(int32_t deviceId) const;
    virtual int32_t getDeviceControllerNumber(int32_t deviceId) const;
    virtual void getConfiguration(int32_t deviceId, PropertyMap* outConfiguration) const;
    virtual status_t getAbsoluteAxisInfo(int32_t deviceId, int axis,
                                         RawAbsoluteAxisInfo* outAxisInfo) const;
    
    // 设备控制
    virtual bool hasLed(int32_t deviceId, int32_t led) const;
    virtual void setLedState(int32_t deviceId, int32_t led, bool on);
    
    // 唤醒
    virtual void wake();
    
private:
    // 设备管理
    status_t openDeviceLocked(const std::string& devicePath);
    void closeDeviceLocked(Device* device);
    void closeAllDevicesLocked();
    
    // 事件读取
    status_t readNotifyLocked();
    status_t scanDirLocked(const std::string& dirname);
    
    // 设备列表
    std::unordered_map<int32_t, std::unique_ptr<Device>> mDevices;
    
    // epoll
    int mEpollFd;
    int mINotifyFd;
    int mWakeReadPipeFd;
    int mWakeWritePipeFd;
    
    // 设备 ID 分配
    int32_t mNextDeviceId;
    
    // 挂起的事件
    std::vector<RawEvent> mPendingEventItems;
    size_t mPendingEventIndex;
    
    // 锁
    mutable std::mutex mLock;
};
```

### 2.2 Device 结构

```cpp
struct Device {
    int fd;                             // 设备文件描述符
    const int32_t id;                   // 设备 ID
    const std::string path;             // 设备路径
    const InputDeviceIdentifier identifier;  // 设备标识
    
    std::unique_ptr<TouchVideoDevice> videoDevice;
    
    uint32_t classes;                   // 设备类型标志
    
    uint8_t keyBitmask[sizeof_bit_array(KEY_MAX + 1)];
    uint8_t absBitmask[sizeof_bit_array(ABS_MAX + 1)];
    uint8_t relBitmask[sizeof_bit_array(REL_MAX + 1)];
    uint8_t swBitmask[sizeof_bit_array(SW_MAX + 1)];
    uint8_t ledBitmask[sizeof_bit_array(LED_MAX + 1)];
    uint8_t ffBitmask[sizeof_bit_array(FF_MAX + 1)];
    uint8_t propBitmask[sizeof_bit_array(INPUT_PROP_MAX + 1)];
    
    std::string configurationFile;
    std::unique_ptr<PropertyMap> configuration;
    std::unique_ptr<VirtualKeyMap> virtualKeyMap;
    KeyMap keyMap;
    
    sp<KeyCharacterMap> overlayKeyMap;
    sp<KeyCharacterMap> combinedKeyMap;
    
    bool ffEffectPlaying;
    int16_t ffEffectId;
    
    // 时间戳处理
    int32_t timestampOverrideSec;
    int32_t timestampOverrideUsec;
    
    Device(int fd, int32_t id, const std::string& path,
           const InputDeviceIdentifier& identifier);
    ~Device();
    
    void close();
    bool enabled;
};
```

### 2.3 RawEvent 结构

```cpp
// 原始事件
struct RawEvent {
    nsecs_t when;           // 事件时间戳 (纳秒)
    int32_t deviceId;       // 设备 ID
    int32_t type;           // 事件类型 (EV_KEY, EV_ABS...)
    int32_t code;           // 事件码
    int32_t value;          // 事件值
};

// 设备类型标志
enum {
    INPUT_DEVICE_CLASS_KEYBOARD      = 0x00000001,  // 键盘
    INPUT_DEVICE_CLASS_ALPHAKEY      = 0x00000002,  // 字母键盘
    INPUT_DEVICE_CLASS_TOUCH         = 0x00000004,  // 触摸设备
    INPUT_DEVICE_CLASS_CURSOR        = 0x00000008,  // 光标设备
    INPUT_DEVICE_CLASS_MULTI_TOUCH   = 0x00000010,  // 多点触控
    INPUT_DEVICE_CLASS_DPAD          = 0x00000020,  // 方向键
    INPUT_DEVICE_CLASS_GAMEPAD       = 0x00000040,  // 游戏手柄
    INPUT_DEVICE_CLASS_SWITCH        = 0x00000080,  // 开关
    INPUT_DEVICE_CLASS_JOYSTICK      = 0x00000100,  // 操纵杆
    INPUT_DEVICE_CLASS_VIBRATOR      = 0x00000200,  // 震动器
    INPUT_DEVICE_CLASS_MIC           = 0x00000400,  // 麦克风
    INPUT_DEVICE_CLASS_EXTERNAL_STYLUS = 0x00000800,// 外部手写笔
    INPUT_DEVICE_CLASS_ROTARY_ENCODER = 0x00001000, // 旋转编码器
    INPUT_DEVICE_CLASS_SENSOR        = 0x00002000,  // 传感器
};
```

---

## 3. 设备发现与管理

### 3.1 初始化流程

```cpp
// EventHub 构造函数
EventHub::EventHub()
    : mBuiltInKeyboardId(NO_BUILT_IN_KEYBOARD)
    , mNextDeviceId(1)
    , mPendingEventIndex(0)
    , mPendingINotify(false) {
    
    // 创建 epoll 实例
    mEpollFd = epoll_create1(EPOLL_CLOEXEC);
    
    // 创建 inotify 实例用于监控设备目录
    mINotifyFd = inotify_init1(IN_CLOEXEC);
    
    // 监控 /dev/input 目录
    mInputWd = inotify_add_watch(mINotifyFd, DEVICE_PATH, 
                                  IN_DELETE | IN_CREATE);
    
    // 将 inotify fd 添加到 epoll
    struct epoll_event eventItem = {};
    eventItem.events = EPOLLIN | EPOLLWAKEUP;
    eventItem.data.fd = mINotifyFd;
    epoll_ctl(mEpollFd, EPOLL_CTL_ADD, mINotifyFd, &eventItem);
    
    // 创建唤醒管道
    int wakeFds[2];
    pipe2(wakeFds, O_CLOEXEC | O_NONBLOCK);
    mWakeReadPipeFd = wakeFds[0];
    mWakeWritePipeFd = wakeFds[1];
    
    // 将唤醒管道添加到 epoll
    eventItem.data.fd = mWakeReadPipeFd;
    epoll_ctl(mEpollFd, EPOLL_CTL_ADD, mWakeReadPipeFd, &eventItem);
    
    // 扫描现有设备
    scanDevicesLocked();
}

// 扫描设备目录
void EventHub::scanDevicesLocked() {
    scanDirLocked(DEVICE_PATH);  // /dev/input
}

status_t EventHub::scanDirLocked(const std::string& dirname) {
    DIR* dir = opendir(dirname.c_str());
    if (dir == nullptr) {
        return -errno;
    }
    
    while (struct dirent* de = readdir(dir)) {
        // 跳过 . 和 ..
        if (de->d_name[0] == '.') continue;
        
        // 只处理 event* 设备
        if (strncmp(de->d_name, "event", 5) != 0) continue;
        
        std::string devicePath = dirname + "/" + de->d_name;
        openDeviceLocked(devicePath);
    }
    
    closedir(dir);
    return OK;
}
```

### 3.2 打开设备

```cpp
status_t EventHub::openDeviceLocked(const std::string& devicePath) {
    // 打开设备文件
    int fd = open(devicePath.c_str(), O_RDWR | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) {
        return -errno;
    }
    
    // 获取设备标识信息
    InputDeviceIdentifier identifier;
    
    // 获取设备名称
    char buffer[80];
    if (ioctl(fd, EVIOCGNAME(sizeof(buffer) - 1), buffer) >= 0) {
        identifier.name = buffer;
    }
    
    // 获取设备 ID
    struct input_id inputId;
    if (ioctl(fd, EVIOCGID, &inputId) >= 0) {
        identifier.bus = inputId.bustype;
        identifier.product = inputId.product;
        identifier.vendor = inputId.vendor;
        identifier.version = inputId.version;
    }
    
    // 获取物理路径
    if (ioctl(fd, EVIOCGPHYS(sizeof(buffer) - 1), buffer) >= 0) {
        identifier.location = buffer;
    }
    
    // 获取唯一标识
    if (ioctl(fd, EVIOCGUNIQ(sizeof(buffer) - 1), buffer) >= 0) {
        identifier.uniqueId = buffer;
    }
    
    // 分配设备 ID
    int32_t deviceId = mNextDeviceId++;
    
    // 创建 Device 对象
    std::unique_ptr<Device> device = 
        std::make_unique<Device>(fd, deviceId, devicePath, identifier);
    
    // 读取设备能力
    loadConfigurationLocked(device.get());
    
    // 读取事件类型位图
    ioctl(fd, EVIOCGBIT(0, sizeof(device->evBitmask)), device->evBitmask);
    
    // 根据能力确定设备类型
    device->classes = 0;
    
    // 检查是否支持按键
    if (test_bit(EV_KEY, device->evBitmask)) {
        ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(device->keyBitmask)), 
              device->keyBitmask);
        
        // 检查是否是键盘
        bool haveKeyboardKeys = containsNonZeroByte(device->keyBitmask, 0, 
                                                     sizeof_bit_array(BTN_MISC));
        if (haveKeyboardKeys) {
            device->classes |= INPUT_DEVICE_CLASS_KEYBOARD;
        }
        
        // 检查是否有 DPAD
        if (test_bit(KEY_UP, device->keyBitmask) &&
            test_bit(KEY_DOWN, device->keyBitmask) &&
            test_bit(KEY_LEFT, device->keyBitmask) &&
            test_bit(KEY_RIGHT, device->keyBitmask)) {
            device->classes |= INPUT_DEVICE_CLASS_DPAD;
        }
        
        // 检查是否是游戏手柄
        if (test_bit(BTN_GAMEPAD, device->keyBitmask)) {
            device->classes |= INPUT_DEVICE_CLASS_GAMEPAD;
        }
    }
    
    // 检查是否支持绝对坐标
    if (test_bit(EV_ABS, device->evBitmask)) {
        ioctl(fd, EVIOCGBIT(EV_ABS, sizeof(device->absBitmask)), 
              device->absBitmask);
        
        // 检查是否是多点触控
        if (test_bit(ABS_MT_POSITION_X, device->absBitmask) &&
            test_bit(ABS_MT_POSITION_Y, device->absBitmask)) {
            device->classes |= INPUT_DEVICE_CLASS_TOUCH | 
                               INPUT_DEVICE_CLASS_MULTI_TOUCH;
        }
        // 检查是否是单点触控
        else if (test_bit(ABS_X, device->absBitmask) &&
                 test_bit(ABS_Y, device->absBitmask)) {
            device->classes |= INPUT_DEVICE_CLASS_TOUCH;
        }
        
        // 检查是否是操纵杆
        if (test_bit(ABS_X, device->absBitmask) ||
            test_bit(ABS_Y, device->absBitmask) ||
            test_bit(ABS_HAT0X, device->absBitmask) ||
            test_bit(ABS_HAT0Y, device->absBitmask)) {
            device->classes |= INPUT_DEVICE_CLASS_JOYSTICK;
        }
    }
    
    // 检查是否支持相对坐标
    if (test_bit(EV_REL, device->evBitmask)) {
        ioctl(fd, EVIOCGBIT(EV_REL, sizeof(device->relBitmask)), 
              device->relBitmask);
        
        // 检查是否是鼠标/触控板
        if (test_bit(REL_X, device->relBitmask) &&
            test_bit(REL_Y, device->relBitmask)) {
            device->classes |= INPUT_DEVICE_CLASS_CURSOR;
        }
    }
    
    // 将设备 fd 添加到 epoll
    struct epoll_event eventItem = {};
    eventItem.events = EPOLLIN | EPOLLWAKEUP;
    eventItem.data.fd = fd;
    epoll_ctl(mEpollFd, EPOLL_CTL_ADD, fd, &eventItem);
    
    // 添加到设备列表
    mDevices[deviceId] = std::move(device);
    
    // 生成设备添加事件
    RawEvent event;
    event.when = systemTime(SYSTEM_TIME_MONOTONIC);
    event.deviceId = deviceId;
    event.type = DEVICE_ADDED;
    event.code = 0;
    event.value = 0;
    mPendingEventItems.push_back(event);
    
    return OK;
}
```

### 3.3 热插拔处理

```cpp
// 处理 inotify 事件
status_t EventHub::readNotifyLocked() {
    char event_buf[512];
    ssize_t res = read(mINotifyFd, event_buf, sizeof(event_buf));
    
    if (res < (int)sizeof(struct inotify_event)) {
        return res < 0 ? -errno : BAD_VALUE;
    }
    
    // 解析 inotify 事件
    char* event_ptr = event_buf;
    while (res >= (int)sizeof(struct inotify_event)) {
        struct inotify_event* event = (struct inotify_event*)event_ptr;
        
        if (event->len > 0) {
            std::string filename = event->name;
            
            // 检查是否是 event* 设备
            if (filename.find("event") == 0) {
                std::string devicePath = std::string(DEVICE_PATH) + "/" + filename;
                
                if (event->mask & IN_CREATE) {
                    // 新设备添加
                    openDeviceLocked(devicePath);
                } else if (event->mask & IN_DELETE) {
                    // 设备移除
                    closeDeviceByPathLocked(devicePath);
                }
            }
        }
        
        size_t event_size = sizeof(struct inotify_event) + event->len;
        res -= event_size;
        event_ptr += event_size;
    }
    
    return OK;
}
```

---

## 4. 事件读取

### 4.1 getEvents 核心实现

```cpp
size_t EventHub::getEvents(int timeoutMillis, RawEvent* buffer, size_t bufferSize) {
    std::scoped_lock _l(mLock);
    
    size_t count = 0;
    
    for (;;) {
        // 1. 先返回挂起的事件
        while (mPendingEventIndex < mPendingEventItems.size()) {
            const RawEvent& event = mPendingEventItems[mPendingEventIndex++];
            buffer[count++] = event;
            if (count >= bufferSize) {
                break;
            }
        }
        
        if (count >= bufferSize) {
            break;
        }
        
        // 清空挂起事件
        mPendingEventItems.clear();
        mPendingEventIndex = 0;
        
        // 2. 处理 inotify 事件
        if (mPendingINotify) {
            mPendingINotify = false;
            readNotifyLocked();
            continue;
        }
        
        // 3. 如果已有事件, 返回
        if (count > 0) {
            break;
        }
        
        // 4. 等待新事件
        int pollResult = epoll_wait(mEpollFd, mPendingEventItems.data(),
                                    EPOLL_MAX_EVENTS, timeoutMillis);
        
        if (pollResult == 0) {
            // 超时
            break;
        }
        
        if (pollResult < 0) {
            if (errno != EINTR) {
                ALOGE("epoll_wait failed: %s", strerror(errno));
            }
            break;
        }
        
        // 5. 处理 epoll 返回的事件
        for (int i = 0; i < pollResult; i++) {
            const struct epoll_event& eventItem = mPendingEventItems[i];
            
            if (eventItem.data.fd == mINotifyFd) {
                // inotify 事件 - 设备添加/移除
                mPendingINotify = true;
            } else if (eventItem.data.fd == mWakeReadPipeFd) {
                // 唤醒管道
                char c;
                read(mWakeReadPipeFd, &c, 1);
            } else {
                // 设备事件
                Device* device = getDeviceByFdLocked(eventItem.data.fd);
                if (device) {
                    readDeviceEventsLocked(device, buffer, bufferSize, count);
                }
            }
        }
    }
    
    return count;
}
```

### 4.2 读取设备事件

```cpp
void EventHub::readDeviceEventsLocked(Device* device, RawEvent* buffer,
                                       size_t bufferSize, size_t& count) {
    struct input_event readBuffer[EVENT_BUFFER_SIZE];
    
    // 读取事件
    ssize_t readSize = read(device->fd, readBuffer, sizeof(readBuffer));
    
    if (readSize < 0) {
        if (errno != EAGAIN && errno != EINTR) {
            ALOGW("Failed to read from device %s: %s",
                  device->path.c_str(), strerror(errno));
            
            // 设备可能已断开
            if (errno == ENODEV) {
                closeDeviceLocked(device);
            }
        }
        return;
    }
    
    // 计算事件数量
    size_t eventCount = readSize / sizeof(struct input_event);
    
    // 转换事件
    for (size_t i = 0; i < eventCount && count < bufferSize; i++) {
        const struct input_event& iev = readBuffer[i];
        
        RawEvent& event = buffer[count++];
        
        // 设置时间戳
        event.when = processEventTimestamp(iev);
        event.deviceId = device->id;
        event.type = iev.type;
        event.code = iev.code;
        event.value = iev.value;
    }
}

// 处理事件时间戳
nsecs_t EventHub::processEventTimestamp(const struct input_event& iev) {
    // 将 timeval 转换为纳秒
    nsecs_t when = s2ns(iev.input_event_sec) + us2ns(iev.input_event_usec);
    
    // 确保时间戳单调递增
    nsecs_t now = systemTime(SYSTEM_TIME_MONOTONIC);
    if (when > now) {
        when = now;
    }
    
    return when;
}
```

---

## 5. 设备配置

### 5.1 配置文件格式

```ini
# /vendor/usr/idc/device_name.idc (Input Device Configuration)

# 设备类型
touch.deviceType = touchScreen

# 触摸参数
touch.orientationAware = 1
touch.size.calibration = diameter
touch.size.scale = 10
touch.size.bias = 0
touch.size.isSummed = 0

touch.pressure.calibration = amplitude
touch.pressure.scale = 0.01

touch.orientation.calibration = none

# 手势参数
touch.gestureMode = multi

# 虚拟按键
virtualKey.0.scanCode = 158
virtualKey.0.centerX = 100
virtualKey.0.centerY = 1350
virtualKey.0.width = 100
virtualKey.0.height = 80
```

### 5.2 键盘布局映射

```cpp
// Key Layout 文件 (.kl)
// /vendor/usr/keylayout/device_name.kl

key 116   POWER          WAKE
key 114   VOLUME_DOWN
key 115   VOLUME_UP
key 158   BACK
key 172   HOME

// Key Character Map 文件 (.kcm)
// /vendor/usr/keychars/device_name.kcm

type FULL

key A {
    label:                              'A'
    base:                               'a'
    shift, capslock:                    'A'
}
```

### 5.3 配置加载

```cpp
void EventHub::loadConfigurationLocked(Device* device) {
    // 查找配置文件
    std::string configPath = getInputDeviceConfigurationFilePathByDeviceIdentifier(
            device->identifier, InputDeviceConfigurationFileType::CONFIGURATION);
    
    if (!configPath.empty()) {
        device->configurationFile = configPath;
        device->configuration = std::make_unique<PropertyMap>();
        
        status_t status = PropertyMap::load(String8(configPath.c_str()),
                                            device->configuration.get());
        if (status) {
            ALOGE("Error loading input device configuration: %s", configPath.c_str());
        }
    }
    
    // 加载键盘布局
    loadKeyMapLocked(device);
    
    // 加载虚拟按键
    loadVirtualKeyMapLocked(device);
}
```

---

## 6. 与 InputReader 的交互

### 6.1 调用时序

```
InputReaderThread
      │
      ▼
┌───────────────────────────────────────────────────────────────┐
│ InputReader::loopOnce()                                       │
│                                                               │
│   // 1. 从 EventHub 获取事件                                  │
│   size_t count = mEventHub->getEvents(timeout,               │
│                                        mEventBuffer,          │
│                                        EVENT_BUFFER_SIZE);    │
│                                                               │
│   // 2. 处理事件                                              │
│   if (count) {                                               │
│       processEventsLocked(mEventBuffer, count);              │
│   }                                                          │
│                                                               │
│   // 3. 刷新到 Dispatcher                                    │
│   mQueuedListener->flush();                                  │
└───────────────────────────────────────────────────────────────┘
```

### 6.2 事件类型处理

```cpp
// InputReader 处理 EventHub 返回的事件
void InputReader::processEventsLocked(const RawEvent* rawEvents, size_t count) {
    for (const RawEvent* rawEvent = rawEvents; count--; rawEvent++) {
        switch (rawEvent->type) {
            case DEVICE_ADDED:
                // 设备添加
                addDeviceLocked(rawEvent->when, rawEvent->deviceId);
                break;
                
            case DEVICE_REMOVED:
                // 设备移除
                removeDeviceLocked(rawEvent->when, rawEvent->deviceId);
                break;
                
            case FINISHED_DEVICE_SCAN:
                // 设备扫描完成
                handleConfigurationChangedLocked(rawEvent->when);
                break;
                
            default:
                // 普通输入事件
                processEventsForDeviceLocked(rawEvent->deviceId, rawEvent, 1);
                break;
        }
    }
}
```

---

## 7. 本章小结

EventHub 是 Native 层 Input 系统的基础，承担以下核心职责：

| 职责 | 实现方式 |
|-----|---------|
| 设备发现 | inotify 监控 /dev/input/ |
| 事件读取 | epoll + read() |
| 设备管理 | Device 结构体封装 |
| 热插拔 | inotify IN_CREATE/IN_DELETE |
| 配置管理 | .idc, .kl, .kcm 文件 |

关键设计点：
1. 使用 epoll 实现高效的多设备事件监听
2. inotify 实现设备热插拔检测
3. 唤醒管道用于外部唤醒阻塞的 getEvents()
4. 设备能力位图用于设备分类

下一篇将介绍 InputReader 的事件处理机制。

---

## 参考资料

1. `frameworks/native/services/inputflinger/reader/EventHub.cpp`
2. `frameworks/native/services/inputflinger/reader/include/EventHub.h`
3. Android Input Device Configuration 文档
