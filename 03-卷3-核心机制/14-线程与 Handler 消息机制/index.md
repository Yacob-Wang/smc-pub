# 第 14 章　线程与 Handler 消息机制

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：主线程的一切都走 Handler——卡顿排查先看主线程消息队列。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 14.1 pthread / HandlerThread / Java 线程模型
- 14.2 Handler / Looper / MessageQueue 原理
- 14.3 消息屏障（Sync Barrier）：Vsync 信号如何优先处理
- 14.4 IdleHandler / 延迟消息 / 定时器
- 14.5 卡帧与 ANR 原理：主线程消息处理超时
- 14.6 IdleHandler 与 Choreographer 协同

## 本章小结

主线程的一切都走 Handler——卡顿排查先看主线程消息队列。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
