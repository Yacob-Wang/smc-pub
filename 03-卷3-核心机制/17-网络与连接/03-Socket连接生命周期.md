# Socket 03：连接生命周期——从创建到关闭

> **系列**：面向稳定性的 Android Socket 子系统深度解析系列(Socket)
>
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
>
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `net/ipv4/tcp_input.c`、`net/ipv4/tcp_output.c`、`net/ipv4/tcp_minisocks.c`、`net/ipv4/tcp_timer.c`;TCP_TIMEWAIT_LEN 在 5.15+ 缩短到 60s 见 §5;MPTCP 路径差异见 §6)
>
> **目标读者**:Android 稳定性框架架构师
>
> **前置阅读**:[01-Socket 总览](01-Socket总览.md) / [02-Socket 内核 API 与数据结构](02-Socket内核API与数据结构.md)
>
> **下一篇**:[04-Socket 缓冲区与数据收发](04-Socket缓冲区与数据收发.md)

---

## 本篇定位

- **本篇系列角色**:Socket 系列第 3 篇「连接生命周期:从创建到关闭」(socket 系列 8 篇规划"第二篇章:核心机制深潜"的收口;与 02 API+数据结构对应——02 讲"是什么 / 怎么组织",03 讲"怎么变化 / 走完一生")
- **强依赖**:
  - [Socket 01-Socket总览](01-Socket总览.md)(6 大场景基线)
  - [Socket 02-Socket内核API与数据结构](02-Socket内核API与数据结构.md)(系统调用入口与三大结构体——本篇所有调用链的基础)
  - [Socket 04-Socket缓冲区与数据收发](04-Socket缓冲区与数据收发.md)(接收/发送队列——本篇 FIN 发送/接收的关键路径)
  - [Socket 05-listen_backlog与连接队列](05-listen_backlog与连接队列.md)(backlog 与半连接/全连接队列——本篇 listen 段会引用)
  - [Socket 06-Unix_Domain_Socket与Android使用](06-Unix_Domain_Socket与Android使用.md)(UDS 路径型/abstract 创建、Zygote 等场景细节)
  - [Socket 07-Socket稳定性风险全景](07-Socket稳定性风险全景.md)(5 大类风险——本篇每段标注对应的风险类型)
  - [Socket 08-Socket诊断工具与治理体系](08-Socket诊断工具与治理体系.md)(监控指标——本篇每种状态给出对应监控点)
  - [epoll 01-epoll总览与核心机制](../epoll/01-epoll总览与核心机制.md)(非阻塞与 epoll 唤醒机制)
  - [IO 06-IO 与进程的深度耦合](../../IO/06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md)(D 状态、wait queue 唤醒——connect/accept/close 阻塞时关联)
- **承接自**:02 §2 系统调用入口与 §3 数据结构——本篇把 syscall 按"生命周期"重组
- **衔接去**:本篇完成后 socket 系列"机制深潜"篇章(02-06)全部完结;最后一篇 08 已经在 03 之前写完作为收口
- **不重复内容**:syscall 的通用入口已由 02 §2 详述;本篇只讲**协议层状态机 + 关键路径的差异点**

#### §0 锚点案例的可验证 4 件套:IM App TIME_WAIT 堆积 30k 导致端口耗尽,新连接 ECONNREFUSED

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.10` GKI(`tcp_tw_reuse=0` 默认,`tcp_tw_timeout=60s`)
> - App:某 IM App v8.5(脱敏代号 `ChatApp`,客户端主动短连接到 5 个 IM 接入服务器)
> - 工具:`ss -s` + `cat /proc/net/sockstat` + `cat /proc/sys/net/ipv4/ip_local_port_range` + `tcpdump`

> **复现步骤**:
> 1. 工厂重置,安装 ChatApp v8.5,登录账号
> 2. 触发高频消息发送(每 5s 重连一次,模拟弱网重连场景)
> 3. `ss -tan state time-wait | wc -l` 每分钟采样
> 4. `cat /proc/sys/net/ipv4/ip_local_port_range` → 默认 `32768 60999`(约 28k 端口)
> 5. 持续运行 30min,观察 TIME_WAIT 堆积情况

> **logcat / ss 关键片段**:
> ```
> # ss -s(30min 后)
> TCP:   41284 (estab 124, closed 40120, orphaned 0, tw 40120)    ← tw = 40120 远超 ip_local_port_range
> # ss -tan state time-wait | wc -l
> 40120   ← TIME_WAIT 堆积 4 万
> # cat /proc/net/sockstat
> sockets: used 41284
> TCP: inuse 124 orphan 0 tw 40120 alloc 124 mem 248
> # /proc/sys/net/ipv4/ip_local_port_range
> 32768   60999   ← 可用端口 28k,TIME_WAIT 4 万严重超出
> # tcpdump 抓客户端连接请求
> 14:32:18 ChatApp → 10.0.0.10:443 SYN
> 14:32:18 10.0.0.10:443 → ChatApp RST, ack  ← 端口耗尽,服务端 RST
> # logcat 客户端错误
> OkHttp ConnectionPool: failed to connect to /10.0.0.10: ECONNREFUSED
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/app/src/main/java/com/chat/app/NetworkClient.kt
> +++ b/app/src/main/java/com/chat/app/NetworkClient.kt
> @@ OkHttpClient.Builder
> -    // 旧版:每次发消息新建短连接,触发频繁 3 次握手 + TIME_WAIT 堆积
> -    client.newCall(Request.Builder().url(url).build()).execute()
> +    // 修复:OkHttp 默认 keepAlive + ConnectionPool 长连接复用
> +    val pooledClient = OkHttpClient.Builder()
> +        .connectionPool(ConnectionPool(50, 300, TimeUnit.SECONDS))  // 50 连接 / 5min
> +        .build()
> +    pooledClient.newCall(Request.Builder().url(url).build()).execute()
> ```
> ```diff
> --- a/proc/sys/net/ipv4/tcp_tw_reuse
> +++ b/proc/sys/net/ipv4/tcp_tw_reuse
> @@ tuning
> -    # 旧版:tcp_tw_reuse=0,TIME_WAIT 不能复用
> +    # 修复:对客户端打开 tcp_tw_reuse=1,允许 TIME_WAIT 端口复用
> +    net.ipv4.tcp_tw_reuse = 1
> +    net.ipv4.ip_local_port_range = 10000 65000   # 55k 端口可用
> ```
> 完整 TCP 状态机 ↔ SYN/ACK/FIN ↔ TIME_WAIT 调优 ↔ 连接池策略见 §2 §4 §5 §7。

> 面向 Android 稳定性架构师：把 socket 的"一生"——从 `socket()` 创建到 `close()` 释放——按"状态机"完整展开，重点是 **TCP 状态机（11 个状态）** 与 **UDS 状态机** 的差异、**TIME_WAIT 60 秒等待**为什么必要、**CLOSE_WAIT 累积**为什么根因总在应用层、**shutdown vs close** 的关键差异、**四次挥手 vs 三次握手**的状态对应。让你看 `/proc/net/tcp` 状态码、看 ANR trace、看 `ss -tan state <state>` 时能精确对应到生命周期的某个阶段。

## 一、背景与定义

### 1.1 为什么需要"生命周期"专题

socket 的"一生"包含**6 个核心阶段**（创建 / 绑定 / 监听 / 接受 / 连接 / 关闭）和 **11 个 TCP 状态**。每个阶段都有：

- **可观测的状态字段**（`socket->state` / `sk->sk_state`）
- **可能失败的环节**（创建失败、bind 冲突、listen 慢、accept 阻塞、connect 超时、close 异常）
- **可监控的指标**（fd 数、连接数、状态分布、队列深度）
- **可治理的工程实践**（超时设置、连接池、backlog 调优）

**实战问题**：
- 看到 `ss -tan` 输出大量 `TIME_WAIT` → 短连接高频 → 治理：连接池
- 看到 `CLOSE_WAIT` 持续增长 → 应用层未 close → 治理：finally/try-with-resources
- 看到 `SYN_SENT` 持续时间过长 → 网络阻塞或对端无响应 → 治理：connect timeout
- 看到 `FIN_WAIT2` 持续不结束 → 对端未 close → 治理：SO_LINGER + read 端主动关闭
- 看到 `LAST_ACK` 持续 60 秒 → 关闭时丢包 → 治理：调整 `tcp_fin_timeout`

**本篇目标**：把这些"状态"和"治理"精确对应。

### 1.2 生命周期全景图

```
[创建]   socket()       → socket->state = SS_UNCONNECTED
                            sk->sk_state = TCP_CLOSE (AF_INET) / SS_UNCONNECTED (UDS)
   ↓
[绑定]   bind()         → socket->state = SS_UNCONNECTED
                            sk->sk_state = TCP_CLOSE
   ↓ (服务端)
[监听]   listen()       → socket->state = SS_LISTENING
                            sk->sk_state = TCP_LISTEN
   ↓
[接受]   accept()       → 新 socket->state = SS_CONNECTED
                            新 sk->sk_state = TCP_ESTABLISHED
   ↓
[收发]   read/write()   → sk->sk_state 保持 TCP_ESTABLISHED
   ↓
[关闭]   close()        → socket->state = SS_UNCONNECTED (调用方)
                            sk->sk_state 走四次挥手：
                                TCP_FIN_WAIT1 → TCP_FIN_WAIT2 → TCP_TIME_WAIT → TCP_CLOSE
                                TCP_CLOSE_WAIT → TCP_LAST_ACK → TCP_CLOSE
   ↓
