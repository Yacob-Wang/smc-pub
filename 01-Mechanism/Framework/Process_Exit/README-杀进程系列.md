# 杀进程全链路系列：4 篇理论 + 1 篇实战

> **系列定位**：补 Process 系列的"杀进程"主题。Process 主序列 (01-08) 讲进程诞生 + 调度 + 治理；09 实战讲具体 case。但 **杀进程本身的理论没有系统讲**：从 AMS 决定杀进程后做了什么、Kernel 收到信号后做了什么、do_exit 内部 9 个 sub-step 各自怎么走、什么才是真正会让杀进程卡住的根因。这些问题在 Process 09 里塞不下，必须开新系列。
>
> **源码基线**：AOSP `android-16.0.0_r1` + Kernel `android16-6.6` GKI 2.0
> **目录位置**：`Android_Framework/Process_Exit/`

---

## 为什么要写这个系列

**线上 P0 故障的 30%+ 都跟"杀进程"相关**：

- 应用卡死 / ANR → LMKD / Watchdog 杀
- 内存不足 → OOM Killer / cgroup 触发杀
- 桌面 Clear All → AMS 遍历 task 杀
- Native crash → debuggerd / RuntimeInit KillApplication
- 用户 force stop / 卸载 → AMS.killApplicationProcess
- 进程冻屏 / 启动超时 → AMS refused to die + am_wtf

但**杀进程从来不是单一事件**——它是 FWK 上半部（AMS 决策）+ FWK 下半部（信号发送）+ Kernel 中段（do_exit 9 sub-step）+ Kernel 收尾（cgroup/reaper）+ FWK 收尾（handleAppDied）**5 个阶段 × 4 个层栈**的协作。

**每个阶段都有自己独立的耗时区间、独立的影响因素、独立的可观测标志**。把它们混在一起讲（比如"杀进程慢"），就会出现 Process 09 里出现的问题：
- "exit_mm 10s" 这个结论没有 kernel log 精确测量做依据
- "swap 55% 是根因" 这种说法经不起反证（高 swap 使用率场景多了，但卡 10s+ 的极少）
- "5 栏对账" 表里每个数字都是拍脑袋，互相循环引用

**本系列目标**：把杀进程拆成 4 篇**独立、可验证、有源码依据**的理论深潜，让你能回答：
1. 从 AMS 决定杀进程到进程完全退出，每一步具体做什么？（01）
2. do_exit 内部 9 个 sub-step 每个的真实耗时范围、变慢的真正条件？（02）
3. 哪些因素是诱因、哪些是根因、如何用 ftrace 证伪？（03）
4. 怎么建监控、怎么治理？（04）

---

## 4 篇理论 + 1 篇实战 完整架构

```
┌────────────────────────────────────────────────────────────┐
│  杀进程监控与治理（04 篇）                                   │
│  ftrace 抓取 / Perfetto / 告警阈值 / 治理清单                 │
│  + Process 09 实战                                          │
└────────────┬───────────────────────────────────────────────┘
             ↑
┌────────────┴───────────────────────────────────────────────┐
│  杀进程慢的根因（03 篇）                                      │
│  诱因 vs 根因 / 6 大根因 / 证伪方法 / 反例                    │
└────────────┬───────────────────────────────────────────────┘
             ↑
┌────────────┴───────────────────────────────────────────────┐
│  do_exit 内部深潜（02 篇）                                    │
│  9 个 sub-step 源码 / 每个 sub-step 的耗时 / 影响因素           │
└────────────┬───────────────────────────────────────────────┘
             ↑
┌────────────┴───────────────────────────────────────────────┐
│  杀进程全链路开篇（01 篇）                                     │
│  5 阶段 × 4 层栈 / 7 类触发源 / 时序图 / 跨篇索引              │
└────────────────────────────────────────────────────────────┘
```

---

## 第一篇：杀进程全链路开篇

### [01-杀进程全链路：从 AMS 触发到进程完全退出](01-杀进程全链路：从AMS触发到进程完全退出.md)

