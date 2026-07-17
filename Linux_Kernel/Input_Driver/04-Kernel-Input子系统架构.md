# Kernel Input 子系统架构

## 引言

Linux Input 子系统是 Android 输入事件的源头，它提供了统一的框架来处理各种输入设备（键盘、鼠标、触摸屏、游戏手柄等）。本文将深入分析 Input 子系统的架构设计、核心组件和事件流转机制。

---

## 1. Input 子系统架构总览

### 1.1 三层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          用户空间                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │   /dev/input/event0   event1   event2   ...                 │   │
│  └───────────────────────────────┬─────────────────────────────┘   │
└──────────────────────────────────┼──────────────────────────────────┘
                                   │ read() / ioctl()
┌──────────────────────────────────┼──────────────────────────────────┐
│                                  ▼                                  │
│                         事件处理层 (Handler)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │   evdev     │  │  keyboard   │  │   mousedev  │                 │
│  │ (通用事件)  │  │  (键盘)     │  │   (鼠标)    │                 │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │
│         │                │                │                        │
│         └────────────────┼────────────────┘                        │
│                          │ input_handler 注册                      │
│  ┌───────────────────────▼───────────────────────────────────────┐ │
│  │                     Input Core                                │ │
│  │                   (input.c / input.h)                         │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │  input_dev 链表  │  input_handler 链表  │  handle 连接   │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────▲───────────────────────────────────────┘ │
│                          │ input_register_device()                 │
│  ┌───────────────────────┴───────────────────────────────────────┐ │
│  │                     设备驱动层 (Driver)                        │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │ │
│  │  │  gpio-keys  │  │ touchscreen │  │  keyboard   │           │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘           │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                               内核空间                              │
└─────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │ 中断 / I2C / SPI
┌─────────────────────────────────────────────────────────────────────┐
│                              硬件层                                  │
│     GPIO 按键  │  触摸屏控制器  │  USB 键盘  │  蓝牙遥控器          │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计理念

| 设计原则 | 实现方式 |
|---------|---------|
| 设备无关性 | 统一的 input_event 结构 |
| 可扩展性 | input_handler 可插拔注册 |
| 多路复用 | 一个设备可连接多个 handler |
| 高效传输 | 环形缓冲区、批量读取 |

---

## 2. 核心数据结构

### 2.1 input_dev - 输入设备

```c
// include/linux/input.h
struct input_dev {
    const char *name;           // 设备名称
    const char *phys;           // 物理路径 (如 "usb-0000:00:1d.0-1/input0")
    const char *uniq;           // 唯一标识符
    struct input_id id;         // 设备 ID
    
    // 设备能力位图
    unsigned long evbit[BITS_TO_LONGS(EV_CNT)];    // 支持的事件类型
    unsigned long keybit[BITS_TO_LONGS(KEY_CNT)];  // 支持的按键
    unsigned long relbit[BITS_TO_LONGS(REL_CNT)];  // 支持的相对轴
    unsigned long absbit[BITS_TO_LONGS(ABS_CNT)];  // 支持的绝对轴
    unsigned long mscbit[BITS_TO_LONGS(MSC_CNT)];  // 支持的杂项事件
    unsigned long ledbit[BITS_TO_LONGS(LED_CNT)];  // 支持的 LED
    unsigned long sndbit[BITS_TO_LONGS(SND_CNT)];  // 支持的声音
    unsigned long ffbit[BITS_TO_LONGS(FF_CNT)];    // 支持的力反馈
    unsigned long swbit[BITS_TO_LONGS(SW_CNT)];    // 支持的开关
    
    // 绝对轴信息
    struct input_absinfo *absinfo;
    
    // 按键状态
    unsigned long key[BITS_TO_LONGS(KEY_CNT)];     // 当前按键状态
    unsigned long led[BITS_TO_LONGS(LED_CNT)];     // 当前 LED 状态
    unsigned long sw[BITS_TO_LONGS(SW_CNT)];       // 当前开关状态
    
    // 回调函数
    int (*open)(struct input_dev *dev);            // 设备打开
    void (*close)(struct input_dev *dev);          // 设备关闭
    int (*flush)(struct input_dev *dev, struct file *file);
    int (*event)(struct input_dev *dev, unsigned int type,
                 unsigned int code, int value);    // 事件处理 (LED/FF)
    
    // 连接的 handle 链表
    struct list_head h_list;
    struct list_head node;      // 全局 input_dev 链表节点
    
    unsigned int users;         // 打开计数
    bool going_away;
    
    struct device dev;          // 设备模型
    // ...
};
```

