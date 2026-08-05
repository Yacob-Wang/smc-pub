# 进程的执行：execve 与程序加载

> 系列第 04 篇 · 阶段 B · 生命周期
>
> **承上**：03 篇讲完 fork——子进程诞生了，但只是个"空壳" task_struct。本篇回答：execve 怎么把这个空壳变成"能跑 /system/bin/ls 的进程"？
>
> **启下**：进程跑起来后会死。05 篇《进程的退出：do_exit 与资源回收》回答"进程怎么死 + 父进程怎么收尸"。
>
> **预计篇幅**：约 1.7 万字
>
> **源码基线**：Linux 5.10 / 5.15（Android 12-14 主流内核）。

---

## 学习目标

读完本文，你应该能：

1. 在脑中画出 execve 家族 6 个函数（execl/execv/execle/execve/execlp/execvp）的关系——为什么它们最终都走 `sys_execve`。
2. 跟踪 `sys_execve()` → `do_execveat_common()` → `search_binary_handler()` → `load_elf_binary()` 的完整路径。
3. 理解 `linux_binprm` 这个"内核的桥梁结构"——它把"用户态可执行文件"和"内核 ELF 解析器"串起来。
4. 知道 ELF 文件格式在内核里被怎么解析——PT_LOAD / PT_INTERP / PT_DYNAMIC 段怎么被处理。
5. 理解动态链接器（ld.so / Android linker）怎么被内核"借壳"加载，以及 Android 14 linker 64 的特殊路径。
6. 理解进程地址空间怎么从 fork 后的"父进程镜像"被 exec 替换为"应用独立空间"。
7. 掌握 Zygote fork 后的 execve 序列——为什么 Zygote 预加载的所有类加载器结果在应用 exec 后被"扔掉"。
8. 能用 `strace -e execve` 在 Android 14 上看真实 exec 序列，能用 `readelf` / `llvm-readelf` 看 ELF 段。
9. 理解 execve 失败的常见原因——ENOEXEC / EACCES / at_secure / SELinux。
10. 理解 execve 与内存账户的关联——`mm->task_size` / `current->mm->start_code` 怎么被改写。

---

## 一、用户态视角：execve 家族的 6 个函数

### 1.1 6 个 API 同一个内核入口

用户态的 exec 家族有 6 个 API——`execlp` / `execl` / `execle` / `execv` / `execvp` / `execve`。它们的差异只在**参数组织方式**：

| API | 参数 | 是否搜索 PATH | 是否传 envp |
|---|---|---|---|
| `execlp(file, arg0, ..., NULL)` | 列表 | ✅（按 PATH 搜） | ❌（继承父） |
| `execl(file, arg0, ..., NULL)` | 列表 | ❌ | ❌ |
| `execle(file, arg0, ..., NULL, envp)` | 列表 | ❌ | ✅（显式传） |
| `execv(file, argv[])` | 数组 | ❌ | ❌ |
| `execvp(file, argv[])` | 数组 | ✅ | ❌ |
| `execve(file, argv[], envp[])` | 数组 | ❌ | ✅（显式传） |

**关键**：在内核入口上，**它们都走同一个 `sys_execve`**——glibc / Bionic 负责把前 5 个转换成 `execve` 调用。

```c
// Bionic libc（Android）
// bionic/libc/unistd/exec.c（简化）
int execve(const char *pathname, char *const argv[], char *const envp[]) {
    return __execve(pathname, argv, envp);
}

// execlp 内部（Bionic）
int execlp(const char *file, const char *arg, ...) {
    va_list ap;
    va_start(ap, arg);
    // 1. 在 PATH 中搜索 file
    // 2. 找到后调用 execve
    // 3. 没找到返回 -1
}
```

**真实路径**：

```
execlp("ls", "ls", "-l", NULL)
  ↓ Bionic 内部 PATH 搜索（按 : 分隔）
  ↓ 找到 /system/bin/ls
  ↓ 构造 argv[] = {"ls", "-l", NULL}
  ↓ 构造 envp[]（继承 environ）
  ↓ execve("/system/bin/ls", argv, envp)
  ↓ [syscall 指令]
  ↓ sys_execve()   ← 内核入口（所有 exec 家族汇聚点）
```

### 1.2 Android 14 上能看到的 execve 序列

```bash
# 跟踪 adb shell 启动 ls 时所有 execve 调用
adb shell "strace -f -e trace=execve /system/bin/ls /data" 2>&1
```

输出（节选）：

```
execve("/system/bin/ls", ["ls", "/data"], 0x7fc8...) = 0
```

ls 本身不 fork 任何子进程，所以只有 1 次 execve。如果跟踪 Zygote 启动应用，会看到完整序列：

```bash
# 跟踪 Zygote fork + exec
adb shell "strace -f -e trace=clone,clone3,execve -p $(pidof zygote64)" 2>&1
```

输出（典型 Android 14 应用启动）：

```
clone3(...) = 12345                            ← fork 子进程
[pid 12345] execve("/system/bin/app_process64", ["app_process64", ...]) = 0
[pid 12345] execve("/data/app/.../base.apk", [...]) = 0
```

应用进程有 **2 次 execve**：
1. 第一次：exec `/system/bin/app_process64`（Android Runtime 入口）
2. 第二次：exec `/data/app/<pkg>/base.apk`（真正的应用可执行文件）

这是 Android 特有的 exec 模式——04 篇后面会展开。

### 1.3 execve 不会返回（成功时）

**最重要的语义**：`execve` 成功时**不会返回到调用方**。

- 失败时：返回 -1，errno 表明原因（ENOEXEC / EACCES / E2BIG 等）
- 成功时：**当前进程被完全替换**——task_struct 复用，但地址空间、文件描述符表（除非带 flag）、信号处理、凭证等被重置

```c
// Bionic 内部
int __execve(const char *pathname, char *const argv[], char *const envp[]) {
    // 走 syscall
    long ret = __bionic_syscall(SYS_execve, pathname, argv, envp);
    // syscall 不会返回到 syscall 之后——成功时 CPU 直接跳到新程序入口
    if (ret == -1) return -1;  // 只有失败时才会到这
    __builtin_unreachable();   // 编译器优化：告诉编译器后面不会到
}
```

**关键认知**：
- execve 成功时，**task_struct 不会释放**——只是它的内容（mm / files / signal 等）被换掉
- task_struct 的 PID 不变
- 这就是为什么 exec 后的进程还能用 `getpid()` 拿到原 PID
- 也为什么"Zygote fork + exec 优化"是可能的——exec 不创建新进程，只是替换内容

---

## 二、内核入口：sys_execve → do_execveat_common

### 2.1 系统调用入口链

```
用户态
─────
execve("/system/bin/ls", argv, envp)
  ↓ Bionic __execve wrapper
[syscall 指令]

内核态
─────
  ↓ entry_SYSCALL_64 (arch/arm64/kernel/entry.S)
  ↓ sys_execve (kernel/exec.c)
  ↓ do_execveat_common(AT_FDCWD, "/system/bin/ls", argv, envp, 0)
  ↓ do_execveat(fd, filename, argv, envp, flags)
  ↓ alloc_bprm(fd, filename)  ← 分配 linux_binprm
  ↓ bprm_execve(bprm, fd, filename, 0)
  ↓ exec_binprm(bprm)
  ↓ search_binary_handler(bprm)
  ↓ 遍历 formats 链表（fmt = ELF / script / misc）
  ↓ 命中 → fmt->load_binary(bprm)  ← load_elf_binary / load_script_binary
  ↓ 成功 → start_thread(regs, ...);  ← 修改用户态寄存器，准备跳到新入口
  ↓ 返回 (long) 0 → pt_regs
```

### 2.2 关键源码入口

```c
// kernel/exec.c
SYSCALL_DEFINE3(execve,
                const char __user *, filename,
                char __user *const __user *, argv,
                char __user *const __user *, envp)
{
    return do_execveat_common(AT_FDCWD, filename, argv, envp, 0);
}

// 内核 5.x 之后，execveat 是更通用的入口
SYSCALL_DEFINE5(execveat,
                int, fd,
                const char __user *, filename,
                char __user *const __user *, argv,
                char __user *const __user *, envp,
                int, flags)
{
    return do_execveat_common(fd, filename, argv, envp, flags);
}
```

