# cgroup 横切系列：为什么 Process / Memory / IO 都绕不开它

> **本系列基线**:
> - **应用层 / Framework**:`android-17.0.0_r1`(API 37)
> - **Linux 内核**:`android17-6.18` LTS
> - **历史参考**:已发布 Kernel Process/IO/MM 系列基线为 AOSP 14 + android14-5.10/5.15,本系列引用时保留 AOSP 14 标注,**关键差异处单独说明**
>
> **视角**:以 cgroup **自身** 为主模块的横切视角——历史演进、核心抽象、三大资源维度的统一、Android 落地、稳定性中心地位、可观测性收口。
>
> **目标读者**:Android 稳定性 SE、性能工程师、Framework 工程师。
>
> **主线**:cgroup 是什么 → 怎么设计 → 怎么管 Process/Memory/IO → Android 上长什么样 → 在稳定性里处于什么中心地位 → 怎么查 / 怎么治。
>
> **预计体量**:6 篇 × 1.5-2.0 万字 ≈ 10-12 万字。
>
> **写作规范**:遵循 `PROMPT-技术系列文章写作指南-v5.md`(v5 §3 一站式模板 + §10 读者视图规范)

---

## 系列定位

本系列是 **"cgroup 自身为主模块"** 的横切解读，区别于项目里已有的"以其他子系统为主模块、cgroup 是子章节"的 5 个视角：

| 已有视角 | 已有文章 | 主模块 | cgroup 的角色 |
|---|---|---|---|
| Kernel Process 视角 | `01-Mechanism/Kernel/Process/10-cgroup_v2_内核里的资源控制器.md` | 进程 | cgroup 是"被约束"的代表 |
| Kernel IO 视角 | `01-Mechanism/Kernel/IO/04-IO优先级与cgroup-IO控制器.md` | IO | cgroup 是 IO 资源隔离的边界 |
| Kernel MM 视角 | `01-Mechanism/Kernel/Memory_Management/MM_v2/07-PSI、vmpressure、memcg 压力传递.md` | Memory | cgroup 是 memcg 的载体 |
| Framework 视角 | `01-Mechanism/Framework/Process/06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd.md` | Framework 接口 | cgroup fs 是 Framework 的"配置通道" |
| App/Hook 视角 | `01-Mechanism/App/Hook/09-场景2-后台治理-cgroup_freezer与启动拦截.md` | OEM Hook | freezer 是"半杀"工具 |

**本系列的横切视角**：把 cgroup 从"被其他系列瓜分的子模块"，提升为"主模块"——讲它自己的**历史、设计、横向地位、稳定性收口**。

> **判断标准**：
> - 读完后想去看 `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` → 已有 Framework 视角
> - 读完后想去看 `block/blk-cgroup.c` 或 `mm/memcontrol.c` → 已有 Kernel Process/IO/MM 视角
> - 读完后想去看 `kernel/cgroup/cgroup.c` 整体设计 + 为什么 cgroup 能成为中心枢纽 → **本系列**

---

## 6 篇目录

### 阶段 A：起源与设计（2 篇）

| # | 标题 | 核心内容 |
|---|---|---|
| **CG-01** | [cgroup 的诞生与历史演进：从 2006 到 Android 17](01-cgroup的诞生与历史演进_从2006到Android17.md) | 2006 前无 cgroup 的"老问题" → Rohit Seth 入 mainline → v1 时代多 hierarchy → Tejun Heo 主导 v2 重构 → Android 7.0 引入 → Android 11 强制 v2 → v1→v2 关键差异表 |
| **CG-02** | [cgroup 核心抽象：subsys / css / cftype / cgroup_file](02-cgroup核心抽象_subsys_css_cftype_cgroup_file.md) | 4 个核心数据结构的设计意图 → 用户态写 memory.max 的完整调用链 → "为什么这样设计"而非"怎么实现" |

### 阶段 B：横向统一（1 篇，系列核心）

