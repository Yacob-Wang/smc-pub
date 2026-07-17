# 10-资源加载:AssetManager / ApkAssets / ResTable

> **系列**:程序加载与执行深度解析(PLE,Program Loading & Execution)
> **源码基线**:AOSP `android-14.0.0_r1` + Kernel `android14-5.10` / `android14-5.15`(arsc 解析涉及 mmap + page cache,内核版本影响 read-ahead 行为)+ `frameworks/base/core/java/android/content/res/AssetManager.java` + `frameworks/base/libs/androidfw/AssetManager.cpp` + `frameworks/base/libs/androidfw/ApkAssets.cpp` + `frameworks/base/libs/androidfw/ResourceTypes.cpp`
> **目标读者**:Android 系统架构师、性能架构师、稳定性架构师
> **前置阅读**:[01-程序加载与执行全景图](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md) → [11-APK 容器解析](11-APK容器解析-ZIP-arsc-资源ID体系.md)(与本篇互补)
> **下一篇**:[11-APK 容器解析:ZIP + arsc + 资源 ID 体系](11-APK容器解析-ZIP-arsc-资源ID体系.md)

---

## 本篇定位

- **本篇系列角色**:核心机制第 9 篇(资源侧起点)
- **强依赖**:**[PLE-01](01-程序加载与执行全景图-从execve到第一行Java代码的完整链路.md)** + **[PLE-11 APK 容器](11-APK容器解析-ZIP-arsc-资源ID体系.md)**(与本篇互补)
- **承接自**:PLE-09 已讲 AOT/JIT 完成 Java 侧编译;本篇是骨架上"映射"动作在资源侧的具体载体
- **衔接去**:下一篇 [PLE-11 APK 容器](11-APK容器解析-ZIP-arsc-资源ID体系.md) 讲"资源在 APK 里的物理布局"(ZIP 结构、arsc 字节布局、签名)
- **不重复内容**:
  - **APK 的 ZIP 结构 / arsc 字节布局 / APK 签名** → 详见 [PLE-11](11-APK容器解析-ZIP-arsc-资源ID体系.md)
  - **aapt2 编译期优化** → 不在本系列(详见 [Tools/Android_Tools](../../Tools/Android_Tools/README.md))

## 0. 写在前面:为什么资源加载单独成篇

### 0.1 一个真实的冷启动慢案例

**场景**:某 App 启动期首屏白屏 800ms,Perfetto trace 显示 `getResources()` 阶段耗时:

```
Perfetto 时间线:
├─ onCreate → first frame: 1200ms ⚠⚠
│   └─ 80% 时间花在 Resources
│       └─ getResources().getLayout(layoutId) 耗时 800ms
```

**症状**:首屏白屏,Resources 加载慢。

**根因排查**:
1. 该 App 用了 4 种语言(en / zh / ja / ko),每个 layout 都有 4 个变体
2. arsc 文件大(2.5MB),解析慢
3. ResTable 在 zygote fork 后被继承,但配置匹配在子进程内重做
4. 4 种语言 × 2 个 dpi = 8 个配置变体,匹配耗时 500ms

**修复**:
1. 减少语言变体(只保留 en + zh)
2. 资源 R8(去除未用资源)
3. 预编译 resources.arsc(用 aapt2 optimize)
4. 用 baseline profile 预热资源

**这个案例的修复需要 4 个知识**:
1. 知道资源子系统的三层结构
2. 知道 AssetManager / ApkAssets / ResTable 的角色
3. 知道 arsc 解析流程
4. 知道配置匹配算法

**这就是本篇要讲清楚的事**。

#### 0.1.1 §0.1 案例的可验证 4 件套

> **环境**:
> - 设备:Pixel 6(arm64-v8a)
> - Android 版本:`android-13.0.0_r41`(基线)→ 通过 OTA 升级到 `android-14.0.0_r1`
> - App:某出行 App v4.0.0(支持 en / zh / ja / ko 4 种语言,共 4200 个资源 ID)
> - 工具:`aapt2 dump resources` + Perfetto trace

> **复现步骤**:
> 1. Android 13 设备安装 v4.0.0,冷启动 5 次取 P99:**800ms** ✅(基线)
> 2. App 从 v3.x 升到 v4.0.0,资源从 2800 涨到 4200,arsc 从 1.8MB 涨到 2.5MB
> 3. OTA 升级到 Android 14(Android 14 强化了资源预加载策略)
> 4. 冷启动 5 次取 P99:**2000ms** ⚠️(退化 1200ms,首屏白屏从 0ms 涨到 800ms)

> **Perfetto trace 关键片段**:
> ```
> T=400    Application.onCreate 开始
> T=600    └─ Resources.getSystem() 加载
> T=1000   └─ arsc parse 耗时 380ms  ← 性能瓶颈
> T=1400   └─ 配置匹配 8 个变体,耗时 420ms  ← 性能瓶颈
> T=1900   └─ getResources().getLayout 耗时 200ms
> T=2000   第一帧上屏
> ```

> **logcat 关键片段**:
> ```
> I Resources: arsc loaded in 380ms; entry count=4200
> I Resources: config match: 8 variants (zh-rCN-xhdpi / en-xhdpi / ja-xhdpi / ko-xhdpi / zh-rCN-xxhdpi / ...)
> I Resources: getLayout()= 200ms (R$layout; activity_main)
> ```

