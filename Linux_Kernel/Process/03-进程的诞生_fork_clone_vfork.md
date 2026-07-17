# 进程的诞生：fork / clone / vfork

> 系列第 03 篇 · 阶段 B · 生命周期
>
> **承上**：02 篇把 task_struct 的所有字段画了全景。本篇回答——这些字段怎么从"无"变"满"？
>
> **启下**：进程诞生后是个空壳，需要加载可执行文件才能"活"起来。04 篇《进程的执行：execve 与程序加载》回扣。
>
> **预计篇幅**：约 1.8 万字
>
> **源码基线**：Linux 5.10 / 5.15（Android 12-14 主流内核）。

---

## 学习目标

读完本文，你应该能：

1. 在脑中画出 fork / clone / vfork 三个系统调用的关系——为什么 libC 把 fork / vfork 都实现成 clone。
2. 跟踪 `sys_clone()` → `_do_fork()` → `copy_process()` → `wake_up_new_task()` 的完整路径。
3. 知道 copy_process 中 4 个关键阶段分别做什么——task_struct 分配 / 资源账本复制 / 子进程入口构造 / 唤醒调度。
4. 理解 COW（写时复制）在 fork 路径上的真实形态——为什么父进程 page table 没被实际复制但子进程能看到。
5. 理解 vfork 的"父进程让出 CPU + 子进程用父页表"特殊语义，以及它为什么被逐渐废弃。
6. 能用 `strace` 在 Android 14 上看到真实 fork 序列，能用 `cat /proc/<pid>/status` 验证 fork 后两个进程的关联关系。
7. 知道 Android Zygote fork 优化在 Kernel 层落到 copy_process 哪几个步骤。

---

## 一、用户态视角：3 个系统调用的关系

### 1.1 三者本质相同——都是 clone

很多人误以为 `fork()` / `vfork()` / `clone()` 是三个不同的系统调用。**真相**：现代 Linux 上，**它们都是 `clone()` 的 wrapper**，区别只是 flag 组合不同。

源码依据（glibc `sysdeps/unix/sysv/linux/fork.c`）：

```c
// glibc fork()
pid_t fork(void) {
    return _Fork();
}

pid_t _Fork(void) {
    pid_t pid;
    struct clone_args args = {
        .flags = CLONE_CHILD_SETTID,    // 只有这个 flag
        .pidfd = (uintptr_t)&pid,
    };
    if (clone3(&args, sizeof(args)) == -1)
        return -1;
    return pid;
}

// glibc vfork()
pid_t vfork(void) {
    struct clone_args args = {
        .flags = CLONE_VFORK | CLONE_VM,  // 这两个 flag
        .pidfd = (uintptr_t)&pid,
    };
    return clone3(&args, sizeof(args));
}

// pthread_create() 内部
int pthread_create(...) {
    struct clone_args args = {
        .flags = CLONE_VM | CLONE_FS | CLONE_FILES | CLONE_SIGHAND
              | CLONE_THREAD | CLONE_SYSVSEM | CLONE_SETTLS | ...,
        // ...
    };
    clone3(&args, sizeof(args));
}
```

**关键认知**：

- `fork()` ≈ `clone(CLONE_CHILD_SETTID)` —— 创建独立进程，共享尽量少
- `vfork()` ≈ `clone(CLONE_VM)` —— 子进程共享父进程地址空间
- `pthread_create()` ≈ `clone(CLONE_VM | CLONE_FS | CLONE_FILES | CLONE_SIGHAND | CLONE_THREAD | ...)` —— 创建线程，共享尽量多

**clone flags 决定了 copy_process 的"复制深度"**——这是 03 篇的核心，下面所有章节都围绕这点展开。

### 1.2 Android 14 上能看到的 fork 序列

```bash
# 跟踪 adb shell 启动 ls 时所有 fork / clone 调用
adb shell "strace -f -e trace=clone,clone3,fork,vfork /system/bin/ls /data"
```

输出（节选）：

```
clone3({flags=CLONE_CHILD_SETTID, ...}) = 1234   ← ls 主进程
execve("/system/bin/ls", ...)                  = 0
```

> 真实路径：`ls` 是单进程，没有线程。如果是 `system_server`，会看到大量 `clone3({flags=CLONE_VM|...})`——那是线程创建。

```bash
# 看 system_server 创建了多少线程
adb shell "ls /proc/$(pidof system_server)/task/ | wc -l"
```

输出（典型 Android 14）：

```
142
```

这就是 142 次 `clone()` 调用的累积——每次 Binder 线程 / 定时线程 / Worker 线程创建都会触发一次。

---

## 二、内核入口：sys_clone → _do_fork → copy_process

### 2.1 系统调用入口

```
用户态                          内核态
─────                          ──────
glibc clone3()
  ↓ sys_clone3
[syscall 指令]
                                ↓ entry_SYSCALL_64 (arch/arm64/kernel/entry.S)
                                ↓ do_sys_clone3 (kernel/fork.c)
                                ↓ _do_fork(args)
                                    ↓ copy_process()
                                    ↓ wake_up_new_task()
                                ↓ 返回 (long) pid → pt_regs → 用户态
```

### 2.2 关键源码入口

