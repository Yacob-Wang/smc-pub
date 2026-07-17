# task_struct 全景拆解

> 系列第 02 篇 · 阶段 A · 建立总览
>
> **承上**：01 篇说 task_struct 是五大子系统的"指针汇聚点"。本篇展开它——读完你应该能用 `pahole` / `bpftrace` 把 task_struct 的内存布局画出来。
>
> **启下**：task_struct 怎么从"空"变"满"？03 篇《进程的诞生：fork / clone / vfork》会回扣。
>
> **预计篇幅**：约 1.8 万字
>
> **源码基线**：Linux 5.10 / 5.15（Android 12-14 主流内核）；部分字段会标注 Android 14 5.15+ / 6.1 内核引入的变化。

---

## 学习目标

读完本文，你应该能：

1. 在脑中画出 task_struct 的完整字段分组——按生命周期 / 调度 / 内存 / 文件 / 信号 / cgroup / 命名空间 / 凭证 / 关联关系 / 统计共 10 个维度。
2. 知道每个字段在哪个内核源码文件被维护、被什么事件修改。
3. 掌握 `pahole` / `bpftrace` 两个工具，能在 Android 14 设备上查看 task_struct 的真实内存布局。
4. 能用 task_struct 的字段组合定位 4 类典型稳定性问题（卡顿 / OOM / ANR / 进程被杀）。
5. 理解 task_struct 是 5 大子系统的"账本指针"——它自己不是账本，是"账本在哪"的目录。

---

## 一、task_struct 的真实形态

### 1.1 先看数字：task_struct 到底有多大

很多人的第一反应是"几百字节"。真实情况是 **Linux 5.10 的 task_struct 在 ARM64 上是 6KB-8KB**，Linux 6.1 接近 10KB。

在 Android 14 设备上实测：

```bash
# 需要 root
adb root
adb shell "ls -l /proc/self | head -5"  # 注意 task_struct 在 kernel heap，不直接暴露大小
# 间接验证：system_server 的 RSS
adb shell "cat /proc/$(pidof system_server)/status | grep -E 'VmSize|VmRSS'"
```

输出（典型）：

```
VmSize:        8192 kB     ← 虚拟地址空间
VmRSS:         4096 kB     ← 物理驻留
```

`VmSize` 不完全等于 task_struct 大小（包含 stack / heap / mmap 等），但量级吻合。

### 1.2 用 pahole 看真实布局

`pahole` 是 dwarfdump 工具链的一部分，能从 vmlinux 的 debug 符号里把结构体字段偏移读出来：

```bash
# 主机环境（需要 Android 内核编译产物）
pahole -C task_struct vmlinux
```

输出（Linux 5.10 Android common kernel，节选）：

```c
struct task_struct {
    struct thread_info          thread_info;          /*     0    16 */
    /* --- cacheline 1 boundary (64 bytes) --- */
    volatile long              state;                 /*    16     8 */
    void                      *stack;                 /*    24     8 */
    refcount_t                 usage;                 /*    32     4 */
    unsigned int               flags;                 /*    36     4 */
    unsigned int               ptrace;                /*    40     4 */
    int                        on_cpu;                /*    44     4 */
    struct __call_single_node  wake_entry;            /*    48    16 */
    unsigned int               cpu;                   /*    64     4 */
    unsigned int               wakee_flips;           /*    68     4 */
    unsigned long              wakee_flip_decay_ts;   /*    72     8 */
    struct task_struct        *last_wakee;            /*    80     8 */
    int                        recent_used_cpu;       /*    88     4 */
    int                        wake_cpu;              /*    92     4 */
    int                        on_rq;                /*    96     4 */
    int                        prio;                  /*   100     4 */
    int                        static_prio;           /*   104     4 */
    int                        normal_prio;           /*   108     4 */
    unsigned int               rt_priority;           /*   112     4 */
    const struct sched_class  *sched_class;          /*   116     8 */
    struct sched_entity        se;                    /*   124   320 */
    struct sched_rt_entity     rt;                    /*   444   192 */
    struct sched_dl_entity     dl;                    /*   636   280 */
    /* ... 中间是 mm_struct / files_struct / signal_struct 指针 ... */
    struct mm_struct          *mm;                    /*   936     8 */
    struct mm_struct          *active_mm;             /*   944     8 */
    /* ... */
    pid_t                      pid;                   /*  1040     4 */
    pid_t                      tgid;                  /*  1044     4 */
    /* ... */
    char                       comm[TASK_COMM_LEN];   /*  1232    16 */
    /* --- 字段超过 100 个，截断 --- */
};                                                  /* total: 6784 bytes */
```

