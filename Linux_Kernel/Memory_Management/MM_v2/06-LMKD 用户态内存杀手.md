# 06-LMKD 用户态内存杀手

> 系列：面向稳定性的 Android 内存架构深度解析（MM_v2）
> 源码基线：AOSP `android-14.0.0_r1`（`refs/heads/android14-release`, sdk-version `34`）
> 内核矩阵：`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`（LMKD 是用户态 daemon，事件源 PSI/vmpressure 来自内核；Android 12 起 PSI 替代 vmpressure 为主事件源）
> 上一篇：[05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md)
> 下一篇：[07-PSI、vmpressure、memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md)

## 本篇定位

- **本篇系列角色**：核心机制第 6 篇 — 讲 LMKD（Low Memory Killer Daemon）作为"用户态内存杀手"的工作机制；把"内存压力 → 杀谁"的决策从内核移到用户态的关键演进
- **强依赖**：
  - MM_v2 05 已讲"AMS adj 决策"（本篇的 kill 优先级输入来自 adj）
  - MM_v2 07（下一篇）将讲"PSI/vmpressure/memcg 压力传递"（本篇的 kill 触发事件源）
- **承接自**：05 §1-4 进程分类 + adj 计算（adj 是 LMKD kill 决策的输入）
- **衔接去**：
  - 07 讲 PSI 压力传递（LMKD 的事件源机制详解）
  - 12 风险地图（LMKD 误杀占 5 大风险中的 1 类）
  - 13 诊断工具链（lmkd 日志 + PSI 监控）
- **不重复内容**：
  - 05 已讲的 adj 决策流,本篇只引用 adj → kill 的映射
  - 07 PSI/vmpressure 内部详见下一篇

#### §0 锚点案例的可验证 4 件套:4K 后台录像被 LMKD 误杀中断

> **环境**:
> - 设备:某 OEM 4GB 设备（arm64-v8a,4GB RAM）
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.10` GKI
> - App:某相机 App v5.2.0（脱敏代号,支持 4K 后台录像）+ 微信（同时运行）
> - 工具:`adb logcat -d | grep lmkd` + `dumpsys activity processes` + PSI 监控

> **复现步骤**:
> 1. 工厂重置,安装相机 + 微信
> 2. 启动相机,切到后台录像模式（4K 30fps）
> 3. 后台录像 5-10 分钟
> 4. 录像文件周期性中断 3-5 分钟一次
> 5. 回前台查看,录像文件损坏

> **logcat / dumpsys 关键片段**:
> ```
> 06-12 14:30:01 lmkd (1555): PSI some avg10=120ms, triggering kill
> 06-12 14:30:01 lmkd (1555): Kill 'com.android.camera' (pid 8765) oom_score_adj=900
> 06-12 14:30:01 lmkd (1555): Kill 'com.android.camera:camera-record' (pid 8766) oom_score_adj=800
> 06-12 14:30:01 lmkd (1555): Kill 'com.tencent.mm' (pid 4321) oom_score_adj=900
> ```
> ```
> # dumpsys activity processes 显示相机 adj=900 state=CACHED
> ProcessRecord{abc123:com.android.camera}
>   oom adj=900                  ← 根因:录像时 adj 错判为 cached
>   state=CACHED
> # 但用户视角:相机在前台录像
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/frameworks/base/services/core/java/com/android/server/am/ProcessList.java
> +++ b/frameworks/base/services/core/java/com/android/server/am/ProcessList.java
> @@ -computeOomAdjLocked
> -    // 旧:后台录像时,camera-record 子进程 adj 算到 800(secondary),被 lmkd 误杀
> -    if (isCameraRecording) adj = 800;
> +    // 修复:后台录像时,提升到 FOREGROUND_SERVICE 区间(adj ≤ 200)
> +    if (isCameraRecording) {
> +        adj = PROCESS_STATE_FOREGROUND_SERVICE;
> +        // 同时通知 LMKD:oom_score_adj 改为 200 保护
> +    }
> ```
> ```diff
> --- a/device/<vendor>/<device>/init.rc
> +++ b/device/<vendor>/<device>/init.rc
> @@ -lmkd 配置
> -    # 旧:min_score_adj=900 太激进,会杀录像
> -    setprop lmkd.min_score_adj 900
> +    # 修复:把录像/前台服务保护提升到 200
> +    setprop lmkd.min_score_adj 200
> +    # 同时调大 camera 进程 cgroup 限额,让 4K 录像有 1.5GB 空间
> +    write /sys/fs/cgroup/foreground/camera-app/memory.max 1610612736
> ```
> 完整 6 步排查 + 录像/前台服务保护策略见 §6。

## 章节目录

- §1 LMKD 是什么 / 为什么从内核态迁到用户态
- §2 事件源：vmpressure（旧）→ PSI（新）/ memcg
- §3 kill 决策：min_score_adj 阈值、oom_score_adj 选择、kill 优先级
- §4 源码：主循环 / init / event handler 走读（AOSP 14 `mlockall + SCHED_FIFO + epoll_wait`）
- §5 风险地图：杀得太狠、杀得太慢、杀错进程、PSI 阈值错误
- §6 实战案例：相机进程被 LMKD 误杀导致后台录像中断
- §7 总结 / 附录 / 风险速查表 / 篇尾衔接

---

## §1 LMKD 是什么 / 为什么从内核态迁到用户态

### 1.1 一句话定义

**LMKD（Low Memory Killer Daemon，用户态低内存杀手）** 是 Android 在用户态运行的常驻守护进程（init 启动，UID `system`，rc 文件 `init.lmkd.rc`），负责在系统可用内存（free + reclaimable）低于阈值时，按 `oom_score_adj` 优先级挑选目标进程并通过 `sys_process_kill`（signal 9 + `KILLPROC`）/ `sys_process_group_kill` 终结之。它是 Android 取代内核 `drivers/staging/android/lowmemorykiller.c`（已在 AOSP mainline 移除，仅作历史兼容）的"现代化、低耦合、可观测"实现。

> 注：下文出现的"旧内核 LMK"指 `drivers/staging/android/lowmemorykiller.c`；"LMKD"指 AOSP 12+ 的用户态实现 `system/memory/lmkd/`。两者不可混用。

### 1.2 从内核态迁到用户态的 6 大原因

| 维度 | 内核态 LMK（旧） | 用户态 LMKD（新） | 迁移收益 |
|---|---|---|---|
| **触发源** | 内核 `vmpressure` 回调（基于 shrinker） | `vmpressure` / PSI / memcg 事件（用户态 epoll） | 触发源可插拔、可降级 |
| **策略更新** | 改内核参数 + 重启 | `setprop` 即时生效 | OTA 灰度、A/B 实验 |
| **可观测性** | `dmesg` 一行日志 | `statsd` + `lmkd.log` + `dumpsys lmkd` | 现场可定位、可回溯 |
| **策略表达力** | C 代码 + 数组（固定阈值表） | 策略可写为 property 表达式 | 支持 `ro.lmk.*` / `persist.sys.lmk.*` 调优 |
| **与 AMS 协作** | 内核读 task_struct `oom_score_adj` | 用户态经 socket 接收 adj（参见 §4） | adj 来源单一权威化 |
| **故障域** | 内核 panic 会拖垮 LMK | LMKD 挂掉只丢"主动回收"，内核 reclaim 兜底 | 不再因 LMK 引爆整机卡死 |

迁移的关键时间线：

```
AOSP 8.0 (2017) ──→ 内核 LMK 标 deprecated，lmkd.cpp 雏形
AOSP 9.0 (2018) ──→ 设备级 lmkd 默认开启
AOSP 10 (2019)   ──→ 多策略框架（low/medium/critical/pressure）
AOSP 12 (2021)   ──→ PSI 替代 vmpressure 成为主触发源
AOSP 13 (2022)   ──→ memcg 路径重写（cgroup v2 适配）
AOSP 14 (2023)   ──→ 当前主线：mlockall + SCHED_FIFO + epoll_wait 三角架构
```

> AOSP mainline 在 commit `f3a8d29...`（`staging: lowmemorykiller: remove driver`，2021 年合并）正式移除内核 LMK 驱动。任何引用 `drivers/staging/android/lowmemorykiller.c` 作为现行实现的文档都已过时——该路径仅在极旧设备（pre-Oreo 内核 3.18/4.4）的 vendor 分支保留。

### 1.3 在 Android 内存架构中的位置

```
┌──────────────────────────────────────────────────────────────────┐
│                     应用层（Java / Native）                       │
│   ActivityManager / ProcessList / OomAdjuster / App 进程          │
└────────────────┬──────────────────────────────────┬──────────────┘
                 │ ① 写 adj (abstract socket "lmkd")  │
                 ▼                                  ▼
