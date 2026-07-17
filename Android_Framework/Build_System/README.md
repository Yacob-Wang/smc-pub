# Android 编译与分区系统完整指南

> 本指南全面介绍 Android 16 的分区系统、编译方法、系统组成和动态更新机制

**最后更新**: 2026年1月  
**适用版本**: Android 16 (Baklava)  
**目标读者**: Android 系统开发者、编译工程师、系统架构师

---

## 📋 目录导航

### 第一部分：分区系统基础

1. **[分区系统概述](01_Partition_System/01_Android_Partition_Overview.md)**
   - Android分区系统的历史演进
   - 分区系统的基本概念
   - 分区与文件系统的关系

2. **[分区类型详解](01_Partition_System/02_Partition_Types_And_Details.md)** ⭐
   - Android 16 所有分区详细说明（30+个分区）
   - 每个分区的作用、大小、文件系统、挂载点
   - 分区与镜像文件的对应关系

3. **[分区布局和结构](01_Partition_System/03_Partition_Layout_And_Structure.md)**
   - GPT分区表详解
   - 动态分区系统
   - 分区大小规划

4. **[分区与镜像的关系](01_Partition_System/04_Partition_vs_Image_Relationship.md)**
   - 分区 vs 镜像的概念区别
   - sparse image 和 raw image 格式
   - 镜像与分区的映射关系

### 第二部分：编译系统

5. **[AOSP编译环境搭建](02_Build_System/01_AOSP_Build_Environment.md)**
   - 编译环境要求
   - 源码获取和配置
   - 工具链配置

6. **[分区编译流程](02_Build_System/02_Partition_Build_Process.md)** ⭐
   - 所有分区的编译方法
   - 编译命令和流程
   - 编译产物说明

7. **[镜像生成和打包](02_Build_System/03_Image_Generation_And_Packaging.md)**
   - 镜像生成工具详解
   - 镜像打包流程
   - 镜像格式转换

8. **[编译配置和选项](02_Build_System/04_Build_Configuration_And_Options.md)**
   - BoardConfig.mk 配置
   - 分区大小配置
   - 编译选项说明

### 第三部分：系统集成

9. **[系统组成和启动流程](03_System_Integration/01_System_Composition_And_Boot.md)**
   - Android系统启动流程
   - 各分区在启动中的作用
   - 分区加载顺序

10. **[分区挂载和使用](03_System_Integration/02_Partition_Mount_And_Usage.md)**
    - fstab文件的作用
    - 分区挂载时机和挂载点
    - 运行时分区访问

11. **[系统初始化流程](03_System_Integration/03_System_Initialization_Flow.md)**
    - init进程的作用
    - rc文件解析
    - 服务启动顺序

### 第四部分：动态更新

12. **[OTA更新机制](04_Dynamic_Updates/01_OTA_Update_Mechanism.md)**
    - OTA更新的基本原理
    - 增量更新 vs 全量更新
    - 更新包生成

13. **[可更新分区详解](04_Dynamic_Updates/02_Updatable_Partitions.md)**
    - 哪些分区可以动态更新
    - 更新限制和原因
    - 更新方式对比

14. **[A/B分区系统](04_Dynamic_Updates/03_A_B_Partition_System.md)**
    - A/B分区的设计原理
    - 无缝更新机制
    - 回滚机制

15. **[更新验证和回滚](04_Dynamic_Updates/04_Update_Verification_And_Rollback.md)**
    - AVB验证机制
    - 签名验证
    - 更新失败处理

### 第五部分：编译专家专题

16. **[动态分区深度解析](05_Expert_Topics/01_Dynamic_Partitions_Deep_Dive.md)**
    - super分区的内部结构
    - 逻辑分区管理
    - 分区大小动态调整

17. **[分区表和GPT详解](05_Expert_Topics/02_Partition_Table_And_GPT.md)**
    - GPT分区表结构
    - 分区表工具使用
    - 分区表修复方法

18. **[镜像格式和工具详解](05_Expert_Topics/03_Image_Format_And_Tools.md)**
    - sparse image格式详解
    - 镜像格式转换
    - 镜像文件解析工具

