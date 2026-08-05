# 卷 4　诊断方法论与稳定性症状

> **本卷定位**：**全书主战场**。先建立通用的调查方法论（第 22 章），再按「影响范围递增」展开 8 大症状。每章结构统一：机制 → 检测 → 现场采集 → 调查方法 → 典型故障 → 治理。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 22 章 | 稳定性调查方法论 | 🚧 撰写中 |
| 第 23 章 | ANR 深度 | 🚧 撰写中 |
| 第 24 章 | Java 异常 | 🚧 撰写中 |
| 第 25 章 | Native 异常 | 🚧 撰写中 |
| 第 26 章 | 内存与 OOM | 📋 待撰写 |
| 第 27 章 | 系统无响应（SWT / Watchdog） | 🚧 撰写中 |
| 第 28 章 | HANG 与死锁 | 🚧 撰写中 |
| 第 29 章 | Kernel Exception | 🚧 撰写中 |
| 第 30 章 | REBOOT | 🚧 撰写中 |

---

## 章节详细

### 第 22 章　稳定性调查方法论

> **本卷总纲**，也是全书方法论的核心。超越具体工具，建立可复用的调查框架。放在症状章之前，因为后续 8 章都是它的具体应用。

- 22.1 问题分类学：从现象到症状族的第一次收敛
- 22.2 现场采集原则：什么必须第一时间抓、什么可以事后补
- 22.3 假设驱动 vs 数据驱动：两种调查模式的适用边界
- 22.4 根因分析方法：5 Why / 鱼骨图 / 故障树 / 诱因-根因-证伪
- 22.5 从根因到修复：最小修复 / 测试覆盖 / 灰度验证
- 22.6 复盘与沉淀：Postmortem / 知识库 / Runbook

**本章小结**：方法论比工具更决定结论质量——同样的 trace，方法不同，得出的根因可以差十万八千里。

### 第 23 章　ANR 深度

> 最高频的稳定性问题——input / broadcast / service / ContentProvider 四类 ANR 全解。

- 23.1 四类 ANR 的触发条件与超时阈值
- 23.2 ANR 检测机制：InputDispatcher / AMS / Watchdog 各自的判定
- 23.3 现场采集：trace.txt / am_anr / data/anr / DropBox
- 23.4 ANR trace 判读：主线程状态 / Binder 等待 / 锁持有链
- 23.5 三大根因族：主线程阻塞 / Binder 阻塞 / 死锁
- 23.6 ANR 治理：线上监控、阈值告警、防御性设计

**本章小结**：ANR 的根因永远不在 input / broadcast 本身——真正的问题是「主线程为什么没能及时返回」。

### 第 24 章　Java 异常

> App 层最常见的崩溃——机制简单但治理复杂。

- 24.1 异常分类：NPE / ClassCast / ConcurrentModification / OOM
- 24.2 崩溃捕获链路：UncaughtExceptionHandler → AMS → DropBox
- 24.3 堆栈判读与混淆还原
- 24.4 启动期崩溃的特殊性：现场少、复现难
- 24.5 第三方库异常的定位与止损
- 24.6 Java Crash 监控体系与崩溃率治理

**本章小结**：约 90% 的 Java 异常集中在空指针、状态错乱与第三方库兼容性三类。

### 第 25 章　Native 异常

> 最难诊断的崩溃——信号、Tombstone、符号化三关缺一不可。

- 25.1 信号机制：SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL
- 25.2 debuggerd 与 Tombstone 生成链路
- 25.3 Tombstone 判读：寄存器 / 栈回溯 / 内存映射
- 25.4 符号化：addr2line / ndk-stack / 符号表管理
- 25.5 内存错误检测：AddressSanitizer / HWASan / GWP-ASan / MTE
- 25.6 Native Crash 上报与治理

**本章小结**：约 80% 的 Native 崩溃是内存问题——踩栈、use-after-free、double-free 三类占绝大多数。

### 第 26 章　内存与 OOM

> 内存不足引发的症状族。内存**机制**见卷 3 第 15 章，本章讲**症状的识别与调查**。

- 26.1 内存症状全景：Java OOM / Native 分配失败 / LMK 杀进程 / GC 抖动
- 26.2 Java OOM：堆溢出 / 大对象 / Bitmap / 线程数超限
- 26.3 Native 内存增长与泄漏
- 26.4 进程被杀：LMK 判定链路与「优先级误配」型误杀
- 26.5 内存压力的连锁反应：GC 抖动 → 掉帧 → ANR
- 26.6 内存类问题的现场采集与水位治理

**本章小结**：内存症状很少直接暴露——它通常伪装成卡顿、ANR 或「应用莫名被杀」。

### 第 27 章　系统无响应（SWT / Watchdog）

> 系统级不响应——Watchdog 是 Android 的应急医生，也是最后一道防线。

- 27.1 Watchdog 架构：Java Watchdog / 内核 watchdog / watchdogd
- 27.2 超时判定：30s 主线程 / 60s 总体 / 各监控线程
- 27.3 卡死 vs 慢：slow operation 阈值与误报
- 27.4 现场保留：Watchdog 触发时抓什么
- 27.5 调查方法：栈采样 / Handler 采样 / 锁分析
- 27.6 SWT 治理与防御

**本章小结**：SWT 的根因约 90% 是 SystemServer 内部某个服务卡死——找到那个服务比分析 Watchdog 本身重要得多。

### 第 28 章　HANG 与死锁

> 最难复现的问题——死锁类型、检测手段与恢复策略。

- 28.1 死锁类型：自死锁 / 互锁 / 活锁 / 饥饿 / 锁顺序反转
- 28.2 Java 侧锁分析：线程 dump 与 monitor 归属
- 28.3 Native 侧锁分析：futex / pthread mutex
- 28.4 内核侧：lockdep / hung_task
- 28.5 活锁与 CPU 跑满但无响应
- 28.6 恢复策略：超时 / Watchdog / 强制重启

**本章小结**：死锁必须「线程 dump + 锁顺序」双向验证——只看其中一个容易得出错误的根因。

### 第 29 章　Kernel Exception

> 内核层异常——panic / Oops / BUG / WARN / hung_task。它既是独立症状，也是下一章 REBOOT 的主要原因。

- 29.1 Kernel panic：触发条件与分析流程
- 29.2 Oops 与 BUG：模块缺陷的典型形式
- 29.3 WARN：内核告警与「未致命但危险」信号
- 29.4 hung_task / RCU stall / softlockup
- 29.5 内核日志现场：pstore / ramoops / console-ramoops
- 29.6 内核问题的调查与厂商协同

**本章小结**：内核异常必须有 last_kmsg 或 pstore，否则基本无法定位——现场保留机制要在出问题**之前**配好。

### 第 30 章　REBOOT

> 影响最严重的症状——整机重启。本章负责**分类与归因**，具体内核根因见上一章。

- 30.1 重启分类：kernel panic / native restart / 异常掉电 / 用户主动
- 30.2 重启归因决策树：从重启栈快速分流
- 30.3 native restart：Watchdog 触发的系统重启
- 30.4 异常掉电：欠压 / 硬件异常 / 电源管理
- 30.5 重启现场：last_kmsg / pstore / ramoops / bootloader 日志
- 30.6 重启率治理：监控、分级告警、止血

**本章小结**：重启栈是唯一能回答「为什么重启」的证据——保不住现场，一切分析都是猜测。
