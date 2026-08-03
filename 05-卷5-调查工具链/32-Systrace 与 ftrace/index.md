# 第 32 章　Systrace 与 ftrace

> **所属卷**：卷 5　调查工具链
> **章定位**：传统但仍必要的工具——分析历史 trace 与内核事件时不可替代。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 32.1 ftrace 子系统：function / graph / event / probe
- 32.2 关键 tracepoint 速查
- 32.3 atrace 用户态埋点
- 32.4 Systrace 原理与 systrace.py
- 32.5 自定义埋点与内核探针
- 32.6 实战场景与数据量控制

## 本章小结

ftrace 是 Perfetto 的数据来源——理解 ftrace 才能解释 Perfetto 里看到的现象。

---

**状态**：📋 骨架完成，待撰写
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
