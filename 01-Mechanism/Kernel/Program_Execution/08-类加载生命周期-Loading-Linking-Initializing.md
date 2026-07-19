# 08-类加载生命周期:Loading → Linking → Initializing

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
>
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15` / `android15-6.1`(Android 14 强化 verify 涉及 `prctl(PR_SET_VMA)` 内核调用,版本差异显著)+ `art/runtime/class_linker.cc` + `art/runtime/verifier/method_verifier.cc` + `art/runtime/class_init.cc` + JVMS(The Java Virtual Machine Specification)第 12 章
>
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
>
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) → [06-DEX](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md) → [07-ClassLoader](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md)
>
> **下一篇**:[09-AOT / JIT 编译流水线:dex2oat 与 ART 运行时编译](09-AOT-JIT编译流水线-dex2oat与ART运行时编译.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 7 篇(Java 侧 · 类加载 7 阶段层)
- **强依赖**:**[PLE-01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-06 DEX](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md)** + **[PLE-07 ClassLoader](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md)**
- **承接自**:PLE-07 已讲 ClassLoader 树如何找到类;本篇是骨架上"链接+初始化"动作在 Java 侧的具体载体(7 阶段生命周期)
- **衔接去**:下一篇 [PLE-09 AOT/JIT](09-AOT-JIT编译流水线-dex2oat与ART运行时编译.md) 讲"类加载完成后字节码怎么变成机器码"(dex2oat + JIT)
- **不重复内容**:
  - **ClassLoader 树 / parent delegation** → 详见 [PLE-07](07-ART-ClassLoader体系-从BootClassLoader到PathClassLoader.md)
  - **DEX 文件结构** → 详见 [PLE-06](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md)
  - **dex2oat / AOT / JIT 编译流水线** → 详见 [PLE-09](09-AOT-JIT编译流水线-dex2oat与ART运行时编译.md)
  - **Native 侧 `__attribute__((constructor))` 与 Java `<clinit>` 的对仗** → 详见 [PLE-05 §0.2](05-init_array与构造函数链-静态初始化的执行顺序.md)

## 0. 写在前面:为什么"类加载生命周期"单独成篇

### 0.1 一个真实的崩溃现场

**场景**:某 App 在 Android 7 升级到 14 后,启动后偶发崩溃:

```
E AndroidRuntime: FATAL EXCEPTION: main
E AndroidRuntime: java.lang.VerifyError: Rejecting class com.example.MyClass because it failed compile-time verification
E AndroidRuntime:        at java.lang.Class<MyClass>.classLinker::defineClass(Native Method)
```

**症状**:`VerifyError`,类验证失败,启动崩溃。

**根因排查**:
1. App 用了某个第三方库,该库在编译时用了一些"非常规"字节码
2. Android 14 加强了 verify 阶段(更严格的字节码校验)
3. 该库的字节码在老 ART 上能过 verify,在 Android 14 上失败
4. 启动时 loadClass 触发 verify → VerifyError

**这个案例的修复需要 4 个知识**:
1. 知道类加载的 7 个阶段
2. 知道 Verify 阶段在做什么
3. 知道 ART 14 的 verify 强化
4. 知道怎么避免/绕过 verify 失败

**这就是本篇要讲清楚的事**。

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Pixel 4a(arm64-v8a)
> - Android 版本:`android-7.0.0_r33`(基线)→ 通过 OTA 升级到 `android-14.0.0_r1`
> - App:某电商 App v3.0.0,集成 1 个老旧的支付 SDK(2019 年发布)
> - 工具:`baksmali` + `art` runtime verify log

> **复现步骤**:
> 1. Android 7 设备安装 v3.0.0,正常运行
> 2. OTA 升级到 Android 14
> 3. 启动 App,在支付 SDK 加载阶段**必现**崩溃
> 4. 闪退信息: `VerifyError: Rejecting class com.example.pay.PayBridge because it failed compile-time verification`

> **logcat 关键片段**:
> ```
> E AndroidRuntime: FATAL EXCEPTION: main
> E AndroidRuntime: java.lang.VerifyError: Rejecting class com.example.pay.PayBridge
>              because it failed compile-time verification (declared in the dex file)
> E AndroidRuntime:        at java.lang.Class<PayBridge>.classLinker::defineClass(Native Method)
> E AndroidRuntime:        at java.lang.ClassLoader.defineClass(ClassLoader.java:...)
> E AndroidRuntime:        at java.lang.DexFile.loadClass(DexFile.java:...)
> E AndroidRuntime:        at com.example.app.PayActivity.onCreate(PayActivity.java:30)
> W art      : Verification failed for class com.example.pay.PayBridge
> W art      : method: <clinit> at bytecode offset 0x0042
> W art      : type=Undefined, expected=Double  ← 操作数栈类型不匹配
> ```

> **根因诊断命令**:
> ```bash
> # Step 1:看 ART verify 日志
> $ adb logcat -d | grep -i "verify\|Rejecting" | head -30
> # Step 2:用 baksmali 拆 SDK 的 class
> $ baksmali disassemble pay-sdk.apk -o smali/
> $ cat smali/com/example/pay/PayBridge.smali | head -100
> # 找到 <clinit> 中 offset 0x0042 处的字节码
> # Step 3:用 javap 看 JDK 编译的字节码作对比
> $ javap -c -p PayBridge.class
> ```

> **修复 commit-style diff**:
> ```diff
> - # 旧支付 SDK(2019 年发布,字节码不规范)
> + # 方案 A:升级支付 SDK 到最新版(修复了字节码)
> + implementation 'com.example.pay:pay-sdk:4.2.0'
> +
> + # 方案 B:如必须保留旧 SDK,在 R8 配置里 keep + 允许混淆
> + # proguard-rules.pro:
> + -keep class com.example.pay.** { *; }
> + -keep,allowobfuscation class com.example.** { *; }
> +
> + # 方案 C:在 AndroidManifest 里启用 vmSafeMode(不推荐)
> + # <application android:vmSafeMode="true" ... />
> +
> + # 方案 D:用 useEmbeddedDex 让 ART 跳过 verify(也不推荐)
> ```
> **修复后**:崩溃消失,支付流程正常。**额外建议**:方案 A 是首选,SDK 升级是治本;方案 B 是临时方案。

> **架构师视角**:Verify 失败是 **"老代码在新 ART 上踩雷"** 的典型表现。**架构师必须建立"Android 大版本升级必做的兼容性测试矩阵"**,特别是支付 / 推送 / 登录等关键 SDK。

### 0.2 类加载生命周期在 PLE 8 阶段中的位置

```
阶段 5:ClassLoader 加载应用 DEX
├─ mmap DEX 文件(本系列 P06)
├─ 创建 DexFile 对象
├─ **本篇:类加载生命周期(7 个阶段)**
│   ├─ Loading:loadClass
│   ├─ Linking:Verify + Prepare + Resolve
│   └─ Initializing:\<clinit\>
├─ 创建 ArtMethod / ArtField / Class 对象
└─ 返回 Class 对象给调用方
```

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 解释类加载的 7 个阶段(Loading / Verifying / Preparing / Resolving / Initializing / Using / Unloading)
2. 描述 Verify 阶段的具体内容
3. 解释 \<clinit\> 的执行机制
4. 诊断 `VerifyError` / `NoClassDefFoundError` / `ClassCircularityError` 的根因
5. 优化类加载启动时间

---

## 1. 类加载的 7 个阶段

### 1.1 JVM 规范的 7 阶段

**JVM 规范(Java SE 8+)定义的类加载 7 个阶段**:

```
┌──────────────────────────────────────────────────────────┐
│ 类加载生命周期                                              │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  1. Loading(加载)         ClassLoader.loadClass          │
│     ├─ 通过全限定名读字节流                                │
│     ├─ 静态结构转为方法区数据结构                          │
│     └─ 生成 Class 对象                                     │
│                                                          │
│  2. Verifying(验证)        class_linker::VerifyClass     │
│     ├─ 文件格式验证(magic / version)                      │
│     ├─ 元数据验证(类继承 / 接口实现)                      │
│     ├─ 字节码验证(操作数栈 / 控制流 / 类型)              │
│     └─ 符号引用验证(类 / 方法 / 字段是否存在)            │
│                                                          │
│  3. Preparing(准备)        class_linker::PrepareClass   │
│     ├─ 类变量(static)分配内存                            │
│     ├─ 设置默认值(0 / false / null)                      │
│     └─ final static 常量在此时设为编译期值               │
│                                                          │
│  4. Resolving(解析)        class_linker::ResolveClass   │
│     ├─ 符号引用 → 直接引用                                │
│     ├─ 类/接口解析                                         │
│     ├─ 字段解析                                           │
│     ├─ 方法解析                                           │
│     └─ 接口方法解析                                       │
│                                                          │
│  5. Initializing(初始化)   class_init.cc::InitializeClass│
│     ├─ 执行 \<clinit\> 方法                                │
│     ├─ 静态变量赋值                                       │
│     └─ static 块执行                                      │
│                                                          │
│  6. Using(使用)            (运行时)                      │
│     ├─ 正常使用类                                         │
│     └─ 主动引用 / 被动引用                                │
│                                                          │
│  7. Unloading(卸载)        Class unloading 触发条件      │
│     └─ ClassLoader 不可达 + Class 不可达                 │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**关键事实**:
- **2-4 阶段(Verify/Prepare/Resolve)统称 Linking(链接)**
- **5 阶段(Init)之前,类不能被主动使用**(new / 静态方法 / 静态字段)
- **5 阶段之后,类进入"已初始化"状态,可以正常使用**

