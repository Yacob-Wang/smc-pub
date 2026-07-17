# 07-ART ClassLoader 体系:从 BootClassLoader 到 PathClassLoader

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15`(ClassLoader 通过 `open() + mmap()` 读 DEX,内核版本影响 VMA 行为)+ `libcore/ojluni/src/main/java/java/lang/ClassLoader.java` + `art/runtime/native/java_lang_ClassLoader.cc` + `art/runtime/class_linker.cc`
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) → [06-DEX/ODEX/VDEX 格式](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md)
> **下一篇**:[08-类加载生命周期:Loading → Linking → Initializing](08-类加载生命周期-Loading-Linking-Initializing.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 6 篇(Java 侧 · ClassLoader 树层)
- **强依赖**:**[PLE-01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-06 DEX](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md)**
- **承接自**:PLE-06 已讲 DEX 文件结构与 mmap;本篇是骨架上"链接"动作在 Java 侧的具体载体(怎么用 ClassLoader 找类)
- **衔接去**:下一篇 [PLE-08 类加载生命周期](08-类加载生命周期-Loading-Linking-Initializing.md) 讲"ClassLoader 找到类后的 7 阶段(Verify/Prepare/Resolve/Init)"
- **不重复内容**:
  - **DEX 文件格式** → 详见 [PLE-06](06-DEX-ODEX-VDEX格式-为mmap而生的字节码.md)
  - **Verify / Prepare / Resolve / `<clinit>` 7 阶段** → 详见 [PLE-08](08-类加载生命周期-Loading-Linking-Initializing.md)
  - **AOT/JIT 编译** → 详见 [PLE-09](09-AOT-JIT编译流水线-dex2oat与ART运行时编译.md)
  - **R8 / ProGuard 配置** → 不在本系列(详见 [App/Hprof 系列](../../App/Hprof_Analysis/README.md))

## 0. 写在前面:为什么 ClassLoader 单独成篇

### 0.1 一个真实的崩溃现场

**场景**:某 App 用某个第三方 SDK,启动时崩溃:

```
E AndroidRuntime: FATAL EXCEPTION: main
E AndroidRuntime: java.lang.ClassNotFoundException: Didn't find class "com.thirdparty.SDKManager" on path: DexPathList[[zip file "/data/app/~~xyz/base.apk"],nativeLibraryDirectories=[/data/app/~~xyz/lib/arm64, /system/lib64]]
E AndroidRuntime:        at java.lang.BootClassLoader.findClass(ClassLoader.java:...)
E AndroidRuntime:        at java.lang.BaseDexClassLoader.findClass(...)
E AndroidRuntime:        at java.lang.PathClassLoader.findClass(...)
```

**症状**:`ClassNotFoundException`,系统找不到 `com.thirdparty.SDKManager` 类。

**根因排查**:
1. 该 App 用了 R8/ProGuard,配置错误把 `SDKManager` 类给 strip 掉了
2. R8 配置里没有保留第三方 SDK 的类
3. APK 安装时,DEX 里没有 `SDKManager` 类
4. 启动时 ClassLoader 在所有 DEX 中找不到这个类 → ClassNotFoundException

**这个案例的修复需要 4 个知识**:
1. 知道 ClassLoader 树是怎么组织的
2. 知道 Class 查找的 5 步路径
3. 知道 BootClassLoader 和 PathClassLoader 的边界
4. 知道 R8/ProGuard 是怎么影响 ClassLoader 可见性的

**这就是本篇要讲清楚的事**。

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Samsung Galaxy S22(SM-S901,arm64-v8a)
> - Android 版本:OneUI 5.1(基于 `android-13.0.0_r41`,部分 OEM 定制)
> - App:某三方推送 SDK 的集成宿主 App v4.5.0,启用 R8 minify
> - 工具:`baksmali` + `apkanalyzer` + `R8 mapping.txt`

> **复现步骤**:
> 1. 该 App 在集成 SDK 后启用 R8 minify,但 proguard-rules.pro **没有添加** SDK 类的 keep 规则
> 2. 直接打 release 包安装
> 3. 启动 App,看到 splash 后立即闪退,概率 100%
> 4. 闪退信息: `ClassNotFoundException: com.thirdparty.SDKManager`

> **logcat 关键片段**:
> ```
> E AndroidRuntime: FATAL EXCEPTION: main
> E AndroidRuntime: java.lang.ClassNotFoundException: Didn't find class "com.thirdparty.SDKManager" on path: DexPathList[
>     [zip file "/data/app/~~xyz/base.apk"],
>     nativeLibraryDirectories=[/data/app/~~xyz/lib/arm64, /system/lib64]]
> E AndroidRuntime:        at java.lang.BootClassLoader.findClass(ClassLoader.java:...)
> E AndroidRuntime:        at java.lang.BaseDexClassLoader.findClass(...)
> E AndroidRuntime:        at java.lang.PathClassLoader.findClass(...)
> E AndroidRuntime:        at com.example.app.App.onCreate(App.java:42)
> ```

> **根因诊断命令**:
> ```bash
> # Step 1:看 APK 里有没有这个类
> $ apkanalyzer dex packages app-release.apk | grep "com.thirdparty.SDKManager"
> # (空 —— R8 把 SDKManager strip 了)
> # Step 2:看 R8 mapping.txt 确认 strip
> $ grep "SDKManager" mapping.txt
> # (空)
> # Step 3:用 baksmali 拆 release APK,确认真的没有
> $ baksmali disassemble app-release.apk -o smali/
> $ find smali/ -name "SDKManager.smali"
> # (空)
> # Step 4:对比未 minify 的 debug 包,确认 SDKManager 是 SDK 里的
> $ apkanalyzer dex packages app-debug.apk | grep "com.thirdparty.SDKManager"
> C com.thirdparty.SDKManager
> ```

> **修复 commit-style diff**:
> ```diff
> - # proguard-rules.pro 旧(没有 keep 规则)
> + # proguard-rules.pro 新
> + -keep class com.thirdparty.** { *; }
> + -keep class com.thirdparty.**$* { *; }
> + # 或者用 @Keep 注解
> + # @Keep public class SDKManager { ... }
> ```
> **修复后**:R8 不再 strip SDKManager,启动期 ClassLoader 找到该类,闪退消失。**额外收益**:R8 误 strip 还会导致 JNI 绑定失败(`UnsatisfiedLinkError`)、`<clinit>` 死锁等,见 [PLE-14](14-加载失败与启动期故障速查.md)。

> **架构师视角**:ClassLoader 是 **"Java 侧加载的统一入口"** —— 它屏蔽了 BootClassLoader / PathClassLoader / DexClassLoader 的差异。**架构师要在 R8 配置时把所有"运行时通过反射 / JNI / Class.forName 加载的类"显式 keep**,否则就是定时炸弹。

### 0.2 ClassLoader 在 PLE 8 阶段中的位置

```
阶段 0-1:execve + linker64                ← PLE 02-05
    ↓