[释放]   sock_release() → sk->sk_refcnt = 0 → 真正释放
```

**关键观察**：
- **socket->state**（BSD 层）和 **sk->sk_state**（协议层）**不是同一个**——前者是宏观状态，后者是 TCP 状态机的精确位置
- 关闭时调用方可以 `socket->state=SS_UNCONNECTED`，但**协议层要走完整的四次挥手**才能真正释放
- 真正释放资源要等 **sk->sk_refcnt=0**——而引用计数受多个因素影响（dup、fork、SCM_RIGHTS 等）

### 1.3 AF_INET vs AF_UNIX 生命周期差异

| 阶段 | AF_INET TCP | AF_UNIX SOCK_STREAM |
|------|-------------|---------------------|
| 创建 | `inet_create` → `tcp_sock` | `unix_create` → `unix_sock` |
| 绑定 | `inet_bind` → `tcp_v4_bind`（端口 + IP） | `unix_bind` → 路径或 abstract |
| 监听 | `inet_listen` → `tcp_listen`（backlog 队列） | `unix_listen`（队列较短） |
| 接受 | `inet_accept` → `inet_csk_accept`（wait_for_connect） | `unix_accept`（path 校验） |
| 连接 | `inet_stream_connect` → `tcp_v4_connect`（三次握手） | `unix_stream_connect`（无握手） |
| 关闭 | `inet_release` → `tcp_close`（四次挥手） | `unix_release`（直接关闭） |
| 状态机 | **11 个 TCP 状态** | **3 个 UDS 状态**（UNCONNECTED/LISTENING/CONNECTED） |
| 关键差异 | 需经过网络栈、SYN/FIN 同步 | 本地直连，无网络状态 |

**实战意义**：
- **AF_UNIX 没有 TIME_WAIT**——这是 Zygote、InputChannel 不会遇到 TIME_WAIT 堆积的原因
- **AF_UNIX 没有 SYN flood**——这是 LocalServerSocket 不会受 SYN flood 影响的原因
- **AF_UNIX 的 close 极快**——这是 UDS 频繁创建销毁不影响性能的原因

### 1.4 11 个 TCP 状态速查

| 状态码 | 名称 | 方向 | 含义 |
|--------|------|------|------|
| 01 | TCP_ESTABLISHED | 双向 | 已建立，可收发数据 |
| 02 | TCP_SYN_SENT | 客户端 | 主动打开，发 SYN |
| 03 | TCP_SYN_RECV | 服务端 | 收 SYN，发 SYN+ACK |
| 04 | TCP_FIN_WAIT1 | 主动关闭方 | 发 FIN |
| 05 | TCP_CLOSE | 双向 | 已关闭 |
| 06 | TCP_TIME_WAIT | 主动关闭方 | 2MSL 等待 |
| 07 | TCP_CLOSE | 同 05 | — |
| 08 | TCP_CLOSE_WAIT | 被动关闭方 | 收 FIN，等待应用 close |
| 09 | TCP_LAST_ACK | 被动关闭方 | 发 FIN，等 ACK |
| 0A | TCP_LISTEN | 服务端 | 监听 |
| 0B | TCP_CLOSING | 双方同时关闭 | 几乎遇不到 |

**实战判断**：
- `ST=06 (TIME_WAIT)` 持续 > 5000 → 短连接高频
- `ST=08 (CLOSE_WAIT)` 持续增长 → 应用未 close
- `ST=04 (FIN_WAIT1)` / `ST=05 (FIN_WAIT2)` 持续 60s+ → 对端未响应

---

## 二、创建：socket() 系统调用

socket 的"出生"由 `socket()` 系统调用完成。已在 02 §2.2 详述，本节只补充**状态机起点**与**创建失败的常见原因**。

### 2.1 创建后的状态

```c
// AF_INET TCP socket
sock->state = SS_UNCONNECTED;     // BSD 状态
sk->sk_state = TCP_CLOSE;          // 协议层状态

// AF_UNIX SOCK_STREAM socket
sock->state = SS_UNCONNECTED;     // BSD 状态
sk->sk_state = SS_UNCONNECTED;     // UDS 没有 TCP 状态
```

**关键**：
- 刚创建的 socket **不能直接收发数据**——必须先 bind（服务端）或 connect（客户端）
- 此时**未加入任何 hash 表**（inet_hash / unix_hash）——所以没有"端口冲突"问题

### 2.2 创建失败的常见原因

| 错误码 | 含义 | 典型场景 |
|--------|------|----------|
| `-EAFNOSUPPORT` | 协议族不支持 | `socket(AF_MAX, ...)` |
| `-EINVAL` | 参数非法 | `socket(AF_INET, 99, 0)`（type 非法） |
| `-ENOBUFS` / `-ENOMEM` | 内存不足 | 系统内存压力 |
| `-EMFILE` | 进程 fd 耗尽 | FD 泄漏或 RLIMIT_NOFILE 满 |
| `-ENFILE` | 系统 fd 耗尽 | `/proc/sys/fs/file-max` 满 |

**对应监控指标**（08 §3.1）：
- 单进程 fd 接近 80% RLIMIT_NOFILE → 预防 EMFILE
- `cat /proc/sys/fs/file-nr` 看整机 fd 余量

### 2.3 与稳定性的关系

**创建失败 P0 场景**：
- **Zygote 启动时** `socket(PF_UNIX, SOCK_STREAM, 0)` 失败 → 所有 app 启动失败（P0 启动失败）
- **应用 bind 80 端口** 创建监听 socket 失败 → 80 端口被占用或权限不足

**治理**（08 §4）：
- 创建前检查 `fd 余量 > 20%`
- 创建时捕获错误码 → 重试或降级
- 创建后立即设 socket 选项（SO_REUSEADDR、TCP_NODELAY 等）

---

## 三、绑定：bind() 系统调用

`bind()` 把 socket 与特定地址关联——服务端**必须** bind，客户端**通常**不 bind（由系统自动分配临时端口）。

### 3.1 AF_INET bind 详解

#### 3.1.1 inet_bind 源码

```c
// net/ipv4/af_inet.c
int inet_bind(struct socket *sock, struct sockaddr *uaddr, int addr_len)
{
    struct sock *sk = sock->sk;
    struct sockaddr_in *addr = (struct sockaddr_in *)uaddr;
    int err;

    /* 1. 地址长度校验 */
    if (addr_len < sizeof(struct sockaddr_in))
        return -EINVAL;

    /* 2. 端口字节序转换（host byte order） */
    snum = ntohs(addr->sin_port);
    
    /* 3. 端口范围检查 */
    if (snum && (snum < PROT_SOCK || snum > 65535))
        return -EACCES;
    
    /* 4. 调协议族 bind（TCP） */
    err = sk->sk_prot->get_port(sk, snum);
    if (err)
        return err;
    
    /* 5. 设置地址 */
    inet->inet_rcv_saddr = inet->inet_saddr = addr->sin_addr.s_addr;
    if (snum)
        inet->inet_sport = htons(snum);
    ...
}
```

**关键点**：
- `get_port(sk, snum)` 是关键——它在内核的 `tcp_bind_hash` 中查找可用端口
- `snum=0` 表示"由系统自动分配临时端口"（客户端默认行为）
- 端口冲突时 `get_port` 返回 `-EADDRINUSE`

#### 3.1.2 tcp_v4_get_port 端口分配算法

```c
// net/ipv4/tcp.c
int tcp_v4_get_port(struct sock *sk, unsigned short snum)
{
    /* 1. snum=0：从某个 base 开始找 */
    if (!snum) {
        for (...) {
            /* 哈希表查找空闲端口 */
        }
        return -EADDRINUSE;  // 找不到
    }
    
    /* 2. snum 非 0：检查该端口是否空闲 */
    /* SO_REUSEADDR 影响此处行为 */
    ...
}
```

**关键观察**：
- 端口分配的"原子性"靠哈希表 + 锁
- **SO_REUSEADDR** 允许 bind 到 TIME_WAIT 状态的端口——这是治理 TIME_WAIT 端口耗尽的关键

### 3.2 AF_UNIX bind 详解

#### 3.2.1 unix_bind 源码

```c
// net/unix/af_unix.c
static int unix_bind(struct socket *sock, struct sockaddr *uaddr, int addr_len)
{
    struct sock *sk = sock->sk;
    struct unix_sock *u = unix_sk(sk);
    struct sockaddr_un *sunaddr = (struct sockaddr_un *)uaddr;
    char *sun_path = sunaddr->sun_path;
    int err;

    /* 1. 地址长度校验 */
    if (addr_len < sizeof(sa_family_t) || addr_len > sizeof(struct sockaddr_un))
        return -EINVAL;

    /* 2. 路径型 UDS */
    if (sun_path[0]) {
        /* 2.1 检查路径长度 */
        if (addr_len == sizeof(sa_family_t))
            return -EINVAL;
        
        /* 2.2 查找路径是否已存在 */
        ...
        
        /* 2.3 创建 socket inode */
        err = unix_mknod(sun_path, ...);
    }
    /* 3. abstract 命名空间 */
    else {
        /* abstract 命名空间以 '\0' 开头 */
        ...
    }
    
    /* 4. 设置 unix_sock 的 addr */
    u->addr = kmalloc(sizeof(*u->addr) + addr_len, GFP_KERNEL);
    memcpy(u->addr->name, sunaddr, addr_len);
    
    /* 5. 加入 unix_socket_table */
    err = unix_hash(sk);
    ...
}
```

**关键点**：
- **路径型 UDS**：在文件系统创建 socket inode（`unix_mknod`）
  - 长度限制：108 字节（UNIX_PATH_MAX）
  - 路径已存在 → bind 失败（除非用 SO_REUSEADDR）
  - 关闭后路径**不自动删除**（需应用 unlink）——这是 06 篇讲的"路径残留"陷阱
- **abstract 命名空间**：sun_path[0]=0、sun_path[1]!=0
  - 不占用文件系统
  - 关闭后**自动删除**——无路径残留问题
  - 多个 socket 绑相同 abstract 路径 → 后者覆盖前者（SO_REUSEPORT）

#### 3.2.2 AF_UNIX bind 失败的常见原因

| 错误码 | 含义 | 典型场景 |
|--------|------|----------|
| `-EADDRINUSE` | 地址已占用 | 路径已存在 / abstract 冲突 |
| `-ENOENT` | 路径不存在 | 父目录被删 |
| `-EACCES` | 权限不足 | 父目录无写权限 |
| `-EINVAL` | 参数非法 | 路径过长 / 长度=sizeof(sa_family_t) |

### 3.3 Android 场景的 bind

#### 3.3.1 Zygote 启动时 bind 路径型 UDS

```java
// ZygoteServer.java（系统源码）
String zygoteSocketName = "zygote";
LocalServerSocket zygoteSocket = new LocalServerSocket(zygoteSocketName);
```

**底层调用链**：
```
LocalServerSocket(name)
  → new LocalSocketImpl()
  → socket(PF_UNIX, SOCK_STREAM, 0)
  → bind(/dev/socket/zygote)
  → listen(1)  // 1=backlog