### 1.2 ART 的实现与 JVM 规范的差异

**ART 的实现与 JVM 规范基本一致,但有几个差异**:

| 差异 | 说明 |
|---|---|
| **Verify 时机** | ART 14+ 默认在 AOT 时(dex2oat)做完整 verify,运行时不重复 |
| **quicken 状态** | VDEX 存储 verify 状态,运行时不重 verify |
| **Class 表示** | ART 的 Class 是 C++ 对象 mirror::Class(不是 java.lang.Class) |
| **Class 创建** | mmap + parse + ArtMethod 表创建 + Class 分配 |
| **Init 触发** | 首次主动引用(规范相同) |

**架构师必记**:**ART 14+ 的 verify 走 AOT 路径(dex2oat 时 verify)**,**运行时只做轻量级 verify**。

---

## 2. Loading 阶段:把 DEX 字节变成 Class 对象

### 2.1 Loading 阶段做什么

**Loading 阶段完成 3 件事**:

1. **通过全限定名读字节流**(从 DEX 文件)
2. **静态结构转为方法区数据结构**(Class 对象)
3. **生成 java.lang.Class 对象**(Java 端可见的 Class)

### 2.2 ART 的 Loading 实现

```c
// art/runtime/class_linker.cc(简化)
mirror::Class* ClassLinker::DefineClass(Thread* self, ...) {
    // 1. 读 DEX 字节流
    const uint8_t* class_data = ...;  // 已在 mmap 后拿到
    
    // 2. 解析 class_def_item
    ClassData class_data;
    dex_file->ReadClassData(class_data);
    
    // 3. 分配 mirror::Class 对象
    mirror::Class* klass = AllocateClass(dex_file, class_def);
    
    // 4. 注册到 ClassTable
    mirror::Class* existing = InsertClass(descriptor, klass, ...);
    
    // 5. 链接(Verify + Prepare + Resolve)
    if (!LinkClass(self, descriptor, klass, ...)) {
        return nullptr;  // 链接失败
    }
    
    return klass;
}
```

