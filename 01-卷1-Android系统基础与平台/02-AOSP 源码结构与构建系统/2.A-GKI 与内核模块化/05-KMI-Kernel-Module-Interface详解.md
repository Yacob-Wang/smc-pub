# KMI (Kernel Module Interface) 详解

## 学习目标

- 理解 KMI 的定义和作用
- 掌握 KMI 符号列表的组成和管理
- 了解 KMI 版本管理和兼容性机制
- 理解 KMI 符号的导出和限制
- 掌握 KMI 在模块间通信中的作用
- 理解 KMI 稳定性保证机制

## 背景介绍

KMI (Kernel Module Interface) 是 GKI 架构的核心接口，定义了 Generic Kernel 向模块导出的符号。理解 KMI 的机制，是理解 GKI 架构如何保证兼容性的关键。

## 核心概念

### KMI 的定义

**KMI (Kernel Module Interface)** 是 Generic Kernel 向模块导出的符号接口，具有以下特点：

1. **稳定的接口**
   - 保证向后兼容
   - 版本管理
   - 接口文档化

2. **受控的导出**
   - 只有列表中的符号可以导出
   - 严格控制接口变更
   - 保证接口稳定性

3. **版本兼容性**
   - 支持版本检查
   - 保证模块兼容性
   - 处理接口变更

### KMI 的作用

#### 1. 定义模块接口

KMI 定义了模块可以使用的内核接口：

- **函数接口**：模块可以调用的内核函数
- **数据结构**：模块可以访问的数据结构
- **常量定义**：模块可以使用的常量

#### 2. 保证兼容性

KMI 通过以下方式保证兼容性：

- **接口稳定性**：接口不会随意变更
- **版本管理**：通过版本号管理接口变更
- **兼容性检查**：加载时检查模块兼容性

#### 3. 控制接口变更

KMI 严格控制接口变更：

- **变更审查**：接口变更需要审查
- **版本升级**：接口变更需要升级版本
- **向后兼容**：尽量保持向后兼容

## KMI 符号列表分析

### KMI 符号列表文件

**位置**：`../common/android/abi_gki_aarch64`

**格式**：
```
[abi_symbol_list]
# 注释说明
  symbol_name
  another_symbol
```

### 符号分类

#### 1. 常用符号（Commonly Used Symbols）

**示例**：
```
arm64_const_caps_ready
kfree
kmalloc_caches
kmem_cache_alloc_trace
memcpy
module_layout
__per_cpu_offset
preempt_schedule
_printk
```

**作用**：
- 基础内核功能
- 内存管理函数
- 常用工具函数

#### 2. 模块特定符号（Module-Specific Symbols）

**示例**：
```
# required by zram.ko
__alloc_percpu
bio_endio
blk_alloc_disk
...
```

**作用**：
- 特定模块需要的符号
- 按模块组织
- 明确模块依赖

#### 3. 保留符号（Preserved Symbols）

**示例**：
```
# preserved by --additions-only
android_kmalloc_64_create
```

**作用**：
- 特殊保留的符号
- 不能随意删除
- 需要特殊处理

### 符号列表管理

#### 查看符号列表

```powershell
# 查看完整的 KMI 符号列表
cd ../common
cat android/abi_gki_aarch64

# 统计符号数量
cat android/abi_gki_aarch64 | grep -v "^#" | grep -v "^$" | wc -l

# 搜索特定符号
cat android/abi_gki_aarch64 | grep -i "memory\|alloc"
```

#### 符号分类统计

```powershell
# 统计不同类别的符号
cd ../common
cat android/abi_gki_aarch64 | grep "^# required by" | wc -l
```

## KMI 版本管理和兼容性

### 版本管理机制

#### 1. KMI 版本号

**格式**：通常与内核版本关联

**示例**：
- `android13-5.15` 对应特定的 KMI 版本
- 版本升级时 KMI 可能变更

#### 2. 版本兼容性

**规则**：
- **主版本变更**：可能不兼容
- **次版本变更**：通常兼容
- **补丁版本变更**：完全兼容

#### 3. 兼容性检查

