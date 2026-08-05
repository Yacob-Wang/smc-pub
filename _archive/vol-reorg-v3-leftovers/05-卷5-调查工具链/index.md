# 卷 5　调查工具链

> **本卷定位**：**工具手册，不必通读**。按需查阅，每章独立自足。卷 4 各症状章会精确指向本卷对应章节。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 31 章 | Perfetto 全栈使用 | 🚧 撰写中 |
| 第 32 章 | Systrace 与 ftrace | 📋 待撰写 |
| 第 33 章 | Dumpsys / Bugreport / DropBox | 🚧 撰写中 |
| 第 34 章 | Hprof 与内存分析 | 🚧 撰写中 |
| 第 35 章 | 断点与 Native 调试 | 🚧 撰写中 |
| 第 36 章 | Oncall 与应急响应 | 🚧 撰写中 |

---

## 章节详细

### 第 31 章　Perfetto 全栈使用

> AOSP 17 的默认 tracing 工具——本卷第一优先级，必须掌握。

- 31.1 Perfetto 架构：Producer / Consumer / traced
- 31.2 抓取实战：ftrace / atrace / heap profiler / 配置模板
- 31.3 trace 判读：UI 操作 / Trace Processor SQL
- 31.4 场景实战：ANR / 启动 / 掉帧 / 内存
- 31.5 高级用法：自定义事件 / 长时抓取 / 自动触发
- 31.6 与 Systrace 的差异与迁移

**本章小结**：Perfetto 是 AOSP 17 稳定性调查的默认入口——不会 SQL 查询就只用到了它三成能力。

### 第 32 章　Systrace 与 ftrace

> 传统但仍必要的工具——分析历史 trace 与内核事件时不可替代。

- 32.1 ftrace 子系统：function / graph / event / probe
- 32.2 关键 tracepoint 速查
- 32.3 atrace 用户态埋点
- 32.4 Systrace 原理与 systrace.py
- 32.5 自定义埋点与内核探针
- 32.6 实战场景与数据量控制

**本章小结**：ftrace 是 Perfetto 的数据来源——理解 ftrace 才能解释 Perfetto 里看到的现象。

### 第 33 章　Dumpsys / Bugreport / DropBox

> 日常排查三件套——状态查询、现场打包、日志归档。

- 33.1 dumpsys 全景：30+ 子系统与关键字段
- 33.2 各视角速查：AMS / WMS / Input / Power / Package / Storage
- 33.3 bugreport 结构与解析路径
- 33.4 DropBox 机制与日志归档策略
- 33.5 在各类症状调查中的应用组合
- 33.6 自动化采集与 CI 集成

**本章小结**：dumpsys + bugreport + DropBox 是稳定性工程师的听诊器——90% 的线上问题从这里起步。

### 第 34 章　Hprof 与内存分析

> 内存问题的 X 光机——堆快照、泄漏定位、Native 内存。

- 34.1 Hprof 格式与生成方式
- 34.2 堆分析：MAT / Android Studio Profiler
- 34.3 GC Roots 与引用链分析
- 34.4 LeakCanary 原理与自动化检测
- 34.5 Native 内存：malloc debug / heapprofd / MTE
- 34.6 内存监控体系搭建

**本章小结**：Hprof 能告诉你「谁在占内存」，但回答「为什么没释放」要靠引用链——后者才是修复依据。

### 第 35 章　断点与 Native 调试

> 终极武器——前面所有手段都失效时才用。

- 35.1 Java 断点：Android Studio / JDWP / 条件断点
- 35.2 Native 调试：lldb / gdb / ndk-gdb
- 35.3 反汇编与符号：objdump / readelf / addr2line
- 35.4 core dump 采集与离线分析
- 35.5 远程调试与真机限制
- 35.6 调试技巧与常见陷阱

**本章小结**：断点调试成本最高、副作用最大——用它之前先确认日志与 trace 真的走到头了。

### 第 36 章　Oncall 与应急响应

> 从个人救火到团队能力——流程、分级、协同、沉淀。

- 36.1 Oncall 制度与轮值设计
- 36.2 故障分级与响应 SLA：P0-P3
- 36.3 应急处置：止血优先于定位
- 36.4 八大症状的响应剧本（Runbook）
- 36.5 跨团队协同：Kernel / Framework / App / 厂商
- 36.6 复盘机制与知识沉淀

**本章小结**：Oncall 的价值不是修得快，而是把个人经验固化成团队可复用的剧本。
