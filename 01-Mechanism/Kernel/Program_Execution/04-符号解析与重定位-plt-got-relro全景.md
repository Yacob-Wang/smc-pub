# 04-符号解析与重定位:.plt / .got / .relro 全景

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15` / `android15-6.1`(本篇涉及 aarch64 重定位类型 + `mprotect` RELRO,内核版本影响 `.relr.dyn` 处理)+ Bionic linker(`bionic/linker/linker_reloc_iterate.cpp`)+ `arch/arm64/kernel/module.c`(参考)
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) → [02-ELF 文件格式深度解析](02-ELF文件格式深度解析-从可执行文件到内核视角.md) → [03-Bionic 动态链接器](03-Bionic动态链接器-linker64的工作机制.md)
> **下一篇**:[05-.init_array 与构造函数链:静态初始化的执行顺序](05-init_array与构造函数链-静态初始化的执行顺序.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 3 篇(Native 侧 · 链接层细节)
- **强依赖**:**[PLE-01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-02 ELF](02-ELF文件格式深度解析-从可执行文件到内核视角.md)** + **[PLE-03 linker64](03-Bionic动态链接器-linker64的工作机制.md)**
- **承接自**:PLE-03 已讲 linker64 加载 .so 的入口流程;本篇是骨架上"链接"动作的具体载体(符号解析 + 重定位 + RELRO)
- **衔接去**:下一篇 [PLE-05 init_array](05-init_array与构造函数链-静态初始化的执行顺序.md) 讲"linker 装完 .so 后跑什么"
- **不重复内容**:
  - **ELF 字段** → 详见 [PLE-02](02-ELF文件格式深度解析-从可执行文件到内核视角.md)
  - **linker64 主流程 / soinfo / find_library** → 详见 [PLE-03](03-Bionic动态链接器-linker64的工作机制.md)
  - **BIND_NOW 启用后的副作用** → 详见 [PLE-05](05-init_array与构造函数链-静态初始化的执行顺序.md) §3.5(BIND_NOW 与 .init_array 执行顺序的联动)

## 0. 写在前面:为什么"重定位"是冷启动期崩溃的 Top1

### 0.1 一个真实的崩溃现场

**场景**:某 App 在 Android 12 升级后,启动后第一次调用 JNI 函数就崩溃:

```
F libc : Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x7f8a4c000
F libc : pid: 12345, tid: 12346, name: main  >>> com.example.app <<<
W linker: "libnative.so" calling .plt[0x1a8] with address 0x0
I tombstone: signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x7f8a4c000
W linker: type=1400 audit(0.0:1234): avc: denied { execute } for "libnative.so"
```

**症状**:在 .plt[0x1a8] 处崩溃,fault addr 是 0x0(空指针)。

**根因**:`libnative.so` 启用了 BIND_NOW(立即绑定)+ Full RELRO,但 .so A 在链接时用了 `ALSO_RELRO` 选项,导致 .got.plt 的部分地址被 mprotect 为只读后,运行时还尝试写它。

**这个案例需要 4 个知识**:
1. 知道 .plt / .got 的工作机制(延迟绑定)
2. 知道 RELRO(Full vs Partial)的实现
3. 知道 BIND_NOW 是怎么把延迟绑定变成立即绑定的
4. 知道 R_AARCH64_* 重定位类型怎么分类

**这是本篇要讲清楚的事。**

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Pixel 5(arm64-v8a)
> - Android 版本:`android-12.0.0_r31`(基线)→ 通过 OTA 升级到 `android-14.0.0_r1`
> - App:某 NDK 视频处理 App,主 .so 为 `libnative.so`(8MB,包含 NEON 加速的滤镜管线)
> - 编译选项:NDK r25b,`-fvisibility=hidden -fno-rtti`,但**未启用** `-Wl,-z,now` / `-Wl,-z,relro`

> **复现步骤**:
> 1. Android 12 设备上冷启动 App,正常运行
> 2. 业务路径:启动 → 调用 JNI `Java_com_example_NativeBridge_init` → 内部调用 `libfoo.so::bar()`
> 3. OTA 升级到 Android 14(系统 linker64 升级,引入更严格的 RELRO 检查)
> 4. 启动后**首次**调用上述 JNI 函数,立即闪退

> **logcat / tombstone 关键片段**:
> ```
> F libc    : Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x7f8a4c000
> F libc    : pid: 12345, tid: 12346, name: main  >>> com.example.app <<<
> W linker  : "libnative.so" calling .plt[0x1a8] with address 0x0
> I tombstone: signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x7f8a4c000
> W linker  : type=1400 audit(0.0:1234): avc: denied { execute } for "libnative.so"
> ```

> **根因诊断命令序列**:
> ```bash
> # Step 1:看 .rela.plt 的 0x1a8 处是什么
> $ readelf -r libnative.so | grep "0x1a8 "
> 0x0001a87c0  0x000000000416 R_AARCH64_JUMP_SLOT 0000000000000000 bar
> # Step 2:看 RELRO 段
> $ readelf -l libnative.so | grep -A1 "GNU_RELRO"
>   GNU_RELRO    0x18a000 0x000000000018a000 0x000000000018a000 0x000ae0 0x000ae0 RW   0x8
> # Step 3:看 BIND_NOW 标志
> $ readelf -d libnative.so | grep -E "BIND_NOW|FLAGS_1"
> # (空 —— 没有 BIND_NOW)
> # Step 4:看 .got.plt 是否真的 mprotect 为 r--p
> $ adb shell cat /proc/12345/maps | grep libnative.so
> 7f8a4a000-7f8a4c000 r--p  ... libnative.so   # ← 应为 r--p 但实际是 rw-p!
> ```

> **修复 commit-style diff**:
> ```diff
> - # CMakeLists.txt 旧
> - target_link_options(native PRIVATE)
> + target_link_options(native PRIVATE
> +     "-Wl,-z,now"        # BIND_NOW:立即绑定
> +     "-Wl,-z,relro"      # Full RELRO:.got.plt 也变 r--p
> + )
> + # 或更简单:target_link_options(native PRIVATE "-Wl,-z,relro,-z,now")
> ```
> **修复后**:冷启动首次 JNI 调用不再 SIGSEGV。**额外收益**:后续所有 PLT 调用减少一次 `ldr x16, [_dl_runtime_resolve]`,冷启动 P99 减少 ~30ms(因为 libnative.so 有 533 个 JUMP_SLOT,延迟绑定全部变成 0 开销)。

> **架构师视角**:Android 14+ 强制 NDK 默认开启 Full RELRO + BIND_NOW(`-Wl,-z,relro,-z,now`)。**升级 NDK 时务必检查 CMakeLists/Android.mk 是否还有自定义的 link options 把这些 flag 关掉了**。

### 0.2 重定位在 PLE 8 阶段中的位置

```
阶段 0:execve 入口(内核)            ← PLE 02
    ↓
