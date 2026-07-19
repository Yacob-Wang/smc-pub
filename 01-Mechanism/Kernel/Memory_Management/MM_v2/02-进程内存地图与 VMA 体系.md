# 02-进程内存地图与 VMA 体系

> **系列**：面向稳定性的 Android 内存架构深度解析系列（MM_v2）
>
> **源码基线**：AOSP `android-14.0.0_r1`（`refs/heads/android14-release`）
>
> **内核矩阵**：`android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`（本篇涉及 `mm/mmap.c` 与 `include/linux/mm_types.h`；各内核版本的差异点见 §3.3 vm_area_struct 字段变化、§5 合并/拆分逻辑）
>
> **目标读者**：Android 稳定性框架架构师
>
> **前置阅读**：[01-内存系统总览：从进程视角到硬件的完整链路](01-内存系统总览：从进程视角到硬件的完整链路.md)
>
> **下一篇**：[03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md)

---

## 本篇定位

- **本篇系列角色**：核心机制第 2 篇 — 讲 App 进程的虚拟地址账本（VMA 体系），把"一个进程的内存长什么样"在用户态视角彻底讲透
- **强依赖**：MM_v2 01 已讲"五层架构 + 一个 byte 旅程"（本篇是 Layer 1:App 视角的展开）
- **承接自**：01 §3 全栈架构图（本篇聚焦 App 进程的虚拟地址账本）
- **衔接去**：
  - 03 讲 ART 堆（Layer 2:Java 堆，[anon:dalvik-*] 在 maps 里怎么映射）
  - 04 讲 Native 堆（Layer 2:Native 堆，scudo 分配的 mmap 段在 maps 里长什么样）
- **不重复内容**：
  - 01 已讲的"五层架构骨架 + byte 旅程",本篇不重复
  - ART/Native 堆的内部机制详见 03/04

#### §0 锚点案例的可验证 4 件套:ShopApp 冷启动 VMA 膨胀 2800→4500 行

> **环境**:
> - 设备:Pixel 7（G2,arm64-v8a,8GB RAM）
> - Android 版本:AOSP `android-14.0.0_r1`
> - Kernel:`android14-5.15` GKI
> - App:某 IM App v6.2.0（脱敏代号 `ShopApp`,集成 6 个 SDK）
> - 工具:`adb shell cat /proc/pid/maps` + `simpleperf -e mm:vm_area_alloc` + `dumpsys gfxinfo`

> **复现步骤**:
> 1. 工厂重置,安装 ShopApp v6.2.0
> 2. `adb shell am force-stop com.shop.app` → `am start -n com.shop.app/.MainActivity`
> 3. `sleep 2` → 抓 `/proc/$(pidof com.shop.app)/maps` 行数
> 4. 对比 v6.1.0 上一版本 maps 行数（典型值 2800 → 4500,+61%）

> **logcat / simpleperf 关键片段**:
> ```
> 99.4%  [kernel]  vm_area_alloc
>         ↳ art::gc::Heap::ConcurrentCopying::Initialize  (新 GC 模式)
>         ↳ art::Class::AllocObject  (Java 对象)
>         ↳ com.shop.app.sdks.XxxSDK::init  (SDK 初始化)
>         ↳ Application.onCreate
> ```
> ```
> # /proc/pid/maps 增量(关键观察点)
> 12 → 1700 个 [anon:4KB] 段(增量 +1688)
> ```

> **修复 commit-style diff**:
> ```diff
> --- a/sdk/src/main/java/com/sdk/NativeBuffer.java
> +++ b/sdk/src/main/java/com/sdk/NativeBuffer.java
> @@ -Activity.onDestroy()
> -    // 旧版:为每个 Activity 预创建 4KB native buffer,Activity destroy 时只清空列表不 munmap
> -    public void onDestroy() {
> -        mBuffers.clear();
> -    }
> +    // 修复:为每个 buffer 显式 munmap,避免 VMA 泄漏
> +    public void onDestroy() {
> +        for (NativeBuffer b : mBuffers) {
> +            b.unmap();  // 内部调用 munmap(b.addr, b.size)
> +        }
> +        mBuffers.clear();
> +    }
> ```
> 完整排查过程与回归指标见 §8。

---

## 0. 写在前面：为什么把 VMA 单独拎出来讲

VMA（Virtual Memory Area，虚拟内存区域）是 Linux 内核为进程维护的"虚拟地址段账本"。每一次 `mmap`、`brk`、`exec`、动态库加载、线程栈创建，都会变成一条 VMA 记录。**一个 App 进程的"内存地图"在 `/proc/pid/maps` 里就是这张账本的对外视图**。

对一个稳定性架构师而言，VMA 是排查下列问题的**第一现场**：

| 现象 | VMA 视角的根因 |
| --- | --- |
| App 冷启动慢 | `mmap` 数量爆炸 → `find_vma` 树查找变慢 |
| 共享库内存统计虚高 | 没有合并的 VMA → PageCache 无法去重 |
| mmap 后忘记 munmap | VMA 永不释放 → RLIMIT_AS / RLIMIT_DATA 触发 |
| [vdso] 多份 | glibc 版本切换残留 → 内核无法合并 |
| JNI `NewLocalRef` 爆栈 | JNI 局部引用表 512 上限（ART 14 改为动态 65536） |
| ASLR 被旁路 | vdso 偏移固定 → ROP 攻击面 |

本篇将沿着"字段全解 → 三类划分 → 数据结构 → 系统调用 → 私有/共享 → 合并拆分 → 风险地图 → 实战案例"的链路，把这张账本彻底讲透。

---

## 1. /proc/pid/maps 字段全解

### 1.1 是什么

`/proc/<pid>/maps`（在 Android 内由 `fs/proc/task_mmu.c` 的 `proc_pid_maps_ops` 与 `show_vma_header_prefix/m_vma_format` 提供）是一个文本文件，按"虚拟地址区间"的粒度，列出进程当前的全部 VMA。它是**用户态唯一无需 root 即可枚举进程虚拟地址空间的标准接口**。

`/proc/<pid>/smaps` 是同一份数据的扩展版，每个 VMA 额外带 RSS、PSS、SwapPss 等统计；`/proc/<pid>/smaps_rollup` 是按类别聚合的精简版。三者底层共享同一套 `vm_area_struct` 链表/红黑树遍历逻辑。

### 1.2 为什么需要它

对稳定性架构师来说，**maps 是排查"内存去哪了"的 5 秒入口**。当你拿到一份 ANR dumpsys 或 bugreport，里面包含的 maps 文本能直接告诉你：

- 加载了哪些 `.so`（路径 + 大小）
- Java 堆在哪一段（`[heap]`）、有多大
- 线程栈有几条（`[stack:<tid>]`，每条默认 8MB，由 `ulimit -s` 决定）
- 是否有异常 mmap（巨量小段、未释放段）
- 是否启用了 ASLR（地址是否每次启动都不同）

### 1.3 一条真实的 maps 行（解构）

```
7f8a4b000-7f8a4f000 r--p 00000000 fc:01 1234567   /system/lib64/libc.so
│              │      │    │       │      │              │
│              │      │    │       │      │              └─ pathname
│              │      │    │       │      └─ inode (1234567)
│              │      │    │       └─ device (fc:01)
│              │      │    └─ offset (4KB 对齐)
│              │      └─ perms (r--p)
│              └─ end (exclusive)
└─ start (inclusive)
```

### 1.4 字段定义与源码

源码入口：`fs/proc/task_mmu.c::show_vma_header_prefix`、`m_vma_format`。

```c
// fs/proc/task_mmu.c
static int do_show_vma(struct vm_area_struct *vma, ...)
{
    // m_vma_format 决定打印顺序：
    //   0: address perms offset dev inode pathname  （默认）
    //   1: address perms dev inode pathname          （无 offset）
    //   2: address perms                            （最简）
    return seq_printf(m, "%08lx-%08lx %c%c%c%c %08llx %02x:%02x %lu ",
                      vma->vm_start, vma->vm_end,
                      vma->vm_flags & VM_READ ? 'r' : '-',
                      vma->vm_flags & VM_WRITE ? 'w' : '-',
                      vma->vm_flags & VM_EXEC ? 'x' : '-',
                      vma->vm_flags & VM_SHARED ? 's' : 'p',
                      (unsigned long long)vma->vm_pgoff << PAGE_SHIFT,
                      MAJOR(vma->vm_file->f_inode->i_sb->s_dev),
                      MINOR(vma->vm_file->f_inode->i_sb->s_dev),
                      vma->vm_file->f_inode->i_ino);
}
```

