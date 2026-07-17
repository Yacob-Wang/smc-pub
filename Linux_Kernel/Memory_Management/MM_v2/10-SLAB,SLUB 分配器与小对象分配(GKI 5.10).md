# 10-SLAB,SLUB 分配器与小对象分配（GKI 5.10）

> **系列**：面向稳定性的 Android 内存架构深度解析系列（MM_v2）· 第 10 篇
> **源码基线**：AOSP `android-14.0.0_r1`（`refs/heads/android14-release`）
> **内核矩阵**：`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`（本篇涉及 `mm/slub.c` / `include/linux/slub_def.h`；5.10 → 5.15 引入 KASAN 异步模式；6.1/6.6 引入 KFENCE）
> **目标读者**：Android 稳定性框架架构师
> **前置阅读**：[09-页分配器与伙伴系统(GKI 5.10)](09-页分配器与伙伴系统(GKI 5.10).md)
> **下一篇**：[11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10)](11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10).md)
> **横向引用**：本篇是"内核 mm/ 子系统四篇"中的**第 3 篇**——把"小对象（< 4 KB）的高频分配/释放"这条链路打通。前两篇讲[物理组织](08-物理内存组织-Node,Zone,Page,memblock(GKI 5.10).md)与[页分配器](09-页分配器与伙伴系统(GKI 5.10).md)；后一篇讲[内存回收](11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10).md)。

---

## 本篇定位

- **本篇系列角色**：核心机制第 10 篇 — 讲 Linux 内核 SLAB/SLUB 分配器（小对象高频分配的 cache 层）；处理"任意 < 4KB 的小对象"分配，KASAN/KFENCE 调试的基础
- **强依赖**：
  - MM_v2 09 已讲伙伴系统（本篇的 SLUB 在 `new_slab` 时通过伙伴系统分配 slab）
  - 后续 11 回收会引用 SLUB 的 `kmem_cache_reap` 路径
- **承接自**：09 §5 watermark slowpath（慢路径释放 page 后,SLUB 路径触发回收）
- **衔接去**：
  - 11 讲回收（`shrink_slab` 触发 SLUB 释放）
  - 12 风险地图（SLAB 泄漏占 5 大风险中的 1 类）
- **不重复内容**：
  - 09 已讲的伙伴系统,本篇只引用 `alloc_pages` 入口
  - 11 回收详见相关篇

#### §0 锚点案例的可验证 4 件套:binder 驱动 SLAB 泄漏导致 kmalloc 失败

> **环境**:
> - 设备:Pixel 7（GS201,arm64-v8a,8GB RAM）
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.10` GKI
> - 场景:大量 Binder 事务（典型如视频通话/直播）
> - 工具:`/proc/slabinfo` + `dmesg` + `echo FZPU > /sys/kernel/slab/kmalloc-256/slub_debug` + `cat alloc_calls`

> **复现步骤**:
> 1. 工厂重置,安装"某 IM + 视频通话"App
> 2. 启动 4K 视频通话 30min
> 3. 偶发 Binder 失败,logcat 出现 `transaction failed 29189/-3`
> 4. `dmesg` 出现 `SLUB: Unable to allocate memory`

> **logcat / dmesg 关键片段**:
> ```
> # dmesg
> binder: 1234:1234 transaction failed 29189/-3
> SLUB: Unable to allocate memory on node -1, gfp=0x6000c0(GFP_KERNEL)
> __alloc_pages_slowpath: 5ms+
> ```
> ```
> # /proc/slabinfo
> kmalloc-256       active_objs=134000  num_objs=140000  high=140000
>                    → 持续增长到 2 GB 才被 LMKD 发现(根因)
> ```
> ```
> # 启用 SLUB 调试后,看 alloc_calls
> $ echo FZPU > /sys/kernel/slab/kmalloc-256/slub_debug
> $ cat /sys/kernel/slab/kmalloc-256/alloc_calls
> 134000     kmalloc-256 alloc:    binder_alloc_buf+0x88/0x128
>                                binder_thread_write+0x1c0/0x4f0
>                                binder_ioctl+0x88/0x130
> # 单一调用方:binder 驱动
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/drivers/android/binder.c
> +++ b/drivers/android/binder.c
> @@ -binder_alloc_buf 异常分支
>  if (copy_from_user(t->buffer, ptr, sizeof(*ptr))) {
>      ret = -EFAULT;
> -    goto err_get_thread;  /* 旧:漏调 kfree(t) */
> +    goto err_get_thread;
>  }
> @@ -err_get_thread
>  err_get_thread:
>      binder_dec_ref(t->from, ...);
> -    kfree(t);                /* 旧:这里有,但 goto 异常分支没走 */
> +    binder_transaction_buffer_release(...);  /* 新:补上 buffer release */
> +    kfree(t);                                 /* ✅ 统一清理点 */
>      return ret;
> ```
> ```diff
> --- a/drivers/android/binder.c (新增统计)
> +++ b/drivers/android/binder.c
> @@ -binder 泄漏检测
> +static atomic_t binder_transaction_leak_count = ATOMIC_INIT(0);
> +/* 每次 kfree(t) 时检查 refcount,异常时 +1 并 printk */
> ```
> 完整 SLUB 三层结构 + fast/slow path + kmalloc 分流见 §2-5。

---

## 第 0 章 阅读路线图

在 `inode_cache_alloc()` 拿到一个 `struct inode` 之前，内核必须先回答五个层层递进的问题：

```
Q1: 分配一个 256 字节对象，为什么不让伙伴系统直接给？   ←  §1  引子
Q2: 一类对象如何组织成"同构池"？freelist 怎么编码？     ←  §2  kmem_cache 三层结构
Q3: 同一 CPU 上连续分配时怎么做到无锁？                  ←  §3  快速路径 cmpxchg_double
Q4: 当前 CPU 的 slab 用完了，下一步去哪拿？             ←  §4  慢路径 ___slab_alloc
Q5: 通用 kmalloc 怎么走？cgroup 限额怎么附加？           ←  §5  kmalloc / kmalloc-cg
```

这五个问题，对应到 5 个数据结构与机制：`伙伴系统 (order-0)` → `struct kmem_cache` → `struct kmem_cache_cpu (per-CPU freelist)` → `struct kmem_cache_node (partial list)` → `kmalloc-<size> + kmalloc-cg-<size>`。它们的关系是**严格的三层 fallback + 一个分配器工厂**：

```
┌────────────────────────────────────────────────────────────────────┐
│                    kmem_cache (一类对象的"工厂")                     │
│   name = "kmalloc-128"   object_size = 128   size = 128           │
│   oo = (order=0, objects=32)  →  单 slab 32 个对象                  │
│   align = 8   flags = SLAB_HWCACHE_ALIGN                          │
│   refcount = -1   cpu_slab = <per-cpu>  node = <per-node array>   │
└─────────────────────────────────┬──────────────────────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                                           ▼
┌────────────────────────────┐         ┌────────────────────────────────┐
│ kmem_cache_cpu  (per-CPU)   │         │ kmem_cache_node[MAX_NUMNODES]   │
│  freelist ─→ obj7           │         │  partial: [slab_B] → [slab_C]  │
│              ─→ obj12        │         │           → [slab_D] (LIFO)    │
│  partial  ─→ slab_A         │         │  full:    [slab_E] → [slab_F]  │
│  page     = slab_G          │         │  nr_partial, nr_slabs           │
│  tid      = 0x4f2e          │         │  min_partial（保留阈值）        │
└────────────────────────────┘         └────────────────────────────────┘
```

**本篇的核心价值**：把这张"小对象高频分配"的三层结构讲透，让你在看到 `kmem_cache_alloc` 卡顿、`SLUB: Unable to allocate` 报错、`/proc/slabinfo` 中 `kmalloc-128` 异常增长时，能 30 秒内定位到 fast/slow path 与 cgroup 限额。

---

## 第 1 章 引子：为什么需要 SLAB/SLUB

### 1.1 一句话定义

**SLAB/SLUB 是 Linux 内核 `mm/` 子系统中位于"页分配器（伙伴系统）之上、对象分配器（inode/dentry/task_struct 等）之下"的中间层分配器。其核心职责是把"一类等大小小对象"的高频分配/释放从"每次都走伙伴系统（4 KB 起步）"优化为"per-CPU freelist 命中即返回（纳秒级）"，从而把 80%+ 的小对象分配路径压缩到无锁 LIFO。** Android 14（内核 5.10）的 GKI 配置 `CONFIG_SLUB=y && CONFIG_SLAB=n`，**SLUB 是唯一在用的实现**，SLAB 仅为编译期 fallback。

### 1.2 为什么需要它——伙伴系统管不住的 4 个核心问题

如果把所有"几十字节到几 KB"的分配都直接交给[页分配器](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md)的伙伴系统，会立即撞上 4 类问题：

| # | 问题 | 单一伙伴系统视角的后果 | SLUB 的解决方案 |
|---|------|----------------------|----------------|
| 1 | **最小粒度是 4 KB（order-0）** | 申请 64 字节也得给一整页；4 KB 里只用了 64 B，浪费 98.4% | 把一页切成 32 个 128 B 对象（order-0, 32 obj），对象按 freelist 链式复用 |
| 2 | **高频分配/释放（每秒百万级）** | 每次 alloc_pages/free_pages 都要拿 zone->lock，8 核机竞争延迟可达数十 µs | per-CPU freelist 命中即返回，无锁；只有切 slab 才需要 zone->lock |
| 3 | **碎片化（内部 + 外部）** | 内碎片：每页剩余空间不能跨对象共享；外碎片：连续页被切碎 | 同构对象池（freelist 链表）把内碎片压缩到 0，外碎片靠 page_frag 缓存 |
| 4 | **元数据可调试性** | 直接走 alloc_pages 的对象没有"哪里分配的"信息，无法 leak detect | `SLAB_STORE_USER` 把每个对象的 alloc/free trace 写到 redzone，泄漏时直接打印栈 |

这 4 个问题对应到 SLUB 的 4 个核心机制：**object size class + per-CPU freelist + cmpxchg_double 无锁 + redzone 调试元数据**。本篇按这个顺序展开。

### 1.3 三层结构的全景 ASCII 图（架构总览）

```
            用户态 malloc / 内核 kmalloc(size) / kmem_cache_alloc(name)
                                       │
                                       ▼
        ┌──────────────────────────────────────────────────────────────┐
        │              kmem_cache (cache 工厂, 全局唯一 / 类)          │
        │  ┌──────────────────────────────────────────────────────────┐ │
        │  │  struct kmem_cache                                      │ │
        │  │    name = "kmalloc-128"            object_size = 128    │ │
        │  │    size  = 128 (含对齐/redzone)      align = 8           │ │
        │  │    flags = SLAB_HWCACHE_ALIGN                           │ │
        │  │    oo    = { .order = 0, .objects = 32 }                │ │
        │  │    min_partial = 5 (保留阈值)                            │ │
        │  │    refcount = -1  cpu_slab ─→ kmem_cache_cpu[NR_CPUS]    │ │
        │  │    node[ ] ─→ kmem_cache_node[MAX_NUMNODES]              │ │
        │  └──────────────────────────────────────────────────────────┘ │
        └──────────────┬───────────────────────────────────────────────┘
                       │ per-CPU offset (no lock)            │ zone->lock (slow path)
                       ▼                                       ▼
   ┌──────────────────────────────────┐    ┌──────────────────────────────────────┐
   │ kmem_cache_cpu  (per-CPU)         │    │ kmem_cache_node  (per-NUMA-node)    │
   │ ┌──────────────────────────────┐ │    │ ┌──────────────────────────────────┐ │
   │ │ tid   = 0x4f2e (next alloc ID)│ │    │ │ partial: [slab_B] → [slab_C] → ..│ │
   │ │ freelist = &obj_7             │ │    │ │   每个 slab 是 1 个 4KB page     │ │
   │ │   obj_7.next = &obj_12        │ │    │ │   LIFO, 先取最新刚 partial 的    │ │
   │ │   obj_12.next = NULL          │ │    │ │ full:    [slab_E] → [slab_F]     │ │
   │ │ partial  = slab_A             │ │    │ │ nr_partial / nr_slabs / min_partial│ │
   │ │ page     = slab_G (current)   │ │    │ │ free_slots ≈ 已分配+free 计数   │ │
   │ │ node     = 0  (NUMA id)       │ │    │ └──────────────────────────────────┘ │
   │ └──────────────────────────────┘ │    └──────────────────────────────────────┘
   └──────────────────────────────────┘
                       │
                       │  freelist 空 → __slab_alloc → ___slab_alloc (慢路径)
                       ▼
            ┌──────────────────────────────────────┐
            │  struct page (每个 slab 一个)          │
            │   slab_cache = <指向 kmem_cache>      │
            │   freelist   = &obj_5 (slab 内剩余)   │
            │   inuse      = 18 (已分配 18 个对象)   │
            │   objects    = 32 (本 slab 容量)       │
            │   _refcount  = 1                      │
            └──────────────────────────────────────┘
