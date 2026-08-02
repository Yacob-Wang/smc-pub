# 面向稳定性的 Native Crash 深度解析系列

## 为什么要写这个系列

Native Crash (NE) 是 Android 稳定性的"深水炸弹"。与 Java Exception 不同，NE 发生在 C/C++ 层，没有虚拟机的安全网兜底——**一旦崩溃，进程直接死亡，没有 try-catch 能救**。

更棘手的是，NE 的排查难度远高于 JE：堆栈可能全是十六进制地址、符号可能被剥离、崩溃现场（Tombstone）信息需要结合寄存器状态和内存映射才能解读。

本系列的目标：**让你拿到任何一份 Tombstone，都能在 5 分钟内判断出信号类型、崩溃模块、根因方向，并知道用什么工具深入排查。**

## 系列设计思路

```
Native Crash 是什么？（定位）
    ↓
它在 Android 系统中的崩溃处理链路是什么？（边界与交互）
    ↓
信号如何产生、传递、捕获？Tombstone 如何生成？（核心机制）
    ↓
7 种信号各自的典型场景和特征是什么？（风险地图）
    ↓
如何读 Tombstone？如何用 ASan？如何建 APM？（诊断与治理）
```

---

## 第一篇章：建立全局观（1 篇）

> 核心问题：Native Crash 是什么？和 Java Crash 有什么本质区别？崩溃处理的完整链路是怎样的？

### [01-Native Crash 总览：稳定性架构师的全局视角](01-NativeCrash总览.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. NE 是什么** | Native Crash 的定义；与 Java Exception 的本质区别（信号 vs 异常、进程死亡 vs 可捕获） | — | 理解为什么 NE 比 JE 更致命 |
| **2. 7 种致命信号全景** | SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL / SIGSYS / SIGTRAP 的含义、触发条件、si_code 分类 | `kernel/include/uapi/asm-generic/signal.h` | 快速识别信号类型的"速查表" |
| **3. 崩溃处理全链路** | 硬件异常 → 内核信号产生 → 进程信号传递 → debuggerd_handler → crash_dump → Tombstone → DropBox → 上报的完整流程图 | `system/core/debuggerd/`、`bionic/linker/` | 理解每个环节可能丢失信息的风险 |
| **4. NE 在各层的分布** | App NDK 代码 / ART 内部（libart.so）/ System Libraries（libutils, libbinder）/ Vendor HAL / Kernel 的 NE 占比和特征 | — | NE 归因的第一步：判断是谁的锅 |
| **5. 与 ART 的交互** | ART 的 FaultHandler（隐式空指针检查）和 sigchain（信号链管理）如何"截获"部分信号，将 SIGSEGV 转化为 NullPointerException | `art/runtime/fault_handler.cc`、`art/sigchain/sigchain.cc` | APM 框架与 ART 信号处理冲突的根因 |
| **6. 核心源码目录** | debuggerd、bionic/linker、kernel/signal、libunwindstack 的职责概览 | 多个目录 | 排查 NE 时的"导航地图" |

---

## 第二篇章：核心机制深潜（4 篇）

> 核心问题：信号如何产生、传递、捕获？Tombstone 是怎么生成的？堆栈是怎么回溯出来的？

