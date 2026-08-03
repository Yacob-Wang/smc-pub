# 02-Linux 信号机制：从硬件异常到用户态回调

每一个 Native Crash 的本质，都是一个**信号（Signal）**。当你在 Tombstone 中看到 `signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0`——这行信息的每一个字段，都来自 Linux 信号机制。如果你不理解信号是如何产生、传递、捕获的，那 Tombstone 在你眼中就只是一堆神秘的数字。

本篇将从信号的本质出发，沿着"产生 → 传递 → 处理"的生命周期，逐层拆解内核源码中的关键路径，并最终落到 Android 特有的 sigchain 机制——它是 ART、APM 框架、debuggerd 三方信号处理共存的基石。

---

## 1. 信号是什么

### 1.1 为什么需要信号

在操作系统中，进程是一个"独立王国"——它有自己的地址空间、文件描述符表、线程。但操作系统需要一种机制来**异步地通知进程发生了某个事件**，比如：

- 进程访问了非法内存地址（硬件 MMU 报错）
- 用户在终端按了 `Ctrl+C`（终端中断）
- 子进程退出了（父进程需要收尸）
- 定时器到期了（闹钟响了）

这些事件的发生时机是不可预测的，进程不可能一直轮询"有没有异常发生"。操作系统的解决方案是**信号（Signal）**——一种**软件层面的中断机制**。

**用一句话定义：** 信号是 Linux 内核向用户态进程发送的异步通知，告知进程发生了某个需要处理的事件。

你可以把信号类比为现实生活中的"紧急通知"：你正在办公室写代码（正常执行流），突然消防警报响了（信号到达），你必须放下手头的工作去执行逃生流程（Signal Handler），逃生完毕后回到工位继续写代码（从 Handler 返回）。

### 1.2 标准信号与实时信号

Linux 信号分为两大类：

| 分类 | 信号编号 | 特点 | 典型代表 |
| :--- | :--- | :--- | :--- |
| **标准信号（Standard Signals）** | 1-31 | 不排队（同一信号多次发送只保留一个）；语义由 POSIX 标准定义 | SIGSEGV(11), SIGABRT(6), SIGKILL(9), SIGBUS(7) |
| **实时信号（Real-time Signals）** | 32-64 | 排队（每次发送都保留）；可携带额外数据；先进先出 | SIGRTMIN(32) - SIGRTMAX(64) |

**稳定性关联：** Native Crash 几乎只涉及标准信号（SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL / SIGSYS / SIGTRAP）。实时信号在 Android 中主要被 Bionic 的线程实现内部使用（如 `SIGRTMIN+0` 用于 `pthread_cancel`），APM 框架一般不需要关心。

### 1.3 7 种致命信号速览

在 Android Native Crash 的语境下，以下 7 种信号是"致命"的——默认行为是终止进程并生成 core dump（在 Android 上即 Tombstone）：

| 信号 | 编号 | 触发原因 | Tombstone 中的典型特征 |
| :--- | :--- | :--- | :--- |
| **SIGSEGV** | 11 | 访问非法内存地址（空指针、野指针、越界） | `fault addr 0x0`（空指针）或随机地址（野指针） |
| **SIGABRT** | 6 | 进程主动调用 `abort()`（断言失败、堆损坏检测） | backtrace 中有 `abort` → `raise` → `tgkill` |
| **SIGBUS** | 7 | 内存对齐错误、mmap 文件被截断 | `fault addr` 指向一个合法的映射区域 |
| **SIGFPE** | 8 | 算术错误（整数除零） | `si_code = FPE_INTDIV` |
| **SIGILL** | 4 | 执行非法指令（ABI 不兼容、代码段损坏） | `si_code = ILL_ILLOPC` |
| **SIGSYS** | 31 | 调用了被 seccomp 禁止的系统调用 | `si_code = SYS_SECCOMP`, `si_syscall = <syscall_nr>` |
| **SIGTRAP** | 5 | 断点、`__builtin_trap()`、`ptrace` 单步 | 调试场景或 `CHECK` 宏触发 |

### 1.4 信号的生命周期

一个信号从诞生到被处理，经历四个阶段：

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Generate  │────►│ Pending  │────►│ Deliver  │────►│ Handle   │
│ 产生      │     │ 挂起      │     │ 传递      │     │ 处理      │
│           │     │           │     │           │     │           │
│ 硬件异常   │     │ 信号挂在   │     │ 内核检查   │     │ 三种选择: │
│ kill()    │     │ 进程/线程  │     │ 是否阻塞   │     │ · 默认    │
│ abort()   │     │ 的 pending │     │ 未阻塞则   │     │ · 忽略    │
│ 内核事件   │     │ 队列中     │     │ 传递给进程 │     │ · 自定义  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
```

- **Generate（产生）：** 内核或其他进程产生一个信号，设置目标进程/线程的 pending 位。
- **Pending（挂起）：** 信号挂在目标的 pending 队列中，等待被传递。如果目标正在阻塞该信号，信号就一直 pending。
- **Deliver（传递）：** 当进程从内核态返回用户态时（系统调用返回、中断返回），内核检查 pending 信号，如果未被阻塞则传递。
- **Handle（处理）：** 进程执行对应的处理动作——默认行为（通常是终止）、忽略、或用户注册的自定义 Handler。

**稳定性关联：** 理解这四个阶段至关重要。APM 框架的工作原理就是在 Handle 阶段注册自定义 Handler，在进程被杀之前抢先收集崩溃信息。而信号掩码（signal mask）操作的是 Deliver 阶段——被 mask 的信号永远到不了 Handle 阶段。

---

## 2. 信号的产生

### 2.1 三种来源

信号不会凭空出现。它的产生有且仅有三种来源，每种来源的排查方向完全不同：

```
                     ┌─────────────────┐
                     │   信号的产生      │
                     └────────┬────────┘
               ┌──────────────┼──────────────┐
               ▼              ▼              ▼
       ┌──────────────┐ ┌──────────┐ ┌────────────┐
       │ 硬件异常      │ │ 软件触发  │ │ 内核事件    │
       │              │ │          │ │            │
       │ CPU/MMU 检测  │ │ kill()   │ │ 子进程退出  │
       │ 到非法操作    │ │ abort()  │ │ 管道断裂    │
       │ → 陷入内核    │ │ raise()  │ │ Alarm 超时  │
       │ → 发送信号    │ │ tgkill() │ │ seccomp 拦截│
       └──────────────┘ └──────────┘ └────────────┘
       SIGSEGV,SIGBUS    SIGABRT      SIGPIPE,SIGCHLD
       SIGFPE,SIGILL     任意信号      SIGSYS