| # | 标题 | 核心内容 |
|---|---|---|
| **CG-03** | [cgroup 三大资源维度的统一抽象：Process / Memory / IO](03-cgroup三大资源维度的统一抽象_Process_Memory_IO.md) | **本系列核心篇**——同一个 cgroup 怎么同时管 CPU/Memory/IO → 三个子系统的接口差异（page_counter / task_group / blkcg）→ 共同模式（限额 + 优先级 + 事件统计）→ 把已有 5 视角拉成一张图 |

### 阶段 C：Android 落地（1 篇）

| # | 标题 | 核心内容 |
|---|---|---|
| **CG-04** | [Android 17 cgroup 树与 libprocessgroup：Framework 怎么用 cgroup](04-Android17_cgroup树与libprocessgroup.md) | 完整 cgroup 树（top-app / background / foreground / system / dexopt）→ libprocessgroup API → ProcessList.setProcessGroup 全栈路径 → task profile + cgroup.procs 配合 |

### 阶段 D：稳定性收口（2 篇）

| # | 标题 | 核心内容 |
|---|---|---|
| **CG-05** | [cgroup 与稳定性的核心关系：OOM / Throttle / 杀进程的源头](05-cgroup与稳定性的核心关系_OOM_Throttle_杀进程.md) | 三个层 OOM 优先级（LMKD → cgroup OOM → 系统 OOM）→ cgroup throttle vs 调度器 throttle → freezer 暂停 vs 杀进程 → Android 17 典型配置 |
| **CG-06** | [cgroup 可观测性全景 + 风险地图（实战收口）](06-cgroup可观测性全景与风险地图_实战收口.md) | 5 类可观测性入口速查 → 5 大 cgroup 故障（OOM 误杀 / CPU throttle / IO 抢断 / freezer 卡住 / cpuset 错配）→ 5 分钟排查 SOP → 3 个完整实战案例 |

---

## 整体结构图

```
主线：cgroup 是什么 → 怎么设计 → 怎么管三资源 → Android 17 长什么样 → 稳定性里什么地位 → 怎么查怎么治
                              │
                              ▼
       ┌─ 阶段 A：起源与设计（拿到地图）──┐
       │  CG-01 历史演进（2006→Android 17）│
       │  CG-02 核心抽象（4 个数据结构）    │
       └──────────────┬──────────────────┘
                      ▼
       ┌─ 阶段 B：横向统一（系列核心）──┐
       │  CG-03 三大资源维度统一抽象       │  ← 真正回答"为什么 cgroup 是中心"
       └──────────────┬──────────────────┘
                      ▼
       ┌─ 阶段 C：Android 落地 ──┐
       │  CG-04 cgroup 树 + libprocessgroup │
       └──────────────┬───────────┘
                      ▼
       ┌─ 阶段 D：稳定性收口 ──┐
       │  CG-05 OOM/Throttle/杀进程 │
       │  CG-06 可观测性 + 风险地图 │  ← 看 / 查 / 治
       └──────────────────────┘
```

---

## 系列"主线 + 承上启下"

```
CG-01：cgroup 怎么来的
  ↓ 钩子：有了 cgroup 之后，内核怎么设计它？
CG-02：4 个核心抽象
  ↓ 钩子：有了抽象之后，它怎么同时管 CPU/Memory/IO？
CG-03：三大资源维度的统一抽象（系列核心）
  ↓ 钩子：抽象设计很完美，Android 上具体长什么样？
CG-04：Android 17 cgroup 树 + libprocessgroup
  ↓ 钩子：Android 上跑起来了，对稳定性意味着什么？
CG-05：cgroup 在稳定性里的中心地位
  ↓ 钩子：理解完地位，怎么落地排查？
CG-06：可观测性 + 风险地图（收口）
```

---

## 模块关系总图

