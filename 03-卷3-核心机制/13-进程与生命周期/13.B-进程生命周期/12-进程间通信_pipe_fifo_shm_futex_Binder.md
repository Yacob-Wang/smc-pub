# 进程间通信：pipe / fifo / shm / futex / Binder

> 系列第 12 篇 · 阶段 D · 控制
>
> **承上**：10-11 篇讲完 cgroup + 信号——进程被约束 + 异步通知。本篇展开进程间**数据交换**：pipe / fifo / shm / futex / Binder。
>
> **启下**：阶段 D 全部结束——13 篇《进程调试与稳定性关联》收口（阶段 E）。
>
> **预计篇幅**：约 2.1 万字（Binder 是重点）
>
> **源码基线**：Linux 5.10 / 5.15（Android 12-14 主流内核）+ Android 14 GKI。

---

## 学习目标

读完本文，你应该能：

1. 在脑中画出 IPC 的全景图——管道 / 共享内存 / 消息队列 / 信号量 / socket / Binder 的对比。
2. 理解 pipe / fifo 的内核实现——pipe_inode_info + ring buffer。
3. 知道 mmap / shmem 共享内存怎么实现进程间共享。
4. 跟踪 futex 的内核实现——futex_wait / futex_wake 快速路径。
5. **理解 Binder 驱动架构**——binder_proc / binder_thread / binder_transaction。
6. 知道 Binder 线程池的工作机制。
7. 理解 Binder 的死亡通知（link_to_death）。
8. 知道 Binder 的性能优化——mmap / oneway / async。
9. 能在 Android 14 上用 `dumpsys binder_calls_stats` 看 binder 调用。
10. 知道 Binder 调用的稳定性排查方法。
11. 理解与 Framework 06 镜像分工——Kernel 层讲 Binder 驱动，Framework 层讲 Binder API。

---

## 一、IPC 是什么

### 1.1 IPC 的定位

**IPC** = **I**nter-**P**rocess **C**ommunication，进程间通信。

**本质**：让多个进程之间**交换数据**——区别于信号的"通知"。

**关键认知**：
- IPC 是"数据交换"——比信号复杂
- IPC 通常涉及**内核态**中转（除了共享内存）
- 性能差异巨大——共享内存最快，binder 中等，socket 较慢

### 1.2 IPC 的 6 大类

```
1. 管道（pipe / fifo）
   - 字节流，先进先出
   - 父子进程或命名管道
   - 用于 shell / 子进程通信

2. 共享内存（shm / mmap）
   - 多进程映射同一段物理内存
   - 最快（无内核中转）
   - 需要同步机制（futex / 信号量）

3. 消息队列（msg queue）
   - 消息（带类型）的链表
   - 较少用——POSIX 接口

4. 信号量（semaphore）
   - 计数器 + 等待队列
   - 用于同步
   - POSIX / System V

5. socket
   - 字节流 / 数据报
   - 同主机 / 跨主机
   - TCP / UDP / unix domain

6. Binder（Android 特有）
   - RPC + 引用计数
   - 内核驱动 + 用户态 stub
   - Android 14 主要 IPC
```

### 1.3 Android 14 上的 IPC 使用

```bash
# 1. 看进程使用的 IPC
# pipe / fifo：fork + exec 用
# shmem：system_server 跟 native service
# futex：所有 pthread 同步
# Binder：所有 framework / app 通信

# 2. 看进程间通信统计
adb shell "dumpsys binder_calls_stats | head -50"
```

**关键**：
- Android 14 上 99% 的 IPC 是 Binder
- futex 用于 pthread 内部同步
- pipe/fifo/shmem/socket 少量使用

### 1.4 性能对比

| IPC 方式 | 数据拷贝 | 适用场景 | 性能 |
|---|---|---|---|
| pipe | 2 次（user → kernel → user） | 父子进程 | 中 |
| shmem | 0 次（共享） | 大数据共享 | 最快 |
| socket | 2-4 次（取决于协议） | 跨主机 / 通用 | 较慢 |
| Binder | 1-2 次（mmap 优化） | Android RPC | 中快 |

**关键**：
- 共享内存最快——但需要同步
- Binder 在 Android 上优化得不错
- socket 较慢——但通用

---

## 二、pipe / fifo 内核实现

### 2.1 pipe 是什么

```c
// 创建匿名 pipe
int pipe(int pipefd[2]);
// pipefd[0] = 读端
// pipefd[1] = 写端

// 创建命名 pipe（fifo）
mkfifo("/tmp/mypipe", 0666);
int fd = open("/tmp/mypipe", O_RDONLY);  // 或 O_WRONLY
```

**关键**：
- 匿名 pipe：父子进程用
- 命名 pipe（fifo）：任意进程
- 都是字节流

### 2.2 pipe 的内核数据结构

```c
// include/linux/pipe_fs_i.h
struct pipe_inode_info {
    struct mutex mutex;             // 保护 pipe
    wait_queue_head_t rd_waiters;   // 读等待队列
    wait_queue_head_t wr_waiters;   // 写等待队列
    unsigned int nrbufs;            // 当前 buffer 数
    unsigned int curbuf;            // 当前读位置
    unsigned int max_usage;         // 最大使用量
    unsigned int ring_size;         // ring buffer 大小
    unsigned int nr_accounted;      // 已计入的 pages
    unsigned int readers;           // 读端数量
    unsigned int writers;           // 写端数量
    unsigned int files;             // 打开的文件数
    unsigned int r_counter;         // 读计数（poll 用）
    unsigned int w_counter;         // 写计数

    struct page *tmp_page;          // 用于 partial writes
    struct fasync_struct *fasync_readers;
    struct fasync_struct *fasync_writers;
    // ...
    struct pipe_buffer *bufs;        // ring buffer
    struct user_struct *user;
    // ...
};

struct pipe_buffer {
    struct page *page;
    unsigned int offset;
    unsigned int len;
    const struct pipe_buf_operations *ops;
    unsigned int flags;
    unsigned long private;
};
```

