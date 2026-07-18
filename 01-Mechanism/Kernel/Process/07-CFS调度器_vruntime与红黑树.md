# CFS 调度器：vruntime 与红黑树

> 系列第 07 篇 · 阶段 C · 调度
>
> **承上**：06 篇讲了调度基础架构——5 个调度类 + runqueue + context_switch。本篇展开**默认调度类 fair**——fair 类怎么挑下一个 task？这是 Linux 调度器最核心、最复杂的部分。
>
> **启下**：fair 类是默认，但 Android 14 上 audio / display / HAL 用 RT 调度。08 篇《调度扩展：RT / Deadline / Idle》展开其他调度类。
>
> **预计篇幅**：约 1.9 万字
>
> **源码基线**：Linux 5.10 / 5.15（Android 12-14 主流内核）。

---

## 学习目标

读完本文，你应该能：

1. 在脑中画出 CFS 调度器的核心数据结构——sched_entity + cfs_rq + 红黑树。
2. 理解 `vruntime` 的计算公式——`vruntime += delta_exec * NICE_0_LOAD / weight`。
3. 理解红黑树在 CFS 中的角色——按 vruntime 排序，最左节点 = 下一个 task。
4. 跟踪 `update_curr` 的完整路径——tick 时怎么更新 vruntime。
5. 跟踪 `pick_next_entity` 怎么挑 vruntime 最小——O(log n) 操作。
6. 理解 `sched_latency` 与 `sched_min_granularity`——调度延迟的核心参数。
7. 知道 PELT 算法怎么算 task / CPU 负载——`se->avg` / `cfs_rq->avg`。
8. 理解 task_group 与组调度——cgroup v1/v2 怎么影响 CFS。
9. 能在 Android 14 上看真实的 CFS 状态——`/proc/sched_debug` / perfetto。
10. 知道 nice / weight / UClamp 怎么影响 CFS 选 task。

---

## 一、CFS 调度器定位

### 1.1 "完全公平"是什么

CFS = **C**ompletely **F**air **S**cheduler。从 2.6.23（2007）开始，CFS 是 Linux 默认调度类。

**核心思想**：

```
如果有 N 个 runnable task：
  每个 task 应该分到 1/N 的 CPU 时间
  ─────────────────────────────
  这是"理想公平"
```

**实现方式**：
- 不用固定时间片——CFS 抛弃了 O(1) 调度器的时间片概念
- 改用 vruntime（虚拟时间）——所有 task 的 vruntime 应该尽量同步
- vruntime 小的 task 表示"被亏待了"——优先跑

**关键认知**：
- vruntime 是 CFS 的核心概念——所有 CFS 决策围绕它
- 权重（weight）由 nice 值映射——nice 越低、weight 越高、vruntime 增长越慢
- 红黑树是 CFS 的物理实现——按 vruntime 排序

### 1.2 CFS 在 Android 14 上的地位

```bash
# 1. 看系统进程的调度策略
adb shell "for pid in \$(ls /proc/ | grep -E '^[0-9]+$' | head -20); do
    policy=\$(cat /proc/\$pid/stat 2>/dev/null | awk '{print \$36}')
    case \$policy in
        0) echo \"\$pid CFS (NORMAL)\";;
        1) echo \"\$pid FIFO\";;
        2) echo \"\$pid RR\";;
        3) echo \"\$pid CFS (BATCH)\";;
        5) echo \"\$pid IDLE\";;
        6) echo \"\$pid DL\";;
        *) echo \"\$pid policy=\$policy\";;
    esac
done"
```

**典型输出**：

```
1 CFS (BATCH)              ← init
2 CFS (BATCH)              ← kthreadd
100 CFS (NORMAL)           ← system_server
120 FIFO                   ← audio HAL
130 FIFO                   ← display HAL
140 RR                     ← SurfaceFlinger（特定路径）
```

**关键**：
- 99% 的 Android 用户进程都是 CFS (NORMAL)
- audio / display / SurfaceFlinger 部分路径用 RT
- 极少数特殊场景用 DL / IDLE

### 1.3 CFS 解决的"老问题"

**O(1) 调度器的问题**（2.6.23 之前）：
- 固定时间片——交互式 task 反应慢
- 优先级反转——低优先级 task 持锁导致高优先级 task 等
- 多核伸缩性差——锁竞争严重

**CFS 的解决**：
- 抛弃固定时间片——按需分配
- vruntime 量化公平——所有 task 都跟踪 vruntime
- per-CPU runqueue——减少锁竞争（06 篇讲过）

### 1.4 CFS 关键参数

```c
// include/linux/sched.h / kernel/sched/fair.c
#define NICE_0_LOAD         (1L << 32)        // nice=0 的 weight
#define WEIGHT_IDLEPRIO     3                  // idle task 的 weight
// nice 值映射 weight
static const int prio_to_weight[40] = {
    /* -20 */     88761,     71755,     56483,     46273,     36291,
    /* -15 */     29154,     23254,     18705,     14949,     11916,
    /* -10 */      9548,      7620,      6100,      4904,      3906,
    /*  -5 */      3121,      2501,      1991,      1586,      1277,
    /*   0 */      1024,       820,       655,       526,       423,
    /*   5 */       335,       272,       215,       172,       137,
    /*  10 */       110,        87,        70,        56,        45,
    /*  15 */        36,        29,        23,        18,        15,
};

// 调度延迟 / 最小粒度
unsigned int sysctl_sched_latency = 6000000;       // 6 ms
unsigned int sysctl_sched_min_granularity = 750000; // 0.75 ms
unsigned int sysctl_sched_wakeup_granularity = 1000000; // 1 ms
```

**关键**：
- `NICE_0_LOAD = 2^32`——nice=0 的 weight 是 1.0
- `sched_latency = 6ms`——所有 runnable task 在 6ms 内至少跑一次
- `sched_min_granularity = 0.75ms`——单个 task 至少跑这么久才让出
- Android 14 上可能改这些值——`/proc/sys/kernel/sched_latency_ns`

---

## 二、sched_entity 数据结构

### 2.1 sched_entity 是什么

`sched_entity` 是 CFS 调度类视角的"调度单位"——每个 task / group 都有一个：

```c
// include/linux/sched.h
struct sched_entity {
    /* For load-balancing: */
    struct load_weight      load;       // task 的权重
    unsigned long           runnable_weight;  // 可运行权重（含 throttled）
    unsigned int            on_rq;      // 是否在 runqueue 上

    u64                     exec_start;   // 上次开始执行时间
    u64                     sum_exec_runtime;  // 累计执行时间
    u64                     vruntime;    // 虚拟时间
    u64                     prev_sum_exec_runtime;  // 上次更新的累计时间

    u64                     nr_migrations;  // 跨 CPU 迁移次数

    struct sched_statistics statistics;  // 调度统计

#ifdef CONFIG_FAIR_GROUP_SCHED
    /* CFS 组的调度信息 */
    int                     depth;      // 组嵌套深度
    struct cfs_rq           *cfs_rq;    // 所属的 cfs_rq
    struct cfs_rq           *my_q;      // 本 entity 的 cfs_rq（如果是组）
    struct sched_entity     *parent;    // 父 entity
    struct rb_node          run_node;   // 红黑树节点
    struct rb_node          *group_node;  // 组红黑树节点
    unsigned int            on_rq_q;    // 是否在组的 rq 上
    // ...
#else
    struct rb_node          run_node;   // 红黑树节点
#endif

    /* PELT 负载算法 */
    struct sched_avg        avg;        // 平均负载
};
```

