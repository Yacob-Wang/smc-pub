# cgroup v2：内核里的资源控制器

> 系列第 10 篇 · 阶段 D · 控制
>
> **承上**：调度器决定"跑多久"——09 篇讲完。cgroup 决定"能跑多少资源"。本篇展开 cgroup v2 的内核实现 + Android 14 cgroup 树。
>
> **启下**：cgroup 是"被约束"的代表。11 篇《信号机制》展开"协作"——信号是异步通知、IPC 是数据交换。
>
> **预计篇幅**：约 1.9 万字
>
> **源码基线**：Linux 5.10 / 5.15（Android 12-14 主流内核）+ Android 14 GKI。

---

## 学习目标

读完本文，你应该能：

1. 在脑中画出 cgroup 子系统的全景图——cgroup_subsys / cftype / cgroup_file 三层抽象。
2. 理解 cgroup v1 vs v2 的设计差异——为什么 Android 14 转向 v2。
3. 跟踪 `cgroup_attach_task` / `cgroup_exit` 的完整路径——task 怎么进出 cgroup。
4. 知道 memory 子系统怎么记账——page_counter + memory.events。
5. 知道 cpu 子系统怎么带宽控制——bandwidth control（07 篇已涉及，本篇完整展开）。
6. 理解 freezer 子系统的实现——Android 14 上用得少，但重要。
7. 看到 Android 14 的 cgroup 树——top-app / background / system-background。
8. 知道 cgroup 与 OOM 的关联——memory 压力时 cgroup 怎么应对。
9. 能在 Android 14 上用 `cat /sys/fs/cgroup/...` 看 cgroup 状态。
10. 知道 cgroup 配置错误的排查方法——quota 用完、memory 不足、freezer 卡住。

---

## 一、cgroup 是什么

### 1.1 cgroup 的定位

**cgroup** = **C**ontrol **Group**，从 Linux 2.6.24 进入 mainline。

**核心思想**：把 task 分组，对组进行资源控制——CPU、内存、IO、设备访问等。

**类比**：
- 进程是资源的使用者
- cgroup 是资源的"容器"——一组进程共享配额
- 内核通过 cgroup 边界统计和控制资源

**关键认知**：
- cgroup 不是调度器——它**告诉**调度器怎么限制，但自己不调度
- cgroup 是控制器的注册中心——所有资源控制器（cpu / memory / freezer / ...）通过它挂载
- cgroup 是 hierarchy（层级）——可以嵌套，父子继承

### 1.2 cgroup 解决的"老问题"

```
以前没有 cgroup 时：
  - init 启动所有进程
  - 某个进程耗光内存 → 系统 OOM → 所有进程被杀
  - 无法限制单个进程的 CPU 用量

有 cgroup 后：
  - top-app slice 限制 CPU = 100%（但能借用 idle）
  - background slice 限制 CPU = 30%
  - background slice 限制 memory = 500MB
  - 某个进程耗光 → cgroup OOM → 只杀 cgroup 内进程
```

### 1.3 cgroup 在 Android 14 上的使用

```bash
# Android 14 上 cgroup v2 的入口
adb shell "ls /sys/fs/cgroup/"
# cgroup.controllers  cgroup.events  cgroup.freeze  cgroup.procs
# cgroup.max.depth  cgroup.max.descendants  cgroup.stat
# cgroup.threads  cgroup.subtree_control  init.scope  system.slice
# top-app.slice  background.slice  system-background.slice
# cpu.pressure  cpu.stat  cpu.uclamp.max  cpu.uclamp.min
```

**关键**：
- Android 14 强制 cgroup v2（自 Android 11+）
- 应用启动时被 framework 分配到对应 slice
- 每个 slice 限制资源 + 设置 UClamp

### 1.4 cgroup 的关键概念

```
hierarchies（层级）：
  - 树形结构——父子关系
  - 资源限制可继承

subsystems（子系统）：
  - cpu / memory / freezer / cpuset / devices / pids / perf_event
  - 每个子系统独立管理一类资源

tasks（任务）：
  - cgroup 内的进程
  - 一个 task 只能在一个 cgroup 内（v1）
  - v2 也一样
```

**关键认知**：
- hierarchy 是"组织"——父子嵌套
- subsystem 是"控制器"——具体控制什么资源
- task 是"成员"——被分组控制

---

## 二、cgroup v1 vs v2

### 2.1 cgroup v1 的设计

```bash
# cgroup v1 路径（旧版 Android 6-10）
adb shell "ls /dev/cpuctl/ /dev/cpuset/ /dev/memcg/"
# /dev/cpuctl/         ← cpu 子系统
# /dev/cpuset/         ← cpuset 子系统
# /dev/memcg/          ← memory 子系统
```

**v1 的特点**：
- 每个子系统一个 hierarchy——`cpuctl` / `cpuset` / `memcg` 是平行的
- task 可以同时在不同 hierarchy 的 cgroup 内
- 但**同一 subsystem 内** task 只能在一个 cgroup

**问题**：
- 多 hierarchy 难管理——systemd / Android 要操作多个 mount point
- "internal process constraint" 问题——kernel 线程受多个 cgroup 影响
- 接口碎片化——每个子系统有自己的配置文件

### 2.2 cgroup v2 的设计

```bash
# cgroup v2 路径（Android 11+）
adb shell "ls /sys/fs/cgroup/"
# 所有子系统在同一个 hierarchy 下
```

**v2 的特点**：
- **统一 hierarchy**——所有 subsystem 在同一棵树
- 更清晰的内核抽象——cgroup_subsys_state（css）
- 改进的内存统计——`memory.events` / `memory.current`
- 默认开启 cpuset 的 CPU 绑定——跟 v1 行为差异

### 2.3 v1 → v2 的关键差异

| 维度 | v1 | v2 |
|---|---|---|
| 数量 | 多 hierarchy | 单一 unified hierarchy |
| 接口 | 每个 subsystem 一套 | 统一 cgroup 接口 + subsystem 字段 |
| cpuset 默认 | 不绑 CPU | 自动绑 CPU |
| memory.events | 无 | 有（low / high / max / oom） |
| threadgroup | 支持 | 仍支持 |
| 兼容性 | 兼容老应用 | Android 11+ 强制 |

**关键**：
- v2 比 v1 简洁——单一 hierarchy
- v2 接口更友好——`memory.events` 看 OOM 计数等
- Android 14 全面转向 v2

### 2.4 v1 → v2 的兼容性

```bash
# Android 14 上 v1 是否还可用？
adb shell "mount | grep cgroup"
# 通常只能看到 v2 mount——v1 mount 被删

# 但 kernel 可能保留 CONFIG_CGROUP_LEGACY_V1=y
# 在 debug build 还能 mount v1
```

**关键**：
- Android 14 默认**禁用** v1
- CONFIG_CGROUP_LEGACY_V1 编译时决定
- 大多数设备看不到 v1 mount point

### 2.5 cgroup v2 在内核中的引入

```c
// include/linux/cgroup-defs.h
#ifdef CONFIG_CGROUPS
// ...
#endif

#ifdef CONFIG_CGROUP_V2
// v2 路径
// ...
#endif
```

**关键**：
- v1 和 v2 共存——通过 CONFIG 切换
- v2 是默认（CONFIG_CGROUP_V2=y）
- v1 是兼容层（CONFIG_CGROUP_LEGACY_V1=y）

---

## 三、cgroup 内核抽象

### 3.1 cgroup_subsys：子系统注册