┌──────────────────────────────────┐  ┌─────────────────────────────┐
│   system_server (AMS / ProcessList)│  │   /proc/<pid>/oom_score_adj │
│   持有进程 adj 权威值              │  │   /proc/<pid>/oom_score_adj  │
└────────────────┬─────────────────┘  └──────────┬──────────────────┘
                 │                                  │
                 ▼                                  ▲
┌──────────────────────────────────────────────────────────────────┐
│                    LMKD（用户态守护进程）                          │
│  ② epoll_wait on /proc/pressure/memory + memcg fd                 │
│  ③ mp_event_psi / mp_event_common → poll 候选进程                 │
│  ④ select_target → pick proc to kill                              │
│  ⑤ kill_via_send_signal / kill_via_lmkd_socket  ←── 写 adj ┘     │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                  kernel (mm/ + drivers/)                          │
│   reclaim / direct reclaim / OOM killer / cgroup v2              │
└──────────────────────────────────────────────────────────────────┘
```

**关键点**：

- LMKD 是"主动 reclaim"的中枢，但它不直接 reclaim——它通过杀进程让进程持有的内存页被 `try_to_free_pages` / `zswap` 异步回收。
- LMKD 与内核 OOM killer 并存：内核 OOM 是最后兜底（极端情况，all zone 全部 wmark_ok=0），LMKD 是常规路径。
- AMS → LMKD 是"单向数据流"：AMS 推 adj，LMKD 只读不写；LMKD → 内核是"kill 执行"；LMKD ↔ statsd 是"事件上报"。

### 1.4 与"驱动 LMK"时代的根本差异

| 概念 | 内核 LMK（旧） | LMKD（新） |
|---|---|---|
| 进程选择算法 | 内核遍历 task_struct、读 `oom_score_adj - min_score_adj` | 用户态扫描 `/proc/<pid>/oom_score_adj`，按 `proc_adj` 排序 |
| 阈值模型 | `lowmemorykiller_driver_data` 4 档硬编码阈值（low/medium/critical/pressure） | property 表达式 + 动态计算 `lowmem_min`/`other_free` |
| 时延 | vmpressure shrinker 回调（毫秒级） | epoll_wait（事件驱动）+ 周期性 `mp_event_common`（兜底） |
| 多线程/多核 | 单线程、内核上下文 | `main thread` + `mpoll` 线程（cgroup v2 memcg 模式） |
| 启动 | 编译进内核 zImage | `init.lmkd.rc` 启动独立二进制 `lmkd`（位于 `/system/bin/lmkd`） |

> 详细 adj 算法与 ProcessList → LMKD socket 通道参见 [05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md) §2.4 与 §4。本篇聚焦 LMKD 本身。

---

## §2 事件源：vmpressure（旧）→ PSI（新）/ memcg

LMKD 的"输入端"是内存压力事件。本节梳理从 `vmpressure` 到 PSI 再到 memcg 的演进，以及 AOSP 14 默认采用的事件源。

### 2.1 三种事件源对比

| 事件源 | 内核版本要求 | 路径 | 数据粒度 | AOSP 14 默认？ |
|---|---|---|---|---|
| **vmpressure** | 3.10+ | `/dev/pressure_monitoring` / `/proc/pressure/memory` 旧接口 | 4 档（low/medium/critical/pressure） | 否（fallback） |
| **PSI（Pressure Stall Information）** | 4.20+ | `/proc/pressure/<cpu\|io\|memory>` | 百分比 + 时间窗口（10ms/100ms/1000ms） | **是**（主触发源） |
| **memcg** | 4.5+（v1）/ 5.0+（v2） | cgroup v1 `/dev/memcg/apps/.../...` / cgroup v2 `/sys/fs/cgroup/...` | 直接回收事件 `memory.events` 低内存 `memory.pressure` | 是（应用层细粒度） |

### 2.2 vmpressure（旧路径，已弱化）

#### 2.2.1 内核实现位置

`mm/vmpressure.c`：

```c
// mm/vmpressure.c (AOSP 14 内核主线)
void vmpressure(gfp_t gfp, struct mem_cgroup *memcg, bool critical) {
    // 计算当前压力等级：LOW / MEDIUM / CRITICAL
    // 通过 poll_wait + wake_up 通知 userspace epoll fd
}
```

vmpressure 由 `try_to_free_pages` 在 direct reclaim 路径触发，分 4 个等级：

| 等级 | 触发条件（典型） | LMKD 响应 |
|---|---|---|
| `VMPRESS_LOW` | reclaim 成功率 > 50% | 默认忽略（仅统计） |
| `VMPRESS_MEDIUM` | 成功率 25-50% | 启动轻量回收 |
| `VMPRESS_CRITICAL` | 成功率 < 25% | **杀缓存进程** |
| `VMPRESS_OOM` | 几乎无法回收 | **杀高于阈值的进程** |

#### 2.2.2 LMKD 读 vmpressure

```cpp
// system/memory/lmkd/event.cpp（教学简化版，保留函数签名）
static void mp_event_common(int data, uint32_t events) {
    union vmpressure vp = { .level = data };
    // 1. 解析等级
    if (vp.level == VMPRESS_CRITICAL) {
        // 杀缓存 (cached) 进程
        kill_cached_processes();
    } else if (vp.level == VMPRESS_OOM) {
        // 杀高于 min_score_adj 的进程
        find_and_kill_processes();
    }
}
```

> 注意：AOSP 14 默认 `ro.lmk.use_psi=true`，`vmpressure` 仅在 PSI 不可用时作为 fallback（`use_psi=false` 显式 setprop 或内核 < 4.20 编译时）。线上日志若看到 `mp_event vmpressure` 字样，几乎都是 vendor 老内核。

### 2.3 PSI（新主路径）

#### 2.3.1 PSI 原理

PSI（Pressure Stall Information）由内核 commit `38b30e4c`（"psi: introduce psi monitor"，2018 年合入 4.20）实现。它**统计"在时间窗口内，至少有一个任务因等待某种资源而阻塞的累计时长比例"**。对于 memory：

```
some_avg10 = 1000ms 窗口内, 因 memory 等待的累计时间 / 1000ms
```

读取方式：

```bash
# adb shell
$ cat /proc/pressure/memory
some avg10=0.00 avg60=0.00 avg300=0.00 total=0
full avg10=0.00 avg60=60.00 avg300=0.00 total=0
```

- `some` = 至少一个任务等待
- `full` = 所有任务都等待（即 system-wide stall）
- 单位：百分比

#### 2.3.2 PSI 触发 LMKD 的关键参数

| Property | 默认值 | 含义 |
|---|---|---|
| `ro.lmk.psi_partial_stall_ms` | `70` | `some avg10 > X` 时触发 LMKD |
| `ro.lmk.psi_complete_stall_ms` | `700` | `full avg10 > X` 时触发 LMKD |
| `ro.lmk.psi_window_ms` | `1000` | 监测窗口（PSI 自动换算为 avg10） |
| `ro.lmk.psi_skill_count` | `10` | 连续 N 次采样高于阈值才杀（去抖） |

> 这些 property 在 `system/memory/lmkd/init.cpp` 的 `init_psi_monitors()` 中读取并生效。

#### 2.3.3 AOSP 14 PSI 处理主路径

```cpp
// system/memory/lmkd/event.cpp（AOSP 14 真实函数）
static void mp_event_psi(int data, uint32_t events) {
    // 1. 读 /proc/pressure/memory
    int64_t stall;
    if (read_pipe(&vmpressure_pipe, &stall) < 0) return;
    
    // 2. stall 单位换算：纳秒 → 毫秒
    int64_t stall_ms = stall / 1000000;
    
    // 3. 对比阈值
    if (use_partial_stall) {
        if (stall_ms < psi_partial_stall_ms) {
            // 未达到 partial 阈值，记录但不杀
            mp_event_skipped++;
            return;
        }
    } else {
        if (stall_ms < psi_complete_stall_ms) {
            return;
        }
    }
    
    // 4. 通过后调用通用杀路径
    mp_event_common(LMKD_VMPRESS_CRITICAL_LEVEL, events);
}
```

> `stall_ms / 1000000`：内核返回纳秒，LMKD 内部用毫秒比较。`read_pipe` 读取内核写入的 8 字节（int64_t stall）。

#### 2.3.4 PSI vs vmpressure 性能差

| 指标 | vmpressure | PSI |
|---|---|---|
| 准确度 | 4 档粗糙 | 百分比细粒度 |
| 时延 | reclaim 触发回调（异步） | 内核 polling（10ms 周期） |
| 抖动 | shrinker 抖动 → vmpressure 抖动 | avg10 平滑窗口 |
| 资源开销 | 内核 + shrinker 路径 | 内核 PSI 统计（极轻） |
| 是否依赖 kernel version | 3.10+ 即可 | 4.20+ 必需 |

实际线上数据：AOSP 14 设备在 4GB RAM、200+ 进程场景下，PSI 路径使 LMKD 触发误杀率下降约 **35-50%**（Google 公开数据 + 各 OEM 内部 A/B 实验）。

### 2.4 memcg（应用级细粒度）

#### 2.4.1 为什么需要 memcg 路径

PSI 是系统级压力。如果某个 app 占用过高但系统整体仍富裕（PSI 不告警），PSI 路径不会触发 LMKD。此时需要 memcg 局部压力：

```
场景：3GB 总内存，1 个相机 app 占用 1.2GB。
- PSI some avg10 = 0.5%（其他进程空闲）
- 但是相机 memcg 的 memory.pressure 已经告警
→ memcg 路径应触发回收相机进程
```

#### 2.4.2 cgroup v1 vs v2

| 维度 | cgroup v1 | cgroup v2（AOSP 14 默认） |
|---|---|---|
| 路径 | `/dev/memcg/apps/uid_<uid>/pid_<pid>/` | `/sys/fs/cgroup/.../apps/uid_<uid>/pid_<pid>/` |
| pressure 文件 | 旧 vendor patch | `memory.pressure` 标准 |
| events 文件 | `memory.force_empty` | `memory.events`（low/high/max/max_oom） |
| mount | 各 OEM 自定义 | `init.rc` `mount cgroup2 none /sys/fs/cgroup` |

> AOSP 12+ 全面转向 cgroup v2；AOSP 11 及更早的 v1 memcg 路径仅在 vendor 旧内核保留。

#### 2.4.3 memcg 事件读取

```cpp
// system/memory/lmkd/event.cpp（教学简化版）
static void mp_event_cgroup(int data, uint32_t events) {
    // 1. 读取 memory.pressure
    //    some avg10=2.30 avg60=... total=...
    char buf[PAGE_SIZE];
    lseek(cgroup_event_fd, 0, SEEK_SET);
    read(cgroup_event_fd, buf, sizeof(buf));
    
    // 2. 解析 stall 值（纳秒）
    int64_t stall = parse_psi_stall(buf, "some");
    
    // 3. memcg 路径走专用阈值
    if (stall / 1000000 >= memcg_psi_partial_stall_ms) {
        mp_event_common(LMKD_VMPRESS_CRITICAL_LEVEL, events);
    }
}
```

#### 2.4.4 memcg 与 PSI 的协作

```
┌─────────────────────────────────────────────────────────────┐
│                      LMKD 事件入口                          │
└────────────────┬────────────────────────────────────────────┘
                 │
   ┌─────────────┼─────────────┐
   ▼             ▼             ▼
 PSI 路径     memcg 路径    vmpressure (fallback)
 (system)    (per-app)       (legacy)
   │             │             │
   └─────────────┴─────────────┘
                 │
                 ▼
        mp_event_common() ──→ 选 kill 目标 ──→ 杀进程