**关键点**：
- `AT_FDCWD`（值是 -100）是特殊的 fd，表示"用 cwd 作为基准目录"——execve 等价于 `execveat(AT_FDCWD, ...)`
- `do_execveat_common` 是**唯一的 exec 入口**——所有变种最终走这里
- `flags` 通常是 0，特殊值包括 `AT_EMPTY_PATH`（允许 `execveat(fd, "", ...)` 执行 fd 指向的文件）

### 2.3 do_execveat_common 的整体结构

```c
// kernel/exec.c
static int do_execveat_common(int fd, struct filename *name,
                              struct user_arg_ptr argv,
                              struct user_arg_ptr envp,
                              int flags)
{
    char *pathbuf;
    struct linux_binprm *bprm;
    int retval;

    // 1. 准备 pathbuf（用于搜索 PATH、解析符号链接）
    pathbuf = getname(name);
    if (IS_ERR(pathbuf)) return PTR_ERR(pathbuf);

    // 2. 分配 linux_binprm（核心结构！下面 §3 详讲）
    bprm = alloc_bprm(fd, pathbuf);
    if (IS_ERR(bprm)) {
        putname(pathbuf);
        return PTR_ERR(bprm);
    }

    // 3. 从用户态复制 argv / envp 到内核
    retval = count(argv, MAX_ARG_STRINGS);
    if (retval < 0) goto out;
    bprm->argc = retval;

    retval = count(envp, MAX_ARG_STRINGS);
    if (retval < 0) goto out;
    bprm->envc = retval;

    retval = prepare_binprm(bprm);
    if (retval < 0) goto out;

    // 4. 复制参数到栈底（exec 后用户态能直接访问 argv）
    retval = copy_strings_kernel(bprm->argc, bprm->envc, bprm);
    if (retval < 0) goto out;

    // 5. 真正执行
    retval = bprm_execve(bprm, fd, pathbuf, flags);
out:
    return retval;
}
```

**关键路径**：
- `alloc_bprm()` 分配 `linux_binprm`——这是 execve 的"工作台"
- `prepare_binprm()` 打开可执行文件、读前 128 字节到 bprm->buf、判断格式魔数
- `bprm_execve()` 调 `exec_binprm` → `search_binary_handler` → 走 `load_elf_binary` 等具体 handler

接下来 §3 详讲 `linux_binprm` 这个核心结构。

---

## 三、内核的"桥梁结构"：linux_binprm

### 3.1 linux_binprm 是什么

`linux_binprm` 是 execve 路径上的"工作台"——它在内核中是一个临时结构，记录了 execve 执行过程中需要的全部状态：

```c
// include/linux/binfmts.h
struct linux_binprm {
    char buf[BINPRM_BUF_SIZE];        // 128 字节：可执行文件前 128 字节（用于格式识别）
    struct vm_area_struct *vma;       // 当前 vma（用于 stack / 参数复制）
    unsigned long vma_pages;          // vma 页数
    struct mm_struct *mm;             // 目标 mm（exec 完成后赋值给 current->mm）
    unsigned long p;                  // 当前游标（在 copy_strings 时使用）
    unsigned int called_set_creds:1,  // 是否已经设置过 cred
                 cap_effective:1,    // 是否需要 cap_effective
                 secureexec:1;       // 是否需要 at_secure
    unsigned int recursion_depth;     // binfmt 递归深度（防无限递归）
    struct file *file;                // 可执行文件的 struct file
    struct cred *cred;                // 临时 cred
    int unsafe;                       // LSM 是否认为此 exec 不安全
    unsigned int per_clear;           // personality flags to clear
    int argc, envc;                   // 参数 / 环境变量计数
    const char *filename;             // 用户态传入的文件名
    const char *interp;               // 动态链接器路径（load_elf_binary 时设置）
    const char *fdpath;               // /proc/<pid>/fd 路径
    unsigned interp_flags;            // 解释器 flags
    int execfd;                       // execveat 用
    unsigned long loader, exec;       // 加载器 / 程序入口
    struct rlimit rlim_stack;          // 当前进程的栈 rlimit
    char buf_ext[BINPRM_BUF_EXT_SIZE];// 扩展 buffer（用于压缩格式）
};
```

**关键字段**：
- `buf[128]`：可执行文件前 128 字节。`search_binary_handler` 靠这个判断格式
- `file`：`struct file *`——可执行文件在内核中的表示
- `cred`：临时凭证——exec 后会替换 current->cred
- `interp`：动态链接器路径（如 `/system/bin/linker64`）——load_elf_binary 解析 ELF 时设置
- `loader` / `exec`：动态链接器入口地址 + 程序入口地址

### 3.2 prepare_binprm：填充 buf 和打开文件

```c
// fs/exec.c
int prepare_binprm(struct linux_binprm *bprm)
{
    int retval = 0;
    struct file *file = bprm->file;

    // 1. 读前 128 字节到 buf
    retval = kernel_read(file, bprm->buf, BINPRM_BUF_SIZE, &pos);
    if (retval < 0) goto out;
    bprm->buflen = retval;

    // 2. 检查是否为脚本（#!开头）
    if (bprm->buflen >= 2 && bprm->buf[0] == '#' && bprm->buf[1] == '!') {
        // 走 load_script_binary 路径——本篇 §4.2 详讲
    }

    // 3. 设置 cred
    bprm->cred = prepare_exec_creds();
    if (IS_ERR(bprm->cred)) {
        retval = PTR_ERR(bprm->cred);
        goto out;
    }

    // 4. 关闭 close-on-exec 的 fd
    do {
        unsigned long close_on_exec = current->files->close_on_exec;
        // ...
    } while (...);

out:
    return retval;
}
```

**关键认知**：
- 读前 128 字节是**格式识别的关键**——内核不解析整个文件，只看 128 字节判断是 ELF / 脚本 / 压缩格式
- `prepare_exec_creds()` 准备新 cred——这与 exec 后的 UID/EUID 变化相关
- `close-on-exec` 的 fd 在 exec 之前被关闭（这是 O_CLOEXEC 标志的真正落实点）

### 3.3 copy_strings_kernel：参数压栈

`copy_strings_kernel()` 把 argv / envp 从用户态复制到内核栈底——这是后续 `start_thread()` 时把它们摆到新进程用户栈顶的依据：

```c
// fs/exec.c
static int copy_strings_kernel(int argc, int envc, struct linux_binprm *bprm)
{
    // 1. 复制 envp（从后往前）
    while (envc-- > 0) {
        // 从用户态复制单个环境变量字符串
        // 把它放在 bprm->p 指向的内核栈位置
        bprm->p -= len;
        copy_from_user(bprm->p, str, len);
    }

    // 2. 复制 argv（从后往前）
    while (argc-- > 0) {
        bprm->p -= len;
        copy_from_user(bprm->p, str, len);
    }

    return 0;
}
```

**关键认知**：
- 内核栈是临时的——exec 完成后，参数会被复制到新进程的用户栈顶
- 参数顺序是**从后往前**压栈——保证新进程 `argv[0]` 在最高地址（栈顶）
- `bprm->p` 游标从栈底向低地址走——这是栈的增长方向

---

## 四、search_binary_handler：二进制格式分发

### 4.1 formats 链表

内核支持多种可执行文件格式——ELF、脚本（#!）、a.out、Misc（Java 等）。它们通过 `linux_binfmt` 注册：

```c
// include/linux/binfmts.h
struct linux_binfmt {
    struct list_head lh;            // 链表节点
    const char *name;               // 格式名（"elf" / "script" / "misc"）
    int (*load_binary)(struct linux_binprm *);   // 加载函数
    int (*load_shlib)(struct file *);            // 动态库加载函数
    int (*core_dump)(struct coredump_params *);  // core dump 函数
    unsigned long min_coredump;     // 最小 core 大小
} __randomize_layout;

// 注册（fs/binfmt_elf.c）
static struct linux_binfmt elf_format = {
    .module         = THIS_MODULE,
    .load_binary    = load_elf_binary,
    .load_shlib     = load_elf_library,
    .core_dump      = elf_core_dump,
    .min_coredump   = ELF_EXEC_PAGESIZE,
};
module_init(register_elf_binfmt);
```