```c
// include/linux/cgroup-defs.h
struct cgroup_subsys {
    struct cgroup_subsys_state *(*css_alloc)(struct cgroup_subsys_state *parent_css);
    int (*css_online)(struct cgroup_subsys_state *css);
    void (*css_offline)(struct cgroup_subsys_state *css);
    void (*css_released)(struct cgroup_subsys_state *css);
    void (*css_free)(struct cgroup_subsys_state *css);
    void (*css_reset)(struct cgroup_subsys_state *css);
    void (*css_rstat_flush)(struct cgroup_subsys_state *css, int cpu);

    int (*can_attach)(struct cgroup_taskset *tset);
    void (*cancel_attach)(struct cgroup_taskset *tset);
    void (*attach)(struct cgroup_taskset *tset);
    void (*post_attach)(struct cgroup_taskset *tset);
    void (*detach)(struct cgroup_taskset *tset);

    void (*fork)(struct task_struct *task);
    void (*release)(struct task_struct *task);
    void (*exit)(struct task_struct *task);

    // ...
};

// 注册示例（kernel/cgroup/memory.c）
struct cgroup_subsys memory_cgrp_subsys = {
    .name = "memory",
    .css_alloc = mem_cgroup_css_alloc,
    .css_online = mem_cgroup_css_online,
    .css_offline = mem_cgroup_css_offline,
    .css_released = mem_cgroup_css_released,
    .css_free = mem_cgroup_css_free,
    .can_attach = mem_cgroup_can_attach,
    .cancel_attach = mem_cgroup_cancel_attach,
    .attach = mem_cgroup_attach,
    .post_attach = mem_cgroup_post_attach,
    .fork = mem_cgroup_fork,
    .exit = mem_cgroup_exit,
    .legacy_name = "memcg",
    // ...
};
```

**关键认知**：
- `cgroup_subsys` 是子系统的"接口"——所有资源控制器（memory / cpu / cpuset 等）都实现这个
- 通过 ops 注册——类似 sched_class 的"多态"
- 关键 ops：alloc / online / offline / attach / fork / exit

### 3.2 cgroup_subsys_state（css）：cgroup 内状态

```c
// include/linux/cgroup-defs.h
struct cgroup_subsys_state {
    struct cgroup *cgroup;     // 所属 cgroup
    struct cgroup_subsys *ss;   // 所属 subsystem
    struct percpu_ref refcnt;   // 引用计数
    struct list_head sibling;   // 兄弟 css 链表
    struct list_head children;  // 子 css 链表
    struct cgroup_subsys_state *parent;  // 父 css

    // v2: 私有标志
    unsigned long flags;
    // ...
};

// 每个 subsystem 在 css 上的"私有数据"
// 例如 memory 的 css
struct mem_cgroup {
    struct cgroup_subsys_state css;
    // memory 特有的字段
    struct page_counter memory;       // memory 账本
    struct page_counter memsw;        // memory + swap 账本
    struct work_struct high_work;     // memory.high 处理
    // ...
};

// 通过 container_of 拿到
static inline struct mem_cgroup *mem_cgroup_from_css(struct cgroup_subsys_state *css)
{
    return container_of(css, struct mem_cgroup, css);
}
```

**关键认知**：
- `css` 是 cgroup 在 subsystem 视角的状态——每个 subsystem 都有自己的 css
- 子系统通过 `container_of` 拿自己的私有数据
- `refcnt` 用于无锁访问——cgroup 可能被并发引用

### 3.3 cgroup_file / cftype：cgroup 文件系统抽象

```c
// include/linux/cgroup-defs.h
struct cftype {
    char name[MAX_CFTYPE_NAME];  // 文件名（如 "memory.max"）
    unsigned long private;        // 私有数据
    size_t max_write_len;        // 最大写入长度

    umode_t mode;                // 文件权限
    struct cgroup_subsys_state *(*css)(struct cgroup_file *cfile);

    // 读 / 写 / 读写序列
    int (*read)(struct cgroup_file *cfile, struct cgroup_namespace *ns,
                struct seq_file *sf);
    int (*write)(struct cgroup_file *cfile, struct cgroup_namespace *ns,
                 struct seq_file *sf, loff_t off, char *buf, size_t len);
    // ...

    // seq_file ops
    struct seq_operations *seq_ops;
    // ...
};
```

**关键**：
- `cftype` 描述 cgroup 文件的属性——读 / 写 / 权限
- 每个 cgroup 子系统注册自己的 cftype 数组
- 内核通过 cgroup_file 暴露这些到 /sys/fs/cgroup

### 3.4 完整调用链：用户态写 memory.max

```
用户态：
echo "100000000" > /sys/fs/cgroup/mygroup/memory.max
  ↓
vfs.write
  ↓
cgroup_file_operations.write
  ↓
cftype.write = memory_max_write
  ↓
mem_cgroup_write (kernel/cgroup/memory.c)
  ↓
page_counter_set_max(&memcg->memory, max)
  ↓
memory.max 限制生效
```

**关键认知**：
- 用户态写 cgroup 文件 → 内核 cftype → 子系统具体函数
- 每个子系统都有自己的 cftype 注册
- 这是 cgroup 与用户态的接口契约

### 3.5 cgroup 层级和树

```c
// include/linux/cgroup-defs.h
struct cgroup {
    struct cgroup_subsys_state self;       // 自己的 css
    struct cgroup_subsys_state *subsys[CGROUP_SUBSYS_COUNT]; // 各 subsystem 的 css
    struct cgroup_root *root;               // 所属 root
    struct list_head siblings;              // 兄弟 cgroup
    struct list_head children;              // 子 cgroup
    struct list_head populated_children;    // 有 task 的子 cgroup
    struct kernfs_node *kn;                 // kernfs 节点
    struct cgroup_file *files;              // 文件列表

    int level;                              // 在 hierarchy 中的层级
    // ...
};
```

**关键**：
- `cgroup` 是 hierarchy 中的一个节点
- 每个 cgroup 在每个 subsystem 都有一个 css
- `root` 是 hierarchy 的根——所有 cgroup 链到 root

---

## 四、cgroup 文件系统与 cgroup2 fs

### 4.1 /sys/fs/cgroup 的 mount

```bash
# 看 cgroup v2 的 mount
adb shell "mount | grep cgroup2"
# cgroup2 on /sys/fs/cgroup type cgroup2 (rw,nosuid,nodev,noexec,relatime)

# 看 mount options
adb shell "cat /proc/self/mountinfo | grep cgroup2"
# 1234 567 0:6 / /sys/fs/cgroup rw,nosuid,nodev,noexec,relatime - cgroup2 cgroup2
```

**关键**：
- cgroup v2 只 mount 一次——`cgroup2`
- 跟 v1 不同——v1 有多个 mount
- 所有子系统在同一 mount 下

### 4.2 kernfs：cgroup 文件的底层

```c
// fs/kernfs/kernfs-inode.h
struct kernfs_node {
    atomic_t count;            // 引用计数
    struct kernfs_node *parent;  // 父节点
    struct list_head siblings;
    union {
        struct list_head all_node;     // 全局链表
        struct rb_node rb_node;       // 红黑树节点
    };
    const void *ns;            // 命名空间
    unsigned int hash;         // 名称 hash
    const char *name;          // 名称
    umode_t mode;              // 文件模式
    struct kernfs_iattrs *iattr;
    ino_t id;                  // inode 号

    union {
        // 普通文件
        struct {
            struct rcu_head rcu_head;
            struct cgroup_file *cfile;  // cgroup 文件
            // ...
        };
        // 目录
        struct {
            // ...
        };
    };
};
```

