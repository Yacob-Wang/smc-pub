# 05-.init_array 与构造函数链:静态初始化的执行顺序

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
>
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15` / `android15-6.1`(本篇涉及 `linker64::call_constructors` 倒序遍历 + `__attribute__((constructor))` 优先级)+ Bionic linker `bionic/linker/linker.cpp::call_constructors` + `crtbegin.o/crtend.o` 运行时文件
>
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
>
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) → [02-ELF](02-ELF文件格式深度解析-从可执行文件到内核视角.md) → [03-linker64](03-Bionic动态链接器-linker64的工作机制.md) → [04-重定位](04-符号解析与重定位-plt-got-relro全景.md)
>
> **下一篇**:[06-DEX / ODEX / VDEX 格式:为 mmap 而生的字节码](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 4 篇(Native 侧 · 初始化层,Native 4 篇收尾)
- **强依赖**:**[PLE-01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-02](02-ELF文件格式深度解析-从可执行文件到内核视角.md)** + **[PLE-03](03-Bionic动态链接器-linker64的工作机制.md)** + **[PLE-04](04-符号解析与重定位-plt-got-relro全景.md)**
- **承接自**:PLE-04 已讲重定位是 link_image 的最后一步;本篇是骨架上"初始化"动作的具体载体
- **衔接去**:下一篇 [PLE-06 DEX](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md) 从 Native 侧切到 Java 字节码侧(DEX)
- **不重复内容**:
  - **linker64 主流程** → 详见 [PLE-03](03-Bionic动态链接器-linker64的工作机制.md)
  - **ELF .init_array/.init 字段** → 详见 [PLE-02 §3](02-ELF文件格式深度解析-从可执行文件到内核视角.md)
  - **Java 侧 `<clinit>`** → 详见 [PLE-08 §4](08-类加载生命周期-Loading-Linking-Initializing.md)(Java 静态初始化,与 Native 的 `__attribute__((constructor))` 概念对仗)

## 0. 写在前面:为什么 .init_array 单独成篇

### 0.1 一个真实的崩溃现场

**场景**:某 App 在升级 NDK r25 后,启动后 ART 加载类时崩溃:

```
F libc : Fatal signal 6 (SIGABRT), code -1 (SI_TKILL)
F libc : pid: 12345, tid: 12346, name: main  >>> com.example.app <<<
I crash_dump: signal 6 (SIGABRT), code -1 (SI_TKILL)
I crash_dump: "Thread-1" tid=12347
E libc    : assertion "cameraserver not running" failed
```

**症状**:`cameraserver not running` 错误——一个 native 库在 `.init_array` 中访问了 cameraserver 服务,但它还没启动。

**根因**:`libcamera.so` 的 `.init_array` 里有一个 `__attribute__((constructor))` 函数,这个函数在加载时立即执行,试图通过 Binder 获取 cameraserver 的服务句柄。但 cameraserver 是异步启动的,启动顺序晚于 App 进程的加载。

**这个案例的修复需要 4 个知识**:
1. 知道 .init_array 是怎么执行的
2. 知道 linker 倒序执行的"假设"
3. 知道 `__attribute__((constructor))` 的优先级如何指定
4. 知道为什么 JNI_OnLoad 在这个时机会被调用

**这就是本篇要讲清楚的事**。

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Pixel 6(arm64-v8a)
> - Android 版本:`android-13.0.0_r41`(基线)→ 通过 OTA 升级到 `android-14.0.0_r1`
> - App:某相机 SDK 集成的拍照 App v2.0.0,使用 NDK r23b 编译
> - 编译选项:NDK r23b 默认,未特殊处理 `.init_array` 顺序

> **复现步骤**:
> 1. Android 13 设备安装 v2.0.0,正常打开相机,**概率性**闪退(20%)
> 2. 抓取闪退时的 crash dump,看 `signal 6 (SIGABRT)` + `cameraserver not running`
> 3. 不动 APK,OTA 升级到 Android 14
> 4. 升级后**必现**闪退,概率从 20% 升到 100%

> **logcat 关键片段**:
> ```
> F libc    : Fatal signal 6 (SIGABRT), code -1 (SI_TKILL)
> F libc    : pid: 12345, tid: 12346, name: main  >>> com.example.app <<<
> I crash_dump: signal 6 (SIGABRT), code -1 (SI_TKILL)
> I crash_dump: "Thread-1" tid=12347
> E libc    : assertion "cameraserver not running" failed
> W art     : JNI_OnLoad returned NULL from /data/app/~~xyz/lib/arm64/libcamera.so
> ```

> **根因诊断命令**:
> ```bash
> # 看 libcamera.so 的 .init_array 里有几个 constructor
> $ readelf -d libcamera.so | grep INIT_ARRAY
> 0x0000000000000019 (INIT_ARRAY)        0x12340
> $ objdump -s -j .init_array libcamera.so
> Contents of section .init_array:
>  12340 a8430000 00000000 b8430000 00000000  # ← 有 2 个 constructor 函数指针
> # 用 nm 找这两个函数
> $ nm libcamera.so | grep -E "123a8|123b8"
> 000123a8 T __init_camera_native  # 第一个 constructor
> 000123b8 T __init_jni_onload      # 第二个 constructor
> ```

> **修复 commit-style diff**:
> ```diff
> - // libcamera.cpp 旧:__init_camera_native 用 default 优先级
> - __attribute__((constructor)) void __init_camera_native() {
> -     // 直接尝试连接 cameraserver
> -     getCameraService();  // 同步等待
> - }
> + // 新:把重活挪到 JNI_OnLoad,或延后到首次调用
> + __attribute__((constructor(101))) void __init_camera_native() {
> +     // 优先级 101,保证在 ART/system_server 启动后才执行
> +     g_pending_camera_init.store(true);
> + }
> + // 或者:从 .init_array 移到 JNI_OnLoad
> + extern "C" JNIEXPORT jint JNI_OnLoad(JavaVM* vm, void* /*reserved*/) {
> +     // 此时 system_server 已起来,cameraserver 已注册
> +     registerNativeMethods(...);
> +     return JNI_VERSION_1_6;
> + }
> ```

> **架构师视角**:`.init_array` 是 **"启动期副作用源"** —— Android 14 加强了系统服务启动顺序检查,任何 `.init_array` 里同步访问系统服务的代码都可能踩雷。**架构师必须把"重活"从 `.init_array` 挪到 `JNI_OnLoad` 或首次业务调用**。

### 0.2 .init_array 在 PLE 8 阶段中的位置

```
阶段 0:execve 入口(内核)            ← PLE 02
    ↓