19. **[分区大小计算和规划](05_Expert_Topics/04_Partition_Size_Calculation.md)**
    - 分区大小计算原则
    - 文件系统开销计算
    - 分区大小优化

20. **[AVB验证和签名机制](05_Expert_Topics/05_AVB_And_Signing.md)**
    - Android Verified Boot原理
    - 分区签名流程
    - 密钥管理

21. **[分区刷写和工具](05_Expert_Topics/06_Partition_Flashing_And_Tools.md)**
    - fastboot协议详解
    - 分区刷写流程
    - 刷写工具对比

22. **[分区调试和故障排查](05_Expert_Topics/07_Partition_Debugging_And_Troubleshooting.md)**
    - 分区问题诊断方法
    - 常见错误和解决方案
    - 调试工具使用

23. **[不同厂商的分区差异](05_Expert_Topics/08_Vendor_Specific_Differences.md)**
    - 主流厂商分区对比
    - 厂商特定分区说明
    - 兼容性考虑

---

## 🎯 快速索引

### Android 16 核心分区列表

**启动分区（A/B槽位）**：
- `boot` - 内核镜像
- `init_boot` - 通用ramdisk（Android 13+）
- `vendor_boot` - 供应商ramdisk
- `dtbo` - 设备树覆盖层

**系统分区（A/B槽位）**：
- `system` - 核心OS镜像
- `system_ext` - 系统扩展模块
- `product` - 产品特定模块
- `vendor` - 硬件特定二进制和HAL
- `odm` - ODM定制化

**DLKM分区（A/B槽位）**：
- `system_dlkm` - 系统内核模块
- `vendor_dlkm` - 供应商内核模块
- `odm_dlkm` - ODM内核模块

**验证分区（A/B槽位）**：
- `vbmeta` - Verified Boot元数据
- `vbmeta_system` - system分区验证
- `vbmeta_vendor` - vendor分区验证
- `vbmeta_vendor_dlkm` - vendor_dlkm验证

**数据分区（单槽位）**：
- `userdata` - 用户数据
- `cache` - 临时数据
- `metadata` - 加密元数据
- `misc` - OTA状态
- `persist` - 持久化存储
- `frp` - 工厂重置保护

**特殊分区**：
- `recovery` - 恢复模式
- `super` - 动态分区容器
- `generic_bootloader` - 引导加载程序

### 常用命令速查

```bash
# 查看分区列表
adb shell ls -l /dev/block/by-name/

# 查看分区信息
adb shell lsblk

# 刷写分区
fastboot flash boot boot.img
fastboot flash system system.img

# 查看分区大小
adb shell df -h

# 查看挂载信息
adb shell mount | grep -E "system|vendor|product"
```

---

## 📚 学习路径建议

### 初学者路径
1. 分区系统概述 → 分区类型详解
2. 分区与镜像的关系
3. AOSP编译环境搭建 → 分区编译流程

### 进阶路径
1. 系统组成和启动流程
2. A/B分区系统
3. 动态分区深度解析

### 专家路径
1. AVB验证和签名机制
2. 分区调试和故障排查
3. 不同厂商的分区差异

---

## 🔗 相关文档

- [ACK内核编译与刷入指南](../05_Linux_Kernel/Architecture/ACK_Build_And_Flash_Complete_Guide.md)
- [GKI 2.0 vs 非GKI完整指南](../05_Linux_Kernel/Architecture/GKI2.0_vs_Non_GKI_Complete_Guide.md)
- [Android内核架构概述](../05_Linux_Kernel/Architecture/Android_Kernel_Architecture_Overview.md)

---

## 📝 文档说明

- ⭐ 标记的文档为重点推荐阅读
- 所有文档基于 Android 16 (Baklava) 版本
- 文档会持续更新，建议定期查看最新版本
- 如有问题或建议，欢迎反馈

---

**开始学习**: 建议从 [分区系统概述](01_Partition_System/01_Android_Partition_Overview.md) 开始