阶段 2:JNI_OnLoad 启动 ART                ← PLE 05
    ↓
阶段 3:Zygote fork                        ← PLE 12
    ↓
阶段 4:ActivityThread.main()
    ↓
阶段 5:ClassLoader 加载应用 DEX            ← 本篇 + PLE 08
├─ 创建 PathClassLoader
├─ 加载 base.apk(整文件 mmap)
├─ 解析 DEX 头(本系列 P06)
├─ 创建 ArtMethod 表
└─ Class 查找 + Verify + Initialize
    ↓
阶段 6:Resources 加载
    ↓
阶段 7:第一行 Java 代码执行
```

**ClassLoader 是 PLE 阶段 5 的核心**——它决定类在哪里、怎么被找到、谁能看到。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 解释 Java ClassLoader 的 parent delegation 模型
2. 描述 Android 的 5 种 ClassLoader 各自的职责
3. 解释 PathClassLoader 的构造流程
4. 描述 Class 查找的 5 步路径
5. 诊断 `ClassNotFoundException` / `NoClassDefFoundError` 的根因

---

## 1. Java ClassLoader 模型

### 1.1 三个核心概念

**Java 的 ClassLoader 模型有三个核心概念**:

| 概念 | 含义 |
|---|---|
| **委托模型(Delegation Model)** | 父 ClassLoader 优先,自己找不到才让子 ClassLoader 找 |
| **可见性(Visibility)** | 子 ClassLoader 可以看到父 ClassLoader 加载的类,反之不行 |
| **唯一性(Uniqueness)** | 同一个类不会被多个 ClassLoader 加载(保证类一致性) |

### 1.2 委托模型(Parent Delegation)

**Java ClassLoader 加载类时,先委托父 ClassLoader,父找不到再自己找**:

```
loadClass(name) 调用:
1. 检查类是否已加载
   └─ 命中 → 返回
2. delegate to parent.loadClass(name)
   └─ 父 ClassLoader 找不到 → 继续
3. findClass(name) (本 ClassLoader 自己的查找逻辑)
   └─ 找到 → 返回
4. 抛 ClassNotFoundException
```

**为什么需要委托模型**:

| 收益 | 说明 |
|---|---|
| **避免重复加载** | 同一个类不会被多个 ClassLoader 加载 |
| **安全性** | 核心类(java.lang.*)由 Bootstrap 加载,不可被替换 |
| **一致性** | `instanceof` 比较时,同一个类一定来自同一个 ClassLoader |

### 1.3 可见性

**可见性规则**:
- **子 ClassLoader 可以看到父 ClassLoader 加载的类**
- **父 ClassLoader 看不到子 ClassLoader 加载的类**

**示例**:

```
Application ClassLoader (PathClassLoader)
  └─ 可见: java.lang.String (父加载) + com.example.MyClass (自己加载)

