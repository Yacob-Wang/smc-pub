# 文件系统架构与 IO 路径深度解析

## 📋 文档概述

本文档深入解析 Linux 文件系统的完整架构，从系统调用到硬件存储的完整 IO 路径，重点说明 F2FS 和 eMMC 在架构中的位置，以及数据在各个层级之间的流转过程。通过本文档，您将全面理解文件系统的工作原理，为分析文件系统相关的性能问题和稳定性问题打下坚实基础。

## 🎯 学习目标

- 理解 Linux 文件系统的完整架构层次
- 掌握从系统调用到硬件存储的完整 IO 路径
- 理解 F2FS 和 eMMC 在架构中的位置和作用
- 理解各层级之间的交互机制
- 能够追踪文件操作的完整流程

---

## 第一章：文件系统整体架构

### 1.1 完整架构图

Linux 文件系统采用分层架构，从应用层到硬件层共 7 层，每一层都有明确的职责：

```
┌─────────────────────────────────────────────────────────────────────┐
│  第 1 层：应用层（Application Layer）                               │
│  - 用户程序（App、SystemUI、系统服务等）                            │
│  - 系统调用：open(), read(), write(), close(), fsync()             │
│  - 示例：应用调用 write("data.txt", "Hello World")                 │
└────────────────────┬────────────────────────────────────────────────┘
                     │ 系统调用接口（syscall）
                     │ sys_write()
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│  第 2 层：VFS 层（Virtual File System）                             │
│  - 统一的文件系统抽象接口                                            │
│  - 路径解析：/data/user/0/com.example.app/files/data.txt          │
│  - 权限检查：检查文件访问权限                                        │
│  - 缓存管理：dentry 缓存、inode 缓存                                │
│  - 核心数据结构：                                                    │
│    • super_block：文件系统超级块                                    │
│    • inode：索引节点（文件元数据）                                  │
│    • dentry：目录项（路径到 inode 的映射）                          │
│    • file：文件对象（打开的文件）                                    │
│  - 关键函数：vfs_write(), vfs_read(), vfs_open()                  │
└────────────────────┬────────────────────────────────────────────────┘
                     │ 调用文件系统操作
                     │ file->f_op->write_iter()
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│  第 3 层：文件系统层（File System Layer）                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  F2FS（Flash-Friendly File System）                         │  │
│  │  - 存储布局管理：Superblock、Checkpoint、SIT、NAT、SSA       │  │
│  │  - 节点管理：Inode、Direct Node、Indirect Node              │  │
│  │  - 段管理：Segment 分配和回收                                │  │
│  │  - 元数据管理：文件大小、权限、时间戳                        │  │
│  │  - 关键函数：                                                │  │
│  │    • f2fs_file_write_iter()：写入处理                       │  │
│  │    • f2fs_file_read_iter()：读取处理                        │  │
│  │    • f2fs_write_data_pages()：数据页写回                    │  │
│  │    • f2fs_read_data_page()：数据页读取                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  其他文件系统（ext4、XFS 等）                                │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────────────┘
                     │ 页面操作
                     │ address_space_operations
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│  第 4 层：Page Cache 层（页面缓存）                                 │
│  - 文件数据的内存缓存                                                │
│  - address_space：管理文件的所有页面                                │
│  - page：4KB 页面，缓存文件数据                                    │
│  - 脏页（dirty page）管理：标记需要写回的页面                      │
│  - 预读（read-ahead）：预测性读取后续数据                          │
│  - 写回（writeback）：后台异步写回脏页                              │
│  - 关键函数：                                                       │
│    • generic_file_write_iter()：通用写入（写入 Page Cache）       │
│    • generic_file_read_iter()：通用读取（从 Page Cache 读取）     │
│    • write_cache_pages()：写回脏页                                │
└────────────────────┬────────────────────────────────────────────────┘
                     │ 块设备操作
                     │ submit_bio()
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│  第 5 层：Block I/O 层（块设备层）                                  │
│  - IO 请求队列管理：request_queue                                  │
│  - IO 调度器：mq-deadline、kyber 等                                │
│  - 请求合并和排序：优化 IO 顺序                                    │
│  - 多队列（Multi-Queue）支持：现代存储设备                          │
│  - 关键数据结构：                                                   │
│    • bio：块 IO 描述符（Block I/O descriptor）                    │
│    • request：IO 请求                                              │
│  - 关键函数：                                                       │
│    • submit_bio()：提交 IO 请求到块设备层                          │
│    • blk_mq_submit_bio()：多队列提交                               │
└────────────────────┬────────────────────────────────────────────────┘
                     │ 设备驱动接口
                     │ 驱动操作函数
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│  第 6 层：设备驱动层（Device Driver Layer）                         │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  eMMC 驱动（Embedded MultiMedia Card Driver）                │  │
│  │  - eMMC 协议处理                                              │  │
│  │  - 命令转换：将 bio 转换为 eMMC 命令                          │  │
│  │  - 数据传输：通过 eMMC 接口传输数据                           │  │
│  │  - 错误处理：处理传输错误和重试                                │  │
│  │  - 关键函数：                                                  │  │
│  │    • mmc_blk_issue_rq()：处理 IO 请求                         │  │
│  │    • mmc_wait_for_req()：等待请求完成                         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  其他存储驱动（UFS、NVMe 等）                                 │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────────────┘
                     │ 硬件接口（MMC/SD 协议）
                     │ 物理命令和数据传输
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│  第 7 层：物理存储设备（Physical Storage）                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  eMMC 芯片（Embedded MultiMedia Card）                      │  │
│  │  - NAND 闪存阵列：存储数据的物理介质                          │  │
│  │  - 控制器：管理 NAND 操作                                    │  │
│  │  - 接口：MMC/SD 标准接口                                      │  │
│  │  - 特性：                                                     │  │
│  │    • 基于 NAND 闪存                                           │  │
│  │    • 顺序写入快，随机写入慢                                   │  │
│  │    • 需要擦除再写入                                           │  │
│  │    • 有擦写次数限制                                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 F2FS 和 eMMC 的位置

**F2FS 的位置**：
- **第 3 层：文件系统层**
- 位于 VFS 层之下，Page Cache 层之上
- 负责管理 eMMC 上的数据组织和元数据

**eMMC 的位置**：
- **第 7 层：物理存储设备**
- 位于整个架构的最底层
- 提供实际的物理存储空间

**关系**：
- F2FS 是软件层，运行在 eMMC 之上
- F2FS 管理 eMMC 上的数据
- eMMC 是 F2FS 的存储介质

---

## 第二章：文件写入的完整路径

### 2.1 写入路径概览

以下是一个完整的文件写入流程，从应用层到 eMMC 硬件：

```
应用层：write("data.txt", "Hello World")
    ↓
