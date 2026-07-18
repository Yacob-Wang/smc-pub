# 11-APK 容器解析:ZIP + arsc + 资源 ID 体系

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15` / `android15-6.1`(Android 14 加强 ZIP 校验涉及 `finit_module` + `verify_pkcs7`,内核版本影响签名验证路径)+ `system/core/libziparchive/` + `frameworks/base/tools/aapt2/` + `frameworks/base/libs/androidfw/ApkAssets.cpp` + 工具 `aapt2`、`apksigner`、`zipinfo`
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[10-资源加载:AssetManager / ApkAssets / ResTable](10-资源加载-AssetManager-ApkAssets-ResTable.md)
> **下一篇**:[12-进程启动全景:Zygote fork → 第一帧](12-进程启动全景-Zygote-fork-第一帧.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 10 篇(资源侧 · 容器格式层,资源 2 篇收尾)
- **强依赖**:**[PLE-01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-10 资源加载](10-资源加载-AssetManager-ApkAssets-ResTable.md)**
- **承接自**:PLE-10 已讲 ResTable 三层结构;本篇讲"资源在 APK 文件里的物理布局"(ZIP 容器 / arsc 字节 / 资源 ID 编码)
- **衔接去**:下一篇 [PLE-12 进程启动全景](12-进程启动全景-Zygote-fork-第一帧.md) 端到端串联全部加载流程
- **不重复内容**:
  - **AssetManager / ResTable 三层结构** → 详见 [PLE-10](10-资源加载-AssetManager-ApkAssets-ResTable.md)
  - **ClassLoader / DEX / 类加载** → 详见 [PLE-06](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md) / [PLE-07](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md)
  - **APK 签名 v2/v3/v4 细节** → 不在本系列(详见 [Tools/Android_Tools/Init_RC](../06-Foundation/Tools/Android_Tools/Init_RC_Complete_Guide.md))

## 0. 写在前面:为什么 APK 容器单独成篇

### 0.1 一个真实的安装失败案例

**场景**:某 App 升级到 Android 14 后,部分设备安装失败:

```
E PackageManager: Failed to parse /data/app/vmdl123.tmp/base.apk
E PackageManager: java.util.zip.ZipException: End of Central Directory not found
E PackageManager: Install failed: INSTALL_FAILED_BAD_APK
```

**症状**:APK 解压时"找不到中央目录",安装失败。

**根因排查**:
1. 该 App 用某个三方加固 SDK,该 SDK 对 APK 做了特殊处理
2. SDK 在 ZIP 末尾添加了"原始字节"作为保护
3. 这导致 ZIP 的 End of Central Directory(EOCD)被覆盖
4. Android 14 加强了 ZIP 校验,严格检查 EOCD
5. 加固 SDK 还没适配 Android 14

**修复**:
- 加固 SDK 升级(适配 Android 14)
- 或改用 Android 14 兼容的加固方案

**这个案例的修复需要 3 个知识**:
1. 知道 APK 本质是 ZIP 容器
2. 知道 ZIP 的关键结构(Local File Header / Central Directory / EOCD)
3. 知道 Android 签名在 ZIP 中的位置

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Huawei P50(Kirin 9000,arm64-v8a,鸿蒙但兼容 AOSP 12)
> - Android 版本:`android-12.0.0_r31`(基线)→ 通过 OTA 升级到 `android-14.0.0_r1`
> - App:某金融 App v6.0.0,使用 360 加固 SDK(2022 年发布的 v3.4.0)
> - 工具:`unzip` + `zipinfo` + `aapt2 dump badging`

> **复现步骤**:
> 1. Android 12 设备安装 v6.0.0,正常安装
> 2. OTA 升级到 Android 14
> 3. 卸载 v6.0.0,重新安装 → **必现失败**
> 4. 失败信息:`INSTALL_FAILED_BAD_APK` + `End of Central Directory not found`

> **logcat 关键片段**:
> ```
> E PackageManager: Failed to parse /data/app/vmdl123.tmp/base.apk
> E PackageManager: java.util.zip.ZipException: End of Central Directory not found
> E PackageManager: Install failed: INSTALL_FAILED_BAD_APK
> W PackageManager: zip verification failed for /data/app/vmdl123.tmp/base.apk
> ```

> **根因诊断命令**:
> ```bash
> # Step 1:用 zipinfo 看 ZIP 结构
> $ zipinfo -v app.apk | tail -20
> End-of-central-directory record:
>   actual offset: 0 NOT FOUND  # ← EOCD 缺失!
> # Step 2:用 unzip -t 看 ZIP 完整性
> $ unzip -t app.apk
> error:  cannot find End-of-central-directory record
> # Step 3:看 APK 末尾字节
> $ hexdump -C app.apk | tail -3
> 0001fff0  XX XX XX XX 50 4b 03 04 XX XX XX XX  # 末尾字节被加固 SDK 篡改
> # Step 4:对比未加固 APK(绕过加固 SDK 测试)
> $ aapt2 dump badging app-unsigned.apk | head -5
> ```

> **修复 commit-style diff**:
> ```diff
> - # build.gradle.kts 旧(用 360 加固 v3.4.0,不兼容 Android 14)
> - apply plugin: 'qihu360'
> + # build.gradle.kts 新(用 360 加固 v4.0.0,适配 Android 14)
> + apply plugin: 'qihu360'
> + ext {
> +     qihu360Version = "4.0.0"  // 升级加固 SDK
> + }
> + # 或者改用其他加固方案,如腾讯乐固、阿里聚安全
> ```
> **修复后**:安装正常,Android 14 上 ZIP 校验通过。**架构师要注意**:加固 SDK 是 APK 链路上"非标准"环节,Android 大版本升级时**必须先验证加固 SDK 兼容性**。

> **架构师视角**:APK 是 **"伪装成 ZIP 的特殊容器"** —— 它的 ZIP 末尾承载了 APK 签名 v2/v3,所以加固 SDK 不能随意改 ZIP 末尾。**Android 14 加强 ZIP 校验**后,任何改 EOCD/签名的加固方案都必须适配。

**这就是本篇要讲清楚的事。**

### 0.2 APK 容器在 PLE 8 阶段中的位置

```
阶段 0:execve 入口(内核)              ← PLE 02
    ↓
