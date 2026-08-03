# Socket 02：内核 API 与核心数据结构

> **系列**：面向稳定性的 Android Socket 子系统深度解析系列(Socket)
>
> **源码基线**:AOSP `android-14.0.0_r1`(`refs/heads/android14-release`)
>
> **内核矩阵**:`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇涉及 `net/socket.c`、`include/net/sock.h`、`include/linux/socket.h`、`net/core/sock.c`;5.10→5.15 struct sock 字段新增 `sk_listener` 与 `sk_socket` 见 §3;Android 14 CGroupSocket 限制见 §5)
>
> **目标读者**:Android 稳定性框架架构师
>
> **前置阅读**:[01-Socket 总览](01-Socket总览.md)
>
> **下一篇**:[03-Socket 连接生命周期](03-Socket连接生命周期.md)

> 面向 Android 稳定性架构师：从一次 `socket()` 系统调用出发，逐层拆解内核中的 `struct socket` / `struct sock` / `struct file` 三元组，理解"用户态 fd → 内核 socket 对象 → 协议实现"的完整映射，**让你看 `/proc/net/*` 字段、strace 输出、ANR trace 时能精确对应到内核结构体的某个字段**。

---

## 本篇定位

- **本篇系列角色**:Socket 系列第 2 篇「内核 API 与核心数据结构」(socket 系列 8 篇规划"第二篇章:核心机制深潜"的第 1 篇;与 01 总览的"四层架构图"对应——本篇把它填成可读源码)
- **强依赖**:
  - [Socket 01-Socket总览](01-Socket总览.md)(§4.4 四层架构图——本篇全部按此架构展开)
  - [IO 06-IO 与进程的深度耦合](../../IO/06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md) §1-2(D 状态、wait queue 唤醒——socket 阻塞时关联)
  - [epoll 01-epoll总览与核心机制](../epoll/01-epoll总览与核心机制.md)(socket 的 f_op->poll 是 epoll 监听的入口——本篇会展开 socket_file_ops 中的 poll)
  - [VFS 04-VFS 与文件系统](../FS/04-VFS设计理念与统一接口.md)(VFS 基础:struct file、struct inode、struct file_operations 的关系——本篇讲 socket 与 VFS 的绑定)
- **承接自**:01 §4.4 的"四层架构"——本篇把每一层的具体结构体与调用链展开
- **衔接去**:本篇末尾会预告下一篇 [03-Socket连接生命周期:从创建到关闭](03-Socket连接生命周期.md) 讲 socket() → bind() → listen() → accept() → close() 的完整状态机
- **不重复内容**:epoll 监听机制、wait queue 基础、VFS 通用部分——全部由强依赖文章承担;本篇只讲**socket 特定的结构体与注册链**

#### §0 锚点案例的可验证 4 件套:某 SDK socket() EINVAL 处理不当导致 FD 泄漏 5000+

> **环境**:
> - 设备:Pixel 7(G2, arm64-v8a, 8GB RAM)
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI(`/proc/sys/fs/nr_open` 默认 1048576)
> - App:某 IM App v7.0(脱敏代号 `ChatApp`,集成某推送 SDK v3.2)
> - 工具:`strace` + `ls /proc/<pid>/fd | wc -l` + `cat /proc/<pid>/fdinfo/<fd>` + `dumpsys meminfo`

> **复现步骤**:
> 1. 工厂重置,安装 ChatApp v7.0,登录账号
> 2. `adb shell strace -p $(pidof com.chat.app) -f -e trace=network` 抓 5min
> 3. `ls /proc/$(pidof com.chat.app)/fd | wc -l` 每 30s 采样一次
> 4. 触发场景:消息推送 / 心跳连接 / 网络切换(飞行模式开关 5 次)
> 5. 30min 后 FD 数量从 200 涨到 5200 → 触发"Too many open files"

> **logcat / strace 关键片段**:
> ```
> # strace(网络系统调用)
> socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP) = -1 EINVAL (Invalid argument)  ← 错误未处理
> socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP) = -1 EINVAL (Invalid argument)
> socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP) = 256       ← 成功分配 fd
> socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP) = -1 EINVAL (Invalid argument)
> ...
> # /proc/<pid>/fd 统计
> $ ls /proc/$(pidof com.chat.app)/fd | wc -l
> 5247    ← FD 数量持续增长
> # /proc/<pid>/fdinfo/256(某个 socket)
> pos:    0
> flags:  02
> mnt_id: 5
> fd:     256
> ino:    24513   ← socket:[24513]
> # /proc/<pid>/net/tcp 中 inode 24513 详情
>   sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
>    0: 0BB89B0F:01BB 0C0BB89B:01BB 01 00000000:00000000 00:00000000 00000000  10087        0 24513 2 ...
> # 关键发现:push_sdk 在 socket() 返回 EINVAL 时没正确 goto 出口,泄漏了 +1 fd 槽位
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/sdk/src/main/cpp/socket_helper.cpp
> +++ b/sdk/src/main/cpp/socket_helper.cpp
> @@ push_sdk::create_socket()
> -    // 旧版:socket() 失败只 log error,fd 未释放
> -    int fd = socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP);
> -    if (fd < 0) {
> -        ALOGE("socket() failed: %s", strerror(errno));
> -        return -1;
> -    }
> +    // 修复:失败也要释放资源,所有路径走同一个 cleanup label
> +    int fd = socket(AF_INET6, SOCK_STREAM, IPPROTO_TCP);
> +    if (fd < 0) {
> +        ALOGE("socket() failed: %s", strerror(errno));
> +        return -1;
> +    }
> +    struct sockaddr_in6 addr = {};
> +    addr.sin6_family = AF_INET6;
> +    // ... 填充 addr ...
> +    int ret = bind(fd, (struct sockaddr*)&addr, sizeof(addr));
> +    if (ret < 0) {
> +        ALOGE("bind() failed: %s", strerror(errno));
> +        goto err_close;
> +    }
>      ...
> -    if (listen(fd, backlog) < 0) {
> -        return -1;
> -    }
> +    if (listen(fd, backlog) < 0) {
> +        goto err_close;
> +    }
>      return fd;
> +err_close:
> +    close(fd);
> +    return -1;
> ```
> 完整 socket 字段 ↔ /proc/net/* ↔ ANR 链路 ↔ FD 泄漏路径见 §2 §4 §6。

> 面向 Android 稳定性架构师：从一次 `socket()` 系统调用出发，逐层拆解内核中的 `struct socket` / `struct sock` / `struct file` 三元组，理解"用户态 fd → 内核 socket 对象 → 协议实现"的完整映射，**让你看 `/proc/net/*` 字段、strace 输出、ANR trace 时能精确对应到内核结构体的某个字段**。

## 一、背景与定义

### 1.1 为什么需要"API + 数据结构"专题

socket 在 Android 稳定性排查里"无处不在"——但绝大多数工程师对它的理解停留在"一个 fd，可以 read/write"。这种理解在以下场景会失灵：

- **看 `/proc/net/tcp` 输出时**：不知道 `sl` `st` `tx_queue` `rx_queue` `inode` 这些字段来自哪个结构体的哪个成员
- **看 strace 输出时**：不知道 `connect(12, ...)` 中 fd=12 对应的内核对象长什么样
- **看 `/proc/pid/fd` 时**：看到 `socket:[24513]` 这种链接，不知道它如何与 `/proc/net/tcp` 中的某行关联
- **排查 FD 泄漏时**：不理解"fd 泄漏 = file 泄漏 = socket 泄漏 = sock 泄漏 = 协议层资源泄漏"的四重含义
- **写代码时**：不理解 `socketpair()` 返回的两个 fd 共享同一个 `struct socket`，导致某些操作二义性

**本篇目标**：把这些"神秘"全部解开。

### 1.2 整体视角——一张"三层视角"图

socket 在内核里有**三个不同视角**，对应三种不同的角色：

```
用户态视角                    VFS 视角                    协议层视角
─────────                    ─────────                  ──────────
fd (int)              →    struct file          →    (无直接对应)
                              │                         ↑
                              │ .f_op=socket_file_ops   │
                              │ .private_data=socket    │
                              ▼                         │
                         struct socket                 │
                              │                         │
                              │ .sk ─────────────→ struct sock
                              │                         │
                              ▼                         ▼
                         struct inode            struct proto
                         (socket_inode)          (tcp_prot / unix_proto)
                              │
                              ▼
                         struct sock_common
                         (sock_common_ops)
```

**关键观察**：
- **fd → file**：fd 是进程的"打开文件表"索引；`fd → struct file *` 由 fdtable 解析
- **file → socket**：`file->private_data` 直接指向 `struct socket`
- **socket ↔ sock**：`socket->sk` 与 `sk->sk_socket` 双向指针
- **sock → proto**：`sock->sk_prot` 指向协议实现（如 `tcp_prot`、`unix_proto`）
- **inode**：socket 自带一种特殊 inode（`S_IFSOCK` 类型），用于让 `select/poll/epoll` 能找到 socket

这三层视角在 02 §3 §4 §5 逐一拆解。

### 1.3 三大核心结构体的角色分工

| 结构体 | 文件 | 视角 | 关键职责 | 生命周期 |
|--------|------|------|----------|----------|
| `struct socket` | `include/linux/net.h` | BSD socket API 层 | 对应用户态 fd；保存 ops 指针（proto_ops）；保存 state | 与 fd 同生命周期 |
| `struct sock` | `include/net/sock.h` | INET socket 通用层 | 通用网络层结构；保存发送/接收队列；保存协议指针（sk_prot） | 与 socket 同生命周期 |
| `struct file` | `include/linux/fs.h` | VFS 层 | 标准 fd 后端；保存 socket_file_ops；保存 private_data 指向 socket | 与 fd 同生命周期 |

**最简化的关系**：
```
fd ──→ file ──→ socket ──→ sock ──→ proto（tcp_prot / unix_proto）
```

后文将逐层拆解。

---

## 二、系统调用入口：从用户态到内核态的桥梁

socket 系列 7 个核心系统调用（`socket`/`bind`/`listen`/`accept`/`connect`/`sendto`/`recvfrom`/`close`）在 Linux 内核中全部走**统一入口** `net/socket.c`，再分发到协议族（AF_INET/AF_UNIX）的具体实现。

### 2.1 七个 syscall 一览

| 系统调用 | 用户态声明 | 内核入口 | 协议族入口 | 典型场景 |
|----------|------------|----------|------------|----------|
| `socket()` | `<sys/socket.h>` | `__sys_socket()` | `sock_create()` → `pf->create` | 创建 socket |
| `bind()` | `<sys/socket.h>` | `__sys_bind()` | `sock->ops->bind` | Zygote 监听 |
| `listen()` | `<sys/socket.h>` | `__sys_listen()` | `sock->ops->listen` | Zygote/adb/installd 服务端 |
| `accept()` | `<sys/socket.h>` | `__sys_accept4()` | `sock->ops->accept` | 服务端接受连接 |
| `connect()` | `<sys/socket.h>` | `__sys_connect()` | `sock->ops->connect` | 客户端连接 Zygote/服务端 |
| `sendto()`/ `send()` | `<sys/socket.h>` | `__sys_sendto()` | `sock->ops->sendmsg` | 数据发送 |
| `recvfrom()`/ `recv()` | `<sys/socket.h>` | `__sys_recvfrom()` | `sock->ops->recvmsg` | 数据接收 |
| `close()` | `<unistd.h>` | `__close_fd()` (fs/open.c) | `sock->ops->release` | 释放 socket |

**关键路径**：`net/socket.c` 提供通用入口 → 通过 `socket->ops`（proto_ops）跳到具体协议族实现 → 协议族调用 `sock->sk_prot`（proto）做实际工作。

### 2.2 socket() 系统调用详解

`socket()` 是所有 socket 的起点——它创建 `struct socket`、`struct sock`、绑定 fd。

#### 2.2.1 用户态 → 内核态的过渡

```c
// 用户态
int fd = socket(AF_INET, SOCK_STREAM, 0);

// 展开为 syscall（glibc 内联）
mov eax, __NR_socket  // x86 系统调用号 359
mov edi, AF_INET      // 协议族
mov esi, SOCK_STREAM  // 类型
mov edx, 0            // 协议
syscall

// 内核态（net/socket.c）
SYSCALL_DEFINE3(socket, int, family, int, type, int, protocol)
{
    return __sys_socket(family, type, protocol);
}
```

#### 2.2.2 __sys_socket 源码逐行拆解

```c
// net/socket.c
int __sys_socket(int family, int type, int protocol)
{
    struct socket *sock;
    int flags, fd;

    /* 1. type 调整：SOCK_NONBLOCK / SOCK_CLOEXEC 可以一起传 */
    flags = type & ~SOCK_TYPE_MASK;   // 去掉 type 主类型
    type &= SOCK_TYPE_MASK;            // 保留纯 type

    /* 2. 创建 socket 对象（最关键） */
    retval = sock_create(family, type, protocol, &sock);
    if (retval < 0)
        return retval;

    /* 3. 绑定 fd（把 socket 与 file 关联） */
    fd = sock_map_fd(sock, flags & (O_CLOEXEC | O_NONBLOCK));
    if (fd < 0) {
        sock->ops->release(sock);  // 失败时释放
        return fd;
    }

    return fd;
}
```

**四步关键路径**：
1. `sock_create()`：分配 `struct socket` + `struct sock`，初始化
2. `sock_map_fd()`：分配 fd、分配 `struct file`、建立 file <-> socket 关系
3. 失败时调用 `release()` 回滚
4. 返回 fd

#### 2.2.3 sock_create() 内部细节

```c
// net/socket.c
int sock_create(int family, int type, int protocol, struct socket **res)
{
    return __sock_create(current->nsproxy->net_ns, family, type, protocol, res, 0);
}

