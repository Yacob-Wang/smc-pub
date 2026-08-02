# 第 1 章　Android 系统全景与 AOSP 17

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：稳定性工作边界 = 全栈但有侧重，重点是 Framework / Native / Kernel 三层协同。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 1.1 系统分层：Hardware → Kernel → HAL → Native → Runtime → Framework → App
- 1.2 AOSP 17 主要变化（vs AOSP 14/15/16）：Mainline 模块演进、ART 17 优化、隐私沙箱
- 1.3 核心组件关系图：AMS/PMS/WMS/SurfaceFlinger/Binder/PackageManager
- 1.4 进程模型：Zygote 体系、SystemServer、App 进程的生命周期与权限边界
- 1.5 稳定性视角的系统边界：哪些是稳定性工程师负责的、哪些跨团队
- 1.6 工程基线：AOSP 17.0.0_r1 + Linux 6.18 + 测试机型

## 本章小结

稳定性工作边界 = 全栈但有侧重，重点是 Framework / Native / Kernel 三层协同。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