```
                            Framework 层
┌─────────────────────────────────────────────────────────────┐
│  ActivityManagerService │ ProcessList │ OomAdjuster │ lmkd  │
│  libprocessgroup │ Process.setProcessGroup │ task profile  │
└──────────────────────────────┬──────────────────────────────┘
                               │ 写 /sys/fs/cgroup/.../cgroup.procs
                               │ 写 cpu.uclamp.{min,max}
                               │ 读 memory.current / memory.events
                               ▼
┌──────────────────────────────────────────────────────────────┐
│            本系列覆盖范围：cgroup 自身横切                       │
│  cgroup_subsys │ cgroup_subsys_state │ cftype │ cgroup_file  │
│       ↓                ↓                ↓             ↓      │
│  memory / cpu / io / freezer / cpuset / pids / devices        │
│  + PSI / vmpressure / memcg pressure                         │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
      Process 子系统       Memory 子系统       IO 子系统
     task_group 调度      mem_cgroup /         blkcg /
     + cpuset.cpus        page_counter         io.weight
     + cpu.max / uclamp   + memory.events      + io.max
            │                  │                  │
            └──────────────────┼──────────────────┘
                               ▼
                    Linux Kernel 进程 + 资源管理
```

---

## 与已有 cgroup 5 视角的边界声明（必读）

> **本节是本系列与项目里已有 5 个 cgroup 视角的"分工契约"——同主题不同视角，不要混读。**

| 主题 | Kernel Process 视角 | Kernel IO 视角 | Kernel MM 视角 | Framework 视角 | App Hook 视角 | **本系列** |
|---|---|---|---|---|---|---|
| cgroup v2 起源 | 10 §1-§2 简提 | — | — | — | — | **CG-01 详讲** |
| subsys / css / cftype | 10 §3-§5 实现 | IO 04 §6 blkcg 视角 | — | 06 §4 写接口视角 | — | **CG-02 设计意图** |
| memory 子系统 | 10 §5 概述 | — | 07 §3-§4 memcg pressure | 06 §4.3 memory.high | — | **CG-03 §3.2 统一抽象** |
| cpu 子系统 | 10 §6 + Process 09 cpuset | — | — | 06 §4.1 uclamp | — | **CG-03 §3.1 统一抽象** |
| io 子系统 | — | IO 04 §6-§7 全讲 | — | 06 §4.4 仅提 | — | **CG-03 §3.3 统一抽象** |
| freezer | 10 §7 简提 | — | — | — | Hook 09 §4 全讲 OEM | **CG-05 §3 治理视角** |
| Android 17 cgroup 树 | 10 §10 概览 | — | — | 06 §4 cgroup fs 写入 | — | **CG-04 完整树** |
| libprocessgroup | 10 §13 简提 | — | — | 06 §4 写接口 | — | **CG-04 桥接视角** |
| 与 OOM 关系 | 10 §11 简提 | — | 07 §4 LMKD 三角 | — | — | **CG-05 详细三 OOM 优先级** |
| 与稳定性排查 | 10 §12 简提 | IO 04 §10-§13 实战 | 07 §6 风险 | 06 §3.5/§4.5/§5.4/§8 8 类故障 | Hook 09 §7 案例 | **CG-06 5 大故障 SOP** |

**关键判断**：
- 读完后想去看 `block/blk-cgroup.c` 的 IO throttle 算法 → 已有 Kernel IO 视角
- 读完后想去看 `mm/memcontrol.c` 的 memcg pressure 钩子 → 已有 Kernel MM 视角
- 读完后想去看 `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` → 已有 Framework 视角
- **读完后想理解"cgroup 为什么能成为中心枢纽、横跨 Process/IO/MM 三大资源"→ 本系列**

---

## 学习路径建议

### 方式 1：系统学习（1-2 周）
按 CG-01 → CG-06 顺序读，每篇都跑示例命令。建议路径：
1. **Day 1-2**（起源）：CG-01（历史）+ CG-02（设计）
2. **Day 3-5**（核心）：CG-03（横切统一）—— 反复读 2 遍
3. **Day 6-7**（落地）：CG-04（Android 17 树）
4. **Day 8-10**（收口）：CG-05（稳定性地位）+ CG-06（可观测性 SOP）