**关键字段**：
- `load`：`load_weight` 结构——权重（由 nice 决定）
- `vruntime`：虚拟时间——CFS 排序的 key
- `sum_exec_runtime`：累计物理执行时间——用于计算 vruntime 增量
- `run_node`：红黑树节点——按 vruntime 排序
- `avg`：`sched_avg`——PELT 算法的核心

### 2.2 load_weight：权重的实现

```c
// include/linux/sched.h
struct load_weight {
    unsigned long           weight;     // 实际权重
    u32                     inv_weight; // 权重倒数（用于快速除法）
};
```

**关键**：
- `weight` 是 task 在调度器中的"重要性"
- `inv_weight` 是预计算的倒数——CFS 计算 vruntime 时用除法转乘法
- nice -20 → weight = 88761
- nice +19 → weight = 15
- nice 0 → weight = 1024

**重要**：weight 越大 → vruntime 增长越慢 → task 越容易排到前面

### 2.3 sched_entity 的拥有者

sched_entity 不是独立的——它嵌套在 task_struct / cfs_rq 中：

```c
// task_struct 包含 sched_entity
struct task_struct {
    // ...
    struct sched_entity se;    // CFS 调度实体
    struct sched_rt_entity rt; // RT 调度实体
    struct sched_dl_entity dl; // DL 调度实体
    // ...
};

// cfs_rq 也包含 sched_entity
struct cfs_rq {
    // ...
    struct sched_entity se;  // group scheduling 时的"代表" entity
    // ...
};
```

**关键**：
- 每个 task_struct 有 3 个调度实体（CFS / RT / DL）——按当前调度类只用一个
- 组的 cfs_rq 也有 sched_entity——代表整个组参与调度
- "组调度"是 cgroup 控制的底层机制

### 2.4 sched_entity 状态机

```c
// kernel/sched/sched.h
enum {
    CFS_SE_INVALID,           // 未初始化
    CFS_SE_NEW,               // 新创建的 task
    CFS_SE_NORUN,             // 不能跑（如 throttled）
    CFS_SE_RUNNING,           // 正在跑
    CFS_SE_SLEEPING,          // 睡眠中
};
```

**关键**：
- sched_entity 状态在 task 生命周期内变化
- `enqueue_entity` / `dequeue_entity` 改变 on_rq 标志
- `update_curr` 在 tick 时更新 vruntime

---

## 三、cfs_rq 数据结构

### 3.1 cfs_rq 的组成

```c
// kernel/sched/sched.h
struct cfs_rq {
    struct load_weight      load;       // cfs_rq 上所有 task 的总 weight
    unsigned long           runnable_weight;  // 可运行 weight
    unsigned int            nr_running; // runnable task 数
    unsigned int            h_nr_running; // 含组的 runnable task 数

    u64                     exec_clock;    // cfs_rq 累计执行时间
    u64                     min_vruntime;  // cfs_rq 上的最小 vruntime

    // 红黑树
    struct rb_root_cached   tasks_timeline;  // 红黑树根
    struct rb_node          *rb_leftmost;    // 红黑树最左节点（min vruntime）

    struct sched_entity     *curr;       // 当前正在跑 CFS task 的 entity
    struct sched_entity     *next;       // 下一个要跑的 entity
    struct sched_entity     *last;       // 上一个跑的 entity
    struct sched_entity     *skip;       // skip entity（用于组调度）

    // task_group 相关信息
    int                     on_list;     // 是否在 parent rq 的 leaf_cfs_rq_list
    struct cfs_rq           *tg_runnable;  // task_group runnable list
    struct cfs_rq           *tg_throttled; // throttled list

    struct rq               *rq;        // 所属的 CPU rq
    int                     runtime_enabled;  // bandwidth 是否开启
    s64                     runtime_remaining; // 剩余 bandwidth

    // PELT
    struct sched_avg        avg;        // cfs_rq 的平均负载
    u64                     throttled_clock;  // throttled 累计时间
    u64                     throttled_clock_task; // task 视角的 throttled
    u64                     throttled_clock_task_time; // 单个 task 视角

    int                     throttle_count;  // throttle 次数
    struct list_head        throttled_list;  // throttled cfs_rq 列表
};
```

**关键字段**：
- `tasks_timeline`：红黑树根——按 vruntime 排序
- `rb_leftmost`：红黑树最左节点——pick_next_task 直接用它
- `min_vruntime`：cfs_rq 的最小 vruntime——用于新 task 加入
- `curr`：当前正在跑的 CFS task——调度器视角
- `avg`：PELT 平均负载——决定 task 在 CPU 上的"占用率"

### 3.2 红黑树结构

```c
// include/linux/rbtree.h
struct rb_root_cached {
    struct rb_root  rb_root;     // 标准红黑树根
    struct rb_node  *rb_leftmost; // 最左节点（最小 vruntime）
};

struct rb_node {
    unsigned long   __rb_parent_color;  // 父节点 + 颜色（bit）
    struct rb_node  *rb_right;
    struct rb_node  *rb_left;
};
```

**关键**：
- 标准红黑树——自平衡二叉查找树
- `rb_leftmost` 缓存了最小节点——pick_next_task 直接用，O(1)
- 插入 / 删除 O(log n)

### 3.3 任务入队的红黑树操作

```c
// kernel/sched/fair.c enqueue_entity 简化
static void enqueue_entity(struct cfs_rq *cfs_rq, struct sched_entity *se,
                           int flags)
{
    // 1. 更新 curr（当前正在跑的 entity）的 vruntime
    if (cfs_rq->curr)
        update_curr(cfs_rq);

    // 2. 把新 entity 的 vruntime 校准——不能比 min_vruntime 小太多
    if (se->vruntime < cfs_rq->min_vruntime) {
        se->vruntime = cfs_rq->min_vruntime;
    }

    // 3. 把 entity 的 load 加到 cfs_rq 总 load
    account_entity_enqueue(cfs_rq, se);

    // 4. 红黑树插入
    if (se != cfs_rq->curr) {
        __enqueue_entity(cfs_rq, se);  // 红黑树插入——O(log n)
    }

    // 5. 更新 cfs_rq 的统计
    // ...
}

// 红黑树插入的核心
static void __enqueue_entity(struct cfs_rq *cfs_rq, struct sched_entity *se)
{
    struct rb_node **link = &cfs_rq->tasks_timeline.rb_root.rb_node;
    struct rb_node *parent = NULL;
    struct sched_entity *entry;
    bool leftmost = true;

    // 1. 二叉查找插入位置
    while (*link) {
        parent = *link;
        entry = rb_entry(parent, struct sched_entity, run_node);
        if (entity_before(se, entry)) {
            link = &parent->rb_left;
        } else {
            link = &parent->rb_right;
            leftmost = false;
        }
    }

    // 2. 插入并平衡
    rb_link_node(&se->run_node, parent, link);
    rb_insert_color(&se->run_node, &cfs_rq->tasks_timeline.rb_root);

    // 3. 更新 leftmost 缓存
    if (leftmost)
        cfs_rq->tasks_timeline.rb_leftmost = &se->run_node;
}
```