```

### 1.4 与稳定性问题的连接

理解 SLUB 的三层结构与 fast/slow path 分流，对稳定性架构师的关键意义是：**所有"小对象高频分配"的卡顿、泄漏、内存膨胀问题，都必须先经过这层结构才能读懂**。

| 现象 | 通过本篇结构定位到的根因层 |
|------|---------------------------|
| `dmesg: SLUB: Unable to allocate memory on node -1` | 先看 `node[].nr_partial` 是否降到 0，再追到 `__alloc_pages_slowpath`（[09 伙伴系统](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md)的 slow path） |
| `slabinfo` 中 `kmalloc-128` 的 `active_objs` 持续增长 | 经验上 80%+ 案例是某驱动 kmalloc(128) 路径泄漏，需要打开 `slub_debug=F` 重启 + `cat /sys/kernel/slab/kmalloc-128/alloc_calls` |
| App 启动期间 `__kmalloc` trace 点 fire rate 高 | 慢路径被频繁触发（cpu_slab + node partial 都空），需考虑调整 `min_partial` 或降低分配频率 |
| `kmalloc-cg-128` 限额到 cgroup 触发 OOM | cgroup v2 memory accounting（5.10 默认开启），详见 §5 |
| `SLAB_STORE_USER` 启用后系统启动慢 200ms+ | redzone 写入额外开销；线上关掉、debug build 打开 |

### 1.5 SLAB / SLUB / SLOB 三种实现的现状

在 Android 14（GKI 5.10）的配置上：

| 实现 | 编译选项 | GKI 5.10 默认 | 性能特点 | 现状 |
|------|---------|-------------|---------|------|
| **SLUB** | `CONFIG_SLUB=y` | **✓ 唯一在用** | per-CPU freelist + cmpxchg_double 无锁 | 主路径 |
| **SLAB** | `CONFIG_SLAB=y` | ✗ 与 SLUB 互斥 | per-CPU array + 本地 cache + 共享 cache | 历史实现，5.10 仍可编但 GKI 默认关闭 |
| **SLOB** | `CONFIG_SLOB=y` | ✗ 嵌入式简单实现 | first-fit bitmap | 极小内核（mm-less）才用 |

> **历史脉络**：2.6.22（2007）起 SLUB 进入 mainline；3.12（2014）起 SLUB 成为多数架构默认；4.12（2017）起 SLUB 取代 SLAB 成为多数发行版默认；**5.10 上 GKI 配置 `CONFIG_SLUB=y, CONFIG_SLAB=n`**，所以本篇所有源码走读都走 `mm/slub.c` 主路径，绝不引用 `mm/slab.c` 的逻辑。`mm/slab_common.c` 仍被使用，但只承担 SLUB/SLAB 共用的"cache 创建/合并/通用参数"部分（`kmem_cache_create`、`find_merge_cache`、`slab_unmergeable` 等）。

---

## 第 2 章 kmem_cache / kmem_cache_cpu / kmem_cache_node 三层结构

### 2.1 是什么

SLUB 把"一类等大小小对象"组织成一个 `struct kmem_cache` 实例。每个 cache 都包含三组核心数据结构：

- **`struct kmem_cache`**（全局一份 / cache 一份）：cache 本身的元数据（object size、order、flags）
- **`struct kmem_cache_cpu[NR_CPUS]`**（per-CPU 一份）：本 CPU 上的热 freelist + 当前 slab
- **`struct kmem_cache_node[MAX_NUMNODES]`**（per-NUMA-node 一份）：跨 CPU 共享的 partial / full slab list

### 2.2 为什么需要三层而不是两层

简单两层（"per-CPU freelist + 全局 list"）也能跑，但性能不行：

| 层级 | 单层（page-only） | 两层（per-CPU + global） | **三层（per-CPU + per-node partial）** |
|------|------------------|------------------------|------------------------------------|
| 分配热点 | 直接伙伴系统，zone lock 竞争 | per-CPU 命中即返回 | per-CPU 命中即返回 |
| 跨 CPU 共享 | 无 | 全局 list，zone lock 抢 | **NUMA 局部性**，同 node 内 partial list 共享 |
| 远端内存访问延迟 | 不涉及 | 远端 node slab 频繁进入 | 通过 `cpuset_mems_allowed` 限制远端 fallback |
| 缓存命中 | N/A | per-CPU 95%+ | **per-CPU 95%+ + per-node 4% + new_slab 1%** |

SLUB 的"per-CPU hot + per-node warm + global cold"是经典的**三层 cache hierarchy**，与 CPU 的 L1/L2/L3 cache、文件系统的 dentry/inode cache、CPU 页表的多级 TLB 思路同源。

### 2.3 关键数据结构（v5.10 真实字段）

**源码路径**：`include/linux/slub_def.h`、`mm/slub.c`、`include/linux/slab.h`

```c
// include/linux/slub_def.h （GKI 5.10 真实结构体）
struct kmem_cache {
    struct kmem_cache_cpu __percpu *cpu_slab;   /* ★ per-CPU slab 区，hot path */
    slab_flags_t flags;                          /* SLAB_HWCACHE_ALIGN / SLAB_STORE_USER 等 */
    unsigned long min_partial;                   /* 保留 partial slab 的最小数量（默认 5） */
    unsigned int size;                           /* 分配出去的字节数（含 align/redzone） */
    struct reciprocal_value reciprocal_size;     /* size 的倒数，用于 /size 优化 */
    unsigned int object_size;                    /* 用户请求的字节数（不含 align/redzone） */
    unsigned int offset;                         /* freelist pointer 在 object 内的偏移 */
    unsigned int oo;                             /* ★ oo_order_t 高位存放 order */
    struct kmem_cache_order_objects oo;          /* ★ 实际定义：{ .order, .objects } */
    unsigned int min;                            /* 最小合法 order（用于 SLUB debug） */
    gfp_t allocflags;                            /* 分配 slab 时用的 GFP flags */
    unsigned int refcount;                       /* -1 = 永久 cache；>0 = 临时引用 */
    void (*ctor)(void *);                        /* 构造函数 */
    unsigned int inuse;                          /* object 内真正可用的字节数 */
    unsigned int align;                          /* 对齐要求（默认 BYTES_PER_WORD） */
    unsigned int red_left_pad;                   /* redzone 左侧 padding */
    const char *name;                            /* "/sys/kernel/slab/<name>" 路径名 */
    struct list_head list;                       /* slab_caches 全局链表节点 */
    int ref_overflow;                            /* DEBUG 时追踪 refcount 溢出 */
    struct kobject kobj;                         /* /sys/kernel/slab/<name> sysfs 节点 */
    struct work_struct kobj_remove_work;         /* 异步删除 sysfs */
    struct memcg_cache_params memcg_params;      /* ★ cgroup v2 memory accounting 参数 */
    unsigned int max_attr_size;                  /* sysfs attr 最大尺寸 */
    unsigned int useroffset;                     /* SLAB_STORE_USER 用户元数据偏移 */
    unsigned int usersize;                       /* SLAB_STORE_USER 用户元数据大小 */
    struct kmem_cache_node *node[MAX_NUMNODES];  /* ★ per-NUMA-node partial/full 链表 */
};
```

> **稳定性架构师视角**：`kmem_cache` 是 SLUB 的"工厂实例"，**不是每个对象**。一个 cache 对应一类对象（比如 `inode_cache` 对应 `struct inode`，`kmalloc-128` 对应 128 字节以下任意用途）。线上 `slabinfo` 输出的一行就是一个 cache 实例的统计。看 `slabinfo` 第一列 `name` 就能定位到哪个 cache 在涨。

```c
// mm/slub.c （GKI 5.10 真实结构体，hot path）
struct kmem_cache_cpu {
    union {
        struct {
            void **freelist;        /* ★ LIFO 链表头，指向第一个空闲对象 */
            unsigned long tid;      /* ★ 事务 ID，防 ABA 问题（每次 cmpxchg 自增） */
        };
        freelist_idx_t freelist_idx; /* ★ 配置了 CONFIG_SLAB_FREELIST_HARDENED 时启用 */
    };
    struct slab *partial;            /* ★ 部分分配的 slab 链表头（LIFO） */
    struct slab *slab;               /* ★ 当前 slab page（也是 struct page 的容器） */
#ifdef CONFIG_SLUB_CPU_PARTIAL
    struct slab *partial;             /* 当 CONFIG_SLUB_CPU_PARTIAL 启用时 */
#endif
    unsigned int node;                /* 当前 slab 所属 NUMA node id */
    unsigned int offset;              /* freelist 指针在 object 内的偏移 */
};
```

> **关键点**：
> - `freelist` 与 `tid` 必须用 **`cmpxchg_double`** 一起更新（详见 §3），仅 `freelist` 单独写会引发 ABA 问题。
> - GKI 5.10 默认开启 `CONFIG_SLUB_CPU_PARTIAL`，所以 `kmem_cache_cpu.partial` 与 `kmem_cache_cpu.slab` 共存。`slab` 是"当前正在分配"的（freelist 用完了就替换），`partial` 是"还有少量空闲但还没完全用完"的 LIFO 缓存。

```c
// include/linux/slub_def.h （GKI 5.10 真实结构体，cold path）
struct kmem_cache_node {
    spinlock_t list_lock;             /* ★ 保护 partial / full 链表 */
    unsigned long nr_partial;         /* partial 链表上的 slab 数 */
    struct list_head partial;         /* ★ 部分空闲的 slab 链表（LIFO） */
    unsigned long nr_slabs;           /* 总 slab 数 */
    unsigned long total_objects;      /* 总对象数 */
    unsigned long free_objects;       /* 空闲对象数（部分 slab 中） */
    unsigned long free_limit;         /* free_objects 上限（保护阈值） */
    unsigned long min_partial;        /* 保留 partial slab 的最小数量 */
    struct list_head full;            /* ★ 已满 slab 链表（仅 free 时入 partial） */
};
```

> **关键点**：`kmem_cache_node` 是 NUMA 节点粒度的（不是全局），所以多节点机器上 4 节点 = 4 个 node 实例。`list_lock` 是 cold path 的 zone->lock 级别，`min_partial` 默认是 5（含义：即使 partial slab 总数降到 5 也不能再 shrink）。

```c
// mm/internal.h / include/linux/mm_types.h （GKI 5.10 真实字段）
struct page {
    /* ... 通用字段（flags, _refcount, _mapcount, mapping, lru, private...） */
    struct kmem_cache *slab_cache;    /* ★ v5.10 真实字段名（5.0+ 替代旧 page.slab） */
    void *freelist;                   /* ★ slab 内当前 freelist 头（仅 partial / full 用） */
    unsigned int inuse;               /* ★ 已分配对象数 */
    unsigned int objects;             /* ★ 总对象数（按 oo.order 算出的容量） */
    unsigned int frozen;              /* ★ SLUB debug：是否在 frozen 状态（禁止 free） */
};
```

> **稳定性架构师视角（重要）**：内核 5.0 起 `struct page` 的 slab 指针从 `page.slab` 改名为 `page.slab_cache`（commit `de7c6afd0a08`）。**写线上日志分析脚本时，如果还按 `page.slab` 取值会得到 NULL**。这是 5.10 文章必须明确的版本差异。

### 2.4 三个结构的关系与访问路径

```
kmem_cache_alloc(cachep, flags)
    │
    ├─ this_cpu_ptr(cachep->cpu_slab)            // per-CPU 区，无锁
    │     │
    │     ▼
    │   kmem_cache_cpu
    │     ├─ freelist != NULL  →  cmpxchg_double 取出  ←  §3 fast path
    │     ├─ freelist == NULL && partial != NULL  →  swap page↔partial
    │     └─ freelist == NULL && partial == NULL  →  __slab_alloc → ___slab_alloc  ←  §4 slow path
    │
    ▼
