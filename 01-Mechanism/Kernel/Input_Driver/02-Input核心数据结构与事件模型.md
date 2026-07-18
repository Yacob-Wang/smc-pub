# Input 核心数据结构与事件模型

## 引言

理解 Input 系统的核心数据结构是深入学习事件处理流程的基础。本文将详细介绍从 Kernel 层到应用层各个关键数据结构的定义、转换过程以及设计考量。

---

## 1. 数据结构层级总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                           应用层 (Java)                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│  │ InputEvent  │    │MotionEvent │    │  KeyEvent   │            │
│  │   (基类)    │    │ (触摸事件) │    │  (按键事件) │            │
│  └─────────────┘    └─────────────┘    └─────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ JNI 转换
┌─────────────────────────────────────────────────────────────────────┐
│                          Native 层 (C++)                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│  │ InputMessage│    │ EventEntry │    │ NotifyArgs  │            │
│  │ (传输格式)  │    │(分发队列项)│    │(Reader输出) │            │
│  └─────────────┘    └─────────────┘    └─────────────┘            │
│  ┌─────────────┐                                                   │
│  │  RawEvent   │                                                   │
│  │(EventHub输出)│                                                   │
│  └─────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ read()
┌─────────────────────────────────────────────────────────────────────┐
│                          Kernel 层 (C)                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      input_event                             │   │
│  │   struct timeval time;  // 时间戳                            │   │
│  │   __u16 type;           // 事件类型                          │   │
│  │   __u16 code;           // 事件码                            │   │
│  │   __s32 value;          // 事件值                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Kernel 层数据结构

### 2.1 input_event

`input_event` 是 Linux Input 子系统的基础数据结构，定义于 `include/uapi/linux/input.h`：

```c
struct input_event {
    struct timeval time;    // 事件时间戳
    __u16 type;             // 事件类型
    __u16 code;             // 事件码
    __s32 value;            // 事件值
};

// 32位系统上: 16 字节
// 64位系统上: 24 字节 (timeval 扩展)
```

### 2.2 事件类型 (type)

| 类型 | 值 | 描述 | 典型使用 |
|-----|---|------|---------|
| EV_SYN | 0x00 | 同步事件 | 事件分隔符 |
| EV_KEY | 0x01 | 按键事件 | 按键按下/释放 |
| EV_REL | 0x02 | 相对位移 | 鼠标移动 |
| EV_ABS | 0x03 | 绝对坐标 | 触摸屏坐标 |
| EV_MSC | 0x04 | 杂项事件 | 扫描码等 |
| EV_SW  | 0x05 | 开关事件 | 合盖检测 |
| EV_LED | 0x11 | LED 事件 | 键盘指示灯 |
| EV_REP | 0x14 | 重复事件 | 按键重复 |
| EV_FF  | 0x15 | 力反馈 | 震动马达 |

### 2.3 按键事件码 (EV_KEY)

```c
// 常用按键码 (include/uapi/linux/input-event-codes.h)
#define KEY_RESERVED     0
#define KEY_ESC          1
#define KEY_1            2
// ...
#define KEY_BACK         158    // Android 返回键
#define KEY_HOMEPAGE     172    // Android Home 键
#define KEY_POWER        116    // 电源键
#define KEY_VOLUMEDOWN   114    // 音量减
#define KEY_VOLUMEUP     115    // 音量加

// 触摸事件（作为按键处理）
#define BTN_TOUCH        0x14a  // 触摸按下
#define BTN_TOOL_FINGER  0x145  // 手指工具
```

### 2.4 绝对坐标事件码 (EV_ABS)