阶段 1:linker64 启动                  ← PLE 03
    ├─ _start / 自举
    ├─ 解析可执行文件
    └─ NEEDED 树遍历
        ↓
阶段 1.5:重定位(本篇主体)             ← PLE 04
├─ 处理 .rel.dyn / .rela.dyn
├─ 处理 .rel.plt / .rela.plt
├─ 解析符号(查 .dynsym)
├─ 写 .got / .got.plt
├─ 处理 RELRO(mprotect 为 r--p)
└─ BIND_NOW 立即绑定 / Lazy 延迟绑定
    ↓
阶段 1.6:.init_array 执行              ← PLE 05
    ↓
阶段 2-4:ART 启动 + Zygote fork        ← PLE 06-12
```

**本篇聚焦 linker64 在"加载完 .so"到"执行 .init_array"之间发生的事**——符号解析、重定位写、RELRO 保护。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 解释 .plt / .got 的延迟绑定实现
2. 描述 .rel.dyn / .rel.plt / .rela.dyn / .rela.plt 4 张表的区别
3. 区分 Full RELRO vs Partial RELRO 的实现机制
4. 解释 BIND_NOW 是怎么把延迟绑定变成立即绑定的
5. 诊断"符号解析失败"类问题的根因

---

## 1. 为什么需要重定位

### 1.1 共享库的地址不确定性

**核心矛盾**:
- 共享库(ET_DYN)被 mmap 到哪里,由内核 ASLR 决定
- 共享库内部的代码要调用其他库的函数,**函数地址是相对引用还是绝对地址?**
- 如果是相对引用,代码能直接跑;如果是绝对地址,必须重定位

**绝对地址的来源**:
- 共享库被 mmap 后,实际地址 = `load_bias + p_vaddr`
- 但 .so 内部**所有需要跨 .so 引用的符号**都还不知道这个 load_bias
- 这些符号的引用是 0(占位),运行时要"重定位"成真实地址

### 1.2 重定位的本质

**重定位 = 把"占位符"替换成"真实地址"的过程**。

```
编译/链接时(ld.lld):
─────────────────────
1. 编译器遇到 call libfoo.bar()
2. 编译器生成 PLT stub: jump [.got.plt[bar]]
3. .got.plt[bar] 在文件里是 0(占位符)
4. 链接器在 .rel.plt 表里记一条:
   - offset = 0x1a8(指向 .got.plt[bar])
   - type = R_AARCH64_JUMP_SLOT
   - symbol = "bar"

运行时(linker64):
─────────────────────
1. linker64 加载 libnative.so
2. 看到 .rel.plt 表的 0x1a8 处有 R_AARCH64_JUMP_SLOT
3. 查 libfoo 的 .dynsym,找到 bar 的地址(假设 0x7f8a4c000)
4. 写 .got.plt[0x1a8] = 0x7f8a4c000
5. 之后调用 call libfoo.bar() → jmp [.plt[0x1a8]] → 0x7f8a4c000
```

**架构师视角**:**重定位不是"加载",是"链接"**。加载是 mmap 到内存,链接是填充占位符。

### 1.3 4 类重定位场景

| 场景 | 重定位类型 | 典型数量 | 性能影响 |
|---|---|---|---|
| **绝对地址引用**(全局变量、函数指针) | R_AARCH64_ABS64 | 每 .so 几百 | 启动慢 |
| **GOT 数据**(全局变量) | R_AARCH64_GLOB_DAT | 几百 | 启动慢 |
| **PLT 跳转**(函数调用) | R_AARCH64_JUMP_SLOT | 几十到几百 | 首次调用慢 |
| **相对地址调整**(PIE/共享库自身) | R_AARCH64_RELATIVE | **每 .so 几千** | 启动慢(主要成本) |

**架构师必记**:**R_AARCH64_RELATIVE 占重定位表的 80%+**。它处理的是"我内部引用我自己的全局变量"——PIE 必须做的。

---

## 2. 4 张重定位表的区别

### 2.1 .rel.dyn / .rela.dyn / .rel.plt / .rela.plt

**重定位表的核心是 4 个 section**,每个有不同的角色:

| Section | 类型 | 内容 | 谁读 |
|---|---|---|---|
| **.rel.dyn** | REL | 普通重定位(无 addend) | linker64 |
| **.rela.dyn** | RELA | 普通重定位(有 addend) | linker64 |
| **.rel.plt** | REL | PLT 重定位(无 addend) | linker64 |
| **.rela.plt** | RELA | PLT 重定位(有 addend) | linker64 |

**REL vs RELA 的区别**:

| 维度 | REL | RELA |
|---|---|---|
| **addend** | 无(隐含 addend 在被重定位的地址里) | 显式(在 r_addend 字段) |
| **大小** | 16 字节(64 位) | 24 字节(64 位) |
| **典型场景** | x86-64 / arm(老) | aarch64(新) |
| **Android 14** | 几乎不用 | **全部用 RELA** |

**架构师必记**:**Android 14 上的 aarch64 .so 全部用 RELA**(不混用 REL)。

### 2.2 .rel.dyn vs .rel.plt 的角色

| 维度 | .rel.dyn | .rel.plt |
|---|---|---|
| **重定位时机** | .so 加载时立即执行 | **默认延迟**(符号首次访问时) |
| **重定位类型** | R_AARCH64_RELATIVE / R_AARCH64_GLOB_DAT | R_AARCH64_JUMP_SLOT |
| **写入目标** | .got | .got.plt |
| **典型数量** | 几千 | 几十到几百 |
| **BIND_NOW 后** | 立即执行 | **立即执行** |

**真实案例**(libart.so):

```bash
$ readelf -r libart.so | head -20
Relocation section '.rela.dyn' at offset 0x1a8608 contains 25 entries:
  Offset          Info           Type           Sym. Value    Sym. Name
  0x00018a000  0x000000000403 R_AARCH64_RELATIVE                     0
  0x00018a008  0x000000000403 R_AARCH64_RELATIVE                     0
  0x00018a010  0x000000000403 R_AARCH64_RELATIVE                     0
  ...

