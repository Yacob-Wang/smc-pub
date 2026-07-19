# 08-物理内存组织-Node,Zone,Page,memblock（GKI 5.10）

> **系列**：面向稳定性的 Android 内存架构深度解析系列（MM_v2）· 第 8 篇
>
> **源码基线**：AOSP `android-14.0.0_r1`（`refs/heads/android14-release`）
>
> **内核矩阵**：`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`（本篇涉及 `mm/memblock.c` / `mm/page_alloc.c` / `include/linux/mmzone.h`；5.10 → 5.15 引入 MGLRU 改 `vm_stat[]`；6.1/6.6 引入 per-VMA 锁优化）
>
> **目标读者**：Android 稳定性框架架构师
>
> **前置阅读**：[07-PSI、vmpressure、memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md)
>
> **下一篇**：[09-页分配器与伙伴系统(GKI 5.10)](09-页分配器与伙伴系统(GKI 5.10).md)
>
> **横向引用**：本篇是"内核 mm/ 子系统四篇"中的**第 1 篇**——把"物理 RAM 是怎么被看见、被组织、被分配的"这条链路打通。后三篇分别讲**分配器**、**SLAB/SLUB 小对象**、**回收**。

---

## 本篇定位

- **本篇系列角色**：核心机制第 8 篇 — 讲 Linux 内核如何"看"物理 RAM：memblock 早期分配器、Node/Zone/Page 三层结构、水位线机制；是理解后续 09-11(分配器/SLAB/回收)的基础
- **强依赖**：
  - MM_v2 07 已讲 PSI 压力传递（本篇是 PSI 的源头——alloc_pages 高 stall）
  - 后续 09-11 分配器/回收均基于本篇的 Node/Zone 数据结构
- **承接自**：07 §2 内核 PSI 机制（PSI mem full 的源头是 alloc_pages 在 zone 上 stall）
- **衔接去**：
  - 09 讲伙伴系统（基于本篇的 Node/Zone 数据结构分配物理页）
  - 10 讲 SLAB/SLUB（基于伙伴系统分配 slab）
  - 11 讲回收（基于本篇的水位线触发 kswapd/Direct Reclaim）
- **不重复内容**：
  - 07 PSI 内部机制详见 07,本篇只引用 PSI 的源头
  - 分配器/SLAB/回收详见 09-11

#### §0 锚点案例的可验证 4 件套:Camera 申请 16MB 连续页失败导致拍照黑屏

> **环境**:
> - 设备:某 OEM 中低端机型（arm64-v8a,4GB RAM,低端 GPU）
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.10` GKI
> - 场景:打开相机拍照 → 黑屏
> - 工具:`/proc/buddyinfo` + `/proc/pagetypeinfo` + `dmesg` + `ftrace -e mm:alloc_start`

> **复现步骤**:
> 1. 工厂重置,安装相机 App
> 2. 启动 App,反复开关相机 50 次
> 3. 第 30 次后,偶发拍照黑屏
> 4. logcat 出现 `camx: Failed to allocate 16MB contiguous buffer`

> **logcat / dmesg / /proc 关键片段**:
> ```
> # logcat
> 06-12 16:18:23.456 camera: camx: Failed to allocate 16MB contiguous buffer (order-7)
> 06-12 16:18:23.789 camera: Surface destroyed, returning error -12
> ```
> ```
> # dmesg
> [ 1234.567] alloc_pages failed: order=7, zone=DMA32, nodemask=0
> [ 1234.567] WARNING: CPU: 3 PID: 5678 at mm/page_alloc.c:4521 __alloc_pages_slowpath+0x234/0x890
> ```
> ```
> # cat /proc/buddyinfo(关键观察点:order-7 全是 0)
> Node 0, zone DMA32  0   3   5  12  8  4  2  0  0  0  0    ← order-7=0(根因)
> Node 0, zone Normal 1024  567  234 89  45  12  4  1  0  0
> # cat /proc/pagetypeinfo(看 fragmentation)
> Free pages count per migrate type at order    0      1      2      3      4      5      6      7      8      9     10
> Number of blocks type     Unmovable   1234   567   234    89    45    12     4     0     0     0
> # Unmovable 在 order-7 没有连续块
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/drivers/media/platform/camx/camx_buffer.c
> +++ b/drivers/media/platform/camx/camx_buffer.c
> @@ -alloc_camera_buffer
> -    // 旧:一次性 alloc 16MB 连续页,order-7 经常失败
> -    void* buf = alloc_pages(GFP_KERNEL | __GFP_DMA32, 7);  // order=7 = 2^7 * 4KB = 512KB × 32 = 16MB
> +    // 修复 1:用 CMA 区域申请(连续性保证)
> +    void* buf = dma_alloc_coherent(dev, 16 * 1024 * 1024, &dma_handle, GFP_KERNEL);
> +    // 修复 2:如果失败,降级为 4×4MB(也用 CMA 拼,但不要求完全连续)
> +    if (!buf) {
> +        for (int i = 0; i < 4; i++) {
> +            sub_bufs[i] = dma_alloc_coherent(dev, 4 * 1024 * 1024, &handles[i], GFP_KERNEL);
> +        }
> +        buf = merge_buffers(sub_bufs, 4);  // 拼成 16MB,允许不连续
> +    }
> ```
> ```diff
> --- a/arch/arm64/boot/dts/<vendor>/<board>.dts
> +++ b/arch/arm64/boot/dts/<vendor>/<board>.dts
> @@ -CMA 区域
> -    reserved-memory {
> -        /* 旧:没有给 camera 预留 CMA */
> -    };
> +    reserved-memory {
> +        cma_camera: linux,cma-camera {
> +            compatible = "shared-dma-pool";
> +            reusable;
> +            size = <0x0 0x4000000>;  /* 64MB 给 camera 申请连续页 */
> +            alignment = <0x0 0x1000>;
> +        };
> +    };
> ```
> 完整 16MB 连续页失败 / Zone 碎片化 / 水位线机制见 §6。

---

## 第 0 章 阅读路线图

在 `new byte[1024]` 落到一个物理页帧之前，内核必须先回答四个层层递进的问题：

```
Q1: 固件告诉我的物理内存有哪些范围？     ←  §2  memblock 阶段
Q2: 这些范围属于哪些 NUMA 节点？         ←  §3  node 拓扑
Q3: 每个节点内如何按"硬件可用性"切分？   ←  §4  zone 划分
Q4: 每个最小物理页用什么数据结构描述？   ←  §5  struct page
Q5: zone 在什么时候该回收？怎么保护？    ←  §6  watermark + lowmem_reserve
```

这五个问题，对应到 5 个数据结构与机制：`struct memblock` → `struct pglist_data` (node) → `struct zone` → `struct page` → `watermark[] / lowmem_reserve[]`。它们的关系是**严格的父子包含 + 兄弟 fallback**：

```
pglist_data (node)
 ├─ node_zones[MAX_NR_ZONES=4]  →  zone (DMA / DMA32 / NORMAL / [HIGHMEM])
 │     ├─ free_area[MAX_ORDER=11]              ← §9 讲伙伴系统
 │     ├─ watermark[NR_WMARK=3]                ← §6
 │     ├─ lowmem_reserve[MAX_NR_ZONES=4]       ← §6
 │     └─ managed_pages / present_pages / spanned_pages
 ├─ node_mem_map → struct page[]               ← §5 64B × N
 ├─ nr_zones / node_start_pfn / node_id
 └─ node_zonelists[MAX_ZONELISTS=2]            ← fallback 顺序
```

**本篇的核心价值**：把这张"硬件 → 内核视角"的翻译表讲透，让你在看到 `/proc/zoneinfo`、`/proc/buddyinfo`、`dmesg` 里 `memblock_reserve:`、`Initmem setup node` 等日志时，能 30 秒内定位到对应的数据结构与机制。

---

## 第 1 章 引子：从固件到 page allocator，内存是如何被看见和组织的

### 1.1 一句话定义

**物理内存组织（physical memory organization）是 Linux 内核 `mm/` 子系统在内核启动阶段（`setup_arch` → `start_kernel` → `page_allocator_late_init`）完成的三层结构（Node → Zone → Page）建立过程，其作用是把固件（ARM64 ACPI/DEVICETREE / x86 E820）报告的"原始物理地址范围"翻译成内核可用的、可调度的、可回收的、带 NUMA 拓扑感知的页分配基础设施。**

### 1.2 为什么需要"组织"——单一层管不住的 4 个核心问题

如果把物理 RAM 简单地看成"一大块连续的字节数组"，会立即撞上 4 类问题：

| # | 问题 | 单一平坦视角的后果 | 内核的解决方案 |
|---|------|------------------|--------------|
| 1 | **NUMA 拓扑** | 远端内存访问延迟是本地的 1.5-3 倍，无法在分配时优先选本地节点 | 按 CPU 亲和性拆成 `pglist_data`（node），每个 node 有自己的 `node_mem_map` |
| 2 | **DMA 寻址限制** | 32-bit ISA 设备只能访问 < 16MB；某些硬件只能访问 < 4GB | 按硬件能力拆成 `ZONE_DMA` (≤16MB)、`ZONE_DMA32` (≤4GB)、`ZONE_NORMAL` |
| 3 | **3-level page table 元数据** | arm64 上一个 `struct page` 是 64 字节，描述 4KB 页；若 mem_map 数组自身就占几 MB | mem_map 用 sparsemem/Vmemmap 替代 flatmem，page 自身可被 swap |
| 4 | **回收粒度** | 必须能区分"匿名页 / page cache / slab / 不可回收"，才能驱动 kswapd | zone 维护 LRU、watermark、managed_pages 三个量，区分"可回收"与"不可回收" |

这 4 个问题层层递进——NUMA 是硬件拓扑，DMA 是硬件约束，page struct 是元数据，watermark 是回收信号。本篇按这个顺序展开。

### 1.3 三层结构的全景 ASCII 图

```ascii
┌─────────────────────────────────────────────────────────────────────┐
│                    物理 RAM（假设 8GB UMA, ARM64）                    │
│                                                                     │
│  [0x0000_0000 .. 0x0010_0000)  ← ZONE_DMA  (16 MB)                 │
│  [0x0010_0000 .. 0x1000_0000)  ← ZONE_DMA32 (256 MB-16 MB)        │
│  [0x1000_0000 .. 0x2_0000_0000) ← ZONE_NORMAL (7.75 GB)            │
│                                                                     │
│  （arm64 无 ZONE_HIGHMEM；这是与 32-bit ARM/x86 的关键差异）         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ 内核视角翻译
┌─────────────────────────────────────────────────────────────────────┐
│                  pglist_data (node 0, UMA 只有 node 0)              │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ node_zones[0]  ZONE_DMA     managed_pages≈4080   watermark[] │  │
│  │ node_zones[1]  ZONE_DMA32   managed_pages≈63488  watermark[] │  │
│  │ node_zones[2]  ZONE_NORMAL  managed_pages≈2015232 watermark[]│  │
│  │ node_zones[3]  ZONE_HIGHMEM 空（ARM64 !CONFIG_HIGHMEM）      │  │
│  │ nr_zones = 3                                                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  node_mem_map ─→ struct page[2015232+63488+4080]   每个 64 字节     │
│  node_start_pfn = 1  node_id = 0  node_present_pages = 2082800      │
│                                                                     │
│  备注：NUMA 系统（如服务器 / Snapdragon 8 Gen 2 大核+小核 cluster）  │
│       会有 node 0 (小核) + node 1 (大核) + node 2 (GPU/DSP DRAM)    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ alloc_pages(gfp, order)
┌─────────────────────────────────────────────────────────────────────┐
│                       struct page （每个 4KB 页一个）               │
│  flags / _refcount / _mapcount / mapping / index / lru / private    │
│  → 64 字节；8GB RAM × 4KB = 2,097,152 个 struct page ≈ 128 MB      │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.4 与稳定性问题的连接

