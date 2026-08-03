# Android 构建系统基础

## 学习目标

- 理解 Android 构建系统的组成
- 掌握 Soong 和 Make 构建系统
- 理解 BoardConfig.mk 和设备配置
- 了解如何定义分区布局
- 理解镜像文件的生成过程
- 掌握构建输出目录的分析

## 背景介绍

Android 构建系统负责将数百万行源代码编译成可以在设备上运行的镜像文件。理解构建系统的工作原理，有助于理解 Android 系统的组织方式，以及如何定制和构建自己的 Android 系统。

## 核心概念

### 构建系统架构

#### 双构建系统

Android 使用两套构建系统：

1. **Make 构建系统**（传统）
   - 基于 GNU Make
   - 用于遗留代码和兼容性
   - 配置文件：`Android.mk`

2. **Soong 构建系统**（现代）
   - 基于 Blueprint（Go 语言）
   - 用于新代码
   - 配置文件：`Android.bp`

#### 构建系统关系

```
Blueprint (解析器)
    ↓
Soong (构建系统)
    ↓
Make (兼容层)
    ↓
构建输出
```

### Soong 构建系统

#### Android.bp 文件格式

**基本语法**：
```json
cc_library {
    name: "libexample",
    srcs: ["src/*.cpp"],
    shared_libs: ["liblog"],
}
```

**常见模块类型**：
- `cc_library` - C/C++ 库
- `cc_binary` - C/C++ 可执行文件
- `java_library` - Java 库
- `android_app` - Android 应用
- `filegroup` - 文件组

#### Soong 的优势

1. **性能更好**：并行构建更高效
2. **配置更简单**：JSON-like 语法
3. **类型安全**：编译时检查
4. **更好的依赖管理**

### Make 构建系统

#### Android.mk 文件格式

**基本语法**：
```makefile
LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_MODULE := libexample
LOCAL_SRC_FILES := src/example.cpp
include $(BUILD_SHARED_LIBRARY)
```

**常见变量**：
- `LOCAL_MODULE` - 模块名
- `LOCAL_SRC_FILES` - 源文件
- `LOCAL_SHARED_LIBRARIES` - 共享库依赖
- `LOCAL_C_INCLUDES` - 头文件路径

### 设备配置

#### BoardConfig.mk

**位置**：`device/<vendor>/<device>/BoardConfig.mk`

**关键配置**：

```makefile
# 架构
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a

# CPU
TARGET_CPU_VARIANT := generic
TARGET_CPU_ABI := arm64-v8a

# 分区大小
BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 3221225472
BOARD_VENDORIMAGE_PARTITION_SIZE := 1073741824

# 文件系统类型
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := ext4

# 分区表
BOARD_SUPER_PARTITION_SIZE := 6442450944
BOARD_SUPER_PARTITION_GROUPS := group_foo
```

#### device.mk

**位置**：`device/<vendor>/<device>/device.mk`

**作用**：定义设备包含的模块和文件

```makefile
# 包含的产品配置
$(call inherit-product, device/vendor/device/common.mk)

# 设备特定属性
PRODUCT_NAME := device_name
PRODUCT_DEVICE := device_name
PRODUCT_BRAND := Vendor
PRODUCT_MODEL := Device Model
```

#### AndroidProducts.mk

**位置**：`device/<vendor>/<device>/AndroidProducts.mk`

**作用**：定义产品变体

```makefile
PRODUCT_MAKEFILES := \
    $(LOCAL_DIR)/device.mk
```

### 分区布局定义

#### 分区表定义

**位置**：`device/<vendor>/<device>/` 或 `BoardConfig.mk`

**静态分区**：
```makefile
BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 3221225472
BOARD_VENDORIMAGE_PARTITION_SIZE := 1073741824
```

**动态分区**：
```makefile
# 超级分区大小
BOARD_SUPER_PARTITION_SIZE := 6442450944

# 分区组
BOARD_SUPER_PARTITION_GROUPS := group_foo
BOARD_GROUP_FOO_SIZE := 6442450944
BOARD_GROUP_FOO_PARTITION_LIST := system vendor product
```

#### fstab 文件

**位置**：`device/<vendor>/<device>/fstab.*`

**作用**：定义分区挂载信息

```text
#<src>                                    <mnt_point>  <type>  <mnt_flags>  <fs_mgr_flags>
/dev/block/by-name/system                 /system      ext4    ro,barrier=1 wait,avb=vbmeta_system
/dev/block/by-name/vendor                /vendor      ext4    ro,barrier=1 wait,avb=vbmeta_vendor
/dev/block/by-name/userdata              /data        ext4    noatime,nosuid,nodev,barrier=1,noauto_da_alloc wait,check,formattable,resize,quota
```

