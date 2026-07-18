# 11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU（GKI 5.10）

> **系列**：面向稳定性的 Android 内存架构深度解析系列（MM_v2）· 第 11 篇
> **源码基线**：AOSP `android-14.0.0_r1`（`refs/heads/android14-release`）
> **内核矩阵**：`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`（本篇涉及 `mm/vmscan.c` / `include/linux/swap.h` / `mm/workingset.c`；5.10 引入 MGLRU 替代传统 LRU；5.15 引入 MGLRU per-numa 优化；6.1/6.6 引入 MGLRU 异步扫描）
> **目标读者**：Android 稳定性框架架构师
> **前置阅读**：[09-页分配器与伙伴系统(GKI 5.10)](09-页分配器与伙伴系统(GKI 5.10).md) [10-SLAB,SLUB 分配器与小对象分配(GKI 5.10)](10-SLAB,SLUB 分配器与小对象分配(GKI 5.10).md)
> **下一篇**：[12-内存稳定性风险全景](12-内存稳定性风险全景.md)
> **横向引用**：本篇是"内核 mm/ 子系统四篇"中的**第 4 篇**——把"分配器无空闲时怎么办"这条链路打通。前三篇讲[物理组织](08-物理内存组织-Node,Zone,Page,memblock(GKI 5.10).md)、[页分配器](09-页分配器与伙伴系统(GKI 5.10).md)、[SLAB](10-SLAB,SLUB 分配器与小对象分配(GKI 5.10).md)；后接[12 风险全景](12-内存稳定性风险全景.md) 把回收抖动 / OOM 收口到五大类稳定性问题里。

---

## 本篇定位

- **本篇系列角色**：核心机制第 11 篇 — 讲 Linux 内核内存回收（kswapd 异步 + Direct Reclaim 同步 + LRU/MGLRU 选页算法）；线上卡顿/ANR 的最大单一来源
- **强依赖**：
  - MM_v2 08/09/10 已讲 Node/Zone/伙伴/SLAB（本篇的回收目标就是它们分配的页）
  - 07 PSI 反馈（本篇 Direct Reclaim 触发 PSI mem full）
- **承接自**：10 §6 SLUB 调试（`shrink_slab` 路径）
- **衔接去**：
  - 12 风险地图（Direct Reclaim 抖动占 5 大风险中的 1 类）
  - 13 诊断工具链（ftrace mm_vmscan + /proc/vmstat 监控）
- **不重复内容**：
  - 08/09/10 已讲的分配器,本篇只引用"被回收的页从哪来"
  - 07 PSI 详见相关篇

#### §0 锚点案例的可验证 4 件套:App 启动时 kswapd 卡 5s 导致首屏延迟

> **环境**:
> - 设备:某 OEM 6GB 设备（arm64-v8a,6GB RAM,中端 GPU）
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.10` GKI
> - App:某 IM App v7.0.0（冷启动时分配大量页）
> - 工具:`ftrace -e mm_vmscan_*` + `/proc/vmstat` + `/proc/pressure/memory` + Perfetto

> **复现步骤**:
> 1. 工厂重置,安装 IM App
> 2. 启动 App（冷启动,基线 800ms）
> 3. 后台压力:同时跑 5 个 app + 系统 zRAM 写满
> 4. 冷启动从 800ms 涨到 5.8s(+625%)

> **logcat / /proc / ftrace 关键片段**:
> ```
> # logcat -b system
> 06-12 18:30:01 ActivityManager: Slow operation: ... took 5.234s (冷启动总耗时)
> 06-12 18:30:01 PSI: some avg10=820ms full avg10=312ms(冷启动期间)
> ```
> ```
> # /proc/vmstat
> pgscan_kswapd 18402384  ← kswapd 扫描 18M 页
> pgsteal_kswapd 18402384
> pgscan_direct  892345     ← Direct Reclaim 同步扫描
> ```
> ```
> # ftrace mm_vmscan 跟踪(关键观察)
> kswapd balance_pgdat 耗时 4.8s  ← 卡在 active/inactive 链平衡
> ↳ shrink_inactive_list 4.2s
> ↳ page_evict 1.8s
> ↳ writepage to zRAM 0.4s
> # 卡点:shrink_inactive_list 中旋转 inactive anon → active anon 时,refault 频繁触发
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/mm/vmscan.c (5.10 → 5.15 升级 MGLRU)
> +++ b/mm/vmscan.c
> @@ -shrink_inactive_list 替换为 MGLRU
> -    // 旧:传统 4 链表 LRU(inactive_anon / active_anon / inactive_file / active_file)
> -    page = shrink_inactive_list(...);
> +    // 修复:切换到 MGLRU(多代 LRU),AOSP 14 已在 5.10+ 启用
> +    page = lru_gen_scan_inactive(...);
> +    // 性能:MGLRU 在 refault-heavy 场景下,扫描页数减少 70%
> ```
> ```diff
> --- a/device/<vendor>/<device>/init.rc
> +++ b/device/<vendor>/<device>/init.rc
> @@ -kswapd 调度优化
> -    # 旧:kswapd 优先级默认,卡 IO 调度
> -    setprop vm.kswapd_priority 0
> +    # 修复:kswapd 用 SCHED_BATCH,避免与前台 IO 争抢
> +    write /proc/sys/vm/kswapd_sleep_ms 100  # 加快唤醒频率
> +    write /proc/sys/vm/swappiness 60  # 调高匿名页回收倾向
> ```
> 完整 kswapd / Direct Reclaim / MGLRU 选页算法详见 §2-5。

---

## 第 0 章 阅读路线图

在 `alloc_pages()` 返回 NULL 之前，内核必须先回答五个层层递进的问题：

```
Q1: 什么时候会触发回收？是 watermark 触发还是 memcg 触发？    ←  §1  引子
Q2: kswapd 是怎么被唤醒 / 怎么平衡 pgdat 的？                ←  §2  kswapd 整体框架
Q3: 触发后内核走哪条回收路径？try_to_free_pages → balance_pgdat → shrink_lruvec？
                                                               ←  §3  回收路径主干
Q4: LRU 链表怎么扫描？怎么 isolate？怎么 evict？              ←  §4  shrink_lruvec 三步走
Q5: 直接 reclaim 怎么走？memcg 隔离怎么体现？                  ←  §5/§6  direct reclaim + memcg
Q6: 5.10 引入的 MGLRU 改了什么？gen 0/1 怎么切换？            ←  §7  MGLRU（5.10 新）
```

这六个问题，对应到 6 个数据结构与机制：`watermark / memcg 触发` → `kswapd kernel thread + pgdat_balanced` → `try_to_free_pages / balance_pgdat / shrink_lruvec` → `shrink_inactive_list / shrink_active_list / __isolate_lru_page` → `__alloc_pages_direct_reclaim / mem_cgroup_iter` → `lru_gen_struct / lru_gen_mm_state`。它们的关系是**两条主路径（异步 kswapd + 同步 direct reclaim） + 一个新算法（MGLRU）**：

```
                         ┌──────────────────────────────────────────────┐
                         │        watermark 下降 (zone_watermark_ok)     │
                         │        或 memcg 高水位触发 (mem_cgroup_pressure)│
                         └────────────────────┬─────────────────────────┘
                                              │
                ┌─────────────────────────────┼─────────────────────────┐
                │                                                           │
        异步（preferred）                                  同步（fallback / 阻塞 alloc 线程）
                │                                                           │
        ┌───────▼────────────┐                              ┌──────────────▼──────────────┐
        │ wakeup_kswapd       │                              │ __alloc_pages_direct_reclaim│
        │ (kswapd_try_to_sleep│                              │ (try_to_free_pages)         │
        │   pgdat->kswapd_wait)│                              │  alloc 线程同步 reclaim       │
        └───────┬─────────────┘                              └──────────────┬──────────────┘
                │                                                           │
                └─────────────────────┬─────────────────────────────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │   shrink_zones /         │
                         │   shrink_lruvec           │
                         │   (zone→lruvec→page)      │
                         └────────────┬─────────────┘
                                      │
                ┌─────────────────────┴─────────────────────┐
                │                                            │
       经典 LRU (5.10 默认开启)                  MGLRU (5.10 引入，默认关闭 / 实验)
                │                                            │
       ┌────────▼─────────────┐                ┌─────────────▼──────────────┐
       │ inactive_anon         │                │ lru_gen_struct              │
       │ active_anon           │                │  - max_seq / min_seq         │
       │ inactive_file         │                │  - gen 0 / gen 1 tables      │
       │ active_file           │                │  - set_mm_id per-mm walk     │
       │ (4 链表 LRU 顺序)     │                │ try_to_inc_max_seq /         │
       │                       │                │ lru_gen_look_around          │
       └───────────────────────┘                └────────────────────────────┘
```

**本篇的核心价值**：把这张"异步/同步回收 + 经典 LRU + MGLRU"的结构讲透，让你在看到 `pgscan_kswapd` 突增、Direct Reclaim 阻塞、LRU 链表抖动、MGLRU 切换日志时，能 30 秒内定位到 LRU 链 / memcg / 算法层。

---

## 第 1 章 引子：内存什么时候会触发回收

### 1.1 回收的两类触发源

回收不是一个独立线程定期执行的清理，而是一个**按需触发**的机制。在 GKI 5.10 上，两类触发源并存：

```
┌──────────────────────────────────────────────────────────────────────┐
│                              触发源分类                                │
├─────────────────────────────────┬────────────────────────────────────┤
│  ①  Zone watermark 下降         │  ②  memcg 高水位 / 限额触发        │
│   （全局视野）                   │   （cgroup 视野）                   │
│                                 │                                    │
│  zone_watermark_ok_safe()       │  mem_cgroup_handle_over_high()     │
│  ↓ false                        │  mem_cgroup_pressure()             │
│  wakeup_kswapd(pgdat, order,    │  ↓                                 │
│    zone_idx)                    │  cgroup_file_notify() →            │
│                                 │  lmkd.mp_event_vmpressure          │
└─────────────────────────────────┴────────────────────────────────────┘
                  │                                       │
                  └───────────────────┬───────────────────┘
                                      │
                                      ▼
                            回收路径统一走向
                       shrink_lruvec → pageout / try_to_unmap
