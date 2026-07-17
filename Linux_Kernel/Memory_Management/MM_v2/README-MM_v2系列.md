# 面向稳定性的 Android 内存架构深度解析系列

> **源码基线**：AOSP android-14.0.0_r1 + Android GKI 5.10
> **案例风格**：典型模式为主（你补的脱敏素材可替换）
> **目录位置**：`Linux_Kernel/Memory_Management/MM_v2/`

---

## 为什么要写这个系列

内存是 Android 稳定性问题的"最大单一来源"。在线上故障归因里，**OOM、内存泄漏、回收抖动、杀进程、内存压力引发的 ANR/卡顿**五类问题常年占据稳定性故障 Top 5。与 Window 系统（一个明确的服务、明确的边界）不同，Android 内存架构是**横跨 5 层**的分布式系统：

```
App 进程（Java 堆 + Native 堆 + 资源）
    ↓ 系统调用与信号
ART 虚拟机（GC、堆、Reference）
    ↓ JNI / binder
Framework（AMS 进程治理、LMKD 用户态杀手、PSI 压力监控）
    ↓ cgroup / kill -9 / 内存事件
Linux 内核 mm/（VMA、页分配器、SLAB、kswapd、Direct Reclaim、OOM Killer）
    ↓ MMU / DMA
硬件（DRAM、ION/DMA-BUF、zRAM）
```

每一层都可能出问题，每一层的问题表象可能相似但根因完全不同。**对稳定性框架架构师来说，不懂全栈就无法定位根因**——App 报"内存不足"可能是 Java 堆满了、Native 堆满了、Address Space 满了、cgroup 限额到了、内核 OOM Killer 触发了、LMKD 误杀了、zRAM 写满磁盘 I/O 死锁了……，每一类的诊断路径和治理手段都不同。

本系列的目标：**让你在 5 分钟内能从现象定位到层、定位到子系统、定位到源码入口，并给出可执行的治理方案**。

## 系列设计思路

```
Android 内存系统是什么？为什么 Google 要做这么复杂的多层架构？（定位）
    ↓
一个 byte 从 malloc 出发，到物理页帧落下，经过了哪些层？谁在管什么？（边界与交互）
    ↓
每一层（App / ART / Framework / LMKD / 内核 / 硬件）内部是怎么运转的？（核心机制）
    ↓
它会在什么场景下出问题？OOM / 泄漏 / 抖动 / 杀进程 / 压力 五大类风险如何识别？（风险地图）
    ↓
线上问题来了怎么查？dumpsys meminfo / procrank / PSI / Perfetto 怎么用？（诊断与治理）
```

```
                    ┌─────────────────────────────────────┐
                    │     诊断与治理（13 篇收尾）          │
                    │     dumpsys / procrank / PSI         │
                    └──────────────┬──────────────────────┘
                                   ↑
        ┌──────────────────────────┴──────────────────────────┐
        │  风险地图（12 篇汇总）                                │
        │  五大类稳定性问题速查表                               │
        └──────────────────────────┬──────────────────────────┘
                                   ↑
    ┌─────────────────────────────┼─────────────────────────────┐
    │   核心机制深潜（8-11 篇）   │                             │
    │   内核 mm/ 四大子系统       │   ART / Native 内存（02-04） │
    │   页分配 / SLAB / 回收       │                             │
    └─────────────────────────────┼─────────────────────────────┘
                                  ↑
            ┌─────────────────────┴─────────────────────┐
            │  Framework 治理（05-07）                   │
            │  AMS / LMKD / PSI / memcg                  │
            └─────────────────────┬─────────────────────┘
                                  ↑
                  ┌───────────────┴───────────────┐
                  │  全局观（01）                   │
                  │  一个 byte 的旅程               │
                  └───────────────────────────────┘
```

---

## 第一篇章：建立全局观（1 篇）

> 核心问题：Android 内存系统是什么？一个 byte 从 malloc 到物理页帧，经过了哪些层？每一层的职责是什么？

