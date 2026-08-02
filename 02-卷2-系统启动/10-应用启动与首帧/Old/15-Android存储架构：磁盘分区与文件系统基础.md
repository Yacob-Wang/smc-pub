# Android 存储架构：磁盘分区与文件系统基础

## 学习目标

- 理解 `adb shell ls` 看到的内容来源（内存 vs 磁盘）
- 掌握 Linux/Android 文件系统缓存机制
- 理解 Android 分区与 Windows 盘符的类比关系
- 了解磁盘分区的基本原理和划分方式
- 理解文件系统挂载与内存缓存的关系

## 背景介绍

在使用 `adb shell` 连接 Android 设备时，很多开发者会对看到的内容产生疑问：这些文件是存储在内存中还是磁盘中？它们与 Windows 的 C/D/E/F 盘符有什么关系？理解这些基础概念对于深入理解 Android 系统架构至关重要。

## 核心概念

### 问题一：adb shell ls 看到的是内存还是磁盘？

#### 答案：主要是磁盘内容，通过文件系统缓存访问

**核心要点**：

1. **文件存储在磁盘（Flash 存储）上**
   - Android 设备使用 eMMC、UFS 等 Flash 存储作为持久化存储
   - 所有文件（包括 `/system`、`/vendor`、`/data` 等）都存储在 Flash 存储的分区中
   - 这些分区在系统启动时被挂载到文件系统树中

2. **通过文件系统缓存访问**
   - 当执行 `ls` 命令时，内核的文件系统缓存（Page Cache）会缓存最近访问的文件和目录信息
   - 如果数据在缓存中，直接从内存读取（快速）
   - 如果数据不在缓存中，从磁盘读取并更新缓存（较慢）

3. **目录结构在内存中组织**
   - 文件系统的目录树结构由内核的 VFS（Virtual File System）在内存中维护
   - 但实际的文件内容存储在磁盘上
   - 目录项（dentry）和 inode 信息会被缓存到内存中

#### 详细解释

**文件存储位置**：

```
物理存储（Flash 芯片）
    ↓
分区（system, vendor, data 等）
    ↓
文件系统（ext4, f2fs, erofs）
    ↓
挂载到文件系统树（/system, /vendor, /data）
    ↓
通过 VFS 访问（ls, cat 等命令）
    ↓
文件系统缓存（Page Cache）
    ↓
用户看到的内容
```

**实际示例**：

```bash
# 查看文件系统挂载信息
adb shell mount | grep system
# 输出示例：
# /dev/block/by-name/system on /system type ext4 (ro,seclabel,relatime)

# 查看文件系统缓存统计
adb shell cat /proc/meminfo | grep -i cache
# 输出示例：
# Cached:           1234567 kB    # 文件系统缓存大小
```

**关键理解**：

- **文件内容在磁盘**：`/system/bin/ls` 这个文件本身存储在 Flash 存储的 system 分区中
- **访问通过缓存**：当你执行 `ls` 时，如果这个文件最近被访问过，会从内存缓存中读取
- **目录信息被缓存**：`ls` 命令显示的目录列表信息会被内核缓存，提高访问速度
- **修改会写回磁盘**：对于可写分区（如 `/data`），修改会先写入缓存，然后异步写回磁盘

### 问题二：是否类似于 Windows 的磁盘交换机制？

#### 答案：有相似之处，但机制不同

**相似之处**：

1. **文件系统缓存机制**
   - Windows 和 Linux/Android 都使用文件系统缓存
   - 最近访问的文件会被缓存在内存中
   - 提高文件访问性能

2. **按需加载**
   - 文件内容不会全部加载到内存
   - 只有在访问时才从磁盘读取
   - 内存不足时会释放缓存

**不同之处**：

1. **Windows 的虚拟内存交换（Swap）**
   - Windows 使用页面文件（pagefile.sys）作为虚拟内存
   - 当物理内存不足时，将内存页面交换到磁盘
   - 这是**内存管理**层面的机制

2. **Android/Linux 的文件系统缓存**
   - Android 使用 Page Cache 缓存文件内容
   - 这是**文件系统**层面的机制
   - 主要用于提高文件 I/O 性能

3. **Android 通常不使用 Swap**
   - 大多数 Android 设备不使用传统的 Swap 分区
   - 使用更激进的 OOM（Out of Memory）机制
   - 直接杀死进程而不是交换到磁盘

#### 详细对比

