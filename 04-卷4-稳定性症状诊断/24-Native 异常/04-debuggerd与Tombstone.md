# 04-debuggerd 与 Tombstone：Android 的崩溃捕获架构

前两篇我们分别拆解了 Linux 信号机制（信号如何产生、传递、处理）和内存管理机制（SIGSEGV/SIGBUS 的硬件根源）。信号告诉我们"发生了什么错误"，内存管理告诉我们"为什么这个地址不合法"。但还有一个关键问题没有回答——**崩溃信息是如何被记录下来的？**

当一个 Native 进程收到致命信号后，它不是简单地死掉。在 Android 系统中，有一套精心设计的崩溃捕获架构，在进程死亡前的最后几百毫秒内，完成寄存器采集、堆栈回溯、内存转储、日志写入等一系列操作，最终生成一份 **Tombstone（墓碑）** 文件——这就是你排查 NE 时看到的那份"遗书"。

本篇将沿着"debuggerd 架构设计 → 进程内 Signal Handler → crash_dump 进程 → Tombstone 生成 → 日志与上报"的路径，从 AOSP 源码层面完整拆解这套崩溃捕获架构。每个环节都将落到稳定性工程实践——因为只有理解了 Tombstone 是怎么生成的，你才能理解它为什么有时候信息不完整。

---

## 1. debuggerd 是什么

### 1.1 为什么 Android 不用 Linux 的 coredump

在标准 Linux 环境中，当进程收到致命信号（如 SIGSEGV）时，内核的默认行为是生成一个 **core dump** 文件——它包含进程死亡瞬间的完整内存映像（虚拟地址空间中所有可读的页面），加上寄存器状态和信号信息。开发者可以用 `gdb core <file>` 加载 core dump 进行事后调试。

但 Android 选择了完全不同的路径——**不生成 core dump，而是生成 Tombstone**。这不是随意的选择，而是基于移动设备的严苛约束：

| 维度 | Linux core dump | Android Tombstone |
| :--- | :--- | :--- |
| **文件大小** | 等于进程虚拟内存用量（几百 MB ~ 数 GB） | 通常 10-200 KB |
| **生成耗时** | 需要将整个地址空间写入磁盘（秒级） | 只采集关键信息（百毫秒级） |
| **存储需求** | 需要大量可用磁盘空间 | 固定 32 个文件槽位，循环覆盖 |
| **隐私风险** | 包含进程的全部内存（可能含用户数据、密钥） | 只包含寄存器、堆栈、关键内存区域的摘要 |
| **可读性** | 需要 GDB + 未剥离的二进制文件 | 纯文本，人眼可直接阅读 |
| **上报可行性** | 文件太大，无法网络上报 | 文件小，可通过 DropBoxManager 上报 |

**用一句话说：** core dump 是为桌面/服务器调试设计的"全量快照"，而 Tombstone 是为移动设备设计的"关键摘要"。在存储有限、隐私敏感、需要远程上报的移动场景下，Tombstone 是更合理的选择。

### 1.2 debuggerd 架构的演进

Android 的崩溃捕获架构经历了两次重大变化：

| 版本 | 架构 | 核心变化 |
| :--- | :--- | :--- |
| **Android 4.x - 7.x** | `debuggerd` 守护进程模型 | 崩溃进程通过 socket 连接到一个常驻的 `debuggerd` 守护进程，由 `debuggerd` 执行 ptrace + 生成 tombstone |
| **Android 8.0+** | `crash_dump` 按需启动模型 | 取消常驻守护进程，改为每次崩溃时 `exec()` 一个 `crash_dump` 独立进程。`tombstoned` 守护进程仅负责管理 tombstone 文件的 fd 分配 |
| **Android 12+** | Proto 格式 Tombstone | 在文本格式基础上新增 Protocol Buffers 二进制格式，支持结构化解析 |

**架构演进的原因：** 旧的常驻 `debuggerd` 守护进程是一个单点——如果它自己崩溃或被 OOM Killer 杀死，所有进程的崩溃都无法被捕获。新架构中 `crash_dump` 是按需 `exec()` 的临时进程，`tombstoned` 只做文件管理不涉及 ptrace，单点风险大幅降低。

### 1.3 当前架构全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Android 崩溃捕获架构（Android 8.0+）                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  崩溃进程                                                            │
│  ┌───────────────────────────────────────────┐                     │
│  │  线程 T1: 正常执行 → SIGSEGV → Signal Handler                    │
│  │                                           │                     │
│  │  debuggerd_signal_handler()                │                     │
│  │    │                                      │                     │
│  │    ├─ 保存崩溃现场（siginfo_t + ucontext） │                     │
│  │    ├─ clone() 创建伪线程                    │                     │
│  │    │    └─ 伪线程:                          │                     │
│  │    │        ├─ socket 连接 tombstoned       │                     │
│  │    │        ├─ 获取 tombstone 文件 fd        │                     │
│  │    │        └─ exec("crash_dump")           │                     │
│  │    └─ futex_wait（等待 crash_dump 完成）    │                     │
│  └───────────────────────────────────────────┘                     │
│                          │                                          │
│                          ▼                                          │
│  crash_dump 进程（独立地址空间）                                       │
│  ┌───────────────────────────────────────────┐                     │
│  │  1. ptrace(ATTACH) 所有线程                │                     │
│  │  2. ptrace(GETREGSET) 读取寄存器           │                     │
│  │  3. process_vm_readv() 读取内存            │                     │
│  │  4. libunwindstack 堆栈回溯                │                     │
│  │  5. engrave_tombstone() 格式化输出          │                     │
│  │  6. ptrace(DETACH) 释放所有线程             │                     │
│  └──────────────────┬────────────────────────┘                     │
│                     │                                               │
│                     ▼                                               │
│  tombstoned 守护进程                                                 │
│  ┌───────────────────────────────────────────┐                     │
│  │  管理 /data/tombstones/ 目录               │                     │
│  │  分配 tombstone_XX 文件 fd                 │                     │
│  │  循环覆盖（最多 32 个文件）                  │                     │
│  │  通知 logd 写入 crash 摘要                  │                     │
│  │  通知 DropBoxManager 归档                   │                     │
│  └───────────────────────────────────────────┘                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**稳定性架构师视角：** 这个三段式架构（进程内 Handler → crash_dump 进程 → tombstoned）的核心设计哲学是**隔离**：
- 进程内 Handler 尽量少做事（只 clone + exec），避免在已损坏的进程状态中执行复杂逻辑
- crash_dump 运行在独立地址空间，不受崩溃进程的堆栈/堆损坏影响
- tombstoned 只管理文件，不涉及 ptrace，不会因 ptrace 操作失败而卡住

