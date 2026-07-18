# 面向稳定性的 epoll 深度解析系列

## 为什么要写这个系列

**epoll 是 Linux/Android 上几乎所有高性能服务的"事件通知底座"**。`system_server` 的 `InputDispatcher`、每个 app 的主线程 `Looper`、`ZygoteServer`、所有 Java NIO Selector（OkHttp/Netty/grpc 底层）、所有 Native daemon（`adbd`、`vold`、`installd`、`AudioFlinger`、`SurfaceFlinger`）——**没有 epoll 就没有今天 Android 的并发能力**。epoll 把传统 `select/poll` 的 O(N) 全量扫描降到 O(M) 就绪数，是 Linux 高并发服务的事实标准。

对于稳定性架构师来说，epoll 的重要性在于：

- **Input 事件无响应的常见根因**：InputDispatcher 在 epoll_wait 唤醒后处理 wakeup 慢，导致 Input 事件积压
- **触摸丢事件 / 卡顿**：ET 模式误用、fd 漏关、缓冲区满
- **主线程假死**：主线程在 epoll_wait 唤醒后做了同步 IO（详见 [Handler 系列](../01-Mechanism/App/Handler-MessageQueue-Looper/README-Handler系列.md)）
- **FD 资源耗尽**：epoll_ctl(ADD) 失败、进程 fd 数超过 `RLIMIT_NOFILE`
- **Zygote fork 慢**：socket + epoll 配合问题导致进程启动 ANR

本系列的目标：**让你理解 epoll 的设计动机、内核实现、ET/LT 语义差异、在 Android 关键场景下的使用模式与踩坑模式，能从 systrace / strace / ANR trace 中快速定位问题。**

## epoll 与 socket 是什么关系

**这是本系列与 [socket 系列](../socket/README-Socket系列.md) 的核心关系，必须先讲清楚：**

- **socket 解决"数据怎么走"**——`socket()` / `bind()` / `listen()` / `accept()` / `connect()` / `send()` / `recv()`，背后是协议族实现（TCP/UDS/UDP）
- **epoll 解决"什么时候知道数据到了"**——监听**任意 fd**（包括 socket，但不仅限 socket）什么时候就绪
- **二者是协作关系，不是包含关系**：socket 是端点，epoll 是通知器

**为什么这个关系重要**：socket 系列里的 02-08 各篇（API/数据结构/生命周期/缓冲区/backlog/UDS/风险/治理）都会涉及"socket 怎么被 epoll 监听"的具体细节；本系列则从 epoll 视角反向看"epoll 怎么监听 socket"，两者互为表里。

**横切关系图**：

```
┌──────────────────────────────────────────────────────┐
│  socket 系列 (../socket/)                              │
│  02-Socket内核API与数据结构.md                          │
│  03-Socket连接生命周期.md                               │
│  04-Socket缓冲区与数据收发.md（epoll 的阻塞语义）         │
│  06-Unix_Domain_Socket与Android使用.md（InputChannel）  │
│  07-Socket稳定性风险全景.md                              │
└──────────────┬───────────────────────────────────────┘
               │  socket fd ←→ epoll 监听
               │
┌──────────────▼───────────────────────────────────────┐
│  epoll 系列 (本目录)                                     │
│  01-epoll总览与核心机制.md                              │
│  (单篇收官：定义/历史/三态/ET-LT/Android应用/风险/案例)  │
└──────────────┬───────────────────────────────────────┘
               │  桥接
               │
┌──────────────▼───────────────────────────────────────┐
│  桥接专题 (../socket/bridge/)                           │
│  01-socket与epoll的关系.md（两者的协作原理）            │
└──────────────────────────────────────────────────────┘
```

**强依赖关系**：

- 本系列强依赖 [socket 04-缓冲区与数据收发](../socket/04-Socket缓冲区与数据收发.md) §4（阻塞与非阻塞）
- 本系列强依赖 [IO 07-IO 与进程阻塞](../../IO/07-IO与进程阻塞.md)（D 状态、wait queue 唤醒）
- 本系列强依赖 [Interrupt 软中断与 ksoftirqd](../../Interrupt/深度解密：中断的“上半部”与“下半部” (Hard IRQ vs SoftIRQ).md)（epoll 利用的 softirq 上下文）
- [socket 01-Socket总览](../socket/01-Socket总览.md) §2.2（struct socket ↔ struct sock ↔ struct file）也对理解本系列有帮助

## 系列设计思路

```
epoll 是什么？解决 select/poll 的什么痛点？（定位）
    ↓
  它在内核中怎么实现？三态数据结构是什么？（核心机制）
    ↓
  ET vs LT 怎么选？为什么 Android 主流选 LT？（语义差异）
    ↓
  Android 哪些关键服务用了 epoll？InputDispatcher/Looper/Zygote/NIO 如何协作？（Android 应用）
    ↓
  上面这些场景在什么情况下会出问题？怎么查？怎么防？（风险与治理）
```

## 篇章列表

本系列采用"**单篇收官**"策略（已与作者确认：epoll 机制 + Android 应用 + 风险 + 案例在一篇内可讲清，不再拆 02/03）。

### [01-epoll 总览与核心机制](01-epoll总览与核心机制.md)

