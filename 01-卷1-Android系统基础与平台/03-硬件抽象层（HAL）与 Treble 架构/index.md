# 第 3 章　硬件抽象层（HAL）与 Treble 架构

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：理解 vendor / system 解耦——为什么 Android 升级不必等芯片厂，以及 vendor 侧问题为什么难查。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 3.1 HAL 接口设计：AIDL / HIDL 与 .hal 文件
- 3.2 Treble 架构：vendor 与 system 解耦、VINTF 兼容性矩阵
- 3.3 HIDL → AIDL 迁移：AOSP 17 已全面 AIDL
- 3.4 VINTF 与 CTS：兼容性验证机制
- 3.5 OEM / BSP 适配要点：哪些必须做、哪些可选
- 3.6 vendor 侧问题的定位边界：日志在哪、能改什么、找谁

## 本章小结

vendor 行为是跨平台稳定性问题的主要根因之一；HAL 抽象让 system 升级不依赖 vendor，但也让问题定位多了一道墙。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