阶段 1:linker64 启动                  ← PLE 03
    ├─ _start / 自举
    ├─ 解析可执行文件
    └─ NEEDED 树遍历
        ↓
阶段 1.5:重定位                     ← PLE 04
    ├─ 处理 .rel.dyn / .rela.dyn
    ├─ 处理 .rel.plt / .rela.plt
    └─ 处理 RELRO
        ↓
阶段 1.6:执行 .init_array(本篇主体)  ← PLE 05
├─ 倒序遍历 Solist
├─ 对每个 .so 执行它的 .init_array
├─ JNI_OnLoad 触发
└─ libart.so 启动 ART 运行时
    ↓
阶段 2-4:ART 启动 + Zygote fork        ← PLE 06-12
```

**.init_array 是"启动期副作用集中地"**——它执行的代码,包括:
- libc 内部状态初始化(`__libc_init` 等)
- libdl.so 注册 dlopen / dlsym API
- libart.so 的 JNI_OnLoad 启动 ART
- 全局 C++ 对象的构造函数
- 应用代码里的 `__attribute__((constructor))` 函数

**架构师必记**:**任何在 .init_array 里跑的事,都是"启动期"**——早于 `main()`,早于任何 Java 代码,甚至早于 ART 运行时。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 解释 .init / .fini / .init_array / .fini_array / .preinit_array 的区别
2. 描述 linker 倒序执行 .init_array 的设计依据
3. 解释 `__attribute__((constructor))` 优先级和 libc 初始化的关系
4. 描述 JNI_OnLoad 触发的精确时机
5. 诊断"启动期崩溃但不在主线程"类问题的根因

---

## 1. 静态初始化的 5 个 section

### 1.1 ELF 里的 5 个初始化 section

**ELF 里有 5 个和初始化相关的 section**,每个有不同的角色和执行时机:

| Section | 类型 | 数量 | 执行时机 | 谁负责 |
|---|---|---|---|---|
| **.preinit_array** | PROGBITS | 0-几 | **ld.so 启动时**(linker 自己用) | 动态链接器 |
| **.init** | PROGBITS | 0-1 | **主程序 _start 之前** | crtbegin.o(_init) |
| **.init_array** | FINI_ARRAY 的反向 | 0-几十 | **.so 加载时** | 动态链接器 |
| **.fini** | PROGBITS | 0-1 | **主程序退出后** | crtend.o(_fini) |
| **.fini_array** | FINI_ARRAY | 0-几十 | **进程退出时** | 动态链接器(at_exit) |

**关键区别**:

| 维度 | .init / .fini | .init_array / .fini_array | .preinit_array |
|---|---|---|---|
| **数量** | 0 或 1(单函数) | 数组(可扩展) | 数组 |
| **目的** | crtbegin 提供默认 init | 用户/编译器添加的 init | 极早期 init |
| **典型使用** | 编译器插入 | C++ 全局构造 / `__attribute__((constructor))` | 罕见(ld.so 自身) |
| **执行者** | crtbegin.o + crtend.o | 动态链接器 | 动态链接器 |

### 1.2 .preinit_array:ld.so 启动的"第一行代码"

**`.preinit_array` 是 .so 加载前执行的代码数组**。只有动态链接器(ld.so / linker64)自己有 .preinit_array,普通 .so 不会有。

**linker64 的 .preinit_array**(典型):

```c
// 在 bionic/linker/ 编译时由链接器注入
extern "C" void _linker_preinit();