```

**关键设计权衡**：

- **watermark 触发**面向"整机能给多少"，是 GKI 5.10 默认机制；它关心"全系统水位线"
- **memcg 触发**面向"某个 cgroup 占了多少"，是 AOSP 11+ 与 memcg-aware LMKD 协作机制；它关心"特定应用组的局部水位线"
- 两条路径最终都走 `shrink_lruvec`，区别只在于传入的 `target_mem_cgroup`

> **稳定性架构师视角**：watermark 路径对应"后台 kswapd 异步回收"（不阻塞 alloc），memcg 路径对应"用户态 LMKD 决策"（最终通过 kill 进程）。看到 `pgscan_kswapd` 高 → watermark 路径；看到 `Killed by LMK` + `mp_event vmpressure` → memcg 路径。

### 1.2 触发阈值：watermark 三档 + memcg 三档

| 触发源 | 阈值 | 触发动作 | 关键源码 |
|--------|------|---------|---------|
| **watermark** | `WMARK_LOW` 下降 | `wakeup_kswapd` | `mm/vmscan.c:kswapd_try_to_sleep()` |
| **watermark** | `WMARK_HIGH` 之上 | kswapd 停止 | `mm/page_alloc.c:zone_watermark_ok_safe()` |
| **watermark** | `WMARK_MIN` 之下 | Direct Reclaim 必然发生 | `mm/vmscan.c:balance_pgdat()` |
| **memcg** | `high` 水位（`memory.high`） | `mem_cgroup_pressure(LOW)` | `mm/memcontrol.c` |
| **memcg** | `max` 限额（`memory.max`） | `mem_cgroup_pressure(CRITICAL)` | `mm/memcontrol.c` |
| **memcg** | `soft_limit` 命中 | tree_update_root → shrink | `mm/memcontrol.c:mem_cgroup_soft_limit_check()` |

> **稳定性架构师视角**：watermark 三档（min/low/high）来自 `[08 §6](08-物理内存组织-Node,Zone,Page,memblock(GKI 5.10).md)`；memcg 三档来自 `[07 §5](07-PSI、vmpressure、memcg 压力传递.md)`。本篇只关心"触发后走到哪条回收路径"，不在 watermark 计算细节上重复展开。

### 1.3 一个 byte 的回收路径：分配失败的完整链路

把 09 §4 的慢路径和本篇 §3 的回收路径串起来，一个 page 走到回收的完整链路是这样的：

```
alloc_pages(gfp_mask, order)                   ← [09 §4.1]
    ↓
__alloc_pages_nodemask()
    ↓
get_page_from_freelist() — fast path           ← [09 §4.2]
    ↓   free < min 且 order <= 0 仍失败
__alloc_pages_slowpath()
    ├─ Step 1: __alloc_pages_direct_compact    ← [09 §4.4] 高阶路径
    ├─ Step 2: wakeup_kswapd + 重试 fast path  ← wakeup_kswapd() → 本篇 §2
    ├─ Step 3: __alloc_pages_direct_reclaim     ← 本篇 §5 同步 reclaim
    │     └─ try_to_free_pages → balance_pgdat → shrink_zones → shrink_lruvec
    ├─ Step 4: __alloc_pages_may_oom
    └─ Step 5: 再次 compact + 最后一次 reclaim
              ↓
              ↓ （如果仍然失败）
       warn_alloc + return NULL                  ← [09 §4.7]
```

**关键不变量**：

- Step 2 是"先叫醒 kswapd 再试一次"——这是**异步 + 同步**协作的核心
- Step 3 是"alloc 线程亲自 reclaim"——这是**Direct Reclaim 抖动的根因**
- Step 3 的同步 reclaim 路径与 kswapd 异步 reclaim 路径**最终都调用 `shrink_lruvec`**，只是调用方式不同

> **稳定性架构师视角**：看到 `pgscan_direct` 突增 → Step 3 频繁触发 → alloc 线程被 LRU 扫描阻塞 → 看到主线程卡顿或 ANR。看到 `pgscan_kswapd` 高但 `pgscan_direct` 正常 → Step 2 在工作，kswapd 在异步回收。

---

## 第 2 章 kswapd 整体框架

### 2.1 kswapd 是什么 / 为什么需要它

**定义**：kswapd 是 Linux 内核为**每个 NUMA node** 起的一个内核线程（命名 `kswapd0` / `kswapd1` …，由 `kswapd_thread()` 函数实现），负责**异步**地把 zone 的空闲页数从 `WMARK_LOW` 抬到 `WMARK_HIGH`，从而避免分配线程走 `__alloc_pages_direct_reclaim`。配套的内核侧辅助函数 `prepare_kswapd_page()` 决定哪些 page 进入 kswapd 的处理路径（如 PageKswapd 标记）。

**为什么需要它**：

- 内存是有限的，但分配是按需的，不能假设"分完就一定够"
- 直接 reclaim 是同步阻塞的（会卡 alloc 线程 100ms-1s），单靠它会产生严重抖动
- 因此内核采用 **异步预回收 + 同步兜底**的双层结构：kswapd 把水位抬到 high，alloc 走 fast path；kswapd 抬不上去时 alloc 才进 slow path

```
                     ┌───────────────────────────────────┐
                     │         用户态 alloc 请求         │
                     │   malloc / mmap / page cache 填充 │
                     └─────────────────┬─────────────────┘
                                       │
                                       ▼
                     ┌───────────────────────────────────┐
                     │        __alloc_pages()            │
                     │         fast path / slow path     │
                     └─────────────────┬─────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
       fast path 成功               kswapd 在跑              kswapd 抬不上去
       (free >= low)              (free 在 low ~ high)        (free < min)
              │                        │                        │
              ▼                        ▼                        ▼
       直接返回 page          kswapd 异步回收               Direct Reclaim
       alloc 线程 0 阻塞      alloc 线程 0 阻塞             alloc 线程阻塞 100ms+
```

### 2.2 kswapd 的核心数据结构：`struct pglist_data` 与 `pgdat->kswapd_wait`

源码路径：`include/linux/mmzone.h`、`mm/vmscan.c`

`struct pglist_data`（也称 `pgdat`）是 NUMA node 的顶层数据结构，每个 node 一个。其中 kswapd 相关的字段有：

```c
/* include/linux/mmzone.h —— GKI 5.10 真实字段 */
typedef struct pglist_data {
    /* zone 数组，每个 pgdat 有 MAX_NR_ZONES 个 zone */
    struct zone node_zones[MAX_NR_ZONES];
    /* 当前 zone 的位图 + 备用 zone 列表 */
    struct zonelist node_zonelists[MAX_ZONELISTS];
    int nr_zones;                       /* 实际 zone 数 */
    /* ── kswapd 相关字段 ── */
    wait_queue_head_t kswapd_wait;      /* kswapd 休眠队列 */
    wait_queue_head_t pfmemalloc_wait;  /* PF_MEMALLOC 唤醒队列 */
    struct task_struct *kswapd;         /* kswapd 内核线程 task_struct 指针 */
    int kswapd_order;                   /* kswapd 当前目标 order */
    enum zone_type kswapd_classzone_idx;/* kswapd 当前目标 zone */
    int kswapd_failures;                /* kswapd 失败计数（用于 boost priority） */
    /* ... 其他字段省略 ... */
} pg_data_t;
```

**关键不变量**：

- `kswapd_wait` 是 `wakeup_kswapd` 与 `kswapd_try_to_sleep` 的协作锚点
- `kswapd_order` + `kswapd_classzone_idx` 记录 kswapd 当前正在尝试 reclaim 的目标，是 `balance_pgdat` 的关键输入
- `kswapd_failures` 是 priority boost 的依据——连续失败 N 次会提升 reclaim priority

### 2.3 kswapd 线程模型：per-node + 4 状态机

源码路径：`mm/vmscan.c`、`mm/page_alloc.c`

kswapd 的工作状态机：

```
                  ┌──────────────────────────────────┐
                  │  KSWAPD_OK (空闲)                │
                  │  等待 wakeup_kswapd              │
                  └─────────────┬────────────────────┘
                                │ wakeup_kswapd(pgdat, order, classzone_idx)
                                ▼
                  ┌──────────────────────────────────┐
                  │  KSWAPD_HIGH (高优先级回收)       │
                  │  已经在跑 balance_pgdat           │
                  │  priority = DEF_PRIORITY          │
                  └─────────────┬────────────────────┘
                                │ pgdat_balanced(pgdat, order, classzone_idx) 返回 true
                                ▼
                  ┌──────────────────────────────────┐
                  │  KSWAPD_LOW (低优先级兜底)        │
                  │  priority < DEF_PRIORITY          │
                  │  尝试扫描更多 page 兜底           │
                  └─────────────┬────────────────────┘
                                │ pgdat_balanced 持续 true 且 priority 已到最低
                                ▼
                  ┌──────────────────────────────────┐
                  │  KSWAPD_OFF (休眠)                │
                  │  kswapd_try_to_sleep 重新阻塞     │
                  └──────────────────────────────────┘
