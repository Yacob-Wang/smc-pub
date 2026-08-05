# 调度扩展：RT / Deadline / Idle

> 系列第 08 篇 · 阶段 C · 调度
>
> **承上**：06-07 篇讲了调度基础 + CFS。Android 14 上 audio / display / SurfaceFlinger 等路径不用 CFS——用 RT（实时）或 Deadline。本篇展开这三个调度类的内核实现。
>
> **启下**：调度器 5 个调度类全部讲完。09 篇《多核调度：SMP 负载均衡 + EAS》展开**多核视角**——单核调度器逻辑不复杂，多核协作才是 Android 14 性能优化的真正战场。
>
> **预计篇幅**：约 1.7 万字
>
> **源码基线**：Linux 5.10 / 5.15（Android 12-14 主流内核）。

---

## 学习目标

读完本文，你应该能：

1. 在脑中画出 RT 调度类的数据结构——位图 + 链表（active 数组）。
2. 理解 SCHED_FIFO 与 SCHED_RR 的区别——FIFO 不切、RR 时间片。
3. 知道 RT 优先级范围——0-99（其中 1-99 给用户态，0 留给内核）。
4. 理解 RT throttle 的实现——防止 RT 饿死 CFS 的兜底机制。
5. 跟踪 SCHED_DEADLINE 的 CBS（Constant Bandwidth Server）算法。
6. 知道 SCHED_IDLE 的特殊路径——只在 idle CPU 跑。
7. 理解**优先级反转**的本质——为什么高优先级 task 反而跑不起来。
8. 理解 PI-futex 的实现——内核态优先级继承如何解决反转。
9. 知道 RT 在 Android 14 上的真实使用场景（audio / display / SurfaceFlinger）。
10. 能在 Android 14 上用 chrt / perfetto 看 RT 调度行为。
11. 知道 RT 配置错误 / 优先级反转 / RT 饿死 CFS 的排查方法。

---

## 一、RT 调度类定位

### 1.1 RT 类什么时候用

**RT = Real-Time 实时**。RT task 比所有 CFS task 优先级高——只要 RT runnable，CFS 必须让出 CPU。

**使用场景**：
- **Audio HAL**：音频采样 / 输出必须在 deadline 内完成
- **Display HAL**：VSYNC 中断处理必须在 16ms 内完成
- **SurfaceFlinger 部分路径**：合成线程
- **Camera HAL**：拍照帧处理
- **Sensor HAL**：sensor 数据采集
- **内核关键路径**：migration / hotplug

**关键认知**：
- RT 不是"快的"——而是"有 deadline 的"
- RT 跑太长会饿死所有 CFS——所以 RT 通常只用于"短小硬实时"
- Android 14 上 RT 调度参数由 HAL 设置，应用层无法直接改

### 1.2 RT 在 Android 14 上的使用

```bash
# 1. 看系统中的 RT 进程
adb shell "for pid in \$(ls /proc/ | grep -E '^[0-9]+$'); do
    policy=\$(cat /proc/\$pid/stat 2>/dev/null | awk '{print \$36}')
    case \$policy in
        1) echo \"\$pid FIFO \$(cat /proc/\$pid/comm 2>/dev/null)\";;
        2) echo \"\$pid RR \$(cat /proc/\$pid/comm 2>/dev/null)\";;
        6) echo \"\$pid DL \$(cat /proc/\$pid/comm 2>/dev/null)\";;
    esac
done 2>/dev/null | head -20"
```

**典型输出**：

```
120 FIFO audio@2.0-servic
130 FIFO display@2.0-servic
140 RR  SurfaceFlinger
250 DL  camera@2.0-impl
```

**关键**：
- audio / display / camera HAL 大多是 FIFO / RR
- SurfaceFlinger 部分路径用 RR
- camera HAL 越来越多用 DL（带宽保证）

### 1.3 RT 在用户态怎么用

```c
// C 代码设置 RT 调度
#include <sched.h>

struct sched_param param;
param.sched_priority = 80;  // 1-99

// 设置为 SCHED_FIFO
if (sched_setscheduler(0, SCHED_FIFO, &param) == -1) {
    perror("sched_setscheduler");
    // 需要 CAP_SYS_NICE 权限
}

// 命令行设置
// chrt -f -p 80 <pid>     ← 设置 FIFO priority 80
// chrt -r -p 80 <pid>     ← 设置 RR priority 80
// chrt -p <pid>           ← 查看
```

```bash
# chrt 命令使用
adb shell "chrt -f -p 80 $(pidof audio@2.0-servic)"
# 输出: pid 120's current scheduling policy: SCHED_FIFO
#        pid 120's current scheduling priority: 80
```

**关键**：
- 普通应用没有 `CAP_SYS_NICE`——不能设 RT
- audio / display / camera HAL 通过 `init.rc` 或 `manifest` 获得权限
- chrt 是排查 RT 调度的关键工具

---

## 二、SCHED_FIFO / SCHED_RR 的实现

### 2.1 RT rq 的数据结构

```c
// kernel/sched/sched.h
struct rt_rq {
    struct rt_prio_array    active;       // RT task 数组——按优先级
    unsigned int            rt_nr_running; // RT task 数
    unsigned int            rr_nr_running;  // RR task 数
    int                     highest_prio;  // 最高优先级
    int                     overloaded;    // 是否过载
    struct plist_head       pushable_tasks; // 可迁移的 RT task
    int                     rt_throttled;  // 是否被 throttle
    u64                     rt_time;       // 累计 RT 执行时间
    u64                     rt_runtime;    // RT 周期 budget
    unsigned long           rt_nr_uninterruptible; // uninterruptible 数
    // ...
};

struct rt_prio_array {
    DECLARE_BITMAP(bitmap, MAX_RT_PRIO+1);  // 100 位的位图
    struct list_head queue[MAX_RT_PRIO];   // 100 个链表头
};
```

