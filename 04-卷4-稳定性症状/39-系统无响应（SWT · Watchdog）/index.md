# 第 27 章　系统无响应（SWT / Watchdog）

> **所属卷**：卷 4　诊断方法论与稳定性症状
> **章定位**：系统级不响应——Watchdog 是 Android 的应急医生，也是最后一道防线。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 27.1 Watchdog 架构：Java Watchdog / 内核 watchdog / watchdogd
- 27.2 超时判定：30s 主线程 / 60s 总体 / 各监控线程
- 27.3 卡死 vs 慢：slow operation 阈值与误报
- 27.4 现场保留：Watchdog 触发时抓什么
- 27.5 调查方法：栈采样 / Handler 采样 / 锁分析
- 27.6 SWT 治理与防御

## 本章小结

SWT 的根因约 90% 是 SystemServer 内部某个服务卡死——找到那个服务比分析 Watchdog 本身重要得多。

---

**状态**：🚧 已有 10 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
