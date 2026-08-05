# 第 14 章　线程与 Handler 消息机制

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：Handler 是 Android UI 线程的骨架——理解消息机制才能理解主线程卡顿与 ANR。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 14.1 线程模型：pthread / Java Thread / HandlerThread
- 14.2 Handler / Looper / MessageQueue 原理
- 14.3 同步屏障（Sync Barrier）：VSYNC 消息如何插队
- 14.4 IdleHandler / 延迟消息 / 定时器
- 14.5 主线程超时如何演变为 ANR
- 14.6 消息队列的可观测性：Looper 监控 / 慢消息采样

## 本章小结

主线程的一切都走 Handler——卡顿排查的第一站永远是主线程消息队列。

---

**状态**：🚧 已有 27 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
