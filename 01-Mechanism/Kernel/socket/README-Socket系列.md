# 面向稳定性的 Socket 深度解析系列

## 为什么要写这个系列

**Socket 是 Linux/Android 上进程间通讯（IPC）与网络通信的重要手段**，不是某一个子系统的附属功能模块。Android 中多处关键通信都依赖 Socket：Zygote 进程创建、Input 事件通道、adb 调试、LocalSocket 本地服务、以及应用与系统的网络请求。理解这些通信的底层机制（fd、缓冲区、连接生命周期），才能从 FD 泄漏、连接堆积、ANR/假死 中快速归因到具体场景——是 Zygote 卡住、InputChannel 满、还是应用 socket 未关。

对于稳定性架构师来说，Socket 的重要性在于：

- **进程创建的必经之路**：AMS 通过 Zygote Socket 请求 fork 应用进程；该 socket 阻塞或异常会导致进程启动失败、启动超时乃至 ANR。
- **输入与渲染的事件通道**：InputChannel（socketpair）将触摸/按键从 system_server 投递到 App；Choreographer 的 BitTube 同样基于 socketpair 传递 VSync。fd 未关闭或缓冲区满会导致事件积压、触摸无响应、丢帧。
- **调试与本地 IPC**：adb、LocalSocket/LocalServerSocket（如 installd、部分 daemon）都依赖 Unix Domain Socket 或 TCP socket；连接数、权限、泄漏会直接导致调试不可用或服务不可用。
- **网络请求的底座**：应用/系统的 HTTP、长连接、推送都建立在 TCP/UDP socket 之上；连接泄漏、TIME_WAIT 堆积、FD 耗尽、主线程阻塞 socket 会引发 OOM、ANR、假死。

本系列的目标：**让你理解 Socket 在内核中的运转方式，建立「Android 中哪些重要通讯使用 Socket」的全景，能从 fd/连接/backlog 等维度快速定位问题场景，并建立有效的监控与治理体系。**

## 系列设计思路

```
Socket 是什么？作为 IPC/网络手段与 pipe、Binder 的边界？（定位）
    ↓
Android 中哪些重要通讯使用 Socket？Zygote、Input、adb、LocalSocket、网络各如何用？（场景全景）
    ↓
在内核中的位置？与 VFS、网络栈的协作？从 socket() 到 read/write 如何运转？（核心机制）
    ↓
上述场景下 FD 耗尽、连接泄漏、backlog 满、超时/ANR 各如何发生？（风险地图）
    ↓
怎么查、怎么建监控与治理？（诊断与治理）
```

## Socket 与 epoll 是什么关系

**Socket 是"通信端点"，epoll 是"事件通知器"——两者是横向协作关系，不是包含关系。** 本系列单独讲 socket 端（端点、缓冲、连接）；epoll 端（事件通知、ET/LT、Android 应用）放在独立的 [epoll 系列](../epoll/README-epoll系列.md)。两者之间的协作原理（`f_op->poll` 钩子、`sk_data_ready` 回调路径、epitem 挂入就绪链表）见桥接篇 [socket 与 epoll 的关系](bridge/01-socket与epoll的关系.md)。

```
socket 系列（本目录）                epoll 系列（../epoll/）
─────────────────────                ─────────────────────
01 总览                              01-epoll 总览与核心机制
02 API/数据结构                      （单篇收官）
03 生命周期
04 缓冲与阻塞 ◄────────协作───────► epoll_wait / ET vs LT
05 backlog
06 UDS 与 Android
07 风险全景
08 诊断治理
│
└─ bridge/01-socket与epoll的关系  ◄─ 桥接篇（讲清两者如何协作）
```

**阅读建议**：先读 socket 01 总览建立端点视角，再读 epoll 01 建立事件通知视角，最后读桥接篇打通两者。本系列 02-08 各篇会反复回到"这个 socket fd 是怎么被 epoll 监听的"。

---

## Android 中基于 Socket 的重要通信场景（系列主线）

以下场景在 **01-Socket 总览** 中集中呈现，并在 **02～08 各篇** 中按机制与场景反复对应：

