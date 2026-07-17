# 01-hprof 原理与文件格式

> **本篇定位**:系列第 1 篇(全局观)。读完能独立读懂 hprof 二进制,理解 ART 怎么生成 hprof,知道它在稳定性工具链中的位置。
>
> **强依赖**:无(本篇是系列入口)
> **承接自**:无
> **衔接去**:[02-hprof 解析工具链](02-hprof解析工具链.md) 会展开工具方法论,[03-perfetto_hprof 详解](03-perfetto_hprof详解.md) 会介绍 Google 的新方向
>
> **不重复内容**:本篇只讲"格式、原理、ART 生成路径",**不讲**:
> - 工具使用细节(见 [02 工具链](02-hprof解析工具链.md))
> - 案例分析(见 [04 案例库](04-内存泄漏典型案例与排查SOP.md))
> - perfetto_hprof 内部实现(见 [03 perfetto_hprof](03-perfetto_hprof详解.md))
>
> **基线**:AOSP `android-14.0.0_r1` + LeakCanary `2.14+` + Android Studio Hedgehog
> **风格**:源码密度 ~15%,重点放在格式图 + 时序图 + 决策树 + 视角分析
>
> **目录位置**:`Android_Framework/Hprof/`
> **上一篇**:无(系列入口)
> **下一篇**:[02-hprof 解析工具链](02-hprof解析工具链.md)

---

## 目录

