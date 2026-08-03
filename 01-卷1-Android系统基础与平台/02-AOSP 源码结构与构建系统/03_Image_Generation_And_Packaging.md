# 镜像生成和打包

## 📋 目录

1. [镜像生成工具](#1-镜像生成工具)
2. [各分区镜像打包流程](#2-各分区镜像打包流程)
3. [稀疏镜像生成](#3-稀疏镜像生成)
4. [镜像压缩和优化](#4-镜像压缩和优化)
5. [镜像签名和验证](#5-镜像签名和验证)
6. [完整系统镜像生成](#6-完整系统镜像生成)

---

## 1. 镜像生成工具

### 1.1 mkbootimg - Boot镜像打包

**用途**：打包 boot.img 和 init_boot.img

**基本用法**：
```bash
mkbootimg \
    --kernel Image.lz4 \
    --ramdisk ramdisk.cpio \
    --output boot.img \
    --pagesize 4096 \
    --base 0x00000000 \
    --kernel_offset 0x00008000 \
    --ramdisk_offset 0x01000000 \
    --tags_offset 0x00000100 \
    --header_version 4
```

**参数说明**：
- `--kernel`：内核镜像文件
- `--ramdisk`：ramdisk文件（cpio格式）
- `--output`：输出文件
- `--pagesize`：页面大小（通常4096）
- `--base`：内核基址
- `--header_version`：boot header版本（Android 11+使用v3/v4）

### 1.2 mkbootfs - Ramdisk打包

**用途**：将目录打包为ramdisk（cpio格式）

**基本用法**：
```bash
mkbootfs ramdisk_dir | gzip > ramdisk.cpio.gz
# 或
mkbootfs ramdisk_dir > ramdisk.cpio
```

### 1.3 make_ext4fs - ext4文件系统镜像

**用途**：创建ext4文件系统镜像

**基本用法**：
```bash
make_ext4fs -s -l 3221225472 -a system system.img system_dir/
```

**参数说明**：
- `-s`：生成sparse镜像
- `-l`：镜像大小（字节）
- `-a`：挂载点名称
- 最后两个参数：输出文件和源目录

### 1.4 mksquashfs - squashfs文件系统镜像

**用途**：创建squashfs压缩只读文件系统

**基本用法**：
```bash
mksquashfs system_dir/ system.squashfs.img -comp lz4 -b 131072
```

### 1.5 img2simg / simg2img - 镜像格式转换

**img2simg**：raw转sparse
```bash
img2simg system.raw.img system.sparse.img
```

**simg2img**：sparse转raw
```bash
simg2img system.sparse.img system.raw.img
```

### 1.6 mkuserimg.sh - 用户数据镜像生成

**用途**：生成userdata等数据分区镜像

**基本用法**：
```bash
mkuserimg.sh userdata_dir/ userdata.img ext4 userdata 3221225472
```

### 1.7 lpmake - 动态分区镜像生成

**用途**：创建super分区（动态分区容器）

**基本用法**：
```bash
lpmake \
    --device-size 17179869184 \
    --metadata-size 65536 \
    --metadata-slots 2 \
    --partition system_a:readonly:3221225472:group_a \
    --partition system_b:readonly:3221225472:group_b \
    --group group_a:8589934592 \
    --group group_b:8589934592 \
    --sparse \
    --output super.img
```

---

## 2. 各分区镜像打包流程

### 2.1 system分区镜像

**流程**：
```bash
# 1. 编译system分区内容
m system

# 2. 生成ext4镜像（自动）
m systemimage

# 内部流程：
# - 使用make_ext4fs创建ext4文件系统
# - 转换为sparse格式
# - 输出: out/target/product/{device}/system.img
```

**手动生成**：
```bash
# 从system目录生成镜像
make_ext4fs -s -l 3221225472 -a system \
    system.img out/target/product/{device}/system/

# 转换为sparse格式（如果还没有）
img2simg system.raw.img system.sparse.img
```

### 2.2 boot分区镜像

**流程**：
```bash
# 1. 编译内核
cd kernel/common
make ARCH=arm64 -j$(nproc)

# 2. 编译ramdisk（Android 12-）
# 或使用init_boot（Android 13+）

# 3. 打包boot.img
mkbootimg \
    --kernel arch/arm64/boot/Image.lz4 \
    --ramdisk ramdisk.cpio \
    --output boot.img \
    --pagesize 4096 \
    --base 0x00000000
```

### 2.3 vendor_boot分区镜像

**流程**：
```bash
# 1. 准备vendor ramdisk
# 2. 编译DTB
# 3. 打包vendor_boot.img
mkbootimg \
    --vendor_ramdisk vendor_ramdisk.cpio \
    --dtb dtb.img \
    --vendor_ramdisk_table vendor_ramdisk_table.txt \
    --output vendor_boot.img \
    --pagesize 4096 \
    --header_version 4
```

### 2.4 dtbo分区镜像

**流程**：
```bash
# 1. 编译设备树覆盖层
dtc -@ -O dtb -o overlay1.dtbo overlay1.dts
dtc -@ -O dtb -o overlay2.dtbo overlay2.dts

# 2. 打包dtbo.img
mkdtimg create dtbo.img overlay1.dtbo overlay2.dtbo
```

---

## 3. 稀疏镜像生成

### 3.1 Sparse Image格式

**结构**：
```
Sparse Image Header (28 bytes)
├── Chunk Header 1
│   └── Chunk Data 1
├── Chunk Header 2
│   └── Chunk Data 2
└── ...
```

**Chunk类型**：
- `CHUNK_TYPE_RAW`：实际数据
- `CHUNK_TYPE_FILL`：填充相同值
- `CHUNK_TYPE_DONT_CARE`：全零块（不存储）
- `CHUNK_TYPE_CRC32`：CRC32校验

### 3.2 生成Sparse镜像

**自动生成**（编译时）：
```bash
# 编译时自动生成sparse镜像
m systemimage
# 输出: system.img (sparse格式)
```

**手动转换**：
```bash
# raw转sparse
img2simg system.raw.img system.sparse.img

# 查看sparse镜像信息
file system.sparse.img
# 输出: Android sparse image, version: 1.0, Total of X 4096-byte output blocks
```

### 3.3 Sparse镜像优势

1. **文件大小**：通常比raw镜像小50-90%
2. **传输速度**：OTA更新包更小
3. **存储效率**：只存储非零数据

---

## 4. 镜像压缩和优化

### 4.1 文件系统压缩

**erofs压缩**（推荐用于只读分区）：
```bash
# erofs支持多种压缩算法
mkfs.erofs -z lz4hc system.erofs.img system_dir/
mkfs.erofs -z lz4 system.erofs.img system_dir/
```

**squashfs压缩**：
```bash
mksquashfs system_dir/ system.squashfs.img \
    -comp lz4 -b 131072 -Xhc
```

### 4.2 镜像优化

**去除调试符号**：
```bash
# 在编译时
export TARGET_STRIP=true
m systemimage
```

**优化文件系统**：
```bash
# 使用tune2fs优化ext4
tune2fs -O ^has_journal system.img
tune2fs -O ^extent system.img
```

---

## 5. 镜像签名和验证

### 5.1 AVB签名

**使用avbtool签名**：
```bash
# 签名分区镜像
avbtool add_hash_footer \
    --image system.img \
    --partition_name system \
    --partition_size 3221225472 \
    --key private_key.pem \
    --algorithm SHA256_RSA4096

# 签名boot镜像
avbtool add_hash_footer \
    --image boot.img \
    --partition_name boot \
    --partition_size 67108864 \
    --key private_key.pem \
    --algorithm SHA256_RSA4096
```

### 5.2 验证签名

```bash
# 验证镜像签名
avbtool verify_image --image system.img

# 使用公钥验证
avbtool verify_image \
    --image system.img \
    --key public_key.pem
```

### 5.3 vbmeta生成

```bash
# 生成vbmeta
avbtool make_vbmeta_image \
    --output vbmeta.img \
    --include_descriptors_from_image system.img \
    --include_descriptors_from_image vendor.img \
    --include_descriptors_from_image boot.img \
    --algorithm SHA256_RSA4096 \
    --key private_key.pem \
    --rollback_index 0
```

---

## 6. 完整系统镜像生成

### 6.1 生成所有分区镜像

```bash
# 编译所有分区镜像
m -j$(nproc)

# 这会生成：
# - boot.img
# - init_boot.img
# - vendor_boot.img
# - dtbo.img
# - system.img
# - vendor.img
# - product.img
# - system_ext.img
# - odm.img
# - system_dlkm.img
# - vendor_dlkm.img
# - odm_dlkm.img
# - vbmeta*.img
# - userdata.img
# - super.img (如果使用动态分区)
```

### 6.2 生成super分区（动态分区）

```bash
# 自动生成（如果配置了动态分区）
m superimage

# 手动生成
lpmake \
    --device-size 17179869184 \
    --metadata-size 65536 \
    --metadata-slots 2 \
    --partition system_a:readonly:3221225472:group_a \
    --partition system_b:readonly:3221225472:group_b \
    --partition vendor_a:readonly:536870912:group_a \
    --partition vendor_b:readonly:536870912:group_b \
    --group group_a:8589934592 \
    --group group_b:8589934592 \
    --sparse \
    --output super.img
```

### 6.3 验证镜像完整性

```bash
# 检查所有镜像
ls -lh out/target/product/{device}/*.img

# 验证镜像格式
file out/target/product/{device}/*.img

# 检查镜像大小
du -sh out/target/product/{device}/*.img

# 验证sparse镜像
simg2img system.sparse.img system.raw.img
# 如果转换成功，说明镜像完整
```

---

## 总结

镜像生成和打包要点：

1. **工具**：mkbootimg, make_ext4fs, img2simg, lpmake等
2. **格式**：sparse镜像（Android标准）或raw镜像
3. **压缩**：erofs, squashfs用于只读分区
4. **签名**：使用avbtool进行AVB签名
5. **验证**：生成后验证镜像完整性和签名

**下一步学习**：
- 了解编译配置选项，请阅读 [编译配置和选项](04_Build_Configuration_And_Options.md)
- 了解系统集成，请阅读 [系统组成和启动](../03_System_Integration/01_System_Composition_And_Boot.md)
