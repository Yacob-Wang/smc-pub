# 进程的退出：do_exit 与资源回收

> 系列第 05 篇 · 阶段 B · 生命周期
>
> **承上**：04 篇讲完 execve——进程有完整的地址空间、能跑指令。但进程不会永远活着。本篇回答：进程怎么死？Kernel 怎么"收尸"？
>
> **启下**：单进程的生命周期讲完了。06 篇《调度基础架构：调度类与上下文切换》开始进入"多进程怎么被调度器排班"的阶段 C。
>
> **预计篇幅**：约 1.7 万字
>
> **源码基线**：Linux 5.10 / 5.15（Android 12-14 主流内核）。

---

## 学习目标

读完本文，你应该能：

1. 在脑中画出 `exit()` / `_exit()` / `return main` / `abort()` / `exit_group()` 的关系——为什么它们最终都走 `sys_exit_group`。
2. 跟踪 `sys_exit_group()` → `do_exit()` 的完整路径——11 个步骤分别做什么。
3. 知道资源释放的顺序——mm / files / fs / signal / sighand / namespace 为什么按这个顺序释放。
4. 理解 SIGCHLD 通知父进程的本质——这是父进程感知子进程死亡的唯一可靠方式。
5. 理解 wait4() / waitpid() 的内核实现——释放 task_struct 的最后一步。
6. 知道**僵尸进程**的本质——task_struct 没释放、占用 PID、内核仍保留退出信息。
7. 知道 Android 14 上 Zygote 怎么感知应用死亡——Zygote 用 SIGCHLD handler 收尸。
8. 理解 exit_group 与 exit 的区别——线程退出与进程退出的本质。
9. 理解异常退出路径——信号杀死 / coredump / kernel panic 在 do_exit 上的位置。
10. 能用 ps / dmesg / ftrace 在 Android 14 上定位"僵尸进程"、"进程被 SIGKILL"、"coredump"。

---

## 一、用户态视角：进程怎么"死"

### 1.1 5 种退出方式

进程退出看起来有 5 种方式，但**它们最终都走同一个内核入口**：

| 用户态调用 | 触发场景 | 内核入口 | 退出组？ |
|---|---|---|---|
| `return main` | main 函数 return | C runtime 调 exit | ✅ exit_group |
| `exit(int status)` | 显式调 exit | C runtime 调 _exit | ✅ exit_group |
| `_exit(int status)` | 显式调 _exit（不进 atexit） | sys_exit_group | ✅ exit_group |
| `abort()` | 触发 SIGABRT | 信号处理 → sys_exit_group | ✅ exit_group |
| `pthread_exit()` | 线程退出 | 退线程，**不**退进程 | ❌ |

**关键认知**：
- "进程退出"对内核来说 = **整个线程组退出**——`sys_exit_group` 不是 `sys_exit` 的简单别名，它会**杀死线程组所有线程**
- 单个线程退出（`pthread_exit`）**不**走 do_exit 路径——它走 `do_exit` 的轻量版（在 §10 展开）
- 异常退出（信号杀死）也是 do_exit 路径——信号处理在 §11 展开

### 1.2 Bionic 内部实现

```c
// bionic/libc/stdlib/exit.c
void exit(int status) {
    // 1. 调用 atexit 注册的 cleanup 函数
    __cxa_finalize(NULL);  // C++ 析构

    // 2. 调用 atexit 链表
    while (__exit_func_list) {
        // 调 atexit 注册的函数
    }

    // 3. 调 _exit
    _exit(status);
}

// bionic/libc/unistd/_exit.c
void _exit(int status) {
    // 直接 syscall
    __bionic_syscall(SYS_exit_group, status);
    __builtin_unreachable();
}
```

**关键路径**：

```
main()
  ↓ return
exit(status)
  ↓ atexit 链表清理（用户态 cleanup）
  ↓ stdio flush
  ↓ _exit(status)
  ↓ [syscall]
sys_exit_group(status)
  ↓ do_exit(status)
```

**关键认知**：
- `atexit()` 注册的函数在 exit 时被调用——这是用户态 cleanup 的最后机会
- `_exit()` 跳过 atexit——用于 fork 后子进程立刻调用的场景（防止父进程的 atexit 在子进程执行）
- `abort()` 触发 SIGABRT——信号处理路径调用 `_exit()` 走 exit_group

### 1.3 异常退出：信号杀死

```c
// 当进程收到致命信号（SIGKILL / SIGTERM / SIGSEGV 等）
static void __force_signal_kernel(int sig) {
    // 1. 在目标进程的内核栈上构造一个"信号帧"
    // 2. 强制设置 pending 标志
    // 3. 目标进程调度回来时，进入信号处理
    // 4. 致命信号的默认处理 = 进程退出
}
```

**关键**：
- 致命信号的默认 handler 是 `SIG_DFL`——动作是"Term"
- Term 动作 = `do_group_exit()` 走 do_exit 路径
- 异常退出和正常退出在 do_exit 阶段**完全相同**——只是 `exit_code` 不同

### 1.4 Android 14 上看进程退出

```bash
# 1. 跟踪进程的所有 exit 调用
adb shell "strace -e trace=exit_group -p <pid>" 2>&1

# 2. 看进程被什么信号杀死
adb shell "cat /proc/<pid>/status | grep -E 'SigQ|SigPnd|ShdPnd'"

# 3. 看系统的进程死亡事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_process_exit' --time 10"
```

**典型输出**：

```
perfetto: sched:sched_process_exit: pid=1234 comm=com.example.app exit_code=0
```

`exit_code=0` 表示正常退出，非 0 表示异常。

### 1.5 exit_code 的编码

**重要**：父进程 `wait4()` 拿到的状态码与 `exit()` 传入的值不同：

| 子进程 | 退出方式 | `WIFEXITED(status)` | `WEXITSTATUS(status)` |
|---|---|---|---|
| `exit(0)` | 正常 | true | 0 |
| `exit(42)` | 正常 | true | 42 |
| `return 42` | 正常 | true | 42 |
| 收到 SIGKILL | 异常 | false | — |
| `WIFSIGNALED(status)` 触发 | 异常 | false | — |

```c
// wait.h
WIFEXITED(status)   // 是否正常退出
WEXITSTATUS(status) // 拿到 exit() 的参数
WIFSIGNALED(status) // 是否被信号杀死
WTERMSIG(status)    // 拿到信号编号
```

**关键**：
- 父进程通过 `WEXITSTATUS` 拿 exit 码
- 通过 `WTERMSIG` 拿杀死子进程的信号
- 父进程 wait4() 之后子进程才是"完全死透"——task_struct 才会被释放

---

## 二、内核入口：sys_exit_group 与 sys_exit

### 2.1 两个系统调用的关系