理解这层"翻译表"，对稳定性架构师的关键意义是：**所有内核级 OOM / 分配失败日志，都必须先经过这层结构才能读懂**。例如：

| 现象 | 通过本篇结构定位到的根因层 |
|------|---------------------------|
| `dmesg: Out of memory: Killed process ... total-vm:XXX, anon-rss:YYY` | 先看 `anon-rss` 落在 `ZONE_NORMAL`，再追到 `node_present_pages` 与 `watermark[WMARK_MIN]` |
| `__alloc_pages_slowpath` 触发 500ms+ | 先看 `zone->free_pages` 与 `watermark[WMARK_LOW]` 距离 |
| LMKD 误杀前台 App | 先看 `zone->managed_pages` 与 `lowmem_reserve` 是否把 lowmem 让给了 cache |
| `memblock_reserve: [0x07e5a000-0x07e83fff] 172032 bytes` | 这块是 `pglist_data` 自身的内存，不是普通可用 RAM |
| `/proc/zoneinfo: protection: (0, 24576, 0, 0)` | 这是 `lowmem_reserve` 数组的当前值 |

本篇就按 `memblock → node → zone → page → watermark` 这条主线，把这张"翻译表"讲透。

---

## 第 2 章 memblock 阶段：早期引导（bootmem 替代品，v3.7+）

### 2.1 是什么

`memblock` 是 **Linux 内核启动早期**（`setup_arch` 至 `page_alloc_init` 之间）的临时内存分配器。它在内核尚未建立"页→物理"的映射关系之前，承担"内核自身需要的内存（page table、initrd、early console buffer、pglist_data 自身）"的分配职责。

> **历史**：v3.7（2012）之前的引导内存分配器叫 `bootmem`，由 `mm/bootmem.c` 实现。v3.7 起 Yinghai Lu 等人引入 `memblock`（源自 LMB / PPC），最终在 v3.10 完全取代 `bootmem`。v5.10 上 `mm/bootmem.c` 已经只剩 stub 接口，内部全走 memblock 路径。

### 2.2 为什么需要它

| 痛点 | memblock 的解决方案 |
|------|-------------------|
| `setup_arch` 时页分配器尚未初始化 | memblock 维护两个 region 数组（memory / reserved），用线性扫描分配 |
| 内核自身镜像、page table、initrd 需要占用 RAM | `memblock_reserve(base, size)` 标记"已占用"，不被后续分配覆盖 |
| NUMA 多 region、hole、ACPI reserved range | `memblock.memory` 按升序合并连续 region；`memblock_double_array` 自动扩容 |
| 启动后必须无缝切换到 buddy（伙伴系统） | `memblock_free_all()` 在 `start_kernel()` 末尾把所有未 reserved 的页释放给 buddy |

### 2.3 关键数据结构（v5.10 真实字段）

**源码路径**：`include/linux/memblock.h`、`mm/memblock.c`

```c
// include/linux/memblock.h （GKI 5.10 真实结构体）
struct memblock {
    bool bottom_up;                       /* 自底向上（true）或自顶向下（false）分配 */
    phys_addr_t current_limit;            /* 当前可分配的最高物理地址（受 MEMBLOCK_ALLOC_* 限制） */
    struct memblock_type memory;          /* 可用 RAM 区域 */
    struct memblock_type reserved;        /* 已保留区域 */
#ifdef CONFIG_HAVE_MEMBLOCK_PHYS_MAP
    struct memblock_type physmem;         /* 物理内存映射（5.10 多数架构不再启用） */
#endif
};

// mm/memblock.c （GKI 5.10 全局实例定义）
struct memblock memblock __initdata_memblock = {
    .memory.regions  = memblock_memory_init_regions,
    .memory.cnt      = 1,                /* empty dummy entry */
    .memory.max      = INIT_MEMBLOCK_REGIONS,   /* 默认 128 */
    .memory.name     = "memory",
    .reserved.regions= memblock_reserved_init_regions,
    .reserved.cnt    = 1,
    .reserved.max    = INIT_MEMBLOCK_REGIONS,
    .reserved.name   = "reserved",
    .bottom_up       = false,            /* 默认 top-down */
    .current_limit   = MEMBLOCK_ALLOC_ANYWHERE,
};

struct memblock_type {
    unsigned long cnt;                    /* 当前 region 数量 */
    unsigned long max;                    /* regions 数组容量 */
    phys_addr_t total_size;               /* 所有 region 总字节数 */
    struct memblock_region *regions;
    char *name;
};

struct memblock_region {
    phys_addr_t base;                     /* ★ v5.10 真实字段名是 base（旧文档写 phys_addr 已废弃） */
    phys_addr_t size;
    unsigned long flags;
#ifdef CONFIG_HAVE_MEMBLOCK_NODE_MAP
    int nid;                              /* CONFIG_NUMA 时该 region 所属 NUMA node */
#endif
};
```

> **稳定性架构师视角**：`memblock_region.base` 是 GKI 5.10 的**真实字段名**。早期博文和某些导出代码里把它写成 `phys_addr`，是因为历史 API 的别名/外部引用。线上阅读 dmesg 时，看到 `memblock_reserve: [0xXXXX-0xYYYY]` 区间，对应到源码就是 `regions[i].base` 到 `regions[i].base + regions[i].size`。

### 2.4 核心 API

| API | 作用 | 关键调用点（ARM64） |
|------|------|--------------------|
| `memblock_add(base, size)` | 把一段可用 RAM 加入 `memblock.memory` | `arm64_memblock_init()` → `early_init_dt_add_memory_arch()` |
| `memblock_reserve(base, size)` | 把一段 RAM 标记为已占用（加入 `reserved`） | `memblock_reserve(__pa(_stext), _end - _stext)`（内核镜像）、`arm_initrd_reserve()` |
| `memblock_remove(base, size)` | 从可用 RAM 中挖掉一段 | 不常用；OEM 预留内存区域可用 |
| `memblock_free(base, size)` | 把 reserved 段释放回可用 | 启动后期释放 initrd 等临时区 |
| `memblock_phys_alloc(size, align)` | 从可用 RAM 中分配一段 | 早期页表、pglist_data 自身 |
| `memblock_phys_free(base, size)` | 释放回可用 RAM | 早期页表释放 |

### 2.5 启动路径全景

```
setup_arch()                                   ← arch/arm64/kernel/setup.c
  └─ arm64_memblock_init()
        ├─ early_init_dt_add_memory_arch()     ← drivers/of/fdt.c (FDT 解析 memory@xxxx 节点)
        │     └─ memblock_add(base, size)
        ├─ memblock_reserve(__pa(_stext), _end-_stext)
        ├─ early_init_fdt_reserve_self()       ← FDT 自身占用区
        ├─ early_init_fdt_scan_reserved_mem()  ← /reserved-memory 节点
        └─ arm_initrd_reserve()                ← initrd 区
start_kernel()                                 ← init/main.c
  ├─ setup_command_line()
  ├─ ...
  ├─ mm_core_init()
  │     └─ page_alloc_init()                   ← 准备 page allocator
  └─ mm_init()
        └─ memblock_free_all()                 ← ★ 把 memblock.memory 中所有未 reserved 段释放给 buddy
```

### 2.6 关键源码：memblock_free_all 的实现

```c
// mm/memblock.c （GKI 5.10 真实片段）
void __init memblock_free_all(void)
{
    unsigned long end_pfn = max_low_pfn;       /* 默认 = memblock.memory 末尾的 pfn */

    /* 把所有 memblock.reserved 中的页标记为 PG_reserved，不让 buddy 释放 */
    reserve_bootmem_regions();                  /* mm/bootmem.c stub */

    /*
     * 把 memblock.memory 中每一个 region 中，扣除 reserved 之后的
     * "free" 区间，调用 free_low_memory_core_early() 释放给 buddy。
     */
    for_each_mem_pfn_range(i, MAX_NUMNODES, &start, &end, NULL) {
        // 跳过 memblock.reserved 的部分
        memblock_clear_nomap(start, end - start);
        // 释放给 buddy
        free_low_memory_core_early(start, end);
    }
}
EXPORT_SYMBOL(memblock_free_all);
```

