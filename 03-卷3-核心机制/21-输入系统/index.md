# 第 21 章　输入系统

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：input ANR 90% 是主线程 / Binder 阻塞，不是 input 系统本身问题。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 21.1 InputManagerService 架构
- 21.2 输入事件流：InputReader → InputDispatcher → 窗口
- 21.3 触摸事件分发：ViewRootImpl → DecorView → ViewGroup → View
- 21.4 输入 ANR 原理：5s input dispatch timeout
- 21.5 输入卡顿与延迟
- 21.6 焦点窗口与无焦点 ANR

## 本章小结

input ANR 90% 是主线程 / Binder 阻塞，不是 input 系统本身问题。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
