# 可更新分区详解

## 📋 目录

1. [可更新分区列表](#1-可更新分区列表)
2. [不可更新分区](#2-不可更新分区)
3. [更新限制和原因](#3-更新限制和原因)
4. [更新方式](#4-更新方式)

---

## 1. 可更新分区列表

### 1.1 A/B槽位分区（可OTA更新）

- ✅ `boot` / `boot_a` / `boot_b`
- ✅ `init_boot` / `init_boot_a` / `init_boot_b`
- ✅ `vendor_boot` / `vendor_boot_a` / `vendor_boot_b`
- ✅ `dtbo` / `dtbo_a` / `dtbo_b`
- ✅ `system` / `system_a` / `system_b`
- ✅ `vendor` / `vendor_a` / `vendor_b`
- ✅ `product` / `product_a` / `product_b`
- ✅ `system_ext` / `system_ext_a` / `system_ext_b`
- ✅ `odm` / `odm_a` / `odm_b`
- ✅ `system_dlkm` / `system_dlkm_a` / `system_dlkm_b`
- ✅ `vendor_dlkm` / `vendor_dlkm_a` / `vendor_dlkm_b`
- ✅ `odm_dlkm` / `odm_dlkm_a` / `odm_dlkm_b`
- ✅ `vbmeta` 系列（需要签名）

---

## 2. 不可更新分区

- ❌ `generic_bootloader`（需要特殊工具，风险高）
- ⚠️ `userdata`（会丢失数据，通常不通过OTA更新）

---

## 3. 更新限制和原因

### 3.1 bootloader更新限制

**原因**：
- 更新失败可能导致设备变砖
- 需要特殊工具和权限
- 通常由厂商通过特殊渠道更新

### 3.2 userdata更新限制

**原因**：
- 包含用户数据
- 更新会丢失数据
- 通常只格式化，不更新内容

---

## 4. 更新方式

### 4.1 OTA更新

- 通过网络下载和安装
- 支持A/B无缝更新
- 需要签名验证

### 4.2 Fastboot更新

```bash
fastboot flash system system.img
fastboot flash vendor vendor.img
```

### 4.3 ADB Sideload

```bash
adb sideload update.zip
```

---

## 总结

可更新分区要点：

1. **A/B分区**：支持无缝OTA更新
2. **bootloader**：通常不可更新
3. **userdata**：条件更新（会丢失数据）

**下一步学习**：
- 了解A/B分区系统，请阅读 [A/B分区系统](03_A_B_Partition_System.md)