**关键**：
- kernfs 是 cgroup 的"底层文件系统"——类似 sysfs
- `cgroup_file` 是 kernfs 文件 + cftype 的绑定
- 用户态写文件 → kernfs → cftype.write → subsystem 函数

### 4.3 cgroup 文件读写流程

```c
// kernel/cgroup/cgroup.c cgroup_file_operations
static const struct file_operations cgroup_file_operations = {
    .read = cgroup_file_read,
    .write = cgroup_file_write,
    .llseek = cgroup_file_llseek,
    .poll = cgroup_file_poll,
    .release = cgroup_file_release,
};

// cgroup_file_read
static ssize_t cgroup_file_read(struct file *file, char __user *buf,
                                 size_t count, loff_t *ppos)
{
    struct cgroup_file *cfile = file->private_data;
    struct cgroup_subsys_state *css = cfile->css;
    struct cftype *cft = cfile->cft;
    struct seq_file *sf;
    int ret;

    // 1. 分配 seq_file
    ret = single_open_size(buf, count, ppos, 4096);
    // ...

    // 2. 调 cft->seq_start / show / next / stop
    // 3. 最终调 cft->read（如果没注册 seq_ops）
    if (cft->read)
        ret = cft->read(cfile, NULL, sf);
    // ...
}
```

**关键认知**：
- cgroup 文件本质是 kernfs 文件
- 读写由 cftype 的 ops 实现
- 每个 subsystem 注册自己的 cftype + read/write 函数

### 4.4 cgroup 树的可见性

```bash
# 看 cgroup 树
adb shell "find /sys/fs/cgroup -type d | head -20"
# /sys/fs/cgroup
# /sys/fs/cgroup/init.scope
# /sys/fs/cgroup/system.slice
# /sys/fs/cgroup/top-app.slice
# /sys/fs/cgroup/background.slice
# /sys/fs/cgroup/system-background.slice

# 看 cgroup 的 events
adb shell "cat /sys/fs/cgroup/top-app.slice/cgroup.events"
# populated 1
# frozen 0

# 看 cgroup 的 procs
adb shell "cat /sys/fs/cgroup/top-app.slice/cgroup.procs"
# 1234
# 5678
# ...
```

**关键**：
- `cgroup.events`：cgroup 状态——populated（有 task）/ frozen（被 freeze）
- `cgroup.procs`：cgroup 内的进程 PID
- 这是排查 cgroup 问题的入口

---

## 五、memory 子系统：账本与 OOM

### 5.1 memory 子系统的核心数据结构

```c
// mm/memcontrol-v1.h / include/linux/memcontrol.h
struct mem_cgroup {
    struct cgroup_subsys_state css;

    // 1. memory 账本（page_counter）
    struct page_counter memory;
    struct page_counter swap;
    struct page_counter memsw;       // memory + swap

    // 2. 软限制（memory.high）
    struct work_struct high_work;
    unsigned long high;

    // 3. OOM 控制
    struct mem_cgroup_reclaim_iter iter[MAX_NR_ZONES];
    struct bpf_prog *oom_lock;       // BPF 程序锁 OOM

    // 4. 内存统计
    atomic_long_t memory_events[MEMCG_EVENTS_COUNT];
    // low / high / max / oom / oom_kill

    // 5. 引用计数 / 父级
    struct mem_cgroup *parent;
    // ...
};

// memory_events 枚举
enum memcg_events {
    MEMCG_LOW = 0,
    MEMCG_HIGH,
    MEMCG_MAX,
    MEMCG_OOM,
    MEMCG_OOM_KILL,
    MEMCG_NR_EVENTS,
};
```

**关键字段**：
- `memory`：`page_counter`——memory 账本
- `memory_events`：OOM / high / low 等事件计数
- `parent`：父 mem_cgroup——配额继承

### 5.2 page_counter：账本核心

```c
// mm/page_counter.c
struct page_counter {
    atomic_long_t count;        // 当前用量
    unsigned long max;          // 硬限制（memory.max）
    unsigned long emin;         // effective min
    unsigned long emax;         // effective max
    struct page_counter *parent; // 父账本（cgroup 树）

    unsigned long failcnt;      // 分配失败计数
    // ...
};

// 关键操作：charge / uncharge / try_charge
int page_counter_try_charge(struct page_counter *pc, unsigned long nr_pages,
                            struct page_counter **fail)
{
    // 1. 原子计数 +1
    long new = atomic_long_add_return(nr_pages, &pc->count);

    // 2. 检查是否超过 max
    if (new > pc->max) {
        // 超过 max——失败
        atomic_long_sub(nr_pages, &pc->count);
        *fail = pc;
        return -1;
    }

    return 0;
}
```

**关键**：
- `page_counter` 是 memory 子系统的核心数据结构
- 分配内存时调 `try_charge`——超额失败
- 释放时调 `uncharge`——减回去
- `failcnt` 累计失败次数——可观测

### 5.3 memory.max / memory.high / memory.low

```bash
# 1. memory.max（硬限制）
adb shell "cat /sys/fs/cgroup/top-app.slice/memory.max"
# 输出: max   ← 默认无限制
# 设置: echo 1G > /sys/fs/cgroup/top-app.slice/memory.max

# 2. memory.high（软限制——超过时触发 reclaim）
adb shell "cat /sys/fs/cgroup/top-app.slice/memory.high"
# 输出: max   ← 默认

# 3. memory.low（保护——保留不被 reclaim）
adb shell "cat /sys/fs/cgroup/top-app.slice/memory.low"
# 输出: 0     ← 默认不保护
```

**三种限制的区别**：

| 限制 | 类型 | 行为 |
|---|---|---|
| `memory.max` | 硬限制 | 超额 → OOM kill |
| `memory.high` | 软限制 | 超额 → 触发 reclaim，但不强制 |
| `memory.low` | 保护 | 保证不被 reclaim |

**关键**：
- `memory.max` 是"绝对上限"——超过杀
- `memory.high` 是"尽量别超"——超了回收但不杀
- `memory.low` 是"我需要这些"——别人别抢

### 5.4 memory.events 事件计数

```bash
# 看 memory 事件
adb shell "cat /sys/fs/cgroup/top-app.slice/memory.events"
# low 0
# high 1234          ← 累计 high 触发 1234 次
# max 0              ← 没有触发 OOM
# oom 0
# oom_kill 0
# oom_group_kill 0
```

**关键**：
- `high`：累计触发 memory.high reclaim 的次数
- `max`：累计触发 memory.max OOM 的次数
- `oom_kill`：累计杀进程的次数
- 这是排查 OOM 的核心入口

### 5.5 memory.current：实时用量

```bash
# 看 memory 实时用量
adb shell "cat /sys/fs/cgroup/top-app.slice/memory.current"
# 输出: 524288000   ← 500MB

# 多个 cgroup 嵌套
adb shell "find /sys/fs/cgroup -name 'memory.current' -exec cat {} \;"
```

**关键**：
- `memory.current` 是 cgroup 当前总占用
- 比 RSS 更准确——包含 page cache
- Android 14 上 dumpsys meminfo 跟 memory.current 大致吻合

### 5.6 memory 子系统的 attach / fork