```c
// 单点触摸
#define ABS_X            0x00    // X 坐标
#define ABS_Y            0x01    // Y 坐标
#define ABS_PRESSURE     0x18    // 压力值

// 多点触摸 (MT - Multi-Touch)
#define ABS_MT_SLOT         0x2f    // 触摸点槽位
#define ABS_MT_TOUCH_MAJOR  0x30    // 触摸区域长轴
#define ABS_MT_TOUCH_MINOR  0x31    // 触摸区域短轴
#define ABS_MT_POSITION_X   0x35    // MT X 坐标
#define ABS_MT_POSITION_Y   0x36    // MT Y 坐标
#define ABS_MT_TRACKING_ID  0x39    // 触摸点追踪 ID
#define ABS_MT_PRESSURE     0x3a    // MT 压力值
```

### 2.5 input_dev 结构

`input_dev` 是输入设备的内核抽象：

```c
struct input_dev {
    const char *name;           // 设备名称
    const char *phys;           // 设备物理路径
    const char *uniq;           // 设备唯一标识
    struct input_id id;         // 设备 ID (vendor, product...)
    
    unsigned long evbit[BITS_TO_LONGS(EV_CNT)];     // 支持的事件类型
    unsigned long keybit[BITS_TO_LONGS(KEY_CNT)];   // 支持的按键
    unsigned long absbit[BITS_TO_LONGS(ABS_CNT)];   // 支持的绝对坐标轴
    
    struct input_absinfo *absinfo;  // 绝对坐标轴信息
    
    int (*open)(struct input_dev *dev);
    void (*close)(struct input_dev *dev);
    int (*event)(struct input_dev *dev, unsigned int type, 
                 unsigned int code, int value);
    // ...
};

struct input_absinfo {
    __s32 value;        // 当前值
    __s32 minimum;      // 最小值
    __s32 maximum;      // 最大值
    __s32 fuzz;         // 噪声过滤阈值
    __s32 flat;         // 中心区死区
    __s32 resolution;   // 分辨率 (单位/毫米)
};
```

---

## 3. Native 层数据结构

### 3.1 RawEvent

`RawEvent` 是 EventHub 读取的原始事件，定义于 `EventHub.h`：

```cpp
struct RawEvent {
    nsecs_t when;           // 事件时间（纳秒）
    int32_t deviceId;       // 设备 ID
    int32_t type;           // 事件类型
    int32_t code;           // 事件码
    int32_t value;          // 事件值
};
```

与 `input_event` 相比，`RawEvent` 添加了：
- `deviceId`：标识事件来源设备
- 时间精度提升到纳秒

### 3.2 NotifyArgs 系列

`NotifyArgs` 是 InputReader 处理后输出的事件，是一个继承体系：

```cpp
// 基类
struct NotifyArgs {
    int32_t id;             // 事件 ID
    nsecs_t eventTime;      // 事件时间
};

// 按键事件
struct NotifyKeyArgs : public NotifyArgs {
    int32_t deviceId;
    uint32_t source;        // 输入源 (AINPUT_SOURCE_KEYBOARD等)
    int32_t displayId;      // 显示屏 ID
    uint32_t policyFlags;   // 策略标志
    int32_t action;         // AKEY_EVENT_ACTION_DOWN/UP
    int32_t flags;          // 事件标志
    int32_t keyCode;        // Android keyCode
    int32_t scanCode;       // 硬件扫描码
    int32_t metaState;      // 修饰键状态 (Alt, Shift, Ctrl)
    nsecs_t downTime;       // 按下时间
};

// 触摸/指针事件
struct NotifyMotionArgs : public NotifyArgs {
    int32_t deviceId;
    uint32_t source;        // AINPUT_SOURCE_TOUCHSCREEN 等
    int32_t displayId;
    uint32_t policyFlags;
    int32_t action;         // AMOTION_EVENT_ACTION_DOWN 等
    int32_t actionButton;   // 按钮动作
    int32_t flags;
    int32_t metaState;
    int32_t buttonState;    // 按钮状态
    int32_t edgeFlags;      // 边缘标志
    
    uint32_t pointerCount;                  // 触摸点数量
    PointerProperties pointerProperties[MAX_POINTERS];  // 指针属性
    PointerCoords pointerCoords[MAX_POINTERS];          // 指针坐标
    
    float xPrecision;       // X 精度
    float yPrecision;       // Y 精度
    float xCursorPosition;  // 光标 X
    float yCursorPosition;  // 光标 Y
    nsecs_t downTime;       // 按下时间
};
```

