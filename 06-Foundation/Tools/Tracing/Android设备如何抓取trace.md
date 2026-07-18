除了 Perfetto，Android 设备上可用于抓取 Trace 的命令行工具非常丰富，主要分为**内核态跟踪**、**系统级跟踪**、**用户态跟踪**和**日志类跟踪**四大类。结合你作为安卓系统开发工程师（关注 Linux 内核、IO 子系统、Binder 驱动）的需求，以下是针对性的工具整理，包含**命令示例**、**适用场景**和**核心特点**：

---

## 一、内核态跟踪工具（核心推荐，针对 Block/IO/调度）
这类工具直接对接 Linux 内核的 `ftrace` 或 `perf` 子系统，能抓取最底层的内核事件（如 `block_rq_issue`、`sched_switch`、`binder_transaction`），**需要 Root 权限**，且内核需开启对应配置（如 `CONFIG_FTRACE`、`CONFIG_PERF_EVENTS`）。

### 1. `ftrace` 原生接口（最底层，无封装）
Systrace 和 Perfetto 底层都是调用 `ftrace`，你可以直接通过 `/sys/kernel/debug/tracing` 接口手动控制，**灵活性最高**，适合精准抓取内核 Block/IO 事件。

#### 核心命令流程（以抓取 `block_rq_issue` 为例）：
```bash
# 1. 进入 ftrace 目录（需 Root）
adb shell su -c "cd /sys/kernel/debug/tracing"

# 2. 重置 trace 缓冲区
adb shell su -c "echo 0 > tracing_on"
adb shell su -c "echo > trace"

# 3. 启用 block 事件（指定具体事件，避免冗余）
adb shell su -c "echo 1 > events/block/block_rq_issue/enable"
# 可选：同时启用 block_rq_complete（IO 完成事件），便于分析 IO 延迟
adb shell su -c "echo 1 > events/block/block_rq_complete/enable"

# 4. 开始跟踪（开启缓冲区写入）
adb shell su -c "echo 1 > tracing_on"

# 5. 触发需要分析的 IO 操作（如拷贝大文件、App 读写存储）
# （在设备上手动操作，或通过 adb 命令触发）

# 6. 停止跟踪
adb shell su -c "echo 0 > tracing_on"

# 7. 读取 trace 结果（两种方式）
# 方式 1：直接打印到控制台
adb shell su -c "cat trace"
# 方式 2：保存到设备文件，再拉取到电脑分析
adb shell su -c "cat trace > /sdcard/block_ftrace.txt"
adb pull /sdcard/block_ftrace.txt .
```

#### 优点：
- 无工具封装开销，**数据最原始**，可抓取到 Perfetto/Systrace 过滤掉的细节；
- 支持所有 `ftrace` 事件（Block、Sched、Binder、IRQ 等），可精准控制跟踪范围。

#### 缺点：
- 命令繁琐，需手动管理缓冲区；
- 输出为纯文本，需自行分析（可结合 `trace-cmd` 工具格式化）。

---

### 2. `perf` 工具（内核性能分析，支持采样+事件跟踪）
Android 设备若内置 `perf` 二进制（部分定制内核/开发版设备提供，或需自行编译），可抓取内核性能事件，**特别适合分析 Block IO 延迟、CPU 占用、函数调用栈**。

#### 核心命令示例（针对 Block 事件）：
```bash
# 1. 抓取 block_rq_issue 事件，持续 10 秒，保存到 perf.data
adb shell su -c "perf record -e block:block_rq_issue -g -o /sdcard/perf.data sleep 10"
# 参数说明：
# -e：指定事件（block:block_rq_issue 为块设备 IO 发出事件）
# -g：记录函数调用栈（分析 IO 触发源头）
# -o：输出文件

# 2. 拉取 perf.data 到电脑
adb pull /sdcard/perf.data .

# 3. 分析结果（需电脑安装 perf 工具）
perf report -i perf.data
# 或查看原始事件
perf script -i perf.data
```