Bootstrap ClassLoader
  └─ 可见: java.lang.String (自己加载)
  └─ 不可见: com.example.MyClass (子加载)
```

**架构师必记**:**Java 核心类(java.lang.*)只能由 Bootstrap ClassLoader 加载**。**App 不能用自己的 ClassLoader 替换 java.lang.String**(否则安全漏洞)。

### 1.4 唯一性

**唯一性规则**:**同一个类只被加载一次**(由第一个加载它的 ClassLoader 完成)。

**判断"同一个类"的标准**:
- 类名完全相同
- 包名完全相同
- **ClassLoader 是同一个**(相同实例)

**架构师视角**:**如果两个 ClassLoader 都加载了 `com.example.Foo`,它们是两个不同的类**。**`Foo.class != Foo.class` 跨 ClassLoader**——`instanceof` 会返回 false。

### 1.5 Java 的 3 种内置 ClassLoader

| ClassLoader | 加载内容 | 实现者 |
|---|---|---|
| **Bootstrap ClassLoader** | JDK 核心类(rt.jar 等) | C++ 实现(Java 看不到) |
| **Extension ClassLoader** | 扩展类 | Java 实现 |
| **Application ClassLoader** | classpath 上的类 | Java 实现 |

**Java 9+ 用 Platform ClassLoader 替代 Extension ClassLoader**。

---

## 2. Android 的 ClassLoader 体系

### 2.1 Android 的 5 种 ClassLoader

**Android 在标准 Java ClassLoader 之上,扩展出 5 种 ClassLoader**:

| ClassLoader | 加载内容 | 父 ClassLoader | 创建时机 |
|---|---|---|---|
| **BootClassLoader** | framework 核心类 | null(顶级) | ART 启动时 |
| **PathClassLoader** | App APK 中的类 | BootClassLoader | 每个 App 进程启动 |
| **DexClassLoader** | 任意 .jar / .apk / .dex | PathClassLoader | 插件化 / 热修复 |
| **InMemoryDexClassLoader** | 内存中的 DEX 字节码 | PathClassLoader | 动态加载 |
| **SystemClassLoader** | framework 中需要被 App 看到的类 | BootClassLoader | system_server 进程 |

**注意**:**Android 没有 Bootstrap ClassLoader 的 C++ 实现,而是用 Java 实现的 BootClassLoader**(在 libcore/ojluni 里)。

### 2.2 ClassLoader 树形结构

```
┌────────────────────────────────────────────────────────┐
│ BootClassLoader(Java 实现)                              │
│  ├─ 加载 framework.jar / core-oj.jar / core-libart.jar │
│  └─ 加载 /system/framework/ 下的所有 jar                │
└─────────────────┬──────────────────────────────────────┘
                  │ 父
                  ↓
┌────────────────────────────────────────────────────────┐
│ PathClassLoader(每个 App 进程一个)                      │
│  ├─ 加载 /data/app/~~xxx/base.apk                      │
│  └─ 加载 /data/app/~~xxx/base.apk 中的 classes.dex      │
└─────────────────┬──────────────────────────────────────┘
                  │ 父
                  ↓