### 2.2 input_handler - 事件处理器

```c
struct input_handler {
    void *private;
    
    // 事件处理回调
    void (*event)(struct input_handle *handle,
                  unsigned int type, unsigned int code, int value);
    void (*events)(struct input_handle *handle,
                   const struct input_value *vals, unsigned int count);
    
    // 过滤器 (返回 true 表示过滤掉事件)
    bool (*filter)(struct input_handle *handle,
                   unsigned int type, unsigned int code, int value);
    
    // 设备匹配和连接
    bool (*match)(struct input_handler *handler, struct input_dev *dev);
    int (*connect)(struct input_handler *handler, struct input_dev *dev,
                   const struct input_device_id *id);
    void (*disconnect)(struct input_handle *handle);
    void (*start)(struct input_handle *handle);
    
    // 文件操作 (用于字符设备)
    const struct file_operations *fops;
    int minor;                  // 次设备号基址
    const char *name;           // handler 名称
    
    // 匹配的设备 ID 表
    const struct input_device_id *id_table;
    
    struct list_head h_list;    // handle 链表
    struct list_head node;      // 全局 handler 链表节点
};
```

### 2.3 input_handle - 连接桥梁

```c
struct input_handle {
    void *private;              // 私有数据
    
    int open;                   // 打开计数
    const char *name;           // handle 名称
    
    struct input_dev *dev;      // 关联的 input_dev
    struct input_handler *handler;  // 关联的 handler
    
    struct list_head d_node;    // input_dev 的 handle 链表节点
    struct list_head h_node;    // input_handler 的 handle 链表节点
};
```

### 2.4 三者关系图

```
              input_handler                         input_handler
             (evdev)                               (keyboard)
                │                                      │
      ┌─────────┼─────────┐                  ┌─────────┼─────────┐
      │         │         │                  │         │         │
      ▼         ▼         ▼                  ▼         ▼         ▼
   handle    handle    handle             handle    handle    handle
      │         │         │                  │         │         │
      │         │         │                  │         │         │
      ▼         ▼         ▼                  ▼         ▼         ▼
 input_dev  input_dev  input_dev        input_dev  input_dev  input_dev
(touchscreen)(keyboard) (mouse)        (touchscreen)(keyboard) (mouse)

说明:
- 一个 input_dev 可以连接多个 handler (通过多个 handle)
- 一个 handler 可以处理多个 input_dev (通过多个 handle)
- handle 是 input_dev 和 handler 之间的连接
```

---

## 3. evdev 驱动详解

evdev 是 Android 使用的主要事件处理器，它为每个输入设备创建 `/dev/input/eventX` 字符设备。

### 3.1 evdev 架构

```
用户空间
                      ┌───────────────────────────────────────┐
                      │        /dev/input/event0              │
                      │   open() / read() / ioctl() / poll()  │
                      └─────────────────┬─────────────────────┘
                                        │
内核空间                                │
┌───────────────────────────────────────┼───────────────────────────────────┐
│                                       ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                            evdev.c                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────┐    │ │
│  │  │  evdev_handler (input_handler)                              │    │ │
│  │  │  - .event = evdev_event                                     │    │ │
│  │  │  - .connect = evdev_connect                                 │    │ │
│  │  │  - .fops = &evdev_fops                                      │    │ │
│  │  └─────────────────────────────────────────────────────────────┘    │ │
│  │                                                                      │ │
│  │  ┌─────────────────────────────────────────────────────────────┐    │ │
│  │  │  evdev (每个设备一个)                                        │    │ │
│  │  │  - handle (连接到 input_dev)                                │    │ │
│  │  │  - client_list (打开该设备的客户端列表)                     │    │ │
│  │  │  - cdev (字符设备)                                          │    │ │
│  │  └─────────────────────────────────────────────────────────────┘    │ │
│  │                                                                      │ │
│  │  ┌─────────────────────────────────────────────────────────────┐    │ │
│  │  │  evdev_client (每个 open 一个)                               │    │ │
│  │  │  - buffer[EVDEV_BUF_PACKETS] (环形缓冲区)                   │    │ │
│  │  │  - head, tail (缓冲区指针)                                   │    │ │
│  │  │  - wait (等待队列)                                           │    │ │
│  │  └─────────────────────────────────────────────────────────────┘    │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────┘
```

