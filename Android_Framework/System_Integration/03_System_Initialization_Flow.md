# 系统初始化流程

## 📋 目录

1. [init进程的作用](#1-init进程的作用)
2. [rc文件解析](#2-rc文件解析)
3. [服务启动顺序](#3-服务启动顺序)
4. [分区在初始化中的角色](#4-分区在初始化中的角色)

---

## 1. init进程的作用

init进程是Android系统的第一个用户空间进程（PID 1），负责：

1. 解析init.rc脚本
2. 创建文件系统目录
3. 挂载分区
4. 启动系统服务
5. 管理进程生命周期

---

## 2. rc文件解析

### 2.1 rc文件位置

- `system/core/rootdir/init.rc` - 主init脚本
- `device/{vendor}/{device}/init.{device}.rc` - 设备特定脚本
- `vendor/etc/init/` - 供应商init脚本

### 2.2 rc文件语法

```
# 服务定义
service servicename /path/to/binary
    class core
    user root
    group root
    oneshot

# 动作
on early-init
    mount system /system
    mount vendor /vendor
```

---

## 3. 服务启动顺序

1. **early-init**：早期初始化
2. **init**：基本初始化
3. **early-fs**：早期文件系统
4. **fs**：文件系统
5. **post-fs**：文件系统后
6. **post-fs-data**：数据分区后
7. **early-boot**：早期启动
8. **boot**：启动

---

## 4. 分区在初始化中的角色

- **早期阶段**：挂载system, vendor等只读分区
- **后期阶段**：挂载userdata等读写分区
- **服务启动**：从system分区加载系统服务

---

## 总结

系统初始化流程要点：

1. **init进程**：第一个用户空间进程
2. **rc文件**：定义初始化步骤
3. **服务启动**：按阶段顺序启动
4. **分区挂载**：在初始化过程中挂载

**下一步学习**：
- 了解OTA更新，请阅读 [OTA更新机制](../04_Dynamic_Updates/01_OTA_Update_Mechanism.md)
