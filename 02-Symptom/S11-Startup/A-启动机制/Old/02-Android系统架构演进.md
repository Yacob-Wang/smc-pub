# Android 系统架构演进

## 学习目标

- 理解 Android 架构的发展历程
- 掌握 Project Treble 的引入和意义
- 理解 GKI（Generic Kernel Image）架构
- 了解 System-as-root 机制
- 理解动态分区和 A/B 分区机制
- 了解不同 Android 版本的架构差异

## 背景介绍

Android 系统架构经历了多次重大演进，从早期的单一系统镜像到现代的模块化架构。这些演进旨在解决系统更新、安全性和碎片化等问题。理解这些演进对于深入理解 Android 系统至关重要。

## 核心概念

### 传统架构（Android 7.x 及之前）

#### 架构特点

**单一系统镜像**：
- 所有系统代码（包括厂商定制）打包在一个 `system.img` 中
- 厂商代码和 AOSP 代码紧密耦合
- 系统更新需要厂商深度参与

**分区布局**：
```
boot/
system/          # 包含所有系统代码和厂商代码
vendor/          # 部分厂商代码（可选）
userdata/
cache/
```

**问题**：
1. **更新困难**：系统更新需要厂商适配整个系统
2. **碎片化严重**：不同设备的内核和系统差异巨大
3. **安全补丁延迟**：安全更新需要等待厂商发布

### Project Treble（Android 8.0+）

#### 引入背景

**目标**：分离系统框架和厂商实现，简化系统更新

#### 架构变化

**分离系统分区**：
```
system/          # AOSP 系统框架（只读）
vendor/          # 厂商实现（HAL、驱动等）
```

**HAL 接口标准化**：
- 使用 HIDL（Hardware Interface Definition Language）
- 定义稳定的 HAL 接口
- 厂商通过 HAL 接口与系统交互

**优势**：
1. **快速更新**：系统框架可以独立更新
2. **降低碎片化**：统一的 HAL 接口
3. **简化开发**：厂商只需维护 HAL 实现

#### Treble 架构图

```
┌─────────────────────────────────────┐
│      Android Framework              │
│      (system.img)                   │
└──────────────┬──────────────────────┘
               │ HIDL Interface
┌──────────────▼──────────────────────┐
│      Vendor Implementation           │
│      (vendor.img)                    │
│      - HAL                           │
│      - Drivers                       │
└─────────────────────────────────────┘
```

### GKI（Generic Kernel Image）- Android 11+

#### 引入背景

**问题**：
- 即使有了 Treble，内核仍然高度定制化
- 内核更新仍然需要厂商适配
- 内核安全补丁难以快速推送

#### GKI 架构

**通用内核**：
- 所有设备使用相同的内核二进制（Generic Kernel）
- 内核由 Google 统一维护和更新
- 设备特定代码以模块形式加载

**模块化设计**：
```
Generic Kernel (boot.img)
    ├── GKI Modules (system_dlkm)
    └── Vendor Modules (vendor_dlkm)
```

**优势**：
1. **统一内核**：所有设备使用相同内核
2. **快速更新**：内核更新可以直接推送
3. **安全补丁**：内核安全补丁快速部署
4. **简化开发**：厂商只需维护模块

**关联知识**：
- 参考 [GKI 架构系列文章](../gki/01-GKI架构概述.md)

### System-as-root（Android 9+）

#### 传统启动方式

**Ramdisk 作为根**：
```
Kernel → Ramdisk (/) → 挂载 system/ → 切换根到 system/
```

**问题**：
- Ramdisk 占用额外空间
- 启动流程复杂
- 需要切换根文件系统

#### System-as-root 机制

**System 分区作为根**：
```
Kernel → System (/) → 直接启动
```

**架构变化**：
- System 分区直接作为根文件系统
- Ramdisk 内容合并到 System 分区
- 简化启动流程