**关键认知**：
- 插入是 O(log n)——二分查找
- leftmost 缓存是关键——pick_next_task 用 O(1) 取最小 vruntime
- 实体 entity_before 比较 vruntime

### 3.4 min_vruntime：cfs_rq 的时间基

```c
// kernel/sched/fair.c update_min_vruntime
static void update_min_vruntime(struct cfs_rq *cfs_rq)
{
    struct sched_entity *curr = cfs_rq->curr;
    struct rb_node *leftmost = cfs_rq->tasks_timeline.rb_leftmost;

    u64 vruntime = cfs_rq->min_vruntime;

    if (curr) {
        if (curr->on_rq)
            vruntime = curr->vruntime;
        else
            curr = NULL;
    }

    if (leftmost) {
        struct sched_entity *se = rb_entry(leftmost, struct sched_entity, run_node);
        if (!curr)
            vruntime = se->vruntime;
        else
            vruntime = min_vruntime(vruntime, se->vruntime);
    }

    cfs_rq->min_vruntime = max_vruntime(cfs_rq->min_vruntime, vruntime);

    // 保证单调递增——不倒退
    smp_wmb();
    cfs_rq->min_vruntime = vruntime;
}
```

**关键**：
- `min_vruntime` 是 cfs_rq 的"当前时间"
- 取 curr.vruntime 和 leftmost.vruntime 的较小值
- 单调递增——保证新 task 的 vruntime 不倒退

### 3.5 任务出队：dequeue_entity

```c
// kernel/sched/fair.c dequeue_entity 简化
static void dequeue_entity(struct cfs_rq *cfs_rq, struct sched_entity *se,
                           int flags)
{
    // 1. 更新 curr
    update_curr(cfs_rq);

    // 2. 红黑树删除
    if (se != cfs_rq->curr)
        __dequeue_entity(cfs_rq, se);  // 红黑树删除——O(log n)

    // 3. 更新 cfs_rq 总 load
    account_entity_dequeue(cfs_rq, se);

    // 4. 如果是 leftmost 节点，重新选 leftmost
    if (rb_is_leftmost(&se->run_node, ...)) {
        cfs_rq->tasks_timeline.rb_leftmost = rb_next(&se->run_node);
    }

    // 5. 更新统计
    update_stats_dequeue(cfs_rq, se, flags);
}
```

**关键**：
- 删除是 O(log n)
- 如果是 leftmost 节点，需要更新 leftmost 缓存
- 这就是为什么睡眠中的 task 从 rq 移除——vruntime 不参与排序

---

## 四、vruntime 计算公式

### 4.1 核心公式

CFS 的核心公式非常简洁：

```
vruntime += delta_exec * NICE_0_LOAD / weight
```

**解释**：
- `delta_exec`：task 自上次更新以来实际运行的时间（ns）
- `NICE_0_LOAD`：nice=0 的 weight = 2^32（用于归一化）
- `weight`：task 自己的 weight（由 nice 决定）

**直觉**：
- nice=0 的 task：`vruntime += delta_exec`——vruntime = 物理时间
- nice=-20（高优先级）的 task：`vruntime += delta_exec / (88761/1024)`——vruntime 增长慢
- nice=+19（低优先级）的 task：`vruntime += delta_exec * (1024/15)`——vruntime 增长快

**关键认知**：
- 同样的物理时间下，nice 越高（数字越大）→ vruntime 涨得越快
- vruntime 越小 → 越靠红黑树左边 → 越先跑
- 所以"nice=-20 的 task 跑得更多"——因为它的 vruntime 涨得慢

### 4.2 真实源码

```c
// kernel/sched/fair.c update_curr
static void update_curr(struct cfs_rq *cfs_rq)
{
    struct sched_entity *curr = cfs_rq->curr;
    u64 now = rq_clock_task(rq_of(cfs_rq));
    u64 delta_exec;

    if (unlikely(!curr))
        return;

    // 1. 计算自上次更新以来的执行时间
    delta_exec = now - curr->exec_start;
    if (unlikely((s64)delta_exec <= 0))
        return;

    // 2. 累计到 sum_exec_runtime
    curr->sum_exec_runtime += delta_exec;
    schedstat_add(cfs_rq->statistics.exec_max, max(delta_exec, curr->statistics.exec_max));

    // 3. **核心公式**：更新 vruntime
    curr->vruntime += calc_delta_fair(delta_exec, curr);
    // calc_delta_fair = delta_exec * NICE_0_LOAD / weight

    // 4. 更新 exec_start
    curr->exec_start = now;

    // 5. 更新 cfs_rq 的 min_vruntime
    if (entity_is_task(curr))
        update_min_vruntime(cfs_rq);

    // 6. 如果 cgroup throttled，更新 cfs_rq 的执行时间
    if (cfs_rq->runtime_enabled && cfs_rq->nr_running)
        account_cfs_rq_runtime(cfs_rq, delta_exec);
}

// 计算 vruntime 增量的核心
static inline u64 calc_delta_fair(u64 delta, struct sched_entity *se)
{
    if (unlikely(se->load.weight != NICE_0_LOAD))
        delta = __calc_delta(delta, NICE_0_LOAD, &se->load);
    // delta = delta * NICE_0_LOAD / se->load.weight

    return delta;
}

static inline u64 __calc_delta(u64 delta_exec, unsigned long weight,
                               struct load_weight *lw)
{
    u64 fact = scale_load_down(weight);
    int shift = WMULT_SHIFT;

    __uint128_t u128 = (__uint128_t)delta_exec * fact;
    // delta_exec * weight / lw->inv_weight
    // 等价于 delta_exec * weight / weight_inv
    // 但 lw->inv_weight 已经是倒数的移位表示

    // 实际实现：乘以 inv_weight
    // ...
}
```

**关键**：
- `__calc_delta` 用 128 位整数计算——避免溢出
- `inv_weight` 是 `weight` 的预计算倒数——节省除法开销
- 乘以 `NICE_0_LOAD` 是归一化——让所有 task 的 vruntime 可以比较

### 4.3 vruntime 的物理含义

```
进程 A：nice=-20, weight=88761
进程 B：nice=0,   weight=1024
进程 C：nice=+19, weight=15

如果三者都跑了 10ms（物理时间）：
  A.vruntime 增加：10ms * 1024 / 88761 ≈ 0.115ms
  B.vruntime 增加：10ms * 1024 / 1024  = 10ms
  C.vruntime 增加：10ms * 1024 / 15    ≈ 683ms

A 的 vruntime 涨 0.115ms——所以它"被亏待"最少
C 的 vruntime 涨 683ms——所以它"被亏待"最多
```

