# 08-APM 集成与治理：从捕获到治理的闭环

上一篇我们系统讲解了 ASan / HWASan / MTE / GWP-ASan 四大内存检测工具，它们解决的是"在错误发生瞬间就捕获"的问题。但检测工具主要用于开发和测试阶段——线上数十亿次运行中产生的 Native Crash，靠什么来采集、聚合、归因、治理？

答案是 **APM（Application Performance Management）**。APM 是连接"崩溃发生"和"问题修复"之间的桥梁。没有 APM，你只能等用户投诉后去设备上捞 Tombstone；有了 APM，每一次 NE 都会被自动捕获、上报、聚合、归因，形成从"发现 → 定位 → 修复 → 验证"的完整闭环。

本篇将从系统 Tombstone 的局限性出发，逐步拆解 APM 框架的核心原理、与 ART sigchain 的共存策略、Minidump 格式选型、以及完整的治理体系建设方法。

---

## 1. 为什么需要 APM

### 1.1 系统 Tombstone 的五大局限

在前面的文章中我们详细拆解了 Android 的 debuggerd 架构和 Tombstone 生成流程。Tombstone 是一份精心设计的崩溃摘要，但它是**为本地调试设计的**，而不是为大规模线上治理设计的。对于稳定性架构师来说，系统 Tombstone 有五个致命局限：

| 局限 | 具体表现 | 对治理的影响 |
| :--- | :--- | :--- |
| **不上报** | Tombstone 只写入 `/data/tombstones/` 目录和 DropBoxManager，不会主动发送到远端服务器 | 你无法知道线上有多少用户遇到了崩溃 |
| **不聚合** | 每个 Tombstone 都是独立的文本文件，没有分组、去重、聚类能力 | 同一个 bug 可能产生了 10 万份 Tombstone，你逐一查看？ |
| **不告警** | 系统不会在 NE 率突增时主动通知你 | 一个灾难性 bug 可能在线上默默肆虐数天才被发现 |
| **数量有限** | `/data/tombstones/` 目录最多保留 32 个文件（`tombstone_00` ~ `tombstone_31`），循环覆盖 | 高频崩溃场景下，旧的 Tombstone 几分钟内就被覆盖 |
| **需要权限** | 普通应用无法读取 `/data/tombstones/` 目录（需要 root 或 `shell` 用户权限） | 线上用户设备上的 Tombstone，你根本拿不到 |

```
系统 Tombstone 的能力边界：

    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │ 能 捕获   │     │ 能 记录   │     │ 能 存储   │
    │ ✓        │────►│ ✓        │────►│ ✓ (32个) │
    └──────────┘     └──────────┘     └──────────┘
                                            │
                                            ▼
    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │ 能 上报   │     │ 能 聚合   │     │ 能 告警   │
    │ ✗        │     │ ✗        │     │ ✗        │
    └──────────┘     └──────────┘     └──────────┘
                                            │
                                            ▼
    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │ 能 归因   │     │ 能 跟踪   │     │ 能 度量   │
    │ ✗        │     │ ✗        │     │ ✗        │
    └──────────┘     └──────────┘     └──────────┘
```

### 1.2 APM 填补的能力空白

APM 框架本质上做了一件事：**在应用进程内自己实现一套崩溃捕获机制，绕过系统 Tombstone 的限制，将崩溃信息以可控的方式采集、存储、上报。**

| 能力 | 系统 Tombstone | APM 框架 |
| :--- | :--- | :--- |
| 捕获 NE | ✓（debuggerd_handler） | ✓（自注册 Signal Handler） |
| 本地存储 | ✓（32 个文件，需 root） | ✓（App 私有目录，无需 root） |
| 自动上报 | ✗ | ✓（下次启动或后台上报） |
| 聚合分析 | ✗ | ✓（堆栈聚类、Top Crash 排序） |
| 实时告警 | ✗ | ✓（NE 率突增触发告警） |
| 归因到版本/机型/渠道 | ✗ | ✓（上报时携带设备元数据） |
| 修复验证 | ✗ | ✓（对比修复前后的 NE 率） |

**稳定性关联：** APM 不是替代系统 Tombstone，而是在它之上构建一套完整的治理能力。系统 Tombstone 仍然是本地调试的首选工具（信息更完整），而 APM 是线上大规模治理的基石。一个成熟的稳定性团队，两者都需要。

---

## 2. 三大框架对比

### 2.1 为什么需要对比

选择 APM 框架是稳定性架构师的一个关键决策。市场上主流的 Native Crash 捕获框架有三个：**xCrash**（爱奇艺开源）、**Breakpad**（Google/Mozilla）、**Crashpad**（Google，Breakpad 的继任者）。它们的架构设计理念不同，在能力、性能、兼容性上各有取舍。

### 2.2 架构设计对比

**xCrash** 采用"进程内捕获"模式——Signal Handler 在崩溃进程内部直接采集信息并写入 Minidump。这种方式简单直接，但受限于 Signal Handler 的 async-signal-safe 约束。

**Breakpad** 采用"进程外捕获"模式——崩溃进程的 Signal Handler 通过 `fork()` 或管道通知一个独立的 handler 进程/线程，由后者通过 `ptrace` 采集崩溃信息。这种方式更安全（不受崩溃进程状态污染），但实现复杂度更高。

**Crashpad** 是 Breakpad 的现代化重写，采用常驻 handler 进程模式，通过 socket 通信，架构更清晰，但引入了额外的进程管理开销。