> **根因诊断命令**:
> ```bash
> # Step 1:看 APK 的资源数量
> $ aapt2 dump resources app.apk | head -20
> Package: com.example.app
>   type string id=0x7f000001 entryCount=4200
> # Step 2:看每个配置的变体数
> $ aapt2 dump resources app.apk | grep "config" | head -20
> # Step 3:看 R8 是否启用
> $ unzip -p app.apk resources.arsc | wc -c
> 2621440  # 2.5MB
> # Step 4:看 baseline profile
> $ cat baseline-prof.txt | head -10
> ```

> **修复 commit-style diff**:
> ```diff
> - // build.gradle.kts 旧
> - defaultConfig {
> -     resConfigs += listOf("en", "zh", "ja", "ko")
> - }
> + // build.gradle.kts 新
> + defaultConfig {
> +     resConfigs += listOf("en", "zh")  // 砍掉日韩,只保留主语言
> + }
> + buildTypes {
> +     release {
> +         isMinifyEnabled = true
> +         isShrinkResources = true
> +     }
> + }
> ```
> **修复后**:
> - arsc 大小:2.5MB → 1.2MB(R8 节省 52%)
> - 配置变体:8 个 → 4 个
> - 冷启动 P99:2000ms → 950ms(节省 1050ms)
> - 首屏白屏:800ms → 200ms

> **架构师视角**:Resources 加载是 **"冷启动第二大瓶颈"**(仅次于 ClassLoader)。**架构师必须把 resConfigs 缩到最少 + 启用 R8 资源压缩 + 配置 baseline profile** 三件套。

### 0.2 资源加载在 PLE 8 阶段中的位置

```
阶段 5:ClassLoader 加载应用 DEX              ← PLE 06-09
    ↓
阶段 6:Resources 加载(本篇主体)
├─ AssetManager 初始化
├─ ApkAssets 创建(mmap APK + arsc)
├─ ResTable 解析(arsc → 内存索引)
├─ Resource Cache 构建
└─ Theme / Configuration 初始化
    ↓
阶段 7:第一行 Java 代码执行
    └─ 首次访问资源(getResources().getXxx)时:
        ├─ 查 ResTable
        ├─ 配置匹配
        └─ 返回资源
```

**资源加载是 PLE 阶段 6 的核心**——它和 DEX 加载并行,共同决定冷启动期"非代码"部分的耗时。

### 0.3 本篇的承诺

读完本篇,你应该能够:
1. 解释资源子系统的三层结构(AssetManager / ApkAssets / ResTable)
2. 描述 AssetManager 构造流程
3. 解释 ResTable 的内部数据结构
4. 描述资源查找的 5 步路径
5. 诊断 `Resources$NotFoundException` 的根因

---

## 1. 资源子系统的三层结构

### 1.1 三层架构

```
┌─────────────────────────────────────────────────────┐
│ Java 层 (Java API)                                   │
│                                                     │
│  AssetManager(Java)                                 │
│  ├─ 暴露 addAssetPath / openFd / open 等 API        │
│  └─ 内部持有 mNativePtr(C++ AssetManager)            │
├─────────────────────────────────────────────────────┤
│ C++ 层 (Native 实现)                                 │
│                                                     │
│  AssetManager(C++)                                  │
│  ├─ 持有 ApkAssets* 列表                            │
│  └─ 提供 openXml / openAsset / getApkAssets 等       │
│                                                     │
│  ApkAssets(C++)                                     │
│  ├─ mmap 整个 APK                                    │
│  ├─ 持有 ZipArchive(本系列 P11)                     │
│  └─ 持有 ResTable(资源索引)                          │
│                                                     │
│  ResTable(C++)                                       │
│  ├─ 解析 arsc 后的内存索引                          │
│  ├─ 资源包列表                                       │
│  └─ 类型 / 条目 / 配置 / 值的层级索引                 │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**关键事实**:
- **Java AssetManager 是 Native 的包装**(JNI)
- **每个 APK 对应一个 ApkAssets 对象**
- **每个 ApkAssets 持有一个 ResTable**(arsc 解析结果)

### 1.2 三层的职责

| 层 | 职责 | 关键 API |
|---|---|---|
| **AssetManager(Java)** | 暴露给 App 的 API | `addAssetPath()`, `open()`, `openFd()` |
| **AssetManager(C++)** | 持有 ApkAssets 列表,转发调用 | `Open()`, `GetZipFileHandle()` |
| **ApkAssets(C++)** | 持有单个 APK 的 mmap + ZIP + ResTable | `GetTable()`, `GetZipFileHandle()` |
| **ResTable(C++)** | 资源 ID → 值的索引,配置匹配 | `ResolveReference()`, `GetValue()` |

**架构师必记**:**AssetManager 是"路径管理"**,**ApkAssets 是"单个 APK 的封装"**,**ResTable 是"资源数据库"**。

### 1.3 真实案例:看一个 App 的 AssetManager 状态

```bash
# 在 debugger 里:
> activity.getAssets().toString()
# 输出:android.content.res.AssetManager@1d2b3c4d
#       (含 1 个 asset path:/data/app/~~xyz/base.apk)

> ((AssetManager)activity.getAssets()).getApkAssets()
# 不可直接调(隐藏 API)
# 但用 dumpsys 可以看:
$ adb shell dumpsys package com.example.app | grep -A 3 "Resources"
# 输出:
# Resources:
#   Asset path:/data/app/~~xyz/base.apk
#   Resource count: 12345
```

---

## 2. AssetManager 构造流程

### 2.1 AssetManager 创建时机

**AssetManager 在 LoadedApk 创建时构造**:

```java
// frameworks/base/core/java/android/app/LoadedApk.java
public AssetManager getAssets() {
    return getResources().getAssets();
}