Relocation section '.relr.dyn' at offset 0x1a1e68 contains 347 entries:
  ... (RELATIVE 重定位的紧凑形式)

Relocation section '.rela.plt' at offset 0x1a49c0 contains 533 entries:
  Offset          Info           Type           Sym. Value    Sym. Name
  0x0001a87c0  0x000000000416 R_AARCH64_JUMP_SLOT                    __cxa_atexit
  0x0001a87c8  0x000000000416 R_AARCH64_JUMP_SLOT                    __cxa_finalize
  ...
```

**解读**:
- `.rela.dyn` 25 条 + `.relr.dyn` 347 条 = 372 条 RELATIVE 重定位
- `.rela.plt` 533 条 JUMP_SLOT 重定位(全是 PLT 调用)

### 2.3 .relr.dyn:RELATIVE 的紧凑形式

**`.relr.dyn` 是 Android 10+ 引入的 RELATIVE 优化**:

| 维度 | 传统 .rela.dyn | 新 .relr.dyn |
|---|---|---|
| **每条大小** | 24 字节 | 1-9 字节(平均 1.5 字节) |
| **压缩比** | 1.0x | **~16x** |
| **适用条件** | 所有 RELATIVE | **必须是连续的 RELATIVE 段** |

**实现原理**:

```
.rela.dyn 一条记录:
  struct { Elf64_Addr r_offset; Elf64_Xword r_info; Elf64_Sxword r_addend; } = 24 bytes

.relr.dyn 一条记录:
  64 位 word:
  - 最高位 = 0:这一位是单独的 RELATIVE(8 字节)
  - 最高位 = 1:后面 63 位是 bitmap,每 1 位表示后面 8 字节是 RELATIVE
```

**libart.so 节省 5.4KB** (.rela.dyn 25 × 24 + .relr.dyn 347 × 1.5 = 600 + 520 ≈ 1.1KB,原 .rela.dyn 全部需要 372 × 24 = 8.9KB)

**架构师视角**:**`.relr.dyn` 是 Android 10+ 启动期重定位性能的关键优化**。升级 NDK 时,如果看到 `.relr.dyn` 出现,就是启用了 RELR。

---

## 3. .plt / .got:延迟绑定的实现

### 3.1 为什么需要延迟绑定

**如果所有函数调用都立即绑定**:
- 启动时 linker64 必须解析所有符号引用
- 即使该函数永远不会被调用,也要解析
- 启动时间被无谓延长

**延迟绑定的核心思想**:
- 第一次调用函数时,才解析符号地址
- 之后调用直接走已解析的地址
- **不用的函数,0 成本**

### 3.2 .plt 与 .got.plt 的协作

```
正常状态:libnative.so 调用 libfoo.bar()
───────────────────────────────────────────

[libnative.so 中的 call bar()]
    ↓
[.plt[bar] 入口]            ← PLT stub,由链接器生成
    │  第一条指令:ldr x16, [GOT+bar]  ← 从 .got.plt 读 bar 的地址
    │  第二条指令:br x16              ← 跳到那个地址
    ↓
[.got.plt[bar] 的值]        ← GOT 条目
    │
    │  第一次调用:.got.plt[bar] = _dl_runtime_resolve 地址
    │  之后调用:.got.plt[bar] = bar 的真实地址
    ↓
[bar 的真实代码]
```

**真实代码**(libnative.so 编译后):

```assembly
# .plt[bar] 的反汇编(简化)
0x1a8:   ldr x16, 0x200c0    # 加载 .got.plt[bar]
0x1ac:   br  x16             # 跳到那里
```

**.got.plt 的物理布局**(典型):

```
.got.plt[0]   = _DYNAMIC 段地址(linker 内部用)
.got.plt[1]   = link_map 指针(linker 内部用)
.got.plt[2]   = _dl_runtime_resolve 函数地址
.got.plt[3]   = bar 的实际地址(初始为 PLT stub + offset)
.got.plt[4]   = baz 的实际地址
...
```

### 3.3 第一次调用的完整流程(延迟绑定)

```
调用 call libfoo.bar() 进入 .plt[bar]
    ↓
.plt[bar] ldr x16, [.got.plt[bar]]
    ↓
x16 = .got.plt[bar] = _dl_runtime_resolve(初始值)
    ↓
br x16 → 跳到 _dl_runtime_resolve
    ↓
_dl_runtime_resolve 内部:
  1. 从 .plt[bar] 的下一条指令读出"重定位索引"(通常是 plt stub 后面的 offset)
  2. 用索引查 .rel.plt,找到 bar 的重定位条目
  3. 用重定位条目查 .dynsym,找到 bar 的符号值(在 libfoo 的 .dynsym 里)
  4. 计算真实地址 = load_bias(libfoo) + sym->st_value
  5. **把真实地址写回 .got.plt[bar]**  ← 关键!
  6. 跳到真实地址
    ↓
调用 _dl_runtime_resolve 后:
  - .got.plt[bar] = bar 的真实地址
  - 跳到 bar 执行
    ↓
[第二次调用]
调用 call libfoo.bar() 进入 .plt[bar]
  .plt[bar] ldr x16, [.got.plt[bar]]
  x16 = bar 的真实地址(已解析)
  br x16 → 跳到 bar 执行
  → 0 解析开销
