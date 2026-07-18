# 09-AOT / JIT 编译流水线:dex2oat 与 ART 运行时编译

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15`(dex2oat 是 CPU/IO 双密集任务,内核版本影响 `madvise(MADV_HUGEPAGE)` / `ion` 分配;Android 14 强化使用 `madvise(MADV_POPULATE_WRITE)`)+ `art/dex2oat/dex2oat.cc` + `art/compiler/` + `art/runtime/jit/` + `art/runtime/oat_file_manager.cc` + 工具 `oatdump`
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) → [06-DEX](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md) → [08-类加载生命周期](08-类加载生命周期-Loading-Linking-Initializing.md)
> **下一篇**:[10-资源加载:AssetManager / ApkAssets / ResTable](10-资源加载-AssetManager-ApkAssets-ResTable.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 8 篇(Java 侧 · 编译层,Java 3 篇收尾)
- **强依赖**:**[PLE-01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-06](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md)** + **[PLE-08](08-类加载生命周期-Loading-Linking-Initializing.md)**
- **承接自**:PLE-08 已讲类加载 7 阶段;本篇讲"类加载完成后,字节码怎么变成机器码"(AOT/JIT)
- **衔接去**:下一篇 [PLE-10 资源加载](10-资源加载-AssetManager-ApkAssets-ResTable.md) 从"代码+数据"切到"纯资源"维度
- **不重复内容**:
  - **类加载 7 阶段 / Verify / `<clinit>`** → 详见 [PLE-08](08-类加载生命周期-Loading-Linking-Initializing.md)
  - **DEX 文件格式** → 详见 [PLE-06](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md)
  - **ART 内部机制(GC / 解释器 / JIT code cache)** → 不在本系列(详见 [Runtime/ART 系列](../01-Mechanism/Runtime/ART/README.md))

## 0. 写在前面:为什么 AOT/JIT 单独成篇

### 0.1 一个真实的安装期卡顿

**场景**:某 App 在 Android 14 升级后,首次安装耗时从 30s 退化到 180s:

```
I PackageManager: Running dex2oat on /data/app/~~xyz/base.apk
I dex2oat: dex2oat took 175.3s for /data/app/~~xyz/base.apk
I PackageManager: Install finished in 180.5s
```

**症状**:安装耗时 180s,主要在 dex2oat(dex2oat = DEX to OAT,AOT 编译工具)。

**根因排查**:
1. 该 App DEX 50MB(包含大量代码)
2. App 用 Kotlin + Java 混合,method count 50万+
3. dex2oat 默认全量 AOT 编译所有方法
4. 50万方法 × 1ms/方法 = 500s(实际 175s,部分被优化)

**修复**:
1. 用 R8 优化减少 method count(40% 节省)
2. 配置 dex2oat 用 profile-guided compilation(只编译热点)
3. 启用 install --no-dex2oat(不预编译,运行时 JIT)

**这个案例的修复需要 4 个知识**:
1. 知道 AOT / JIT / Interpreted 三种模式的差异
2. 知道 dex2oat 的工作流程
3. 知道 Profile Guided Compilation
4. 知道如何配置 dex2oat 选项

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Pixel 5(arm64-v8a)
> - Android 版本:`android-13.0.0_r41`(基线)→ 通过 OTA 升级到 `android-14.0.0_r1`
> - App:某金融 App v8.0.0(DEX 50MB,Kotlin + Java 混合,method count 50万+)
> - 工具:`adb logcat` + `oatdump` + `dex2oat --help`

> **复现步骤**:
> 1. Android 13 设备安装 v8.0.0,首次安装 + 首次冷启动:**30s**(基线)
> 2. OTA 升级到 Android 14(dex2oat 工具链 + Verify 策略升级)
> 3. 卸载 v8.0.0,重新安装
> 4. 首次安装:**180s** ⚠️(退化了 6 倍)

> **logcat 关键片段**:
> ```
> I PackageManager: Running dex2oat on /data/app/~~xyz/base.apk
> I dex2oat: dex2oat took 175.3s for /data/app/~~xyz/base.apk
> I PackageManager: Install finished in 180.5s
> I dex2oat: Compilation mode: speed
> I dex2oat: Compile method count: 512345
> I dex2oat: oat file size: 88MB
> ```

> **根因诊断命令**:
> ```bash
> # Step 1:看 dex2oat 用的什么编译模式
> $ adb shell getprop | grep -i dex2oat
> [dalvik.vm.dex2oat-flags]: --watch-dog
> [dalvik.vm.dex2oat-Xms]: 256m
> [dalvik.vm.dex2oat-Xmx]: 512m
> # Step 2:看 APK 的 method count
> $ apkanalyzer dex packages app.apk | grep "method" | wc -l
> 512345
> # Step 3:看 method 分类
> $ apkanalyzer dex packages app.apk | grep "method.*defined" | head -20
> ```

> **修复 commit-style diff**:
> ```diff
> - // build.gradle.kts 旧
> - buildTypes {
> -     release {
> -         isMinifyEnabled = false  // R8 关闭,method count 50 万+
> -     }
> - }
> + // build.gradle.kts 新
> + buildTypes {
> +     release {
> +         isMinifyEnabled = true   // R8 开启,method count -40%
> +         isShrinkResources = true
> +         proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
> +     }
> + }
> + // 同时启用 profile-guided compilation
> + android {
> +     baselineProfileFile = file("baseline-prof.txt")
> + }
> ```
> **修复后**:
> - method count:50 万 → 30 万(R8 节省 40%)
> - dex2oat 耗时:175s → 60s(节省 65%)
> - 首次安装:180s → 65s

> **架构师视角**:dex2oat 是 **"安装期性能黑洞"** —— AOSP 14 强化了 Verify 模式(新增 strict verify),method count 多寡直接决定安装耗时。**架构师必须用 R8 + baseline profile + multidex 拆分三件套** 把 dex2oat 耗时压到 60s 以下。

**这就是本篇要讲清楚的事**。

### 0.2 AOT/JIT 在 PLE 8 阶段中的位置

```
阶段 5:ClassLoader 加载应用 DEX              ← PLE 06-08
    ↓
