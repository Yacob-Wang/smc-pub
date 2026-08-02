# 第 12 章　Binder IPC 深度

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：ANR 30% 根因是 Binder 阻塞。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 12.1 Binder 驱动：mmap / 引用计数 / 线程池（红黑树）
- 12.2 Binder 协议：BC/BR 命令 / Parcel / flat_binder_object
- 12.3 Java 框架层：AIDL / ServiceManager / deathRecipient
- 12.4 oneway / parcelable / Binder 池大小
- 12.5 Binder 调用链路：客户端 → 驱动 → 服务端
- 12.6 Binder 卡死排查：binder 线程数 / oneway 阻塞 / 死锁

## 本章小结

ANR 30% 根因是 Binder 阻塞。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