### 3.3 PointerProperties 和 PointerCoords

```cpp
struct PointerProperties {
    int32_t id;             // 指针 ID (追踪同一触摸点)
    int32_t toolType;       // 工具类型 (手指、手写笔等)
};

struct PointerCoords {
    // 使用位掩码标记有效数据
    uint64_t bits;
    
    // 坐标值数组
    float values[MAX_AXES];  // X, Y, PRESSURE, SIZE, ...
    
    // 访问方法
    float getX() const;
    float getY() const;
    float getPressure() const;
    float getSize() const;
    float getTouchMajor() const;
    float getTouchMinor() const;
    // ...
};

// 坐标轴定义
enum {
    AMOTION_EVENT_AXIS_X = 0,
    AMOTION_EVENT_AXIS_Y = 1,
    AMOTION_EVENT_AXIS_PRESSURE = 2,
    AMOTION_EVENT_AXIS_SIZE = 3,
    AMOTION_EVENT_AXIS_TOUCH_MAJOR = 4,
    AMOTION_EVENT_AXIS_TOUCH_MINOR = 5,
    // ...
};
```

### 3.4 EventEntry

`EventEntry` 是 InputDispatcher 内部使用的事件队列项：

```cpp
struct EventEntry {
    enum Type {
        TYPE_CONFIGURATION_CHANGED,
        TYPE_DEVICE_RESET,
        TYPE_FOCUS,
        TYPE_KEY,
        TYPE_MOTION,
        TYPE_SENSOR,
        TYPE_POINTER_CAPTURE_CHANGED,
        TYPE_DRAG,
    };
    
    int32_t id;
    Type type;
    nsecs_t eventTime;
    uint32_t policyFlags;
    InjectionState* injectionState;
    
    bool dispatchInProgress;    // 是否正在分发
    
    // 引用计数
    int32_t refCount;
};

struct KeyEntry : EventEntry {
    int32_t deviceId;
    uint32_t source;
    int32_t displayId;
    int32_t action;
    int32_t flags;
    int32_t keyCode;
    int32_t scanCode;
    int32_t metaState;
    int32_t repeatCount;        // 重复次数
    nsecs_t downTime;
    
    // 分发状态
    InterceptKeyResult interceptKeyResult;
    nsecs_t interceptKeyWakeupTime;
};

struct MotionEntry : EventEntry {
    int32_t deviceId;
    uint32_t source;
    int32_t displayId;
    int32_t action;
    int32_t actionButton;
    int32_t flags;
    int32_t metaState;
    int32_t buttonState;
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

### 3.5 InputMessage

`InputMessage` 是通过 InputChannel 传输的消息格式：

```cpp
struct InputMessage {
    enum Type : uint32_t {
        TYPE_KEY = 1,
        TYPE_MOTION = 2,
        TYPE_FINISHED = 3,      // 事件处理完成
        TYPE_FOCUS = 4,
        TYPE_CAPTURE = 5,
        TYPE_DRAG = 6,
        TYPE_TIMELINE = 7,
    };
    
    struct Header {
        Type type;
        uint32_t seq;           // 序列号（用于匹配响应）
    } header;
    
    union Body {
        struct Key {
            int32_t eventId;
            nsecs_t eventTime;
            int32_t deviceId;
            int32_t source;
            int32_t displayId;
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
            int32_t action;
            int32_t actionButton;
            int32_t flags;
            int32_t metaState;
            int32_t buttonState;
            int32_t edgeFlags;
            nsecs_t downTime;
            float xOffset;
            float yOffset;
            float xPrecision;
            float yPrecision;
            float xCursorPosition;
            float yCursorPosition;
            uint32_t pointerCount;
            // 可变长度的指针数据...
        } motion;
        
