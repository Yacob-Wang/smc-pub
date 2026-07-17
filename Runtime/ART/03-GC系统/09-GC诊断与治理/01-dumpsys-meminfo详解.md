# 9.1 dumpsys meminfo 全字段解读

> **本节回答一个根本问题**：dumpsys meminfo 的每个字段代表什么？怎么从 dumpsys meminfo 判断内存状态？
>
> **答案**：**dumpsys meminfo 是 ART 内存信息的官方诊断工具** —— 解读每个字段是 GC 排查的第一步。

---

## 一、dumpsys meminfo 基础

### 9.1.1 命令格式

```bash
adb shell dumpsys meminfo <package_name>
# 或
adb shell dumpsys meminfo -d <package_name>  # 详细模式
adb shell dumpsys meminfo -h                  # 帮助
```

### 9.1.2 输出结构

```
$ adb shell dumpsys meminfo com.example.app

# 顶部：App 基础信息
# 中部：内存分类（Native / Dalvik / Stack / Graphics / Code / ...）
# 底部：对象分布（Views / AppContexts / Activities / Assets / ...）
```

---

## 二、完整输出解读

### 9.1.3 完整输出示例

```
$ adb shell dumpsys meminfo com.example.app
Applications Memory Usage (kB):
Uptime: 1234567 Realtime: 1234567

** MEMINFO in pid 12345 [com.example.app] **
                   Pss  Private  Private  SwapPss      Rss     Heap     Heap     Heap
                 Total    Dirty    Clean    Dirty    Total     Size    Alloc     Free
                ------   ------   ------   ------   ------   ------   ------   ------
  Native Heap    12345    10000     2345      100    15000   102400    87654    14746
  Dalvik Heap    45678    40000     5678      200    51234    65536    45678    19858
   Stack          1500     1400      100        0     1700
   Cursor           50       40       10        0       60
   Ashmem         2000     1500      500        0     2300
   Other dev       300      200      100        0      350
    .so mmap      6789     5000     1789        0     8500
    .jar mmap      500      400      100        0      600
    .apk mmap     1200      800      400        0     1500
    .ttf mmap       200      150       50        0      250
    .dex mmap     3000     2000     1000        0     3500
   Other mmap      800      500      300        0      900
   TOTAL         81901    63890    17822      300   96844  102400    87654    14746

Objects
               Views:       45         ViewRootImpl:        1
         AppContexts:        4           Activities:        1
              Assets:       12        AssetManagers:        0
       Local Binders:       18        Proxy Binders:       24
       Parcel memory:        2         Parcel count:       12
    Death Recipients:        0      OpenSSL Sockets:        1
            WebViews:        0

SQL
               MEMINFO_DB:        0
```

### 9.1.4 列的含义

```
Pss Total    : 实际使用的物理内存（按比例分摊共享库）
Private Dirty: 进程独占的脏页（已被修改的内存）
Private Clean: 进程独占的干净页（未修改但独占的内存）
SwapPss Dirty: 换出的内存（按比例分摊）
Rss Total    : 实际占用的物理内存（含共享库）
Heap Size    : 堆的总大小
Heap Alloc   : 堆已分配（使用）的部分
Heap Free    : 堆空闲的部分
```

---

## 三、各分类详解

### 9.1.5 Native Heap

```
Native Heap    12345    10000     2345      100    15000   102400    87654    14746
              ↑↑↑↑↑   ↑↑↑↑↑↑↑  ↑↑↑↑↑    ↑↑↑    ↑↑↑↑↑↑  ↑↑↑↑↑↑↑↑  ↑↑↑↑↑↑↑  ↑↑↑↑↑↑↑
              PSS     Dirty    Clean    Swap    RSS     Size     Alloc    Free

含义：
- libc malloc 分配的 native 内存
- .so 库的 native 代码
- DirectByteBuffer 的 native 像素
- Bitmap 的 native 像素
- JNI 分配的 native 对象
```

### 9.1.6 Dalvik Heap

