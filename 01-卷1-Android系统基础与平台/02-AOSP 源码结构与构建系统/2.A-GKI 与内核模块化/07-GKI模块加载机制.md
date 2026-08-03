# GKI 模块加载机制

## 学习目标

- 理解模块加载的时机和顺序
- 掌握 System DLKM 的加载机制
- 了解 Vendor Modules 的加载机制
- 理解模块依赖关系管理
- 掌握模块符号解析过程

## 背景介绍

模块加载机制是 GKI 架构的关键部分，理解模块如何加载、何时加载、如何解析符号，有助于理解 GKI 架构的模块化设计。

## 核心概念

### 模块加载的基本流程

#### 1. 模块发现

**位置**：系统在以下位置查找模块文件

- `/vendor/lib/modules/` - Vendor 模块
- `/system/lib/modules/` - System 模块（GKI Modules）
- `/apex/*/lib/modules/` - APEX 模块

**过程**：
1. 系统扫描模块目录
2. 识别模块文件（.ko 文件）
3. 验证模块签名
4. 检查模块兼容性

#### 2. 依赖解析

**过程**：
1. 读取模块的依赖信息
2. 查找依赖模块
3. 递归解析依赖
4. 构建依赖树

**示例**：
```
zram.ko 依赖 zsmalloc.ko
加载顺序：先加载 zsmalloc.ko，再加载 zram.ko
```

#### 3. 符号解析

**过程**：
1. 读取模块需要的符号
2. 在内核的 KMI 中查找符号
3. 验证符号版本
4. 解析符号地址

**验证**：
- 符号必须在 KMI 列表中
- 符号版本必须兼容
- 符号类型必须匹配

#### 4. 模块加载

**过程**：
1. 分配模块内存
2. 加载模块代码
3. 解析符号引用
4. 执行模块初始化
5. 注册模块功能

## System DLKM 的加载机制

### 加载时机

#### 1. 系统启动时

**时机**：Android 系统启动过程中

**阶段**：
1. **Kernel 启动**：内核启动完成
2. **Init 进程**：init 进程启动
3. **模块加载**：init 进程加载 System DLKM

**特点**：
- 自动加载
- 系统管理
- 保证加载顺序

#### 2. 加载顺序

**顺序**：
1. 先加载依赖模块
2. 再加载依赖的模块
3. 按照依赖关系排序

**示例**：
```
zsmalloc.ko (无依赖)
    ↓
zram.ko (依赖 zsmalloc)
```

### 加载配置

**配置位置**：`../common/build.config.gki.aarch64`

```bash
BUILD_SYSTEM_DLKM=1
MODULES_LIST=${ROOT_DIR}/${KERNEL_DIR}/android/gki_system_dlkm_modules
MODULES_ORDER=android/gki_aarch64_modules
```

**配置说明**：
- `BUILD_SYSTEM_DLKM=1`：启用 System DLKM 构建
- `MODULES_LIST`：指定模块列表文件
- `MODULES_ORDER`：指定模块加载顺序

### 加载过程

#### 1. 模块文件准备

**位置**：模块文件被放置在系统分区

**路径**：`/system/lib/modules/`

**特点**：
- 系统分区，只读
- 由系统更新管理
- 与 Generic Kernel 版本匹配

#### 2. Init 进程加载

**过程**：
1. Init 进程读取模块列表
2. 按照顺序加载模块
3. 处理模块依赖
4. 验证模块兼容性

#### 3. 模块初始化

**过程**：
1. 调用模块的 `module_init()` 函数
2. 初始化模块功能
3. 注册设备或功能
4. 完成加载

## Vendor Modules 的加载机制

### 加载时机

#### 1. 系统启动时

**时机**：系统启动过程中

**特点**：
- 由厂商的 init 脚本控制
- 可以自定义加载顺序
- 支持条件加载

#### 2. 运行时加载

**时机**：系统运行过程中

**场景**：
- 热插拔设备
- 动态功能启用
- 按需加载

### 加载位置

**位置**：`/vendor/lib/modules/`

**特点**：
- Vendor 分区，可更新
- 由厂商 OTA 管理
- 设备特定

### 加载过程

#### 1. 模块发现

**过程**：
1. 扫描 `/vendor/lib/modules/` 目录
2. 识别模块文件
3. 验证模块签名
4. 检查模块兼容性

#### 2. 依赖处理

**过程**：
1. 检查模块依赖
2. 查找依赖模块（可能在 vendor 或 system 分区）
3. 加载依赖模块
4. 验证依赖关系

#### 3. 符号解析

**过程**：
1. 读取模块需要的符号
2. 在 Generic Kernel 的 KMI 中查找
3. 验证符号版本
4. 解析符号地址

**限制**：
- 只能使用 KMI 定义的符号
- 符号版本必须兼容
- 不能使用未导出的符号

## 模块依赖关系管理

### 依赖声明

#### 1. 模块依赖

**声明方式**：
```c
// 在模块代码中声明依赖
MODULE_DEPENDS("other_module");
```

**作用**：
- 明确模块依赖关系
- 保证加载顺序
- 处理依赖问题

#### 2. 符号依赖

**方式**：模块通过符号引用表达依赖

**示例**：
```c
// 模块中使用外部符号
extern void kmalloc(size_t size, gfp_t flags);
```

**处理**：
- 加载时解析符号
- 验证符号存在
- 检查符号版本

### 依赖解析算法

#### 1. 拓扑排序