**关键认知**：
- 高优先级 task 的 vruntime 涨得慢——所以它总在红黑树左边
- 低优先级 task 的 vruntime 涨得快——所以它总在红黑树右边
- CFS 通过这种方式实现"优先级"——而不是固定时间片

### 4.4 新 task 加入时 vruntime 怎么定

```c
// kernel/sched/fair.c enqueue_entity 校准 vruntime
static void enqueue_entity(struct cfs_rq *cfs_rq, struct sched_entity *se,
                           int flags)
{
    // ...

    // 校准：不能比 min_vruntime 小太多
    // 否则新 task 会立刻被选——抢占所有老 task
    if (se->vruntime < cfs_rq->min_vruntime) {
        se->vruntime = cfs_rq->min_vruntime;
    }
    // ...
}
```

**关键**：
- 新 task 的 vruntime 默认是 0
- 如果不校准，新 task 立刻抢占所有老 task——CPU 全让给它
- 校准到 `min_vruntime`——新 task 和其他 task "公平起跑"
- **这就是为什么 `sched_child_runs_first=1`——子进程 fork 后抢占父进程**（03 篇讲过）

### 4.5 睡眠 task 唤醒时 vruntime 怎么定

```c
// kernel/sched/fair.c place_entity
static u64 place_entity(struct cfs_rq *cfs_rq, struct sched_entity *se,
                        int initial)
{
    u64 vruntime = cfs_rq->min_vruntime;
    // ...

    if (initial)
        vruntime += sched_latency >> 1;
    // initial 表示新创建 task——给它 50% 调度延迟的"奖励"
    else if (!sched_feat(START_DEBIT))
        vruntime += sched_latency >> 1;

    // 不能超过 cfs_rq 的 max_vruntime
    if (vruntime < cfs_rq->min_vruntime)
        vruntime = cfs_rq->min_vruntime;
    if (vruntime > cfs_rq->max_vruntime)
        vruntime = cfs_rq->max_vruntime;

    return vruntime;
}
```

**关键**：
- 睡眠 task 唤醒时 vruntime 不重置
- 但可能加一些"奖励"——让交互式 task 反应快
- 这是 CFS 实现"交互性"的关键

### 4.6 vruntime 的可视化

```bash
# 看 task 的 vruntime
adb shell "cat /proc/sched_debug" | head -100
```

输出（节选）：

```
cfs_rq[0]:/system
  .exec_clock                      : 0.000000
  .min_vruntime                    : 82453.765432
  .tasks_timeline                  : 5
  .load_avg                        : 12.345
  .runnable_avg                    : 12.345
  .util_avg                        : 1.234

task PID=1234 comm=com.example.app
  .se.exec_start                   : 0.000000
  .se.vruntime                     : 82450.123456
  .se.sum_exec_runtime             : 123.456789
  .se.load.weight                  : 1024
  .se.load.inv_weight              : 4194304
  ...
```

**关键**：
- `se.vruntime` 是当前 task 的虚拟时间
- `cfs_rq.min_vruntime` 是 cfs_rq 上的最小 vruntime
- task 的 vruntime 越小 → 越靠近红黑树左边 → 越先跑

---

## 五、update_curr：tick 时 vruntime 更新

### 5.1 update_curr 何时被调

```c
// kernel/sched/fair.c
// 1. scheduler_tick
static void task_tick_fair(struct rq *rq, struct task_struct *curr, int queued)
{
    struct cfs_rq *cfs_rq;
    struct sched_entity *se = &curr->se;

    for_each_sched_entity(se) {
        cfs_rq = cfs_rq_of(se);
        entity_tick(cfs_rq, se, queued);
    }
}

// 2. enqueue_entity / dequeue_entity / put_prev_entity 等
// 3. set_next_entity
// 4. 其他
```

**关键**：
- 每个 tick（4ms @ HZ=250）都会调一次
- `entity_tick` → `update_curr` → 更新 vruntime
- 这是 vruntime 推进的核心

### 5.2 update_curr 的完整路径

```c
static void update_curr(struct cfs_rq *cfs_rq)
{
    struct sched_entity *curr = cfs_rq->curr;
    u64 now = rq_clock_task(rq_of(cfs_rq));
    u64 delta_exec;

    if (unlikely(!curr))
        return;

    // 1. 计算执行时间
    delta_exec = now - curr->exec_start;
    if (unlikely((s64)delta_exec <= 0))
        return;

    // 2. 累计到 sum_exec_runtime（物理执行时间）
    curr->sum_exec_runtime += delta_exec;

    // 3. 累计 group cfs_rq 的时间
    if (entity_is_task(curr))
        account_group_exec_runtime(cfs_rq, delta_exec);

    // 4. **核心**：更新 vruntime
    curr->vruntime += calc_delta_fair(delta_exec, curr);

    // 5. 更新 cfs_rq 的 min_vruntime
    if (entity_is_task(curr))
        update_min_vruntime(cfs_rq);

    // 6. 更新 exec_start
    curr->exec_start = now;

    // 7. bandwidth 控制（cgroup v2 cpu.max）
    if (cfs_rq->runtime_enabled && cfs_rq->nr_running)
        account_cfs_rq_runtime(cfs_rq, delta_exec);
}
```

**关键**：
- 7 步看起来多，但每步都必要
- 步骤 4 是核心——vruntime 推进
- 步骤 7 是 cgroup bandwidth——cgroup 用满后 throttled

### 5.3 check_preempt_tick：决定是否抢占

```c
// kernel/sched/fair.c entity_tick
static void entity_tick(struct cfs_rq *cfs_rq, struct sched_entity *curr,
                        int queued)
{
    update_curr(cfs_rq);

    // 1. 检查 ideal_runtime 是否用完——决定是否抢占
    if (cfs_rq->nr_running > 1)
        check_preempt_tick(cfs_rq, curr);

    // 2. 唤醒后调度的 task
    if (queued)
        enqueue_sleeper(cfs_rq, curr);
}

static void check_preempt_tick(struct cfs_rq *cfs_rq,
                               struct sched_entity *curr)
{
    unsigned long ideal_runtime, delta_exec;
    struct sched_entity *se;
    s64 delta;

    // 1. 计算 ideal_runtime = sched_latency / nr_running
    ideal_runtime = sched_slice(cfs_rq, curr);

    // 2. 计算 delta_exec（已运行时间）
    delta_exec = curr->sum_exec_runtime - curr->prev_sum_exec_runtime;
    if (delta_exec > ideal_runtime) {
        // 3. 已经跑够理想时间——抢占
        resched_curr(rq_of(cfs_rq));
    }

    // 4. 或者——红黑树左边有更小 vruntime 的 task
    // (在这种情况下也要抢占)
}
```

**关键认知**：
- `ideal_runtime = sched_latency / nr_running`——每个 task 的"理想运行时间"
- 比如 6ms 调度延迟，3 个 runnable → 每个 2ms
- 跑够了就 `resched_curr`——触发调度

