# 第 12 章　Binder IPC 深度

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：Android 唯一的通用跨进程通信机制——理解 Binder 才能理解绝大多数跨进程卡死。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 12.1 Binder 驱动：mmap / 引用计数 / 线程池
- 12.2 Binder 协议：BC / BR 命令 / Parcel / flat_binder_object
- 12.3 Java 框架层：AIDL / ServiceManager / DeathRecipient
- 12.4 调用模式：同步 / oneway / 事务大小限制
- 12.5 完整调用链路：客户端 → 驱动 → 服务端 → 返回
- 12.6 Binder 卡死排查：线程池耗尽 / oneway 堆积 / 跨进程死锁

## 本章小结

Binder 阻塞是 ANR 的头号跨进程根因——看 ANR trace 先确认主线程是否卡在 Binder 上。

---

**状态**：🚧 已有 13 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