**优势**：
1. **简化启动**：减少启动步骤
2. **节省空间**：不需要单独的 Ramdisk
3. **统一管理**：所有系统文件在一个分区

### 动态分区（Dynamic Partitions）- Android 10+

#### 传统分区问题

**固定分区大小**：
- 每个分区大小固定
- 无法动态调整
- 空间浪费或不足

#### 动态分区机制

**超级分区（Super Partition）**：
```
super/
├── system_a/
├── system_b/
├── vendor_a/
├── vendor_b/
└── ...
```

**特点**：
- 多个逻辑分区共享物理空间
- 分区大小可以动态调整
- 支持 A/B 分区

**优势**：
1. **灵活分配**：根据实际需要分配空间
2. **支持 A/B**：无缝 OTA 更新
3. **节省空间**：避免空间浪费

### A/B 分区机制（Android 7.0+）

#### 设计目标

**无缝更新**：在后台更新系统，无需重启到 Recovery

#### 分区布局

**双槽设计**：
```
boot_a/  boot_b/
system_a/  system_b/
vendor_a/  vendor_b/
...
```

**工作原理**：
1. 系统运行在 Slot A
2. OTA 更新写入 Slot B
3. 重启后切换到 Slot B
4. 如果失败，可以回滚到 Slot A

**优势**：
1. **无缝更新**：用户无感知更新
2. **快速回滚**：更新失败可快速恢复
3. **提高可靠性**：减少更新失败风险

### 不同 Android 版本的架构差异

#### Android 7.x 及之前

- **单一系统镜像**
- **固定分区**
- **传统启动方式**

#### Android 8.0-8.1（Project Treble）

**架构特点**：
- **分离 system/vendor**：系统框架和厂商实现分离
- **HIDL 接口**：硬件接口定义语言
- **固定分区**：分区大小固定
- **传统启动方式**：Ramdisk 作为根

**关键变化**：

1. **Project Treble 引入**：
   - 系统框架（system）和厂商实现（vendor）完全分离
   - 通过版本化接口（VINTF）确保兼容性
   - 系统框架可以独立更新

2. **HIDL（Hardware Interface Definition Language）**：
   - 定义稳定的 HAL 接口
   - 支持接口版本化
   - 厂商通过 HIDL 接口与系统交互

3. **分区布局**：
   ```
   boot/
   system/          # AOSP 系统框架（只读）
   vendor/          # 厂商实现（HAL、驱动等）
   userdata/
   cache/
   ```

4. **优势**：
   - 系统更新不再需要厂商深度参与
   - 降低系统碎片化
   - 简化厂商开发工作

#### Android 9.0（System-as-root）

**架构特点**：
- **System-as-root**：System 分区作为根文件系统
- **分离 system/vendor**：继续使用 Treble 架构
- **HIDL 接口**：继续使用
- **固定分区**：分区大小仍固定

**关键变化**：

1. **System-as-root 引入**：
   - System 分区直接作为根文件系统（/）
   - Ramdisk 内容合并到 System 分区
   - 简化启动流程，减少启动步骤

2. **启动流程变化**：
   ```
   传统方式：Kernel → Ramdisk (/) → 挂载 system/ → 切换根到 system/
   Android 9：Kernel → System (/) → 直接启动
   ```

3. **优势**：
   - 启动流程简化
   - 节省存储空间（不需要单独的 Ramdisk）
   - 统一管理所有系统文件

4. **分区布局**：
   ```
   boot/              # 包含内核和合并后的 ramdisk
   system/            # 作为根文件系统（/）
   vendor/            # 厂商实现
   userdata/
   cache/
   ```

#### Android 10（动态分区）

**架构特点**：
- **System-as-root**：继续使用
- **动态分区**：引入超级分区机制
- **分离 system/vendor**：继续使用 Treble 架构
- **HIDL/AIDL 接口**：AIDL 开始引入

**关键变化**：