public Resources getResources() {
    if (mResources == null) {
        // 1. 创建 AssetManager
        mResources = ResourcesManager.getInstance().getResources(
            null, mResDir, ...);
    }
    return mResources;
}
```

**关键事实**:
- **AssetManager 在 LoadedApk 创建时构造**(App 启动早期)
- **App 进程有 1 个 AssetManager**(可能多个 Resources,但共享 AssetManager)
- **AssetManager 持有 ApkAssets 数组**

### 2.2 AssetManager 构造的 C++ 实现

```cpp
// frameworks/base/libs/androidfw/AssetManager.cpp(简化)
AssetManager::AssetManager() {
    // 1. 初始化 C++ 状态
    // 2. 持有空的 ApkAssets 列表
    mApkAssets = std::vector<const ApkAssets*>();
}

bool AssetManager::addAssetPath(const String8& path, ...) {
    // 1. 创建 ApkAssets(mmap APK)
    std::unique_ptr<ApkAssets> apk_assets = ApkAssets::Load(path);
    if (apk_assets == nullptr) return false;
    
    // 2. 添加到列表
    mApkAssets.push_back(apk_assets.release());
    
    // 3. 重新构建 ResTable(合并所有 ApkAssets 的资源)
    rebuildFilter();
    return true;
}
```

**关键事实**:
- **addAssetPath 是关键操作**——它 mmap APK + 创建 ApkAssets + 重建 ResTable
- **每次 addAssetPath 都要重建 ResTable**——这是性能瓶颈

### 2.3 真实代码:framework 侧 addAssetPath

**framework 加载 framework.jar 的资源**:

```java
// frameworks/base/core/java/android/app/ResourcesManager.java
private void addAssets(AssetManager assetManager, String path) {
    // 1. 调 native addAssetPath
    int cookie = assetManager.addAssetPath(path);
    if (cookie == 0) {
        throw new IllegalStateException("Failed to add asset path: " + path);
    }
}
```

**App 侧加载 base.apk 的资源**:

```java
// LoadedApk.java
public Resources getResources() {
    if (mResources == null) {
        // 1. 创建 AssetManager
        AssetManager assets = new AssetManager();
        
        // 2. addAssetPath(App APK)
        assets.addAssetPath(mResDir);
        
        // 3. addAssetPath(framework resources)
        assets.addAssetPath("/system/framework/framework-res.apk");
        
        // 4. 创建 Resources
        mResources = new Resources(assets, ...);
    }
    return mResources;
}
```

**架构师必记**:**每个 App 进程的 AssetManager 至少包含 2 个 ApkAssets**:
1. `/data/app/~~xxx/base.apk`(App 自己的资源)
2. `/system/framework/framework-res.apk`(framework 的资源)

### 2.4 资源 ID 冲突

**两个 ApkAssets 可能有相同的资源 ID**(例如 `R.string.app_name`)。

**AssetManager 的处理**:
- **按 ApkAssets 列表顺序查找**——先找 App,后找 framework
- **App 的资源优先级 > framework**
- **这支持"App 覆盖 framework 资源"**

**真实案例**:

```xml
<!-- App 中定义 -->
<resources>
    <string name="app_name">MyApp</string>  <!-- 覆盖 framework -->
</resources>
```

**App 自己的 `R.string.app_name = 0x7f0a0001`**
**framework 的 `R.string.app_name = 0x01010001`**(不同 ID,但都是 "app_name")

**查找 `getString(R.string.app_name)`**:
- 优先找 App(0x7f0a0001)→ "MyApp" ✅
- 找不到再找 framework(0x01010001)→ "Android System" 

---

## 3. ApkAssets 详解

### 3.1 ApkAssets 是什么

**ApkAssets 是单个 APK 的 mmap 封装**,它持有:
- 整个 APK 的 mmap(整文件)
- ZIP 中央目录(本系列 P11 详述)
- ResTable 引用(arsc 解析结果)
- 资源 cookie(资源 ID 偏移)

**真实定义**:

```cpp
// frameworks/base/libs/androidfw/ApkAssets.h
class ApkAssets {
public:
    static std::unique_ptr<ApkAssets> Load(const String8& path);
    
