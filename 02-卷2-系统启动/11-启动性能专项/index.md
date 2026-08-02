# 第 11 章　启动性能专项

> **所属卷**：卷 2　系统启动
> **章定位**：启动优化是综合工程——Application、四大组件、资源、反射、类加载都要管。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 11.1 启动时间测量工具：bootchart / Perfetto / bootstat / am start -W
- 11.2 启动阶段拆分：Pre-loader → Application → Activity → Window → First Frame
- 11.3 启动卡顿定位：主线程 IO / 反射 / 类加载 / 资源加载
- 11.4 启动优化方法：预加载 / 延迟初始化 / 多阶段 / Jetpack Startup / Baseline Profile
- 11.5 启动期稳定性保障：白屏 / 闪退 / 黑屏 / 跨进程通信
- 11.6 启动期内存峰值治理

## 本章小结

启动优化是综合工程——Application、四大组件、资源、反射、类加载都要管。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