### 3.2 evdev 核心代码分析

```c
// drivers/input/evdev.c

// evdev 设备结构
struct evdev {
    int open;                       // 打开计数
    struct input_handle handle;     // 与 input_dev 的连接
    wait_queue_head_t wait;         // 等待队列
    struct evdev_client __rcu *grab;// 独占客户端
    struct list_head client_list;   // 客户端链表
    spinlock_t client_lock;
    struct mutex mutex;
    struct device dev;              // 设备
    struct cdev cdev;               // 字符设备
    bool exist;
};

// 客户端结构 (每次 open 创建一个)
struct evdev_client {
    unsigned int head;              // 环形缓冲区头
    unsigned int tail;              // 环形缓冲区尾
    unsigned int packet_head;       // 当前包的头
    spinlock_t buffer_lock;
    struct fasync_struct *fasync;
    struct evdev *evdev;
    struct list_head node;
    unsigned int clk_type;
    bool revoked;
    unsigned long *evmasks[EV_CNT]; // 事件过滤掩码
    unsigned int bufsize;           // 缓冲区大小
    struct input_event buffer[];    // 环形缓冲区
};

// 连接回调 - 当匹配到新设备时调用
static int evdev_connect(struct input_handler *handler, struct input_dev *dev,
                         const struct input_device_id *id)
{
    struct evdev *evdev;
    int minor;
    int dev_no;
    int error;
    
    // 分配次设备号
    minor = input_get_new_minor(EVDEV_MINOR_BASE, EVDEV_MINORS, true);
    
    // 分配 evdev 结构
    evdev = kzalloc(sizeof(struct evdev), GFP_KERNEL);
    
    // 初始化
    INIT_LIST_HEAD(&evdev->client_list);
    init_waitqueue_head(&evdev->wait);
    evdev->exist = true;
    
    // 设置 handle
    evdev->handle.dev = input_get_device(dev);
    evdev->handle.name = dev_name(&evdev->dev);
    evdev->handle.handler = handler;
    evdev->handle.private = evdev;
    
    // 创建字符设备 /dev/input/eventX
    cdev_init(&evdev->cdev, &evdev_fops);
    error = cdev_device_add(&evdev->cdev, &evdev->dev);
    
    // 注册 handle
    error = input_register_handle(&evdev->handle);
    
    return 0;
}

// 事件回调 - 当 input_dev 上报事件时调用
static void evdev_event(struct input_handle *handle,
                        unsigned int type, unsigned int code, int value)
{
    struct input_value vals[] = { { type, code, value } };
    evdev_events(handle, vals, 1);
}

static void evdev_events(struct input_handle *handle,
                         const struct input_value *vals, unsigned int count)
{
    struct evdev *evdev = handle->private;
    struct evdev_client *client;
    ktime_t time_mono, time_real;
    
    // 获取时间戳
    time_mono = ktime_get();
    time_real = ktime_mono_to_real(time_mono);
    
    // 遍历所有客户端, 传递事件
    rcu_read_lock();
    list_for_each_entry_rcu(client, &evdev->client_list, node)
        evdev_pass_values(client, vals, count, time_mono, time_real);
    rcu_read_unlock();
}

// 将事件写入客户端缓冲区
static void evdev_pass_values(struct evdev_client *client,
                              const struct input_value *vals, unsigned int count,
                              ktime_t mono, ktime_t real)
{
    struct evdev *evdev = client->evdev;
    const struct input_value *v;
    struct input_event event;
    struct timespec64 ts;
    bool wakeup = false;
    
    // 转换时间戳
    ts = ktime_to_timespec64(client->clk_type == CLOCK_REALTIME ? real : mono);
    event.input_event_sec = ts.tv_sec;
    event.input_event_usec = ts.tv_nsec / NSEC_PER_USEC;
    
    spin_lock(&client->buffer_lock);
    
    for (v = vals; v != vals + count; v++) {
        // 检查事件过滤
        if (__evdev_is_filtered(client, v->type, v->code))
            continue;
        
        // 检查缓冲区溢出
        if (client->head - client->tail >= client->bufsize) {
            // 缓冲区满, 丢弃最旧的事件
            client->tail++;
        }
        
        // 写入事件
        event.type = v->type;
        event.code = v->code;
        event.value = v->value;
        client->buffer[client->head++ % client->bufsize] = event;
        
        // SYN_REPORT 标记一组事件结束
        if (v->type == EV_SYN && v->code == SYN_REPORT) {
            client->packet_head = client->head;
            wakeup = true;
        }
    }
    
    spin_unlock(&client->buffer_lock);
    
    // 唤醒等待的进程
    if (wakeup)
        wake_up_interruptible(&evdev->wait);
}
```

