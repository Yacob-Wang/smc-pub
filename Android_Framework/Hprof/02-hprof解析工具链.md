# 02-hprof 解析工具链

> **本篇定位**:系列第 2 篇(工具方法论)。读完能用对工具解析 hprof,理解工具间的差异,知道什么场景用什么工具。
>
> **强依赖**:[01-hprof 原理与文件格式](01-hprof原理与文件格式.md)(本篇会引用 01 §3 的格式讲解)
>
> **不重复内容**:
> - hprof 格式细节 → 见 [01 §3-§5](01-hprof原理与文件格式.md)
> - perfetto_hprof 工具用法 → 见 [03](03-perfetto_hprof详解.md)
> - 具体泄漏案例 → 见 [04](04-内存泄漏典型案例与排查SOP.md)
>
> **基线**:AOSP `android-14.0.0_r1` + LeakCanary `2.14+` + Eclipse MAT `1.12.0+` + Android Studio Hedgehog
> **风格**:源码密度 ~15%,重点放在决策树 + 工具矩阵 + 视角分析
>
> **目录位置**:`Android_Framework/Hprof/`
> **上一篇**:[01-hprof 原理与文件格式](01-hprof原理与文件格式.md)
> **下一篇**:[03-perfetto_hprof 详解](03-perfetto_hprof详解.md)

---

## 目录

