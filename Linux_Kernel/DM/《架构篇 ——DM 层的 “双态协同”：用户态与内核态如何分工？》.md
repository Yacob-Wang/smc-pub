# 第2篇：架构篇——DM层的“双态协同”：用户态与内核态如何分工？

在上一篇文章中，我们认识了Device Mapper（DM）是Linux/安卓存储栈中的“隐形骨架”，一个通用的块设备虚拟化框架。但一个框架的强大，不仅在于其核心思想，更在于其精妙的架构设计。

DM层采用了经典的**“用户态管理 + 内核态执行”**双态协同架构。这种设计将“复杂的配置与管理”放在用户态，将“高性能的IO数据处理”放在内核态，完美平衡了灵活性与效率。

本篇文章，我们将深入剖析DM层的内部架构，带你看清用户态工具（如`dmsetup`）是如何指挥内核态驱动（`dm-mod`）工作的，以及数据在这两层之间是如何流转的。

---

## 一、DM层整体架构：一张图看懂“双态协同”

DM层的架构可以清晰地划分为**用户态（User Space）**和**内核态（Kernel Space）**两大部分，它们通过一个特殊的字符设备进行通信。

```mermaid
graph TD
    subgraph 用户态 (User Space)
        A[高层管理工具] --> B[libdm 库]
        C[dmsetup 工具] --> B
        B --> D[ioctl 系统调用]
        
        A1[LVM2 (lvcreate/vgcreate)] --> A
        A2[cryptsetup (LUKS)] --> A
        A3[multipath-tools (多路径)] --> A
    end

    D --> E[/dev/mapper/control]

    subgraph 内核态 (Kernel Space)
        E --> F[DM 核心驱动 (dm-mod)]
        F --> G[Target 驱动管理器]
        F --> H[DM 设备管理器]
        F --> I[Bio/Request 处理器]
        
        G --> J[Target 驱动集合]
        J --> J1[linear]
        J --> J2[crypt]
        J --> J3[verity]
        J --> J4[snapshot]
        J --> J5[thin]
        
        H --> K[已创建的 DM 设备]
        K --> K1[/dev/dm-0]
        K --> K2[/dev/dm-1]
        
        I --> L[Block 层]
        L --> M[物理设备驱动]
    end

    style B fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style F fill:#ffecb3,stroke:#f57c00,stroke-width:2px
    style E fill:#bbdefb,stroke:#1976d2,stroke-width:2px
```

### 架构核心解读
1.  **用户态（大脑）**：负责“思考”和“指挥”。它不直接处理IO数据，而是负责配置DM设备的映射规则、管理设备的生命周期（创建/删除/暂停/恢复）。
2.  **内核态（手脚）**：负责“执行”和“干活”。它接收用户态的指令，创建对应的DM虚拟设备，并拦截、处理所有发往这些设备的IO请求（Bio/Request），按照映射规则将其转发到底层物理设备。
3.  **通信桥梁**：`/dev/mapper/control` 字符设备是连接用户态和内核态的唯一桥梁，通信协议是标准的`ioctl`命令。

---

## 二、用户态组件详解：DM层的“大脑”与“管家”

用户态组件的核心目标是**简化DM设备的管理**，为用户和高层应用提供友好的接口。

### 1. libdm：DM层的“灵魂库”
`libdm`（Device Mapper Library）是DM层用户态的核心库，几乎所有DM相关的工具（包括`dmsetup`）都基于它构建。
- **核心功能**：
    - 封装了与内核态DM驱动通信的所有`ioctl`命令。
    - 提供了一套高级API，用于创建设备、加载映射表、查询设备状态、监控设备事件等。
    - 负责解析用户输入的映射表文本，并将其转换为内核能够理解的二进制格式。
- **重要性**：`libdm`是用户态与内核态交互的“翻译官”和“信使”。没有它，用户需要直接构造复杂的`ioctl`命令来操作DM，这几乎是不可行的。

### 2. dmsetup：DM层的“瑞士军刀”
`dmsetup`是DM层最基础、最常用的命令行工具，直接面向终端用户。它是`libdm`的一个简单封装。
- **核心功能**：
    - **创建设备**：`dmsetup create <name> < <mapfile>`
    - **删除设备**：`dmsetup remove <name>`
    - **加载/更新映射表**：`dmsetup load <name> < <mapfile>` + `dmsetup resume <name>`
    - **查询设备信息**：`dmsetup info`, `dmsetup table`, `dmsetup status`
    - **监控设备事件**：`dmsetup monitor`
- **使用场景**：手动调试、编写自动化脚本、系统启动时的初始化脚本。