        struct Finished {
            bool handled;       // 事件是否被处理
            nsecs_t consumeTime;
        } finished;
    } body;
};
```

---

## 4. Framework 层数据结构 (Java)

### 4.1 InputEvent

`InputEvent` 是所有输入事件的基类：

```java
public abstract class InputEvent implements Parcelable {
    // 事件来源
    public abstract int getSource();
    public abstract void setSource(int source);
    
    // 设备 ID
    public abstract int getDeviceId();
    
    // 事件时间（系统启动后的纳秒）
    public abstract long getEventTime();
    public abstract long getEventTimeNanos();
    
    // 是否来自指定设备类型
    public final boolean isFromSource(int source) {
        return (getSource() & source) == source;
    }
}
```

### 4.2 KeyEvent

`KeyEvent` 表示按键事件：

```java
public class KeyEvent extends InputEvent {
    // Action 常量
    public static final int ACTION_DOWN = 0;
    public static final int ACTION_UP = 1;
    public static final int ACTION_MULTIPLE = 2;
    
    // 修饰键掩码
    public static final int META_ALT_ON = 0x02;
    public static final int META_SHIFT_ON = 0x01;
    public static final int META_CTRL_ON = 0x1000;
    public static final int META_META_ON = 0x10000;
    
    // 成员变量
    private int mDeviceId;
    private int mSource;
    private int mDisplayId;
    private int mAction;
    private int mKeyCode;           // KEYCODE_BACK, KEYCODE_HOME 等
    private int mScanCode;          // 硬件扫描码
    private int mMetaState;         // 修饰键状态
    private int mFlags;
    private int mRepeatCount;       // 按键重复次数
    private long mDownTime;         // 按下时间
    private long mEventTime;        // 事件时间
    private String mCharacters;     // ACTION_MULTIPLE 时的字符
    
    // 常用方法
    public final int getAction();
    public final int getKeyCode();
    public final int getScanCode();
    public final int getMetaState();
    public final int getRepeatCount();
    public final long getDownTime();
    
    // 修饰键检查
    public final boolean isAltPressed();
    public final boolean isShiftPressed();
    public final boolean isCtrlPressed();
    
    // KeyCode 转换
    public static int keyCodeFromString(String symbolicName);
    public static String keyCodeToString(int keyCode);
}
```

### 4.3 MotionEvent

`MotionEvent` 表示触摸和指针事件，是最复杂的事件类型：

```java
public final class MotionEvent extends InputEvent {
    // Action 常量
    public static final int ACTION_DOWN = 0;
    public static final int ACTION_UP = 1;
    public static final int ACTION_MOVE = 2;
    public static final int ACTION_CANCEL = 3;
    public static final int ACTION_OUTSIDE = 4;
    public static final int ACTION_POINTER_DOWN = 5;    // 多点触控
    public static final int ACTION_POINTER_UP = 6;
    public static final int ACTION_HOVER_MOVE = 7;
    public static final int ACTION_SCROLL = 8;
    
    // Action 掩码（用于提取多点触控的指针索引）
    public static final int ACTION_MASK = 0xff;
    public static final int ACTION_POINTER_INDEX_MASK = 0xff00;
    public static final int ACTION_POINTER_INDEX_SHIFT = 8;
    
    // 坐标轴常量
    public static final int AXIS_X = 0;
    public static final int AXIS_Y = 1;
    public static final int AXIS_PRESSURE = 2;
    public static final int AXIS_SIZE = 3;
    public static final int AXIS_TOUCH_MAJOR = 4;
    public static final int AXIS_TOUCH_MINOR = 5;
    public static final int AXIS_TOOL_MAJOR = 6;
    public static final int AXIS_TOOL_MINOR = 7;
    public static final int AXIS_ORIENTATION = 8;
    
    // 工具类型
    public static final int TOOL_TYPE_UNKNOWN = 0;
    public static final int TOOL_TYPE_FINGER = 1;
    public static final int TOOL_TYPE_STYLUS = 2;
    public static final int TOOL_TYPE_MOUSE = 3;
    public static final int TOOL_TYPE_ERASER = 4;
    