阶段 1:linker64 加载 .so                ← PLE 03-05
    ↓
阶段 2:JNI_OnLoad 启动 ART              ← PLE 05
    ↓
阶段 3:Zygote fork                       ← PLE 12
    ↓
阶段 4:ActivityThread.main()
    ↓
阶段 5:ClassLoader 加载 base.apk        ← PLE 06-09
    ├─ mmap base.apk
    ├─ 找到 classes.dex
    └─ DEX 加载 + Verify + Init
    ↓
阶段 6:Resources 加载                    ← PLE 10
    ├─ mmap base.apk
    ├─ 找到 resources.arsc
    └─ arsc 解析 → ResTable
    ↓
**本篇:APK 容器 = ZIP + arsc + classes.dex + 签名 + .so**
```

**APK 容器是 PLE 阶段 5-6 的"前置"**——DEX 加载和资源加载都依赖它能正确解析 APK。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 解释 APK = ZIP + 多个组件
2. 描述 ZIP 格式的 3 个关键结构
3. 解释 Android 签名 v1/v2/v3 的位置和工作机制
4. 描述 arsc 在 APK 中的角色
5. 诊断 APK 解析失败类问题

---

## 1. APK 的本质:ZIP 容器

### 1.1 APK = ZIP + 多个组件

**APK 本质是 ZIP 容器**,里面装了 Android App 所需的所有文件:

```
base.apk (ZIP 容器)
├── AndroidManifest.xml    ← 应用清单(编译后是二进制)
├── classes.dex            ← Java/Kotlin 字节码
├── classes2.dex           ← (multidex) 第二个 DEX
├── resources.arsc         ← 资源索引
├── res/                   ← 资源文件
│   ├── layout/xxx.xml     ← 布局
│   ├── drawable/xxx.png   ← 图片
│   ├── mipmap/ic_launcher ← 图标
│   └── values/strings.xml ← 字符串(已编译)
├── assets/                ← 任意文件(AssetManager.open 读取)
├── lib/                   ← 原生库
│   ├── arm64-v8a/libfoo.so
│   ├── armeabi-v7a/libfoo.so
│   └── x86_64/libfoo.so
├── META-INF/              ← 签名信息
│   ├── CERT.RSA
│   ├── CERT.SF
│   └── MANIFEST.MF
├── resources.arsc         ← 资源索引(再次出现,可能没在根目录)
└── ... (其他文件)
```

**关键事实**:
- **APK 是标准 ZIP**(可以用 `unzip` 解压)
- **APK 内部有特定目录结构**(Android 规定的)
- **APK 包含 4 类核心内容**:清单、DEX、资源、原生库

### 1.2 APK 的 4 个核心组件

| 组件 | 路径 | 作用 | 加载器 |
|---|---|---|---|
| **AndroidManifest.xml** | 根目录 | App 元数据 + 组件声明 | PackageParser |
| **classes.dex** | 根目录(或 classes2.dex 等) | Java/Kotlin 字节码 | ART ClassLoader |
| **resources.arsc** | 根目录 | 资源索引 | AssetManager |
| **res/ + assets/** | 多个路径 | 资源文件 + 任意文件 | AssetManager |
| **lib/<abi>/** | 子目录 | 原生库 | Bionic linker |
| **META-INF/** | 子目录 | 签名 | PackageManager |

**架构师必记**:**APK 的每个组件都有自己的"加载器"**:
- AndroidManifest → PackageParser
- classes.dex → ART ClassLoader
- resources.arsc → AssetManager
- lib/*/lib*.so → Bionic linker
- META-INF → PackageManager(签名验证)

### 1.3 用 unzip 查看 APK 内容

```bash
$ unzip -l app.apk
Archive:  app.apk
  Length      Date    Time    Name
