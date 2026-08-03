# 01-Native Crash 总览：稳定性架构师的全局视角

## 1. NE 是什么

Native Crash（业内简称 NE，Native Exception）是指运行在 Android 用户态的 Native 代码（C/C++）因非法操作触发 Linux 信号而导致进程异常终止的事件。简单来说，当一段 C/C++ 代码试图访问非法内存地址、执行非法指令、或者主动调用 `abort()` 时，Linux 内核会向该进程发送一个致命信号（如 `SIGSEGV`），若该信号未被有效处理，进程将被杀死。

**用一句话定义：** NE 是 Linux 信号驱动的进程级致命错误，它不经过任何虚拟机安全网，直接导致整个进程（包括其中的所有 Java/Kotlin 线程）立即死亡。

### 1.1 NE 与 JE 的本质区别

很多开发者把 Native Crash 和 Java Exception 混为一谈，但它们在机制上是完全不同的两个世界：

| 维度 | Java Exception (JE) | Native Crash (NE) |
| :--- | :--- | :--- |
| **触发机制** | JVM/ART 层面的异常对象，通过 `throw` 语句抛出 | Linux 内核信号（Signal），由 CPU 硬件异常或内核逻辑触发 |
| **可捕获性** | 可通过 `try-catch` 捕获并恢复 | 信号可拦截（`sigaction`），但进程状态通常已不可恢复 |
| **影响范围** | 仅影响当前线程的执行流，其他线程不受影响 | 整个进程终止，所有线程（Java + Native）全部死亡 |
| **堆栈信息** | 完整的 Java 堆栈，包含类名、方法名、行号 | 原始的 PC/LR 寄存器地址，需要通过符号表（symbols）还原 |
| **安全网** | ART 提供 UncaughtExceptionHandler 作为最后防线 | 无虚拟机安全网，信号处理函数是唯一的拦截点 |
| **排查难度** | 低——堆栈直观可读，日志中直接打印 | 高——堆栈可能残缺、符号可能被剥离（stripped）、需要 addr2line 翻译 |

### 1.2 为什么 NE 比 JE 更难排查

作为稳定性架构师，NE 之所以让人头疼，原因不止一个：

1. **无虚拟机安全网：** Java 代码运行在 ART 之上，ART 提供了内存安全（不会越界访问）、空指针保护（转为 `NullPointerException`）、数组越界保护等机制。而 Native 代码直接跑在 CPU 上，任何非法操作都会导致硬件异常。
2. **堆栈可能残缺：** 编译器优化（如 `-fomit-frame-pointer`）、栈被破坏（stack corruption）、异步信号中断等原因都可能导致 unwinder 无法正确回溯完整的调用栈。
3. **符号可能被剥离：** Release 版本的 so 库通常会执行 `strip` 操作，移除调试符号。此时 tombstone 中只有原始地址（如 `pc 0x7f8a3b2c`），必须用 `addr2line` 或 `ndk-stack` 配合未剥离的 so 文件（带 `.debug` 段或 `.sym` 后缀）才能还原函数名和行号。
4. **多线程竞态：** 很多 NE 由多线程竞态条件触发（如 use-after-free），这类问题往往难以复现，且 tombstone 中的堆栈只能反映崩溃瞬间的状态，无法直接看到"是谁释放了这块内存"。
5. **跨层调用链复杂：** 一个 NE 可能涉及 Java → JNI → Native → Kernel 的多层调用，需要同时具备 Java、C/C++、Linux 内核的知识才能定位根因。

---

## 2. 七种致命信号全景

在 NE 的世界里，一切始于信号。Linux 内核定义了一组信号，当进程执行非法操作时，内核会向其发送对应的信号。理解这些信号的含义和触发条件，是 NE 排查的基本功。

### 2.1 为什么要理解信号

拿到一份 tombstone，你首先看到的就是信号类型和 `si_code`。信号类型告诉你"发生了什么类别的错误"，`si_code` 进一步细化"具体是什么原因"。不理解信号，你连"问题方向"都无法判断。例如：

- `SIGSEGV + SEGV_MAPERR`：访问了一个完全未映射的地址——通常是空指针或野指针
- `SIGSEGV + SEGV_ACCERR`：地址有映射但权限不足——可能是写了只读内存（如代码段）
- `SIGABRT`：进程自己调用了 `abort()`——通常是检测到了内部一致性错误

### 2.2 信号定义源码

信号的数值定义位于内核头文件中：

```c
// kernel/include/uapi/asm-generic/signal.h

#define SIGHUP     1
#define SIGINT     2
#define SIGQUIT    3
#define SIGILL     4
#define SIGTRAP    5
#define SIGABRT    6
#define SIGBUS     7
#define SIGFPE     8
#define SIGKILL    9
#define SIGSEGV   11
#define SIGSYS    31
```