### 5.4 ideal_runtime 的计算

```c
// kernel/sched/fair.c sched_slice
static u64 sched_slice(struct cfs_rq *cfs_rq, struct sched_entity *se)
{
    u64 slice = __sched_period(cfs_rq->nr_running + !se->on_rq);

    // 按 weight 分配 slice
    for_each_sched_entity(se) {
        struct load_weight *load;
        struct load_weight lw;

        cfs_rq = cfs_rq_of(se);
        load = &cfs_rq->load;

        if (unlikely(!se->on_rq)) {
            lw = cfs_rq->load;
            update_load_add(&lw, se->load.weight);
            load = &lw;
        }
        slice = __calc_delta(slice, se->load.weight, load);
    }
    return slice;
}
```

**关键**：
- `slice = sched_period / nr_running`（基础分配）
- 再按 weight 调整——高 weight task 拿更多 slice
- 这就是"按权重分配 CPU 时间"

### 5.5 sched_period 的边界

```c
// kernel/sched/fair.c __sched_period
static u64 __sched_period(unsigned long nr_running)
{
    u64 period = sysctl_sched_latency;  // 默认 6ms
    unsigned long nr_latency = period / sysctl_sched_min_granularity;  // 6ms / 0.75ms = 8

    // 如果 runnable task 太多，扩大切片——避免频繁切换
    if (nr_running > nr_latency) {
        period = sysctl_sched_min_granularity * nr_running;
        // 例：100 个 runnable → period = 0.75ms * 100 = 75ms
    }

    return period;
}
```

**关键**：
- runnable 少于 8 个 → period = 6ms
- runnable 多于 8 个 → period = 0.75ms × nr_running
- 这是"调度延迟 vs 切换开销"的折中——runnable 多了就放大周期

### 5.6 update_curr 在 Android 14 上的表现

```bash
# 看调度延迟——可用 /proc/sys/kernel/sched_latency_ns 调
adb shell "cat /proc/sys/kernel/sched_latency_ns"
# 输出: 6000000   ← 6ms

# 看最小粒度
adb shell "cat /proc/sys/kernel/sched_min_granularity_ns"
# 输出: 750000    ← 0.75ms

# 看 wakeup granularity（决定唤醒的 task 能否抢占）
adb shell "cat /proc/sys/kernel/sched_wakeup_granularity_ns"
# 输出: 1000000   ← 1ms
```

**关键**：
- Android 14 上默认 6ms / 0.75ms / 1ms
- 这三个值影响调度延迟——调小让调度更激进、调大让调度更平滑
- 修改要谨慎——影响所有 task 的调度

---

## 六、pick_next_entity：挑 vruntime 最小

### 6.1 完整路径

```c
// kernel/sched/fair.c pick_next_task_fair
static struct task_struct *pick_next_task_fair(struct rq *rq)
{
    struct cfs_rq *cfs_rq = &rq->cfs;
    struct sched_entity *se;
    struct task_struct *p;
    struct sched_entity *curr = cfs_rq->curr;

    // 1. 把当前 task 的 vruntime 更新到 cfs_rq
    if (curr)
        update_curr(cfs_rq);

    // 2. 挑 next entity（关键！）
    se = pick_next_entity(cfs_rq, curr);

    if (!se)
        return NULL;

    // 3. 把 next 设置为 curr
    set_next_entity(cfs_rq, se);

    // 4. 从 entity 反向找到 task_struct
    p = task_of(se);

    return p;
}
```

### 6.2 pick_next_entity 的实现

```c
// kernel/sched/fair.c pick_next_entity
static struct sched_entity *
pick_next_entity(struct cfs_rq *cfs_rq, struct sched_entity *curr)
{
    struct sched_entity *left = __pick_first_entity(cfs_rq);
    struct sched_entity *second;

    // 1. 红黑树为空
    if (left == curr) {
        // 没有别的 task——继续跑 curr
        return curr;
    }

    // 2. leftmost 就是 curr——继续跑 curr
    if (!left || (curr && entity_before(curr, left)))
        left = curr;

    // 3. 找 second（红黑树根的左子树的最右节点）
    second = __pick_next_entity(left);

    // 4. 比较 left 和 curr / second 的 vruntime
    // ...

    return left;
}

// O(1) 取最左节点
static inline struct sched_entity *
__pick_first_entity(struct cfs_rq *cfs_rq)
{
    struct rb_node *left = cfs_rq->tasks_timeline.rb_leftmost;

    if (!left)
        return NULL;

    return rb_entry(left, struct sched_entity, run_node);
}
```

**关键**：
- `rb_leftmost` 让 pick_next_entity 是 O(1)
- `__pick_first_entity` 直接返回红黑树最左节点
- `__pick_next_entity` 找"次小"——用于 wakeup preemption 判断

### 6.3 set_next_entity：标记为 curr

```c
// kernel/sched/fair.c set_next_entity
static void set_next_entity(struct cfs_rq *cfs_rq, struct sched_entity *se)
{
    // 1. 把 entity 从红黑树移除
    if (se->on_rq) {
        __dequeue_entity(cfs_rq, se);  // 红黑树删除
        se->on_rq = 0;
        update_load_sub(&cfs_rq->load, se->load.weight);
    }

    // 2. 设置为 curr
    cfs_rq->curr = se;

    // 3. 更新 vruntime 累计
    se->prev_sum_exec_runtime = se->sum_exec_runtime;

    // 4. ...
}
```

**关键**：
- "正在跑"的 task 从红黑树移除
- 红黑树上的都是"等待跑"的 task
- 切走时再 enqueue

### 6.4 wakeup preemption：唤醒后是否抢占

```c
// kernel/sched/fair.c wakeup_preempt_entity
static bool wakeup_preempt_entity(struct sched_entity *curr,
                                  struct sched_entity *se)
{
    s64 gran, vdiff = curr->vruntime - se->vruntime;

    // 1. 如果 se 的 vruntime 已经小很多——立刻抢占
    if (vdiff > 0)
        return true;

    // 2. vdiff 在 [gran, 0] 之间——不抢占
    gran = wakeup_gran(curr);
    if (vdiff <= -gran)
        return false;

    // 3. 其他情况——按 nice 决定
    return !entity_before(curr, se);
}
```

**关键**：
- 唤醒的 task (se) vruntime < curr.vruntime → 立刻抢占
- 但要减去 `wakeup_gran`（默认 1ms）——避免过分激进
- 这是 CFS 实现"交互性"的核心：被唤醒的 task 比当前 task 的 vruntime 小很多 → 立刻抢占

### 6.5 Android 14 上的 CFS 行为

```bash
# 看 CFS 的实时状态
adb shell "cat /proc/sched_debug | head -50"
```

输出（节选）：

```
runnable tasks:
 S            pid   function                  param        sleep         prio
 1234  0 0.000000 0.000000      120     -20
 5678  0 0.000000 0.000000      120       0
 9012  0 0.000000 0.000000      120       0
```