```c
// mm/memcontrol-v1.c mem_cgroup_can_attach
static int mem_cgroup_can_attach(struct cgroup_taskset *tset)
{
    struct cgroup_taskset *src = tset;
    struct cgroup *dst_cgroup = cgroup_taskset_destination(tset);
    struct mem_cgroup *dst_memcg = mem_cgroup_from_css(...);
    struct task_struct *task;

    // 1. 遍历要 attach 的 task
    cgroup_taskset_for_each(task, src) {
        // 2. 检查 task 的 mm 是否能装下 dst cgroup
        // (一般不会失败)
    }
    return 0;
}

// mm/memcontrol-v1.c mem_cgroup_attach
static void mem_cgroup_attach(struct cgroup_taskset *tset)
{
    struct task_struct *task;

    cgroup_taskset_for_each(task, tset) {
        // 1. 把 task 的 mm 转到 dst memcg
        // 2. 设置 memcg_from_mm(mm)
        // 3. 更新 css_set
    }
}
```

**关键**：
- task 移动 cgroup 时 memory 子系统做 migrate
- mm 结构里的 memcg 引用更新
- cgroup 树上下移动影响 memory 账本

### 5.7 OOM 的触发路径

```c
// mm/memcontrol-v1.c mem_cgroup_out_of_memory
static bool mem_cgroup_out_of_memory(struct mem_cgroup *memcg, gfp_t gfp_mask,
                                       int order)
{
    // 1. 检查 OOM 是否允许
    if (!memcg_oom_check_bypass(...))
        return false;

    // 2. 选 victim
    // 通常是 oom_score 最高的进程
    victim = select_victim(memcg);

    // 3. 杀 victim
    // __oom_kill_process -> send_sig(SIGKILL)
    return __oom_kill_process(victim);
}

// page fault 时
static int __handle_mm_fault(struct vm_area_struct *vma, ...)
{
    // 1. 分配物理页
    // 2. try_to_charge——失败时 OOM
    if (charge_failed) {
        mem_cgroup_oom(memcg, ...);
    }
}
```

**关键**：
- cgroup memory OOM 是局部 OOM——只杀 cgroup 内进程
- 跟系统级 OOM 区分——系统 OOM 杀 oom_score 最高的全局进程
- Android 14 上 LMKD 优先用 PSI——但 cgroup OOM 仍然是兜底

### 5.8 Android 14 上的 memory 配置

```bash
# Android 14 典型 memory 配置
# top-app slice:
adb shell "cat /sys/fs/cgroup/top-app.slice/memory.max"
# max  ← 默认无限制（前台应用不被限制）

# background slice:
adb shell "cat /sys/fs/cgroup/background.slice/memory.max"
# 524288000  ← 500MB 限制（防止后台应用占用过多）

# system slice:
adb shell "cat /sys/fs/cgroup/system.slice/memory.max"
# max  ← 系统服务无限制
```

**关键**：
- top-app / system 默认无限——前台不能卡
- background 限制 500MB（vendor 可配）——保护前台
- vendor 可能根据 RAM 大小调整

### 5.9 memory 子系统在 Android 14 上的可观测性

```bash
# 1. 看每个 cgroup 的内存占用
adb shell "for slice in \$(ls /sys/fs/cgroup/); do
    if [ -f /sys/fs/cgroup/\$slice/memory.current ]; then
        current=\$(cat /sys/fs/cgroup/\$slice/memory.current)
        max=\$(cat /sys/fs/cgroup/\$slice/memory.max 2>/dev/null)
        echo \"\$slice: current=\$current max=\$max\"
    fi
done"

# 2. 看 memory events（OOM 计数）
adb shell "for slice in \$(ls /sys/fs/cgroup/); do
    if [ -f /sys/fs/cgroup/\$slice/memory.events ]; then
        echo === \$slice ===
        cat /sys/fs/cgroup/\$slice/memory.events
    fi
done"

# 3. 看 memory pressure
adb shell "cat /sys/fs/cgroup/memory.pressure"
# some avg10=0.00 avg60=0.00 avg300=0.00 total=0
# full avg10=0.00 avg60=0.00 avg300=0.00 total=0
```

**关键**：
- `memory.pressure`：PSI（Pressure Stall Information）——所有 cgroup 共享
- `memory.events`：每个 cgroup 的 OOM 计数
- 两者结合能定位 memory 问题

---

## 六、cpu 子系统：bandwidth control

### 6.1 cpu 子系统的核心数据结构

```c
// kernel/sched/core.c
struct task_group {
    struct cgroup_subsys_state css;

    // 1. shares（cpu.weight / cpu.shares）
    unsigned long shares;

    // 2. quota + period（cpu.max）
    unsigned int quota;
    unsigned int period;
    unsigned int quota_period;
    unsigned int nr_running;        // 这个 task_group 内 runnable 数
    unsigned int nr_sleeping;       // sleep 数

    // 3. 每个 CPU 一个 cfs_rq
    struct cfs_rq **cfs_rq;

    // 4. CPU bandwidth
    int runtime_enabled;            // bandwidth 是否开启
    s64 runtime_remaining;          // 剩余 bandwidth
    u64 throttled_us;
    // ...
};
```

**关键认知**：
- `task_group`（cgroup cpu 视角）就是 CFS 视角的"组调度"（07 篇讲过）
- `quota` / `period` 是 bandwidth 控制
- 每个 CPU 有一个 cfs_rq——组调度使用

### 6.2 cpu.max 的设置

```bash
# cpu.max 格式：<quota> <period>
adb shell "cat /sys/fs/cgroup/top-app.slice/cpu.max"
# max 100000  ← quota=max, period=100ms（无限制）

# 设置：500ms quota，100ms period
echo "50000 100000" > /sys/fs/cgroup/background.slice/cpu.max
# 含义：100ms 内最多跑 50ms = 50% CPU

# top-app slice 不限：
adb shell "echo max 100000 > /sys/fs/cgroup/top-app.slice/cpu.max"
```

**关键**：
- `cpu.max = "max 100000"`：quota=MAX_INT（无限制）
- `cpu.max = "50000 100000"`：quota=50ms / period=100ms = 50% CPU
- 单位是微秒

### 6.3 bandwidth throttle 的实现

```c
// kernel/sched/fair.c check_cfs_rq_runtime
static void check_cfs_rq_runtime(struct cfs_rq *cfs_rq)
{
    // 1. 检查是否开启 bandwidth
    if (!cfs_rq->runtime_enabled)
        return;

    // 2. 检查 budget
    if (cfs_rq->runtime_remaining > 0)
        return;

    // 3. 触发 throttle
    if (cfs_rq->throttled)
        return;
    throttle_cfs_rq(cfs_rq);
}
```

**关键**：
- `runtime_remaining`：当前 period 剩余 budget
- 用完 throttle——task 从 runqueue 移除
- period 重置时 unthrottle

### 6.4 throttle_cfs_rq 实现

```c
// kernel/sched/fair.c throttle_cfs_rq
static void throttle_cfs_rq(struct cfs_rq *cfs_rq)
{
    struct rq *rq = rq_of(cfs_rq);
    struct task_group *tg = cfs_rq->tg;
    struct sched_entity *se;

    // 1. 标记 throttled
    cfs_rq->throttled = 1;
    cfs_rq->throttled_clock = rq_clock(rq);

    // 2. 遍历所有 task，从 runqueue 移除
    for_each_sched_entity(se) {
        if (!se->on_rq)
            continue;
        dequeue_entity(cfs_rq, se, DEQUEUE_SLEEP);
        // mark entity as throttled
        se->on_rq_q = 0;
    }

    // 3. 加入 throttled list——quota 重置时唤醒
    list_add_tail(&cfs_rq->throttled_list, &tg->throttled_cfs_rqs);

    // 4. 触发负载均衡
    idle_balance(rq);
}
```