```

### 2.2 来源一：硬件异常

这是 SIGSEGV、SIGBUS、SIGFPE、SIGILL 的产生路径。CPU 在执行指令时检测到非法操作，触发硬件异常（Exception），陷入内核态，内核再将硬件异常转换为对应的信号。

以最常见的 SIGSEGV 为例，完整路径如下：

```
用户代码: int *p = NULL; *p = 42;
    │
    ▼
CPU 执行 store 指令，访问地址 0x0
    │
    ▼
MMU 查页表，发现地址 0x0 没有映射
    │
    ▼
MMU 触发 Page Fault 异常（ARM64: Synchronous Abort）
    │
    ▼
CPU 陷入内核态，跳转到异常向量表
    │
    ▼
内核: do_mem_abort() → do_page_fault() → __do_page_fault()
    │
    ▼
内核发现这不是合法的缺页（地址不在任何 VMA 中）
    │
    ▼
调用 force_sig_fault(SIGSEGV, SEGV_MAPERR, fault_addr)
    │
    ▼
信号挂到目标线程的 pending 队列
```

**源码路径：** `arch/arm64/mm/fault.c`

```c
// arch/arm64/mm/fault.c
static int __kprobes do_page_fault(unsigned long far, unsigned long esr,
                                   struct pt_regs *regs)
{
    struct vm_area_struct *vma;
    struct mm_struct *mm = current->mm;
    unsigned long addr = untagged_addr(far);

    // 查找地址所在的 VMA（Virtual Memory Area）
    vma = find_vma(mm, addr);

    if (unlikely(!vma)) {
        // 地址不在任何 VMA 中 → SEGV_MAPERR（映射不存在）
        fault = VM_FAULT_BADMAP;
        goto bad_area;
    }

    if (unlikely(vma->vm_start > addr)) {
        // 地址在 VMA 的 gap 中 → SEGV_MAPERR
        fault = VM_FAULT_BADMAP;
        goto bad_area;
    }

    // 检查权限：尝试写入只读区域 → SEGV_ACCERR（权限不足）
    if (!(vma->vm_flags & vm_flags)) {
        fault = VM_FAULT_BADACCESS;
        goto bad_area;
    }

    // ...

bad_area:
    __do_user_fault(far, esr, regs);
}

static void __do_user_fault(unsigned long far, unsigned long esr,
                            struct pt_regs *regs)
{
    // 根据 fault 类型确定 si_code
    int si_code = cycled_fault ? SEGV_MAPERR : SEGV_ACCERR;

    // 向当前线程发送 SIGSEGV
    force_sig_fault(SIGSEGV, si_code, (void __user *)far);
}
```

**稳定性架构师视角：**
- `SEGV_MAPERR`（code 1）表示访问的地址根本不存在映射——空指针（fault addr 接近 0x0）、野指针（fault addr 是随机值）、Use-After-Free（内存已被释放，VMA 可能已回收）都属于这一类。
- `SEGV_ACCERR`（code 2）表示映射存在但权限不匹配——写只读内存（如修改 `.rodata`）、执行不可执行内存（NX/DEP 保护）。
- 这两个 `si_code` 的区分是 Tombstone 排查的**第一个分叉点**：code 1 往往是内存安全问题，code 2 往往是权限/保护问题。

### 2.3 来源二：软件触发

软件触发的信号来自用户态的系统调用，最典型的是 `kill()` 和 `abort()`。

```c
// 向指定进程发送信号
kill(pid, SIGTERM);

// abort() 的实现本质上是向自己发送 SIGABRT
// bionic/libc/bionic/abort.cpp
void abort() {
    // 先尝试用已注册的 Handler 处理
    raise(SIGABRT);
    // 如果 Handler 返回了（没有终止进程），强制发送不可捕获的 SIGABRT
    sigset_t mask;
    sigfillset(&mask);
    sigdelset(&mask, SIGABRT);
    sigprocmask(SIG_SETMASK, &mask, NULL);
    raise(SIGABRT);
    _exit(127);  // 如果还没死，强制退出
}
```

**源码路径：** `kernel/signal.c` 中的 `send_signal` 是所有信号产生的汇聚点。

```c
// kernel/signal.c
static int send_signal(int sig, struct kernel_siginfo *info,
                       struct task_struct *t, enum pid_type type)
{
    struct sigpending *pending;

    // 决定信号挂到进程级还是线程级的 pending 队列
    pending = (type != PIDTYPE_PID) ? &t->signal->shared_pending
                                    : &t->pending;

    // 标准信号：检查是否已经 pending，如果是则丢弃（不排队）
    if (legacy_queue(pending, sig))
        return 0;

    // 分配 sigqueue 结构体，填充 siginfo
    q = __sigqueue_alloc(sig, t, GFP_ATOMIC, override_rlimit);
    if (q) {
        list_add_tail(&q->list, &pending->list);
        // 将 siginfo 复制到 sigqueue 中（包含 si_signo, si_code, si_addr 等）
        copy_siginfo(&q->info, info);
    }

    // 设置 pending 位图
    sigaddset(&pending->signal, sig);

    // 唤醒目标线程（如果它正在睡眠）
    complete_signal(sig, t, type);

