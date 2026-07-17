# Kernel 进程系列文章（共 13 篇）

> 本系列基于 Linux Kernel 5.10 / 5.15（Android 12-14 主流内核）+ Android 14 GKI。
> **视角**：Kernel 层（与 `Android_Framework/Process` 镜像分工——见末尾）。
> **目标读者**：Android 稳定性 SE、性能工程师、Framework 工程师。
> **主线**：一个进程在 Linux Kernel 内部是如何被"管起来"的——结构 → 行为 → 调度 → 控制 → 协作 → 调试。

---

## 系列定位

本系列是**从 Kernel 视角**完整讲解 Linux 进程子系统的 13 篇深度文章。区别于"运行原理扫盲"或"代码片段解读"，本系列：

- **主线贯穿**：从结构（task_struct）→ 行为（fork / exec / exit）→ 调度（sched_class / CFS / RT / DL / SMP）→ 控制（cgroup / 信号）→ 协作（IPC / Binder）→ 调试（ftrace / perfetto）
- **逐步深入**：每篇都建立在前一篇基础上，承上启下
- **稳定性视角**：每章都回答"这和我排查线上问题有什么关系"
- **实战可执行**：所有示例在 Android 14 + Linux 5.10 GKI 上可跑

## 设计原则

1. **递进式骨架**：5 个阶段（A 总览 → B 生命周期 → C 调度 → D 控制 → E 调试）
2. **主线贯穿**：每篇都有"上一篇留下什么钩子 → 本篇解决什么 → 给下一篇留什么钩子"
3. **每篇都回答稳定性问题**：卡顿、ANR、OOM、僵尸进程、调度延迟等场景都在工具章节给具体排查方法
4. **源码 + 命令 + 数据**：源码路径 + Android 14 真实命令 + 量化数据
5. **与 Framework 06 镜像分工**：互不重叠——Kernel 视角与 Framework 视角互补

---

## 13 篇目录

### 阶段 A：建立总览（拿到地图）

| # | 标题 | 核心内容 |
|---|---|---|
| **01** | [进程子系统全景与边界契约](01-进程子系统全景与边界契约.md) | Kernel 进程子系统模块图 + 与 Framework 06 镜像分工契约 |
| **02** | [task_struct 全景拆解](02-task_struct全景拆解.md) | task_struct 字段按子系统分组 + 5 个排查场景 |

### 阶段 B：生命周期（怎么活）

| # | 标题 | 核心内容 |
|---|---|---|
| **03** | [进程的诞生：fork / clone / vfork](03-进程的诞生_fork_clone_vfork.md) | sys_clone → copy_process + COW + vfork + Zygote 优化 |
| **04** | [进程的执行：execve 与程序加载](04-进程的执行_execve与程序加载.md) | sys_execve → linux_binprm → load_elf_binary + Android 14 binfmt |
| **05** | [进程的退出：do_exit 与资源回收](05-进程的退出_do_exit与资源回收.md) | sys_exit_group → do_exit + SIGCHLD + 僵尸进程 |

### 阶段 C：调度（被谁挑中跑）

| # | 标题 | 核心内容 |
|---|---|---|
| **06** | [调度基础架构：调度类与上下文切换](06-调度基础架构_调度类与上下文切换.md) | sched_class 5 类 + runqueue + schedule() + context_switch |
| **07** | [CFS 调度器：vruntime 与红黑树](07-CFS调度器_vruntime与红黑树.md) | sched_entity + cfs_rq + vruntime 公式 + PELT + 任务组调度 |
| **08** | [调度扩展：RT / Deadline / Idle](08-调度扩展_RT_Deadline_Idle.md) | SCHED_FIFO/RR + SCHED_DEADLINE CBS + 优先级反转 + PI-futex |
| **09** | [多核调度：SMP 负载均衡 + EAS](09-多核调度_SMP负载均衡_EAS.md) | sched_domain + load_balance + EAS + WALT + UClamp + cpuset |

### 阶段 D：控制（被谁约束 + 协作）

| # | 标题 | 核心内容 |
|---|---|---|
| **10** | [cgroup v2：内核里的资源控制器](10-cgroup_v2_内核里的资源控制器.md) | cgroup_subsys + cftype + memory / cpu / freezer + Android 14 cgroup 树 |
| **11** | [信号机制：从产生到投递](11-信号机制_从产生到投递.md) | sys_kill / pending / dequeue_signal / **SIGKILL 不可捕获的底层原因** |
| **12** | [进程间通信：pipe / fifo / shm / futex / Binder](12-进程间通信_pipe_fifo_shm_futex_Binder.md) | pipe / mmap / futex + **Binder 驱动内核实现** + 与 Framework 06 镜像分工 |

### 阶段 E：调试收口

