# 第 35 章　断点与 Native 调试

> **所属卷**：卷 5　调查工具链
> **章定位**：终极武器——前面所有手段都失效时才用。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 35.1 Java 断点：Android Studio / JDWP / 条件断点
- 35.2 Native 调试：lldb / gdb / ndk-gdb
- 35.3 反汇编与符号：objdump / readelf / addr2line
- 35.4 core dump 采集与离线分析
- 35.5 远程调试与真机限制
- 35.6 调试技巧与常见陷阱

## 本章小结

断点调试成本最高、副作用最大——用它之前先确认日志与 trace 真的走到头了。

---

**状态**：📋 骨架（正文待按 35.1–35.6 撰写）
**清理**：2026-08-04 迁出 Git/Logcat/ftrace/Init.rc 等错位稿 → `_archive/misplaced-by-chapter-boundary/2026-08-04/vol5-ch35-offtopic/`
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
