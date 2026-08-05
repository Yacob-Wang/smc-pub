# 03-Forensics/Bugreport · 03 · Bugreport 关键文件速查

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 现场取证
>
> **强依赖**：[02 目录结构全梳理](02-Bugreport-目录结构全梳理.md) · [01 Bugreport 总览](01-Bugreport-总览与生成解析.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 bugreport 30+ 关键文件的"看 / 不看"指南做成速查表，5 类事故下"先看哪个 / 再看哪个 / 不要看哪个"明确
- **不是**：不复述 [02 §2-7 各子目录结构](02-Bugreport-目录结构全梳理.md)；不复述 [04 实战 5 案例](04-Bugreport-实战5类典型案例.md)
- **承接自**：[02 §9 看 / 不看原则](02-Bugreport-目录结构全梳理.md)（本文给完整 30 文件速查）
- **衔接去**：[04 实战 5 案例](04-Bugreport-实战5类典型案例.md) / [05 bugreport vs perfetto](05-Bugreport-vs-perfetto-trace.md) / [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../../03-卷3-调查工具/24-Dumpsys · Bugreport · DropBox/12-dumpsys实战SOP.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1-5 章按 5 大 buffer 组织（logcat / FS / dumpsys / proc / kernel）| 跟 bugreport 实际目录对齐 |
| 2 | 每个文件给 3 行信息（用途 / 看什么 / 不看什么）| 5 秒决策 |
| 3 | 第 6 章 30 个 grep 命令 + 第 7 章 7 大症状完整路径 | 实战直接复制粘贴 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**30+ 关键文件逐一"看 / 不看"指南 = oncall 5 秒找到"该看哪个"。**

AOSP 17 bugreport 300+ 文件里**只有 30 个关键文件占 80% 取证时间**——本文给每个文件的 3 行信息（用途 / 看什么 / 不看什么）+ 完整 grep 命令集。

---

## 1. logcat/ 关键文件速查

### 1.1 5 大 buffer 速查

| 文件 | 用途 | 看什么 | 不看什么 |
|:-----|:-----|:-------|:-------|
| `logcat_main.txt` | 默认（app + system）| app 异常 / service 死 / 默认 | kernel |
| `logcat_system.txt` | system 进程 | init / system_server / service_manager | app |
| `logcat_events.txt` | 二进制 events | systrace 解析 | 文本模式 |
| `logcat_crash.txt` | crash 信息 | FATAL / tombstone / ANR 触发 | 正常运行 |
| `logcat_kernel.txt` | kernel log | KE / SELinux denied / panic | app |

### 1.2 logcat_main.txt 重点命令

```bash
# 1. 时间范围
$ unzip -p bugreport.zip logcat/logcat_main.txt | head -1
$ unzip -p bugreport.zip logcat/logcat_main.txt | tail -1

# 2. FATAL / ANR
$ unzip -p bugreport.zip logcat/logcat_main.txt | grep -E "FATAL|ANR"

# 3. service died
$ unzip -p bugreport.zip logcat/logcat_main.txt | grep "service died"

# 4. 特定 package
$ unzip -p bugreport.zip logcat/logcat_main.txt | grep "com.example.app"

# 5. tag 过滤（运行时）
$ adb logcat -s MyTag:V

# 6. level 过滤
$ unzip -p bugreport.zip logcat/logcat_main.txt | grep " E " | head

# 7. 时间过滤
$ unzip -p bugreport.zip logcat/logcat_main.txt | awk '/07-27 10:30:00/,/07-27 10:35:00/'
```

### 1.3 logcat_system.txt 重点命令

```bash
# 1. init 启动
$ unzip -p bugreport.zip logcat/logcat_system.txt | grep "init:"

# 2. service_manager
$ unzip -p bugreport.zip logcat/logcat_system.txt | grep "ServiceManager"

# 3. system_server
$ unzip -p bugreport.zip logcat/logcat_system.txt | grep "SystemServer"

# 4. watchdog
$ unzip -p bugreport.zip logcat/logcat_system.txt | grep -i "watchdog"
```

### 1.4 logcat_crash.txt 重点命令

```bash
# 1. crash 信号
$ unzip -p bugreport.zip logcat/logcat_crash.txt | grep -E "FATAL|tombstone|signal"

# 2. 进程死亡
$ unzip -p bugreport.zip logcat/logcat_crash.txt | grep "Process.*died"

# 3. 堆栈
$ unzip -p bugreport.zip logcat/logcat_crash.txt | grep -A 20 "FATAL EXCEPTION"
```

### 1.5 logcat_kernel.txt 重点命令

```bash
# 1. SELinux denied
$ unzip -p bugreport.zip logcat/logcat_kernel.txt | grep "avc: denied"

# 2. kernel panic / oops
$ unzip -p bugreport.zip logcat/logcat_kernel.txt | grep -E "panic|oops"

# 3. memory cgroup
$ unzip -p bugreport.zip logcat/logcat_kernel.txt | grep -E "memory.*cgroup|psi"

# 4. scheduler
$ unzip -p bugreport.zip logcat/logcat_kernel.txt | grep -E "sched|throttled"
```

---

## 2. FS/ 关键文件速查

### 2.1 ANR / NE 现场

| 文件 | 用途 | 看什么 | 不看什么 |
|:-----|:-----|:-------|:-------|
| `FS/data/anr/traces.txt` | ANR 栈 | ⭐ main thread / blocked on | 非 main thread |
| `FS/data/anr/traces_<pid>.txt` | 特定进程 ANR | 跟 main 同样的逻辑 | 无关进程的 |
| `FS/data/tombstones/tombstone_00` | 最新 NE | backtrace / signal / map | 旧的 (tombstone_05+) |
| `FS/data/tombstones/tombstone_01` | 第 2 新 NE | 同上 | - |
| `FS/data/system/dropbox/system_app_crash@*.txt` | dropbox app crash | 完整 stack | 正常运行 |
| `FS/data/system/dropbox/SYSTEM_TOMBSTONE@*.txt` | dropbox NE | 跟 tombstone 一样 | - |

### 2.2 traces.txt 重点命令

```bash
# 1. main thread 状态
$ unzip -p bugreport.zip FS/data/anr/traces.txt | grep -B1 -A30 '"main"'

# 2. 找 blocked on
$ unzip -p bugreport.zip FS/data/anr/traces.txt | grep -E "waiting on|held by"

# 3. 找 ANR 触发点
$ unzip -p bugreport.zip FS/data/anr/traces.txt | grep "ANR"

# 4. 5 秒前栈
$ unzip -p bugreport.zip FS/data/anr/traces.txt | grep "5 seconds earlier"

# 5. 找 lock
$ unzip -p bugreport.zip FS/data/anr/traces.txt | grep "synchronized"
```

### 2.3 tombstone 重点命令

```bash
# 1. 列所有 tombstone
$ unzip -l bugreport.zip | grep tombstone

# 2. 读最新 tombstone
$ unzip -p bugreport.zip FS/data/tombstones/tombstone_00

# 3. 看 signal 类型
$ unzip -p bugreport.zip FS/data/tombstones/tombstone_00 | grep "signal:"

# 4. 看 backtrace
$ unzip -p bugreport.zip FS/data/tombstones/tombstone_00 | grep -A20 "backtrace:"

# 5. 看 maps（哪个 .so 出错）
$ unzip -p bugreport.zip FS/data/tombstones/tombstone_00 | grep "memory map" -A50 | head
```

### 2.4 dropbox 重点命令

```bash
# 1. 列所有 dropbox
$ unzip -l bugreport.zip | grep dropbox

# 2. 看最近 crash
$ unzip -p bugreport.zip FS/data/system/dropbox/ | grep "crash" | head

# 3. 看 drops 列表
$ unzip -p bugreport.zip dumpsys/dumpsys_dropbox.txt | head -50
```

### 2.5 kernel panic 持久化

| 文件 | 用途 | 看什么 |
|:-----|:-----|:------|
| `FS/data/vendor/ramoops/pmsg-ramoops-0` | 持久化 printk | kernel 启动 log |
| `FS/data/vendor/ramoops/console-ramoops` | 持久化 console | panic 现场 |
| `FS/data/vendor/ramoops/elog_*` | event log | boot / panic event |

```bash
# 1. 看 pmsg
$ unzip -p bugreport.zip FS/data/vendor/ramoops/pmsg-ramoops-0 | head -100

# 2. 看 console
$ unzip -p bugreport.zip FS/data/vendor/ramoops/console-ramoops | tail -100
```

---

## 3. dumpsys/ 关键文件速查

### 3.1 12 大 dumpsys 速查表

| 文件 | 用途 | 看什么 | 不看什么 |
|:-----|:-----|:-------|:-------|
| `dumpsys_activity.txt` | Activity/AMS 状态 | ANR 列表 / 进程状态 / top activity | 详细 fragment 树 |
| `dumpsys_window.txt` | Window/WMS 状态 | current focus / IME / input target | 全 window 树 |
| `dumpsys_input.txt` | Input 状态 | input event / 焦点链 | history |
| `dumpsys_meminfo.txt` | 内存详细 | ⭐ PSS / native heap / graphics | 单进程细节 |
| `dumpsys_procstats.txt` | 进程统计 | OOM adj / 启动时间 | 历史 |
| `dumpsys_gfxinfo.txt` | 渲染性能 | jank 帧 / draw 时间 | 非 UI app |
| `dumpsys_SurfaceFlinger.txt` | SF 状态 | frame latency / layer | 全 layer list |
| `dumpsys_battery.txt` | 电池 | 充电 / 耗电速率 | history |
| `dumpsys_batterystats.txt` | 耗电详细 | wakelock / app 耗电 | 全 history |
| `dumpsys_diskstats.txt` | 磁盘 IO | IO 等待 / 读速率 | - |
| `dumpsys_dropbox.txt` | dropbox 列表 | entry 列表 | 单 entry 详情 |
| `dumpsys_jobscheduler.txt` | Job 调度 | 等待 Job / 当前 Job | history |

### 3.2 dumpsys_meminfo.txt 重点命令

```bash
# 1. 内存总览
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | head -50

# 2. 找 PSS 最大的进程
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep -A5 "Pss Total" | sort -k3 -n -r | head

# 3. 找 native heap
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep -A2 "Native Heap"

# 4. 找 graphics
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep "Graphics"

# 5. 找 swap
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep -A5 "Swap"

# 6. 找 OOM adj
$ unzip -p bugreport.zip dumpsys/dumpsys_procstats.txt | grep "oom"
```

### 3.3 dumpsys_activity.txt 重点命令

```bash
# 1. ANR 列表
$ unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "ANR in"

# 2. 当前焦点
$ unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "mResumedActivity"

# 3. 进程状态
$ unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "ProcessRecord" | head

# 4. 启动超时
$ unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "slow"
```

### 3.4 dumpsys_dropbox.txt 重点命令

```bash
# 1. 列全部 entry
$ unzip -p bugreport.zip dumpsys/dumpsys_dropbox.txt | grep "@" | head -20

# 2. 按 tag 过滤
$ unzip -p bugreport.zip dumpsys/dumpsys_dropbox.txt | grep "system_app_crash"

# 3. 按时间过滤
$ unzip -p bugreport.zip dumpsys/dumpsys_dropbox.txt | grep "2026-07-27"
```

### 3.5 dumpsys_window.txt 重点命令

```bash
# 1. 当前焦点
$ unzip -p bugreport.zip dumpsys/dumpsys_window.txt | grep "mCurrentFocus"

# 2. IME
$ unzip -p bugreport.zip dumpsys/dumpsys_window.txt | grep "mInputMethodTarget"

# 3. 焦点链
$ unzip -p bugreport.zip dumpsys/dumpsys_window.txt | grep "focusedApp"
```

---

## 4. proc/ 关键文件速查

### 4.1 15 大 proc 速查表

| 文件 | 用途 | 看什么 | 不看什么 |
|:-----|:-----|:-------|:-------|
| `proc/meminfo` | 内存总览 | ⭐ MemAvailable / Committed_AS | 单进程 |
| `proc/vmstat` | 虚拟内存统计 | pgscan / pgsteal / allocstall | 详细 zone |
| `proc/cmdline` | kernel cmdline | ⭐ selinux mode | vendor args |
| `proc/version` | kernel 版本 | Linux version | - |
| `proc/mounts` | 挂载 | 异常挂载 / 满 | 默认挂载 |
| `proc/pressure/cpu` | CPU PSI | ⭐ some avg10/full avg10 | total |
| `proc/pressure/memory` | 内存 PSI | ⭐ some avg10/full avg10 | total |
| `proc/pressure/io` | IO PSI | ⭐ some avg10/full avg10 | total |
| `proc/interrupts` | 中断统计 | 异常中断号 | 全部 |
| `proc/schedstat` | 调度统计 | 调度延迟 | - |
| `proc/zoneinfo` | 内存 zone | ⭐ lowmem / 高水位 | 全部 zone |
| `proc/buddyinfo` | buddy allocator | 内存碎片 | - |
| `proc/slabinfo` | slab allocator | ⭐ 内核 slab 泄漏 | 全部 slab |
| `proc/vmallocinfo` | vmalloc 统计 | 异常 vmalloc | - |
| `proc/sys/kernel/tainted` | kernel 警告位 | 非 0 → KE 现场 | 0 |

### 4.2 proc/meminfo 速查

```bash
# 1. 找关键字段
$ unzip -p bugreport.zip proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|Committed_AS|CommitLimit|CmaTotal|CmaFree|SUnreclaim"

# 2. OOM 风险判断
$ unzip -p bugreport.zip proc/meminfo | awk '/MemAvailable:/ { av=$2 }
                                              /CommitLimit:/ { cl=$2 }
                                              /Committed_AS:/ { ca=$2 }
                                              END { 
                                                print "MemAvailable:", av
                                                print "CommitLimit:", cl
                                                print "Committed_AS:", ca
                                                if (ca > cl) print "WARNING: OOM risk"
                                              }'
```

### 4.3 proc/pressure/* 速查

```bash
# 1. CPU 压力
$ unzip -p bugreport.zip proc/pressure/cpu

# 2. 内存压力
$ unzip -p bugreport.zip proc/pressure/memory
# 关键：some avg10 + full avg10

# 3. IO 压力
$ unzip -p bugreport.zip proc/pressure/io

# 4. PSI 阈值判断
$ for p in cpu memory io; do
  echo "=== $p ==="
  unzip -p bugreport.zip proc/pressure/$p | head -1
done
```

### 4.4 proc/cmdline 速查

```bash
# 1. 看 selinux mode
$ unzip -p bugreport.zip proc/cmdline | tr '\0' '\n' | grep selinux
androidboot.selinux=enforcing

# 2. 看设备信息
$ unzip -p bugreport.zip proc/cmdline | tr '\0' '\n' | grep -E "serial|hardware|boot_devices"
```

### 4.5 proc/slabinfo 速查（内存泄漏）

```bash
# 1. 看内核 slab
$ unzip -p bugreport.zip proc/slabinfo

# 2. 找异常 slab
$ unzip -p bugreport.zip proc/slabinfo | sort -k3 -n -r | head

# 3. 找 dentry / inode 泄漏
$ unzip -p bugreport.zip proc/slabinfo | grep -E "dentry|inode"
```

---

## 5. kernel/ 关键文件速查

### 5.1 5 大 kernel 速查

| 文件 | 用途 | 看什么 | 不看什么 |
|:-----|:-----|:-------|:-------|
| `kernel/dmesg.txt` | 当前 boot kernel log | ⭐ 启动 / panic / denied | history |
| `kernel/last_kmsg.txt` | 上次 boot kernel log | ⭐ bootloop / KE 复现 | - |
| `kernel/kallsyms` | kernel symbol table | crash 反查 | 全表 |
| `kernel/modules` | 加载的 module | 驱动问题 | - |
| `kernel/cpuinfo` | CPU 信息 | 性能 baseline | - |

### 5.2 dmesg.txt 重点命令

```bash
# 1. 时间范围
$ unzip -p bugreport.zip kernel/dmesg.txt | head -3
$ unzip -p bugreport.zip kernel/dmesg.txt | tail -3

# 2. 启动时间
$ unzip -p bugreport.zip kernel/dmesg.txt | grep "Booting kernel"

# 3. 找 SELinux
$ unzip -p bugreport.zip kernel/dmesg.txt | grep "SELinux" | head

# 4. 找 panic / oops
$ unzip -p bugreport.zip kernel/dmesg.txt | grep -E "panic|oops|BUG"

# 5. 找 module load
$ unzip -p bugreport.zip kernel/dmesg.txt | grep "module" | head

# 6. 找 cgroup
$ unzip -p bugreport.zip kernel/dmesg.txt | grep "cgroup" | head

# 7. 找 PSI
$ unzip -p bugreport.zip kernel/dmesg.txt | grep -E "psi|pressure"
```

### 5.3 last_kmsg.txt 重点命令

```bash
# 1. 直接读（这是上次 boot 的 kernel log）
$ unzip -p bugreport.zip kernel/last_kmsg.txt | head -100

# 2. 找 panic
$ unzip -p bugreport.zip kernel/last_kmsg.txt | grep "panic"

# 3. 找 oops
$ unzip -p bugreport.zip kernel/last_kmsg.txt | grep "Oops"
```

### 5.4 kallsyms 重点命令

```bash
# 1. 找特定 symbol
$ unzip -p bugreport.zip kernel/kallsyms | grep "vfs_read"

# 2. 找某地址的 symbol
$ unzip -p bugreport.zip kernel/kallsyms | grep "ffffffff81234567"
```

---

## 6. 30 个 grep 命令集（速查用）

### 6.1 ANR 5 命令

```bash
# 1. 找 ANR 触发
unzip -p bugreport.zip logcat/logcat_main.txt | grep "ANR in"

# 2. 看主线程栈
unzip -p bugreport.zip FS/data/anr/traces.txt | grep -A30 '"main"'

# 3. 找 blocked on
unzip -p bugreport.zip FS/data/anr/traces.txt | grep "waiting on"

# 4. 找 input dispatching
unzip -p bugreport.zip logcat/logcat_system.txt | grep "Input dispatching"

# 5. ANR 列表
unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "ANR in"
```

### 6.2 NE 5 命令

```bash
# 1. 找 FATAL
unzip -p bugreport.zip logcat/logcat_crash.txt | grep "FATAL"

# 2. 看 tombstone signal
unzip -p bugreport.zip FS/data/tombstones/tombstone_00 | grep "signal:"

# 3. 看 backtrace
unzip -p bugreport.zip FS/data/tombstones/tombstone_00 | grep -A20 "backtrace:"

# 4. 找 maps
unzip -p bugreport.zip FS/data/tombstones/tombstone_00 | grep "memory map" -A50 | head

# 5. dropbox crash
unzip -p bugreport.zip dumpsys/dumpsys_dropbox.txt | grep "crash"
```

### 6.3 OOM 5 命令

```bash
# 1. MemAvailable
unzip -p bugreport.zip proc/meminfo | grep "MemAvailable"

# 2. 内存 PSI
unzip -p bugreport.zip proc/pressure/memory

# 3. 找大进程
unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep -A5 "Pss Total" | sort -k3 -n -r | head

# 4. native heap
unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep -A2 "Native Heap"

# 5. OOM adj
unzip -p bugreport.zip dumpsys/dumpsys_procstats.txt | grep "oom"
```

### 6.4 KE 5 命令

```bash
# 1. dmesg 找 panic
unzip -p bugreport.zip kernel/dmesg.txt | grep -E "panic|oops"

# 2. last_kmsg
unzip -p bugreport.zip kernel/last_kmsg.txt | head -50

# 3. 找 BUG
unzip -p bugreport.zip kernel/dmesg.txt | grep "BUG:"

# 4. pmsg-ramoops
unzip -p bugreport.zip FS/data/vendor/ramoops/pmsg-ramoops-0 | head

# 5. tainted
unzip -p bugreport.zip proc/sys/kernel/tainted
```

### 6.5 SELinux / Permission 5 命令

```bash
# 1. 找 denied
unzip -p bugreport.zip logcat/logcat_kernel.txt | grep "avc: denied"

# 2. 数 denied 数量
unzip -p bugreport.zip logcat/logcat_kernel.txt | grep -c "avc: denied"

# 3. 找 service 启动 denied
unzip -p bugreport.zip logcat/logcat_kernel.txt | grep "transition"

# 4. 找 file_contexts 漏写
unzip -p bugreport.zip logcat/logcat_kernel.txt | grep "unlabeled"

# 5. 找 enforcement 状态
unzip -p bugreport.zip proc/cmdline | tr '\0' '\n' | grep selinux
```

### 6.6 bootloop 5 命令

```bash
# 1. last_kmsg
unzip -p bugreport.zip kernel/last_kmsg.txt | tail -100

# 2. init 启动
unzip -p bugreport.zip logcat/logcat_system.txt | grep "init:" | head -30

# 3. service 重启循环
unzip -p bugreport.zip logcat/logcat_system.txt | grep "restarted"

# 4. SELinux denied
unzip -p bugreport.zip logcat/logcat_kernel.txt | grep "avc: denied" | head

# 5. setenforce
unzip -p bugreport.zip proc/cmdline | tr '\0' '\n' | grep selinux
```

---

## 7. 7 大症状的完整取证路径

### 7.1 S01 ANR 完整路径

```bash
# Step 1: 触发证据
unzip -p bugreport.zip logcat/logcat_main.txt | grep "ANR in"

# Step 2: 主线程栈
unzip -p bugreport.zip FS/data/anr/traces.txt > /tmp/traces.txt
vim /tmp/traces.txt
# /'"main"/' → 看 main thread 状态
# /waiting on/ → 找锁

# Step 3: input 状态
unzip -p bugreport.zip logcat/logcat_system.txt | grep "Input dispatching"

# Step 4: activity 状态
unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "ANR\|slow"

# Step 5: 进程优先级
unzip -p bugreport.zip dumpsys/dumpsys_procstats.txt | grep "<process name>"
```

### 7.2 S02 JE 完整路径

```bash
# Step 1: 触发证据
unzip -p bugreport.zip logcat/logcat_crash.txt | grep "FATAL EXCEPTION"

# Step 2: Java stack
unzip -p bugreport.zip logcat/logcat_crash.txt | grep -A 30 "at "

# Step 3: dropbox
unzip -p bugreport.zip dumpsys/dumpsys_dropbox.txt | grep "java"
```

### 7.3 S03 NE 完整路径

```bash
# Step 1: 触发证据
unzip -p bugreport.zip logcat/logcat_crash.txt | grep "tombstone\|FATAL"

# Step 2: tombstone 完整
unzip -p bugreport.zip FS/data/tombstones/tombstone_00 > /tmp/ts.txt
# 看 signal: + backtrace: + memory map

# Step 3: 同进程前后 30 秒
unzip -p bugreport.zip logcat/logcat_main.txt | grep "<comm>"

# Step 4: 库版本
unzip -p bugreport.zip FS/data/tombstones/tombstone_00 | grep "BuildID"
```

### 7.4 S04 SWT 完整路径

```bash
# Step 1: watchdog 触发
unzip -p bugreport.zip logcat/logcat_main.txt | grep -i "watchdog\|system_server.*died"

# Step 2: ANR 列表
unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "ANR"

# Step 3: 关键 service 状态
unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "ProcessRecord" | head
```

### 7.5 S05 OOM 完整路径

```bash
# Step 1: PSI 早期信号
unzip -p bugreport.zip proc/pressure/memory
# some avg10 > 20% → 内存压力高

# Step 2: MemAvailable
unzip -p bugreport.zip proc/meminfo | grep "MemAvailable"
# < 200MB → 风险

# Step 3: 大进程
unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep -A5 "Pss Total" | sort -k3 -n -r | head

# Step 4: native heap / graphics
unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep "Native Heap\|Graphics"

# Step 5: kernel slab
unzip -p bugreport.zip proc/slabinfo | head
```

### 7.6 S06 REBOOT 完整路径

```bash
# Step 1: last_kmsg
unzip -p bugreport.zip kernel/last_kmsg.txt | head -50

# Step 2: dropbox 系统级
unzip -p bugreport.zip FS/data/system/dropbox/ | grep "reboot"

# Step 3: init log
unzip -p bugreport.zip logcat/logcat_system.txt | grep "init:.*Rebooting"
```

### 7.7 S07 KE 完整路径

```bash
# Step 1: dmesg
unzip -p bugreport.zip kernel/dmesg.txt | grep -E "panic|oops|BUG"

# Step 2: last_kmsg
unzip -p bugreport.zip kernel/last_kmsg.txt | head -50

# Step 3: pmsg-ramoops
unzip -p bugreport.zip FS/data/vendor/ramoops/pmsg-ramoops-0 | head

# Step 4: tainted
unzip -p bugreport.zip proc/sys/kernel/tainted
# 非 0 → KE 现场

# Step 5: kallsyms 反查
unzip -p bugreport.zip kernel/kallsyms | grep "<symbol>"
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 Bugreport 总览](01-Bugreport-总览与生成解析.md) | 工具 + 总览 |
| [02 目录结构全梳理](02-Bugreport-目录结构全梳理.md) | 上篇 |
| [04 实战 5 类典型案例](04-Bugreport-实战5类典型案例.md) | 下篇 |
| [05 vs perfetto](05-Bugreport-vs-perfetto-trace.md) | 工具边界 |
| [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../../03-卷3-调查工具/24-Dumpsys · Bugreport · DropBox/12-dumpsys实战SOP.md) | dumpsys 完整 |
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) | perfetto |
| [06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../../03-卷3-调查工具/26-断点与 Native 调试/Logcat_Complete_Guide.md) | logcat 完整 |
| [06-Foundation/SELinux/04-AVC与avc_denied](../../../01-卷1-平台基础与启动/05-安全基础（SELinux · AVB）/SELinux/04-AVC与avc_denied：从一次denied反推策略.md) | denied 解读 |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[04 Bugreport 实战 5 类典型案例](04-Bugreport-实战5类典型案例.md) 讲 5 个真实场景的完整取证流程：
1. ANR 现场（traces.txt + activity dumpsys）
2. NE 现场（tombstone + dropbox）
3. OOM 现场（meminfo + PSI + slabinfo）
4. KE 现场（dmesg + last_kmsg + ramoops）
5. bootloop 现场（last_kmsg + init log + SELinux denied）

### 9.2 看完本文的自检

- [ ] 能用 §6 的 30 grep 命令直接取证
- [ ] 能用 §7 的 7 大症状完整路径
- [ ] 知道每个关键文件的"看 / 不看"
- [ ] 能用 5 类事故对应表秒级定位

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