int __sock_create(struct net *net, int family, int type, int protocol,
                  struct socket **res, int kern)
{
    struct socket *sock;
    const struct net_proto_family *pf;
    int err, err2;

    /* 1. 分配 struct socket */
    sock = sock_alloc();
    if (!sock)
        return -ENOMEM;

    /* 2. family 转 net_proto_family 指针（关键跳转表） */
    pf = rcu_dereference(net_families[family]);  // ← 协议族注册点
    err = -EAFNOSUPPORT;
    if (!pf)
        goto out_release;  // family 不支持：常见 AF 错误

    /* 3. 调用协议族的 create 方法 */
    err = pf->create(net, sock, protocol, kern);
    if (err < 0)
        goto out_module_put;
    
    /* 4. 初始化 socket 公共字段 */
    sock->type = type;
    
    *res = sock;
    return 0;
    
out_release:
    sock_release(sock);
    ...
}
```

**关键点**：
- `net_families[]` 是协议族跳转表（数组下标 = family 值，如 AF_INET=2）
- `pf->create` 跳转到协议族的具体 create 实现：
  - `AF_INET` → `inet_create()` → 创建 `struct sock_common` + `struct inet_sock` + TCP/UDP 特定结构
  - `AF_UNIX` → `unix_create()` → 创建 UDS 特定结构
- `sock_alloc()` 分配 socket + 关联的特殊 inode（`S_IFSOCK`）

#### 2.2.4 sock_map_fd()——fd 与 socket 的绑定

```c
// net/socket.c
static int sock_map_fd(struct socket *sock, int flags)
{
    struct file *newfile;
    int fd;

    /* 1. 分配 fd（进程的 fdtable） */
    fd = get_unused_fd_flags(flags);
    if (fd < 0)
        return fd;

    /* 2. 分配 struct file */
    newfile = sock_alloc_file(sock, flags, NULL);
    if (IS_ERR(newfile)) {
        put_unused_fd(fd);
        return PTR_ERR(newfile);
    }

    /* 3. 把 fd 装入进程的 fdtable */
    fd_install(fd, newfile);
    
    return fd;
}
```

**关键关系**：
- `newfile->private_data = sock` —— **file 指向 socket**
- `sock->file = newfile` —— **socket 指向 file**（双向指针）
- `fd` 是 fdtable 的索引

**调试意义**：从此，`fd` 在用户态的每个操作都通过 `fd → file → socket → sock → proto` 一路追到协议实现。

### 2.3 bind() / listen()——服务端初始化

#### 2.3.1 bind() 源码

```c
// net/socket.c
int __sys_bind(int fd, struct sockaddr __user *umyaddr, int addrlen)
{
    struct socket *sock;
    struct sockaddr_storage address;
    int err, fput_needed;

    /* 1. 从 fd 拿 socket */
    sock = sockfd_lookup(fd, &fput_needed);
    if (!sock)
        return -EBADF;

    /* 2. 地址从用户态拷贝到内核态 */
    err = move_addr_to_kernel(umyaddr, addrlen, &address);
    if (err)
        goto out;

    /* 3. 调用协议族的 bind */
    err = sock->ops->bind(sock, (struct sockaddr *)&address, addrlen);
    
out:
    fput_light(sock->file, fput_needed);
    return err;
}
```

**实战**：
- `sockfd_lookup()`：fd → file → socket（验证 fd 有效性）
- `sock->ops->bind`：分发到 `inet_bind()`（AF_INET）或 `unix_bind()`（AF_UNIX）
- `move_addr_to_kernel`：把用户态 sockaddr 拷贝到内核（这是用户态/内核态边界）

#### 2.3.2 listen() 源码

```c
// net/socket.c
int __sys_listen(int fd, int backlog)
{
    struct socket *sock;
    int err, fput_needed;

    sock = sockfd_lookup(fd, &fput_needed);
    if (!sock)
        return -EBADF;

    err = sock->ops->listen(sock, backlog);
    
    fput_light(sock->file, fput_needed);
    return err;
}
```

**`inet_listen()` 内核实现**（`net/ipv4/af_inet.c`）：

```c
int inet_listen(struct socket *sock, int backlog)
{
    struct sock *sk = sock->sk;
    ...
    
    /* 1. 状态检查：必须是 SS_UNCONNECTED 或 SS_LISTENING */
    if (sock->state != SS_UNCONNECTED)
        goto out;
    
    /* 2. 调整 backlog：取用户传入与系统上限的最小值 */
    sk->sk_max_ack_backlog = min(backlog, READ_ONCE(somaxconn));
    
    /* 3. 调用 TCP 层 */
    if (sk->sk_prot->listen) {
        sk->sk_prot->listen(sk, backlog);   // → tcp_listen()
    }
    
    sock->state = SS_LISTENING;
    ...
}
```

**关键**：
- `backlog = min(用户值, somaxconn)` —— 用户调 `listen(fd, 1000)` 而 somaxconn=4096，实际 backlog=1000
- `sk->sk_max_ack_backlog`：全连接队列上限（accept queue）
- `tcp_listen()` 在 `net/ipv4/tcp.c` 完成实际工作（详见 05 篇）

### 2.4 accept()——服务端接受连接

```c
// net/socket.c
int __sys_accept4(int fd, struct sockaddr __user *upeer_sockaddr,
                  int __user *upeer_addrlen, int flags)
{
    struct socket *sock, *newsock;
    struct file *newfile;
    int err, len, newfd, fput_needed;

    sock = sockfd_lookup(fd, &fput_needed);
    if (!sock)
        return -EBADF;

    /* 1. 创建新 socket（接受连接会产生新 socket 对象） */
    newsock = sock_alloc();
    if (!newsock)
        return -ENOMEM;
    newsock->type = sock->type;
    newsock->ops = sock->ops;  // 继承 ops

    /* 2. 调用协议族的 accept */
    err = sock->ops->accept(sock, newsock, sock->file->f_flags, false);
    if (err < 0)
        goto out_release;

    /* 3. 给新 socket 分配新 fd */
    newfile = sock_alloc_file(newsock, flags, NULL);
    ...
    newfd = get_unused_fd_flags(flags);
    fd_install(newfd, newfile);
    
    return newfd;
}
```

**关键观察**：
- `accept()` **创建新的 socket + 新的 file + 新的 fd**——这是为什么 server 端会有"监听 fd + 已连接 fd 多个"
- `newsock->ops = sock->ops` —— 新 socket 继承协议族的 ops
- `accept()` 返回的 fd 与原监听 fd 是**完全独立的两个 socket**

### 2.5 connect()——客户端发起连接

```c
// net/socket.c
int __sys_connect(int fd, struct sockaddr __user *uservaddr, int addrlen)
{
    struct socket *sock;
    struct sockaddr_storage address;
    int err, fput_needed;

    sock = sockfd_lookup(fd, &fput_needed);
    ...
    err = sock->ops->connect(sock, (struct sockaddr *)&address, addrlen, sock->file->f_flags);
    ...
}
```

**TCP 的 connect 实现**（`net/ipv4/tcp.c` → `tcp_v4_connect()`）：

```c
int tcp_v4_connect(struct sock *sk, struct sockaddr *uaddr, int addr_len)
{
    ...
    /* 1. 状态检查 */
    if (sk->sk_state != TCP_CLOSE)
        goto sock_err;

    /* 2. 路由查找 */
    rt = ip_route_connect(...);
    
    /* 3. 发起 SYN */
    err = tcp_connect(sk);  // 发送 SYN 包
    
    /* 4. 设置状态 */
    sk->sk_state = TCP_SYN_SENT;
    ...
}
```

**关键点**：
- `connect()` 是**发起方主动**调用——`inet_stream_connect` 内部会等待三次握手完成（默认阻塞模式）
- 非阻塞模式下立即返回 `-EINPROGRESS`，连接完成由 epoll 通知
- 客户端的 socket 与服务端 accept 出来的 socket **不是同一个对象**——但两端使用相同协议

### 2.6 send/recv——数据收发

#### 2.6.1 sendto()/send() 内核入口

```c
// net/socket.c
int __sys_sendto(int fd, void __user *buff, size_t len, unsigned flags,
                 struct sockaddr __user *addr, int addr_len)
{
    struct socket *sock;
    struct sockaddr_storage address;
    ...
    
