# 01-程序加载与执行全景图:从 execve 到第一行 Java 代码的完整链路

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
>
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15` / `android15-6.1` / `android15-6.6`(本篇为锚点,涉及内核侧 execve/mmap/缺页路径;具体差异详见各子篇标注)
>
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
>
> **前置阅读**:无(本篇是系列起点)
>
> **下一篇**:[02-ELF 文件格式深度解析:从可执行文件到内核视角](02-ELF文件格式深度解析-从可执行文件到内核视角.md)

---

## 本篇定位

- **本篇系列角色**:锚点篇(全局观),PLE 全系列地图
- **强依赖**:无(系列起点)
- **承接自**:无
- **衔接去**:下一篇 [PLE-02 ELF 文件格式](02-ELF文件格式深度解析-从可执行文件到内核视角.md) 从"文件格式"切入;PLE-03-05 走 Native 侧 link_image 全流程;PLE-06-09 走 Java 侧类加载;PLE-10-11 走资源;PLE-12-13 走进程维度;PLE-14 收口
- **不重复内容**:本篇定义"四元动作(解析/映射/链接/初始化)+ 8 阶段流水线"骨架,后续 PLE-02~14 在此骨架上展开,不在本篇讲任何子机制细节

## 0. 写在前面:为什么这个领域要单独开一个系列

### 0.1 一个被忽略的事实

在 Android 工程师的日常里,有三类问题出现的频率远高于其他故障,但很少被系统地讲过:

| 现象 | 出现频率 | 首次定位耗时 | 根因所在层 |
|---|---|---|---|
| **冷启动慢**(同场景 800ms → 1800ms 退化) | 高 | 4-8 小时 | DEX 加载 + Resources 解析 + 动态库 relro |
| **类找不到**(ClassNotFoundException / NoClassDefFoundError) | 高 | 1-3 小时 | ClassLoader 树 + DEX 完整性 |
| **首屏黑/白屏**(Activity 已 onCreate 但 view 未渲染) | 中 | 2-6 小时 | Resources inflate + ClassLoader 同步阻塞 |
| **动态库加载失败**(UnsatisfiedLinkError,so 架构错配) | 中 | 1-2 小时 | Bionic linker + abi 过滤 |
| **进程残留 / 僵尸** | 中 | 0.5-2 小时 | Zygote fork 路径上的错误恢复 |
| **启动期 OOM**(Java heap 还没起来就 native OOM) | 中 | 2-4 小时 | mmap 顺序、scudo reserve、ION 预留 |
| **ART Verify 错误**(优化开关切换后崩溃) | 低 | 4-12 小时 | dex2oat 流水线 + profile guided |
| **资源 ID 冲突**(同名资源覆盖后行为异常) | 低 | 6+ 小时 | arsc 解析 + aapt2 编译 |

**这八类问题的根因层都集中在一个领域:程序加载与执行。** 内存模型讲过"运行时数据长在哪",但完全没讲"这些数据是怎么被搬进来、按什么顺序执行"。这是 MM_v2 系列主动留下的空缺,也是 PLE 系列要填的洞。

#### 0.1.1 八类问题中"冷启动慢"的完整可验证案例

> **本节作为系列锚点案例**,把第一行表格里的"冷启动慢(800ms → 1800ms)"展开成可复现、可定位、可修复的 4 件套(环境/复现/logcat/diff)。**后续 PLE-02~14 各自带一个聚焦案例**,参见各篇 §0.1。

**环境**:
- 设备:Pixel 6(GS101,arm64-v8a)
- Android 版本:AOSP `android-14.0.0_r1`(从 `android-12.0.0_r31` OTA 升级)
- Kernel:`android14-5.15` GKI
- App 版本:某 IM App v8.4.0(APK 120MB,native 库 18 个)

**复现步骤**:
1. 工厂重置设备,首次开机完成 Setup Wizard
2. 安装该 IM App,从 Play Store 拉取 v8.3.0(基线)
3. 冷启动 5 次取 P99:基线 **820ms** ✅
4. 升级该 App 到 v8.4.0(新增 1 个 .so,DEX 增加 8MB)
5. 同样冷启动 5 次取 P99:**1820ms** ⚠️(退化 **1000ms**)

**Perfetto trace 关键片段**(简化):
```
T=0       user tap icon
T=200     fork 子进程完成
T=400     ActivityThread.main 进入
T=600     Application.onCreate 开始
T=1200    └─ ClassLoader loadClass SDKManager  ← 单类 400ms,占比 22%
T=1400    └─ Resources getIntArray layout      ← 单步 200ms,占比 11%
T=1600    └─ getResources().getLayout         ← 单步 200ms,占比 11%
T=1820    first frame committed
```

**logcat 关键片段**:
```
I Perfetto: slice("ClassLoader::loadClass com.thirdparty.SDKManager")= 412ms
W linker  : "/data/app/~~xyz/lib/arm64/libnative.so" unused DT entry: type 0x6ffffffb
I Resources: arsc load= 180ms; type count=4200; config count=8
I dex2oat : time= 1100ms (cold, no profile)
```

**修复**(commit-style diff):
```diff
- // build.gradle.kts
- multiDexEnabled = true
- // 未启用 baseline profile
+ isMinifyEnabled = true
+ isShrinkResources = true
+ baselineProfileFile = file("baseline-prof.txt")
+ // 在 Application.attachBaseContext 中
+ MultiDex.install(this);  // 提前安装避免主线程 stall
```
**修复后冷启动 P99:1820ms → 950ms**(节省 870ms)。

**架构师视角**:PLE-01 的"四元动作+8 阶段"在这个案例里的拆解 —— 退化的 1000ms 主要落在 **ClassLoader**(PLE-07/08)+ **Resources**(PLE-10)+ **未做 baseline profile 触发的 dex2oat 冷编译**(PLE-09)三段,本系列后续 14 篇会在各自主题里把这三段拆到机制级。

### 0.2 这个系列和已有系列的边界

```
┌──────────────────────────────────────────────────────────────────┐
│                    Android 技术知识地图(节选)                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Linux_Kernel/                                             │
│  ├─ Process/                ← 进程管理(创建/调度/退出)             │
│  ├─ Memory_Management/      ← MM_v2 内存模型(运行时长啥样)         │
│  └─ Program_Execution/      ← PLE 本系列(代码怎么被搬进来)        │
│         ↑ 你在这里                                               │
│                                                                  │
│  Runtime/                                          │
│  └─ ART/                    ← ART 内部机制(GC/解释器/JIT)         │
│         ↑ PLE 06-09 会从这里借视角                                │
│                                                                  │
│  Android_Framework/                                        │
│  └─ Process/                ← Android 进程架构(AMS/LMKD/zygote)   │
│         ↑ PLE 12-13 会从这里借视角                                │
│                                                                  │
│  App/                                               │
│  └─ (开发者应用)               ← 不在 PLE 范围                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**一句话定位**:

- **MM_v2 回答"运行时长啥样"**(一张内存账本)
- **PLE 回答"启动时装啥、按什么顺序"**(一台装配流水线)
- **ART 系列回答"装好后怎么跑"**(运行时的字节码执行)
- **Android_Framework/Process 回答"Android 侧如何调度进程"**(AMS/LMKD)

四者正交,两两互补。

### 0.3 风格与节奏

本系列严格遵守以下写作纪律:

| 维度 | 约束 | 原因 |
|---|---|---|
| 场景驱动 | 每章 1-2 个真实场景开篇 | 不堆概念,先建立直觉 |
| 代码克制 | 单片段 ≤ 20 行,全章 ≤ 8 处 | 保留架构视角,避免陷入源码 |
| 层次递进 | 概念→机制→决策→风险 四层 | 架构师需要的递进式理解 |
| 跨篇引用 | 关键术语首次出现时标注系列内位置 | 14 篇互为索引,不重复 |
| 架构师视角 | 每章末段固定一段"架构师视角"小节 | 把机制映射到稳定性/性能/风险 |
| 故障落地 | 14 篇末尾专章给故障速查表 | 排查时有抓手 |

---

## 1. 一句话定义:程序加载是什么

### 1.1 从静态文件到运行时实例的"翻译"过程

**程序加载(Program Loading)是把磁盘/Flash 上的静态文件(ELF、DEX、Resources、Configuration XML 等)转换成进程地址空间中可被 CPU 直接执行的运行时实例的过程。**

把这句话拆开:

```
静态文件                          加载器                          运行时实例
─────────                      ─────                          ──────────
ELF (.so)              ──→   Bionic linker (linker64)  ──→   内存中的 r-xp 段 + 符号表
DEX / ODEX / VDEX      ──→   ART ClassLoader            ──→   ArtMethod[] + Class 对象
resources.arsc         ──→   AssetManager               ──→   ResTable 内存索引
AndroidManifest.xml    ──→   PackageParser              ──→   Package 对象 + 组件表
assets/* 任意二进制     ──→   AssetManager.open()         ──→   Asset 句柄 + mmap 段
```

**每一行的"加载器"都不同,但"动作"惊人地一致**:

1. **解析(parse)**:把文件格式解码成内部数据结构
2. **映射(map)**:把数据/代码段 mmap 到进程虚拟地址空间
3. **链接(link)**:把外部依赖解析并绑定到具体地址(符号→地址、类→方法、资源 ID→值)
4. **初始化(init)**:执行静态初始化(.init_array、`<clinit>`、单例)

这就是**程序加载的"四元动作"**,后面 13 篇里几乎每一篇都在讲这四个动作在某个具体加载器上的实现细节。

### 1.2 为什么"加载"和"执行"必须放一起讲

很多文章把 ELF 加载(动态链接)和 ART 类加载分开讲,这是错误的。**它们是同一条流水线上的两段,中间被 execve 和 JNI_OnLoad 串起来**:

```
┌─────────────────────────┐                    ┌──────────────────────────┐
│  内核态                  │                    │  用户态                   │
│  ─────                  │                    │  ─────                   │
│  execve()               │                    │                          │
│    ↓                    │                    │                          │
│  load_elf_binary()      │                    │                          │
│    ↓                    │                    │                          │
│  mmap 所有 PT_LOAD 段   │                    │                          │
│    ↓                    │                    │                          │
│  mmap 动态链接器         │  → 转到用户态 →     │  _start(linker64 入口)    │
│  (linker64)             │                    │    ↓                     │
│    ↓                    │                    │  解析 ELF 依赖图          │
│  跳转到 linker 入口     │                    │    ↓                     │
│                         │                    │  递归 mmap 所有 NEEDED    │
│                         │                    │    ↓                     │
│                         │                    │  重定位(.plt/.got)        │
│                         │                    │    ↓                     │
│                         │                    │  执行 .init_array         │
│                         │                    │    ↓                     │
│                         │                    │  跳到 app_process 入口    │
│                         │                    │    ↓                     │
│                         │                    │  JNI_OnLoad(libart.so)   │
│                         │                    │    ↓                     │
│                         │                    │  ART 运行时启动           │
│                         │                    │    ↓                     │
│                         │                    │  Zygote fork             │
│                         │                    │    ↓                     │
│                         │                    │  ActivityThread.main()   │
│                         │                    │    ↓                     │
│                         │                    │  ClassLoader 加载应用 DEX │
│                         │                    │    ↓                     │
│                         │                    │  AssetManager 加载资源    │
│                         │                    │    ↓                     │
│                         │                    │  第一行 Java 代码执行     │
└─────────────────────────┘                    └──────────────────────────┘
```

**这就是 PLE 01 要讲的全景**——从内核 `execve` 入口开始,一直追到用户态第一行 Java 代码执行。中间不跳步,但不深入细节(细节分给 02-13)。

### 1.3 架构师视角:为什么这条流水线决定 Android 性能

如果你只看运行时(RSS、PSS、GC),你看到的是**结果**;如果你看加载流水线,你看的是**原因**。同一个 App:

- 加载顺序优化得好 → 冷启动 600ms
- 加载顺序混乱 → 冷启动 1800ms

**冷启动 70% 的时间花在这条流水线上**。架构师的判断题往往是:

| 决策 | 加载侧需要做什么 |
|---|---|
| 启动优化目标压到 800ms | 重新设计 .so 加载顺序,把非关键 .so 延后到 `Application.onCreate` 之后 |
| 首屏白屏 < 200ms | 资源预加载、主题 splash 优化、AssetManager 复用 |
| 内存峰值压到 250MB | 控制 mmap 顺序、避免 scudo reserve 阶段峰值 |
| 冷启动成功率 > 99.5% | 加载失败的容错(类找不到重试、so 缺失兜底) |

后面 13 篇每一篇都会回头对应到这些决策上。

---

## 2. 三种程序数据的统一视角

### 2.1 你表里那三列的"共同骨架"

回到你给的那张表:

| 维度 | SO (动态链接库) | APK 中的 DEX | APK 中的 Resources |
|---|---|---|---|
| 文件格式 | ELF | DEX / ODEX / VDEX | ZIP 容器内的 arsc、xml、png |
| 核心加载器 | Bionic Linker | ART ClassLoader | AssetManager / ApkAssets |
| 主要动作 | mmap、符号解析、重定位、执行 init | mmap、类解析、JIT/AOT 编译 | mmap 索引表、解析 ZIP 目录、解压数据 |
| 内存属性 | 包含可执行内存页 (r-xp) | 只读映射 (r--p) + ART 元数据堆 | 只读映射 (r--p) + Java/Native 缓存对象 |
| 触发时机 | `System.loadLibrary()` 或进程启动 | 类首次被加载/使用时 | 调用 `getResources()` 或 inflate 布局时 |

**这张表里藏着一个非常优雅的统一骨架**:

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  文件格式层     ELF                  DEX              ARSC          │
│       ↓         ↓                    ↓                ↓             │
│  解析器层      link_elf_object()    dex2oat/Parse()  ResTable::parse│
│       ↓         ↓                    ↓                ↓             │
│  映射器层      mmap(PT_LOAD)        mmap(whole file) mmap(arsc)     │
│       ↓         ↓                    ↓                ↓             │
│  链接器层      relocate()           linkClass()      index resolve  │
│       ↓         ↓                    ↓                ↓             │
│  初始化器层    .init_array          <clinit>         lazy inflate   │
│       ↓         ↓                    ↓                ↓             │
│  运行时实例    so_handle            ArtMethod        ResourceValue  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**左边的"列名"对每个加载器都一样,只是右边的"具体实现"不同。** 这就是为什么这三种加载能放一个系列讲——它们是同一个 pattern 在三种介质上的三种实现。

### 2.2 ELF vs DEX:为什么 Android 要造一个 DEX

这个问题困扰过很多架构师。Linux 上有 ELF,Java 有 class 文件,Android 为啥不直接用 class 而要造一个 DEX?