### 1.5 每个字段的语义

| 字段 | 取值 | 含义 | 稳定性关注点 |
| --- | --- | --- | --- |
| **address** | `start-end`（hex） | VMA 的虚拟地址区间，左闭右开 | 是否落在 `mmap_base` 附近、是否横跨 `stack_guard_gap` |
| **perms** | `r/w/x/s/p` 四组 | VMA 的权限位 + 是否共享 | JNI 误把 `w` 加上 → 代码段被改写 |
| **offset** | 文件内偏移（hex） | 仅文件映射有意义；匿名映射显示为 `00000000` 或 `4k * pgoff` | 与文件实际大小是否一致 |
| **dev** | `major:minor` | 文件所在设备 | 跨挂载点 / chroot 后的偏差 |
| **inode** | inode 编号 | 文件唯一标识 | 0 表示匿名映射（heap / stack / BSS） |
| **pathname** | 文件路径或特殊标签 | 标识 VMA 用途 | 出现奇怪的路径 → 第三方 SDK 残留 |

### 1.6 特殊的 pathname 取值

| pathname | 含义 | 来源 |
| --- | --- | --- |
| `[heap]` | 由 `brk()` 管理的传统堆 | `mm/brk.c::do_brk_flags`，`vm_flags` 含 `VM_HEAP` |
| `[stack]` | 主线程栈 | `mm/mmap.c::create_elf_tables` 在 exec 时创建 |
| `[stack:<tid>]` | 子线程栈 | `clone3` 时由内核 `mm/mmap.c::do_mmap` 创建，含 `VM_GROWSDOWN` |
| `[vdso]` | 虚拟动态共享对象 | `arch/x86/entry/vdso/vma.c`，提供 `__vdso_gettimeofday` 等快速 syscall |
| `[vvar]` | 与 vdso 配对的内核-用户共享页 | 提供 vvar 数据 |
| `[vsyscall]` | x86-64 遗留的固定地址 syscall 跳转页（仅读） | `arch/x86/entry/vsyscall/vsyscall_emu.c` |
| `[anon:<tag>]` | 用户态 mmap 时传入的 `MAP_ANONYMOUS` + 显式标签 | ART 在 `[anon:dalvik-main space]` 等位置出现 |

### 1.7 稳定性架构师视角

1. **maps 是"零成本"诊断起点**。看到 `[heap]` 异常大 → Java/ART 堆或 brk 区域泄漏；看到巨量 4KB 段 → mmap 调用太碎。
2. **paths 出现 `/data/data/<pkg>` 中的 `libxxx.so`** → 这个 `.so` 是 App 自带，不是 system，说明厂商定制或 32/64 位混合加载。
3. **`[vdso]` 出现多份**（虽然罕见）→ 说明 `personality` 或 `execve` 不一致，会拖慢 syscall 性能，详见 [7.4 ASLR 失效]。

---

## 2. VMA 三类划分：代码段 / 堆 / 栈 / mmap 区 / [vdso] / [vsyscall]

### 2.1 进程虚拟地址空间全景

arm64 Linux 用户态地址空间默认 39-bit（512GB），高 256GB 给内核（`PAGE_OFFSET`），低 256GB 给用户（`TASK_SIZE = 0x0000_8000_0000_0000`）。下面是一个典型 App 进程的空间布局（**注意：arm64 没有 x86 那种高位的固定 vsyscall**）：

```
虚拟地址                内容                       大小（典型）
───────────────────  ────────────────────────  ────────────────
0x0000_7fff_ffff_ffff ┐
                      │  内核空间（不可见）       256GB
0x0000_8000_0000_0000 ┘  TASK_SIZE 边界
0x0000_7fff_xxxx_xxxx ┐
                      │  [stack] 主线程           8MB
                      │  [stack:<tid>] 子线程    每条 8MB（pthread_attr 默认）
                      │  --- gap (ASLR random) ---
                      │  mmap 区（向下增长）       可达数十 GB
                      │  ─ libc.so / libart.so / libskia.so ...
                      │  ─ [vdso] 1 page（随机）  4KB
                      │  ─ [vvar]  1-2 page       4-8KB
                      │  ─ 运行时 mmap（Bionic scudo, 字体, GL） 
0x0000_7000_0000_0000 ┤
                      │  --- brk heap ---         由 RLIMIT_DATA 决定，常见配置为 RLIM_INFINITY
                      │  [heap] （brk 管理）
                      │  --- BSS / data ---
                      │  /system/bin/app_process (exe)
0x0000_0000_0010_0000 ┘
                      │  NULL page guard          64KB
0x0000_0000_0000_0000 
```

### 2.2 VMA 的三大类来源

| 类型 | 创建系统调用 | VMA 标志（关键） | 典型场景 |
| --- | --- | --- | --- |
| **代码段 / 数据段** | `execve()` 内核侧 | `VM_READ \| VM_EXEC`（代码）、`VM_READ \| VM_WRITE`（data/bss） | `/system/bin/app_process`、`.so` 文件映射 |
| **堆（Heap）** | `brk()` / `mmap(MAP_ANONYMOUS)` | `VM_READ \| VM_WRITE \| VM_HEAP`（仅 brk） | malloc 小对象（scudo）、ART 堆的 native 备份 |
| **栈（Stack）** | `clone()` 时由内核创建 | `VM_READ \| VM_WRITE \| VM_GROWSDOWN` | 主线程 + 任意子线程 |
| **mmap 区** | `mmap()` | 视 flags 而定 | 动态库、JNI ByteBuffer、Bitmap native、ashmem |
| **[vdso]** | 内核在 exec 时插入 | `VM_READ \| VM_EXEC \| VM_DONTEXPAND \| VM_MAYREAD \| VM_MAYEXEC \| VM_MAYSHARE` | `clock_gettime` 快速路径 |
| **[vsyscall]**（仅 x86-64） | 内核静态映射 | `VM_READ`（不可执行、不可写） | 历史遗留，arm64 不存在 |

### 2.3 代码段：从 ELF 到 VMA

进程启动时，内核 `fs/binfmt_elf.c::load_elf_binary` 解析 ELF，按 `PT_LOAD` 段逐个调用 `mmap`：

源码路径：`fs/binfmt_elf.c`、`mm/mmap.c::do_mmap`。

```c
// fs/binfmt_elf.c（简化）
static int load_elf_binary(struct linux_binprm *bprm)
{
    // 1. 解析 ELF header & program headers
    // 2. 对每个 PT_LOAD 调用 elf_map()
    for (i = 0; i < elf_ex.e_phnum; i++) {
        elf_map(filep, load_bias + vaddr, elf_ppnt, ...);
        // 3. 标志转换：PF_R → VM_READ，PF_W → VM_WRITE，PF_X → VM_EXEC
    }
    // 4. 创建 BSS（如果 PT_LOAD 含未初始化段）：do_brk_flags()
    // 5. 创建 [stack]：create_elf_tables() + setup_arg_pages()
    // 6. 把动态链接器（ld.so）也 mmap 进来
}
```

**稳定性架构师视角**：如果一个 `.so` 的 PT_LOAD 段设置错误（如代码段加了 `PF_W`），它在 maps 中会显示 `rwx`，给攻击者改写代码段的机会。Android 12+ SELinux 配合 `mmap_min_addr` 已加固此类风险。

### 2.4 堆：brk vs mmap

传统 `malloc(<=128KB)` 走 `brk` 区域（[heap]），`malloc(>128KB)` 走 mmap 匿名映射。Android bionic scudo 在 5.0+ 改用纯 mmap 策略，所以**现代 App 几乎看不到 `[heap]`，而是有大量 `[anon:scudo:...]`**。详见 [04-Native 堆内存与分配器（AOSP 14）](04-Native 堆内存与分配器（AOSP 14）.md)。

源码路径：`mm/brk.c::do_brk_flags`、`mm/mmap.c::do_mmap`。

### 2.5 栈：主线程与子线程的差异

主线程栈来自 `execve` 末尾的 `setup_arg_pages`，子线程栈来自 `clone` 时的 `mm/mmap.c::do_mmap(VM_GROWSDOWN)`：

```c
// mm/mmap.c（简化）
static struct vm_area_struct *__install_special_mapping(
    struct mm_struct *mm, unsigned long addr, unsigned long len,
    unsigned long vm_flags, ...)
{
    // 子线程栈：addr 是 pthread_attr 里指定的 stackaddr
    // vm_flags 必须含 VM_GROWSDOWN → 缺页时栈可自动向下扩张
}
```