**关键认知**：
- RT rq 用 **位图 + 链表**——O(1) 选最高优先级
- `MAX_RT_PRIO = 100`（0-99）
- 优先级数组索引 = `MAX_RT_PRIO - priority`（数值越小、优先级越高）

### 2.2 priority 数值 vs 实际优先级

```c
// kernel/sched/sched.h
#define MAX_USER_RT_PRIO    100
#define MAX_RT_PRIO         MAX_USER_RT_PRIO

// priority 数值：1-99 给用户态
// 优先级索引：MAX_RT_PRIO - priority = 99-0
// 位图索引越小 = 优先级越高
```

**关键**：
- `priority=99` → 索引=0（最高优先级）
- `priority=1` → 索引=98（最低 RT 优先级）
- `priority=0` 保留给内核（idle task 的 RT）
- **数值小的优先级反而高**——这跟 nice 相反

### 2.3 入队：__enqueue_rt_entity

```c
// kernel/sched/rt.c
static void __enqueue_rt_entity(struct sched_rt_entity *rt_se, bool head)
{
    struct rt_rq *rt_rq = rt_rq_of_se(rt_se);
    struct rt_prio_array *array = &rt_rq->active;
    struct list_head *queue = array->queue + rt_se_prio(rt_se);
    struct list_head *dl_tail;

    // 1. 找到相同优先级的链表尾
    dl_tail = rt_se->dl_tail;
    rt_se->dl_tail = NULL;

    // 2. 链表插入
    if (head)
        list_add(&rt_se->run_list, queue);
    else
        list_add_tail(&rt_se->run_list, queue);

    // 3. 设置位图
    __set_bit(rt_se_prio(rt_se), array->bitmap);

    // 4. 更新 rt_rq 统计
    rt_rq->rt_nr_running++;
    if (rt_se_is_rr(rt_se))
        rt_rq->rr_nr_running++;

    // 5. 更新最高优先级
    if (rt_se_prio(rt_se) < rt_rq->highest_prio)
        rt_rq->highest_prio = rt_se_prio(rt_se);
}
```

**关键**：
- 链表插入 + 位图设置——O(1)
- 维护 `highest_prio` 缓存——pick_next 不需要遍历位图
- `dl_tail` 是 deadline 链表——DL 调度用

### 2.4 选下一个：pick_next_task_rt

```c
// kernel/sched/rt.c pick_next_task_rt
static struct task_struct *_pick_next_task_rt(struct rq *rq)
{
    struct task_struct *p;
    struct sched_rt_entity *rt_se;
    struct rt_rq *rt_rq = &rq->rt;

    // 1. 没有 RT task
    if (!rt_rq->rt_nr_running)
        return NULL;

    // 2. 找最高优先级
    if (rt_rq->highest_prio < MAX_RT_PRIO) {
        struct list_head *queue;
        struct rt_prio_array *array = &rt_rq->active;
        // 3. 直接索引到最高优先级的链表
        queue = array->queue + rt_rq->highest_prio;
        rt_se = list_first_entry(queue, struct sched_rt_entity, run_list);
        p = rt_task_of(rt_se);
    }

    return p;
}
```

**关键认知**：
- 选 RT task 是 **O(1)**——直接索引 `highest_prio`
- 比 CFS 的红黑树取最左节点还快
- 这是 RT 调度快的原因

### 2.5 SCHED_FIFO 与 SCHED_RR 的区别

```c
// SCHED_FIFO：跑完才让出（或主动 yield）
// SCHED_RR：跑完时间片就轮到同优先级其他 task
```

**FIFO 行为**：
```c
// FIFO 不会主动让出——除非：
// 1. 主动调 sched_yield
// 2. 阻塞（IO / 信号 / sleep）
// 3. 退出
```

**RR 行为**：
```c
// kernel/sched/rt.c task_tick_rt
static void task_tick_rt(struct rq *rq, struct task_struct *p, int queued)
{
    struct sched_rt_entity *rt_se = &p->rt;

    update_curr_rt(rq);

    // RR task 检查时间片
    if (rt_se_is_rr(rt_se) && --rt_se->time_slice <= 0) {
        rt_se->time_slice = sched_rr_timeslice;  // 重置时间片

        // requeue 到同优先级链表尾
        requeue_task_rt(rq, p, 0);

        // 触发调度
        resched_curr(rq);
    }
}

#define RR_TIMESLICE        (100 * HZ / 1000)  // 100ms（HZ=1000 时）
// 在 HZ=250 上是 25ms
```

**关键**：
- FIFO：跑完主动让出（同优先级 FIFO 不会被抢占）
- RR：100ms 时间片（同优先级 RR 轮流跑）
- Android 14 HAL 通常用 FIFO（任务短）——不抢占同优先级
- SurfaceFlinger 用 RR——防止某个线程独占

### 2.6 yield_task_rt

```c
// SCHED_FIFO 主动 yield
// kernel/sched/rt.c yield_task_rt
static void yield_task_rt(struct rq *rq)
{
    struct task_struct *p = rq->curr;
    struct sched_rt_entity *rt_se = &p->rt;
    struct rt_rq *rt_rq = &rq->rt;

    // 重新放到同优先级链表尾
    requeue_task_rt(rq, p, 0);
    // 让同优先级的其他 task 跑

    resched_curr(rq);
}
```