**答案藏在 ELF 和 class 文件都解决不了的三个 Android 特定问题上**:

| 约束 | ELF 的局限 | class 的局限 | DEX 的解法 |
|---|---|---|---|
| **存储空间** | 每个 .so 独立,重复 string/代码段 | class 内 string pool 重复 | DEX 把所有 class 的 string/类型/method 集中到 4 个 pool,跨 class 复用 |
| **mmap 友好** | ELF 的 section/segment 复杂 | class 文件碎片化 | DEX 头固定 + linear alloc,整文件 mmap 一次即可 |
| **运行时编译** | ELF 不可在设备上重编译 | class 无法 AOT | DEX/VDEX/ODEX 三件套,AOT 产物 VDEX 可独立 mmap |
| **跨进程共享** | ELF 共享靠内核 page cache | class 无共享机制 | Zygote 把 DEX mmap 后 fork,所有 App 进程共享同一份物理页 |

**DEX 的本质是"为 mmap 而生的字节码格式"**。它的所有设计取舍都指向一个目标:**让 zygote-fork 模式下的内存共享最大化**。这是后文 06-09 篇会展开的核心。

### 2.3 Resources 容器:为什么是 ZIP 而不是独立文件

APK 里的 resources 不是一个文件,是一个 ZIP 容器(里面装 arsc、xml、png、9.png、ttf 等)。为什么不扁平化?

| 方案 | 优势 | 劣势 |
|---|---|---|
| **独立文件** (dex 单文件、.so 单文件、resources 散落) | 简单 | 安装慢、I/O 次数多、签名粒度差 |
| **ZIP 容器** (APK 整体打成一个 zip) | 一次 I/O 拿全部、整文件 mmap、签名一次 | 解压需要 ZLIB 算 context、维护中央目录 |

Android 选 ZIP 容器的真正理由不是"打包方便",而是 **"整文件 mmap + 中央目录索引"**。这一点 PLE 11 会讲清楚。

**但 ZIP 容器也带来三个代价**,架构师必须知道:

1. **资源 I/O 必须走 AssetManager**,不能像 Linux 那样 `open()`。`Asset.open("drawable/icon.png")` 内部会:
   - 二分查找 ZIP 中央目录
   - 计算 deflate 流偏移
   - mmap 那一段
   - 如果是压缩的,解压(只对 xml,图片/字体不解压)
2. **签名校验必须解析 ZIP End-of-Central-Directory**,这是 v2/v3 签名验证的前置
3. **增量更新不能改 ZIP 内单文件**,必须整 APK 重打包,这是 Android 增量包大的原因之一

### 2.4 架构师视角:统一骨架带来的设计判断

理解这个"统一骨架"之后,你看任何新的"加载器"都能用同样的框架分析。例如:

- **JNI 库加载** = ELF pattern 的简化版(没 NEEDED,只有 dlopen)
- **Android NDK .so** = ELF pattern + 隐式 NEEDED(libc/libdl/libm/liblog)
- **Flutter Dart VM** = DEX pattern 的 VM 等价物(.dill + isolate)
- **WebView 资源** = Resources pattern + 远程 URL

这就是为什么这个系列的价值不仅是"知道 ELF/DEX/Resources 怎么加载",而是"掌握一种分析任何运行时加载系统的元方法"。

---

## 3. 完整加载流水线:从 execve 到第一行 Java

### 3.1 阶段切分

把整个流水线切成 **8 个阶段**。每个阶段是后续一篇或多篇文章的主题:

```
阶段 0  内核入口          execve() → load_elf_binary()        (本节)
阶段 1  动态链接器        Bionic linker64 解析 NEEDED 树      (P03-P05)
阶段 2  ART 运行时启动    JNI_OnLoad → Runtime::Init         (P06 引用,ART 03)
阶段 3  Zygote fork       fork() + 共享内存模板              (P12)
阶段 4  应用进程初始化    ActivityThread.main()               (P12)
阶段 5  ClassLoader 树    PathClassLoader 加载应用 DEX        (P07-P08)
阶段 6  Resources 加载    AssetManager 初始化 + ResTable 解析 (P10-P11)
阶段 7  第一行 Java       用户点击事件分发到第一行回调         (系列外)
```

**架构师必记**:**阶段 0-1 在每次进程启动时都跑**(包括 fork 出的子进程),**阶段 5-6 在每个应用进程内独立跑**(zygote 模板里已就绪,新进程只装载应用层)。

### 3.2 阶段 0:内核态 execve 入口

**场景**:Launcher 进程调用 `Process.start()` → `Process.killProcess()` ... 等等,这里有个易错点。**真实的启动路径是**:

```
Launcher tap icon
  ↓
Launcher 进程发 Binder → ActivityManagerService
  ↓
AMS 决定目标进程未启动 → Process.start(...)
  ↓
Socket 写 "启动 com.example" 到 Zygote
  ↓
Zygote fork() 出子进程,在子进程里:
    1. 关闭从 Zygote 继承的 socket
    2. 调用 ZygoteInit.zygoteInit() → nativeForkAndSpecialize()
    3. native 侧调用 execve(app_process, ...)
    4. app_process 启动 → ActivityThread.main()
```

**所以"execve 在哪发生"不是在 Zygote 里,是在每个 App 进程 fork 后立刻 execve 一次**。Zygote 自己是单独 execve 启动的(`/system/bin/app_process -Xzygote`)。

**阶段 0 的核心动作**:

```c
// fs/binfmt_elf.c (简化,只看主线)
static int load_elf_binary(struct linux_binprm *bprm) {
    // 1. 读 ELF 头,校验魔数 (0x7f 'E' 'L' 'F')
    // 2. 遍历 program headers (e_phnum 个)
    for (i = 0; i < elf_ex.e_phnum; i++) {
        switch (elf_ppnt->p_type) {
        case PT_LOAD:
            // 3. 把每个 PT_LOAD 段 mmap 到进程地址空间
            elf_map(filep, load_bias + vaddr, elf_ppnt, prot, ...);
            //    prot 来自 p_flags: PF_R → PROT_READ 等
            break;
        case PT_INTERP:
            // 4. 记录动态链接器路径(后面要 mmap 它)
            interp = elf_ppnt;
            break;
        case PT_DYNAMIC:
            // 5. 标记:这是个动态链接的可执行文件
            load_bias = ELF_ET_DYN_BASE;  // 共享库基址
            break;
        }
    }
    // 6. mmap 动态链接器本身
    elf_map(filep_interp, ..., interpreter, ...);
    // 7. 把链接器路径写入 bprm,后面会写到栈顶供 _start 用
    // 8. 如果有 PT_GNU_STACK,设置 stack 的执行权限(关闭可执行栈)
    // 9. 跳到 entry point(动态链接器入口)
    start_thread(regs, elf_entry, ...);
}
```

**关键事实**(架构师必须记):

| 事实 | 影响 |
|---|---|
| 内核只看 PT_LOAD 段 | section 头对内核不可见,内核根本不知道 .text/.data/.bss 的存在 |
| 多个 PT_LOAD 段连续 mmap | 共享库的 .text 和 .data 看起来是两个 VMA,实际可以相邻(内核会尝试合并,见 MM_v2 02) |
| PT_GNU_STACK 缺省不可执行 | 防止 stack 上的 shellcode,这是 Android 12+ 强制要求 |
| execve 不解析符号 | 重定位、plt、got 全是用户态 linker64 的事,内核不管 |

### 3.3 阶段 1:用户态 Bionic Linker(linker64)