```c
// kernel/exit.c
SYSCALL_DEFINE1(exit_group, int, error_code)
{
    do_group_exit(error_code);
    // 不会返回
}

SYSCALL_DEFINE1(exit, int, error_code)
{
    do_exit(error_code);
    // 不会返回
}
```

**关键差异**：

| 维度 | sys_exit | sys_exit_group |
|---|---|---|
| 退出范围 | 当前线程 | 整个线程组（所有线程） |
| 触发场景 | 线程主动退出 | 进程退出（main return） |
| 内核实现 | do_exit | do_group_exit → do_exit |
| Linux 版本 | 都有 | 都有（glibc 2.3+） |

**关键认知**：
- `pthread_exit()` 走 sys_exit
- main 函数 return 走 sys_exit_group（默认终止整个进程）
- 现代 Linux 上 glibc 几乎只调 `exit_group`——`sys_exit` 主要给线程用

### 2.2 do_group_exit 的"传染"机制

```c
// kernel/exit.c
void do_group_exit(int exit_code)
{
    struct signal_struct *sig = current->signal;

    // 1. 已经在退出中：直接 do_exit
    if (current->flags & PF_EXITING) {
        do_exit(exit_code);
        return;
    }

    // 2. 设置 group exit code（这会被所有线程读到）
    sig->group_exit_code = exit_code;
    sig->flags = SIGNAL_GROUP_EXIT;

    // 3. 给线程组所有其他线程发 SIGKILL
    for_each_thread(tsk) {
        if (tsk != current)
            zap_other_threads(tsk);
    }

    // 4. 自己 do_exit
    do_exit(exit_code);
}
```

**关键认知**：
- `do_group_exit` 第一个动作：给所有"同胞线程"发 SIGKILL
- SIGKILL 不可捕获——其他线程必死
- 然后调用方自己 do_exit
- 整个线程组**原子性退出**——不会出现"主线程退出了，worker 线程还在跑"

### 2.3 do_exit 的 11 个步骤概览

do_exit 是 Linux 内核中**最关键也最不容错**的函数之一。它按以下顺序执行（kernel/exit.c）：

```
do_exit(error_code)
  ↓
  1. irq/tsc 同步（多核下保证时间戳一致）
  ↓
  2. 标记进程为 EXITING（PF_EXITING）
  ↓
  3. 释放 mm（mm = NULL）
  ↓
  4. 给父进程发 STATIS 子信号 + 调度器脱离
  ↓
  5. 关闭所有文件描述符
  ↓
  6. 释放 namespace 引用
  ↓
  7. 释放 task_io_accounting
  ↓
  8. 释放 sighand / signal
  ↓
  9. 释放 exit_code
  ↓
  10. 调度器通知（schedule 不再选这个 task）
  ↓
  11. release_task 准备 task_struct 释放
  ↓
  12. schedule() 让出 CPU（永不再被调度）
```

接下来 §3 逐步骤展开。

---

## 三、do_exit 关键路径

### 3.1 步骤 1-2：标记 EXITING 状态

```c
// kernel/exit.c
void do_exit(long code)
{
    struct task_struct *tsk = current;
    int group_dead;

    // 1. 多核时间戳同步
    // (vtime + lockdep + 其他 per-CPU 状态)
    // ...

    // 2. 标记 EXITING
    tsk->flags |= PF_EXITING;
    // 这一步之后:
    // - 调度器不再选这个 task
    // - 其他线程看到这个标志知道该进程正在退出
}
```

**关键认知**：
- `PF_EXITING` 一旦设置，**调度器不再选这个 task**（在 `try_to_wake_up` / `select_task_rq` 里检查）
- 防止"do_exit 还没走完，又被调度到"——这是个坑爹的边界情况
- 多核时间戳同步确保 `task_struct` 的退出时间戳对所有 CPU 一致

### 3.2 步骤 3：释放 mm

```c
    // 3. 释放 mm_struct
    tsk->mm = NULL;
    tsk->active_mm = NULL;
    // ...
    mm = tsk->mm;
    if (mm) {
        // 关闭内核态活动的 mm
        // ...
    }

    // mm 引用计数 -1
    mmdrop(mm);
```

**关键**：
- 这一步后，进程的 VMA 全部释放（如果有其他进程共享——引用计数 > 1——则保留）
- 物理页释放：引用计数归 0 时释放
- `tsk->mm = NULL` 是关键——任何后续访问 `current->mm` 都会 panic

### 3.3 步骤 4：通知调度器 + 父进程

```c
    // 4. 通知调度器
    schedule_exit_group(tsk, tsk->signal->group_exit_code);

    // 给父进程发 STATIS 子信号（SIGCHLD 的内核版）
    tsk->exit_code = code;
    // ...
    do_notify_parent(tsk, tsk->signal->group_exit_code);
```

**关键**：
- `schedule_exit_group` 把 task 从 runqueue 移除
- `do_notify_parent` 触发 SIGCHLD 通知父进程——这是父进程感知子进程死亡的关键
- `exit_code` 暂存在 task_struct 中，父进程 wait4() 时取走

### 3.4 步骤 5：关闭所有 fd

```c
    // 5. 关闭所有文件描述符
    for (;;) {
        unsigned long nr;
        // 遍历 files_struct
        // 对每个 fd 调 filp_close
        // ...
    }
```

**关键**：
- 关闭所有 fd 触发 `file->f_count` 减 1——file 是真正释放（如果引用归 0）
- 不关闭已经 O_CLOEXEC 的 fd（因为它们在 exec 时已经关闭）
- Linux 不区分"哪些 fd 是用户态关的，哪些是 exit 关的"——所有 fd 都关

### 3.5 步骤 6-7：释放 namespace / io_accounting

```c
    // 6. 释放 namespace 引用
    exit_task_namespaces(tsk);
    // 7. 释放 task_io_accounting
    task_io_accounting_cleanup(tsk);
    // 释放 signal / sighand
    // ...
```

**关键**：
- namespace 引用减 1——真正的 namespace 在最后一个进程退出时释放
- task_io_accounting 释放 IO 统计
- signal / sighand 释放信号相关的账本

### 3.6 步骤 8-9：释放 sighand / signal

```c
    // 8. 释放 sighand
    __cleanup_sighand(tsk->sighand);
    tsk->sighand = NULL;

    // 9. 释放 signal
    // 最后一个线程退出时彻底释放
    if (atomic_dec_and_test(&tsk->signal->sigcnt)) {
        tsk->signal = NULL;
    }
```

**关键**：
- `sighand_struct` 引用计数减 1
- `signal_struct` 引用计数减 1——**线程组最后一个线程退出时彻底释放**
- 单线程退出的进程，signal_struct 立即释放

### 3.7 步骤 10-11：调度器脱离

