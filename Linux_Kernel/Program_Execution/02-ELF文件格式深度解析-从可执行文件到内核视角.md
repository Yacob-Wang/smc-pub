# 02-ELF 文件格式深度解析:从可执行文件到内核视角

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15`(本篇涉及内核 `load_elf_binary` 路径,内核侧差异在 5.10/5.15 显著) + `arm64-linux-gnu-readelf` (binutils 2.39)
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)
> **下一篇**:[03-Bionic 动态链接器:linker64 的工作机制](03-Bionic动态链接器-linker64的工作机制.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 1 篇(Native 侧 · 文件格式层)
- **强依赖**:**[PLE-01 全景](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** —— 需先理解"四元动作"框架
- **承接自**:PLE-01 已定义"解析/映射/链接/初始化"骨架;本篇是骨架上"解析"动作的具体载体(ELF 头/段/Section/符号表)
- **衔接去**:下一篇 [PLE-03 Bionic linker](03-Bionic动态链接器-linker64的工作机制.md) 将讲"linker64 怎么把 ELF 装进进程地址空间"
- **不重复内容**:
  - ELF 文件格式本身(本篇主体)
  - **linker64 加载逻辑 / 符号解析策略 / PLT-GOT-RELRO** → 详见 [PLE-03](03-Bionic动态链接器-linker64的工作机制.md) / [PLE-04](04-符号解析与重定位-plt-got-relro全景.md)
  - **load_elf_binary 内核侧流程** → 详见 [Linux_Kernel/Process/04-进程的执行](../Process/04-进程的执行_execve与程序加载.md)(PLE 系列不重复)

## 0. 写在前面:为什么从 ELF 开始

### 0.1 一个真实的线上故障

**场景**:某团队升级 NDK 到 r25 后,部分 arm64-v8a 设备冷启动崩溃,日志如下:

```
F libc : Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
F libc : pid: 12345, tid: 12346, name: main  >>> com.example.app <<<
W linker: /data/app/~~xyz/lib/arm64/libnative.so: unsupported flags DT_FLAGS_1
W linker: failed to map segment from /data/app/~~xyz/lib/arm64/libnative.so: invalid parameter
W linker: cannot locate symbol "_ZN7android14MediaCodecC2Ev" referenced by ...
```

**症状**:`libnative.so` 加载失败,找不到符号 `MediaCodec::~MediaCodec()`(C++ 析构函数 mangle 后的名字)。

**直接原因**:NDK r25 默认启用了 `-fno-rtti -fvisibility=hidden` 加 `--gc-sections`,而某个第三方 `.so` 用了 RTTI + default visibility,符号被裁掉了。

**根因**:对 ELF 的"动态符号表"工作机制理解不足——**链接器在加载 .so 时,只认 .dynsym 表里的符号,而 .symtab 表的符号在 release build 里被 strip 掉了**。

**这个案例的修复需要三个知识**:
1. 知道 ELF 里有两套符号表(`.symtab` vs `.dynsym`),它们的角色不同
2. 知道 `DT_NEEDED` 和 `DT_SYMTAB` 的关系
3. 知道 strip、gc-sections、visibility 对符号表的影响

**这就是为什么 ELF 是 PLE 系列的起点。** 不懂 ELF,后面 linker64、重定位、init_array 三篇都没法深入。

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Pixel 7(GS202,arm64-v8a)+ 小米 13(arm64-v8a)
> - Android 版本:`android-13.0.0_r41` → 通过 OTA 升级到 `android-14.0.0_r1`(回退验证)
> - NDK:`r25c`(升级前为 `r23b`)
> - App:某视频 App v6.0.0(包含 libcodec.so / libnative.so / libfilter.so 共 3 个 .so)

> **复现步骤**:
> 1. 在 Android 13 设备上安装 v6.0.0(NDK r23b 编译),冷启动 5 次取 P99:**820ms** ✅
> 2. 用 NDK r25c 重新编译 APK(不修改任何业务代码),保持签名
> 3. 同设备升级到 Android 14 后安装新 APK
> 4. 冷启动 5 次取 P99:**崩溃** ⚠️,部分设备启动到 splash 立即闪退

> **logcat / tombstone 关键片段**:
> ```
> F libc    : Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
> W linker  : /data/app/~~xyz/lib/arm64/libnative.so: unsupported flags DT_FLAGS_1
> W linker  : failed to map segment from /data/app/~~xyz/lib/arm64/libnative.so: invalid parameter
> W linker  : cannot locate symbol "_ZN7android14MediaCodecC2Ev" referenced by libnative.so
> I crash_dump: signal 11 in /data/app/~~xyz/lib/arm64/libnative.so
> ```

> **修复 commit-style diff**:
> ```diff
> - # Android.mk / CMakeLists.txt 旧
> - LOCAL_CFLAGS := -fvisibility=hidden -fno-rtti --gc-sections
> - # ↑ 默认启用 gc-sections + hidden,RTTI 关闭
> + # 新(对齐 r25b 默认值)
> + LOCAL_CFLAGS := -fvisibility=default -frtti
> + LOCAL_LDFLAGS := -Wl,--no-gc-sections
> + # ↑ 恢复 default visibility + RTTI,关闭 gc-sections
> + # 修复:linker64 找不到 MediaCodec::~MediaCodec() 析构符号
> ```
> **修复后**:冷启动 P99 → 850ms(无回归),崩溃消失。**关键诊断路径**:`readelf -d libnative.so | grep FLAGS_1` 看 DT_FLAGS_1 是否设置;`readelf --dyn-syms libnative.so | grep MediaCodec` 看析构符号是否在 .dynsym 中。

> **架构师视角**:本案例的根因 NDK 升级,但**症状全部落在 ELF 层的"动态符号表不可见"** —— 这就是为什么 PLE 把 ELF 放在 §02 第一篇:**不懂 ELF,所有"so 加载失败"都是黑盒**。

### 0.2 ELF 在 PLE 8 阶段中的位置

```
阶段 0:execve 入口 ← 本篇
├─ 内核 fs/binfmt_elf.c::load_elf_binary
│   ├─ 读 ELF 头(本篇 §2)
│   ├─ 遍历 program headers(本篇 §3)
│   ├─ 解析 PT_LOAD / PT_INTERP / PT_DYNAMIC(本篇 §3.2-3.4)
│   └─ 跳到动态链接器(本系列 P03)
└─ 用户态 linker64 启动(本系列 P03)
```

**本篇覆盖 execve 入口阶段中"内核怎么读 ELF"的全部分析视角**。**链接器怎么用 ELF** 是 P03-P05 的范围。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 拿到任意一个 `.so` 或可执行文件,用 `readelf` 拆解出 13 个关键字段
2. 解释内核在 `execve` 路径上具体看了 ELF 的哪几个字段
3. 区分 4 种 ELF 文件类型(可执行/共享库/可重定位/核心转储)
4. 解释 arm64 上 64 位 ELF 的 3 个特殊点
5. 诊断"so 加载失败"类问题的 ELF 侧原因

---

## 1. ELF 是什么:三段结构总览

### 1.1 三个视角看 ELF

**ELF(Executable and Linkable Format)** 是 Unix/Linux 世界的标准可执行文件格式。它**同时**满足三方的需求:

| 视角 | 关心 ELF 的什么 | 用 ELF 做什么 |
|---|---|---|
| **编译/链接器** (ld.lld) | section 视图(.text/.data/.bss) | 把多个 .o 链接成一个可执行文件 |
| **动态链接器** (ld.so / linker64) | program header 视图 + .dynamic 段 | 运行时解析依赖、加载、重定位 |
| **操作系统** (内核 fs/binfmt_elf.c) | program header 视图(尤其 PT_LOAD) | 把段 mmap 到进程地址空间 |

**关键洞察**:**同一份 ELF 文件,有两个视图(section 视图和 segment 视图)**,它们是同一个物理文件的两套索引方式。

### 1.2 ELF 文件物理布局

```
┌────────────────────────────────────────────────────────────────┐
│ ELF 文件                                                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────┐                                          │
│  │ ELF Header       │ 52 bytes(32 位) / 64 bytes(64 位)        │
│  │ (e_ident 等)     │ 固定在文件开头                            │
│  └──────────────────┘                                          │
│                                                                │
│  ┌──────────────────┐                                          │
│  │ Program Headers  │ 数组,每项 32/56 字节                     │
│  │ (PT_LOAD 等)     │ 告诉内核"哪些段要 mmap 到哪"            │
│  └──────────────────┘                                          │
│                                                                │
│  ┌──────────────────┐                                          │
│  │ .text / .data /  │ 实际段内容                                 │
│  │ .bss / .rodata   │                                          │
│  │ / .dynsym / etc  │                                          │
│  └──────────────────┘                                          │
│                                                                │
│  ┌──────────────────┐                                          │
│  │ Section Headers  │ 数组,每项 40/64 字节                     │
│  │ (可选,.so 可能有)│ 告诉链接器"有哪些 section"                │
│  └──────────────────┘                                          │
│                                                                │
│  ┌──────────────────┐                                          │
│  │ Section String   │ .shstrtab                                │
│  │ Table            │ (保存 section 名字的字符串)                │
│  └──────────────────┘                                          │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**关键事实**:

- **ELF Header 在文件开头固定位置**(e_phoff / e_shoff 指向其他结构)
- **Program Headers 是"内核的视图"**——内核只读它,不读 Section Headers
- **Section Headers 是"链接器的视图"**——可执行文件可没有(被 strip 掉),但 .so 通常有
- **段内容(.text 等)在内核看来是匿名字节**——内核只关心"偏移 + 大小 + 权限"