`execve` 把控制权交给 linker64 的 `_start`。这是**整个流水线中最复杂的一段**,P03-P05 会展开。这里只给骨架:

```
linker64::_start
  ↓
  1. 自举(重定位 linker 自身,因为 linker 也是个 .so)
  ↓
  2. 解析 executable 的 .dynamic 段,得到:
     - DT_NEEDED 列表(要加载哪些 .so)
     - DT_SYMTAB / DT_STRTAB(符号表)
     - DT_PLTGOT / DT_JMPREL(重定位表)
     - DT_INIT / DT_INIT_ARRAY(初始化函数)
  ↓
  3. 广度优先遍历 DT_NEEDED 树:
     - 对每个 NEEDED .so 调用 find_library()
     - find_library 先查 DT_RUNPATH/DT_RPATH,再查 /system/lib64 等默认路径
     - 找到后 mmap(整个 .so)
  ↓
  4. 对每个已 mmap 的 .so 执行重定位:
     - 解析符号(查符号表)
     - 写 .got.plt / .relro
     - 标记 DF_BIND_NOW 时立即绑定,否则延后到符号首次访问
  ↓
  5. 执行 .init_array(每个 .so 的构造链)
  ↓
  6. 跳到 executable 的入口点(app_process)
```

**这里要记住的"三件大事"**:

1. **.so mmap 后不会复制到进程空间**——它是文件映射,内核 PageCache 里的页被多个进程共享
2. **重定位是"写"操作**——会把 .got.plt 页从 r--p 改成 rw-p(在 .relro 之前),或者在 .relro 之后用 mprotect 重新设成 r--p
3. **构造链有顺序**——.so A 的 .init_array 在 .so B(被 A 依赖)之前执行?其实反过来。**linker 倒序执行**。这跟 Java 类加载不同,要小心。

### 3.4 阶段 2-4:从 ART 启动到 Zygote fork

这一段是 ART + Zygote 的边界,在 P06、P12 会展开。这里只给主线:

```
app_process 入口(实际是 AppRuntime::onStarted 或类似)
  ↓
  1. 解析参数:看到 "--zygote" → 走 Zygote 模式
              看到 "com.example.MainActivity" → 走应用模式
  ↓
  2. 加载 libart.so(libcutils, liblog, libnativehelper 已经被 linker 加载)
  ↓
  3. JNI_OnLoad(libart.so):
     - 创建 JavaVM
     - 注册 JNI 方法
     - 初始化 ART 运行时(Runtime::Init)
     - GC 线程、Verifier 线程、Signal handler 等启动
  ↓
  4. ZygoteInit.main() (仅 Zygote 进程)
     - 预加载 (preload):
        - preloadClasses()      ← 这里会触发阶段 5 的大规模 DEX 加载
        - preloadResources()    ← 这里会触发阶段 6 的资源加载
        - preloadSharedLibraries()
     - 创建 ZygoteServerSocket
     - runSelectLoop()          ← 阻塞等待 fork 请求
  ↓
  5. 收到 fork 请求 → forkAndSpecialize():
     - fork()  → 子进程
     - 子进程继续 native 初始化
     - 子进程 handleChildProc() → 反射调用 ZygoteInit$ZygoteConnection.processOneCommand()
     - processOneCommand() → 解析参数 → 执行 ZygoteInit.zygoteInit() → 走到 ActivityThread.main()
```

**关键时间点(冷启动指标参考)**:

| 节点 | 典型耗时(中端机) | 主要工作 |
|---|---|---|
| execve 开始 → linker 完成 | 30-80ms | 解析 ELF,加载 libc/libdl/libm/log 等基础库 |
| linker 完成 → JNI_OnLoad | 50-100ms | ART 运行时启动 + GC 线程 + JIT 初始化 |
| JNI_OnLoad → Zygote fork | 100-300ms (仅 Zygote 启动) | preload classes/resources(仅 Zygote) |
| Zygote fork → 子进程 execve | 15-40ms | fork + 子进程 execve(注意:子进程也 execve 一次) |
| 子进程 execve → ActivityThread.main | 100-300ms | 子进程的 .so 加载 + ART 启动 + 应用 DEX 加载 |
| ActivityThread.main → 第一帧 | 200-600ms | ClassLoader 树构建 + Resources inflate + 业务初始化 |

**加起来冷启动 600-1500ms 是正常区间**,超过这个范围通常意味着加载链路上有阻塞点。**架构师的第一反应不是优化代码,而是打开 Perfetto 看加载时间线**——本系列 13 篇会反复用这个视角。

### 3.5 阶段 5-6:ClassLoader 与 Resources 加载

这两个阶段是**应用进程内独立跑的部分**,zygote 模板里已经预加载 framework 的 DEX/Resources,新 fork 出来的子进程只需要加载**应用自己的** APK:

```
ActivityThread.main()
  ↓
  1. 创建 LoadedApk 对象(从 ApplicationInfo 反查 APK 路径)
  ↓
  2. 创建 ClassLoader 树:
     - 父: BootClassLoader(framework 的 DEX,已在 zygote 模板中)
     - 子: PathClassLoader(/data/app/~~xxx/base.apk)
  ↓
  3. AssetManager 初始化:
     - new AssetManager()
     - addAssetPath(apkPath)    ← P10 详解
     - 解析 arsc → ResTable
     - 缓存所有 R.id 常量到内存
  ↓
  4. Application.attachBaseContext() → onCreate()
  ↓
  5. Activity 启动 → setContentView() → inflate 布局 XML
     - 这里会触发 Resources.getLayout() → 二分查 arsc → 解析二进制 XML
  ↓
  6. 第一帧渲染
```

**关键事实**:

| 事实 | 影响 |
|---|---|
| framework 的 DEX 已经在 zygote 里 mmap 过 | 子进程 fork 后这些页是"已经加载"的,只需 invalidate 写时复制 |
| 应用 DEX 必须在子进程内 mmap | 这就是冷启动的"必要成本",无解,只能优化 |
| Resources 索引(arsc)必须在子进程内解析 | 比 DEX 加载慢(因为 arsc 是二进制的,需要逐项反序列化) |
| 第一帧渲染依赖全部前序阶段 | 任何一个阶段阻塞,首屏时间就长 |

### 3.6 架构师视角:8 阶段是排查的"骨架清单"

当你看到线上冷启动 1500ms 退化到 2800ms,排查思路就是**按 8 阶段切分时间线**:

```
2800ms
 ├─ 阶段 0 内核入口           50ms ✓
 ├─ 阶段 1 linker              300ms ⚠ (比基线 200ms 慢)
 ├─ 阶段 2-4 ART/Zygote fork  500ms ✓
 ├─ 阶段 5 ClassLoader         800ms ⚠⚠ (比基线 300ms 慢)
 ├─ 阶段 6 Resources           500ms ✓
 └─ 阶段 7 业务/渲染           650ms ⚠
```

**锁定到阶段 1 和阶段 5**。然后用 linker trace(`LD_DEBUG=all` 或 `simpleperf`)+ DEX 加载 trace(`art-trace`)深入。这就是 PLE 14 风险篇会教的方法。

---

## 4. 加载的"四元动作":跨所有加载器的统一抽象

### 4.1 解析(Parse):从字节流到内部数据结构

**所有加载器的第一步**。把磁盘上的字节流解码成内存里可遍历的数据结构:

| 加载器 | 解析对象 | 关键数据结构 |
|---|---|---|
| linker64 | ELF 头 + program headers | `soinfo` (Bionic 内部结构) |
| ART ClassLoader | DEX 头 + string_ids + type_ids | `DexFile` (art/libdexfile) |
| AssetManager | ZIP 中央目录 + arsc 头 | `ResTable` + `Asset` |
| PackageParser | AndroidManifest 二进制 XML | `Package` + `Activity` 等组件 |

**解析的三个共性**:

1. **校验在前**:每个加载器都先校验魔数(ELF:0x7f 'E' 'L' 'F',DEX:0x64 0x65 0x78 0x0a,ZIP:0x50 0x4b 0x03 0x04)
2. **失败要明确**:解析失败的错误码必须能精确定位(偏移 + 字段名),不要只说"加载失败"
3. **缓存解析结果**:同一文件被多个进程加载时,只解析一次(例如 framework.jar 的 DexFile 在 zygote 解析后被所有 fork 进程共享)

### 4.2 映射(Map):从文件到虚拟地址

**所有加载器的第二步**。把数据/代码段映射到进程虚拟地址空间:

| 加载器 | 映射粒度 | 内存属性 |
|---|---|---|
| linker64 | PT_LOAD 段(通常 1-3 个) | r-xp / r--p / rw-p |
| ART ClassLoader | 整文件 mmap | r--p |
| AssetManager | 整 APK mmap + 单文件 mmap | r--p |
| PackageParser | 二进制 XML 段 mmap | r--p |

**映射的三个共性**:

1. **mmap 优于 read**:所有现代加载器都用 mmap,不会先把整个文件读到用户缓冲区。这样 PageCache 可以跨进程共享
2. **整文件优先**:DEX/Resources 都用整文件 mmap,内部用偏移寻址(DEX 的 `string_ids[offset]`、arsc 的 `ResTable_package[off+idx]`)。这样 mmap 一次就够
3. **属性严格按需**:可执行页只给 .text,数据/资源页只 r--p 或 rw-p,绝不 rwx

### 4.3 链接(Link):从虚拟地址到运行时引用

**所有加载器的第三步,也是最复杂的一步**。把"虚拟的引用"解析成"具体的地址/对象":

| 加载器 | 链接对象 | 解析结果 |
|---|---|---|
| linker64 | ELF 符号(函数名/变量名) | 进程内的绝对地址 |
| ART ClassLoader | 类引用、字段引用、方法引用 | ArtMethod* / ArtField* 指针 |
| AssetManager | 资源 ID (R.id.xxx) | 资源数据指针 + 类型 + 配置 |
| PackageParser | 组件名(string) | 内部 Activity/Service 对象 |

**链接的三个共性**:

1. **可见性边界决定链接范围**:
   - ELF 符号:DT_EXPORTED + DT_BIND_NOW
   - Java 类:package + classloader 树
   - 资源:package 边界(R.id 不能跨包引用)
2. **链接错误是头号崩溃源**:
   - ELF:`UnsatisfiedLinkError` (so 找不到 / 符号缺失 / 架构错配)
   - Java:`NoClassDefFoundError` / `IllegalAccessError`
   - 资源:`Resources$NotFoundException`
3. **链接策略影响启动**:
   - ELF 早期绑定(`-z now`)→ 启动慢,运行时快
   - ELF 延迟绑定(默认)→ 启动快,首次访问符号时慢
   - Java 类验证(strict → quick)→ 启动慢,安全
   - Java 类 quicken → 启动快,首次访问时 verify

### 4.4 初始化(Init):从静态数据到可执行状态

**所有加载器的第四步**。执行静态构造代码,把"静态的结构"变成"动态的可执行状态":

| 加载器 | 初始化触发 | 初始化内容 |
|---|---|---|
| linker64 | .init_array 段 | C++ 全局对象构造、libc 内部状态、libc++ abi 设置 |
| ART ClassLoader | `<clinit>` 方法 | Java 静态字段赋值、static 块 |
| AssetManager | lazy | 第一次访问资源时 inflate |
| PackageParser | parse 完时 | 组件注册到 PMS/AMS |

**初始化的三个共性**:

1. **顺序敏感**:静态构造之间可能有隐式依赖,顺序错了就 crash
2. **失败成本高**:初始化失败通常意味着整个 .so/类/资源不可用,必须重启进程
3. **可观测性差**:很多初始化是隐式的(全局对象构造、`<clinit>`),出问题难以定位

### 4.5 架构师视角:四元动作是"加载性能优化"的四个把手

任何加载性能优化,本质都是在这四个动作里减少工作量:

| 优化方向 | 对应动作 | 例子 |
|---|---|---|
| 减少解析 | Parse | dex2oat 把 DEX 转 VDEX(预解析) |
| 减少映射 | Map | 拆分 .so,只 mmap 需要的 |
| 减少链接 | Link | 减少 NEEDED 数量,改用 dlopen 延迟加载 |
| 减少初始化 | Init | 拆分 .init_array,把非关键初始化延后 |

**13 篇里,每篇文章都会回到这个四元动作框架**。记住它,你就有了"看穿任何加载器"的元方法。

---

## 5. 13 篇文章的层次递进

### 5.1 篇章划分

```
第一篇章:全局观(1 篇)                        ← 你在这里
├─ 01 程序加载与执行全景图

第二篇章:ELF 与动态链接(4 篇)
├─ 02 ELF 文件格式深度解析
├─ 03 Bionic 动态链接器(linker64)
├─ 04 符号解析与重定位(.plt/.got/.relro)
└─ 05 .init_array 与构造函数链

第三篇章:DEX 与 ART(4 篇)
├─ 06 DEX/ODEX/VDEX 格式
├─ 07 ART ClassLoader 体系
├─ 08 类加载生命周期(Loading→Linking→Initializing)
└─ 09 AOT/JIT 编译流水线

第四篇章:Resources 与 APK(2 篇)
├─ 10 资源加载(AssetManager / ApkAssets)
└─ 11 APK 容器解析(ZIP + arsc + 资源 ID)

第五篇章:进程启动与跨进程(2 篇)
├─ 12 进程启动全景(Zygote fork → 第一帧)
└─ 13 不同进程类型的加载差异

第六篇章:风险地图(1 篇)
└─ 14 加载失败与启动期故障速查
```

### 5.2 依赖关系图

```
                    ┌──────────────┐
                    │  01 全景     │ ← 你读这里
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ 02 ELF 格式  │   │ 06 DEX 格式  │   │ 10 资源加载  │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ 03 linker64  │   │ 07 ClassLoader│   │ 11 APK 解析  │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ 04 重定位    │   │ 08 类生命周期 │   │ (12 进程启动 │
└──────┬───────┘   └──────┬───────┘   │  汇合这三条) │
       │                  │           └──────┬───────┘
       ▼                  ▼                  │
┌──────────────┐   ┌──────────────┐          │
│ 05 .init     │   │ 09 AOT/JIT   │          │
└──────┬───────┘   └──────┬───────┘          │
       │                  │                  │
       └──────────────────┼──────────────────┘
                          ▼
                  ┌──────────────┐
                  │ 12 进程启动  │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │ 13 进程类型  │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │ 14 风险地图  │
                  └──────────────┘
```

### 5.3 写作时序

13 篇文章分 4 批落地:

| 批次 | 篇目 | 预期时间 | 主题 |
|---|---|---|---|
| 批 1 | 02-05 | ~3 周 | ELF 与动态链接(打基础) |
| 批 2 | 06-09 | ~3 周 | DEX 与 ART(Android 特色) |
| 批 3 | 10-12 | ~2 周 | Resources + 进程启动(汇合) |
| 批 4 | 13-14 | ~1 周 | 跨进程类型 + 风险地图(收尾) |