**关键**：
- `S` = sleep，`R` = running
- `prio` = 优先级（nice + 120）
- 可看到每个 CPU 的 runqueue 上有什么 task

---

## 七、PELT 算法：负载计算

### 7.1 PELT 是什么

**PELT** = **P**er-**E**ntity **L**oad **T**racking。从 Linux 3.8 开始引入。

核心思想：跟踪每个 sched_entity / cfs_rq 的"过去 1024us 的负载衰减平均"。

**关键概念**：
- `load_avg`：任务的"负载"——对应 nice 0 的 weight 1024
- `util_avg`：任务的"利用率"——真实 CPU 占用率
- 衰减周期 1024us（≈1ms）
- 用 32 位定点数表示——避免浮点开销

### 7.2 PELT 公式

```
y_n = y_(n-1) * d + contribution

其中：
  d = decay_factor = 0.978... ≈ 1/1024 每 ms
  contribution = 当前时刻的负载
```

**关键**：
- 每过 1ms，y_n 衰减 1/1024
- contribution 是"当前 task 的 weight × 它在跑的时间"
- 这样算出的 y_n 是"过去一段时间的累计负载"

### 7.3 PELT 的实现

```c
// kernel/sched/pelt.h
// decay_factor = 0.5^(32/period)
// period = 1024us = 1ms
// decay_factor 在 32 位定点表示

#define HALFLIFE_BITS 32
#define HALFLIFE (1UL << HALFLIFE_BITS)
// 1024us = 1ms 半衰期
// decay_factor 在 __accumulate_pelt_segments 中用

// kernel/sched/fair.c __accumulate_pelt_segments
static u32 __accumulate_pelt_segments(u64 periods, u32 d1, u32 d3)
{
    u32 c1, c2, c3 = d3;

    c1 = decay_load(c1, periods);
    c2 = decay_load(c2, periods);

    return c1 + c2 + c3;
}
```

**关键**：
- decay_load 函数是衰减的核心
- PELT 不用浮点——全用 32 位整数
- 这是调度器"嵌入式友好"的关键——不用 FP 单元

### 7.4 load_avg vs util_avg

```c
struct sched_avg {
    u64             last_update_time;     // 上次更新时间
    u64             load_sum;             // load 累计（weight × 时间）
    u32             util_sum;             // util 累计
    u32             period_contrib;       // 部分周期
    unsigned long   load_avg;             // 平均 load
    unsigned long   util_avg;             // 平均 util
    struct util_est util_est;             // util 估计
};
```

**关键**：
- `load_avg`：sched_entity 的"负载"——受 weight 影响
- `util_avg`：sched_entity 的"利用率"——只算 CPU 占用率
- `util_est`：util 估计——用于 UClamp 等决策

### 7.5 load_avg / util_avg 的更新

```c
// kernel/sched/fair.c ___update_load_avg
static inline void
___update_load_avg(struct sched_avg *sa, unsigned long load)
{
    u32 delta_w, scaled_delta_w;
    u64 contrib, delta;

    // 1. 计算时间增量
    delta = sa->period_contrib + period_contrib;
    // ...

    // 2. 计算贡献
    contrib = div_u64(load * delta, 1024);
    // load * delta / 1024 = 当前 task 的 weight × 时间 / 1024

    // 3. 更新 load_sum
    sa->load_sum += contrib;
    // 4. 更新 util_sum
    if (load > util_avg)
        sa->util_sum += contrib;

    // 5. 衰减旧值
    sa->load_sum = decay_load(sa->load_sum, periods - 1);
    sa->util_sum = decay_load(sa->util_sum, periods - 1);

    // 6. 计算新的平均值
    sa->load_avg = div_u64(sa->load_sum, PELT_MIN_DIVIDER);
    sa->util_avg = sa->util_sum / PELT_MIN_DIVIDER;
}
```

**关键认知**：
- `load_sum` 是"累计贡献"——衰减后再除以常数得到平均
- `util_avg` 是 task 实际占 CPU 的百分比（×1024）
- 这就是为什么调 UClamp 时看到 `util_avg`——这是 task 真实占用率

### 7.6 PELT 的用途

PELT 的输出用于：

1. **CPU 选 task**：`util_avg` 高的 task 优先
2. **task 迁移决策**：CPU 上 `util_avg` 总和 vs 其他 CPU——负载均衡
3. **UClamp 决策**：`util_avg` 和 `uclamp_min/max` 比较
4. **DVFS / cpufreq**：`util_avg` 决定 CPU 频率
5. **EAS**：`util_avg` 决定 task 放哪颗 CPU

### 7.7 Android 14 上看 PELT

```bash
# /proc/sched_debug 显示 PELT 数据
adb shell "cat /proc/sched_debug | grep -A 10 'cfs_rq'"
```

输出（节选）：

```
cfs_rq[0]:
  .exec_clock                      : 82450.123456
  .min_vruntime                    : 82450.123456
  .tasks_timeline                  : 5
  .load_avg                        : 1024.5       ← load 平均
  .runnable_avg                    : 1024.5       ← runnable 平均
  .util_avg                        : 512.3        ← 利用率（×1024）
```

**关键**：
- `util_avg = 512.3` 意味着这个 cfs_rq 平均占用 50% CPU
- 在 top-app 上 util_avg 应该接近 1024（满载）
- `load_avg` 用于 EAS 决策

### 7.8 util_est：util 的快速估计

```c
// include/linux/sched.h
struct util_est {
    unsigned int            enqueued;     // 入队时的 util
    unsigned int            ewma;         // 指数移动平均
};
```

**关键**：
- util_est 是 util_avg 的"快速版本"
- 用于 task 唤醒时的 UClamp 决策——不需要等 100ms 的 PELT 收敛
- Android 14 上 wakeup 路径大量使用 util_est

---

## 八、task_group 与组调度

### 8.1 什么是 task_group

```c
// kernel/sched/sched.h
struct task_group {
    struct cgroup_subsys_state css;     // cgroup 子系统状态

    // 权重 / 配额
    unsigned long           shares;     // cpu.shares / cpu.weight
    unsigned long           quota;      // cpu.cfs_quota_us / cpu.max
    unsigned int            period;     // cpu.cfs_period_us / period
    unsigned int            qos_level;  // Android 14 新增：QOS level

    // CFS 调度
    struct sched_entity     **se;       // 每个 CPU 一个 sched_entity
    struct cfs_rq           **cfs_rq;   // 每个 CPU 一个 cfs_rq
    unsigned long           updateload_seq;

    // ...
};
```

**关键**：
- `task_group` 对应 cgroup 树上的一个节点
- 每个 CPU 有独立的 `sched_entity` 和 `cfs_rq`
- `shares` / `quota` 是 cgroup 的 CPU 控制参数

### 8.2 task_group 与 cgroup v1/v2

```bash
# cgroup v1 路径（旧版 Android）
adb shell "ls /dev/cpuctl/"
# cpu.cfs_period_us  cpu.cfs_quota_us  cpu.shares  tasks

# cgroup v2 路径（Android 14）
adb shell "ls /sys/fs/cgroup/"
# cpu.max  cpu.weight  cpu.uclamp.min  cpu.uclamp.max
```