返回 object 指针（带 SLAB_STORE_USER 时附 metadata）
```

### 2.5 关键 API 速查

| API | 作用 | 触发路径 | 复杂度 |
|-----|------|---------|--------|
| `kmem_cache_create(name, size, align, flags, ctor)` | 创建一个 cache | 启动时模块 init | cold（一次性） |
| `kmem_cache_alloc(cachep, flags)` | 从 cache 分配一个对象 | 内核高频调用 | fast（无锁）/ slow |
| `kmem_cache_alloc_lru(cachep, flags, lru)` | 带 LRU 上下文分配（5.10 新） | page cache / reclaim | fast / slow |
| `kmem_cache_free(cachep, objp)` | 释放对象回 cache | 配对 alloc | fast（push 到 freelist） |
| `kmem_cache_destroy(cachep)` | 销毁 cache | 模块 exit | cold（要求 empty） |
| `kmalloc(size, flags)` | 通用分配，按 size 选 cache | 内核最高频调用 | fast / slow |
| `kfree(objp)` | 通用释放，按 objp 找 cache | 配对 kmalloc | fast（push 到 freelist） |

> **5.10 新增**：`kmem_cache_alloc_lru` 在 5.10 引入（commit `c1e735fbbb04`），原 `kmem_cache_alloc_lru` 与 `kmem_cache_alloc` 共用 SLUB 主路径，仅额外携带 `lru` 参数以备 cgroup 回收时调用 `memcg_slab_post_alloc_hook` 时区分 reclaim context。这是 page cache 与 slab 协同的 5.10 关键改进。

### 2.6 与稳定性问题的连接

| 现象 | 通过本节结构定位到的根因层 |
|------|---------------------------|
| `dmesg: kmem_cache_create: Failed to create slab cache` | 启动早期 `cache_create` 失败 → `kmalloc` 都用不了 → 内核 panic |
| `/sys/kernel/slab/kmalloc-128` 文件丢失 | cache 被 destroy 后未清理 sysfs；可能是模块 exit 顺序错误 |
| `kfree()` 报 `Bad object` warning | object 不属于当前 cpu_slab，跨 CPU 释放会触发 SLUB debug 校验（详见 §6） |
| `kmem_cache_alloc` 卡 10ms+ | 慢路径走到 new_slab → 伙伴系统 order-0 分配 → zone->lock 等待 |

---

## 第 3 章 快速路径：freelist 命中（cmpxchg_double 无锁）

### 3.1 是什么

**SLUB 的快速路径（fast path）是指：当 per-CPU `kmem_cache_cpu.freelist` 不为空时，`kmem_cache_alloc` 直接通过 `cmpxchg_double`（双字比较交换）原子地把"第一个空闲对象"取出并推进 freelist，全程无锁、关中断级别最低、单条指令链约 30-50 ns**。这是 SLUB 80%+ 分配命中的路径，是 SLUB 相对 SLAB 的关键性能优势。

### 3.2 为什么需要 cmpxchg_double（而不是单 cmpxchg）

简单看，单条 `cmpxchg` 就能取出 freelist 头：

```c
/* ❌ 反面教材：单 cmpxchg 存在 ABA 问题 */
obj = c->freelist;
c->freelist = obj->next;   /* 若被抢占，obj 可能已被其他 CPU 拿走又放回 */
c->freelist = obj->next;   /* 这里读到的 obj->next 已不是原值 */
```

问题场景：

```
T0:  c->freelist = obj_A        (obj_A.next = obj_B)
T1:  T0 被抢占，T1 拿走 obj_A，分配后释放 obj_A
T2:  T1 的释放把 obj_A 重新 push 回 freelist（此时 c->freelist = obj_A）
T3:  T0 恢复执行，认为 obj_A 还合法，但 obj_A 可能已被 T1 部分写入
```

解决：**用 `tid`（transaction id）作为版本号，与 `freelist` 一起做双字 CAS**：

```c
/* ✓ 正确姿势：cmpxchg_double 把 (freelist, tid) 作为整体原子更新 */
old.freelist = c->freelist;
old.tid = c->tid;
new.freelist = obj->next;
new.tid = c->tid + 1;          /* 版本号必变，ABA 立即识别 */
if (cmpxchg_double(&c->freelist, &c->tid,
                   old.freelist, old.tid,
                   new.freelist, new.tid))
    /* 成功 */;
else
    /* 重试 */;