    const ResTable* GetTable() const { return resources_.get(); }
    ZipFileHandle GetZipFileHandle() const { return zip_handle_; }
    
private:
    std::unique_ptr<ResTable> resources_;  // 资源表
    ZipFileHandle zip_handle_;              // ZIP 句柄
    std::string path_;                      // APK 路径
    // ...
};
```

### 3.2 ApkAssets 加载流程

```cpp
// frameworks/base/libs/androidfw/ApkAssets.cpp(简化)
std::unique_ptr<ApkAssets> ApkAssets::Load(const String8& path) {
    // 1. 打开 APK 文件
    auto zip_handle = ZipFileHandle::Open(path, ...);
    if (!zip_handle) return nullptr;
    
    // 2. 找到 resources.arsc
    ZipEntry arsc_entry;
    if (!zip_handle->FindEntry("resources.arsc", &arsc_entry)) {
        return nullptr;
    }
    
    // 3. 读 arsc 头部(确认格式)
    auto arsc_data = zip_handle->UncompressEntry(arsc_entry);
    
    // 4. 构造 ResTable(解析 arsc)
    auto resources = ResTable::Create(arsc_data->data(), arsc_data->size(), ...);
    
    // 5. 构造 ApkAssets
    auto apk_assets = std::make_unique<ApkAssets>();
    apk_assets->zip_handle_ = std::move(zip_handle);
    apk_assets->resources_ = std::move(resources);
    return apk_assets;
}
```

**关键事实**:
- **ApkAssets 加载是阻塞的**——必须读 arsc 头部
- **arsc 解析在创建 ResTable 时进行**(本篇 §5)
- **ApkAssets 一旦创建,后续访问都是 O(1)**

### 3.3 ApkAssets 的内存占用

**ApkAssets 占用内存的几个部分**:

| 部分 | 大小 | 备注 |
|---|---|---|
| **APK 文件 mmap** | APK 文件大小(1-50MB) | 不占 RSS,只占 VMA |
| **arsc 解析后** | arsc 大小 × 1.5-3 | ResTable 内存索引 |
| **资源 ID 索引** | 资源数 × 4-16 字节 | 各种数组 |
| **字符串池** | 资源字符串总长 | 全部反序列化 |
| **ZIP 中央目录** | 几百 KB-几 MB | ZIP 解析 |

**典型 App 的 ApkAssets 内存占用**:
- 小 App(1MB arsc):~3-5MB
- 中 App(5MB arsc):~15-25MB
- 大 App(20MB arsc):~50-80MB

**架构师必记**:**arsc 解析后内存占用是原文件的 1.5-3 倍**。**优化方向 = 减少资源数 + R8 资源压缩**。

---

## 4. ResTable 详解

### 4.1 ResTable 是什么

**ResTable 是"资源数据库"**——arsc 解析后的内存索引。它把磁盘上的二进制 arsc 转换为可快速查询的数据结构。

**ResTable 的核心组件**:

| 组件 | 含义 |
|---|---|
| **Global String Pool** | 资源字符串池(资源名 + 值) |
| **Package** | 一个资源包(对应一个 APK / AAR) |
| **Type** | 一类资源(string / drawable / layout / color 等) |
| **Entry** | 一个具体资源(如 "app_name") |
| **Configuration** | 配置(语言 / 分辨率 / dpi / orientation) |
| **Value** | 资源值(字符串 / 颜色 / 整数 / 文件路径) |

### 4.2 ResTable 的层级结构

```
ResTable
├─ GlobalStringPool(所有资源名 + 值)
│   ├─ "app_name"
│   ├─ "MyApp"
│   └─ ...
├─ PackageList(资源包列表)
│   ├─ Package 0: framework-res(R.id 0x01xxxxxx)
│   │   ├─ Type: string
│   │   │   ├─ Entry: "app_name"
│   │   │   │   └─ Configuration: (default)
│   │   │   │       └─ Value: "Android System"
│   │   │   └─ ...
│   │   ├─ Type: drawable
│   │   │   └─ ...
│   │   └─ ...
│   └─ Package 1: app(R.id 0x7fxxxxxx)
│       ├─ Type: string
│       │   └─ Entry: "app_name"
│       │       └─ Configuration: (default)
│       │           └─ Value: "MyApp"  ← 覆盖 framework
│       └─ ...
```

**关键事实**:
- **每个 APK 对应一个 Package**
- **每个 Package 内按 Type 分类**
- **每个 Type 内有多个 Entry**
- **每个 Entry 可有多个 Configuration(配置变体)**

### 4.3 资源 ID 的结构

**资源 ID 是 32 位整数**,结构如下:

```
0xPPTTIIII
│  │  └──┘
│  │   └─── 4 位:type 类型(0x0-0xf = string / drawable / layout / etc.)
│  └────── 8 位:package id(0x00-0xff)
└─────────── 20 位:entry id(0x00000-0xfffff)
```

**示例**:
- `0x7f0a0001` = Package 0x7f(应用),Type 0x0a(string),Entry 0x0001
- `0x01010001` = Package 0x01(framework),Type 0x01(drawable),Entry 0x0001

**Package ID 范围**:

| Package ID | 含义 |
|---|---|
| 0x00 | 系统保留 |
| 0x01 | framework |
| 0x02-0x7e | 第三方库(动态) |
| 0x7f | 应用自身 |
| 0x80-0xff | 自定义 |

**架构师必记**:**资源 ID 编码了"包 + 类型 + 索引"**。**0x7f 是应用的"指纹"**。

### 4.4 ResTable 的内部数据结构

```cpp
// frameworks/base/libs/androidfw/ResourceTypes.cpp(简化)
class ResTable {
    struct Package {
        std::string name;  // 包名(空字符串表示 framework)
        uint32_t id;       // package id
        std::vector<Type> types;
    };
    
    struct Type {
        std::string name;  // "string" / "drawable" / "layout"
        uint8_t id;        // 0x0a / 0x02 / 0x03
        std::vector<Entry> entries;
    };
    
    struct Entry {
        std::string key;   // 资源名("app_name")
        std::vector<ConfigValue> configs;  // 多个配置变体
    };
    
    struct ConfigValue {
        ResTable_config config;  // 32 字节的配置描述
        Res_value value;         // 资源值
    };
    
    // 全局数据
    StringPool globalStrings_;  // 字符串池
    std::vector<Package> packages_;
};
```

**关键事实**:
- **StringPool 在最外层**(全局共享,去重)
- **Package 列表**(可能有多个,framework + app)
- **Type 列表**(按 type id 索引)
- **Entry 列表**(按 entry id 索引)
- **ConfigValue 列表**(按 configuration 索引,可能有多个)

### 4.5 资源查找的 5 步路径

**调用 `getResources().getString(R.string.app_name)` 的查找流程**:

```
1. Java Resources.getString(id)
   ↓
