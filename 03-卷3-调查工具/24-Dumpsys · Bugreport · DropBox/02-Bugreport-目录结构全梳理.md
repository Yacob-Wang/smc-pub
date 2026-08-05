# 03-Forensics/Bugreport · 02 · Bugreport 目录结构全梳理

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 现场取证人员
>
> **强依赖**：[01 Bugreport 总览](01-Bugreport-总览与生成解析.md) · [04-Tool/Dumpsys/](../../../04-Tool/Dumpsys/)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 bugreport.zip 里 50+ 关键文件**逐一拆解**——每个文件"是什么 / 看什么 / 不看什么"，8 类事故"看哪个文件"
- **不是**：不复述 [01 §2 顶层结构](01-Bugreport-总览与生成解析.md)；不复述 [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../../03-卷3-调查工具/24-Dumpsys · Bugreport · DropBox/12-dumpsys实战SOP.md)
- **承接自**：[01 §1.4 5 类现场的工具选择](01-Bugreport-总览与生成解析.md) → 本文展开"具体看哪个文件"
- **衔接去**：[03 关键文件速查](03-Bugreport-关键文件速查.md) / [04 实战 5 类典型案例](04-Bugreport-实战5类典型案例.md) / [05 bugreport vs perfetto trace](05-Bugreport-vs-perfetto-trace.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 2-7 章按子目录分（FS / dumpsys / logcat / traces / proc / kernel）| 与 bugreport 实际结构对齐 |
| 2 | 第 8 章 8 类事故对应表 | oncall 现场 5 秒定位 |
| 3 | 每个文件给"看 / 不看"二分法 | 减少无意义阅读 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**bugreport.zip 50+ 关键文件逐一拆解——oncall 5 秒定位"看哪个文件 / 不看哪个文件"。**

AOSP 17 上 bugreport 通常 100-300MB，**90% 的取证时间花在"打开不相关的文件"**——本文给 50+ 文件的"用途 + 看什么 + 不看什么"对照表。

---

## 1. 完整文件树（AOSP 17）

```
bugreport.zip
├── version.txt                         # dumpstate 版本
├── main_entry.txt                      # 入口 dumpstate 文本
├── build.prop                          # 设备 build 信息
├── FS/                                 # 文件系统 dump
│   ├── data/
│   │   ├── anr/
│   │   │   └── traces.txt              # ⭐ ANR 现场栈
│   │   ├── tombstones/
│   │   │   ├── tombstone_00            # ⭐ NE 现场（tombstone_00-09）
│   │   │   └── ...
│   │   ├── system/
│   │   │   ├── dropbox/                # ⭐ dropbox crash 历史
│   │   │   │   ├── system_app_crash@xxx.txt
│   │   │   │   └── ...
│   │   │   └── users/                  # 用户数据
│   │   └── vendor/
│   │       └── ramoops/                # ⭐ kernel panic 持久化
│   │           ├── pmsg-ramoops-0
│   │           └── ...
│   ├── system/
│   │   ├── build.prop
│   │   ├── etc/
│   │   │   ├── selinux/                # SELinux 策略
│   │   │   │   ├── plat_sepolicy
│   │   │   │   └── precompiled_sepolicy
│   │   │   └── ...
│   │   └── frameworks/                 # framework jar
│   └── vendor/
│       ├── build.prop
│       └── ...
├── dumpsys/                            # ⭐ dumpsys 所有 service
│   ├── dumpsys_*.txt                   # 每个 service 1 个文件
│   └── ...
├── logcat/                             # ⭐ logcat 5 大 buffer
│   ├── logcat_main.txt                 # 主 logcat
│   ├── logcat_system.txt
│   ├── logcat_events.txt
│   ├── logcat_crash.txt
│   └── logcat_kernel.txt
├── traces/                             # ⭐ systrace / perfetto
│   ├── systrace.html
│   ├── systrace_0.html
│   ├── perfetto-trace.pb
│   └── ...
├── pkg/                                # 包管理
│   ├── packages.xml
│   └── ...
├── proc/                               # /proc 文件 dump
│   ├── meminfo                         # ⭐ 内存概览
│   ├── vmstat
│   ├── cmdline
│   ├── version
│   ├── mounts
│   ├── pressure/
│   │   ├── cpu
│   │   ├── memory
│   │   └── io
│   ├── interrupts
│   ├── schedstat
│   ├── zoneinfo
│   └── ...
├── kernel/                             # kernel info
│   ├── dmesg.txt                       # ⭐ kernel log
│   ├── last_kmsg.txt                   # 上次 boot kernel log
│   ├── kallsyms                        # kernel symbol table
│   ├── modules                         # 加载的 kernel module
│   └── ...
└── system/                             # 设备信息
    ├── package_info.txt
    └── ...
```

**总文件数**：300+
**总大小**：100-300MB
**关键文件（标 ⭐）**：~20 个（占 80% 取证时间）

---

## 2. FS/ 详解

### 2.1 FS/data/ 核心子目录

| 路径 | 用途 | 何时看 |
|:-----|:-----|:------|
| `FS/data/anr/traces.txt` | ANR 现场栈 | **ANR 现场必看** |
| `FS/data/anr/traces_<system_server>.txt` | system_server ANR | system_server 卡死 |
| `FS/data/tombstones/tombstone_*` | NE 现场 | **NE 现场必看** |
| `FS/data/system/dropbox/` | dropbox 历史 crash | 看历史 NE/ANR |
| `FS/data/vendor/ramoops/` | kernel panic 持久化 | **KE 现场必看** |
| `FS/data/system/users/` | 用户配置 | 多用户问题 |

### 2.2 traces.txt 重点看什么

```
# 看 main thread 状态
"main" prio=5 tid=7 Blocked
  | group="main" sCount=1 ...
  at java.lang.Object.wait(Native method)
  at com.example.app.FooClass.barMethod(FooClass.java:42)
  ...

# 看 blocked on 哪个锁
  - waiting on <0x12345> (a java.lang.Object)
  - held by thread tid=12 ("Worker-1")

# 找 ANR 时间
... 5 seconds earlier ...
```

**关键信息**：
1. 主线程在等什么锁
2. 持锁线程在做什么
3. ANR 触发前 5 秒栈

### 2.3 tombstone 重点看什么

```
# 看 backtrace
backtrace:
  #00 pc 0x0000abcd in vendor::hwc::Config::Write() at hwc.cpp:42
  #01 pc 0x00001234 in main at main.cpp:18

# 看 signal
signal: 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x000000000000

# 看 maps（虚拟内存布局）
memory map (1536 entries):
  0x000000001234-0x000000005678 r-xp  /system/lib64/libfoo.so
  ...

# 看 registers
    x0  0000000000000000  x1  0000007f8bcd1234
    x2  0000000000000042  x3  0000000000000000
```

**关键信息**：
1. backtrace 前 5 帧
2. signal 类型 + 触发地址
3. 哪个 .so 出错

### 2.4 dropbox 重点看什么

```bash
# 列 dropbox 全部 entry
$ unzip -p bugreport.zip dumpsys/dumpsys_dropbox.txt | head -50
# 输出：所有 dropbox entry（按时间倒序）

# 看具体 crash
$ unzip -p bugreport.zip FS/data/system/dropbox/system_app_crash@12345.txt
# 含完整 stack + 触发原因
```

### 2.5 ramoops 重点看什么

```bash
# 看 pmsg-ramoops
$ unzip -p bugreport.zip FS/data/vendor/ramoops/pmsg-ramoops-0
# 内核 log（持久化，重启后仍保留）

# 看 console-ramoops
$ unzip -p bugreport.zip FS/data/vendor/ramoops/console-ramoops
# 内核 printk 输出
```

---

## 3. dumpsys/ 详解

### 3.1 50+ dumpsys 文件分类

| 类别 | 文件 | 何时看 |
|:-----|:-----|:------|
| **Activity/Window** | `dumpsys_activity.txt` | ANR / UI 卡死 |
|  | `dumpsys_window.txt` | Window/UI 问题 |
|  | `dumpsys_input.txt` | 输入问题 |
| **Service** | `dumpsys_activity_services.txt` | Service 列表 |
|  | `dumpsys_battery.txt` | 耗电问题 |
|  | `dumpsys_jobscheduler.txt` | Job 调度 |
|  | `dumpsys_alarm.txt` | Alarm 调度 |
| **Memory** | `dumpsys_meminfo.txt` | ⭐ **OOM 必看** |
|  | `dumpsys_procstats.txt` | 进程统计 |
|  | `dumpsys_gfxinfo.txt` | 渲染性能 |
|  | `dumpsys_SurfaceFlinger.txt` | SF 状态 |
| **Network** | `dumpsys_connectivity.txt` | 网络状态 |
|  | `dumpsys_network_management.txt` | 网络策略 |
|  | `dumpsys_wifi.txt` | WiFi 状态 |
| **System** | `dumpsys_diskstats.txt` | 磁盘 IO 统计 |
|  | `dumpsys_dropbox.txt` | dropbox 列表 |
|  | `dumpsys_usagestats.txt` | 使用统计 |
|  | `dumpsys_content.txt` | ContentProvider |
|  | `dumpsys_package.txt` | 包管理 |
|  | `dumpsys_userspace.txt` | 用户空间 |
|  | `dumpsys_appops.txt` | 权限状态 |
|  | `dumpsys_power.txt` | 电源管理 |
|  | `dumpsys_sensorservice.txt` | 传感器 |
|  | `dumpsys_location.txt` | 定位 |
|  | `dumpsys_account.txt` | 账户 |
| **Hardware** | `dumpsys_media_session.txt` | 媒体会话 |
|  | `dumpsys_audio.txt` | 音频 |
|  | `dumpsys_camera.txt` | 相机 |
|  | `dumpsys_display.txt` | 显示 |
|  | `dumpsys_input_method.txt` | 输入法 |
| **Native** | `dumpsys_SurfaceFlinger.txt` | 渲染 |
|  | `dumpsys_gpuservice.txt` | GPU |
|  | `dumpsys_thermal.txt` | 散热 |

### 3.2 dumpsys_meminfo.txt 重点

```bash
# 看总览
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | head -50
# MemTotal / MemFree / Cached / Swap

# 找大进程
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep -A5 "Pss Total" | sort -k3 -n -r | head

# 找 native heap
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep "Native Heap"

# 找 graphics
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep "Graphics"
```

### 3.3 dumpsys_activity.txt 重点

```bash
# 找 ANR 列表
$ unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "ANR"

# 找进程状态
$ unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "ProcessRecord" | head

# 找 top activity
$ unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "mResumedActivity"
```

### 3.4 dumpsys_window.txt 重点

```bash
# 找当前 window
$ unzip -p bugreport.zip dumpsys/dumpsys_window.txt | grep "mCurrentFocus"

# 找 IME
$ unzip -p bugreport.zip dumpsys/dumpsys_window.txt | grep "mInputMethodTarget"
```

---

## 4. logcat/ 详解

### 4.1 5 大 buffer

| 文件 | 内容 | 用途 |
|:-----|:-----|:-----|
| `logcat_main.txt` | 默认（app + system）| **90% 现场看这个** |
| `logcat_system.txt` | system 进程 | init / system_server |
| `logcat_events.txt` | 二进制 events | systrace 用 |
| `logcat_crash.txt` | crash 信息 | NE/ANR 触发时 |
| `logcat_kernel.txt` | kernel log | KE / SELinux denied |

### 4.2 logcat_main.txt 重点

```bash
# 1. 看时间范围
$ unzip -p bugreport.zip logcat/logcat_main.txt | head -3
$ unzip -p bugreport.zip logcat/logcat_main.txt | tail -3
# 头 3 行 + 尾 3 行 = 时间窗口

# 2. 找 FATAL / ANR
$ unzip -p bugreport.zip logcat/logcat_main.txt | grep -E "FATAL|ANR"

# 3. 找 service died
$ unzip -p bugreport.zip logcat/logcat_main.txt | grep "service died"

# 4. 找 SLOW operation
$ unzip -p bugreport.zip logcat/logcat_main.txt | grep "Slow operation"
```

### 4.3 logcat_crash.txt 重点

```bash
# 找 crash 信号
$ unzip -p bugreport.zip logcat/logcat_crash.txt | grep -E "tombstone|sigsegv|sigabrt"

# 找 ProcessRecord died
$ unzip -p bugreport.zip logcat/logcat_crash.txt | grep "Process.*died"
```

### 4.4 logcat_kernel.txt 重点

```bash
# 找 SELinux denied
$ unzip -p bugreport.zip logcat/logcat_kernel.txt | grep "avc: denied"

# 找 kernel panic
$ unzip -p bugreport.zip logcat/logcat_kernel.txt | grep -E "panic|oops"

# 找 cgroup / PSI
$ unzip -p bugreport.zip logcat/logcat_kernel.txt | grep -E "memory.*pressure|cgroup"
```

---

## 5. traces/ 详解

### 5.1 trace 文件类型

| 文件 | 格式 | 用途 |
|:-----|:-----|:-----|
| `systrace.html` | 浏览器 HTML | 浏览器打开看 |
| `systrace_<n>.html` | 分段 systrace | 大 trace 拆分 |
| `perfetto-trace.pb` | Perfetto 二进制 | UI 打开看 |
| `atrace.txt` | 纯文本 trace | 命令行看 |

### 5.2 systrace vs perfetto

| 维度 | systrace | perfetto |
|:-----|:---------|:---------|
| **格式** | HTML + JSON | protobuf |
| **工具** | Chrome 浏览器 | ui.perfetto.dev |
| **大小** | 几 MB | 几 MB-100MB |
| **AOSP 17 状态** | 兼容（不推荐）| **默认** |
| **看 perf counter** | 否 | 是 |

### 5.3 何时用 trace

- **UI 卡顿** → systrace / perfetto 看 main thread + render thread
- **冷启动慢** → perfetto 看 zygote fork + class load
- **NE 现场** → 不必抓 trace（logcat + tombstone 够）
- **KE 现场** → 不必抓 trace（dmesg 够）

---

## 6. proc/ 详解

### 6.1 关键 proc 文件

| 文件 | 用途 | 何时看 |
|:-----|:-----|:------|
| `proc/meminfo` | 内存总览 | ⭐ OOM 现场 |
| `proc/vmstat` | 虚拟内存统计 | OOM 分析 |
| `proc/cmdline` | kernel cmdline | SELinux / boot mode |
| `proc/version` | kernel 版本 | 版本对齐 |
| `proc/mounts` | 挂载信息 | 磁盘问题 |
| `proc/pressure/cpu` | CPU PSI 压力 | 性能问题 |
| `proc/pressure/memory` | **内存 PSI 压力** | ⭐ OOM 早期信号 |
| `proc/pressure/io` | IO PSI 压力 | 磁盘 IO 慢 |
| `proc/interrupts` | 中断统计 | 性能问题 |
| `proc/schedstat` | 调度统计 | 性能问题 |
| `proc/zoneinfo` | 内存 zone | 内存分析 |
| `proc/buddyinfo` | buddy allocator | 内存碎片 |
| `proc/slabinfo` | slab allocator | 内核 slab 泄漏 |
| `proc/pagetypeinfo` | 页面类型 | 内存分析 |
| `proc/vmallocinfo` | vmalloc 统计 | 内核内存 |
| `proc/softirqs` | 软中断统计 | 网络问题 |
| `proc/net/dev` | 网络统计 | 网络问题 |
| `proc/net/tcp` | TCP 状态 | 网络问题 |
| `proc/net/xt_qtaguid/stats` | 流量统计 | 流量问题 |
| `proc/sys/kernel/tainted` | kernel 警告位 | KE 现场 |

### 6.2 proc/meminfo 重点字段

```
MemTotal:        3909976 kB
MemFree:          234560 kB
MemAvailable:    1234567 kB   ← 关键：可用内存
Buffers:          123456 kB
Cached:           567890 kB
SwapCached:            0 kB
Active:          1234567 kB
Inactive:         567890 kB
Active(anon):     890123 kB
Inactive(anon):   234567 kB
Active(file):     344444 kB
Inactive(file):   333323 kB
Unevictable:       12345 kB
Mlocked:               0 kB
AnonPages:       1123456 kB
Mapped:           345678 kB
Shmem:             12345 kB
KReclaimable:     234567 kB
Slab:             345678 kB
SReclaimable:     234567 kB
SUnreclaim:       111111 kB
KernelStack:       12345 kB
PageTables:        45678 kB
NFS_Unstable:          0 kB
Bounce:                0 kB
WritebackTmp:          0 kB
CommitLimit:     4567890 kB
Committed_AS:    7890123 kB   ← 关键：commit（> Limit → OOM 风险）
VmallocTotal:   263061440 kB
VmallocUsed:       12345 kB
VmallocChunk:          0 kB
Percpu:             1234 kB
HardwareCorrupted:     0 kB
AnonHugePages:    234567 kB
ShmemHugePages:        0 kB
ShmemPmdMapped:        0 kB
FileHugePages:         0 kB
FilePmdMapped:         0 kB
CmaTotal:         123456 kB
CmaFree:          100000 kB
HugePages_Total:       0
HugePages_Free:        0
HugePages_Rsvd:        0
HugePages_Surp:        0
Hugepagesize:       2048 kB
Hugetlb:               0 kB
DirectMap4k:      234567 kB
DirectMap2M:     3456789 kB
DirectMap1G:           0 kB
```

**重点 4 个字段**：
- `MemAvailable` < 200MB → OOM 风险
- `Committed_AS` > `CommitLimit` → OOM 风险
- `CmaFree` < `CmaTotal * 0.1` → CMA 紧张
- `SUnreclaim` > 100MB → 内核 slab 泄漏

### 6.3 proc/pressure/memory 重点

```
# 格式：some avg10=X.XX avg60=Y.YY avg300=Z.ZZ total=W
# some = 部分任务阻塞
# full = 所有任务阻塞（> 0 表示有任务饿死）

some avg10=0.00 avg60=0.00 avg300=0.00 total=0
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
```

**阈值**：
- `some avg10 > 5%` → 内存压力中
- `some avg10 > 20%` → 内存压力高
- `full avg10 > 0%` → 有任务完全饿死

### 6.4 proc/cmdline 重点

```
$ unzip -p bugreport.zip proc/cmdline
androidboot.boot_devices=soc androidboot.selinux=enforcing androidboot.serialno=xxx
```

**关键参数**：
- `androidboot.selinux` → enforcing / permissive / disabled
- `androidboot.boot_devices` → 启动设备
- `androidboot.serialno` → 设备 SN
- `androidboot.hardware` → hardware 平台
- `androidboot.hardware.platform` → SoC 平台

---

## 7. kernel/ 详解

### 7.1 关键 kernel 文件

| 文件 | 用途 | 何时看 |
|:-----|:-----|:------|
| `kernel/dmesg.txt` | 当前 boot kernel log | ⭐ KE 现场 |
| `kernel/last_kmsg.txt` | 上次 boot kernel log | ⭐ bootloop / KE |
| `kernel/kallsyms` | kernel symbol table | crash 解析 |
| `kernel/modules` | 加载的 module | 驱动问题 |
| `kernel/cpuinfo` | CPU 信息 | 性能问题 |
| `kernel/devicetree` | device tree | 硬件问题 |
| `kernel/interrupts` | 中断 | 性能问题 |

### 7.2 dmesg.txt 重点

```bash
# 看启动时间
$ unzip -p bugreport.zip kernel/dmesg.txt | head -5
# [    0.000000] Linux version 6.18.0 ...

# 找 panic / oops
$ unzip -p bugreport.zip kernel/dmesg.txt | grep -E "panic|oops|BUG"

# 找 SELinux denied
$ unzip -p bugreport.zip kernel/dmesg.txt | grep "avc: denied"

# 找 module load
$ unzip -p bugreport.zip kernel/dmesg.txt | grep "module"

# 找 cgroup
$ unzip -p bugreport.zip kernel/dmesg.txt | grep "cgroup"
```

### 7.3 last_kmsg.txt 重点

**与 dmesg.txt 的区别**：
- `dmesg.txt` = 当前 boot 的 ringbuffer（重启丢）
- `last_kmsg.txt` = **上次 boot 的 kernel log**（持久化）

**何时用**：
- bootloop → 拉 last_kmsg 看上次 boot 死在哪
- KE 复现 → 拉 last_kmsg 看 panic 现场

---

## 8. 8 类事故对应表（oncall 5 秒定位）

| 事故 | 第一文件 | 第二文件 | 第三文件 |
|:-----|:--------|:--------|:--------|
| **ANR（app 卡死）** | `FS/data/anr/traces.txt` | `logcat/logcat_main.txt` | `dumpsys/dumpsys_activity.txt` |
| **ANR（system_server）** | `dumpsys/dumpsys_activity.txt` | `logcat/logcat_system.txt` | `FS/data/anr/traces.txt` |
| **NE（Native Crash）** | `FS/data/tombstones/tombstone_*` | `logcat/logcat_crash.txt` | `FS/data/system/dropbox/` |
| **JE（Java Exception）** | `logcat/logcat_crash.txt` | `logcat/logcat_main.txt` | `dumpsys/dumpsys_dropbox.txt` |
| **OOM** | `proc/meminfo` | `dumpsys/dumpsys_meminfo.txt` | `proc/pressure/memory` |
| **KE（Kernel Exception）** | `kernel/dmesg.txt` | `kernel/last_kmsg.txt` | `logcat/logcat_kernel.txt` |
| **bootloop** | `kernel/last_kmsg.txt` | `logcat/logcat_system.txt` | `logcat/logcat_kernel.txt` |
| **SWT（system watchdog）** | `logcat/logcat_main.txt` | `dumpsys/dumpsys_activity.txt` | `kernel/dmesg.txt` |
| **REBOOT** | `kernel/last_kmsg.txt` | `dumpsys/dumpsys_dropbox.txt` | `logcat/logcat_system.txt` |
| **Janky / 卡顿** | `traces/systrace.html` | `traces/perfetto-trace.pb` | `dumpsys/dumpsys_gfxinfo.txt` |
| **高 CPU** | `proc/pressure/cpu` | `logcat/logcat_main.txt` | `dumpsys/dumpsys_cpuinfo.txt` |
| **高 IO 等待** | `proc/pressure/io` | `kernel/dmesg.txt` | `dumpsys/dumpsys_diskstats.txt` |
| **耗电** | `dumpsys/dumpsys_battery.txt` | `dumpsys/dumpsys_batterystats.txt` | `dumpsys/dumpsys_power.txt` |
| **WiFi 断** | `dumpsys/dumpsys_wifi.txt` | `logcat/logcat_main.txt` | `dumpsys/dumpsys_connectivity.txt` |
| **蓝牙断** | `dumpsys/dumpsys_bluetooth_manager.txt` | `logcat/logcat_main.txt` | - |

---

## 9. 8 类文件的"看 / 不看"原则

### 9.1 高频（80% 取证时间）

```
✅ FS/data/anr/traces.txt        ANR 必看
✅ FS/data/tombstones/tombstone_*  NE 必看
✅ logcat/logcat_main.txt         通用
✅ logcat/logcat_system.txt       init / system_server
✅ logcat/logcat_crash.txt        crash
✅ logcat/logcat_kernel.txt       kernel / SELinux
✅ dumpsys/dumpsys_meminfo.txt    OOM
✅ kernel/dmesg.txt               KE
✅ kernel/last_kmsg.txt           bootloop
✅ proc/meminfo                   OOM
✅ proc/pressure/memory           OOM 早期
```

### 9.2 中频（按事故看）

```
🟡 dumpsys/dumpsys_activity.txt  ANR / Activity
🟡 dumpsys/dumpsys_window.txt    Window / UI
🟡 dumpsys/dumpsys_battery.txt   耗电
🟡 dumpsys/dumpsys_dropbox.txt   crash 历史
🟡 FS/data/system/dropbox/       crash 历史
🟡 FS/data/vendor/ramoops/       KE
🟡 traces/perfetto-trace.pb      卡顿 / 启动
🟡 proc/cmdline                  SELinux mode
🟡 proc/pressure/cpu             CPU 压力
🟡 proc/pressure/io              IO 压力
```

### 9.3 低频（特定场景才看）

```
⚪ dumpsys/dumpsys_gfxinfo.txt   渲染性能深度
⚪ dumpsys/dumpsys_gpuservice.txt GPU 状态
⚪ dumpsys/dumpsys_SurfaceFlinger.txt  SF 深度
⚪ proc/slabinfo                 kernel slab 泄漏
⚪ proc/buddyinfo                内存碎片
⚪ kernel/kallsyms               symbol 反查
```

---

## 10. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 Bugreport 总览](01-Bugreport-总览与生成解析.md) | 工具 + 总览 |
| [03 关键文件速查](03-Bugreport-关键文件速查.md) | 下篇 |
| [04 实战 5 类典型案例](04-Bugreport-实战5类典型案例.md) | 实战 |
| [05 bugreport vs perfetto](05-Bugreport-vs-perfetto-trace.md) | 工具边界 |
| [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../../03-卷3-调查工具/24-Dumpsys · Bugreport · DropBox/12-dumpsys实战SOP.md) | dumpsys 完整 |
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) | perfetto 完整 |
| [06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../../03-卷3-调查工具/26-断点与 Native 调试/Logcat_Complete_Guide.md) | logcat 完整 |
| [02-Symptom/S00-S09 7 大症状](../../02-Symptom/) | 7 大症状视角 |
| [03-Forensics/F00-F07 7 大取证](../../03-Forensics/) | 取证总览 |
| [06-Case/Cases-Extended/](../../../06-Case/Cases-Extended/) | 实战案例 |

---

## 11. 下一篇预告 + 自检

### 11.1 下一篇

[03 Bugreport 关键文件速查](03-Bugreport-关键文件速查.md) 讲清：
- 30+ 关键文件逐一"看 / 不看"指南
- 5 类事故下"先看哪个文件 / 再看哪个文件 / 不要看哪个"
- 真实 case：5 分钟定位到具体行号
- 完整 grep 命令集

### 11.2 看完本文的自检

- [ ] 能说 bugreport.zip 6 大子目录
- [ ] 能从 1 个事故类型秒级定位 3 个关键文件
- [ ] 能用 §8 8 类事故对应表
- [ ] 能区分 dmesg.txt vs last_kmsg.txt
- [ ] 能区分 logcat 5 大 buffer 各自用途
- [ ] 知道 proc/meminfo 4 个关键字段

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
