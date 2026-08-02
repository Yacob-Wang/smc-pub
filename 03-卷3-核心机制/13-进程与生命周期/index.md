# 第 13 章　进程与生命周期

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：进程优先级设置错误 = 关键进程被 LMK 误杀。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 13.1 进程模型：fork / vfork / clone / CGroup
- 13.2 进程优先级：oom_score_adj / cgroup / ProcessList
- 13.3 进程间通信总览：Binder / Socket / SharedMemory / Handler / ContentProvider
- 13.4 进程生命周期：启动 / 优先级 / 杀进程策略 / LMK (Low Memory Killer)
- 13.5 进程退出：Exit / Tombstone / Process.kill / ANR 杀进程
- 13.6 进程崩溃与恢复：CrashHandler / 进程拉起策略

## 本章小结

进程优先级设置错误 = 关键进程被 LMK 误杀。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