```c
    // 10. 调度器脱离
    schedule_task_dead(tsk);
    // 11. prepare_to_sleep
    current->flags |= PF_DEAD;

    // 12. 让出 CPU
    do {
        schedule();
    } while (current);
    // 注：do_exit 不会返回
```

**关键**：
- `PF_DEAD` 标志：task_struct 已死，等待父进程收尸
- 调度器不再选这个 task
- `schedule()` 让出 CPU——这个 task 永不再被调度

### 3.8 do_exit 的不可逆性

**do_exit 是不可逆的**——一旦调用，进程必死亡。`schedule()` 之后的循环是"死循环"——直到父进程收尸后 `release_task` 把 task_struct 彻底释放。

```c
    // 死循环：等待父进程收尸
    do {
        schedule();
    } while (current);
    // 父进程 wait4() → release_task() → 真正释放
```

**关键认知**：
- do_exit 后进程变成"Z 状态"（zombie）——task_struct 还在
- 父进程 `wait4()` 后，task_struct 才被彻底释放
- 没有父进程 → 进程永远 zombie（init 进程会"过继"给 init，init 负责收尸）

---

## 四、资源释放详解

### 4.1 释放顺序：mm → files → fs → signal

do_exit 释放资源的顺序有讲究：

```c
// kernel/exit.c 简化版顺序
mm_release(tsk, tsk->mm);             // 1. mm
// ...
filp_close_all(tsk);                  // 5. files
// ...
exit_fs(tsk);                          // fs
// ...
disassociate_ctty(1);                  // 释放 tty
// ...
release_task_struct_misc(tsk);
```

**为什么这个顺序？**

| 顺序 | 资源 | 理由 |
|---|---|---|
| 1 | mm | 释放 VMA 和物理页——大块资源 |
| 2 | files | 关闭 fd——可能触发 file release，进而释放 inode |
| 3 | fs | 释放 fs_struct（root/pwd/umask） |
| 4 | signal | 释放 sighand/signal_struct |
| 5 | namespace | 引用计数 |
| 6 | cred | 释放凭证 |
| 7 | tty | 释放 tty 关联 |

**关键认知**：
- **mm 必须先释放**——其他资源释放时可能访问 VMA（如 files 关闭时访问 inode）
- **files 在 fs 之后**——fs_struct 引用了 dentry，files 关闭可能让 dentry 释放
- **signal 最后释放**——释放过程中还要用它发 SIGCHLD

### 4.2 mm 释放的细节

```c
// mm_release
void mm_release(struct task_struct *tsk, struct mm_struct *mm)
{
    // 1. 释放 futex（如果有 vma 持锁）
    futex_mm_release(tsk);

    // 2. 通知 vma 子系统（如 userfaultfd）
    // 3. 释放 userfaultfd 引用

    // 4. 调用户态 cleanup
    uprobe_free_utask(tsk);
}
```

**mmput 真正的释放**：

```c
// mm/oom_mm.c
void mmput(struct mm_struct *mm)
{
    // 引用计数 -1
    if (atomic_dec_and_test(&mm->mm_count)) {
        // 真正释放
        __mmput(mm);
    }
}
```

`__mmput` 释放：
- 销毁所有 VMA
- 释放所有页表
- 释放物理页引用

**关键**：
- 如果 mm 被其他进程共享（COW），引用计数 > 1，do_exit 时只减 1
- 真正的释放发生在**最后一个引用者**退出时
- 这就是 Zygote fork 的优化"在 do_exit 时的反面"——子进程退出不会立即释放 Zygote 共享的页

### 4.3 files 释放的细节

```c
// fs/exec.c
void filp_close_all(struct task_struct *tsk)
{
    struct files_struct *files = tsk->files;
    if (!files) return;

    // 1. 遍历 fdtable
    for (;;) {
        unsigned long set;
        // 找到所有 open 的 fd
        // 对每个 fd 调 filp_close
        // ...
    }

    // 2. 释放 fdtable
    put_files_struct(files);
}
```

**关键**：
- 不区分"用户态 close" vs "exit close"——所有 fd 都关
- 共享的 fd 不会真关——只有引用计数归 0 才真正释放
- 这就是 fork 后父进程 close 不影响子进程的原因（do_exit 视角下）

### 4.4 signal / sighand 释放的细节

```c
// kernel/exit.c
void __cleanup_sighand(struct sighand_struct *sighand)
{
    if (refcount_dec_and_test(&sighand->count)) {
        kmem_cache_free(sighand_cachep, sighand);
    }
}

// 释放 signal_struct
if (atomic_dec_and_test(&tsk->signal->sigcnt)) {
    // 线程组最后一个线程退出
    tsk->signal = NULL;
    kmem_cache_free(signal_cachep, sig);
}
```

**关键**：
- `sighand_struct` 引用计数——线程组共享，引用归 0 才释放
- `signal_struct` 引用计数——线程组所有线程共享，**最后一个线程退出时**才真正释放
- 父子进程 fork 后子进程 exit 释放自己的 signal_struct——父进程的不会受影响

### 4.5 cred 释放

```c
// kernel/cred.c
void exit_creds(struct task_struct *tsk)
{
    struct cred *cred = tsk->real_cred;
    // 释放 cred
    put_cred(cred);
    // 释放 thread_keyring
    exit_thread_keyring(cred);
}
```

**关键**：
- `cred` 释放可能触发 SELinux context 释放
- thread_keyring 释放——每个线程独立的密钥环
- keyring 在 Android 14 上用于 keystore 等场景

### 4.6 cgroup 引用

```c
// kernel/exit.c
static void exit_cgroup(struct task_struct *tsk)
{
    // 把 task 从 cgroup 中移除
    cgroup_exit(tsk);
    // cgroup 引用计数 -1
}
```

**关键**：
- 进程退出 cgroup——cgroup 内的进程数 -1
- 引用计数归 0 时 cgroup 销毁（这是 10 篇详讲的内容）
- Android 14 上这是 LMK 杀进程时算分的关键路径

### 4.7 完整释放顺序图

```
do_exit()
  ↓
  PF_EXITING
  ↓
  mm_release + futex_mm_release + uprobe_free_utask
  ↓
  mmput() → __mmput() → 释放 VMA / 页表 / 物理页
  ↓
  schedule_exit_group
  ↓
  do_notify_parent → 发 SIGCHLD
  ↓
  exit_signals(tsk) → 清空 pending
  ↓
  __cleanup_sighand → release_signal
  ↓
  exit_task_namespaces
  ↓
  exit_task_work
  ↓
  exit_creds
  ↓
  filp_close_all → 关闭所有 fd
  ↓
  exit_fs → 释放 fs_struct
  ↓
  disassociate_ctty
  ↓
  exit_keys
  ↓
  taskstats_exit
  ↓
  release_task → 让父进程 wait 时释放
  ↓
  schedule() 死循环
```