### 2.3 七种致命信号详解

以下是 Android Native Crash 中最常见的 7 种致命信号的完整参考表：

| 信号 | 编号 | 含义 | 典型触发场景 | si_code 子类型 |
| :--- | :---: | :--- | :--- | :--- |
| **SIGSEGV** | 11 | 段错误（Segmentation Fault） | 空指针解引用、野指针、缓冲区溢出 | `SEGV_MAPERR`(1): 地址未映射; `SEGV_ACCERR`(2): 权限不足 |
| **SIGABRT** | 6 | 进程主动中止 | `abort()`, `__fortify_fail()`, `CHECK()` 宏失败 | `SI_TKILL`(-6): `tgkill()`发送; `SI_USER`(0): `kill()`发送 |
| **SIGBUS** | 7 | 总线错误 | 未对齐的内存访问、映射文件被截断 | `BUS_ADRALN`(1): 对齐错误; `BUS_ADRERR`(2): 物理地址不存在; `BUS_OBJERR`(3): 硬件错误 |
| **SIGFPE** | 8 | 算术异常 | 整数除零、整数溢出（ARM 上较少见） | `FPE_INTDIV`(1): 整数除零; `FPE_INTOVF`(2): 整数溢出; `FPE_FLTDIV`(3): 浮点除零 |
| **SIGILL** | 4 | 非法指令 | 执行了 CPU 不支持的指令、代码段被损坏 | `ILL_ILLOPC`(1): 非法操作码; `ILL_ILLOPN`(2): 非法操作数; `ILL_PRVREG`(6): 特权寄存器 |
| **SIGSYS** | 31 | 非法系统调用 | seccomp 策略拦截了不允许的 syscall | `SYS_SECCOMP`(1): seccomp 触发 |
| **SIGTRAP** | 5 | 断点/陷阱 | 调试断点、`__builtin_trap()`、单步执行 | `TRAP_BRKPT`(1): 断点; `TRAP_TRACE`(2): 单步跟踪; `TRAP_HWBKPT`(4): 硬件断点 |

### 2.4 各信号与稳定性的关联

**SIGSEGV** 是 NE 中占比最大的信号（通常占 60-70%）。它的两个 `si_code` 子类型指向不同的排查方向：

- **SEGV_MAPERR**（地址未映射）：
  - `fault addr 0x0` ~ `0x1000`：空指针解引用（最常见）
  - `fault addr` 为一个明显不合理的值（如 `0xdeadbeef`）：内存已被释放后写入了 magic number（use-after-free）
  - `fault addr` 为一个合理但很大的值：可能是栈溢出或数组越界
- **SEGV_ACCERR**（权限不足）：
  - 尝试写入只读的 `.text` 段或 `.rodata` 段
  - 尝试执行数据段的内容（NX 保护触发）
  - mprotect 保护的内存区域被非法访问

**SIGABRT** 是占比第二大的信号（约 20-25%）。它意味着代码**主动决定终止进程**，通常是因为检测到了不可恢复的一致性错误。常见的触发源：

- `libc` 的 `fortify` 检查：如 `strcpy` 检测到缓冲区溢出
- `CHECK()` / `LOG(FATAL)` 宏：ART、libutils 等系统库中的断言失败
- `std::terminate()`：未捕获的 C++ 异常
- `fdsan`（Android 10+）：检测到文件描述符的 double-close 或 use-after-close

**SIGBUS** 在 Android 上常见于 mmap 映射的文件在运行时被截断或删除的场景（如应用更新过程中 so 文件被替换）。

**SIGSYS** 在 Android 8.0+ 的 seccomp 策略下变得更常见。当 Vendor HAL 或旧版 NDK 代码使用了 seccomp 黑名单中的系统调用时，会触发此信号。

---

## 3. 崩溃处理全链路

一个 Native Crash 从发生到最终被记录，会经过一条完整的处理链路。理解这条链路，你才能知道"tombstone 里的每一行信息从哪来"、"链路的哪个环节可能出问题导致崩溃日志丢失"。

