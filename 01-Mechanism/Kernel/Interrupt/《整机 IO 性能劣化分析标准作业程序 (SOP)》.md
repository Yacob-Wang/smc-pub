这是一个为你深度定制的 **《整机 IO 性能劣化分析标准作业程序 (SOP)》**。

这份文档不仅仅是操作指南，更是一套**从内核原理出发的分析方法论**。它遵循你要求的逻辑：先定义“看什么”（维度），再决定“怎么测”（场景）和“怎么抓”（工具），最后“怎么算”（分析）。

---

# 整机 IO 性能劣化分析 SOP (Standard Operating Procedure)

## 一、 分析维度定义 (Dimensions)
*在设计测试之前，必须明确我们要分析的四个层级。IO 不仅仅是磁盘读写，更是文件系统到硬件的漫长旅程。*

### 1. 应用感知层 (User Experience)
*   **核心指标**：应用处于 **D 状态 (Uninterruptible Sleep)** 的总时长。
*   **意义**：用户只关心应用卡不卡。如果 IO 很快，但锁竞争导致 D 状态很久，也是 IO 子系统的锅。

### 2. VFS 与缓存层 (Filesystem & PageCache)
*   **核心指标**：Page Cache 命中率、`ext4/f2fs` 锁耗时。
*   **关键点**：区分 **Logical IO** (应用发起的) 与 **Physical IO** (落盘的)。
    *   如果 Logical IO 变多但 Physical IO 没变 -> 说明应用变了，不是系统劣化。
    *   如果 Logical IO 没变但 Physical IO 变多 -> 说明 Page Cache 失效或内存回收机制劣化。

### 3. 块设备层 (Block Layer)
*   **核心指标**：IO 调度延迟 (Queue to Issue)、IO 合并率 (Merge Rate)。
*   **意义**：检测 IO 调度器 (CFQ/BFQ/MQ-Deadline) 是否配置不当或负载过高。

### 4. 驱动与中断层 (Driver & SoftIRQ)
*   **核心指标**：硬件物理延迟 (D2C)、软件中断回调延迟 (C2B)、SoftIRQ CPU 占用率。
*   **意义**：检测磁盘硬件老化、驱动 Bug 或 CPU 调度导致的“软中断借用”卡顿。

---

## 二、 负载场景设计 (Workload Design)
*为了对比两个版本，变量必须受控。我们采用“合成测试”+“模拟真机”双轨制。*

### 1. 基准压力测试 (Baseline Micro-benchmarks)
*目标：测出系统 IO 的物理极限和纯净环境下的调度开销。*
*   **工具**：`fio` (必须使用静态编译版本 push 到机器)。
*   **场景 A (随机读写)**：模拟数据库/应用日常操作。
    *   `fio --name=rand_rw --rw=randrw --rwmixread=70 --bs=4k --ioengine=libaio --iodepth=32 --numjobs=4`
*   **场景 B (重度 fsync)**：模拟应用安装、数据库提交。
    *   `fio --name=sync_test --rw=write --bs=4k --fsync=1`
*   **检查点**：对比两个版本的 IOPS、Lat (avg/p99)。

### 2. 模拟真机业务测试 (Real-world Simulation)
*目标：引入文件系统锁、内存压力和 CPU 抢占的复杂环境。*
*   **工具**：自定义脚本或 App（推荐 Shell 脚本循环操作）。
*   **场景 C (冷启动风暴)**：
    *   *操作*：`echo 3 > /proc/sys/vm/drop_caches` (清空缓存) -> 启动大型应用 (如游戏/微信) -> 记录启动时间。
    *   *目的*：强制触发大量**读盘 (Read Miss)**，检测 Read Ahead (预读) 机制和磁盘读性能。
*   **场景 D (应用安装/SQLite 写入)**：
    *   *操作*：后台解压一个大 ZIP 包，同时前台运行一个简单的滑动列表 Demo。
    *   *目的*：检测**写压力**下的前台流畅度，观察 SoftIRQ 是否挤占前台 UI 线程。

---

## 三、 数据捕获 SOP (Data Capture)
*抛弃简单的 top，我们需要精确到微秒的 trace。*

### 1. 抓取工具配置 (Perfetto / Systrace)
必须开启以下 Tag/Events，缺一不可：

*   **Scheduler (调度类)**: `sched_switch`, `sched_wakeup`, `sched_waking` (分析线程被谁唤醒，被谁抢占)。
*   **Block IO (块设备类)**: `block_rq_issue`, `block_rq_complete`, `block_bio_queue`, `block_bio_complete` (分析 IO 生命周期)。
*   **File System (文件系统类)**: `ext4_readpage`, `ext4_write_begin`, `ext4_da_write_begin`, `f2fs_...` (分析 VFS 耗时)。
*   **Page Cache (缓存类)**: `mm_filemap_add_to_page_cache`, `mm_filemap_delete_from_page_cache` (分析缓存命中)。
*   **IRQ (中断类)**: `irq_handler_entry/exit`, `softirq_entry/exit` (分析中断耗时)。
*   **Workqueue**: `workqueue_execute_start/end` (分析 kworker 行为)。

