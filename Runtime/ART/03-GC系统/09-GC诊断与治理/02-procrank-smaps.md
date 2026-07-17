# 9.2 procrank 与 smaps

> **本节回答一个根本问题**：procrank 和 smaps 是什么？怎么用它们找进程内最大内存？
>
> **答案**：**procrank 看进程排名，smaps 看进程内存详情** —— 两者互补。

---

## 一、procrank 详解

### 9.2.1 procrank 的定义

```
procrank：
- 输出所有进程的内存排名
- 按 PSS 排序
- 快速定位内存大户
```

### 9.2.2 procrank 命令

```bash
adb shell procrank

# 输出示例：
#   PID       Vss      Rss      Pss      Uss  Swap    SwapPSs      FD    Process
#  12345   512MB    234MB    123MB     98MB      0         0     256  com.example.app
#   1234   256MB    123MB     80MB     65MB      0         0     100  com.android.systemui
#   5678   128MB     80MB     50MB     40MB      0         0      50  com.android.launcher
```

### 9.2.3 procrank 字段

```
PID：进程 ID
Vss：虚拟内存大小（含未实际分配的虚拟地址）
Rss：实际占用的物理内存（含共享库）
Pss：按比例分摊后的真实占用（最重要的指标）
Uss：进程独占的物理内存（Private Dirty + Private Clean）
Swap：换出的内存
SwapPSs：换出内存按比例分摊
FD：文件描述符数
Process：进程名
```

### 9.2.4 procrank 的工程使用

```bash
# 1. 快速定位内存大户
adb shell procrank | head -10
# 看哪个进程 PSS 最高

# 2. 对比多个进程
adb shell procrank | grep "com.example"
# 看自己 App 的多个进程

# 3. 监控 PSS 增长
while true; do
    adb shell procrank | grep "com.example.app"
    sleep 60
done > procrank_trend.log
```

### 9.2.5 procrank 异常的诊断

| PSS | 状态 | 诊断 |
|:---|:---|:---|
| < 100 MB | 正常 | — |
| 100-300 MB | 警告 | 可能内存泄漏 |
| 300-500 MB | 严重 | 紧急优化 |
| > 500 MB | 紧急 | 即将被 LMK 杀 |

---

## 二、smaps 详解

### 9.2.6 smaps 的定义

```
smaps：
- /proc/<pid>/smaps
- 显示进程的所有 VMA（虚拟内存区域）详情
- 每个 VMA 的内存使用情况
```

### 9.2.7 smaps 的获取

```bash
# 1. 获取 smaps
adb shell run-as <package> cat /proc/self/smaps > smaps.txt

# 2. 看自己 App 的 smaps
adb shell cat /proc/<pid>/smaps > smaps.txt

# 3. 看特定进程
adb shell cat /proc/12345/smaps > smaps.txt
```

### 9.2.8 smaps 输出详解

```
cat smaps.txt
# 输出示例（每个 VMA 一段）：
564d6fbc0000-564d6fbc1000 r--p 00000000 fc:01 123456 /system/bin/app_process
Size:                4 kB
KernelPageSize:       4 kB
MMUPageSize:          4 kB
Rss:                  8 kB
Pss:                  8 kB
Shared_Clean:         0 kB
Shared_Dirty:         0 kB
Private_Clean:        0 kB
Private_Dirty:        8 kB
Referenced:           8 kB
Anonymous:            0 kB
LazyFree:             0 kB
AnonHugePages:        0 kB
ShmemPmdMapped:       0 kB
FilePmdMapped:        0 kB
Shared_Hugetlb:       0 kB
Private_Hugetlb:      0 kB
Swap:                 0 kB
SwapPss:              0 kB
Locked:               0 kB
THPeligible:          0
VmFlags: rd mr mw me

# 下一个 VMA：
564d6fbd0000-564d6fbd1000 rw-p 00000000 00:00 0 
Size:                8 kB
Rss:                 16 kB
Pss:                 16 kB
...
```

### 9.2.9 smaps 关键字段