系统调用：sys_write()
    ↓
VFS 层：vfs_write()
    ↓
文件系统层（F2FS）：f2fs_file_write_iter()
    ↓
Page Cache 层：generic_file_write_iter()
    ↓
Page Cache：写入到内存页面（延迟写入）
    ↓
后台写回：f2fs_write_data_pages()
    ↓
Block I/O 层：submit_bio()
    ↓
eMMC 驱动：mmc_blk_issue_rq()
    ↓
eMMC 芯片：物理写入 NAND 闪存
```

### 2.2 各层级详细流程

#### 第 1 层：应用层

**代码示例**：
```c
// 应用代码
int fd = open("/data/user/0/com.example.app/files/data.txt", O_WRONLY);
write(fd, "Hello World", 11);
close(fd);
```

**操作**：
- 应用调用 `write()` 系统调用
- 传递文件描述符、数据缓冲区、数据长度

#### 第 2 层：VFS 层

**关键函数**：`vfs_write()`

**处理流程**：
```c
// VFS 层的处理（简化）
ssize_t vfs_write(struct file *file, const char __user *buf, size_t count, loff_t *pos)
{
    // 1. 权限检查
    if (!(file->f_mode & FMODE_WRITE))
        return -EBADF;
    
    // 2. 获取文件操作函数
    if (file->f_op->write)
        return file->f_op->write(file, buf, count, pos);
    else if (file->f_op->write_iter)
        return file->f_op->write_iter(...);
    
    // 3. 调用文件系统的写入函数
    // 对于 F2FS：file->f_op->write_iter = f2fs_file_write_iter
}
```

**关键操作**：
1. **路径解析**：将路径转换为 inode
2. **权限检查**：检查文件写入权限
3. **获取文件操作**：从 inode 获取文件系统的操作函数
4. **路由到文件系统**：调用 F2FS 的写入函数

**数据结构**：
- `file`：打开的文件对象
- `inode`：文件的索引节点
- `dentry`：目录项（路径到 inode 的映射）

#### 第 3 层：文件系统层（F2FS）

**关键函数**：`f2fs_file_write_iter()`

**处理流程**：
```c
// F2FS 写入处理（简化）
static ssize_t f2fs_file_write_iter(struct kiocb *iocb, struct iov_iter *from)
{
    struct inode *inode = file_inode(iocb->ki_filp);
    
    // 1. 检查文件系统状态
    // 2. 处理直接 IO（如果启用）
    // 3. 调用通用写入函数（写入 Page Cache）
    return __generic_file_write_iter(iocb, from);
}
```

**F2FS 的职责**：
1. **元数据管理**：更新文件大小、修改时间等
2. **空间分配**：如果需要，分配新的段（Segment）
3. **节点管理**：更新或创建 Direct Node、Indirect Node
4. **数据组织**：决定数据写入的位置

**关键点**：
- F2FS **不直接写入 eMMC**
- F2FS 将数据写入 **Page Cache**（内存）
- 实际的物理写入由后台写回机制完成

#### 第 4 层：Page Cache 层

**关键函数**：`generic_file_write_iter()`

**处理流程**：
```c
// Page Cache 写入处理（简化）
ssize_t generic_file_write_iter(struct kiocb *iocb, struct iov_iter *from)
{
    // 1. 获取或创建页面
    struct page *page = grab_cache_page_write_begin(...);
    
    // 2. 将数据写入页面
    copy_from_user(page->data, user_buf, count);
    
    // 3. 标记页面为脏页（dirty）
    set_page_dirty(page);
    
    // 4. 释放页面
    put_page(page);
    
    // 注意：此时数据还在内存中，尚未写入 eMMC
}
```

**Page Cache 的作用**：
1. **缓存文件数据**：最近写入的数据缓存在内存
2. **延迟写入**：不立即写入 eMMC，提高性能
3. **批量写入**：合并多个小写入，减少 IO 次数

**脏页管理**：
- 写入 Page Cache 的页面被标记为"脏页"（dirty）
- 脏页需要写回到 eMMC
- 写回由后台机制触发

#### 第 4.5 层：后台写回（Writeback）

**触发条件**：
1. 脏页数量达到阈值（`dirty_ratio`）
2. 时间到期（`dirty_expire_centisecs`）
3. 内存压力（需要回收脏页）
4. 显式同步（`fsync()`、`sync()`）

**写回流程**：
```c
// F2FS 写回处理（简化）
static int f2fs_write_data_pages(struct address_space *mapping,
                                  struct writeback_control *wbc)
{
    // 1. 遍历脏页
    // 2. 对每个脏页：
    //    - 分配段和节点（如果需要）
    //    - 调用 f2fs_write_data_page()
    // 3. 提交到 Block I/O 层
}
```

**F2FS 写回的职责**：
1. **段分配**：为数据分配段（Segment）
2. **节点更新**：更新 Direct Node 或 Indirect Node
3. **元数据更新**：更新文件大小等元数据
4. **提交 IO**：调用 `submit_bio()` 提交到 Block I/O 层

#### 第 5 层：Block I/O 层

**关键函数**：`submit_bio()`

**处理流程**：
```c
// Block I/O 层处理（简化）
void submit_bio(struct bio *bio)
{
    // 1. 创建 bio 结构
    //    - 包含：设备、起始扇区、数据长度、数据缓冲区
    
    // 2. 获取请求队列
    struct request_queue *q = bdev_get_queue(bio->bi_bdev);
    
    // 3. IO 调度器处理
    //    - 合并相邻请求
    //    - 排序请求（按扇区号）
    //    - 选择执行顺序
    
    // 4. 提交到设备驱动
    q->make_request_fn(q, bio);
}
```

**Block I/O 层的职责**：
1. **请求队列管理**：管理待处理的 IO 请求
2. **IO 调度**：决定 IO 请求的执行顺序
3. **请求合并**：合并相邻的 IO 请求
4. **路由到驱动**：将请求传递给设备驱动

**关键数据结构**：
- `bio`：块 IO 描述符，包含 IO 请求的基本信息
- `request`：IO 请求，可能包含多个 bio
- `request_queue`：请求队列，管理所有 IO 请求

#### 第 6 层：eMMC 驱动层

**关键函数**：`mmc_blk_issue_rq()`

**处理流程**：
```c
// eMMC 驱动处理（简化）
static int mmc_blk_issue_rq(struct mmc_queue *mq, struct request *req)
{
    // 1. 将 bio 转换为 eMMC 命令
    //    - 读取：MMC_READ_SINGLE_BLOCK 或 MMC_READ_MULTIPLE_BLOCK
    //    - 写入：MMC_WRITE_SINGLE_BLOCK 或 MMC_WRITE_MULTIPLE_BLOCK
    
    // 2. 准备数据传输
    //    - 设置数据缓冲区
    //    - 设置传输长度
    
    // 3. 发送命令到 eMMC
    mmc_wait_for_req(host, &mrq);
    
    // 4. 等待传输完成
    // 5. 处理错误和重试
}
```

**eMMC 驱动的职责**：
1. **协议处理**：处理 MMC/SD 协议
2. **命令转换**：将 bio 转换为 eMMC 命令
3. **数据传输**：通过 eMMC 接口传输数据
4. **错误处理**：处理传输错误和重试

**eMMC 命令类型**：
- `MMC_READ_SINGLE_BLOCK`：读取单个块
- `MMC_READ_MULTIPLE_BLOCK`：读取多个块
- `MMC_WRITE_SINGLE_BLOCK`：写入单个块
- `MMC_WRITE_MULTIPLE_BLOCK`：写入多个块

#### 第 7 层：eMMC 芯片（物理存储）

**物理操作**：
1. **接收命令**：eMMC 控制器接收来自驱动的命令
2. **地址解析**：解析要访问的物理地址
3. **NAND 操作**：
   - **读取**：从 NAND 闪存读取数据
   - **写入**：
     - 如果目标块已擦除：直接写入
     - 如果目标块未擦除：先擦除再写入
4. **数据传输**：通过 MMC 接口传输数据
5. **状态返回**：返回操作状态（成功/失败）

**eMMC 的特性**：
- **基于 NAND 闪存**：需要先擦除再写入
- **块擦除**：擦除单位是块（Block），通常 128KB 或 256KB
- **页写入**：写入单位是页（Page），通常 4KB
- **顺序写入快**：顺序写入性能好
- **随机写入慢**：随机写入需要频繁擦除

---

## 第三章：文件读取的完整路径

### 3.1 读取路径概览

```
应用层：read("data.txt", buf, size)
    ↓
