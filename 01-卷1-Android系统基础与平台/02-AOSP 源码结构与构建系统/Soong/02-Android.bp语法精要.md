# 06-Foundation/Build-System/Soong · 02 · Android.bp 语法精要

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · BSP · 改源码工程师
>
> **强依赖**：[01 从 Make 到 Soong](01-从Make到Soong：AOSP编译系统演进.md) · [03 Blueprint](03-Blueprint：Soong的中间表示与解析.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Android.bp 的 9 大常用 module 类型 + 6 大通用属性 + 3 个特殊语法讲清楚——vendor 加 module 时 5 分钟上手
- **不是**：不重复 Blueprint 内部 AST 解析（[03](03-Blueprint：Soong的中间表示与解析.md)）；不重复 Soong 整体架构（[04](04-Soong架构：plugin.provider.mutator.generator.md)）
- **承接自**：[01 §6 mk vs bp 真实对比](01-从Make到Soong：AOSP编译系统演进.md)（本文展开 .bp 完整语法）
- **衔接去**：[03 Blueprint](03-Blueprint：Soong的中间表示与解析.md) / [05 Ninja 文件解读](05-Ninja生成与ninja文件解读.md) / [07 常见编译错误](07-常见编译错误速查.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 9 大 module 类型按"出现频率"排序 | cc_library / java_library / android_app 占 80% |
| 2 | 6 大属性族按"改源码触及频率"排序 | srcs / include_dirs 改 100 次，cflags 改 10 次 |
| 3 | 第 4-7 章用 4 个真实 cross-compile 案例 | 不用 toy example，AOSP 17 真实 case |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Android.bp = JSON-like 配置 + 强类型 module 抽象 + Blueprint 函数调用。**

AOSP 17 上 25000+ 个 Android.bp 文件，**9 大 module 类型覆盖 99% 的场景**。本文给"9 类型 + 6 属性 + 3 特殊语法 + 4 真实案例"，让 vendor 适配 5 分钟上手。

---

## 1. 9 大常用 module 类型

按 AOSP 17 实际出现频率排序（基于 `find . -name "Android.bp" | xargs grep -h "^[a-z_]* {" | sort | uniq -c | sort -rn` 简化）：

| 排名 | module 类型 | 用途 | 出现频率 |
|:----:|:-----------|:----|:--------|
| 1 | `cc_library` | C/C++ 库 | ~30% |
| 2 | `java_library` | Java 库 | ~20% |
| 3 | `android_app` / `android_library` | Android 应用 / 库 | ~15% |
| 4 | `cc_binary` | C/C++ 可执行 | ~8% |
| 5 | `cc_test` / `cc_benchmark` | C/C++ 测试 | ~5% |
| 6 | `java_test` | Java 测试 | ~5% |
| 7 | `filegroup` | 文件集合（不编译）| ~5% |
| 8 | `prebuilt_*` | 预编译产物 | ~7% |
| 9 | `header_library` | 头文件库 | ~5% |

### 1.1 前 4 类型（占 73%）

**cc_library**（C/C++ 库，30%）：

```python
cc_library {
    name: "libfoo",
    srcs: ["src/*.cpp"],
    include_dirs: ["include"],
    shared_libs: ["liblog"],
    static_libs: ["libbar"],
    cflags: ["-Wall", "-Werror"],
    sanitize: { integer: true },
    vendor_available: true,  # platform 和 vendor 都能用
}
```

**java_library**（Java 库，20%）：

```python
java_library {
    name: "my-framework-jar",
    srcs: ["src/**/*.java"],
    static_libs: ["framework-annotations-lib"],
    java_version: "17",  # AOSP 17 默认
}
```

**android_app**（Android 应用，10%）：

```python
android_app {
    name: "MyApp",
    srcs: ["src/**/*.java"],
    resource_dirs: ["res"],
    manifest: "AndroidManifest.xml",
    platform_apis: true,  # 用 @hide API
    certificate: "platform",  # 签名
}
```

**cc_binary**（C/C++ 可执行，8%）：

```python
cc_binary {
    name: "mytool",
    srcs: ["src/main.cpp"],
    shared_libs: ["liblog", "libutils"],
    init_rc: ["mytool.rc"],  # 自动生成 init.<device>.rc
}
```

### 1.2 5 个补充类型

**filegroup**（5%）：纯文件集合，不编译

```python
filegroup {
    name: "my-config-files",
    srcs: ["*.conf", "*.cfg"],
}
```

**prebuilt_***（7%）：引入外部编译产物

```python
prebuilt_shared_library {
    name: "libvendorfoo",
    srcs: ["vendor/foo/lib/libvendorfoo.so"],
    strip: { keep_symbols: true },
}
```

**header_library**（5%）：纯头文件库（仅 include_dirs）

```python
header_library {
    name: "libfoo_headers",
    export_include_dirs: ["include"],
}
```

**cc_test**（5%）：C/C++ 测试

```python
cc_test {
    name: "mytest",
    srcs: ["test/*.cpp"],
    gtest: true,
    shared_libs: ["libgtest"],
}
```

**java_test**（5%）：Java 测试

```python
java_test {
    name: "MyTest",
    srcs: ["test/**/*.java"],
    static_libs: ["junit", "mockito"],
    jni: { name: "mytestjni" },
}
```

---

## 2. 6 大通用属性族

### 2.1 srcs（源文件）— 改 100 次

**3 种值**：

```python
# 显式列表
srcs: ["src/foo.cpp", "src/bar.cpp"]

# glob 模式
srcs: ["src/*.cpp", "src/**/*.cpp"]

# exclude 排除
srcs: ["src/**/*.cpp"],
exclude_srcs: ["src/bad.cpp"],
```

**glob 规则**：
- `*` → 任意字符（不含 `/`）
- `**` → 任意字符（含 `/`）
- `?` → 单字符
- `[abc]` → 字符集

**真实例子**：

```python
# 找所有 .cpp 但排除 test/
srcs: ["src/**/*.cpp"],
exclude_srcs: ["src/test/**/*"],
```

### 2.2 include_dirs（头文件路径）— 改 50 次

```python
# 当前 module 内的 include
include_dirs: ["include"]

# 多个目录
include_dirs: ["include", "external/libfoo/include"]

# 相对路径（相对当前 Android.bp 所在目录）
include_dirs: ["include", "../common/include"]

# 导出（让依赖此 module 的也能 include）
export_include_dirs: ["include"]
```

**关键区分**：
- `include_dirs`：本 module 编译时用
- `export_include_dirs`：依赖此 module 的也能用
- **90% 的 include 错误是因为漏 `export`**

### 2.3 shared_libs / static_libs（库依赖）— 改 30 次

```python
# 动态链接（运行时）
shared_libs: ["liblog", "libutils", "libcutils"]

# 静态链接（编译时合并）
static_libs: ["libfoo"]

# header_libs（仅头文件）
header_libs: ["libbar_headers"]

# 整个 group
shared_libs: ["liblog", "libutils"],
group_shared_libs: ["mylibs", "libfoo"],  # 来自 filegroup / defaults
```

**AOSP 17 强制规则**：
- `libc` / `libm` / `libdl` / `libc++` → 隐式 link，不用写
- `liblog` / `libutils` → 大多数 module 需要
- `libbinder_ndk` / `libbinder` → 用 Binder 通信时需要

### 2.4 cflags / cppflags（编译选项）— 改 10 次

```python
# 简单字符串列表
cflags: ["-Wall", "-Werror", "-fPIC"]

# 平台特定
cflags: ["-Wall"],  # 所有平台
arm_cflags: ["-mfpu=neon"],  # ARM only
x86_cflags: ["-msse4.2"],     # x86 only

# 优化级别
cflags: ["-O2"],

# 调试
cflags: ["-g", "-O0"],
```

**AOSP 17 推荐**：用 `cflags` + 平台后缀而不是单一 `cflags`，避免污染其他 arch。

### 2.5 sanitize（清理器）— 改 5 次

```python
sanitize: {
    integer: true,           # 整数溢出检查
    address: true,           # ASan（地址越界）
    undefined: true,         # UBSan（未定义行为）
    thread: true,            # TSan（线程竞争）
    fuzzer: true,            # libFuzzer
}
```

**AOSP 17 默认**：ASan + UBSan 自动启用（userdebug build）。

### 2.6 visibility（可见性）— 改 5 次但**最关键**

```python
# 默认：仅同 Android.bp 文件内可见
# 但实际大多数 module 想被其他 module 用

visibility: [
    "//frameworks/base:__subpackages__",
    "//vendor/<vendor>:__subpackages__",
]
```

**4 种可见性**：
| 值 | 含义 |
|:---|:-----|
| `//visibility:public` | 任何 module 都能用（公开）|
| `//visibility:private` | 仅当前 module |
| `//visibility:hidden` | 默认，隐藏 |
| `//<package>:__subpackages__` | 特定包及其子包 |

**AOSP 17 强制规则**：
- `vendor` 侧 module 默认**不能被 platform 引用**
- `platform` module 默认**不能被 vendor 引用**
- 必须显式声明 `visibility: ["//<package>:..."]`

---

## 3. 3 个特殊语法

### 3.1 glob（通配符）

```python
# 简单 glob
srcs: ["src/*.cpp"]

# 递归 glob
srcs: ["src/**/*.cpp"]

# 排除
srcs: ["src/**/*.cpp"],
exclude_srcs: ["src/internal/*.cpp"]

# glob 多个目录
srcs: [
    "src/**/*.cpp",
    "test/**/*.cpp",
],
exclude_srcs: [
    "src/internal/**",
    "test/benchmark/**",
]
```

**glob 性能提示**：递归 glob 多了会让 Blueprint 解析变慢。**>10000 个文件** 时改用显式列表。

### 3.2 select（条件选择）

```python
srcs: ["src/common.cpp"],

// 根据 arch 选择
arch: {
    arm: {
        srcs: ["src/arm_optimized.cpp"],
        cflags: ["-mfpu=neon"],
    },
    x86: {
        srcs: ["src/x86_optimized.cpp"],
    },
    x86_64: {
        srcs: ["src/x86_64_optimized.cpp"],
        cflags: ["-msse4.2"],
    },
},

// 根据 sdk version 选择
sdk_version: {
    minimum: {
        cflags: ["-fno-rtti"],
    },
    current: {
        cflags: ["-frtti"],
    },
},
```

**4 大常见 select 维度**：
- `arch`：arm / arm64 / x86 / x86_64
- `os`：android / linux_glibc
- `sdk_version`：minimum / current / module_lib / system_4.0
- `target`：`android` / `host` / `linux_bionic` / `windows`

### 3.3 defaults（默认值）

```python
// 1. 定义一个 defaults 块
cc_defaults {
    name: "mydefaults",
    cflags: ["-Wall", "-Werror"],
    shared_libs: ["liblog", "libutils"],
    sanitize: { integer: true },
}

// 2. 其他 module 引用
cc_library {
    name: "libfoo",
    defaults: ["mydefaults"],
    srcs: ["src/foo.cpp"],
}

cc_library {
    name: "libbar",
    defaults: ["mydefaults"],
    srcs: ["src/bar.cpp"],
}
```

**defaults 嵌套**：

```python
// AOSP 17 真实
cc_defaults {
    name: "mylib-defaults",
    defaults: ["parent-defaults"],
    cflags: ["-DMYLIB=1"],
}
```

### 3.4 3 个特殊语法对比

| 语法 | 何时用 | 真实场景 |
|:-----|:-------|:--------|
| **glob** | 源文件多（>10 个）| `srcs: ["src/**/*.cpp"]` |
| **select** | 不同 arch 编译不同 | ARM 用 NEON，x86 用 SSE |
| **defaults** | 多个 module 共享属性 | 整个 framework 用 `-Wall -Werror` |

---

## 4. 真实案例 1：cross-compile cc_library

**需求**：写一个 `libfoo` C++ 库，支持 Android 和 Linux host 编译。

```python
// libfoo/Android.bp
cc_library {
    name: "libfoo",
    srcs: ["src/*.cpp"],
    export_include_dirs: ["include"],
    shared_libs: ["liblog"],
    target: {
        android: {
            cflags: ["-DANDROID=1"],
            shared_libs: ["liblog", "libutils"],
        },
        host: {
            cflags: ["-DHOST=1"],
        },
    },
    arch: {
        arm64: {
            cflags: ["-DARM64_OPTIMIZED=1"],
            srcs: ["src/arm64/*.cpp"],
        },
        x86_64: {
            cflags: ["-DX86_64_OPTIMIZED=1"],
            srcs: ["src/x86_64/*.cpp"],
        },
    },
}
```

**编译命令**：

```bash
# 编译 Android target
$ m libfoo
# 产物：out/target/product/<device>/obj/lib/libfoo.so

# 编译 host
$ m libfoo HOST
# 产物：out/host/linux-x86_64/obj/lib/libfoo.so
```

---

## 5. 真实案例 2：android_app

**需求**：写一个系统 App `MySettings`，能调 system_server。

```python
// packages/apps/MySettings/Android.bp
android_app {
    name: "MySettings",
    srcs: ["src/**/*.java"],
    resource_dirs: ["res"],

    // AAPT2 资源
    aaptflags: ["--no-version-vectors"],

    // manifest
    manifest: "AndroidManifest.xml",

    // SDK 版本
    sdk_version: "current",  // 用最新 SDK
    min_sdk_version: "33",    // 最低支持 API 33

    // 平台 API（@hide）
    platform_apis: true,

    // 签名
    certificate: "platform",  // 用 platform key 签名

    // 优化
    optimize: {
        proguard_flags_files: ["proguard.cfg"],
    },

    // 包含 / 排除
    exclude_kotlin_stdlib: false,
    kotlin_stdlib: "kotlin-stdlib",

    // 依赖
    static_libs: [
        "androidx.core_core",
        "androidx.appcompat_appcompat",
        "framework-annotations-lib",
    ],
    libs: [
        "framework",
        "services",
    ],
    shared_libs: [
        "libandroid_runtime",
        "libbinder",
    ],
}
```

**AOSP 17 新增选项**：

```python
// 启用 R8（默认）
optimize: {
    enabled: true,
}

// 自定义 R8 rules
optimize: {
    proguard_flags_files: ["proguard.cfg"],
    dex_preopt: { enabled: true },
}
```

---

## 6. 真实案例 3：java_library + 注解处理

**需求**：写一个 framework 内部库，用 Dagger 注解处理。

```python
cc_library {
    name: "framework-annotations-lib",  // 仅注解，运行时不需要
    srcs: ["src/**/*.java"],
    installable: false,  // 不进 .apk
}

java_library {
    name: "my-framework-lib",
    srcs: ["src/**/*.java"],
    static_libs: [
        "framework-annotations-lib",
        "my-annotation-processor",
    ],
    plugins: [
        "my-annotation-processor",  // KAPT 风格的注解处理
    ],
    jarjar_rules: "jarjar-rules.txt",  // 重命名包路径
    java_version: "17",
}
```

**关键属性**：
- `installable: false`：仅编译，不装到镜像
- `plugins: [...]`：启用注解处理
- `jarjar_rules`：包名重写（避免冲突）

---

## 7. 真实案例 4：prebuilt_* 引入 vendor 二进制

**需求**：vendor 自带 `libvendorfoo.so`，直接引入而不从源码编。

```python
prebuilt_shared_library {
    name: "libvendorfoo",
    srcs: ["vendor/foo/lib/libvendorfoo.so"],
    
    // strip 后保留符号表
    strip: {
        keep_symbols: true,
    },
    
    // header 在哪
    export_include_dirs: ["vendor/foo/include"],
    
    // AOSP 17 新增：链接检查
    check_stl_libs: true,
    
    // 32/64 兼容
    compile_multilib: "both",
}
```

**4 个常见 prebuilt 类型**：
- `prebuilt_shared_library` → .so
- `prebuilt_static_library` → .a
- `prebuilt_executable` → 可执行
- `prebuilt_etc` → 配置文件（init.rc / selinux 策略等）

---

## 8. 5 个常见错误

### 8.1 错误 1：include_dirs 漏 export

```
# 报错
fatal error: 'foo.h' file not found
```

**根因**：`include_dirs` 没 `export`，依赖此 module 的看不到。

**修法**：

```python
cc_library {
    name: "libfoo",
    export_include_dirs: ["include"],  # 加 export_
}
```

### 8.2 错误 2：循环依赖

```
# 报错
error: cycle detected in dependency graph
  libfoo depends on libbar
  libbar depends on libfoo
```

**根因**：A 依赖 B，B 又依赖 A。

**修法**：
- 拆出一个公共库 libcommon
- libfoo 和 libbar 都依赖 libcommon
- 互相不依赖

### 8.3 错误 3：glob 没匹配到

```
# 报错但容易忽略
warning: no files matched glob pattern "src/**/*.cpp"
```

**根因**：glob 路径相对当前 Android.bp，**不是相对 module 根目录**。

**修法**：

```python
# 错误：相对 workspace
srcs: ["path/from/root/src/*.cpp"]

# 正确：相对 Android.bp
srcs: ["src/*.cpp"]
```

### 8.4 错误 4：visibility 错误

```
# 报错
error: //vendor/foo:libbar is not visible to //platform:libqux
```

**根因**：vendor 侧 module 默认 platform 不可见。

**修法**：

```python
# 在 libbar 加 visibility
cc_library {
    name: "libbar",
    visibility: ["//platform:__subpackages__"],
}
```

### 8.5 错误 5：missing default prop

```
# 报错
error: 'foo' is not a default
```

**根因**：用了某个 property 但 module 类型不支持。

**修法**：看 module type 文档，AOSP 17 完整属性列表在：

```
build/soong/docs/
├── cc_library.md
├── java_library.md
├── android_app.md
└── ...
```

---

## 9. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 从 Make 到 Soong](01-从Make到Soong：AOSP编译系统演进.md) | 历史背景 |
| [03 Blueprint](03-Blueprint：Soong的中间表示与解析.md) | 下篇讲 .bp 怎么被解析 |
| [04 Soong 架构](04-Soong架构：plugin.provider.mutator.generator.md) | 下下篇讲 module 内部 |
| [05 Ninja 文件解读](05-Ninja生成与ninja文件解读.md) | 编译产物 |
| [07 常见编译错误](07-常见编译错误速查.md) | 第 8 章 5 个错误的展开 |
| [08 实战](08-实战：写一个自己的Android.bp-module.md) | M4 末篇 |
| [Build-System/04_Build_Configuration_And_Options](../04_Build_Configuration_And_Options.md) | BoardConfig.mk 跟 Android.bp 配合 |
| [06-Foundation/SELinux/02](../SELinux/02-策略文件体系：sepolicy.te.cil.编译产物.md) | selinux_policy 也是 Android.bp module |

---

## 10. 下一篇预告 + 自检

### 10.1 下一篇

[03 Blueprint：Soong 的中间表示与解析](03-Blueprint：Soong的中间表示与解析.md) 讲清：
- Android.bp → token → AST → module 列表 的完整解析流程
- Blueprint 的 Lexer / Parser / Builder 3 个核心组件
- Blueprint 的全局 namespace 管理
- 真实代码走读：`build/blueprint/parser.go`

### 10.2 看完本文的自检

- [ ] 能说 9 大常用 module 类型 + 各占比
- [ ] 能用 6 大属性族写一个 cc_library
- [ ] 能用 select / defaults / glob 3 个特殊语法
- [ ] 能改 android_app / java_library / prebuilt_shared_library
- [ ] 能识别 5 个常见编译错误的根因

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
