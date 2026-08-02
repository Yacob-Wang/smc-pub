# 第 28 章　Kernel Exception

> **所属卷**：卷 4　稳定性症状诊断
> **章定位**：内核异常 = 必须有 last_kmsg，否则无法定位。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 28.1 Kernel panic：触发条件、分析流程
- 28.2 Oops 与 BUG：模块 bug 的常见形式
- 28.3 WARN：内核告警机制
- 28.4 hung_task / RCU stall / softlockup
- 28.5 内核日志工具：pstore / ramoops / dmesg / syslog
- 28.6 内核问题调查方法

## 本章小结

内核异常 = 必须有 last_kmsg，否则无法定位。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
