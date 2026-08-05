# 第 1 章　Android 系统全景与 AOSP 17

> **所属卷**：卷 1　Android 系统基础与平台
> **章定位**：建立 AOSP 17 的全局视图——分层架构、核心组件、进程模型、稳定性边界。后续所有章节都挂在这张地图上。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 1.1 系统分层：Hardware → Kernel → HAL → Native → Runtime → Framework → App
- 1.2 核心组件关系图：AMS / PMS / WMS / SurfaceFlinger / Binder / ServiceManager
- 1.3 进程模型：Zygote 体系、SystemServer、App 进程的生命周期与权限边界
- 1.4 AOSP 17 主要变化（vs 14/15/16）：Mainline 模块演进、ART 17 优化、隐私沙箱
- 1.5 稳定性视角的系统边界：哪些归稳定性团队、哪些需要跨团队
- 1.6 工程基线：AOSP 17.0.0_r1 + Linux 6.18 + 测试机型

## 本章小结

稳定性工作边界 = 全栈但有侧重，重点是 Framework / Native / Kernel 三层协同。

---

**状态**：🚧 已有 2 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
