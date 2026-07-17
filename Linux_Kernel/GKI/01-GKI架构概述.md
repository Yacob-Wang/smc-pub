# GKI 架构概述与设计理念

![generic-kernel-image-architecture (1)](D:\ACK\ACKLearning\articles\01-GKI架构概述.assets\generic-kernel-image-architecture (1)-1769048382167.png)

## 学习目标

- 理解 GKI (Generic Kernel Image) 诞生的背景和原因
- 掌握 GKI 的核心设计理念和架构思想
- 了解 GKI 与传统内核架构的区别
- 理解 GKI 的优势和面临的挑战
- 能够解读 GKI 架构图

## 背景介绍

### Android 内核碎片化问题

在 GKI 之前，Android 生态系统面临严重的**内核碎片化**问题：

1. **每个厂商维护独立内核**：每个设备厂商都需要 fork 整个 Linux 内核，添加自己的驱动和定制
2. **难以统一更新**：安全补丁和功能更新需要每个厂商分别适配
3. **更新延迟**：设备厂商需要几个月甚至更长时间才能推送内核更新
4. **维护成本高**：厂商需要维护大量内核代码，容易出错

### GKI 的诞生

为了解决这些问题，Google 从 **Android 11** 开始引入 GKI 架构：

- **2019 年**：GKI 概念提出
- **2020 年**：Android 11 开始要求新设备支持 GKI
- **2021 年**：Android 12 进一步强化 GKI 要求
- **现在**：GKI 已成为 Android 内核的标准架构

## 核心概念

### 什么是 GKI

**GKI (Generic Kernel Image)** 是一个标准化的内核架构，将内核分为两个部分：

1. **Generic Kernel（通用内核）**
   - 包含所有设备通用的内核功能
   - 由 Google 统一维护和更新
   - 所有 GKI 设备使用相同的二进制

2. **Vendor Modules（厂商模块）**
   - 包含设备特定的驱动和功能
   - 由设备厂商开发和维护
   - 通过模块机制动态加载

### GKI 的核心设计理念

#### 1. 分离关注点（Separation of Concerns）

**理念**：将通用功能和设备特定功能分离

- **通用功能**：内存管理、进程调度、文件系统等 → Generic Kernel
- **设备特定功能**：硬件驱动、厂商定制 → Vendor Modules

**好处**：
- 通用功能可以统一维护和更新
- 设备特定功能不影响核心内核
- 降低代码耦合度

#### 2. 接口稳定性（Interface Stability）

**理念**：通过 KMI (Kernel Module Interface) 定义稳定的接口

- Generic Kernel 通过 KMI 向模块导出符号
- Vendor Modules 只能使用 KMI 定义的接口
- KMI 接口保持向后兼容

**好处**：
- Generic Kernel 可以独立升级
- Vendor Modules 无需频繁修改
- 保证系统稳定性

#### 3. 模块化架构（Modular Architecture）

**理念**：将功能以模块形式组织

- 核心功能在内核中
- 可选功能以模块形式提供
- 模块可以动态加载和卸载

**好处**：
- 灵活性高
- 易于扩展
- 减少内核体积

#### 4. 统一更新（Unified Updates）

**理念**：Generic Kernel 可以独立更新

- 安全补丁直接应用到 Generic Kernel
- 无需等待厂商适配
- 快速推送到所有设备

**好处**：
- 提高安全性
- 减少更新延迟
- 降低维护成本

## GKI 与传统内核架构的对比

### 传统架构

```
┌─────────────────────────────────┐
│     Android Framework          │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│     HAL Implementation         │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│  厂商定制内核 (完整内核树)      │
│  - 通用功能                     │
│  - 设备驱动                     │
│  - 厂商定制                     │
└─────────────────────────────────┘
```

**特点**：
- 每个厂商维护完整的内核树
- 内核代码高度定制化
- 难以统一更新
- 安全补丁需要厂商适配

### GKI 架构

```
┌─────────────────────────────────┐
│     Android Framework          │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│     HAL Implementation         │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│   Generic Kernel (统一内核)     │
│   + GKI Modules                 │
│   + Vendor Modules (通过 KMI)   │
└─────────────────────────────────┘
```

**特点**：
- Generic Kernel 由 Google 统一维护
- 厂商通过模块扩展功能
- 可以快速推送安全补丁
- 降低碎片化

### 对比表格