    return 0;
}
```

**这段代码揭示了一个关键行为：** `legacy_queue()` 对标准信号做了去重——如果同一个标准信号已经在 pending 队列中，新来的信号直接丢弃。这意味着如果你在短时间内对同一个进程发送了 10 次 SIGSEGV，进程只会收到 1 次。但实时信号不会被丢弃，它们严格排队。

### 2.4 来源三：内核事件

内核在检测到某些事件时，会主动向进程发送信号：

| 内核事件 | 产生的信号 | Android 场景 |
| :--- | :--- | :--- |
| 子进程退出 | `SIGCHLD` | Zygote fork 的子进程（App）崩溃时，Zygote 收到 SIGCHLD |
| 写入已关闭的管道/Socket | `SIGPIPE` | Binder 通信对端进程死亡时 |
| seccomp 拦截到禁止的系统调用 | `SIGSYS` | Android 8.0+ 的 seccomp 沙箱拦截非法 syscall |
| 定时器到期 | `SIGALRM` | Watchdog 超时检测 |

**稳定性关联：** `SIGSYS` 是 Android 8.0 引入 seccomp 策略后新出现的信号类型。如果你的 NDK 代码调用了被禁止的系统调用（如直接调用 `swapon`、`reboot` 等），会收到 SIGSYS 而不是 `EPERM` 错误码。Tombstone 中会包含 `si_syscall` 字段，告诉你是哪个系统调用被拦截了。

---

## 3. 信号的传递

### 3.1 传递的时机

信号不是"立即"送达进程的。它只是被挂在 pending 队列中。内核在以下时机检查 pending 信号并传递：

1. **系统调用返回用户态时**
2. **中断/异常处理完毕返回用户态时**
3. **进程被调度器选中、即将返回用户态执行时**

这三个时机有一个共同点：**都是在从内核态切换到用户态的边界上**。内核在这个"关卡"上检查信号，决定是正常返回用户代码，还是改道去执行 Signal Handler。

**源码路径：** `arch/arm64/kernel/signal.c`

```c
// arch/arm64/kernel/entry-common.c (ARM64 的系统调用返回路径)
static void do_notify_resume(struct pt_regs *regs, unsigned long thread_flags)
{
    if (thread_flags & _TIF_SIGPENDING) {
        // 有信号 pending → 进入信号处理流程
        do_signal(regs);
    }

    if (thread_flags & _TIF_NOTIFY_RESUME) {
        resume_user_mode_work(regs);
    }
}
```

### 3.2 do_signal：信号传递的核心路径

当内核发现有 pending 信号时，进入 `do_signal()` → `get_signal()` → `handle_signal()` 的处理链。

```
do_signal(regs)
    │
    ├─ get_signal(&ksig)           // 从 pending 队列取出一个待处理的信号
    │   ├─ dequeue_signal()        // 按优先级出队
    │   ├─ 检查信号的处理方式:
    │   │   ├─ SIG_IGN → 忽略，继续取下一个
    │   │   ├─ SIG_DFL → 执行默认行为（终止/停止/忽略/core dump）
    │   │   └─ 用户自定义 Handler → 返回该 Handler 信息
    │   └─ 返回 ksig（包含 siginfo + sigaction）
    │
    └─ handle_signal(&ksig, regs)  // 设置用户态栈帧，准备执行 Handler
        ├─ setup_rt_frame()        // 在用户栈上构造 sigframe
        ├─ 修改 regs->pc = Handler 地址
        ├─ 修改 regs->sp = sigframe 顶部
        └─ 返回用户态 → CPU 跳转到 Handler 执行
```

**源码路径：** `arch/arm64/kernel/signal.c`

```c
// arch/arm64/kernel/signal.c
static void do_signal(struct pt_regs *regs)
{
    struct ksignal ksig;

    // 从 pending 队列中取出一个需要处理的信号
    if (get_signal(&ksig)) {
        // 有用户注册的 Handler → 设置栈帧让用户态去执行
        handle_signal(&ksig, regs);
        return;
    }

    // 没有需要处理的信号 → 恢复原始返回路径
    restore_saved_sigmask();
}
```

### 3.3 get_signal：信号出队与默认行为

`get_signal()` 是信号传递的"决策中心"。它决定了一个信号最终的命运。

**源码路径：** `kernel/signal.c`

```c
// kernel/signal.c
bool get_signal(struct ksignal *ksig)
{
    struct sighand_struct *sighand = current->sighand;
    struct signal_struct *signal = current->signal;

    for (;;) {
        struct k_sigaction *ka;

        // 按优先级从 pending 队列取出信号
        // 先检查线程级 pending，再检查进程级 pending
        signr = dequeue_signal(current, &current->blocked,
                               &ksig->info, &type);
        if (!signr)
            break;  // 没有更多 pending 信号

        ka = &sighand->action[signr - 1];

        if (ka->sa.sa_handler == SIG_IGN) {
            // 处理方式是"忽略" → 跳过这个信号
            continue;
        }

        if (ka->sa.sa_handler != SIG_DFL) {
            // 用户注册了自定义 Handler → 返回让调用者去设置栈帧
            ksig->ka = *ka;
            break;
        }

        // 处理方式是"默认" → 根据信号类型执行默认行为
        if (sig_kernel_coredump(signr)) {
            // SIGSEGV, SIGABRT, SIGBUS 等 → 终止进程 + core dump
            do_coredump(&ksig->info);
        }

        if (sig_kernel_stop(signr)) {
            // SIGSTOP, SIGTSTP → 停止进程
            do_signal_stop(signr);
            continue;
        }

        // SIGKILL, SIGTERM 等 → 终止进程
        do_group_exit(ksig->info.si_signo);
    }

    return ksig->sig > 0;
}
```

**稳定性架构师视角：** 这段代码解释了一个重要事实：**SIGKILL（信号 9）是无法被捕获的**。因为 `get_signal()` 在进入循环之前有一段特殊处理（上述代码已简化），对 SIGKILL 直接调用 `do_group_exit()` 而不经过 `ka->sa.sa_handler` 的判断。这就是为什么 APM 框架只能捕获 SIGSEGV/SIGABRT 等信号，但无法捕获进程被 `kill -9` 杀死的情况。

### 3.4 handle_signal：从内核态到用户态的"魔法"

这是信号传递中最精妙的部分。内核需要让进程"不知不觉地"跳转到用户态的 Signal Handler 去执行。它是怎么做到的？

**核心思路：** 修改进程即将返回用户态时的寄存器上下文（`pt_regs`），让 CPU 以为自己应该跳转到 Signal Handler 而不是原来的代码。

**源码路径：** `arch/arm64/kernel/signal.c`

```c
// arch/arm64/kernel/signal.c
static int handle_signal(struct ksignal *ksig, struct pt_regs *regs)
{
    struct rt_sigframe __user *frame;
    int usig = ksig->sig;

    // 1. 在用户栈上分配 sigframe 空间
    frame = get_sigframe(ksig, regs, sizeof(*frame));

    // 2. 将当前寄存器上下文保存到 sigframe 中（用于 Handler 返回后恢复）
    err |= setup_sigframe(frame, regs);

    // 3. 将 siginfo 复制到 sigframe 中（Handler 可以通过参数读取）
    err |= copy_siginfo_to_user(&frame->info, &ksig->info);

    // 4. 设置 sigreturn 的 trampoline 代码地址
    //    Handler 执行完毕后，会调用 rt_sigreturn 系统调用恢复原始上下文
    regs->regs[30] = (unsigned long)VDSO_SYMBOL(vdso, sigtramp);

    // 5. 修改 PC 指向 Signal Handler
    regs->pc = (unsigned long)ksig->ka.sa.sa_handler;

    // 6. 修改 SP 指向 sigframe
    regs->sp = (unsigned long)frame;

    // 7. 设置 Handler 的参数（ARM64 调用约定：x0-x7）
    regs->regs[0] = usig;                           // 第一个参数：信号编号
    regs->regs[1] = (unsigned long)&frame->info;     // 第二个参数：siginfo_t *
    regs->regs[2] = (unsigned long)&frame->uc;       // 第三个参数：ucontext_t *

    return 0;
}
```

**当这个函数返回后，内核恢复"被修改过的" `pt_regs` 到 CPU 寄存器，CPU 开始在用户态执行——但此时 PC 已经指向了 Signal Handler 而不是原来的代码。** 对用户态来说，就好像是一次"透明的函数调用"。

整个过程用图表示：

```
内核态                                        用户态
                                     ┌─────────────────┐
                                     │ 正在执行用户代码    │
                                     │ PC = 0x7f001234  │
                                     └────────┬────────┘
                                              │
                                     发生异常/系统调用返回
                                              │
