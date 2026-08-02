# 卷 1　Android 系统基础与平台

> **本卷定位**：地基章节——稳定性架构师必须理解全栈结构、构建系统、HAL 抽象、Kernel 视角、安全模型。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 1 章 | Android 系统全景与 AOSP 17 | 🚧 撰写中 |
| 第 2 章 | AOSP 源码结构与构建系统 | 🚧 撰写中 |
| 第 3 章 | 硬件抽象层（HAL）与 Treble 架构 | 🚧 撰写中 |
| 第 4 章 | Linux Kernel 基础（Android 视角） | 🚧 撰写中 |
| 第 5 章 | 安全基础（SELinux / AVB） | 🚧 撰写中 |

---

## 章节目录（详细）

### 第 1 章　Android 系统全景与 AOSP 17

- 1.1 系统分层：Hardware → Kernel → HAL → Native → Runtime → Framework → App
- 1.2 AOSP 17 主要变化（vs AOSP 14/15/16）：Mainline 模块演进、ART 17 优化、隐私沙箱
- 1.3 核心组件关系图：AMS/PMS/WMS/SurfaceFlinger/Binder/PackageManager
- 1.4 进程模型：Zygote 体系、SystemServer、App 进程的生命周期与权限边界
- 1.5 稳定性视角的系统边界：哪些是稳定性工程师负责的、哪些跨团队
- 1.6 工程基线：AOSP 17.0.0_r1 + Linux 6.18 + 测试机型

> **本章小结**：稳定性工作边界 = 全栈但有侧重，重点是 Framework / Native / Kernel 三层协同。

### 第 2 章　AOSP 源码结构与构建系统

- 2.1 源码目录：frameworks/base / system/core / kernel / hardware / vendor / packages
- 2.2 Soong / Blueprint / Android.bp：现代构建语言
- 2.3 Makefile / BoardConfig / device.mk：兼容层与传统构建
- 2.4 镜像生成：system.img / vendor.img / boot.img / vbmeta.img / dtbo.img
- 2.5 模块化与 GKI：Generic Kernel Image 与模块化架构
- 2.6 编译/烧录/调试工具链：adb / fastboot / avbtool / lunch / make

> **本章小结**：能从源码定位到机制，能从构建系统追溯到版本来源。

### 第 3 章　硬件抽象层（HAL）与 Treble 架构

- 3.1 HAL 接口设计：AIDL / HIDL 与 .hal 文件
- 3.2 Treble 架构：vendor 与 system 解耦、VINTF 兼容性矩阵
- 3.3 HIDL → AIDL 迁移：AOSP 17 已全面 AIDL
- 3.4 VINTF 与 CTS：兼容性验证机制
- 3.5 OEM-BSP 适配要点：哪些必须做、哪些可选

> **本章小结**：vendor 行为是稳定性跨平台问题的根因之一，HAL 抽象让 system 升级不依赖 vendor。

### 第 4 章　Linux Kernel 基础（Android 视角）

- 4.1 进程调度：CFS / RT / deadline / cgroup
- 4.2 内存管理：VMA / 页面回收 / OOM / LMK / PSI
- 4.3 IO 栈：VFS / Page Cache / IO 调度 / f2fs / erofs
- 4.4 中断与同步：workqueue / RCU / 自旋锁 / 内存屏障
- 4.5 Binder 驱动：mmap / 引用计数 / 线程池（卷 3 第 12 章展开）
- 4.6 网络协议栈：TCP/UDP/socket / netfilter（卷 3 第 17 章展开）

> **本章小结**：稳定性问题 30% 根因在 Kernel，ANR / NE / 卡死都从这里找。

### 第 5 章　安全基础（SELinux / AVB）

- 5.1 Android 安全模型：沙箱 / UID / 权限 / 签名
- 5.2 SELinux：sepolicy / 域 / 类型 / 强制访问控制
- 5.3 AVB（Android Verified Boot）：启动验证链
- 5.4 权限框架：Android Permission / Runtime Permission / AppOps
- 5.5 权限拒绝类问题的调查方法

> **本章小结**：权限失败 ≠ 应用问题，可能是 SELinux 拒绝或 AVB 校验失败。