typedef void (*preinit_func_t)();
preinit_func_t __preinit_array_start[] = { _linker_preinit };
preinit_func_t __preinit_array_end[] = { _linker_preinit + 1 };
```

**`_linker_preinit` 干了什么**:

```c
void _linker_preinit() {
    // 1. 解析 ELF auxv,找到 PHDR / DYNAMIC 段
    // 2. 解析 linker64 自己的 .dynamic
    // 3. 找到 __init_array / __init_array_end 的范围
    //    (注意:这是 linker64 自己的 init_array,不是被加载的 .so 的)
}
```

**架构师视角**:**普通 .so 不会执行 .preinit_array**——只有 ld.so / linker64 自身。这个 section 在 Android 14 上几乎不可见(被合并到 .text)。

### 1.3 .init:编译器提供的"默认初始化"

**`.init` 是一个固定函数**,由 `crtbegin.o` 提供,所有 .so 都会包含它(如果用 clang/gcc 编译):

```c
// crtbegin.o
void _init() {
    // 编译器自动生成的代码
    // 调用 .init_array 中的所有函数
    for (init_func_t* f = __init_array_start; f < __init_array_end; f++) {
        (*f)();
    }
}
```

**注意**:**这个 `_init` 函数实际是在 .init section 里,但它的作用是"调用 .init_array"**。所以从执行顺序看,.init 和 .init_array 几乎是同时的(都在 _init 内被遍历调用)。

**架构师必记**:

- 真正"用户写的"初始化代码在 **.init_array** 里(由 C++ 全局对象、`__attribute__((constructor))`、链接器插入)
- .init 是"包装代码",用于调用 .init_array

### 1.4 .init_array:用户级初始化的"主战场"

**`.init_array` 是一个函数指针数组**,每个元素都是一个无参无返回值的函数。**这是启动期副作用的真正来源**。

**3 类填充 .init_array 的代码**:

| 来源 | 触发条件 | 优先级 |
|---|---|---|
| **C++ 全局对象构造** | 任何全局对象 | 编译期决定 |
| **`__attribute__((constructor))`** | 显式标记 | 0-100 (用户指定) |
| **编译器/链接器插入** | C++ ABI 需要的初始化 | 链接期决定 |

**真实代码**(.so 编译后):

```c
// __attribute__((constructor)) 的实现
void my_init() __attribute__((constructor(101)));

// 编译后,.init_array 里就有:
typedef void (*init_func_t)();
init_func_t __init_array_start[] = {
    /* 编译器插入的 C++ ABI init */,
    /* 用户 constructor 0-100 的所有函数(按优先级) */,
    /* 用户 constructor 101 之后的函数(按顺序) */
};
```

### 1.5 真实案例:用 readelf 看 .init_array

```bash
$ readelf -d libart.so | grep -E "INIT|FINI"
0x000000000000000c (INIT)               0x17ec28
0x0000000000000019 (INIT_ARRAY)         0x45d180 (14 entries)
0x000000000000001b (INIT_ARRAYSZ)       112 (bytes)
0x000000000000000d (FINI)               0x19d860
0x0000000000000019 (FINI_ARRAY)         0x45d1a0 (2 entries)
0x000000000000001b (FINI_ARRAYSZ)       16 (bytes)
```

**解读**(libart.so):
- `INIT` = 0x17ec28:DT_INIT 函数(传统 init)
- `INIT_ARRAY` = 0x45d180,14 entries × 8 字节 = 112 字节
- `FINI` = 0x19d860:DT_FINI 函数
- `FINI_ARRAY` = 0x45d1a0,2 entries × 8 字节 = 16 字节

**架构师必记**:**libart.so 有 14 个 init_array 函数**——每个都可能是 ART 启动期的关键步骤。任何一个崩溃,ART 启动就崩溃。

---

## 2. 倒序执行:linker 的设计哲学

### 2.1 为什么要倒序

**核心问题**:A.so 依赖 B.so,B.so 依赖 C.so。执行顺序应该是什么?

**直觉**:A 应该先 init,然后 B,然后 C。**(错!)**

**正确顺序**:**C 先 init,然后 B,然后 A**。

**为什么**:
- A 的 init 可能要调用 B 的函数(B 的全局状态必须先就绪)
- B 的 init 可能要调用 C 的函数
- 所以**底层先 init,高层后 init**

**倒序遍历 Solist 自然实现这个语义**:

```
Solist 顺序(由 NEEDED 树决定):
  [app_process, libfoo, libbar, libbaz, libart]
  ↑                                              ↑
  先加载                                       后加载
  (高层先出现)                              (底层后出现)

倒序遍历:
  libart → libbaz → libbar → libfoo → app_process
  (底层先 init)              (高层后 init)  ✅
