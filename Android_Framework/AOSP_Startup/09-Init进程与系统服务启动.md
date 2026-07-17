# Init 进程与系统服务启动

## 学习目标

- 理解 Init 进程的作用和重要性
- 掌握 init.rc 脚本的语法和结构
- 理解 Service 定义和启动机制
- 了解触发器（triggers）的使用
- 理解属性系统（Property）
- 掌握分区挂载过程
- 理解 System-as-root 的实现
- 了解 Zygote 和 System Server 的启动

## 背景介绍

Init 进程是 Android 系统中第一个用户空间进程（PID 1），负责系统初始化、服务管理、属性管理等关键功能。理解 Init 进程的工作机制，对于理解 Android 启动流程、调试系统问题、定制系统行为都至关重要。

## 核心概念

### Init 进程概述

#### Init 进程的作用

**1. 系统初始化**
- 解析 init.rc 脚本
- 挂载文件系统
- 初始化系统环境

**2. 服务管理**
- 启动系统服务
- 监控服务状态
- 重启崩溃的服务

**3. 属性管理**
- 管理系统属性
- 处理属性变化
- 触发属性相关动作

**4. 信号处理**
- 处理子进程退出
- 处理系统信号

#### Init 进程源码位置

**AOSP 源码**：`system/core/init/`

**关键文件**：
- `init.cpp` - 主入口
- `init_parser.cpp` - 解析器
- `service.cpp` - 服务管理
- `property_service.cpp` - 属性服务

### init.rc 脚本

#### 脚本位置

**多个位置**：
- `system/core/rootdir/init.rc` - 主脚本
- `device/<vendor>/<device>/init.*.rc` - 设备特定
- `vendor/etc/init/*.rc` - Vendor 脚本
- `system/etc/init/*.rc` - System 脚本

#### 脚本语法

**基本结构**：
```text
on <trigger>
    <command>
    <command>
    ...
```

**Action（动作）**：
```text
on early-init
    start ueventd
    ...
```

**Service（服务）**：
```text
service <name> <path> [ <argument> ]*
    <option>
    <option>
    ...
```

#### 常用命令

**1. mount**
```text
mount <type> <device> <dir> [ <flag> ]*
```
挂载文件系统

**2. mkdir**
```text
mkdir <path> [mode] [owner] [group]
```
创建目录

**3. chmod / chown**
```text
chmod <octal-mode> <path>
chown <owner> <group> <path>
```
修改权限和所有者

**4. start / stop**
```text
start <service>
stop <service>
```
启动/停止服务

**5. setprop**
```text
setprop <name> <value>
```
设置属性

**6. write**
```text
write <path> <string>
```
写入文件

#### Service 定义

**基本格式**：
```text
service <name> <path> [ <argument> ]*
    <option>
    <option>
    ...
```

**常用选项**：
- `user <username>` - 运行用户
- `group <groupname>` - 运行组
- `oneshot` - 只运行一次
- `disabled` - 默认不启动
- `class <name>` - 服务类
- `onrestart` - 重启时执行

**示例**：
```text
service ueventd /system/bin/ueventd
    class core
    critical
    seclabel u:r:ueventd:s0
```

#### 触发器（Triggers）

**内置触发器**：
- `early-init` - 早期初始化
- `init` - 初始化
- `late-init` - 后期初始化
- `early-fs` - 早期文件系统
- `fs` - 文件系统
- `post-fs` - 文件系统后
- `post-fs-data` - 数据分区后
- `property:<name>=<value>` - 属性触发

**示例**：
```text
on property:sys.boot_completed=1
    start my_service
```

### 分区挂载过程

#### 第一阶段挂载（First Stage Mount）

**时机**：Init 进程早期

**目的**：挂载必要的只读分区

**过程**：
1. 读取 fstab 文件
2. 查找 `first_stage_mount` 标志的分区
3. 挂载分区到临时位置
4. System-as-root 下挂载 system 为根

**关键代码**：
```c
// system/core/init/first_stage_mount.cpp
```

#### 第二阶段挂载（Second Stage Mount）

