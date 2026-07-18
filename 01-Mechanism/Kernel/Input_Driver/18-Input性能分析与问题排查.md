# Input 性能分析与问题排查

## 引言

Input 系统的性能直接影响用户体验，触摸响应延迟、按键卡顿等问题都需要有效的工具和方法来分析排查。本文将介绍 Android Input 系统的常用调试工具和问题排查方法。

---

## 1. 调试工具概览

### 1.1 工具矩阵

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Input 调试工具                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  设备层调试                                                             │
│  ├── getevent: 读取原始输入事件                                        │
│  ├── sendevent: 注入输入事件                                           │
│  └── input: 模拟按键和触摸                                             │
│                                                                         │
│  系统层调试                                                             │
│  ├── dumpsys input: 输入系统状态                                       │
│  ├── dumpsys window: 窗口和焦点信息                                    │
│  └── adb shell wm: 显示信息                                            │
│                                                                         │
│  性能分析                                                               │
│  ├── systrace: 系统级追踪                                              │
│  ├── perfetto: 下一代追踪工具                                          │
│  └── simpleperf: CPU profiling                                         │
│                                                                         │
│  日志分析                                                               │
│  ├── logcat: 系统日志                                                  │
│  ├── bugreport: 完整诊断报告                                           │
│  └── traces.txt: ANR 堆栈                                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. getevent 工具

### 2.1 基本使用

```bash
# 列出所有输入设备
adb shell getevent -pl

# 输出示例:
# add device 1: /dev/input/event0
#   name:     "gpio-keys"
#   events:
#     KEY (0001): KEY_VOLUMEDOWN   KEY_VOLUMEUP    KEY_POWER
# add device 2: /dev/input/event1
#   name:     "touch_dev"
#   events:
#     ABS (0003): ABS_X  ABS_Y  ABS_PRESSURE  ABS_MT_SLOT  ...

# 监听所有事件 (十六进制)
adb shell getevent

# 监听所有事件 (可读格式)
adb shell getevent -lt

# 监听特定设备
adb shell getevent -lt /dev/input/event1
```

### 2.2 事件输出解读

```
# getevent -lt 输出示例

[  12345.678901] /dev/input/event1: EV_ABS       ABS_MT_SLOT          00000000
[  12345.678902] /dev/input/event1: EV_ABS       ABS_MT_TRACKING_ID   00000045
[  12345.678903] /dev/input/event1: EV_ABS       ABS_MT_POSITION_X    0000021c  (540)
[  12345.678904] /dev/input/event1: EV_ABS       ABS_MT_POSITION_Y    000003c0  (960)
[  12345.678905] /dev/input/event1: EV_ABS       ABS_MT_PRESSURE      00000032  (50)
[  12345.678906] /dev/input/event1: EV_KEY       BTN_TOUCH            DOWN
[  12345.678907] /dev/input/event1: EV_SYN       SYN_REPORT           00000000

# 格式: [时间戳] 设备: 事件类型 事件码 事件值

# 关键事件类型:
# EV_KEY (0001): 按键事件
# EV_ABS (0003): 绝对坐标 (触摸)
# EV_SYN (0000): 同步事件
```

### 2.3 分析触摸轨迹

```bash
# 提取触摸坐标
adb shell getevent -lt /dev/input/event1 | grep -E "ABS_MT_POSITION_[XY]"

# 分析触摸频率 (计算事件间隔)
adb shell getevent -t /dev/input/event1 | grep SYN_REPORT | \
    awk 'NR>1{print $1-prev; prev=$1}prev{prev=$1}'
```

---

## 3. dumpsys input

### 3.1 完整信息输出

```bash
adb shell dumpsys input
```

### 3.2 输出内容解析

```
INPUT MANAGER (dumpsys input)

Event Hub State:
  Devices:
    1: gpio-keys
      Classes: 0x00000001 (KEYBOARD)
      Path: /dev/input/event0
      ...
    2: touch_dev
      Classes: 0x00000014 (TOUCH | MULTI_TOUCH)
      Path: /dev/input/event1
      ...

Input Reader State:
  Input Devices:
    Device 1: gpio-keys
      Sources: 0x00000101 (KEYBOARD | DPAD)
      KeyboardType: non-alphabetic
      ...
    Device 2: touch_dev
      Sources: 0x00001002 (TOUCHSCREEN)
      ...

Input Dispatcher State:
  FocusedApplications:
    displayId=0, name='com.example.app/.MainActivity'
    
  FocusedWindows:
    displayId=0, name='com.example.app/com.example.app.MainActivity'
    
  TouchStates:
    displayId=0:
      windows:
        0: name='com.example.app/...', pointerIds=0x00000001, targetFlags=0x105
        
  Connections:
    0: channelName='com.example.app/...', windowName='...', status=NORMAL
       outboundQueue: <empty>
       waitQueue: <empty>
       
  AnrTracker:
    <empty>
    
  Configuration:
    KeyRepeatDelay: 50ms
    KeyRepeatTimeout: 50ms
```