```

### 2.2 真实代码:linker64 的 call_constructors

```c
// bionic/linker/linker.cpp
void call_constructors(Solist& solist) {
    // 1. 倒序遍历(底层先)
    for (auto&& si : solist.get_vector_backward()) {
        // 2. 对每个 .so,先调它的 DT_INIT(单函数)
        if (si->init_func) {
            trace("calling init func %p", si->init_func);
            si->init_func();
        }
        
        // 3. 遍历它的 .init_array(数组)
        for (ElfW(Addr) func : si->init_array_range()) {
            trace("calling init array func %p", func);
            ((void(*)())func)();
        }
    }
}
```

**关键事实**:

- **DT_INIT 在 .init_array 之前**——但 DT_INIT 通常是 .init(_init 函数),它的作用是调用 .init_array
- **.init_array 内部顺序 = 优先级降序**(`__attribute__((constructor(101)))` 在 `__attribute__((constructor(100)))` 之后)
- **倒序的 .so 顺序 = 底层先 init**

### 2.3 倒序的边界条件

**特殊场景 1:循环依赖**

```
A.so 依赖 B.so, B.so 依赖 A.so
```

**linker64 行为**:
- 加载 A(状态 = LOADING)
- 加载 B(因为 A 的 NEEDED)
- B 的 NEEDED 里有 A,A 已 LOADING,跳过
- B 加载完成
- A 继续加载完成
- **Solist 顺序 = [B, A]**
- **倒序 = A 先 init, B 后 init**

**问题**:如果 B 的 init 需要 A 先 init,但 A 反而先 init,可能 crash。

**真实案例**:A 和 B 互依赖,通常用一个标志位解决:"B.init 检查 A.is_loaded"。

**特殊场景 2:DT_NEEDED 顺序**

```
A.so 的 DT_NEEDED 顺序: [B.so, C.so]
A 的 init 依赖 B 的 init
```

**linker64 行为**:
- Solist 里 B 在 C 之前(A 先 NEEDED B)
- 倒序遍历时,C 先 init,然后 B init
- **C 先 init 可能不对!**

**修复**:在 .so 的 DT_NEEDED 顺序里,把先 init 的 .so 放前面:

```cmake
# CMakeLists.txt
target_link_libraries(foo PRIVATE baz bar)
# 这样 foo 的 NEEDED 顺序 = [libbaz.so, libbar.so]
# Solist 顺序 = [app_process, foo, bar, baz]
# 倒序 = baz 先 init,然后 bar,然后 foo ✅
```

**架构师必记**:**DT_NEEDED 顺序就是 init 顺序**(反过来)。**链接顺序决定 init 顺序**,写 CMakeLists 时就要考虑。

### 2.4 真实案例:倒序与正序的对比

**典型 libfoo.so + libbar.so + libart.so**:

```
app_process
  NEEDED: libart.so, libbar.so, libfoo.so

Solist 加载顺序(前向):
  [app_process, libart.so, libbar.so, libfoo.so]

init 执行顺序(后向):
  libfoo.so → libbar.so → libart.so → app_process
```

**含义**:
- libfoo.so 先 init(它最"叶子",没被其他依赖)
- libart.so 后 init(它有大量 .init_array,做 ART 启动)
- app_process 最后 init(它最"高层")

**架构师必记**:**app_process 的 .init_array 在所有依赖之后执行**——这是为什么 main() 之前 ART 已经启动。

---

## 3. `__attribute__((constructor))` 优先级

### 3.1 优先级如何指定

**`__attribute__((constructor(priority)))` 用一个整数指定优先级**:

| 优先级 | 含义 | 典型使用 |
|---|---|---|
| 0-100 | 较低优先级 | 应用代码的 init(在 libart 之后) |
| 101-1000 | 中等优先级 | 第三方库的 init |
| 1001-65535 | 较高优先级 | libc 内部 init, libdl init |
| 不指定 | 65535(最低) | 默认 |

**执行顺序**:
- **优先级数字小的先执行**(`constructor(0)` 比 `constructor(100)` 先)
- **同优先级的按链接顺序**(DT_NEEDED 顺序)
- **跨 .so 的优先比较**:先比优先级,再比 .so 顺序

**真实代码**:

```c
// libA.c
__attribute__((constructor(101))) void init_a() {
    LOG("init_a from libA");
}

// libB.c
__attribute__((constructor(200))) void init_b() {
    LOG("init_b from libB");
}

// libC.c
__attribute__((constructor(101))) void init_c() {
    LOG("init_c from libC");
}

// 链接:app → libA → libB → libC
// DT_NEEDED 顺序:[libA, libB, libC]

// 实际执行顺序:
// 1. init_a (libA, priority 101) - 先按 .so 顺序
// 2. init_c (libC, priority 101) - 同优先级,后加载
// 3. init_b (libB, priority 200) - 后执行
```

### 3.2 与 C++ 全局对象的关系

**C++ 全局对象构造等价于 `__attribute__((constructor(65535)))`**(最低优先级):

```cpp
class MyClass {
public:
    MyClass() {
        LOG("MyClass constructed");
    }
};

