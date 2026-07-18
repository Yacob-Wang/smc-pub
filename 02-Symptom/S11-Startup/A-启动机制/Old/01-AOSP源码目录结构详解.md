# AOSP 源码目录结构详解

## 学习目标

- 理解 AOSP 源码下载后的顶层目录结构
- 掌握各个主要目录的职责和作用
- 了解目录间的依赖关系
- 理解构建输出目录的组织方式

## 背景介绍

Android Open Source Project (AOSP) 是一个庞大的代码库，包含数百万行代码。理解源码的组织结构是深入学习 Android 系统的基础。当你下载 AOSP 源码后，会看到一个包含多个顶级目录的代码树，每个目录都有其特定的职责。

## 核心概念

### AOSP 源码顶层目录概览

当你执行 `repo sync` 下载 AOSP 源码后，会看到类似如下的目录结构：

```
aosp/
├── art/                    # Android Runtime
├── bionic/                 # C 库实现
├── bootable/               # 启动相关代码
├── build/                  # 构建系统
├── cts/                    # 兼容性测试套件
├── dalvik/                 # Dalvik 虚拟机（已废弃）
├── developers/             # 开发者工具和示例
├── development/           # 开发工具
├── device/                 # 设备特定配置
├── external/               # 外部开源项目
├── frameworks/            # Android 框架层
├── hardware/              # 硬件抽象层（HAL）
├── kernel/                # 内核源码（可选）
├── libcore/               # 核心 Java 库
├── libnativehelper/       # JNI 辅助库
├── packages/              # 系统应用和中间件
├── pdk/                   # 平台开发工具包
├── platform_testing/      # 平台测试
├── prebuilts/            # 预编译工具和库
├── sdk/                   # SDK 工具
├── system/                # 核心系统组件
├── test/                  # 测试框架
├── toolchain/            # 工具链
└── vendor/                # 厂商代码
```

### 主要目录详解

#### 1. frameworks/ - Android 框架层

**职责**：包含 Android 应用框架的核心代码

**重要子目录**：
- `frameworks/base/` - 核心框架代码
  - `core/` - 核心 Java 类库
  - `services/` - 系统服务（ActivityManagerService, WindowManagerService 等）
  - `native/` - 本地代码（JNI）
  - `packages/` - 系统应用（Settings, SystemUI 等）
- `frameworks/native/` - 本地框架（SurfaceFlinger, InputFlinger 等）
- `frameworks/av/` - 媒体框架（Audio, Video, Camera）
- `frameworks/rs/` - RenderScript

**关键文件示例**：
- `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` - Activity 管理服务
- `frameworks/native/services/surfaceflinger/` - 图形合成服务

#### 2. system/ - 核心系统组件

**职责**：包含系统级别的核心组件和工具

**重要子目录**：
- `system/core/` - 核心系统组件
  - `init/` - Init 进程源码
  - `adb/` - ADB 工具
  - `libcutils/` - C 工具库
  - `libutils/` - 通用工具库
- `system/extras/` - 额外系统工具
- `system/libbase/` - 基础 C++ 库
- `system/tools/` - 系统工具

**关键文件示例**：
- `system/core/init/init.cpp` - Init 进程主入口
- `system/core/init/init.rc` - Init 启动脚本

#### 3. packages/ - 系统应用和中间件

**职责**：包含系统自带的应用和中间件组件

**重要子目录**：
- `packages/apps/` - 系统应用
  - `Settings/` - 设置应用
  - `Launcher3/` - 启动器
  - `Dialer/` - 拨号器
  - `Contacts/` - 联系人
- `packages/providers/` - 内容提供者
- `packages/services/` - 系统服务应用
- `packages/wallpapers/` - 壁纸

#### 4. hardware/ - 硬件抽象层（HAL）

**职责**：提供硬件抽象层接口和实现

**重要子目录**：
- `hardware/interfaces/` - HAL 接口定义（HIDL/AIDL）
- `hardware/libhardware/` - HAL 库
- `hardware/qcom/` - 高通相关 HAL
- `hardware/broadcom/` - 博通相关 HAL
- `hardware/nvidia/` - 英伟达相关 HAL

**关键概念**：
- HAL 接口定义在 `hardware/interfaces/` 中
- 厂商实现通常在 `vendor/` 目录下

#### 5. device/ - 设备特定配置

**职责**：包含特定设备的配置和定制代码

**目录结构**：
```
device/
├── common/              # 通用设备配置
├── google/              # Google 设备
│   ├── crosshatch/      # Pixel 3 XL
│   └── ...
├── samsung/             # 三星设备
├── xiaomi/              # 小米设备
└── ...
```

**重要文件**：
- `BoardConfig.mk` - 板级配置
- `device.mk` - 设备配置
- `AndroidProducts.mk` - 产品定义
- `fstab.*` - 文件系统表

#### 6. vendor/ - 厂商代码