### [01-内存系统总览：从进程视角到硬件的完整链路](01-内存系统总览：从进程视角到硬件的完整链路.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. Android 内存系统是什么** | 五层架构定义；为什么不能像单片机那样直接管物理 RAM | — | 架构误解 → 排查方向跑偏 |
| **2. 为什么需要多层架构** | 单一层管不住的 4 个核心问题：地址空间隔离、资源配额、调度公平、回收策略 | — | 每一层解决什么问题 |
| **3. 全栈架构图** | App → ART → Framework → LMKD → 内核 → 硬件 五层 + 数据流 | 多个目录 | 定位问题在哪一层 |
| **4. 一个 byte 的旅程** | 从 `new byte[1024]` 到 256 个 4KB 页帧落定的完整路径 | `bionic/libc/bionic/malloc.cpp`、`mm/page_alloc.c` | 端到端理解"内存去哪了" |
| **5. 关键名词速查** | PSS / RSS / VSS / USS / memcg / oom_adj / oom_score_adj / PSI some-full | 多个目录 | 沟通时术语对齐 |
| **6. 内存指标全景** | dumpsys meminfo / procrank / /proc/meminfo / /proc/vmstat 字段含义 | 多个目录 | 看懂数字 |
| **7. 历史演进** | 内核 LMK → 用户态 LMKD、内核 4.x → 5.x → 6.x PSI、jemalloc → scudo | 多个目录 | 不同版本的兼容性问题 |
| **8. 五大类稳定性问题映射** | OOM / 泄漏 / 抖动 / 杀进程 / 卡顿 归类到层 | 多个目录 | 排查入口指引 |

---

## 第二篇章：进程与 ART 内存（3 篇）

> 核心问题：App 进程的内存长什么样？ART 堆怎么分代？Native 堆的 malloc 怎么选？

### [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. /proc/pid/maps 字段全解** | address / perms / offset / dev / inode / pathname 每一个字段的含义 | `fs/proc/task_mmu.c`、`fs/proc/base.c` | 看不懂 maps 字段 = 排查起点错 |
| **2. VMA 三类划分** | 代码段 / 堆 / 栈 / mmap 区 / [vdso] / [vsyscall] 各自来历 | `mm/mmap.c` | 内存段职责混淆 |
| **3. vm_area_struct 数据结构** | 红黑树 + 链表双索引设计；vm_flags 语义 | `include/linux/mm_types.h`、`include/linux/mm.h` | VMA 数量爆炸导致调度慢 |
| **4. mmap / munmap / brk / mprotect** | 系统调用源码走读 | `mm/mmap.c`、`mm/mprotect.c`、`mm/brk.c` | 调用模式 → 性能/稳定性 |
| **5. 私有映射 vs 共享映射** | COW 触发条件；refcount 与 page cache | `mm/memory.c` | 共享库未去重 → 内存浪费 |
| **6. VMA 合并与拆分** | can_vma_merge 的判断逻辑 | `mm/mmap.c` | VMA 碎片化 → 内核调度开销 |
| **7. 风险地图** | VMA 数量爆炸、JNI 局部引用表溢出、mmap 泄漏、ASLR 失效 | — | 各种 VMA 异常场景 |
| **8. 实战案例** | App 启动时 VMA 异常膨胀导致冷启动慢 30%（典型模式） | — | 端到端排查示范 |

### [03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. ART 堆的分代** | Young / Old / Zygote / Card Table / Region | `art/runtime/gc/heap.cc`、`art/runtime/gc/space/` | 堆分代策略 → GC 频率 |
| **2. GC 算法选型** | Concurrent Copying (CC) / Concurrent Mark Sweep (CMS) | `art/runtime/gc/collector/concurrent_copying.cc`、`art/runtime/gc/collector/concurrent_mark_sweep.cc` | 算法选择影响 pause 时长 |
| **3. ART 堆的"可见性"** | Concurrent GC 与 stop-the-world 的边界 | `art/runtime/gc/collector/` | STW 时长 → 主线程卡顿 |
| **4. Java 堆与 Native 堆的边界** | JNI 引用表：local / global / weak | `art/runtime/jni/jni_internal.cc`、`art/runtime/reflection.cc` | JNI 引用泄漏 |
| **5. 大对象分配** | LOS (Large Object Space) 与 HUMONGOUS 对象 | `art/runtime/gc/space/large_object_space.cc` | 大对象分配 → GC 退化 |
| **6. 内存压力下的 GC 行为** | Concurrent / Background / Foreground 三种模式切换 | `art/runtime/gc/heap.cc` | pressure GC → CPU 抢占 |
| **7. 风险地图** | 长 GC pause、Reference 泄漏、Finalizer 死锁、image space 损坏 | — | 高频 ART 异常 |
| **8. 实战案例** | CMS 退化 Concurrent 失败导致主线程 STW 1.5s（典型模式） | — | 排查路径示范 |

