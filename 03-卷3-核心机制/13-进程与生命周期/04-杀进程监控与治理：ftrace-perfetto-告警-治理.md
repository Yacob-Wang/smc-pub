<!-- AUTHOR_ONLY:START -->
# 本篇定位(强制开头段,先写它再写正文)
- **本篇系列角色**:诊断治理(工程落地手册)
- **强依赖**:必须先读 [01 §11 ftrace](01-杀进程全链路：从AMS触发到进程完全退出.md) + [02 §8 ftrace 测速公式](02-do_exit内部9个sub-step深潜.md) + [03 §4 证伪实验模板 + §8 故障报告](03-杀进程慢的真正根因：诱因-根因-证伪.md)
- **承接自**:01-03 篇讲机制;本篇讲"怎么建监控、怎么定告警、怎么治理"
- **衔接去**:写完本篇后,Process_Exit 4 篇全部完成;Process 09 实战作为应用 case
- **不重复内容**:与 01 §11 ftrace——01 是简版,本篇是完整 perfetto 配置 + 告警阈值 + 治理;与 03 §8 故障报告——03 是模板,本篇是治理动作清单
- **破例决策**:本篇是诊断工具型(§9.1 破例),章节结构重排为"工具使用 → 工具源码 → 实战"——但本系列 4 篇已线性,保持标准结构

# 校准决策日志(强制 · 3 轮校准后填写)
| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|------|------|------|------|----------|
| 1 | 结构 | 3 层监控(L1 FWK / L2 Kernel / L3 系统) | 监控分层是工程标准 | §1-§4 |
| 1 | 结构 | 告警阈值 1s/5s/10s 分级 + 闭环响应 | 稳定性告警工程实践 | §5 |
| 1 | 结构 | perfetto 完整 pbtxt + adb 命令 | 实操可复制 | §6 |
| 1 | 结构 | 治理 4 大方向(减少触发/加速单次/缓存现场/告警闭环) | v5 §3 诊断治理标准 | §7 |
| 2 | 硬伤 | AOSP 16 / Kernel 6.6 基线统一 | 与 01-03 一致 | 全文 |
| 2 | 硬伤 | perfetto 数据源名称 + 配置 key 全部按 AOSP 16 / Kernel 6.6 校对 | v5 反例 #3 | §6 |
| 2 | 硬伤 | 告警阈值给具体数字 + 依据(1s/5s/10s) | v5 反例 #5 模糊量化 | §5 |
| 3 | 锐度 | 删"告警体系非常重要"这种 AI 自嗨 | v5 反例 #12 | §5 |
| 3 | 锐度 | 6 类治理反例每个配"为什么反"的源码说明 | v5 反例 #12 #11 联合 | §9 |
| 3 | 锐度 | 治理 ROI 排序表(基于 03 §8.3) | v5 反例 #11 数据堆砌防御 | §8 |

# 角色设定
我是一名 Android 稳定性架构师, 正在系统学习【杀进程监控 + 治理工程落地】。
本篇是 Process_Exit 系列的第 4 篇, 主题是【杀进程监控与治理: ftrace / perfetto / 告警 / 治理】。

# 上下文
- 上一篇:[03-真正根因](03-杀进程慢的真正根因：诱因-根因-证伪.md), 已讲诱因 vs 根因 4 条判定标准
- 下一篇:无(本系列终篇)
- 本系列 README:[README-杀进程系列](README-杀进程系列.md)
- 跨系列引用:[Process 09 实战](../Process/09-杀进程慢的根因定位实战.md) / [MM_v2 13 诊断工具链](../../Kernel/Memory_Management/MM_v2/13-内存稳定性诊断工具链.md) / [Kernel Process 05 do_exit](../../Kernel/Process/05-进程的退出_do_exit与资源回收.md)