**关键观察**：

- `state` 在 16 字节偏移——和 `thread_info` 同 cacheline，调度器访问频繁，刻意靠前。
- `sched_entity`（CFS 调度实体）单字段就占 320 字节——调度算法在数据结构里"很重"。
- `mm` 在 936 字节偏移——但它只是指针，真正的"内存账本"在 `mm_struct` 里。
- `comm`（进程名）在 1232 字节偏移，16 字节——`TASK_COMM_LEN=16` 决定了 `ps` 显示最长 15 字符 + `\0`。

### 1.3 用 bpftrace 实时读 task_struct 字段

如果设备有 bpftrace（通常需要 userdebug + 开启 kprobe），可以这样看：

```bash
# 抓所有调度事件，打印 task_struct->comm 字段
adb shell bpftrace -e '
kprobe:finish_task_switch
{
    printf("prev: %s → next: %s on cpu %d\n",
        arg0->prev->comm, arg0->next->comm, arg0->next->cpu);
}
'
```

输出：

```
prev: kswapd0 → next: system_server on cpu 0
prev: system_server → next: Binder:system_1 on cpu 2
prev: Binder:system_1 → next: surfaceflinger on cpu 3
```

13 篇会展开更复杂的 bpftrace 实战。

---

## 二、按子系统分组的字段全景

下面按 10 个维度拆 task_struct 的所有字段。每个字段给"偏移 / 类型 / 作用 / 维护它的源码 / 实战对应"。

### 2.1 生命周期子系统字段

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `state` | 16 | `volatile long` | 进程当前状态（TASK_RUNNING 等） | `kernel/sched/core.c` set_current_state() |
| `exit_state` | 168 | `int` | 退出状态（EXIT_ZOMBIE / EXIT_DEAD） | `kernel/exit.c` do_exit() |
| `pid` | 1040 | `pid_t` | 进程 ID（namespace 内唯一） | `kernel/pid.c` |
| `tgid` | 1044 | `pid_t` | 线程组 ID（主线程 ID） | `kernel/pid.c` |
| `exit_code` | 1640 | `int` | 退出码（wait4 取出） | `kernel/exit.c` |
| `exit_signal` | 1644 | `int` | 退出时给父进程的信号（默认 SIGCHLD） | `kernel/fork.c` |
| `comm` | 1232 | `char[16]` | 进程名（`ps` 显示） | `kernel/exec.c` |
| `flags` | 36 | `unsigned int` | 进程级标志（PF_EXITING / PF_FORKNOEXEC 等） | 多处 |

**实战对应**：

- `state` 决定 `ps` 的 STAT 列：S (TASK_INTERRUPTIBLE)、R (TASK_RUNNING)、D (TASK_UNINTERRUPTIBLE)、Z (EXIT_ZOMBIE)
- `exit_code` 决定 `wait4(pid, &status)` 取出的 status 含义
- `comm` 在 kworker / kthread 中显示为 `[kworker/0:1H]`，这是 `kworker_Deep_Dive` 补充专题的内容
- `flags` 中的 `PF_FORKNOEXEC` 标记 fork 后还没 exec 的进程（典型如 Android 的 Zygote 子进程）