**关键**：
- FIFO yield：把自己放到链表尾，下一个同优先级 task 跑
- 这是 FIFO 调度里"同优先级轮转"的唯一方式

---

## 三、RT 在调度器中的位置

### 3.1 schedule() 中的优先级判断

```c
// kernel/sched/core.c pick_next_task
static inline struct task_struct *
pick_next_task(struct rq *rq, struct task_struct *prev, struct rq_flags *rf)
{
    // ...

    if (likely(rq->nr_running == rq->cfs.h_nr_running)) {
        // 优化路径：只有 CFS
        p = fair_sched_class.pick_next_task(rq);
        return p;
    }

    // 完整路径：按优先级
again:
    for_each_class(class) {
        p = class->pick_next_task(rq);
        if (p)
            return p;
    }
}
```

**关键**：
- 调度器先看 RT——有 RT 就跑 RT
- 没 RT 看 DL
- 没 DL 才看 CFS
- **这是 Android 14 上 RT 任务能抢占所有 CFS 的根因**

### 3.2 RT 抢占 CFS 的实现

```c
// kernel/sched/rt.c wake_up_new_task → check_preempt_curr_rt
static void check_preempt_curr_rt(struct rq *rq, struct task_struct *p, int flags)
{
    struct task_struct *curr = rq->curr;
    struct sched_rt_entity *se = &p->rt, *pse = &curr->rt;

    // 1. 如果 curr 也是 RT——按优先级比较
    if (rt_task(curr)) {
        if (rt_prio(pse) > rt_prio(se)) {
            // p 的优先级高——抢占
            resched_curr(rq);
        }
    }

    // 2. 如果 curr 是 CFS / IDLE——RT 永远抢占
    if (!test_tsk_need_resched(curr)) {
        resched_curr(rq);
    }
}
```

**关键**：
- RT task 唤醒时自动 resched_curr
- CFS task 正在跑 → 立刻被抢占
- 这就是为什么 audio / display 不会被应用卡

### 3.3 RT 在 Android 14 上的具体配置

```bash
# 看 audio server 的 RT 参数
adb shell "chrt -p $(pidof audio@2.0-servic)"
# 输出: pid 120's current scheduling policy: SCHED_FIFO
#        pid 120's current scheduling priority: 80

# 看 SurfaceFlinger 的 RT 参数
adb shell "chrt -p $(pidof surfaceflinger)"
# 输出: pid 140's current scheduling policy: SCHED_RR
#        pid 140's current scheduling priority: 90
```

**关键**：
- audio 用 FIFO priority 80
- SurfaceFlinger 用 RR priority 90
- 这些数值在 HAL 启动时通过 init.rc 或 HAL manifest 设置

### 3.4 init.rc 中的 RT 配置

```rc
# system/core/rootdir/init.zygote64.rc（Android 14）
service zygote /system/bin/app_process64 -Xzygote ...
    class main
    priority -20
    nice -20
    socket zygote stream 660 root system
    # 注意：priority -20 是 nice 值，不是 RT priority

# audio HAL（HAL manifest）
service vendor.audio-hal /vendor/bin/hw/android.hardware.audio.service
    class hal
    priority -20
    # 某些 HAL 加上：
    # rlimit rtprio 95
```

**关键**：
- `priority -20` 在 init.rc 里是 nice 值——CFS 类
- RT priority 由 HAL 在运行时用 `sched_setscheduler` 设置
- `rlimit rtprio 95` 允许 RT priority 95

---

## 四、RT Throttle：兜底机制

### 4.1 为什么需要 RT throttle

**问题**：如果 RT task 写了一个死循环，所有 CFS 都会被饿死——系统卡死。

**解决**：RT throttle——给 RT 一个时间 budget，用完强制让出。

```c
// kernel/sched/rt.c sysctl_sched_rt_runtime
int sysctl_sched_rt_runtime = 950000;   // 0.95s
int sysctl_sched_rt_period = 1000000;  // 1s

// 默认：每 1s 给 RT 0.95s 时间
// 剩余 0.05s 给 CFS
```

**关键认知**：
- RT 默认只有 95% CPU 时间
- Android 14 可能调成 100%——具体看 vendor 配置
- Throttle 不是禁用 RT——只是强制让出

### 4.2 RT throttle 的实现

```c
// kernel/sched/rt.c start_rt_period
static int start_rt_period(struct rt_rq *rt_rq)
{
    // 1. 检查 budget 是否用完
    if (rt_rq->rt_time >= rt_rq->rt_runtime) {
        // 2. budget 用完——throttle
        rt_rq->rt_throttled = 1;
        // 把 RT task 从 runqueue 移除
        sched_rt_rq_dequeue(rt_rq);
        return 1;  // 返回 1 表示被 throttle
    }
    return 0;
}
```

**关键**：
- 每秒（rt_period）检查一次
- budget 用完就 throttle
- period 重置时 unthrottle

### 4.3 Android 14 上的 RT throttle 配置

```bash
# 看 RT throttle 配置
adb shell "cat /proc/sys/kernel/sched_rt_runtime_us"
# 输出: 950000

adb shell "cat /proc/sys/kernel/sched_rt_period_us"
# 输出: 1000000

# 看 RT throttle 事件
adb shell "cat /proc/sched_debug | grep -A 3 'rt_rq\|rt_time\|throttle'"
```

**关键**：
- 95% 是 Linux 默认——CFS 至少有 5% 时间
- Android 14 上 vendor 可能改——audio HAL 要求高可用
- 改这个值要慎重——改完 RT 可能饿死 CFS

### 4.4 RT throttle 的稳定性影响