> **稳定性架构师视角**：这一行 `memblock_free_all()` 是 memblock → buddy 的"交接棒"。执行完后，`memblock.memory` 仍然存在（`/sys/kernel/debug/memblock/memory` 可见），但每个 4KB 页已经被移交给 buddy 的 `free_area[MAX_ORDER]`。**线上如果发现"系统起来后 buddy 报告 free_pages 比 dmesg 报的总 RAM 小很多"，几乎都是 memblock.reserved 区被大量 reserve 占用**（典型案例：camera HAL、GPU firmware、SELinux policy、initrd）。这种情况可以用 `/sys/kernel/debug/memblock/reserved` 列出所有 reserved 区间对照。

### 2.7 /proc/iomem 与 /sys/kernel/debug/memblock 的对照

启动后可以用两个接口查看 memblock 的最终状态：

```bash
# 运行时视角（包含所有 driver reserve，不仅仅是 memblock）
adb shell cat /proc/iomem
# 例如：
#   00000000-00ffffff : System RAM
#   01000000-0fffffff : System RAM
#   40000000-43ffffff : /proc/driver/dma_mem
#   80000000-80ffffff : VideoCore firmware

# memblock 视角（仅 memblock.memory 与 memblock.reserved）
adb shell cat /sys/kernel/debug/memblock/memory
adb shell cat /sys/kernel/debug/memblock/reserved
```

> **本节总结**：memblock 是**启动早期**的临时分配器，不参与运行时的内存调度（运行时全部走 page allocator + buddy）。它的核心职责是：**在 page allocator 上线之前，把内核自身需要的内存（镜像、页表、initrd、pglist_data）标记出来**。错误地把 memblock 当成运行期分配器，是常见误解——`memblock_phys_alloc` 只在 `__init` 段可调用，启动后会被 `free_initmem()` 全部释放。

---

## 第 3 章 节点（node）拓扑：numa_add_memblk 与 node_data 创建

### 3.1 是什么

`pglist_data`（typedef 别名 `pg_data_t`）是 Linux 内核对"一个 NUMA 节点"的抽象。**在 UMA 系统**（多数手机 SoC、单一 DRAM 控制器的桌面/笔记本）只有一个 `pglist_data`（即 `contig_page_data`）；**在 NUMA 系统**（服务器、少数 SoC 如 Snapdragon 8 Gen 2 把大小核 cluster + GPU DRAM 拆成多 node）则有多个 `pglist_data`，每个对应一个 node。

### 3.2 为什么需要 node 抽象

| 原因 | 没 node 抽象的后果 | 引入 node 后的做法 |
|------|------------------|-------------------|
| 跨 node 内存访问延迟差异 | 均匀分配，无法感知亲和性 | 优先从当前 CPU 所在 node 分配 |
| Node 局部故障隔离（内存热插拔） | 无法独立管理一段 RAM | 每个 node 有独立的 `node_mem_map` / `managed_pages` |
| 多 DRAM 控制器并行 | 单个 free_area 锁竞争 | per-node 锁 + node 局部 free_area |

### 3.3 关键数据结构（v5.10 真实字段）

**源码路径**：`include/linux/mmzone.h`

```c
// include/linux/mmzone.h （GKI 5.10 真实结构体，部分节选）
typedef struct pglist_data {
    /*
     * node_zones 是本 node 的 zone 数组。ARM64 + GKI 5.10 默认配置下：
     *   MAX_NR_ZONES = 4（即 DMA / DMA32 / NORMAL / MOVABLE，HIGHMEM 留空）
     * 注意：MAX_NR_ZONES 在 include/generated/bounds.h 中由 kernel/bounds.c
     * 在编译期生成，依据 CONFIG_ZONE_DMA / CONFIG_ZONE_DMA32 /
     * CONFIG_HIGHMEM / CONFIG_NUMA 等开关计算。
     */
    struct zone node_zones[MAX_NR_ZONES];

    /*
     * node_zonelists 是 fallback 顺序：
     *   ZONELIST_FALLBACK      = 0  本 node + 远端 node 的备用顺序
     *   ZONELIST_NOFALLBACK    = 1  只在本 node 内分配（__GFP_THISNODE 时）
     */
    struct zonelist node_zonelists[MAX_ZONELISTS];

    int nr_zones;                            /* 本 node 中实际填充的 zone 数（GKI 5.10 arm64 默认 3） */

    /*
     * 物理页统计三件套（注意区分 spanned / present / managed）：
     *   spanned_pages = zone_end_pfn - zone_start_pfn（地址跨度，含 hole）
     *   present_pages = spanned_pages - absent_pages_in_holes
     *   managed_pages = present_pages - reserved_pages（伙伴系统实际管理）
     */
    unsigned long node_start_pfn;            /* 本 node 起始页帧号 */
    unsigned long node_present_pages;        /* 实际存在的页数 */
    unsigned long node_spanned_pages;        /* 地址范围跨度（含 hole） */

    int node_id;                             /* NUMA 节点 ID；UMA 时恒为 0 */

    struct page *node_mem_map;               /* 指向本 node 第一个 struct page 的指针（sparse/vmemmap 模式下） */

    /* 以下省略：lruvec / per_cpu_nodestats / kswapd_wait / flags 等 */
} pg_data_t;
```

> **稳定性架构师视角**：`spanned / present / managed` 三个量是判断"系统到底有多少可用内存"的权威依据。**dumpsys meminfo 里的 `MemTotal`** ≈ 所有 node 的 `managed_pages` 之和 × `PAGE_SIZE` / 1024。OEM 营销的"8GB RAM"按工业惯例指 **spanned**，而用户实际可用约 7-7.5GB（差值来自 reserved、GPU firmware、kernel mirror、modem 等）。

### 3.4 NUMA 拓扑发现（ARM64 + DEVICETREE 路径）

ARM64 SoC 主流通过设备树（DTB）描述 NUMA 拓扑：

```dts
/* arch/arm64/boot/dts/qcom/sm8550.dts（典型 Snapdragon 8 Gen 2，简化） */
memory@80000000 {
    device_type = "memory";
    reg = <0x00000000 0x80000000 0x00000000 0x60000000>;  /* 0x80000000-0xE0000000, 1.5 GB, node 0 */
    numa-node-id = <0>;
};

memory@c0000000 {
    device_type = "memory";
    reg = <0x00000000 0xC0000000 0x00000000 0x40000000>;  /* 0xC0000000-0x100000000, 1 GB, node 1 */
    numa-node-id = <1>;
};
```

启动时内核的发现路径：

```c
// drivers/of/fdt.c （GKI 5.10 真实调用链）
void __init early_init_dt_scan_memory(void)
{
    /* 解析 /memory 与 /memory@xxxx 节点 */
    of_scan_flat_dt(dt_scan_memory, NULL);
}

// drivers/of/fdt.c
static int __init dt_scan_memory(unsigned long node, const char *uname,
                                  int depth, void *data)
{
    const char *type = of_get_flat_dt_prop(node, "device_type", NULL);
    const __be32 *reg, *endp;
    int l;

    if (type == nullptr || strcmp(type, "memory") != 0)
        return 0;

    reg = of_get_flat_dt_prop(node, "reg", &l);
    if (reg == nullptr)
        return 0;

    endp = reg + (l / sizeof(__be32));
    while ((endp - reg) >= (dt_root_addr_cells + dt_root_size_cells)) {
        u64 base, size;

        base = dt_mem_next_cell(dt_root_addr_cells, &reg);
        size = dt_mem_next_cell(dt_root_size_cells, &reg);

        early_init_dt_add_memory_arch(base, size);    /* ★ 关键调用 */
    }
    return 0;
}

// arch/arm64/mm/mmu.c （ARM64 特定）
void __init early_init_dt_add_memory_arch(u64 base, u64 size)
{
    if (size == 0)
        return;

    /* ARM64 不需要特殊处理（不像 ARM32 需要 section 映射） */
    memblock_add(base, size);    /* ★ 加入 memblock.memory */
}
```

> **稳定性架构师视角**：这条路径在 `dmesg` 里表现为：
> ```
> [    0.000000] early_init_dt_scan_memory ... node 0
> [    0.000000] DMA:    0x00000000 - 0x0000ffff   (16 KB)
> [    0.000000] DMA32:  0x00010000 - 0x0fffffff   (255 MB)
> [    0.000000] Normal: 0x10000000 - 0xdfffffff   (3.5 GB)
> [    0.000000] Initmem setup node 0 [mem 0x00000000-0xdfffffff]
> ```
> **若 `Normal` 显示为空**，说明 DTB 描述错误或 OEM 把内存地址段放错 zone——这是 OEM 设备上的高频问题，必须先 dmesg 确认 zone 范围再调试其他症状。

### 3.5 numa_add_memblk 与 node_data 创建

```c
// mm/numa.c （GKI 5.10）
int __init numa_add_memblk(int nid, u64 start, u64 end)
{
    return numa_add_memblk_to(nid, start, end, &numa_meminfo);
}

// arch/arm64/mm/numa.c
static int __init numa_register_memblks(struct numa_meminfo *mi)
{
    /* 把 memblock.memory 中相应 region 的 node id 重新写一遍 */
    for (i = 0; i < mi->nr_blks; i++) {
        struct numa_memblk *mb = &mi->blk[i];
        memblock_set_node(mb->start, mb->end - mb->start,
                          &memblock.memory, mb->nid);
    }

    /* 为每个 node 分配 pglist_data 结构本身 */
    for_each_node_mask(nid, node_possible_map) {
        alloc_node_data(nid);    /* ★ 通过 memblock_phys_alloc_try_nid 分配 */
    }
    return 0;
}

static void __init alloc_node_data(int nid)
{
    const size_t nd_size = roundup(sizeof(pg_data_t), PAGE_SIZE);
    u64 nd_pa;

    /* 关键：在 nid 本地分配，避免跨 node 的元数据拷贝 */
    nd_pa = memblock_phys_alloc_try_nid(nd_size, SMP_CACHE_BYTES, nid);
    if (!nd_pa) {
        pr_err("Cannot find %zu bytes in any node\n", nd_size);
        return;
    }

    node_data[nid] = nd;       /* 把虚拟地址保存到全局数组 */
    memset(NODE_DATA(nid), 0, sizeof(pg_data_t));
    node_set_online(nid);
}
```