阶段 5.5:AOT / JIT 编译(本篇主体)
├─ dex2oat 在安装时把 DEX 编译为 OAT
├─ OAT 包含机器码 + 类元数据
├─ VDEX 包含 verify 状态
├─ 运行时 JIT 编译热点方法
└─ Profile Guided Compilation 优化策略
    ↓
阶段 6:Resources 加载
    ↓
阶段 7:第一行 Java 代码执行
    │
    └─ 第一次执行方法时:
        ├─ 如果 OAT 有机器码 → 直接执行
        ├─ 如果 VDEX 有 quicken 状态 → quicken 后执行
        └─ 否则 Interpreted(慢)
```

**AOT/JIT 是 PLE 阶段 5 的"后续"**——类加载完成后,字节码要被翻译成机器码才能被 CPU 执行。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 解释 AOT / JIT / Interpreted 三种模式的差异
2. 描述 dex2oat 的工作流程和输入输出
3. 解释 Profile Guided Compilation 的优化策略
4. 描述 JIT code cache 的工作机制
5. 诊断 dex2oat 失败 / 编译产物损坏的根因

---

## 1. 为什么需要 AOT:启动速度 vs 运行速度的权衡

### 1.1 三种执行模式

**Android 有 3 种执行模式**:

| 模式 | 翻译时机 | 启动速度 | 运行速度 | 内存占用 |
|---|---|---|---|---|
| **Interpreted** | 每次执行 | 快(无编译) | 极慢(逐条解释) | 最低 |
| **JIT** | 运行时编译 | 中(JIT 启动开销) | 中(编译后快) | 中(JIT 缓存) |
| **AOT** | 安装时编译 | 快(无运行时编译) | 快(直接执行) | 高(OAT 占用空间) |

**Android 7+ 的混合模式**:

```
┌────────────────────────────────────────────────────────┐
│ 启动期:                                                 │
│  优先用 AOT(OAT 文件)                                    │
│  fallback 到 VDEX(快速 verify)                          │
│  fallback 到 DEX(Interpreted)                            │
├────────────────────────────────────────────────────────┤
│ 运行期:                                                 │
│  优先执行 AOT 机器码                                     │
│  JIT 编译热点方法                                       │
│  后台 dex2oat 异步编译未 AOT 的方法                     │
└────────────────────────────────────────────────────────┘
```

**架构师必记**:**现代 Android 是 AOT + JIT + Interpreted 混合**。**没有"纯 AOT"或"纯 JIT"**。

### 1.2 AOT 的优势与代价

**AOT 的优势**:
- 启动期无运行时编译开销
- 方法直接执行(无解释开销)
- 冷启动性能可预测

**AOT 的代价**:
- 安装时编译耗时(分钟级)
- OAT 文件占用空间(2-5 倍 DEX)
- 重编译代价大(类更新要重新 AOT)
- 部分代码可能从未被调用(浪费编译时间)

### 1.3 JIT 的优势与代价

**JIT 的优势**:
- 无需安装时编译
- 只编译热点方法(节省空间)
- 可根据运行时 profile 优化
- 类更新即时生效

**JIT 的代价**:
- 启动期 JIT 开销
- 运行时编译占用 CPU(影响冷启动)
- JIT 缓存占用内存(20-50MB)

### 1.4 Profile Guided Compilation(PGC)

**PGC 是 Android 7+ 的核心优化**:用真实使用数据指导 AOT 编译。

```
PGC 的 3 步:
1. 运行时收集 profile(cloud + on-device)
   - 哪些方法被调用(热点)
   - 调用频率
   - 调用链