**Android 14 上注册的格式**：

```bash
# 看 /proc/sys/fs/binfmt_misc 注册的格式
adb shell "cat /proc/sys/fs/binfmt_misc/status"
```

典型输出：

```
enabled
```

```bash
adb shell "ls /proc/sys/fs/binfmt_misc/"
```

输出：

```
android_app_image    ← Android 应用的 zip 格式（misc binfmt）
status
```

**关键**：
- Android 14 默认有 `elf`（来自 `fs/binfmt_elf.c`）+ `script`（来自 `fs/binfmt_script.c`）+ `misc`（`fs/binfmt_misc.c`）+ `android_app_image`（Android 特殊注册）

### 4.2 search_binary_handler：尝试所有格式

```c
// fs/exec.c
static int search_binary_handler(struct linux_binprm *bprm)
{
    struct linux_binfmt *fmt;
    int retval;

    retval = search_binary_handler_recursive(bprm, 0);
    return retval;
}

static int search_binary_handler_recursive(struct linux_binprm *bprm, int level)
{
    // 1. 限制递归深度（防 #! 无限嵌套）
    if (level >= BINPRM_MAX_RECURSION)
        return -ELOOP;

retry:
    // 2. 遍历所有注册的 binfmt
    read_lock(&binfmt_lock);
    list_for_each_entry(fmt, &formats, lh) {
        if (!try_module_get(fmt->module))
            continue;
        read_unlock(&binfmt_lock);

        // 3. 尝试这个格式
        retval = fmt->load_binary(bprm);
        if (retval >= 0) {
            // 成功！exec 完成
            put_binfmt(fmt);
            return retval;
        }

        // 4. 失败，尝试下一个
        read_lock(&binfmt_lock);
        put_binfmt(fmt);
        if (retval != -ENOEXEC && retval != -EINVAL)
            return retval;  // 致命错误，不是 ENOEXEC 直接返回
    }
    read_unlock(&binfmt_lock);

    // 5. 脚本（#!）特殊处理
    if (bprm->buf[0] == '#' && bprm->buf[1] == '!') {
        retval = load_script_binary(bprm);
        // 脚本加载：把 interpreter 路径提取出来
        // 重新走 search_binary_handler 加载 interpreter
        // 这就是"递归"
    }

    return -ENOEXEC;  // 都没匹配
}
```

**关键认知**：
- 内核按 `formats` 链表的顺序尝试每种格式——先 ELF、再 script、再 misc
- 每个格式的 `load_binary` 返回：
  - `>= 0`：成功
  - `-ENOEXEC`：格式不匹配，尝试下一个
  - 其他负值：致命错误
- **脚本** 是特例：识别出 `#!` 后，加载脚本解释器（如 `/bin/bash`），然后**递归**调用 search_binary_handler

### 4.3 脚本（#!）的特殊路径

脚本处理是 execve 最有趣的部分之一：

```bash
#!/system/bin/sh
echo "hello"
```

内核看到 `#!` 后走 `load_script_binary`：

```c
// fs/binfmt_script.c
static int load_script_binary(struct linux_binprm *bprm)
{
    // 1. 解析 #! 行
    // 例：#!/system/bin/sh -x
    //     interpreter = "/system/bin/sh"
    //     arg         = "-x"
    char *cp, *interp, *i_name;
    cp = bprm->buf + 2;  // 跳过 "#!"
    while (*cp == ' ') cp++;
    interp = cp;
    while (*cp && *cp != ' ' && *cp != '\n') cp++;
    // ... 解析 ...

    // 2. 把 interpreter 路径设置回 bprm
    bprm->interp = interp;

    // 3. 把 interpreter 作为新的可执行文件
    bprm->file = open_executable_file(bprm->interp);
    if (IS_ERR(bprm->file)) return PTR_ERR(bprm->file);

    // 4. 重新读前 128 字节
    kernel_read(bprm->file, bprm->buf, BINPRM_BUF_SIZE, NULL);

    // 5. 重新走 search_binary_handler（递归！）
    return search_binary_handler_recursive(bprm, 1);
}
```

**关键认知**：
- 脚本不是"被解析执行"——是**被翻译成 exec interpreter** 后再 exec
- `#!/system/bin/sh -x hello.sh`：内核会 exec `/system/bin/sh` 并把 `-x hello.sh` 作为 argv 前缀
- 递归深度限制 `BINPRM_MAX_RECURSION`（默认 4）——防止恶意 `#!` 循环

**Android 14 上的脚本**：
- `/system/bin/sh` 是真实的 ELF 文件（Bionic ash）
- 应用通常不用脚本（dex 编译后没有 #!）
- 调试时 `setprop debug.keepapp.shell 1` 才会启用某些脚本

### 4.4 命中 ELF 格式：load_elf_binary

如果文件是 ELF 格式（魔数 `0x7f 'E' 'L' 'F'`），`load_elf_binary` 被调用：

```c
// fs/binfmt_elf.c
static int load_elf_binary(struct linux_binprm *bprm)
{
    // 1. 解析 ELF 头
    // 2. 遍历 program header
    // 3. 加载所有 PT_LOAD 段
    // 4. 如果有 PT_INTERP，加载动态链接器
    // 5. 构造用户态栈
    // 6. start_thread(regs, e_entry, ...)
}
```

下一章展开这个函数。

---

## 五、load_elf_binary 完整路径

### 5.1 ELF 基础回顾

ELF（Executable and Linkable Format）文件结构：

```
+---------------------------+
|       ELF Header          |  ← 必选，文件开头
|  e_ident / e_type / ...   |
+---------------------------+
|    Program Header Table   |  ← 运行时使用
|  PT_LOAD / PT_INTERP / ...|
+---------------------------+
|        Sections           |  ← 链接时使用
|  .text / .data / .rodata  |
+---------------------------+
|    Section Header Table   |  ← 链接时使用
+---------------------------+
```

**关键 Program Header 类型**：

| 类型 | 含义 | load_elf_binary 行为 |
|---|---|---|
| `PT_LOAD` | 可加载段 | 映射到用户空间 |
| `PT_INTERP` | 动态链接器路径 | 加载 interpreter |
| `PT_DYNAMIC` | 动态链接信息 | 传给动态链接器 |
| `PT_GNU_STACK` | 栈权限 | 决定是否可执行栈 |
| `PT_GNU_RELRO` | 只读重定位 | mprotect 标只读 |

### 5.2 load_elf_binary 第一阶段：解析 ELF 头

```c
// fs/binfmt_elf.c
static int load_elf_binary(struct linux_binprm *bprm)
{
    struct elfhdr elf_ex;     // ELF 头
    struct elfhdr interp_ex;  // interpreter 的 ELF 头
    struct elf_phdr *elf_phdata;  // program header 表
    unsigned long elf_entry;
    int retval;

    // 1. 复制 ELF 头（用户态 → 内核栈）
    retval = elf_read(bprm->file, &elf_ex, sizeof(elf_ex), 0);
    if (retval < 0) goto out;

    // 2. 验证魔数
    if (memcmp(elf_ex.e_ident, ELFMAG, SELFMAG) != 0)
        goto out;

    // 3. 验证 class（32 / 64 bit）
    if (elf_ex.e_ident[EI_CLASS] != ELFCLASS32 &&
        elf_ex.e_ident[EI_CLASS] != ELFCLASS64)
        goto out;

    // 4. 验证 machine
    if (elf_ex.e_machine != EM_ARM && elf_ex.e_machine != EM_AARCH64)
        goto out;

    // 5. 读取 program header 表
    elf_phdata = kmalloc(sizeof(struct elf_phdr) * elf_ex.e_phnum, GFP_KERNEL);
    elf_read(bprm->file, elf_phdata,
             sizeof(struct elf_phdr) * elf_ex.e_phnum,
             elf_ex.e_phoff);
    elf_ppnt = elf_phdata;
}
```