**方法**：使用拓扑排序确定加载顺序

**过程**：
1. 构建依赖图
2. 找到无依赖的模块
3. 加载这些模块
4. 更新依赖图
5. 重复直到所有模块加载

#### 2. 循环依赖检测

**检测**：检测模块间的循环依赖

**处理**：
- 报告错误
- 拒绝加载
- 要求修复依赖关系

## 模块符号解析过程

### 符号解析步骤

#### 1. 读取符号需求

**过程**：
1. 读取模块的符号表
2. 识别未定义的符号（U 类型）
3. 列出所有需要的符号

**查看**：
```bash
# 查看模块需要的符号
nm vendor_module.ko | grep " U "
```

#### 2. 在 KMI 中查找

**过程**：
1. 在内核的 KMI 符号列表中查找
2. 验证符号存在
3. 检查符号版本

**验证**：
```powershell
# 验证符号是否在 KMI 中
cd ../common
cat android/abi_gki_aarch64 | grep "symbol_name"
```

#### 3. 解析符号地址

**过程**：
1. 在内核符号表中查找符号地址
2. 验证符号类型
3. 解析符号引用

**查看**：
```bash
# 查看内核导出的符号
cat /proc/kallsyms | grep "symbol_name"
```

#### 4. 绑定符号

**过程**：
1. 将模块的符号引用绑定到内核符号
2. 更新模块的符号表
3. 完成符号解析

### 符号解析失败

#### 常见错误

1. **Unknown symbol**
   ```
   Unknown symbol in module
   ```

   **原因**：
   - 符号不在 KMI 中
   - 符号版本不匹配
   - 模块不兼容

2. **Symbol version mismatch**
   ```
   Symbol version mismatch
   ```

   **原因**：
   - 符号版本不兼容
   - 模块与内核版本不匹配

#### 解决方法

1. **检查符号列表**
   ```bash
   # 检查符号是否在 KMI 中
   cat /proc/kallsyms | grep "symbol_name"
   ```

2. **验证模块版本**
   ```bash
   # 检查模块版本要求
   modinfo vendor_module.ko | grep vermagic
   ```

3. **检查内核版本**
   ```bash
   # 查看内核版本
   uname -r
   ```

## 源码分析

### 查看模块加载配置

```powershell
# 查看 System DLKM 配置
cd ../common
grep -A 5 "BUILD_SYSTEM_DLKM" build.config.gki.aarch64

# 查看模块列表
cat android/gki_system_dlkm_modules
```

### 分析模块依赖

```powershell
# 查看 zram 模块的依赖
cd ../common
grep -r "zsmalloc" drivers/block/zram/
```

### 查看模块符号

```powershell
# 查看模块导出的符号（如果已编译）
# 需要先编译模块
```

## 实际应用

### 在设备上查看模块加载

```bash
# 查看已加载的模块
lsmod

# 查看模块依赖关系
cat /proc/modules

# 查看模块加载日志
dmesg | grep -i "module\|loading"
```

### 分析模块加载问题

如果遇到模块加载问题：

1. **查看加载日志**
   ```bash
   dmesg | grep -i "module\|unknown symbol"
   ```

2. **检查模块文件**
   ```bash
   ls -l /vendor/lib/modules/
   ls -l /system/lib/modules/
   ```

3. **验证符号兼容性**
   ```bash
   # 查看未解析的符号
   dmesg | grep "Unknown symbol"
   ```

### 调试模块加载

```bash
# 查看模块信息
modinfo vendor_module.ko

# 查看模块参数
cat /sys/module/vendor_module/parameters/*

# 查看模块使用情况
cat /proc/modules | grep vendor_module
```

## 与你的性能问题的关联

模块加载机制可能影响性能：

1. **加载时间**：启动时加载大量模块需要时间
2. **符号解析开销**：符号解析需要时间
3. **模块初始化开销**：模块初始化可能影响性能
4. **依赖处理开销**：依赖关系处理需要时间

在你的升级问题中：
- 模块加载顺序的变化可能影响性能
- 符号解析的变化可能影响加载时间
- 模块初始化的变化可能影响系统性能

## 总结

### 核心要点

1. **模块加载是系统化的过程**：包括发现、依赖解析、符号解析、加载
2. **System DLKM 自动加载**：系统启动时自动加载
3. **Vendor Modules 灵活加载**：可以启动时加载或运行时加载
4. **依赖关系管理**：通过拓扑排序确定加载顺序

### 关键特性

- **自动化**：系统自动管理模块加载
- **依赖处理**：自动处理模块依赖
- **符号解析**：自动解析符号引用
- **兼容性检查**：加载时检查兼容性

### 加载流程

1. **模块发现** → 2. **依赖解析** → 3. **符号解析** → 4. **模块加载** → 5. **初始化**

### 后续学习

- [GKI 中的内存管理特殊性](08-GKI中的内存管理特殊性.md) - 了解模块加载对内存的影响
- [GKI 升级与兼容性](09-GKI升级与兼容性.md) - 理解升级对模块加载的影响
- [GKI 实战案例分析](10-GKI实战案例分析.md) - 实际案例分析

## 参考资料

- [System DLKM 列表](../common/android/gki_system_dlkm_modules)
- [GKI 模块列表](../common/android/gki_aarch64_modules)
- [Linux 内核模块文档](https://www.kernel.org/doc/html/latest/kernel-hacking/modules.html)

## 更新记录

- 2024-01-21：初始创建，包含 GKI 模块加载机制详解