**关键认知**：
- `pipe_inode_info` 是 pipe 的核心结构
- `bufs` 是 ring buffer——pipe_buffer 数组
- `rd_waiters` / `wr_waiters`：读 / 写等待队列

### 2.3 pipe 的读写路径

```c
// fs/pipe.c pipe_read
static ssize_t pipe_read(struct kiocb *iocb, struct iov_iter *to)
{
    // 1. 拿 mutex
    mutex_lock(&pipe->mutex);

    // 2. 等数据（如果空）
    while (!pipe->nrbufs) {
        // 没有写端——EOF
        if (!pipe->writers) {
            // 返回 0
            mutex_unlock(&pipe->mutex);
            return 0;
        }
        // 等写端
        // ...
    }

    // 3. 从 ring buffer 读
    pipe_buf_operations->confirm(pipe, buf);
    if (copy_page_to_iter(buf->page, buf->offset, chars, to) != chars) {
        // 错误
    }

    // 4. 唤醒写端
    wake_up_interruptible(&pipe->wr_waiters);

    mutex_unlock(&pipe->mutex);
    return chars;
}
```

**关键**：
- pipe_read 从 ring buffer 读——FIFO
- 没有数据时 sleep（block）/ 返回 0（EOF）
- 写端关闭时返回 0——read() 返回 0 是 EOF

### 2.4 pipe 的写路径

```c
// fs/pipe.c pipe_write
static ssize_t pipe_write(struct kiocb *iocb, struct iov_iter *from)
{
    // 1. 拿 mutex
    mutex_lock(&pipe->mutex);

    // 2. 没有读端——SIGPIPE
    if (!pipe->readers) {
        send_sig(SIGPIPE, current, 0);
        return -EPIPE;
    }

    // 3. 等空间（如果满）
    while (pipe->nrbufs >= pipe->max_usage) {
        // 满——sleep
        // ...
    }

    // 4. 写到 ring buffer
    copy_from_iter_full(...);

    // 5. 唤醒读端
    wake_up_interruptible(&pipe->rd_waiters);

    mutex_unlock(&pipe->mutex);
    return chars;
}
```

**关键**：
- pipe_write 没读端时返回 SIGPIPE
- Android 14 上默认忽略 SIGPIPE——返回 EPIPE
- 写满时 block / 返回 EAGAIN（O_NONBLOCK）

### 2.5 pipe 的 Android 14 使用

```c
// Android 14 上 pipe 主要用于：
// 1. fork 后 exec 的父子进程
// 2. logcat 管道
// 3. shell 命令管道
// 4. dumpsys 的进程间通信

// 例子：dumpsys meminfo
// logd → pipe → dumpsys → 读取
```

**关键**：
- Android 14 上 pipe 大量用于系统工具
- Binder 是 app / framework 的主要 IPC
- pipe 是"基础设施"——shell / 工具

---

## 三、mmap / shmem 共享内存

### 3.1 mmap 是什么

```c
// mmap 把文件 / 设备 / 匿名映射到进程虚拟地址空间
void *mmap(void *addr, size_t length, int prot, int flags,
            int fd, off_t offset);
```

**关键**：
- mmap 是"虚拟地址映射"
- 多进程 mmap 同一文件 / 同一 shmem fd → 共享内存
- 是最高效的 IPC 方式

### 3.2 shmem / tmpfs

```bash
# 1. tmpfs 挂载
adb shell "df -h | grep tmpfs"

# 2. /dev/shm（Linux）
adb shell "ls /dev/shm/"

# 3. Android 14 上 /dev/shm 可能在 init.rc 中挂载
```

**关键**：
- shmem 是 tmpfs 的一种——基于内存的文件系统
- 多进程 mmap 同一 shmem 文件 → 共享内存

### 3.3 mmap 共享内存的实现

```c
// mm/mmap.c do_mmap
// 创建 VMA，关联到 file

// 多进程 mmap 同一 file 时：
// - 共享 inode
// - 共享 page cache
// - 多进程的 VMA 指向同一物理页

// 写时复制（COW）：
// - 默认 fork 时父子进程共享 page cache
// - 写时复制——保证独立性
```

**关键**：
- mmap 同一 file → 共享 page cache
- COW：写时复制——避免每次 mmap 都分配
- 进程间共享：要么匿名 mmap + CLONE_VM（vfork 风格），要么同一 file

### 3.4 shmem_get_inode

```c
// mm/shmem.c shmem_get_inode
// 创建 shmem inode

struct inode *shmem_get_inode(struct super_block *sb, const struct inode *dir,
                              umode_t mode, dev_t dev, unsigned long flags)
{
    struct inode *inode = new_inode(sb);
    // 初始化 inode
    // ...
}
```

**关键**：
- shmem inode 是内存中的文件
- shmem_file_operations 定义操作
- shmem_vm_ops 定义 mmap 操作

### 3.5 Android 14 上 mmap / shmem 的使用

```c
// 1. SystemUI 用 mmap 共享内存
// 2. SurfaceFlinger 用 mmap 共享 buffer
// 3. Camera 用 mmap 共享 image buffer
// 4. Hardware composer 用 mmap

// Binder 也用 mmap——见 §10
```

**关键**：
- Android 14 上大量 native 服务用 mmap
- binder 用 mmap 减少数据拷贝
- 这是 Android 性能的关键

### 3.6 mmap 共享内存的稳定性

```bash
# 1. 看进程的 mmap 列表
adb shell "cat /proc/<pid>/maps | head -20"

# 输出例子：
# address          perms offset  dev   inode   pathname
# 7f9a8b0000-7f9a8c0000 r--p 00000000 fd:05 1234  /system/bin/linker64
# 7f9a8c0000-7f9b000000 r-xp 00000000 fd:05 1234  /system/bin/linker64
# 7f9b000000-7f9b040000 r--p 00000000 fd:05 5678  /system/lib64/libc.so

# 2. 看 mmap 的具体共享
adb shell "cat /proc/<pid>/maps | grep '/dev/ashmem\|/system/lib64'"
```

**关键**：
- `r--p`：read-only private（代码段）
- `r--s`：read-only shared（共享库）
- `rw-p`：read-write private（堆）
- `rw-s`：read-write shared（共享内存）