---

## 2. 进程内 Signal Handler

### 2.1 debuggerd_handler 的注册时机

崩溃捕获的起点是——在进程生命周期的极早期，Bionic 的动态链接器（linker）就为当前进程注册了一个 Signal Handler，用于拦截致命信号。这个注册发生在 `main()` 函数执行之前，甚至在任何 constructor 函数（`__attribute__((constructor))`）之前。

**源码路径：** `bionic/linker/linker_main.cpp`

```cpp
// bionic/linker/linker_main.cpp
static ElfW(Addr) linker_main(KernelArgumentBlock& args,
                                const char* exe_to_load) {
    // ... ELF 加载、重定位等 ...

    // 在所有共享库加载完成后、执行 init 函数之前，注册 debuggerd handler
    debuggerd_init(&callbacks);

    // ... 执行 .init_array 构造函数 ...
    // ... 跳转到 main() ...
}
```

`debuggerd_init()` 的实现位于 `bionic/linker/debuggerd_handler.cpp`：

```cpp
// bionic/linker/debuggerd_handler.cpp
void debuggerd_init(debuggerd_callbacks_t* callbacks) {
    // 保存回调函数（用于获取 abort message 等）
    g_callbacks = *callbacks;

    // 为 6 种致命信号注册同一个 Handler
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    sigfillset(&action.sa_mask);             // Handler 执行期间阻塞所有信号
    action.sa_sigaction = debuggerd_signal_handler;
    action.sa_flags = SA_RESTART | SA_SIGINFO | SA_ONSTACK;

    // 逐个注册：SIGABRT, SIGBUS, SIGFPE, SIGILL, SIGSEGV, SIGTRAP, SIGSYS
    debuggerd_register_handlers(&action);
}
```

**关键标志位解读：**
- `SA_SIGINFO`：使用三参数形式的 Handler `(int sig, siginfo_t* info, void* ucontext)`，能获取 `fault addr` 和寄存器上下文
- `SA_ONSTACK`：在 Alternate Signal Stack 上运行 Handler。如果崩溃原因是栈溢出，此时用户栈已不可用，没有备用栈就无法执行 Handler
- `SA_RESTART`：被信号中断的系统调用自动重启
- `sigfillset(&action.sa_mask)`：Handler 执行期间阻塞所有其他信号，防止嵌套中断

**稳定性关联：** `debuggerd_init()` 的调用时机极其重要——它在所有共享库的 constructor 之前执行。这意味着即使某个 `.so` 的 `__attribute__((constructor))` 函数中发生 Native Crash，debuggerd handler 也已经就位，能够捕获崩溃。但反过来，如果 linker 自身在 `debuggerd_init()` 之前就崩溃了（比如 ELF 加载阶段的 bug），则没有 handler 可以拦截，进程会被内核默认行为杀死，不留任何 tombstone。

### 2.2 Signal Handler 的核心逻辑

当致命信号到达时，`debuggerd_signal_handler` 被调用。它的设计原则是**在信号处理函数中做尽可能少的事**——因为此时进程状态可能已经损坏（堆被破坏、栈被溢出、锁被持有），任何复杂操作都可能导致死锁或二次崩溃。

**源码路径：** `bionic/linker/debuggerd_handler.cpp`

```cpp
// bionic/linker/debuggerd_handler.cpp
static void debuggerd_signal_handler(int signal_number, siginfo_t* info,
                                      void* context) {
    // 防止递归进入（如果 Handler 自身触发了崩溃）
    static bool handler_reentered = false;
    if (handler_reentered) {
        // 二次进入 → 直接恢复默认行为，让内核杀死进程
        signal(signal_number, SIG_DFL);
        raise(signal_number);
        return;
    }
    handler_reentered = true;

    // 1. 收集崩溃线程的基本信息
    //    注意：这里只保存指针，不做任何内存分配
    debugger_thread_info thread_info = {
        .pseudothread_tid = -1,
        .crashing_tid = __gettid(),
        .siginfo = info,
        .ucontext = static_cast<ucontext_t*>(context),
        .signal_number = signal_number,
        .abort_msg = __android_log_abort_message(),
    };

    // 2. 通过 clone() 创建一个"伪线程"来完成后续操作
    //    为什么不用 fork()？因为 fork() 在多线程环境中不安全（可能死锁）
    //    为什么不用 pthread_create()？因为它需要 malloc，在 Signal Handler 中不安全
    pid_t child_pid = clone(debuggerd_dispatch_pseudothread,
                            &memory[thread_info_size],  // 预分配的栈空间
                            CLONE_THREAD | CLONE_SIGHAND | CLONE_VM | CLONE_CHILD_SETTID
                            | CLONE_CHILD_CLEARTID,
                            &thread_info,
                            nullptr, nullptr,
                            &thread_info.pseudothread_tid);

    if (child_pid == -1) {
        // clone 失败 → 无法生成 tombstone，直接退出
        __libc_write_log(ANDROID_LOG_FATAL, "libc",
                         "failed to spawn debuggerd dispatch thread");
    }

    // 3. 等待伪线程完成（通过 futex）
    //    这里崩溃线程被挂起，等 crash_dump 收集完信息后才继续
    futex_wait(&thread_info.pseudothread_tid, -1);

    // 4. crash_dump 已完成，恢复默认信号处理，重新发送信号
    //    进程将被内核的默认行为终止
    signal(signal_number, SIG_DFL);
    raise(signal_number);
}
```

### 2.3 伪线程：debuggerd_dispatch_pseudothread

`clone()` 创建的伪线程负责"对外联络"——连接 tombstoned 守护进程获取 tombstone 文件 fd，然后 `exec()` 启动 `crash_dump` 进程。

**源码路径：** `bionic/linker/debuggerd_handler.cpp`

```cpp
// bionic/linker/debuggerd_handler.cpp
static int debuggerd_dispatch_pseudothread(void* arg) {
    debugger_thread_info* thread_info = static_cast<debugger_thread_info*>(arg);

    // 1. 通过 UNIX domain socket 连接到 tombstoned
    int tombstone_socket = -1;
    int output_fd = -1;
    tombstoned_connect(thread_info->crashing_tid,
                       &tombstone_socket, &output_fd,
                       kDebuggerdTombstoneProto);  // Android 12+ 请求 Proto 格式

    // 2. 准备 crash_dump 的参数
    //    将崩溃进程 PID、崩溃线程 TID、信号信息等通过 pipe 传递
    int pipe_fds[2];
    pipe(pipe_fds);

    // 将 siginfo_t 和 ucontext_t 写入 pipe
    // crash_dump 将通过 pipe 读取这些信息
    write(pipe_fds[1], thread_info->siginfo, sizeof(siginfo_t));
    write(pipe_fds[1], thread_info->ucontext, sizeof(ucontext_t));

    // 3. exec() 启动 crash_dump 进程
    //    crash_dump 继承了 output_fd（tombstone 文件）和 pipe_fds[0]（崩溃信息）
    char pid_str[20];
    snprintf(pid_str, sizeof(pid_str), "%d", thread_info->crashing_tid);

    execle("/system/bin/crash_dump64",  // 或 crash_dump32
           "crash_dump64",
           pid_str,                     // 崩溃线程 TID
           nullptr,
           nullptr);

    // exec 失败 → crash_dump 未能启动
    return 1;
}
```

