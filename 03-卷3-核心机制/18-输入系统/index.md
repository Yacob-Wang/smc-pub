# 第 18 章　输入系统

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：输入是 ANR 的最高频触发路径——理解 InputDispatcher 才能读懂 input ANR。**与第 19 章构成「触摸 → 首帧」完整交互链路。**
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 18.1 InputManagerService 架构
- 18.2 输入事件流：EventHub → InputReader → InputDispatcher → 窗口
- 18.3 InputChannel 与跨进程投递
- 18.4 触摸事件分发：ViewRootImpl → DecorView → ViewGroup → View
- 18.5 输入 ANR 原理：5s dispatch timeout 的判定条件
- 18.6 焦点窗口与「无焦点窗口」ANR

## 本章小结

input ANR 约 90% 的根因是主线程或 Binder 阻塞，而非输入系统本身——input 只是最先报警的那个。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