### 3.3 关键信息

```bash
# 查看焦点窗口
adb shell dumpsys input | grep -A 5 "FocusedWindows"

# 查看触摸状态
adb shell dumpsys input | grep -A 10 "TouchStates"

# 查看连接状态 (检查 ANR)
adb shell dumpsys input | grep -A 5 "Connections"

# 查看 ANR 状态
adb shell dumpsys input | grep -A 5 "AnrTracker"
```

---

## 4. dumpsys window

### 4.1 窗口信息

```bash
# 完整窗口信息
adb shell dumpsys window

# 焦点信息
adb shell dumpsys window | grep -E "mCurrentFocus|mFocusedApp"

# 输入相关信息
adb shell dumpsys window input
```

### 4.2 输出示例

```
WINDOW MANAGER LAST ANR (dumpsys window lastanr)
  <no ANR recorded>

WINDOW MANAGER INPUT (dumpsys window input)
  mInputMethodTarget: Window{...}
  mInputMethodInputTarget: Window{...}
  
  Focus: Window{... com.example.app/com.example.app.MainActivity}
  
  TouchableWindows:
    Window{... NavigationBar}
      frame=[0,1920][1080,2000] visible=true
      touchRegion=[0,1920][1080,2000]
    Window{... com.example.app/com.example.app.MainActivity}
      frame=[0,0][1080,1920] visible=true
      touchRegion=[0,0][1080,1920]
```

---

## 5. Systrace / Perfetto

### 5.1 Systrace 使用

```bash
# 录制 Input 相关 trace
python systrace.py -a com.example.app -t 10 \
    input view gfx sched freq idle -o trace.html

# 关键 tag:
# input: Input 系统
# view: View 绘制
# gfx: 图形系统
# sched: 调度
```

### 5.2 Perfetto 使用

```bash
# 使用 Perfetto 录制 (推荐)
adb shell perfetto \
    -c - --txt \
    -o /data/misc/perfetto-traces/trace.perfetto-trace <<EOF

buffers: {
    size_kb: 63488
    fill_policy: DISCARD
}
buffers: {
    size_kb: 2048
    fill_policy: DISCARD
}
data_sources: {
    config {
        name: "linux.ftrace"
        ftrace_config {
            ftrace_events: "input/*"
            ftrace_events: "sched/*"
            atrace_categories: "input"
            atrace_categories: "view"
            atrace_categories: "gfx"
        }
    }
}
duration_ms: 10000
EOF

# 拉取并分析
adb pull /data/misc/perfetto-traces/trace.perfetto-trace
```

### 5.3 关键 Trace 点

```
Trace 分析要点:

1. 输入事件延迟
   - 从 EventHub.getEvents() 到应用 onTouchEvent()
   - 检查 InputReader/InputDispatcher 处理时间
   
2. 主线程阻塞
   - 检查 input 事件处理期间的其他工作
   - 查找长时间占用主线程的操作
   
3. 绘制延迟
   - 从 input 事件到 View.draw()
   - 检查 Choreographer doFrame
```

---

## 6. 日志分析

### 6.1 启用 Input 调试日志

```bash
# 启用 InputDispatcher 日志
adb shell setprop log.tag.InputDispatcher DEBUG

# 启用 InputReader 日志
adb shell setprop log.tag.InputReader DEBUG

# 启用 ViewRootImpl 日志
adb shell setprop log.tag.ViewRootImpl DEBUG

# 查看日志
adb logcat -v time | grep -E "InputDispatcher|InputReader|ViewRootImpl"
```

### 6.2 常见日志

```
# 事件分发日志
InputDispatcher: dispatchKey - eventTime=12345, deviceId=1, action=0, keyCode=4

# 焦点变化
InputDispatcher: Focus entering window 'com.example.app/...'

# ANR 相关
InputDispatcher: Application not responding: ...
InputDispatcher: Waiting because no window has focus but there is a focused application

# Touch 事件
InputReader: Touch event: x=540, y=960, pressure=50
```

---

## 7. 常见问题排查

### 7.1 触摸不响应