```c
// kernel/fork.c
SYSCALL_DEFINE3(clone, unsigned long, clone_flags, ...
{
    return _do_fork(clone_flags, newsp, 0, parent_tid, child_tid, 0);
}

SYSCALL_DEFINE2(clone3, struct clone_args __user *, uargs, size_t, size)
{
    struct clone_args args;
    if (copy_from_user(&args, uargs, size)) return -EFAULT;
    return _do_fork(args.flags, args.stack, args.stack_size,
                    &args.parent_tid, &args.child_tid, args.set_tid);
}

// fork() / vfork() 在内核侧等价于：
SYSCALL_DEFINE0(fork)
{
    return _do_fork(SIGCHLD, 0, 0, NULL, NULL, 0);
}

SYSCALL_DEFINE0(vfork)
{
    return _do_fork(CLONE_VFORK | CLONE_VM | SIGCHLD, 0, 0, NULL, NULL, 0);
}
```

**关键点**：
- `_do_fork` 是所有 fork / vfork / clone 的"统一入口"
- 第一个参数 `clone_flags` 决定 copy_process 怎么复制（10 篇详解的"复制深度"就靠这个 flags）
- `stack` 决定子进程用户栈起始地址（用户态传 NULL 表示子进程沿用父进程栈）
- `parent_tid` / `child_tid` 是用户态指定的两个 int*，内核会把分配的 pid 写回

### 2.3 _do_fork 的整体结构

```c
// kernel/fork.c
long _do_fork(unsigned long clone_flags,
              unsigned long stack_start,
              int stack_size,
              int __user *parent_tid,
              int __user *child_tid,
              unsigned long tls)
{
    struct task_struct *p;
    int trace = 0;
    long nr;

    // 1. 跟踪点
    if (!(clone_flags & CLONE_UNTRACED)) {
        if (clone_flags & CLONE_VFORK)
            trace = PTRACE_EVENT_VFORK;
        else if ((clone_flags & CSIGNAL) != SIGCHLD)
            trace = PTRACE_EVENT_CLONE;
        else
            trace = PTRACE_EVENT_FORK;

        if (likely(!ptrace_event_enabled(current, trace)))
            trace = 0;
    }

    // 2. 核心：复制 task_struct
    p = copy_process(clone_flags, stack_start, stack_size,
                     child_tid, NULL, trace, tls, NUMA_NO_NODE);
    add_latent_entropy();
    if (IS_ERR(p))
        return PTR_ERR(p);

    // 3. 任务统计
    task_struct_task_in(p);

    // 4. 唤醒新进程
    wake_up_new_task(p);

    // 5. vfork 特殊处理：父进程让出 CPU 直到子进程 exec / _exit
    if (clone_flags & CLONE_VFORK) {
        p->vfork_done = &vfork;
        init_completion(&vfork);
        complete_vfork_done:
            schedule();
    }

    // 6. 把 pid 写回用户态指定的 parent_tid 位置
    if (clone_flags & CLONE_PARENT_SETTID)
        put_user(nr, parent_tid);

    // 7. ptrace 报告
    if (trace) ptrace_event_pid(trace, p->pid);

    return nr;
}
```

**关键路径**：
1. `copy_process()` 是 _do_fork 的核心——完成所有 task_struct 字段填充
2. `wake_up_new_task()` 把新进程放上 runqueue
3. CLONE_VFORK 时父进程 `schedule()` 让出 CPU
4. 父进程返回时，子进程的 pid 通过返回值拿到

接下来 4 个章节逐个展开。

---

## 三、copy_process 第一阶段：task_struct 分配与基础字段

### 3.1 入口函数

```c
// kernel/fork.c
static __latent_entropy struct task_struct *copy_process(
    unsigned long clone_flags,
    unsigned long stack_start,
    int stack_size,
    int __user *child_tid,
    struct pid *pid,
    int trace,
    unsigned long tls,
    int node)
{
    struct task_struct *p;
    struct pid *pid_struct;

    // 1. flags 兼容性检查（早退）
    if ((clone_flags & (CLONE_NEWNS|CLONE_FS)) == (CLONE_NEWNS|CLONE_FS))
        return ERR_PTR(-EINVAL);
    if ((clone_flags & (CLONE_NEWUSER|CLONE_FS)) == (CLONE_NEWUSER|CLONE_FS))
        return ERR_PTR(-EINVAL);
    if ((clone_flags & CLONE_THREAD) && !(clone_flags & CLONE_SIGHAND))
        return ERR_PTR(-EINVAL);
    if ((clone_flags & CLONE_SIGHAND) && !(clone_flags & CLONE_VM))
        return ERR_PTR(-EINVAL);
    if (unlikely(clone_flags & CLONE_NEWUSER) && !ns_capable(current_user_ns(), CAP_SYS_ADMIN))
        return ERR_PTR(-EPERM);
    // ... 几十条 sanity check ...

    // 2. 进程数超过 rlimit 限制
    if (nr_threads >= max_threads)
        return ERR_PTR(-EAGAIN);

    // 3. 分配 task_struct slab
    p = alloc_task_struct_node(node);   // ← slab 分配，02 篇 §5.1 讲过
    if (!p)
        return ERR_PTR(-ENOMEM);

    // 4. 分配栈（thread_info + 异常栈 + 调度栈）
    p->stack = alloc_thread_stack_node(p, node);
    if (!p->stack) {
        free_task_struct(p);
        return ERR_PTR(-ENOMEM);
    }

    // 5. 零初始化（关键！）
    // task_struct 中很多字段用 kmem_cache_zalloc 自动清零
    // 但 stack 部分需要手动清零（因为里面是 thread_info + 内核栈）
    setup_thread_stack(p, current);
    ...
}
```

