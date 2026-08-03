# 第 2 章　AOSP 源码结构与构建系统

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：能从源码定位到机制，能从构建系统追溯到版本来源。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 2.1 源码目录：frameworks/base / system/core / kernel / hardware / vendor / packages
- 2.2 Soong / Blueprint / Android.bp：现代构建语言
- 2.3 Makefile / BoardConfig / device.mk：兼容层与传统构建
- 2.4 镜像生成：system.img / vendor.img / boot.img / vbmeta.img / dtbo.img
- 2.5 模块化与 GKI：Generic Kernel Image 与模块化架构
- 2.6 编译/烧录/调试工具链：adb / fastboot / avbtool / lunch / make

## 本章小结

能从源码定位到机制，能从构建系统追溯到版本来源。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
