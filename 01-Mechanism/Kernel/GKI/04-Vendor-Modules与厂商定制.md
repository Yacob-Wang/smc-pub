# Vendor Modules 与厂商定制

## 学习目标

- 理解 Vendor Modules 的作用和限制
- 掌握厂商如何通过 Vendor Modules 进行定制
- 了解 Vendor Modules 的加载时机
- 理解 Vendor Modules 与 GKI Modules 的区别
- 掌握厂商模块开发规范

## 背景介绍

Vendor Modules 是 GKI 架构中厂商定制的核心，允许厂商在不修改 Generic Kernel 的情况下，实现设备特定的功能。理解 Vendor Modules 的机制，有助于理解 GKI 架构如何平衡统一性和灵活性。

## 核心概念

### Vendor Modules 的定义

**Vendor Modules** 是设备厂商开发的特定功能模块，具有以下特点：

1. **设备特定**
   - 针对特定硬件设计
   - 实现厂商定制功能
   - 由厂商开发和维护

2. **通过模块加载**
   - 以内核模块形式存在
   - 动态加载到系统中
   - 可以独立更新

3. **受 KMI 限制**
   - 只能使用 KMI 定义的接口
   - 不能修改 Generic Kernel
   - 必须遵循兼容性要求

### Vendor Modules 的作用

#### 1. 硬件驱动

**作用**：实现设备特定的硬件驱动

**示例**：
- 摄像头驱动
- 传感器驱动
- 显示驱动
- 音频驱动

#### 2. 厂商定制功能

**作用**：实现厂商特定的功能和优化

**示例**：
- 性能优化
- 功耗管理
- 安全特性
- 调试功能

#### 3. 扩展内核功能

**作用**：在不修改 Generic Kernel 的情况下扩展功能

**限制**：
- 只能使用 KMI 接口
- 不能访问未导出的符号
- 必须遵循接口规范

## Vendor Modules 与 GKI Modules 的区别

### 对比表格

| 特性 | GKI Modules | Vendor Modules |
|------|------------|----------------|
| 维护者 | Google | 设备厂商 |
| 适用范围 | 所有 GKI 设备 | 特定设备 |
| 功能 | 通用功能 | 设备特定功能 |
| 加载位置 | System 分区 | Vendor 分区 |
| 更新方式 | 系统更新 | 厂商 OTA |
| 接口限制 | KMI 接口 | KMI 接口 |

### 关键区别

#### 1. 维护者不同

- **GKI Modules**：由 Google 维护，所有设备共享
- **Vendor Modules**：由厂商维护，设备特定

#### 2. 功能范围不同

- **GKI Modules**：提供通用功能（如 zram）
- **Vendor Modules**：提供设备特定功能（如硬件驱动）

#### 3. 加载位置不同

- **GKI Modules**：通常位于 `/system/lib/modules/`
- **Vendor Modules**：通常位于 `/vendor/lib/modules/`

## Vendor Modules 的加载时机

### 1. 系统启动时加载

**时机**：Android 系统启动过程中

**过程**：
1. **Boot 阶段**：内核启动后
2. **Init 进程**：由 init 进程负责
3. **加载顺序**：按照依赖关系加载

**特点**：
- 自动加载
- 系统管理
- 保证加载顺序

### 2. 运行时加载

**时机**：系统运行过程中

**场景**：
- 热插拔设备
- 动态功能启用
- 按需加载

**特点**：
- 动态加载
- 可以卸载
- 灵活管理

### 3. 延迟加载

**时机**：系统启动后延迟加载

**目的**：
- 加快启动速度
- 减少启动时内存占用
- 按需加载

## 厂商如何通过 Vendor Modules 进行定制

### 1. 硬件驱动开发

**步骤**：

1. **识别硬件需求**
   - 分析硬件特性
   - 确定驱动需求
   - 设计驱动架构

2. **使用 KMI 接口**
   - 查看 KMI 符号列表
   - 使用导出的接口
   - 遵循接口规范

3. **实现驱动功能**
   - 实现硬件初始化
   - 实现设备操作
   - 实现中断处理

4. **编译为模块**
   - 编写 Makefile
   - 编译为 .ko 文件
   - 签名和验证

### 2. 功能扩展

**方式**：

1. **扩展现有功能**
   - 基于 Generic Kernel 的功能
   - 添加厂商特定优化
   - 提供额外特性

2. **实现新功能**
   - 实现厂商特定功能
   - 不修改 Generic Kernel
   - 通过模块提供

### 3. 性能优化

**方法**：

1. **算法优化**
   - 优化特定算法
   - 针对硬件优化
   - 提高性能

2. **资源管理**
   - 优化资源使用
   - 提高效率
   - 降低功耗

## Vendor Modules 的开发规范

### 1. KMI 接口使用