**Windows 机制**：

```
应用程序内存
    ↓
物理内存（RAM）
    ↓（内存不足时）
虚拟内存（页面文件 pagefile.sys 在 C: 盘）
    ↓
磁盘存储
```

**Android/Linux 机制**：

```
文件访问请求
    ↓
文件系统缓存（Page Cache）
    ↓（缓存命中）
直接从内存读取
    ↓（缓存未命中）
从磁盘读取 → 更新缓存
    ↓
磁盘存储（Flash）
```

**关键区别**：

| 特性 | Windows 虚拟内存 | Android 文件系统缓存 |
|------|-----------------|---------------------|
| 目的 | 扩展可用内存空间 | 提高文件访问性能 |
| 交换内容 | 进程内存页面 | 文件数据块 |
| 触发条件 | 物理内存不足 | 文件访问请求 |
| 性能影响 | 可能显著降低性能 | 通常提高性能 |
| 存储位置 | 页面文件（C: 盘） | 原始文件所在分区 |

**实际验证**：

```bash
# 查看 Android 设备的内存使用情况
adb shell cat /proc/meminfo

# 查看文件系统缓存大小
adb shell cat /proc/meminfo | grep Cached
# Cached: 表示文件系统缓存的大小

# 查看是否有 Swap
adb shell cat /proc/meminfo | grep Swap
# 大多数 Android 设备 SwapTotal: 0 kB（没有 Swap）
```

### 问题三：分区是否类似于 Windows 的 C/D/E/F 盘符？

#### 答案：概念相似，但实现和用途不同

**相似之处**：

1. **都是存储空间的逻辑划分**
   - Windows 的 C:、D:、E:、F: 是逻辑分区
   - Android 的 system、vendor、data 等也是逻辑分区
   - 都是将一块物理存储设备划分为多个逻辑区域

2. **都有特定的用途**
   - Windows C: 盘通常用于系统和程序
   - Android system 分区用于系统框架
   - 都有明确的用途划分

**不同之处**：

1. **挂载方式不同**
   - **Windows**：每个分区挂载为独立的根（C:\、D:\、E:\）
   - **Android**：所有分区挂载到统一的文件系统树（/system、/vendor、/data）

2. **可见性不同**
   - **Windows**：用户可以直接看到和使用所有盘符
   - **Android**：用户通常只能看到 /data 分区的一部分（通过 /sdcard）
   - 系统分区对用户不可见或只读

3. **分区用途更细分**
   - **Windows**：通常按用途划分（系统、程序、数据）
   - **Android**：按系统架构划分（system、vendor、product、odm 等）

#### 详细类比

**Windows 分区结构**：

```
物理磁盘
├── C: 盘（系统盘）
│   ├── Windows\        # 操作系统
│   ├── Program Files\  # 程序文件
│   └── Users\          # 用户数据
├── D: 盘（数据盘）
│   └── 用户文件
└── E: 盘（其他）
    └── 其他文件
```

**Android 分区结构**：

```
物理 Flash 存储
├── boot 分区
│   └── 内核和启动文件
├── system 分区 → 挂载到 /system
│   └── Android 系统框架
├── vendor 分区 → 挂载到 /vendor
│   └── 厂商实现
├── product 分区 → 挂载到 /product
│   └── 产品特定内容
└── userdata 分区 → 挂载到 /data
    └── 用户数据和应用
```

**关键区别总结**：

| 特性 | Windows 盘符 | Android 分区 |
|------|-------------|-------------|
| 挂载点 | C:\、D:\、E:\ | /system、/vendor、/data |
| 文件系统树 | 多个根 | 单一根（/） |
| 用户可见性 | 全部可见 | 部分可见 |
| 分区用途 | 按用途划分 | 按系统架构划分 |
| 分区数量 | 通常 2-4 个 | 通常 10+ 个 |
| 分区大小 | 用户可调整 | 构建时确定 |

#### 实际查看 Android 分区

```bash
# 查看所有分区
adb shell ls -la /dev/block/by-name/

# 输出示例：
# boot -> /dev/block/sda1
# system -> /dev/block/sda2
# vendor -> /dev/block/sda3
# userdata -> /dev/block/sda4
# ...

# 查看分区挂载情况
adb shell mount

# 输出示例：
# /dev/block/by-name/system on /system type ext4 (ro,...)
# /dev/block/by-name/vendor on /vendor type ext4 (ro,...)
# /dev/block/by-name/userdata on /data type f2fs (rw,...)

# 查看分区大小
adb shell df -h

# 输出示例：
# Filesystem           Size  Used Avail Use% Mounted on
# /dev/block/.../system   2.0G  1.8G  200M  90% /system
# /dev/block/.../vendor   512M  400M  112M  78% /vendor
# /dev/block/.../userdata  32G   10G   22G  31% /data
```

