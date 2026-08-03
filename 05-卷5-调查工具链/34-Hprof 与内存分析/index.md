# 第 34 章　Hprof 与内存分析

> **所属卷**：卷 5　调查工具链
> **章定位**：内存问题的 X 光机——堆快照、泄漏定位、Native 内存。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 34.1 Hprof 格式与生成方式
- 34.2 堆分析：MAT / Android Studio Profiler
- 34.3 GC Roots 与引用链分析
- 34.4 LeakCanary 原理与自动化检测
- 34.5 Native 内存：malloc debug / heapprofd / MTE
- 34.6 内存监控体系搭建

## 本章小结

Hprof 能告诉你「谁在占内存」，但回答「为什么没释放」要靠引用链——后者才是修复依据。

---

**状态**：🚧 已有 6 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