### [04-Native 堆内存与分配器（AOSP 14）](04-Native 堆内存与分配器（AOSP 14）.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. Android Native 内存的两条主线** | bionic malloc（scudo）+ 第三方（jemalloc、tcmalloc） | `bionic/libc/bionic/malloc.cpp`、`bionic/libc/bionic/scudo/` | 选型影响性能与可调试性 |
| **2. scudo 分配器** | Chunk / Size Class / Quarantine / Hardening | `bionic/libc/bionic/scudo/` | 越界检测、双重释放保护 |
| **3. malloc_debug** | malloc 钩子如何检测泄漏与越界 | `bionic/libc/malloc_debug/` | 调试模式 vs release 模式差异 |
| **4. JNI 与 Native 堆的"看不见"的内存** | ByteBuffer.allocateDirect、Bitmap.NativeAllocation | `frameworks/base/graphics/java/android/graphics/Bitmap.cpp` | "Java 堆"与"Native 堆"统计口径差异 |
| **5. 图形缓冲区内存** | ION / DMA-BUF / Gralloc 三方协作 | `drivers/staging/android/ion/`、`drivers/dma-buf/`、`hardware/interfaces/graphics/` | 显存占用与泄漏 |
| **6. 风险地图** | Native 泄漏难查的 5 个原因、Bitmap 分配在哪个堆、ION 泄漏 | — | 高频 Native 问题 |
| **7. 实战案例** | Bitmap.recycle() 漏调导致 Native 堆增长 800MB（典型模式） | — | 端到端排查示范 |

---

## 第三篇章：Framework 内存治理（3 篇）

> 核心问题：AMS 怎么管进程优先级？LMKD 怎么杀进程？内核压力怎么传到 Framework？

### [05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. 进程分类体系** | 前台 / 可见 / 后台服务 / 缓存 / 空 五类 | `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` | 分类 → 杀进程策略 |
| **2. oom_adj / oom_score_adj 体系** | 数值含义（-1000~1000+）、计算规则、Persist 与 System 例外 | `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` | adj 异常 → 杀错进程 |
| **3. adj 的更新时机** | Activity 生命周期、Service start/bind、锁屏、UID 切换 | `ActivityRecord.java`、`ServiceRecord.java` | 何时被重算 |
| **4. computeOomAdjLocked 源码** | 完整流程走读 | `OomAdjuster.java` | 理解 adj 计算细节 |
| **5. LMK → LMKD 演进** | 内核 LMK（drivers/staging/android/lowmemorykiller.c）退役原因 | `drivers/staging/android/lowmemorykiller.c` | 历史背景 |
| **6. 风险地图** | adj 异常导致误杀、Persist 进程配置错误、空进程数过多 | — | 高频治理问题 |
| **7. 实战案例** | Service 保活 + 锁屏后被误杀（典型模式） | — | 排查路径示范 |

### [06-LMKD 用户态内存杀手](06-LMKD 用户态内存杀手.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. LMKD 是什么 / 为什么迁到用户态** | 内核 LMK 的局限：策略僵化、调试困难、无法跨 cgroup | `system/memory/lmkd/` | 架构演进动机 |
| **2. 事件源** | vmpressure (旧) → PSI (新) / memcg watermark | `system/memory/lmkd/` | 不同 Android 版本的兼容 |
| **3. kill 决策** | min_score_adj 阈值、oom_score_adj 选择、kill 优先级 | `system/memory/lmkd/` | 杀谁不杀谁 |
| **4. 源码：主循环 / init / event handler** | lmkd.c / init.cpp / event.cpp 走读 | `system/memory/lmkd/` | 理解执行流 |
| **5. 风险地图** | 杀得太狠、杀得太慢、杀错进程、PSI 阈值错误 | — | 治理与监控 |
| **6. 实战案例** | 相机进程被 LMKD 误杀导致后台录像中断（典型模式） | — | 端到端排查示范 |

