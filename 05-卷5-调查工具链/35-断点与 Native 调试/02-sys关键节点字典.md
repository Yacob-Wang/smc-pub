# 06-Foundation/Tools/Filesystem-Cheat-Sheet · 02 · /sys 关键节点字典

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 设备 / 硬件 / 调优
>
> **强依赖**：[01 /proc 关键文件字典](01-/proc关键文件字典.md) · [06-Foundation/Build-System/Soong/05-Ninja文件解读](../../Build-System/Soong/05-Ninja生成与ninja文件解读.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 /sys 30+ 关键节点（按 5 大类：硬件 / 设备 / 内核 / 调度 / 文件系统）+ /dev/block/by-name 设备查找路径讲清楚——oncall 5 秒定位"设备信息 / 调优参数"
- **不是**：不复述 [01 /proc 字典](01-/proc关键文件字典.md)（本文是它的姐妹篇）；不复述 [06-Foundation/Build-System/08-Vendor_Specific_Differences](../../Build-System/08_Vendor_Specific_Differences.md)
- **承接自**：[01 §0 /proc 字典](01-/proc关键文件字典.md) → 本文 /sys 是进程外的"硬件 + 内核配置"
- **衔接去**：[06-Foundation/Build-System/01_AOSP_Build_Environment](../../Build-System/01_AOSP_Build_Environment.md) / [06-Foundation/Build-System/04_Build_Configuration_And_Options](../../Build-System/04_Build_Configuration_And_Options.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章先讲 /proc vs /sys 差异 | 避免混淆 |
| 2 | 5 大类：硬件 / 设备 / 内核 / 调度 / 文件系统 | 跟内核子系统对齐 |
| 3 | 第 6 章 /dev/block/by-name 设备查找 | oncall 5 秒找设备 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**/sys = Linux sysfs（内核 → 用户空间接口）——硬件信息 + 设备属性 + 内核调优参数。oncall 5 秒定位"设备是什么 / 怎么调"。**

AOSP 17 上 /sys 含 200+ 节点，**但 90% 取证只看 30 个**。本文给 30 个节点的"用途 / 看什么 / 怎么调"对照表。

---

## 1. /proc vs /sys 核心差异

### 1.1 5 维差异

| 维度 | /proc | /sys |
|:-----|:------|:-----|
| **本质** | 进程 / 系统信息 | 硬件 / 设备 / 内核配置 |
| **来源** | 内核动态生成 | 设备驱动 + 内核配置 |
| **内容** | 进程级（/proc/<pid>/）+ 系统级 | 设备树 + 内核对象 |
| **可写** | 大多只读 | 不少可写（调优用）|
| **AOSP 17 默认** | 默认 | 默认 |

### 1.2 何时用哪个

| 场景 | 用 /proc | 用 /sys |
|:-----|:--------|:-------|
| **看内存** | `/proc/meminfo` | `/sys/fs/cgroup/memory/...` |
| **看 CPU** | `/proc/stat`, `/proc/loadavg` | `/sys/devices/system/cpu/...` |
| **看进程** | `/proc/<pid>/...` | （不适用）|
| **看设备** | `/proc/partitions` | `/sys/block/...`, `/sys/class/...` |
| **看内核参数** | `/proc/sys/...` | `/sys/module/...` |
| **看调度** | `/proc/schedstat` | `/sys/kernel/debug/sched/...` |

### 1.3 5 大类速览

```
/sys
├── /sys/devices/        ← 设备树（按总线组织）
├── /sys/class/          ← 设备类（按功能组织）
├── /sys/block/          ← 块设备（磁盘 / 分区）
├── /sys/bus/            ← 总线（PCI / USB / I2C / ...）
├── /sys/kernel/         ← 内核对象
│   ├── /sys/kernel/debug/  ← debugfs（debugfs 挂载点）
│   └── /sys/kernel/mm/     ← mm 子系统
├── /sys/fs/             ← 文件系统
│   ├── /sys/fs/cgroup/   ← cgroup
│   ├── /sys/fs/ext4/     ← ext4 调优
│   └── /sys/fs/selinux/  ← SELinux 接口
├── /sys/module/         ← 已加载模块
├── /sys/power/          ← 电源管理
└── /sys/firmware/       ← 固件
```

---

## 2. 硬件类（5 大节点）

### 2.1 /sys/devices/system/cpu/

**用途**：CPU 拓扑 + 频率

**关键节点**：

```bash
# 1. CPU 拓扑
$ adb shell ls /sys/devices/system/cpu/
cpu0/  cpu1/  cpu2/  cpu3/  cpu4/  cpu5/  cpu6/  cpu7/  online  offline  present

# 2. CPU 频率
$ adb shell cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
# 当前频率（Hz）

$ adb shell cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq
# 最大频率

# 3. governor（性能模式）
$ adb shell cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
# schedutil / performance / powersave

# 4. CPU 启用
$ adb shell cat /sys/devices/system/cpu/online
# 0-7（0-7 都启用）
```

**4 个告警场景**：

| 现象 | 阈值 | 根因 |
|:-----|:-----|:-----|
| `scaling_cur_freq` 持续 = `cpuinfo_min_freq` | CPU 节流 | 散热 / 电源 |
| `scaling_governor` = powersave | 性能差 | 误配 |
| `online` = 0-N (N<总核数) | CPU 离线 | thermal / hotplug |
| `cpuinfo_max_freq` < 标称 | CPU 降频 | vendor 限制 |

### 2.2 /sys/devices/system/clk/（kernel clk）

**用途**：clock 树（kernel 层）

**看什么**：

```bash
# 1. 找某 clock
$ adb shell ls /sys/kernel/debug/clk/

# 2. 看 clock rate
$ adb shell cat /sys/kernel/debug/clk/<clock>/clk_rate
```

**适用场景**：debug 时钟树配置错误

### 2.3 /sys/class/ 设备类

**用途**：按功能分组的设备

**5 大常用 class**：

```bash
# 1. 块设备（磁盘 / 分区）
$ adb shell ls /sys/class/block/
loop0  loop1  loop2  loop3  loop4  loop5  loop6  loop7  sda  sdb

# 2. 输入设备
$ adb shell ls /sys/class/input/
event0  event1  event2  input0  mice  mouse0

# 3. 网络设备
$ adb shell ls /sys/class/net/
lo  eth0  wlan0  rmnet0  ...

# 4. LED
$ adb shell ls /sys/class/leds/
red  green  blue  lcd-backlight  ...

# 5. 电源
$ adb shell ls /sys/class/power_supply/
battery  usb  dc  wireless  ...
```

**4 个关键 grep**：

```bash
# 1. 找 input event
$ adb shell ls /sys/class/input/ | grep event

# 2. 找网络设备
$ adb shell ls /sys/class/net/ | grep -v lo

# 3. 找 battery
$ adb shell ls /sys/class/power_supply/battery/

# 4. 找 LED
$ adb shell ls /sys/class/leds/lcd-backlight/
```

### 2.4 /sys/devices/LNXSYSTM:00/

**用途**：DMI / SMBIOS 信息（系统硬件信息）

**看什么**：

```bash
$ adb shell ls /sys/devices/LNXSYSTM:00/
# BIOS info / System info / Baseboard info / Chassis info / ...

$ adb shell cat /sys/devices/LNXSYSTM:00/LNXSYBUS:00/PNP0A03:00/device:00/...
# 设备树
```

**适用场景**：硬件兼容性问题

### 2.5 /sys/firmware/

**用途**：固件信息

**关键节点**：

```bash
# 1. 设备树 compatible
$ adb shell cat /sys/firmware/devicetree/base/compatible
# qcom,sm8150  或  qcom,sm4450

# 2. 固件加载
$ adb shell ls /sys/firmware/efi/  # EFI 设备
```

---

## 3. 设备类（5 大节点）

### 3.1 /sys/block/

**用途**：块设备（磁盘 / 分区）

**关键节点**：

```bash
# 1. 块设备列表
$ adb shell ls /sys/block/
sda  sdb  sdc  mmcblk0  mmcblk1

# 2. 分区
$ adb shell ls /sys/block/sda/
sda1  sda2  sda3  sda4  ...
# 或
$ adb shell ls /sys/block/mmcblk0/
mmcblk0p1  mmcblk0p2  mmcblk0p3  ...

# 3. 看设备大小
$ adb shell cat /sys/block/sda/size
# 扇区数（除 2 = GB）
# 例：250059665920 / 2 = 125029832960 字节

# 4. 看设备型号
$ adb shell cat /sys/block/sda/device/model
# Samsung SSD 970 EVO

# 5. 看调度器
$ adb shell cat /sys/block/sda/queue/scheduler
# [none] mq-deadline kyber bfq

# 6. 看 read ahead
$ adb shell cat /sys/block/sda/queue/read_ahead_kb
# 128
```

**关键 grep**：

```bash
# 1. 列所有块设备 + 型号
$ adb shell "for d in /sys/block/*; do echo -n \"\$(basename \$d) \"; cat \$d/device/model 2>/dev/null; done"

# 2. 找某设备调度器
$ adb shell cat /sys/block/sda/queue/scheduler

# 3. 找 read ahead KB
$ adb shell cat /sys/block/sda/queue/read_ahead_kb

# 4. 找 IO scheduler 配置
$ adb shell cat /sys/block/sda/queue/iosched/
```

### 3.2 /sys/bus/ 总线

**用途**：按总线组织设备

**5 大总线**：

```bash
# 1. PCI 总线
$ adb shell ls /sys/bus/pci/devices/

# 2. USB 总线
$ adb shell ls /sys/bus/usb/devices/

# 3. I2C 总线
$ adb shell ls /sys/bus/i2c/devices/

# 4. SPI 总线
$ adb shell ls /sys/bus/spi/devices/

# 5. platform 总线
$ adb shell ls /sys/bus/platform/devices/
```

**看什么**：

```bash
# 1. USB 设备
$ adb shell ls /sys/bus/usb/devices/1-1/
# 1-1:1.0/  bMaxPower  ...
$ adb shell cat /sys/bus/usb/devices/1-1/idVendor
$ adb shell cat /sys/bus/usb/devices/1-1/idProduct

# 2. platform 设备
$ adb shell ls /sys/bus/platform/devices/ | grep "qcom"
# 厂商设备
```

### 3.3 /dev/block/by-name/

**用途**：AOSP 标准分区查找

**关键节点**：

```bash
# 1. 列所有 by-name 链接
$ adb shell ls -la /dev/block/by-name/
# system -> /dev/block/sdaXX
# vendor -> /dev/block/sdaXX
# boot -> /dev/block/sdaXX
# userdata -> /dev/block/sdaXX
# ...

# 2. 找 system 在哪个设备
$ adb shell readlink /dev/block/by-name/system
# /dev/block/sda5

# 3. 找 boot 在哪个设备
$ adb shell readlink /dev/block/by-name/boot
# /dev/block/sda1

# 4. 找 userdata
$ adb shell readlink /dev/block/by-name/userdata
# /dev/block/sda45
```

**oncall 5 秒定位**：

```bash
# 1. 找 system 设备节点
$ adb shell readlink /dev/block/by-name/system

# 2. 直接 dd 到 system 分区
$ adb shell dd if=/sdcard/new_system.img of=$(readlink /dev/block/by-name/system)

# 3. 找 vendor
$ adb shell readlink /dev/block/by-name/vendor

# 4. 找 boot
$ adb shell readlink /dev/block/by-name/boot
```

### 3.4 /dev/block/by-path/

**用途**：按物理路径找设备

```bash
$ adb shell ls /dev/block/by-path/
# platform-xxx\:0\:0\:0-scsi-0\:0\:0\:0
# platform-xxx-pci-0000\:00\:1f\.2-ata-1
```

### 3.5 /dev/block/by-uuid/

**用途**：按 UUID 找设备

```bash
$ adb shell ls -la /dev/block/by-uuid/
# 1234-5678 -> /dev/block/sda5
# abcdef-... -> /dev/block/sda6
```

**适用场景**：ext4 分区按 UUID 挂载

---

## 4. 内核类（5 大节点）

### 4.1 /sys/kernel/debug/（debugfs）

**用途**：内核调试接口

**看什么**：

```bash
# 1. 看 debugfs 挂载
$ adb shell mount | grep debugfs
# debugfs on /sys/kernel/debug type debugfs (rw,seclabel)

# 2. 调度器 debug
$ adb shell ls /sys/kernel/debug/sched/
# 实时调度信息

# 3. tracing debug
$ adb shell ls /sys/kernel/debug/tracing/
# trace 抓取（见 [06-Foundation/Tools/Tracing](../../Tools/Tracing/)）

# 4. 内核锁
$ adb shell cat /sys/kernel/debug/lockdep
# lockdep 状态

# 5. slab 详细
$ adb shell cat /sys/kernel/debug/slab/
# 详细 slab 分配
```

**3 个告警场景**：

| 节点 | 阈值 | 根因 |
|:-----|:-----|:-----|
| `sched/latency` | > 10ms | 调度延迟 |
| `tracing/trace` | 大量 events | 系统繁忙 |
| `slab/` | 大 slab | 内存泄漏 |

### 4.2 /sys/kernel/mm/

**用途**：内存管理子系统

**关键节点**：

```bash
# 1. transparent hugepage
$ adb shell cat /sys/kernel/mm/transparent_hugepage/enabled
# madvise（Android 默认）

# 2. swap
$ adb shell cat /sys/kernel/mm/swap/vm_swappiness
# 0（Android 默认不 swap）

# 3. page table
$ adb shell ls /sys/kernel/mm/page_table/
```

### 4.3 /sys/module/

**用途**：已加载的 kernel module

**看什么**：

```bash
# 1. 列所有 module
$ adb shell ls /sys/module/ | head
# 8021q  ac97  adsp_loader  binder  ...

# 2. 看 module 信息
$ adb shell cat /sys/module/binder/version
# Android version

# 3. 看 module 参数
$ adb shell ls /sys/module/binder/parameters/

# 4. 看 module 引用计数
$ adb shell cat /sys/module/binder/refcnt
# 0（未引用）
```

**3 个告警场景**：

| 现象 | 阈值 | 根因 |
|:-----|:-----|:-----|
| `refcnt` 一直 > 0 | module 引用泄漏 | use count bug |
| `version` = "0.0" | debug build | 厂商自定 |
| parameters 改不了 | read-only | 设计 |

### 4.4 /sys/power/

**用途**：电源管理

**关键节点**：

```bash
# 1. 唤醒源
$ adb shell cat /sys/power/wakeup_count
# 0

# 2. 自动睡眠
$ adb shell cat /sys/power/autosleep
# mem

# 3. 状态
$ adb shell cat /sys/power/state
# mem
```

### 4.5 /sys/fs/selinux/

**用途**：SELinux 用户空间接口

**关键节点**：

```bash
# 1. enforcing 状态
$ adb shell cat /sys/fs/selinux/enforce
# 1

# 2. 当前 policy
$ adb shell cat /sys/fs/selinux/policy
# binary

# 3. 加载新 policy
$ adb shell echo 1 > /sys/fs/selinux/load
# 仅在 init 进程可写
```

---

## 5. 调度类（cgroup）

### 5.1 /sys/fs/cgroup/

**用途**：cgroup v2（Android 12+ 默认）

**关键节点**：

```bash
# 1. cgroup 根
$ adb shell ls /sys/fs/cgroup/
# cgroup.controllers  cgroup.max.depth  ...
# cgroup.procs  cgroup.stat  ...
# init/  system/  vendor/  ...

# 2. cgroup 版本
$ adb shell cat /sys/fs/cgroup/cgroup.controllers
# cpuset cpu io memory hugetlb pids

# 3. 进程所在 cgroup
$ adb shell cat /proc/self/cgroup
# 0::/init

# 4. 子 cgroup
$ adb shell ls /sys/fs/cgroup/init/
# cgroup.procs  cgroup.subtree_control  memory.*  cpu.*  ...
```

### 5.2 4 大 cgroup 子系统

#### memory cgroup

```bash
# 1. 找某 app 的 memory cgroup
$ adb shell ls /sys/fs/cgroup/memory/ | grep "com.example.app"
# 或
$ adb shell cat /sys/fs/cgroup/memory/<cgroup>/memory.peak
# 峰值内存

# 2. 看 memory.current
$ adb shell cat /sys/fs/cgroup/memory/<cgroup>/memory.current
# 当前内存

# 3. 看 memory.high（软上限）
$ adb shell cat /sys/fs/cgroup/memory/<cgroup>/memory.high
# 应用触发压力

# 4. 看 memory.max（硬上限）
$ adb shell cat /sys/fs/cgroup/memory/<cgroup>/memory.max
# 超过就 OOM kill
```

#### cpu cgroup

```bash
# 1. CPU 配额
$ adb shell cat /sys/fs/cgroup/cpu/<cgroup>/cpu.max
# 50000 100000（50% 1 核）

# 2. CPU 统计
$ adb shell cat /sys/fs/cgroup/cpu/<cgroup>/cpu.stat
# usage_usec 1234567
# nr_periods 100
# throttled_usec 5678
```

**告警**：
- `throttled_usec > 100ms` → CPU 被节流
- `usage_usec / nr_periods > 1e6` → 持续占用 1 核

#### cpuset cgroup

```bash
# 1. 允许的 CPU
$ adb shell cat /sys/fs/cgroup/cpuset/<cgroup>/cpuset.cpus
# 0-3

# 2. 允许的内存节点
$ adb shell cat /sys/fs/cgroup/cpuset/<cgroup>/cpuset.mems
# 0
```

#### io cgroup

```bash
# 1. IO 统计
$ adb shell cat /sys/fs/cgroup/io/<cgroup>/io.stat
# rbytes=1234 wbytes=5678 rios=10 wios=20

# 2. IO 权重
$ adb shell cat /sys/fs/cgroup/io/<cgroup>/io.weight
# 100
```

### 5.3 找进程 cgroup 路径

```bash
# 1. 从 pid 找 cgroup
$ adb shell cat /proc/<pid>/cgroup
# 0::/init/...

# 2. 直接进 cgroup 目录
$ adb shell cd /sys/fs/cgroup/init/...

# 3. 看 cgroup.procs
$ adb shell cat /sys/fs/cgroup/<path>/cgroup.procs
# 列出 cgroup 内所有 PID
```

---

## 6. 文件系统类

### 6.1 /sys/fs/ext4/

**用途**：ext4 文件系统调优

**关键节点**：

```bash
# 1. mount 选项
$ adb shell cat /sys/fs/ext4/<device>/options
# rw,seclabel,noatime,...

# 2. 写回参数
$ adb shell cat /sys/fs/ext4/<device>/writeback
# 1234

# 3. 最大挂载数
$ adb shell cat /sys/fs/ext4/<device>/max_mount_count
# 36

# 4. 检查间隔
$ adb shell cat /sys/fs/ext4/<device>/check_interval
# 0（关）
```

### 6.2 /sys/fs/f2fs/

**用途**：f2fs 文件系统（Samsung）

**关键节点**：

```bash
# 1. 调度
$ adb shell cat /sys/fs/f2fs/<device>/s_dirty_segments
# 脏段数

# 2. GC 状态
$ adb shell cat /sys/fs/f2fs/<device>/gc_urgent
# 0/1
```

### 6.3 /sys/fs/selinux/ 详解

**见 [06-Foundation/SELinux/05-init进程与SELinux：分阶段加载](../../SELinux/05-init进程与SELinux：分阶段加载.md) §3.2**

---

## 7. /dev/block/by-name 完整指南

### 7.1 完整分区速查（AOSP 17）

| 分区 | 大小（参考）| 用途 |
|:-----|:----------|:-----|
| `boot` | 50-100MB | kernel + ramdisk |
| `init_boot` | 10-30MB | first stage init |
| `vendor_boot` | 10-50MB | vendor ramdisk |
| `dtbo` | 几 MB | device tree overlay |
| `system` | 800MB-2GB | system 分区 |
| `system_ext` | 100-500MB | system extension |
| `product` | 50-200MB | product 定制 |
| `vendor` | 50-500MB | vendor 私有 |
| `system_dlkm` | 10-50MB | 系统内核模块 |
| `vendor_dlkm` | 10-50MB | 供应商内核模块 |
| `odm` | 50-200MB | ODM 厂商 |
| `odm_dlkm` | 几 MB | ODM 内核模块 |
| `vbmeta` | < 1MB | AVB 元数据 |
| `vbmeta_system` | < 1MB | system AVB |
| `vbmeta_vendor` | < 1MB | vendor AVB |
| `vbmeta_vendor_dlkm` | < 1MB | vendor_dlkm AVB |
| `userdata` | 1-8GB | 用户数据 |
| `cache` | 100-500MB | 缓存 |
| `metadata` | 几 MB | 加密元数据 |
| `misc` | 几 MB | OTA 状态 |
| `persist` | 几 MB | 持久化 |
| `frp` | 几 MB | 工厂重置保护 |
| `recovery` | 50-100MB | 恢复模式 |
| `super` | 2-4GB | 动态分区容器 |
| `generic_bootloader` | 几 MB | bootloader |

### 7.2 常用 oncall 命令

```bash
# 1. 列所有 by-name
$ adb shell ls -la /dev/block/by-name/

# 2. 找 system
$ adb shell readlink /dev/block/by-name/system

# 3. 找 boot
$ adb shell readlink /dev/block/by-name/boot

# 4. 找 vendor
$ adb shell readlink /dev/block/by-name/vendor

# 5. 找 userdata
$ adb shell readlink /dev/block/by-name/userdata

# 6. 找 recovery
$ adb shell readlink /dev/block/by-name/recovery
```

### 7.3 烧录用法

```bash
# 烧录 system
$ adb shell dd if=/sdcard/new_system.img of=$(readlink /dev/block/by-name/system)

# 烧录 boot
$ adb shell dd if=/sdcard/boot.img of=$(readlink /dev/block/by-name/boot)

# 注意：烧录 system 后 /dev/block/by-name/system 会变（重挂载）
```

---

## 8. 写操作注意（3 类风险）

### 8.1 风险 1：写 sysfs 节点可能破坏系统

```bash
# 错误：改写 CPU governor
$ adb shell echo "performance" > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
# 可能 CPU 不再省电 / 烧机

# 安全：先 cat 看
$ adb shell cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

### 8.2 风险 2：debugfs 仅 root 可见

```bash
# debugfs 默认仅 root
$ adb shell ls /sys/kernel/debug/
# ls: cannot open directory '/sys/kernel/debug/': Permission denied

# 1. adb root
$ adb root
$ adb shell ls /sys/kernel/debug/
# OK
```

### 8.3 风险 3：cgroup 写操作需 root + 可能影响其他进程

```bash
# 错误：改 cgroup memory.max
$ adb shell "echo 100M > /sys/fs/cgroup/memory/<cgroup>/memory.max"
# 该 cgroup 内所有进程 OOM

# 安全：先看现状
$ adb shell cat /sys/fs/cgroup/memory/<cgroup>/memory.max
```

---

## 9. oncall 5 分钟定位速查

### 9.1 设备 / 硬件问题 5 个必看节点

```bash
# 1. /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq
$ adb shell cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
# 看 CPU 是否被节流

# 2. /sys/class/net
$ adb shell ls /sys/class/net/
# 看网络设备

# 3. /sys/class/power_supply/battery/
$ adb shell cat /sys/class/power_supply/battery/capacity
# 看电池

# 4. /sys/block/sda/queue/scheduler
$ adb shell cat /sys/block/sda/queue/scheduler
# 看 IO 调度器

# 5. /sys/devices/LNXSYSTM:00/
$ adb shell ls /sys/devices/LNXSYSTM:00/
# 看硬件信息
```

### 9.2 性能 / 调优 5 个必看节点

```bash
# 1. /sys/devices/system/cpu/cpu*/cpufreq/
$ adb shell cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# 2. /sys/fs/cgroup/memory/<cgroup>/memory.peak
$ adb shell cat /sys/fs/cgroup/memory/<cgroup>/memory.peak

# 3. /sys/fs/cgroup/cpu/<cgroup>/cpu.stat
$ adb shell cat /sys/fs/cgroup/cpu/<cgroup>/cpu.stat
# throttled_usec 监控

# 4. /sys/block/sda/queue/read_ahead_kb
$ adb shell cat /sys/block/sda/queue/read_ahead_kb

# 5. /sys/kernel/mm/transparent_hugepage/enabled
$ adb shell cat /sys/kernel/mm/transparent_hugepage/enabled
```

### 9.3 SELinux 现场 5 个必看节点

```bash
# 1. /sys/fs/selinux/enforce
$ adb shell cat /sys/fs/selinux/enforce
# 1 = enforcing

# 2. /sys/fs/selinux/policy
$ adb shell cat /sys/fs/selinux/policy | wc -c
# binary policy size

# 3. /sys/fs/selinux/checkreqprot
$ adb shell cat /sys/fs/selinux/checkreqprot
# 0

# 4. /proc/cmdline
$ adb shell cat /proc/cmdline | tr '\0' '\n' | grep selinux

# 5. /sys/fs/selinux/avc/
$ adb shell ls /sys/fs/selinux/avc/
# AVC cache
```

---

## 10. 关键阈值速查表

| 指标 | 阈值 | 含义 | 节点 |
|:-----|:-----|:-----|:-----|
| scaling_cur_freq | 持续 = cpuinfo_min_freq | CPU 节流 | /sys/devices/system/cpu/.../cpufreq/ |
| scaling_governor | powersave | 性能差 | /sys/devices/system/cpu/.../cpufreq/ |
| memory.peak | > 1GB | 进程内存大 | /sys/fs/cgroup/memory/.../memory.peak |
| memory.current | > 80% memory.max | 接近 OOM | /sys/fs/cgroup/memory/.../memory.current |
| cpu throttled_usec | > 100ms | CPU 节流 | /sys/fs/cgroup/cpu/.../cpu.stat |
| scheduler | none (mq) | kernel mq 调度 | /sys/block/*/queue/scheduler |
| read_ahead_kb | 128 (默认) | 可调优 | /sys/block/*/queue/read_ahead_kb |
| selinux/enforce | 0 (permissive) | 临时绕过 | /sys/fs/selinux/enforce |
| online | 缺核 | 热插拔 | /sys/devices/system/cpu/online |
| Tainted | > 0 | kernel 警告 | /proc/sys/kernel/tainted |

---

## 11. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 /proc 字典](01-/proc关键文件字典.md) | 姐妹篇 |
| [06-Foundation/Build-System/01_AOSP_Build_Environment](../../Build-System/01_AOSP_Build_Environment.md) | 编译环境 |
| [06-Foundation/Build-System/04_Build_Configuration_And_Options](../../Build-System/04_Build_Configuration_And_Options.md) | BoardConfig |
| [06-Foundation/SELinux/05-init进程与SELinux：分阶段加载](../../SELinux/05-init进程与SELinux：分阶段加载.md) | SELinux 接口 |
| [01-Mechanism/Kernel/cgroup/](../../../../01-Mechanism/Kernel/cgroup/) | cgroup 机制 |
| [06-Foundation/Tools/Tracing/ftrace的语法解析](../../Tools/Tracing/ftrace的语法解析.md) | debugfs/tracing |

---

## 12. 文件字典 2 篇收官 + 自检

### 12.1 看完 2 篇文件字典的自检

- [ ] 能区分 /proc vs /sys 5 大差异
- [ ] 知道 /proc 5 大类（内存 / CPU / 网络 / 进程 / 系统）
- [ ] 知道 /sys 5 大类（硬件 / 设备 / 内核 / 调度 / 文件系统）
- [ ] 能从 1 个事故秒级定位该看 /proc 还是 /sys
- [ ] 能用 /dev/block/by-name 5 秒找设备
- [ ] 知道 §10 关键阈值表
- [ ] 知道写 /sys 节点的 3 类风险

### 12.2 收官话

文件字典 2 篇 = oncall 系统级诊断的"基础设施"。下一步推荐读：
- [06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../Tools/Android_Tools/Logcat_Complete_Guide.md) — logcat 深入
- [06-Foundation/SELinux/04-AVC与avc_denied](../../SELinux/04-AVC与avc_denied：从一次denied反推策略.md) — SELinux 排错
- [01-Mechanism/Kernel/cgroup/](../../../../01-Mechanism/Kernel/cgroup/) — cgroup 机制

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，文件字典 2 篇收官）