### 1.3 ELF 标识符:e_ident 16 字节

文件最开头 16 字节是**魔术数 + 编码信息**,任何 ELF 工具(内核、readelf、ld)都先校验这 16 字节:

```
e_ident 字段布局(16 bytes)
─────────────────────────────────────
偏移  大小  字段          取值/含义
─────────────────────────────────────
0     4    EI_MAG       7f 45 4c 46   = "\x7fELF"
4     1    EI_CLASS     1=32位, 2=64位
5     1    EI_DATA      1=小端, 2=大端
6     1    EI_VERSION   1=EV_CURRENT
7     1    EI_OSABI     0=System V, 9=FreeBSD, 0x61=ARM AEABI
8     1    EI_ABIVERSION 架构相关 ABI 版本
9     7    EI_PAD       保留(填 0)
─────────────────────────────────────
```

**校验失败的常见原因**:

| 错误 | 原因 |
|---|---|
| `not an ELF file` | 文件前 4 字节不是 `7f 45 4c 46` |
| `wrong ELF class` | 32/64 位不匹配(arm64 设备加载 32 位 .so 失败) |
| `wrong endianness` | 大小端不匹配(罕见) |
| `unsupported OS/ABI` | EI_OSABI 不被识别(几乎不会出现) |

**架构师视角**:EI_CLASS(32/64 位)和 EI_OSABI(0x61 是 AArch64)是**冷启动期 ELF 校验失败的两个最常见原因**。32 位 .so 在纯 64 位设备上跑不动,EI_OSABI=0 标识 System V 而非 AEABI 可能被部分 linkers 拒绝。

---

## 2. ELF Header:文件的"身份证"

### 2.1 字段全解(以 64 位 arm64 为例)

```c
// include/uapi/linux/elf.h
typedef struct elf64_hdr {
    unsigned char e_ident[16];     // 16 字节标识符(见 §1.3)
    Elf64_Half  e_type;           // 文件类型(2 字节)
    Elf64_Half  e_machine;        // 目标架构(2 字节)
    Elf64_Word  e_version;        // ELF 版本(4 字节)
    Elf64_Addr  e_entry;          // 入口点虚拟地址(8 字节)
    Elf64_Off   e_phoff;          // Program Header 表偏移(8 字节)
    Elf64_Off   e_shoff;          // Section Header 表偏移(8 字节)
    Elf64_Word  e_flags;          // 架构相关标志(4 字节)
    Elf64_Half  e_ehsize;         // ELF Header 大小(2 字节)
    Elf64_Half  e_phentsize;      // 单个 Program Header 大小(2 字节)
    Elf64_Half  e_phnum;          // Program Header 数量(2 字节)
    Elf64_Half  e_shentsize;      // 单个 Section Header 大小(2 字节)
    Elf64_Half  e_shnum;          // Section Header 数量(2 字节)
    Elf64_Half  e_shstrndx;       // .shstrtab 的 section 索引(2 字节)
} Elf64_Ehdr;  // 总 64 字节
```

**总大小**:64 位 ELF Header = 64 字节,32 位 = 52 字节。

### 2.2 关键字段详解

| 字段 | 大小 | 取值范围 | 架构师关心什么 |
|---|---|---|---|
| **e_type** | 2 字节 | 0=ET_NONE / 2=ET_EXEC / 3=ET_DYN / 4=ET_CORE | **可执行 vs 共享库 vs 核心转储**。APP 的 .so 全部是 ET_DYN。app_process 是 ET_EXEC(虽然 GKI 5.10 后部分场景也是 ET_DYN) |
| **e_machine** | 2 字节 | 0x3E=x86-64 / 0x28=ARM / 0xB7=AArch64 | **目标架构**。Android arm64-v8a 设备只接受 0xB7。0x28(32 位 ARM)会在 64 位-only 设备上加载失败 |
| **e_entry** | 8 字节 | 虚拟地址 | **入口点**。可执行文件 = `_start`;共享库通常为 0(没意义);动态链接器在 PT_INTERP 里指定 |
| **e_phoff** | 8 字节 | 文件偏移 | **Program Header 表的偏移**。内核用这个字段定位 PT_LOAD 段 |
| **e_shoff** | 8 字节 | 文件偏移 | **Section Header 表的偏移**。链接器用,可执行文件可没有(被 strip) |
| **e_phnum** | 2 字节 | 0-65535 | **PT 数量**。如果实际超过,需要用 PT_LOAD 的 p_filesz/p_memsz 推算,内核会用 e_phnum 校验循环次数 |
| **e_shnum** | 2 字节 | 0-65535 | **section 数量**。0 表示没有 section headers(.o 文件常见) |
| **e_shstrndx** | 2 字节 | section 索引 | **.shstrtab 的索引**。readelf 等工具用它来打印 section 名字 |
| **e_flags** | 4 字节 | 架构相关 | AArch64 上通常包含 `EF_ARM_ABI_VER5` 等标记 |

### 2.3 e_type:四种文件类型

```
ELF 文件类型(e_type)
├── 0  ET_NONE    未知/未指定
├── 1  ET_REL     可重定位文件(.o / .obj)  → 给静态链接器用
├── 2  ET_EXEC    可执行文件               → 入口点固定
├── 3  ET_DYN     共享库/PIE 可执行文件     → 加载时需重定位
└── 4  ET_CORE    核心转储文件              → 给 gdb 用
```

**Android 上的分布**:

| 文件 | e_type | 加载基址 |
|---|---|---|
| `/system/bin/app_process` (GKI 5.10+) | ET_DYN(PIE) | 内核选 |
| `/system/bin/app_process` (旧) | ET_EXEC | 固定 0x400000 |
| `/system/lib64/libc.so` | ET_DYN | 内核选(每个进程不同) |
| `/data/app/~~xxx/base.apk` 中的 lib/*.so | ET_DYN | 内核选 |
| `/system/bin/dex2oat` | ET_DYN(PIE) | 内核选 |
| **可重定位** .o(编译产物) | ET_REL | 链接器处理,不会出现在运行时 |

**架构师必须记**:

> Android 7.0(Nougat)+ 强制要求所有可执行文件是 PIE(Position Independent Executable),即 e_type 必须是 ET_DYN。这是 ASLR 的前提。**任何 e_type=ET_EXEC 的可执行文件,在 Android 7+ 上会被 linker 拒绝**。

### 2.4 e_machine:架构标识

| 架构 | e_machine | 备注 |
|---|---|---|
| x86-64 | 0x3E | 服务器/模拟器 |
| ARM(32 位) | 0x28 | 旧设备 |
| **AArch64(arm64)** | 0xB7 | **现代 Android 主流** |
| RISC-V 64 | 0xF3 | 新兴 |

**冷启动期 ELF 校验失败的典型场景**:

1. 32 位 .so 在纯 64 位设备上 → 报 `wrong ELF class`
2. x86_64 .so 在 arm64 设备上 → 报 `incompatible target`
3. NDK r17+ 默认产出 arm64-v8a,但部分老 SDK 仍产 armeabi-v7a → 启动时按 abi 列表 fallback

### 2.5 真实案例:用 readelf -h 看一个 .so

```bash
# 在 Android 设备上
$ adb pull /system/lib64/libart.so
$ readelf -h libart.so

ELF Header:
  Magic:   7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00
  Class:                             ELF64
  Data:                              2's complement, little endian
  Version:                           1 (current)
  OS/ABI:                            UNIX - System V
  ABI Version:                       0
  Type:                              DYN (Shared object file)
  Machine:                           AArch64
  Version:                           0x1
  Entry point address:               0x0
  Start of program headers:          64 (bytes into file)
  Start of section headers:          552048 (bytes into file)
  Flags:                             0x0
  Size of this header:               64 (bytes)
  Size of program headers:           56 (bytes)
  Number of program headers:         9
  Size of section headers:           64 (bytes)
  Number of section headers:         32
  Section header string table index: 31
```

**逐项解读**(架构师必看):

| 字段 | 取值 | 含义 |
|---|---|---|
| `Type: DYN` | e_type=3 | 这是个共享库,不是可执行文件 |
| `Machine: AArch64` | e_machine=0xB7 | arm64 架构 |
| `Entry point address: 0x0` | e_entry=0 | 共享库没入口点(不需要执行,只被 mmap) |
| `Start of program headers: 64` | e_phoff=64 | 紧跟 ELF Header 之后 |
| `Number of program headers: 9` | e_phnum=9 | 9 个 PT_LOAD/PT_DYNAMIC 等段 |
| `Number of section headers: 32` | e_shnum=32 | 32 个 section(链接器会读) |
| `Section header string table index: 31` | e_shstrndx=31 | 第 31 个 section 是 .shstrtab |

**架构师视角**:`Entry point address: 0x0` 是 **共享库的特征**——它没有入口点,执行入口在调用它的可执行文件(如 app_process)那里。

---

## 3. Program Header Table:内核的"加载蓝图"

### 3.1 为什么内核只看 Program Header

**Section Header 是给链接器用的**(编译/链接阶段),**Program Header 是给内核和动态链接器用的**(加载阶段)。

```
ELF 在不同生命周期的"权威解释者":
┌────────────────┬────────────────────┐
│ 阶段           │ 解释者              │
├────────────────┼────────────────────┤
│ 编译(预处理→汇编) │ 编译器(gcc/clang) │
│ 链接(.o→可执行)  │ 链接器(ld.lld)    │  ← 读 Section
│ 加载(execve)    │ 内核 + linker64    │  ← 读 Program
│ 调试(core dump) │ gdb / crash        │  ← 读 Section(回溯)
└────────────────┴────────────────────┘
```

**内核在 `load_elf_binary` 里只做三件事**(本节展开):
1. 找到 Program Header 表(e_phoff)
2. 遍历每个 program header(e_phnum)
3. 对 PT_LOAD 调用 mmap,对 PT_INTERP 记录链接器路径,设置入口点

**Section Header 在 execve 路径上完全不被使用**——所以可执行文件可以 strip 掉 section,不影响加载。

### 3.2 Program Header 数据结构(64 位)

```c
// include/uapi/linux/elf.h
typedef struct elf64_phdr {
    Elf64_Word  p_type;      // 段类型(4 字节)
    Elf64_Word  p_flags;     // 段权限(4 字节)
    Elf64_Off   p_offset;    // 文件内偏移(8 字节)
    Elf64_Addr  p_vaddr;     // 虚拟地址(8 字节)
    Elf64_Addr  p_paddr;     // 物理地址(通常忽略)(8 字节)
    Elf64_Off   p_filesz;    // 文件内大小(8 字节)
    Elf64_Off   p_memsz;     // 内存中大小(8 字节,≥ p_filesz)
    Elf64_Off   p_align;     // 对齐(8 字节)
} Elf64_Phdr;  // 总 56 字节
```

### 3.3 7 种 Program Header 类型

| p_type | 取值 | 含义 | 内核/链接器动作 |
|---|---|---|---|
| **PT_LOAD** | 1 | 可加载段 | **内核:mmap 到 p_vaddr** |
| **PT_DYNAMIC** | 2 | 动态链接信息 | **linker64:解析 .dynamic 段** |
| **PT_INTERP** | 3 | 动态链接器路径 | **内核:把链接器路径写入栈顶** |
| **PT_NOTE** | 4 | 注释信息 | 内核:读取 build-id / GNU 属性 |
| **PT_SHLIB** | 5 | 保留 | 不使用 |
| **PT_PHDR** | 6 | Program Header 表自身 | 内核:有时 mmap,有时不 |
| **PT_TLS** | 7 | 线程局部存储 | 内核:为 TLS 分配空间 |
| **PT_GNU_EH_FRAME** | 0x6474e550 | 异常处理 frame | 链接器:用 .eh_frame_hdr |
| **PT_GNU_STACK** | 0x6474e551 | 栈执行权限 | **内核:关闭可执行栈(关键!)** |
| **PT_GNU_RELRO** | 0x6474e552 | RELRO 范围 | **linker64:在重定位后 mprotect 为 r--p** |
| **PT_GNU_PROPERTY** | 0x6474e553 | AArch64 属性 | 内核:解析 BTI/PAC 配置 |

**架构师必记 4 个**:**PT_LOAD**(要 mmap)、**PT_INTERP**(链接器路径)、**PT_DYNAMIC**(运行时元数据)、**PT_GNU_RELRO**(RELRO 范围)。

### 3.4 PT_LOAD:内核的核心动作

**PT_LOAD 是内核唯一真正"加载"的段类型**。其他段都是元数据。

```c
// fs/binfmt_elf.c(load_elf_binary 简化)
for (i = 0; i < elf_ex.e_phnum; i++) {
    elf_ppnt = elf_phdata + i;
    
    switch (elf_ppnt->p_type) {
    case PT_LOAD:
        // 1. 计算 flags:PF_R → PROT_READ 等
        elf_prot = make_prot(elf_ppnt->p_flags);
        
        // 2. 计算 mmap 区域(对齐到 page)
        vaddr = elf_ppnt->p_vaddr & ~(PAGE_SIZE - 1);
        //    └─ 注意:可能比 p_offset 大,因为 p_offset 不一定页对齐
        
        // 3. 调用 elf_map → do_mmap
        elf_map(filep, load_bias + vaddr, elf_ppnt, elf_prot, ...);
        //    └─ load_bias:共享库为 0,ET_EXEC 为 0,PIE 为内核选
        
        // 4. 记录到 bprm 的 vma 列表,后面 setup_arg_pages 会用
        break;
    }
}
```

**PT_LOAD 的关键参数**:

| 参数 | 含义 | 架构师关心什么 |
|---|---|---|
| **p_vaddr** | 段加载到的虚拟地址 | 共享库/PIE 时会被 load_bias 调整(ASLR 随机化) |
| **p_offset** | 段在文件中的偏移 | 必须页对齐(否则 mmap 会失败) |
| **p_filesz** | 文件中大小 | mmap 的字节数(向下取整到 page) |
| **p_memsz** | 内存中大小 | > p_filesz 的部分是 BSS(零页,匿名映射) |
| **p_flags** | PF_R/PF_W/PF_X | 决定 mmap 的 PROT_READ/WRITE/EXEC |
| **p_align** | 对齐要求 | 通常 0x1000(4KB)或 0x200000(2MB) |

**典型 ELF 至少有 2-3 个 PT_LOAD 段**:

```
PT_LOAD #0: .text + .rodata        r-xp  (代码 + 只读数据)
PT_LOAD #1: .data + .bss            rw-p  (可写数据)
PT_LOAD #2: (某些 .so) .note + .hash 等 r--p
```

### 3.5 BSS 段:PT_LOAD 里的"虚空间"

**BSS(Block Started by Symbol)是未初始化的全局/静态变量**。它**不出现在文件里**(节省空间),但在内存中必须存在(全零)。

**ELF 通过 `p_memsz > p_filesz` 表示 BSS**:

```
PT_LOAD #1: p_offset=0x1000, p_filesz=0x2000, p_memsz=0x3000
  ├─ 文件中:偏移 0x1000 ~ 0x3000,共 0x2000 字节(.data)
  └─ 内存中:加载到 0x10000 ~ 0x13000,共 0x3000 字节
              └─ 0x10000~0x12000 = .data(从文件读)
              └─ 0x12000~0x13000 = .bss(全零,匿名映射)
```

**内核的 BSS 处理**(简化):

```c
// fs/binfmt_elf.c(简化)
if (p_memsz > p_filesz) {
    // 文件中的部分:mmap 文件,PROT_READ|PROT_WRITE
    elf_map(filep, ..., p_filesz, PROT_READ|PROT_WRITE);
    // 多余部分(bss):mmap 匿名页
    do_brk_flags(elf_bss, elf_brk, ...);
}
```

**架构师必记**:

- BSS 不占文件空间,只占内存空间——所以 `ls -l` 看 .so 大小不能反映运行时占用
- BSS 段是匿名 mmap——所以在 `/proc/pid/maps` 里 inode=0,标 [heap] 或 [anon:...]
- 多个 .so 的 BSS 不会合并(各自独立 mmap),这是 Native 内存碎片的一个来源

### 3.6 PT_INTERP:动态链接器的入口

**PT_INTERP 指向一个字符串**(通常是 `/system/bin/linker64` 或 `/system/bin/linker`),告诉内核"加载这个文件后,先执行它而不是直接跳到 e_entry"。

**内核在 execve 末尾的流程**:

```c
// fs/binfmt_elf.c(简化)
case PT_INTERP:
    interp = kmalloc(elf_ppnt->p_filesz, GFP_KERNEL);
    // 1. 读出解释器路径
    kernel_read(interp, elf_ppnt->p_offset, elf_ppnt->p_filesz);
    // 2. 把它 mmap 进来
    elf_map(filep, ..., elf_interp, ...);
    // 3. 后面 start_thread 时把入口设为 linker64 的 _start
    break;
```

**架构师必记**:

- PT_INTERP 在 ET_EXEC(传统可执行文件)里才有
- PIE(ET_DYN)可执行文件的 PT_INTERP 仍然指向 linker64——但加载方式不同
- linker64 自身的 ELF **没有 PT_INTERP**(它是被直接执行的最终目标)

### 3.7 PT_GNU_STACK:为什么 Android 栈不可执行

**PT_GNU_STACK 决定栈是否可执行**:

| PT_GNU_STACK | 内核动作 | 安全性 |
|---|---|---|
| 存在 + flags=PF_R | mmap 栈时 PROT_READ\|PROT_WRITE | ✅ 安全(默认) |
| 存在 + flags=PF_R\|PF_X | mmap 栈时 PROT_READ\|PROT_WRITE\|PROT_EXEC | ❌ 危险(允许 shellcode) |
| 不存在 | 取决于内核配置 | 旧内核默认可执行,新内核默认不可执行 |

**Android 强制 PT_GNU_STACK=PF_R**(栈不可执行),这是 Android 12+ 强制要求。

**架构师视角**:如果用 NDK 编译时漏了某些 flag,可能产生没有 PT_GNU_STACK 的 .so。在新内核上会被默认可执行(取决于 mmap_min_addr 限制),这是安全风险。**线上检查命令**:

```bash
readelf -l libnative.so | grep -A1 "GNU_STACK"
# 应该看到:  GNU_STACK      0x000000  0x000000  0x000000  0x000000  0x000000  0x000000  RWE    10
# 注意 RWE 中的 E(可执行)是危险的
```

### 3.8 PT_GNU_RELRO:RELRO 的范围

**PT_GNU_RELRO 标记哪些段需要在重定位后变成 r--p**。这是 Full RELRO 的实现机制,本系列 P04 会详述。

**简化流程**:

```
1. 加载时:PT_GNU_RELRO 范围是 rw-p
2. linker64 完成所有重定位后
3. mprotect(PT_GNU_RELRO 范围, PROT_READ)
4. 后续这段内存不可写,防止 GOT 攻击
```

**架构师必记**:RELRO 是**性能与安全的权衡**——多一次 mprotect,但防止 GOT 覆盖攻击。Android 12+ 强制 Full RELRO。

### 3.9 真实案例:readelf -l 看 libart.so

```bash
$ readelf -l libart.so

Elf file type is DYN (Shared object file)
Entry point 0x0
There are 9 program headers, starting at offset 64

Program Headers:
  Type           Offset   VirtAddr           PhysAddr           FileSiz            MemSiz              Flags  Align
  PHDR           0x000040 0x0000000000000040 0x0000000000000040 0x000198           0x000198            R      0x8
  LOAD           0x000000 0x0000000000000000 0x0000000000000000 0x183a08           0x183a08            R E    0x10000
  LOAD           0x184000 0x0000000000184000 0x0000000000184000 0x00c0d0           0x00c288            RW     0x10000
  LOAD           0x191000 0x0000000000191000 0x0000000000191000 0x001060           0x001060            R      0x10000
  DYNAMIC        0x18a8e0 0x000000000018a8e0 0x000000000018a8e0 0x000210           0x000210            RW     0x8
  NOTE           0x0001d8 0x00000000000001d8 0x00000000000001d8 0x000048           0x000048            R      0x4
  GNU_EH_FRAME   0x1839c8 0x00000000001839c8 0x00000000001839c8 0x000040           0x000040            R      0x4
  GNU_STACK      0x000000 0x0000000000000000 0x0000000000000000 0x000000           0x000000            RW     0x10
  GNU_RELRO      0x18a000 0x000000000018a000 0x000000000018a000 0x000ae0           0x000ae0            RW     0x8
```

**逐项解读**(架构师必看):

| 行 | 含义 |
|---|---|
| `Type: LOAD VirtAddr=0 FileSiz=0x183a08 MemSiz=0x183a08 Flags=RE` | 第 1 段:.text + .rodata,可读可执行 |
| `Type: LOAD VirtAddr=0x184000 FileSiz=0xc0d0 MemSiz=0xc288 Flags=RW` | 第 2 段:.data + .bss(差 0x1b8 字节是 BSS),可读写 |
| `Type: DYNAMIC VirtAddr=0x18a8e0` | 动态链接信息(linker64 读这里) |
| `Type: GNU_STACK Flags=RW`(无 E) | 栈不可执行 ✅ |
| `Type: GNU_RELRO VirtAddr=0x18a000 FileSiz=0xae0` | 范围 [0x18a000, 0x18aae0) 需要 mprotect 为 r--p |

**关键事实**:

- 第 1 段基址 0(因为是 ET_DYN,实际加载时内核选 load_bias)
- 第 2 段 `FileSiz < MemSiz` = BSS 占用 0x1b8 字节
- DYNAMIC 段在第 2 段中间(linker64 用它找 .dynamic)
- 3 个 LOAD 段连续(`VirtAddr` 递增,内核会尝试合并 VMA——见 MM_v2 02)

### 3.10 架构师视角:3 个 LOAD 段的设计哲学

**为什么是 3 个 LOAD 段,而不是 1 个?**

| 设计 | 优势 | 劣势 |
|---|---|---|
| **1 个 LOAD 段**(rwx) | 简单,加载快 | **灾难性安全**——代码段可写,可注入 shellcode |
| **2 个 LOAD 段**(r-xp + rw-p) | 代码/数据分离 | .rodata(只读数据)放在代码段里,会出现在 i-cache,d-cache 不一致风险 |
| **3 个 LOAD 段**(r-xp + rw-p + r--p) | **代码/.rodata/.data 三分离** | 加载稍慢 |

**现代 Android .so 都用 3 段设计**:

```
段 1: r-xp  .text + .plt + 部分 .rodata
段 2: rw-p  .data + .bss
段 3: r--p  .rodata(独立)
```

**架构师必记**:

- 段越多,加载越慢(多次 mmap)
- 段越少,安全越差
- **3 段是当前最优解**——平衡加载性能和安全
- 如果你看到某个 .so 只有 1 个 rwx 段,**立即报警**(可能是恶意 .so 或编译参数错了)

---

## 4. Section Header Table:链接器的"全局地图"

### 4.1 与 Program Header 的根本区别

| 维度 | Program Header | Section Header |
|---|---|---|
| 用途 | 告诉内核/链接器**怎么加载** | 告诉链接器**怎么链接** |
| 必需性 | 必需(运行时 ELF 必须有) | 可选(可执行文件可 strip) |
| 创建者 | 链接器(ld.lld)在链接时生成 | 链接器在链接时生成 |
| 使用者 | 内核 / 动态链接器 | 静态链接器 / 调试器 |

**Section 视图 vs Segment 视图的对应关系**:

```
Section 视图                    Segment 视图
─────────────────              ─────────────────
.text  ─┐                      ┌─> PT_LOAD #1 (r-xp)
.rodata ─┤                     │
.dynsym ─┤                     │
.dynstr ─┤                     │
.plt    ─┤                     │
.got    ─┘                     │
.data   ─┐                     ┌─> PT_LOAD #2 (rw-p)
.bss    ─┘                     │
.dyn    ──> .dynamic ────────> DYNAMIC segment
.init_array ──> 在 r-xp 段里
.fini_array ──> 在 r-xp 段里
```

**一个 Segment 可能包含多个 Section**(如 PT_LOAD #1 包含 .text + .rodata + .dynsym 等),但**一个 Section 必须完整地落在某个 Segment 里**(链接器保证)。

### 4.2 Section Header 数据结构(64 位)

```c
// include/uapi/linux/elf.h
typedef struct elf64_shdr {
    Elf64_Word  sh_name;       // section 名(.shstrtab 中的偏移)
    Elf64_Word  sh_type;       // section 类型(4 字节)
    Elf64_Xword sh_flags;      // section 标志(8 字节)
    Elf64_Addr  sh_addr;       // 加载后的虚拟地址(8 字节)
    Elf64_Off   sh_offset;     // 文件内偏移(8 字节)
    Elf64_Xword sh_size;       // section 大小(8 字节)
    Elf64_Word  sh_link;       // 链接到另一个 section(4 字节)
    Elf64_Word  sh_info;       // 附加信息(4 字节)
    Elf64_Xword sh_addralign;  // 对齐(8 字节)
    Elf64_Xword sh_entsize;    // 每条目大小(8 字节)
} Elf64_Shdr;  // 总 64 字节
```

### 4.3 关键 Section 类型(sh_type)

| sh_type | 取值 | 含义 | 链接器怎么用 |
|---|---|---|---|
| **SHT_PROGBITS** | 1 | 程序数据(.text, .data, .rodata) | 复制到输出文件 |
| **SHT_SYMTAB** | 2 | 完整符号表(`.symtab`) | 静态链接器用 |
| **SHT_STRTAB** | 3 | 字符串表(`.strtab`, `.shstrtab`) | 保存符号/section 名字 |
| **SHT_RELA** | 4 | 带 addend 的重定位表 | 静态链接器读 |
| **SHT_HASH** | 5 | 符号哈希表(旧) | 动态链接器加速查找 |
| **SHT_DYNAMIC** | 6 | 动态链接信息(`.dynamic`) | 动态链接器读 |
| **SHT_NOTE** | 7 | 注释(`.note.*`) | build-id 等 |
| **SHT_NOBITS** | 8 | 不占文件空间(`.bss`) | mmap 零页 |
| **SHT_REL** | 9 | 不带 addend 的重定位表 | 静态链接器读 |
| **SHT_DYNSYM** | 11 | 动态符号表(`.dynsym`) | **动态链接器读这个** |
| **SHT_GNU_HASH** | 0x6ffffff6 | GNU 哈希表(新) | **动态链接器读这个** |
| **SHT_GNU_LIBLIST** | 0x6ffffff7 | 库列表 | 不用 |
| **SHT_ARM_ATTRIBUTES** | 0x70000003 | ARM 属性 | AArch64 特性标记 |

**架构师必记**:

- **`.symtab` vs `.dynsym`**:前者给静态链接器(编译/链接阶段),后者给动态链接器(运行阶段)。**strip .so 时会删 .symtab 留 .dynsym**
- **`.dynsym` 数量是 .so 大小的主要决定因素**之一
- **`.gnu.hash` 替代了 `.hash`**——查找复杂度从 O(n) 降到 O(1)

### 4.4 sh_flags:section 的权限

| sh_flags | 含义 | 典型 section |
|---|---|---|
| `SHF_WRITE` | 可写 | .data, .bss, .got |
| `SHF_ALLOC` | 加载到内存 | .text, .data, .bss |
| `SHF_EXECINSTR` | 可执行 | .text, .plt |
| `SHF_MERGE` | 可合并 | .rodata.cst* |
| `SHF_STRINGS` | 字符串 section | .rodata.str* |
| `SHF_TLS` | 线程局部存储 | .tdata, .tbss |

**SHF_ALLOC 决定 section 是否在运行时存在**——非 ALLOC 的 section(如 .symtab)加载时不被 mmap。

### 4.5 真实案例:readelf -S 看 libart.so

```bash
$ readelf -S libart.so

There are 32 section headers, starting at offset 0x86af0:

Section Headers:
  [Nr] Name              Type             Address           Offset    Size              EntSize          Flags  Link  Info  Align
  [ 0]                   NULL             0000000000000000  00000000  0000000000000000  0000000000000000         0     0     0
  [ 1] .note.gnu.build-id NOTE             00000000000001d8  000001d8  0000000000000048  0000000000000000  A       0     0     8
  [ 2] .text              PROGBITS         00000000000001e8  000001e8  0000000000163a78  0000000000000000  AX      0     0     16
  [ 3] .plt               PROGBITS         0000000000163c60  000163c60  0000000000000a10  0000000000000000  AX      0     0     16
  [ 4] .rodata            PROGBITS         0000000000164670  000164670  00000000001d33a4  0000000000000000  AMS     0     0     8
  [ 5] .eh_frame_hdr      PROGBITS         0000000000337a14  000337a14  000000000000bfb4  0000000000000000  A       0     0     4
  [ 6] .eh_frame          PROGBITS         00000000003439c8  0003439c8  0000000000050000  0000000000000000  A       0     0     8
  [ 7] .text.tail         PROGBITS         00000000003939c8  0003939c8  00000000000c0000  0000000000000000  AX      0     0     16
  [ 8] .ARM.exidx         ARM_EXIDX        00000000004539c8  0004539c8  0000000000000008  0000000000000000  AL      0     0     8
  [ 9] .data.rel.ro       PROGBITS         00000000004539d0  0004539d0  00000000000097c8  0000000000000000  WA      0     0     8
  [10] .fini_array        FINI_ARRAY       000000000045d198  00045d198  0000000000000010  0000000000000000  WA      0     0     8
  [11] .data              PROGBITS         000000000045d1a8  00045d1a8  0000000000009c50  0000000000009c50  WA      0     0     8
  [12] .bss               NOBITS           0000000000466e00  000466df8  0000000000000000  00000000000001b8  WA      0     0     8
  ...
  [22] .dynamic           DYNAMIC          000000000018a8e0  00018a8e0  0000000000000210  0000000000000010  WA      23    0     8
  [23] .dynstr            STRTAB           000000000018aaf0  00018aaf0  0000000000010268  0000000000000000  A       0     0     1
  [24] .dynsym            DYNSYM           000000000019ad58  00019ad58  0000000000003750  0000000000000018  A       25    8     8
  [25] .gnu.hash          GNU_HASH         000000000019e4a8  00019e4a8  00000000000039c0  0000000000000000  A       23    0     8
  [26] .relr.dyn          RELR             00000000001a1e68  0001a1e68  0000000000002b58  0000000000000008  A       0     0     8
  [27] .rel.plt           REL              00000000001a49c0  0001a49c0  0000000000003cf8  0000000000000018  AI      24    0     8
  ...
  [31] .shstrtab          STRTAB           0000000000000000  00086368  0000000000000758  0000000000000000         0     0     1
```

**关键观察**:

| section | 关键事实 |
|---|---|
| `.text` (0x163a78 字节 ≈ 1.4MB) | libart.so 主体代码,AX 标志(可读可执行) |
| `.rodata` (0x1d33a4 字节 ≈ 1.8MB) | 只读数据(字符串、const 数组),有 S(STRINGS) 标志 |
| `.plt` (0xa10 字节 ≈ 2.5KB) | **PLT(Procedure Linkage Table)**,延迟绑定用 |
| `.data.rel.ro` | vtable / typeinfo 等"只读重定位数据",在 RELRO 范围 |
| `.bss` (0x1b8 字节) | BSS 段,NOBITS 表示不占文件空间 |
| `.dynamic` (0x210 字节) | **动态链接信息**——linker64 第一个读的 section |
| `.dynsym` (0x3750 字节,每项 0x18) | **动态符号表**(0x3750/0x18 = 442 个符号) |
| `.gnu.hash` | GNU 哈希表,加速符号查找 |
| `.rel.plt` | PLT 重定位表(延迟绑定用) |
| `.shstrtab` | 32 个 section 的名字表 |

**架构师必记**:

- `.text` + `.rodata` 占了 libart.so 大部分空间(~3.2MB)——这是代码的物理大小,加载后是 r-xp
- `.dynsym` 442 个符号 / 0x18 字节 = 符号表项大小(每个 Elf64_Sym 24 字节)
- `.bss` 只有 0x1b8 字节——libart 的全局变量不多(大部分是 ART 堆里分配)

### 4.6 符号表详解:.symtab vs .dynsym

**这是 §0.1 那个真实故障的关键**。

```c
// include/uapi/linux/elf.h
typedef struct elf64_sym {
    Elf64_Word  st_name;     // 符号名(.dynstr 中的偏移)
    unsigned char st_info;    // 符号类型 + 绑定属性
    unsigned char st_other;  // 可见性
    Elf64_Half  st_shndx;    // 所在 section 索引
    Elf64_Addr  st_value;    // 符号值(地址)
    Elf64_Xword st_size;     // 符号大小
} Elf64_Sym;  // 总 24 字节
```

| 字段 | 含义 |
|---|---|
| **st_name** | 符号名在 .dynstr 中的偏移,如 `_ZN7android14MediaCodecC2Ev` |
| **st_info** | 高 4 位 = STB_*(绑定),低 4 位 = STT_*(类型) |
| **st_other** | 低 2 位 = STV_*(可见性):DEFAULT / INTERNAL / HIDDEN / PROTECTED |
| **st_shndx** | 符号所在 section;`SHN_UNDEF` 表示"未定义,需要从其他 .so 解析" |
| **st_value** | 符号值(地址) |
| **st_size** | 符号大小(函数体大小或变量大小) |

**st_info 拆解**:

```
st_info (1 字节)
├── 高 4 位:STB_*
│   ├── STB_LOCAL  (0)   本地符号,不出现在动态符号表
│   ├── STB_GLOBAL (1)   全局符号,导出
│   └── STB_WEAK   (2)   弱符号
└── 低 4 位:STT_*
    ├── STT_NOTYPE  (0)   未指定
    ├── STT_OBJECT  (1)   数据对象(变量)
    ├── STT_FUNC    (2)   函数
    ├── STT_SECTION (3)   section
    └── STT_FILE    (4)   文件名
```

**.symtab 与 .dynsym 的区别**(架构师核心):

| 维度 | .symtab | .dynsym |
|---|---|---|
| 包含 | 所有符号(包括 LOCAL、辅助) | 仅 GLOBAL + WEAK + 函数 |
| 使用者 | 静态链接器 + 调试器 | **动态链接器(linker64)** |
| release build | **strip 删掉** | **保留** |
| 大小 | 大(包含 .text 内部函数) | 小(只导出符号) |

**为什么 .so 必须有 .dynsym**:

```
linker64 看到 libfoo.so:
  1. 读 .dynamic 段,找到 DT_SYMTAB = 指向 .dynsym
  2. 读 .dynsym 表,得到导出符号列表
  3. 其他 .so / app_process 引用 libfoo 的符号时,在 .dynsym 里找
  4. 如果找不到 → "cannot locate symbol" 错误
```

**回到 §0.1 的故障**:

```
W linker: cannot locate symbol "_ZN7android14MediaCodecC2Ev" referenced by ...
```

**这就是说**:在 libart.so 的 .dynsym 里,找不到 `_ZN7android14MediaCodecC2Ev` 这个符号。

**为什么找不到**?两种可能:
1. **符号被 --gc-sections 裁掉**——只有当符号在 .symtab 而不是 .dynsym 时,gc-sections 才会处理它
2. **符号加了 STV_HIDDEN**——visibility=hidden 的符号不会出现在 .dynsym

**怎么排查**:

```bash
$ readelf -s libart.so | grep MediaCodec
# 查 .dynsym 表(默认 readelf -s 显示所有符号表,可用 -D 只显示 .dynsym)
$ readelf -Ds libart.so | grep MediaCodec
$ readelf -s libart.so | grep -c "FUNC.*GLOBAL"
# 数 GLOBAL 函数符号数量(应 > 2000)
```

**架构师视角**:release .so 的 .dynsym 符号数应该稳定(几千个),如果突然减少,可能是 strip 参数错了。

---

## 5. 关键 Section 详解:链接器真正关心的几个

### 5.1 .dynsym / .dynstr:动态符号的"名片"

**`.dynstr` 是字符串表,保存所有导出符号的名字**。`.dynsym` 是符号表,每个符号项的 `st_name` 是 `.dynstr` 中的偏移。

**架构师视角**:

- .dynstr 大小 ≈ 所有导出符号名长度 + 1(末尾的 null)
- .dynsym 大小 = 符号数 × 24 字节(64 位)
- 减少导出符号(`-fvisibility=hidden`)能显著缩小 .dynstr + .dynsym

### 5.2 .plt / .got:延迟绑定的实现

**PLT(Procedure Linkage Table)和 GOT(Global Offset Table)是延迟绑定(lazy binding)的实现机制**。本系列 P04 会详述,这里给骨架。

```
调用 libfoo 的 bar() 函数的第一次:
──────────────────────────
1. 调用跳到 .plt[bar]  (在 libnative.so 里)
2. .plt[bar] 第一条指令:跳到 .got.plt[bar] 存的地址
3. 第一次调用:.got.plt[bar] = _dl_runtime_resolve_xsavec
4. _dl_runtime_resolve 解析 bar 的真实地址
5. 写入 .got.plt[bar]
6. 跳到 bar() 执行

后续调用:
──────────────────────────
1. 调用跳到 .plt[bar]
2. .plt[bar] 第一条指令:跳到 .got.plt[bar] 存的地址
3. .got.plt[bar] = bar 的真实地址
4. 跳到 bar() 执行
```

**架构师必记**:

- 延迟绑定的"代价"是:第一次调用 bar() 时会进入 _dl_runtime_resolve,耗时比直接调用多 1-2 个数量级
- 启用 `DF_BIND_NOW` 后,所有符号在 .so 加载时立即绑定,首次调用也快——但启动慢
- PLE 04 会详细讲

### 5.3 .init_array / .fini_array:静态构造链

**`.init_array` 是一个函数指针数组**,每个元素是一个无参无返回值的函数。linker64 在加载 .so 后,**倒序**执行这个数组。

```c
// .init_array 在 ELF 里的形式
typedef void (*init_func_t)(void);

init_func_t __init_array_start[] = {
    func1,  // 最后执行
    func2,  //
    func3,  // 最先执行
};
init_func_t __init_array_end[] = { /* 哨兵 */ };
```

**linker64 的执行流程**(简化):

```c
// bionic/linker/linker.cpp
void call_constructors(Solist* solist) {
    // 倒序遍历
    for (auto&& si : solist) {
        for (ElfW(Addr) func : get_init_array(si)) {
            trace("%s: calling constructor %p", si->name, func);
            ((void(*)(void))func)();
        }
    }
}
```

**架构师必记**:

- **.init_array 是"启动期副作用"的隐形源**——它执行时,你的全局对象可能被构造,JNI_OnLoad 可能被调用
- 倒序执行:依赖的 .so 先初始化(类似 C++ 析构顺序)
- PLE 05 会详细讲

### 5.4 .dynamic:动态链接的"总目录"

**`.dynamic` 是一个 `Elf64_Dyn` 数组**,每个元素是 (d_tag, d_un) 对,告诉 linker64 在哪里找各种表:

| d_tag | 含义 | d_un 指向 |
|---|---|---|
| DT_NEEDED | 依赖的 .so 列表 | 字符串(路径) |
| DT_SYMTAB | .dynsym 的地址 | 内存中的符号表 |
| DT_STRTAB | .dynstr 的地址 | 内存中的字符串表 |
| DT_PLTGOT | .got.plt 的地址 | GOT 表 |
| DT_JMPREL | .rel.plt 的地址 | 延迟绑定重定位表 |
| DT_RELA / DT_REL | 立即绑定重定位表 | 重定位表 |
| DT_INIT / DT_INIT_ARRAY | 构造函数 | 函数指针 |
| DT_FINI / DT_FINI_ARRAY | 析构函数 | 函数指针 |
| DT_RUNPATH / DT_RPATH | 库搜索路径 | 字符串 |
| DT_FLAGS_1 | 标志位 | 数值 |
| DT_VERSYM / DT_VERDEF | 版本信息 | 数组 |
| DT_GNU_HASH | GNU 哈希表 | 哈希表 |

**linker64 启动后的第一件事**:读 .dynamic 段,把所有表的位置记下来。

### 5.5 真实案例:readelf -d 看 libart.so

```bash
$ readelf -d libart.so