### 磁盘分区划分原理

#### 分区表类型

**1. GPT（GUID Partition Table）** - 现代 Android 设备使用

- **特点**：
  - 支持最多 128 个分区（实际可更多）
  - 有备份分区表，更安全
  - 支持大于 2TB 的磁盘
  - 每个分区有唯一的 GUID

- **分区表位置**：
  - 主分区表：磁盘开头
  - 备份分区表：磁盘末尾

**2. MBR（Master Boot Record）** - 较老设备可能使用

- **特点**：
  - 最多 4 个主分区
  - 或 3 个主分区 + 1 个扩展分区
  - 扩展分区可包含多个逻辑分区
  - 限制较多，逐渐被 GPT 取代

#### 分区划分过程

**1. 物理存储设备**

```
┌─────────────────────────────────────┐
│     物理 Flash 存储芯片                │
│     (eMMC/UFS，例如 64GB)            │
└─────────────────────────────────────┘
```

**2. 创建分区表**

```
┌─────────────────────────────────────┐
│  GPT 分区表                          │
│  ┌─────────┬─────────┬─────────┐   │
│  │ boot    │ system  │ vendor  │   │
│  │ 64MB    │ 2GB     │ 512MB   │   │
│  └─────────┴─────────┴─────────┘   │
│  ... (更多分区)                      │
└─────────────────────────────────────┘
```

**3. 格式化分区**

```
boot 分区    → ext4 文件系统
system 分区  → ext4/erofs 文件系统
vendor 分区  → ext4/erofs 文件系统
userdata 分区 → f2fs 文件系统
```

**4. 系统启动时挂载**

```
boot 分区    → 由 Bootloader 读取
system 分区  → 挂载到 /system
vendor 分区  → 挂载到 /vendor
userdata 分区 → 挂载到 /data
```

#### 分区划分工具

**在开发阶段**（AOSP 构建）：

```bash
# 分区布局定义在 BoardConfig.mk 中
BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864      # 64MB
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 2147483648   # 2GB
BOARD_VENDORIMAGE_PARTITION_SIZE := 536870912   # 512MB
```

**在设备上查看**：

```bash
# 查看分区表
adb shell fdisk -l /dev/block/sda

# 查看分区信息
adb shell lsblk

# 查看分区详细信息
adb shell cat /proc/partitions
```

### 文件系统与内存的关系

#### 文件系统层次结构

```
应用层
    ↓
系统调用（open, read, write）
    ↓
VFS（虚拟文件系统层）
    ↓
具体文件系统（ext4, f2fs, erofs）
    ↓
块设备层（Block Device Layer）
    ↓
设备驱动（eMMC/UFS 驱动）
    ↓
物理存储（Flash 芯片）
```

#### 内存缓存机制

**1. Page Cache（页面缓存）**

- **作用**：缓存文件数据到内存
- **内容**：最近访问的文件页面
- **管理**：由内核统一管理
- **策略**：LRU（最近最少使用）算法

**2. Dentry Cache（目录项缓存）**

- **作用**：缓存目录项信息
- **内容**：路径名到 inode 的映射
- **优势**：快速路径查找

**3. Inode Cache（索引节点缓存）**

- **作用**：缓存文件元数据
- **内容**：文件属性、权限、大小等
- **优势**：减少磁盘访问

#### 缓存工作流程

**读取文件时**：

```
1. 应用请求读取文件
    ↓
2. VFS 查找文件（使用 dentry cache）
    ↓
3. 检查 Page Cache 是否有数据
    ├─ 有 → 直接从内存返回（快速）
    └─ 无 → 从磁盘读取 → 更新 Page Cache → 返回数据
```

**写入文件时**（可写分区）：

**默认情况（异步写入）**：

```
1. 应用调用 write() 系统调用
    ↓
2. 数据写入 Page Cache（快速，立即返回）
    ↓
3. 标记页面为"脏"（dirty）
    ↓
4. write() 系统调用返回成功（此时数据还在内存中）
    ↓
5. 后台异步写回磁盘（由内核线程完成，延迟几秒到几分钟）
```