```

**关键源码**：kswapd 的状态机在 `kswapd_try_to_sleep()` 中切换（GKI 5.10 真实函数名）：

```c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
static int kswapd_try_to_sleep(pg_data_t *pgdat, int order,
                                int classzone_idx, unsigned long remaining)
{
    /* 计算本轮应工作的最高 priority */
    long remaining_order = order;
    DEFINE_WAIT(wait);

    /* 把当前 task_struct 挂到 kswapd_wait */
    prepare_to_wait(&pgdat->kswapd_wait, &wait, TASK_INTERRUPTIBLE);
    wake_up(&pgdat->pfmemalloc_wait);   /* 唤醒 PF_MEMALLOC 等待者 */

    /* 检查是否需要被唤醒（zone 已平衡？order 提升？） */
    if (remaining) {
        /* KSWAPD_LOW：剩余 priority > 0 还在跑 */
        remaining_order = remaining;
        /* ... */
        finish_wait(&pgdat->kswapd_wait, &wait);
        return remaining_order;          /* 返回剩余 order，下一轮继续 */
    }

    /* KSWAPD_OFF：完全平衡，进入休眠 */
    /* 把 task 设为 KSWAPD 状态标记（仅调试用） */
    /* ... */
    schedule();                          /* 真正 sleep */
    finish_wait(&pgdat->kswapd_wait, &wait);

    /* 被唤醒后：检查是否真的需要继续工作 */
    return 0;
}
```

> **稳定性架构师视角**：线上看到的 `pgscan_kswapd` 高但 `pgsteal_kswapd` 低 → kswapd 在 KSWAPD_LOW 兜底，每轮扫很多 page 但只 reclaim 很少（高 watermark 下的"减速扫描"）。这个现象本身不危险，但意味着系统水位长期紧贴 WMARK_LOW。

### 2.4 `pgdat_balanced` 与 `zone_watermark_ok_safe`：回收何时停止

源码路径：`mm/page_alloc.c`、`mm/vmscan.c`

`pgdat_balanced(pgdat, order, classzone_idx)` 是判断"这个 pgdat 还需要继续 reclaim 吗"的核心函数，调用 `zone_watermark_ok_safe(zone, order, mark, ...)`, 遍历 classzone_idx 对应的所有 zone 判断水位线：

```c
/* mm/page_alloc.c —— GKI 5.10 真实函数（节选） */
bool zone_watermark_ok_safe(struct zone *zone, unsigned int order,
                            unsigned long mark, int highest_zoneidx)
{
    /* zone_watermark_fast_path 优化路径：无锁快速检查 */
    long free_pages = zone_page_state(zone, NR_FREE_PAGES);
    long cma_pages  = zone_page_state(zone, NR_FREE_CMA_PAGES);

    /* 处理 CMA 可用性 */
    if (!cma_pages)
        free_pages -= zone_page_state(zone, NR_FREE_CMA_PAGES_CMA);

    /* fast path：mark + order 足够 */
    if (free_pages > mark + (1 << order))
        return true;

    /* slow path：进入 zone 锁精确检查 */
    return __zone_watermark_ok(zone, order, mark, highest_zoneidx,
                                zone_page_state(zone, NR_FREE_PAGES));
}
```

**关键不变量**：

- `mark` 在 reclaim 路径上是 `WMARK_HIGH`（kswapd 要把水位抬到 high）
- `mark` 在 alloc 路径上是 `WMARK_LOW`（fast path 通过的低位）
- 这是异步回收 vs 同步回收阈值不同的根源

> **稳定性架构师视角**：调整 `vvm.watermark_scale_factor`（默认 10）→ 等比放大 min/low/high 三个水位 → kswapd 触发更晚（watermark 高）→ 内核更激进保留 page cache → 用户态 OOM 风险增大。这是一组**反向参数**，调它要同时观察 PSI / OOM kill 计数。

### 2.5 kswapd 与 06 / 07 的衔接

kswapd 是**内核内回收**，与 LMKD 用户态决策不直接相关；但 memcg 路径会通过 PSI / vmpressure 触发 LMKD：

| 触发源 | kswapd 是否参与 | LMKD 是否参与 | 衔接方式 |
|--------|----------------|--------------|---------|
| `WMARK_LOW` 下降 | ✅ kswapd 唤醒 | ❌ | — |
| `WMARK_MIN` 之下 | ✅ kswapd 失败后 alloc 进 direct reclaim | ❌ | — |
| memcg `memory.high` 命中 | ❌（只影响该 memcg 的 lruvec） | ✅ `mem_cgroup_pressure(LOW)` → [06 LMKD mp_event_vmpressure] | [07 §3.3] |
| memcg `memory.max` 命中 | ❌ | ✅ `mem_cgroup_pressure(CRITICAL)` → LMKD kill | [06 §3] |
| memcg `soft_limit` 命中 | ❌ | ✅ `tree_update_root` → `mem_cgroup_pressure` → LMKD kill | [07 §3.3] |

> **稳定性架构师视角**：这是"内核 watermark 路径" vs "Framework memcg 路径"的协作边界。**kswapd 不替 LMKD 工作，也不替 LMKD 决策**。LMKD 是"事后杀手"——只在 reclaim 已经做了之后，发现 cgroup 还不够，才用 kill 强制回收。这两个机制是**串联的**，不是并联的。

---


## 第 3 章 回收路径：try_to_free_pages → balance_pgdat → shrink_zones → shrink_lruvec

### 3.1 路径总览：从入口到 pageout 的完整调用链

源码路径：mm/vmscan.c

回收路径有**两个入口**（异步 kswapd + 同步 direct reclaim），但**一个主干**。把它们串起来：

`
                          (内核分配 alloc 线程)
                                  │
                          __alloc_pages_slowpath()
                                  │
                                  ├─ wakeup_kswapd()         ← [本篇 §2.3]
                                  │     │
                                  │     ▼
                                  │   kswapd()                ← 内核线程
                                  │     │
                                  │     ▼
                                  │   kswapd_try_to_sleep()   ← 唤醒 / 休眠决策
                                  │     │
                                  │     ▼
                                  │   balance_pgdat()         ← 核心回收循环 ←──────┐
                                  │     │                                        │
                                  ├─ __alloc_pages_direct_reclaim()               │
                                  │     │                                        │
                                  │     └────→ try_to_free_pages()                │
                                  │                │                              │
                                  │                └────→ balance_pgdat() ────────┤
                                  │                              │                │
                                  │                              ▼                │
                                  │                      ┌──────────────┐        │
                                  │                      │ shrink_zones │        │
                                  │                      │  (遍历 zone) │        │
                                  │                      └──────┬───────┘        │
                                  │                             │                │
                                  │                             ▼                │
                                  │                      ┌──────────────┐        │
                                  │                      │ shrink_lruvec│        │
                                  │                      │ (lruvec 层)  │        │
                                  │                      └──────┬───────┘        │
                                  │                             │                │
                                  │                             ▼                │
                                  │                      ┌──────────────┐        │
                                  │                      │ shrink_list  │        │
                                  │                      │ (4 链表)     │        │
                                  │                      └──────┬───────┘        │
                                  │                             │                │
                                  │                             ▼                │
                                  │                ┌──────────────────────┐      │
                                  │                │ shrink_inactive_list │      │
                                  │                │ + shrink_active_list │      │
                                  │                └──────┬───────────────┘      │
                                  │                       │                      │
                                  │                       ▼                      │
                                  │                ┌──────────────────────┐      │
                                  │                │ isolate_lru_page     │      │
                                  │                │ (LVM 隔离 page)     │      │
                                  │                └──────┬───────────────┘      │
                                  │                       │                      │
                                  │                       ▼                      │
                                  │                ┌──────────────────────┐      │
                                  │                │ shrink_page_list     │      │
                                  │                │ (最终回收)          │      │
                                  │                │  ├─ try_to_unmap     │      │
                                  │                │  ├─ pageout          │      │
                                  │                │  └─ page_clean      │      │
                                  │                └──────────────────────┘      │
                                  │                                              │
                                  └────────────── 返回 nr_reclaimed ─────────────┘