Dynamic section at offset 0x18a8e0 contains 30 entries:
  Tag        Type                         Name/Value
 0x0000000000000001 (NEEDED)             Shared library: [libc.so]
 0x0000000000000001 (NEEDED)             Shared library: [libdl.so]
 0x0000000000000001 (NEEDED)             Shared library: [libm.so]
 0x0000000000000001 (NEEDED)             Shared library: [liblog.so]
 0x000000000000000c (INIT)               0x17ec28
 0x0000000000000019 (INIT_ARRAY)         0x45d180 (14 entries)
 0x000000000000001b (INIT_ARRAYSZ)       112 (bytes)
 0x0000000000000005 (STRTAB)             0x18aaf0
 0x0000000000000006 (SYMTAB)             0x19ad58
 0x000000000000000a (STRTAB)             0x19e4a0
 0x000000000000000b (SYMTAB)             0x18acf0
 0x0000000000000007 (RELA)               0x1a8608
 0x0000000000000008 (RELASZ)             0x3b8 (bytes)
 0x0000000000000009 (RELAENT)            24 (bytes per entry)
 0x0000000000000017 (JMPREL)             0x1a49c0
 0x0000000000000002 (PLTRELSZ)           0x3cf8 (bytes)
 0x0000000000000003 (PLTGOT)             0x1a87c0
 0x0000000000000014 (PLTREL)             REL
 0x000000000000000d (DT_DEBUG)           0x0
 0x0000000000000015 (DT_DEBUGLINK)       0x0
 0x0000000000000018 (BIND_NOW)           0x0
 0x000000000000001e (FLAGS)              BIND_NOW
 0x0000000000000006 (FLAGS_1)            NOW
 0x6ffffffefb000010 (VERSYM)             0x19e498
 0x6ffffff0 (VERSYM)                     0x19e498
 0x6ffffffa (RELACOUNT)                 0
 0x6ffffffe (VERNEED)                   0x1a8c30
 0x6fffffff (VERNEEDNUM)                4
 0x6ffffff0 (VERSYM)                    0x19e498
 0x6ffffff2 (PLTGOT_SHIM)               0x1a87c0