### [02-Linux 信号机制：从硬件异常到用户态回调](02-Linux信号机制.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. 信号是什么** | 信号的本质（进程间异步通知机制）；标准信号 vs 实时信号；信号的生命周期（产生 → 挂起 → 传递 → 处理） | — | 建立信号的概念模型 |
| **2. 信号的产生** | 三种来源：硬件异常（MMU fault → SIGSEGV）、软件触发（`abort()` → SIGABRT、`kill()` → 任意信号）、内核事件 | `kernel/signal.c`（`send_signal`） | 不同来源的信号，排查方向完全不同 |
| **3. 信号的传递** | 内核 `do_signal()` → `handle_signal()` 的完整路径；如何从内核态切换到用户态执行 Signal Handler | `arch/arm64/kernel/signal.c` | 理解为什么信号处理函数在"特殊的栈"上运行 |
| **4. 信号的处理** | `sigaction` 注册机制；`siginfo_t` 结构体（si_signo / si_code / si_addr）；Signal Handler 的栈帧（sigframe） | `kernel/signal.c`、`bionic/libc/bionic/sigaction.cpp` | `si_addr` 就是 Tombstone 中的 fault addr |
| **5. 信号掩码与多线程** | `sigprocmask` / `pthread_sigmask`；为什么多线程程序的信号行为如此复杂（信号可能被任意线程接收） | `kernel/signal.c` | 多线程 NE 的 Tombstone 中"崩溃线程"可能不是真正的罪魁祸首 |
| **6. Android 的 sigchain** | ART 如何通过 sigchain 链式管理多个 Signal Handler；`sigchain_action` 的链表结构 | `art/sigchain/sigchain.cc` | APM 框架注册 Signal Handler 时必须通过 sigchain，否则会被 ART 覆盖 |

### [03-内存管理与保护：SIGSEGV 背后的真相](03-内存管理与保护.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. 虚拟内存与 MMU** | 页表、MMU、TLB 的协作关系；虚拟地址 → 物理地址的翻译过程 | `arch/arm64/mm/` | 理解 SIGSEGV 的硬件本质 |
| **2. Page Fault 的三种结局** | 正常缺页（Demand Paging）、COW 缺页（fork 后写入）、非法访问（→ SIGSEGV） | `kernel/mm/memory.c`（`handle_mm_fault`） | 区分"正常"的 page fault 和"致命"的 page fault |
| **3. mmap 与内存映射** | 文件映射 vs 匿名映射；权限控制（PROT_READ/WRITE/EXEC）；映射与 VMA 的关系 | `kernel/mm/mmap.c` | mmap 文件被截断 → SIGBUS；权限不足 → SIGSEGV(SEGV_ACCERR) |
| **4. 栈的结构与保护** | 线程栈的布局（Guard Page / Stack / TLS）；栈溢出如何触发 SIGSEGV | `bionic/libc/bionic/pthread_create.cpp` | 递归过深 / 局部变量过大导致的栈溢出 |
| **5. 堆的结构与分配器** | Scudo（Android 11+ 默认）/ jemalloc 的架构；堆元数据（chunk header）损坏如何被检测 → SIGABRT | `bionic/libc/bionic/malloc_common.cpp` | Double-Free / Use-After-Free / Heap Buffer Overflow 的内存层面原理 |
| **6. MTE（Memory Tagging）** | ARM v8.5+ 硬件内存标签；Android 12+ 的 MTE 支持；如何零开销检测内存错误 | `bionic/libc/bionic/scudo_wrapper.cpp` | 未来内存安全的终极方案 |

### [04-debuggerd 与 Tombstone：Android 的崩溃捕获架构](04-debuggerd与Tombstone.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. debuggerd 是什么** | Android 独有的崩溃捕获守护进程；与 Linux coredump 的区别；为什么 Android 选择 Tombstone 而非 core 文件 | — | 理解 Android NE 处理的设计哲学 |
| **2. 进程内 Signal Handler** | `debuggerd_handler` 的注册时机（linker 初始化阶段）；首次接收信号后的处理逻辑（clone 子线程 → 通知 crash_dump） | `bionic/linker/debuggerd_handler.cpp` | 为什么 Signal Handler 中不能调用 malloc 等 async-signal-unsafe 函数 |
| **3. crash_dump 进程** | crash_dump 如何通过 `ptrace` 附加崩溃进程；读取寄存器状态、内存内容；调用 libunwindstack 回溯堆栈 | `system/core/debuggerd/crash_dump.cpp` | ptrace 失败时 Tombstone 信息不完整的原因 |
| **4. Tombstone 生成** | Tombstone 文件的完整结构（Header / Signal Info / Registers / Backtrace / Memory Maps / Memory Near / Threads）；Proto 格式（Android 12+） | `system/core/debuggerd/libdebuggerd/tombstone.cpp` | 逐段解读 Tombstone 的前置知识 |
| **5. 日志与上报** | Tombstone 写入 `/data/tombstones/`；同步写入 logd（logcat 中的 `DEBUG` tag）；通过 DropBoxManager 上报到系统 | `system/core/debuggerd/` | 为什么有时 logcat 有 NE 日志但 Tombstone 文件不存在 |