**重要理解**：
- **write() 返回成功 ≠ 数据已写入磁盘**
- write() 返回只表示数据已写入内核的 Page Cache
- 真正的磁盘写入是异步的，由内核的 writeback 线程完成
- 如果系统崩溃，Page Cache 中的数据可能丢失

**同步写入（强制立即写入磁盘）**：

```
1. 应用调用 write() + fsync() 或使用 O_SYNC 标志
    ↓
2. 数据写入 Page Cache
    ↓
3. 立即触发同步写回磁盘（阻塞等待）
    ↓
4. 等待所有脏页面写入磁盘完成
    ↓
5. fsync() 返回成功（此时数据已真正写入磁盘）
```

**同步写入方法**：
- `fsync(fd)` - 同步文件的所有脏页面
- `fdatasync(fd)` - 只同步文件数据，不同步元数据（更快）
- `O_SYNC` 标志 - 每次 write() 都同步写入（性能较差）
- `O_DSYNC` 标志 - 每次 write() 只同步数据（类似 fdatasync）

**实际验证**：

```bash
# 查看文件系统缓存统计
adb shell cat /proc/meminfo

# 关键指标：
# Cached:       文件系统缓存大小
# Buffers:      缓冲区大小
# Dirty:        待写回的脏页面
# Writeback:    正在写回的页面

# 查看缓存命中率（需要内核支持）
adb shell cat /proc/sys/vm/vfs_cache_pressure
```

## 实际应用

### 验证文件存储位置

```bash
# 1. 查看文件所在分区
adb shell df /system/bin/ls
# 输出：/dev/block/.../system   2.0G  1.8G  200M  90% /system

# 2. 查看文件系统类型
adb shell mount | grep system
# 输出：/dev/block/by-name/system on /system type ext4 (ro,...)

# 3. 查看文件 inode 信息
adb shell ls -li /system/bin/ls
# 输出：12345 -rwxr-xr-x ... /system/bin/ls
# 12345 是 inode 号，存储在磁盘上
```

### 观察文件系统缓存

```bash
# 1. 查看当前缓存使用
adb shell cat /proc/meminfo | grep -E "Cached|Buffers|Dirty|Writeback"

# 关键指标说明：
# Cached:       文件系统缓存总大小
# Buffers:      缓冲区大小
# Dirty:        待写回的脏页面（已修改但未写入磁盘）
# Writeback:    正在写回的页面

# 2. 查看脏页面写回参数
adb shell cat /proc/sys/vm/dirty_ratio          # 脏页面占内存的最大比例（默认 20%）
adb shell cat /proc/sys/vm/dirty_background_ratio # 后台写回触发比例（默认 10%）
adb shell cat /proc/sys/vm/dirty_expire_centisecs # 脏页面过期时间（默认 3000，即30秒）

# 3. 清空缓存（需要 root）
adb shell sync  # 同步所有脏页面到磁盘（强制立即写回）
adb shell echo 3 > /proc/sys/vm/drop_caches  # 清空缓存

# 4. 再次查看缓存
adb shell cat /proc/meminfo | grep -E "Cached|Buffers|Dirty|Writeback"
# 缓存大小应该明显减少，Dirty 应该接近 0
```

### 验证异步写入机制

**测试异步写入**：

```bash
# 在设备上创建一个测试脚本
adb shell "cat > /data/local/tmp/test_async.sh << 'EOF'
#!/system/bin/sh
# 写入数据（异步）
echo 'test data' > /data/local/tmp/test.txt
echo 'Write completed'

# 查看脏页面（数据可能还在内存中）
cat /proc/meminfo | grep Dirty

# 等待几秒，观察脏页面变化
sleep 5
cat /proc/meminfo | grep Dirty

# 强制同步
sync
cat /proc/meminfo | grep Dirty
EOF"

adb shell chmod +x /data/local/tmp/test_async.sh
adb shell /data/local/tmp/test_async.sh
```

**C 代码示例（同步 vs 异步）**：

