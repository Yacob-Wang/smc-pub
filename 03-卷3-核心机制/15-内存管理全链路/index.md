# 第 15 章　内存管理全链路

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：内存问题 = 全栈，单独看任何一层都不够。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 15.1 内核分配器：kmalloc / vmalloc / slab / page
- 15.2 进程虚拟内存：VMA / mmap / 缺页 / 写时复制
- 15.3 ART 堆：TLAB / Concurrent GC / 引用类型 / 卡片表
- 15.4 Framework 内存治理：AMS / TrimMemory / ComponentCallbacks2
- 15.5 OOM 与低内存：LMK / OOM Killer / PSI / memory pressure
- 15.6 内存泄漏排查：hprof / LeakCanary 原理 / GC roots / MAT

## 本章小结

内存问题 = 全栈，单独看任何一层都不够。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