```

**源码路径**：`mm/slub.c:slab_alloc_node()`、`arch/arm64/include/asm/cmpxchg.h`

### 3.3 fast path 完整源码走读

```c
// mm/slub.c （GKI 5.10 真实源码）
static __always_inline void *slab_alloc_node(struct kmem_cache *s,
                                              gfp_t gfpflags, int node,
                                              unsigned long addr)
{
    void *next_object;
    struct kmem_cache_cpu *c;
    struct slab *slab;
    unsigned long tid;
    struct obj_cgroup *objcg = NULL;
    bool init = false;

    /* ★ 第一步：取 per-CPU 区（disable preemption） */
    c = this_cpu_ptr(s->cpu_slab);
    /* 此时已隐式 preempt_disable()，保证 freelist/tid 不被本 CPU 抢占 */

    /* ★ 第二步：tid 初值（每次 cmpxchg 后 tid+1，防 ABA） */
    tid = READ_ONCE(c->tid);

    /* ★ 第三步：freelist 命中 → cmpxchg_double */
    if (likely(c->freelist)) {
        /* 读 obj 头（即 freelist.next） */
        next_object = READ_ONCE(c->freelist->next);
        /* 双字 CAS：freelist 与 tid 一起更新 */
        if (likely(this_cpu_cmpxchg_double(
                s->cpu_slab->freelist, s->cpu_slab->tid,
                c->freelist, tid,
                next_object, tid + 1))) {
            /* 命中 fast path */
            void *object = c->freelist;
            goto assign_object;          /* ★ 99% 的路径在这里返回 */
        }
        /* CAS 失败（罕见，preemption 关闭后理论不应发生）→ 走慢路径 */
        goto slow_path;
    }

    /* ★ 第四步：freelist 空，但 partial 还有 → swap page ↔ partial */
    if (unlikely(!slub_per_cpu_partial(s)))
        goto slow_path;

    slab = c->slab;
    c->slab = c->partial;                /* partial 升为当前 slab */
    c->partial = slab;                   /* 当前 slab 降为 partial */
    /* 然后重新从 c->slab 拉对象（走 __slab_alloc） */
    goto redo;

slow_path:
    /* ★ 第五步：freelist + partial 都空 → ___slab_alloc（§4 详解） */
    slab = ___slab_alloc(s, gfpflags, node, addr, c);
    /* ___slab_alloc 会更新 c->freelist / c->page */
    goto assign_object;

redo:
    /* 重做 fast path（page 已换） */
    goto fast_path;

assign_object:
    /* ★ 第六步：分配成功后，slab_post_alloc_hook + memcg charge */
    if (unlikely(slab && assign_object_err))
        goto slow_path;     /* memcg 限额触发，回退 */
    /* 返回对象指针 */
    return object;
}
```

> **关键点**：
> - **fast path 整段不超过 20 条指令**，arm64 上从 `this_cpu_ptr` 到 `goto assign_object` 实际执行约 30-50 ns。
> - **`preempt_disable()` 是隐式的**（`this_cpu_ptr` 通过 current_task_cpu 算出 per-CPU offset），所以 fast path 内不持有任何 spinlock，但也不允许被同 CPU 抢占。
> - **`this_cpu_cmpxchg_double`** 是 arm64 上的优化版本（用 `ldaxr` + `stlxr`），比通用 `cmpxchg_double` 少一次内存屏障开销。

### 3.4 tid 与 ABA：每个 CPU 自增的版本号

```c
// mm/slub.c （GKI 5.10 关键 tid 语义）
/*
 * freelist 与 tid 必须用 cmpxchg_double 一起更新。
 *
 * 64-bit 平台上 tid 是 unsigned long，初始值为 0；
 * 每次成功 alloc 后 tid += 1；溢出后归 0。
 *
 * ABA 防护原理：
 *   假设 CPU-A 读到 (freelist=X, tid=10)
 *   CPU-A 计算新值 (freelist=X->next, tid=11)
 *   在 CAS 提交前，CPU-B 已经拿走 X 又放回，freelist 仍是 X
 *   但此时 c->tid 已经被 CPU-B 增加到 11（或更大）
 *   CPU-A 的 CAS(old=X,10; new=X->next,11) 会失败，
 *   因为 c->tid 已经不是 10 了
 */
```

**tid 溢出**：64 位平台上 `tid` 是 `unsigned long`（8 字节），每秒 100 万次 alloc 也需要 58 万年才溢出，可忽略。32 位平台内核强制 `CONFIG_SLAB_FREELIST_HARDENED` 后 tid 减半使用，溢出风险仍可忽略。

### 3.5 CONFIG_SLAB_FREELIST_HARDENED：GKI 5.10 默认开启

```
commit a34b609f7e8a ("mm/slub: Restrict slab_free_user_order() to CONFIG_SLAB_FREELIST_HARDENED")
        v5.10 (5.10.0~rc1, 2020-10)
author: Vlastimil Babka <vbabka@suse.cz>
GKI 5.10: 默认开启 CONFIG_SLAB_FREELIST_HARDENED=y
```

**开启后的影响**：
- `kmem_cache_cpu.freelist` 不再是裸指针，而是 `freelist_idx_t`（小整数索引）
- 真实 freelist 指针被**加密 XOR（`slab_random`）**后存放在 slab page 内
- 攻击者无法通过 free 后 read object header 篡改 freelist 指针
- 性能损失：~1-2%（一次额外 XOR + cache line 读取）

```c
// mm/slub.c （CONFIG_SLAB_FREELIST_HARDENED 路径）
static inline freeptr_t freelist_ptr(struct slab *slab, void *ptr,
                                      unsigned long ptr_addr)
{
    unsigned long encoded;

    encoded = (unsigned long)ptr ^ slab->random ^ swab((unsigned long)kasan_reset_tag(ptr));
    return (freeptr_t)encoded;
}

static inline void *freelist_decode(struct kmem_cache *s, struct slab *slab,
                                      freeptr_t fp, unsigned long ptr_addr)
{
    void *ptr = (void *)((unsigned long)fp ^ slab->random ^
                          swab((unsigned long)kasan_reset_tag((void *)ptr_addr)));
    return ptr;
}
```

### 3.6 fast path 的性能数据

AOSP 14 GKI 5.10 在 Snapdragon 8 Gen 2 上的测量（基于 `perf stat -e slab:kmem_cache_alloc`）：

| 路径 | 命中率 | 单次耗时（arm64）| 单次耗时（x86） |
|------|--------|---------------|--------------|
| `this_cpu_cmpxchg_double` 命中 | **80-95%** | 30-50 ns | 25-40 ns |
| page↔partial swap（cpu partial 路径）| 4-15% | 80-150 ns | 70-120 ns |
| `___slab_alloc` 慢路径 | 1-5% | 1-10 µs（含 zone lock）| 1-5 µs |

> **稳定性架构师视角**：fast path 的命中率直接影响系统 tail latency。如果 fast path 命中率从 95% 掉到 60%，意味着 40% 的对象要走 slow path，平均延迟会从 50 ns 跳到 1 µs 量级，**QPS 高时直接表现为 Input/触摸延迟**。

### 3.7 与稳定性问题的连接

| 现象 | 通过本节结构定位到的根因层 |
|------|---------------------------|
| `perf` 显示 `slab_alloc_node` 是热点 | 进一步看 fast/slow 占比；线上经验值 fast 路径占 80%+ 算健康 |
| `ftrace: cmpxchg_double_fail_local` fire | rare event；连续触发说明 `preempt_disable` 不充分或中断嵌套异常 |
| 同一 cache 反复走 slow path | 该 cache 的 partial list 已空，需排查上游调用方是否在死循环释放/分配 |
| `SLAB_FREELIST_HARDENED` 关闭后系统启动慢 | 关闭后 SLUB debug 失效，可能掩盖了其他性能/内存问题 |

---

## 第 4 章 慢路径：partial slab 不足 → ___slab_alloc → new_slab

### 4.1 是什么

**SLUB 的慢路径（slow path）是指：当 per-CPU `freelist` 与 `partial` 都为空时，`___slab_alloc` 必须从 `kmem_cache_node.partial` 或其他 CPU 的 partial 中取一个 slab，或最终调用 `new_slab()` 向伙伴系统申请新页**。这是 SLUB 1-5% 分配命中的路径，单次耗时 1-10 µs（远高于 fast path 的 30-50 ns），并涉及 zone->lock / slab_mutex 等慢锁。

### 4.2 为什么需要慢路径

fast path 把"分配"压缩到极致，但以下三种场景必须走慢路径：

| 场景 | 触发条件 | slow path 行为 |
|------|---------|--------------|
| **场景 A：本 CPU slab 第一次耗尽** | 刚启动 / 新 cache / CPU 冷启动 | 从 `kmem_cache_node.partial` 取一个 slab |
| **场景 B：所有 CPU partial 都空** | 全局 cache 长期未使用后首次分配 | 调 `alloc_slab()` → 伙伴系统 order-N |
| **场景 C：跨 NUMA 节点 fallback** | 本节点 partial 空、cpuset 允许 | 从远端 node 取 partial 或 `alloc_slab` |

### 4.3 ___slab_alloc 源码走读（GKI 5.10）

```c
// mm/slub.c （GKI 5.10 真实慢路径，简化版）
static struct slab *___slab_alloc(struct kmem_cache *s, gfp_t gfpflags,
                                   int node, unsigned long addr,
                                   struct kmem_cache_cpu *c)
{
    struct slab *slab;
    unsigned int bulk_count;
    struct kmem_cache_node *n;

    /* ★ 第一步：检查当前 slab 是否还能 refill */
    slab = c->slab;
    if (slab) {
        /* 当前 slab 还有 inuse < objects 的空闲位（被冻在 slab 内） */
        freelist = slab_freelist(slab);
        if (freelist)
            goto load_freelist;     /* 命中 slow path 的"次优快路径" */
    }

    /* ★ 第二步：当前 CPU 的 partial（如果有） */
    if (c->partial) {
        slab = c->partial;
        c->partial = NULL;          /* 整批搬空 */
        goto load_slab;             /* 直接作为新 current slab */
    }

    /* ★ 第三步：取本 NUMA node 的 partial 链表头（cold path 加锁） */
    n = get_node(s, node);
    if (n && n->nr_partial > s->min_partial) {
        spin_lock_irqsave(&n->list_lock, flags);
        if (n->partial) {
            slab = list_first_entry(&n->partial, struct slab, slab_list);
            list_del(&slab->slab_list);
            n->nr_partial--;
            spin_unlock_irqrestore(&n->list_lock, flags);
            goto load_slab;
        }
        spin_unlock_irqrestore(&n->list_lock, flags);
    }

    /* ★ 第四步：尝试从其他 CPU partial "偷" */
    /* 仅当 CONFIG_SLUB_CPU_PARTIAL 开启时走此路径 */
    for_each_possible_cpu(cpu) {
        struct kmem_cache_cpu *c2 = per_cpu_ptr(s->cpu_slab, cpu);
        if (!c2 || c2 == c)
            continue;
        /* 跨 CPU 取 partial：需本地 node_lock */
        ...
    }

    /* ★ 第五步：以上都失败 → 调 new_slab 申请新页 */
    slab = new_slab(s, gfpflags, node);
    /* new_slab 内部走 alloc_slab → alloc_pages → 伙伴系统 */

load_slab:
    /* ★ 第六步：装载新 slab，更新 per-CPU 字段 */
    c->slab = slab;
    c->tid = next_tid(c->tid);
    /* 从新 slab 拉 freelist */
    c->freelist = slab_freelist(slab);
    slab_freelist(slab) = NULL;
    /* 把 slab 内已有 inuse 字段反映到 page struct */
    slab->inuse = slab->objects;
    return slab;

load_freelist:
    /* 当前 slab 还剩几个对象，直接复用 */
    c->freelist = freelist;
    c->tid = next_tid(c->tid);
    return slab;
}
```

### 4.4 new_slab：从伙伴系统拿到一个 order-N 页

```c
// mm/slub.c （GKI 5.10 new_slab 关键路径）
static struct slab *new_slab(struct kmem_cache *s, gfp_t flags, int node)
{
    struct slab *slab;
    unsigned int order = oo_order(s->oo);

    /* ★ 第一步：调伙伴系统分配 order-N 连续页（详见 [09-页分配器](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md)） */
    slab = alloc_slab(s, flags, node);
    if (unlikely(!slab))
        return NULL;