**检查时机**：
- 模块加载时
- 符号解析时
- 版本验证时

**检查内容**：
- 符号是否存在
- 符号版本是否匹配
- 接口是否兼容

### 兼容性保证机制

#### 1. 符号导出控制

**机制**：
- 只有 KMI 列表中的符号可以导出
- 未列出的符号不能导出
- 严格控制导出范围

**配置**：
```bash
# 从 build.config.gki.aarch64 中可以看到：
KMI_ENFORCED=1
KMI_SYMBOL_LIST_STRICT_MODE=1
TRIM_NONLISTED_KMI=1
```

这些配置确保：
- 强制 KMI 检查
- 严格模式
- 删除未列出的符号

#### 2. 接口变更管理

**变更流程**：
1. **提出变更**：需要添加或修改接口
2. **审查变更**：审查接口变更的影响
3. **更新列表**：更新 KMI 符号列表
4. **版本升级**：升级 KMI 版本
5. **兼容性测试**：测试模块兼容性

#### 3. 向后兼容保证

**原则**：
- 尽量保持向后兼容
- 接口变更需要充分理由
- 提供迁移路径

## KMI 符号的导出和限制

### 符号导出机制

#### 1. EXPORT_SYMBOL

**作用**：导出符号供模块使用

**示例**：
```c
// 在内核代码中
EXPORT_SYMBOL(kmalloc);
EXPORT_SYMBOL_GPL(kfree);
```

**限制**：
- 只有 KMI 列表中的符号可以导出
- 未列出的符号即使使用 EXPORT_SYMBOL 也不会导出

#### 2. 符号可见性

**机制**：
- KMI 列表中的符号：可见，可以导出
- 未列出的符号：不可见，不能导出

**验证**：
```powershell
# 查看内核导出的符号
cd ../common
nm vmlinux | grep " T " | head -20
```

### 符号使用限制

#### 1. 模块只能使用 KMI 符号

**限制**：
- 模块只能使用 KMI 列表中的符号
- 不能使用未导出的内部符号
- 不能直接访问内核内部数据结构

**检查**：
```bash
# 检查模块使用的符号
nm vendor_module.ko | grep " U "

# 验证符号是否在 KMI 中
# 对比模块需要的符号和 KMI 列表
```

#### 2. 符号版本检查

**机制**：
- 模块加载时检查符号版本
- 验证符号兼容性
- 拒绝不兼容的模块

**错误示例**：
```
Unknown symbol in module
```

这通常表示：
- 符号不在 KMI 中
- 符号版本不匹配
- 模块不兼容

## KMI 在模块间通信中的作用

### 1. Generic Kernel → GKI Modules

**通信方式**：
- GKI Modules 使用 KMI 符号
- 调用 Generic Kernel 的函数
- 访问 Generic Kernel 的数据结构

**示例**：
```c
// GKI Module 中使用 KMI 符号
void *ptr = kmalloc(size, GFP_KERNEL);  // kmalloc 在 KMI 中
kfree(ptr);  // kfree 在 KMI 中
```

### 2. Generic Kernel → Vendor Modules

**通信方式**：
- Vendor Modules 使用 KMI 符号
- 通过 KMI 接口与内核交互
- 受 KMI 限制

**限制**：
- 只能使用 KMI 定义的接口
- 不能访问未导出的符号
- 必须遵循接口规范

### 3. GKI Modules ↔ Vendor Modules

**通信方式**：
- 通过 KMI 接口间接通信
- 都使用 Generic Kernel 的接口
- 不直接交互

**特点**：
- 模块间不直接依赖
- 通过 Generic Kernel 交互
- 降低耦合度

## KMI 稳定性保证机制

### 1. 符号列表管理

#### 添加符号

**流程**：
1. 提出添加请求
2. 审查符号的必要性
3. 更新 KMI 符号列表
4. 验证兼容性

**配置**：
```bash
KMI_SYMBOL_LIST_ADD_ONLY=1
```

这个配置确保：
- 只能添加符号
- 不能随意删除符号
- 保证接口稳定性

#### 删除符号