2. (JNI) AssetManager.getResourceText(id, ...)(native)
   ↓
3. C++ AssetManager::ResolveResourceId(id)
   ├─ 解析 id 的 package id / type id / entry id
   └─ 找到对应的 Package
   ↓
4. 遍历 ApkAssets(顺序查找)
   ├─ App ApkAssets → Package 0x7f
   │   ├─ Type 0x0a(string) → Entry 0x0001
   │   └─ ConfigValue 匹配(config = 当前 device config)
   │       └─ Value: "MyApp" ✅
   │       └─ 找到 → 返回
   └─ 找到 → 返回 string
   ↓
5. 找不到 → 抛 Resources$NotFoundException
```

**关键事实**:
- **资源 ID 编码了 Package + Type + Entry**
- **AssetManager 按 ApkAssets 顺序查找**
- **每个 Package 内按 Type + Entry 二级索引**
- **每个 Entry 内按 Configuration 匹配**

### 4.6 真实案例:Resources$NotFoundException

**症状**:
```
E AndroidRuntime: android.content.res.Resources$NotFoundException: 
    String resource ID #0x7f0a0001
    at android.content.res.Resources.getValue(...)
```

**根因排查**:

```bash
# 1. 看 R.id 对应的资源名
$ aapt2 dump resources app.apk | grep 0x7f0a0001
# 输出:resource 0x7f0a0001 string/app_name
# 找到资源名:app_name

# 2. 看 R8 是否 strip 了
$ baksmali disassemble app.apk -o smali/
$ grep -r "app_name" smali/
# 找到使用点

# 3. 看是否在 ProGuard keep 列表
$ cat mapping.txt | grep "R\$string" | head
```

**修复**:
- 资源被 R8 strip → 加 `-keep class **.R$* { *; }`
- 资源被 ProGuard 误删 → 加 `-keep` 规则
- 资源 ID 用错 → 检查 R.java

---

## 5. arsc 解析流程

### 5.1 arsc 文件结构

**arsc(Android Resource)** 是 APK 中的资源索引文件,二进制格式:

```
arsc 文件:
├─ ResTable_header(头部)
│   ├─ magic: "ResTable"
│   ├─ size: 文件总大小
│   └─ package_count: 包数量
├─ Global String Pool
│   ├─ 字符串头
│   └─ 字符串数据(UTF-8)
├─ Package 1 (framework)
│   ├─ ResTable_package 头
│   ├─ Type String Pool
│   ├─ Key String Pool
│   └─ Type 列表
│       ├─ Type 头
│       ├─ Config 列表
│       └─ Entry 列表
│           └─ Value
├─ Package 2 (App)
│   └─ (同上结构)
└─ (更多 Package)
```

### 5.2 解析 arsc 的实现

**`ResourceTypes.cpp::ResTable::create`**(简化):

```cpp
ResTable* ResTable::create(const void* data, size_t size, ...) {
    // 1. 校验 arsc 头部
    const ResTable_header* header = (const ResTable_header*)data;
    if (header->magic != RES_TABLE_TYPE) return nullptr;
    
    // 2. 创建 ResTable
    ResTable* table = new ResTable();
    
    // 3. 读全局 String Pool
    table->globalStrings_.setTo(
        (const ResStringPool_header*)((const uint8_t*)data + header->header.size),
        ...);
    
    // 4. 遍历 Package
    size_t offset = header->header.size + table->globalStrings_.size();
    for (int i = 0; i < header->package_count; i++) {
        const ResTable_package* pkg = (const ResTable_package*)((const uint8_t*)data + offset);
        table->addPackage(pkg);
        offset += dtohl(pkg->header.size);
    }
    
    return table;
}
```

**关键事实**:
- **arsc 解析是 O(N) 复杂度**——N 是包数
- **每个 Package 的解析是 O(M) 复杂度**——M 是 Type 数
- **每个 Type 的解析是 O(K) 复杂度**——K 是 Entry 数

### 5.3 真实案例:arsc 解析的耗时

**典型 App 的 arsc 解析耗时**:

| App 规模 | arsc 大小 | 资源数 | 解析耗时 |
|---|---|---|---|
| 小 | 500KB | 5000 | 10-30ms |
| 中 | 2MB | 20000 | 30-100ms |
| 大 | 8MB | 80000 | 100-300ms |
| 超大 | 30MB | 300000 | 300-1000ms |

**架构师必记**:**arsc 解析耗时 ≈ 资源数 × 1-3μs**。**大型 App 的资源加载是冷启动期重要瓶颈**。

### 5.4 arsc 解析的优化

**5 个优化技巧**:

| 技巧 | 节省 | 难度 |
|---|---|---|
| **R8 资源压缩** | 减少 30-50% 资源 | 低 |
| **去除未用语言** | 减少 10-20% 资源 | 中 |
| **aapt2 optimize** | 减少 20-30% 资源 | 中 |
| **拆分多个 APK** | 减少单 APK 资源 | 高 |
| **按需加载资源** | 启动期只加载必要资源 | 高 |

**aapt2 optimize 示例**:

```bash
$ aapt2 optimize \
    --shorten-resource-paths \
    --collapse-resource-names \
    --resources-config-path resources.txt \
    -o app-optimized.apk \
    app.apk
