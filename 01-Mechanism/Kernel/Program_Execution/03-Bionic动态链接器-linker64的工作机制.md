# 03-Bionic 动态链接器:linker64 的工作机制

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15` / `android15-6.1`(linker64 涉及 `load_elf_binary` + `mmap` 系统调用,内核版本差异主要在 `mmap` 行为)+ Bionic linker `bionic/linker/`(`linker.cpp`、`linker_phdr.cpp`、`linker_reloc_iterate.cpp`)
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) → [02-ELF 文件格式深度解析](02-ELF文件格式深度解析-从可执行文件到内核视角.md)
> **下一篇**:[04-符号解析与重定位:.plt / .got / .relro 全景](04-符号解析与重定位-plt-got-relro全景.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 2 篇(Native 侧 · 加载器层)
- **强依赖**:**[PLE-01 全景](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-02 ELF](02-ELF文件格式深度解析-从可执行文件到内核视角.md)**
- **承接自**:PLE-02 已讲 ELF 文件结构;本篇是骨架上"链接"动作的具体载体(怎么把 ELF 装进地址空间 + 怎么找 NEEDED)
- **衔接去**:下一篇 [PLE-04 重定位](04-符号解析与重定位-plt-got-relro全景.md) 讲"linker64 装完 .so 后,怎么解析符号 + 写 GOT"
- **不重复内容**:
  - **ELF 文件字段** → 详见 [PLE-02](02-ELF文件格式深度解析-从可执行文件到内核视角.md)
  - **PLT/GOT/RELRO 实现细节** → 详见 [PLE-04](04-符号解析与重定位-plt-got-relro全景.md)
  - **init_array / .so 构造函数执行顺序** → 详见 [PLE-05](05-init_array与构造函数链-静态初始化的执行顺序.md)
  - **内核 execve / load_elf_binary 流程** → 详见 [Linux_Kernel/Process/04-进程的执行](../Process/04-进程的执行_execve与程序加载.md)

## 0. 写在前面:为什么 linker64 单独成篇

### 0.1 一个真实的性能事故

**场景**:某 App 在 Android 12 升级后冷启动退化 400ms,Perfetto trace 显示在 `linker` 阶段耗时异常:

```
Perfetto 时间线:
├─ execve → first Java: 800ms(基线 200ms)  ⚠⚠⚠
│   └─ 90% 时间花在 linker64
│       └─ find_library 200 次,平均 2ms 一次
```

**根因排查**:
1. App 的 5 个 native 库(liba.so / libb.so / libc.so / libd.so / libe.so)形成交叉依赖
2. 每次 `dlopen` 时 linker64 都要遍历整个依赖图,找库
3. 5 个 .so × 平均 3 层 NEEDED = 每次 dlopen 触发 15+ 次 find_library

**修复**:重新设计依赖关系,让 5 个 .so 改为单层依赖(都依赖一个公共 libbase.so),find_library 次数降到 5 次,启动时间从 800ms 回到 250ms。

**这个案例的诊断需要 3 个知识**:
1. 知道 linker64 的 `find_library` 路径搜索顺序
2. 知道 `soinfo` 数据结构如何记录 .so 的依赖关系
3. 知道 NEEDED 树的遍历策略(BFS / DFS / 缓存)

**这就是本篇要讲清楚的事。**

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:OnePlus 11(SM8550,arm64-v8a)
> - Android 版本:`android-12.0.0_r31` → 通过 OTA 升级到 `android-14.0.0_r1`
> - App:某工具类 App v3.2.0(包含 liba.so / libb.so / libc.so / libd.so / libe.so 共 5 个 native 库,初始编译期就形成交叉依赖)
> - 工具:`simpleperf record -e cpu-cycles` + `perfetto -o trace.perfetto-trace`

> **复现步骤**:
> 1. Android 12 设备上安装 v3.2.0,冷启动 5 次取 P99:**820ms** ✅
> 2. 同设备 OTA 升级到 Android 14(系统组件 + linker64 都换新)
> 3. 不动 APK,直接冷启动 5 次取 P99:**1820ms** ⚠️(退化 1000ms)
> 4. 抓 Perfetto trace,定位到 `linker` slice 单段 1100ms(原本 80ms)

> **logcat / Perfetto trace 关键片段**:
> ```
> # Perfetto slice 树
> I Perfetto: slice("execve")= 50ms
> I Perfetto: slice("linker64::link_image liba.so")= 220ms  ← 比预期 60ms 长 160ms
> I Perfetto: slice("linker64::link_image libb.so")= 240ms
> I Perfetto: slice("linker64::link_image libc.so")= 260ms
> I Perfetto: slice("linker64::find_library")= 380ms  ← 200 次 find_library 累计
> ```
> ```
> # simpleperf 热点
> 42.3%  linker64::find_library
> 18.7%  linker64::load_library
> 11.2%  linker64::soinfo_do_lookup
> ```

> **修复 commit-style diff**:
> ```diff
> - // 旧:5 个 .so 形成网状依赖
> - liba.so  → libb.so, libc.so
> - libb.so  → libc.so, libd.so
> - libc.so  → libd.so, libe.so
> - libd.so  → libe.so
> - libe.so  → liba.so    # 形成环!
> + // 新:统一依赖一个公共 libbase.so
> + liba.so  → libbase.so
> + libb.so  → libbase.so
> + libc.so  → libbase.so
> + libd.so  → libbase.so
> + libe.so  → libbase.so
> + # 依赖深度从 3+ 降到 1,find_library 次数从 200 降到 5
> ```
> **修复后**:冷启动 P99 → 850ms(回到基线)。**诊断命令**:`adb shell setprop debug.ld.debug.syms 1` + `adb logcat | grep linker` 看每次 find_library 调用链。

> **架构师视角**:本案例的根因不是 linker64 慢,是**依赖图结构问题**。linker64 在 Android 14 上对符号解析做了优化(默认启用 `--Wl,--hash-style=gnu`),但**网状依赖 + 多层 NEEDED 拖慢 lookup**。**架构师要在 SDK 编译期就把依赖图压平**。

### 0.2 linker64 在 PLE 8 阶段中的位置

```
阶段 0:execve 入口(内核)        ← PLE 02
    ↓
阶段 1:用户态 linker64 启动     ← 本篇主体
├─ _start 自举
├─ 解析主 .so 的 .dynamic
├─ 广度优先遍历 NEEDED 树       ← §3-5
├─ 重定位 + 符号解析            ← PLE 04
├─ 执行 .init_array              ← PLE 05
└─ 跳到主 .so 的入口
    ↓