| # | 标题 | 核心内容 |
|---|---|---|
| **13** | [进程调试与稳定性关联](13-进程调试与稳定性关联.md) | ftrace / perfetto / PSI + **3 个实战案例**（卡顿 / ANR / LMKD）+ bpftrace |

---

## 整体结构图

```
主线：进程在 Kernel 内部是如何被"管起来"的
                       │
                       ▼
       ┌─ 阶段 A：建立总览（拿到地图）─┐
       │   01 子系统全景 + 边界契约      │
       │   02 task_struct 全景拆解      │
       └──────────────┬───────────────┘
                      ▼
       ┌─ 阶段 B：生命周期（怎么活）─┐
       │   03 诞生 fork/clone         │
       │   04 执行 execve             │
       │   05 退出 do_exit            │
       └──────────────┬───────────────┘
                      ▼
       ┌─ 阶段 C：调度（被谁挑中跑）─┐
       │   06 调度基础架构            │
       │   07 CFS vruntime            │
       │   08 RT/Deadline/Idle        │
       │   09 多核 SMP + EAS          │
       └──────────────┬───────────────┘
                      ▼
       ┌─ 阶段 D：控制（被谁约束 + 协作）─┐
       │   10 cgroup v2 内核实现      │
       │   11 信号机制                │
       │   12 IPC pipe/shm/futex/Binder│
       └──────────────┬───────────────┘
                      ▼
       ┌─ 阶段 E：调试（出问题怎么定位）─┐
       │   13 调试 + 稳定性案例收口        │
       └───────────────────────────────┘
```

---

## 系列"主线 + 承上启下"

```
01：子系统全景
  ↓ 钩子：task_struct 是枢纽
02：task_struct 全景
  ↓ 钩子：task_struct 怎么从空变满？
03：fork / clone / vfork（诞生）
  ↓ 钩子：子进程 fork 后是空壳——怎么变实？
04：execve / 程序加载（执行）
  ↓ 钩子：进程跑起来后会死——怎么死？
05：do_exit / 资源回收（退出）
  ↓ 钩子：单进程讲完了，多个怎么排班？
06：调度基础架构 + 调度类 + context_switch
  ↓ 钩子：fair 是默认——怎么挑下一个？
07：CFS / vruntime / 红黑树
  ↓ 钩子：除 CFS 外还有 RT / DL
08：RT / Deadline / Idle + PI-futex
  ↓ 钩子：单核讲完，多核怎么调度？
09：多核 + EAS + WALT + UClamp + cpuset
  ↓ 钩子：调度器挑中跑，cgroup 决定能跑多少
10：cgroup v2 内核实现
  ↓ 钩子：约束之后还要协作——异步通知
11：信号机制（产生→投递）
  ↓ 钩子：信号是通知，IPC 是数据交换
12：pipe / shm / futex / Binder
  ↓ 钩子：原理讲完了，怎么排查线上问题？
13：调试工具栈 + 3 个实战案例
```

---

## 模块关系总图

```
                          Framework 层
┌─────────────────────────────────────────────────────────────┐
│   ActivityManagerService │ ProcessList │ Zygote │ App      │
└────────────────────────────┬────────────────────────────────┘
                             │ 系统调用
┌────────────────────────────▼────────────────────────────────┐
│                     13 篇覆盖范围                            │
│         fork │ clone │ execve │ exit │ wait                │
│              + cgroup v1/v2                                │
│              + signal                                      │
│              + IPC (pipe/shm/futex/Binder)                 │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                   进程管理子系统                             │
│              kernel/fork.c │ kernel/exit.c                  │
│                    task_struct                              │
└────────────────────────────┬────────────────────────────────┘
          │                  │                  │
    ┌─────▼─────┐     ┌─────▼─────┐     ┌─────▼─────┐
    │ 调度子系统 │     │ 内存管理  │     │ 文件系统  │
    │ kernel/   │     │ mm/       │     │ fs/       │
    │ sched/    │     │ mm_struct │     │files_struct│
    │ 5 类调度  │     │           │     │           │
    └─────┬─────┘     └───────────┘     └───────────┘
          │
    ┌─────▼─────┐     ┌──────────────┐     ┌──────────┐
    │ 信号子系统 │     │ cgroup v2    │     │   IPC    │
    │ kernel/   │     │ cpu/memory/  │     │ binder/  │
    │ signal.c  │     │ freezer/...  │     │ pipe/... │
    └───────────┘     └──────────────┘     └──────────┘
```

---

## 核心数据结构关系

