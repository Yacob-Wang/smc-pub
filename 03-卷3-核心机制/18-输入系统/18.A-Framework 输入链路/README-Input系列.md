# 面向稳定性的 Input 系统深度解析系列

## 为什么要写这个系列

Input 系统是 Android 的"感觉神经"。**用户的每一次触摸、每一次滑动、每一次按键，都必须经过 Input 系统的五层架构，从硬件中断一路传递到 App 的 `onTouchEvent`。** 任何一个环节出问题，用户感知就是"点了没反应"或"滑动卡顿"。

对于稳定性架构师来说，Input 系统的重要性在于：

- **ANR 的头号来源**：Input ANR 占线上 ANR 总量的 60% 以上。理解 InputDispatcher 的超时检测逻辑，是 ANR 归因的基础。
- **用户体验的最前线**：触摸延迟超过 100ms，用户就能明显感知。从 EventHub 到 View.onTouchEvent 的每一毫秒都影响体验。
- **跨层问题的交汇点**：Input 系统跨越 Kernel → Native → Framework → App 四大层，问题可能出在任何一层。
- **与 Handler/Binder/WMS 深度耦合**：Input 事件通过 Looper fd 注入主线程、通过 WMS 获取窗口信息、ANR 由 AMS 处理——所有核心模块在此交汇。

本系列的目标：**让你理解从硬件中断到 App 响应的完整链路，能从 `dumpsys input` / ANR trace / Systrace 中快速定位 Input 相关问题的根因，并建立有效的触摸延迟监控与治理体系。**

## 系列设计思路

```
Input 系统是什么？为什么 Android 需要如此复杂的五层架构？（定位）
    ↓
事件从硬件中断到 App 响应的完整链路是什么？跨越了哪些进程和线程？（边界与交互）
    ↓
InputReader 如何读取事件？InputDispatcher 如何选择目标窗口？InputChannel 如何跨进程投递？（核心机制）
    ↓
Input ANR 是怎么发生的？事件丢失、触摸延迟、事件冲突各是什么原因？（风险地图）
    ↓
怎么用 dumpsys input / getevent / Systrace 排查？怎么建延迟监控体系？（诊断与治理）
```

---

## 第一篇章：建立全局观（1 篇）

> 核心问题：Input 系统是什么？一次触摸事件经历了哪些环节？为什么需要如此复杂的架构？

### [01-Input 系统总览：从触摸屏到 App 响应的全链路](01-Input系统总览.md)


| 章节                 | 内容                                                                                     | 核心源码路径                                     | 稳定性关联             |
| ------------------ | -------------------------------------------------------------------------------------- | ------------------------------------------ | ----------------- |
| **1. Input 系统是什么** | 触摸/按键/传感器事件从硬件到应用的完整处理管线                                                               | —                                          | "一切触摸皆 Input"     |
| **2. 为什么需要五层架构**   | 安全隔离、多窗口仲裁、ANR 检测三大设计驱动力                                                               | —                                          | 架构决定了问题排查的层次      |
| **3. 五层架构全景图**     | Kernel → EventHub → InputReader → InputDispatcher → InputChannel → ViewRootImpl → View | `frameworks/native/services/inputflinger/` | 出问题时定位在哪一层        |
| **4. 一次触摸事件的完整旅程** | 从硬件中断到 `onTouchEvent` 的全链路概要                                                           | 多个目录                                       | 建立端到端的心智模型        |
| **5. 进程与线程模型**     | InputReaderThread / InputDispatcherThread / App 主线程的分工                                 | `InputManager.cpp`                         | 线程阻塞 → 事件延迟       |
| **6. 与其他模块的交互**    | WMS（窗口列表）、AMS（ANR）、Choreographer（VSync）、IME（输入法）                                       | 多个目录                                       | Input 是系统模块的"交汇点" |
| **7. 核心源码目录**      | inputflinger / InputManagerService / View 等目录速查                                        | 多个目录                                       | 排查问题时的"导航地图"      |


---

## 第二篇章：核心机制深潜（5 篇）

> 核心问题：EventHub 如何读取硬件事件？InputDispatcher 如何选择窗口？InputChannel 如何跨进程传输？View 树如何分发事件？Input ANR 如何检测？

### [02-EventHub 与 InputReader：从硬件中断到原始事件](02-EventHub与InputReader.md)


