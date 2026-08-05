# GKI 中的内存管理特殊性

## 学习目标

- 理解 GKI 架构对内存管理的影响
- 掌握模块化架构下的内存分配特点
- 了解内存管理在升级问题中的作用
- 理解 GKI 内存管理的最佳实践
- 掌握与你的性能问题的关联分析

## 背景介绍

GKI 架构的模块化设计对内存管理有特殊的影响。理解这些特殊性，有助于分析你在升级后遇到的性能问题。

## 核心概念

### GKI 架构对内存管理的影响

#### 1. 模块化内存分配

**特点**：
- 模块代码和数据结构需要分配内存
- 模块内存与内核内存分离
- 模块内存可以动态分配和释放

**影响**：
- 增加内存分配复杂度
- 可能影响内存碎片
- 需要管理模块内存生命周期

#### 2. 符号解析的内存开销

**特点**：
- 模块加载时需要解析符号
- 符号表占用内存
- 符号解析需要临时内存

**影响**：
- 增加内存使用
- 可能影响启动性能
- 需要优化符号解析

#### 3. 模块间交互的内存开销

**特点**：
- 模块间通过 KMI 交互
- 交互需要内存缓冲区
- 数据传递需要内存

**影响**：
- 增加内存使用
- 可能影响性能
- 需要优化交互机制

## 模块化架构下的内存分配

### 1. 模块代码内存

#### 分配方式

**方式**：使用 `vmalloc()` 分配模块代码内存

**源码位置**：`../common/arch/arm64/kernel/module.c`

**特点**：
- 使用虚拟地址空间
- 可以动态分配
- 支持大块内存

**代码示例**：
```c
// 模块内存分配
void *module_alloc(unsigned long size)
{
    return __vmalloc_node_range(size, 1, MODULES_VADDR, MODULES_END,
                                GFP_KERNEL, PAGE_KERNEL_EXEC, ...);
}
```

#### 内存布局

**模块内存区域**：
- **MODULES_VADDR**：模块虚拟地址起始
- **MODULES_END**：模块虚拟地址结束
- 位于 VMALLOC 区域

**特点**：
- 与内核代码分离
- 可以动态分配
- 支持模块卸载

### 2. 模块数据内存

#### 分配方式

**方式**：使用 `kmalloc()` 或 `vmalloc()` 分配数据内存

**选择**：
- 小对象：使用 `kmalloc()`
- 大对象：使用 `vmalloc()`
- 持久数据：使用 `kmalloc()`
- 临时数据：可以使用 `vmalloc()`

#### 内存管理

**特点**：
- 模块负责管理自己的数据内存
- 卸载时需要释放所有内存
- 避免内存泄漏

### 3. 符号表内存

#### 分配方式

**方式**：内核为符号表分配内存

**特点**：
- 内核维护符号表
- 模块加载时更新符号表
- 符号表占用内核内存

**影响**：
- 增加内核内存使用
- 符号表大小影响内存
- 需要优化符号表

## 内存管理在升级问题中的作用

### 1. 内存回收策略变更

#### 可能的影响

**Generic Kernel 升级可能改变**：
- 内存回收阈值
- 回收策略
- 回收算法

**影响**：
- 可能影响系统性能
- 可能影响应用行为
- 可能影响 GO 语言的 GC

#### 分析方法

```powershell
# 对比两个版本的内存管理变更
cd ../common
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- mm/vmscan.c

# 查看内存回收相关配置变更
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- arch/arm64/configs/gki_defconfig | grep -i "memory\|vmscan"
```

### 2. 页面写回策略变更

#### 可能的影响

**Generic Kernel 升级可能改变**：
- 脏页刷新策略
- 写回阈值
- 写回频率

**影响**：
- 可能影响 I/O 性能
- 可能影响应用响应
- 可能影响 GO 语言的 I/O

#### 分析方法

```powershell
# 对比页面写回相关变更
cd ../common
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- mm/page-writeback.c
```

### 3. 内存分配器变更

#### 可能的影响

**Generic Kernel 升级可能改变**：
- 分配器算法
- 分配策略
- 碎片管理

**影响**：
- 可能影响分配性能
- 可能影响内存碎片
- 可能影响大对象分配

#### 分析方法

```powershell
# 对比内存分配相关变更
cd ../common
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- mm/page_alloc.c mm/slub.c
```

### 4. MMU 和地址布局变更

#### 可能的影响

**Generic Kernel 升级可能改变**：
- 地址空间布局
- 线性映射区域
- 页表管理

**影响**：
- 可能影响地址转换性能
- 可能影响内存访问模式
- 可能影响模块加载

#### 分析方法

```powershell
# 对比 MMU 相关变更
cd ../common
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- arch/arm64/mm/mmu.c

# 查看地址布局定义变更
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- arch/arm64/include/asm/memory.h
```

## GKI 内存管理的最佳实践

### 1. 模块内存管理

#### 分配策略

**建议**：
- 小对象使用 `kmalloc()`
- 大对象使用 `vmalloc()`
- 及时释放不需要的内存
- 避免内存泄漏

#### 生命周期管理

