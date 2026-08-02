# 第 24 章　Native 异常

> **所属卷**：卷 4　稳定性症状诊断
> **章定位**：Native 崩溃 80% 是内存问题——踩栈 / use-after-free / double-free。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 24.1 信号处理：SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL
- 24.2 Tombstone 解析：寄存器 / 栈回溯 / 内存映射 / 共享库
- 24.3 so 库加载与符号化：addr2line / ndk-stack / symbolicator
- 24.4 AddressSanitizer / HWASan / UBSan / GWP-ASan
- 24.5 Native 案例库（5-10 个真实场景）
- 24.6 Native Crash 治理：crashpad / breakpad

## 本章小结

Native 崩溃 80% 是内存问题——踩栈 / use-after-free / double-free。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