**关键事实**:
- **Class 对象分配在 ART 堆**(不是 Java 堆)
- **Class 注册到 ClassTable**(全局 Class 索引)
- **Loading 完成后立即 Link**(Verify + Prepare + Resolve)

### 2.3 Class 加载的缓存

**ART 维护 3 个 Class 缓存**:

| 缓存 | 位置 | 作用 |
|---|---|---|
| **ClassTable** | ClassLinker 全局 | 进程级 Class 索引(descriptor → Class*) |
| **ClassLoader.classTable** | 每个 ClassLoader | 该 ClassLoader 加载的所有 Class |
| **class() 方法** | 每个 java.lang.Class | 反射访问的入口 |

**缓存查找流程**:

```
loadClass(name):
    ↓
1. ClassLoader 缓存(classTable)
    └─ 命中 → 返回
    ↓ 未命中
2. 委托父 ClassLoader
    └─ 父的 classTable 命中 → 返回
    ↓ 未命中
3. findClass(name) 在自己 DEX 中找
    └─ 找到 → DefineClass(走 Link 流程)
    └─ 找不到 → 抛 ClassNotFoundException
```

**架构师必记**:**Class 加载是有状态的**。**第一次加载后缓存,后续直接返回**。**重复 loadClass 不会重复走 Link**。

---

## 3. Linking 阶段:Verify + Prepare + Resolve

### 3.1 Linking 是 3 步合一

**JVM 规范把 Verify / Prepare / Resolve 算作"Linking"阶段**。**ART 也是这样**。

```
Loading 完成后 → Linking 开始
    ↓
Verify(验证)
    ↓
Prepare(准备)
    ↓
Resolve(解析)   ← 可选,延迟到首次使用
    ↓
Initializing(初始化)
```

### 3.2 Verify 阶段详解

**Verify 是最复杂的阶段**——它要保证字节码不会让 JVM 崩溃。

**4 层验证**:

| 层级 | 内容 | 失败错误 |
|---|---|---|
| **1. 文件格式验证** | magic / version / 大小 | ClassFormatError |
| **2. 元数据验证** | 类继承 / 接口实现 / 访问标志 | IncompatibleClassChangeError |
| **3. 字节码验证** | 操作数栈 / 控制流 / 类型检查 | VerifyError |
| **4. 符号引用验证** | 引用是否存在 / 访问权限 | NoClassDefFoundError / IllegalAccessError |

