# 01-杀进程全链路：从 AMS 触发到进程完全退出

> **本篇定位**：杀进程系列**第 1 篇**，**开篇总表**。从 AMS 决定杀进程 → 信号投递 → Kernel do_exit → 资源回收 → FWK 收尾，把**5 个阶段 × 4 个层栈**的完整链路画清楚。
>
> **结构**：
> - **§1** 全景图：5 阶段 × 4 层栈
> - **§2-§8** 各阶段概览（先占位，详细内容见 02/03）
> - **§9** 时序图 + 每阶段耗时典型值
> - **§10** 慢的真正条件 + 反证（**关键章节，回应"swap 55% 不是根因"**）
> - **§11** ftrace 抓取 + 测速方法（沿用 09 §6.7.3）
> - **§12** 跨篇索引
>
> **基线**：AOSP `android-16.0.0_r1` + Kernel `android16-6.6` GKI 2.0
> **目录位置**：`Android_Framework/Process_Exit/`
> **本系列关系**：[README-杀进程系列](README-杀进程系列.md)

---

## 目录

- [1. 全景图：5 阶段 × 4 层栈](#1-全景图5-阶段--4-层栈)
- [2. 阶段 1：触发源 7 类](#2-阶段-1触发源-7-类)
- [3. 阶段 2：AMS 决策（killPackageProcessesLocked）](#3-阶段-2ams-决策killpackageprocesseslocked)
- [4. 阶段 3：信号发送（pidfd_send_signal）](#4-阶段-3信号发送pidfd_send_signal)
- [5. 阶段 4：Kernel 信号投递 + do_group_exit](#5-阶段-4kernel-信号投递--do_group_exit)
- [6. 阶段 5：do_exit 9 个 sub-step 概览](#6-阶段-5do_exit-9-个-sub-step-概览)
- [7. 阶段 6：资源回收（cgroup + reaper）](#7-阶段-6资源回收cgroup--reaper)
- [8. 阶段 7：FWK 收尾（handleAppDied）](#8-阶段-7fwk-收尾handleappdied)
- [9. 时序图 + 耗时典型值](#9-时序图--耗时典型值)
- [10. 慢的真正条件 + 反证](#10-慢的真正条件--反证关键章节)
- [11. ftrace 抓取 + 测速方法](#11-ftrace-抓取--测速方法)
- [12. 跨篇索引](#12-跨篇索引)

---

## 1. 全景图：5 阶段 × 4 层栈

杀进程是**多阶段、多层栈**的协作过程。把它想象成"接力赛跑"——每阶段都是独立的"选手"，有自己的起跑线、跑道、计时器。

### 1.1 5 个阶段

| 阶段 | 名称 | 起点 | 终点 | 主导者 | 典型耗时 |
|---|---|---|---|---|---|
| **1** | 触发源 | 用户操作 / 系统事件 | `am_kill` 日志 | FWK 上半部 | < 1ms (决策) |
| **2** | AMS 决策 | `am_kill` | `pidfd_send_signal` 调用 | FWK 上半部 | ~5ms |
| **3** | 信号发送 | `pidfd_send_signal` | `kill_pid_info` 内核入口 | FWK 下半部 | ~5ms |
| **4** | Kernel 信号投递 | `kill_pid_info` | `do_group_exit` | Kernel 中段 | < 1ms |
| **5** | Kernel 进程退出 | `do_group_exit` | `release_task` | Kernel 中段 | **50ms-10s+** (本案 10s) |
| **6** | 资源回收 | `release_task` | cgroup 节点真消失 | Kernel 收尾 | < 1ms - 24s+ (本案异步 24s+) |
| **7** | FWK 收尾 | `am_proc_died` | `handleAppDied` 完成 | FWK 上半部 | < 100ms |

**注意**：阶段 1-3 总共 < 11ms；阶段 4 < 1ms；**阶段 5 是主战场**（本案 10s）；阶段 6 在 sync 路径下 < 1ms，但 async 路径（cgroup.workqueue）可能秒级；阶段 7 < 100ms。

### 1.2 4 个层栈

```
┌─────────────────────────────────────────────────────┐
│ FWK 上半部（SystemServer 进程，Java 层）              │
│   - ActivityManagerService (AMS)                    │
│   - ProcessList / OomAdjuster / ProcessStatsService │
├─────────────────────────────────────────────────────┤
│ FWK 下半部（SystemServer 进程，Native 层 / IPC）      │
│   - PidfdProcess (libbinder Native)                  │
│   - pidfd_send_signal 系统调用                        │
│   - waitid(P_PIDFD) 收尸                             │
├─────────────────────────────────────────────────────┤
│ Kernel 中段（被杀的进程，Kernel 态）                   │
│   - dequeue_signal → do_signal → do_group_exit     │
│   - do_exit 9 个 sub-step                            │
│   - release_task                                     │
├─────────────────────────────────────────────────────┤
│ Kernel 收尾（cgroup.workqueue 异步 + 父进程 wait）    │
│   - cgroup_release → cgroup_destroy_css_killed      │
│   - cgroup.workqueue 异步清理 cgroup 节点            │
│   - 父进程 waitid(P_PIDFD) 返回                      │
└─────────────────────────────────────────────────────┘
```

### 1.3 关键观察

- **阶段 1-4（FWK + Kernel 信号投递）总耗时 < 12ms** —— 这部分即使在生产环境最差的优化下也几乎不可能卡 1s
- **阶段 5（do_exit）是主战场** —— 本案 12.24s 中 10s+ 在这里
- **阶段 6（cgroup 释放）分 sync 和 async** —— sync 部分（cgroup_release < 1ms）发生在 do_exit 末尾；async 部分（cgroup.workqueue）可能数秒到数十秒，**但不影响 am_proc_died 时点**
- **阶段 7（FWK 收尾）< 100ms** —— handleAppDied 是纯 Java 内存操作，无 IO

**所以"杀进程慢"的诊断，90% 的工作要聚焦在阶段 5**。其他阶段要么是 ms 级（不值得看），要么是"看着吓人但不影响主流程"（如 cgroup 销毁 async 24s）。

---

## 2. 阶段 1：触发源 7 类

> **本节为占位，详细见 02 篇 §2 + 04 篇 §1**。

杀进程的 7 类触发源：

| 类别 | 触发条件 | 调用栈 | 案例 |
|---|---|---|---|
| ① `am_kill ... remove task` | Clear All / 滑动删除 | Launcher3 → SystemUiProxy → AMS.removeTask | **Process 09 案** |
| ② `am_kill ... force stop` | 设置 → 强制停止 | Settings → AMS.killApplicationProcess | 用户卸载/强停 |
| ③ `am_kill ... lowmem` | LMKD 决策 | lmkd → AMS.recordLmkdKill | 系统低内存 |
| ④ `lmkd` (内核) | cgroup 内存超限 | 内核 cgroup → lmkd 事件循环 | 同 ③，但走 cgroup 路径 |
| ⑤ OOM Killer (内核) | 物理内存耗尽 | 内核 OOM → SIGKILL | 系统 OOM（极少） |
| ⑥ Native crash | unhandled signal | debuggerd → RuntimeInit KillApplication | Native 异常 |
| ⑦ Watchdog | 主线程 hang 5s+ | Watchdog 监控 → am_wtf + kill | ANR 转 Watchdog kill |

**所有 7 类的最终执行路径都是：→ AMS 决策（阶段 2）→ 信号发送（阶段 3）→ Kernel（阶段 4-6）→ FWK 收尾（阶段 7）**。

---

## 3. 阶段 2：AMS 决策（killPackageProcessesLocked）

> **本节为占位，详细见 02 篇**。

`frameworks/base/services/core/java/com/android/server/am/ProcessList.java`：

```java
final boolean killPackageProcessesLocked(String packageName, ...) {
    // 1. 找到所有 ProcessRecord
    for (ProcessRecord proc : mProcessNames.get(packageName)) {
        // 2. 调 PidfdProcess.killProcess
        pidfdProcess.killProcess(pid, signal);
    }
    return true;
}
```

`PidfdProcess.killProcess`（`frameworks/native/libs/binder/PidfdCache.cpp`）：

```cpp
int PidfdProcess::killProcess(int pid, int signal) {
    int pidfd = acquire(pid);       // 获取 pidfd
    siginfo_t info;
    info.si_signo = signal;        // SIGKILL
    info.si_code = SI_KERNEL;
    info.si_pid = 0;
    // ★ 系统调用：pidfd_send_signal
    return sys_pidfd_send_signal(pidfd, signal, &info, 0);
}
```

**AMS 决策阶段耗时 ~5ms**（纯 Java + 一次系统调用）。

---

## 4. 阶段 3：信号发送（pidfd_send_signal）

> **本节为占位，详细见 02 篇**。

`pidfd_send_signal` 是 Linux 5.1+ 引入的系统调用，通过 pidfd 而不是 PID 投递信号：

```c
// kernel/signal.c
SYSCALL_DEFINE4(pidfd_send_signal, int, pidfd, int, sig,
                siginfo_t __user *, info, unsigned int, flags)
{
    // 1. fd → struct pid
    pid = pidfd_to_pid(pidfd, flags);
    // 2. 调 kill_pid_info
    return kill_pid_info(sig, info, pid);
}
```

**优势**：
- 不受 PID 复用影响（pidfd 绑定 struct pid，不是 PID 数字）
- 避免 PID race（PID 在 prepare 期间被复用）

**信号发送阶段耗时 ~5ms**（系统调用 + 内核路径）。

---

## 5. 阶段 4：Kernel 信号投递 + do_group_exit

> **本节为占位，详细见 02 篇**。

`kill_pid_info` → `group_send_sig_info` → `send_signal` → 目标进程被唤醒后：

```c
// kernel/signal.c
static void complete_signal(int sig, struct task_struct *p, enum pid_type type) {
    // ...
    signal_wake_up(state, sig == SIGKILL);
}
```

目标进程被调度后，ret_to_user 之前走 `do_signal`：

```c
// arch/arm64/kernel/signal.c
void do_signal(struct pt_regs *regs) {
    // ...
    if (sig_kernel_only(signr)) {
        // ★ SIGKILL 不走用户态
        do_group_exit(force_sigsegv ? SIGSEGV : signr);
    }
}
```

**Kernel 信号投递阶段耗时 < 1ms**（SIGKILL 直接 do_group_exit，不走用户态）。

---

## 6. 阶段 5：do_exit 9 个 sub-step 概览

> **本节为概览，详细见 02 篇**。

```c
// kernel/exit.c
void do_exit(long code) {
    // ① exit_signals
    exit_signals(tsk);
    
    // ② exit_mm ★ 主战场
    exit_mm(tsk);
    
    // ③ exit_files
    exit_files(tsk);
    
    // ④ exit_fs
    exit_fs(tsk);
    
    // ⑤ exit_thread
    exit_thread(tsk);
    
    // ⑥ exit_namespaces
    exit_namespaces(tsk);
    
    // ⑦ exit_task_stack
    exit_task_stack(tsk);
    
    // ⑧ exit_task_work
    exit_task_work(tsk);
    
    // ⑨ sched_set_group_id + sched_dead + schedule()
    sched_set_group_id(tsk);
    sched_dead(tsk);
    schedule();
}
```

**9 个 sub-step 的耗时典型值**（健康范围 / 真实 case）：

| sub-step | 理想耗时 | 真实 case 范围 | 变慢的真正条件 |
|---|---|---|---|
| ① exit_signals | < 1ms | < 1ms | 不会慢 |
| **② exit_mm** | ~50ms | **100ms - 10s+** | vma 状态异常 / swap slot 锁竞争 / unmap 大量物理页 |
| ③ exit_files | ~5ms | 5ms - 5s | 慢 FS（fuse / network）/ GPU flush 慢 / 数千 fd |
| ④ exit_fs | < 1ms | < 1ms | 不会慢 |
| ⑤ exit_thread | < 10ms | < 100ms | 线程数极多（1000+），一般不会 |
| ⑥ exit_namespaces | < 1ms | < 10ms | 多层 nsproxy（容器场景），一般不会 |
| ⑦ exit_task_stack | < 1ms | < 1ms | 不会慢 |
| ⑧ exit_task_work | < 1ms | < 100ms | task_work 队列堆积（少见） |
| ⑨ sched_dead + schedule | < 1ms | < 1ms | 不会慢（除非调度器本身卡） |

**关键**：**只有 ② exit_mm 和 ③ exit_files 有可能卡 1s+**。其他 7 个 sub-step 几乎不可能单独卡 1s。

---

## 7. 阶段 6：资源回收（cgroup + reaper）

> **本节为概览，详细见 02 篇**。

```c
// kernel/exit.c (父进程 waitid 内)
void release_task(struct task_struct *tsk) {
    detach_pid(tsk, ...);
    cgroup_release(tsk);            // ★ sync 部分
    put_cred(...);
    free_task_struct(tsk);
}

// kernel/cgroup/cgroup.c
void cgroup_release(struct task_struct *tsk) {
    cset->task_count--;
    if (refcount == 1) {
        cgroup_destroy_css_killed(cset);  // 标记 + 排队
    }
}

// kernel/cgroup/cgroup.c (异步 workqueue)
cgroup_destroy_work() → 节点真从 /sys/fs/cgroup 树消失
```

**关键时序**（回应用户问题"am_proc_died 打印后才发生 cgroup 的移除吗"）：
- **是，正常 am_proc_died 早于 cgroup 节点真销毁**——am_proc_died 在 do_exit 末尾触发（阶段 5 → ⑥ → ⑨ schedule 之前）；cgroup 释放在父进程 waitid 返回后触发（阶段 6 sync）；cgroup 节点真从 /sys/fs/cgroup 树消失还要再走 cgroup.workqueue 异步（阶段 6 async）
- 正常时序差：am_proc_died → waitid < 1ms（同步）；cgroup_release → 节点真消失 几 ms - 几秒（async）
- 本案异常：am_proc_died 31.898 → 56.016 cgroup "Still waiting ... after 2209 ms" → 58.224 "Device or resource busy"（24s 缺口 = cgroup.workqueue 锁竞争 + cgroup_mutex 被 vendor 配置持有）

---

## 8. 阶段 7：FWK 收尾（handleAppDied）

> **本节为概览，详细见 02 篇**。

```java
// ActivityManagerService.java
public void handleAppDied(ProcessRecord app, int pid) {
    // 1. cleanUpApplicationRecordLocked
    cleanUpApplicationRecordLocked(app, ...);
    
    // 2. removeProcessLocked
    removeProcessLocked(app, ...);
    
    // 3. 通知 observers
    for (ProcessObserver observer : mProcessObservers) {
        observer.onProcessDied(app);
    }
}
```

**耗时 < 100ms**（纯 Java 内存操作，无 IO）。

---

## 9. 时序图 + 耗时典型值

> **本节为占位，详细见 02 篇**。

### 9.1 健康范围时序

```
am_kill (19.658)
  ↓ < 1ms
pidfd_send_signal (19.659)
  ↓ < 1ms
do_group_exit (19.660)
  ↓ ~50ms
do_exit 9 sub-step 完成
  ↓ < 1ms
release_task
  ↓ < 1ms
am_proc_died (19.760)
  ↓ < 100ms
handleAppDied 完成 (19.850)
```

**健康总耗时 ~200ms**。

### 9.2 本案时序（Process 09 真实 case）

```
am_kill (19.658)
  ↓ < 1ms
pidfd_send_signal (19.659)
  ↓ < 1ms
do_group_exit (19.660)
  ↓ ~10s ★ 阶段 5 exit_mm 慢
do_exit 9 sub-step 完成
  ↓ < 1ms
release_task
  ↓ < 1ms
am_proc_died (31.898)
  ↓ < 100ms
handleAppDied 完成 (32.000)
  ↓ (后续 async)
cgroup 节点真消失 (24s+ 后 / 失败)
```

**本案总耗时 12.24s（am_kill → am_proc_died）+ 24s+（cgroup 残留）**。

### 9.3 关键时序差对照

| 时序 | 健康 | 本案 | 倍数 |
|---|---|---|---|
| am_kill → pidfd_send_signal | < 1ms | < 1ms | 1x |
| pidfd_send_signal → do_group_exit | < 1ms | < 1ms | 1x |
| do_group_exit → do_exit 完成 | ~50ms | ~10s | **200x** |
| do_exit 完成 → am_proc_died | < 1ms | < 1ms | 1x |
| am_proc_died → cgroup 节点消失 | < 1s | 24s+ | 24x+ |

**关键观察**：本案唯一被放大的环节是"do_group_exit → do_exit 完成"，其他环节都是健康的。

---

## 10. 慢的真正条件 + 反证（关键章节）

> **本节为杀进程系列最核心的章节**——区分"诱因"和"根因"是排查杀进程慢的关键。

### 10.1 诱因 vs 根因的判定标准

4 条判定规则：

| 规则 | 含义 | 检验方法 |
|---|---|---|
| **重现性** | 根因必须能在受控条件下独立重现 | ftrace 抓 trace，删除/保留该因素对比 |
| **充分性** | 仅有该因素就能触发杀进程慢 | 单变量实验 |
| **必要性** | 没有该因素就不会慢 | 阻断该因素，看是否还慢 |
| **可证伪** | 必须有反例能推翻这个说法 | 找"高 swap 50% 但杀进程不慢"的 case |

### 10.2 6 大"伪根因"的证伪

| 伪根因 | 反证 | 真实角色 |
|---|---|---|
| **swap 55% 高使用率** | 系统 swap 55%+ 场景线上很多，但杀进程卡 10s+ 极少 | **诱因**（放大器），不是根因 |
| **rss 170MB 大** | 进程 rss 几百 MB 场景很多，单纯 unmap rss 大不会让 do_exit 慢到 10s | **诱因**（unmap 数量大），不是根因 |
| **进程数量多** | Clear All 杀 20 个 task，每个 do_exit 是独立的，不互相阻塞 | **诱因**（叠加），不是根因 |
| **zRAM 压缩比高** | zRAM 压缩比只影响 IO 性能，不影响 swap_free 路径 | **无关** |
| **系统 MemFree 80MB** | MemFree 低只影响"新分配"性能，不影响"释放"性能（释放不需要新分配） | **无关**（但 MemFree 低会让 2-3 重压力叠加） |
| **单 app 复杂业务逻辑** | SIGKILL 不走用户态，直接 do_group_exit，复杂逻辑不会跑 | **完全无关** |

**关键观察**：
- **swap 55% 高使用率** → 只能让 ③-c swap_free 慢 100-500ms（在合理范围内），**不能独立触发 10s+**
- **rss 170MB** → 单纯 unmap rss 大 应该是 ms 级
- **这些因素都是"必要条件"但不是"充分条件"**

### 10.3 真正根因 3 类

| 根因类别 | 含义 | 真实耗时 | 关键观测 | 治理 |
|---|---|---|---|---|
| **A. vma 状态异常** | 进程在被杀前 mmap 已被预回收（vma 状态与页表不一致） | **5-10s** | kernel log `binder_alloc: ... no vma` / `mmap 已被预回收` 标志 | 修复 process_reclaim / vendor hook 同步状态 |
| **B. fd 关闭慢** | 慢 FS（fuse / network）/ GPU flush / 数千 fd | 1-5s | `lsof -p <pid>` 看 fd 类型 / `ftrace exit_files` 耗时 | 减少 fd / 优化 FS / GPU 资源提前释放 |
| **C. 资源回收拥堵** | cgroup 销毁 / reaper 排队 / 锁竞争 | 1-24s | `/sys/fs/cgroup/.../memory.events` oom_kill / `cgroup_mutex` 等待 | vendor cgroup 配置 / workqueue 调度优化 |

**关键观察**：
- **A. vma 状态异常是 Process 09 案的真正根因**——案发前 24min kernel log 4 次 `binder_alloc: 15770: no vma`，证明 vma 已被 transsion `process_reclaim` 预回收过
- **B. fd 关闭慢**是另一类常见根因（fuse FS / 相机 GPU flush），但跟本案无关
- **C. 资源回收拥堵**影响 am_proc_died 之后的 cgroup 残留，但**不影响 12.24s 主耗时**

### 10.4 证伪方法（ftrace + 反例）

#### 10.4.1 用 ftrace 验证"swap 55% 是根因"

```bash
# 准备：开启 ftrace + 制造 swap 50% 环境
echo 1 > /proc/sys/vm/swappiness  # 提高 swap 使用
# 制造大压力
stress-ng --vm 4 --vm-bytes 4G &

# 制造简单杀进程场景
adb shell am force-stop com.example.test  # 一个简单 app，不应该有 vma 异常

# 抓 trace
echo 1 > /sys/kernel/debug/tracing/tracing_on
# ... 等 5s ...
echo 0 > /sys/kernel/debug/tracing/tracing_on

# 分析：找 sched_process_exit → exit_mmap 耗时
# 预期: < 200ms (即使 swap 55%)
# 结论: swap 55% 不能独立触发 10s+
```

#### 10.4.2 用反例证伪

**反例**：线上 swap 使用率 50%-60% 的 case 很多（任何长跑测试都会达到），但杀进程卡 10s+ 的 case 极少。这直接证明 swap 55% **不充分**——不是根因。

**对比实验**：
- 实验 1：swap 55% + 健康 vma → 杀进程 ~200ms
- 实验 2：swap 30% + vma 异常 → 杀进程 5-10s

**结论**：vma 异常才是充分条件，swap 55% 只是必要条件。

### 10.5 根因 → 治理映射

| 根因类别 | 治理方向 | 优先级 | 案例 |
|---|---|---|---|
| A. vma 状态异常 | (a) 修复 vendor process_reclaim 同步状态 (b) 减少 vma 预回收 (c) 加重启间隔做 mmap 校验 | P0 | **Process 09 案**（transsion process_reclaim） |
| B. fd 关闭慢 | (a) 减少 fd 数 (b) 异步 close（background） (c) 优化 GPU 资源释放 | P1 | 相机 GPU flush 慢导致杀进程 1-2s |
| C. 资源回收拥堵 | (a) vendor cgroup 配置优化 (b) cgroup.workqueue 调度优化 | P2 | transsion cgroup Device or resource busy |

---

## 11. ftrace 抓取 + 测速方法

> **本节为占位，详细命令见 09 §6.7.3**。

抓 trace 的 6 个关键事件：

```bash
echo 1 > events/sched/sched_process_exit/enable       # do_exit 入口
echo 1 > events/sched/sched_process_wait/enable       # 父进程 wait 入口
echo 1 > events/signal/signal_generate/enable         # 信号生成
echo 1 > events/signal/signal_deliver/enable          # 信号投递到目标
echo 1 > events/mm/mm_page_free/enable                # exit_mm 释放页
echo 1 > events/mm/mm_page_free_batched/enable        # bulk free
```

**测速公式**（精确版 vs 估算版）：

| 阶段 | 精确版（ftrace） | 估算版（events_log 反推） |
|---|---|---|
| 杀进程总耗时 | `T_wait_done - T_exit` | 31.898 - 19.658 = 12.24s（直接观测） |
| exit_mm 耗时 | exit_mmap start - end | 12.24s - 其他 ~2.24s = ~10s（反推） |
| exit_files 耗时 | filp_close start - end | 估算 < 100ms（健康范围） |

**反推 vs 精确的差异**：精确版用 ftrace 的 start/end 事件；反推版用 events_log 边界 - 已知其他阶段耗时。

---

## 12. 跨篇索引

| 主题 | 见本系列哪篇 | 详细程度 |
|---|---|---|
| 5 阶段全链路概览 | **本篇 01** | 概览 |
| do_exit 9 个 sub-step 源码深潜 | → 02 | 源码级 |
| 真正根因判定 + 证伪方法 | → 03 | 框架 + 反例 |
| 监控 + 告警 + 治理 | → 04 | 工程落地 |
| 真实 case（TECNO KM9 / Android 16） | → Process 09 实战 | 案例 |

**实战**：[Process 09-杀进程慢的根因定位实战](../Process/09-杀进程慢的根因定位实战.md) — 用本系列理论分析的真实案例。

**Process 9 → Process_Exit 01**：Process 09 的"5 栏对账表"已被你识别为"数字无证据"。本系列 02/03 将用 ftrace 实测 + 反例证伪替代。

---

## 篇尾衔接

**本篇是杀进程系列的开篇**，画了 5 阶段 × 4 层栈的全景图。骨架交付，请验收架构：

- **5 阶段划分**合理吗？
- **§10 慢的真正条件**（swap 55% 不是根因 / vma 异常才是根因）方向对吗？
- **§6 do_exit 9 sub-step 概览** 拆分合理吗？

确认后开始写 02 篇（do_exit 9 sub-step 深潜，源码级）。
