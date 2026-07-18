# 分区挂载和使用

## 📋 目录

1. [fstab文件的作用](#1-fstab文件的作用)
2. [分区挂载时机](#2-分区挂载时机)
3. [分区挂载点](#3-分区挂载点)
4. [运行时分区访问](#4-运行时分区访问)

---

## 1. fstab文件的作用

### 1.1 fstab文件位置

fstab文件定义了分区的挂载信息：

- `device/{vendor}/{device}/fstab.{board}`
- 编译后复制到：`/vendor/etc/fstab.{board}` 或 `/system/etc/fstab.{board}`

### 1.2 fstab文件格式

```
<src> <mnt_point> <type> <mnt_flags> <fs_mgr_flags>
```

**示例**：
```
/dev/block/by-name/system /system ext4 ro,seclabel,relatime wait,avb=system
/dev/block/by-name/vendor /vendor ext4 ro,seclabel,relatime wait,avb=vendor
/dev/block/by-name/userdata /data f2fs rw,seclabel,nosuid,nodev,noatime wait,check,fileencryption=aes-256-xts
```

### 1.3 fs_mgr_flags说明

- `wait`：等待设备就绪
- `check`：检查文件系统
- `avb=system`：AVB验证
- `fileencryption`：文件加密

---

## 2. 分区挂载时机

### 2.1 早期挂载（Init阶段）

在init进程启动时挂载：

- `system`
- `vendor`
- `product`
- `system_ext`
- `odm`

### 2.2 后期挂载（系统服务启动后）

在系统服务启动后挂载：

- `userdata`
- `metadata`
- `cache`

---

## 3. 分区挂载点

| 分区 | 挂载点 | 说明 |
|------|--------|------|
| `system` | `/system` | 系统框架 |
| `vendor` | `/vendor` | 供应商代码 |
| `product` | `/product` 或 `/system/product` | 产品模块 |
| `system_ext` | `/system_ext` 或 `/system/system_ext` | 系统扩展 |
| `odm` | `/odm` | ODM定制 |
| `userdata` | `/data` | 用户数据 |
| `cache` | `/cache` | 缓存 |

---

## 4. 运行时分区访问

### 4.1 查看挂载信息

```bash
# 查看所有挂载点
adb shell mount

# 查看特定分区
adb shell mount | grep system
adb shell mount | grep vendor

# 查看分区使用情况
adb shell df -h
```

### 4.2 分区访问权限

- 只读分区：`system`, `vendor`, `product`等
- 读写分区：`userdata`, `cache`

---

## 总结

分区挂载和使用要点：

1. **fstab文件**：定义分区挂载配置
2. **挂载时机**：早期挂载系统分区，后期挂载数据分区
3. **挂载点**：每个分区有固定的挂载点
4. **访问权限**：系统分区只读，数据分区读写

**下一步学习**：
- 了解系统初始化流程，请阅读 [系统初始化流程](03_System_Initialization_Flow.md)