**真实代码**(art/runtime/verifier/method_verifier.cc 简化):

```c
// ART Verify 流程
bool MethodVerifier::Verify() {
    // 1. 文件格式验证(在 Parse 时已完成)
    
    // 2. 元数据验证
    if (!VerifyMetadata()) return false;
    
    // 3. 字节码验证(核心)
    while (pc < code_size) {
        Instruction inst = DecodeInstruction(pc);
        // 3.1 检查操作数栈
        if (!CheckStack(inst)) return false;
        // 3.2 检查寄存器类型
        if (!CheckRegisters(inst)) return false;
        // 3.3 检查分支目标
        if (!CheckBranchTargets(inst)) return false;
        // 3.4 检查方法调用
        if (!CheckMethodInvocation(inst)) return false;
        pc += inst.GetSize();
    }
    
    // 4. 符号引用验证
    if (!VerifyReferences()) return false;
    
    return true;  // ✅ verify 通过
}
```

**Verify 失败常见原因**:

| 错误 | 根因 |
|---|---|
| `ClassFormatError` | DEX 文件损坏 |
| `IncompatibleClassChangeError` | 类继承关系错误 |
| `VerifyError` | 字节码非法(操作数栈不平衡 / 类型不匹配) |
| `NoClassDefFoundError` | 引用的类不存在 |

### 3.3 ART 14 的 verify 强化

**Android 14 的 ART 引入了"强 verify 模式"**:

| 模式 | 时机 | 速度 |
|---|---|---|
| **soft verify** | 启动时,后台线程 verify | 快 |
| **hard verify** | dex2oat 时,完整 verify | 慢 |
| **strict verify** | Android 14 引入,字节码 + 元数据严格校验 | 最慢 |

**Android 14 默认用 hard verify**(dex2oat 完整 verify,运行时 skip)。

**架构师必记**:**Android 14 的 hard verify 模式 + strict verify 是导致 "VerifyError" 增多的根因**。**老代码在新系统上 verify 失败**。

### 3.4 真实案例:VerifyError 的修复

**症状**(回到 §0.1):
```
java.lang.VerifyError: Rejecting class com.example.MyClass
```

**根因**:
1. 第三方库的字节码使用了"非法"操作数栈模式
2. Android 14 strict verify 检测到,拒绝
3. 启动崩溃

**修复**:
- **方案 A**:升级第三方库(修复字节码)
- **方案 B**:在 R8 配置里 -keep 但加 `-keepclasseswithmembernames` 保留类名(避免 R8 重写字节码)
- **方案 C**:在 AndroidManifest 里禁用 ART verify(不安全,仅 debug)
  ```xml
  <application
      android:vmSafeMode="true"
      ... />
  ```
- **方案 D**:用 `android:useEmbeddedDex` 让 ART 跳过 verify

**架构师必记**:**VerifyError 通常是"老代码在新系统上"问题**。**升级系统时,务必做兼容性测试**。

### 3.5 Prepare 阶段详解

**Prepare 阶段做 2 件事**:

1. **为类变量(static 字段)分配内存**
2. **设置默认值**(0 / false / null)

**重要规则**:
- **static final 常量**(基本类型 + String)在 Prepare 阶段设为编译期值
- **static 非 final 字段**在 Prepare 阶段设为默认值
- **static final 引用类型**(非 String)在 \<clinit\> 阶段初始化

**示例**:

```java
class MyClass {
    static int a = 42;           // Prepare: a = 0, \<clinit\>: a = 42
    static final int b = 100;    // Prepare: b = 100(编译期值)
    static final String c = "x"; // Prepare: c = "x"(编译期值)
    static final Object d = new Object();  // Prepare: d = null, \<clinit\>: d = new Object()
}
```

**架构师必记**:**Prepare 在 Linking 时跑(先于 Init),Init 在首次使用时跑**。

### 3.6 Resolve 阶段详解

**Resolve 把"符号引用"变成"直接引用"**。

| 阶段 | 引用类型 | 存储 |
|---|---|---|
| **编译期** | 符号引用(类名 + 方法名) | DEX 文件里 |
| **运行期** | 直接引用(地址 / 偏移) | 内存中 |

**Resolve 的 5 类引用**:

| 类型 | 含义 | ART 实现 |
|---|---|---|
| **类 / 接口** | 把类描述符解析为 Class* | ResolveClass() |
| **字段** | 解析 field_id 为 ArtField* | ResolveField() |
| **方法** | 解析 method_id 为 ArtMethod* | ResolveMethod() |
| **接口方法** | 同上,针对接口 | ResolveInterfaceMethod() |
| **方法类型** | MethodType 引用 | ResolveMethodType() |
| **方法句柄** | MethodHandle 引用 | ResolveMethodHandle() |

**Resolve 时机**:

- **预先解析(eager)**:类加载时立即解析所有引用
- **延迟解析(lazy)**:首次使用时才解析(Java 默认)

**架构师必记**:**Android ART 默认 lazy resolve**(首次使用才解析)。**这是为了减少类加载时间**。

**真实代码**(ART lazy resolve):

```c
// art/runtime/class_linker.cc
mirror::ArtMethod* ClassLinker::ResolveMethod(...) {
    // 1. 查缓存(本类的 resolved_methods_ 数组)
    if (method->IsResolved()) return method;
    
    // 2. 解析(真正查符号表)
    mirror::ArtMethod* resolved = DoResolveMethod(...);
    
    // 3. 缓存到 resolved_methods_
    method->SetResolved(resolved);
    return resolved;
}
```

**架构师视角**:**Lazy resolve 节省启动时间,但首次调用方法慢 1-10μs**(类似 JUMP_SLOT 的延迟绑定)。

---

## 4. Initializing 阶段:\<clinit\> 执行

### 4.1 \<clinit\> 是什么

**`<clinit>` 是类的"静态初始化器"**,由编译器自动生成。它包含:
- 静态变量的赋值语句
- static 块的代码

**示例**:

```java
class MyClass {
    static int a = 42;
    static int b;
    static {
        b = a * 2;
    }
    static int c = b + 1;
}
```

**编译后的字节码**:

```
MyClass.<clinit>:
    const/16 v0, 0x2a       # 42
    sput v0, MyClass.a       # a = 42
    sget v0, MyClass.a       # v0 = a = 42
    mul-int/lit8 v0, v0, 0x2 # v0 = 84
    sput v0, MyClass.b       # b = 84
    sget v0, MyClass.b       # v0 = b = 84
    add-int/lit8 v0, v0, 0x1 # v0 = 85
    sput v0, MyClass.c       # c = 85
    return-void
```

**关键事实**:
- **`<clinit>` 在类加载完成后,首次主动使用时执行**
- **`<clinit>` 是线程安全的**(JVM 保证只有一个线程执行)
- **`<clinit>` 抛异常会导致 `ExceptionInInitializerError`**

### 4.2 主动引用 vs 被动引用

**5 类主动引用**(**触发 `<clinit>`**):

| 引用类型 | 示例 |
|---|---|
| **new** | `new MyClass()` |
| **静态字段** | `MyClass.a`(读 / 写) |
| **静态方法** | `MyClass.foo()` |
| **反射** | `Class.forName("MyClass")` |
| **子类初始化** | 子类 `<clinit>` 触发父类 `<clinit>` |

**4 类被动引用**(**不触发 `<clinit>`**):

| 引用类型 | 示例 |
|---|---|
| **子类引用父类静态字段** | `MyClass.a`(通过子类) |
| **数组定义** | `MyClass[] arr = new MyClass[10]` |
| **final 静态常量** | `MyClass.B` (final int B = 100) |
| **类加载** | `ClassLoader.loadClass` 本身不触发 |

**架构师必记**:**final 静态常量在 Prepare 阶段就赋值,不触发 `<clinit>`**。**数组定义只触发 array class 的加载,不触发元素的 `<clinit>`**。

### 4.3 真实案例:\<clinit\> 死锁

**症状**:App 启动卡死,主线程在等子线程,子线程在等主线程。

**根因**:

```java
class MyClass {
    static Thread t = new Thread(() -> {
        // 1. 子线程启动
        // 2. 等待主线程的某些资源
        synchronized (Lock.class) {  // ← 死锁!
            // ...
        }
    });
    static {
        t.start();
        // 等待子线程完成
        try {
            t.join();
        } catch (InterruptedException e) {}
    }
}
```

**`MyClass` 的 `<clinit>` 启动子线程,子线程等待主线程的锁,主线程在等 `<clinit>` 完成 → 死锁**。

**架构师必记**:**`<clinit>` 里不能起线程、不能做阻塞操作、不能访问主线程资源**。**`static` 块只做"无副作用的初始化"**。

### 4.4 真实案例:ExceptionInInitializerError

**症状**:
```
java.lang.ExceptionInInitializerError
Caused by: java.lang.RuntimeException: failed
    at MyClass.<clinit>(MyClass.java:10)
```

**根因**:`<clinit>` 抛了异常。

**3 个常见根因**:

| 根因 | 触发条件 |
|---|---|
| **静态变量初始化抛异常** | `static int x = someMethod()` 中 someMethod 抛异常 |
| **static 块抛异常** | `static { foo(); }` 中 foo 抛异常 |
| **依赖未初始化** | 静态变量依赖另一个还没初始化的类 |

**架构师必记**:**`<clinit>` 只执行一次**,**失败后这个类永远不可用**。**修复需要重启进程**。

---

## 5. Using 阶段:类使用

### 5.1 Using 阶段

**Using 阶段是"正常使用类"**——创建对象、调用方法、访问字段。

**Using 阶段的性能要点**:

- **首次方法调用**:lazy resolve + 可能 JIT
- **JIT 编译**:热点方法被 JIT 编译为机器码
- **AOT 编译**:dex2oat 编译的机器码直接执行
- **GC**:Using 阶段会触发 GC(对象分配 / 回收)

**架构师必记**:**Using 阶段才是"用户能感知"的阶段**。**前面 4 阶段(Load/Link/Init)是"冷启动期"**。

### 5.2 类的引用计数

**ART 用引用计数判断类是否可达**:

| 引用 | 增加计数的位置 |
|---|---|
| **ClassLoader 持有** | ClassLoader.classTable 引用 |
| **对象实例** | 每个 instance 的 klass 字段引用 |
| **静态字段** | 静态字段如果持有对象 |
| **JNI 引用** | JNI 局部 / 全局引用 |
| **Stack** | 当前栈帧里的局部变量 |

**架构师必记**:**只要类有 1 个引用,就不会被卸载**。**通常 App 进程从启动到结束,所有类都不会被卸载**。

---

## 6. Unloading 阶段:类卸载

### 6.1 Unloading 触发条件

**JVM 规范的卸载条件**:
- **ClassLoader 不可达**
- **Class 自身不可达**

**Android 的实际情况**:
- **App 进程的 PathClassLoader 永远可达**(进程生命周期内)
- **所以 App 类基本不会被卸载**
- **Zygote 进程的 BootClassLoader 永远可达**
- **只有 system_server 等特殊进程可能触发类卸载**

**架构师必记**:**Android 上几乎看不到类卸载**。**这个阶段在 App 进程中基本不发生**。

### 6.2 类卸载的副作用

**类卸载要做 4 件事**:

1. **回收 Class 对象**(mirror::Class)
2. **回收 ArtMethod / ArtField 数组**
3. **回收静态变量值**
4. **清空各种缓存**(vtable / iftable / dex cache)

**危险点**:
- **类卸载 + 静态变量持有资源** → 资源泄漏
- **类卸载 + 还有实例存活** → 这些实例的 method 调用会抛 NoClassDefFoundError

**架构师必记**:**类卸载在 App 进程基本不会发生**。**但要避免"假设类被卸载"的设计**。

---

## 7. 类加载的启动期耗时

### 7.1 冷启动 1.5s 中,类加载贡献多少

| 阶段 | 耗时 | 占比 |
|---|---|---|
| linker64 启动 | 50-150ms | 3-10% |
| ART 启动 | 80-150ms | 5-10% |
| **类加载生命周期**(本篇) | **100-300ms** | **7-20%** |
| └─ Loading(dex 加载) | 30-100ms | 2-7% |
| └─ Verify | 20-100ms | 1-7% |
| └─ Prepare + Resolve | 10-30ms | 1-2% |
| └─ Init(`<clinit>`) | 30-100ms | 2-7% |
| Resources 加载 | 100-200ms | 7-13% |
| Application onCreate | 300-500ms | 20-33% |
| 第一帧渲染 | 200-400ms | 13-27% |

**类加载生命周期占 7-20%**——是冷启动的重要瓶颈。

### 7.2 4 个优化技巧

| 技巧 | 节省时间 | 难度 |
|---|---|---|
| **AOT 预编译** | 跳过 verify 30-100ms | 中 |
| **减少 static 块** | 减少 Init 时间 20-50ms | 中 |
| **懒加载非关键类** | 减少 Loading 时间 30-80ms | 中 |
| **R8 优化** | 减少总类数 30-50% | 低 |

### 7.3 真实案例:启动期类加载监控

**用 art-trace 监控类加载**:

```bash
# 开启 ART trace
$ adb shell setprop dalvik.vm.dex2oat-flags --watch-dog
$ adb shell setprop debug.alloc-count-max 10000

# 重启 App,触发完整类加载
$ adb shell am start -W -n com.example.app/.MainActivity

# 看 logcat 中的类加载信息
$ adb logcat -d | grep -E "Loaded class|ClassLinker" | head -50
```