```

**实战**：
- Zygote listen backlog=1（旧版本）——**这是隐患**
- 新版本（AOSP 14+）使用 `usap`（Unsocket Accept Pool）改善

#### 3.3.2 adb daemon bind 端口

```cpp
// adbd.cpp
int adb_listen_transport(atransport *t, usb_handle *h) {
    ...
    t->fd = socket_network_client(...);  // adb server 端连接
}
```

**底层**：adbd 监听 TCP 5555 端口 + UDS `/dev/socket/adbd`（新版）

**稳定性关联**：
- `adb_listen` 失败 → adb 不可用 → 调试通道断
- 5555 端口被占 → adb 启动失败

### 3.4 bind 与稳定性的关系

**bind 失败 P0 场景**：
- Zygote bind 失败 → 所有 app 启动失败（P0）
- adb bind 5555 失败 → adb 不可用（P0 调试场景）
- 应用 bind 80 端口失败 → 服务启动失败

**bind 慢 / 阻塞场景**：
- bind 通常**不阻塞**——但在内核端口分配哈希表竞争时可能短暂阻塞
- 实际场景中 bind 慢通常是因为**前面的 socket 未关闭**导致端口被占

**治理**（08 §4）：
- bind 前捕获 `-EADDRINUSE` → 报错并提示端口被占
- bind 时设 `SO_REUSEADDR`（TIME_WAIT 端口可重用）
- bind 时设 `SO_REUSEPORT`（多 socket 监听同一端口——内核做负载均衡）
- 路径型 UDS bind 前 `unlink` 旧 socket 文件（避免路径残留）

---

## 四、监听：listen() 系统调用

`listen()` 把 socket 转换为**服务端监听 socket**——从此 socket 等待客户端连接。

### 4.1 AF_INET listen 详解

#### 4.1.1 inet_listen 源码

```c
// net/ipv4/af_inet.c
int inet_listen(struct socket *sock, int backlog)
{
    struct sock *sk = sock->sk;
    int err;

    /* 1. 状态检查 */
    if (sock->state != SS_UNCONNECTED)
        return -EINVAL;  // 已 listen / connect 不能再次 listen

    /* 2. backlog 调整（关键） */
    sk->sk_max_ack_backlog = min_t(int, backlog, READ_ONCE(somaxconn));
    // 实际 backlog = min(用户传入, somaxconn)
    
    /* 3. 调协议族 listen */
    if (sk->sk_prot->listen) {
        err = sk->sk_prot->listen(sk, backlog);
        if (err)
            return err;
    }
    
    /* 4. 设置 BSD 状态 */
    sock->state = SS_LISTENING;
    
    return 0;
}
```

**关键**：
- `backlog` 被 `min(用户值, somaxconn)` 截断——**用户传 1000 而 somaxconn=4096，实际是 1000**
- `sk->sk_max_ack_backlog` 是**全连接队列上限**（accept queue）
- 真正的半连接队列上限是 `tcp_max_syn_backlog`（详见 05 篇）

#### 4.1.2 tcp_listen 源码

```c
// net/ipv4/tcp.c
int tcp_listen(struct sock *sk, int backlog)
{
    struct inet_connection_sock *icsk = inet_csk(sk);
    struct tcp_fastopen_context *fastopen;
    int err;

    /* 1. 状态检查 */
    if (((1 << sk->sk_state) & (TCPF_CLOSE | TCPF_LISTEN)) != TCPF_CLOSE)
        return -EINVAL;

    /* 2. 分配 accept 队列 */
    sk->sk_state = TCP_LISTEN;
    ...
    sk_acceptq_added(sk);  // 初始化 accept queue
    
    return 0;
}
```

**关键状态**：
- `sk->sk_state = TCP_LISTEN` 是**进入 listen 状态的标志**
- 此时 `inet_hash` 把 socket 加入 **TCP 的 listen hash 表**——内核会通过它做 SYN 匹配
- 半连接队列（`SYN queue`）的内存此时分配

#### 4.1.3 Zygote listen 的特殊点

```java
// ZygoteServer.java
ZygoteServer() throws RuntimeException {
    ...
    try {
        LocalServerSocket zygoteSocket = new LocalServerSocket("zygote");
        ...
    }
}
```

**关键**：
- Zygote 监听 **UDS**（不是 TCP）——走 `unix_listen` 而非 `tcp_listen`
- Zygote listen 几乎不耗资源——UDS 队列较短
- **Zygote 监听不阻塞**——但 accept 慢会导致 AMS fork 超时（这是 07 篇的 P0 风险）

### 4.2 AF_UNIX listen 详解

```c
// net/unix/af_unix.c
static int unix_listen(struct socket *sock, int len)
{
    struct sock *sk = sock->sk;
    struct unix_sock *u = unix_sock_lock(sk);
    int err;

    /* 1. 状态检查 */
    if (sock->state != SS_UNCONNECTED)
        return -EINVAL;

    /* 2. 必须先 bind */
    if (!u->addr)
        return -EINVAL;

    /* 3. 长度截断 */
    backlog = min_t(int, len, 128);  // UDS 队列上限 128
    
    /* 4. 分配 accept 队列 */
    sk->sk_max_ack_backlog = backlog;
    
    /* 5. 设置状态 */
    sock->state = SS_LISTENING;
    sk->sk_state = TCP_LISTEN;  // 注意：UDS 也用 TCP_LISTEN 标记
    
    /* 6. 加入 unix_socket_table 的 listener 部分 */
    list_add_tail(&u->link, &sk->sk_net->unx_listeners);
    
    return 0;
}
```

**关键**：
- UDS 的 backlog 上限是 128（写死）——即使 somaxconn=4096
- UDS 没有半连接队列（无 SYN 概念）——全连接队列就是 UDS 的全部
- **UDS 的全连接队列满** → connect 失败（`-EAGAIN` 或 `-ECONNREFUSED`）

### 4.3 listen 与稳定性的关系

**listen 慢 / 失败 P0 场景**：
- Zygote listen 失败 → 所有 app 启动失败（P0）
- adb listen 5555 失败 → adb 不可用（P0）

**backlog 不当 P0 场景**：
- Zygote listen backlog=1（旧版本）——**单点故障**
- 应用服务端 listen backlog=8（默认）——**高并发时连接被拒**
- LocalServerSocket backlog 满 → 系统 daemon 不可用

**治理**（08 §4.3）：
- 高并发服务端 backlog = `min(业务峰值并发 × 1.5, somaxconn)`
- Zygote：使用 USAP 替代单 listen socket
- adb：写死 backlog=128（可考虑 vendor 改大）
- 监控 `ListenOverflows`（全连接队列溢出）—— > 0 立即告警

**监控点**（08 §3.2.2）：
- `/proc/net/netstat` 的 `TcpExt: ListenOverflows ListenDrops`
- `ss -ln` 输出的 `Send-Q`（实际是 accept queue 长度）

---

## 五、接受：accept() 系统调用

`accept()` 是**服务端**获取新连接的入口——它会**创建新 socket 对象**承载连接。

### 5.1 AF_INET accept 详解

#### 5.1.1 inet_accept 源码

```c
// net/ipv4/af_inet.c
int inet_accept(struct socket *sock, struct socket *newsock, int flags,
                bool kern)
{
    struct sock *sk1 = sock->sk;
    int err = -EINVAL;

    /* 1. 检查 listen socket 状态 */
    if (sk1->sk_state != TCP_LISTEN)
        goto out;

    /* 2. 清理 newsock */
    newsock->state = SS_UNCONNECTED;
    newsock->ops = sock->ops;  // 继承 ops

    /* 3. 调协议族 accept（关键） */
    err = sk1->sk_prot->accept(sk1, newsock, flags, kern);
    if (err != 0)
        goto out;

    /* 4. 设置 newsock 状态 */
    newsock->state = SS_CONNECTED;
    ...
}
```

#### 5.1.2 inet_csk_accept 核心逻辑

```c
// net/ipv4/inet_connection_sock.c
struct sock *inet_csk_accept(struct sock *sk, int flags, int *err, bool kern)
{
    struct inet_connection_sock *icsk = inet_csk(sk);
    struct request_sock *req;
    struct sock *newsk;

    /* 1. 错误检查 */
    if (sk->sk_state != TCP_LISTEN)
        goto out_err;

    /* 2. 检查 accept queue 是否有连接 */
    if (reqsk_queue_empty(&icsk->icsk_accept_queue)) {
        long timeo = sock_rcvtimeo(sk, flags & O_NONBLOCK);
        
        /* 2.1 阻塞模式：等待 */
        if (!timeo)
            goto out_err;
        timeo = inet_csk_wait_for_connect(sk, timeo);
        if (timeo)
            goto out_err;
    }
    
    /* 3. 取出第一个连接（先进先出） */
    req = reqsk_queue_remove(&icsk->icsk_accept_queue);
    newsk = req->sk;
    
    /* 4. 完成三次握手的最后一步（服务端发 ACK） */
    ...
    
    return newsk;
}
```

**关键观察**：
- **accept queue 是 FIFO 队列**——连接按到达顺序被 accept
- accept queue 为空 + 阻塞模式 → 进程挂入 sk->sk_sleep → 等新连接
- accept queue 满 → 新连接被丢弃（ListenDrops 增加）

#### 5.1.3 accept 与 epoll 的协作

```c
// 服务端典型代码
struct epoll_event ev;
int listenfd = socket(AF_INET, SOCK_STREAM, 0);
bind(listenfd, ...);
listen(listenfd, 128);
epoll_ctl(epfd, EPOLL_CTL_ADD, listenfd, &ev);

while (1) {
    int n = epoll_wait(epfd, events, MAX, -1);
    for (int i = 0; i < n; i++) {
        if (events[i].data.fd == listenfd) {
            int connfd = accept(listenfd, ...);  // 非阻塞模式
            if (connfd < 0) continue;
            // 处理 connfd
        }
    }
}
```

**关键**：
- epoll 监听 listenfd 的 **EPOLLIN** 事件——由 `tcp_poll()` 在 accept queue 非空时返回
- **accept 必须设为非阻塞**——避免某个 accept 阻塞影响整个事件循环
- 这是 OkHttp、Netty 等网络库的标准模式

### 5.2 AF_UNIX accept 详解

```c
// net/unix/af_unix.c
static int unix_accept(struct socket *sock, struct socket *newsock, int flags,
                       bool kern)
{
    struct sock *sk = sock->sk;
    struct sock *tsk;
    struct unix_sock *u = unix_sk(sk);
    int err;

    /* 1. 状态检查 */
    if (sock->state != SS_LISTENING)
        return -EINVAL;

    /* 2. 等待连接（与 AF_INET 类似） */
    ...
    tsk = unix_mkname(sk, ...);  // 从 accept queue 取连接
    
    /* 3. 接受连接 */
    unix_state_lock(tsk);
    newsock->state = SS_CONNECTED;
    sock_graft(tsk, newsock);   // 关联 newsock 和 tsk
    unix_state_unlock(tsk);
    
    return 0;
}
```

**关键**：
- UDS 的 accept queue 也是 FIFO
- **UDS 没有"路径校验"**——accept 出的 socket 看不到客户端的路径（除 SO_PEERPID）
- **UDS 不需要 ACK**——accept 后立即可用（不像 TCP 需服务端 ACK 完成三次握手）

### 5.3 accept 与稳定性的关系

**accept 慢 / 阻塞 P0 场景**：
- **服务端 accept 慢** → accept queue 满 → ListenDrops 增加 → 新连接被丢弃
- **阻塞 accept** + epoll 监听 → 整个事件循环卡住 → 所有连接无响应
- **Zygote accept 慢** → 所有 app fork 超时 → P0 启动 ANR

**accept 异常处理**：
```java
// 错误写法
while (running) {
    int connfd = accept(listenfd, ...);  // 阻塞 + 无错误处理
    handle(connfd);
}