**关键认知**：
- 魔数验证很严格——任何偏移 0-3 字节不对的"ELF"都失败
- Android 14 上运行的是 AArch64（`EM_AARCH64 = 183`）——ARM32（`EM_ARM = 40`）已经很少见
- program header 表读到**内核内存**——后续 `elf_ppnt` 遍历它做映射

### 5.3 第二阶段：遍历 program header

```c
    // 1. 第一次遍历：找到 PT_INTERP（动态链接器路径）
    for (i = 0; i < elf_ex.e_phnum; i++) {
        if (elf_ppnt[i].p_type == PT_INTERP) {
            retval = elf_read(bprm->file, elf_interpreter,
                              elf_ppnt[i].p_filesz,
                              elf_ppnt[i].p_offset);
            if (retval < 0) goto out_free_dentry;
            interp_ex = *elf_ppnt;  // 保存 interpreter 的 program header
            interpreter = elf_interpreter;
            break;
        }
    }

    // 2. 第二次遍历：映射所有 PT_LOAD 段
    for (i = 0; i < elf_ex.e_phnum; i++) {
        if (elf_ppnt[i].p_type == PT_LOAD) {
            elf_map(bprm->file, load_bias + vaddr, elf_ppnt + i,
                    elf_prot, elf_flags, total_size);
        }
    }
```

**关键认知**：
- 第一次遍历是找 interpreter——这是为了**先**加载 interpreter，**再**映射主程序
- 第二次遍历才真正把 PT_LOAD 段映射到用户空间
- `load_bias` 是加载偏移——Android 14 上默认 PIE（位置无关可执行）需要这个偏移

### 5.4 PT_LOAD 段映射：elf_map

```c
// fs/binfmt_elf.c
static unsigned long elf_map(struct file *filep, unsigned long addr,
                             const struct elf_phdr *eppnt, int prot, int type,
                             unsigned long total_size)
{
    unsigned long map_addr;
    unsigned long size = eppnt->p_filesz + ELF_PAGEOFFSET(eppnt->p_vaddr);
    unsigned long off = eppnt->p_offset - ELF_PAGEOFFSET(eppnt->p_vaddr);

    // 1. mmap 到用户空间
    map_addr = vm_mmap(filep, addr, size, prot, type, off);
    if (map_addr == -EINVAL || map_addr < 0)
        return map_addr;

    return map_addr;
}
```

**关键认知**：
- 实际是 `mmap()` 到用户空间——`vma->vm_file = bprm->file`（vma 与可执行文件关联）
- 内存不足时 `vm_mmap()` 返回负值——exec 失败
- 这就是为什么"启动大应用"会先卡顿——可能触发 mmap 失败导致 exec 失败

### 5.5 处理动态链接器（PT_INTERP）

如果 ELF 包含 PT_INTERP（如 `/system/bin/linker64`），内核需要"借壳"加载它：

```c
    // 1. 打开 interpreter
    if (interpreter) {
        bprm->interp = interpreter;
        bprm->file = open_executable_file(interpreter);
        if (IS_ERR(bprm->file)) {
            retval = PTR_ERR(bprm->file);
            goto out_free_dentry;
        }

        // 2. 解析 interpreter 的 ELF 头
        elf_read(bprm->file, &interp_ex, sizeof(interp_ex), 0);

        // 3. 把 interpreter 映射到用户空间
        // interpreter 通常在比主程序更高的虚拟地址
        for (i = 0; i < interp_ex.e_phnum; i++) {
            if (interp_elf_ppnt[i].p_type == PT_LOAD) {
                elf_map(bprm->file, load_bias + vaddr,
                        interp_elf_ppnt + i, ...);
            }
        }
    }
```

**关键认知**：
- 内核不"执行" interpreter——它只是把 interpreter 加载到内存
- interpreter 的入口地址存到 `bprm->loader`——这是用户态第一条指令的地址
- 主程序的入口地址存到 `bprm->exec`——interpreter 会找到并跳转

**Android 14 上的 interpreter**：
- `/system/bin/linker64`（AArch64）
- `/system/bin/linker`（ARM 32）
- `/system/bin/linker_sleb128`（带调试信息的 linker）

### 5.6 构造用户态栈：create_elf_tables

```c
    // fs/binfmt_elf.c
    // 构造新进程用户栈底——包含：
    // - 程序名（filename）
    // - 环境变量（envp）
    // - 参数（argv）
    // - ELF 辅助向量（auxv）
    retval = create_elf_tables(bprm, &elf_ex, interp_ex, ...);
```

`create_elf_tables` 把以下内容按特定顺序压栈：

```
高地址（栈顶）
  ┌──────────────┐
  │  字符串区     │  ← filename, envp[], argv[] 的实际字符串
  │  filename    │
  │  argv[0]     │
  │  argv[1]     │
  │  envp[0]     │
  │  ...         │
  ├──────────────┤
  │  auxv[]      │  ← ELF 辅助向量（AT_PHDR / AT_ENTRY / AT_BASE 等）
  ├──────────────┤
  │  NULL        │  ← envp 数组的结束
  ├──────────────┤
  │  envp[n-1]   │
  │  ...         │
  │  envp[0]     │
  ├──────────────┤
  │  NULL        │  ← argv 数组的结束
  ├──────────────┤
  │  argv[argc-1]│
  │  ...         │
  │  argv[0]     │
  ├──────────────┤
  │  argc        │  ← exec 后的栈顶
低地址
```

**关键**：
- exec 后新进程入口收到的栈就是这个样子
- `argc` 在最低地址，**这就是 `main(argc, argv, envp)` 的来源**
- `auxv` 包含关键信息：`AT_ENTRY`（主程序入口）、`AT_PHDR`（program header 虚拟地址）、`AT_BASE`（interpreter 加载地址）

### 5.7 start_thread：跳到 interpreter 入口

```c
    // arch/arm64/kernel/process.c
    void start_thread(struct pt_regs *regs, unsigned long pc,
                      unsigned long sp)
    {
        // 1. 清空大部分寄存器
        memset(regs, 0, sizeof(*regs));

        // 2. 设置 PC（程序计数器）= interpreter 入口
        regs->pc = pc;
        regs->sp = sp;

        // 3. 清除 FPU 状态
        fpsimd_flush_task_state(current);

        // 4. 标记线程信息
        current->thread.fault_address = 0;
        current->thread.fault_code = 0;
    }

    // 调用
    start_thread(regs, elf_entry, bprm->p);
```

**关键**：
- `elf_entry` 是 interpreter 入口（`/system/bin/linker64` 起点）——**不是**主程序入口
- `bprm->p` 是新栈顶
- 从这一刻起，调度器切回这个进程时，它会从 interpreter 开始跑——不再是 fork 后的 `ret_from_fork`

**完整调用链**：

```
sys_execve → do_execveat_common → alloc_bprm → prepare_binprm
  → bprm_execve → exec_binprm → search_binary_handler
  → load_elf_binary → elf_map(主程序) + elf_map(interpreter)
  → create_elf_tables → start_thread(regs, interp_entry, stack_top)
  → 返回到用户态时，CPU 跳到 interp_entry
```

下一章展开动态链接器本身怎么工作。

---

## 六、动态链接器：ld.so / Android linker 怎么工作

### 6.1 为什么需要动态链接器

ELF 可执行文件可以**静态链接**或**动态链接**：

- **静态链接**：所有库代码打包到 ELF 内部——文件大，但启动快、不依赖库
- **动态链接**：库代码在运行时由 `ld.so`（Linux）/ `linker64`（Android）加载——文件小，多个进程共享库

现代 Android 14 上**几乎所有应用都是动态链接**：

```bash
# 看应用的依赖库
adb shell "ldd /system/bin/ls"  # Linux 工具，Android 上不一定可用

# Android 用 readelf 看
adb shell "readelf -d /system/bin/app_process64 | grep NEEDED"
```