1. **动态分区引入**：
   - 引入超级分区（Super Partition）
   - 多个逻辑分区共享物理空间
   - 分区大小可以动态调整
   - 支持 A/B 分区

2. **分区布局变化**：
   ```
   super/             # 超级分区（新）
   ├── system_a/
   ├── system_b/
   ├── vendor_a/
   ├── vendor_b/
   └── ...
   ```

3. **AIDL 开始引入**：
   - Android Interface Definition Language
   - 作为 HIDL 的补充和未来替代
   - 更简洁的接口定义

4. **优势**：
   - 灵活的空间分配
   - 支持无缝 OTA 更新
   - 避免空间浪费

#### Android 11（GKI 引入）

**架构特点**：
- **System-as-root**：继续使用
- **动态分区**：继续使用
- **GKI 架构**：首次引入通用内核镜像
- **分离 system/vendor**：继续使用 Treble 架构
- **HIDL/AIDL 接口**：AIDL 继续发展
- **Shared System Image (SSI)**：引入共享系统镜像

**关键变化**：

1. **GKI（Generic Kernel Image）引入**：
   - 所有设备使用相同的内核二进制
   - 内核由 Google 统一维护
   - 设备特定代码以模块形式加载
   - 基于 Linux 5.4+ LTS 内核

2. **模块化设计**：
   ```
   Generic Kernel (boot.img)
       ├── GKI Modules (system_dlkm)
       └── Vendor Modules (vendor_dlkm)
   ```

3. **Shared System Image (SSI)**：
   - 引入 `/product` 分区
   - OEM 可以构建一个 SSI 用于多个设备 SKU
   - 产品特定组件放在 product 分区

4. **分区布局**：
   ```
   boot/              # GKI 内核
   super/
   ├── system_a/
   ├── system_b/
   ├── vendor_a/
   ├── vendor_b/
   ├── product_a/    # 产品特定组件（新）
   └── product_b/
   ```

5. **优势**：
   - 统一内核，简化更新
   - 内核安全补丁快速部署
   - 厂商只需维护模块

#### Android 12（GKI 2.0）

**架构特点**：
- **System-as-root**：继续使用
- **动态分区**：完全支持
- **GKI 2.0**：更严格的模块化要求
- **Vendor Boot 分离**：vendor_boot 分区独立
- **HIDL/AIDL 接口**：继续演进

**关键变化**：
1. **GKI 2.0 增强**：
   - 更严格的 KMI（Kernel Module Interface）要求
   - 模块接口更加稳定
   - 更好的模块隔离

2. **Vendor Boot 分区**：
   - 将 vendor 相关的启动文件从 boot 分区分离
   - vendor_boot 包含 vendor ramdisk 和模块
   - boot 分区只包含 GKI 内核

3. **模块化增强**：
   - 更清晰的模块边界
   - 更好的模块依赖管理

#### Android 13（GKI 成熟期）

**架构特点**：
- **System-as-root**：继续使用
- **动态分区**：继续使用
- **GKI 成熟**：android13-5.15 内核
- **init_boot 分区**：引入新的启动分区
- **Virtual A/B 要求**：新设备必须支持
- **DLKM 分区**：vendor_dlkm、odm_dlkm 等

**关键变化**：

1. **init_boot 分区引入**：
   - 将通用 ramdisk 从 boot 分区分离
   - boot 分区只包含 GKI 内核
   - init_boot 包含通用初始化代码
   - 简化启动流程，提高灵活性

2. **Virtual A/B 分区要求**：
   - 新设备必须支持 Virtual A/B
   - 实现无缝 OTA 更新
   - 支持快照和回滚机制

3. **DLKM（Dynamically Loadable Kernel Modules）分区**：
   - **vendor_dlkm**：厂商内核模块
   - **odm_dlkm**：ODM 内核模块
   - 模块可以独立更新，无需更新父分区