MyClass g_instance;  // 全局对象 → .init_array 中的一项
```

**编译后**:
- `g_instance` 的构造被插入到 .init_array,优先级 65535
- 同一优先级按 .o 链接顺序

**真实代码**(.so 编译后):

```c
// clang++ 生成的 __cxx_global_var_init
void __cxx_global_var_init() {
    MyClass::MyClass(&g_instance);  // 调用构造函数
}
```

**架构师必记**:**C++ 全局对象构造的优先级 = 65535(最低)**。如果你需要确保 init 在 libart 之后,把优先级设为 101-1000 之间。

### 3.3 libc 的初始化:priority = 100

**libc 内部的 init 优先级通常是 100**(很早):

```c
// bionic/libc/bionic/libc_init_common.cpp
__attribute__((constructor(100))) static void __libc_init_globals() {
    // 1. 初始化 libc 内部全局变量
    // 2. 设置 errno
    // 3. 初始化 locale
}
```

**为什么 priority = 100**:
- libc 是最底层,必须最早 init
- priority < 100 的 .init_array 函数会拿到"未初始化的 libc"(危险)
- priority = 100 是 bionic 的约定

**架构师必记**:**用户的 `__attribute__((constructor(50)))` 会在 libc 之前 init**——这很危险,因为 libc 还没就绪。**永远不要用 priority < 100**。

### 3.4 libdl 的初始化:priority = 1000

**libdl 的 init 优先级是 1000**(在 libc 之后,应用之前):

```c
// bionic/libdl/libdl.cpp
__attribute__((constructor(1000))) static void __libdl_init() {
    // 1. 注册 dlopen / dlsym / dlclose
    // 2. 初始化 linker 状态
}
```

**为什么 priority = 1000**:
- libdl 是 linker 暴露给用户的 API
- 必须在 libc 之后(用了 libc 的 syscall)
- 必须在应用之前(应用要用 dlopen)

### 3.5 libart 的初始化:priority = 65535(最低)

**libart 的 init 优先级是 65535**(最后 init):

```c
// art/runtime/runtime.cc
__attribute__((constructor))  // priority 默认 65535
static void __libart_init() {
    // 1. JNI_OnLoad
    // 2. ART 运行时启动
    // 3. GC 线程、Verifier、JIT profile
}
```

**为什么 priority = 65535**:
- libart 是最"高层"的 .so(其他 .so 都依赖它)
- 它必须最后 init
- 默认 65535(最低)正好符合需求

**架构师视角**:**链接器在编译时给 .init_array 排序,优先级低(数字小)的先执行**。这和直觉相反——**数字小 = 优先级高**。

---

## 4. JNI_OnLoad:启动期最关键的"钩子"

### 4.1 JNI_OnLoad 是什么

**JNI_OnLoad 是 libart.so 在 .init_array 末尾触发的一个函数**,它负责:

```c
// art/runtime/java_vm_ext.cc(简化)
extern "C" jint JNI_OnLoad(JavaVM* vm, void* reserved) {
    // 1. 获取 JNIEnv
    JNIEnv* env = nullptr;
    vm->GetEnv((void**)&env, JNI_VERSION_1_6);
    
    // 2. 注册 JNI 方法(可选,通常在 RegisterNatives 里)
    // 3. 初始化 ART 运行时
    Runtime::Create();  // 关键!
    
    // 4. 返回 JNI 版本
    return JNI_VERSION_1_6;
}
```

**关键事实**:

- **JNI_OnLoad 在 libart.so 的 .init_array 之后被调用**(因为它是 DT_INIT 的目标)
- **JNI_OnLoad 启动 ART 运行时**(Runtime::Create)
- **ART 启动是冷启动 100-300ms 的主要来源**

### 4.2 触发链

```
linker64::call_constructors()
    ↓
倒序遍历 Solist,最后是 libart.so
    ↓
执行 libart.so 的 .init_array(14 entries)
    ├─ 1-13: 各种 ART 内部 init
    └─ 14: 调 DT_INIT(如果存在)
        ↓
        DT_INIT = JNI_OnLoad 的 wrapper
            ↓
            JNI_OnLoad()
                ├─ 注册 JNI 方法
                ├─ Runtime::Create()  ← ART 启动
                └─ 返回 JNI_VERSION
```

**架构师视角**:**JNI_OnLoad 是"系统层的 main()"**——它在 app_process 的 main() 之前就跑完了。

### 4.3 JNI_OnLoad 的启动耗时

**典型中端机**:
- JNI_OnLoad 调用 Runtime::Create():**80-150ms**
- Runtime::Create() 内部:GC 线程、Verifier、JIT profile、信号处理……

**性能优化机会**:
- Runtime::Create() 内部的步骤可以分阶段
- 部分步骤可以延后到第一次需要时(惰性 init)
- ART 12+ 引入了"快速启动"模式

### 4.4 真实案例:JNI_OnLoad 失败

**场景**:某厂商定制 ART,启动时崩溃:

```
F libc : Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
W linker: "libart.so" calling DT_INIT 0x17ec28
I crash_dump: signal 11, fault addr 0x0
```

**症状**:`libart.so` 的 DT_INIT 函数崩溃。

**根因排查**:
1. **确认是不是 libart 本身 bug**——`adb shell setprop dalvik.vm.dex2oat-Xms 0` 跳过 AOT
2. **看 init_array 执行栈**——`adb shell setprop debug.ld.debug.reloc 1`
3. **看 ART 启动日志**——`adb logcat -d | grep -i "art\|runtime"`

**架构师视角**:**libart 的 .init_array 崩溃是"不可恢复"错误**——一旦 init 失败,整个进程死。**修复只能靠厂商发包**。

---

## 5. 构造链失败的连锁反应

### 5.1 5 类 .init_array 失败模式

| 失败类型 | 触发条件 | 后果 |
|---|---|---|
| **构造函数抛异常** | C++ 全局对象构造 throw | 进程崩溃(无法 catch) |
| **构造函数访问未初始化服务** | 调 Binder / Socket / File | 服务不可用时崩溃 |
| **构造函数死循环** | 全局对象相互依赖 | 启动卡死 |
| **构造函数内存越界** | 写越界全局变量 | SIGSEGV |
| **构造函数静态依赖错位** | 优先级不对 | 拿到未初始化的状态 |

### 5.2 真实案例:`cameraserver not running`(回到 §0.1)

**根因**:

```c
// libcamera.so 的构造函数
__attribute__((constructor(101))) void camera_init() {
    // 1. 获取 cameraserver 服务
    sp<IServiceManager> sm = defaultServiceManager();
    sp<ICameraService> cs = sm->getService(String16("media.camera"));
    
    // 2. 错误检查失败
    if (cs == nullptr) {
        LOG_FATAL("cameraserver not running");  // 崩溃!
    }
    
    // 3. 缓存 cs
    g_camera_service = cs.get();
}
```

**问题分析**:

| 时机 | 状态 |
|---|---|
| **app 启动** | cameraserver 可能还没启动 |
| **constructor 执行** | cameraserver "未运行" |
| **main() 执行** | 太晚了(已经 SIGABRT) |

**修复**:
- **方案 A**:改成 lazy init,第一次访问时再获取
- **方案 B**:构造函数里只"启动一个后台线程",不立即访问服务
- **方案 C**:使用 `ServiceManager::waitForService()`(阻塞等服务就绪)

**架构师视角**:**构造函数应该只做"无副作用"的初始化**。任何依赖外部服务的代码,都应该是 lazy init。

### 5.3 真实案例:循环依赖导致 init 失败

**场景**:A.so 和 B.so 互依赖,各自 constructor 用对方的全局状态。

```c
// A.so
extern int g_b_value;
__attribute__((constructor(101))) void a_init() {
    g_b_value = 42;  // 写 B 的全局
}