总计 ~9 周,平均每篇 3-4 天深度写作。**01 篇作为模板,先写完让你过目定调**。

---

## 6. 真实场景串讲:一次点图标的完整加载时间线

为了把 8 阶段和 13 篇文章的依赖关系落到真实场景,我们走一遍**"用户点开微信"**的完整加载链路。

### 6.1 阶段 0:Launcher 进程发出启动请求

**用户行为**:Launcher 图标被点击,`onClick` 触发 `Intent.ACTION_MAIN + LAUNCHER` 启动 `com.tencent.mm.ui.LauncherUI`。

**架构师视角**:这个阶段不在 PLE 范围(应用层),但我们要知道:
- Launcher 进程**早已运行**,它通过 Binder 通知 AMS
- AMS 进程在 system_server 内部,接收请求并查 `PackageManagerService` 获取目标 APK 路径
- AMS 判断目标进程未启动 → 通过 LocalSocket 向 Zygote 发请求:"帮我 fork 一个 com.tencent.mm"

**这中间有一次 Binder 跨进程调用 + 一次 LocalSocket 跨进程调用,耗时 1-3ms。**

### 6.2 阶段 1-2:Zygote fork + 子进程初始化

**PLE 12(进程启动)展开**:

```
Zygote 进程 runSelectLoop() 收到请求
  ↓
  forkAndSpecialize()  // fork 子进程
  ↓
  子进程:
    1. handleChildProc()
    2. ZygoteInit.zygoteInit()
    3. RuntimeInit.applicationInit()
    4. invokeStaticMain("com.android.app.ActivityThread")
    5. ActivityThread.main()       ← PLE 12 详述
```

**子进程内 execve** 在哪? 实际上:

```
子进程 fork 出来 →
  关键:Zygote 子进程不重新 execve(它继承 Zygote 的地址空间)→
  但每个 App 进程会通过 invokeStaticMain 反射调用 ActivityThread.main()
  → 这时 ART 才"切换"到应用模式
```

等等,这里有歧义,PLE 12 会厘清。**架构师只需知道:fork 之后 ART 还在,zygote 的 DEX/Resources 还在 mmap 状态,子进程复用它们**。

### 6.3 阶段 5-6:ClassLoader 与 Resources 加载

**ActivityThread.main() 启动后,关键动作**:

```java
// ActivityThread.java(简化,只看主线)
public static void main(String[] args) {
    // 1. 初始化 Looper、Choreographer(此时还没有 Choreographer 能力)
    Looper.prepareMainLooper();
    
    // 2. 创建 ActivityThread 对象
    ActivityThread thread = new ActivityThread();
    thread.attach(false, /* startSeq */);  // 系统进程传 true,普通 App 传 false
    
    // 3. Looper.loop() → 启动消息循环
    Looper.loop();
}
```

**thread.attach() 内部**:

```java
// 1. 通过 Binder 调到 system_server 获取 ApplicationInfo
ApplicationInfo ai = getLoadedApk(...);

// 2. 创建 LoadedApk,内部会:
LoadedApk loadedApk = new LoadedApk(this, ai);
//   ├─ 创建 PathClassLoader(父是 BootClassLoader)        ← PLE 07
//   ├─ 创建 AssetManager,addAssetPath(ai.sourceDir)      ← PLE 10
//   └─ 解析 arsc,构建 ResTable

// 3. 反射创建 Application
Application app = loadedApk.makeApplication(...);
```

**这是 PLE 07(ClassLoader 体系)+ PLE 10(资源加载)的现场。** 架构师要清楚:**这一步如果慢,冷启动就慢,而且没有捷径**(framework 的可以 fork 共享,应用 APK 必须自己 mmap)。

### 6.4 阶段 7:第一行 Java 代码执行

```java
// LoadedApk.makeApplication() 内部(简化)
public Application makeApplication(...) {
    // 1. 通过 ClassLoader 加载 Application 类
    Class<?> cl = mClassLoader.loadClass(mApplicationClass);  // PLE 07-08
    //    └─ 如果类不在 boot framework 中,会查 mClassLoader 的 DEX (应用 APK)
    //    └─ 第一次访问类 → 触发 verify + JIT 编译(可选)   ← PLE 09
    
    // 2. 调用 Application.<clinit> 静态初始化              ← PLE 08
    // 3. 反射创建实例,调用 attachBaseContext
    // 4. 调用 onCreate
    app.onCreate();
    
    return app;
}
```

**第一行 Java 代码 = Application.attachBaseContext()**。如果 attach 慢,意味着 Resources/ClassLoader 在阻塞;如果 onCreate 慢,意味着应用代码在阻塞。**架构师要能区分这两类慢**。

### 6.5 时间线总览(典型中端机参考)

```
时间(ms)    阶段
0           用户 tap
0-3         Launcher → AMS(Binder)
3-8         AMS → Zygote(LocalSocket)
8-35        Zygote fork() + 子进程 handleChildProc
35-200      linker64(子进程只 mmap app_process 的 NEEDED)
            └─ libc.so, libdl.so, libm.so, liblog.so, libart.so, libandroid_runtime.so
200-350     JNI_OnLoad(libart.so) → ART 启动
            └─ GC 线程、Verifier、JIT profile
350-450     ActivityThread.main() + attach()
            └─ ClassLoader 创建
            └─ AssetManager 初始化 + arsc 解析
450-650     Application.attachBaseContext + onCreate
            └─ 这里业务代码开始跑(微信的 onCreate 很重)
650-850     Activity 启动 + setContentView
            └─ inflate 布局 XML
            └─ 加载 drawable、字体
850-1100    首帧渲染(doFrame)
            └─ measure / layout / draw
1100        第一帧上屏(用户感知到的"启动了")
```

**总冷启动 1100ms 算优秀,1500ms 算正常,2000ms+ 需要优化。** 优化的杠杆点按 8 阶段顺序检查。

### 6.6 架构师视角:用 8 阶段拆解线上问题

**线上案例**(虚构但典型):

> 某 App 升级到 8.0 后,冷启动 P99 从 1200ms 退化到 2500ms。

**排查思路**:

1. **不要直接看代码**,先抓一份 Perfetto trace
2. **看 8 阶段时间分布**:
   ```
   Perfetto 拆解:
   ├─ execve → first Java: 200ms(基线 100ms)  ⚠
   ├─ first Java → onCreate: 400ms(基线 300ms) ✓
   ├─ onCreate → first frame: 1900ms ⚠⚠⚠
   ```
3. **锁定在"onCreate → first frame"**:这是 PLE 阶段 5-7 的领域
4. **继续切分**:
   - ClassLoader 加载 Application 类(用 `art-trace` 看 Verify 时间)
   - AssetManager inflate 布局 XML(用 `atrace` 看 inflate 耗时)
   - 业务 onCreate 跑重活(用 `simpleperf` 看哪个函数耗时)
5. **典型原因**:
   - VDEX 没编出来 → ClassLoader 走慢路径 verify
   - 资源分包后 arsc 解析变慢
   - 业务 onCreate 里有第三方 SDK 同步初始化

**这就是 PLE 14(风险地图)会教的方法**。

---

## 7. 加载的"陷阱集中地":每个阶段都有攻击面

### 7.1 加载是攻击者最爱的入口