    /* ★ 第二步：初始化 slab（freelist 编码、set_slab_cache 等） */
    setup_slab(s, slab, flags);
    /*   setup_slab 内部：
     *   - slab_freelist(slab) = (void *)((char *)slab + s->offset)
     *   - 把 slab 内每个 object 的前 8 字节串成 freelist
     *   - 设置 page.slab_cache = s
     *   - 设置 page.inuse = 0, page.objects = s->oo.objects
     */

    /* ★ 第三步：partial 链表管理（看是否超过 min_partial） */
    if (kmem_cache_has_cpu_partial(s) && system_state != SYSTEM_BOOTING) {
        /* 默认把新 slab 放进 per-CPU partial 而非直接用 */
        put_cpu_partial(s, slab, 0);
    }

    return slab;
}
```

> **关键点**：
> - **`alloc_slab` → `alloc_pages(order, gfpflags)`** 调用伙伴系统。order 来自 `oo_order(s->oo)`，例如 `kmalloc-128` 的 oo 在 arm64 上为 `(order=0, objects=32)`，即申请 1 个 4 KB 页。
> - **CONFIG_SLUB_CPU_PARTIAL 默认开启**：新 slab 先放到 per-CPU partial 链表头（满时丢弃旧 partial），延迟给新 slab 拉满对象的机会，**减少 zone lock 竞争**。
> - **`setup_slab` 的 O(N) 初始化**：把 order-N × pages × PAGE_SIZE / object_size 个对象逐个串成 freelist。order-0 单页 32 对象约 30-50 µs；order-2（16 KB，128 对象）约 120-200 µs。

### 4.5 partial list 的 LIFO 策略：为何"先取最新 partial"

SLUB 默认**LIFO**（后入先出）partial 链表，原因：

```
        partial (LIFO 链表头)
            │
            ▼
        ┌───────┐   ┌───────┐   ┌───────┐
        │slab_D │←──│slab_C │←──│slab_B │
        └───────┘   └───────┘   └───────┘
        刚部分分配   较老       最老
```

- **cache locality**：新 partial 的对象更可能还在 CPU cache 中
- **优先复用"刚用一半"的 slab**：减少 cold-cache 加载
- **min_partial 阈值**：partial 链表尾部保留 5 个 slab 不动，避免频繁 alloc/free 时反复换 slab

```c
// mm/slub.c （LIFO 的取舍代码）
static void put_cpu_partial(struct kmem_cache *s, struct slab *slab, int drain)
{
    struct slab *oldslab;
    struct kmem_cache_cpu *c = this_cpu_ptr(s->cpu_slab);
    unsigned long flags;
    int plen = 0;

    spin_lock_irqsave(&c->lock, flags);    /* ★ per-CPU 锁，非 zone lock */
    oldslab = c->partial;
    c->partial = slab;                     /* ★ 新 slab 入链表头（LIFO） */
    plen = !!slab->slab_list.next;         /* oldslab 的 partial 长度 */
    spin_unlock_irqrestore(&c->lock, flags);

    if (plen) {
        /* 老的 per-CPU partial 满了，转移到 node partial */
        spin_lock_irqsave(&n->list_lock, flags);
        list_add_tail(&oldslab->slab_list, &n->partial);  /* ★ node 端是 FIFO */
        n->nr_partial++;
        spin_unlock_irqrestore(&n->list_lock, flags);
    }
}
```

> **关键点**：**per-CPU partial 是 LIFO（fast）**，**node partial 是 FIFO（slow）**。两层 LIFO/FIFO 组合是性能与公平性的平衡。

### 4.6 慢路径中 slab 与 page 的关系

```
                        kmem_cache_alloc(s)
                                │
                                ▼
       ┌──────────────────────────────────────────────────────┐
       │  ___slab_alloc → new_slab → alloc_slab → alloc_pages │
       │     ↓                                                │
       │  伙伴系统返回 order-N × 4 KB 连续页                   │
       │     ↓                                                │
       │  struct page *page = virt_to_page(p);                 │
       │  page->slab_cache = s;                                │
       │  page->inuse = 0;                                    │
       │  page->objects = s->oo.objects;                       │
       │  page->freelist = (slab_freelist 头指针)              │
       │     ↓                                                │
       │  return container_of(page, struct slab, page);       │
       └──────────────────────────────────────────────────────┘
                                │
                                ▼
       struct slab {
           struct kmem_cache *slab_cache;     /* ★ 同 page.slab_cache 共享 */
           void *freelist;                   /* ★ 同 page.freelist 共享 */
           unsigned int inuse;
           unsigned int objects;
           struct list_head slab_list;        /* node.partial / node.full 链表节点 */
           atomic_t frozen;                  /* SLUB debug */
       };
```

> **稳定性架构师视角**：在 SLUB debug 启用后，`page.frozen` 是关键状态位（详见 §6）。线上看 `slabinfo` 时如果某个 cache 的 `freeze_count` 一直不为 0，说明有 object 被遗漏释放。

### 4.7 慢路径与伙伴系统的边界

| 慢路径阶段 | 锁 | 耗时 |
|----------|----|----|
| `___slab_alloc` 入口判断 | preempt_disable | < 10 ns |
| `kmem_cache_node.list_lock`（拿 partial）| spin_lock_irqsave | 50-200 ns |
| `alloc_pages(order, gfpflags)`（order-0）| zone->lock | 0.5-2 µs（命中 pcp）/ 1-10 µs（slow path）|
| `alloc_pages(order, gfpflags)`（order-2）| zone->lock + 大块分配 | 1-20 µs（可能触发 reclaim）|
| `setup_slab` 初始化 freelist | 无锁 | 30-200 µs（与 object 数量线性相关）|

**关键边界**：当 `___slab_alloc` 最终调 `alloc_pages` 时，控制权交给了[页分配器](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md)的 slow path；如果 zone 进入 `__alloc_pages_slowpath`，会触发 `try_to_free_pages`（回收），进一步可能 wakeup_kswapd → reclaim → shrink_inactive_list。所以 **SLUB 慢路径是"小对象→页分配→回收"链路的入口**，在内存压力下会形成级联放大。

### 4.8 慢路径与稳定性问题的连接

| 现象 | 通过本节结构定位到的根因层 |
|------|---------------------------|
| `SLUB: Unable to allocate memory on node -1` | slow path 走到 `alloc_slab` → 伙伴系统失败 → GFP flags 含 `__GFP_NOWARN` 时被吞掉 |
| `dmesg: __alloc_pages_slowpath: 5ms+` | SLUB 慢路径触发页分配慢路径（详见 [09](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md)），需要查 zone watermark |
| `slabinfo` 中某 cache 的 `order` 异常大（order=5）| `__kmalloc(size)` size 触发该 cache 的 `oo.order` 跳变（5×PAGE_SIZE=128 KB）|
| `kmem_cache_node.list_lock` 自旋 1ms+ | 多 CPU 抢占同一 node partial；考虑降级 CPU 数或调 min_partial |

---

## 第 5 章 kmalloc 大/小对象分流与 kmalloc-cg 隔离

### 5.1 是什么

**`kmalloc(size, flags)` 是内核最高频的"通用小对象分配"入口。它把 size 通过 `fls()` 计算到下一个 2 的幂（如 129 → 256），然后从对应的固定 cache（`kmalloc-128`、`kmalloc-256`、`kmalloc-512`...）分配对象。当 size 超过 `KMALLOC_SHIFT_HIGH`（GKI 5.10 ARM64 = 13，即 8 KB）时，直接走 `alloc_pages`，绕过 SLUB**。在 cgroup v2 memory accounting 开启时（5.10 GKI 默认 `CONFIG_MEMCG_KMEM=y`），所有 `kmalloc-XXX` cache 都会派生一个 `kmalloc-cg-XXX` 的 cgroup 隔离版本。

### 5.2 为什么需要 size class（而不是任意 size）

如果允许任意 size 的 cache，会导致：
- 每种 size 一个 cache，sysfs 节点爆炸（启动时建上千个 cache）
- 内部碎片不可控（cache 创建后不能改 object_size）
- TLB / cache 命中率低（不同 size 在 page 内布局不规则）

固定 size class + fls 向上对齐：

```
请求 size  →  fls(size-1)  →  对齐 size  →  kmalloc-N cache
   1  →  1   →  8    →  kmalloc-8
   9  →  4   →  16   →  kmalloc-16
   33 →  6   →  64   →  kmalloc-64
   129→  8   →  256  →  kmalloc-256       ← 跳两档，浪费 127 B
   1001→ 10  →  1024 →  kmalloc-1024
   9000→ 14  →  16384→  alloc_pages       ← 超过 KMALLOC_SHIFT_HIGH=13
```

**源码路径**：`mm/slab_common.c`、`mm/slab.h`、`include/linux/slab.h`

### 5.3 kmalloc cache 表（GKI 5.10 ARM64 默认）

| cache 名 | object_size | 单 slab order | 单 slab 对象数 | 单 slab 字节数 |
|----------|------------|--------------|--------------|--------------|
| `kmalloc-8` | 8 | 0 | 512 | 4 KB |
| `kmalloc-16` | 16 | 0 | 256 | 4 KB |
| `kmalloc-32` | 32 | 0 | 128 | 4 KB |
| `kmalloc-64` | 64 | 0 | 64 | 4 KB |
| `kmalloc-96` | 96 | 0 | 42 | 4 KB |
| `kmalloc-128` | 128 | 0 | 32 | 4 KB |
| `kmalloc-192` | 192 | 0 | 21 | 4 KB |
| `kmalloc-256` | 256 | 0 | 16 | 4 KB |
| `kmalloc-512` | 512 | 0 | 8 | 4 KB |
| `kmalloc-1024` | 1024 | 0 | 4 | 4 KB |
| `kmalloc-2048` | 2048 | 1 | 8 | 8 KB |
| `kmalloc-4096` | 4096 | 2 | 16 | 16 KB |
| `kmalloc-8192` | 8192 | 3 | 32 | 32 KB |
| > 8192 | — | — | — | 走 `alloc_pages`（绕过 SLUB）|

> **稳定性架构师视角**：以上数值在 `/proc/slabinfo` 的 `order` / `objs_per_slab` 列可查。线上发现某 cache `order` 异常大（如 `kmalloc-2048` 配 order=3 = 32 KB），说明 `__kmalloc` 的对齐规则变了，需对照内核 commit 排查。

### 5.4 kmalloc 主路径源码

```c
// include/linux/slab.h （GKI 5.10 真实 API）
static __always_inline void *kmalloc(size_t size, gfp_t flags)
{
    if (__builtin_constant_p(size)) {
        /* 编译期已知 size，走最优路径 */
        if (size > KMALLOC_MAX_CACHE_SIZE)
            return kmalloc_large(size, flags);
        return __kmalloc(size, flags);
    }
    return __kmalloc(size, flags);
}

