# AOSP 编译环境搭建

## 📋 目录

1. [系统要求](#1-系统要求)
2. [安装编译依赖](#2-安装编译依赖)
3. [安装 Repo 工具](#3-安装-repo-工具)
4. [获取 AOSP 源码](#4-获取-aosp-源码)
5. [配置编译环境](#5-配置编译环境)
6. [选择设备配置](#6-选择设备配置)
7. [验证环境](#7-验证环境)
8. [常见问题](#8-常见问题)

---

## 1. 系统要求

### 1.1 推荐操作系统

**官方支持**：
- **Ubuntu 18.04 LTS** 或更高版本（推荐 Ubuntu 20.04/22.04）
- **Debian 10** 或更高版本
- **macOS 10.15** 或更高版本（本文档主要针对 Linux）

**其他 Linux 发行版**：
- Fedora、CentOS、Arch Linux 等也可以，但需要相应调整

### 1.2 硬件要求

**最低要求**：
- **CPU**：4 核心
- **内存**：16GB RAM
- **磁盘空间**：200GB 可用空间（源码 + 编译产物）

**推荐配置**：
- **CPU**：8+ 核心（编译速度更快）
- **内存**：32GB+ RAM（可以并行编译更多）
- **磁盘空间**：300GB+ 可用空间
- **SSD**：强烈推荐使用 SSD（大幅提升编译速度）

### 1.3 网络要求

- 稳定的网络连接（下载源码需要大量数据）
- 能够访问 Google 服务器（或使用镜像源）
- 建议使用代理或镜像加速下载

---

## 2. 安装编译依赖

### 2.1 Ubuntu/Debian 系统

#### 安装基础工具

```bash
# 更新包列表
sudo apt-get update

# 安装基础编译工具
sudo apt-get install -y \
    git-core \
    gnupg \
    flex \
    bison \
    build-essential \
    zip \
    curl \
    zlib1g-dev \
    gcc-multilib \
    g++-multilib \
    libc6-dev-i386 \
    libncurses5 \
    lib32ncurses5-dev \
    x11proto-core-dev \
    libx11-dev \
    lib32z1-dev \
    libgl1-mesa-dev \
    libxml2-utils \
    xsltproc \
    unzip \
    fontconfig
```

#### 安装 Python 和 Java

```bash
# 安装 Python 3
sudo apt-get install -y python3 python3-pip

# Android 16 需要 Java 17
sudo apt-get install -y openjdk-17-jdk

# 设置 Java 环境变量
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$PATH:$JAVA_HOME/bin

# 验证 Java 版本
java -version
# 应该显示: openjdk version "17.x.x"
```

#### 安装其他依赖

```bash
# 安装额外的编译工具
sudo apt-get install -y \
    libssl-dev \
    libffi-dev \
    python3-dev \
    rsync \
    imagemagick \
    ccache \
    lzop \
    schedtool
```

### 2.2 其他 Linux 发行版

#### Fedora/RHEL/CentOS

```bash
sudo dnf install -y \
    git-core gnupg flex bison gperf \
    build-essential zip curl zlib-devel \
    gcc-multilib g++-multilib libc6-dev-i386 \
    libX11-devel lib32z1-devel \
    libgl1-mesa-dev libxml2-utils \
    xsltproc unzip fontconfig \
    python3 python3-pip \
    java-17-openjdk-devel
```

#### Arch Linux

```bash
sudo pacman -S --needed \
    git gnupg flex bison gperf \
    base-devel zip curl zlib \
    multilib-devel lib32-glibc \
    libx11 lib32-zlib \
    mesa libxml2 \
    python python-pip \
    jdk17-openjdk
```

### 2.3 安装 ccache（可选但推荐）

ccache 可以加速重复编译：

```bash
# Ubuntu/Debian
sudo apt-get install -y ccache

# 配置 ccache
export USE_CCACHE=1
export CCACHE_EXEC=/usr/bin/ccache
ccache -M 50G  # 设置缓存大小为 50GB

# 添加到 ~/.bashrc
echo 'export USE_CCACHE=1' >> ~/.bashrc
echo 'export CCACHE_EXEC=/usr/bin/ccache' >> ~/.bashrc
```

---

## 3. 安装 Repo 工具

Repo 是 Google 开发的用于管理多个 Git 仓库的工具。

### 3.1 安装 Repo

```bash
# 创建 bin 目录（如果不存在）
mkdir -p ~/bin

# 下载 repo 工具
curl https://storage.googleapis.com/git-repo-downloads/repo > ~/bin/repo

# 或使用镜像（如果无法访问 Google）
# curl https://mirrors.tuna.tsinghua.edu.cn/git-repo-downloads/repo > ~/bin/repo

# 添加执行权限
chmod a+x ~/bin/repo

# 添加到 PATH
export PATH=~/bin:$PATH

# 添加到 ~/.bashrc（永久生效）
echo 'export PATH=~/bin:$PATH' >> ~/.bashrc
source ~/.bashrc

# 验证安装
repo --version
```

### 3.2 配置 Git

```bash
# 配置 Git 用户信息
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# 配置 Git 颜色输出
git config --global color.ui auto

# 验证配置
git config --list
```

---

## 4. 获取 AOSP 源码

### 4.1 创建工作目录

```bash
# 创建 AOSP 工作目录
mkdir -p ~/aosp
cd ~/aosp
```

### 4.2 初始化 Repo 仓库

#### 方法1：从官方源（需要访问 Google）

```bash
# 初始化 repo（指定 Android 版本）
# Android 16 分支名通常是 android-16.0.0_rXX
repo init -u https://android.googlesource.com/platform/manifest \
    -b android-16.0.0_r1

# 或使用特定标签
repo init -u https://android.googlesource.com/platform/manifest \
    -b refs/tags/android-16.0.0_r1
```

#### 方法2：使用镜像源（推荐，速度更快）

**清华大学镜像**：
```bash
repo init -u https://mirrors.tuna.tsinghua.edu.cn/git/AOSP/platform/manifest \
    -b android-16.0.0_r1
```

**中科大镜像**：
```bash
repo init -u https://mirrors.ustc.edu.cn/aosp-monthly/ \
    -b android-16.0.0_r1
```

### 4.3 同步源码

```bash
# 同步所有源码（这需要很长时间，可能需要数小时）
repo sync -j$(nproc)

# 如果同步中断，可以继续同步
repo sync -j$(nproc) -c  # -c 只同步当前分支

# 查看同步进度
repo sync -j$(nproc) --progress
```

**同步时间**：
- 首次同步：2-4 小时（取决于网络速度）
- 源码大小：约 100-150GB

### 4.4 查看可用分支

```bash
# 查看所有可用分支
cd .repo/manifests
git branch -a

# 切换到其他 Android 版本
cd ~/aosp
repo init -b android-15.0.0_r1
repo sync -j$(nproc)
```

---

## 5. 配置编译环境

### 5.1 设置编译环境变量

创建环境配置文件 `build/envsetup.sh` 会自动设置环境变量，但也可以手动设置：

```bash
# 进入 AOSP 源码目录
cd ~/aosp

# 加载编译环境
source build/envsetup.sh

# 这会设置以下环境变量：
# - ANDROID_BUILD_TOP: AOSP 源码根目录
# - OUT_DIR: 编译输出目录
# - 各种编译工具路径
```

### 5.2 配置 Jack（如果使用旧版本）

Android 16 使用 Soong 构建系统，不需要 Jack。

### 5.3 设置编译选项

```bash
# 设置编译线程数（使用所有 CPU 核心）
export JACK_SERVER_VM_ARGUMENTS="-Dfile.encoding=UTF-8 -XX:+TieredCompilation -Xmx4g"

# 设置 Java 堆大小
export JAVA_TOOL_OPTIONS="-Xmx8g"

# 设置编译输出目录（可选）
export OUT_DIR=out
```

---

## 6. 选择设备配置

### 6.1 查看可用设备

```bash
# 加载环境后，查看可用设备
source build/envsetup.sh
lunch

# 会显示设备列表，例如：
# 1. aosp_arm-eng
# 2. aosp_arm64-eng
# 3. aosp_x86-eng
# 4. aosp_x86_64-eng
# 5. aosp_car_arm-userdebug
# ...
```

### 6.2 选择设备配置

```bash
# 方法1：交互式选择
lunch
# 输入数字选择设备

# 方法2：直接指定
lunch aosp_arm64-eng

# 方法3：指定完整名称
lunch aosp_arm64-eng
```

### 6.3 设备配置说明

设备配置格式：`{product}-{variant}`

**Product（产品）**：
- `aosp_arm64` - ARM64 模拟器
- `aosp_x86_64` - x86_64 模拟器
- `sdk_phone_arm64` - SDK 手机（ARM64）
- `{vendor}_{device}` - 特定设备（如 `pixel_6`）

**Variant（变体）**：
- `eng` - 工程版本（包含调试工具，可 root）
- `userdebug` - 用户调试版本（可调试，可 root）
- `user` - 用户版本（生产版本，不可 root）

### 6.4 验证设备配置

```bash
# 查看当前配置
echo $TARGET_PRODUCT
echo $TARGET_BUILD_VARIANT
echo $TARGET_BUILD_TYPE

# 查看设备信息
get_build_var TARGET_ARCH
get_build_var TARGET_CPU_ABI
```

---

## 7. 验证环境

### 7.1 检查编译环境

```bash
# 检查所有必需工具
which git
which repo
which java
java -version
python3 --version

# 检查环境变量
echo $ANDROID_BUILD_TOP
echo $JAVA_HOME
echo $PATH
```

### 7.2 测试编译

```bash
# 尝试编译一个简单的目标
m -j$(nproc) nothing

# 或编译系统镜像（这会花费很长时间）
m -j$(nproc) systemimage

# 查看编译输出
ls -lh $OUT/system.img
```

### 7.3 检查磁盘空间

```bash
# 检查可用空间
df -h

# 检查源码目录大小
du -sh ~/aosp

# 检查编译输出目录大小（编译后）
du -sh ~/aosp/out
```

---

## 8. 常见问题

### 8.1 网络问题

**问题**：无法访问 Google 服务器

**解决方案**：
```bash
# 使用镜像源
repo init -u https://mirrors.tuna.tsinghua.edu.cn/git/AOSP/platform/manifest

# 或配置代理
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
```

### 8.2 内存不足

**问题**：编译时内存不足

**解决方案**：
```bash
# 减少并行编译线程数
m -j4  # 使用4个线程而不是所有核心

# 增加 swap 空间
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### 8.3 Java 版本问题

**问题**：Java 版本不匹配

**解决方案**：
```bash
# Android 16 需要 Java 17
sudo apt-get install -y openjdk-17-jdk

# 设置正确的 Java 版本
sudo update-alternatives --config java
sudo update-alternatives --config javac

# 验证版本
java -version
```

### 8.4 磁盘空间不足

**问题**：编译时磁盘空间不足

**解决方案**：
```bash
# 清理旧的编译产物
make clean
# 或
rm -rf out

# 使用符号链接将 out 目录放到其他位置
ln -s /path/to/large/disk/out ~/aosp/out
```

### 8.5 依赖缺失

**问题**：编译时提示缺少依赖

**解决方案**：
```bash
# 安装缺失的依赖
sudo apt-get install -y <package-name>

# 或使用 apt-file 查找
sudo apt-get install -y apt-file
sudo apt-file update
apt-file search <missing-file>
```

---

## 总结

AOSP 编译环境搭建步骤：

1. ✅ **系统要求**：Ubuntu 20.04+，16GB+ RAM，200GB+ 磁盘
2. ✅ **安装依赖**：编译工具、Python、Java 17
3. ✅ **安装 Repo**：用于管理多个 Git 仓库
4. ✅ **获取源码**：使用 repo sync 同步 AOSP 源码
5. ✅ **配置环境**：source build/envsetup.sh
6. ✅ **选择设备**：lunch 选择目标设备
7. ✅ **验证环境**：测试编译

**下一步**：
- 了解如何编译各个分区，请阅读 [分区编译流程](02_Partition_Build_Process.md)
- 了解编译配置选项，请阅读 [编译配置和选项](04_Build_Configuration_And_Options.md)