---------  ---------- -----   ----
     1234  2024-01-01 00:00   AndroidManifest.xml
  1234567  2024-01-01 00:00   classes.dex
   234567  2024-01-01 00:00   classes2.dex
   567890  2024-01-01 00:00   resources.arsc
      ...
  1234567  2024-01-01 00:00   res/mipmap-xxxhdpi/ic_launcher.png
   123456  2024-01-01 00:00   lib/arm64-v8a/libnative.so
   234567  2024-01-01 00:00   lib/arm64-v8a/libfoo.so
     1234  2024-01-01 00:00   META-INF/MANIFEST.MF
     1234  2024-01-01 00:00   META-INF/CERT.SF
     1234  2024-01-01 00:00   META-INF/CERT.RSA
  1234567  2024-01-01 00:00   assets/data.bin
```

**架构师视角**:**unzip -l 是诊断 APK 问题的最常用命令**。

---

## 2. ZIP 格式详解

### 2.1 ZIP 的 3 个关键结构

**ZIP 文件由 3 个部分组成**(必须都有):

```
ZIP 文件:
├─ Local File Headers + 文件数据(多个)
│   ├─ Local File Header 1
│   ├─ 文件数据 1
│   ├─ Local File Header 2
│   ├─ 文件数据 2
│   └─ ...
├─ Central Directory(中央目录,所有文件的索引)
│   ├─ Central Directory Entry 1
│   ├─ Central Directory Entry 2
│   └─ ...
└─ End of Central Directory Record(EOCD)
    └─ 指向 Central Directory 起始位置
```

**关键事实**:
- **Local File Header 在每个文件前面**(局部信息)
- **Central Directory 在文件末尾**(全局索引)
- **EOCD 在 ZIP 最末尾**(中央目录的"地址")

### 2.2 Local File Header(本地文件头)

**每个文件前面都有 Local File Header**(30 字节起):

```c
// ZIP 规范
struct LocalFileHeader {
    uint32_t signature;        // 0x04034b50("PK\x03\x04")
    uint16_t version_needed;   // 需要的解压版本
    uint16_t flags;            // 标志位
    uint16_t compression;      // 0=store, 8=deflate
    uint16_t mod_time;         // 修改时间
    uint16_t mod_date;         // 修改日期
    uint32_t crc32;            // CRC-32 校验
    uint32_t compressed_size;  // 压缩后大小
    uint32_t uncompressed_size; // 原始大小
    uint16_t filename_length;   // 文件名长度
    uint16_t extra_length;      // 扩展字段长度
    char filename[];           // 文件名
    char extra[];              // 扩展字段
    // 后面是文件数据
};
```

**关键事实**:
- **signature = 0x04034b50**("PK\x03\x04" = Phil Katz)
- **compression = 0**(store,无压缩)或 **8**(deflate,默认)
- **crc32 校验文件完整性**

### 2.3 Central Directory(中央目录)

**Central Directory 是 ZIP 的"目录"**(每个文件一个条目,46 字节起):

```c
struct CentralDirEntry {
    uint32_t signature;        // 0x02014b50("PK\x01\x02")
    uint16_t version_made;     // 制作版本
    uint16_t version_needed;   // 需要的解压版本
    uint16_t flags;
    uint16_t compression;
    uint16_t mod_time;
    uint16_t mod_date;
    uint32_t crc32;
    uint32_t compressed_size;
    uint32_t uncompressed_size;
    uint16_t filename_length;
    uint16_t extra_length;
    uint16_t comment_length;   // 注释长度
    uint16_t disk_start;       // 起始磁盘号
    uint16_t internal_attrs;   // 内部属性
    uint32_t external_attrs;   // 外部属性
    uint32_t local_header_offset;  // ← 关键!指向 Local File Header
    char filename[];
    char extra[];
    char comment[];
};
```

**关键事实**:
- **local_header_offset 指向 Local File Header**
- **Central Directory 顺序 = Local File Header 顺序**(一般)
- **Central Directory 是 ZIP 索引的核心**

### 2.4 End of Central Directory Record(EOCD)

**EOCD 在 ZIP 最末尾**(22 字节起):

```c
struct EndOfCentralDir {
    uint32_t signature;        // 0x06054b50("PK\x05\x06")
    uint16_t disk_number;      // 磁盘号
    uint16_t disk_with_cd;     // 中央目录起始磁盘
    uint16_t cd_entries_here;  // 本磁盘的条目数
    uint16_t cd_entries_total; // 总条目数
    uint32_t cd_size;          // 中央目录大小
    uint32_t cd_offset;        // ← 关键!中央目录的偏移
    uint16_t comment_length;   // ZIP 注释长度
    char comment[];            // ZIP 注释
};
```

**关键事实**:
- **signature = 0x06054b50**("PK\x05\x06")
- **cd_offset 指向 Central Directory 起始位置**
- **EOCD 是 ZIP 的"入口"——从它开始找到所有文件**

### 2.5 ZIP 解析流程

**Android 解析 ZIP 的流程**:

```c
// system/core/libziparchive/ZipArchive.cpp(简化)
bool OpenArchive(const char* path, ZipArchive* archive) {
    // 1. mmap 整个文件
    void* map = mmap(NULL, file_size, PROT_READ, MAP_PRIVATE, fd, 0);
    
    // 2. 找到 EOCD(从文件末尾向前找)
    //    EOCD 的 signature 是固定的 0x06054b50
    EOCD* eocd = FindEOCD(map, file_size);
    if (eocd == nullptr) return false;
    
    // 3. 读 Central Directory
    void* cd_start = (uint8_t*)map + eocd->cd_offset;
    int cd_count = eocd->cd_entries_total;
    
    // 4. 遍历 Central Directory
    for (int i = 0; i < cd_count; i++) {
        CentralDirEntry* entry = (CentralDirEntry*)((uint8_t*)cd_start + offset);
        // 4.1 读 entry 信息
        // 4.2 用 local_header_offset 找到 Local File Header
        LocalFileHeader* lfh = (LocalFileHeader*)((uint8_t*)map + entry->local_header_offset);
        // 4.3 把文件名、大小、offset 等保存到 archive
    }
    
    return true;
}
```

**关键事实**:
- **mmap 整个 ZIP 文件**(整文件加载)
- **从 EOCD 开始反向查找**(EOCD 在文件末尾)
- **Central Directory 提供完整索引**

### 2.6 真实案例:ZIP 解析失败

**回到 §0.1**:某加固 SDK 在 ZIP 末尾添加"原始字节",覆盖了 EOCD。

**ZIP 解析为什么会失败**:

```
正常 ZIP:
[文件数据][Central Directory][EOCD 0x06054b50]
                                         ↑ EOCD 标志