### 2.4 为什么 Signal Handler 中禁止调用 async-signal-unsafe 函数

这是整个崩溃捕获架构中最微妙也最重要的设计约束。POSIX 标准定义了一组**异步信号安全（async-signal-safe）** 函数——只有这些函数可以在 Signal Handler 中安全调用。`malloc()`、`printf()`、`pthread_mutex_lock()` 等常见函数都**不在**此列。

**原因：** Signal Handler 可以在进程执行流的**任意位置**被调用。如果进程正在 `malloc()` 内部（持有 malloc 的内部锁），此时信号到达，Handler 中再调用 `malloc()` 就会尝试获取同一把锁 → **死锁**。

```
正常执行流:
  main() → process_data() → malloc()  [持有 malloc 内部锁]
                                 │
                            SIGSEGV 到达
                                 │
                                 ▼
  Signal Handler:
    crash_handler() → collect_info() → malloc()  [尝试获取同一把锁]
                                                   ↓
                                              ★ 死锁 ★
                                          进程永远挂在这里
                                          没有 tombstone 输出
```

这就是为什么 `debuggerd_signal_handler` 使用 `clone()` 而非 `fork()` 或 `pthread_create()`：

| 方式 | 问题 |
| :--- | :--- |
| `fork()` | 在多线程环境中，`fork()` 只复制调用线程，不复制其他线程。如果其他线程持有 mutex（如 malloc 锁），子进程中这些 mutex 永远无法被释放 → 死锁 |
| `pthread_create()` | 内部调用 `mmap()` 分配线程栈 + `clone()`，而 `mmap()` 可能需要获取 `mm->mmap_lock`，在 Signal Handler 中不安全 |
| `clone(CLONE_VM)` | 共享地址空间，不复制页表，不需要 malloc。使用预分配的栈空间，完全避免内存分配 |

**稳定性关联：** 这个约束不仅适用于 debuggerd，也适用于所有 APM 框架。如果你的 APM 框架在 Signal Handler 中调用了 `malloc()`、`snprintf()`、`std::string` 的构造函数、`dladdr()`（内部有 mutex）等 async-signal-unsafe 函数，就存在在崩溃时死锁的风险——表现为"进程挂死而非崩溃"，APM 和系统都捕获不到任何信息。

---

## 3. crash_dump 进程

### 3.1 为什么需要独立进程

`crash_dump` 作为独立进程执行崩溃信息采集，这个设计有几个关键优势：

1. **地址空间隔离：** crash_dump 有自己独立的堆和栈。即使崩溃进程的堆已被严重破坏（heap corruption），crash_dump 的内存操作不受影响。
2. **可以安全使用所有 libc 函数：** 不再受 async-signal-safe 的限制——`malloc()`、`snprintf()`、`dladdr()` 都可以自由使用。
3. **ptrace 权限：** crash_dump 通过 `ptrace(PTRACE_ATTACH)` 附着到崩溃进程，以"调试器"的身份读取崩溃进程的寄存器和内存。这是一种安全且可靠的进程间数据读取方式。
4. **超时保护：** 如果 crash_dump 自身卡住（比如 ptrace 操作超时），init 进程可以杀死它而不影响系统稳定性。

### 3.2 crash_dump 的核心流程

**源码路径：** `system/core/debuggerd/crash_dump.cpp`

```cpp
// system/core/debuggerd/crash_dump.cpp
int main(int argc, char** argv) {
    // 从命令行参数获取崩溃进程的 PID 和 TID
    pid_t target_process = atoi(argv[1]);
    pid_t main_tid = atoi(argv[2]);

    // 1. 读取崩溃进程的线程列表
    //    通过 /proc/<pid>/task/ 枚举所有线程
    std::set<pid_t> threads;
    if (!android::procinfo::GetProcessTids(target_process, &threads)) {
        LOG(FATAL) << "failed to get threads for " << target_process;
    }

    // 2. ptrace attach 到所有线程
    //    attach 后，目标线程被暂停（SIGSTOP）
    for (pid_t thread : threads) {
        if (ptrace(PTRACE_SEIZE, thread, 0, 0) != 0) {
            PLOG(WARNING) << "failed to seize thread " << thread;
            // 部分线程 attach 失败不是致命错误
            // 但该线程的信息将不会出现在 tombstone 中
        }
    }

    // 3. 读取崩溃线程的寄存器状态
    //    使用 PTRACE_GETREGSET 获取通用寄存器和浮点寄存器
    struct iovec iov;
    struct user_pt_regs regs;
    iov.iov_base = &regs;
    iov.iov_len = sizeof(regs);
    ptrace(PTRACE_GETREGSET, main_tid, NT_PRSTATUS, &iov);

    // 4. 读取崩溃进程的内存映射（/proc/<pid>/maps）
    std::unique_ptr<unwindstack::Maps> maps(
        new unwindstack::RemoteMaps(target_process));
    maps->Parse();

    // 5. 创建远程内存读取接口
    auto process_memory = unwindstack::Memory::CreateProcessMemory(target_process);

    // 6. 使用 libunwindstack 进行堆栈回溯
    for (pid_t thread : threads) {
        std::unique_ptr<unwindstack::Regs> thread_regs(
            unwindstack::Regs::RemoteGet(thread));

        unwindstack::Unwinder unwinder(256, maps.get(),
                                        thread_regs.get(),
                                        process_memory);
        unwinder.Unwind();

        // 保存回溯结果
        thread_info[thread].frames = unwinder.frames();
    }

    // 7. 生成 tombstone
    engrave_tombstone(std::move(output_fd),
                      unwinder, threads, main_tid,
                      process_memory, maps.get(),
                      abort_msg, ...);

    // 8. ptrace detach 所有线程
    //    detach 后，崩溃进程恢复执行（然后被默认信号行为杀死）
    for (pid_t thread : threads) {
        ptrace(PTRACE_DETACH, thread, 0, 0);
    }

    return 0;
}
```