### 3.1 全链路架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Native Crash 处理全链路                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ① 硬件异常                                                                 │
│  ┌───────────────┐                                                         │
│  │  CPU / MMU     │  非法内存访问 → 触发 Page Fault / Alignment Fault        │
│  └──────┬────────┘                                                         │
│         ▼                                                                   │
│  ② 内核信号产生                                                              │
│  ┌───────────────────────────────────────────┐                             │
│  │  kernel/signal.c                           │                             │
│  │  do_send_sig_info() → complete_signal()    │  内核将信号挂到目标线程        │
│  └──────┬────────────────────────────────────┘                             │
│         ▼                                                                   │
│  ③ 进程信号传递                                                              │
│  ┌───────────────────────────────────────────┐                             │
│  │  kernel/signal.c                           │                             │
│  │  get_signal() → 调用用户态 signal handler   │  从内核态返回用户态时检查      │
│  └──────┬────────────────────────────────────┘                             │
│         ▼                                                                   │
│  ④ debuggerd_handler（Bionic 层）                                           │
│  ┌───────────────────────────────────────────┐                             │
│  │  bionic/linker/debuggerd_handler.cpp       │                             │
│  │  debuggerd_signal_handler()                │  通过 socket 通知 crash_dump │
│  │  → clone() 子进程                          │                             │
│  └──────┬────────────────────────────────────┘                             │
│         ▼                                                                   │
│  ⑤ crash_dump 进程                                                          │
│  ┌───────────────────────────────────────────┐                             │
│  │  system/core/debuggerd/crash_dump.cpp      │                             │
│  │  ptrace(PTRACE_ATTACH) → 读取寄存器/内存    │  独立进程，防止崩溃进程污染    │
│  │  → libunwindstack 回溯堆栈                  │                             │
│  │  → 生成 Tombstone                          │                             │
│  └──────┬────────────────────────────────────┘                             │
│         ▼                                                                   │
│  ⑥ Tombstone 生成与存储                                                      │
│  ┌───────────────────────────────────────────┐                             │
│  │  /data/tombstones/tombstone_XX             │  循环写入（最多 32 个文件）     │
│  │  logd → logcat 输出 crash 摘要             │                             │
│  │  DropBoxManagerService 归档                │                             │
│  └──────┬────────────────────────────────────┘                             │
│         ▼                                                                   │
│  ⑦ 上报                                                                     │
│  ┌───────────────────────────────────────────┐                             │
│  │  APM SDK（如 xCrash/Breakpad/Firebase）     │  上报到后端平台进行聚合分析    │
│  └───────────────────────────────────────────┘                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 关键环节源码解析

#### 环节 ①②：从硬件异常到内核信号产生

当 CPU 执行到一条非法的内存访问指令（如解引用空指针 `*((int*)0) = 1`），MMU（内存管理单元）检测到虚拟地址 `0x0` 没有对应的物理页映射，触发 Page Fault 异常。内核的 Page Fault 处理程序判断这是一个不可恢复的错误，调用 `force_sig_fault()` 向当前线程发送 `SIGSEGV` 信号。

信号的发送核心函数位于：

```c
// kernel/kernel/signal.c

static int __send_signal(int sig, struct kernel_siginfo *info,
                         struct task_struct *t, enum pid_type type, bool force)
{
    struct sigpending *pending;
    struct sigqueue *q;

    // 将信号加入目标线程的 pending 队列
    pending = (type != PIDTYPE_PID) ? &t->signal->shared_pending : &t->pending;

    q = __sigqueue_alloc(sig, t, GFP_ATOMIC, override_rlimit);
    if (q) {
        list_add_tail(&q->list, &pending->list);
        copy_siginfo(&q->info, info);
    }

    // 设置信号位图
    sigaddset(&pending->signal, sig);

    // 唤醒目标线程来处理信号
    complete_signal(sig, t, type);
    return 0;
}
```

**稳定性架构师视角：** 信号是"挂"到目标线程的 pending 队列中的。如果目标线程正在内核态执行不可中断的操作（`TASK_UNINTERRUPTIBLE`），信号的处理会被延迟到该操作完成后。这就是为什么有时候崩溃日志的时间戳和实际触发时间有微小差异。

#### 环节 ③：用户态信号传递

当线程从内核态返回用户态时（如从系统调用返回或从中断返回），内核会检查是否有待处理的信号：

```c
// kernel/kernel/signal.c

bool get_signal(struct ksignal *ksig)
{
    struct sighand_struct *sighand = current->sighand;
    struct signal_struct *signal = current->signal;

    for (;;) {
        // 从 pending 队列取出待处理信号
        signr = dequeue_signal(current, &current->blocked, &ksig->info);

        ka = &sighand->action[signr - 1];

        if (ka->sa.sa_handler == SIG_DFL) {
            // 默认动作：对于 SIGSEGV/SIGABRT 等是终止进程并生成 core dump
            // ...
        } else {
            // 用户注册了 signal handler，设置用户态栈帧来执行 handler
            ksig->ka = *ka;
            break;
        }
    }
    return true;
}
```

**关键点：** 如果进程通过 `sigaction()` 注册了信号处理函数（如 Bionic 的 `debuggerd_handler`），内核不会直接杀死进程，而是在用户态栈上构造一个新的栈帧，让线程跳转到信号处理函数执行。这就是 Android 能够在进程死亡前生成 tombstone 的关键机制。

#### 环节 ④：debuggerd_handler（Bionic 层）