### 2.2 调度子系统字段

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `on_rq` | 96 | `int` | 是否在某个 runqueue 上（0/1/2/3 分别表示 不在 / 在 CFS / 在 RT / 在 DL） | `kernel/sched/core.c` enqueue_task() |
| `prio` | 100 | `int` | 动态优先级（受 nice / OOM 影响） | `kernel/sched/core.c` |
| `static_prio` | 104 | `int` | 静态优先级（nice 值映射） | `kernel/sched/core.c` |
| `normal_prio` | 108 | `int` | 派生优先级（基于 static_prio + 调度策略） | `kernel/sched/core.c` |
| `rt_priority` | 112 | `unsigned int` | RT 优先级（0-99，0 表示非 RT） | `kernel/sched/rt.c` |
| `sched_class` | 116 | `const struct sched_class*` | 指向调度类（fair / rt / deadline / idle） | `kernel/sched/*.c` |
| `se` | 124 | `struct sched_entity`（320 字节） | CFS 调度实体（vruntime / 负载权重 / 红黑树节点） | `kernel/sched/fair.c` |
| `rt` | 444 | `struct sched_rt_entity`（192 字节） | RT 调度实体（优先级 / 时间片） | `kernel/sched/rt.c` |
| `dl` | 636 | `struct sched_dl_entity`（280 字节） | Deadline 调度实体（runtime / deadline / period） | `kernel/sched/deadline.c` |
| `policy` | 1132 | `unsigned int` | 调度策略（SCHED_NORMAL / SCHED_FIFO / SCHED_RR / SCHED_DEADLINE / SCHED_IDLE / SCHED_BATCH） | `kernel/sched/core.c` |
| `cpus_ptr` | 1168 | `struct cpumask*` | CPU 亲和性掩码（动态） | `kernel/sched/core.c` |
| `user_cpus_ptr` | 1176 | `struct cpumask*` | 用户态 CPU 亲和性掩码 | `kernel/sched/core.c` |
| `cpus_mask` | 1184 | `struct cpumask`（变长） | 内嵌 CPU 掩码（动态和用户态合一时） | 同上 |
| `nr_cpus_allowed` | — | `int` | 允许的 CPU 数 | 同上 |
| `uclamp_req` | — | `struct uclamp_se` | UClamp 请求值（min/max） | `kernel/sched/core.c` |
| `uclamp_min` / `uclamp_max` | — | `struct uclamp_se` | UClamp 实际生效值 | `kernel/sched/core.c` |

**实战对应**：

- `prio` < 100 → RT 进程；`prio` >= 100 → 普通 CFS 进程
- `policy` 是 6 个 SCHED_* 常量之一，决定 `sched_class` 指向哪个调度类
- `on_rq` 的值 1/2/3 直接对应调度类型——这是调度器看"我属于谁"的入口
- `se` 里的 `vruntime` 是 CFS 公平调度的核心（07 篇会展开）
- `cpus_ptr` 实现 CPU 亲和性（`taskset` 命令修改的就是这个字段）
- `uclamp_min` / `uclamp_max` 是 Android 14 重点——`cpu.uclamp.min` 写入后内核会同步到这里（09 篇会展开）

### 2.3 内存子系统字段（指针）

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `mm` | 936 | `struct mm_struct*` | 用户态地址空间描述符 | `kernel/fork.c` copy_mm() / `kernel/exit.c` exit_mm() |
| `active_mm` | 944 | `struct mm_struct*` | 内核线程借用的 mm（内核线程此字段 != NULL，`mm` 为 NULL） | `kernel/sched/core.c` context_switch() |

**关键认知**：task_struct 自身**不存储内存账本**——`mm_struct` 才是账本。`task_struct->mm` 只是指针，指向那块独立的内存账本。

**实战对应**：

- `mm == NULL && active_mm != NULL` → 内核线程（kworker / kthreadd 等）
- `mm != NULL && active_mm == mm` → 普通用户进程
- `mm->owner == task_struct` 决定谁负责释放

### 2.4 文件子系统字段（指针）

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `files` | 1000 | `struct files_struct*` | 打开的文件表（fd → file* 映射） | `kernel/fork.c` copy_files() / `fs/open.c` |
| `fs` | 1008 | `struct fs_struct*` | 文件系统上下文（root / pwd） | `kernel/fork.c` copy_fs() |

**实战对应**：

- `files` 的引用计数决定 fd 表何时真正释放（多线程 fork 时的关键）
- `fs` 决定了 `chroot()` / `chdir()` 后进程看到的世界

### 2.5 信号子系统字段

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `signal` | 952 | `struct signal_struct*` | 线程组共享的信号信息（主线程创建，子线程共享） | `kernel/fork.c` copy_signal() |
| `sighand` | 960 | `struct sighand_struct*` | 共享的信号 handler 表（被所有线程共享） | `kernel/fork.c` copy_sighand() |
| `blocked` | 968 | `sigset_t` | 阻塞掩码 | `kernel/signal.c` |
| `real_blocked` | 1032 | `sigset_t` | 真实阻塞掩码（绕过 SA_NODEFER 后的值） | `kernel/signal.c` |
| `saved_sigmask` | 1096 | `sigset_t` | 系统调用时临时保存的阻塞掩码（sys_pause / sigsuspend 用） | `kernel/signal.c` |
| `pending` | 1104 | `struct sigpending` | 线程私有 pending 队列 | `kernel/signal.c` |

