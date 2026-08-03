# 第 19 章　显示与渲染

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：显示是用户感知的终点——本章讲**机制**（帧是怎么产生的），卡顿优化实践见卷 6 第 39 章。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 19.1 SurfaceFlinger 与 BufferQueue：跨进程 Buffer 传递
- 19.2 VSYNC 与 Choreographer：60 / 90 / 120Hz 调度
- 19.3 View 体系：measure / layout / draw / invalidate
- 19.4 RenderThread 与 HWUI：硬件加速管线
- 19.5 一帧的完整时序：从 input 到 present
- 19.6 显示异常：黑屏 / 闪屏 / 花屏的机制成因

## 本章小结

一帧要穿过 App 主线程、RenderThread、SurfaceFlinger 三个环节——任何一环超时都表现为掉帧。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
