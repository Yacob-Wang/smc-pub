# 多核调度：SMP 负载均衡 + EAS

> 系列第 09 篇 · 阶段 C · 调度
>
> **承上**：06-08 篇讲完调度器 5 个调度类——但都是单核视角。Android 14 是 big.LITTLE 多核架构，调度器必须决定：把 task 放哪颗 CPU？什么时候迁？EAS 怎么算能效？UClamp 怎么配合？本篇展开**多核调度**。
>
> **启下**：调度篇（阶段 C）全部结束——10 篇《cgroup v2：内核里的资源控制器》进入"进程被约束"的阶段 D。
>
> **预计篇幅**：约 1.9 万字
>
> **源码基线**：Linux 5.10 / 5.15 + Android 14 GKI（Android Common Kernel）。

---

## 学习目标

读完本文，你应该能：

1. 在脑中画出多核调度的全景图——CPU 拓扑 + 调度域 + 负载均衡 + EAS + UClamp。
2. 理解 big.LITTLE 架构——大小核怎么分工。
3. 知道 sched_domain 是什么——分层的负载均衡结构。
4. 跟踪 load_balance 的核心算法——什么时候触发、怎么选 CPU。
5. 理解 EAS（Energy Aware Scheduling）怎么选最省电的 CPU。
6. 知道 WALT 算法（Android 14 默认）跟 PELT 的差异。
7. 理解 UClamp min/max 怎么影响调度——top-app / background slice 怎么配合。
8. 知道 cpuset 怎么限制 task 在哪些 CPU 上跑——Android 14 的 top-app CPU 集。
9. 理解 wake_affine 算法——唤醒的 task 倾向于放哪颗 CPU。
10. 能在 Android 14 上用 perfetto / cat /sys/devices 看 CPU 拓扑和负载。
11. 知道负载不均 / 迁移风暴 / EAS 选错的排查方法。

---

## 一、多核调度的挑战

### 1.1 单核调度 vs 多核调度

**单核调度器只关心"挑谁跑"——多核调度器还要关心"放在哪颗 CPU 上跑"**：

```
单核调度器：
  决策 1：下一个跑谁？
  决策 2：context_switch 到那个 task

多核调度器：
  决策 1：下一个跑谁？
  决策 2：放在哪颗 CPU？
  决策 3：要不要从其他 CPU 拉任务过来？
  决策 4：要不要把自己跑的任务推给其他 CPU？
  决策 5：能效——放 CPU 0（小核）省电还是 CPU 4（大核）反应快？
```

**关键认知**：
- 单核调度器的"挑谁跑"算法（CFS / RT / DL）已经讲完
- 多核调度的核心是"放在哪"——这才是 Android 14 性能优化的主战场
- EAS / UClamp / cpuset / 调度域都是为"放在哪"服务的

### 1.2 多核调度器要解决的 4 个核心问题

```
1. 负载均衡（Load Balance）
   → 各 CPU 任务数差不多——避免某些 CPU 满载、某些空闲

2. 能效感知（Energy Aware）
   → 轻负载放小核（省电）、重负载放大核（够用）

3. 缓存亲和性（Cache Affinity）
   → task 在哪颗 CPU 跑，它的 cache 就热——尽量不迁移

4. 拓扑感知（Topology Aware）
   → 同一 cluster 的 CPU 共享 L2 cache——优先调度到同 cluster
```

**关键**：
- 这 4 个目标经常冲突——大核反应快但费电、小核省电但慢
- EAS 用"能耗模型"权衡——这是 Linux 内核里独有的设计
- Android 14 上 EAS 是默认（vendor 必须实现）

### 1.3 Android 14 的多核 CPU 拓扑

```bash
# 1. 看 CPU 拓扑
adb shell "ls /sys/devices/system/cpu/"
# 输出: cpu0 cpu1 cpu2 cpu3 cpu4 cpu5 cpu6 cpu7

# 2. 看每个 CPU 的容量（performance）
adb shell "cat /sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq"
# 输出:
#   /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq: 1800000
#   /sys/devices/system/cpu/cpu4/cpufreq/cpuinfo_max_freq: 2800000
# （典型 big.LITTLE：小核 1.8GHz，大核 2.8GHz）

# 3. 看 capacity（capacity = frequency / max_freq）
adb shell "cat /sys/devices/system/cpu/cpu*/cpu_capacity"
# 输出:
#   cpu0: 416  ← 小核 capacity
#   cpu4: 1024 ← 大核 capacity

# 4. 看 CPU 是否 online
adb shell "cat /sys/devices/system/cpu/cpu*/online"
# 输出:
#   cpu0: 1
#   cpu4: 1
```

**关键**：
- Android 14 典型 big.LITTLE：4 小核（cpu0-3）+ 4 大核（cpu4-7）
- capacity 是 EAS 选 CPU 的核心依据
- 大核 capacity = 1024（满），小核 capacity = 416（40%）

### 1.4 CPU 拓扑在内核的表示

```c
// include/linux/topology.h
struct cpu_topology {
    int thread_id;
    int core_id;
    int cluster_id;     // 哪一 cluster（big.LITTLE 区分 cluster）
    cpumask_t thread_siblings;  // 同一物理核的 SMT 兄弟
    cpumask_t core_siblings;    // 同一 cluster 的所有核
    int package_id;
    cpumask_t llc_siblings;    // 共享 LLC（Last Level Cache）的核
};

// kernel/sched/topology.c build_sched_domains
// 根据 cpu_topology 构建 sched_domain 树
```

**关键认知**：
- `cluster_id` 区分大小核——同一 cluster 内 L2 cache 共享
- `llc_siblings` 是 EAS 决策的关键——任务尽量在 LLC sibling 内跑
- 调度域（sched_domain）就是基于这些拓扑构建的

---

## 二、CPU 拓扑与缓存层级

### 2.1 big.LITTLE 架构

```
典型的 big.LITTLE 8 核 SoC：

┌─────────────────┐  ┌─────────────────┐
│  LITTLE cluster │  │   big cluster   │
│                 │  │                 │
│  cpu0  cpu1     │  │  cpu4  cpu5     │
│  cpu2  cpu3     │  │  cpu6  cpu7     │
│                 │  │                 │
│  Cortex-A55     │  │  Cortex-A78     │
│  1.8GHz         │  │  2.8GHz         │
│  capacity 416   │  │  capacity 1024  │
│  共享 L2        │  │  共享 L2        │
└─────────────────┘  └─────────────────┘
        │                    │
        └──────┬─────────────┘
               │
        ┌──────▼──────────┐
        │  System Cache   │
        │  + DRAM         │
        └─────────────────┘
```

**关键**：
- LITTLE cluster 省电——适合后台任务
- big cluster 性能高——适合前台任务
- EAS 决定 task 放哪

