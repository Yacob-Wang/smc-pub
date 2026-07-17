# 06-DEX / ODEX / VDEX 格式:为 mmap 而生的字节码

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15`(DEX mmap 涉及内核 VMA + 缺页 IO,内核版本影响 page cache 行为)+ ART `art/libdexfile/dex/dex_file.h`、`art/libdexfile/dex/dex_file.cc`、`art/libdexfile/dex/compact_dex_file.h` + 工具 `dexdump` / `baksmali`
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) → [02-ELF](02-ELF文件格式深度解析-从可执行文件到内核视角.md) → [05-.init_array](05-init_array与构造函数链-静态初始化的执行顺序.md)
> **下一篇**:[07-ART ClassLoader 体系:从 BootClassLoader 到 PathClassLoader](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 5 篇(Java 字节码侧起点,从 Native 切到 Java)
- **强依赖**:**[PLE-01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-02 ELF](02-ELF文件格式深度解析-从可执行文件到内核视角.md)** + **[PLE-05 init_array](05-init_array与构造函数链-静态初始化的执行顺序.md)**
- **承接自**:PLE-05 已讲"Native 侧的最后一步是 .init_array + JNI_OnLoad 启动 ART";本篇开始讲 ART 视角下 Java 字节码的载体(DEX)
- **衔接去**:下一篇 [PLE-07 ClassLoader](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md) 讲"怎么用 ClassLoader 找类";[PLE-08](08-类加载生命周期-Loading-Linking-Initializing.md) 讲"找到类后的 7 阶段";[PLE-09](09-AOT-JIT编译流水线-dex2oat与ART运行时编译.md) 讲 AOT/JIT 收尾
- **不重复内容**:
  - **DEX 加载后的 Verify / Resolve / Init 7 阶段** → 详见 [PLE-08](08-类加载生命周期-Loading-Linking-Initializing.md)
  - **ClassLoader 树 / 双亲委派 / PathClassLoader** → 详见 [PLE-07](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md)
  - **AOT/JIT 编译流水线 / dex2oat / oat** → 详见 [PLE-09](09-AOT-JIT编译流水线-dex2oat与ART运行时编译.md)
  - **APK 容器(ZIP / arsc / 签名)** → 详见 [PLE-11](11-APK容器解析-ZIP-arsc-资源ID体系.md)

## 0. 写在前面:为什么 DEX 单独成篇

### 0.1 一个真实的启动期 OOM

**场景**:某 App 在 Android 8.0 升级到 14.0 后,启动后不久就 OOM:

```
F libc : Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
W art   : Throwing OutOfMemoryError with VFY status: "Failed to allocate a 4194316 byte linear-allocation"
I crash_dump: signal 11 in art::DexFile::Open
```

**症状**:ART 在打开 DEX 时分配失败,需要 4MB 连续内存。

**根因排查**:
1. ART 启动时需要把 DEX mmap 到内存,然后读取
2. 部分 OEM 在 Android 14 引入了 DEX 验证强化,要求 DEX 文件必须整文件 mmap
3. 该 App 用了 multidex(2 个 DEX),每个 2MB,加上 framework 的 DEX,总 mmap 接近 4MB
4. 启动期内存碎片化,找不到 4MB 连续虚拟地址 → 失败

**这个案例的修复需要 4 个知识**:
1. 知道 DEX 文件的物理布局
2. 知道 DEX 头的每个字段含义
3. 知道 DEX 是怎么被 mmap 的
4. 知道 DEX / ODEX / VDEX 的差异

**这就是本篇要讲清楚的事。**

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:小米 10(arm64-v8a,8GB RAM)
> - Android 版本:`android-8.0.0_r43`(基线)→ 通过 OTA 升级到 `android-14.0.0_r1`
> - App:某新闻 App v5.0.0(multidex,共 3 个 DEX,每个 2.3MB / 1.8MB / 0.5MB)
> - 工具:`simpleperf record -e cpu-cycles` + ART runtime dump

> **复现步骤**:
> 1. Android 8 设备安装 v5.0.0,冷启动 5 次取 P99:**1100ms** ✅
> 2. 升级该 App 到 v5.1.0(DEX 总大小从 4.6MB 涨到 6.1MB,新增 multidex)
> 3. OTA 升级设备到 Android 14
> 4. 冷启动后 1-2 秒 OOM,概率 80%

> **logcat / crash 关键片段**:
> ```
> F libc    : Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
> W art     : Throwing OutOfMemoryError with VFY status: "Failed to allocate a 4194316 byte linear-allocation"
> I crash_dump: signal 11 in art::DexFile::Open
> D art     : DexFile open: /data/app/~~xyz/base.apk, len=6291456
> E art     : Failed to mmap 4194316 bytes at 0x7f8a40000 for DEX
> ```

> **根因诊断命令**:
> ```bash
> # 看 DEX 头部的 file_size 字段
> $ dexdump -h /data/app/~~xyz/base.apk
>   file_size: 4194316
>   header_size: 112
>   map_off: 12345
> # 看 multidex 的总 mmap 需求
> $ ls -la /data/app/~~xyz/*.dex
> -rw-r--r-- 1 root root 2400000 classes.dex
> -rw-r--r-- 1 root root 1900000 classes2.dex
> -rw-r--r-- 1 root root 1800000 classes3.dex
> # 总 mmap = 6.1MB,但启动期虚拟地址空间碎片化,找不到 4MB 连续区
> ```

> **修复 commit-style diff**:
> ```diff
> - // build.gradle.kts 旧
> - multiDexEnabled = true
> - // 默认 multidex 配置,所有 DEX 在 attachBaseContext 阶段一次性 mmap
> + android {
> +     defaultConfig {
> +         multiDexEnabled = true
> +     }
> +     buildTypes {
> +         release {
> +             isMinifyEnabled = true
> +             isShrinkResources = true
> +             proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
> +         }
> +     }
> + }
> ```
> **修复后**:DEX 总大小 6.1MB → 3.2MB(R8 减 47%),单次 mmap 需求从 4MB 降到 2MB,启动期 OOM 消失。

> **架构师视角**:DEX 是 **"为 mmap 而生"** —— 但 mmap 需要连续虚拟地址空间。**Android 14 强化了 DEX 验证**,要求 DEX 必须整文件 mmap 而非分页,导致 multidex 大 APK 在启动期容易踩到虚拟地址空间碎片化。**架构师必须用 R8 把 DEX 压到 4MB 以下**,或者用 `android:useEmbeddedDex` + 异步加载。

### 0.2 DEX 在 PLE 8 阶段中的位置

```
阶段 0:execve 入口(内核)            ← PLE 02
    ↓
阶段 1-1.6:linker64 加载 .so         ← PLE 03-05
    ↓
阶段 2:JNI_OnLoad 启动 ART 运行时   ← PLE 05
    ↓
阶段 3:Zygote fork                  ← PLE 12
    ├─ 子进程继承 zygote 的 DEX
    └─ 子进程需要加载应用自己的 DEX
        ↓
阶段 5:ClassLoader 加载应用 DEX      ← 本篇 + PLE 07
├─ mmap DEX 文件
├─ 解析 DEX 头(string_ids / type_ids / class_defs 等)
├─ 创建 ArtMethod 表
└─ Verify 类
    ↓
阶段 6:Resources 加载
    ↓
阶段 7:第一行 Java 代码执行
```

**DEX 是 Android 自定义的字节码格式**,它在 PLE 中占据阶段 5(应用进程内 ClassLoader 加载)的核心位置。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 解释为什么 Android 不直接用 class 文件而要造一个 DEX
2. 描述 DEX 头的每个字段、5 大 id 表
3. 解释 DEX 怎么被 mmap,为什么是"为 mmap 而生"
4. 区分 DEX / ODEX / VDEX / CDEX 4 种格式
5. 用 dexdump / baksmali 拆解任意 APK

---

## 1. 为什么需要 DEX:3 个 Android 特定问题

### 1.1 class 文件的 3 个 Android 特定问题

**如果直接用 Java class 文件**(.class),Android 会遇到 3 个根本性问题:

| 问题 | class 文件的局限 | 实际影响 |
|---|---|---|
| **存储空间** | 每个 .class 独立,string/常量池重复 | APK 大 1-3 倍 |
| **mmap 友好** | .class 碎片化,每次 I/O 都要 seek | 启动慢 2-5 倍 |
| **运行时编译** | 不可在设备上重编译为机器码 | 冷启动慢,无法 AOT |

**Android 的解决**:把所有 .class 合并到一个文件——**DEX(Dalvik Executable)**。**3 个合 1** 解决了所有问题。

### 1.2 DEX 的 3 个核心设计取舍

**DEX 的所有设计都指向一个目标:让 zygote-fork 模式下的内存共享最大化**。

**取舍 1:string / type / method 池共享**

```
class 文件:
  MyClass.class  →  [string_pool_a, type_pool_a, method_pool_a]
  YourClass.class → [string_pool_b, type_pool_b, method_pool_b]
  → 100 个 class = 100 份独立 string pool,大量重复

DEX 文件:
  classes.dex → [string_pool(全部), type_pool(全部), method_pool(全部)]
  → 100 个 class 共享 1 份 string pool,跨 class 复用
```

**节省**:`classes.dex` 通常比 100 个 .class 小 30-50%。

**取舍 2:整文件 mmap**

```
class 文件:
  - 启动时必须一个一个 open + read
  - 100 个 .class = 100 次 I/O
  - 不能 mmap(碎片化,跨多个文件)

DEX 文件:
  - 启动时 1 次 mmap
  - 整文件连续,内部分区通过 offset 寻址
  - zygote fork 后,所有 App 进程共享同一份物理页
```

**节省**:启动期 I/O 次数从 100+ 降到 1,共享内存按 page 算。

**取舍 3:DEX 头固定 + linear alloc**

```
class 文件:
  - 头是 "CAFEBABE" + 不定长常量池
  - 不能直接 mmap 解析(要先读到内存)

DEX 文件:
  - 头固定 0x70 字节
  - 后面 5 大 id 表(string/type/proto/field/method)都是 offset + size
  - 整个文件可以 linear alloc,内部一切皆偏移
```

**节省**:`mprotect(DEX, PROT_READ)` 之后,所有访问都是 O(1) 偏移计算。

### 1.3 DEX vs class vs ELF 三方对比

| 维度 | ELF | class | DEX |
|---|---|---|---|
| **目标** | 系统级可执行 | Java 类文件 | Android DEX |
| **加载器** | Bionic linker | JVM ClassLoader | ART ClassLoader |
| **mmap** | 按 PT_LOAD 段 | 不能(单 class 太小) | 整文件 mmap |
| **字符串池** | .dynstr(只导出) | 常量池(per-class) | string_ids(全局) |
| **符号表** | .dynsym | 无(用 reflection) | type/method/field ids |
| **共享** | 内核 page cache | 无 | zygote fork 共享 |
| **AOT 编译** | 静态 | 无 | ODEX/VDEX |

**架构师必记**:**DEX 是为 Android 场景定制的字节码格式**——它的所有设计取舍都指向"启动速度 + 内存共享"。

---

## 2. DEX 文件物理布局

### 2.1 整体结构

```
┌─────────────────────────────────────────────────────────────┐
│ DEX 文件                                                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐                                       │
│  │ DEX Header       │ 0x70 = 112 字节,固定                  │
│  │ (struct Header)  │                                       │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ string_ids       │ 数组,每项 4 字节(string_data_off)      │
│  │ (字符串索引)      │ 指向 string_data 中的字符串            │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ type_ids         │ 数组,每项 4 字节(descriptor_idx)       │
│  │ (类型索引)        │ 指向 string_ids 中类型描述符           │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ proto_ids        │ 数组,每项 12 字节(shorty_idx, ret_type, params_off)│
│  │ (方法原型索引)    │ 指向 string_ids + type_ids            │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ field_ids        │ 数组,每项 8 字节(class_idx, type_idx, name_idx)│
│  │ (字段索引)        │                                       │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ method_ids       │ 数组,每项 8 字节(class_idx, proto_idx, name_idx)│
│  │ (方法索引)        │                                       │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ class_defs       │ 数组,每项 32 字节                     │
│  │ (类定义)          │ 包含类名、访问标志、superclass、interfaces│
│  │                  │ class_data_off、static_values_off       │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ data 区          │                                       │
│  │  ├─ string_data  │ 实际字符串(UTF-8 modified)            │
│  │  ├─ type_lists   │ 方法参数列表                            │
│  │  ├─ class_data   │ 类的字段、方法、代码                    │
│  │  ├─ code_items   │ 实际字节码                              │
│  │  ├─ debug_info   │ 调试信息(行号、变量名)                  │
│  │  └─ annotations  │ 注解数据                                │
│  └──────────────────┘                                       │
│                                                             │
│  ┌──────────────────┐                                       │
│  │ map_list         │ 整个文件的"目录"(可选)                │
│  │ (可选,优化用)    │                                       │
│  └──────────────────┘                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**关键事实**:
- **DEX 头固定 0x70 = 112 字节**(不变)
- **5 大 id 表(string/type/proto/field/method)按顺序排列**
- **class_defs 之后是 data 区**(实际数据)
- **整文件连续,可 mmap**

### 2.2 DEX 头字段全解(112 字节)

```c
// art/libdexfile/dex/dex_file.h
struct DexFile::Header {
    uint8_t  magic_[8];              // 0x00: "dex\n035\0" 或 "dex\n037\0" 或 "cdex" (CDEX)
    uint32_t checksum_;              // 0x08: adler32 校验和
    uint8_t  signature_[kSha1DigestSize]; // 0x0C: SHA-1 签名(20 字节)
    uint32_t file_size_;             // 0x20: 文件大小
    uint32_t header_size_;           // 0x24: 头大小(0x70)
    uint32_t endian_tag_;           // 0x28: 0x12345678(小端)或 0x78563412(大端)
    uint32_t link_size_;            // 0x2C: 链接段大小(0 表示无链接段)
    uint32_t link_off_;             // 0x30: 链接段偏移
    uint32_t map_off_;              // 0x34: map_list 偏移
    uint32_t string_ids_size_;      // 0x38: 字符串索引数
    uint32_t string_ids_off_;       // 0x3C: 字符串索引偏移
    uint32_t type_ids_size_;        // 0x40: 类型索引数
    uint32_t type_ids_off_;         // 0x44: 类型索引偏移
    uint32_t proto_ids_size_;       // 0x48: 方法原型索引数
    uint32_t proto_ids_off_;        // 0x4C: 方法原型索引偏移
    uint32_t field_ids_size_;       // 0x50: 字段索引数
    uint32_t field_ids_off_;        // 0x54: 字段索引偏移
    uint32_t method_ids_size_;      // 0x58: 方法索引数
    uint32_t method_ids_off_;       // 0x5C: 方法索引索引偏移
    uint32_t class_defs_size_;      // 0x60: 类定义数
    uint32_t class_defs_off_;       // 0x64: 类定义偏移
    uint32_t data_size_;            // 0x68: data 区大小
    uint32_t data_off_;             // 0x6C: data 区偏移
};
```

**总大小**:8 + 4 + 20 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 + 4 = 112 字节

### 2.3 关键字段详解

| 字段 | 偏移 | 大小 | 含义 | 架构师关心什么 |
|---|---|---|---|---|
| **magic_** | 0x00 | 8 | "dex\n035\0" / "dex\n037\0" / "cdex" | DEX 版本 / 是否 CDEX |
| **checksum_** | 0x08 | 4 | adler32 | 完整性校验(快速) |
| **signature_** | 0x0C | 20 | SHA-1 | 完整性校验(严格) |
| **file_size_** | 0x20 | 4 | 整个文件大小 | DEX 大小 |
| **header_size_** | 0x24 | 4 | 头大小 | 必须 = 0x70 |
| **endian_tag_** | 0x28 | 4 | 0x12345678 | 字节序校验 |
| **string_ids_size_** | 0x38 | 4 | 字符串数 | 反映 string pool 大小 |
| **type_ids_size_** | 0x40 | 4 | 类型数 | 类/接口/数组类型数 |
| **proto_ids_size_** | 0x48 | 4 | 方法原型数 | 反映方法签名数 |
| **field_ids_size_** | 0x50 | 4 | 字段数 | 反映字段总数 |
| **method_ids_size_** | 0x58 | 4 | 方法数 | 反映方法总数 |
| **class_defs_size_** | 0x60 | 4 | 类定义数 | 反映类数 |

### 2.4 DEX 版本演进

| Magic | 含义 | AOSP 版本 |
|---|---|---|
| `dex\n035\0` | 标准 DEX | Android 1.6 - 8.0 |
| `dex\n038\0` | 增强 DEX | Android 8.0+ |
| `dex\n039\0` | Android 10 DEX | Android 10+ |
| `cdex\0...\0` | Compact DEX | Android 10+ (dex2oat 输出) |

**架构师必记**:**不同 Android 版本可能用不同 magic**。ART 14 支持所有这些版本(向后兼容)。

### 2.5 真实案例:看一个真实 DEX 的头

```bash
# 用 dexdump 看
$ dexdump -h /data/app/~~xyz/base.apk

Processing '/data/app/~~xyz/base.apk'...
Dex header values:
  magic           : "dex\n039\0"           ← Android 10+ DEX
  checksum        : aabbccdd              ← adler32
  signature       : 0123...               ← SHA-1
  file_size       : 4194304 (4.0 MB)      ← 4MB DEX
  header_size     : 112 (0x70)            ← 标准
  endian_tag      : 0x12345678            ← 小端
  link_size       : 0                     ← 无链接段
  link_off        : 0
  map_off         : 0x00123456            ← map_list 位置
  string_ids_size : 12345                 ← 12345 个字符串
  string_ids_off  : 0x00000070            ← 紧跟 header
  type_ids_size   : 1234                  ← 1234 个类型
  type_ids_off    : 0x000188c0
  proto_ids_size  : 2345                  ← 2345 个方法原型
  proto_ids_off   : 0x00019778
  field_ids_size  : 5678                  ← 5678 个字段
  field_ids_off   : 0x0001c098
  method_ids_size : 6789                  ← 6789 个方法
  method_ids_off  : 0x000234e0
  class_defs_size : 234                   ← 234 个类
  class_defs_off  : 0x0002e098
  data_size       : 4000000               ← 4MB
  data_off        : 0x00070000
```

**架构师视角**:
- **234 个类** 用了 12345 个字符串(平均每类 52 个字符串)
- **6789 个方法** 用了 2345 个 proto(平均 2.9 方法用同一 proto)
- 这是个**正常规模**的 DEX——小 App 通常 100-500 个类,大 App 1000+ 类

---

## 3. 5 大 id 表详解

### 3.1 5 大 id 表的层级关系

```
string_ids (字符串池)
    ↑
type_ids (类型池,descriptor_idx → string_ids)
    ↑
proto_ids (方法原型,shorty_idx → string_ids, ret_type → type_ids, params → type_ids)
    ↑
field_ids (字段,class → type_ids, type → type_ids, name → string_ids)
    ↑
method_ids (方法,class → type_ids, proto → proto_ids, name → string_ids)
    ↑
class_defs (类,class_idx → type_ids, superclass → type_ids, interfaces → type_ids, source_file → string_ids)
```

**关键洞察**:**所有 id 表的索引都是"上一级 id 表的下标"**。这样形成一个紧凑的引用图,所有数据都通过 offset 寻址。

### 3.2 string_ids:字符串池

```c
struct DexFile::StringId {
    uint32_t string_data_off;  // 指向 string_data 的偏移
};
```

**string_data 格式**(变长):

```
1 字节:UTF-8 字符串长度(N)
N 字节:UTF-8 modified 数据(MUTF-8)
1 字节:终止符(0)
```

**MUTF-8 与 UTF-8 的区别**:
- MUTF-8 用 1 字节表示"空字符"(修改 UTF-8)
- MUTF-8 用 2-3 字节表示 code point(标准 UTF-8 用 1-4)
- MUTF-8 适合 JVM 内部存储

**真实案例**:

```bash
# 用 dexdump 看字符串
$ dexdump -d app.apk | grep "string_ids_size" -A 5
# 12345 个字符串
# 平均长度 12 字节
# 总大小 ≈ 12345 × (1 + 12 + 1) ≈ 172KB
```

### 3.3 type_ids:类型池

```c
struct DexFile::TypeId {
    uint32_t descriptor_idx;  // 指向 string_ids 中的类型描述符
};
```

**类型描述符的格式**:
- `Lpackage/ClassName;` 表示引用类型
- `[I` 表示 int[]
- `[[Z` 表示 boolean[][]
- `V` 表示 void(只用于返回类型)
- `I` / `J` / `F` / `D` / `B` / `C` / `S` / `Z` 表示基本类型

**示例**:
- `Ljava/lang/String;` → string_ids 的索引 N
- `I` → string_ids 的索引 M
- `[[Landroid/view/View;` → string_ids 的索引 K

**架构师必记**:**type_ids 是"类描述符 → 类型"的映射**。**一个类对应一个 type_id**,但可以有多个 class_defs(内部类)。

### 3.4 proto_ids:方法原型池

```c
struct DexFile::ProtoId {
    uint32_t shorty_idx;        // 指向 string_ids 中的方法签名缩写
    uint32_t return_type_idx;   // 指向 type_ids 中的返回类型
    uint32_t parameters_off;    // 指向 type_list(参数列表)
};
```

**shorty_idx 格式**:方法的"短签名",如 `VI` 表示 `void(int)`,`IIJ` 表示 `long(int, int, long)`。

**type_list 格式**:

```c
struct DexFile::TypeList {
    uint32_t size;              // 参数个数
    TypeItem items[1];          // 实际是 size 个 TypeItem
};

struct DexFile::TypeItem {
    uint16_t type_idx;          // 指向 type_ids
};
```

**示例**:
- `void foo(int, String)` 的 proto:
  - shorty_idx = "VILjava/lang/String;" → "VI L..."(用 MUTF-8 编码的 "VI Ljava/lang/String;")
  - return_type_idx = V 的 type_id
  - parameters_off = type_list (size=2, [int, String])

**架构师必记**:**proto_ids 是"方法签名 → 类型"**。**它去重方法签名**——如果两个方法签名相同(同返回类型 + 同参数),它们共享一个 proto_id。

### 3.5 field_ids:字段池

```c
struct DexFile::FieldId {
    uint16_t class_idx;     // 字段所属类
    uint16_t type_idx;      // 字段类型
    uint32_t name_idx;      // 字段名
};
```

**示例**:`int MyClass.value`:
- class_idx = MyClass 的 type_id
- type_idx = I 的 type_id
- name_idx = "value" 的 string_id

**架构师必记**:**field_id 是"类 + 类型 + 名字"三件套**。**字段名去重**——如果两个类都有 `value` 字段,它们的 name_idx 相同。

### 3.6 method_ids:方法池

```c
struct DexFile::MethodId {
    uint16_t class_idx;     // 方法所属类
    uint16_t proto_idx;     // 方法签名
    uint32_t name_idx;      // 方法名
};
```

**示例**:`void MyClass.foo(int)`:
- class_idx = MyClass 的 type_id
- proto_idx = "VI" 的 proto_id
- name_idx = "foo" 的 string_id

**架构师必记**:**method_id 的命名空间 = class_idx**。同名方法在不同类里可以共享 name_idx,但 class_idx + name_idx 唯一标识一个方法。

### 3.7 5 大 id 表的"索引压缩"哲学

**DEX 用 4 字节和 2 字节混合存储**:
- string_id / proto_id / field_id / method_id 用 4 字节索引(全文件可达 4GB)
- type_id / class_idx / type_idx / name_idx 用 2 字节索引(最大 65535)

**为什么 type_idx 用 2 字节**:
- DEX 设计假设类型数不会超过 65535
- 大型 APK 可能接近上限——这会触发 multidex

**实际数据**(Android 14 的大型 App):
- Facebook: ~30MB DEX(20+ 个),200K+ 方法
- WeChat: ~50MB DEX(30+ 个),500K+ 方法
- 系统 framework.jar: ~50MB DEX,500K+ 方法

**架构师必记**:**id 表索引位数 = DEX 大小的隐藏上限**。如果 type_idx 溢出,ART 拒绝加载。

---

## 4. class_defs:类定义的"主入口"

### 4.1 class_def_item 结构

```c
struct DexFile::ClassDef {
    uint32_t class_idx;           // 类的 type_id
    uint32_t access_flags;        // 访问标志(public / final / abstract 等)
    uint32_t superclass_idx;      // 父类的 type_id
    uint32_t interfaces_off;      // interfaces 列表(0 表示无)
    uint32_t source_file_idx;     // 源文件名
    uint32_t annotations_off;     // 注解数据
    uint32_t class_data_off;      // 类的实际数据(字段、方法)
    uint32_t static_values_off;   // 静态字段值
};
```

**总大小**:32 字节/类。

### 4.2 访问标志详解

| access_flags | 值 | 含义 |
|---|---|---|
| ACC_PUBLIC | 0x1 | public |
| ACC_PRIVATE | 0x2 | private |
| ACC_PROTECTED | 0x4 | protected |
| ACC_STATIC | 0x8 | static |
| ACC_FINAL | 0x10 | final |
| ACC_SYNCHRONIZED | 0x20 | synchronized |
| ACC_VOLATILE | 0x40 | volatile(字段) |
| ACC_BRIDGE | 0x40 | bridge(方法) |
| ACC_TRANSIENT | 0x80 | transient |
| ACC_VARARGS | 0x80 | varargs |
| ACC_NATIVE | 0x100 | native |
| ACC_INTERFACE | 0x200 | interface |
| ACC_ABSTRACT | 0x400 | abstract |
| ACC_STRICT | 0x800 | strictfp |
| ACC_SYNTHETIC | 0x1000 | synthetic |
| ACC_ANNOTATION | 0x2000 | annotation |
| ACC_ENUM | 0x4000 | enum |
| ACC_MODULE | 0x8000 | module(Java 9+) |

**真实案例**:

```bash
$ dexdump -d app.apk | grep "Class descriptor" -A 2
# 输出:
# Class descriptor  : 'Lcom/example/MainActivity;'
#   access flags    : 0x0001 (PUBLIC)              ← 0x1
#   superclass      : 'Landroid/app/Activity;'     ← 0x10A(= 0x100 + 0x8 + 0x2 ?)
```

### 4.3 class_data:类的实际数据

**class_data_off 指向 class_data_item**:

```c
struct DexFile::ClassData {
    uint32_t static_fields_size;    // 静态字段数
    uint32_t instance_fields_size;  // 实例字段数
    uint32_t direct_methods_size;   // 直接方法数
    uint32_t virtual_methods_size;  // 虚方法数
    
    // 后面是 4 个变长数组(编码方式:uleb128)
    Field[static_fields_size];      // 静态字段
    Field[instance_fields_size];    // 实例字段
    Method[direct_methods_size];    // 直接方法
    Method[virtual_methods_size];   // 虚方法
};
```

**uleb128 编码**:每个字段/方法的"差分索引"用 uleb128 存储,而不是绝对索引。

**示例**(`MyClass` 的 class_data):
```
static_fields_size = 1
instance_fields_size = 2
direct_methods_size = 1
virtual_methods_size = 3

static_fields:[
  { field_idx_diff=0, access_flags=0x8 }   // 静态字段 #0
]
instance_fields:[
  { field_idx_diff=1, access_flags=0x0 },   // 实例字段 #1
  { field_idx_diff=2, access_flags=0x0 }    // 实例字段 #2
]
direct_methods:[
  { method_idx_diff=0, access_flags=0x10081, code_off=0x1a8 }  // <init> 构造函数
]
virtual_methods:[
  { method_idx_diff=1, access_flags=0x1, code_off=0x1b0 },
  { method_idx_diff=2, access_flags=0x1, code_off=0x1b8 },
  { method_idx_diff=3, access_flags=0x1, code_off=0x1c0 }
]
```

**架构师必记**:**class_data 用 uleb128 编码索引差**——这大幅节省空间(对比 4 字节绝对索引)。

### 4.4 uleb128 编码详解

**uleb128(Unsigned Little Endian Base 128)**:变长整数编码,1-5 字节,每个字节用 7 位存值,最高位为 1 表示还有后续字节。

**示例**:
- 0x00 → 0x00 (1 字节)
- 0x7F → 0x7F (1 字节)
- 0x80 → 0x80 0x01 (2 字节)
- 0x3FFF → 0xFF 0x7F (2 字节)
- 0x4000 → 0x80 0x80 0x01 (3 字节)

**架构师必记**:**DEX 中所有变长索引都使用 uleb128**——比固定 4 字节节省 50% 空间。

---

## 5. DEX 整文件 mmap 与 linear alloc

### 5.1 整文件 mmap 的实现

**ART ClassLoader 加载 DEX 的流程**:

```c
// art/runtime/dex_file.cc(简化)
std::unique_ptr<const DexFile> DexFile::Open(const std::string& filename, ...) {
    // 1. 打开文件
    File fd(filename, O_RDONLY);
    
    // 2. 读前 4 字节,确认 magic
    char magic[8];
    fd.Read(magic, 8);
    if (memcmp(magic, "dex\n", 4) != 0) {
        // 不是 DEX
        return nullptr;
    }
    
    // 3. 读头(前 0x70 字节)
    Header header;
    fd.Read(&header, sizeof(header));
    
    // 4. 校验 magic / checksum / signature
    if (!VerifyMagicAndChecksum(header, fd)) {
        return nullptr;
    }
    
    // 5. mmap 整个文件
    size_t length = header.file_size_;
    void* mem = mmap(nullptr, length, PROT_READ, MAP_PRIVATE, fd.GetFd(), 0);
    
    // 6. 构造 DexFile 对象
    return std::make_unique<DexFile>(mem, length, ...);
}
```

**关键事实**:
- **DEX 整文件 mmap** = 一次 I/O + 一次 mmap
- **内存权限 = PROT_READ**(只读)
- **共享 = MAP_PRIVATE**(私有,但通过 PageCache 与其他进程共享)

### 5.2 跨进程共享的物理页

**zygote fork 后的 DEX 共享**:

```
zygote 进程
  └─ mmap(framework.dex) → mmap_addr_z
       └─ 物理页:AABBCCDD... (被多进程共享)

App 进程 1 (fork 自 zygote)
  └─ 继承 mmap_addr_z
       └─ 物理页:仍是 AABBCCDD... (COW 未触发,只读)

App 进程 2 (fork 自 zygote)
  └─ 继承 mmap_addr_z
       └─ 物理页:仍是 AABBCCDD... (COW 未触发,只读)
```

**关键事实**:
- 100 个 App 进程共享 framework.dex 的物理页(只读)
- 写时复制(COW)只在某个进程要写时才触发
- **节省内存 = 99 × framework.dex_size**

**架构师视角**:**DEX 的整文件 mmap 是 Android 内存优化的关键**。**没有 mmap,zygote fork 模式无法成立**。

### 5.3 linear alloc:ART 堆外的"一次性分配"

**DEX 加载后,ART 还需要分配额外的数据结构**:
- ArtMethod 数组(每个方法一个 ArtMethod 对象)
- ArtField 数组(每个字段一个 ArtField 对象)
- Class 对象(每个类一个)
- 各种 vtable / iftable

**这些分配走 ART 的 linear alloc(线性分配器)**:

```c
// art/runtime/linear_alloc.h
class LinearAlloc {
public:
    void* Alloc(Thread* self, size_t size);
    void* AllocAlign16(Thread* self, size_t size);
    // ...
private:
    std::unique_ptr<MemMap> mem_map_;  // 用 MemMap 分配大块
    size_t total_size_;                 // 已分配总量
};
```

**linear alloc 的特点**:
- **快**:顺序分配,O(1)
- **不可回收**:直到 ClassLoader 卸载时整个释放
- **共享**:在 zygote 中分配的 linear alloc 内存被 fork 后的子进程继承

**关键事实**:**ART 的 linear alloc 是"冷启动期内存峰值"的主要来源**——一个 DEX 加载后,可能要分配 10-30MB 的 ArtMethod/Class 对象。

### 5.4 真实案例:DEX 加载的内存占用

**典型 App 启动后 DEX 相关的内存占用**:

| 数据结构 | 大小 | 说明 |
|---|---|---|
| DEX 文件本身 | 4-50MB | 整文件 mmap |
| ArtMethod 表 | 5-20MB | 每个方法 32 字节 |
| ArtField 表 | 1-3MB | 每个字段 16 字节 |
| Class 对象 | 1-3MB | 每个类 200-500 字节 |
| vtable / iftable | 1-5MB | 每个类 100-500 字节 |
| 字符串去重 | 2-10MB | interned strings |
| **总计** | **15-90MB** | **冷启动期峰值** |

**架构师必记**:**DEX 加载的内存占用 ≈ 5-10 倍 DEX 文件大小**。Multidex 会让这个数字翻倍。

---

## 6. ODEX / VDEX / CDEX:AOT 编译产物

### 6.1 为什么需要 AOT 编译

**DEX 是字节码,不是机器码**。ART 在执行时需要"翻译"字节码:

| 模式 | 翻译时机 | 速度 | 内存 |
|---|---|---|---|
| **Interpreted**(解释执行) | 每次执行都翻译 | 极慢 | 低 |
| **JIT**(Just-In-Time) | 运行时编译 | 中 | 中 |
| **AOT**(Ahead-Of-Time) | 安装时编译 | 快 | 高 |

**Android 7+ 的混合模式**:
- 启动期:Interpreted 或 quick(JIT 前的快速 verify)
- 热点代码:JIT 编译
- 后台:dex2oat 异步 AOT 编译

**AOT 的产物** = ODEX / VDEX。

### 6.2 ODEX (Optimized DEX)

**ODEX 是 ART 优化后的 DEX**(可能包含机器码):

```
ODEX 文件:
  [DEX 部分(原始字节码)]
  [OAT 部分(AOT 编译的机器码)]
  [metadata 部分(类/方法的偏移、vtable 等)]
```

**ODEX 加载流程**:
1. mmap ODEX 文件
2. 读 DEX 部分 → 解析字节码
3. 读 OAT 部分 → 获取机器码
4. 首次调用方法时,直接执行机器码

**架构师视角**:**ODEX 是"DEX + AOT 机器码"的组合**。加载 ODEX 比加载 DEX 快(跳过解释)。

### 6.3 VDEX (Validated DEX)

**VDEX 是"已验证的 DEX"**(不含机器码):

```
VDEX 文件:
  [DEX 部分(原始字节码)]
  [verify 数据(快速 verify 的状态)]
```

**VDEX 的作用**:
- 跳过 verify 阶段(已 verify 过)
- 启动时 ArtMethod 创建快
- 文件通常比 DEX 大 10-20%

**VDEX 加载流程**:
1. mmap VDEX 文件
2. 读 DEX 部分
3. 读 verify 数据 → 快速 verify(quicken 状态)
4. 直接创建 ArtMethod(不需运行时 verify)

**架构师必记**:**VDEX 是"DEX + 验证结果"**。**它解决"启动期 verify 太慢"的问题**。

### 6.4 CDEX (Compact DEX)

**CDEX 是 dex2oat 的"压缩 DEX"格式**:

```
CDEX 文件:
  [CDEX 头(替代 DEX 头)]
  [压缩的 string pool]
  [压缩的 type pool]
  [压缩的 field/method pools]
  [DEX 部分(原样保留)]
```

**CDEX 的优势**:
- 头部信息压缩(节省 30-50% 空间)
- 加载时不需解压(直接 mmap)
- 适合 system 分区空间紧张的设备

**CDEX 头**:

```
magic: "cdex\0...\0"
CDEX 001 版本:Android 10+
CDEX 002 版本:Android 14+(增强压缩)
```

**架构师必记**:**CDEX 看着像"压缩格式",但实际是"重新编码的 DEX"**。**它能节省 space,但加载时间和 DEX 一样**。

### 6.5 3 种格式对比

| 格式 | 内容 | 加载速度 | 文件大小 | 何时用 |
|---|---|---|---|---|
| **DEX** | 原始字节码 | 慢(需 verify + interpret) | 中 | 编译产物 |
| **ODEX** | DEX + 机器码 | 快(直接执行) | 大(2-5x DEX) | 旧版 ART |
| **VDEX** | DEX + verify 结果 | 中(快速 verify) | 略大(1.1-1.2x DEX) | Android 8+ 默认 |
| **CDEX** | 重新编码的 DEX | 中 | 小(0.7-0.8x DEX) | space 紧张设备 |

**架构师必记**:**现代 Android(8+)默认用 VDEX,OAT 单独存**。**ODEX 在 Android 7- 上使用,Android 8+ 已被 OAT + VDEX 替代**。

### 6.6 真实案例:一个 App 的 4 种文件

```
$ ls /data/app/~~xyz/oat/arm64/
base.odex    # OAT 编译产物
base.vdex    # 验证过的 DEX
```

**含义**:
- Android 14 上,App 安装时会运行 dex2oat
- dex2oat 输出两个文件:OAT(机器码)+ VDEX(验证过的 DEX)
- App 启动时,加载 VDEX(快速 verify)+ OAT(机器码)

**架构师必记**:**ODEX + VDEX 是 Android 8+ 的标准产物**。**单独 OAT 文件是机器码,VDEX 是字节码 + verify 数据**。

---

## 7. 真实案例:用 dexdump 拆解一个 APK

### 7.1 5 个最常用的 dexdump 命令

**命令 1:看头**

```bash
$ dexdump -h app.apk
```

输出 DEX 头 112 字节的解析(magic、checksum、各 id 表大小等)。

**命令 2:看 5 大 id 表**

```bash
$ dexdump -i app.apk
# 输出:string_ids / type_ids / proto_ids / field_ids / method_ids
```

**命令 3:看类定义**

```bash
$ dexdump -d app.apk | head -100
# 输出:每个类的 access_flags / superclass / interfaces / 字段 / 方法
```

**命令 4:看反汇编的字节码**

```bash
$ dexdump -d app.apk | grep -A 50 "Class descriptor.*MainActivity"
# 输出:MainActivity 类的字节码反汇编
```

**命令 5:看统计信息**

```bash
$ dexdump -h app.apk | grep -E "size"
# 输出:5 大 id 表的大小汇总
```

### 7.2 真实案例:用 baksmali 看 smali 代码

**baksmali** 是 dex 反汇编工具(比 dexdump 更可读):

```bash
$ baksmali disassemble app.apk -o smali_output/
# 输出:每个类对应一个 .smali 文件
```

**smali 文件示例**(`MainActivity.smali`):

```smali
.class public Lcom/example/MainActivity;
.super Landroidx/appcompat/app/AppCompatActivity;
.source "MainActivity.java"


# instance fields
.field private mTextView:Landroid/widget/TextView;


# direct methods
.method public constructor <init>()V
    .registers 2
    invoke-direct {p0}, Landroidx/appcompat/app/AppCompatActivity;-><init>()V
    return-void
.end method

# virtual methods
.method protected onCreate(Landroid/os/Bundle;)V
    .registers 4
    invoke-super {p0, p1}, Landroidx/appcompat/app/AppCompatActivity;->onCreate(Landroid/os/Bundle;)V
    const v0, 0x7f0c001c
    invoke-virtual {p0, v0}, Lcom/example/MainActivity;->setContentView(I)V
    return-void
.end method
```

**架构师必记**:**smali 是 DEX 的"汇编语言"**。**任何 Java 工程师都应该会读 smali**——它能告诉你 DEX 里的实际逻辑。

### 7.3 真实案例:DEX 大小优化

**优化前**(某 App 的 DEX 太大):
```
string_ids_size: 85000
type_ids_size: 12000
proto_ids_size: 18000
field_ids_size: 45000
method_ids_size: 60000
class_defs_size: 3500
file_size: 12MB
```

**优化手段**:

| 优化 | 节省 | 难度 |
|---|---|---|
| **R8/ProGuard** | 30-50% | 低 |
| **去除无用类** | 10-30% | 中 |
| **拆分 multidex** | 不减少,但加载快 | 低 |
| **资源压缩** | 5-10% | 中 |

**架构师必记**:**DEX 太大 = 冷启动期 ART 加载慢**。**R8 是必用的**。

---

## 8. DEX 加载的性能与稳定性影响

### 8.1 性能影响

**冷启动 1.5s 中,DEX 加载贡献多少**:

| 阶段 | 耗时 | 占比 |
|---|---|---|
| linker64 启动 | 50-150ms | 3-10% |
| ART 启动(JNI_OnLoad) | 80-150ms | 5-10% |
| **DEX 加载**(本篇) | **50-200ms** | **3-13%** |
| └─ mmap DEX | 10-50ms | 1-3% |
| └─ 解析 5 大 id 表 | 10-30ms | 1-2% |
| └─ 验证 + 创建 ArtMethod | 30-100ms | 2-7% |
| Resources 加载 | 100-200ms | 7-13% |
| Application onCreate | 300-500ms | 20-33% |
| 第一帧渲染 | 200-400ms | 13-27% |

**DEX 加载占 3-13%**——是冷启动的中等瓶颈。

### 8.2 4 个优化技巧

| 技巧 | 节省时间 | 难度 |
|---|---|---|
| **R8 优化** | 20-50% DEX 大小 | 低 |
| **VDEX/AOT 预编译** | 跳过 verify 30-100ms | 中 |
| **拆分 multidex** | 减少单次 mmap 大小 | 中 |
| **懒加载类** | 启动期不加载非关键类 | 中 |

### 8.3 稳定性影响

**5 大稳定性陷阱**:

| 陷阱 | 触发条件 | 后果 |
|---|---|---|
| **DEX 文件损坏** | 校验和错误、签名错误 | 启动崩溃 |
| **Multidex 顺序错** | main.dex 不是主类 | ClassNotFoundException |
| **DEX 版本不兼容** | 新版 DEX 在旧 ART | VerifyError |
| **id 索引溢出** | type_idx > 65535 | 编译失败 |
| **linear alloc 失败** | 内存碎片 | OutOfMemoryError |

### 8.4 真实案例:DEX 校验失败

**症状**:
```
E art   : Failed to verify dex file '/data/app/~~xyz/base.apk': bad checksum
E AndroidRuntime: FATAL EXCEPTION: main
E AndroidRuntime: java.lang.VerifyError
```

**诊断**:
```bash
# 看 checksum
$ adb shell sha1sum /data/app/~~xyz/base.apk
# 对比 APK 原始 sha1
```

**修复**:
- 重新安装 APK
- 检查签名流程

---

## 9. 架构师视角:DEX 视角的 5 个核心洞察

### 9.1 洞察 1:DEX 是为 mmap 而生的字节码

**DEX 的所有设计都指向"整文件 mmap"**:
- 头固定 0x70 字节
- 5 大 id 表用 offset 寻址
- string/type/method 跨类共享
- uleb128 压缩索引

**架构师必记**:**DEX 不是 Java class 的"打包版"**——它是为 Android 启动场景定制的全新格式。

### 9.2 洞察 2:DEX 是 zygote fork 模式的基础

**没有 DEX 的整文件 mmap,zygote fork 模式无法成立**:
- 100 个 App 进程共享 framework.dex 的物理页
- 节省内存 = 99 × framework.dex_size
- **这是 Android 内存优化的关键**

### 9.3 洞察 3:DEX / ODEX / VDEX / CDEX 是同一个东西的 4 个版本

| 格式 | 主要区别 | 加载速度 |
|---|---|---|
| DEX | 原始字节码 | 慢 |
| ODEX | DEX + 机器码 | 快(旧版) |
| VDEX | DEX + verify 结果 | 中(新版) |
| CDEX | 重新编码的 DEX | 中 |

**架构师必记**:**现代 Android(8+)用 VDEX + OAT(单独文件),不再用 ODEX**。

### 9.4 洞察 4:DEX 加载的内存占用 = 5-10 倍 DEX 大小

**DEX 文件 mmap + ArtMethod + ArtField + Class 对象 + vtable** = 5-10 倍 DEX 大小。

**架构师必记**:**4MB DEX 加载后占 20-40MB 内存**。**Multidex 时这个数字翻倍**。

### 9.5 洞察 5:从 DEX 失败直接映射到故障现象

| 故障现象 | DEX 根因 |
|---|---|
| `VerifyError` | DEX 损坏 / VDEX 与 OAT 不一致 |
| `ClassNotFoundException` | Multidex 顺序错 |
| `OutOfMemoryError` linear alloc | DEX 太大 / 内存碎片 |
| `bad checksum` | DEX 损坏(下载/签名问题) |
| 启动慢 200ms+ | DEX 太大 / VDEX 缺失 / verify 失败 |

---

## 10. DEX 工具链速查

### 10.1 必装工具

| 工具 | 用途 | 关键命令 |
|---|---|---|
| **dexdump** | DEX 信息查看 | `-h` 头 / `-d` 反汇编 / `-i` id 表 |
| **baksmali** | DEX 反汇编为 smali | `disassemble app.apk -o smali/` |
| **smali** | smali 汇编为 DEX | `assemble smali/ -o new.dex` |
| **apkanalyzer** | APK 整体分析 | `dex packages app.apk` |
| **aapt2** | APK 资源 + DEX | `dump xmltree app.apk` |
| **R8** | DEX 优化 | `java -jar r8.jar --release app.apk` |
| **dex2oat** | DEX → ODEX/VDEX/CDEX | `dex2oat --dex-input=app.dex --oat-file=app.oat` |

### 10.2 5 个常用诊断组合

**组合 1:DEX 头快速看**

```bash
$ dexdump -h app.apk | head -30
```

**组合 2:DEX 统计**

```bash
$ dexdump -h app.apk | grep -E "size" | sort
```

**组合 3:看某个类**

```bash
$ baksmali disassemble app.apk -o smali/
$ cat smali/com/example/MainActivity.smali
```

**组合 4:DEX 验证**

```bash
$ aapt2 dump xmltree app.apk --file AndroidManifest.xml
# 同时验证 APK 结构
```

**组合 5:DEX 转 ODEX**

```bash
$ dex2oat --dex-input=app.dex --oat-file=app.oat --instruction-set=arm64
```

---

## 11. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **DEX 是为 mmap 而生的字节码** | 头固定 0x70 字节 + 5 大 id 表 + 整文件 mmap |
| 2 | **3 个 Android 特定问题** | 存储空间 / mmap 友好 / 运行时编译 |
| 3 | **5 大 id 表 = 全局索引池** | string → type → proto → field/method → class_defs |
| 4 | **4 个格式 = 同一事物的不同版本** | DEX / ODEX / VDEX / CDEX |
| 5 | **DEX 加载占 5-10 倍 DEX 大小内存** | mmap + ArtMethod + ArtField + Class + vtable |

---

## 12. 下一篇预告

07 篇《ART ClassLoader 体系:从 BootClassLoader 到 PathClassLoader》会沿着本篇埋下的线索,深入讲:

- Java ClassLoader 模型:parent delegation
- Android 的 ClassLoader 树:
  - BootClassLoader(framework 核心类)
  - PathClassLoader(/system/app/ 和 /data/app/ 的 APK)
  - InMemoryDexClassLoader(动态加载 DEX)
- PathClassLoader 构造流程:loadDex → DexPathList → Element
- 隔离机制:每个应用独立的 ClassLoader 实例
- Class 加载的"位置"决定可见性
- 热修复/插件化:动态替换 ClassLoader 的边界

**07 篇预计 3 天后产出**,届时一起发你看。

---

## 附录 A:DEX 头 112 字节字段速查

| 偏移 | 大小 | 字段 | 含义 |
|---|---|---|---|
| 0x00 | 8 | magic_ | "dex\n039\0" 等 |
| 0x08 | 4 | checksum_ | adler32 |
| 0x0C | 20 | signature_ | SHA-1 |
| 0x20 | 4 | file_size_ | 文件大小 |
| 0x24 | 4 | header_size_ | 必须 0x70 |
| 0x28 | 4 | endian_tag_ | 0x12345678 |
| 0x2C | 4 | link_size_ | 链接段大小 |
| 0x30 | 4 | link_off_ | 链接段偏移 |
| 0x34 | 4 | map_off_ | map_list 偏移 |
| 0x38 | 4 | string_ids_size_ | 字符串数 |
| 0x3C | 4 | string_ids_off_ | 字符串索引偏移 |
| 0x40 | 4 | type_ids_size_ | 类型数 |
| 0x44 | 4 | type_ids_off_ | 类型索引偏移 |
| 0x48 | 4 | proto_ids_size_ | 方法原型数 |
| 0x4C | 4 | proto_ids_off_ | 方法原型索引偏移 |
| 0x50 | 4 | field_ids_size_ | 字段数 |
| 0x54 | 4 | field_ids_off_ | 字段索引偏移 |
| 0x58 | 4 | method_ids_size_ | 方法数 |
| 0x5C | 4 | method_ids_off_ | 方法索引偏移 |
| 0x60 | 4 | class_defs_size_ | 类数 |
| 0x64 | 4 | class_defs_off_ | 类定义偏移 |
| 0x68 | 4 | data_size_ | data 区大小 |
| 0x6C | 4 | data_off_ | data 区偏移 |

## 附录 B:5 大 id 表对比

| 表 | 元素大小 | 索引空间 | 数量级 | 优化手段 |
|---|---|---|---|---|
| string_ids | 4B(string_data_off) | 全文件 4GB | 1K-50K | 字符串去重 |
| type_ids | 4B(descriptor_idx) | 全文件 4GB | 1K-10K | 类型共享 |
| proto_ids | 12B | 全文件 4GB | 1K-20K | proto 去重 |
| field_ids | 8B | 全文件 4GB | 5K-50K | 字段共享 |
| method_ids | 8B | 全文件 4GB | 5K-50K | 方法共享 |

## 附录 C:DEX / ODEX / VDEX / CDEX 对比

| 格式 | magic | 内容 | 加载时间 | 文件大小 |
|---|---|---|---|---|
| DEX | `dex\n035\0` 等 | 原始字节码 | 慢 | 中 |
| ODEX | (Android 7-) | DEX + 机器码 | 快 | 大(2-5x) |
| VDEX | (Android 8+) | DEX + verify 结果 | 中(快速 verify) | 略大(1.1-1.2x) |
| CDEX | `cdex\0` | 重新编码 DEX | 中 | 小(0.7-0.8x) |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 07 ClassLoader | 加载 DEX 的 ClassLoader 树 |
| 08 类生命周期 | DEX 加载后的 7 个阶段 |
| 09 AOT/JIT | DEX → VDEX/ODEX 的 AOT 流水线 |
| 12 进程启动 | Zygote fork 后,子进程的 DEX 加载 |

---

> **本篇把 DEX 拆解到"格式 + 5 大 id 表 + 4 种产物 + 工具链"5 个维度。**
> **07 篇会在这个基础上,讲 ClassLoader 体系——DEX 怎么被加载、Class 怎么被解析、可见性怎么隔离。**
> **记住 3 个问题、5 大 id 表、4 种产物,你的 DEX 视角就立住了。**
