# GKI Modules 深入解析

## 学习目标

- 理解 GKI Modules 的定义和分类
- 掌握 GKI Modules 列表的组成
- 了解 GKI Modules 的加载机制
- 理解 GKI Modules 与 Generic Kernel 的交互
- 掌握 System DLKM 的作用和特点

## 背景介绍

GKI Modules 是 GKI 架构中的标准模块，提供可选的内核功能。理解 GKI Modules 的机制，有助于理解 GKI 架构的模块化设计。

## 核心概念

### GKI Modules 的定义

**GKI Modules** 是 GKI 架构中的标准可选模块，具有以下特点：

1. **由 Google 维护**
   - 所有 GKI 设备都可以使用
   - 遵循 GKI 标准
   - 与 Generic Kernel 兼容

2. **可选功能**
   - 不是内核核心的一部分
   - 可以通过模块机制动态加载
   - 可以根据需要启用或禁用

3. **标准化接口**
   - 使用 KMI 定义的接口
   - 与 Generic Kernel 兼容
   - 遵循模块开发规范

### GKI Modules 的分类

#### 1. System DLKM（系统动态可加载内核模块）

**定义**：系统级的动态可加载内核模块

**特点**：
- 在系统启动时自动加载
- 由 Android 系统管理
- 提供系统级功能

**位置**：`../common/android/gki_system_dlkm_modules`

**示例模块**：
- `drivers/block/zram/zram.ko` - 压缩内存设备
- `mm/zsmalloc.ko` - 小对象内存分配器

#### 2. 其他 GKI 模块

**定义**：其他通用的 GKI 模块

**特点**：
- 可选加载
- 提供特定功能
- 遵循 GKI 标准

**位置**：`../common/android/gki_aarch64_modules`

## GKI Modules 列表分析

### System DLKM 列表

**文件**：`../common/android/gki_system_dlkm_modules`

**内容**：
```
drivers/block/zram/zram.ko
mm/zsmalloc.ko
```

**分析**：

1. **zram.ko** - 压缩内存设备
   - 作用：提供内存压缩功能
   - 用途：Android 的 swap 机制
   - 特点：系统级功能，启动时加载

2. **zsmalloc.ko** - 小对象分配器
   - 作用：为 zram 提供小对象内存分配
   - 用途：配合 zram 使用
   - 特点：zram 的依赖模块

### GKI 模块列表

**文件**：`../common/android/gki_aarch64_modules`

**内容**：
```
mm/zsmalloc.ko
drivers/block/zram/zram.ko
```

**注意**：这个列表与 System DLKM 列表相同，说明当前版本的 GKI 模块主要是 System DLKM。

## GKI Modules 的加载机制

### 加载时机

#### 1. 系统启动时加载

**System DLKM** 在系统启动时自动加载：

1. **Boot 阶段**：Android 系统启动时
2. **Init 进程**：由 init 进程负责加载
3. **加载顺序**：按照模块依赖关系加载

#### 2. 运行时加载

某些 GKI 模块可以在运行时动态加载：

1. **按需加载**：当需要某个功能时加载
2. **动态卸载**：不需要时可以卸载
3. **依赖管理**：自动处理模块依赖

### 加载过程

#### 1. 模块发现

系统在以下位置查找模块：
- `/vendor/lib/modules/` - Vendor 模块
- `/system/lib/modules/` - System 模块
- `/apex/` - APEX 模块

#### 2. 依赖解析

加载模块时，系统会：
1. 检查模块依赖
2. 加载依赖模块
3. 验证符号兼容性

#### 3. 符号解析

模块加载时：
1. 解析模块需要的符号
2. 在 Generic Kernel 的 KMI 中查找
3. 验证符号版本兼容性

### 模块加载示例

```bash
# 查看已加载的模块
lsmod

# 查看模块信息
modinfo zram

# 查看模块依赖
modprobe -D zram
```

## GKI Modules 与 Generic Kernel 的交互

### 接口使用

GKI Modules 通过 KMI 接口与 Generic Kernel 交互：

1. **使用导出的符号**
   - 调用内核函数
   - 访问内核数据结构
   - 使用内核服务

2. **遵循接口规范**
   - 只能使用 KMI 定义的接口
   - 不能访问未导出的符号
   - 必须遵循接口版本

### 交互方式

#### 1. 函数调用

```c
// GKI Module 中调用内核函数
// 这些函数必须通过 KMI 导出
kmalloc(size, GFP_KERNEL);
kfree(ptr);
```

#### 2. 数据结构访问

```c
// 访问内核数据结构
// 这些结构必须通过 KMI 导出
struct page *page = alloc_pages(GFP_KERNEL, order);
```

#### 3. 回调注册

```c
// 注册回调函数
// 内核通过 KMI 调用模块的回调
register_block_device(device);
```

## System DLKM 详解

### System DLKM 的定义

**System DLKM (Dynamic Loadable Kernel Module)** 是系统级的动态可加载内核模块。

### System DLKM 的特点

1. **系统级功能**
   - 提供系统核心功能
   - 在系统启动时加载
   - 由系统管理

2. **自动加载**
   - 无需手动加载
   - 系统自动处理依赖
   - 保证加载顺序

3. **版本兼容**
   - 与 Generic Kernel 版本兼容
   - 通过 KMI 保证兼容性
   - 可以随系统更新

### System DLKM 的模块

#### zram.ko - 压缩内存设备

**作用**：
- 提供内存压缩功能
- 实现 Android 的 swap 机制
- 提高内存利用率