```
task_struct（进程描述符，02 篇）
    │
    ├── mm_struct ───────► 进程地址空间（与内存管理交互，02/04 篇）
    │
    ├── files_struct ────► 打开文件表（02/03/05 篇）
    │
    ├── fs_struct ───────► 文件系统信息（02/03 篇）
    │
    ├── signal_struct ───► 信号处理（02/11 篇）
    │
    ├── sched_entity ───► CFS 调度实体（02/06/07 篇）
    ├── sched_rt_entity ► RT 调度实体（02/06/08 篇）
    ├── sched_dl_entity ► DL 调度实体（02/06/08 篇）
    │
    ├── nsproxy ─────────► 命名空间（02/03 篇简提）
    │
    └── cgroup_subsys_state ► cgroup 资源控制（02/10 篇）
```

---

## 学习路径建议

### 方式 1：系统学习（2-3 周）

按 01 → 13 顺序读，每篇都跑示例命令。建议路径：

1. **Week 1（基础）**：01-05（拿到地图 + 数据结构 + 生命周期）
2. **Week 2（调度）**：06-09（5 个调度类 + 多核 + EAS）
3. **Week 3（控制 + 调试）**：10-13（cgroup + 信号 + IPC + 调试）

### 方式 2：主题速查（1-2 天）

按主题直接跳读：

| 想了解 | 跳到 |
|---|---|
| 进程是什么 | 01 + 02 |
| fork / 进程诞生 | 03 |
| 调度器怎么挑 task | 06 + 07 |
| Android 14 上调度的具体优化 | 09 |
| cgroup 怎么限制资源 | 10 |
| 信号怎么传递 | 11 |
| Binder 驱动 | 12 |
| 排查卡顿 / ANR | 13 |

### 方式 3：问题驱动（1-2 小时）

遇到稳定性问题：
1. 用速查表（见 13 §10.2）定位章节
2. 跑 13 §1.2 的关键工具栈
3. 看对应章节的实战案例（13 §6 / §7 / §8）
4. 定位根因 + 修复

---

## 系列特点

### 1. 主线贯穿 + 逐步深入

13 篇不是孤立文章——是有机整体。每篇都有"承上"和"启下"，读者读完一篇知道下一篇在哪。

### 2. 实战导向

每章都有 Android 14 上的真实命令，**可以立即跑**。例如：
- `adb shell "cat /proc/<pid>/status"` —— 02/13 篇
- `adb shell "perfetto --record ..."` —— 13 篇
- `adb shell "cat /sys/fs/cgroup/top-app.slice/cpu.max"` —— 09/10 篇

### 3. 稳定性视角

每章都明确回答"排查什么稳定性问题"：
- 02 §10（5 个排查场景）
- 05 §12（僵尸进程 / 杀不掉 / 资源泄漏）
- 06 §10（调度延迟可观测性）
- 07 §10（调度延迟 / nice 配置 / cgroup throttle）
- 09 §12（负载不均 / 迁移风暴 / EAS 选错）
- 10 §12（cgroup 配置错误）
- 11 §13（信号丢失 / handler 卡）
- 12 §12（binder 拥塞 / 死锁）
- 13 §6/§7/§8（3 个完整实战案例）

### 4. 与 Framework 镜像分工

Kernel 视角与 Framework 视角**互不重叠**——见下一节。

---

## 与 Android_Framework/Process 系列的镜像分工

> **本节是本系列与 Android_Framework 进程系列的"分工契约"——同主题两个系列有不同视角，不要混读。**

| 主题 | Kernel 系列（本系列） | Framework 系列镜像篇目 |
|---|---|---|
| 进程子系统全景 | **[01](01-进程子系统全景与边界契约.md)** | Framework/Process/06 §1 模块图视角 |
| `task_struct` 字段语义 | **[02](02-task_struct全景拆解.md)** | Framework/Process/06 §3.1 投影视角 |
| fork / copy_process | **[03](03-进程的诞生_fork_clone_vfork.md)** | Framework/Process/06 §3 fork 视角 |
| execve / 程序加载 | **[04](04-进程的执行_execve与程序加载.md)** | Framework/Process/06 §3.2 ELF 视角 |
| do_exit / 资源回收 | **[05](05-进程的退出_do_exit与资源回收.md)** | Framework/Process/06 §3.3 do_exit 视角 |
| sched_class / 调度基础 | **[06](06-调度基础架构_调度类与上下文切换.md)** | Framework/Process/06 §4.1 调度视角 |
| CFS / vruntime | **[07](07-CFS调度器_vruntime与红黑树.md)** | Framework/Process/06 §4.2 CFS 视角 |
| RT / Deadline | **[08](08-调度扩展_RT_Deadline_Idle.md)** | Framework/Process/06 §4.3 RT 视角 |
| SMP / EAS / UClamp | **[09](09-多核调度_SMP负载均衡_EAS.md)** | Framework/Process/06 §4.4 EAS 视角 |
| cgroup v2 | **[10](10-cgroup_v2_内核里的资源控制器.md)** | Framework/Process/06 §5 cgroup 视角 |
| 信号机制 | **[11](11-信号机制_从产生到投递.md)** | Framework/Process/06 §6 信号视角 |
| IPC / Binder | **[12](12-进程间通信_pipe_fifo_shm_futex_Binder.md)** | Framework/Process/06 §7 Binder 视角 |
| 进程调试 | **[13](13-进程调试与稳定性关联.md)** | Framework/Process/06 §8 调试视角 |