### 方式 2：主题速查（1-2 天）

| 想了解 | 跳到 |
|---|---|
| cgroup 怎么来的 / v1 vs v2 怎么选 | CG-01 |
| subsys / css / cftype 怎么设计 | CG-02 |
| cgroup 怎么同时管 CPU/Memory/IO | CG-03 |
| Android 17 上 cgroup 长什么样 | CG-04 |
| OOM 误杀 / CPU 卡顿 / IO 抢断的 cgroup 根因 | CG-05 |
| 5 分钟定位 cgroup 故障 | CG-06 |

### 方式 3：问题驱动（1-2 小时）
遇到线上稳定性问题：
1. 看 CG-06 §5 的 5 大故障速查表定位故障类型
2. 跳到对应章节（OOM 误杀 → CG-05 §1；CPU throttle → CG-05 §2；IO 抢断 → CG-03 §3.3 + CG-05 §3；freezer 卡住 → CG-05 §3）
3. 跑 CG-06 §4 的排查命令
4. 看 CG-06 §5 的完整实战案例

---

## 系列特点

### 1. 横向串联，不重复造轮
本系列**不重写**已有 5 个视角的 cgroup 章节，而是：
- 把它们的素材拉成一张"cgroup 中心图"
- 补充它们没讲的（历史演进 / 横向统一 / Android 17 完整树 / 稳定性中心地位 / SOP）
- 明确"想看 cgroup 在 X 子系统细节，参见 [已有文章]"

### 2. 稳定性视角贯穿
每篇都明确回答"这和我排查线上问题有什么关系"：
- CG-01：v1 时代的"多 mount 难管理"如何在线上出故障
- CG-02：subsys 注册错怎么导致整组策略失效
- CG-03：三个子系统的接口差异如何影响排查
- CG-04：进程被切到错 cgroup 的稳定性后果
- CG-05：5 大稳定性故障的 cgroup 根因
- CG-06：5 分钟排查 SOP

### 3. 实战导向
每篇都有 Android 17 上的真实命令，可以立即跑：
- `adb shell cat /sys/fs/cgroup/top-app.slice/cpu.max`
- `adb shell cat /proc/<pid>/cgroup`
- `adb shell cat /sys/fs/cgroup/<cgroup>/memory.events`

### 4. 与已有 5 视角互补

| 系列 | cgroup 在该系列的角色 | 本系列的对应补强 |
|---|---|---|
| Kernel Process | cgroup 是"被约束"的代表（10 §3-§7） | CG-02 讲"为什么这样设计" |
| Kernel IO | cgroup 是 IO 隔离边界（IO 04 §6） | CG-03 §3.3 拉成三资源统一图 |
| Kernel MM | cgroup 是 memcg 载体（MM 07 §3） | CG-05 §2 讲 PSI vs cgroup OOM 关系 |
| Framework | cgroup fs 是写接口（06 §4） | CG-04 讲完整 Android 17 树 |
| App/Hook | freezer 是 OEM 工具（Hook 09 §4） | CG-05 §3 讲 freezer 在稳定性里的边界 |

---

## 与已有系列的关系

| 系列 | 关系 | 交互点 |
|---|---|---|
| `Linux_Kernel/Process` | 横向联动 | CG-02 §2 引用 Process 10 §3-§5；CG-05 §1 引用 Process 10 §11 |
| `Linux_Kernel/IO` | 横向联动 | CG-03 §3.3 引用 IO 04 §6-§7；CG-05 §2 引用 IO 04 §11 案例 |
| `Linux_Kernel/Memory_Management` | 横向联动 | CG-03 §3.2 引用 MM 07 §3；CG-05 §2 引用 MM 07 §4 LMKD 三角 |
| `Android_Framework/Process` | 横向联动 | CG-04 引用 Framework 06 §4 cgroup fs 写入路径 |
| `Android_App/Hook` | 横向联动 | CG-05 §3 引用 App Hook 09 §4 freezer OEM 实现 |
| `Android_Framework/AMS` | 平级交叉 | CG-04 §3 展开 ProcessList.setProcessGroup |