### 3.3 ptrace：crash_dump 的"眼睛"

`ptrace` 是 Linux 提供的进程追踪系统调用，也是调试器（GDB）和崩溃转储工具的核心能力。crash_dump 使用以下 ptrace 操作：

| ptrace 操作 | 用途 | 失败后果 |
| :--- | :--- | :--- |
| `PTRACE_SEIZE` | 附着到目标线程（不发送 SIGSTOP） | 无法读取该线程的任何信息 |
| `PTRACE_INTERRUPT` | 中断目标线程的执行 | 线程状态不稳定 |
| `PTRACE_GETREGSET` | 读取寄存器组（通用寄存器 + 浮点寄存器） | Tombstone 中寄存器段为空 |
| `PTRACE_PEEKDATA` | 读取目标进程的一个 word 内存 | 内存转储不完整 |
| `PTRACE_DETACH` | 释放目标线程 | 目标线程永远停在暂停状态 |

**源码路径：** `system/core/debuggerd/crash_dump.cpp` 中的 `ReadRegisters` 函数：

```cpp
// system/core/debuggerd/crash_dump.cpp（简化）
static bool ReadRegisters(pid_t tid, unwindstack::Regs** regs) {
    // ARM64 使用 GETREGSET 而非 GETREGS
    struct iovec iov;
    struct user_pt_regs arm64_regs;
    iov.iov_base = &arm64_regs;
    iov.iov_len = sizeof(arm64_regs);

    if (ptrace(PTRACE_GETREGSET, tid, NT_PRSTATUS, &iov) == -1) {
        PLOG(ERROR) << "failed to read registers for thread " << tid;
        return false;
    }

    *regs = unwindstack::RegsArm64::Read(&arm64_regs);
    return true;
}
```

### 3.4 ptrace 失败的常见原因

ptrace 操作并非总是成功的。以下场景会导致 ptrace 失败，进而导致 Tombstone 信息不完整：

| 失败原因 | 具体场景 | Tombstone 表现 |
| :--- | :--- | :--- |
| **SELinux 策略拒绝** | crash_dump 对目标进程没有 ptrace 权限（常见于 Vendor 分区的进程） | 整个 Tombstone 缺失，logcat 中有 `avc: denied { ptrace }` |
| **`PR_SET_DUMPABLE` 为 0** | 进程调用了 `prctl(PR_SET_DUMPABLE, 0)` 禁止被 ptrace | crash_dump 无法 attach，Tombstone 不生成 |
| **Yama ptrace_scope** | `/proc/sys/kernel/yama/ptrace_scope` 限制了 ptrace 权限 | 非父进程无法 ptrace |
| **线程在 ptrace 之前已退出** | 崩溃发生后，其他线程在 crash_dump attach 之前退出 | Tombstone 中缺失这些线程的信息 |
| **内存不可读** | `process_vm_readv()` 读取某些地址失败（如 VDSO 区域） | 对应的 memory 段显示 `(unreadable)` |

**稳定性架构师视角：** SELinux 导致的 ptrace 失败是 Tombstone 缺失的最常见原因。如果你发现 logcat 中有 NE 的 crash 日志（`DEBUG` tag），但 `/data/tombstones/` 中找不到对应文件，首先检查 `dmesg` 或 `logcat` 中是否有 `avc: denied { ptrace }` 的 SELinux 拒绝日志。修复方式是在 SELinux 策略中为 `crash_dump` 添加对目标进程域的 ptrace 权限。

### 3.5 libunwindstack：堆栈回溯引擎

crash_dump 调用 `libunwindstack` 进行堆栈回溯——从崩溃线程的 PC/SP/FP 寄存器出发，逐帧回溯出完整的函数调用链。

**源码路径：** `system/unwinding/libunwindstack/Unwinder.cpp`

```cpp
// system/unwinding/libunwindstack/Unwinder.cpp（简化）
void Unwinder::Unwind(const std::vector<std::string>* initial_map_names_to_skip,
                      const std::vector<std::string>* map_suffixes_to_ignore) {
    frames_.clear();

    for (size_t frame_num = 0; frame_num < max_frames_; frame_num++) {
        uint64_t cur_pc = regs_->pc();
        uint64_t cur_sp = regs_->sp();

        // 1. 通过 PC 地址查找对应的 ELF 文件（.so）
        MapInfo* map_info = maps_->Find(cur_pc);
        if (map_info == nullptr) {
            // PC 不在任何已知映射中 → 无法继续回溯
            break;
        }

        // 2. 从 ELF 中读取 unwind 信息（.eh_frame / .debug_frame）
        Elf* elf = map_info->GetElf(process_memory_, true);
        uint64_t rel_pc = elf->GetRelPc(cur_pc, map_info);

        // 3. 记录当前帧
        FrameData frame;
        frame.num = frame_num;
        frame.pc = rel_pc;
        frame.sp = cur_sp;
        frame.map_name = map_info->name();
        frame.function_name = elf->GetFunctionName(rel_pc, &frame.function_offset);
        frames_.push_back(frame);

        // 4. 使用 DWARF CFI 或 FP 链回溯到上一帧
        bool finished = false;
        if (!elf->Step(rel_pc, regs_.get(), process_memory_.get(), &finished)) {
            break;  // 回溯失败 → 堆栈断裂
        }
        if (finished) {
            break;  // 到达栈底
        }
    }
}
```

**堆栈回溯失败的常见原因：**

| 原因 | 后果 | 典型场景 |
| :--- | :--- | :--- |
| `.eh_frame` 段被剥离 | DWARF CFI 不可用，只能尝试 FP-based 回溯 | 某些 Vendor SO 编译时使用了 `-fno-asynchronous-unwind-tables` |
| `-fomit-frame-pointer` | FP 链断裂，无法沿 FP 回溯 | Release 构建的优化选项（ARM64 默认保留 FP） |
| 栈被严重破坏 | SP/FP 值不合法，回溯在第一帧就失败 | 栈缓冲区溢出覆盖了返回地址 |
| JIT 生成的代码无 unwind info | PC 在 ART JIT 代码缓存中，没有标准的 DWARF 信息 | ART 有自己的 JIT unwind 机制，但可能不完整 |

---

## 4. Tombstone 生成

### 4.1 为什么需要理解 Tombstone 的结构

Tombstone 是稳定性架构师日常工作中接触最多的"原始证据"。理解它的每一段内容**从何而来**，你才能判断：
- 哪些信息是可信的、哪些可能因采集失败而缺失
- 当信息缺失时，从哪里可以补充
- 如何自动化解析 Tombstone 进行聚类和归因

