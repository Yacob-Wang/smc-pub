# 第 10 章　应用启动与首帧

> **所属卷**：卷 2　系统启动
> **章定位**：从 Launcher 点击到第一帧显示——App 启动的**机制链路**。优化实践见卷 6 第 38 章。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 10.1 Launcher 点击 → ActivityThread：Binder 跨进程调用
- 10.2 进程创建：Zygote fork 的特殊参数
- 10.3 Application 初始化：attachBaseContext / onCreate / ContentProvider 初始化
- 10.4 视图树构建：measure / layout / draw
- 10.5 Choreographer 调度：VSYNC 与 input / animation / traversal 回调
- 10.6 首帧定义：First Frame / First Image / Cold / Warm / Hot Start
- 10.7 启动时间测量：am start -W / logcat / Perfetto

## 本章小结

启动优化必须分段——Application、Activity、Window、View 各自的瓶颈成因完全不同。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