**稳定性架构师视角**：

- **栈溢出**：每条子线程默认 8MB，1024 条线程就吃掉 8GB 虚拟地址空间；实际 RSS 取决于是否触发过缺页。`pthread_create` 失败原因之一就是 RLIMIT_AS。
- **栈爆栈**：Android 主线程会捕获 `SIGSEGV` 并触发 `DEBUG_CHILD` 流程，但子线程没有注册 `SIGSEGV` handler——爆栈后被默认信号行为直接终止（SIGSEGV → 进程被杀）。

### 2.6 mmap 区：动态库与运行时数据

mmap 区是 App 进程最大、最复杂的部分。一个典型 App 启动后的 mmap 区包含：

| 来源 | 路径样例 | 大小量级 |
| --- | --- | --- |
| 系统库 | `/system/lib64/libc.so`、`libart.so` | 1-30MB |
| App 自带库 | `/data/app/~~xxx/lib/arm64-v8a/libxxx.so` | 1-50MB |
| ART 镜像 | `/system/framework/boot.art` 等 | 数十 MB-百 MB |
| scudo 大块 | `[anon:scudo:arena0]` | 数十-数百 MB |
| JNI ByteBuffer | `[anon]` | 视 App |
| gralloc 图形 | `/dev/ashmem` 或 `/dmabuf` | 数十-数百 MB |
| vdso | `[vdso]` | 4KB |
| vvar | `[vvar]` | 4-8KB |

### 2.7 [vdso]：虚拟动态共享对象

`[vdso]` 是内核映射到用户态的一页共享代码，**用于加速常用 syscall**：

- `clock_gettime(CLOCK_REALTIME/MONOTONIC)`：避免进入内核
- `gettimeofday()`：避免进入内核
- `getcpu()`：避免进入内核

源码路径：`arch/arm64/kernel/vdso.c`、`arch/arm64/kernel/vdso/vgettimeofday.c`。

```c
// arch/arm64/kernel/vdso.c（简化）
int arch_setup_additional_pages(struct linux_binprm *bprm, int uses_interp)
{
    // 1. 计算随机化偏移（ASLR）
    vdso_random_offset = vdso_base_cookie ^ mm->mmap_base;
    // 2. mmap vdso 数据段（[vvar]）
    // 3. mmap vdso 代码段（[vdso]）
}
```

**稳定性架构师视角**：

- `[vdso]` 性能极高（纳秒级）；若被旁路（如某个 hook 替换 `clock_gettime`），则所有依赖时间的代码路径都会慢 1-2 个数量级。
- 老版本 glibc（<2.31）会**自己 dlopen 一份 libc vdso**，导致内核 vdso 失效。

### 2.8 [vsyscall]：x86-64 历史遗留（arm64 无）

`[vsyscall]` 是 x86-64 在 2.6 时代引入的固定地址 (`0xffffffffff600000`) syscall 跳转页。**arm64 没有这个概念**——这是 arm64 Android 的天然安全优势。

现代内核默认以 `vsyscall=emulate` 启动（仅可读、不可执行），且每次执行触发 #PF → 内核模拟返回结果。性能比 `[vdso]` 慢 10-100 倍。

### 2.9 综合：一次 `am start -n com.example/.MainActivity` 后的 maps 概貌

```
地址                              段名                                    累计大小
────────────────────────────  ─────────────────────────────────────  ─────────
0x0000_7000_0000_0000        mmap_base 附近
                              ... /system/lib64/libc.so               ~1.4 MB
                              ... /system/lib64/libart.so             ~10 MB
                              ... /system/lib64/libskia.so            ~10 MB
                              ... /data/app/.../libxxx.so             ~5 MB
                              ... /system/framework/boot.art          ~60 MB
                              ... [anon:scudo:arena0..N]              ~50 MB
                              ... [vdso] [vvar]                       ~16 KB
0x0000_7fff_xxxx_xxxx        [stack]                                 ~8 MB
                              --- stack guard gap ---
                              [stack:12345] [stack:12346] ...        N×8 MB
────────────────────────────  ─────────────────────────────────────  ─────────
合计 VMA 数量：200-500 个（冷启动初期） / 800-1500 个（运行 5 分钟后）
```

> 经验值：普通 App 启动初期 VMA 数 ~200-400，运行起来后稳定在 ~800-1500。**若超过 3000**，需重点排查是否有 mmap 泄漏。

---

## 3. vm_area_struct 数据结构

### 3.1 是什么

`struct vm_area_struct`（简称 `vma`）是描述一段连续虚拟地址的内核结构体，每个进程的所有 vma 通过两种数据结构组织：

1. **单链表**（`mm->mmap`，头节点在 `mm_struct`）：按地址顺序双向链接，用于顺序遍历。
2. **红黑树**（`mm->mm_rb`，根节点在 `mm_struct`）：用于 O(log N) 的 `find_vma()`。

源码路径：`include/linux/mm_types.h`、`include/linux/mm.h`、`mm/mmap.c`。

### 3.2 为什么需要双索引

| 操作 | 链表复杂度 | 红黑树复杂度 | 实际使用 |
| --- | --- | --- | --- |
| 顺序遍历所有 VMA | O(N) | O(N)（中序） | `/proc/pid/maps`、unmap 整个范围 |
| 按地址查找 VMA | O(N) | O(log N) | 每次缺页、每次 mmap/munmap |
| 找最大空闲区间 | O(N) | O(N)（带 cached_hole 优化） | mmap 分配策略 |

**N=数千时，O(N) 缺页就是稳定性的灾难**——一次 1ms 的缺页在 1 千万次/天面前就是 2.7 小时的总延迟。这就是 VMA 数量爆炸会导致"冷启动慢"的核心原因。

### 3.3 关键字段全解

源码路径：`include/linux/mm_types.h::vm_area_struct`（基于 GKI 5.10）。

```c
// include/linux/mm_types.h（精简）
struct vm_area_struct {
    /* The first cache line has the info for VMA tree walking */
    unsigned long vm_start;            /* 起始虚拟地址（含） */
    unsigned long vm_end;              /* 结束虚拟地址（不含） */
    struct mm_struct *vm_mm;           /* 所属 mm */
    pgprot_t vm_page_prot;             /* 页保护位（写 PTE 时用） */
    unsigned long vm_flags;            /* VMA 标志位，见 3.4 */

    /* 三种链接方式 */
    struct rb_node vm_rb;              /* 红黑树节点 */
    struct list_head anon_vma_chain;   /* anon_vma 链表 */
    const struct vm_operations_struct *vm_ops; /* 缺页、close、mremap 等回调 */

    /* 文件映射 */
    unsigned long vm_pgoff;            /* 文件内偏移（页） */
    struct file *vm_file;              /* 文件指针（NULL=匿名） */
    void *vm_private_data;             /* 驱动私有数据 */
    struct vm_area_struct *vm_prev;    /* 链表前驱 */
    struct vm_area_struct *vm_next;    /* 链表后继 */

    /* 锁与引用 */
    struct rw_semaphore *vm_lock;      /* 通常指向 i_mmap_rwsem 或 anon_vma->rwsem */
    refcount_t vm_refcnt;              /* 引用计数（split 后共享） */
    atomic_long_t swap_readahead_info; /* swap 预读 hint */

    /* NUMA */
    struct mempolicy *vm_policy;       /* mbind/mbind2 时设置 */

    /* 其它 */
    struct vm_userfaultfd_ctx vm_userfaultfd_ctx; /* userfaultfd */
};
```

**总大小**（典型 GKI 5.10 arm64）：**~232 字节**（不含 vm_lock 等外部指针）。

> 经验值：VMA 自身每条 ~232B × 1000 条 ≈ 232KB。**VMA 本身的元数据开销并不是问题**，问题在于 `find_vma()` 的 O(log N) 树遍历在 N>3000 时仍可观测到 1-3μs 的单次开销。

### 3.4 vm_flags 标志位全解

源码路径：`include/linux/mm.h`。