### 2. 辅助数据 (快照类)
在 Trace 抓取期间，每隔 1秒 记录一次：
*   `/proc/diskstats`: 获取宏观的 IO 吞吐量和平均队列长度。
*   `/proc/meminfo`: 监控 Dirty Page (脏页) 数量，判断回写压力。

---

## 四、 数据分析与归因 SOP (Analysis Methodology)
*这是最核心的部分，请按照以下“漏斗模型”编写分析脚本或人工审查。*

### 步骤 1：全景过滤 (Macro Filter)
*   **操作**：在 Trace 中找到你的测试进程（如 `fio` 或 `com.tencent.mm`）。
*   **判断**：查看该进程的 `state`。
    *   如果是 **Running** 状态久：CPU 瓶颈，非 IO 问题。
    *   如果是 **Runnable (Preempted)** 状态久：CPU 调度问题，被抢占。
    *   如果是 **Uninterruptible Sleep (D)** 状态久：**进入 IO 深度分析流程。**

### 步骤 2：IO 生命周期拆解 (Micro Breakdown)
*针对每一个导致进程进入 D 状态的 IO 请求，计算以下四个阶段耗时。若发现某阶段在“新版本”中显著增加，即为根本原因。*

| 阶段代码 | 起止事件 | 含义 | 劣化可能原因 |
| :--- | :--- | :--- | :--- |
| **P1 (VFS)** | syscall_entry -> bio_queue | **文件系统层** | 锁竞争 (inode lock)、内存分配慢、创建 BIO 慢。 |
| **P2 (Sch)** | bio_queue -> rq_issue | **IO 调度层** | IO 调度器配置变更、请求合并逻辑变重、队列堵塞。 |
| **P3 (H/W)** | rq_issue -> rq_complete | **硬件物理层** | 驱动版本问题、UFS 固件问题、GC 触发、电源管理 (LPM) 唤醒慢。 |
| **P4 (IRQ)** | rq_complete -> bio_complete | **软中断回调** | **重点关注**。CPU 负载高、SoftIRQ 锁竞争、加密/校验逻辑耗时。 |

### 步骤 3：Page Cache 穿透分析
*   **现象**：应用发起读取，但没有对应的 `block_bio_queue`。
*   **分析**：
    *   检查 `ext4_readpage` 是否快速返回。如果是，说明命中了 Cache (Good)。
    *   对比两个版本：如果旧版本 Cache 命中率 90%，新版本只有 50%，说明新版本的内存回收策略太激进，导致**缓存抖动 (Thrashing)**，进而引发物理 IO 暴增。

### 步骤 4：上下文借用 (Context Borrowing) 分析
*   **针对你关心的 SoftIRQ 问题**。
*   **操作**：在 Trace 中筛选 `softirq_entry (BLOCK)` 事件。
*   **检查**：
    1.  **宿主分析**：查看 SoftIRQ 是运行在 `ksoftirqd` 线程中，还是“寄生”在 app 线程中？
    2.  **耗时对比**：统计 SoftIRQ 的平均执行时长。如果从 50us 涨到了 200us，说明 IO 完成后的回调逻辑（如 dm-verity 校验）变重了。
    3.  **抢占影响**：如果前台 App 频繁运行 SoftIRQ（且不是它自己的 IO），说明系统不仅 IO 慢，还因为处理 IO 拖慢了 UI 渲染。

---

## 五、 报告输出模板 (Reporting)

你的最终报告应包含以下章节，用数据说话：

1.  **结论摘要**：
    *   "版本 B 相比 版本 A，冷启动 IO 耗时增加 15%，主要劣化点在于 **P4 (软中断回调)** 阶段。"

2.  **宏观对比 (Histogram)**：
    *   绘制 IO 延迟分布直方图。展示 P99 延迟是否出现长尾。

3.  **分层归因图谱**：
    *   **VFS 层耗时**：Avg A vs B
    *   **Block 调度耗时**：Avg A vs B
    *   **Disk 物理耗时**：Avg A vs B (排除硬件差异)
    *   **SoftIRQ 耗时**：Avg A vs B (**关键证据**)

4.  **异常 Case 抓拍**：
    *   贴出 Trace 截图，展示一次典型的“慢 IO”。
    *   例如：“在 1989.11s，PID 2566 被 block_bio_queue 阻塞，物理 IO 耗时仅 1ms，但 SoftIRQ 等待 CPU 调度花费了 10ms，导致总 D 状态 11ms。”

---

### 给你的执行建议 (Actionable Advice)

1.  **脚本化**：不要每次都人工看 Trace。编写 Python 脚本解析 `ftrace` 文本。
    *   脚本逻辑：建立 `Dictionary`，以 `Device + Sector` 为 Key，记录 `Queue` 时间，匹配 `Complete` 时间，计算差值，最后输出 CSV。
2.  **控制变量**：确保两个版本的测试机是**同一台机器**（排除闪存体质差异），且测试前都执行 `fstrim`。
3.  **关注 CPU**：IO 慢往往不是 IO 的问题，而是 CPU 忙不过来处理 IO 中断。分析 IO 时一定要并行看 CPU 频率和负载。