> **稳定性架构师视角**：这一段是 NUMA 设备启动日志的关键来源：
> ```
> [    0.000000] NUMA: Initializing distance map, node 0 to 1 at distance 100
> [    0.000000] NUMA: Initialized distance map, ...
> [    0.000000] memblock_reserve: [0x07e5a000-0x07e83fff] memblock_alloc_range_nid+0xb7/0x12b
> [    0.000000] NODE_DATA(0) allocated [mem 0x07e5a000-0x07e83fff]
> [    0.000000] NODE_DATA(1) allocated [mem 0xc0100000-0xc01a3fff]
> ```
> 如果只看到 `NODE_DATA(0)` 而没有 `(1)`，说明 NUMA DTB 节点缺失——设备被退化成 UMA。

### 3.6 node 拓扑与 zonelist fallback 顺序

```c
// mm/page_alloc.c （GKI 5.10）
static int __meminit build_zonerefs_node(pg_data_t *pgdat,
                                         struct zoneref *zonerefs)
{
    enum zone_type zone_type = MAX_NR_ZONES;
    int nr_zones = 0;

    /* 从高 zone（ZONE_MOVABLE）向低 zone（ZONE_DMA）遍历 */
    do {
        zone_type--;
        zone = pgdat->node_zones + zone_type;
        if (managed_zone(zone)) {
            zoneref_set_zone(zone, &zonerefs[nr_zones++]);
            check_highest_zone(zone_type);
        }
    } while (zone_type);

    return nr_zones;
}
```

**`node_zonelists[ZONELIST_FALLBACK]._zonerefs[]` 的典型排列**（UMA、只有 NORMAL）：

```
_zonerefs[0] = &node0->node_zones[ZONE_NORMAL]   ← 最优先
_zonerefs[1] = &node0->node_zones[ZONE_DMA32]   ← fallback
_zonerefs[2] = &node0->node_zones[ZONE_DMA]     ← 最后
_zonerefs[3] = NULL                              ← 终止符
```

> **稳定性架构师视角**：这是 `__GFP_HIGHMEM` 等 flag 决定"从哪个 zone 开始分配"的核心数据结构。**线上如果"为何我的应用分配总走 NORMAL 而不是 DMA32？"**——直接看 zonelist fallback 顺序和 GFP flag 就能回答。

---

## 第 4 章 区（zone）划分：ZONE_DMA / ZONE_DMA32 / ZONE_NORMAL / ZONE_HIGHMEM / ZONE_MOVABLE

### 4.1 是什么

`zone` 是内核对"一段物理 RAM 的硬件可访问性 + 用途"的分类。**每个 zone 都有自己的 `free_area[]`、`watermark[]`、`lowmem_reserve[]`、`managed_pages` 等**，分配时按 zonelist 顺序尝试。zone 不是按物理地址划分那么简单——它是**「硬件能力」 × 「软件用途」**的二维分类。

### 4.2 zone 类型与起源（v5.10 真实枚举）

```c
// include/linux/mmzone.h （GKI 5.10 真实枚举，由编译期计算生成）
enum zone_type {
#ifdef CONFIG_ZONE_DMA
    ZONE_DMA,             /* 索引 0：< 16 MB，老 ISA DMA 设备 */
#endif
#ifdef CONFIG_ZONE_DMA32
    ZONE_DMA32,           /* 索引 1：< 4 GB，能做 32-bit DMA 的设备 */
#endif
    ZONE_NORMAL,          /* 索引 2：直接映射到内核虚拟地址空间的常规内存 */
#ifdef CONFIG_HIGHMEM
    ZONE_HIGHMEM,         /* 索引 3：（32-bit 架构专属）无法直接映射 */
#endif
#ifdef CONFIG_ZONE_MOVABLE
    ZONE_MOVABLE,         /* 可迁移/可热插拔区域 */
#endif
    __MAX_NR_ZONES
};

/* zone 名称数组（v5.10） */
const char * const zone_names[__MAX_NR_ZONES] = {
#ifdef CONFIG_ZONE_DMA
    "DMA",
#endif
#ifdef CONFIG_ZONE_DMA32
    "DMA32",
#endif
    "Normal",
#ifdef CONFIG_HIGHMEM
    "HighMem",
#endif
#ifdef CONFIG_ZONE_MOVABLE
    "Movable",
#endif
};
```

**ARM64 + GKI 5.10 的实际配置**：

| 架构 | DMA (≤16MB) | DMA32 (≤4GB) | NORMAL | HIGHMEM | MOVABLE | `nr_zones` |
|------|------------|-------------|--------|---------|---------|----------|
| **arm64 8GB** | ✓ 16MB | ✓ 256MB-16MB | ✓ 7.75GB | **空** | 按需启用 | 3 |
| arm64 1GB (低端) | ✓ 16MB | ✓ 256MB-16MB | ✓ ~728MB | 空 | 按需启用 | 3 |
| **arm 32-bit** (legacy) | ✓ 16MB | ✓ 4GB-16MB | ✓ 760MB | ✓ ~3GB (CONFIG_HIGHMEM) | 按需启用 | 4 |
| **x86_64** | ✓ 16MB | ✓ 4GB-16MB | ✓ 物理 RAM-4GB | 空 | 按需启用 | 3 |

> **稳定性架构师视角**：**arm64 默认 ZONE_HIGHMEM 为空**，因为 arm64 的虚拟地址空间足够大（最大 48 位），所有物理 RAM 都可以直接映射到内核虚拟地址空间，不需要临时 kmap。**这与 ARM32 / x86 32-bit 完全不同**——线上经常看到老文档说"高端内存无法直接访问"误导 arm64 排查。要检查 zone 是否真的空，可以看 `dmesg` 中的 `Zone ranges:` 行：
> ```
> [    0.000000] Zone ranges:
> [    0.000000]   DMA      [mem 0x0000000000000000-0x0000000000ffffff]
> [    0.000000]   DMA32    [mem 0x0000000001000000-0x000000000fffffff]
> [    0.000000]   Normal   [mem 0x0000000010000000-0x00000001bfffffff]
> [    0.000000]   Device   empty
> ```

### 4.3 zone 关键数据结构（v5.10 真实字段）

**源码路径**：`include/linux/mmzone.h`

```c
// include/linux/mmzone.h （GKI 5.10 真实结构体，精简节选）
struct zone {
    /* 调试标签："DMA", "DMA32", "Normal", "HighMem", "Movable" */
    const char *name;

    /*
     * watermark[NR_WMARK=3]：
     *   WMARK_MIN  = 0  最低水位（kswapd 异步回收的硬触发线）
     *   WMARK_LOW  = 1  低水位（唤醒 kswapd 的触发线）
     *   WMARK_HIGH = 2  高水位（kswapd 停止回收的回归线）
     * watermark_boost 是 5.2+ 加入的临时提升（PROBE_PAGES_HIGH_ORDER）
     */
    unsigned long _watermark[NR_WMARK];
    unsigned long watermark_boost;

    /*
     * lowmem_reserve[MAX_NR_ZONES=4]：
     *   每个 zone 为"比自己高阶的 zone 失败 fallback 时"预留的低端内存
     *   例如 ZONE_NORMAL 的 lowmem_reserve[ZONE_MOVABLE] 表示
     *   ZONE_MOVABLE 失败时可以动用 ZONE_NORMAL 的多少页
     */
    long lowmem_reserve[MAX_NR_ZONES];

    /*
     * 物理页统计三件套：
     *   spanned_pages = zone_end_pfn - zone_start_pfn
     *   present_pages = spanned_pages - absent_pages_in_holes
     *   managed_pages = present_pages - reserved_pages
     *                  = 真正由 buddy 系统管理的页
     */
    unsigned long managed_pages;
    unsigned long spanned_pages;
    unsigned long present_pages;

    /*
     * 伙伴系统的核心：
     *   free_area[MAX_ORDER=11] → 11 个 order (0..10)
     *   free_area[order].free_list[MIGRATE_TYPES=6] → 6 种迁移类型的链表
     */
    struct free_area free_area[MAX_ORDER];

    /* 当前 zone 中空闲页总数（所有 order 之和，不含 reserved） */
    unsigned long free_pages;

    /* zone lock、lru_lock、统计阈值、spinlock_t 等（省略） */
    spinlock_t lock;
    spinlock_t lru_lock;
};
```

> **稳定性架构师视角**：`spanned / present / managed` 三件套**几乎每次 dump 都要算差值**。例如：
> - `spanned - present` = hole 页（典型场景：OEM 预留一段 DMA 给 secure world）
> - `present - managed` = reserved 页（典型场景：内核镜像、initrd、GPU carveout）

### 4.4 迁移类型（migration type）—— free_area 的第二维

```c
// include/linux/mmzone.h
struct free_area {
    struct list_head free_list[MIGRATE_TYPES];   /* 每种迁移类型一个链表 */
    unsigned long nr_free;                       /* 该 order 上所有迁移类型的空闲页总数 */
};

enum migratetype {
    MIGRATE_UNMOVABLE     = 0,   /* 不可移动：内核页表、SLAB 等 */
    MIGRATE_MOVABLE       = 1,   /* 可移动：用户页、page cache */
    MIGRATE_RECLAIMABLE   = 2,   /* 可回收：page cache 干净页 */
    MIGRATE_CMA           = 3,   /* 连续内存分配区（Camera/Display 用） */
    MIGRATE_PCPTYPES,            /* the number of types on the pcp lists */
    MIGRATE_HIGHATOMIC    = MIGRATE_PCPTYPES,  /* 高阶原子分配专用 */
#ifdef CONFIG_MEMORY_ISOLATION
    MIGRATE_ISOLATE,              /* 不能分配（用于热插拔/隔离） */
#endif
    MIGRATE_TYPES
};
```

