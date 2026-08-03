# 第 2 章　AOSP 源码结构与构建系统

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：源码目录、构建系统、镜像生成——读源码与验证假设的动手基础。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8
> **本章可跳读**：只想读机制不想编译的读者可跳过，需要时再回来。

## 核心子节

- 2.1 源码目录：frameworks/base / system/core / kernel / hardware / vendor / packages
- 2.2 Soong / Blueprint / Android.bp：现代构建语言
- 2.3 Makefile / BoardConfig / device.mk：兼容层与传统构建
- 2.4 镜像生成：system.img / vendor.img / boot.img / vbmeta.img / dtbo.img
- 2.5 模块化与 GKI：Generic Kernel Image 与模块化架构
- 2.6 工具链：adb / fastboot / avbtool / lunch / make

## 本章小结

能从源码定位到机制，能从构建系统追溯到版本来源。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