| 场景 | 用途 | 典型实现 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **Zygote Socket** | AMS 请求 Zygote fork 应用进程 | LocalSocket（客户端）+ Zygote 监听 socket（服务端）；`ZygoteServer.runSelectLoop` | socket 阻塞/异常 → 进程启动失败、ANR |
| **InputChannel** | InputDispatcher 向 App 投递触摸/按键事件 | socketpair(AF_UNIX, SOCK_SEQPACKET)；一对 fd 跨进程 | fd 未关闭/缓冲区满 → 事件积压、触摸无响应 |
| **Choreographer / VSync** | 渲染帧同步信号 | BitTube（基于 socketpair）在 SurfaceFlinger 与 App 间传 VSync | 与 InputChannel 类似的 fd/buffer 问题 |
| **adb (adbd)** | 主机与设备调试、shell、文件推送 | 设备端 adbd 通过 TCP socket 与 host 通信；本地 adb server 也依赖 socket | 连接数、端口占用、调试通道不可用 |
| **LocalSocket / LocalServerSocket** | 系统服务或应用内本地 IPC（如 installd、某些 daemon） | Unix Domain Socket（AF_UNIX）；路径或抽象命名空间 | 权限、命名空间、泄漏导致服务不可用 |
| **网络请求** | 应用/系统 HTTP、长连接、推送 | TCP/UDP socket（AF_INET） | 连接泄漏、TIME_WAIT、FD 耗尽、超时 ANR |

---

## 第一篇章：建立全局观（1 篇）

> 核心问题：Socket 是什么？作为 IPC/网络手段的边界？Android 中哪些重要通讯使用 Socket？内核四层如何协作？

### [01-Socket 总览：Linux 网络与 IPC 的通用抽象](01-Socket总览.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. Socket 是什么** | 面向文件描述符的通信抽象；支持 AF_INET/AF_UNIX 等；流式/数据报/顺序包 | — | 建立「网络与本地 IPC 皆可落到 socket」的认知 |
| **2. 为什么需要 Socket** | 与 pipe/FIFO/Binder 的对比；统一 fd、可 poll/epoll、协议可插拔 | — | 理解 Android 中何时用 Binder、何时用 socket |
| **3. 四层架构** | VFS（file_operations）→ 通用 socket 层（net/socket.c）→ 协议层（inet/unix）→ 设备/软中断 | `net/socket.c`、`net/ipv4/af_inet.c`、`net/unix/af_unix.c` | 出问题时能判断是通用层还是协议层 |
| **4. Android 中基于 Socket 的重要通信场景** | Zygote Socket、InputChannel、Choreographer/BitTube、adb、LocalSocket、网络请求逐项说明；与 Binder 的分工（Binder 负责 RPC/控制面，Socket 负责流式/事件通道）；场景与 Socket 对应关系简图 | `ZygoteServer`、`InputTransport.cpp`、adb 相关、`frameworks/base/core/java/android/net/LocalSocket.java` 等 | 建立「哪些重要通讯用到了 Socket」的全景，后续篇章与场景挂钩 |
| **5. Socket 在系统中的角色** | 内核中 socket 与 VFS、网络栈的协作；典型源码目录速查 | `net/socket.c`、`net/core/sock.c`、`include/net/sock.h`、各 af_*.c | 排查问题时的导航地图 |

---

## 第二篇章：核心机制深潜（5 篇）

> 核心问题：内核里 socket 的 API 与数据结构如何组织？从创建到关闭、缓冲区与 backlog 如何运转？与 Zygote/Input/adb/LocalSocket/网络 等场景如何对应？