输出（典型）：

```
 0x0000000000000001 (NEEDED)             Shared library: [libc.so]
 0x0000000000000001 (NEEDED)             Shared library: [libdl.so]
 0x0000000000000001 (NEEDED)             Shared library: [liblog.so]
 0x0000000000000001 (NEEDED)             Shared library: [libutils.so]
```

### 6.2 动态链接器在内核视角的"被加载"

内核只负责"把 dynamic linker 加载到用户空间"——dynamic linker 的"执行"完全是用户态的事：

```c
// load_elf_binary 路径上的关键点
bprm->loader = interp_entry;   // 记录 dynamic linker 入口
bprm->exec   = elf_ex.e_entry; // 记录主程序入口
start_thread(regs, interp_entry, bprm->p);
```

**关键认知**：
- 第一个跑的代码是 **dynamic linker**，不是 main 函数
- dynamic linker 完成库的加载后，才跳到主程序入口
- 整个过程对内核透明——内核只看到"一个 ELF 加载完成"

### 6.3 dynamic linker 内部流程（用户态）

**Linux glibc ld.so**（glibc-2.x）：

```
_start (汇编入口)
  ↓
__libc_start_main()
  ↓
1. 解析 ELF 头找到 PT_DYNAMIC 段
2. 遍历动态段：DT_NEEDED / DT_SYMTAB / DT_STRTAB / DT_JMPREL ...
3. 加载所有 NEEDED 库（递归）
   ↓
   打开 libfoo.so → mmap → 查符号表 → 重定位 → 注册到全局符号表
4. 处理重定位（RELRO / IRELATIVE / JMPREL）
   ↓
5. 调用所有 DT_INIT / DT_INIT_ARRAY
6. 跳到主程序入口（e_entry）
   ↓
main(argc, argv, envp)
```

**Android Bionic linker**（bionic/linker/）：

Android 14 的 linker 实现（`linker64`）路径：

```
bionic/linker/linker_main.cpp
  ↓ linker_main()
  1. 解析 ELF 头
  2. 加载所有 NEEDED 库（ld_library_list 顺序）
     ↓
     soinfo_alloc / load_library
     ↓
     打开 .so 文件 → mmap → parse_elf → register_soinfo
  3. 重定位（relocator.RelaPlt / RelaRel）
  4. 调用 DT_INIT / DT_INIT_ARRAY
  5. 跳到主程序入口
  ↓
main(argc, argv, envp)
```

**关键差异**（Linux glibc vs Android linker）：

| 维度 | glibc ld.so | Android linker |
|---|---|---|
| 链接器路径 | `/lib64/ld-linux-x86-64.so.2` 等 | `/system/bin/linker64` |
| 命名空间 | 单全局 | 支持 namespace（Android 10+） |
| soname 解析 | 按 ld.so.cache | 按 `/system/etc/public.libraries.txt` 等 |
| 加载策略 | 按需 lazy binding | 既支持 lazy，也支持 now |

### 6.4 namespace：Android 10+ 的关键机制

Android 10 引入了 **library namespace**——每个应用只看自己"可见"的库：

```bash
# 看当前进程的 linker namespace
adb shell "cat /proc/$(pidof system_server)/maps | grep linker64"
```

输出（节选）：

```
7f9a8b0000-7f9a8c0000 r--p 00000000 fd:05 1234  /system/bin/linker64
```

**Android 14 的 namespace 机制**：
- 默认 namespace（`default`）：所有应用可见的平台库
- `vndk` namespace：供应商可见的 VNDK 库
- 应用私有 namespace：应用私有目录的库

**关键**：
- 不同 namespace 看到不同的 `/system/lib/` 子集
- namespace 不影响 `dlopen()` 行为——只影响"哪些库被自动加载"
- 这与 SELinux context 配合实现库隔离

### 6.5 重定位的两种类型

动态链接器做两件事：

#### 6.5.1 全量重定位（Eager / Now）

```bash
# 启动时 LD_BIND_NOW=1 强制全量重定位
adb shell "LD_BIND_NOW=1 /system/bin/ls"
```

优：运行时调用函数无开销
缺：启动慢

#### 6.5.2 懒加载重定位（Lazy / PLT）

默认行为——函数第一次被调用时才解析：

```c
// 编译为
call printf@plt   ← 第一次会跳到 PLT
                    ← PLT 跳到 resolver
                    ← resolver 找真实地址并修改 PLT
                    ← 第二次直接跳到真实地址
```

优：启动快
缺：第一次调用有开销

**Android 14 上的现实**：
- 系统库（`libc.so` / `liblog.so`）默认 lazy
- 性能敏感路径（`libart.so`）用 RELRO + BIND_NOW
- ART 编译时把 .so 链接成"运行时全量重定位"——这是 ART 启动快的原因之一

### 6.6 ld.so 与 Zygote fork 的关系

Zygote 在 fork 时**已经加载了所有常用库**（`libc.so` / `libart.so` / `framework.jar` 等）：

```bash
# 看 Zygote 进程的 maps
adb shell "cat /proc/$(pidof zygote64)/maps | head -50"
```

输出（节选）：

```
7f9a8b0000-7f9a8c0000 r--p  /system/bin/linker64
7f9a8c0000-7f9b000000 r-xp  /system/bin/linker64
7f9b000000-7f9b040000 r--p  /system/lib64/libc.so
7f9b040000-7f9b080000 r-xp  /system/lib64/libc.so
7f9b080000-7f9b0c0000 r--p  /system/lib64/libc.so
...
```

Zygote fork 出应用进程后，应用进程的地址空间**共享**这些库（COW）。但 exec 后：

1. exec `/system/bin/app_process64` → 内核替换 mm
2. exec `/data/app/<pkg>/base.apk` → 内核再次替换 mm
3. **每次 exec 都会丢弃之前的 mm**——所以 Zygote 预加载的"成果"在应用进程 exec 后**完全失效**

这就是为什么 Zygote 优化集中在"fork 阶段"（03 篇 §10 详讲）——exec 之后，进程是"全新"的。

下一章展开"exec 之后地址空间是什么样"。

---

## 七、exec 之后：进程地址空间成型

### 7.1 exec 后的 VMA 布局

exec 完成后，进程的虚拟地址空间大致是这样的（Android 14 AArch64）：

```
高地址
  0x0000_7fff_ffff_ffff
    ↓
  ┌─────────────────────────┐
  │  内核空间                │  ← 0xffff_0000_0000_0000+
  └─────────────────────────┘
    ↓
  ┌─────────────────────────┐
  │  用户栈                  │  ← ~0x0000_7fff_ffff_0000
  │  (top: 8MB 向下增长)     │     exec 时构造的栈
  ├─────────────────────────┤
  │  vvar / vdso             │  ← 内核提供的 vDSO（gettimeofday 等）
  ├─────────────────────────┤
  │  mmap 区                │  ← 大块匿名 mmap / 共享库
  │  (共享库 + 动态 mmap)   │
  ├─────────────────────────┤
  │  heap                   │  ← malloc 增长
  ├─────────────────────────┤
  │  bss                    │  ← 未初始化数据
  ├─────────────────────────┤
  │  data                   │  ← 已初始化数据
  ├─────────────────────────┤
  │  text                   │  ← 代码段（r-xp）
  └─────────────────────────┘
  0x0000_0000_0000_0000
低地址
```

**关键**：
- 文本段是 r-xp（只读可执行）—— 不可写
- 数据段是 rw-p（读写）—— 程序运行中可改
- 共享库 mmap 到 text 上方的"中间地带"

### 7.2 ASLR：exec 时的地址随机化

Android 14 默认开启 ASLR（Address Space Layout Randomization）：

```bash
# 看 ASLR 配置
adb shell "cat /proc/sys/kernel/randomize_va_space"
```

输出：

```
2   ← 完整 ASLR
```

**exec 时内核做的随机化**：
- mmap base 随机：共享库加载基地址变化
- heap base 随机：堆起点变化
- stack top 随机：栈顶变化
- ELF loader / executable 加载基址随机（PIE）