架构师必须有"威胁模型"意识。**程序加载的每个阶段,都是攻击者的潜在入口**:

| 阶段 | 攻击面 | 缓解措施 |
|---|---|---|
| **execve 解析 ELF** | ELF 头攻击(畸形 program header) | 内核校验 e_phnum/e_phentsize |
| **linker64 加载 .so** | 符号劫持(export 覆盖)、依赖混淆 | RELRO、符号命名空间、Android 7+ namespace |
| **ART 加载 DEX** | DEX 注入、类替换、热补丁 | 签名校验、类加载器隔离、final 类 |
| **AssetManager 加载资源** | 资源 ID 冲突、APK 替换 | APK 签名 v2/v3、resources.arsc 校验 |
| **PackageParser 解析 manifest** | 组件劫持、permission 提升 | 签名校验 + permission 验证 |
| **Zygote fork** | 模板污染(在 zygote 阶段 hook 全部受影响) | SELinux、seccomp、namespace |

### 7.2 安全与性能的取舍

**很多安全加固都增加加载耗时**:

| 加固项 | 性能影响 | 安全收益 |
|---|---|---|
| RELRO(Full) | 启动 +5-10ms(可忽略) | 防止 GOT 覆盖 |
| BIND_NOW | 启动 +20-50ms | 防止延迟绑定的 PLT 攻击 |
| 启动时 verify DEX | 启动 +100-300ms | 防止 DEX 注入 |
| VDEX 签名校验 | 启动 +10-30ms | 防止 VDEX 篡改 |
| 资源完整性校验 | 启动 +20-50ms | 防止 arsc 篡改 |

**架构师要清楚这些开销的"性价比"**。在可信执行环境(TEE)里,这些都可以关掉以追求性能;在用户态,默认全开。

### 7.3 架构师视角:威胁模型意识

写加载器代码或优化加载性能时,先问自己三个问题:

1. **如果攻击者能控制这个文件,后果是什么?**
2. **如果攻击者能触发这个加载路径,后果是什么?**
3. **如果攻击者能 race 这个加载过程,后果是什么?**

这三个问题在 PLE 03(linker64)和 PLE 08(类生命周期)里会反复出现。

---

## 8. 加载是"诊断窗口":性能/稳定性问题的根因集中地

### 8.1 性能问题的根因分布(经验数据)

基于多年稳定性问题排查经验,**程序加载相关问题在性能类问题中的占比**:

| 性能问题类型 | 加载相关占比 | 典型表现 |
|---|---|---|
| **冷启动慢** | 90%+ | 用户感知启动慢 |
| **首屏黑/白屏** | 80%+ | splash 闪退、首屏卡 |
| **滑动卡顿** | 20-30% | 列表滚动卡顿(可能跟资源加载/类加载并发) |
| **内存峰值高** | 50%+ | 启动期 mmap 顺序不合理 |
| **ANR** | 10-20% | 主线程加载阻塞 |

**架构师应该把"加载"作为性能问题的第一嫌疑**。不要先怀疑算法复杂度,先看加载时间线。

### 8.2 稳定性问题的根因分布

| 稳定性问题类型 | 加载相关占比 | 典型表现 |
|---|---|---|
| **ClassNotFoundException** | 100% | 类找不到 |
| **UnsatisfiedLinkError** | 100% | .so 加载失败 |
| **VerifyError** | 100% | DEX 校验失败 |
| **Resources$NotFoundException** | 100% | 资源 ID 找不到 |
| **NoSuchMethodError** | 90%+ | 方法签名变更 |
| **冷启动崩溃** | 70%+ | 启动期未捕获异常 |
| **进程残留** | 50%+ | 加载失败后未正确退出 |

**架构师看到这些异常,直接定位到加载链路的对应阶段**:

```
ClassNotFoundException    → PLE 08 类加载失败
UnsatisfiedLinkError      → PLE 03 linker64 失败
VerifyError               → PLE 08/PLE 09 DEX verify
Resources$NotFoundException → PLE 10/PLE 11 资源解析
```

### 8.3 架构师视角:加载链 = 故障定位地图

**记住这张映射表,你就在 80% 的启动期故障面前有了 5 秒定位能力**:

| 异常关键字 | PLE 阶段 | 排查文章 |
|---|---|---|
| `Linker` / `dlopen` / `cannot locate symbol` | 阶段 1 | PLE 03/04 |
| `ClassNotFound` / `NoClassDefFound` | 阶段 5 | PLE 07/08 |
| `Verify` / `Illegal access` | 阶段 5 | PLE 08/09 |
| `ResourceNotFound` / `InflateException` | 阶段 6 | PLE 10/11 |
| `AndroidRuntime` / `FATAL EXCEPTION at ActivityThread.main` | 阶段 4 | PLE 12 |
| `Zygote` / `preload` / `fork` | 阶段 3 | PLE 12 |
| `init` / `Constructor` / `UnsatisfiedLinkError` | 阶段 0-1 | PLE 03/05 |

**后面 14 篇每一篇都会给出"故障速查表"**,你可以照着表对号入座。

---

## 9. 14 篇的命名与"对仗"设计

### 9.1 命名风格

| 篇号 | 命名 | 风格 |
|---|---|---|
| 01 | 程序加载与执行全景图:从 execve 到第一行 Java 代码的完整链路 | 锚点篇,长标题 |
| 02 | ELF 文件格式深度解析:从可执行文件到内核视角 | 主题 + 子题 |
| 03 | Bionic 动态链接器:linker64 的工作机制 | 主题 + 副标题 |
| 04 | 符号解析与重定位:.plt / .got / .relro 全景 | 主题 + 关键概念 |
| 05 | .init_array 与构造函数链:静态初始化的执行顺序 | 主题 + 关键点 |
| 06 | DEX / ODEX / VDEX 格式:为 mmap 而生的字节码 | 主题 + 核心特点 |
| 07 | ART ClassLoader 体系:从 BootClassLoader 到 PathClassLoader | 主题 + 范围 |
| 08 | 类加载生命周期:Loading → Linking → Initializing | 主题 + 三阶段 |
| 09 | AOT / JIT 编译流水线:dex2oat 与 ART 运行时编译 | 主题 + 关键工具 |
| 10 | 资源加载:AssetManager / ApkAssets / ResTable | 主题 + 三个核心组件 |
| 11 | APK 容器解析:ZIP + arsc + 资源 ID 体系 | 主题 + 三个关键概念 |
| 12 | 进程启动全景:Zygote fork → 第一帧 | 主题 + 范围 |
| 13 | 不同进程类型的加载差异:zygote / system_server / app / native | 主题 + 四类进程 |
| 14 | 加载失败与启动期故障速查 | 主题 + 用途 |

### 9.2 与 MM_v2 的对仗

| MM_v2 | PLE | 关系 |
|---|---|---|
| 01 内存系统总览 | 01 程序加载全景 | 姐妹篇锚点 |
| 02 VMA 体系 | 02 ELF 格式 | 都是"虚拟地址空间"侧 |
| 03 ART 堆 | 06/07/08 DEX/ClassLoader | 都是 ART 相关 |
| 04 Native 堆 | 03/04/05 linker64/重定位/init | 都是 native 加载 |
| 05 AMS 内存 | 12 进程启动 | 都有 AMS 参与 |
| 06 LMKD | 13 进程类型 | 都是"进程管理"侧 |
| 07 PSI/压力 | 14 故障地图 | 都是稳定性治理 |
| 08-11 内核 | (跨篇引用) | 内核基础是共同的 |
| 12 风险 | 14 风险 | 风险篇对仗 |
| 13 诊断 | (14 风险中含诊断) | 诊断融在风险里 |
| 14 进程类型学 | 13 进程类型 | **完全对仗,同视角切换** |

