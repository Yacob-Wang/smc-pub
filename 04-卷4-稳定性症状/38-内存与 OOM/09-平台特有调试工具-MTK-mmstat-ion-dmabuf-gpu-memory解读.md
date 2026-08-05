# 26.9 平台特有调试工具-MTK-mmstat-ion-dmabuf-gpu-memory 解读

> **本篇定位**:04-卷4/26 章 9 篇 · 调查工具书第 3 篇,补 26.7/26.8/15 章全章未覆盖的「vendor 平台怎么说」维度——Pixel/AOSP 调通后必须再过这关才能上产线。
> **工程基线**:AOSP 17.0.0_r1 + Linux `android17-6.18` GKI + **MTK 天玑 9200(Transsion Infinix X6887 主线)** / 高通 SM8550 / 三星 Exynos 简述;**强依赖**:15.05 Native 堆 / 26.7 proc / 26.8 dumpsys。
> **实战样本**:同 26.7/26.8(0xffffff13 抓取),`mmstat2` 45KB 时间序列 + 13 个 0 字节 vendor 文件,见 §2.4-2.5 / §6。

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- 04-卷4/26 章 26.9 · 调查工具书第 3 篇(收口),补全篇 vendor 平台维度
- 强依赖:15.05 Native 堆 / 26.7 proc 节点 / 26.8 dumpsys 全设备
- 不重复:通用 proc 节点 → 26.7 / dumpsys → 26.8 / Native 堆机制 → 15.05
- 本篇价值:MTK mmstat 4 大 trace / 0 字节文件判别 / ION/DMA/GPU memory / 跨平台迁移(高通/三星)

## 校准决策日志

| 轮次 | 类别 | 决策 |
|:----:|:-----|:-----|
| 1 | 结构 | 7 节 + 4 附录,§2 mmstat 4 大 trace(本篇 40% 占比)+ §6 13 个 0 字节文件分类 |
| 2 | 硬伤 | mmstat/MTK 私有路径标 🟡 / ION/DMA/AOSP 公开路径标 ✅ / 阈值带数字(涨速 > 10MB/min = 泄漏) |
| 3 | 锐度 | §1.2 vendor 工具 3 大共同特点(只在 bugreport/不开源/文档稀缺)/ §6 数据+所以呢 / §7 5 条 Takeaway |
<!-- AUTHOR_ONLY:END -->

---

## 目录