**关键**：
- throttle 时所有 task 离开 runqueue
- quota 重置（period 重置）时 unthrottle
- 这是 cgroup CPU 控制的"硬限"

### 6.5 CPU bandwidth 控制的可观测性

```bash
# 1. 看 cpu.stat
adb shell "cat /sys/fs/cgroup/background.slice/cpu.stat"
# nr_periods 100
# nr_throttled 5           ← 累计 throttle 次数
# throttled_time 12345     ← 累计 throttle 时间（ns）
# nr_bursts 0
# burst_time 0

# 2. 看 nr_throttled
adb shell "cat /sys/fs/cgroup/background.slice/cpu.stat | grep throttled"
# nr_throttled 5
# throttled_time 12345

# 3. 看 cpu.pressure
adb shell "cat /sys/fs/cgroup/cpu.pressure"
# some avg10=0.00 avg60=0.00 avg300=0.00 total=0
# full avg10=0.00 avg60=0.00 avg300=0.00 total=0
```

**关键**：
- `nr_throttled > 0`：cgroup 用完 quota
- `throttled_time`：累计 throttle 时间
- `cpu.pressure`：PSI——CPU 受压力时间百分比

### 6.6 cpu.weight（权重）

```bash
# 看 cpu.weight
adb shell "cat /sys/fs/cgroup/top-app.slice/cpu.weight"
# 100   ← 默认 100

# 看 background slice 的 cpu.weight
adb shell "cat /sys/fs/cgroup/background.slice/cpu.weight"
# 50    ← 较小权重——在多 slice 竞争中拿少
```

**关键**：
- `cpu.weight` 决定 CFS 类的权重
- 多个 cgroup 竞争 CPU 时按 weight 比例分
- top-app weight 大——优先抢到 CPU

### 6.7 cpu 子系统的 attach

```c
// kernel/sched/core.c cpu_cgroup_attach
static void cpu_cgroup_attach(struct cgroup_taskset *tset)
{
    struct task_struct *task;

    cgroup_taskset_for_each(task, tset) {
        // 1. 更新 task 的 sched_task_group
        // 2. 触发调度
        // 3. 重新计算 shares
        sched_move_task(task);
    }
}
```

**关键**：
- task 移动 cgroup 时 sched_task_group 更新
- task 立即按新 cgroup 的 weight / quota 调度

### 6.8 Android 14 上的 CPU 配置示例

```bash
# Android 14 典型 CPU 配置

# top-app slice：前台应用，无 CPU 限制
cpu.max: max 100000
cpu.weight: 100
cpu.uclamp.min: 0   ← Framework 动态设
cpu.uclamp.max: max

# background slice：后台应用，限制 30% CPU
cpu.max: 30000 100000   ← 30% CPU
cpu.weight: 50
cpu.uclamp.min: 0
cpu.uclamp.max: 80

# system slice：系统服务，无限制
cpu.max: max 100000
cpu.weight: 100

# system-background slice：系统后台任务，限制 5% CPU
cpu.max: 5000 100000
cpu.weight: 20
```

**关键认知**：
- Android 14 通过 cpu.max + cpu.weight + cpu.uclamp 三层控制
- 前台无限、后台严控——这是调度优化的核心
- vendor 可以改这些值——但要保证前台体验

---

## 七、freezer 子系统

### 7.1 freezer 是什么

**freezer 子系统**：把 cgroup 内所有 task 冻结——不让它们跑。

```bash
# 冻结一个 cgroup
adb shell "echo 1 > /sys/fs/cgroup/background.slice/cgroup.freeze"

# 解冻
adb shell "echo 0 > /sys/fs/cgroup/background.slice/cgroup.freeze"

# 看状态
adb shell "cat /sys/fs/cgroup/background.slice/cgroup.events"
# frozen 1   ← 已冻结
```

**关键认知**：
- freezer 让 cgroup 内 task 暂停
- task 仍在 TASK_RUNNING 状态——但被冻结不调度
- 用于"暂时挂起但不杀"的场景

### 7.2 freezer 的内核实现

```c
// kernel/cgroup/freezer.c
struct freezer {
    struct cgroup_subsys_state css;
    unsigned int state;     // FREEZER_NORMAL / FREEZING / FROZEN
    // ...
};

// cgroup_freeze
static int cgroup_freeze(struct cgroup *cgrp)
{
    struct freezer *freezer = cgroup_freezer(cgrp);

    // 1. 设置 state = FREEZING
    freezer->state = CGROUP_FREEZING;

    // 2. 遍历 cgroup 内所有 task
    cgroup_taskset_for_each(task, &tset) {
        // 3. 给 task 发假的 wakeup——让它进 sleep
        //    然后冻结
        //    或者：
        // 4. 直接冻结——内核调度器跳过
    }

    return 0;
}
```

**关键**：
- freezer 不是"停止" task——而是让调度器跳过
- task 仍在内核中、只是不跑
- 解冻后立即恢复

### 7.3 freezer 的应用场景

```
1. Android 进程缓存
   - "Cached apps" 被冻结——保留在内存但不占 CPU
   - 解冻时快速恢复

2. 系统升级
   - 升级前冻结所有应用
   - 升级后解冻

3. 调试
   - 冻结问题进程——看系统是否稳定
```

### 7.4 Android 14 上的 freezer 使用

```bash
# 看 cached apps 状态
adb shell "dumpsys activity processes | grep -i 'cached\|frozen'"

# 看 cgroup 的 frozen 状态
adb shell "cat /sys/fs/cgroup/cgroup.events | grep frozen"
# frozen 0   ← 没冻结

# Android 14 上 freezer 主要用于 Cached processes
```

**关键**：
- Android 14 上 cached apps 通过 trim memory 实现——不直接用 freezer
- 但 freezer 是 cgroup v2 的标配接口——framework 可以用

### 7.5 freezer 的限制

```bash
# 看支持的控制器
adb shell "cat /sys/fs/cgroup/cgroup.controllers"
# cpu memory io cpuset
#  ← 没有 freezer？

# Android 14 可能没启用 freezer
adb shell "cat /proc/cgroups | grep freezer"
# 1  freezer  1  1  0  ← freezer 启用
```

**关键**：
- freezer 不是默认启用——CONFIG 决定
- Android 14 通常启用——但 framework 很少用
- 主要是"快速冻结 cgroup"——可能引起问题（task 卡住）

---

## 八、cpuset 子系统

### 8.1 cpuset 在 cgroup v2 中的位置

09 篇已经讲过 cpuset 的核心机制。本篇补充 cgroup v2 视角：

```bash
# 看 cpuset 控制文件
adb shell "ls /sys/fs/cgroup/top-app.slice/ | grep cpuset"
# cpuset.cpus
# cpuset.cpus.partition
# cpuset.mems
# cpuset.cpu_exclusive
# cpuset.mem_exclusive
# cpuset.sched_load_balance
# cpuset.spread_slab
```

**关键**：
- `cpuset.cpus`：允许的 CPU 集合
- `cpuset.mems`：允许的 memory node（NUMA）
- `cpuset.cpus.partition`：partition 模式（v2 新增）
- `cpuset.cpu_exclusive` 等：v1 兼容字段

### 8.2 cpuset.cpus.partition：v2 的新机制

```bash
# 看 partition 状态
adb shell "cat /sys/fs/cgroup/top-app.slice/cpuset.cpus.partition"
# member   ← member 是普通 partition（可借用 CPU）

# 设成 root（独占）
adb shell "echo root > /sys/fs/cgroup/top-app.slice/cpuset.cpus.partition"
# root partition——只能分配给 top-app
```