**典型场景**：HAL bug 导致 RT task 死循环

```
1. audio HAL 卡在死循环（RT priority 80）
2. 系统每 1s 给 audio 0.95s 时间
3. audio 用完 0.95s——throttle
4. 0.05s 期间 CFS 跑——但 CFS 已经卡很久
5. period 重置——audio 继续跑
6. 系统"抖动"——0.95s 卡 + 0.05s 流畅
```

**排查**：
- `dmesg` 看 RT throttling 日志
- perfetto 看 audio task 的运行时间

---

## 五、SCHED_DEADLINE：CBS 算法

### 5.1 SCHED_DEADLINE 是什么

```c
// 用户态设置 SCHED_DEADLINE
struct sched_attr attr = {
    .sched_policy = SCHED_DEADLINE,
    .sched_runtime = 1 * 1000 * 1000,    // 1ms runtime
    .sched_deadline = 10 * 1000 * 1000,  // 10ms deadline
    .sched_period = 10 * 1000 * 1000,    // 10ms period
};

sched_setattr(0, &attr, 0);
```

**关键参数**：
- `runtime`：每个周期可以运行的最长时间
- `deadline`：每个周期必须完成的时间
- `period`：周期长度

**核心语义**：
```
任务每个 period：
  - 最多跑 runtime 时间
  - 必须在 deadline 前跑完
  - deadline 在 period 结束时
  
满足：runtime ≤ deadline ≤ period
```

**关键认知**：
- DL 比 RT 更"精确"——不是简单优先级，是带宽保证
- DL 任务保证在 deadline 前完成——适合"硬实时"
- Android 14 上 camera HAL 部分路径用 DL

### 5.2 CBS（Constant Bandwidth Server）算法

**核心思想**：
- 每个 DL task 有 bandwidth = `runtime / period`
- 调度器跟踪 task 的实际运行时间
- 实际 runtime 累计到 deadline 时，强制让出

```c
// kernel/sched/deadline.c
struct dl_bandwidth {
    raw_spinlock_t      dl_runtime_lock;
    u64                 dl_runtime;      // 累计 runtime
    u64                 dl_period;       // 周期
    u64                 dl_bw;           // bandwidth（runtime / period）
    u64                 dl_total_bw;     // 总 bandwidth
    // ...
};
```

**关键**：
- CBS 把 task 抽象成"恒定带宽服务"
- 系统能容纳 `100% / bandwidth` 个 DL task
- 例：每个 DL task 占 10% bandwidth → 系统最多 10 个 DL task

### 5.3 dl_rq 数据结构

```c
// kernel/sched/sched.h
struct dl_rq {
    struct rb_root_cached   root;       // 红黑树——按 deadline 排序
    unsigned int            dl_nr_running; // DL task 数

    struct dl_bw            dl_bw;      // 系统 DL bandwidth
    // ...
};

// DL 调度实体
struct sched_dl_entity {
    struct rb_node          rb_node;    // 红黑树节点——按 deadline 排序
    u64                     dl_runtime; // 任务 runtime
    u64                     dl_deadline;// 任务 deadline
    u64                     dl_period;  // 任务 period
    u64                     dl_bw;      // 任务 bandwidth
    u64                     dl_density; // 任务 density = runtime/deadline

    int                     dl_throttled;  // 是否 throttle
    int                     dl_yielded;    // 是否 yield
    u64                     deadline;      // 当前 deadline（绝对时间）
    u64                     runtime;       // 当前周期剩余 runtime
    // ...
};
```

**关键**：
- 红黑树按 deadline 排序——deadline 最早的最先跑
- 比 RT 更"智能"——考虑绝对时间

### 5.4 pick_next_task_dl

```c
// kernel/sched/deadline.c pick_next_task_dl
static struct task_struct *pick_next_task_dl(struct rq *rq)
{
    struct sched_dl_entity *dl_se;
    struct task_struct *p;
    struct dl_rq *dl_rq = &rq->dl;

    // 1. 红黑树最左节点 = deadline 最早
    dl_se = rb_entry(dl_rq->root.rb_leftmost, struct sched_dl_entity, rb_node);
    p = dl_task_of(dl_se);

    return p;
}
```

**关键**：
- 跟 CFS 一样用红黑树最左节点
- 但 CFS 按 vruntime 排序，DL 按 deadline 排序
- 都是 O(1) 取最小

### 5.5 DL throttle 的实现

```c
// kernel/sched/deadline.c dl_check_constrained_dl
static void dl_check_constrained_dl(struct sched_dl_entity *dl_se)
{
    // 1. 检查 task 是否还在 budget 内
    if (dl_se->runtime <= 0) {
        // 2. budget 用完——throttle 到下一个 deadline
        dl_se->dl_throttled = 1;
        dl_se->runtime = dl_se->dl_runtime;  // 重置 runtime
        dl_se->deadline = dl_se->deadline + dl_se->dl_period;  // 下一个 deadline
    }
}
```

**关键**：
- DL throttle 不是"破坏"任务——是推迟到下个 deadline
- DL task 在 budget 用完后**还能继续**——只是推迟到下个周期
- 这跟 RT throttle 完全不同

### 5.6 DL 在 Android 14 上的使用

```bash
# 看 DL 进程
adb shell "for pid in \$(ls /proc/ | grep -E '^[0-9]+$'); do
    policy=\$(cat /proc/\$pid/stat 2>/dev/null | awk '{print \$36}')
    if [ \"\$policy\" = \"6\" ]; then
        echo \"\$pid DL: \$(cat /proc/\$pid/comm 2>/dev/null)\"
    fi
done 2>/dev/null"

# 看 DL 参数
adb shell "chrt -d -p <pid>"
# 输出: pid 250's current scheduling policy: SCHED_DEADLINE
#        pid 250's current runtime/deadline/period: 1000000/10000000/10000000
#        pid 250's current flags: 0
```