### 4.2 engrave_tombstone：Tombstone 的"雕刻者"

**源码路径：** `system/core/debuggerd/libdebuggerd/tombstone.cpp`

`engrave_tombstone()` 是 Tombstone 内容的总入口。它按顺序调用各个子函数，将崩溃信息写入输出 fd：

```cpp
// system/core/debuggerd/libdebuggerd/tombstone.cpp（简化主流程）
void engrave_tombstone(int tombstone_fd,
                        unwindstack::Unwinder* unwinder,
                        const std::map<pid_t, ThreadInfo>& threads,
                        pid_t target_thread,
                        const ProcessInfo& process_info,
                        const OpenFilesList* open_files,
                        std::string* amfd_data) {
    // 1. Header：进程基本信息
    dump_header_info(log, process_info);

    // 2. Signal Info：信号类型、si_code、fault addr
    dump_signal_info(log, thread_info, process_info);

    // 3. Abort Message：如果是 SIGABRT，输出 abort() 时的消息
    if (abort_msg && !abort_msg->empty()) {
        dump_abort_message(log, *abort_msg);
    }

    // 4. Registers：崩溃线程的所有寄存器值
    dump_registers(log, thread_info.registers);

    // 5. Backtrace：崩溃线程的堆栈回溯
    dump_backtrace(log, unwinder, thread_info);

    // 6. Memory Near Registers：寄存器指向地址附近的内存内容
    dump_memory_and_code(log, thread_info);

    // 7. Memory Maps：进程的完整内存映射
    dump_all_maps(log, unwinder, thread_info);

    // 8. Other Threads：其他线程的寄存器和堆栈
    for (auto& [tid, info] : threads) {
        if (tid == target_thread) continue;
        dump_thread(log, unwinder, info);
    }

    // 9. Open Files：进程打开的文件描述符列表
    dump_open_fds(log, open_files);

    // 10. Log Messages：logcat 中该进程最近的日志
    dump_log_file(log, "main", target_thread);
    dump_log_file(log, "system", target_thread);
}
```

### 4.3 Tombstone 的完整结构

一份标准的 Tombstone 文件包含以下段，每段都有明确的数据来源：

```
*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***   ← 魔术头
```

**段一：Header（进程基本信息）**

```
Build fingerprint: 'google/raven/raven:13/TP1A.221105.002/9080065:userdebug/dev-keys'
Revision: 'MP1.0'
ABI: 'arm64'
Timestamp: 2024-01-15 14:23:45.123+0800
Process uptime: 3842s
Cmdline: com.example.app
pid: 12345, tid: 12367, name: RenderThread  >>> com.example.app <<<
uid: 10128
tagged_addr_ctrl: 0000000000000001 (PR_TAGGED_ADDR_ENABLE)
```

| 字段 | 数据来源 | 稳定性价值 |
| :--- | :--- | :--- |
| Build fingerprint | `ro.build.fingerprint` system property | 确定系统版本，关联 symbol 文件 |
| ABI | 进程的 ELF 类型（arm64/arm/x86） | 选择正确的 addr2line 工具链 |
| pid / tid / name | `/proc/<pid>/status`、`/proc/<tid>/comm` | 崩溃线程标识（pid=进程号，tid=崩溃线程号） |
| Process uptime | 进程启动至崩溃的时间 | 启动阶段崩溃 vs 运行时崩溃的判断依据 |

**段二：Signal Info（信号信息）**

```
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0000000000000010
Cause: null pointer dereference
```

数据来源：Signal Handler 接收到的 `siginfo_t` 结构体。`Cause` 字段是 Android 系统根据 `fault addr` 和 `si_code` 自动推断的原因描述。

**段三：Abort Message（仅 SIGABRT）**

```
Abort message: 'Scudo ERROR: corrupted chunk header at address 0x7b340a2010'
```

数据来源：`__android_log_abort_message()` 返回的字符串。当代码调用 `LOG(FATAL)`、`CHECK()` 宏、或 Scudo 检测到堆损坏时，会先将描述信息写入全局缓冲区，然后调用 `abort()`。

**段四：Registers（寄存器）**

```
    x0  0000000000000000  x1  0000007b340a2010  x2  0000000000000008  x3  0000000000000000
    x4  ffffffffffffffff  x5  0000000000000000  x6  0000000000000000  x7  0000000000000001
    ...
    x28 0000007fe4d02a80  x29 0000007fe4d02a30
    lr  0000007a3e1234b8  sp  0000007fe4d02a10  pc  0000007a3e123480  pstate 0000000060001000
```

数据来源：`ptrace(PTRACE_GETREGSET)` 读取的 `user_pt_regs` 结构体。

| 关键寄存器 | 含义 | 排查价值 |
| :--- | :--- | :--- |
| `pc` | Program Counter，指向触发崩溃的指令地址 | Backtrace 第一帧的地址 |
| `lr` (x30) | Link Register，调用者的返回地址 | 如果 backtrace 回溯失败，`lr` 提供了上一帧的线索 |
| `sp` | Stack Pointer，当前栈顶地址 | 验证栈是否溢出（对比 maps 中的栈范围） |
| `x0-x7` | 函数参数（ARM64 调用约定） | 崩溃函数的入参，可能包含 NULL 指针 |

**段五：Backtrace（堆栈回溯）**

```
backtrace:
      #00 pc 0x0004a2bc  /vendor/lib64/libcamera_hal.so (CameraDevice::processRequest+188)
      #01 pc 0x0004b890  /vendor/lib64/libcamera_hal.so (RequestThread::threadLoop+240)
      #02 pc 0x00012f64  /system/lib64/libutils.so (android::Thread::_threadLoop+280)
      #03 pc 0x000b2e48  /system/lib64/libc.so (__pthread_start+64)
      #04 pc 0x00050eb4  /system/lib64/libc.so (__start_thread+68)
```

数据来源：`libunwindstack::Unwinder::Unwind()` 的结果。`pc` 是相对于 SO 基地址的偏移，用于 `addr2line` 符号化。

**段六：Memory Near Registers（寄存器附近的内存）**

```
memory near x1 ([anon:scudo:primary]):
    0000007b340a2000 0000000000000000 0000000000000000  ................
    0000007b340a2010 0000000000000000 a3b2c1d000000100  ................
```

数据来源：`process_vm_readv()` 或 `ptrace(PTRACE_PEEKDATA)` 读取寄存器值指向地址前后各 256 字节。

**段七：Memory Maps（内存映射）**