**关键认知**：
- `alloc_task_struct_node()` 来自 02 篇讲的专用 slab 缓存 `task_struct_cachep`
- task_struct 用 `kmem_cache_alloc()` 分配后 **默认是 zeroed**——所以多数指针字段会从 NULL 开始
- `setup_thread_stack(p, current)` 把父进程的 thread_info 复制给子进程作为初始值——子进程 fork 完会先回到"父进程的当前上下文"

### 3.2 第一阶段填充的字段

第一阶段后，task_struct 的状态：

| 字段组 | 来源 | 状态 |
|---|---|---|
| `pid` / `tgid` | 未分配 | 0 |
| `comm` | 由可执行文件名定 | 暂时等于父进程 |
| `state` | 默认 | `TASK_NEW`（一个临时标志） |
| `mm` | 暂时共享 | 与父进程相同 |
| `files` / `fs` | 暂时共享 | 与父进程相同 |
| `signal` / `sighand` | 暂时共享 | 与父进程相同 |
| `cred` | 默认 | `current_cred()` 引用 +1 |

**关键观察**：第一阶段 task_struct 几乎是空的，主要工作是把"父进程的镜像"装到子进程。第二阶段才决定"哪些资源是真的复制，哪些只共享"。

---

## 四、copy_process 第二阶段：资源账本复制

这是最复杂、最容易出错的部分。每个子系统对应一个 `copy_*()` 函数，**根据 clone_flags 决定"深拷贝"还是"引用 +1"**。

### 4.1 copy_creds：凭证复制

```c
// kernel/cred.c
int copy_creds(struct task_struct *p, unsigned long clone_flags)
{
    struct cred *new;
    int ret;

    // fork / 独立进程：复制 cred
    if (clone_flags & CLONE_THREAD) {
        // 线程：直接引用 current_cred()（共享）
        p->real_cred = get_current_cred();
        p->cred = p->real_cred;
        return 0;
    }

    new = prepare_creds();   // 复制当前 cred
    if (!new) return -ENOMEM;

    p->real_cred = get_cred(new);
    p->cred = get_cred(new);
    alter_cred_subscribers(new, 2);  // 引用计数 +2

    return 0;
}
```

**关键认知**：
- 普通 fork：复制 cred → 父子进程各有独立凭证（uid/gid/capabilities 可独立修改）
- 线程（CLONE_THREAD）：共享 cred → 修改一个线程的 uid 会影响所有线程
- setuid() 调用时只改 current 线程的 cred —— 不改线程组其他线程

### 4.2 copy_files：文件表复制

```c
// kernel/fork.c
int copy_files(unsigned long clone_flags, struct task_struct *tsk)
{
    struct files_struct *oldf, *newf;
    int error = 0;

    oldf = current->files;
    if (!oldf) goto out;

    // CLONE_FILES 标志：线程共享文件表
    if (clone_flags & CLONE_FILES) {
        atomic_inc(&oldf->count);   // 引用 +1
        tsk->files = oldf;
        goto out;
    }

    // 独立进程：复制整个文件表
    newf = dup_fd(oldf, &error);
    if (!newf) goto out;

    tsk->files = newf;
    error = 0;
out:
    return error;
}
```

**关键认知**：
- 普通 fork：`dup_fd()` 复制 `files_struct`（fd 表），但**文件描述符指向的 file* 不复制**——只是引用 +1
- CLONE_FILES：完全不复制，文件表共享
- Android 14 中 Zygote fork 时**会主动关闭部分 fd**（如 /dev/binder 在 fork 后才有）——这是 Framework 层做的，Kernel 不感知

### 4.3 copy_fs：文件系统上下文复制

```c
// kernel/fork.c
int copy_fs(unsigned long clone_flags, struct task_struct *tsk)
{
    struct fs_struct *fs = current->fs;
    if (!fs) return 0;
    if (clone_flags & CLONE_FS) {
        fs->users++;             // CLONE_FS：共享
        tsk->fs = fs;
        return 0;
    }
    tsk->fs = copy_fs_struct(fs);  // 普通 fork：复制
    return tsk->fs ? 0 : -ENOMEM;
}
```

**fs_struct 包含的内容**：
- `root`（根目录的 path / dentry）
- `pwd`（当前目录的 path / dentry）
- `umask`

普通 fork 会复制这两个目录引用，线程共享。

### 4.4 copy_sighand / copy_signal：信号表复制

```c
// kernel/fork.c
int copy_sighand(unsigned long clone_flags, struct task_struct *tsk)
{
    struct sighand_struct *sig;

    if (clone_flags & CLONE_SIGHAND) {
        // 线程共享 sighand
        refcount_inc(&current->sighand->count);
        tsk->sighand = current->sighand;
        return 0;
    }
    sig = kmem_cache_alloc(sighand_cachep, GFP_KERNEL_ACCOUNT);
    // 复制 sighand_action[]
    memcpy(sig->action, current->sighand->action, sizeof(sig->action));
    refcount_set(&sig->count, 1);
    tsk->sighand = sig;
    return 0;
}

int copy_signal(unsigned long clone_flags, struct task_struct *tsk)
{
    struct signal_struct *sig;

    if (clone_flags & CLONE_THREAD) {
        // 线程共享 signal_struct
        refcount_inc(&current->signal->sigcnt);
        tsk->signal = current->signal;
        return 0;
    }
    sig = kmem_cache_zalloc(signal_cachep, GFP_KERNEL_ACCOUNT);
    tsk->signal = sig;
    // 复制 pending queue / 退出状态 / OOM 信息...
    return 0;
}
```