┌─────────────────────────────┐               ▼
│ do_signal()                  │      ┌──────────────┐
│  ├─ get_signal() → SIGSEGV  │      │ 保存用户态    │
│  └─ handle_signal()         │      │ 寄存器到      │
│     ├─ 保存原 regs 到 sigframe│      │ pt_regs      │
│     ├─ regs->pc = handler   │      └──────────────┘
│     ├─ regs->sp = sigframe  │
│     └─ 返回                  │
└──────────────┬──────────────┘
               │
               ▼ 恢复 pt_regs 到 CPU
                                     ┌─────────────────┐
                                     │ Signal Handler   │
                                     │ PC = handler_addr│
                                     │ SP = sigframe    │
                                     └────────┬────────┘
                                              │
                                     Handler 执行完毕，
                                     调用 rt_sigreturn
                                              │
               ┌──────────────────────────────┘
               ▼
┌─────────────────────────────┐
│ sys_rt_sigreturn()           │
│  从 sigframe 恢复原始 regs    │
│  regs->pc = 0x7f001234      │
└──────────────┬──────────────┘
               │
               ▼ 恢复 pt_regs 到 CPU
                                     ┌─────────────────┐
                                     │ 继续执行原代码    │
                                     │ PC = 0x7f001234  │
                                     └─────────────────┘
```

**稳定性关联：** 整个 sigframe 机制是 Tombstone 中 `ucontext` 信息的来源。debuggerd 的 Signal Handler 收到的第三个参数 `ucontext_t *` 就包含了崩溃瞬间所有寄存器的值——这就是 Tombstone 中寄存器段（`x0` 到 `x30`、`sp`、`pc`、`pstate`）的数据来源。

---

## 4. 信号的处理

### 4.1 sigaction：注册 Signal Handler

用户态进程通过 `sigaction()` 系统调用注册自定义的 Signal Handler。它替代了不安全的 `signal()` 函数。

**源码路径：** `bionic/libc/bionic/sigaction.cpp`

```cpp
// bionic/libc/bionic/sigaction.cpp
int sigaction(int signal, const struct sigaction* bionic_new_action,
              struct sigaction* bionic_old_action)
{
    // Bionic 对 sigaction 做了一层包装
    // 将 bionic 的 sigaction 结构体转换为内核的 sigaction 结构体
    // 并添加 SA_RESTORER 标志，设置 sigreturn trampoline

    __kernel_sigaction kernel_new;
    if (bionic_new_action) {
        kernel_new.sa_flags = bionic_new_action->sa_flags;
        kernel_new.sa_handler = bionic_new_action->sa_handler;
        kernel_new.sa_mask = filter_reserved_signals(bionic_new_action->sa_mask);
        kernel_new.sa_restorer = bionic_new_action->sa_restorer;

        // 强制添加 SA_RESTORER，确保 Handler 返回时能正确调用 sigreturn
        if (!(kernel_new.sa_flags & SA_RESTORER)) {
            kernel_new.sa_flags |= SA_RESTORER;
            kernel_new.sa_restorer = &__restore_rt;
        }
    }

    return __rt_sigaction(signal, &kernel_new, &kernel_old, sizeof(sigset_t));
}
```

### 4.2 sigaction 结构体的关键字段

```c
struct sigaction {
    // Signal Handler 函数指针
    // 如果设置了 SA_SIGINFO 标志，使用 sa_sigaction 而非 sa_handler
    union {
        void (*sa_handler)(int);                                    // 简单 Handler
        void (*sa_sigaction)(int, siginfo_t *, void *);             // 带 siginfo 的 Handler
    };