| 章节 | 内容 | 核心源码路径 | 内核版本基线 | 稳定性关联 |
| :--- | :--- | :--- | :--- | :--- |
| 1. 背景与定义 | epoll 是什么、为什么需要它、select/poll 的 O(N) 痛点 | `fs/eventpoll.c` | Linux 5.10/5.15/6.1/6.6 | 架构师建立 O(M) 心智模型 |
| 2. 发展历史 | 2.5.44 引入 → 2.6 ET → 4.5 EPOLLEXCLUSIVE → 4.14 epoll_pwait2 → Android 5.0 Java NIO 迁移 → 7.0/8.0 改用 epoll_pwait | kernel.org git log | 全版本 | 解释老代码遗留与升级行为差异 |
| 3. 架构与交互 | epoll 在系统中的位置（VFS 层、协议层、softirq 层协作） | `fs/eventpoll.c` | Linux 5.10 | 故障定位时的栈帧归因 |
| 4. 三态数据结构源码 | `struct eventpoll`（红黑树/就绪链表/等待队列）+ `struct epitem` | `include/linux/eventpoll.h`、`fs/eventpoll.c` | Linux 5.10 | epoll_ctl(ADD) 与 epoll_wait 的成本分摊 |
| 5. ET vs LT 语义 | 状态通知 vs 边沿通知的时序对比 + 源码 `ep_poll_callback` | `fs/eventpoll.c` | Linux 5.10+ | "为什么 Input 选 LT、Netty 选 ET" 的工程取舍 |
| 6. epoll_pwait 与信号屏蔽 | 原子信号屏蔽的必要性、Android 8+ 改用 | `fs/eventpoll.c`、`kernel/signal.c` | Linux 5.10+ | 偶发事件丢失的根因 |
| 7. Android 实际应用 | InputDispatcher / Looper / ZygoteServer / Java NIO Selector / eventfd 等 | AOSP 14.0.0_r1 | AOSP 14 + kernel 5.10 | 6 大使用方的踩坑重点 |
| 8. 风险地图 | 10 类稳定性问题速查表 | `/proc/<pid>/fd` | — | 问题类型/日志/排查入口对照 |
| 9. 实战案例 | 案例 1：InputDispatcher 偶发按键无响应（厂商 GKI IO 调度器异常）<br>案例 2：Java NIO Selector 泄漏导致 fd 数爆炸 | AOSP 12/14 + kernel 5.10/5.15 | AOSP 12-14 | 完整可验证（环境+复现+logcat+修复） |
| 10. 总结 + 4 附录 | 5 条 Takeaway + 排查路径速查 + 附录 A 源码索引 / B 路径对账表 / C 量化自检表 / D 工程基线表 | — | — | v3 强制项 |

## 阅读建议

**如果你时间有限，优先阅读**：

1. **§1-2 背景与历史**（10 分钟）— 理解 epoll 为什么存在、和 select/poll 的差异
2. **§4 三态数据结构**（15 分钟）— 建立"epoll 不是加速版 select，而是 O(N)→O(M) 的算法重构"的心智模型
3. **§5 ET vs LT**（10 分钟）— 这是稳定性架构师必须能讲清楚的概念
4. **§7 Android 实际应用**（20 分钟）— InputDispatcher / Looper 的设计选择是稳定性最相关的部分
5. **§9 实战案例**（15 分钟）— 两个完整案例是排查时最直接的参考

**如果系统学习**：按 §1 → §10 顺序读完即可（本系列 1 篇收官）。

**关联阅读**：

- 理解 socket 端点视角：[socket 01-Socket总览](../socket/01-Socket总览.md)
- 理解 socket 阻塞与 epoll 的对接：[socket 04-缓冲区与数据收发](../socket/04-Socket缓冲区与数据收发.md) §4
- 理解 wait queue 与 D 状态：[IO 07-IO 与进程阻塞](../../IO/07-IO与进程阻塞.md)
- 理解 epoll 与 socket 的协作原理：[socket/bridge/01-socket与epoll的关系](../socket/bridge/01-socket与epoll的关系.md)
- 理解 InputDispatcher 端到端：[Input 系列](../01-Mechanism/Framework/Input/)
- 理解主线程消息机制：[Handler 系列](../01-Mechanism/App/Handler-MessageQueue-Looper/README-Handler系列.md)

每篇文章的设计逻辑是：
```
背景与定义（是什么、为什么需要它）
    → 架构与交互（在系统中的位置、与内核/驱动的关系）
        → 核心机制与源码（关键数据结构、核心流程）
            → 稳定性风险点（会在哪里出问题）
                → 实战案例（线上真实问题的排查过程）
```

## 与其他系列的交叉引用

| 本系列章节 | 引用系列 | 引用文章 | 引用原因 |
|-----------|---------|----------|----------|
| §1.2 select/poll 痛点 | IO | [IO 01-IO 子系统总览](../../IO/01-IO子系统总览.md) | 阻塞 IO 模型 |
| §3 架构与交互 | socket | [socket 01-Socket总览](../socket/01-Socket总览.md) §2 | socket 的 VFS 绑定层 |
| §3 架构与交互 | Interrupt | [Interrupt 软中断与 ksoftirqd](../../Interrupt/深度解密：中断的“上半部”与“下半部” (Hard IRQ vs SoftIRQ).md) | epoll_callback 在 softirq 上下文 |
| §4 三态数据结构 | IO | [IO 07-IO 与进程阻塞](../../IO/07-IO与进程阻塞.md) | wait queue 基础 |
| §7 InputDispatcher | Input | [Input 系列](../01-Mechanism/Framework/Input/) | 端到端 Input 事件链路 |
| §7 Looper | Handler | [Handler 系列](../01-Mechanism/App/Handler-MessageQueue-Looper/README-Handler系列.md) | Java/Native Looper 关系 |
| §7 Java NIO Selector | socket | [socket 06-UDS 与 Android](../socket/06-Unix_Domain_Socket与Android使用.md) | Java NIO 与 UDS |
| §9 实战案例 | socket | [socket 04-缓冲区与数据收发](../socket/04-Socket缓冲区与数据收发.md) | 缓冲区与 ANR 关联 |
