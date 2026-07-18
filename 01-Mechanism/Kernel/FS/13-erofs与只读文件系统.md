# erofs 与只读文件系统

## 学习目标

- 理解 erofs 的设计理念：只读、压缩、高效
- 掌握 erofs 的磁盘格式
- 了解压缩算法（LZ4, LZMA）
- 理解 erofs 在 Android system 分区的应用
- 了解 squashfs 简介与对比

## 概述

erofs（Enhanced Read-Only File System）是专为只读场景设计的高效文件系统，在 Android 中用于 system 和 vendor 分区。

---

## 一、erofs 设计理念

### 为什么需要只读文件系统

Android system 分区特点：
- **只读**：系统分区不需要写入
- **压缩**：节省存储空间
- **快速**：启动时快速加载
- **高效**：减少内存占用

### erofs 设计目标

1. **只读优化**：针对只读场景优化
2. **压缩支持**：支持多种压缩算法
3. **高性能**：快速访问和加载
4. **低内存**：减少内存占用

---

## 二、erofs 磁盘格式

### 整体布局

```
erofs 文件系统布局：

┌─────────────────────────────────────────────────────────────┐
│  Superblock                                                 │
│  - 文件系统魔数                                              │
│  - 块大小、总块数                                            │
│  - 压缩算法                                                  │
├─────────────────────────────────────────────────────────────┤
│  Inode Table                                                │
│  - 压缩的 inode 数据                                         │
├─────────────────────────────────────────────────────────────┤
│  Data Blocks                                                │
│  ┌──────────┬──────────┬──────────┬──────────┐            │
│  │  Block 0 │  Block 1 │  Block 2 │  ...    │            │
│  │ (压缩)   │ (压缩)   │ (未压缩) │         │            │
│  └──────────┴──────────┴──────────┴──────────┘            │
└─────────────────────────────────────────────────────────────┘
```

### 超级块结构

```c
// fs/erofs/erofs_fs.h
struct erofs_super_block {
    __le32 magic;           // 魔数（EROFS_SUPER_MAGIC_V1）
    __le32 checksum;        // 校验和
    __le32 feature_compat;  // 兼容特性
    __u8 blkszbits;         // 块大小（log2）
    __u8 reserved;
    __le16 root_nid;        // 根inode号
    __le64 inos;            // inode总数
    __le64 build_time;      // 构建时间
    __le32 build_time_nsec; // 构建时间（纳秒）
    __le32 blocks;          // 总块数
    __le32 meta_blkaddr;    // 元数据块地址
    __le32 xattr_blkaddr;   // 扩展属性块地址
    __u8 uuid[16];          // UUID
    __u8 volume_name[16];    // 卷名
    __le32 feature_incompat; // 不兼容特性
    __u8 reserved2[44];
};
```

---

## 三、压缩算法

### 支持的压缩算法

| 算法 | 压缩比 | 速度 | 内存占用 |
|-----|-------|------|---------|
| LZ4 | 低 | 快 | 低 |
| LZMA | 高 | 慢 | 中 |
| LZ4HC | 中 | 中 | 低 |

### LZ4 压缩

**特点**：
- 压缩速度快
- 解压速度快
- 压缩比一般

**适用场景**：
- 需要快速加载
- 对压缩比要求不高

### LZMA 压缩

**特点**：
- 压缩比高
- 压缩速度慢
- 解压速度慢

**适用场景**：
- 存储空间有限
- 可以接受较慢的加载速度

---

## 四、erofs 在 Android 中的应用

### Android 分区使用

```bash
# 查看 system 分区文件系统
mount | grep system
# /dev/block/sda2 on /system type erofs (ro,seclabel,relatime)

# 查看 erofs 信息
ls -l /system
# 文件系统为只读
```

### erofs 构建

```bash
# 使用 mkfs.erofs 创建 erofs 文件系统
mkfs.erofs -z lz4 -d /path/to/system /system.img

# 参数说明：
# -z: 压缩算法（lz4, lzma, lz4hc）
# -d: 源目录
# 输出: erofs 镜像文件
```

### Android 构建集成

```makefile
# Android.mk
$(BUILT_SYSTEMIMAGE): $(INTERNAL_SYSTEMIMAGE_FILES) | $(MKEXT4IMG)
    $(call build-systemimage-target,$@)
    $(hide) $(MKEXT4IMG) -s -T $(INSTALLED_SYSTEMIMAGE_TARGET) \
        -L system -z lz4 -C $(TARGET_OUT) $@
```

---

## 五、squashfs 简介与对比

### squashfs 概述

squashfs 是另一个只读压缩文件系统，在 Linux 发行版中广泛使用。

### erofs vs squashfs

| 特性 | erofs | squashfs |
|-----|-------|----------|
| 压缩算法 | LZ4, LZMA | gzip, xz, lz4 |
| 随机访问 | 支持 | 支持 |
| 元数据压缩 | 是 | 是 |
| Android 支持 | 是 | 否（需要额外支持） |
| 性能 | 高 | 中 |

### 选择建议

- **erofs**：Android 系统分区，需要原生支持
- **squashfs**：Linux 发行版，通用只读文件系统

---

## 总结

### 核心要点

1. **erofs 设计理念**：
   - 只读优化
   - 压缩支持
   - 高性能

2. **压缩算法**：
   - LZ4：快速
   - LZMA：高压缩比

3. **Android 应用**：
   - system 和 vendor 分区
   - 节省存储空间
   - 快速启动

### 后续学习

- [虚拟文件系统实现](14-虚拟文件系统实现.md) - 理解虚拟文件系统
- [文件系统性能分析](19-文件系统性能分析.md) - 性能优化

## 参考资源

- 内核源码：
  - `fs/erofs/` - erofs 文件系统
  - `fs/erofs/erofs_fs.h` - erofs 结构定义
- erofs 文档：`Documentation/filesystems/erofs.rst`

## 更新记录

- 2026-01-28：初始创建，包含 erofs 与只读文件系统详解