```
排查步骤:

1. 检查硬件事件
   $ adb shell getevent -lt
   - 确认触摸事件正常上报
   
2. 检查焦点窗口
   $ adb shell dumpsys input | grep FocusedWindows
   - 确认有正确的焦点窗口
   
3. 检查连接状态
   $ adb shell dumpsys input | grep -A 3 Connections
   - 检查 status 是否为 NORMAL
   - 检查 waitQueue 是否有积压
   
4. 检查窗口可见性
   $ adb shell dumpsys window | grep visible
   - 确认目标窗口可见
   
5. 检查主线程状态
   $ adb shell kill -3 <pid>  # 生成 traces
   - 分析主线程是否阻塞
```

### 7.2 触摸延迟

```
排查步骤:

1. 测量延迟
   - 使用高速摄像机
   - 或使用 Systrace 测量
   
2. 分析延迟来源
   - Kernel 到 EventHub: getevent 时间戳
   - EventHub 到应用: Systrace
   - 应用处理时间: 方法耗时
   
3. 优化点
   - 减少主线程工作
   - 避免在 onTouchEvent 中执行耗时操作
   - 考虑使用 InputChannel 批处理
```

### 7.3 Input ANR 分析

```
排查步骤:

1. 获取 ANR traces
   $ adb pull /data/anr/traces.txt
   
2. 分析主线程状态
   - 查看 "main" 线程的调用栈
   - 查看线程状态 (Sleeping/Waiting/Blocked/Native)
   
3. 常见原因
   - 主线程执行耗时操作
   - 死锁
   - Binder 调用阻塞
   - IO 操作
   
4. 使用 dumpsys input 检查
   - 查看 AnrTracker
   - 查看 waitQueue 中的事件
```

### 7.4 按键无响应

```
排查步骤:

1. 检查按键事件
   $ adb shell getevent -lt | grep KEY
   - 确认按键正常上报
   
2. 检查按键映射
   $ adb shell dumpsys input | grep -A 10 "Key Layout"
   - 确认按键码映射正确
   
3. 检查策略拦截
   - PhoneWindowManager 可能拦截系统按键
   - 检查 interceptKeyBeforeQueueing 返回值
   
4. 检查焦点
   $ adb shell dumpsys input | grep FocusedWindows
   - 按键发送给焦点窗口
```

---

## 8. 性能优化建议

### 8.1 应用层优化

```java
// 1. 避免在触摸回调中执行耗时操作
@Override
public boolean onTouchEvent(MotionEvent event) {
    // 快速返回
    if (event.getAction() == MotionEvent.ACTION_DOWN) {
        // 异步处理
        executor.execute(() -> doHeavyWork());
    }
    return true;
}

// 2. 使用 VelocityTracker 时及时回收
@Override
public boolean onTouchEvent(MotionEvent event) {
    if (event.getAction() == MotionEvent.ACTION_UP) {
        mVelocityTracker.recycle();
        mVelocityTracker = null;
    }
}

// 3. 避免创建大量临时对象
// 复用 PointF, RectF 等对象
private final PointF mTempPoint = new PointF();
```

### 8.2 View 层优化

```java
// 1. 避免不必要的 requestLayout
@Override
public boolean onTouchEvent(MotionEvent event) {
    // 只改变绘制, 使用 invalidate
    invalidate();
    // 而非 requestLayout()
}

// 2. 使用 setWillNotDraw(false) 时注意性能
// 3. 考虑使用 SurfaceView 处理高频绘制
```

### 8.3 系统层建议

```
1. 触摸屏驱动优化
   - 减少中断到事件上报的延迟
   - 使用批量上报
   
2. InputFlinger 配置
   - 调整 InputDispatcher 超时
   - 优化窗口查找算法
   
3. 减少 Binder 调用
   - 批量更新窗口信息
   - 缓存常用查询结果
```

---

## 9. 本章小结

Input 调试工具和方法：

| 工具 | 用途 |
|-----|------|
| getevent | 原始事件监控 |
| dumpsys input | 系统状态查看 |
| dumpsys window | 窗口焦点信息 |
| Systrace/Perfetto | 性能追踪 |
| logcat | 日志分析 |

问题排查流程：
1. 确认硬件事件正常 (getevent)
2. 检查焦点和窗口状态 (dumpsys)
3. 分析延迟来源 (Systrace)
4. 查看主线程状态 (traces.txt)

优化要点：
1. 主线程不做耗时操作
2. 及时回收资源
3. 减少不必要的 requestLayout
4. 使用异步处理

---

## 参考资料

1. Android Input 调试官方文档
2. Systrace 使用指南
3. Perfetto 官方文档
4. Android 性能优化指南