**职责**：包含厂商特定的代码和二进制文件

**目录结构**：
```
vendor/
├── <vendor_name>/
│   ├── <device_name>/
│   │   ├── proprietary/  # 专有二进制文件
│   │   ├── overlay/     # 覆盖层
│   │   └── ...
│   └── ...
└── ...
```

**关键内容**：
- 厂商 HAL 实现
- 专有驱动和库
- 设备特定配置
- 预编译二进制文件

#### 7. kernel/ - 内核源码

**职责**：Linux 内核源码（可选，通常使用独立仓库）

**说明**：
- 现代 Android 通常使用独立的 Kernel 仓库（如 ACK）
- 如果包含，通常是特定设备的 Kernel 树
- 与 ACK (Android Common Kernel) 的关系

#### 8. build/ - 构建系统

**职责**：包含 Android 构建系统的核心代码

**重要子目录**：
- `build/make/` - Make 构建系统
- `build/soong/` - Soong 构建系统（Go 语言）
- `build/blueprint/` - Blueprint 解析器
- `build/tools/` - 构建工具

**关键文件**：
- `build/make/core/Makefile` - 主 Makefile
- `build/make/core/envsetup.sh` - 环境设置脚本

#### 9. prebuilts/ - 预编译工具和库

**职责**：包含预编译的工具链、库和工具

**重要子目录**：
- `prebuilts/gcc/` - GCC 工具链
- `prebuilts/clang/` - Clang 工具链
- `prebuilts/ndk/` - NDK
- `prebuilts/sdk/` - SDK 工具
- `prebuilts/python/` - Python 解释器

**说明**：
- 这些是预编译的二进制文件，不需要从源码构建
- 用于加速构建过程

#### 10. external/ - 外部开源项目

**职责**：包含 Android 使用的外部开源项目

**示例**：
- `external/openssl/` - OpenSSL
- `external/zlib/` - zlib 压缩库
- `external/libpng/` - PNG 图像库
- `external/sqlite/` - SQLite 数据库

**说明**：
- 这些是第三方开源项目
- Android 可能包含修改版本

### 目录间的依赖关系

#### 构建依赖关系

```
prebuilts/ (工具链)
    ↓
build/ (构建系统)
    ↓
system/ (核心组件)
    ↓
frameworks/ (框架层)
    ↓
packages/ (应用)
    ↓
device/ + vendor/ (设备配置)
```

#### 运行时依赖关系

```
Kernel
    ↓
system/core/init (Init 进程)
    ↓
frameworks/base/services (系统服务)
    ↓
packages/apps (系统应用)
```

### 构建输出目录

当你执行 `m` 或 `make` 构建后，会生成 `out/` 目录：

```
out/
├── target/
│   └── product/
│       └── <product_name>/
│           ├── system.img      # System 分区镜像
│           ├── vendor.img      # Vendor 分区镜像
│           ├── boot.img        # Boot 分区镜像
│           ├── ramdisk.img     # Ramdisk 镜像
│           ├── root/           # 根文件系统
│           ├── system/         # System 分区内容
│           └── ...
└── host/
    └── linux-x86/             # 主机工具
        ├── bin/               # 可执行文件
        └── ...
```

## 实际应用

### 查看 AOSP 源码结构

如果你有 AOSP 源码，可以：

```bash
# 查看顶层目录
ls -la

# 查看 frameworks 目录大小
du -sh frameworks/

# 查看某个关键文件
find . -name "ActivityManagerService.java" -type f
```

### 理解目录大小

典型 AOSP 源码大小：
- `frameworks/` - 最大，包含大部分框架代码
- `external/` - 很大，包含大量外部项目
- `prebuilts/` - 很大，包含预编译文件
- `device/` + `vendor/` - 取决于包含的设备数量

## 总结

### 核心要点

1. **frameworks/** 是 Android 应用框架的核心
2. **system/** 包含系统级组件（init、adb 等）
3. **device/** 和 **vendor/** 包含设备特定代码
4. **build/** 包含构建系统
5. **prebuilts/** 包含预编译工具，加速构建

### 关键目录

- **frameworks/** - 框架层代码
- **system/** - 系统组件
- **device/** - 设备配置
- **vendor/** - 厂商代码
- **build/** - 构建系统

### 后续学习

- [Android系统架构演进](02-Android系统架构演进.md) - 理解架构发展
- [Android构建系统基础](03-Android构建系统基础.md) - 理解如何构建
- [Android分区系统全解析](04-Android分区系统全解析.md) - 理解分区设计

## 参考资料

- [AOSP 源码下载](https://source.android.com/setup/build/downloading)
- [AOSP 项目结构](https://source.android.com/setup/build)
- [Android 源码目录结构详解](https://source.android.com/docs)

## 更新记录

- 2024-01-22：初始创建，包含 AOSP 源码目录结构详解