系统调用：sys_read()
    ↓
VFS 层：vfs_read()
    ↓
文件系统层（F2FS）：f2fs_file_read_iter()
    ↓
Page Cache 层：generic_file_read_iter()
    ↓
Page Cache：检查页面是否在缓存中
    ├─ 命中：直接从内存返回
    └─ 未命中：f2fs_read_data_page()
        ↓
        Block I/O 层：submit_bio()
        ↓
        eMMC 驱动：mmc_blk_issue_rq()
        ↓
        eMMC 芯片：从 NAND 闪存读取
        ↓
        填充 Page Cache
        ↓
        返回数据给应用
```

### 3.2 读取路径的关键点

#### Page Cache 命中（Cache Hit）

**流程**：
```
1. 应用调用 read()
2. VFS 层处理
3. F2FS 层处理
4. Page Cache 层检查：页面在缓存中
5. 直接从内存复制数据到用户缓冲区
6. 返回给应用
```

**优势**：
- **速度快**：无需访问 eMMC
- **低延迟**：内存访问延迟极低
- **减少 IO**：减少对 eMMC 的访问

#### Page Cache 未命中（Cache Miss）

**流程**：
```
1. 应用调用 read()
2. VFS 层处理
3. F2FS 层处理
4. Page Cache 层检查：页面不在缓存中
5. 调用 f2fs_read_data_page()
6. F2FS 确定数据在 eMMC 上的位置
7. 提交 IO 请求到 Block I/O 层
8. eMMC 驱动处理
9. eMMC 芯片从 NAND 读取数据
10. 数据填充到 Page Cache
11. 返回数据给应用
```

**关键点**：
- F2FS 需要确定数据在 eMMC 上的物理位置
- 通过节点（Node）结构查找数据块地址
- 读取后填充 Page Cache，供后续访问使用

---

## 第四章：F2FS 在架构中的关键作用

### 4.1 F2FS 的职责

**1. 数据组织**
- 决定文件数据在 eMMC 上的存储位置
- 使用段（Segment）管理存储空间
- 优化写入模式（日志结构）

**2. 元数据管理**
- 管理文件大小、权限、时间戳
- 管理节点（Node）结构
- 管理段信息表（SIT）、节点地址表（NAT）

**3. 空间管理**
- 分配和回收段
- 垃圾回收（GC）
- 碎片整理

**4. 性能优化**
- 减少随机写入（日志结构）
- 批量更新元数据
- 延迟写入优化

### 4.2 F2FS 与 eMMC 的协作

**F2FS 的优势**：
- **针对 NAND 闪存优化**：eMMC 基于 NAND 闪存
- **减少随机写入**：eMMC 随机写入性能差
- **延长寿命**：均衡磨损，延长 eMMC 寿命
- **提高性能**：顺序写入，利用 eMMC 的优势

**协作流程**：
```
F2FS 决定数据组织方式
    ↓