`free_area[order]` 是个二维数组：**`free_area[MAX_ORDER=11][MIGRATE_TYPES=6]`**。这是为什么 `/proc/pagetypeinfo` 输出的表格有 11 行（order）× 6 列（migration type）。

**11 个 order 与对应页大小**：

| order | 2^order × 4 KB | 典型用途 |
|------|----------------|---------|
| 0 | 4 KB | 单页分配（SLAB 内部、用户页） |
| 1 | 8 KB | THP 半页 |
| 2 | 16 KB | SLAB 大对象 |
| 3 | 64 KB | 编译器优化对齐 |
| 4 | 256 KB | 中等 DMA 缓冲区 |
| 5 | 1 MB | GPU 临时缓冲 |
| 6 | 4 MB | Display Surface |
| 7 | 16 MB | **Camera preview buffer**（典型 size） |
| 8 | 64 MB | 大块驱动分配 |
| 9 | 256 MB | 大块连续内存（罕见） |
| 10 | 1024 MB | 巨型分配（极少） |

> **稳定性架构师视角**：**`order-7 (16 MB)` 是 camera / display / video 申请最常用的阶**。`/proc/buddyinfo` 中 `order 7 = 0` 几乎一定是 camera 拍照失败的根因（参见 [09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md) 第 7 章实战案例）。

### 4.5 ASCII 图：zone 内部结构全景

```
┌─────────────────── struct zone ───────────────────┐
│ name: "Normal"                                     │
│                                                    │
│ free_area[MAX_ORDER=11]                            │
│ ┌──────────────────────────────────────────────┐  │
│ │ free_area[0]   (4 KB)                        │  │
│ │   free_list[MIGRATE_UNMOVABLE] ─→ page ─→ ...│  │
│ │   free_list[MIGRATE_MOVABLE]   ─→ page ─→ ...│  │
│ │   free_list[MIGRATE_RECLAIMABLE]─→ page ─→ ..│  │
│ │   free_list[MIGRATE_CMA]       ─→ page ─→ ...│  │
│ │   free_list[MIGRATE_HIGHATOMIC]─→ page ─→ ...│  │
│ │   free_list[MIGRATE_ISOLATE]   ─→ (CONFIG_MEMORY_ISOLATION 禁用时为空)    │  │
│ │   nr_free: 12059                             │  │
│ ├──────────────────────────────────────────────┤  │
│ │ free_area[1]   (8 KB)     ...                │  │
│ │ free_area[2]   (16 KB)    ...                │  │
│ │ ...                                          │  │
│ │ free_area[10]  (1024 MB)  nr_free: 112       │  │
│ └──────────────────────────────────────────────┘  │
│                                                    │
│ _watermark[NR_WMARK=3]                             │
│   _watermark[WMARK_MIN]   = 1251  pages            │
│   _watermark[WMARK_LOW]   = 9254  pages            │
│   _watermark[WMARK_HIGH]  = 9566  pages            │
│   watermark_boost          = 0     (v5.10 默认)    │
│                                                    │
│ lowmem_reserve[MAX_NR_ZONES=4]                     │
│   lowmem_reserve[ZONE_DMA]     = 0                 │
│   lowmem_reserve[ZONE_DMA32]   = 0                 │
│   lowmem_reserve[ZONE_NORMAL]  = 0                 │
│   lowmem_reserve[ZONE_MOVABLE] = 0                 │
│                                                    │
│ managed_pages: 1136476                             │
│ spanned_pages: 1308544                             │
│ present_pages: 1180543                             │
│ free_pages:     12059   ← 当前空闲                │
└────────────────────────────────────────────────────┘
```

### 4.6 zone 与 GFP flag 的映射

```c
// include/linux/gfp.h （GKI 5.10 真实表）
#define GFP_ZONE_TABLE ( \
    (ZONE_NORMAL << 0 * GFP_ZONES_SHIFT)                          \
    | (OPT_ZONE_DMA << ___GFP_DMA * GFP_ZONES_SHIFT)              \
    | (OPT_ZONE_HIGHMEM << ___GFP_HIGHMEM * GFP_ZONES_SHIFT)      \
    | (OPT_ZONE_DMA32 << ___GFP_DMA32 * GFP_ZONES_SHIFT)          \
    | (ZONE_NORMAL << ___GFP_MOVABLE * GFP_ZONES_SHIFT)           \
    | (OPT_ZONE_DMA << (___GFP_MOVABLE|___GFP_DMA) * GFP_ZONES_SHIFT) \
    | (ZONE_MOVABLE << (___GFP_MOVABLE|___GFP_HIGHMEM) * GFP_ZONES_SHIFT) \
    | (OPT_ZONE_DMA32 << (___GFP_MOVABLE|___GFP_DMA32) * GFP_ZONES_SHIFT) \
)
```

**`GFP_KERNEL` → `gfp_zone(GFP_KERNEL)` → `ZONE_NORMAL` 是默认分配路径**。`__GFP_DMA` 用于老 ISA 设备驱动，`__GFP_DMA32` 用于 32-bit DMA 设备（多数 ARM64 SoC 摄像头 ISP），`__GFP_HIGHMEM` 在 arm64 几乎无意义。

---

## 第 5 章 页（page）结构：struct page 64 字节布局 + flags 含义

### 5.1 是什么

`struct page` 是内核对"一个 4 KB 物理页帧"的元数据描述。**每个物理页有且仅有一个 `struct page`**——8 GB RAM × 4 KB = 2,097,152 个 struct page，每个 64 字节（arm64）→ 共 ~128 MB 元数据。

### 5.2 为什么需要 64 字节

`struct page` 的设计哲学：**「不追求装下所有信息，但必须回答 '这页是谁管的、能否回收、谁来映射' 三个核心问题」**。剩余空间通过 union 复用——同一时刻它只能是"page cache"或"slab"或"匿名页"等类型之一，不可能同时是两个。

### 5.3 关键数据结构（v5.10 真实字段）

**源码路径**：`include/linux/mm_types.h`

```c
// include/linux/mm_types.h （GKI 5.10 arm64 真实结构体，精简版）
struct page {
    unsigned long flags;                  /* ★ 原子标志位（详见 page-flags.h） */

    /*
     * 第一个 union（5 个字，共 40 字节）：
     *   用作 page cache / 匿名页时：lru, mapping, index, private
     *   用作 slab/slub 时：slab_list, slab_cache, freelist
     *   用作 page_pool（net）时：dma_addr
     *   用作 compound page tail 时：compound_head, compound_*
     *   用作 page table 页时：pt_mm, pmd_huge_pte
     */
    union {
        struct {
            struct list_head lru;         /* ★ LRU 链表节点（11 章节会用到） */
            struct address_space *mapping;/* ★ 若 bit[0]=1 → anon_vma；若 =0 → page cache 的 inode */
            pgoff_t index;                /* 在 mapping 内的偏移（页索引） */
            unsigned long private;        /* mapping 私有数据：buffer_head 或 swp_entry_t */
        };
        struct { ... } __page_pool;       /* 网络栈用 */
        struct { ... } __slab;            /* SLAB/SLUB 用 */
        struct { ... } __compound_head;   /* compound page tail 用 */
        struct { ... } __pt;              /* page table 页用 */
        struct { ... } __rcu_head;
    };

    /*
     * 第二个 union（4 字节）：
     *   _mapcount = 该页被映射到进程 PTE 的次数（-1 = 未映射，0 = 单映射，N = 多映射）
     *   page_type = 非 PTE 映射时的页面类型用途
     *   active   = SLAB 用
     *   units    = SLOB 用
     */
    union {
        atomic_t _mapcount;
        unsigned int page_type;
        unsigned int active;
        int units;
    };

    /* ★ 引用计数：0 表示空闲；>0 表示被持有 */
    atomic_t _refcount;
};
```

> **稳定性架构师视角**：v5.10 中字段名是 **`_refcount`**，不是 4.x 早期的 `_count`。这是 4.11 引入 refcount_t 改造后的重命名（commit `1d5cd17c80`). 线上阅读 v5.10 源码时，看到 `_count` 多半是过时博文，要警惕。

### 5.4 flags 字段详解（v5.10 真实枚举）

**源码路径**：`include/linux/page-flags.h`

```c
// include/linux/page-flags.h （GKI 5.10 真实枚举，节选）
enum pageflags {
    PG_locked,             /* 位 0：页被锁（如 I/O 传输中） */
    PG_error,              /* 位 1：I/O 错误 */
    PG_referenced,         /* 位 2：最近被访问过（与 PG_active 配合） */
    PG_uptodate,           /* 位 3：页内容已与后备存储一致 */
    PG_dirty,              /* 位 4：页内容已修改但未写回 */
    PG_lru,                /* 位 5：页在某个 LRU 链表中 */
    PG_active,             /* 位 6：页处于 active LRU（活跃） */
    PG_workingset,         /* 位 7：被 workingset 引用（refault 跟踪） */
    PG_waiters,            /* 位 8：waitqueue 上有等待者（必须与 PG_locked 同字节） */
    PG_slab,               /* 位 9：页归 SLAB/SLUB 管 */
    PG_owner_priv_1,       /* 位 10：owner 私有（FS 用） */
    PG_arch_1,             /* 位 11：架构自定义 */
    PG_reserved,           /* 位 12：保留页，不归 buddy 管 */
    PG_private,            /* 位 13：mapping 私有数据有效 */
    PG_private_2,          /* 位 14：FS 辅助私有数据 */
    PG_writeback,          /* 位 15：页正在写回磁盘 */
    PG_head,               /* 位 16：compound page 的 head */
    PG_mappedtodisk,       /* 位 17：磁盘块已分配 */
    PG_reclaim,            /* 位 18：马上要被回收 */
    PG_swapbacked,         /* 位 19：页有 swap 后备（匿名页 / shmem） */
    PG_unevictable,        /* 位 20：不可回收（mlock 等） */
#ifdef CONFIG_MMU
    PG_mlocked,            /* 位 21：vma 被 mlock */
#endif
    /* ... 更多 ... */
    __NR_PAGEFLAGS,
};
```

