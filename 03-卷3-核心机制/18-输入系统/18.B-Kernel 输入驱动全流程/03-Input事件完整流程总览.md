# Input 事件完整流程总览

## 引言

本文从全局视角梳理一个输入事件从产生到被应用处理的完整流程，建立端到端的理解，为后续深入各层细节打下基础。

---

## 1. 事件流转全景图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              硬件层                                      │
│  用户按下按键 / 触摸屏幕                                                  │
│  → 硬件产生电信号                                                        │
│  → 触发 GPIO 中断 / I2C 数据传输                                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ ① 硬件中断
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            Kernel 层                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │  设备驱动    │───►│  Input Core  │───►│    evdev     │              │
│  │ (中断处理)   │    │ (input_event)│    │(/dev/input/) │              │
│  └──────────────┘    └──────────────┘    └──────────────┘              │
│                                                                         │
│  关键函数: input_report_key() / input_report_abs() → input_sync()      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ ② read() 系统调用
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       system_server 进程                                 │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                        Native 层                                  │  │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │  │
│  │  │  EventHub    │───►│ InputReader  │───►│InputDispatcher│──┐   │  │
│  │  │ (epoll监听)  │    │ (事件处理)   │    │  (事件分发)  │  │   │  │
│  │  └──────────────┘    └──────────────┘    └──────────────┘  │   │  │
│  │                                                             │   │  │
│  │  ③ 设备管理      ④ 事件加工        ⑤ 查找目标窗口        │   │  │
│  └─────────────────────────────────────────────────────────────┼───┘  │
│                                                                │      │
│  ┌──────────────────────────────────────────────────────────┐ │      │
│  │                      Framework 层 (Java)                  │ │      │
│  │  ┌──────────────┐    ┌──────────────┐                    │ │      │
│  │  │     IMS      │◄──►│     WMS      │                    │ │      │
│  │  └──────────────┘    └──────────────┘                    │ │      │
│  │  ⑥ 焦点管理、InputChannel 注册、按键拦截策略             │ │      │
│  └──────────────────────────────────────────────────────────┘ │      │
└───────────────────────────────────────────────────────────────┼──────┘
                                                                │
           ⑦ InputChannel (Socket) - 事件直接跨进程传输         │
           不经过 Java 层的 IMS/WMS                             │
                                                                │
┌───────────────────────────────────────────────────────────────┼──────┐
│                            应用进程                            │      │
│                                                                ▼      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐           │
│  │ ViewRootImpl │───►│  DecorView   │───►│   View/      │           │
│  │ (InputStage) │    │              │    │  ViewGroup   │           │
│  │              │    │              │    │              │           │
│  │ InputChannel │    │              │    │              │           │
│  │ (client 端)  │    │              │    │              │           │
│  └──────────────┘    └──────────────┘    └──────────────┘           │
│                                                                      │
│  ⑧ InputStage 链   ⑨ dispatchTouchEvent / dispatchKeyEvent         │
│                     onTouchEvent / onKeyDown                         │
└──────────────────────────────────────────────────────────────────────┘
```

> **重要说明**：InputDispatcher 通过 InputChannel (Socket) **直接**将事件发送到应用进程，
> 不经过 Java 层的 IMS/WMS。IMS/WMS 的作用是**建立 InputChannel 连接**和**焦点管理**，
> 而不是转发每个事件。这是 Android Input 系统低延迟的关键设计。详见 [19-Input事件分发通信与拦截机制](19-Input事件分发通信与拦截机制.md)。

---

## 2. 按键事件完整流程

以用户按下 **音量减键 (VOLUME_DOWN)** 为例：

### 2.1 Kernel 层处理

```
时间线
─────────────────────────────────────────────────────────────►

T0: 用户按下音量键
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ GPIO 驱动                                               │
│ gpio_keys_irq_isr() 中断服务程序                        │
│   → 读取 GPIO 电平                                      │
│   → 确定按键状态 (按下/释放)                            │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Input 子系统                                            │
│ input_report_key(input_dev, KEY_VOLUMEDOWN, 1)         │
│   → input_handle_event()                               │
│   → input_pass_values()                                │
│                                                         │
│ input_sync(input_dev)                                  │
│   → 产生 EV_SYN 事件                                   │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ evdev 驱动                                              │
│ evdev_event() → evdev_pass_event()                     │
│   → 将事件写入 evdev client 的环形缓冲区               │
│   → wake_up_interruptible() 唤醒等待的进程             │
│                                                         │
│ /dev/input/event0 可读                                 │
└─────────────────────────────────────────────────────────┘