| 标志 | 位 | 含义 | 稳定性关联 |
| --- | --- | --- | --- |
| `VM_READ` | 0 | 可读 | 缺页时 PF_PROT 触发 #PF |
| `VM_WRITE` | 1 | 可写 | 同上 |
| `VM_EXEC` | 2 | 可执行 | W^X：代码段不应有写 |
| `VM_SHARED` | 3 | 共享映射 | 决定是否走 COW 路径 |
| `VM_MAYREAD` | 4 | 可被 mprotect 加读 | |
| `VM_MAYWRITE` | 5 | 可被 mprotect 加写 | |
| `VM_MAYEXEC` | 6 | 可被 mprotect 加执行 | |
| `VM_MAYSHARE` | 7 | 可被 mprotect 加共享 | |
| `VM_GROWSDOWN` | 8 | 向下扩展（栈） | 缺页自动 grow |
| `VM_UFFD_MISSING` | 9 | userfaultfd 缺页通知 | |
| `VM_PFNMAP` | 10 | 映射物理页（ioremap 等） | 驱动用 |
| `VM_LOCKED` | 11 | mlock：永不被 swap | mlock 过多会拖垮系统 |
| `VM_IO` | 12 | I/O 映射 | |
| `VM_SEQ_READ` | 13 | 顺序读 hint | |
| `VM_RAND_READ` | 14 | 随机读 hint | |
| `VM_DONTCOPY` | 15 | fork 时不复制 | |
| `VM_DONTEXPAND` | 16 | mremap/mmap 不扩展 | |
| `VM_LOCKONFAULT` | 17 | 缺页时上锁（mlock） | |
| `VM_ACCOUNT` | 18 | 是否计入 RLIMIT_AS | 缺页时检查 |
| `VM_NORESERVE` | 19 | 不预占 swap | MAP_NORESERVE 时设置 |
| `VM_HUGEPAGE` | 20 | 透明大页 hint | |
| `VM_SYNC` | 21 | 同步 I/O | |
| `VM_ARCH_1` | 22 | 架构自定义 | |
| `VM_WIPEONFORK` | 23 | fork 时清零（用于 secret-mmap） | 5.4+ |
| `VM_DONTDUMP` | 24 | core dump 不写 | 5.4+ |
| `VM_MIXEDMAP` | 25 | PFN+pte 混合 | |
| `VM_HUGEPAGE` | 26 | 同 20（位冲突，旧版） | |
| `VM_NOHUGEPAGE` | 27 | 禁大页 hint | |
| `VM_MERGEABLE` | 28 | KSM 可合并 | 5.4+ |
| `VM_HEAP` | 内部 | brk 区域标记 | 仅内核用 |
| `VM_DROPPABLE` | 内部 | cgroup v2 可回收 | 6.1+ |

**稳定性架构师视角**：在 maps 中看到 `---p`（全无权限）通常是栈的 guard page 或 seccomp filter 的 page，看 `---s` 不太可能（VM_SHARED 需要映射后端）。看到 `rwx` 在非代码段 → 严重 bug 或被恶意改写。

### 3.5 mm_struct：VMA 容器

源码路径：`include/linux/mm_types.h::mm_struct`。

```c
struct mm_struct {
    struct vm_area_struct *mmap;          /* 链表头 */
    struct rb_root mm_rb;                 /* 红黑树根 */
    u64 vmacache_seqnum;                  /* vmacache 序列号（避免 stale） */
    unsigned long mmap_base;              /* mmap 起始地址（向下生长） */
    unsigned long mmap_legacy_base;       /* 兼容模式 mmap_base */
    unsigned long task_size;              /* 用户地址空间上限 */
    unsigned long highest_vm_end;         /* 已分配最高地址（get_unmapped_area 用） */
    pgd_t *pgd;                           /* 页表基址 */
    atomic_t mm_users;                    /* 共享用户数（CLONE_VM） */
    atomic_t mm_count;                    /* 总引用数 */
    int map_count;                        /* 当前 VMA 数量 */

    /* 锁 */
    struct rw_semaphore mmap_sem;         /* 主写锁（重入） */
    spinlock_t page_table_lock;           /* 页表锁 */

    /* RSS 统计 */
    unsigned long total_vm;               /* 虚拟页总数 */
    unsigned long locked_vm;              /* mlock 页数 */
    unsigned long pinned_vm;              /* pin_user_pages 占用 */
    unsigned long data_vm;                /* data/heap 页数 */
    unsigned long exec_vm;                /* 代码段页数 */
    unsigned long stack_vm;               /* 栈页数 */

    /* 资源限制 */
    unsigned long start_code, end_code, start_data, end_data;
    unsigned long start_brk, brk, start_stack;
    unsigned long arg_start, arg_end, env_start, env_end;

    /* per-cached VMA */
    struct vm_area_struct *vmacache[VMA_VM_CACHE_SIZE]; /* 4 路 LRU 缓存 */
};
```

**关键设计点**：`vmacache` 是一个 4 项的 VMA 指针缓存（参见 `find_vma` 内），命中时省去红黑树查找。**它在 hot path 上让 VMA 查找从 O(log N) 降到 O(1)**。但当 VMA 被拆/合并时需要失效（`vmacache_seqnum` 增 1）。

---

## 4. mmap / munmap / brk / mprotect 源码走读

### 4.1 mmap：用户态到内核态的完整链路

源码路径：`mm/mmap.c::ksys_mmap_pgoff`、`mm/mmap.c::do_mmap`、`mm/util.c::kmm_mmap`。

```c
// mm/mmap.c（精简）
SYSCALL_DEFINE6(mmap, unsigned long, addr, unsigned long, len,
                unsigned long, prot, unsigned long, flags,
                unsigned long, fd, unsigned long, off)
{
    // 1. 参数检查
    if (offset_in_page(off)) return -EINVAL;
    if (prot & ~(PROT_READ | PROT_WRITE | PROT_EXEC | PROT_SEM | PROT_GROWSUP | PROT_GROWSDOWN))
        return -EINVAL;

    // 2. flags 转 vma flags
    //    MAP_SHARED  -> VM_SHARED
    //    MAP_ANONYMOUS -> vm_file=NULL
    //    MAP_FIXED   -> 强制覆盖
    //    MAP_GROWSDOWN -> VM_GROWSDOWN
    //    MAP_HUGETLB -> VM_HUGEPAGE

    // 3. 调用 do_mmap
    return ksys_mmap_pgoff(addr, len, prot, flags, fd, off >> PAGE_SHIFT);
}

// mm/mmap.c::do_mmap 是核心
unsigned long do_mmap(struct file *file, unsigned long addr,
                      unsigned long len, unsigned long prot,
                      unsigned long flags, unsigned long pgoff,
                      unsigned long *populate, struct list_head *uf)
{
    // 1. 计算 mmap_base 附近的地址（如果 addr=NULL）
    // 2. 调用 get_unmapped_area() 获取可用区间
    // 3. 调用 mmap_region() 真正插入 VMA
}
```

### 4.2 mmap_region：插入 VMA

源码路径：`mm/mmap.c::mmap_region`、`mm/mmap.c::vma_link`。

```c
// mm/mmap.c::mmap_region（精简）
unsigned long mmap_region(struct file *file, unsigned long addr,
                          unsigned long len, vm_flags_t vm_flags,
                          unsigned long pgoff, struct list_head *uf)
{
    // 1. 找 VMA 空闲区间（如果未指定 addr）
    addr = get_unmapped_area(file, addr, len, pgoff, vm_flags);

    // 2. 调用 file->f_op->mmap()（如果是文件映射）
    //    或 shmem_zero_setup()（如果是匿名 SHARED）
    //    或直接分配（如果是匿名 PRIVATE）

    // 3. vma_link()：同时插入链表 + 红黑树
    vma_link(mm, vma, prev, rb_link, rb_parent);
    // vma_link 内部：
    //   __vma_link_list(mm, vma, prev)  -> 链表
    //   __vma_link_rb(mm, vma, rb_link, rb_parent) -> 红黑树
    //   __vma_link_file(vma) -> 加入 file->f_mapping 的 i_mmap 树

    // 4. 统计计数
    mm->map_count++;
    vm_stat_account(mm, vm_flags, len >> PAGE_SHIFT);

    return addr;
}
```

### 4.3 munmap：拆除 VMA

源码路径：`mm/mmap.c::do_munmap`、`mm/mmap.c::remove_vma`。

```c
// mm/mmap.c::do_munmap（精简）
int do_munmap(struct mm_struct *mm, unsigned long start, size_t len,
              struct list_head *uf)
{
    // 1. find_vma 找到起始 VMA
    // 2. split_vma 把 [start, end] 范围内的 VMA 切成多段
    // 3. detach_vmas_to_be_unmapped 把要删的 VMA 从链表/红黑树拆下
    // 4. unmap_region() 走页表，TLB 失效
    // 5. remove_vma() 释放 vma 结构体

    // 关键：unmap_region 会调 tlb_gather_mmu / tlb_finish_mmu
    // 涉及大量页时（如 100MB），单次 unmap 可达数十 ms
}
```