2. dex2oat 根据 profile 选择性编译
   - 只编译热点方法
   - 其他方法保持 Interpreted 或 quicken
3. 持续优化
   - profile 变化时,重新 AOT
```

**优势**:
- 节省 30-50% AOT 时间
- 节省 30-50% OAT 空间
- 启动性能更接近全 AOT

**架构师必记**:**PGC 是"用真实使用数据换编译效率"**。**核心思想:不预编译可能不用的代码**。

---

## 2. dex2oat 详解

### 2.1 dex2oat 是什么

**dex2oat** 是 Android 的 AOT 编译器,输入 DEX,输出 OAT + VDEX + CDEX。

**源码位置**:`art/dex2oat/dex2oat.cc`

**典型调用**:

```bash
$ dex2oat \
    --dex-input=app.apk \
    --oat-file=app.oat \
    --vdex-file=app.vdex \
    --instruction-set=arm64 \
    --compiler-filter=speed-profile \
    --profile-file=app.prof
```

**关键参数**:

| 参数 | 含义 |
|---|---|
| `--dex-input` | 输入 DEX 或 APK |
| `--oat-file` | 输出 OAT 文件 |
| `--vdex-file` | 输出 VDEX 文件(verify 状态) |
| `--instruction-set` | 目标架构(arm64 / x86_64) |
| `--compiler-filter` | 编译策略(见 §2.3) |
| `--profile-file` | Profile 文件(PGC 用) |

### 2.2 dex2oat 工作流程

```
dex2oat 输入:DEX + Profile(可选)
    ↓
1. 解析 DEX(本系列 P06)
    ├─ 读 5 大 id 表
    ├─ 读 class_defs
    └─ 解析所有类
    ↓
2. Verify(本系列 P08)
    ├─ 字节码验证
    ├─ 类型检查
    └─ 输出 verify 状态(写入 VDEX)
    ↓
3. 优化
    ├─ 死代码消除
    ├─ 方法内联
    ├─ 循环优化
    ├─ 寄存器分配
    └─ 指令调度
    ↓
4. 编译
    ├─ 字节码 → 机器码(arm64)
    └─ 生成 OAT
    ↓
5. 输出
    ├─ OAT(机器码 + 类元数据)
    └─ VDEX(verify 状态)
```

**关键事实**:
- **dex2oat 一次跑完整个 DEX**(不是流式)
- **Verify 阶段必须先于编译**(未 verify 不能编译)
- **优化阶段是耗时大头**(占 dex2oat 60-80% 时间)

### 2.3 编译策略(--compiler-filter)

**dex2oat 支持 7 种编译策略**:

| Filter | 含义 | 耗时 | OAT 大小 | 启动速度 |
|---|---|---|---|---|
| `verify-none` | 只 verify,不编译 | 极快 | 极小 | 慢 |
| `verify-at-runtime` | 运行时 verify | 快 | 小 | 慢 |
| `verify-profile` | 按 profile 编译 verify 部分 | 中 | 小 | 中 |
| `speed-profile` | 按 profile 编译 speed 部分 | 中 | 中 | 快 |
| `speed` | 编译所有方法,不做 speed 优化 | 慢 | 大 | 极快 |
| `space` | 编译所有方法,做 space 优化 | 慢 | 中 | 极快 |
| `space-profile` | 按 profile + space 优化 | 慢 | 中 | 快 |

**Android 14 的默认策略**:`speed-profile`(从 Android 7 开始)。

**架构师必记**:**`speed-profile` 是最佳折中**——只编译热点方法,启动速度接近全 AOT,空间节省 30-50%。

### 2.4 dex2oat 触发的 3 个时机

**dex2oat 在 3 个时机运行**:

| 时机 | 触发条件 | 典型耗时 |
|---|---|---|
| **安装时** | `pm install` 流程 | 30-180s |
| **后台 idle** | 设备 idle 时(`pm dexopt -p`) | 60-300s |
| **运行时 JIT** | 热点方法被频繁调用 | ms 级 |

**关键事实**:
- **安装时只做"基础" AOT**(verify + 关键方法)
- **后台 idle 做"完整" AOT**(全方法)
- **运行时 JIT 补充 PGC 未覆盖的方法**

### 2.5 真实案例:dex2oat 失败的诊断

**症状**:
```
I PackageManager: Install failed: INSTALL_FAILED_DEXOPT
I dex2oat: dex2oat failed: out of memory
```

**根因**:
1. DEX 太大(> 100MB)
2. dex2oat 默认 1GB 内存不够
3. OOM 导致 dex2oat 失败

**修复**:
```bash
# 1. 增大 dex2oat 内存
$ adb shell setprop dalvik.vm.dex2oat-Xmx 2g