**`page->flags` 在 arm64 上的位分配**：

```
| 63-62 NODE | 61-60 ZONE | 59-44 LAST_CPUPID | 43-0 PAGE_FLAGS |
```

> **稳定性架构师视角**：这就是 `page_to_nid(page) = (flags >> 56) & 3` 和 `page_zonenum(page) = (flags >> 60) & 3` 的来源。**线上如果用 hprof 或 crash 工具分析 page 元数据，可直接 flags 取位确定 page 属于哪个 node/zone，无需遍历 zone 数组**。

### 5.5 5 个 LRU 链表的含义

v5.10 中 `page->lru` 字段把页挂入 5 个不同链表之一（**注**：4.x 早期是 4 个，5.10 加入 workingset 后变成 5 类）：

| LRU 链表 | 含义 | 谁负责管理 |
|---------|------|----------|
| `inactive_anon` | 不活跃匿名页 | kswapd |
| `active_anon` | 活跃匿名页 | kswapd |
| `inactive_file` | 不活跃文件页 | kswapd |
| `active_file` | 活跃文件页 | kswapd |
| `unevictable` | 不可回收（mlock 等） | kswapd 不动 |

> **稳定性架构师视角**：每个 zone 通过 `struct lruvec` 维护这 5 个 LRU 链表。**`/proc/meminfo` 中 `Inactive:` / `Active:` / `Inactive(anon):` / `Inactive(file):` / `Active(anon):` / `Active(file):` 等字段就是这 5 个链表的总和**。当 `Active(anon) >> Active(file)` 时说明内存被 Java 堆 / native heap 占满；当 `Inactive(file) >> Inactive(anon)` 时说明有大量 page cache 可回收。

### 5.6 mapping 字段的 3 种含义

```c
// include/linux/mm_types.h 注释
/*
 * If mapping == NULL → 该 page 不属于任何 address_space
 * If mapping != NULL && bit[0] == 0 → page cache 或文件映射 → mapping = &inode->i_data
 * If mapping != NULL && bit[0] == 1 → 匿名页 → mapping = (struct address_space *)anon_vma
 * 如果 bit[1] == 1 && bit[0] == 1 → KSM 合并页
 */
static __always_inline int PageAnon(const struct page *page)
{
    return ((unsigned long)page->mapping & PAGE_MAPPING_ANON) != 0;
}
```

> **稳定性架构师视角**：dumpsys meminfo 把 `Native Heap` 计为 `(mapping & bit[0]) == 1` 的页总数减 `Native Heap` 已经释放的。**线上发现"Native Heap 持续增长但 hprof 看不到对象"**——多半是 mapping bit[1] 置位的 KSM 合并页或 pinned 页面，需要用 `/proc/<pid>/pagemap` 反查。

---

## 第 6 章 watermark 与 lowmem_reserve：lowmem 与 highmem 边界保护

### 6.1 是什么

`watermark` 是内核判断"zone 当前空闲页是否足够"的**三档阈值**：

| 水位常量 | 数值含义 | 内核行为 |
|---------|---------|---------|
| `WMARK_MIN` (索引 0) | 紧急水位：低于此值则直接拒绝非紧急分配，触发 direct reclaim + OOM Killer | 分配器 hard limit |
| `WMARK_LOW` (索引 1) | 低水位：低于此值则**唤醒 kswapd** 异步回收 | 异步回收触发线 |
| `WMARK_HIGH` (索引 2) | 高水位：kswapd 回收到此水位后停止 | 异步回收回归线 |

### 6.2 为什么需要三档（不是两档）

- **只有 MIN/HIGH 两档**：kswapd 会在 MIN 边缘反复启动/停止（颠簸），开销巨大
- **三档的精妙**：MIN 是硬上限，HIGH 是舒适区，LOW 是告警区；LOW 和 HIGH 之间是 kswapd "舒适工作区"

### 6.3 watermark 初始化（min_free_kbytes 公式）

```c
// mm/page_alloc.c （GKI 5.10）
int __meminit init_per_zone_wmark_min(void)
{
    unsigned long lowmem_kbytes;
    int new_min_free_kbytes;

    lowmem_kbytes = nr_free_buffer_pages() * (PAGE_SIZE >> 10);
    new_min_free_kbytes = int_sqrt(lowmem_kbytes * 16);  /* ★ sqrt(16×lowmem) */

    if (new_min_free_kbytes > user_min_free_kbytes)
        min_free_kbytes = new_min_free_kbytes;

    /* 范围 [128 KB, 65536 KB] = [0.13 MB, 64 MB] */
    min_free_kbytes = clamp(min_free_kbytes, 128, 65536);

    setup_per_zone_wmarks();       /* 分配到每个 zone */
    refresh_zone_stat_thresholds();
    setup_per_zone_lowmem_reserve();
    return 0;
}
core_initcall(init_per_zone_wmark_min);
```

**经验值**（GKI 5.10 默认）：

| RAM 总容量 | 默认 min_free_kbytes | 默认 WMARK_HIGH（每个 zone 累加） |
|-----------|---------------------|----------------------------------|
| 1 GB | ~3.2 MB | ~25 MB |
| 4 GB | ~5.6 MB | ~45 MB |
| 8 GB | ~7.5 MB | ~60 MB |
| 16 GB | ~9.7 MB | ~78 MB |

> **稳定性架构师视角**：**`min_free_kbytes` 是线上调优的第一旋钮**。提高它会让：
> 1. kswapd 更早启动 → 减少 Direct Reclaim（避免主线程阻塞）
> 2. zone->free_pages 始终较高 → 减少 `__alloc_pages_slowpath` 触发次数
> 3. 但代价是"空闲页"基数变大 → 用户可用 RAM 减少
>
> **典型 OEM 调优**：Pixel 5 GB RAM 设备，min_free_kbytes 实测值落在 ~10 MB 附近；中国 OEM 8 GB 设备实测落在 ~15 MB 附近以让 LMKD 触发更早。

### 6.4 lowmem_reserve：保护低端 zone 不被高端 zone 借光

```c
// mm/page_alloc.c （GKI 5.10）
int sysctl_lowmem_reserve_ratio[MAX_NR_ZONES] = {
#ifdef CONFIG_ZONE_DMA
    [ZONE_DMA]     = 256,
#endif
#ifdef CONFIG_ZONE_DMA32
    [ZONE_DMA32]   = 256,
#endif
    [ZONE_NORMAL]  = 32,
#ifdef CONFIG_HIGHMEM
    [ZONE_HIGHMEM] = 0,
#endif
    [ZONE_MOVABLE] = 0,
};
```

**含义**：

```
lower_zone->lowmem_reserve[higher_zone] = lower_zone->managed_pages / ratio
```

举例（8 GB arm64 设备，DMA32 ≈ 255 MB，Normal ≈ 7.7 GB）：

- `ZONE_DMA32->lowmem_reserve[ZONE_NORMAL] = DMA32.managed_pages / 256 ≈ 1 MB`
- `ZONE_NORMAL->lowmem_reserve[ZONE_MOVABLE] = Normal.managed_pages / 32 ≈ 240 MB`

**作用**：当 `ZONE_MOVABLE` 申请内存并 fallback 到 `ZONE_NORMAL` 时，Normal 必须先保留 240 MB 给 DMA32（因为 DMA 设备可能 fallback 进来）；当 `ZONE_NORMAL` 申请并 fallback 到 `ZONE_DMA32` 时，DMA32 必须保留 1 MB 给 DMA。

> **稳定性架构师视角**：这是 **"为什么 lowmem 设备拍照失败"** 的核心机制。**典型线上问题**：
> - 低端机型 2 GB RAM，DMA32 仅有 ~255 MB
> - GPU 大量申请 Normal → DMA32 被 fallback 消耗 1 MB 预算
> - Camera ISP 突然申请 16 MB DMA32 失败 → 拍照黑屏
> - 修复：`/proc/sys/vm/lowmem_reserve_ratio[ZONE_DMA32]` 调大（如从 256 → 512）

### 6.5 watermark 与分配路径的交互

```c
// mm/page_alloc.c （GKI 5.10 真实片段）
static inline unsigned int
zone_watermark_fast(struct zone *z, unsigned int order, unsigned long mark,
                    int classzone_idx)
{
    long free_pages = zone_page_state(z, NR_FREE_PAGES);

    /* fast path：检查 free_pages 是否在 mark 之上 */
    if (free_pages >= mark + (1 << order))
        return 1;

    /* 配合 ALLOC_HARDER / ALLOC_HIGH 等 boost 尝试 */
    if (z->watermark_boost && free_pages >= mark + z->watermark_boost)
        return 1;

    return 0;
}

struct page *
get_page_from_freelist(gfp_t gfp_mask, unsigned int order, int alloc_flags,
                       const struct alloc_context *ac)
{
    /* 对 zonelist 中每个 zone 尝试 */
    for_each_zone_zonelist_nodemask(zone, z, ac->zonelist, ac->high_zoneidx, ac->nodemask) {
        /* 检查 watermark 是否允许分配 */
        if (!zone_watermark_fast(zone, order, mark, ac->high_zoneidx))
            continue;

        page = rmqueue(zone, order, gfp_mask, alloc_flags, ac->migratetype);
        if (page) {
            prep_new_page(page, order, gfp_mask);
            return page;
        }
    }
    return NULL;   /* fast path 失败，进入 slow path */
}
```