```
Size：VMA 大小（虚拟地址空间）
Rss：实际占用的物理内存
Pss：按比例分摊的物理内存（最准确）
Shared_Clean：共享的干净页
Shared_Dirty：共享的脏页（其他进程也修改）
Private_Clean：进程独占的干净页
Private_Dirty：进程独占的脏页（已修改）
Swap：换出到磁盘的内存
SwapPss：换出内存按比例分摊
```

### 9.2.10 smaps 的工程使用

```bash
# 1. 看总内存
adb shell run-as <package> cat /proc/self/smaps | grep "Pss:" | awk '{sum += $2} END {print sum " kB"}'

# 2. 看最大的 VMA
adb shell run-as <package> cat /proc/self/smaps | grep -B 1 "Pss:" | grep -v "Pss:"

# 3. 看特定库的内存
adb shell run-as <package> cat /proc/self/smaps | grep -A 10 "libart.so"

# 4. 看 native heap 内存
adb shell run-as <package> cat /proc/self/smaps | grep -A 10 "\\[heap\\]"
```

### 9.2.11 smaps 的诊断

```bash
# 1. 看 native heap（malloc 分配）
adb shell run-as <package> cat /proc/self/smaps | grep -A 12 "\\[heap\\]"
# 看 Pss 是否过大

# 2. 看 Java 堆（mmap 分配）
adb shell run-as <package> cat /proc/self/smaps | grep -A 12 "dalvik"
# 看 Pss 是否过大

# 3. 看特定 .so 的占用
adb shell run-as <package> cat /proc/self/smaps | grep -A 12 "libglide.so"
# 看 Glide 占用的内存
```

---

## 三、procrank 与 smaps 的协作

### 9.2.12 排查流程

```
procrank / smaps 排查流程：

1. procrank 找内存大户
   │
2. dumpsys meminfo 看具体 App 的内存分类
   │
3. smaps 看具体的 VMA 分布
   │
4. hprof 分析具体的对象
   │
5. 修复 + 监控
```

### 9.2.13 smaps vs dumpsys meminfo

| 维度 | smaps | dumpsys meminfo |
|:---|:---|:---|
| **粒度** | VMA（虚拟内存区域） | 内存分类 |
| **详细度** | 非常高 | 中等 |
| **性能开销** | 较大 | 小 |
| **使用场景** | 深度排查 | 常规监控 |
| **权限要求** | run-as 或 root | 无 |

### 9.2.14 smaps 的限制

```
smaps 的限制：

1. 只能看当前进程的 VMA
2. 不能看其他进程的 VMA（除非 root）
3. smaps 是快照，不反映实时变化
4. 大进程 smaps 输出很大（数十 MB）

→ smaps 适合深度排查，不适合实时监控
```

---

## 四、smaps 的实战案例

### 9.2.15 案例 1：找出 native 内存泄漏

```bash
# 1. dumpsys meminfo 看 native heap
adb shell dumpsys meminfo <package> | grep "Native Heap"
# 输出：Native Heap 100 MB（异常）

# 2. smaps 看 native heap
adb shell run-as <package> cat /proc/self/smaps | grep -A 12 "\\[heap\\]"
# 输出：Pss: 100 MB（确认是 [heap] 段）

# 3. 进一步定位
# [heap] 段大 → native malloc 分配的内存多
# 检查 DirectByteBuffer / JNI 分配
```

### 9.2.16 案例 2：找出最大 .so 库

```bash
# 1. smaps 找最大的 .so
adb shell run-as <package> cat /proc/self/smaps | grep -B 1 ".so$" | head -20

# 2. 看每个 .so 的 Pss
adb shell run-as <package> cat /proc/self/smaps | grep -A 12 ".so$" | grep "Pss:"

# 3. 输出示例：
# libart.so: Pss: 30 MB
# libwebviewchromium.so: Pss: 80 MB（异常！）
# libflutter.so: Pss: 50 MB
```

### 9.2.17 案例 3：找出 VMA 碎片化