# 2. 用 --no-dex2oat 安装(只 verify)
$ adb install --no-dex2oat app.apk

# 3. R8 优化减少 DEX 大小
```

---

## 3. OAT 文件格式

### 3.1 OAT 是什么

**OAT(Optimized Art)** 是 dex2oat 的输出,**包含 AOT 编译的机器码 + 类元数据**。

**OAT 文件结构**:

```
┌─────────────────────────────────────────────────────┐
│ OAT 文件                                                │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐                                   │
│  │ OAT Header   │ OAT 文件头                         │
│  └──────────────┘                                   │
│                                                     │
│  ┌──────────────┐                                   │
│  │ OAT DexFile  │ 包含原始 DEX 引用                  │
│  │              │ (可能内嵌 VDEX)                    │
│  └──────────────┘                                   │
│                                                     │
│  ┌──────────────┐                                   │
│  │ Class Table  │ 类索引                              │
│  └──────────────┘                                   │
│                                                     │
│  ┌──────────────┐                                   │
│  │ Method Table │ 方法索引(指向机器码)              │
│  └──────────────┘                                   │
│                                                     │
│  ┌──────────────┐                                   │
│  │ 机器码段     │ AOT 编译的 arm64 机器码           │
│  │ (text 段)    │                                   │
│  └──────────────┘                                   │
│                                                     │
│  ┌──────────────┐                                   │
│  │ 元数据段     │ 类元数据、vtable、iftable          │
│  │ (data 段)    │                                   │
│  └──────────────┘                                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 3.2 OAT 头

```c
// art/runtime/oat_file.h
struct OatHeader {
    uint8_t magic[4];        // "oat\n"
    uint8_t version[4];      // 版本号
    uint32_t checksum;       // 校验和
    uint32_t instruction_set;  // 目标架构
    uint32_t key_value_size;   // key-value 存储大小
    // ...
};
```

**真实案例**:
```bash
$ oatdump --header app.oat
MAGIC: oat\n
VERSION: 183
CHECKSUM: 0xabcdef01
INSTRUCTION SET: arm64
```

### 3.3 用 oatdump 拆解 OAT

**oatdump 是 OAT 文件的反汇编工具**:

```bash
# 1. 拆解 OAT 头
$ oatdump --header app.oat

# 2. 拆解所有类
$ oatdump --dump-classes app.oat

# 3. 拆解某个方法
$ oatdump --method "com.example.MainActivity.onCreate" app.oat
```

**真实输出**(简化):

```
Class #123: 'Lcom/example/MainActivity;'
  Method #456: 'onCreate(Landroid/os/Bundle;)V' (offset 0x12345)
    CODE: (size 234 bytes)
    0x0000:  d10043ff   sub  sp, sp, #0x10
    0x0004:  a9025ff8   stp  x24, x23, [sp, #0x20]
    0x0008:  a90367fa   stp  x26, x25, [sp, #0x30]
    0x000c:  aa0003f3   mov  x19, x0
    0x0010:  94012345   bl   0x12345  ; Landroidx/appcompat/app/AppCompatActivity;.onCreate:(Landroid/os/Bundle;)V
    ...
```

**架构师必记**:**oatdump 是 AOT 性能分析的核心工具**。**它能把 OAT 反汇编为 ARM 汇编,直接看 JIT 优化效果**。

---

## 4. ART 三态切换

### 4.1 AOT / JIT / Interpreted 切换策略

**ART 在运行时动态切换三种模式**:

```
方法首次调用:
    ↓
1. 看 OAT 是否有机器码
    ├─ 有 → 直接执行(AOT)✅
    └─ 没有 → 继续
    ↓
2. 看 VDEX 是否有 quicken 状态
    ├─ 有 → quicken 后执行(快速 verify)✅
    └─ 没有 → 继续
    ↓
3. Interpreted(解释执行)❌ 慢
    ↓
4. JIT 后台编译该方法(标记为热点)
    ↓
5. 后续调用 → JIT 编译后执行✅
```

