# Android 根目录结构详解

## 学习目标

- 理解根目录 `/` 的组成和来源
- 掌握来自 Ramdisk 的目录
- 理解分区挂载点目录
- 了解虚拟文件系统目录
- 理解其他重要目录的作用
- 掌握 System-as-root 下的特殊处理

## 背景介绍

Android 设备的根目录 `/` 是一个复杂的结构，包含来自不同来源的内容：Ramdisk、分区挂载点、虚拟文件系统等。理解根目录结构，对于理解 Android 文件系统、调试系统问题、进行系统定制都至关重要。

## 核心概念

### 根目录的组成

#### 来源分类

**1. 来自 Ramdisk**
- `/init` - Init 进程
- `/sbin` - 系统工具
- `/etc` - 配置文件

**2. 来自分区挂载**
- `/system` - System 分区
- `/vendor` - Vendor 分区
- `/data` - Userdata 分区
- 等等

**3. 虚拟文件系统**
- `/proc` - 进程信息
- `/sys` - 内核对象
- `/dev` - 设备文件

**4. 运行时创建**
- `/mnt` - 挂载点
- `/storage` - 存储
- `/acct` - 进程统计

### 来自 Ramdisk 的目录

#### /init

**作用**：Init 进程可执行文件

**特点**：
- 第一个用户空间进程
- PID 1
- 负责系统初始化

**位置**：
- Ramdisk 中（传统方式）
- System 分区中（System-as-root）

#### /sbin

**作用**：系统工具目录

**内容**：
- `adbd` - ADB 守护进程
- `ueventd` - 设备管理
- 其他系统工具

**特点**：
- 早期启动工具
- 系统级工具

#### /etc

**作用**：配置文件目录

**内容**：
- `init.rc` - Init 脚本
- `fstab.*` - 文件系统表
- 其他配置文件

**注意**：
- Ramdisk 中的 `/etc` 是早期配置
- 分区挂载后可能有其他 `/etc`

### 分区挂载点目录

#### /system

**作用**：System 分区挂载点

**内容**：
- Android 框架代码
- 系统服务
- 系统应用
- 系统库

**特点**：
- 只读（正常运行时）
- System-as-root 下作为根
- 符号链接 `/system -> /` 保持兼容

**查看**：
```bash
ls -la /system
```

#### /vendor

**作用**：Vendor 分区挂载点

**内容**：
- HAL 实现
- 厂商驱动
- 厂商库
- 厂商应用

**特点**：
- 只读（正常运行时）
- 厂商维护
- Project Treble 后与 system 分离

#### /product

**作用**：Product 分区挂载点（Android 10+）

**内容**：
- 产品特定应用
- 产品特定配置
- 产品特定资源

**特点**：
- 只读
- 产品特定内容

#### /system_ext

**作用**：System_ext 分区挂载点（Android 10+）

**内容**：
- 系统扩展应用
- 系统扩展库
- OEM 特定的系统扩展

**特点**：
- 只读
- 系统扩展内容

#### /odm

**作用**：ODM 分区挂载点（Android 10+）

**内容**：
- ODM 特定的 HAL
- ODM 特定的驱动
- ODM 特定的配置

**特点**：
- 只读
- ODM 特定内容

#### /data

**作用**：Userdata 分区挂载点

**内容**：
- 用户安装的应用
- 用户数据
- 应用数据
- 媒体文件

**特点**：
- 可读写
- 用户数据主要存储
- 格式化会清除所有数据

**查看**：
```bash
ls -la /data
# 需要 root 权限
```

#### /cache

**作用**：Cache 分区挂载点

**内容**：
- OTA 更新包
- 临时文件
- 缓存数据

**特点**：
- 可读写
- 可以安全清除
- 某些设备可能不使用

### 虚拟文件系统目录

#### /proc

**作用**：进程和系统信息

**内容**：
- `/proc/pid/` - 进程信息
- `/proc/cpuinfo` - CPU 信息
- `/proc/meminfo` - 内存信息
- `/proc/mounts` - 挂载信息
- `/proc/version` - 内核版本

**特点**：
- 虚拟文件系统
- 动态生成
- 只读（大部分）

