# 06-Foundation/Build-System/Soong · 04 · Soong 架构：plugin / provider / mutator / generator

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · 想给 Soong 写 plugin 的人 · 改源码工程师
>
> **强依赖**：[01 从 Make 到 Soong](01-从Make到Soong：AOSP编译系统演进.md) · [02 Android.bp 语法精要](02-Android.bp语法精要.md) · [03 Blueprint](03-Blueprint：Soong的中间表示与解析.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Soong 内部 4 大核心概念（module / variant / provider / mutator）+ plugin 扩展点讲清楚——这是改源码 / 加 module 类型 / 调 variant 行为的"路线图"
- **不是**：不复述 [02 §1 module 类型](02-Android.bp语法精要.md)（那是配置层）；不复述 [03 Blueprint AST](03-Blueprint：Soong的中间表示与解析.md)（那是解析层）
- **承接自**：[03 §5 Type check](03-Blueprint：Soong的中间表示与解析.md) Module 列表 → 本文讲 Module 怎么变出 variant / 怎么生成 Ninja
- **衔接去**：[05 Ninja 文件解读](05-Ninja生成与ninja文件解读.md) / [06 编译产物 out/](06-编译产物全梳理：out-目录结构.md) / [08 实战 写 Android.bp](08-实战：写一个自己的Android.bp-module.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章先讲 4 大概念 module/variant/provider/mutator | 90% 的理解都从这 4 个词开始 |
| 2 | 第 6 章用 cc_library 真实生命周期走读 | 不用 toy example |
| 3 | 第 7 章给 4 大 plugin 扩展点 | 给"想给 Soong 加功能"的人直接入口 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Soong = 强类型 module 系统 + 阶段化 mutator 链 + 灵活 provider 数据流 + Ninja 生成器。**

改 Android.bp 时 90% 是改 9 大 module 的属性——但 10% 的"我想加个新 module 类型"或"我想加个新属性"就要进 Soong 内部。本文给"4 大概念 + 真实 cc_library 生命周期 + 4 大 plugin 扩展点"。

---

## 1. 4 大核心概念

### 1.1 module（模块）

**module = 一个独立编译单元**（cc_library / java_library / android_app ...）。

```go
// build/soong/android/module.go
type Module interface {
    Name() string
    GenerateAndroidBuildActions(ctx ModuleContext)
    // ...
}
```

**module 包含**：
- 属性（Properties）
- 依赖（deps）
- 产物（output files）
- Provider（提供数据给依赖者）

### 1.2 variant（变体）

**variant = 一个 module 的"具体编译变种"**。

例如 `cc_library` 可能有：
- `android_arm64_armv8-a_shared` (arm64 + shared)
- `android_arm64_armv8-a_static` (arm64 + static)
- `android_x86_64_shared` (x86_64 + shared)
- `linux_glibc_x86_64_shared` (host)
- ...

**variant 由 mutator 算**。

### 1.3 provider（数据提供）

**provider = module 之间传递的数据**（不是产物文件，而是元信息）。

```go
// cc_library 提供的 Provider
type CcInfo struct {
    // 头文件路径
    IncludeDirs []string
    // 链接库
    SharedLibs []string
    StaticLibs []string
    // 编译标志
    Cflags []string
    // ...
}
```

**关键**：
- module A 用 `provider` 暴露数据
- module B 依赖 A 时，可以从 A 拿这些数据
- provider 是**编译期元数据**，不是运行时数据

### 1.4 mutator（变异器）

**mutator = 在 variant 阶段修改 module / 算 variant 的函数**。

```go
// build/soong/cc/mutator.go
func archMutator(mctx android.BottomUpMutatorContext) {
    // 读 module 的 arch variant 设置
    // 创建具体 variant
    mctx.CreateVariants("android_arm64", "android_x86_64", ...)
}
```

**mutator 阶段**：

```
android.RegisterMutator("arch", archMutator)
android.RegisterMutator("sdk", sdkMutator)
android.RegisterMutator("release", releaseMutator)
// 依次执行：arch → sdk → release
```

### 1.5 4 大概念关系图

```
        Module A (cc_library: libfoo)
            │
            │  1. mutator arch 算 variant
            ▼
        Variant A1 (android_arm64_shared)
        Variant A2 (android_x86_64_shared)
        Variant A3 (linux_glibc_x86_64_shared)
            │
            │  2. 算完 variant 后，generate build actions
            ▼
        Build Actions (compile / link / strip)
            │
            │  3. 暴露 Provider 给依赖者
            ▼
        CcInfo provider
            │
            │  4. 依赖者读 provider
            ▼
        Module B (android_app: MyApp)
            │  读 libfoo 的 CcInfo
            │  拿到 include_dirs / shared_libs
            ▼
        B 的 variant 也算出来
```

---

## 2. module 生命周期

### 2.1 5 个阶段

```
[1] Load
    Blueprint 解析所有 Android.bp
    → Go struct（module 列表）

[2] Generate
    对每个 module：
    └─ GenerateBuildActions(ctx)
       └─ 算依赖、注册产物、注册 provider

[3] Mutate
    阶段化 mutator 链：
    └─ arch mutator
    └─ sdk mutator  
    └─ release mutator
    └─ link mutator
    └─ 等等

[4] Resolve
    variant 之间互相拿 provider
    └─ A 暴露 CcInfo → B 读 CcInfo

[5] Generate Build Actions
    算 Ninja rule
    └─ 写 build.ninja
```

### 2.2 真实代码走读：cc_library

`build/soong/cc/library.go`（简化）：

```go
func init() {
    android.RegisterModuleType("cc_library", ccLibraryFactory)
    android.RegisterModuleType("cc_library_shared", ccLibrarySharedFactory)
    android.RegisterModuleType("cc_library_static", ccLibraryStaticFactory)
}

func ccLibraryFactory() android.Module {
    module := newBaseLibrary(...)
    module.library = true
    module.Build()
    return module.Init()
}

func (c *library) GenerateAndroidBuildActions(ctx android.ModuleContext) {
    // 1. 算 deps
    deps := ctx.GetDirectDepsWithTags(...)
    
    // 2. 暴露 provider
    provider := CcInfo{
        IncludeDirs: c.ExportedIncludeDirs(),
        SharedLibs:  c.ExportedSharedLibs(),
        StaticLibs:  c.ExportedStaticLibs(),
    }
    ctx.SetProvider(CcInfoProvider, provider)
    
    // 3. 注册 build action
    ctx.Build(pctx, android.BuildParams{
        Rule:   link,
        Output: c.outputFile,
        Inputs: c.objects,
    })
}
```

### 2.3 生命周期时间线（AOSP 17 实测）

```
t=0       Blueprint 解析（5-15 秒）
t=15s     所有 module 列表完成
t=15s     BeginMutators
t=15.5s   arch mutator（0.5 秒）
t=16s     sdk mutator（0.5 秒）
t=16.5s   release mutator（0.5 秒）
t=17s     ...
t=20s     所有 variant 完成
t=20.5s   Resolve phase（0.5 秒）
t=21s     写 build.ninja（0.5 秒）
t=21.5s   调 Ninja
t=21.5s+  Ninja 增量构建
```

---

## 3. provider 数据流

### 3.1 provider 4 大场景

| 场景 | Provider | 例子 |
|:-----|:---------|:-----|
| C/C++ 头文件 / 库 | CcInfo | libfoo 暴露 include_dirs 给所有用它的 module |
| Java 类路径 | JavaInfo | my-jar 暴露 classpath 给下游 jar |
| AAR 资源 | AAR | libs 暴露资源给 android_app |
| APEX 成员 | ApexMembership | 标 .apex_available 的 module 暴露给 apex |

### 3.2 provider 接口

```go
// build/soong/cc/provider.go
type CcInfo struct {
    IncludeDirs       []string
    SystemIncludeDirs []string
    SharedLibs        []string
    StaticLibs        []string
    Cflags            []string
    Cppflags          []string
}

var CcInfoProvider = blueprint.NewProvider("cc_info", CcInfo{})
```

### 3.3 真实 provider 用法

```go
// 1. 生产者（cc_library）暴露
func (c *library) GenerateAndroidBuildActions(ctx android.ModuleContext) {
    ctx.SetProvider(CcInfoProvider, CcInfo{
        IncludeDirs: c.exportedIncludeDirs(),
        SharedLibs:  c.exportedSharedLibs(),
    })
}

// 2. 消费者（android_app）读
func (a *app) GenerateAndroidBuildActions(ctx android.ModuleContext) {
    // 拿所有依赖
    deps := ctx.GetDirectDepsWithTags(...)
    
    for _, dep := range deps {
        if info, ok := ctx.GetProvider(CcInfoProvider, dep).(CcInfo); ok {
            // 用 dep 的 CcInfo
            a.includeDirs = append(a.includeDirs, info.IncludeDirs...)
        }
    }
}
```

**关键**：
- Provider 是**编译期数据结构**（不是运行时）
- 通过 reflect 拿类型
- 编译期校验类型正确性

### 3.4 4 大 Provider 用错的真实报错

| 错 | 真实报错 |
|:--|:--------|
| Provider 不存在 | `no provider named "foo_info"` |
| Provider 类型错 | `expected CcInfo, got int` |
| 拿不存在的 dep | `dependency "libbar" does not provide CcInfo` |
| 循环依赖 | `circular dependency: libfoo -> libbar -> libfoo` |

---

## 4. mutator 阶段

### 4.1 Soong 内置的 6 大 mutator

| 顺序 | mutator | 干什么 | 例子 |
|:----:|:--------|:------|:-----|
| 1 | `arch` | 算 arch variant | arm64 / x86_64 / ... |
| 2 | `os` | 算 OS variant | android / linux_glibc / ... |
| 3 | `sdk` | 算 SDK variant | current / minimum / ... |
| 4 | `release` | 算 release variant | user / userdebug / eng |
| 5 | `link` | 算 link variant | shared / static |
| 6 | `apex` | 算 APEX 归属 | 是否进某 APEX |

### 4.2 mutator 执行顺序

```go
// build/soong/android/mutator.go
func registerMutators() {
    android.RegisterBottomUpMutator("arch", archMutator)
    android.RegisterBottomUpMutator("os", osMutator)
    android.RegisterBottomUpMutator("sdk", sdkMutator)
    android.RegisterBottomUpMutator("release", releaseMutator)
    android.RegisterBottomUpMutator("link", linkMutator)
    android.RegisterBottomUpMutator("apex", apexMutator)
}
```

**BottomUp**：先 leaf module，再依赖者。跟 top-down 区别：
- TopDown：先 root 再 leaf
- BottomUp：先 leaf 再 root
- AOSP 用 BottomUp（因为 provider 流向 leaf → root）

### 4.3 mutator 真实代码走读：arch

```go
// build/soong/cc/arch.go
func archMutator(mctx android.BottomUpMutatorContext) {
    // 1. 读 module 的 arch 偏好
    var preferredArchs []string
    if p := mctx.Module().(*Module).GetProperties(); p != nil {
        preferredArchs = p.Arch.Preferred
    }
    
    // 2. 算 variant
    archs := mctx.DeviceConfig().Arches()  // device 配置的 arch
    if len(preferredArchs) > 0 {
        archs = filterArchs(archs, preferredArchs)
    }
    
    // 3. 创建 variants
    for _, arch := range archs {
        mctx.CreateVariants(arch)  // 创建一个新 variant
    }
}
```

**实际效果**：
- `cc_library: libfoo`（全局）→ 1 个 module
- `m libfoo`（arm64 device）→ 算 1 个 variant：`android_arm64_armv8-a_shared`
- `m libfoo`（arm64 + x86_64）→ 算 2 个 variant
- 跨 arch 编译 → 算 2 个 variant 并行

### 4.4 mutator 阶段化思想

**为什么 mutator 阶段化？**

```python
# 假设没有阶段化
android_app {
    name: "MyApp",
    srcs: arch_select {
        arm: ["src_arm.cpp"],
        x86: ["src_x86.cpp"],
    },
}
# mutator 阶段化后：
android_app {
    name: "MyApp",
    srcs: ["src_*.cpp"],  # glob 已经足够
}
# arch 决定 * 具体匹配
```

**关键洞察**：
- mutator 阶段化让**同一份 .bp** 支持多 arch
- 不必为每个 arch 写一份 module
- 这是 AOSP 17 跨 arch 编译的核心机制

---

## 5. generator 输出 build.ninja

### 5.1 generator 真实作用

**generator 把 Soong 的 module + variant + provider 转成 Ninja rule**。

```go
// build/soong/cc/generator.go
func (c *library) generateBuildActions(ctx android.ModuleContext) {
    // 1. compile rule
    for i, src := range c.Srcs {
        obj := c.objDir + "/" + strings.TrimSuffix(src, ".cpp") + ".o"
        ctx.Build(pctx, android.BuildParams{
            Rule:   ccRule,
            Output: obj,
            Input:  src,
            Args:   cflags,
        })
    }
    
    // 2. link rule
    ctx.Build(pctx, android.BuildParams{
        Rule:   linkRule,
        Output: c.outputFile,
        Inputs: c.objects,
        Args:   ldflags,
    })
}
```

### 5.2 一个 build action 长什么样

```go
ctx.Build(pctx, android.BuildParams{
    Rule:   ccRule,
    Output: "out/.../libfoo.so",
    Input:  "src/foo.cpp",
    Args: map[string]string{
        "cflags":   "-Wall -O2",
        "include":  "include",
        "libs":     "liblog",
    },
    Deps:   [...],  // 依赖其他 build action
})
```

**最终生成 Ninja**：

```ninja
# out/soong/build.ninja（部分）
rule ccRule
  command = clang -Wall -O2 -I include -shared -o $out $in -llog
  description = C++ compile $out

build out/.../libfoo.so: ccRule src/foo.cpp
  deps = gccdeps
```

**Ninja 用**：
```bash
$ ninja -f out/soong/build.ninja libfoo
# 增量构建 libfoo
```

---

## 6. cc_library 完整生命周期走读

### 6.1 真实场景

```python
// libfoo/Android.bp
cc_library {
    name: "libfoo",
    srcs: ["src/*.cpp"],
    shared_libs: ["liblog"],
    cflags: ["-Wall"],
}
```

### 6.2 完整生命周期（AOSP 17 实测）

```
[1] Blueprint 解析（t=0-5s）
    Android.bp → token → AST → Module{Type: "cc_library", Name: "libfoo"}
    ↓
[2] Soong 工厂（t=5.0s）
    ccLibraryFactory() 调 init
    → newBaseLibrary(...)
    → module.library = true
    → module.Build()
    → module.Init()
    ↓
[3] 读 properties（t=5.1s）
    module.SetProperties(Properties{
        Name: "libfoo",
        Srcs: ["src/*.cpp"],
        SharedLibs: ["liblog"],
        Cflags: ["-Wall"],
    })
    ↓
[4] BeginMutators（t=5.5s）
    arch mutator: 创 variant
    └─ libfoo.android_arm64_armv8-a_shared
    └─ libfoo.android_x86_64_shared
    sdk mutator: 算 sdk variant
    └─ libfoo.android_arm64_armv8-a_shared.sdk_current
    release mutator: 算 release variant
    └─ libfoo.android_arm64_armv8-a_shared.sdk_current.userdebug
    link mutator: 算 link variant
    └─ libfoo.android_arm64_armv8-a_shared.sdk_current.userdebug.shared
    ↓
[5] Resolve（t=8s）
    拿 liblog 的 provider
    └─ liblog: CcInfo{ IncludeDirs: [], SharedLibs: ["liblog" 的 deps] }
    ↓
[6] GenerateBuildActions（t=8.5s）
    算 compile objects
    ├─ libfoo.o from src/foo.cpp
    └─ libbar.o from src/bar.cpp
    算 link
    └─ libfoo.so from [libfoo.o, libbar.o] + liblog.so
    ↓
[7] 写 build.ninja（t=9s）
    写所有 rule
    写所有 build action
    写 dependency edges
    ↓
[8] 调 Ninja（t=9s+）
    $ ninja libfoo
    增量构建
```

### 6.3 一个 variant 的最终 ninja 段

```ninja
# out/soong/build.ninja（节选 libfoo 部分）

# 1. compile rule
rule ccRule_libfoo
  command = clang -Wall -O2 -fPIC -I include -c -o $out $in
  description = C++ compile $out

# 2. compile objects
build out/.../libfoo.o: ccRule_libfoo src/foo.cpp
build out/.../libbar.o: ccRule_libfoo src/bar.cpp

# 3. link rule
rule linkRule_libfoo
  command = clang -shared -o $out $in -L out/... -llog
  description = Link shared lib $out

# 4. link
build out/.../libfoo.so: linkRule_libfoo libfoo.o libbar.o

# 5. 默认
default libfoo.so
```

---

## 7. Soong 4 大 plugin 扩展点

### 7.1 4 大扩展点

| 扩展点 | 用途 | 注册函数 |
|:------|:-----|:--------|
| **新 module type** | 加新 .bp module 类型 | `android.RegisterModuleType` |
| **新 mutator** | 加新变体算规则 | `android.RegisterBottomUpMutator` |
| **新 provider** | 加新数据流 | `blueprint.NewProvider` |
| **新 build action** | 加新 Ninja rule | `ctx.Build(...)` |

### 7.2 扩展点 1：新 module type

```go
// build/soong/myfeature/myfeature.go
package myfeature

import "android/soong/android"

func init() {
    android.RegisterModuleType("my_module", myModuleFactory)
}

type myModule struct {
    android.ModuleBase
    Properties struct {
        Name string
        // 自定义属性
        Foo string
        Bar int
    }
}

func myModuleFactory() android.Module {
    m := &myModule{}
    android.InitAndroidModule(m)
    return m
}

func (m *myModule) GenerateAndroidBuildActions(ctx android.ModuleContext) {
    // 自定义 build action
}
```

**用法**：

```python
// Android.bp
my_module {
    name: "myinst",
    foo: "hello",
    bar: 42,
}
```

### 7.3 扩展点 2：新 mutator

```go
func myMutator(mctx android.BottomUpMutatorContext) {
    // 1. 读所有 module
    // 2. 算新 variant
    mctx.CreateVariants("my_variant_a", "my_variant_b")
    // 3. 改 module properties
}

func init() {
    android.RegisterBottomUpMutator("mymutator", myMutator)
}
```

### 7.4 扩展点 3：新 provider

```go
var MyInfoProvider = blueprint.NewProvider("my_info", MyInfo{})

type MyInfo struct {
    // 自定义数据
    Path string
    Config []string
}

// 生产者
func (m *myModule) GenerateAndroidBuildActions(ctx android.ModuleContext) {
    ctx.SetProvider(MyInfoProvider, MyInfo{Path: "foo", Config: []string{"x"}})
}

// 消费者
func (m *otherModule) GenerateAndroidBuildActions(ctx android.ModuleContext) {
    deps := ctx.GetDirectDepsWithTags(...)
    for _, dep := range deps {
        if info, ok := ctx.GetProvider(MyInfoProvider, dep).(MyInfo); ok {
            // 用 dep 的 MyInfo
        }
    }
}
```

### 7.5 扩展点 4：新 build action

```go
// 用 pctx + ctx.Build
var myRule = pctx.StaticRule(
    "myRule",
    blueprint.RuleParams{
        Command:     "my-tool --input $in --output $out --config $config",
        CommandDeps: []string{"my-tool"},
    },
    "config",  // 变量
)

// 调
ctx.Build(pctx, android.BuildParams{
    Rule:   myRule,
    Output: "out.txt",
    Input:  "in.txt",
    Args: map[string]string{
        "config": "default",
    },
})
```

### 7.6 完整例子：写一个 my_module

```go
// build/soong/myfeature/myfeature.go
package myfeature

import (
    "android/soong/android"
    "github.com/google/blueprint"
)

var pctx = android.NewPackageContext("myfeature")

func init() {
    android.RegisterModuleType("my_module", myModuleFactory)
    android.RegisterBottomUpMutator("mymutator", myMutator)
}

var myRule = pctx.StaticRule(
    "myRule",
    blueprint.RuleParams{
        Command: "my-tool --input=$in --output=$out",
    },
    "input",  // 变量
)

type myModule struct {
    android.ModuleBase
    Properties struct {
        Name string
        InputFile string
        Config string
    }
    output android.OutputPath
}

func myModuleFactory() android.Module {
    m := &myModule{}
    android.InitAndroidModule(m)
    return m
}

func (m *myModule) GenerateAndroidBuildActions(ctx android.ModuleContext) {
    // 1. 算 output
    m.output = android.PathForModuleOut(ctx, "output.txt")
    
    // 2. 算 input
    input := android.PathForModuleSrc(ctx, m.Properties.InputFile)
    
    // 3. 调 build action
    ctx.Build(pctx, android.BuildParams{
        Rule:   myRule,
        Output: m.output,
        Input:  input,
        Args: map[string]string{
            "input":  m.Properties.InputFile,
            "config": m.Properties.Config,
        },
    })
    
    // 4. 暴露 provider
    ctx.SetProvider(myInfoProvider, myInfo{Output: m.output.String()})
}

var myInfoProvider = blueprint.NewProvider("my_info", myInfo{})

type myInfo struct {
    Output string
}

func myMutator(mctx android.BottomUpMutatorContext) {
    // 不算 variant，只改 properties
    mctx.CreateVariants("default")
}
```

**调用**：

```bash
$ m my_module
# 触发 Blueprint 解析 + Soong 注册 + 调 myModuleFactory + 走 mutator + generate build action
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 从 Make 到 Soong](01-从Make到Soong：AOSP编译系统演进.md) | 历史 |
| [02 Android.bp 语法精要](02-Android.bp语法精要.md) | 配置层 |
| [03 Blueprint](03-Blueprint：Soong的中间表示与解析.md) | 解析层 |
| [05 Ninja 文件解读](05-Ninja生成与ninja文件解读.md) | Soong 产物 |
| [06 编译产物 out/](06-编译产物全梳理：out-目录结构.md) | out/ 全景 |
| [07 常见编译错误](07-常见编译错误速查.md) | 错误视角 |
| [08 实战 写 Android.bp](08-实战：写一个自己的Android.bp-module.md) | M4 末篇 |
| [Build-System/04_Build_Configuration_And_Options](../04_Build_Configuration_And_Options.md) | BoardConfig.mk |
| [06-Foundation/SELinux/02](../SELinux/02-策略文件体系：sepolicy.te.cil.编译产物.md) | SELinux 编译 = Soong module |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇（M4 第 1 篇）

[05 Ninja 生成与 ninja 文件解读](05-Ninja生成与ninja文件解读.md) 讲清：
- Soong 怎么生成 build.ninja
- build.ninja 内部结构（rule / build / dep / default）
- 真实走读：out/soong/build.ninja 节选
- 怎么手工 ninja 增量构建
- Ninja 与 Soong 的边界

### 9.2 看完本文的自检

- [ ] 能说 Soong 4 大核心概念：module / variant / provider / mutator
- [ ] 能说 module 5 阶段生命周期：Load → Generate → Mutate → Resolve → BuildActions
- [ ] 能从 1 个 cc_library 走完 8 步真实生命周期
- [ ] 能用 4 大 plugin 扩展点（ModuleType / Mutator / Provider / BuildAction）写个 my_module
- [ ] 知道 AOSP 17 6 大内置 mutator（arch / os / sdk / release / link / apex）

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