**判断标准**：
- 读完后想去看 `kernel/sched/` 或 `kernel/fork.c` → **本系列**
- 读完后想去看 `frameworks/base/services/core/java/com/android/server/am/` → **Framework 系列**

---

## 与已有系列的关系

| 系列 | 关系 | 交互点 |
|---|---|---|
| Linux_Kernel/Memory_Management | 横向联动 | 02 §4 task_struct.mm / 09 §8 / 10 §5 |
| Linux_Kernel/FS | 横向联动 | 02 §5 files_struct / 03 §4 / 05 §3 |
| Linux_Kernel/Program_Execution | 上游联动 | 04 §3-§4 程序加载视角 |
| Linux_Kernel/System_Calls | 上游联动 | 03-05 系统调用入口 |
| Linux_Kernel/Binder | 横向联动 | 12 §6-§10 Binder 驱动 |
| Linux_Kernel/Socket | 横向联动 | 12 §5.3 unix domain socket |
| Android_Framework/Process | 镜像分工 | 13 个主题对照（见上表） |
| Android_Framework/AMS | 平级交叉 | 13 篇的实战案例多涉及 AMS |

---

## 参考资源

### 内核文档

- `Documentation/scheduler/` —— 调度器文档
- `Documentation/cgroup-v2.txt` —— cgroup v2 文档
- `Documentation/admin-guide/sysctl/kernel.rst` —— 内核参数
- `Documentation/filesystems/proc.rst` —— /proc 文档

### 内核源码

- `kernel/fork.c` —— 进程创建
- `kernel/exit.c` —— 进程退出
- `kernel/sched/` —— 调度器
- `kernel/signal.c` —— 信号
- `kernel/cgroup/` —— cgroup
- `mm/memcontrol-v1.c` / `include/linux/memcontrol.h` —— memory 子系统
- `drivers/android/binder.c` —— Binder 驱动
- `fs/pipe.c` —— pipe
- `kernel/futex.c` —— futex
- `kernel/trace/` —— ftrace

### 调试工具

- `kernel/trace/ftrace.c` —— ftrace
- `external/perfetto/` —— perfetto
- `external/bpftrace/` —— bpftrace
- `tools/perf/` —— perf

### 相关系列

- `../Memory_Management/` —— 内存管理系列
- `../FS/` —— 文件系统系列
- `../Program_Execution/` —— 程序执行系列
- `../../Android_Framework/Process/` —— Framework 进程系列（镜像分工）
- `../Stability_README.md` —— 稳定性综合索引

---

## 更新记录

- **2026-06-24**：系列大改版完成（v2 大纲，13 篇）
  - 整改：把 19 篇（22 万字）压缩到 13 篇（17 万字）
  - 增加主线贯穿 + 5 个阶段递进
  - 增加每章稳定性场景
  - 增加与 Framework 06 镜像分工对照表
  - 修复若干笔误（vfrok → vfork 等）
- **2026-01-31**：新增 v1 第 19 篇《用户态与内核态深入解析》（已废弃）
- **2026-01-28**：初始创建，包含 18 篇进程管理系列文章（已废弃）

---

## 系列总结

```
13 篇 + 5 个阶段 + 1 条主线 = Linux Kernel 进程子系统完整解读

主线：
  结构 → 行为 → 调度 → 控制 → 协作 → 调试

5 个阶段：
  A 总览（B 篇拿到地图 + 数据结构）
  B 生命周期（fork / exec / exit）
  C 调度（sched_class / CFS / RT / DL / SMP）
  D 控制（cgroup + 信号 + IPC）
  E 调试（ftrace / perfetto + 3 个案例）

总字数：约 17 万字（13 篇 × 1.3-2.0 万字）
目标读者：Android 稳定性 SE / 性能工程师 / Framework 工程师
镜像分工：Kernel 层视角（与 Framework 系列互补）
```

---

## 引用（系列）

| 引用 | 路径 |
|---|---|
| 系列原文 | `Linux_Kernel/Process/01-...md` ~ `13-...md` |
| 兄弟系列 | `Android_Framework/Process/06-...md` |
| 实战案例 | 13 §6 / 13 §7 / 13 §8 |
| 调试入口 | 13 §1.2 + 13 §10.2 |