被加固的 ZIP:
[文件数据][Central Directory][原始字节 XXX][0x06054b50]
                                                  ↑ 看起来像 EOCD,但其实不是
                                                  (signature 巧合)
```

**Android 14 修复**:严格校验 EOCD 周围的字节(不能"偶然"匹配)。

**修复**:
- 加固 SDK 升级(避免在 ZIP 末尾添加数据)
- 或改用 v2/v3 签名替代

**架构师必记**:**APK 解析对 ZIP 格式非常敏感**。**任何"非标准"的 ZIP 处理都可能导致解析失败**。

---

## 3. Android 签名机制

### 3.1 Android 签名的 3 个版本

**Android 有 3 个签名版本**——它们在 APK 中的位置和工作方式都不同:

| 版本 | 位置 | 校验时机 | 速度 |
|---|---|---|---|
| **v1 (JAR)** | META-INF/MANIFEST.MF + .SF + .RSA | 安装时 | 慢(逐个文件 SHA-1) |
| **v2** | ZIP 中央目录之前(APK Signing Block) | 安装时 | 快(整 APK 校验) |
| **v3** | v2 之上,支持密钥轮换 | 安装时 | 更快(增量校验) |

**关键事实**:
- **v1 在 META-INF 目录里**(META-INF 是 ZIP 内的标准目录)
- **v2/v3 在 ZIP 的"APK Signing Block"里**(不在标准 ZIP 结构中)
- **Android 7+ 默认用 v2,Android 9+ 默认用 v3**

### 3.2 v1 签名:JAR 签名

**v1 签名是传统 JAR 签名,Android 7 之前唯一支持的方式**:

```
META-INF/
├── MANIFEST.MF      ← 每个文件的 SHA-1
├── CERT.SF          ← MANIFEST.MF 的签名
└── CERT.RSA         ← 证书 + 签名
```

**v1 签名的过程**:
1. 对 APK 内每个文件计算 SHA-1
2. 把所有 SHA-1 写入 MANIFEST.MF
3. 对 MANIFEST.MF 签名,得到 CERT.SF
4. 用证书对 CERT.SF 签名,得到 CERT.RSA

**v1 签名的问题**:
- 逐个文件 SHA-1(慢,大 APK 几十秒)
- 不防"重打包"攻击(可以改 APK 内的文件,重新签名)
- Android 7 之前唯一支持的方式

### 3.3 v2 签名:APK Signing Block

**v2 签名是 Google 2016 年为 Android 7 引入**,解决了 v1 的问题:

```
ZIP 文件结构(带 v2 签名):
[文件数据][Central Directory][APK Signing Block][EOCD]
                                ↑
                                含 v2 签名