**建议**：
- 在模块初始化时分配
- 在模块卸载时释放
- 使用引用计数管理共享内存
- 避免悬空指针

### 2. 符号表优化

#### 优化策略

**建议**：
- 只导出必要的符号
- 使用 KMI 列表管理符号
- 定期清理未使用的符号
- 优化符号表大小

### 3. 内存回收优化

#### 优化策略

**建议**：
- 合理设置 swappiness
- 优化内存回收阈值
- 监控内存使用情况
- 调整回收策略

## 与你的性能问题的关联

### 问题分析

你的升级问题（2024-05_r2 → 2024-11_r3 性能劣化）可能与以下内存管理变更相关：

#### 1. 内存回收策略变更

**可能原因**：
- Generic Kernel 升级改变了内存回收策略
- 新的回收策略可能更激进
- 可能影响 GO 语言的 GC 行为

**分析方法**：
```powershell
cd ../common
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- mm/vmscan.c | Select-String -Pattern "swappiness\|watermark\|reclaim" -Context 3
```

#### 2. 页面写回策略变更

**可能原因**：
- 页面写回策略的变化
- 脏页刷新频率的变化
- 可能影响 I/O 性能

**分析方法**：
```powershell
cd ../common
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- mm/page-writeback.c | Select-String -Pattern "dirty\|writeback" -Context 3
```

#### 3. 内存分配器变更

**可能原因**：
- 分配器算法的优化
- 分配策略的变化
- 可能影响大对象分配

**分析方法**：
```powershell
cd ../common
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- mm/page_alloc.c mm/slub.c | Select-String -Pattern "alloc\|free" -Context 2
```

#### 4. MMU 和地址布局变更

**可能原因**：
- 地址空间布局的变化
- 线性映射区域的变化
- 可能影响内存访问性能

**分析方法**：
```powershell
cd ../common
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- arch/arm64/mm/mmu.c | Select-String -Pattern "PAGE_OFFSET\|PAGE_END\|VMALLOC" -Context 3
```

### GO 语言 GC 与内核内存回收的交互

#### 潜在冲突

**问题**：
- GO 语言的 GC 需要分配大块内存
- 内核的内存回收可能回收这些内存
- 两者可能产生冲突

**影响**：
- GO GC 可能触发内核内存回收
- 内核内存回收可能影响 GO GC
- 可能导致性能劣化

#### 分析思路

1. **监控内存使用**
   ```bash
   # 监控内存使用情况
   cat /proc/meminfo
   cat /proc/vmstat
   ```

2. **分析内存回收**
   ```bash
   # 查看内存回收统计
   cat /proc/vmstat | grep -i "reclaim\|scan"
   ```

3. **对比两个版本**
   - 对比内存使用模式
   - 对比内存回收频率
   - 对比性能指标

## 源码分析

### 查看内存管理相关变更

```powershell
# 对比内存管理核心文件的变更
cd ../common

# 内存回收
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- mm/vmscan.c --stat

# 页面写回
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- mm/page-writeback.c --stat

# MMU
git diff android13-5.15-2024-05_r2 android13-5.15-2024-11_r3 -- arch/arm64/mm/mmu.c --stat
```

### 分析关键变更

```powershell
# 查找可能影响性能的变更
cd ../common
git log android13-5.15-2024-05_r2..android13-5.15-2024-11_r3 --oneline -- mm/vmscan.c mm/page-writeback.c arch/arm64/mm/mmu.c
```

## 实际应用

### 在设备上监控内存

```bash
# 查看内存使用情况
cat /proc/meminfo

# 查看内存统计
cat /proc/vmstat

# 查看内存回收统计
cat /proc/vmstat | grep -i "reclaim\|scan\|compact"
```

### 分析内存问题

```bash
# 查看内存压力
cat /proc/pressure/memory

# 查看 OOM 统计
dmesg | grep -i "oom\|kill"

# 查看内存分配失败
dmesg | grep -i "allocation failure"
```

## 总结

### 核心要点

1. **GKI 架构对内存管理有特殊影响**：模块化架构增加了内存管理复杂度
2. **升级可能改变内存管理策略**：Generic Kernel 升级可能影响内存管理行为
3. **需要分析内存管理变更**：通过对比版本差异分析问题
4. **GO GC 与内核回收可能冲突**：需要协调两者的行为

### 关键特性

- **模块化内存**：模块代码和数据需要特殊管理
- **符号表内存**：符号解析需要内存开销
- **交互内存**：模块间交互需要内存缓冲区
- **升级影响**：升级可能改变内存管理策略

### 分析要点

- 对比内存回收策略变更
- 对比页面写回策略变更
- 对比内存分配器变更
- 对比 MMU 和地址布局变更

### 后续学习

- [GKI 升级与兼容性](09-GKI升级与兼容性.md) - 理解升级对内存管理的影响
- [GKI 实战案例分析](10-GKI实战案例分析.md) - 实际案例分析

## 参考资料

- [内存管理源码](../common/mm/)
- [MMU 源码](../common/arch/arm64/mm/mmu.c)
- [内存管理文档](../common/Documentation/admin-guide/mm/)

## 更新记录

- 2024-01-21：初始创建，包含 GKI 中的内存管理特殊性