#### 只能使用 KMI 导出的符号

**正确做法**：
```c
// 使用 KMI 导出的函数
void *ptr = kmalloc(size, GFP_KERNEL);
kfree(ptr);
```

**错误做法**：
```c
// 不能使用未导出的内部函数
// __kmalloc() 是内部函数，不能直接使用
```

#### 检查符号是否在 KMI 中

**方法**：
```powershell
# 查看 KMI 符号列表
cd ../common
cat android/abi_gki_aarch64 | grep "kmalloc"
```

### 2. 模块签名

**要求**：
- 模块必须签名
- 使用厂商证书
- 验证模块完整性

**目的**：
- 保证模块安全
- 防止恶意模块
- 验证模块来源

### 3. 版本兼容性

**要求**：
- 与 Generic Kernel 版本兼容
- 遵循 KMI 版本规范
- 测试兼容性

**检查**：
```bash
# 检查模块版本
modinfo vendor_module.ko

# 检查符号版本
nm vendor_module.ko | grep "U "
```

### 4. 依赖管理

**要求**：
- 明确声明模块依赖
- 处理依赖关系
- 保证加载顺序

**示例**：
```c
// 在模块中声明依赖
MODULE_DEPENDS("other_module");
```

## 源码分析

### 查看 KMI 符号列表

```powershell
# 查看完整的 KMI 符号列表
cd ../common
cat android/abi_gki_aarch64

# 搜索特定符号
cat android/abi_gki_aarch64 | grep -i "memory\|alloc"
```

### 分析模块开发示例

虽然 Vendor Modules 由厂商开发，但我们可以查看 GKI Modules 作为参考：

```powershell
# 查看 zram 模块的实现
cd ../common
cat drivers/block/zram/zram_drv.c | head -100
```

### 理解模块接口使用

```powershell
# 查看模块如何使用 KMI 接口
cd ../common
grep -r "kmalloc\|kfree" drivers/block/zram/
```

## 实际应用

### 在设备上查看 Vendor Modules

```bash
# 查看已加载的厂商模块
lsmod | grep -v "zram\|zsmalloc"

# 查看模块位置
ls -l /vendor/lib/modules/

# 查看模块信息
modinfo vendor_module.ko
```

### 分析模块加载问题

如果遇到 Vendor Modules 加载问题：

1. **检查模块文件**
   ```bash
   ls -l /vendor/lib/modules/*.ko
   ```

2. **查看加载日志**
   ```bash
   dmesg | grep -i "module\|vendor"
   ```

3. **验证符号兼容性**
   ```bash
   # 检查未解析的符号
   dmesg | grep "Unknown symbol"
   ```

### 调试模块问题

```bash
# 查看模块加载状态
cat /proc/modules

# 查看模块参数
cat /sys/module/vendor_module/parameters/*

# 查看模块使用情况
cat /proc/modules | grep vendor_module
```

## 与你的性能问题的关联

Vendor Modules 可能影响性能：

1. **模块加载开销**：启动时加载大量模块需要时间
2. **符号解析开销**：模块加载时的符号解析
3. **模块间交互**：模块间的交互可能影响性能
4. **兼容性问题**：模块与 Generic Kernel 的兼容性问题

在你的升级问题中：
- Vendor Modules 可能与新版本 Generic Kernel 存在兼容性问题
- 模块加载机制的变化可能影响性能
- 符号解析的变化可能影响模块行为

## 总结

### 核心要点

1. **Vendor Modules 是厂商定制的核心**：允许厂商在不修改 Generic Kernel 的情况下实现定制
2. **受 KMI 限制**：只能使用 KMI 定义的接口
3. **设备特定**：针对特定硬件和需求设计
4. **模块化设计**：可以动态加载和更新

### 关键特性

- **灵活性**：允许厂商定制功能
- **限制性**：受 KMI 接口限制
- **兼容性**：必须与 Generic Kernel 兼容
- **可更新性**：可以独立更新

### 开发要点

- 只能使用 KMI 导出的符号
- 必须遵循模块开发规范
- 需要处理版本兼容性
- 需要管理模块依赖

### 后续学习

- [KMI 详解](05-KMI-Kernel-Module-Interface详解.md) - 深入理解 KMI 接口
- [GKI 模块加载机制](07-GKI模块加载机制.md) - 详细学习加载机制
- [GKI 升级与兼容性](09-GKI升级与兼容性.md) - 理解升级兼容性

## 参考资料

- [KMI 符号列表](../common/android/abi_gki_aarch64)
- [GKI 模块开发指南](https://source.android.com/docs/core/architecture/kernel/generic-kernel-image)
- [Linux 内核模块开发](https://www.kernel.org/doc/html/latest/kernel-hacking/hacking.html)

## 更新记录

- 2024-01-21：初始创建，包含 Vendor Modules 详解