// B.so
extern int g_a_value;
__attribute__((constructor(101))) void b_init() {
    g_a_value = 24;  // 写 A 的全局
}
```

**执行顺序**:
- 倒序遍历 Solist = [B, A]
- B.init 先跑(priority 101) → 写 g_a_value
- A.init 后跑(priority 101) → 写 g_b_value

**没出事**——但如果 B.init 读 g_a_value 就会得到 0(A 还没 init)。

**真实场景**:A 和 B 互依赖,各自读对方的全局,初始值都是 0,出 bug。

**架构师必记**:**互依赖的 .so 的 .init_array 是"时序炸弹"**。**避免**互依赖,或者显式定义 init 顺序。

### 5.4 启动期崩溃的"5 秒定位法"

**当看到启动期崩溃(在 main 之前)**:

```
1. 看崩溃信号
   ├─ SIGABRT:assertion failed → 看 assertion 信息
   ├─ SIGSEGV:空指针 / 越界 → 看 fault addr
   └─ SIGBUS:未对齐访问 → 看具体指令

2. 看崩溃栈
   ├─ 如果栈里有 _dl_init:DT_INIT 触发
   ├─ 如果栈里有 __libc_init:libc init 失败
   ├─ 如果栈里有 __libart_init:libart 失败
   └─ 否则:看 linker logcat 找哪个 .so 加载

3. 看 linker logcat
   ├─ "calling DT_INIT 0xXXX" → 在执行某个 .init_array
   ├─ "library not found" → 依赖 .so 没找到
   └─ "cannot locate symbol" → 符号未解析

4. 看 maps 文件
   └─ 确认 .so 列表是否正确
```

**架构师必记**:**linker logcat 是诊断 .init_array 失败的"第一现场"**。

---

## 6. .init_array 的性能影响

### 6.1 启动期耗时占比

**冷启动 1.5s 中,.init_array 贡献多少**:

| 阶段 | 耗时 | 占比 |
|---|---|---|
| linker64 启动 | 50-150ms | 3-10% |
| 重定位 | 30-100ms | 2-7% |
| **.init_array 执行**(本篇) | **30-100ms** | **2-7%** |
| └─ JNI_OnLoad | 80-150ms | 5-10% |
| ART 启动 | 100-200ms | 7-13% |
| ClassLoader + Resources | 300-500ms | 20-33% |
| Application onCreate | 300-500ms | 20-33% |
| 第一帧渲染 | 200-400ms | 13-27% |

**.init_array 本身只占 2-7%**,但它**触发 JNI_OnLoad 启动 ART**,这是冷启动 5-10% 的来源。

### 6.2 4 个优化技巧

| 技巧 | 节省时间 | 难度 |
|---|---|---|
| **减少 .init_array 数量** | 5-15ms | 中(改代码) |
| **避免重操作在 constructor** | 10-30ms | 中(改代码) |
| **拆分 .init_array** | 5-10ms | 低(改链接选项) |
| **用 --gc-sections** | 5-10ms | 低(编译选项) |

### 6.3 真实案例:.init_array 优化

**优化前**:

```c
// libA.so
__attribute__((constructor(101))) void init_a() {
    // 1. 打开文件
    FILE* f = fopen("/data/local/tmp/cfg", "r");
    // 2. 读取配置
    // 3. 解析
    // 4. 应用配置
}
```

**优化后**:

```c
// libA.so
static Config* g_config = nullptr;

__attribute__((constructor(101))) void init_a() {
    // 1. 只做"惰性注册"
    g_config_init_func = []() { /* 原构造逻辑 */ };
}