### 2.2 缓存层级对调度的影响

```
L1 cache：每 CPU 独立（最小、最快）
L2 cache：每 cluster 共享（中等）
LLC / L3：所有核共享（最大、最慢）

调度器考虑：
  - L1 命中：~1ns
  - L2 命中：~5ns
  - LLC 命中：~20ns
  - DRAM：~100ns
  
迁移 task 的成本：
  - 跨 CPU：L1 完全失效
  - 跨 cluster：L2 失效
  - 跨 NUMA 节点：LLC 失效
```

**关键**：
- 同 CPU 不迁移——cache 全热
- 同 cluster 可迁移——L2 仍可用
- 跨 cluster 迁移——L2 失效，性能损失

### 2.3 cpufreq 与 cpuidle 的关系

```bash
# 1. 看 CPU 调频策略
adb shell "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
# 输出: schedutil  ← Android 14 默认的 governor

# 2. 看 cpuidle 的 C-state
adb shell "cat /sys/devices/system/cpu/cpu0/cpuidle/state*/name"
# 输出: WFI / cpu-sleep-0 / cpu-sleep-1
```

**关键**：
- `schedutil` governor 由 scheduler 驱动——按 util_avg 调频
- `WFI` 是 ARM 的 Wait For Interrupt——最低功耗 C-state
- EAS 同时考虑 cpufreq 和 cpuidle——找最省电的 CPU

### 2.4 NUMA 拓扑（部分 Android 14 设备）

```bash
# 看 NUMA 拓扑
adb shell "cat /sys/devices/system/node/node*/cpulist"
# 输出:
#   node0: 0-3    ← 小核 cluster
#   node1: 4-7    ← 大核 cluster
```

**关键**：
- Android 14 部分高端 SoC 有 NUMA——cluster 跨 NUMA
- 跨 NUMA 访问慢——task 尽量在本 NUMA 节点
- NUMA-aware 调度在 EAS 中处理

---

## 三、sched_domain：调度域

### 3.1 sched_domain 是什么

`sched_domain` 是分层的**调度域**——多核调度器用它组织 CPU 拓扑：

```
顶层：DIE domain（所有核）
  │
  ├── 中层：MC domain（multi-core / cluster）
  │     │
  │     ├── 内层：SMT domain（per-CPU，超线程）
  │     │     │
  │     │     └── CPU
  │     │
  │     └── CPU / CPU / CPU / CPU
  │
  └── CPU / CPU / CPU / CPU
```

**关键认知**：
- 调度域是"树形"结构——根覆盖所有 CPU，叶子覆盖单 CPU
- **同 cluster 的 CPU 在同一个 MC domain 内**——可以做 cluster 内负载均衡
- **跨 cluster 在 DIE domain 内**——可以做全局负载均衡

### 3.2 sched_domain 结构

```c
// kernel/sched/sched.h
struct sched_domain {
    struct sched_domain *parent;     // 父 domain
    struct sched_domain *child;      // 子 domain

    struct sched_group *groups;      // 这个 domain 内的 group 列表
    unsigned long min_interval;      // 负载均衡最小间隔
    unsigned long max_interval;      // 负载均衡最大间隔

    unsigned int busy_factor;        // 负载阈值倍数
    unsigned int imbalance_pct;      // 不平衡容忍度
    unsigned int cache_nice_tries;   // cache_nice 尝试次数

    int flags;                       // SD_LOAD_BALANCE / SD_BALANCE_WAKE / ...
    int level;                       // domain 层级

    // ops
    const struct sched_domain_ops *ops;

    // ... 统计
};

// domain flag
enum {
    SD_LOAD_BALANCE,         // 负载均衡
    SD_BALANCE_NEWIDLE,      // 新建 idle 时均衡
    SD_BALANCE_WAKE,         // wake 时均衡
    SD_BALANCE_EXEC,         // exec 时均衡
    SD_BALANCE_FORK,         // fork 时均衡
    SD_WAKE_AFFINE,          // wake_affine
    SD_SHARE_CPUCAPACITY,    // 共享 CPU 容量（同 cluster）
    // ...
};
```

**关键字段**：
- `parent` / `child`：树形结构
- `flags`：domain 能力——能做哪些均衡
- `ops`：domain 特定的操作

### 3.3 sched_domain 层级

```c
// kernel/sched/topology.c
enum sched_domain_level {
    SD_LEVEL_NONE = 0,
    SD_LEVEL_SMT,    // 超线程兄弟
    SD_LEVEL_MC,     // multi-core（同 cluster）
    SD_LEVEL_NUMA,   // NUMA 节点
    SD_LEVEL_MAX,
};

// Android 14 典型 8 核 big.LITTLE 的 domain 结构：
// DIE domain (cpu0-7)
//   └── MC domain (cpu0-3 小核 cluster)
//   │     └── CPU
//   │     └── CPU
//   │     └── CPU
//   │     └── CPU
//   └── MC domain (cpu4-7 大核 cluster)
//         └── CPU
//         └── CPU
//         └── CPU
//         └── CPU
```

**关键**：
- DIE domain 做全局均衡——可能跨 cluster 迁移
- MC domain 做 cluster 内均衡——不跨 cluster
- 跨 cluster 迁移成本高——EAS 会尽量避免

### 3.4 sched_domain_shared

```c
// kernel/sched/sched.h
struct sched_domain_shared {
    atomic_t ref;                 // 引用计数
    unsigned int nr_load_avg;     // 共享的 load_avg 数量
    // ...
};

// 每个 MC domain 有一个 sched_domain_shared
// 同一 cluster 的 CPU 共享 L2 cache——负载均衡时考虑
```

**关键**：
- 同 cluster 的 CPU 共享 `sched_domain_shared`
- 共享 cache 的 task 迁移成本低
- EAS 利用这一点做 cluster 内调度

### 3.5 sched_group

```c
// kernel/sched/sched.h
struct sched_group {
    struct sched_group *next;     // 链表 next
    atomic_t ref;                 // 引用计数

    unsigned int group_weight;    // 这个 group 的 CPU 数
    unsigned int cores;           // 物理核数
    struct cpumask cpumask;       // 这个 group 的 CPU 列表

    // 每个 CPU 的 CPU capacity（用于 EAS）
    unsigned long cpu_capacity[]; // 变长数组
};
```

**关键**：
- `sched_group` 是 `sched_domain` 内的子单元
- 一个 domain 可能有多个 group——每个 group 是候选迁移目标
- `cpu_capacity` 是 EAS 决策的关键

### 3.6 Android 14 上看 sched_domain

```bash
# 看调度域（需要 root）
adb shell "cat /proc/sys/kernel/sched_domain/cpu0/domain0/name 2>/dev/null"
# 输出: DIE
adb shell "cat /proc/sys/kernel/sched_domain/cpu0/domain1/name 2>/dev/null"
# 输出: MC
```