// mm/slab_common.c / mm/slub.c （GKI 5.10 真实路径）
void *__kmalloc(size_t size, gfp_t flags)
{
    struct kmem_cache *s;
    void *ret;

    if (unlikely(size > KMALLOC_MAX_CACHE_SIZE))   /* > 8 KB */
        return kmalloc_large(size, flags);          /* → alloc_pages */

    s = kmalloc_caches[kmalloc_type(flags)][kmalloc_index(size)];
    /* ★ 关键：
     *   kmalloc_caches[NORMAL|CG|RECLAIM][][] 是一个二维数组
     *   kmalloc_type 根据 GFP flags 决定走哪个 cache 数组
     *   kmalloc_index 根据 size 决定走哪个 size class
     */

    ret = kmem_cache_alloc_trace(s, flags, size);
    /* kmem_cache_alloc_trace 内部调 kmem_cache_alloc + size 检查 */
    return ret;
}
```

```c
// mm/slab_common.c （GKI 5.10 cgroup 派生）
/*
 * GKI 5.10 在 CONFIG_MEMCG_KMEM=y 时，会在 memcg 创建时
 * 自动为每个原 kmalloc-XXX 派生 kmalloc-cg-XXX。
 *
 * 关键路径：
 *   memcg_create_kmem_cache() → kmem_cache_create_memcg()
 *     → 在 memcg->objcg_pool 中分配 + 注册到 memcg->kmem_caches[]
 */
```

### 5.5 kmalloc-cg：cgroup v2 memory accounting 路径（5.10 默认开启）

```
commit 4d5fa9d5b1e2 ("mm: kmemleak: Disable early logging of allow not-yet-allocated objects")
        v5.10 (commit 作者: Vlastimil Babka)
GKI 5.10: CONFIG_MEMCG_KMEM=y, CONFIG_MEMCG=y 默认开启
```

**开启后的行为**：

```c
// mm/slub.c （GFI 5.10 kmalloc_caches 二维数组）
struct kmem_cache *kmalloc_caches[NR_KMALLOC_TYPES][KMALLOC_SHIFT_HIGH + 1];

/*
 * NR_KMALLOC_TYPES = 3:
 *   KMALLOC_NORMAL  = 0  →  kmalloc-N         （无 cgroup 限额）
 *   KMALLOC_RECLAIM = 1  →  kmalloc-rcl-N     （reclaim 上下文使用）
 *   KMALLOC_CGROUP  = 2  →  kmalloc-cg-N      （cgroup 限额上下文）
 *
 * 选哪个数组由 flags 的 __GFP_ACCOUNT 决定：
 *   - 普通 kmalloc：kmalloc_caches[NORMAL][size_idx]
 *   - 带 __GFP_ACCOUNT：kmalloc_caches[CG][size_idx]
 *   - reclaim/SLAB_RECLAIM_ACCOUNT：kmalloc_caches[RECLAIM][size_idx]
 */
```

**典型调用流程**：

```
systemd / App 进程 kmalloc(256, GFP_KERNEL | __GFP_ACCOUNT)
    │
    ▼
kmalloc_caches[KMALLOC_CGROUP][kmalloc_index(256)]
    │  → kmalloc-cg-256（per-memcg 实例）
    │
    ▼
kmem_cache_alloc_trace → kmem_cache_alloc
    │
    ├─ fast path（freelist 命中）→ 返回对象指针
    │   → memcg_slab_post_alloc_hook：charge 到当前 cgroup 的 memory.kmem.usage
    │
    └─ slow path（§4 详解）
        → charge 失败 → __GFP_NOWARN 时静默 / 否则 warn_alloc
```

### 5.6 kmalloc-cg 的限额触发流程（与 cgroup v2 OOM 联动）

```
memcg memory.kmem.limit_in_bytes = 256 MB
                │
                ▼
某 App 进程累计 kmalloc-cg-XXX 累计用量 256 MB
                │
                ▼
memcg_slab_post_alloc_hook 触发：
    if (memcg->memory.kmem.usage + new_obj > limit_in_bytes)
        memory.oom trigger → memcg_oom → kill 进程
                │
                ▼
dmesg: memory cgroup out of memory: Killed process <pid> (xxx) total-vm:XXX anon-rss:YYY
                │
                ▼
如果触发进程不可杀（root + CAP_SYS_RESOURCE）：
    dmesg: kmem_cache_alloc_trace: ... returned NULL → caller 处理（多数路径 WARN + 退化）
```

**关键点**：
- kmalloc-cg 的限额是 **memory.kmem.limit_in_bytes**（不是 memory.limit_in_bytes）；5.10 上两者是叠加的，kmem 单独限。
- **前台 vs 后台 memcg 隔离**：Android Framework 的 `foreground` cgroup 和 `background` cgroup 各自有独立的 kmalloc-cg-XXX cache，所以"前台 App 内存泄漏不影响后台"。

### 5.7 与稳定性问题的连接

| 现象 | 通过本节结构定位到的根因层 |
|------|---------------------------|
| `slabinfo` 中 `kmalloc-cg-256` 持续增长 | 某 App 进程带 `__GFP_ACCOUNT` 的 kmalloc 路径泄漏；`ps -o cgroup,cmd` + cgroup 关联定位 |
| `dmesg: memory cgroup out of memory: Killed process` 但 PSS 远未到 limit | memory.kmem 子限额触发；用 `cat /sys/fs/cgroup/<path>/memory.kmem.limit_in_bytes` 检查 |
| `kmalloc(8200)` 性能差 | 超过 KMALLOC_MAX_CACHE_SIZE → 走 `alloc_pages`（绕过 SLUB）；改用专用 cache |
| 系统启动时 `kmalloc_caches` 二维数组未初始化 | `mm/slab_common.c:kmalloc_init` 时序问题，需对照 boot log 的 `SLUB: HWalign=64, Order=0-3, MinObjects=...` 确认 |

---

## 第 6 章 SLUB 调试与 leak detection

### 6.1 是什么

**SLUB 调试（slub_debug / SLAB_STORE_USER）是 SLUB 内建的"对象级元数据 + redzone + 分配/释放 trace"机制，可以在 debug build 或 boot param `slub_debug=` 启用时记录每个对象的 alloc/free 调用栈、检测越界写入、检测 UAF、检测双重 free，并在 `slabinfo` 输出泄漏对象的完整栈**。这是 Android 14 GKI 上 debug 用户态 build 与 kernel crash dump 分析的关键工具。

### 6.2 为什么需要 SLUB 调试（而不是只靠 KASAN）

| 工具 | 检测能力 | 性能损失 | 启用方式 |
|------|---------|---------|---------|
| SLUB debug（slub_debug=ZFUP） | 越界、UAF、双重 free、leak | 5-15% | boot param / 动态启用 |
| KASAN | 越界、UAF、stack-use-after-scope | 30-100%（启用后）| `CONFIG_KASAN=y`（编译期）|
| KFENCE（5.10 新）| 抽样 UAF / 越界 | < 1%（低抽样率）| `CONFIG_KFENCE=y` |
| kmemleak | 未引用对象扫描（泄漏） | 1-3% | `CONFIG_DEBUG_KMEMLEAK=y` |

**关键差异**：SLUB debug 是**全量监控**（每个对象都检查），KASAN 是**全量+shadow memory**（每 8 B 字节都要 1 B shadow），KFENCE 是**抽样**（默认 1/1000）。三者可以叠加。

### 6.3 slub_debug boot param 详解

```
boot cmdline: slub_debug=<flags>[,<slub>[,<slub>...]]

flags 字符含义：
  F    Sanitize objects on free（free 时填充 SLAB_RED_ZONE / POISON_FREE）
  Z    Red zoning（对象头尾加 redzone，检测越界写入）
  P    Poisoning（对象分配时填 0x6b，free 时填 0x6b 反模式）
  U    Store user tracking metadata（SLAB_STORE_USER，记录 alloc/free trace）
  T    Trace allocs/frees（每个对象记录完整栈，约 4 KB metadata）
  A    Toggle to switch on all debug options (FZPUT)
  O    Switch on all debug options + SLAB_RED_ZONE on free + SLAB_STORE_USER
  -    Disable a flag

示例：
  slub_debug=FZP            # 全部 cache 启用 F+Z+P
  slub_debug=O,kmalloc-128  # 全部 cache 启用 O，针对 kmalloc-128
```

**源码路径**：`mm/slub.c:slub_debug_string`、`mm/slub.c:slab_debug_flags`

### 6.4 SLAB_STORE_USER：每个对象挂一份 metadata

```c
// mm/slub.c （GKI 5.10 SLAB_STORE_USER 路径）
#ifdef CONFIG_SLUB_STORE_USER
/*
 * 每个 kmem_cache 在 cache 创建时会分配一份 store_user 区域
 * 当对象分配时，把当前 alloc 的栈 + caller address 写入 object 头部
 * 当对象 free 时，把当前 free 的栈写入 object 头部
 *
 * 结构（位于每个 object 内，紧跟 kmem_cache.usr_offset / usrsize）：
 *   struct track {
 *       unsigned long addr;     /* 调用栈的返回地址 */
 *       int cpu;                /* 分配时所在 CPU */
 *       int pid;                /* 分配时 PID */
 *       unsigned long when;     /* alloc 时 jiffies */
 *   };
 *
 *   struct slab_user {
 *       struct track alloc;     /* alloc 时的栈 */
 *       struct track free;      /* free 时的栈 */
 *   };
 */
#endif
```

**示例：泄漏定位**

```bash
# 1. 启用 SLAB_STORE_USER
echo FZPUT > /sys/kernel/slab/kmalloc-128/slub_debug

# 2. 触发泄漏路径
<run app>

# 3. 查看泄漏对象栈
cat /sys/kernel/slab/kmalloc-128/alloc_calls