Bionic（Android 的 C 库）在进程启动时通过 `debuggerd_init()` 注册了一个信号处理函数。当致命信号到达时，该处理函数负责启动崩溃转储流程：

```cpp
// bionic/linker/debuggerd_handler.cpp

static void debuggerd_signal_handler(int signal_number, siginfo_t* info,
                                      void* context) {
    // 1. 保存崩溃现场信息
    debugger_thread_info thread_info = {
        .crashing_tid = __gettid(),
        .siginfo = info,
        .ucontext = static_cast<ucontext_t*>(context),
        .signal_number = signal_number,
    };

    // 2. 通过 clone() 创建一个子线程来处理崩溃
    //    不用 fork() 是因为崩溃进程的状态可能已不安全
    //    不用 pthread_create() 是因为它需要分配内存，在信号处理函数中不安全
    pid_t child_pid = clone(debuggerd_dispatch_pseudothread, ...,
                            CLONE_THREAD | CLONE_SIGHAND | ...);

    // 3. 等待子线程完成（通过 futex）
    futex_wait(&thread_info.pseudothread_tid, -1);

    // 4. 子线程内部：通过 socket 连接到 tombstoned 守护进程
    //    请求一个 tombstone 文件的 fd
    //    然后 exec() 启动 crash_dump 进程
}
```

**稳定性架构师视角：** 这里使用 `clone()` 而非 `fork()` 或 `pthread_create()` 是精心设计的。`fork()` 在多线程环境中可能导致死锁（如果其他线程持有 malloc 锁），`pthread_create()` 需要调用 malloc，而信号处理函数中调用 malloc 是不安全的（async-signal-unsafe）。`clone(CLONE_THREAD)` 创建的是同一线程组中的新线程，共享地址空间但不需要 malloc。

#### 环节 ⑤：crash_dump 进程

`crash_dump` 是一个独立的进程（通过 `exec()` 启动），它通过 `ptrace` 系统调用附着到崩溃进程，读取其寄存器和内存，进行堆栈回溯：

```cpp
// system/core/debuggerd/crash_dump.cpp

int main(int argc, char** argv) {
    // 1. ptrace attach 到崩溃进程的所有线程
    for (pid_t thread : threads) {
        ptrace(PTRACE_ATTACH, thread, 0, 0);
    }

    // 2. 读取崩溃线程的寄存器
    struct user_regs_struct regs;
    ptrace(PTRACE_GETREGS, crash_tid, 0, &regs);

    // 3. 使用 libunwindstack 进行堆栈回溯
    unwindstack::Unwinder unwinder(256, maps, regs, process_memory);
    unwinder.Unwind();

    // 4. 生成 tombstone 格式的输出
    engrave_tombstone(output_fd, unwinder, threads, ...);

    // 5. ptrace detach，让崩溃进程继续执行默认信号动作（终止）
    for (pid_t thread : threads) {
        ptrace(PTRACE_DETACH, thread, 0, 0);
    }
}
```

**稳定性架构师视角：** `crash_dump` 作为独立进程运行有一个关键优势——它不受崩溃进程的污染。即使崩溃进程的堆已经损坏、栈已经溢出，`crash_dump` 运行在自己的干净地址空间中，能安全地通过 `ptrace` 读取崩溃进程的内存。但这也意味着 `crash_dump` 只能看到崩溃进程的原始内存内容，无法调用崩溃进程中的任何函数（如 C++ 的 demangling）。

### 3.3 链路中的稳定性风险

整条链路中有多个环节可能出问题，导致崩溃日志丢失或不完整：

| 环节 | 可能的问题 | 后果 |
| :--- | :--- | :--- |
| 信号处理函数被覆盖 | 第三方 SDK 通过 `sigaction()` 覆盖了 Bionic 的 handler | tombstone 无法生成 |
| `clone()` 失败 | 进程的线程数已达内核限制 | 信号处理函数直接返回，进程被默认动作杀死，无 tombstone |
| tombstoned 连接失败 | tombstoned 守护进程未运行或 socket 繁忙 | crash_dump 无法获得输出 fd |
| ptrace 被拒绝 | SELinux 策略或 `prctl(PR_SET_DUMPABLE, 0)` 阻止 ptrace | crash_dump 无法读取崩溃进程内存 |
| unwind 失败 | 栈被破坏、.eh_frame 信息缺失 | tombstone 中堆栈为空或截断 |
| tombstone 文件被轮转 | 32 个 tombstone 文件槽位已满，旧的被覆盖 | 历史崩溃信息丢失 |

---

## 4. NE 在 Android 各层的分布

Native Crash 并非只发生在应用的 NDK 代码中。事实上，Android 系统从应用层到内核层的每一层都可能产生 NE。理解 NE 在各层的分布特征，能帮助你在拿到 tombstone 的第一时间判断"这是谁的问题"。

### 4.1 各层分布概览