### [07-PSI / vmpressure / memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. PSI 是什么** | Pressure Stall Information，4.20 引入；some / full 区别 | `kernel/sched/psi.c`、`Documentation/accounting/psi.rst` | 压力监控基础设施 |
| **2. 字段语义** | avg10 / avg60 / avg300 / total | `kernel/sched/psi.c` | 阈值设置依据 |
| **3. /proc/pressure/memory 读取** | 用户态读取接口、轮询 / epoll | `fs/proc/proc_misc.c` | LMKD 的数据源 |
| **4. memcg 的作用** | 把 PSI 限制在 cgroup 范围内；foreground/background/top-app 隔离 | `kernel/memcontrol.c`、`fs/memcontrol.c` | foreground cgroup 内存隔离 |
| **5. PSI → LMKD 的事件通路** | 内核 → cgroup → /proc/pressure/memory → lmkd 事件循环 | 多个目录 | 端到端事件流 |
| **6. 风险地图** | PSI 阈值配置错误、cgroup 配置错误、压力持续时间误判 | — | 监控盲点 |
| **7. 实战案例** | foreground cgroup PSI full 持续 800ms 导致 ANR（典型模式） | — | 端到端排查示范 |

---

## 第四篇章：内核内存子系统（4 篇）

> 核心问题：物理内存怎么组织？页分配器怎么工作？小对象怎么分配？回收怎么触发？

### [08-物理内存组织-Node,Zone,Page,memblock](08-物理内存组织-Node,Zone,Page,memblock(GKI 5.10).md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. 启动早期：memblock 分配器** | 内核启动时的内存分配器，与 page allocator 的过渡 | `mm/memblock.c`、`include/linux/memblock.h` | 启动阶段内存分配 |
| **2. memblock_free_all：从 memblock 到 page_alloc** | 启动后期切换过程 | `mm/memblock.c`、`mm/page_alloc.c` | 切换时点 |
| **3. Node / Zone / Page 三层结构** | struct pglist_data、struct zone、struct page | `include/linux/mmzone.h`、`include/linux/mm_types.h` | 内存拓扑 |
| **4. ZONE_DMA / ZONE_NORMAL / ZONE_HIGHMEM / ZONE_MOVABLE** | 起源、设计动机、Android 实际配置 | `include/linux/mmzone.h`、`arch/arm64/mm/init.c` | 高端内存不可用问题 |
| **5. struct page 与页描述符** | arm64 上 64B 的内存代价；flags / mapping / lru 等字段 | `include/linux/mm_types.h` | 大页减少 struct page 开销 |
| **6. 水位线 (watermark) 机制** | min / low / high 三档；与 kswapd 协作 | `include/linux/mmzone.h`、`mm/page_alloc.c` | 触发回收的阈值 |
| **7. 风险地图** | zone 碎片化、高端内存不可用、低端机型 DMA 不足 | — | 各种 zone 异常 |
| **8. 实战案例** | 低端机型 ZONE_DMA 耗尽导致 camera 分配失败（典型模式） | — | 端到端排查示范 |

### [09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)](09-页分配器与伙伴系统(GKI 5.10)(GKI 5.10)(GKI 5.10)(GKI 5.10).md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. 伙伴系统原理** | order 0-10，2^k 阶，binary buddy 合并 | `mm/page_alloc.c` | 分配器基础算法 |
| **2. alloc_pages 核心流程** | fast path / slow path 分支 | `mm/page_alloc.c` | 分配性能 |
| **3. per-CPU 页帧缓存（pcp）** | 减少 zone lock 竞争 | `mm/page_alloc.c`、`include/linux/mmzone.h` | 多核扩展性 |
| **4. migration type** | MIGRATE_UNMOVABLE / MOVABLE / RECLAIMABLE / CMA / ISOLATE | `include/linux/mmzone.h` | 碎片化与迁移 |
| **5. watermark 提升：lowmem_reserve** | 保护低端 zone 不被高端 zone 借光 | `mm/page_alloc.c`、`include/linux/mmzone.h` | 多 zone 协调 |
| **6. __alloc_pages_slowpath** | 慢路径：尝试各种 zone、回收、CMA | `mm/page_alloc.c` | 慢路径的代价 |
| **7. 分配失败：warn_alloc** | 触发条件、dump_stack 行为 | `mm/page_alloc.c` | 排查入口 |
| **8. 风险地图** | order-5 分配失败、慢路径耗时、pcp 缓存命中率低 | — | 高频分配问题 |
| **9. 实战案例** | camera 申请 16MB 连续页失败导致拍照黑屏（典型模式） | — | 端到端排查示范 |