- [1. 背景:hprof 是 Android 内存稳定性的"事故取证"](#1-背景hprof-是-android-内存稳定性的事故取证)
  - [1.1 一个线上 OOM 案例的"无 hprof 之痛"](#11-一个线上-oom-案例的无-hprof-之痛)
  - [1.2 hprof 在稳定性工具链的"压舱石"地位](#12-hprof-在稳定性工具链的压舱石地位)
- [2. hprof 格式 30 年演进:JVM HPROF → Android HPROF](#2-hprof-格式-30-年演进jvm-hprof--android-hprof)
  - [2.1 两个版本的差异矩阵](#21-两个版本的差异矩阵)
  - [2.2 为什么 Android 不沿用 JVM 标准格式](#22-为什么-android-不沿用-jvm-标准格式)
- [3. hprof 二进制文件结构:HEADER + RECORD + TAG](#3-hprof-二进制文件结构header--record--tag)
  - [3.1 全景图:一个 hprof 文件 = 1 个 HEADER + N 个 RECORD](#31-全景图一个-hprof-文件--1-个-header--n-个-record)
  - [3.2 HEADER(文件头):格式 + 时间戳 + ID 大小](#32-header文件头格式--时间戳--id-大小)
  - [3.3 RECORD(记录):TAG + 时间 + 长度 + BODY](#33-record记录tag--时间--长度--body)
  - [3.4 Android 扩展 TAG(0xFE ~ 0xFF):Heap Dump Info / Heap Name](#34-android-扩展-tag0xfe--0xffheap-dump-info--heap-name)
- [4. 关键 RECORD 详解:STRING / CLASS / INSTANCE / ROOT](#4-关键-record-详解string--class--instance--root)
  - [4.1 STRING 记录:解析 ID 到字符串的映射](#41-string-记录解析-id-到字符串的映射)
  - [4.2 CLASS 记录:类元数据 + 字段 + 静态引用](#42-class-记录类元数据--字段--静态引用)
  - [4.3 INSTANCE 记录:对象实例的字段值](#43-instance-记录对象实例的字段值)
  - [4.4 OBJECT ARRAY / PRIMITIVE ARRAY:数组结构](#44-object-array--primitive-array数组结构)
  - [4.5 ROOT 记录:GC Root 类型(JNI/Global/Local/Thread/Stack)](#45-root-记录gc-root-类型jnigloballocalthreadstack)
- [5. Android ART 中 hprof 的生成机制](#5-android-art-中-hprof-的生成机制)
  - [5.1 三种触发路径:Debug.dumpHprofData / kill -10 / Perfetto heapprofd](#51-三种触发路径debugdumphprofdata--kill--10--perfetto-heapprofd)
  - [5.2 ART `art/runtime/hprof/` 源码结构](#52-art-artruntimehprof-源码结构)
  - [5.3 关键流程:GraphVisitor → HeapObject → 序列化 RECORD](#53-关键流程graphvisitor--heapobject--序列化-record)
  - [5.4 性能开销:为什么 hprof 会让 app 卡顿 5-30s](#54-性能开销为什么-hprof-会让-app-卡顿-5-30s)
- [6. hprof 在稳定性工具链中的定位](#6-hprof-在稳定性工具链中的定位)
  - [6.1 五大内存追踪工具的能力矩阵](#61-五大内存追踪工具的能力矩阵)
  - [6.2 工具选型决策树:遇到 X 问题用 Y 工具](#62-工具选型决策树遇到-x-问题用-y-工具)
  - [6.3 关键认知:hprof 决定你能"看见"什么](#63-关键认知hprof-决定你能看见什么)
- [7. hprof 的三大局限](#7-hprof-的三大局限)
  - [7.1 性能开销:Stop-The-World + 全量扫描](#71-性能开销stop-the-world--全量扫描)
  - [7.2 Native 盲区:Bitmap / DirectByteBuffer / JNI 全看不见](#72-native-盲区bitmap--directbytebuffer--jni-全看不见)
  - [7.3 采样缺失:不能像 perfetto_hprof 那样持续采样](#73-采样缺失不能像-perfetto_hprof-那样持续采样)
- [8. 实战:同 OOM 问题 hprof vs 纯 logcat 对比](#8-实战同-oom-问题-hprof- vs-纯-logcat-对比)
  - [8.1 案例背景](#81-案例背景)
  - [8.2 纯 logcat 的"看不见"](#82-纯-logcat-的看不见)
  - [8.3 hprof 的"看得清"](#83-hprof-的看得清)
  - [8.4 关键 takeaway](#84-关键-takeaway)
- [9. 总结:架构师视角的 5 条 Takeaway](#9-总结架构师视角的-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:hprof TAG 全量表](#附录-bhprof-tag-全量表)
- [附录 C:量化数据自检表](#附录-c量化数据自检表)
- [附录 D:工程基线表](#附录-d工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. 背景:hprof 是 Android 内存稳定性的"事故取证"

### 1.1 一个线上 OOM 案例的"无 hprof 之痛"

**线上场景**:某 app 后台被频繁 OOM kill,Dumpsys 显示 `oom_adj = 900` 的进程被杀。

**没有 hprof 时,你只有这些信息**:

```
logcat:
  E/art: Throwing OutOfMemoryError "Failed to allocate a 8MB byte buffer"
  W/ActivityManager: Process com.example.app has died (OOM)
  I/libc: malloc.c: failed to allocate 8388608 bytes
  W/System.err: java.lang.OutOfMemoryError: Failed to allocate
```

**你看到的**:app 试图分配 8MB 失败被杀。
**你想知道的**:
- 这 8MB 是 Bitmap?ListView?还是 native buffer? → **logcat 不告诉你**
- 哪个对象持有它?是 Activity?Fragment?静态变量? → **logcat 不告诉你**
- 是一直累积的,还是单次突发? → **logcat 不告诉你**
- 被谁引用导致不能释放? → **logcat 不告诉你**

> **hprof 就是解开这四个问题的钥匙**——它记录了"那一瞬间,堆里每个对象是谁、占多大、被谁引用"。

### 1.2 hprof 在稳定性工具链的"压舱石"地位

```
内存稳定性问题(线上)
    ↓
[第一现场:hprof 堆转储]
    ↓              ↘
[分析]              [对比]
    ↓                  ↓
LeakCanary         性能基线
MAT                历史 hprof
perfetto_hprof     代码 diff
    ↓
[根因 + 修复]
```

**没有 hprof,内存稳定性问题基本只能靠"猜"** ——这是它和 Perfetto trace 的本质区别:
- Perfetto 看 **时间维度**(谁在什么时候做了什么)
- hprof 看 **空间维度**(谁占用了多少内存、被谁引用)

两者互补,缺一不可。

### 1.3 稳定性工程师的"三件套"心法

| 工具 | 看的维度 | 解决的问题 |
|------|---------|-----------|
| **Perfetto trace** | 时间维度 | 卡顿、ANR、启动慢、IO 劣化 |
| **hprof** | 空间维度 | **OOM、内存泄漏、Bitmap 暴涨** |
| **logcat + dumpsys** | 事件 + 状态 | 异常日志、系统快照 |

> **口诀**:时间找 Perfetto,空间找 hprof,线索找 logcat。

---

## 2. hprof 格式 30 年演进:JVM HPROF → Android HPROF

### 2.1 两个版本的差异矩阵

| 维度 | JVM HPROF (1.0.2/1.0.3) | Android HPROF |
|------|------------------------|---------------|
| 出生 | JDK 1.2 (1998) | Android 1.0 (2008) |
| 标识符 | `"JAVA PROFILE 1.0.2"` | `"JAVA PROFILE 1.0.3"` |
| ID 大小 | 固定 4 字节 | **动态(4 或 8 字节)** |
| Heap 概念 | 单 heap | **多 heap(Zygote / Image / Boot / App / Camera...)** |
| ART 扩展 | 无 | `HEAP_DUMP_INFO`、`HEAP_NAME` 等 0xFE/0xFF TAG |
| 默认输出 | `.hprof.txt` 文本 | 二进制 `.hprof`(Android Studio 自动转 `.hprof` 标准格式) |

> **关键差异**:Android 的 hprof 在 JVM 基础上扩展了"多 Heap"和"动态 ID 大小",这是 Android 进程隔离机制(Zygote fork)决定的。

### 2.2 为什么 Android 不沿用 JVM 标准格式

```
JVM 进程模型:                    Android 进程模型:
┌──────────────┐                  ┌────────────────────────┐
│   单 JVM     │                  │   Zygote(共享 boot heap)│
│   单 Heap    │                  │   ↓ fork               │
│              │                  │   ┌──────┐ ┌──────┐    │
└──────────────┘                  │   │App1  │ │App2  │    │
                                  │   │独立 heap│独立 heap│
                                  └────────────────────────┘
```

Android 的 Zygote fork 模型要求 hprof **区分"共享 heap"和"私有 heap"**,否则 App1 的 hprof 会包含 Zygote 共享的 boot class 对象(占用 60%+ 空间)。所以 Android 扩展了:
- `HEAP_DUMP_INFO`(0xFE):声明 heap ID 对应的类型字符串
- `HEAP_NAME`(0xFF):标记每段 heap dump 属于哪个 heap
- **动态 ID 大小**:heap 越大用越大 ID 节省空间(典型 app 用 4 字节,大堆用 8 字节)

### 2.3 工程视角:Android Studio 的自动转换

Android Studio 打开 Android hprof 时,**自动检测格式**并转换:
- Android binary HPROF → 标准 Java HPROF(用于 MAT/LeakCanary 解析)
- 转换工具:Android SDK `platform-tools/hprof-conv`

```bash
# 标准用法(Android Studio 内部就是这么做的)
hprof-conv input.hprof output.hprof
```

> 这就是为什么 LeakCanary/MAT 能直接处理 `.hprof` 后缀——它们读的是转换后的标准 Java HPROF。

---

## 3. hprof 二进制文件结构:HEADER + RECORD + TAG

### 3.1 全景图:一个 hprof 文件 = 1 个 HEADER + N 个 RECORD

```
┌──────────────────────────────────────────────────────────────┐
│  HEADER(变长,通常 20-30 字节)                                 │
│  ┌────────────────────────┬────────────┬────────────────┐    │
│  │ MAGIC: "JAVA PROFILE  │ NULL byte  │ ID Size: 4 or 8 │    │
│  │          1.0.3\0"      │ (1 byte)   │ (4 bytes)       │    │
│  │ (17 bytes,含 \0)       │            │                 │    │
│  └────────────────────────┴────────────┴────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Timestamp (8 bytes,ms since epoch)                  │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  RECORD 1                                                     │
│  ┌────────┬──────────┬──────────┬──────────────────────────┐  │
│  │ TAG    │ Time     │ Length   │ BODY                     │  │
│  │(1 byte)│(4 bytes) │(4 bytes) │ (Length bytes)           │  │
│  └────────┴──────────┴──────────┴──────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  RECORD 2                                                     │
│  ...                                                          │
└──────────────────────────────────────────────────────────────┘
... 共 N 个 RECORD
```

### 3.2 HEADER(文件头):格式 + 时间戳 + ID 大小

**字节级布局**:

```
偏移  大小    字段                示例值
───────────────────────────────────────────────────
0x00  17      magic               "JAVA PROFILE 1.0.3\0"
0x11  1       padding             0x00
0x12  4       id_size             4 或 8 (小端)
0x16  8       timestamp           0x0000017E5C4A8B12 (ms)
───────────────────────────────────────────────────
```

**关键约束**:
- `magic` 字符串**固定**,以 `\0` 结尾;如果不是 `"JAVA PROFILE 1.0.3"`,Android Studio 会尝试按 Android 二进制格式解析
- `id_size` **必须与文件 BODY 中所有 ID 字段大小一致**(典型 4 字节,大堆 8 字节)
- `timestamp` 是 dump 开始时间,**不是 dump 完成时间**(完整 dump 可能耗时 10-30s)

### 3.3 RECORD(记录):TAG + 时间 + 长度 + BODY

**字节级布局**:

```
偏移  大小    字段                说明
───────────────────────────────────────────────────
0x00  1       tag                 RECORD 类型 TAG(见下表)
0x01  4       delta_time_us       距上一个 RECORD 的微秒数(相对时间)
0x05  4       length              BODY 长度(字节)
0x09  L       body                实际内容,长度由 length 决定
───────────────────────────────────────────────────
```

> **注意**:delta_time_us 是**相对时间**,不是绝对时间。首个 RECORD 通常 delta = 0。

### 3.4 Android 扩展 TAG(0xFE ~ 0xFF):Heap Dump Info / Heap Name

**完整 TAG 列表**(JVM 标准 + Android 扩展):

| TAG 值 | 名称 | 出现位置 | 用途 |
|--------|------|---------|------|
| `0x01` | STRING | 文件早期 | 字符串常量池 |
| `0x02` | LOAD_CLASS | 文件早期 | 类元数据 |
| `0x04` | FRAME | HEAP DUMP 内 | Java 栈帧 |
| `0x05` | TRACE | HEAP DUMP 内 | 栈追踪 |
| `0x06` | HEAP_DUMP_SEGMENT | 文件主体 | Heap 转储段 |
| `0x0C` | HEAP_DUMP_END | 文件主体 | Heap dump 结束标记 |
| `0x1C` | HEAP_DUMP | 文件主体 | 单段堆 dump(Android 简化) |
| `0x2C` | HEAP_DUMP_END | 文件主体 | 段结束(同上) |
| `0xFE` | **HEAP_DUMP_INFO** | HEAP DUMP 段首 | Android 扩展:声明 heap 类型 |
| `0xFF` | **HEAP_NAME** | HEAP DUMP 段首 | Android 扩展:heap 名称字符串 |

> **0xFE / 0xFF 是 Android 独有**——标准 JVM HPROF 不识别这两个 TAG。这就是为什么必须用 hprof-conv 转换才能在 MAT/LeakCanary 中正确显示"哪个 heap 占多少"。

---

## 4. 关键 RECORD 详解:STRING / CLASS / INSTANCE / ROOT

### 4.1 STRING 记录:解析 ID 到字符串的映射

```
┌──────────────────────────────────────────┐
│  STRING RECORD                           │
│  ┌──────────┬──────────────────────┐    │
│  │ string_id│ UTF-8 string         │    │
│  │(id_size) │ (length bytes)       │    │
│  └──────────┴──────────────────────┘    │
└──────────────────────────────────────────┘

例:STRING id=0x01, "java.lang.String"
→ 后续 INSTANCE 记录引用 0x01 时,就表示这个对象的 name 字段是 "java.lang.String"
```

**关键作用**:hprof 里所有"字符串字段"(类名、字段名、字段值)都是 ID 引用,**必须先解析 STRING 表才能反序列化 INSTANCE**。

> **性能提示**:LeakCanary 解析时第一步就是建 STRING 索引(HashMap),通常 100MB hprof 含 50万+ 字符串,这一步耗时 1-3s。

### 4.2 CLASS 记录:类元数据 + 字段 + 静态引用

```
┌──────────────────────────────────────────────────────────────┐
│  CLASS DUMP RECORD(在 HEAP DUMP 段内)                         │
│  ┌─────────┬──────────┬──────────┬────────────┬──────────┐  │
│  │class_id │ stack_   │ super_   │ class_loader│ signers  │  │
│  │(id_size)│ trace_   │ class_id │ _id         │ _id      │  │
│  │         │ serial   │ (id_size)│ (id_size)   │ (id_size)│  │
│  │         │ (4 bytes)│          │             │          │  │
│  │         │ trace_   │ prot_    │ prot_domain │ _domain  │  │
│  │         │ size     │ domain_  │ _id         │ _id      │  │
│  │         │ (2 bytes)│ id       │             │          │  │
│  │         │          │ (id_size)│             │          │  │
│  │         │ instance │ static_  │ static_     │          │  │
│  │         │ _size    │ field    │ field       │          │  │
│  │         │ (4 bytes)│ count    │ values      │          │  │
│  │         │          │ (2 bytes)│             │          │  │
│  └─────────┴──────────┴──────────┴────────────┴──────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**关键字段**:
- `class_id`:类的唯一 ID
- `super_class_id`:父类 ID(构成继承链)
- `instance_size`:该类一个实例占用字节数(64 位 VM 会有对齐 padding)
- `static_fields`:静态字段值列表——**static 引用泄漏的全在这里**!

### 4.3 INSTANCE 记录:对象实例的字段值

```
┌─────────────────────────────────────────────────────┐
│  INSTANCE DUMP RECORD                               │
│  ┌──────────┬────────────┬────────────────────────┐ │
│  │ class_id │ byte_      │ field_values          │ │
│  │(id_size) │ length     │ (按 class 字段顺序)   │ │
│  │          │ (4 bytes)  │                        │ │
│  └──────────┴────────────┴────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**反序列化逻辑**:
1. 读 `class_id` → 在 CLASS 表查类元数据
2. 按类元数据的字段顺序,逐个读 `field_values`:
   - 引用类型 → `id_size` 字节的 ID
   - boolean/byte → 1 字节
   - char/short → 2 字节
   - int/float → 4 字节
   - long/double → 8 字节
3. 累计 `byte_length` 必须严格匹配(否则 hprof 损坏)

### 4.4 OBJECT ARRAY / PRIMITIVE ARRAY:数组结构

```
┌────────────────────────────────────────────────────┐
│  OBJECT ARRAY DUMP                                 │
│  ┌──────────┬─────────────┬──────────┬──────────┐ │
│  │ class_id │ length      │ element  │ element  │ │
│  │(id_size) │ (4 bytes)   │ id #0    │ id #1    │ │
│  │          │             │(id_size) │(id_size) │ │
│  │          │             │  ...     │  ...     │ │
│  └──────────┴─────────────┴──────────┴──────────┘ │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│  PRIMITIVE ARRAY DUMP                              │
│  ┌──────────┬─────────────┬──────────────────────┐ │
│  │ type     │ length      │ element values       │ │
│  │(1 byte)  │ (4 bytes)   │ (length * elem_size) │ │
│  │ 4=int    │             │                      │ │
│  │ 5=long   │             │                      │ │
│  │ 8=double │             │                      │ │
│  └──────────┴─────────────┴──────────────────────┘ │
└────────────────────────────────────────────────────┘
```

**关键提示**:
- `Bitmap` 在 hprof 里本质是 `byte[]`(PRIMITIVE ARRAY,type=8)——找大 bitmap 直接搜 `byte[]` 长度 > 1MB
- `ArrayList` 内部是 `Object[]`——找"长列表泄漏"直接搜 `Object[10000+]`

### 4.5 ROOT 记录:GC Root 类型(JNI/Global/Local/Thread/Stack)

```
┌────────────────────────────────────────────────────────┐
│  ROOT 记录类型(在 HEAP DUMP 段内)                       │
├──────┬─────────────────────┬───────────────────────────┤
│ TAG  │ 名称                │ 典型场景                   │
├──────┼─────────────────────┼───────────────────────────┤
│ 0xFF │ ROOT_JNI_GLOBAL     │ JNI 全局引用(Native 持有)  │
│ 0x01 │ ROOT_JNI_LOCAL      │ JNI 局部引用(栈帧持有)     │
│ 0x02 │ ROOT_JAVA_FRAME     │ Java 栈帧持有              │
│ 0x03 │ ROOT_NATIVE_STACK   │ Native 栈持有              │
│ 0x04 │ ROOT_STICKY_CLASS   │ 系统类(永不回收)           │
│ 0x05 │ ROOT_THREAD_BLOCK   │ 线程对象持有               │
│ 0x06 │ ROOT_MONITOR_USED   │ Monitor 锁对象持有         │
│ 0x07 │ ROOT_THREAD_OBJ     │ 活跃线程                  │
│ 0x08 │ ROOT_UNKNOWN        │ 未知                       │
│ 0x20 │ ROOT_FINALIZING     │ 等待 finalize             │
│ 0x21 │ ROOT_INTERNED_STRING│ 字符串常量池               │
└──────┴─────────────────────┴───────────────────────────┘
```

> **核心概念**:从 GC Root 出发不可达的对象才能被回收。**泄漏 = 对象从 GC Root 可达,但业务上已不需要**。
>
> LeakCanary 的核心算法就是:对每个 GC Root 做 BFS/DFS,找"应该被释放但还可达"的对象(典型:Activity 被静态引用持有)。

---

## 5. Android ART 中 hprof 的生成机制

### 5.1 三种触发路径:Debug.dumpHprofData / kill -10 / Perfetto heapprofd

| 触发方式 | API/命令 | 适用场景 | 性能开销 |
|---------|---------|---------|---------|
| **代码触发** | `Debug.dumpHprofData(path)` | debug 主动 dump | 中(GC 后扫描 5-10s) |
| **信号触发** | `kill -10 <pid>`(SIGUSR1) | shell 命令 dump | 中(同上) |
| **Perfetto** | `heapprofd` 配置 | 线上持续采样 | 低(后台采样 1-3%) |
| **系统自动** | `am dumpheap <pkg>` | adb 命令 | 中-高(全量 GC) |
| **OOM 前自动** | Application.onLowMemory + watchdog | 线上兜底 | 高(瞬间 STW) |

### 5.2 ART `art/runtime/hprof/` 源码结构

```
art/runtime/hprof/
├── hprof.cc                       # Hprof 核心实现(~3000 行)
├── hprof.h
├── heap_dump.cc                   # Heap dump 序列化逻辑
├── heap_dump.h
└── hprof_md.h                     # 平台相关宏
```

**关键类**:
- `Hprof`:主类,负责打开文件 + 写 HEADER
- `HeapDump`:负责遍历 ART 堆 + 序列化所有对象
- `GraphVisitor`:访问者模式,遍历每个对象(根、类、实例、数组)

### 5.3 关键流程:GraphVisitor → HeapObject → 序列化 RECORD

**简化的时序图**(完整流程见 `art/runtime/hprof/hprof.cc`):

```
用户调用 Debug.dumpHprofData()
    ↓
[ART] Runtime::DumpHeap() 
    ↓
[ART] Hprof::Dump() 
    ↓ 写 HEADER("JAVA PROFILE 1.0.3")
    ↓
[ART] Heap::VisitObjects() 启动 GC + 暂停所有线程(STW)
    ↓
[ART] GraphVisitor::Visit() 遍历每个 HeapObject
    ↓
    ├── ROOT 类型 → 写 ROOT RECORD
    ├── Class 类型 → 写 CLASS DUMP RECORD
    ├── Instance → 写 INSTANCE DUMP RECORD  
    ├── Object[] → 写 OBJECT ARRAY DUMP RECORD
    └── Primitive[] → 写 PRIMITIVE ARRAY DUMP RECORD
    ↓
[ART] 恢复线程,关闭文件
    ↓
返回文件路径给用户
```

> **关键视角**:整个 dump 过程是 **Stop-The-World**——所有 Java 线程暂停。这就是为什么 hprof 会让 app 卡顿 5-30s。

### 5.4 性能开销:为什么 hprof 会让 app 卡顿 5-30s

| 阶段 | 耗时 | 原因 |
|------|------|------|
| 触发 GC | 50-500ms | 需要先 GC 一遍确保回收已死对象 |
| **STW 暂停** | **100-2000ms** | 所有 Java 线程暂停,不能有任何对象移动 |
| 堆扫描 | 1-10s/GB | 遍历每个 HeapObject,序列化字段 |
| 字符串去重 | 0.5-3s | 字符串池去重写入 STRING RECORD |
| 写盘 | 0.5-5s | 文件 IO(取决于存储速度) |
| **总计** | **5-30s/GB** | **典型 100MB 堆需要 5-15s** |

> **稳定性影响**:线上使用 hprof dump 会导致 app **完全卡死 5-30s**——这是为什么 perfetto_hprof(后台采样,1-3% 开销)是 Google 的演进方向。

### 5.5 关键源码视角(15% 源码密度控制)

```cpp
// art/runtime/hprof/hprof.cc 简化版
void Hprof::Dump(const char* filename) {
  // 1. 打开输出文件
  int fd = open(filename, O_CREAT | O_WRONLY | O_TRUNC, 0644);
  
  // 2. 写 HEADER
  WriteHeader(fd, sizeof(uint32_t));  // 4 字节 ID
  
  // 3. 触发 GC(确保回收已死对象)
  heap_->CollectGarbage(/*cause*/ GC::kGcCauseHprof);
  
  // 4. STW:暂停所有线程
  ScopedSuspendAll ssa("Hprof dump");
  
  // 5. 遍历堆 + 序列化
  HprofHeapDumpVisitor visitor(this, fd);
  heap_->VisitObjects(&visitor);
  
  // 6. 写 END RECORD
  WriteHeapDumpEnd(fd);
  
  close(fd);
  // ssa 析构时自动恢复线程
}
```

**视角**:这是典型的 "**STW + 全量扫描**" 模式——简单但粗暴。perfetto_hprof 用相反的策略:**后台持续采样**(每 N ms 记录一次调用栈),无需 STW。

---

## 6. hprof 在稳定性工具链中的定位

### 6.1 五大内存追踪工具的能力矩阵

| 工具 | 时间维度 | 空间维度 | 性能开销 | 适用场景 |
|------|---------|---------|---------|---------|
| **hprof** | ❌ 单次快照 | ✅ 全量对象图 | ❌ 高(5-30s STW) | 离线深度分析 |
| **Perfetto heapprofd** | ✅ 持续 | ⚠️ 采样 | ✅ 低(1-3%) | 线上持续监控 |
| **LeakCanary** | ❌ 自动触发 | ✅ 仅泄漏对象 | ⚠️ 中(后台分析) | 开发 + 灰度 |
| **dumpsys meminfo** | ✅ 实时 | ⚠️ 分类聚合 | ✅ 低 | 线上实时观察 |
| **logcat GC log** | ✅ 每次 GC | ⚠️ 仅大小 | ✅ 极低 | GC 频率监控 |

### 6.2 工具选型决策树:遇到 X 问题用 Y 工具

```
线上 OOM / 频繁被杀
    ↓
[dumpsys meminfo 确认内存分类]
    ├── Java Heap 占比高(>50%) → 用 hprof(LeakCanary)
    ├── Native Heap 占比高(>30%) → 用 perfetto_heapprofd native sampling
    ├── Graphics 占比高 → Bitmap 泄漏,用 hprof 找 byte[] 大对象
    └── Code/.so 占比高 → 代码加载问题,排查是否多 dex / 多 so
    ↓
[分析 hprof]
    ↓
[LeakCanary 报告 / MAT 手动分析]
    ↓
[根因 + 修复]
```

### 6.3 关键认知:hprof 决定你能"看见"什么

```
能看见的:                            不能看见的:
✅ 所有 Java 对象(类、实例、数组)   ❌ Native 内存(bitmap 像素、so)
✅ 引用关系(A 持有 B)               ❌ 内存增长"过程"(只有快照)
✅ 静态字段值(找 static 泄漏)        ❌ DirectByteBuffer(NIO)
✅ ThreadLocal 内容                  ❌ JNI 全局引用(只能看 JNI local)
✅ 字符串内容(去重后)                ❌ 被 finalize 队列阻塞的对象
```

> **核心结论**:hprof 是 **Java 堆空间的"快照"**,不是"全内存视图"。Native 部分需要 perfetto_heapprofd 补全。

---

## 7. hprof 的三大局限

### 7.1 性能开销:Stop-The-World + 全量扫描

**问题**:每次 dump 都是 STW,100MB 堆需要 5-15s。

**典型线上事故**:

```
14:23:01 线上 dump hprof
14:23:01.000 用户点击 → 无响应(STW 开始)
14:23:11.500 恢复响应(STW 结束,共 10.5s)
14:23:12.000 客户端超时,主动断连
14:23:12.001 用户投诉:"app 卡死"
```

**对策**:
- Debug 包 dump 即可
- Release 包尽量用 **LeakCanary 后台分析**(只在检测到泄漏时静默 dump)
- **超大规模 app(>500MB 堆)**:用 perfetto_heapprofd 替代

### 7.2 Native 盲区:Bitmap / DirectByteBuffer / JNI 全看不见

**问题**:hprof 只记录 Java 引用,不记录 native 分配。

**典型案例**:
- `Bitmap.createBitmap(1920, 1080)` → Java 端只有 16 字节引用,**像素数据在 native(8MB)**
- `ByteBuffer.allocateDirect(1024 * 1024)` → Java 端 24 字节引用,**buffer 在 native(1MB)**
- `JNI_OnLoad` 注册的全局引用 → 完全在 native

**对策**:
- Bitmap 泄漏 → 转 hprof 后看 `byte[]` 大小(像素数据被 byte[] 持有)
- DirectByteBuffer → 用 `dumpsys meminfo | grep -A 5 Native` 看 native heap
- 真正的 native 追踪 → 用 perfetto_heapprofd native sampling

### 7.3 采样缺失:不能像 perfetto_hprof 那样持续采样

**问题**:hprof 是单次快照,无法回答"内存从什么时候开始涨"。

**示例**:
- ❌ hprof:**"现在堆里有 100MB"**
- ✅ perfetto_heapprofd:**"内存从 14:00 开始每分钟涨 2MB,14:23 达到 100MB"**

**对策**:
- 排查"持续增长"型问题 → 必须用 perfetto_heapprofd(见 [03 篇](03-perfetto_hprof详解.md))
- 排查"峰值异常"型问题 → hprof 够用

---

## 8. 实战:同 OOM 问题 hprof vs 纯 logcat 对比

### 8.1 案例背景

**App**:电商 app,首页有商品瀑布流。
**现象**:用户逛 30 分钟以上必现 OOM 弹窗,被杀后重启。
**已有信息**:`logcat` 显示 `Failed to allocate a 8MB byte buffer`。

### 8.2 纯 logcat 的"看不见"

```
logcat:
  E/art: Throwing OutOfMemoryError "Failed to allocate a 8MB byte buffer"
  W/ActivityManager: Process com.example.app has died (OOM)
```

**用 logcat 能得出的结论**:有 8MB byte 分配失败。
**用 logcat 看不出的**:
- ❓ 这 8MB 是不是商品图片(Bitmap)?
- ❓ 是单个 8MB 还是累积到 8MB?
- ❓ 谁持有这个 buffer?
- ❓ 是 Activity 还是 Fragment 泄漏?

> **结果**:基于 logcat,只能瞎猜"可能是图片缓存太大"。

### 8.3 hprof 的"看得清"

抓一份 hprof(用户崩溃前),用 LeakCanary 自动分析:

**报告关键信息**:
```
HomeActivity has leaked:
  ↑ retained 234.5 MB (84% of total heap)
  ↑ static field mAdapter: ProductListAdapter
  ↑ ProductListAdapter.mBitmapCache: LruCache<String, Bitmap>
  ↑ LruCache contains 87 entries totaling 218.3 MB
  ↑ Bitmap entries:
      - "product_1234_full.jpg" → 4096×4096 → 67.1 MB (Android 13, RGBA_F16)
      - "product_5678_full.jpg" → 4096×4096 → 67.1 MB
      - ...
```

**根因清晰**:
- ProductListAdapter 静态缓存了商品大图
- 静态字段 → 永不回收 → 累计 87 张 4096×4096 图 = 218MB
- 加载高清原图但没按需加载(应该用缩略图)

### 8.4 关键 takeaway

| 工具 | 能看见的 | 看不见的 |
|------|---------|---------|
| **logcat** | 异常类型、错误消息 | 对象关系、持有链、内存大小 |
| **hprof** | **对象关系、持有链、内存大小** | 内存增长过程、native 部分 |

> **实战结论**:遇到 OOM 第一反应**就是 dump hprof**(debug 包直接触发,release 包用 LeakCanary 静默触发)。logcat 只用来"辅助定位时间点",不依赖它做根因分析。

---

## 9. 总结:架构师视角的 5 条 Takeaway

### Takeaway 1:hprof = 内存稳定性的"事故取证"
没有 hprof,OOM 排查基本只能"猜";有了 hprof,**每个泄漏对象都能被精确定位**。它是和 Perfetto trace 平起平坐的"必选第一现场"。

### Takeaway 2:hprof 格式 30 年演进,核心是 HEADER + RECORD + TAG
Android 扩展了 HEAP_DUMP_INFO / HEAP_NAME(0xFE/0xFF)和动态 ID 大小,这是为了支持 **Zygote fork 模型的多 Heap 隔离**。理解这点,才能理解为什么 MAT 能区分"App 自己的内存"和"Zygote 共享的内存"。

### Takeaway 3:三种触发方式各有用武之地
- **Debug.dumpHprofData**:开发自测
- **kill -10**:线上紧急 dump(需要预先 root 或 debuggable)
- **Perfetto heapprofd**:线上持续监控(推荐,见 [03 篇](03-perfetto_hprof详解.md))

### Takeaway 4:三大局限决定 hprof 不是万能的
- **性能开销**:STW 5-30s,**不适合线上频繁使用**
- **Native 盲区**:Bitmap 像素、DirectByteBuffer、JNI 都看不见
- **采样缺失**:只能单次快照,看不到增长过程

### Takeaway 5:工具组合拳才完整
**hprof + LeakCanary + perfetto_heapprofd** = Java 泄漏 + Native 增长 + 全时间维度。三者组合才是完整的内存稳定性工具链。

---

## 附录 A:核心源码路径索引

| 路径 | 作用 |
|------|------|
| `art/runtime/hprof/hprof.cc` | Hprof 核心实现 |
| `art/runtime/hprof/heap_dump.cc` | 堆 dump 序列化 |
| `art/runtime/hprof/hprof.h` | Hprof 类定义 |
| `art/runtime/gc/heap.cc` | Heap::CollectGarbage 触发 |
| `art/runtime/gc/heap_visitor.cc` | GraphVisitor 实现 |
| `frameworks/base/core/java/android/os/Debug.java` | Debug.dumpHprofData API |
| `frameworks/native/cmds/hprof-conv/` | hprof-conv 工具源码 |
| `libcore/luni/src/main/java/java/lang/StackTraceElement.java` | 栈追踪反序列化 |

## 附录 B:hprof TAG 全量表

| TAG (hex) | 名称 | 类别 | 用途 |
|-----------|------|------|------|
| 0x01 | STRING | 文件级 | 字符串常量池 |
| 0x02 | LOAD_CLASS | 文件级 | 类元数据加载 |
| 0x04 | FRAME | Heap Dump | Java 栈帧 |
| 0x05 | TRACE | Heap Dump | 栈追踪 |
| 0x06 | HEAP_DUMP_SEGMENT | 文件级 | Heap 段(分片模式) |
| 0x0C | HEAP_DUMP_END | 文件级 | Heap 结束标记 |
| 0x1C | HEAP_DUMP | 文件级 | Heap(单段模式) |
| 0x2C | HEAP_DUMP_END | 文件级 | 同 0x0C |
| **0xFE** | **HEAP_DUMP_INFO** | **Android 扩展** | **Heap 类型声明** |
| **0xFF** | **HEAP_NAME** | **Android 扩展** | **Heap 名称** |
| 0x01-0x08 | ROOT_* | Heap Dump | GC Root 类型(见 §4.5) |
| 0x20-0x23 | ROOT_* | Heap Dump | 特殊 Root |
| 0xFF | ROOT_JNI_GLOBAL | Heap Dump | 注意:0xFF 在 ROOT 和 HEAP_NAME 间复用,通过上下文区分 |

## 附录 C:量化数据自检表

| 指标 | 典型值 | 说明 |
|------|-------|------|
| hprof dump 耗时(100MB 堆) | 5-15s | STW 时间 |
| hprof dump 耗时(500MB 堆) | 20-60s | 超大堆需考虑 perfetto_heapprofd |
| STRING 记录数 | 50万-200万 | 100MB 堆典型值 |
| INSTANCE 记录数 | 100万-500万 | 同上 |
| 解析 hprof 内存占用 | 堆的 3-5 倍 | LeakCanary/MAT 都需要完整加载 |
| Android Studio 转换耗时 | 1-5s/100MB | hprof-conv 转换 |
| MAT 加载耗时 | 5-30s/100MB | 索引构建 |

## 附录 D:工程基线表

| 项 | 版本/路径 |
|----|---------|
| AOSP 基线 | `android-14.0.0_r1` |
| ART 源码 | `art/runtime/hprof/` |
| LeakCanary | `2.14+` |
| Eclipse MAT | `1.12.0+` |
| hprof-conv 路径 | Android SDK `platform-tools/hprof-conv` |
| Android Studio | Hedgehog (2023.1.1) 或更新 |
| 测试设备 | Pixel 6+ / Android 13+ (Android 12 以下扩展 TAG 不全) |

## 篇尾衔接

**下一篇**:[02-hprof 解析工具链](02-hprof解析工具链.md) 会展开工具方法论——`hprof-conv` / LeakCanary / MAT / hprof-slice 横向对比,工具选型决策树,工程坑位图(LeakCanary 误报 / MAT 加载大文件 OOM)。

**强依赖本篇的章节**:
- 02 §1 会引用本篇 §3 的 hprof 文件结构讲解 `hprof-conv` 转换原理
- 02 §3 会引用本篇 §5 的 ART 生成机制讲解 LeakCanary 为什么能"自动检测泄漏"
- 03 §3 会引用本篇 §4 的 ROOT 记录讲解 perfetto_heapprofd 的采样原理

**本篇不覆盖**(留给后续篇目):
- 具体工具使用命令 → [02](02-hprof解析工具链.md)
- perfetto_hprof 内部实现 → [03](03-perfetto_hprof详解.md)
- 内存泄漏案例库 → [04](04-内存泄漏典型案例与排查SOP.md)
- 内存监控体系搭建 → [05](05-实战：内存监控体系搭建.md)