优化为顺序写入
    ↓
减少随机写入
    ↓
提高 eMMC 性能
    ↓
延长 eMMC 寿命
```

---

## 第五章：关键数据结构流转

### 5.1 写入路径的数据结构流转

```
应用层：
  char *buf = "Hello World"
    ↓
VFS 层：
  struct file *file
  struct inode *inode
    ↓
F2FS 层：
  struct f2fs_inode_info *fi
  struct f2fs_sb_info *sbi
    ↓
Page Cache 层：
  struct address_space *mapping
  struct page *page (标记为 dirty)
    ↓
Block I/O 层：
  struct bio *bio
    - bi_bdev: 块设备
    - bi_sector: 起始扇区
    - bi_io_vec: 数据向量
    ↓
eMMC 驱动层：
  struct mmc_request *mrq
    - cmd: eMMC 命令
    - data: 数据传输描述符
    ↓
eMMC 芯片：
  物理 NAND 闪存单元
```

### 5.2 关键数据结构说明

**VFS 层**：
- `file`：打开的文件对象
- `inode`：文件的索引节点
- `dentry`：目录项

**F2FS 层**：
- `f2fs_inode_info`：F2FS 的 inode 信息
- `f2fs_sb_info`：F2FS 的超级块信息
- `node`：F2FS 的节点结构

**Page Cache 层**：
- `address_space`：管理文件的所有页面
- `page`：4KB 页面，缓存文件数据

**Block I/O 层**：
- `bio`：块 IO 描述符
- `request`：IO 请求
- `request_queue`：请求队列

**eMMC 驱动层**：
- `mmc_request`：eMMC 请求
- `mmc_command`：eMMC 命令
- `mmc_data`：数据传输描述符

---

## 第六章：性能优化点

### 6.1 各层级的优化

**VFS 层优化**：
- **缓存机制**：dentry 缓存、inode 缓存
- **路径解析优化**：快速查找 inode

**F2FS 层优化**：
- **日志结构**：减少随机写入
- **批量更新**：批量更新元数据
- **段管理**：优化空间分配

**Page Cache 层优化**：
- **延迟写入**：减少 IO 次数
- **预读机制**：预测性读取
- **批量写回**：合并多个写入

**Block I/O 层优化**：
- **IO 调度**：优化 IO 顺序
- **请求合并**：合并相邻请求
- **多队列**：提高并发性能

**eMMC 驱动层优化**：
- **命令优化**：使用多块命令
- **DMA 传输**：直接内存访问
- **命令队列**：提高并发性

### 6.2 整体性能影响

**延迟写入的优势**：
```
应用写入 → Page Cache（快速，内存操作）
    ↓