**用 simpleperf 找 verify 热点**:

```bash
$ adb shell simpleperf record -e cpu-cycles -p PID -o /data/local/tmp/perf.data
# 等启动完成
$ adb shell simpleperf report -i /data/local/tmp/perf.data --show-callchain
# 找 ClassLinker::VerifyClass 函数的调用栈
```

**架构师必记**:**类加载的热点方法** = `ClassLinker::DefineClass` + `MethodVerifier::Verify`。

---

## 8. 真实案例:类加载失败的全套诊断

### 8.1 5 类失败模式

| 失败 | 触发条件 | 错误 |
|---|---|---|
| **ClassNotFoundException** | 找不到类 | ClassLoader.findClass 返回 null |
| **NoClassDefFoundError** | 类存在但链接失败 | Verify / Prepare / Resolve 失败 |
| **VerifyError** | 字节码验证失败 | MethodVerifier 拒绝 |
| **IncompatibleClassChangeError** | 类继承关系变化 | 父类 / 接口变化 |
| **ExceptionInInitializerError** | `<clinit>` 失败 | 静态初始化抛异常 |

### 8.2 真实案例:ClassNotFoundException

**症状**(回到 §7 PLE 07 §0.1):
```
java.lang.ClassNotFoundException: Didn't find class "com.thirdparty.SDKManager"
```

**诊断**:
```bash
# 1. 看 APK 是否包含
$ baksmali disassemble app.apk -o smali/
$ find smali/ -name "SDKManager.smali"
# 空 → R8 strip 了

# 2. 看 R8 配置
$ cat proguard-rules.pro
# 确认 -keep class com.thirdparty.** { *; }
```

**修复**:
```proguard
-keep class com.thirdparty.** { *; }
-keep class com.thirdparty.**$* { *; }
```

### 8.3 真实案例:VerifyError(回到 §0.1)

**症状**:
```
java.lang.VerifyError: Rejecting class com.example.MyClass
```

**诊断**:
```bash
# 1. 看 ART verify 日志
$ adb logcat -d | grep -i "verify" | head -30

# 2. 看 smali 看是否异常
$ baksmali disassemble app.apk -o smali/
$ cat smali/com/example/MyClass.smali | head -50
# 寻找异常的操作数栈模式

# 3. 看是不是第三方库
$ cat mapping.txt | grep "MyClass"
# 如果是 com.thirdparty 库,确认是不是已知问题
```

**修复**:
```proguard
# 在 R8 配置里加
-keep class com.thirdparty.** { *; }
-keep,allowobfuscation class com.example.** { *; }

# 或关闭 verify(strict verify 模式)
# AndroidManifest.xml:
<application
    android:vmSafeMode="true"
    ... />
```

### 8.4 真实案例:NoClassDefFoundError

**症状**:
```
java.lang.NoClassDefFoundError: com.example.MyClass
    at MyClass.<clinit>(MyClass.java:10)
```

**根因**:`<clinit>` 失败,导致 MyClass 永远不可用。

**诊断**:
```bash
# 看 ART 日志
$ adb logcat -d | grep -i "class.*def\|<clinit>\|ExceptionInInitializer"
```

**修复**:
- 修复 `<clinit>` 中的失败逻辑
- 重启进程(因 `<clinit>` 只执行一次,失败后永远不可用)

### 8.5 真实案例:ClassCircularityError

**症状**:
```
java.lang.ClassCircularityError: com/example/A
```

**根因**:A 依赖 B,B 依赖 A(类继承循环)。

**架构师必记**:**类继承不能有循环**。**A extends B, B extends A** → ClassCircularityError。

---

## 9. 架构师视角:类生命周期的 5 个核心洞察

### 9.1 洞察 1:7 阶段 = 4 步加载 + 3 步使用

**Loading + Linking + Initializing = 加载期**(启动期)
**Using + Unloading = 使用期**(运行时)

**启动期耗时占比 7-20%**——值得优化。

### 9.2 洞察 2:Verify 是最大瓶颈

**Verify 耗时占类加载生命周期的 30-50%**。**AOT 预编译可以跳过运行期 verify,节省 30-100ms**。

### 9.3 洞察 3:\<clinit\> 只执行一次,失败 = 进程死

**`<clinit>` 的"只能成功,不能失败"特性是设计哲学**。**它保证类状态的一致性,但也意味着任何失败都是不可恢复的**。

**架构师必记**:**`<clinit>` 里只做"无副作用的初始化"**。

### 9.4 洞察 4:Android 上几乎看不到类卸载

**App 进程从启动到结束,所有类都不会卸载**。**这意味着"类内存"是稳态的**。**优化重点是减少启动期类加载,而不是卸载**。