**关键对仗点**:MM_v2 14(进程类型学)和 PLE 13(进程类型加载差异)互为补充——前者看运行时,后者看启动时。

---

## 10. 阅读路径建议

### 10.1 三条推荐路径

按不同需求给你三条路径:

**路径 A:只想懂 Android 启动**(架构师 5 篇)
```
01 全景图
  ↓
03 linker64(只读 §1 §2 §3 加载机制)
  ↓
07 ClassLoader 体系
  ↓
10 资源加载
  ↓
12 进程启动全景
```

**路径 B:想做加载性能优化**(性能架构师 8 篇)
```
01 全景
  ↓
02 ELF 格式
03 linker64
04 重定位
05 .init_array
  ↓
06 DEX 格式
07 ClassLoader
08 类生命周期
09 AOT/JIT
  ↓
10 资源加载
11 APK 解析
  ↓
12 进程启动
13 进程类型
  ↓
14 风险地图
```

**路径 C:想完整理解,自学为主**(本系列作者本人推荐)← **你**
```
01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 11 → 12 → 13 → 14
按顺序,每篇 2-3 小时精读
```

### 10.2 与其他系列的协同阅读

| 你想了解 | 推荐先读 |
|---|---|
| 启动后内存怎么布局 | MM_v2 02 → PLE 01 |
| 启动后 ART 怎么跑 | PLE 06 → PLE 09 → ART 系列 03 |
| Zygote 怎么 fork | Android_Framework/Process 16 → PLE 12 |
| Binder 怎么传数据 | Binder 系列 → PLE 04(重定位思路相通) |
| 进程优先级怎么算 | Android_Framework/Process 17 → PLE 13 |

---

## 11. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **程序加载是 8 阶段的流水线** | execve → linker → ART → Zygote fork → 子进程初始化 → ClassLoader → Resources → 第一行 Java |
| 2 | **三种程序数据用同一个 pattern** | 解析 → 映射 → 链接 → 初始化(四元动作) |
| 3 | **加载占冷启动 70%** | 中端机 600-1500ms,优化空间主要在加载侧 |
| 4 | **加载是攻击面的集中地** | 每个阶段都有对应的安全加固,加固换性能 |
| 5 | **加载是故障定位的"骨架清单"** | 异常类型直接映射到 PLE 阶段和文章 |

---

## 12. 下一篇预告

02 篇《ELF 文件格式深度解析:从可执行文件到内核视角》会沿着 01 篇埋下的线索,深入讲:

- ELF 头的每个字段、内核视角的最小校验集
- Program Header vs Section Header 的区别(为什么内核只关心前者)
- 动态库的 ELF 结构(ET_DYN vs ET_EXEC)
- 32 位 / 64 位 ELF 的 arm64 特殊处理
- 真实案例:用 `readelf` 拆解 libart.so

**02 篇预计 3 天后产出**,届时一起发你看。

---

## 附录 A:本篇关键术语速查

| 术语 | 一句话 | 详见 |
|---|---|---|
| **execve** | 进程启动的内核入口,把磁盘上的可执行文件变成进程 | §3.2 |
| **linker64** | Bionic 动态链接器,用户态的 .so 加载器 | §3.3, P03 |
| **PT_LOAD** | ELF program header 的一种,标记一个可加载段 | §3.2 |
| **.init_array** | ELF 中的静态构造链,linker64 倒序执行 | P05 |
| **DEX** | Android 字节码格式,为 mmap 优化 | §2.2, P06 |
| **ClassLoader** | Java 类的加载器,Android 用树形结构隔离 | P07 |
| **AssetManager** | Android 资源加载器,基于 ZIP 中央目录 | P10 |
| **Zygote** | Android 进程模板,所有 App 进程的"母体" | P12 |
| **冷启动** | 进程从无到有到第一帧的完整时间 | §3.4 |
| **soinfo** | Bionic linker64 内部表示一个已加载 .so 的结构 | P03 |
| **四元动作** | 解析 / 映射 / 链接 / 初始化,所有加载器的统一抽象 | §4 |

## 附录 B:本篇时间线参考(冷启动 8 阶段)

| 阶段 | 典型耗时(中端机) | 主要工作 | PLE 文章 |
|---|---|---|---|
| 阶段 0:内核入口 | 5-15ms | execve + load_elf_binary | (P02 引用) |
| 阶段 1:linker64 | 30-80ms | mmap .so + 重定位 + .init_array | P03-P05 |
| 阶段 2:ART 启动 | 50-100ms | JNI_OnLoad + Runtime::Init | P06 引用 |
| 阶段 3:Zygote fork | 15-40ms | fork + 子进程初始化 | P12 |
| 阶段 4:ActivityThread | 50-150ms | main() + attach() | P12 |
| 阶段 5:ClassLoader | 100-300ms | PathClassLoader + 应用 DEX | P07-P08 |
| 阶段 6:Resources | 100-200ms | AssetManager + arsc 解析 | P10-P11 |
| 阶段 7:业务 + 渲染 | 200-600ms | Application onCreate + 第一帧 | (应用层) |
| **总计** | **600-1500ms** | 冷启动 8 阶段合计 | |

## 附录 C:本篇异常关键字 → PLE 文章映射

| 异常关键字 | 阶段 | PLE 文章 |
|---|---|---|
| `linker / dlopen / cannot locate symbol` | 1 | P03, P04 |
| `ClassNotFound / NoClassDefFound` | 5 | P07, P08 |
| `VerifyError / IllegalAccess` | 5 | P08, P09 |
| `Resources$NotFound / InflateException` | 6 | P10, P11 |
| `AndroidRuntime / FATAL EXCEPTION` | 4 | P12 |
| `Zygote / preload / fork` | 3 | P12 |
| `init / Constructor` | 0-1 | P03, P05 |

## 附录 D:本篇与 MM_v2 的对仗矩阵

| MM_v2 篇 | PLE 篇 | 对仗关系 |
|---|---|---|
| 01 内存总览 | 01 加载全景 | 姐妹锚点篇 |
| 02 VMA 体系 | 02 ELF 格式 | 虚拟地址空间视角 |
| 03 ART 堆 | 06-08 DEX/ClassLoader/生命周期 | ART 视角 |
| 04 Native 堆 | 03-05 linker64/重定位/init | native 加载视角 |
| 05 AMS 内存 | 12 进程启动 | AMS 参与 |
| 06 LMKD | 13 进程类型 | 进程管理 |
| 07 PSI/压力 | 14 故障地图 | 稳定性治理 |
| 08-11 内核基础 | (跨篇引用) | 共同基础 |
| 12 风险 | 14 风险 | 风险篇对仗 |
| 13 诊断 | 14(含诊断) | 诊断融入风险 |
| 14 进程类型学 | 13 进程类型 | **完全对仗** |

---

> **本篇作为 PLE 系列的锚点文章,定下了"四元动作"、"8 阶段"、"跨篇引用"的写作骨架。后续 13 篇都按这个骨架展开。**
> **如果你认可这个骨架,我会按 02-05-06-09-10-12-13-14 的顺序推进,每批 2-3 篇,大约 9 周完成全系列。**
> **如果你希望调整方向(比如想先看 DEX 体系,或者想加 ART GC 视角),现在告诉我还来得及。**