| 章节 | 内容 | 核心源码路径 |
| --- | --- | --- |
| **1. 全景图：5 阶段 × 4 层栈** | 杀进程不是单一事件，是多阶段多层栈的协作 | 整体 |
| **2. 阶段 1：触发源 7 类** | am_kill / lmkd / OOM / native crash / Watchdog / force stop / refused to die | 多个 |
| **3. 阶段 2：AMS 决策** | killPackageProcessesLocked + PidfdProcess.killProcess 源码 | `frameworks/base/services/...am/ProcessList.java` |
| **4. 阶段 3：信号发送** | pidfd_send_signal / kill_pid_info 源码 + pidfd vs PID 路径 | `frameworks/native/libs/binder/PidfdCache.cpp` |
| **5. 阶段 4：Kernel 信号投递 + do_group_exit** | siginfo 构造 + dequeue_signal + do_signal + do_group_exit | `kernel/signal.c` |
| **6. 阶段 5：do_exit 9 个 sub-step 概览** | exit_signals / exit_mm / exit_files / ... / schedule() | `kernel/exit.c` |
| **7. 阶段 6：资源回收** | release_task / cgroup_release / reaper | `kernel/exit.c` + `kernel/cgroup/cgroup.c` |
| **8. 阶段 7：FWK 收尾** | handleAppDied + cleanUpApplicationRecordLocked | `ActivityManagerService.java` |
| **9. 时序图 + 耗时典型值** | 5 阶段时序 + 每阶段典型 ms 级范围 | — |
| **10. 慢的真正条件 + 反证** | 哪些是诱因、哪些是根因、如何用 ftrace 证伪 | — |
| **11. ftrace 抓取 + 测速方法** | 完整命令集（沿用 09 §6.7.3） | `kernel/trace/` |
| **12. 跨篇索引** | → 02/03/04 + Process 09 实战 | — |

**本篇产出**：杀进程全链路的**理论总表**。看完整篇，能在脑子里画出"AMS 决定杀进程 → ... → 进程完全退出"的完整路径，每个节点知道有什么、做什么、典型多快。

---

## 第二篇：do_exit 内部深潜

### [02-do_exit 内部 9 个 sub-step 深潜](02-do_exit内部9个sub-step深潜.md)

**本篇核心问题**：do_exit 9 个 sub-step **每个**的真实耗时范围、变慢的真正条件、kernel log 怎么观测。

| 章节 | 内容 | 核心源码路径 |
| --- | --- | --- |
| **1. do_exit 9 个 sub-step 总表** | sub-step / 理想耗时 / 实测方法 / 变慢的真正条件 | `kernel/exit.c` |
| **2. ① exit_signals 深潜** | 通知父进程 SIGCHLD 源码 + 耗时 | `kernel/exit.c#exit_signals` |
| **3. ② exit_mm 深潜** | exit_mmap / unmap_vmas / unmap_page_range / swap_free 完整代码路径 + 每个 sub-sub-step 耗时 | `mm/mmap.c` + `mm/memory.c` + `mm/swapfile.c` |
| **4. ③ exit_files 深潜** | close_files / filp_close / fput 完整代码路径 + 慢 FS / 网络 FIN 慢在哪 | `fs/file.c` |
| **5. ④ exit_fs / ⑤ exit_thread / ⑥ exit_namespaces / ⑦ exit_task_stack 深潜** | 元数据释放细节 | 多个 |
| **6. ⑧ sched_set_group_id / ⑨ sched_dead / schedule() 深潜** | 调度器协同 | `kernel/sched/core.c` |
| **7. ftrace 测速方法（按 9 个 sub-step）** | 每个 sub-step 对应的 ftrace 事件 + 测速公式 | — |
| **8. 真实 case 复现（基于 Process 09）** | 用 ftrace 实测 9 个 sub-step 各自的精确耗时 | — |

**本篇产出**：**do_exit 内部 9 个 sub-step 的可验证理论**。看完整篇，能回答"任何 sub-step 慢在哪、怎么测、变慢需要什么条件"。

---

## 第三篇：杀进程慢的真正根因

### [03-杀进程慢的真正根因：诱因、根因、证伪](03-杀进程慢的真正根因：诱因-根因-证伪.md)

**本篇核心问题**：哪些因素是诱因（必要条件）、哪些是根因（充分条件）、如何用 ftrace 实测证伪。

| 章节 | 内容 | 核心源码路径 |
| --- | --- | --- |
| **1. 诱因 vs 根因的判定标准** | 4 条判定规则（重现性 / 充分性 / 必要性 / 可证伪） | — |
| **2. 网上 6 大"伪根因"的证伪** | swap 55% / rss 大 / 进程多 / zRAM 高 / 系统 MemFree 低 / 单 app 复杂逻辑 — 每个都拆 | — |
| **3. 真正根因 3 类的判定** | **A. vma 状态异常**（mmap 预回收） / **B. fd 关闭慢**（慢 FS / GPU flush）/ **C. 资源回收拥堵**（cgroup 锁 / reaper 排队） | 多个 |
| **4. 每个真正根因的 case 复现** | 用真实 case 证明每个根因都能独立触发 10s+ | 多个 |
| **5. 证伪方法（ftrace + 反例）** | 怎么用反例证伪"swap 55% 是根因"这种说法 | — |
| **6. 根因 → 治理映射** | 找到根因后怎么治理 | — |

**本篇产出**：**判别"诱因 / 根因"的思维框架**。看完整篇，能在线上 case 中快速区分"哪些是表面因素、哪些是真正要修复的"。

---

## 第四篇：杀进程监控与治理

### [04-杀进程监控与治理：ftrace / Perfetto / 告警 / 治理](04-杀进程监控与治理：ftrace-perfetto-告警-治理.md)