### [02-Socket 内核 API 与核心数据结构](02-Socket内核API与数据结构.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. 背景与定义** | 为什么需要 API+数据结构专题；三层视角（用户态 fd / VFS file / 协议 sock）；三大结构体分工 | — | 框架性认识 |
| **2. 系统调用入口** | 7 个 syscall 总览；socket()/bind()/listen()/accept()/connect()/send/recv/close 源码逐行拆解 | `net/socket.c` | 明确 syscall 到 socket 层的边界 |
| **3. struct socket 与 struct sock** | socket/sock/sock_common 三层结构；sock<->sk_socket 双向指针；AF_INET 扩展（inet_sock/tcp_sock）；AF_UNIX 扩展（unix_sock） | `include/linux/net.h`、`include/net/sock.h`、`include/net/inet_sock.h`、`include/linux/tcp.h` | 看 /proc/net 或内核 trace 时能对应结构 |
| **4. 协议层挂接** | proto_ops 与 proto 双层函数指针表；net_families 协议族注册；inetsw[] 协议分流；AF_INET → inet_stream_ops → tcp_prot 注册链；AF_UNIX → unix_stream_ops → unix_proto 注册链；完整 read() 13 步调用链 | `net/ipv4/af_inet.c`、`net/unix/af_unix.c`、`net/core/sock.c` | 区分「通用 socket 层」与「TCP/UDS 实现」 |
| **5. 与 VFS 的绑定** | socket_file_ops 详细；sock_alloc_file 中 file<->socket 双向指针；socket 伪文件系统 sockfs；/proc/pid/fd 中 Zygote/InputChannel/BitTube/应用 socket 的具体表现 | `net/socket.c`、`fs/proc/fd.c` | fd 泄漏即 file/socket 未释放；能按 fd 类型归因到场景 |
| **6. 综合：诊断工具与结构体对应** | /proc/net/tcp、/proc/net/unix 字段→结构体字段对照表；strace→内核入口对照；ANR trace 栈→内核函数对照；一键 socket 查询脚本 | — | 把 08 诊断工具与本篇结构体打通 |
| **7. 稳定性关联与实战案例** | socket 三元组 3 个易错点；CLOSE_WAIT 5000 个 FD 泄漏案例完整排查 | — | 联动 ①FD 耗尽 + ④协议失败 |
| **8. 附录** | 核心源码路径、字段速查、调用链速查、量化数据自检、与其他文章关系 | — | 工程化沉淀 |

### [03-Socket 连接生命周期：从创建到关闭](03-Socket连接生命周期.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. 背景与定义** | 生命周期专题的必要性；6 阶段 11 状态全景；AF_INET vs AF_UNIX 生命周期差异；11 个 TCP 状态速查 | — | 框架性认识 |
| **2. 创建** | socket() 系统调用；状态机起点；创建失败原因（EAFNOSUPPORT/EMFILE/ENFILE） | `net/socket.c` | 创建失败的错误码与场景 |
| **3. 绑定** | inet_bind / unix_bind 详细源码；tcp_v4_get_port 端口分配；UDS 路径型/abstract 差异；bind 失败原因 | `net/ipv4/af_inet.c`、`net/unix/af_unix.c` | EADDRINUSE、端口冲突、路径残留 |
| **4. 监听** | inet_listen / unix_listen 源码；backlog 与 somaxconn 截断；Zygote listen 特殊点 | `net/ipv4/af_inet.c`、`net/unix/af_unix.c` | backlog 过小 → 连接建立慢或失败 |
| **5. 接受** | inet_accept / unix_accept 源码；inet_csk_accept 等待连接；accept 与 epoll 协作 | `net/ipv4/af_inet.c`、`net/ipv4/inet_connection_sock.c` | 阻塞 accept 反模式、EMFILE 处理 |
| **6. 连接** | inet_stream_connect / unix_stream_connect 源码；TCP 三次握手完整状态机；connect 超时与重试 | `net/ipv4/tcp.c`、`net/ipv4/tcp_ipv4.c` | 网络请求连接超时、半连接堆积的根因 |
| **7. 关闭** | close() vs shutdown() 关键差异；close() 完整调用链；inet_release；tcp_close；四次挥手完整状态机；4 个关键状态详解（FIN_WAIT1/2、CLOSE_WAIT、TIME_WAIT、LAST_ACK）；SO_LINGER；half-close；AF_UNIX 关闭特殊点；close 与 sock 引用计数 | `net/ipv4/tcp.c`、`net/socket.c` | CLOSE_WAIT 根因、TIME_WAIT 端口耗尽、shutdown 协议 |
| **8. 特殊状态与边界** | RST vs FIN 关键差异；half-close 半关闭；AF_UNIX 关闭的特殊点（无四次挥手、无 TIME_WAIT） | — | RST 数据丢失、半关闭协议支持 |
| **9. Android 6 大场景生命周期映射** | Zygote / InputChannel / Choreographer / adb / LocalSocket / 应用网络 全场景的生命周期图 + 关键路径 + 对应风险 | AOSP 源码 | 6 大场景的状态机视图 |
| **10. 实战案例** | 案例 1：CLOSE_WAIT 5000 个应用未 close；案例 2：TIME_WAIT 10000+ 端口耗尽；案例 3：FIN_WAIT2 60s+ 对端不 close；案例 4：connect 60s+ 启动 ANR | — | 完整闭环：现象→定位→根因→修复→治理 |
| **11. 附录** | 核心源码路径、TCP 11 状态速查、AF_INET vs AF_UNIX 对比、状态→监控指标对照、量化数据自检、与其他文章关系 | — | 工程化沉淀 |
| **12. socket 系列"机制深潜"篇章收口** | 02-06 五篇知识地图、socket 系列完结、生命周期诊断卡 | — | 闭环 |