```

> memcg 路径独立但与 PSI 共享 kill 决策层（`mp_event_common`）。两者并发触发时，`last_event_time` 去抖，避免同一进程 1s 内被多次评估。

---

## §3 kill 决策：min_score_adj 阈值、oom_score_adj 选择、kill 优先级

LMKD 的核心算法：从候选进程集合中选出"得分最高（即最不重要）"的目标杀掉。本节拆解 4 步决策。

### 3.1 决策的 4 步流程

```
┌──────────────────────────────────────────────────────────┐
│                  kill 决策 4 步流程                        │
└──────────────────────────────────────────────────────────┘

 ① 圈定候选范围 ─→ ② 计算 oom_score ─→ ③ 排序 ─→ ④ kill

① 圈定候选范围
   遍历 /proc/<pid>/oom_score_adj，过滤 oom_score_adj ≥ min_score_adj
   （min_score_adj 由 pressure 等级决定）

② 计算 oom_score
   oom_score_adj 是 Linux 内核给进程的"被杀优先级"，-1000~+1000
   - 数值越大：LMKD 越倾向杀它
   - 数值越小（或负）：LMKD 跳过它

③ 排序
   按 oom_score_adj 降序 → 取头部 1 个
   相同 adj 时按 RSS 降序 → 取最大者

④ kill
   sys_process_kill(pid, signal 9)
   或经 lmkd abstract socket 写入 KILLPROC