### [10-SLAB,SLUB 分配器与小对象分配(GKI 5.10)](10-SLAB,SLUB 分配器与小对象分配(GKI 5.10).md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. 为什么需要 SLAB** | kmalloc 的小对象需求、伙伴系统的浪费 | — | 分配器层次结构 |
| **2. SLUB 数据结构** | kmem_cache / kmem_cache_cpu / kmem_cache_node | `mm/slub.c`、`include/linux/slub_def.h` | 缓存拓扑 |
| **3. 分配/释放路径** | __kmem_cache_alloc_lru / kmem_cache_free | `mm/slub.c` | fast path / slow path |
| **4. SLAB 与 SLUB 的区别** | Android 默认 SLUB；为什么 SLUB 取代 SLAB | `mm/slab.c`、`mm/slub.c` | 兼容性背景 |
| **5. KASAN / KFENCE 钩子** | 越界 / UAF 检测、redzone | `mm/kasan/`、`mm/kfence/` | 调试与稳定性 |
| **6. 风险地图** | SLAB 泄漏、KASAN 报告风暴、SLAB 碎片 | — | 高频 SLAB 问题 |
| **7. 实战案例** | binder 驱动 SLAB 泄漏导致 kmalloc 失败（典型模式） | — | 端到端排查示范 |

### [11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10)](11-内存回收-kswapd,Direct Reclaim,LRU,MGLRU(GKI 5.10).md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. 为什么需要回收** | 内存是有限的；分配与回收的博弈 | — | 设计的根本动机 |
| **2. kswapd 异步回收** | balance_pgdat 主循环、kswapd 内核线程模型 | `mm/vmscan.c`、`include/linux/swap.h` | 后台回收 |
| **3. Direct Reclaim 同步回收** | __alloc_pages_slowpath 触发；性能代价 | `mm/vmscan.c`、`mm/page_alloc.c` | 同步阻塞 |
| **4. LRU 链表** | inactive_anon / active_anon / inactive_file / active_file 四链表 | `mm/swap.c`、`include/linux/swap.h`、`mm/vmscan.c` | 冷热页识别 |
| **5. 匿名页 swap 路径** | shrink_page_list → swap_writepage → zRAM/swap 设备 | `mm/swap.c`、`mm/swapfile.c` | 匿名页回收 |
| **6. 文件页回收** | drop_pagecache_sb / truncate / invalidate_mapping | `mm/truncate.c`、`fs/super.c` | 文件页回收 |
| **7. refault 机制** | workingset_refault；冷热页的动态调整 | `mm/workingset.c` | cache 命中率优化 |
| **8. swappiness 参数** | 100=倾向匿名、0=倾向文件 | `mm/vmscan.c` | 参数调优 |
| **9. 风险地图** | Direct Reclaim 抖动、swap 风暴、kswapd 卡死、refault 风暴 | — | 各种回收异常 |
| **10. 实战案例** | kswapd 卡死 5s 导致 App 启动卡顿（典型模式） | — | 端到端排查示范 |

---

## 第六篇章:补篇(1 篇)

> 核心问题:同一个 VMA 体系(02 篇)按"进程类型"反过来拆开看 ——Android 6 大类进程(zygote / system_server / app / native 守护进程 / kernel 线程 / init)的 /proc/pid/maps 分别长什么样?