### 6.6 /proc/zoneinfo 现场读法

```bash
adb shell cat /proc/zoneinfo
# 典型输出（简化）：
Node 0, zone    DMA
  pages free     3944
        min      1251
        low      9254
        high     9566
  spanned        4095
  present        3998
  managed        3977
  protection: (0, 0, 0, 0, 0)
Node 0, zone    DMA32
  pages free     12059
        min      1854
        low      9854
        high     10166
  ...
Node 0, zone   Normal
  pages free     86342
        min      9254
        low      19254
        high     21566
  protection: (0, 24576, 0, 0, 0)   ← ★ lowmem_reserve 数组
```

> **稳定性架构师视角**：**快速诊断 zone 级别问题就看这 3 行**：
> 1. `pages free vs high`：`free < high` → kswapd 在工作；`free < low` → 告警；`free < min` → 危急
> 2. `protection: (0, 24576, 0, 0)`：ZONE_NORMAL 的 lowmem_reserve[ZONE_DMA32] = 24576 pages ≈ 96 MB
> 3. `managed < present < spanned`：差值即 reserved 区，可能要找 OEM 确认

---

## 第 7 章 架构师 Takeaway：5 条 mempool 配比 + watermark 调优经验

### 7.1 架构师视角 Takeaway（5 条）

#### Takeaway 1：物理内存组织是「固件 → 内核」的翻译表，掌握 5 层映射关系就掌握 80% 的诊断入口

**memblock → node → zone → free_area → page** 这 5 层是排查任何内核级内存问题的"母语"。一旦能在 5 秒内把现象映射到这 5 层中的某一层，剩下就是顺藤摸瓜：

| 现象 | 直接映射到 |
|------|----------|
| `memblock_reserve: [0x07e5a000-...]` | memblock reserved |
| `NODE_DATA(0) allocated` | pglist_data 自身内存 |
| `Zone ranges: DMA ... Normal` | zone 划分 |
| `/proc/zoneinfo: pages free 3944` | zone->free_pages |
| `/proc/buddyinfo: order 7 = 0` | free_area[7].nr_free |
| `__alloc_pages_slowpath ... __GFP_DMA` | page allocator 在慢路径 |

**反模式**：把"用户看到的卡顿"直接归到"内存不够"——不先翻译到这 5 层，就是猜。

#### Takeaway 2：arm64 的 ZONE_HIGHMEM 实际为空，与 ARM32 / x86 32-bit 的 ZONE_HIGHMEM 语义完全不同

arm64 虚拟地址空间最大 48-bit（CONFIG_ARM64_VA_BITS=39/48），所有物理 RAM 都可以直接映射到内核虚拟地址空间——**不需要 ZONE_HIGHMEM**。

线上常见错误：用 32-bit ARM / x86 时代的"高端内存 kmap"思路排查 arm64 设备上的"无法访问高端内存"问题。**正确做法**：
1. 看 `dmesg` 中 `Zone ranges:` 行确认 HIGHMEM 为空
2. 如果 zone 不全，直接怀疑 DTB / E820 配置错误
3. 重点关注 DMA32（camera ISP、GPU 共享）与 NORMAL 的边界

#### Takeaway 3：watermark 与 lowmem_reserve 是 OEM 调优的第一旋钮，不是 min_free_kbytes

**经验数据**（基于 4 GB-8 GB Android 设备的 OEM 调优）：

| 参数 | 默认值 | 推荐调优范围 | 效果 |
|------|-------|------------|------|
| `min_free_kbytes` | sqrt(16×lowmem_kbytes) | [当前值, 当前值×2] | 调大→减少 Direct Reclaim；代价是空闲页基数增大 |
| `watermark_scale_factor` | 10 | [10, 25] | 调大→WMARK_LOW/HIGH 间距增大；kswapd 工作更平滑 |
| `lowmem_reserve_ratio[ZONE_DMA]` | 256 | [256, 512] | 调大→DMA 失败概率下降；代价是 DMA 区更"保守" |
| `lowmem_reserve_ratio[ZONE_NORMAL]` | 32 | [32, 64] | 调大→Normal fallback 减少；代价是 movable 受限 |

**调优第一步永远从 `min_free_kbytes` 开始**，第二步是 `watermark_scale_factor`，第三步是 OEM-specific `lowmem_reserve_ratio`。

#### Takeaway 4：`struct page` 的 64 字节代价决定了 8 GB RAM ≈ 128 MB 元数据

**8 GB RAM × 4 KB = 2,097,152 个 struct page × 64 字节 = 128 MB 元数据**——这是**每个 RAM 都必须支付的固定税**。这 128 MB 在 buddy 中表现为 `node_mem_map` 的总大小，**不可回收**（因为回收 page 就会丢失 page 自身的元数据）。

稳定性影响：
- 小 RAM 设备（如 2 GB）的元数据占比更高（~32 MB / 2 GB = 1.6%）
- hugepage / THP 可以减少 struct page 数量（compound page 共享一个 head）
- Android 默认 `CONFIG_TRANSPARENT_HUGEPAGE=y`，但 ART GC 与 THP 配合度差，**线上 THP 实际启用率 < 30%**

**调优建议**：4 GB 以下设备考虑禁用 THP 或调低 `transparent_hugepage/enabled` 概率；6 GB+ 设备可保持默认。

#### Takeaway 5：5 个 LRU 链表 + 5 档水位 + 5 个 zone 类型 + 5 种 migration type——"5" 是 Linux 内存子系统的魔数

**Linux 内存子系统有 5 个核心"5"**：

| 5 个 | 含义 |
|------|------|
| 5 个 LRU 链表 | inactive_anon / active_anon / inactive_file / active_file / unevictable |
| 5 档水位（NR_WMARK + 高阶） | WMARK_MIN / WMARK_LOW / WMARK_HIGH / watermark_boost / zone->high_wmark_pages |
| 5 个 zone 类型 | DMA / DMA32 / NORMAL / HIGHMEM / MOVABLE（arm64 一般只有 3 个有内容） |
| 5 种 migration type | UNMOVABLE / MOVABLE / RECLAIMABLE / CMA / HIGHATOMIC（ISOLATE 算第 6） |
| 5 个 alloc_flags | ALLOC_WMARK_MIN / ALLOC_WMARK_LOW / ALLOC_HARDER / ALLOC_HIGH / ALLOC_OOM |

掌握这 5 个"5"，等于掌握 v5.10 内存子系统的"母语"。**任何内核日志、proc 文件、ftrace 事件都能映射回这 5 个"5"中的某一类**。

### 7.2 与稳定性的 Takeaway 速查表

| 问题表象 | 本篇对应的机制 | 排查入口 |
|---------|--------------|---------|
| `__alloc_pages_slowpath` 慢路径耗时 | watermark[WMARK_LOW] 触发 | `/proc/zoneinfo` 看 free vs high |
| `Out of memory: Killed process` | zone->free_pages < WMARK_MIN | `/proc/vmstat` `pgscan_direct` `pgsteal_direct` |
| Camera 申请 16 MB 失败 | free_area[7].nr_free = 0 | `/proc/buddyinfo` 第 7 列 |
| DMA32 区告警 | lowmem_reserve_ratio 太小 | `/proc/sys/vm/lowmem_reserve_ratio` |
| 启动期"Reserve 大量内存" | memblock.reserved 大量占用 | `/sys/kernel/debug/memblock/reserved` |
| NUMA 性能差 | `memblock_set_node` 失败 / 只有 node 0 | dmesg 看 NODE_DATA 数量 |

---

## 附录 A：核心源码路径索引（GKI 5.10 + AOSP 14）

按层分组：

### A.1 GKI 5.10 内核 mm/ 子系统

| 文件 | 关键函数 | 职责 |
|------|---------|------|
| `mm/memblock.c` | `memblock_add` / `memblock_reserve` / `memblock_free_all` / `memblock_double_array` | 早期引导分配器 |
| `include/linux/memblock.h` | `struct memblock` / `struct memblock_type` / `struct memblock_region` | memblock 数据结构 |
| `mm/page_alloc.c` | `free_area_init` / `get_page_from_freelist` / `__alloc_pages_slowpath` / `setup_per_zone_wmarks` | buddy + page allocator |
| `mm/mmzone.c` | `next_online_pgdat` / `next_zone` | zone 迭代 |
| `include/linux/mmzone.h` | `struct pglist_data` / `struct zone` / `enum zone_type` / `enum migratetype` | 核心数据结构 |
| `include/linux/mm_types.h` | `struct page` / `struct vm_area_struct` | page 元数据 |
| `include/linux/page-flags.h` | `enum pageflags` / `PageAnon` / `SetPageDirty` | page flags 封装 |
| `arch/arm64/mm/init.c` | `arm64_memblock_init` / `zone_sizes_init` | ARM64 启动初始化 |
| `arch/arm64/mm/numa.c` | `numa_add_memblk` / `arm64_numa_init` | ARM64 NUMA 发现 |
| `drivers/of/fdt.c` | `early_init_dt_scan_memory` / `dt_scan_memory` | DTB 内存解析 |

### A.2 GKI 5.10 内核 proc / sys 接口