┌────────────────────────────────────────────────────────┐
│ DexClassLoader(可选,用于插件化)                         │
│  └─ 加载 /data/data/.../plugin.apk                     │
└────────────────────────────────────────────────────────┘
```

**关键事实**:
- **每个 App 进程有独立的 PathClassLoader 实例**
- **PathClassLoader 共享 BootClassLoader**(framework 类)
- **DexClassLoader 是 PathClassLoader 的子**(可选)

### 2.3 5 种 ClassLoader 详解

**1. BootClassLoader**

```java
// libcore/ojluni/src/main/java/java/lang/BootClassLoader.java
class BootClassLoader extends ClassLoader {
    // 1. 加载 framework 的 jar
    // 2. 加载 core-oj.jar / core-libart.jar 等
    
    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        return VMClassLoader.findClass(name);  // native 调用
    }
}
```

**职责**:
- 加载所有 framework 类
- 加载 java.* / javax.* / android.* 等系统类
- 加载 core-oj.jar(core OpenJDK)
- 加载 core-libart.jar(ART 核心)

**2. PathClassLoader**

```java
// libcore/ojluni/src/main/java/java/lang/PathClassLoader.java
public class PathClassLoader extends BaseDexClassLoader {
    public PathClassLoader(String dexPath, String librarySearchPath, ClassLoader parent) {
        super(dexPath, librarySearchPath, parent);
    }
}
```

**职责**:
- 加载 App 的 base.apk
- 加载 multidex 的 classes2.dex / classes3.dex 等

**3. DexClassLoader**

```java
// libcore/ojluni/src/main/java/java/lang/DexClassLoader.java
public class DexClassLoader extends BaseDexClassLoader {
    public DexClassLoader(String dexPath, String optimizedDirectory, 
                          String librarySearchPath, ClassLoader parent) {
        super(dexPath, librarySearchPath, parent);
    }
}
```

**职责**:
- 加载任意路径的 .dex / .jar / .apk
- 历史上需要 optimizedDirectory 参数,Android 8+ 已弃用
- 用于插件化(把插件 APK 当外部 DEX 加载)

**4. InMemoryDexClassLoader**

```java
// libcore/ojluni/src/main/java/java/lang/InMemoryDexClassLoader.java
public class InMemoryDexClassLoader extends BaseDexClassLoader {
    public InMemoryDexClassLoader(ByteBuffer buffer, ClassLoader parent) {
        // 直接用 ByteBuffer 里的 DEX 字节,不需要文件
    }
}
```

**职责**:
- 直接从内存里的 ByteBuffer 加载 DEX
- 用于动态下载的 DEX(网络下载后直接在内存加载)
- Android 8+ 引入

**5. SystemClassLoader**

```java
// 用于 system_server 进程
// 和 App 进程的 ClassLoader 树不同
```

**职责**:
- system_server 进程用,加载 system_server 自己的类
- 不是 App 进程关注的对象

### 2.4 真实案例:看一个 App 进程的 ClassLoader 树

```bash
# 用 debugger 看 ClassLoader 树
$ adb shell am start -n com.example.app/.MainActivity
# 启动后,在 debugger 里:
> Thread.currentThread().getContextClassLoader()
# 返回:dalvik.system.PathClassLoader[...] 

> ((PathClassLoader)Thread.currentThread().getContextClassLoader()).getParent()
# 返回:java.lang.BootClassLoader@...

> ((BootClassLoader)((PathClassLoader)...).getParent()).getParent()
# 返回:null(顶级)
```

**架构师视角**:**App 进程只有 2 层 ClassLoader**——PathClassLoader(自己) + BootClassLoader(framework)。**DexClassLoader 是可选的**。

---

## 3. PathClassLoader 构造流程

### 3.1 构造时机

**PathClassLoader 在 LoadedApk 创建时构造**:

```java
// frameworks/base/core/java/android/app/LoadedApk.java
public ClassLoader getClassLoader() {
    if (mClassLoader == null) {
        // 1. 创建 PathClassLoader
        mClassLoader = new PathClassLoader(
            mSourceDir,                    // /data/app/~~xxx/base.apk
            mLibrarySearchPath,            // /data/app/~~xxx/lib/arm64
            mParent);                      // BootClassLoader
    }
    return mClassLoader;
}
```

**关键参数**:
- `mSourceDir`:`/data/app/~~xxx/base.apk`(APK 路径)
- `mLibrarySearchPath`:`/data/app/~~xxx/lib/arm64`(原生库路径)
- `mParent`:`BootClassLoader`(父)

### 3.2 BaseDexClassLoader 构造流程

**PathClassLoader 继承 BaseDexClassLoader,实际构造在父类**:

```java
// libcore/ojluni/src/main/java/java/lang/BaseDexClassLoader.java
public BaseDexClassLoader(String dexPath, String librarySearchPath, ClassLoader parent) {
    super(parent);
    // 1. 创建 DexPathList
    this.pathList = new DexPathList(this, dexPath, librarySearchPath);
}
```

**DexPathList 构造**:

```java
// libcore/ojluni/src/main/java/java/lang/DexPathList.java
public DexPathList(ClassLoader definingContext, String dexPath, String librarySearchPath) {
    // 1. 解析 dexPath(分号分隔的多个路径)
    // 2. 对每个路径调用 loadDexFile
    // 3. 把 DexFile 包装成 Element
    // 4. 添加到 dexElements 数组
    
    for (String path : dexPath.split(":")) {
        // 2. mmap DEX 文件
        DexFile dex = loadDexFile(path, ...);
        // 3. 包装成 Element
        dexElements.add(new Element(dex));
    }
}
```

**Element 数据结构**:

```java
static class Element {
    private final DexFile dexFile;  // mmap 后的 DEX
    private final File dir;          // 父目录(用于 native lib)
    // ...
}
```

**架构师必记**:**PathClassLoader 内部维护一个 dexElements 数组**,每个元素对应一个 DEX 文件。**Class 查找就是遍历这个数组**。

### 3.3 真实代码:构造完整的 ClassLoader 树

```java
// ActivityThread.java(简化)
private void createAppContext(LoadedApk packageInfo) {
    // 1. 拿到 LoadedApk
    ContextImpl context = new ContextImpl();
    
    // 2. 触发 ClassLoader 创建
    ClassLoader classLoader = packageInfo.getClassLoader();
    //    └─ new PathClassLoader(apkPath, libPath, BootClassLoader)
    
    // 3. 用 ClassLoader 创建 Application
    Application app = packageInfo.makeApplication(false, mInstrumentation);
    
    // 4. Application.attachBaseContext
    app.attachBaseContext(context);
    //    └─ 这里 context 已经绑定了 ClassLoader
}
```

**关键事实**:**ClassLoader 是在 LoadedApk 创建时构造的,而不是在 Application 创建时**。**构造发生在 process startup 的早期**。

### 3.4 真实案例:debugger 看 ClassLoader 内容

```bash
# 在 debugger 里:
> ((PathClassLoader)Thread.currentThread().getContextClassLoader()).toString()
# 输出:dalvik.system.PathClassLoader[
#         DexPathList[
#           [zip file "/data/app/~~xyz/base.apk"],
#           nativeLibraryDirectories=[
#             /data/app/~~xyz/lib/arm64,
#             /system/lib64
#           ]
#         ]
#       ]
```

**解读**:
- 加载 1 个 APK:base.apk
- 加载 2 个 native lib 目录:App lib + System lib
- 这是个**典型配置**——简单 App 不会用 DexClassLoader

---

## 4. Class 查找的 5 步路径

### 4.1 完整查找流程

**当 App 调用 `Class.forName("com.example.Foo")` 或 `ClassLoader.loadClass("com.example.Foo")` 时**:

```
1. 查缓存(本 ClassLoader 的已加载类集合)
   └─ 命中 → 返回 Class 对象
   ↓ 未命中