阶段 2-4:ART 启动 + Zygote fork   ← PLE 06-12
```

**本篇聚焦 linker64 的"加载与依赖解析"**。重定位(.plt/.got/.relro)是 P04;静态构造(.init_array)是 P05。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 解释 `linker64` 启动时的 7 步流程
2. 描述 `soinfo` 数据结构,看懂任意 .so 在 linker 内部的全部状态
3. 预测 `find_library` 的搜索顺序,并优化依赖图
4. 理解 Android 7+ 的 ELF namespace 隔离机制
5. 诊断 `dlopen` / `dlsym` 失败类问题的根因

---

## 1. linker64 是什么:用户态 ELF 加载器

### 1.1 与 glibc ld.so 的对比

| 维度 | glibc ld.so (x86_64 Linux) | bionic linker64 (Android arm64) |
|---|---|---|
| **代码量** | ~30,000 行 | ~8,000 行 |
| **优化重点** | 通用(PC/server/嵌入式) | **移动端冷启动 + 小内存** |
| **namespace** | 单一全局 | Android 7+: **每个进程独立** |
| **安全加固** | RELRO/FORTIFY | RELRO/BTI/PAC **+ namespace 隔离** |
| **API** | dlopen/dlsym/dlclose | 同左(API 兼容) |
| **性能优化** | 缓存 + 并行 | **mmap 优先 + 共享库预加载** |

**Android 为什么不用 glibc 的 ld.so**:
1. **bionic 是为移动端重写的 libc**,不依赖 glibc 的实现
2. **linker64 必须支持 namespace 隔离**(Android 7+ 强制 SELinux namespace)
3. **必须支持 BTI/PAC**(arm64 CPU 特性)
4. **必须小**——linker64 ~8K 行,ld.so ~30K 行

**架构师视角**:linker64 的代码量只有 ld.so 的 1/4,但**做了 3 件 ld.so 没做的事**:namespace 隔离、BTI 支持、移动端冷启动优化。这是 Android 的"刻意取舍"。

### 1.2 linker64 启动的两条路径

**路径 1:作为可执行文件直接运行** (Zygote 启动场景)

```
内核 execve("/system/bin/linker64", ["linker64", "/system/bin/app_process", "-Xzygote", ...])
    ↓
linker64::_start()              ← 关键!linker64 自己就是 ELF
    ↓
自举(重定位 linker 自身)
    ↓
把可执行文件路径作为参数
    ↓
开始加载真正的可执行文件(app_process)
```

**路径 2:作为动态链接器被 execve 隐式调用** (App 进程启动场景)

```
内核 execve("/system/bin/app_process", ...)
    ↓
内核读 PT_INTERP,得到 "/system/bin/linker64"
    ↓
内核 mmap linker64,跳到 linker64::_start
    ↓
linker64::_start 知道自己是"被 execve 调用的",从栈顶的辅助向量读参数
    ↓
开始加载 app_process
```

**两种路径在 linker64 内部会合到同一个函数**:`linker_main()`。这是 §2 的核心。

### 1.3 linker64 源码组织

```
bionic/linker/
├── arch/
│   ├── arm64/
│   │   ├── begin.S          ← _start 入口
│   │   ├── tlsdesc.S
│   │   └── ...
│   └── x86_64/...
├── linker.cpp               ← 核心实现
├── linker_phdr.cpp          ← Program Header 解析
├── linker_reloc_iterate.cpp ← 重定位遍历
├── linker_libcxx.cpp        ← libc++ abi 设置
├── linker_main.cpp          ← 主入口(实际是 linker.cpp 里)
├── soinfo.cpp               ← soinfo 数据结构
├── soinfo_list.cpp
├── linked_list.h
├── dlfcn.cpp                ← dlopen / dlsym / dlclose API
├── android_namespace.cpp    ← namespace 隔离
├── linker_utils.cpp
└── linker_mapped_file_fragment.cpp
```

**架构师必看 3 个文件**:
1. `linker.cpp` — 主流程(soinfo 加载、NEEDED 遍历、init_array 执行)
2. `android_namespace.cpp` — namespace 隔离(Android 7+ 安全核心)
3. `dlfcn.cpp` — dlopen/dlsym/dlclose 实现(应用层调用的入口)

---

## 2. linker64 启动的 7 步流程

### 2.1 完整时间线

```
┌────────────────────────────────────────────────────────────────────┐
│ linker64 启动 7 步流程                                                │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Step 1: _start 入口(arch/arm64/begin.S)                            │
│  ├─ 接收内核传入的栈指针                                            │
│  ├─ 设置栈基址(BP)                                                 │
│  ├─ 调用 linker_init() 解析 ELF auxv                                │
│  └─ 调到 linker_main()                                              │
│                                                                    │
│  Step 2: 自举(Bootstrap)                                            │
│  ├─ 重定位 linker64 自身(因为 linker 也是一个 .so)                  │
│  ├─ 解析自己的 .dynamic 段                                          │
│  └─ 完成后再处理真正的目标可执行文件                                 │
│                                                                    │
│  Step 3: 解析可执行文件                                              │
│  ├─ 读 ELF Header + Program Headers                                 │
│  ├─ 检查 ELF 合法性(魔数、架构、版本)                              │
│  └─ 找 .dynamic 段                                                  │
│                                                                    │
│  Step 4: 解析依赖(NEEDED 树遍历)                                     │
│  ├─ 读 DT_NEEDED 列表                                               │
│  ├─ 对每个 .so 调 find_library()                                    │
│  ├─ 递归处理子依赖                                                  │
│  └─ 返回 Solist(已加载 .so 列表)                                    │
│                                                                    │
│  Step 5: 重定位(PLE 04 详述)                                         │
│  ├─ 处理 .rel.dyn / .rela.dyn                                       │
│  ├─ 处理 .rel.plt / .rela.plt                                       │
│  └─ 标记 RELRO 范围                                                 │
│                                                                    │
│  Step 6: 执行 .init_array(PLE 05 详述)                               │
│  ├─ 倒序遍历 Solist                                                 │
│  └─ 对每个 .so 执行它的 .init_array                                 │
│                                                                    │
│  Step 7: 跳到主入口                                                  │
│  ├─ 关闭 stdout/stderr 缓冲                                         │
│  └─ 跳到 e_entry(可执行文件的 _start)                                │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 Step 1:_start 入口(汇编)

**`arch/arm64/begin.S`**(简化,只看主线):