**关键**：
- `/proc/sys/kernel/sched_domain/<cpu>/domain<N>/` 暴露 domain 信息
- 这在 Android 14 上**不是默认开启**——需要 root
- 大多数场景看 dmesg 或 perfetto

---

## 四、负载均衡（load_balance）

### 4.1 负载均衡的核心思想

**目标**：让所有 CPU 的负载尽量接近——避免某些 CPU 满载、某些空闲。

**两类操作**：
- **pull**：CPU 自己 idle，主动拉其他 CPU 的 task 过来
- **push**：其他 CPU 过载，把 task 推过来

### 4.2 负载均衡的触发时机

```c
// kernel/sched/fair.c
// 触发点：
// 1. scheduler_tick - 每 tick 检查 idle CPU
// 2. try_to_wake_up - wake up 时检查
// 3. nohz_idle_balance - idle CPU 不平衡时主动均衡
// 4. CPU hotplug - 热插拔
// 5. sched_domain 更新
```

**关键**：
- tick 中检查——最频繁
- wake up 时检查——影响 wake_affine 决策
- idle CPU 主动均衡——nohz_idle_balance

### 4.3 load_balance 的核心算法

```c
// kernel/sched/fair.c load_balance
static int load_balance(int cpu, struct rq *this_rq,
                        struct sched_domain *sd, enum cpu_idle_type idle,
                        int *continue_balancing)
{
    struct sched_group *group;
    struct rq *busiest;
    unsigned long flags;
    struct cpumask *cpus = this_cpu_cpumask_var_ptr(load_balance_mask);

    // 1. 找最忙的 group
    group = find_busiest_group(sd, this_rq, &busiest, idle);
    if (!group)
        goto out_balanced;

    // 2. 找最忙的 rq
    busiest = find_busiest_queue(sd, busiest, this_cpu);
    if (!busiest || busiest == this_rq)
        goto out_balanced;

    // 3. 算需要迁移多少
    nr_balance_tasks = calculate_imbalance(sd, busiest, this_rq);
    if (!nr_balance_tasks)
        goto out_balanced;

    // 4. 迁移 task
    if (move_tasks(this_rq, busiest, nr_balance_tasks, ...)) {
        // 成功迁移
    }

    return 1;
}
```

**关键路径**：
1. 找最忙的 group
2. 找最忙的 rq
3. 计算不均衡量
4. 迁移 task

### 4.4 find_busiest_group

```c
// kernel/sched/fair.c find_busiest_group
static struct sched_group *
find_busiest_group(struct sched_domain *sd, struct rq *this_rq,
                   struct rq **busiest, enum cpu_idle_type idle)
{
    struct sched_group *group, *busiest_group = NULL;
    unsigned long max_load, busiest_load = 0;
    int busiest_sd_idle;

    for_each_group(sd, group) {
        // 1. 计算 group 的负载
        load = scale_load_down(group_load(group));

        // 2. 找出最大负载
        if (load > busiest_load) {
            busiest_load = load;
            busiest_group = group;
        }
    }

    // 3. 检查不均衡
    if (busiest_load - this_load > imbalance) {
        *busiest = busiest_rq;
        return busiest_group;
    }

    return NULL;  // 平衡——不需要迁移
}
```

**关键**：
- 遍历所有 group，找最大负载
- 跟当前 CPU 负载比，超过阈值就迁移
- 不平衡阈值 `imbalance` 是动态算的

### 4.5 负载不均衡阈值

```c
// kernel/sched/fair.c calculate_imbalance
static unsigned long calculate_imbalance(struct sched_domain *sd,
                                        struct rq *busiest,
                                        struct rq *this_rq)
{
    unsigned long max_imb;
    int busiest_weight, this_weight;
    int imbalance = sd->imbalance_pct;
    int imbn;

    // 1. 基础阈值
    if (busiest->nr_running > 1)
        imbalance = max(sd->imbalance_pct, 100);

    // 2. 算 busy / this 的负载差
    max_imb = busiest->avg.load_avg - this_rq->avg.load_avg;

    // 3. 算出需要迁多少 task
    imbn = div_u64(max_imb * busiest_weight, busiest_load);
    imbn = min(imbn, busiest->nr_running);

    return imbn;
}
```

**关键**：
- 阈值 `imbalance_pct` 默认 117%
- 实际迁移数 = 负载差 × 比例
- 不超过 busiest 的 runnable task 数

### 4.6 迁移 task：move_tasks

```c
// kernel/sched/fair.c move_tasks
static int move_tasks(struct rq *dst_rq, struct rq *src_rq,
                      int max_tasks_move, ...)
{
    struct sched_domain *sd;
    struct task_struct *p;

    for (;;) {
        // 1. 找 src_rq 上要迁移的 task
        if (src_rq->nr_running <= 1)
            break;

        // 2. 取 src rq 的 leftmost（CFS 最久没跑的）
        p = pick_next_task_fair(src_rq, ...);
        if (!p)
            break;

        // 3. 检查 cache affinity
        if (!can_migrate(p, dst_cpu, sd)) {
            // 不能迁移——试下一个
            continue;
        }

        // 4. 迁移
        migrate_task(p, dst_rq);
        moved++;
    }
    return moved;
}
```

**关键**：
- 优先迁移 CFS 最久没跑的 task——避免影响任务调度
- 检查 cache affinity——同 cluster 优先
- 实际迁移通过 `migrate_task` 完成

### 4.7 cache_nice：跨 cluster 的成本考虑

```c
// kernel/sched/fair.c can_migrate
static int can_migrate(struct task_struct *p, int dst_cpu,
                       struct sched_domain *sd)
{
    // 1. 检查 task 是否允许 dst_cpu
    if (!cpumask_test_cpu(dst_cpu, p->cpus_allowed))
        return 0;

    // 2. 检查 cache affinity
    // 如果 task 在 src_cpu 跑了一段时间——cache 热
    // 迁到 dst_cpu——cache 失效
    tsk_cache_hot = task_hot(p, rq_clock_task(src_rq), sd);

    // 3. cache hot 的话，cache_nice_tries 次之后才能迁
    if (tsk_cache_hot && --sd->cache_nice_tries)
        return 0;

    return 1;  // 可以迁移
}
```

**关键**：
- "cache hot" = task 跑的时间 < `cache_decay_ticks`（默认 100ms）
- cache hot 时尝试 cache_nice_tries 次才迁移
- 减少不必要的跨 cluster 迁移

---

## 五、EAS（Energy Aware Scheduling）

### 5.1 EAS 是什么

**EAS = Energy Aware Scheduling**，从 Linux 3.16 起进入 mainline，Android 8.0 起强制实现。