---

## 参考资源

### 内核文档
- `Documentation/admin-guide/cgroup-v2.rst` —— cgroup v2 官方文档（必读）
- `Documentation/cgroup-v1/` —— cgroup v1 文档（历史参考）
- `Documentation/scheduler/sched-design-CFS.rst` —— CFS 与 cgroup 关系

### 内核源码
- `kernel/cgroup/cgroup.c` —— cgroup 核心
- `kernel/cgroup/freezer.c` —— freezer 子系统
- `kernel/cgroup/legacy_freezer.c` —— v1 freezer
- `mm/memcontrol.c` / `include/linux/memcontrol.h` —— memory 子系统
- `kernel/sched/core.c` —— cpu 子系统
- `block/blk-cgroup.c` / `block/blk-throttle.c` —— io 子系统（v1 兼容）
- `block/blk-iocost.c` —— io 子系统（v2 成本控制）

### Android 源码
- `system/core/libprocessgroup/` —— cgroup 桥接库
- `frameworks/base/services/core/java/com/android/server/am/ProcessList.java` —— ProcessList 主类
- `frameworks/base/services/core/java/com/android/server/am/OomAdjuster.java` —— adj 决策
- `system/memory/lmkd/lmkd.cpp` —— lmkd 主程序
- `frameworks/base/services/core/java/com/android/server/am/lmkscore.h` —— adj 阈值计算

### 调试工具
- `kernel/cgroup/cgroup-v2.cp` —— cgroup bpf 程序支持
- BPF / bpftrace —— cgroup 性能分析
- perfetto —— cgroup 调度事件 track

### 关键 commit（按时间）
- `ec8d2429` "cgroup: convert to kernfs"（v1→v2 重构起点，2014）
- `5af7df7` "cgroup: introduce css_set and cgroup_subsys_state"（css 抽象）
- `e7f1bae5` "psi: cgroups v2: enable psi for cgroups"（5.2 cgroup v2 PSI 支持）
- `7e381c0e` "cgroup: cgroup v2 freezer"（freezer v2 迁移）

---

## 更新记录
- **2026-07-20**：系列启动（CG-01 待写）

---

## 系列总结

```
6 篇 + 4 个阶段 + 1 条主线 = cgroup 横切系列完整解读

主线：
  起源 → 设计 → 横切统一 → Android 落地 → 稳定性地位 → 可观测性收口

4 个阶段：
  A 起源与设计（CG-01 + CG-02）         — 拿到地图
  B 横向统一（CG-03）                   — 回答"为什么 cgroup 是中心"
  C Android 落地（CG-04）              — 看 Android 17 长什么样
  D 稳定性收口（CG-05 + CG-06）         — 排查 / 治理 / SOP

总字数：约 10-12 万字
目标读者：Android 稳定性 SE / 性能工程师 / Framework 工程师
与已有 5 视角的关系：横向串联 + 中心地位视角，不重复造轮
```

---

## 引用（系列）

| 引用 | 路径 |
|---|---|
| 系列原文 | `01-Mechanism/Kernel/cgroup/01-...md` ~ `06-...md` |
| Kernel Process 视角 | `01-Mechanism/Kernel/Process/10-cgroup_v2_内核里的资源控制器.md` |
| Kernel IO 视角 | `01-Mechanism/Kernel/IO/04-IO优先级与cgroup-IO控制器.md` |
| Kernel MM 视角 | `01-Mechanism/Kernel/Memory_Management/MM_v2/07-PSI、vmpressure、memcg 压力传递.md` |
| Framework 视角 | `01-Mechanism/Framework/Process/06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd.md` |
| App Hook 视角 | `01-Mechanism/App/Hook/09-场景2-后台治理-cgroup_freezer与启动拦截.md` |
| 实战 SOP | CG-06 §4 排查命令 + §5 完整案例 |