**稳定性架构师视角**：

- **mmap 大块 + munmap** 比 **mmap 小块 + 多次 munmap** 快 10×——前者单次拆 VMA、单次 TLB flush；后者多次。
- **ARCore/相机**等场景使用 `munmap + mmap` 做"环形 buffer"，如果 chunk size 选错，会反复触发 TLB shootdown，单次可达 5-20ms（详见 [08-实战案例]）。

### 4.4 brk：传统堆管理

源码路径：`mm/brk.c`。

```c
// mm/brk.c（精简）
SYSCALL_DEFINE1(brk, unsigned long, brk)
{
    struct mm_struct *mm = current->mm;
    unsigned long newbrk, oldbrk;

    oldbrk = mm->brk;
    newbrk = PAGE_ALIGN(brk);

    // 1. 检查 RLIMIT_DATA / RLIMIT_AS
    if (brk <= mm->start_brk) goto out;
    if (check_data_rlimit(rlimit(RLIMIT_DATA), newbrk, mm->start_brk, mm->end_data, ...))
        goto out;

    // 2. 扩堆：do_brk_flags 扩展 [heap]
    if (brk > oldbrk) {
        // can_vma_merge 检查能否合并到现有 [heap]
        if (!do_brk_flags(oldbrk, newbrk - oldbrk, 0, mm))
            goto out;
    }
    // 3. 缩堆：do_munmap 缩小 [heap]
    else if (brk < oldbrk) {
        if (!do_munmap(mm, newbrk, oldbrk - newbrk, ...))
            goto out;
    }

    mm->brk = brk;
out:
    return mm->brk;
}
```

**Android 上的特别说明**：bionic scudo 不依赖 brk（AOSP 5.0+ 全面切到 scudo），**所以 Android App 的 brk 在 bionic 初始化期使用**——用于 `pthread_internal_t` 等小对象预分配；运行期 `malloc` / `mmap` 走 scudo，brk 区域大小基本固定。

### 4.5 mprotect：修改权限

源码路径：`mm/mprotect.c`。

```c
// mm/mprotect.c（精简）
SYSCALL_DEFINE3(mprotect, unsigned long, start, size_t, len, unsigned long, prot)
{
    // 1. 找到 start 处的 VMA
    // 2. 沿 VMA 切分（vma = vma_adjust / split_vma）
    // 3. 对切分后的 VMA 设置新 vm_flags、vm_page_prot
    // 4. change_protection 走页表，update PTE
    //    PTE 修改后调 flush_tlb_mm_range
}
```

**稳定性架构师视角**：

- mprotect 经常被 JNI 用作"代码段 W^X"加固——加载时 `PROT_READ`，调用前临时 `PROT_READ|PROT_EXEC`，调用后立即 `PROT_READ`。
- 这种"切换式" mprotect 每次都需要 TLB 失效，单次 1-10ms。如果 JNI 频繁调用（如每帧一次），**累积开销巨大**。

---

## 5. 私有映射 vs 共享映射：COW 触发条件

### 5.1 是什么

每个 VMA 由 `MAP_SHARED` 或 `MAP_PRIVATE` 决定写时的行为：

| 标志 | 写时 | 谁能看到变化 | 典型用途 |
| --- | --- | --- | --- |
| `MAP_PRIVATE` | **COW（Copy-on-Write）**：首次写时复制页 | 只有本进程 | 代码段、数据段、malloc、绝大多数场景 |
| `MAP_SHARED` | 直接写到原页 | 进程间、磁盘文件可见 | IPC、ashmem、gralloc、显式文件映射 |

源码路径：`include/linux/mm.h::MAP_SHARED`、`mm/memory.c`。

### 5.2 为什么需要 COW

传统 fork() 需要把父进程全部用户态内存复制一份，**对 1GB 进程就是 1GB 复制 + 1GB 物理内存**，而 99% 的 fork 后立刻 exec。COW 把"复制"延迟到首次写：

- 父进程 fork 子进程：子进程共享父的所有页（只读），但 PTE 标记为只读
- 子进程 exec：被共享的页从未被写过 → 直接丢弃（unmap），无需复制
- 子进程写：触发 #PF（写保护）→ 内核分配新物理页 → 复制旧页内容 → 子 PTE 指向新页 → 子进程可写

### 5.3 COW 触发路径源码

源码路径：`mm/memory.c::__handle_mm_fault`、`mm/memory.c::wp_page_copy`。

```c
// mm/memory.c::wp_page_copy（精简）
static vm_fault_t wp_page_copy(struct vm_fault *vmf)
{
    // 1. 分配新物理页
    new_page = alloc_page_vma(GFP_HIGHUSER_MOVABLE, vma, vmf->address);

    // 2. 复制旧页内容
    copy_user_highpage(new_page, vmf->page, vmf->address, vma);

    // 3. 设置新页的 mapcount/_mapcount、加入 LRU
    __SetPageUptodate(new_page);
    lru_cache_add(new_page);

    // 4. PTE 切换到新页（保留 COW 标记为 0，可写）
    set_pte_at_notify(mm, vmf->address, vmf->pte, new_pte);

    // 5. 旧页 refcount -1
    put_page(vmf->page);
}
```

### 5.4 COW 触发的具体条件

COW 在以下**任意一种**情况下触发：

1. `MAP_PRIVATE` 区域首次**写**（PF_PROT 异常 + VM_WRITE）。
2. `fork()` 后子进程**写**任何被父标记只读的页。
3. `MAP_SHARED` 区域但底层是文件且文件系统不支持共享写（如 ext4 普通文件，**实际 MAP_PRIVATE 行为**）。

**稳定性架构师视角**：

- **冷启动性能杀手之一**：Zygote fork 出的子进程，**首次访问 Java 堆、native 堆、.so 数据段时都会触发 COW**。这就是为什么"冷启动时间 = TLB warmup + COW 时间 + ART 初始化时间"。
- **COW 是 RSS 增长的隐藏原因**：启动初期 PSS 很低（共享），10 秒后 PSS 接近 RSS（COW 完成）。**不要在启动 1 秒内用 PSS 判断内存健康**。

### 5.5 fork 与 vma 复制

源码路径：`mm/fork.c::dup_mmap`。

```c
// mm/fork.c（精简）
static int dup_mmap(struct mm_struct *mm, struct mm_struct *oldmm)
{
    // 1. 复制 mm->mmap 链表
    // 2. 对每个 vma 调用 dup_vma()
    // 3. dup_vma 内部：
    //    - 分配新 vma
    //    - 复制 flags / file / pgoff / ops
    //    - **关键：copy_vma(&vma->vm_flags)** → 检测是否可合并
    //    - 共享映射复制 PTE，私有映射标记 PTE 只读（COW）
}
```

**Android 上的 fork 路径**：

- `app_process` → Zygote（init 阶段启动）→ `Zygote.forkAndSpecialize()` → fork 子进程
- 子进程 exec 后加载 dex / oat，开始 COW

---

## 6. VMA 合并与拆分：can_vma_merge 的判断逻辑

### 6.1 为什么需要合并

相邻的 VMA 如果属性完全相同，可以合并为一条 VMA。**合并的收益**：

1. **`find_vma()` 树节点数减少** → O(log N) 更小。
2. **`/proc/pid/maps` 行数减少** → 用户可读性 + 排查便利。
3. **vm_stat_account 统计更准确** → RSS 计算更高效。

合并的判断由 `can_vma_merge()` 决定，所有属性必须严格相等。

### 6.2 can_vma_merge 源码

源码路径：`mm/mmap.c::can_vma_merge`、`include/linux/mm.h`。

