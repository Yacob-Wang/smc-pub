# 06-Foundation/Tools/Filesystem-Cheat-Sheet · 01 · /proc 关键文件字典

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 系统级诊断
>
> **强依赖**：[03-Forensics/Bugreport/02-目录结构全梳理](../../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/02-Bugreport-目录结构全梳理.md) · [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../05-卷5-调查方法论与工具链/31-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 /proc 关键文件 50+ 个逐一拆解——是什么、看什么、不看什么，oncall 现场 5 秒找"该 grep 哪个"
- **不是**：不复述 [03-Forensics/Bugreport/02 §6 proc/ 详解](../../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/02-Bugreport-目录结构全梳理.md)（本文是它的全量字典版）；不复述 [Bugreport/03 §4 proc 速查](../../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/03-Bugreport-关键文件速查.md)
- **承接自**：[Bugreport/02 §6 14 大 proc 速查表](../../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/02-Bugreport-目录结构全梳理.md) → 本文按 5 大类全量拆解
- **衔接去**：[02 /sys 关键节点](02-sys关键节点字典.md) / [Bugreport/04 实战 5 案例](../../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/04-Bugreport-实战5类典型案例.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 5 大类：内存 / CPU / 网络 / 进程 / 系统 | /proc 按功能分 |
| 2 | 每个文件给"用途 / 看什么 / 不看什么" + 1 个 grep | oncall 5 秒 |
| 3 | 第 7 章 oncall 5 分钟定位 + 关键阈值表 | 现场 5 分钟决策 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**/proc 字典 = oncall 系统级诊断的"基础设施"——50+ 文件按内存 / CPU / 网络 / 进程 / 系统 5 类分，看哪个文件、grep 什么字段，5 秒决策。**

AOSP 17 上 /proc 包含 200+ 文件，**但 90% 取证只看 30 个**。本文给这 30 个的"用途 / 看 / 不看 / 1 个 grep"对照表。

---

## 1. /proc 5 大分类

```
/proc 目录
├── 数字子目录（进程信息）      ← /proc/<pid>/...
│   ├── 1/         ← init 进程
│   ├── 2/         ← kthreadd
│   ├── self/      ← 当前 shell
│   └── ...
├── 内存类                       ← 第 2 章
│   ├── meminfo
│   ├── vmstat
│   ├── zoneinfo
│   ├── buddyinfo
│   ├── slabinfo
│   ├── pagetypeinfo
│   ├── vmallocinfo
│   └── pressure/memory
├── CPU / 调度类                  ← 第 3 章
│   ├── loadavg
│   ├── stat
│   ├── schedstat
│   ├── cpuinfo
│   └── pressure/cpu
├── 网络类                       ← 第 4 章
│   ├── net/dev
│   ├── net/tcp
│   ├── net/udp
│   ├── net/sockstat
│   └── net/route
├── 进程 / 线程类                 ← 第 5 章
│   ├── <pid>/
│   │   ├── status
│   │   ├── stat
│   │   ├── statm
│   │   ├── maps
│   │   ├── smaps
│   │   ├── smaps_rollup
│   │   ├── cmdline
│   │   ├── environ
│   │   ├── fd/
│   │   ├── fdinfo/
│   │   ├── task/<tid>/
│   │   └── ...
│   └── ...
└── 系统类                       ← 第 6 章
    ├── version
    ├── cmdline
    ├── mounts
    ├── uptime
    ├── loadavg
    ├── sys/
    │   ├── kernel/
    │   │   ├── tainted
    │   │   ├── random/
    │   │   └── ...
    │   ├── fs/
    │   ├── net/
    │   ├── vm/
    │   └── ...
    └── ...
```

---

## 2. 内存类（8 个核心文件）

### 2.1 /proc/meminfo（⭐ OOM 必看）

**用途**：系统内存总览

**看什么**：

```
MemTotal:        3909976 kB      # 总物理内存
MemFree:          234560 kB      # 完全未用
MemAvailable:    1234567 kB      # 关键：可用（含可回收）
Buffers:          123456 kB      # page cache 中 buffers
Cached:           567890 kB      # page cache 中 cached
Active(anon):     890123 kB      # 活跃匿名页（app heap）
Inactive(anon):   234567 kB      # 不活跃匿名页
Active(file):     344444 kB      # 活跃文件页
Inactive(file):   333323 kB      # 不活跃文件页
Anonymous:       1123456 kB      # 匿名页（不能换出到磁盘的）
Mapped:           345678 kB      # mmap 映射
Slab:             345678 kB      # 内核 slab
SReclaimable:     234567 kB      # 可回收 slab
SUnreclaim:       111111 kB      # 不可回收 slab ⚠️
KernelStack:       12345 kB
PageTables:        45678 kB
NFS_Unstable:          0 kB
Bounce:                0 kB
WritebackTmp:          0 kB
CommitLimit:     4567890 kB      # 当前可分配上限
Committed_AS:    7890123 kB      # 已 commit 内存 ⚠️
VmallocTotal:   263061440 kB
VmallocUsed:       12345 kB
Percpu:             1234 kB
HardwareCorrupted:     0 kB
AnonHugePages:    234567 kB
ShmemHugePages:        0 kB
ShmemPmdMapped:        0 kB
CmaTotal:         123456 kB      # CMA 总数
CmaFree:          100000 kB      # CMA 空闲
HugePages_Total:       0
HugePages_Free:        0
HugePages_Rsvd:        0
HugePages_Surp:        0
Hugepagesize:       2048 kB
DirectMap4k:      234567 kB
DirectMap2M:     3456789 kB
DirectMap1G:           0 kB
```

**关键 grep**：

```bash
$ adb shell cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|CommitLimit|Committed_AS|CmaTotal|CmaFree|SUnreclaim"
```

**4 个告警阈值**：

| 字段 | 阈值 | 含义 |
|:-----|:-----|:-----|
| `MemAvailable` | < 200MB | OOM 风险 |
| `Committed_AS` | > `CommitLimit` | OOM 风险（commit 超分配）|
| `CmaFree` | < `CmaTotal * 0.1` | CMA 紧张（影响 audio / camera）|
| `SUnreclaim` | > 100MB | 内核 slab 泄漏 |

### 2.2 /proc/vmstat（VM 行为统计）

**用途**：虚拟内存事件计数

**看什么**：

```bash
$ adb shell cat /proc/vmstat | head -30
nr_free_pages 58640
nr_alloc_batch 1024
nr_inactive_anon 234567
nr_active_anon 1234567
nr_inactive_file 333323
nr_active_file 344444
nr_unevictable 12345
nr_mlock 0
nr_anon_pages 1234567
nr_mapped 345678
nr_file_pages 567890
nr_dirty 123
nr_writeback 0
nr_slab_reclaimable 234567
nr_slab_unreclaimable 111111
nr_page_table_pages 45678
nr_kernel_stack 12345
...
pgpgin 1234567
pgpgout 2345678
pswpin 0
pswpout 0
pgalloc_dma 12345
pgalloc_normal 1234567
pgalloc_movable 234567
pgfree 2345678
pgactivate 12345
pgdeactivate 23456
pgfault 12345678
pgmajfault 1234
pgrefill_dma 0
...
```

**关键 grep**：

```bash
# 1. page fault 统计（看是否有大量 major fault）
$ adb shell cat /proc/vmstat | grep -E "pgfault|pgmajfault"

# 2. 写回 dirty 页
$ adb shell cat /proc/vmstat | grep "pgpgout\|nr_writeback"

# 3. 内存压力
$ adb shell cat /proc/vmstat | grep "allocstall\|pgrefill"
```

**3 个告警阈值**：

| 字段 | 阈值 | 含义 |
|:-----|:-----|:-----|
| `pgmajfault` | > 1000/s | 大量 major fault（swap / 文件）|
| `allocstall` | > 100 | 频繁内存不足 |
| `nr_writeback` | > 1000 | IO 写回慢 |

### 2.3 /proc/zoneinfo

**用途**：内存 zone 详细（kernel 调试）

**看什么**：

```bash
# 找特定 zone
$ adb shell cat /proc/zoneinfo | grep -A 5 "Zone  |DMA"
# 找 lowmem / 高水位
$ adb shell cat /proc/zoneinfo | grep -E "min|low|high"
```

**适用场景**：kernel 内存压力分析（普通 app 看不到）

### 2.4 /proc/buddyinfo

**用途**：buddy allocator（内存碎片）

**看什么**：

```bash
$ adb shell cat /proc/buddyinfo
Node 0, zone   Normal  1023  512  256  128  64  32  16   8   4   2   1
Node 0, zone  HighMem  4095 2048 1024  512 256 128 64  32  16   8   4
Node 0, zone   Movable  100  200  100   50  25  12   6   3   1   0   0
```

**关键**：每列代表"2^n 个 page 的 free 块"数量
- 第 1 列（1023）= 1 page 的 free 块（碎片）
- 最后 1 列（1）= 1024 page 的大块（连续内存）

**告警**：第 1 列 0 → 严重碎片

### 2.5 /proc/slabinfo（⭐ 内核 slab 泄漏）

**用途**：内核 slab 缓存统计

**看什么**：

```bash
$ adb shell cat /proc/slabinfo | head
# name            <active_objs> <num_objs> <objsize> <objperslab> <pagesperslab> ...

dentry           123456  130000    192   21    1 :  100000  5000 :  0
inode            234567  240000    640   25    4 :  100000  4000 :  0
vm_area_struct   100000  100000    200   20    1 :   50000  5000 :  0
...
```

**关键 grep**：

```bash
# 1. 找泄漏 slab
$ adb shell cat /proc/slabinfo | sort -k2 -n -r | head -10

# 2. 找特定 slab
$ adb shell cat /proc/slabinfo | grep "dentry\|inode"

# 3. 找异常 slab
$ adb shell cat /proc/slabinfo | awk '$3 > 100000 {print}'  # > 100MB slab
```

**4 个告警 slab**：

| slab | 含义 | 阈值 |
|:-----|:-----|:-----|
| `dentry` | 目录项缓存 | > 200MB 可能泄漏 |
| `inode` | inode 缓存 | > 300MB 可能泄漏 |
| `vm_area_struct` | VMA 结构 | > 50MB 可能泄漏 |
| `skbuff_head_cache` | socket buffer | > 50MB 可能泄漏 |

### 2.6 /proc/pagetypeinfo

**用途**：按 page type 统计（kernel 调试）

**适用场景**：内存碎片深度分析

### 2.7 /proc/vmallocinfo

**用途**：vmalloc 分配记录

**看什么**：

```bash
$ adb shell cat /proc/vmallocinfo | head
# 0xffff... start+...
# 每个 vmalloc 分配的调用栈
```

**告警**：总 size > 500MB → vmalloc 区域紧张

### 2.8 /proc/pressure/memory（⭐ OOM 早期信号）

**用途**：内存 PSI 压力

**看什么**：

```
some avg10=0.00 avg60=0.00 avg300=0.00 total=0
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
```

**关键 grep**：

```bash
# 1. 看 memory 压力
$ adb shell cat /proc/pressure/memory

# 2. 监控 full avg10（> 0 = 有任务饿死）
$ adb shell cat /proc/pressure/memory | head -1
```

**3 个告警阈值**：

| 字段 | 阈值 | 含义 |
|:-----|:-----|:-----|
| `some avg10` | > 5% | 内存压力中 |
| `some avg10` | > 20% | 内存压力高 |
| `full avg10` | > 0% | 有任务完全饿死（OOM 风险）|

---

## 3. CPU / 调度类（5 个核心文件）

### 3.1 /proc/loadavg

**用途**：系统负载

**看什么**：

```
3.50 4.20 5.10 1/1234 5678
│    │    │    │  │   └── 最近创建的 PID
│    │    │    └── 正在运行进程 / 总进程
│    │    └─────── 15 分钟平均
│    └──────────── 5 分钟平均
└───────────────── 1 分钟平均
```

**告警**：
- 1 分钟 load > 4 * CPU 核数 → CPU 饱和
- 3 个数 1>5>15 → load 在涨（恶化）
- 3 个数 1<5<15 → load 在降（恢复）

### 3.2 /proc/stat

**用途**：CPU 总体统计

**看什么**：

```bash
# 1. CPU 总体
$ adb shell head -10 /proc/stat
cpu  123456 1234 56789 9876543 1234 0 0 0 0 0
    │      │    │     │       │    │ │ │ │ │ │
    │      │    │     │       │    │ │ │ │ │ └ steal
    │      │    │     │       │    │ │ │ │ └── guest_nice
    │      │    │     │       │    │ │ │ └──── guest
    │      │    │     │       │    │ │ └────── nice
    │      │    │     │       │    │ └──────── irq
    │      │    │     │       │    └────────── softirq
    │      │    │     │       └─────────────── iowait ⚠️
    │      │    │     └───────────────────── idle
    │      │    └──────────────────────────── system
    │      └───────────────────────────────── user
    └───────────────────────────────────────── total

# 2. 单个 CPU
$ adb shell cat /proc/stat | grep "^cpu[0-9]"
cpu0  ...
cpu1  ...
cpu2  ...
cpu3  ...

# 3. 进程统计
$ adb shell cat /proc/stat | grep "processes\|procs_running\|procs_blocked"
processes 12345
procs_running 5
procs_blocked 2
```

**告警**：
- `iowait` > 30% → IO 卡
- `procs_blocked` > 5 → 进程在等锁

### 3.3 /proc/schedstat

**用途**：scheduler 详细统计

**看什么**：

```bash
$ adb shell cat /proc/schedstat | head
# 格式：version  timestamp
# 然后每个 CPU 一行
cpu0 0 0 0 0 0 0 ...
   │ │ │ │ │ │ │
   │ │ │ │ │ │ └ yld_count
   │ │ │ │ │ └── schedule_failed
   │ │ │ │ └──── rq_run_time
   │ │ │ └────── rq_cpu_time
   │ │ └──────── rq_max_run_time
   │ └────────── wait_time
   └──────────── timeslices
```

**适用场景**：调度延迟调试

### 3.4 /proc/cpuinfo

**用途**：CPU 信息

**看什么**：

```bash
$ adb shell cat /proc/cpuinfo
# 列出所有 CPU 核
# model name / cpu MHz / cache size
```

**告警**：不同 CPU 的 `cpu MHz` 差异 > 30% → 调度不平衡

### 3.5 /proc/pressure/cpu

**用途**：CPU PSI 压力

**看什么**：

```
some avg10=12.50 avg60=8.30 avg300=5.10 total=...
full avg10=2.10 avg60=1.20 avg300=0.50 total=...
```

**告警**：
- `some avg10` > 20% → CPU 压力高
- `full avg10` > 0% → 有任务完全饿死

---

## 4. 网络类（5 个核心文件）

### 4.1 /proc/net/dev

**用途**：网络设备统计

**看什么**：

```bash
$ adb shell cat /proc/net/dev
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1234567   12345    0    0    0     0          0         0  1234567   12345    0    0    0     0       0          0
  eth0: 1234567  123456    0    0    0     0          0         0  2345678  123456    0    0    0     0       0          0
wlan0: 1234567  234567    0    0    0     0          0         0  2345678  234567    0    0    0     0       0          0
```

**关键 grep**：

```bash
# 1. 看总流量
$ adb shell cat /proc/net/dev | grep -v "Inter\| face\| lo:"

# 2. 看 errors / drops
$ adb shell cat /proc/net/dev | grep -E "errs|drop"
```

### 4.2 /proc/net/tcp

**用途**：TCP 连接

**看什么**：

```bash
$ adb shell cat /proc/net/tcp
# sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
# 0: 0100007F:0277 0100007F:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 ...

# local_address: 0100007F = 127.0.0.1
# 端口: 0277 (hex) = 631 (dec)
# state: 0A = LISTEN
```

**关键 grep**：

```bash
# 1. 看 ESTABLISHED 连接
$ adb shell cat /proc/net/tcp | awk '$4 == "01" {print}'

# 2. 看 LISTEN socket
$ adb shell cat /proc/net/tcp | awk '$4 == "0A" {print}'

# 3. 看某 IP 的连接
$ adb shell cat /proc/net/tcp | grep "1234567F"
```

### 4.3 /proc/net/udp

**用途**：UDP socket

### 4.4 /proc/net/sockstat

**用途**：socket 总览

**看什么**：

```
sockets: used 1234
TCP: inuse 234 orphan 0 tw 12 alloc 345 mem 567
UDP: inuse 56 mem 123
UDPLITE: inuse 0
RAW: inuse 0
FRAG: inuse 0 memory 0
```

**告警**：
- `TCP:tw > 10000` → TIME_WAIT 积压
- `TCP:orphan > 100` → 孤立 socket 泄漏

### 4.5 /proc/net/route

**用途**：路由表

**看什么**：

```bash
$ adb shell cat /proc/net/route
# 路由表
# Iface Destination Gateway Flags RefCnt Use Metric
```

**适用场景**：网络不通排查

---

## 5. 进程 / 线程类（/proc/<pid>/）

### 5.1 /proc/<pid>/status

**用途**：进程状态（最常用）

**看什么**：

```bash
$ adb shell cat /proc/<pid>/status
Name:   com.example.app
Umask:  0077
State:  S (sleeping)
Tgid:   12345
Ngid:   0
Pid:    12345
PPid:   1
TracerPid:      0
Uid:    10001   10001   10001   10001
Gid:    10001   10001   10001   10001
FDSize: 128
Threads:        123
SigQ:   0/15338
SigPnd: 0000000000000000
ShdPnd: 0000000000000000
SigBlk: 0000000000000000
SigIgn: 0000000000000000
SigCgt: 0000000000000000
CapInh: 0000000000000000
CapPrm: 00000000a82425fb
CapEff: 0000000000000000
CapBnd: 00000000a82425fb
CapAmb: 0000000000000000
Seccomp:        2
Seccomp_filters: 1
Speculation_Store_Bypass:       vulnerable
Cpus_allowed:   ff
Cpus_allowed_list:      0-7
Mems_allowed:   1
Mems_allowed_list:      0
voluntary_ctxt_switches:        1234
nonvoluntary_ctxt_switches:     5

# 关键字段
VmPeak:    1234567 kB      # 峰值虚拟内存
VmSize:    1234567 kB      # 当前虚拟内存
VmLck:           0 kB      # 锁住
VmPin:           0 kB      # pin
VmHWM:      234567 kB      # 峰值物理内存（PSS HWM）
VmRSS:      123456 kB      # 当前物理内存（RSS）
VmData:     567890 kB      # data 段
VmStk:        1234 kB      # stack
VmExe:        1234 kB      # executable
VmLib:        1234 kB      # shared lib
VmPTE:        1234 kB      # page table entries
VmSwap:           0 kB      # swap
Threads:        123
SigQ:   0/15338
...
```

**关键 grep**：

```bash
# 1. 找 RSS 最大的进程
$ adb shell "for p in /proc/[0-9]*; do echo -n \"\$(basename \$p) \"; cat \$p/status 2>/dev/null | grep VmRSS; done" | sort -k2 -n -r | head

# 2. 看线程数
$ adb shell cat /proc/<pid>/status | grep "Threads"

# 3. 看 seccomp / cap
$ adb shell cat /proc/<pid>/status | grep -E "Seccomp|Cap"
```

### 5.2 /proc/<pid>/stat

**用途**：进程详细状态

**看什么**：

```bash
$ adb shell cat /proc/<pid>/stat
12345 (com.example.app) S 1 12345 12345 0 -1 ...
```

**字段含义**（42 个）：

- 1: pid
- 2: comm（进程名）
- 3: state
- 4: ppid
- 5-8: pgrp / session
- 14-15: utime / stime（用户态 / 内核态 CPU 时间）
- 22: starttime
- 39: cpu
- 44: rss

### 5.3 /proc/<pid>/maps

**用途**：进程虚拟内存映射

**看什么**：

```bash
$ adb shell cat /proc/<pid>/maps
address           perms offset  dev   inode      pathname
00400000-00401000 r-xp 00000000 08:01 12345     /system/bin/app_process
01000000-01001000 rw-p 00000000 00:00 0
01234000-03234000 rw-p 00000000 00:00 0          [heap]
7000000-8000000 ---p 00000000 00:00 0          [stack]
7f000000-7f100000 r-xp 00000000 08:01 23456     /system/lib64/libfoo.so
...
```

**关键 grep**：

```bash
# 1. 找特定 .so
$ adb shell cat /proc/<pid>/maps | grep "libfoo.so"

# 2. 找 native heap
$ adb shell cat /proc/<pid>/maps | grep "heap"

# 3. 找 stack
$ adb shell cat /proc/<pid>/maps | grep "stack"
```

### 5.4 /proc/<pid>/smaps_rollup

**用途**：进程内存汇总（⭐ OOM 必看）

**看什么**：

```bash
$ adb shell cat /proc/<pid>/smaps_rollup
00400000-ffffffffff ---
Rss:             234567 kB
Pss:             123456 kB
Shared_Clean:     12345 kB
Shared_Dirty:     12345 kB
Private_Clean:    12345 kB
Private_Dirty:   100000 kB
Referenced:      234567 kB
Anonymous:       100000 kB
LazyFree:             0 kB
AnonHugePages:    12345 kB
ShmemPmdMapped:        0 kB
FilePmdMapped:         0 kB
SwapPss:              0 kB
Locked:               0 kB
```

**告警**：
- Pss > 1GB → 进程内存大
- Private_Dirty > 500MB → 私有脏页多（潜在泄漏）

### 5.5 /proc/<pid>/cmdline

**用途**：进程命令行

```bash
$ adb shell cat /proc/<pid>/cmdline
# 真实命令行（null 结尾）
$ adb shell "cat /proc/<pid>/cmdline | tr '\0' ' '"
```

### 5.6 /proc/<pid>/fd/ + fdinfo/

**用途**：进程打开的文件描述符

```bash
# 1. 列出所有 fd
$ adb shell ls -l /proc/<pid>/fd/

# 2. 看特定 fd
$ adb shell cat /proc/<pid>/fdinfo/<fd>

# 3. 找泄漏 fd
$ adb shell ls /proc/<pid>/fd/ | wc -l
# > 1000 → 可能泄漏
```

### 5.7 /proc/<pid>/task/<tid>/

**用途**：进程内所有线程

```bash
# 1. 列所有 thread
$ adb shell ls /proc/<pid>/task/

# 2. 看特定 thread
$ adb shell cat /proc/<pid>/task/<tid>/status
```

### 5.8 /proc/<pid>/oom_score + oom_score_adj

**用途**：OOM 优先级

```bash
$ adb shell cat /proc/<pid>/oom_score
# 数值越大，越容易被 OOM 杀

$ adb shell cat /proc/<pid>/oom_score_adj
# [-1000, 1000]
# -1000 = 永不杀
# 0 = 默认
# 1000 = 最先杀
```

---

## 6. 系统类（6 个核心文件）

### 6.1 /proc/version

**用途**：kernel 版本

```bash
$ adb shell cat /proc/version
Linux version 6.18.0-android17-... (build@xxx)
```

### 6.2 /proc/cmdline（⭐ 启动诊断必看）

**用途**：kernel 启动参数

```bash
$ adb shell cat /proc/cmdline
androidboot.boot_devices=soc androidboot.selinux=enforcing ...
```

**关键参数**：

| 参数 | 取值 | 含义 |
|:-----|:-----|:-----|
| `androidboot.selinux` | enforcing / permissive / disabled | SELinux 模式 |
| `androidboot.boot_devices` | soc | 启动设备 |
| `androidboot.serialno` | xxx | 设备 SN |
| `androidboot.hardware` | xxx | 平台 |
| `androidboot.hardware.platform` | xxx | SoC 平台 |
| `androidboot.verifiedbootstate` | green/yellow/orange/red | AVB 状态 |
| `androidboot.dm_verity` | enabled/disabled | dm-verity 状态 |

### 6.3 /proc/mounts

**用途**：当前挂载点

```bash
$ adb shell cat /proc/mounts
/dev/block/sda1 / ext4 rw,seclabel,relatime 0 0
tmpfs /dev tmpfs rw,seclabel,nosuid,size=...,mode=755 0 0
...
```

**关键 grep**：

```bash
# 1. 找异常挂载
$ adb shell cat /proc/mounts | grep -v -E "ext4|tmpfs|proc|sysfs|devpts|cgroup|selinuxfs"

# 2. 找 ro / rw
$ adb shell cat /proc/mounts | grep -E "ro,|rw,"

# 3. 找容量
$ adb shell cat /proc/mounts | grep "size="
```

### 6.4 /proc/uptime

**用途**：系统运行时间

```bash
$ adb shell cat /proc/uptime
12345.67 6789.12
│         └── 空闲时间
└──────────── 运行时间（秒）
```

### 6.5 /proc/sys/kernel/tainted

**用途**：kernel 警告位

```bash
$ adb shell cat /proc/sys/kernel/tainted
# 0 = 干净
# 非 0 = 有警告（KE 现场）
```

**位含义**：
- bit 0: 加载专有 module
- bit 1: 加载未签名 module
- bit 2: 硬件 fault
- bit 4: Oops
- bit 5: panic
- bit 7: relabel warning
- bit 8: ACPI 错误
- bit 9: 内存错误
- bit 10: 警告

**告警**：任何一位 = 1 → kernel 有问题

### 6.6 /proc/sys/vm/

**用途**：VM 调优参数

**关键文件**：

```bash
# 1. dirty page 阈值
$ adb shell cat /proc/sys/vm/dirty_ratio
# 20

# 2. dirty page 写回时机
$ adb shell cat /proc/sys/vm/dirty_expire_centisecs
# 3000（30 秒）

# 3. swappiness
$ adb shell cat /proc/sys/vm/swappiness
# 0（Android 默认不 swap）
```

---

## 7. oncall 5 分钟定位速查

### 7.1 OOM 现场 5 个必看文件

```bash
# 1. /proc/meminfo 总览
$ adb shell cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|Commit"

# 2. /proc/pressure/memory PSI
$ adb shell cat /proc/pressure/memory

# 3. /proc/<pid>/smaps_rollup 单进程
$ adb shell cat /proc/<pid>/smaps_rollup

# 4. /proc/<pid>/oom_score_adj 优先级
$ adb shell cat /proc/<pid>/oom_score_adj

# 5. /proc/slabinfo 内核 slab
$ adb shell cat /proc/slabinfo | sort -k2 -n -r | head
```

### 7.2 ANR 现场 5 个必看文件

```bash
# 1. /proc/<pid>/status 进程状态
$ adb shell cat /proc/<pid>/status | head -10

# 2. /proc/<pid>/task/<tid>/status 所有线程
$ adb shell "for t in /proc/<pid>/task/*/; do cat \${t}status | head -3; done"

# 3. /proc/<pid>/wchan 内核等待通道
$ adb shell cat /proc/<pid>/wchan
# 输出 kernel 函数名（do_wait / futex_wait 等）

# 4. /proc/loadavg 系统负载
$ adb shell cat /proc/loadavg

# 5. /proc/<pid>/stack 内核栈
$ adb shell cat /proc/<pid>/stack
# root 权限才能看
```

### 7.3 NE 现场 5 个必看文件

```bash
# 1. /proc/<pid>/maps 内存映射
$ adb shell cat /proc/<pid>/maps | grep "libfoo\|heap\|stack"

# 2. /proc/<pid>/smaps 详细
$ adb shell cat /proc/<pid>/smaps | grep -E "Rss|Shared_Dirty"

# 3. /proc/<pid>/limits 系统限制
$ adb shell cat /proc/<pid>/limits

# 4. /proc/<pid>/oom_score OOM 优先级
$ adb shell cat /proc/<pid>/oom_score

# 5. /proc/<pid>/io IO 统计
$ adb shell cat /proc/<pid>/io
```

### 7.4 KE 现场 5 个必看文件

```bash
# 1. /proc/sys/kernel/tainted 警告位
$ adb shell cat /proc/sys/kernel/tainted

# 2. /proc/version kernel 版本
$ adb shell cat /proc/version

# 3. /proc/cmdline 启动参数
$ adb shell cat /proc/cmdline | tr '\0' '\n'

# 4. /proc/modules 加载的 module
$ adb shell cat /proc/modules

# 5. /proc/kallsyms 符号表
$ adb shell cat /proc/kallsyms | grep "func_name"
```

### 7.5 性能问题 5 个必看文件

```bash
# 1. /proc/loadavg
$ adb shell cat /proc/loadavg

# 2. /proc/stat CPU 总体
$ adb shell cat /proc/stat | head -1

# 3. /proc/<pid>/stat 单进程 CPU
$ adb shell cat /proc/<pid>/stat

# 4. /proc/pressure/cpu
$ adb shell cat /proc/pressure/cpu

# 5. /proc/<pid>/io 单进程 IO
$ adb shell cat /proc/<pid>/io
```

---

## 8. 关键阈值速查表

| 指标 | 阈值 | 含义 | 文件 |
|:-----|:-----|:-----|:-----|
| MemAvailable | < 200MB | OOM 风险 | /proc/meminfo |
| Committed_AS / CommitLimit | > 1 | OOM 风险 | /proc/meminfo |
| pressure/memory some avg10 | > 20% | 内存压力高 | /proc/pressure/memory |
| pressure/memory full avg10 | > 0% | 任务饿死 | /proc/pressure/memory |
| loadavg 1min | > 4*CPU 核数 | CPU 饱和 | /proc/loadavg |
| pressure/cpu some avg10 | > 20% | CPU 压力高 | /proc/pressure/cpu |
| procs_blocked | > 5 | 锁等待 | /proc/stat |
| iowait | > 30% | IO 卡 | /proc/stat |
| pgmajfault/s | > 1000 | 大量 major fault | /proc/vmstat |
| allocstall | > 100 | 内存不足 | /proc/vmstat |
| dentry slab | > 200MB | 目录缓存大 | /proc/slabinfo |
| inode slab | > 300MB | inode 缓存大 | /proc/slabinfo |
| TCP:tw | > 10000 | TIME_WAIT 积压 | /proc/net/sockstat |
| Tainted | > 0 | kernel 警告 | /proc/sys/kernel/tainted |
| CmaFree | < 10% CmaTotal | CMA 紧张 | /proc/meminfo |
| SUnreclaim | > 100MB | slab 泄漏 | /proc/meminfo |

---

## 9. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [03-Forensics/Bugreport/02-目录结构全梳理 §6](../../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/02-Bugreport-目录结构全梳理.md) | bugreport 中 proc/ 文件 |
| [03-Forensics/Bugreport/03 §4 proc 速查](../../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/03-Bugreport-关键文件速查.md) | 15 大 proc 速查 |
| [02 /sys 关键节点](02-sys关键节点字典.md) | 下篇 |
| [03-Forensics/Bugreport/04 实战 5 案例](../../../../../05-卷5-调查方法论与工具链/33-Dumpsys · Bugreport · DropBox/04-Bugreport-实战5类典型案例.md) | OOM 案例用 |
| [01-Mechanism/Kernel/Memory_Management/](../../../../01-Mechanism/Kernel/Memory_Management/) | 内存机制 |
| [01-Mechanism/Kernel/cgroup/](../../../../01-Mechanism/Kernel/cgroup/) | cgroup 接口 |

---

## 10. 下一篇预告 + 自检

### 10.1 下一篇

[02 /sys 关键节点字典](02-sys关键节点字典.md) 讲清：
- /sys 30+ 关键节点（按 5 大类：硬件 / 设备 / 内核 / 调度 / 文件系统）
- 跟 /proc 的差异（/sys 给用户空间，/proc 主要给内核）
- 性能 / 调优类节点的写操作
- oncall 现场 5 秒定位

### 10.2 看完本文的自检

- [ ] 能从 1 个事故秒级定位该看哪个 /proc 文件
- [ ] 知道 §7 5 类事故的 5 个必看文件
- [ ] 知道 §8 16 个关键阈值
- [ ] 能用 §2.1 4 个 meminfo 告警字段
- [ ] 知道 /proc/<pid>/status 关键字段含义
- [ ] 能区分 /proc/meminfo vs /proc/vmstat vs /proc/slabinfo

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