**关键**：
- `member`：普通 partition——可借用 idle CPU
- `root`：独占 partition——不允许借用
- `isolated`：完全隔离——不允许其他 cgroup 用

### 8.3 cpuset 的 attach 实现

```c
// kernel/cgroup/cpuset.c cpuset_attach_task
static void cpuset_attach_task(struct cpuset *cs, struct task_struct *task)
{
    // 1. 检查 task 的 cpus_allowed 是否被新 cs 包含
    // 2. 不在则强制修改 cpus_allowed
    guarantee_online_cpus(task, cs);
    guarantee_online_mems(task, cs);

    // 3. 更新 task 的 cpus_allowed
    set_cpus_allowed(task, cs->cpus_allowed);

    // 4. 触发迁移
    if (!cpumask_equal(current->cpus_allowed, cs->cpus_allowed))
        wake_up_process(task);
}
```

**关键**：
- cpuset attach 时强制 task 的 cpus_allowed
- 触发 wake_up——可能迁移到新 CPU
- 09 篇详讲过调度器怎么处理

### 8.4 cpuset 与 EAS 的协作（与 09 篇呼应）

```
top-app.slice:
  cpuset.cpus: 4-7               ← 大核
  cpuset.cpus.partition: root    ← 独占

background.slice:
  cpuset.cpus: 0-3               ← 小核
  cpuset.cpus.partition: member  ← 可借用

EAS 决策：
  top-app task 唤醒 → EAS 在 {4-7} 中选
  background task 唤醒 → EAS 在 {0-3} 中选
  → 不冲突、不浪费
```

**关键认知**：
- cpuset 圈定"可选 CPU"——缩小 EAS 搜索范围
- cpuset.cpus.partition 决定"是否能借用"
- 三者配合实现 Android 14 的"前台大核、后台小核"

---

## 九、其他子系统

### 9.1 blkio（Block I/O）

```bash
# v2 中叫 io
adb shell "ls /sys/fs/cgroup/top-app.slice/ | grep ^io"
# io.max
# io.stat
# io.weight

# io.max：IO 带宽限制
adb shell "cat /sys/fs/cgroup/background.slice/io.max"
# 253:0 rbps=10485760 wbps=10485760 riops=max wiops=max
# 含义: 对 253:0（major:minor）设备，read 10MB/s, write 10MB/s

# io.stat：IO 统计
adb shell "cat /sys/fs/cgroup/background.slice/io.stat"
# 253:0 rbytes=12345 wbytes=67890 rios=123 wios=45
```

**关键**：
- io 子系统 v2 中是统一接口（v1 分 blkio.throttle / blkio.weight）
- Android 14 上 io.max 默认不限
- 主要用于云端 / 服务器场景

### 9.2 pids（限制 task 数）

```bash
# pids 子系统
adb shell "cat /sys/fs/cgroup/top-app.slice/pids.max"
# max   ← 默认无限制

# 设置：限制最多 100 个 task
adb shell "echo 100 > /sys/fs/cgroup/top-app.slice/pids.max"

# 看当前 task 数
adb shell "cat /sys/fs/cgroup/top-app.slice/pids.current"
# 50   ← 当前 50 个 task
```

**关键**：
- Android 14 上 pids 子系统默认不限
- vendor 可能用——比如限制 background app 的线程数
- fork 时检查

### 9.3 devices（设备访问控制）

```bash
# devices 子系统
adb shell "ls /sys/fs/cgroup/top-app.slice/ | grep device"
# devices.allow / devices.deny（v1 风格）
# v2 中一般不直接控制
```

**关键**：
- v1 中用 devices.allow / devices.deny 控制设备访问
- v2 中由 SELinux / 其他 LSM 替代
- Android 14 上几乎不用

### 9.4 perf_event

```bash
# perf_event 子系统
adb shell "ls /sys/fs/cgroup/ | grep perf"
# 通常没启用

# 控制 cgroup 级别的 perf 采样
adb shell "cat /sys/fs/cgroup/perf_event.* 2>/dev/null"
```

**关键**：
- Android 14 上 perf_event 通常不启用
- 服务器 / debug 场景用
- 控制 perf event 采样权限

### 9.5 rdma / misc

```c
// 其他可选子系统
struct cgroup_subsys rdma_cgrp_subsys;   // RDMA
struct cgroup_subsys misc_cgrp_subsys;    // misc（其他资源）
// ...
```

**关键**：
- 这些子系统 CONFIG 决定启用
- Android 14 上通常没启用
- 略过不展开

---

## 十、Android 14 cgroup 树

### 10.1 完整的 cgroup 树

```bash
# 看 cgroup 树的根
adb shell "ls /sys/fs/cgroup/"
# init.scope
# system.slice
# system-background.slice
# top-app.slice
# background.slice
# foreground.slice
# dexopt.slice
# ...
```

**关键**：
- Android 14 的 cgroup 树：
  - `init.scope`——init 进程
  - `system.slice`——系统服务（system_server / zygote）
  - `system-background.slice`——系统后台任务
  - `top-app.slice`——前台应用
  - `background.slice`——后台应用
  - `foreground.slice`——前台服务（与 top-app 不同）
  - `dexopt.slice`——dex2oat 进程

### 10.2 各 slice 的资源限制

```bash
# 1. top-app slice
adb shell "cat /sys/fs/cgroup/top-app.slice/memory.max /sys/fs/cgroup/top-app.slice/cpu.max /sys/fs/cgroup/top-app.slice/cpuset.cpus"
# memory.max: max             ← 无内存限制
# cpu.max: max 100000         ← 无 CPU 限制
# cpuset.cpus: 4-7            ← 大核

# 2. background slice
adb shell "cat /sys/fs/cgroup/background.slice/memory.max /sys/fs/cgroup/background.slice/cpu.max /sys/fs/cgroup/background.slice/cpuset.cpus"
# memory.max: 524288000       ← 500MB
# cpu.max: 30000 100000       ← 30% CPU
# cpuset.cpus: 0-3            ← 小核

# 3. system slice
adb shell "cat /sys/fs/cgroup/system.slice/memory.max /sys/fs/cgroup/system.slice/cpu.max"
# memory.max: max             ← 无限制
# cpu.max: max 100000         ← 无限制

# 4. system-background slice
adb shell "cat /sys/fs/cgroup/system-background.slice/cpu.max"
# 5000 100000                 ← 5% CPU
```

**关键**：
- 前台（top-app / foreground）：无限资源 + 大核
- 后台（background）：500MB / 30% CPU / 小核
- 系统后台：限制更严（5% CPU）
- 这是 Android 14 性能/耗电平衡的核心

### 10.3 foreground vs top-app

```bash
# foreground slice 和 top-app slice 是不同的：
# foreground: 前台服务（Service 组件）但应用可能不可见
# top-app: 应用可见且活跃

# 看 foreground slice 的进程
adb shell "cat /sys/fs/cgroup/foreground.slice/cgroup.procs"
```

**关键**：
- foreground 是中间态——前台服务但应用不在前台
- 通常跟 top-app 接近但稍弱
- vendor 可调整

### 10.4 dexopt slice

```bash
# dexopt slice——dex2oat 进程
adb shell "cat /sys/fs/cgroup/dexopt.slice/cpu.max /sys/fs/cgroup/dexopt.slice/memory.max"
# cpu.max: max 100000          ← AOT 编译需要大量 CPU
# memory.max: 4294967296       ← 4GB（足够 AOT）

# dex2oat 是性能敏感的——安装时的 AOT 编译
```