**关键事实**:
- **AOT 优先**(启动期所有调用走 AOT)
- **JIT 补充**(AOT 没编译的方法,JIT 编译热点)
- **Interpreted 兜底**(JIT 还没编译的,先解释执行)

### 4.2 三态切换的实现

**`art/runtime/oat_file_manager.cc`**(简化):

```c
const void* OatFileManager::GetOatMethodCode(ArtMethod* method) {
    // 1. 查 OAT 缓存
    const OatFile::OatMethod* oat_method = oat_file_->GetOatMethod(method);
    if (oat_method != nullptr) {
        return oat_method->GetCode();
    }
    
    // 2. OAT 没有,返回 nullptr(让调用方用 Interpreted 或 JIT)
    return nullptr;
}
```

**`art/runtime/jit/jit.cc`**(简化):

```c
void Jit::MethodEntered(Thread* self, ArtMethod* method) {
    // 1. 增加调用计数
    method->hotness_count_++;
    
    // 2. 如果达到 hotness 阈值,触发 JIT 编译
    if (method->hotness_count_ >= kJitHotnessThreshold) {
        CompileMethod(method);
    }
}
```

**架构师必记**:**ART 维护每个方法的"热度"**。**达到阈值就触发 JIT 编译**。**这是 ART 自适应的核心**。

### 4.3 真实案例:启动期方法执行模式分析

**用 simpleperf + oatdump 分析启动期方法执行模式**:

```bash
# 1. 抓启动期 perf 数据
$ adb shell simpleperf record -e cpu-cycles -p PID -o /data/local/tmp/perf.data
# 等启动完成

# 2. 看热点方法
$ adb shell simpleperf report -i /data/local/tmp/perf.data | head -30

# 3. 对热点方法,看是 AOT / JIT / Interpreted
$ adb shell oatdump --method <method> /data/app/~~xyz/oat/arm64/base.odex | head -20
```

**判断方法执行模式**:

| 输出 | 模式 |
|---|---|
| 有 `CODE:` 段(汇编代码) | AOT ✅ |
| 有 `QUICKENED:` 标记 | quicken(JIT 前的快速 verify) |
| 只有 method signature,无 code | Interpreted ❌ |

**架构师必记**:**如果热点方法是 Interpreted,说明 dex2oat 没编译它**。**需要调整 --compiler-filter 或 profile**。

---

## 5. JIT 编译流水线

### 5.1 JIT 触发条件

**JIT 在两个条件下触发**:

| 条件 | 阈值 | 来源 |
|---|---|---|
| **方法热度** | 调用次数 > kJitHotnessThreshold(默认 10000) | 计数器 |
| **栈深度** | 调用栈深度 < kJitMaxStackDepth(默认 20) | 防止过深递归 |

**JIT 编译流程**:

```
MethodEntered(method):
    ↓
1. hotness_count_++
    ↓
2. if hotness_count_ >= threshold:
    ↓
3. 调 Jit::CompileMethod(method)
    ├─ 锁定方法(JIT 编译期间)
    ├─ 编译字节码 → 机器码
    ├─ 写入 JIT code cache
    ├─ 设置 method 的 entry_point 指向新机器码
    └─ 解锁方法
```

### 5.2 JIT Code Cache

**JIT 编译的机器码存在 JIT code cache**(`art/runtime/jit/jit_code_cache.cc`):

```c
class JitCodeCache {
    // 4 个独立的 code cache
    std::unique_ptr<JitMemoryRegion> code_cache_;          // 普通方法
    std::unique_ptr<JitMemoryRegion> profiled_code_cache_; // Profile 方法
    // ...
    
    // 添加方法到 cache
    uint8_t* AddCode(const uint8_t* code, size_t size, ...);
};
```

**关键事实**:
- **JIT code cache 默认 20-50MB**(可配置)
- **JIT 编译的代码在 cache 满了时会被回收**
- **JIT code cache 内的内存被 mmap 为 rwx**(可执行)

### 5.3 JIT 的内存管理

**JIT code cache 的内存生命周期**:

| 阶段 | 内存位置 | 权限 |
|---|---|---|
| **JIT 编译时** | 临时 mmap | rw- |
| **方法已 JIT** | JIT code cache | rwx |
| **方法被回收** | cache 满时回收 | - |

**JIT code cache 满的处理**:
- **回收最少调用的方法**(LRU)
- **回收过大的方法**
- **回收 profile 变化的方法**

**架构师必记**:**JIT code cache 是 ART 内存占用的"隐藏大头"**。**冷启动 20-50MB 来自 JIT cache**。

### 5.4 JIT 的优劣势