    /* 1. 通过 msghdr 描述待发送数据 */
    struct msghdr msg;
    struct iovec iov;
    iov.iov_base = buff;
    iov.iov_len = len;
    msg.msg_name = NULL;     // 目标地址（如果 addr 为 NULL）
    msg.msg_namelen = 0;
    msg.msg_iov = &iov;
    msg.msg_iovlen = 1;
    
    /* 2. 调用协议族 sendmsg */
    sock->ops->sendmsg(sock, &msg, len);
}
```

**sendmsg 调用链**：
```
用户 send()
  → __sys_sendto()
    → sock->ops->sendmsg()         // → inet_sendmsg()
      → sk->sk_prot->sendmsg()      // → tcp_sendmsg()
        → tcp_push() / tcp_write_xmit()   // 实际发送 TCP 包
```

#### 2.6.2 recvfrom()/recv() 内核入口

```c
// net/socket.c
int __sys_recvfrom(int fd, void __user *ubuf, size_t size, unsigned flags,
                   struct sockaddr __user *addr, int __user *addr_len)
{
    struct socket *sock;
    ...
    sock->ops->recvmsg(sock, &msg, size, flags);
    ...
}
```

**recvmsg 调用链**：
```
用户 read()/recv()
  → __sys_recvfrom()
    → sock->ops->recvmsg()         // → inet_recvmsg()
      → sk->sk_prot->recvmsg()      // → tcp_recvmsg()
        → sk_wait_data() / skb_copy_to_page()   // 阻塞等数据 + 拷贝到用户态
```

**关键点**：
- `read()` 是 `recv()` 的语法糖——最终都走 `__sys_recvfrom`
- `recv()` 阻塞的本质是 `sk_wait_data()`（§04 详细拆解）

### 2.7 close()——socket 释放

`close()` 是 socket 的"消亡路径"——这是**FD 泄漏的根因位置**。

```c
// fs/open.c（close 不在 net/socket.c 而在通用文件系统层）
int __close_fd(struct files_struct *files, unsigned fd)
{
    ...
    filp_close(file, files);  // → 调 file->f_op->release()
}

// 展开：filp_close → file->f_op->release(file, inode)
// 对 socket 而言，file->f_op = socket_file_ops
// release = sock_close()
```

`sock_close()` 源码（`net/socket.c`）：

```c
static int sock_close(struct inode *inode, struct file *filp)
{
    struct socket *sock = filp->private_data;

    /* 1. 调用协议族的 release */
    sock->ops->release(sock);
    
    /* 2. 释放 socket */
    sock_release(sock);
    
    return 0;
}
```

**`sock_release()`**（`net/socket.c`）：

```c
void sock_release(struct socket *sock)
{
    if (sock->ops) {
        struct module *owner = sock->ops->owner;
        sock->ops->release(sock);   // 二次调用？或 inode->i_ops?...
        ...
    }
    ...
    sock_put(sock);  // 释放 sock 引用计数
}
```

**关键观察（稳定性视角）**：
- `close()` 走通用文件层 → 调用 socket 的 release
- **如果应用层不调 close()**：`sock` 引用计数不为 0 → sock 对象不释放 → `struct file` 不释放 → fd 在 fdtable 中占位 → **FD 泄漏**
- 这就是为什么"忘记 close = FD 泄漏"的根因

---

## 三、struct socket 与 struct sock：核心数据结构

`struct socket` 与 `struct sock` 是 socket 在内核里"两个层次的核心"——一个在 BSD socket API 层（用户态可见），一个在传输层（协议相关）。

### 3.1 struct socket（VFS/BSD 层）

**源码位置**：`include/linux/net.h`

```c
struct socket {
    socket_state        state;          // socket 状态：SS_UNCONNECTED/SS_CONNECTING/SS_CONNECTED/SS_LISTENING
    short               type;           // socket 类型：SOCK_STREAM/SOCK_DGRAM/SOCK_SEQPACKET

    unsigned long       flags;          // SOCK_ASYNC_NOSPACE / SOCK_VMIO 等

    struct file         *file;          // 关联的 struct file（指向 fd 后端）
    struct sock         *sk;            // 关联的 struct sock（协议层对象）—— 双向指针
    const struct proto_ops  *ops;       // 协议族操作集：决定 bind/connect/sendmsg 等跳到哪个实现
};

typedef enum {
    SS_FREE = 0,            // 未分配
    SS_UNCONNECTED,         // 未连接
    SS_CONNECTING,          // 正在连接
    SS_CONNECTED,           // 已连接
    SS_DISCONNECTING        // 正在断开
} socket_state;
```

**字段详解**：

| 字段 | 类型 | 作用 | 实战用途 |
|------|------|------|----------|
| `state` | `socket_state` | socket 状态机 | `SS_LISTENING` = 监听中；`SS_CONNECTED` = 已连接 |
| `type` | `short` | SOCK_STREAM/SOCK_DGRAM 等 | 用户传入的 type |
| `file` | `struct file *` | VFS 后端 | 通过它找到 fd（§5 详述） |
| `sk` | `struct sock *` | 协议层对象 | **最关键指针**——`sk->sk_prot` 决定协议 |
| `ops` | `proto_ops *` | 协议族操作集 | `sock->ops->bind()` 跳到 `inet_bind()` 或 `unix_bind()` |

**与用户态 fd 的对应**：
- `struct socket` 是一对一的——一个 socket 对应一个内核对象
- 同一个 socket 可以被 dup 成多个 fd（如 `dup()` 或 `fork()`），但 socket 对象不变
- `socketpair()` 产生两个 socket 对象 + 两个 fd（**注意：socketpair 的两端是独立 socket 对象**）

**典型问题——socket 状态与 sock 状态的差异**：
- `socket->state`：BSD 层状态（监听、连接、未连接等宏观状态）
- `sock->sk_state`：协议层状态（TCP 状态机的 SYN_SENT/ESTABLISHED 等）
- 两者**不完全等价**——例如 `socket->state=SS_CONNECTED` 但 `sk->sk_state=TCP_CLOSE_WAIT`

### 3.2 struct sock（协议通用层）

**源码位置**：`include/net/sock.h`

`struct sock` 是 socket 协议层的"通用底座"——所有协议（TCP/UDP/UDS 等）共用的部分。

```c
struct sock {
    /*
     * 1. 与 BSD socket 的双向指针
     */
    struct socket       *sk_socket;     // 指向 struct socket（反指）
    
    /*
     * 2. 协议族与协议
     */
    struct proto        *sk_prot;        // 协议实现：tcp_prot / unix_proto
    struct proto_ops    *sk_prot_creator;// 创建者（用于 ref counting）
    __u32               sk_family;      // AF_INET / AF_UNIX 等
    __u16               sk_type;        // SOCK_STREAM / SOCK_DGRAM
    __u8                sk_protocol;    // IPPROTO_TCP / 0（UDS 无 protocol）
    __u8                sk_gso_type;    // GSO 类型
    
    /*
     * 3. 状态机
     */
    socket_state        sk_state;        // 协议层状态（与 socket->state 配合）
    unsigned long       sk_flags;        // SOCK_DEAD / SOCK_ZAPPED 等
    
    /*
     * 4. 队列与缓冲（重要！）
     */
    struct sk_buff_head sk_receive_queue;  // 接收队列：网络收到的 skb
    struct sk_buff_head sk_write_queue;    // 发送队列：待发送的 skb
    struct sk_buff_head sk_error_queue;    // 错误队列（OOB/错误）
    
    /*
     * 5. 等待队列与回调
     */
    wait_queue_head_t   *sk_sleep;         // 等待队列（recv/send 阻塞时用）
    void                (*sk_data_ready)(struct sock *sk);  // 数据就绪回调
    void                (*sk_write_space)(struct sock *sk); // 写空间可用回调
    
    /*
     * 6. 缓冲与窗口
     */
    int                 sk_sndbuf;        // 发送 buffer 上限
    int                 sk_rcvbuf;        // 接收 buffer 上限
    ...
    
    /*
     * 7. 引用计数
     */
    atomic_t            sk_refcnt;        // sock 引用计数——close 时减 1
};
```

**关键字段详解**：

#### 3.2.1 双向指针：`sk_socket` 与 `socket->sk`

```c
// 初始化时（在 sock_create 中）：
sock->sk = sk;       // socket → sock
sk->sk_socket = sock; // sock → socket

// 释放时（sock_release 中）：
sk->sk_socket = NULL;
sock->sk = NULL;
```

**实战用途**：
- 给定一个 `struct sock *`，可通过 `sk->sk_socket->file` 找到 `struct file`
- 给定一个 `struct file *`，可通过 `file->private_data` 找到 `struct socket`，再找 `sk`
- **这是 fd → socket → sock 双向追溯的根基**

#### 3.2.2 协议指针：`sk_prot`

```c
struct proto {
    void (*close)(struct sock *sk, long timeout);  // 关闭协议层
    int  (*connect)(struct sock *sk, struct sockaddr *uaddr, int addr_len);
    int  (*disconnect)(struct sock *sk, int flags);
    int  (*accept)(struct sock *sk, struct socket *newsock, int flags, bool kern);
    int  (*ioctl)(struct sock *sk, int cmd, unsigned long arg);
    int  (*init)(struct sock *sk);
    void (*destroy)(struct sock *sk);
    ...
};
```

**典型值**：
- `tcp_prot`（`net/ipv4/tcp.c`）—— TCP 协议实现
- `udp_prot`（`net/ipv4/udp.c`）—— UDP 协议实现
- `unix_proto`（`net/unix/af_unix.c`）—— UDS 协议实现

**实战用途**：
- 给定 sock，通过 `sk->sk_prot->connect` 跳到 TCP/UDS 的 connect 实现
- 通过 `sk->sk_prot->close` 找到 close 实现（释放 TCP 状态/窗口/重传队列等）

#### 3.2.3 队列：`sk_receive_queue` / `sk_write_queue`

```c
// 接收队列：存放已收到但用户态未 read 的 skb
struct sk_buff_head sk_receive_queue;

// 发送队列：存放已写入但尚未发送出去的 skb
struct sk_buff_head sk_write_queue;
```

**实战信号**：
- `sk_receive_queue.qlen` > 0 → 有数据未读
- `sk_write_queue.qlen` > 0 → 有数据未发送（可能发送慢或对端接收慢）
- **与 `/proc/net/tcp` 的 `rx_queue` / `tx_queue` 字段对应**——后者就是这两个队列的字节数

#### 3.2.4 等待队列与回调：`sk_sleep` / `sk_data_ready` / `sk_write_space`

```c
wait_queue_head_t *sk_sleep;    // 进程等待的 wait_queue（用户态 read 阻塞时挂入）

