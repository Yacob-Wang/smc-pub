# 卷 5　调查方法论与工具链

> **本卷定位**：怎么找问题——方法论 + 工具。稳定性工程师的瑞士军刀。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 30 章 | 稳定性调查方法论 | 🚧 撰写中 |
| 第 31 章 | Perfetto 全栈使用 | 🚧 撰写中 |
| 第 32 章 | Systrace 与 ftrace | 🚧 撰写中 |
| 第 33 章 | Dumpsys / Bugreport / DropBox | 🚧 撰写中 |
| 第 34 章 | Hprof 与内存分析 | 🚧 撰写中 |
| 第 35 章 | 断点与 Native 调试 | 🚧 撰写中 |
| 第 36 章 | Oncall 与应急响应 | 🚧 撰写中 |

---

## 章节目录（详细）

### 第 30 章　稳定性调查方法论

- 30.1 现象采集：用户反馈 / 监控告警 / 自动化测试
- 30.2 现场保留：bugreport / logcat / 复现路径
- 30.3 假设驱动 vs 数据驱动调查
- 30.4 根因分析：5 Why / Fishbone / Fault Tree
- 30.5 修复与回归：最小修复 / 测试覆盖 / 灰度
- 30.6 复盘文化：Postmortem / 知识库 / Runbook

> **本章小结**：方法论比工具更重要——同样的工具，方法不同结论差 10 倍。

### 第 31 章　Perfetto 全栈使用

- 31.1 Perfetto 架构：Producer / Consumer / daemon
- 31.2 抓 trace 实战：ftrace / atrace / heap / memory
- 31.3 trace 解析：SQL / UI / ftrace_decoder
- 31.4 实战：ANR 30s trace / 启动 trace / 滑动卡顿 trace
- 31.5 Perfetto 高级用法：自定义事件 / 远程抓取 / 在线分析
- 31.6 与 Systrace 的差异

> **本章小结**：Perfetto 是 AOSP 17 默认工具——必须掌握。

### 第 32 章　Systrace 与 ftrace

- 32.1 Systrace 原理
- 32.2 ftrace 子系统：function / graph / event / probe
- 32.3 atrace 用户态埋点
- 32.4 kernel tracepoints
- 32.5 systrace.py 工具链
- 32.6 实战场景

> **本章小结**：Systrace 在 AOSP 17 仍有用——分析老 trace 时必备。

### 第 33 章　Dumpsys / Bugreport / DropBox

- 33.1 dumpsys 子系统全集（30+ 个）
- 33.2 bugreport 抓取与解析
- 33.3 dropbox 机制与日志归档
- 33.4 Oncall 工具链集成
- 33.5 dumpsys 在稳定性调查中的应用
- 33.6 自动化 bugreport 与告警

> **本章小结**：dumpsys + bugreport + dropbox 是稳定性工程师的听诊器。

### 第 34 章　Hprof 与内存分析

- 34.1 Hprof 格式与生成
- 34.2 内存泄漏分析：MAT / LeakCanary / Android Studio Profiler
- 34.3 GC Roots 分析
- 34.4 Native 内存分析：malloc debug / MTE
- 34.5 实战案例：常见内存泄漏模式
- 34.6 内存监控体系

> **本章小结**：Hprof 是定位内存问题的第一工具——但要会读。

### 第 35 章　断点与 Native 调试

- 35.1 Java 断点调试：Android Studio / JDWP / 断点条件
- 35.2 Native 调试：gdb / lldb / ndk-stack
- 35.3 反汇编与符号化：objdump / readelf / addr2line
- 35.4 core dump 采集与分析
- 35.5 远程调试
- 35.6 调试技巧与陷阱

> **本章小结**：断点调试是终极大招——前面工具解决不了才用。

### 第 36 章　Oncall 与应急响应

- 36.1 Oncall 轮值与值班制度
- 36.2 故障应急响应流程：P0-P3 分级
- 36.3 故障复盘：Postmortem / RCA 报告
- 36.4 知识库与 Runbook
- 36.5 跨团队协作（内核 / Framework / App）
- 36.6 Oncall 工具链集成

> **本章小结**：Oncall 流程 = 把个人经验沉淀为团队能力。