**JIT 优势**:
- 无需安装时编译(节省安装时间)
- 只编译热点(节省空间)
- 运行时 profile 优化更精确

**JIT 劣势**:
- 首次调用方法慢(JIT 编译耗时)
- 占用运行时 CPU(影响冷启动)
- JIT cache 占用内存
- 占用 rwx 内存(安全风险)

**架构师必记**:**JIT cache 用 rwx 内存**(可执行 + 可写)。**这是 Android 12+ 强化 rwx 检查的对象**。

---

## 6. Profile Guided Compilation 详解

### 6.1 Profile 是什么

**Profile 是"方法使用数据"**——记录哪些方法被调用、调用频率、调用链。

**Profile 类型**:

| 类型 | 来源 | 时机 |
|---|---|---|
| **Cloud Profile** | Google Play(系统 App) | Play 服务上传 |
| **On-device Profile** | 设备本地收集 | 运行时 |
| **Baseline Profile** | 开发者提供 | 应用启动 |

**Profile 文件格式**:`/data/misc/profiles/cur/<uid>/<package_name>/primary.prof`

**真实案例**:

```bash
# 看一个 App 的 profile
$ adb shell ls /data/misc/profiles/cur/0/com.example.app/
# primary.prof(基准 profile)
# cur.prof(当前使用数据)
```

### 6.2 Profile 的结构

```c
// art/profman/profman.proto(简化)
message Profile {
    repeated MethodHotness method_hotnesses = 1;  // 方法热度
    repeated ClassHotness class_hotnesses = 2;    // 类热度
    // ...
}

message MethodHotness {
    string dex_location = 1;    // DEX 文件
    uint32 dex_method_index = 2;  // 方法索引
    uint32 method_hotness = 3;    // 热度值
    // ...
}
```

**关键事实**:
- **Profile 用 protobuf 编码**(节省空间)
- **Profile 大小通常 1-5MB**
- **Profile 记录"热点方法"** + 热度值

### 6.3 PGC 工作流程

```
App 启动 → 收集 on-device profile(后台)
    ↓
一段时间后(7-30 天)
    ↓
后台 dex2oat 用 profile 编译(--compiler-filter=speed-profile)
    ↓
只编译 profile 里的热点方法
    ↓
OAT 文件更新(覆盖原文件)
    ↓
后续启动速度提升
```

**优势**:
- 启动速度接近全 AOT
- 节省 30-50% OAT 空间
- 持续优化(7-30 天后重编译)

### 6.4 Baseline Profile(Android 14 引入)

**Baseline Profile 是开发者提供的"启动期热点"**——让 ART 在首次启动就能快速编译。

**使用**:

```kotlin
// 在 build.gradle.kts 里
android {
    buildTypes {
        release {
            baselineProfileFile = file("baseline-prof.txt")
        }
    }
}
```

**baseline-prof.txt 格式**:

```
HSPLcom/example/MainActivity;->onCreate(Landroid/os/Bundle;)V
HSPLcom/example/MainActivity;->onResume()V
```

**优势**:
- 首次启动就有 PGC 优化
- 冷启动速度提升 20-40%
- 云端 baseline profile 可被其他用户使用

**架构师必记**:**Baseline Profile 是 Android 14 的核心优化**。**强烈建议大型 App 启用**。

---

## 7. AOT / JIT / Interpreted 三态对比

### 7.1 三态对比

| 维度 | AOT | JIT | Interpreted |
|---|---|---|---|
| **编译时机** | 安装时 | 运行时 | 不编译 |
| **首次执行** | 直接跑 | 解释 + 后台编译 | 解释 |
| **后续执行** | 直接跑 | 跑 JIT 编译后代码 | 解释 |
| **内存占用** | 大(OAT) | 中(JIT cache) | 小 |
| **CPU 占用** | 一次性高 | 持续中 | 持续高 |
| **启动时间** | 快 | 中(JIT 开销) | 慢 |
| **运行时间** | 快 | 中 | 慢 |

### 7.2 三态的协作

**Android 7+ 三态协作**:

```
启动期(冷启动):
  1. AOT(主要) - OAT 里的机器码直接跑
  2. quicken(次要) - VDEX 里有 verify 状态,快速初始化
  3. Interpreted(兜底) - 没编译的方法,先解释

运行期(热运行):
  1. AOT(主要) - OAT 里的机器码
  2. JIT(补充) - 热点方法被 JIT 编译
  3. Interpreted(兜底) - JIT 还没编译的

后台期:
  1. dex2oat 异步编译 - 用 profile 编译热点
  2. 替换 OAT - 新 OAT 覆盖旧 OAT
```

### 7.3 真实案例:启动期方法执行模式分布