void (*sk_data_ready)(struct sock *sk);    // 数据到达回调（唤醒 sk_sleep 上的进程）
void (*sk_write_space)(struct sock *sk);  // 写空间可用回调
```

**实战用途**：
- 用户态 `read()` 阻塞 → 进程挂入 `sk->sk_sleep`
- 内核收到数据 → 调用 `sk->sk_data_ready` → 唤醒 `sk->sk_sleep` 上的进程
- 这就是 04 篇"阻塞 read 的实现"的核心机制

### 3.3 struct sock_common（更底层的"通用基类"）

`struct sock` 内嵌一个 `struct sock_common`——后者是真正的"协议无关基类"。

**源码位置**：`include/net/sock.h`

```c
struct sock_common {
    /* 1. 地址族（早期字段，频繁访问，提到顶部） */
    unsigned short      skc_family;       // AF_INET / AF_UNIX
    volatile unsigned char  skc_state;    // 协议层状态（sk_state 是这个的复制）
    unsigned char       skc_reuse : 4;    // SO_REUSEADDR
    unsigned char       skc_reuseport : 1;
    unsigned char       skc_ipv6only : 1;
    unsigned char       skc_net_refcnt : 1;

    int                 skc_bound_dev_if;  // 绑定的设备索引
    struct net          *skc_net;          // 所在网络命名空间

    /* 2. INET 通用 */
    struct ino          skc_rxhash;        // 用于 RSS
    ...
};
```

**作用**：
- 协议无关的最小通用结构
- AF_INET/AF_UNIX 都通过嵌入 `sock_common` 复用这部分
- `skc_state` 是 `sk_state` 的"物理存储"——访问 `sk->sk_state` 等价于访问 `sk->__sk_common.skc_state`

**实战意义**：
- 看 ftrace 中 `sock:inet_sock_set_state` 事件时——改变的是 `skc_state`
- 看 `ss -tan state <state>` 时——查询的也是这个字段

### 3.4 AF_INET 专用：struct inet_sock / struct tcp_sock

`struct sock` 之上还有协议特定的扩展结构。

**源码位置**：`include/net/inet_sock.h`、`include/linux/tcp.h`

```c
struct inet_sock {
    struct sock         sk;             // 内嵌 struct sock（向上继承）
    
    __u32               inet_daddr;     // 对端 IPv4 地址
    __u32               inet_rcv_saddr; // 本地绑定 IPv4 地址
    __u16               inet_dport;     // 对端端口（网络字节序）
    __u16               inet_sport;     // 本地端口
    ...
};

struct tcp_sock {
    struct inet_sock    inet;           // 内嵌 inet_sock
    
    /* TCP 状态机字段 */
    __u32               srtt;           // 平滑 RTT
    __u32               mdev;           // RTT 平均偏差
    __u32               snd_ssthresh;   // 慢启动阈值
    __u32               snd_cwnd;       // 拥塞窗口
    __u32               rcv_nxt;        // 期望接收的下一个字节
    
    /* 发送/接收状态 */
    u32                 copied_seq;     // 用户态已拷贝
    u32                 rcv_wup;        // 接收窗口更新点
    u32                 snd_nxt;        // 已发送的下一个字节
    u32                 snd_una;        // 已确认的下一个字节
    ...
};
```

**结构体层次**（AF_INET TCP）：
```
struct tcp_sock (TCP 特定)
  └─ struct inet_sock (INET 通用)
       └─ struct sock (协议通用)
            └─ struct sock_common (最底层基类)
```

**实战意义**：
- 找 TCP 拥塞窗口：`tcp_sock->snd_cwnd`
- 找 RTT：`tcp_sock->srtt`
- 找重传状态：`tcp_sock->retransmits`
- **但通过 `struct sock *` 也能找到它们**——container_of 宏

```c
// 已知 struct sock *sk，找 struct tcp_sock *
struct tcp_sock *tp = tcp_sk(sk);
```

### 3.5 AF_UNIX 专用：struct unix_sock

**源码位置**：`net/unix/af_unix.c`

```c
struct unix_sock {
    struct sock         sk;            // 内嵌 struct sock
    struct unix_address *addr;         // 绑定地址
    struct path         path;          // 路径型 UDS 的 dentry+ vfsmnt
    struct list_head    link;          // 全局 UDS 链表
    unsigned int        gc_candidate : 1;  // GC 候选
    unsigned int        gc_may_cycle : 1;
    ...
};
```

**与 tcp_sock 的对比**：
- UDS 没有拥塞控制、没有 RTT、没有 snd_cwnd——所以 unix_sock 简单很多
- 但有 `path` 字段（路径型 UDS 的文件系统路径）和 `link`（全局链表）

### 3.6 socket 三元组小结

```
[用户态]    fd (int)         ─→   fdtable[fd] = struct file *
                                                              ↓
[VFS层]    struct file       ←→   file->private_data = struct socket *
            ├ .f_op                              ↓
            └ .f_flags                    [BSD层] struct socket
                                              ├ .state (SS_*)
                                              ├ .type
                                              ├ .file ─→ struct file
                                              ├ .sk ─→ struct sock
                                              └ .ops = proto_ops
                                                            ↓
[协议层]    struct sock ──── sk->sk_socket ──── struct socket (反指)
            ├ .sk_prot = tcp_prot / unix_proto
            ├ .sk_state (TCP: TCP_* / UDS: SS_*)
            ├ .sk_receive_queue / .sk_write_queue
            ├ .sk_sleep
            └ .sk_data_ready / .sk_write_space 回调
                                                ↓
[协议扩展]  struct tcp_sock / struct unix_sock（内嵌 struct sock）
```

**最简关系**：
```
fd → file → socket → sock → sk_prot（具体协议实现）
        ↑                    ↓
        └── private_data ─── socket（双向）
```

---

## 四、协议层挂接：proto_ops 与 proto 的注册链

socket 的"协议可插拔"是通过**两层函数指针表**实现的：`struct proto_ops`（BSD 层接口）和 `struct proto`（协议层实现）。

### 4.1 struct proto_ops（BSD socket API 入口）

**源码位置**：`include/linux/net.h`

```c
struct proto_ops {
    int     family;                  // AF_INET / AF_UNIX
    struct module *owner;
    
    int     (*release)(struct socket *sock);                  // close 入口
    int     (*bind)(struct socket *sock, struct sockaddr *, int);
    int     (*connect)(struct socket *sock, struct sockaddr *, int, int flags);
    int     (*socketpair)(struct socket *sock1, struct socket *sock2);
    int     (*accept)(struct socket *sock, struct socket *newsock, int flags, bool kern);
    int     (*getname)(struct socket *sock, struct sockaddr *, int);
    __poll_t (*poll)(struct socket *sock, struct file *file, struct poll_table_struct *wait);
    int     (*ioctl)(struct socket *sock, unsigned int cmd, unsigned long arg);
    int     (*listen)(struct socket *sock, int len);
    int     (*shutdown)(struct socket *sock, int flags);
    int     (*setsockopt)(struct socket *sock, int level, int optname, char __user *optval, unsigned int optlen);
    int     (*getsockopt)(struct socket *sock, int level, int optname, char __user *optval, int __user *optlen);
    int     (*sendmsg)(struct socket *sock, struct msghdr *m, size_t total_len);
    int     (*recvmsg)(struct socket *sock, struct msghdr *m, size_t total_len, int flags);
    ...
};
```

**与用户态的对应**：
- `socket()->ops->bind()` = 用户调 `bind()`
- `socket()->ops->connect()` = 用户调 `connect()`
- `socket()->ops->poll()` = 用户调 `select/poll/epoll`（注意：`poll` 接收 `struct file`——用于 epoll 协作）

### 4.2 struct proto（协议实现）

**源码位置**：`include/net/sock.h`

```c
struct proto {
    void            (*close)(struct sock *sk, long timeout);
    int             (*connect)(struct sock *sk, struct sockaddr *uaddr, int addr_len);
    int             (*disconnect)(struct sock *sk, int flags);
    struct sock *   (*accept)(struct sock *sk, int flags, int *err, bool kern);
    int             (*ioctl)(struct sock *sk, int cmd, unsigned long arg);
    int             (*init)(struct sock *sk);
    void            (*destroy)(struct sock *sk);
    int             (*setsockopt)(struct sock *sk, int level, int optname, char __user *optval, unsigned int optlen);
    int             (*getsockopt)(struct sock *sk, int level, int optname, char __user *optval, int __user *optlen);
    int             (*sendmsg)(struct sock *sk, struct msghdr *m, size_t total_len);
    int             (*recvmsg)(struct sock *sk, struct msghdr *m, size_t total_len, int flags, int *err, int *flags);
    int             (*bind)(struct sock *sk, struct sockaddr *uaddr, int addr_len);
    int             (*backlog_rcv)(struct sock *sk, struct sk_buff *skb);
    void            (*release_cb)(struct sock *sk);
    
    /* 状态机相关 */
    int             (*hash)(struct sock *sk);
    void            (*unhash)(struct sock *sk);
    int             (*get_port)(struct sock *sk, unsigned short snum);
    
    /* 缓冲与窗口 */
    int             (*setsndbuf)(struct sock *sk, int val);
    int             (*setrcvbuf)(struct sock *sk, int val);
    
    /* 内存与生命周期 */
    int             (*memory_pressure)(struct sock *sk);
    void            (*enter_memory_pressure)(struct sock *sk);
    ...
};
```

**关键观察**：
- `proto_ops` 和 `proto` **很多方法同名**（`bind`/`connect`/`sendmsg`/`recvmsg`）——但接收的第一个参数不同：
  - `proto_ops::*` 接收 `struct socket *`
  - `proto::*` 接收 `struct sock *`
- 调用链是：`proto_ops::connect` 内部会跳转到 `proto::connect`

### 4.3 注册链：AF_INET → inet_stream_ops → tcp_prot

#### 4.3.1 协议族注册（net_families 数组）

```c
// net/socket.c
static DEFINE_SPINLOCK(net_family_lock);
static const struct net_proto_family __rcu *net_families[NPROTO] __read_mostly;

// 注册：sock_register
int sock_register(const struct net_proto_family *ops)
{
    ...
    rcu_assign_pointer(net_families[ops->family], ops);
    ...
}

// AF_INET 在 net/ipv4/af_inet.c 中注册
static const struct net_proto_family inet_family_ops = {
    .family = PF_INET,
    .create = inet_create,
    .owner  = THIS_MODULE,
};

fs_initcall(inet_init);  // 内核初始化时调用
  → inet_init() 中调用 sock_register(&inet_family_ops);
