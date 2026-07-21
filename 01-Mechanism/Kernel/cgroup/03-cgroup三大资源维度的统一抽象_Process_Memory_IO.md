<!-- AUTHOR_ONLY:START -->

# 本篇定位

- **本篇系列角色**：阶段 B 第 1 篇——**本系列核心篇**。cgroup 横切系列的第 3 篇。
- **强依赖**：
  - [CG-01 cgroup 的诞生与历史演进](01-cgroup的诞生与历史演进_从2006到Android17.md)（必读，知道 v1/v2 差异）
  - [CG-02 cgroup 核心抽象：subsys / css / cftype / cgroup_file](02-cgroup核心抽象_subsys_css_cftype_cgroup_file.md)（必读，知道 4 个核心抽象的分工）
- **承接自**：CG-02 讲 4 个核心抽象；本篇用这 4 个抽象论证"cgroup 为什么能成为中心枢纽"
- **衔接去**：
  - [CG-04 Android17 cgroup 树与 libprocessgroup](04-Android17_cgroup树与libprocessgroup.md) —— 抽象在 Android 17 上怎么落地
  - [CG-05 cgroup 与稳定性的核心关系：OOM/Throttle/杀进程](05-cgroup与稳定性的核心关系_OOM_Throttle_杀进程.md) —— 抽象在稳定性里的具体表现
- **不重复内容**：
  - memory subsystem 实现细节 → [Kernel MM 07 §3-§4](../Memory_Management/MM_v2/07-PSI、vmpressure、memcg压力传递.md)（**基线 AOSP 14**） + [Process 10 §5](../Process/10-cgroup_v2_内核里的资源控制器.md)
  - cpu subsystem 实现细节 → [Process 10 §6 + 09 §7 UClamp/cpuset](../Process/10-cgroup_v2_内核里的资源控制器.md)
  - io subsystem 实现细节 → [Kernel IO 04 §6-§7](../IO/04-IO优先级与cgroup-IO控制器.md)（**基线 AOSP 14**） + [Process 10 §9]
  - **本篇讲"3 个抽象的统一性"(设计模式视角)**——不重复子系统的具体实现

# 校准决策日志

| 轮次 | 类别 | 决策 | 理由 | 影响范围 |
|------|------|------|------|----------|
| 1 | 结构 | 不破例，按 v5 §3 标准 8 章 | 本篇是"系列核心篇"，必须完整而非简化 | 仅本篇 |
| 1 | 结构 | §1 抛出"3 大资源维度统一性"作为系列核心问题 | 锚定系列主线——本篇回答"为什么 cgroup 是中心" | §1-§8 全篇 |
| 2 | 硬伤 | 严格分工：memory 细节走 MM 07、cpu 细节走 Process 10、io 细节走 IO 04 | README §"与已有 5 视角的边界声明" | 全文 8 处引用 |
| 2 | 硬伤 | 引用 MM 07 / IO 04 / Process 10 时显式标注"基线 AOSP 14" | 已有 Kernel 系列基线与本系列不同 | 全文 |
| 3 | 锐度 | §1.3 共同模式"限额 + 优先级 + 事件统计"贯穿全文 | 锚定分析框架——3 个 subsystem 共同遵循 | §2-§6 |
| 3 | 锐度 | §5 拉成一张图作为本篇核心交付物 | 反例 #11（数据堆砌）防御——对比表必须服务洞察 | §5 |

# 角色设定

我是一名 **Android 稳定性架构师**，正在系统学习 cgroup 子系统。本篇是 cgroup 横切系列的第 3 篇（**本系列核心篇**），主题是 **cgroup 三大资源维度的统一抽象**——论证 cgroup 为什么能同时管 CPU / Memory / IO。

# 上下文

- 上一篇：[CG-02 cgroup 核心抽象](02-cgroup核心抽象_subsys_css_cftype_cgroup_file.md) 已讲 4 个核心抽象（subsys / css / cftype / cgroup_file）的设计意图
- 下一篇：[CG-04 Android17 cgroup 树与 libprocessgroup](04-Android17_cgroup树与libprocessgroup.md) 将用本篇的"统一性"看 Android 17 上 cgroup 怎么落地
- 本系列 README：[README-cgroup系列.md](README-cgroup系列.md)

# 写作标准