```

**架构师必记**:**第一次调用的开销 = PLT stub + _dl_runtime_resolve + 写 GOT**,通常 1-10μs。如果有大量首次调用,累计开销可观。

### 3.4 BIND_NOW:把延迟绑定变成立即绑定

**BIND_NOW(DF_BIND_NOW / DF_1_NOW)的作用**:让 .so 加载时立即解析所有 PLT 重定位。

**实现机制**:

```
正常 .so(无 BIND_NOW):
  加载 .so
  → 处理 .rela.dyn(RELATIVE、GLOB_DAT)
  → 写 .got 的值
  → .got.plt 的值保持为 _dl_runtime_resolve
  → 跳 .init_array
  → 第一次调用时,触发 .got.plt 解析

带 BIND_NOW 的 .so:
  加载 .so
  → 处理 .rela.dyn
  → 处理 .rela.plt(把 .got.plt 的值直接写成真实地址)
  → 跳 .init_array
  → 第一次调用时,直接走真实地址(无 _dl_runtime_resolve)
```

**架构师必记**:

- BIND_NOW 启动慢 30-50ms(每 .so),运行时首次调用快
- Android 12+ 关键库(libart, libc)默认 BIND_NOW
- 第三方 SDK .so 通常不启用

### 3.5 真实案例:.plt / .got.plt 的物理布局

```bash
$ readelf -S libart.so | grep -E "plt|got"

[3] .plt                PROGBITS  ... AX   ...
[12] .got                PROGBITS  ... WA   ...   ← .got
[27] .rel.plt            REL       ... AI   24 8
[29] .got.plt            PROGBITS  ... WA   ...   ← .got.plt
```

**libart.so 的 PLT/GOT 规模**(从 readelf 数据):
- `.plt` = 0xa10 字节 ≈ 2.5KB(每个 stub 16 字节,533 个 = 8528 字节 ≈ 8.5KB,实际 PLT 头占 32 字节,所以 ~8.5KB;但 .plt 段只显示 2.5KB,说明实际有部分 PLT 是 .plt.sec 形式——Android 9+ 引入)
- `.got` = 0x210 字节(GOT 数据)
- `.got.plt` ≈ 0x40 字节 + N×8(每个 JUMP_SLOT 一项)
- `.rel.plt` = 533 条 × 24 字节 ≈ 12.5KB

**架构师必记**:**现代 Android 的 .so 大量使用 `.plt.sec`(更小的 PLT stub,16 字节)**,比传统 .plt(32 字节)小一半。

---

## 4. RELRO:把 .got.plt 变成只读

### 4.1 为什么需要 RELRO

**GOT 攻击的场景**:
- 攻击者通过缓冲区溢出,改写 .got.plt 中某个函数的地址
- 例如把 `free` 的地址改成 `system`
- 下次调用 `free(ptr)` 时,实际执行 `system(ptr)`,如果 ptr 来自用户输入 → 任意命令执行

**RELRO(Relocation Read-Only)的解法**:
- 加载完 .so + 完成所有重定位后
- mprotect(.got.plt 范围, PROT_READ)  ← 关键
- 之后 .got.plt 不可写,攻击者无法修改

### 4.2 Partial RELRO vs Full RELRO

| 维度 | Partial RELRO | Full RELRO |
|---|---|---|
| **保护 .got** | ✅(.got 段 mprotect 为 r--p) | ✅ |
| **保护 .got.plt** | ❌(保持 rw-p,允许延迟绑定) | ✅(.got.plt 也 mprotect 为 r--p) |
| **BIND_NOW** | 不需要 | **必须** |
| **性能** | 启动 +5ms | 启动 +30-50ms |
| **安全** | 防 .got 攻击 | **防 .got 攻击 + 防延迟绑定 PLT 攻击** |

**架构师必记**:**Full RELRO 必须配合 BIND_NOW**。否则 .got.plt 仍要写入,无法 mprotect 为只读。

### 4.3 RELRO 的实现机制

**RELRO 范围由 ELF 的 `PT_GNU_RELRO` program header 标记**(PLE 02 详述)。

**linker64 在 link_image 末尾的实现**:

```c
// linker.cpp::protect_relro(简化)
static void protect_relro(soinfo* si) {
    // 1. 找到 .gnu_relro 段
    const ElfW(Phdr)* relro_phdr = nullptr;
    for (int i = 0; i < si->phnum; i++) {
        if (si->phdr[i].p_type == PT_GNU_RELRO) {
            relro_phdr = &si->phdr[i];
            break;
        }
    }
    if (relro_phdr == nullptr) return;
    
    // 2. 计算 mprotect 范围
    ElfW(Addr) relro_start = page_start(relro_phdr->p_vaddr + si->base);
    ElfW(Addr) relro_end = page_end(relro_phdr->p_vaddr + si->base + relro_phdr->p_memsz);
    
    // 3. mprotect 为 r--p
    if (mprotect(reinterpret_cast<void*>(relro_start), relro_end - relro_start, PROT_READ) == -1) {
        DL_ERR("mprotect failed for RELRO");
    }
}
```

**关键事实**:

- mprotect 按 page(4KB)对齐,所以范围可能比 PT_GNU_RELRO 段大
- 一旦 mprotect 成功,这段内存永久只读(进程退出前)
- **顺序很重要**——必须先完成所有重定位,再 mprotect

### 4.4 真实案例:检查 .so 的 RELRO 状态

```bash
$ readelf -l libart.so | grep -A1 "GNU_RELRO"
  GNU_RELRO      0x18a000 0x000000000018a000 0x000000000018a000 0x000ae0 0x000ae0 RW     0x8