**关键认知**：
- `sighand_struct`：handler 表（sigaction[]）—— 线程共享，进程复制
- `signal_struct`：线程组共享的信号信息（共享 pending、退出码、OOM 评分）—— 线程共享，进程复制
- 普通 fork 后父子进程有独立的 signal_struct 和 sighand_struct

### 4.5 copy_mm：地址空间复制（最关键）

这是最复杂也是 fork 的灵魂部分：

```c
// kernel/fork.c
static int copy_mm(unsigned long clone_flags, struct task_struct *tsk)
{
    struct mm_struct *mm, *oldmm;

    oldmm = current->mm;
    if (!oldmm) goto skip_mm;   // 内核线程

    // CLONE_VM：线程共享地址空间（vfork 也走这条路径）
    if (clone_flags & CLONE_VM) {
        mmget(oldmm);
        tsk->mm = oldmm;       // 共享！
        goto good_mm;
    }

    // 普通 fork：复制 mm_struct
    mm = dup_mm(tsk, current->mm);
    if (!mm) return -ENOMEM;

    tsk->mm = mm;
good_mm:
    tsk->active_mm = tsk->mm;
skip_mm:
    return 0;
}
```

接下来重点展开 `dup_mm()`。

### 4.6 dup_mm：mm_struct 深度复制（COW 在这里发生）

```c
// kernel/fork.c
static struct mm_struct *dup_mm(struct task_struct *tsk, struct mm_struct *oldmm)
{
    struct mm_struct *mm;
    int err;

    mm = allocate_mm();
    if (!mm) goto fail_nomem;

    memcpy(mm, oldmm, sizeof(*mm));   // 浅拷贝 mm_struct 主体
    // ... 后续修改 ...

    // 1. VMA 复制（虚拟内存区域）
    err = dup_mmap(mm, oldmm);
    if (err) goto free_pt;

    // 2. 页表复制（COW 关键）
    // 注意：不是真的复制物理页，只是修改页表项并标记只读
    return mm;
}
```

```c
// mm/memory.c
struct vm_area_struct *dup_mmap(struct mm_struct *mm, struct mm_struct *oldmm)
{
    // 遍历父进程 VMA 链表，逐个复制
    for (mpnt = oldmm->mmap; mpnt; mpnt = mpnt->vm_next) {
        if (mpnt->vm_flags & VM_DONTCOPY) continue;  // VM_IO / VM_DONTCOPY 等不复制
        tmp = vm_area_dup(mpnt);   // 复制 VMA 结构
        // ... 插入新链表 ...

        // 复制页表
        if (mpnt->vm_flags & VM_DONTCOPY)
            continue;
        copy_page_range(mm, oldmm, mpnt);
    }
}
```

**关键路径**：`copy_page_range()` 是 COW 的入口。

```c
// mm/memory.c
int copy_page_range(struct mm_struct *dst_mm, struct mm_struct *src_mm,
                    struct vm_area_struct *vma)
{
    // 简化版
    for (addr = vma->vm_start; addr < vma->vm_end; addr += PAGE_SIZE) {
        // 1. 读源页表项
        src_pte = pte_offset_map(src_pgd, addr);
        if (!pte_present(src_pte)) continue;  // 未映射页跳过
        if (is_cow_mapping(src_vma->vm_flags)) {
            // 2. COW：把页表项改成"只读" + "共享"
            ptep_set_wrprotect(src_mm, addr, src_pte);
            pte = pte_wrprotect(pte);
            pte = pte_mkold(pte);
        }
        // 3. 把同一个 PTE 写入目标进程的页表（共享同一物理页）
        set_pte_at(dst_mm, addr, dst_pte, pte);
    }
}
```

**关键认知**：
- 普通 fork 后，父子进程**指向同一组物理页**——物理页没复制
- 但**两个进程的页表都把这些页标成"只读"**
- 任一进程写这个页时，触发缺页异常（#PF）→ 走 COW 路径 → 真的分配新页 → 复制数据 → 修改 PTE 指向新页 → 恢复可写

### 4.7 COW 缺页异常：do_wp_page

```c
// mm/memory.c 简化
static vm_fault_t do_wp_page(struct vm_fault *vmf)
{
    // 1. 检查是否有"独占副本"
    if (PageAnon(vmf->page) && PageAnonExclusive(vmf->page)) {
        // 已经有独占副本，直接标可写
        wp_page_reuse(vmf);
        return 0;
    }

    // 2. 没有独占副本，分配新页
    new_page = alloc_page_vma(GFP_HIGHUSER_MOVABLE, vmf->vma, vmf->address);

    // 3. 复制内容
    copy_user_highpage(new_page, vmf->page, vmf->address, vmf->vma);

    // 4. 修改 PTE 指向新页
    vmf->page = new_page;
    wp_page_install(vmf);

    return 0;
}
```

**关键认知**：
- COW 触发后才真的复制——**fork() 本身开销很小**（只复制页表项）
- 大型进程 fork 出来的子进程，初始内存占用几乎为 0——直到子进程或父进程写入才涨
- 这是 Android 14 Zygote fork 优化的核心基础——所有应用进程共享 Zygote 的代码段

### 4.8 copy_mm 后续：清理 PF_FORKNOEXEC

```c
// kernel/fork.c
p->flags &= ~PF_FORKNOEXEC;
```

**关键**：`PF_FORKNOEXEC` 标记 fork 后还没 exec 的进程。这个 flag 影响 cgroup 的内存统计：

```c
// mm/memory.c
static inline void mm_account_pgfault(struct mm_struct *mm, ... )
{
    if (mm->task->flags & PF_FORKNOEXEC)
        return;  // 不计入 cgroup memory.events 统计
}
```

