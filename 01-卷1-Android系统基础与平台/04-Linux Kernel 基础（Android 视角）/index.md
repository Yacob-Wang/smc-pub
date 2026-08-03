# 第 4 章　Linux Kernel 基础（Android 视角）

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：稳定性问题 30% 根因在 Kernel，ANR / NE / 卡死都从这里找。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 4.1 进程调度：CFS / RT / deadline / cgroup
- 4.2 内存管理：VMA / 页面回收 / OOM / LMK / PSI
- 4.3 IO 栈：VFS / Page Cache / IO 调度 / f2fs / erofs
- 4.4 中断与同步：workqueue / RCU / 自旋锁 / 内存屏障
- 4.5 Binder 驱动：mmap / 引用计数 / 线程池（卷 3 第 12 章展开）
- 4.6 网络协议栈：TCP/UDP/socket / netfilter（卷 3 第 17 章展开）

## 本章小结

稳定性问题 30% 根因在 Kernel，ANR / NE / 卡死都从这里找。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