## 硬性要求（v5 §3）
1. 目标读者：资深架构师。不需要解释"什么是 mem_cgroup""什么是 cfs_rq"，但需要解释"为什么 3 个抽象有共同模式"
2. 每个章节先讲"这个维度的设计意图 + 与其他维度的对比"，再深入具体抽象
3. 涉及源码时：AOSP 17 + android17-6.18 基线；引用已有 AOSP 14 文章时显式标注
4. 每个技术点必须关联到"为什么 cgroup 能成为中心枢纽"这个核心问题
5. 量化描述：必须给具体数字 + 来源
6. 长度：1.8-2.0 万字

## 章节结构（v5 §3 标准 8 章）
- §1 背景与定义：3 大资源维度的统一性问题
- §2 memory 维度：mem_cgroup / page_counter
- §3 cpu 维度：task_group / cfs_rq
- §4 io 维度：blkcg / blk-throttle
- §5 共同模式分析：限额 + 优先级 + 事件统计（本篇核心章节）
- §6 横切视角总览：把已有 5 视角拉成一张图
- §7 实战案例：3 个 subsystem 协同问题
- §8 总结 + 附录 A/B/C/D

## 图表格式
- 核心图：3 个 subsystem 的对比表（§5）+ 横切视角总览图（§6）
- 关系图：3 个 subsystem 与 4 个核心抽象的关系图

## 图表密度
- 标准 4-6 张 ASCII 图
- 核心图：3 个 subsystem 的限额 / 优先级 / 事件统计对比表

## 跨模块引用规范
- 涉及本系列其他篇：用 Markdown 链接
- 涉及已有 Kernel Process 10 / IO 04 / MM 07：标注"基线 AOSP 14"，只概述"它在讲什么"
- 涉及项目其他系列：用相对路径

## 禁止事项
1. 禁止挖坑不填（每个共同模式必须在 §5 兑现）
2. 禁止数据堆砌（每个数字后必须有"所以呢"）
3. 禁止 AI 自嗨（"非常精妙""体现了……深度融合"→ 删）
4. 禁止模糊量化（"通常""大约"→ 给具体数字 + 来源）
5. 禁止跨篇重复（已在 Process 10 / IO 04 / MM 07 讲过的细节，本系列只引用不展开）

<!-- AUTHOR_ONLY:END -->

# cgroup 三大资源维度的统一抽象：Process / Memory / IO

> 系列第 3 篇 · 阶段 B · 系列核心篇
>
> **承上**：[CG-02](02-cgroup核心抽象_subsys_css_cftype_cgroup_file.md) 讲了 cgroup 的 4 个核心抽象（subsys / css / cftype / cgroup_file）。本篇用这 4 个抽象论证 **"cgroup 为什么能成为中心枢纽"**——3 大资源维度的统一抽象。
>
> **启下**：抽象在 Android 17 上怎么落地？下篇 [CG-04](04-Android17_cgroup树与libprocessgroup.md) 展开。
>
> **预计篇幅**：约 1.9 万字
>
> **基线声明**：
> - 应用层 / Framework：`android-17.0.0_r1`（API 37）
> - Linux 内核：`android17-6.18` LTS
> - 已有 Kernel Process 10 / IO 04 / MM 07 等文章基线为 AOSP 14 + android14-5.10/5.15，本篇**讲统一性**(不重复具体实现)，**引用时显式标注差异**

---

## 学习目标

读完本篇，你应该能：

1. **画出 cgroup 3 大资源维度的对比表**（memory / cpu / io 的限额 / 优先级 / 事件统计）
2. **解释"为什么 3 个 subsystem 有共同模式"**——而不是"碰巧长得像"
3. **跟踪同一 cgroup 同时管 3 资源的完整路径**（如 top-app.slice 同时含 memory/css + cpu/css + io/css）
4. **理解 cgroup 作为"中心枢纽"的具体含义**——3 个 subsystem 各自有自己数据结构，但都通过 4 个核心抽象（CG-02）协作
5. **把已有 5 视角（Process 10 / IO 04 / MM 07 / Framework 06 / App Hook 09）拉成一张图**——本系列核心交付物
6. **识别 3 个 subsystem 协同的稳定性风险**（如 cpu 限额耗尽触发 memcg high）

---

## §1 背景与定义

### 1.1 核心问题：cgroup 为什么能成为"中心枢纽"？

读完 [CG-01](01-cgroup的诞生与历史演进_从2006到Android17.md) 和 [CG-02](02-cgroup核心抽象_subsys_css_cftype_cgroup_file.md)，我们知道：
- cgroup 解决了 3 个核心问题：**限额 / 隔离 / 统计**（CG-01 §1.3）
- cgroup 通过 4 个核心抽象实现：**subsys / css / cftype / cgroup_file**（CG-02 §1.2）