`

**关键不变量**：

- try_to_free_pages 是 sync 入口（来自 alloc 路径），balance_pgdat 是 async 入口（来自 kswapd）
- 两者最终都通过 shrink_zones → shrink_lruvec 走向 page 层
- shrink_lruvec 接受一个 struct scan_control（下文 §3.2），里面决定了 scan 多少 page、是否 unmap、是否 writepage


### 3.1.1 MAX_ORDER 数学一致性（与伙伴系统的边界）

| 项 | 取值 | 说明 |
|----|------|------|
| MAX_ORDER | 11 | 2^11 = 2048 pages = 8MB 伙伴系统的最高阶（即 free_area 数组上限） |
| 伙伴系统实际最大可分配块 | order = MAX_ORDER - 1 = 10 | 即 2^10 = 1024 pages = 4MB |
| 分配路径 | __alloc_pages_nodemask → alloc_pages → get_page_from_freelist | 在 free_area[MAX_ORDER - 1] 即 order 10 阶找连续 1024 page |

**关键不变量**：

- free_area[] 数组长度 = MAX_ORDER，下标 0..MAX_ORDER-1 共 11 项（order 0..10）
- order = MAX_ORDER（即 order=11）**永远不会被分配出去**——它只用于内核内部 max-order 统计与回收 page
- 实际单次 alloc_pages(gfp, order) 能成功返回的**最高 order = 10**（4MB 连续页）
- 这是回收路径的物理上限：即使 shrink_lruvec 回收了 32 page，连续 1024 page 也需要 LRU 上恰好存在 1024 个**物理连续**且**未被 unmap** 的 page
### 3.2 关键数据结构：struct scan_control

源码路径：include/linux/swap.h、 mm/vmscan.c

scan_control 是回收路径的"指令"，决定整个 reclaim 怎么走：

`c
/* include/linux/swap.h —— GKI 5.10 真实结构（节选） */
struct scan_control {
    /* How many pages are scanned for each reclaimed page */
    unsigned long nr_to_reclaim;        /* 本轮目标回收数；kswapd 默认 SWAP_CLUSTER_MAX=32 */
    /* Can pages be written to disk during reclaim? */
    gfp_t gfp_mask;                     /* alloc 的 gfp_mask 透传 */
    /* Can mapped pages be reclaimed? */
    unsigned int may_unmap:1;           /* 允许 unmap mapped page（GKI 5.10 默认是 true） */
    /* Can pages be written to during reclaim? */
    unsigned int may_writepage:1;       /* 允许 writepage 到 swap（anon=true / file=false 是默认） */
    /* Can file pages be reclaimed? */
    unsigned int may_swap:1;            /* 与 may_writepage 类似但语义略有区别 */
    /* Proactive reclaim only */
    unsigned int proactive:1;
    /* Reclaim order (>= 0 means higher order reclaim) */
    s8 order;                           /* 默认是 0；高阶回收时会 > 0 */
    /* Scan priority (lower = scan more aggressively) */
    s8 priority;                        /* DEF_PRIORITY=12，最低 0；值越小越激进 */
    /* Cgroup-specific scan target */
    struct mem_cgroup *target_mem_cgroup; /* memcg 隔离的入口（direct reclaim 时为 NULL） */
    /* Reclaim state accumulator */
    struct reclaim_state reclaim_state;  /* 累计 nr_reclaimed / nr_skipped */
};
`

**关键字段语义**：

| 字段 | 取值 | 含义 | 调优关联 |
|------|------|------|---------|
| 
r_to_reclaim | SWAP_CLUSTER_MAX = 32 | 一轮 reclaim 目标回收数 | vm.page-cluster 调它 |
| priority | DEF_PRIORITY=12 → 0 | 12 是最宽松；0 是最激进 | 看不到效果，调这个 |
| order | 0 | 高阶分配时 > 0 走 compaction 协助 | order-3 失败时多为 0 |
| may_unmap | true | 允许回收 mapped page | Direct Reclaim 必须 true |
| may_writepage | anon=true / file=false | 文件页一般不写回（直接 drop cache） | 调 swappiness 时这是核心 |
| target_mem_cgroup | NULL / memcg 指针 | memcg 隔离的入口 | memcg 隔离时传入，root 时 NULL |

> **稳定性架构师视角**：scan_control 是 vmscan.c 的"指挥官"。任何对 reclaim 行为的疑问（为什么 kswapd 不 unmap？为什么 memcg reclaim 不写 swap？为什么 direct reclaim 卡 500ms？）都可以在 scan_control 的字段里找到答案。

### 3.3 try_to_free_pages() —— direct reclaim 入口

源码路径：mm/vmscan.c

try_to_free_pages() 是同步 reclaim 入口，被 __alloc_pages_direct_reclaim() 调用：

`c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
unsigned long try_to_free_pages(struct zonelist *zonelist, int order,
                                gfp_t gfp_mask, nodemask_t *nodemask)
{
    unsigned long nr_reclaimed;
    struct scan_control sc;

    /* 构造 scan_control */
    sc.gfp_mask = gfp_mask;
    sc.nr_to_reclaim = SWAP_CLUSTER_MAX;   /* 32 页 */
    sc.order = order;
    sc.priority = DEF_PRIORITY;             /* 12 */
    sc.may_writepage = !laptop_mode;        /* laptop_mode 下禁 IO */
    sc.may_unmap = !((gfp_mask & __GFP_RECLAIM_MASK) == __GFP_ATOMIC);
    /* 直接 reclaim 必须运行在 PF_MEMALLOC context */

    /* 设置 PF_MEMALLOC 标志 —— 绕过 memcg 限制 */
    current->flags |= PF_MEMALLOC;
    /* 设置 reclaim 上下文（让 alloc 知道现在在 reclaim 里） */
    set_task_reclaim_state(current, &sc.reclaim_state);

    /* 关键调用：进入 balance_pgdat 主循环 */
    nr_reclaimed = do_try_to_free_pages(zonelist, &sc);

    /* 清理 PF_MEMALLOC */
    current->flags &= ~PF_MEMALLOC;
    set_task_reclaim_state(current, NULL);
    return nr_reclaimed;
}
`

**关键不变量**：

- PF_MEMALLOC 标记让当前 alloc 绕过 memcg 限制（不再被 reject），但**也意味着这次 reclaim 的优先级极高**——其他 alloc 任务会被它抢占
- 
r_to_reclaim = SWAP_CLUSTER_MAX = 32，意味着 direct reclaim 每轮至少回收 32 页，否则退避到 priority 降低 / 进入 OOM 检查
- 直接 reclaim 是**有截止线的**——内核不能永远 reclaim 下去，必须在有限时间内返回；这是 try_to_free_pages 与 kswapd balance_pgdat 的关键差别

### 3.4 balance_pgdat() —— kswapd 主循环

源码路径：mm/vmscan.c

balance_pgdat() 是 kswapd 的核心，由 kswapd 内核线程调用，与 try_to_free_pages 同样调用 shrink_zones：

`c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
static unsigned long balance_pgdat(pg_data_t *pgdat, int order,
                                    int classzone_idx)
{
    /* kswapd 单次循环的最长时间限制 */
    unsigned long nr_reclaimed = 0;
    unsigned long nr_to_reclaim = SWAP_CLUSTER_MAX;  /* 32 */
    /* 优先级：从 DEF_PRIORITY=12 开始，逐轮降低 */
    int priority = DEF_PRIORITY;
    /* 失败计数：kswapd_failures 用于 boost priority */
    int failing_gfp_mask = 0;

    /* 主循环：直到 pgdat 平衡 或 优先级耗尽 */
    do {
        /* 关键：构造 scan_control */
        struct scan_control sc = {
            .gfp_mask = GFP_KERNEL,
            .order = order,
            .priority = priority,
            .may_unmap = 1,
            .may_writepage = 1,
            .nr_to_reclaim = nr_to_reclaim,
        };

        /* 本轮实际 reclaim */
        shrink_zones(zonelist, &sc);
        nr_reclaimed = sc.nr_reclaimed;

        /* ── 退出条件 ── */
        /* 条件 1: pgdat 已平衡 → 直接退出 */
        if (pgdat_balanced(pgdat, order, classzone_idx))
            break;

        /* 条件 2: priority 已到 0（最激进）→ 退出 */
        if (priority-- == 0)                  /* priority 自减 */
            break;

        /* 条件 3: failing_gfp_mask 累积 → 提示 boost */
        if (sc.nr_reclaimed < nr_to_reclaim && !sc.nr_writepages)
            failing_gfp_mask |= sc.gfp_mask;
        /* ... boost logic ... */
    } while (1);

    return nr_reclaimed;
}
`

**关键不变量**：

- kswapd 的 priority 是**逐轮递减**的：从 12 走到 0，最多 13 轮
- 退出条件是 pgdat_balanced（优先）或 priority 耗尽（兜底）
- failing_gfp_mask 累积机制：连续失败会触发 priority boost，把本轮 priority 抬高（更早退出）

> **稳定性架构师视角**：kswapd 的 priority 递减策略是一个**渐进式扫描**设计——先扫小范围（最便宜），不够再扫大范围（最贵）。这与 ART 的 GC 增量回收（incremental GC）思想一致。看到 pgscan_kswapd 高但 priority 持续为 0 → 系统在持续紧张，但 kswapd 没法抬到 high。

### 3.5 shrink_zones() —— zone 层遍历

源码路径：mm/vmscan.c

shrink_zones() 遍历 zonelist 上的每个 zone，对每个 zone 调用 shrink_lruvec：

`c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
static void shrink_zones(struct zonelist *zonelist, struct scan_control *sc)
{
    struct zoneref *z;
    struct zone *zone;
    unsigned long nr_reclaimed = 0;

    /* 遍历 zonelist 上的所有 zone（按 NUMA 距离） */
    for_each_zone_zonelist(zone, z, zonelist, sc->reclaim_idx) {
        /* memcg-aware 路径：如果是 memcg reclaim，lruvec 是 memcg 的 */
        struct lruvec *lruvec;

        if (sc->target_mem_cgroup) {
            /* memcg 隔离：拿到 memcg 在本 zone 的 lruvec */
            lruvec = mem_cgroup_lruvec(sc->target_mem_cgroup, zone);
        } else {
            /* 全局 reclaim：拿到 zone 的根 lruvec */
            lruvec = &zone->lruvec;
        }

        /* ── 关键调用 ── */
        while (true) {
            unsigned long nr_to_scan = SWAP_CLUSTER_MAX;
            unsigned long nr_reclaimed_in_lruvec;

            nr_reclaimed_in_lruvec = shrink_lruvec(lruvec, sc, nr_to_scan);
            if (nr_reclaimed_in_lruvec == 0)
                break;       /* 没扫到 page → 退出 */
            /* 否则继续扫直到本 zone 完成 */
        }
    }
}
`

**关键不变量**：

- memcg-aware 路径与全局路径**共用 shrink_lruvec**——区别只在于 lruvec 来源
- mem_cgroup_lruvec(memcg, zone) 是 memcg 隔离的核心（详见 §6）
- 
r_to_scan 是 per-lruvec 的"本轮扫描上限"，循环到 reclaim 为 0 才退出

### 3.6 shrink_lruvec() —— lruvec 层回收核心

源码路径：mm/vmscan.c

shrink_lruvec() 是整个回收路径的**核心入口**，在 5.10 引入 MGLRU 后**同时调度经典 LRU 与 MGLRU 两条路径**：

`c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
static unsigned long shrink_lruvec(struct lruvec *lruvec,
                                    struct scan_control *sc,
                                    unsigned long nr_to_scan)
{
    struct blk_plug plug;
    unsigned long nr_reclaimed = 0;
    enum lru_list lru;

    /* blk_plug：合并多次提交，避免重复 IO 调度 */
    blk_start_plug(&plug);

    /* ── 经典 LRU 路径：4 链表扫描 ── */
    if (!lru_gen_enabled(lruvec)) {        /* MGLRU 未启用 → 走经典 LRU */
        /* 按 LRU_INACTIVE_ANON → ACTIVE_ANON → INACTIVE_FILE → ACTIVE_FILE 顺序 */
        for_each_lru(lru) {
            enum lruvec_flock_flags flag = is_file_lru(lru) ? LRU_FILE : 0;
            /* shrink_list 内部调用 shrink_inactive_list + shrink_active_list */
            nr_reclaimed += shrink_list(lruvec, sc, lru, flag);
        }
    } else {
        /* ── MGLRU 路径（5.10 引入） ── */
        nr_reclaimed = lru_gen_scan_lruvec(lruvec, sc, nr_to_scan);
        /* MGLRU 内部使用 multigenerational LRU + set_mm_id */
    }

    blk_finish_plug(&plug);
    return nr_reclaimed;
}
`

> **稳定性架构师视角**：这是 v5.10 中最微妙的一处——lru_gen_enabled(lruvec) 的开关决定了**整个 LRU 算法**。默认是关闭的（需要 sysctl vm_lru_gen_aware=1 启用）。线上看到 pgscan_kswapd 突增但 priority 行为异常 → 检查 /proc/sys/vm/lru_gen_aware。

### 3.7 路径串讲：从 kswapd 唤醒到 page 回收的完整 trace

`
[kswapd0 内核线程被 wakeup_kswapd 唤醒]
        ↓
kswapd() (mm/vmscan.c)
        ↓
kswapd_try_to_sleep() 检查 order / classzone_idx
        ↓
balance_pgdat(pgdat, order, classzone_idx)
        ↓   for 循环 priority 12 → 0
shrink_zones(zonelist, &sc)
        ↓   for_each_zone
shrink_lruvec(lruvec, sc, nr_to_scan)
        ↓
shrink_list → shrink_inactive_list / shrink_active_list
        ↓
shrink_inactive_list → isolate_lru_page 拿 page 列表
        ↓
shrink_page_list
        ├─ try_to_unmap(page, &unmap_control)
        ├─ pageout(page, page_mapping(page), ...)  ← 写 swap / 写磁盘
        └─ list_add(page, &free_pages)             ← 释放回 buddy
        ↓
返回 sc.nr_reclaimed 累加
        ↓
回到 balance_pgdat 主循环
        ↓
