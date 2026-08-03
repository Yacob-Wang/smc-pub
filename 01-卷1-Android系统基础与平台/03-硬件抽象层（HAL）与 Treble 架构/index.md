# 第 3 章　硬件抽象层（HAL）与 Treble 架构

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：vendor 行为是稳定性跨平台问题的根因之一，HAL 抽象让 system 升级不依赖 vendor。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 3.1 HAL 接口设计：AIDL / HIDL 与 .hal 文件
- 3.2 Treble 架构：vendor 与 system 解耦、VINTF 兼容性矩阵
- 3.3 HIDL → AIDL 迁移：AOSP 17 已全面 AIDL
- 3.4 VINTF 与 CTS：兼容性验证机制
- 3.5 OEM-BSP 适配要点：哪些必须做、哪些可选

## 本章小结

vendor 行为是稳定性跨平台问题的根因之一，HAL 抽象让 system 升级不依赖 vendor。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