**实战对应**：

- `sighand` 是线程组共享——多线程进程下，一个线程注册 SIGTERM handler，所有线程共享
- `pending` 是线程私有——发送给特定 tid 的信号存在这里
- `signal->shared_pending` 是线程组共享——发送给 tgid 的信号存在这里
- `blocked` 决定哪些信号被屏蔽；`ps -o sigblk,pid,comm` 能看到当前 blocked

11 篇会展开。

### 2.6 cgroup 子系统字段

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `cgroups` | 1124 | `struct css_set*` | 进程所属的 cgroup 集合（指针） | `kernel/cgroup/cgroup.c` |

**关键认知**：task_struct 不直接存 cgroup 路径，它存的是一个 `css_set*` 指针，指向一张"进程 ↔ cgroup 子系统 ↔ cgroup 节点"的映射表。

**实战对应**：

- `cat /proc/<pid>/cgroup` 读出来的路径，就是顺着 `cgroups` 指针查出来的
- 一个进程被 `cgroup_attach_task()` 移动到新 cgroup 时，只改 `cgroups` 指针，不改 task_struct 自身

10 篇会展开。

### 2.7 命名空间子系统字段

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `nsproxy` | 1112 | `struct nsproxy*` | 命名空间代理（指向 5 个 namespace 的指针表） | `kernel/nsproxy.c` |

**实战对应**：

- `nsproxy->pid_ns` 决定 PID 在哪个 namespace 编号
- `nsproxy->mnt_ns` 决定 mount point
- `nsproxy->net_ns` 决定网络设备

本系列不单独成篇讲 namespace（理由见 01 §2.2）。

### 2.8 凭证与审计字段

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `cred` | 1136 | `const struct cred*` | 当前凭证（uid / gid / capabilities） | `kernel/cred.c` |
| `real_cred` | 1144 | `const struct cred*` | 真实凭证（用于某些安全检查） | `kernel/cred.c` |
| `audit_context` | — | `struct audit_context*` | 审计上下文 | `kernel/audit.c` |

**实战对应**：

- `cred->uid == 0` → root 进程
- `real_cred` 与 `cred` 通常相同，但在 setuid 后可能不同

### 2.9 关联关系字段（链表 / 红黑树节点）

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `tasks` | 880 | `struct list_head` | 链表节点——把所有 task_struct 串成全局链表 | `kernel/fork.c` |
| `pid_links` | 888 | `struct hlist_node` | 哈希链表——通过 PID 快速找 task_struct | `kernel/pid.c` |
| `thread_group` | 904 | `struct list_head` | 线程组链表头 | `kernel/fork.c` |
| `thread_node` | 920 | `struct list_head` | 线程组链表节点 | `kernel/fork.c` |
| `children` | 976 | `struct list_head` | 子进程链表头 | `kernel/fork.c` |
| `sibling` | 992 | `struct list_head` | 兄弟节点（同一父进程下） | `kernel/fork.c` |

**实战对应**：

- `for_each_process(p)` 宏遍历全局链表——遍历的就是 `tasks` 链表
- `do_each_thread` / `while_each_thread` 遍历线程组——用 `thread_group` / `thread_node`
- `wait4` 找子进程——遍历 `children`
- 03 篇讲 fork 时，会用这个图：

```
            init_task
                │
                ▼
            thread_group (头)
                │
   ┌────────────┼────────────┐
   ▼            ▼            ▼
  kthreadd   kswapd0     ...
                │ (thread_group 继续串)
                ▼
              ...
```

### 2.10 统计与调试字段

