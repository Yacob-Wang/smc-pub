# Android 分区系统全解析

## 学习目标

- 理解 Android 分区表的设计
- 掌握核心系统分区的作用
- 理解厂商分区的设计
- 了解用户数据分区
- 理解特殊分区的用途
- 掌握 A/B 分区机制
- 理解动态分区机制

## 背景介绍

Android 设备使用分区来组织存储空间，每个分区有特定的用途。理解分区系统是理解 Android 系统架构、启动流程和更新机制的基础。从 Android 8.0 的 Project Treble 开始，分区设计发生了重大变化，引入了更多分区来支持模块化架构。

## 核心概念

### 分区表基础

#### GPT vs MBR

**GPT（GUID Partition Table）**：
- 现代 Android 设备使用 GPT
- 支持更多分区（最多 128 个）
- 更安全，有备份分区表

**MBR（Master Boot Record）**：
- 传统分区表
- 最多 4 个主分区
- 较老的设备可能使用

#### 查看分区表

```bash
# 查看分区表
lsblk

# 查看分区详情
fdisk -l /dev/block/sda

# 查看分区列表
ls -la /dev/block/by-name/
```

### 核心系统分区

#### boot 分区

**作用**：包含内核和初始 ramdisk

**内容**：
- Kernel 镜像（Image）
- Ramdisk（包含 init 和早期启动文件）
- Device Tree Blob (DTB)
- Boot Image Header

**大小**：通常 64-128 MB

**特点**：
- 只读（正常运行时）
- 启动时由 Bootloader 加载
- Android 12+ 可能使用 `vendor_boot` 分离部分内容

#### vendor_boot 分区（Android 12+）

**作用**：包含厂商特定的启动组件

**内容**：
- 厂商 ramdisk
- 设备树覆盖（DTBO）
- 内核模块

**大小**：通常 64-128 MB

**优势**：
- 分离通用内核和厂商代码
- 支持 GKI 架构
- 厂商可以独立更新启动组件

#### system 分区

**作用**：包含 Android 系统框架

**内容**：
- Android 框架代码
- 系统服务
- 系统应用（Settings, SystemUI 等）
- 系统库

**大小**：通常 2-4 GB

**特点**：
- 只读（正常运行时）
- System-as-root 下作为根文件系统
- 由 Google 维护和更新

#### system_ext 分区（Android 10+）

**作用**：系统扩展内容

**内容**：
- 系统扩展应用
- 系统扩展库
- OEM 特定的系统扩展

**大小**：通常 256-512 MB

**用途**：
- 分离系统核心和扩展
- 支持部分系统更新

#### product 分区（Android 10+）

**作用**：产品特定内容

**内容**：
- 产品特定应用
- 产品特定配置
- 产品特定资源

**大小**：通常 256-512 MB

**用途**：
- 支持同一设备的不同产品变体
- 产品特定定制

### 厂商分区

#### vendor 分区

**作用**：包含厂商实现

**内容**：
- HAL 实现
- 厂商驱动
- 厂商库
- 厂商应用

**大小**：通常 512 MB - 2 GB

**特点**：
- 只读（正常运行时）
- 由厂商维护
- Project Treble 后与 system 分离

#### odm 分区（Android 10+）

**作用**：ODM（Original Design Manufacturer）特定内容

**内容**：
- ODM 特定的 HAL
- ODM 特定的驱动
- ODM 特定的配置

**大小**：通常 256-512 MB

**用途**：
- 支持 ODM 定制
- 进一步模块化

#### vendor_dlkm 分区（GKI 设备）

**作用**：厂商动态加载内核模块

**内容**：
- 厂商内核模块（.ko 文件）
- 模块依赖

**大小**：通常 64-128 MB

**关联**：
- 与 GKI 架构相关
- 参考 [GKI Modules 文章](../gki/03-GKI-Modules深入解析.md)

#### odm_dlkm 分区（GKI 设备）

**作用**：ODM 动态加载内核模块

**内容**：
- ODM 内核模块

**大小**：通常 32-64 MB

### 用户数据分区

#### userdata 分区

**作用**：用户数据和应用

**内容**：
- 用户安装的应用
- 用户数据
- 应用数据
- 媒体文件

**大小**：设备剩余空间

**特点**：
- 可读写
- 用户数据的主要存储
- 格式化会清除所有用户数据

#### cache 分区

**作用**：临时缓存

**内容**：
- OTA 更新包
- 临时文件
- 缓存数据

**大小**：通常 256 MB - 1 GB

**特点**：
- 可读写
- 可以安全清除
- 某些设备可能不使用（使用 userdata 的一部分）

### 特殊分区

#### recovery 分区

**作用**：恢复模式

**内容**：
- Recovery 内核
- Recovery ramdisk
- Recovery 工具

**大小**：通常 64-128 MB

**用途**：
- 系统恢复
- OTA 更新（非 A/B 设备）
- 工厂重置

#### vbmeta 分区