| 章节                      | 内容                                                         | 核心源码路径                 | 稳定性关联                  |
| ----------------------- | ---------------------------------------------------------- | ---------------------- | ---------------------- |
| **1. EventHub**         | Linux Input 子系统封装；epoll 监听 `/dev/input/eventX`             | `EventHub.cpp`         | epoll fd 泄漏 → 设备不响应    |
| **2. getEvents()**      | epoll_wait → 读取 input_event → 设备热插拔（inotify）               | `EventHub.cpp`         | 驱动延迟 → 触摸延迟源头          |
| **3. InputReader**      | 原始事件 → Android 语义事件（MotionEvent/KeyEvent）                  | `InputReader.cpp`      | InputReader 处理慢 → 事件积压 |
| **4. loopOnce()**       | getEvents → processEventsLocked → InputMapper → NotifyArgs | `InputReader.cpp`      | 理解事件转换管线               |
| **5. TouchInputMapper** | 多点触控 Slot 协议、坐标变换、手势状态机                                    | `TouchInputMapper.cpp` | 坐标映射错误 → 触摸偏移          |
| **6. 设备配置**             | `.idc` / `.kl` / `.kcm` 文件解析；设备能力检测                        | `EventHub.cpp`         | 配置错误 → 按键映射异常          |


### [03-InputDispatcher：事件分发引擎与窗口选择](03-InputDispatcher.md)


| 章节                    | 内容                                                                                        | 核心源码路径                | 稳定性关联             |
| --------------------- | ----------------------------------------------------------------------------------------- | --------------------- | ----------------- |
| **1. Dispatcher 是什么** | Input 系统的"大脑"：决定事件发给谁、何时发、发不出怎么办                                                          | —                     | 理解分发逻辑是排查 ANR 的前提 |
| **2. dispatchOnce()** | mInboundQueue → dispatch*Locked → findTargets → dispatchEvent → InputChannel::sendMessage | `InputDispatcher.cpp` | 分发流程的每一步都可能延迟     |
| **3. 窗口选择**           | findTouchedWindowTargetsLocked：Z-order 遍历 → 命中测试 → FLAG 检查                                | `InputDispatcher.cpp` | 窗口遮挡 → 事件发给错误窗口   |
| **4. 焦点管理**           | FocusedApplication / FocusedWindow 的设置与切换                                                 | `InputDispatcher.cpp` | 焦点丢失 → 按键事件无处可发   |
| **5. ANR 超时检测**       | 发送事件后 5 秒倒计时；checkWindowReadyForMoreInputLocked                                           | `InputDispatcher.cpp` | Input ANR 的"审判官"  |
| **6. onANR 回调链**      | onAnrLocked → IMS.notifyANR → AMS.inputDispatchingTimedOut                                | `InputDispatcher.cpp` | ANR 从检测到处理的完整链路   |


### [04-InputChannel 与跨进程投递：从 system_server 到 App](04-InputChannel与跨进程投递.md)


| 章节                      | 内容                                                                  | 核心源码路径                    | 稳定性关联                   |
| ----------------------- | ------------------------------------------------------------------- | ------------------------- | ----------------------- |
| **1. InputChannel 是什么** | Unix Domain Socket（socketpair）；server 端 + client 端                  | `InputTransport.cpp`      | 理解跨进程事件传输               |
| **2. 创建时机**             | ViewRootImpl.setView → WMS.addWindow → IMS.registerInputChannel     | `InputTransport.cpp`      | 窗口注册失败 → 事件无法投递         |
| **3. 事件序列化**            | InputMessage 结构体 → sendMessage / receiveMessage → socket read/write | `InputTransport.cpp`      | socket buffer 满 → 事件积压  |
| **4. App 端接收**          | WindowInputEventReceiver → InputChannel fd 注册到 NativeLooper → 回调    | `InputEventReceiver.java` | fd 未注册 → 事件无法接收         |
| **5. finishInputEvent** | App 处理完回复 → InputDispatcher 取消 ANR 倒计时                              | `InputTransport.cpp`      | 回复不及时 → Input ANR       |
| **6. Connection 对象**    | outboundQueue / waitQueue 的管理；串行化投递策略                               | `InputDispatcher.cpp`     | waitQueue 堆积 → 后续事件全部延迟 |


### [05-View 事件分发：从 ViewRootImpl 到触摸响应](05-View事件分发.md)


| 章节                     | 内容                                                                   | 核心源码路径                       | 稳定性关联               |
| ---------------------- | -------------------------------------------------------------------- | ---------------------------- | ------------------- |
| **1. ViewRootImpl 处理** | onInputEvent → enqueueInputEvent → deliverInputEvent → InputStage 管线 | `ViewRootImpl.java`          | 管线中每个 Stage 都可能延迟   |
| **2. InputStage 管线**   | 7 个 Stage 的职责和顺序（PreIme → Ime → PostIme → Synthetic）                 | `ViewRootImpl.java`          | IME 阶段可能截获事件        |
| **3. View 树分发**        | dispatchTouchEvent → onInterceptTouchEvent → onTouchEvent 三大方法       | `ViewGroup.java`、`View.java` | 最核心的应用层分发逻辑         |
| **4. 事件序列**            | ACTION_DOWN 确定 TouchTarget → MOVE/UP 直接投递 → CANCEL 释放                | `ViewGroup.java`             | DOWN 未消费 → 后续事件全部丢失 |
| **5. 滑动冲突**            | onInterceptTouchEvent 拦截 vs requestDisallowInterceptTouchEvent 反制    | `ViewGroup.java`             | 嵌套滑动冲突 → 滑动失效       |