```c
// mm/mmap.c::can_vma_merge（精简）
bool can_vma_merge(struct vm_area_struct *vma, unsigned long addr,
                   unsigned long end, unsigned long vm_flags,
                   struct file *file, unsigned long pgoff,
                   struct vm_userfaultfd_ctx vm_userfaultfd_ctx,
                   struct anon_vma *anon_vma)
{
    // 1. 地址必须相邻
    if (vma->vm_end != addr)
        return false;

    // 2. flags 必须严格相等（含 VM_READ/WRITE/EXEC/SHARED 等所有位）
    if (!vma_flags_compatible(vma, vm_flags))
        return false;
    // vma_flags_compatible 内部逐位对比：
    //   VM_READ | VM_WRITE | VM_EXEC | VM_SHARED
    //   VM_MAYREAD | VM_MAYWRITE | VM_MAYEXEC | VM_MAYSHARE
    //   VM_DONTCOPY | VM_DONTEXPAND | VM_ACCOUNT | VM_NORESERVE
    //   VM_HUGEPAGE | VM_NOHUGEPAGE | VM_MERGEABLE
    //   VM_DROPPABLE | VM_WIPEONFORK | VM_DONTDUMP
    //   VM_LOCKED | VM_SYNC
    //   VM_PFNMAP | VM_MIXEDMAP | VM_IO
    //   anon_vma 必须相同（私有匿名）或都是文件映射

    // 3. 文件映射：file 指针 + pgoff 必须连续
    if (file) {
        if (vma->vm_file != file)
            return false;
        if (vma->vm_pgoff + vma_pages(vma) != pgoff)
            return false;
    } else {
        // 匿名映射：anon_vma 必须相同
        if (anon_vma != vma->anon_vma)
            return false;
    }

    return true;
}
```

### 6.3 拆分：split_vma

源码路径：`mm/mmap.c::split_vma`。

```c
// mm/mmap.c::split_vma（精简）
int split_vma(struct mm_struct *mm, struct vm_area_struct *vma,
              unsigned long addr, int new_below)
{
    struct vm_area_struct *new;
    int err = -ENOMEM;

    // 1. 分配新 vma
    new = kmem_cache_alloc(vm_area_cachep, GFP_KERNEL_ACCOUNT);
    if (!new) goto out;

    // 2. 复制旧 vma 的属性
    *new = *vma;  // 大块复制，~232B

    // 3. 调整地址
    if (new_below) {
        new->vm_end = addr;
        vma->vm_start = addr;
    } else {
        new->vm_start = addr;
        vma->vm_end = addr;
    }

    // 4. 插入 vma
    vma_link(mm, new, ...);

    // 5. 如果是文件映射，分页表也要拆
    if (new->vm_file)
        vma_adjust_file_links(new);
}
```

### 6.4 拆分的稳定性代价

**拆分触发场景**：

1. `munmap()` 中间一段
2. `mprotect()` 修改中段权限
3. `mremap()` 中段搬迁
4. `madvise(MADV_DONTNEED)` 单页

**代价清单**：

- **结构体分配**：每次 `kmem_cache_alloc(vm_area_cachep)`，高频时 SLUB 缓存命中率下降。
- **红黑树重平衡**：拆/合可能触发多次旋转。
- **页表操作**：文件映射拆 VMA 还要拆页表项（`vma_adjust_file_links`）。
- **TLB**：拆分伴随 `tlb_finish_mmu`。

**经验值**：连续 `munmap` 中间一段 1MB，触发 2 次拆 VMA + 1 次红黑树旋转 + 256 次 TLB flush，单次耗时 50-300μs。

### 6.5 can_vma_merge 实战分析

**典型合并失败场景**：

```c
// 场景：连续两次 mmap，但权限不同
void* a = mmap(NULL, 0x1000, PROT_READ|PROT_WRITE,
               MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);  // VM_READ|VM_WRITE
void* b = mmap(NULL, 0x1000, PROT_READ,
               MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);  // VM_READ
// can_vma_merge 返回 false（VM_WRITE 位不同）
// → 产生 2 个独立 VMA

// 场景：连续两次 mmap，但 anon_vma 不同（不可能发生，anon_vma 是按 mm_struct 共享）
// 实际场景：fork 后父子进程对同一区间，can_vma_merge 会因 anon_vma 不通（if CONFIG_PER_VMA_LOCK）失败
```

### 6.6 vma_merge：尝试合并

源码路径：`mm/mmap.c::vma_merge`。

```c
// mm/mmap.c::vma_merge（精简）
struct vm_area_struct *vma_merge(struct mm_struct *mm,
            struct vm_area_struct *prev, unsigned long addr,
            unsigned long end, unsigned long vm_flags,
            struct file *file, unsigned long pgoff,
            struct mempolicy *policy,
            struct vm_userfaultfd_ctx vm_userfaultfd_ctx,
            struct anon_vma *anon_vma)
{
    // 1. 尝试与 prev 合并（addr 必须 == prev->vm_end）
    // 2. 尝试与 next 合并（end 必须 == next->vm_start）
    // 3. 尝试 prev + next + 当前一起合并
    // 4. 任何一条命中都返回合并后的 VMA（不创建新 VMA）
}
```

**稳定性架构师视角**：

- 高频 mmap（如日志缓冲、JNI 注册）应尽量保持权限一致，让内核合并。
- 不要在 mmap 之间穿插 mprotect，会强制拆 VMA。

---

## 7. 风险地图：四大典型故障模式

### 7.1 风险速查表（架构师 5 秒定位）

| 风险类型 | 触发条件 | 日志关键字 | 排查入口 | 修复路径 |
| --- | --- | --- | --- | --- |
| **VMA 数量爆炸** | mmap 调用过碎 / 泄漏 | `mmap` 在 `systrace` 中高频出现；`maps` 行数 > 3000 | `/proc/pid/maps` 行数；`ftrace mm:vm_area_alloc` | 合并 mmap 调用、加 cache；检查 munmap |
| **mmap 泄漏** | mmap 后忘记 munmap | `total_vm` 持续增长；`RLIMIT_AS` 触顶 `EACCES` | `dumpsys meminfo` 的 `TOTAL PSS` 趋势；`/proc/pid/status.VmRSS` | 审计 JNI/Native 代码路径 |
| **JNI 局部引用表溢出** | JNI 函数未释放 `NewLocalRef` | `JNI ERROR (app bug): local reference table overflow` | logcat | 改用 `NewGlobalRef` 或及时 `DeleteLocalRef` |
| **ASLR 失效** | vdso 偏移被固定；setarch 关闭 ASLR | `[vdso]` 地址每次启动相同 | `cat /proc/sys/kernel/randomize_va_space` | 确认 `2`；避免 `personality(ADDR_NO_RANDOMIZE)` |
| **栈爆栈** | 线程栈递归过深 | `stack overflow`；`SIGSEGV` 在栈 VMA | `dumpsys meminfo` 的 `Stack`；`getrlimit(RLIMIT_STACK)` | 改 `pthread_attr_setstacksize` |
| **mmap 巨块阻塞** | 单次 mmap > 256MB | `futex` 长时间 blocked；`mmap_region` 慢路径 | `dumpsys gfxinfo`；`simpleperf record -e mm:vm_area_*` | 改用 `madvise(MADV_HUGEPAGE)` 分块 |
| **共享库未去重** | 不同进程加载同一 .so 但路径不同 | PSS > RSS 1.2× | `/proc/<pid>/smaps` 的 `Shared_Dirty` | 使用 `prelink`；检查 `LD_LIBRARY_PATH` |

### 7.2 风险一：VMA 数量爆炸

**症状**：App 启动慢、丢帧；`/proc/pid/maps` 行数 > 3000。

**根因**：

1. **过度细粒度的 mmap**：JNI 把每个小块用 mmap 单独分配，每次都产生一个 VMA。
2. **动态库过多**：典型反例是 Google Play Services + 微信 + 抖音同时拉起，每个都带数十个 .so。
3. **未合并的内存映射**：连续 mmap 但 flags 不同，被内核拒绝合并。

**诊断命令**：

```bash
# 查看当前 VMA 数量
cat /proc/$(pidof com.example.app)/maps | wc -l

# 查看 VMA 类型分布
cat /proc/$(pidof com.example.app)/maps | awk '{print $6}' | sort | uniq -c | sort -rn | head

# Perfetto 追踪
simpleperf record -e mm:vm_area_alloc -e mm:vm_area_free --app com.example.app
```

**典型经验值**：

| 场景 | VMA 数量 | 冷启动时间 |
| --- | --- | --- |
| 简单 Activity App | 200-400 | 400-700ms |
| 普通 App（30 个 .so） | 800-1500 | 800-1500ms |
| 重型 App（浏览器、地图） | 2000-4000 | 1500-3000ms |
| 病态（VMA 爆炸） | > 5000 | > 3500ms |

### 7.3 风险二：mmap 泄漏

**症状**：`dumpsys meminfo` 中 `TOTAL PSS` 单调增长；`maps` 中 `[anon]` 段持续出现且不释放。

**典型场景**：

