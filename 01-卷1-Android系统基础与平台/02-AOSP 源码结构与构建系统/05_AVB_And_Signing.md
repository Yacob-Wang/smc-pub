# AVB验证和签名机制

## 📋 目录

1. [Android Verified Boot原理](#1-android-verified-boot原理)
2. [分区签名流程](#2-分区签名流程)
3. [密钥管理](#3-密钥管理)
4. [vbmeta结构](#4-vbmeta结构)

---

## 1. Android Verified Boot原理

AVB（Android Verified Boot）用于验证分区完整性，防止恶意修改。

### 1.1 验证流程

```
Bootloader → vbmeta → 各分区
```

### 1.2 验证链

- vbmeta是验证链的根
- 各分区通过vbmeta验证
- 验证失败则拒绝启动

---

## 2. 分区签名流程

### 2.1 使用avbtool签名

```bash
avbtool add_hash_footer \
    --image system.img \
    --partition_name system \
    --partition_size 3221225472 \
    --key private_key.pem \
    --algorithm SHA256_RSA4096
```

---

## 3. 密钥管理

### 3.1 生成密钥

```bash
# 生成RSA密钥对
openssl genrsa -out private_key.pem 4096
openssl rsa -in private_key.pem -pubout -out public_key.pem
```

### 3.2 密钥安全

- 私钥必须保密
- 公钥可以公开
- 私钥丢失无法更新系统

---

## 4. vbmeta结构

vbmeta包含：
- 分区描述符
- 哈希值
- 签名
- 公钥

---

## 总结

AVB验证要点：

1. **验证链**：vbmeta是根
2. **签名**：使用avbtool签名
3. **密钥**：私钥保密，公钥公开

**下一步学习**：
- 了解分区刷写，请阅读 [分区刷写和工具](06_Partition_Flashing_And_Tools.md)