事件序列:
  { type: EV_KEY,  code: KEY_VOLUMEDOWN, value: 1 }  // 按下
  { type: EV_SYN,  code: SYN_REPORT,     value: 0 }  // 同步
```

### 2.2 Native 层处理

```
┌─────────────────────────────────────────────────────────┐
│ EventHub::getEvents()                                   │
│ ─────────────────────                                   │
│ epoll_wait() 返回                                       │
│ read(fd, buffer, sizeof(input_event) * count)          │
│   → 读取 input_event 数组                              │
│   → 转换为 RawEvent                                    │
│   → 添加 deviceId                                      │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ InputReader::processEventsLocked()                      │
│ ──────────────────────────────────                      │
│ processEventsForDeviceLocked()                         │
│   → KeyboardInputMapper::process()                     │
│   → 硬件扫描码转换为 Android keyCode                   │
│   → 生成 NotifyKeyArgs                                 │
│                                                         │
│ NotifyKeyArgs {                                        │
│   action: AKEY_EVENT_ACTION_DOWN                       │
│   keyCode: AKEYCODE_VOLUME_DOWN                        │
│   scanCode: 114                                        │
│   ...                                                  │
│ }                                                      │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ InputDispatcher::notifyKey()                            │
│ ─────────────────────────────                           │
│ 1. 创建 KeyEntry                                        │
│ 2. 添加到 mInboundQueue                                │
│ 3. 唤醒分发线程                                        │
│                                                         │
│ dispatchOnce() → dispatchKeyLocked()                   │
│   → interceptKeyBeforeDispatching() (系统按键拦截)     │
│   → findFocusedWindowTargetLocked() (查找焦点窗口)     │
│   → dispatchEventLocked() (分发到目标)                 │
└────────────────────────────┬────────────────────────────┘
                             │ InputChannel
                             ▼
┌─────────────────────────────────────────────────────────┐
│ InputPublisher::publishKeyEvent()                       │
│ ────────────────────────────────                        │
│ 构建 InputMessage                                       │
│ 通过 Socket 发送到应用进程                              │
└─────────────────────────────────────────────────────────┘
```

### 2.3 应用层处理

```
┌─────────────────────────────────────────────────────────┐
│ InputConsumer (应用进程)                                │
│ ────────────────────────                                │
│ Looper::pollOnce() 检测到 InputChannel fd 可读         │
│ NativeInputEventReceiver::handleEvent()                │
│   → InputConsumer::consume()                           │
│   → 构建 KeyEvent 对象                                 │
└────────────────────────────┬────────────────────────────┘
                             │ JNI 回调
                             ▼
┌─────────────────────────────────────────────────────────┐
│ ViewRootImpl.WindowInputEventReceiver                   │
│ ──────────────────────────────────────                  │
│ onInputEvent(InputEvent event)                         │
│   → enqueueInputEvent()                                │
│   → deliverInputEvent()                                │
│   → InputStage 链式处理                                │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ InputStage 处理链                                       │
│ ────────────────────                                    │
│ 1. NativePreImeInputStage (Native 预处理)              │
│ 2. ViewPreImeInputStage (IME 之前的 View 处理)         │
│ 3. ImeInputStage (输入法处理)                          │
│ 4. EarlyPostImeInputStage (IME 之后的早期处理)         │
│ 5. NativePostImeInputStage (Native 后处理)             │
│ 6. ViewPostImeInputStage (View 事件分发)               │
│    → DecorView.dispatchKeyEvent()                      │
│    → Activity.dispatchKeyEvent()                       │
│    → PhoneWindow.onKeyDown()                           │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ 事件消费                                                │
│ ────────                                                │
│ 音量键被 PhoneWindowManager 拦截处理                   │
│   → AudioManager.adjustVolume()                        │
│                                                         │
│ 或者传递到 Activity.onKeyDown() 由应用处理             │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 触摸事件完整流程

以用户**点击屏幕**为例：

### 3.1 Kernel 层处理

```
T0: 用户触摸屏幕
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 触摸屏驱动                                              │
│ (I2C 中断 → 读取触摸数据)                              │
│                                                         │
│ 上报多点触摸事件:                                       │
│ input_mt_slot(input_dev, 0)           // 槽位 0        │
│ input_mt_report_slot_state(dev, MT_TOOL_FINGER, true)  │
│ input_report_abs(dev, ABS_MT_POSITION_X, x)            │
│ input_report_abs(dev, ABS_MT_POSITION_Y, y)            │
│ input_report_abs(dev, ABS_MT_PRESSURE, pressure)       │
│ input_mt_sync_frame(input_dev)                         │
│ input_sync(input_dev)                                  │
└─────────────────────────────────────────────────────────┘

事件序列 (单点触摸):
  { EV_ABS, ABS_MT_SLOT, 0 }
  { EV_ABS, ABS_MT_TRACKING_ID, 100 }
  { EV_ABS, ABS_MT_POSITION_X, 540 }
  { EV_ABS, ABS_MT_POSITION_Y, 960 }
  { EV_ABS, ABS_MT_PRESSURE, 50 }
  { EV_KEY, BTN_TOUCH, 1 }
  { EV_SYN, SYN_REPORT, 0 }
```