### [04-Socket 缓冲区与数据收发](04-Socket缓冲区与数据收发.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. 发送/接收队列** | sk_write_queue、sk_receive_queue、sk_error_queue；sk_buff 在队列中的角色 | `include/net/sock.h`、`net/core/sock.c` | 队列满导致阻塞或 EAGAIN |
| **2. socket buffer 与 SO_SNDBUF/SO_RCVBUF** | 用户态与内核缓冲的关系；sk_sndbuf、sk_rcvbuf | `net/core/sock.c` | buffer 过小 → 吞吐差；过大 → 内存占用；InputChannel/Choreographer buffer 满 → 事件积压或丢帧 |
| **3. send/recv 与 copy_from_user/copy_to_user** | 数据如何从用户态进内核、进协议栈、进网卡/对端 | `net/socket.c`、协议层 | 理解「数据拷贝」与性能/稳定性 |
| **4. 阻塞与非阻塞** | wait queue、EAGAIN/EWOULDBLOCK、poll/select/epoll 与 socket 的联动 | `net/core/sock.c` | 主线程阻塞 socket 或未处理 EAGAIN → 假死/ANR 风险 |

### [05-listen backlog 与连接队列](05-listen_backlog与连接队列.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. backlog 语义** | listen(sock, backlog) 在内核中的解释；与全连接队列、半连接队列的关系 | `net/core/sock.c`、`net/ipv4/tcp.c` | 配置不当导致连接被拒绝或延迟 |
| **2. 半连接队列（SYN queue）与 SYN cookie** | SYN 到达后的存放；队列满时的行为与 SYN cookie | `net/ipv4/tcp_ipv4.c`、`net/ipv4/syncookies.c` | SYN flood、半连接队列溢出（网络场景） |
| **3. 全连接队列（accept queue）** | 已完成三次握手的连接等待 accept()；队列满时对 SYN-ACK 的影响 | `net/ipv4/tcp.c` | 高并发下 accept 慢 → 全连接队列满 → 建连失败；Zygote accept 循环、adb/LocalServerSocket 并发连接 |
| **4. 与稳定性/性能的取舍** | 典型取值、内核参数（somaxconn、tcp_max_syn_backlog）及调优注意点 | 内核文档/参数 | 避免盲目调大导致内存或 DoS 风险 |

### [06-Unix Domain Socket 与 Android 中的使用](06-Unix_Domain_Socket与Android使用.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. AF_UNIX 特点** | 本地 only、无网络栈、可用于 IPC；流式/数据报/seqpacket | `net/unix/af_unix.c`、`net/unix/dgram.c` | 与 Binder 的选用场景（如 InputChannel、Zygote） |
| **2. socketpair 与 InputChannel/BitTube** | socketpair() 创建双向 fd；Android Input 事件通道、Choreographer VSync 通道 | `InputTransport.cpp`、Choreographer 相关 | socket buffer 满 → 事件积压/丢事件/丢帧 |
| **3. Zygote Socket 与 LocalSocket** | ZygoteServer 监听 UDS；AMS 通过 LocalSocket 连接；installd 等 daemon 的 LocalServerSocket | `ZygoteServer`、`LocalSocket`/`LocalServerSocket`（Java）、Native 实现 | 权限、命名空间、泄漏导致进程启动失败或服务不可用 |
| **4. 权限与命名空间** | 路径型 vs 抽象命名空间；与 Android 权限的关系 | `net/unix/af_unix.c` | 权限或命名空间导致连接失败 |