**核心思想**：
- 不仅考虑"放在哪颗 CPU 性能最好"
- 还考虑"放在哪颗 CPU 最省电"
- 用能耗模型（energy model）计算每个 CPU 在指定负载下的功耗

**关键认知**：
- EAS 是 Android 14 调度器的核心
- Vendor 必须在 device tree 提供 energy model
- 没有 energy model 时 EAS 退化——fallback 到传统调度

### 5.2 Energy Model 数据结构

```c
// include/linux/energy_model.h
struct em_perf_domain {
    cpumask_t cpus;                 // 这个 domain 的 CPU
    unsigned long frequency;         // 当前频率
    unsigned long max_frequency;     // 最大频率
    unsigned long min_frequency;     // 最小频率
    unsigned long cost;              // 切换到这个 domain 的成本
    unsigned long flags;             // EM_PERF_DOMAIN_*

    // 每个 performance state 的功耗
    struct em_perf_state *states;
    unsigned int nr_states;
};

// 每个 performance state
struct em_perf_state {
    unsigned long frequency;   // 频率
    unsigned long power;       // 功耗（mW）
    unsigned long cost;        // 成本（用于 EAS 决策）
};
```

**关键**：
- `em_perf_domain`：能效域——通常是一个 cluster
- `states`：每个 P-state（频点）的功耗
- EAS 调度器根据 util_avg 选最省电的 P-state + CPU

### 5.3 EAS 的决策函数

```c
// kernel/sched/fair.c find_energy_efficient_cpu
static int find_energy_efficient_cpu(struct task_struct *p, int cpu,
                                      int prev_cpu)
{
    unsigned long prev_energy = ULONG_MAX, best_energy = ULONG_MAX;
    struct sched_domain *sd;
    int best_energy_cpu = -1;
    struct root_domain *rd;

    // 1. EAS 是否启用
    rd = cpu_rq(cpu)->rd;
    if (!rd->pd)
        goto eas_not_ready;  // EAS 未启用——fallback

    // 2. 遍历所有 candidate CPU
    for_each_cpu(cpus, cpu_online_mask) {
        struct em_perf_domain *pd;
        unsigned long util, energy;

        // 3. 算把 p 放到 cpu 的能耗
        pd = em_pd_get(cpus);
        util = cpu_util(cpu, p);
        energy = em_cpu_energy(pd, util, p->cpus_allowed, cpu);

        // 4. 找最小能耗
        if (energy < best_energy) {
            best_energy = energy;
            best_energy_cpu = cpu;
        }
    }

    return best_energy_cpu;
}
```

**关键**：
- EAS 遍历所有 CPU，算把 task 放上去的能耗
- 选能耗最低的 CPU——这是 Android 14 的默认策略

### 5.4 em_cpu_energy 的计算

```c
// kernel/sched/energy.c em_cpu_energy
static unsigned long em_cpu_energy(struct em_perf_domain *pd,
                                   unsigned long max_util, unsigned long sum_util,
                                   unsigned long allowed_cap, int cpu)
{
    unsigned long freq, scale_cpu;
    struct em_perf_state *ps;
    int i;

    // 1. 找到合适的 P-state
    // max_util 决定需要多少算力
    // 在 P-state 列表中选最便宜的

    // 2. 算功耗
    for (i = 0; i < pd->nr_states; i++) {
        ps = &pd->states[i];
        // 计算 freq 对应的功耗
        // power = ps->power * sum_util / allowed_cap
        // ...
    }

    return total_energy;
}
```

**关键**：
- EAS 算的是"把 task 放上去后，整个 cluster 的总功耗"
- 选最便宜的 cluster + P-state

### 5.5 EAS 在 wake up 路径

```c
// kernel/sched/fair.c select_task_rq_fair
static int select_task_rq_fair(struct task_struct *p, int prev_cpu, int wake_flags)
{
    int sync = (wake_flags & WF_SYNC) && !likely(current->flags & PF_EXITING);
    int new_cpu = prev_cpu;

    // 1. wake_affine 决策
    if (sd_flag & SD_WAKE_AFFINE) {
        // 在当前 CPU 调度——降低 cache miss
        new_cpu = wake_affine(sd, p, prev_cpu, this_cpu, sync);
        if (new_cpu != -1)
            goto out;
    }

    // 2. EAS 决策
    new_cpu = find_energy_efficient_cpu(p, prev_cpu);
    if (new_cpu >= 0)
        goto out;

    // 3. fallback：找 idle CPU
    new_cpu = find_idlest_cpu();

out:
    return new_cpu;
}
```

**关键认知**：
- wake_affine 优先——减少 cache miss
- 找不到 wake_affine 才用 EAS
- EAS 失败用 idle CPU fallback
- 这就是 Android 14 上"前台任务在大核跑"的路径

### 5.6 EAS 在 Android 14 上的状态

```bash
# 看 EAS 是否启用
adb shell "cat /sys/kernel/debug/sched_features 2>/dev/null | grep ENERG"
# 或：
adb shell "dmesg | grep -i 'eas\|energy'"
# 看到 "sched-energy" 信息说明 EAS 已启用

# 看 energy model
adb shell "ls /sys/kernel/debug/energy_model/"
# 输出: cpu0 cpu1 cpu2 cpu3 cpu4 cpu5 cpu6 cpu7

# 看某个 CPU 的能耗
adb shell "cat /sys/kernel/debug/energy_model/cpu0/0"
# 输出: 1000000 100  ← freq, power
```

**关键**：
- EAS 默认开启——vendor 必须支持
- 没有 energy model 时 EAS 退化
- Android 14 上 vendor 在 device tree 提供 model

### 5.7 EAS 与 UClamp 的耦合

```c
// kernel/sched/fair.c find_energy_efficient_cpu
// UClamp 修正 util 估算
static unsigned long effective_cpu_util(int cpu, unsigned long util,
                                        struct task_struct *p)
{
    // 1. 应用 UClamp
    util = uclamp_eff_value(p, util);
    // uclamp_min 提高 util——让调度器认为 task 更"重"
    // uclamp_max 降低 util——让调度器认为 task 更"轻"

    return min(util, capacity_of(cpu));
}
```

**关键**：
- EAS 决策前会应用 UClamp 修正
- uclamp_min 高 → 调度器认为 task 重 → 放大核
- uclamp_max 低 → 调度器认为 task 轻 → 放小核
- 这是 Android 14 上"top-app 优先放大核"的实现

---

## 六、WALT vs PELT：负载算法

### 6.1 WALT 是什么

**WALT = Window-Assisted Load Tracking**，Google 自研的负载算法，Android 8.0+ 默认。

**核心思想**：
- 用"窗口"（window，如 100ms）算平均负载——比 PELT 反应快
- 显式区分"过去 N 毫秒"的负载——直接 window
- 不像 PELT 那样用指数衰减