```bash
# 两次执行 ls，看 mmap 区域地址变化
adb shell "/system/bin/ls" > /dev/null
adb shell "cat /proc/$(pidof ls)/maps | grep libc.so" 2>/dev/null
# 杀进程后再次执行
```

**关键**：
- ASLR 让攻击者难以预测地址——防御漏洞利用
- 调试时可以用 `setprop debug.aslr 0` 关闭（仅 debug build）
- 性能影响：mmap 阶段需要更复杂的地址选择

### 7.3 exec 后的 task_struct 变化

exec 改变了 task_struct 的**多个字段**：

| 字段 | exec 前 | exec 后 |
|---|---|---|
| `mm` | 父进程 mm | 新 mm（empty → 被 elf_map 填充） |
| `active_mm` | 同上 | 同上 |
| `files` | 父进程 files_struct（共享） | 复制 + 关闭 CLOEXEC fd |
| `cred` | 父进程 cred | 新 cred（prepare_exec_creds） |
| `signal->sighand` | 父进程 sighand（共享） | 复制 |
| `comm` | 父进程 comm | 截取可执行文件名（如 `ls`、`app_process64`） |
| `flags & PF_FORKNOEXEC` | 设置 | **清除** |
| `thread_info->cpu_context` | 父进程寄存器 | 指向 interpreter 入口 |

**关键认知**：
- `comm`（进程名）来自 `set_task_comm()`——默认是 ELF 文件名（去掉路径）
- `PF_FORKNOEXEC` 被清除——这影响 cgroup memory 统计（03 篇 §4.8 详讲）
- task_struct 的 PID 不变——这是 exec 不是 fork 的本质区别

### 7.4 comm 字段：进程名的来源

```c
// fs/exec.c
static int exec_binprm(struct linux_binprm *bprm)
{
    // ...
    // 截取可执行文件名（最多 15 字符）
    set_task_comm(current, kbasename(bprm->filename));
    // ...
}
```

`kbasename` 提取路径的 basename：`/system/bin/ls` → `ls`。

```bash
# 看进程的 comm
adb shell "cat /proc/$$/comm"
# 输出: sh
```

**Android 14 特殊情况**：
- `app_process64` 是 zygote fork 后的第一个 exec
- `com.example.app` 是第二个 exec 后的 comm
- 但 `ps` 显示的是 `task_struct->comm` 截断到 15 字符

### 7.5 内存账户更新

exec 后，多个内存账户更新：

```c
// mm/memory.c
// 1. 旧的 mm_struct 释放
mmput(old_mm);

// 2. 新 mm 的统计初始化
mm->total_vm = 0;
mm->locked_vm = 0;
// ... 各种 counter ...

// 3. cgroup 内存统计
if (cgroup_subsys_on_dfl(memory_cgrp_subsys)) {
    // v2 模式：记入新 mm 的 cgroup
}
```

**关键**：
- 旧 mm 的页被释放——但物理页是否释放要看引用计数（COW 共享的页可能还被 Zygote 持有）
- 新 mm 重新从 0 开始计费——exec 不继承父进程的内存账户
- Android Zygote fork 优化的"成果"在 exec 后**完全丢弃**——所以应用冷启动慢

---

## 八、Android 14 实战：Zygote fork + exec 应用

### 8.1 完整的 exec 序列

Android 14 启动应用进程的完整 exec 序列：

```bash
# 抓取启动过程的 exec
adb shell "strace -f -e trace=clone,execve -p $(pidof zygote64) 2>&1 | grep execve" | head -20
```

典型输出：

```
[pid 12345] execve("/system/bin/app_process64",
                   ["app_process64", "-Xzygote",
                    "/system/bin/app_process64",
                    "--zygote",
                    "--start-system-server",
                    "--socket-name=zygote",
                    "--enable-lazy-preload",
                    "--setresuid=1000:1000:1000",
                    "--nice-name=zygote",
                    "--runtime-args",
                    "--setgroups=1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1018,1021,1023,1024,1026,1027,1028,2029,3001,3002,3003,3006,3007,3009,3010",
                    "android.app.ActivityThread"],
                   0x7fc8...) = 0

[pid 12345] execve("/data/app/~~xyz==/com.example.app-abc==/base.apk",
                   ["com.example.app"],
                   0x7fc8...) = 0
```

**两次 exec**：
1. 第一次：`/system/bin/app_process64`——Android Runtime 入口
2. 第二次：`/data/app/<pkg>/base.apk`——真正的应用

### 8.2 第一次 exec：app_process64

`app_process64` 是 Android Runtime 的入口：

```c
// frameworks/base/cmds/app_process/app_main.cpp
int main(int argc, char* const argv[]) {
    // 1. 解析参数
    // 2. 区分 zygote mode 和普通 mode
    if (strcmp(argv[1], "--zygote") == 0) {
        // zygote 模式：启动 ZygoteInit
        runtime.start("ZygoteInit", ...);
    } else {
        // 普通 mode：启动应用
        runtime.start("ActivityThread", ...);
    }
}
```

**关键**：
- Zygote fork 时，传入的参数是 `--zygote`
- 应用 fork 时，传入的参数是 `-Xzygote` + 应用的 ActivityThread
- exec 替换的是 `app_process64` 的代码段——但 Zygote 的"已加载状态"被丢弃

### 8.3 第二次 exec：base.apk

`base.apk` 是应用的可执行文件——但它**不是 ELF**！它是 ZIP 格式：

```bash
# 看 APK 的实际格式
adb shell "head -c 4 /data/app/.../base.apk | xxd"
```

输出：

```
504b0304   ← "PK\x03\x04" ZIP 魔数
```

**关键**：
- APK 是 ZIP——内核怎么把它当 ELF 加载？
- 答案：`/system/bin/linker64` 接受 ZIP 格式（Android 特殊）
- 看 §4.1 提到的 `android_app_image` binfmt 注册——这是 Android 14 的特殊 binfmt

```bash
# 看注册的 binfmt_misc
adb shell "cat /proc/sys/fs/binfmt_misc/android_app_image"
```

输出（典型）：

```
enabled
interpreter /system/bin/linker64
flags: 0x1
offset 0
magic 504b0304
mask ffffffff
```

**含义**：
- 魔数 `504b0304`（PK\x03\x04）开头的文件被识别为 Android app image
- 内核把这种文件交给 `/system/bin/linker64` 处理
- linker64 内部解析 ZIP，找到 `classes.dex` 并加载

### 8.4 Zygote fork 优化在 exec 后的"失效"

**一个关键问题**：Zygote 预加载的所有类（`framework.jar`、`core-oj.jar` 等）在 fork 后通过 COW 共享给应用。但 exec 后：

```
Zygote mm ──COW──> 应用进程 mm (fork 时刻)
                  ↓
                  exec /system/bin/app_process64
                  ↓
                  内核：mmput(应用 mm)
                  ↓
                  内核：alloc mm (空)
                  ↓
                  内核：mmap app_process64 + libc.so + libart.so + ...
                  ↓
                  应用 mm (新)
```

**关键认知**：
- exec 时**旧 mm 被释放**——Zygote 预加载的页（如果没被其他进程使用）也被释放
- 新 mm 从零开始——Zygote 优化的"成果"在 exec 后**完全丢失**
- 唯一的"继承"是物理页缓存（page cache）——但 VMA 是空的

**为什么 Zygote 还要在 fork 前预加载？** 答案在 **fork 阶段**：
- fork 不释放物理页——只复制页表项
- 多个应用进程同时存在时，Zygote 预加载的页被**所有应用共享**
- 这是 03 篇 §10 详讲的 COW 优化

### 8.5 Android 14 性能数据：exec 开销

| 操作 | 大致耗时 | 说明 |
|---|---|---|
| exec 一个 100KB 的简单 ELF | ~1-2 ms | 解析 ELF + mmap |
| exec 一个 50MB 的应用 | ~5-20 ms | mmap 50MB + linker 加载 |
| exec + ART 启动 | ~50-200 ms | exec + 类的 linking + 静态初始化 |
| 完整应用冷启动 | ~500-1500 ms | exec + ART + Application.onCreate + Activity.onCreate |