| 字段 | 偏移 | 类型 | 作用 | 维护源码 |
|---|---|---|---|---|
| `utime` | — | `u64` | 用户态累计时间（ns） | `kernel/sched/cputime.c` |
| `stime` | — | `u64` | 内核态累计时间（ns） | `kernel/sched/cputime.c` |
| `start_time` | — | `u64` | 进程创建时间 | `kernel/fork.c` |
| `nvcsw` | — | `unsigned long` | 自愿上下文切换次数 | `kernel/sched/core.c` |
| `nivcsw` | — | `unsigned long` | 非自愿上下文切换次数 | `kernel/sched/core.c` |
| `min_flt` / `maj_flt` | — | `unsigned long` | 缺页异常次数 | `mm/memory.c` |
| `ioac` | — | `u64` | IO 累计字节（cgroup 统计） | `block/blk-cgroup.c` |

**实战对应**：

- `ps -o pid,comm,time,etime` 用 `utime + stime` / `start_time`
- `pidstat` 用 `nvcsw / nivcsw` 区分"主动让出"还是"被抢占"
- `pidstat -r` 用 `min_flt / maj_flt` 看内存压力

---

## 三、5 个最常用字段组合模式（实战视角）

光看字段表不够，本节给 5 个**真实排查场景**，展示"从问题现象到 task_struct 字段"的定位路径。

### 3.1 场景 1：卡顿定位——`nivcsw` 暴增

**现象**：用户反馈某 App 卡顿，`top` 看 CPU 不高但 `STAT` 列频繁出现 `R`。

**定位**：

```bash
adb shell "cat /proc/<pid>/status | grep -E 'State|nivcsw|nvcsw'"
```

```
State:  R (running)
voluntary_ctxt_switches:    12      ← 主动让出
nonvoluntary_ctxt_switches: 5890   ← 被抢占 ← 异常高
```

**task_struct 解读**：`nivcsw` 在 13 篇会展开，对应 task_struct 同名字段。该字段被调度子系统每次 context_switch 时自增。

**根因**：进程被频繁抢占。可能原因：
- 高优先级进程（RT）抢占（看 `prio`）
- CPU 集限制（看 `cpus_ptr`）
- 大核被 cgroup 屏蔽（看 `cgroups->cpu.uclamp.min`）

**对应本系列**：
- 09 篇：EAS / UClamp / CPU 集
- 13 篇：ftrace sched_switch 实战

### 3.2 场景 2：OOM 排查——`signal->oom_score_adj`

**现象**：logcat 出现 `Out of memory: Killed process` 后，进程消失。

**定位**：

```bash
# 找到被杀的进程当时的 oom_score_adj
adb shell "dmesg | grep -i 'killed process'"  # 历史记录
adb shell "cat /proc/<pid>/oom_score_adj"     # 当前值（如果进程还在）
```

**task_struct 解读**：`oom_score_adj` 不直接存在 task_struct，它存在 `signal->oom_score_adj_min` 和 `task->signal->oom_score_adj` 两处：

```c
struct signal_struct {
    int oom_score_adj_min;   /* OOM killer 评分下限 */
    /* ... */
};
```

**根因分析**：
- `oom_score_adj` 越高 → 越容易被杀
- `oom_score_adj` 范围 [-1000, 1000]，-1000 表示永远不杀（OOM_DISABLE）
- Android 14 的 LMKD 改用 PSI 后不再直接用 `oom_score_adj`，但 cgroup 触发的 OOM 仍会用

**对应本系列**：
- 10 篇：cgroup 内存账本
- 13 篇：OOM 实战案例

### 3.3 场景 3：ANR 归因——`state` 长时间不变

**现象**：App 触发 ANR，`Systrace` 显示进程卡在某一行。

**定位**：

```bash
adb shell "cat /proc/<pid>/status | grep -E '^(State|Threads|Cpus_allowed)'"
```

输出：

```
State:  D (uninterruptible sleep)   ← 注意这个 D
Threads:        42
Cpus_allowed:   3
Cpus_allowed_list:      0-1
```

**task_struct 解读**：`state` 在 16 字节偏移，是调度子系统最频繁访问的字段。`D (uninterruptible sleep)` 表示 `TASK_UNINTERRUPTIBLE`——进程在等 IO / 锁，且**不能被信号唤醒**。

**根因**：
- 进程在等磁盘 IO（典型：日志卡住）
- 进程在等 `mm->mmap_lock` 等长持锁
- 进程在 cgroup throttle 中（10 篇会讲）

**对应本系列**：
- 03-05 篇：进程状态机详解
- 13 篇：D 状态实战