**典型 App 启动期 1000 个方法调用**:

| 模式 | 比例 | 备注 |
|---|---|---|
| **AOT** | 70-85% | framework + dex2oat 编译的 App 方法 |
| **quicken** | 5-10% | VDEX 验证过,快速 verify |
| **JIT** | 5-15% | 运行时编译的热点 |
| **Interpreted** | 5-10% | 未编译 |

**架构师必记**:**AOT 占比应该 > 70%**,否则启动慢。

---

## 8. dex2oat 启动期性能影响

### 8.1 安装期耗时

**典型 App 安装时 dex2oat 耗时**:

| App 规模 | method count | dex2oat 耗时 |
|---|---|---|
| 小(< 10MB DEX) | < 50K | 5-30s |
| 中(10-50MB DEX) | 50K-300K | 30-180s |
| 大(> 50MB DEX) | > 300K | 180-600s |

**关键事实**:
- **dex2oat 耗时 ≈ method count × 1-2ms**
- **优化空间在 --compiler-filter**(speed-profile 比 speed 快 30-50%)

### 8.2 运行时 JIT 启动期影响

**JIT 编译对冷启动的影响**:

| 阶段 | 耗时 |
|---|---|
| 启动期首次调用热点方法 | 1-10ms(JIT 编译) |
| 后续调用 | < 1μs(已编译) |

**关键事实**:
- **JIT 编译只影响"首次调用"**
- **后台线程编译,不阻塞主线程**
- **但占用 CPU,可能影响其他线程**

### 8.3 4 个优化技巧

| 技巧 | 节省 | 难度 |
|---|---|---|
| **用 speed-profile 而不是 speed** | 30-50% dex2oat 时间 | 低 |
| **提供 Baseline Profile** | 启动期 20-40% 提升 | 中 |
| **R8 优化 method count** | 30-50% dex2oat 时间 | 低 |
| **关闭非热点 .so 的 BIND_NOW** | 启动期 5-10ms | 低 |

---

## 9. 真实案例:AOT/JIT 失败的诊断

### 9.1 4 类失败模式

| 失败 | 触发条件 | 错误 |
|---|---|---|
| **dex2oat OOM** | DEX 太大,内存不够 | `dex2oat failed: out of memory` |
| **OAT 文件损坏** | 存储错误 / 签名错误 | `OAT file verification failed` |
| **JIT 编译失败** | 类不在白名单 | `JIT: skipped non-hot method` |
| **Verify 失败** | 字节码非法(本系列 P08) | `VerifyError` |

### 9.2 真实案例:dex2oat OOM

**症状**(回到 §0.1):
```
dex2oat took 175.3s for /data/app/~~xyz/base.apk
```

**优化**:

```bash
# 1. R8 优化
# build.gradle.kts:
android {
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
        }
    }
}

# 2. 用 --compiler-filter=speed-profile
# 默认是 speed-profile,但部分 OEM 改了

# 3. 关闭资源压缩(节省 dex2oat 内存)
$ adb install --no-dex2oat app.apk
```

### 9.3 真实案例:OAT 损坏

**症状**:
```
E art : Failed to load OAT file '/data/app/~~xyz/oat/arm64/base.odex': bad checksum
E AndroidRuntime: FATAL EXCEPTION: main
E AndroidRuntime: java.lang.VerifyError
```

**根因**:
1. OAT 文件损坏(存储错误 / 签名问题)
2. OAT 与 DEX 版本不匹配

**修复**:
```bash
# 1. 重新安装 App
$ adb install -r app.apk

# 2. 强制重新 dex2oat
$ adb shell cmd package compile -m verify -f com.example.app
$ adb shell cmd package compile -m speed-profile -f com.example.app
```

### 9.4 真实案例:JIT 卡顿

**症状**:
- 启动期某方法首次调用卡 100ms
- logcat 看到 `JIT compiled` 日志

**根因**:
- 热点方法被 JIT 编译
- 首次调用要等编译完成

**修复**:
- 用 Baseline Profile 预编译
- 用 AOT 替代 JIT(--compiler-filter=speed)

---

## 10. 架构师视角:AOT/JIT 的 5 个核心洞察

### 10.1 洞察 1:现代 Android 是 AOT + JIT + Interpreted 混合

**没有"纯 AOT"或"纯 JIT"**。**三态协作是 Android 7+ 的设计哲学**。

### 10.2 洞察 2:dex2oat 是启动期关键路径

**dex2oat 耗时占安装 30-90%**。**优化 --compiler-filter 和 R8 是减少 dex2oat 时间的关键**。