### [06-Input ANR：从事件超时到系统裁决](06-InputANR.md)


| 章节                    | 内容                                              | 核心源码路径                | 稳定性关联                    |
| --------------------- | ----------------------------------------------- | --------------------- | ------------------------ |
| **1. Input ANR 完整机制** | 发送 → 5 秒倒计时 → 超时 → onAnrLocked → AMS            | `InputDispatcher.cpp` | Input ANR 占线上 ANR 的 60%+ |
| **2. 与其他 ANR 的区别**    | Input ANR 由 InputDispatcher 主动检测，非 Handler 超时炸弹 | —                     | 不同的检测机制 → 不同的排查方法        |
| **3. 无焦点窗口 ANR**      | Activity 启动慢 → 无 InputChannel → 事件无处可发 → 5 秒超时  | `InputDispatcher.cpp` | 冷启动慢的常见后果                |
| **4. waitQueue 串行化**  | 前一个事件未回复 → 后续事件排队 → 级联延迟                        | `InputDispatcher.cpp` | 一条慢消息导致所有事件排队            |
| **5. ANR trace 解读**   | logcat 关键词 + traces.txt 主线程栈 + dumpsys input 状态 | —                     | 实战 ANR 归因技能              |


---

## 第三篇章：诊断实战与治理（2 篇）

> 核心问题：Input 出了问题怎么查？怎么建监控？怎么做到"能查→能治→能防"？

### [07-Input 稳定性风险全景：ANR、延迟与事件丢失](07-Input稳定性风险全景.md)


| 章节                  | 内容                                                   | 稳定性关联       |
| ------------------- | ---------------------------------------------------- | ----------- |
| **1. Input ANR 分类** | 主线程卡顿型 / 无焦点窗口型 / Binder 阻塞型 / 同步屏障泄漏型               | 四种类型的识别方法   |
| **2. 触摸延迟分类**       | InputReader 阶段 / InputDispatcher 阶段 / 跨进程传输 / App 处理 | 定位延迟在哪一层    |
| **3. 事件丢失场景**       | mInboundQueue 满 / socket buffer 满 / App 未消费          | 触摸无响应的排查方向  |
| **4. 模式识别速查表**      | 问题类型 / 日志特征 / dumpsys 特征 / 排查方向                      | 5 分钟内定位问题类型 |


### [08-Input 诊断工具与延迟治理体系](08-Input诊断工具与延迟治理体系.md)


| 章节                       | 内容                                                               | 稳定性关联           |
| ------------------------ | ---------------------------------------------------------------- | --------------- |
| **1. getevent**          | 直接读取 `/dev/input/eventX`；验证硬件层事件                                 | 硬件层排查入口         |
| **2. dumpsys input**     | InputDispatcher/InputReader 状态快照；Queue 状态解读                      | 系统层排查核心工具       |
| **3. Systrace/Perfetto** | input 分类可视化；事件端到端延迟分析                                            | 性能分析主力工具        |
| **4. ANR trace 解读**      | 主线程栈 + reason 字段 + waitQueue 状态                                  | ANR 根因分析核心技能    |
| **5. 延迟监控体系**            | FrameCallback 掉帧 / InputEventReceiver 耗时 / dispatchTouchEvent 统计 | 从被动排查到主动预警      |
| **6. 治理最佳实践**            | onTouchEvent 禁耗时 / NestedScrolling / 窗口快速就绪 / 消息耗时预算             | 从"能查"到"能治"到"能防" |


---

## 阅读建议

**如果你时间有限，优先阅读：**

1. **01 总览** — 建立全局观，理解五层架构和事件完整旅程。
2. **06 Input ANR** — 实战价值最高，理解 Input ANR 的检测机制和排查方法。
3. **03 InputDispatcher** — 理解事件分发引擎和窗口选择逻辑。

**如果你要系统学习，按顺序阅读 01 → 08。** 每篇文章的设计逻辑是：

```
背景与定义（是什么、为什么需要它）
    → 架构与交互（在系统中的位置、上下游关系）
        → 核心机制与源码（关键数据结构、核心流程）
            → 稳定性风险点（会在哪里出问题）
                → 实战案例（线上真实问题的排查过程）
```

