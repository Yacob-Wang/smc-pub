# 分区表和GPT详解

## 📋 目录

1. [GPT分区表结构](#1-gpt分区表结构)
2. [分区表工具](#2-分区表工具)
3. [分区表修复](#3-分区表修复)

---

## 1. GPT分区表结构

GPT（GUID Partition Table）是Android设备使用的分区表格式。

### 1.1 GPT布局

```
LBA 0: Protective MBR
LBA 1: Primary GPT Header
LBA 2-33: Primary Partition Entries (128 entries)
...
实际分区数据
...
Backup Partition Entries
Backup GPT Header
```

### 1.2 GPT Header

包含分区表元数据：
- 签名
- 版本
- 分区表大小
- 分区条目数量

---

## 2. 分区表工具

### 2.1 gdisk

```bash
# 查看分区表
gdisk -l /dev/block/sda

# 编辑分区表
gdisk /dev/block/sda
```

### 2.2 parted

```bash
# 查看分区表
parted /dev/block/sda print

# 创建分区
parted /dev/block/sda mkpart primary ext4 1MiB 100MiB
```

---

## 3. 分区表修复

### 3.1 备份恢复

```bash
# 备份分区表
sgdisk --backup=partition_table_backup.bin /dev/block/sda

# 恢复分区表
sgdisk --load-backup=partition_table_backup.bin /dev/block/sda
```

---

## 总结

GPT分区表要点：

1. **GPT结构**：包含主表和备份表
2. **工具**：gdisk, parted, sgdisk
3. **修复**：可以使用备份恢复

**下一步学习**：
- 了解镜像格式，请阅读 [镜像格式和工具详解](03_Image_Format_And_Tools.md)