---

## 第三篇章：诊断实战与治理（2 篇）

> 核心问题：Socket 在 Zygote/Input/adb/LocalSocket/网络 等场景下会出哪些问题？如何查、如何建监控与治理？

### [07-Socket 稳定性风险全景](07-Socket稳定性风险全景.md)

| 章节 | 内容 | 稳定性关联 |
| :--- | :--- | :--- |
| **1. Zygote 相关** | Zygote Socket 阻塞、accept 慢、连接未正确关闭；进程启动失败、启动超时、ANR | 现象与排查方向 |
| **2. Input / Choreographer 相关** | InputChannel fd 泄漏、socket buffer 满、事件积压；触摸无响应、丢帧 | fd 与 buffer 的归因 |
| **3. adb / LocalSocket 相关** | 连接数、端口占用、LocalServerSocket 泄漏；调试不可用、本地服务不可用 | 连接与权限问题 |
| **4. 应用网络相关** | FD 与连接泄漏、TIME_WAIT 堆积、主线程阻塞 socket、backlog 满 | OOM、ANR、假死、连接失败 |
| **5. 通用问题与速查表** | FD/socket 泄漏、连接泄漏、backlog 与队列满、缓冲区与阻塞；问题类型 / 日志特征 / 排查方向 对照 | 5 分钟内定位问题类型与场景 |

### [08-Socket 诊断工具与治理体系](08-Socket诊断工具与治理体系.md)

| 章节 | 内容 | 稳定性关联 |
| :--- | :--- | :--- |
| **1. 背景与定义** | 诊断 + 治理双视角；工具全景图；治理体系全景图 | 框架性认识 |
| **2. 诊断工具详解** | /proc/net/* 完整解读（sockstat/tcp/unix/snmp/netstat）；ss/lsof 实战；/proc/pid/fd 与 socket:[inode] 归属；strace+tcpdump 抓包模板；ANR trace 关键栈识别；dumpsys 命令速查；dropwatch/perf/ftrace 内核观测 | 现场 5 分钟定位 |
| **3. 监控指标体系** | 进程级（fd 总量/分类/异常状态）、协议级（TCP 状态分布/队列溢出/重传错误）、场景级（InputChannel/Zygote/Choreographer/网络）；主动巡检 + 触发告警 + dashboard | 从被动排查到主动预警 |
| **4. 治理体系** | 主动防御（fdsan/StrictMode/code review）、资源管理（连接池/buffer/超时规范）、调优（backlog/TIME_WAIT/buffer）、工程化（CI 校验脚本）、监控（告警阈值/dashboard） | 能查 → 能治 → 能防 |
| **5. 实战案例** | 案例 1：FD 耗尽导致所有 app 启动失败（联动 ①③④）；案例 2：触摸无响应主线程被 InputChannel 阻塞（联动 ②④）；案例 3：adb 假死全连接队列满 | 联动多类风险的综合案例 |
| **6. 附录** | 核心源码路径、工具命令速查卡、监控告警阈值基线、量化数据自检表、知识地图 | 工程化沉淀 |
| **7. socket 系列收官** | 8 篇知识地图、epoll 协作、工程化沉淀、后续延伸方向 | 闭环 |

---

## 阅读建议

**如果你时间有限，优先阅读：**
1. **01 总览** — 建立全局观，理解 Socket 是 IPC 手段，以及「Android 中哪些重要通讯使用 Socket」。
2. **07 稳定性风险全景** — 按场景（Zygote/Input/adb/LocalSocket/网络）理解风险，直接提升排查效率。
3. **08 诊断工具与治理体系** — 工具与场景对应、监控与治理落地。

**如果你要系统学习，按顺序阅读 01 → 08。** 每篇文章的设计逻辑是：
```
背景与定义（是什么、为什么需要它）
    → 架构与交互（在系统中的位置、与 Android 场景的对应）
        → 核心机制与源码（关键数据结构、核心流程）
            → 稳定性风险点（会在哪里出问题、对应哪些场景）
                → 实战案例（线上真实问题的排查过程）
```