// 正确写法
listenfd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);  // 非阻塞
...
while (running) {
    int n = epoll_wait(epfd, events, MAX, -1);
    for (int i = 0; i < n; i++) {
        if (events[i].data.fd == listenfd) {
            int connfd = accept4(listenfd, ..., SOCK_NONBLOCK);  // 非阻塞 accept
            if (connfd < 0) {
                if (errno == EAGAIN) break;  // accept queue 暂时空
                if (errno == EMFILE) handle_fd_exhausted();  // fd 耗尽
                continue;
            }
            epoll_ctl(epfd, EPOLL_CTL_ADD, connfd, &ev);
        }
    }
}
```

**关键**：
- **必须用 SOCK_NONBLOCK 模式 accept**——阻塞 accept 在 epoll 中是反模式
- 必须处理 **EMFILE**（进程 fd 耗尽）和 **ENFILE**（系统 fd 耗尽）——临时关闭部分连接以释放 fd

**治理**（08 §4.2）：
- 服务端 accept 必须在工作线程池——accept 慢的主线程会被反压
- 监控 `ListenOverflows` / `ListenDrops`——> 0 立即排查
- 监控 accept 队列深度（`/proc/net/tcp` 的 `rx_queue` 字段）

---

## 六、连接：connect() 与 TCP 三次握手

`connect()` 是**客户端**发起连接的入口——它触发 **TCP 三次握手**（对 AF_INET）或**直连**（对 AF_UNIX）。

### 6.1 AF_INET connect 详解

#### 6.1.1 inet_stream_connect 源码

```c
// net/ipv4/af_inet.c
int inet_stream_connect(struct socket *sock, struct sockaddr *uaddr,
                        int addr_len, int flags)
{
    struct sock *sk = sock->sk;
    int err;
    long timeo;

    /* 1. 状态检查 */
    switch (sock->state) {
    case SS_UNCONNECTED:
        /* 合法：未连接状态可以 connect */
        break;
    case SS_CONNECTED:
        return -EISCONN;  // 已连接不能再 connect
    case SS_CONNECTING:
        /* 状态机重复调用：EINPROGRESS */
        if (... flags & O_NONBLOCK)
            return -EINPROGRESS;
        ...
    }

    /* 2. 调用协议族 connect（关键：发起 SYN） */
    err = sk->sk_prot->connect(sk, uaddr, addr_len);
    if (err < 0)
        return err;

    /* 3. 设置 BSD 状态 */
    sock->state = SS_CONNECTING;
    timeo = sock_sndtimeo(sk, flags & O_NONBLOCK);
    
    /* 4. 等待连接完成 */
    if (!timeo || !inet_wait_for_connect(sk, timeo, writebias))
        goto out;
    
    err = sock_intr_errno(timeo);
    if (err != 0)
        goto out;
    
    /* 5. 错误检查 */
    err = sk->sk_err;
    if (!err)
        sock->state = SS_CONNECTED;
    ...
}
```

**关键观察**：
- `connect()` 是**同步阻塞**——直到三次握手完成或超时
- 非阻塞模式立即返回 `-EINPROGRESS`——通过 epoll 监听 `EPOLLOUT` 事件判断完成
- 协议层 `sk->sk_prot->connect` 跳到 `tcp_v4_connect`

#### 6.1.2 tcp_v4_connect 发起 SYN

```c
// net/ipv4/tcp_ipv4.c
int tcp_v4_connect(struct sock *sk, struct sockaddr *uaddr, int addr_len)
{
    struct inet_sock *inet = inet_sk(sk);
    struct tcp_sock *tp = tcp_sk(sk);
    int err;

    /* 1. 状态检查 */
    if (sk->sk_state != TCP_CLOSE)
        return -EALREADY;

    /* 2. 路由查找 */
    rt = ip_route_connect(...);
    if (IS_ERR(rt))
        return PTR_ERR(rt);

    /* 3. 设置目的地址 */
    inet->inet_dport = usin->sin_port;
    inet->inet_daddr = usin->sin_addr.s_addr;
    ...

    /* 4. 路由缓存 + 设置源地址 */
    inet_sk_rx_dst_set(sk, ...);
    
    /* 5. 设置 TCP 状态 */
    sk->sk_state = TCP_SYN_SENT;
    sk_set_tx_timestamp(sk, ...);
    
    /* 6. 初始化连接状态 */
    tp->write_seq = secure_tcp_seq(inet->inet_saddr, inet->inet_daddr, ...);
    tp->snd_nxt = tp->write_seq + 1;
    
    /* 7. 发送 SYN 包（实际是 skb + TCP 选项） */
    err = tcp_connect(sk);
    ...
}
```

**关键**：
- `sk->sk_state = TCP_SYN_SENT`——客户端进入 SYN_SENT 状态
- `secure_tcp_seq` 生成**初始序列号（ISN）**——防 TCP 序列号攻击
- 实际发包在 `tcp_connect`（更底层）

#### 6.1.3 三次握手完整状态机

```
客户端                              服务端
  │                                   │
  │  1. CLOSE                         │ LISTEN
  │     ↓                             │
  │  2. SYN_SENT                     │
  │     → SYN (seq=x) ──────────────→  │
  │                                   │ 3. SYN_RECV
  │                                   │  ← SYN+ACK (seq=y, ack=x+1)
  │  ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
  │  4. ESTABLISHED                   │
  │     → ACK (seq=x+1, ack=y+1) ───→  │
  │                                   │ 5. ESTABLISHED
  │                                   │
  │     可收发数据                      │
```

**内核对应**：

| 步骤 | 客户端状态 | 服务端状态 | 内核动作 |
|------|-----------|-----------|----------|
| 1. connect 调用 | TCP_CLOSE | TCP_LISTEN | 客户端 `sk_state=TCP_SYN_SENT` |
| 2. 发 SYN | TCP_SYN_SENT | TCP_LISTEN | 客户端 `tcp_connect` 构造 SYN |
| 3. 服务端收 SYN | TCP_SYN_SENT | TCP_SYN_RECV | 服务端 `tcp_v4_rcv` → 收 SYN → `conn_request` → 发 SYN+ACK |
| 4. 客户端收 SYN+ACK | TCP_SYN_SENT → TCP_ESTABLISHED | TCP_SYN_RECV | 客户端 `tcp_rcv_state_process` → 发 ACK |
| 5. 服务端收 ACK | TCP_ESTABLISHED | TCP_SYN_RECV → TCP_ESTABLISHED | 服务端 `tcp_child_process` → 把连接移到 accept queue |

**关键**：
- **三次握手在客户端**：2 个状态切换（SYN_SENT → ESTABLISHED）
- **三次握手在服务端**：2 个状态切换（LISTEN → SYN_RECV → ESTABLISHED）
- **半连接队列** 存的是 `SYN_RECV` 状态的连接（详见 05 篇）
- **全连接队列** 存的是 `ESTABLISHED` 状态、等待 `accept()` 的连接

#### 6.1.4 connect 超时与重试

```c
// net/ipv4/tcp.c
int tcp_connect(struct sock *sk)
{
    ...
    /* 设置 SYN 重传定时器 */
    inet_csk_reset_xmit_timer(sk, ICSK_TIME_RETRANS,
                               inet_csk(sk)->icsk_rto, TCP_RTO_MAX);
    ...
}
```

**关键参数**：
- `tcp_synack_retries` = 5（默认）——服务端 SYN+ACK 重传次数
- `tcp_syn_retries` = 6（默认）——客户端 SYN 重传次数
- 每次重传 timeout **翻倍**——1s → 2s → 4s → 8s → 16s → 32s
- 总超时：客户端 SYN 约 1+2+4+8+16+32+64=127 秒；服务端 SYN+ACK 约 1+2+4+8+16+32=63 秒

**实战**：
- **connect() 阻塞 60 秒无响应** → 大概率是 SYN 丢包或对端无响应
- **非阻塞 connect() + epoll**：在 `EPOLLOUT` 事件到来后调 `getsockopt(SO_ERROR)` 检查是否真连接成功

### 6.2 AF_UNIX connect 详解

```c
// net/unix/af_unix.c
static int unix_stream_connect(struct socket *sock, struct sockaddr *uaddr,
                                int addr_len, int flags)
{
    struct sock *sk = sock->sk;
    struct sockaddr_un *sunaddr = (struct sockaddr_un *)uaddr;
    struct sock *other;
    int err;

    /* 1. 状态检查 */
    if (sock->state != SS_UNCONNECTED)
        return -EISCONN;

    /* 2. 查找对端 socket */
    other = unix_find_other(sunaddr, addr_len, &err);
    if (!other)
        return err;

    /* 3. 检查对端状态（必须 LISTENING） */
    if (other->sk_state != TCP_LISTEN) {  // UDS 复用 TCP_LISTEN
        err = -ECONNREFUSED;
        goto out;
    }
    
    /* 4. 设置状态 */
    sock->state = SS_CONNECTING;
    sk->sk_state = TCP_SYN_SENT;  // UDS 借用 TCP 状态名
    
    /* 5. 加入对端的 accept queue */
    ...
    other = unix_mkname(sk, ...);
    ...
    unix_state_lock(other);
    __skb_queue_tail(&other->sk_receive_queue, ...);
    other->sk_data_ready(other);  // 唤醒对端 accept
    unix_state_unlock(other);
    
    /* 6. 等待对端 accept */
    timeo = sock_sndtimeo(sk, flags & O_NONBLOCK);
    if (!timeo)
        return -EINPROGRESS;
    err = unix_wait_for_connect(sk, timeo);
    ...
    
    sock->state = SS_CONNECTED;
    sk->sk_state = TCP_ESTABLISHED;
    return 0;
}
```

**关键观察**：
- **UDS 的 connect 没有三次握手**——直接把连接放到对端 accept queue
- 但 UDS 复用了 TCP 状态名（`TCP_SYN_SENT`、`TCP_ESTABLISHED`）——这只是常量复用，不代表有三次握手
- **UDS 的"connect 成功"是 atomic**——不会有半连接状态

### 6.3 connect 与稳定性的关系

**connect 失败 / 慢 P0 场景**：
- **网络 connect 超时** → 应用 ANR（主线程同步 connect）
- **Zygote connect 慢** → 进程启动 ANR
- **UDS connect 失败** → LocalServerSocket 不可达 → 系统服务挂

**connect 错误码**：

| 错误码 | 含义 | 典型场景 |
|--------|------|----------|
| `-ECONNREFUSED` | 连接被拒 | 服务端未 listen / 路径不存在 / abstract 未绑定 |
| `-ETIMEDOUT` | 连接超时 | 网络丢包 + SYN 重传耗尽 |
| `-EHOSTUNREACH` | 主机不可达 | 路由失败 / 防火墙 drop |
| `-ENETUNREACH` | 网络不可达 | 无路由到目标网络 |
| `-EINPROGRESS` | 连接进行中 | 非阻塞模式 + 握手未完成 |
| `-EALREADY` | 已有连接在进行 | 重复调用 connect |

**connect 异常处理**：
```java
// 错误写法
try {
    sock.connect(new InetSocketAddress(host, port));
} catch (IOException e) {
    // connect 超时 → 60 秒
}