### 3. 高层管理工具：DM层的“应用程序”
除了`dmsetup`，还有许多更高级的工具基于`libdm`和DM框架实现了特定的存储解决方案。它们对用户更加友好，隐藏了底层DM的复杂细节。
- **LVM2**：逻辑卷管理工具集（`pvcreate`, `vgcreate`, `lvcreate`等）。它将多个物理磁盘抽象为卷组（VG），再从卷组中划分出逻辑卷（LV）。每个LV本质上就是一个DM设备。
- **cryptsetup**：Linux统一密钥设置（LUKS）工具。用于创建和管理加密的DM设备（基于`dm-crypt` Target）。
- **multipath-tools**：多路径IO管理工具。用于管理存储设备的多条访问路径（基于`dm-multipath` Target）。
- **安卓 init 进程**：安卓系统启动时，`init`进程会解析`fstab`文件中的DM配置项，自动创建动态分区、加密分区、verity校验分区等DM设备。

---

## 三、内核态组件详解：DM层的“心脏”与“手脚”

内核态组件是DM层的执行引擎，直接处理IO请求，性能至关重要。

### 1. DM核心驱动（dm-mod）：DM层的“心脏”
`dm-mod`是DM层的内核模块，是整个框架的中枢。它负责协调所有其他组件，处理用户态的请求，并管理DM设备的生命周期。
- **核心职责**：
    - **设备管理**：维护一个全局的DM设备链表，负责`mapped_device`结构体的分配、初始化和销毁。
    - **映射表管理**：负责接收用户态加载的映射表，解析并构建内核内部的`dm_table`结构。
    - **IO拦截与分发**：注册块设备驱动，拦截发往DM设备的Bio/Request，根据映射表将其分发给对应的Target驱动处理。
    - **用户态通信**：实现`/dev/mapper/control`字符设备的`file_operations`接口，处理用户态的`ioctl`命令。

### 2. Target驱动：DM层的“功能插件”
Target驱动是DM层实现具体存储功能的“插件”。每个Target驱动对应一种特定的IO处理逻辑。DM核心驱动本身不处理具体的IO，而是将IO转发给Target驱动。
- **常见Target驱动**：
    - **linear**：线性映射，将一个逻辑设备映射到一个或多个物理设备的连续区域。安卓动态分区的基础。
    - **crypt**：数据加密/解密，基于内核加密API。安卓FDE/FBE的基础。
    - **verity**：数据完整性校验，基于哈希树。安卓dm-verity的基础。
    - **snapshot**：写时复制（COW）快照。安卓虚拟A/B分区的基础。
    - **thin**：精简配置，按需分配物理空间。
- **Target驱动接口**：每个Target驱动必须实现一组标准的回调函数，如`map`（处理IO映射）、`end_io`（处理IO完成）、`ctr`（创建Target实例）、`dtr`（销毁Target实例）等。DM核心驱动通过这些接口与Target驱动交互。

### 3. 核心数据结构：DM层的“骨架”
内核态通过几个关键的数据结构来组织和管理DM设备及其映射规则。理解这些结构是读懂DM源码的关键。

#### `struct mapped_device`：DM设备的“身份证”
代表一个具体的DM虚拟设备（如`/dev/dm-0`）。它是DM设备在内核中的唯一实体。
```c
struct mapped_device {
    struct mutex                io_lock;          // 保护IO操作的锁
    struct mutex                table_lock;       // 保护映射表的锁
    struct dm_table             *map;             // 当前生效的映射表
    struct gendisk              *disk;            // 对应的通用磁盘结构（Block层）
    struct request_queue        *queue;           // 对应的IO请求队列（Block层）
    struct list_head            devices;          // 链接到全局DM设备链表
    dev_t                       dev;              // 设备号（主:次）
    atomic_t                    io_count;         // 当前IO计数
    // ... 其他状态和统计信息
};
```

#### `struct dm_table`：DM设备的“导航图”
存储了DM设备的完整映射规则。它是一个由多个`dm_target`结构体组成的数组。
```c
struct dm_table {
    struct mapped_device        *md;              // 所属的DM设备
    struct dm_target            **targets;        // Target数组
    unsigned int                nr_targets;       // Target数量
    sector_t                    size;             // DM设备的总大小（扇区数）
    // ... 其他属性
};
```

#### `struct dm_target`：映射规则的“具体条目”
代表映射表中的一个连续映射段。它包含了该段的逻辑地址范围、对应的Target驱动、以及传给Target驱动的参数。
```c
struct dm_target {
    struct dm_table             *table;           // 所属的映射表
    const struct target_type    *type;            // 对应的Target驱动类型
    sector_t                    begin;            // 逻辑起始扇区
    sector_t                    len;              // 逻辑扇区长度
    void                        *private;         // Target驱动的私有数据
    // ... 其他属性
};
```

---

## 四、用户态与内核态的通信机制：ioctl与控制设备

