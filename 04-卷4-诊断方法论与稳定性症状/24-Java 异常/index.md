# 第 24 章　Java 异常

> **所属卷**：卷 4　诊断方法论与稳定性症状
> **章定位**：App 层最常见的崩溃——机制简单但治理复杂。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 24.1 异常分类：NPE / ClassCast / ConcurrentModification / OOM
- 24.2 崩溃捕获链路：UncaughtExceptionHandler → AMS → DropBox
- 24.3 堆栈判读与混淆还原
- 24.4 启动期崩溃的特殊性：现场少、复现难
- 24.5 第三方库异常的定位与止损
- 24.6 Java Crash 监控体系与崩溃率治理

## 本章小结

约 90% 的 Java 异常集中在空指针、状态错乱与第三方库兼容性三类。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