| 特性 | 传统架构 | GKI 架构 |
|------|---------|---------|
| 内核维护 | 每个厂商独立维护 | Google 统一维护 Generic Kernel |
| 安全更新 | 需要厂商适配 | 直接推送到 Generic Kernel |
| 更新速度 | 慢（数月） | 快（数周） |
| 代码复用 | 低 | 高 |
| 碎片化程度 | 高 | 低 |
| 厂商工作量 | 大（维护整个内核） | 小（只需维护模块） |

## GKI 的优势

### 1. 快速安全更新

**优势**：安全补丁可以直接推送到 Generic Kernel，无需等待厂商适配

**示例**：

- 发现内核安全漏洞
- Google 修复并推送到 Generic Kernel
- 所有 GKI 设备可以快速获得修复

### 2. 降低碎片化

**优势**：所有设备使用相同的 Generic Kernel，减少差异

**效果**：
- 统一的测试和验证
- 更好的兼容性
- 简化的开发流程

### 3. 简化厂商开发

**优势**：厂商只需维护自己的模块，无需维护整个内核

**好处**：
- 减少代码量
- 降低维护成本
- 提高开发效率

### 4. 提高系统稳定性

**优势**：Generic Kernel 经过充分测试，稳定性更高

**原因**：
- 统一的内核代码
- 广泛的测试覆盖
- 更好的质量保证

## GKI 面临的挑战

### 1. KMI 接口设计

**挑战**：需要设计稳定且足够灵活的 KMI 接口

**难点**：
- 接口太少：无法满足厂商需求
- 接口太多：增加维护成本
- 接口变更：需要保证兼容性

### 2. 模块兼容性

**挑战**：确保 Vendor Modules 与 Generic Kernel 兼容

**问题**：
- 模块可能依赖未导出的符号
- 接口变更可能导致模块失效
- 需要严格的兼容性测试

### 3. 性能考虑

**挑战**：模块化可能带来性能开销

**影响**：
- 模块加载时间
- 符号解析开销
- 内存占用增加

### 4. 迁移成本

**挑战**：从传统架构迁移到 GKI 需要大量工作

**工作**：
- 重构现有驱动
- 适配 KMI 接口
- 测试和验证

## 架构图详细解读

基于提供的 GKI 架构图，我们来详细解读各个组件：

### 上层：用户空间

#### Android Framework（绿色块）

- **位置**：架构图左侧，绿色块
- **作用**：Android 系统框架，提供应用开发接口
- **特点**：AOSP 维护，所有设备共享

#### HAL Implementation（蓝色块）

- **位置**：架构图右侧，蓝色块，占据大部分宽度
- **作用**：硬件抽象层实现，连接 Framework 和 Kernel
- **特点**：由厂商提供，设备特定

**交互**：
- 与 Android Framework 通过浅蓝色双向箭头交互
- 接收 Framework 的调用请求
- 将请求转发到内核层

### 下层：内核空间

#### Generic Kernel（绿色块）

- **位置**：架构图左侧，绿色块
- **作用**：通用内核核心，包含所有设备通用的功能
- **特点**：
  - 由 Google 维护
  - 所有设备使用相同的二进制
  - 包含核心内存管理、进程调度等

**交互**：
- 直接接收 Android Framework 的调用（实线蓝色向上箭头）
- 直接接收 HAL Implementation 的调用（实线蓝色向上箭头）
- 与 GKI Modules 交互（虚线灰色双向箭头）

#### GKI Modules（绿色堆叠块）

- **位置**：架构图中间，绿色堆叠块
- **作用**：GKI 标准模块，提供可选功能
- **特点**：
  - 由 Google 维护
  - 所有设备都可以使用
  - 通过 System DLKM 加载

**交互**：
- 与 Generic Kernel 交互（虚线灰色双向箭头）
- 接收 HAL Implementation 的调用（实线蓝色向上箭头）
- 与 Vendor Modules 通过 KMI 交互（实线灰色双向箭头，标注 "KMI"）

#### Vendor Modules（蓝色堆叠块）

- **位置**：架构图右侧，蓝色堆叠块
- **作用**：厂商特定模块，提供设备特定功能
- **特点**：
  - 由厂商开发和维护
  - 设备特定
  - 只能使用 KMI 接口

**交互**：
- 与 GKI Modules 通过 KMI 交互（实线灰色双向箭头，标注 "KMI"）
- 接收 HAL Implementation 的调用（虚线蓝色向上箭头）

### 关键接口：KMI

**KMI (Kernel Module Interface)** 是架构图中的关键接口：

- **位置**：GKI Modules 和 Vendor Modules 之间
- **表示**：实线灰色双向箭头，标注 "KMI"
- **作用**：
  - 定义 Generic Kernel 向模块导出的符号
  - 保证接口的稳定性和兼容性
  - 管理模块与内核的交互