```

**关键观察**:

| Tag | 解读 |
|---|---|
| NEEDED: libc.so / libdl.so / libm.so / liblog.so | libart.so 依赖 4 个 .so |
| INIT_ARRAY 14 entries × 8 字节 = 112 字节 | 14 个构造函数 |
| BIND_NOW / FLAGS_1 NOW | **Full RELRO** + 立即绑定(无延迟) |
| JMPREL = 0x1a49c0, PLTRELSZ = 0x3cf8 | 0x3cf8/24 = 0x215 = 533 个 PLT 重定位项 |
| VERSYM | 符号版本(libc 不同版本可能不兼容) |

**架构师视角**:libart.so 启用了 Full RELRO + BIND_NOW——这是因为它包含大量关键代码,JIT/AOT 编译器对延迟绑定敏感,立即绑定能避免首次调用卡顿。

---

## 6. 三种文件类型:ET_EXEC vs ET_DYN vs ET_REL

### 6.1 ET_EXEC:传统可执行文件(已淘汰)

**ET_EXEC 有固定入口点(e_entry 是绝对地址)**,加载时不需要重定位,直接 mmap 到 e_entry 指定的地址。

**问题**:
- 入口地址固定 → 没有 ASLR
- 多个可执行文件无法共享(每个都要占用固定地址)
- **Android 7+ 禁止**——所有可执行文件必须 PIE(ET_DYN)

### 6.2 ET_DYN:共享库 / PIE

**ET_DYN 的 e_entry 是相对地址**(实际地址 = load_bias + e_entry)。**load_bias 由内核在加载时随机选**(ASLR)。

**两种 ET_DYN**:

| 类型 | 入口点 | Android 现状 |
|---|---|---|
| **共享库** (.so) | e_entry=0(无意义) | 全部 |
| **PIE 可执行文件** | e_entry 非 0 | Android 7+ 强制 |

**PIE 加载流程**:

```
1. 内核在 mmap PT_LOAD 段时,先选一个随机 load_bias
2. 每个 PT_LOAD 的实际地址 = load_bias + p_vaddr
3. 内核把 load_bias 写入 task_struct 的 ELF_PLAT_DATA(或 elf_auxv)
4. start_thread 跳到 load_bias + e_entry
```

**架构师必记**:

- PIE 的 ASLR 粒度 = 4KB(page size)或 2MB(巨型页)
- 共享库的 ASLR 粒度 = 4KB
- 调试 PIE 时,gdb 看到的地址是 `load_bias + offset`

### 6.3 ET_REL:可重定位文件(.o)

**ET_REL 是编译产物**(`.o` 或 `.obj`),还没被链接成可执行文件或共享库。

**特征**:
- 没有 Program Header(还没确定"加载蓝图")
- Section 名是相对引用(如 .text, .data)
- 链接器把多个 .o 链接成可执行文件/共享库,这一过程叫"链接"

**Android 上看不到 .o**——它只在编译阶段存在,被打包进 .so 之前消失。

### 6.4 ET_CORE:核心转储

**ET_CORE 是进程崩溃时内核生成的 core dump**。gdb 用它来还原崩溃现场。

**架构师必记**:Android 上的 tombstone 机制类似 core dump,但格式不同(纯文本 + 寄存器快照)。PLE 14 风险篇会涉及。

---

## 7. arm64 64 位 ELF 的 3 个特殊点

### 7.1 ELFCLASS64 与 Elf64_*

**arm64 强制使用 64 位 ELF**(ELFCLASS64),数据结构是 Elf64_Ehdr / Elf64_Phdr / Elf64_Shdr / Elf64_Sym。

**32 位 vs 64 位字段差异**(关键):

| 字段 | 32 位 | 64 位 | 原因 |
|---|---|---|---|
| 虚拟地址 | Elf32_Addr (4 字节) | Elf64_Addr (8 字节) | 64 位地址空间 |
| 文件偏移 | Elf32_Off (4 字节) | Elf64_Off (8 字节) | 支持 > 4GB 文件 |
| 结构体大小 | Phdr 32 / Shdr 40 / Sym 16 | Phdr 56 / Shdr 64 / Sym 24 | 地址字段变长 |

**冷启动期故障**:32 位 .so 加载到纯 64 位 Android 设备 → `wrong ELF class` 错误。

### 7.2 AArch64 重定位类型

**arm64 平台的重定位类型**(从 `R_AARCH64_*` 命名):

| 类型 | 含义 | 典型场景 |
|---|---|---|
| R_AARCH64_ABS64 | 64 位绝对地址重定位 | 64 位全局指针 |
| R_AARCH64_ABS32 | 32 位绝对地址重定位 | 兼容 32 位值 |
| R_AARCH64_GLOB_DAT | GOT 数据重定位 | `.got` 表项 |
| R_AARCH64_JUMP_SLOT | PLT 跳转重定位 | `.got.plt` 表项 |
| R_AARCH64_RELATIVE | 相对地址调整(PIE/共享库) | **load_bias + offset** |
| R_AARCH64_TLS_DTPMOD | TLS 模块引用 | thread_local 变量 |
| R_AARCH64_TLS_DTPREL | TLS 块内偏移 | thread_local 变量 |
| R_AARCH64_TLS_TPREL | TLS TP-relative 偏移 | thread_local 变量 |
| R_AARCH64_IRELATIVE | IFUNC 间接函数 | glibc 用,Android 少 |

**架构师必记**:

- `R_AARCH64_RELATIVE` 是 **shared library 加载时的主要重定位类型**(每个 .so 都有)
- `R_AARCH64_JUMP_SLOT` 是 **PLT 延迟绑定的实现**
- 这两类占了真实 .so 重定位表的 90%+

### 7.3 AArch64 CPU 特性标记(.note.gnu.property)

**arm64 平台有一个特殊 section**:`.note.gnu.property`,它告诉内核这个 .so 需要哪些 CPU 特性。

**常见特性**:

| 特性 | 含义 | 用途 |
|---|---|---|
| `GNU_PROPERTY_AARCH64_BTI` | Branch Target Identification | 防 ROP 攻击,Android 12+ 默认 |
| `GNU_PROPERTY_AARCH64_PAC` | Pointer Authentication | 防指针篡改,Android 12+ |
| `GNU_PROPERTY_AARCH64_FEATURE_1_*` | 通用特性 | 浮点、SIMD 等 |

**加载时检查**:

```
内核在 execve 路径上:
1. 读 .note.gnu.property
2. 检查 CPU 是否支持所需特性(读 HWCAP)
3. 不支持则报错(BTI 标记的 .so 在老 CPU 上跑不了)
```

**架构师必记**:升级 NDK 时,可能默认开启 BTI/PAC。如果设备 CPU 不支持,会启动崩溃。

---

## 8. 真实案例:用 readelf 拆解 libart.so

### 8.1 三步拆解法

**第一步:ELF Header**——看类型、架构、入口

```bash
$ readelf -h libart.so | head -20
```

输出(简化):
```
ELF Header:
  Magic:   7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00
  Class:                             ELF64
  Data:                              2's complement, little endian
  OS/ABI:                            UNIX - System V
  Type:                              DYN (Shared object file)     ← 共享库
  Machine:                           AArch64                        ← arm64
  Entry point address:               0x0                            ← 共享库无入口
  Number of program headers:         9                              ← 9 个段
  Number of section headers:         32                             ← 32 个 section