    sigset_t sa_mask;       // Handler 执行期间额外阻塞的信号集
    int sa_flags;           // 标志位
    void (*sa_restorer)(void); // sigreturn trampoline
};
```

**关键标志位：**

| 标志 | 含义 | 在 Native Crash 中的作用 |
| :--- | :--- | :--- |
| `SA_SIGINFO` | Handler 使用三参数形式 `(int sig, siginfo_t *info, void *ucontext)` | **必须设置**。APM 框架需要 `siginfo_t` 获取 fault addr，需要 `ucontext` 获取寄存器状态 |
| `SA_ONSTACK` | 在备用栈（Alternate Signal Stack）上运行 Handler | **必须设置**。崩溃时原栈可能已损坏（如栈溢出），在备用栈上运行才安全 |
| `SA_RESTART` | 被信号中断的系统调用自动重启 | 避免信号导致 `read()`/`write()` 等调用返回 `EINTR` |
| `SA_NODEFER` | Handler 执行期间不自动阻塞当前信号 | 小心使用，可能导致 Handler 递归 |
| `SA_RESETHAND` | Handler 执行一次后恢复为默认行为 | debuggerd_handler 使用此标志确保二次崩溃时执行默认行为（生成 core dump） |

### 4.3 siginfo_t：崩溃信息的载体

`siginfo_t` 是信号携带的详细信息结构体，也是 Tombstone 中最关键的几行数据的来源。

```c
typedef struct {
    int      si_signo;    // 信号编号（如 11 = SIGSEGV）
    int      si_errno;    // 错误码（通常为 0）
    int      si_code;     // 信号子码（如 SEGV_MAPERR=1, SEGV_ACCERR=2）

    union {
        // 对于 SIGSEGV/SIGBUS/SIGFPE：
        struct {
            void    *si_addr;    // ★ 故障地址（Tombstone 中的 fault addr）
            short    si_addr_lsb;
            union {
                struct {
                    void *_lower;
                    void *_upper;
                } _addr_bnd;     // BNDERR (MPX) 的边界信息
                __u32 _pkey;     // PKUERR (PKU) 的保护密钥
            } _bounds;
        } _sigfault;

        // 对于 kill()/tgkill() 发送的信号：
        struct {
            pid_t si_pid;     // 发送者的 PID
            uid_t si_uid;     // 发送者的 UID
        } _kill;

        // 对于 SIGSYS (seccomp)：
        struct {
            int   _syscall;   // 被拦截的系统调用号
            int   _arch;      // 调用架构
        } _sigsys;
    } _sifields;
} siginfo_t;
```

**稳定性架构师视角：** 当你在 Tombstone 中看到：

```
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0000000c
```

这三个值分别对应：
- `si_signo = 11` → SIGSEGV
- `si_code = 1` → SEGV_MAPERR（映射不存在）
- `si_addr = 0x0000000c` → fault addr

`fault addr = 0x0000000c` 是一个接近 0 的小地址。这通常意味着代码通过一个 NULL 指针访问了偏移量为 12 的成员变量。比如：

```cpp
struct Foo {
    int a;      // offset 0
    int b;      // offset 4
    int c;      // offset 8
    int d;      // offset 12  ← fault addr = 0x0c = 12
};

Foo *p = nullptr;
p->d = 42;     // 访问 nullptr + 12 = 0x0000000c → SIGSEGV
```

### 4.4 Signal Handler 的栈帧：sigframe

上一节中我们看到，内核在用户栈上构造了一个 `sigframe`（或 `rt_sigframe`）。这个栈帧是 Signal Handler 能够访问崩溃上下文的关键。

**源码路径：** `arch/arm64/kernel/signal.c`

```c
// arch/arm64/include/uapi/asm/sigcontext.h + arch/arm64/kernel/signal.c
struct rt_sigframe {
    struct siginfo info;           // siginfo_t（包含 si_signo, si_code, si_addr）
    struct ucontext uc;            // 用户上下文
};

struct ucontext {
    unsigned long     uc_flags;
    struct ucontext  *uc_link;
    stack_t           uc_stack;    // 备用栈信息
    sigset_t          uc_sigmask;  // Handler 执行期间的信号掩码
    struct sigcontext uc_mcontext; // ★ 关键：包含所有寄存器的值
};