为什么？因为 fork 后子进程共享父进程的物理页，对 cgroup 来说"这部分内存不是子进程独占的"，不应该计入子进程的 memory 配额。这正是 Android 14 Zygote 优化的核心——预加载的代码段不算入子进程的内存。

---

## 五、copy_process 第三阶段：copy_thread 与子进程入口

### 5.1 copy_thread 在做啥

`copy_thread` 是 copy_process 的关键——它让子进程能"从正确的地方"开始跑。

```c
// arch/arm64/kernel/process.c
int copy_thread(unsigned long clone_flags, unsigned long stack_start,
                unsigned long top_of_stack, int __user *p,
                struct task_struct *p, unsigned long tls)
{
    struct pt_regs *childregs = task_pt_regs(p);

    // 1. 复制父进程的寄存器上下文
    *childregs = *current_pt_regs();

    // 2. 修改 childregs：子进程的返回值是 0
    childregs->regs[0] = 0;
    childregs->sp = stack_start;  // 新的用户栈

    // 3. 构造子进程的内核栈底
    p->thread.cpu_context.pc = (unsigned long)ret_from_fork;
    p->thread.cpu_context.sp = (unsigned long)childregs;

    // ... TLS 处理 ...
    return 0;
}
```

**关键认知**：
- `task_pt_regs(p)` 是子进程内核栈顶
- `*childregs = *current_pt_regs()` 把父进程当前的寄存器状态复制给子进程
- 子进程的 `regs[0]`（即 x0 寄存器）置 0 —— 这是 fork() 返回 0 的原因（syscall 返回值在 x0）
- `ret_from_fork` 是子进程第一次被调度时的入口——它会从内核栈恢复 regs 然后返回用户态

### 5.2 子进程从哪里开始跑

```
ret_from_fork (arch/arm64/kernel/entry.S)
  ↓
restore_all:
    // 从内核栈恢复通用寄存器（x0-x30）
    // x0 = 0（fork 返回值）
    // sp = stack_start（用户栈顶）
    // pc = 用户态断点（fork 系统调用之后的指令）
  ↓
eret                          // 异常返回：EL1 → EL0
  ↓
用户态 fork() 调用点之后的指令
```

**关键认知**：
- 子进程一开始就像父进程"刚刚从 fork() 返回"——只是返回值是 0
- 此时子进程和父进程的 PC、SP、通用寄存器几乎相同——但栈是新分配的
- 用户态看到 fork() 返回两个不同值（父进程返回 pid，子进程返回 0）就是靠这个 `regs[0] = 0`

### 5.3 TLS 处理（线程本地存储）

`copy_thread` 还处理 TLS（Thread Local Storage）——`clone` 时传入的 `tls` 参数被写入 `tpidr_el0` 寄存器：

```c
// arch/arm64/kernel/process.c
if (clone_flags & CLONE_SETTLS)
    p->thread.tpidr_el0 = tls;
```

用户态的 `__thread` 变量访问 `tpidr_el0`，所以每个线程有不同的 TLS 区。

---

## 六、copy_process 第四阶段：sched_fork 与 wake_up_new_task

### 6.1 sched_fork：初始化调度器视角

```c
// kernel/sched/core.c
int sched_fork(unsigned long clone_flags, struct task_struct *p)
{
    // 1. 初始化调度实体
    p->state = TASK_NEW;          // 临时状态，调度器跳过
    p->prio = current->normal_prio;
    p->static_prio = current->static_prio;
    p->normal_prio = current->normal_prio;
    p->sched_class = &fair_sched_class;  // 默认 CFS

    // 2. 初始化 se / rt / dl 调度实体
    init_sched_entity(p);
    init_sched_rt_entity(p);
    init_sched_dl_entity(p);

    // 3. 选择 CPU（多核调度）
    p->cpu = select_task_rq(p, ...);  // 09 篇会展开
    p->wake_cpu = p->cpu;

    // 4. cgroup 迁移（如果需要）
    if (unlikely(p->sched_in__)) {
        // 把父进程 cgroup 继承给子进程
    }
    return 0;
}
```

**关键**：
- `TASK_NEW` 是临时状态——新进程还没真正进入 runqueue
- 子进程的调度实体 `se` 是"零初始化"——没 vruntime、没在红黑树
- `select_task_rq()` 决定子进程第一次被调度时跑在哪颗 CPU——这是 09 篇的入口

### 6.2 wake_up_new_task：把子进程放上 runqueue

```c
// kernel/sched/core.c
void wake_up_new_task(struct task_struct *p)
{
    struct rq *rq;

    // 1. 选 CPU
    task_rq_lock(p, &rq);
    p->state = TASK_RUNNING;        // 解除 TASK_NEW

    // 2. 激活子进程（加入 runqueue）
    activate_task(rq, p, ENQUEUE_NOCLOCK);
    // 内部调用 enqueue_task(rq, p, flags)
    //   → enqueue_entity() if CFS
    //   → 加入红黑树（07 篇会展开）

    // 3. 设置"刚唤醒"标志（用于选择 CPU）
    p->on_rq = TASK_ON_RQ_QUEUED;

    // 4. 触发负载均衡
    check_preempt_curr(rq, p, WF_FORK);

    task_rq_unlock(rq, p);
}
```

**关键认知**：
- 子进程被加入父进程的 runqueue（默认）
- `check_preempt_curr()` 决定父进程是否被抢占——`sched_child_runs_first` 决定 fork 后谁先跑（默认子进程先跑，减少写时复制）
- 这是 Zygote fork 优化的关键——子进程可以几乎立刻被调度