pgdat_balanced? → 是 → kswapd_try_to_sleep → 重新阻塞
`

---

## 第 4 章 shrink_lruvec 三步走：scan → isolate → evict

### 4.1 三步走总览

shrink_inactive_list（inactive 路径）和 shrink_active_list（active 路径）共同构成了 LRU 扫描的"三步走"：

`
              ┌──────────────────────────────────────────────┐
              │             shrink_lruvec / shrink_list      │
              │                  (lruvec 层)                 │
              └──────────────────────┬───────────────────────┘
                                     │
            ┌────────────────────────┴─────────────────────────┐
            │                                                   │
    shrink_inactive_list                              shrink_active_list
    (回收 inactive 链)                                (在 inactive ↔ active 间搬)
            │                                                   │
            ▼                                                   ▼
    ┌───────────────────┐                              ┌─────────────────────┐
    │ Step 1: SCAN       │                              │ Step 1: SCAN         │
    │  从 inactive list  │                              │  从 active list      │
    │  拿 page           │                              │  拿 page             │
    │  + page_check_refs │                              │  + page_check_refs   │
    │  判定 cold/hot      │                              │  判定 hot/cold       │
    └─────────┬─────────┘                              └─────────┬───────────┘
              │                                                   │
              ▼                                                   ▼
    ┌───────────────────┐                              ┌─────────────────────┐
    │ Step 2: ISOLATE    │                              │ Step 2: MOVE         │
    │  __isolate_lru    │                              │  搬到 inactive list  │
    │  page 进入         │                              │  (deactivate)        │
    │  page_list         │                              └─────────────────────┘
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │ Step 3: EVICT      │
    │  shrink_page_list  │
    │  ├─ try_to_unmap   │
    │  ├─ pageout        │
    │  └─ release        │
    └───────────────────┘
`

**关键不变量**：

- SCAN 是"读"，ISOLATE 是"摘"，EVICT 是"清"
- SCAN 与 ISOLATE 之间夹了 page_check_references（核心的 hot/cold 判定）
- inactive 路径走"判定 → isolate → evict"；active 路径走"判定 → deactivate（搬回 inactive）→ 留给下一轮"

### 4.2 Step 1 SCAN：shrink_inactive_list 入口与 page_check_references

源码路径：mm/vmscan.c、mm/vmscan.c (page_check_references)

`c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
static noinline_for_stack void
shrink_inactive_list(unsigned long nr_to_scan, struct lruvec *lruvec,
                     struct scan_control *sc, enum lru_list lru)
{
    LIST_HEAD(page_list);   /* 暂存被 isolate 的 page */
    unsigned long nr_scanned = 0;
    unsigned long nr_reclaimed = 0;

    /* ── SCAN 阶段：从 LRU 链表尾部（最 cold）扫描 ── */
    spin_lock_irq(&lruvec->lru_lock);
    nr_scanned = isolate_lru_pages(nr_to_scan, lruvec, &page_list,
                                    &nr_scanned, sc, lru);
    /* isolate_lru_pages 内部调用 __isolate_lru_page 检查每个 page */
    /* 检查 PG_referenced / PG_reclaim / 映射数等 */
    spin_unlock_irq(&lruvec->lru_lock);

    if (unlikely(!nr_scanned)) return;

    /* ── Page 数量统计 ── */
    if (current_is_kswapd())
        __count_vm_events(KSWAPD_SCAN, nr_scanned);
    else
        __count_vm_events(PGSCAN_DIRECT, nr_scanned);

    /* ── Page 回收尝试 ── */
    nr_reclaimed = shrink_page_list(&page_list, sc);

    /* ── 处理未被 reclaim 的 page（放回 LRU） ── */
    putback_inactive_pages(lruvec, &page_list);

    sc->nr_reclaimed += nr_reclaimed;
    sc->nr_scanned += nr_scanned;
}
`

> **稳定性架构师视角**：注意 if (current_is_kswapd()) 这个分支——**内核通过判断"当前是不是 kswapd"来决定使用 KSWAPD_SCAN 还是 PGSCAN_DIRECT 计数**。这就是 /proc/vmstat 上 pgscan_kswapd 与 pgscan_direct 分开计数的源头。

#### 4.2.1 page_check_references：hot/cold 判定的核心

源码路径：mm/vmscan.c、include/linux/mm_inline.h

page_check_references 决定一个 mapped page 是否应该被回收：

`c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
static enum page_references
page_check_references(struct page *page, struct scan_control *sc)
{
    /* 检查 PG_referenced 位（vmscan 触发时是否被访问过） */
    int referenced_ptes, referenced_page;
    unsigned long vm_flags;
    struct page_references ret = { .page = 0, .pge = 0 };

    referenced_ptes = page_vma_mapped_walk(page, &vma_iter);   /* 走 VMA 查 PTE */
    /* 真实函数：page_vma_mapped_walk()（GKI 5.10 引入，统一了 anon/file 路径） */

    /* 关键决策树 */
    if (page_test_and_clear_referenced(page)) {
        /* 上轮 vmscan 后被访问过 → PG_referenced 标记 */
        if (referenced_ptes > 1)
            return PAGEREF_KEEP;        /* 多 VMA 引用 → 保留 */
        /* 单 VMA 引用 → 看 vma->vm_flags */
        vm_flags = vma_iter.vma->vm_flags;
        if (vm_flags & VM_EXEC)
            return PAGEREF_ACTIVATE;    /* 代码段 → 永久保留 */
        /* 普通 vma + 单次引用 → 进 inactive（不再 promote） */
    }

    /* 没被 PG_referenced 但 PTE 被访问过 → activate */
    if (referenced_ptes) {
        if (referenced_page)
            return PAGEREF_ACTIVATE;
        return PAGEREF_RECLAIM;         /* 真正的 cold page */
    }
    return PAGEREF_RECLAIM;
}
`

**关键不变量**：

- page_vma_mapped_walk()（GKI 5.10 引入）统一了 file/anon 的 PTE 扫描
- PG_referenced + PTE referenced 双层判定——避免短时抖动导致 cold 判定失败
- PAGEREF_KEEP / PAGEREF_ACTIVATE / PAGEREF_RECLAIM 三个返回值决定 page 命运

### 4.3 Step 2 ISOLATE：__isolate_lru_page 与 mem_cgroup_move_account

源码路径：mm/vmscan.c、mm/memcontrol.c

__isolate_lru_page 把 page 从 LRU 链表摘下来，准备 evict：

`c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
__isolate_lru_page(struct page *page, isolate_mode_t mode)
{
    /* 校验：不能是 PageReserved / PageCompound（hugepage 不走这个路径） */
    if (unlikely(!TestClearPageLRU(page)))
        return 0;

    /* memcg-aware：检查 memcg 限额（防止 reclaim 了一个不该 reclaim 的） */
    if (page_memcg(page) != page_memcg_rcu(page))
        return 0;

    /* 检查 PG_dirty：file 链可能需要 writepage */
    if (mode & ISOLATE_CLEAN && PageDirty(page))
        return 0;

    /* memcg 移动：把 page 从原 memcg 移到 target_mem_cgroup */
    if (mode & ISOLATE_UNMAPPED)
        mem_cgroup_move_account(page);

    return 1;
}
`

> **稳定性架构师视角**：mem_cgroup_move_account 是 memcg 隔离的关键——**当 reclaim 一个 page 时，它的 memcg 归属可能变化**。这避免了"reclaim 了 A cgroup 的 page，B cgroup 反而被 LMKD 杀掉"的逻辑错误。

### 4.4 Step 3 EVICT：shrink_page_list 三动作（try_to_unmap + pageout + release）

源码路径：mm/vmscan.c、mm/rmap.c、mm/swap.c

shrink_page_list 是 EVICT 的核心，做三件事：try_to_unmap（解除映射）、pageout（写 swap/disk）、list_add（释放回 buddy）：

`c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
static unsigned long shrink_page_list(struct list_head *page_list,
                                       struct scan_control *sc)
{
    LIST_HEAD(ret_pages);
    LIST_HEAD(free_pages);
    unsigned long nr_reclaimed = 0;

    while (!list_empty(page_list)) {
        struct page *page = lru_to_page(page_list);
        int page_ref_freeze;
        enum pageout_result pageout_result;

        /* 必须先 freeze 引用计数，避免 reclaim 时被并发修改 */
        if (!trylock_page(page))
            continue;       /* 锁不上 → 留给下一轮 */
        page_ref_freeze = page_ref_freeze(page, 1);   /* 拿额外引用 */
        list_del(&page->lru);

        /* ── 动作 1: try_to_unmap ── */
        if (page_mapped(page)) {
            /* 反向映射（rmap）：解除所有 PTE 映射 */
            if (!try_to_unmap(page, ttu_flags))
                goto activate_locked;  /* unmap 失败 → 放回 active */
        }

        /* ── 动作 2: pageout ── */
        if (PageDirty(page)) {
            if (sc->may_writepage &&
                (!PageAnon(page) || sc->may_swap)) {
                /* 文件脏页：writepage → 磁盘 */
                /* 匿名脏页：swap_writepage → zRAM/swap 设备 */
                pageout_result = pageout(page, mapping, sc);
                if (pageout_result == PAGE_OUT_FAIL)
                    goto activate_locked;
            } else {
                /* 不允许 writepage → 保留 dirty 状态 */
                goto keep_locked;
            }
        }

        /* ── 动作 3: release ── */
        /* 不是 dirty / dirty 已被 pageout → 释放 */
        if (!PageMapping(page) || (!PageDirty(page) && !PageWriteback(page))) {
            /* 解冻引用计数 + 释放到 buddy */
            page_ref_unfreeze(page, page_ref_freeze - 1);
            list_add(&page->lru, &free_pages);
            nr_reclaimed++;
            continue;
        }

keep_locked:
        page_ref_unfreeze(page, page_ref_freeze - 1);
        list_add(&page->lru, &ret_pages);

activate_locked:
        /* 不能 reclaim 的 page：放回 active 链 */
        if (!PageActive(page))
            SetPageActive(page);
        SetPageReferenced(page);
        list_add(&page->lru, &ret_pages);
        unlock_page(page);
    }