**常用文件**：
```bash
# 查看 CPU 信息
cat /proc/cpuinfo

# 查看内存信息
cat /proc/meminfo

# 查看挂载信息
cat /proc/mounts
```

#### /sys

**作用**：内核对象和配置

**内容**：
- `/sys/class/` - 设备类
- `/sys/devices/` - 设备
- `/sys/kernel/` - 内核配置
- `/sys/power/` - 电源管理

**特点**：
- 虚拟文件系统
- 内核对象接口
- 可读写（部分）

**常用操作**：
```bash
# 查看设备
ls /sys/class/

# 查看内核配置
cat /sys/kernel/*
```

#### /dev

**作用**：设备文件

**内容**：
- `/dev/block/` - 块设备
- `/dev/char/` - 字符设备
- `/dev/null` - 空设备
- `/dev/zero` - 零设备

**特点**：
- 虚拟文件系统
- 设备节点
- 由 ueventd 创建

**查看**：
```bash
# 查看块设备
ls -la /dev/block/

# 查看分区
ls -la /dev/block/by-name/
```

### 其他重要目录

#### /mnt

**作用**：挂载点目录

**内容**：
- 临时挂载点
- 外部存储挂载点

**特点**：
- 运行时创建
- 临时使用

#### /storage

**作用**：存储目录

**内容**：
- `/storage/emulated/` - 模拟存储
- `/storage/self/` - 当前用户存储

**特点**：
- 多用户支持
- 存储访问

#### /acct

**作用**：进程统计

**内容**：
- 进程统计信息

**特点**：
- 进程监控
- 资源统计

#### /sys/fs

**作用**：文件系统信息

**内容**：
- `/sys/fs/cgroup/` - Cgroup
- `/sys/fs/selinux/` - SELinux

**特点**：
- 文件系统相关
- 系统配置

### System-as-root 下的特殊处理

#### 符号链接

**兼容性链接**：
```bash
/system -> /
/vendor -> /vendor
/product -> /product
```

**目的**：
- 保持应用和脚本兼容性
- 允许代码使用 `/system` 路径

**查看**：
```bash
ls -la / | grep "^l"
```

#### 根目录内容

**System-as-root 下**：
- `/` 直接是 System 分区内容
- Ramdisk 内容合并到 System 分区
- 简化启动流程

## 实际应用

### 查看根目录结构

```bash
# 查看根目录
ls -la /

# 查看挂载信息
mount | head -20

# 查看分区挂载
df -h
```

### 分析目录来源

```bash
# 查看符号链接
ls -la / | grep "^l"

# 查看挂载点
mount | grep -E "system|vendor|data"

# 查看虚拟文件系统
ls -la /proc /sys /dev
```

### 调试系统问题

```bash
# 查看 Init 进程
ls -la /init

# 查看配置文件
cat /etc/init.rc | head -50

# 查看系统信息
cat /proc/version
cat /proc/cpuinfo
```

## 总结

### 核心要点

1. **根目录包含多种来源**：Ramdisk、分区挂载、虚拟文件系统
2. **分区挂载点**：system, vendor, data 等
3. **虚拟文件系统**：proc, sys, dev
4. **System-as-root 下**：System 分区作为根，使用符号链接保持兼容

### 关键目录

- **/system**：系统框架
- **/vendor**：厂商实现
- **/data**：用户数据
- **/proc**：进程信息
- **/sys**：内核对象

### 后续学习

- [文件系统类型与挂载机制](11-文件系统类型与挂载机制.md) - 理解文件系统
- [分区与挂载点映射关系](06-分区与挂载点映射关系.md) - 理解挂载机制
- [Init进程与系统服务启动](09-Init进程与系统服务启动.md) - 理解启动过程
- [Android存储架构：磁盘分区与文件系统基础](15-Android存储架构：磁盘分区与文件系统基础.md) - 理解存储架构基础

## 参考资料

- [Android 文件系统](https://source.android.com/docs/core/architecture/partitions)
- [System-as-root](https://source.android.com/docs/core/architecture/partitions/system-as-root)
- [Linux 文件系统](https://www.kernel.org/doc/html/latest/filesystems/)

## 更新记录

- 2024-01-22：初始创建，包含 Android 根目录结构详解