### 6.3 父子进程谁先跑

```c
// kernel/sched/fair.c
int sysctl_sched_child_runs_first = 1;   // 默认 1：子进程先跑
```

**为什么子进程先跑更好？**
- 子进程通常紧接着 exec() —— 替换地址空间会让共享的物理页失效
- 让子进程先跑 → 共享页还热 → 父进程再被调度时这些页可能还在 TLB / 缓存里
- 这是经典的 fork+exec 模式优化——子进程先跑 exec 后立刻"扔掉"父进程的共享页

---

## 七、COW 的真实形态总结

### 7.1 fork 后的内存状态

```
fork 前:
  父进程 page table → 物理页 A (代码段)
                   → 物理页 B (数据段)

fork 后（立即）:
  父进程 page table → 物理页 A (r--, COW 标记)
                   → 物理页 B (rw-, COW 标记)
  子进程 page table → 物理页 A (r--, COW 标记)
                   → 物理页 B (rw-, COW 标记)

子进程写入 B 的某一行:
  缺页异常 → COW → 分配物理页 B' → 复制 B → 子进程 PTE 指向 B' (rw-)
  父进程 PTE 仍指向 B (rw-)

父进程之后也写 B 的某一行:
  缺页异常 → COW → 分配物理页 B'' → 复制 B → 父进程 PTE 指向 B'' (rw-)
  子进程 PTE 仍指向 B' (rw-)
```

### 7.2 COW 的代价

**不是免费的**：
- 每次 fork 后，父子进程都"几乎全只读"——任何写入都会触发缺页异常
- 缺页异常本身有开销（保存寄存器、查 PTE、分配新页、复制、恢复）—— 大约几微秒
- 大型进程 fork 后被立即 exec—— exec 会立刻释放共享页，COW 几乎不发生
- 大型进程 fork 后被立即 exec**且** exec 后立刻访问大量数据——大量缺页异常，但页是新的（exec 加载新程序）

**Android Zygote 受益于这个特性**：
- Zygote fork 后几乎立刻 exec 应用可执行文件
- 加载新程序的物理页与共享页完全无关——COW 几乎不发生
- 唯一共享的部分是 **Zygote 预加载的代码段**——但代码段本就是只读，COW 永远不会发生

---

## 八、vfork 的特殊语义

### 8.1 vfork 为什么存在

传统 fork 需要复制页表 + COW 标记，有性能开销。早期 Unix 实现希望"创建子进程后立刻 exec" 的模式能更快——这就是 vfork：

```c
SYSCALL_DEFINE0(vfork)
{
    return _do_fork(CLONE_VFORK | CLONE_VM | SIGCHLD, 0, 0, NULL, NULL, 0);
}
```

`CLONE_VM` 表示子进程**完全共享父进程的 mm_struct**——不复制、不 COW。

### 8.2 vfork 的特殊语义

```c
// kernel/fork.c _do_fork()
if (clone_flags & CLONE_VFORK) {
    p->vfork_done = &vfork;
    init_completion(&vfork);
complete_vfork_done:
    schedule();   // ← 父进程主动让出 CPU！
}
```

**vfork 后**：
1. 子进程被调度运行
2. 父进程进入 `wait_for_completion()`（阻塞）
3. 子进程**必须在调用 exec() 或 _exit() 之前不修改父进程的地址空间**
4. 子进程调用 exec() 或 _exit() 后，唤醒父进程

**为什么子进程不能用父进程的栈？** 因为 vfork 子进程和父进程共用栈——子进程一旦写了栈，会覆盖父进程的栈帧，导致父进程唤醒后崩溃。这就是为什么 vfork 子进程必须立刻 exec。

### 8.3 vfork 在现代 Linux 上的状态

**vfork 已被认为是危险的、不推荐的**。现代 libc 的 fork 几乎都不再用 vfork。

glibc 2.x 中：
- `fork()` 内部就是 `clone(CLONE_CHILD_SETTID)`（普通 fork）
- `vfork()` 是历史兼容接口保留
- Android 14 Bionic libc 中 `vfork()` 等价于 `fork()`（实际是 clone3 with CLONE_VFORK | CLONE_VM，但行为已经被改写得更安全）

**Android 14 上 vfork 的现实**：
```bash
# 大多数 Android 应用都不主动调用 vfork
# pthread_create() 也不用 vfork
# Zygote fork 用普通 fork + COW（Kernel 层实现的优化）

adb shell "strace -e trace=vfork /system/bin/ls" 2>&1 | head
# 输出通常为空（说明 vfork 不被调用）
```

---

## 九、clone flags 详解：复制深度全景表

下面用一个表把 clone flags 完整映射到 copy_process 的"复制深度"：