### [14-Android 进程内存类型学](14-Android 进程内存类型学-zygote,system_server,app,kernel,native 守护进程.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **0. 写在前面的反问** | 02 讲通用 VMA 体系,本篇反过来按进程类型展开 | — | 看到 maps 能立刻判断是哪类进程 |
| **1. 6 大类进程分类总览** | zygote / system_server / app / native / kernel / init | 多个 | 进程类型速查 |
| **2. Zygote 进程** | preload 后的 maps 全貌、dex cache、印钞机模板 | `frameworks/base/`、`art/` | Zygote 内存膨胀导致所有 app 冷启动慢 |
| **3. App 进程** | fork Zygote 后的"差异化"、uid/namespace/SELinux | `bionic/`、`art/` | App 进程内存的 7 个关键观察点 |
| **4. system_server 进程** | 80+ 服务、Binder 线程池(128 × 8MB 栈) | `frameworks/base/services/` | system_server 内存爆炸触发系统卡顿 |
| **5. Native 守护进程** | init / lmkd / surfaceflinger / audioserver / cameraserver | `frameworks/av/`、`system/memory/lmkd/` | 单点重启导致依赖服务降级 |
| **6. Kernel 线程** | kthreadd / kworker / migration 看不到 maps 的根因 | `kernel/kthread.c`、`kernel/workqueue.c` | 看不见的杀手:内核栈 + struct page |
| **7. 跨进程视图** | dumpsys meminfo 的 PSS / RSS / SwapPss 解读 | `frameworks/base/core/java/android/os/Debug.java` | 跨进程内存拓扑 |
| **8. 6 大典型故障** | Zygote 膨胀 / system_server 爆炸 / App 泄漏 / 单点重启 / kernel OOM / RSS 失真 | — | 风险地图 |

---

## 第五篇章:性能、风险与诊断治理(2 篇)

## 第五篇章：性能、风险与诊断治理（2 篇）

> 核心问题：内存稳定性问题全景图怎么画？dumpsys / PSI / Perfetto 怎么用？监控体系怎么建？

### [12-内存稳定性风险全景](12-内存稳定性风险全景.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. 五大类问题分类** | OOM / 泄漏 / 抖动 / 杀进程 / 系统卡顿 | — | 顶层分类 |
| **2. 速查表（四列）** | 问题类型 / 日志关键字 / dumpsys 特征 / 排查入口 | — | 5 分钟定位 |
| **3. OOM 分类** | Java OOM / Native OOM / 系统 OOM / 杀进程触发 OOM | 跨篇 | 各种 OOM 模式 |
| **4. 泄漏分类** | Java 堆泄漏 / Native 堆泄漏 / 资源泄漏（fd/线程/Window） | 跨篇 | 各种泄漏模式 |
| **5. 抖动分类** | GC 抖动 / Direct Reclaim 抖动 / swap 抖动 / 锁竞争抖动 | 跨篇 | 各种抖动模式 |
| **6. 杀进程分类** | LMKD 误杀 / OOM Killer 杀 / Watchdog 杀 | 跨篇 | 各种杀进程模式 |
| **7. 跨篇章引用** | 本篇是其他 12 篇的"风险地图汇总" | 跨篇 | 串联各篇 |

### [13-内存稳定性诊断工具链](13-内存稳定性诊断工具链.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| --- | --- | --- | --- |
| **1. dumpsys meminfo 字段全解** | PSS / Private Dirty / Private Clean / Heap Size / Heap Alloc / Heap Free | `frameworks/base/core/java/android/os/Debug.java` | App 内存分析第一工具 |
| **2. procrank / procmem** | 排序看 TopN、按类别聚合 | `system/core/lmkd/procrank.cpp` | 系统级内存分析 |
| **3. /proc/meminfo / /proc/vmstat** | 内核视角的内存统计 | `fs/proc/meminfo.c`、`fs/proc/vmstat.c` | 内核指标 |
| **4. PSI 接口** | /proc/pressure/memory / /proc/cgroups | `fs/proc/proc_misc.c` | 压力监控 |
| **5. Perfetto 与 ftrace** | mm 事件追踪：page_alloc / kmalloc / vmscan | `kernel/trace/trace_mm.c` | 性能与时序分析 |
| **6. 监控体系设计** | 阈值、告警、归因、根因定位 | — | 治理体系 |
| **7. 治理最佳实践** | 内存基线、TopN 治理、版本回归 | — | 持续治理 |

---

## 与已有系列的交叉引用