**作用**：Verified Boot 元数据

**内容**：
- 分区签名信息
- 哈希树根
- 验证链信息

**大小**：通常 64 KB

**关联**：
- Android Verified Boot (AVB)
- 参考 [验证启动机制文章](12-Android验证启动机制.md)

#### metadata 分区

**作用**：设备元数据

**内容**：
- 设备标识
- 加密密钥
- 其他元数据

**大小**：通常 16-32 MB

**特点**：
- 加密存储
- 设备特定

#### misc 分区

**作用**：杂项信息

**内容**：
- Bootloader 消息
- Recovery 命令
- 其他杂项数据

**大小**：通常 4-16 MB

### A/B 分区机制

#### 设计原理

**双槽设计**：
- 每个分区有两个槽：`_a` 和 `_b`
- 系统运行在一个槽
- OTA 更新写入另一个槽

#### 分区命名

```
boot_a / boot_b
system_a / system_b
vendor_a / vendor_b
...
```

#### 工作流程

1. **正常运行**：系统运行在 Slot A
2. **OTA 更新**：更新写入 Slot B
3. **重启切换**：Bootloader 切换到 Slot B
4. **验证启动**：验证 Slot B 的完整性
5. **成功/失败**：
   - 成功：继续使用 Slot B
   - 失败：回滚到 Slot A

#### 优势

1. **无缝更新**：后台更新，用户无感知
2. **快速回滚**：更新失败可立即恢复
3. **提高可靠性**：减少更新失败风险

### 动态分区（Dynamic Partitions）

#### 设计原理

**超级分区**：
- 创建一个大的 `super` 分区
- 多个逻辑分区共享这个空间
- 分区大小可以动态调整

#### 分区布局

```
super/
├── system_a/
├── system_b/
├── vendor_a/
├── vendor_b/
├── product_a/
├── product_b/
└── ...
```

#### 优势

1. **灵活分配**：根据实际需要分配空间
2. **支持 A/B**：无缝 OTA 更新
3. **节省空间**：避免空间浪费
4. **易于扩展**：可以添加新分区

#### 限制

1. **需要支持**：Bootloader 和 Recovery 必须支持
2. **复杂性**：管理更复杂
3. **工具要求**：需要特殊工具操作

### 分区大小规划

#### 典型分区大小（示例）

| 分区 | 大小 | 说明 |
|------|------|------|
| boot | 64 MB | 内核和 ramdisk |
| vendor_boot | 64 MB | 厂商启动组件 |
| system | 2-4 GB | 系统框架 |
| system_ext | 256 MB | 系统扩展 |
| product | 256 MB | 产品内容 |
| vendor | 512 MB - 2 GB | 厂商实现 |
| odm | 256 MB | ODM 内容 |
| userdata | 剩余空间 | 用户数据 |
| cache | 256 MB - 1 GB | 缓存 |

#### 大小规划原则

1. **system**：足够容纳系统框架和更新
2. **vendor**：足够容纳厂商代码和更新
3. **userdata**：尽可能大，用户数据主要存储
4. **其他**：根据实际需要

## 实际应用

### 查看设备分区

```bash
# 查看所有分区
lsblk

# 查看分区列表
ls -la /dev/block/by-name/

# 查看分区大小
df -h
```

### 查看分区挂载

```bash
# 查看挂载信息
mount | grep -E "system|vendor|product|data"

# 查看挂载表
cat /proc/mounts
```

### 检查 A/B 分区

```bash
# 查看当前槽
getprop ro.boot.slot_suffix

# 查看所有槽
ls /dev/block/by-name/ | grep -E "_a|_b"
```

## 总结

### 核心要点

1. **核心系统分区**：boot, system, system_ext, product
2. **厂商分区**：vendor, odm, vendor_dlkm, odm_dlkm
3. **用户数据分区**：userdata, cache
4. **特殊分区**：recovery, vbmeta, metadata
5. **A/B 分区**：支持无缝更新
6. **动态分区**：灵活的空间管理

### 关键分区

- **boot**：启动分区
- **system**：系统框架
- **vendor**：厂商实现
- **userdata**：用户数据

### 后续学习

- [分区镜像文件格式详解](05-分区镜像文件格式详解.md) - 理解镜像格式
- [分区与挂载点映射关系](06-分区与挂载点映射关系.md) - 理解挂载机制
- [Android启动流程总览](07-Android启动流程总览.md) - 理解启动流程
- [Android存储架构：磁盘分区与文件系统基础](15-Android存储架构：磁盘分区与文件系统基础.md) - 理解存储架构基础

## 参考资料

- [Android 分区架构](https://source.android.com/docs/core/architecture/partitions)
- [动态分区](https://source.android.com/docs/core/architecture/partitions/dynamic-partitions)
- [A/B 分区更新](https://source.android.com/docs/core/ota/ab)

## 更新记录

- 2024-01-22：初始创建，包含 Android 分区系统全解析
