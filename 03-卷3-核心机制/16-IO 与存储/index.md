# 第 16 章　IO 与存储

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：启动期 70% 卡顿根因是主线程 IO。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 16.1 VFS 与文件系统：ext4 / f2fs / erofs
- 16.2 Page Cache 与 IO 调度：CFQ / deadline / bfq
- 16.3 存储框架：StorageManager / Volume / FUSE / SDCardFS
- 16.4 ContentProvider 数据访问
- 16.5 数据库：SQLite / Room / 文件锁
- 16.6 IO 性能瓶颈定位：iostat / atrace / IO hang

## 本章小结

启动期 70% 卡顿根因是主线程 IO。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