**关键**：
- Android 14 camera HAL 部分路径用 DL
- runtime/deadline/period 是关键参数
- 配置错误会导致 deadline miss——camera 卡

### 5.7 DL 与 RT 的取舍

| 维度 | RT | Deadline |
|---|---|---|
| 优先级语义 | 数字小 = 高 | deadline 早 = 高 |
| 带宽控制 | throttle 兜底 | 严格 bandwidth |
| 配置复杂度 | 简单 | 复杂（3 个参数） |
| 适合场景 | 短小硬实时 | 长 deadline 任务 |
| Android 14 使用 | audio / display | camera 部分 |

**关键认知**：
- RT 适合"必须在 μs 级响应"的任务（audio 中断）
- DL 适合"必须在 ms 级 deadline 内"的任务（camera 帧处理）
- Android 14 上 vendor 选择：传统 HAL 用 RT、新型 HAL 用 DL

---

## 六、SCHED_IDLE：只在 idle 时跑

### 6.1 SCHED_IDLE 定位

```c
// SCHED_IDLE 的 task——比 nice=+19 还低
// 只在 CPU idle 时跑——绝对不抢占任何其他任务
```

**关键认知**：
- SCHED_IDLE 是"绝不跑"——只有在 idle CPU 才调度
- 优先级低于所有 CFS / RT / DL
- 适合"无所谓跑不跑"的后台任务

### 6.2 SCHED_IDLE 的实现

```c
// kernel/sched/idle.c pick_next_task_idle
static struct task_struct *pick_next_task_idle(struct rq *rq)
{
    // SCHED_IDLE 没有优先级——只有 idle task 候选
    return NULL;  // idle 类不返回 task——选 idle_sched_class
}
```

**关键**：
- pick_next_task_idle 返回 NULL——调度器会调 idle_sched_class
- idle_sched_class 是真正的 idle task（0 号 task）
- SCHED_IDLE task 被排在 idle 之前——但本质上也是"跑就跑、不跑也没事"

### 6.3 SCHED_IDLE 在 Android 14 上的使用

```bash
# 找 SCHED_IDLE 进程
adb shell "ps -A -o PID,POLICY,NAME | grep -i idle"

# 设置进程为 SCHED_IDLE
adb shell "chrt -i -p 0 <pid>"
# chrt -i: SCHED_IDLE
# priority 0: SCHED_IDLE 不需要 priority
```

**关键**：
- Android 14 上几乎没有 SCHED_IDLE 进程
- init 的某些线程、logcat daemon 可能用
- 用户态可以用 `chrt -i` 设置——但需要权限

### 6.4 idle_sched_class：CPU 真正的空闲

```c
// kernel/sched/idle.c
DEFINE_SCHED_CLASS(idle) = {
    .next = &fair_sched_class,
    .enqueue_task = enqueue_task_idle,
    .pick_next_task = pick_next_task_idle,  // 选 idle task
    .task_tick = task_tick_idle,
    // ...
};

// CPU idle 时跑的 idle task
struct task_struct *idle_task(int cpu) {
    return cpu_rq(cpu)->idle;
}

// 跑 idle 任务
static void cpu_idle_loop(void)
{
    while (1) {
        // 1. 有其他 task 跑——schedule
        if (need_resched()) {
            schedule();
            continue;
        }

        // 2. CPU 空闲——进入低功耗
        cpuidle_idle_call();
        // 内部调用 cpuidle_enter()
        // 让 CPU 进入 C-state（停时钟、降电压）
    }
}
```

**关键认知**：
- idle_sched_class 的 task 是每个 CPU 的 idle task
- CPU 没事干时跑 idle——进 cpuidle 节能
- 有 task 要跑时 idle 立刻让出

---

## 七、优先级反转：经典问题

### 7.1 优先级反转是什么

**经典场景**：

```
三个 task：
  T_high：RT priority 90（最高）
  T_mid：CFS normal
  T_low：CFS normal（持锁 L）

时序：
  1. T_low 拿锁 L
  2. T_high 想拿锁 L——阻塞
  3. T_mid 抢走 CPU（T_low 被抢占，无法释放锁）
  4. T_high 等 T_low，但 T_mid 一直跑——T_high 永远等不到

→ 高优先级任务 T_high 反而被低优先级任务 T_mid 阻塞
→ 这就是优先级反转
```

**图示**：

```
时间线：
T_low  ─────[持锁L]──────────────释放锁→
                 ↑
        T_high 等锁
                 ↑
T_mid ───────────[抢占 T_low]──────→

T_high 的有效优先级被压低——反转
```

### 7.2 真实案例：火星探路者

1997 年火星探路者任务因为优先级反转反复重启——这是 IT 史上最著名的优先级反转案例。

**关键认知**：
- 优先级反转不是"理论问题"——会真的卡死系统
- 内核必须主动解决——PI-futex 就是方案之一

### 7.3 优先级反转的 3 个条件

```
1. 高优先级 task（T_high）阻塞在锁上
2. 低优先级 task（T_low）持有锁
3. 中等优先级 task（T_mid）抢占 T_low
```

**满足 3 个条件** → 优先级反转发生

### 7.4 内核的解决方案：优先级继承

**核心思想**：
- 当 T_high 等 T_low 的锁时，把 T_low 临时提到 T_high 的优先级
- 这样 T_mid 抢不走 T_low 的 CPU——T_low 快速释放锁