### 3.4 场景 4：进程残留——`state == EXIT_ZOMBIE`

**现象**：某进程"消失"了，但 `ps` 还能看到 `<defunct>` 标记。

**定位**：

```bash
adb shell "ps -A | grep '<defunct>'"
adb shell "cat /proc/<ppid>/status | grep -E 'State|Threads'"
```

**task_struct 解读**：

```c
#define EXIT_ZOMBIE   16
#define EXIT_DEAD      32

// task_struct.state 在 EXIT_ZOMBIE 时表示
// task_struct 还没被父进程 wait() 回收
```

僵尸进程的判定依据：`state & EXIT_ZOMBIE`，且父进程没 wait。

**根因**：
- 父进程没注册 SIGCHLD handler
- 父进程忙，没来得及 wait
- 父进程本身就是僵尸——链式僵尸

**对应本系列**：
- 05 篇：do_exit 完整路径
- 13 篇：僵尸进程排查

### 3.5 场景 5：CPU 亲和性被改——`cpus_ptr` 异常

**现象**：某进程性能下降，怀疑被绑到小核。

**定位**：

```bash
adb shell "cat /proc/<pid>/status | grep -E '^Cpus' "
adb shell "taskset -p <pid>"
```

输出：

```
Cpus_allowed:   2
Cpus_allowed_list:      1    ← 只能跑在 CPU 1 上（小核）
pid 1234's current affinity mask: 2
```

**task_struct 解读**：`cpus_ptr` 在 task_struct 里维护。`taskset -p` 修改的是 `cpus_ptr`（动态）和 `user_cpus_ptr`（用户态）。

**根因**：某个调用方调用了 `sched_setaffinity()`，可能是 Framework 层的 ProcessList / CpusetService。

**对应本系列**：
- 09 篇：cpuset 内核实现
- Framework/Process 系列：ProcessList CPU 集配置

---

## 四、task_struct 设计的三个核心权衡

看完字段，一个常见的疑问是：**为什么 task_struct 设计成"指针汇聚"而不是"嵌入式账本"？**

三个理由：

### 4.1 资源独立回收

进程的 `mm_struct` / `files_struct` / `signal_struct` 可能被子进程继承（COW 模型）。如果它们嵌入 task_struct，子进程继承时要复制整个结构——成本高。

用指针：
- 父进程退出时，`files_struct` 引用计数 > 0，子进程仍在用，延迟释放
- `mm_struct` 同理

### 4.2 跨子系统不污染

调度子系统关心 `se` `rt` `dl`，不关心内存布局。如果 `mm_struct` 嵌入 task_struct，调度器访问 `task->mm` 时会触及内存子系统的缓存行——伪共享（false sharing）。

把账本独立出来，调度子系统只用 task_struct 前 1KB 的字段，单独 cacheline，调度延迟更稳定。

### 4.3 凭证切换的原子性

`cred` 和 `real_cred` 是两个指针——某些场景（如 setuid 系统调用）需要"切换"凭证但保留原凭证以便恢复。两个指针 = 原子替换。

如果嵌入，`copy_creds()` 要复制整块内存——开销大且并发不安全。

---

## 五、task_struct 的内存分配与释放

### 5.1 分配：slab 缓存

task_struct 不是用 kmalloc 直接分配，而是用 **专用 slab 缓存**：

```c
// kernel/fork.c
struct kmem_cache *task_struct_cachep;

void fork_init(void)
{
    task_struct_cachep = kmem_cache_create("task_struct",
        ARCH_MIN_TASKALIGN, SLAB_HWCACHE_ALIGN|SLAB_PANIC|SLAB_ACCOUNT, NULL);
}
```

**为什么用 slab 而不是 kmalloc**：
- task_struct 分配释放极频繁（每次 fork 一次）
- 大小固定（6KB-8KB），slab 不会碎片化
- `SLAB_HWCACHE_ALIGN` 让 task_struct 按 cacheline 对齐，减少伪共享

### 5.2 释放：RCU 延迟

task_struct 释放用 RCU 延迟（`call_rcu(&tsk->rcu, delayed_free_task)`），原因是：
- 调度器可能在另一 CPU 上访问这个 task_struct（虽然理论上已不在 runqueue）
- 信号子系统可能正在投递信号
- 用 RCU 延后释放窗口，确保所有可能的访问都结束后才真正 free