但还有一个根本性问题没回答：**cgroup 怎么同时管 3 大资源（CPU / Memory / IO）？**

```
场景：top-app.slice 这个 cgroup 节点
  - memory.max = max（前台不限内存）
  - cpu.max = max 100000（前台不限 CPU）
  - io.weight = 200（前台 IO 权重高）
  - 同时含 3 个资源维度的配置

问题：3 个资源完全独立（CPU 是调度器、Memory 是页分配器、IO 是块设备）
     cgroup 怎么把它们"统一"在同一个 cgroup 节点下？
```

**答案在 CG-02 讲过的 4 个抽象**：
- `cgroup_subsys` 让 3 个 subsystem 各自注册
- `cgroup_subsys_state (css)` 让 1 个 cgroup 节点在 3 个 subsystem 下各有 1 个状态对象
- `cftype` 让 3 个 subsystem 各自暴露文件系统接口
- `cgroup_file` 让运行时 read/write 高效

**4 个抽象的协作让 cgroup 成了"中心枢纽"**——本篇深入论证这一点。

### 1.2 3 大资源维度的关系图

```
                top-app.slice/                    ← 同一个 cgroup 节点
                    │
                    ├──── 6 个 css（每个 subsystem 1 个）：
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
   memory/css   cpu/css    io/css
   (→ mem_cgroup) (→ task_group) (→ blkcg)
        │           │           │
        │           │           │
   mm/memcontrol.c   kernel/sched/   block/blk-cgroup.c
        │           │           │
        ▼           ▼           ▼
   page_counter   cfs_rq       throtl_data
   (memory.max)   (cpu.max)    (io.max)
        │           │           │
        └───────────┴───────────┘
                    │
                    ▼
            page_alloc / sched / bio
         (实际生效点：分配 / 调度 / 提交)
```

**关键洞察**：
- 1 个 cgroup 节点 = 1 个 kernfs 目录
- 1 个 cgroup 节点 = 6 个 css（v2 时代 6 个 subsystem：cpu/memory/io/freezer/cpuset/pids）
- 6 个 css 通过 `container_of` 各自拿到自己的 subsystem 私有数据
- 6 个 subsystem 私有数据**完全独立**——但都通过同一棵 cgroup 树组织

**所以"统一"的不是数据结构，而是"组织方式"**——6 个完全独立的数据结构，被组织在同一棵 cgroup 树下。

### 1.3 共同模式：限额 + 优先级 + 事件统计

虽然 3 个 subsystem 各自的数据结构完全不同（mem_cgroup / task_group / blkcg），但它们**都遵循 3 个共同模式**：

**模式 1：限额（Limits）**

| 资源 | 限额字段 | 限额单位 | 触发行为 |
|---|---|---|---|
| memory | `memory.max` / `memory.high` | 字节 | 超额 → reclaim / OOM |
| cpu | `cpu.max`（quota / period） | 微秒 | 超额 → throttle |
| io | `io.max`（rbps / wbps / riops / wiops） | 字节 / IO 数 | 超额 → throttle |
| pids | `pids.max` | 进程数 | 超额 → fork 失败 |
| cpuset | `cpuset.cpus` | CPU 位图 | 不在范围 → 不可调度 |
| freezer | `cgroup.freeze` | 0/1 | frozen → task 暂停 |

**模式 2：优先级（Priority）**

| 资源 | 优先级字段 | 优先级语义 | 调度依据 |
|---|---|---|---|
| memory | `memory.low`（保护）/ `memory.high`（软限） | "保护 vs 让出" | reclaim 时优先保 memory.low |
| cpu | `cpu.weight`（CFS 权重）/ `cpu.uclamp.min/max`（UClamp） | "组内优先级 + 最少保证" | CFS 调度权重 + UClamp |
| io | `io.weight`（bfq 权重） | "bfq 调度权重" | bfq 调度时按 weight 比例 |
| cpuset | `cpuset.cpus.partition`（root/member/isolated） | "独占 / 可借用 / 完全隔离" | EAS 调度范围 |

**模式 3：事件统计（Accounting）**

| 资源 | 统计文件 | 统计内容 | 消费方 |
|---|---|---|---|
| memory | `memory.current` / `memory.events` / `memory.stat` | 当前用量 + 事件计数 + 详细分类 | LMKD / dumpsys meminfo / 监控 |
| cpu | `cpu.stat`（usage_usec / nr_throttled / throttled_usec） | CPU 时间 + throttle 计数 | lmkd / ProcessCpuTracker / 监控 |
| io | `io.stat`（rbytes / wbytes / rios / wios）+ `io.pressure` | IO 字节 + IO 次数 + PSI | lmkd / 监控 |
| pids | `pids.current` | 当前进程数 | 监控 |