```c
// kernel/sched/walt/walt.h
struct walt_task_struct {
    u64 cumulative_runnable_avg_scaled;  // 累计 runnable 时间
    u64 pred_demand_scaled;              // 预测的 demand
    u64 pred_demand_scaled_history[MAX_PRED_DEMAND_HISTORY];
    // ...
};
```

### 6.2 WALT 与 PELT 的对比

```
PELT（Linux 内核默认）：
  - 时间衰减常数：32 ms
  - 用 1024μs 衰减——更平滑但反应慢
  - 历史 32+ms 才收敛

WALT（Android 默认）：
  - 时间窗口：100ms
  - 直接算 100ms 内的累计负载
  - 反应快——window 内任务变化立即反映
```

**关键**：
- WALT 比 PELT 反应快——更适合 EAS 决策
- PELT 反应慢但平滑——适合 cpufreq / 统计
- Android 14 上默认 WALT——Linux 5.10 内核已支持

### 6.3 WALT 在内核的实现位置

```
kernel/sched/
├── fair.c          ← CFS 主入口
├── pelt.c          ← PELT 算法
├── walt.c          ← WALT 算法（Android 14 GKI）
└── ...

// Android 14 上 WALT 是 GKI 一部分——所有 vendor 共享
```

**关键**：
- WALT 在 Linux 5.10 GKI 中——所有 Android 14 设备都能用
- 不再是 vendor 私货
- 这是 Android 14 调度统一的关键

### 6.4 看 WALT 状态

```bash
# 看 WALT 状态
adb shell "cat /proc/sys/kernel/sched_walt_init_task_load_pct"
# 默认: 100
adb shell "cat /proc/sys/kernel/sched_walt_load_avg_period_ms"
# 默认: 100ms

# 看 WALT 调度事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_update_task_ravg' --time 30"
```

### 6.5 选 PELT 还是 WALT

```c
// kernel/sched/walt/walt.c
// Android 14 GKI 默认 WALT——但可以切换
CONFIG_WALT=y
CONFIG_SCHED_WALT=y

// 不开启 WALT 时用 PELT
// WALT 开启时调度事件不同
```

**关键**：
- Android 14 GKI 默认 WALT
- 性能调优可能关 WALT
- 大多数场景不需要改

---

## 七、UClamp：top-app / background 的调度提示

### 7.1 UClamp 是什么

**UClamp = Utilization Clamp**，从 Linux 5.3 进入 mainline，Android 11+ 强制使用。

**两个值**：
- `uclamp_min`：task 的最小利用率保证
- `uclamp_max`：task 的最大利用率上限

```c
// include/linux/sched.h
struct task_struct {
    struct uclamp_se uclamp_req[UCLAMP_CNT];   // 用户请求的 UClamp
    struct uclamp_se uclamp[UCLAMP_CNT];        // 实际生效的 UClamp
};

// uclamp_min = 50% → 调度器会"挤"出 50% CPU 给这个 task
// uclamp_max = 80% → 调度器不会让这个 task 跑超过 80% CPU
```

### 7.2 UClamp 怎么影响 EAS

```c
// kernel/sched/fair.c
// 在 find_energy_efficient_cpu 中调用
static unsigned long uclamp_eff_value(struct task_struct *p,
                                       unsigned long util)
{
    unsigned long min = uclamp_value(p, UCLAMP_MIN);
    unsigned long max = uclamp_value(p, UCLAMP_MAX);

    util = max(util, min);  // uclamp_min 提高 util
    util = min(util, max);  // uclamp_max 降低 util
    return util;
}
```

**关键认知**：
- `uclamp_min` 高 → 调度器认为 task 重 → 选大核
- `uclamp_max` 低 → 调度器认为 task 轻 → 选小核
- 这就是 Android 14 上 top-app 强制放大核、background 强制放小核的机制

### 7.3 Android 14 上的 UClamp 配置

```bash
# 1. 看 top-app slice 的 UClamp
adb shell "cat /sys/fs/cgroup/top-app.slice/cpu.uclamp.min"
# 输出: 0  ← 默认
adb shell "cat /sys/fs/cgroup/top-app.slice/cpu.uclamp.max"
# 输出: max  ← 默认

# 2. 看 background slice 的 UClamp
adb shell "cat /sys/fs/cgroup/background.slice/cpu.uclamp.min"
# 输出: 0
adb shell "cat /sys/fs/cgroup/background.slice/cpu.uclamp.max"
# 输出: max

# 3. 看 task 自己的 UClamp
adb shell "cat /proc/<pid>/sched | grep uclamp"
```

**关键**：
- 默认都是 0 / max——无约束
- Android 14 上 Framework 通过 libprocessgroup 设置 UClamp
- 设置时机：app 启动到前台 / 退到后台

### 7.4 top-app 进入前台时的 UClamp 设置

```java
// frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java
// 当应用进入前台：
public void setProcessGroup(int uid, int pid, int group) {
    // top-app 时给 uclamp.min = 50%（让前台应用有保证的 CPU）
    if (group == Process.TOP_APP) {
        mProcessGroupInfo.setUclamp(pid, 50, 100);
    }
}

// 退后台时
public void setBackground(int uid, int pid) {
    // background slice 的 uclamp.min = 0
    mProcessGroupInfo.setUclamp(pid, 0, 100);
}
```

**关键**：
- 进程进 top-app：uclamp_min = 50
- 退到 background：uclamp_min = 0
- 这是 Android 14 调度的关键优化

### 7.5 UClamp 的稳定性影响

```bash
# UClamp 配置错误的症状：
# - top-app 卡（uclamp_min 没设）
# - background 占太多 CPU（uclamp_max 没设）

# 排查：
adb shell "cat /proc/<pid>/sched | grep uclamp"
# 看实际生效的 uclamp 值
```

**关键**：
- UClamp 配置错误直接导致性能问题
- Framework 层 setUclamp 是关键路径
- Vendor 改 framework 要小心

---

## 八、cpuset：限制 task 跑在哪些 CPU

### 8.1 cpuset 是什么

```bash
# 1. 看 cpuset cgroup v2
adb shell "cat /sys/fs/cgroup/cpuset.cpus"
# 输出: 0-7  ← 默认所有 CPU

# 2. 看 top-app slice 的 cpuset
adb shell "cat /sys/fs/cgroup/top-app.slice/cpuset.cpus"
# 输出: 4-7  ← 只允许大核

# 3. 看 background slice 的 cpuset
adb shell "cat /sys/fs/cgroup/background.slice/cpuset.cpus"
# 输出: 0-3  ← 只允许小核
```

**关键**：
- Android 14 上 top-app 默认只允许大核
- background 默认只允许小核
- 这就是 Android 14 的 CPU 集策略

### 8.2 cpuset 的内核实现