| flag | 含义 | copy_creds | copy_files | copy_fs | copy_mm | copy_sighand | copy_signal | copy_thread | 用例 |
|---|---|---|---|---|---|---|---|---|---|
| （无） | fork | 复制 | 复制 | 复制 | 复制（COW） | 复制 | 复制 | 复制+入口 | 默认 |
| `CLONE_VM` | 共享地址空间 | 共享 | 共享 | 共享 | **共享 mm** | 共享 | 共享 | 共享栈 | vfork |
| `CLONE_FS` | 共享 FS 上下文 | 共享 | 共享 | **共享** | 复制 | 复制 | 复制 | 复制 | pthread |
| `CLONE_FILES` | 共享文件表 | 共享 | **共享** | 复制 | 复制 | 复制 | 复制 | 复制 | pthread |
| `CLONE_SIGHAND` | 共享 sighand | 共享 | 共享 | 共享 | 复制 | **共享** | 共享 | 复制 | pthread |
| `CLONE_THREAD` | 共享 thread group | 共享 | 共享 | 共享 | 共享 | 共享 | **共享** | 共享 | pthread |
| `CLONE_NEWNS` | 新 mount namespace | 复制 | 复制 | **新 ns** | 复制 | 复制 | 复制 | 复制 | unshare -m |
| `CLONE_NEWUSER` | 新 user namespace | **新 ns** | 复制 | 复制 | 复制 | 复制 | 复制 | 复制 | unshare -U |
| `CLONE_NEWPID` | 新 PID namespace | 复制 | 复制 | 复制 | 复制 | 复制 | 复制 | 复制 | unshare -p |
| `CLONE_SYSVSEM` | 共享 System V 信号量 | 共享 | 共享 | 共享 | 共享 | 共享 | 共享 | 共享 | pthread |
| `CLONE_SETTLS` | 设置 TLS | — | — | — | — | — | — | **TLS** | pthread |

**这就是 pthread_create() 和 fork() 的本质区别**：
- pthread_create 是 clone 带上 CLONE_VM | CLONE_FS | CLONE_FILES | CLONE_SIGHAND | CLONE_THREAD | CLONE_SYSVSEM | CLONE_SETTLS
- fork 是 clone 几乎不带这些 flag
- 线程 = 几乎全部共享；进程 = 几乎全部独立

---

## 十、Android 14 实战：Zygote fork 优化在 Kernel 层的落点

### 10.1 Zygote fork 序列

Android 14 中，应用进程启动路径：

```
ActivityManager.startProcessLocked()
  ↓
Process.start()
  ↓
ZygoteProcess.zygoteRequest()
  ↓ 通过 socket 发到 zygote
ZygoteServer.runSelectLoop()
  ↓
ZygoteConnection.processOneCommand()
  ↓
Zygote.forkAndSpecialize()           ← 用户态 fork()
  ↓
NativeForkAndSpecialize.doFork()    ← JNI
  ↓
fork()                              ← syscall
```

### 10.2 Kernel 层的 Zygote 优化

Zygote 优化的本质是 **让 fork 更快 + 让 fork 后所有应用进程共享相同的"基础内存"**。

```bash
# 看 Zygote 进程占用的内存
adb shell "cat /proc/$(pidof zygote64)/status | grep -E 'VmRSS|VmSize'"
```

输出（典型）：

```
VmSize:       4194304 kB     ← Zygote 自身占用 ~4GB（含 ART 预加载）
VmRSS:         524288 kB     ← 物理驻留 ~512MB
```

```bash
# 看一个应用进程的内存（fork 自 Zygote）
adb shell "cat /proc/$(pidof com.tencent.mm)/status | grep -E 'VmRSS|VmSize'"
```

输出：

```
VmSize:        524288 kB     ← 应用进程 ~512MB（与 Zygote 共享代码段）
VmRSS:          65536 kB     ← 物理驻留 ~64MB（应用自己独有的部分）
```

**为什么应用进程的 VmSize 比 Zygote 小？**
- 因为 Zygote 预加载的所有类（`preload()`）在 fork 后被所有应用共享
- 应用进程"看到"的 VmSize 是自身独有的部分 + 共享部分（但统计上可能只算独占部分）

### 10.3 优化点 1：Zygote fork 后立刻 exec

Zygote fork 后，子进程几乎立刻 exec 应用可执行文件——这正是 fork+exec 模式：

```c
// Zygote fork 后立刻 exec
pid_t pid = fork();
if (pid == 0) {
    // 子进程：exec 应用
    execve("/system/bin/app_process", ...);
}
```

**Kernel 层优化**：由于 fork + exec 之间没有大量写入，COW 几乎不发生——fork 本身的开销很小。

### 10.4 优化点 2：PF_FORKNOEXEC flag

fork 后未 exec 的子进程打上 `PF_FORKNOEXEC`：

```c
// kernel/fork.c
p->flags |= PF_FORKNOEXEC;
```

cgroup 内存统计忽略 `PF_FORKNOEXEC` 进程的"fork 期间临时内存"——避免 Zygote fork 应用时内存瞬时飙升触发误杀。

### 10.5 优化点 3：CLONE_CHILD_SETTID + pidfd

Android 14 通过 `clone3(CLONE_CHILD_SETTID)` 创建子进程时，内核把分配的 pid 写入用户态指定的 int*：

```c
struct clone_args args = {
    .flags = CLONE_CHILD_SETTID,
    .pidfd = (uintptr_t)&pid,
};
clone3(&args, sizeof(args));
```

这让 Framework 不需要额外调用 `gettid()` 就能拿到 pid——减少了一次 syscall。

---

## 十一、稳定性排查：fork 失败 / 子进程僵死 / 资源泄漏

### 11.1 fork 失败常见原因

```bash
# 看 fork 失败错误码
adb shell "strace -e trace=clone,clone3 /system/bin/ls 2>&1"
```

输出：

```
clone3(...) = -1 EAGAIN (Resource temporarily unavailable)
```

**常见原因**：
- `nr_threads >= max_threads`：系统线程数超限
- `pid 分配失败`：PID namespace 已满（默认 32768 个）
- `alloc_task_struct_node` 失败：内存不足
- `copy_*()` 失败：某个子系统初始化失败

### 11.2 子进程僵死

