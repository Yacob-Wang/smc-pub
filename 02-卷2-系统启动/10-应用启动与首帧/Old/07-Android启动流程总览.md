# Android 启动流程总览

## 学习目标

- 理解 Android 从开机到系统就绪的完整流程
- 掌握各个启动阶段的关键操作
- 理解 Bootloader、Kernel、Init、Zygote 和 System Server 的作用
- 了解启动流程图和各阶段的依赖关系

## 背景介绍

Android 设备的启动是一个复杂的过程，涉及多个阶段和组件。理解启动流程对于调试启动问题、优化启动时间、理解系统架构都至关重要。从 Android 9.0 开始，System-as-root 机制改变了启动流程，简化了部分步骤。

## 核心概念

### 启动阶段划分

Android 启动可以分为以下几个主要阶段：

```
1. Bootloader 阶段
   ↓
2. Kernel 启动阶段
   ↓
3. Init 进程阶段
   ↓
4. Zygote 和 System Server 阶段
   ↓
5. Launcher 启动
```

### 启动流程图

```
┌─────────────────┐
│   上电/复位      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Bootloader    │
│  - 硬件初始化    │
│  - 加载 boot.img │
│  - AVB 验证      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Kernel 启动   │
│  - 内核解压      │
│  - 设备树解析    │
│  - 早期初始化    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Init 进程      │
│  - 解析 init.rc  │
│  - 挂载分区      │
│  - 启动服务      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Zygote        │
│  - 预加载类      │
│  - 启动应用进程  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  System Server  │
│  - 系统服务      │
│  - 框架初始化    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Launcher      │
│  - 桌面启动      │
└─────────────────┘
```

### 阶段一：Bootloader 阶段

#### Bootloader 的职责

**1. 硬件初始化**
- CPU 初始化
- 内存初始化
- 存储设备初始化
- 基本外设初始化

**2. 加载启动镜像**
- 从存储设备读取 boot 分区
- 解析 boot.img 格式
- 加载内核到内存
- 加载 ramdisk 到内存
- 加载设备树（DTB）

**3. 验证启动（AVB）**
- 验证 boot 分区签名
- 验证 vbmeta
- 检查启动完整性

**4. 启动内核**
- 设置内核启动参数
- 跳转到内核入口

#### Bootloader 类型

**常见 Bootloader**：
- **U-Boot** - 开源 Bootloader
- **Little Kernel (LK)** - 高通使用
- **ABL (Android Bootloader)** - 现代 Android 使用
- **厂商定制 Bootloader**

#### 关键操作

```bash
# Bootloader 通常输出到串口
# 可以看到启动信息
```

### 阶段二：Kernel 启动阶段

#### Kernel 启动流程

**1. 内核入口**
- ARM64: `arch/arm64/kernel/head.S`
- 早期汇编初始化
- 设置页表
- 初始化 MMU

**2. 内核解压**（如果压缩）
- 解压内核镜像
- 设置解压后的内存布局

**3. 设备树解析**
- 解析 DTB 文件
- 初始化设备树节点
- 识别硬件配置

**4. 早期初始化**
- 内存管理初始化
- 中断系统初始化
- 时钟初始化
- 控制台初始化

**5. 启动 Init 进程**
- 从 ramdisk 加载 init
- 切换到用户空间
- 执行 init 进程

#### 关联知识

- 参考 [ARM64系统调用机制](../syscalls/02-ARM64系统调用机制.md)
- 参考 [Bootloader到Kernel启动](08-Bootloader到Kernel启动.md)

### 阶段三：Init 进程阶段

#### Init 进程的作用

**1. 解析 init.rc**
- 解析启动脚本
- 定义服务和动作
- 设置触发器

**2. 挂载分区**
- 第一阶段挂载（first_stage_mount）
- 挂载 system, vendor 等分区
- 第二阶段挂载（second_stage_mount）
- 挂载 data, cache 等分区

**3. 启动服务**
- 启动关键系统服务
- 启动属性服务
- 启动 SELinux

