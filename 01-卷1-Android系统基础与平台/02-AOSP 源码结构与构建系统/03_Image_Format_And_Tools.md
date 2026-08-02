# 镜像格式和工具详解

## 📋 目录

1. [Sparse Image格式](#1-sparse-image格式)
2. [Raw Image格式](#2-raw-image格式)
3. [镜像格式转换](#3-镜像格式转换)
4. [镜像工具](#4-镜像工具)

---

## 1. Sparse Image格式

Sparse Image是Android标准镜像格式，只存储非零数据块。

### 1.1 格式结构

```
Header (28 bytes)
├── Chunk Header
│   └── Chunk Data
└── ...
```

### 1.2 Chunk类型

- `CHUNK_TYPE_RAW`：实际数据
- `CHUNK_TYPE_FILL`：填充值
- `CHUNK_TYPE_DONT_CARE`：全零块（不存储）

---

## 2. Raw Image格式

Raw Image是完整的分区镜像，文件大小等于分区大小。

---

## 3. 镜像格式转换

### 3.1 sparse转raw

```bash
simg2img system.sparse.img system.raw.img
```

### 3.2 raw转sparse

```bash
img2simg system.raw.img system.sparse.img
```

---

## 4. 镜像工具

### 4.1 查看镜像信息

```bash
file system.img
```

### 4.2 挂载镜像

```bash
# 挂载raw镜像
sudo mount -o loop system.raw.img /mnt
```

---

## 总结

镜像格式要点：

1. **Sparse Image**：压缩格式，Android标准
2. **Raw Image**：完整镜像
3. **转换工具**：simg2img, img2simg

**下一步学习**：
- 了解分区大小计算，请阅读 [分区大小计算和规划](04_Partition_Size_Calculation.md)