---

## 五、通知父进程：SIGCHLD

### 5.1 SIGCHLD 的作用

子进程退出时，**第一个**通知到的对象是父进程——通过 SIGCHLD 信号：

```c
// kernel/exit.c
static void do_notify_parent(struct task_struct *tsk, int sig)
{
    struct task_struct *parent;
    struct sighand_struct *sighand;

    // 1. 找到父进程
    parent = tsk->parent;

    // 2. 选信号：SIGCHLD 或 SIGNAL_GROUP_EXIT
    if (sig == SIGCHLD && tsk->signal->group_exit_task)
        sig = SIGNAL_GROUP_EXIT;

    // 3. 找到父进程的 sighand
    sighand = parent->sighand;
    if (sighand) {
        // 4. 设置 TIF_SIGPENDING
        if (!test_tsk_thread_flag(parent, TIF_SIGPENDING)) {
            // 给父进程发信号
            __group_send_sig_info(sig, &send_sigchld, parent);
        }
    }
}
```

**关键**：
- SIGCHLD 默认 handler 是 `SIG_DFL`——动作是 `Ignore`（默认忽略）
- 父进程想"感知"子进程退出，必须**主动注册 SIGCHLD handler**
- 没有 SIGCHLD handler 的父进程，子进程 exit 后变 zombie——没人收尸

### 5.2 父进程 wait4 之前的中间状态

```
子进程 exec → 子进程跑业务
  ↓
子进程 exit / 被信号杀死
  ↓
do_exit → 发 SIGCHLD
  ↓
子进程状态：TASK_DEAD（zombie）
  ↓
task_struct 还在内存
  ↓
pid 还占用
  ↓
exit_code 在 task_struct 里等着父进程取
  ↓
父进程调度到 → 处理 SIGCHLD
  ↓
wait4() → release_task()
  ↓
task_struct 释放
```

**关键认知**：
- 父进程不调 wait4 → 进程永远 zombie
- zombie 进程不占内存（task_struct 是固定大小），但占 PID
- 大量 zombie 进程 → PID 耗尽

### 5.3 Android 14 上的 SIGCHLD 处理

```java
// frameworks/base/core/java/android/os/ZygoteProcess.java
// 实际上 SIGCHLD 是在 native 层处理
// libcore/include/Zygote.h
// 或 frameworks/base/cmds/app_process/...
```

实际上 Android 14 上 SIGCHLD 处理在 native 层（`libcutils` / `zygote`）：

```c
// frameworks/native/cmds/zygote/zygote_main.cpp（简化）
// Zygote 启动后注册 SIGCHLD handler
static void sigchld_handler(int sig) {
    pid_t pid;
    int status;

    // 1. 循环 wait 防止信号丢失
    while ((pid = waitpid(-1, &status, WNOHANG)) > 0) {
        // 2. 处理子进程退出
        // - 记录退出状态
        // - 通知 ActivityManager
    }
}
```

**关键**：
- `WNOHANG` 标志：非阻塞 waitpid
- `while` 循环：可能多个 SIGCHLD 同时到达，必须循环处理
- Zygote 收到 SIGCHLD 后会**通知系统**——这是 Zygote 知道应用死亡的方式

### 5.4 init 进程的孤儿收养

```c
// kernel/exit.c
// 如果父进程不存在（已经死了），子进程被 init 收养
if (!tsk->parent) {
    // 子进程被 init 收养
    tsk->parent = init_task;
    // ...
}
```

**关键**：
- 父进程先死、子进程后死 → 子进程被 init 收养
- init 进程（PID 1）负责收尸
- Android 14 上 init 是 `system/core/init/init.cpp`

---

## 六、父进程收尸：wait4 / release_task

### 6.1 sys_wait4 的内核实现

```c
// kernel/exit.c
SYSCALL_DEFINE4(wait4, pid_t, upid, int __user *, stat_addr,
                int, options, struct __kernel_rusage __user *, ru)
{
    struct rusage ru64;
    long ret = kernel_wait4(upid, stat_addr, options, &ru64);
    // 把结果回写到用户态
    if (ret > 0) {
        if (put_rusage(&ru64, ru))
            return -EFAULT;
    }
    return ret;
}

long kernel_wait4(pid_t upid, int __user *stat_addr, int options,
                  struct rusage *ru)
{
    // 1. 找到目标子进程
    // 2. 如果子进程还在跑，按 options 阻塞或返回 0
    // 3. 如果子进程已死，调用 wait_task_zombie
    retval = wait_task_zombie(wo, &u64);
    // 4. 释放 task_struct
    return retval;
}
```

**关键**：
- `wait4()` 阻塞父进程直到子进程退出（除非带 WNOHANG）
- 子进程退出后，`wait_task_zombie` 释放 task_struct
- 这是"父进程收尸"的真正实现

### 6.2 release_task 释放 task_struct

```c
// kernel/exit.c
static void release_task(struct task_struct *p)
{
    // 1. 从 pid namespace 删除
    // 2. 从 task list 删除
    // 3. 释放 task_struct
    // 4. 释放 thread_info
    // 5. 减少父进程引用
    // 6. 释放信号
    // 7. 释放 pid
    // 8. 释放 taskstats / per-task data
    put_task_struct_rcu(p);
}
```

**关键**：
- task_struct 的释放是延迟的（RCU）
- 父进程 wait4() 之后，task_struct 才被真正释放
- 大量 zombie 进程 → 内存中累积 task_struct → 内存压力

### 6.3 父进程不 wait4 的后果

```bash
# 复现：父进程不 wait4
cat > /tmp/zombie_test.c << 'EOF'
#include <sys/wait.h>
#include <unistd.h>
int main() {
    if (fork() == 0) {
        _exit(42);  // 子进程立刻退
    }
    // 父进程不 wait4
    sleep(60);
    return 0;
}
EOF
gcc /tmp/zombie_test.c -o /tmp/zombie_test
/tmp/zombie_test &
ps -ef | grep zombie_test
```

输出（子进程状态）：

```
root  1234  5678  ...  <defunct>  ← Z 状态
```

**关键**：
- 子进程变 zombie（`<defunct>` / `Z+`）
- 持续 60 秒直到父进程 exit（被 init 收养）
- 如果父进程永不退，子进程永远 zombie

### 6.4 Android 14 上的进程退出

```bash
# 1. 跟踪 SIGCHLD
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'signal:signal_generate signal:signal_deliver' --time 30"

# 2. 看进程退出统计
adb shell "dumpsys activity processes | grep -A 5 'ProcessRecord{.*com.example.app'"

# 3. 看进程死亡 trace
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_process_exit' --time 10"
```