### [05-栈回溯与符号化：从地址到代码行](05-栈回溯与符号化.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. 栈回溯是什么** | 从崩溃现场的 PC/SP/FP 寄存器，回溯出完整的函数调用链 | — | Tombstone 中 backtrace 的来源 |
| **2. FP-based 回溯** | Frame Pointer 链表遍历（`FP → 上一帧 FP → ...`）；为什么 `-fomit-frame-pointer` 会破坏回溯 | — | 部分 so 库堆栈断裂的原因 |
| **3. DWARF CFI 回溯** | `.eh_frame` / `.debug_frame` 段的作用；CFI（Call Frame Information）指令如何描述寄存器保存规则 | `system/unwinding/libunwindstack/` | 为什么 DWARF 回溯比 FP 回溯更可靠但更慢 |
| **4. libunwindstack** | ART 和 debuggerd 共用的回溯库；`Regs` / `Maps` / `Elf` 三大核心类的协作 | `system/unwinding/libunwindstack/` | libunwindstack 回溯失败的常见原因 |
| **5. 符号化工具链** | `addr2line` / `ndk-stack` / `llvm-symbolizer` 的原理；读取 ELF 的 `.symtab` / `.debug_info` / `.debug_line` 段 | — | 如何从 `#01 pc 0x12345 libfoo.so` 还原到 `foo.cpp:42` |
| **6. MiniDebugInfo** | Android 的 `.gnu_debugdata` 压缩段；为什么 Release 版 so 库仍然能部分回溯 | `system/unwinding/libunwindstack/` | 堆栈全是 `<unknown>` 的排查思路 |

---

## 第三篇章：诊断实战与治理（3 篇）

> 核心问题：拿到 Tombstone 后怎么读？用什么工具预防？如何建设 APM 体系？

### [06-Tombstone 深度解读：7 种信号的特征识别与排查](06-Tombstone深度解读.md)

| 章节 | 内容 | 稳定性关联 |
| :--- | :--- | :--- |
| **1. Tombstone 逐字段解析** | signal / code / fault addr / registers / backtrace / maps / memory near 每一行的含义和解读方法 | 读懂 Tombstone 的基本功 |
| **2. SIGSEGV + SEGV_MAPERR** | 空指针（fault addr 接近 0x0）、野指针（fault addr 随机值）、Use-After-Free（地址合法但内容已变）的特征与区分 | 最常见的 NE 类型（占 60%+） |
| **3. SIGSEGV + SEGV_ACCERR** | 写只读内存（如修改 .rodata 段）、执行不可执行内存（DEP/NX）、JIT 代码权限问题 | 权限相关 NE |
| **4. SIGABRT** | `abort()` 主动调用、`__fortify_fail`（缓冲区溢出检测）、Scudo 检测到堆损坏、`CHECK` 宏失败 | 第二常见 NE 类型 |
| **5. SIGBUS** | mmap 文件被截断（文件大小变小但映射未更新）、内存对齐错误（ARM strict alignment） | I/O 相关 NE |
| **6. SIGFPE / SIGILL / SIGTRAP** | 整数除零、ABI 不兼容（32-bit so 在 64-bit 环境误加载）、`__builtin_trap` / 调试断点 | 低频但排查方向明确 |
| **7. Memory Maps 段解读** | 如何从 maps 段判断 fault addr 属于哪个 so / 是否在栈上 / 是否在堆上 / 是否在 [anon:...] 区域 | 定位崩溃模块的关键技能 |