```c
// kernel/cgroup/cpuset.c
struct cpuset {
    struct cgroup_subsys_state css;
    unsigned long flags;          // CS_SPREAD_PAGE / CS_SCHED_LOAD_BALANCE
    cpumask_var_t cpus_allowed;   // 允许的 CPU
    // ...
};

// task 进 cpuset 时
// kernel/cgroup/cpuset.c cpuset_attach_task
static void cpuset_attach_task(struct cpuset *cs, struct task_struct *task)
{
    // 1. 设置 task 的 cpus_allowed
    set_cpus_allowed(task, cs->cpus_allowed);
    // 2. 触发迁移
    wake_up_process(task);
}
```

**关键**：
- task 进 cpuset 时 cpus_allowed 被更新
- 调度器只能用 cpus_allowed 内的 CPU
- 跨 cpuset 迁移通过 wake_up_process 触发

### 8.3 cpuset 与 EAS 的协作

```
top-app slice:
  cpus_allowed: {4, 5, 6, 7}    ← 只能跑大核
  uclamp_min: 50                  ← 保证放大核
  uclamp_max: 100                 ← 不限制

background slice:
  cpus_allowed: {0, 1, 2, 3}    ← 只能跑小核
  uclamp_min: 0                   ← 不保证
  uclamp_max: 80                  ← 不超过 80%

调度器行为：
  - top-app task 唤醒 → EAS 在 {4,5,6,7} 选最省电
  - background task 唤醒 → EAS 在 {0,1,2,3} 选最省电
  - 跨 cpuset 迁移禁止
```

**关键认知**：
- cpuset 决定"允许哪些 CPU"
- UClamp 决定"在允许的 CPU 中选哪个"
- 两者配合实现 Android 14 的"前台大核、后台小核"策略

### 8.4 cpuset 在 Android 14 上的实际配置

```bash
# Android 14 的 cgroup v2 cpuset 配置
adb shell "find /sys/fs/cgroup -name 'cpuset.cpus' -exec sh -c 'echo === \$1 ===; cat \$1' _ {} \;"
```

**典型输出**：

```
=== /sys/fs/cgroup/cpuset.cpus ===
0-7
=== /sys/fs/cgroup/top-app.slice/cpuset.cpus ===
4-7                  ← top-app 只能大核
=== /sys/fs/cgroup/foreground.slice/cpuset.cpus ===
0-7                  ← foreground 任意
=== /sys/fs/cgroup/background.slice/cpuset.cpus ===
0-3                  ← background 只能小核
=== /sys/fs/cgroup/system.slice/cpuset.cpus ===
0-7                  ← system 任意
=== /sys/fs/cgroup/system-background.slice/cpuset.cpus ===
0-3                  ← system-background 只能小核
```

**关键**：
- Android 14 默认配置——top-app 强制大核
- vendor 可以改——但要保证前台体验

### 8.5 cpuset 与 cpufreq

```bash
# 看小核 cluster 的最大频率
adb shell "cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"
# 1800000

# 看大核 cluster 的最大频率
adb shell "cat /sys/devices/system/cpu/cpu4/cpufreq/cpuinfo_max_freq"
# 2800000
```

**关键**：
- top-app 只能跑大核——但大核频率可能不高
- 如果大核频率低 → top-app 也跑不快
- cpuset + cpufreq 配合调优

---

## 九、CPU 热插拔 / 调频

### 9.1 CPU hotplug

```bash
# 1. 看 CPU 是否 online
adb shell "ls /sys/devices/system/cpu/ | grep -E 'cpu[0-9]+$'"
# 输出: cpu0 cpu1 cpu2 cpu3 cpu4 cpu5 cpu6 cpu7

# 2. 离线一个 CPU（需要 root）
adb shell "echo 0 > /sys/devices/system/cpu/cpu4/online"
# cpu4 下线

# 3. 上线一个 CPU
adb shell "echo 1 > /sys/devices/system/cpu/cpu4/online"
```

**关键**：
- CPU hotplug 影响调度——offline CPU 的 task 必须迁移
- Android 14 上 hotplug 由 kernel core control 控制
- 高负载时上 CPU、空闲时下 CPU

### 9.2 cpufreq governor

```bash
# 看 governor 类型
adb shell "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
# schedutil  ← Android 14 默认

# schedutil 根据调度器提供的 util 调频
# ondemand / conservative / powersave / performance / userspace
```

**关键**：
- `schedutil`：由调度器驱动——按 util_avg 调频
- `ondemand`：基于频率利用率——传统 governor
- `performance`：一直最高频率
- Android 14 默认 `schedutil`

### 9.3 schedutil governor 的实现

```c
// drivers/cpufreq/cpufreq_schedutil.c
// 在每次 util 更新时调
static void sugov_update_shared(struct update_util_data *data,
                                  u64 time, unsigned int flags)
{
    struct sugov_cpu *sg_cpu = container_of(data, struct sugov_cpu, update_util);
    struct sugov_policy *sg_policy = sg_cpu->sg_policy;
    unsigned long util, max;
    unsigned int next_freq;

    // 1. 获取 util（来自调度器）
    sugov_get_util(&util, &max);

    // 2. 算目标频率
    next_freq = sugov_next_freq_shared(sg_cpu, util, max);
    // util / max * scaling_max_freq

    // 3. 调频
    if (next_freq != sg_policy->next_freq) {
        sg_policy->next_freq = next_freq;
        cpufreq_driver_adjust_perf(sg_policy->policy, next_freq);
    }
}
```

**关键认知**：
- 调度器在 update_load_avg 时会调 `cpufreq_update_util`
- schedutil 接到 util 后算目标频率
- 这就是"scheduler 驱动 cpufreq"的具体实现

### 9.4 schedutil 与 UClamp 的耦合

```c
// cpufreq_schedutil.c sugov_get_util
// 考虑 UClamp
static void sugov_get_util(unsigned long *util, unsigned long *max)
{
    // 1. 拿 cfs_rq 的 util_avg
    *util = cpu_util_cfs(cpu);

    // 2. 应用 UClamp
    // 如果 task 有 uclamp_min，用 uclamp_min 替换 util
    // 如果 task 有 uclamp_max，用 uclamp_max 截断 util
    *util = uclamp_eff_value(p, *util);

    *max = capacity_of(cpu);
}
```

**关键**：
- cpufreq 也用 UClamp——保证 top-app 频率
- uclamp_min 高 → 频率更高
- 这就是 Android 14 上"前台反应快"的实现

### 9.5 cpuidle 与多核调度

```bash
# 看 cpuidle 状态
adb shell "cat /sys/devices/system/cpu/cpu0/cpuidle/state*/name"
# WFI / cpu-sleep-0 / cpu-sleep-1
```

**关键**：
- CPU idle 时进入 C-state——省电
- 但 C-state 唤醒有延迟
- EAS 考虑"放 idle CPU 省电 vs 唤醒延迟"的权衡