2. 委托父 ClassLoader(BootClassLoader)
   └─ 命中 → 返回 Class 对象
   ↓ 未命中
3. 遍历 DexPathList 的 dexElements
   └─ 对每个 Element 的 DexFile 查类
       └─ 命中 → 加载类 + 返回
   ↓ 未命中
4. 抛 ClassNotFoundException
```

### 4.2 委托模型的实现

```java
// java.lang.ClassLoader.loadClass(简化)
protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
    // 1. 查本 ClassLoader 的已加载类
    Class<?> c = findLoadedClass(name);
    if (c == null) {
        try {
            // 2. 委托父 ClassLoader
            if (parent != null) {
                c = parent.loadClass(name, false);
            } else {
                // 父是 null(顶级 ClassLoader),找 Bootstrap
                c = findBootstrapClassOrNull(name);
            }
        } catch (ClassNotFoundException e) {
            // 父 ClassLoader 找不到,继续
        }
        if (c == null) {
            // 3. 自己找(findClass)
            c = findClass(name);
        }
    }
    return c;
}
```

**关键事实**:
- **父 ClassLoader 优先**(委托模型)
- **找不到才自己找**(本 ClassLoader 的 DEX)
- **缓存优先**(已加载的类直接返回)

### 4.3 真实案例:Class 查找的完整路径

**查找 `android.app.Activity`**:

```
调用:PathClassLoader.loadClass("android.app.Activity")
    ↓
1. PathClassLoader 的已加载类 → 没找到
    ↓
2. 委托 BootClassLoader
    └─ BootClassLoader.findClass("android.app.Activity")
    └─ 在 framework.jar 中找到
    └─ 返回 Activity.class ✅
```

**查找 `com.example.app.MainActivity`**:

```
调用:PathClassLoader.loadClass("com.example.app.MainActivity")
    ↓
1. PathClassLoader 的已加载类 → 没找到
    ↓
2. 委托 BootClassLoader
    └─ BootClassLoader.findClass("com.example.app.MainActivity")
    └─ 找不到(com.example.app 是 App 自己的)
    ↓ 抛 ClassNotFoundException
3. PathClassLoader 自己的 findClass
    └─ 在 base.apk 的 classes.dex 中找到
    └─ 返回 MainActivity.class ✅
```

**查找 `java.lang.String`**:

```
调用:PathClassLoader.loadClass("java.lang.String")
    ↓
1. PathClassLoader 的已加载类 → 可能已加载
    ↓ 没加载
2. 委托 BootClassLoader
    └─ BootClassLoader.findClass("java.lang.String")
    └─ 在 core-oj.jar 中找到
    └─ 返回 String.class ✅
```

### 4.4 真实案例:类找不到的诊断

**回到 §0.1 案例**:`com.thirdparty.SDKManager` 找不到。

**诊断步骤**:

```bash
# Step 1: 确认 APK 是否包含这个类
$ baksmali disassemble app.apk -o smali/
$ ls smali/com/thirdparty/
# 空 → 类不在 APK 里
# 或 grep -r "SDKManager" smali/

# Step 2: 看 R8/ProGuard 配置
$ cat proguard-rules.pro
# 确认没有 -keep class com.thirdparty.** { *; }

