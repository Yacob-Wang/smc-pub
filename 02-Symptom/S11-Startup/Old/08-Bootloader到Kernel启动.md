# Bootloader 到 Kernel 启动

## 学习目标

- 深入理解 Bootloader 的职责和工作流程
- 掌握 Kernel 启动的详细过程
- 理解 Ramdisk 的作用
- 了解从 Kernel 到 Init 的切换过程
- 掌握设备树（Device Tree）的作用

## 背景介绍

从 Bootloader 到 Kernel 启动是 Android 设备启动的最早阶段。理解这个过程对于理解整个启动流程、调试启动问题、优化启动时间都至关重要。这个过程涉及硬件初始化、镜像加载、验证启动等多个关键步骤。

## 核心概念

### Bootloader 阶段详解

#### Bootloader 的职责

**1. 硬件初始化**

**CPU 初始化**：
- 设置 CPU 频率
- 初始化缓存
- 设置异常向量表

**内存初始化**：
- 检测内存大小
- 初始化内存控制器
- 设置内存映射

**存储设备初始化**：
- 初始化 eMMC/UFS
- 读取分区表
- 准备读取分区

**外设初始化**：
- 串口初始化（用于调试）
- 时钟初始化
- GPIO 初始化

**2. 加载启动镜像**

**读取 boot 分区**：
- 从存储设备读取 boot 分区
- 解析 boot.img 格式
- 验证镜像完整性

**加载到内存**：
- 加载内核到指定地址
- 加载 ramdisk 到指定地址
- 加载设备树（DTB）到指定地址

**3. 验证启动（AVB）**

**验证流程**：
- 读取 vbmeta 分区
- 验证 boot 分区签名
- 检查哈希值
- 验证启动链

**验证失败处理**：
- 显示警告信息
- 可能阻止启动（严格模式）
- 或允许启动但标记为未验证（警告模式）

**4. 设置启动参数**

**内核命令行**：
- 从 boot.img header 读取
- 设置 root 设备
- 设置 init 路径
- 设置其他内核参数

**设备树**：
- 传递设备树地址
- 内核会解析设备树

**5. 跳转到内核**

**跳转过程**：
- 设置 CPU 状态
- 禁用中断
- 跳转到内核入口地址
- 传递启动参数

#### Bootloader 类型

**U-Boot**：
- 开源 Bootloader
- 广泛使用
- 功能强大

**Little Kernel (LK)**：
- 高通使用
- 轻量级
- 快速启动

**ABL (Android Bootloader)**：
- 现代 Android 使用
- 支持 AVB
- 支持 A/B 分区

**厂商定制**：
- 各厂商可能有定制版本
- 添加特定功能

### Kernel 启动阶段详解

#### 内核入口（ARM64）

**位置**：`arch/arm64/kernel/head.S`

**关键步骤**：

**1. 早期汇编初始化**
```assembly
ENTRY(_text)
    // 设置异常向量表
    adr x0, vectors
    msr vbar_el1, x0
    
    // 初始化 MMU
    bl __enable_mmu
    
    // 跳转到 C 代码
    bl start_kernel
END(_text)
```

**2. 页表设置**
- 设置初始页表
- 映射内核代码段
- 映射设备内存

**3. MMU 初始化**
- 启用 MMU
- 切换到虚拟地址
- 设置内存属性

#### 内核早期初始化

**start_kernel() 函数**（`init/main.c`）：

**关键初始化**：
1. **锁初始化**：`lockdep_init()`
2. **设置架构相关**：`setup_arch()`
3. **页分配器初始化**：`mm_init()`
4. **调度器初始化**：`sched_init()`
5. **中断初始化**：`init_IRQ()`
6. **时钟初始化**：`time_init()`
7. **控制台初始化**：`console_init()`

#### 设备树解析

**设备树作用**：
- 描述硬件配置
- 替代硬编码配置
- 支持不同硬件变体