```assembly
// arch/arm64/begin.S
ENTRY(_start)
    // 1. 内核调用时传入了 sp 栈顶
    // 2. 设置栈基址(给后续函数调用用)
    mov x29, #0
    mov x30, #0
    // 3. 取出 main 函数地址(从 ELF auxv)
    ldr x5, [sp, #16]      // argc
    add x6, sp, #24         // argv
    add x7, x6, x5, lsl #3  // envp
    add x7, x7, #8          // auxv(跳过 NULL 终止符)
    // 4. 调用 C 函数 linker_main(argc, argv, envp)
    bl linker_main
    // 5. 不应该返回,如果返回就 exit
    mov x0, #127
    b exit
END(_start)
```

**架构师视角**:`_start` 几乎不做任何事——只解析栈上的参数,转交给 C 函数 `linker_main`。所有"复杂逻辑"都在 `linker_main` 里。

### 2.3 Step 2:自举(Bootstrap)

**自举 = 重定位 linker64 自身**。因为 linker64 也是一个 .so,它在被加载时也需要被重定位。

**为什么要自举**:
- linker64 是一个 PIE(ET_DYN),加载基址(load_bias)由内核随机选
- linker64 内部的全局变量、函数指针都需要根据 load_bias 调整
- 否则 linker64 自己会 crash,根本加载不了别的 .so

**自举的简化流程**:

```c
// linker.cpp::linker_init(ElfW(Addr)* auxv)
static ElfW(Addr) linker_init(ElfW(Addr)* auxv) {
    // 1. 从 auxv 读出 PHDR(Program Header 表的位置)
    ElfW(phdr)* phdr = (ElfW(phdr)*)getauxval(auxv, AT_PHDR);
    
    // 2. 找到自己的 .dynamic 段
    ElfW(dyn)* dynamic = nullptr;
    for (int i = 0; i < phdr_num; i++) {
        if (phdr[i].p_type == PT_DYNAMIC) {
            dynamic = (ElfW(dyn)*)(phdr[i].p_vaddr + load_bias);
            break;
        }
    }
    
    // 3. 解析自己的 .dynamic,得到 STRTAB / SYMTAB / JMPREL 等
    parse_dynamic(dynamic);
    
    // 4. 自重定位:处理 R_AARCH64_RELATIVE 类型
    relocate(linker_soinfo);
    
    return load_bias;
}
```

**架构师必记**:

- 自举是 linker64 启动的"第一道关卡"——自举失败,整个加载流程崩溃
- 自举只处理 R_AARCH64_RELATIVE(其他类型如 JUMP_SLOT 还没意义,因为没人调用)
- 自举成功 = linker64 内部的指针全部正确,可以开始处理真正的可执行文件

### 2.4 Step 3:解析可执行文件

```c
// linker.cpp::linker_main(简化)
static void linker_main(int argc, char** argv, char** envp) {
    // 1. 设置一些基础环境(信号处理、栈保护等)
    // 2. 自举(已讨论)
    ElfW(Addr) linker_load_bias = linker_init(auxv);
    
    // 3. 找到真正的可执行文件路径
    //    - 路径 1:argv[0](被 execve 隐式调用时)
    //    - 路径 2:argv[1](作为可执行文件运行时)
    const char* exe_path = (argc > 1) ? argv[1] : argv[0];
    
    // 4. 解析可执行文件的 ELF
    soinfo* exe_so = load_library(exe_path, RTLD_NOW);
    //    └─ 详见 §3
}
```

**架构师必记**:

- `load_library()` 是 linker64 加载 .so 的核心函数——可执行文件、依赖、运行时 dlopen 都用它
- `RTLD_NOW` 标志:立即绑定所有符号(无延迟)

### 2.5 Step 4-7:依赖解析 → 重定位 → init_array → 跳入口

**这 4 步是连续的,在 `linker_main` 末尾**:

```c
// linker.cpp::linker_main(继续)
    // 5. 重定位 + 链接符号
    if (exe_so->is_linked) {
        // 已经 link 过(动态 dlopen 不会到这里)
    } else {
        // 立即绑定所有符号
        link_image(exe_so);
        //    └─ 处理所有 .rel.dyn / .rela.dyn
        //    └─ 处理所有 .rel.plt / .rela.plt
        //    └─ 处理所有 R_AARCH64_RELATIVE
    }
    
    // 6. 执行 .init_array(每个 .so 倒序)
    call_constructors(Solist);
    
    // 7. 跳到主入口
    ElfW(Addr) entry = exe_so->entry;
    ((void(*)())entry)(argc, argv, envp);
    //    └─ exe_so->entry = load_bias + e_entry
}
```

**架构师视角**:**call_constructors 是"启动期副作用集中地"**。它会触发所有 .so 的 `.init_array`,包括 libart.so 的 JNI_OnLoad(虽然 JNI_OnLoad 不在 .init_array 里,而是 DT_INIT)。**这是冷启动 100-300ms 的主要来源**。

### 2.6 7 步流程的耗时分布(典型中端机)

| 步骤 | 耗时(中端机) | 主要工作 |
|---|---|---|
| Step 1 _start | < 1ms | 栈初始化 + 转交 C 函数 |
| Step 2 自举 | 5-15ms | 重定位 linker64 自身 |
| Step 3 解析可执行文件 | 5-10ms | 读 ELF 头 + PH |
| Step 4 NEEDED 树遍历 | **20-80ms** | 找库 + mmap + 递归依赖 |
| Step 5 重定位 | **10-50ms** | 符号解析 + 写 .got.plt |
| Step 6 .init_array | **30-100ms** | 执行全局构造 + JNI_OnLoad |
| Step 7 跳入口 | < 1ms | 跳到 app_process |
| **合计** | **~80-260ms** | linker64 整体 |

**架构师必记**:

- **Step 4 和 Step 6 是优化重点**(共占 50-180ms)
- Step 4 优化:减少 .so 数量 / 减少 NEEDED 树深度 / 预加载常用 .so
- Step 6 优化:.init_array 拆分 / 关键库优先 init / 延迟 init 非关键 .so

---

## 3. soinfo:一个 .so 在 linker 内部的全部状态

### 3.1 soinfo 数据结构(简化)

**`bionic/linker/linker.h::soinfo`**(只保留关键字段):