```
memory map (1428 entries):
    0000005500000000-0000005500001000 r--p 00000000  /system/bin/app_process64
    0000007a3e000000-0000007a3e100000 r--p 00000000  /data/app/com.example/lib/arm64/libnative.so
    0000007a3e100000-0000007a3e200000 r-xp 00100000  /data/app/com.example/lib/arm64/libnative.so (BuildId: abcdef1234567890)
    0000007fe4c00000-0000007fe4d03000 rw-p 00000000  [stack]
```

数据来源：`/proc/<pid>/maps`。每行对应一个 VMA（Virtual Memory Area），包含地址范围、权限（r/w/x/p）、文件映射路径、BuildId 等。

**段八：Other Threads（其他线程信息）**

为进程中所有其他存活线程输出寄存器和 backtrace。虽然崩溃发生在特定线程，但其他线程的状态对分析多线程竞态问题至关重要。

### 4.4 Proto 格式（Android 12+）

Android 12 引入了 Protocol Buffers 格式的 Tombstone，与传统文本格式并存。Proto 格式的优势是结构化、可编程解析，便于自动化分析平台处理。

**源码路径：** `system/core/debuggerd/proto/tombstone.proto`

```protobuf
// system/core/debuggerd/proto/tombstone.proto（关键定义）
message Tombstone {
    string build_fingerprint = 1;
    string revision = 2;
    string timestamp = 3;
    uint32 pid = 4;
    uint32 tid = 5;
    uint32 uid = 6;
    string command_line = 7;
    repeated string log_buffers = 8;

    Signal signal_info = 9;
    string abort_message = 10;

    repeated Thread threads = 11;      // 所有线程的详细信息
    repeated MemoryMapping memory_mappings = 12;
}

message Signal {
    int32 number = 1;        // 信号编号
    string name = 2;         // 信号名（如 "SIGSEGV"）
    int32 code = 3;          // si_code
    string code_name = 4;    // si_code 名（如 "SEGV_MAPERR"）
    uint64 fault_address = 5;
    bool has_sender = 6;
    int32 sender_uid = 7;
    int32 sender_pid = 8;
}

message Thread {
    uint32 id = 1;
    string name = 2;
    repeated Register registers = 3;
    repeated BacktraceFrame backtrace = 4;
    repeated MemoryDump memory_dump = 5;
}
```

**Proto Tombstone 的存储位置：** `/data/tombstones/tombstone_XX.pb`（与文本格式的 `tombstone_XX` 并存）。

**稳定性架构师视角：** Proto 格式 Tombstone 是构建自动化 NE 分析平台的基础。与文本格式相比，Proto 格式：
- 不需要写复杂的正则表达式来解析各字段
- 字段有明确的类型（int/string/repeated），不会因格式微调导致解析器失效
- 可以直接用 `protoc` 生成各语言（Java/Python/Go）的解析代码

---

## 5. 日志与上报

### 5.1 Tombstone 文件的写入

`tombstoned` 守护进程负责管理 `/data/tombstones/` 目录下的 Tombstone 文件。

**源码路径：** `system/core/debuggerd/tombstoned/tombstoned.cpp`

```cpp
// system/core/debuggerd/tombstoned/tombstoned.cpp（简化）
static void tombstoned_intercept(int sockfd) {
    // 1. 接收来自 crash_dump 的连接请求
    unique_fd peer_fd(accept4(sockfd, nullptr, nullptr, SOCK_CLOEXEC));

    // 2. 分配一个 tombstone 文件槽位
    //    /data/tombstones/tombstone_00 到 tombstone_31
    //    循环覆盖最旧的文件
    int slot = find_oldest_tombstone();
    std::string path = StringPrintf("/data/tombstones/tombstone_%02d", slot);

    // 3. 打开文件，将 fd 通过 socket 发送给 crash_dump
    unique_fd tombstone_fd(open(path.c_str(),
                                O_CREAT | O_TRUNC | O_WRONLY | O_CLOEXEC,
                                0640));

    // 同时创建 .pb 后缀的 Proto 格式文件（Android 12+）
    std::string proto_path = path + ".pb";
    unique_fd proto_fd(open(proto_path.c_str(),
                            O_CREAT | O_TRUNC | O_WRONLY | O_CLOEXEC,
                            0640));

    // 4. 将 fd 通过 UNIX socket 的 SCM_RIGHTS 发送给 crash_dump
    send_fd(peer_fd, tombstone_fd);
}
```

**文件管理策略：**

| 特性 | 值 |
| :--- | :--- |
| 存储目录 | `/data/tombstones/` |
| 文件命名 | `tombstone_00` 到 `tombstone_31`（循环） |
| 最大文件数 | 32（文本格式）+ 32（Proto 格式）|
| 覆盖策略 | 最旧文件优先被覆盖 |
| 文件权限 | `0640`（owner 可读写，group 可读） |
| SELinux 上下文 | `u:object_r:tombstone_data_file:s0` |

### 5.2 logd 日志输出

crash_dump 在生成 Tombstone 文件的同时，也会将崩溃摘要（Header + Signal + Backtrace）写入 logd，这就是你在 `logcat` 中看到的 `DEBUG` tag 日志。

**源码路径：** `system/core/debuggerd/libdebuggerd/tombstone.cpp`

```cpp
// system/core/debuggerd/libdebuggerd/tombstone.cpp（简化）
void engrave_tombstone_ucontext(int tombstone_fd, ...) {
    // 同时输出到文件和 logd
    TombstonedLog tombstone_log(tombstone_fd);
    LogdLog logd_log;

    // 文件写入
    dump_header_info(&tombstone_log, ...);
    dump_signal_info(&tombstone_log, ...);
    dump_backtrace(&tombstone_log, ...);

    // logd 写入（只输出摘要，不包含 maps 等详细信息）
    dump_header_info(&logd_log, ...);
    dump_signal_info(&logd_log, ...);
    dump_backtrace(&logd_log, ...);
}
```

**logcat 中的典型 NE 日志：**

```
F DEBUG   : *** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
F DEBUG   : Build fingerprint: 'google/raven/raven:13/...'
F DEBUG   : pid: 12345, tid: 12367, name: RenderThread  >>> com.example.app <<<
F DEBUG   : signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x10
F DEBUG   : Cause: null pointer dereference
F DEBUG   :     x0  0000000000000000  x1  0000007b340a2010 ...
F DEBUG   : backtrace:
F DEBUG   :       #00 pc 0x0004a2bc  /vendor/lib64/libcamera_hal.so
F DEBUG   :       #01 pc 0x0004b890  /vendor/lib64/libcamera_hal.so
```

### 5.3 DropBoxManager 上报

`system_server` 中的 `NativeCrashListener` 会监听 NE 事件，并通过 `DropBoxManagerService` 将 Tombstone 内容归档。