**v1 → v2 映射**：

| v1 | v2 | 含义 |
|---|---|---|
| `cpu.shares` | `cpu.weight` | 权重（按比例分 CPU） |
| `cpu.cfs_quota_us` / `cpu.cfs_period_us` | `cpu.max` | 带宽（quota period） |
| 无 | `cpu.uclamp.min/max` | 利用率约束 |
| 无 | `cpu.idle` | idle CPU 调度 |

### 8.3 组调度的实现

```c
// task_group 在每个 CPU 上有一个 cfs_rq
// cfs_rq 也有 sched_entity（作为"组的代表"参与调度）

// 关键函数：tg_shares_up
// 在 fork / exec / 移动 task 进 cgroup 时调用
// 把 cgroup 的 shares 加权到所属 CPU 的 cfs_rq
```

**关键认知**：
- 组调度：cgroup 的所有 task **共同**参与 CPU 调度
- 一个 cgroup 的总 weight = 所有 task 的 weight 之和
- cgroup 抢占整个 weight 后，内部再按 task weight 分配

### 8.4 Android 14 上的 task_group

```bash
# 看 top-app 的 cgroup 配置
adb shell "ls /sys/fs/cgroup/top-app.slice/"
# cgroup.procs  cpu.max  cpu.weight  cpu.uclamp.min  cpu.uclamp.max

# 看 top-app 当前的进程
adb shell "cat /sys/fs/cgroup/top-app.slice/cgroup.procs | head -10"

# 看 top-app 的 cpu.max 配置
adb shell "cat /sys/fs/cgroup/top-app.slice/cpu.max"
# 输出: max 100000   ← quota=max（不限）, period=100ms

# 看 cpu.weight
adb shell "cat /sys/fs/cgroup/top-app.slice/cpu.weight"
# 输出: 100   ← 默认 100
```

**关键**：
- top-app 的 cpu.max = max 100000 —— Android 14 默认无带宽限制
- cpu.weight = 100——权重
- cpu.uclamp 是动态设置的——影响调度

### 8.5 CPU 带宽限制（throttling）

```c
// kernel/sched/fair.c check_cfs_rq_runtime
static void check_cfs_rq_runtime(struct cfs_rq *cfs_rq)
{
    // 1. 检查 cfs_rq 的 bandwidth 是否用完
    if (cfs_rq->runtime_remaining <= 0) {
        // 2. 用完了——throttle
        throttle_cfs_rq(cfs_rq);
        return;
    }
    // ...
}

// throttle 把 cfs_rq 的 task 从 runqueue 移除
static void throttle_cfs_rq(struct cfs_rq *cfs_rq)
{
    struct rq *rq = rq_of(cfs_rq);
    struct task_group *tg = cfs_rq->tg;
    struct sched_entity *se;
    // ...

    // 遍历所有 task，dequeue
    for_each_sched_entity(se) {
        if (!se->on_rq)
            continue;
        dequeue_entity(cfs_rq, se, DEQUEUE_SLEEP);
        cfs_rq->throttled = 1;
    }

    // 加入 throttled list——quota 重置后唤醒
    list_add_tail(&cfs_rq->throttled_list, &tg->throttled_cfs_rqs);
}
```

**关键认知**：
- 当 cgroup 用完 quota 后，所有 task 被 throttle
- throttle 的 task 从 runqueue 移除——不参与调度
- quota 周期（period）重置后 task 唤醒

### 8.6 Android 14 上的 throttle 排查

```bash
# 1. 看 cgroup 是否 throttle
adb shell "cat /sys/fs/cgroup/<slice>/cpu.stat"
# nr_periods 100  nr_throttled 5  throttled_time 12345

# 2. 看 throttle 次数
adb shell "cat /sys/fs/cgroup/top-app.slice/cpu.stat | grep throttled"
# nr_throttled 5  throttled_time 12345

# 3. 查应用线程数
adb shell "for pid in \$(cat /sys/fs/cgroup/top-app.slice/cgroup.procs); do
    echo \"=== \$pid ===\"
    cat /proc/\$pid/cgroup 2>/dev/null
done"
```

**关键**：
- `nr_throttled > 0` 说明 cgroup 用满了 quota
- `throttled_time` 累计 throttle 时间
- throttle 是 Android 14 性能问题的常见原因

---

## 九、Android 14 实战：CFS 可观测性

### 9.1 /proc/sched_debug

```bash
# 看完整调度器状态
adb shell "cat /proc/sched_debug" | head -100
```

输出结构：

```
Sched Debug Version: v0.18, 5.10.43-android14-8
# Timestamps are in nanoseconds.
now at 8245367890123 nsecs
  .jiffies                  : 1234567
  .sysctl_sched_latency     : 6000000
  .sysctl_sched_min_granularity : 750000
  .sysctl_sched_wakeup_granularity : 1000000
  .sysctl_sched_child_runs_first : 1
  .sysctl_sched_cfs_bandwidth_slice : 5000

cfs_rq[0]:/system
  .exec_clock                      : 0.000000
  .min_vruntime                    : 82453.765432
  .tasks_timeline                  : 5
  .load_avg                        : 12.345
  .runnable_avg                    : 12.345
  .util_avg                        : 1.234

task PID=1234 comm=com.example.app
  .se.exec_start                   : 0.000000
  .se.vruntime                     : 82450.123456
  .se.sum_exec_runtime             : 123.456789
  ...
```

### 9.2 perfetto 看 CFS 行为

```bash
# 抓 CFS 调度事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_switch sched:sched_stat_runtime sched:sched_stat_wait sched:sched_stat_sleep' --time 30"
```

**关键事件**：
- `sched_switch`：上下文切换
- `sched_stat_runtime`：task 在 rq 上的累计运行时间
- `sched_stat_wait`：在 runqueue 上的等待时间
- `sched_stat_sleep`：睡眠时间

### 9.3 nice / weight 的可视化

```bash
# 看每个 task 的 nice / weight
adb shell "cat /proc/<pid>/sched" | head -30
```

输出（节选）：

```
se.load.weight                  : 1024       ← weight
se.load.inv_weight              : 4194304    ← weight 的倒数（移位）
se.runnable_weight              : 1024
se.avg.load_avg                 : 512        ← 过去 1ms 的平均 load
se.avg.util_avg                 : 256        ← 过去 1ms 的平均 util
se.avg.last_update_time         : 8245367890123
se.vruntime                     : 82450.123456
```

**关键**：
- `se.load.weight = 1024` → nice = 0
- `se.avg.util_avg = 256` → task 占用 25% CPU
- 这就是排查"哪个 task 占 CPU 多"的入口

### 9.4 walt / pelt 切换

Android 14 上有 WALT（**W**indow-**A**ssisted **L**oad **T**racking）算法——Google 自研的负载追踪：