# Step 3: 重新编译 + 不 strip 第三方类
$ cat proguard-rules.pro
-keep class com.thirdparty.** { *; }
-keep class com.example.** { *; }
```

**架构师必记**:**R8/ProGuard 默认会 strip 没用到的类**。**第三方 SDK 必须显式 -keep**。

---

## 5. Class 加载的可见性边界

### 5.1 4 个"看不到"的场景

**架构师必须清楚,什么时候"看不到"**:

| 场景 | "看不到"的原因 |
|---|---|
| **父看不到子** | ClassLoader 委托模型:子先看自己的 |
| **同 ClassLoader 看不到** | 唯一性:同一个类只加载一次 |
| **Plugin ClassLoader 看不到 App 类** | 反向委托不成立 |
| **App ClassLoader 看不到 Plugin 类** | App 没委托到 Plugin |

**关键事实**:**ClassLoader 是单向委托**——父看不到子。

### 5.2 真实场景:插件化如何让 App 看到 Plugin 类

**插件化的难题**:
- Plugin 用 DexClassLoader 加载
- Plugin 的类不在 App 的 PathClassLoader 里
- App 引用 Plugin 的类时,ClassLoader 树找不到

**3 个常见解法**:

| 解法 | 原理 | 缺点 |
|---|---|---|
| **预先注册** | App 启动时主动 loadClass("com.plugin.Foo") | 启动慢,需遍历所有 Plugin |
| **Hook ClassLoader** | 修改 PathClassLoader 的 dexElements | 不安全,易被 R8 检测 |
| **重写 loadClass** | 自定义 ClassLoader,先查 Plugin 再查 App | 复杂度高 |

**真实案例**(以 Tinker / Robust 等热修复为例):

```java
// 简化版 Plugin ClassLoader
public class PluginClassLoader extends DexClassLoader {
    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        // 1. 先在 Plugin 自己的 DEX 里找
        Class<?> c = super.findClass(name);
        if (c != null) return c;
        // 2. 找不到,委托父(可能能找到)
        return getParent().loadClass(name);
    }
}
```

**架构师必记**:**插件化 / 热修复的核心 = 自定义 ClassLoader,反向委托**。**复杂度高,要小心使用**。

### 5.3 真实场景:App 之间的隔离

**两个 App 进程**:

```
App A 进程:
  PathClassLoader_A
    ├─ /data/app/~~A/base.apk
    └─ 父:BootClassLoader(共享)

App B 进程:
  PathClassLoader_B
    ├─ /data/app/~~B/base.apk
    └─ 父:BootClassLoader(共享)
