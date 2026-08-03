# 第 16 章　IO 与存储

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：IO 影响启动速度、应用响应与卡顿——理解全栈 IO 才能定位 IO 类阻塞。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 16.1 VFS 与文件系统：ext4 / f2fs / erofs
- 16.2 Page Cache 与 IO 调度
- 16.3 存储框架：StorageManager / Volume / FUSE
- 16.4 数据库：SQLite / Room / 文件锁竞争
- 16.5 ContentProvider 的跨进程数据访问
- 16.6 IO 瓶颈定位：iostat / atrace / IO hang 的特征

## 本章小结

启动期与冷路径的卡顿，主线程 IO 是最高频的单一根因。

---

**状态**：🚧 已有 47 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