```

**v2 签名块的结构**:

```
APK Signing Block:
├─ size_of_block (8 字节)  ← 整个块的大小
├─ id-value pairs           ← 多个键值对
│   ├─ id=0x7109871a (APK_SIGNATURE_SCHEME_V2_BLOCK_ID)
│   │   └─ v2 签名数据
│   ├─ 其他可选 id
│   └─ ...
└─ magic (16 字节) = "APK Sig Block 42"  ← 用于从 EOCD 找到这个块
```

**v2 签名的过程**:
1. 把整个 APK(从 start 到 Central Directory 结束)的内容计算 SHA-256
2. 用私钥签名这个 SHA-256 哈希
3. 把签名数据放在 APK Signing Block 里

**v2 签名的优势**:
- 整 APK 校验(快,几毫秒)
- 防"重打包"攻击(任何文件改动都会被检测)
- 校验更严格

### 3.4 v3 签名:密钥轮换

**v3 签名是 Android 9 引入**,支持密钥轮换:

**v3 vs v2 的差异**:
- v3 在 v2 基础上增加"密钥轮换支持"
- v3 记录"祖先"签名,可以追溯到原始密钥
- 当密钥更换时,新 APK 可以用新密钥 + 旧密钥的"支持记录"

**v3 的工作流程**:
1. App 第一次签名(用密钥 A)
2. 密钥 A 即将过期,生成"密钥轮换记录"(用 A 签名)
3. 之后用新密钥 B 签名
4. v3 校验时,可以验证 B 是 A 的合法继承者

**架构师必记**:**v3 是为了解决"密钥过期但 App 还在用"的问题**。

### 3.5 真实案例:签名验证失败

**症状**:
```
E PackageManager: Failed to install com.example.app: 
    INSTALL_FAILED_UPDATE_INCOMPATIBLE: 
    Package com.example.app signatures do not match the previously installed version
```

**根因**:
- App 升级时,签名密钥和旧版本不匹配
- Android 强制要求"升级必须用相同密钥"

**修复**:
- 用原密钥重新签名
- 或卸载旧版本,作为新 App 安装

### 3.6 签名验证流程

**Android 14 验证 APK 签名的流程**:

```
PackageManager.installPackage():
    ↓
1. 解析 APK(读 ZIP 解析)
    ↓
2. 找 APK Signing Block
    ├─ v3 块(Android 9+)→ 验证 v3
    ├─ v2 块(Android 7+)→ 验证 v2
    └─ v1 块(旧 APK)→ 验证 v1
    ↓
3. 校验签名
    ├─ 用证书公钥验证签名
    └─ 用证书链验证证书(到 CA 根)
    ↓
4. 检查密钥白名单
    ├─ 系统 App → 系统密钥
    └─ 普通 App → 自签名
    ↓
5. 检查权限
    ├─ signatureOrSystem 权限 → 签名匹配
    └─ signature 权限 → 签名匹配
```

**架构师必记**:**Android 14 严格签名校验,任何不一致都拒绝安装**。

---

## 4. arsc 在 APK 中的位置

### 4.1 arsc 是 ZIP 内的一个文件

**resources.arsc 是 APK ZIP 里的一个文件**:

```
base.apk
├── classes.dex
├── resources.arsc        ← 在 ZIP 根目录
├── res/
├── lib/
└── ...
```

**arsc 的访问**:
- AssetManager 通过 ZIP 中央目录找到 `resources.arsc` 的位置
- 读其内容(整文件 mmap 或 read)
- 解析为 ResTable

**真实代码**(AssetManager.cpp 简化):

```cpp
// 在 ApkAssets::Load 中
ZipEntry arsc_entry;
if (!zip_handle->FindEntry("resources.arsc", &arsc_entry)) {
    return nullptr;  // 找不到 arsc
}

auto arsc_data = zip_handle->UncompressEntry(arsc_entry);
// 用 arsc_data 创建 ResTable
```

### 4.2 arsc 文件大小

**arsc 文件大小 = 资源数 × 平均每资源字节数**:

| App 规模 | 资源数 | arsc 大小 |
|---|---|---|
| 小 | 5000 | 200-500KB |
| 中 | 20000 | 1-3MB |
| 大 | 80000 | 3-10MB |
| 超大 | 300000 | 10-30MB |

**架构师必记**:**arsc 大小 ≈ 资源数 × 100-200 字节**。**减少资源数 = 减少 arsc 大小 = 减少冷启动期**。

### 4.3 arsc 解析性能

**arsc 解析耗时**(本系列 P10 §5.3):

| arsc 大小 | 资源数 | 解析耗时 |
|---|---|---|
| 500KB | 5000 | 10-30ms |
| 2MB | 20000 | 30-100ms |
| 8MB | 80000 | 100-300ms |

**关键事实**:
- **arsc 解析是冷启动期 100-300ms 的来源**
- **优化方向** = 减少资源数 + R8 资源压缩 + aapt2 optimize

---

## 5. aapt2 编译流程

### 5.1 aapt2 是什么

**aapt2(Android Asset Packaging Tool 2)** 是 Android 资源编译器,把资源源文件编译为 APK 内的二进制格式。

**aapt2 工作流程**:

```
1. 资源源文件(扩展名 .xml / .png / .arsc / .txt)
    ↓