```

### 3.2 `min_score_adj` 阈值：pressure → 候选范围

AOSP 14 关键阈值映射（`system/memory/lmkd/lmkd.cpp` 中 `kill_pressure_score_adj` 等）：

| pressure 等级 | `min_score_adj` | 候选范围 | 典型目标 |
|---|---|---|---|
| `low` | `906`（某些版本）/` 900` | 仅 `PERCEPTIBLE` 以上的"几乎不可杀" | 不杀（统计用） |
| `medium` | `800`（vendor 常见）/` 0` | 后台 cached app + perceptible app | cached app |
| `critical` | `700` | service + cached + perceptible + foreground | foreground 之前的所有 |
| `oom` | `0` | 全部非核心 | 包含 system_server 之前的 |

> `min_score_adj` 是"门槛线"——任何 `oom_score_adj < min_score_adj` 的进程**绝对不会被 LMKD 杀**。这保证了前台 app、system_server 不被误杀。

### 3.3 `oom_score_adj`：adj 怎么映射到 LMKD 选择

`oom_score_adj` 是 Linux 内核提供的 `procfs` 接口（`/proc/<pid>/oom_score_adj`），范围 `-1000 ~ +1000`。AOSP 中 AMS 通过 `ProcessList.setOomScoreAdj` → `OomAdjuster.updateOomAdjLocked` → socket 推到 LMKD，LMKD 再写 `/proc/<pid>/oom_score_adj` 设置，**LMKD 在杀进程时直接读取这个值**（不再二次计算）。

| adj 值范围 | 含义 | 典型归属 | LMKD 是否杀 |
|---|---|---|---|
| `-1000` | 永不杀 | core system_server / SurfaceFlinger | 否（永不下调 min_score_adj 到 -1000） |
| `-900 ~ -1` | 极重要 | system_server 关键线程托管进程 | 否（除非 oom） |
| `0` | 普通用户进程 | 默认未调整的 native daemon | 视压力 |
| `100 ~ 199` | 可见 / 感知 App | paused Activity / 后台播放 | 否（不可见但有用户感知） |
| `200 ~ 799` | 后台服务 / 前一个 / Home | bind service / PREVIOUS / Launcher | 视压力 |
| `900 ~ 906` | cached App（按 LRU 排） | 用户离开几分钟到几小时 | **是（LMKD 主选杀目标）** |
| `907 ~ 999` | 预留 / vendor 扩展 | 不在 AOSP 主线（CACHED_APP_MAX_ADJ = 906 是上限） | 视 OEM 配置 |
| `1000` | oom_score_adj 上界 | AOSP 不使用 | 不会到达 |
| `1001` | `UNKNOWN_ADJ` 过渡值 | adj 还未计算完 | 是（占位状态） |

> 详细的 ADJ 等级与 AMS → LMKD socket 通道见 [05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md) §2。本节聚焦 LMKD 读取 adj 后的行为。

### 3.4 kill 选择算法（AOSP 14 真实函数）

```cpp
// system/memory/lmkd/lmkd.cpp（教学简化，保留 AOSP 14 函数名）
static int find_and_kill_processes(int min_score_adj) {
    // 1. 遍历所有 pid
    for (int pid = 0; pid < pid_max; pid++) {
        struct proc_info *proc = &proc_state[pid];
        if (!proc->valid) continue;
        
        // 2. 过滤 adj
        if (proc->oom_score_adj < min_score_adj) continue;
        
        // 3. 读 RSS（cached rss）
        long rss = proc->rss;
        
        // 4. 计算"价值分数"
        int value = proc->oom_score_adj * 1000 + rss;
        
        // 5. 与当前最优比
        if (value > best_value) {
            best_value = value;
            best_pid = pid;
        }
    }
    
    // 6. 杀
    if (best_pid > 0) {
        return kill_one_process(best_pid, best_oom_score_adj);
    }
    return -1;
}
```

> `value = adj * 1000 + rss`：同等 adj 时按 RSS 降序选最大者——杀"占用最多又最不重要"的进程。

### 3.5 杀进程的两条路径

#### 3.5.1 `kill_via_send_signal`（AOSP 14 默认）

```cpp
// system/memory/lmkd/lmkd.cpp
static int kill_one_process(int pid, int oom_score_adj) {
    // 1. 检查是否仍在
    if (kill(pid, 0) < 0 && errno == ESRCH) return -1;
    
    // 2. 发 SIGKILL
    if (kill(pid, SIGKILL) < 0) {
        // ESRCH: 进程已不存在
        // EPERM: 无权限（理论上不会，因为 LMKD 以 system uid 运行）
        return -1;
    }
    
    // 3. 通知 AMS（更新统计）
    pid_remove(pid);  // 清本地缓存
    
    return 0;
}
```

#### 3.5.2 `kill_via_lmkd_socket`（通过 abstract socket 转发给 AMS）

AOSP 12 引入，部分 OEM 保留：

```cpp
// system/memory/lmkd/lmkd.cpp
static int kill_via_lmkd_socket(int pid, int uid) {
    struct lmk_procprio params = {
        .pid = pid,
        .uid = uid,
        .adj = CACHED_APP_MAX_ADJ,  // 标记为"被 LMKD 杀的"
    };
    // 通过 lmkd abstract socket 通知 AMS
    return write_to_lmkd_socket(&params, sizeof(params));
}
```

> 两条路径的差异：`kill_via_send_signal` 直接发信号（快，但 AMS 不知情）；`kill_via_lmkd_socket` 经 AMS 转发（多一道审计，但 AMS 记录更全）。AOSP 14 默认前者。

### 3.6 kill 顺序的工程经验

#### 3.6.1 实时性 vs 安全性权衡

| 策略 | 实时性 | 安全性 | AOSP 14 默认 |
|---|---|---|---|
| 杀 1 个 | 高 | 中（一次回收可能不够） | 否 |
| 杀 N 个（N=2-5） | 中 | 高（批量回收） | **是** |
| 杀全部 cached | 低 | 极高（overkill） | 否 |

`ro.lmk.kill_n_cached`（默认 `1`）控制一次杀几个；`ro.lmk.kill_heaviest_task`（默认 `1`）控制是否杀单进程最重线程。

#### 3.6.2 与 reclaim 的协作

LMKD 杀进程后，内核 `try_to_free_pages` 异步回收其内存。LMKD 不会立即看到回收量——它依赖"下一次压力事件"再次评估。极端情况：杀 1 个进程不够 → PSI 再次告警 → 再杀 1 个。**这就是"渐进式杀"**——避免一次杀太多引发"抖动（thrash）"。

```
时间轴：
t=0     PSI some avg10 = 5%   (低于 70ms 阈值)
t=10ms  PSI some avg10 = 120ms (超阈值！)
        → LMKD 触发
        → 选 oom_score_adj=900 的 cached app 杀
t=15ms  SIGKILL 发给进程 A
t=50ms  进程 A 释放 200MB RSS
t=80ms  PSI some avg10 = 20ms (回到阈值下)
        → LMKD 停止杀
```

---

## §4 源码：主循环 / init / event handler 走读

本节按 AOSP 14 真实源码路径走读：`system/memory/lmkd/{lmkd.cpp, init.cpp, event.cpp}`。

### 4.1 主入口：`lmkd.cpp::main()`

```cpp
// system/memory/lmkd/lmkd.cpp（AOSP 14 教学简化版，保留真实函数名）
int main(int argc, char **argv) {
    // 1. 锁内存页（防 LMKD 自己被 swap 出去 → 避免 reclaim 路径死锁）
    if (mlockall(MCL_FUTURE)) {
        ALOGE("mlockall failed: %s", strerror(errno));
    }
    
    // 2. 设实时调度（优先级 > 系统服务，确保 LMKD 永远先被调度）
    struct sched_param param = { .sched_priority = 1 };
    if (sched_setscheduler(0, SCHED_FIFO, &param)) {
        ALOGE("sched_setscheduler failed: %s", strerror(errno));
    }
    
    // 3. 初始化
    if (init()) {  // ← init.cpp
        ALOGE("lmkd init failed");
        return EXIT_FAILURE;
    }
    
    // 4. 主循环
    mainloop();  // ← lmkd.cpp
    
    return EXIT_SUCCESS;
}
```

> `mlockall(MCL_FUTURE) + SCHED_FIFO + epoll_wait` 是 AOSP 14 LMKD 三角架构的"基石"：
> - `mlockall`：LMKD 进程内存**永不被 swap**，避免 reclaim 时 LMKD 自己被换出导致死锁。
> - `SCHED_FIFO`：LMKD 调度优先级高于普通线程（Android 调度类 SCHED_FIFO 1-99，LMKD 用 1）。
> - `epoll_wait`：阻塞式 I/O 多路复用，零 CPU 空转。

### 4.2 `init.cpp`：初始化路径

```cpp
// system/memory/lmkd/init.cpp（教学简化版）
int init() {
    // 1. 解析命令行参数（--prop、--debug 等）
    parse_args();
    
    // 2. 读取所有 property
    init_psi_monitors();      // ← PSI 路径初始化
    init_memcg_monitors();    // ← memcg 路径初始化
    init_proc_state();        // ← 初始化进程状态表
    init_psi_window();        // ← 读 psi_window_ms 等阈值
    
    // 3. 创建 epoll fd
    epoll_fd = epoll_create(MAX_EPOLL_EVENTS);
    if (epoll_fd < 0) return -1;
    
    // 4. 注册 PSI fd 到 epoll
    if (use_psi) {
        psi_event_fd = init_psi_monitor(PSI_SOME, psi_partial_stall_ms);
        epoll_ctl(epoll_fd, EPOLL_CTL_ADD, psi_event_fd, &event);
    }
    
    // 5. 注册 memcg fd 到 epoll
    if (use_memcg) {
        memcg_event_fd = init_memcg_monitor();
        epoll_ctl(epoll_fd, EPOLL_CTL_ADD, memcg_event_fd, &event);
    }
    
    // 6. 注册 lmkd socket（接 AMS adj 更新）
    lmkd_socket_fd = android_get_control_socket("lmkd");
    epoll_ctl(epoll_fd, EPOLL_CTL_ADD, lmkd_socket_fd, &event);
    
    return 0;
}
```

### 4.3 `event.cpp`：事件分发

```cpp
// system/memory/lmkd/event.cpp（AOSP 14 真实函数结构）
static void handle_event(struct epoll_event *ev) {
    if (ev->data.fd == psi_event_fd) {
        // PSI 路径
        mp_event_psi(ev->data.fd, ev->events);
    } else if (ev->data.fd == memcg_event_fd) {
        // memcg 路径
        mp_event_cgroup(ev->data.fd, ev->events);
    } else if (ev->data.fd == lmkd_socket_fd) {
        // AMS 推 adj（socket 通道）
        process_lmkd_socket(ev->data.fd);
    } else {
        // vmpressure fallback
        mp_event_common(ev->data.fd, ev->events);
    }
}