```

**问题**:App A 能不能看到 App B 的类?

**答案**:**不能**(即使两个 App 用了相同的库,它们的 ClassLoader 实例不同)。

**这保证了**:
- App A 不能访问 App B 的私有数据(没有可见路径)
- App A 不能用 `instanceof` 跨 App 比较类
- App A 不能通过反射访问 App B 的内部 API

**架构师必记**:**Android 的 ClassLoader 隔离 = 应用沙箱的核心机制**。**没有 ClassLoader 隔离,Android 安全模型不成立**。

---

## 6. Class 加载的 4 个动作

### 6.1 四元动作在 ClassLoader 视角的体现

**回顾 PLE 01 的"四元动作"(解析/映射/链接/初始化),在 ClassLoader 视角下**:

| 四元动作 | ClassLoader 视角 |
|---|---|
| **解析(Parse)** | 读 DEX 头 + 5 大 id 表 + class_defs |
| **映射(Map)** | 整文件 mmap DEX + 创建 DexFile 对象 |
| **链接(Link)** | 创建 ArtMethod / ArtField / Class 对象 |
| **初始化(Init)** | 执行 `<clinit>`(类初始化器) |

**这 4 个动作是 PLE 08(类加载生命周期)的内容**,本篇聚焦 ClassLoader 树和查找机制。

### 6.2 ClassLoader 的性能影响

**ClassLoader 创建的耗时**:
- 创建 PathClassLoader:**5-15ms**(主要是 mmap base.apk)
- 第一次 Class.forName():**0.1-10ms**(取决于类大小)
- Class Verify:**1-100ms**(取决于类复杂度)

**冷启动 1.5s 中,ClassLoader 贡献多少**:

| 阶段 | 耗时 | 占比 |
|---|---|---|
| linker64 启动 | 50-150ms | 3-10% |
| ART 启动 | 80-150ms | 5-10% |
| ClassLoader 创建 | **10-30ms** | 1-2% |
| DEX 加载 + Verify | 50-200ms | 3-13% |
| Resources 加载 | 100-200ms | 7-13% |
| Application onCreate | 300-500ms | 20-33% |
| 第一帧渲染 | 200-400ms | 13-27% |

**ClassLoader 本身只占 1-2%**,但它**触发的 DEX 加载占 3-13%**。

### 6.3 4 个优化技巧

| 技巧 | 节省时间 | 难度 |
|---|---|---|
| **预加载关键类** | 20-50ms(避免 verify 卡主线程) | 中 |
| **R8 优化** | 30-50% DEX 大小 | 低 |
| **减少 Application onCreate 加载** | 100-300ms | 中 |
| **AOT/VDEX 预编译** | 跳过 verify 30-100ms | 中 |

---

## 7. ClassLoader 工具链速查

### 7.1 必装工具

| 工具 | 用途 | 关键命令 |
|---|---|---|
| **baksmali** | DEX 反汇编 | `baksmali disassemble app.apk -o smali/` |
| **dexdump** | DEX 信息 | `dexdump -d app.apk` |
| **debugger** | ClassLoader 树 | `Thread.currentThread().getContextClassLoader()` |
| **R8** | 优化 DEX | `java -jar r8.jar --release` |
| **art`/bin/dex2oat`** | DEX → ODEX | `dex2oat --dex-input=app.dex` |
| **procyon / jadx** | DEX → Java 源码 | `jadx app.apk` |

### 7.2 5 个常用诊断命令

**命令 1:看 APK 包含的所有类**

```bash
$ baksmali disassemble app.apk -o smali/
$ find smali/ -name "*.smali" | wc -l
```

**命令 2:看某个类是否存在**

```bash
$ baksmali disassemble app.apk -o smali/
$ find smali/ -name "MainActivity.smali"
```

**命令 3:看 R8 是否 strip 了类**

```bash
$ cat mapping.txt | grep "com.example.MyClass"
# 看到映射关系,说明类被处理
# 找不到 → 类被完全 strip
```

**命令 4:看 ClassLoader 树**

```bash
# debugger 里
> ClassLoader cl = ClassLoader.getSystemClassLoader();
> while (cl != null) { System.out.println(cl); cl = cl.getParent(); }
```

**命令 5:看类加载日志**

```bash
$ adb logcat -c
$ adb shell am start -n com.example.app/.MainActivity
$ adb logcat -d | grep "ClassLoader\|Class.forName"
```

---

## 8. 真实案例:类找不到的全套诊断

### 8.1 5 类 ClassNotFoundException 根因

| 根因 | 触发条件 | 诊断命令 |
|---|---|---|
| **类不在 APK** | R8 strip / multidex 顺序错 | `baksmali disassemble` |
| **jar 包缺失** | 依赖未打包 | `unzip -l app.apk \| grep .jar` |
| **父 ClassLoader 找不到** | framework 类被混淆 | `mapping.txt` |
| **ClassLoader 实例不同** | 插件化 / 热修复 | debugger |
| **类加载顺序** | `<clinit>` 死锁 | logcat 看 deadlock |

### 8.2 真实案例:Multidex 顺序错

**症状**:
```
java.lang.ClassNotFoundException: Didn't find class "com.example.MainApplication"
```

**根因**:Multidex 配置错误,MainApplication 在 classes2.dex 里,但 PathClassLoader 找不到。

**修复**:
```groovy
// build.gradle(模块级)
android {
    defaultConfig {
        multiDexEnabled true
        multiDexKeepFile file('multidex-keep.txt')  // 关键类放 main dex
    }
}