**本篇核心问题**：杀进程相关的监控怎么建、告警阈值怎么定、治理怎么落地。

| 章节 | 内容 | 核心源码路径 |
| --- | --- | --- |
| **1. 监控的 3 个层次** | **L1 FWK 事件**（am_kill / am_proc_died 间隔）/ **L2 Kernel 事件**（sched_process_exit / mm_page_free 速率）/ **L3 系统指标**（MemFree / Swap / PSI） | 多个 |
| **2. 告警阈值设计** | 杀进程 1s / 5s / 10s 的判定 + 历史趋势 | — |
| **3. 治理的 4 大方向** | (a) 减少触发次数 / (b) 加速单次杀进程 / (c) 缓存现场 / (d) 告警闭环 | 多个 |
| **4. perfetto 实战配置** | 完整 pbtxt（含 ftrace / process_memory / process_stats） | — |
| **5. 治理清单** | 8 类治理动作 + 风险 + ROI | — |
| **6. 治理反例** | 6 类治理反例（无效治理 / 反向治理） | — |

**本篇产出**：**杀进程监控 + 治理的工程落地手册**。看完整篇，能在自己的设备上建完整的告警 + 治理体系。

---

## 实战：Process 09

### [Process 09-杀进程慢的根因定位实战](../Process/09-杀进程慢的根因定位实战.md)

- **定位**：基于 TECNO KM9 / Android 16 / HiOS 16.3.0 真实 case 的 12.2s 黑屏分析
- **与 4 篇理论的关系**：
  - 触发源：Clear All 触发 `dismissAllTasks` → `removeTask` → `am_kill`（→ 01 §2）
  - AMS 决策：`killPackageProcessesLocked` 源码（→ 01 §3）
  - 信号发送：`pidfd_send_signal` 19.658（→ 01 §4）
  - do_exit 9 sub-step：10s 集中在 exit_mm（→ 02 §3）
  - 真正根因：vma 状态异常（mmap 预回收伏笔）（→ 03 §3）
  - ftrace 抓取：未开（案发 kernel log 缺失）（→ 01 §11）

**09 实战的价值**：
- 把 4 篇理论应用到真实 case
- 暴露"5 栏对账表"数字无证据的问题（已被用户识别）
- 引出第 3 篇"哪些是诱因、哪些是根因"的核心问题

---

## 4 篇之间的关系

| 关联 | 方向 | 关键问题 |
|---|---|---|
| 01 → 02 | 总表 → 深潜 | 01 §6 概览 do_exit 9 sub-step，02 §1-6 逐个深潜 |
| 02 → 03 | 机制 → 判定 | 02 讲每个 sub-step 怎么慢，03 讲"哪些慢才是真正根因" |
| 03 → 04 | 根因 → 治理 | 03 找到根因后，04 讲怎么监控 + 治理 |
| 01-04 → 09 实战 | 理论 → 应用 | 09 是 4 篇理论在 TECNO KM9 / Android 16 上的真实应用 |

---

## 阅读建议

### 如果你时间有限

1. **01** 全链路开篇（建立全景图）
2. **03** 真正根因（学会判定"诱因 vs 根因"）
3. **09** 实战（看 4 篇理论在真实 case 中的应用）

### 如果你要系统学习

按 01 → 02 → 03 → 04 → 09 顺序

### 如果你要快速定位线上问题

直接看 03 §3 真正根因 3 类判定 + 04 §1-2 监控 + 告警

---

## 进度

- [x] **Step 0**：系列 README + 4 篇架构设计 — 2026-07-20（本轮）
- [ ] **Step 1**：01 骨架（让你过架构）— 2026-07-20
- [ ] **Step 2**：01 完整内容（验收后）
- [ ] **Step 3**：02 do_exit 9 sub-step 深潜
- [ ] **Step 4**：03 真正根因 + 证伪
- [ ] **Step 5**：04 监控与治理
- [ ] **Step 6**：Process 09 实战重写（基于新理论框架）

---

## 与 Process 系列的边界

| 系列 | 主题 | 杀进程相关内容 |
|---|---|---|
| **Process 01-08** | 进程诞生 / 调度 / 治理 | 01 §0.3 杀进程是终点；06 §5 pidfd；08 §X 杀进程在 10 大故障的位置 |
| **Process 09** | 杀进程慢的根因定位实战 | 实战 case |
| **Process_Exit 01-04** | 杀进程全链路理论 | **本系列——理论深潜** |

**本系列不重复 Process 01-08 内容**，专注杀进程全链路的深度理论，Process 09 作为应用 case 存在。

---

## 篇尾衔接

- **往前**：[Process 系列 README](../Process/README-进程架构演进系列.md)
- **往后**：本系列 02/03/04 篇（待写）
- **实战**：[Process 09 杀进程慢的根因定位实战](../Process/09-杀进程慢的根因定位实战.md)