后台写回 → eMMC（异步，不阻塞应用）
```

**优势**：
- 应用不等待 eMMC 写入完成
- 可以合并多个小写入
- 可以优化写入顺序

---

## 第七章：实际案例分析

### 7.1 案例：应用写入文件

**场景**：Android 应用写入配置文件

**完整流程**：
```
1. 应用：write("/data/user/0/com.app/files/config.txt", "key=value")
   
2. 系统调用：sys_write(fd, buf, len)
   - fd: 文件描述符
   - buf: "key=value"
   - len: 9
   
3. VFS 层：vfs_write()
   - 路径解析：/data/user/0/com.app/files/config.txt
   - 查找 inode
   - 权限检查
   - 获取 F2FS 的操作函数
   
4. F2FS 层：f2fs_file_write_iter()
   - 更新文件大小
   - 准备写入 Page Cache
   
5. Page Cache 层：generic_file_write_iter()
   - 获取或创建页面
   - 将 "key=value" 写入页面
   - 标记页面为脏页
   
6. 返回应用：写入完成（但数据还在内存中）
   
7. 后台写回（稍后触发）：
   - f2fs_write_data_pages()
   - 分配段（如果需要）
   - 更新节点
   - submit_bio()
   
8. Block I/O 层：
   - IO 调度
   - 请求合并
   - 提交到驱动
   
