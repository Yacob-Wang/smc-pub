# 第 15 章　内存管理全链路

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：内存是最复杂的稳定性领域——Kernel 分配、ART 堆、Framework 治理三层协同。**ART 内部 GC 算法见第 20 章**，本章讲跨层协作。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 15.1 内核分配器：kmalloc / vmalloc / slab / page
- 15.2 进程虚拟内存：VMA / mmap / 缺页 / 写时复制
- 15.3 Native 堆：bionic / scudo 分配器
- 15.4 ART 堆与系统内存的边界：堆增长如何影响系统水位
- 15.5 Framework 内存治理：AMS / onTrimMemory / ComponentCallbacks2
- 15.6 低内存机制：LMK / OOM Killer / PSI / memory pressure

## 本章小结

内存问题必须跨层看——只看 ART 堆会漏掉 Native 增长，只看进程会漏掉系统水位。

---

**状态**：🚧 已有 25 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