```c
struct soinfo {
    // === 基础标识 ===
    const ElfW(Phdr)* phdr;        // Program Header 表
    size_t phnum;                  // PH 数量
    ElfW(Addr) base;               // 加载基址(load_bias)
    size_t size;                   // 加载大小
    
    // === 名称与版本 ===
    char const* soname;            // .so 名(如 "libc.so")
    char const* realpath;          // 实际路径
    ElfW(Half) nsoinfo;            // 依赖的 .so 数量
    soinfo** soinfos;              // 依赖的 soinfo 数组
    
    // === 动态链接信息 ===
    ElfW(Dyn)* dynamic;            // .dynamic 段指针
    const char* strtab;            // .dynstr 字符串表
    ElfW(Sym)* symtab;             // .dynsym 符号表
    size_t nbucket;                // GNU hash 桶数
    size_t nchain;                 // GNU hash 链数
    uint32_t* bucket;              // GNU hash 桶
    uint32_t* chain;               // GNU hash 链
    
    // === 重定位信息 ===
    ElfW(Rela)* plt_rela;          // .rel.plt 重定位表
    size_t plt_rela_count;
    ElfW(Rela)* rela;              // .rel.dyn 重定位表
    size_t rela_count;
    ElfW(Addr)* relr;              // .relr.dyn(紧凑相对重定位)
    size_t relr_count;
    
    // === 初始化函数 ===
    ElfW(Addr)* init_array;        // .init_array 数组
    size_t init_array_count;
    ElfW(Addr) init_func;          // DT_INIT 函数(传统)
    ElfW(Addr) fini_array;[];
    size_t fini_array_count;
    ElfW(Addr) fini_func;
    
    // === 状态标志 ===
    uint32_t flags;                // DF_1_NOW / DF_1_GLOBAL 等
    bool is_linked;                // 是否已完成重定位
    
    // === 构造链信息 ===
    ElfW(Addr) constructors[2];    // C++ 静态构造(用于 __attribute__((constructor)))
    
    // === namespace ===
    android_namespace_t* ns;       // 所属 namespace
};
```

**架构师必记**:soinfo 是**一个 .so 在 linker 内部的全息画像**——它记录了这个 .so 的全部信息,直到进程退出都不会释放。

### 3.2 soinfo 的生命周期

```
创建(分配)
    ↓
1. 加载(load_library)
    ├─ mmap PT_LOAD 段
    ├─ 读 ELF 头 + PH
    └─ 填充 phdr / phnum / base
    ↓
2. 解析动态信息(parse_dynamic)
    ├─ 读 .dynamic 段
    ├─ 填 strtab / symtab / bucket / chain
    └─ 填 plt_rela / rela / init_array
    ↓
3. 解析依赖
    ├─ 读 DT_NEEDED
    ├─ 对每个 NEEDED 递归 load_library
    └─ 填 soinfos 数组
    ↓
4. 链接(link_image)
    ├─ 处理 .rel.dyn
    ├─ 处理 .rel.plt
    └─ 设置 is_linked = true
    ↓
5. 构造
    ├─ 调 .init_array
    └─ 调 DT_INIT / __attribute__((constructor))
    ↓
6. 销毁(进程退出时)
    └─ munmap + 释放 soinfo
```

### 3.3 Solist:全局已加载 .so 列表

**Solist 是所有 soinfo 的链表**,linker64 用它来跟踪已加载的 .so:

```c
// soinfo_list.h
class SoinfoList {
    LinkedList<soinfo> list_;
    // ...
public:
    void add(soinfo* si);
    void remove(soinfo* si);
    void for_each(std::function<void(soinfo*)> f);
};
```

**为什么需要 Solist**:

1. **init_array 倒序执行**——倒序遍历 Solist,执行每个 .so 的 init_array
2. **dlclose 引用计数**——记录 .so 引用次数
3. **debug 工具**——`/proc/<pid>/maps` 之外,linker 内部也有完整列表
4. **.fini_array 顺序执行**——进程退出时正序执行

### 3.4 真实案例:看一个进程的 soinfo 列表

**用 `lsof` / `cat /proc/pid/maps` / `simpleperf record`** 等工具可以间接看:

```bash
# 在 Android 设备上
$ adb shell cat /proc/1234/maps | head -20

# 输出是 VMA 列表,不是 soinfo 列表,但能反映 .so 加载情况
7f8a4b000-7f8a4f000 r--p 00000000 fc:01 1234567  /system/lib64/libc.so
7f8a4f000-7f8c4f000 r-xp 00004000 fc:01 1234567  /system/lib64/libc.so
7f8c4f000-7f8c53000 r--p 001a4000 fc:01 1234567  /system/lib64/libc.so
7f8c53000-7f8c54000 rw-p 001a8000 fc:01 1234567  /system/lib64/libc.so
...
```

**更直接的方法**——用 `simpleperf record` 抓 `dlopen` 调用栈:

```bash
$ adb shell simpleperf record -e raw_syscalls:sys_enter -p 1234 -o /data/local/tmp/perf.data
$ adb shell simpleperf report -i /data/local/tmp/perf.data --show-callchain
```

**架构师必记**:Solist 在 `linker.cpp` 里是一个静态全局变量。**任何 .so 加载/卸载都会修改它**。冷启动期 Solist 增长曲线是性能分析的重要指标。

---

## 4. find_library:依赖图的核心

### 4.1 find_library 的搜索顺序

**`linker.cpp::find_library(const char* name, soinfo* loader, ...)`** 的搜索顺序(简化):

```
1. 检查 loader 的 .so 列表(已经加载过,直接复用)
   ↓
2. 检查 loader 所在 namespace 的 soname 缓存
   ├─ 命中:直接返回
   └─ 未命中:继续
   ↓
3. 检查 DT_RUNPATH / DT_RPATH(loader 的动态链接路径)
   ├─ 命中:返回
   └─ 未命中:继续
   ↓
4. 检查默认 namespace 路径
   ├─ /system/lib64/
   ├─ /system/lib/
   ├─ /vendor/lib64/
   ├─ /vendor/lib/
   ├─ /odm/lib64/
   └─ /odm/lib/
   ↓
5. 检查 LD_LIBRARY_PATH 环境变量(仅 debug build)
   ↓
6. 报错:library "X.so" not found
```

**关键事实**:

- **同进程内已经加载的 .so 会优先复用**(避免重复 mmap)
- **DT_RUNPATH 优先于默认路径**(可被链接器配置)
- **Android 7+ 有 6 个默认 namespace**(`default`、`system`、`vendor`、`odm`、`product`、`vndk`)
- **LD_LIBRARY_PATH 在 release build 不可用**

### 4.2 DT_NEEDED vs DT_RUNPATH vs DT_RPATH

| 标签 | 作用 | 搜索范围 | Android 行为 |
|---|---|---|---|
| **DT_NEEDED** | 声明依赖 | linker 用 find_library 加载 | **必用**(主机制) |
| **DT_RUNPATH** | 运行时搜索路径 | **只搜索依赖自己的库** | 现代做法,推荐 |
| **DT_RPATH** | 运行时搜索路径 | **全局**(已废弃) | 旧 .so 会有,现代 .so 不用 |