2. aapt2 compile (单个文件编译)
    ├─ .xml → 二进制 XML(AXML)
    ├─ .png → 优化 PNG
    ├─ .txt → flat buffer
    └─ ...
    ↓ 输出:.flat 文件(每个资源一个)
3. aapt2 link (链接)
    ├─ 把所有 .flat 链接成一个 arsc
    ├─ 生成 R.java(R.id 常量)
    ├─ 生成资源索引
    └─ 生成 AndroidManifest.xml(编译后)
    ↓ 输出:base.apk
```

### 5.2 aapt2 compile vs link

**aapt2 分为两步**:

| 步骤 | 作用 | 输入 | 输出 |
|---|---|---|---|
| **compile** | 单个资源编译 | .xml / .png / 资源 | .flat 文件 |
| **link** | 资源链接 | 多个 .flat + R.txt | base.apk + R.java |

**优势**:
- **compile 可以并行**(每个资源独立)
- **link 集中处理**(生成完整 arsc)
- **增量编译**(只重新编译修改的资源)

### 5.3 R.java 生成

**aapt2 link 阶段生成 R.java**:

```java
// R.java
public final class R {
    public static final class string {
        public static final int app_name = 0x7f0a0001;  // ← 自动生成
        public static final int hello = 0x7f0a0002;
    }
    public static final class drawable {
        public static final int ic_launcher = 0x7f0c0001;
    }
    public static final class layout {
        public static final int activity_main = 0x7f0d0001;
    }
}
```

**关键事实**:
- **R.java 在编译时生成**
- **R.id 是常量,不是变量**
- **R.id = 0x7f0a0001 等**(本系列 P10 §4.3 详述)
- **R8 不 strip R.id**(被 Java 代码引用)

### 5.4 资源 ID 分配算法

**aapt2 给资源分配 ID 的算法**:

```
0x7fXXYYYY
│  │└──┘
│  │   └─── YYYY = entry 索引
│  └────── XX = type id(0x0a = string, 0x0b = drawable, etc.)
└────────── 7f = package id(应用)
```

**type id 分配**:
- 0x01 = attr
- 0x02 = drawable
- 0x03 = layout
- 0x04 = color
- 0x05 = dimen
- 0x06 = id
- 0x07 = string
- 0x08 = style
- 0x09 = bool
- 0x0a = integer
- 0x0b = array
- 0x0c = plurals
- 0x0d = fraction
- 0x0e = mipmap
- 0x0f = animator
- 0x10 = xml
- ...

**架构师必记**:**type id 是固定的**——aapt2 按字母序分配。

### 5.5 aapt2 optimize(高级优化)

**aapt2 optimize** 是 post-build 优化,可以做更激进的处理:

```bash
$ aapt2 optimize \
    --shorten-resource-paths \      # 缩短资源路径
    --collapse-resource-names \    # 折叠资源名
    --enable-sparse-encoding \     # 启用稀疏编码
    --resources-config-path config.txt \  # 指定保留的资源
    -o app-optimized.apk \
    app.apk
```

**优化效果**:
- **路径缩短**:`res/drawable-hdpi/ic_launcher.png` → `res/X_.png`(节省 1-3MB)
- **名称折叠**:`string/app_name` → `s/0`(节省 arsc 大小)
- **稀疏编码**:去除未使用资源
- **总优化**:20-50% APK 体积

**架构师必记**:**aapt2 optimize 是大型 App 必备工具**。**和 R8 配合使用效果更佳**。

---

## 6. split APK / Bundle / Dynamic Feature

### 6.1 split APK

**split APK 是"按维度拆分 APK"**——同一个 App 的不同变体作为不同 APK 安装:

| 拆分维度 | 示例 |
|---|---|
| **ABI** | base-arm64.apk / base-armeabi.apk / base-x86.apk |
| **Density** | base-xxhdpi.apk / base-xxxhdpi.apk |
| **Language** | base-zh.apk / base-en.apk |
| **SDK version** | base-21.apk / base-26.apk |

**加载机制**:
- PackageManager 安装时根据设备选择合适的 split
- 启动时把所有 split 的 DEX 合并为一个 PathClassLoader
- 资源类似,把多个 split 的 arsc 合并

### 6.2 App Bundle(.aab)

**App Bundle(.aab)** 是 Google 推荐的"分包格式":
- 上传时是 .aab
- Google Play 根据设备生成 split APK
- 用户下载的是优化后的 split APK

**.aab 包含**:
- base.apk(主模块)
- x86 / x86_64 / armeabi-v7a / arm64-v8a(ABI splits)
- hdpi / xhdpi / xxhdpi / xxxhdpi(密度 splits)
- en / zh / ja / ...(语言 splits)
- ... (任意维度 splits)

**架构师必记**:**App Bundle 节省用户下载体积 30-50%**。**但需要 Play Store 支持**。

### 6.3 Dynamic Feature(动态功能)

**Dynamic Feature 是 Google Play 的"按需下载"机制**:

```
App 启动时
    ↓
