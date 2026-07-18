# 06-Foundation · Android 基础主题（BSP / 构建 / 杂项）

> **目标读者**：Android BSP 工程师 / 平台架构师 / 构建系统工程师
>
> **分类定位**：按 **基础依赖**组织 BSP / 构建 / 集成 / 杂项工具——是 Mechanism / Tool / Governance 的"前置依赖"
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）

---

## 0. 分类总定位

### 0.1 一句话定位

**Foundation 是 smc-pub 的"基础库"——把 Android 平台的 BSP、构建系统、系统集成、杂项工具独立成类，让架构师能"按需查阅"，不与机制/症状/工具/治理混在一起。**

### 0.2 与其他分类的关系

| 维度 | Foundation | Mechanism | Tool | Governance |
|:-----|:------------|:----------|:-----|:------------|
| **视角** | 基础（依赖）| 机制（自下而上）| 工具（横向）| 治理（运营）|
| **核心问题** | "怎么编译/集成" | "这层怎么工作" | "用什么工具查" | "怎么治理" |
| **产出** | 编译配置 + 集成脚本 | 源码 + 流程图 | 工具子命令 | 治理框架 |

> **本分类是其他分类的"前置依赖"**——任何编译/集成/杂项问题先来这里查。

### 0.3 4 子分类

| 子分类 | 文件数 | 重点 |
|:-------|:------:|:-----|
| **Build-System/** | 13 | Android 构建系统 + makefile + soong |
| **System-Integration/** | 3 | HAL 集成 + 厂商定制集成 |
| **Dynamic-Updates/** | 4 | APEX / Mainline / OTA |
| **Tools/** | 17 | Android_Tools + Git_Mastery + Memory_Analysis + Tracing |

---

## 1. 子分类导览

### 1.1 Build-System/（13 篇 · Android 构建系统）

- **核心内容**：
  - Android Build System 基础（Makefile + Kati + Soong）
  - AOSP 17 构建流程（`source build/envsetup.sh` + `lunch` + `m`）
  - 模块依赖 + `Android.bp` 语法
  - vendor / system / product 分区构建
  - GKI 内核构建（android17-6.18）
  - 启动镜像构建（boot.img + initramfs）

### 1.2 System-Integration/（3 篇 · 系统集成）

- **核心内容**：
  - HAL 集成（HIDL/AIDL）
  - 厂商定制集成（OEM 适配层）
  - 启动期 init.rc 集成

### 1.3 Dynamic-Updates/（4 篇 · 动态更新）

- **核心内容**：
  - APEX 模块（Android 10+）
  - Mainline 模块更新
  - OTA 升级（A/B 分区）
  - 启动期模块加载

### 1.4 Tools/（17 篇 · 杂项工具）

- **4 子目录**：

| 子目录 | 篇数 | 重点 |
|:-------|:----:|:-----|
| Android_Tools/ | 2 | Init_RC 完整指南 + Logcat 完整指南 |
| Git_Mastery/ | 5 | Git 基础 + 进阶 + 专家 + 别名 + 实战 |
| Memory_Analysis/ | 1 | PSI 内存压力分析 |
| Tracing/ | 7 | ftrace/atrace/systrace/perfetto 综合（临时承载，后续并入 04-Tool/Tracing/）|

---

## 2. 文档统计

| 子分类 | 文件数 | 状态 | 重点 |
|:-------|:------:|:----:|:-----|
| Build-System/ | 13 | ✅ 完整 | 编译基础 |
| System-Integration/ | 3 | ✅ 完整 | 集成基础 |
| Dynamic-Updates/ | 4 | ✅ 完整 | 动态更新 |
| Tools/ | 17 | ✅ 完整 | 杂项工具 |
| **总计** | **37** | **完整** | **0.31 MB** |

---

## 3. 强依赖 / 衔接

- **被依赖**：
  - [01-Mechanism](../01-Mechanism/) 所有源码编译依赖 Foundation
  - [05-Governance/OEM-BSP](../05-Governance/OEM-BSP/) 厂商集成依赖 Foundation
- **依赖**：
  - [00-Meta/Reference/版本基线](../00-Meta/版本基线.md) 统一基线声明

---

## 4. 后续计划

- **Build-System/**：补充 AOSP 17 新构建工具（如 RBE / Soong 的最新特性）
- **System-Integration/**：补充 vendor 适配层文档
- **Dynamic-Updates/**：补充 APEX v2 文档（AOSP 17 增强）
- **Tools/Tracing/**：合并到 04-Tool/Tracing/

---

**最后更新**：2026-07-19（阶段 3 完成）
**作者**：Mavis · Stability Matrix Course