4. **分区布局演进**：
   ```
   boot/              # 只包含 GKI 内核
   init_boot/         # 通用 ramdisk（新）
   vendor_boot/       # Vendor ramdisk 和模块
   system/
   vendor/
   product/
   system_ext/
   vendor_dlkm/       # Vendor 内核模块（新）
   odm_dlkm/         # ODM 内核模块（新）
   ```

5. **GKI 内核版本**：
   - 使用 `android13-5.15` 内核
   - 基于 Linux 5.15 LTS
   - 统一的 KMI 接口

#### Android 14（GKI 全面要求）

**架构特点**：
- **System-as-root**：继续使用
- **动态分区**：继续使用
- **GKI 强制要求**：所有主要设备类型必须使用
- **内核版本**：android14-6.1（主要）和 android14-5.15（兼容）
- **受保护 GKI 模块**：引入模块保护机制
- **并行模块加载**：支持并行加载内核模块

**关键变化**：

1. **GKI 全面要求**：
   - **所有主要设备类型必须使用 GKI**：
     - 手持设备（Handhelds）
     - 智能手表（Watches）
     - 汽车（Automotive）
     - 电视（Televisions）
   - 要求 AArch64 芯片组
   - 要求内核 5.15 或更高版本

2. **双内核版本支持**：
   - **android14-6.1**：主要启动内核（基于 Linux 6.1 LTS）
   - **android14-5.15**：兼容启动内核（基于 Linux 5.15 LTS）
   - 同一内核版本可以支持多个 Android 版本

3. **受保护 GKI 模块机制**：
   - **受保护模块**：构建时签名，不能被厂商模块覆盖
   - **未受保护模块**：可以被厂商驱动替换
   - 允许厂商在 KMI 冻结后集成新功能
   - 限制对 KMI 符号的访问

4. **并行模块加载**：
   - 通过 `androidboot.load_modules_parallel` 启用
   - 加速启动过程
   - 提高模块加载效率

5. **符号检查增强**：
   - 激活内核符号检查
   - 防止未使用的符号被裁剪（CONFIG_TRIM_UNUSED_KSYMS）
   - 确保厂商模块可以访问所需的 GKI 模块符号

6. **ACK DDK（Android Common Kernel Developer Kit）**：
   - 帮助厂商开发 GKI 模块
   - 提供正确的工具链使用
   - 确保 GKI 内核资源的可见性

#### Android 15（16KB 页面支持）

**架构特点**：
- **System-as-root**：继续使用
- **动态分区**：继续使用
- **GKI 继续演进**：android15-6.6 内核
- **16KB 内存页面**：重大底层变化
- **模块保护增强**：继续完善
- **性能优化**：启动和运行性能提升

**关键变化**：

1. **内核版本升级**：
   - **android15-6.6**：基于 Linux 6.6 LTS
   - 继续统一内核架构
   - KMI 接口保持稳定

2. **16KB 内存页面支持**（重大变化）：
   - **从 4KB 升级到 16KB**：标准页面大小变化
   - **性能提升**：
     - 应用启动速度平均提升 ~3.16%（最高 30%）
     - 电池效率提升 4-6%
     - 启动时间减少 ~0.8 秒
     - 减少页面错误、TLB 未命中和页表开销
   - **对开发者的影响**：
     - 仅影响原生代码（NDK/C++）
     - 纯 Java/Kotlin 应用不受影响
     - 2025年11月1日后，针对 Android 15+ 的新应用必须支持 16KB 页面
     - 不支持的应用将被 Google Play 拒绝

3. **GKI 模块机制继续完善**：
   - 受保护/未受保护模块机制继续优化
   - 更好的模块依赖管理
   - 改进的符号导出机制

4. **性能优化**：
   - 启动流程优化
   - 内存管理改进
   - I/O 性能提升

#### Android 16（未来演进）