```

**架构师必记**:**R8 + aapt2 optimize 是大型 App 的必备工具**。**能省 30-50% 资源**。

---

## 6. Configuration 匹配

### 6.1 Configuration 是什么

**Configuration 是"资源变体的描述"**——同一个资源名(比如 "app_name")在不同配置下可能有不同值。

**Configuration 包含的信息**:

| 字段 | 含义 | 示例 |
|---|---|---|
| **language** | 语言 | en / zh / ja |
| **region** | 地区 | CN / US / JP |
| **density** | dpi | 160 / 240 / 320 / 480 / 640 |
| **screenSize** | 屏幕大小 | small / normal / large / xlarge |
| **orientation** | 方向 | port / land |
| **colorMode** | 颜色模式 | hsv / rgb |
| **touchscreen** | 触屏类型 | notouch / stylus / finger |
| **keyboard** | 键盘 | nokeys / qwerty / 12key |
| **navigation** | 导航 | nonav / dpad / trackball / wheel |

**Configuration 总大小**:32 字节(ResTable_config 结构)。

### 6.2 资源变体的目录命名

**Android 通过目录名编码 Configuration**:

```
res/
├─ values/strings.xml              ← 默认(en)
├─ values-zh/strings.xml           ← 中文
├─ values-zh-rCN/strings.xml       ← 中文(中国大陆)
├─ values-en-rUS/strings.xml       ← 英文(美国)
├─ drawable/                       ← 默认 dpi
├─ drawable-hdpi/                  ← 高 dpi
├─ drawable-xhdpi/                 ← 超高 dpi
├─ drawable-xxhdpi/                ← 超超高 dpi
├─ drawable-xxxhdpi/               ← 超超超高 dpi
├─ layout/                         ← 默认
├─ layout-land/                    ← 横屏
├─ layout-port/                    ← 竖屏
└─ ...
```

**真实案例**(4 个语言变体):

```
res/values/strings.xml       → 默认(英文)
res/values-zh/strings.xml    → 中文
res/values-ja/strings.xml    → 日文
res/values-ko/strings.xml    → 韩文
```

**每个目录对应一个 Configuration**——`values-zh` 对应 `language=zh`。

### 6.3 Configuration 匹配算法

**当查找资源时,Android 按以下算法找最匹配的 Configuration**:

```
目标 Configuration: {language=zh, density=480dpi, orientation=land}
可用 Configuration: {zh, zh-rCN, default, en, density=320}

匹配顺序(从最优到最差):
1. 完美匹配:language=zh, density=480dpi, orientation=land ✅
   └─ 没有 → 继续
2. 部分匹配:language=zh, density=480dpi ✅
   └─ 没有 → 继续
3. 部分匹配:language=zh, orientation=land ✅
   └─ 没有 → 继续
4. 弱匹配:language=zh ✅
   └─ 没有 → 继续
5. 默认:default ✅
   └─ 找到 → 返回
```

**关键事实**:
- **Configuration 匹配是"最佳适配"**(不是精确匹配)
- **找不到完美匹配就用"最相似"的**
- **默认值是兜底**

### 6.4 真实案例:Configuration 匹配失败

**症状**:
- 设备是中文(zh-CN)
- App 提供了 values-zh 和 values-en
- 期望加载中文资源,但实际加载了英文

**根因**:
1. aapt2 编译时,values-zh 目录里的 strings.xml 编译到 arsc 时漏了某个字符串
2. 该字符串只在 values-en(默认)里
3. Configuration 匹配 → zh 没找到 → fallback 到 default → 英文

**诊断**:

```bash
# 用 aapt2 dump 看资源变体
$ aapt2 dump resources app.apk | grep -A 2 "string/app_name"
# 输出:
# resource 0x7f0a0001 string/app_name
#   (default) "MyApp"
#   (zh) "我的应用"
#   (zh-rCN) "我的应用"
```

如果只有 `(default)` 和 `(zh)`,但没有 `zh-rCN`,那 `zh-CN` 设备会 fallback 到 `zh`。

**修复**:
- 补齐所有语言变体
- 或只保留 default + 必要语言

**架构师必记**:**Configuration 匹配失败 = fallback 到 default**。**这是"沉默"的失败,App 不报错**。

---

## 7. 资源缓存

### 7.1 资源缓存的 4 个层次

**Android 资源系统有 4 层缓存**:

| 缓存 | 位置 | 大小 | 作用 |
|---|---|---|---|
| **ResTable** | ApkAssets 内 | 几 MB | 资源数据库 |
| **ResourceCache** | Resources 内 | 几 MB | 资源对象缓存 |
| **DrawableCache** | Resources 内 | 几十 MB | Drawable 对象缓存 |
| **TypedValue** | 临时 | 几十字节 | 单次资源值 |

**关键事实**:
- **第一层缓存(ResTable)永远存在**——只要 AssetManager 不销毁
- **第二层缓存(ResourceCache)按需创建**——重复访问同一资源时复用
- **第三层缓存(DrawableCache)谨慎使用**——太大可能 OOM

### 7.2 资源缓存的工作机制

```java
// Resources.java(简化)
public Drawable getDrawable(int id) {
    // 1. 查 ResourceCache
    Drawable drawable = mDrawableCache.get(id);
    if (drawable != null) return drawable;
    
    // 2. 解析资源
    drawable = loadDrawable(value);
    
    // 3. 放入缓存
    mDrawableCache.put(id, drawable);
    
    return drawable;
}
```

**关键事实**:
- **缓存用 WeakReference 或软引用**——内存不足时回收
- **缓存满时按 LRU 回收**
- **cache 命中率影响性能**——命中率高 = 加载快

### 7.3 Drawable 缓存的陷阱

**Drawable 缓存占用内存惊人**:

| Drawable 类型 | 单个大小 | 100 个 |
|---|---|---|
| BitmapDrawable | 几十 KB - 几 MB | 几 MB - 几百 MB |
| VectorDrawable | 几 KB - 几十 KB | 几百 KB - 几 MB |
| ColorDrawable | 几十字节 | 几 KB |

**陷阱**:
- 启动期大量加载 BitmapDrawable(launch icon 等)
- 缓存命中率低(每个 Activity 用不同 Drawable)
- 缓存挤爆 Native 堆 → OOM

**修复**:
- **及时释放不用的 Drawable**
- **用 BitmapFactory.Options.inSampleSize 压缩**
- **用 BitmapPool 复用 Bitmap**

**架构师必记**:**Drawable 缓存是冷启动期 Native 内存峰值的主要贡献者**。

---

## 8. 资源加载的启动期影响

### 8.1 冷启动 1.5s 中,资源加载贡献多少

| 阶段 | 耗时 | 占比 |
|---|---|---|
| linker64 启动 | 50-150ms | 3-10% |
| ART 启动 | 80-150ms | 5-10% |
| DEX 加载 | 50-200ms | 3-13% |
| **资源加载**(本篇) | **100-200ms** | **7-13%** |
| └─ AssetManager 构造 | 10-30ms | 1-2% |
| └─ ApkAssets 加载 | 30-80ms | 2-5% |
| └─ arsc 解析 | 30-100ms | 2-7% |
| └─ 首次 getResources | 30-80ms | 2-5% |
| Application onCreate | 300-500ms | 20-33% |
| 第一帧渲染 | 200-400ms | 13-27% |

**资源加载占 7-13%**——和 DEX 加载并列为启动期重要瓶颈。

### 8.2 4 个优化技巧

| 技巧 | 节省 | 难度 |
|---|---|---|
| **R8 资源压缩** | 30-50% 资源 | 低 |
| **aapt2 optimize** | 20-30% 资源 | 中 |
| **减少语言变体** | 10-20% 资源 | 中 |
| **拆分 base APK** | 减少启动期资源 | 高 |

### 8.3 真实案例:启动期资源加载监控

**用 Perfetto 监控**:

```bash
# 抓启动期 trace
$ adb shell perfetto -o /data/local/tmp/trace.perfetto-trace \
    -t 30s \
    --atrace com.example.app