### 数据流向分析

1. **Framework → Generic Kernel**
   - 实线蓝色向上箭头
   - Framework 直接调用内核系统调用
   - 访问通用内核功能（如内存管理、进程调度）

2. **Framework ↔ HAL**
   - 浅蓝色双向箭头
   - Framework 通过 HAL 访问硬件功能
   - HAL 将请求转发到内核

3. **HAL → Generic Kernel**
   - 实线蓝色向上箭头
   - HAL 直接调用内核接口

4. **HAL → GKI Modules**
   - 实线蓝色向上箭头
   - HAL 使用 GKI 模块提供的功能

5. **HAL → Vendor Modules**
   - 虚线蓝色向上箭头
   - HAL 调用厂商模块的功能
   - 虚线表示这是可选的、设备特定的路径

6. **Generic Kernel ↔ GKI Modules**
   - 虚线灰色双向箭头
   - 内核与 GKI 模块的交互
   - 虚线表示这是模块化的、可选的

7. **GKI Modules ↔ Vendor Modules**
   - 实线灰色双向箭头，标注 "KMI"
   - 通过 KMI 接口进行交互
   - 这是模块间通信的标准接口

## 源码位置

### GKI 配置文件

- **GKI defconfig**：`../common/arch/arm64/configs/gki_defconfig`
- **构建配置**：`../common/build.config.gki.aarch64`
- **模块列表**：`../common/android/gki_aarch64_modules`
- **System DLKM**：`../common/android/gki_system_dlkm_modules`

### 查看 GKI 配置

```powershell
# 查看 GKI defconfig
cd ../common
cat arch/arm64/configs/gki_defconfig | head -50

# 查看 GKI 模块列表
cat android/gki_aarch64_modules

# 查看 System DLKM 列表
cat android/gki_system_dlkm_modules
```

## 实际应用

### 识别 GKI 设备

在你的设备上，可以通过以下方式确认是否为 GKI 设备：

```bash
# 检查 GKI 相关配置
cat /proc/config.gz | zcat | grep -i "GKI"

# 如果看到大量 CONFIG_GKI_HIDDEN_* 配置，说明是 GKI 设备
```

### 与你的性能问题的关联

你遇到的升级问题（2024-05_r2 → 2024-11_r3）可能与 GKI 架构相关：

1. **Generic Kernel 变更**：Generic Kernel 的升级可能改变了内存管理策略
2. **模块兼容性**：Vendor Modules 可能与新版本 Generic Kernel 存在兼容性问题
3. **KMI 接口变更**：KMI 接口的变更可能影响模块行为
4. **模块加载顺序**：模块加载顺序的变化可能影响系统性能

## 总结

### 核心要点

1. **GKI 解决了内核碎片化问题**：通过统一 Generic Kernel，降低碎片化
2. **模块化架构**：将设备特定功能以模块形式组织
3. **KMI 接口**：通过稳定的接口保证兼容性
4. **快速更新**：Generic Kernel 可以独立更新，快速推送安全补丁

### 关键概念

- **Generic Kernel**：通用内核，所有设备共享
- **Vendor Modules**：厂商模块，设备特定功能
- **GKI Modules**：GKI 标准模块，可选功能
- **KMI**：内核模块接口，保证兼容性
- **System DLKM**：系统动态可加载内核模块

### 后续学习

- [Generic Kernel 详解](02-Generic-Kernel详解.md) - 深入理解通用内核的实现
- [GKI Modules 深入解析](03-GKI-Modules深入解析.md) - 掌握 GKI 模块机制
- [KMI 详解](05-KMI-Kernel-Module-Interface详解.md) - 深入理解 KMI 接口

## 参考资料