### 3.3 读取事件流程

```c
// evdev_read - 用户空间读取事件
static ssize_t evdev_read(struct file *file, char __user *buffer,
                          size_t count, loff_t *ppos)
{
    struct evdev_client *client = file->private_data;
    struct evdev *evdev = client->evdev;
    struct input_event event;
    size_t read = 0;
    int error;
    
    // 检查读取大小
    if (count != 0 && count < input_event_size())
        return -EINVAL;
    
    for (;;) {
        // 检查设备是否存在
        if (!evdev->exist || client->revoked)
            return -ENODEV;
        
        // 尝试读取事件
        while (read + input_event_size() <= count) {
            error = evdev_fetch_next_event(client, &event);
            if (error)
                break;
            
            // 复制到用户空间
            if (input_event_to_user(buffer + read, &event))
                return -EFAULT;
            
            read += input_event_size();
        }
        
        if (read)
            return read;
        
        // 非阻塞模式
        if (file->f_flags & O_NONBLOCK)
            return -EAGAIN;
        
        // 阻塞等待事件
        error = wait_event_interruptible(evdev->wait,
                    client->packet_head != client->tail ||
                    !evdev->exist || client->revoked);
        if (error)
            return error;
    }
}

// 从环形缓冲区获取下一个事件
static int evdev_fetch_next_event(struct evdev_client *client,
                                  struct input_event *event)
{
    spin_lock_irq(&client->buffer_lock);
    
    // 检查是否有完整的事件包
    if (client->packet_head == client->tail) {
        spin_unlock_irq(&client->buffer_lock);
        return -EAGAIN;
    }
    
    // 读取事件
    *event = client->buffer[client->tail++ % client->bufsize];
    
    spin_unlock_irq(&client->buffer_lock);
    return 0;
}
```

---

## 4. Input Core 事件上报

### 4.1 事件上报 API

```c
// 上报按键事件
static inline void input_report_key(struct input_dev *dev, 
                                    unsigned int code, int value)
{
    input_event(dev, EV_KEY, code, !!value);
}

// 上报绝对坐标
static inline void input_report_abs(struct input_dev *dev,
                                    unsigned int code, int value)
{
    input_event(dev, EV_ABS, code, value);
}

// 上报相对位移
static inline void input_report_rel(struct input_dev *dev,
                                    unsigned int code, int value)
{
    input_event(dev, EV_REL, code, value);
}

// 同步事件 (标记一组事件结束)
static inline void input_sync(struct input_dev *dev)
{
    input_event(dev, EV_SYN, SYN_REPORT, 0);
}

// 多点触摸同步
static inline void input_mt_sync(struct input_dev *dev)
{
    input_event(dev, EV_SYN, SYN_MT_REPORT, 0);
}
```

### 4.2 核心事件处理函数