---

## 四、futex 内核实现

### 4.1 futex 是什么

**futex** = **F**ast Use**r**space mu**tex**

**核心思想**：
- 无竞争时纯用户态——零 syscall
- 有竞争时走内核——sys_futex

**关键认知**：
- pthread_mutex 内部用 futex
- 所有 pthread 同步原语（mutex / cond / rwlock）用 futex
- futex 是 Linux 上最快的同步原语

### 4.2 futex 的使用

```c
// glibc / Bionic pthread_mutex
// pthread_mutex_lock
//   1. 尝试 CAS（用户态）
//   2. 失败 → syscall FUTEX_WAIT
// pthread_mutex_unlock
//   1. 释放锁
//   2. 如果有 waiter → syscall FUTEX_WAKE
```

**关键**：
- pthread_mutex 无竞争时零 syscall
- 性能比 system V semaphore / POSIX mutex 好得多

### 4.3 futex 的内核实现

```c
// kernel/futex.c
// 关键数据结构
struct futex_q {
    struct plist_node list;     // 等待队列链表
    struct task_struct *task;   // 等待的 task
    spinlock_t *lock_ptr;      // 锁指针
    u32 key;                    // futex key
    // ...
};

// futex_wait
static int futex_wait(u32 __user *uaddr, unsigned int flags,
                       u32 bitset, u64 abs_time)
{
    // 1. 拿到 futex key（基于 uaddr）
    // 2. 检查值是否还是 expected
    // 3. 加入等待队列
    // 4. schedule() 让出 CPU
    // 5. 被唤醒时检查是否真的该醒来
    return futex_wait_queue_me(...);
}

// futex_wake
static int futex_wake(u32 __user *uaddr, unsigned int flags,
                       u32 bitset, int nr_wake)
{
    // 1. 拿到 futex key
    // 2. 在等待队列里找匹配 key 的 waiter
    // 3. 唤醒最多 nr_wake 个
    // 4. 返回唤醒数量
    return futex_wake_mark(...);
}
```

**关键**：
- futex_wait：sleep 在等待队列
- futex_wake：唤醒等待者
- 都基于 uaddr 计算 key

### 4.4 futex key 的计算

```c
// kernel/futex.c get_futex_key
// 根据 uaddr 计算 key

// 1. 匿名 page（heap）
//    key = page->index + offset_in_page

// 2. 文件-backed（mmap 共享）
//    key = (inode, offset)

// 3. shmem（tmpfs）
//    类似文件-backed

// 多线程同一进程的 mutex：
//    同一 anon page → 同一 key

// 多进程共享内存 mutex：
//    同一 mmap 区域 → 同一 key
```

**关键**：
- 不同进程的 futex 通过 key 识别
- 共享内存的 futex 在多进程可用

### 4.5 PI-futex（Priority Inheritance futex）

```c
// kernel/futex.c futex_lock_pi
// 带优先级继承的 futex——08 篇讲过

// kernel/rtmutex.c rt_mutex_slowlock
// 实现 PI 协议

// 当 task A 等 task B 的 PI-futex：
// 1. 临时提升 B 的优先级到 A
// 2. B 释放 futex 后恢复原优先级
```

**关键**：
- PI-futex 解决优先级反转（08 篇 §7.4）
- Android 14 ART 内部大量用
- pthread_mutex 的 PTHREAD_PRIO_INHERIT 走这个

### 4.6 futex 在 Android 14 上的使用

```bash
# 1. 看 futex 等待
adb shell "cat /proc/<pid>/status | grep voluntary_ctxt_switches"
# 高 voluntary switches = 多 futex 等待

# 2. perfetto 看 futex
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'futex:futex_wait_start futex:futex_wait_end futex:futex_wake' --time 30"
```

**关键**：
- Android 14 上所有 pthread 同步都用 futex
- ART / framework / native 库都依赖
- futex 性能是 Android 性能的关键

---

## 五、其他 IPC 简介

### 5.1 消息队列（msg queue）

```c
// POSIX mq_open / mq_send / mq_receive
// System V msgget / msgsnd / msgrcv

// Android 14 上几乎不用
// system V 还需要 mount mqueue（CONFIG_SYSVIPC）
```

**关键**：
- Android 14 上消息队列用得很少
- 大多数场景用 binder
- 略过

### 5.2 信号量（semaphore）

```c
// POSIX sem_init / sem_wait / sem_post
// System V semget / semop

// Android 14 上 System V 通常禁用
// POSIX sem 用 futex 实现——与 futex 等价
```

**关键**：
- Android 14 上信号量很少用
- 通常用 pthread_mutex + cond
- 略过

### 5.3 unix domain socket

```c
// 创建
int fd = socket(AF_UNIX, SOCK_STREAM, 0);
// bind to path
bind(fd, (struct sockaddr*)&addr, sizeof(addr));
// listen / accept / connect / send / recv

// Android 14 上：
// 1. logd 跟 logcat 通信
// 2. zygote 跟 system_server
// 3. SurfaceFlinger 跟 HWComposer
```

**关键**：
- unix domain socket 是同主机 socket——不走网络协议
- 比 TCP 快很多
- Android 14 上部分 native 服务用

### 5.4 TCP / UDP socket

```c
// TCP：面向连接，可靠
// UDP：无连接，可能丢失

// Android 14 上：
// 1. Network stack 用
// 2. App 间网络通信
// 3. Debug 工具（adb 走 TCP）
```

**关键**：
- TCP/UDP 走网络协议——开销较大
- Android 上主要是网络层
- 本地 IPC 不用这个

---

## 六、Binder 驱动架构

### 6.1 Binder 是什么

**Binder** = Android 的核心 IPC 机制（基于内核驱动）。

**核心组件**：
- **Binder 驱动**（kernel/drivers/android/binder.c）——内核态
- **Binder 库**（libbinder / libutils）——用户态 stub
- **ServiceManager**——服务注册中心
- **AIDL / HIDL**——接口定义语言