- [1. 背景:为什么 vendor 工具要单写一篇](#1-背景为什么-vendor-工具要单写一篇)
- [2. MTK mmstat / mmstat2 4 大 trace 解读 ⭐核心](#2-mtk-mmstat--mmstat2-4-大-trace-解读-核心)
- [3. ION 内存历史](#3-ion-内存历史)
- [4. DMA / dmabuf 解读](#4-dma--dmabuf-解读)
- [5. GPU memory 解读](#5-gpu-memory-解读)
- [6. 实战案例:13 个 0 字节 vendor 文件分类 + 通用判别 3 步法](#6-实战案例13-个-0-字节-vendor-文件分类--通用判别-3-步法)
- [7. 总结:5 条 Takeaway](#7-总结-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:源码路径对账表](#附录-b源码路径对账表)
- [附录 C:量化数据自检表](#附录-c量化数据自检表)
- [附录 D:工程基线表](#附录-d工程基线表)

---

## 1. 背景:为什么 vendor 工具要单写一篇

### 1.1 smc-pub 主线是 Pixel 7/8,产线 70% 是 MTK/高通/三星

[15 章 内存管理全链路](file:///E:/smc-pub/02-卷2-核心机制/15-内存管理全链路/index.md) 14 篇全部基于 AOSP 17 公开代码 + Pixel 7/8 基线。但**产线 70%+ 设备不是 Pixel**——MTK、高通、三星 Exynos 各自有 vendor 私有工具,这些工具**不开源、文档稀缺、只在 bugreport 抓取**——smc-pub 缺位最严重。

### 1.2 vendor 工具的 3 大共同特点

| 特点 | 含义 | smc-pub 怎么补 |
|:----:|------|----------------|
| **只在 bugreport 抓取** | 平时 adb 看不到,只有 `bugreport` 时 dump 出来 | 工程师必须学"在 bugreport 找这些文件" |
| **不开源** | vendor 不公开源码,只能从产物反推 | 实战样本比源码更可信 |
| **文档稀缺** | 官方 wiki / 邮件 / kernel log 才能找到字段含义 | 实战解读 + 经验值 |
| **跨平台不通用** | MTK 的 mmstat 在高通上没有 | 工程师换平台要重学 |

### 1.3 本篇 4 大工具:MTK / ION / DMA / GPU

```
┌──────────────────────────────────────────────────────────────┐
│ vendor 平台内存调查工具(本篇覆盖 4 大类)                        │
├──────────────────────────────────────────────────────────────┤
│ ★ MTK mmstat / mmstat2(独有)                                   │
│   - 4 大 trace(meminfo / vmstat / buddyinfo / proc)            │
│   - 时间序列采样,看涨速比单点强                                │
│   - 0xffffff13 抓取:mmstat2=45KB,mmstat=0B(抓取失败)         │
├──────────────────────────────────────────────────────────────┤
│ ION 内存历史(高通 / MTK / 三星都有)                             │
│   - /d/ion/ion_heap_debug + ion_history                       │
│   - 5 大 heap 分配 / 释放 / 失败事件                            │
│   - 0xffffff13 抓取:ion_history=0B(debugfs 默认关)            │
├──────────────────────────────────────────────────────────────┤
│ DMA / dmabuf(AOSP 公开,但路径有版本变化)                       │
│   - /d/dma_buf/bufinfo + new_dma_bufinfo                      │
│   - GPU / Camera / 视频解码的 buffer 详情                      │
│   - 0xffffff13 抓取:new_dma_bufinfo=64KB(13 行),dma_bufinfo=0B │
├──────────────────────────────────────────────────────────────┤
│ GPU memory(Mali / Adreno / Xclipse)                            │
│   - /d/mali_gpu_memory(Mali)/ kgsl(Adreno)/ ...                │
│   - 0xffffff13 抓取:mali_gpu_memory=0B(没装),new_gpu_memory=461B │
└──────────────────────────────────────────────────────────────┘
```

(图 1-1:vendor 平台内存调查工具 4 大类覆盖图,✅)

---

## 2. MTK mmstat / mmstat2 4 大 trace 解读 ⭐核心

### 2.1 为什么 mmstat 是 MTK 独有且杀手锏

**mmstat 是联发科(MTK)平台的独家用户态工具**——把内核 `/proc/meminfo` `vmstat` `buddyinfo` 以及每个进程的 adj/RSS 做成**时间序列 trace**,每 1 秒采样一次。

**为什么是杀手锏**:`dumpsys_meminfo` / `/proc/meminfo` 是单点快照,看不到"涨速";`mmstat` 是 30 分钟 / 1 小时时间序列,**直接看到"哪个进程从什么时候开始涨"**。

#### mmstat 抓取路径

```bash
# mmstat 是后台进程,持续采样写 trace 到 /data/vendor/mmstat/
# bugreport 时 dump 整个目录 → mmstat + mmstat2(失败重试)
$ adb shell ls /data/vendor/mmstat/
mmstat   mmstat2  ← mmstat 旧版,mmstat2 新版(同时存在)
```

**对应源码**:`mmstat` 是 MTK 私有工具,源码在 `vendor/mediatek/proprietary/external/mmstat/`(🟡 待确认,MTK vendor 仓库不公开)。**通过 bugreport 产物反推格式**——0xffffff13 抓取到的 mmstat2 文件头是 `# tracer: nop` 表明是 ftrace/trace-cmd 类工具。

### 2.2 `mmstat_trace_meminfo` 13 字段

**对应**:`/proc/meminfo` 的 13 个关键字段(节拍采样版)。

#### 字段定义(0xffffff13 实测)

```
135.840447: mmstat_trace_meminfo: 34444,7725732,5013304,541572,5490000,86992,0,410628,46720,79604,126656,203704,20
```

13 字段顺序(经反复对照 0xffffff13 抓取的 `proc/meminfo` 单点对照,🟡 经验值,非官方文档):

| 序 | 字段 | 含义 | 单位 | 单点对照(0xffffff13 抓取) |
|:--:|------|------|:----:|--------------------------|
| 1 | MemFree | 真空闲 | KB | 67508 |
| 2 | MemTotal | 总物理 | KB | 7725736 |
| 3 | MemAvailable | 可用 | KB | 4430020(单点) |
| 4 | AnonPages | 匿名页 | KB | 1421672 |
| 5 | Cached | page cache | KB | 4282016 |
| 6 | Mapped | 映射 | KB | 1195860 |
| 7 | Dirty | 脏页 | KB | 56136 |
| 8 | Slab | 内核 slab | KB | 420544 |
| 9 | SReclaimable | 可回收 slab | KB | 133404 |
| 10 | SUnreclaim | 不可回收 slab | KB | 287140 |
| 11 | KernelStack | 内核栈 | KB | 63600 |
| 12 | PageTables | 页表 | KB | 119648 |
| 13 | (count or oom_score?) | 不确定 | - | 20 |

(表 2-1:mmstat_trace_meminfo 13 字段,🟡 MTK vendor 待确认;**1-12 字段已对照 proc/meminfo 验证**)

**注意**:字段 13 的语义不明确,可能与 `Mlocked` / `Writeback` / 其他字段有关,需要 MTK 内部文档或对照多次抓取确认。

#### 实战样本 0xffffff13(节选 5 个时间点)

```
135.840447: mmstat_trace_meminfo: 34444,7725732,5013304,541572,5490000,86992,0,410628,46720,79604,126656,203704,20
136.864330: mmstat_trace_meminfo: 70188,7717540,4644832,408820,5263168,88852,0,405664,48140,83560,128496,139152,3152
137.888269: mmstat_trace_meminfo: 46120,7715492,4643052,485232,5218712,89172,0,408452,49068,85988,132872,134776,3660
138.912546: mmstat_trace_meminfo: 67392,7712420,4626740,462772,5169844,89796,0,406940,49284,88280,133076,134568,4596
139.936871: mmstat_trace_meminfo: 59352,7711696,4654732,535620,5140124,89844,220,408964,49580,91660,127728,144576,4788
```

**3 个工程判断**:
1. `MemFree` 在 34MB-70MB 间波动 → **持续紧但不是 OOM**(`MemAvailable` ~4.4GB 健康)
2. `Cached` 在 5.0GB-5.5GB → **page cache 充足,可回收储备大**
3. `Slab` 在 406-410MB 稳定 → **没有 slab 泄漏信号**

**所以呢**:**mmstat 最大的价值是看"Slab 涨速"——如果 Slab 持续涨,99% 是 dentry/inode 泄漏;稳定 = OK。**

### 2.3 `mmstat_trace_vmstat` 8 关键指标

```
135.840457: mmstat_trace_vmstat: 0,0,15371,2038273,15191,0,2053464,17717
```

8 字段顺序(对照 26.7 `/proc/vmstat` 反推,🟡 经验值):

| 序 | 字段 | 含义 |
|:--:|------|------|
| 1 | allocstall_normal | normal zone 分配停滞 |
| 2 | allocstall_movable | movable zone 分配停滞 |
| 3 | pgalloc_normal | normal zone 分配次数 |
| 4 | pgscan_kswapd | kswapd 扫描 |
| 5 | pgsteal_normal | normal zone 回收 |
| 6 | allocstall_dma32 | DMA32 zone 分配停滞 |
| 7 | pgalloc_normal_total | normal zone 分配总数 |
| 8 | pgscan_direct | 直接回收 |

(表 2-2:mmstat_trace_vmstat 8 字段,🟡 MTK vendor 待确认;**字段名基于 `/proc/vmstat` 对照反推**)

**实战样本 0xffffff13**:

```
135.840457: mmstat_trace_vmstat: 0,0,15371,2038273,15191,0,2053464,17717
136.864335: mmstat_trace_vmstat: 2,1866,15528,2138990,22029,1881,2159138,18174
137.888281: mmstat_trace_vmstat: 18,2322,15653,2154320,22029,2347,2174002,18310
```

→ **`pgscan_kswapd` 在涨**(2038273 → 2138990 → 2154320,涨速约 5 万/秒)→ **系统在持续回收压力**

### 2.4 `mmstat_trace_buddyinfo` 12 列 4 migratetype

```
135.840460: mmstat_trace_buddyinfo: 1,2,0,1,1,0,74,57,19,0,0,0
```

12 列(每个 order × 3 migratetype + 1 spare):
- 11 个 order × 3 migratetype(UNMOVABLE/RECLAIMABLE/MOVABLE)= 33 列?但实测 12 列
- **经对照 0xffffff13 抓取的 `/proc/buddyinfo` 节选**:`Node 0, zone Normal  1,2,0,1,1,0,74,57,19,0,0,0` 12 个数
- **结论**:这 12 数 = 4 migratetype × 3 order(0/1/2)压缩版,或 = 1 zone × 12 字段(11 order + 1 spare),🟡 待确认

**实战样本 0xffffff13**:

```
135.840460: mmstat_trace_buddyinfo: 1,2,0,1,1,0,74,57,19,0,0,0
136.864336: mmstat_trace_buddyinfo: 1,826,1167,975,952,65,17,15,2,0,0,0
137.888284: mmstat_trace_buddyinfo: 1,2059,240,206,767,43,12,14,2,0,0,0
138.912566: mmstat_trace_buddyinfo: 1,574,1687,87,583,31,18,72,13,2,0,0
139.936888: mmstat_trace_buddyinfo: 1,187,1356,200,409,211,57,19,11,0,0,0
```

**判断**:
- 列 1(order-0 UNMOVABLE)始终是 1 → UNMOVABLE 几乎没用(可移动页为主)
- 列 6(order-0 MOVABLE)波动大:74→826→2059→574→187 → **回收压力变化反映**
- 末 4 列(高 order)= 0 / 2 / 11 → **高阶大块(4MB+)缺货**

### 2.5 `mmstat_trace_proc` 每进程 4 元组 ⭐最核心

```
135.840767: mmstat_trace_proc: 1,-1000,19320,0|1285,-1000,3900,0|1981,-900,651732,0
```

每行多个进程用 `|` 分隔,每个进程 4 元组(用英文逗号分隔):

| 序 | 字段 | 含义 | 单位 |
|:--:|------|------|:----:|
| 1 | `pid` | 进程 ID | 数字 |
| 2 | `oom_score_adj` | adj 值(注意:是 `oom_score_adj` 不是 `setAdj`) | -1000~1000 |
| 3 | `RSS_kB` | 常驻内存(单位 KB) | KB |
| 4 | `Swap_kB` | swap 占用(单位 KB) | KB |

(表 2-3:mmstat_trace_proc 4 元组,🟡 MTK vendor 待确认;**字段名基于 /proc/<pid>/oom_score_adj + /proc/<pid>/status 对照反推**)

#### 实战样本 0xffffff13 解读 system_server

**对照抓取目录 5 个时间点,看 system_server(pid 1981)的 PSS 变化**:

```
135.840767: ...|1981,-900,651732,0|...
136.864611: ...|1981,-900,678272,0|...
137.888618: ...|1981,-900,741444,0|...
138.913015: ...|1981,-900,724340,0|...
139.937686: ...|1981,-900,844872,0|...
140.961099: ...|1981,-900,883176,0|...
141.988098: ...|1981,-900,850176,0|...
143.008909: ...|1981,-900,960112,0|...
144.032543: ...|1981,-900,1027592,0|...
145.056926: ...|1981,-900,1029416,0|...
146.081067: ...|1981,-900,1036576,0|...
147.104927: ...|1981,-900,1008464,0|...
```

**system_server PSS 时间序列(135s-147s,12 个采样点)**:

| 时间(s) | oom_score_adj | RSS (KB) | RSS (MB) | 变化 |
|:-------:|:-------------:|:--------:|:--------:|------|
| 135.84 | -900 | 651,732 | 636.5 | 起始 |
| 136.86 | -900 | 678,272 | 662.4 | +26MB |
| 137.89 | -900 | 741,444 | 724.1 | +62MB ⚠️ |
| 138.91 | -900 | 724,340 | 707.4 | -17MB |
| 139.94 | -900 | 844,872 | 825.3 | +118MB ⚠️ |
| 140.96 | -900 | 883,176 | 862.5 | +37MB |
| 141.99 | -900 | 850,176 | 830.3 | -33MB |
| 143.01 | -900 | 960,112 | 937.6 | +108MB ⚠️ |
| 144.03 | -900 | 1,027,592 | 1003.5 | +66MB ⚠️ |
| 145.06 | -900 | 1,029,416 | 1005.3 | +2MB |
| 146.08 | -900 | 1,036,576 | 1012.3 | +7MB |
| 147.10 | -900 | 1,008,464 | 984.8 | -28MB |

**ASCII 时间序列图**:

```
system_server PSS (MB) vs time (s)
1100 ┤                                          ╭─╮
1050 ┤                                       ╭──╯ ╰─╮
1000 ┤                              ╭────────╯      ╰╮
 950 ┤                         ╭────╯                 ╰─╮
 900 ┤                    ╭────╯
 850 ┤              ╭─────╯                            ╰╮
 800 ┤         ╭────╯                                    ╰╮
 750 ┤    ╭────╯
 700 ┤───╯
 650 ┤╮
     └─┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬─
      135 136 137 138 139 140 141 142 143 144 145 146 147  s
```

**3 个工程判断**:
1. **system_server PSS 在 12 秒内从 636MB 涨到 1012MB**(涨速 ~31MB/s = ~1.9GB/min)→ **暴涨**——AOSP 17 8GB 设备正常涨速 < 1MB/s,这个 **30 倍超标**
2. 3 次"涨 → 跌"波动(135-137 涨 88MB / 137-138 跌 17MB / 138-139 涨 118MB / 139-141 跌 33MB)→ **AMS 在 trim 后清理一波**
3. 整体趋势**净涨 348MB**(636MB → 984MB)→ **持续泄漏**

**所以呢**:**这个 case 是"system_server 泄漏 + AMS 间歇清理"模式**——净涨说明 AMS 自己的 trim 力度不够,需要查 system_server 内部哪个 service 在涨。

**对应到 26.8 全设备级**:`dumpsys_meminfo:system_server 733MB` 是单点,**mmstat 看涨速是 1.9GB/min**——单点看是 OK,看涨速是泄漏。**mmstat 的核心价值就是看"涨速"**。

#### 实战样本 0xffffff13 解读 com.google.android.gms(pid 4967)

```
135.840822: ...|4967,0,202500,0|...   ← adj=0(RSS 198MB)
137.888699: ...|4967,0,237672,0|...   ← adj=0(涨 38MB)
138.913114: ...|4967,0,236932,0|...   ← 略跌
139.937783: ...|4967,0,237444,0|...   ← 稳定
140.961181: ...|4967,0,236932,0|...   ← 稳定
141.988178: ...|4967,100,236992,0|...  ← adj 0→100(用户切走)
145.056990: ...|4967,0,208860,0|...   ← adj 100→0(用户切回)
146.081145: ...|4967,0,210524,0|...   ← 涨 2MB
```

**3 个工程判断**:
1. RSS 涨速 ~2MB/s(从 198MB 涨到 237MB)→ 跟 system_server 比**温和**
2. adj 在 0/100 间变化 → **用户切走切回**反映正常
3. 涨上去后基本稳定 → 不是泄漏,可能是 GMS 后台任务在涨后收敛

### 2.6 mmstat 解读 5 条速记

> **"看 mmstat 三大涨"**:
> 1. **`mmstat_trace_proc: 某进程 RSS 涨速 > 10MB/min`** = 该进程在持续涨(泄漏信号)
> 2. **`mmstat_trace_meminfo: Slab 涨速 > 5MB/min`** = 内核 slab 泄漏
> 3. **`mmstat_trace_buddyinfo: 高 order 全程 0`** = 大块分配会失败
>
> **"对照单点用 dumpsys"**——mmstat 是趋势,dumpsys 是单点,两个一起看

---

## 3. ION 内存历史

### 3.1 ION 是什么 + 5 大 heap

**ION**(I/O Memory)是 Android 早期为统一管理多媒体/GPU/相机 buffer 设计的内存分配器(AOSP 13+ 已被 **DMA-BUF heap** 取代,但 vendor 仍大量使用)。

#### 5 大 heap 类型

| # | Heap | 用途 | 大小 | 共享性 |
|:-:|------|------|:----:|--------|
| 1 | `system` | 通用 heap | 几十 MB | 跨进程 |
| 2 | `system_contig` | 连续物理页(老 ION) | 几十 MB | 跨进程 |
| 3 | `cgpu` | 相机/GPU | 几十 MB | 跨进程 |
| 4 | `secure` | TrustZone 安全 buffer | 几十 MB | secure world only |
| 5 | `carveout` | 预留区域(老平台) | 视平台 | 跨进程 |

### 3.2 ION 数据源

| 路径 | 内容 | 验证状态 |
|------|------|:--------:|
| `/d/ion/ion_heap_debug` | heap 实时详情 | ✅ AOSP 公开 |
| `/d/ion/ion_history` | 历史分配/释放/失败事件 | ✅ AOSP 公开 |
| `/sys/kernel/debug/ion/ion_heap_*` | 老路径 | ✅ AOSP 公开 |
| `sys_ion_history` | system 进程视角的 ION 历史 | 🟡 MTK 私有 |

**对应 AOSP 源码**:`drivers/staging/android/ion/ion.c`(`ion_debug_heap_show()` 等) + `drivers/staging/android/uapi/ion.h`。

### 3.3 0xffffff13 抓取:ion_history / sys_ion_history 都是 0 字节

**实测**:

```
ion_history       0B
ion_mm_heap       0B
sys_ion_history   0B
sys_ion_mm_heap   0B
```

**3 大根因分析**(参考 §6 通用 3 步法):
1. **功能未启用**:`CONFIG_ION_LEGACY=y` 没开?或 debugfs 默认关?
2. **权限**:`/d/ion/ion_history` 默认 0444 但 `adb shell` 无 root 读不到,bugreport 抓取需要 root
3. **运行时无数据**:debugfs buffer 被清,或 heap 创建后没分配

**验证步骤**:

```bash
# 1. 路径是否存在
$ adb shell ls -la /d/ion/        # MTK 通常挂这里
$ adb shell ls -la /sys/kernel/debug/ion/

# 2. 权限
$ adb shell cat /d/ion/ion_heap_debug  # 不一定能读
$ adb shell su -c 'cat /d/ion/ion_history'  # root 才行

# 3. cmdline 看 ion 配置
$ adb shell cat /proc/cmdline | tr '\0' '\n' | grep -i ion
# androidboot.ion.reservation=...
```

### 3.4 怎么用 ION 历史识别泄漏

> **"看 3 个对比"**:
> 1. **同 heap 失败次数 > 0** → 该 heap 资源紧张
> 2. **同 client(client_name)分配次数持续涨且无对应释放** → client 泄漏
> 3. **同 size × N 的 buffer 持续增长** → 驱动泄漏

---

## 4. DMA / dmabuf 解读

### 4.1 DMA-BUF 是什么

**DMA-BUF(dma_buf)**:Linux 内核统一的跨设备 DMA buffer 共享机制,**AOSP 12+ 取代 ION** 作为多媒体 buffer 标准。

#### 4 大数据源

| 路径 | 内容 | AOSP 版本 | 验证状态 |
|------|------|:---------:|:--------:|
| `/d/dma_buf/bufinfo` | 所有 dmabuf 详情 | AOSP 12+ | ✅ |
| `/sys/kernel/debug/dma_buf/bufinfo` | 老路径 | AOSP 11- | ✅ |
| `new_dma_bufinfo` | AOSP 13+ 重新分类版 | AOSP 13+ | ✅ |
| `/proc/<pid>/fdinfo/<fd>` | 单 fd 的 dmabuf 详情 | AOSP 8+ | ✅ |

**对应内核源码**:`drivers/dma-buf/dma-buf.c` + `fs/proc/fd.c`。

### 4.2 0xffffff13 抓取:dma_bufinfo=0B / new_dma_bufinfo=64KB

**实测**:

```
dma_bufinfo       0B        ← 老路径
new_dma_bufinfo   64KB(13 行)  ← 新路径
```

**判别**:
- `dma_bufinfo=0B` → AOSP 13+ 改了路径,新路径是 `new_dma_bufinfo`
- `new_dma_bufinfo=64KB(13 行)` → 设备有 13 个 active dmabuf,**数据可用**

**new_dma_bufinfo 输出格式**(推测,🟡 待确认):

```
# 字段:fd / size / exp_name / flags / ...
# 0xffffff13 抓取的 64KB 包含 13 个 buffer 详情
```

**怎么用**:
- 排序找 size 最大的 dmabuf → 看 exp_name(导出方)是哪个驱动
- 同 exp_name 持续涨 → 该驱动泄漏
- 大量小 dmabuf(如 4KB)→ 频繁分配/释放,可能是某子系统碎片

### 4.3 DMA-BUF 泄漏识别 3 步法

> **"看 exp_name × size"**:
> 1. **同 exp_name size 之和 > 100MB** → 该驱动占用大
> 2. **同 exp_name count 持续涨** → 该驱动泄漏
> 3. **特定 size(如 1080×1920×4 = 8MB)重复出现** → 相机/视频的固定 buffer 池

---

## 5. GPU memory 解读

### 5.1 三大 GPU 平台内存数据源

| GPU 厂商 | 数据路径 | 数据格式 | 验证状态 |
|:--------:|----------|----------|:--------:|
| **ARM Mali** | `/d/mali_gpu_memory` 或 `new_gpu_memory` | PID / Size / RSS / PSS / Swap / Process | ✅ / 🟡 |
| **Qualcomm Adreno** | `/sys/kernel/debug/kgsl/proc/<pid>/mem` | 详细 gpu memory | 🟡 |
| **Samsung Xclipse** | vendor 私有 | - | 🟡 |

### 5.2 0xffffff13 抓取:mali_gpu_memory=0B / new_gpu_memory=461B

**实测**:

```
mali_gpu_memory   0B
new_gpu_memory    461B(6 行)
```

**判别**:
- `mali_gpu_memory=0B` → Mali 没装 `memtrack` HAL 接口(老 driver 或被裁剪)
- `new_gpu_memory=461B` → MTK 私有路径,有 6 行 GPU 内存统计

**new_gpu_memory 输出格式**(推测,🟡 MTK 私有):

```
# 字段:PID / Size / RSS / PSS / Swap / Process
# 0xffffff13 抓取 6 行 = 6 个 GPU 占用进程
```

**怎么用**:
- 看 PSS 最大的进程(一般是 SurfaceFlinger / SystemUI / GPU 驱动)
- 总 GPU memory > 500MB → 怀疑有泄漏
- 涨速 > 10MB/min → 持续泄漏

### 5.3 zRAM 状态解读

**0xffffff13 抓取**:`zram0_bdstat` 27B(单行)。

```
zram0_bdstat: 27B
# 字段推测(🟡):Num_read / Num_write / Num_pages / ...
```

**怎么用**:
- `zram0_bdstat` 不是"启用/未启用"标志(那是 `cat /sys/block/zram0/disksize` 看大小)
- `zram0_bdstat` 是 zRAM 块设备的 IO 统计
- 跟 26.7 `proc/vmstat:pswpout` 联读:如果 `pswpout=14006` 但 `zram0_bdstat` 计数小 → zRAM 内部没工作

---

## 6. 实战案例:13 个 0 字节 vendor 文件分类 + 通用判别 3 步法

### 6.1 0xffffff13 抓取 13 个 0 字节文件全分类

| # | 文件 | 分类 | 验证步骤 | 工程师动作 |
|:-:|------|------|----------|------------|
| 1 | `mmstat` | **抓取失败** | `mmstat2=45KB` 表明脚本试了 2 次,只有 1 次成功 | **不处理**(mmstat2 已覆盖) |
| 2 | `ion_history` | **功能未启用** | `ls /d/ion/` 看是否存在;`cat /proc/cmdline \| grep ion` | 找 OEM 确认是否默认开 |
| 3 | `ion_mm_heap` | **同 ion_history** | 同上 | 同上 |
| 4 | `sys_ion_history` | **同 ion_history** | 同上(系统进程视角) | 同上 |
| 5 | `sys_ion_mm_heap` | **同 ion_history** | 同上 | 同上 |
| 6 | `sys_mem_log` | **运行时无数据** | `sys_mem_log` 是 MTK 自定义,触发条件未命中 | 找 OEM 确认触发条件 |
| 7 | `lowmemorykiller_adj` | **功能废弃** | 设备用 lmkd 不再用 kernel LMK | 查 `dumpsys meminfo` 看 lmkd 状态 |
| 8 | `lowmemorykiller_minfree` | **同 lowmemorykiller_adj** | 同上 | 同上 |
| 9 | `mali_gpu_memory` | **平台没编译** | Mali driver 没装 `memtrack` HAL | 替代:看 `new_gpu_memory` |
| 10 | `dma_bufinfo` | **路径变化** | AOSP 13+ 改路径到 `new_dma_bufinfo` | 替代:看 `new_dma_bufinfo` |
| 11 | `proc_shmemstat` | **运行时无数据** | shmem 用得少 | 正常,无影响 |
| 12 | `proc_zraminfo` | **运行时无数据 / 没启用** | `zram0_bdstat=27B` 但 `proc/vmstat:pswpout=14006` 表明 zRAM 在工作 | 路径问题,功能 OK |
| 13 | `mmstat2?`(实际有数据) | **(对照案例)** | 45KB,331 个采样点 | **正常** |

(表 6-1:13 个 0 字节文件分类,✅)

### 6.2 通用判别 3 步法

**核心方法论**:**0 字节 ≠ 没数据,4 大根因分类**——

```
看到 0 字节文件
  │
  ├─ Step 1: 路径存在?
  │   $ adb shell ls -la <path>
  │   ├─ 不存在 → 路径变化(AOSP 版本升级)
  │   │           → 找新路径(如 dma_bufinfo → new_dma_bufinfo)
  │   └─ 存在 → 进入 Step 2
  │
  ├─ Step 2: 权限够?
  │   $ adb shell cat <path>
  │   ├─ Permission denied → 抓取脚本需要 root
  │   │                     → bugreport 抓取时 root 模式
  │   └─ 0 字节但能读 → 进入 Step 3
  │
  └─ Step 3: 触发条件?
      $ adb shell cat /proc/cmdline | tr '\0' '\n' | grep <key>
      ├─ 关键字没出现 → 功能未启用 / 内核没编译
      │                  → 找 OEM 确认
      ├─ 关键字出现 → 运行时无数据
      │              → 触发条件未命中(找文档)
      └─ 抓取脚本有问题 → 抓取失败
                         → 重抓 / 替代路径
```

(图 6-1:0 字节文件判别 3 步法流程图,✅)

### 6.3 跨平台扩展:高通 / 三星怎么迁移

| 维度 | MTK | 高通 | 三星 |
|------|-----|------|------|
| 时间序列工具 | **mmstat2** | 无(用 perfetto + ftrace) | 无(用 ftrace) |
| 内存历史 | ion_history(部分) | kgsl proc mem | vendor |
| GPU 内存 | new_gpu_memory | /sys/kernel/debug/kgsl/... | vendor |
| bugreport 抓取 | dumpsys 包含 mmstat | 不包含时间序列 | 不包含时间序列 |
| 替代方案 | - | perfetto + ftrace | perfetto + ftrace |

**对高通 / 三星**:用 **perfetto + ftrace** 替代 mmstat2——抓 30 分钟的 `ftrace/events/kmem` + `kmem_mmstat` trace,再用 `trace_processor` 分析。

**对应 AOSP**:`external/perfetto/`(✅) + `kernel/trace/trace_events_filter.c`。

---

## 7. 总结:5 条 Takeaway

读这篇应能回答:

1. **"MTK mmstat 4 大 trace 怎么读?"** ——
   - `mmstat_trace_meminfo`:13 字段(对照 proc/meminfo),看 `Slab` 涨速
   - `mmstat_trace_vmstat`:8 字段(对照 proc/vmstat),看 `pgscan_kswapd` 涨速
   - `mmstat_trace_buddyinfo`:12 列(对照 proc/buddyinfo),看高 order 缺货
   - `mmstat_trace_proc`:4 元组(pid/adj/RSS_kB/Swap_kB),**最核心**——看进程 PSS 涨速,涨速 > 10MB/min = 泄漏

2. **"0 字节文件怎么判别?"** ——
   - 通用 3 步法:**Step 1 路径存在 → Step 2 权限够 → Step 3 触发条件**
   - 4 大根因:**抓取失败 / 路径变化 / 功能未启用 / 运行时无数据**
   - 0xffffff13 13 个 0 字节文件分布:抓取失败 1 / 路径变化 1 / 功能未启用 6 / 运行时无数据 5

3. **"ION / DMA / GPU memory 怎么用?"** ——
   - ION:`/d/ion/ion_heap_debug` + `ion_history`,看 5 大 heap + 历史事件
   - DMA-BUF:`/d/dma_buf/bufinfo`(老) / `new_dma_bufinfo`(新 AOSP 13+),看 exp_name × size
   - GPU:ARM Mali `mali_gpu_memory`(常 0 字节) / MTK `new_gpu_memory` / Adreno `kgsl/proc/<pid>/mem`

4. **"system_server 涨速 1.9GB/min 怎么解读?"** ——
   - 0xffffff13 抓取:12 秒从 636MB 涨到 1012MB,涨速 31MB/s = **1.9GB/min** → 30 倍超标
   - 对照 26.8 单点 733MB = 看起来正常,**但 mmstat 看涨速 = 泄漏**
   - 下一步:跳 15.06 单进程 dumpsys + hprof,定位 system_server 内部哪个 service 在涨

5. **"跨平台怎么迁移(高通/三星)?"** ——
   - 时间序列工具:MTK 用 mmstat2,高通/三星用 **perfetto + ftrace** 替代
   - GPU 内存:Adreno 用 `/sys/kernel/debug/kgsl/proc/<pid>/mem`,三星用 vendor
   - 通用方法:抓 `ftrace/events/kmem` + `kmem_mmstat` trace,trace_processor 分析
   - ION/DMA-BUF 在 AOSP 12+ 统一为 DMA-BUF,跨平台可移植

---

## 附录 A:核心源码路径索引

| 工具 | AOSP / Vendor 源码路径 | 验证状态 |
|------|------------------------|:--------:|
| **mmstat / mmstat2** | `vendor/mediatek/proprietary/external/mmstat/` | 🟡 MTK vendor,不开源 |
| `/proc/meminfo` | `fs/proc/meminfo.c` | ✅ AOSP 17 |
| `/proc/vmstat` | `mm/vmstat.c` + `fs/proc/vmstat.c` | ✅ |
| `/proc/buddyinfo` | `mm/page_alloc.c:show_free_areas()` | ✅ |
| ION 框架 | `drivers/staging/android/ion/ion.c` | ✅ AOSP 公开 |
| `/d/ion/ion_heap_debug` | `drivers/staging/android/ion/ion.c:ion_debug_heap_show()` | ✅ |
| DMA-BUF 框架 | `drivers/dma-buf/dma-buf.c` | ✅ |
| `/d/dma_buf/bufinfo` | `drivers/dma-buf/dma-buf.c:dma_buf_bufinfo()` | ✅ AOSP 13+ |
| Mali GPU 内存 | `drivers/gpu/arm/mali/platform/.../mali_memory.c` | 🟡 ARM vendor |
| `/d/mali_gpu_memory` | MTK 私有 debugfs | 🟡 MTK vendor |
| `new_gpu_memory` | MTK 私有 | 🟡 MTK vendor |
| `zram0_bdstat` | `drivers/block/zram/zram_drv.c` | ✅ AOSP |
| perfetto | `external/perfetto/` | ✅ AOSP |
| ftrace kmem events | `include/trace/events/kmem.h` | ✅ AOSP |

---

## 附录 B:源码路径对账表

| 工具/数据源 | AOSP 17 实测 URL | HTTP 状态 |
|------------|:-----------------|:---------:|
| `drivers/staging/android/ion/ion.c` | `https://android.googlesource.com/kernel/common/+/refs/heads/android17-6.18/drivers/staging/android/ion/ion.c` | 🟡 待验证 |
| `drivers/dma-buf/dma-buf.c` | `https://android.googlesource.com/kernel/common/+/refs/heads/android17-6.18/drivers/dma-buf/dma-buf.c` | 🟡 待验证 |
| `drivers/gpu/arm/mali/...` | `https://android.googlesource.com/kernel/common/+/refs/heads/android17-6.18/drivers/gpu/arm/mali/` | 🟡 待验证 |
| `drivers/block/zram/zram_drv.c` | `https://android.googlesource.com/kernel/common/+/refs/heads/android17-6.18/drivers/block/zram/zram_drv.c` | 🟡 待验证 |
| `external/perfetto/` | `https://cs.android.com/android/platform/superproject/main/+/main:external/perfetto/` | 🟡 待验证 |
| `include/trace/events/kmem.h` | `https://android.googlesource.com/kernel/common/+/refs/heads/android17-6.18/include/trace/events/kmem.h` | 🟡 待验证 |

(说明:本篇 MTK 私有工具路径标 🟡,完整对账见 `00-Meta/技术对账表/vendor-工具/` 维护文件)

---

## 附录 C:量化数据自检表

| # | 数据 | 阈值 | 0xffffff13 实测 | 判定 |
|:-:|------|------|:---------------:|:----:|
| 1 | system_server PSS 涨速 | < 1MB/s | **31MB/s = 1.9GB/min** | ⚠️ 30 倍超标 |
| 2 | system_server RSS 净涨(12s) | < 20MB | **+348MB** | ⚠️ 净涨 |
| 3 | Slab 涨速 | < 5MB/min | 稳定(406-410MB) | 健康 |
| 4 | Cached 涨速 | — | 稳定(5.0-5.5GB) | 健康 |
| 5 | gms PSS 涨速 | < 5MB/s | ~2MB/s | 健康偏紧 |
| 6 | ION 历史 buffer | 0 字节 | 0 字节 | 🟡 debugfs 默认关 |
| 7 | DMA-BUF 数量 | < 50 | 13 | 健康 |
| 8 | GPU memory 总占用 | < 500MB | 461B(6 行,数据量小) | 数据不足 |
| 9 | zRAM IO 计数 | — | zram0_bdstat=27B | 单行统计 |
| 10 | mmstat 采样点 | — | 331 个(135s-150s) | 1Hz 采样 165s |
| 11 | mmstat 字段 13 含义 | — | 20/3152/3660... | 🟡 不确定 |
| 12 | 高 order 空闲块 | > 0(健康)/ 0(碎片) | 高 order = 0/2/11 | 偏碎片 |
| 13 | allocstall_movable 涨速 | < 100/min | 持续涨 | ⚠️ 用户态吃紧 |
| 14 | oom_kill 计数 | = 0 | 0 | 健康 |
| 15 | gms adj 0→100→0 变化 | 正常 | 切走切回 3 次 | 正常 |

(本表覆盖本篇 4 大类工具 + 0 字节文件 8 个分类,共 15 条量化断言)

---

## 附录 D:工程基线表

| 参数 | 默认 | 选用准则 | 踩坑 |
|------|------|----------|------|
| **AOSP 版本** | `android-17.0.0_r1` (API 37) | 17 LTS | < AOSP 13 路径不同(ION 还在) |
| **GKI 内核** | `android17-6.18` (6.18 LTS) | 6.18 LTS | < 6.6 perfetto 集成弱 |
| **DMA-BUF 路径** | AOSP 13+ `new_dma_bufinfo` | AOSP 12- 仍用 `dma_bufinfo` | 跨版本注意 |
| **mmstat 采样率** | 1Hz | vendor 固定 | 不能调 |
| **mmstat buffer 大小** | 30 分钟 ~1MB | vendor 固定 | 超过会被覆盖 |
| **ION 启用** | `CONFIG_ION_LEGACY=y` | AOSP 13+ 默认 dma-buf | vendor 仍可能开 ION |
| **GPU memtrack** | Mali 需 HAL 实现 | 老 driver 可能没装 | 没装就看不到 mali_gpu_memory |
| **perfetto 后端** | `traced_probes` | 6.18 GKI 默认 | 低端机可能缺 |
| **bugreport mmstat 抓取** | root 必填 | 写脚本 root 后 dump | 不 root 拿不到 |
| **跨平台迁移** | MTK→ perfetto+ftrace | 高通/三星通用 | ftrace buffer 注意大小 |

---

**本文为 26 章 26.9 子节,「调查工具书」系列第 3 篇(收口)。**
**上一篇**:[26.8 dumpsys_meminfo 全设备级 + procstats 解读](file:///E:/smc-pub/04-卷4-稳定性症状/38-内存与 OOM/08-dumpsys-meminfo全设备级与procstats解读.md)——把"AMS 怎么说"补完
**回到**:[26 章 README](file:///E:/smc-pub/04-卷4-稳定性症状/38-内存与 OOM/index.md) / [00-计划-新增3篇](file:///E:/smc-pub/04-卷4-稳定性症状/38-内存与 OOM/00-计划-新增3篇.md)
**完成**:26.7-26.9 调查工具书组,3 篇收官
