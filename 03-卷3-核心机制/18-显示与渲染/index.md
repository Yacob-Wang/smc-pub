# 第 18 章　显示与渲染

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：卡顿 50% 根因在主线程，30% 在 RenderThread，20% 在 SurfaceFlinger。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 18.1 SurfaceFlinger 与 BufferQueue：跨进程 Buffer 传递
- 18.2 Choreographer 与 VSYNC：60Hz / 90Hz / 120Hz 调度
- 18.3 View 体系：measure / layout / draw / invalidate
- 18.4 RenderThread 与 HWUI：硬件加速
- 18.5 卡顿与掉帧分析：Jank / Slow frame / Stutter
- 18.6 屏幕闪烁 / 黑屏 / 花屏调查

## 本章小结

卡顿 50% 根因在主线程，30% 在 RenderThread，20% 在 SurfaceFlinger。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