// 正确写法（用 OkHttp 等库）
Request request = new Request.Builder().url(url).build();
Call call = okHttpClient.newCall(request);
call.timeout()  // 配置 connectTimeout、readTimeout、writeTimeout
```

**治理**（08 §4.2.3）：
- connect timeout 必设（建议 5-10 秒）
- 应用层禁止主线程同步 connect（主线程 socket IO 触发 ANR）
- 监控 `SYN_SENT` 状态时长——> 30s 立即告警
- UDS 路径型：connect 前确保路径存在；abstract：connect 前确保对端已 listen

---

## 七、关闭：close() 与 TCP 四次挥手

`close()` 是 socket 的"消亡路径"——但**关闭不是"立即释放"**，对 TCP 而言要经过**四次挥手**状态机。

### 7.1 close() vs shutdown() 关键差异

**close()**：
- 释放 fd
- 减少 sock 引用计数
- 在引用计数归 0 时发起四次挥手
- 之后 socket 不能再用——`read()` `write()` 都返回错误

**shutdown()**：
- 不释放 fd（不调用 close）
- 关闭一个方向：
  - `shutdown(SHUT_RD)` = 关闭读
  - `shutdown(SHUT_WR)` = 关闭写
  - `shutdown(SHUT_RDWR)` = 关闭读写
- 可双向独立关闭
- 触发**对端 TCP 状态切换**——`shutdown(SHUT_WR)` 立即发 FIN

**核心差异**：

| 维度 | close() | shutdown() |
|------|---------|-----------|
| 释放 fd | ✓ | ✗（只关方向） |
| sock 引用计数 | -1 | 不变 |
| 能否再使用 | ✗ | ✓（可读或可写） |
| 触发 FIN | 引用计数归 0 时 | 立即（`SHUT_WR`） |
| 半关闭支持 | ✗ | ✓（`SHUT_RD` / `SHUT_WR`） |
| HTTP 半关闭 | ✗ | ✓（Content-Length 后） |

**实战**：
- HTTP/1.1 长连接：`shutdown(SHUT_WR)` 通知对端"我写完了"——对端才能响应（**Content-Length 边界**）
- 默认 close() 不会立即发 FIN——因为引用计数可能 > 0（dup / fork / epoll ref）
- **shutdown(SHUT_WR) 不会减少引用计数**——所以可以安全地"先 shutdown 再 close"

### 7.2 close() 完整调用链

```c
// 用户态
close(fd);
   ↓
// fs/open.c
int filp_close(struct file *filp, fl_owner_t id)
{
    ...
    fput(filp);  // 减少 file->f_count
}
   ↓
// kernel/fork.c 等
void fput(struct file *file)
{
    if (atomic_long_dec_and_test(&file->f_count))
        __fput(file);  // 引用计数归 0 时调用
}
   ↓
// net/socket.c
static void __fput(struct file *file)
{
    ...
    file->f_op->release(file, file->f_path.dentry->d_inode);
    // 调 socket_file_ops.release = sock_close
}
   ↓
static int sock_close(struct inode *inode, struct file *filp)
{
    struct socket *sock = filp->private_data;
    sock->ops->release(sock);  // → inet_release / unix_release
    sock_release(sock);        // 释放 socket
    return 0;
}
```

**关键观察**：
- `close(fd)` 不一定立即调用 `sock_close`——要等 `file->f_count` 归 0
- `file->f_count` 受**多次 dup、fork、epoll 引用**等影响
- 真正的"释放"是 `__fput`——但应用层 close() 触发的"关闭语义"在 `sock_close` 中

### 7.3 inet_release 与 TCP 四次挥手

```c
// net/ipv4/af_inet.c
int inet_release(struct socket *sock)
{
    struct sock *sk = sock->sk;
    ...
    
    /* 1. 跳过监听 socket（监听 socket 的 release 不发 FIN） */
    if (sk->sk_state == TCP_LISTEN) {
        /* 直接清理 */
        sock_orphan(sk);  // 标记为孤儿
        ...
        return 0;
    }
    
    /* 2. 对已连接 socket 调协议族 close */
    if (sk->sk_prot->close) {
        sk->sk_prot->close(sk, timeout);
        // → tcp_close(sk, timeout)
    }
    
    sock->sk = NULL;
    return 0;
}
```

**关键**：
- **监听 socket close 不发 FIN**——只清理
- **已连接 socket close 触发四次挥手**——通过 `tcp_close`

### 7.4 tcp_close 源码

```c
// net/ipv4/tcp.c
void tcp_close(struct sock *sk, long timeout)
{
    struct tcp_sock *tp = tcp_sk(sk);
    int state = sk->sk_state;

    /* 1. 状态分流 */
    if (state == TCP_LISTEN) {
        tcp_set_state(sk, TCP_CLOSE);
        /* 清理监听状态 */
        ...
    } else if (state == TCP_ESTABLISHED) {
        /* 关键：四次挥手的起点 */
        tcp_set_state(sk, TCP_FIN_WAIT1);
        sk->sk_shutdown |= SEND_SHUTDOWN;
        tcp_send_fin(sk);   // 发送 FIN
    } else if (state == TCP_CLOSE_WAIT) {
        /* 被动关闭：应用层 close 走这里 */
        tcp_set_state(sk, TCP_LAST_ACK);
        sk->sk_shutdown |= SEND_SHUTDOWN;
        tcp_send_fin(sk);
    } else if (state == TCP_SYN_SENT || state == TCP_SYN_RECV) {
        /* 握手未完成：直接 RST */
        ...
    }
    ...
}
```

**关键**：
- `TCP_ESTABLISHED` 主动 close → `TCP_FIN_WAIT1` → 发 FIN
- `TCP_CLOSE_WAIT` 主动 close → `TCP_LAST_ACK` → 发 FIN
- `TCP_SYN_SENT/RECV` 异常 close → 直接 RST（无 FIN 过程）

### 7.5 TCP 四次挥手完整状态机

```
主动关闭方                            被动关闭方
  │                                    │
  │  ESTABLISHED                       │ ESTABLISHED
  │  close()                            │
  │     ↓                               │
  │  FIN_WAIT1                          │
  │  → FIN ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ →   │
  │                                    │ 收 FIN
  │                                    │ close()
  │                                    │   ↓
  │                                    │ CLOSE_WAIT
  │  ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │ → ACK
  │  FIN_WAIT2                          │
  │  (等对方应用 close)                   │ 应用关闭
  │                                    │   ↓
  │  ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │ → FIN
  │  TIME_WAIT                          │ LAST_ACK
  │  → ACK ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ →   │
  │                                    │ 收 ACK
  │                                    │   ↓
  │                                    │ CLOSE
  │  2MSL 等待 (60s)                    │
  │     ↓                               │
  │  CLOSE                              │