```

**关键点**：
- `net_families[AF_INET]` 在内核启动后指向 `inet_family_ops`
- 用户调 `socket(AF_INET, ...)` 时，`__sock_create` 通过 `net_families[AF_INET]->create` 跳到 `inet_create()`

#### 4.3.2 AF_INET 内部协议分流

```c
// net/ipv4/af_inet.c
static int inet_create(struct net *net, struct socket *sock, int protocol, int kern)
{
    struct sock *sk;
    ...
    
    /* 1. 找到协议（TCP/UDP/...） */
    list_for_each_entry_rcu(answer, &inetsw[sock->type], list) {
        if (protocol == answer->protocol) break;
    }
    
    /* 2. 分配 sock 对象（按 answer->prot 分配） */
    sk = sk_alloc(net, PF_INET, GFP_KERNEL, answer->prot, kern);
    
    /* 3. 初始化 sock 公共部分 */
    sock_init_data(sock, sk);  // sock->sk = sk; sk->sk_socket = sock;
    
    /* 4. 关联到 socket */
    sock->ops = answer->ops;     // 关键：sock->ops 来自 inetsw 表
    
    /* 5. 初始化协议（TCP 的三次握手状态等） */
    if (sk->sk_prot->init(sk)) { ... }
}
```

**核心数据结构** `inetsw[]`（inet socket switch table）：

```c
static struct inet_protosw inetsw_array[] = {
    {
        .type = SOCK_STREAM,
        .protocol = IPPROTO_TCP,
        .prot = &tcp_prot,            // ← TCP 协议实现
        .ops = &inet_stream_ops,      // ← TCP BSD ops
        ...
    },
    {
        .type = SOCK_DGRAM,
        .protocol = IPPROTO_UDP,
        .prot = &udp_prot,            // ← UDP 协议实现
        .ops = &inet_dgram_ops,
        ...
    },
    {
        .type = SOCK_DGRAM,
        .protocol = IPPROTO_ICMP,
        .prot = &ping_prot,
        .ops = &inet_dgram_ops,
        ...
    },
};
```

**关键洞察**：
- `inetsw[]` 是 **type + protocol → prot + ops** 的映射表
- 用户调 `socket(AF_INET, SOCK_STREAM, 0)` → 命中 `inetsw_array[0]` → `tcp_prot` + `inet_stream_ops`
- 用户调 `socket(AF_INET, SOCK_DGRAM, 0)` → 命中 `inetsw_array[1]` → `udp_prot` + `inet_dgram_ops`

#### 4.3.3 inet_stream_ops 与 tcp_prot

**inet_stream_ops**（`net/ipv4/af_inet.c`）：

```c
const struct proto_ops inet_stream_ops = {
    .family = PF_INET,
    .owner  = THIS_MODULE,
    .release = inet_release,           // → tcp_close
    .bind    = inet_bind,              // → tcp_v4_bind
    .connect = inet_stream_connect,    // → tcp_v4_connect
    .accept  = inet_accept,            // → inet_csk_accept
    .poll    = tcp_poll,               // ★ epoll 用这个
    .listen  = inet_listen,            // → tcp_listen
    .shutdown = inet_shutdown,
    .setsockopt = sock_common_setsockopt,
    .getsockopt = sock_common_getsockopt,
    .sendmsg = inet_sendmsg,           // → tcp_sendmsg
    .recvmsg = inet_recvmsg,           // → tcp_recvmsg
    ...
};
```

**tcp_prot**（`net/ipv4/tcp.c`）：

```c
struct proto tcp_prot = {
    .name       = "TCP",
    .owner      = THIS_MODULE,
    .close      = tcp_close,
    .connect    = tcp_v4_connect,
    .disconnect = tcp_disconnect,
    .accept     = inet_csk_accept,
    .ioctl      = tcp_ioctl,
    .init       = tcp_v4_init_sock,
    .destroy    = tcp_v4_destroy_sock,
    .setsockopt = tcp_setsockopt,
    .getsockopt = tcp_getsockopt,
    .sendmsg    = tcp_sendmsg,
    .recvmsg    = tcp_recvmsg,
    .backlog_rcv = tcp_v4_do_rcv,
    .hash       = inet_hash,
    .unhash     = inet_unhash,
    ...
};
```

**关键洞察**：
- `inet_stream_ops.bind` = `inet_bind`（BSD 层通用入口）→ 内部跳转到 `tcp_prot.bind`（如果存在）
- `inet_stream_ops.poll` = `tcp_poll`（TCP 专属 poll）—— epoll 用这个判断事件
- `inet_stream_ops.sendmsg` = `inet_sendmsg` → 内部调用 `sk->sk_prot->sendmsg`（即 `tcp_sendmsg`）

### 4.4 UDS 注册链：AF_UNIX → unix_stream_ops → unix_proto

```c
// net/unix/af_unix.c
static const struct net_proto_family unix_family_ops = {
    .family = PF_UNIX,
    .create = unix_create,
    .owner  = THIS_MODULE,
};

// 模块初始化
fs_initcall(af_unix_init);
  → af_unix_init() 中调用 sock_register(&unix_family_ops);
```

**unix_stream_ops 与 unix_dgram_ops**（`net/unix/af_unix.c`）：

```c
static const struct proto_ops unix_stream_ops = {
    .family = PF_UNIX,
    .owner  = THIS_MODULE,
    .release = unix_release,
    .bind    = unix_bind,
    .connect = unix_stream_connect,
    .socketpair = unix_socketpair,
    .accept  = unix_accept,
    .poll    = unix_poll,             // ★
    .listen  = unix_listen,
    .shutdown = unix_shutdown,
    .sendmsg = unix_stream_sendmsg,
    .recvmsg = unix_stream_recvmsg,
    ...
};

static const struct proto_ops unix_dgram_ops = {
    .family = PF_UNIX,
    .release = unix_dgram_release,
    .sendmsg = unix_dgram_sendmsg,
    .recvmsg = unix_dgram_recvmsg,
    ...
};
```

**unix_proto**（`net/unix/af_unix.c`）：

```c
struct proto unix_proto = {
    .name        = "UNIX",
    .owner       = THIS_MODULE,
    .close       = unix_release,
    .connect     = unix_stream_connect,
    .accept      = unix_accept,
    .ioctl       = unix_ioctl,
    .init        = unix_init_sock,
    .destroy     = unix_destroy_sock,
    .sendmsg     = unix_stream_sendmsg,
    .recvmsg     = unix_stream_recvmsg,
    .bind        = unix_bind,
    .hash        = unix_hash,
    .unhash      = unix_unhash,
    ...
};
```

**对比**：
- AF_INET 有 `inetsw[]` 进一步分 TCP/UDP/ICMP
- AF_UNIX 按 type（stream/dgram/seqpacket）直接对应 unix_stream_ops / unix_dgram_ops
- UDS 的 seqpacket 类型在 Linux 4.5+ 由 `unix_seqpacket_ops` 提供

### 4.5 完整调用链：read() 的 13 步路径

**场景**：app 从 InputChannel（UDS SOCK_SEQPACKET）read 触摸事件。

```
[用户态]    1. read(fd, buf, 8)
              ↓
[syscall]   2. __sys_recvfrom(fd, ...)
              fd → struct file → struct socket
              ↓
[BSD ops]   3. socket->ops->recvmsg()
              socket->ops = unix_stream_ops（或 unix_seqpacket_ops）
              ↓
[协议层]    4. unix_stream_recvmsg() / unix_dgram_recvmsg()
              sk = socket->sk
              ↓
[等待]      5. skb_recv_datagram() / skb_recv_udp()
              → 等待 sk->sk_receive_queue 上有数据
              → 进程挂入 sk->sk_sleep
              ↓
              ... 阻塞 ...
              ↓
[网卡/对端] 6. 收到数据（另一端 write 过来）
              ↓
[接收]      7. unix_dgram_recvmsg() / unix_stream_recvmsg()
              skb_dequeue(&sk->sk_receive_queue)
              ↓
[拷贝]      8. skb_copy_datagram_from_iter()
              copy_to_user(buf, skb->data, len)
              ↓
[唤醒]      9. sk->sk_data_ready(sk)  // 唤醒 sk_sleep 上的进程
              ↓
[返回]      10. 返回给用户 read()
              ↓
[用户态]    11. read() 返回，buf 装好数据
```

**关键观察**：
- 第 3 步是 `socket->ops->recvmsg`（BSD 层入口）
- 第 4 步是协议层具体实现（`unix_stream_recvmsg` / `tcp_recvmsg`）
- 第 5-6 步的"阻塞 + 唤醒"是 socket 阻塞的核心（详见 04 篇）
- 第 8 步是 `copy_to_user`——这是**数据从内核态到用户态的边界**

### 4.6 调用链对稳定性的意义

| 失败点 | 现象 | 根因 |
|--------|------|------|
| 第 1 步 fd 无效 | read 返回 -EBADF | fd 已关闭或未打开 |
| 第 3 步 ops 无效 | read 返回 -ENOPROTOOPT | socket 类型不匹配 |
| 第 5 步永久阻塞 | read 一直不返回 | 对端未写 + 无超时 |
| 第 5 步被意外唤醒 | read 返回 -EAGAIN | 非阻塞 + 暂无可读 |
| 第 6 步数据未达 | read 阻塞 | 网络丢包/对端 crash |
| 第 8 步 copy 失败 | read 返回 -EFAULT | 用户态 buf 失效 |
| 第 9 步 wakeup 漏掉 | read 永久阻塞 | 回调未注册或 sk_sleep 损坏 |

---

## 五、与 VFS 的绑定：socket_file_ops 与 /proc/pid/fd

socket 与 VFS 的"绑定"是通过 `struct file` 完成的——而 `struct file` 的关键字段是 `f_op`（指向 `socket_file_ops`）。

### 5.1 socket 与 struct file 的关系

#### 5.1.1 初始化路径

```c
// net/socket.c
struct file *sock_alloc_file(struct socket *sock, int flags, const char *dname)
{
    struct file *file;
    ...

    file = alloc_file_pseudo(sock->inode, sock_mnt, dname,
                O_RDWR | (flags & O_NONBLOCK), &socket_file_ops);
    if (IS_ERR(file))
        return file;

    sock->file = file;
    file->private_data = sock;     // ★ 关键：file → socket

    return file;
}
```

**关键关系**：
- `file->private_data = sock` —— VFS 通过 private_data 找到 socket
- `sock->file = file` —— socket 反向找到 file
- 双向指针建立后，**VFS 层的所有操作（read/write/poll/close）通过 `file->f_op` 找到 socket_file_ops，再跳到 socket**。

#### 5.1.2 close 路径

```c
// fs/open.c
int filp_close(struct file *filp, fl_owner_t id)
{
    ...
    fput(filp);  // 减少引用计数
    return 0;
}

// 最终调用 file->f_op->release(file, inode)
// 对 socket 而言：socket_file_ops.release = sock_close
```

`sock_close()` 已经在 §2.7 详述。

### 5.2 socket_file_ops（socket 的 file_operations）

**源码位置**：`net/socket.c`

```c
static const struct file_operations socket_file_ops = {
    .owner =    THIS_MODULE,
    .llseek =   no_llseek,           // socket 不支持 llseek
    .read_iter =    sock_read_iter,  // → sock_recvmsg
    .write_iter =   sock_write_iter, // → sock_sendmsg
    .poll =     sock_poll,           // → socket->ops->poll
    .unlocked_ioctl = sock_ioctl,    // → socket->ops->ioctl
    .mmap =     sock_mmap,           // 用于一些特殊场景
    .release =  sock_close,          // close 入口
    ...
};
```

**关键观察**：

| file_operations 方法 | 实现 | 跳转到 |
|----------------------|------|--------|
| `.read_iter` | `sock_read_iter` | 内部调 `socket->ops->recvmsg`（协议族相关） |
| `.write_iter` | `sock_write_iter` | 内部调 `socket->ops->sendmsg` |
| `.poll` | `sock_poll` | 调 `socket->ops->poll`（关键！epoll 用） |
| `.release` | `sock_close` | 调 `socket->ops->release` |
| `.unlocked_ioctl` | `sock_ioctl` | 调 `socket->ops->ioctl` |

**`sock_poll` 源码**：

```c
// net/socket.c
static __poll_t sock_poll(struct file *file, struct poll_table_struct *wait)
{
    struct socket *sock = file->private_data;
    __poll_t events = 0;

    poll_wait(file, sock->wq, wait);  // ★ 注册到 socket 的 wait queue

    if (!sock->ops->poll)
        return POLLNVAL;
    
    events = sock->ops->poll(sock, file, wait);  // → tcp_poll / unix_poll

    return events;
}
```

**关键**：
- `poll_wait` 把当前进程挂入 `sock->wq`（socket 的 wait queue）
- `sock->ops->poll` 跳到协议族 poll（如 `tcp_poll`）
- **这就是为什么 epoll 能监听 socket——见 [epoll 01](../epoll/01-epoll总览与核心机制.md) §3 详细机制**

### 5.3 socket 的特殊 inode（sock_inode）

socket 不是普通文件，但需要一个 inode 才能挂入 VFS。

```c
// net/socket.c
static struct inode *sock_alloc_inode(struct super_block *sb)
{
    struct socket_alloc *i;
    