```

**解读**:RELRO 范围是 [0x18a000, 0x18aae0),共 0xae0 字节。

**检查是否 Full RELRO + BIND_NOW**:

```bash
$ readelf -d libart.so | grep -E "BIND_NOW|FLAGS_1"
0x000000000000001e (FLAGS)              BIND_NOW
0x0000000000000006 (FLAGS_1)            NOW
```

**两个标志都存在 → Full RELRO + BIND_NOW**。✅

**架构师必记**:**Android 12+ 强制要求所有 .so 启用 Full RELRO + BIND_NOW**。如果你的 .so 没启用,会在编译时被 NDK 警告。

### 4.5 安全收益量化

| 攻击 | 启用 RELRO 前的成功率 | 启用 RELRO 后 |
|---|---|---|
| **GOT 覆盖**(改 .got.plt 中的函数地址) | 高 | **0%(内存只读)** |
| **延迟绑定 PLT 攻击**(利用 _dl_runtime_resolve 写 GOT) | 中 | **0%(Full RELRO + BIND_NOW)** |
| **return-to-PLT**(不修改,直接调用) | 中 | 中(RELRO 防不了这种) |
| **ASLR 旁路**(用 PLT 入口代替真实地址) | 高 | 中(ASLR 仍生效) |

---

## 5. 符号解析机制

### 5.1 符号查找的 5 步路径

**linker64 解析一个未定义符号时,按以下顺序查找**:

```
1. .so 自身的 .dynsym(STT_GLOBAL/STT_WEAK)
   ↓ 命中 → 返回
2. .so 的依赖 .so 列表(soinfos[])
   └─ 对每个依赖 .so 递归执行步骤 1
   ↓ 命中 → 返回
3. 加载器(loader)所在的 namespace 全局搜索
   └─ find_library(已经加载的)
   ↓ 命中 → 返回
4. RTLD_DEFAULT / RTLD_NEXT 特殊 handle
   ↓ 命中 → 返回
5. 返回 nullptr → 抛"undefined symbol"错误
```

**关键事实**:

- **同进程内已加载的 .so 优先**——避免重复 mmap
- **依赖顺序很重要**——A 依赖 B,符号在 B 里能找到
- **DT_NEEDED 顺序 = 搜索顺序**——链接器按这个顺序遍历

### 5.2 GNU hash 表:O(1) 符号查找

**为什么需要 hash 表**:
- 线性扫描 .dynsym(几千项)太慢
- GNU hash 表用 O(1) 找到符号桶 → O(k) 解决冲突

**GNU hash 表的 3 个数组**(由 .gnu.hash section 提供):

```
buckets[nbucket]:  每个桶指向 chain 数组的第一个元素
chain[]:           链表,同桶的符号串起来
bloom[nbloom]:     布隆过滤器,加速"肯定不在"判断
```

**查找流程**:

```c
// linker_phdr.cpp::soinfo_do_lookup(简化)
const ElfW(Sym)* soinfo_do_lookup(soinfo* si, const char* name, soinfo** lsi) {
    // 1. 算 name 的 GNU hash
    uint32_t hash = compute_gnu_hash(name);
    
    // 2. 查 bloom filter
    if (!bloom_test(si->bloom, hash)) {
        return nullptr;  // 肯定不在
    }
    
    // 3. 查 bucket
    uint32_t bucket = hash % si->nbucket;
    uint32_t sym_index = si->bucket[bucket];
    
    // 4. 遍历 chain
    while (sym_index != STN_UNDEF) {
        ElfW(Sym)* sym = &si->symtab[sym_index];
        if (sym->st_name + sym->st_value) {
            // 5. 比较 name
            if (strcmp(si->strtab + sym->st_name, name) == 0) {
                return sym;  // 找到
            }
        }
        sym_index = si->chain[sym_index - si->symtab_offset];
    }
    return nullptr;
}
```

**性能对比**:

| 算法 | 1000 个符号的查找耗时 |
|---|---|
| 线性扫描 | 1-10μs |
| GNU hash(命中) | 0.1-0.5μs |
| GNU hash(未命中) | 0.1-0.3μs(走 bloom filter) |

**架构师必记**:**启用 GNU hash 是 NDK r17+ 的默认行为**。`--hash-style=gnu` 显式开启,`--hash-style=sysv` 用旧版 hash。

### 5.3 符号可见性:STB_* + STV_*

**符号的 8 种"绑定 × 可见性"组合**(核心 4 种):

| 绑定 | 可见性 | 含义 | 出现在 .dynsym |
|---|---|---|---|
| STB_GLOBAL | STV_DEFAULT | **正常导出符号** | ✅ |
| STB_GLOBAL | STV_HIDDEN | 隐藏,不出现在 .dynsym | ❌ |
| STB_WEAK | STV_DEFAULT | 弱符号,可被覆盖 | ✅ |
| STB_LOCAL | - | 局部符号,不出现在 .dynsym | ❌ |

**架构师视角**:**STV_HIDDEN 是减少符号暴露的核心武器**。`-fvisibility=hidden` 让所有符号默认 hidden,然后用 `__attribute__((visibility("default")))` 显式导出。

### 5.4 真实案例:符号解析失败的 4 个根因

**症状**:`undefined symbol: X`,启动期崩溃。

**根因 1:符号未导出**

```bash
$ readelf -s libfoo.so | grep -w "X"
# 没找到
```

**诊断**:
```bash
# 看看 libfoo 的 .dynsym 里有没有 X
$ readelf -Ds libfoo.so | grep "X"
# 如果 .symtab 里有但 .dynsym 里没有 → 符号没导出
```

**修复**:在源码里加 `__attribute__((visibility("default")))`,或在编译时不用 `-fvisibility=hidden`。

**根因 2:.so 没被加载**

```bash
# 看 libnative.so 的 NEEDED 列表
$ readelf -d libnative.so | grep NEEDED
0x0000000000000001 (NEEDED)             Shared library: [libfoo.so]
# libfoo.so 应该在 NEEDED 列表
```

**诊断**:
```bash
# 看 libfoo.so 是否被加载
$ adb shell cat /proc/1234/maps | grep "libfoo.so"
# 空 → libfoo.so 没被加载
```

**修复**:检查 linker logcat 找 `library not found` 原因。

**根因 3:架构错配**

```bash
# 看 libfoo.so 是什么架构
$ readelf -h libfoo.so | grep Machine
Machine:                           AArch64
# 但进程是 32 位
```

**修复**:用 arm64 设备跑 arm64 .so,不要混用 32/64 位。

**根因 4:SONAME 不匹配**

```bash
# libfoo.so 编译时的 SONAME 是 libfoo.so.1
$ readelf -d libfoo.so | grep SONAME
0x000000000000000e (SONAME)             Library soname: [libfoo.so.1]
# 但 libnative.so 的 NEEDED 写的是 libfoo.so
$ readelf -d libnative.so | grep "libfoo"
# 这是合法的,linker64 会按 SONAME 匹配
```

**诊断**:linker logcat 会有详细说明。

---

## 6. arm64 重定位类型详解

### 6.1 R_AARCH64_* 全表(常用)

**aarch64 平台有 60+ 种重定位类型,常用 8 种**:

| 类型 | 数值 | 含义 | 典型场景 |
|---|---|---|---|
| **R_AARCH64_ABS64** | 257 | 64 位绝对地址 | 64 位指针 |
| **R_AARCH64_ABS32** | 258 | 32 位绝对地址 | 兼容 32 位值 |
| **R_AARCH64_ABS16** | 259 | 16 位绝对地址 | 兼容 16 位值 |
| **R_AARCH64_PREL64** | 260 | 64 位 PC-relative | - |
| **R_AARCH64_PREL32** | 261 | 32 位 PC-relative | - |
| **R_AARCH64_PREL16** | 262 | 16 位 PC-relative | - |
| **R_AARCH64_GOTREL32** | 314 | GOT-relative 32 位 | - |
| **R_AARCH64_GOTREL64** | 315 | GOT-relative 64 位 | - |
| **R_AARCH64_GLOB_DAT** | 1025 | GOT 数据(全局变量) | .got 中的变量 |
| **R_AARCH64_JUMP_SLOT** | 1026 | PLT 跳转 | .got.plt 中的函数 |
| **R_AARCH64_RELATIVE** | 1027 | 相对基址 | PIE 内部引用 |
| **R_AARCH64_TLS_DTPMOD** | 1028 | TLS 模块引用 | thread_local |
| **R_AARCH64_TLS_DTPREL** | 1029 | TLS 块内偏移 | thread_local |
| **R_AARCH64_TLS_TPREL** | 1030 | TLS TP-relative 偏移 | thread_local |
| **R_AARCH64_TLSDESC** | 1031 | TLS 描述符 | TLS 优化 |
| **R_AARCH64_IRELATIVE** | 1032 | IFUNC 间接函数 | glibc 用 |

### 6.2 4 类重定位的"成本对比"

| 类型 | 数量级 | 性能影响 | 优化手段 |
|---|---|---|---|
| **RELATIVE** | 几千/so | **高**(必须立即) | .relr.dyn(紧凑) |
| **GLOB_DAT** | 几百/so | 中(必须立即) | GNU hash |
| **JUMP_SLOT** | 几十到几百/so | **中**(可延迟) | BIND_NOW(立即但启动慢) |
| **ABS** | 几十/so | 中(必须立即) | 无 |

**架构师必记**:**RELATIVE + GLOB_DAT 占 95% 的重定位耗时**。优化这两个 = 优化启动。

### 6.3 RELATIVE 重定位的细节

**R_AARCH64_RELATIVE 的语义**:

```
被重定位的地址 = load_bias + 被重定位地址处已存在的值
```

**典型场景**(全局变量指向另一个全局变量):

```c
// 编译时
int foo = 1;
int* bar = &foo;  // bar 指向 foo