**关键认知**：
- Binder 是 Android 14 上 99% 跨进程通信的基础
- 所有 framework / app / system_server 通信走 Binder
- 由内核驱动 + 用户态 stub 实现

### 6.2 Binder 的核心数据结构

```c
// drivers/android/binder.c

// 1. binder_proc：每个使用 binder 的进程一个
struct binder_proc {
    struct hlist_node proc_node;     // 链表
    struct rb_root threads;          // binder_thread 红黑树
    struct rb_root nodes;            // binder_node 红黑树（服务节点）
    struct rb_root refs_by_desc;     // binder_ref 按 desc
    struct rb_root refs_by_node;     // binder_ref 按 node

    int pid;                         // 进程 PID
    struct vm_area_struct *vma;      // mmap 的 VMA
    struct mm_struct *vma_vm_mm;
    struct task_struct *tsk;         // task_struct

    // 2. 分配 / 释放的 binder object
    struct list_head todo;           // 待办事务（transaction）
    wait_queue_head_t wait;          // binder 等待队列
    struct binder_stats stats;       // 统计

    // 3. mmap 的 buffer（关键！）
    void *buffer;                    // 内核映射用户空间
    void *user_buffer_offset;        // 用户态地址偏移

    // ...
};

// 2. binder_thread：每个 binder 线程一个
struct binder_thread {
    struct binder_proc *proc;
    struct rb_node rb_node;          // 在 proc->threads 红黑树
    int pid;                         // task PID
    int looper;                      // 状态
    struct binder_transaction *transaction_stack;
    struct list_head todo;           // 待办
    struct binder_error return_error;
    wait_queue_head_t wait;          // binder 线程等待
    // ...
};

// 3. binder_node：服务节点
struct binder_node {
    int debug_id;
    struct binder_work work;
    union {
        struct rb_node rb_node;       // proc->nodes 红黑树
        struct hlist_node dead_node;
    };
    struct binder_proc *proc;        // 所属进程
    // ...
};

// 4. binder_ref：远程引用
struct binder_ref {
    struct rb_node rb_node_desc;     // 按 desc 索引
    struct rb_node rb_node_node;     // 按 node 索引
    struct hlist_node node_entry;
    struct binder_proc *proc;        // 持有引用的进程
    struct binder_node *node;        // 指向的服务节点
    // ...
};
```

**关键认知**：
- `binder_proc`：每个进程一个——管理本进程的所有 binder 资源
- `binder_thread`：每个 binder 线程一个——执行 binder 事务
- `binder_node`：服务节点——服务端注册的服务
- `binder_ref`：客户端引用——指向远程 binder_node

### 6.3 Binder 的"两方"视角

```
客户端进程（caller）：
  - 有 binder_ref（指向远程 binder_node）
  - 通过 handle 访问（handle 是 binder_ref 的描述符）
  - binder 调用 = "把事务发给 handle"

服务端进程（callee）：
  - 有 binder_node（服务节点）
  - 接收 transaction
  - 在 binder_thread 中处理

ServiceManager：
  - 注册中心
  - "字符串 name" → handle 的映射
```

**关键认知**：
- 客户端用 handle（数字描述符）访问服务
- ServiceManager 把 name 转 handle
- 服务端有 binder_node——实现服务

### 6.4 Binder 通信的完整路径

```
client 进程                    service 进程
─────────                      ──────────
1. app 调 ServiceProxy.foo()
2. JNI 调 IBinder::transact()
3. libbinder 构造 Parcel
4. ioctl(BINDER_WRITE_READ, ...)
                                ↓
                              [内核 Binder 驱动]
                                5. binder_transaction() 接收
                                6. 把事务放到 service->todo
                                7. wake_up service 的 binder_thread
                                8. service 进程调度到
                                9. binder_thread 从 todo 读
                                10. 调 service 的 onTransact()
                                11. service 执行 foo()
                                12. 构造 reply Parcel
                                13. ioctl(BINDER_WRITE_READ, ...)
                                ↓
14. client 的 binder_thread 醒来
15. 解析 reply Parcel
16. libbinder 返回结果给 Java
```

**关键**：
- Binder 通信是同步的（默认）——调用方阻塞等结果
- 但也可以 oneway——不阻塞、不等结果
- 跨进程要走两次内核——但用 mmap 优化

### 6.5 Binder 的性能优化

```c
// 1. mmap 共享 buffer
//    client 和 service 共享一段内核 mmap 区域
//    减少 user ↔ kernel 拷贝

// 2. oneway 调用
//    不需要 reply——不阻塞
//    service 处理完直接结束

// 3. async transaction
//    非阻塞事务
//    适合高频小数据

// 4. RT 优先级
//    binder_thread 可以跑在 RT 优先级
//    保证响应时间
```

**关键**：
- Binder 用 mmap 减少拷贝——比 socket 快
- oneway / async 减少阻塞
- Android 14 上 binder 是优化得很好的 IPC

### 6.6 Binder 与其他 IPC 对比

```
vs pipe：
  - pipe 是字节流——无结构
  - Binder 是 RPC——有接口
  - Binder 支持同步 + oneway

vs socket：
  - socket 是网络协议——开销大
  - Binder 是内核驱动——开销小
  - Binder 支持引用计数（死亡通知）

vs shmem：
  - shmem 最快——但需要同步
  - Binder 不如 shmem 快——但更安全（内核中转）
  - Binder 是同步的——shmem 需要自己同步
```

**关键认知**：
- Binder 在"易用性 + 性能"之间平衡
- 不如 shmem 快——但更安全（内核中转 + 权限检查）
- Android 上首选 Binder

---

## 七、Binder 驱动：核心 ops

### 7.1 Binder 设备节点

```bash
# Android 14 上 Binder 设备
adb shell "ls -l /dev/binder*"
# crw------- 1 root root 10, 47  binder
# crw------- 1 root root 10, 48  binderfs
# crw------- 1 root root 10, 52  hwbinder
# crw------- 1 root root 10, 53  vndbinder
```

**关键**：
- `/dev/binder`：主 Binder——framework / app
- `/dev/hwbinder`：HAL Binder——HAL 服务
- `/dev/vndbinder`：Vendor Binder——vendor HAL
- 不同 Binder 隔离——vendor 不会破坏 framework