struct sigcontext {
    __u64 fault_address;           // 故障地址
    __u64 regs[31];                // x0 - x30
    __u64 sp;                      // 栈指针
    __u64 pc;                      // 程序计数器（崩溃指令的地址）
    __u64 pstate;                  // 处理器状态
    // ... FPSIMD 状态等
};
```

**稳定性关联：** `uc_mcontext.pc` 就是 Tombstone 中 backtrace 第一帧的 PC 值——它指向**触发崩溃的那条机器指令**。`uc_mcontext.regs[30]`（即 `x30` / `LR`）指向调用者，是堆栈回溯的起始点。APM 框架（如 xCrash/Breakpad）的 Signal Handler 正是从这里提取寄存器值，然后调用 libunwindstack 进行堆栈回溯。

### 4.5 Alternate Signal Stack：安全的后备栈

如果崩溃原因是**栈溢出**（递归过深导致 SP 超出栈边界触碰到 Guard Page），此时用户栈已经不可用。如果 Signal Handler 还试图在用户栈上运行，就会引发**二次崩溃**，直接导致进程被杀，什么信息都收集不到。

解决方案是 **Alternate Signal Stack**（备用信号栈）。通过 `sigaltstack()` 系统调用预先分配一块独立的内存区域作为 Signal Handler 的运行栈。

```c
// 典型的 Alternate Signal Stack 设置
stack_t ss;
ss.ss_sp = mmap(NULL, SIGSTKSZ, PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
ss.ss_size = SIGSTKSZ;  // 通常 8KB
ss.ss_flags = 0;
sigaltstack(&ss, NULL);

// 注册 Handler 时设置 SA_ONSTACK 标志
struct sigaction sa;
sa.sa_sigaction = my_signal_handler;
sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
sigaction(SIGSEGV, &sa, NULL);
```

**稳定性关联：** Android 的 `debuggerd_handler`（源码：`bionic/linker/debuggerd_handler.cpp`）在进程启动时就设置了 Alternate Signal Stack。如果 APM 框架没有设置 `SA_ONSTACK`，在栈溢出场景下就会"静默失败"——进程死了但 APM 什么都没捕获到。这是一个常见的 APM 框架 bug。

---

## 5. 信号掩码与多线程

### 5.1 信号掩码

每个线程都有一个 **信号掩码（signal mask）**，类型为 `sigset_t`。被 mask 的信号不会被传递给该线程，而是保持在 pending 状态直到解除 mask。

```c
// 在当前线程中阻塞 SIGSEGV
sigset_t mask;
sigemptyset(&mask);
sigaddset(&mask, SIGSEGV);
pthread_sigmask(SIG_BLOCK, &mask, NULL);

// 此后即使发生 SIGSEGV，也不会立即传递给本线程
// 但一旦解除 mask，之前 pending 的 SIGSEGV 会立即传递
```

操作信号掩码的两个函数：

| 函数 | 作用域 | 使用场景 |
| :--- | :--- | :--- |
| `sigprocmask()` | 单线程进程 | 在多线程环境中行为未定义 |
| `pthread_sigmask()` | 当前线程 | 多线程程序必须使用此函数 |

### 5.2 进程级信号 vs 线程级信号

这是多线程信号处理中最容易混淆的概念。

**源码路径：** `kernel/signal.c`

```c
// kernel/signal.c
struct task_struct {
    // ...
    struct sigpending pending;        // ★ 线程级 pending 队列
    // ...
    struct signal_struct *signal;     // 指向进程共享的信号结构体
};

struct signal_struct {
    struct sigpending shared_pending; // ★ 进程级 pending 队列
    // ...
};
```

**两种信号的区别：**

| 特征 | 进程级信号 | 线程级信号 |
| :--- | :--- | :--- |
| 产生方式 | `kill(pid, sig)`、内核事件 | `pthread_kill(tid, sig)`、`tgkill()`、硬件异常 |
| 挂在哪里 | `signal->shared_pending` | `task_struct->pending` |
| 谁来处理 | **任意一个**未阻塞该信号的线程 | **指定的**那个线程 |
| 典型场景 | 用户在终端 `kill <pid>` | SIGSEGV（硬件异常总是发给触发异常的线程） |

**关键认知：** 硬件异常（SIGSEGV/SIGBUS/SIGFPE/SIGILL）产生的信号是**线程级信号**——它们直接挂到触发异常的那个线程的 `pending` 队列，而不是进程级的 `shared_pending`。这就是为什么 Tombstone 中"崩溃线程"总是能精确指向实际触发崩溃的线程。

### 5.3 complete_signal：多线程中信号的分发策略

当一个**进程级信号**产生时，内核需要选择一个线程来接收它。选择策略在 `complete_signal()` 中实现。

**源码路径：** `kernel/signal.c`

```c
// kernel/signal.c
static void complete_signal(int sig, struct task_struct *p,
                            enum pid_type type)
{
    struct task_struct *t;

    // 如果是线程级信号（type == PIDTYPE_PID），目标线程已确定
    if (wants_signal(sig, p))
        t = p;
    else {
        // 进程级信号 → 遍历线程组，找一个没有阻塞该信号的线程
        t = signal->curr_target;  // 上次接收信号的线程
        while (!wants_signal(sig, t)) {
            t = next_thread(t);
            if (t == signal->curr_target)
                return;  // 所有线程都阻塞了该信号 → 信号保持 pending
        }
        signal->curr_target = t;  // 记录这次选中的线程
    }

    // 如果目标线程正在睡眠（TASK_INTERRUPTIBLE），唤醒它
    signal_wake_up(t, sig == SIGKILL);
}
```

**稳定性架构师视角：** 这段代码解释了一个常见的困惑：为什么 `kill <pid>` 发送的 SIGABRT 有时候在 Tombstone 中显示的崩溃线程不是主线程，而是某个工作线程？因为进程级信号会被分配给**任意一个未阻塞该信号的线程**。如果主线程恰好在某个系统调用中阻塞了该信号，信号就会被分配给其他线程。

### 5.4 常见的多线程信号陷阱

| 陷阱 | 原因 | 后果 |
| :--- | :--- | :--- |
| 主线程收到其他线程的 SIGSEGV | 不会发生——硬件异常信号是线程级的 | 如果你在 Tombstone 中看到"崩溃线程=主线程"但 backtrace 显示的是 worker 代码，说明 Tombstone 解析有误或是主线程自己触发的 |
| 所有线程都 mask 了某个信号 | `pthread_sigmask(SIG_BLOCK, ...)` 在每个线程中都调用了 | 信号永远 pending，进程表现为"信号丢失" |
| Signal Handler 中调用了非 async-signal-safe 函数 | `malloc()`、`printf()`、`mutex_lock()` 等函数不是信号安全的 | Handler 内部死锁或 heap 损坏 → 二次崩溃 |
| 在子线程中调用 `sigprocmask` | 多线程环境中行为未定义 | 可能只影响调用线程，也可能影响整个进程（取决于实现） |

**稳定性关联：** "Signal Handler 中调用非 async-signal-safe 函数"是 APM 框架最常见的 bug 来源。当进程收到 SIGSEGV 时，Signal Handler 试图调用 `malloc()` 分配内存来存储崩溃信息——但 `malloc()` 本身使用了 mutex，如果崩溃恰好发生在 `malloc()` 内部（持有 mutex 的状态下），Handler 中的 `malloc()` 就会死锁。这就是为什么成熟的 APM 框架（如 xCrash）在 Handler 中只使用预分配的内存和 `write()` 等 async-signal-safe 的系统调用。

---

## 6. Android 的 sigchain

### 6.1 为什么需要 sigchain

在 Android 系统中，一个进程可能有**多个模块**都需要注册 Signal Handler：

1. **ART 的 FaultHandler**：需要捕获 SIGSEGV 来实现隐式空指针检查（将 SIGSEGV 转化为 Java `NullPointerException`）和栈溢出检测（将 SIGSEGV 转化为 Java `StackOverflowError`）。
2. **debuggerd_handler**：需要捕获 SIGSEGV/SIGABRT 等信号来生成 Tombstone。
3. **APM 框架**（xCrash/Breakpad）：需要捕获相同的信号来收集崩溃信息并上报。

问题在于，Linux 的 `sigaction()` 对每个信号只允许注册**一个** Handler。后注册的会覆盖先注册的。这意味着：

- 如果 APM 框架在 ART 之后注册了 SIGSEGV Handler，ART 的隐式空指针检查就失效了——所有的 null 引用访问都会变成 Native Crash 而不是 Java `NullPointerException`。
- 如果 ART 在 APM 框架之后注册，APM 框架就捕获不到 Native Crash 了。

**sigchain 就是为了解决这个"信号处理权争夺"问题而设计的。**

### 6.2 sigchain 的架构

**源码路径：** `art/sigchain/sigchain.cc`

sigchain 的核心思想：**拦截所有的 `sigaction()` 调用，自己管理一条 Handler 链表**。

```
┌─────────────────────────────────────────────────────────┐
│                    sigchain 管理                          │
│                                                          │
│  对外暴露:                                                │
│    sigaction() ──→ sigchain 拦截 ──→ 内部链表管理          │
│                                                          │
│  对于 SIGSEGV 信号，Handler 链:                            │
│                                                          │
│    ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│    │ ART          │───►│ debuggerd    │───►│ APM 框架   │ │
│    │ FaultHandler │    │ handler      │    │ Handler   │ │
│    │              │    │              │    │           │ │
│    │ 检查是否是    │    │ 生成         │    │ 收集信息   │ │
│    │ 隐式空指针    │    │ Tombstone    │    │ 写Minidump│ │
│    └──────────────┘    └──────────────┘    └───────────┘ │
│         │                    │                    │       │
│     能处理？              能处理？             最后兜底     │
│     Y → 转NPE            Y → Tombstone        → 默认    │
│     N → 传给下一个        N → 传给下一个         行为      │
└─────────────────────────────────────────────────────────┘
```

### 6.3 sigchain 的核心实现

**源码路径：** `art/sigchain/sigchain.cc`

```cpp
// art/sigchain/sigchain.cc

// 每个信号的 Handler 链
static std::vector<SigchainAction> chains[_NSIG];

// SigchainAction 结构体：链表中的一个节点
struct SigchainAction {
    // Handler 返回 true 表示已处理，false 表示传给下一个
    bool (*sc_sigaction)(int, siginfo_t*, void*);
    // 是否设置了 SA_SIGINFO
    bool sc_flags;
};

// 注册一个 "special handler"（优先级最高，由 ART 内部调用）
void AddSpecialSignalHandlerFn(int signal, SigchainAction* sa) {
    chains[signal].insert(chains[signal].begin(), *sa);
}

// sigchain 自己注册到内核的真实 Handler（所有信号都走这里）
static void sigchain_handler(int sig, siginfo_t* info, void* ucontext) {
    // 遍历 Handler 链
    for (auto& action : chains[sig]) {
        if (action.sc_sigaction(sig, info, ucontext)) {
            // 某个 Handler 返回 true → 信号已被处理，不再传递
            return;
        }
    }

    // 所有 Handler 都不处理 → 执行用户通过 sigaction() 注册的 Handler
    // （即 APM 框架或 debuggerd_handler 注册的）
    user_sigactions[sig].sa_sigaction(sig, info, ucontext);
}
```

### 6.4 sigchain 对 sigaction 的拦截

sigchain 通过 **LD_PRELOAD** 或链接器机制，将 libc 的 `sigaction()` 替换为自己的版本：

```cpp
// art/sigchain/sigchain.cc
extern "C" int sigaction(int signal, const struct sigaction* new_action,
                         struct sigaction* old_action) {
    // 如果是 ART 管理的信号（SIGSEGV, SIGABRT 等），
    // 不真正调用内核的 sigaction，而是保存到 user_sigactions 数组中
    if (is_managed_signal(signal)) {
        if (old_action) {
            *old_action = user_sigactions[signal];
        }
        if (new_action) {
            user_sigactions[signal] = *new_action;
        }
        return 0;  // 假装成功了
    }

    // 其他信号正常调用内核
    return real_sigaction(signal, new_action, old_action);
}
```

**这段代码的精妙之处在于：** 当 APM 框架调用 `sigaction(SIGSEGV, &my_handler, &old_handler)` 时，它以为自己成功注册了 Handler，但实际上 sigchain 只是把它保存到了 `user_sigactions` 数组中。内核中注册的真实 Handler 始终是 `sigchain_handler`，由 sigchain 统一分发。

### 6.5 信号处理的优先级链

在 Android 进程中，一个 SIGSEGV 信号的完整处理流程：

```
SIGSEGV 到达
    │
    ▼
sigchain_handler() 被内核调用
    │
    ▼
1. ART FaultHandler
   ├─ 检查 fault addr 是否在 Null Page（0x0 - 0xFFF）
   │   → 是：转化为 NullPointerException，返回 true（信号已处理）
   ├─ 检查 fault addr 是否在栈的 Guard Page
   │   → 是：转化为 StackOverflowError，返回 true
   └─ 都不是 → 返回 false，传给下一个
    │
    ▼
2. user_sigactions[SIGSEGV]（debuggerd_handler 或 APM 框架）
   ├─ 收集寄存器、堆栈、内存映射等信息
   ├─ 写 Tombstone / Minidump
   ├─ 设置 SA_RESETHAND 恢复默认行为
   └─ 重新发送 SIGSEGV → 进程被杀（生成 core dump）
```

**稳定性架构师视角：**

**APM 框架必须通过 sigchain 注册 Handler 的原因：** 如果 APM 框架绕过 sigchain 直接调用内核的 `sigaction()`（比如通过 `syscall(__NR_rt_sigaction, ...)` 直接发起系统调用），它会**覆盖** sigchain 注册的 `sigchain_handler`。此后：
- ART 的隐式空指针检查完全失效，所有 null 引用访问都变成 Native Crash。
- 线上的 Java `NullPointerException` 率骤降，Native Crash 率暴增——但根因其实只是 APM 框架注册方式不对。

这就是为什么 ART 的 sigchain 文档明确要求：**所有第三方 Signal Handler 必须通过 `sigaction()` 注册（会被 sigchain 拦截），而不是直接调用系统调用。**

---

## 7. 稳定性实战案例

### 案例一：APM 框架导致大量"假 NullPointerException 消失"

**现象：**

某 App 在集成新版 APM SDK（某自研 Native Crash 捕获框架）后，线上监控出现两个同时发生的异常：
1. Java `NullPointerException` 上报量下降了约 40%
2. Native Crash（SIGSEGV）上报量增加了约 300%，且大量 Tombstone 的 `fault addr` 在 `0x0` - `0xFFF` 范围内

**分析思路：**

1. `fault addr` 在 `0x0` - `0xFFF` 范围内的 SIGSEGV，正是 ART 隐式空指针检查的特征——Java 代码访问 null 引用的字段时，MMU 触发 SIGSEGV，ART 的 `FaultHandler` 捕获后转化为 `NullPointerException`。
2. 现在这些 SIGSEGV 不再被 ART 转化为 NPE，而是直接作为 Native Crash 上报——说明 ART 的 `FaultHandler` 没有机会处理这些信号。
3. 检查 APM SDK 的信号注册代码，发现它使用了 `syscall(__NR_rt_sigaction, ...)` 直接调用内核，绕过了 sigchain 的拦截。

**根因：**

APM SDK 通过直接系统调用注册了 SIGSEGV Handler，覆盖了 sigchain 注册的 `sigchain_handler`。此后所有 SIGSEGV 直接到达 APM 的 Handler，ART 的 FaultHandler 完全被旁路。

信号处理链变成了：

```
SIGSEGV → APM Handler（直接处理为 Native Crash）
          ×
          ART FaultHandler 完全不参与
```

**修复方案：**

将 APM SDK 的信号注册方式从直接系统调用改为标准的 `sigaction()` 调用，让 sigchain 正确拦截并管理 Handler 优先级：

```cpp
// 修复前（错误）
struct kernel_sigaction ksa;
ksa.sa_sigaction = my_crash_handler;
ksa.sa_flags = SA_SIGINFO | SA_ONSTACK;
syscall(__NR_rt_sigaction, SIGSEGV, &ksa, &old_ksa, sizeof(sigset_t));

// 修复后（正确）
struct sigaction sa;
sa.sa_sigaction = my_crash_handler;
sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
sigaction(SIGSEGV, &sa, &old_sa);  // 会被 sigchain 拦截
```

修复后，ART 的 FaultHandler 重新获得优先处理权，NPE 和 Native Crash 的比率恢复正常。

---

### 案例二：栈溢出崩溃但 APM 未捕获

**现象：**

线上某 App 频繁出现"静默崩溃"——用户反馈 App 闪退，但 APM 平台上没有对应的 Native Crash 记录。通过系统 Tombstone（`/data/tombstones/`）发现了大量如下日志：

```
signal 11 (SIGSEGV), code 2 (SEGV_ACCERR), fault addr 0x71a3c00ff0
Cause: stack-guard-page-hit

backtrace:
    #00 pc 0x000234a8  librecursive.so (deep_recursive_call+24)
    #01 pc 0x000234b0  librecursive.so (deep_recursive_call+32)
    #02 pc 0x000234b0  librecursive.so (deep_recursive_call+32)
    ... (重复 500+ 帧)
```

**分析思路：**

1. `SEGV_ACCERR` + `Cause: stack-guard-page-hit` 明确指向栈溢出——线程的 SP 超出了栈边界，触碰到了只读的 Guard Page。
2. 栈溢出时，当前线程的用户栈已经不可用（SP 已越界）。如果 Signal Handler 试图在用户栈上运行，会立即触发二次 SIGSEGV。
3. 检查 APM SDK 的初始化代码，发现注册 Handler 时**没有设置 `SA_ONSTACK` 标志**，也没有调用 `sigaltstack()` 设置备用栈。

**根因：**

APM 框架的 Signal Handler 注册缺少 `SA_ONSTACK` 标志。在栈溢出场景下，内核尝试在用户栈上构造 `sigframe`，但用户栈已满，构造失败，内核直接杀死进程（发送 SIGKILL）。APM 的 Handler 从未被执行。

```c
// APM 框架的注册代码（有缺陷）
struct sigaction sa;
sa.sa_sigaction = crash_handler;
sa.sa_flags = SA_SIGINFO;  // ← 缺少 SA_ONSTACK
sigaction(SIGSEGV, &sa, &old_sa);
// 也没有调用 sigaltstack() 设置备用栈
```

**修复方案：**

1. 在每个线程创建时，通过 `sigaltstack()` 设置一个 Alternate Signal Stack（建议 16KB 以上）。
2. 注册 Handler 时添加 `SA_ONSTACK` 标志。

```c
// 修复后
// 1. 设置备用栈
stack_t ss;
ss.ss_sp = mmap(NULL, 16384, PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
ss.ss_size = 16384;
ss.ss_flags = 0;
sigaltstack(&ss, NULL);

// 2. 注册 Handler 带 SA_ONSTACK
struct sigaction sa;
sa.sa_sigaction = crash_handler;
sa.sa_flags = SA_SIGINFO | SA_ONSTACK;  // ← 添加 SA_ONSTACK
sigaction(SIGSEGV, &sa, &old_sa);
```

修复上线后，栈溢出导致的 Native Crash 全部被 APM 正确捕获，"静默崩溃"问题解决。

---

## 总结

本篇沿着信号的生命周期（产生 → 传递 → 处理），从内核源码层面拆解了 Linux 信号机制的核心路径，并深入分析了 Android 特有的 sigchain 机制。

核心要点：

1. **信号有三种来源**（硬件异常 / 软件触发 / 内核事件），不同来源的排查方向完全不同。
2. **信号在内核态→用户态的切换点传递**，通过修改 `pt_regs` 实现对用户态 Handler 的"透明调用"。
3. **`siginfo_t` 的 `si_signo` / `si_code` / `si_addr` 三个字段**就是 Tombstone 中最关键的那行信息的来源。
4. **硬件异常产生的信号是线程级的**——Tombstone 中的"崩溃线程"一定是实际触发异常的线程。
5. **sigchain 是 Android 信号处理的中枢**——ART、debuggerd、APM 三方共存的基石。APM 框架必须通过标准 `sigaction()` 注册而不是直接系统调用。
6. **`SA_ONSTACK` + `sigaltstack()` 是处理栈溢出崩溃的必要条件**——没有备用栈，栈溢出时 APM 什么都捕获不到。

在下一篇中，我们将深入 SIGSEGV 背后的内存管理机制——MMU、页表、mmap、Guard Page——理解这些才能真正解读 Tombstone 中 `fault addr` 和 `memory maps` 段的含义。