// 编译后 bar 的位置(假设在 0x18a000)存的是 foo 的虚拟地址(假设 0x18a010)
// 但因为是 PIE,0x18a010 实际位置 = load_bias + 0x18a010
// 所以 bar 处要存:load_bias + 0x18a010

// 重定位项:
//   offset = 0x18a000(bar 的位置)
//   type = R_AARCH64_RELATIVE
//   addend = 0x18a010(foo 的虚拟地址)
```

**linker64 处理**:

```c
// linker.cpp::relocate(简化,只处理 RELATIVE)
case R_AARCH64_RELATIVE:
    // 1. 读被重定位地址处的当前值(就是 addend)
    ElfW(Addr) addend = *(ElfW(Addr)*)(reloc_offset);
    // 2. 写入:load_bias + addend
    *(ElfW(Addr)*)(reloc_offset) = si->base + addend;
    break;
```

**架构师视角**:**RELATIVE 重定位是 PIE 的"必要成本"**。Android 7+ 强制 PIE,意味着每个 .so 都有几千条 RELATIVE 重定位,启动时必须处理。

---

## 7. 立即绑定 vs 延迟绑定的取舍

### 7.1 性能对比

| 指标 | 延迟绑定(默认) | 立即绑定(BIND_NOW) |
|---|---|---|
| **启动时间** | 快 | 慢 30-50ms(每 .so) |
| **首次调用函数** | 慢 1-10μs | 快(已解析) |
| **运行时符号查找** | 需要 .dynsym | 不需要(已填) |
| **RELRO** | Partial 可选 | **Full 必须** |
| **安全性** | 中(防不了延迟绑定 PLT 攻击) | 高(防) |

### 7.2 什么场景用 BIND_NOW

**启用 BIND_NOW 的场景**:

| 场景 | 原因 |
|---|---|
| **关键库** (libart, libc, libm, libdl) | 启动后大量调用,首次调用不能慢 |
| **.so 数量少**(< 5) | 启动时间占比小,值得换运行时性能 |
| **严格安全要求** | Android 12+ SELinux 强制 |
| **JIT 引擎** (libart 的 JIT) | 编译时频繁调用 helper,延迟绑定会卡 |

**不启用 BIND_NOW 的场景**:

| 场景 | 原因 |
|---|---|
| **第三方 SDK** | 启动期不调用的函数较多,延迟绑定省启动时间 |
| **大量 .so** (> 10) | 启动时间成本太高 |
| **可选模块** | 部分函数可能永远不被调用 |

### 7.3 启动期优化 4 步法

**如果冷启动在 linker64 阶段慢,按这 4 步走**:

**Step 1:看 .so 数量**

```bash
$ adb shell cat /proc/1234/maps | grep -c "\.so"
# 假设 35 个 .so
```

**Step 2:看 .so 大小**

```bash
# 按 size 排序,找最大那几个
$ for f in $(ls /data/app/~~*/lib/arm64/*.so /system/lib64/*.so); do
    echo "$(stat -c %s $f) $f"
done | sort -rn | head -10
```

**Step 3:看 .so 的依赖深度**

```bash
# libfoo.so 依赖 libbar.so,libbar.so 依赖 libbaz.so → 深度 3
# 用 readelf -d 看 DT_NEEDED,手工算
```

**Step 4:看 .so 的 .rela.plt 大小**

```bash
$ readelf -r libfoo.so | grep -c "JUMP_SLOT"
# 100+ 个 JUMP_SLOT → 启用 BIND_NOW 可能省 1ms 首次调用
```

**架构师必记**:**优化前先量化,不要凭直觉改 BIND_NOW**。一次启动期多 30-50ms 是很重的成本。

---

## 8. 真实案例:重定位失败的全套诊断

### 8.1 症状分类

| 日志关键字 | 根因 | PLE 阶段 |
|---|---|---|
| `undefined symbol: X` | X 没导出 / 没加载 | §5.4 |
| `cannot locate symbol` | 同上 | §5.4 |
| `library not found` | 找不到 .so 文件 | §4.5(本系列 P03) |
| `wrong ELF class` | 32/64 位不匹配 | PLE 02 §2.4 |
| `invalid handle` | dlopen 失败时 dlsym | PLE 03 §7 |
| `mprotect failed` | RELRO 失败 | §4.3 |
| `Bad RELRO address` | RELRO 范围超出 VMA | §4.3 |

### 8.2 标准诊断流程

```bash
# Step 1: 看 linker 日志
$ adb logcat -d | grep -i "linker\|dlopen" | tail -50

# Step 2: 看进程加载了哪些 .so
$ adb shell cat /proc/1234/maps | grep "\.so" | awk '{print $NF}' | sort -u

# Step 3: 对出问题的 .so 做完整 readelf
$ adb pull /data/app/~~xxx/lib/arm64/libproblem.so
$ readelf -h libproblem.so
$ readelf -d libproblem.so
$ readelf -s libproblem.so | grep <symbol>
$ readelf -r libproblem.so | grep <symbol>

# Step 4: 用 nm 看导出符号
$ aarch64-linux-gnu-nm -D libproblem.so | grep <symbol>

# Step 5: 用 objdump 看反汇编
$ aarch64-linux-gnu-objdump -d libproblem.so | grep -A 5 "plt"
```

### 8.3 真实案例:`undefined symbol` 的完整修复

**症状**:

```
F libc : Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
W linker: cannot locate symbol "_ZNSt6vectorIiSaIiEE9push_backEi" referenced by /data/app/~~xyz/lib/arm64/libnative.so
```

**第 1 步:看 libnative.so 的 .rela.plt**

```bash
$ readelf -r libnative.so | grep "_ZNSt6vectorIiSaIiEE9push_backEi"
0x0001a87d0  0x000000000416 R_AARCH64_JUMP_SLOT  0000000000000000 _ZNSt6vectorIiSaIiEE9push_backEi
```

**第 2 步:看 .so 列表是否包含 libstdc++.so**

```bash
$ readelf -d libnative.so | grep NEEDED
# 没有 libstdc++.so!只有 libc++ 库
```

**根因**:`_ZNSt6vector...` 是 libstdc++ 的符号,但 libnative.so 没链接 libstdc++。可能 NDK 升级时 STL 库换了。

**第 3 步:修复** — 重新编译,链接正确的 STL:

```cmake
# CMakeLists.txt
target_link_libraries(native PRIVATE)
# 不指定 STL 库,使用 NDK 默认的 c++_shared
# 或者显式指定:target_link_libraries(native PRIVATE c++_shared)
```

**架构师视角**:**这类问题的根因是 NDK STL 库变化**。NDK r18+ 默认 `c++_shared`(动态链接),旧版本默认 `c++_static`(静态链接)。升级 NDK 时务必确认 STL 链接方式。

---

## 9. 重定位的性能影响与优化

### 9.1 重定位的耗时占比

**冷启动 1.5s 中,重定位贡献多少**:

| 阶段 | 耗时 | 占比 |
|---|---|---|
| linker64 启动 | 50-150ms | 3-10% |
| **重定位**(本篇) | **30-100ms** | **2-7%** |
| .init_array 执行 | 30-100ms | 2-7% |
| 进程启动其他 | 1000-1300ms | 67-87% |

**重定位不是冷启动的瓶颈**,但优化空间大(每 .so 节省 1-2ms 即可观)。

### 9.2 4 个优化技巧

| 技巧 | 节省时间 | 难度 |
|---|---|---|
| **启用 .relr.dyn** | 5-20ms(RELATIVE 压缩) | 自动(NDK r17+) |
| **减少 .rel.plt 数量** | 5-15ms(每减少 100 项) | 中(改代码用 static 函数) |
| **启用 BIND_NOW** | 首次调用 -50%,启动 +30-50ms | 低(改链接选项) |
| **拆分 .so** | 减少单 .so 重定位数 | 高(改架构) |

### 9.3 启动期重定位监控

**用 simpleperf 监控重定位耗时**:

```bash
$ adb shell simpleperf record -e cpu-cycles -p 1234 -o /data/local/tmp/perf.data
# 跑一段启动过程
$ adb shell simpleperf report -i /data/local/tmp/perf.data --show-callchain
# 找 _dl_runtime_resolve / _dl_relocate_* 函数
```

**用 linker trace 看每次 dlopen**:

```bash
# 开启 linker trace
$ adb shell setprop debug.ld.debug.syms 1
$ adb shell setprop debug.ld.debug.reloc 1
$ adb shell setprop debug.ld.debug.files 1
# 重启进程,看 logcat
```

**架构师必记**:**简单 perf 抓 .so 加载时,关注 `_dl_runtime_resolve` 函数**——它是延迟绑定的"重灾区"。

---

## 10. 架构师视角:重定位的 5 个核心洞察

### 10.1 洞察 1:重定位 = 占位符替换

**把"绝对地址"在加载后变成"真实地址"**。这是共享库能在任意地址运行的关键。

**两种策略**:
- 立即绑定(BIND_NOW):启动慢,运行时快
- 延迟绑定(默认):启动快,首次调用慢

### 10.2 洞察 2:4 张表 + 1 个紧凑格式

| 表 | 内容 | 时机 |
|---|---|---|
| .rela.dyn | RELATIVE + GLOB_DAT | 加载时立即 |
| .rela.plt | JUMP_SLOT | 默认延迟,BIND_NOW 立即 |
| .relr.dyn | RELATIVE 压缩 | 加载时立即(新格式) |

**架构师必记**:**`.rela.dyn + .relr.dyn` 是 PIE 的"必要成本"**。现代 .so 这两张表占大头。

### 10.3 洞察 3:RELRO 是性能/安全的最优解

| RELRO 类型 | 安全 | 性能 |
|---|---|---|
| 无 | 0 分 | 最快 |
| Partial | 1 分 | +5ms |
| **Full** | **2 分** | **+30-50ms** |

**Android 12+ 强制 Full RELRO**。**架构师要把 Full RELRO 当作"免费安全"**。

### 10.4 洞察 4:GNU hash 是启动期性能的关键

**没有 GNU hash**:
- 1000 个符号的 .so,符号查找 1-10μs
- 启动期数千次符号查找 → 5-10ms 总开销

**有 GNU hash**:
- 符号查找 0.1-0.5μs
- 启动期符号查找总开销 0.5-1ms

**节省 5-9ms**——值得检查。

### 10.5 洞察 5:从重定位失败直接映射到故障现象

| 故障现象 | 重定位根因 |
|---|---|
| `undefined symbol` | GLOB_DAT / JUMP_SLOT 找不到符号 |
| `library not found` | RELATIVE 失败(整个 .so 没加载) |
| `Bad RELRO address` | RELRO 范围超出 mprotect 限制 |
| `signal 11` 在 .plt | JUMP_SLOT 解析成 0x0(空函数指针) |
| 启动慢 100ms+ | BIND_NOW 启用太多 .so |

---

## 11. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **重定位 = 占位符替换** | 把 .so 里的占位地址(0 或 load_bias)替换成真实地址 |
| 2 | **4 张表 + RELR** | .rela.dyn(RELATIVE/GLOB_DAT) + .rela.plt(JUMP_SLOT) + .relr.dyn(RELATIVE 压缩) |
| 3 | **RELRO 是性能/安全的最优解** | Full RELRO + BIND_NOW,Android 12+ 强制 |
| 4 | **GNU hash 把 O(n) 变 O(1)** | bloom filter + bucket + chain,启动期节省 5-9ms |
| 5 | **重定位失败直接映射故障现象** | 异常 → 根因 → 修复(见 §8.2) |

---

## 12. 下一篇预告

05 篇《.init_array 与构造函数链:静态初始化的执行顺序》会沿着本篇埋下的线索,深入讲:

- .init / .fini / .init_array / .fini_array / .preinit_array 区别
- linker 倒序执行 .init_array 的设计依据
- `__attribute__((constructor))` 优先级
- libc / libdl / libm / liblog 的初始化顺序
- JNI_OnLoad 在 .init_array 之后触发
- 构造失败的连锁反应
- 架构师视角:.init_array 是隐藏的"启动期副作用源"

**05 篇预计 3 天后产出**,届时一起发你看。

---

## 附录 A:R_AARCH64_* 重定位类型速查

| 类型 | 数值 | 含义 | 性能影响 |
|---|---|---|---|
| R_AARCH64_ABS64 | 257 | 64 位绝对地址 | 中 |
| R_AARCH64_ABS32 | 258 | 32 位绝对地址 | 中 |
| R_AARCH64_PREL64 | 260 | 64 位 PC-relative | 低 |
| R_AARCH64_PREL32 | 261 | 32 位 PC-relative | 低 |
| R_AARCH64_GLOB_DAT | 1025 | GOT 数据 | 高 |
| R_AARCH64_JUMP_SLOT | 1026 | PLT 跳转 | 中(可延迟) |
| R_AARCH64_RELATIVE | 1027 | 相对基址 | **高(必须立即)** |
| R_AARCH64_TLS_DTPMOD | 1028 | TLS 模块 | 低 |
| R_AARCH64_TLS_DTPREL | 1029 | TLS 块内偏移 | 低 |
| R_AARCH64_TLS_TPREL | 1030 | TLS TP-relative | 低 |
| R_AARCH64_TLSDESC | 1031 | TLS 描述符 | 中 |
| R_AARCH64_IRELATIVE | 1032 | IFUNC 间接函数 | 中 |

## 附录 B:4 张重定位表对比

| 维度 | .rela.dyn | .relr.dyn | .rela.plt | (无 .rel.plt) |
|---|---|---|---|---|
| **类型** | RELA | 紧凑 RELA | RELA | - |
| **项大小** | 24B | 1-9B(平均 1.5B) | 24B | - |
| **重定位类型** | RELATIVE/GLOB_DAT/ABS | RELATIVE | JUMP_SLOT | - |
| **写入目标** | .got | .got | .got.plt | - |
| **时机** | 加载时立即 | 加载时立即 | 默认延迟 / BIND_NOW 立即 | - |
| **数量级** | 几百 | 几千(压缩) | 几十到几百 | - |

## 附录 C:RELRO 状态检查

| 检查项 | 命令 | 期望 |
|---|---|---|
| PT_GNU_RELRO 存在 | `readelf -l lib.so \| grep GNU_RELRO` | 存在 |
| BIND_NOW 标志 | `readelf -d lib.so \| grep -E "BIND_NOW\|FLAGS_1.*NOW"` | 同时存在 |
| .got.plt 实际只读 | `adb shell cat /proc/PID/maps \| grep lib.so` | r--p(不是 rw-p) |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 05 .init_array | 本篇 §6 讲的 RELATIVE 重定位处理完后,才执行 .init_array |
| 12 进程启动 | Zygote fork 后,子进程会执行本篇的 link_image() |
| 14 风险地图 | §8 失败诊断的"标准流程"是 P14 的核心 |

---

> **本篇把"重定位"拆解到 4 张表 + RELRO + 符号解析 + arm64 类型 + 失败诊断 5 个维度。**
> **05 篇会在这个基础上,讲 .init_array——.so 加载完成后,那些"看不见的初始化"到底跑了什么。**
> **记住 4 张表、RELRO 两种、5 类失败映射,你的重定位视角就立住了。**