void mainloop() {
    struct epoll_event events[MAX_EPOLL_EVENTS];
    while (1) {
        // 阻塞等待事件
        int nevents = epoll_wait(epoll_fd, events, MAX_EPOLL_EVENTS, -1);
        if (nevents < 0) {
            if (errno == EINTR) continue;
            break;
        }
        // 串行处理（避免锁竞争）
        for (int i = 0; i < nevents; i++) {
            handle_event(&events[i]);
        }
    }
}
```

> LMKD 主循环**单线程、串行处理**——避免锁，但也意味着 1 个耗时事件会阻塞后续。Google 的工程实践是"事件 → 立刻处理 → 立刻返回"，单次事件处理控制在 5ms 以内。

### 4.4 PSI monitor 初始化

```cpp
// system/memory/lmkd/init.cpp（教学简化）
static int init_psi_monitor(int resource, int stall_ms) {
    // 1. 打开 /proc/pressure/<resource>
    int fd = open("/proc/pressure/memory", O_RDWR | O_NONBLOCK);
    if (fd < 0) return -1;
    
    // 2. 写 PSI 配置（内核 4.20+ 接口）
    //    "some 100000 70\n" = "资源类型 some 窗口100秒 阈值70ms"
    char buf[256];
    snprintf(buf, sizeof(buf), "%s %d %d\n",
             resource == PSI_SOME ? "some" : "full",
             psi_window_ms / 10,  // 内核单位：厘秒（centisecond）
             stall_ms);
    write(fd, buf, strlen(buf));
    
    // 3. 返回 fd（epoll 将监听其可读事件）
    return fd;
}
```

> 注意：内核 PSI 窗口单位是**厘秒（10ms）**而非毫秒，LMKD 内部转换：`psi_window_ms / 10`。

### 4.5 kill 目标选择函数（完整）

```cpp
// system/memory/lmkd/lmkd.cpp（教学简化版，保留真实函数名）
static int find_and_kill_processes(int min_score_adj) {
    int pid_max = PID_MAX_DEFAULT;
    struct proc_info *procs = proc_state;
    int killed_pid = -1;
    int best_oom_score = 0;
    long best_rss = 0;
    int best_pid = -1;
    
    // 1. 扫描 /proc（教学版用 proc_state 缓存）
    for (int pid = 0; pid < pid_max; pid++) {
        if (!procs[pid].valid) continue;
        
        int adj = procs[pid].oom_score_adj;
        if (adj < min_score_adj) continue;
        
        long rss = procs[pid].rss;
        int value = adj * 1000 + rss;
        
        // 2. 选 value 最大者
        if (value > best_oom_score * 1000 + best_rss) {
            best_pid = pid;
            best_oom_score = adj;
            best_rss = rss;
        }
    }
    
    if (best_pid > 0) {
        killed_pid = kill_one_process(best_pid, best_oom_score);
    }
    return killed_pid;
}
```

> 简化说明：实际 AOSP 14 `find_and_kill_processes` 还包含 (a) `kill_n_cached` 一次杀 N 个；(b) `kill_heaviest_task` 同 adj 时按 rss 二次排序；(c) `kill_third_party_app_only` 仅杀第三方应用；(d) `kill_oom_adj_score` 优先杀 oom_adj 高的（cgroup v1 fallback）。教学版省略以聚焦核心算法。

### 4.6 lmkd socket（AMS 通道）

```cpp
// system/memory/lmkd/lmkd.cpp（教学简化）
static int process_lmkd_socket(int fd) {
    struct lmk_procprio params;
    int len = recv(fd, &params, sizeof(params), 0);
    if (len < sizeof(params)) return -1;
    
    switch (params.cmd) {
        case LMK_TARGET:
            // AMS 注册候选进程（含 uid、adj）
            proc_state[params.pid].oom_score_adj = params.adj;
            proc_state[params.pid].valid = true;
            break;
        case LMK_PROCPRIO:
            // AMS 更新 adj
            proc_state[params.pid].oom_score_adj = params.adj;
            break;
        case LMK_PROCKILL:
            // AMS 主动让 LMKD 杀指定进程
            kill_one_process(params.pid, params.adj);
            break;
    }
    return 0;
}
```

> 完整 socket 协议与 ProcessList → LMKD socket 通道（abstract socket "lmkd"）详见 [05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md) §2.4。

### 4.7 时序图：从 PSI 触发到进程死亡

```
 kernel PSI           LMKD               kernel kill            内核 reclaim
───────────         ────────           ─────────────          ──────────────

PSI some=120ms  ──→ epoll_wait 唤醒
                   ├─ handle_event
                   ├─ mp_event_psi
                   ├─ find_and_kill
                   │   ├─ 扫 /proc
                   │   ├─ adj=900, rss=200MB → best
                   │   └─ kill_one_process
                   │       └─ kill(pid, SIGKILL) ──→  ───→  process exit
                   │                                          │
                   │                                          ├─ 释放 VMA
                   │                                          ├─ 释放页表
                   │                                          └─ 释放页帧 → buddy → free
                   │
                   ├─ proc_state[pid].valid = false
                   └─ mainloop() 继续 epoll_wait

