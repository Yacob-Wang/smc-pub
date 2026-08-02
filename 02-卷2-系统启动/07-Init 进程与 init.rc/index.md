# 第 7 章　Init 进程与 init.rc

> **所属卷**：卷 2　系统启动
> **章定位**：init 阶段慢 = 整机启动慢的 N 倍影响（gating 后续所有服务）。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 7.1 Init 进程（system/core/init）启动流程
- 7.2 init.rc 语法：service / action / import / on
- 7.3 启动阶段：early / init / late-start / post-fs / post-fs-data
- 7.4 属性服务（Property Service）：跨进程配置传递
- 7.5 SELinux 上下文加载与策略执行
- 7.6 init 启动慢的常见原因

## 本章小结

init 阶段慢 = 整机启动慢的 N 倍影响（gating 后续所有服务）。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