    i = kmem_cache_alloc(sock_inode_cachep, GFP_KERNEL);
    if (!i)
        return NULL;
    
    return &i->vfs_inode;
}

static void sock_destroy_inode(struct inode *inode)
{
    kmem_cache_free(sock_inode_cachep, container_of(inode, struct socket_alloc, vfs_inode));
}

// 注册伪文件系统
static int __init sock_init(void)
{
    int err;
    ...
    
    sock_mnt = kern_mount(&sock_fs_type);
    if (IS_ERR(sock_mnt))
        return PTR_ERR(sock_mnt);
    ...
}

static struct file_system_type sock_fs_type = {
    .name =       "sockfs",
    .mount =      sockfs_mount,
    .kill_sb =    kill_anon_super,
};
```

**关键观察**：
- socket 走**伪文件系统** `sockfs`（与 `pipefs`、`tmpfs` 类似）
- 每个 socket 分配一个 `socket_alloc`（内嵌 `struct inode`）
- inode 的 `i_mode = S_IFSOCK`（标识为 socket 类型）

**与 VFS 关系**：
- 普通文件 inode → 关联到磁盘文件
- socket inode → 关联到 `struct socket`
- 但都遵循 VFS 接口——这是 Unix "everything is a file" 的实现

### 5.4 /proc/pid/fd 中看到的 socket

#### 5.4.1 /proc/pid/fd 输出格式

```bash
$ ls -l /proc/<pid>/fd/
lrwx------ 1 system system 64 ... 0 -> /dev/null
lrwx------ 1 system system 64 ... 1 -> /dev/null
lrwx------ 1 system system 64 ... 2 -> /dev/null
lrwx------ 1 system system 64 ... 3 -> socket:[12345]
lrwx------ 1 system system 64 ... 4 -> socket:[12346]
lrwx------ 1 system system 64 ... 5 -> pipe:[67890]
lrwx------ 1 system system 64 ... 6 -> anon_inode:[eventpoll]
```

**关键观察**：
- `socket:[12345]` —— socket 类型，inode=12345
- `pipe:[67890]` —— pipe 类型，inode=67890
- `anon_inode:[eventpoll]` —— 匿名 inode（如 eventfd、eventpoll 等）

**实战技巧**：
- socket fd 的 inode 必须在 `/proc/net/tcp` 或 `/proc/net/unix` 中能找到（详见 08 §2.3.2）

#### 5.4.2 /proc/net/sockstat 字段来源

```c
// net/ipv4/proc.c
static int sockstat_seq_show(struct seq_file *seq, void *v)
{
    ...
    seq_printf(seq, "TCP:   inuse %d orphan %d tw %d alloc %d mem %d\n",
           ...);
    ...
}
```

这些字段直接来自内核中的 `tcp_hashinfo` 等全局变量——**这是 `/proc/net/sockstat` 的"字段来源对照"**。

#### 5.4.3 /proc/net/tcp 字段来源

```c
// net/ipv4/tcp_ipv4.c
static int tcp4_seq_show(struct seq_file *seq, void *v)
{
    ...
    seq_printf(seq, "%4d: %08X:%04X %08X:%04X "
        "%02X %08X:%08X %02X:%08lX %08X %5u %8d %lu %d %pK %u "
        "%u %u %u %u %d",
        i, src, srcp, dest, destp, state,
        tp->write_seq - tp->snd_una,  // tx_queue
        rx_queue,
        ...);
}
```

**字段对应**：
- `tx_queue` ← `tp->write_seq - tp->snd_una`（已发送但未确认的字节数）
- `rx_queue` ← `sk->sk_receive_queue` 的字节总数
- `st` ← `sk->sk_state`（TCP 状态码）

**实战意义**：
- 看 `/proc/net/tcp` 输出时，知道每个字段来自 `struct tcp_sock` / `struct sock` 的哪个成员
- 看 `tx_queue > 0` 立刻知道是 `tp->write_seq > tp->snd_una`（数据未确认）

### 5.5 三大场景在 /proc/pid/fd 中的具体表现

#### 5.5.1 Zygote 监听 socket

**场景**：system_server 启动时通过 `LocalSocket` 监听 `/dev/socket/zygote`

```bash
# zygote64 进程的 fd
$ ls -l /proc/$(pidof zygote64)/fd | grep socket
lrwx------ ... 12 -> socket:[18432]   # /dev/socket/zygote 监听 socket
lrwx------ ... 13 -> socket:[19847]   # 某个 client 连接（fork 出去的 app 进程）
...
```

**对应关系**：
- `socket:[18432]` 在 `/proc/net/unix` 中：
  ```
  Num  RefCount Protocol Flags    Type  St  Inode  Path
  0:  00000002 00000000 0001     01    18432  /dev/socket/zygote
  ```
- 状态码 `01` = LISTEN

**稳定性意义**：
- **Zygote 进程 socket 数量持续增长** → USAP 进程或 app 进程未正常关闭 client socket
- **listen socket 不在** → Zygote 监听失败，所有 app 启动失败

#### 5.5.2 InputChannel（socketpair 配对）

**场景**：app 与 system_server 之间的触摸事件通道

```bash
# app 进程的 fd
$ ls -l /proc/$(pidof com.example.app)/fd | grep socket
...
lrwx------ ... 87 -> socket:[24513]   # InputChannel 端 1（app 端 read）
lrwx------ ... 88 -> socket:[24514]   # InputChannel 端 2（system_server 端 write）
...
```

**关键**：
- InputChannel 是 `socketpair(AF_UNIX, SOCK_SEQPACKET, 0)` 产生的**两个独立 socket 对象**
- app 进程持有 read 端，system_server 持有 write 端
- **但 app 进程的 fd 表中**有**两个 socket fd**——这是 socketpair 的特性（一对独立 socket）

**实战排查**：
- 查找 InputChannel：app 进程的 socket fd 中，**没有 path**（abstract 或 socketpair）的两个连续 inode
- 更可靠方式：从 `dumpsys input` 中读取（08 §2.6.1 详述）

#### 5.5.3 Choreographer BitTube（socketpair 配对）

**场景**：SurfaceFlinger 与 app 之间传递 VSync

```bash
# app 进程的 fd
$ ls -l /proc/$(pidof com.example.app)/fd | grep socket
...
lrwx------ ... 90 -> socket:[30500]   # BitTube 端 1（app 端 read VSync）
lrwx------ ... 91 -> socket:[30501]   # BitTube 端 2（SurfaceFlinger 端 write）
...
```

**与 InputChannel 的区别**：
- BitTube 是 `socketpair(AF_UNIX, SOCK_STREAM)`（SOCK_STREAM 不是 SOCK_SEQPACKET）
- BitTube 是**单向**——VSync 只能从 SF 发到 app
- InputChannel 是**双向** seqpacket

**源码**：`frameworks/native/libs/gui/BitTube.cpp`

```cpp
BitTube::BitTube(size_t bufsize) {
    ...
    int sv[2];
    socketpair(AF_UNIX, SOCK_STREAM, 0, sv);
    mReceiveFd = sv[0];
    mSendFd = sv[1];
    // app 用 mReceiveFd（read 端）
    // SF 用 mSendFd（write 端）
}
```

#### 5.5.4 应用网络 socket

**场景**：OkHttp 创建的 HTTP 连接

```bash
# app 进程的 fd
$ ls -l /proc/$(pidof com.example.app)/fd | grep socket
...
lrwx------ ... 100 -> socket:[35001]   # 与 api.example.com:443 的 TCP 连接
lrwx------ ... 101 -> socket:[35002]   # 另一个连接
...
```

**对应关系**：
- `socket:[35001]` 在 `/proc/net/tcp` 中：
  ```
  0: 0100007F:1F90 0100007F:9C40 01 ... 35001 ...
  ```
- 本地地址 `0100007F:1F90` = 127.0.0.1:8080
- 对端地址 `0100007F:9C40` = 127.0.0.1:40000
- 状态 `01` = ESTABLISHED

**稳定性意义**：
- 异常 socket 数量持续增长 → 连接泄漏
- CLOSE_WAIT 状态的 socket 多 → 应用未 close

### 5.6 FD 泄漏的四重含义

理解了 fd → file → socket → sock 的关系后，**FD 泄漏的完整含义**就清晰了：

```
fd 未关闭
   ↓
struct file 未释放
   ↓
struct socket 未释放
   ↓
struct sock 未释放（sk_refcnt > 0）
   ↓