```

**对应 4 个分组**（与 3 次握手对比）：
- **FIN**（主动方发）
- **ACK**（被动方确认 FIN）
- **FIN**（被动方发——如果被动方先 close）
- **ACK**（主动方确认第二个 FIN）

**为什么需要 4 次而不是 3 次**：
- **TCP 是全双工**——每个方向都需单独关闭
- 被动关闭方可能仍在发送数据——所以 ACK 和 FIN 不能合并
- 主动方 close 后，被动方可能在继续发送剩余数据（此时主动方在 FIN_WAIT2）

### 7.6 四个关键 TCP 关闭状态详解

#### 7.6.1 FIN_WAIT1（主动关闭方发 FIN 后）

**含义**：主动关闭方发完 FIN，等待对端 ACK

**典型时长**：1 RTT（通常 1-100ms）

**异常信号**：
- FIN_WAIT1 持续 60 秒+ → 对端不响应 ACK（网络丢包或对端无响应）
- 大量 FIN_WAIT1 → SYN 拥塞 / 对端服务挂

#### 7.6.2 FIN_WAIT2（收到对端 ACK，等待对端 FIN）

**含义**：主动方收到 ACK，但等对端发 FIN

**典型时长**：长——取决于对端应用何时 close

**异常信号**：
- FIN_WAIT2 持续 > tcp_fin_timeout（默认 60 秒）→ 对端没 close
- 大量 FIN_WAIT2 → 对端应用泄漏 close

**与稳定性**：
- 对端 "半关闭"：关闭了写但没关闭读——主动方会一直等 FIN
- **服务端典型 bug**：`response.close()` 后没调 `socket.close()`——socket 不发 FIN，客户端永久等

#### 7.6.3 CLOSE_WAIT（被动方收到 FIN）

**含义**：对端发来 FIN，本端已确认；但本端应用还没 close

**典型时长**：取决于应用何时 close——**0 到无穷大**

**异常信号（最关键）**：
- **CLOSE_WAIT 持续 > 0 且增长** → **应用层未 close**（P0 必修）
- 100 个 CLOSE_WAIT → 应用至少 100 个 socket 未 close
- **不要在生产环境看到 CLOSE_WAIT 长时间存在**

**根因**：
- 应用未调 `close()` / `dispose()` ——GC 慢 + 引用泄漏
- `try-catch` 中未 `finally close`
- 异步/协程模型中 close 逻辑被绕过
- **永远记住：CLOSE_WAIT = 应用层 bug**

#### 7.6.4 TIME_WAIT（主动方收完对端 FIN 并回 ACK）

**含义**：等待 2MSL（Maximum Segment Lifetime）以确保对端收到 ACK

**典型时长**：60 秒（AOSP 默认）

**为什么需要 TIME_WAIT**：

1. **确保对端收到 ACK**：如果 ACK 丢失，对端会重传 FIN；TIME_WAIT 期间可以重发 ACK
2. **避免新旧连接混淆**：TIME_WAIT 期间旧 socket 仍占用端口——防止旧连接的延迟包到达新连接

**TIME_WAIT 的"60 秒"来源**：
- MSL（Maximum Segment Lifetime）= 30 秒（业内常用）
- 2MSL = 60 秒
- 内核参数 `net.ipv4.tcp_fin_timeout` 可调

**异常信号**：
- TIME_WAIT > 5000 → 短连接高频
- TIME_WAIT 占满可用端口 → 短连接失败（`-EADDRINUSE`）

**TIME_WAIT 优化**：
- `tcp_tw_reuse=1`：复用 TIME_WAIT 端口给**新连接的 client**
- `tcp_tw_recycle`：**已废弃**——会引起 NAT 问题
- `tcp_max_tw_buckets`：限制 TIME_WAIT 数量上限（默认 262144）

#### 7.6.5 LAST_ACK（被动方发 FIN 后）

**含义**：被动关闭方发完 FIN，等对端 ACK

**典型时长**：1 RTT

**异常信号**：LAST_ACK 持续 60 秒+ → 对端不响应 ACK

### 7.7 SO_LINGER 选项（关闭的精细控制）

```c
struct linger {
    int l_onoff;   // 0 = 关闭，1 = 启用
    int l_linger;  // 等待时长（秒）
};
setsockopt(fd, SOL_SOCKET, SO_LINGER, &linger, sizeof(linger));
```

**行为矩阵**：

| l_onoff | l_linger | close() 行为 |
|---------|----------|--------------|
| 0 | — | 默认：立即返回，FIN 由后台发送 |
| 1 | 0 | 立即返回 + **发送 RST**（不是 FIN）——强制中断 |
| 1 | > 0 | **阻塞等待**直到对端 ACK 或超时 |
| 1 | -1 | 等对端确认，无超时 |

**实战**：
- `SO_LINGER(0)`：**慎用**——RST 会让对端丢失接收 buffer 中的数据
- `SO_LINGER(5)`：用于协议要求"对端必须收到"——但会阻塞 close
- 默认行为（无 SO_LINGER）：**绝大多数情况最优**——close 立即返回，FIN 后台发送

### 7.8 shutdown(SHUT_WR) 关闭流程

```c
// net/socket.c
int __sys_shutdown(int fd, int how)
{
    struct socket *sock;
    ...
    sock = sockfd_lookup(fd, &fput_needed);
    if (!sock)
        return -EBADF;
    
    err = sock->ops->shutdown(sock, how);
    ...
}
```

```c
// net/ipv4/af_inet.c
static int inet_shutdown(struct socket *sock, int how)
{
    struct sock *sk = sock->sk;
    int err = 0;

    /* 1. 关闭写 */
    if (how == SHUT_WR || how == SHUT_RDWR) {
        if (!sk->sk_prot->send_shutdown) {
            sk->sk_shutdown |= SEND_SHUTDOWN;
            sk->sk_state_change(sk);
        } else {
            sk->sk_prot->send_shutdown(sk, how);
        }
    }
    
    /* 2. 关闭读 */
    if (how == SHUT_RD || how == SHUT_RDWR) {
        sk->sk_shutdown |= RCV_SHUTDOWN;
        sk_state_change(sk);
    }
    
    return err;
}
```

**关键**：
- `shutdown(SHUT_WR)` 立即发 FIN——不减少引用计数
- `shutdown(SHUT_RD)` 标记 RCV_SHUTDOWN——之后 read 返回 0（EOF）
- **HTTP 协议的关键**：服务器发完 response 后 `shutdown(SHUT_WR)`——客户端知道响应完整

### 7.9 close 与 sock 引用计数

**FD 泄漏的本质** = `file->f_count > 0` 或 `sk->sk_refcnt > 0` 持续时间过长。

**多次 dup**：
```c
int s1 = socket(AF_INET, SOCK_STREAM, 0);
int s2 = dup(s1);
int s3 = dup(s1);
close(s1);  // s1 关闭，sock 引用计数 2
close(s2);  // sock 引用计数 1
close(s3);  // sock 引用计数 0 → 真正释放
```

**fork 的影响**：
```c
int s = socket(...);
pid_t pid = fork();
if (pid == 0) {
    // 子进程继承 fd——但不需要它
    // 必须 close(s) 否则父进程 close(s) 时子进程仍持有
    // ★ 子进程必须显式 close(fd) 除非用 SOCK_CLOEXEC
}
```

**epoll 的影响**：
```c
epoll_ctl(epfd, EPOLL_CTL_ADD, fd, &ev);  // epoll 增加 fd 引用
// 之后 close(fd) 不会真正释放——epoll 仍持有引用
// 必须 epoll_ctl(EPOLL_CTL_DEL) 才能释放
```

**SOCK_CLOEXEC**：fork 时自动关闭 fd——避免引用泄漏

### 7.10 close 与稳定性的关系

**close 异常 P0 场景**：
- **应用未 close** → CLOSE_WAIT 累积 → fd 耗尽 → P0
- **shutdown 不当** → 对端永久等 FIN → FIN_WAIT2 累积 → 端口耗尽
- **未 SOCK_CLOEXEC** → fork 后子进程泄漏 fd → 进程组 fd 耗尽

**close 慢 / 阻塞**：
- `SO_LINGER(timeout)` 会阻塞 close——`timeout` 秒内等 ACK
- 默认 close 不阻塞——但内核层面要继续发 FIN

**治理**（08 §4.1）：
- **fdsan 检测**（AOSP 14+）——自动发现 fd 泄漏
- **try-with-resources / finally**——保证 close 被调用
- **SOCK_CLOEXEC 默认开**——避免 fork 泄漏
- **HTTP 客户端用 Connection: close**（或 keep-alive 配连接池）——避免 TIME_WAIT
- **监控 CLOSE_WAIT > 0**——立即告警

---

## 八、特殊状态与边界

### 8.1 RST（复位）vs FIN（正常关闭）

**FIN**：正常关闭——4 次挥手，对端收完数据
**RST**：异常关闭——直接关闭，对端可能丢数据

**触发 RST 的常见情况**：

| 场景 | 触发 RST 的原因 |
|------|-----------------|
| **数据发到已 close 的 socket** | 接收方早已关闭，发方后写的包触发 RST |
| **监听 socket 收到不期望的 SYN** | 服务端没有 listener 监听该端口 |
| **连接队列满** | `tcp_abort_on_overflow=1` 时全连接队列满发 RST |
| **TIME_WAIT 中收到新 SYN** | 与 TIME_WAIT 旧连接"冲突"——内核发 RST |
| **应用调 SO_LINGER(0) close** | 显式发 RST 中断连接 |

**RST 的危害**：
- 接收方丢弃接收 buffer 中的数据——**业务层数据丢失**
- 监控：`/proc/net/snmp` 的 `OutRsts` 字段（持续增长 → 异常）

**治理**：
- 关闭连接前先 shutdown 再 close——避免 RST
- `tcp_abort_on_overflow=1`：全连接队列满发 RST（治标不治本）
- 监控 `OutRsts`：> 100/分钟告警

### 8.2 half-close 半关闭

**场景**：一方关闭写，但还在读（HTTP 响应场景）

**主动方**（HTTP 客户端）：
```c
shutdown(fd, SHUT_WR);  // 发完请求后告诉服务端"我写完了"
read(fd, buf, sizeof(buf));  // 继续读响应
close(fd);
```

**被动方**（HTTP 服务端）：
- 客户端发 FIN → 服务端进入 CLOSE_WAIT
- 服务端继续 read → 收到 EOF（read 返回 0）
- 服务端发送完响应 → shutdown(SHUT_WR) → 发 FIN
- 服务端 close → 进入 LAST_ACK

**关键观察**：
- HTTP 协议基于 half-close——客户端主动关闭写，服务端能识别"请求完整"
- 现代 HTTP/2、HTTP/3 不需要 half-close——多路复用

### 8.3 AF_UNIX 关闭的特殊点

**UDS 没有四次挥手**：
- UDS 是本地直连——无 FIN 概念
- close() 后立即释放
- **UDS 没有 TIME_WAIT**——这是 Zygote、InputChannel 不会受 TIME_WAIT 影响的原因

**UDS close 时的清理**：
- 路径型 UDS：unlink 路径（如果 close 前已 unlink）——可能残留 socket inode
- abstract 命名空间：自动清理
- socketpair：两端独立——一端 close 另一端可继续使用（不收影响）

**实战**：
- 路径型 UDS 关闭时 unlink 顺序很重要：
  - 错误：`unlink(path); close(fd);` 之间的客户端 connect 会失败（路径不存在）
  - 正确：`close(fd); unlink(path);`——但需要确保有重连机制
  - AOSP 标准：`close()` → 应用退出时 cleanup → `unlink()`

---

## 九、Android 6 大场景的生命周期映射

把生命周期"理论"映射到 6 大场景，让"在哪里出问题"一目了然。

### 9.1 Zygote Socket

**类型**：AF_UNIX SOCK_STREAM

**生命周期**：

```
[系统启动]
init → 启动 zygote 进程
zygote → socket(AF_UNIX, SOCK_STREAM, 0)
       → bind("/dev/socket/zygote")
       → listen(1)  // 旧版本
       → 进入 loop 等待 client
       
[每次 fork app]
AMS (system_server)
  → socket(AF_UNIX, SOCK_STREAM, 0)  // 新建 client socket
  → connect("/dev/socket/zygote")    // 连接 zygote
  → send(ZygoteCommand)
  → read(response)                    // 阻塞等 fork 结果
  → close(client socket)              // 关闭
  
zygote
  → accept()                            // 接收连接
  → fork(app_process)
  → 关闭 child socket                  // 在 zygote 端
```

**生命周期关键路径**：
- 创建：zygote 启动时一次
- 连接：每个 app fork 一次
- 关闭：fork 完成后立即关闭（双端）

**对应风险**（07 §2.1）：
- P0 启动 ANR：Zygote accept 慢 / 阻塞
- P0 fork 失败：Zygote 路径被改 / selinux 错
- P1 usap fd 泄漏：usap 进程异常退出

**监控点**：
- Zygote listen socket 数量
- zygote 进程 fd 总数
- Zygote accept 队列深度
- `dumpsys activity processes` 中的 Zygote fork 耗时

### 9.2 InputChannel

**类型**：AF_UNIX SOCK_SEQPACKET（socketpair）

**生命周期**：

```
[ViewRootImpl 初始化时]
ViewRootImpl.setView()
  → InputChannel.openInputChannelPair(name)  // socketpair
    → socketpair(AF_UNIX, SOCK_SEQPACKET, 0, fds)
  → serverChannel = fds[0]   // 持有在 system_server
  → clientChannel = fds[1]   // 持有在 app 进程
  → 注册 serverChannel 到 InputDispatcher

[ViewRootImpl 销毁时]
  → serverChannel.dispose()
  → clientChannel.dispose()
  → 两端都关闭 socketpair
```

**生命周期关键路径**：
- 创建：每个 window 关联一个 InputChannel
- 使用：app 进程与 system_server 双向通信
- 关闭：window 销毁时关闭两端

**对应风险**（07 §2.2）：
- P0 触摸无响应：app 主线程不消费
- P0 ANR：InputChannel buffer 满 + 主线程卡
- P0 fd 泄漏：`InputEventReceiver` 未 dispose

**监控点**：
- `dumpsys input` 中的 InboundQueue 深度
- app 进程 InputChannel 相关 fd 数量
- ANR trace 中 `InputEventReceiver.dispatchInputEvent` 出现频率

### 9.3 Choreographer BitTube

**类型**：AF_UNIX SOCK_STREAM（socketpair）

**生命周期**：

```
[Choreographer 初始化]
  → BitTube 创建（surfaceflinger 与 app 间的 VSync 通道）
  → socketpair(AF_UNIX, SOCK_STREAM, 0, sv)
  → mReceiveFd = sv[0]   // app 端 read
  → mSendFd = sv[1]      // surfaceflinger 端 write

[VSync 投递]
surfaceflinger
  → bitTube.write(vsync_time)
  
app
  → choreographer.doFrame()  // 读 vsync

[进程退出]
  → bitTube.destroy()
  → close 两端
```

**生命周期关键路径**：
- 创建：每个 app 与 surfaceflinger 间的 VSync 通道
- 使用：高频率（60/120Hz）单向 VSync 投递
- 关闭：app 进程退出

**对应风险**（07 §2.3）：
- P1 BitTube fd 泄漏
- P0 VSync 信号丢失 / 丢帧（BitTube 阻塞）
- P0 整个渲染卡死

**监控点**：
- `dumpsys gfxinfo` 的 janky frames
- BitTube buffer 深度（`/proc/<pid>/fd` 中的 socket fd）
- surfaceflinger 发送频率

### 9.4 adb (adbd)

**类型**：TCP socket（5555 端口）+ UDS（部分版本）

**生命周期**：

```
[设备启动]
init → 启动 adbd 进程
adbd → socket(AF_INET, SOCK_STREAM, 0)
     → bind(0.0.0.0:5555)
     → listen(128)  // 写死
     → 进入 loop 接受 host 连接