```
Dalvik Heap    45678    40000     5678      200    51234    65536    45678    19858
              ↑↑↑↑↑↑  ↑↑↑↑↑↑↑  ↑↑↑↑↑    ↑↑↑    ↑↑↑↑↑↑  ↑↑↑↑↑↑↑↑  ↑↑↑↑↑↑↑  ↑↑↑↑↑↑↑
              PSS      Dirty    Clean    Swap    RSS      Size      Alloc    Free

含义：
- Java 堆使用情况
- Heap Size = 当前堆总大小（64 MB 默认）
- Heap Alloc = 已分配（使用）的部分
- Heap Free = 空闲的部分

→ 真实 OOM 时：Heap Alloc ≈ Heap Size
→ 碎片化 OOM 时：Heap Alloc << Heap Size
```

### 9.1.7 Stack

```
Stack          1500     1400      100        0     1700

含义：
- 线程栈占用的内存
- 默认每线程 1 MB
- 线程数过多 → Stack 占用大

诊断：
- Stack > 5 MB/线程 → 异常（线程数过多）
- Stack > 50 MB → 紧急（可能线程泄漏）
```

### 9.1.8 Cursor / Ashmem / Other dev

```
Cursor           50       40       10        0       60

含义：
- Cursor 占用的内存（数据库查询）
- 忘记 close 的 Cursor 会累积

Ashmem         2000     1500      500        0     2300

含义：
- Ashmem 共享内存
- Surface / Bitmap 共享

Other dev       300      200      100        0      350

含义：
- 其他设备内存
```

### 9.1.9 .so / .jar / .apk / .dex mmap

```
.so mmap       6789     5000     1789        0     8500
.jar mmap       500      400      100        0      600
.apk mmap      1200      800      400        0     1500
.dex mmap      3000     2000     1000        0     3500
.ttf mmap       200      150       50        0      250

含义：
- .so mmap：.so 库占用的 mmap 内存
- .jar mmap：.jar 文件
- .apk mmap：APK 文件
- .dex mmap：DEX 文件
- .ttf mmap：字体文件

诊断：
- .so mmap > 30 MB → 异常（太多 .so 库）
- .dex mmap > 50 MB → 异常（DEX 太多）
```

### 9.1.10 TOTAL

```
TOTAL         81901    63890    17822      300   96844  102400    87654    14746
              ↑↑↑↑↑↑  ↑↑↑↑↑↑↑  ↑↑↑↑↑↑↑  ↑↑↑↑↑  ↑↑↑↑↑↑↑
              PSS 总   Private  Private   Swap    RSS

含义：
- 进程总内存占用
- PSS 是按比例分摊后的真实占用

诊断：
- TOTAL PSS > 500 MB → 警告（内存压力大）
- TOTAL PSS > 1 GB → 紧急（即将被 LMK 杀）
```

---

## 四、Heap 字段的精确解读

### 9.1.11 Heap Size / Alloc / Free 的关系

```
Dalvik Heap    45678    40000     5678      200    51234    65536    45678    19858
                                                              ↑↑↑↑↑↑↑↑  ↑↑↑↑↑↑↑  ↑↑↑↑↑↑↑
                                                              Size      Alloc     Free

关系：
Heap Size = Heap Alloc + Heap Free + 内部开销
           65536    =    45678   +  19858  + 0
           65536    ≈    65536 ✓

→ 当前堆总大小 64 MB（65536 KB）
→ 已分配 45.6 MB（45678 KB）
→ 空闲 19.4 MB（19858 KB）
→ 使用率 = 45678 / 65536 = 69.7%
```

### 9.1.12 真实 OOM vs 碎片化 OOM 的判断

```
情况 1：真实 OOM（堆真的满了）
  Heap Size:   65536
  Heap Alloc:  65000  ← 接近 Heap Size
  Heap Free:   536
  → 真实 OOM，需要修复泄漏

情况 2：碎片化 OOM（堆还有空闲但碎片化）
  Heap Size:   65536
  Heap Alloc:  30000  ← 远小于 Heap Size
  Heap Free:   35536
  → 碎片化 OOM，需要优化 Bitmap / byte[] 等大对象管理
```

---

## 五、对象分布字段