**源码路径：** `frameworks/base/services/core/java/com/android/server/am/NativeCrashListener.java`

```java
// frameworks/base/services/core/java/com/android/server/am/NativeCrashListener.java
final class NativeCrashListener extends Thread {
    @Override
    public void run() {
        // 监听来自 debuggerd 的 UNIX socket
        final LocalSocket socket = new LocalSocket();
        socket.connect(new LocalSocketAddress(
            "/data/system/ndebugsocket", LocalSocketAddress.Namespace.FILESYSTEM));

        while (true) {
            LocalSocket connection = socket.accept();
            // 读取 tombstone 内容
            String tombstoneContent = readTombstone(connection);

            // 通过 DropBoxManager 归档
            // tag 为 "data_app_native_crash" 或 "system_server_native_crash"
            DropBoxManager db = context.getSystemService(DropBoxManager.class);
            db.addText("data_app_native_crash", tombstoneContent);

            // 同时触发 App Error Dialog（如果配置了的话）
            ActivityManagerService.handleApplicationCrash(processRecord);
        }
    }
}
```

**DropBox 存储位置：** `/data/system/dropbox/`，文件名格式为 `data_app_native_crash@<timestamp>.txt.gz`。

### 5.4 为什么有时 logcat 有 NE 日志但找不到 Tombstone 文件

这是稳定性工程中的常见困惑。可能的原因有以下几种：

| 场景 | 原因 | 解决方案 |
| :--- | :--- | :--- |
| **Tombstone 文件被覆盖** | 32 个槽位已满，旧文件被新崩溃覆盖。高频崩溃的设备上，Tombstone 可能存活不到几分钟 | 增加 tombstone 槽位数量（需修改 tombstoned 源码），或实时上报 |
| **logcat 日志来自 logd 而非文件** | logd 输出和 Tombstone 文件写入是两条独立路径。如果 tombstoned 连接失败（socket 繁忙），文件可能写入失败，但 logd 仍可输出 | 同时检查 logcat 和 Tombstone 文件 |
| **权限问题** | 非 root 设备上普通 adb 无法直接读取 `/data/tombstones/`。需要 `adb bugreport` 或 root shell | 使用 `adb bugreport` 获取完整报告 |
| **进程在 crash_dump 之前被杀** | 如果进程被 SIGKILL 杀死（如 OOM Killer、ActivityManager 的 `forceStop`），在 crash_dump 完成之前进程已死 | 此时 crash_dump 的 ptrace 操作失败，Tombstone 不完整或缺失 |
| **tombstoned 未运行** | 极端情况下 tombstoned 守护进程被杀或未启动 | 检查 `init.rc` 中 tombstoned 的 service 定义和运行状态 |
| **磁盘空间不足** | `/data` 分区满了，无法创建新文件 | 清理磁盘空间 |

**稳定性架构师视角：** 在企业级 APM 体系中，不应仅依赖系统 Tombstone。系统 Tombstone 有三个先天不足：

1. **不上报**：Tombstone 存在设备本地，除非用户提交 bugreport，否则你无法远程获取
2. **会覆盖**：32 个槽位的循环策略意味着高频崩溃设备上的历史信息会丢失
3. **不聚合**：每个 Tombstone 都是独立文件，没有自动化的聚类和 Top Crash 分析

这就是为什么生产环境需要 APM 框架（xCrash/Breakpad/Crashpad）来补充——它们有独立的信号处理、本地存储、重启后上报、服务端聚合分析等完整链路。但 APM 框架必须与系统的 debuggerd 架构正确共存（通过 sigchain），否则两者可能互相干扰。

---

## 6. 稳定性实战案例

### 案例一：SELinux 策略导致 Vendor HAL 崩溃无 Tombstone

**现象：**

某手机厂商在新系统版本上线后，用户大量反馈"相机闪退"。但后端 APM 平台上该机型的 Camera 相关 Native Crash 上报量却为零。运维团队在问题设备上手动执行 `adb shell ls /data/tombstones/`，发现目录下没有任何与 `cameraserver` 相关的 Tombstone 文件。然而 `logcat | grep "DEBUG"` 有如下输出：

```
F DEBUG   : pid: 4521, tid: 4521, name: cameraserver  >>> /system/bin/cameraserver <<<
F DEBUG   : signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
F DEBUG   : (failed to attach to process)
```

注意关键行 `(failed to attach to process)` —— crash_dump 未能成功附着到崩溃进程。

**分析思路：**

1. **logcat 有 NE 日志但无 Tombstone 文件**：说明 crash_dump 被成功 exec，但执行过程中失败了。`(failed to attach to process)` 直接指向 ptrace 失败。
2. **检查 SELinux 日志**：在 `dmesg` 中搜索 `avc: denied`：
   ```
   avc: denied { ptrace } for pid=5123 comm="crash_dump64"
       scontext=u:r:crash_dump:s0
       tcontext=u:r:hal_camera_default:s0
       tclass=process permissive=0
   ```
   SELinux 策略拒绝了 `crash_dump` 对 `hal_camera_default` 域进程的 ptrace 操作。
3. **根因追溯**：新版本的系统更新中，Camera HAL 从 `system` 分区迁移到了 `vendor` 分区，对应的 SELinux 域从 `hal_camera_system` 变更为 `hal_camera_default`。但 `crash_dump` 的 SELinux 策略文件没有同步更新，缺少对新域的 ptrace 权限。

**根因：**

SELinux 策略不完整。`crash_dump` 域缺少对 `hal_camera_default` 域的 `ptrace` 权限，导致 crash_dump 无法 attach 到 cameraserver 进程，Tombstone 生成失败。

**修复方案：**

1. **短期修复**：在 SELinux 策略中为 crash_dump 添加对 `hal_camera_default` 域的 ptrace 权限：
   ```
   # vendor/sepolicy/private/crash_dump.te
   allow crash_dump hal_camera_default:process { ptrace };
   ```
2. **长期治理**：
   - 在 SELinux 策略编写规范中增加检查项：任何新增的 HAL 域必须同时添加 crash_dump 的 ptrace 权限
   - 在 CI 流水线中增加自动化测试：对所有系统服务进程发送 `kill -SIGSEGV` 并验证 Tombstone 是否生成
   - 建立 SELinux 策略审计脚本：定期扫描所有 `hal_*` 域，检查 `crash_dump` 是否有对应的 ptrace 权限