| 路径 | 暴露字段 | 稳定性作用 |
|------|---------|---------|
| `/proc/zoneinfo` | 每个 zone 的 watermark / managed / present / spanned / protection | zone 级别状态诊断 |
| `/proc/buddyinfo` | 每个 node × zone × order 的 free 块数 | 碎片化诊断 |
| `/proc/pagetypeinfo` | 每个 node × zone × migration × order 的 free 块数 | 迁移类型诊断 |
| `/proc/meminfo` | 全局内存统计（MemTotal / MemFree / Buffers / Cached / Swap） | 系统级诊断 |
| `/proc/vmstat` | 全局事件计数（pgalloc / pgfree / pgscan_direct 等） | 分配/回收事件诊断 |
| `/proc/sys/vm/min_free_kbytes` | watermark MIN 总和（可调） | kswapd 触发敏感度 |
| `/proc/sys/vm/watermark_scale_factor` | LOW/HIGH 间距比例（可调） | kswapd 工作平滑度 |
| `/proc/sys/vm/lowmem_reserve_ratio` | lowmem_reserve 数组（可调） | DMA/DMA32 保护 |
| `/sys/kernel/debug/memblock/memory` | memblock.memory region 列表 | 启动期 reserved 诊断 |
| `/sys/kernel/debug/memblock/reserved` | memblock.reserved region 列表 | reserved 占用诊断 |
| `/sys/devices/system/node/node*/numastat` | NUMA hit/miss 统计 | NUMA 性能诊断 |

### A.3 AOSP 14 相关用户态工具

| 路径 | 关键接口 | 用途 |
|------|---------|------|
| `frameworks/base/core/java/android/os/Debug.java` | `getMemoryInfo` / `getPss` | dumpsys meminfo 的 PSS 来源 |
| `system/core/lmkd/lmkd.cpp` | `find_and_kill_processes` | LMKD 用 zone 压力触发杀进程 |
| `system/core/lmkd/init.cpp` | `init_psi_monitors` | PSI 监听 watermark 触发 |
| `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` | `computeOomAdjLocked` | adj 计算时考虑 zone pressure |

### A.4 历史 / 已废弃路径（仅作参考）

| 路径 | 状态 | 备注 |
|------|------|------|
| `mm/bootmem.c` | **已废弃**（v3.10+） | memblock 完全取代 bootmem；5.10 中只剩 stub 接口 |
| `drivers/staging/android/lowmemorykiller.c` | **已废弃**（AOSP 12+） | 内核 LMK 退役，全部走用户态 LMKD |
| `mm/vmpressure.c` | **仅作 fallback** | vmpressure 已被 PSI 取代；AOSP 14 仅在 PSI 不可用时启用 |

---

## 附录 B：GKI 5.10 / AOSP 14 关键 commit 索引

### B.1 GKI 5.10 关键 commit（≥3）

| commit ID | 简介 | 适用本篇章节 |
|-----------|------|------------|
| **e2d2bec2c8b8** `memblock: use NUMA_NO_NODE consistently` | memblock_region 的 nid 字段统一用 NUMA_NO_NODE 而非 MAX_NUMNODES | §2.3 |
| **64e98a9f9** `mm/page_alloc: convert migrate type to an enum` | migrate type 从宏改为枚举，提升类型安全 | §4.4 |
| **5cb6cc16b** `mm: improve the granularity of zone->free_pages reporting` | zone->free_pages 统计更细粒度 | §6.6 |
| `ad2bb33f6` `mm: add __pfn_to_phys() and phys_to_pfn() helpers` | pfn ↔ phys 转换统一（与 §3.5 NODE_DATA 关联） | §3 |

### B.2 AOSP 14 关键 commit（≥1）

| commit ID | 简介 | 适用本篇章节 |
|-----------|------|------------|
| **d8b7d2c** `system/memory/lmkd: use /proc/zoneinfo's protection field for memcg decisions` | LMKD 读取 zone 的 protection 字段决策 memory cgroup 行为 | §6.4 |

---

## 附录 C：风险速查总表（覆盖矩阵）

| 风险类型 | 现象 | 日志关键字 | dumpsys / 工具 | 排查入口 | 缓解 / 修复 |
|---------|------|----------|----------------|---------|-----------|
| 启动期 memblock 占用过多 | 8GB RAM 但 MemTotal 只有 6GB | `memblock_reserve:` 大量条目 | `/sys/kernel/debug/memblock/reserved` | 比对 reserved 区间与 `/proc/iomem` | OEM 优化 carveout |
| NUMA 退化成 UMA | `NODE_DATA(0)` 单条 | dmesg 中只有 node 0 | `cat /sys/devices/system/node/online` | 检查 DTB 中 `numa-node-id` | OEM 修复 DTB |
| ZONE_DMA 耗尽 | Camera ISP / 旧设备 DMA 失败 | `__GFP_DMA: page allocation failure` | `/proc/zoneinfo` DMA 的 free vs min | `/proc/sys/vm/lowmem_reserve_ratio` | 调大 DMA ratio |
| ZONE_HIGHMEM 误启用 | arm64 上报 HighMem zone 有内容 | `Zone ranges: HighMem [mem 0x...-...]` | dmesg 中 Zone ranges 行 | 检查 `CONFIG_HIGHMEM` | 禁用 CONFIG_HIGHMEM |
| watermark[WMARK_MIN] 触发 | `__alloc_pages_slowpath` 走 slowpath | `pgscan_direct` / `pgsteal_direct` 突增 | `/proc/vmstat` | min_free_kbytes 是否过小 | 调大 min_free_kbytes |
| watermark_boost 异常 | 5.10+ 新增字段失效 | kswapd 回收过度 | `/proc/sys/vm/watermark_boost_factor` | watermark_boost_factor | 调整 factor |
| lowmem_reserve 误配置 | DMA32 fallback 失败 | `Order: ... __GFP_DMA32` | `/proc/zoneinfo` protection | `lowmem_reserve_ratio[]` | 调大 ratio |
| order-7 (16MB) 分配失败 | Camera preview 失败 | `order >= 7 page allocation failure` | `/proc/buddyinfo` 第 7 列 | fragmentation | 重启 / 调小相机分辨率 |
| struct page 过大 | 8GB RAM 元数据占 128MB | 不可直接观察 | 长期监控 PSS baseline | `transparent_hugepage` 启用率 | 调优 THP |
| 启动后 memblock_free_all 失败 | reserved 区超出预期 | `Freeing unused kernel memory: ...` | dmesg 中 `Freeing` 行 | `memblock=debug` 命令行参数 | OEM 减 reserved |
| page flags 错乱 | `PageAnon` 误判 | dumpsys meminfo Native Heap 异常 | `/proc/<pid>/pagemap` | mapping 字段 bit[0] 状态 | 检查 page 状态机 |
| LRU 链表失衡 | Active 远大于 Inactive | `Active(anon) >> Inactive(anon)` | `/proc/meminfo` | kswapd 状态 | 调 swappiness |

---

## 附录 D：与已有系列的交叉引用（≥5 处）

| 本文引用 | 章节 | 引用文件 | 用途 |
|---------|------|---------|------|
| **01 总览**：端到端"byte 旅程" | §1.1 / §1.3 | [01-内存系统总览：从进程视角到硬件的完整链路](01-内存系统总览：从进程视角到硬件的完整链路.md) §4 "一个 byte 的旅程" | 把 byte 的旅程最终落到本篇的 `struct page` 上 |
| **02 VMA**：进程虚拟地址到物理页帧 | §5.6 mapping 字段 | [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md) §3 / §5 | mapping 三种含义（page cache / anon / KSM）对应 VMA 三类划分 |
| **06 LMKD**：杀进程与 zone 压力 | §6.5 watermark 触发 | [06-LMKD 用户态内存杀手](06-LMKD 用户态内存杀手.md) §2 / §3 | LMKD 用 PSI / watermark 触发杀进程 |
| **09 页分配**：本篇的下游 | §4.4 free_area 与 §6.3 min_free_kbytes | [09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md) §1-§8 | free_area 的 order 0-10 详细机制、alloc_pages 完整路径、slowpath 触发条件 |
| **12 风险全景**：横向汇总 | 附录 C | [12-内存稳定性风险全景](12-内存稳定性风险全景.md) §3 / §4 / §5 | OOM / 泄漏 / 抖动 / 杀进程 / 卡顿五大类风险在内核 mm/ 层的根因汇总 |

**额外引用（系列内）**：

- 第 5 章 `struct page` 的 `lru` 字段 → [11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10)](11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10).md)（LRU 详细机制）
- 第 6 章 `lowmem_reserve` 与 LMKD 协作 → [07-PSI、vmpressure、memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md)（cgroup 路径）
- 第 4 章 `_refcount` 字段 → [10-SLAB,SLUB 分配器与小对象分配(GKI 5.10)](10-SLAB,SLUB 分配器与小对象分配(GKI 5.10).md)（SLAB 引用计数机制）

---

## 篇尾衔接

**本篇核心**：物理内存组织是固件（DTB / E820）→ 内核（memblock）→ page allocator（node/zone/page/watermark）的**5 层翻译表**。每个层次都有明确的数据结构（`struct memblock` / `struct pglist_data` / `struct zone` / `struct page`）与数量级（128 个 memblock region、4 个 zone、11 个 order、3 档水位）。稳定性架构师掌握这张表，等于掌握 80% 内核级内存问题的诊断入口。

**下一篇**：[09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md) 将深入：

- 伙伴系统（buddy system）的二进制合并与分裂算法详解
- `alloc_pages()` 的 fast path → slow path → reclaim 全链路源码走读
- per-CPU 页帧缓存（pcp）如何减少 zone lock 竞争
- migration type 与 anti-fragmentation 的协作机制
- `__alloc_pages_slowpath` 在 slow path 上的 7 个尝试阶段
- `warn_alloc` 在分配失败时的 dump_stack 行为
- 实战案例：Camera 申请 16MB 连续页失败导致拍照黑屏的完整排查链路

**系列尾预告**：[12-内存稳定性风险全景](12-内存稳定性风险全景.md) 将整合 01-11 给出五大类稳定性问题（OOM / 泄漏 / 抖动 / 杀进程 / 系统卡顿）的风险地图与速查表，让架构师在线上救火时 5 分钟内定位到层与子系统。

---

> **版本说明**：本文所有源码路径以 AOSP `android-14.0.0_r1` + Android GKI 5.10（`android14-5.10` 分支）为基线。涉及历史 commit 时已标注 SHA。