### 9.6 big.LITTLE + EAS + UClamp 的总效果

```
应用启动（top-app）：
  1. framework 调 setProcessGroup(pid, TOP_APP)
  2. cpuset: cpus_allowed = {4, 5, 6, 7}    ← 大核
  3. UClamp: min = 50, max = max              ← 50% CPU 保证
  4. 调度器决策：
     - EAS 在 {4,5,6,7} 选最便宜的 CPU
     - util = max(util_avg, 50%) → 选大核
     - 让 top-app 在大核跑，频率高，性能好

应用退到后台：
  1. framework 调 setProcessGroup(pid, BACKGROUND)
  2. cpuset: cpus_allowed = {0, 1, 2, 3}    ← 小核
  3. UClamp: min = 0, max = 80%               ← 不超过 80%
  4. 调度器决策：
     - EAS 在 {0,1,2,3} 选最便宜的 CPU
     - util = min(util_avg, 80%) → 选小核
     - background 在小核跑，频率低，省电
```

**关键认知**：
- 三者配合：cpuset 圈定范围、UClamp 圈定权重、EAS 在范围内选最优
- 这就是 Android 14 调度的核心机制

---

## 十、wake_affine 与任务迁移

### 10.1 wake_affine 是什么

```c
// kernel/sched/fair.c wake_affine
// 唤醒时优先在"当前 CPU"调度——减少 cache miss
static int wake_affine(struct sched_domain *sd, struct task_struct *p,
                       int this_cpu, int prev_cpu, int sync)
{
    int target = nr_cpumask_bits;

    // 1. 如果 this_cpu == prev_cpu——优先这个
    if (this_cpu == prev_cpu)
        return this_cpu;

    // 2. 检查 cache 亲和性
    if (sync && (sd->flags & SD_WAKE_AFFINE)) {
        // 同步 wakeup——优先同 CPU
        target = this_cpu;
    }

    // 3. 检查 idle 状态
    if (idle_cpu(this_cpu) && !idle_cpu(prev_cpu))
        target = this_cpu;

    // 4. 检查负载
    // ...
    return target;
}
```

**关键**：
- 唤醒时优先放原 CPU——cache 热
- 但要平衡负载——避免原 CPU 过载
- 这是 wake up 时的"省钱 vs 性能"权衡

### 10.2 select_task_rq 选 CPU 的完整路径

```c
// kernel/sched/fair.c select_task_rq_fair
static int select_task_rq_fair(struct task_struct *p, int prev_cpu, int wake_flags)
{
    int sync = ...;
    int new_cpu = prev_cpu;
    struct sched_domain *sd;
    int cpu = smp_processor_id();

    // 1. wake_affine
    if (sd_flag & SD_WAKE_AFFINE) {
        new_cpu = wake_affine(sd, p, prev_cpu, cpu, sync);
        if (new_cpu != -1)
            goto out;
    }

    // 2. EAS 决策
    if (sched_energy_enabled()) {
        new_cpu = find_energy_efficient_cpu(p, prev_cpu);
        if (new_cpu >= 0)
            goto out;
    }

    // 3. fallback: 找 idle CPU
    new_cpu = find_idlest_cpu(sd, p, cpu, prev_cpu, sync);
    if (new_cpu != -1)
        goto out;

out:
    return new_cpu;
}
```

**关键**：
- 三层决策：wake_affine → EAS → idle CPU
- 任一层找到合适的就返回
- 这是 Android 14 上"任务在哪颗 CPU 跑"的完整决策路径

### 10.3 跨 CPU 迁移的成本

```c
// kernel/sched/fair.c task_numa_migrate / migration_cost
// 跨 NUMA 节点迁移：~10μs
// 跨 cluster 迁移：~1-5μs（cache 失效）
// 同 cluster 迁移：~0.5-2μs（L2 失效）
// 同 CPU（无迁移）：0
```

**关键**：
- 跨 cluster 迁移成本中等
- 跨 NUMA 成本最高——尽量避免
- EAS 决策考虑这个成本

### 10.4 migration 任务

```c
// 跨 CPU 迁移由 migration 线程完成
// kernel/sched/core.c migration_thread
// 每个 CPU 一个 migration 线程
static int migration_thread(void *data)
{
    struct rq *rq = data;
    struct sched_domain *sd;
    int cpu = rq->cpu;

    while (!kthread_should_stop()) {
        // 1. 等迁移请求
        // 2. 停止 src cpu 的调度
        // 3. 迁移 task
        // 4. 恢复 src cpu 调度
    }
}
```

**关键**：
- migration 线程是高优先级内核线程
- 跨 CPU 迁移需要 migration 线程协调
- 频繁迁移会增加 migration 线程负担

---

## 十一、Android 14 实战：多核调度的真实场景

### 11.1 应用冷启动的调度路径

```bash
# 抓应用启动的调度事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_wakeup sched:sched_switch sched:sched_migrate_task \
        sched:sched_energy_diff sched:sched_uclamp' --time 30"
```

UI 上看到的完整流程：

```
[CPU 4] wakeup: pid=1234 (com.example.app)
   ↓ sched_energy_diff: CPU 4 是最省电（选中）
   ↓ sched_switch: 切到 pid=1234
   ↓ perfetto 显示 CPU 4 上跑
```

**关键**：
- 启动时 wakeup 触发 select_task_rq_fair
- EAS 选最省电 CPU——通常是大核（前台应用）
- perfetto 能完整看到调度决策

### 11.2 binder 调用的 CPU 分布

```bash
# 看 binder 调用的 CPU 分布
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_switch binder:transaction' --time 30"
```

**关键**：
- binder 调用在不同 CPU 跑——binding 线程池分散
- 系统服务（system_server）线程多——分布在多个 CPU
- 这是为什么 binder 调用延迟"稳定"

### 11.3 input 事件的调度

```bash
# input 事件路径
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_switch sched:sched_wakeup input:*' --time 30"
```

**关键**：
- touch 中断→唤醒 system_server→处理 input
- input 事件调度走 EAS——通常在大核
- 调度延迟 < 16ms 是 60Hz 流畅的保证

### 11.4 看 CPU 利用率分布

```bash
# 用 mpstat 风格工具
adb shell "top -m 8"
# 看到 8 个 CPU 的利用率

# 用 perfetto 累计
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_switch' --time 30"
```

**关键**：
- `top` 看瞬时状态
- perfetto 看时间序列
- 两者配合才能定位问题

### 11.5 看迁移事件

```bash
# 看迁移事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_migrate_task' --time 30"
```

**关键**：
- 频繁迁移 = 调度问题
- 跨 cluster 迁移 > 10次/秒 = 配置问题
- 单次迁移正常——cache_nice 兜底

---

## 十二、稳定性排查