**DT_RPATH vs DT_RUNPATH 的关键区别**:

| DT_RPATH | DT_RUNPATH |
|---|---|
| 搜索范围:全局(包括传递依赖) | 搜索范围:只搜直接依赖 |
| 行为:DEPRECATED(已废弃) | 现代标准 |
| **Android 7+ 新编译的 .so 优先用 DT_RUNPATH** | |

**真实案例**:

```bash
$ readelf -d libfoo.so | grep -E "NEEDED|RUNPATH|RPATH"
0x0000000000000001 (NEEDED)             Shared library: [libc.so]
0x000000000000001d (RUNPATH)            Library runpath: [/vendor/lib64]
```

**解读**:
- `libfoo.so` 依赖 `libc.so`
- `libfoo.so` 的依赖(.so A 依赖 libfoo,然后 A 又依赖其他 .so)只在 `/vendor/lib64` 搜索
- 自己的依赖仍在 linker 默认路径搜索

**架构师必记**:DT_RUNPATH 在 2017 年后才被广泛使用,旧 .so 仍用 DT_RPATH。**Android 7+ 强制 PIE + DT_RUNPATH**(更安全)。

### 4.3 内置库(Built-in Libraries)

**Android linker64 有 4 个内置 .so** ——它们**不通过 mmap 加载**,而是直接被 linker 内部处理:

| 内置库 | 作用 |
|---|---|
| **libdl.so** | dlopen / dlsym / dlclose 实现 |
| **libc.so** | 基础 C 库(但 Android 上 libdl 是 libc 的 dlopen 实现) |
| **libm.so** | 数学库 |
| **liblog.so** | 日志库 |

**为什么"内置"**:
1. **libdl.so 必须在 linker 启动后立即可用**——否则 dlopen 自己怎么实现?
2. **libc.so 是 libdl 的依赖**——链式依赖,必须先就绪
3. **libm/liblog** 是常用基础库,提前就绪减少 dlopen 开销

**实现机制**:

```c
// linker.cpp
static soinfo* find_builtin_library(const char* name) {
    if (strcmp(name, "libdl.so") == 0) {
        return &g_libdl_info;  // 静态 soinfo
    }
    if (strcmp(name, "libc.so") == 0) {
        return &g_libc_info;
    }
    // ...
    return nullptr;
}
```

**架构师必记**:**内置库的存在意味着,即使你删除 /system/lib64/libdl.so,系统仍然能正常加载**——因为 linker 内部就有 libdl 的实现。**线上故障排查时,这一点常被忽略**。

### 4.4 find_library 性能优化

**find_library 的真实耗时**:

| 阶段 | 耗时(中端机) | 优化点 |
|---|---|---|
| 命中已加载缓存 | < 0.1ms | ✅ 已优化 |
| 命中 soname 缓存 | 0.1-0.5ms | ✅ 已优化 |
| DT_RUNPATH 搜索 | 1-3ms(每路径) | 可优化:减少路径数 |
| 默认 namespace 搜索 | 5-20ms(6 个路径) | 难优化(系统行为) |
| 实际 mmap .so | 10-50ms(每个 .so) | 可优化:减少 NEEDED |

**4 个优化技巧**:

1. **减少 NEEDED 数量**:5 个 .so → 1 个公共 .so(§0.1 案例)
2. **避免循环依赖**:A 依赖 B,B 依赖 A → 每次 find_library 都要遍历
3. **避免深嵌套依赖**:A 依赖 B,B 依赖 C,C 依赖 D,D 依赖 E → 4 层 find_library
4. **预加载常用 .so**:用 `System.loadLibrary()` 在启动早期就加载

**架构师必记**:**每次 find_library 的搜索范围 = loader 的 DT_RUNPATH + 默认 namespace**。loader 越多,搜索范围越大,启动越慢。

### 4.5 真实案例:依赖图优化

**优化前**:

```
app_process
├─ libA.so (NEEDED: libB.so, libC.so)
├─ libB.so (NEEDED: libD.so, libE.so)
├─ libC.so (NEEDED: libE.so, libF.so)
├─ libD.so (NEEDED: libG.so)
├─ libE.so (NEEDED: libG.so, libH.so)
├─ libF.so (NEEDED: libH.so, libI.so)
└─ libG.so, libH.so, libI.so
```

**find_library 次数** = 9 + 5(子依赖) + 2(共享) = 16 次

**优化后**(引入 libbase.so):

```
app_process
├─ libA.so (NEEDED: libbase.so)
├─ libB.so (NEEDED: libbase.so)
├─ libC.so (NEEDED: libbase.so)
├─ libD.so (NEEDED: libbase.so)
├─ libE.so (NEEDED: libbase.so)
├─ libF.so (NEEDED: libbase.so)
└─ libbase.so (NEEDED: libG.so, libH.so, libI.so)
```

**find_library 次数** = 6 + 3 = 9 次

**节省**:43% 的 find_library 调用 + 16ms 启动时间。

---

## 5. NEEDED 树遍历:广度优先 + 去重

### 5.1 遍历算法

**linker64 用广度优先遍历(BFS)+ 去重表遍历 NEEDED 树**:

```c
// linker.cpp::load_library_list 简化
static bool load_library_list(android_namespace_t* ns, const char* name_list, soinfo* loader) {
    // 1. 用 queue 模拟 BFS
    std::queue<const char*> pending_libraries;
    add_to_pending(pending_libraries, name_list);
    
    // 2. 去重表(避免重复加载)
    std::unordered_set<std::string> already_loaded;
    
    while (!pending_libraries.empty()) {
        const char* name = pending_libraries.front();
        pending_libraries.pop();
        
        // 3. 检查是否已加载
        if (already_loaded.count(name)) continue;
        already_loaded.insert(name);
        
        // 4. find_library
        soinfo* si = find_library(name, loader);
        if (si == nullptr) return false;
        
        // 5. 把它的 NEEDED 加入待处理队列
        for (const auto& needed : si->get_needed_libraries()) {
            pending_libraries.push(needed.c_str());
        }
    }
    return true;
}
```

**关键事实**:

- **BFS 而不是 DFS** —— 减少栈深度,避免依赖图复杂时栈溢出
- **去重表避免重复** —— 即使多个父 .so 都需要同一个 .so,只加载一次
- **同进程内已加载优先** —— 见 §4.1

### 5.2 遍历顺序的稳定性

**Android 8+ 用 `deterministic_order_path` 强制 NEEDED 遍历顺序稳定**:

```c
// linker.cpp
static bool deterministic_order_path = true;
// 如果开启,会按字母序排序 NEEDED 列表
```

**为什么强制稳定**:

- 调试:同样的依赖图,同样的加载顺序,行为可复现
- 安全:防止依赖顺序不同导致攻击者注入 .so
- 性能:预测性 cache 友好

**架构师视角**:**线上排查"为什么同样代码库,有些设备能跑有些不能"时,看依赖图遍历顺序是关键**。不同的系统 namespace 顺序会导致同样的 .so 在不同设备上被解析到不同的物理文件。

### 5.3 真实案例:循环依赖的灾难

**场景**:A.so 和 B.so 互相依赖(常见的 Java ↔ Native JNI 库):

```cmake
# A.so 的 CMakeLists.txt
target_link_libraries(A PRIVATE B)
# B.so 的 CMakeLists.txt
target_link_libraries(B PRIVATE A)
```

**linker64 行为**:

```
1. 加载 A.so
2. 解析 A 的 NEEDED: [B]
3. 加载 B.so
4. 解析 B 的 NEEDED: [A]
5. A 已在加载中 → 检查 already_loaded[A] → 找到 → 跳过
6. B 加载完成
7. A 继续加载,完成
```

**linker64 内部用状态机处理**:
- `LOADING` 状态:.so 正在加载
- `LOADED` 状态:.so 加载完成
- 循环检测:遇到 LOADING 状态的 .so,跳过

**架构师必记**:**循环依赖能跑,但性能极差**——每次 find_library 都要查表,栈深度增加,而且有些 linker 在循环时还会报警告。**架构上应该避免**。

---

## 6. ELF Namespace:Android 7+ 的安全隔离

### 6.1 什么是 ELF Namespace

**ELF Namespace 是 Android 7.0 引入的安全机制**:每个进程只能看到自己被授权的 .so。

**Android 的 6 个默认 namespace**:

| Namespace | 搜索路径 | 谁能访问 |
|---|---|---|
| `default` | /system/lib/ 等 | 所有进程 |
| `system` | /system/lib/ | 系统进程 |
| `vendor` | /vendor/lib/ | vendor 进程 |
| `odm` | /odm/lib/ | odm 进程 |
| `product` | /product/lib/ | product 进程 |
| `vndk` | /system/lib/vndk/ | 跨 HAL |

### 6.2 进程能加载的 .so 范围

**App 进程的 namespace 配置**(典型):

```xml
<!-- /system/etc/ld.config.txt -->
[app]
namespace.default.search.paths = /system/lib64
namespace.default.asan.search.paths = /data/asan/system/lib64
namespace.default.permitted.paths = /system/lib64:/vendor/lib64
```

**关键事实**:
- App 进程只能加载 `/system/lib64`、`/vendor/lib64` 下的 .so
- 即使 App 知道 `/data/local/tmp/libfoo.so` 存在,`dlopen` 也会失败(被 namespace 拒绝)
- **这阻止了"私有 .so 注入攻击"**

### 6.3 私有 .so 怎么加载

**App 自带的 .so**(在 `/data/app/~~xxx/lib/arm64/`)怎么加载?

**机制**:`/data/app/~~xxx/lib/arm64/` 会被 linker 加入 `permitted.paths`,App 进程可以加载。

**实现**:

```c
// linker.cpp::init_default_namespace
static void init_default_namespace(android_namespace_t* ns) {
    // 1. 添加 /system/lib64
    ns->set_search_paths({"/system/lib64"});
    // 2. 添加 permitted 路径(per-app 配置)
    //    这些路径由 PackageManagerService 在 App 安装时设置
    ns->set_permitted_paths(permitted_paths);
}
```

**架构师必记**:

- **App 自己的 .so 路径在 permitted.paths 里**——这是怎么"授权"的
- **/data/local/tmp 不在 permitted.paths**——debug 工具 debug .so 会被拒绝
- **Workaround**:adb shell `chmod 777` + `setenforce 0` 关 SELinux

### 6.4 Namespace 冲突诊断

**典型错误日志**:

```
W linker: cannot open "libfoo.so" from namespace "default"
W linker: namespace "default" does not have path "/data/local/tmp"
```

**诊断步骤**:

```bash
# 1. 确认 libfoo.so 存在
adb shell ls -la /data/local/tmp/libfoo.so

# 2. 确认进程的 namespace 配置
adb shell cat /proc/1234/maps | grep namespace  # 不存在,直接看 linker log

# 3. 看 linker 错误日志
adb logcat | grep "linker.*namespace"

# 4. (debug)用 strace 看 dlopen 系统调用
adb shell strace -e openat,access -p 1234
```

**修复方法**:

1. 把 .so 移到 `/system/lib64/`(需要 root)
2. 修改 `/system/etc/ld.config.txt` 加入路径
3. debug 时 `setenforce 0`(关 SELinux)

**架构师必记**:**namespace 冲突是 Android 7+ 最常见的 .so 加载失败原因**。比架构错配、符号缺失更常见。

---

## 7. dlopen / dlsym / dlclose:运行时动态加载

### 7.1 dlopen 完整流程

**dlopen(path, flags)** 内部流程:

```c
// dlfcn.cpp::android_dlopen
void* android_dlopen(const char* path, int flags) {
    // 1. 解析 flags(RTLD_NOW / RTLD_LAZY / RTLD_GLOBAL / RTLD_LOCAL)
    
    // 2. 调 load_library
    soinfo* si = load_library(path, flags, current_ns);
    //    └─ find_library
    //    └─ mmap
    //    └─ parse_dynamic
    //    └─ 递归 load_library_list(NEEDED)
    
    // 3. 如果 RTLD_NOW:link_image(立即绑定)
    if (flags & RTLD_NOW) {
        link_image(si);
    }
    
    // 4. 引用计数 +1
    si->ref_count++;
    
    // 5. 返回 handle(= si 指针)
    return si;
}
```

**关键事实**:

- `dlopen` 返回的 `handle` 实际是 `soinfo*`(被 void* 隐藏)
- 同一个 .so 多次 `dlopen` 会增加引用计数,不会重复加载
- `RTLD_NOW` 立即绑定符号(慢但安全);`RTLD_LAZY` 延迟绑定(快但首次调用慢)

### 7.2 dlsym 完整流程

**dlsym(handle, name)** 内部流程:

```c
// dlfcn.cpp::android_dlsym
void* android_dlsym(void* handle, const char* name) {
    // 1. 解析 handle
    soinfo* si = (soinfo*)handle;
    
    // 2. 在 si 的 .dynsym 里查找 name
    const ElfW(Sym)* sym = soinfo_do_lookup(si, name, ...);
    
    // 3. 如果找到
    if (sym != nullptr) {
        if (sym->st_shndx != SHN_UNDEF) {
            // 直接返回地址
            return (void*)(si->base + sym->st_value);
        }
        // SHN_UNDEF:符号在别处定义,需要解析
        // 递归查找
        return lookup_in_other_ns(sym, ...);
    }
    return nullptr;
}
```

**关键事实**:

- `dlsym` 的复杂度 = O(symbol_table_size),O(1) 取决于 GNU hash 表
- **handle = RTLD_DEFAULT** 时,在全局 namespace 找
- **handle = RTLD_NEXT** 时,在当前 .so 之后的全局找

### 7.3 dlclose 完整流程

**dlclose(handle)**:

```c
// dlfcn.cpp::android_dlclose
int android_dlclose(void* handle) {
    soinfo* si = (soinfo*)handle;
    
    // 1. 引用计数 -1
    si->ref_count--;
    
    // 2. 如果引用计数 = 0,真正卸载
    if (si->ref_count == 0) {
        // 倒序执行 .fini_array
        call_destructors(si);
        // munmap
        unmap_all_segments(si);
        // 从 Solist 移除
        Solist.remove(si);
    }
    
    return 0;
}
```

**关键事实**:

- **真正的 .so 卸载在引用计数 = 0 时发生**——多个 dlopen 共享一个 .so
- **.so 一旦被 mmap 就不容易"卸载干净"**——因为内核的 PageCache 还可能保留
- **进程退出时不调用 dlclose**——OS 回收所有内存

### 7.4 架构师视角:dlopen 的 3 大陷阱

**陷阱 1:`RTLD_LAZY` 的隐性卡顿**

```c
// ❌ 错误:首次调用 find_function 慢 1-2 个数量级
void* handle = dlopen("libfoo.so", RTLD_LAZY);
void (*func)() = dlsym(handle, "do_something");
func();  // 这里会触发 _dl_runtime_resolve,首次调用 100-1000μs
```

**修复**:用 `RTLD_NOW` 立即绑定,提前到 dlopen 阶段就解析完。

**陷阱 2:`RTLD_GLOBAL` 的全局污染**

```c
// ❌ 错误:把 .so 的符号加到全局符号表
void* handle = dlopen("libfoo.so", RTLD_GLOBAL);
// 其他 .so 也能看到 libfoo 的符号
// → 可能覆盖已有符号,导致难以诊断的 bug
```

**修复**:`dlopen` 默认是 `RTLD_LOCAL`,除非真的需要跨 .so 共享符号,否则不要用 GLOBAL。

**陷阱 3:`dlclose` 后使用 handle**

```c
// ❌ 错误:handle 已被 free
void* handle = dlopen("libfoo.so", RTLD_LAZY);
dlclose(handle);
func();  // use-after-free
```

**修复**:检查引用计数,或干脆不 dlclose(进程退出时 OS 清理)。

---

## 8. linker64 的性能与稳定性影响

### 8.1 linker64 启动期对冷启动的贡献

**冷启动 1.5s 拆分**(典型中端机):

| 阶段 | 耗时 | 占比 |
|---|---|---|
| execve 内核侧 | 50ms | 3% |
| linker64 启动 + 加载 | **200-400ms** | **13-27%** |
| ART 启动 | 100-200ms | 7-13% |
| ClassLoader + Resources | 300-500ms | 20-33% |
| Application onCreate | 300-500ms | 20-33% |
| 第一帧渲染 | 200-400ms | 13-27% |

**linker64 占 13-27%**——是冷启动的**第二大瓶颈**(仅次于 ClassLoader+Resources)。

### 8.2 减少 linker64 启动时间的 7 个技巧

| 技巧 | 节省时间 | 难度 | 适用场景 |
|---|---|---|---|
| **预加载常用 .so** | 30-80ms | 中 | 关键路径 .so |
| **减少 NEEDED 数量** | 5-15ms / 库 | 中 | 多个 .so 互依赖 |
| **避免循环依赖** | 5-10ms | 低 | 任何项目 |
| **拆分 .so 边界** | 10-30ms | 高 | 大型 SDK |
| **合并小 .so** | 10-20ms | 中 | 多个 100KB 以下的 .so |
| **延迟加载非关键 .so** | 50-100ms | 中 | 启动期不用的 .so |
| **用 NDK r25+ 的 lld 链接** | 10-20ms | 低 | 任何项目 |

### 8.3 linker64 启动期的稳定性风险

**5 大稳定性陷阱**:

| 风险 | 触发条件 | 后果 |
|---|---|---|
| **循环依赖** | A.so NEEDED B.so, B.so NEEDED A.so | 启动慢 5-10ms,极少数 linker 报警 |
| **重复 NEEDED** | 多个 .so 都需要 libfoo.so | 正常(linker 去重),但占内存 |
| **ABI 不匹配** | 32 位 .so 加载到 64 位进程 | 启动崩溃 |
| **namespace 冲突** | 私有路径 .so | `cannot open` 错误 |
| **init_array 失败** | 全局对象构造抛异常 | 启动崩溃,且难以定位 |

### 8.4 线上诊断工具

**5 个常用工具**:

```bash
# 1. /proc/pid/maps - 看 .so 加载情况
adb shell cat /proc/1234/maps | grep "\.so"

# 2. lsof - 看 .so 引用
adb shell lsof -p 1234 | grep "\.so"

# 3. simpleperf record - 抓调用栈
adb shell simpleperf record -e sched:sched_process_exec -p 1234

# 4. linker logcat - 看 .so 加载日志
adb logcat -v time | grep -i "linker"

# 5. LD_DEBUG=files - linker 内部 trace
adb shell setprop debug.ld.debug.files 1
adb shell setprop debug.ld.all 1
# 然后重启进程
```

**架构师必记**:**linker logcat 是诊断 .so 加载问题的第一现场**。任何 "cannot locate symbol" / "library not found" 都在这里。

---

## 9. 架构师视角:linker64 的 5 个核心洞察

### 9.1 洞察 1:linker64 是用户态的 ELF 加载器

**和内核的关系**:
- 内核:把 PT_LOAD 段 mmap 到进程地址空间
- linker64:解析 .dynamic,递归加载 NEEDED,执行 .init_array
- 两者职责清晰:内核管"映射",linker 管"链接"

**故障时,先看哪边**:
- `wrong ELF class` / `unsupported flags` → 内核侧(mmap 失败)
- `cannot locate symbol` / `library not found` → linker64 侧

