# ACK 内核编译与刷入完整实战指南

## 📋 目录

1. [环境准备](#1-环境准备)
2. [获取 ACK 源代码](#2-获取-ack-源代码)
3. [切换到指定标签](#3-切换到指定标签)
4. [配置内核](#4-配置内核)
5. [编译内核](#5-编译内核)
6. [生成 GKI 镜像](#6-生成-gki-镜像)
7. [准备刷机环境](#7-准备刷机环境)
8. [刷入内核镜像](#8-刷入内核镜像)
9. [验证结果](#9-验证结果)
10. [常见问题排查](#10-常见问题排查)
11. [完整脚本示例](#11-完整脚本示例)

---

## 1. 环境准备

### 1.1 系统要求

**推荐操作系统**：
- Ubuntu 20.04 LTS 或更高版本
- Debian 11 或更高版本
- 其他 Linux 发行版（需要相应调整包管理器命令）

**硬件要求**：
- CPU：4 核心或更多（编译速度更快）
- 内存：至少 8GB RAM（推荐 16GB+）
- 磁盘空间：至少 50GB 可用空间

### 1.2 安装编译工具和依赖

#### Ubuntu/Debian 系统

```bash
# 更新包列表
sudo apt-get update

# 安装基础编译工具
sudo apt-get install -y \
    build-essential \
    git \
    curl \
    wget \
    python3 \
    python3-pip

# 安装内核编译必需工具
sudo apt-get install -y \
    libncurses5-dev \
    libncursesw5-dev \
    libssl-dev \
    bc \
    flex \
    bison \
    libelf-dev \
    dwarves \
    rsync \
    kmod \
    cpio

# 安装交叉编译工具链（ARM64）
sudo apt-get install -y \
    gcc-aarch64-linux-gnu \
    g++-aarch64-linux-gnu

# 验证工具链安装
aarch64-linux-gnu-gcc --version
```

#### 其他 Linux 发行版

**Fedora/RHEL/CentOS**：
```bash
sudo dnf install -y \
    gcc gcc-c++ make git \
    ncurses-devel openssl-devel \
    bc flex bison elfutils-libelf-devel \
    gcc-aarch64-linux-gnu
```

**Arch Linux**：
```bash
sudo pacman -S --needed \
    base-devel git \
    ncurses openssl \
    bc flex bison libelf \
    aarch64-linux-gnu-gcc
```

### 1.3 安装 Android 工具（用于刷机）

```bash
# 安装 ADB 和 Fastboot
# Ubuntu/Debian
sudo apt-get install -y android-tools-adb android-tools-fastboot

# 或下载 Android SDK Platform Tools
cd ~
wget https://dl.google.com/android/repository/platform-tools-latest-linux.zip
unzip platform-tools-latest-linux.zip
export PATH=$PATH:~/platform-tools

# 验证安装
adb version
fastboot --version
```

### 1.4 设置环境变量

创建环境配置文件 `~/.kernel_build_env.sh`：

```bash
cat > ~/.kernel_build_env.sh << 'EOF'
#!/bin/bash
# 内核编译环境变量配置

# 架构设置
export ARCH=arm64

# 交叉编译工具链（使用系统安装的）
export CROSS_COMPILE=aarch64-linux-gnu-

# 或使用 AOSP 工具链（如果已下载）
# export CROSS_COMPILE=/path/to/aosp/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/bin/aarch64-linux-android-

# 编译线程数（使用所有 CPU 核心）
export JOBS=$(nproc)

# 内核源码目录（根据实际情况修改）
export KERNEL_DIR=~/android-kernel

# 输出目录
export OUT_DIR=~/kernel-build-output
EOF

# 使配置文件生效
chmod +x ~/.kernel_build_env.sh
source ~/.kernel_build_env.sh
```

**每次使用前加载环境**：
```bash
source ~/.kernel_build_env.sh
```

---

## 2. 获取 ACK 源代码

### 2.1 克隆 ACK 仓库

#### 方法 1：从 Google 官方仓库克隆（推荐）

```bash
# 创建工作目录
mkdir -p ~/android-kernel
cd ~/android-kernel

# 克隆 Android Common Kernel 仓库
# 注意：这是一个大仓库，首次克隆可能需要较长时间（1-2小时）
git clone https://android.googlesource.com/kernel/common

# 进入仓库目录
cd common
```

#### 方法 2：使用镜像仓库（如果官方仓库访问慢）

```bash
# 使用 GitHub 镜像（如果有）
git clone https://github.com/aosp-mirror/kernel_common.git common

# 或使用其他镜像源
# 注意：镜像可能不是最新的，建议使用官方源
```

### 2.2 查看可用分支和标签

```bash
cd ~/android-kernel/common

# 获取所有远程分支和标签
git fetch --all --tags

# 查看所有分支
git branch -a | grep android

# 查看所有标签（按版本排序）
git tag | grep -E "android[0-9]+" | sort -V

# 查看特定 Android 版本的标签
git tag | grep "android14"
git tag | grep "android13"
git tag | grep "android12"

# 查看标签的详细信息
git show-ref --tags | grep "android14-5.15"
```

**常见标签格式**：
```
android<版本>-<LTS版本>-<年月>_r<修订号>
例如：
- android14-6.1-2024-11_r3
- android14-5.15-2024-11_r3
- android13-5.15-2024-05_r2
```

### 2.3 查看仓库信息

```bash
# 查看当前分支
git branch

# 查看远程仓库信息
git remote -v

# 查看仓库大小
du -sh .git
```

### 2.4 为什么内核更新需要提交两个仓库？

#### 2.4.1 问题：为什么需要两个仓库？

在厂商环境中，内核版本更新通常需要提交两个仓库：
1. **ACK 源代码仓库**（如 `kernel/common`）
2. **GKI 构建/产物仓库**（如 `gki2.0`）

**疑问**：为什么不能只提交 ACK 代码，然后根据编译产物自动更新？

#### 2.4.2 两个仓库的不同作用

**仓库 1：ACK 源代码仓库（kernel/common）**
```
作用：
├── 包含内核源代码（基于 ACK）
├── 包含厂商对 ACK 的修改/补丁
├── 包含内核配置（.config）
└── 源代码版本管理

内容：
- arch/
- drivers/
- kernel/
- mm/
- fs/
- Makefile
- .config
```

**仓库 2：GKI 构建/产物仓库（gki2.0）**
```
作用：
├── GKI 构建配置和脚本
├── 构建产物管理（Image.lz4 等）
├── 模块构建配置
├── 发布清单（manifest.xml）
└── 构建流程管理

内容：
- BUILD 文件（Bazel 构建规则）
- 构建脚本
- 构建产物（released/ 目录）
- 模块配置
- 发布清单
```

#### 2.4.3 为什么不能只提交 ACK 代码？

**原因 1：构建配置和脚本需要版本控制**

```bash
# ACK 仓库只包含源代码
kernel/common/
├── 源代码 ✅
├── .config ✅
└── 构建脚本 ❌（通常不在 ACK 仓库）

# GKI 仓库包含构建系统
gki2.0/
├── BUILD 文件（Bazel 规则）✅
├── 构建脚本 ✅
├── 模块构建配置 ✅
└── 产物管理 ✅
```

**原因 2：构建产物需要独立管理**

```bash
# 构建产物不应该在源代码仓库中
# 原因：
# 1. 文件太大（Image.lz4 25MB，vmlinux.gz 180MB）
# 2. 二进制文件不适合 Git 管理
# 3. 需要独立的版本控制和发布流程

gki2.0/released/
├── Image.lz4          # 需要版本控制
├── System.map         # 需要版本控制
├── vmlinux.symvers    # 需要版本控制
└── manifest_*.xml     # 需要版本控制
```

**原因 3：构建流程可能涉及多个步骤**

```bash
# 完整的构建流程：
1. 从 ACK 仓库获取源代码
2. 应用 GKI 特定配置
3. 编译内核
4. 构建模块
5. 生成 GKI 镜像
6. 生成符号文件
7. 打包发布

# 这些步骤的配置和脚本在 gki2.0 仓库中
```

**原因 4：模块构建需要独立管理**

```bash
# GKI 架构中，模块是独立构建的
gki2.0/
├── 模块构建配置
├── 模块依赖管理
└── 模块版本控制

# 模块构建需要：
# - vmlinux.symvers（从内核构建获得）
# - 模块源代码（可能在 common-modules/）
# - 模块构建脚本（在 gki2.0/）
```

#### 2.4.4 Google 官方的流程

**Google 的流程**：

```
1. 维护 ACK 源代码
   └─> kernel/common 仓库
   └─> 只包含源代码

2. 构建 GKI 镜像
   └─> 使用内部构建系统
   └─> 生成 Image.lz4 等产物
   └─> 产物存储在独立的发布系统

3. 发布 GKI
   └─> 通过 AOSP 发布系统
   └─> 提供预编译的 Image.lz4
   └─> OEM 直接下载使用
```

**Google 为什么不需要两个仓库？**

1. **Google 使用内部构建系统**：
   - 不是基于 Git 的构建配置
   - 使用专门的 CI/CD 系统
   - 构建产物存储在独立的存储系统

2. **Google 直接提供预编译产物**：
   - OEM 不需要自己构建
   - 直接下载 Google 构建的 GKI
   - 不需要管理构建产物仓库

3. **Google 的模块是独立的**：
   - 模块在独立的仓库中
   - 使用独立的构建流程
   - 不需要与内核构建耦合

#### 2.4.5 厂商为什么需要两个仓库？

**厂商的特殊需求**：

**需求 1：需要自己构建 GKI**
```bash
# 厂商可能需要：
# - 定制内核配置
# - 添加特殊补丁
# - 控制构建过程
# - 管理构建产物

# 因此需要：
gki2.0/
├── 构建配置
├── 构建脚本
└── 构建产物
```

**需求 2：需要版本控制构建产物**
```bash
# 厂商需要：
# - 跟踪每个版本的构建产物
# - 确保构建可重现
# - 管理发布版本
# - 支持回退

# 因此需要独立的仓库管理产物
```

**需求 3：需要管理模块构建**
```bash
# 厂商的模块构建流程：
1. 从 ACK 构建内核 → 获得 vmlinux.symvers
2. 使用 vmlinux.symvers 构建模块
3. 模块和内核需要版本匹配

# 这个流程的配置在 gki2.0 仓库中
```

**需求 4：需要集成到 CI/CD**
```bash
# 厂商的 CI/CD 流程：
1. 提交 ACK 代码变更 → 触发构建
2. 构建系统读取 gki2.0 配置
3. 执行构建流程
4. 将产物提交到 gki2.0 仓库

# 两个仓库协同工作
```

#### 2.4.6 实际工作流程示例

**场景：更新内核版本**

```bash
# 步骤 1：更新 ACK 源代码
cd kernel/common
git checkout android14-5.15-2024-11_r3
# 应用厂商补丁
git commit -m "Update to android14-5.15-2024-11_r3"
# 提交到 Gerrit
git push origin HEAD:refs/for/main

# 步骤 2：更新 GKI 构建配置
cd gki2.0
# 更新构建配置指向新的 ACK 版本
vim BUILD  # 或构建脚本
# 更新版本号
vim manifest.xml
git commit -m "Update GKI build config for android14-5.15-2024-11_r3"
# 提交到 Gerrit

# 步骤 3：CI/CD 自动构建
# 系统检测到两个仓库的变更
# 触发构建流程：
# 1. 从 kernel/common 获取源代码
# 2. 使用 gki2.0 的构建配置
# 3. 执行构建
# 4. 生成产物

# 步骤 4：提交构建产物
cd gki2.0/released
# 构建产物自动提交
git add Image.lz4 System.map vmlinux.symvers manifest_*.xml
git commit -m "Release GKI for android14-5.15-2024-11_r3"
```

#### 2.4.7 为什么不能只提交 ACK 然后自动构建？

**技术限制**：

1. **构建产物太大**：
   ```bash
   # 构建产物不适合放在源代码仓库
   Image.lz4:     25MB
   vmlinux.gz:    180MB
   System.map:    7.4MB
   # 总共约 200MB+，Git 管理效率低
   ```

2. **构建需要配置**：
   ```bash
   # 构建不是自动的，需要：
   # - 构建脚本
   # - 构建配置
   # - 工具链配置
   # 这些在 gki2.0 仓库中
   ```

3. **版本对应关系**：
   ```bash
   # 需要明确记录：
   # - 哪个 ACK 版本
   # - 对应哪个 GKI 构建
   # - 构建产物版本
   # 这些信息在 gki2.0 仓库中管理
   ```

4. **模块依赖**：
   ```bash
   # 模块构建依赖：
   # - 内核的 vmlinux.symvers
   # - 模块构建配置
   # - 模块源代码
   # 这些需要统一管理
   ```

#### 2.4.8 Google 官方的最佳实践

**Google 的建议**：

1. **源代码和构建产物分离**：
   - 源代码在 Git 仓库
   - 构建产物在发布系统

2. **使用 CI/CD 自动化**：
   - 源代码变更触发构建
   - 构建产物自动发布
   - 不需要手动管理产物

3. **版本对应关系**：
   - 通过标签管理版本
   - 构建产物包含版本信息
   - manifest.xml 记录对应关系

**厂商的实现方式**：

```bash
# 方式 1：两个仓库（您的情况）
kernel/common/  → 源代码
gki2.0/         → 构建配置 + 产物

# 方式 2：单一仓库 + 外部存储
kernel/common/  → 源代码 + 构建脚本
外部存储        → 构建产物

# 方式 3：完全自动化
kernel/common/  → 源代码
CI/CD 系统      → 自动构建和发布
```

#### 2.4.9 总结

**为什么需要两个仓库**：

1. ✅ **职责分离**：
   - ACK 仓库：源代码管理
   - GKI 仓库：构建配置和产物管理

2. ✅ **技术限制**：
   - 构建产物太大，不适合 Git
   - 构建需要配置和脚本
   - 版本对应关系需要管理

3. ✅ **工作流程**：
   - 源代码变更 → 触发构建
   - 构建配置变更 → 影响构建
   - 构建产物 → 需要版本控制

4. ✅ **模块管理**：
   - 模块构建依赖内核符号
   - 需要统一的构建流程
   - 版本匹配需要管理

**Google 官方流程**：
- Google 使用内部构建系统，不依赖 Git 管理构建产物
- Google 直接提供预编译 GKI，OEM 不需要自己构建
- 如果 OEM 需要自己构建，就需要管理构建配置和产物

**您的厂商流程**：
- 需要自己构建 GKI → 需要构建配置仓库
- 需要管理构建产物 → 需要产物仓库
- 需要版本控制 → 两个仓库协同工作

### 2.5 所有 SoC 厂商都需要这样更新 Kernel 吗？

#### 2.5.1 答案：不是所有厂商都需要

**实际情况**：不同 SoC 厂商的实现方式不同，取决于：
- 厂商的组织架构
- 构建系统设计
- 与 OEM 的合作模式
- 内部工作流程

#### 2.5.2 不同 SoC 厂商的实现方式

##### 方式 1：两个仓库模式（如 Unisoc/展讯）

**特点**：
- ACK 源代码仓库（kernel/common）
- GKI 构建/产物仓库（gki2.0）
- 需要同时提交两个仓库

**适用场景**：
- SoC 厂商需要自己构建 GKI
- 需要管理构建产物
- 需要版本控制和发布流程
- 与 OEM 紧密集成

**工作流程**：
```
1. 更新 ACK 源代码 → kernel/common 仓库
2. 更新 GKI 构建配置 → gki2.0 仓库
3. CI/CD 自动构建
4. 构建产物提交到 gki2.0/released/
```

##### 方式 2：单一仓库 + 外部存储（如某些厂商）

**特点**：
- 只有 ACK 源代码仓库
- 构建产物存储在外部系统（如 Artifactory、Nexus）
- 不需要 Git 管理构建产物

**适用场景**：
- 使用外部构建系统
- 构建产物存储在专门的存储系统
- 不需要在 Git 中管理二进制文件

**工作流程**：
```
1. 更新 ACK 源代码 → kernel/common 仓库
2. CI/CD 检测变更，触发构建
3. 构建产物上传到外部存储
4. 通过 API 或 Web 界面管理版本
```

##### 方式 3：完全自动化（如 Google、某些大厂）

**特点**：
- ACK 源代码仓库
- 完全自动化的 CI/CD
- 构建产物自动发布
- 不需要手动管理构建产物

**适用场景**：
- 成熟的 CI/CD 系统
- 自动化测试和发布
- 直接提供预编译 GKI 给 OEM

**工作流程**：
```
1. 更新 ACK 源代码 → kernel/common 仓库
2. 自动触发构建（基于标签或提交）
3. 自动测试和验证
4. 自动发布到下载服务器
5. OEM 直接下载使用
```

##### 方式 4：混合模式（如 Qualcomm、MediaTek）

**特点**：
- 源代码在独立仓库
- 构建系统使用内部工具
- 部分产物在 Git，部分在外部分存储
- 提供 SDK 给 OEM

**适用场景**：
- 大型 SoC 厂商
- 需要支持多个 OEM
- 提供完整的开发工具链

**工作流程**：
```
1. 更新 ACK 源代码 → 内部仓库
2. 使用内部构建系统构建
3. 产物打包到 SDK
4. OEM 通过 SDK 获取
```

#### 2.5.3 主要 SoC 厂商的实际情况

##### Qualcomm（高通）

**实现方式**：
- 使用内部构建系统
- 提供 Snapdragon 平台 SDK
- OEM 通过 SDK 获取内核和模块
- 不需要 OEM 自己构建 GKI

**特点**：
- ✅ 提供预编译 GKI（通过 SDK）
- ✅ 源代码在内部管理
- ✅ 构建产物在 SDK 中
- ❌ OEM 通常不需要两个仓库

**OEM 的工作**：
```bash
# OEM 通常只需要：
1. 下载 Qualcomm SDK
2. 获取预编译的 GKI
3. 构建自己的模块
4. 集成到设备
```

##### MediaTek（联发科）

**实现方式**：
- 类似 Qualcomm
- 提供 MediaTek 平台 SDK
- 源代码和构建产物在 SDK 中
- OEM 通过 SDK 获取

**特点**：
- ✅ 提供预编译 GKI
- ✅ 源代码在 SDK 中
- ✅ 构建工具在 SDK 中
- ❌ OEM 通常不需要两个仓库

**OEM 的工作**：
```bash
# OEM 通常只需要：
1. 下载 MediaTek SDK
2. 获取预编译的 GKI
3. 构建自己的模块
4. 集成到设备
```

##### Unisoc（展讯/紫光展锐）

**实现方式**：
- 使用两个仓库模式
- ACK 源代码仓库
- GKI 构建/产物仓库
- 需要同时提交两个仓库

**特点**：
- ✅ 源代码在 kernel/common 仓库
- ✅ 构建配置在 gki2.0 仓库
- ✅ 构建产物在 gki2.0/released/
- ✅ 需要版本控制两个仓库

**OEM 的工作**：
```bash
# OEM 需要：
1. 更新 kernel/common 仓库
2. 更新 gki2.0 仓库
3. 触发构建
4. 获取构建产物
```

##### Google（Pixel 设备）

**实现方式**：
- 完全自动化
- 源代码在 AOSP
- 自动构建和发布
- 直接提供预编译 GKI

**特点**：
- ✅ 源代码在 AOSP 中
- ✅ 自动构建系统
- ✅ 自动发布
- ✅ OEM（Google 自己）直接使用

#### 2.5.4 为什么不同厂商方式不同？

**因素 1：组织架构**

```bash
# 大型 SoC 厂商（Qualcomm、MediaTek）
- 有完整的 SDK 团队
- 提供完整的开发工具链
- OEM 不需要自己构建

# 中小型 SoC 厂商（Unisoc 等）
- 可能没有完整的 SDK
- OEM 需要自己构建
- 需要管理构建流程
```

**因素 2：与 OEM 的合作模式**

```bash
# 紧密集成模式
- SoC 厂商和 OEM 深度合作
- 需要共享源代码和构建产物
- 使用 Git 仓库管理

# SDK 模式
- SoC 厂商提供 SDK
- OEM 通过 SDK 获取
- 不需要共享源代码仓库
```

**因素 3：技术能力**

```bash
# 成熟的 CI/CD
- 自动化构建和发布
- 不需要手动管理产物

# 传统方式
- 需要手动管理
- 使用 Git 管理产物
```

**因素 4：合规要求**

```bash
# GPL 合规
- 需要提供源代码
- 可能使用 Git 仓库

# 商业考虑
- 源代码可能不公开
- 通过 SDK 提供
```

#### 2.5.5 Google 的要求 vs 实际实现

**Google 的官方要求**：

1. **Android 12+ 设备必须使用 GKI**
2. **GKI 必须基于 ACK 构建**
3. **需要提供源代码**（GPL 要求）

**Google 不要求**：
- ❌ 必须使用两个仓库
- ❌ 必须使用 Git 管理构建产物
- ❌ 必须使用特定的构建系统

**实际实现**：
- 各厂商根据自己的情况选择
- 只要满足 GKI 要求即可
- 构建方式可以不同

#### 2.5.6 总结：不同厂商的对比

| SoC 厂商 | 仓库数量 | 构建方式 | OEM 工作 | 特点 |
|---------|---------|---------|---------|------|
| **Qualcomm** | 1（内部） | SDK 提供 | 下载 SDK | 成熟 SDK，OEM 简单 |
| **MediaTek** | 1（内部） | SDK 提供 | 下载 SDK | 类似 Qualcomm |
| **Unisoc** | 2（公开） | 需要构建 | 提交两个仓库 | 需要自己构建 |
| **Google** | 1（AOSP） | 自动构建 | 直接使用 | 完全自动化 |
| **其他小厂** | 1-2 | 各种方式 | 根据情况 | 方式多样 |

#### 2.5.7 对 OEM 的影响

**如果 SoC 厂商使用 SDK 模式**：
```bash
# OEM 的工作简单
1. 下载 SDK
2. 获取预编译 GKI
3. 构建自己的模块
4. 集成到设备

# 不需要：
- 管理 ACK 源代码仓库
- 管理 GKI 构建仓库
- 自己构建 GKI
```

**如果 SoC 厂商使用仓库模式**：
```bash
# OEM 的工作复杂
1. 更新 ACK 源代码仓库
2. 更新 GKI 构建仓库
3. 触发构建
4. 获取构建产物
5. 集成到设备

# 需要：
- 管理两个仓库
- 理解构建流程
- 处理构建问题
```

#### 2.5.8 最佳实践建议

**对于 SoC 厂商**：

1. **如果可能，提供 SDK**：
   - 降低 OEM 的使用门槛
   - 统一构建和测试
   - 减少支持成本

2. **如果使用仓库模式**：
   - 提供清晰的文档
   - 自动化构建流程
   - 简化 OEM 的工作

3. **无论哪种方式**：
   - 确保 GKI 合规
   - 提供源代码（GPL 要求）
   - 支持 OEM 的需求

**对于 OEM**：

1. **了解 SoC 厂商的方式**：
   - 阅读文档
   - 理解工作流程
   - 遵循最佳实践

2. **如果使用仓库模式**：
   - 理解两个仓库的关系
   - 正确提交代码
   - 验证构建结果

3. **如果使用 SDK 模式**：
   - 及时更新 SDK
   - 验证 GKI 版本
   - 确保模块兼容

### 2.6 理解厂商内核仓库结构

**注意**：如果您使用的是厂商提供的仓库（而不是直接克隆 ACK），目录结构可能不同。

#### 常见的厂商仓库结构

**示例 1：标准 ACK 仓库结构**
```
common/
├── arch/
├── drivers/
├── kernel/
├── mm/
├── fs/
├── Makefile
└── ...
```

**示例 2：厂商定制仓库结构（使用 Bazel 构建系统）**
```
kernel5.15/
├── build/              # 构建脚本和配置
├── common-modules/     # 通用内核模块
├── external/           # 外部依赖和工具
├── gki2.0/            # GKI 2.0 相关（见下方说明）
├── kernel/            # 内核源码（可能是符号链接）
├── kernel5.15/        # 内核 5.15 源码目录
├── prebuilts/         # 预编译工具链和二进制
├── tools/             # 构建工具
└── WORKSPACE          # Bazel 工作空间文件
```

#### gki2.0 目录的作用

`gki2.0` 目录通常包含以下内容之一：

**情况 1：编译输出目录**
```bash
# 查看 gki2.0 目录内容
ls -la gki2.0/

# 如果包含以下文件，说明是编译输出：
# - Image.lz4
# - System.map
# - vmlinux
# - .config
```

**情况 2：GKI 2.0 配置和补丁**
```bash
# 如果包含以下内容，说明是配置目录：
# - defconfig 文件
# - 补丁文件（.patch）
# - 构建脚本
```

**情况 3：GKI 2.0 构建脚本和规则**
```bash
# 如果使用 Bazel 构建系统：
# - BUILD 文件
# - 构建规则定义
```

**如何确认 gki2.0 目录的作用**：

```bash
# 1. 查看目录内容
ls -la gki2.0/

# 2. 查看文件类型
file gki2.0/*

# 3. 查看目录大小
du -sh gki2.0/

# 4. 检查是否在 .gitignore 中（编译产物通常在 .gitignore 中）
grep gki2.0 .gitignore

# 5. 查看构建脚本中如何使用这个目录
grep -r "gki2.0" build/ tools/
```

#### 在厂商仓库中查找内核源码

```bash
# 方法 1：查找实际的源码目录
find . -name "Makefile" -type f | head -5
find . -name "Kconfig" -type f | head -5

# 方法 2：查看 kernel 或 kernel5.15 目录
ls -la kernel/
ls -la kernel5.15/

# 方法 3：检查是否是符号链接
ls -l kernel kernel5.15

# 方法 4：查看构建脚本了解源码位置
cat build/build.sh | grep -i "kernel\|source"
```

#### 使用厂商构建系统编译

**如果使用 Bazel（有 WORKSPACE 文件）**：

```bash
# 查看构建目标
bazel query //...

# 构建 GKI 内核
bazel build //gki2.0:kernel

# 或查看构建帮助
cat build/README.md
cat tools/README.md
```

**如果使用 Makefile 构建系统**：

```bash
# 查找主 Makefile
find . -name "Makefile" -path "*/kernel*" | head -1

# 查看构建说明
cat build/README.md
cat README.md
```

**如果使用自定义构建脚本**：

```bash
# 查找构建脚本
ls -la build/
ls -la tools/

# 查看构建帮助
./build/build.sh --help
# 或
python3 tools/build.py --help
```

---

## 3. 切换到指定标签

### 3.1 选择目标标签

**根据需求选择**：
- **最新稳定版本**：通常选择最新的 `_r` 修订版本
- **特定 Android 版本**：如 `android14-5.15-*`
- **特定 LTS 内核**：如 `*-5.15-*` 或 `*-6.1-*`

**查看标签列表**：
```bash
cd ~/android-kernel/common

# 列出所有 Android 14 的标签
git tag | grep "android14" | sort -V

# 列出所有 5.15 LTS 的标签
git tag | grep "5.15" | sort -V

# 查看最新标签
git tag | grep "android14-5.15" | sort -V | tail -5
```

### 3.2 切换到指定标签

```bash
# 切换到指定标签（例如：android14-5.15-2024-11_r3）
TAG="android14-5.15-2024-11_r3"
git checkout $TAG

# 验证切换成功
git describe --tags
git log --oneline -1

# 查看内核版本信息
head -20 Makefile | grep VERSION
```

### 3.3 创建工作分支（可选，推荐）

```bash
# 基于标签创建本地工作分支
TAG="android14-5.15-2024-11_r3"
git checkout -b work-$TAG $TAG

# 这样可以在不影响标签的情况下进行修改
# 查看当前分支
git branch
```

### 3.4 验证代码完整性

```bash
# 检查关键文件是否存在
ls -la Makefile
ls -la arch/arm64/
ls -la drivers/

# 检查内核版本
cat Makefile | grep -E "VERSION|PATCHLEVEL|SUBLEVEL"
```

---

## 4. 配置内核

### 4.1 清理之前的构建（首次可跳过）

```bash
cd ~/android-kernel/common

# 深度清理（删除所有构建产物和配置）
make ARCH=arm64 distclean

# 或轻度清理（保留配置）
make ARCH=arm64 clean

# 或仅清理构建产物
make ARCH=arm64 mrproper
```

### 4.2 使用 GKI 标准配置（推荐）

```bash
# 加载环境变量（如果还没加载）
source ~/.kernel_build_env.sh

# 使用 GKI 标准配置
make ARCH=arm64 gki_defconfig

# 配置会保存到 .config 文件
ls -la .config
```

### 4.3 查看和验证配置

```bash
# 查看配置摘要
make ARCH=arm64 kernelversion
make ARCH=arm64 kernelrelease

# 查看 GKI 相关配置
grep -E "GKI|KMI" .config

# 查看内核版本配置
grep "CONFIG_LOCALVERSION" .config

# 统计配置项数量
wc -l .config
```

### 4.4 自定义配置（可选）

如果需要修改配置：

#### 方法 1：交互式配置工具

```bash
# 使用 menuconfig（基于 ncurses 的图形界面）
make ARCH=arm64 menuconfig

# 或使用 nconfig（更现代的界面）
make ARCH=arm64 nconfig

# 操作说明：
# - 方向键：导航
# - 空格/回车：选择/取消选择
# - /：搜索配置项
# - ?：查看帮助
# - Esc Esc：退出并保存
```

#### 方法 2：直接编辑配置文件

```bash
# 编辑 .config 文件
vim .config
# 或
nano .config

# 修改后验证配置
make ARCH=arm64 olddefconfig
```

#### 方法 3：使用脚本修改配置

```bash
# 启用某个配置项
./scripts/config --enable CONFIG_XXX

# 禁用某个配置项
./scripts/config --disable CONFIG_XXX

# 设置配置值
./scripts/config --set-val CONFIG_XXX y

# 验证配置
make ARCH=arm64 olddefconfig
```

### 4.5 保存自定义配置（可选）

```bash
# 将当前配置保存为新的 defconfig
make ARCH=arm64 savedefconfig

# 复制到 arch/arm64/configs/ 目录
cp defconfig arch/arm64/configs/my_custom_defconfig

# 以后可以使用
# make ARCH=arm64 my_custom_defconfig
```

---

## 5. 编译内核

### 5.1 基本编译命令

```bash
cd ~/android-kernel/common

# 确保环境变量已设置
source ~/.kernel_build_env.sh

# 编译内核（使用所有 CPU 核心）
make ARCH=arm64 -j$(nproc)

# 或指定编译线程数
make ARCH=arm64 -j8  # 使用 8 个线程
```

### 5.2 详细编译步骤

#### 步骤 1：验证环境

```bash
# 检查架构设置
echo $ARCH
# 应该输出：arm64

# 检查交叉编译工具链
echo $CROSS_COMPILE
# 应该输出：aarch64-linux-gnu-

# 验证工具链可用
aarch64-linux-gnu-gcc --version
```

#### 步骤 2：开始编译

```bash
# 完整编译（内核 + 模块 + 设备树）
make ARCH=arm64 -j$(nproc) 2>&1 | tee build.log

# 这样可以将编译输出保存到 build.log 文件
# 同时也在终端显示
```

#### 步骤 3：仅编译内核（不编译模块）

```bash
# 只编译内核镜像
make ARCH=arm64 Image -j$(nproc)
```

#### 步骤 4：编译模块

```bash
# 编译所有模块
make ARCH=arm64 modules -j$(nproc)

# 编译特定模块
make ARCH=arm64 M=drivers/gpu/drm modules
```

### 5.3 编译输出文件

编译成功后，主要输出文件：

```bash
# 查看输出文件
ls -lh arch/arm64/boot/

# 主要文件：
# - Image：未压缩的内核镜像（通常 20-50MB）
# - Image.gz：gzip 压缩的内核镜像
# - Image.lz4：lz4 压缩的内核镜像（GKI 常用，8-15MB）

# 查看内核 ELF 文件（包含调试符号）
ls -lh vmlinux

# 查看符号表
ls -lh System.map
```

### 5.4 验证编译结果

```bash
# 检查内核版本
strings arch/arm64/boot/Image | grep "Linux version"

# 检查 GKI 信息
strings arch/arm64/boot/Image | grep -i "gki\|kmi"

# 检查文件大小（应该在合理范围内）
ls -lh arch/arm64/boot/Image*

# 验证内核镜像完整性
file arch/arm64/boot/Image
# 应该显示：Linux kernel ARM64 boot executable Image
```

### 5.5 编译时间参考

**典型编译时间**（取决于硬件）：
- **快速机器**（16 核心，32GB RAM）：10-20 分钟
- **中等机器**（8 核心，16GB RAM）：30-60 分钟
- **较慢机器**（4 核心，8GB RAM）：1-2 小时

**优化编译速度**：
```bash
# 使用更多并行任务（如果内存充足）
make ARCH=arm64 -j$(($(nproc) * 2))

# 使用 ccache 加速（如果已安装）
export CC="ccache aarch64-linux-gnu-gcc"
make ARCH=arm64 -j$(nproc)
```

---

## 6. 生成 GKI 镜像

### 6.1 生成压缩的内核镜像

```bash
cd ~/android-kernel/common

# 如果还没有生成 Image.lz4，需要手动压缩
# 方法 1：使用内核构建系统（如果支持）
make ARCH=arm64 Image.lz4

# 方法 2：手动压缩
lz4 -f arch/arm64/boot/Image arch/arm64/boot/Image.lz4

# 验证压缩文件
ls -lh arch/arm64/boot/Image.lz4
file arch/arm64/boot/Image.lz4
```

### 6.2 生成符号版本文件（用于模块兼容性）

```bash
# 生成模块符号版本文件
make ARCH=arm64 modules_prepare

# 检查生成的文件
ls -lh Module.symvers
ls -lh vmlinux.symvers  # GKI 需要

# 如果没有 vmlinux.symvers，从 Module.symvers 生成
# 或使用脚本
scripts/gen_ksymversions.sh vmlinux > vmlinux.symvers
```

### 6.3 生成模块信息文件

```bash
# 生成内置模块信息
scripts/extract-module-info.sh vmlinux > modules.builtin.modinfo

# 验证文件
ls -lh modules.builtin.modinfo
head -20 modules.builtin.modinfo
```

### 6.4 创建 GKI 发布包

```bash
# 创建发布目录
OUTPUT_DIR=~/kernel-build-output/gki-release
mkdir -p $OUTPUT_DIR

# 复制内核镜像
cp arch/arm64/boot/Image.lz4 $OUTPUT_DIR/

# 复制其他格式（可选）
cp arch/arm64/boot/Image.gz $OUTPUT_DIR/ 2>/dev/null || true
cp arch/arm64/boot/Image $OUTPUT_DIR/ 2>/dev/null || true

# 复制符号表
cp System.map $OUTPUT_DIR/

# 复制符号版本文件
cp vmlinux.symvers $OUTPUT_DIR/ 2>/dev/null || true
cp Module.symvers $OUTPUT_DIR/ 2>/dev/null || true

# 复制模块信息
cp modules.builtin.modinfo $OUTPUT_DIR/ 2>/dev/null || true

# 复制内核 ELF 文件（用于调试）
cp vmlinux $OUTPUT_DIR/

# 复制配置文件
cp .config $OUTPUT_DIR/

# 查看发布包内容
ls -lh $OUTPUT_DIR/
```

### 6.5 GKI 发布文件详解

当您看到 `gki2.0/released/` 目录下的文件时，以下是每个文件的详细说明：

#### 内核镜像文件

**1. `Image`（约 47MB）**
- **作用**：未压缩的内核镜像（ARM64 Image 格式）
- **用途**：可以直接刷写到设备的 boot 分区
- **格式**：ARM64 Linux 内核可执行镜像
- **使用**：`fastboot flash boot Image`

**2. `Image.gz`（约 21MB）**
- **作用**：gzip 压缩的内核镜像
- **用途**：压缩版本，节省空间，某些设备支持
- **格式**：gzip 压缩的 Image
- **使用**：`fastboot flash boot Image.gz`（如果设备支持）

**3. `Image.lz4`（约 25MB）**
- **作用**：lz4 压缩的内核镜像（GKI 标准格式）
- **用途**：**GKI 推荐格式**，压缩率高，解压速度快
- **格式**：lz4 压缩的 Image
- **使用**：`fastboot flash boot Image.lz4`（推荐）

**4. `boot-5.15.img`（约 67MB）**
- **作用**：完整的 boot 镜像（包含内核 + ramdisk）
- **用途**：某些设备需要完整的 boot.img，包含：
  - 内核镜像（Image）
  - ramdisk（初始文件系统）
  - 设备树（Device Tree）
- **格式**：Android boot 镜像格式
- **使用**：`fastboot flash boot boot-5.15.img`

#### 符号和调试文件

**5. `System.map`（约 7.4MB）**
- **作用**：内核符号表
- **用途**：
  - 将内核地址映射到函数/变量名
  - 调试内核崩溃（Oops/Panic）
  - 分析内核日志中的地址
- **格式**：文本文件，每行格式：`地址 类型 符号名`
- **示例**：
  ```
  ffffff8008080000 T _text
  ffffff8008080000 T stext
  ```

**6. `vmlinux.gz`（约 180MB）**
- **作用**：压缩的内核 ELF 文件（包含完整调试符号）
- **用途**：
  - 使用 GDB 调试内核
  - 分析内核崩溃
  - 查看函数源码位置
- **格式**：gzip 压缩的 ELF 文件
- **使用**：
  ```bash
  gunzip vmlinux.gz
  gdb vmlinux
  ```

**7. `vmlinux.symvers`（约 510KB）**
- **作用**：内核符号版本信息（KMI 相关）
- **用途**：
  - **模块兼容性检查**：确保模块使用正确的 KMI 版本
  - 模块编译时验证符号版本
  - GKI 模块开发必需
- **格式**：文本文件，包含符号的 CRC 和版本信息
- **重要性**：⭐⭐⭐⭐⭐（GKI 模块开发必需）

#### 模块相关文件

**8. `modules.builtin`（约 22KB）**
- **作用**：内置模块列表（编译进内核的模块）
- **用途**：
  - 列出所有编译进内核的模块名
  - 系统启动时自动加载这些模块
  - 用于模块依赖分析
- **格式**：文本文件，每行一个模块名
- **示例**：
  ```
  kernel/drivers/android/binder.ko
  kernel/drivers/char/random.ko
  ```

**9. `modules.builtin.modinfo`（约 145KB）**
- **作用**：内置模块的元信息
- **用途**：
  - 包含模块的版本、作者、描述等信息
  - 模块依赖关系
  - 模块参数信息
- **格式**：文本文件，包含模块元数据
- **使用**：`modinfo` 命令可以读取这些信息

**10. `system_dlkm_staging_archive.tar.gz`（约 61KB）**
- **作用**：系统 DLKM（Dynamically Loadable Kernel Module）暂存归档
- **用途**：
  - 包含系统级可加载模块
  - 用于 Android 13+ 的模块化架构
  - 系统更新时使用
- **格式**：tar.gz 压缩包
- **内容**：可能包含系统模块的 .ko 文件

#### 元数据文件

**11. `manifest_13919866.xml`（约 4KB）**
- **作用**：GKI 发布清单文件
- **用途**：
  - 记录 GKI 版本信息
  - 包含构建信息（时间、构建号等）
  - 列出所有文件的哈希值（用于验证）
  - 记录 KMI 版本信息
- **格式**：XML 文件
- **重要性**：用于验证 GKI 完整性和版本

**12. `spl.info`（约 11 字节）**
- **作用**：SPL（Secondary Program Loader）信息
- **用途**：
  - 某些设备的分区信息
  - 启动加载器相关信息
- **格式**：文本文件
- **注意**：不是所有设备都需要

#### 文件使用场景总结

| 文件 | 刷机使用 | 调试使用 | 模块开发 | 重要性 |
|------|---------|---------|---------|--------|
| `Image.lz4` | ✅ 主要 | ❌ | ❌ | ⭐⭐⭐⭐⭐ |
| `boot-5.15.img` | ✅ 完整 boot | ❌ | ❌ | ⭐⭐⭐⭐ |
| `System.map` | ❌ | ✅ 必需 | ❌ | ⭐⭐⭐⭐ |
| `vmlinux.gz` | ❌ | ✅ 必需 | ❌ | ⭐⭐⭐ |
| `vmlinux.symvers` | ❌ | ❌ | ✅ 必需 | ⭐⭐⭐⭐⭐ |
| `modules.builtin.modinfo` | ❌ | ⚠️ 有用 | ✅ 有用 | ⭐⭐⭐ |
| `manifest_*.xml` | ⚠️ 验证 | ❌ | ❌ | ⭐⭐⭐ |

#### 实际使用示例

**场景 1：刷入内核到设备**
```bash
# 推荐方式：使用 Image.lz4
fastboot flash boot Image.lz4

# 或使用完整的 boot 镜像
fastboot flash boot boot-5.15.img
```

**场景 2：调试内核崩溃**
```bash
# 1. 解压 vmlinux
gunzip vmlinux.gz

# 2. 使用 GDB 加载
gdb vmlinux

# 3. 使用 System.map 查找符号
grep "crash_function" System.map
```

**场景 3：开发内核模块**
```bash
# 1. 使用 vmlinux.symvers 验证模块兼容性
# 在模块编译时，Makefile 会使用这个文件

# 2. 查看模块信息
cat modules.builtin.modinfo | grep "your_module"

# 3. 检查模块依赖
cat modules.builtin | grep "dependency_module"
```

**场景 4：验证 GKI 版本**
```bash
# 查看清单文件
cat manifest_13919866.xml

# 或查看内核版本
strings Image.lz4 | grep "Linux version"
strings Image.lz4 | grep -i "gki\|kmi"
```

#### 文件大小说明

- **Image.lz4（25MB）**：压缩后的内核，适合刷机
- **Image（47MB）**：未压缩内核，某些场景需要
- **vmlinux.gz（180MB）**：包含完整调试符号，仅调试时使用
- **System.map（7.4MB）**：符号表，调试必需
- **vmlinux.symvers（510KB）**：KMI 符号版本，模块开发必需

**建议**：
- **日常刷机**：只需要 `Image.lz4` 或 `boot-5.15.img`
- **调试问题**：需要 `System.map` 和 `vmlinux.gz`
- **开发模块**：需要 `vmlinux.symvers` 和 `modules.builtin.modinfo`

### 6.5 生成清单文件（可选）

```bash
# 创建简单的清单文件
cat > $OUTPUT_DIR/manifest.txt << EOF
Kernel Version: $(make ARCH=arm64 kernelversion)
Kernel Release: $(make ARCH=arm64 kernelrelease)
Build Date: $(date)
Build Host: $(hostname)
GKI Version: $(grep CONFIG_GKI .config | head -1)
KMI Version: $(grep CONFIG_KMI .config | head -1)
EOF

cat $OUTPUT_DIR/manifest.txt
```

---

## 7. 准备刷机环境

### 7.1 设备准备

#### 启用开发者选项和 USB 调试

1. **在设备上**：
   - 进入"设置" → "关于手机"
   - 连续点击"版本号" 7 次，启用开发者选项
   - 返回"设置" → "开发者选项"
   - 启用"USB 调试"
   - 启用"OEM 解锁"（如果需要解锁 bootloader）

#### 连接设备

```bash
# 使用 USB 线连接设备到电脑

# 检查设备连接
adb devices

# 应该显示设备序列号
# 例如：
# List of devices attached
# ABC123XYZ    device
```

**如果设备未识别**：
```bash
# 检查 USB 权限
lsusb
# 查看设备 ID

# 添加 udev 规则（Linux）
sudo vim /etc/udev/rules.d/51-android.rules
# 添加：
# SUBSYSTEM=="usb", ATTR{idVendor}=="<vendor_id>", MODE="0666", GROUP="plugdev"

# 重新加载 udev 规则
sudo udevadm control --reload-rules
sudo udevadm trigger

# 重新连接设备
adb kill-server
adb start-server
adb devices
```

### 7.2 进入 Fastboot 模式

#### 方法 1：通过 ADB

```bash
# 设备已通过 USB 连接并启用 USB 调试
adb reboot bootloader

# 等待设备重启到 bootloader 模式
```

#### 方法 2：手动进入

1. 关闭设备
2. 按住特定按键组合（因设备而异）：
   - **大多数设备**：音量下 + 电源键
   - **某些设备**：音量上 + 电源键
   - 查看设备说明书确认

#### 验证 Fastboot 连接

```bash
# 检查 fastboot 连接
fastboot devices

# 应该显示设备序列号
# 例如：
# ABC123XYZ    fastboot
```

**如果 fastboot 未识别设备**：
```bash
# 检查 USB 连接
lsusb

# 尝试不同的 USB 端口
# 尝试不同的 USB 线
# 检查 fastboot 驱动（Windows）
```

### 7.3 解锁 Bootloader（如果需要）

**警告**：解锁 bootloader 会：
- 清除设备数据
- 可能使设备失去保修
- 降低设备安全性

```bash
# 检查 bootloader 锁定状态
fastboot getvar unlocked

# 如果显示 "unlocked: no"，需要解锁

# 解锁 bootloader（需要设备支持）
fastboot oem unlock
# 或
fastboot flashing unlock

# 按照设备屏幕提示确认解锁
# 注意：这会清除设备数据

# 验证解锁状态
fastboot getvar unlocked
# 应该显示 "unlocked: yes"
```

**某些设备**可能需要：
- 在设备上手动确认解锁
- 使用设备特定的解锁工具
- 申请解锁码（如小米、华为等）

### 7.4 备份原始内核（强烈推荐）

```bash
# 方法 1：通过 ADB 备份（如果设备已 root）
adb shell su -c "dd if=/dev/block/bootdevice/by-name/boot of=/sdcard/boot_backup.img"
adb pull /sdcard/boot_backup.img ~/boot_backup.img

# 方法 2：通过 fastboot 备份
# 注意：某些设备可能不支持直接读取 boot 分区
fastboot boot ~/boot_backup.img  # 如果已有备份

# 方法 3：从设备提取（需要 root）
adb shell
su
dd if=/dev/block/platform/*/by-name/boot of=/sdcard/boot_original.img
exit
exit
adb pull /sdcard/boot_original.img ~/
```

---

## 8. 刷入内核镜像

### 8.1 准备内核镜像

```bash
# 确认内核镜像路径
KERNEL_IMAGE=~/android-kernel/common/arch/arm64/boot/Image.lz4

# 或使用之前创建的发布包
KERNEL_IMAGE=~/kernel-build-output/gki-release/Image.lz4

# 验证文件存在
ls -lh $KERNEL_IMAGE

# 检查文件类型
file $KERNEL_IMAGE
```

### 8.2 刷入方法

#### 方法 1：直接刷入 boot 分区（永久）

```bash
# 确保设备在 fastboot 模式
fastboot devices

# 刷入内核镜像到 boot 分区
fastboot flash boot $KERNEL_IMAGE

# 等待刷入完成
# 输出示例：
# Sending 'boot' (XXXXX KB)...
# OKAY [  X.XXXs]
# Writing 'boot'...
# OKAY [  X.XXXs]
# Finished. Total time: X.XXXs
```

#### 方法 2：临时启动（不刷入，仅测试）

```bash
# 临时启动新内核（不修改设备）
fastboot boot $KERNEL_IMAGE

# 设备会使用新内核启动
# 重启后会恢复原内核
# 适合测试新内核
```

#### 方法 3：刷入 boot.img（如果使用完整 boot 镜像）

```bash
# 某些设备需要完整的 boot.img（包含内核 + ramdisk）
# 需要先打包 boot.img

# 使用 Android 工具打包
# mkbootimg --kernel Image.lz4 --ramdisk ramdisk.cpio --output boot.img

# 然后刷入
fastboot flash boot boot.img
```

### 8.3 刷入后操作

```bash
# 清除缓存（可选，但推荐）
fastboot erase cache

# 重启设备
fastboot reboot

# 或重启到系统
fastboot reboot system

# 等待设备启动
# 首次启动可能需要较长时间
```

### 8.4 刷入完整系统镜像（高级）

如果需要刷入包含内核的完整系统：

```bash
# 构建完整系统镜像（需要 AOSP 环境）
# source build/envsetup.sh
# lunch <target>
# make bootimage

# 刷入 boot 镜像
fastboot flash boot out/target/product/<device>/boot.img

# 或刷入完整系统
fastboot flashall
```

---

## 9. 验证结果

### 9.1 设备启动验证

```bash
# 等待设备完全启动后，连接 USB

# 检查设备连接
adb devices

# 如果设备正常启动，应该能看到设备
```

### 9.2 验证内核版本

```bash
# 方法 1：通过 ADB
adb shell uname -r
# 应该显示新编译的内核版本

adb shell cat /proc/version
# 显示详细的内核版本信息

# 方法 2：在设备上直接查看
# 设置 → 关于手机 → 内核版本
```

### 9.3 验证 GKI 信息

```bash
# 检查 GKI 相关配置
adb shell zcat /proc/config.gz | grep GKI

# 检查内核模块
adb shell lsmod

# 检查内核日志
adb shell dmesg | head -50
```

### 9.4 功能测试

```bash
# 测试基本功能
adb shell getprop ro.build.version.release
adb shell getprop ro.build.version.sdk

# 测试系统稳定性
adb shell top -n 1

# 检查内核日志中的错误
adb shell dmesg | grep -i error
adb shell dmesg | grep -i "fail\|warn" | head -20
```

### 9.5 性能验证

```bash
# 检查系统负载
adb shell uptime

# 检查内存使用
adb shell cat /proc/meminfo | head -10

# 检查 CPU 信息
adb shell cat /proc/cpuinfo | head -20
```

### 9.6 回退到原始内核（如果出现问题）

```bash
# 如果新内核有问题，可以回退

# 方法 1：使用备份的内核
fastboot flash boot ~/boot_backup.img
fastboot reboot

# 方法 2：从设备恢复（如果支持）
# 进入 Recovery 模式
# 选择恢复出厂设置或恢复备份

# 方法 3：刷入官方固件
# 下载官方固件包
# 使用 fastboot 或设备特定工具刷入
```

---

## 10. 常见问题排查

### 10.1 编译问题

#### 问题 1：找不到交叉编译工具链

**错误信息**：
```
make: aarch64-linux-gnu-gcc: Command not found
```

**解决方案**：
```bash
# 安装工具链
sudo apt-get install gcc-aarch64-linux-gnu

# 或设置正确的 CROSS_COMPILE 路径
export CROSS_COMPILE=/path/to/toolchain/bin/aarch64-linux-gnu-

# 验证工具链
which aarch64-linux-gnu-gcc
aarch64-linux-gnu-gcc --version
```

#### 问题 2：配置错误

**错误信息**：
```
.config:1234:warning: override: reassigning to symbol XXX
```

**解决方案**：
```bash
# 清理并重新配置
make ARCH=arm64 distclean
make ARCH=arm64 gki_defconfig
make ARCH=arm64 olddefconfig
```

#### 问题 3：内存不足

**错误信息**：
```
virtual memory exhausted: Cannot allocate memory
```

**解决方案**：
```bash
# 减少并行编译任务
make ARCH=arm64 -j4  # 使用 4 个线程

# 或增加 swap 空间
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 永久启用 swap
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

#### 问题 4：缺少头文件或库

**错误信息**：
```
fatal error: xxx.h: No such file or directory
```

**解决方案**：
```bash
# 安装缺失的开发库
sudo apt-get install libssl-dev libelf-dev libncurses5-dev

# 检查 include 路径
make ARCH=arm64 V=1  # 显示详细编译命令
```

### 10.2 刷机问题

#### 问题 1：设备未识别

**症状**：`fastboot devices` 无输出

**解决方案**：
```bash
# 检查 USB 连接
lsusb

# 检查 fastboot 服务
sudo fastboot devices

# 尝试不同的 USB 端口和线缆
# 检查设备是否在 fastboot 模式（显示 fastboot 界面）
# 安装设备特定的 fastboot 驱动（Windows）
```

#### 问题 2：权限被拒绝

**错误信息**：
```
fastboot: error: insufficient permissions for device
```

**解决方案**：
```bash
# Linux：添加 udev 规则
sudo vim /etc/udev/rules.d/51-android.rules
# 添加设备规则

# 或使用 sudo
sudo fastboot flash boot $KERNEL_IMAGE

# 将用户添加到 plugdev 组
sudo usermod -aG plugdev $USER
# 重新登录
```

#### 问题 3：刷入失败

**错误信息**：
```
FAILED (remote: 'partition table doesn't exist')
```

**解决方案**：
```bash
# 检查分区名称
fastboot getvar partition-type:boot

# 某些设备使用不同的分区名称
fastboot flash boot_a $KERNEL_IMAGE  # A/B 分区设备
fastboot flash boot_b $KERNEL_IMAGE

# 或检查设备文档
```

#### 问题 4：设备无法启动

**症状**：刷入后设备无法启动，卡在启动画面

**解决方案**：
```bash
# 1. 进入 fastboot 模式（如果可能）
# 按住音量下 + 电源键

# 2. 刷回原始内核
fastboot flash boot ~/boot_backup.img

# 3. 清除缓存
fastboot erase cache

# 4. 重启
fastboot reboot

# 5. 如果仍然无法启动，可能需要刷入完整固件
```

### 10.3 运行时问题

#### 问题 1：模块加载失败

**症状**：某些功能不工作，dmesg 显示模块错误

**解决方案**：
```bash
# 检查模块依赖
adb shell lsmod

# 检查内核日志
adb shell dmesg | grep -i "module\|fail"

# 检查 KMI 版本兼容性
adb shell cat /proc/version
# 确保模块使用相同的 KMI 版本编译
```

#### 问题 2：性能问题

**症状**：设备运行缓慢，卡顿

**解决方案**：
```bash
# 检查系统负载
adb shell top

# 检查内存使用
adb shell cat /proc/meminfo

# 检查内核日志中的错误
adb shell dmesg | grep -i error

# 可能需要调整内核配置或回退到稳定版本
```

---

## 11. 完整脚本示例

### 11.1 一键编译脚本

创建 `build_kernel.sh`：

```bash
#!/bin/bash
# build_kernel.sh - 一键编译内核脚本

set -e  # 遇到错误立即退出

# 配置变量
KERNEL_DIR="${KERNEL_DIR:-$HOME/android-kernel/common}"
ARCH="arm64"
CONFIG="gki_defconfig"
JOBS="${JOBS:-$(nproc)}"
OUTPUT_DIR="${OUTPUT_DIR:-$HOME/kernel-build-output}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查环境
check_environment() {
    log_info "检查编译环境..."
    
    # 检查工具链
    if ! command -v aarch64-linux-gnu-gcc &> /dev/null; then
        log_error "未找到交叉编译工具链，请安装：sudo apt-get install gcc-aarch64-linux-gnu"
        exit 1
    fi
    
    # 检查内核目录
    if [ ! -d "$KERNEL_DIR" ]; then
        log_error "内核目录不存在: $KERNEL_DIR"
        exit 1
    fi
    
    # 设置环境变量
    export ARCH=$ARCH
    export CROSS_COMPILE=aarch64-linux-gnu-
    
    log_info "环境检查完成"
}

# 配置内核
configure_kernel() {
    log_info "配置内核: $CONFIG"
    cd "$KERNEL_DIR"
    
    # 清理（可选）
    if [ "$1" == "clean" ]; then
        log_info "清理之前的构建..."
        make ARCH=$ARCH distclean
    fi
    
    # 配置
    make ARCH=$ARCH $CONFIG
    
    log_info "内核配置完成"
}

# 编译内核
build_kernel() {
    log_info "开始编译内核（使用 $JOBS 个并行任务）..."
    cd "$KERNEL_DIR"
    
    # 编译
    make ARCH=$ARCH -j$JOBS 2>&1 | tee build.log
    
    # 检查编译结果
    if [ -f "arch/$ARCH/boot/Image" ]; then
        log_info "内核编译成功！"
        ls -lh arch/$ARCH/boot/Image*
    else
        log_error "内核编译失败，请查看 build.log"
        exit 1
    fi
}

# 生成 GKI 镜像
create_gki_image() {
    log_info "生成 GKI 镜像..."
    cd "$KERNEL_DIR"
    
    # 生成 lz4 压缩镜像
    if [ ! -f "arch/$ARCH/boot/Image.lz4" ]; then
        log_info "压缩内核镜像..."
        lz4 -f arch/$ARCH/boot/Image arch/$ARCH/boot/Image.lz4
    fi
    
    # 创建输出目录
    mkdir -p "$OUTPUT_DIR"
    
    # 复制文件
    cp arch/$ARCH/boot/Image.lz4 "$OUTPUT_DIR/"
    cp System.map "$OUTPUT_DIR/" 2>/dev/null || true
    cp vmlinux "$OUTPUT_DIR/" 2>/dev/null || true
    cp .config "$OUTPUT_DIR/" 2>/dev/null || true
    
    log_info "GKI 镜像已生成: $OUTPUT_DIR/Image.lz4"
    ls -lh "$OUTPUT_DIR/"
}

# 主函数
main() {
    log_info "=== 内核编译脚本 ==="
    log_info "内核目录: $KERNEL_DIR"
    log_info "架构: $ARCH"
    log_info "配置: $CONFIG"
    log_info "并行任务: $JOBS"
    echo
    
    check_environment
    configure_kernel "$1"
    build_kernel
    create_gki_image
    
    log_info "=== 编译完成 ==="
    log_info "内核镜像: $OUTPUT_DIR/Image.lz4"
    
    # 显示内核版本
    if [ -f "$KERNEL_DIR/vmlinux" ]; then
        log_info "内核版本:"
        strings "$KERNEL_DIR/arch/$ARCH/boot/Image" | grep "Linux version" | head -1
    fi
}

# 运行主函数
main "$@"
```

**使用方法**：
```bash
chmod +x build_kernel.sh
./build_kernel.sh          # 正常编译
./build_kernel.sh clean    # 清理后编译
```

### 11.2 一键刷机脚本

创建 `flash_kernel.sh`：

```bash
#!/bin/bash
# flash_kernel.sh - 一键刷机脚本

set -e

# 配置变量
KERNEL_IMAGE="${1:-$HOME/kernel-build-output/Image.lz4}"
BACKUP_DIR="$HOME/kernel-backup"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查 fastboot 连接
check_fastboot() {
    log_info "检查 fastboot 连接..."
    
    if ! command -v fastboot &> /dev/null; then
        log_error "未找到 fastboot，请安装：sudo apt-get install android-tools-fastboot"
        exit 1
    fi
    
    if ! fastboot devices | grep -q fastboot; then
        log_error "未检测到 fastboot 设备，请："
        log_error "1. 确保设备已连接"
        log_error "2. 进入 fastboot 模式：adb reboot bootloader"
        exit 1
    fi
    
    log_info "Fastboot 连接正常"
    fastboot devices
}

# 备份原始内核
backup_kernel() {
    log_info "备份原始内核..."
    
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/boot_$(date +%Y%m%d_%H%M%S).img"
    
    # 尝试通过 fastboot 获取 boot 分区信息
    log_warn "注意：某些设备可能无法直接备份 boot 分区"
    log_warn "建议手动备份或从设备提取"
    
    log_info "备份信息已记录到: $BACKUP_FILE.info"
    fastboot getvar all > "$BACKUP_FILE.info" 2>&1 || true
}

# 刷入内核
flash_kernel() {
    log_info "准备刷入内核: $KERNEL_IMAGE"
    
    if [ ! -f "$KERNEL_IMAGE" ]; then
        log_error "内核镜像不存在: $KERNEL_IMAGE"
        exit 1
    fi
    
    log_info "文件信息:"
    ls -lh "$KERNEL_IMAGE"
    file "$KERNEL_IMAGE"
    
    # 确认
    read -p "确认刷入内核？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "已取消"
        exit 0
    fi
    
    # 刷入
    log_info "刷入内核..."
    fastboot flash boot "$KERNEL_IMAGE"
    
    # 清除缓存
    log_info "清除缓存..."
    fastboot erase cache 2>/dev/null || log_warn "无法清除缓存（某些设备不支持）"
    
    log_info "刷入完成！"
}

# 重启设备
reboot_device() {
    log_info "重启设备..."
    read -p "是否立即重启设备？(y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        fastboot reboot
        log_info "设备正在重启..."
    else
        log_info "请手动重启设备: fastboot reboot"
    fi
}

# 主函数
main() {
    log_info "=== 内核刷机脚本 ==="
    
    if [ -z "$1" ]; then
        log_info "使用方法: $0 <kernel_image>"
        log_info "示例: $0 ~/kernel-build-output/Image.lz4"
        exit 1
    fi
    
    check_fastboot
    backup_kernel
    flash_kernel
    reboot_device
    
    log_info "=== 刷机完成 ==="
}

main "$@"
```

**使用方法**：
```bash
chmod +x flash_kernel.sh
./flash_kernel.sh ~/kernel-build-output/Image.lz4
```

### 11.3 完整流程脚本

创建 `build_and_flash.sh`：

```bash
#!/bin/bash
# build_and_flash.sh - 完整流程：编译 + 刷机

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SCRIPT="$SCRIPT_DIR/build_kernel.sh"
FLASH_SCRIPT="$SCRIPT_DIR/flash_kernel.sh"
KERNEL_IMAGE="$HOME/kernel-build-output/Image.lz4"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# 主函数
main() {
    log_info "=== 完整流程：编译 + 刷机 ==="
    
    # 步骤 1：编译
    log_info "步骤 1/2: 编译内核"
    if [ -f "$BUILD_SCRIPT" ]; then
        "$BUILD_SCRIPT"
    else
        log_warn "未找到编译脚本，跳过编译步骤"
    fi
    
    # 步骤 2：刷机
    log_info "步骤 2/2: 刷入内核"
    if [ -f "$FLASH_SCRIPT" ] && [ -f "$KERNEL_IMAGE" ]; then
        "$FLASH_SCRIPT" "$KERNEL_IMAGE"
    else
        log_warn "未找到刷机脚本或内核镜像，请手动刷入"
        log_info "内核镜像位置: $KERNEL_IMAGE"
    fi
    
    log_info "=== 流程完成 ==="
}

main "$@"
```

---

## 12. 总结

### 12.1 完整流程回顾

1. ✅ **环境准备**：安装工具链和依赖
2. ✅ **获取代码**：克隆 ACK 仓库
3. ✅ **切换标签**：选择目标内核版本
4. ✅ **配置内核**：使用 gki_defconfig 或自定义配置
5. ✅ **编译内核**：生成内核镜像
6. ✅ **生成 GKI**：创建发布包
7. ✅ **准备设备**：启用 USB 调试，进入 fastboot
8. ✅ **刷入镜像**：使用 fastboot 刷入
9. ✅ **验证结果**：检查内核版本和功能

### 12.2 关键命令速查

```bash
# 环境设置
export ARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-

# 获取代码
git clone https://android.googlesource.com/kernel/common
cd common
git checkout android14-5.15-2024-11_r3

# 配置和编译
make ARCH=arm64 gki_defconfig
make ARCH=arm64 -j$(nproc)

# 刷机
fastboot flash boot arch/arm64/boot/Image.lz4
fastboot reboot
```

### 12.3 重要提示

1. **备份原始内核**：刷机前务必备份
2. **测试内核**：使用 `fastboot boot` 先测试
3. **保持兼容**：确保 KMI 版本兼容
4. **查看日志**：遇到问题查看编译日志和内核日志
5. **安全第一**：解锁 bootloader 会清除数据并可能失去保修

### 12.4 下一步

- 学习如何修改内核配置
- 了解如何开发内核模块
- 学习如何调试内核问题
- 贡献代码回 ACK 仓库

---

**文档版本**：v1.0  
**最后更新**：2024年  
**维护者**：稳定性学习项目
