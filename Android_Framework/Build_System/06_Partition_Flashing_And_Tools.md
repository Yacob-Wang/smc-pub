# 分区刷写和工具

## 📋 目录

1. [Fastboot协议](#1-fastboot协议)
2. [Fastboot命令](#2-fastboot命令)
3. [分区刷写流程](#3-分区刷写流程)
4. [刷写工具对比](#4-刷写工具对比)

---

## 1. Fastboot协议

Fastboot是Android设备刷写分区的标准协议。

### 1.1 进入Fastboot模式

```bash
# 通过ADB
adb reboot bootloader

# 或按住特定按键组合
```

---

## 2. Fastboot命令

### 2.1 基本命令

```bash
# 查看设备
fastboot devices

# 刷写分区
fastboot flash system system.img

# 擦除分区
fastboot erase system

# 重启
fastboot reboot
```

### 2.2 高级命令

```bash
# 刷写到指定槽位
fastboot flash system_a system.img

# 临时启动（不刷写）
fastboot boot boot.img

# 解锁bootloader
fastboot oem unlock
```

---

## 3. 分区刷写流程

1. 进入fastboot模式
2. 连接设备
3. 刷写分区镜像
4. 验证刷写
5. 重启设备

---

## 4. 刷写工具对比

| 工具 | 用途 | 特点 |
|------|------|------|
| fastboot | 标准刷写 | 官方支持 |
| adb | 文件传输 | 需要系统运行 |
| dd | 底层复制 | 需要root |

---

## 总结

分区刷写要点：

1. **Fastboot**：标准刷写工具
2. **命令**：flash, erase, reboot
3. **流程**：进入fastboot → 刷写 → 重启

**下一步学习**：
- 了解分区调试，请阅读 [分区调试和故障排查](07_Partition_Debugging_And_Troubleshooting.md)
