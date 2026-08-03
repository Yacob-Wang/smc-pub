# 第 10 章　应用启动与首帧

> **所属卷**：卷 2　系统启动
> **章定位**：启动优化必须分段——Application、Activity、Window、View 各自的瓶颈不同。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 10.1 Launcher 点击 → ActivityThread：Binder 跨进程调用
- 10.2 进程创建：Zygote fork（特殊参数 + waiting for debugger）
- 10.3 Application 初始化：attachBaseContext / onCreate
- 10.4 视图树构建：measure / layout / draw
- 10.5 Choreographer 调度：VSYNC 信号与 input/animation/traversal/tick
- 10.6 第一帧：First Frame / First Image / Cold Start / Warm Start / Hot Start
- 10.7 启动时间测量：am start -W / logcat / bootchart

## 本章小结

启动优化必须分段——Application、Activity、Window、View 各自的瓶颈不同。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