### 9.1.13 Views / Activities

```
Views:       45         ViewRootImpl:        1
AppContexts:        4           Activities:        1

含义：
- Views：当前 Activity 中的 View 数量（包含所有子 View）
- ViewRootImpl：根 View 数量（通常 = Activity 数量）
- AppContexts：Application Context 数量（通常 = 1 + 服务数）
- Activities：Activity 数量

诊断：
- Views > 1000 → 异常（View 层级过深）
- Activities > 5 → 可能 Activity 泄漏
```

### 9.1.14 Assets / AssetManagers

```
Assets:       12        AssetManagers:        0

含义：
- Assets：资源加载器数量（Bitmap / Drawable）
- AssetManagers：AssetManager 实例数

诊断：
- Assets > 100 → 异常（资源加载过多）
```

### 9.1.15 Binders / Parcel

```
Local Binders:       18        Proxy Binders:       24
Parcel memory:        2         Parcel count:       12

含义：
- Local Binders：本地 Binder 引用数
- Proxy Binders：远程 Binder 引用数
- Parcel memory：Parcel 内存（IPC 用）
- Parcel count：Parcel 数量

诊断：
- Binders > 100 → 可能 Binder 泄漏
- Parcel memory > 10 MB → 异常（IPC 数据大）
```

---

## 六、dumpsys meminfo 的工程使用

### 9.1.16 排查 OOM 流程

```
1. dumpsys meminfo 看 Heap Alloc
   │
2. Heap Alloc ≈ Heap Size → 真实 OOM
   │
3. Heap Alloc << Heap Size → 碎片化 OOM
   │
4. hprof 分析
   │
5. 修复 + 监控
```

### 9.1.17 监控内存趋势

```bash
# 1. 定期采集 dumpsys meminfo
while true; do
    adb shell dumpsys meminfo <package> | grep "TOTAL PSS"
    sleep 60
done > memory_trend.log

# 2. 看趋势
cat memory_trend.log
# 输出示例：
#   TOTAL PSS: 234567 → 持续增长 → 内存泄漏
```

### 9.1.18 多个 App 的内存对比

```bash
# 1. 看系统所有进程的内存
adb shell dumpsys meminfo

# 2. 看具体 App 的详细内存
adb shell dumpsys meminfo -d <package>

# 3. 看进程排名
adb shell procrank  # 见 9.2 节
```

---

## 七、dumpsys meminfo 的限制

### 9.1.19 dumpsys meminfo 不显示的内容

```
dumpsys meminfo 不显示：

1. LOS（Large Object Space）大对象详情
   - 只能看到 LOS 总占用
   - 不能看到具体哪个 Bitmap 占用了 LOS

2. 跨进程内存引用
   - Bitmap / Surface 等跨进程共享
   - 看不到对方进程的引用

3. Java 对象的具体类型
   - 不知道哪个 Bitmap 占内存最大
   - 需要 hprof + MAT 分析

→ dumpsys meminfo 是"内存概览"，详细分析需要 hprof
```

---

## 八、本节小结

1. **dumpsys meminfo 是 ART 内存诊断的基础工具**
2. **关键字段**：Heap Size / Alloc / Free（Java 堆）、Native Heap（native 内存）、TOTAL（总内存）
3. **OOM 判断**：Heap Alloc ≈ Heap Size = 真实 OOM；Heap Alloc << Heap Size = 碎片化 OOM
4. **工程使用**：定期采集 + 趋势分析 + 对比
5. **限制**：不显示 LOS 详情，需要 hprof + MAT

→ **理解 dumpsys meminfo，就掌握了"看内存状态"的基础工具**。

---

## 跨节引用

**本节被以下章节引用**：
- [9.9 实战案例 1](./09-实战案例1-dumpsys诊断.md) —— dumpsys meminfo 实战
- 02 篇 2.2 5 Space 详解 —— LOS
- 03/04/05 篇 —— 各 GC 时代的 OOM 排查

**本节引用**：
- 02 篇 2.1 Heap 总览 —— Heap 类
- 06 篇 Reference —— DirectByteBuffer