**限制**：
- 删除符号需要充分理由
- 需要提供迁移路径
- 需要版本升级

**流程**：
1. 评估删除影响
2. 提供替代方案
3. 更新文档
4. 版本升级

### 2. 接口变更控制

#### 变更类型

1. **添加接口**：相对安全，向后兼容
2. **修改接口**：可能不兼容，需要版本升级
3. **删除接口**：不兼容，需要版本升级

#### 变更审查

**审查内容**：
- 变更的必要性
- 对现有模块的影响
- 兼容性保证
- 迁移方案

### 3. 版本兼容性测试

**测试内容**：
- 模块加载测试
- 符号解析测试
- 功能测试
- 性能测试

**自动化**：
- CI/CD 集成
- 自动化测试
- 兼容性检查

## 源码分析

### 查看 KMI 符号列表

```powershell
# 查看完整的 KMI 符号列表
cd ../common
cat android/abi_gki_aarch64

# 分析符号分类
cat android/abi_gki_aarch64 | grep "^#"

# 统计符号数量
cat android/abi_gki_aarch64 | grep -v "^#" | grep -v "^$" | wc -l
```

### 查看 KMI 配置

```powershell
# 查看构建配置中的 KMI 设置
cd ../common
grep -A 10 "KMI" build.config.gki.aarch64
```

### 分析符号导出

```powershell
# 查看内核中的符号导出
cd ../common
grep -r "EXPORT_SYMBOL" mm/ | head -20
```

## 实际应用

### 在设备上验证 KMI

```bash
# 查看内核导出的符号
cat /proc/kallsyms | grep " T " | head -20

# 查看模块使用的符号
cat /proc/modules
dmesg | grep "Unknown symbol"
```

### 分析模块兼容性问题

如果遇到模块加载失败：

1. **检查符号**
   ```bash
   # 查看未解析的符号
   dmesg | grep "Unknown symbol"
   ```

2. **验证 KMI 兼容性**
   ```bash
   # 检查模块需要的符号是否在 KMI 中
   modinfo vendor_module.ko
   ```

3. **检查版本兼容性**
   ```bash
   # 查看内核版本
   uname -r
   # 查看模块版本要求
   modinfo vendor_module.ko | grep vermagic
   ```

## 与你的性能问题的关联

KMI 接口的变更可能影响性能：

1. **接口变更**：KMI 接口的变更可能影响模块行为
2. **符号解析**：符号解析的变化可能影响性能
3. **兼容性检查**：兼容性检查的开销
4. **模块交互**：通过 KMI 的模块交互可能影响性能

在你的升级问题中：
- KMI 接口的变更可能影响 Vendor Modules 的行为
- 符号解析的变化可能影响模块加载性能
- 兼容性检查的变化可能影响系统性能

## 总结

### 核心要点

1. **KMI 是 GKI 架构的核心接口**：定义模块可以使用的内核接口
2. **保证接口稳定性**：通过版本管理和兼容性检查
3. **严格控制接口变更**：确保向后兼容
4. **支持模块化架构**：允许模块通过接口交互

### 关键特性

- **稳定性**：接口保持稳定，向后兼容
- **可控性**：严格控制接口变更
- **兼容性**：保证模块兼容性
- **文档化**：接口明确文档化

### 管理机制

- **符号列表管理**：明确列出可用的符号
- **版本管理**：通过版本号管理接口变更
- **兼容性检查**：加载时检查兼容性
- **变更审查**：严格控制接口变更

### 后续学习

- [GKI 模块加载机制](07-GKI模块加载机制.md) - 了解模块如何通过 KMI 加载
- [GKI 升级与兼容性](09-GKI升级与兼容性.md) - 理解 KMI 在升级中的作用
- [GKI 实战案例分析](10-GKI实战案例分析.md) - 实际案例分析

## 参考资料

- [KMI 符号列表](../common/android/abi_gki_aarch64)
- [GKI 构建配置](../common/build.config.gki.aarch64)
- [Android KMI 文档](https://source.android.com/docs/core/architecture/kernel/generic-kernel-image)

## 更新记录

- 2024-01-21：初始创建，包含 KMI 详解