```c
// drivers/input/input.c

void input_event(struct input_dev *dev,
                 unsigned int type, unsigned int code, int value)
{
    unsigned long flags;
    
    // 检查设备是否支持该事件类型
    if (is_event_supported(type, dev->evbit, EV_MAX)) {
        spin_lock_irqsave(&dev->event_lock, flags);
        input_handle_event(dev, type, code, value);
        spin_unlock_irqrestore(&dev->event_lock, flags);
    }
}

static void input_handle_event(struct input_dev *dev,
                               unsigned int type, unsigned int code, int value)
{
    int disposition = input_get_disposition(dev, type, code, &value);
    
    // 检查事件是否有效
    if (disposition != INPUT_IGNORE_EVENT) {
        // 更新设备状态
        if (type == EV_KEY)
            __change_bit(code, dev->key);
        else if (type == EV_SW)
            __change_bit(code, dev->sw);
        // ...
        
        // 传递给所有连接的 handler
        if (disposition & INPUT_PASS_TO_HANDLERS) {
            struct input_value *v;
            
            // 添加到缓存
            v = &dev->vals[dev->num_vals++];
            v->type = type;
            v->code = code;
            v->value = value;
        }
        
        // SYN_REPORT 时刷新缓存
        if (disposition & INPUT_FLUSH) {
            input_pass_values(dev, dev->vals, dev->num_vals);
            dev->num_vals = 0;
        }
    }
}

// 将事件传递给所有连接的 handler
static void input_pass_values(struct input_dev *dev,
                              struct input_value *vals, unsigned int count)
{
    struct input_handle *handle;
    
    // 遍历所有连接的 handle
    list_for_each_entry_rcu(handle, &dev->h_list, d_node) {
        if (!handle->open)
            continue;
        
        struct input_handler *handler = handle->handler;
        
        // 调用 handler 的事件回调
        if (handler->events)
            handler->events(handle, vals, count);
        else if (handler->event) {
            for (int i = 0; i < count; i++)
                handler->event(handle, vals[i].type, 
                              vals[i].code, vals[i].value);
        }
    }
}
```

---

## 5. 多点触摸协议

### 5.1 Type A 和 Type B 协议

```
Type A (已弃用) - 无槽位追踪
──────────────────────────────────────
ABS_MT_POSITION_X   x1
ABS_MT_POSITION_Y   y1
SYN_MT_REPORT           // 分隔点
ABS_MT_POSITION_X   x2
ABS_MT_POSITION_Y   y2
SYN_MT_REPORT
SYN_REPORT              // 帧结束


Type B (推荐) - 槽位追踪
──────────────────────────────────────
ABS_MT_SLOT         0
ABS_MT_TRACKING_ID  45   // 分配追踪 ID
ABS_MT_POSITION_X   x1
ABS_MT_POSITION_Y   y1
ABS_MT_SLOT         1
ABS_MT_TRACKING_ID  46
ABS_MT_POSITION_X   x2
ABS_MT_POSITION_Y   y2
SYN_REPORT

// 释放第一个触摸点
ABS_MT_SLOT         0
ABS_MT_TRACKING_ID  -1   // -1 表示释放
SYN_REPORT
```

### 5.2 MT 辅助函数

```c
// 分配/获取槽位
int input_mt_get_slot_by_key(struct input_dev *dev, int key);

// 设置槽位
void input_mt_slot(struct input_dev *dev, int slot);

// 报告槽位状态
void input_mt_report_slot_state(struct input_dev *dev,
                                unsigned int tool_type, bool active);

// 同步帧
void input_mt_sync_frame(struct input_dev *dev);

// 使用示例
void report_touch(struct input_dev *dev, int id, int x, int y, bool active)
{
    int slot = input_mt_get_slot_by_key(dev, id);
    if (slot < 0)
        return;
    
    input_mt_slot(dev, slot);
    input_mt_report_slot_state(dev, MT_TOOL_FINGER, active);
    
    if (active) {
        input_report_abs(dev, ABS_MT_POSITION_X, x);
        input_report_abs(dev, ABS_MT_POSITION_Y, y);
    }
}

// 在帧结束时
input_mt_sync_frame(dev);
input_sync(dev);
```

---

## 6. 本章小结

本文介绍了 Kernel Input 子系统的核心架构：

| 组件 | 职责 |
|-----|------|
| input_dev | 输入设备抽象，定义设备能力 |
| input_handler | 事件处理器，evdev 为主 |
| input_handle | 连接 dev 和 handler |
| evdev | 创建 /dev/input/eventX，事件缓冲 |

关键流程：
1. 驱动调用 `input_event()` 上报事件
2. Input Core 传递给所有连接的 handler
3. evdev 将事件写入客户端缓冲区
4. 用户空间通过 `read()` 获取事件

下一篇将详细介绍具体的输入设备驱动实现。

---

## 参考资料

1. `Documentation/input/` - Linux Input 文档
2. `drivers/input/input.c` - Input Core 实现
3. `drivers/input/evdev.c` - evdev 实现