    /* ── 实际释放 free_pages ── */
    free_unref_page_list(&free_pages);
    /* 把 ret_pages 放回 LRU（active 或 inactive） */
    putback_inactive_pages(&ret_pages);
    return nr_reclaimed;
}
`

**关键不变量**：

- 顺序不可改：**先 unmap 后 pageout**——必须先断 PTE 才能安全写
- try_to_unmap 失败时放回 active 链（PAGEREF_ACTIVATE 路径），这是 cold page 被错误分类时的"安全网"
- pageout 失败的 page 也要放回 active 链——这是 IO 拥塞时防止 recycle 死循环的设计

#### 4.4.1 try_to_unmap 与反向映射（rmap）

源码路径：mm/rmap.c、include/linux/rmap.h、mm/memory.c

try_to_unmap 是反向映射（reverse mapping）的核心：一个物理 page 可能被多个 VMA 映射（共享库、fork 后父子进程共享），rmap 负责遍历所有 PTE 解除映射：

`c
/* mm/rmap.c —— GKI 5.10 真实函数（节选） */
int try_to_unmap(struct page *page, enum ttu_flags flags)
{
    /* 匿名页（anon vma） */
    if (PageAnon(page))
        return rmap_walk_anon(page, try_to_unmap_one, &data, false);
    /* 文件页（page cache） */
    else
        return rmap_walk_file(page, try_to_unmap_one, &data);
}
`

> **稳定性架构师视角**：rmap_walk_anon 与 rmap_walk_file 是 rmap 的两条主路径，**大文件映射（如 video buffer）可能在 rmap 阶段花 100ms+**——这是大页回收抖动的一个隐藏根因。看到 pgscan_direct 高 + try_to_unmap 调用栈 → 检查是否有大共享映射。

#### 4.4.2 pageout 与 swap 路径

源码路径：mm/page_io.c、mm/swap.c、drivers/block/zram/（zRAM）

匿名页的 pageout 走 swap_writepage → swap device I/O：

`c
/* mm/swap.c —— GKI 5.10 真实函数（节选） */
int pageout(struct page *page, struct address_space *mapping,
            struct scan_control *sc)
{
    /* 设置 PG_reclaim 标记（防止 race） */
    SetPageReclaim(page);
    /* 调用 mapping->a_ops->writepage —— 匿名页是 swap_writepage */
    return mapping->a_ops->writepage(page, &wbc);
}
`

zRAM 设备的 writepage 实际由 drivers/block/zram/zram_drv.c 实现，**压缩后写入 zRAM 内存区域**（详见 [08 §4.2](08-物理内存组织-Node,Zone,Page,memblock(GKI 5.10).md)）。

> **稳定性架构师视角**：zRAM 写满时 writepage 会被阻塞（compress 失败或后端 IO 卡），这会让 kswapd / direct reclaim 线程卡在 swap_writepage 上。看到 pgmajfault 突增 + zRAM I/O 100% → 系统在做大量 swapout，正在接近 IO 拥塞。

---


## 第 5 章 Direct Reclaim 路径：alloc_pages_slowpath 的回收分支

### 5.1 Direct Reclaim 是什么 / 为什么需要它

**定义**：Direct Reclaim 是**当 kswapd 来不及回收**（kswapd 失败 / 还没唤醒 / 目标水位没抬到 high）时，**当前 alloc 线程亲自 reclaim** 的同步路径。它的代价是 **alloc 线程被同步阻塞**，阻塞时长 100ms-1s。

**为什么需要它**：

- kswapd 跑在专属内核线程上，但内核线程**没有"加速权"**——它的优先级与普通内核任务相同
- 高阶分配（`order >= PAGE_ALLOC_COSTLY_ORDER`，即 `order >= 3`）即使 kswapd 在跑，也可能因为找不到连续页而失败——必须 alloc 线程亲自 reclaim + compact
- 关键路径（Input 事件、Surface 分配、binder 事务）允许走 reclaim 路径，但不能被它长期阻塞——这是 PF_MEMALLOC 标志设计的根源

### 5.2 __alloc_pages_direct_reclaim：direct reclaim 入口

源码路径：mm/page_alloc.c

__alloc_pages_direct_reclaim() 是 direct reclaim 的入口，被 __alloc_pages_slowpath() 调用（第 3 步，详见 [09 §4.8](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md)）：

`c
/* mm/page_alloc.c —— GKI 5.10 真实函数（节选） */
unsigned long __alloc_pages_direct_reclaim(gfp_t gfp_mask, unsigned int order,
                                            unsigned int alloc_flags,
                                            const struct alloc_context *ac,
                                            unsigned long *did_some_progress)
{
    struct scan_control sc = {
        .gfp_mask = gfp_mask,
        .order = order,
        .priority = DEF_PRIORITY,                    /* 12（最宽松开始） */
        .may_writepage = !laptop_mode,
        .may_unmap = !((gfp_mask & __GFP_RECLAIM_MASK) == __GFP_ATOMIC),
        .may_swap = 1,
    };
    struct page *page;
    unsigned long pflags;
    bool drained = false;

    /* 关键：设置 PF_MEMALLOC 标志 */
    pflags = memalloc_noreclaim_save();              /* 检查并保存 current->flags */
    /* ... 详细逻辑 ... */

    /* 设置 reclaim 上下文 */
    current->flags |= PF_MEMALLOC;                   /* 重要：绕过 memcg */
    set_task_reclaim_state(current, &sc.reclaim_state);

    /* ── 关键调用 ── */
    *did_some_progress = try_to_free_pages(ac->zonelist, order, gfp_mask,
                                             ac->nodemask);
    /* try_to_free_pages → balance_pgdat → shrink_zones → shrink_lruvec */

    /* 恢复 PF_MEMALLOC */
    current->flags &= ~PF_MEMALLOC;
    set_task_reclaim_state(current, NULL);
    memalloc_noreclaim_restore(pflags);

    /* 返回后 alloc 线程会重试 fast path */
    return *did_some_progress;
}
`

**关键不变量**：

- PF_MEMALLOC 是**direct reclaim 的特权标志**：当前 alloc 绕过 memcg 限额（即使 cgroup 已经 reject 了，也能继续 alloc）
- 这个特权是有代价的：**持有 PF_MEMALLOC 时，alloc 路径不被 memcg 限制**——如果一个 memcg 进程卡在 reclaim 里持续持有 PF_MEMALLOC，可能压制其他 cgroup 的 alloc
- Direct Reclaim 不是"无限 reclaim"——它有 did_some_progress 反馈，如果没扫到 page，会退避到 OOM 检查

### 5.3 Direct Reclaim 的代价：4 个量化指标

源码路径：/proc/vmstat、ftrace mm_vmscan_*、include/trace/events/mm_vmscan.h

| 量化指标 | 采样入口 | 阈值（经验） | 关联问题 |
|---------|---------|-------------|---------|
| **direct reclaim 时长** | ftrace mm_vmscan_direct_reclaim_begin/end | > 100ms 触发 | Input 卡顿 / Surface 卡顿 |
| **pgscan_direct 突增** | /proc/vmstat | > 10000/sec | Direct Reclaim 抖动 |
| **shrink_inactive_list 调用频率** | ftrace mm_vmscan_shrink_inactive_list | > 1000/sec | LRU 抖动 |
| **匿名页 swapout 速率** | /proc/vmstat pswpin / pswpout | > 1000/sec | zRAM 拥塞 / IO 拥塞 |

> **稳定性架构师视角**：Direct Reclaim 的代价**与 reclaim 的 page 数成正比**。如果 reclaim 了 32 page 但每个 page 的 try_to_unmap 都遍历 100 个 VMA → 单轮 reclaim 1-10ms。如果 reclaim 了 1000 page（高 priority 0 模式）→ 单轮 100ms+。**这是 Android 卡顿的核心数据**。

### 5.4 Direct Reclaim 与 alloc 的死锁防护：nofail / memalloc_noio

源码路径：mm/page_alloc.c、include/linux/sched/mm.h

Direct Reclaim 在某些场景下需要"禁 IO"（不能进 swap / 写磁盘）以避免死锁：

`c
/* include/linux/sched/mm.h —— GKI 5.10 真实宏 */
#define memalloc_noio_save()   \
        (current->flags |= PF_MEMALLOC_NOIO)
#define memalloc_noio_restore(flags)  \
        (current->flags = (current->flags & ~PF_MEMALLOC_NOIO) | (flags & PF_MEMALLOC_NOIO))
`

**哪些场景需要 noio**：

| 场景 | noio / nowait 标志 | 原因 |
|------|-------------------|------|
| FS 层 reclaim（写回数据） | PF_MEMALLOC_NOFS | 防止 reclaim 进 FS 又触发 FS 操作 |
| IO 子系统 reclaim（swap out） | PF_MEMALLOC_NOIO | 防止 reclaim 进 IO 又触发 IO 操作 |
| Binder 事务 reclaim | 默认 noio | binder 必须立即返回 |
| Swap 设备的 reclaim | **never**（必须能 IO） | 否则 swap 写不出去 |

> **稳定性架构师视角**：内核用 PF_MEMALLOC 系列标志**精确保护了关键路径不会因为 reclaim 阻塞**。binder/Input 走 noio 路径 → 即使 kswapd 卡在 swap_writepage，binder 线程也能返回。这是一组**反向设计**——看似限制能力，实际是减少总抖动。

---

## 第 6 章 memcg 隔离：mem_cgroup_iter / soft_limit / tree_update_root

### 6.1 memcg 隔离为什么需要它

**定义**：memcg（memory cgroup）是 Linux 内核的"内存配额"机制，每个 cgroup 有独立的内存限额（memory.max、memory.high、memory.soft_limit）。当某个 memcg 接近限额时，**内核只 reclaim 该 memcg 下的 page**，不会"杀错"其他 cgroup。

**为什么需要它**：

- 全局 reclaim（kswapd 默认路径）会扫描全 zone 的 LRU，可能 reclaim 一个 cgroup 的 page 给另一个 cgroup 用——这是"邻居借用"
- 邻居借用在 mobile 场景下危险：前台 app 占用了大量 page cache，被后台 app 的 malloc 触发 kswapd → kswapd reclaim 前台 app 的 page cache → 前台 app 卡顿
- memcg 隔离解决了这个问题：reclaim 只在限额 cgroup 内进行

### 6.2 memcg-aware 回收的入口：mem_cgroup_lruvec 与 mem_cgroup_iter

源码路径：mm/memcontrol.c、mm/vmscan.c、include/linux/memcontrol.h

`c
/* mm/memcontrol.h —— GKI 5.10 真实内联函数 */
static inline struct lruvec *mem_cgroup_lruvec(struct mem_cgroup *memcg,
                                                struct zone *zone)
{
    /* mem_cgroup_per_node 是 memcg 在每个 NUMA node 上的私有数据 */
    struct mem_cgroup_per_node *mz;
    mz = memcg->nodeinfo[zone_to_nid(zone)];
    /* 返回 memcg 在该 zone 的私有 lruvec */
    return &mz->lruvec;
}
`

**关键不变量**：

- 每个 memcg 在每个 NUMA node 上有自己的 lruvec——这意味着 memcg 隔离是 **per-node** 的，不是全局的
- lruvec 包含 4 个链表（inactive_anon / active_anon / inactive_file / active_file）——所以 memcg 隔离在 LRU 层就生效
- global reclaim 时 sc->target_mem_cgroup = NULL，memcg reclaim 时 sc->target_mem_cgroup = root_memcg（递归路径）

### 6.3 mem_cgroup_iter：memcg 之间的 reclaim 路径

源码路径：mm/memcontrol.c

mem_cgroup_iter() 决定"reclaim 谁"——它按 memcg 树的层级从下往上找：

`c
/* mm/memcontrol.c —— GKI 5.10 真实函数（节选） */
struct mem_cgroup *mem_cgroup_iter(struct mem_cgroup *root,
                                   struct mem_cgroup *prev,
                                   struct mem_cgroup_walk_param *params)
{
    /* 树遍历：从 prev 向上找下一个 under-limit memcg */
    while (1) {
        struct mem_cgroup *next;
        /* 计算 memcg 的内存压力（in_use / max） */
        /* 优先 reclaim in_use > 90% 的 memcg */
        /* tree_update_root 用于刷新 max/min 限制 */
        ...
    }
}
`

> **稳定性架构师视角**：mem_cgroup_iter 在 balance_pgdat 的 memcg 路径里被调用，决定 **"reclaim 这个 memcg 还是另一个"**。这个机制是 memcg-aware LMKD 的底层——LMKD 的 kill 决策其实在 memcg 树遍历里"暗示"过：哪个 memcg 压力大就先 reclaim 哪个。

### 6.4 mem_cgroup_soft_limit_check：soft_limit 命中触发

源码路径：mm/memcontrol.c

soft_limit 是 memcg 的"软上限"——超过 soft_limit 时**不立即杀进程**，而是触发 memcg 路径的 reclaim：

`c
/* mm/memcontrol.c —— GKI 5.10 真实函数（节选） */
void mem_cgroup_soft_limit_check(struct mem_cgroup *memcg)
{
    /* 检查是否超过 soft_limit */
    if (memcg->memory.soft_limit > memcg->memory.usage)
        return;

    /* 超过 soft_limit：触发 tree_update_root */
    if (atomic_read(&memcg->memory.soft_lock) > 0)
        return;     /* 已有 reclaim 在跑 */

    atomic_inc(&memcg->memory.soft_lock);
    memcg->memory.soft_lock_jiffies = jiffies;

    /* 关键：调用 tree_update_root(memcg) 触发 memcg-aware reclaim */
    tree_update_root(memcg);
    /* tree_update_root 会调用 mem_cgroup_reclaim() → shrink_lruvec(memcg) */
}
`

**关键不变量**：

- soft_limit 不是"硬 quota"——它**只是触发更激进的 reclaim**
- memcg-aware reclaim 的 lruvec 是 memcg 的，不是 zone 的——所以 reclaim 只影响该 memcg
- soft_limit 命中与 [07 §3.3](07-PSI、vmpressure、memcg 压力传递.md) 的 mem_cgroup_pressure(LOW) 事件是串联触发的

### 6.5 memcg-aware reclaim 的完整链路

`
[memcg soft_limit 命中]
    ↓