### [07-检测工具体系：ASan / HWASan / MTE / GWP-ASan](07-检测工具体系.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. 为什么需要检测工具** | 内存错误的"冰山模型"：大多数内存错误不会立即崩溃，而是"默默腐蚀"，直到在完全不相关的位置爆发 | — | 理解为什么 NE 的崩溃点往往不是根因点 |
| **2. ASan** | 编译时插桩原理（Shadow Memory）；检测能力矩阵（UAF / OOB / Stack-BOF / Double-Free）；2x CPU + 3x Memory 的性能开销 | `compiler-rt/lib/asan/` | 开发阶段的内存错误检测利器 |
| **3. HWASan** | ARM64 TBI（Top Byte Ignore）的利用；与 ASan 的能力对比；更低的内存开销 | `compiler-rt/lib/hwasan/` | 测试阶段的推荐方案 |
| **4. MTE** | ARM v8.5+ 硬件内存标签；同步模式 vs 异步模式；Android 12+ 的系统级支持 | `bionic/libc/` | 硬件级零开销检测，未来的终极方案 |
| **5. GWP-ASan** | 线上采样检测原理（概率性替换 malloc/free 为 Guard Page 保护版本）；采样率配置 | `bionic/libc/bionic/gwp_asan_wrappers.cpp` | 唯一可在线上使用的内存错误检测方案 |
| **6. 工具选型矩阵** | 开发 / 测试 / 线上三阶段的工具选型建议；各工具的能力、开销、兼容性对比表 | — | 实操选型指南 |

### [08-APM 集成与治理：从捕获到治理的闭环](08-APM集成与治理.md)

| 章节 | 内容 | 核心源码路径 | 稳定性关联 |
| :--- | :--- | :--- | :--- |
| **1. 为什么需要 APM** | 系统 Tombstone 的局限性（不上报、不聚合、不告警、数量有限只保留最近 N 个） | — | 从"被动等 Bug 报告"到"主动发现问题" |
| **2. 三大框架对比** | xCrash vs Breakpad vs Crashpad 的架构设计、能力边界、性能开销、兼容性矩阵 | 各框架 GitHub 源码 | 框架选型依据 |
| **3. APM 核心原理** | 注册 Signal Handler → 在 Handler 中收集崩溃信息（寄存器 / 堆栈 / maps）→ 写 Minidump 到磁盘 → 下次启动上报 | — | 理解 APM 框架的工作边界和限制 |
| **4. 与 ART sigchain 的共存** | 为什么必须用 `sigaction` 而非 `signal`；如何处理 ART 的隐式异常信号（NullPointerException / StackOverflowError）；信号处理的优先级链 | `art/sigchain/sigchain.cc` | APM 框架误拦截 ART 信号导致的"假 NE" |
| **5. Minidump 格式** | 与 Tombstone 的结构对比；为什么 APM 选择 Minidump（跨平台、更紧凑、可离线符号化） | — | Minidump 解析工具链 |
| **6. 治理体系建设** | 崩溃聚合（堆栈相似度算法）、Top Crash 看板、归因到模块/版本/机型/渠道、修复验证闭环、NE 率监控与告警 | — | 从"能查"到"能治"到"能防" |

---

## 阅读建议

**如果你时间有限，优先阅读：**
1. **01 总览** — 建立全局观，理解崩溃处理全链路。
2. **06 Tombstone 深度解读** — 实战价值最高，直接提升排查效率。
3. **04 debuggerd 与 Tombstone** — 理解 Tombstone 是怎么生成的，才能理解它为什么有时候信息不全。

**如果你要系统学习，按顺序阅读 01 → 08。** 每篇文章的设计逻辑是：
```
背景与定义（是什么、为什么需要它）
    → 架构与交互（在系统中的位置、上下游关系）
        → 核心机制与源码（关键数据结构、核心流程）
            → 稳定性风险点（会在哪里出问题）
                → 实战案例（线上真实问题的排查过程）
```