1. base APK 加载
    ↓
2. 首次访问 dynamic_feature 时
    ├─ 检查是否已下载
    ├─ 未下载 → 触发 Play Store 下载
    └─ 下载完成 → 加载
    ↓
3. dynamic_feature 的 DEX + 资源合并到 PathClassLoader
```

**优势**:
- base APK 体积小(10-20MB)
- 按需下载功能(App 启动快)
- 用户只用到的功能才下载

**挑战**:
- 需要 Play Store 支持
- 动态加载 ClassLoader 复杂
- 资源 ID 可能冲突

### 6.4 真实案例:Bundle 资源冲突

**症状**:
- App Bundle 拆分后,某些资源找不到
- `Resources$NotFoundException: Drawable ID #0x7f0c0001`

**根因**:
- base APK 的 R.java 和 dynamic feature 的 R.java 都生成 `0x7f0c0001`
- 但它们指向不同资源
- 合并时 ID 冲突

**修复**:
- 用 R8 混淆资源 ID(`-allowobfuscation`)
- 资源 ID 用 `R.drawable.feature_xxx` 避免冲突
- 拆分更细的 dynamic feature

**架构师必记**:**Bundle/Dynamic Feature 引入的"ID 冲突"是常见问题**。**必须用 R8 混淆或拆分 R 文件**。

---

## 7. APK 解析的常见故障

### 7.1 5 类 APK 解析故障

| 故障 | 触发条件 | 错误 |
|---|---|---|
| **ZIP 损坏** | EOCD 找不到 | `End of Central Directory not found` |
| **签名验证失败** | 证书不匹配 | `INSTALL_FAILED_UPDATE_INCOMPATIBLE` |
| **arsc 损坏** | 文件截断 / CRC 错误 | `Failed to parse resources` |
| **AndroidManifest 损坏** | 编译失败 | `Failed to parse manifest` |
| **DEX 损坏** | 文件截断 / magic 错误 | `Failed to load DEX` |

### 7.2 真实案例:ZIP 损坏

**症状**(回到 §0.1):
```
java.util.zip.ZipException: End of Central Directory not found
```

**诊断**:

```bash
# 1. 用 unzip 测试 ZIP 完整性
$ unzip -t app.apk
# 输出:ERROR: bad signature 或 ERROR: cannot find EOCD

# 2. 用 zipinfo 看 ZIP 头
$ zipinfo app.apk | head -20
# 如果没有输出 → ZIP 损坏

# 3. 看 ZIP 的最后 22 字节(应该是 EOCD)
$ hexdump -C app.apk | tail -5
# 应该看到 0x06054b50
# 如果不是 → ZIP 损坏
```

**修复**:
- 重新打包 APK(标准 ZIP 工具)
- 避免用"加固 SDK"在 ZIP 末尾添加数据

### 7.3 真实案例:签名升级失败

**症状**:
```
INSTALL_FAILED_UPDATE_INCOMPATIBLE: Signatures do not match
```

**根因**:
- App 升级时,签名和旧版本不匹配

**修复**:
```bash
# 用 apksigner 重新签名(用原密钥)
$ apksigner sign --ks keystore.jks --out app-signed.apk app.apk

# 看 APK 当前签名
$ apksigner verify --print-certs app.apk
```

### 7.4 真实案例:arsc 损坏

**症状**:
```
E AndroidRuntime: Failed to load resource: Resources$NotFoundException
```

**根因**:
- arsc 文件被截断(下载不完整)
- arsc 文件 CRC 校验失败

**诊断**:

```bash
# 1. 看 arsc 是否在 APK 中
$ unzip -l app.apk | grep arsc

# 2. 解压 arsc 看大小
$ unzip -p app.apk resources.arsc > arsc.bin
$ ls -la arsc.bin

# 3. 看 arsc 头部
$ hexdump -C arsc.bin | head -1
# 应该看到 0x00000002(ResTable 类型)
```

---

## 8. 架构师视角:APK 容器的 5 个核心洞察