```
xCrash 架构（进程内捕获）：

  崩溃进程
  ┌─────────────────────────────────────┐
  │  Signal Handler                      │
  │   ├─ 读取 ucontext 中的寄存器        │
  │   ├─ 遍历 /proc/self/maps            │
  │   ├─ 调用 libunwindstack 回溯堆栈    │
  │   ├─ 写 Minidump 到 App 私有目录      │
  │   └─ 调用 old_handler（传递给系统）   │
  └─────────────────────────────────────┘

Breakpad 架构（进程外捕获）：

  崩溃进程                  Handler 子进程
  ┌──────────────┐         ┌──────────────────┐
  │ Signal Handler│─ fork ─►│ ptrace(ATTACH)    │
  │  ├─ 设置标记  │  /pipe  │ 读取寄存器 + 内存  │
  │  └─ wait()   │         │ 写 Minidump       │
  └──────────────┘         └──────────────────┘

Crashpad 架构（常驻 Handler 进程）：

  崩溃进程                  Crashpad Handler（常驻）
  ┌──────────────┐ socket  ┌──────────────────┐
  │ Signal Handler│────────►│ 收到通知          │
  │  └─ 通知     │         │ ptrace(ATTACH)    │
  └──────────────┘         │ 读取寄存器 + 内存  │
                           │ 写 Minidump       │
                           └──────────────────┘
```

### 2.3 能力与兼容性矩阵

| 维度 | xCrash | Breakpad | Crashpad |
| :--- | :--- | :--- | :--- |
| **开源协议** | MIT | BSD-3 | Apache-2.0 |
| **维护状态** | 活跃（爱奇艺持续维护） | 维护模式（新功能转向 Crashpad） | 活跃（Chromium 团队维护） |
| **捕获模式** | 进程内 | 进程外（fork） | 进程外（常驻进程） |
| **支持信号** | SIGSEGV/SIGABRT/SIGBUS/SIGFPE/SIGILL/SIGTRAP/SIGSYS | SIGSEGV/SIGABRT/SIGBUS/SIGFPE/SIGILL/SIGTRAP | SIGSEGV/SIGABRT/SIGBUS/SIGFPE/SIGILL/SIGTRAP |
| **Java Crash 捕获** | ✓（同时支持 JE + NE + ANR） | ✗（仅 NE） | ✗（仅 NE） |
| **ANR 捕获** | ✓ | ✗ | ✗ |
| **输出格式** | Minidump / 自定义文本 | Minidump | Minidump |
| **最低 API** | API 16（Android 4.1） | API 16 | API 21（Android 5.0） |
| **ABI 支持** | armeabi-v7a / arm64-v8a / x86 / x86_64 | armeabi-v7a / arm64-v8a / x86 / x86_64 | arm64-v8a / x86_64 |
| **包体增量** | ~200 KB | ~800 KB | ~1.2 MB |
| **sigchain 兼容** | ✓（通过标准 sigaction 注册） | 需要注意（部分版本直接调用内核） | ✓ |
| **进程内 async-signal-safe** | ✓（精心实现） | N/A（进程外处理） | N/A（进程外处理） |
| **fork 安全性** | N/A | 需要注意（多线程 fork 风险） | N/A（不 fork） |

### 2.4 性能开销对比

| 指标 | xCrash | Breakpad | Crashpad |
| :--- | :--- | :--- | :--- |
| **初始化耗时** | ~2 ms | ~5 ms | ~10 ms（需启动常驻进程） |
| **运行时内存** | ~100 KB（预分配 buffer） | ~200 KB | ~2 MB（Handler 进程常驻） |
| **崩溃采集耗时** | 50-200 ms | 100-500 ms | 100-300 ms |
| **对正常运行的影响** | 几乎为零（仅注册 handler） | 几乎为零 | 多一个常驻进程 |

### 2.5 框架选型建议

| 场景 | 推荐 | 理由 |
| :--- | :--- | :--- |
| **国内 Android App** | xCrash | 同时覆盖 JE + NE + ANR；包体小；API 16+ 兼容性好；中文社区活跃 |
| **跨平台应用（Android + iOS + Desktop）** | Crashpad | Chromium 团队维护，跨平台一致性最好 |
| **已有 Breakpad 集成的老项目** | 继续用 Breakpad 或逐步迁移 Crashpad | 迁移成本高时保持稳定 |
| **游戏引擎（Unity/Unreal）** | 引擎自带方案 + xCrash 兜底 | 引擎自带方案覆盖引擎内崩溃，xCrash 覆盖引擎外崩溃 |

**稳定性关联：** 框架选型不只是技术决策，也是工程决策。一个好的框架需要满足三个条件：（1）捕获率高——不能漏报；（2）捕获安全——不能因为捕获本身导致二次崩溃；（3）上报可靠——文件写入和上报链路要健壮。三大框架在这三个维度上各有侧重，没有绝对的"最好"，只有最适合你的场景的。

---

## 3. APM 核心原理

### 3.1 四步工作流

APM 框架捕获 Native Crash 的核心流程可以概括为四步：

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ ① 注册 Handler    │───►│ ② 崩溃时采集      │───►│ ③ 写 Minidump     │───►│ ④ 下次启动上报    │
│                  │    │                  │    │                  │    │                  │
│ sigaction() 注册  │    │ 在 Signal Handler │    │ 将采集的数据序列化 │    │ 检查是否有未上报的 │
│ 对 SIGSEGV 等信号 │    │ 中采集寄存器、     │    │ 为 Minidump 格式  │    │ Minidump 文件     │
│ 设置 SA_SIGINFO   │    │ 堆栈、maps 等     │    │ 写入磁盘          │    │ 上传到后端         │
│ + SA_ONSTACK     │    │ 崩溃现场信息       │    │                  │    │                  │
└──────────────────┘    └──────────────────┘    └──────────────────┘    └──────────────────┘
         │                      │                      │                      │
      App 启动时             崩溃瞬间               崩溃瞬间               下次启动时
```

### 3.2 步骤一：注册 Signal Handler

APM 框架在 App 初始化阶段（通常在 `Application.onCreate()` 中通过 JNI 调用 Native 代码）注册自己的 Signal Handler：

```c
static struct sigaction s_old_handlers[NSIG];