**关键**：
- dexopt slice 给 dex2oat 足够资源
- 内存限制 4GB——AOT 编译需要
- CPU 不限——优先编译

### 10.5 libprocessgroup：framework 设置 cgroup

```cpp
// system/core/libprocessgroup/processgroup.cpp
// 设置进程的 cgroup
bool SetProcessGroup(int tid, int group_id)
{
    // 1. 解析 cgroup controller
    // 2. 写 cgroup.procs
    return WriteStringToFile(std::to_string(tid), cgroup_path + "/cgroup.procs");
}

// frameworks/base/core/java/com/android/server/am/ProcessList.java
public static int setProcessGroup(ProcessRecord app, int groupId) {
    // 1. 根据 groupId 选 cgroup
    // 2. 调 libprocessgroup
    // 3. 设置 UClamp
}
```

**关键**：
- framework 通过 libprocessgroup 设置 cgroup
- 进程启动时 + 状态变化时（top-app / background）
- 这是 framework 与内核 cgroup 的桥梁

### 10.6 framework 切 cgroup 的时机

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java
// 应用启动：
public static void setProcessGroup(...) {
    if (state == TOP_APP) {
        SetProcessGroup(tid, CPUSET_TOP_APP);
        // + UClamp.min = 50
    } else if (state == BACKGROUND) {
        SetProcessGroup(tid, CPUSET_BACKGROUND);
        // + UClamp.max = 80
    }
}

// 应用状态变化：
// - 进入前台：TOP_APP
// - 退到后台：BACKGROUND
// - 缓存：CACHED
```

**关键**：
- framework 监听 Activity / Service 生命周期
- 触发 cgroup 切换
- 这是 Android 14 性能优化的关键路径

---

## 十一、cgroup 与 OOM 的关联

### 11.1 三个 OOM 层级

```
1. 系统级 OOM（kernel oom_killer）
   → 全局 oom_score 最高 → 杀

2. cgroup OOM（mem_cgroup_out_of_memory）
   → cgroup 内 oom_score 最高 → 杀

3. Android LMKD（用户态）
   → PSI 监控 → 选择性杀
```

**关键认知**：
- 三者并存——不是替代关系
- LMKD 是用户态兜底——优先于 cgroup OOM
- cgroup OOM 优先于系统 OOM——但 Android 上 LMKD 提前干预

### 11.2 cgroup OOM 的实现

```c
// mm/memcontrol-v1.c __mem_cgroup_threshold
static void __mem_cgroup_threshold(struct mem_cgroup *memcg, bool swap)
{
    // 1. 检查是否超过 limit
    // 2. 选 victim
    // 3. 杀 victim
}
```

**关键**：
- cgroup OOM 只杀 cgroup 内进程
- 不会跨 cgroup 杀
- 这是 cgroup 隔离的本质

### 11.3 LMKD 与 cgroup

```cpp
// system/core/lmkd/lmkd.cpp
// LMKD 监听 PSI 和 cgroup memory
// 选择性杀进程

void mp_event_psi(...) {
    // 1. 读 PSI（pressure stall information）
    // 2. 读 cgroup memory.current
    // 3. 选 victim（oom_score_adj 高的）
    // 4. 杀进程
    kill(pid, SIGKILL);
}
```

**关键**：
- LMKD 走 cgroup memory 状态
- 提前杀——避免 cgroup OOM 触发
- Android 14 默认用 LMKD

### 11.4 oom_score_adj 与 cgroup

```bash
# 看进程的 oom_score_adj
adb shell "cat /proc/<pid>/oom_score_adj"
# -1000  ← 永远不杀（init）
# 0      ← 默认
# 900    ← 易杀（缓存进程）

# Android 14 的 oom_score_adj 设置：
# - 前台应用：-800
# - 系统服务：-900
# - 后台应用：500
# - 缓存应用：900
```

**关键认知**：
- `oom_score_adj` 决定 OOM 优先级
- Android 14 上 framework 主动设置
- 跟 cgroup 配合——cgroup 内按 oom_score_adj 选 victim

---

## 十二、稳定性排查

### 12.1 cgroup 配置错误

```bash
# 症状：top-app 卡 / background 占资源

# 排查 1：看 cgroup 配置
adb shell "cat /sys/fs/cgroup/top-app.slice/{memory.max,cpu.max,cpuset.cpus}"

# 排查 2：看 process 实际位置
adb shell "cat /proc/<pid>/cgroup"
# 0::/top-app.slice   ← 在 top-app

# 排查 3：看 cgroup.procs
adb shell "cat /sys/fs/cgroup/top-app.slice/cgroup.procs"
```

**关键**：
- 进程不在预期 cgroup → framework bug
- 进程在 cgroup 但资源限制错 → cgroup 配置错

### 12.2 memory 不足排查

```bash
# 1. 看 memory.current
adb shell "cat /sys/fs/cgroup/background.slice/memory.current"
# 524288000 / 524288000   ← 已满 500MB

# 2. 看 memory.events
adb shell "cat /sys/fs/cgroup/background.slice/memory.events"
# high 1234
# max 5     ← 触发 5 次 OOM

# 3. 看进程 RSS
adb shell "dumpsys meminfo"
```

**关键**：
- `memory.current ≈ memory.max` → memory 满
- `memory.events.max > 0` → 已经 OOM
- 排查：哪个进程占用大？能不能调小？

### 12.3 CPU bandwidth throttle 排查

```bash
# 1. 看 cpu.stat
adb shell "cat /sys/fs/cgroup/background.slice/cpu.stat | grep throttle"
# nr_throttled 50
# throttled_time 12345678

# 2. 看 cpu.max
adb shell "cat /sys/fs/cgroup/background.slice/cpu.max"
# 30000 100000   ← 30% CPU

# 3. 解决：
#   - 调大 cpu.max
#   - 把 process 移到 top-app slice
```

**关键**：
- `nr_throttled > 0` 说明 CPU 配额不够
- 解决：调配额 or 移 slice

### 12.4 cpuset 配错排查

```bash
# 1. 看 cpuset
adb shell "cat /sys/fs/cgroup/top-app.slice/cpuset.cpus"
# 0-7   ← 包含小核——错误

# 2. 看进程实际 CPU
adb shell "taskset -p <pid>"
# pid 1234's current affinity mask: ff   ← 0-7

# 3. 解决：
adb shell "echo 4-7 > /sys/fs/cgroup/top-app.slice/cpuset.cpus"
```

**关键**：
- cpuset 配错 → top-app 在小核跑
- 必须 4-7 才能保证前台体验

### 12.5 freezer 卡住排查

```bash
# 1. 看 frozen 状态
adb shell "cat /sys/fs/cgroup/cgroup.events | grep frozen"
# frozen 1