```

**第二步:Program Header**——看加载蓝图

```bash
$ readelf -l libart.so
```

输出(简化):
```
Program Headers:
  Type           Offset   VirtAddr           FileSiz            MemSiz              Flags  Align
  PHDR           0x000040 0x0000000000000040 0x000198           0x000198            R      0x8
  LOAD           0x000000 0x0000000000000000 0x183a08           0x183a08            R E    0x10000  ← 段1
  LOAD           0x184000 0x0000000000184000 0x00c0d0           0x00c288            RW     0x10000  ← 段2
  LOAD           0x191000 0x0000000000191000 0x001060           0x001060            R      0x10000  ← 段3
  DYNAMIC        0x18a8e0 ...                                                 RW     0x8
  GNU_STACK      ...                                                  RW     0x10            ← 栈不可执行
  GNU_RELRO      0x18a000 0x000000000018a000 0x000ae0           0x000ae0            RW     0x8      ← RELRO 范围
```

**解读**:
- 3 个 LOAD 段:r-xp / rw-p / r--p(代码+只读 / 数据 / 只读数据)
- 段 2 `MemSiz > FileSiz`:BSS 占用 0x1b8 字节
- GNU_STACK 不可执行 ✅
- GNU_RELRO 范围 [0x18a000, 0x18aae0)——后面会 mprotect 为 r--p

**第三步:关键 Section + Dynamic**——看符号和动态链接信息

```bash
$ readelf -d libart.so
$ readelf -s libart.so | grep -c "FUNC.*GLOBAL"
```

输出(简化):
```
Dynamic section contains 30 entries:
  NEEDED             libc.so / libdl.so / libm.so / liblog.so
  INIT_ARRAY         0x45d180 (14 entries)              ← 14 个构造函数
  BIND_NOW / FLAGS_1 NOW                                 ← Full RELRO + 立即绑定
  VERSYM / VERNEEDNUM 4                                 ← 4 个符号版本