**时序**：

```
1. T_low 拿锁 L（正常优先级）
2. T_high 想拿锁 L——阻塞
   → 内核发现 T_high 等 T_low
   → 把 T_low 临时提到 T_high 的优先级（RT 90）
3. T_mid 想跑——优先级低——无法抢占 T_low（现在是 RT 90）
4. T_low 继续跑，释放锁 L
5. T_low 恢复原优先级
6. T_high 拿到锁——立即执行
```

### 7.5 内核 PI 机制的实现位置

```c
// 内核 PI 实现分散在几个地方：
// 1. kernel/locking/rtmutex.c - RT mutex 实现
// 2. kernel/locking/rwsem-rt.c - RT rw semaphore
// 3. include/linux/rtmutex.h - PI 数据结构
// 4. kernel/sched/core.c - 优先级调整
```

**关键**：
- 内核的 mutex 默认不是 RT-aware 的
- 必须用 `rt_mutex_init()` / `rt_mutex_lock()` 才有 PI
- 用户态 mutex 走 futex——PI 在 futex 层做

---

## 八、PI-futex：用户态 PI

### 8.1 futex 是什么

**futex** = **F**ast Use**r**space mu**tex**

```c
// 用户态 futex
#include <linux/futex.h>
#include <sys/syscall.h>

// 等待
syscall(SYS_futex, &lock, FUTEX_WAIT, 0, NULL, NULL, 0);

// 唤醒
syscall(SYS_futex, &lock, FUTEX_WAKE, 1, NULL, NULL, 0);
```

**关键认知**：
- futex 是"快速路径用户态 + 慢速路径内核态"的混合锁
- 无竞争时纯用户态——零 syscall 开销
- 有竞争时走内核——sys_futex

### 8.2 PI-futex 的存在

```c
// 用户态 pthread mutex 默认不用 PI
// 必须显式设置：
pthread_mutexattr_t attr;
pthread_mutexattr_init(&attr);
pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT);
pthread_mutex_init(&mutex, &attr);

// 然后这个 mutex 的 lock/unlock 走 PI-futex
```

**关键**：
- pthread 默认 mutex 是**普通 mutex**——不支持 PI
- Android 14 上 `PTHREAD_PRIO_INHERIT` 可以启用 PI
- 启用后 mutex 变成 PI-aware

### 8.3 PI-futex 的内核实现

```c
// kernel/futex.c
SYSCALL_DEFINE3(futex, uint32_t __user *, uaddr, int, op, uint32_t, val, ...);

// FUTEX_LOCK_PI - 加锁（带 PI）
// FUTEX_UNLOCK_PI - 解锁（恢复 PI）
// FUTEX_WAIT_REQUEUE_PI - 等锁
```

**关键路径**：

```
用户态：pthread_mutex_lock(mutex)
  ↓
  调 futex(FUTEX_LOCK_PI)
  ↓
  [syscall]
  ↓
内核：futex_lock_pi
  ↓
  1. 找到 task 正在持锁的 owner
  2. 把 owner 的 effective priority 提升到 waiter 的优先级
  3. owner 被唤醒——快速释放锁
  4. waiter 拿到锁
  ↓
用户态：pthread_mutex_lock 返回
```

### 8.4 priority inheritance 的内核细节

```c
// kernel/locking/rtmutex.c
int rt_mutex_setprio(struct task_struct *p, struct task_struct *pi_task)
{
    int prio, oldprio;
    struct sched_param param = {
        .sched_priority = MAX_RT_PRIO - 1 - pi_task->prio,
    };

    // 1. 提取 pi_task 的优先级
    prio = rt_mutex_getprio(pi_task);

    // 2. 调整 p 的优先级
    if (task_has_rt_policy(p)) {
        // RT task：直接改 priority
        p->rtpriority = prio;
    } else {
        // CFS task：改 nice（不破坏 CFS）
        p->static_prio = NICE_TO_PRIO(prio);
    }

    // 3. 触发调度
    if (running)
        check_preempt_curr(...);

    return 0;
}
```

**关键**：
- 优先级继承是动态调整——owner 的优先级变化
- CFS task 用 nice 调整（不是 RT priority）——保持 CFS 语义
- RT task 直接改 priority

### 8.5 PI 在 Android 14 上的使用

```c
// Android 14 上哪些场景用 PI：
// 1. ART 内部用 rt_mutex（C++ mutex 包装）
// 2. libbinder 的 mutex
// 3. 一些 native 服务（如 SurfaceFlinger）
// 4. 第三方 native 库（按需）
```

**关键**：
- ART 内部大量用 rt_mutex——因为 ART 是性能敏感的
- 第三方代码通常不用——所以优先级反转仍可能发生
- 排查优先级反转：perfetto 看 task 的优先级变化

---

## 九、Android 14 实战：RT 调度排查

### 9.1 chrt 命令

```bash
# 1. 看进程调度策略
adb shell "chrt -p $(pidof audio@2.0-servic)"
# 输出: pid 120's current scheduling policy: SCHED_FIFO
#        pid 120's current scheduling priority: 80

# 2. 设置 RT（需要权限）
adb shell "chrt -f -p 80 $(pidof test_app)"

# 3. 改 RT 时间片（需要 root）
adb shell "chrt -r -p 50 $(pidof surfaceflinger)"

# 4. 看 SCHED_DEADLINE 参数
adb shell "chrt -d -p 250"

# 5. 看 SCHED_IDLE
adb shell "chrt -i -p $(pidof some_task)"
```

