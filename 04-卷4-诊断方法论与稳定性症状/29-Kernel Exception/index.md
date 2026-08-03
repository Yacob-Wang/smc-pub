# 第 29 章　Kernel Exception

> **所属卷**：卷 4　诊断方法论与稳定性症状
> **章定位**：内核层异常——panic / Oops / BUG / WARN / hung_task。它既是独立症状，也是下一章 REBOOT 的主要原因。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 29.1 Kernel panic：触发条件与分析流程
- 29.2 Oops 与 BUG：模块缺陷的典型形式
- 29.3 WARN：内核告警与「未致命但危险」信号
- 29.4 hung_task / RCU stall / softlockup
- 29.5 内核日志现场：pstore / ramoops / console-ramoops
- 29.6 内核问题的调查与厂商协同

## 本章小结

内核异常必须有 last_kmsg 或 pstore，否则基本无法定位——现场保留机制要在出问题**之前**配好。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