**Android 14 的优化**：
- **ART image**（`/system/framework/boot.art`）—— AOT 编译的 ART 镜像
- **Profilo**——ART 性能追踪
- **Cloud profiles**——云端 profile 指导 AOT

这些优化在 exec 之后起作用——04 篇先讲 exec 本身的成本。

---

## 九、execve 失败的常见原因

### 9.1 失败 vs 致命错误

execve 失败的两种语义：

- **`-ENOEXEC`**：内核尝试了所有 binfmt 都不识别——文件不是有效可执行格式
- **其他负值**：致命错误，exec 直接失败

### 9.2 常见 errno 与原因

| errno | 含义 | 典型原因 |
|---|---|---|
| `ENOENT` | 文件不存在 | 路径错误、文件被删 |
| `EACCES` | 权限不足 | 文件无 execute 权限、被 SELinux 阻止 |
| `ENOEXEC` | 不是有效可执行文件 | ELF 魔数错、文件被破坏、不是 ELF 也不是脚本 |
| `E2BIG` | 参数总长超限 | argv + envp 超过 `MAX_ARG_STRLEN`（默认 2097152 字节） |
| `EFAULT` | 内存错误 | argv / envp 指针无效 |
| `ENOMEM` | 内存不足 | mmap 失败 |
| `ETXTBSY` | 文件被写 | 有人在写入可执行文件 |
| `ELOOP` | 符号链接循环 | `#!` 嵌套过深或软链循环 |
| `ELIBBAD` | 库损坏 | ELF interpreter 损坏 |
| `EISDIR` | 是目录 | execve 路径是目录 |
| `EMFILE` | 进程 fd 超限 | `RLIMIT_NOFILE` 超过 |
| `ENFILE` | 系统 fd 超限 | `/proc/sys/fs/file-max` 达到 |

### 9.3 Android 14 上的真实失败场景

**场景 1：脚本没有 #!**

```bash
echo 'echo hi' > /data/local/tmp/no_shebang.sh
chmod +x /data/local/tmp/no_shebang.sh
/data/local/tmp/no_shebang.sh
```

错误：

```
sh: exec: line 1: /data/local/tmp/no_shebang.sh: not found
```

内核返回 `-ENOEXEC`——`search_binary_handler` 都不识别。

**场景 2：可执行文件权限被 SELinux 阻止**

```bash
adb shell "ls -l /data/local/tmp/test_bin"
# -rwx------ root root
# SELinux: u:object_r:shell_data_file:s0
# 应用进程无 SELinux 权限执行
```

错误：

```
avc: denied { execute } for comm="..." name="test_bin" ...
```

**场景 3：APK 损坏**

```bash
adb shell "pm path com.example.app"
# 拿到的 base.apk 路径被损坏
# 启动时 execve 返回 -ENOEXEC
```

错误：

```
AndroidRuntime: Failed to exec, status: -ENOEXEC
```

### 9.4 排查 exec 失败的命令

```bash
# 1. 用 strace 看 execve 失败原因
adb shell "strace -f -e trace=execve /system/bin/ls" 2>&1

# 2. 看 binfmt_misc 注册的格式
adb shell "ls /proc/sys/fs/binfmt_misc/"
adb shell "cat /proc/sys/fs/binfmt_misc/android_app_image"

# 3. 看应用启动 logcat
adb logcat -b crash  # crash 日志
adb logcat | grep -E "AndroidRuntime|execve"

# 4. 看 SELinux 拒绝
adb shell "dmesg | grep avc"
```

### 9.5 exec 失败对 task_struct 的影响

**重要**：exec 失败时 task_struct **不变**——失败的 exec 不影响任何状态。

```c
// do_execveat_common 失败路径
out:
    return retval;  // 失败时只是返回错误码
// 没有 mmput / cred 释放
// current->mm 不变
// current->files 不变
```

**关键认知**：
- exec 失败 = 什么都没发生——task_struct 保持 fork 时的状态
- 这是"原子性"——要么全成功，要么全失败
- Zygote fork 后如果 exec 失败，会**回到 Zygote 的状态**——但实际上 Zygote 会直接终止子进程（子进程已经从 Zygote 分离）

---

## 十、安全性：execve 路径上的安全检查

### 10.1 noexec 挂载

文件系统可以标记 `noexec`——禁止 exec：

```bash
# 看挂载选项
adb shell "mount | grep -E 'noexec|exec'"
```

典型：

```
/data on /data type ext4 (rw,nosuid,nodev,noatime,noexec)
```

`/data` 标记 noexec——这意味着：
- `/data/local/tmp/test_bin` 不能 exec
- 这是 Android 14 防止恶意代码执行的策略

**内核实现**：

```c
// fs/exec.c
int bprm_execve(struct linux_binprm *bprm, int fd, ...)
{
    // 检查 noexec
    if (bprm->file->f_path.mnt->mnt_flags & MNT_NOEXEC) {
        retval = -EPERM;
        goto out;
    }
    // ...
}
```

### 10.2 SELinux 拦截

Android 用 SELinux 强制访问控制——exec 路径上有多次 MAC 检查：

```c
// security/samsung/sed/.../hooks.c（Android 14 中路径可能不同）
static int selinux_bprm_check_security(struct linux_binprm *bprm)
{
    // 1. 检查新进程的 SID（基于可执行文件的 context）
    new_sid = security_transition_sid(
        current_sid(), bprm->file->f_path.dentry, &bprm->cred->user,
        SECCLASS_PROCESS, &new_sid);

    // 2. 拒绝无权限的 transition
    if (avc_has_perm(current_sid(), new_sid, SECCLASS_PROCESS, ...) != 0)
        return -EACCES;

    // 3. 设置新进程的 SID
    bprm->cred->security = new_sid;
    return 0;
}
```

**关键**：
- SELinux 让"应用 exec 平台二进制"被限制——防止越权
- `zygote_exec` 这个 SELinux 策略是 Zygote 启动应用的关键——允许 zygote 域转换到应用域

### 10.3 at_secure：exec 后的安全标志

```c
// 安全相关：exec 触发的 at_secure 标志
if (bprm->secureexec) {
    // 设置 AT_SECURE auxv 项
    // libc 看到这个标志后会清空 LD_PRELOAD / LD_LIBRARY_PATH 等
}
```

`bprm->secureexec` 在以下情况被设置：
- 可执行文件设置了 setuid / setgid 位
- 文件系统有 nosuid 挂载——但内核还是允许执行（**注意**：现代 Linux 5.10 上 nosuid 不会自动 set secureexec，但会在 exec 失败时阻止 setuid）
- LSM 拒绝
- 文件在 noexec 文件系统

**AT_SECURE 在 auxv 中**：

```
用户态栈
  ↓
  AT_SECURE=1  ← 应用看到后清空环境变量
```

这让"setuid 程序不能被 LD_PRELOAD 劫持"——安全模型的关键一环。

### 10.4 setuid / setgid 的执行限制

```c
// fs/exec.c
// 如果 setuid 位被设置，exec 后 cred 改变
if (bprm->file->f_mode & FMODE_SETUID) {
    bprm->cred->euid = bprm->file->f_uid;
    bprm->cred->suid = bprm->file->f_uid;
}
if (bprm->file->f_mode & FMODE_SETGID) {
    bprm->cred->egid = bprm->file->f_gid;
    bprm->cred->sgid = bprm->file->f_gid;
}
```

**关键**：
- exec setuid 程序时 euid 改变
- 这就是为什么 `su` 命令 setuid root——exec 后 euid=0
- Android 14 用 SELinux 而不是传统 setuid 体系

### 10.5 个人化标志：personality

```c
// fs/exec.c
// exec 时清空/设置一些 personality 标志
// 例如：ADDR_NO_RANDOMIZE（关 ASLR）、FDPIC_FALLBACK 等
```

**关键**：
- `personality(2)` 系统调用可以改
- Android 14 上默认 `ADDR_NO_RANDOMIZE` = 0（开启 ASLR）
- 调试器 `gdb` 启动子进程时可能改 personality