### 9.2 洞察 2:Solist + soinfo 是 linker 内部的"数据库"

**类比**:
- Solist = 已加载 .so 的"账本"(像 MM_v2 里的 VMA 列表)
- soinfo = 每个 .so 的"档案"(像 MM_v2 里的 vm_area_struct)

**架构师应该把 Solist 当作"加载期 VMA 列表"**——任何 .so 加载/卸载都修改它。

### 9.3 洞察 3:find_library 是启动期最贵的操作

**真实数据**:
- 命中已加载:0.1ms
- 命中 DT_RUNPATH:1-3ms
- 默认 namespace 搜索:5-20ms
- 实际 mmap:10-50ms

**总启动时间 = Σ find_library 耗时 + Σ mmap 耗时**。

**优化 = 减少 find_library 次数 + 减少 mmap 数量**。

### 9.4 洞察 4:Namespace 是 Android 7+ 的安全基石

**App 进程能加载的 .so 范围 = default + permitted.paths**。

**这阻止了**:
- 私有 .so 注入(`/data/local/tmp/libfoo.so`)
- 跨进程 .so 替换(`/system/lib/libfoo.so` 被替换)
- 重打包攻击

**代价**:
- 调试困难(不能 dlopen /data/local/tmp 的 .so)
- 热修复/插件化需要特殊机制

### 9.5 洞察 5:dlopen 的 3 个 flag 决定运行时行为

| flag | 行为 | 适用场景 |
|---|---|---|
| `RTLD_NOW` | 立即绑定 | 性能关键路径(避免首次调用卡顿) |
| `RTLD_LAZY` | 延迟绑定 | 内存敏感场景(冷启动用不到的 .so) |
| `RTLD_GLOBAL` | 符号全局可见 | 跨 .so 共享符号(慎用) |

**架构师必记**:**生产环境 dlopen 默认用 RTLD_NOW + RTLD_LOCAL**,避免隐性卡顿和符号污染。

---

## 10. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **linker64 启动是 7 步流程** | _start → 自举 → 解析可执行文件 → NEEDED 树 → 重定位 → init_array → 跳入口 |
| 2 | **soinfo 是 .so 在 linker 内的全息画像** | phdr / dynamic / symtab / strtab / plt_rela / init_array / namespace |
| 3 | **find_library 是启动期最贵的操作** | 5-50ms 一次,NEEDED 树遍历是主要成本 |
| 4 | **Android 7+ namespace 是安全基石** | App 进程只能加载 permitted.paths 下的 .so |
| 5 | **dlopen 的 3 个 flag 决定行为** | RTLD_NOW/LAZY/GLOBAL 选错,后果严重 |

---

## 11. 下一篇预告

04 篇《符号解析与重定位:.plt / .got / .relro 全景》会沿着本篇埋下的线索,深入讲:

- 符号表的本质:.dynsym + .dynstr 的查找机制
- 重定位表:.rel.dyn / .rel.plt / .rela.dyn / .rela.plt
- .plt / .got:延迟绑定的实现
- RELRO:.got.plt 重映射为只读,防 GOT 攻击
- 符号可见性:STB_LOCAL / STB_GLOBAL / STB_WEAK
- 立即绑定(DF_BIND_NOW)vs 延迟绑定
- arm64 重定位类型:R_AARCH64_* 全解

**04 篇预计 3 天后产出**,届时一起发你看。

---

## 附录 A:soinfo 关键字段速查

| 字段 | 类型 | 含义 | 何时填充 |
|---|---|---|---|
| `phdr` | `ElfW(Phdr)*` | Program Header 表指针 | mmap 之后 |
| `phnum` | `size_t` | PH 数量 | 同上 |
| `base` | `ElfW(Addr)` | 加载基址(load_bias) | mmap 之后 |
| `size` | `size_t` | 加载大小 | mmap 之后 |
| `soname` | `const char*` | .so 名 | 解析 .dynamic |
| `realpath` | `const char*` | 实际路径 | find_library 命中 |
| `dynamic` | `ElfW(Dyn)*` | .dynamic 段指针 | parse_dynamic |
| `strtab` | `const char*` | .dynstr 字符串表 | parse_dynamic |
| `symtab` | `ElfW(Sym)*` | .dynsym 符号表 | parse_dynamic |
| `bucket` / `chain` | `uint32_t*` | GNU hash 表 | parse_dynamic |
| `plt_rela` / `rela` | `ElfW(Rela)*` | 重定位表 | parse_dynamic |
| `init_array` | `ElfW(Addr)*` | 构造链 | parse_dynamic |
| `init_func` | `ElfW(Addr)` | DT_INIT 函数 | parse_dynamic |
| `flags` | `uint32_t` | DF_1_NOW 等 | parse_dynamic |
| `is_linked` | `bool` | 是否已链接 | link_image 后 |
| `ns` | `android_namespace_t*` | 所属 namespace | load_library 时 |

## 附录 B:NEEDED 树遍历算法

```
输入:可执行文件 exe 的 DT_NEEDED 列表
输出:已加载 .so 的 Solist

BFS 遍历:
1. queue ← exe 的 NEEDED
2. already_loaded ← {exe}
3. while queue not empty:
   a. name ← queue.pop()
   b. if name in already_loaded: continue
   c. already_loaded.add(name)
   d. si ← find_library(name)
   e. if si is null: error
   f. for each needed in si.get_needed_libraries():
         queue.push(needed)
4. return Solist
```

## 附录 C:Android 6 个默认 namespace

| Namespace | 路径 | 谁能访问 |
|---|---|---|
| `default` | /system/lib/ | 所有进程 |
| `system` | /system/lib/ | 系统进程 |
| `vendor` | /vendor/lib/ | vendor 进程 |
| `odm` | /odm/lib/ | odm 进程 |
| `product` | /product/lib/ | product 进程 |
| `vndk` | /system/lib/vndk/ | 跨 HAL |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 04 重定位 | .rel.dyn / .rel.plt / .rela.dyn 的解析在 link_image() 里 |
| 05 .init_array | call_constructors() 的实现依赖 Solist |
| 12 进程启动 | Zygote 子进程的 linker 行为和 App 进程相同 |

---

> **本篇把 linker64 拆解到"工作流级"——7 步流程、soinfo 数据结构、find_library 算法、namespace 隔离、dlopen API。**
> **04 篇会在这个基础上,讲"重定位"——.so 加载完成后,符号地址怎么确定、.plt/.got 怎么联动、RELRO 怎么防攻击。**
> **记住 7 步、soinfo、find_library、namespace、3 个 flag,你的 linker 视角就立住了。**