# 2. 看哪些 cgroup 被冻结
adb shell "for slice in \$(ls /sys/fs/cgroup/); do
    if [ -f /sys/fs/cgroup/\$slice/cgroup.events ]; then
        frozen=\$(cat /sys/fs/cgroup/\$slice/cgroup.events | grep frozen | awk '{print \$2}')
        if [ \"\$frozen\" = \"1\" ]; then
            echo \"\$slice is frozen\"
        fi
    fi
done"

# 3. 解冻
adb shell "echo 0 > /sys/fs/cgroup/<slice>/cgroup.freeze"
```

**关键**：
- freezer 一直 frozen → task 不跑
- 排查：是不是 framework bug

---

## 十三、Android 14 libprocessgroup 详解

### 13.1 libprocessgroup 是什么

```c
// system/core/libprocessgroup/processgroup.cpp
// 提供 cgroup 操作的 C API
// frameworks 层通过它设置 cgroup

bool SetProcessGroup(int tid, int group_id);
bool SetTaskProfiles(int tid, const std::vector<std::string>& profiles);
```

**关键**：
- libprocessgroup 是 cgroup 与 framework 的桥梁
- 设置 ProcessGroup 是 cgroup 切片的入口

### 13.2 processgroup.cpp 的核心逻辑

```cpp
// system/core/libprocessgroup/processgroup.cpp
// 把 cgroup 描述符转成 /sys/fs/cgroup/... 路径

static bool SetProcessGroup(int tid, int group_id) {
    // 1. 找 cgroup mount point
    std::string path;
    if (group_id == CPUSET_TOP_APP) {
        path = "/sys/fs/cgroup/top-app.slice";
    } else if (group_id == CPUSET_BACKGROUND) {
        path = "/sys/fs/cgroup/background.slice";
    }
    // ...

    // 2. 把 tid 写到 cgroup.procs
    std::string procs_file = path + "/cgroup.procs";
    if (!WriteStringToFile(std::to_string(tid), procs_file)) {
        return false;
    }

    return true;
}
```

**关键**：
- libprocessgroup 直接写 cgroup.procs
- 这是 framework 唯一与 cgroup 交互的 API

### 13.3 ProcessList 的 group 定义

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java
public static final int SCHED_GROUP_DEFAULT = 0;
public static final int SCHED_GROUP_BACKGROUND = 1;
public static final int SCHED_GROUP_TOP_APP = 2;
public static final int SCHED_GROUP_TOP_APP_BOUND = 3;

private static final int[] SCHED_GROUP_CPU_SET = {
    CPUSET_SP_DEFAULT,
    CPUSET_SP_BACKGROUND,
    CPUSET_SP_TOP_APP,
    CPUSET_SP_TOP_APP,
};
```

**关键**：
- `SCHED_GROUP_TOP_APP` → `CPUSET_SP_TOP_APP` → top-app.slice
- `SCHED_GROUP_BACKGROUND` → CPUSET_SP_BACKGROUND → background.slice
- framework 内部用 SCHED_GROUP 抽象——映射到具体 cgroup

### 13.4 task profiles

```bash
# Android 14 的 task profile
adb shell "cat /sys/kernel/debug/sched_features | head"

# framework 用 "task profiles" 抽象调度属性
# profiles 包括：cpu.uclamp.min / cpu.uclamp.max / cpu.shares 等

# 切换 profile：
adb shell "cmd activity set-task-profile <pid> <profile-name>"
```

**关键**：
- framework 用 task profile 抽象 cgroup 配置
- 一个 profile = 一组 cgroup + UClamp 配置
- 应用切换状态时切换 profile

### 13.5 实际使用案例

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java
public static boolean setProcessGroup(ProcessRecord app, int groupId) {
    int pid = app.pid;
    int tid = app.renderThreadTid;

    // 1. 设置 process cgroup
    Process.setProcessGroup(pid, groupId);

    // 2. 设置 UClamp
    int uclampMin = 0;
    int uclampMax = 100;
    if (groupId == SCHED_GROUP_TOP_APP) {
        uclampMin = 50;  // top-app 50% CPU 保证
    } else if (groupId == SCHED_GROUP_BACKGROUND) {
        uclampMax = 80;  // background 不超 80%
    }
    Process.setTaskProfiles(tid, new String[]{profile});

    return true;
}
```

**关键**：
- 一次 setProcessGroup 同时设置 cgroup + UClamp
- 这是 Android 14 调度优化的关键路径

---

## 十四、给 11 篇留的钩子

读完 10 篇，你应该能：

1. 在脑中画出 cgroup 子系统的全景图——cgroup_subsys / cftype / css 三层抽象。
2. 理解 cgroup v1 vs v2 的设计差异。
3. 跟踪 cgroup_attach_task 的完整路径。
4. 知道 memory 子系统的 page_counter + memory.events。
5. 知道 cpu 子系统的 bandwidth control + throttle。
6. 理解 freezer 子系统的实现。
7. 看到 Android 14 的 cgroup 树——top-app / background / system。
8. 知道 cgroup 与 OOM 的关联——LMKD 兜底。
9. 能在 Android 14 上用 `/sys/fs/cgroup/...` 看 cgroup 状态。
10. 知道 libprocessgroup 怎么与 framework 协作。

**阶段 D 主题"被约束"展开了一半**——cgroup 是"对内约束"。

下一篇 11《信号机制：从产生到投递》展开"对外协作"——信号是异步通知：

> 一个进程怎么"通知"另一个进程？
> - sys_kill / sys_tkill / sys_rt_sigqueueinfo 产生信号
> - pending 队列
> - dequeue_signal / handle_signal / sys_sigreturn
> - 信号安全（async-signal-safe）
> - **SIGKILL / SIGSTOP 不可捕获不可阻塞的底层原因**——force_sig_info_to_task 绕过 handler

读完 10-12，你将掌握"进程被约束"和"进程间协作"两条主线。

---

## 小结

| 维度 | 一句话总结 |
|---|---|
| cgroup 定位 | 资源控制的内核抽象——按组管理进程 |
| v1 vs v2 | v2 单一 hierarchy、改进接口、Android 14 强制 v2 |
| cgroup_subsys | 子系统接口——memory / cpu / cpuset / freezer 都注册 |
| cftype | cgroup 文件描述——通过 /sys/fs/cgroup/... 暴露 |
| memory 子系统 | page_counter 账本 + memory.events 事件 |
| cpu 子系统 | bandwidth control + cpu.weight + UClamp |
| Android 14 | top-app 无限 / background 严控 / framework 通过 libprocessgroup 设置 |
| 与 OOM 关联 | 三层 OOM：LMKD（用户态）+ cgroup OOM + 系统 OOM |

---

## 给下篇的桥

**本篇留下三个钩子**：

1. signal 是异步通知——11 篇展开
2. cgroup 内的信号会被 deliver 给 cgroup 内 task——11 篇讲清楚
3. SIGKILL 不可捕获——11 篇讲 force_sig_info_to_task 怎么绕过 handler

如果读完本文仍有疑问：

- **"top-app 卡顿？"** → §12 cgroup 配置排查
- **"后台 OOM？"** → §11.1-11.4 三层 OOM 排查
- **"framework 怎么切 cgroup？"** → §13 libprocessgroup + ProcessList

---

## 引用

| 引用 | 路径 |
|---|---|
| cgroup_subsys | `include/linux/cgroup-defs.h:struct cgroup_subsys` |
| cgroup_subsys_state | `include/linux/cgroup-defs.h:struct cgroup_subsys_state` |
| cftype | `include/linux/cgroup-defs.h:struct cftype` |
| cgroup | `include/linux/cgroup-defs.h:struct cgroup` |
| page_counter | `mm/page_counter.c` |
| mem_cgroup | `include/linux/memcontrol.h:struct mem_cgroup` |
| task_group | `kernel/sched/sched.h:struct task_group` |
| cpuset | `kernel/cgroup/cpuset.c` |
| freezer | `kernel/cgroup/freezer.c` |
| Android 14 cgroup | `/sys/fs/cgroup/top-app.slice` |
| libprocessgroup | `system/core/libprocessgroup/processgroup.cpp` |