# OTA更新机制

## 📋 目录

1. [OTA更新的基本原理](#1-ota更新的基本原理)
2. [增量更新vs全量更新](#2-增量更新vs全量更新)
3. [更新包的生成](#3-更新包的生成)
4. [更新流程](#4-更新流程)

---

## 1. OTA更新的基本原理

OTA（Over-The-Air）更新允许设备通过网络接收和安装系统更新，无需连接电脑。

### 1.1 更新方式

- **全量更新**：完整的系统镜像
- **增量更新**：只包含变更部分
- **A/B更新**：无缝更新，无需重启到recovery

---

## 2. 增量更新vs全量更新

### 2.1 全量更新

**特点**：
- 包含完整分区镜像
- 文件较大
- 更新可靠

**适用场景**：
- 大版本升级
- 增量更新失败时回退

### 2.2 增量更新

**特点**：
- 只包含变更部分
- 文件较小
- 更新速度快

**适用场景**：
- 小版本更新
- 安全补丁

---

## 3. 更新包的生成

### 3.1 生成OTA包

```bash
# 生成全量OTA包
./build/tools/releasetools/ota_from_target_files \
    -k build/target/product/security/testkey \
    target_files.zip ota.zip

# 生成增量OTA包
./build/tools/releasetools/ota_from_target_files \
    -k build/target/product/security/testkey \
    -i previous_target_files.zip \
    target_files.zip incremental_ota.zip
```

---

## 4. 更新流程

### 4.1 A/B设备更新流程

1. 下载OTA包到非活动槽位
2. 验证OTA包签名
3. 应用更新到非活动槽位
4. 验证更新后的分区
5. 切换活动槽位
6. 重启到新系统

### 4.2 非A/B设备更新流程

1. 下载OTA包
2. 重启到recovery模式
3. 验证OTA包
4. 应用更新
5. 重启到新系统

---

## 总结

OTA更新机制要点：

1. **更新方式**：全量或增量
2. **A/B更新**：无缝更新体验
3. **更新流程**：下载→验证→应用→重启

**下一步学习**：
- 了解可更新分区，请阅读 [可更新分区详解](02_Updatable_Partitions.md)
