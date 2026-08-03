# 第 25 章　系统无响应（SWT / Watchdog）

> **所属卷**：卷 4　稳定性症状诊断
> **章定位**：SWT 的根因 90% 是 SystemServer 内部某个服务卡死。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 25.1 Watchdog 原理：30s 主线程 / 60s 总体
- 25.2 卡死 vs 慢：slow operation 阈值
- 25.3 调查方法：systrace / stack sampling / Handler sampling
- 25.4 卡死期间的现场保留
- 25.5 SWT 案例库（3-5 个）
- 25.6 SWT 治理

## 本章小结

SWT 的根因 90% 是 SystemServer 内部某个服务卡死。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