```
┌─────────────────────────────────────────────────────────────┐
│  App NDK Code（应用自己的 .so）                              │  ~35%
│  例: libgame.so, libjpeg-turbo.so, libsqlite_custom.so      │
├─────────────────────────────────────────────────────────────┤
│  ART Internal（libart.so, libart-compiler.so）               │  ~15%
│  例: JIT 编译器 bug, GC 堆损坏, JNI 引用表溢出               │
├─────────────────────────────────────────────────────────────┤
│  System Libraries（libutils.so, libbinder.so, libhwui.so）   │  ~20%
│  例: Binder 通信异常, RenderThread 崩溃, media codec crash    │
├─────────────────────────────────────────────────────────────┤
│  Vendor HAL（libcamera_hal.so, libgralloc.so, 各种 hw/*.so） │  ~25%
│  例: Camera HAL 崩溃, GPU 驱动崩溃, Sensor HAL 超时           │
├─────────────────────────────────────────────────────────────┤
│  Kernel（oops/panic → 不走 tombstone 流程，走 ramoops/pstore）│  ~5%
│  例: 内核空指针, use-after-free, 驱动 bug                     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 如何通过 Backtrace 快速判断层级

拿到 tombstone 后，快速扫描 backtrace 中出现的 so 库名称，就能判断崩溃属于哪一层：

| backtrace 中的库名 | 所属层级 | 归责方向 |
| :--- | :--- | :--- |
| `libXXX.so`（App 自带，位于 `/data/app/` 下） | App NDK | 应用开发者/第三方 SDK |
| `libart.so`, `libart-compiler.so` | ART Internal | ART 虚拟机团队 |
| `libhwui.so`, `libandroid_runtime.so` | Framework Native | Framework 团队 |
| `libbinder.so`, `libutils.so`, `libcutils.so` | System Libraries | 系统库团队 |
| `libEGL_xxx.so`, `libGLES_xxx.so`, `gralloc.xxx.so` | Vendor HAL (GPU) | SoC 厂商 (Qualcomm/MTK/...) |
| `camera.xxx.so`, `sensors.xxx.so` | Vendor HAL (Sensor/Camera) | SoC 厂商 |
| `[kernel address]`, `[vdso]` | Kernel | 内核/驱动团队 |

**实用判断技巧：**

1. **看崩溃地址的前缀**：`/data/app/` 开头 → App层；`/system/lib64/` → 系统层；`/vendor/lib64/` → Vendor层
2. **看崩溃线程名**：`RenderThread` → 很可能是 `libhwui.so` 或 GPU 驱动；`Binder:XXX` → Binder 通信相关；`Signal Catcher` → ART 内部信号处理
3. **看 `abort message`**：如果有 `abort message`，直接搜索这个字符串，它通常来自 `LOG(FATAL)` 或 `CHECK()` 宏，能直接定位到出错的源码位置

---

## 5. 与 ART 的交互

NE 与 ART 之间有着密切且微妙的关系。ART 自身就大量使用 Linux 信号来实现性能优化，这使得 NE 的处理变得更加复杂。

### 5.1 ART 的 FaultHandler：信号的"拦路者"

**为什么 ART 要拦截信号？**

ART 利用硬件异常来实现两个重要的性能优化：

1. **隐式空指针检查（Implicit Null Check）**：Java 代码 `obj.field` 的正常做法是先检查 `obj != null`，但这意味着每次字段访问都要多一条比较指令。ART 的优化策略是直接尝试访问——如果 `obj` 为 null，CPU 会触发 `SIGSEGV`，ART 的 `FaultHandler` 拦截后将其转换为 Java 层的 `NullPointerException`。
2. **隐式栈溢出检查（Implicit Stack Overflow Check）**：在线程栈底部设置不可访问的 Guard Page，当栈增长到越过 Guard Page 时触发 `SIGSEGV`，ART 将其转换为 `StackOverflowError`。

核心源码位于 `art/runtime/fault_handler.cc`：

```cpp
// art/runtime/fault_handler.cc

void FaultManager::HandleFault(int sig, siginfo_t* info, void* context) {
    // 1. 获取崩溃地址
    uintptr_t fault_addr = reinterpret_cast<uintptr_t>(info->si_addr);

    // 2. 检查崩溃地址是否在 ART 管理的区域内
    //    如果是，尝试将其转换为 Java 异常
    for (const auto& handler : generated_code_handlers_) {
        if (handler->Action(sig, info, context)) {
            return;  // 信号已被 ART 处理（转为 Java 异常），不再传递
        }
    }

    // 3. 不是 ART 可处理的情况，传递给信号链中的下一个 handler
    //    最终会到达 debuggerd_handler，生成 tombstone
}