    // Native 指针（指向 C++ 对象）
    private long mNativePtr;
    
    // 基本方法
    public final int getAction();
    public final int getActionMasked();     // 不含指针索引
    public final int getActionIndex();      // 多点触控指针索引
    
    // 单点坐标（第一个触摸点）
    public final float getX();
    public final float getY();
    public final float getPressure();
    public final float getSize();
    
    // 多点触控
    public final int getPointerCount();
    public final int getPointerId(int pointerIndex);
    public final int findPointerIndex(int pointerId);
    public final float getX(int pointerIndex);
    public final float getY(int pointerIndex);
    public final float getPressure(int pointerIndex);
    
    // 历史数据（批处理优化）
    public final int getHistorySize();
    public final long getHistoricalEventTime(int pos);
    public final float getHistoricalX(int pointerIndex, int pos);
    public final float getHistoricalY(int pointerIndex, int pos);
    
    // 坐标变换
    public final void offsetLocation(float deltaX, float deltaY);
    public final void setLocation(float x, float y);
    public final void transform(Matrix matrix);
}
```

### 4.4 InputChannel

`InputChannel` 是事件传输通道：

```java
public final class InputChannel implements Parcelable {
    // Native 指针
    private long mPtr;
    
    // 创建 Socket 对
    public static InputChannel[] openInputChannelPair(String name) {
        // 返回 [server, client] 两个 InputChannel
    }
    
    // 获取名称
    public String getName();
    
    // 复制 channel
    public InputChannel dup();
    
    // Native 文件描述符
    public IBinder getToken();
}
```

---

## 5. 输入源 (Input Source)

Input Source 标识输入设备类型，定义于 `InputDevice.java` 和 Native 层：

```java
public final class InputDevice {
    // 类别掩码
    public static final int SOURCE_CLASS_MASK = 0x000000ff;
    public static final int SOURCE_CLASS_NONE = 0x00000000;
    public static final int SOURCE_CLASS_BUTTON = 0x00000001;   // 按钮
    public static final int SOURCE_CLASS_POINTER = 0x00000002;  // 指针
    public static final int SOURCE_CLASS_TRACKBALL = 0x00000004;// 轨迹球
    public static final int SOURCE_CLASS_POSITION = 0x00000008; // 位置
    public static final int SOURCE_CLASS_JOYSTICK = 0x00000010; // 操纵杆
    