[host adb 接入]
host adb server
  → socket(AF_INET, SOCK_STREAM, 0)
  → connect(device_ip:5555)
  → 通信：adb 协议握手
  → 长连接保持
```

**生命周期关键路径**：
- 创建：adbd 启动时一次
- 连接：每个 host adb 客户端连接
- 关闭：host adb 主动断开

**对应风险**（07 §2.4）：
- P1 adb 假死：all queue 满
- P0 拒连：5555 端口被占
- P0 adb 不可用：路径被改

**监控点**：
- adbd 进程 fd 数
- adbd listen backlog 深度
- `cat /proc/net/netstat` 的 ListenDrops（adb 侧）

### 9.5 LocalSocket / LocalServerSocket

**类型**：AF_UNIX SOCK_STREAM（路径型或 abstract）

**生命周期**（以 installd 为例）：

```
[init.rc 启动]
service installd /system/bin/installd
    socket installd stream 600 system system
    # init 创建 /dev/socket/installd socket

[installd 进程]
main()
  → LocalServerSocket("installd")
    → socket(AF_UNIX, SOCK_STREAM, 0)
    → bind("/dev/socket/installd")
    → listen()
  → accept() 循环
  → 处理 client 请求
  → close() 处理完一个 client

[client 进程（如 PackageManager）]
  → LocalSocket()
    → socket(AF_UNIX, SOCK_STREAM, 0)
  → connect("/dev/socket/installd")
  → send(request)
  → read(response)
  → close()
```

**生命周期关键路径**：
- 创建：init 时创建 socket 文件 + installd 启动时 bind+listen
- 连接：每个 client 请求时新建
- 关闭：每条连接处理完关闭

**对应风险**（07 §2.5）：
- P0 服务挂：daemon 异常退出
- P1 排队：backlog 满
- P0 selinux 错：路径权限被改

**监控点**：
- `dumpsys package <pkg>` 看 service 状态
- daemon 进程 fd 总数
- `/proc/net/unix` 中 LocalServerSocket 数量

### 9.6 应用网络请求

**类型**：AF_INET SOCK_STREAM（TCP）

**生命周期**（以 OkHttp 为例）：

```
[App 启动]
  → OkHttpClient.Builder().build()
  → 创建连接池（默认 5 个 idle 连接）

[每次请求]
  → client.newCall(request).execute()
    → 从连接池获取连接
    → 无可用 → 创建 socket
      → socket(AF_INET, SOCK_STREAM, 0)
      → connect(host:port)  // 三次握手
    → write(request)
    → read(response)
    → 关闭 response body（不关闭 socket——复用）
  → close()

[App 退出 / 空闲超时]
  → idle 连接 5 分钟后被连接池清理
  → close(idleConnection)
    → 发起 FIN
    → 60s 后 TIME_WAIT 结束
```

**生命周期关键路径**：
- 创建：每个长连接 socket 一次
- 连接：每次新连接或连接池为空
- 关闭：HTTP keep-alive 决定 close 时机

**对应风险**（07 §2.6）：
- P0 联网失败：fd 耗尽 / 连接池满
- P0 ANR：主线程 socket IO
- P0 TIME_WAIT：短连接高频

**监控点**：
- 应用进程 socket fd 数
- `/proc/net/tcp` 中对应 ESTABLISHED 数
- OkHttp 连接池使用率
- 每次请求的 DNS、connect、read 时长

### 9.7 6 大场景生命周期对比

| 场景 | 类型 | 创建时机 | 关闭时机 | 关键状态 | 监控入口 |
|------|------|----------|----------|----------|----------|
| Zygote | UDS SOCK_STREAM | 系统启动 | zygote 进程退出 | LISTEN / CONNECTED | zygote fd 数 |
| InputChannel | UDS SOCK_SEQPACKET | window 创建 | window 销毁 | CONNECTED（持续） | dumpsys input |
| BitTube | UDS SOCK_STREAM | VSync 通道初始化 | app 进程退出 | CONNECTED | dumpsys gfxinfo |
| adb | TCP SOCK_STREAM | adbd 启动 | adbd 退出 | LISTEN / ESTABLISHED | adbd fd |
| LocalSocket | UDS SOCK_STREAM | init 时创建 socket 文件 | daemon 退出 | LISTEN | dumpsys package |
| 应用网络 | TCP SOCK_STREAM | app 启动 / 请求时 | keep-alive / close | ESTABLISHED / TIME_WAIT | app fd |

---

## 十、实战案例

### 案例 1：CLOSE_WAIT 5000 个——应用未 close 导致 P0 故障

**现象**：某 app 启动后 30 分钟内 fd 增长到 8000，最终导致 `socket(AF_INET, SOCK_STREAM, 0)` 返回 `-EMFILE`，所有新连接失败。

**5 分钟定位**（08 §2 工具）：

```bash
# 步骤 1：fd 总量
$ ls /proc/<pid>/fd | wc -l
7892

# 步骤 2：分类 socket
$ ls -l /proc/<pid>/fd | grep socket | wc -l
7800

# 步骤 3：找状态（按 socket inode 关联）
$ ss -tan state close-wait | wc -l
5000   # ← 根因
$ ss -tan state established | wc -l
2500
$ ss -tan state time-wait | wc -l
300
```

**根因分析**（按本篇 03 §7.6.3 知识）：
- `CLOSE_WAIT` 含义：对端已发 FIN，本端收 ACK，但**应用层未 close**（未走完四次挥手）
- 5000 个 CLOSE_WAIT → 应用至少 500 个 socket 未 close
- 应用层 `try-catch` 中 `IOException` 分支 `return` 而非 `finally close`——代码 bug

**修复**（按本篇 03 §7.10 治理）：

```java
// 错误写法
public void fetchData() {
    try {
        Response response = okHttpClient.newCall(request).execute();
        process(response.body().string());
    } catch (IOException e) {
        Log.e(TAG, "fetch failed", e);
        // ❌ 异常路径没有 close response
    }
}

// 正确写法
public void fetchData() {
    Response response = null;
    try {
        response = okHttpClient.newCall(request).execute();
        process(response.body().string());
    } catch (IOException e) {
        Log.e(TAG, "fetch failed", e);
    } finally {
        if (response != null) response.close();  // ✓ 兜底关闭
    }
}
```

**长期治理**：
- fdsan 检测（08 §4.1.1）—— 调试包开启
- 监控 `CLOSE_WAIT > 0` 立即告警
- OkHttp 配置 `try-with-resources` 风格 + 强 review

### 案例 2：TIME_WAIT 10000+——短连接高频导致端口耗尽

**现象**：某网关服务（每秒 1000 短连接）TIME_WAIT 持续 8000，告警：可用端口数 < 1000。

**5 分钟定位**：

```bash
# 整机 TIME_WAIT
$ ss -s
TCP:   8000 (estab 5000, closed 1000, orphaned 0, timewait 8000)

# 应用视角
$ ss -tan state time-wait | wc -l
8500
```

**根因**：
- 每秒 1000 短连接 → 每个连接在 60 秒 TIME_WAIT 内占一个端口
- 总占用 = 1000 × 60 = 60000 端口（远大于可用 28000 端口）
- 端口耗尽 → 新建连接 `bind()` 失败 → `-EADDRINUSE`

**修复**：

**方案 1：连接池**（根本解决）
```java
// 用连接池替代短连接
GenericObjectPoolConfig<HttpClient> config = new GenericObjectPoolConfig<>();
config.setMaxTotal(100);   // 最多 100 个连接复用
config.setMaxIdle(20);     // 最多 20 个 idle