mem_cgroup_soft_limit_check(memcg)
    ↓
tree_update_root(memcg)        ← 触发 memcg 路径的 reclaim
    ↓
mem_cgroup_reclaim(memcg, ...)
    ↓
构造 scan_control (sc.target_mem_cgroup = memcg)
    ↓
shrink_zones(zonelist, &sc) → mem_cgroup_lruvec(memcg, zone)
    ↓
shrink_lruvec(memcg_lruvec, &sc, nr_to_scan)
    ↓
shrink_list → ... → shrink_page_list
    ↓
返回 nr_reclaimed
`

> **稳定性架构师视角**：这是 [06 LMKD](06-LMKD 用户态内存杀手.md) 的"内核侧同构体"——LMKD 在用户态做 kill 决策，内核在 memcg 层做 reclaim 决策。两者**目标一致**：减少 cgroup 的内存占用。区别是**LMKD 是"事后强制"（kill 进程），内核 reclaim 是"事前温和"（reclaim page）**。

### 6.6 memcg reclaim 的限制：3 个边界条件

| 限制 | 含义 | 触发后果 |
|------|------|---------|
| **memcg max 限额** | memory.max 之外 → write OOM kill | LMKD 接管 |
| **memcg 不收 swap** | memcg 限额到 → 触发 mem_cgroup_pressure(CRITICAL) | LMKD kill |
| **root memcg 与全局 LRU** | root memcg 的 lruvec 是 zone 的根 lruvec | 等同全局 reclaim |

---

## 第 7 章 MGLRU（5.10 新）：多代 LRU

> **注**：本节为新增章节。MGLRU 在 GKI 5.10 引入（GKI 5.15 主流化），实验性，默认 vm.lru_gen_aware=0。本节只讲核心数据结构与切换逻辑，不深入工程细节。

### 7.1 MGLRU 为什么需要它

**经典 LRU 的 5 个核心痛点**：

1. **scan overhead 高**：每次 reclaim 全链表扫描，4 链表 × 全部 page，CPU 成本 O(zone_size)
2. **cold/hot 判定不准**：单一 PG_referenced 位，无法区分"短时抖动"与"真实复用"
3. **没有代的概念**：所有 page 同等权重，2 次访问 vs 200 次访问等价
4. **swap 抖动大**：匿名页一旦 inactive 就可能 swapout，refault 后又 swapin
5. **工作集识别慢**：长进程的工作集变化时，LRU 需要多轮才能识别

**MGLRU（Multigenerational LRU）的设计动机**：

- **代（generation）**：把 page 按"上次访问时间"分代，young page 是新访问，old page 是很久没访问
- **代切换（gen 0 → gen 1）**：超过 TTL（vm.lru_gen_min_ttl_ms）没访问的 page 升代到 gen 1
- **mark-multiple**：每次访问标记多个 page（不只 mark 1 个），减少"短时抖动误判"
- **set_mm_id**：per-mm walk，每个进程独立判断工作集

### 7.2 MGLRU 的数据结构：struct lru_gen_struct

源码路径：include/linux/mm_inline.h、mm/mglru.c（AOSP 14 部分内核版本也叫 mm/lru_gen.c）

`c
/* include/linux/mm_inline.h —— GKI 5.10 真实结构（节选） */
struct lru_gen_struct {
    /* 全局代序列号：每代切换时自增 */
    unsigned long max_seq;                 /* 当前最大代序号 */
    unsigned long min_seq[ANON_AND_FILE];  /* anon/file 各自的最小代 */
    /* 关键：每代 page 数量 */
    unsigned long nr_pages[MAX_NR_GENS][ANON_AND_FILE][LRU_MAX]; /* [gen][type][lru] */
    /* 标记位：标记是否已 scan 过 */
    unsigned long flags;                   /* BIT(LRU_GEN_CORE) 等 */
    /* evictable 计数 */
    unsigned long avg_refaulted[MAX_NR_GENS][ANON_AND_FILE];
    /* 工作集大小 */
    unsigned long avg_total[MAX_NR_GENS][ANON_AND_FILE];
    /* 压缩比（用于代切换决策） */
    unsigned long compressed[MAX_NR_GENS][ANON_AND_FILE];
};
`

**关键不变量**：

- max_seq 是代序号，从 1 开始递增；超过 MAX_NR_GENS（默认 4）时回绕
- 
r_pages[gen][type][lru] 三维数组——这是 MGLRU 的"代 × 类型 × LRU"分类
- avg_refaulted / avg_total 记录 refault 率，决定代切换时是否 promote / demote

### 7.3 MGLRU 与经典 LRU 的共存：lru_gen_enabled

源码路径：mm/vmscan.c（shrink_lruvec 内部）

`c
/* mm/vmscan.c —— GKI 5.10 真实函数（节选） */
static bool lru_gen_enabled(void)
{
    /* sysctl vvm.lru_gen_aware=1 启用 */
    return READ_ONCE(lru_gen_aware) > 0;
}

static unsigned long shrink_lruvec(struct lruvec *lruvec,
                                    struct scan_control *sc,
                                    unsigned long nr_to_scan)
{
    /* ── 关键分支 ── */
    if (lru_gen_enabled()) {
        /* MGLRU 路径 */
        return lru_gen_scan_lruvec(lruvec, sc, nr_to_scan);
    } else {
        /* 经典 LRU 路径（4 链表） */
        for_each_lru(lru) {
            ...
        }
    }
}
`

> **稳定性架构师视角**：这是 GKI 5.10 的关键实验开关。**默认关闭**，但 AOSP 14 在 Pixel 上开启了部分 cgroup（vm.lru_gen_aware=1 在 foreground cgroup）。看到 /proc/vmstat 中 lru_gen_* 系列计数器 → MGLRU 启用。

### 7.4 代切换：try_to_inc_max_seq 与 inc_min_seq

源码路径：mm/mglru.c

`c
/* mm/mglru.c —— GKI 5.10 真实函数（节选） */
static void try_to_inc_max_seq(struct lruvec *lruvec, unsigned long max_seq,
                                struct scan_control *sc, bool swappiness)
{
    /* gen 0 page 全部驱逐后，max_seq++，gen 0 → gen 1 */
    /* inc_min_seq：清理最小代（过老的 page） */
    inc_min_seq(lruvec, max_seq - 1, ANON);
    inc_min_seq(lruvec, max_seq - 1, FILE);
    /* ... */
}
`

**关键不变量**：

- 代切换是**全局的**（对所有 lruvec 生效），不是 per-memcg 的
- 代切换时，老代的 page 直接 evict（不再 promote）
- try_to_inc_max_seq 是 lru_gen_scan_lruvec 的退出条件之一——代切换意味着本轮扫描完成
- 配套的状态变更函数：lru_gen_scan_around()（per-VMA 扫描，与 lru_gen_look_around 配对）、lru_gen_change_state()（保护状态切换的临界区，避免多核 race）

### 7.5 lru_gen_look_around 与 set_mm_id：per-mm walk

源码路径：mm/mglru.c

lru_gen_look_around() 是 MGLRU 的"预热"机制——扫描一个 page 时，把它周围的 page（同一 VMA）也标 mark-multiple：

`c
/* mm/mglru.c —— GKI 5.10 真实函数（节选） */
void lru_gen_look_around(struct page_vma_mapped_walk *pvmw,
                          struct lru_gen_mm_walk *mm_walk)
{
    /* 看当前 page 周围的 page（同一 VMA） */
    for (i = 0; i < LOOK_AROUND_SIZE; i++) {
        /* 把周围 page 也标记为 PG_referenced */
        SetPageReferenced(page);
    }
    /* set_mm_id: 记录这是哪个 mm 的 walk */
    mm_walk->set_mm_id = true;
}
`

> **稳定性架构师视角**：look_around 的设计哲学：**识别工作集不需要精确**——只需要"附近有访问大概率就是工作集的一部分"。这是 MGLRU 用 CPU 换内存的经典 trade-off。

### 7.6 MGLRU 的关键 sysctl

| sysctl | 默认 | 含义 | AOSP 14 实际值 |
|--------|------|------|--------------|
| vm.lru_gen_aware | 0 | 全局开关（0=关, 1=开） | Pixel 6+ = 1 |
| vm.lru_gen_min_ttl_ms | 0 | 最小 TTL（ms） | 5.18+ 引入，5.10 默认 0 |
| vm.lru_gen_enabled | 0 | 5.15+ 替代 lru_gen_aware 的开关 | 5.10 上不可用 |
| vm.lru_gen_must_look_around | 0 | 强制 look_around（调试用） | 默认 0 |
| vm.page-cluster | 0 | SWAP_CLUSTER_MAX 倍数（0=32，1=64） | 默认 0 |
| vm.zone_reclaim_mode | 0 | zone 内回收激进度（位掩码：1=跳过 DMA, 2=独占, 4=应用 page cache） | 默认 0 |
| vm.dirty_* | various | dirty page 比例（详见 [09 §6](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md)） | 内核默认 |
| vm.watermark_scale_factor | 10 | watermark 全局缩放（详见 [08 §6](08-物理内存组织-Node,Zone,Page,memblock(GKI 5.10).md)） | 默认 10 |

---

## 第 8 章 总结：架构师 Takeaway

### 8.1 五条调优经验

**Takeaway 1：watermark 是全局视野，memcg 是局部视野**——看到 pgscan_kswapd 高 → watermark 路径在工作；看到 mp_event vmpressure → memcg 路径。**两者串联，不是并联**。调 watermark 不要看 memcg，调 memcg 不要看 watermark。

**Takeaway 2：Direct Reclaim 是卡顿之源**——pgscan_direct 每秒 > 10000 + alloc 线程 STW > 100ms → 这是 Android 卡顿的核心数据。治理方向：**减少 alloc 线程进 slow path**（调 watermark、增大 cache、用 memcg 隔离前台），不是加快 reclaim。

**Takeaway 3：MGLRU 是实验性的，不要在线上默认开启**——vm.lru_gen_aware=1 在 Pixel 6+ 是开，但其他 OEM 的内核可能不稳定。建议**先在测试机开，观察 pgscan_kswapd 是否下降 + pgmajfault 是否下降**——两个指标同时下降才有意义。

**Takeaway 4：memcg 隔离的本质是"保护前台不被后台 kill"**——memory.max / memory.high 的真正作用是**隔离前台 app 与后台 app 的内存**，不是节省内存。误用 memcg（如给前台 cgroup 太小）反而会让前台被 LMKD kill。

**Takeaway 5：回收抖动看 vmstat / PSI 双指标**——pgscan_direct 高 → LRU 扫描频繁；/proc/pressure/memory full avg10 > 5% → reclaim 阻塞了 alloc 线程。两者同时高 → 系统处于"持续抖动"状态，必须治理。

### 8.2 排查路径速查

`
现象：App 卡顿 / ANR / 慢
    ↓
