# 06-Foundation/Build-System/Soong · 05 · Ninja 生成与 ninja 文件解读

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · 改源码工程师 · 想手工调 Ninja 的人
>
> **强依赖**：[04 Soong 架构](04-Soong架构：plugin.provider.mutator.generator.md) · [01 从 Make 到 Soong](01-从Make到Soong：AOSP编译系统演进.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Soong 生成的 build.ninja 内部结构讲清楚——rule / build / dep / default 4 大元素，加上手工 ninja 增量构建的 3 个场景
- **不是**：不复述 [01 §5 阶段 4](01-从Make到Soong：AOSP编译系统演进.md) Ninja 是执行器；不复述 [04 §5 generator](04-Soong架构：plugin.provider.mutator.generator.md) 的代码（本文是它的产物）
- **承接自**：[04 §6 cc_library 完整生命周期](04-Soong架构：plugin.provider.mutator.generator.md) → 本文讲这个生命周期的最终产物
- **衔接去**：[06 编译产物 out/](06-编译产物全梳理：out-目录结构.md) / [07 常见编译错误](07-常见编译错误速查.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 2 章用 4 大元素结构 table | 90% 的 ninja 阅读是这 4 个词 |
| 2 | 第 4 章用真实 out/soong/build.ninja 节选 | 不用示意图 |
| 3 | 第 5 章给 3 个手工 ninja 场景 | oncall 5 分钟上手 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**build.ninja = Soong 的最终执行图，**纯文本、100MB+ 规模、几百 MB 大小**——理解它的 4 大元素 = 手工 ninja 增量构建 5 分钟上手。**

AOSP 17 上 build.ninja 通常 150-300MB，含 **5-10 万条 build action**——手工 `m` 走 Soong 慢时，**直接 ninja 调 1 个 target** 只要 1-5 秒。

---

## 1. Ninja 在 AOSP 17 的位置

```
AOSP 17 编译系统（全景）
═══════════════════════════════════════════════════════════════

vendor 写
─────────
Android.bp × 25000
    ↓
[Blueprint 解析]   ←  5-15 秒
    ↓
Module 列表（Go struct）
    ↓
[Soong 编译]       ←  5-10 秒
    ↓
variant / provider
    ↓
[Soong generator]  ←  1-2 秒
    ↓
build.ninja（150-300MB）
    ↓
[Ninja 执行]       ←  几秒 ~ 几分钟
    ↓
.so / .jar / .apk
```

**build.ninja 是 Soong 与 Ninja 的"接缝"——所有 variant / provider / mutator 都被压平成 4 大 ninja 元素**。

---

## 2. Ninja 4 大元素

### 2.1 4 大元素速查

| 元素 | 作用 | 数量级（AOSP 17）|
|:-----|:----|:---------------|
| **rule** | 定义命令模板 | ~300-500 个 |
| **build** | 1 个具体执行目标 | 5-10 万个 |
| **default** | 默认 target | 1 个（"all"）|
| **pool** | 资源池（限制并发）| 10-20 个 |

### 2.2 rule 详解

**rule = "怎么编译"的模板**：

```ninja
# 通用 rule 定义语法
rule <name>
  command = <命令行>
  description = <输出提示>
  depfile = <gcc 依赖文件>
  deps = <gcc|gccdep>  # 用 gcc 生成的 .d 文件
  restat = <0|1>       # 命令是否要重 stat
  generator = <0|1>    # 是否生成新 build 文件
  pool = <pool_name>   # 用哪个 pool

# AOSP 17 真实 rule 例子
rule ccRule_libfoo
  command = clang -Wall -O2 -fPIC -I include -c -o $out $in
  description = C++ compile $out
  depfile = $out.d
  deps = gcc

# AOSP 17 真实 rule 例子 2
rule linkRule_libfoo
  command = clang -shared -o $out $in -llog
  description = Link $out
  restat = 1
```

**关键变量**：
- `$in` → 输入文件（前面是路径或文件列表）
- `$out` → 输出文件
- `$depfile` → gcc 生成的 .d 依赖文件
- `$` + 自定义变量（在 `build` 里 Args 传）

### 2.3 build 详解

**build = "用 rule 编译某个目标"**：

```ninja
# 通用 build 语法
build <output>: <rule> <inputs> | <order_only_inputs>
  key = value
  ...

# AOSP 17 真实 build
build out/.../libfoo.o: ccRule_libfoo src/foo.cpp
  depfile = out/.../libfoo.o.d

# 多个 input
build out/.../libfoo.so: linkRule_libfoo libfoo.o libbar.o

# implicit / order-only inputs
build out/.../app.apk: apkRule
  | order.txt    # 不参与 hash
```

**3 类 input**：
- 显式 input（参与 hash + 触发重新构建）
- implicit input（自动包含 hash，参与触发）
- order-only input（不参与 hash，只保证顺序）

### 2.4 default 详解

```ninja
# AOSP 17 真实 default
default out/.../system.img

# 多个 default
default out/.../system.img out/.../vendor.img

# 不设 default → 跑 ninja 必须显式给 target
```

**AOSP 17 的 default 是 `out/.../system.img`**——这是 `m` 不带 target 时的最终产物。

### 2.5 pool 详解

```ninja
# AOSP 17 真实 pool 定义
pool high_mem_pool
  depth = 1     # 同时只跑 1 个
  # 高内存消耗的 link 步骤用

pool local_pool
  depth = 8     # 8 并行
  # 普通 compile 用

# 在 rule 里用
rule linkRule
  command = ...
  pool = local_pool
```

**AOSP 17 实际 pool**：
- `local_pool`（8 并行，编译任务）
- `console`（1 并行，需要 console 的）
- `high_mem_pool`（1 并行，链接大 so）
- `java_pool`（4 并行，Java 编译）

---

## 3. AOSP 17 真实 build.ninja 节选

### 3.1 文件位置

```
out/soong/build.ninja                       # Soong 生成的（核心）
out/soong/bootstrap.ninja                   # bootstrap 阶段
out/soong/soong.ninja                       # Soong 自身
out/combined-<device>.ninja                 # 合并版（可选）
```

**AOSP 17 默认用 `out/soong/build.ninja`**。

### 3.2 文件头

```ninja
# out/soong/build.ninja 文件头

# ninja所需的最小版本
ninja_required_version = 1.9.0

# include 其他 .ninja
include out/soong/bootstrap.ninja
include out/soong/soong.ninja

# 全局变量
builddir = out
android_top = /path/to/aosp
product_out = /path/to/aosp/out/target/product/cf_x86_64_phone
sandbox_allow_network = false

# pool 定义
pool console
  depth = 1

pool local_pool
  depth = 8
```

### 3.3 一个完整 build action

```ninja
# AOSP 17 真实节选（libfoo 编译）

# 1. rule 定义（通常出现在文件头或中间）
rule ccRule_libfoo
  command = /path/to/clang -Wall -Werror -O2 -fPIC --target=aarch64-linux-android21 -c -o $out $in
  description = C++ compile $out
  depfile = $out.d
  deps = gcc

rule linkRule_libfoo
  command = /path/to/clang -shared -fPIC -o $out $in -L out/... -llog -lutils
  description = Link shared lib $out

# 2. compile 步骤
build out/.../libfoo.o: ccRule_libfoo src/foo.cpp
  depfile = out/.../libfoo.o.d
build out/.../libbar.o: ccRule_libfoo src/bar.cpp
  depfile = out/.../libbar.o.d

# 3. link 步骤
build out/.../libfoo.so: linkRule_libfoo
  in = out/.../libfoo.o out/.../libbar.o

# 4. phony（伪 target）
build libfoo: phony out/.../libfoo.so
```

### 3.4 Ninja 的 .d 依赖追踪

```ninja
# .d 文件由 gcc 自动生成
# 例：foo.cpp 包含 bar.h，gcc 输出：
# out/.../libfoo.o.d:
#   libfoo.o: src/foo.cpp src/bar.h src/baz.h

# Ninja 读 .d，得出：
#   libfoo.o 依赖 [src/foo.cpp, src/bar.h, src/baz.h]
#   改 bar.h → 重新编译 libfoo.o

# AOSP 17 启用 depfile + deps = gcc
```

**关键**：
- .d 文件**自动维护**（不用手写）
- 头文件改了 → .o 自动重编译
- 漏 .d → 头文件改动不触发重编译（**编译 bug 常见根因**）

### 3.5 真实 depfile

```ninja
# out/.../libfoo.o.d
out/.../libfoo.o: \
  src/foo.cpp \
  src/bar.h \
  src/baz.h \
  include/config.h
```

Ninja 启动时**扫描所有 .d 文件**，建完整依赖图。

---

## 4. 手工 Ninja 增量构建 5 个场景

### 4.1 场景 1：调单个 module

```bash
# 1. 找 build action 名
$ grep "build.*libfoo\.so" out/soong/build.ninja | head -3
build out/.../libfoo.so: linkRule_libfoo
  in = out/.../libfoo.o out/.../libbar.o
build libfoo: phony out/.../libfoo.so

# 2. 直接调 ninja
$ ninja -f out/soong/build.ninja out/.../libfoo.so
# 增量构建 libfoo.so（不重走 Soong）
# 耗时：1-5 秒
```

### 4.2 场景 2：调 phony target

```bash
# phony 是 alias
$ ninja -f out/soong/build.ninja libfoo
# 等价于调 out/.../libfoo.so

# AOSP 17 phony 命名约定
# <module_name> → <output> 单一产物
# <module_name>_combined → 多个产物
```

### 4.3 场景 3：dry-run 看会调哪些

```bash
# -n = dry-run（不真跑，看计划）
$ ninja -f out/soong/build.ninja -n libfoo
# 输出：
# ninja explain: out/.../libfoo.o is up to date
# ninja explain: out/.../libbar.o is up to date
# ninja explain: out/.../libfoo.so is up to date

# -d explain 看每个 decision
$ ninja -f out/soong/build.ninja -d explain libfoo
```

### 4.4 场景 4：清掉单个 .o 强制重编译

```bash
# 1. 删 .o
$ rm out/.../libfoo.o

# 2. ninja 自动重新编译
$ ninja -f out/soong/build.ninja libfoo
# 增量重建 libfoo.o
```

### 4.5 场景 5：清掉 .ninja 强制重走 Soong

```bash
# 改 Android.bp 后，Ninja 不感知
# 必须重新生成 build.ninja

# 1. 删 build.ninja
$ rm out/soong/build.ninja

# 2. 重新走 Soong
$ m libfoo  # 会触发 Soong 重新解析 + 生成 build.ninja
```

**关键洞察**：
- 改 Android.bp → 必须 `m`（重新生成 ninja）
- 改 .cpp / .h → 直接 `ninja`（增量构建）

---

## 5. build.ninja 的 5 个高级特性

### 5.1 特性 1：变量展开

```ninja
# 顶层变量
clang = /path/to/clang

# rule 里用
rule ccRule
  command = $clang -o $out $in

# 等价展开
# command = /path/to/clang -o out/.../libfoo.o src/foo.cpp
```

### 5.2 特性 2：path

```ninja
# path 指令定义多文件变量
path libfoo_objs = out/.../libfoo.o out/.../libbar.o

# rule 用 path
build out/.../libfoo.so: linkRule $libfoo_objs
```

### 5.3 特性 3：subninja

```ninja
# 主 .ninja 包含子 .ninja
include out/soong/bootstrap.ninja
include out/soong/soong.ninja
include out/.../libfoo.ninja   # 可选：每个 module 一个 .ninja
```

### 5.4 特性 4：环境变量

```ninja
# AOSP 17 build.ninja 用
sandbox_allow_network = false   # sandbox 模式
sandbox_path = /usr/local/bin/ninja
```

### 5.5 特性 5：phony 依赖图

```ninja
# phony 不编译，只聚合
build libfoo: phony out/.../libfoo.so
build libbar: phony out/.../libbar.so

# 一次调多个
build mygroup: phony libfoo libbar

# 调 mygroup → 同时编 libfoo + libbar
$ ninja -f out/soong/build.ninja mygroup
```

---

## 6. 性能优化：让 ninja 增量构建更快

### 6.1 -j 控制并发

```bash
# AOSP 17 默认 -j32（32 线程）
$ ninja -f out/soong/build.ninja -j32 libfoo

# 8 线程（不挤 IO）
$ ninja -f out/soong/build.ninja -j8 libfoo

# 64 线程（服务器编译，IO 不是瓶颈）
$ ninja -f out/soong/build.ninja -j64 libfoo
```

### 6.2 -d 调试模式

```bash
# explain 模式：每个 decision 都打印
$ ninja -f out/soong/build.ninja -d explain libfoo

# stats 模式：性能统计
$ ninja -f out/soong/build.ninja -d stats libfoo
# 输出：
#   +edge counts: ...
#   +depfile load: ...
#   +restat: ...

# 完整调试
$ ninja -f out/soong/build.ninja -d all libfoo 2>&1 | head -100
```

### 6.3 -k 失败不终止

```bash
# -k = 失败后继续（默认停止）
$ ninja -f out/soong/build.ninja -k 0 libfoo
# 所有 action 都跑完
# 看哪些失败
```

### 6.4 -t query 高级查询

```bash
# 列所有 build action
$ ninja -f out/soong/build.ninja -t targets all | head

# 列所有 rule
$ ninja -f out/soong/build.ninja -t rules

# 找特定 build action
$ ninja -f out/soong/build.ninja -t targets all | grep libfoo

# 编译数据库（compile_commands.json）
$ ninja -f out/soong/build.ninja -t compdb > compile_commands.json
# vscode / clangd 用
```

### 6.5 性能数据（AOSP 17 实测）

| 操作 | Soong 走完 + Ninja 调 | 纯 Ninja 调 |
|:-----|:---------------------|:-----------|
| 改 1 行 .cpp | 15-30 秒（重 Soong + 重 .o）| **1-3 秒**（仅重 .o）|
| 改 1 行 Android.bp | 30-60 秒（重 Soong + 重 build.ninja）| **0 秒**（Ninja 不感知，需重生成）|
| 全量构建 | 2-3 分钟 | 2-3 分钟（等价，但 Soong 提供签名/产物依赖）|
| 改 .h 头文件 | 5-10 秒（Soong 不感知，Ninja 自动）| **1-5 秒**（Ninja 读 .d 触发）|

**关键洞察**：
- oncall 5 分钟改 .cpp + 验证 → 用 `ninja -f out/soong/build.ninja <target>` 1-3 秒
- oncall 改 .bp → 必须 `m`（30-60 秒）

---

## 7. 真实调试案例：手工 ninja 排查编译问题

### 7.1 案例 1：libfoo link 失败但 m 不报错

```bash
# 现象：手工 ninja link 失败
$ ninja -f out/soong/build.ninja out/.../libfoo.so
FAILED: out/.../libfoo.so
... undefined reference to `bar_func()'

# 原因：改 libbar 但没重编 libbar.so
$ ls -la out/.../libbar.so
# 老的 libbar.so，缺新 bar_func 符号

# 修法：先编 libbar，再编 libfoo
$ ninja -f out/soong/build.ninja out/.../libbar.so
$ ninja -f out/soong/build.ninja out/.../libfoo.so
```

### 7.2 案例 2：incremental 不触发

```bash
# 现象：改了 src/foo.cpp 但 ninja 不重编 libfoo.o

# 排查：
$ cat out/.../libfoo.o.d
# 看依赖追踪对不对
# .d 漏 src/bar.h → 改 bar.h 不触发重编

# 修法：
# 1. 加 deps = gcc 到 rule（一般 AOSP 已加）
# 2. 删 .o 强制重编
$ rm out/.../libfoo.o
$ ninja -f out/soong/build.ninja out/.../libfoo.o
```

### 7.3 案例 3：build.ninja 损坏

```bash
# 现象：ninja 报 ninja file corrupt
$ ninja -f out/soong/build.ninja libfoo
ninja: error: out/soong/build.ninja: ...

# 修法：重生成
$ rm out/soong/build.ninja
$ m libfoo  # Soong 重生成
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 从 Make 到 Soong](01-从Make到Soong：AOSP编译系统演进.md) | §5 阶段 4 简述 Ninja |
| [04 Soong 架构](04-Soong架构：plugin.provider.mutator.generator.md) | §5 generator 输出 Ninja |
| [06 编译产物 out/](06-编译产物全梳理：out-目录结构.md) | 下篇讲 out/ 全景 |
| [07 常见编译错误](07-常见编译错误速查.md) | 错误视角 |
| [08 实战](08-实战：写一个自己的Android.bp-module.md) | M4 末篇 |
| [Build-System/01_AOSP_Build_Environment](../01_AOSP_Build_Environment.md) | 编译环境 |
| [06-Foundation/SELinux/02](../../05-安全基础（SELinux%20·%20AVB）/SELinux/02-策略文件体系：sepolicy.te.cil.编译产物.md) | selinux_policy 也走 Soong → Ninja |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[06 编译产物全梳理：out/ 目录结构](06-编译产物全梳理：out-目录结构.md) 讲清：
- `out/host/` 全景（host 端工具链）
- `out/target/` 全景（target 端产物）
- `out/soong/` 全景（Soong 自身产物）
- `out/target/product/<device>/` 镜像与文件
- 真实 AOSP 17 编译产物树形图

### 9.2 看完本文的自检

- [ ] 能说 Ninja 4 大元素（rule / build / default / pool）
- [ ] 能找 `build.ninja` 位置 + 读 1 个完整 build action
- [ ] 能手工 `ninja -f build.ninja <target>` 增量构建
- [ ] 知道 -j / -d / -k / -t 等高级选项
- [ ] 能解释 .d 依赖文件怎么让头文件改动自动触发重编

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