```

**整合判断**:

| 维度 | libart.so 状况 | 含义 |
|---|---|---|
| 文件大小 | ~1.4MB(text) + 1.8MB(rodata) = 3.2MB | 加载后内存占用 ~3.2MB(代码/只读) |
| 段设计 | 3 段(r-xp / rw-p / r--p) | ✅ 标准安全设计 |
| 符号数 | 442(仅 .dynsym) | 大量函数被 strip |
| 依赖 | 4 个 .so | libc + libdl + libm + liblog |
| 构造函数 | 14 个(.init_array) | 启动期有副作用 |
| RELRO | Full + BIND_NOW | 启动慢 30ms,但首次调用快 |

**架构师视角**:**这就是一个"为性能优化的 .so"**——3 段分离、全 RELRO、立即绑定、只导出必要符号。

### 8.2 异常 ELF:看一个出问题的 .so

**场景**:启动期日志报 `cannot locate symbol`。

```bash
# 检查 .dynsym 中是否有目标符号
$ readelf -Ds libproblem.so | grep SomeSymbol
# 空 → .dynsym 里没有这个符号

# 检查 .symtab(更全的符号表)
$ readelf -s libproblem.so | grep SomeSymbol
12345: 0000000000123456   123 FUNC    GLOBAL DEFAULT   12 SomeSymbol
# 找到了!但它在 .symtab,不在 .dynsym

# 检查 visibility
$ readelf -s libproblem.so | grep SomeSymbol | awk '{print $5}'
# DEFAULT → visibility 没问题