**典型输出**：

```
sched:sched_process_exit: pid=12345 comm=com.example.app prio=120 exit_code=0
```

---

## 七、僵尸进程的本质

### 7.1 僵尸进程的定义

**僵尸进程**（zombie process）= task_struct 在内存中、占用 PID、等待父进程收尸的进程。

```
子进程 exit
  ↓
  do_exit() 把进程变成 TASK_DEAD
  ↓
  task_struct 还在
  ↓
  状态字段 = TASK_DEAD
  ↓
  exit_code 保留在 task_struct
  ↓
  父进程 wait4 → release_task → 真正释放
```

**关键认知**：
- zombie 状态是**正常的**——不是 bug
- zombie 不占 CPU、不占内存（task_struct 是固定大小的）
- zombie 占 PID——大量 zombie 可能让系统无法创建新进程

### 7.2 zombie 的内存占用

```bash
# 看系统中 zombie 进程的 PID 数
adb shell "ps -A -o PID,STATE,NAME | grep -E '^\\s*[0-9]+\\s+Z' | wc -l"
```

**关键数据**：
- task_struct 大小：~10KB（Linux 5.10 ARM64）
- 1000 个 zombie = 10MB 内存
- 10000 个 zombie = 100MB 内存 + PID 空间压力
- PID 默认上限 32768——`/proc/sys/kernel/pid_max`

### 7.3 Android 14 上处理 zombie

Android 14 上 Zygote 子进程（应用进程）变成 zombie 后：

1. Zygote 收到 SIGCHLD
2. Zygote 在 SIGCHLD handler 中 `waitpid(-1, &status, WNOHANG)`
3. 立刻收尸——几乎不出现 zombie
4. 通知 `ActivityManager` 应用退出

**关键**：
- Android 14 设计上几乎看不到 zombie
- 如果你看到 zombie 大概率是：
  - Zygote 自身死了（system_server 卡住）
  - 第三方进程 fork 后不 wait
  - Native 进程没注册 SIGCHLD handler

### 7.4 排查 zombie 进程

```bash
# 1. 列出所有 zombie
adb shell "ps -A -o PID,PPID,STATE,NAME | grep ' Z '"

# 2. 看父进程
adb shell "ps -A -o PID,PPID,NAME | grep <ZOMBIE_PID>"

# 3. 看父进程的 SIGCHLD handler
adb shell "cat /proc/<PPID>/status | grep SigCgt"
# 如果 SigCgt=0000000000000000 → 没注册 SIGCHLD handler
```

**关键**：
- 找到 zombie 的 PPID（父进程 PID）
- 看父进程 status 中的 SigCgt（signal caught）
- 0x0000000000000000 = 没注册 SIGCHLD handler

### 7.5 解决 zombie 问题

```c
// 方案 1：父进程调 wait4
if (waitpid(child_pid, &status, 0) == -1) {
    perror("waitpid");
}

// 方案 2：父进程注册 SIGCHLD handler
struct sigaction sa = { .sa_handler = sigchld_handler };
sigaction(SIGCHLD, &sa, NULL);

void sigchld_handler(int sig) {
    int saved_errno = errno;
    while (waitpid(-1, NULL, WNOHANG) > 0) { /* nothing */ }
    errno = saved_errno;
}

// 方案 3：使用 signalfd + epoll（高性能方案）
int sfd = signalfd(-1, &mask, SFD_CLOEXEC);
```

**关键**：
- 方案 1：阻塞收尸（简单）
- 方案 2：非阻塞收尸（Zygote 风格）
- 方案 3：异步收尸（高性能服务器）

---

## 八、调度器视角：TASK_DEAD 与 schedule

### 8.1 进程状态的最终归处

02 篇讲的 TASK_RUNNING / TASK_INTERRUPTIBLE / TASK_UNINTERRUPTIBLE 等状态在 do_exit 路径上的最终归处：

```c
// kernel/exit.c do_exit 末尾
tsk->state = TASK_DEAD;   // 显式标记
tsk->flags |= PF_DEAD;
```

**关键认知**：
- `TASK_DEAD` 是 task 的最终状态——不会再变
- 调度器看到 `TASK_DEAD` 不会选这个 task
- 这是"死循环 schedule() 直到被 release"的前提

### 8.2 release_task 后的 release

```c
// kernel/exit.c
void release_task(struct task_struct *p)
{
    // 1. 更新 taskstats（per-task 统计）
    taskstats_exit(p);

    // 2. 从 cgroup 移除
    cgroup_release(p);

    // 3. 从 pid 命名空间释放
    free_pid(p->thread_pid);

    // 4. RCU 延迟释放 task_struct
    put_task_struct_rcu(p);
    // 调用栈：
    // put_task_struct_rcu -> call_rcu(&p->rcu, delayed_put_task_struct)
    // 真正的释放发生在 RCU grace period 之后
}
```

**关键**：
- `put_task_struct_rcu` 是延迟释放——通过 RCU
- RCU grace period 结束后，`delayed_put_task_struct` 真正释放内存
- 这保证 `current` 的引用是安全的（即使被访问）

### 8.3 调度器在 do_exit 中的角色

```c
// kernel/exit.c
void do_exit(...)
{
    // ...
    schedule_exit_group(tsk, tsk->signal->group_exit_code);
    // 这让 task 脱离 runqueue
    // ...
    do {
        schedule();
    } while (current);
    // schedule 内部：
    // 1. pick_next_task 选择下一个 task
    // 2. context_switch 切换
    // 3. 旧的 task（TASK_DEAD）永不再被选
}
```

**关键**：
- `schedule()` 在 do_exit 末尾死循环
- 调度器每次选下一个 task 跑——**永不再选**这个 TASK_DEAD 的 task
- 父进程 release_task 后，task_struct 被释放，do_exit 的 schedule 循环结束

### 8.4 perfetto 调度条上的死亡事件

```bash
# 抓取进程死亡事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_process_exit' --time 30"
```

UI 上看到的"sched_process_exit"事件：

| 字段 | 含义 |
|---|---|
| `pid` | 退出的进程 PID |
| `comm` | 进程名（task_struct->comm） |
| `prio` | 优先级 |
| `exit_code` | 退出码 |

**关键**：
- 退出事件会显示在 perfetto 的调度条上
- 紧跟着的调度条切换——其他进程接管 CPU
- 这是"进程死亡"在 perfetto 上的可观测信号

---

## 九、Android 14 实战：Zygote 感知应用死亡

### 9.1 Zygote 的 SIGCHLD 处理

