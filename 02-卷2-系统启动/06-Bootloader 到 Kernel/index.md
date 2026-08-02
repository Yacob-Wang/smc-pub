# 第 6 章　Bootloader 到 Kernel

> **所属卷**：卷 2　系统启动
> **章定位**：Kernel 启动阶段出问题 = boot loop，调查工具是 last_kmsg / pstore。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 6.1 Bootloader 类型：LK / ABL / U-Boot
- 6.2 Bootloader 启动流程：PBL → ABL → Kernel
- 6.3 Kernel 启动入口：head.S / start_kernel
- 6.4 早期初始化：setup_arch / sched_init / page_alloc
- 6.5 Kernel cmdline 与 dtb：设备树 + 内核参数
- 6.6 启动失败案例：Kernel panic / boot loop

## 本章小结

Kernel 启动阶段出问题 = boot loop，调查工具是 last_kmsg / pstore。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