// 复用连接 → 不创建新 socket → 不进 TIME_WAIT
```

**方案 2：tcp_tw_reuse=1**（治标）
```bash
sysctl -w net.ipv4.tcp_tw_reuse=1
# 允许复用 TIME_WAIT 端口给新客户端连接
```

**方案 3：调整 TIME_WAIT 时长**（不推荐）
```bash
sysctl -w net.ipv4.tcp_fin_timeout=30
# 缩短到 30 秒——但会增加异常关闭风险
```

**方案 4：SNAT 端口池**（运维）
- 增加网关的 SNAT 端口范围：`ip_local_port_range=10000-65000`
- 扩大可用端口空间——临时缓解

**推荐组合**：方案 1 + 方案 2 + 监控。

### 案例 3：FIN_WAIT2 持续 60 秒——对端不 close 导致 socket 泄漏

**现象**：某 client app 与 server 通信时，FIN_WAIT2 状态持续累积，每分钟增加 100 个。

**5 分钟定位**：

```bash
$ ss -tan state fin-wait-2 | wc -l
3000
$ ss -tan state fin-wait-2 | head -3
# 输出大量 客户端:server 配对
```

**根因分析**：
- client 主动 close → 发 FIN → `FIN_WAIT1`
- server 收 FIN → `CLOSE_WAIT` → 发 ACK → `FIN_WAIT2`
- server 应当再 close → 发 FIN → 但 server 端**没 close**——client 永远等 FIN
- 持续 60 秒后 kernel 超时关 socket（`tcp_fin_timeout`）

**根因**：
- server 端有 bug：发完 response 后没 close socket
- client 端问题：调 `close()` 后无法感知 server 异常

**修复**：

**client 端**：
- 设 `SO_LINGER(0)`：close 时立即发 RST 而不是等 FIN（不推荐——会丢数据）
- 设应用层心跳：超过 N 秒无响应主动 close

**server 端**：
- 修复 close 逻辑：发完 response 后必须 `shutdown(SHUT_WR) + close()` 或 `close()`
- 加监控：server 端 `CLOSE_WAIT > 0` 告警

**通用**：
- 监控 FIN_WAIT2 持续时长 → > 30s 告警
- 应用层心跳兜底

### 案例 4：connect 超时 60 秒——SYN 丢包导致启动 ANR

**现象**：某 app 启动时调 `HttpClient.connect()` 阻塞 60 秒后失败，触发 ANR。

**5 分钟定位**：

```bash
# strace 抓 connect
$ strace -e trace=connect,sendto -p <pid>
connect(12, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("1.2.3.4")}, 16) = -1 ETIMEDOUT
```

**根因**：
- client 发 SYN
- server 端 SYN+ACK 丢失（防火墙 / 网络抖动）
- client 重传 SYN 6 次（约 127 秒超时）——但 ANR 5 秒已触发
- 实际是 client 重传第 3 次时（约 7 秒）已过 5 秒 ANR 阈值

**修复**：

**短期**：
- 应用层设 `connectTimeout = 3000ms`（3 秒）——早抛错
- 主线程不调 `connect()`——放异步线程

**长期**：
- 网络质量监控：连续 SYN 丢包告警
- 服务端防火墙：放行 client IP
- 服务端用 SYN cookie：防 SYN flood

**ANR 防护**：
- Android StrictMode：检测主线程网络 IO（08 §4.1.2）
- 应用层：所有网络操作异步化

---

## 十一、附录

### 附录 A：核心源码路径索引

| 文件名 | 完整路径 | 内核/AOSP 版本 | 说明 |
|--------|----------|----------------|------|
| net/socket.c | net/socket.c | Linux 5.10+ | 通用 socket 层、syscall |
| net/ipv4/af_inet.c | net/ipv4/af_inet.c | Linux 5.10+ | INET 协议族（含 inet_bind/listen/accept/connect） |
| net/ipv4/tcp.c | net/ipv4/tcp.c | Linux 5.10+ | TCP 协议（含 tcp_close/tcp_listen/tcp_send_fin） |
| net/ipv4/tcp_ipv4.c | net/ipv4/tcp_ipv4.c | Linux 5.10+ | TCP IPv4 路径（tcp_v4_connect、tcp_v4_syn_recv_sock） |
| net/ipv4/inet_connection_sock.c | net/ipv4/inet_connection_sock.c | Linux 5.10+ | inet_csk_accept 等连接层函数 |
| net/unix/af_unix.c | net/unix/af_unix.c | Linux 5.10+ | UDS 协议族（含 unix_bind/listen/accept/connect） |
| net/core/sock.c | net/core/sock.c | Linux 5.10+ | socket 通用层 |
| include/net/sock.h | include/net/sock.h | Linux 5.10+ | struct sock 定义 |
| include/uapi/linux/tcp.h | include/uapi/linux/tcp.h | Linux 5.10+ | TCP_ESTABLISHED 等状态码 |
| frameworks/base/core/java/com/android/internal/os/ZygoteServer.java | AOSP 14 | Zygote 监听 socket |
| frameworks/native/libs/input/InputTransport.cpp | AOSP 14 | InputChannel socketpair |
| frameworks/native/libs/gui/BitTube.cpp | AOSP 14 | Choreographer VSync |
| frameworks/base/core/java/android/net/LocalSocket.java | AOSP 14 | UDS Java 封装 |
| frameworks/base/core/java/android/os/StrictMode.java | AOSP 14 | fdsan + 主线程 IO 检测 |

### 附录 B：TCP 11 状态速查表

| 状态码 | 名称 | 方向 | 含义 | 典型时长 | 异常信号 |
|--------|------|------|------|----------|----------|
| 01 | TCP_ESTABLISHED | 双向 | 已建立 | 任意（业务） | — |
| 02 | TCP_SYN_SENT | 客户端 | 发 SYN | < 1 RTT | 持续 60s+ → 网络丢包 |
| 03 | TCP_SYN_RECV | 服务端 | 收 SYN | < 1 RTT | 持续增长 → 半连接队列满 |
| 04 | TCP_FIN_WAIT1 | 主动方 | 发 FIN | < 1 RTT | 持续 60s+ → 对端无 ACK |
| 05 | TCP_CLOSE | 双向 | 已关闭 | — | — |
| 06 | TCP_TIME_WAIT | 主动方 | 2MSL 等待 | 60s | > 5000 → 短连接高频 |
| 07 | TCP_CLOSE | 同 05 | — | — | — |
| 08 | TCP_CLOSE_WAIT | 被动方 | 收 FIN | 0 到∞ | **> 0 → 应用未 close** |
| 09 | TCP_LAST_ACK | 被动方 | 发 FIN 后 | < 1 RTT | 持续 60s+ → 对端无 ACK |
| 0A | TCP_LISTEN | 服务端 | 监听 | 任意 | — |
| 0B | TCP_CLOSING | 双方同时 | 同时关闭 | 极短 | 几乎遇不到 |

### 附录 C：AF_INET vs AF_UNIX 生命周期对比

| 阶段 | AF_INET TCP | AF_UNIX SOCK_STREAM |
|------|-------------|---------------------|
| 创建 | inet_create → tcp_sock | unix_create → unix_sock |
| 绑定 | inet_bind（端口+IP） | unix_bind（路径/abstract） |
| 监听 | inet_listen（backlog 默认 8） | unix_listen（backlog 上限 128） |
| 接受 | inet_csk_accept（等 accept queue） | unix_accept（等 accept queue） |
| 连接 | inet_stream_connect（三次握手） | unix_stream_connect（直接加入队列） |
| 关闭 | inet_release → tcp_close（四次挥手） | unix_release（直接释放） |
| 状态数 | 11 个 TCP 状态 | 3 个 UDS 状态 |
| TIME_WAIT | 有（60s） | 无 |
| 半连接 | 有（SYN queue） | 无 |
| 全连接溢出 | ListenOverflows | ListenOverflows（但行为不同） |

### 附录 D：状态→监控指标对照

| 状态 | 监控命令 | 阈值 | 告警行动 |
|------|----------|------|----------|
| TCP_LISTEN | `ss -tlnp \| wc -l` | 长期不变 | 监听 socket 变化告警 |
| TCP_SYN_SENT | `ss -tan state syn-sent` | < 100 | 持续高 → 网络阻塞 |
| TCP_SYN_RECV | `ss -tan state syn-recv` | < 200 | 持续高 → 半连接队列满 |
| TCP_ESTABLISHED | `ss -tan state established` | < 20000 | 持续高 → 长连接过多 |
| TCP_FIN_WAIT1 | `ss -tan state fin-wait-1` | < 50 | 持续高 → 对端无 ACK |
| TCP_FIN_WAIT2 | `ss -tan state fin-wait-2` | < 100 | 持续高 → 对端不 close |
| **TCP_CLOSE_WAIT** | `ss -tan state close-wait` | **= 0** | **任何 > 0 → P0 告警** |
| TCP_LAST_ACK | `ss -tan state last-ack` | < 50 | 持续高 → 对端无 ACK |
| **TCP_TIME_WAIT** | `ss -tan state time-wait` | **< 5000** | **> 5000 → 短连接高频** |

### 附录 E：量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据来源 |
|------|----------|--------|----------|
| 1 | TCP 状态数 | 11 个 | uapi/linux/tcp.h |
| 2 | TIME_WAIT 默认时长 | 60 秒 | net/ipv4/tcp.c |
| 3 | tcp_synack_retries 默认 | 5 次 | AOSP 14 |
| 4 | tcp_syn_retries 默认 | 6 次 | AOSP 14 |
| 5 | UDS backlog 上限 | 128 | net/unix/af_unix.c |
| 6 | TCP backlog 上限（somaxconn） | 4096 | AOSP 14 |
| 7 | UDS 路径长度限制 | 108 字节 | UNIX_PATH_MAX |
| 8 | TCP 半连接队列默认 | tcp_max_syn_backlog=256 | AOSP 14 |
| 9 | TCP 全连接队列默认 | min(用户, somaxconn) | net/ipv4/af_inet.c |
| 10 | SO_LINGER 阻塞模式最长 | 由用户指定 | setsockopt |
| 11 | UDS 状态数 | 3 个 | SS_UNCONNECTED/LISTENING/CONNECTED |
| 12 | 三次握手步骤数 | 3 步 | TCP 协议 |
| 13 | 四次挥手步骤数 | 4 步 | TCP 协议 |
| 14 | close() 实际调用链层数 | 4-5 层 | net/socket.c |
| 15 | 监听 socket close 不发 FIN | 1 个例外 | inet_release |
| 16 | TIME_WAIT 占总可用端口比例 | 短连接场景下可达 50% | 工程经验 |
| 17 | FIN_WAIT2 默认超时 | tcp_fin_timeout 默认 60s | net/ipv4/tcp.c |

### 附录 F：与其他文章的关系

| 文章 | 本文引用位置 |
|------|--------------|
| 01-Socket 总览 | §1.2 生命周期全景图、§9.7 6 大场景对比 |
| 02-Socket API 与数据结构 | §2-§7 系统调用入口、§3-§4 三大结构体 |
| 04-Socket 缓冲 | §7.4 关闭时缓冲清理、§7.5 四次挥手 |
| 05-listen backlog | §4.1 listen 详细 backlog、§5.1 accept queue |
| 06-UDS 与 Android | §3.2 UDS bind、§4.2 UDS listen、§6.2 UDS connect、§8.3 UDS close |
| 07-风险全景 | §9 6 大场景生命周期映射、§10 实战案例属于 5 大类风险中的不同联动 |
| 08-诊断治理 | §10 实战案例用了 §2 工具 + §3 监控指标 + §4 治理方案 |
| bridge/01-socket 与 epoll | §5.1.3 accept 与 epoll 协作、§6.1 非阻塞 connect |
| epoll 01-epoll 总览 | §5.1.3 epoll_wait 监听 listenfd |
| IO 07-IO 与进程阻塞 | §7 close 阻塞与 wait queue |

---

## 十二、socket 系列"机制深潜"篇章收口

到本篇为止，socket 系列**第二篇章：核心机制深潜**（02-06）共 5 篇全部完结：

| 篇号 | 标题 | 角色 | 行数 |
|------|------|------|------|
| 02 | 内核 API 与核心数据结构 | 机制骨架 | 1664 |
| 03 | 连接生命周期：从创建到关闭 | 状态机走完一生（本篇） | ~1900 |
| 04 | 缓冲区与数据收发 | 数据怎么流通 | 811 |
| 05 | listen backlog 与连接队列 | 队列机制 | 764 |
| 06 | UDS 与 Android 使用 | UDS 主题深潜 | 770 |

**02-06 知识地图**：

```
02 (API+结构)
   ↓
03 (生命周期：创建→bind→listen→accept→connect→close)
   ↓
04 (缓冲区：sk_buff 队列、SO_SNDBUF/SO_RCVBUF、阻塞 read/write)
   ↓
05 (backlog：半连接/全连接队列、SYN cookie、accept queue 行为)
   ↓
06 (UDS：path/abstract、socketpair、SCM_RIGHTS、6 大场景)
```

**加上其他篇章**：
- 01 总览：全局观（已写）
- 07 风险全景：5 大类风险矩阵（已写）
- 08 诊断治理：诊断工具 + 治理体系（已写）
- bridge/01-socket 与 epoll：协作（已写）

**socket 系列 8 篇规划 + 桥接 1 + epoll 1 全部完结** 🎉

**给架构师的"生命周期诊断卡"**：
1. **看状态码**：拿 03 附录 B 的 11 状态表对照
2. **看错误码**：拿 03 §3.2 / §6.3 / §7.10 的错误码表对照
3. **看时长**：拿 03 附录 D 的状态→监控指标对照
4. **看应用层**：CLOSE_WAIT > 0 永远是应用层 bug

---

## 篇尾衔接

socket 系列 8 篇规划 + 1 桥接 + 1 epoll 全部完结。

**本篇完成后**：
- 02 讲 socket 是什么、怎么组织
- 03 讲 socket 怎么变化、走完一生（本篇）
- 04-06 讲 socket 内部机制（缓冲、backlog、UDS）
- 07 讲 socket 在哪里会出问题
- 08 讲 socket 怎么查、怎么治

**可考虑的后续延伸**：
- 01 总览的更新：把 02-08 写完的"扩展视角"补回到 01
- TCP 内部机制专题：重传、拥塞控制、TIME_WAIT 细节（独立专题）
- 网络性能优化：socket + epoll 性能 benchmark
- 实战案例库：从 socket 系列 8 篇中抽离出"案例汇编"

但 socket 系列本身——**已经齐了**。

---