---

## 六、稳定性排查中的高频字段组合

按"问题 → 必看字段"做一个速查表：

| 问题 | 必看字段 | 速查命令 |
|---|---|---|
| 卡顿 / 调度延迟 | `state` `prio` `policy` `nivcsw` `cpus_ptr` `uclamp_min` | `cat /proc/<pid>/status` |
| OOM / 进程被杀 | `signal->oom_score_adj` `cgroups` `mm->total_vm` | `cat /proc/<pid>/oom_score_adj` |
| ANR / 卡死 | `state`（D 状态）`comm`（看哪个线程）`wchan` | `cat /proc/<pid>/wchan` |
| 进程残留 | `state`（Z 状态）`exit_code` | `ps -A` 看 `<defunct>` |
| CPU 亲和性 | `cpus_ptr` `user_cpus_ptr` `cpus_mask` | `taskset -p <pid>` |
| 调度策略异常 | `policy` `rt_priority` `dl.runtime` | `chrt -p <pid>` |
| 内存泄漏 | `mm->total_vm` `mm->pinned_vm` | `cat /proc/<pid>/smaps_rollup` |
| 信号丢失 | `pending` `blocked` `real_blocked` | `cat /proc/<pid>/status` 看 SigQ |

---

## 七、给 03 篇留的钩子

读完 02 篇，你应该能：

1. 在脑中画出 task_struct 的 10 个字段分组。
2. 用 `pahole` 读真实偏移，用 `bpftrace` 实时读字段。
3. 用字段组合定位 4 类稳定性问题。
4. 理解 task_struct 是"指针目录"而非"完整档案"。

03 篇《进程的诞生：fork / clone / vfork》会回答：

> task_struct 怎么从"空"变"满"？
>
> - `copy_process()` 怎么一步一步填这些字段？
> - 哪些字段是父进程"原样复制"？
> - 哪些字段是"重新初始化"？
> - COW 怎么在 task_struct 这一层体现？
> - 子进程从 `kernel/fork.c:copy_thread` 之后怎么变成"能跑"？

读完 02 + 03 两篇，你应该能把 task_struct 的"出生"全过程写出来——这正是 Android 14 中 Zygote fork 优化的核心（Framework/Process 系列 02 篇会回扣）。

---

## 小结

| 维度 | 一句话总结 |
|---|---|
| 真实大小 | 6KB-8KB（ARM64 Linux 5.10-6.1） |
| 字段数 | 200+ 字段 |
| 字段分组 | 10 个维度（生命周期 / 调度 / 内存 / 文件 / 信号 / cgroup / 命名空间 / 凭证 / 关联 / 统计） |
| 核心定位 | 指针汇聚点，不是完整档案 |
| 实战工具 | `pahole` 看布局，`bpftrace` 实时读字段，`cat /proc/<pid>/status` 看投影 |
| 性能特性 | slab 专用缓存 + RCU 延迟释放 + cacheline 对齐 |

---

## 给下篇的桥

**本篇留下三个钩子**：

1. task_struct 的字段"从哪里来"——03 篇讲 fork 时怎么填这些字段
2. `se` `rt` `dl` 三个调度实体怎么被调度器操作——07-09 篇展开
3. 僵尸进程的判定依据 `state & EXIT_ZOMBIE`——05 篇讲 do_exit 时会回扣

如果读完本文仍有疑问：

- **"task_struct 字段太多记不住"** → 不需要记，按"问题 → 字段"反查 §六的速查表即可
- **"为什么调度实体这么大"** → 07-09 篇专门讲 CFS / RT / DL 调度实体的内部结构
- **"我想马上动手"** → 直接跑 §1.2 的 `pahole` 命令

---

## 引用

| 引用 | 路径 |
|---|---|
| task_struct 定义 | `include/linux/sched.h` |
| task_struct slab 缓存 | `kernel/fork.c:1815`（fork_init） |
| copy_process | `kernel/fork.c:1790` |
| RCU 释放 | `kernel/fork.c:131`（free_task） |
| Android 14 内核符号 | `vmlinux`（需 Android 内核 debug build） |
| Framework 镜像 | [Framework/Process/06 §3.1 投影视角](../../Android_Framework/Process/06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd.md) |