```c
// frameworks/native/cmds/zygote/zygote_main.cpp（简化）
static void SigChldHandler(int sig) {
    pid_t pid;
    int status;

    // 1. 循环 wait 防止信号丢失
    while ((pid = waitpid(-1, &status, WNOHANG)) > 0) {
        if (WIFEXITED(status)) {
            // 正常退出
            ALOGV("Process %d exited normally with status %d", pid, WEXITSTATUS(status));
        } else if (WIFSIGNALED(status)) {
            // 被信号杀死
            ALOGW("Process %d was killed by signal %d", pid, WTERMSIG(status));
        }

        // 2. 通知 ActivityManager（通过 socket）
        // zygote 通知 system_server 这个应用死了
    }
}
```

**关键**：
- Zygote 注册了 SIGCHLD handler
- 用 `WNOHANG` + 循环 waitpid
- 通知 ActivityManager——这是 AMS 知道应用死亡的关键

### 9.2 Zygote 处理 ANR 退出

```c
// 当 system_server 决定杀进程（ANR / OOM）
// 实际是调 native kill
// libsystem_server 路径：
//   killProcess(pid, signal) → kill(pid, SIGKILL) → kernel send_sig_info

// Zygote 收到 SIGCHLD 后：
//   1. waitpid 收到子进程状态
//   2. status 显示是被 SIGKILL 杀死
//   3. WTERMSIG(status) = SIGKILL
//   4. 通知 system_server 这个应用死了
```

**关键**：
- ANR 时 system_server 调 `Process.killProcess()` → 内核 `kill(pid, SIGKILL)`
- SIGKILL 不可捕获——子进程立即被 kill
- Zygote 收到 SIGCHLD 后通知 system_server
- system_server 把这个 ANR 写入 dropbox + logcat

### 9.3 应用 crash 退出

```java
// Java 层 uncaught exception
Thread.setDefaultUncaughtExceptionHandler((t, e) -> {
    // 1. 写入 dropbox
    // 2. 通知 system_server
    // 3. Process.killProcess(myPid())  ← 触发 native exit
});
```

**关键路径**：

```
Java 未捕获异常
  ↓
UncaughtExceptionHandler
  ↓
Process.killProcess(myPid())
  ↓
native: kill(myPid, SIGKILL)  ← 或者 Process.killProcess 直接调 exit
  ↓
kernel: do_group_exit(SIGKILL)
  ↓
kernel: do_exit
  ↓
Zygote 收到 SIGCHLD
  ↓
通知 system_server
  ↓
AMS 标记 process died
```

### 9.4 进程死亡时 perfetto 看到的

```bash
# 抓 sched_process_exit 事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_process_exit signal:signal_generate' --time 30"
```

UI 看到的：

```
[12345] signal_generate: sig=9 (SIGKILL)
[12345] sched_process_exit: exit_code=-9
[12345] signal_deliver: pid=12345 sig=9  (从 system_server 来)
```

**关键**：
- SIGKILL 信号从 system_server 发出
- 子进程立刻死
- perfetto 显示完整链路

### 9.5 应用死亡后的资源释放顺序

```
应用进程 exit
  ↓
kernel do_exit 释放：
  - VMA
  - 文件 fd
  - signal/sighand
  - cgroup 引用
  ↓
Zygote 收到 SIGCHLD
  ↓
Zygote: waitpid → release_task
  ↓
ActivityManager: processDied 回调
  ↓
应用的所有 ComponentName 取消注册
  ↓
所有 binder 死亡回调触发
  ↓
应用的进程组清理完成
```

---

## 十、exit_group 与 exit 的区别

### 10.1 线程退出 vs 进程退出

```c
// 单个线程退出（pthread_exit）
void *worker(void *arg) {
    // ...
    pthread_exit(NULL);
}

// 进程退出（exit / main return）
int main() {
    // ...
    return 0;
}
```

**内核路径**：

| 调用 | 内核入口 | 退出范围 | 资源释放 |
|---|---|---|---|
| pthread_exit | sys_exit | 仅当前线程 | 线程私有资源 |
| exit / return main | sys_exit_group | 整个进程 | 整个进程资源 |

### 10.2 pthread_exit 的实现

```c
// kernel/exit.c
SYSCALL_DEFINE1(exit, int, error_code)
{
    do_exit(error_code);
    // 不会返回
}
```

pthread_exit 调 `sys_exit`，它**只退出当前线程**：
- 释放当前线程的 thread_info、栈、tls
- 减少 signal_struct 引用（线程组其他线程不受影响）
- **不**关闭 files_struct（线程共享）
- **不**关闭 mm（线程共享）

**关键认知**：
- `pthread_exit` 后，进程**不退出**——其他线程继续跑
- 这就是为什么 worker 线程退出不会让 main 退出

### 10.3 进程退出的"传染"过程

```c
// kernel/exit.c do_group_exit
void do_group_exit(int exit_code)
{
    // 1. 检查当前是否已经在退出
    if (current->flags & PF_EXITING) {
        do_exit(exit_code);
        return;
    }

    // 2. 设置 group exit code
    current->signal->group_exit_code = exit_code;
    current->signal->flags = SIGNAL_GROUP_EXIT;

    // 3. 给所有其他线程发 SIGKILL
    for (p = next_thread(current); p != current; p = next_thread(p)) {
        if (p->exit_state != EXIT_ZOMBIE && !(p->flags & PF_EXITING)) {
            // 给线程发 SIGKILL
            zap_other_threads(p);
        }
    }

    // 4. 自己 do_exit
    do_exit(exit_code);
}
```

**关键**：
- `for_each_thread` 遍历线程组
- 给每个还没退出的线程发 SIGKILL
- SIGKILL 不可捕获——必死

### 10.4 Android 14 上的真实场景

**场景 1：应用主线程异常 → ART crash → 进程退出**

```
主线程：SIGSEGV
  ↓
ART signal handler 调 _exit(EXIT_FAILURE)
  ↓
sys_exit_group
  ↓
do_group_exit → 给 worker 线程发 SIGKILL
  ↓
所有线程死
  ↓
do_exit → 释放资源
```

**场景 2：worker 线程异常 → worker 退出 → 进程继续**

```
worker 线程：SIGSEGV
  ↓
worker signal handler 调 pthread_exit
  ↓
sys_exit → do_exit（仅 worker）
  ↓
worker 死，主线程继续
```

**关键**：
- ART 默认对 fatal signal 的处理是退出**整个进程**
- 用户态 catch 后调 `pthread_exit` 只是退出线程
- ART crash 时通常整个进程死——这是 ART 的设计

### 10.5 为什么 do_group_exit 用 SIGKILL

```c
// zap_other_threads
static void zap_other_threads(struct task_struct *p)
{
    // 1. 设置 SIGKILL pending
    p->signal->shared_pending.signal.sig[0] |= SIGKILL_MASK;
    // 2. 唤醒目标线程（如果它在 sleep）
    if (p != current) {
        wake_up_state(p, TASK_INTERRUPTIBLE);
    }
}
```