9. eMMC 驱动：
   - 转换为 eMMC 命令
   - 发送到 eMMC 芯片
   
10. eMMC 芯片：
    - 写入 NAND 闪存
    - 数据持久化
```

### 7.2 案例：应用读取文件

**场景**：Android 应用读取配置文件

**完整流程**：
```
1. 应用：read("/data/user/0/com.app/files/config.txt", buf, size)
   
2. 系统调用：sys_read(fd, buf, size)
   
3. VFS 层：vfs_read()
   - 路径解析
   - 查找 inode
   - 权限检查
   
4. F2FS 层：f2fs_file_read_iter()
   - 准备读取
   
5. Page Cache 层：generic_file_read_iter()
   - 检查页面是否在缓存中
   
   情况 A：缓存命中
   - 直接从内存复制数据
   - 返回给应用（快速）
   
   情况 B：缓存未命中
   - 调用 f2fs_read_data_page()
   - F2FS 确定数据位置
   - submit_bio()
   - eMMC 驱动读取
   - eMMC 芯片从 NAND 读取
   - 填充 Page Cache
   - 返回数据给应用
```

---

## 第八章：关键源码位置

### 8.1 各层级的源码位置

**VFS 层**：
- `fs/read_write.c`：read/write 系统调用实现
- `fs/open.c`：open 系统调用实现
- `include/linux/fs.h`：VFS 接口定义

**F2FS 层**：
- `fs/f2fs/file.c`：文件操作实现
- `fs/f2fs/data.c`：数据读写实现
- `fs/f2fs/segment.c`：段管理实现

**Page Cache 层**：
- `mm/filemap.c`：Page Cache 实现
- `mm/page-writeback.c`：Writeback 实现

**Block I/O 层**：
- `block/blk-core.c`：Block I/O 核心
- `block/blk-mq.c`：多队列实现

**eMMC 驱动层**：
- `drivers/mmc/core/`：MMC 核心
- `drivers/mmc/host/`：MMC 主机驱动
- `drivers/mmc/block/`：MMC 块设备驱动

---

## 📝 总结

### 关键要点

1. **分层架构**：Linux 文件系统采用 7 层架构，每层职责明确
2. **F2FS 位置**：第 3 层（文件系统层），管理数据组织
3. **eMMC 位置**：第 7 层（物理存储），提供实际存储
4. **IO 路径**：从系统调用到硬件存储，经过所有层级
5. **延迟写入**：写入先到 Page Cache，后台异步写回
6. **缓存机制**：Page Cache 提高读取性能

### 性能优化

- **延迟写入**：减少 IO 次数，提高写入性能
- **缓存机制**：Page Cache 提高读取性能
- **IO 调度**：优化 IO 顺序，提高吞吐量
- **批量操作**：合并多个小 IO，减少开销

### 学习建议

1. **理解架构**：先理解整体架构，再深入各层
2. **追踪路径**：通过实际案例追踪 IO 路径
3. **查看源码**：结合源码理解实现细节
4. **工具辅助**：使用 strace、ftrace 等工具追踪

---

**下一步**：
1. 深入学习 VFS 架构和核心数据结构
2. 理解 Page Cache 和 Writeback 机制
3. 深入研究 F2FS 的实现细节
4. 分析文件系统相关的性能问题