### 7.2 ioctl 入口

```c
// drivers/android/binder.c binder_ioctl
static long binder_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
    // 1. 拿 proc
    struct binder_proc *proc = filp->private_data;

    switch (cmd) {
    case BINDER_WRITE_READ:
        // 收发 binder 事务
        return binder_ioctl_write_read(filp, cmd, arg, ...);

    case BINDER_SET_MAX_THREADS:
        // 设置最大 binder thread 数
        // ...

    case BINDER_SET_CONTEXT_MGR:
        // 注册为 ServiceManager
        // ...

    case BINDER_THREAD_EXIT:
        // binder 线程退出
        // ...

    case BINDER_VERSION:
        // ...
    }
}
```

**关键**：
- 用户态通过 ioctl 跟 Binder 驱动通信
- BINDER_WRITE_READ 是最常用——发 / 收事务
- 其他 cmd 用于设置 / 注册

### 7.3 BINDER_WRITE_READ 的实现

```c
// drivers/android/binder.c binder_ioctl_write_read
static int binder_ioctl_write_read(struct file *filp,
                                    unsigned int cmd, unsigned long arg,
                                    struct binder_thread *thread)
{
    // 1. 从用户态读 write buffer（要发的）
    if (bwr.write_size > 0) {
        ret = binder_thread_write(proc, thread,
                                    bwr.write_buffer,
                                    bwr.write_size,
                                    &bwr.write_consumed);
    }

    // 2. 从内核态读 read buffer（要收的）
    if (bwr.read_size > 0) {
        ret = binder_thread_read(proc, thread,
                                  bwr.read_buffer,
                                  bwr.read_size,
                                  &bwr.read_consumed,
                                  filp->f_flags & O_NONBLOCK);
    }

    // 3. 回写结果
    if (copy_to_user(ubuf, &bwr, sizeof(bwr)))
        return -EFAULT;

    return 0;
}
```

**关键认知**：
- 一次 ioctl 既发又收——简化用户态逻辑
- write buffer：要发的事务
- read buffer：要收的事务

### 7.4 binder_transaction 路径

```c
// drivers/android/binder.c binder_transaction
static int binder_transaction(struct binder_proc *proc,
                               struct binder_thread *thread,
                               struct binder_transaction_data *tr,
                               int reply)
{
    // 1. 解析 transaction data
    // 2. 找目标 thread / proc
    // 3. 拷贝 data 到目标 proc 的 buffer（mmap 共享）
    // 4. 把 transaction 加入目标 todo
    // 5. wake_up 目标 thread
}
```

**关键**：
- 客户端发起：binder_thread_write → binder_transaction
- 数据拷贝到 service 进程的 mmap buffer
- 唤醒 service 的 binder_thread

### 7.5 binder_thread_read 路径

```c
// drivers/android/binder.c binder_thread_read
static int binder_thread_read(struct binder_proc *proc,
                               struct binder_thread *thread,
                               void __user *buffer, int size,
                               int *consumed, int non_block)
{
    // 1. 等事务
    while (1) {
        // 1.1 检查 todo list
        if (!list_empty(&thread->todo))
            break;

        // 1.2 等新事务
        // ...

        // 1.3 处理 BR_* 命令
    }

    // 2. 把事务写到 read buffer（用户态）
    // 3. 解析 transaction data
    // 4. 返回给用户态
}
```

**关键认知**：
- binder_thread 阻塞在 binder_thread_read
- 有事务时醒来——返回给用户态
- 用户态处理后再次 ioctl——形成循环

---

## 八、Binder 线程池

### 8.1 binder thread 的创建

```c
// 用户态：libbinder 在没有空闲 binder thread 时创建
// 1. pthread_create
// 2. 新线程进入 IPCThreadState::joinThreadPool
// 3. 循环 ioctl(BINDER_WRITE_READ, ...)
// 4. 内核看到 BINDER_THREAD_ENTRY 创建 binder_thread
```

**关键**：
- binder thread 由用户态创建——内核不知道
- 内核通过 BINDER_THREAD_ENTRY 创建 binder_thread
- 线程池大小可配置

### 8.2 binder thread pool 大小

```bash
# 1. 看进程的 binder thread pool
adb shell "ls /proc/<pid>/task | wc -l"  # 总线程数
adb shell "cat /proc/<pid>/task/*/status | grep State"  # 状态

# 2. Android 14 上：
# system_server 默认 31 个 binder thread
# zygote 默认 1 个
# 应用默认 1-4 个

# 3. 设置：
# frameworks/base/services/core/java/com/android/server/am/ProcessList.java
# MAX_BINDER_THREADS = 31
```

**关键**：
- system_server 有 31 个 binder thread——处理所有 binder 调用
- 应用少 binder thread——主要调出去的
- framework 层管理 thread pool

### 8.3 binder 线程池的扩展

```c
// 用户态扩展 thread pool
// libbinder IPCThreadState.cpp

void IPCThreadState::joinThreadPool(bool isMain)
{
    // 1. 设置 max threads
    setMaxThreads(sMaxBinderThreads);

    // 2. 主线程：注册到 ServiceManager
    if (isMain) {
        // ...
    }

    // 3. 循环处理
    while (1) {
        // 3.1 等事务
        // 3.2 处理事务
        // 3.3 必要时退出
    }
}
```

**关键**：
- libbinder 自动扩展 thread pool
- 高并发时自动创建新线程
- 空闲时销毁多余线程

### 8.4 binder 线程的状态

```c
// drivers/android/binder.c
enum {
    BINDER_LOOPER_STATE_REGISTERED,  // 已注册
    BINDER_LOOPER_STATE_ENTERED,     // 已 enter
    BINDER_LOOPER_STATE_EXITED,      // 已 exit
    BINDER_LOOPER_STATE_INVALID,     // 无效
};
```

**关键**：
- 线程状态机：注册 → enter → exit → invalid
- 用户态通过 BC_ENTER_LOOPER 等 cmd 控制

---