1. **JNI ByteBuffer**：`NewDirectByteBuffer` 分配 native 内存，忘了 `DeleteLocalRef`。
2. **ASHMEM / ION**：Gralloc 缓冲区在 `munmap` 后文件描述符未 close。
3. **动态库 dlopen 不 dlclose**：某些 SDK 在每个 Activity 创建时 dlopen 一个 .so，Activity 销毁时不 dlclose，导致 `.so` 的全部 VMA 永远不释放。

**诊断命令**：

```bash
# 1. 抓 maps 快照
adb shell cat /proc/$(pidof com.example.app)/maps > maps_t0.txt
# ... 等 5 分钟 ...
adb shell cat /proc/$(pidof com.example.app)/maps > maps_t1.txt
diff maps_t0.txt maps_t1.txt

# 2. 看 [anon] 段累计大小
cat /proc/$(pidof com.example.app)/maps | awk '{print $2}' | grep -E '\[anon' | wc -l

# 3. 抓 native 堆分配
adb shell setprop libc.debug.malloc.program com.example.app
adb shell setprop libc.debug.malloc.options backtrace
```

### 7.4 风险三：JNI 局部引用表溢出

**症状**：logcat 出现 `JNI ERROR (app bug): local reference table overflow`，随后进程被 SIGABRT。

**原理**：

- JNI 规范要求每个 JNIEnv 维护一个局部引用表（local reference table），上限默认 **512 项**（Android 14 ART 改为动态上限 65536，但单个 JNI 函数的栈仍按 512 检查）。
- 每次 `NewLocalRef`、`FindClass`、`NewObject`、`GetObjectClass` 都会占用一项。
- 表满时 → JNI 抛 `JNI ERROR` → ART 触发 `__android_log_print(ANDROID_LOG_FATAL, ...)` → abort。

**源码路径**：`art/runtime/jni/jni_internal.cc::NewLocalRef`、`art/runtime/jni/ref_table.cc::Add`。

```c
// art/runtime/jni/ref_table.cc::Add（精简）
bool ReferenceTable::Add(ObjPtr<mirror::Object> obj)
{
    if (size_ >= max_size_) {  // max_size_ 默认 512
        LOG(FATAL) << "JNI ERROR (app bug): local reference table overflow";
        return false;
    }
    ...
}
```

**修复模式**：

1. **及时 `DeleteLocalRef`**：每个 `NewLocalRef` 都要配对一个 `DeleteLocalRef`，尤其在循环中。
2. **改用全局引用**：`NewGlobalRef` 不占用局部表，但需要 `DeleteGlobalRef`。
3. **使用 `PopLocalFrame` / `PushLocalFrame`**：批量管理局部引用。

### 7.5 风险四：ASLR 失效

**症状**：连续多次启动 App，`/proc/pid/maps` 中 `[vdso]` 和 `libc.so` 的地址不变。

**根因**：

1. `setarch x86_64 -R ./app` 或 `personality(ADDR_NO_RANDOMIZE)` 关闭 ASLR。
2. 32 位 App 在 32-bit 兼容模式下 ASLR 仅 8-bit（256 种），远低于 64-bit 28-bit。
3. 内核参数 `randomize_va_space=0`（仅调试用）。

**稳定性架构师视角**：

- ASLR 失效不直接引起稳定性问题，但**显著扩大攻击面**——攻击者可以通过多次启动 PoC 找到 gadget。
- 对 App 而言，如果发现某次启动 vdso 地址和上次完全相同，应上报安全团队。

### 7.6 风险五（额外）：大块 mmap 阻塞 TLB

**症状**：单次 `mmap(2GB)` 后，主线程 stall 100-500ms。

**根因**：

- `mmap_region` 内部要更新 PTE，2GB = 524288 个 4KB 页 = 524288 次 PTE 写。
- 即使走大页（`MAP_HUGETLB` 2MB），也要 1024 次。
- PTE 修改伴随 TLB 失效，单次 `tlb_flush_mmu` 可达数十 ms。

**修复模式**：

- 分块 mmap（每次 ≤ 64MB）。
- 使用 `madvise(MADV_HUGEPAGE)` 提示透明大页。
- 后台预分配而非主线程分配。

---

## 8. 实战案例：App 启动时 VMA 异常膨胀导致冷启动慢 30%

### 8.1 现象（典型模式）

某 App（脱敏代号 `ShopApp`）在 Android 13 升级后，冷启动时间从 **900ms → 1200ms**（+30%）。bugreport 中观察到：

- App 启动后 2 秒内 `/proc/pid/maps` 行数 **2800 → 4500**
- `dumpsys gfxinfo` 的 `Profile drawing in` 阶段耗时从 120ms → 280ms

### 8.2 分析思路

**Step 1：抓 maps 快照对比版本**

```bash
adb shell am force-stop com.shop.app
adb shell am start -n com.shop.app/.MainActivity
sleep 2
adb shell cat /proc/$(pidof com.shop.app)/maps > /tmp/maps_v14.txt
```

观察到：

- 2800 → 4500 的增长主要集中在 `[anon]` 段
- 大量 4KB 大小的小段

**Step 2：抓 mmap 调用栈**

```bash
# 使用 simpleperf 抓 mm:vm_area_alloc 事件
adb shell simpleperf record -e mm:vm_area_alloc --app com.shop.app -o /data/local/tmp/perf.data
adb shell simpleperf report -i /data/local/tmp/perf.data
```

观察到热点：

```
99.4%  [kernel]  vm_area_alloc
        ↳ art::gc::Heap::ConcurrentCopying::Initialize  (新 GC 模式)
        ↳ art::Class::AllocObject  (Java 对象)
        ↳ com.shop.app.sdks.XxxSDK::init  (SDK 初始化)
        ↳ Application.onCreate
```

**Step 3：定位 SDK**

- 阅读 SDK 文档，发现新版 SDK 在 `attachBaseContext` 中为每个 `Activity` 创建一个 `NativeBuffer`，每个用 `mmap(4KB, MAP_ANONYMOUS)` 分配。
- SDK 内部维护 `mBuffers` 列表，但 Activity destroy 时只清空列表，不 munmap 内存。

**Step 4：确认是 VMA 膨胀**

| 指标 | 旧版本 | 新版本 | 增量 |
| --- | --- | --- | --- |
| VMA 数（启动后 2s） | 2800 | 4500 | +1700 |
| `[anon:4KB]` 数 | 12 | 1700 | +1688 |
| 冷启动 PSS (MB) | 180 | 220 | +40 |
| 冷启动时间 (ms) | 900 | 1200 | +300 |

**Step 5：根因**

- SDK 为每个 Activity 创建 4KB native buffer，启动时一次性预创建 ~1700 个 Activity（在某些场景下）。
- 每个 4KB buffer = 1 个 VMA，导致 VMA 数量爆炸。
- 每个 Activity destroy 时只清空列表不 munmap，泄漏的 VMA 不会被回收。
- VMA 膨胀导致 `find_vma()` 树查找变慢，每次 ART 分配新对象都要 `find_vma` 检查，累积 200ms。

### 8.3 修复方案

1. **短期**：
   - 让 SDK 提供方改为 `munmap` 释放不再使用的 buffer。
   - 在自己 App 内做 `PackageInfo` 检查，对有问题 SDK 版本降级。
   - 设置 `setrlimit(RLIMIT_AS)` 上限，超过即触发进程自杀 + 报警。

2. **中期**：
   - 引入 `librangex` 或自研 buffer pool，把小 buffer 合并到少量 mmap 大块。
   - 用 `madvise(MADV_DONTNEED)` 主动释放不再使用的内存（不删除 VMA，但释放物理页）。

3. **长期**：
   - 推动 SDK 提供方改用 `scudo` / `jemalloc` 而非裸 mmap。
   - 接入 `simpleperf` + 自动化回归，监控 VMA 数量趋势。

### 8.4 经验沉淀

| 教训 | 落地措施 |
| --- | --- |
| VMA 数量是冷启动的隐藏瓶颈 | CI 增加 `/proc/pid/maps` 行数监控，> 3000 即告警 |
| `[anon:4KB]` 大量出现 = 有人在裸 mmap | Code Review 禁用裸 mmap，统一走 malloc |
| SDK 升级可能引入 VMA 爆炸 | 第三方 SDK 升级前要求性能基线对比 |

---

## 9. 总结：架构师视角的 5 条 Takeaway

1. **VMA 是进程的"虚拟地址账本"，任何 mmap/munmap/brk/mprotect 都是账本的一笔交易**。理解这张账本就能解释 80% 的"内存去哪了"问题。第一现场永远是 `/proc/pid/maps` + `smaps`。

