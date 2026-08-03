# Init.rc 完整指南

## 目录
1. [简介](#简介)
2. [历史与发展](#历史与发展)
3. [基本概念](#基本概念)
4. [语法详解](#语法详解)
5. [常用指令](#常用指令)
6. [服务管理](#服务管理)
7. [属性系统](#属性系统)
8. [触发器机制](#触发器机制)
9. [适用场景](#适用场景)
10. [实战案例](#实战案例)
11. [最佳实践](#最佳实践)
12. [常见问题](#常见问题)

---

## 简介

`init.rc` 是 Android 系统的初始化脚本文件，由 `init` 进程（PID 1）解析和执行。它是 Android 系统启动过程中最重要的配置文件之一，负责：

- 创建和挂载文件系统
- 启动系统服务
- 设置系统属性
- 配置权限和 SELinux 上下文
- 响应系统事件（如设备插入、属性变化等）

### 核心特点
- **声明式语法**：使用简单的声明式语法描述系统配置
- **事件驱动**：基于触发器的响应机制
- **服务管理**：统一管理所有系统服务的生命周期
- **属性集成**：与 Android 属性系统深度集成

---

## 历史与发展

### Android 1.0 - 早期版本（2008-2010）

**起源**
- Android 基于 Linux 内核，但需要自己的初始化系统
- 参考了 Linux 的 `init` 系统，但针对移动设备进行了优化
- 最初的 `init.rc` 语法相对简单，主要关注服务启动和文件系统挂载

**特点**
- 基本的服务启动和停止
- 简单的文件系统操作
- 基本的权限设置

### Android 2.0 - 属性系统集成（2010-2012）

**改进**
- 引入 Android 属性系统（property system）
- 支持属性触发器和条件执行
- 增强的服务管理功能

**语法扩展**
```rc
# 属性触发器
on property:sys.boot_completed=1
    start my_service
```

### Android 4.0+ - SELinux 支持（2012-2014）

**重大变化**
- 引入 SELinux 安全上下文设置
- 增强的权限控制
- 更细粒度的安全策略

**新增语法**
```rc
# SELinux 上下文
service my_service /system/bin/my_service
    class main
    seclabel u:r:my_service:s0
```

### Android 5.0+ - 系统化改进（2014-2016）

**改进**
- 模块化的 init.rc 文件组织
- 支持多个 init 文件（init.rc, init.${ro.hardware}.rc 等）
- 改进的错误处理和日志记录

**文件组织**
```
/system/etc/init/
├── init.rc                    # 主配置文件
├── init.${ro.hardware}.rc    # 硬件特定配置
└── init.${ro.product.name}.rc # 产品特定配置
```

### Android 7.0+ - 现代 init 系统（2016-2018）

**重大重构**
- 引入 `init` 进程的 C++ 重写版本
- 支持更复杂的条件逻辑
- 改进的性能和可维护性
- 支持命名空间和 cgroup

**新特性**
```rc
# 命名空间支持
service my_service /system/bin/my_service
    namespace default
    user system
    group system
```

### Android 8.0+ - Treble 架构（2018-至今）

**架构变化**
- Android Treble 架构引入
- 分离系统分区和供应商分区
- 供应商特定的 init 文件（`/vendor/etc/init/`）
- 更严格的接口定义

**文件分布**
```
/system/etc/init/     # 系统 init 文件
/vendor/etc/init/     # 供应商 init 文件
/odm/etc/init/        # ODM init 文件（Android 10+）
/product/etc/init/    # 产品 init 文件（Android 10+）
```

### Android 11+ - 最新发展（2020-至今）

**持续改进**
- 更好的模块化支持
- 增强的调试工具
- 改进的错误报告
- 支持更复杂的服务依赖关系

---

## 基本概念

### 1. Init 进程

`init` 进程是 Android 系统中第一个用户空间进程（PID 1），负责：
- 解析和执行 init.rc 文件
- 管理系统服务的生命周期
- 处理系统属性和事件
- 响应硬件事件（如 USB 插入）

### 2. Init.rc 文件位置

**主要位置**
```
/system/etc/init/init.rc              # 主配置文件
/vendor/etc/init/                     # 供应商特定配置
/odm/etc/init/                        # ODM 特定配置
/product/etc/init/                    # 产品特定配置
```

**加载顺序**
1. `/system/etc/init/init.rc`
2. `/vendor/etc/init/*.rc`
3. `/odm/etc/init/*.rc`
4. `/product/etc/init/*.rc`

### 3. 文件结构

```rc
# 注释以 # 开头

# 导入其他文件
import /vendor/etc/init/vendor.rc

# 动作（Action）
on early-init
    # 命令

# 服务（Service）
service myservice /system/bin/myservice
    # 选项

# 属性触发器
on property:sys.boot_completed=1
    # 命令
```

---

## 语法详解

### 1. 注释

```rc
# 这是单行注释
# 注释可以出现在任何地方
```

### 2. 导入语句

```rc
# 导入其他 init 文件
import /vendor/etc/init/vendor.rc
import /system/etc/init/hw/init.${ro.hardware}.rc
```

**说明**
- 支持条件导入（Android 7.0+）
- 导入的文件会被解析并合并
- 后导入的文件可以覆盖先导入的配置

### 3. 动作（Action）

动作是一组命令的集合，在特定条件下执行。

**语法**
```rc
on <trigger>
    <command>
    <command>
    ...
```

**示例**
```rc
on early-init
    mkdir /dev/socket 0775 root system
    mkdir /dev/block 0755 root root

on init
    symlink /system/bin /bin
    symlink /system/etc /etc
```

### 4. 服务（Service）

服务定义了一个可执行程序及其运行方式。

**基本语法**
```rc
service <name> <pathname> [ <argument> ]*
    <option>
    <option>
    ...
```

**示例**
```rc
service zygote /system/bin/app_process64 -Xzygote /system/bin --zygote --start-system-server
    class main
    priority -20
    user root
    group root readproc
    socket zygote stream 660 root system
    onrestart write /sys/power/state on
    onrestart restart audioserver
    writepid /dev/cpuset/foreground/tasks
```

### 5. 命令（Command）

命令是动作中执行的具体操作。

**常用命令类型**
- 文件系统操作：`mkdir`, `mount`, `symlink`, `chmod`, `chown`
- 服务操作：`start`, `stop`, `restart`
- 属性操作：`setprop`, `getprop`, `write`
- 执行程序：`exec`, `exec_start`
- 条件判断：`if`, `ifelse`

---

## 常用指令

### 文件系统操作

#### mkdir - 创建目录
```rc
mkdir <path> [mode] [owner] [group]
```
**示例**
```rc
mkdir /data/app 0755 system system
mkdir /cache 0770 system cache
```

#### mount - 挂载文件系统
```rc
mount <type> <device> <dir> [ <option> ]*
```
**示例**
```rc
mount tmpfs tmpfs /dev
mount ext4 /dev/block/platform/soc/1da4000.ufshc/by-name/system /system ro
```

#### symlink - 创建符号链接
```rc
symlink <target> <link_name>
```
**示例**
```rc
symlink /system/bin /bin
symlink /system/lib64 /lib64
```

#### chmod/chown - 修改权限和所有者
```rc
chmod <octal-mode> <path>
chown <owner> <group> <path>
```
**示例**
```rc
chmod 0644 /system/build.prop
chown root system /system/bin/app_process
```

### 服务操作

#### start - 启动服务
```rc
start <service_name>
```
**示例**
```rc
on boot
    start servicemanager
    start surfaceflinger
```

#### stop - 停止服务
```rc
stop <service_name>
```
**示例**
```rc
on property:sys.shutdown.requested=1
    stop zygote
    stop surfaceflinger
```

#### restart - 重启服务
```rc
restart <service_name>
```
**示例**
```rc
on property:sys.boot_completed=1
    restart my_service
```

### 属性操作

#### setprop - 设置属性
```rc
setprop <name> <value>
```
**示例**
```rc
on early-init
    setprop ro.boottime.init 1
    setprop sys.usb.config none
```

#### getprop - 获取属性（用于条件判断）
```rc
# 在 if 语句中使用
if [ "$(getprop ro.debuggable)" = "1" ]
    start adbd
endif
```

#### write - 写入文件
```rc
write <path> <content>
```
**示例**
```rc
on early-init
    write /proc/sys/kernel/panic_on_oops 1
    write /sys/class/android_usb/android0/enable 0
```

### 条件判断

#### if/else/endif
```rc
if <condition>
    <command>
else
    <command>
endif
```
**示例**
```rc
on boot
    if [ "$(getprop ro.debuggable)" = "1" ]
        start adbd
    else
        stop adbd
    endif
```

### 执行程序

#### exec - 执行命令（阻塞）
```rc
exec [ <path> ]* <command>
```
**示例**
```rc
on early-init
    exec /system/bin/init_first_stage
```

#### exec_start - 启动后台进程
```rc
exec_start <service_name>
```
**示例**
```rc
on boot
    exec_start my_script_service
```

---

## 服务管理

### 服务选项

#### class - 服务类
```rc
class <name>
```
**说明**
- 将服务分组到类中
- 可以使用 `start class_name` 启动整个类
- 常用类：`main`, `core`, `late_start`

**示例**
```rc
service zygote /system/bin/app_process64
    class main
```

#### user/group - 运行用户和组
```rc
user <username>
group <groupname> [ <groupname> ]*
```
**示例**
```rc
service system_server /system/bin/app_process64
    user system
    group system readproc
```

#### oneshot - 一次性服务
```rc
oneshot
```
**说明**
- 服务退出后不会自动重启
- 适用于脚本或一次性任务

**示例**
```rc
service preinstall /system/bin/preinstall.sh
    class main
    oneshot
```

#### disabled - 禁用服务
```rc
disabled
```
**说明**
- 服务不会自动启动
- 需要手动使用 `start` 命令启动

**示例**
```rc
service adbd /system/bin/adbd
    class core
    disabled
```

#### critical - 关键服务
```rc
critical
```
**说明**
- 如果服务在 4 分钟内退出超过 4 次，系统会重启到恢复模式

**示例**
```rc
service surfaceflinger /system/bin/surfaceflinger
    class core
    critical
```

#### seclabel - SELinux 上下文
```rc
seclabel <context>
```
**示例**
```rc
service my_service /system/bin/my_service
    seclabel u:r:my_service:s0
```

#### socket - 创建 Unix 域套接字
```rc
socket <name> <type> <perm> [ <user> [ <group> ] ]
```
**类型**
- `stream` - TCP 风格
- `dgram` - UDP 风格
- `seqpacket` - 有序数据包

**示例**
```rc
service zygote /system/bin/app_process64
    socket zygote stream 660 root system
```

#### onrestart - 服务重启时执行
```rc
onrestart <command>
```
**示例**
```rc
service zygote /system/bin/app_process64
    onrestart write /sys/power/state on
    onrestart restart audioserver
```

#### writepid - 写入进程 ID
```rc
writepid <file> [ <file> ]*
```
**示例**
```rc
service zygote /system/bin/app_process64
    writepid /dev/cpuset/foreground/tasks
```

#### priority - 进程优先级
```rc
priority <priority>
```
**说明**
- 设置进程的 nice 值
- 范围：-20（最高）到 19（最低）

**示例**
```rc
service zygote /system/bin/app_process64
    priority -20
```

---

## 属性系统

### 属性触发器

属性触发器允许在属性值改变时执行命令。

**语法**
```rc
on property:<name>=<value>
    <command>
```

**示例**
```rc
# 当系统启动完成时
on property:sys.boot_completed=1
    start my_service
    setprop my.property ready

# 当 USB 配置改变时
on property:sys.usb.config=*
    stop adbd
    start adbd
```

### 常用系统属性

#### 启动相关
```rc
ro.boottime.*          # 启动时间戳
sys.boot_completed     # 启动完成标志
sys.shutdown.requested # 关机请求
```

#### USB 相关
```rc
sys.usb.config         # USB 配置
sys.usb.state          # USB 状态
persist.vendor.usb.config # 持久化 USB 配置
```

#### 调试相关
```rc
ro.debuggable          # 是否可调试
ro.secure              # 是否安全模式
persist.sys.usb.config # 持久化 USB 配置
```

### 属性操作命令

```rc
# 设置属性
setprop <name> <value>

# 在条件中使用
if [ "$(getprop <name>)" = "<value>" ]
    # 命令
endif
```

---

## 触发器机制

### 内置触发器

#### 启动阶段触发器
```rc
on early-init      # 最早阶段，初始化基本环境
on init            # 初始化阶段，设置文件系统
on late-init       # 后期初始化，启动服务
on post-fs         # 文件系统挂载后
on post-fs-data    # 数据分区挂载后
on boot            # 系统启动时
```

#### 文件系统触发器
```rc
on fs              # 文件系统相关
on post-fs         # 文件系统挂载后
on post-fs-data    # 数据分区挂载后
```

#### 属性触发器
```rc
on property:<name>=<value>  # 属性值等于指定值
on property:<name>=*        # 属性值改变（任意值）
```

#### 设备触发器
```rc
on device-added-<path>      # 设备添加
on device-removed-<path>    # 设备移除
```

### 触发器执行顺序

```
1. early-init
2. init
3. late-init
   ├── on post-fs
   ├── on post-fs-data
   └── on boot
4. 属性触发器（根据属性变化触发）
5. 设备触发器（根据设备事件触发）
```

### 自定义触发器

```rc
# 触发自定义事件
trigger my_custom_trigger

# 响应自定义事件
on my_custom_trigger
    start my_service
```

---

## 适用场景

### 1. 系统服务启动

**场景描述**
启动系统核心服务，如 Zygote、SystemServer、SurfaceFlinger 等。

**示例**
```rc
on boot
    # 启动核心服务
    start servicemanager
    start hwservicemanager
    start vndservicemanager
    
    # 启动 Zygote
    start zygote
    start zygote_secondary
    
    # 启动图形服务
    start surfaceflinger
```

### 2. 文件系统初始化

**场景描述**
创建必要的目录结构，设置权限，挂载文件系统。

**示例**
```rc
on early-init
    # 创建基本目录
    mkdir /dev/socket 0775 root system
    mkdir /dev/block 0755 root root
    mkdir /data 0771 system system
    mkdir /cache 0770 system cache
    
    # 挂载文件系统
    mount tmpfs tmpfs /dev mode=0755
    mount tmpfs tmpfs /mnt mode=0755 noexec nosuid nodev
```

### 3. 权限和 SELinux 配置

**场景描述**
设置文件权限、所有者和 SELinux 上下文。

**示例**
```rc
on init
    # 设置权限
    chmod 0644 /system/build.prop
    chown root system /system/bin/app_process
    
    # 设置 SELinux 上下文
    restorecon_recursive /system
    restorecon /data
```

### 4. 系统属性初始化

**场景描述**
设置系统属性，配置系统行为。

**示例**
```rc
on early-init
    # 设置启动时间
    setprop ro.boottime.init $(date +%s)
    
    # 设置 USB 配置
    setprop sys.usb.config none
    
    # 设置调试标志
    if [ "$(getprop ro.debuggable)" = "1" ]
        setprop persist.sys.usb.config adb
    endif
```

### 5. 条件启动服务

**场景描述**
根据系统状态或属性值决定是否启动服务。

**示例**
```rc
# 调试模式下启动 ADB
on property:ro.debuggable=1
    start adbd

# 启动完成后启动应用服务
on property:sys.boot_completed=1
    start my_app_service
```

### 6. 响应硬件事件

**场景描述**
响应 USB 插入、设备添加等硬件事件。

**示例**
```rc
# USB 配置改变
on property:sys.usb.config=*
    stop adbd
    start adbd

# 设备添加
on device-added-/dev/block/mmcblk0
    mount ext4 /dev/block/mmcblk0 /mnt/sdcard
```

### 7. 服务依赖管理

**场景描述**
管理服务之间的启动顺序和依赖关系。

**示例**
```rc
# 先启动基础服务
on boot
    start servicemanager
    start hwservicemanager

# 然后启动依赖服务
on property:init.svc.servicemanager=running
    start system_server
```

### 8. 系统恢复和重启

**场景描述**
处理系统崩溃、服务异常退出等情况。

**示例**
```rc
# 关键服务退出时重启
service surfaceflinger /system/bin/surfaceflinger
    class core
    critical
    onrestart restart zygote

# 系统关机处理
on property:sys.shutdown.requested=1
    stop zygote
    stop surfaceflinger
    umount /data
```

### 9. 性能调优

**场景描述**
设置 CPU 调度、内存管理、I/O 调度等参数。

**示例**
```rc
on boot
    # 设置 CPU 调度参数
    write /proc/sys/kernel/sched_latency_ns 10000000
    write /proc/sys/kernel/sched_min_granularity_ns 1000000
    
    # 设置内存参数
    write /proc/sys/vm/swappiness 60
    write /proc/sys/vm/dirty_ratio 15
```

### 10. 安全加固

**场景描述**
配置 SELinux 策略、设置安全参数。

**示例**
```rc
on early-init
    # 启用 SELinux
    setenforce 1
    
    # 设置安全参数
    write /proc/sys/kernel/dmesg_restrict 1
    write /proc/sys/kernel/kptr_restrict 2
```

---

## 实战案例

### 案例1：添加自定义系统服务

**需求**
添加一个自定义的后台服务，在系统启动时自动运行。

**实现**
```rc
# /vendor/etc/init/my_service.rc

service my_service /vendor/bin/my_service
    class main
    user system
    group system
    seclabel u:r:my_service:s0
    oneshot
    disabled

on property:sys.boot_completed=1
    start my_service
```

### 案例2：USB 调试自动启用

**需求**
在开发版本中自动启用 USB 调试。

**实现**
```rc
on early-init
    if [ "$(getprop ro.debuggable)" = "1" ]
        setprop persist.vendor.usb.config adb
        setprop sys.usb.config adb
    endif

on property:sys.usb.config=adb
    start adbd
```

### 案例3：动态挂载外部存储

**需求**
当 SD 卡插入时自动挂载。

**实现**
```rc
on device-added-/dev/block/mmcblk1p1
    mkdir /mnt/sdcard 0775 system sdcard_rw
    mount vfat /dev/block/mmcblk1p1 /mnt/sdcard
    setprop sys.sdcard.mounted 1

on device-removed-/dev/block/mmcblk1p1
    umount /mnt/sdcard
    setprop sys.sdcard.mounted 0
```

### 案例4：服务健康检查

**需求**
监控关键服务，如果频繁崩溃则重启系统。

**实现**
```rc
service critical_service /system/bin/critical_service
    class core
    critical
    restart
    onrestart write /sys/class/leds/status/brightness 1
```

### 案例5：性能监控服务

**需求**
启动性能监控服务，记录系统性能数据。

**实现**
```rc
service perfmon /system/bin/perfmon
    class late_start
    user system
    group system
    disabled

on property:sys.boot_completed=1
    start perfmon

on property:sys.perfmon.enable=1
    start perfmon

on property:sys.perfmon.enable=0
    stop perfmon
```

### 案例6：条件启动服务

**需求**
根据设备类型启动不同的服务。

**实现**
```rc
on boot
    if [ "$(getprop ro.product.device)" = "tablet" ]
        start tablet_service
    else
        start phone_service
    endif
```

---

## 最佳实践

### 1. 文件组织

**推荐结构**
```
/system/etc/init/
├── init.rc                    # 主配置文件
├── init.${ro.hardware}.rc    # 硬件特定
└── init.${ro.product.name}.rc # 产品特定

/vendor/etc/init/
├── vendor.rc                  # 供应商主配置
├── hw/                        # 硬件相关
└── *.rc                       # 各模块配置
```

**原则**
- 按功能模块拆分文件
- 硬件特定配置放在单独文件
- 避免在单个文件中堆积过多配置

### 2. 服务定义

**推荐做法**
```rc
service my_service /vendor/bin/my_service
    class main
    user system
    group system
    seclabel u:r:my_service:s0
    socket my_service stream 660 system system
    onrestart restart dependent_service
```

**注意事项**
- 明确指定运行用户和组
- 设置正确的 SELinux 上下文
- 使用 socket 进行进程间通信
- 处理服务重启时的依赖关系

### 3. 错误处理

**推荐做法**
```rc
# 使用 critical 标记关键服务
service critical_service /system/bin/critical_service
    class core
    critical

# 使用 onrestart 处理服务重启
service my_service /system/bin/my_service
    onrestart write /sys/kernel/debug/my_service/restart 1
    onrestart restart dependent_service
```

### 4. 性能优化

**推荐做法**
```rc
# 使用 oneshot 避免不必要的服务保持运行
service init_script /system/bin/init_script.sh
    class main
    oneshot

# 延迟启动非关键服务
on property:sys.boot_completed=1
    start non_critical_service
```

### 5. 安全性

**推荐做法**
```rc
# 使用最小权限原则
service my_service /system/bin/my_service
    user system
    group system
    capabilities NET_BIND_SERVICE

# 设置正确的 SELinux 上下文
service my_service /system/bin/my_service
    seclabel u:r:my_service:s0
```

### 6. 调试和日志

**推荐做法**
```rc
# 添加调试服务（仅在调试版本）
on property:ro.debuggable=1
    start debug_service

# 记录服务状态
service my_service /system/bin/my_service
    onrestart write /data/my_service_restart.log "$(date)"
```

---

## 常见问题

### Q1: 如何查看 init.rc 文件？

**方法1：从设备提取**
```bash
adb pull /system/etc/init/init.rc
adb pull /vendor/etc/init/
```

**方法2：从源码查看**
```bash
# AOSP 源码中
system/core/rootdir/init.rc
device/*/init*.rc
```

### Q2: 如何调试 init.rc 问题？

**查看 init 日志**
```bash
adb logcat -b all | grep init
```

**查看服务状态**
```bash
adb shell getprop | grep init.svc
```

**手动测试服务**
```bash
adb shell start my_service
adb shell stop my_service
```

### Q3: 服务无法启动怎么办？

**检查步骤**
1. 检查服务文件是否存在
2. 检查权限是否正确
3. 检查 SELinux 上下文
4. 查看 init 日志
5. 检查服务依赖是否满足

**调试命令**
```bash
# 查看服务状态
adb shell getprop init.svc.my_service

# 查看服务日志
adb logcat | grep my_service

# 手动启动测试
adb shell /system/bin/my_service
```

### Q4: 如何添加新的 init.rc 文件？

**步骤**
1. 创建 init 文件（如 `/vendor/etc/init/my_service.rc`）
2. 确保文件权限正确（644）
3. 确保 SELinux 上下文正确
4. 在构建系统中包含该文件
5. 重新编译和刷机

### Q5: 属性触发器不工作？

**可能原因**
1. 属性名称拼写错误
2. 属性值格式不匹配
3. 触发器定义位置错误
4. 属性设置时机问题

**解决方法**
```bash
# 检查属性值
adb shell getprop sys.boot_completed

# 手动设置属性测试
adb shell setprop test.property test_value

# 查看 init 日志
adb logcat -b all | grep init
```

### Q6: 如何修改系统 init.rc？

**注意事项**
- 系统 init.rc 在 `/system` 分区，需要 root 权限
- 修改后需要重新挂载为可写
- 建议在供应商分区添加自定义配置

**推荐方法**
```rc
# 在 /vendor/etc/init/my.rc 中添加
import /vendor/etc/init/my.rc

# 覆盖或扩展系统配置
on boot
    # 自定义启动逻辑
    start my_service
```

### Q7: SELinux 相关问题？

**常见错误**
```
avc: denied { execute } for pid=xxx comm="init" name="my_service"
```

**解决方法**
1. 检查 SELinux 策略文件
2. 添加相应的 allow 规则
3. 设置正确的 seclabel

### Q8: 服务启动顺序问题？

**解决方法**
```rc
# 使用属性触发器确保顺序
on property:init.svc.service1=running
    start service2

# 使用 class 分组
service service1 /system/bin/service1
    class main

service service2 /system/bin/service2
    class main
    # service1 和 service2 会在 boot 阶段一起启动
```

---

## 调试工具

### 1. Init 日志

```bash
# 查看所有 init 相关日志
adb logcat -b all | grep init

# 查看服务启动日志
adb logcat | grep "init.*service"
```

### 2. 属性查看

```bash
# 查看所有属性
adb shell getprop

# 查看服务状态属性
adb shell getprop | grep init.svc

# 查看特定属性
adb shell getprop sys.boot_completed
```

### 3. 服务控制

```bash
# 启动服务
adb shell start <service_name>

# 停止服务
adb shell stop <service_name>

# 重启服务
adb shell restart <service_name>
```

### 4. Init 解析测试

```bash
# 在设备上测试 init 文件语法
adb shell init --help

# 查看 init 版本
adb shell getprop ro.build.version.incremental
```

---

## 总结

`init.rc` 是 Android 系统初始化的核心配置文件，掌握其语法和使用方法对于：

- **系统定制**：添加自定义服务和配置
- **问题调试**：理解系统启动流程
- **性能优化**：优化服务启动顺序
- **安全加固**：配置 SELinux 和权限

### 关键要点

1. **语法简洁**：声明式语法，易于理解
2. **事件驱动**：基于触发器的响应机制
3. **模块化**：支持多文件组织
4. **与属性系统集成**：深度集成 Android 属性系统
5. **服务管理**：统一管理所有系统服务

### 学习路径

1. 理解基本语法和概念
2. 学习常用命令和选项
3. 掌握触发器和属性系统
4. 实践添加自定义服务
5. 深入理解系统启动流程

---

## 参考资源

- [Android 源码 - Init 系统](https://android.googlesource.com/platform/system/core/+/master/init/)
- [Android 官方文档 - Init 语言](https://android.googlesource.com/platform/system/core/+/master/init/README.md)
- [SELinux for Android](https://source.android.com/security/selinux)
- [Android 属性系统](https://source.android.com/devices/tech/config/props)

---

*最后更新：2026-01-28*