fork 后如果父进程没注册 SIGCHLD handler，子进程退出后变成 zombie（02 篇 §3.4）。

```bash
# 看僵尸进程
adb shell "ps -A | grep '<defunct>'"
```

输出：

```
root  1234  567   1  ... <defunct>
```

**排查**：
- 找父进程 `567` 的代码，看它是否在 wait() / waitpid()
- 看父进程的 strace：`strace -p 567 -e trace=wait4`
- 如果父进程就是僵尸——链式僵尸，只能重启系统

### 11.3 资源泄漏

fork 后不 exec，父子进程共享文件描述符。任一方 close() 不影响另一方的引用计数——但父进程 close 后，子进程的引用计数才生效。

```c
// 危险代码（Android 不常见，仅示例）
int fd = open("file.txt", O_RDWR);
if (fork() == 0) {
    // 子进程：fd 有效
    write(fd, "child\n", 6);
    // exit 时 fd 被 close
} else {
    // 父进程：fd 有效
    write(fd, "parent\n", 7);
    close(fd);
}
```

**问题**：父子进程同时写同一个 fd，可能产生交错输出——这是 bug 而非资源泄漏。

### 11.4 fork 风暴

```bash
# 看 fork 速率（每个进程的 fork 计数）
adb shell "cat /proc/$(pidof system_server)/status | grep -E 'voluntary_ctxt_switches|nonvoluntary_ctxt_switches'"
# 这只能看上下文切换，看不到 fork 计数
# 看 fork 计数：
adb shell "echo; cat /proc/sys/kernel/fork_count_total"  # 不存在

# 间接方法：trace
adb shell "perfetto --record -o /data/local/tmp/trace.proto -e 'sched:sched_process_fork' --time 5"
```

fork 风暴的根因通常是：
- 启动多个 Service / Receiver 时重复 fork
- 第三方 SDK 滥用 fork（如某些 Native 模块）
- 系统 PID namespace 耗尽

---

## 十二、给 04 篇留的钩子

读完 03 篇，你应该能：

1. 跟踪 fork / clone / vfork 在内核里的完整路径。
2. 理解 copy_process 中 4 个阶段分别做什么。
3. 理解 COW 的实现——fork 后物理页没真的复制，写入时才复制。
4. 理解 vfork 的危险语义，知道为什么它被废弃。
5. 在脑中建立"clone flags → copy_process 复制深度"的映射表。

04 篇《进程的执行：execve 与程序加载》会回答：

> 进程诞生后是个空壳——子进程怎么从一个空 task_struct 变成"能跑 /system/bin/ls 的进程"？
>
> - `sys_execve()` → `do_execveat_common()` → `search_binary_handler()` → `load_elf_binary()`
> - ELF 格式怎么被解析
> - 动态链接器怎么被加载
> - 进程地址空间怎么从 Zygote 的预加载态变成应用进程的最终态

读完 03 + 04 两篇，你应该能把"一个进程从诞生到执行第一个指令"的完整故事讲清楚——这是 Android 14 应用启动优化的核心（Framework/Process 系列 02 篇会回扣）。

---

## 小结

| 维度 | 一句话总结 |
|---|---|
| fork 本质 | 所有 fork / vfork / clone 都是同一个 `clone()`，区别只在 flags 组合 |
| copy_process 4 阶段 | 分配 → 资源账本复制 → 子进程入口构造 → 唤醒调度 |
| COW 关键 | fork 不复制物理页，只把两个页表项都标只读；写入时才真的复制 |
| vfork 特殊 | 父子共享地址空间 + 父让出 CPU，已被现代 libc 视为危险接口 |
| clone flags 表 | 决定了 copy_process 哪个子系统共享、哪个子系统复制 |
| Android Zygote | 利用 fork+exec 模式 + COW，让所有应用进程共享 Zygote 的预加载代码 |

---

## 给下篇的桥

**本篇留下三个钩子**：

1. 子进程 fork 后是个"空壳"——04 篇讲 execve 怎么把它变实
2. COW 让 Zygote fork 几乎免费——但 COW 的边界在 exec 时被打破
3. `ret_from_fork` 子进程入口——04 篇会回扣"exec 后这个入口怎么被替换"

如果读完本文仍有疑问：

- **"copy_process 真的只是 memcpy 吗？"** → 不是。本篇 §4.6 给出 dup_mm 的真实路径——含 COW 标记
- **"我想看 fork 时的页表"** → 13 篇会讲 perfetto / bpftrace 实战
- **"Zygote fork 优化具体在哪里"** → §10.3-10.5

---

## 引用

| 引用 | 路径 |
|---|---|
| 系统调用入口 | `kernel/fork.c:do_sys_clone3 / _do_fork / SYSCALL_DEFINE0(fork)` |
| copy_process | `kernel/fork.c:copy_process` |
| copy_creds | `kernel/cred.c:copy_creds` |
| copy_files | `kernel/fork.c:copy_files / dup_fd` |
| copy_mm | `kernel/fork.c:copy_mm / dup_mm` |
| dup_mmap | `mm/memory.c:dup_mmap` |
| copy_page_range | `mm/memory.c:copy_page_range` |
| COW 缺页 | `mm/memory.c:do_wp_page` |
| copy_thread | `arch/arm64/kernel/process.c:copy_thread` |
| sched_fork | `kernel/sched/core.c:sched_fork` |
| wake_up_new_task | `kernel/sched/core.c:wake_up_new_task` |
| Framework 镜像 | [Framework/Process/02-Process启动与生命周期](../../Android_Framework/Process/02-Process启动与生命周期.md) |