## 九、Binder 死亡通知

### 9.1 linkToDeath 是什么

```java
// frameworks/base/core/java/android/os/IBinder.java
public interface IBinder {
    public interface DeathRecipient {
        void binderDied();
    }

    public void linkToDeath(DeathRecipient recipient, int flags);
    public boolean unlinkToDeath(DeathRecipient recipient, int flags);
}
```

**关键**：
- 客户端通过 `linkToDeath` 注册死亡回调
- 服务端进程死亡时——客户端收到通知
- Binder 驱动实现——不需要 service 进程参与

### 9.2 死亡通知的内核实现

```c
// drivers/android/binder.c binder_send_failed_reply
// 当目标进程死亡时

// 1. 标记死亡的 proc
// proc->is_dead = 1

// 2. 遍历 proc->refs——所有引用这个 proc 的 ref
// 3. 给每个 ref 触发死亡通知
// 4. 唤醒等待死亡通知的线程

// 用户态：binder_thread 收到 BR_DEAD_BINDER
// libbinder 调 linkToDeath 注册的 DeathRecipient
```

**关键**：
- 死亡通知是内核主动触发的
- 不需要 service 进程活着
- 即使 service 进程崩溃，客户端也会收到通知

### 9.3 死亡通知在 Android 14 上的应用

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java
// 注册 binder 死亡回调
app.thread.asBinder().linkToDeath(app, 0);

// 当 app 进程死时，ActivityManagerService 收到通知
// → 清理 app 相关资源
```

**关键**：
- ActivityManagerService 注册所有 app 的死亡通知
- 进程死时立即清理资源
- 这是 Android 14 稳定性的关键

### 9.4 死亡通知 vs 信号

| 维度 | 死亡通知 | 信号 |
|---|---|---|
| 发起方 | 内核（进程死时） | 用户态 / 内核 |
| 接收方 | 引用了死亡进程的客户端 | 任何进程 |
| 触发条件 | 进程死 | 进程死 / 主动发 |
| 数据 | 无 | 可携带 data |
| 排队 | 是 | 标准信号不排队 |

**关键**：
- 死亡通知是"特定的信号"——只通知死亡事件
- 适合"我持有的服务死了，我该清理"
- 信号适合通用场景

---

## 十、Binder 性能优化

### 10.1 mmap 优化

```c
// drivers/android/binder.c binder_mmap
// 用户态 mmap binder 设备时调

static int binder_mmap(struct file *filp, struct vm_area_struct *vma)
{
    // 1. 分配物理页
    // 2. 把物理页映射到内核 + 用户空间
    // 3. 这样客户端 / 服务端共享这段 buffer

    // 关键：binder mmap 是 rw-（不是 COW）
    // 客户端写→ 服务端读到（共享）
    // 服务端写→ 客户端读到（共享）

    // 节省：原本需要 user → kernel → user 两次拷贝
    //       现在是 user → user（直接读 mmap buffer）
}
```

**关键**：
- Binder mmap 是**真正共享**——两端映射同一物理页
- 数据拷贝只需要 1 次（写入端写、读取端读 mmap buffer）
- 这是 Binder 比 socket 快的原因

### 10.2 oneway 调用

```java
// AIDL oneway 关键字
oneway void onNewEvent(Event e);
```

**关键**：
- `oneway` 调用不阻塞——客户端不等结果
- 服务端处理完直接结束
- 适合"通知类"调用——onNewEvent、状态变化

### 10.3 async transaction

```c
// drivers/android/binder.c
// TF_ONE_WAY 标志——async
if (tr->flags & TF_ONE_WAY) {
    // 不等 reply——直接返回
}
```

**关键**：
- TF_ONE_WAY 是异步——内核不阻塞客户端
- 适合"频繁调用 + 不需要结果"

### 10.4 Binder 与 cgroup

```bash
# binder 调用受 cgroup 限制
# - CPU 被 top-app / background slice 限制
# - memory 受 cgroup memory.max 限制
# - system_server 在 system.slice

# binder 调用慢通常跟 cgroup 限制有关
# 不是 binder 本身的问题
```

**关键**：
- binder 性能也受 cgroup 影响
- top-app 在大核跑——binder 快
- background 在小核跑——binder 慢

### 10.5 Binder 的 sched_setattr 优化

```c
// libbinder / libutils
// Binder 线程可以设 RT 优先级

// frameworks/native/libs/binder/IPCThreadState.cpp
int IPCThreadState::setupPolling(int* fd)
{
    // 设置 binder thread 的优先级
    // 通常是 RT priority 50-70
}
```

**关键**：
- Binder thread 是 RT——保证响应
- framework 内部有 priority 配置
- Android 14 默认优化

---

## 十一、Binder 在 Android 14 上的实测

### 11.1 binder 调用统计

```bash
# 1. 看 binder 调用统计
adb shell "dumpsys binder_calls_stats | head -50"

# 输出例子：
# Binder call stats for system_server:
#   PIDs: 1234 5678 9012
#   Top slow calls (last 5s):
#     call to ActivityManager.getTasks: avg 1234μs max 5678μs
#     call to InputManager.injectInput: avg 234μs max 1234μs

# 2. 看具体 binder 调用
adb shell "dumpsys binder_calls_stats --all 2>/dev/null | head -100"

# 3. 按包名看 binder
adb shell "dumpsys binder --all 2>/dev/null | grep -A 20 'com.example.app'"
```

**关键**：
- `dumpsys binder_calls_stats` 是 binder 性能的关键工具
- "Top slow calls" 看哪些 binder 调用慢
- "max" 字段看最坏情况

### 11.2 binder transaction 的 perfetto 追踪

```bash
# 抓 binder 事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'binder:transaction binder:transaction_received binder:transaction_alloc_buf' --time 30"
```

**关键事件**：
- `binder:transaction`：客户端发起
- `binder:transaction_received`：服务端收到
- `binder:transaction_alloc_buf`：分配 buffer

### 11.3 Binder 调用的延迟分解

```
总延迟 = 客户端延迟 + 内核延迟 + 服务端延迟
        = T1 + T2 + T3