```c
// 异步写入（默认）
int fd = open("/data/test.txt", O_WRONLY | O_CREAT, 0644);
write(fd, "data", 4);  // 立即返回，数据在 Page Cache 中
close(fd);              // close() 不保证数据已写入磁盘！

// 同步写入方法 1：使用 fsync()
int fd = open("/data/test.txt", O_WRONLY | O_CREAT, 0644);
write(fd, "data", 4);
fsync(fd);              // 阻塞等待，直到数据真正写入磁盘
close(fd);

// 同步写入方法 2：使用 O_SYNC 标志（每次 write 都同步）
int fd = open("/data/test.txt", O_WRONLY | O_CREAT | O_SYNC, 0644);
write(fd, "data", 4);  // 阻塞等待，直到数据真正写入磁盘
close(fd);

// 同步写入方法 3：使用 fdatasync()（只同步数据，不同步元数据，更快）
int fd = open("/data/test.txt", O_WRONLY | O_CREAT, 0644);
write(fd, "data", 4);
fdatasync(fd);          // 只同步数据，不同步文件大小、时间戳等元数据
close(fd);
```

### 理解分区布局

```bash
# 1. 查看所有分区
adb shell ls -la /dev/block/by-name/

# 2. 查看分区大小
adb shell lsblk

# 3. 查看分区挂载
adb shell mount | grep -E "system|vendor|data|product"

# 4. 查看分区使用情况
adb shell df -h
```

### 对比 Windows 和 Android

**Windows 示例**：

```
C:\Windows\        → 系统文件
C:\Program Files\  → 程序文件
D:\Users\          → 用户数据（如果在 D: 盘）
```

**Android 对应**：

```
/system/           → 系统框架（类似 C:\Windows\）
/vendor/           → 厂商实现（类似 C:\Program Files\ 中的系统程序）
/data/             → 用户数据（类似 D:\Users\）
/data/app/         → 用户安装的应用（类似 C:\Program Files\ 中的用户程序）
```

## 总结

### 核心要点

1. **`adb shell ls` 看到的内容**：
   - 文件存储在磁盘（Flash）上
   - 通过文件系统缓存访问
   - 目录结构在内存中组织

2. **与 Windows 的相似性**：
   - 都使用文件系统缓存提高性能
   - 都有按需加载机制
   - 但 Android 通常不使用 Swap

3. **分区与 Windows 盘符**：
   - 概念相似：都是逻辑划分
   - 实现不同：Android 使用统一文件系统树
   - 用途不同：Android 分区更细分

4. **分区划分**：
   - 使用 GPT 分区表（现代设备）
   - 在构建时确定分区布局
   - 系统启动时挂载到文件系统树

### 关键概念

- **文件系统缓存**：提高文件访问性能
- **分区挂载**：将分区映射到文件系统树
- **统一文件系统树**：所有分区挂载到根 `/` 下
- **Page Cache**：内核的文件数据缓存机制

### 与 Windows 的对比总结

| 方面 | Windows | Android |
|------|---------|---------|
| 存储位置 | 磁盘（HDD/SSD） | Flash（eMMC/UFS） |
| 分区可见性 | 独立盘符（C:\、D:\） | 统一树（/system、/data） |
| 文件系统缓存 | 有（系统缓存） | 有（Page Cache） |
| 虚拟内存交换 | 有（页面文件） | 通常无（OOM 机制） |
| 分区数量 | 通常 2-4 个 | 通常 10+ 个 |
| 分区用途 | 按用途划分 | 按系统架构划分 |

### 后续学习

- [Android分区系统全解析](04-Android分区系统全解析.md) - 深入理解分区设计
- [文件系统类型与挂载机制](11-文件系统类型与挂载机制.md) - 理解文件系统类型
- [Android根目录结构详解](10-Android根目录结构详解.md) - 理解文件系统结构
- [分区与挂载点映射关系](06-分区与挂载点映射关系.md) - 理解挂载机制
- [文件描述符（File Descriptor）详解](16-文件描述符（File Descriptor）详解.md) - 理解文件描述符机制

## 参考资料

- [Linux 文件系统缓存](https://www.kernel.org/doc/html/latest/filesystems/vfs.html)
- [Android 分区架构](https://source.android.com/docs/core/architecture/partitions)
- [Page Cache 机制](https://www.kernel.org/doc/html/latest/admin-guide/mm/page_cache.html)
- [GPT 分区表](https://en.wikipedia.org/wiki/GUID_Partition_Table)

## 更新记录

- 2025-01-22：初始创建，详细解答三个核心问题：
  - adb shell ls 看到的内容来源（内存 vs 磁盘）
  - 文件系统缓存机制与 Windows 的对比
  - Android 分区与 Windows 盘符的类比关系
  - 磁盘分区划分原理和实际应用