    // 具体设备类型
    public static final int SOURCE_UNKNOWN = 0x00000000;
    public static final int SOURCE_KEYBOARD = 0x00000100 | SOURCE_CLASS_BUTTON;
    public static final int SOURCE_DPAD = 0x00000200 | SOURCE_CLASS_BUTTON;
    public static final int SOURCE_GAMEPAD = 0x00000400 | SOURCE_CLASS_BUTTON;
    public static final int SOURCE_TOUCHSCREEN = 0x00001000 | SOURCE_CLASS_POINTER;
    public static final int SOURCE_MOUSE = 0x00002000 | SOURCE_CLASS_POINTER;
    public static final int SOURCE_STYLUS = 0x00004000 | SOURCE_CLASS_POINTER;
    public static final int SOURCE_TRACKBALL = 0x00010000 | SOURCE_CLASS_TRACKBALL;
    public static final int SOURCE_MOUSE_RELATIVE = 0x00020000 | SOURCE_CLASS_TRACKBALL;
    public static final int SOURCE_TOUCHPAD = 0x00100000 | SOURCE_CLASS_POSITION;
    public static final int SOURCE_JOYSTICK = 0x01000000 | SOURCE_CLASS_JOYSTICK;
}
```

---

## 6. 事件 Action 详解

### 6.1 KeyEvent Action

| Action | 值 | 描述 |
|-------|---|------|
| ACTION_DOWN | 0 | 按键按下 |
| ACTION_UP | 1 | 按键释放 |
| ACTION_MULTIPLE | 2 | 多个按键字符（已废弃） |

### 6.2 MotionEvent Action

| Action | 值 | 描述 |
|-------|---|------|
| ACTION_DOWN | 0 | 第一个触摸点按下 |
| ACTION_UP | 1 | 最后一个触摸点抬起 |
| ACTION_MOVE | 2 | 触摸点移动 |
| ACTION_CANCEL | 3 | 事件被取消 |
| ACTION_OUTSIDE | 4 | 触摸在窗口外 |
| ACTION_POINTER_DOWN | 5 | 非第一个触摸点按下 |
| ACTION_POINTER_UP | 6 | 非最后一个触摸点抬起 |
| ACTION_HOVER_MOVE | 7 | 指针悬浮移动 |
| ACTION_SCROLL | 8 | 滚轮滚动 |
| ACTION_HOVER_ENTER | 9 | 指针进入窗口 |
| ACTION_HOVER_EXIT | 10 | 指针离开窗口 |
| ACTION_BUTTON_PRESS | 11 | 按钮按下 |
| ACTION_BUTTON_RELEASE | 12 | 按钮释放 |

### 6.3 多点触控 Action 编码

```java
// 多点触控的 action 编码：低 8 位是动作类型，高 8 位是指针索引
int action = event.getAction();
int actionMasked = action & MotionEvent.ACTION_MASK;          // 动作类型
int pointerIndex = (action & MotionEvent.ACTION_POINTER_INDEX_MASK) 
                   >> MotionEvent.ACTION_POINTER_INDEX_SHIFT;  // 指针索引

// 示例：第二个手指抬起
// action = ACTION_POINTER_UP | (1 << ACTION_POINTER_INDEX_SHIFT)
// action = 6 | (1 << 8) = 6 | 256 = 262
```

---

## 7. 数据结构转换流程

```
┌─────────────────┐
│  input_event    │   Kernel: 驱动上报
│  (type/code/    │
│   value/time)   │
└────────┬────────┘
         │ read() 系统调用
         ▼
┌─────────────────┐
│   RawEvent      │   EventHub: 添加 deviceId
│  (+ deviceId)   │
└────────┬────────┘
         │ InputMapper 处理
         ▼
┌─────────────────┐
│  NotifyArgs     │   InputReader: 事件合成
│ (KeyArgs/       │   - 坐标转换
│  MotionArgs)    │   - 多点触控合成
└────────┬────────┘   - Action 生成
         │
         ▼
┌─────────────────┐
│  EventEntry     │   InputDispatcher: 添加分发信息
│ (+ dispatch     │   - 目标窗口
│   state)        │   - 超时控制
└────────┬────────┘
         │ InputChannel (Socket)
         ▼
┌─────────────────┐
│  InputMessage   │   跨进程传输
│ (序列化格式)    │
└────────┬────────┘
         │ JNI
         ▼
┌─────────────────┐
│  InputEvent     │   Java 层
│ (KeyEvent/      │   - View 分发
│  MotionEvent)   │   - 应用处理
└─────────────────┘
```

---

## 8. 本章小结

本文介绍了 Input 系统各层的核心数据结构：

| 层级 | 核心结构 | 特点 |
|-----|---------|------|
| Kernel | input_event | 简单、通用、16/24 字节 |
| Native | RawEvent | 添加设备 ID |
| Native | NotifyArgs | 事件合成后的完整信息 |
| Native | EventEntry | 添加分发状态 |
| Native | InputMessage | 跨进程传输格式 |
| Java | InputEvent | 面向对象封装 |
| Java | MotionEvent | 支持多点触控、历史数据 |

理解这些数据结构是分析事件流转的基础，下一篇将介绍事件的完整流程。

---

## 参考资料

1. `include/uapi/linux/input.h` - 内核事件定义
2. `frameworks/native/include/input/Input.h` - Native 层定义
3. `frameworks/base/core/java/android/view/InputEvent.java` - Java 层定义