**关键**：
- chrt 是排查 RT 调度的第一工具
- 设置 RT 需要权限——chrt 失败一般就是权限
- 输出明确显示 policy + priority

### 9.2 perfetto 看 RT 调度

```bash
# 抓 RT 调度事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_switch sched:sched_pi_setprio' --time 30"
```

**关键事件**：
- `sched_switch`：调度切换
- `sched_pi_setprio`：PI 优先级调整——看到 PI-futex 在工作

### 9.3 RT throttle 日志

```bash
# dmesg 看 RT throttling
adb shell "dmesg | grep -i 'rt.*throttl\|throttle'"
# 输出: sched: RT throttling activated for CPU 0
```

**关键**：
- RT throttle 是兜底——不是 bug
- 但频繁 throttle 说明 RT 配置有问题
- 排查：看是哪个 RT task 跑太久

### 9.4 优先级反转排查

```bash
# 1. 看 priority inheritance 事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_pi_setprio' --time 30"

# 2. UI 上看：
# - audio task（priority 80）的 priority 临时变成 high priority task 的优先级
# - 这就是 PI 在工作

# 3. 如果没有 PI 事件，但 RT task 卡了——优先级反转
```

**关键**：
- perfetto 看 PI 事件——能直观看到优先级继承
- 没看到 PI 但 RT 卡——可能是第三方代码没用 PI mutex

### 9.5 binder 与 RT

```bash
# binder 调用是 Android 14 上重要的"调度场景"
adb shell "dumpsys binder_calls_stats | head -50"
```

**关键**：
- binder 调用走 CFS（system_server / 普通进程）
- 但 HAL 层可能有 RT 任务
- binder 调用慢往往跟 RT 任务抢占有关

---

## 十、RT / DL / Idle 的稳定性场景

### 10.1 RT 饿死 CFS

```bash
# 症状：应用卡顿、系统响应慢
# 排查：
# 1. 看 RT task 是不是 RT throttle
adb shell "dmesg | grep throttl"

# 2. 看每个 CPU 的 RT 累计时间
adb shell "cat /proc/sched_debug | grep -A 10 'rt_rq\|rt_time'"

# 3. 看 RT 进程在跑什么
adb shell "strace -p $(pidof audio@2.0-servic) 2>&1 | head -20"
```

**关键**：
- RT throttle 是兜底——95% budget 用完会强制让出
- 但前 95% 期间 CFS 完全跑不了
- 排查思路：找到跑 RT 太久的那一个 task

### 10.2 RT 优先级配置错误

```bash
# 症状：HAL 卡顿或响应慢
# 排查：
# 1. 看 HAL 的 RT priority
adb shell "chrt -p $(pidof audio@2.0-servic)"

# 2. priority 应该 < 95（保留给关键路径）
# 3. 普通 HAL 用 70-85
```

**关键**：
- priority 99 是最高——但 HAL 几乎不用
- 普通 HAL 用 70-85 之间
- HAL bug 可能让 priority=99——容易出问题

### 10.3 DL 带宽超限

```bash
# 症状：DL 任务偶尔卡顿
# 排查：
adb shell "chrt -d -p $(pidof camera@2.0-impl)"
# 看 runtime/deadline/period 配置

# DL task 总 bandwidth 不能超过 100%
# 多个 DL task 累计 bandwidth ≤ 100%
adb shell "cat /proc/sched_debug | grep -A 5 'dl_rq\|dl_bw'"
```

**关键**：
- DL 总带宽 = runtime / period 之和
- 多个 DL task 累计带宽不能超 100%
- 否则 schedule 失败（-EBUSY）

### 10.4 优先级反转排查

```bash
# 1. 看是否有 PI 事件
adb shell "perfetto --record -o /data/local/tmp/trace.proto \
    -e 'sched:sched_pi_setprio sched:sched_switch' --time 30"

# 2. 看 task 的 priority 变化
# UI 上：某个 RT task 的 priority 暂时升高 → PI 在工作
# 如果没有变化但任务卡 → 没用 PI mutex

# 3. 看代码是否用了 PTHREAD_PRIO_INHERIT
adb shell "objdump -d <library.so> | grep -i futex_lock_pi"
```

**关键**：
- perfetto 是排查 PI 的核心工具
- 代码层面：找 `PTHREAD_PRIO_INHERIT` 的 mutex
- Android 14 上 framework 层都用 PI mutex——但第三方代码不一定

### 10.5 RT 进程优先级调整

```bash
# 把进程设为 SCHED_IDLE（不需要权限）
adb shell "chrt -i -p 0 <pid>"

# 把进程设为 nice=10（CFS）
adb shell "renice +10 -p <pid>"

# 临时调高 nice（low priority）
adb shell "renice -n 19 -p <pid>"
```

**关键**：
- renice 改 CFS 类 nice——不影响 RT
- chrt -i 改 SCHED_IDLE——适合"不重要"的任务
- 普通应用不能调 RT——需要权限

---

## 十一、Android 14 上调度类的组合使用

### 11.1 system_server 的调度

```bash
# system_server 的线程
adb shell "ls /proc/$(pidof system_server)/task | wc -l"
# 输出: 142

# 这些线程的调度策略
adb shell "for tid in \$(ls /proc/$(pidof system_server)/task); do
    policy=\$(cat /proc/$(pidof system_server)/task/\$tid/stat | awk '{print \$36}')
    nice=\$(cat /proc/$(pidof system_server)/task/\$tid/stat | awk '{print \$19}')
    echo \"\$tid policy=\$policy nice=\$nice\"
done | head -20"
```