Config* get_config() {
    if (g_config == nullptr) {
        g_config = g_config_init_func();
    }
    return g_config;
}
```

**节省**:`init_a()` 从 30ms 降到 1ms。首次 `get_config()` 调用 30ms,但此时应用已经在 onCreate,不影响冷启动。

**架构师视角**:**任何超过 5ms 的 constructor 都值得改成 lazy init**。

---

## 7. .fini 与进程退出

### 7.1 .fini_array 的作用

**.fini_array 是进程退出时执行的清理代码**。linker64 在 exit() 时遍历执行。

**典型 .fini_array 函数**:
- `__cxa_finalize` 析构 C++ 全局对象
- 关闭文件句柄
- 卸载 dlopen 的 .so

**正序遍历**(与 .init_array 相反):

```c
// linker.cpp::call_destructors
void call_destructors(Solist& solist) {
    for (auto&& si : solist.get_vector_forward()) {
        // 正序
        for (ElfW(Addr) func : si->fini_array_range()) {
            ((void(*)())func)();
        }
    }
}
```

**架构师必记**:**进程退出时 .fini 顺序 = .init 的逆序**(先 init 的后 fini)。这保证清理顺序符合 LIFO 语义。

### 7.2 at_exit 与 fini_array 的关系

**Android 上的退出清理链**:

```
进程退出
    ↓
1. exit() 调用 atexit() 注册的函数(后注册的先执行)
    ↓
2. .fini_array(正序)
    ↓
3. .fini(_fini 函数)
    ↓
4. _exit() 系统调用
```

**架构师必记**:**Android 不保证 .fini_array 完整执行**——内核可能直接 SIGKILL 进程。**关键资源用 onPause / onStop / 显式 close() 释放,不要依赖 .fini_array**。

---

## 8. 架构师视角:.init_array 的 5 个核心洞察

### 8.1 洞察 1:.init_array 是"启动期副作用源"

**任何在 .init_array 里跑的事都是"启动期"**——早于 main(),早于 Java 代码,甚至早于 ART 运行时。

**架构师必记**:
- 启动期 30-100ms 的隐藏成本
- 任何失败都是"不可恢复"——进程直接死
- 任何重操作都拉低冷启动

### 8.2 洞察 2:倒序 = 底层先 init

**linker64 倒序遍历 Solist,执行每个 .so 的 .init_array**。这保证:
- 底层 .so(被多个高层依赖)先 init
- 高层 .so(依赖底层)后 init
- 避免"高层 init 时底层未就绪"

**架构师必记**:**DT_NEEDED 顺序 = init 顺序(反过来)**。**写 CMakeLists 时就要考虑 init 顺序**。

### 8.3 洞察 3:优先级数字小 = 优先级高

**`__attribute__((constructor(0)))` 比 `__attribute__((constructor(100)))` 先执行**。

| 优先级 | 含义 | 典型使用 |
|---|---|---|
| 0-100 | **很早** | libc 内部 |
| 100-1000 | 早 | 第三方库 |
| 1000-65535 | 较晚 | libdl、libart、应用 |

**架构师必记**:**不要用 priority < 100**——会拿到未初始化的 libc。**C++ 全局对象 = priority 65535**(最低)。

### 8.4 洞察 4:JNI_OnLoad 是"系统层的 main()"

**JNI_OnLoad 启动 ART 运行时**,是冷启动 100-300ms 的主要来源。

**架构师必记**:
- JNI_OnLoad 在 .init_array 之后被调
- 它启动 Runtime::Create()(GC 线程、Verifier、JIT profile)
- 这部分耗时是"必要成本",不能省
- 优化空间在 Runtime::Create() 内部

### 8.5 洞察 5:从 .init_array 失败直接映射到故障现象

| 故障现象 | .init_array 根因 |
|---|---|
| 启动期 SIGABRT(在 main 之前) | 构造函数 assertion failed |
| 启动期 SIGSEGV | 构造函数访问空指针 |
| 启动期卡死 | 构造函数死循环 / 同步等待 |
| 启动期卡死 + 链路服务错误 | 构造函数访问未启动服务(§5.2 案例) |
| 启动慢 100ms+ | constructor 执行重操作 |

---

## 9. .init_array 工具链速查

### 9.1 必装工具

| 工具 | 用途 | 关键命令 |
|---|---|---|
| `readelf` | ELF 信息查看 | `readelf -d lib.so \| grep -E "INIT\|FINI"` |
| `objdump` | 反汇编 .init_array | `objdump -s -j .init_array lib.so` |
| `nm` | 看 init 函数符号 | `nm lib.so \| grep _GLOBAL__sub_I_` |
| `simpleperf` | 抓 .init_array 调用栈 | `simpleperf record -e cpu-cycles` |

### 9.2 3 个常用诊断组合

**组合 1:看 .init_array 大小**

```bash
$ readelf -d lib.so | grep -E "INIT_ARRAY|INIT_ARRAYSZ"
0x0000000000000019 (INIT_ARRAY)         0x45d180 (14 entries)
0x000000000000001b (INIT_ARRAYSZ)       112 (bytes)
```

**组合 2:看 init 函数**

```bash
$ readelf -s lib.so | grep -E "_GLOBAL__sub_I_|_init$"
# 列出所有 init 函数
```

**组合 3:看 init 顺序**

```bash
# 1. 看 .so 加载顺序
$ adb shell cat /proc/PID/maps | grep "\.so" | awk '{print $NF}' | sort -u