2. **VMA 数量膨胀是冷启动的隐形杀手**。N=3000 时 `find_vma` 已能观测到 1-3μs 单次开销；N=5000 时 ART 分配一个 Java 对象就要多走 200-500μs 红黑树路径。**冷启动优化不只是 ART / IO，VMA 治理同样关键**。

3. **COW 是 RSS 增长的隐藏原因**。Zygote fork → 子进程 COW 是冷启动期 PSS 偏低的根本原因，**不要在启动 1 秒内用 PSS 判断内存健康**。10 秒后 PSS 才接近真实水位。

4. **共享映射与私有映射的边界 = 进程隔离的边界**。`MAP_PRIVATE` 配合 fork 是 Linux 进程模型的基石；任何把"进程间共享"做在 `MAP_SHARED` 上的设计都要警惕**写入放大**（一个写入触发 N 个 PTE 修改）。

5. **JNI 局部引用表 512 项是 JNI 编程的硬约束**。所有 JNI 代码都要按"用完即释放"原则写；长期持有的引用必须 `NewGlobalRef`。**不释放局部引用 = 直接 abort**，且 ART 14 才把这个上限扩大到 65536（仍按函数 512 检查）。

### 排查路径速查（架构师 5 秒）

```
"App 内存异常" 
    ↓
/proc/pid/maps 行数？→ > 3000 = VMA 膨胀
    ↓
[dump]/proc/pid/smaps_rollup → 按类型看 PSS 分布
    ↓
dumpsys meminfo → TOTAL PSS / Heap / Stack / Graphics
    ↓
定位是 Java 堆 / Native 堆 / VMA / Graphics 哪一类
    ↓
对应到本系列的 03 (ART GC)、04 (Native malloc)、08 (回收抖动)
```

---

## 附录 A：核心源码路径索引

| 文件 | 完整路径 | 说明 |
| --- | --- | --- |
| vm_area_struct 定义 | `include/linux/mm_types.h` | VMA 主结构体；链表/红黑树嵌入 |
| vm_flags 定义 | `include/linux/mm.h` | VM_READ/WRITE/EXEC/SHARED/GROWSDOWN 等所有位 |
| mmap 系统调用 | `mm/mmap.c::ksys_mmap_pgoff` / `do_mmap` | mmap 主入口 |
| mmap_region | `mm/mmap.c::mmap_region` | VMA 插入流程 |
| munmap | `mm/mmap.c::do_munmap` | 拆除 VMA |
| brk | `mm/brk.c::SYSCALL_DEFINE1(brk, ...)` | brk 区域管理 |
| mprotect | `mm/mprotect.c::SYSCALL_DEFINE3(mprotect, ...)` | 修改 VMA 权限 |
| vma_link | `mm/mmap.c::vma_link` | 链表 + 红黑树 + file 三处插入 |
| can_vma_merge | `mm/mmap.c::can_vma_merge` | VMA 合并判断 |
| vma_merge | `mm/mmap.c::vma_merge` | 实际合并动作 |
| split_vma | `mm/mmap.c::split_vma` | VMA 拆分 |
| find_vma | `mm/mmap.c::find_vma` | 红黑树查找（含 vmacache 优化） |
| dup_mmap | `mm/fork.c::dup_mmap` | fork 时 VMA 复制 |
| wp_page_copy | `mm/memory.c::wp_page_copy` | COW 写时复制 |
| do_brk_flags | `mm/brk.c::do_brk_flags` | brk 区域扩展 |
| /proc/pid/maps 输出 | `fs/proc/task_mmu.c::show_vma_header_prefix` | maps 行格式 |
| /proc/pid/smaps 输出 | `fs/proc/task_mmu.c::smaps_show` | smaps 扩展字段 |
| /proc/pid/smaps_rollup | `fs/proc/task_mmu.c::show_smaps_rollup` | smaps_rollup 聚合 |
| /proc/pid/status 字段 | `fs/proc/task_mmu.c::task_mem` | VmRSS / VmSize / VmData |
| 32 位兼容 | `arch/arm64/kernel/vdso.c` | arm64 vdso 初始化 |
| ELF 加载 | `fs/binfmt_elf.c::load_elf_binary` | exec 时创建代码段 VMA |
| 子线程栈 | `mm/mmap.c::__install_special_mapping` | `clone` 时创建线程栈 |

## 附录 B：关键命令与 sysfs 节点速查

| 命令 | 路径 | 用途 |
| --- | --- | --- |
| `cat /proc/pid/maps` | 内核 | 全量 VMA 列表 |
| `cat /proc/pid/smaps` | 内核 | 全量 VMA + RSS/PSS/Shared |
| `cat /proc/pid/smaps_rollup` | 内核 | VMA 按类别聚合 |
| `cat /proc/pid/status` | 内核 | VmRSS / VmSize / VmData / VmStk |
| `cat /proc/pid/statm` | 内核 | 单行统计：`size resident shared text lib data dt` |
| `cat /proc/sys/vm/max_map_count` | 内核 | 单进程最大 VMA 数（默认 65530） |
| `getrlimit(RLIMIT_AS)` | libc | 进程虚拟地址上限 |
| `getrlimit(RLIMIT_DATA)` | libc | data 段上限（影响 brk） |
| `getrlimit(RLIMIT_STACK)` | libc | 主线程栈上限 |
| `dumpsys meminfo` | Android | TOTAL PSS / Heap / Graphics / Stack |
| `procrank` | Android | 系统级 TopN |
| `simpleperf record -e mm:*` | Android | mm 事件追踪 |

## 附录 C：本文档涉及的常量与默认值

| 常量 | 默认值 | 含义 | 来源 |
| --- | --- | --- | --- |
| `PAGE_SIZE` | 4096 (arm64) | 页大小 | `arch/arm64/include/asm/page.h` |
| `TASK_SIZE` | `0x0000_8000_0000_0000` | 用户地址上限（39-bit） | `arch/arm64/include/asm/memory.h` |
| `RLIMIT_AS` | `RLIM_INFINITY`（Android 默认） | 虚拟地址上限 | `prlimit(2)` |
| `RLIMIT_DATA` | `RLIM_INFINITY`（Android 默认） | data 段上限 | `prlimit(2)` |
| `STACK_TOP` | `TASK_SIZE - PAGE_SIZE` | 主线程栈最高地址 | `arch/arm64/include/asm/processor.h` |
| 默认线程栈 | 8 MB | `pthread_create` 默认 | `bionic/libc/bionic/pthread_create.cpp` |
| `MAP_PRIVATE` | — | 私有映射标志 | `asm-generic/mman-common.h` |
| `MAP_SHARED` | — | 共享映射标志 | 同上 |
| `JNI 局部引用表上限` | 512（旧）/ 65536（新） | JNI 函数内局部引用上限 | `art/runtime/jni/ref_table.cc` |
| `max_map_count` | 65530 | 单进程最大 VMA 数 | `fs/proc/proc_sysctl.c` |
| `mmap_base` | `STACK_TOP - 128 MB - ASLR_random` | mmap 区起始 | `mm/mmap.c::setup_new_exec` |

---

## 篇尾衔接

下一篇 [03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md) 将深入 Java 堆的分代、GC 算法（CC vs CMS）、JNI 引用表与 Java 堆的边界，以及内存压力下的 GC 行为切换。VMA 是"虚拟地址账本"，ART 堆是在账本上"开了个专项账户"——下一篇将讲这个专项账户怎么管。

---

## 跨模块引用

- 上一篇：[01-内存系统总览：从进程视角到硬件的完整链路](01-内存系统总览：从进程视角到硬件的完整链路.md) — 讲了五层架构与"一个 byte 的旅程"，本篇是该旅程在 **mm/mmap.c** 的着陆点。
- 关联文章：[Window 02-Window 的创建与添加](../01-Mechanism/Framework/Window/02-Window的创建与添加.md) — Window Token 创建时 binder 缓冲区扩张，间接导致 mmap 区的 `[anon]` 增长，可与本篇 7.3 节 mmap 泄漏结合看。
- 同篇章：[03-ART 堆内存与 GC 全景](03-ART 堆内存与 GC 全景.md) — ART 堆在 VMA 视角是一个 `[anon:dalvik-main space]` 段，下一篇深入其内部机制。
- 同篇章：[04-Native 堆内存与分配器（AOSP 14）](04-Native 堆内存与分配器（AOSP 14）.md) — bionic scudo 几乎全部使用 `mmap` 分配，是本篇 7.3 mmap 泄漏的最大单一来源。