**关键洞察**：
- 3 个模式在 3 个 subsystem 上**都成立**——这是"共同模式"的具体表现
- 共同模式不是"碰巧长得像"——是 cgroup framework **设计**成这样
- 共同模式让用户态能用**统一的方式**配置 3 个资源（`echo 100M > memory.max` / `echo 50000 100000 > cpu.max` / `echo "8:0 rbps=100M" > io.max`）

**为什么是这 3 个模式**？后续 §5 深入分析。

### 1.4 与已有视角的边界声明

> **本节是"边界声明"——避免和已有 5 视角重复。**

| 维度 | 已有视角（基线 AOSP 14） | 本篇（基线 AOSP 17） |
|---|---|---|
| memory 详细实现 | [Kernel MM 07 §3-§4](../Memory_Management/MM_v2/07-PSI、vmpressure、memcg压力传递.md) 详讲 memcg pressure 钩子 | 本篇 §2 讲 mem_cgroup 的"统一抽象"角色，不重复 memcg pressure 细节 |
| cpu 详细实现 | [Kernel Process 10 §6 + 09 §7 UClamp/cpuset](../Process/10-cgroup_v2_内核里的资源控制器.md) 详讲 cfs_rq / UClamp | 本篇 §3 讲 task_group 的"统一抽象"角色，不重复 cfs_rq 实现 |
| io 详细实现 | [Kernel IO 04 §6-§7](../IO/04-IO优先级与cgroup-IO控制器.md) 详讲 blk-throttle / blk-iolatency | 本篇 §4 讲 blkcg 的"统一抽象"角色，不重复 blk-throttle 算法 |
| Framework 接口 | [Framework 06 §4 cgroup fs 写入路径](../Framework/Process/06-Framework视角的Kernel进程接口_procfs_cgroup_pidfd.md) 详讲 cgroup.procs / cpu.uclamp.min 写入 | 本篇 §5-§6 讲 Framework 与 3 个 subsystem 的协作模式，不重复写入路径 |
| OEM Hook 视角 | [App Hook 09 §4 freezer OEM 实现](../App/Hook/09-场景2-后台治理-cgroup_freezer与启动拦截.md) | 本篇 §5 提 freezer 在"统一抽象"中的位置 |

**判断标准**：
- 读完后想去看 `mem_cgroup_attach` 的代码 → 已有 MM 07
- 读完后想去看 `cfs_rq` 的红黑树操作 → 已有 Process 10
- 读完后想去看 `blk_throtl_bio` 的 throttle 算法 → 已有 IO 04
- **读完后想理解"为什么 cgroup 能同时管 3 个资源" → 本篇**

### 1.5 本篇主线与组织方式

```
§1 背景与定义：3 大资源维度的统一性问题
  ├─ §1.1 核心问题
  ├─ §1.2 3 大资源维度关系图
  ├─ §1.3 共同模式
  └─ §1.4 边界声明
  ↓ 钩子：3 个模式都成立——但 3 个 subsystem 各自怎么实现？
§2 memory 维度：mem_cgroup / page_counter
  ↓ 钩子：memory 实现了 3 个模式——cpu 呢？
§3 cpu 维度：task_group / cfs_rq
  ↓ 钩子：cpu 也实现了 3 个模式——io 呢？
§4 io 维度：blkcg / blk-throttle
  ↓ 钩子：3 个维度都实现 3 个模式——为什么？
§5 共同模式分析：限额 + 优先级 + 事件统计（本篇核心）
  ├─ §5.1 为什么是这 3 个模式
  ├─ §5.2 共同模式的边界
  └─ §5.3 共同模式的源码统一性
  ↓ 钩子：3 个维度统一了——已有 5 视角怎么拉成一张图？
§6 横切视角总览：把已有 5 视角拉成一张图
  ↓ 钩子：3 个维度协同会出什么稳定性问题？
§7 实战案例：3 个 subsystem 协同
§8 总结
```

---

> **本文档为第 1 批写入,已完成作者前言 5 段 + §1 背景与定义。**
> **剩余批次**:
> - 第 2 批:§2 memory 维度 + §3 cpu 维度 + §4 io 维度
> - 第 3 批:§5 共同模式分析 + §6 横切视角总览 + §7 实战案例 + §8 总结 + 附录 A/B/C/D + 篇尾衔接