// NullPointerHandler: 处理隐式空指针检查
bool NullPointerHandler::Action(int sig, siginfo_t* info, void* context) {
    // 检查 fault_addr 是否在低地址区域（通常 < 4KB，即 null 附近）
    // 并且 PC 在 ART 编译的代码中
    uintptr_t fault_addr = reinterpret_cast<uintptr_t>(info->si_addr);
    if (IsInGeneratedCode(context) && fault_addr < kPageSize) {
        // 修改 context 中的 PC，让线程跳转到 NullPointerException 的抛出逻辑
        SetRegister(context, PC_REG, art_quick_throw_null_pointer);
        return true;
    }
    return false;
}
```

**稳定性架构师视角：** `FaultHandler` 的判断逻辑如果出错（误判了信号来源），会导致两种严重后果：
- **False Positive**：本应是真正的 Native Crash 被错误地当成 Java `NullPointerException`，掩盖了 Native 层的 bug
- **False Negative**：本应转为 `NullPointerException` 的信号未被拦截，变成了 Native Crash，增加了 NE 的噪音

### 5.2 sigchain：信号链管理

**为什么需要 sigchain？**

一个 Android 进程中可能有多个组件都想注册同一个信号的处理函数：ART 的 `FaultHandler` 要拦截 `SIGSEGV`，APM 框架（如 xCrash/Breakpad）也要拦截 `SIGSEGV` 来捕获 Native Crash。但 `sigaction()` 是覆盖式的——后注册的会覆盖先注册的。

ART 提供了 `sigchain` 库来解决这个问题。它劫持了 `sigaction()` 系统调用，实现了一个信号处理函数的链式管理：

```cpp
// art/sigchain/sigchain.cc

// 替代 libc 的 sigaction，实现链式管理
extern "C" int sigaction(int signal, const struct sigaction* new_action,
                          struct sigaction* old_action) {
    // 如果是 ART 关注的信号，将 new_action 添加到链中
    // 而不是直接覆盖
    SignalChain& chain = GetChain(signal);

    if (old_action) {
        *old_action = chain.GetCurrentAction();
    }
    if (new_action) {
        chain.SetUserAction(*new_action);
    }
    return 0;
}

// ART 注册自己的 handler 为"特殊 handler"，优先级最高
void AddSpecialSignalHandlerFn(int signal, SigchainAction* sa) {
    SignalChain& chain = GetChain(signal);
    chain.AddSpecialHandler(sa);
    // 确保 ART 的 handler 永远第一个被调用
}
```

**信号处理顺序：**

```
信号到达
  ↓
sigchain 分发
  ↓
① ART FaultHandler（Special Handler）
  → 如果是隐式空指针/栈溢出，转为 Java 异常，信号消化
  → 否则，传递给下一个 handler
  ↓
② APM 框架 Handler（User Handler，如 xCrash）
  → 记录崩溃信息、采集现场数据
  → 调用之前的 handler 或重新抛出信号
  ↓
③ Bionic debuggerd_handler
  → 启动 crash_dump，生成 tombstone