- [Android GKI 官方文档](https://source.android.com/docs/core/architecture/kernel/generic-kernel-image)
- [GKI 构建配置](../common/build.config.gki.aarch64)
- [GKI defconfig](../common/arch/arm64/configs/gki_defconfig)
- [Android Kernel 架构](https://source.android.com/docs/core/architecture/kernel)

## 更新记录

- 2024-01-21：初始创建，包含 GKI 架构概述和设计理念

---

# Kernel overview



The Android kernel is based on an upstream [Linux Long Term Supported (LTS) kernel](https://www.kernel.org/category/releases.html). At Google, LTS kernels are combined with Android-specific patches to form *Android Common Kernels (ACKs)*.

ACKs are built from the [kernel/common](https://android.googlesource.com/kernel/common) repository. This repository is a superset of the upstream Linux kernel, with additional Android-specific patches.

ACKs that are 5.10 and higher are also known as *generic kernel images (GKI) kernels. GKI kernels support the separation of the hardware-agnostic *generic core kernel* code and [GKI modules](https://source.android.com/docs/core/architecture/kernel/modules#gki-modules) from hardware-specific [vendor modules](https://source.android.com/docs/core/architecture/kernel/modules#vendor-modules).

The interaction between the GKI kernel and vendor modules is enabled by the *Kernel Module Interface (KMI)* consisting of symbol lists identifying the functions and global data required by vendor modules. Figure 1 shows the GKI kernel and vendor module architecture:

![generic-kernel-image-architecture (1)](D:\ACK\ACKLearning\articles\01-GKI架构概述.assets\generic-kernel-image-architecture (1).png)

## Kernel glossary

Following are terms used throughout the kernel documentation.

### Kernel types

- 

- *Android Common Kernel (ACK)*

  A kernel that is downstream of a LTS kernel and includes patches that are important to the Android community. These patches haven't been merged into Linux mainline or Long Term GKI kernels.

Kernel with versions of 5.10 and higher are also referred to as [Generic Kernel Image (GKI)](https://source.android.com/docs/core/architecture/kernel#gkik) kernels.

- *Android Open Source Project (AOSP) kernel*

  See [Android Common Kernel](https://source.android.com/docs/core/architecture/kernel#ack).

Android 12 features can't be backported to 4.19 kernels; the feature set would be similar to a device that launched with 4.19 on Android 11 and upgraded to Android 12.

- 

- *Generic Kernel Image (GKI) kernel*

  Any 5.10 and higher [ACK kernel](https://source.android.com/docs/core/architecture/kernel#ack)(aarch64 only). The GKI kernel has these two parts:*Generic kernel* - The portion of the GKI kernel that is common across all devices.*GKI modules* - Kernel modules built by Google that can be dynamically loaded on devices where applicable. These modules are built as artifacts of the GKI kernel and are delivered alongside GKI as the `system_dlkm_staging_archive.tar.gz` archive. GKI modules are signed by Google using the kernel build time key pair and are compatible only with the GKI kernel that they're built with.

- *Kernel Module Interface (KMI) kernel*

  See [GKI kernel](https://source.android.com/docs/core/architecture/kernel#gkik).

- 

- *Long Term Supported (LTS) kernel*

  A Linux kernel that's supported for 2 to 6 years. [LTS kernels](https://www.kernel.org/category/releases.html) are released once per year and are the basis for each of Google's [Android Common Kernels](https://source.android.com/docs/core/architecture/kernel#ack).

### Branch types

- *ACK KMI kernel branch*

  The branch for which [GKI kernels](https://source.android.com/docs/core/architecture/kernel#gkik) are built. Branch names correspond to kernel versions, such as `android15-6.6`.

- *Android-mainline*

  The primary development branch for Android features. When a new [LTS kernel](https://source.android.com/docs/core/architecture/kernel#lts) is declared upstream, the corresponding new [GKI kernel](https://source.android.com/docs/core/architecture/kernel#gkik)GKI kernel is branched from android-mainline.

*Linux mainline* :The primary development branch for the upstream Linux kernels, including LTS kernels.

### Other terms

- *Certified boot image*

  The kernel delivered in binary form (`boot.img`) and flashed onto the device. This image is considered certified because contains embedded certificates so Google can verify that the device ships with a kernel certified by Google.

- 

- *Dynamically loadable kernel module (DLKM)*

  A module that can be dynamically loaded during device boot depending on the needs of the device. GKI and vendor modules are both types of DLKMs. DLKMs are released in `.ko` form and can be drivers or can deliver other kernel functionality.

- *GKI project*

  A Google project addressing kernel fragmentation by separating common core kernel functionality from vendor-specific SoC and board support into loadable modules.

*Generic Kernel Image (GKI)* :A boot image certified by Google that contains a [GKI kernel](https://source.android.com/docs/core/architecture/kernel#gkik) built from an [ACK](https://source.android.com/docs/core/architecture/kernel#ack) source tree and is suitable to be flashed to the boot partition of an Android-powered device.

- *Kernel Module Interface (KMI)*

  An interface between the [GKI kernel](https://source.android.com/docs/core/architecture/kernel#gkik) and vendor modules allowing vendor modules to be updated independently of the GKI kernel. This interface consists of kernel functions and global data that have been identified as vendor/OEM dependencies using per-partner symbol lists.

- *Vendor module*

  A hardware-specific module developed by a partner and that contains SoC and device-specific functionality. A vendor module is a type of dynamically loadable kernel module.