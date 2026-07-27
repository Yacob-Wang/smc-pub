# 03-Forensics/Bugreport · 01 · Bugreport 总览与生成/解析

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 现场取证人员
>
> **强依赖**：[06-Foundation/Tools/Tracing](../../06-Foundation/Tools/Tracing/) · [06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 bugreport 这个 oncall 7×24 最高频工具讲清楚——怎么生成、怎么解析、内部结构、5 类现场 5 分钟取证
- **不是**：不复述 logcat 命令（[06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide.md)）；不复述 trace 抓取（[06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南](../../06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto.md)）
- **承接自**：[00-Meta/缺项规划-P0补全路线图 §1.4 缺项清单](../00-Meta/缺项规划-P0补全路线图.md)（bugreport 系列从 0 到 1 新建）
- **衔接去**：[02 目录结构全梳理](02-Bugreport-目录结构全梳理.md) / [06-Case/Cases-Extended/](../06-Case/Cases-Extended/) 实战案例 / [04-Tool/Dumpsys/](../04-Tool/Dumpsys/)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章 5 类 bugreport 工具对比 | oncall 现场 5 秒选对工具 |
| 2 | 第 4 章 5 类现场 5 分钟取证 | 实战 5 步法 |
| 3 | 第 5 章"不要做"的 5 个反模式 | oncall 容易踩雷 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**bugreport = Android 设备的"完整状态快照"——dumpsys + logcat + trace + tombstones 全部打包到一个 .zip，oncall 现场 7×24 第一证据。**

AOSP 17 上 bugreport 包含 **300+ 文件、50-300MB**，覆盖设备所有运行状态。理解它的结构 = 现场 5 分钟从 bugreport 反推 7 大症状的根因。

---

## 1. 5 类 bugreport 工具对比

### 1.1 Android 5 类取现场工具

| 工具 | 何时用 | 大小 | 触发方式 |
|:-----|:-------|:----|:--------|
| `bugreport`（标准）| **90% 现场第一选择** | 100-300MB | `adb bugreport` |
| `bugreportz`（压缩 zip）| 大设备 | 50-150MB | `adb bugreportz`（AOSP 12+）|
| `bugreport+`-incremental | 流式 | 几 MB 起 | AOSP 14+ 实验性 |
| `incident` | 系统级事故 | 几 MB | `incidentd` 自动触发 |
| `dropbox` | crash 历史 | 几 MB | `dumpsys dropbox` |

### 1.2 `bugreport` vs `bugreportz` 关键差异

| 维度 | `bugreport` (AOSP 4-12) | `bugreportz` (AOSP 12+) |
|:-----|:----------------------|:---------------------|
| **输出** | 1 个 .txt（dumpstate 文本）| 1 个 .zip（dumpstate 文本 + 所有附件）|
| **流式** | 否（一次性 dump）| 是（边 dump 边写）|
| **大小** | 100-300 MB（单文件）| 50-150 MB（zip 压缩）|
| **附件** | 嵌在 .txt 里（base64）| zip 内独立文件 |
| **稳定性含义** | 大设备可能 OOM | 流式不 OOM |

**AOSP 17 默认 `bugreportz`**（zip 模式）。

### 1.3 AOSP 17 真实命令

```bash
# 1. 标准 bugreport（zip 模式）
$ adb bugreport /tmp/bugreport.zip
# 等待 30-120 秒
# 输出：/tmp/bugreport.zip

# 2. bugreportz（流式）
$ adb bugreportz /tmp/bugreportz
# 等待 30-120 秒
# 输出：/tmp/bugreportz.zip

# 3. 强制 logcat 全量（默认只 200KB）
$ adb shell bugreport -b ALL

# 4. 指定 incident ID
$ adb shell bugreport --incident 12345
```

### 1.4 5 类现场的工具选择

| 现场 | 第一选择 | 第二选择 | 不用 |
|:-----|:--------|:--------|:----|
| **ANR 现场** | `bugreportz` + `traces.txt` | logcat -b system | bugreport（太慢）|
| **NE 现场** | `bugreport` + tombstone | `dumpsys dropbox` | trace（不必要）|
| **OOM** | `bugreport` + meminfo | `dumpsys meminfo` | trace（耗资源）|
| **KE** | `bugreport` + ramoops | `dmesg` | logcat（漏 kernel）|
| **bootloop** | `bugreport` + last_kmsg | `dmesg` | - |

---

## 2. bugreport 的内部结构（AOSP 17）

### 2.1 zip 顶层结构

```
bugreport.zip
├── version.txt                        # 版本信息
├── main_entry.txt                     # 入口 dumpstate
├── FS/                                # 文件系统 dump
│   ├── data/
│   │   ├── anr/                       # ANR traces.txt
│   │   ├── tombstones/                # NE tombstone_*
│   │   ├── system/dropbox/            # dropbox 系统日志
│   │   ├── vendor/ramoops/            # kernel panic 持久化
│   │   └── ...
│   ├── system/
│   │   ├── etc/selinux/               # SELinux 策略
│   │   ├── build.prop
│   │   └── ...
│   ├── proc/                          # /proc 关键文件
│   │   ├── meminfo
│   │   ├── vmstat
│   │   ├── pressure/
│   │   │   ├── cpu
│   │   │   ├── memory
│   │   │   └── io
│   │   └── ...
│   └── ...
├── dumpsys/                           # 所有 dumpsys 输出
│   ├── dumpsys_*.txt                  # 每个 service 1 个文件
│   │   ├── dumpsys_activity.txt
│   │   ├── dumpsys_window.txt
│   │   ├── dumpsys_meminfo.txt
│   │   ├── dumpsys_battery.txt
│   │   └── ...
├── logcat/                            # logcat 全部 buffer
│   ├── logcat_main.txt
│   ├── logcat_system.txt
│   ├── logcat_events.txt
│   ├── logcat_crash.txt
│   ├── logcat_kernel.txt
│   └── ...
├── traces/                            # systrace / perfetto trace
│   ├── systrace.html
│   ├── perfetto-trace.pb
│   └── ...
├── pkg/                               # 包管理信息
├── proc/                              # /proc 文本
│   ├── version
│   ├── cmdline
│   ├── mounts
│   └── ...
└── kernel/                            # kernel 信息
    ├── dmesg.txt
    ├── last_kmsg.txt
    └── ...
```

**AOSP 17 bugreport 典型大小**：
- 标准 device：100-200MB
- 大 device（> 8GB RAM）：200-500MB
- Pixel 8 / Samsung S24：~150MB

### 2.2 关键文件清单

| 文件 | 用途 | 大小 |
|:-----|:-----|:----|
| `FS/data/anr/traces.txt` | ANR 现场 stack | 几 MB |
| `FS/data/tombstones/tombstone_*` | NE 现场 | 几 MB |
| `dumpsys/dumpsys_activity.txt` | Activity/AMS 状态 | 几 MB |
| `dumpsys/dumpsys_meminfo.txt` | 内存详细 | 几 MB |
| `dumpsys/dumpsys_window.txt` | 窗口/UI 状态 | 几 MB |
| `logcat/logcat_main.txt` | 主 logcat | 1-10MB |
| `logcat/logcat_system.txt` | system logcat | 1-5MB |
| `logcat/logcat_kernel.txt` | kernel logcat | 100KB-1MB |
| `logcat/logcat_crash.txt` | crash logcat | 1-5MB |
| `traces/systrace.html` | systrace 浏览器版 | 几 MB |
| `traces/perfetto-trace.pb` | Perfetto 二进制 | 几 MB |
| `proc/meminfo` | 内存概览 | 几 KB |
| `proc/pressure/*` | PSI 压力 | 几 KB |
| `proc/cmdline` | kernel cmdline | 几 KB |
| `kernel/dmesg.txt` | kernel log | 100KB-1MB |
| `kernel/last_kmsg.txt` | 上次 boot kernel log | 1-10MB |

---

## 3. bugreport 生成时序（AOSP 17）

### 3.1 12 步生成流程

```
[1] adb bugreport 触发
[2] adbd 接收 → 转给 system_server 的 bugreportd
[3] bugreportd fork dumpstate 子进程
[4] dumpstate 写 version.txt
[5] dumpstate 触发 dumpsys 全面
[6] dumpstate 触发 logcat dump
[7] dumpstate 触发 trace dump
[8] dumpstate 触发 proc 文件系统 dump
[9] dumpstate 触发 kernel log dump
[10] dumpstate 触发 FS dump（重要文件）
[11] dumpstate 触发 pkg dump
[12] dumpstate 打 zip 输出
```

**典型耗时**：30-120 秒（依设备性能）

### 3.2 dumpstate 真实代码路径

```
adbd (system/core/adbd)
  ↓
bugreportd (frameworks/base/services/core/java/com/android/server/os/BugreportdService.java)
  ↓
dumpstate (frameworks/native/cmds/dumpstate/dumpstate.cpp)
  ↓
并发触发多个 dump task
  ├─ dumpsys
  ├─ logcat
  ├─ trace
  ├─ proc
  └─ kernel
  ↓
写 zip
```

### 3.3 关键源码锚点

| 路径 | 干什么 |
|:-----|:------|
| `frameworks/native/cmds/dumpstate/dumpstate.cpp` | 核心 dump 工具（C++）|
| `frameworks/base/services/core/java/com/android/server/os/BugreportdService.java` | bugreport 系统服务 |
| `system/core/logd/LogReader.cpp` | logcat 读 |
| `external/perfetto/.../tracing_service_impl.cc` | Perfetto trace |
| `frameworks/base/services/core/java/com/android/server/.../*Service.java` | 每个 service 1 个 dumpsys 实现 |

---

## 4. 5 类现场 5 分钟取证

### 4.1 现场 1：ANR（5 分钟）

```bash
# 1. 看 ANR traces
$ unzip -p bugreport.zip FS/data/anr/traces.txt | head -200

# 2. 找主线程 blocked
$ grep "main thread" FS/data/anr/traces.txt
# 找到 ANR 的栈

# 3. 看 system_server 状态
$ unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "ANR" | head

# 4. 找 input dispatching
$ unzip -p bugreport.zip dumpsys/dumpsys_window.txt | grep "Input"
```

**关键文件优先级**：
1. `FS/data/anr/traces.txt`（ANR 栈，1MB）
2. `logcat/logcat_system.txt` 找 ANR 字样
3. `dumpsys/dumpsys_activity.txt` 找 ANR 列表

### 4.2 现场 2：NE（5 分钟）

```bash
# 1. 看 tombstone
$ unzip -p bugreport.zip FS/data/tombstones/tombstone_01
# 看 backtrace + signal + map

# 2. 看 dropbox
$ unzip -p bugreport.zip FS/data/system/dropbox/ | grep "crash"
# 或直接看 dropbox 列表
$ unzip -p bugreport.zip dumpsys/dumpsys_dropbox.txt | head

# 3. 找前后 logcat
$ unzip -p bugreport.zip logcat/logcat_crash.txt | grep "signal"
```

**关键文件优先级**：
1. `FS/data/tombstones/tombstone_*`
2. `logcat/logcat_crash.txt`
3. `FS/data/system/dropbox/`

### 4.3 现场 3：OOM（5 分钟）

```bash
# 1. 看 meminfo 概览
$ unzip -p bugreport.zip proc/meminfo
# MemTotal / MemFree / MemAvailable

# 2. 看详细 meminfo
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | head -200

# 3. 看 PSI 压力
$ unzip -p bugreport.zip proc/pressure/memory
# some avg10=...  full avg10=...

# 4. 找大进程
$ unzip -p bugreport.zip dumpsys/dumpsys_meminfo.txt | grep "Pss Total" | sort -k3 -n -r | head -10
```

**关键文件优先级**：
1. `proc/meminfo`（概览）
2. `dumpsys/dumpsys_meminfo.txt`（详细）
3. `proc/pressure/memory`（PSI）

### 4.4 现场 4：KE（5 分钟）

```bash
# 1. 看 kernel log
$ unzip -p bugreport.zip kernel/dmesg.txt | tail -200

# 2. 看 last_kmsg（上次 boot）
$ unzip -p bugreport.zip kernel/last_kmsg.txt | head -200

# 3. 看 ramoops
$ unzip -p bugreport.zip FS/data/vendor/ramoops/
# 或
$ unzip -p bugreport.zip dumpsys/dumpsys_kernel.txt | tail
```

**关键文件优先级**：
1. `kernel/dmesg.txt`（当前 boot）
2. `kernel/last_kmsg.txt`（上次 boot）
3. `FS/data/vendor/ramoops/`

### 4.5 现场 5：bootloop（5 分钟）

```bash
# 1. 看 init log
$ unzip -p bugreport.zip logcat/logcat_system.txt | grep "init:" | head -50

# 2. 看 service 启动情况
$ unzip -p bugreport.zip dumpsys/dumpsys_activity.txt | grep "Service" | head

# 3. 看 SELinux denied
$ unzip -p bugreport.zip logcat/logcat_kernel.txt | grep "avc: denied"
```

**关键文件优先级**：
1. `logcat/logcat_system.txt`（init 启动 log）
2. `logcat/logcat_kernel.txt`（denied 风暴）
3. `kernel/dmesg.txt`（kernel panic）

---

## 5. 5 个"不要做"的反模式

### 5.1 反模式 1：不要只 grep 关键字不看上下文

```
错：
$ grep "crash" bugreport.zip
# 输出 1000+ 行匹配，看不出时间顺序

正：
$ unzip bugreport.zip -d /tmp/br
$ vim /tmp/br/logcat/logcat_crash.txt
# vim 里 :set hlsearch + /crash
```

### 5.2 反模式 2：不要直接在生产环境 adb shell

```
错：
$ adb shell "dmesg | grep xxx"   # 可能 OOM

正：
$ adb pull /proc/kmsg /tmp/
$ grep xxx /tmp/kmsg
```

### 5.3 反模式 3：不要在 OOM 设备跑 bugreport

```
错：设备已 OOM → adb bugreport → 再 OOM 一次

正：用 incidentd 触发 / 等设备恢复后再抓
```

### 5.4 反模式 4：不要丢原始 bugreport

```
错：
$ adb bugreport > /dev/null   # 丢原始
# 后续再要 → 已经丢了

正：保存 + 标日期 + 标设备 + 标现场
$ adb bugreport /data/tmp/2026-07-27_crash.zip
$ sync
```

### 5.5 反模式 5：不要只看 dumpsys 不看 logcat

```
错：只看 dumpsys → 不知道"什么时候发生"
正：logcat 给时间线，dumpsys 给当前状态，组合才完整
```

---

## 6. 真实 oncall 工作流（5 步）

```
[1] 接收事故
    - 用户反馈 / 监控告警
    - 抓 5 个维度：what / when / where / who / how

[2] 远程取现场
    - adb bugreport 抓设备
    - 等 30-120 秒
    - 同时抓 logcat -d -b all 保留

[3] 解压 bugreport
    - unzip bugreport.zip -d /tmp/br
    - 看 5 个关键目录：FS/data/anr + tombstones + logcat + dumpsys + kernel

[4] 5 分钟定位（按现场类型选）
    - ANR → traces.txt
    - NE → tombstone
    - OOM → meminfo + PSI
    - KE → dmesg + last_kmsg
    - bootloop → init log + denied

[5] 出报告 + 提 fix
    - 写 5 行：症状 / 现场 / 根因 / fix / 预防
    - commit 修复代码
    - 加监控 / 门禁
```

---

## 7. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [02 目录结构全梳理](02-Bugreport-目录结构全梳理.md) | 下篇 |
| [06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide](../../06-Foundation/Tools/Android_Tools/Logcat_Complete_Guide.md) | logcat 完整语法 |
| [06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南](../../06-Foundation/Tools/Tracing/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto.md) | trace 抓取 |
| [04-Tool/Dumpsys/12-dumpsys实战SOP](../../../04-Tool/Dumpsys/12-dumpsys实战SOP.md) | dumpsys 实战 |
| [04-Tool/AmCommand/01-am命令全景与Activity触发](../../../04-Tool/AmCommand/01-am命令全景与Activity触发.md) | am + bugreport 联动 |
| [04-Tool/Hprof/01-Hprof总览](../../../04-Tool/Hprof/) | 内存泄漏取证 |
| [06-Case/Cases-Extended/](../../../06-Case/Cases-Extended/) | 实战案例 |
| [02-Symptom/S00-S09 7 大症状](../../02-Symptom/) | 7 大症状 |
| [03-Forensics/F00-F07 7 大取证](../../03-Forensics/) | 取证总览 |

---

## 8. 下一篇预告 + 自检

### 8.1 下一篇

[02 Bugreport 目录结构全梳理](02-Bugreport-目录结构全梳理.md) 讲清：
- bugreport.zip 内 50+ 关键文件的逐一用途
- 5 大子目录（FS / dumpsys / logcat / traces / proc / kernel）的完整树
- 每个文件的"看什么 / 不看什么"
- 8 类常见事故的"看哪个文件"对照表

### 8.2 看完本文的自检

- [ ] 能说 5 类 bugreport 工具的差异
- [ ] 能说 AOSP 17 bugreport.zip 顶层 6 大子目录
- [ ] 能从 1 个 bugreport.zip 5 分钟定位 5 类现场
- [ ] 知道 5 个反模式
- [ ] 能用 6 步 oncall 工作流处理事故

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