### 10.3 洞察 3:Profile Guided Compilation 是"用真实数据换效率"

**PGC 只编译热点方法,节省 30-50% 空间**。**配合 Baseline Profile 效果更佳**。

### 10.4 洞察 4:JIT 内存是冷启动期的"隐藏大头"

**JIT code cache 占用 20-50MB**。**这是冷启动期内存峰值的主要贡献者之一**。

### 10.5 洞察 5:从 AOT/JIT 失败直接映射到故障现象

| 故障现象 | AOT/JIT 根因 |
|---|---|
| 安装期 100s+ | dex2oat 耗时 |
| 启动期方法卡 100ms+ | JIT 编译首次调用 |
| 启动期 OOM | JIT cache + linear alloc 占用 |
| `OAT file verification failed` | OAT 损坏 |
| 启动慢 200ms+ | speed-profile 比例低 |

---

## 11. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **三态混合是 Android 的设计哲学** | AOT + JIT + Interpreted 协作 |
| 2 | **dex2oat 是安装期关键路径** | 占安装时间 30-90% |
| 3 | **PGC 用真实数据换编译效率** | speed-profile 节省 30-50% 空间 |
| 4 | **JIT cache 占冷启动 20-50MB** | 内存峰值的主要贡献者 |
| 5 | **Baseline Profile 是冷启动 20-40% 提升** | Android 14 引入 |

---

## 12. PLE 第三篇章(06-09)完结

**DEX 与 ART 4 篇全部完成**:

| 篇号 | 标题 | 大小 |
|---|---|---|
| 06 | DEX/ODEX/VDEX 格式 | 42KB |
| 07 | ART ClassLoader 体系 | 30KB |
| 08 | 类加载生命周期 | 29KB |
| 09 | AOT/JIT 编译流水线 | 本篇 |

---

## 13. 下一篇预告

10 篇《资源加载:AssetManager / ApkAssets / ResTable》是 PLE 第四篇章(Resources 与 APK 2 篇)的开篇,会沿着 PLE 06-09 的"DEX 加载"埋下的线索,深入讲:

- 资源子系统的三层结构:AssetManager → ApkAssets → ResTable
- AssetManager 构造:framework 与 app 的不同初始化路径
- addAssetPath 流程:路径解析、ApkAssets 创建、缓存
- ResTable 构建:arsc 解析、type spec、entry 索引
- 资源查找:从 R.id 到具体值的 5 步路径
- 资源匹配:configuration(语言/分辨率/dpi/orientation)选择
- 资源缓存:ResCache / Theme / Drawable cache
- 架构师视角:资源加载是冷启动的"被低估的瓶颈"

**10 篇预计 1 周后产出**,届时一起发你看。

---

## 附录 A:3 种执行模式对比

| 维度 | AOT | JIT | Interpreted |
|---|---|---|---|
| 编译时机 | 安装时 | 运行时 | 不编译 |
| 首次执行 | 直接跑 | 解释 + 后台编译 | 解释 |
| 后续执行 | 直接跑 | JIT 后 | 解释 |
| 内存 | 大 | 中 | 小 |
| 启动 | 快 | 中 | 慢 |

## 附录 B:7 种 --compiler-filter

| Filter | 编译什么 | 耗时 | OAT 大小 |
|---|---|---|---|
| verify-none | 不编译 | 极快 | 极小 |
| verify-at-runtime | 运行时 verify | 快 | 小 |
| verify-profile | profile 里的 verify | 中 | 小 |
| speed-profile | profile + speed 优化 | 中 | 中 |
| speed | 全部编译 | 慢 | 大 |
| space | 全部编译 + space 优化 | 慢 | 中 |
| space-profile | profile + space | 慢 | 中 |

## 附录 C:dex2oat 3 个触发时机

| 时机 | 触发条件 | 耗时 |
|---|---|---|
| 安装时 | `pm install` | 30-180s |
| 后台 idle | `pm dexopt` | 60-300s |
| 运行时 JIT | 热点方法 | ms 级 |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 10 资源加载 | 资源加载与 DEX 加载并行的两大类启动期工作 |
| 12 进程启动 | Zygote fork 时,OAT 状态被继承 |
| 14 风险地图 | §9 失败诊断的"4 类根因"是 P14 速查表核心 |

---

> **本篇把 AOT/JIT 拆解到"3 模式 + dex2oat + OAT + PGC + JIT cache"5 个维度。**
> **10 篇会在这个基础上,讲 Resources 加载——APK 里另一半内容(非 DEX)怎么被加载。**
> **记住三态混合、dex2oat、PGC、Baseline Profile、JIT cache,你的 AOT/JIT 视角就立住了。**