```
修复前后对比：
┌────────────────────────────────┬───────────┬───────────┐
│ 指标                            │ 修复前     │ 修复后     │
├────────────────────────────────┼───────────┼───────────┤
│ Camera NE Tombstone 生成率      │ 0%        │ 100%      │
│ APM 平台 Camera NE 可见率       │ 0%        │ 100%      │
│ 平均问题定位时间                 │ 48h+      │ 2h        │
│ "相机闪退"用户投诉（仍存在崩溃） │ 350/天    │ 350/天    │
│ "相机闪退"问题修复后用户投诉     │ —         │ 12/天     │
└────────────────────────────────┴───────────┴───────────┘
```

注意：修复 SELinux 策略只是让崩溃**可见**了（Tombstone 生成成功），崩溃本身（Camera HAL 的 SIGSEGV）还需要进一步分析 Tombstone 定位根因并修复。

---

### 案例二：crash_dump 超时导致 Tombstone 截断和 ANR

**现象：**

某 App 在特定低端机型上出现两个关联异常：
1. 部分 Tombstone 文件内容**截断**——只有 Header + Signal Info + Registers，没有 Backtrace 和 Memory Maps
2. 崩溃发生后，系统界面卡顿约 20 秒才弹出"应用无响应"对话框，期间整个设备 UI 冻结

`logcat` 中有以下日志：

```
W crash_dump64: ptrace(PTRACE_GETREGSET, 23456) failed: ESRCH
W crash_dump64: Failed to unwind thread 23456
W crash_dump64: --- timed out waiting for threads to stop ---
```

以及 `system_server` 的日志：

```
I ActivityManager: Process com.example.app (pid 23450) has died: fg  TOP
W ActivityManager: Slow operation: 18203ms so far, now at startProcess: done updating pids map
```

**分析思路：**

1. **Tombstone 截断 + "timed out waiting for threads to stop"**：crash_dump 尝试 ptrace attach 到崩溃进程的所有线程，但部分线程无法被暂停——它们可能在内核态的不可中断状态（`TASK_UNINTERRUPTIBLE`），通常是 I/O 等待（如磁盘读写、Binder 调用阻塞）。
2. **系统 UI 冻结 20 秒**：在低端设备上，crash_dump 的 ptrace 操作本身就很慢（需要遍历上百个线程并读取每个线程的寄存器和内存）。如果部分线程无法被暂停，crash_dump 会等待超时，进一步延长了 Tombstone 生成时间。
3. **关键洞察**：崩溃的进程是前台 TOP 进程，`system_server` 需要等待该进程完全退出后才能启动新进程。crash_dump 持有该进程（ptrace attach 期间进程不会退出），导致 `system_server` 的 `startProcess` 操作被阻塞约 18 秒。

**根因：**

崩溃进程拥有大量线程（该 App 启动了 128 个线程池线程），其中多个线程正在进行磁盘 I/O（处于 `TASK_UNINTERRUPTIBLE` 状态）。crash_dump 对这些线程执行 `PTRACE_INTERRUPT` 后需要等待它们退出内核态，而 I/O 操作在低端设备的 eMMC 上非常慢。crash_dump 的默认超时设置（约 20 秒）导致整个 Tombstone 生成过程耗时极长。在此期间，崩溃进程被 ptrace 持有无法退出，system_server 等待进程退出后才能启动替代进程，导致用户可见的 UI 冻结。

**修复方案：**

1. **短期修复**：在 crash_dump 的超时逻辑中加入"快速模式"——如果超过 5 秒仍有线程无法暂停，跳过这些线程并立即生成**部分** Tombstone（保证至少有崩溃线程的完整信息）
2. **长期治理**：
   - 在 App 侧限制线程数量（128 个线程池线程对于移动 App 明显过多），将线程池上限降至 CPU 核心数 × 2
   - 在 system_server 中增加"崩溃进程快速回收"机制——如果崩溃进程在 5 秒内未退出，发送 SIGKILL 强制终止（牺牲 Tombstone 完整性，换取用户体验）
   - 在低端设备上调低 crash_dump 的超时参数（通过 system property `debug.debuggerd.timeout_secs`）

```
修复前后对比：
┌────────────────────────────────┬───────────┬───────────┐
│ 指标                            │ 修复前     │ 修复后     │
├────────────────────────────────┼───────────┼───────────┤
│ Tombstone 截断率                │ 35%       │ 5%        │
│ NE 后 UI 冻结时长（低端机）      │ ~20s      │ ~3s       │
│ 崩溃线程 Backtrace 完整率       │ 65%       │ 98%       │
│ 用户可感知的"卡死后闪退"投诉    │ 180/天    │ 12/天     │
└────────────────────────────────┴───────────┴───────────┘
```

---

## 7. 总结

本篇沿着崩溃捕获的完整路径，从进程内 Signal Handler 到 crash_dump 到 Tombstone 生成和上报，拆解了 Android 的 debuggerd 架构。

核心要点：

1. **Android 选择 Tombstone 而非 core dump** 是基于移动设备的存储、隐私和上报约束。Tombstone 是"关键摘要"而非"全量快照"，以 10-200KB 的体积涵盖了排查 NE 所需的绝大部分信息。
2. **debuggerd_handler 在 linker 初始化阶段注册**，早于所有 constructor 函数。它在 Signal Handler 中只做 `clone()` + `exec()`，将所有复杂操作留给独立的 crash_dump 进程——这是为了规避 async-signal-unsafe 函数在信号处理上下文中的死锁风险。
3. **crash_dump 通过 ptrace 附着崩溃进程**，读取寄存器和内存，调用 libunwindstack 进行堆栈回溯。ptrace 失败（SELinux、PR_SET_DUMPABLE、线程已退出）是 Tombstone 信息不完整的主要原因。
4. **Tombstone 的每一段数据都有明确来源**——Header 来自 `/proc/<pid>/status`，Signal Info 来自 `siginfo_t`，Registers 来自 `ptrace(GETREGSET)`，Backtrace 来自 libunwindstack，Memory Maps 来自 `/proc/<pid>/maps`。理解来源才能判断信息的可靠性和缺失原因。
5. **Tombstone 写入 `/data/tombstones/`（32 文件循环）、logd（DEBUG tag）、DropBoxManager 三个目的地**。logcat 有日志但无 Tombstone 文件，通常是 ptrace 失败或 tombstoned 连接失败。
6. **Proto 格式 Tombstone（Android 12+）** 是构建自动化 NE 分析平台的基础，支持结构化解析，消除了文本格式正则解析的脆弱性。

在下一篇中，我们将深入堆栈回溯的原理——从 FP-based 到 DWARF CFI 到 libunwindstack 的实现，理解 Tombstone 中 Backtrace 的每一帧是如何计算出来的，以及为什么有时候堆栈会"断裂"。
