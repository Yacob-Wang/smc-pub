# 第 39 章　滑动与渲染性能

> **所属卷**：卷 6　性能工程
> **章定位**：卡顿 80% 在主线程，剩下 20% 在 RenderThread / SurfaceFlinger。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 39.1 帧率指标：FPS / Jank / Slow frame
- 39.2 渲染管线：measure / layout / draw / RenderThread
- 39.3 滑动卡顿定位
- 39.4 动画与过渡优化
- 39.5 复杂布局优化：ConstraintLayout / ViewStub / merge
- 39.6 滑动性能案例

## 本章小结

卡顿 80% 在主线程，剩下 20% 在 RenderThread / SurfaceFlinger。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