T1 (客户端)：
  - ioctl 进入内核
  - binder_transaction 处理
  - 把事务放到 service->todo
  - 客户端 wake_up

T2 (内核)：
  - 数据拷贝到 mmap buffer
  - 唤醒 service binder thread
  - 处理 transaction data

T3 (服务端)：
  - binder_thread 从 ioctl 醒来
  - 解析 transaction
  - 调 onTransact
  - 执行服务逻辑
  - 构造 reply
  - ioctl 返回 reply

perfetto 可以分别追踪：
  - T1 看 client 进程的 binder 事件
  - T2 看内核 binder:transaction_alloc_buf
  - T3 看 service 进程的 binder 事件
```

**关键**：
- 用 perfetto 能分段看延迟
- 这是 binder 性能优化的入口

### 11.4 binder 调用延迟基准

| 场景 | 典型延迟 |
|---|---|
| 简单 IPC（同进程） | < 100μs |
| 简单 IPC（跨进程） | 200-1000μs |
| 复杂 IPC（带大 Parcel） | 1-10ms |
| binder 调用超过 10ms | 通常是问题 |
| 系统 binder 拥塞 | > 50ms（需排查） |

**关键**：
- binder 调用慢通常不是 binder 本身
- 可能是 service 实现慢
- 或 system_server 拥塞
- 或 cgroup 限制

---

## 十二、Binder 调用的稳定性场景

### 12.1 system_server binder 拥塞

```bash
# 症状：所有 app 调用 binder 都慢

# 排查：
# 1. 看 system_server 的 binder thread pool
adb shell "ls /proc/$(pidof system_server)/task | wc -l"
# 输出: 142（主线程 + binder thread）

# 2. 看 binder thread 状态
adb shell "cat /proc/$(pidof system_server)/task/*/status | grep State"
# 看是否有 R 状态的 binder thread

# 3. 看 system_server 的 CPU
adb shell "top -p $(pidof system_server) -n 1"
# 看 system_server 是否 CPU 满

# 解决：
# - 排查某个 app 频繁调用 binder
# - 排查 system_server 内部卡顿
```

**关键**：
- system_server binder 拥塞影响所有 app
- 排查方向：哪个 thread 慢？哪个 app 频繁调？

### 12.2 binder 死锁

```bash
# 症状：binder 调用 hang 住

# 排查：
# 1. 看 binder transaction 栈
adb shell "cat /proc/<binder_thread_id>/stack"

# 2. 看 system_server 状态
adb shell "dumpsys binder --all 2>/dev/null | head"

# 解决：
# - 死锁检查
# - 重启 system_server（不推荐，但最有效）
```

**关键**：
- binder 死锁是经典问题——A 等 B，B 等 A
- framework 层应有死锁检测
- system_server 重启会清空所有 binder——影响 app

### 12.3 应用进程 binder 异常

```bash
# 症状：app 收不到 binder reply

# 排查：
# 1. 看 app 进程是否还活着
adb shell "ps -A | grep <app_pkg>"

# 2. 看 system_server 是否有 app 的引用
adb shell "dumpsys binder --all 2>/dev/null | grep -A 5 'app_pkg'"

# 3. 看 binder transaction 是否丢
adb shell "dumpsys binder_calls_stats | grep <app_pkg>"
```

**关键**：
- binder reply 丢失通常意味着进程死了
- linkToDeath 通知会触发

### 12.4 Binder buffer 耗尽

```bash
# 症状：binder transaction 失败
# Error: "binder: 1234:4567 transaction failed 29189/-3, size 48-0 line 2563"

# 排查：
# - 进程 binder buffer 用完
# - 默认 1MB per-process
# - 需要重用 buffer

# 解决：
# - 减少 binder Parcel 大小
# - 拆分大 Parcel
# - 增加 binder thread（释放 buffer）
```

**关键**：
- 每个进程 binder buffer 默认 1MB
- 大 transaction 容易耗尽
- 通过 BC_FREE_BUFFER 释放

### 12.5 binder thread pool 耗尽

```bash
# 症状：binder transaction 排队

# 排查：
# 1. 看 binder thread 是否忙
adb shell "ls /proc/$(pidof system_server)/task | wc -l"
# system_server 默认 31 个 binder thread

# 2. 看 binder transaction 数量
adb shell "dumpsys binder --all 2>/dev/null | grep transaction"

# 解决：
# - 增加 MAX_BINDER_THREADS
# - 减少 service 调用时间
```

**关键**：
- binder thread pool 耗尽 = 所有 binder 调用排队
- 解决方向：增加线程 or 优化 service

---

## 十三、Binder 与其他子系统的联动

### 13.1 Binder 与 cgroup

```bash
# 1. binder 受 cgroup cpu 限制
# top-app 在大核跑——binder 快
# background 在小核跑——binder 慢

# 2. binder thread pool 受 cgroup 内存限制
# 进程内存不足——binder buffer 无法分配
```

**关键**：
- binder 性能跟 cgroup 紧密关联
- top-app 调用 binder 通常快
- background 调用 binder 可能慢

### 13.2 Binder 与调度

```bash
# 1. binder thread 用 RT 优先级
adb shell "chrt -p $(pidof system_server)"
# binder thread 可能在 RT

# 2. binder 拥塞时调度延迟增加
# perfetto 看 binder 事件的延迟
```

**关键**：
- binder thread 可以 RT——保证响应
- 但 binder 拥塞时仍可能慢

### 13.3 Binder 与信号

```c
// SIGCHLD 通知 Zygote 应用退出
// binder 内部也用 SIGCHLD 检测客户端死亡
// libbinder IPCThreadState 监听 SIGCHLD
```

**关键**：
- Binder + 信号 + Zygote 联动
- 死亡通知是这套机制的核心

---

## 十四、Android 14 上 IPC 的实际选择

### 14.1 选 IPC 的决策树

```
需求是什么？
  ├─ 大数据共享 → mmap / shmem
  ├─ 父子进程 → pipe / socket
  ├─ 同进程同步 → futex
  ├─ 跨进程同步 → futex (PI) / 共享内存
  ├─ 跨进程通知 → 信号
  └─ 跨进程 RPC → Binder