**典型 system_server 线程**：
- Main thread：CFS nice=-20（最高 CFS）
- Binder 线程：CFS normal
- RenderThread：可能 RT
- Audio 线程：可能 RT

### 11.2 SurfaceFlinger 的调度

```bash
# SurfaceFlinger 调度
adb shell "chrt -p $(pidof surfaceflinger)"
# 输出: pid 140's current scheduling policy: SCHED_RR
#        pid 140's current scheduling priority: 90
```

**关键**：
- SurfaceFlinger 用 SCHED_RR priority 90
- 调度线程用 SCHED_RR——保证合成不被卡
- 内部 worker 可能用 CFS

### 11.3 audio HAL 的调度

```bash
# audio HAL 调度
adb shell "chrt -p $(pidof audio@2.0-servic)"
# 输出: pid 120's current scheduling policy: SCHED_FIFO
#        pid 120's current scheduling priority: 80
```

**关键**：
- audio 用 SCHED_FIFO priority 80
- 不需要 RR——audio 是连续的
- priority 80 比 SurfaceFlinger 低（90）——音频延迟容忍度高

### 11.4 调度类的协作图

```
优先级（从高到低）：
  stop_task > deadline > rt > fair > idle

Android 14 上：
  stop_task  ── 内核 hotplug / migration
  deadline   ── camera HAL（部分路径）
  rt         ── audio / display / SurfaceFlinger 部分路径
  fair       ── system_server / zygote / app
  idle       ── 几乎不用

各调度类协作：
  RT/DL 抢占 CFS——保证实时性
  CFS 抢占 idle——CPU 空闲时给 idle 让位
  stop_task 抢占所有——内核专用
```

---

## 十二、给 09 篇留的钩子

读完 08 篇，你应该能：

1. 在脑中画出 RT rq 的数据结构——位图 + 链表。
2. 理解 SCHED_FIFO 与 SCHED_RR 的区别。
3. 知道 RT 优先级范围 1-99。
4. 理解 RT throttle 的兜底机制。
5. 跟踪 SCHED_DEADLINE 的 CBS 算法。
6. 知道 SCHED_IDLE 的特殊路径。
7. 理解优先级反转的本质 + PI-futex 的解决。
8. 能在 Android 14 上用 chrt / perfetto 看 RT 调度。

调度器 5 个调度类全部讲完——本系列调度篇的最后一块：**多核调度**。

**09 篇《多核调度：SMP 负载均衡 + EAS》会展开**：

> 单核调度器逻辑不复杂，但 Android 14 是 big.LITTLE 多核架构。多核下：
>
> - per-CPU runqueue 怎么协作？
> - 什么时候把 task 从 CPU 0 迁到 CPU 1？
> - **EAS（Energy Aware Scheduling）**怎么决定 task 放哪颗 CPU？
> - **UClamp + Android 14 top-app** 怎么影响调度？
> - **cpuset** 怎么限制 task 跑在哪些 CPU？
> - **CPU 热插拔 + 调频**跟调度的关系？
> - **CPU 拓扑**（big.LITTLE）怎么影响选 CPU 策略？
>
> 读完 09，调度篇就完整了——然后进入 10 篇的 cgroup v2 内核实现 + 11 篇的信号 + 12 篇的 IPC。

---

## 小结

| 维度 | 一句话总结 |
|---|---|
| RT rq 结构 | 位图 + 链表——O(1) 选最高优先级 |
| SCHED_FIFO | 跑完主动让出——同优先级不切换 |
| SCHED_RR | 100ms 时间片——同优先级轮流跑 |
| RT throttle | 95% 周期 budget 兜底——防止饿死 CFS |
| SCHED_DEADLINE | CBS 算法——保证 deadline 内完成 |
| SCHED_IDLE | 只在 CPU idle 时跑——绝不抢占 |
| 优先级反转 | 高优先级等锁被低优先级反向阻塞 |
| PI-futex | 持锁者优先级临时提升——解决反转 |
| Android 14 RT | audio / display / SurfaceFlinger / camera HAL |
| Android 14 DL | camera HAL 部分路径（带宽保证） |

---

## 给下篇的桥

**本篇留下三个钩子**：

1. 调度器 5 个类已讲完——09 篇进入"多核视角"
2. RT / DL 在 Android 14 上的具体使用——09 篇会回扣 UClamp + EAS
3. 优先级反转在多核下更复杂——09 篇会展开 cross-CPU PI

如果读完本文仍有疑问：

- **"RT task 写死循环会怎样？"** → §10.1 RT throttle 兜底
- **"SCHED_DEADLINE 用的人少？"** → §5.7 跟 RT 的取舍
- **"PI-futex 在 Android 14 上用了多少？"** → §11 各场景的实际配置

---

## 引用

| 引用 | 路径 |
|---|---|
| RT rq | `kernel/sched/sched.h:struct rt_rq` |
| pick_next_task_rt | `kernel/sched/rt.c:pick_next_task_rt` |
| task_tick_rt | `kernel/sched/rt.c:task_tick_rt` |
| RT throttle | `kernel/sched/rt.c:start_rt_period` |
| sched_setattr | `kernel/sched/core.c:sched_setattr` |
| DL rq | `kernel/sched/sched.h:struct dl_rq` |
| CBS | `kernel/sched/deadline.c:dl_check_constrained_dl` |
| idle task | `kernel/sched/idle.c:cpu_idle_loop` |
| PI 实现 | `kernel/locking/rtmutex.c:rt_mutex_setprio` |
| futex PI | `kernel/futex.c:futex_lock_pi` |
| Android 14 RT | `chrt` 命令 |
| Android 14 perfetto | `sched:sched_pi_setprio` tracepoint |