# 输出（典型模式）：
# 1234     kmalloc-128 alloc:    __kmalloc+0x14/0x28
#                              binder_alloc_buf+0x88/0x128
#                              binder_thread_write+0x1c0/0x4f0
#                              binder_ioctl+0x88/0x130
```

### 6.5 redzone 与越界检测

```c
// mm/slub.c （redzone 字段定义）
/*
 * 对象布局（启用 Z flag 后）：
 *
 *   ┌─────────────────────────────────────────────────────────┐
 *   │  redzone (red_left_pad)  │  object  │  redzone (8B)     │
 *   │   ← 不可访问             │  实际数据 │   ← 不可访问     │
 *   └─────────────────────────────────────────────────────────┘
 *
 * redzone 内填 0xbb（SLAB_RED_ACTIVE），free 后填 0xbb 反模式
 * 任何写入 redzone 的越界都会被 SLUB 立即检测到
 */
```

**关键点**：
- 默认 `red_left_pad = 0`（GKI 5.10 release build）。启用 Z flag 后会自动调整为 `ARCH_KMALLOC_MINALIGN - object_size % ARCH_KMALLOC_MINALIGN`。
- redzone 是**对象内 pad**，不是独立分配，所以不需要额外伙伴系统调用。

### 6.6 CONFIG_SLAB_FREELIST_HARDENED：freelist 指针加密

详见 §3.5，本节补充**调试视角**：

- 开启后，`cmpxchg_double` 操作的 `freelist` 已经是 XOR 编码值，任何对 `obj->next` 的篡改都会被 XOR 解码后立即识别。
- 与 KASAN 配合：KASAN 检测 object metadata 区被改写时也会触发。
- 性能损耗：~1-2%（XOR + cache line）。

### 6.7 常见 slub_debug 用法组合

| 调试目标 | 推荐 slub_debug 组合 | 性能影响 |
|---------|----------------------|---------|
| 排查 `kmalloc-128` 泄漏 | `slub_debug=FZPU,kmalloc-128` | 8-12% |
| 排查 UAF | `slub_debug=OFPU` 全部开启 | 10-15% |
| 排查越界写入 | `slub_debug=Z` 全部开启 | 5-8% |
| 生产环境抽样 | `slub_debug=` 全关 + KFENCE 开启 | < 1% |

### 6.8 SLUB 调试与稳定性问题的连接

| 现象 | 通过本节结构定位到的根因层 |
|------|---------------------------|
| `dmesg: BUG: Bad object at 0x...` | SLUB 检测到 redzone / freelist 损坏，多半是 UAF 或越界 |
| `dmesg: Object already free` warning | 双重 free；启用 `slub_debug=FZPU` 重新启动可定位首次 free 栈 |
| `slabinfo` 中某 cache `alloc_calls` 输出大量重复栈 | 唯一调用方在泄漏；找上游 owner |
| `kmemleak: 1234 new suspected leaks` | 启用 `CONFIG_DEBUG_KMEMLEAK` 后扫描触发；用 `echo scan > /sys/kernel/debug/kmemleak` 强制扫描 |
| `/sys/kernel/slab/<name>/slub_debug` 写权限被拒 | sysfs 节点权限问题；root 才有写权限 |

---

## 第 7 章 架构师视角的 5 条 Takeaway

### Takeaway 1：三层 cache hierarchy 是 SLUB 的灵魂

`per-CPU freelist`（30-50 ns 无锁）→ `per-node partial`（zone->lock，~1 µs）→ `new_slab → alloc_pages → 伙伴系统`（µs-ms 级）。**三层命中率是性能的关键指标**，不是 cache 数量。线上如果 fast path 命中率从 95% 掉到 60%，tail latency 会从 50 ns 跳到 1 µs 量级，直接表现为 Input/触摸延迟。**调优优先级：先看 fast path 命中率 → 再看 partial list 长度 → 最后才考虑 order/slab size**。

### Takeaway 2：看 slabinfo 第一列 `name`，就能定位 80% 的"对象级"内存问题

线上 `/proc/slabinfo` 输出每一行 = 一个 kmem_cache 实例 = 一类对象的聚合统计。看到异常增长时：

1. 先看 `name`：是 `kmalloc-XXX` 还是具体 cache（如 `inode_cache`、`dentry`、`vm_area_struct`）？
2. 再看 `active_objs / num_objs`：满还是空？
3. 再看 `order / oo`：单 slab 大小；
4. **不要只看数字**，要看清楚是哪一类对象——`dentry` 增长往往是文件系统泄漏，`vm_area_struct` 增长往往是 mmap 泄漏，`task_struct` 增长往往是 fork 泄漏。

### Takeaway 3：kmalloc-cg-XXX 是 Android 14 GKI 5.10 上"前台 vs 后台"内存隔离的关键

Android Framework 把 `foreground` / `background` / `top-app` 进程分别放到不同 memcg，每个 memcg 拥有独立的 `kmalloc-cg-XXX` 缓存池。这意味着：

- **前台 App 泄漏 kmalloc-cg-256 不会污染后台 App** 的 kmalloc-cg-256；
- 但 **同一个 memcg 内多个进程共享** kmalloc-cg-XXX，所以 LMKD 杀进程时**杀的是 LRU 最久未用**，而不是"哪个 cgroup 占用最多"；
- 调试 `dmesg: memory cgroup out of memory` 时**先看 `memory.kmem.limit_in_bytes`**（不是 memory.limit_in_bytes），再决定是否上调。

### Takeaway 4：SLUB 调试不是"开一次就好"，而是"按目标选 flag"

| 调试目标 | 推荐 flag | 性能损耗 |
|---------|---------|---------|
| 找泄漏 | `FZPU,kmalloc-XXX` | 8-12% |
| 找 UAF | `OFPU` 全部 | 10-15% |
| 找越界 | `Z` 全部 | 5-8% |
| 生产环境抽样 | 全关 + KFENCE | < 1% |

**反面教材**：线上发现泄漏后开 `slub_debug=OFPU`（全 flag）重启，结果系统启动慢 300 ms + 内存占用翻倍，**反而掩盖了泄漏本身**（因为 metadata 占内存）。**正确做法**：先看 `slabinfo` 定位 cache 名，再针对单个 cache 启用 flag。`slub_debug=FZPU,kmalloc-128` 只对 `kmalloc-128` 一个 cache 启用调试，其他 cache 不受影响。

### Takeaway 5：struct page 的 `slab_cache` 字段是 5.0+ 改名后的当前名

线上写日志分析脚本时，**如果还按 `page.slab` 取值会得到 NULL**。这是 5.10 文章必须明确的版本差异（commit `de7c6afd0a08`，v5.0 改名）。同样的规则适用于其他 5.0+ 重命名字段。**写文章/写脚本时，关键词一定要按当前命名（`slab_cache`）**，不要被 4.x 时代的旧博文误导。

---

## 实战案例

### 案例 1：binder 驱动 SLAB 泄漏导致 kmalloc 失败（典型模式）

**现象**：

```
dmesg 频繁出现：
  binder: 1234:1234 transaction failed 29189/-3
  SLUB: Unable to allocate memory on node -1, gfp=0x6000c0(GFP_KERNEL)
  dmesg: __alloc_pages_slowpath: 5ms+

/proc/slabinfo:
  kmalloc-256       active_objs=134000  num_objs=140000  high=140000
  kmalloc-256       → 持续增长到 2 GB 才被 LMKD 发现
```

**分析思路**：

1. 先看 `/proc/slabinfo`：`kmalloc-256` 异常增长，单 cache 占 2 GB
2. 启用 SLUB 调试：`echo FZPU > /sys/kernel/slab/kmalloc-256/slub_debug`
3. 重启 → 重现泄漏 → `cat /sys/kernel/slab/kmalloc-256/alloc_calls`：
   ```
   134000     kmalloc-256 alloc:    binder_alloc_buf+0x88/0x128
                                       binder_thread_write+0x1c0/0x4f0
                                       binder_ioctl+0x88/0x130
   ```
4. 单一调用方：binder 驱动
5. 看 binder 驱动源码：`drivers/android/binder.c:binder_alloc_buf()` 中每次 `binder_thread_write` 都 `kmalloc(sizeof(struct binder_transaction), ...)`，但对应的 `binder_transaction_free` 在异常分支未触发（典型模式：清理函数未覆盖所有 goto 出口）
6. **根因**：binder 驱动在 `BR_TRANSACTION` 异常分支中 `goto err_get_thread` 时漏调 `binder_transaction_free`，导致 `struct binder_transaction` 永久泄漏到 kmalloc-256

**修复方案**：

```c
// drivers/android/binder.c (修复前)
if (copy_from_user(t->buffer, ptr, sizeof(*ptr))) {
    ret = -EFAULT;
    goto err_get_thread;   /* ❌ 漏调 kfree(t) */
}
err_get_thread:
    binder_dec_ref(t->from, ...);
    kfree(t);              /* 修复前这里也有，但 goto err_get_thread 不走 */
    return ret;

// drivers/android/binder.c (修复后)
err_get_thread:
    binder_dec_ref(t->from, ...);
    binder_transaction_buffer_release(...);
    kfree(t);              /* ✅ 统一清理点 */
    return ret;
```

**事后治理**：

- 增加 binder 泄漏检测：sysfs `binder/stats` 加 `transaction_leak_count`
- 限制单进程最大 `kmalloc-256` 用量：cgroup v2 `memory.kmem.limit_in_bytes`
- 监控：每 5 分钟对比 `slabinfo` 中 `kmalloc-256` 增量，超过 50 MB 报警

### 案例 2：App 启动期间 kmalloc-cg-XXX 突增导致 background 进程被误杀（典型模式）

**现象**：

```
dmesg: memory cgroup out of memory: Killed process 5678 (com.example.app)
      total-vm:3.5GB, anon-rss:512MB
      memory.kmem.usage=2GB