### 8.1 洞察 1:APK 是 ZIP + 多个组件的容器

**APK 不是单一文件,是 ZIP 容器内的 6 个核心组件**:
- AndroidManifest.xml
- classes.dex (含 classes2.dex 等)
- resources.arsc
- res/ + assets/
- lib/<abi>/
- META-INF/(签名)

### 8.2 洞察 2:Android 14 严格 ZIP 校验

**Android 14 严格校验 EOCD、签名、文件完整性**。**任何"非标准" ZIP 处理都可能导致解析失败**。

**架构师必记**:**加固 SDK / 第三方优化工具必须用标准 ZIP 工具生成 APK**。

### 8.3 洞察 3:签名是 APK 安全的基础

**v1 / v2 / v3 签名是 Android 安全模型的基础**。**密钥管理 = App 生命周期管理**。

### 8.4 洞察 4:arsc 是 APK 体积的隐形大头

**arsc 通常 1-10MB,占 APK 总体积 5-15%**。**aapt2 optimize + R8 资源压缩 = 节省 20-50%**。

### 8.5 洞察 5:从 APK 故障直接映射到现象

| 故障现象 | APK 根因 |
|---|---|
| `End of Central Directory not found` | ZIP 损坏 |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | 签名不匹配 |
| `Resources$NotFoundException` | arsc 损坏 / R8 strip |
| `ClassNotFoundException` | DEX 损坏 / R8 strip |
| 安装期 100s+ | arsc + DEX 太大 |

---

## 9. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **APK 是 ZIP + 6 个核心组件** | Manifest + DEX + arsc + res + lib + META-INF |
| 2 | **ZIP 的 3 个关键结构** | Local File Header / Central Directory / EOCD |
| 3 | **Android 14 严格签名校验** | v1 / v2 / v3 三种签名,APK Signing Block |
| 4 | **aapt2 optimize 节省 20-50% 体积** | 路径缩短 + 名称折叠 + 稀疏编码 |
| 5 | **Bundle/Dynamic Feature 节省 30-50% 用户下载** | 按 ABI / density / language 拆分 |

---

## 10. 下一篇预告

12 篇《进程启动全景:Zygote fork → 第一帧》是 PLE 第五篇章(进程启动与跨进程 2 篇)的开篇,会沿着 PLE 01 的"8 阶段流水线"埋下的线索,深入讲:

- Zygote 进程本身的启动:init.rc → app_process -Xzygote
- ZygoteInit.main() 流程:preload + runSelectLoop
- preload 阶段:preloadClasses / preloadResources / preloadSharedLibraries / createSystemServerClassLoader
- ZygoteServer 通信:LocalSocket 协议
- forkAndSpecialize:关键的 fork 调用链
- 子进程初始化:handleChildProc → ZygoteInit.zygoteInit → RuntimeInit
- ActivityThread.main():应用进程内"主线程"的诞生
- 真实案例:用 Perfetto 拆解一次冷启动
- 架构师视角:启动链路上 5 个可优化点

**12 篇预计 1 周后产出**,届时一起发你看。

---

## 附录 A:APK 6 个核心组件

| 组件 | 路径 | 加载器 |
|---|---|---|
| AndroidManifest.xml | 根目录 | PackageParser |
| classes.dex | 根目录 | ART ClassLoader |
| resources.arsc | 根目录 | AssetManager |
| res/ + assets/ | 多个 | AssetManager |
| lib/<abi>/*.so | 子目录 | Bionic linker |
| META-INF/ | 子目录 | PackageManager |

## 附录 B:ZIP 3 个关键结构

| 结构 | 位置 | 作用 |
|---|---|---|
| Local File Header | 每个文件前 | 文件的局部信息 |
| Central Directory | ZIP 末尾 | 全局索引 |
| EOCD | ZIP 最末尾 | 指向 Central Directory |

## 附录 C:Android 3 个签名版本

| 版本 | 位置 | 校验速度 | 引入版本 |
|---|---|---|---|
| v1 (JAR) | META-INF/ | 慢 | 1.0+ |
| v2 | APK Signing Block | 快 | 7.0+ |
| v3 | v2 之上 | 快(支持密钥轮换) | 9.0+ |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 12 进程启动 | Zygote fork 时,APK 被 mmap 到子进程 |
| 14 风险地图 | §7 故障诊断的"5 类根因"是 P14 速查表核心 |

---

> **本篇把 APK 容器拆解到"ZIP 格式 + 签名机制 + arsc + aapt2 + Bundle"5 个维度。**
> **12 篇会在这个基础上,讲 Zygote fork——APK 怎么被加载、进程怎么启动、第一帧怎么渲染。**
> **记住 ZIP 3 结构、Android 14 严格签名校验、aapt2 optimize、Bundle 节省下载,你的 APK 视角就立住了。**