**时机**：Init 进程后期

**目的**：挂载其他分区

**过程**：
1. 读取 fstab 文件
2. 挂载 data, cache 等分区
3. 设置挂载点权限

#### System-as-root 实现

**传统方式**：
```
Ramdisk (/) → 挂载 system/ → 切换根到 system/
```

**System-as-root**：
```
System (/) → 直接作为根
```

**实现**：
- System 分区直接挂载为根
- 创建符号链接 `/system -> /` 保持兼容
- Ramdisk 内容合并到 system 分区

### 属性系统（Property）

#### 属性服务

**作用**：管理系统属性

**属性类型**：
- `ro.*` - 只读属性
- `persist.*` - 持久化属性
- `sys.*` - 系统属性
- `vendor.*` - Vendor 属性

#### 属性操作

**设置属性**：
```bash
setprop <name> <value>
```

**获取属性**：
```bash
getprop <name>
```

**属性触发**：
```text
on property:<name>=<value>
    <command>
```

### Zygote 启动

#### Zygote 进程

**作用**：
- 预加载 Java 类和资源
- 作为应用进程模板
- 通过 fork 创建应用进程

**启动**：
```text
service zygote /system/bin/app_process64 -Xzygote /system/bin --zygote --start-system-server
    class main
    priority -20
    user root
    group root readproc
    socket zygote stream 660 root system
    onrestart write /sys/android_power/request_state wake
    onrestart restart audioserver
    onrestart restart cameraserver
    ...
```

#### Zygote 启动流程

1. Init 启动 Zygote 服务
2. Zygote 预加载类和资源
3. Zygote 启动 System Server
4. Zygote 进入循环，等待 fork 请求

### System Server 启动

#### System Server 进程

**作用**：
- 启动所有系统服务
- 初始化 Android 框架
- 管理应用生命周期

**启动**：
- 由 Zygote fork 创建
- 运行 `SystemServer.main()`
- 启动各种系统服务

#### 系统服务启动顺序

**1. 启动引导服务**：
- ActivityManagerService
- PowerManagerService
- DisplayManagerService
- PackageManagerService
- UserManagerService

**2. 启动核心服务**：
- BatteryService
- UsageStatsService
- WebViewUpdateService

**3. 启动其他服务**：
- WindowManagerService
- InputManagerService
- 等等

## 实际应用

### 查看 Init 进程

```bash
# 查看 Init 进程
ps aux | grep init

# 查看 Init 日志
logcat -b all | grep init
```

### 分析 init.rc

```bash
# 查看主脚本
cat /init.rc

# 查看设备特定脚本
cat /vendor/etc/init/*.rc
```

### 调试服务启动

```bash
# 查看服务状态
getprop | grep service

# 查看服务日志
logcat -b all | grep <service_name>
```

## 总结

### 核心要点

1. **Init 进程是第一个用户空间进程**，负责系统初始化
2. **init.rc 脚本定义启动行为**，包括服务、动作、触发器
3. **分区挂载分两个阶段**，确保正确的挂载顺序
4. **System-as-root 简化启动**，System 分区直接作为根
5. **Zygote 和 System Server 由 Init 启动**，完成应用框架初始化

### 关键概念

- **init.rc**：启动脚本
- **Service**：系统服务
- **Trigger**：触发器
- **Property**：属性系统
- **First Stage Mount**：早期挂载

### 后续学习

- [Android根目录结构详解](10-Android根目录结构详解.md) - 理解文件系统结构
- [分区与挂载点映射关系](06-分区与挂载点映射关系.md) - 理解挂载机制
- [Android启动流程总览](07-Android启动流程总览.md) - 理解完整流程

## 参考资料

- [Init 进程源码](https://source.android.com/docs/core/architecture/init)
- [init.rc 语法](https://source.android.com/docs/core/architecture/init)
- [System-as-root](https://source.android.com/docs/core/architecture/partitions/system-as-root)

## 更新记录

- 2024-01-22：初始创建，包含 Init 进程与系统服务启动详解