### 3.2 Native 层处理

```
┌─────────────────────────────────────────────────────────┐
│ EventHub                                                │
│ ────────                                                │
│ 读取原始事件序列                                        │
│ 转换为 RawEvent 数组                                   │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ InputReader → TouchInputMapper                          │
│ ──────────────────────────────                          │
│ 1. 累积触摸点数据                                       │
│ 2. 处理 SYN_REPORT 时合成事件                          │
│ 3. 坐标转换 (设备坐标 → 显示坐标)                      │
│    - 应用显示方向旋转                                  │
│    - 应用分辨率缩放                                    │
│ 4. 生成 NotifyMotionArgs                               │
│                                                         │
│ NotifyMotionArgs {                                     │
│   action: AMOTION_EVENT_ACTION_DOWN                    │
│   pointerCount: 1                                      │
│   pointerCoords[0]: { x: 540, y: 960, pressure: 0.5 }  │
│   source: AINPUT_SOURCE_TOUCHSCREEN                    │
│   displayId: 0                                         │
│ }                                                      │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ InputDispatcher                                         │
│ ───────────────                                         │
│ notifyMotion() → 创建 MotionEntry                      │
│                                                         │
│ dispatchMotionLocked():                                │
│ 1. 确定分发目标                                        │
│    - 计算触摸点坐标                                    │
│    - 遍历窗口栈 (从上到下)                             │
│    - 检查窗口可见性、可触摸区域                        │
│    - 找到命中的窗口                                    │
│                                                         │
│ 2. 权限检查                                            │
│    - 检查窗口是否可以接收输入                          │
│    - 检查是否被遮挡                                    │
│                                                         │
│ 3. 分发事件                                            │
│    - 创建 DispatchEntry                                │
│    - 加入目标窗口的 outbound queue                     │
│    - 通过 InputChannel 发送                            │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ InputPublisher::publishMotionEvent()                    │
│ ─────────────────────────────────────                   │
│ 序列化 MotionEntry → InputMessage                      │
│ socket send()                                          │
└─────────────────────────────────────────────────────────┘
```

### 3.3 应用层处理

```
┌─────────────────────────────────────────────────────────┐
│ InputConsumer → NativeInputEventReceiver               │
│ ──────────────────────────────────────                  │
│ 接收 InputMessage                                       │
│ 反序列化为 MotionEvent                                 │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ ViewRootImpl                                            │
│ ────────────                                            │
│ InputStage 链处理:                                      │
│ ... → ViewPostImeInputStage                            │
│                                                         │
│ processPointerEvent():                                 │
│   mView.dispatchPointerEvent(event)                    │
│     → DecorView.dispatchTouchEvent()                   │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ View 事件分发                                           │
│ ──────────────                                          │
│ DecorView.dispatchTouchEvent()                         │
│   → Activity.dispatchTouchEvent()                      │
│   → PhoneWindow.superDispatchTouchEvent()              │
│   → DecorView.superDispatchTouchEvent()                │
│   → ViewGroup.dispatchTouchEvent()                     │
│                                                         │
│ ViewGroup 分发逻辑:                                    │
│ 1. onInterceptTouchEvent() - 是否拦截                  │
│ 2. 遍历子 View (逆序, 从上到下)                        │
│ 3. 检查触摸点是否在子 View 区域内                      │
│ 4. 调用子 View.dispatchTouchEvent()                    │
│ 5. 如果没有子 View 处理, 调用自身 onTouchEvent()       │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│ View.onTouchEvent()                                     │
│ ────────────────────                                    │
│ 根据 clickable/longClickable 处理点击事件              │
│ ACTION_DOWN: 开始追踪, 设置 pressed 状态               │
│ ACTION_MOVE: 检查是否移出区域                          │
│ ACTION_UP: 触发 onClick() / performClick()             │
└─────────────────────────────────────────────────────────┘
```

---

## 4. 关键时序图

### 4.1 按键事件时序