dependencies {
    implementation 'androidx.multidex:multidex:2.0.1'
}
```

**multidex-keep.txt**:
```
com/example/MainApplication.class
com/example/MainActivity.class
```

### 8.3 真实案例:R8 strip 第三方 SDK

**症状**:启动时 `ClassNotFoundException: com.thirdparty.SDKManager`。

**根因**:R8 把 SDKManager 给 strip 了。

**修复**:
```proguard
# proguard-rules.pro
-keep class com.thirdparty.** { *; }
-keep class com.thirdparty.**$* { *; }
```

**架构师必记**:**所有第三方 SDK 必须在 proguard-rules.pro 里 -keep**。**R8 默认 strip 没用到的类**。

### 8.4 真实案例:ClassLoader 实例不同

**症状**:用反射创建的类,`instanceof` 返回 false。

**根因**:两个 ClassLoader 都加载了同一个类,但不是同一个 Class 对象。

**诊断**:
```java
// 两个类的 ClassLoader 不同
Class<?> c1 = classLoaderA.loadClass("com.example.Foo");
Class<?> c2 = classLoaderB.loadClass("com.example.Foo");
c1 != c2  // 即使类名相同,Class 对象不同
c1.getClassLoader() != c2.getClassLoader()
```

**修复**:**所有 App 应该共享一个 PathClassLoader**。**热修复 / 插件化要小心 ClassLoader 边界**。

---

## 9. 架构师视角:ClassLoader 的 5 个核心洞察

### 9.1 洞察 1:ClassLoader 是单项链表

**Android App 的 ClassLoader 树只有 2 层**:
- BootClassLoader(framework 共享)
- PathClassLoader(每个 App 进程独立)

**插件化 / 热修复用 DexClassLoader 加第 3 层**。

### 9.2 洞察 2:Class 查找 = 委托 + dexElements 遍历

**5 步路径**:
1. 查缓存
2. 委托父
3. 遍历 dexElements
4. 抛异常
5. 找不到

**优化核心**:**dexElements 数组短 = 查找快**。**multidex / 插件化 = 数组长 = 查找慢**。

### 9.3 洞察 3:可见性是单向的

**子看到父,父看不到子**。**这是 Android 沙箱的核心机制**。

### 9.4 洞察 4:Class 唯一性 = 同一个 ClassLoader 实例

**同一个类被两个 ClassLoader 加载,Class 对象不同**。**`instanceof` 跨 ClassLoader 不可用**。

### 9.5 洞察 5:从 ClassLoader 失败直接映射到故障现象

| 故障现象 | ClassLoader 根因 |
|---|---|
| `ClassNotFoundException` | 类不在 dexPath / R8 strip |
| `NoClassDefFoundError` | 类存在但加载失败(verify 错) |
| `LinkageError` | 重复加载 / ClassLoader 实例不同 |
| `IllegalAccessError` | 访问权限不匹配 |
| 启动慢 100ms+ | Class 加载阻塞主线程 |

---

## 10. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **Android ClassLoader 树只有 2 层** | BootClassLoader(共享) + PathClassLoader(每 App) |
| 2 | **Class 查找 = 委托 + 遍历 dexElements** | 5 步路径,父优先 |
| 3 | **可见性单向** | 子看到父,父看不到子 |
| 4 | **Class 唯一性 = ClassLoader 实例** | 跨 ClassLoader 的 instanceof 不可用 |
| 5 | **R8 必须 -keep 第三方 SDK** | 否则 strip 启动崩溃 |

---

## 11. 下一篇预告

08 篇《类加载生命周期:Loading → Linking → Initializing》会沿着本篇埋下的线索,深入讲:

- Java 7 个阶段(Loading / Verifying / Preparing / Resolving / Initializing / Using / Unloading)
- Loading:loadClass 流程 + parent delegation 缓存
- Verifying:dex2oat 后的 quicken 状态 + 运行时 verify
- Preparing:静态字段默认值
- Resolving:符号引用 → 直接引用
- Initializing:\<clinit\> 执行 + Finalizer 死锁
- Unloading:Class 卸载触发条件
- 架构师视角:7 个阶段的"故障注入点"

**08 篇预计 2 周后产出**,届时一起发你看。

---

## 附录 A:5 种 ClassLoader 对比

| ClassLoader | 加载内容 | 父 | 父指向 |
|---|---|---|---|
| BootClassLoader | framework.jar / core-oj.jar | null | (顶级) |
| PathClassLoader | App APK | BootClassLoader | 共享 |
| DexClassLoader | 任意 .dex / .jar / .apk | PathClassLoader | 可选 |
| InMemoryDexClassLoader | ByteBuffer DEX | PathClassLoader | 可选 |
| SystemClassLoader | system_server 类 | BootClassLoader | system_server |

## 附录 B:Class 查找 5 步路径

```
loadClass(name) {
  1. c = findLoadedClass(name);  // 本 ClassLoader 缓存
  2. if (parent != null) c = parent.loadClass(name);  // 委托父
  3. if (c == null) c = findClass(name);  // 自己找(遍历 dexElements)
  4. if (c == null) throw ClassNotFoundException;
  5. return c;
}
```

## 附录 C:PathClassLoader 构造流程

```
new PathClassLoader(apkPath, libPath, BootClassLoader)
    ↓
super(apkPath, libPath, BootClassLoader)  // BaseDexClassLoader
    ↓
this.pathList = new DexPathList(this, apkPath, libPath)
    ↓
DexPathList 构造:
    for each path in dexPath:
        dex = loadDexFile(path);  // mmap + parse
        dexElements.add(new Element(dex));
```

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 08 类生命周期 | 5 步路径的"3. 自己找"展开为 7 阶段 |
| 09 AOT/JIT | Verify 阶段是 AOT 优化的重点 |
| 12 进程启动 | Zygote fork 后,子进程创建 PathClassLoader |
| 14 风险地图 | §8 失败诊断的"5 类根因"是 P14 速查表的核心 |

---

> **本篇把 ClassLoader 拆解到"5 种类型 + 5 步路径 + 4 个动作 + 5 类失败"5 个维度。**
> **08 篇会在这个基础上,讲"类加载生命周期"——7 个阶段里到底发生了什么、故障在哪里注入。**
> **记住 5 种 ClassLoader、5 步路径、可见性单向、-keep 第三方 SDK,你的 ClassLoader 视角就立住了。**