**关键**：
- SIGKILL 不可捕获——目标线程必死
- 即使目标线程在 atomic 上下文，`SIGKILL` 也能"打断"它
- 这是 do_group_exit 强杀其他线程的方式

### 10.6 SIGKILL 不能"立刻"死亡的边界情况

虽然 SIGKILL 不可捕获，但**有 3 种情况会让目标线程延后死亡**：

1. **不可中断的 sleep（D 状态）**：目标线程在 `uninterruptible_sleep`——例如等待 IO
2. **内核态死循环**：但内核不会无限循环，通常会 schedule
3. **中断上下文**：在 hardirq 上下文——但中断上下文不能 schedule，所以不会无限

**关键**：
- D 状态的进程无法被 SIGKILL 立刻杀
- 这是 `kill -9` 不一定立刻生效的根因
- Android 14 上"杀不掉的应用"通常是 D 状态（IO 卡住）

---

## 十一、异常退出：信号杀死、coredump、kernel panic

### 11.1 信号杀死

信号杀死是进程异常退出的**最常见方式**：

```c
// 致命信号的默认 handler
// include/linux/signal.h
#define SIG_DFL ((__sighandler_t)0)   // 默认处理
#define SIG_IGN ((__sighandler_t)1)   // 忽略

// 默认处理动作（killing signal）
case SIGHUP:  /* Hangup */
case SIGINT:  /* Interrupt (Ctrl+C) */
case SIGQUIT: /* Quit */
case SIGABRT: /* Abort */
case SIGFPE:  /* Floating point exception */
case SIGKILL: /* Kill (uncatchable) */
case SIGUSR1: /* User defined */
case SIGSEGV: /* Segmentation fault */
case SIGUSR2: /* User defined */
case SIGPIPE: /* Broken pipe */
    // 默认动作 = Term (do_group_exit)
    return;
```

**关键**：
- 大部分致命信号默认动作是 `Term`——调 do_group_exit
- `Term` 动作 = `do_group_exit(signum)`（signum 作为 exit_code）
- 父进程 `wait4` 拿到的状态：`WIFSIGNALED` = true，`WTERMSIG` = 信号编号

### 11.2 SIGKILL 的特殊性

```c
// 不可捕获、不可阻塞、不可忽略
if (sig == SIGKILL || sig == SIGSTOP) {
    // 直接 force_sig_info_to_task
    // 绕过所有 handler
    force_sig_info_to_task(sig, &send_sigchld, tsk);
}
```

**关键**：
- SIGKILL / SIGSTOP 不可捕获——用户态 handler 不会跑
- 任何信号 mask 都不影响
- 唯一阻止 SIGKILL 的方法：D 状态

### 11.3 coredump 在 exit 路径上的位置

```c
// kernel/exit.c
// 当子进程收到 SIGSEGV 等带 coredump 的信号
// 1. 信号处理在 deliver_signal
// 2. SIG_DFL 动作 = Core dump
// 3. 调用 do_coredump
// 4. 写入 coredump 文件
// 5. 然后调 do_group_exit（子进程退出）

static int do_coredump(struct kernel_siginfo *info)
{
    // 1. 找到 coredump handler
    // 2. 调用 format-specific handler (elf_core_dump)
    // 3. 写入 /data/coredump/<comm>-<pid>-<timestamp>.core
    // 4. 释放 coredump 资源
    // 5. 调 do_group_exit
}
```

**关键**：
- coredump 不阻止进程退出——是"额外动作"
- coredump 写完后进程才退
- Android 14 上 coredump 默认不开启（debug build 才开）

### 11.4 Android 14 上的 coredump 路径

```bash
# Android 14 的 coredump 路径
adb shell "ls /data/coredump/"

# 配置 coredump
adb shell "cat /proc/sys/kernel/core_pattern"
# 输出: |/system/bin/save_core  ← Android 特有：把 core 转给 save_core
```

**关键**：
- Android 14 用 `core_pattern` 把 coredump 转给 `save_core` 程序
- `save_core` 把 coredump 写入 `/data/coredump/` 目录
- 这是为了避免 coredump 直接写入应用目录

### 11.5 kernel panic 与进程 exit

```c
// kernel/panic.c
void panic(const char *fmt, ...)
{
    // 1. 打印 panic 信息
    // 2. 调 blk/icmp/... 等
    // 3. 关键路径：crash_kexec 或重启
    // 4. **不调 do_exit**——这是 kernel 自己死
}
```

**关键认知**：
- kernel panic 是**内核死**——不是进程退
- 进程 exit 调用 do_exit
- kernel panic 调 panic()
- 两者路径完全不同

### 11.6 oom kill 路径

```c
// mm/oom_kill.c
// 1. oom_score 最高的进程被选中
// 2. 调 oom_kill_process
// 3. 给目标进程发 SIGKILL（加 special flag OOM）
// 4. 目标进程 do_group_exit
// 5. 打 oom log

void oom_kill_process(struct oom_control *oc, const char *message)
{
    // 1. 给目标进程发 SIGKILL
    send_sig(SIGKILL, victim, 0);
    // 2. 设置 OOM flag
    mark_oom_victim(victim);
    // 3. 打印 oom 警告
    pr_err("Killed process %d (%s) total-vm:%lukB ...\n",
           pid, victim->comm, ...);
}
```

**关键**：
- oom killer 选最高 oom_score 的进程杀
- Android 14 上是 LMKD（`lmkd`）用户态选择——不是内核 oom_killer
- LMKD 用 PSI（Pressure Stall Information）判断内存压力

---

## 十二、稳定性排查：僵尸 / 资源泄漏 / 杀不掉

### 12.1 排查僵尸进程

```bash
# 1. 列出 zombie
adb shell "ps -A -o PID,PPID,STATE,NAME | grep ' Z '"

# 2. 找父进程
adb shell "ps -A -o PID,NAME | grep <ZOMBIE_PID>"

# 3. 看父进程的信号 mask
adb shell "cat /proc/<PPID>/status | grep SigCgt"

# 4. 看父进程的 strace
adb shell "strace -p <PPID> -e trace=wait4"

# 5. 强杀父进程（init 收养 zombie）
adb shell "kill -9 <PPID>"
```

**关键**：
- zombie 的根因是父进程没 wait4
- 杀父进程让 init 收养
- 找到根因（代码 bug）才能彻底解决

### 12.2 排查资源泄漏（fd / memory）

```bash
# 1. fd 泄漏
adb shell "ls /proc/<pid>/fd | wc -l"  # 看 fd 数
# 持续增长 → 泄漏

# 2. memory 泄漏
adb shell "dumpsys meminfo <pid>"  # 多次采样对比
# Pss / Private Dirty 持续增长 → 泄漏

# 3. 看 fd 详情
adb shell "ls -l /proc/<pid>/fd"  # 列出所有 fd
# 找到重复的 → 泄漏点
```