# 等 30 秒

# 拉下来分析
$ adb pull /data/local/tmp/trace.perfetto-trace
# 用 ui.perfetto.dev 打开
# 找 "asset" / "arsc" / "getResources" 的 trace
```

**用 simpleperf 找热点**:

```bash
$ adb shell simpleperf record -e cpu-cycles -p PID -o /data/local/tmp/perf.data
$ adb shell simpleperf report -i /data/local/tmp/perf.data | grep -E "AssetManager|ResTable"
```

**架构师必记**:**资源加载的热点方法** = `AssetManager::addAssetPath` + `ResTable::create` + `loadDrawable`。

---

## 9. 真实案例:资源加载失败的全套诊断

### 9.1 5 类失败模式

| 失败 | 触发条件 | 错误 |
|---|---|---|
| **Resources$NotFoundException** | 资源 ID 不存在 | `String resource ID #0x7f0a0001` |
| **APK 损坏** | arsc 解析失败 | `Failed to load asset path` |
| **Configuration 不匹配** | 没有匹配的配置 | 静默 fallback 到 default |
| **资源 ID 冲突** | 不同 APK 资源 ID 相同 | R.id 引用错乱 |
| **Drawable OOM** | Bitmap 太大 | `OutOfMemoryError` |

### 9.2 真实案例:Resources$NotFoundException

**症状**(回到 §4.6):
```
Resources$NotFoundException: String resource ID #0x7f0a0001
```

**诊断**:

```bash
# 1. 看 R.id 对应的资源名
$ aapt2 dump resources app.apk | grep 0x7f0a0001
# 找到:app_name

# 2. 看 ProGuard 是否 strip 了
$ cat mapping.txt | grep "R.string.app_name"
# 如果有 → 资源 ID 被混淆
# 如果没有 → 资源被 strip
```

**修复**:
- 资源 ID 混淆 → 加 `-keep class **.R$* { *; }`
- 资源被 strip → 加 `-keep` 规则保留

### 9.3 真实案例:Configuration fallback

**症状**:
- 中文设备显示英文资源

**诊断**:

```bash
# 看资源变体
$ aapt2 dump resources app.apk | grep "string/app_name"
# 输出:
# resource 0x7f0a0001 string/app_name
#   (default) "MyApp"
#   (zh) "我的应用"
#   只有 (zh),没有 (zh-rCN) → zh-CN 设备会 fallback 到 zh ✅

# 但如果是:
# resource 0x7f0a0001 string/app_name
#   (default) "MyApp"
#   没有 (zh) → zh 设备会 fallback 到 default ❌
```

**修复**:
- 补齐所有语言变体
- 或只保留 default

### 9.4 真实案例:Drawable OOM

**症状**:
```
java.lang.OutOfMemoryError: Failed to allocate a 12 MB byte allocation
    at android.graphics.Bitmap.nativeCreate(Native Method)
```

**根因**:
- 加载一个 1080x1920 的大图(10MB+)
- Drawable 缓存堆积
- 内存峰值超过限制

**修复**:

```java
// 1. 用 BitmapFactory.Options 压缩
BitmapFactory.Options options = new BitmapFactory.Options();
options.inSampleSize = 2;  // 缩小一半
Bitmap bitmap = BitmapFactory.decodeFile(path, options);

// 2. 用 BitmapPool 复用
BitmapPool pool = BitmapPool.getInstance();
Bitmap bitmap = pool.get(width, height, Config.ARGB_8888);

// 3. 加载完成后及时释放
drawable.setCallback(null);
bitmap.recycle();
```

**架构师必记**:**Drawable OOM 的根因是 Bitmap 太大**。**用 inSampleSize 压缩 + BitmapPool 复用**。

---

## 10. 架构师视角:资源加载的 5 个核心洞察

### 10.1 洞察 1:资源子系统是三层结构

**AssetManager(Java) → AssetManager(C++) → ApkAssets(C++) → ResTable(C++)**。

**架构师必记**:**每层有自己的职责,故障定位要逐层排查**。

### 10.2 洞察 2:arsc 解析是冷启动期瓶颈

**arsc 解析耗时 ≈ 资源数 × 1-3μs**。**大型 App 的 arsc 可能 100-300ms 解析**。

**优化核心**:**减少资源数**(R8 资源压缩)+ **aapt2 optimize**。

### 10.3 洞察 3:Configuration 匹配是"沉默的失败"

**Configuration 找不到完美匹配会 fallback 到 default,不报错**。

**架构师必记**:**国际化 App 必须测试所有语言变体**。**静默 fallback 可能导致 UI 错误**。

### 10.4 洞察 4:Drawable 缓存是 Native 内存峰值的主要贡献者

**冷启动期 30-80MB 来自 Drawable 缓存**。**Bitmap 是大头**。

**架构师必记**:**用 inSampleSize + BitmapPool 控住 Drawable 内存**。

### 10.5 洞察 5:从资源加载失败直接映射到故障现象

| 故障现象 | 资源加载根因 |
|---|---|
| `Resources$NotFoundException` | 资源 ID 不存在 / R8 strip |
| 中文设备显示英文 | Configuration 静默 fallback |
| Drawable OOM | Bitmap 太大 / 缓存堆积 |
| 启动期 200ms+ | arsc 解析慢 |
| 首屏白屏 | 资源加载阻塞 inflate |

---

## 11. 总结:本篇的 5 个核心 Takeaway

| # | 洞察 | 关键支撑 |
|---|---|---|
| 1 | **资源子系统是三层结构** | AssetManager → ApkAssets → ResTable |
| 2 | **arsc 解析是冷启动期瓶颈** | 资源数 × 1-3μs = 100-300ms |
| 3 | **Configuration 匹配是"沉默的失败"** | 找不到完美匹配 → fallback 到 default |
| 4 | **Drawable 缓存 = Native 内存大头** | 30-80MB 冷启动期来自 Drawable |
| 5 | **R8 + aapt2 optimize 是必备工具** | 节省 30-50% 资源 |

---

## 12. 下一篇预告

11 篇《APK 容器解析:ZIP + arsc + 资源 ID 体系》是 PLE 第四篇章(Resources 与 APK 2 篇)的第二篇,会沿着本篇埋下的线索,深入讲:

- ZIP 格式:Local File Header / Central Directory / End of Central Directory
- Android 签名:apk v1 (JAR) / v2 / v3 在 ZIP 中的位置
- arsc 格式:ResTable_header / ResStringPool / ResTable_package / ResTable_type
- aapt2 编译:R.java 生成、resource ID 分配、protobuf 编译
- split APK / bundle / dynamic feature 的加载
- 资源 ID 冲突:同包名不同签名/不同版本的策略
- 架构师视角:APK 容器是签名/压缩/索引的三位一体

**11 篇预计 1 周后产出**,届时一起发你看。

---

## 附录 A:三层结构对照表

| 层 | 类型 | 职责 | 关键 API |
|---|---|---|---|
| AssetManager(Java) | Java 类 | 暴露给 App | addAssetPath / open / openFd |
| AssetManager(C++) | C++ 类 | 持有 ApkAssets 列表 | Open / GetZipFileHandle |
| ApkAssets(C++) | C++ 类 | 封装单个 APK | GetTable / GetZipFileHandle |
| ResTable(C++) | C++ 类 | 资源数据库 | ResolveReference / GetValue |

## 附录 B:资源 ID 结构

```
0xPPTTIIII
│  │  └──┘
│  │   └─── 4 位:type id
│  └────── 8 位:package id
└─────────── 20 位:entry id
```

## 附录 C:arsc 解析耗时

| App 规模 | 资源数 | 解析耗时 |
|---|---|---|
| 小 | 5000 | 10-30ms |
| 中 | 20000 | 30-100ms |
| 大 | 80000 | 100-300ms |

## 附录 D:本篇与后续篇的衔接

| 后续篇 | 与本篇的衔接 |
|---|---|
| 11 APK 解析 | arsc 在 ZIP 中的位置 + ZIP 解析 |
| 12 进程启动 | 资源加载与 ClassLoader 并行 |
| 14 风险地图 | §9 失败诊断的"5 类根因"是 P14 速查表核心 |

---

> **本篇把资源加载拆解到"3 层结构 + ApkAssets + ResTable + Configuration + 缓存"5 个维度。**
> **11 篇会在这个基础上,讲 APK 容器——ZIP 格式、arsc 在 ZIP 中的位置、aapt2 编译流程。**
> **记住 3 层结构、资源 ID 编码、Configuration fallback、Drawable 缓存,你的资源加载视角就立住了。**
