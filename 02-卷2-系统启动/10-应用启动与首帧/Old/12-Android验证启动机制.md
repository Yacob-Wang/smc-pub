# Android 验证启动机制

## 学习目标

- 理解 Verified Boot (AVB) 的作用和原理
- 掌握 vbmeta 分区的作用
- 理解分区签名和验证流程
- 了解 dm-verity 机制
- 理解启动链验证流程
- 掌握安全启动失败处理

## 背景介绍

Android Verified Boot (AVB) 是 Android 的安全机制，用于验证系统完整性，防止恶意代码和篡改。理解验证启动机制，对于理解 Android 安全架构、调试启动问题、进行安全分析都至关重要。

## 核心概念

### Verified Boot 概述

#### 设计目标

**1. 完整性验证**
- 验证分区未被篡改
- 确保系统代码完整性
- 防止恶意代码注入

**2. 启动链验证**
- 验证整个启动链
- 从 Bootloader 到系统
- 确保每个环节可信

**3. 安全启动**
- 防止未授权修改
- 保护系统安全
- 支持安全更新

#### AVB 版本

**AVB 1.0**：
- 基础验证功能
- 分区签名验证

**AVB 2.0**：
- 增强的验证功能
- 支持 A/B 分区
- 支持回滚保护

### vbmeta 分区

#### 作用

**存储验证元数据**：
- 分区描述符
- 哈希树根
- 签名信息
- 验证链信息

#### vbmeta 结构

**主要内容**：
- **分区描述符**：描述每个分区的验证信息
- **哈希树根**：dm-verity 哈希树根
- **签名**：分区签名
- **公钥**：验证公钥
- **回滚索引**：防止回滚攻击

#### vbmeta 格式

**VBMeta Image Header**：
```
struct AvbVBMetaImageHeader {
    uint8_t magic[4];           // "AVB0"
    uint32_t required_libavb_version_major;
    uint32_t required_libavb_version_minor;
    uint64_t authentication_data_block_size;
    uint64_t auxiliary_data_block_size;
    uint32_t algorithm_type;
    uint64_t hash_offset;
    uint64_t hash_size;
    uint64_t signature_offset;
    uint64_t signature_size;
    uint64_t public_key_offset;
    uint64_t public_key_size;
    uint64_t public_key_metadata_offset;
    uint64_t public_key_metadata_size;
    uint64_t descriptors_offset;
    uint64_t descriptors_size;
    uint64_t rollback_index;
    uint32_t flags;
    uint32_t rollback_index_location;
    uint8_t release_string[AVB_RELEASE_STRING_SIZE];
    uint8_t reserved[80];
}
```

### 分区签名和验证

#### 签名流程

**构建时**：
1. 生成分区哈希
2. 使用私钥签名
3. 将签名存储在 vbmeta
4. 将公钥存储在 vbmeta

**启动时**：
1. Bootloader 读取 vbmeta
2. 验证 vbmeta 签名
3. 验证分区哈希
4. 允许或阻止启动

#### 验证模式

**严格模式（Enforcing）**：
- 验证失败阻止启动
- 显示错误信息
- 进入 Recovery 模式

**警告模式（Warning）**：
- 验证失败允许启动
- 显示警告信息
- 标记为未验证状态

#### 验证链

**启动链验证**：
```
Bootloader
    ↓ 验证
vbmeta
    ↓ 验证
boot
    ↓ 验证
system (通过 dm-verity)
    ↓ 验证
vendor (通过 dm-verity)
    ...
```

### dm-verity 机制

#### 作用

**运行时验证**：
- 验证文件系统块
- 防止运行时篡改
- 持续保护系统

#### 工作原理

**1. 构建时生成哈希树**
- 为每个文件系统块计算哈希
- 构建哈希树
- 存储哈希树根

**2. 运行时验证**
- 读取块时验证哈希
- 验证失败阻止访问
- 记录验证错误

#### 哈希树结构

```
Root Hash
    ├── Hash 1
    │   ├── Block Hash 1
    │   └── Block Hash 2
    └── Hash 2
        ├── Block Hash 3
        └── Block Hash 4
```

#### 配置

**fstab 标志**：
```text
avb=vbmeta_system
```

**dm-verity 设备**：
- 创建虚拟设备
- 透明验证
- 对上层透明

### 启动链验证流程

#### Bootloader 验证

**1. 验证 vbmeta**
- 读取 vbmeta 分区
- 验证 vbmeta 签名
- 检查回滚索引

**2. 验证 boot**
- 从 vbmeta 获取 boot 验证信息
- 验证 boot 分区
- 加载内核

**3. 验证其他分区**
- 从 vbmeta 获取分区验证信息
- 设置验证参数
- 传递给内核

#### 内核验证

**1. 设置 dm-verity**
- 读取验证参数
- 创建 dm-verity 设备
- 设置验证规则

**2. 挂载分区**
- 通过 dm-verity 挂载
- 透明验证
- 验证失败阻止访问

### 安全启动失败处理

#### 验证失败场景

**1. vbmeta 验证失败**
- 签名无效
- 公钥不匹配
- 回滚索引错误

**2. 分区验证失败**
- 哈希不匹配
- 分区被篡改
- 验证信息错误

**3. dm-verity 验证失败**
- 文件系统块被篡改
- 哈希树损坏
- 运行时篡改

#### 失败处理

**严格模式**：
- 阻止启动
- 显示错误信息
- 进入 Recovery 模式

**警告模式**：
- 允许启动
- 显示警告
- 标记未验证状态

#### 恢复方法

**1. 刷入正确镜像**
- 使用 fastboot 刷入
- 恢复原始分区
- 重新验证

**2. 清除验证**
- 解锁 Bootloader（开发设备）
- 禁用验证（开发模式）
- 重新刷入

## 实际应用

### 查看验证状态

```bash
# 查看 AVB 状态
getprop ro.boot.vbmeta.device_state

# 查看验证模式
getprop ro.boot.verifiedbootstate

# 查看 vbmeta 信息
avbtool info_image --image vbmeta.img
```

### 分析验证问题

```bash
# 查看启动日志
dmesg | grep -i "avb\|verity"

# 查看验证错误
logcat -b all | grep -i "avb\|verity"
```

### 验证分区

```bash
# 验证 vbmeta
avbtool verify_image --image vbmeta.img

# 验证分区哈希
avbtool calculate_vbmeta_digest --image vbmeta.img
```

## 总结

### 核心要点

1. **AVB 提供完整性验证**：防止系统被篡改
2. **vbmeta 存储验证信息**：分区描述符、签名、哈希树根
3. **启动链验证**：从 Bootloader 到系统
4. **dm-verity 提供运行时保护**：持续验证文件系统
5. **验证失败处理**：严格模式阻止启动，警告模式允许但标记

### 关键机制

- **AVB**：Android Verified Boot
- **vbmeta**：验证元数据分区
- **dm-verity**：运行时验证
- **启动链**：完整的验证链

### 后续学习

- [分区镜像文件格式详解](05-分区镜像文件格式详解.md) - 理解 vbmeta 格式
- [Bootloader到Kernel启动](08-Bootloader到Kernel启动.md) - 理解验证流程
- [OTA更新与分区管理](13-OTA更新与分区管理.md) - 理解安全更新

## 参考资料

- [Android Verified Boot](https://source.android.com/docs/security/features/verifiedboot)
- [AVB 工具](https://source.android.com/docs/security/features/verifiedboot/avb)
- [dm-verity](https://source.android.com/docs/security/features/verifiedboot/dm-verity)

## 更新记录

- 2024-01-22：初始创建，包含 Android 验证启动机制详解
