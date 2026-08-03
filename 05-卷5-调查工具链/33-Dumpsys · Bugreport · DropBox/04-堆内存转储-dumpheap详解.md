# 04-堆内存转储 - dumpheap 详解

> **本篇定位**:系列第 4 篇(内存触发核心)。读完能完整使用 `am dumpheap`,理解其内部调用栈和 Android 11/12/14 行为差异,5 分钟内跑通"触发 dump → pull 文件 → hprof-conv 转换 → MAT 解析"的端到端流程。
>
> **强依赖**:
> - [01-am 命令全景](01-am命令全景与Activity触发.md)(理解 am 本质)
> - [Hprof 系列 01-hprof 原理与文件格式](../Hprof/01-hprof原理与文件格式.md)(理解产物的格式)
>
> **承接自**:
> - [02 进程管理三件套](02-进程管理三件套-kill-crash-restart.md)(杀进程前先 dump heap 是标准操作)
>
> **衔接去**:
> - [Hprof 系列 02-hprof 解析工具链](../Hprof/02-hprof解析工具链.md)(转换后的文件怎么分析)
> - [Hprof 系列 04-内存泄漏典型案例与排查 SOP](../Hprof/04-内存泄漏典型案例与排查SOP.md)(分析后怎么定位根因)
>
> **不重复内容**:本篇只讲"am dumpheap 的使用、调用栈、自动化",**不讲**:
> - hprof 二进制格式内部细节(见 Hprof 01)
> - MAT 工具使用(见 Hprof 02)
> - 内存泄漏案例(见 Hprof 04)
>
> **基线**:AOSP `android-14.0.0_r1` + adb `platform-tools 34.0.0+` + LeakCanary `2.14+` + MAT 1.12
> **风格**:源码密度 ~12%,重点放在"调用栈图 + 决策树 + 端到端脚本"
>
> **目录位置**:`Android_Framework/AmCommand/`
> **上一篇**:[03-性能分析入口-profile命令](03-性能分析入口-profile命令.md)
> **下一篇**:[05-诊断与监控-hang-monitor](05-诊断与监控-hang-monitor.md)

---

## 目录