### 12.3 排查"杀不掉"的进程

```bash
# 1. 看进程状态
adb shell "ps -A -o PID,STATE,NAME | grep <pid>"
# D = 不可中断 sleep（IO 卡住）
# R = 运行中
# S = 可中断 sleep

# 2. 看进程的 syscall
adb shell "cat /proc/<pid>/syscall"
# 5 = openat, 0xffff... = IO 等待
# 例：openat -1 ENOENT 表示在等文件系统
```

**关键**：
- D 状态进程杀不掉——必须等 IO 完成
- 长卡 D 状态通常是文件系统 bug
- 排查方法：`dmesg` 看内核 IO 错误

### 12.4 排查 exit_code 非 0

```bash
# 1. 看应用 crash log
adb logcat -b crash | grep -A 30 "<pid>"

# 2. 看 exit_code
adb shell "cat /proc/<pid>/status 2>/dev/null"
# 已退的进程看不到 status

# 3. 用 perfetto 抓 exit
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_process_exit' --time 30"
```

**关键**：
- exit_code 非 0 通常是 crash
- 检查 SIGSEGV / SIGABRT / SIGKILL 等信号
- ART 异常会写 dropbox

### 12.5 exit_code 与稳定性指标

| exit_code | 含义 | 稳定性影响 |
|---|---|---|
| 0 | 正常 | 无影响 |
| 1 | 通用错误 | 应用 bug，但不影响系统 |
| 2-N | 应用自定义 | 应用 bug |
| -1 (128+SIGKILL=137) | 被 SIGKILL | 可能是 ANR / OOM |
| -11 (128+SIGSEGV=139) | SIGSEGV | crash |
| -6 (128+SIGABRT=134) | SIGABRT | 应用主动 abort |

**关键**：
- `kill -9` → exit_code = 128+9 = 137
- `kill -SIGSEGV` → exit_code = 128+11 = 139
- 父进程 wait4 拿到的不是这个 exit_code——是 `WTERMSIG` = 信号编号

---

## 十三、给 06 篇留的钩子

读完 05 篇，你应该能：

1. 跟踪 exit 在用户态的 5 种方式。
2. 理解 do_exit 的 11 个步骤——为什么按这个顺序释放资源。
3. 理解 SIGCHLD 是父进程感知子进程死亡的唯一可靠方式。
4. 理解 wait4 / release_task 是收尸的最后一步。
5. 知道僵尸进程的本质——task_struct 没释放、占 PID。
6. 理解 exit_group 与 exit 的本质区别——线程退出 vs 进程退出。
7. 理解异常退出路径——信号杀死 / coredump / oom kill。

阶段 B（生命周期）到这里结束——你已经知道一个进程怎么从"无"变"有"（03）、"空壳"变"活的"（04）、"活的"变"死的"（05）。

**下一阶段：阶段 C — 进程被调度（Kernel 最核心的子系统）**

06 篇《调度基础架构：调度类与上下文切换》会回答：

> 单进程讲完了——多个进程怎么被调度器"排班"？
>
> - sched_class 体系（fair / rt / deadline / idle / stop）
> - runqueue 数据结构
> - schedule() 主入口
> - context_switch 实现（switch_to / switch_mm）
> - 调度器"挑中谁跑"的判断逻辑

读完 06-09，你将进入"调度器视角"——这是 Kernel 最硬核的子系统之一，也是 Android 14 上 EAS / UClamp / 优先级反转等现象的根源。

---

## 小结

| 维度 | 一句话总结 |
|---|---|
| 用户态退出 | 5 种方式都最终走 sys_exit_group → do_group_exit → do_exit |
| do_exit 顺序 | EXITING → mm → files → signal → namespace → cred → TASK_DEAD → schedule |
| SIGCHLD | 父进程感知子进程死亡的方式，必须注册 handler 才能收尸 |
| wait4 / release_task | 父进程收尸的最后一步——真正释放 task_struct |
| 僵尸进程 | task_struct 还在、占 PID、占 ~10KB 内存、不占 CPU |
| exit_group vs exit | 前者杀整个进程，后者只退当前线程 |
| 异常退出 | SIGKILL / SIGSEGV / SIGABRT 等带 Core / Term 动作的信号 |
| Android Zygote | 注册 SIGCHLD handler + waitpid(-1, WNOHANG) 收尸 + 通知 AMS |

---

## 给下篇的桥

**本篇留下三个钩子**：

1. do_exit 释放的 mm / files / signal 都是 02 篇 task_struct 字段的"反面"——06 篇讲调度器怎么访问这些资源
2. 调度器在 do_exit 中"切走"当前 task——06 篇详讲 schedule() 主入口
3. Zygote 注册的 SIGCHLD handler 是"用户态 + 内核"协作的范例——06 篇会讲用户态 / 内核态切换

如果读完本文仍有疑问：

- **"父进程没 wait4 怎么办？"** → §5.4 init 进程的孤儿收养
- **"信号杀死和正常退出的差异？"** → §11.1 / 11.2 致命信号 vs 正常 exit
- **"Android 14 上 zombie 几乎看不到？"** → §9.1 Zygote 主动收尸
- **"kill -9 不一定立刻杀？"** → §10.6 D 状态的 SIGKILL 延迟

---

## 引用

| 引用 | 路径 |
|---|---|
| 系统调用入口 | `kernel/exit.c:SYSCALL_DEFINE1(exit_group)` |
| do_group_exit | `kernel/exit.c:do_group_exit` |
| do_exit | `kernel/exit.c:do_exit` |
| mm_release | `kernel/exit.c:mm_release` |
| mmput | `mm/oom_mm.c:mmput` |
| filp_close_all | `fs/exec.c:filp_close_all` |
| release_task | `kernel/exit.c:release_task` |
| wait4 | `kernel/exit.c:SYSCALL_DEFINE4(wait4)` |
| sys_wait4 | `kernel/exit.c:kernel_wait4` |
| SIGCHLD 通知 | `kernel/signal.c:do_notify_parent` |
| exit_signals | `kernel/exit.c:exit_signals` |
| oom_kill | `mm/oom_kill.c:oom_kill_process` |
| do_coredump | `fs/coredump.c:do_coredump` |
| 调度器脱离 | `kernel/sched/core.c:schedule_exit_group` |
| Android 14 Zygote SIGCHLD | `frameworks/native/cmds/zygote/zygote_main.cpp:SigChldHandler` |
| Android 14 coredump | `/proc/sys/kernel/core_pattern` |
| Android 14 OOM killer | `system/core/lmkd/lmkd.cpp` |