```
┌──────┐    ┌──────┐    ┌────────┐    ┌───────────┐    ┌────────────┐    ┌────────┐
│Driver│    │evdev │    │EventHub│    │InputReader│    │InputDispatcher│  │App     │
└──┬───┘    └──┬───┘    └───┬────┘    └─────┬─────┘    └──────┬───────┘    └───┬────┘
   │           │            │               │                  │                │
   │ IRQ       │            │               │                  │                │
   ├──────────►│            │               │                  │                │
   │           │            │               │                  │                │
   │ input_event            │               │                  │                │
   │ ─────────►│            │               │                  │                │
   │           │ write to   │               │                  │                │
   │           │ buffer     │               │                  │                │
   │           │            │               │                  │                │
   │           │            │ epoll_wait()  │                  │                │
   │           │            │ returns       │                  │                │
   │           │            │◄──────────────│                  │                │
   │           │            │               │                  │                │
   │           │            │ RawEvent      │                  │                │
   │           │            │──────────────►│                  │                │
   │           │            │               │                  │                │
   │           │            │               │ NotifyKeyArgs    │                │
   │           │            │               │─────────────────►│                │
   │           │            │               │                  │                │
   │           │            │               │                  │ KeyEvent       │
   │           │            │               │                  │───────────────►│
   │           │            │               │                  │                │
   │           │            │               │                  │   finish()     │
   │           │            │               │                  │◄───────────────│
   │           │            │               │                  │                │
```

### 4.2 触摸事件时序

```
┌──────────┐    ┌────────┐    ┌───────────┐    ┌────────────┐    ┌───────┐
│TouchDriver│    │EventHub│    │InputReader│    │InputDispatcher│  │App    │
└─────┬────┘    └───┬────┘    └─────┬─────┘    └──────┬───────┘    └───┬───┘
      │             │               │                  │                │
      │ MT events   │               │                  │                │
      │ ──────────►│               │                  │                │
      │             │               │                  │                │
      │             │ RawEvent[]    │                  │                │
      │             │──────────────►│                  │                │
      │             │               │                  │                │
      │             │               │ process()        │                │
      │             │               │ 坐标转换         │                │
      │             │               │ 合成触摸点       │                │
      │             │               │                  │                │
      │             │               │ NotifyMotionArgs │                │
      │             │               │─────────────────►│                │
      │             │               │                  │                │
      │             │               │                  │ 查找目标窗口   │
      │             │               │                  │ 命中测试       │
      │             │               │                  │                │
      │             │               │                  │ MotionEvent    │
      │             │               │                  │───────────────►│
      │             │               │                  │                │
      │             │               │                  │                │ dispatch
      │             │               │                  │                │ TouchEvent
      │             │               │                  │                │
      │             │               │                  │   finish()     │
      │             │               │                  │◄───────────────│
      │             │               │                  │                │
```

---

## 5. 关键节点延迟分析

```
事件延迟组成
═══════════════════════════════════════════════════════════════════

┌─────────────────┐
│   硬件中断      │  ~ 0.1-1 ms
│   (IRQ 响应)    │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Kernel 处理    │  ~ 0.1-0.5 ms
│  (驱动+Input)   │
└────────┬────────┘
         ▼
┌─────────────────┐
│  EventHub 读取  │  ~ 1-2 ms (取决于 epoll 唤醒)
│  (系统调用)     │
└────────┬────────┘
         ▼
┌─────────────────┐
│  InputReader    │  ~ 0.1-0.5 ms
│  (事件处理)     │
└────────┬────────┘
         ▼
┌─────────────────┐
│  InputDispatcher│  ~ 0.5-2 ms
│  (分发+IPC)     │
└────────┬────────┘
         ▼
┌─────────────────┐
│  应用处理       │  ~ 1-16 ms (取决于应用)
│  (View 分发)    │
└─────────────────┘

总延迟: 通常 5-20 ms (从硬件中断到应用处理完成)
```

---

## 6. 本章小结

本文梳理了输入事件从硬件产生到应用处理的完整流程：

| 阶段 | 关键组件 | 主要工作 |
|-----|---------|---------|
| 硬件 | 驱动中断 | 电信号检测、数据读取 |
| Kernel | Input 子系统 | 事件标准化、evdev 上报 |
| Native | EventHub | 设备管理、事件读取 |
| Native | InputReader | 事件处理、坐标转换 |
| Native | InputDispatcher | 目标查找、事件分发 |
| Framework | IMS/WMS | 焦点管理、策略控制 |
| 应用 | InputStage | 链式处理、事件过滤 |
| 应用 | View | 事件分发、手势识别 |

下一篇将深入 Kernel Input 子系统的架构细节。

---

## 参考资料

1. Linux Input 子系统文档
2. Android InputFlinger 源码
3. ViewRootImpl 源码分析