### 镜像文件生成过程

#### 构建流程

```
源码编译
    ↓
生成文件到 out/target/product/<device>/
    ↓
打包镜像文件
    ↓
生成 .img 文件
```

#### 主要镜像文件

**1. boot.img**
```
构建流程：
Kernel 编译 → 生成 Image
Ramdisk 构建 → 生成 ramdisk.img
DTB 编译 → 生成 *.dtb
    ↓
mkbootimg → boot.img
```

**2. system.img**
```
构建流程：
编译系统组件 → 安装到 out/target/product/<device>/system/
    ↓
构建文件系统镜像 → system.img
    ↓
（可选）转换为 sparse 格式
```

**3. vendor.img**
```
构建流程：
编译厂商组件 → 安装到 out/target/product/<device>/vendor/
    ↓
构建文件系统镜像 → vendor.img
```

#### 镜像格式

**Raw 镜像**：
- 完整的文件系统镜像
- 可以直接挂载
- 文件较大

**Sparse 镜像**：
- 压缩格式，只包含非零块
- 文件较小
- 需要 `simg2img` 转换

**转换命令**：
```bash
# Sparse 转 Raw
simg2img system.img system_raw.img

# Raw 转 Sparse
img2simg system_raw.img system.img
```

### 构建输出目录

#### 目录结构

```
out/
├── target/
│   └── product/
│       └── <device_name>/
│           ├── system.img          # System 分区镜像
│           ├── vendor.img          # Vendor 分区镜像
│           ├── product.img         # Product 分区镜像
│           ├── boot.img            # Boot 分区镜像
│           ├── vbmeta.img          # Vbmeta 镜像
│           ├── system/             # System 分区内容
│           ├── vendor/             # Vendor 分区内容
│           ├── root/               # 根文件系统
│           ├── ramdisk/            # Ramdisk 内容
│           └── ...
└── host/
    └── linux-x86/
        ├── bin/                    # 主机工具
        └── ...
```

#### 关键文件

**分区内容目录**：
- `out/target/product/<device>/system/` - System 分区文件
- `out/target/product/<device>/vendor/` - Vendor 分区文件
- `out/target/product/<device>/root/` - 根文件系统

**镜像文件**：
- `*.img` - 分区镜像文件
- `*.zip` - OTA 更新包

### 构建命令

#### 环境设置

```bash
# 初始化构建环境
source build/envsetup.sh

# 选择设备
lunch <device_name>

# 或直接指定
lunch aosp_arm64-eng
```

#### 构建命令

```bash
# 完整构建
m

# 并行构建（推荐）
m -j$(nproc)

# 构建特定模块
m <module_name>

# 构建特定镜像
m bootimage
m systemimage
m vendorimage
```

#### 清理命令

```bash
# 清理构建输出
m clean

# 清理特定模块
m <module_name>-clean
```

## 实际应用

### 查看设备配置

```bash
# 查看 BoardConfig.mk
cat device/<vendor>/<device>/BoardConfig.mk

# 查看 fstab
cat device/<vendor>/<device>/fstab.*
```

### 分析构建输出

```bash
# 查看生成的镜像
ls -lh out/target/product/<device>/*.img

# 查看 System 分区内容
ls -R out/target/product/<device>/system/
```

### 定制构建

**添加新模块**：
1. 创建 `Android.bp` 或 `Android.mk`
2. 定义模块
3. 添加到产品配置

**修改分区大小**：
1. 编辑 `BoardConfig.mk`
2. 修改 `BOARD_*_PARTITION_SIZE`
3. 重新构建

## 总结

### 核心要点

1. **Soong 是新的构建系统**，性能更好
2. **Make 用于兼容**，逐步迁移到 Soong
3. **BoardConfig.mk 定义硬件配置**和分区布局
4. **镜像文件从构建输出目录生成**
5. **构建系统负责编译和打包**

### 关键文件

- `Android.bp` / `Android.mk` - 模块定义
- `BoardConfig.mk` - 板级配置
- `device.mk` - 设备配置
- `fstab.*` - 分区挂载表

### 后续学习

- [Android分区系统全解析](04-Android分区系统全解析.md) - 理解分区设计
- [分区镜像文件格式详解](05-分区镜像文件格式详解.md) - 理解镜像格式
- [Android启动流程总览](07-Android启动流程总览.md) - 理解启动流程

## 参考资料

- [Android 构建系统](https://source.android.com/docs/setup/build)
- [Soong 构建系统](https://source.android.com/docs/setup/build)
- [设备配置](https://source.android.com/docs/core/architecture/partitions)

## 更新记录

- 2024-01-22：初始创建，包含 Android 构建系统基础详解