#### 优点：
- 支持**事件跟踪**和**CPU 采样**（如 `perf record -g -F 99 sleep 10`）；
- 可记录函数调用栈，能定位“哪个内核函数触发了 IO”；
- 兼容 Linux 原生 `perf` 分析工具，生态成熟。

#### 缺点：
- 多数商用 Android 设备默认不内置 `perf`，需自行编译适配内核；
- 部分内核可能未开启 `CONFIG_PERF_EVENTS`，导致无法使用。

---

### 3. `dmesg`（内核日志，抓取驱动/Block 底层报错）
`dmesg` 用于读取 Linux 内核的 `printk` 缓冲区，**适合抓取 Block 驱动、IO 子系统的内核报错、警告或调试信息**（如磁盘读写错误、驱动初始化失败）。

#### 核心命令示例：
```bash
# 1. 查看当前所有内核日志
adb shell dmesg

# 2. 实时跟踪内核日志（类似 tail -f）
adb shell dmesg -w

# 3. 过滤 Block 相关日志（结合 grep，需设备支持 grep）
adb shell dmesg | grep -i "block"
adb shell dmesg | grep -i "sdhci"  # 过滤存储驱动相关日志
```

#### 优点：
- 无需额外配置，**所有 Android 设备默认支持**；
- 能捕获内核启动阶段和运行时的底层错误，定位 Block 驱动问题高效。

#### 缺点：
- 仅记录内核打印信息，非结构化 Trace，无法分析事件时序；
- 缓冲区大小有限，旧日志可能被覆盖。

---

## 二、系统级跟踪工具（Android 专属，兼容 ftrace）
这类工具是 Google 为 Android 封装的跟踪工具，底层基于 `ftrace`，**无需手动操作内核接口**，适合快速抓取系统级 Trace（Block、Sched、Binder、UI 等）。

### 1. `atrace`（Systrace 底层命令，设备端直接调用）
`atrace` 是 Systrace 的设备端核心命令，可直接在 Android 设备上执行，**无需依赖电脑的 SDK 工具**，输出格式与 Systrace 一致（HTML）。

#### 核心命令示例（抓取 Block 事件）：
```bash
# 1. 查看设备支持的跟踪类别（确认 block 可用）
adb shell atrace --list_categories

# 2. 抓取 block + sched + binder 事件，持续 10 秒，保存为 HTML
adb shell atrace -o /sdcard/atrace_block.html block sched binder -t 10
# 参数说明：
# -o：输出文件（需指定路径，如 /sdcard）
# block/sched/binder：跟踪类别（可添加多个）
# -t：跟踪时长（秒）

# 3. 拉取 HTML 文件到电脑，用 Chrome 打开分析
adb pull /sdcard/atrace_block.html .
```

#### 优点：
- 与 Systrace 完全兼容，输出 HTML 可直接在浏览器中可视化分析；
- 无需电脑安装 SDK，直接在设备端操作，适合远程调试。

#### 缺点：
- 功能与 Systrace 一致，无额外扩展；
- 部分非 root 设备可能无法抓取 `block` 等内核级类别。

---

### 2. `systrace` 命令行（电脑端，Android SDK 工具）
虽然你问的是“除了 Perfetto”，但 `systrace` 是独立于 Perfetto 的经典工具，且命令行使用便捷，**适合快速抓取 Android 系统 Trace**，已在之前的回答中详细说明，这里补充核心命令：
```bash
# 抓取 block + sched + process 事件，持续 20 秒，输出 HTML
systrace block sched process -t 20 -o systrace_block.html
```

---

## 三、用户态跟踪工具（分析 App/进程与内核的交互）
这类工具聚焦用户态进程，可跟踪系统调用、库调用等，**适合分析“用户态进程如何触发 Block IO”**（如 App 调用 `read()`/`write()` 导致的磁盘操作）。

### 1. `strace`（系统调用跟踪）
`strace` 能跟踪用户态进程的**所有系统调用**（如 `open`、`read`、`write`、`ioctl`），并记录调用参数、返回值和耗时，**需要 Root 权限**。