### 12.1 负载不均

```bash
# 1. 看 CPU 利用率分布
adb shell "top -m 8 -n 1 -b"
# 看哪个 CPU 满载、哪个空闲

# 2. 看 sched_migrate_task 计数
adb shell "cat /proc/sched_debug | grep -A 5 'nr_migrate'"
```

**关键**：
- 负载不均症状：某些 CPU 100%，某些空闲
- 排查：调整 cpuset / UClamp / sched_domain flags

### 12.2 迁移风暴

```bash
# 看迁移频率
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_migrate_task' --time 30"
```

**关键**：
- > 50 次/秒 = 风暴
- 通常是 UClamp 配置错误——task 在 cluster 间跳
- 解决：调整 UClamp 让 task 留在 cluster 内

### 12.3 EAS 选错 CPU

```bash
# 1. 看 EAS 决策
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_energy_diff' --time 30"

# 2. 看 task 实际跑的 CPU
# 看到 task 频繁在小核、大核间跳 → EAS 选错
```

**关键**：
- EAS 选错通常因为 energy model 不准
- Vendor 必须用 vendor-specific data 校准
- 没有 energy model 时 EAS 退化

### 12.4 cpuset 配置错误

```bash
# 看 cpuset 配置
adb shell "cat /sys/fs/cgroup/<slice>/cpuset.cpus"

# 错误 1：top-app 包含小核
adb shell "cat /sys/fs/cgroup/top-app.slice/cpuset.cpus"
# 如果输出 0-7 → top-app 不只大核——性能差

# 错误 2：background 包含大核
adb shell "cat /sys/fs/cgroup/background.slice/cpuset.cpus"
# 如果输出 4-7 → background 抢大核——耗电
```

**关键**：
- cpuset 配置错了直接导致性能/耗电问题
- 必须保证 top-app 强制大核、background 强制小核

### 12.5 UClamp 配置错误

```bash
# 看 task 的 UClamp
adb shell "cat /proc/<pid>/sched | grep uclamp"
# uclamp.min 应该是 0（默认） 或 50（top-app）
# uclamp.max 应该是 max（默认） 或 80（background）

# 错误 1：top-app 没设 uclamp_min
# → 调度器认为 task 轻 → 放小核 → 性能差

# 错误 2：background uclamp_max 没设
# → 调度器不限 background → 后台抢大核 → 耗电
```

**关键**：
- UClamp 是 top-app / background 调度的核心
- Framework 层调 setProcessGroup 时设置
- Framework 改坏了直接性能回归

---

## 十三、给 10 篇留的钩子

读完 09 篇，你应该能：

1. 在脑中画出多核调度的全景图——CPU 拓扑 + 调度域 + 负载均衡 + EAS + UClamp。
2. 理解 big.LITTLE 架构——大小核分工。
3. 知道 sched_domain 是什么——分层的负载均衡结构。
4. 跟踪 load_balance 的核心算法。
5. 理解 EAS 怎么选最省电的 CPU。
6. 知道 WALT 算法跟 PELT 的差异。
7. 理解 UClamp 怎么影响调度。
8. 知道 cpuset 怎么限制 task 跑在哪些 CPU。
9. 理解 wake_affine 算法。
10. 能在 Android 14 上看 CPU 拓扑、负载、迁移事件。

**调度篇（阶段 C）全部结束——共 4 篇（06-09），约 7 万字**。本系列调度的核心机制讲完。

下一阶段：**阶段 D — 进程被控制（资源约束 + 协作）**

10 篇《cgroup v2：内核里的资源控制器》会回答：

> 调度器决定"跑多久"，cgroup 决定"能跑多少资源"。cgroup v2 在 Android 14 上是 top-app / background / system 切分的基础。
>
> - cgroup v1 vs v2 的内核实现差异
> - cgroup_subsys / cftype 文件系统抽象
> - memory 子系统账本（page_counter / memory.events）
> - cpu 子系统账本（bandwidth control）
> - freezer 子系统
> - cpuset 子系统（08 篇已涉及，10 篇完整展开）
> - Android 14 cgroup 树（top-app / background / system-background）
> - cgroup 与 OOM 的关联
>
> 读完 10-12，你将掌握"进程被约束"和"进程间协作"两条主线——这是 13 篇"调试 + 稳定性收口"的前提。

---

## 小结

| 维度 | 一句话总结 |
|---|---|
| 多核调度挑战 | 单核"挑谁跑"、多核还要"放哪颗 CPU 跑" |
| sched_domain | 分层结构——DIE / MC / SMT |
| 负载均衡 | load_balance——找最忙 group、迁移 task |
| EAS | 基于能耗模型——选最省电 CPU |
| WALT vs PELT | WALT 窗口快反应、PELT 指数衰减平滑 |
| UClamp | min/max——Android 14 top-app 调度的关键 |
| cpuset | 限制 task 在哪些 CPU 跑——top-app 强制大核 |
| wake_affine | 唤醒时优先原 CPU——cache 亲和性 |
| Android 14 | cpuset + UClamp + EAS + WALT 协同 |

---

## 给下篇的桥

**本篇留下三个钩子**：

1. UClamp 通过 cgroup 实现——10 篇完整展开 cpu 子系统
2. cpuset 是 cgroup 子系统之一——10 篇深入
3. OOM 跟 cgroup memory 强相关——10 篇 + 11 篇（信号）联动

如果读完本文仍有疑问：

- **"为什么 task 在 CPU 间跳？"** → §12.2 迁移风暴 + §12.5 UClamp 配置错误
- **"EAS 没启用会怎样？"** → §5.6 fallback 到传统调度
- **"top-app 怎么保证？"** → §7.4 framework setProcessGroup + §9.6 总效果

---

## 引用

| 引用 | 路径 |
|---|---|
| sched_domain | `kernel/sched/sched.h:struct sched_domain` |
| load_balance | `kernel/sched/fair.c:load_balance` |
| find_busiest_group | `kernel/sched/fair.c:find_busiest_group` |
| find_energy_efficient_cpu | `kernel/sched/fair.c:find_energy_efficient_cpu` |
| EAS | `kernel/sched/energy.c:em_cpu_energy` |
| energy model | `include/linux/energy_model.h` |
| UClamp | `kernel/sched/core.c:uclamp_eff_value` |
| WALT | `kernel/sched/walt/walt.c` |
| PELT | `kernel/sched/pelt.c` |
| cpuset | `kernel/cgroup/cpuset.c` |
| schedutil | `drivers/cpufreq/cpufreq_schedutil.c` |
| select_task_rq_fair | `kernel/sched/fair.c:select_task_rq_fair` |
| wake_affine | `kernel/sched/fair.c:wake_affine` |
| Android 14 cpuset | `/sys/fs/cgroup/top-app.slice/cpuset.cpus` |