**源码位置**：`../common/drivers/block/zram/`

**特点**：
- 系统级功能
- 启动时加载
- 与 zsmalloc 配合使用

#### zsmalloc.ko - 小对象分配器

**作用**：
- 为 zram 提供小对象内存分配
- 优化内存使用
- 减少内存碎片

**源码位置**：`../common/mm/zsmalloc.c`

**特点**：
- zram 的依赖模块
- 专门为压缩内存设计
- 高效的小对象分配

### System DLKM 的加载配置

**配置位置**：`../common/build.config.gki.aarch64`

```bash
BUILD_SYSTEM_DLKM=1
MODULES_LIST=${ROOT_DIR}/${KERNEL_DIR}/android/gki_system_dlkm_modules
MODULES_ORDER=android/gki_aarch64_modules
```

这些配置定义：
- 启用 System DLKM 构建
- 指定模块列表
- 定义模块加载顺序

## 源码分析

### 查看 GKI 模块列表

```powershell
# 查看 System DLKM 列表
cd ../common
cat android/gki_system_dlkm_modules
jiabo.wang@build-0-158:~/kl4vnd/bsp/kernel5.15/kernel5.15$ cat android/gki_system_dlkm_modules
drivers/block/zram/zram.ko
mm/zsmalloc.ko

# 查看 GKI 模块列表
cat android/gki_aarch64_modules

jiabo.wang@build-0-158:~/kl4vnd/bsp/kernel5.15/kernel5.15$ cat android/gki_system_dlkm_modules
drivers/block/zram/zram.ko
mm/zsmalloc.ko
jiabo.wang@build-0-158:~/kl4vnd/bsp/kernel5.15/kernel5.15$ cat android/gki_aarch64_modules
mm/zsmalloc.ko
drivers/block/zram/zram.ko

# 查看模块源码
ls drivers/block/zram/
ls mm/zsmalloc.*
```

```powershell
jiabo.wang@build-0-158:~/kl4vnd/bsp/kernel5.15/kernel5.15$ cat android/gki_system_dlkm_modules
drivers/block/zram/zram.ko
mm/zsmalloc.ko
jiabo.wang@build-0-158:~/kl4vnd/bsp/kernel5.15/kernel5.15$ cat android/gki_aarch64_modules
mm/zsmalloc.ko
drivers/block/zram/zram.ko
jiabo.wang@build-0-158:~/kl4vnd/bsp/kernel5.15/kernel5.15$ ^C
jiabo.wang@build-0-158:~/kl4vnd/bsp/kernel5.15/kernel5.15$ ls drivers/block/zram/
Kconfig  Makefile  zcomp.c  zcomp.h  zram_dedup.c  zram_dedup.h  zram_drv.c  zram_drv.h
jiabo.wang@build-0-158:~/kl4vnd/bsp/kernel5.15/kernel5.15$ ls mm/zsmalloc.*
mm/zsmalloc.c
```



### 分析模块依赖

```powershell
# 查看 zram 模块的依赖
cd ../common
grep -r "zsmalloc" drivers/block/zram/
```

### 查看模块构建配置

```powershell
# 查看构建配置中的模块设置
cd ../common
grep -A 5 "BUILD_SYSTEM_DLKM" build.config.gki.aarch64
```

## 实际应用

### 在设备上查看模块

```bash
# 查看已加载的模块
lsmod | grep -E "zram|zsmalloc"

# 查看模块信息
cat /proc/modules | grep zram

# 查看模块参数
cat /sys/module/zram/parameters/*
```

### 分析模块加载问题

如果遇到模块加载问题，可以：

1. **检查模块文件**
   ```bash
   ls -l /vendor/lib/modules/
   ls -l /system/lib/modules/
   ```

2. **查看加载日志**
   ```bash
   dmesg | grep -i "module\|zram"
   ```

3. **验证符号兼容性**
   ```bash
   modinfo zram
   ```

## 与你的性能问题的关联

GKI Modules 的加载可能影响性能：

1. **模块加载时间**：启动时加载模块需要时间
2. **内存占用**：模块占用内核内存
3. **符号解析开销**：模块加载时的符号解析
4. **模块间交互**：模块间的交互可能影响性能

在你的升级问题中，如果 GKI Modules 的加载机制发生变化，可能影响系统性能。

## 总结

### 核心要点

1. **GKI Modules 是标准模块**：由 Google 维护，所有设备可用
2. **System DLKM 是系统级模块**：启动时自动加载
3. **通过 KMI 交互**：使用 KMI 定义的接口
4. **模块化设计**：提供灵活的功能扩展

### 关键特性

- **标准化**：遵循 GKI 标准
- **兼容性**：与 Generic Kernel 兼容
- **模块化**：可以动态加载和卸载
- **系统管理**：由系统自动管理

### 后续学习

- [Vendor Modules 与厂商定制](04-Vendor-Modules与厂商定制.md) - 了解厂商模块
- [KMI 详解](05-KMI-Kernel-Module-Interface详解.md) - 深入理解 KMI 接口
- [GKI 模块加载机制](07-GKI模块加载机制.md) - 详细学习加载机制

## 参考资料

- [GKI 模块列表](../common/android/gki_aarch64_modules)
- [System DLKM 列表](../common/android/gki_system_dlkm_modules)
- [zram 驱动源码](../common/drivers/block/zram/)
- [zsmalloc 源码](../common/mm/zsmalloc.c)

## 更新记录

- 2024-01-21：初始创建，包含 GKI Modules 深入解析
