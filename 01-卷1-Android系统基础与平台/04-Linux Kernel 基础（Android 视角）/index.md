# 第 4 章　Linux Kernel 基础（Android 视角）

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：Kernel 是 Android 稳定性的最底层——理解调度 / 内存 / IO / 同步才能理解 OOM、卡死、掉电。本章只讲**稳定性相关**的 Kernel 子系统。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 4.1 进程调度：CFS / RT / deadline / cgroup v2
- 4.2 内存管理：VMA / 页面回收 / OOM / LMK / PSI
- 4.3 IO 栈：VFS / Page Cache / IO 调度 / f2fs / erofs
- 4.4 中断与同步：workqueue / RCU / 自旋锁 / 内存屏障
- 4.5 Kernel 日志与崩溃现场：dmesg / pstore / ramoops（卷 4 第 29 章展开分析）
- 4.6 与 Android 的接口：Binder 驱动（卷 3 第 12 章展开）/ 网络栈（卷 3 第 17 章展开）

## 本章小结

约 30% 的稳定性根因落在 Kernel——ANR、Native 崩溃、卡死都要下探到这一层。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