# 检查是否被 strip
$ readelf -S libproblem.so | grep "symtab"
[24] .symtab          SYMTAB  ...    ← 还有 .symtab,没被 strip
```

**诊断**:
- 符号在 .symtab 但不在 .dynsym
- 链接选项里没加 `-fvisibility=default` 或 `-rdynamic`
- 修复:在编译时加 `-fvisibility=default` 或链接时加 `-rdynamic`

---

## 9. ELF 与性能/安全的取舍

### 9.1 性能取舍

| ELF 设计选择 | 启动影响 | 运行时影响 | 推荐 |
|---|---|---|---|
| **BIND_NOW** | +30-50ms(每 .so) | 首次调用 -2 个数量级 | 关键库开,辅助库关 |
| **Full RELRO** | +5-10ms | 无 | 开(安全收益 > 性能损失) |
| **3 段 LOAD** | +5-10ms(多次 mmap) | 无 | 开(代码/数据/只读分离) |
| **.gnu.hash vs .hash** | -1ms(查找快) | -1ms(查找快) | 开(新版默认) |
| **strip .symtab** | -5ms(加载更少) | gdb 不可见 | release build 开 |

### 9.2 安全取舍

| ELF 设计选择 | 安全收益 | 性能损失 |
|---|---|---|
| **BTI (.note.gnu.property)** | 防 ROP 攻击 | 启动 +2-5ms |
| **PAC (Pointer Authentication)** | 防指针篡改 | 启动 +5-10ms,运行 +1% |
| **Full RELRO** | 防 GOT 覆盖 | +5-10ms |
| **BIND_NOW** | 防延迟绑定 PLT 攻击 | +30-50ms |
| **栈不可执行 (GNU_STACK=RW)** | 防 shellcode | 几乎无 |

**架构师必记**:

- **安全加固几乎都增加启动时间**——预算要算
- **不同 .so 的加固程度可以不同**——关键库(libs, libart)全开,辅助库(第三方 SDK)可以宽松
- **攻击面 vs 性能**的平衡要在 App 启动时(< 200ms 关键)避免 BTI/PAC

---

## 10. 架构师视角:ELF 视角的 5 个核心洞察

### 10.1 洞察 1:同一份 ELF,两个视图

**架构师看 ELF 必须切换视图**:

- **加载视角** = Program Header(.text 在哪、.data 在哪、要不要 mmap)
- **链接视角** = Section Header(.dynsym 在哪、.plt 在哪、RELRO 范围)

**两个视角由不同角色消费**:
- 内核 + linker64:加载视角
- 静态链接器 + 调试器:链接视角

**冷启动期故障排查时,先用哪个视角?** **加载视角**——`readelf -l` 必看;链接视角用于深度诊断。

### 10.2 洞察 2:.dynsym 是动态链接的唯一符号源

**这意味着**:

- 任何 release .so **必须**保留 .dynsym(否则 linker64 拒绝加载)
- 任何 release .so **可以**删 .symtab(节省空间,不影响加载)
- **隐藏符号** = visibility=hidden 或 -fvisibility=hidden,符号不出现在 .dynsym
- **依赖混淆攻击**(Dependency Confusion) = 攻击者提供的 .so 在 .dynsym 里暴露同名符号,被优先解析

### 10.3 洞察 3:3 个 LOAD 段 = 性能/安全/可维护性的最优解

**为什么 3 段**:

- 1 段 rwx:加载最快,最不安全(代码可写)
- 2 段 r-xp + rw-p:标准,但 .rodata 在代码段,i-cache/d-cache 不一致
- **3 段 r-xp + rw-p + r--p:代码 / 数据 / 只读数据三分离,加载稍慢但最安全**

**架构师决策**:
- 不要自己改 NDK 参数强制 1 段
- 如果 .so 比较大(> 1MB),3 段是必要的
- 如果 .so 非常小(< 100KB,如纯资源),1 段也是可接受的

### 10.4 洞察 4:PT_GNU_STACK + PT_GNU_RELRO 是 2 个安全开关

| PT 类型 | 缺失后果 | 修复 |
|---|---|---|
| **PT_GNU_STACK=RWE** | 栈可执行 → shellcode 注入 | 编译加 `-Wl,-z,noexecstack` |
| **缺失 PT_GNU_RELRO** | GOT 段可写 → 攻击者改函数指针 | 链接加 `-Wl,-z,relro,-z,now` |

**架构师必查**:

```bash
# 检查所有 .so 的安全属性
for f in /data/app/~~*/lib/*/lib*.so; do
    echo "=== $f ==="
    readelf -l "$f" | grep -E "GNU_STACK|GNU_RELRO"
done
```

如果有 RWE 的 GNU_STACK 或缺失 GNU_RELRO,**立即修复**。

### 10.5 洞察 5:从 ELF 字段直接映射到故障现象

| ELF 字段 | 异常值 | 故障现象 |
|---|---|---|
| e_ident.EI_CLASS | 1(32 位) | 64 位设备加载失败 |
| e_machine | 0x3E(x86_64) | arm64 设备加载失败 |
| e_type | ET_EXEC | Android 7+ 拒绝加载 |
| PT_GNU_STACK | 缺 RWE | 安全告警(虽然能跑) |
| .dynsym | 0 个符号 | linker64 拒绝加载 |
| .dynamic | 缺 DT_NEEDED | linker64 不知道依赖什么 |
| .init_array | 大小异常 | 启动期构造链问题 |

**架构师必记**:**这 7 个字段的异常,覆盖了 80% 的 ELF 侧冷启动故障**。

---

## 11. ELF 工具链速查

### 11.1 必装工具

| 工具 | 用途 | 关键命令 |
|---|---|---|
| **readelf** | ELF 信息查看 | `-h` 头 / `-l` 段 / `-S` section / `-s` 符号 / `-d` 动态 / `-r` 重定位 |
| **objdump** | 反汇编 | `-d` 反汇编 / `-t` 符号表 / `-T` 动态符号 |
| **nm** | 符号表查看 | `-D` 动态符号 / `-a` 所有 / `--defined-only` |
| **ldd** | 查看依赖 | (Android 上不可用,改用 `readelf -d`) |
| **file** | 文件类型 | `file libfoo.so` → "ELF 64-bit LSB shared object, ARM aarch64" |
| **strings** | 字符串提取 | `strings libfoo.so` 看导出符号/版本信息 |
| **aarch64-linux-gnu-objcopy** | strip | `--strip-all` 删 .symtab,保留 .dynsym |
| **llvm-readelf** | LLVM 版 readelf | macOS 上用 |

### 11.2 5 个常用诊断组合

**组合 1:基础信息**(任何时候先用)

```bash
readelf -h libfoo.so
file libfoo.so
```

**组合 2:加载信息**(查加载失败)

```bash
readelf -l libfoo.so         # 看 PT_LOAD 段
readelf -d libfoo.so         # 看 NEEDED
readelf --segments libfoo.so | grep INTERP  # 查解释器
```

**组合 3:符号信息**(查类/函数找不到)

```bash
readelf -Ds libfoo.so | grep <symbol>     # 动态符号
readelf -s libfoo.so | grep <symbol>      # 所有符号
nm -D libfoo.so | grep <symbol>            # nm 简化版
```

**组合 4:重定位信息**(查 undefined symbol)

```bash
readelf -r libfoo.so                       # 所有重定位
readelf -r libfoo.so | grep UND            # 未解析的重定位
readelf --dyn-syms libfoo.so | grep UND    # 动态符号里的 UND
```

**组合 5:section 信息**(查 strip / 安全属性)

```bash
readelf -S libfoo.so | grep -E "symtab|debug"   # 查 strip 状态
readelf -S libfoo.so | grep -E "got|plt"        # 查 GOT/PLT
```

---

## 12. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **ELF 同时满足三方需求** | 编译/链接器看 section、内核看 program、调试器看 section |
| 2 | **3 个 LOAD 段是性能/安全的最优解** | r-xp(rwx 危险) / r-xp+rw-p(.rodata 错位) / 3 段(标准) |
| 3 | **.dynsym 是动态链接的唯一符号源** | .symtab 可 strip,.dynsym 不可 |
| 4 | **PT_GNU_STACK + PT_GNU_RELRO 是 2 个安全开关** | 缺一不可 |
| 5 | **从 ELF 字段直接映射到故障现象** | 7 个字段的异常覆盖 80% ELF 侧冷启动故障 |

---

## 13. 下一篇预告

03 篇《Bionic 动态链接器:linker64 的工作机制》会沿着本篇埋下的线索,深入讲:

- `_start` 自举:linker 怎么重定位自己
- `soinfo` 数据结构:一个 .so 在 linker 内部的全部状态
- `find_library` 路径:DT_RUNPATH / DT_RPATH / 默认路径 / 内置库
- NEEDED 树遍历:广度优先 + 递归 + 去重
- ELF 命名空间:Android 7+ 的 namespace 隔离
- `dlopen` / `dlsym` / `dlclose` 运行时 API

**03 篇预计 3 天后产出**,届时一起发你看。

---

## 附录 A:ELF Header 字段速查(64 位 arm64)

| 字段 | 偏移 | 大小 | 取值范围 | 含义 |
|---|---|---|---|---|
| e_ident | 0 | 16 | 7f 45 4c 46 ... | 标识符(magic/class/data/version/OSABI) |
| e_type | 16 | 2 | 0/1/2/3/4 | NONE/REL/EXEC/DYN/CORE |
| e_machine | 18 | 2 | 0x28/0xB7/0x3E | ARM/AArch64/x86-64 |
| e_version | 20 | 4 | 1 | EV_CURRENT |
| e_entry | 24 | 8 | 虚拟地址 | 入口点(共享库为 0) |
| e_phoff | 32 | 8 | 文件偏移 | Program Header 表偏移 |
| e_shoff | 40 | 8 | 文件偏移 | Section Header 表偏移 |
| e_flags | 48 | 4 | 架构相关 | AArch64 特性标记 |
| e_ehsize | 52 | 2 | 64(64 位) | ELF Header 大小 |
| e_phentsize | 54 | 2 | 56(64 位) | 单个 PH 大小 |
| e_phnum | 56 | 2 | 0-65535 | PH 数量 |
| e_shentsize | 58 | 2 | 64(64 位) | 单个 SH 大小 |
| e_shnum | 60 | 2 | 0-65535 | SH 数量 |
| e_shstrndx | 62 | 2 | 0-e_shnum | .shstrtab 索引 |

## 附录 B:Program Header 类型速查

| p_type | 名称 | 含义 | 内核/linker 动作 |
|---|---|---|---|
| 0 | PT_NULL | 忽略 | 跳过 |
| 1 | PT_LOAD | 可加载段 | **mmap 到 p_vaddr** |
| 2 | PT_DYNAMIC | 动态链接信息 | linker64 读 .dynamic 段 |
| 3 | PT_INTERP | 动态链接器路径 | mmap 链接器并跳到它 |
| 4 | PT_NOTE | 注释 | 读 build-id |
| 6 | PT_PHDR | PHDR 表自身 | 有时 mmap |
| 7 | PT_TLS | 线程局部存储 | 为 TLS 分配 |
| 0x6474e550 | PT_GNU_EH_FRAME | 异常处理 frame | 链接器读 |
| 0x6474e551 | **PT_GNU_STACK** | 栈执行权限 | 决定栈是否可执行 |
| 0x6474e552 | **PT_GNU_RELRO** | RELRO 范围 | linker64 mprotect 为 r--p |
| 0x6474e553 | PT_GNU_PROPERTY | AArch64 属性 | 内核读 BTI/PAC |

## 附录 C:Section 类型速查(常用)

| sh_type | 名称 | 含义 | 是否在运行时存在 |
|---|---|---|---|
| 0 | SHT_NULL | 忽略 | - |
| 1 | SHT_PROGBITS | 程序数据 | 是 |
| 2 | **SHT_SYMTAB** | 完整符号表 | 否(strip 后) |
| 3 | SHT_STRTAB | 字符串表 | 部分 |
| 6 | **SHT_DYNAMIC** | 动态信息 | 是 |
| 8 | **SHT_NOBITS** | 不占文件空间(.bss) | 是(零页) |
| 11 | **SHT_DYNSYM** | 动态符号表 | 是 |
| 0x6ffffff6 | SHT_GNU_HASH | GNU 哈希 | 是 |
| 0x70000003 | SHT_ARM_ATTRIBUTES | ARM 属性 | 是 |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 03 linker64 | DT_NEEDED / DT_SYMTAB / DT_STRTAB / DT_PLTGOT / DT_JMPREL 的使用 |
| 04 重定位 | .rel.plt / .rela.dyn / .plt / .got 的工作机制 |
| 05 .init_array | DT_INIT_ARRAY / DT_INIT_ARRAYSZ 的解析 |

---

> **本篇把 ELF 拆解到"字段级",目的是让你拿到任何 .so 都能在 5 分钟内用 readelf 看清它的关键属性。**
> **03 篇会在这个基础上,讲 linker64 怎么用这些字段——把"静态文件"变成"运行时实例"。**
> **记住 3 个段、3 个安全开关、3 类异常映射,你的 ELF 视角就立住了。**