void apm_init() {
    stack_t ss;
    ss.ss_sp = mmap(NULL, APM_SIGNAL_STACK_SIZE, PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    ss.ss_size = APM_SIGNAL_STACK_SIZE;
    ss.ss_flags = 0;
    sigaltstack(&ss, NULL);

    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sigemptyset(&sa.sa_mask);
    sa.sa_sigaction = apm_signal_handler;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK;

    int fatal_signals[] = {SIGSEGV, SIGABRT, SIGBUS, SIGFPE, SIGILL, SIGTRAP, SIGSYS};
    for (int i = 0; i < sizeof(fatal_signals) / sizeof(int); i++) {
        sigaction(fatal_signals[i], &sa, &s_old_handlers[fatal_signals[i]]);
    }
}
```

关键设计点：

- **`SA_ONSTACK`**：使 Handler 在备用栈（Alternate Signal Stack）上运行，即使崩溃是栈溢出也能安全采集。
- **`SA_SIGINFO`**：获取 `siginfo_t`（包含 `si_addr` 等崩溃细节）和 `ucontext_t`（包含寄存器快照）。
- **保存 `old_handler`**：确保信号链不断裂。采集完毕后将信号转发给原 Handler（通常是 debuggerd_handler），保证系统 Tombstone 也能正常生成。

### 3.3 步骤二：在 Handler 中采集崩溃信息

这是 APM 框架最核心也最受限的环节。Signal Handler 运行在一个极其特殊的上下文中——**只有 async-signal-safe 的函数才能安全调用**。

```c
static void apm_signal_handler(int sig, siginfo_t *info, void *ucontext) {
    // ① 从 ucontext 中提取寄存器快照
    ucontext_t *uc = (ucontext_t *)ucontext;
    // ARM64: uc->uc_mcontext.regs[0..30], .sp, .pc, .pstate

    // ② 从 /proc/self/maps 读取内存映射（使用 open/read/close，均为 async-signal-safe）
    int fd = open("/proc/self/maps", O_RDONLY);
    // 读取到预分配的 buffer 中（不能 malloc！）
    read(fd, g_preallocated_maps_buffer, MAPS_BUFFER_SIZE);
    close(fd);

    // ③ 堆栈回溯（受限模式）
    // 基于 FP 链遍历或预编译的 libunwindstack 进行回溯
    // 回溯结果写入预分配的 buffer

    // ④ 将采集的数据写入 Minidump 文件
    int dump_fd = open(g_dump_path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    write(dump_fd, &minidump_header, sizeof(minidump_header));
    // ... 写入各个 Stream（寄存器、堆栈、模块列表、内存）
    close(dump_fd);

    // ⑤ 将信号传递给 old_handler（保证系统 Tombstone 也能生成）
    s_old_handlers[sig].sa_sigaction(sig, info, ucontext);
}
```

### 3.4 Signal Handler 上下文的约束

Signal Handler 是一个"地雷阵"——稍有不慎就会导致二次崩溃或死锁。以下是必须遵守的规则：

| 约束 | 原因 | 违反后果 |
| :--- | :--- | :--- |
| **只能调用 async-signal-safe 函数** | 崩溃可能发生在 `malloc()` 内部（持有 heap lock），Handler 中再调用 `malloc()` 会死锁 | 进程永久挂起（hang），而非崩溃退出——APM 什么信息都拿不到 |
| **不能使用 `printf` / `fprintf` / `snprintf`** | 这些函数内部调用 `malloc()`，不是 async-signal-safe 的 | 二次崩溃或死锁 |
| **不能使用 C++ 异常、STL 容器** | `new` / `delete` 底层调用 `malloc()`；STL 容器的增长操作也依赖动态内存 | 二次崩溃或死锁 |
| **不能使用 `pthread_mutex_lock`** | 崩溃线程可能正持有同一个 mutex | 死锁 |
| **栈空间有限（通常 8-16 KB）** | 运行在 Alternate Signal Stack 上，空间远小于正常线程栈（通常 1-8 MB） | 栈溢出导致二次崩溃 |
| **必须使用预分配的内存** | 所有 buffer 在初始化时就 `mmap()` 分配好，Handler 中直接使用 | — |

**POSIX 标准定义的常用 async-signal-safe 函数：**

```
open()    close()    read()    write()    lseek()
getpid()  gettid()   kill()    raise()    abort()
_exit()   sigaction()  sigprocmask()  fork()  execve()
mmap()    munmap()   mprotect()
```

注意 `malloc()` / `free()` / `printf()` / `pthread_mutex_lock()` 均**不在列表中**。

**稳定性关联：** 这些约束是 APM 框架质量的分水岭。一个成熟的框架（如 xCrash）会严格遵守 async-signal-safe 约束，所有数据采集操作都基于预分配内存和文件 I/O 系统调用；而不成熟的框架可能在 Handler 中偷偷调用了 `malloc()`——大部分时候能工作，但在 1% 的崩溃场景（恰好崩在 malloc 内部）下会导致二次崩溃和数据丢失。

---

## 4. 与 ART sigchain 的共存

### 4.1 为什么这是一个必须处理的问题

我们在第 02 篇（Linux 信号机制）和第 01 篇（NE 总览）中详细分析了 ART 的 sigchain 机制。核心要点回顾：

- ART 利用 `SIGSEGV` 实现**隐式空指针检查**（Java `null.field` → SIGSEGV → NullPointerException）和**隐式栈溢出检查**（触碰 Guard Page → SIGSEGV → StackOverflowError）。
- ART 通过 **sigchain**（`art/sigchain/sigchain.cc`）管理信号处理链，确保 ART 的 FaultHandler 优先处理信号。
- sigchain 拦截了所有通过标准 `sigaction()` 的注册调用，维护一条内部 Handler 链表。

APM 框架要在这个生态中安全工作，必须处理好三个问题：

### 4.2 问题一：必须通过 sigaction 注册，而非 signal 或直接系统调用

```cpp
// ✗ 错误方式 1：使用 signal()（无法获取 siginfo_t，且行为不可靠）
signal(SIGSEGV, my_handler);

// ✗ 错误方式 2：直接系统调用，绕过 sigchain
syscall(__NR_rt_sigaction, SIGSEGV, &ksa, &old_ksa, sizeof(sigset_t));

// ✗ 错误方式 3：通过 dlsym 获取原始 sigaction，绕过 sigchain
typedef int (*sigaction_t)(int, const struct sigaction*, struct sigaction*);
sigaction_t real_sigaction = (sigaction_t)dlsym(RTLD_NEXT, "sigaction");
real_sigaction(SIGSEGV, &sa, &old_sa);

// ✓ 正确方式：通过标准 sigaction()，会被 sigchain 拦截
sigaction(SIGSEGV, &sa, &old_sa);
```

**源码路径：** `art/sigchain/sigchain.cc`

sigchain 在 App 进程启动时通过链接器将 libc 的 `sigaction()` 替换为自己的版本。当 APM 框架调用 `sigaction(SIGSEGV, ...)` 时，实际执行的是 sigchain 的包装函数，它会把 APM 的 Handler 保存到 `user_sigactions[SIGSEGV]`，而不是覆盖内核中注册的 `sigchain_handler`。

如果 APM 绕过 sigchain 直接调用内核（上面的错误方式 2 和 3），就会覆盖 sigchain 注册的分发函数，导致：
- ART 的 FaultHandler 不再收到 SIGSEGV
- 所有 Java 层的 `NullPointerException` 变成 Native Crash
- 线上 NE 率暴增 300%+，NPE 率骤降

### 4.3 问题二：正确处理 ART 的隐式异常信号

在 sigchain 的信号处理链中，ART 的 FaultHandler 是第一优先级。当 SIGSEGV 到达时：

```
SIGSEGV 信号到达
    │
    ▼
sigchain_handler()（注册在内核中的真实 Handler）
    │
    ▼
① ART FaultHandler（Special Handler，优先级最高）
    ├─ 检查 fault addr 是否在 Null Page（< 4KB）
    │   且 PC 在 ART 编译的 Java 代码中
    │   → 是：修改 PC 跳转到 NullPointerException 抛出逻辑
    │        返回 true（信号已消化）
    │
    ├─ 检查 fault addr 是否在线程栈的 Guard Page
    │   → 是：修改 PC 跳转到 StackOverflowError 抛出逻辑
    │        返回 true（信号已消化）
    │
    └─ 都不满足 → 返回 false（传递给下一个 Handler）
    │
    ▼
② APM 框架的 Handler（User Handler）
    ├─ 采集崩溃信息、写 Minidump
    └─ 调用 old_handler 或重新抛出信号
    │
    ▼
③ debuggerd_handler（系统最终兜底）
    └─ 生成 Tombstone
```

**关键认知：** 正常情况下，ART 的隐式空指针和栈溢出信号不会到达 APM 的 Handler——它们在第 ① 步就被 ART 消化了。APM 的 Handler 只会收到"真正的" Native Crash。但如果 ART 的 FaultHandler 判断逻辑出现 bug（虽然极少见），可能会有少量 ART 应该处理的信号"泄漏"到 APM 层。

### 4.4 问题三：APM 误拦截 ART 信号 → 虚假 NE 报告

如果 APM 框架的注册方式破坏了信号链（如绕过 sigchain），所有 SIGSEGV 都会先到达 APM 的 Handler。此时 APM 无法区分"ART 隐式异常信号"和"真正的 Native Crash"，会将所有 SIGSEGV 都当作 NE 上报——产生海量**虚假 NE 报告**。

识别虚假 NE 报告的特征：

| 特征 | 正常 NE | APM 误拦截的 ART 隐式信号 |
| :--- | :--- | :--- |
| fault addr | 随机值或特定模式 | 集中在 `0x0` ~ `0xFFF`（Null Page 范围） |
| PC 所在代码 | 在 `.so` 库的 Native 代码中 | 在 ART JIT/AOT 编译的 Java 代码中 |
| backtrace 特征 | 完整的 Native 调用链 | 顶层几帧在 `[anon:dalvik-*]` 区域 |
| 伴随现象 | — | Java NPE 上报量同时骤降 |

**稳定性关联：** "虚假 NE"是 APM 集成中最常见的"坑"。它不会导致用户感知的问题（因为 ART 本来就能正确处理这些信号），但会严重污染 NE 数据——让你的 Top Crash 列表充斥着无关的噪声，掩盖真正需要修复的 bug。排查方法：当 NE 率异常突增时，先检查 `fault addr` 分布——如果大量集中在低地址，几乎可以确认是信号链被破坏。

---

## 5. Minidump 格式

### 5.1 为什么 APM 选择 Minidump 而非 Tombstone 格式

APM 框架需要一种崩溃文件格式，满足三个需求：跨平台一致（Android/iOS/Windows 使用统一格式简化后端处理）、体积紧凑（上报时节省带宽）、支持离线符号化（服务端拿到文件后能自行还原函数名和行号）。

| 维度 | Tombstone | Minidump |
| :--- | :--- | :--- |
| **格式** | 纯文本（Android 12+ 新增 Proto 二进制格式） | 二进制结构化格式 |
| **跨平台** | Android 专有 | Google 定义的跨平台标准（Windows/macOS/Linux/Android） |
| **体积** | 10-200 KB（文本冗余大） | 20-100 KB（二进制紧凑） |
| **符号化时机** | 生成时就已符号化（如果有符号） | 离线符号化——生成时只包含地址，服务端用符号表还原 |
| **结构化解析** | 文本需要正则匹配解析 | 有明确的二进制结构定义，可程序化解析 |
| **生态工具** | `ndk-stack`、`addr2line` | `minidump_stackwalk`、`dump_syms`、Sentry/Bugly 等平台原生支持 |

### 5.2 Minidump 文件结构

Minidump 文件由一个 Header 和多个 **Stream** 组成。每个 Stream 包含一类崩溃信息：

```
┌──────────────────────────────────────────────┐
│              Minidump Header                  │
│  ├─ Signature: "MDMP"                        │
│  ├─ Version                                  │
│  ├─ NumberOfStreams                           │
│  └─ StreamDirectoryRva（指向 Stream 目录）     │
├──────────────────────────────────────────────┤
│              Stream Directory                 │
│  ├─ Stream[0]: ThreadListStream              │
│  ├─ Stream[1]: ModuleListStream              │
│  ├─ Stream[2]: ExceptionStream               │
│  ├─ Stream[3]: SystemInfoStream              │
│  ├─ Stream[4]: MemoryListStream              │
│  ├─ Stream[5]: LinuxMaps                     │
│  └─ Stream[6]: LinuxProcStatus               │
├──────────────────────────────────────────────┤
│              Stream Data                      │
│                                              │
│  ThreadListStream:                           │
│    ├─ Thread[0]: tid, context(registers),    │
│    │             stack memory                 │
│    └─ Thread[1]: ...                         │
│                                              │
│  ModuleListStream:                           │
│    ├─ Module[0]: name, base_addr, size,      │
│    │             build_id                    │
│    └─ Module[1]: ...                         │
│                                              │
│  ExceptionStream:                            │
│    ├─ thread_id（崩溃线程 ID）                │
│    ├─ exception_code（信号编号）              │
│    └─ exception_address（fault addr）        │
│                                              │
│  MemoryListStream:                           │
│    ├─ 崩溃地址附近的内存内容                    │
│    └─ 栈内存                                 │
└──────────────────────────────────────────────┘
```

### 5.3 核心 Stream 与 Tombstone 字段的对应关系

| Minidump Stream | 包含信息 | 对应 Tombstone 段 |
| :--- | :--- | :--- |
| **ExceptionStream** | 信号编号、si_code、fault addr、崩溃线程 ID | `signal X (SIGXXX), code Y, fault addr 0x...` |
| **ThreadListStream** | 所有线程的 ID、寄存器快照、栈内存 | `registers` 段 + `backtrace` 段 |
| **ModuleListStream** | 所有已加载 so 库的名称、基地址、大小、Build ID | `memory map` 段 |
| **MemoryListStream** | 崩溃地址附近的原始内存内容 | `memory near` 段 |
| **SystemInfoStream** | CPU 架构、OS 版本 | Tombstone 头部信息 |
| **LinuxMaps** | `/proc/self/maps` 内容 | `memory map` 段 |

### 5.4 Minidump 处理工具链

当 Minidump 文件上传到后端后，需要通过工具链进行符号化和堆栈重建：

```
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│ dump_syms     │    │ Minidump 文件 │    │ minidump_stackwalk│
│              │    │              │    │                  │
│ 从未剥离的 so │    │ 从客户端上传  │    │ 输入：Minidump    │
│ 中提取符号信息 │    │              │    │ + 符号文件         │
│ → .sym 文件   │    │              │    │                  │
└──────┬───────┘    └──────┬───────┘    │ 输出：带函数名和   │
       │                   │           │ 行号的可读堆栈     │
       ▼                   ▼           └──────────────────┘
  ┌────────────────────────────┐
  │  符号服务器                  │
  │  按 Build ID 索引 .sym 文件 │
  │  Minidump + .sym → 符号化   │
  └────────────────────────────┘
```

**关键工具说明：**

- **`dump_syms`**：从未剥离（unstripped）的 so 文件中提取 DWARF 调试信息，生成 Breakpad 格式的 `.sym` 符号文件。每次构建 Release 版本时应自动运行。
- **`minidump_stackwalk`**：读取 Minidump 文件，结合 `.sym` 符号文件，重建完整的带函数名和行号的调用栈。
- **Build ID 匹配**：每个 so 文件在编译时会嵌入一个唯一的 Build ID（存在 ELF `.note.gnu.build-id` 段中），Minidump 和 `.sym` 文件通过 Build ID 精确匹配，避免版本不对应导致的符号化错误。

**稳定性关联：** 符号化是 Minidump 处理链路中最容易出错的环节。最常见的问题是 **Build ID 不匹配**——发布版本的 so 文件没有保存对应的未剥离版本或 `.sym` 文件，导致 Minidump 无法符号化，backtrace 中只有原始地址。稳定性架构师必须在 CI/CD 流程中强制执行：每次构建 Release APK 时，自动为所有 so 文件运行 `dump_syms` 并上传 `.sym` 文件到符号服务器。

---

## 6. 治理体系建设

### 6.1 为什么"能捕获"远远不够

很多团队在集成 APM 框架后就觉得"NE 问题解决了"——其实 APM 只完成了第一步。捕获只是手段，治理才是目的。一个完整的 NE 治理体系需要回答以下问题：

| 阶段 | 核心问题 | 对应能力 |
| :--- | :--- | :--- |
| **能查** | 某次崩溃的根因是什么？ | Minidump 解析 + 符号化 + 堆栈分析 |
| **能治** | 哪些崩溃影响最大？应该先修哪个？ | 崩溃聚合 + Top Crash 排序 + 归因 |
| **能防** | 如何在崩溃发生前发现风险？ | NE 率监控 + 趋势告警 + 灰度验证 |

### 6.2 崩溃聚合：堆栈相似度算法

一个 bug 可能在线上产生数十万份 Minidump。人不可能逐一查看，必须通过聚合算法将"同一根因"的崩溃归为一组。

**堆栈相似度算法的核心思想：** 取崩溃线程 backtrace 的前 N 帧（通常 N=3~5），对帧中的函数名进行归一化后计算哈希值，哈希值相同的崩溃归为同一 Issue。

```
聚合算法流程：

Crash Report
    │
    ▼
提取崩溃线程的 backtrace
    │
    ▼
取前 N 帧的函数名（忽略偏移量和行号）
    │
    ▼
归一化处理：
  ├─ 移除 C++ 模板参数（如 std::vector<int>::push_back → std::vector::push_back）
  ├─ 移除 lambda 表达式的编号（如 $lambda$0 → $lambda$）
  └─ 统一 demangle 格式
    │
    ▼
计算 fingerprint = hash(signal + frame[0] + frame[1] + ... + frame[N-1])
    │
    ▼
按 fingerprint 聚合 → 每个 fingerprint 对应一个 Issue
```

**取帧数量的权衡：**

| 取帧数 | 优点 | 缺点 |
| :--- | :--- | :--- |
| 1 帧 | 聚合度高，同一函数的不同调用路径归为一组 | 过度聚合——不同 bug 恰好崩在同一函数时被错误合并 |
| 3 帧 | 平衡点——大部分场景下既不过度聚合也不过度拆分 | — |
| 5+ 帧 | 精确区分不同调用路径 | 过度拆分——同一 bug 因为上层调用路径不同被拆成多个 Issue |

实践中推荐 **3 帧** 作为默认值，对于帧数少于 3 帧的崩溃取全部帧。

### 6.3 Top Crash 看板

聚合后的 Issue 需要排序，帮助团队决定修复优先级。Top Crash 看板的核心指标：

| 指标 | 定义 | 作用 |
| :--- | :--- | :--- |
| **影响设备数** | 触发该 Issue 的唯一设备（UDID）数量 | 衡量影响面——1 万设备各崩 1 次 vs 1 个设备崩了 1 万次，前者更紧急 |
| **崩溃次数** | 该 Issue 的总崩溃次数 | 衡量严重程度 |
| **NE 率占比** | 该 Issue 的崩溃次数 / 总 NE 数量 | 修复后能带来的 NE 率下降比例 |
| **首次出现版本** | 该 Issue 最早出现在哪个 App 版本 | 判断是新引入还是历史遗留 |
| **机型集中度** | 是否集中在特定机型/芯片平台 | 判断是通用 bug 还是机型兼容性问题 |

### 6.4 归因到模块/版本/机型/渠道

单纯的堆栈聚合还不够，需要多维度归因来精确定位责任方和影响范围：

```
多维度归因视图：

                ┌───────────────────────────────────────┐
                │            某 Issue（Top 1 NE）         │
                │  Signal: SIGSEGV (SEGV_MAPERR)         │
                │  Crash in: libimage_proc.so             │
                ├───────────────────────────────────────┤
                │                                       │
                │  按版本分布:                             │
                │  v3.2.0: ████████████████ 85%          │
                │  v3.1.9: ██ 10%                        │
                │  v3.1.8: █ 5%                          │
                │  → 结论: v3.2.0 引入的回归               │
                │                                       │
                │  按机型分布:                             │
                │  Pixel 7:     ██████ 30%               │
                │  Samsung S23: █████ 25%                │
                │  Xiaomi 13:   ████ 20%                 │
                │  Others:      █████ 25%                │
                │  → 结论: 非机型相关，通用 bug             │
                │                                       │
                │  按渠道分布:                             │
                │  Google Play: ██████████ 50%           │
                │  应用宝:      ██████ 30%               │
                │  Others:      ████ 20%                 │
                │  → 结论: 非渠道相关                      │
                │                                       │
                │  按模块归属:                             │
                │  libimage_proc.so → 图片处理模块         │
                │  → 指派给: 图片处理团队                   │
                └───────────────────────────────────────┘
```

### 6.5 修复验证闭环

修复一个 NE 不是发布 hotfix 就结束了。必须建立一个闭环来验证修复是否有效：

```
发现 Issue → 定位根因 → 提交修复 → 灰度发布 → 验证修复 → 全量发布
    │                                    │            │
    │                                    ▼            │
    │                              对比灰度版本        │
    │                              与旧版本的          │
    │                              该 Issue NE 率      │
    │                                    │            │
    │                              ┌─────┴─────┐     │
    │                              │ 率下降90%+? │     │
    │                              └─────┬─────┘     │
    │                               Y    │    N       │
    │                              全量   │  回滚 +    │
    │                                    │  继续排查   │
    └────────────────────────────────────┘            │
                    Issue 关闭 ◄──────────────────────┘
```

**灰度验证的关键指标：**

- **该 Issue 的 NE 率**：修复后应降至接近 0。如果只降了 50%，说明修复不彻底或该 Issue 被过度聚合（包含了多个不同根因的崩溃）。
- **整体 NE 率**：确认修复没有引入新的崩溃（回归）。
- **相邻 Issue 的 NE 率**：确认没有将崩溃从一个 Issue "转移"到另一个 Issue。

### 6.6 NE 率监控与告警

稳定性治理的最高阶段是"能防"——在问题影响大面积用户之前发现并响应。

**NE 率的定义：**

```
NE 率 = 发生 NE 的设备数 / 日活设备数 × 100%

行业参考水平：
  优秀: < 0.01%（万分之一）
  良好: 0.01% - 0.05%
  及格: 0.05% - 0.1%
  需要治理: > 0.1%
```

**告警策略：**

| 告警类型 | 触发条件 | 响应 |
| :--- | :--- | :--- |
| **绝对值告警** | NE 率突破阈值（如 > 0.1%） | 排查 Top Crash，考虑紧急 hotfix |
| **环比告警** | NE 率较昨日同时段上升 50%+ | 检查是否有新版本发布或配置变更 |
| **新 Issue 告警** | 出现之前未见过的 Issue 且影响设备数 > 100 | 可能是新版本引入的回归 |
| **单 Issue 爆发告警** | 某个 Issue 在 1 小时内崩溃次数 > 1000 | 可能是服务端下发的配置触发了特定 Native 代码路径 |

**稳定性关联：** 治理体系的终极目标是实现"从捕获到治理的闭环"——APM 捕获 → 后端聚合 → 看板归因 → 指派修复 → 灰度验证 → 全量发布 → 监控告警。当这个闭环完整运转时，NE 率会持续下降并稳定在可接受范围内。每一个环节的缺失都会导致"治理黑洞"——bug 被发现但没人修、修了但不知道是否有效、有效了但新的又来了。

---

## 7. 稳定性实战案例

### 案例一：APM 框架绕过 sigchain 导致海量虚假 NE

**现象：**

某社交 App v8.5.0 上线后，NE 率从稳定的 0.03% 暴涨至 0.15%，同时 Java NPE 率从 0.12% 骤降至 0.02%。APM 后台 Top 1 Issue 是 SIGSEGV (SEGV_MAPERR)，影响设备数超过 50 万台/天。

**分析过程：**

**① 检查 fault addr 分布。** 导出 Top 1 Issue 的所有 Minidump 样本，统计 `fault addr`：

```
fault addr 分布:
  0x00000000 - 0x00000FFF:  92%  ← Null Page 范围
  0x00001000 - 0x0000FFFF:   3%
  其他:                       5%
```

92% 的 `fault addr` 集中在 Null Page 范围——这些应该是 ART 隐式空指针检查的信号，本应被 ART 的 FaultHandler 转化为 Java `NullPointerException`。

**② 检查版本差异。** v8.5.0 相比 v8.4.0 的变更中，新集成了一个第三方安全加固 SDK。

**③ 排查加固 SDK 的信号注册。** 反编译加固 SDK 的 so 库，发现其初始化代码中通过 `dlsym(RTLD_NEXT, "__sigaction")` 获取了 libc 的原始 `__sigaction` 函数，绕过了 sigchain 的拦截：

```c
// 加固 SDK 的初始化代码（反编译还原）
typedef int (*real_sigaction_t)(int, const struct sigaction*, struct sigaction*);
real_sigaction_t real_sa = (real_sigaction_t)dlsym(RTLD_NEXT, "__sigaction");
struct sigaction sa;
sa.sa_sigaction = security_signal_handler;
sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
real_sa(SIGSEGV, &sa, &old_sa);  // 绕过了 sigchain！
```

**④ 验证。** 在 sigchain 的 `sigchain_handler` 入口处打日志，确认 v8.5.0 启动后 `sigchain_handler` 不再被内核调用——因为内核中注册的 Handler 已经被加固 SDK 覆盖为 `security_signal_handler`。

**根因：**

加固 SDK 通过 `dlsym(RTLD_NEXT, "__sigaction")` 绕过 sigchain 直接调用了 libc 底层的 `__sigaction`，覆盖了内核中注册的 `sigchain_handler`。此后所有 SIGSEGV 直接到达加固 SDK 的 Handler，ART FaultHandler 完全被旁路。

信号链变化：

```
修复前:
  SIGSEGV → security_signal_handler（加固 SDK）→ 全部当 NE 处理
            × ART FaultHandler 完全不参与

修复后:
  SIGSEGV → sigchain_handler
            → ART FaultHandler（隐式空指针 → NPE）
            → security_signal_handler
            → debuggerd_handler
```

**修复方案：**

1. **短期**：联系加固 SDK 厂商，升级到使用标准 `sigaction()` 的版本。
2. **长期防护**：
   - CI 中增加 SO 符号扫描：检查所有集成的 so 库的导入符号表，如果发现引用了 `__sigaction` 或 `__rt_sigaction`，标记为风险。
   - App 启动完成后，主动验证 SIGSEGV 的当前内核 Handler 是否仍为 sigchain 的 dispatcher（通过 `syscall(__NR_rt_sigaction, SIGSEGV, NULL, &current_sa, ...)` 读取，不修改）。

**修复前后对比：**

```
┌──────────────────┬──────────┬──────────┐
│ 指标              │ 修复前    │ 修复后    │
├──────────────────┼──────────┼──────────┤
│ NE 率             │ 0.15%    │ 0.03%    │
│ NPE 率            │ 0.02%    │ 0.12%    │
│ Top 1 Issue 影响  │ 50万台/天 │ 消失      │
│ 总异常量          │ ~0.17%   │ ~0.15%   │
└──────────────────┴──────────┴──────────┘
```

总异常量基本不变，证实这些 NE 本质上是被错误分类的 Java NPE。

---

### 案例二：Signal Handler 中调用 malloc 导致崩溃信息丢失

**现象：**

某短视频 App 的 APM 系统发现一个奇怪的现象：后端收到的 Minidump 文件中，约 5% 的文件内容为空或严重截断（仅有 Header，缺少所有 Stream 数据）。这些"空 Minidump"无法进行任何分析，等于崩溃信息丢失。

同时，系统 `/data/tombstones/` 中存在对应时间点的完整 Tombstone——说明崩溃确实发生了，但 APM 没有成功采集。

**分析过程：**

**① 统计"空 Minidump"出现的规律。** 将空 Minidump 的崩溃时间与系统 Tombstone 交叉比对，发现这些崩溃的共同特征：

```
空 Minidump 对应的 Tombstone 特征:
  信号: SIGABRT (76%)、SIGSEGV (24%)
  abort message（SIGABRT 场景）:
    - "scudo: corrupted chunk header"     42%
    - "scudo: invalid chunk state"        18%
    - "fdsan: attempted to close..."      16%
```

76% 的空 Minidump 对应 SIGABRT，且 abort message 大量指向 **Scudo 堆损坏检测**。

**② 推断根因方向。** Scudo 的堆损坏检测在 `free()` 或 `malloc()` 内部触发——这意味着崩溃瞬间堆分配器的内部状态已经不一致。如果 APM 的 Signal Handler 在此时调用了 `malloc()`，就会触发二次崩溃或死锁。

**③ 代码审查。** 审查该 App 使用的 APM SDK（一个内部自研版本），在 Signal Handler 中发现：

```c
static void crash_signal_handler(int sig, siginfo_t *info, void *ucontext) {
    // 采集线程名
    char thread_name[64];
    prctl(PR_GET_NAME, thread_name);

    // ✗ 问题在这里：用 snprintf 格式化日志
    char *log_buffer = (char *)malloc(4096);  // ← async-signal-UNSAFE!
    snprintf(log_buffer, 4096,                // ← async-signal-UNSAFE!
             "Crash: sig=%d, tid=%d, thread=%s",
             sig, gettid(), thread_name);

    // 写入 Minidump
    write_minidump(sig, info, ucontext);

    // 转发给 old handler
    old_handler(sig, info, ucontext);
}
```

`malloc()` 和 `snprintf()` 都不是 async-signal-safe 函数。当崩溃发生在堆分配器内部时（Scudo 检测到堆损坏并调用 `abort()`），`malloc()` 的内部 mutex 已被崩溃线程持有。Signal Handler 中再次调用 `malloc()` → 尝试获取同一个 mutex → **死锁**。

进程被死锁挂住后，后续的 `write_minidump()` 永远不会执行——Minidump 文件要么为空（未写入任何内容），要么只写了 Header（`write_minidump` 函数的前几个字节在死锁前写出）。

最终内核的 watchdog 或系统的进程管理器杀死了挂住的进程（SIGKILL），系统的 debuggerd_handler 也没有机会执行（因为 APM 的 Handler 死锁了，信号没有被传递下去）。但由于这个特定 App 使用了 `SA_RESETHAND` 标志，部分场景下系统的 Tombstone 仍能生成。

**根因：**

APM SDK 的 Signal Handler 中调用了 `malloc()` 和 `snprintf()` 等 async-signal-unsafe 函数。当崩溃原因本身就是堆损坏（Scudo 检测触发 SIGABRT）时，Handler 中的 `malloc()` 死锁，导致崩溃信息采集失败。

**修复方案：**

1. **消除所有 async-signal-unsafe 调用**：将 `malloc()` 替换为初始化时预分配的 `mmap` 内存；将 `snprintf()` 替换为手写的整数/字符串拼接函数（仅使用栈上内存和 `write()` 系统调用）。
2. **增加 Handler 超时保护**：在 Signal Handler 入口设置一个 `alarm()` 定时器（alarm 是 async-signal-safe 的），如果 Handler 执行超过 5 秒未完成，由 SIGALRM 触发强制退出逻辑，将已采集的部分数据写入磁盘。
3. **增加 Handler 重入保护**：使用原子变量标记 Handler 是否已在执行中，避免二次崩溃导致 Handler 递归。

```c
static volatile sig_atomic_t s_handler_entered = 0;
static char s_preallocated_buffer[4096];  // 预分配，不在 handler 中 malloc

static void crash_signal_handler(int sig, siginfo_t *info, void *ucontext) {
    if (__atomic_exchange_n(&s_handler_entered, 1, __ATOMIC_SEQ_CST)) {
        // 已经在处理中（二次崩溃），直接传递给 old handler
        old_handler(sig, info, ucontext);
        return;
    }

    alarm(5);  // 5 秒超时保护

    // 使用预分配 buffer，不调用 malloc
    int len = 0;
    const char *prefix = "Crash: sig=";
    memcpy(s_preallocated_buffer + len, prefix, strlen(prefix));
    len += strlen(prefix);
    // ... 手写整数转字符串 ...

    write_minidump(sig, info, ucontext);
    old_handler(sig, info, ucontext);
}
```

**修复前后对比：**

```
┌──────────────────────┬──────────┬──────────┐
│ 指标                  │ 修复前    │ 修复后    │
├──────────────────────┼──────────┼──────────┤
│ 空 Minidump 比例      │ 5.2%     │ 0.1%     │
│ 崩溃信息丢失率        │ 5.2%     │ 0.1%     │
│ 堆损坏类 NE 的捕获率  │ ~24%     │ ~99%     │
│ Handler 死锁导致的     │ 约 300   │ 0        │
│ 进程挂起次数/天        │ 次/天    │          │
└──────────────────────┴──────────┴──────────┘
```

修复后空 Minidump 比例从 5.2% 降至 0.1%（剩余 0.1% 是磁盘空间不足等极端场景），堆损坏类崩溃的捕获率从约 24% 提升至 99%。

---

## 8. 总结

本篇从"为什么需要 APM"出发，逐步拆解了 APM 框架的核心原理、与 ART sigchain 的共存策略、Minidump 格式、以及治理体系建设的全貌。

核心要点：

1. **系统 Tombstone 有五大局限**（不上报、不聚合、不告警、数量有限、需要权限），APM 框架是线上大规模 NE 治理的必需品。
2. **三大框架各有取舍**：xCrash 适合国内 Android App（全能型、包体小）、Crashpad 适合跨平台（架构清晰、Google 维护）、Breakpad 适合存量项目（成熟稳定）。
3. **Signal Handler 中只能使用 async-signal-safe 函数**——这是 APM 框架质量的分水岭。`malloc()`、`printf()`、`pthread_mutex_lock()` 在 Handler 中都是定时炸弹。
4. **APM 必须通过标准 `sigaction()` 注册**，让 sigchain 正确管理信号链——否则 ART 的隐式空指针检查失效，产生海量虚假 NE。
5. **Minidump 是 APM 的首选格式**——跨平台、紧凑、支持离线符号化。Build ID 匹配和 `.sym` 文件管理是符号化链路的关键。
6. **治理体系的三个层次**：能查（Minidump 分析）→ 能治（聚合 + 归因 + Top Crash）→ 能防（监控 + 告警 + 灰度验证闭环）。

对稳定性架构师而言，APM 不仅是一个技术工具，更是一套治理方法论。技术上做到"不漏报、不误报、不丢数据"，流程上做到"发现 → 定位 → 修复 → 验证"的完整闭环——这才是从"消防式救火"到"体系化治理"的跨越。