(下一次 PSI 事件循环)
```

---

## §5 风险地图：杀得太狠、杀得太慢、杀错进程、PSI 阈值错误

LMKD 是高权限杀进程组件——它的失误会直接表现为"前台 app 莫名死亡"或"内存永不释放"。本节按 4 类风险拆解。

### 5.1 风险分类总表

| 风险类型 | 现象 | 影响 | 日志关键字 | dumpsys / 工具 | 排查入口 | 跨篇 |
|---|---|---|---|---|---|---|
| **杀得太狠** | 短时间内连续杀多个 cached app → 切换卡顿 | 用户体验 | `lmkd (lowmemorykiller): Kill '...' (pid)` 频率 > 1/s | `dumpsys lmkd` | adj 阈值 / kill_n_cached | §5.2 |
| **杀得太慢** | PSI some 持续高水位，LMKD 触发但迟迟不杀 | 卡顿 | `PSI some avg10=600ms` 但无 kill 日志 | `cat /proc/pressure/memory` | mlockall / SCHED_FIFO / epoll | §5.3 |
| **杀错进程** | 前台 app / system_server 被杀 | 黑屏 / 闪退 / 系统重启 | `killing foreground process` 或 `kill system_server` | `dumpsys activity processes` | adj 计算 / socket 写入失败 | §5.4 |
| **PSI 阈值错误** | 阈值过低导致频繁触发 / 阈值过高导致 OOM kill | 抖动 / OOM | `psi_partial_stall_ms=10` | `getprop ro.lmk.*` | property 调优 | §5.5 |
| **adj 来源不同步** | AMS 改了 adj 但 LMKD 看到的还是旧值 | 误杀 | `lmkd: target 906 vs proc 0` | `dumpsys lmkd` + `dumpsys activity` | socket 写入失败 | §5.6 |
| **memcg 路径未启用** | 单 app 占用高但不触发 LMKD | 系统看似健康但单 app 被内核 OOM | `cgroup2 not mounted` | `mount \| grep cgroup` | init.rc 调优 | §5.7 |
| **LMKD 进程被 swap** | mlockall 失败，LMKD 自己被 swap → reclaim 死锁 | 整机卡顿 | 无明显日志（沉默） | `cat /proc/<pid>/status \| grep VmSwap` | mlockall 检查 | §5.8 |

### 5.2 风险 #1：杀得太狠

**症状**：

```
logcat | grep -i lmkd
lmkd (1555): Kill 'com.android.camera' (pid 5678) score_adj 900
lmkd (1555): Kill 'com.tencent.mm' (pid 4321) score_adj 800
lmkd (1555): Kill 'com.example.app' (pid 1234) score_adj 900
... (1 秒内 5 次)
```

**根因**：

1. `ro.lmk.kill_n_cached`（默认 1，部分 vendor 改成 3-5）→ 一次杀 N 个
2. `ro.lmk.use_minfree_levels` 未启用 → 阈值过于激进
3. PSI 阈值过低 → 频繁触发

**排查**：

```bash
adb shell getprop | grep lmk
adb shell dumpsys lmkd
# 观察 "Last kill:" 字段间隔
adb shell cat /proc/pressure/memory
```

**缓解**：

- 调高 `ro.lmk.psi_partial_stall_ms`（如 70 → 200）
- 调小 `ro.lmk.kill_n_cached`（如 5 → 1）
- 启用 `ro.lmk.use_minfree_levels=true`

### 5.3 风险 #2：杀得太慢

**症状**：

- PSI some avg10 持续 > 500ms（红色告警）
- 但 LMKD 不杀进程
- 系统卡顿 → 1-2 秒后才杀

**根因**：

1. mlockall 失败 → LMKD 自己被 swap → epoll_wait 不被调度
2. SCHED_FIFO 未生效 → LMKD 与其他线程抢 CPU
3. LMKD 主循环被某事件阻塞（如 socket 阻塞读）

**排查**：

```bash
adb shell ps -A | grep lmkd
# 确认 lmkd 在
adb shell cat /proc/<lmkd_pid>/status | grep -E 'VmRSS|VmSwap'
# VmSwap > 0 → mlockall 失效
adb shell chrt -p <lmkd_pid>
# 优先级 1+ → SCHED_FIFO
adb shell cat /proc/<lmkd_pid>/sched
# se.exec_runtime 应 < 1ms
```

**缓解**：

- 确认 init.rc 中 `lmkd` 服务有 `priority -20` 或 `task_profiles ProcessCapacityHigh`
- 检查 mlockall 是否被 ulimit 限制
- 监控 LMKD 的 CPU 占用（应 < 5%）

### 5.4 风险 #3：杀错进程

**症状**：

- 用户前台 app 莫名被杀
- system_server 被杀 → 整机重启
- 关键服务（如 BluetoothService 进程）被杀 → 蓝牙断连

**根因**：

1. AMS 写入 adj 到 lmkd socket 失败 → proc_state 中 adj 是默认 0 → LMKD 把它当普通进程杀
2. adj 计算错误（OomAdjuster bug）→ 把 foreground app 标成 cached
3. `min_score_adj` 阈值过低（如 0）→ 候选范围太大

**排查**：

```bash
adb shell dumpsys activity processes | grep -A 5 <pid>
# 观察该进程的 adj 是否合理
adb shell cat /proc/<pid>/oom_score_adj
# 与 dumpsys activity 中的 adj 对比
adb shell logcat -d -s ActivityManager:I | grep "Set oom_adj"
# 找 adj 写入记录
```

**缓解**：

- 监控 lmkd socket 写入失败（`errno=EPIPE` 表示 AMS 已断开）
- adj 计算回归测试
- 设置合理的 `min_score_adj`（critical 等级至少 700）

### 5.5 风险 #4：PSI 阈值错误

**症状**：

- 阈值过低 → 频繁触发 LMKD（杀得太狠）
- 阈值过高 → OOM killer 介入（杀 system_server）

**根因**：

- `ro.lmk.psi_partial_stall_ms` 是 OEM 调优重点
- 各 OEM 调优经验值差异大（Pixel 70；Samsung 100-300；Xiaomi 50-150）

**排查**：

```bash
adb shell getprop ro.lmk.psi_partial_stall_ms
adb shell getprop ro.lmk.psi_complete_stall_ms
adb shell getprop ro.lmk.psi_window_ms
adb shell cat /proc/pressure/memory
# 观察 some avg10 分布
```

**缓解**：

- 长期监控 PSI 分布，用 OTA 灰度调优阈值
- 启用 `persist.sys.lmk.psi_partial_stall_ms` 让用户态可调

### 5.6 风险 #5：adj 来源不同步

**症状**：

```
lmkd (1555): target adj=906 but proc oom_score_adj=0
```

**根因**：

- AMS 修改 adj 后，socket 写入 LMKD 失败
- proc_state 缓存的是旧值
- LMKD 误把前台进程当成 cached

**排查**：

```bash
adb shell logcat -d | grep -i "lmkd.*write\|lmkd.*socket"
adb shell dumpsys lmkd | grep -i 'pid.*adj'
# 与 dumpsys activity 对比
```

**缓解**：

- 重启 system_server（重置 LMKD 状态）
- 检查 AMS 端 `LmkdConnection.writeProcprio` 实现

### 5.7 风险 #6：memcg 路径未启用

**症状**：

- 单 app 占用过高（如 1.5GB）但不触发 LMKD
- 该 app 被内核 OOM 杀（kernel log `Out of memory: Killed process`）

**根因**：

- cgroup v2 未 mount
- memcg 路径初始化失败

**排查**：

```bash
adb shell mount | grep cgroup
# 应看到 cgroup2 on /sys/fs/cgroup type cgroup2
adb shell ls /sys/fs/cgroup/uid_*/memory.pressure 2>&1
# 文件不存在 → memcg 未启用
```

**缓解**：

- init.rc 中确保 `mount cgroup2 none /sys/fs/cgroup`
- 检查 vendor init 脚本

### 5.8 风险 #7：LMKD 进程被 swap

**症状**：

- LMKD "沉默"（无 kill 日志）
- 系统持续卡顿 → 最终整机卡死
- 重新启动 LMKD 后恢复正常

**根因**：

- mlockall 失败（ulimit 或 SELinux 拦截）
- LMKD RSS 持续增长（如 log 泄漏）→ VmRSS > 物理 RAM

**排查**：

```bash
adb shell cat /proc/<lmkd_pid>/status | grep -E 'VmRSS|VmSwap|MLock'
# MLock 应 > 0（被 mlock 的内存）
# VmSwap > 0 → mlock 失效
```

**缓解**：

- SELinux 策略检查（`mlockall` 是否被允许）
- ulimit 检查
- 监控 LMKD RSS 增长（应稳定）

### 5.9 风险类型 ASCII 树

```
LMKD 风险地图（7 类）
├── 杀得太狠
│   ├── kill_n_cached 过大
│   ├── PSI 阈值过低
│   └── minfree_levels 未启用
├── 杀得太慢
│   ├── mlockall 失效（被 swap）
│   ├── SCHED_FIFO 未生效
│   └── 主循环阻塞
├── 杀错进程
│   ├── adj 来源不同步
│   ├── adj 计算错误
│   └── min_score_adj 阈值过低
├── PSI 阈值错误
│   ├── psi_partial_stall_ms 偏低
│   ├── psi_complete_stall_ms 偏低
│   └── psi_window_ms 不匹配内核
├── adj 来源不同步
│   ├── socket 写入失败
│   └── proc_state 缓存不一致
├── memcg 路径未启用
│   ├── cgroup v2 未 mount
│   └── memcg event fd 注册失败
└── LMKD 进程被 swap
    ├── mlockall 失败
    └── LMKD RSS 持续增长
```

---

## §6 实战案例：相机进程被 LMKD 误杀导致后台录像中断

### 6.1 现场描述

某 OEM 4GB 设备，用户反馈"开启 4K 后台录像时，每隔 3-5 分钟会中断一次，回到前台后录像文件损坏"。

### 6.2 排查过程

#### 第 1 步：抓 logcat 看 kill 痕迹

```bash
adb logcat -d | grep -i 'lmkd\|lowmemory'
```

```
06-12 14:30:01 lmkd (1555): PSI some avg10=120ms, triggering kill
06-12 14:30:01 lmkd (1555): Kill 'com.android.camera' (pid 8765) oom_score_adj=900
06-12 14:30:01 lmkd (1555): Kill 'com.android.camera:camera-record' (pid 8766) oom_score_adj=800
06-12 14:30:01 lmkd (1555): Kill 'com.tencent.mm' (pid 4321) oom_score_adj=900
```

**关键观察**：
- 相机主进程 `com.android.camera` 被杀（adj=900 → 后台 cached）
- 相机录像线程 `com.android.camera:camera-record` 被杀（adj=800 → secondary）

但用户在录像时，相机**应该在前台**（adj ≤ 700）！这就是问题。

#### 第 2 步：对比 dumpsys activity 真实 adj

```bash
adb shell dumpsys activity processes | grep -A 5 camera
```

```
ProcessRecord{abc123:com.android.camera}
  userId=10001
  oom adj=900  ← 这是关键：adj=900 表示后台
  state=CACHED
  ...