**架构特点**（基于当前趋势预测）：
- **System-as-root**：继续使用
- **动态分区**：继续使用
- **GKI 持续演进**：预计使用更新的 LTS 内核
- **16KB 页面成为标准**：全面要求
- **安全增强**：继续加强安全机制
- **性能优化**：持续优化

**预期变化**：

1. **内核版本**：
   - 预计使用更新的 Linux LTS 内核
   - 继续统一内核架构

2. **16KB 页面全面要求**：
   - 所有新设备必须支持 16KB 页面
   - 所有应用必须兼容

3. **安全增强**：
   - 更强的模块签名验证
   - 更严格的权限控制
   - 增强的隔离机制

4. **性能持续优化**：
   - 启动时间进一步优化
   - 内存使用优化
   - I/O 性能提升

## 架构演进的影响

### 对分区设计的影响

1. **分区数量增加**：从简单的几个分区到复杂的动态分区
2. **分区角色变化**：System 分区从包含所有到只包含框架
3. **新分区出现**：vendor_boot, system_ext, product 等

### 对启动流程的影响

1. **启动简化**：System-as-root 简化启动
2. **验证增强**：AVB 验证更严格
3. **模块加载**：GKI 模块动态加载

### 对更新的影响

1. **更新更快**：模块化架构支持部分更新
2. **更新更安全**：A/B 分区支持回滚
3. **更新更灵活**：动态分区支持空间调整

## 实际应用

### 识别设备架构版本

```bash
# 检查是否支持 Treble
getprop ro.treble.enabled

# 检查是否使用 GKI
cat /proc/config.gz | zcat | grep CONFIG_GKI

# 检查分区布局
ls -la /dev/block/by-name/
```

### 理解设备分区

```bash
# 查看所有分区
lsblk

# 查看挂载信息
mount | grep -E "system|vendor|product"
```

## 总结

### 核心要点

1. **Project Treble** 分离了系统框架和厂商实现
2. **GKI** 统一了内核，简化了内核更新
3. **System-as-root** 简化了启动流程
4. **动态分区** 提供了灵活的空间管理
5. **A/B 分区** 实现了无缝更新

### 关键演进时间线

- **Android 8.0**：Project Treble - 分离系统框架和厂商实现
- **Android 9.0**：System-as-root - System 分区作为根文件系统
- **Android 10**：动态分区 - 引入超级分区机制
- **Android 11**：GKI 引入 - 通用内核镜像架构
- **Android 12**：GKI 2.0 - Vendor Boot 分离，模块化增强
- **Android 13**：init_boot 分区，Virtual A/B 要求，DLKM 分区
- **Android 14**：GKI 全面要求，6.1 内核，受保护模块机制
- **Android 15**：6.6 内核，16KB 内存页面支持
- **Android 16**：持续演进（预计）

### 后续学习

- [GKI 架构系列](../gki/01-GKI架构概述.md) - 深入理解 GKI
- [Android分区系统全解析](04-Android分区系统全解析.md) - 理解分区设计
- [Android启动流程总览](07-Android启动流程总览.md) - 理解启动流程

## 参考资料

- [Project Treble](https://source.android.com/docs/core/architecture/hidl)
- [GKI 架构](https://source.android.com/docs/core/architecture/kernel/generic-kernel-image)
- [System-as-root](https://source.android.com/docs/core/architecture/partitions/system-as-root)
- [动态分区](https://source.android.com/docs/core/architecture/partitions/dynamic-partitions)

## 更新记录

- 2024-01-22：初始创建，包含 Android 系统架构演进详解
- 2025-01-22：补充 Android 13-16 的详细架构变化，包括：
  - Android 13：init_boot 分区、Virtual A/B 要求、DLKM 分区
  - Android 14：GKI 全面要求、6.1 内核、受保护模块机制
  - Android 15：6.6 内核、16KB 内存页面支持
  - Android 16：未来演进方向
  - 扩展了每个版本的详细架构变化说明
