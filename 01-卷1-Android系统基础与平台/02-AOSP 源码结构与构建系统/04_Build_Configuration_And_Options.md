# 编译配置和选项

## 📋 目录

1. [BoardConfig.mk配置](#1-boardconfigmk配置)
2. [device.mk配置](#2-devicemk配置)
3. [分区大小配置](#3-分区大小配置)
4. [编译选项说明](#4-编译选项说明)
5. [动态分区配置](#5-动态分区配置)
6. [A/B分区配置](#6-ab分区配置)
7. [文件系统选择](#7-文件系统选择)

---

## 1. BoardConfig.mk配置

### 1.1 基本配置

`BoardConfig.mk` 位于 `device/{vendor}/{device}/BoardConfig.mk`

**架构配置**：
```makefile
# 目标架构
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_VARIANT := generic
TARGET_CPU_ABI := arm64-v8a

# 32位支持（如果需要）
TARGET_2ND_ARCH := arm
TARGET_2ND_ARCH_VARIANT := armv8-a
TARGET_2ND_CPU_VARIANT := generic
TARGET_2ND_CPU_ABI := armeabi-v7a
```

### 1.2 分区大小配置

```makefile
# Boot分区大小
BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864  # 64MB

# Init Boot分区大小
BOARD_INIT_BOOT_IMAGE_PARTITION_SIZE := 8388608  # 8MB

# Vendor Boot分区大小
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 67108864  # 64MB

# Dtbo分区大小
BOARD_DTBOIMG_PARTITION_SIZE := 8388608  # 8MB

# System分区大小（如果使用静态分区）
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 3221225472  # 3GB

# Vendor分区大小
BOARD_VENDORIMAGE_PARTITION_SIZE := 536870912  # 512MB

# Product分区大小
BOARD_PRODUCTIMAGE_PARTITION_SIZE := 536870912  # 512MB

# System Ext分区大小
BOARD_SYSTEM_EXTIMAGE_PARTITION_SIZE := 268435456  # 256MB

# ODM分区大小
BOARD_ODMIMAGE_PARTITION_SIZE := 268435456  # 256MB

# Userdata分区大小
BOARD_USERDATAIMAGE_PARTITION_SIZE := 48318382080  # 45GB

# Cache分区大小
BOARD_CACHEIMAGE_PARTITION_SIZE := 1073741824  # 1GB
```

### 1.3 文件系统配置

```makefile
# System分区文件系统
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := ext4
# 或
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := erofs

# Vendor分区文件系统
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := ext4

# Userdata分区文件系统
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := f2fs
# 或
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := ext4
```

### 1.4 分区对齐配置

```makefile
# 擦除块大小
BOARD_FLASH_BLOCK_SIZE := 4096

# 分区对齐（自动计算，通常不需要手动设置）
```

---

## 2. device.mk配置

### 2.1 产品配置

`device.mk` 位于 `device/{vendor}/{device}/device.mk`

**基本产品信息**：
```makefile
# 产品名称
PRODUCT_NAME := my_device
PRODUCT_DEVICE := my_device
PRODUCT_BRAND := MyBrand
PRODUCT_MANUFACTURER := MyManufacturer
PRODUCT_MODEL := My Device Model
```

### 2.2 分区列表定义

```makefile
# 定义分区列表
PRODUCT_BUILD_SYSTEM_IMAGE := true
PRODUCT_BUILD_VENDOR_IMAGE := true
PRODUCT_BUILD_PRODUCT_IMAGE := true
PRODUCT_BUILD_SYSTEM_EXT_IMAGE := true
PRODUCT_BUILD_ODM_IMAGE := true
```

### 2.3 分区挂载配置

```makefile
# 分区挂载点配置（在fstab中）
PRODUCT_COPY_FILES += \
    device/{vendor}/{device}/fstab.qcom:$(TARGET_COPY_OUT_VENDOR)/etc/fstab.qcom
```

### 2.4 包配置

```makefile
# System分区包
PRODUCT_PACKAGES += \
    app1 \
    app2

# System Ext分区包
PRODUCT_PACKAGES += \
    system_ext:module1 \
    system_ext:module2

# Product分区包
PRODUCT_PACKAGES += \
    product:app1 \
    product:app2

# Vendor分区包
PRODUCT_PACKAGES += \
    android.hardware.camera.provider@2.4-service \
    vendor.specific.binary
```

---

## 3. 分区大小配置

### 3.1 大小计算原则

1. **基于实际大小**：编译产物大小 × 1.2-1.3（预留更新空间）
2. **对齐要求**：必须是擦除块大小的倍数
3. **A/B槽位**：每个槽位都需要空间

### 3.2 大小配置示例

```makefile
# 计算示例
# system编译产物: 2.5GB
# 预留30%空间: 2.5GB × 1.3 = 3.25GB
# 对齐到1GB: 4GB
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 4294967296  # 4GB

# 对于A/B设备，每个槽位需要4GB
# 总system空间: 4GB × 2 = 8GB（在super分区中）
```

### 3.3 动态分区大小

```makefile
# Super分区总大小
BOARD_SUPER_PARTITION_SIZE := 17179869184  # 16GB

# Super分区组
BOARD_SUPER_PARTITION_GROUPS := group_a group_b

# 每个组的大小
BOARD_GROUP_A_SIZE := 8589934592  # 8GB
BOARD_GROUP_B_SIZE := 8589934592  # 8GB

# 组内分区列表
BOARD_GROUP_A_PARTITION_LIST := system vendor product system_ext
BOARD_GROUP_B_PARTITION_LIST := system vendor product system_ext
```

---

## 4. 编译选项说明

### 4.1 TARGET_* 变量

```makefile
# 目标构建类型
TARGET_BUILD_TYPE := release  # 或 debug

# 目标变体
TARGET_BUILD_VARIANT := user  # user, userdebug, eng

# 目标产品
TARGET_PRODUCT := aosp_arm64

# 目标架构
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_VARIANT := generic
```

### 4.2 编译优化选项

```makefile
# 启用优化
TARGET_OPTIMIZE := true

# 编译标志
TARGET_GLOBAL_CFLAGS += -O2
TARGET_GLOBAL_CPPFLAGS += -O2

# 链接优化
TARGET_LINKER := gold
```

### 4.3 调试选项

```makefile
# 启用调试符号
TARGET_STRIP := false

# 启用调试信息
TARGET_DEBUG := true

# 启用GDB支持
TARGET_GDB := true
```

---

## 5. 动态分区配置

### 5.1 启用动态分区

```makefile
# 启用动态分区
BOARD_SUPER_PARTITION_ENABLE := true

# Super分区大小
BOARD_SUPER_PARTITION_SIZE := 17179869184  # 16GB

# 元数据大小
BOARD_SUPER_PARTITION_METADATA_DEVICE := super
```

### 5.2 配置分区组

```makefile
# 定义分区组
BOARD_SUPER_PARTITION_GROUPS := group_a group_b

# 组大小
BOARD_GROUP_A_SIZE := 8589934592  # 8GB
BOARD_GROUP_B_SIZE := 8589934592  # 8GB

# 组内分区
BOARD_GROUP_A_PARTITION_LIST := \
    system \
    vendor \
    product \
    system_ext

BOARD_GROUP_B_PARTITION_LIST := \
    system \
    vendor \
    product \
    system_ext
```

### 5.3 分区大小限制

```makefile
# 设置分区最大大小（在组内）
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 3221225472  # 3GB per slot
BOARD_VENDORIMAGE_PARTITION_SIZE := 536870912   # 512MB per slot
BOARD_PRODUCTIMAGE_PARTITION_SIZE := 536870912  # 512MB per slot
```

---

## 6. A/B分区配置

### 6.1 启用A/B分区

```makefile
# 启用A/B分区
AB_OTA_UPDATER := true

# A/B分区标志
AB_OTA_PARTITIONS := \
    boot \
    system \
    vendor \
    product
```

### 6.2 配置A/B槽位

```makefile
# 当前槽位（运行时确定）
# 通过 ro.boot.slot_suffix 属性获取

# A/B更新支持的分区
AB_OTA_PARTITIONS += \
    boot \
    init_boot \
    vendor_boot \
    system \
    vendor \
    product \
    system_ext \
    odm
```

### 6.3 A/B更新配置

```makefile
# OTA更新包类型
TARGET_OTA_ASSERT_DEVICE := my_device

# 更新脚本
AB_OTA_POSTINSTALL_CONFIG += \
    RUN_POSTINSTALL_system=true \
    POSTINSTALL_PATH_system=bin/check_gki_compatibility \
    FILESYSTEM_TYPE_system=ext4 \
    POSTINSTALL_OPTIONAL_system=true
```

---

## 7. 文件系统选择

### 7.1 ext4

**特点**：
- 成熟稳定
- 支持日志
- 兼容性好

**配置**：
```makefile
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := ext4
TARGET_USERIMAGES_USE_EXT4 := true
```

### 7.2 erofs

**特点**：
- 只读文件系统
- 压缩率高
- 性能好

**配置**：
```makefile
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := erofs
TARGET_USERIMAGES_USE_EROFS := true

# 压缩算法
BOARD_EROFS_COMPRESSOR := lz4hc
```

### 7.3 f2fs

**特点**：
- 针对闪存优化
- 适合读写频繁的分区

**配置**：
```makefile
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := f2fs
TARGET_USERIMAGES_USE_F2FS := true
```

### 7.4 文件系统选择建议

| 分区 | 推荐文件系统 | 原因 |
|------|------------|------|
| system | erofs | 只读，压缩率高 |
| vendor | erofs | 只读，压缩率高 |
| product | erofs | 只读，压缩率高 |
| userdata | f2fs | 读写频繁，闪存优化 |
| cache | f2fs | 读写频繁 |

---

## 总结

编译配置要点：

1. **BoardConfig.mk**：硬件和分区配置
2. **device.mk**：产品和包配置
3. **分区大小**：基于实际大小 + 预留空间
4. **动态分区**：使用super分区容器
5. **A/B分区**：支持无缝更新
6. **文件系统**：erofs用于只读，f2fs用于读写

**配置文件位置**：
- `device/{vendor}/{device}/BoardConfig.mk`
- `device/{vendor}/{device}/device.mk`
- `device/{vendor}/{device}/AndroidProducts.mk`

**下一步学习**：
- 了解系统集成，请阅读 [系统组成和启动](../03_System_Integration/01_System_Composition_And_Boot.md)
- 了解OTA更新，请阅读 [OTA更新机制](../04_Dynamic_Updates/01_OTA_Update_Mechanism.md)