协议层资源未释放（TCP 状态、UDS 路径、sk_buff 等）
```

**任何一环卡住都会导致后续环节泄漏**——这就是为什么 FD 泄漏排查需要"逐层定位"。

**典型场景**：
- 进程 crash → fd 自然释放（内核清理）
- 进程不 crash 但 fd 增长 → 必有代码路径不调 close
- 代码不调 close → `sock` 引用计数 > 0 → 即使 socket 析构也不释放内核对象

---

## 六、综合：诊断工具与三大结构体的对应

> 把 §2-5 的知识汇总成"诊断工具的每个输出对应到哪个结构体、哪个字段"——这是工程师现场排查的"翻译表"。

### 6.1 /proc/net/tcp 字段→内核结构对照表

| /proc/net/tcp 字段 | 内核结构 | 成员 | 实战用途 |
|--------------------|----------|------|----------|
| `sl` | `seq_operations` 序号 | （proc 输出序号） | 排序 |
| `local_address` | `struct sock_common` | `skc_rcv_saddr` + `inet_sport` | 找本地监听 |
| `rem_address` | `struct sock_common` | `skc_daddr` + `inet_dport` | 找连接对端 |
| `st` | `struct sock` | `__sk_common.skc_state` | TCP 状态机 |
| `tx_queue` | `struct tcp_sock` | `write_seq - snd_una` | 未确认字节数 |
| `rx_queue` | `struct sock` | `sk_receive_queue` 字节总数 | 接收队列堆积 |
| `tr` | `struct tcp_sock` | `retransmits` | 重传次数（IPv4 才有） |
| `tm->when` | `struct tcp_sock` | `timer.expires` | 重传定时器到期时间 |
| `retrnsmt` | `struct tcp_sock` | `retransmits` | 重传次数（同 tr） |
| `uid` | `struct sock` | `sk_uid` | socket 所属用户 |
| `timeout` | `struct sock` | `sk_timer.expires` | 定时器到期时间 |
| `inode` | `struct socket` | `socket_alloc.vfs_inode.i_ino` | 关联 /proc/pid/fd |

**实战**：
- 看 `tx_queue > 0`：立即知道是 `write_seq > snd_una`（数据已发送未确认）→ 网络丢包或对端接收慢
- 看 `rx_queue > 0`：立即知道是 `sk_receive_queue` 有数据 → 用户态 read 慢

### 6.2 /proc/net/unix 字段→内核结构对照表

| /proc/net/unix 字段 | 内核结构 | 成员 |
|--------------------|----------|------|
| `Num` | 序号 | — |
| `RefCount` | `struct sock` | `sk_refcnt` |
| `Protocol` | `struct proto` | `0`（UDS 不用 protocol 字段） |
| `Flags` | `struct sock` | `sk_flags`（如 SOCK_PASSCRED） |
| `Type` | `struct socket` | `type`（SOCK_STREAM=1 / SOCK_DGRAM=2 / SOCK_SEQPACKET=5） |
| `St` | `struct socket` | `state`（SS_UNCONNECTED=1 / SS_LISTENING=4 / SS_CONNECTED=3） |
| `Inode` | `struct socket` | `socket_alloc.vfs_inode.i_ino` |
| `Path` | `struct unix_sock` | `addr->name` 或 NULL |

**实战**：
- Type=5 (SOCK_SEQPACKET)：通常是 InputChannel
- St=4 (SS_LISTENING)：监听 socket
- St=3 (SS_CONNECTED)：已连接 socket
- Path 以 `/dev/socket/` 开头：init.rc 创建的 socket
- Path 以 `@` 开头：abstract 命名空间

### 6.3 strace 输出→内核入口对照表

| strace 输出 | 内核入口 | 实际调用 |
|-------------|----------|----------|
| `socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)` | `__sys_socket` | → `sock_create` → `inet_create` → 分配 `tcp_sock` |
| `bind(3, {sa_family=AF_INET, sin_port=htons(80), ...}, 16)` | `__sys_bind` | → `sock->ops->bind` = `inet_bind` |
| `listen(3, 128)` | `__sys_listen` | → `inet_listen` → `tcp_listen` |
| `accept(3, ...)` | `__sys_accept4` | → `inet_accept` → 等待完成队列 |
| `connect(4, {sa_family=AF_UNIX, sun_path="/dev/socket/zygote"}, 110)` | `__sys_connect` | → `sock->ops->connect` = `unix_stream_connect` |
| `read(4, buf, 8)` | `__sys_recvfrom` | → `socket->ops->recvmsg` = `unix_stream_recvmsg` |
| `write(4, buf, len)` | `__sys_sendto` | → `socket->ops->sendmsg` = `unix_stream_sendmsg` |
| `close(4)` | `__close_fd` | → `file->f_op->release` = `sock_close` |

**实战信号**：
- strace 看到 `connect()` 长时间无返回 → 内核卡在 `inet_stream_connect` → 三次握手未完成
- strace 看到 `read()` 阻塞 30s+ → 内核卡在 `unix_stream_recvmsg` 的 `skb_recv_datagram` → 等待对端

### 6.4 ANR trace 栈→内核调用对照

**典型栈**：

```
"main" tid=1 Sleeping
  at java.net.SocketInputStream.read(SocketInputStream.java:0)
  at java.net.SocketInputStream.read(SocketInputStream.java:0)
  ...
  at java.net.Socket.connect(Socket.java:0)
  ...
```

**对应内核调用**：

| Java 调用 | 内核函数 | 内核文件 |
|-----------|----------|----------|
| `SocketInputStream.read` | `__sys_recvfrom` → `inet_recvmsg` → `tcp_recvmsg` → `sk_wait_data` | net/socket.c, net/ipv4/tcp.c |
| `Socket.connect` | `__sys_connect` → `inet_stream_connect` → `tcp_v4_connect` → `inet_wait_for_connect` | net/socket.c, net/ipv4/af_inet.c |
| `ServerSocket.accept` | `__sys_accept4` → `inet_accept` → `inet_csk_accept` | net/socket.c, net/ipv4/af_inet.c |
| `FileInputStream.read` | （非 socket） | — |

**实战意义**：
- ANR 栈定位到 `SocketInputStream.read` → 内核卡在 `sk_wait_data`（等待数据）→ 上游主线程阻塞
- ANR 栈定位到 `Socket.connect` → 内核卡在 `inet_wait_for_connect`（等待三次握手）→ 网络慢或对端无响应

### 6.5 socket 三元组的"全栈查询"脚本

**一键脚本**：给定 fd，输出该 socket 的完整信息。

```bash
#!/bin/bash
# 已知某进程的某 fd，输出该 socket 的所有信息
PID=$1
FD=$2

echo "=== fd=$FD in pid=$PID ==="

# 1. fd 后端类型
TARGET=$(readlink /proc/$PID/fd/$FD 2>/dev/null)
echo "fd 指向: $TARGET"

# 2. 提取 inode
if [[ "$TARGET" == socket:* ]]; then
    INODE=$(echo $TARGET | grep -oP '\[\K[0-9]+')
    echo "inode: $INODE"
    
    # 3. 查 /proc/net/tcp
    echo "--- /proc/net/tcp 匹配 ---"
    grep " $INODE " /proc/net/tcp 2>/dev/null
    
    # 4. 查 /proc/net/tcp6
    echo "--- /proc/net/tcp6 匹配 ---"
    grep " $INODE " /proc/net/tcp6 2>/dev/null
    
    # 5. 查 /proc/net/unix
    echo "--- /proc/net/unix 匹配 ---"
    grep " $INODE " /proc/net/unix 2>/dev/null
fi
```

**使用示例**：
```bash
$ ./socket_query.sh 1234 4
=== fd=4 in pid=1234 ===
fd 指向: socket:[24513]
inode: 24513
--- /proc/net/tcp 匹配 ---
   0: 0100007F:1F90 0100007F:9C40 01 00000000:00000000 00:00000000 00000000  1000        0 24513 1 ...
--- /proc/net/unix 匹配 ---
(无匹配)
```

**实战意义**：
- 一行命令把"进程 fd"翻译成"具体连接信息"——这是 FD 排查的"瑞士军刀"

---

## 七、稳定性关联与实战案例

### 7.1 socket 三元组的"3 个最容易出问题的关系"

#### 7.1.1 `file->private_data` 与 `socket` 不一致

**场景**：dup() 后 file 不同但 socket 相同——close 其中一个不会真正释放 socket

```c
int s1 = socket(AF_INET, SOCK_STREAM, 0);
int s2 = dup(s1);  // s2 与 s1 共享同一 socket 对象

close(s1);  // socket 引用计数 1
close(s2);  // socket 引用计数 0 → 真正释放
```

**问题**：如果代码路径中只 close s1 但 close s2 失败 → 引用计数 1 → socket 泄漏
**诊断**：`/proc/pid/fd` 中看同一 socket:[inode] 出现多次

#### 7.1.2 `socket->sk` 与 `sk->sk_socket` 单向破坏

**场景**：自定义 socket 释放逻辑中只解了一边指针

```c
// 错误示例（虚构）
sock->sk = NULL;  // 清掉 socket → sk
// 但 sk->sk_socket 没清！下次 sk 释放时再访问 sk->sk_socket = NULL
// 可能导致 use-after-free
```

**正确**：`sock_release` 会同时清两边指针，不要单边操作
**诊断**：内核 Oops 出现 `sock_release` 栈 → 怀疑本类问题

#### 7.1.3 `sk->sk_prot` 误用（协议层对象不匹配）

**场景**：AF_INET 协议族下，错误地调用了 UDS 协议的方法

**典型表现**：内核 Oops 或 panic
**诊断**：内核日志 `BUG: unable to handle kernel paging request at ...` + backtrace 含 `tcp_*` 或 `unix_*`

### 7.2 实战案例：socket 泄漏的完整排查

#### 现象

某 app 启动后 fd 持续增长，从 100 个增长到 8000 个后被 RLIMIT_NOFILE=32768 阻断，最终无法连接服务器。

#### 排查步骤（按本篇 02 知识）

**步骤 1：看进程 fd 总数**
```bash
$ ls /proc/<pid>/fd | wc -l
7892
```
- 单进程 7892 个 fd——严重异常

**步骤 2：分类 socket**
```bash
$ ls -l /proc/<pid>/fd | grep socket | wc -l
7800   # 其中 socket 占 7800 个
```
- 几乎全部是 socket fd——典型 socket 泄漏

**步骤 3：找 socket 连接状态**
```bash
$ for ino in $(ls -l /proc/<pid>/fd | grep socket | awk -F'[][]' '{print $2}'); do
    grep " $ino " /proc/net/tcp
done | awk '{print $4}' | sort | uniq -c
   5000 CLOSE_WAIT   # ← 关键！
   2500 ESTABLISHED
    300 TIME_WAIT
```
- **CLOSE_WAIT 5000 个**——应用未 close 的典型表现

**步骤 4：定位到具体业务**

按本篇 6.5 的脚本找几个 CLOSE_WAIT 连接的"对端 IP"：
```bash
$ ./socket_query.sh <pid> 1023
fd 指向: socket:[45678]
--- /proc/net/tcp 匹配 ---
   ...
   local: 10.0.0.1:12345
   remote: 10.0.0.100:443
   state: CLOSE_WAIT
   uid: 10086
