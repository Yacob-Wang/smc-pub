# 分区调试和故障排查

## 📋 目录

1. [分区问题诊断](#1-分区问题诊断)
2. [常见错误和解决方案](#2-常见错误和解决方案)
3. [调试工具](#3-调试工具)

---

## 1. 分区问题诊断

### 1.1 查看分区信息

```bash
# 查看所有分区
adb shell ls -l /dev/block/by-name/

# 查看分区大小
adb shell blockdev --getsize64 /dev/block/by-name/system

# 查看挂载信息
adb shell mount | grep system
```

---

## 2. 常见错误和解决方案

### 2.1 分区挂载失败

**问题**：分区无法挂载

**解决方案**：
```bash
# 检查分区是否存在
adb shell ls -l /dev/block/by-name/system

# 检查文件系统
adb shell e2fsck -f /dev/block/by-name/system
```

### 2.2 分区空间不足

**问题**：分区空间不足

**解决方案**：
- 清理分区内容
- 增加分区大小（需要重新分区）

---

## 3. 调试工具

### 3.1 lsblk

```bash
adb shell lsblk
```

### 3.2 blkid

```bash
adb shell blkid
```

### 3.3 df

```bash
adb shell df -h
```

---

## 总结

分区调试要点：

1. **诊断工具**：lsblk, blkid, df
2. **常见问题**：挂载失败、空间不足
3. **解决方案**：检查分区、修复文件系统

**下一步学习**：
- 了解厂商差异，请阅读 [不同厂商的分区差异](08_Vendor_Specific_Differences.md)