```bash
# 看 WALT 状态
adb shell "cat /proc/sys/kernel/sched_walt_init_task_load_pct"
adb shell "cat /proc/sys/kernel/sched_walt_load_avg_period_ms"
```

**关键**：
- WALT 用窗口（如 100ms）算平均负载——比 PELT 反应快
- Android 14 默认用 WALT——用于 EAS 决策
- PELT 是 Linux 内核默认——用于 cgroup / cpufreq

---

## 十、CFS 的稳定性场景

### 10.1 长尾调度延迟

```bash
# 用 perfetto 找长尾
# SQL: 找出 wakeup 到执行的延迟 > 10ms 的事件
SELECT
    sched_wakeup.ts AS wakeup_ts,
    sched_switch.ts AS run_ts,
    sched_switch.ts - sched_wakeup.ts AS delay_ns,
    sched_wakeup.pid,
    sched_wakeup.comm
FROM sched_wakeup
JOIN sched_switch
  ON sched_wakeup.pid = sched_switch.next_pid
WHERE sched_switch.ts > sched_wakeup.ts
  AND (sched_switch.ts - sched_wakeup.ts) > 10000000
ORDER BY delay_ns DESC
LIMIT 20;
```

**关键**：
- 延迟 > 10ms 通常意味着：
  - CPU 满载
  - UClamp 配置错误
  - cgroup quota 用完
  - 实时任务抢占

### 10.2 nice 配置错误

```bash
# 看进程的 nice 值
adb shell "for pid in \$(ls /proc/ | grep -E '^[0-9]+$' | head -20); do
    nice=\$(cat /proc/\$pid/stat 2>/dev/null | awk '{print \$19}')
    comm=\$(cat /proc/\$pid/comm 2>/dev/null)
    echo \"pid=\$pid nice=\$nice comm=\$comm\"
done"
```

**关键**：
- 默认 nice=0（priority=120）
- nice 高的进程（值越大、优先级越低）容易被饿死
- Android 14 上 system_server / zygote 是 nice=-20（最高）

### 10.3 cgroup quota 配置错误

```bash
# 看 cgroup quota
adb shell "find /sys/fs/cgroup -name 'cpu.max' -exec sh -c 'echo === \$1 ===; cat \$1' _ {} \;"
```

**关键**：
- quota 太小 → 应用频繁 throttle
- quota = "max" → 无限制
- Android 14 top-app 默认 max 100000（100ms 内不限）

### 10.4 RT task 饿死 CFS

```c
// RT task 抢占 CFS task——公平性被破坏
// 解决：
// 1. RT task 用尽量短的时间
// 2. 用 SCHED_DEADLINE 替代 RT（带宽保证）
// 3. 在 cgroup 内用 cpuset 限制 RT 的 CPU
```

---

## 十一、给 08 篇留的钩子

读完 07 篇，你应该能：

1. 在脑中画出 CFS 的核心数据结构——sched_entity + cfs_rq + 红黑树。
2. 理解 vruntime 计算公式——`vruntime += delta_exec * NICE_0_LOAD / weight`。
3. 知道红黑树在 CFS 中的角色——按 vruntime 排序，pick_next 是 O(1)。
4. 跟踪 update_curr / pick_next_entity 的完整路径。
5. 理解 sched_latency / sched_min_granularity / sched_wakeup_granularity。
6. 知道 PELT 算法怎么算 load / util。
7. 理解 task_group 与组调度——cgroup 怎么参与 CFS。
8. 能在 Android 14 上用 /proc/sched_debug / perfetto 看 CFS 状态。

07 篇讲完了 CFS——这是 fair 类调度器的全部。但 Android 14 上还有：

**08 篇《调度扩展：RT / Deadline / Idle》会展开**：

> 默认调度类是 CFS，但 Android 14 上 audio / display / SurfaceFlinger 部分路径用 RT。08 篇回答：
>
> - SCHED_FIFO / SCHED_RR 的实现（位图 + 链表）
> - SCHED_DEADLINE 的 CBS（Constant Bandwidth Server）算法
> - SCHED_IDLE 的特殊路径
> - **优先级反转**：RT 持锁 vs CFS 等待 → PI-futex
> - RT throttle——RT task 跑太久会强制让出
> - RT 在 Android 14 上的真实使用（audio HAL / display HAL）
>
> 读完 06 + 07 + 08，调度器 5 个调度类全部讲完——09 篇进入"多核调度"。

---

## 小结

| 维度 | 一句话总结 |
|---|---|
| CFS 核心思想 | 所有 task 的 vruntime 应该尽量同步——红黑树排序 |
| vruntime 公式 | `vruntime += delta_exec * NICE_0_LOAD / weight` |
| 红黑树 | 按 vruntime 排序，最左节点 = next task |
| update_curr | tick 时累计 vruntime + 检查抢占 |
| pick_next_entity | O(1) 取最左节点（vruntime 最小） |
| sched_latency | 默认 6ms——所有 runnable task 在 6ms 内至少跑一次 |
| PELT | 1024us 衰减平均——算 load_avg / util_avg |
| task_group | cgroup 树上的节点——组调度的基础 |
| Android 14 | top-app / background slice 通过 cgroup v2 + UClamp 调度 |

---

## 给下篇的桥

**本篇留下三个钩子**：

1. CFS 处理不了的"实时"场景——08 篇展开 RT / Deadline
2. CFS 处理不了的"绝不跑"——08 篇展开 Idle 类
3. CFS + RT 协作的边界——08 篇展开优先级反转 + PI-futex

如果读完本文仍有疑问：

- **"为什么 CFS 用红黑树而不是链表？"** → §3.2 红黑树 O(log n) 插入 + O(1) 取最小
- **"UClamp 怎么影响 vruntime？"** → UClamp 在 PELT 后处理——影响 util 决策，不影响 vruntime
- **"Android 14 上 nice 默认值？"** → 大多数进程 nice=0；system_server / zygote nice=-20

---

## 引用

| 引用 | 路径 |
|---|---|
| sched_entity | `include/linux/sched.h:struct sched_entity` |
| cfs_rq | `kernel/sched/sched.h:struct cfs_rq` |
| task_group | `kernel/sched/sched.h:struct task_group` |
| update_curr | `kernel/sched/fair.c:update_curr` |
| calc_delta_fair | `kernel/sched/fair.c:calc_delta_fair` |
| enqueue_entity | `kernel/sched/fair.c:enqueue_entity` |
| dequeue_entity | `kernel/sched/fair.c:dequeue_entity` |
| pick_next_entity | `kernel/sched/fair.c:pick_next_entity` |
| check_preempt_tick | `kernel/sched/fair.c:check_preempt_tick` |
| sched_slice | `kernel/sched/fair.c:sched_slice` |
| place_entity | `kernel/sched/fair.c:place_entity` |
| PELT | `kernel/sched/pelt.c:___update_load_avg` |
| throttle_cfs_rq | `kernel/sched/fair.c:throttle_cfs_rq` |
| Android 14 cgroup v2 | `/sys/fs/cgroup/top-app.slice/` |
| /proc/sched_debug | `kernel/sched/debug.c` |