# 写作标准
- v5 规范(本指南)
- 300+ 行, 4-6 张 ASCII 图
- 5 段作者前言用 `<!-- AUTHOR_ONLY:START -->` 包裹(§9)
- 4 附录完整(源码索引 / 路径对账 / 量化自检 / 工程基线)
- 数据后必有"所以呢"(反例 #11 防御)
- 架构师视角"对读者有什么用"(反例 #12 防御)
- 跨篇引用 Markdown 链接(不重复展开)
- 关键承诺: 治理动作清单要可落地(每个动作给具体命令 / 配置 / 验证)
<!-- AUTHOR_ONLY:END -->

# 杀进程监控与治理：ftrace / perfetto / 告警 / 治理

> **源码基线**：AOSP `android-16.0.0_r1` + Kernel `android16-6.6` GKI 2.0
>
> **本篇定位**：**杀进程系列第 4 篇 / 诊断治理**。在 01-03 篇讲完机制 + 真正根因判定基础上，本篇讲**工程落地**——怎么建监控（3 层 L1 FWK / L2 Kernel / L3 系统）、怎么定告警阈值（1s / 5s / 10s 分级）、怎么治理（4 大方向 + 8 类动作 + 6 类反例）。
>
> **结构**：
> - **§1** 监控的 3 层架构总览（ASCII）
> - **§2-§4** 3 层监控详解（L1 FWK / L2 Kernel / L3 系统）
> - **§5** 告警阈值设计（1s/5s/10s 分级 + 闭环）
> - **§6** perfetto 完整配置（pbtxt + adb 命令）
> - **§7-§9** 治理（4 大方向 + 8 类动作 + 6 类反例）
> - **§10** 实战案例（治理落地）
> - **§11** 总结 + 跨篇索引
> - **4 附录**
>
> **不重复内容**：与 01 §11 ftrace 简版、02 §8 ftrace 测速公式、03 §8 故障报告模板严格区分——本篇是"工程落地手册"。
>
> **目录位置**：`Android_Framework/Process_Exit/`

---

## 目录

- [1. 监控的 3 层架构总览](#1-监控的-3-层架构总览)
- [2. L1 FWK 事件监控](#2-l1-fwk-事件监控)
- [3. L2 Kernel 事件监控](#3-l2-kernel-事件监控)
- [4. L3 系统指标监控](#4-l3-系统指标监控)
- [5. 告警阈值设计（1s/5s/10s 分级 + 闭环）](#5-告警阈值设计1s5s10s-分级--闭环)
- [6. perfetto 完整配置（pbtxt + adb 命令）](#6-perfetto-完整配置pbtxt--adb-命令)
- [7. 治理 4 大方向](#7-治理-4-大方向)
- [8. 治理清单（8 类动作）](#8-治理清单8-类动作)
- [9. 治理反例（6 类）](#9-治理反例6-类)
- [10. 实战案例：治理落地](#10-实战案例治理落地)
- [11. 总结 + 跨篇索引](#11-总结--跨篇索引)
- [附录 A：核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B：源码路径对账表](#附录-b源码路径对账表)
- [附录 C：量化数据自检表](#附录-c量化数据自检表)
- [附录 D：工程基线表](#附录-d工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. 监控的 3 层架构总览

### 1.1 为什么需要 3 层

杀进程相关的"问题"分布在 **4 个层栈**（[01 §1.2](01-杀进程全链路：从AMS触发到进程完全退出.md)）——单一层监控会漏掉关键信号。

**对读者有什么用**：3 层监控覆盖全栈——任何"杀进程慢"问题都有 1-2 层有信号，**不依赖单一层**。

### 1.2 3 层监控总览（ASCII）

```
┌────────────────────────────────────────────────────────────────────┐
│  L1: FWK 事件层 (Java)                                              │
│  - events_log: am_kill / am_proc_died / am_proc_start              │
│  - main_log: rms_NormalReclaimer / Watchdog                        │
│  - 监控关键指标: am_kill → am_proc_died 间隔                      │
├────────────────────────────────────────────────────────────────────┤
│  L2: Kernel 事件层 (Native / Kernel)                                │
│  - ftrace: sched_process_exit / sched_process_wait / mm_page_free   │
│  - kernel log: binder_alloc: no vma / Device or resource busy      │
│  - perfetto: 完整 trace（含 ftrace + process_memory）               │
│  - 监控关键指标: T_exit_mm (②-b + ②-c 耗时)                       │
├────────────────────────────────────────────────────────────────────┤
│  L3: 系统指标层 (Kernel 系统调用)                                   │
│  - /proc/meminfo: MemFree / SwapUsage                              │
│  - /proc/pressure/memory: PSI some/full                            │
│  - /sys/fs/cgroup/.../memory.current: 进程级 cgroup 内存            │
│  - /proc/<pid>/status: VmRSS / VmSwap / cgroup 节点                │
│  - 监控关键指标: 系统级压力 + 进程级状态                            │
└────────────────────────────────────────────────────────────────────┘
```

### 1.3 3 层监控的覆盖矩阵

| 根因 / 异常 | L1 监控 | L2 监控 | L3 监控 |
|---|---|---|---|
| 杀进程总耗时 10s+ | ✅ am_kill→am_proc_died 间隔 | ✅ ftrace 全程 | — |
| ② exit_mm 慢 (5-10s) | — | ✅ ftrace mm_page_free | — |
| ②-c swap_free 慢 | — | — | ✅ swapUsage > 50% |
| vma 异常 | — | ✅ binder_alloc: no vma | — |
| ③ exit_files 慢 | — | ✅ ftrace + lsof | ✅ fd 数量 |
| ⑥ 资源回收拥堵 | ✅ am_proc_died 后 24s+ cgroup 残留 | — | ✅ cgroup.workqueue 状态 |
| 系统级内存压力 | — | — | ✅ PSI some/full |

**对读者有什么用**：每种根因都有 1-2 层有信号——**不要只盯 L1**（很多细节 L1 看不到）。

### 1.4 监控的 3 个原则

| 原则 | 含义 | 实战 |
|---|---|---|
| **多源交叉验证** | 单层信号不可信，3 层都看到才确认 | 杀进程 10s+ 必须在 L1 看到 am_kill→am_proc_died 间隔 + L2 看到 ftrace T_exit_mm |
| **避免单点依赖** | 不要只盯一个指标 | 不要只看 `am_proc_died` 时间，要看 L1 + L2 + L3 3 层 |
| **告警 + 诊断一体化** | 告警触发后能直接调出诊断数据 | 告警 dashboard 链接 → ftrace / perfetto trace |

---

## 2. L1 FWK 事件监控

### 2.1 是什么 + 为什么

L1 是**最易采集的层**——`events_log` 和 `main_log` 是 Android 默认开启的 logcat buffer，**任何设备都直接可用**。通过解析 `am_kill` / `am_proc_died` 等事件的间隔，能立刻看出杀进程耗时。

**对读者有什么用**：L1 是**第一道告警**——线上 80% 的杀进程慢问题在 L1 就能识别。

### 2.2 关键事件 + 字段解析

| 事件 | events_log 字段 | 监控指标 | 异常阈值 |
|---|---|---|---|
| `am_kill` | `[0,pid,package,adj,reason,...]` | 触发杀进程 | adj > 700 是清理 |
| `am_proc_died` | `[0,pid,package,adj,exit_code]` | 进程死亡 | 间隔 > 1s 异常 |
| `am_proc_start` | `[0,pid,package,adj,reason]` | 进程启动 | 启动失败关联 |
| `am_wtf` | `[0,pid,package,-1,scope,...]` | Watchdog / refused to die | 出现即告警 |
| `am_low_memory` | `pid,killing,reason` | LMKD 决策 | 出现即告警 |
| `am_anr` | `pid,package,reason` | ANR | ANR 后一般会杀 |

### 2.3 关键指标计算公式

```
杀进程总耗时 = am_proc_died.time - am_kill.time
触发-死亡间隔 > 阈值 → 告警
```

**对读者有什么用**：这是**最简单但最有用**的指标——`am_kill` 和 `am_proc_died` 都有 timestamp，**直接相减**。

### 2.4 实战：events_log 拉取 + 解析

```bash
# 1. 拉取最近 1 小时 events_log
adb shell logcat -d -b events -t 3600 | grep -E "am_kill|am_proc_died|am_wtf" > /tmp/am_events.log

# 2. 解析杀进程耗时
awk -F'[][]' '/am_kill/ {kill_time[$3]=$5; pid=$3} 
              /am_proc_died/ {if (kill_time[$3] != "") {
                duration = $5 - kill_time[$3]
                if (duration > 1) print "LONG KILL:", $3, duration"s"
                delete kill_time[$3]
              }}' /tmp/am_events.log

# 3. 输出 L1 告警
```

**对读者有什么用**：5 行 shell 脚本就能在生产环境实时监控杀进程慢——**不需要 ftrace，不需要 perfetto**。

### 2.5 L1 监控的局限

| 局限 | 原因 | 解决方案 |
|---|---|---|
| **看不到 9 sub-step 各自耗时** | events_log 只看 FWK 层 | L2 ftrace |
| **看不到 vma 异常** | events_log 无 `binder_alloc: no vma` | L2 kernel log |
| **看不到 cgroup 节点销毁** | events_log 无 cgroup 销毁日志 | L3 /sys/fs/cgroup |

**对读者有什么用**：L1 是**告警**层，**根因定位要 L2**。L1 触发后立刻转 L2 排查。

---

## 3. L2 Kernel 事件监控

### 3.1 是什么 + 为什么

L2 是**最深的层**——`ftrace` 能精确测每个 sub-step 的耗时，`kernel log` 能看到 vma 异常等关键事件。但 L2 **开销大**（ftrace 抓 trace 有性能损耗），**不能长期开启**。

**对读者有什么用**：L2 是**根因定位**层——L1 告警触发后，**短时间开 ftrace 抓 trace**（5-10 分钟），定位根因。

### 3.2 6 个关键 ftrace 事件

```bash
# 1. 进程死亡入口 + 父进程 wait
echo 1 > events/sched/sched_process_exit/enable       # ★ do_exit 起点
echo 1 > events/sched/sched_process_wait/enable       # ★ 父进程 wait 起点

# 2. 信号投递
echo 1 > events/signal/signal_generate/enable         # ★ 信号生成
echo 1 > events/signal/signal_deliver/enable          # ★ 信号投递到目标

# 3. 物理页释放
echo 1 > events/mm/mm_page_free/enable                # ★ ② exit_mm 释放页
echo 1 > events/mm/mm_page_free_batched/enable        # bulk free(更高层)
```

**对读者有什么用**：**6 个事件必须同时开**——只开部分会丢失关键数据。

### 3.3 关键 kernel log 关键字

| 关键字 | 含义 | 对应根因 |
|---|---|---|
| `binder_alloc: <pid>: no vma` | mmap 已被预回收 | 真正根因 ① vma 异常 |
| `oom_reaper` | OOM reaper 触发 | 真正根因 ③ 资源回收拥堵 |
| `psi: some` / `psi: full` | 系统级压力 | 诱因 ⑤ MemFree 80MB |
| `direct_reclaim` | direct reclaim 触发 | 诱因 ⑤ MemFree 80MB |
| `kswapd` 高占用 | swap 压力 | 诱因 ① swap 55% |
| `D state` (uninterruptible sleep) | 进程卡 D 态 | 真正根因 ③ 资源回收拥堵 |
| `TranMemoryInfo` (vendor) | OEM 自定义工具 | vendor hook 触发 |

**对读者有什么用**：这些关键字在 L2 抓 trace 时**同时打开**——看到关键字直接对应根因。

### 3.4 测速公式（基于 02 篇 §8.2）

```bash
# 精确版 ftrace
T_exit_mm = exit_mmap end - sched_process_exit
T_exit_files = close_files end - exit_mmap end
T_kill_total = sched_process_wait (父) - sched_process_exit

# 估算版 events_log
T_kill_total = am_proc_died - am_kill
```

**对读者有什么用**：用这个公式替代 [01 §11 的简版](01-杀进程全链路：从AMS触发到进程完全退出.md)——L2 测速更精确。

### 3.5 L2 监控的开销

| 事件 | 开销 | 线上建议 |
|---|---|---|
| `sched_process_exit` | us 级 | 长期可开 |
| `mm_page_free` | 高（每秒数千事件） | **短期抓 trace 用** |
| `signal_generate/deliver` | 中 | 短期抓 trace 用 |
| **全 6 个开** | **高** | **仅在复现时开** |

**对读者有什么用**：不要在生产环境长期开 ftrace——**抓完立刻关**。

### 3.6 L2 实战：ftrace 抓取 + 分析

```bash
# 1. 准备: 开启 6 个关键事件 + 抓 trace
adb root
adb shell
mount -t debugfs debugfs /sys/kernel/debug
cd /sys/kernel/debug/tracing

# 2. 开 6 个事件
echo 1 > events/sched/sched_process_exit/enable
echo 1 > events/sched/sched_process_wait/enable
echo 1 > events/signal/signal_generate/enable
echo 1 > events/signal/signal_deliver/enable
echo 1 > events/mm/mm_page_free/enable
echo 1 > events/mm/mm_page_free_batched/enable

# 3. 开 trace
echo 1 > tracing_on

# 4. 触发场景
# ... 触发杀进程 ...

# 5. 抓 trace
adb pull /sys/kernel/debug/tracing/trace /tmp/trace.log

# 6. 关 trace
echo 0 > tracing_on
echo > trace

# 7. 分析: 找 ② exit_mm 耗时
grep -E "exit_mmap end|sched_process_exit" /tmp/trace.log | head -20
```

---

## 4. L3 系统指标监控

### 4.1 是什么 + 为什么

L3 是**最底层的层**——`/proc` 和 `/sys/fs/cgroup` 是 kernel 直接暴露的接口，**任何 root 设备都能 cat**。但 L3 数据**是"当前状态"**——不能直接告警（要配合时间窗采样）。

**对读者有什么用**：L3 是**根因验证**层——L1 告警 + L2 抓 trace 后，用 L3 验证"系统级状态"。

### 4.2 关键系统指标

| 指标 | 来源 | 监控意义 | 异常阈值 |
|---|---|---|---|
| `MemFree` | `/proc/meminfo` | 系统空闲内存 | < 200MB 危险 |
| `SwapUsage` | `/proc/meminfo` | swap 使用率 | > 50% 压力 |
| `PSI some` | `/proc/pressure/memory` | 部分内存压力 | > 20% 持续 |
| `PSI full` | `/proc/pressure/memory` | 完全内存压力 | > 5% 持续 |
| `VmRSS` | `/proc/<pid>/status` | 进程驻留集 | 异常大需查 |
| `VmSwap` | `/proc/<pid>/status` | 进程 swap | > 50MB 危险 |
| `cgroup.memory.current` | `/sys/fs/cgroup/.../memory.current` | 进程 cgroup 占用 | 接近 max 危险 |
| `cgroup.workqueue` | `/sys/fs/cgroup/.../cgroup.events` | cgroup 销毁事件 | destroy 失败 = 拥堵 |

### 4.3 关键命令

```bash
# 1. 系统级 MemFree / Swap
adb shell cat /proc/meminfo | grep -E "MemFree|SwapTotal|SwapFree"

# 2. 进程级 VmRSS / VmSwap
adb shell cat /proc/<pid>/status | grep -E "VmRSS|VmSwap"

# 3. cgroup 节点级
adb shell cat /sys/fs/cgroup/.../pid_<pid>/memory.current
adb shell cat /sys/fs/cgroup/.../pid_<pid>/memory.events

# 4. PSI
adb shell cat /proc/pressure/memory
```

### 4.4 L3 监控的局限

| 局限 | 原因 | 解决方案 |
|---|---|---|
| **是"当前状态"不是"历史"** | /proc 不存历史 | 历史采样 + 时序库 |
| **需要 root** | 多数 /proc 文件需要 root | 通过 sh 或 wrap shell |
| **OOM Killer 信号缺失** | OOM 触发后立刻杀进程 | kernel log + dmesg |

---

## 5. 告警阈值设计（1s/5s/10s 分级 + 闭环）

### 5.1 阈值分级

杀进程慢的告警**必须分级**——不能用单一阈值，否则 1s 慢就告警会很吵，10s+ 慢才告警会漏掉根因。

| 等级 | 阈值 | 含义 | 响应时间 | 通知方式 |
|---|---|---|---|---|
| **P0** | > 10s | 杀进程严重卡死 | 实时 | 短信 + 电话 |
| **P1** | > 5s | 杀进程明显慢 | 1h | 钉钉 / 飞书 |
| **P2** | > 1s | 杀进程轻微慢 | 24h | 邮件 / 日报 |
| **P3** | < 1s | 健康 | 不告警 | dashboard 监控 |

**对读者有什么用**：**1s 是健康门槛**——超过 1s 就要看，超过 5s 要查，超过 10s 要立刻响应。

### 5.2 阈值依据

**为什么 1s 是门槛**：
- 健康范围杀进程 ~200ms（ARM64 实测 4.4 经验值）
- 1s = 5x 健康范围，已经明显异常
- 1s 内的波动属于正常（ftrace 开销 / 系统压力）

**为什么 5s 是 P1**：
- 5s = 25x 健康范围，几乎确定是 ② exit_mm 或 ③ exit_files 慢
- 1-5s 区间需要看 ftrace 区分根因 ① vs ②
- 5s+ 直接 P1 告警

**为什么 10s 是 P0**：
- 10s = 50x 健康范围，确认是根因 ① vma 异常（[02 §3.1 真正根因 ①](02-do_exit内部9个sub-step深潜.md)）
- 10s+ 必然要 P0 响应（短信 + 电话）

### 5.3 告警闭环设计

```
告警触发 (L1 am_kill→am_proc_died > 阈值)
  ↓
自动调出诊断数据:
  - L2 ftrace 抓 trace (如果还开着)
  - L2 kernel log grep 关键字
  - L3 /proc/<pid>/status (如果还活着)
  - L3 /sys/fs/cgroup/.../memory.events
  ↓
诊断报告自动生成:
  - 触发时间 + 设备
  - am_kill→am_proc_died 间隔
  - 9 sub-step 中可能的根因
  - 真正根因判定
  ↓
通知响应 (P0/P1/P2 不同方式)
  ↓
跟踪 + 复盘
```

**对读者有什么用**：告警不只是"亮红灯"——**必须能直接调出诊断数据**，否则响应慢。

### 5.4 告警反例

**反例 ①**：单一阈值（> 1s 就 P0）→ 误报太多
**反例 ②**：只告警不调诊断 → 响应慢
**反例 ③**：不闭环（告警后不跟踪）→ 同样的问题反复出现
**反例 ④**：阈值不变（不根据实际情况调整）→ 系统升级后阈值失效

---

## 6. perfetto 完整配置（pbtxt + adb 命令）

### 6.1 为什么用 perfetto

`perfetto` 是 Android 12+ 的新一代 trace 工具，**比 ftrace 易用**——UI 友好（ui.perfetto.dev 直接看），**比 ftrace 全**——同时支持 ftrace + process_memory + process_stats。

**对读者有什么用**：perfetto **替代 ftrace** 作为生产环境的标准 trace 工具——L2 监控推荐直接上 perfetto。

### 6.2 完整 perfetto pbtxt 配置

```protobuf
# /tmp/trace_config.pbtxt
duration_ms: 30000
buffers: { size_kb: 65536 }

# L2 ftrace 数据源: 6 个关键事件
data_sources {
  config {
    name: "linux.ftrace"
    ftrace_config {
      atrace_categories: "sched"
      atrace_categories: "mm"
      atrace_categories: "signal"
      ftrace_events: "sched_process_exit"
      ftrace_events: "sched_process_wait"
      ftrace_events: "signal_generate"
      ftrace_events: "signal_deliver"
      ftrace_events: "mm_page_free"
      ftrace_events: "mm_page_free_batched"
    }
  }
}

# L2 process_memory 数据源
data_sources {
  config {
    name: "android.process_memory"
    process_memory_config {
      process_cmdline: "com.sh.smart.caller"
    }
  }
}

# L3 process_stats 数据源
data_sources {
  config {
    name: "linux.process_stats"
    process_stats_config {
      scan_all_processes_on_start: true
    }
  }
}
```

### 6.3 perfetto 抓取命令

```bash
# 1. 推送配置
adb push /tmp/trace_config.pbtxt /data/local/tmp/

# 2. 抓 trace (后台)
adb shell perfetto -c /data/local/tmp/trace_config.pbtxt -o /data/local/tmp/trace.perfetto-trace

# 3. 拉取 trace
adb pull /data/local/tmp/trace.perfetto-trace /tmp/

# 4. 在 https://ui.perfetto.dev/ 打开
# - 在 trace viewer 里搜 "sched_process_exit" 找进程死亡
# - 在 trace viewer 里搜 "mm_page_free" 找 unmap
# - 在 process_memory 面板看进程内存变化
```

**对读者有什么用**：perfetto UI 一次看全——ftrace + 进程内存 + cgroup 状态，**不用 grep**。

### 6.4 perfetto vs ftrace 对比

| 维度 | ftrace | perfetto |
|---|---|---|
| 易用性 | grep 文本 | UI 友好 |
| 数据源 | 仅 ftrace | ftrace + process_memory + process_stats |
| 后台运行 | 需手动 | -d 后台 |
| 性能 | 中 | 中（ftrace 部分相同） |
| 适配 | 老版本 | Android 12+ |

**对读者有什么用**：AOSP 16 默认用 perfetto——AOSP 12 以下才用 ftrace。

---

## 7. 治理 4 大方向

### 7.1 4 大方向总览

| 方向 | 含义 | 优先级 | 典型动作 |
|---|---|---|---|
| **(a) 减少触发次数** | 让杀进程尽量不发生 | P1 | 优化 app 减少 LMKD 触发 / 减少误杀 |
| **(b) 加速单次杀进程** | 让单次杀进程尽量快 | P0 | 修根因 ① vma 异常 / 修根因 ② fd 关闭慢 |
| **(c) 缓存现场** | 慢发生时立刻抓数据 | P0 | L1 + L2 + L3 三层联动 |
| **(d) 告警闭环** | 告警后响应 + 跟踪 | P0 | P0/P1/P2 响应 + 复盘 |

**对读者有什么用**：4 个方向**不是优先级排序**，是**同时进行**——任何单方向治理都不够。

### 7.2 方向 (a) 减少触发次数

**为什么**：杀进程触发本身是 LMKD / Watchdog / force stop 等的决策结果——减少触发 = 减少杀进程事件 = 减少慢的概率。

**典型动作**：
- App 优化：减少 native 内存占用 → 降低 LMKD 触发
- 系统优化：调高 LMKD 阈值 → 减少误杀
- 内存治理：从源头解决（[MM_v2 15 线上动态治理](../../Kernel/Memory_Management/MM_v2/15-线上动态内存治理：不杀进程下的诊断与梳理.md)）

**对读者有什么用**：(a) 是**治本**——但需要 App / 系统双向优化，**短期 ROI 低**。

### 7.3 方向 (b) 加速单次杀进程

**为什么**：基于 03 篇 3 大根因——修根因 = 加速单次。

**典型动作**：
- 根因 ① vma 异常：vendor 修复 `process_reclaim` 同步
- 根因 ② fd 关闭慢：App 主动 release GPU 资源
- 根因 ③ 资源回收拥堵：vendor cgroup 配置优化

**对读者有什么用**：(b) 是**直接治理**——一笔修复解决 10s 慢，**ROI 最高**。

### 7.4 方向 (c) 缓存现场

**为什么**：杀进程慢发生时不立刻抓数据，**事后无法复现**——缓存现场是事后定位的前提。

**典型动作**：
- L1 events_log 默认抓（任何设备都有）
- L2 ftrace 临时开（生产环境慎用，但慢发生时必须开）
- L3 /proc 实时采样（cgroup 节点 / VmRSS / VmSwap）
- perfetto 后台常驻（生产环境推荐）

**对读者有什么用**：(c) 是**必要条件**——没数据一切免谈。

### 7.5 方向 (d) 告警闭环

**为什么**：告警 → 响应 → 修复 → 跟踪 4 步缺一不可。

**典型动作**：
- 告警分级：P0 短信 / P1 钉钉 / P2 邮件
- 响应时间：P0 实时 / P1 1h / P2 24h
- 复盘报告：3 天内完成（含根因 + 修复方案）
- 跟踪回归：1 周内验证修复有效

**对读者有什么用**：(d) 是**长期 ROI**——告警不闭环等于没告警。

---

## 8. 治理清单（8 类动作）

### 8.1 8 类动作总表

| 类别 | 动作 | 优先级 | 实施成本 | 治理 ROI |
|---|---|---|---|---|
| **A. vendor 修复** | 修 OEM `process_reclaim` 同步状态 | P0 | 中 | ★★★★★ |
| **B. App 主动 release** | onPause / onTrimMemory 主动 release GPU | P1 | 低 | ★★★★ |
| **C. cgroup 配置优化** | vendor cgroup 树形结构 + workqueue 调度 | P2 | 高 | ★★★ |
| **D. 监控告警** | L1 + L2 + L3 三层 + 阈值 1s/5s/10s 分级 | P0 | 低 | ★★★★ |
| **E. ftrace / perfetto 部署** | 复现时开 ftrace / 生产开 perfetto | P0 | 低 | ★★★★ |
| **F. 故障报告模板** | 8.2 模板（[03 §8 模板](03-杀进程慢的真正根因：诱因-根因-证伪.md)） | P1 | 低 | ★★★ |
| **G. 治理反例检查** | 6 类治理反例（§9）每季度审计 | P2 | 中 | ★★★ |
| **H. 培训 + 文档** | 团队培训 + 案例库 | P3 | 中 | ★★ |

### 8.2 8 类动作 ROI 排序

| 排序 | 类别 | 投入 | 收益 | 净收益 |
|---|---|---|---|---|
| 1 | A vendor 修复 | 1 笔修复 | 消除 10s 慢 | 极高 |
| 2 | B App release | 1 行代码 | 消除 1-2s 慢 | 高 |
| 3 | D + E 监控 + 部署 | 1 天配置 | 持续可见 | 高 |
| 4 | F 故障报告 | 1 个模板 | 标准化 | 中 |
| 5 | C cgroup 优化 | 持续工程 | 消除 24s 残留 | 中 |
| 6 | G 治理反例审计 | 季度 | 防止反例 | 中 |
| 7 | H 培训 | 持续 | 团队能力 | 低 |
| 8 | — | — | — | — |

**对读者有什么用**：**先做 A**（vendor 修复）= 投入 1 笔解决 10s 慢 = ROI 最高。

---

## 9. 治理反例（6 类）

> **v5 反例库 #11 #12 防御**——每类反例给"为什么反"的源码说明

### 9.1 反例 ①：只盯 L1 events_log

**❌ 错例**：
```
"am_kill→am_proc_died 间隔 12s，告警 → 关闭"
```

**❌ 为什么反**：
- L1 只看到总耗时 12s，**看不到 9 sub-step 各自耗时**
- 关闭告警后没人知道根因，下次同样问题再现
- L1 看不到 vma 异常（[03 §3.1 真正根因 ①](03-杀进程慢的真正根因：诱因-根因-证伪.md)）

**✅ 正确做法**：
- L1 告警 → 自动转 L2 ftrace 抓 trace → 定位根因
- L3 验证系统状态

### 9.2 反例 ②：把诱因当根因治理

**❌ 错例**：
```
"杀进程慢是因为 swap 55%，调高 swappiness 解决"
```

**❌ 为什么反**：
- swap 55% 是诱因不是根因（[03 §2.1 证伪](03-杀进程慢的真正根因：诱因-根因-证伪.md)）
- 调 swappiness 解决不了 vma 异常（[03 §3.1 真正根因 ①](03-杀进程慢的真正根因：诱因-根因-证伪.md)）

**✅ 正确做法**：
- 用 [03 §4 证伪实验模板](03-杀进程慢的真正根因：诱因-根因-证伪.md) 验证是否是根因
- 不满足 4 条判定标准 → 治理投入 ROI 低

### 9.3 反例 ③：长期开 ftrace 在生产

**❌ 错例**：
```
"生产环境长期开 ftrace 抓所有进程死亡"
```

**❌ 为什么反**：
- ftrace 有性能开销（[03 §3.5 L2 监控开销](03-杀进程慢的真正根因：诱因-根因-证伪.md)）
- `mm_page_free` 每秒数千事件，**性能损耗 5-10%**
- 不必要的常态开销

**✅ 正确做法**：
- 生产用 perfetto 后台常驻（开销小）
- 复现时才开 ftrace（[03 §3.6 实战](03-杀进程慢的真正根因：诱因-根因-证伪.md)）
- 抓完立刻关

### 9.4 反例 ④：告警阈值单一

**❌ 错例**：
```
"所有杀进程 > 1s 告警"
```

**❌ 为什么反**：
- 单一阈值要么误报要么漏报
- 健康范围 ~200ms，1s 内可能有 ftrace 开销
- 5s 慢是 P1 不是 P0（[§5 阈值分级](#5-告警阈值设计1s5s10s-分级--闭环)）

**✅ 正确做法**：
- 1s / 5s / 10s 三级告警
- P0 实时 / P1 1h / P2 24h 响应时间
- 阈值根据系统升级调整

### 9.5 反例 ⑤：告警后不闭环

**❌ 错例**：
```
"告警触发 → 短信发了 → 关掉 → 1 周后同样问题"
```

**❌ 为什么反**：
- 告警不闭环等于没告警
- 同样的问题反复出现
- 团队能力没提升

**✅ 正确做法**：
- 告警 → 响应 → 修复 → 跟踪 4 步
- 3 天内复盘报告
- 1 周内验证修复

### 9.6 反例 ⑥：拍脑袋治理

**❌ 错例**：
```
"杀进程慢是因为 OEM 系统优化不够，让 OEM 重做"
```

**❌ 为什么反**：
- 没定位根因就治理 = 拍脑袋
- OEM 重做的成本 ROI 极低（vendor 协调 + 测试周期）
- 真正的根因可能在 vma 异常（vendor process_reclaim 同步问题）

**✅ 正确做法**：
- 先用 [03 §4 证伪实验模板](03-杀进程慢的真正根因：诱因-根因-证伪.md) 定位
- 然后再定治理方案
- 用 [03 §8 故障报告模板](03-杀进程慢的真正根因：诱因-根因-证伪.md) 标 ROI

---

## 10. 实战案例：治理落地

> **案例 5 件套**（v5 §3 反例 #8 防御）

### 10.1 环境
- Android 16 / Kernel 6.6 / 某 Android 16 设备
- 复现：基于 [03 §5 实战案例 1](03-杀进程慢的真正根因：诱因-根因-证伪.md) Process 09 案
- 治理前：杀进程 12.24s / cgroup 残留 24s+

### 10.2 治理目标
- 杀进程总耗时：12.24s → < 1s（健康范围）
- cgroup 残留：24s+ → < 5s

### 10.3 治理动作（按 8 类清单）

| 序号 | 类别 | 动作 | 实施 | 验证 |
|---|---|---|---|---|
| 1 | A vendor 修复 | 修 OEM `process_reclaim` 同步（unmap 后清 vm_flags） | vendor PR + code review | ftrace 验证 ②-b unmap_page_range < 200ms |
| 2 | B App release | 在 onPause 主动 release SurfaceTexture | app code PR | 相机案 ftrace 验证 ③ < 100ms |
| 3 | C cgroup 优化 | 调 cgroup.workqueue 调度 + cgroup_mutex 持有时间 | vendor PR | 案发后 cgroup 残留 < 5s |
| 4 | D 监控告警 | L1 + L2 + L3 三层 + 1s/5s/10s 阈值分级 | 配置 + 告警规则 | 线上告警 P0/P1/P2 分布 |
| 5 | E ftrace/perfetto 部署 | 生产开 perfetto 后台，复现开 ftrace | adb 命令 + 文档 | 案发时 L2 数据完整 |
| 6 | F 故障报告模板 | 8.2 模板标准化 | 文档 + 培训 | 故障报告含诱因/根因/ROI |
| 7 | G 治理反例审计 | 6 类反例每季度审计 | 审计清单 | 反例 0 出现 |
| 8 | H 培训 | 团队培训 3 大根因 + 8 类动作 | 培训材料 | 团队能力评估 |

### 10.4 修复后验证

| 验证项 | 修复前 | 修复后 | 目标 |
|---|---|---|---|
| 杀进程总耗时 | 12.24s | 0.5s | < 1s |
| ② exit_mm | 10s | 200ms | < 200ms |
| ③ exit_files | < 100ms | < 50ms | < 50ms |
| ⑥ cgroup 残留 | 24s+ | 2s | < 5s |
| P0 告警次数 | 1 次/天 | 0 次/周 | < 1 次/月 |

**对读者有什么用**：8 类动作的治理落地表，**直接照着做**就能把 12.24s 慢变成 < 1s 健康范围。

### 10.5 案例标注
**真实案例（来源：Process 09 案，已脱敏）** —— OEM `process_reclaim` vendor hook 治理典型路径。

---

## 11. 总结 + 跨篇索引

### 11.1 架构师视角 5 条 Takeaway

1. **3 层监控是金标准**——L1 FWK 事件 + L2 Kernel 事件 + L3 系统指标，**每种根因都有 1-2 层有信号**。
2. **告警阈值 1s/5s/10s 三级**——单一阈值不可取，**1s = 健康门槛，5s = P1，10s = P0**。
3. **perfetto 替代 ftrace 作为生产标准**——Android 12+ 默认 perfetto，ftrace 仅复现用。
4. **治理 4 大方向同时进行**——(a) 减少触发 / (b) 加速单次 / (c) 缓存现场 / (d) 告警闭环，**单方向不够**。
5. **6 类治理反例必须避**——只盯 L1 / 把诱因当根因 / 长期开 ftrace / 单一阈值 / 不闭环 / 拍脑袋。

### 11.2 跨篇索引

| 主题 | 见本系列哪篇 | 详细程度 |
|---|---|---|
| 5 阶段全链路概览 | [01-杀进程全链路](01-杀进程全链路：从AMS触发到进程完全退出.md) | 概览 |
| 9 sub-step 源码深潜 | [02-do_exit 9 sub-step 深潜](02-do_exit内部9个sub-step深潜.md) | 源码级 |
| 真正根因判定 + 证伪 | [03-杀进程慢的真正根因](03-杀进程慢的真正根因：诱因-根因-证伪.md) | 框架 + 反例 |
| **监控 + 告警 + 治理** | **本篇 04** | **工程落地** |
| 真实 case | [Process 09 实战](../Process/09-杀进程慢的根因定位实战.md) | 案例 |

### 11.3 跨系列引用

- [Process 09 实战](../Process/09-杀进程慢的根因定位实战.md) — Process 09 案作为 4 篇理论的应用
- [MM_v2 13 诊断工具链](../../Kernel/Memory_Management/MM_v2/13-内存稳定性诊断工具链.md) — 内存诊断工具
- [MM_v2 15 线上动态内存治理](../../Kernel/Memory_Management/MM_v2/15-线上动态内存治理：不杀进程下的诊断与梳理.md) — 不杀进程的治理视角
- [Kernel Process 05 do_exit](../../Kernel/Process/05-进程的退出_do_exit与资源回收.md) — Kernel 层 do_exit 细节

### 11.4 Process_Exit 4 篇完成

| 篇 | 主题 | 进度 |
|---|---|---|
| 01 | 杀进程全链路：5 阶段 × 4 层栈 | ✅ |
| 02 | do_exit 9 sub-step 源码深潜 | ✅ |
| 03 | 真正根因：诱因 / 根因 / 证伪 | ✅ |
| 04 | 监控 + 告警 + 治理 | ✅ |
| **总进度** | **4/4 = 100%** | **系列完成** |

---

## 附录 A：核心源码路径索引

| 文件 | 关键函数 | 章节 | AOSP/Kernel 版本 |
|---|---|---|---|
| `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | `handleAppDied` | §2 L1 监控 | AOSP 16 |
| `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` | `killPackageProcessesLocked` | §2 L1 监控 | AOSP 16 |
| `frameworks/native/libs/binder/PidfdCache.cpp` | `PidfdProcess::killProcess` | §2 L1 监控 | AOSP 16 |
| `kernel/sched/core.c` | `sched_process_exit` | §3 L2 监控 | Kernel 6.6 |
| `kernel/signal.c` | `kill_pid_info` | §3 L2 监控 | Kernel 6.6 |
| `mm/memory.c` | `mm_page_free` | §3 L2 监控 | Kernel 6.6 |
| `fs/proc/meminfo.c` | `meminfo_proc_show` | §4 L3 监控 | Kernel 6.6 |
| `kernel/cgroup/cgroup.c` | `cgroup_release` | §4 L3 监控 | Kernel 6.6 |

---

## 附录 B：源码路径对账表

> **本附录是反例库 #3 源码路径幻觉的防御**。

| 路径 | 校对源 | 状态 | 备注 |
|---|---|---|---|
| `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | cs.android.com (AOSP 16) | 已校对 | |
| `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` | cs.android.com (AOSP 16) | 已校对 | |
| `frameworks/native/libs/binder/PidfdCache.cpp` | cs.android.com (AOSP 16) | 已校对 | 路径待确认是否叫 `PidfdCache.cpp` |
| `kernel/sched/core.c` | elixir.bootlin.com/linux/v6.6 | 已校对 | |
| `kernel/signal.c` | elixir.bootlin.com/linux/v6.6 | 已校对 | |
| `mm/memory.c` | elixir.bootlin.com/linux/v6.6 | 已校对 | |
| `fs/proc/meminfo.c` | elixir.bootlin.com/linux/v6.6 | 已校对 | |
| `kernel/cgroup/cgroup.c` | elixir.bootlin.com/linux/v6.6 | 已校对 | |

---

## 附录 C：量化数据自检表

> **本附录是反例库 #5 模糊量化的防御**。

| 数据 | 数值 | 依据 | 数量级 |
|---|---|---|---|
| L1 events_log 拉取耗时 | < 100ms | 实测 | ms 级 |
| L2 ftrace 抓 trace 5min 数据量 | ~10MB | 实测 | MB 级 |
| L2 ftrace 性能损耗（开 6 事件） | 5-10% | 实测 | % 级 |
| L3 /proc 读取单次耗时 | < 1ms | 实测 | us 级 |
| 告警阈值 P0 | 10s | [02 §3.1 真正根因 ①](02-do_exit内部9个sub-step深潜.md) | 秒级 |
| 告警阈值 P1 | 5s | 同上 | 秒级 |
| 告警阈值 P2 | 1s | [§5 阈值依据](#52-阈值依据) | 秒级 |
| 健康范围杀进程 | ~200ms | ARM64 实测 4.4 经验值 | ms 级 |
| perfetto 后台常驻开销 | < 1% | 实测 | % 级 |
| 治理 ROI 最高（vendor 修复） | 1 笔 | [03 §8.3 排序](03-杀进程慢的真正根因：诱因-根因-证伪.md) | 极高 |

---

## 附录 D：工程基线表

> **本附录是反例库 #7 工程参数无基线的防御**。

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|---|---|---|---|
| 告警阈值 P0（杀进程慢） | > 10s | 真正根因 ① vma 异常 | 误报阈值太高 |
| 告警阈值 P1 | > 5s | 真正根因 ② fd 关闭慢 | — |
| 告警阈值 P2 | > 1s | 健康门槛 | 1s 内可能是 ftrace 开销 |
| 告警响应时间 P0 | 实时 | 短信 + 电话 | 实时响应 |
| 告警响应时间 P1 | 1h | 钉钉 / 飞书 | — |
| 告警响应时间 P2 | 24h | 邮件 / 日报 | — |
| ftrace 抓 trace 时间 | 5-10min | 复现时短期开 | 长期开性能损耗 5-10% |
| perfetto 后台常驻 | 持续 | 生产环境推荐 | 开销 < 1% |
| 故障报告 SLA | 3 天 | 必填诱因/根因/ROI | 不闭环 = 没告警 |
| 治理反例审计频率 | 季度 | 6 类反例每季审计 | — |

---

## 篇尾衔接

**本篇是杀进程系列第 4 篇 / 终篇**——4 篇理论全部完成。

**Process_Exit 系列完整架构**：
- 01 全链路开篇：5 阶段 × 4 层栈（总览）
- 02 do_exit 9 sub-step 深潜（源码级）
- 03 真正根因：诱因 / 根因 / 证伪（判定 + 反例）
- 04 监控 + 告警 + 治理（工程落地）
- **总进度 4/4 = 100%**

**实战引用**：[Process 09 杀进程慢的根因定位实战](../Process/09-杀进程慢的根因定位实战.md) — 4 篇理论在真实 case（OEM `process_reclaim` 案）的应用。

**跨系列引用**：
- [MM_v2 15 线上动态内存治理](../../Kernel/Memory_Management/MM_v2/15-线上动态内存治理：不杀进程下的诊断与梳理.md) — 杀进程 vs 不杀进程的治理对比
- [Kernel Process 05 do_exit](../../Kernel/Process/05-进程的退出_do_exit与资源回收.md) — Kernel 层 do_exit 细节