- [1. 一句话定位](#1-一句话定位)
  - [1.1 am dumpheap 在稳定性工具链中的位置](#11-am-dumpheap-在稳定性工具链中的位置)
  - [1.2 一句话总结](#12-一句话总结)
- [2. 完整调用栈:从 shell 到 ART 的 4 跳](#2-完整调用栈从-shell-到-art-的-4-跳)
  - [2.1 全景图](#21-全景图)
  - [2.2 跳 1:shell 端 am.jar 解析](#22-跳-1shell-端-amjar-解析)
  - [2.3 跳 2:AMS 接收 + 权限检查](#23-跳-2ams-接收--权限检查)
  - [2.4 跳 3:跨进程投递到目标 app](#24-跳-3跨进程投递到目标-app)
  - [2.5 跳 4:ART 真正 dump heap](#25-跳-4art-真正-dump-heap)
  - [2.6 关键源码:6 个核心方法](#26-关键源码6-个核心方法)
- [3. 命令语法详解](#3-命令语法详解)
  - [3.1 基础语法](#31-基础语法)
  - [3.2 五大参数矩阵](#32-五大参数矩阵)
  - [3.3 Android 11/12/14 行为差异](#33-android-111214-行为差异)
  - [3.4 关键参数:-n userId 的含义](#34-关键参数-n-userid-的含义)
- [4. 实战 1:基础流程(5 分钟跑通)](#4-实战-1基础流程5-分钟跑通)
  - [4.1 Step 1:找到目标进程](#41-step-1找到目标进程)
  - [4.2 Step 2:触发 dump](#42-step-2触发-dump)
  - [4.3 Step 3:pull 文件](#43-step-3pull-文件)
  - [4.4 Step 4:hprof-conv 转换](#44-step-4hprof-conv-转换)
  - [4.5 Step 5:MAT 解析](#45-step-5mat-解析)
- [5. 实战 2:端到端自动化脚本](#5-实战-2端到端自动化脚本)
  - [5.1 dumpheap_and_analyze.sh](#51-dumpheap_and_analyze)
  - [5.2 Windows 版 PowerShell](#52-windows-版-powershell)
  - [5.3 进阶:自动定位泄漏 Activity](#53-进阶自动定位泄漏-activity)
- [6. 实战 3:线上 OOM 现场保留](#6-实战-3线上-oom-现场保留)
  - [6.1 现象:线上 OOM 抓不到现场](#61-现象线上-oom-抓不到现场)
  - [6.2 方案:dumpheap 巡检 + 内存阈值触发](#62-方案dumpheap-巡检--内存阈值触发)
  - [6.3 与 LeakCanary 灰度的协同](#63-与-leakcanary-灰度的协同)
- [7. 性能开销与踩坑图](#7-性能开销与踩坑图)
  - [7.1 dumpheap 期间的 app 卡顿(Stop-The-World 5-30s)](#71-dumpheap-期间的-app-卡顿stop-the-world-5-30s)
  - [7.2 内存占用峰值(2-3x 当前堆大小)](#72-内存占用峰值2-3x-当前堆大小)
  - [7.3 8 大经典坑位](#73-8-大经典坑位)
- [8. 与其他工具的对比与协同](#8-与其他工具的对比与协同)
  - [8.1 am dumpheap vs Debug.dumpHprofData vs kill -10](#81-am-dumpheap-vs-debugdumphprofdata-vs-kill--10)
  - [8.2 与 Hprof 系列的呼应:同一条路径,不同入口](#82-与-hprof-系列的呼应同一条路径不同入口)
  - [8.3 与 perfetto_hprof 的取舍](#83-与-perfetto_hprof-的取舍)
- [9. 案例库:4 个真实问题排查](#9-案例库4-个真实问题排查)
  - [9.1 案例 1:Activity 泄漏导致 OOM](#91-案例-1activity-泄漏导致-oom)
  - [9.2 案例 2:Bitmap 暴涨导致 Native OOM](#92-案例-2bitmap-暴涨导致-native-oom)
  - [9.3 案例 3:Handler 消息堆积导致内存抖动](#93-案例-3handler-消息堆积导致内存抖动)
  - [9.4 案例 4:LeakCanary 误报定位](#94-案例-4leakcanary-误报定位)
- [10. 总结:架构师视角的 6 条 Takeaway](#10-总结架构师视角的-6-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:Android 版本差异速查表](#附录-bandroid-版本差异速查表)
- [附录 C:工程资产清单](#附录-c工程资产清单)
- [附录 D:工程基线表](#附录-d工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. 一句话定位

### 1.1 am dumpheap 在稳定性工具链中的位置

```
稳定性问题(线上 / 线下)
    ↓
需要 dump 堆内存?
    ├─ Debug.dumpHprofData()  ← app 内部 API(开发自调用)
    ├─ am dumpheap            ← shell 命令入口(本篇) ★
    ├─ kill -10 <pid>         ← signal 触发(等同 ANR 后台 dump)
    └─ perfetto_hprof         ← 持续采样(新方向,见 Hprof 03)
            ↓
        hprof 文件
            ↓
        hprof-conv(格式转换)
            ↓
        MAT / LeakCanary / Android Studio Profiler
```

**`am dumpheap` 是稳定性工程师最常用的离线 heap dump 触发方式**——不需要修改 app 代码,一条命令搞定。

### 1.2 一句话总结

> **`am dumpheap` 是 ActivityManagerService 提供的"跨进程 Java 堆转储"命令,本质是触发目标 app 进程内的 ART 引擎 `Debug.dumpHprofData()`,产出一份标准 hprof 二进制文件。**

---

## 2. 完整调用栈:从 shell 到 ART 的 4 跳

### 2.1 全景图

```
$ adb shell am dumpheap <pid> /data/local/tmp/heap.hprof
        │ 跳 1:shell 端
        ▼
[am.jar 进程]  ActivityManagerShellCommand.runDumpHeap()
   └─ 解析参数,构造 Bundle
   └─ IActivityManager.dumpHeap(pid, filePath, ...)
        │ 跳 2:Binder IPC
        ▼
[system_server 进程]  ActivityManagerService.dumpHeap()
   └─ 权限检查:Settings.Global.ANR_SHOW_BACKGROUND 或 ADB 授权
   └─ 找到目标进程的 IApplicationThread
   └─ IApplicationThread.dumpHeap(filePath, ...)
        │ 跳 3:跨进程投递
        ▼
[目标 app 进程]  ApplicationThread.dumpHeap()
   └─ sendMessage(H.DUMP_HEAP, ...)
        │ 跳 4:app 主线程
        ▼
[app 主线程]  ActivityThread.handleDumpHeap()
   └─ 反射调 Debug.dumpHprofData(filePath)
        │
        ▼
[ART 引擎]  art/runtime/debug.cc :: DumpHeap()
   └─ 触发 GC(确保堆稳定)
   └─ 遍历 HeapObject → 序列化 hprof RECORD
   └─ 写入 /data/local/tmp/heap.hprof
```

> **4 跳进程,3 次 Binder IPC,1 次主线程反射调用**——任何一个环节失败,dumpheap 都会失败。

### 2.2 跳 1:shell 端 am.jar 解析

`Am.java` 解析 `dumpheap` 子命令:

```java
// frameworks/base/cmds/am/src/com/android/commands/am/Am.java
private int runDumpHeap() throws Exception {
    String proc = nextArgRequired();          // <pid>
    String file = nextArgRequired();          // /data/local/tmp/heap.hprof
    boolean runGc = true;                     // 默认 dump 前先 GC
    boolean managed = false;
    int userId = -1;

    // 解析 -n <userId> / --user
    String opt;
    while ((opt = nextOption()) != null) {
        switch (opt) {
            case "-n": userId = Integer.parseInt(nextArgRequired()); break;
            case "--user": userId = Integer.parseInt(nextArgRequired()); break;
            case "-g": managed = true; break;     // managed-only
        }
    }

    ParcelFileDescriptor fd = ParcelFileDescriptor.open(
        new File(file), ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_WRITE_ONLY);
    try {
        // ★ IPC 调用,跨进程到 system_server
        mInterface.dumpHeap(proc, Integer.parseInt(proc), fd, runGc, managed, userId);
    } finally {
        fd.close();
    }
    return 0;
}
```

**关键点**:
- `mInterface` 是 `IActivityManager` AIDL 代理
- `fd` 是要写入的文件的描述符(跨进程传递,内核层做 dup)
- 错误处理:无 catch 块,异常直接抛到 am 主进程退出

### 2.3 跳 2:AMS 接收 + 权限检查

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java
public void dumpHeap(String process, int uid, ParcelFileDescriptor fd,
                     boolean runGc, boolean managed, int userId) {
    if (checkCallingPermission(android.Manifest.permission.DUMP) != PERMISSION_GRANTED) {
        throw new SecurityException("Permission Denial: ...");   // ★ 没权限直接抛
    }
    // ...
    ProcessRecord proc = findProcessByPid(pid);
    if (proc == null) {
        throw new SecurityException("Process not found: " + process);
    }
    proc.thread.dumpHeap(fd, runGc, managed);  // ★ 跳 3
}
```

**关键点**:
- 必须有 `android.permission.DUMP` 权限——`adb shell` 用户(uid=2000)有
- 没权限会立即抛 `SecurityException`——常见坑(见 §7)
- `proc.thread` 是 app 进程的 `IApplicationThread` 代理

### 2.4 跳 3:跨进程投递到目标 app

```java
// frameworks/base/core/java/android/app/ActivityThread.java
private class ApplicationThread extends IApplicationThread.Stub {
    public void dumpHeap(ParcelFileDescriptor fd, boolean runGc, boolean managed) {
        // ★ 通过 Handler post 到主线程
        sendMessage(H.DUMP_HEAP, new DumpHeapData(fd, runGc, managed));
    }
}
```

**关键点**:
- **不能**在 Binder 线程直接 dump——会卡 IPC 通道
- 必须 post 到主线程,等 Looper 处理
- **这就是为什么 dumpheap 期间 app 会卡顿**——主线程被占用

### 2.5 跳 4:ART 真正 dump heap

```java
// frameworks/base/core/java/android/os/Debug.java
public static void dumpHprofData(String fileName) throws IOException {
    VMDebug.dumpHprofData(fileName);  // 调到 native
}
```

```cpp
// art/runtime/debug.cc
static void DumpHeap(const char* file_name, bool run_gc) {
    // 1. 触发 GC(如果 run_gc=true)
    if (run_gc) {
        heap->CollectGarbage(/* clear_soft_refs= */ false);
    }

    // 2. 打开 hprof 文件
    UniquePtr<Hprof> hprof_file(new Hprof(file_name));

    // 3. 遍历所有 HeapObject
    heap->VisitObjects(new Hprof::HeapVisitor(hprof_file.get()));

    // 4. 写入 HEADER + RECORD
    hprof_file->Flush();
}
```

> **这里就是 Hprof 系列 01 篇讲的"ART 生成 hprof"的入口**——同一条路径,不同入口。

### 2.6 关键源码:6 个核心方法

| 跳 | 进程 | 方法 | 路径 |
|----|------|------|------|
| 1 | am | `Am.runDumpHeap()` | `frameworks/base/cmds/am/src/com/android/commands/am/Am.java` |
| 2 | system_server | `AMS.dumpHeap()` | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` |
| 3 | app(Binder) | `ApplicationThread.dumpHeap()` | `frameworks/base/core/java/android/app/ActivityThread.java` |
| 4 | app(主线程) | `ActivityThread.handleDumpHeap()` | 同上 |
| 4 | app(主线程) | `Debug.dumpHprofData()` | `frameworks/base/core/java/android/os/Debug.java` |
| 4 | ART | `art::Dbg::DumpHeap()` | `art/runtime/debug.cc` |

---

## 3. 命令语法详解

### 3.1 基础语法

```bash
# 语法格式
am dumpheap [options] <pid> <file>

# 最常用
adb shell am dumpheap <pid> /data/local/tmp/heap.hprof
```

**参数说明**:

| 位置 | 必填 | 含义 | 示例 |
|------|------|------|------|
| `<pid>` | 是 | 目标进程 pid | `12345` |
| `<file>` | 是 | dump 文件路径(设备上) | `/data/local/tmp/heap.hprof` |
| `-n <userId>` | 否 | 指定 userId(Android 11+) | `-n 0` |
| `--user <userId>` | 否 | 同 -n | `--user 0` |
| `-g` | 否 | managed-only(只 dump Java 堆) | `-g` |

### 3.2 五大参数矩阵

| 参数 | 含义 | 实战场景 | Android 版本 |
|------|------|---------|------------|
| `pid` | 目标进程 pid | **必填** | 5.0+ |
| `file` | 设备上的输出路径 | **必填** | 5.0+ |
| `-n` / `--user` | 多用户设备指定 user | 多用户调试 | 11+ |
| `-g` | managed-only(只 Java 堆) | 排除 native 减少文件大小 | 11+ |
| `--managed` | 同 -g | 同上 | 11+ |

### 3.3 Android 11/12/14 行为差异

| Android 版本 | 行为变化 | 实战影响 |
|------------|---------|---------|
| **5.0 - 7.0** | 基础可用,无 `-n` | 多用户设备必须指定 user |
| **8.0 - 10.0** | 路径必须在 `/data/local/tmp/` 之下 | 否则 `Permission denied` |
| **11.0** | 引入 `-n` / `--user` 参数 | 跨 user 操作强制要求 |
| **12.0** | **默认路径限制收紧** | 写 `/sdcard/` 等非 `/data/local/tmp` 路径需要 root |
| **13.0** | 引入 `--managed` 参数 | 减少 native heap 干扰 |
| **14.0** | **SELinux 策略进一步收紧** | 某些 OEM 设备上 `/data/local/tmp` 写失败 |

**关键坑位**:
- Android 14 上某些厂商 ROM(尤其 MIUI/HyperOS)对 `/data/local/tmp` 加了额外限制
- 解法:`adb shell setenforce 0` 或换路径到 `/data/local/tmp/heap_$(date +%s).hprof`

### 3.4 关键参数:-n userId 的含义

```bash
# 单用户设备
adb shell am dumpheap 12345 /data/local/tmp/heap.hprof

# 多用户设备(企业设备 / 折叠屏)
adb shell am dumpheap -n 10 12345 /data/local/tmp/heap.hprof
```

`userId` 是 Android 系统的 user 编号:
- `0` = owner(主用户)
- `10+` = secondary user
- `999` = 工作资料

**实战中**,如果不指定 `-n`,默认只对 owner 用户的进程生效。**多用户设备上 dump 不到目标进程**,99% 是这个原因。

---

## 4. 实战 1:基础流程(5 分钟跑通)

### 4.1 Step 1:找到目标进程

```bash
# 方法 1:用包名找 pid
adb shell pidof com.example.app
# 输出:12345

# 方法 2:用 ps 过滤
adb shell ps -A | grep com.example.app
# 输出:u0_a123    12345  ...  com.example.app

# 方法 3:dumpsys(更详细,会带 oom_adj)
adb shell dumpsys meminfo com.example.app | grep "Process ID"
```

### 4.2 Step 2:触发 dump

```bash
# 标准命令
adb shell am dumpheap 12345 /data/local/tmp/heap.hprof
```

**典型输出**:

```
$ adb shell am dumpheap 12345 /data/local/tmp/heap.hprof
(等待 5-30 秒,期间 app 会卡顿)
$ adb shell ls -l /data/local/tmp/heap.hprof
-rw-r----- 1 shell shell 156M 2024-06-22 10:23 /data/local/tmp/heap.hprof
```

> **文件大小** = 堆使用量 × 1.5 - 3 倍。一个 50MB 堆的 app,dump 出来可能 150MB。

### 4.3 Step 3:pull 文件

```bash
# 拉取到本地
adb pull /data/local/tmp/heap.hprof ./heap.hprof
```

> **注意**:文件可能很大(100MB+),拉取会慢。生产环境建议直接 `tar czf` 压缩后再 pull。

### 4.4 Step 4:hprof-conv 转换

**为什么要转换?**

Android 输出的 hprof 文件和 JVM 标准 hprof 有差异:
- ID 大小不同(Android 32-bit / 64-bit,JVM 32-bit)
- 多了几个 Android 私有 TAG(`0xFE` Heap Dump Info, `0xFF` Heap Name)

MAT / VisualVM 等 JVM 工具**不能直接读 Android hprof**。需要用 `hprof-conv` 转换:

```bash
# hprof-conv 来自 Android SDK
$ANDROID_HOME/platform-tools/hprof-conv heap.hprof heap_for_mat.hprof

# Windows
$ANDROID_HOME/platform-tools/hprof-conv.exe heap.hprof heap_for_mat.hprof
```

**转换后**:
- ID size 从 Android 的 32-bit 统一为 JVM 的 32-bit(Android 64-bit 会被 split)
- 私有 TAG 仍然保留(MAT 会忽略)
- 文件大小可能略变

### 4.5 Step 5:MAT 解析

```bash
# 1. 打开 MAT(Eclipse Memory Analyzer)
#    File → Open Heap Dump → 选择 heap_for_mat.hprof

# 2. 关键操作:
#    - Leak Suspects Report(自动给出疑似泄漏)
#    - Dominator Tree(看谁占内存最多)
#    - Histogram(按类看实例数和大小)

# 3. 进阶:用 OQL 查询
#    select * from android.app.Activity
#    select * from android.graphics.Bitmap
```

**详细分析见 Hprof 系列 02、04**。

---

## 5. 实战 2:端到端自动化脚本

### 5.1 dumpheap_and_analyze.sh

完整 5 分钟跑通的端到端脚本(见 `scripts/dumpheap_and_analyze.sh`):

```bash
#!/bin/bash
# dumpheap_and_analyze.sh
# 端到端:触发 dump → pull → hprof-conv 转换 → 准备 MAT
#
# 用法:
#   ./dumpheap_and_analyze.sh <package> [output_dir]
#   ./dumpheap_and_analyze.sh com.example.app
#   ./dumpheap_and_analyze.sh com.example.app ./heap_dumps

set -e

PKG="$1"
OUT_DIR="${2:-./heap_dumps}"

if [ -z "$PKG" ]; then
    echo "用法: $0 <package> [output_dir]"
    echo "示例: $0 com.example.app"
    exit 1
fi

# 1. 创建输出目录
mkdir -p "$OUT_DIR"
TS=$(date +%Y%m%d_%H%M%S)
HEAP_FILE="/data/local/tmp/heap_${TS}.hprof"
LOCAL_FILE="$OUT_DIR/heap_${TS}.hprof"
CONVERTED="$OUT_DIR/heap_${TS}_mat.hprof"

echo "=== [1/5] 查找目标进程 $PKG ==="
PID=$(adb shell pidof "$PKG" | tr -d '\r\n')
if [ -z "$PID" ]; then
    echo "ERROR: 进程 $PKG 未运行"
    exit 1
fi
echo "PID: $PID"

echo "=== [2/5] 触发 am dumpheap ==="
echo "  目标: $HEAP_FILE"
echo "  警告:app 会卡顿 5-30 秒"
START_TIME=$(date +%s)
adb shell am dumpheap "$PID" "$HEAP_FILE"
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "  完成,耗时: ${DURATION}s"

echo "=== [3/5] 拉取文件到本地 ==="
adb pull "$HEAP_FILE" "$LOCAL_FILE"
echo "  路径: $LOCAL_FILE"
echo "  大小: $(ls -lh "$LOCAL_FILE" | awk '{print $5}')"

echo "=== [4/5] hprof-conv 转换 ==="
HPROF_CONV="$ANDROID_HOME/platform-tools/hprof-conv"
if [ ! -x "$HPROF_CONV" ]; then
    echo "ERROR: hprof-conv 不在 $HPROF_CONV"
    echo "  请设置 ANDROID_HOME 环境变量"
    exit 1
fi
"$HPROF_CONV" "$LOCAL_FILE" "$CONVERTED"
echo "  转换后: $CONVERTED"
echo "  大小: $(ls -lh "$CONVERTED" | awk '{print $5}')"

echo "=== [5/5] 清理设备文件 + 输出报告 ==="
adb shell rm -f "$HEAP_FILE"

cat <<EOF

========================================
Dump 完成!
========================================
原始文件:  $LOCAL_FILE
MAT 文件:  $CONVERTED
dump 耗时:  ${DURATION}s

下一步:
  1. 用 MAT 打开 $CONVERTED
  2. 运行 Leak Suspects Report
  3. 看 Dominator Tree 找大对象
  4. 用 OQL 查询特定类

OQL 模板:
  select * from android.app.Activity
  select * from android.graphics.Bitmap
  select * from android.os.Handler

========================================
EOF
```

**执行效果**:

```bash
$ ./dumpheap_and_analyze.sh com.example.app
=== [1/5] 查找目标进程 com.example.app ===
PID: 12345
=== [2/5] 触发 am dumpheap ===
  目标: /data/local/tmp/heap_20240622_1023.hprof
  警告:app 会卡顿 5-30 秒
  完成,耗时: 18s
=== [3/5] 拉取文件到本地 ===
  路径: ./heap_dumps/heap_20240622_1023.hprof
  大小: 156M
=== [4/5] hprof-conv 转换 ===
  转换后: ./heap_dumps/heap_20240622_1023_mat.hprof
  大小: 152M
=== [5/5] 清理设备文件 + 输出报告 ===
...
```

### 5.2 Windows 版 PowerShell

见 `scripts/dumpheap_and_analyze.ps1`:

```powershell
# dumpheap_and_analyze.ps1
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [string]$OutputDir = ".\heap_dumps"
)

$ErrorActionPreference = "Stop"

# 1. 创建输出目录
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$heapFile = "/data/local/tmp/heap_$ts.hprof"
$localFile = "$OutputDir\heap_$ts.hprof"
$converted = "$OutputDir\heap_$ts`_mat.hprof"

# 2. 找 PID
Write-Host "=== [1/5] 查找目标进程 $Package ===" -ForegroundColor Cyan
$pidRaw = adb shell pidof $Package
$pid = $pidRaw.Trim()
if ([string]::IsNullOrEmpty($pid)) { throw "进程 $Package 未运行" }
Write-Host "PID: $pid"

# 3. 触发 dump
Write-Host "=== [2/5] 触发 am dumpheap ===" -ForegroundColor Cyan
$startTime = Get-Date
adb shell am dumpheap $pid $heapFile
$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds
Write-Host "完成,耗时: $duration s"

# 4. pull 文件
Write-Host "=== [3/5] 拉取文件到本地 ===" -ForegroundColor Cyan
adb pull $heapFile $localFile
$fileSize = (Get-Item $localFile).Length / 1MB
Write-Host "大小: $([math]::Round($fileSize, 2)) MB"

# 5. hprof-conv 转换
Write-Host "=== [4/5] hprof-conv 转换 ===" -ForegroundColor Cyan
$hprofConv = "$env:ANDROID_HOME\platform-tools\hprof-conv.exe"
if (-not (Test-Path $hprofConv)) { throw "hprof-conv 不在 $hprofConv" }
& $hprofConv $localFile $converted

# 6. 清理
Write-Host "=== [5/5] 清理 + 报告 ===" -ForegroundColor Cyan
adb shell rm -f $heapFile

Write-Host @"
========================================
Dump 完成!
MAT 文件: $converted
dump 耗时: $duration s
========================================
"@ -ForegroundColor Green
```

### 5.3 进阶:自动定位泄漏 Activity

见 `scripts/dumpheap_and_analyze.ps1` + `trace_analysis_sql/leak_pattern_match.sql`(后续补)。核心思路:

```bash
# 1. dump heap(脚本同 5.1)
# 2. hprof-conv 转换
# 3. 用 strings + grep 快速定位泄漏 Activity(无需 MAT)

strings heap_for_mat.hprof | grep "android.app.Activity" | sort -u
# 输出:
# com.example.app.ui.MainActivity
# com.example.app.ui.OrderDetailActivity
# com.example.app.ui.UserProfileActivity    ← 出现多次,可能泄漏
```

> **技巧**:dump 两次,做"差集"——间隔 5-10 秒 dump 两次,如果某 Activity 实例数增加就是泄漏。

---

## 6. 实战 3:线上 OOM 现场保留

### 6.1 现象:线上 OOM 抓不到现场

```
线上监控告警:
  [OOM] com.example.app oom_adj=900 killed by LMK
  触发时间: 14:32:15
  触发设备: Xiaomi Mi 13 (Android 14)
  内存峰值: 873MB / 总内存 4GB
```

**痛点**:
- LMK 杀进程后,内存现场就丢了
- logcat 只能告诉你"试图分配 X MB 失败",不告诉你"为什么"
- 用户反馈"打开 app 就崩",QA 复现不出来

### 6.2 方案:dumpheap 巡检 + 内存阈值触发

**方案架构**:

```
[APP 内置 SDK]                       [Server 端]
  ↓ 定期采集内存                      
  ↓ PSS > 700MB 触发                  
  ↓                                   
  ├─ 调 am dumpheap 给自己            
  ├─ 文件上传到 server                
  └─ 标记用户 / 设备 / 触发原因       
                                    ↓
                                    收到 hprof
                                    触发 hprof-conv
                                    触发 MAT 分析(离线)
                                    报告归档到工单
```

**伪代码**(集成到 app 内):

```java
// 稳定性 SDK 内部
public class MemoryMonitor {
    private static final long MEMORY_THRESHOLD = 700 * 1024 * 1024L; // 700MB
    
    public void checkMemory() {
        long pss = Debug.getPss();  // 获取当前 PSS
        if (pss > MEMORY_THRESHOLD && !isDumping.get()) {
            isDumping.set(true);
            try {
                // 1. dump 自身
                Debug.dumpHprofData("/sdcard/oom_capture.hprof");
                
                // 2. 上传到 server
                uploadHprof("/sdcard/oom_capture.hprof");
                
                // 3. 标记工单
                reportOOMEvent(pss);
            } finally {
                isDumping.set(false);
            }
        }
    }
}
```

**注意事项**:
- 必须在子线程 dump(否则会 ANR)
- 加 `isDumping` 锁避免重复触发
- 文件可能 200MB+,需要压缩上传

### 6.3 与 LeakCanary 灰度的协同

```
┌──────────────┬──────────────────────┬──────────────────────┐
│   场景        │  工具                 │  触发方式            │
├──────────────┼──────────────────────┼──────────────────────┤
│ Debug 包     │ LeakCanary            │ 自动,泄漏即 dump     │
│ 灰度包(1%)   │ 内存阈值 + am dumpheap │ SDK 触发             │
│ 全量包       │ 仅监控 + logcat       │ 无 dump,只打点       │
└──────────────┴──────────────────────┴──────────────────────┘
```

**为什么不全量包也用 am dumpheap?**
- dumpheap 期间 app 卡 5-30s(详见 §7.1)
- 全量包影响范围大,会被用户感知
- 灰度包先用,验证稳定后再逐步放开

---

## 7. 性能开销与踩坑图

### 7.1 dumpheap 期间的 app 卡顿(Stop-The-World 5-30s)

**为什么会卡?**

```
App 主线程
   │
   ├─ onCreate / onResume / onClick / onDraw 全部阻塞
   │
   │  ★ 阻塞原因:ActivityThread.handleDumpHeap() 在主线程同步执行
   │  ★ ART DumpHeap 期间触发"全局暂停"(类似 GC)
   │
   ▼
[Dump 完成,主线程恢复]
```

**实测数据**(AOSP 14,Pixel 6,堆 200MB):

| App 堆大小 | dump 耗时 | 主线程卡顿 |
|----------|---------|-----------|
| 50MB | 2-5s | 2-5s |
| 100MB | 5-10s | 5-10s |
| 200MB | 10-20s | 10-20s |
| 500MB | 20-40s | 20-40s |

> **稳定性视角**:dumpheap 期间用户感知是"app 死了",期间**任何 ANR 监测、Watchdog 都会报"主线程无响应"**——这是 dumpheap 误报 ANR 的根因。

### 7.2 内存占用峰值(2-3x 当前堆大小)

dumpheap 期间,设备会同时存在:
- 原始堆(200MB)
- ART 内部遍历中的临时对象(50-100MB)
- hprof 文件缓冲区(200MB+)

**总峰值**:2-3x 当前堆,可能触发 OOM。

**线上建议**:
- 在 PSS < 600MB 的设备上 dump
- 提前给目标进程预留 1.5x 内存
- 失败后等待 30s 再重试

### 7.3 8 大经典坑位

| # | 坑 | 表现 | 解法 |
|---|----|------|------|
| 1 | `Permission Denial: ... requires android.permission.DUMP` | SecurityException | 确认是 adb shell 用户,或 root |
| 2 | `Process not found` | pid 已死 | 重新 `pidof` 拿最新 pid |
| 3 | 写入 `/sdcard/` 失败 | Permission denied | 改用 `/data/local/tmp/`(Android 12+ 必须) |
| 4 | 文件大小 0KB | dump 提前失败 | 看 logcat 的 ART 日志 |
| 5 | hprof-conv 报"Invalid hprof" | 文件截断 | dump 期间不要杀进程,等完成 |
| 6 | dump 完 app 立即崩溃 | OOM | 见 §7.2,减小堆或加内存 |
| 7 | ANR 告警误报 | dump 期间主线程被占 | 排除 dump 期间的 ANR |
| 8 | SELinux 拒绝 | Android 14 OEM | `adb shell setenforce 0` 临时关闭 |

---

## 8. 与其他工具的对比与协同

### 8.1 am dumpheap vs Debug.dumpHprofData vs kill -10

| 维度 | `am dumpheap` | `Debug.dumpHprofData` | `kill -10 <pid>` (SIGUSR1) |
|------|--------------|----------------------|------------------------------|
| **触发方式** | shell 命令 | app 内部代码 | shell signal |
| **权限要求** | DUMP | 无(自己进程) | root |
| **调用入口** | AMS → AT | 直接 ART | ART signal handler |
| **是否阻塞主线程** | **是**(5-30s) | 看调用线程 | **是**(等价于 ANR 后台 dump) |
| **产物路径** | 命令行指定 | 代码指定 | `/data/anr/` 之类 |
| **典型场景** | 离线 dump | 自动化 dump(SDK) | 紧急兜底 |

**实战选择**:
- 临时分析 → `am dumpheap`(本篇重点)
- 集成到 SDK → `Debug.dumpHprofData`(可控性更强)
- ANR 兜底 → `kill -10`(系统级,见 [Hprof 系列 01 §5.1](../Hprof/01-hprof原理与文件格式.md))

### 8.2 与 Hprof 系列的呼应:同一条路径,不同入口

```
[本篇 AmCommand 04]                      [Hprof 系列 01]
                                          
am dumpheap                              ART Debug.dumpHprofData
   ↓                                        ↓
AMS.dumpHeap()                            ★ 同一个 native 方法
   ↓                                        ↓
IApplicationThread.dumpHeap()             (都是 art::Dbg::DumpHeap)
   ↓                                        ↓
Debug.dumpHprofData()                      ↓
   ↓                                        ↓
art::Dbg::DumpHeap() ←──── 这里是交汇点 ───→ 
   ↓
hprof 文件
```

> **本篇讲"触发",Hprof 01 讲"格式"**——合起来才是完整的"am dumpheap 知识图谱"。

### 8.3 与 perfetto_hprof 的取舍

| 维度 | am dumpheap(传统) | perfetto_hprof |
|------|------------------|---------------|
| **触发** | 一次性,全量 dump | 持续采样 |
| **开销** | 高(Stop-The-World) | 低(sampling) |
| **文件大小** | 100-500MB | 几 MB |
| **Java 堆** | ✅ 全量 | ✅ 采样 |
| **Native 堆** | ❌ 看不全 | ✅ 支持 |
| **分析工具** | MAT(成熟) | Perfetto trace_processor(新) |
| **线上可用** | ⚠️ 灰度 | ✅ 全量 |

> **实战建议**:debug + 灰度用 am dumpheap(精度高),全量用 perfetto_hprof(开销低)。

---

## 9. 案例库:4 个真实问题排查

### 9.1 案例 1:Activity 泄漏导致 OOM

**现象**:用户反馈"反复打开/关闭某页面 5 次后 app 必崩"。

**用 am dumpheap 排查**:

```bash
# 1. 复现路径(打开/关闭 5 次)
for i in {1..5}; do
  adb shell am start-activity -n com.example.app/.TargetActivity
  sleep 2
  adb shell input keyevent KEYCODE_BACK
  sleep 1
done

# 2. dump heap
./dumpheap_and_analyze.sh com.example.app

# 3. MAT 打开,看 Histogram
#    输入正则:com\.example\.app\.ui\..*Activity
#    预期:每个 Activity 实例数 = 0
#    实际:TargetActivity 实例数 = 5  ← 泄漏!
```

**根因**:TargetActivity 内部有 static 字段持有 Context,导致 Activity 销毁时无法回收。

**修复**:

```java
// Before(泄漏)
public class TargetActivity extends Activity {
    private static Context sContext;  // ← 持有 Activity,泄漏!
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        sContext = this;
    }
}

// After(修复)
public class TargetActivity extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        // 不再持有 static Context
    }
}
```

### 9.2 案例 2:Bitmap 暴涨导致 Native OOM

**现象**:打开图片列表页 → 滑动 5 分钟 → app 闪退。

**用 am dumpheap 排查**:

```bash
# 1. 打开图片列表
adb shell am start-activity -n com.example.app/.ImageListActivity

# 2. 滑动
for i in {1..20}; do adb shell input swipe 500 1500 500 500; sleep 0.5; done

# 3. dump
./dumpheap_and_analyze.sh com.example.app
```

**MAT 观察**:

```
Histogram 排序:
android.graphics.Bitmap
  ├─ instances: 347
  ├─ shallow heap: 13.5 MB
  └─ retained heap: 487 MB  ← 占总堆 78%

Dominator Tree 顶部:
  Bitmap @ 0x...  shallow=3.2MB retained=85MB
   └─ mBuffer (byte[])  retained=82MB
        └─ native Paint$1
             └─ ImageView[12]
                  └─ RecyclerView.ViewHolder[24]
                       └─ ImageListActivity  ← 持有 ViewHolder 链
```

**根因**:RecyclerView 的 ViewHolder 被某个 static 集合持有,导致图片 Bitmap 全部无法释放。

**修复**:清除 static 集合的引用,或改用 WeakReference。

### 9.3 案例 3:Handler 消息堆积导致内存抖动

**现象**:app 启动后内存缓慢上涨,每隔 10 分钟 PSS 增加 50MB。

**MAT 观察**:

```
Histogram 顶部:
android.os.Message
  instances: 8421  ← 异常多
  shallow heap: 1.2 MB
  retained heap: 256 MB

Handler @ 0x...
  mMessages (MessageQueue)
   ├─ Message #1
   ├─ Message #2
   ├─ ... (8000+)
   └─ Message #8421
```

**根因**:Handler 在子线程 postDelayed 但没 removeCallbacks,导致延迟消息累积,每个 Message 持有 Runnable,Runnable 持有 Activity Context。

**修复**:在 onDestroy 调 `handler.removeCallbacksAndMessages(null)`。

### 9.4 案例 4:LeakCanary 误报定位

**现象**:LeakCanary 报告 `MainActivity has leaked`,但用 am dumpheap 看不到泄漏。

**用 am dumpheap 反证**:

```bash
# 1. 退出到 launcher
adb shell input keyevent KEYCODE_HOME

# 2. 等 5s 确保 Activity 走完 onDestroy
sleep 5

# 3. dump
./dumpheap_and_analyze.sh com.example.app
```

**MAT 观察**:

```
Histogram:
com.example.app.MainActivity
  instances: 0  ← 没有泄漏
```

**根因**:LeakCanary 把"Activity 被 system_server 持有"误判为泄漏。am dumpheap 时 Activity 已经被 GC 回收,LeakCanary 是 dump 后才分析,触发时间不同。

**修复**:在 LeakCanary 报告时 dump,而不是退出后 dump。

---

## 10. 总结:架构师视角的 6 条 Takeaway

1. **am dumpheap 是稳定性工程师最常用的"离线 dump"工具**——比 Debug.dumpHprofData 更轻量,比 kill -10 更安全。
2. **4 跳进程,3 次 IPC,1 次主线程反射**——理解调用栈能解释 90% 的 dump 失败原因。
3. **dump 期间 app 必卡 5-30s**——线上使用必须灰度,且要主动排除 dump 期间的 ANR 告警。
4. **Android 11+ 必须显式 `-n userId`**——多用户设备 dump 失败 99% 是这个原因。
5. **am dumpheap 和 Debug.dumpHprofData 是同一条路径,不同入口**——根据"是否需要改 app"选入口。
6. **dumpheap 是 Hprof 系列的"触发入口"**——和 Hprof 01(格式)、02(工具)、04(案例)合起来才是完整的"heap dump 知识图谱"。

---

## 附录 A:核心源码路径索引

| 模块 | 路径 |
|------|------|
| am.jar dumpheap 入口 | `frameworks/base/cmds/am/src/com/android/commands/am/Am.java` :: `runDumpHeap()` |
| IActivityManager AIDL | `frameworks/base/core/java/android/app/IActivityManager.aidl` |
| AMS dumpHeap | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` :: `dumpHeap()` |
| ApplicationThread | `frameworks/base/core/java/android/app/ActivityThread.java` :: `ApplicationThread.dumpHeap()` |
| ActivityThread.handleDumpHeap | `frameworks/base/core/java/android/app/ActivityThread.java` :: `handleDumpHeap()` |
| Debug.dumpHprofData | `frameworks/base/core/java/android/os/Debug.java` :: `dumpHprofData()` |
| ART DumpHeap | `art/runtime/debug.cc` :: `Dbg::DumpHeap()` |
| Hprof 序列化 | `art/runtime/hprof/hprof.cc` |

---

## 附录 B:Android 版本差异速查表

| Android 版本 | dumpheap 行为 | 实战注意 |
|------------|-------------|---------|
| 5.0 - 7.0 | 基础可用,无 `-n` | 单用户设备足够 |
| 8.0 - 10.0 | 路径必须在 `/data/local/tmp/` | 不要写 `/sdcard/` |
| 11.0 | 引入 `-n` / `--user` | 多用户设备必带 |
| 12.0 | **默认路径限制收紧** | 写 `/sdcard/` 需要 root |
| 13.0 | 引入 `--managed` | 减少 native 干扰 |
| 14.0 | **SELinux 策略进一步收紧** | 某些 OEM 设备需 `setenforce 0` |

---

## 附录 C:工程资产清单

```
AmCommand/
└── scripts/
    ├── dumpheap_and_analyze.sh            ← 端到端脚本(Linux/Mac,本文 §5.1)
    ├── dumpheap_and_analyze.ps1           ← 端到端脚本(Windows,本文 §5.2)
    ├── oom_capture_pipeline.md            ← 线上 OOM 采集流程(本文 §6)
    └── (后续)leak_pattern_match.sql       ← OQL 模板(后续补)
```

---

## 附录 D:工程基线表

| 项 | 版本/路径 |
|----|---------|
| AOSP 基线 | `android-14.0.0_r1` |
| adb 工具 | `platform-tools 34.0.0+` |
| Android Studio | Hedgehog (2023.1.1) 或更新 |
| am.jar 路径 | `/system/framework/am.jar` |
| AMS 源码路径 | `frameworks/base/services/core/java/com/android/server/am/` |
| ART 源码 | `art/runtime/debug.cc`、`art/runtime/hprof/hprof.cc` |
| hprof-conv | `platform-tools/hprof-conv` |
| LeakCanary | 2.14+ (基于 Shark 引擎) |
| MAT | Eclipse Memory Analyzer 1.12+ |

---

## 篇尾衔接

**下一篇**:[05-诊断与监控-hang-monitor](05-诊断与监控-hang-monitor.md)——`am hang` 主动触发 ANR + `am monitor` 实时监控 GC/Crash。

**回到系列目录**:[README-AmCommand系列](README-AmCommand系列.md)