**解析过程**：
1. Bootloader 传递 DTB 地址
2. 内核解析 DTB
3. 创建设备树节点
4. 初始化设备驱动

**设备树内容**：
- CPU 信息
- 内存信息
- 设备信息
- 中断信息
- 时钟信息

#### Ramdisk 处理

**Ramdisk 作用**：
- 包含初始根文件系统
- 包含 init 进程
- 包含早期启动文件

**加载过程**：
1. Bootloader 加载 ramdisk 到内存
2. 内核解压 ramdisk（如果压缩）
3. 挂载为根文件系统（传统方式）
4. 或合并到 system 分区（System-as-root）

**Ramdisk 内容**：
```
ramdisk/
├── init              # Init 进程
├── sbin/             # 系统工具
│   └── ...
├── etc/              # 配置文件
│   └── ...
└── ...
```

#### 启动 Init 进程

**过程**：
1. 内核完成早期初始化
2. 挂载根文件系统（ramdisk 或 system）
3. 执行 `/init` 程序
4. 切换到用户空间

**关键代码**（`init/main.c`）：
```c
if (!ramdisk_execute_command)
    ramdisk_execute_command = "/init";

run_init_process(ramdisk_execute_command);
```

### 从 Kernel 到 Init 的切换

#### 切换过程

**1. 内核准备**
- 完成所有内核初始化
- 准备好用户空间环境
- 设置进程 0（idle 进程）

**2. 挂载根文件系统**
- 挂载 ramdisk（传统）
- 或挂载 system 分区（System-as-root）

**3. 执行 Init**
- 内核执行 `/init`
- 创建第一个用户空间进程（PID 1）
- 切换到用户模式

**4. Init 接管**
- Init 进程开始执行
- 解析 init.rc
- 启动系统服务

## 实际应用

### 查看 Bootloader 日志

**串口输出**：
- Bootloader 通常输出到串口
- 可以看到硬件初始化信息
- 可以看到镜像加载信息

**UART 连接**：
- 需要硬件连接串口
- 使用串口工具查看

### 查看 Kernel 启动日志

```bash
# 查看内核日志
dmesg

# 查看启动时间
dmesg | grep -i "boot"

# 查看设备树信息
dmesg | grep -i "dtb"
```

### 分析启动问题

**常见问题**：
1. **Bootloader 无法加载内核**：检查 boot 分区
2. **AVB 验证失败**：检查签名
3. **内核崩溃**：查看 dmesg
4. **Init 无法启动**：检查 ramdisk

**调试方法**：
```bash
# 查看完整启动日志
dmesg > boot.log

# 分析启动时间
dmesg | grep -E "\[.*\]"
```

## 总结

### 核心要点

1. **Bootloader 负责硬件初始化和加载内核**
2. **Kernel 启动包括早期初始化和设备树解析**
3. **Ramdisk 提供初始根文件系统**
4. **从 Kernel 到 Init 的切换是启动的关键转折点**

### 关键步骤

- **Bootloader**：硬件初始化 → 加载镜像 → AVB 验证 → 跳转内核
- **Kernel**：入口 → 早期初始化 → 设备树解析 → 启动 Init
- **切换**：内核完成 → 挂载根文件系统 → 执行 Init

### 后续学习

- [Init进程与系统服务启动](09-Init进程与系统服务启动.md) - 理解 Init 启动
- [Android验证启动机制](12-Android验证启动机制.md) - 理解 AVB
- [ARM64系统调用机制](../syscalls/02-ARM64系统调用机制.md) - 理解内核机制

## 参考资料

- [ARM64 启动文档](../common/Documentation/arm64/booting.rst)
- [Boot Image 格式](05-分区镜像文件格式详解.md)
- [Android 启动流程](07-Android启动流程总览.md)

## 更新记录

- 2024-01-22：初始创建，包含 Bootloader 到 Kernel 启动详解