#### 核心命令示例（跟踪特定进程的文件 IO）：
```bash
# 1. 查看进程 PID（如跟踪 main 进程）
adb shell ps -A | grep main

# 2. 跟踪该进程的文件操作相关系统调用（open/read/write/close）
adb shell su -c "strace -p <进程PID> -e trace=file -o /sdcard/strace_main.txt"
# 参数说明：
# -p：指定进程 PID
# -e trace=file：仅跟踪文件相关系统调用（缩小范围）
# -o：输出文件

# 3. 拉取结果分析
adb pull /sdcard/strace_main.txt .
```

#### 优点：
- 精准定位用户态进程的系统调用行为，可分析“App 为何频繁触发 IO”；
- 支持过滤特定系统调用，减少冗余数据。

#### 缺点：
- 会增加进程开销，可能影响性能；
- 仅跟踪用户态，无法直接看到内核态 Block 事件的细节。

---

### 2. `ltrace`（库调用跟踪）
`ltrace` 用于跟踪用户态进程的**库函数调用**（如 `libc`、`libbinder` 中的函数），补充 `strace` 的不足（`strace` 仅跟踪系统调用，`ltrace` 可跟踪库调用）。

#### 核心命令示例：
```bash
# 跟踪进程的 libc 库调用，输出到文件
adb shell su -c "ltrace -p <进程PID> -o /sdcard/ltrace_main.txt"
```

#### 优点：
- 能看到进程内部的库函数调用流程，如 `fopen`、`fread` 等；
- 适合分析用户态代码逻辑导致的 IO 问题。

#### 缺点：
- 多数 Android 设备默认不内置 `ltrace`，需自行安装；
- 开销比 `strace` 更大，不适合长时间跟踪。

---

## 四、日志类跟踪工具（辅助分析，补充上下文）
### 1. `logcat`（系统/应用日志，含事件日志）
`logcat` 主要用于抓取 Android 系统和应用的日志，其中**事件日志（`-b events`）**包含系统级事件（如磁盘挂载、IO 错误），可作为 Block 跟踪的补充。

#### 核心命令示例：
```bash
# 1. 查看所有日志（含系统、应用、事件）
adb logcat

# 2. 仅查看事件日志（过滤系统级 IO 相关事件）
adb logcat -b events | grep -i "disk"

# 3. 保存日志到文件
adb logcat -d -f /sdcard/logcat.txt  # -d：读取当前日志后退出
```

---

## 五、工具选择指南（按你的需求场景）
| 需求场景                          | 推荐工具               | 核心优势                                  |
|-----------------------------------|------------------------|-------------------------------------------|
| 抓取内核 Block/IO 原始事件（如 `block_rq_issue`） | `ftrace` 原生接口、`perf` | 数据最完整，支持调用栈分析                |
| 快速生成可视化 Trace（HTML）分析 Block 时序 | `atrace`、`systrace`   | 浏览器可直接查看，支持与 Sched/Binder 关联 |
| 分析用户态进程触发 IO 的系统调用  | `strace`               | 精准定位 App/进程的文件操作行为          |
| 排查 Block 驱动/内核底层报错      | `dmesg`                | 捕获内核 printk 日志，无需额外配置        |
| 全平台通用、支持复杂过滤/后处理   | `Perfetto`（补充提及） | 虽你问“除了 Perfetto”，但它仍是最全面的选择 |

---

## 六、关键注意事项
1. **权限问题**：所有内核级工具（`ftrace`、`perf`、`strace`、`ltrace`）**必须 Root**，非 root 设备只能抓取 `atrace`/`systrace`/`logcat` 的非内核类别（如 `gfx`、`view`）。
2. **内核配置**：需确认设备内核开启 `CONFIG_FTRACE`、`CONFIG_BLOCK_TRACE`（Block 事件）、`CONFIG_PERF_EVENTS`（`perf` 工具），否则部分工具/事件无法使用。
3. **性能影响**：`strace`、`ltrace`、`perf` 等工具会增加系统/进程开销，建议在测试环境使用，避免影响生产环境性能。