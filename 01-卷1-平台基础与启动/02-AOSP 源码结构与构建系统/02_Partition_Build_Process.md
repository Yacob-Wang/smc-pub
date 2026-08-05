# 分区编译流程

> 本文档详细介绍 Android 16 中所有分区的编译过程，包括编译命令、依赖关系、输出文件等

## 📋 目录

1. [编译系统概述](#1-编译系统概述)
2. [系统分区编译](#2-系统分区编译)
3. [启动分区编译](#3-启动分区编译)
4. [供应商分区编译](#4-供应商分区编译)
5. [DLKM分区编译](#5-dlkm分区编译)
6. [验证分区生成](#6-验证分区生成)
7. [数据分区生成](#7-数据分区生成)
8. [完整编译流程](#8-完整编译流程)

---

## 1. 编译系统概述

### 1.1 Android 构建系统

Android 使用 **Soong** 构建系统（基于 Bazel 理念）：

- **Blueprint**：定义构建规则
- **Soong**：执行构建
- **Kati**：处理 Makefile（兼容旧系统）
- **Ninja**：实际执行编译任务

### 1.2 编译命令

```bash
# 基本编译命令
m [target]              # 编译指定目标
m -j[N] [target]        # 使用N个线程编译
mm                      # 编译当前目录模块
mma                     # 编译当前目录及依赖模块

# 常用编译目标
m systemimage           # 编译system分区
m vendorimage           # 编译vendor分区
m bootimage             # 编译boot分区
m -j$(nproc)            # 编译所有内容
```

### 1.3 编译输出目录

```bash
# 编译输出目录结构
out/target/product/{device}/
├── system.img          # system分区镜像
├── vendor.img          # vendor分区镜像
├── boot.img            # boot分区镜像
├── system/             # system分区内容
├── vendor/             # vendor分区内容
└── obj/                # 编译中间文件
```

---

## 2. 系统分区编译

### 2.1 system 分区编译

**编译命令**：
```bash
# 编译system分区
m systemimage

# 或编译system分区及其依赖
m -j$(nproc) systemimage
```

**编译流程**：
1. 编译 Framework 代码
2. 编译系统服务
3. 编译系统应用
4. 打包到 system 目录
5. 生成 system.img

**输出文件**：
- `out/target/product/{device}/system.img`
- `out/target/product/{device}/system/`（分区内容）

**配置文件**：
- `build/make/core/Makefile` - 系统镜像生成规则
- `device/*/system.prop` - 系统属性配置

**依赖关系**：
```
systemimage 依赖:
├── Framework (frameworks/base)
├── System Services (frameworks/native)
├── System Apps (packages/apps)
└── System Libraries (libcore, libart)
```

### 2.2 system_ext 分区编译

**编译命令**：
```bash
# 编译system_ext分区
m system_extimage
```

**编译流程**：
1. 编译 system_ext 模块
2. 打包到 system_ext 目录
3. 生成 system_ext.img

**输出文件**：
- `out/target/product/{device}/system_ext.img`
- `out/target/product/{device}/system_ext/`

**配置**：
在 `device.mk` 中配置：
```makefile
PRODUCT_PACKAGES += \
    system_ext:module1 \
    system_ext:module2
```

### 2.3 product 分区编译

**编译命令**：
```bash
# 编译product分区
m productimage
```

**编译流程**：
1. 编译 product 模块
2. 打包到 product 目录
3. 生成 product.img

**输出文件**：
- `out/target/product/{device}/product.img`
- `out/target/product/{device}/product/`

**配置**：
在 `device.mk` 中配置：
```makefile
PRODUCT_PACKAGES += \
    product:app1 \
    product:app2
```

---

## 3. 启动分区编译

### 3.1 boot 分区编译

**编译命令**：
```bash
# 编译boot分区
m bootimage

# 或单独编译内核
m kernel
```

**编译流程**：

#### 步骤1：编译内核

```bash
# 进入内核目录
cd kernel/common  # 或 device/*/kernel

# 配置内核
make ARCH=arm64 gki_defconfig

# 编译内核
make ARCH=arm64 -j$(nproc)

# 输出：arch/arm64/boot/Image.lz4
```

#### 步骤2：编译 ramdisk（Android 12-）

```bash
# ramdisk 由构建系统自动生成
# 包含 init 和初始启动脚本
```

#### 步骤3：打包 boot.img

```bash
# 使用 mkbootimg 工具打包
mkbootimg \
    --kernel arch/arm64/boot/Image.lz4 \
    --ramdisk ramdisk.cpio \
    --output boot.img \
    --pagesize 4096 \
    --base 0x00000000 \
    --kernel_offset 0x00008000 \
    --ramdisk_offset 0x01000000 \
    --tags_offset 0x00000100
```

**输出文件**：
- `out/target/product/{device}/boot.img`
- `out/target/product/{device}/obj/PACKAGING/bootimage/`（中间文件）

**Android 13+ 变化**：
- ramdisk 已分离到 `init_boot` 分区
- boot.img 只包含内核

### 3.2 init_boot 分区编译

**编译命令**：
```bash
# 编译init_boot分区
m init_bootimage
```

**编译流程**：
1. 编译 init 可执行文件
2. 收集初始启动脚本
3. 打包为 ramdisk（cpio 格式）
4. 生成 init_boot.img

**输出文件**：
- `out/target/product/{device}/init_boot.img`

**ramdisk 内容**：
```
ramdisk/
├── init                 # init 可执行文件
├── init.rc              # init 脚本
├── init.environ.rc      # 环境变量
└── ...
```

### 3.3 vendor_boot 分区编译

**编译命令**：
```bash
# 编译vendor_boot分区
m vendor_bootimage
```

**编译流程**：
1. 编译供应商 ramdisk
2. 编译设备树 Blob（DTB）
3. 生成供应商 ramdisk 表
4. 打包为 vendor_boot.img

**输出文件**：
- `out/target/product/{device}/vendor_boot.img`

**配置**：
在 `device/*/vendor_boot/` 目录中配置：
- `vendor_boot.rc` - 供应商 ramdisk 脚本
- `dtb/` - 设备树文件

### 3.4 dtbo 分区编译

**编译命令**：
```bash
# 编译dtbo分区
m dtboimage
```

**编译流程**：
1. 编译设备树覆盖层（.dts → .dtbo）
2. 使用 `mkdtimg` 打包
3. 生成 dtbo.img

**输出文件**：
- `out/target/product/{device}/dtbo.img`

**设备树覆盖层示例**：
```dts
// overlay.dts
/dts-v1/;
/plugin/;

&soc {
    // 覆盖配置
};
```

---

## 4. 供应商分区编译

### 4.1 vendor 分区编译

**编译命令**：
```bash
# 编译vendor分区
m vendorimage
```

**编译流程**：
1. 编译 HAL 实现
2. 编译供应商二进制文件
3. 编译供应商库
4. 打包到 vendor 目录
5. 生成 vendor.img

**输出文件**：
- `out/target/product/{device}/vendor.img`
- `out/target/product/{device}/vendor/`

**HAL 编译示例**：
```bash
# HAL 模块通常使用 Android.bp 或 Android.mk
# 例如：hardware/interfaces/camera/4.0/default/

# 编译特定 HAL
m camera.default
```

**配置**：
在 `device.mk` 中配置：
```makefile
PRODUCT_PACKAGES += \
    android.hardware.camera.provider@2.4-service \
    vendor.specific.binary
```

### 4.2 odm 分区编译

**编译命令**：
```bash
# 编译odm分区
m odmimage
```

**编译流程**：
1. 编译 ODM 特定代码
2. 打包到 odm 目录
3. 生成 odm.img

**输出文件**：
- `out/target/product/{device}/odm.img`
- `out/target/product/{device}/odm/`

**配置**：
在 `device.mk` 中配置：
```makefile
PRODUCT_PACKAGES += \
    odm:specific.module
```

---

## 5. DLKM分区编译

### 5.1 system_dlkm 分区编译

**编译命令**：
```bash
# 编译system_dlkm分区
m system_dlkmimage
```

**编译流程**：
1. 编译系统内核模块（.ko 文件）
2. 打包到 system_dlkm 目录
3. 生成 system_dlkm.img

**输出文件**：
- `out/target/product/{device}/system_dlkm.img`
- `out/target/product/{device}/system_dlkm/`

**内核模块编译**：
```bash
# 在内核源码目录
cd kernel/common

# 编译模块
make ARCH=arm64 modules -j$(nproc)

# 安装模块到输出目录
make ARCH=arm64 INSTALL_MOD_PATH=../out/modules modules_install
```

### 5.2 vendor_dlkm 分区编译

**编译命令**：
```bash
# 编译vendor_dlkm分区
m vendor_dlkmimage
```

**编译流程**：
1. 编译供应商内核模块
2. 打包到 vendor_dlkm 目录
3. 生成 vendor_dlkm.img

**输出文件**：
- `out/target/product/{device}/vendor_dlkm.img`
- `out/target/product/{device}/vendor_dlkm/`

**供应商模块编译**：
```bash
# 在设备目录
cd device/*/vendor_dlkm/

# 编译模块
make -C kernel/common M=$(pwd) modules
```

### 5.3 odm_dlkm 分区编译

**编译命令**：
```bash
# 编译odm_dlkm分区
m odm_dlkmimage
```

**编译流程**：
1. 编译 ODM 内核模块
2. 打包到 odm_dlkm 目录
3. 生成 odm_dlkm.img

**输出文件**：
- `out/target/product/{device}/odm_dlkm.img`
- `out/target/product/{device}/odm_dlkm/`

---

## 6. 验证分区生成

### 6.1 vbmeta 分区生成

**生成命令**：
```bash
# 生成vbmeta分区
m vbmetaimage
```

**生成流程**：
1. 收集所有分区的哈希值
2. 使用 `avbtool` 生成验证元数据
3. 签名（如果配置了密钥）
4. 生成 vbmeta.img

**输出文件**：
- `out/target/product/{device}/vbmeta.img`

**avbtool 使用**：
```bash
# 手动生成vbmeta
avbtool make_vbmeta_image \
    --output vbmeta.img \
    --include_descriptors_from_image system.img \
    --include_descriptors_from_image vendor.img \
    --algorithm SHA256_RSA4096 \
    --key private_key.pem
```

### 6.2 其他 vbmeta 分区

```bash
# vbmeta_system
m vbmeta_systemimage

# vbmeta_vendor
m vbmeta_vendorimage

# vbmeta_vendor_dlkm
m vbmeta_vendor_dlkmimage
```

---

## 7. 数据分区生成

### 7.1 userdata 分区生成

**生成命令**：
```bash
# 生成userdata分区（初始空镜像）
m userdataimage
```

**生成流程**：
1. 创建空的文件系统镜像
2. 格式化（ext4 或 f2fs）
3. 生成 userdata.img

**输出文件**：
- `out/target/product/{device}/userdata.img`

**大小配置**：
在 `BoardConfig.mk` 中：
```makefile
BOARD_USERDATAIMAGE_PARTITION_SIZE := 48318382080  # 45GB
```

### 7.2 其他数据分区

```bash
# cache分区
m cacheimage

# metadata分区
m metadataimage

# misc分区
m miscimage

# persist分区
m persistimage

# frp分区
m frpimage
```

---

## 8. 完整编译流程

### 8.1 完整系统编译

```bash
# 1. 加载环境
source build/envsetup.sh

# 2. 选择设备
lunch aosp_arm64-eng

# 3. 编译所有内容
m -j$(nproc)

# 这会编译：
# - 所有系统分区
# - 所有启动分区
# - 所有供应商分区
# - 所有镜像文件
```

### 8.2 增量编译

```bash
# 只编译修改的部分
m -j$(nproc)

# 编译特定模块
m module_name

# 清理后重新编译
m clean
m -j$(nproc)
```

### 8.3 编译特定分区

```bash
# 只编译system分区
m systemimage

# 只编译boot分区
m bootimage

# 编译多个分区
m systemimage vendorimage productimage
```

### 8.4 编译输出验证

```bash
# 检查所有镜像文件
ls -lh out/target/product/{device}/*.img

# 验证镜像格式
file out/target/product/{device}/system.img
file out/target/product/{device}/boot.img

# 检查镜像大小
du -sh out/target/product/{device}/*.img
```

---

## 总结

分区编译流程总结：

1. **系统分区**：`m systemimage`, `m system_extimage`, `m productimage`
2. **启动分区**：`m bootimage`, `m init_bootimage`, `m vendor_bootimage`, `m dtboimage`
3. **供应商分区**：`m vendorimage`, `m odmimage`
4. **DLKM分区**：`m system_dlkmimage`, `m vendor_dlkmimage`, `m odm_dlkmimage`
5. **验证分区**：`m vbmetaimage` 等
6. **数据分区**：`m userdataimage` 等

**编译输出**：所有镜像文件在 `out/target/product/{device}/` 目录

**下一步学习**：
- 了解镜像生成和打包的详细过程，请阅读 [镜像生成和打包](03_Image_Generation_And_Packaging.md)
- 了解编译配置选项，请阅读 [编译配置和选项](04_Build_Configuration_And_Options.md)
