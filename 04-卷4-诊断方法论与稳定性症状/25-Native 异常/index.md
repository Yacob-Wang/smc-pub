# 第 25 章　Native 异常

> **所属卷**：卷 4　诊断方法论与稳定性症状
> **章定位**：最难诊断的崩溃——信号、Tombstone、符号化三关缺一不可。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8
> **完整案例**：卷 8 第 49 章

## 核心子节

- 25.1 信号机制：SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL
- 25.2 debuggerd 与 Tombstone 生成链路
- 25.3 Tombstone 判读：寄存器 / 栈回溯 / 内存映射
- 25.4 符号化：addr2line / ndk-stack / 符号表管理
- 25.5 内存错误检测：AddressSanitizer / HWASan / GWP-ASan / MTE
- 25.6 Native Crash 上报与治理

## 本章小结

约 80% 的 Native 崩溃是内存问题——踩栈、use-after-free、double-free 三类占绝大多数。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
