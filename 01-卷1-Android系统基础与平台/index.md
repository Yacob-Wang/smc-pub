# 卷 1　Android 系统基础与平台

> **本卷定位**：稳定性架构师必须理解全栈结构——硬件怎么动、Kernel 怎么调度、HAL 怎么抽象、安全模型怎么约束。**地基卷**，不读后面章节会缺基础。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 1 章 | Android 系统全景与 AOSP 17 | 🚧 撰写中 |
| 第 2 章 | AOSP 源码结构与构建系统 | 🚧 撰写中 |
| 第 3 章 | 硬件抽象层（HAL）与 Treble 架构 | 📋 待撰写 |
| 第 4 章 | Linux Kernel 基础（Android 视角） | 📋 待撰写 |
| 第 5 章 | 安全基础（SELinux / AVB） | 🚧 撰写中 |

---

## 章节详细

### 第 1 章　Android 系统全景与 AOSP 17

> 建立 AOSP 17 的全局视图——分层架构、核心组件、进程模型、稳定性边界。后续所有章节都挂在这张地图上。

- 1.1 系统分层：Hardware → Kernel → HAL → Native → Runtime → Framework → App
- 1.2 核心组件关系图：AMS / PMS / WMS / SurfaceFlinger / Binder / ServiceManager
- 1.3 进程模型：Zygote 体系、SystemServer、App 进程的生命周期与权限边界
- 1.4 AOSP 17 主要变化（vs 14/15/16）：Mainline 模块演进、ART 17 优化、隐私沙箱
- 1.5 稳定性视角的系统边界：哪些归稳定性团队、哪些需要跨团队
- 1.6 工程基线：AOSP 17.0.0_r1 + Linux 6.18 + 测试机型

**本章小结**：稳定性工作边界 = 全栈但有侧重，重点是 Framework / Native / Kernel 三层协同。

### 第 2 章　AOSP 源码结构与构建系统

> 源码目录、构建系统、镜像生成——读源码与验证假设的动手基础。

- 2.1 源码目录：frameworks/base / system/core / kernel / hardware / vendor / packages
- 2.2 Soong / Blueprint / Android.bp：现代构建语言
- 2.3 Makefile / BoardConfig / device.mk：兼容层与传统构建
- 2.4 镜像生成：system.img / vendor.img / boot.img / vbmeta.img / dtbo.img
- 2.5 模块化与 GKI：Generic Kernel Image 与模块化架构
- 2.6 工具链：adb / fastboot / avbtool / lunch / make

**本章小结**：能从源码定位到机制，能从构建系统追溯到版本来源。

### 第 3 章　硬件抽象层（HAL）与 Treble 架构

> 理解 vendor / system 解耦——为什么 Android 升级不必等芯片厂，以及 vendor 侧问题为什么难查。

- 3.1 HAL 接口设计：AIDL / HIDL 与 .hal 文件
- 3.2 Treble 架构：vendor 与 system 解耦、VINTF 兼容性矩阵
- 3.3 HIDL → AIDL 迁移：AOSP 17 已全面 AIDL
- 3.4 VINTF 与 CTS：兼容性验证机制
- 3.5 OEM / BSP 适配要点：哪些必须做、哪些可选
- 3.6 vendor 侧问题的定位边界：日志在哪、能改什么、找谁

**本章小结**：vendor 行为是跨平台稳定性问题的主要根因之一；HAL 抽象让 system 升级不依赖 vendor，但也让问题定位多了一道墙。

### 第 4 章　Linux Kernel 基础（Android 视角）

> Kernel 是 Android 稳定性的最底层——理解调度 / 内存 / IO / 同步才能理解 OOM、卡死、掉电。本章只讲**稳定性相关**的 Kernel 子系统。

- 4.1 进程调度：CFS / RT / deadline / cgroup v2
- 4.2 内存管理：VMA / 页面回收 / OOM / LMK / PSI
- 4.3 IO 栈：VFS / Page Cache / IO 调度 / f2fs / erofs
- 4.4 中断与同步：workqueue / RCU / 自旋锁 / 内存屏障
- 4.5 Kernel 日志与崩溃现场：dmesg / pstore / ramoops（卷 4 第 29 章展开分析）
- 4.6 与 Android 的接口：Binder 驱动（卷 3 第 12 章展开）/ 网络栈（卷 3 第 17 章展开）

**本章小结**：约 30% 的稳定性根因落在 Kernel——ANR、Native 崩溃、卡死都要下探到这一层。

### 第 5 章　安全基础（SELinux / AVB）

> Android 安全模型——沙箱 + 权限 + SELinux + AVB。理解安全边界才能识别「看起来像 bug、实际是权限拒绝」的问题。

- 5.1 Android 安全模型：沙箱 / UID / 权限 / 签名
- 5.2 SELinux：sepolicy / 域 / 类型 / 强制访问控制
- 5.3 权限框架：Android Permission / Runtime Permission / AppOps
- 5.4 AVB（Android Verified Boot）：启动验证链
- 5.5 权限拒绝类问题的调查方法：从 avc denied 反推策略

**本章小结**：权限失败 ≠ 应用问题，可能是 SELinux 拒绝或 AVB 校验失败——这类问题的日志特征与普通崩溃完全不同。