**4. 启动 Zygote**
- 启动 Zygote 进程
- 预加载类和资源

#### Init 进程关键文件

**init.rc 位置**：
- `system/core/rootdir/init.rc` - 主脚本
- `device/<vendor>/<device>/init.*.rc` - 设备特定脚本
- `vendor/etc/init/*.rc` - Vendor 脚本

**参考**：
- [Init进程与系统服务启动](09-Init进程与系统服务启动.md)

### 阶段四：Zygote 和 System Server 阶段

#### Zygote 进程

**作用**：
- 预加载 Java 类和资源
- 作为应用进程的模板
- 通过 fork 创建应用进程

**启动**：
- 由 Init 进程启动
- 运行 Java 代码（ZygoteInit）
- 预加载框架类

#### System Server

**作用**：
- 启动所有系统服务
- 初始化 Android 框架
- 管理应用生命周期

**关键服务**：
- ActivityManagerService
- WindowManagerService
- PackageManagerService
- PowerManagerService
- 等等

**启动顺序**：
1. 启动核心服务
2. 启动其他服务
3. 启动应用服务

### 阶段五：Launcher 启动

#### Launcher 进程

**作用**：
- 显示桌面
- 管理应用图标
- 处理用户交互

**启动**：
- 由 System Server 启动
- 作为第一个应用进程
- 显示主屏幕

## 启动时间分析

### 各阶段耗时

**典型启动时间**（示例）：
- Bootloader: 1-3 秒
- Kernel: 2-5 秒
- Init: 3-8 秒
- Zygote + System Server: 5-15 秒
- Launcher: 2-5 秒

**总启动时间**：15-40 秒（取决于设备）

### 优化启动时间

**方法**：
1. **并行启动服务**：减少串行等待
2. **延迟启动非关键服务**：先启动必要服务
3. **预加载优化**：减少 Zygote 预加载时间
4. **内核优化**：减少内核启动时间

## 启动日志分析

### 查看启动日志

**Kernel 日志**：
```bash
dmesg
```

**Init 日志**：
```bash
logcat -b all | grep init
```

**系统日志**：
```bash
logcat
```

### 关键日志信息

**Bootloader**：
- 硬件初始化信息
- 分区加载信息
- AVB 验证信息

**Kernel**：
- 内核版本信息
- 设备树信息
- 驱动加载信息

**Init**：
- 服务启动信息
- 分区挂载信息
- 属性设置信息

## 实际应用

### 分析启动问题

```bash
# 查看完整启动日志
dmesg > boot.log
logcat -b all > init.log

# 分析启动时间
dmesg | grep -i "boot"
```

### 调试启动流程

```bash
# 查看当前进程
ps aux

# 查看 Init 进程
ps aux | grep init

# 查看 Zygote 进程
ps aux | grep zygote
```

## 总结

### 核心要点

1. **启动分多个阶段**：Bootloader → Kernel → Init → Zygote → System Server → Launcher
2. **每个阶段有特定职责**：硬件初始化、内核启动、系统初始化、应用启动
3. **启动流程可以优化**：并行启动、延迟启动、预加载优化
4. **日志分析很重要**：dmesg、logcat 等工具

### 关键阶段

- **Bootloader**：硬件初始化和加载内核
- **Kernel**：内核启动和设备初始化
- **Init**：系统初始化和服务启动
- **Zygote**：应用进程模板
- **System Server**：系统服务

### 后续学习

- [Bootloader到Kernel启动](08-Bootloader到Kernel启动.md) - 深入理解早期启动
- [Init进程与系统服务启动](09-Init进程与系统服务启动.md) - 深入理解 Init
- [Android根目录结构详解](10-Android根目录结构详解.md) - 理解文件系统结构

## 参考资料

- [Android 启动流程](https://source.android.com/docs/core/architecture/bootloader)
- [Init 进程](https://source.android.com/docs/core/architecture/init)
- [Zygote 进程](https://source.android.com/docs/core/runtime)

## 更新记录

- 2024-01-22：初始创建，包含 Android 启动流程总览