用户态与内核态的通信是通过`/dev/mapper/control`这个字符设备和`ioctl`系统调用来完成的。这是一种高效且标准的Linux内核与用户态通信方式。

### 1. 通信流程
1.  **用户态打开控制设备**：`fd = open("/dev/mapper/control", O_RDWR);`
2.  **用户态构造请求**：填充特定的`ioctl`请求结构体（如`struct dm_ioctl`），包含命令类型、设备名称、映射表数据等。
3.  **用户态发送ioctl命令**：`ioctl(fd, DM_DEV_CREATE, &cmd);`
4.  **内核态处理请求**：DM核心驱动的`dm_ioctl`函数被调用。它解析请求，执行相应的操作（如创建设备、加载映射表）。
5.  **内核态返回结果**：将操作结果（成功/失败、错误码、设备信息等）填充回请求结构体，并返回给用户态。
6.  **用户态关闭控制设备**：`close(fd);`

### 2. 关键ioctl命令
DM定义了一系列`ioctl`命令，用于完成各种操作。以下是几个最核心的命令：
- **`DM_DEV_CREATE`**：创建一个新的DM设备。
- **`DM_DEV_REMOVE`**：删除一个已存在的DM设备。
- **`DM_TABLE_LOAD`**：向一个已创建但未激活的DM设备加载映射表。
- **`DM_DEV_SUSPEND`**：暂停一个DM设备的IO操作（常用于更新映射表）。
- **`DM_DEV_RESUME`**：恢复一个被暂停的DM设备的IO操作（激活新的映射表）。
- **`DM_TABLE_STATUS`**：查询一个DM设备当前的映射表状态。
- **`DM_DEV_INFO`**：查询一个DM设备的详细信息（如设备号、大小、状态）。

---

## 五、实操彩蛋：动手体验“双态协同”

让我们通过一个简单的例子，来直观感受DM层的用户态与内核态是如何协同工作的。我们将创建一个基于`linear` Target的DM设备。

### 步骤1：准备一个物理设备
假设我们有一个物理分区 `/dev/sdb1`。

### 步骤2：编写映射表文件（mapfile.txt）
```txt
0 1048576 linear /dev/sdb1 0
```
解释：将DM设备的0到1048575扇区，线性映射到`/dev/sdb1`的0到1048575扇区。

### 步骤3：用户态操作（使用dmsetup）
```bash
# 1. 创建DM设备，名为mydm，加载映射表
dmsetup create mydm < mapfile.txt

# 2. 查看已创建的DM设备
dmsetup ls
# 输出：mydm (253:0)

# 3. 查看DM设备的映射表
dmsetup table mydm
# 输出：0 1048576 linear 8:17 0

# 4. 查看DM设备的详细信息
dmsetup info mydm
# 输出设备号、大小、状态等信息

# 5. 格式化并挂载DM设备
mkfs.ext4 /dev/mapper/mydm
mount /dev/mapper/mydm /mnt

# 6. 写入测试数据
echo "Hello, Device Mapper!" > /mnt/test.txt

# 7. 卸载并删除DM设备
umount /mnt
dmsetup remove mydm
```

### 步骤4：内核态验证
```bash
# 1. 查看DM内核模块是否加载
lsmod | grep dm_mod

# 2. 查看内核日志，确认DM设备创建/删除
dmesg | grep -i device-mapper
# 输出类似：
# device-mapper: table: 253:0: linear: dm-0: bound to device /dev/sdb1
# device-mapper: ioctl: 4.45.0-ioctl (2021-03-15) initialised: dm-devel@redhat.com
```

---

## 六、总结与预告

### 核心要点回顾
1.  DM层采用**“用户态管理 + 内核态执行”**的双态协同架构，平衡了灵活性与性能。
2.  **用户态**包含`libdm`（核心库）、`dmsetup`（命令行工具）和高层管理工具（LVM2、cryptsetup等），负责配置和管理DM设备。
3.  **内核态**包含DM核心驱动（`dm-mod`）和各种Target驱动（`linear`、`crypt`、`verity`等），负责执行IO处理逻辑。
4.  核心数据结构`mapped_device`、`dm_table`和`dm_target`构成了DM设备在内核中的“骨架”。
5.  用户态与内核态通过`/dev/mapper/control`字符设备和`ioctl`命令进行通信。

### 下一篇预告
理解了DM层的双态架构和核心数据结构后，你可能会问：一个DM设备从用户态发出`dmsetup create`命令，到内核态真正创建出`/dev/dm-*`设备文件，中间到底经历了哪些具体步骤？IO请求又是如何被精准地拦截、映射并转发的？

**下一篇《原理篇——DM设备的“诞生”与IO的“旅程”：从创建到IO处理全流程》**，我们将通过一个完整的时序图，详细拆解DM设备的创建流程和IO请求的处理流程，带你深入DM层的核心工作机制。