# 2. 倒序 = init 顺序
```

### 9.3 真实案例:诊断 constructor 性能

**步骤 1:确认 constructor 是冷启动瓶颈**

```bash
$ adb shell setprop debug.ld.debug.reloc 1
$ adb shell setprop debug.ld.debug.syms 1
$ adb logcat -c
$ adb shell am start -n com.example.app/.MainActivity
$ adb logcat -d | grep -E "init_array|DT_INIT" | head -30
```

**步骤 2:用 simpleperf 抓 init 栈**

```bash
$ adb shell simpleperf record -e cpu-cycles -p PID -o /data/local/tmp/perf.data
# 等几秒
$ adb shell simpleperf report -i /data/local/tmp/perf.data --show-callchain
```

**步骤 3:定位慢函数**

- 找 `call_constructors` 调用的栈
- 找耗时最长的 init 函数
- 决定是否改成 lazy init

---

## 10. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **.init_array 是启动期副作用源** | C++ 全局对象 + `__attribute__((constructor))` + libart 启动 + libc init |
| 2 | **倒序遍历 = 底层先 init** | linker64 倒序遍历 Solist,执行 .init_array |
| 3 | **优先级数字小 = 优先级高** | `constructor(0)` 在 `constructor(100)` 之前;不要用 < 100 |
| 4 | **JNI_OnLoad 是系统层的 main()** | 启动 ART 运行时,80-150ms 必要成本 |
| 5 | **init_array 失败 = 不可恢复** | 进程直接死;避免在 constructor 里访问外部服务 |

---

## 11. PLE 第二篇章(02-05)完结

**ELF 与动态链接 4 篇全部完成**:

| 篇号 | 标题 | 大小 |
|---|---|---|
| 02 | ELF 文件格式深度解析 | 61KB |
| 03 | Bionic 动态链接器 | 42KB |
| 04 | 符号解析与重定位 | 35KB |
| 05 | .init_array 与构造函数链 | 本篇 |

**累计批 1 产出:~150KB / ~2200 行**。

---

## 12. 下一篇预告

06 篇《DEX / ODEX / VDEX 格式:为 mmap 而生的字节码》是 PLE 第二篇章(DEX 与 ART 4 篇)的开篇,会沿着本系列第 01 篇的"为什么 Android 要造一个 DEX"埋下的线索,深入讲:

- DEX 头每个字段(string_ids、type_ids、proto_ids、field_ids、method_ids、class_defs)
- 整文件 mmap 与 linear alloc:DEX 的设计取舍
- ODEX 与 VDEX:AOT 编译产物的格式
- Compact DEX(CDEX):dex2oat 的压缩格式
- 真实案例:用 dexdump / baksmali 拆解
- 架构师视角:DEX 视角的加载性能与安全

**06 篇预计 2 周后产出**,届时一起发你看。

---

## 附录 A:5 个初始化 section 对比

| Section | 类型 | 数量 | 执行时机 | 典型使用 |
|---|---|---|---|---|
| .preinit_array | PROGBITS | 数组 | ld.so 启动时 | linker64 自身 |
| .init | PROGBITS | 0-1 | 主程序 _start 之前 | crtbegin 包装 |
| .init_array | FINI_ARRAY | 数组 | .so 加载时 | C++ 全局对象 / `__attribute__((constructor))` |
| .fini | PROGBITS | 0-1 | 主程序退出后 | crtend 包装 |
| .fini_array | FINI_ARRAY | 数组 | 进程退出时 | C++ 全局对象析构 |

## 附录 B:linker64 的 call_constructors 流程

```c
void call_constructors(Solist& solist) {
    // 倒序遍历(底层先)
    for (auto&& si : solist.get_vector_backward()) {
        // 1. 调 DT_INIT(单函数)
        if (si->init_func) {
            si->init_func();
        }
        // 2. 遍历 .init_array
        for (ElfW(Addr) func : si->init_array_range()) {
            ((void(*)())func)();
        }
    }
}
```

## 附录 C:典型优先级约定

| 优先级 | 使用者 | 备注 |
|---|---|---|
| 0-100 | libc 内部 | 危险区,可能拿到未初始化的 libc |
| 100-500 | 第三方库 | 常见 |
| 500-1000 | 较晚初始化 | libdl 等 |
| 1000-65535 | 较晚初始化 | libart 启动期 |
| 65535(默认) | C++ 全局对象 | 最晚执行 |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 06 DEX 格式 | DEX 头里的"构造链"概念与 ELF .init_array 类似 |
| 09 AOT/JIT | AOT 编译的 DEX2OAT 启动期在 .init_array 之外 |
| 12 进程启动 | Zygote fork 后,子进程的 libart JNI_OnLoad 走完才到 main |

---

> **本篇把 .init_array 拆解到"section 类型 + 倒序执行 + 优先级 + JNI_OnLoad + 失败模式"5 个维度。**
> **批 1 全部完成,接下来是批 2(DEX 与 ART 4 篇)。**
> **记住倒序、优先级、JNI_OnLoad、5 类失败,你的 .init_array 视角就立住了。**