```bash
# 1. smaps 看 VMA 数量
adb shell run-as <package> cat /proc/self/smaps | grep "^Size:" | wc -l
# 输出：1000 个 VMA（可能过多）

# 2. 看小 VMA（碎片化）
adb shell run-as <package> cat /proc/self/smaps | awk '/^[0-9a-f]+-[0-9a-f]+/ {va = $0} /Size:/ {size = $2} {if (size < 64) print va " " size " kB"}'
# 看小于 64 KB 的 VMA（碎片化）
```

---

## 五、procrank / smaps 的工程监控

### 9.2.18 自动化监控

```bash
#!/bin/bash
# monitor_memory.sh - 自动化内存监控脚本

PACKAGE=$1
LOG_FILE="memory_monitor.log"

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # 1. procrank
    PSS=$(adb shell procrank | grep "$PACKAGE" | awk '{print $4}')
    
    # 2. dumpsys meminfo
    HEAP_ALLOC=$(adb shell dumpsys meminfo "$PACKAGE" | grep "Dalvik Heap" | awk '{print $9}')
    
    # 3. smaps（每小时一次）
    if [ $(date +%M) == "00" ]; then
        adb shell run-as "$PACKAGE" cat /proc/self/smaps > "smaps_$(date +%Y%m%d%H%M).txt"
    fi
    
    # 4. 记录
    echo "$TIMESTAMP PSS=$PSS HeapAlloc=$HEAP_ALLOC" >> "$LOG_FILE"
    
    # 5. 告警
    if [ "$PSS" -gt 500 ]; then
        echo "[ALERT] $TIMESTAMP PSS=$PSS > 500MB"
    fi
    
    sleep 60
done
```

### 9.2.19 APM 监控 smaps 关键指标

```java
public class SmapsMonitor {
    @Scheduled(fixedRate = 3600000)  // 1 小时
    public void monitor() {
        // 1. 读取 smaps
        String smaps = readSmaps();
        
        // 2. 解析关键指标
        int totalPss = parseTotalPss(smaps);
        int nativeHeapPss = parseNativeHeapPss(smaps);
        int javaHeapPss = parseJavaHeapPss(smaps);
        int soCount = parseSoCount(smaps);
        
        // 3. 上报
        apmClient.report("smaps.total.pss", totalPss);
        apmClient.report("smaps.native.heap", nativeHeapPss);
        apmClient.report("smaps.java.heap", javaHeapPss);
        apmClient.report("smaps.so.count", soCount);
        
        // 4. 告警
        if (nativeHeapPss > 100 * 1024) {  // > 100 MB
            apmClient.alert("smaps.native.heap.high", "Native heap > 100MB");
        }
    }
}
```

---

## 六、procrank / smaps 的工程建议

### 9.2.20 何时使用哪个工具

```
工具选择：

1. 日常监控
   → dumpsys meminfo（轻量）

2. 找内存大户
   → procrank（看排名）

3. 深度排查
   → smaps（看 VMA）

4. 对象级分析
   → hprof + MAT（看对象）

5. GC 事件分析
   → Perfetto / Systrace
```

### 9.2.21 监控告警阈值

| 指标 | 阈值 | 监控方式 |
|:---|:---|:---|
| PSS | > 500 MB | procrank |
| Native Heap | > 100 MB | dumpsys meminfo / smaps |
| Heap Alloc / Heap Size | > 80% | dumpsys meminfo |
| .so 数量 | > 30 | smaps |
| VMA 数量 | > 1000 | smaps |

---

## 七、本节小结

1. **procrank**：看进程排名，快速定位内存大户
2. **smaps**：看 VMA 详情，深度排查 native / .so 占用
3. **dumpsys meminfo**：日常监控
4. **协作**：procrank → dumpsys meminfo → smaps → hprof
5. **自动化**：shell 脚本 + APM

→ **理解 procrank / smaps，就掌握了"深度内存排查"的工具链**。

---

## 跨节引用

**本节被以下章节引用**：
- [9.1 dumpsys meminfo](./01-dumpsys-meminfo详解.md) —— 内存分类
- [9.4 MAT](./04-MAT使用指南.md) —— 对象级分析
- [9.9 实战案例 1](./09-实战案例1-dumpsys诊断.md) —— 综合实战

**本节引用**：
- 02 篇 2.1 Heap 总览 —— Heap 类