| 内存主题 | 关联的系列 | 关联点 |
|---------|----------|--------|
| 进程内存地图 | [Window 02-创建与添加](../../../../Android_Framework/Window/02-Window的创建与添加.md) | Activity 创建时 Window Token 占用、Binder 缓冲区增长 |
| 进程优先级 (oom_adj) | [Window 10-WMS 锁竞争](../../../../Android_Framework/Window/10-WMS锁竞争与Watchdog.md) | system_server 优先级保护、Watchdog 杀进程 |
| 内存压力 → ANR | Input 系列 (../Input/) | PSI some/full → Input 事件分发延迟 |
| 内存压力 → 卡顿 | [Window 06-动画与转场](../../../../Android_Framework/Window/06-窗口动画与转场.md) | 内存压力 → Surface 分配失败 → 转场卡死 |
| 杀进程 → Cold Start | [Window 08-TTID/TTFD](../../../../Android_Framework/Window/08-窗口显示性能：TTID、TTFD与启动优化.md) | LMKD 杀后台 → 用户切回时冷启动 |
| 进程内存泄漏 | ART 系列（待建） | Java 堆泄漏 / Finalizer 队列 / Reference 持有 |
| 系统启动内存 | `Linux_Kernel/Process/` | init 进程内存、Zygote 内存 |
| Swap 与 zRAM | `Linux_Kernel/IO/` | zRAM 块设备 I/O 行为 |

---

## 阅读建议

### 如果你时间有限，优先阅读：

1. **[01 总览]** — 建立全局观，理解五层架构和"一个 byte 的旅程"。
2. **[12 风险全景]** — 速查表 + 五大类问题分类，先看这张图能省 80% 排查时间。
3. **[13 诊断工具]** — dumpsys / procrank / PSI / Perfetto 速查，工具箱式阅读。
4. **[07 PSI/压力传递]** — 理解"内存压力"是怎么从内核传到 Framework 的，连接应用与系统。
5. **[11 内存回收]** — 理解 Direct Reclaim / kswapd 抖动的根因，高频性能问题来源。

### 如果你要系统学习，按顺序阅读 01 → 13：

```
01 总览（建立全局观）
    ↓
02-04 进程与 ART（应用层内存机制）
    ↓
05-07 Framework 治理（AMS、LMKD、PSI）
    ↓
08-11 内核 mm/（物理组织、分配器、SLAB、回收）
    ↓
12 风险全景（横向速查）
    ↓
13 诊断工具（垂直工具箱）
```

### 每篇文章的设计逻辑：

```
背景与定义（是什么、为什么需要它、解决什么问题）
    → 架构与交互（在系统中的位置、上下游关系）
        → 核心机制与源码（关键数据结构、核心流程）
            → 稳定性风险点（会在哪里出问题）
                → 实战案例（典型模式排查过程）
                    → 总结（架构师视角的 Takeaway）
                        → 附录（核心源码路径索引）
                            → 篇尾衔接（下一篇预告）
```

---

## 进度

- [x] Step 2: 系列 README（本文档）
- [x] Step 3a: 首批试点 3 篇（01 总览 + 02 VMA + 12 风险全景）— 2026-06-11
- [x] Step 3b: 第二批 4 篇（03 ART GC + 05 AMS + 06 LMKD + 07 PSI）— 2026-06-12
- [x] Step 3c: 第三批 4 篇（04 Native/scudo + 08 物理组织 + 09 页分配 + 10 SLAB）— 2026-06-13
- [x] Step 3d: 第四批 2 篇（11 回收 + 13 诊断工具链）— 2026-06-15
- [x] Step 4: verifier 审计 + 修复（11 MAX_ORDER box、06 ADJ 笔误补正）
- [x] Step 5: 跨篇链接校正（57 处 04/08/09/10/11/13 文件名不一致，全部已修）

**全 14 篇(13 + 1 补篇) 100% 落地，目录位置**：`Linux_Kernel/Memory_Management/MM_v2/`。**总规模** ≈ 1.0 MB / ~14 万字。

### 后续补强项（可选）

- 05 AMS 30+ 处 AMS 内部 API 名字细节瑕疵（override_accept 残留，质量风险低）
- 06 LMKD line 354/356 adj 范围不精确（低严重性）
- 各篇引入"实战案例脱敏素材"替换（用户身份解锁后）