```

**步骤 5：定位代码**
- `uid=10086` → 某 app
- 找到代码中 `OkHttpClient` 创建处——确认是否在 `finally` 块中 `close()` Response

**步骤 6：定位根因**

业务代码（伪代码）：
```java
public void fetchData() {
    try {
        Response response = okHttpClient.newCall(request).execute();
        process(response.body().string());
    } catch (IOException e) {
        // ← 没有 finally close response！
        Log.e(TAG, "fetch failed", e);
    }
}
```

**根因**：`response` 未在 `finally` 关闭 → OkHttp 底层 socket 不会关闭 → CLOSE_WAIT 累积

**修复**：
```java
public void fetchData() {
    Response response = null;
    try {
        response = okHttpClient.newCall(request).execute();
        process(response.body().string());
    } catch (IOException e) {
        Log.e(TAG, "fetch failed", e);
    } finally {
        if (response != null) response.close();  // ← 关键修复
    }
}
```

**长期治理**：
- fdsan 检测（08 §4.1.1）
- StrictMode 检测泄漏
- OkHttp 推荐用 `try-with-resources` 风格或确保 `close()`

#### 案例总结

| 维度 | 内容 |
|------|------|
| 涉及结构体 | struct file / struct socket / struct sock / struct tcp_sock |
| 排查工具 | `/proc/pid/fd` 分类 + inode 关联 + 状态码识别 |
| 根因 | Java 层未 close Response → socket 不释放 → CLOSE_WAIT 累积 |
| 修复 | finally close + fdsan 检测 |
| 关联风险类 | ①FD 耗尽 + ④协议失败（连接无法建立） |

---

## 八、附录

### 附录 A：核心源码路径索引

| 文件名 | 完整路径 | 内核/AOSP 版本 | 说明 |
|--------|----------|----------------|------|
| net/socket.c | net/socket.c | Linux 5.10+ | 通用 socket 层、syscall 入口 |
| include/linux/net.h | include/linux/net.h | Linux 5.10+ | struct socket 定义 |
| include/net/sock.h | include/net/sock.h | Linux 5.10+ | struct sock / struct sock_common 定义 |
| include/net/inet_sock.h | include/net/inet_sock.h | Linux 5.10+ | struct inet_sock 定义 |
| include/linux/tcp.h | include/linux/tcp.h | Linux 5.10+ | struct tcp_sock 定义 |
| net/ipv4/af_inet.c | net/ipv4/af_inet.c | Linux 5.10+ | INET 协议族入口 |
| net/ipv4/tcp.c | net/ipv4/tcp.c | Linux 5.10+ | TCP 协议实现 |
| net/ipv4/tcp_ipv4.c | net/ipv4/tcp_ipv4.c | Linux 5.10+ | TCP IPv4 路径 |
| net/ipv4/proc.c | net/ipv4/proc.c | Linux 5.10+ | /proc/net/* 输出 |
| net/unix/af_unix.c | net/unix/af_unix.c | Linux 5.10+ | UDS 协议族 |
| net/core/sock.c | net/core/sock.c | Linux 5.10+ | socket 通用层（释放、引用计数） |
| fs/open.c | fs/open.c | Linux 5.10+ | close() 实现 |
| include/linux/fs.h | include/linux/fs.h | Linux 5.10+ | struct file 定义 |
| fs/proc/fd.c | fs/proc/fd.c | Linux 5.10+ | /proc/pid/fd 输出 |
| fs/eventpoll.c | fs/eventpoll.c | Linux 5.10+ | epoll 监听 socket |
| include/uapi/linux/in.h | include/uapi/linux/in.h | Linux 5.10+ | AF_INET 等常量 |
| frameworks/base/core/java/com/android/internal/os/ZygoteServer.java | AOSP 14 | Zygote 监听 socket 入口 |
| frameworks/native/libs/input/InputTransport.cpp | AOSP 14 | InputChannel socketpair |

### 附录 B：数据结构字段速查卡

#### B.1 struct socket 关键字段

| 字段 | 类型 | 用途 |
|------|------|------|
| state | socket_state | SS_UNCONNECTED/CONNECTED/LISTENING |
| type | short | SOCK_STREAM/DGRAM/SEQPACKET |
| file | struct file* | VFS 后端 |
| sk | struct sock* | 协议层对象 |
| ops | proto_ops* | 协议族操作集 |

#### B.2 struct sock 关键字段

| 字段 | 类型 | 用途 |
|------|------|------|
| sk_socket | struct socket* | 双向指针（反指 socket） |
| sk_prot | struct proto* | 协议实现 |
| sk_state | __u8 | 协议层状态（skc_state） |
| sk_receive_queue | sk_buff_head | 接收队列 |
| sk_write_queue | sk_buff_head | 发送队列 |
| sk_sleep | wait_queue_head_t* | 阻塞等待队列 |
| sk_data_ready | function ptr | 数据就绪回调 |
| sk_write_space | function ptr | 写空间可用回调 |
| sk_sndbuf | int | 发送 buffer 上限 |
| sk_rcvbuf | int | 接收 buffer 上限 |
| sk_refcnt | atomic_t | sock 引用计数 |

#### B.3 struct file 与 socket 关联字段

| 字段 | 用途 |
|------|------|
| f_op | file_operations 指针，socket 时指向 socket_file_ops |
| private_data | 指向 struct socket |
| f_flags | O_NONBLOCK / O_CLOEXEC 等 |

#### B.4 TCP 状态码 vs BSD socket state 对照

| TCP 状态（sk_state） | BSD state（socket->state） | 含义 |
|----------------------|---------------------------|------|
| TCP_ESTABLISHED (1) | SS_CONNECTED | 已建立 |
| TCP_SYN_SENT (2) | SS_CONNECTING | 客户端发 SYN |
| TCP_SYN_RECV (3) | SS_CONNECTING | 服务端收 SYN |
| TCP_FIN_WAIT1 (4) | SS_DISCONNECTING | 主动关闭方发 FIN |
| TCP_CLOSE_WAIT (8) | SS_DISCONNECTING | 被动关闭方收 FIN |
| TCP_LAST_ACK (9) | SS_DISCONNECTING | 被动关闭方发 FIN |
| TCP_LISTEN (10) | SS_LISTENING | 监听 |
| TCP_CLOSE (7) | SS_UNCONNECTED | 已关闭 |
| TCP_TIME_WAIT (6) | SS_UNCONNECTED | 2MSL 等待 |

### 附录 C：完整调用链速查

#### C.1 socket() 完整调用链（13 步）

```
1. 用户态: socket(AF_INET, SOCK_STREAM, 0)
2. SYSCALL_DEFINE3(socket, ...) → __sys_socket()
3. sock_create(family, type, protocol, &sock)
4. __sock_create() → net_families[family]->create = inet_create
5. inet_create() → sk_alloc(..., tcp_prot, ...)
6. sock_init_data(sock, sk)  // 双向指针
7. sock->ops = inet_stream_ops
8. sk->sk_prot = tcp_prot
9. __sock_create() 返回
10. sock_map_fd(sock, flags)
11. sock_alloc_file() → alloc_file_pseudo(..., socket_file_ops)
12. file->private_data = sock; sock->file = file
13. fd_install(fd, file) → 返回 fd
```

#### C.2 read() 完整调用链（11 步）

```
1. 用户态: read(fd, buf, 8)
2. SYSCALL_DEFINE3(read, ...) → __sys_recvfrom()
3. sockfd_lookup(fd) → file → socket
4. socket->ops->recvmsg = unix_stream_recvmsg
5. sk = socket->sk
6. skb_recv_datagram() / unix_stream_recvmsg() 内部
7. 进程挂入 sk->sk_sleep
... 阻塞 ...
8. 另一端 write 唤醒 sk->sk_data_ready
9. skb_dequeue(&sk->sk_receive_queue)
10. skb_copy_datagram_from_iter() → copy_to_user()
11. 返回用户态
```

#### C.3 close() 完整调用链（8 步）

```
1. 用户态: close(fd)
2. fs/open.c: __close_fd() / filp_close()
3. fput() 减少 file 引用计数
4. file->f_op->release = sock_close
5. sock_close() → socket->ops->release
6. inet_release() → tcp_close() / unix_release()
7. sock_release()
8. sock_put() 减 sk_refcnt，到 0 时释放协议层对象
```

### 附录 D：量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据来源 |
|------|----------|--------|----------|
| 1 | fd → file → socket → sock 调用层数 | 4 层 | 内核代码 |
| 2 | 一次 socket() 涉及的函数调用 | ~13 步 | 调用链追踪 |
| 3 | struct socket 大小 | ~64 字节 | sizeof(struct socket) |
| 4 | struct sock 基础大小 | ~500 字节 | sizeof(struct sock) |
| 5 | struct tcp_sock 大小 | ~2KB | sizeof(struct tcp_sock) |
| 6 | struct file 大小 | ~200 字节 | sizeof(struct file) |
| 7 | file_operations 关键方法数 | 9 个（socket_file_ops） | net/socket.c |
| 8 | proto_ops 关键方法数 | 12+ 个 | include/linux/net.h |
| 9 | proto 关键方法数 | 15+ 个 | include/net/sock.h |
| 10 | net_families 数组大小 | NPROTO = 40+ | include/linux/socket.h |
| 11 | inetsw 协议项数 | 3+（TCP/UDP/ICMP/...） | net/ipv4/af_inet.c |
| 12 | struct sock 队列数 | 3 个（rcv/wr/err） | include/net/sock.h |
| 13 | sock 引用计数原子操作次数 | 每次 dup/close 各 1 次 | net/core/sock.c |
| 14 | strace 网络 syscall 类型数 | 8+ | net/socket.c |
| 15 | read() 调用链函数数 | 11 步 | 调用链追踪 |
| 16 | ANR trace 中 socket 阻塞常见栈 | 5+ 个 | 实测 |

### 附录 E：与其他文章的关系

| 文章 | 本文引用位置 |
|------|--------------|
| 01-Socket 总览 | §1.2 三层视角图、§1.3 三大结构体分工 |
| 03-Socket 生命周期（待写） | §2.3-§2.7 系统调用展开为状态机 |
| 04-Socket 缓冲 | §3.2.3 队列字段、§4.5 read 调用链中缓冲位置 |
| 05-listen backlog | §2.3.2 inet_listen 中 backlog 处理、§4.3.2 inetsw 表 |
| 06-UDS 与 Android | §4.4 UDS 注册链、§5.5.2 InputChannel socketpair |
| 07-风险全景 | §7.2 实战案例属于 ①FD 耗尽 + ④协议失败 联动 |
| 08-诊断治理 | §6 诊断工具与结构体对照 |
| bridge/01-socket 与 epoll | §5.2 socket_file_ops.poll 是 epoll 入口 |
| epoll 01-epoll 总览 | §5.2 sock_poll 调 poll_wait 详细机制 |
| IO 07-IO 与进程阻塞 | §3.2.4 sk_sleep 阻塞机制 |
| VFS 04-VFS 与文件系统 | §5.3 socket 伪文件系统 sockfs |

---

## 篇尾衔接

本篇把 socket 的"骨架"（API + 数据结构）展开为可读源码——下一篇 [03-Socket连接生命周期：从创建到关闭](../socket/03-Socket连接生命周期.md) 将以本篇为基础，展开 socket 对象的**完整生命周期**：

- **创建**：`socket()` → `__sys_socket` → `sock_create` → 协议族 create（01/02 已涉及，本篇深化）
- **绑定**：`bind()` → `sock->ops->bind` → `inet_bind` / `unix_bind`（端口冲突、抽象命名空间）
- **监听**：`listen()` → `inet_listen` → `tcp_listen`（backlog 详细处理）
- **接受**：`accept()` → `inet_accept` → 等待完成队列（阻塞/非阻塞差异）
- **连接**：`connect()` → `inet_stream_connect` → TCP 三次握手状态机（SYN_SENT/ESTABLISHED）
- **关闭**：`close()` → `sock_close` → 协议层 release（FIN 发送、sock 引用计数归零）
- **特殊状态**：TIME_WAIT 的来源、CLOSE_WAIT 的根因、TIME_WAIT 优化

**03 篇特别关注**：
- **TIME_WAIT 的 60 秒等待**为什么是必要的
- **CLOSE_WAIT 持续累积**的应用层根因
- **shutdown() 与 close() 的差异**
- **四次挥手 vs 三次握手**的状态对应

socket 系列 8 篇规划已写 5 篇（01/02/04/05/06/07/08）+ 桥接 1 + epoll 1，03 是"机制深潜"篇章的最后一片拼图。

---