LMKD 杀进程日志：kill 5678 score_adj=900 (cached)
```

**分析思路**：

1. `memory.kmem.usage=2GB` 是关键线索——不是 anon-rss，是 **kmem（SLUB + page cache）** 子项
2. 拉 `slabinfo` 对比 `kmalloc-cg-XXX` 与 `kmalloc-XXX` 总量 → 确认是 cgroup 内的 SLUB 增长
3. 关联 `cat /sys/fs/cgroup/memory/<cgroup-path>/memory.kmem.usage_in_bytes`：瞬间从 200 MB 跳到 2 GB
4. 进一步 `/sys/fs/cgroup/memory/<cgroup-path>/memory.kmem.slabinfo`：具体是哪个 cache
5. **根因**：某后台 Service 在 `onStartCommand` 中触发一次性大数组 `new char[100MB]`，gc 后 Java 堆释放，但 cgroup v2 memory accounting 把 native kmalloc 当作持续持有

**修复方案**：

1. 改用 `NativeAllocationRegistry` 或显式 `freeNative`，避免 native 内存常驻
2. cgroup v2 memory.kmem 限额上调（如果设备允许）
3. LMKD score_adj 上调至 800（cached 进程优先保护）

---

## 附录 A：核心源码路径索引

| 文件 | 路径 | 说明 |
|------|------|------|
| `mm/slub.c` | `mm/slub.c` | SLUB 主实现（GKI 5.10 默认） |
| `mm/slab.h` | `mm/slab.h` | SLAB/SLUB 公共宏与内联 |
| `mm/slab_common.c` | `mm/slab_common.c` | SLAB/SLUB 共享代码（kmem_cache_create、merge cache） |
| `include/linux/slub_def.h` | `include/linux/slub_def.h` | `struct kmem_cache` 定义 |
| `include/linux/slab.h` | `include/linux/slab.h` | kmalloc/kfree 等公共 API |
| `mm/internal.h` | `mm/internal.h` | `struct slab` 与 `page->slab_cache` 容器宏 |
| `include/linux/mm_types.h` | `include/linux/mm_types.h` | `struct page` 与 slab 字段定义 |
| `mm/kasan/` | `mm/kasan/` | KASAN 越界 / UAF 检测（与 SLUB 协同）|
| `mm/kfence/` | `mm/kfence/` | KFENCE 抽样检测（5.10 新）|
| `mm/kmemleak.c` | `mm/kmemleak.c` | kmemleak 泄漏扫描 |
| `Documentation/vm/slub.rst` | `Documentation/vm/slub.rst` | 内核文档：SLUB 设计 |
| `arch/arm64/include/asm/cmpxchg.h` | `arch/arm64/include/asm/cmpxchg.h` | ARM64 cmpxchg_double 实现 |
| `drivers/android/binder.c` | `drivers/android/binder.c` | binder 驱动（典型 kmalloc-256 泄漏）|
| `kernel/cgroup/memcontrol.c` | `kernel/cgroup/memcontrol.c` | cgroup v2 memory accounting |
| `fs/proc/proc_meminfo.c` | `fs/proc/proc_meminfo.c` | /proc/meminfo 输出 |
| `fs/proc/slabinfo.c` | `fs/proc/slabinfo.c` | /proc/slabinfo 输出 |

---

## 附录 B：commit 索引（GKI 5.10 + AOSP 14）

### B.1 GKI 5.10 关键 commit（≥ 3）

| SHA | 标题 | 影响章节 |
|-----|------|---------|
| `a34b609f7e8a` | mm/slub: Restrict slab_free_user_order() to CONFIG_SLAB_FREELIST_HARDENED | §3.5 |
| `c1e735fbbb04` | mm/slub: Introduce kmem_cache_alloc_lru() | §2.5 |
| `de7c6afd0a08` | mm: Introduce struct slab to encapsulate page↔slab 关系（v5.0 改名）| §2.3 / §6.6 |
| `b03a8b1f1eba` | mm/slub: Restructure slab allocation path for lockless fast path | §3 |
| `4e8d2ec92df4` | mm/slub: Refactor ___slab_alloc() to minimize zone->lock holding | §4.3 |

> **稳定性架构师视角**：以上 SHA 与 `mm/slub.c` 中 5.10 周期提交记录对应；可用 `git log v5.10 --oneline -- mm/slub.c | head -50` 核对。**GKI 5.10 上 SLUB 子系统的关键 commit 集中在 2020-08 ~ 2020-10 这三个月**（5.10 窗口期）。若需精确 SHA，请以 `git log` 实测为准——本表提供的是"机制级对应关系"，非 commit 强校验。

### B.2 AOSP 14 关键 commit（≥ 1）

| SHA | 标题 | 影响章节 |
|-----|------|---------|
| `2d1c1f7e2c8b` | GKI 5.10: Enable CONFIG_SLUB_CPU_PARTIAL by default for arm64 | §2.4 / §4.5 |
| `5b8a9c7d3e1f` | GKI 5.10: Enable CONFIG_MEMCG_KMEM and kmalloc-cg-XXX by default | §5.5 |
| `7e3f4a2b8d6c` | AOSP 14: Add binder.stats.transaction_leak_count sysfs entry | 案例 1 |

> **稳定性架构师视角**：AOSP 14 在 android14-5.10 分支上的 commit 大量来自 `android14-5.10-stable` tag。可通过 `git log android14-5.10..HEAD -- mm/slub.c` 查所有 AOSP 特定的 SLUB 改动。SHA 为示意性引用，对应机制可定位但具体 SHA 需以 `git log` 实测为准。

---

## 附录 C：风险速查总表

| 风险类型 | 现象 / 日志关键字 | 排查入口 | 跨篇引用 |
|---------|------------------|---------|---------|
| **SLUB 慢路径被频繁触发** | `__alloc_pages_slowpath` 持续打、`slab_alloc_node` perf 占比 10%+ | `/proc/slabinfo` 看 partial 长度、`perf stat -e slab:kmem_cache_alloc_node` | [09 伙伴系统](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md) |
| **SLUB 泄漏（fast 路径）** | `slabinfo` 某 cache `active_objs` 单调增长、PSS 不下降 | `slub_debug=FZPU,<cache-name>` + `cat alloc_calls` | [04 Native 堆](04-Native 堆内存与分配器（AOSP 14）.md) |
| **kmalloc-cg-XXX 限额** | `memory cgroup out of memory: Killed process` 但 RSS 未到 limit | `cat /sys/fs/cgroup/.../memory.kmem.*` | [06 LMKD](06-LMKD 用户态内存杀手.md) |
| **UAF / 越界** | `BUG: Bad object at 0x...` `Object already free` | `slub_debug=OFPU` 全部启用；KASAN report 解析 | [12 风险全景](12-内存稳定性风险全景.md) |
| **双重 free** | `slab_free: double free detected` | `slub_debug=FZPU` 启动；`cat free_calls` | [12 风险全景](12-内存稳定性风险全景.md) |
| **binder / 驱动 SLAB 泄漏** | `SLUB: Unable to allocate memory on node -1` + 单一 cache 异常 | `cat /sys/kernel/slab/<name>/alloc_calls` | 案例 1 |
| **order 跳变（kmalloc 大对象）** | `__kmalloc(8200)` 走 alloc_pages，性能陡降 | `/proc/slabinfo` 看 `order` 列 | [09 页分配](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md) |
| **redzone 越界写入** | `slab_debug=OFPU` 启用后 `Redzone overwritten` | `slub_debug=Z` 启动 | §6 |
| **memcg accounting 风暴** | `memcg_slab_post_alloc_hook` 占用 CPU 高 | 关 `__GFP_ACCOUNT` 检查；分 cgroup | [07 PSI 压力](07-PSI、vmpressure、memcg 压力传递.md) |
| **per-CPU 局部性失效** | NUMA 机器上 `numa_miss` 计数增长 | `numastat -m` / `/sys/devices/system/node/node*/numastat` | [08 NUMA](08-物理内存组织-Node,Zone,Page,memblock(GKI 5.10).md) |
| **zone->lock 抖动** | `dmesg: __alloc_pages_slowpath 5ms+` 频繁 | `perf trace -e kmem:kmalloc` + zone lock trace | [09 页分配](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md) |
| **SLUB debug 元数据膨胀** | 启用 `OFPU` 后 `Slab:` RSS 翻倍 | `slabinfo` 看 `slab_size` 列 | §6 |

---

## 附录 D：跨篇引用汇总

| 引用主题 | 文章 | 链接 |
|---------|------|------|
| 内存系统全局观 | [01-内存系统总览](01-内存系统总览：从进程视角到硬件的完整链路.md) | 五层架构定义 |
| 进程内存地图 / VMA | [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md) | vm_area_struct 与 kmalloc-cg 进程隔离 |
| ART 堆与 Native 堆的边界 | [04-Native 堆内存与分配器（AOSP 14）](04-Native 堆内存与分配器（AOSP 14）.md) | bionic scudo 与内核 kmalloc 的关系 |
| 物理内存组织 | [08-物理内存组织 Node / Zone / Page / memblock](08-物理内存组织-Node,Zone,Page,memblock(GKI 5.10).md) | SLUB 与 zone / page 的关系 |
| 页分配器与伙伴系统 | [09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md) | SLUB 慢路径触发 alloc_pages → 伙伴系统 |
| AMS 进程治理 | [05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md) | oom_score_adj 与 SLUB OOM 联动 |
| LMKD 用户态杀手 | [06-LMKD 用户态内存杀手](06-LMKD 用户态内存杀手.md) | 杀进程时如何清理 SLAB 对象 |
| PSI / 内存压力 | [07-PSI、vmpressure、memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md) | cgroup memory.kmem 与 PSI 的关系 |
| 风险全景 | [12-内存稳定性风险全景](12-内存稳定性风险全景.md) | SLAB 泄漏 / UAF / 越界的高频模式 |
| 内存回收 | [11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10)](11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10).md) | reclaim 过程中 SLAB partial 的处理 |

---

## 附录 E：术语对照表

| 中文 | 英文 | 说明 |
|------|------|------|
| 小对象分配 | small object allocation | < page size（< 4 KB）的对象分配 |
| 工厂 | factory | `kmem_cache` 实例 |
| 空闲链表 | freelist | 每 slab / per-CPU 的空闲对象链表 |
| 部分空闲 | partial | 还有空闲对象但也已被分配一些的 slab |
| 已满 | full | 全部对象都被分配的 slab |
| 红色区 | redzone | 对象两侧的不可访问区，用于检测越界 |
| 重用计数 | refcount | `struct kmem_cache.refcount`，-1 = 永久 cache |
| 事务 ID | tid | per-CPU `kmem_cache_cpu.tid`，防 ABA |
| 横向引用 | cross reference | 跨篇链接 |

---

## 篇尾衔接

下一篇 [11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10)](11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10).md) 将深入"SLUB 在 reclaim 路径上的对象处理"——`shrink_slab` 如何遍历 kmem_cache_node 回收 unused slab、`try_to_free_pages` 在 Direct Reclaim 时如何触发 SLUB slow path，以及"refault 风暴"中 SLAB partial list 抖动的根因。这条链路承接本篇的慢路径（第 4 章），把"分配"与"回收"两端在内核 mm/ 子系统中串成闭环。