### 9.5 洞察 5:从类加载失败直接映射到故障现象

| 故障现象 | 类加载阶段根因 |
|---|---|
| `ClassNotFoundException` | Loading(findClass 失败) |
| `VerifyError` | Linking(Verify 失败) |
| `NoClassDefFoundError` | Linking(Resolve 失败) |
| `IncompatibleClassChangeError` | Linking(元数据验证失败) |
| `ExceptionInInitializerError` | Initializing(`<clinit>` 失败) |
| 启动慢 100ms+ | 多阶段叠加 |

---

## 10. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **7 阶段 = 4 步加载 + 3 步使用** | Loading/Verify/Prepare/Resolve + Init + Using + Unloading |
| 2 | **Verify 是最大瓶颈** | 占类加载 30-50%,AOT 可跳过 |
| 3 | **\<clinit\> 只执行一次** | 失败 = 进程死 |
| 4 | **Android 上几乎无类卸载** | 优化重点在启动期类加载 |
| 5 | **5 类失败 = 5 阶段根因** | 异常 → 阶段 → 修复 |

---

## 11. PLE 第三篇章(06-08)完结

**DEX 与 ART 前 3 篇完成,差 09 AOT/JIT 收尾**:

| 篇号 | 标题 | 大小 |
|---|---|---|
| 06 | DEX/ODEX/VDEX 格式 | 42KB |
| 07 | ART ClassLoader 体系 | 30KB |
| 08 | 类加载生命周期 | 本篇 |

---

## 12. 下一篇预告

09 篇《AOT / JIT 编译流水线:dex2oat 与 ART 运行时编译》是 PLE 第三篇章(DEX 与 ART)的收尾,会沿着本篇埋下的线索,深入讲:

- 为什么需要 AOT:启动速度 vs 运行速度的权衡
- dex2oat 输入输出:DEX → ODEX/VDEX
- ART 编译模式:AOT / JIT / Interpreted 三态切换
- Profile Guided Compilation:cloud profile + on-device profile
- JIT code cache:CodeInfo / JIT 编译的内存占用
- OAT 文件格式:VDEX + OAT 两段式
- 真实案例:用 oatdump 拆解 boot.oat
- 架构师视角:AOT/JIT 的工程取舍

**09 篇预计 2 周后产出**,届时一起发你看。

---

## 附录 A:7 阶段速查

| 阶段 | 触发条件 | 关键动作 | 失败异常 |
|---|---|---|---|
| Loading | loadClass | 读字节流 + 创建 Class 对象 | ClassFormatError |
| Verify | 加载后 | 字节码验证 | VerifyError |
| Prepare | Verify 后 | 静态变量默认值 | OutOfMemoryError |
| Resolve | 首次引用 | 符号引用 → 直接引用 | NoSuchFieldError / NoSuchMethodError |
| Initializing | 主动引用 | `<clinit>` 执行 | ExceptionInInitializerError |
| Using | 正常 | 使用 | - |
| Unloading | GC + 不可达 | 释放 | (基本不发生) |

## 附录 B:5 类主动引用

| 引用类型 | 示例 | 触发 `<clinit>` |
|---|---|---|
| new | `new MyClass()` | ✅ |
| 静态字段 | `MyClass.a` | ✅ |
| 静态方法 | `MyClass.foo()` | ✅ |
| 反射 | `Class.forName("MyClass")` | ✅ |
| 子类初始化 | 子类 `<clinit>` | ✅(父类先) |

## 附录 C:4 类被动引用

| 引用类型 | 示例 | 触发 `<clinit>` |
|---|---|---|
| 子类引用父类静态字段 | `SubClass.SUPER_FIELD` | ❌(只触发父类) |
| 数组定义 | `new MyClass[10]` | ❌(只触发 array class) |
| final 静态常量 | `MyClass.B`(final int) | ❌(Prepare 已赋值) |
| ClassLoader.loadClass | `classLoader.loadClass(name)` | ❌(只 Load,不 Init) |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 09 AOT/JIT | AOT 预编译 = dex2oat 时完成 Verify |
| 12 进程启动 | Zygote fork 时,类加载状态被继承 |
| 14 风险地图 | §8 失败诊断的"5 类根因"是 P14 速查表的核心 |

---

> **本篇把类加载拆解到"7 阶段 + 5 类失败 + 5 类主动引用 + 4 类被动引用"5 个维度。**
> **09 篇会在这个基础上,讲 AOT/JIT——类加载完成后,字节码怎么变成可执行的机器码。**
> **记住 7 阶段、Verify 强化、`<clinit>` 一次性、Android 无卸载,你的类加载视角就立住了。**