- [1. 工具全景:6 大 hprof 解析工具的能力矩阵](#1-工具全景6-大-hprof-解析工具的能力矩阵)
- [2. hprof-conv:Android SDK 自带格式转换器](#2-hprof-convandroid-sdk-自带格式转换器)
  - [2.1 转换原理:Android binary HPROF → 标准 Java HPROF](#21-转换原理android-binary-hprof--标准-java-hprof)
  - [2.2 命令详解与典型用法](#22-命令详解与典型用法)
  - [2.3 工程坑位图:hprof-conv 失败 5 大原因](#23-工程坑位图hprof-conv-失败-5-大原因)
- [3. LeakCanary:自动化泄漏检测](#3-leakcanary自动化泄漏检测)
  - [3.1 工作原理:Shark 引擎 + WeakReference + GC Root 追踪](#31-工作原理shark-引擎--weakreference--gc-root-追踪)
  - [3.2 接入实战:Debug + Release 灰度策略](#32-接入实战debug--release-灰度策略)
  - [3.3 报告解读:4 段式 + 引用链 + retained size](#33-报告解读4-段式--引用链--retained-size)
  - [3.4 工程坑位图:LeakCanary 误报 / 漏报 5 大场景](#34-工程坑位图leakcanary-误报--漏报-5-大场景)
- [4. Eclipse MAT:离线深度分析之王](#4-eclipse-mat离线深度分析之王)
  - [4.1 离线分析 vs 在线分析:为什么 MAT 适合大文件](#41-离线分析-vs-在线分析为什么-mat-适合大文件)
  - [4.2 核心视图:Dominator Tree / Leak Suspects / OQL](#42-核心视图dominator-tree--leak-suspects--oql)
  - [4.3 工程坑位图:MAT 加载 1GB+ hprof OOM](#43-工程坑位图mat-加载-1gb-hprof-oom)
- [5. hprof-slice / jhat / 自研工具](#5-hprof-slice--jhat--自研工具)
  - [5.1 hprof-slice:hprof 命令行切片工具](#51-hprof-slicehprof-命令行切片工具)
  - [5.2 jhat:JDK 自带 HTTP 分析器](#52-jhatjdk-自带-http-分析器)
  - [5.3 自研工具:解析脚本 + SQL 查询](#53-自研工具解析脚本--sql-查询)
- [6. 工具选型决策树](#6-工具选型决策树)
  - [6.1 遇到 X 问题用 Y 工具](#61-遇到-x-问题用-y-工具)
  - [6.2 工具组合拳:5 阶段流水线](#62-工具组合拳5-阶段流水线)
- [7. 实战:从 hprof 到根因的完整链路](#7-实战从-hprof-到根因的完整链路)
  - [7.1 案例背景](#71-案例背景)
  - [7.2 阶段 1:dump](#72-阶段-1dump)
  - [7.3 阶段 2:转换](#73-阶段-2转换)
  - [7.4 阶段 3:分析](#74-阶段-3分析)
  - [7.5 阶段 4:定位](#75-阶段-4定位)
  - [7.6 阶段 5:修复](#76-阶段-5修复)
- [8. 总结:架构师视角的 5 条 Takeaway](#8-总结架构师视角的-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:LeakCanary 误报/漏报排查清单](#附录-bleakcanary-误报漏报排查清单)
- [附录 C:量化数据自检表](#附录-c量化数据自检表)
- [附录 D:工程基线表](#附录-d工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. 工具全景:6 大 hprof 解析工具的能力矩阵

| 工具 | 类型 | 输入格式 | 核心能力 | 性能 | 适用场景 |
|------|------|---------|---------|------|---------|
| **hprof-conv** | 命令行 | Android binary HPROF | 格式转换 | 快(1-5s/100MB) | 转换后才能用其他工具 |
| **LeakCanary** | 运行时库 | 自动 dump | **自动检测泄漏** | 后台分析(30-120s) | 开发 + 灰度 |
| **Eclipse MAT** | 桌面 GUI | 标准 Java HPROF | **深度分析(Dominator Tree)** | 加载 5-30s/100MB | 复杂泄漏根因 |
| **Android Studio** | IDE | 自动转换 | 基础查看 | 中 | 快速浏览 |
| **hprof-slice** | 命令行 | 标准 Java HPROF | 切片导出(按类/包) | 中 | 提取子集 |
| **jhat** | 命令行 HTTP | 标准 Java HPROF | 远程分析 | 慢 | 兼容旧 JDK |

```
                输入 hprof
                    ↓
              ┌──────────┐
              │hprof-conv│ (Android binary → 标准 Java)
              └────┬─────┘
                   ↓ 标准 Java HPROF
        ┌──────────┼──────────┬──────────┐
        ↓          ↓          ↓          ↓
   LeakCanary   MAT    Android Studio  hprof-slice
   (自动)      (深度)   (快速浏览)     (切片)
        ↓          ↓          ↓          ↓
   [报告]      [视图]     [快照]       [子集]
        └──────────┴──────────┴──────────┘
                   ↓
              [根因 + 修复]
```

---

## 2. hprof-conv:Android SDK 自带格式转换器

### 2.1 转换原理:Android binary HPROF → 标准 Java HPROF

**为什么需要转换**(引用 01 §3.4)?

Android 的 hprof 包含 **0xFE/0xFF 扩展 TAG**(HEAP_DUMP_INFO / HEAP_NAME),MAT / LeakCanary 这些标准 JVM 工具不识别。转换过程:

```
Android HPROF:
┌──────────────────────────────┐
│ HEADER (magic="JAVA PROFILE  │
│          1.0.3")             │
├──────────────────────────────┤
│ STRING 记录                   │
│ LOAD_CLASS 记录               │
│ HEAP_DUMP (含 0xFE/0xFF)     │ ← Android 扩展,标准工具看不懂
│ HEAP_DUMP_END                │
└──────────────────────────────┘
            ↓ hprof-conv
标准 Java HPROF:
┌──────────────────────────────┐
│ HEADER (同上)                 │
├──────────────────────────────┤
│ STRING 记录                   │
│ LOAD_CLASS 记录               │
│ HEAP_DUMP (重写 ID + 合并     │ ← 把多 heap 合并,标准工具能看
│   HEAP_DUMP_INFO 到 ID 前缀)   │
│ HEAP_DUMP_END                │
└──────────────────────────────┘
```

**关键转换点**:
1. 把 0xFE `HEAP_DUMP_INFO`(heap ID + 类型字符串)**展开到所有对象 ID 前缀**(如 heap 1 的对象 ID 范围 `[0x10000000, 0x1FFFFFFF]`)
2. 移除 0xFF `HEAP_NAME` 记录
3. 把每个 heap 单独 segment 转为全局统一 ID

### 2.2 命令详解与典型用法

```bash
# 基础用法
hprof-conv input.hprof output.hprof

# 批量转换(Linux/Mac)
for f in *.hprof; do
  hprof-conv "$f" "${f%.hprof}_converted.hprof"
done

# 批量转换(Windows PowerShell)
Get-ChildItem *.hprof | ForEach-Object {
  $out = $_.BaseName + "_converted.hprof"
  hprof-conv $_.FullName $out
}
```

> **配套脚本**:本系列提供 `scripts/hprof_batch_convert.sh` 和 `.ps1`,见工程资产。

### 2.3 工程坑位图:hprof-conv 失败 5 大原因

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| **`ERROR: hprof file does not contain JAVA PROFILE`** | 输入文件损坏 / 不是 hprof | 重新 dump,检查文件大小 > 1MB |
| **`ERROR: ID size unexpected`** | hprof 是 8 字节 ID,工具按 4 字节读 | 用新版 hprof-conv(SDK 26+) |
| **`out of memory`** | 输出文件占用过大内存 | 加 `-Xmx4g` 给 hprof-conv 进程 |
| **转换后文件大小翻倍** | 多 heap 展开 ID 占用更多字节 | 正常现象,1.5-2 倍 |
| **MAT 打开报错 `unknown tag 0xFE`** | 没经过 hprof-conv | 必须先转换 |

---

## 3. LeakCanary:自动化泄漏检测

### 3.1 工作原理:Shark 引擎 + WeakReference + GC Root 追踪

**简化流程**:

```
Activity.onDestroy()
    ↓
[LeakCanary] 延迟 5s 后检查 WeakReference
    ↓
WeakReference.get() != null? (说明 Activity 没被回收)
    ↓ 是
[Shark 引擎] 后台线程分析:
    1. 触发 GC(确保死对象都回收)
    2. Dump hprof 到磁盘
    3. hprof-conv 转换
    4. Shark 解析:建对象图 + 找 GC Root → Activity 路径
    5. 生成报告(PDF/HTML)
    ↓
[通知] 桌面通知 + 文件保存
```

**核心算法**:从 Activity 对象出发做 BFS,**直到找到 GC Root**——这条路径就是泄漏路径。

> **优势**:全自动,开发自测 + 灰度验证都可用。
> **劣势**:每个 Activity 销毁都会触发(可关闭),分析耗时 30-120s。

### 3.2 接入实战:Debug + Release 灰度策略

**Debug 包(默认)**:

```kotlin
// app/build.gradle.kts
dependencies {
  debugImplementation("com.squareup.leakcanary:leakcanary-android:2.14")
}
```

**Release 包灰度**(配套 `hprof_configs/leakcanary_config.gradle`):

```kotlin
// 只在内部灰度包启用,通过 build flavor 控制
releaseImplementation("com.squareup.leakcanary:leakcanary-android:2.14") {
  // 空实现
}

// 内部灰度包
internalImplementation("com.squareup.leakcanary:leakcanary-android:2.14")
```

**关键策略**:
- ✅ Debug 包:默认全功能(可在开发者选项关)
- ✅ 内部灰度包:启用,作为线上预警
- ❌ Release 正式包:不启用(性能 + 隐私 + 包大小)

### 3.3 报告解读:4 段式 + 引用链 + retained size

**典型 LeakCanary 报告**:

```
┌─────────────────────────────────────────────────────────┐
│ 1. 标题(泄漏类型 + 类名)                                │
│    com.example.MainActivity has leaked                   │
├─────────────────────────────────────────────────────────┤
│ 2. retained size(占用内存)                              │
│    retained 234.5 MB (84% of total heap)                 │
├─────────────────────────────────────────────────────────┤
│ 3. 引用链(GC Root → 泄漏对象)                           │
│    ┌─ static field com.example.GlobalCache.sInstance     │
│    │  ↓                                                  │
│    │  GlobalCache                                       │
│    │  ↓                                                  │
│    │  mAdapter: ProductAdapter                          │
│    │  ↓                                                  │
│    │  ProductAdapter.mContext: MainActivity ← 泄漏对象   │
├─────────────────────────────────────────────────────────┤
│ 4. 详情(对象大小 + 子对象)                              │
│    ├── MainActivity: 2.3 KB                             │
│    ├── mDecor: ViewRootImpl: 8.7 KB                     │
│    ├── mFragments: FragmentManagerImpl: 12.4 KB         │
│    └── ...                                              │
└─────────────────────────────────────────────────────────┘
```

**关键字段**:
- **retained size**:释放这个对象能回收的总内存(包括所有子对象)
- **shallow size**:对象自身大小(不含引用对象)
- **引用链**:从 GC Root 到泄漏对象的完整路径

### 3.4 工程坑位图:LeakCanary 误报 / 漏报 5 大场景

| 场景 | 类型 | 原因 | 解决方案 |
|------|------|------|---------|
| **Activity onDestroy 后 5s 被回收也算泄漏** | 误报 | 某些 Activity 内部有延迟逻辑(如统计) | 在 LeakCanary 中 `excludedActivities` 排除 |
| **Toast / Dialog 等系统对象被报泄漏** | 误报 | 系统对象生命周期长于 5s | 同上,过滤系统类 |
| **WebView 持有 Activity** | 真泄漏但难修 | WebView 设计缺陷 | 用独立进程跑 WebView |
| **第三方 SDK 持有 Activity** | 真泄漏 | 第三方 SDK bug | 联系 SDK 提供方 / 包裹 try-catch |
| **延迟回调 / Handler 消息** | 真泄漏 | MessageQueue 持有 Message 引用 Activity | Activity.onDestroy 时 `handler.removeCallbacksAndMessages(null)` |

> **误报处理 SOP**:LeakCanary 报告出现 → 先看 retained size(>1MB 才值得修) → 看引用链(系统类可忽略) → 复现验证(连续 3 次稳定出现才算)。

---

## 4. Eclipse MAT:离线深度分析之王

### 4.1 离线分析 vs 在线分析:为什么 MAT 适合大文件

**LeakCanary 的局限**:
- 仅追踪 Activity / Fragment 销毁后的泄漏
- 不支持复杂查询(如"所有大于 10MB 的 byte[]")
- 报告是"已知泄漏模式",**自定义查询能力弱**

**MAT 的优势**:
- **OQL**(Object Query Language):类似 SQL 查询堆
- **Dominator Tree**:看"谁真正占用了大块内存"
- **大文件支持**:支持 1GB+ hprof(LeakCanary 经常卡死)

### 4.2 核心视图:Dominator Tree / Leak Suspects / OQL

**Dominator Tree**(支配树)概念:

```
Root
 └─ A (支配 B、C、D)
     ├─ B
     ├─ C
     └─ D
```

- A 支配 B → **A 不释放,B 一定不释放**
- A 的 retained size = A + B + C + D 的总大小

**典型查询**:"找所有大于 10MB 的 byte[]"(用 OQL):

```sql
SELECT * FROM instanceof java.lang.Object[] 
WHERE sizeof >= 10485760
```

**Leak Suspects**:MAT 自动分析的报告,类似 LeakCanary 但更通用。

### 4.3 工程坑位图:MAT 加载 1GB+ hprof OOM

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| **`OutOfMemoryError: Java heap space`** | MAT 默认堆 1024MB | 修改 `MemoryAnalyzer.ini`:`-Xmx8g` |
| **加载 10 分钟还在解析** | 索引构建慢 | 用 `-vmargs -Xmx8g` + SSD 磁盘 |
| **报告查询超时** | OQL 命中全表 | 加索引字段,如 `WHERE className LIKE 'com.example.%'` |
| **导出报告 OOM** | 报告生成时全量加载 | 用 `-nosplash` + 命令行模式 |

**MAT 启动配置调优**(必备):

```ini
# MemoryAnalyzer.ini
-vmargs
-Xms2g
-Xmx8g
-XX:+UseG1GC
```

---

## 5. hprof-slice / jhat / 自研工具

### 5.1 hprof-slice:hprof 命令行切片工具

**用途**:从大 hprof 中提取子集(如只保留 `com.example.*` 类的对象)

**安装**:
```bash
# 来源:https://github.com/square/hprof-slice
git clone https://github.com/square/hprof-slice.git
cd hprof-slice
mvn install
```

**用法**:
```bash
java -jar hprof-slice.jar input.hprof --package com.example --output sliced.hprof
```

**典型场景**:
- 500MB hprof 只关心自己 app 的对象 → 切成 50MB
- 上传到 bug 平台时减小体积
- 加快 MAT 加载速度

### 5.2 jhat:JDK 自带 HTTP 分析器

**用法**:
```bash
jhat -J-Xmx4g input.hprof
# 浏览器访问 http://localhost:7000
```

**特点**:
- ✅ JDK 自带,无需额外安装
- ✅ 支持 OQL 查询
- ❌ **速度慢**(比 MAT 慢 5-10 倍)
- ❌ 界面古老,基本没人用了

> **结论**:除非不想装 MAT,否则不用 jhat。

### 5.3 自研工具:解析脚本 + SQL 查询

**场景**:批量分析 hprof 报告(如 CI 集成)

**Python 示例**(解析 LeakCanary 报告):

```python
# scripts/leakcanary_report_parse.py
# 简化版,实际需要更复杂的解析

import json
import sys
from pathlib import Path

def parse_leakcanary_report(report_path: Path):
    """解析 LeakCanary JSON 报告,提取关键字段"""
    data = json.loads(report_path.read_text())
    
    leaks = data.get("leaks", [])
    results = []
    for leak in leaks:
        results.append({
            "class": leak["className"],
            "retained_size_mb": leak["retainedSize"] / 1024 / 1024,
            "root_chain": " → ".join(leak["referenceChain"]),
            "is_real_leak": leak["retainedSize"] > 1_000_000  # >1MB 算真泄漏
        })
    return results
```

> **配套脚本**:完整版本见 `scripts/leakcanary_report_parse.py`。

---

## 6. 工具选型决策树

### 6.1 遇到 X 问题用 Y 工具

```
线上 OOM / 频繁被杀
    ↓
[Debug 包] → LeakCanary(自动检测)
    ↓
[Release 包 / LeakCanary 未集成]
    ↓
[dumpsys meminfo 确认内存分类]
    ↓
dump hprof(Debug.dumpHprofData / kill -10 / am dumpheap)
    ↓
hprof-conv 转换(Android binary → 标准 Java)
    ↓
[文件 < 100MB] → Android Studio 直接看
[文件 100MB-500MB] → LeakCanary 分析 或 MAT
[文件 > 500MB] → MAT(LeakCanary 会 OOM)
    ↓
[已知 Activity/Fragment 泄漏] → 看 LeakCanary 报告
[复杂自定义查询] → MAT OQL
[持续监控] → perfetto_heapprofd(见 03)
```

### 6.2 工具组合拳:5 阶段流水线

```
[1. 触发]    Debug.dumpHprofData / kill -10 / LeakCanary 自动
    ↓
[2. 转换]    hprof-conv(如果需要用 MAT/LeakCanary 看)
    ↓
[3. 初筛]    Android Studio / LeakCanary 报告
    ↓
[4. 深挖]    MAT Dominator Tree + OQL 查询
    ↓
[5. 验证]    LeakCanary 重复触发 + 单元测试
```

---

## 7. 实战:从 hprof 到根因的完整链路

### 7.1 案例背景

**App**:某视频 app,首页有视频列表(RecyclerView)。
**现象**:持续刷视频 30 分钟,内存从 200MB 涨到 800MB,偶现 OOM。
**目标**:找出谁在涨内存。

### 7.2 阶段 1:dump

```kotlin
// 在 DebugApplication.onCreate 中加
if (BuildConfig.DEBUG && Debug.isDebuggerConnected()) {
    // 仅 debug + 调试时手动 dump
}

// 命令行 dump(更通用)
adb shell am dumpheap <pkg> /sdcard/dump.hprof
adb pull /sdcard/dump.hprof ./
```

> **dump 时机**:用户报问题 → 让用户操作复现 → dump。

### 7.3 阶段 2:转换

```bash
hprof-conv dump.hprof dump_standard.hprof
# 200MB Android hprof → 350MB 标准 Java hprof(多 heap 展开)
```

### 7.4 阶段 3:分析

**Android Studio 快速浏览**:
- 看到 `byte[]` 总占用 250MB
- 进一步发现 12 个 `byte[16MB]` 的对象

**MAT OQL 查询**:

```sql
SELECT t.@displayName, t.@retainedHeapSize 
FROM instanceof byte[] t
WHERE t.@length > 10000000
```

→ 输出 12 个大 `byte[]`,每个 16MB+。

**查看这些 byte[] 的引用路径**:
- 选中最大一个 → "Path to GC Roots" → "exclude weak references"
- 链路:`HomeActivity` → `mRecyclerView` → `mAdapter` → `mBitmapPool` → `Bitmap[]` → `byte[]`

### 7.5 阶段 4:定位

```
HomeActivity (泄漏)
  ↑
  BitmapPool 静态缓存
    ↑
    12 个 Bitmap,每个 16MB(原始视频帧缩略图,实际应该是 256x256 缩略图但存了 1080p 原图)
```

**根因清晰**:
- 视频列表加载缩略图时,**缓存了原图**而不是缩略图
- 静态 BitmapPool 永不释放
- 持续刷 → 持续缓存 → OOM

### 7.6 阶段 5:修复

```kotlin
// 错误实现
Glide.with(view).load(url).into(view)  // 默认缓存原图

// 正确实现
Glide.with(view)
  .load(url)
  .override(256, 256)  // 强制缩放到 256x256
  .into(view)
```

**验证**:
- LeakCanary:HomeActivity 销毁后 WeakReference 在 5s 内被清空
- 持续刷 30 分钟:内存稳定在 250MB 左右

---

## 8. 总结:架构师视角的 5 条 Takeaway

### Takeaway 1:hprof-conv 是"必经一步"
Android binary hprof 必须用 hprof-conv 转换才能用 MAT / LeakCanary。**不转换直接用 MAT,会报 unknown tag 错误**。

### Takeaway 2:LeakCanary 适合"已知泄漏模式",MAT 适合"未知探索"
- LeakCanary:Activity / Fragment 销毁后引用追踪 → **自动化 + 模式化**
- MAT:任意查询 + Dominator Tree → **探索式 + 深度**

### Takeaway 3:大文件必须 MAT
500MB+ hprof **LeakCanary 必崩**,必须用 MAT(MemoryAnalyzer.ini `-Xmx8g`)。

### Takeaway 4:工具组合拳才是工程化
单工具不够,**5 阶段流水线**(触发→转换→初筛→深挖→验证)才能稳定产出根因。

### Takeaway 5:工具只是"放大镜",根因在代码
工具找出"谁持有谁",**修复要在代码层**(取消静态引用 / 改用弱引用 / 包裹 try-catch)。

---

## 附录 A:核心源码路径索引

| 路径 | 作用 |
|------|------|
| `frameworks/native/cmds/hprof-conv/` | hprof-conv 工具源码 |
| `com/squareup/leakcanary/LeakCanary.java` | LeakCanary 入口 |
| `com/squareup/leakcanary/Shark.kt` | Shark 分析引擎 |
| `shark/`(Shark 库) | 堆解析核心算法 |
| `com/squareup/haha/perflib/` | hprof 解析(LeakCanary 依赖) |
| `org/eclipse/mat/snapshot/` | MAT 快照模型 |
| `org/eclipse/mat/parser/` | MAT hprof 解析器 |

## 附录 B:LeakCanary 误报/漏报排查清单

```
[ ] 1. retained size < 1MB? → 可忽略
[ ] 2. 引用链含系统类(android.* / java.*)? → 可排除
[ ] 3. 第三方 SDK 持有? → 包裹 try-catch 或联系 SDK
[ ] 4. WebView / TextureView? → 用独立进程
[ ] 5. Handler 消息未清空? → onDestroy 时 removeCallbacksAndMessages
[ ] 6. 静态集合未清理? → 改用 WeakHashMap
[ ] 7. 注册未反注册(Broadcast / EventBus)? → onDestroy 反注册
[ ] 8. 内部类持有外部类? → 改静态内部类 + WeakReference
[ ] 9. 反复 3 次稳定复现? → 真泄漏
[ ] 10. retained size > 10MB? → 必须修
```

## 附录 C:量化数据自检表

| 工具 | 100MB hprof 耗时 | 500MB hprof 耗时 | 内存峰值 |
|------|----------------|----------------|---------|
| hprof-conv | 1-5s | 5-15s | 200-500MB |
| LeakCanary | 30-60s | **常 OOM** | 500MB-1GB |
| MAT | 5-15s | 30-90s | 2-8GB(可调) |
| Android Studio | 5-10s | 30-60s | 1-2GB |
| hprof-slice | 10-30s | 60-180s | 500MB-1GB |

## 附录 D:工程基线表

| 项 | 版本/路径 |
|----|---------|
| LeakCanary | `2.14+` |
| Eclipse MAT | `1.12.0+` |
| hprof-slice | `1.1+` |
| hprof-conv | Android SDK `platform-tools/`(跟随 SDK 更新) |
| Android Studio | Hedgehog (2023.1.1) 或更新 |
| JDK | 17+(MAT 需要) |

## 篇尾衔接

**下一篇**:[03-perfetto_hprof 详解](03-perfetto_hprof详解.md) 会介绍 Google 把 hprof 集成到 Perfetto 的真正动机——**heapprofd 守护进程架构、native heap sampling、配置模板、与传统 hprof 的对比**。

**强依赖本篇的章节**:
- 03 §3 会引用本篇 §3 的 LeakCanary 讲解 perfetto_heapprofd 与传统 hprof 的差异
- 04 §2-§5 会用本篇的工具完成案例分析
- 05 §3-§4 会基于本篇的工具搭建监控体系

**本篇不覆盖**:
- perfetto_hprof 内部实现 → [03](03-perfetto_hprof详解.md)
- 内存泄漏案例库 → [04](04-内存泄漏典型案例与排查SOP.md)
- 内存监控体系搭建 → [05](05-实战：内存监控体系搭建.md)