```

### 5.3 APM 框架与 ART 信号处理的冲突

这是 Android 稳定性领域的经典"坑"。APM 框架通常在 App 初始化时注册自己的 `SIGSEGV` handler，但如果注册方式不当，会干扰 ART 的 `FaultHandler`：

| 场景 | 原因 | 后果 |
| :--- | :--- | :--- |
| APM 直接用 `sigaction()` 注册 | 如果 sigchain 未被正确加载，APM 的 handler 会覆盖 ART 的 | ART 的隐式空指针检查失效，所有 `NullPointerException` 变成 NE |
| APM handler 中不调用 `old_handler` | 信号链断裂，后续 handler 无法执行 | debuggerd_handler 无法执行，tombstone 无法生成 |
| APM handler 中执行 async-signal-unsafe 操作 | 如 `malloc()`、`printf()` | 信号处理函数中死锁或二次崩溃 |

---

## 6. 核心源码目录

作为稳定性架构师，你需要知道 NE 相关的源码"藏"在哪里。以下是 AOSP 中 NE 排查最常涉及的源码目录：

| 源码目录 | 核心职责 | 关键文件 |
| :--- | :--- | :--- |
| `system/core/debuggerd/` | **崩溃处理框架**。tombstoned 守护进程、crash_dump 工具、tombstone 格式化 | `crash_dump.cpp`, `tombstoned.cpp`, `tombstone_handler.cpp` |
| `bionic/linker/` | **动态链接器 + debuggerd handler 注册** | `debuggerd_handler.cpp`, `linker_main.cpp` |
| `bionic/libc/bionic/` | **信号相关 libc 实现** | `sigaction.cpp`, `abort.cpp`, `pthread_create.cpp` |
| `system/core/libunwindstack/` | **堆栈回溯库**。解析 `.eh_frame`/`.debug_frame` 段进行 unwinding | `Unwinder.cpp`, `ElfInterface.cpp`, `DwarfSection.cpp` |
| `art/runtime/` | **ART 运行时**。FaultHandler、Thread、信号处理 | `fault_handler.cc`, `thread.cc`, `runtime.cc` |
| `art/sigchain/` | **信号链管理** | `sigchain.cc` |
| `kernel/kernel/signal.c` | **内核信号子系统** | `signal.c`（信号发送、传递、处理） |
| `kernel/arch/arm64/kernel/` | **ARM64 异常处理入口** | `entry.S`（异常向量表）, `traps.c`, `fault.c` |
| `system/core/liblog/` | **日志库**。崩溃日志写入 logd | `logger_write.cpp` |
| `frameworks/base/services/core/` | **DropBoxManagerService**。归档 tombstone 和 ANR trace | `DropBoxManagerService.java` |

**实用建议：** 在本地 AOSP 源码中建立以下 bookmark（收藏），遇到 NE 问题时能快速定位：

1. **`bionic/linker/debuggerd_handler.cpp`** — 理解信号是如何被拦截的
2. **`system/core/debuggerd/crash_dump.cpp`** — 理解 tombstone 是如何生成的
3. **`system/core/libunwindstack/Unwinder.cpp`** — 理解堆栈是如何回溯的
4. **`art/runtime/fault_handler.cc`** — 理解 ART 如何"偷走"了你的 SIGSEGV
5. **`kernel/kernel/signal.c`** — 理解信号从产生到传递的完整流程

---

## 7. 稳定性实战案例

### 案例一：APM 框架导致海量 NullPointerException 变成 Native Crash

**现象：**

某应用版本上线后，后端 NE 上报量突增 300%，信号类型全部为 `SIGSEGV (SEGV_MAPERR)`，`fault addr` 集中在 `0x0` ~ `0x100` 的低地址区间。与此同时，Java 层的 `NullPointerException` 上报量骤降。

**分析思路：**

1. **低地址 SIGSEGV 的特征**：`fault addr` 在 `0x0` ~ `0x100` 范围内，这是典型的空指针解引用特征（访问 `null` 对象的字段，字段偏移通常不大）。正常情况下，这些应该被 ART 的 `FaultHandler` 拦截并转为 `NullPointerException`。
2. **NE 增 + NPE 降 = 信号链被破坏**：ART 的 `FaultHandler` 未能优先处理 SIGSEGV，导致信号直接流向了 debuggerd_handler。
3. **排查信号注册顺序**：检查应用初始化代码，发现新版本集成了一个 APM SDK，该 SDK 在 `JNI_OnLoad` 中直接调用了 POSIX 的 `sigaction()` 注册了自己的 `SIGSEGV` handler，并且 **没有保存和回调之前的 handler（old_action）**。
4. **验证**：在 sigchain 的 `sigaction()` 包装函数中加日志，确认 APM SDK 的注册确实覆盖了 ART 的处理链。

**根因：**

APM SDK 绕过 sigchain 直接调用了 libc 的 `__sigaction()`（通过 `dlsym(RTLD_NEXT, "sigaction")` 获取），破坏了 ART 的信号链。ART 的 `FaultHandler` 不再是第一个收到 `SIGSEGV` 的 handler，导致隐式空指针检查机制失效。

**修复方案：**

1. **短期修复**：升级 APM SDK 到支持 sigchain 的版本，确保 handler 注册通过 sigchain 管理的 `sigaction()` 进行。
2. **长期防护**：
   - 在 CI 中增加检查：扫描所有集成的 so 库的符号表，如果发现直接引用了 `__sigaction` 或通过 `dlsym` 获取 `sigaction`，发出警告。
   - 在应用启动完成后，验证 sigchain 的信号链完整性（检查 `SIGSEGV` 的当前 handler 是否仍然是 sigchain 的 dispatcher）。

```
修复前后对比：
┌──────────────┬───────────┬───────────┐
│ 指标          │ 修复前     │ 修复后     │
├──────────────┼───────────┼───────────┤
│ NE 日均量     │ 12,000    │ 3,000     │
│ NPE 日均量    │ 500       │ 9,500     │
│ 总异常量      │ 12,500    │ 12,500    │
└──────────────┴───────────┴───────────┘
```

总异常量不变，证实了这些 NE 实际上是被错误分类的 NPE。

---

### 案例二：Vendor HAL 中的 Use-After-Free 导致 Camera 进程周期性崩溃

**现象：**

线上部分机型（特定芯片平台）用户反馈"打开相机闪退"，后端聚类发现 `cameraserver` 进程高频崩溃，tombstone 信号为 `SIGSEGV (SEGV_MAPERR)`，`fault addr` 为一些看似随机的大地址值（非低地址空指针）。Backtrace 最顶部帧为 `libcamera_hal.so`：

```
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x7a3f012340
    #00 pc 0x0004a2bc  /vendor/lib64/libcamera_hal.so (CameraDevice::processRequest+188)
    #01 pc 0x0004b890  /vendor/lib64/libcamera_hal.so (RequestThread::threadLoop+240)
    #02 pc 0x00012f64  /system/lib64/libutils.so (android::Thread::_threadLoop+280)