```

**关键**：
- Android 14 上 Binder 是默认 IPC
- 不用 Binder 的话用 socket
- 性能敏感场景用 mmap + futex

### 14.2 framework 层 vs native 层的选择

```
framework 层（Java）：
  - 几乎全用 Binder（AIDL）
  - 例：ActivityManager / WindowManager / PackageManager

native 层（C++）：
  - HAL 用 hwbinder / vndbinder
  - 服务间用 unix socket（logd 等）
  - 性能敏感用 socketpair（fork 时）

Java ↔ C++：
  - libbinder / libutils
  - 通过 JNI 桥接
```

**关键**：
- framework 用 Binder 是常态
- native 层根据场景选
- 大数据传输考虑 mmap

### 14.3 binder 调用的 4 种模式

```
1. 同步调用（默认）
   client 调 service.foo() → 阻塞等 reply

2. oneway 调用
   client 调 service.foo() → 不阻塞

3. async 调用
   libbinder 内部排队——避免阻塞 caller

4. death notification
   client 注册——service 死时收到通知
```

**关键**：
- 默认同步——最简单
- oneway——通知类场景
- async——避免阻塞
- death notification——客户端感知服务死亡

---

## 十五、与 Framework 06 的镜像分工

### 15.1 Kernel 层（本篇）讲什么

```
本篇讲：
  - Binder 驱动的内核实现（binder.c）
  - binder_proc / binder_thread / binder_node / binder_ref
  - ioctl 路径
  - mmap 优化
  - 死亡通知
  - oneway / async
  - 与 cgroup / 调度 / 信号 的联动
```

### 15.2 Framework 06 讲什么

```
Framework 06 讲：
  - AIDL 接口定义
  - libbinder 客户端 stub
  - libbinder 服务端 stub
  - ServiceManager 注册/查询
  - BinderProxy / Binder 类
  - Parcel 序列化
  - Java DeathRecipient
  - 应用层 API
```

**关键认知**：
- Kernel 层：本篇（IPC 的"基础设施"）
- Framework 层：API + 用户态 stub
- 镜像分工：互不重叠

### 15.3 学习路径建议

```
1. 先读 Framework 06：
   了解 AIDL、ServiceManager、Binder API

2. 再读本篇：
   理解内核驱动实现 + 性能优化

3. 实践：
   用 dumpsys binder / perfetto 调 binder
```

**关键**：
- Framework 06 先读——应用层先理解
- 本篇再读——内核视角理解
- 两者配合形成完整认知

---

## 十六、给 13 篇留的钩子

读完 12 篇，你应该能：

1. 在脑中画出 IPC 的全景图——pipe / shm / futex / Binder。
2. 跟踪 pipe / fifo 的内核实现。
3. 知道 mmap / shmem 共享内存怎么实现。
4. 跟踪 futex 的内核实现。
5. **理解 Binder 驱动架构**——binder_proc / binder_thread / binder_transaction。
6. 知道 Binder 线程池的工作机制。
7. 理解 Binder 的死亡通知。
8. 知道 Binder 的性能优化。
9. 能在 Android 14 上看 binder 调用统计。
10. 理解与 Framework 06 的镜像分工。

**阶段 D（控制）全部结束**——本系列核心机制讲完。

最后一篇 13《进程调试与稳定性关联》收口（阶段 E）：

> 1-12 篇全是原理。13 篇回答："这和我排查线上问题有什么关系"？
>
> - ftrace sched_switch / PSI / proc 关键字段 / perfetto 调度条
> - 3 个实战案例（卡顿定位 / ANR 系统侧归因 / LMKD 误杀排查）
>
> 读完 13，整个 13 篇系列闭环。

---

## 小结

| 维度 | 一句话总结 |
|---|---|
| IPC 分类 | pipe / shm / futex / Binder / socket / msg queue |
| pipe | 字节流——父子进程通信 |
| mmap / shmem | 共享内存——最快，需同步 |
| futex | pthread 同步基础——无竞争零 syscall |
| Binder | Android 14 跨进程 RPC——mmap 优化 |
| 死亡通知 | linkToDeath——内核主动通知客户端 |
| framework vs Kernel | Framework 06 讲 API / 本篇讲内核 |

---

## 给下篇的桥

**本篇留下三个钩子**：

1. binder 调用耗时怎么算？→ 13 篇详讲
2. binder 死锁怎么排查？→ 13 篇实战案例
3. binder 跟 ANR 怎么联动？→ 13 篇 ANR 系统侧归因

如果读完本文仍有疑问：

- **"binder 调用慢？"** → §11.4 延迟基准 + §11.3 perfetto 分段
- **"binder 死锁？"** → §12.2 排查
- **"binder 内存耗尽？"** → §12.4 buffer 管理

---

## 引用

| 引用 | 路径 |
|---|---|
| pipe_inode_info | `include/linux/pipe_fs_i.h:struct pipe_inode_info` |
| pipe_buffer | `include/linux/pipe_fs_i.h:struct pipe_buffer` |
| pipe_read | `fs/pipe.c:pipe_read` |
| pipe_write | `fs/pipe.c:pipe_write` |
| shmem | `mm/shmem.c` |
| futex 入口 | `kernel/futex.c` |
| futex_wait | `kernel/futex.c:futex_wait` |
| futex_wake | `kernel/futex.c:futex_wake` |
| PI-futex | `kernel/rtmutex.c` |
| Binder 驱动 | `drivers/android/binder.c` |
| binder_proc | `drivers/android/binder.c:struct binder_proc` |
| binder_thread | `drivers/android/binder.c:struct binder_thread` |
| binder_transaction | `drivers/android/binder.c:binder_transaction` |
| binder_ioctl | `drivers/android/binder.c:binder_ioctl` |
| Android 14 Binder | `frameworks/native/libs/binder/` |
| Android 14 AIDL | `frameworks/base/core/java/android/os/IBinder.java` |
| Android 14 binder_calls_stats | `frameworks/native/services/binder/binder_calls_stats.cpp` |