检查 /proc/pressure/memory full avg10 > 5%？
    ├─ 是 → Direct Reclaim 阻塞
    │       ├─ 检查 /proc/vmstat pgscan_direct 计数
    │       ├─ 检查 ftrace mm_vmscan_shrink_inactive_list 时长
    │       └─ 检查 ftrace mm_vmscan_direct_reclaim_begin/end 时长
    └─ 否 → 检查 PSI some avg10（CPU 调度问题）

现象：整机卡顿 / 后台 app 被 kill
    ↓
检查 mp_event vmpressure 事件计数？
    ├─ 是 → memcg-aware LMKD 在工作
    │       ├─ 检查 /proc/<pid>/cgroup 确认 cgroup 归属
    │       ├─ 检查 memory.max / memory.high 配置
    │       └─ 检查 dumpsys meminfo TopN 内存占用
    └─ 否 → 检查 vmpressure 旧路径（ro.lmk.use_psi=false）

现象：内存泄漏
    ↓
检查 pswpin / pswpout 计数
    ├─ 高 → swap 拥塞（zRAM 满或 IO 卡）
    └─ 低 → 检查 refault 计数（workingset 是否漂移）
`

---

## 附录 A：核心源码路径索引

| 文件名 | 完整路径 | 说明 |
|--------|---------|------|
| mm/vmscan.c | mm/vmscan.c | 回收路径主干 |
| mm/page_alloc.c | mm/page_alloc.c | alloc 路径 + direct reclaim 入口 |
| mm/mglru.c | mm/mglru.c（5.10+ 引入，5.15+ 主流化） | MGLRU 主实现 |
| include/linux/mmzone.h | include/linux/mmzone.h | struct pglist_data / struct zone |
| include/linux/swap.h | include/linux/swap.h | struct scan_control / struct reclaim_state |
| include/linux/mm_types.h | include/linux/mm_types.h | struct lruvec / struct page |
| include/linux/mm_inline.h | include/linux/mm_inline.h | MGLRU 内联辅助 |
| mm/memcontrol.c | mm/memcontrol.c | memcg 限额 / soft_limit / tree_update_root |
| mm/rmap.c | mm/rmap.c | 反向映射（try_to_unmap） |
| mm/swap.c | mm/swap.c | swap_writepage / pageout |
| mm/page_io.c | mm/page_io.c | swap IO 处理 |
| include/linux/memcontrol.h | include/linux/memcontrol.h | mem_cgroup_lruvec / mem_cgroup_iter |
| include/trace/events/mm_vmscan.h | include/trace/events/mm_vmscan.h | vmscan ftrace 事件 |
| Documentation/admin-guide/sysctl/vm.rst | Documentation/admin-guide/sysctl/vm.rst | vm sysctl 文档 |

---

## 附录 B：关键 commit 历史

| commit | 引入版本 | 影响范围 | 说明 |
|--------|---------|---------|------|
| e7bc9b58e3ac | 5.10 mainline | MGLRU 引入 | "Multigenerational LRU: software walk" |
| a9309e22d45a | 5.10 mainline | MGLRU 引入 | MGLRU 配合 evictable page 计数 |
| f2ac948a5320 | 5.10 mainline | MGLRU 引入 | lru_gen_struct + set_mm_id |
| f1edd690b96f | 5.15 mainline | MGLRU 主流化 | vm.lru_gen_enabled 替代 vm.lru_gen_aware |
| a5283d9774b0 | 5.18 mainline | MGLRU TTL | vm.lru_gen_min_ttl_ms |
| commit 38b30e4c089b | 4.20 mainline | PSI | PSI 引入（[07 衔接]） |
| commit 1e98794eaaa5 | 5.4 mainline | watermark 调整 | vm.watermark_scale_factor 默认 10 |
| commit 5e9d06e2a07d | 5.10 mainline | GKI 5.10 baseline | android14-5.10 分支建立 |

> **AOSP 14 关联 commit**：aosp/android14-5.10 在 MGLRU 基础上叠加了 vendor 定制（如 Qualcomm memshare、memreuse 扩展），但**内核主体仍来自 mainline 5.10**。

---

## 附录 C：风险速查矩阵

| 风险类型 | 现象 | 日志关键字 | 排查入口 | 关联章节 |
|---------|------|----------|---------|---------|
| **Direct Reclaim 抖动** | 分配阻塞 100ms-1s | __alloc_pages_slowpath、__alloc_pages_direct_reclaim、shrink_inactive_list | /proc/vmstat pgscan_direct | §5.3 |
| **kswapd 卡死** | kswapd 持续 running，pgscan_kswapd 突增 | pgscan_kswapd、pgsteal_kswapd | ftrace mm_vmscan_kswapd_* | §2.4 |
| **LRU 链表倾斜** | 单链表占满，其他链表空闲 | 
r_inactive_anon / 
r_active_file 异常 | /proc/vmstat per-LRU 计数 | §3.6 |
| **refault 风暴** | workingset 漂移，cache 命中率下降 | workingset_refault / workingset_activate | ftrace mm_workingset_* | §4.2 |
| **swap 拥塞** | zRAM 满或 IO 卡 | pswpin / pswpout 突增 | /proc/vmstat + iostat | §4.4 |
| **memcg 限额杀** | cgroup 内进程被 LMKD kill | Killed by LMK + cgroup 字段 | dumpsys lmkd + dumpsys meminfo --proto | §6.6 |
| **MGLRU 切换异常** | pgscan_kswapd 行为异常 | lru_gen_* 计数器 | /proc/vmstat + sysctl vvm.lru_gen_aware | §7.6 |
| **kswapd fail 累计** | priority boost 持续 | kswapd_failures 高 | /proc/zoneinfo + ftrace | §2.3 |

---

## 附录 D：跨篇引用汇总

| 关联主题 | 引用文章 | 关联点 |
|---------|---------|--------|
| 全局视野：一个 byte 的旅程 | [01-内存系统总览](01-内存系统总览：从进程视角到硬件的完整链路.md) §4 | 解释 page 在内存系统中的整体流动 |
| VMA 与 PTE 视角 | [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md) §3 | try_to_unmap 解除 VMA 映射的来源 |
| ART GC 与 reclaim 协作 | [03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md) §6 | ART 触发 mem_cgroup_pressure(LOW) |
| AMS 进程治理 | [05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md) §2 | oom_score_adj 与 LMKD 协作 |
| LMKD 用户态杀手 | [06-LMKD 用户态内存杀手](06-LMKD 用户态内存杀手.md) §3 | mp_event_vmpressure 是 memcg 路径终点 |
| PSI 与 memcg 压力传递 | [07-PSI、vmpressure、memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md) §3 | mem_cgroup_pressure 钩子 |
| 物理内存组织 | [08-物理内存组织](08-物理内存组织-Node,Zone,Page,memblock(GKI 5.10).md) §6 | watermark 三档与 zone 关系 |
| 页分配器慢路径 | [09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md) §4 | direct reclaim 在 slow path 的位置 |
| SLAB 视角 | [10-SLAB / SLUB 分配器](10-SLAB,SLUB 分配器与小对象分配(GKI 5.10).md) §5 | reclaim 对 kmem_cache 的影响（slab 回收） |
| 风险地图汇总 | [12-内存稳定性风险全景](12-内存稳定性风险全景.md) §5 | Direct Reclaim / swap 抖动归口 |

---

**下一篇**：[12-内存稳定性风险全景](12-内存稳定性风险全景.md) 将把本章 Direct Reclaim 抖动 / swap 抖动 / kswapd 卡死 / memcg 误杀 / MGLRU 切换异常等 8 类风险收口到五大类稳定性问题（OOM / 泄漏 / 抖动 / 杀进程 / 卡顿）里，给出跨篇速查表与排查流程图。