```

**分析思路：**

1. **fault addr 随机且为大地址**：排除空指针（空指针 fault addr 通常在 `0x0` ~ `0xFFF`）。随机大地址通常意味着指针指向的内存已被释放并被其他分配占用（use-after-free）或未初始化。
2. **通过 addr2line 还原符号**：使用未剥离的 `libcamera_hal.so` 进行地址翻译：
   ```
   $ addr2line -Cfe libcamera_hal.so 0x0004a2bc
   CameraDevice::processRequest(CaptureRequest*)
   camera_device.cpp:342
   ```
3. **代码审查**：在 `camera_device.cpp:342` 处，代码通过一个 `std::shared_ptr<StreamBuffer>` 访问 buffer 对象。但进一步审查发现，该 `shared_ptr` 是从一个 `std::vector` 中通过裸指针缓存的引用获取的，而 `vector` 在另一个线程中会执行 `resize()` 操作，导致迭代器/指针失效。
4. **使用 ASan 复现**：编译 ASan（AddressSanitizer）版本的 `libcamera_hal.so`，复现后 ASan 报告精确定位：
   ```
   ==12345==ERROR: AddressSanitizer: heap-use-after-free on address 0x7a3f012340
   READ of size 8 at 0x7a3f012340 thread T5 (RequestThread)
   freed by thread T3 (ConfigThread) here:
       #0 operator delete(void*)
       #1 std::vector<StreamBuffer>::_M_realloc_insert(...)
       #2 ConfigThread::reconfigureStreams(...)
   ```

**根因：**

`RequestThread` 持有了指向 `vector<StreamBuffer>` 内部元素的裸指针。当 `ConfigThread` 调用 `reconfigureStreams()` 触发 `vector::resize()` 时，`vector` 内部存储重新分配，旧的内部数组被释放。`RequestThread` 随后通过已失效的裸指针访问被释放的内存，触发 `SIGSEGV`。

**修复方案：**

1. **短期修复**：将 `vector` 替换为预分配的固定大小数组，避免 `resize()` 导致的内存重分配。或使用 `std::shared_ptr` 管理 `StreamBuffer`，确保对象生命周期安全。
2. **长期治理**：
   - 在 Vendor HAL 的编译配置中默认开启 `-fsanitize=address` 用于内部测试构建
   - 推动 HAL 层使用 `HWASan`（Hardware-assisted ASan）进行持续的内存安全测试
   - 在 CameraService 层增加 `cameraserver` 进程崩溃后的自动重启和状态恢复逻辑，降低用户感知

```
修复前后对比：
┌──────────────────────┬───────────┬───────────┐
│ 指标                  │ 修复前     │ 修复后     │
├──────────────────────┼───────────┼───────────┤
│ Camera NE 日均崩溃量  │ 2,800     │ 12        │
│ "相机闪退" 用户投诉   │ 350/天    │ 5/天      │
│ Camera HAL 重启次数   │ 3,200/天  │ 15/天     │
└──────────────────────┴───────────┴───────────┘
```

---

## 8. 总结

本篇从"定义 → 信号 → 链路 → 分布 → ART 交互 → 源码目录"六个维度，建立了 Native Crash 的全局认知。

核心要点：

1. **NE 是信号驱动的进程级致命错误**，与 Java Exception 有着本质区别——它没有虚拟机安全网，一旦发生就是进程死亡。
2. **7 种致命信号各有含义**，其中 `SIGSEGV` 占比最大（60-70%），`si_code` 子类型直接决定排查方向。
3. **崩溃处理链路从硬件异常到 tombstone 生成要经过 7 个环节**，每个环节都可能成为崩溃日志丢失的原因。
4. **通过 backtrace 中的 so 库名和路径前缀**，可以在 10 秒内判断崩溃属于哪一层、应该找谁。
5. **ART 的 FaultHandler 和 sigchain 是 NE 领域最微妙的机制**——它们将部分 SIGSEGV "偷走"转化为 Java 异常，APM 框架如果不尊重这个机制就会引发混乱。
6. **掌握核心源码目录的位置**，是从"看 tombstone"进阶到"读源码定位根因"的关键一步。

在接下来的文章中，我们将逐步深入 NE 的每一个子领域：Tombstone 的解读与自动化分析、堆栈回溯原理（libunwindstack）、内存破坏检测工具（ASan/HWASan/MTE）、以及 NE 的体系化治理方案。