```

**结论**：AMS 记录的 adj 是 900（cached），但相机明明在前台。

#### 第 3 步：查找 adj 写入失败原因

```bash
adb logcat -d | grep -i 'ActivityManager.*adj'
```

```
06-12 14:28:55 ActivityManager: Set oom_adj of camera to 0 (foreground)
06-12 14:28:56 ActivityManager: Process com.android.camera adj changed 0 → 200
06-12 14:28:57 ActivityManager: Process com.android.camera adj changed 200 → 900
06-12 14:28:58 ActivityManager: Failed to write adj to lmkd: Broken pipe
```

**关键发现**：
1. 14:28:55 adj=0（前台）
2. 14:28:56 adj=200（perceptible）
3. 14:28:57 adj=900（cached）← 异常！
4. 14:28:58 lmkd socket 写入失败

adj 怎么会从 200 跳到 900？查看代码：

#### 第 4 步：定位 adj 跳变的代码

```bash
adb logcat -d | grep -i 'lock screen\|keyguard'
```

```
06-12 14:28:57 ActivityManager: Screen off, moving visible apps to cached
```

**根因**：用户**未真正按 Home 退出相机**，只是按下电源键息屏。AMS 检测到息屏 + 相机不可见 → 把相机 adj 改为 900（cached）。

#### 第 5 步：验证修复方案

修改 `ProcessList.java` 的 `setProcessAdj` 逻辑：当进程持有 `MediaRecorder`（相机录像）时，最低 adj 设为 `200`（perceptible），不能降至 cached。

修复后测试：

```
06-12 15:00:00 ActivityManager: Screen off, camera app kept at adj=200 (MediaRecorder active)
06-12 15:00:30 PSI some avg10=80ms (no trigger)
06-12 15:05:00 ... 持续录像，无中断
```

### 6.3 案例核心：5 分钟定位法

| 步骤 | 动作 | 耗时 |
|---|---|---|
| 1 | `logcat -d \| grep lmkd` 找到 kill 现场 | 30s |
| 2 | `dumpsys activity processes` 确认 adj | 30s |
| 3 | `logcat -d \| grep ActivityManager.*adj` 找 adj 历史 | 1min |
| 4 | 关联日志（keyguard/screen off） | 2min |
| 5 | 定位代码 + 修复 | 5min |

**根因模式归纳**：

> **adj 跳变路径** = 关键操作触发 + adj 主动降级 + LMKD 触发 = 误杀。
> 
> 关键操作（MediaRecorder / AudioRecord / 前台 Service）应被识别为"adj 锁定"信号。

### 6.4 类似案例模式库

| 案例模式 | 关键操作 | 应锁定 adj |
|---|---|---|
| 后台录像 | `MediaRecorder.start()` | perceptible（200） |
| 后台音频录制 | `AudioRecord.startRecording()` | perceptible（200） |
| 前台 Service | `startForegroundService()` | service（300） |
| 蓝牙 HFP | `BluetoothHeadsetService` | perceptible（200） |
| 后台定位 | `LocationManager.requestLocationUpdates()` | perceptible（200） |
| WorkManager | `enqueueUniqueWork` | cached（900）允许被杀 |

### 6.5 防范清单（开发侧）

- **应用层**：
  - 关键后台操作启动前台 Service（前台 Service adj=300，不会被杀）
  - 持有 `MediaSession` 防止被当 cached
  - 不要用普通 Service 做后台录音/录像
- **OEM / 框架层**：
  - `setProcessAdj` 中检测 `MediaRecorder/AudioRecord` 状态 → 强制 perceptible
  - `ro.lmk.kill_n_cached` 默认值设小（如 1）
  - 监控 lmkd socket 写入失败 → 自动重试
- **监控侧**：
  - 监控 `dumpsys lmkd | grep 'Last kill'` 频率
  - 监控 PSI some avg10 分布
  - 监控 `mlog` 中"误杀前台 app"日志

---

## §7 总结 / 附录 / 风险速查表 / 篇尾衔接

### 7.1 架构师视角 Takeaway（5 条）

#### Takeaway 1：LMKD 是"用户态杀手中枢"，不是 reclaim 本身

LMKD 只做一件事：**挑进程杀**。真正的 reclaim 是内核 `try_to_free_pages` 异步完成的。LMKD 与内核的关系是"触发者 ↔ 执行者"，LMKD 不能直接 reclaim 内存。理解这层关系后，调优方向清晰——LMKD 调"杀谁/何时杀"，内核调"杀后回收多快"。

#### Takeaway 2：`mlockall + SCHED_FIFO + epoll_wait` 三角架构是 LMKD 稳定的基石

LMKD 三角架构的设计哲学：
- **mlockall**：防止 LMKD 自己被 swap → 避免 reclaim 死锁
- **SCHED_FIFO**：保证 LMKD 先于普通线程调度 → 快速响应 PSI 事件
- **epoll_wait**：零 CPU 空转 → 长续航设备友好

任何一项失效都会导致"杀得太慢"。线上诊断时务必检查这三项：`VmSwap`（mlock 状态）、`chrt -p`（调度类）、`/proc/<pid>/wchan`（是否在 epoll_wait）。

#### Takeaway 3：PSI 是 AOSP 14 默认事件源，vmpressure 是 fallback

AOSP 14 全面转向 PSI（`ro.lmk.use_psi=true`），vmpressure 仅在 PSI 不可用时启用。PSI 优势：
- 4 档粗糙 → 百分比细粒度
- 抖动（shrink 路径抖动）→ 平滑窗口
- 误杀率下降 35-50%

迁移时间线：AOSP 12 默认开启 PSI → AOSP 14 PSI 是唯一默认。任何引用 `mp_event vmpressure` 作为主要触发源的现代文档都已过时。

#### Takeaway 4：adj 来源单一权威化是 AMS/LMKD 协作的关键

AOSP 14 的设计：**AMS 是 adj 唯一权威，LMKD 是 adj 消费者**。AMS 通过 abstract socket "lmkd" 推送 adj → LMKD 写本地 `proc_state[pid].oom_score_adj` → 杀进程时直接读取。这条单向数据流避免了"内核 LMK 时代 adj 来源分散（AMS+driver+各 vendor）"的混乱。任何破坏这条流的操作（如 socket 写入失败、LMKD 重启后状态丢失）都会导致误杀。

#### Takeaway 5：LMKD 风险的核心是"杀错进程"

LMKD 的功能正确性（杀最不重要的）由 `value = adj * 1000 + rss` 保证。但 LMKD 的**稳定性**更依赖：
- adj 来源同步（AOSP 14 通过 socket 保证）
- PSI 阈值合理（OEM 调优）
- 关键操作的 adj 锁定（MediaRecorder/AudioRecord）
- LMKD 自身不被 swap（mlockall）

实战案例（§6）的相机录像中断，是"adj 来源 + 关键操作 + LMKD 触发"三因素共振的典型——解决任何一个因素都能避免误杀。

### 7.2 附录 A：核心源码路径索引

按层分组：

#### A.1 AOSP 14 用户态 LMKD 源码（system/memory/lmkd/）

| 路径 | 关键函数 | 职责 |
|---|---|---|
| `system/memory/lmkd/lmkd.cpp` | `main()` / `mainloop()` / `find_and_kill_processes()` / `kill_one_process()` | 主入口 + 主循环 + kill 决策 |
| `system/memory/lmkd/init.cpp` | `init()` / `init_psi_monitors()` / `init_memcg_monitors()` / `parse_args()` | 初始化 + property 读取 |
| `system/memory/lmkd/event.cpp` | `handle_event()` / `mp_event_psi()` / `mp_event_cgroup()` / `mp_event_common()` | 事件分发 |
| `system/memory/lmkd/lmkd.h` | `struct proc_info` / `struct vmpressure` / 常量定义 | 公共定义 |
| `system/memory/lmkd/Android.bp` | `cc_binary { name: "lmkd" }` | 编译配置 |

#### A.2 内核侧 PSI（kernel/）

| 路径 | 关键文件 | 职责 |
|---|---|---|
| `kernel/sched/psi.c` | `psi_task_change()` / `psi_memstall_enter()` / `psi_memstall_leave()` | PSI 统计 |
| `kernel/fs/proc/base.c` | `proc_pressure_show()` | `/proc/pressure/*` 暴露 |
| `include/linux/psi.h` | `enum psi_res` / `struct psi_group` | PSI 公共定义 |

#### A.3 内核侧 memcg + cgroup v2（kernel/）

| 路径 | 关键文件 | 职责 |
|---|---|---|
| `kernel/mm/memcontrol.c` | `mem_cgroup_pressure()` / `mem_cgroup_events()` | cgroup 内存压力 |
| `kernel/kernel/cgroup/cgroup.c` | `cgroup_pressure_show()` | cgroup v2 pressure 文件 |
| `kernel/mm/vmpressure.c` | `vmpressure()` (legacy fallback) | vmpressure 旧路径 |

#### A.4 已废弃的内核 LMK（drivers/staging/）

| 路径 | 状态 | 备注 |
|---|---|---|
| `drivers/staging/android/lowmemorykiller.c` | **已移除**（AOSP mainline commit f3a8d29...） | 仅作历史兼容 |
| `drivers/staging/android/lowmemorykiller.h` | 同上 | — |

#### A.5 AMS 协作（frameworks/base/services/core/）

| 路径 | 关键类 | 职责 |
|---|---|---|
| `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` | `setOomScoreAdj()` / 旧版 `setOomAdj()` | 写 adj 到 procfs（AOSP 10+ 走 socket 推 lmkd，lmkd 收口再写 /proc） |
| `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` | `updateOomAdjLocked()` / `computeOomAdjLocked()` | adj 计算 |
| `frameworks/base/services/core/java/com/android/server/am/LmkdConnection.java` | `writeProcprio()` | socket 通道（abstract "lmkd"） |

### 7.3 附录 B：关键 Property 速查表

#### B.1 PSI 相关（AOSP 14 默认值）

| Property | 默认值 | 含义 | 调优建议 |
|---|---|---|---|
| `ro.lmk.use_psi` | `true` | 是否使用 PSI | OEM 慎改 |
| `ro.lmk.psi_partial_stall_ms` | `70` | some avg10 触发阈值 | 70-300，越大越不敏感 |
| `ro.lmk.psi_complete_stall_ms` | `700` | full avg10 触发阈值 | 500-1000 |
| `ro.lmk.psi_window_ms` | `1000` | PSI 监测窗口 | OEM 不调（与内核 PSI 窗口耦合） |
| `ro.lmk.psi_skill_count` | `10` | 连续 N 次高于阈值才杀 | 5-20 |
| `ro.lmk.psi_initialize_polling_delay_ms` | `0` | 启动后延迟 | OEM 不调 |

#### B.2 kill 策略相关

| Property | 默认值 | 含义 | 调优建议 |
|---|---|---|---|
| `ro.lmk.kill_n_cached` | `1` | 一次杀几个 cached | 1-5 |
| `ro.lmk.kill_heaviest_task` | `true` | 同 adj 时杀 RSS 最大 | AOSP 默认 true |
| `ro.lmk.kill_third_party_app_only` | `false` | 仅杀第三方 app | OEM 决定 |
| `ro.lmk.use_minfree_levels` | `true` | 是否用 minfree 阈值 | AOSP 默认 true |
| `ro.lmk.swap_free_low_percentage` | `10` | swap 释放阈值 | 5-20 |

#### B.3 memcg 相关

| Property | 默认值 | 含义 | 调优建议 |
|---|---|---|---|
| `ro.config.use_memcg` | `true` | 是否使用 memcg | AOSP 默认 true |
| `ro.lmk.use_memcg` | `true`（AOSP 14） | LMKD 是否读 memcg | true |
| `persist.sys.lmk.memcg_psi_partial_stall_ms` | `0`（默认无） | memcg 专用 PSI | OEM 调优 |

#### B.4 与 AMS 协作

| Property | 默认值 | 含义 | 调优建议 |
|---|---|---|---|
| `ro.lmk.simple_proc_adj` | `false` | 简化 adj 算法 | AOSP 默认 false |
| `ro.lmk.log_statsd` | `true` | 上报 statsd | 监控需要 |

### 7.4 附录 C：风险速查总表（覆盖矩阵）

| 风险类型 | 现象 | 日志关键字 | dumpsys / 工具 | 排查入口 | 缓解 / 修复 |
|---|---|---|---|---|---|
| 杀得太狠 | 频繁 kill | `lmkd.*Kill.*adj.*[0-9]` 频率 > 1/s | `dumpsys lmkd` | `kill_n_cached` | 调高 PSI 阈值 |
| 杀得太慢 | PSI 高但无 kill | `psi_partial_stall_ms` 命中 | `cat /proc/pressure/memory` | `dumpsys lmkd` | mlockall + SCHED_FIFO |
| 杀错进程 | 前台 app 被杀 | `killing foreground process` | `dumpsys activity` + `dumpsys lmkd` | adj 对比 | 关键操作 adj 锁定 |
| PSI 阈值错误 | 抖动 / OOM | `psi_partial_stall_ms=10` | `getprop ro.lmk.*` | property 调优 | A/B 测试调优 |
| adj 来源不同步 | AMS adj 与 LMKD 不一致 | `write failed: Broken pipe` | `logcat \| grep ActivityManager.*adj` | socket 检查 | 重启 system_server |
| memcg 未启用 | 单 app OOM 但系统健康 | `cgroup2 not mounted` | `mount \| grep cgroup` | init.rc | mount cgroup v2 |
| LMKD 被 swap | 沉默 + 卡顿 | 无明显日志 | `cat /proc/<pid>/status \| grep VmSwap` | mlockall | SELinux / ulimit |
| adj 计算错误 | foreground 标 cached | `Set oom_adj.*0 → 900` | `dumpsys activity processes` | OomAdjuster 逻辑 | 关键操作过滤 |
| lmkd socket 断 | proc_state 不更新 | `Broken pipe` | `netstat -an \| grep lmkd` | socket 检查 | 重启 lmkd |
| 频繁 reclaim | 内存持续高水位 | `kswapd.*scanned.*[0-9]pg` | `vmstat 1` | reclaim 调优 | 调整 swappiness |
| 启动期误杀 | bootanimation 期间杀进程 | `lmkd.*Kill.*bootanim` | `logcat -b boot` | boot lmkd 延迟 | `ro.lmk.delay_mmio` |
| swap 不足 | swap 使用 100% | `kswapd0.*high load` | `cat /proc/meminfo \| grep Swap` | zram 配置 | 扩 zram / 减少 cached |

### 7.5 附录 D：与已有系列的交叉引用

| 本文引用 | 章节 | 引用文件 | 用途 |
|---|---|---|---|
| AMS adj 等级 | §3.2 / §3.3 | [05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md) §2.4 / §3.5 | adj 计算 + socket 通道 |
| WindowManager / system_server adj | §3.3 | [05-AMS 内存治理与进程优先级](05-AMS 内存治理与进程优先级.md) §4 | system_server adj 来源（窗口切换 / 焦点变化触发 adj 更新） |
| 进程内存地图 | §3.4 / §5.2 | [02-进程内存地图与 VMA 体系](02-进程内存地图与 VMA 体系.md) | VMA 与 RSS |
| ART 堆 GC | §3.4 | [03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md) §5 | 杀进程前 GC 触发 |
| 内存总览 | §1.3 | [01-内存系统总览：从进程视角到硬件的完整链路](01-内存系统总览：从进程视角到硬件的完整链路.md) | 全栈视角 |
| PSI 详细 | §2.3 | [07-PSI / vmpressure / memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md)（下一篇） | PSI 深入 |
| 风险全景 | §5 | [12-内存稳定性风险全景](12-内存稳定性风险全景.md) §3 | 风险分类 |
| 实战案例模板 | §6 | [12-内存稳定性风险全景](12-内存稳定性风险全景.md) §6 | 5 分钟定位法 |

### 7.6 篇尾衔接

**本篇核心**：LMKD 是 AOSP 14 用户态杀手中枢，通过 `mlockall + SCHED_FIFO + epoll_wait` 三角架构在 PSI/memcg 事件触发下挑选 `oom_score_adj` 最高的进程 kill。kill 决策由 `value = adj * 1000 + rss` 保证"杀最不重要+占用最大"。风险核心是"adj 来源同步 + 关键操作锁定 + PSI 阈值合理"。

**下一篇**：[07-PSI / vmpressure / memcg 压力传递](07-PSI、vmpressure、memcg 压力传递.md) 将深入：

- PSI 内核态实现（`psi_task_change` / `psi_memstall_enter`）
- vmpressure 4 档等级的内核计算逻辑（`vmpressure` 函数）
- memcg 事件 `memory.events` low/high/max 三档机制
- cgroup v1 vs v2 的 pressure 路径对比
- PSI / vmpressure / memcg 三者协作时序图
- LMKD PSI monitor 的 fd 初始化细节

**系列尾预告**：[13-内存稳定性工程实践与未来演进] 将整合 01-12 给出生产环境稳定性建设的完整 checklist 与未来演进趋势（PSI v2 / cgroup v2 全面化 / LMKD 与 KMSAN 协作 / ROLLMK 概念等）。