---

## 十一、exec 与 02 篇 task_struct 的对应

02 篇把 task_struct 字段分组讲完了。exec 改变了哪些字段？本节做一个回扣：

| 02 篇字段 | exec 行为 | 04 篇哪里讲 |
|---|---|---|
| `mm` | 替换为新 mm | §7.3 |
| `active_mm` | 同上 | §7.3 |
| `files` | 复制 + 关闭 CLOEXEC | §7.3 |
| `cred` | 替换为 prepare_exec_creds | §10.4 |
| `signal` / `sighand` | 复制 | §7.3 |
| `comm` | 截取可执行文件名 | §7.4 |
| `flags & PF_FORKNOEXEC` | 清除 | §7.3 |
| `nsproxy` | 默认不变（除非 namespace flag） | 不展开 |
| `thread_info->cpu_context` | 指向 interpreter 入口 | §5.7 |

**关键**：
- 一次 exec 会改 10+ 字段
- 这些字段的修改集中在 `load_elf_binary` → `start_thread` 路径
- 任何一处失败都会回滚到 exec 之前的状态

---

## 十二、稳定性排查：exec 相关问题

### 12.1 应用启动慢（冷启动）

```bash
# 1. 抓 exec 耗时
adb shell "strace -ttt -T -e trace=execve /system/bin/ls" 2>&1

# 2. 抓 ART 启动耗时（am start -W）
adb shell "am start -W com.example.app/.MainActivity"
# WaitTime / ThisTime / TotalTime 三个值
```

**典型瓶颈**：
- exec 路径本身 < 5 ms（mmap 阶段）
- linker 加载共享库：~10-50 ms
- ART 启动（class linking + verification）：~50-200 ms
- Application.onCreate：~100-500 ms
- Activity.onCreate：~50-300 ms

**冷启动优化**：
- 减少 Application 初始化
- ART image（`boot.art`）让类预加载
- Cloud profiles 让 AOT 更准确

### 12.2 exec 失败导致 ANR

应用启动时如果 exec 失败，AMS 会等 5 秒（`ACTIVITY_START_TIMEOUT`）后判 ANR：

```bash
# 看 ANR logcat
adb logcat -b crash | grep -A 30 "ANR in com.example.app"
```

**关键**：
- ANR 不一定是 exec 失败——可能是 Application.onCreate 卡了
- exec 失败通常会立刻 crash，不至于 ANR
- 但"exec 成功但 ART 卡住"会导致 ANR

### 12.3 内存不足导致 exec 失败

```bash
# 看系统内存压力
adb shell "cat /proc/meminfo | head -10"
adb shell "dumpsys meminfo"  # 详细
```

**关键**：
- 内存不足时 `mmap` 失败 → exec 失败
- 触发 LMKD 杀进程——但被杀的不是你启动的应用
- 排查方向：dumpsys meminfo 看具体哪个进程占用大

### 12.4 fd 泄漏导致 exec 失败

`EMFILE` (Process fd limit) 或 `ENFILE` (System fd limit)：

```bash
# 看当前进程的 fd 数
adb shell "ls /proc/$(pidof system_server)/fd | wc -l"

# 看系统限制
adb shell "cat /proc/sys/fs/file-max"
```

**关键**：
- fd 泄漏会让新 exec 失败
- 排查：`lsof` / `procrank` 看泄漏源
- 修复：close 没用的 fd、用 O_CLOEXEC

---

## 十三、给 05 篇留的钩子

读完 04 篇，你应该能：

1. 跟踪 execve 在内核的完整路径：sys_execve → do_execveat_common → search_binary_handler → load_elf_binary → start_thread。
2. 理解 `linux_binprm` 这个"工作台"——它把用户态可执行文件变成内核结构。
3. 理解 ELF 文件怎么被解析——PT_LOAD / PT_INTERP / PT_DYNAMIC 段怎么被处理。
4. 理解 dynamic linker 怎么被加载——内核只做"借壳"，真正执行是用户态的事。
5. 理解 Zygote fork 后的两次 exec——为什么 Zygote 预加载的成果在 exec 后失效。
6. 知道 exec 失败的常见原因和排查命令。

05 篇《进程的退出：do_exit 与资源回收》会回答：

> 进程会死。Kernel 怎么"收尸"？
>
> - sys_exit() → do_exit() 关键路径
> - 释放 mm / files / fs / sighand / signal
> - 通知父进程（SIGCHLD）
> - 父进程 wait4() 收尸
> - release_task() 释放 task_struct
> - 僵尸进程的本质
> - Android 14 上的 Zygote 处理退出 / ANR 退出的特殊路径
> - exit_group 与 exit 的区别
> - atexit / on_exit 用户态 cleanup 链
> - coredump 在 exit 路径上的位置

读完 04 + 05 两篇，你应该能把"一个进程从诞生到死亡"的完整故事讲清楚——这是 Android 14 应用启动 + 退出优化的核心（Framework/Process 系列会回扣）。

---

## 小结

| 维度 | 一句话总结 |
|---|---|
| exec 本质 | 替换 task_struct 中的 mm / files / signal / cred 等，task_struct 本身不变 |
| linux_binprm | exec 路径的"工作台"——buf[128] 用于格式识别，interp 用于动态链接器 |
| search_binary_handler | 遍历 formats 链表尝试所有 binfmt——ELF / script / misc / android_app_image |
| load_elf_binary | 解析 ELF 头 + 映射 PT_LOAD + 加载 interpreter + 构造栈 + start_thread |
| dynamic linker | 内核只做"借壳"——真正执行是用户态的事；重定位 + 初始化 + 跳到主程序 |
| 进程地址空间成型 | exec 后 mm 是空的，VMA 重新被 elf_map 填满 |
| Android Zygote exec | 两次 exec：app_process64 + base.apk（zip 格式，由特殊 binfmt 处理） |
| exec 失败语义 | 失败时 task_struct 不变，原子性：要么全成功要么全失败 |
| 安全性 | noexec / SELinux / at_secure / setuid —— 多重防护 |

---

## 给下篇的桥

**本篇留下三个钩子**：

1. exec 后进程有"完整的地址空间"——05 篇讲进程死时这些资源怎么被释放
2. exec 失败的"原子性"是 do_exit 的反面——05 篇讲 do_exit 也是原子的
3. Zygote fork + exec 链——05 篇讲应用 crash 退出时 Zygote 怎么感知

如果读完本文仍有疑问：

- **"exec 后文件描述符表是全新的吗？"** → §7.3 讲了 `files_struct` 复制 + 关闭 CLOEXEC
- **"PIE 怎么加载到随机地址？"** → §7.2 ASLR 提到 `load_bias` 是随机偏移
- **"应用启动慢在哪里？"** → §12.1 给出完整耗时分解
- **"Android 14 的特殊 binfmt？"** → §8.3 `android_app_image` 处理 APK

---

## 引用

| 引用 | 路径 |
|---|---|
| 系统调用入口 | `kernel/exec.c:do_execveat_common / SYSCALL_DEFINE3(execve)` |
| linux_binprm | `include/linux/binfmts.h:struct linux_binprm` |
| prepare_binprm | `fs/exec.c:prepare_binprm` |
| search_binary_handler | `fs/exec.c:search_binary_handler_recursive` |
| ELF 格式处理 | `fs/binfmt_elf.c:load_elf_binary / elf_map` |
| 动态链接器 | `bionic/linker/linker_main.cpp:linker_main` |
| namespace | `bionic/linker/linker_namespaces.cpp` |
| 栈构造 | `fs/binfmt_elf.c:create_elf_tables` |
| start_thread | `arch/arm64/kernel/process.c:start_thread` |
| exec 失败 | `fs/exec.c:do_execveat_common` 错误处理 |
| SELinux 检查 | `security/selinux/hooks.c:selinux_bprm_check_security` |
| 内存账户 | `mm/memory.c:mmput` |
| Android 14 binfmt | `/proc/sys/fs/binfmt_misc/android_app_image` |




