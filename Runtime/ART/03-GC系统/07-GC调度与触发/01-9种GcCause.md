# 7.1 GC 触发的 9 种原因

> **本节回答一个根本问题**：ART GC 怎么被触发？9 种 GcCause 各代表什么场景？
>
> **答案**：**GcCause 枚举** 标识 9 种触发原因，对应不同的 GC 策略。

---

## 一、GcCause 枚举

### 7.1.1 GcCause 的定义

```cpp
// art/runtime/gc/gc_cause.h
enum GcCause {
    kGcCauseNone,                  // 默认
    kGcCauseForAlloc,              // 分配失败触发
    kGcCauseForNativeAlloc,        // Native 分配触发
    kGcCauseBackground,            // 后台 GC
    kGcCauseExplicit,              // 显式 System.gc()
    kGcCauseForTrim,               // Trim Heap
    kGcCauseForInspect,            // 调试用
    kGcCauseJitArenaFull,          // JIT Arena 满
    kGcCauseMax,                   // 哨兵
};
```

### 7.1.2 9 种 GcCause 总览

| GcCause | 触发场景 | GC 类型 | STW |
|:---|:---|:---|:---|
| `kGcCauseForAlloc` | 分配对象失败 | 同步 GC | 长 |
| `kGcCauseForNativeAlloc` | Native 内存压力 | 后台 GC | 短 |
| `kGcCauseBackground` | 后台定时 | 后台 GC | 短 |
| `kGcCauseExplicit` | 显式 System.gc() | 同步 GC | 长 |
| `kGcCauseForTrim` | Trim Heap | 后台 GC | 短 |
| `kGcCauseForInspect` | 调试用 | 同步 GC | 长 |
| `kGcCauseJitArenaFull` | JIT Arena 满 | 后台 GC | 短 |

---

## 二、各 GcCause 详解

### 7.1.3 `kGcCauseForAlloc`（最常见）

**触发场景**：
```
业务线程分配对象：
1. TLAB 分配 → 失败
2. 申请新 Region / Run → 失败
3. 触发 GC_FOR_ALLOC
4. 同步 GC（业务线程阻塞等 GC 完成）
5. GC 后重试分配
6. 仍失败 → OOM
```

**特点**：
- 同步阻塞（业务线程等待）
- 必须快速完成（不能卡顿太久）
- 通常是 Minor GC（GenCC）或全堆 GC（CC）

**触发频率**：最高（每次 OOM 前都会触发）

### 7.1.4 `kGcCauseForNativeAlloc`（ART 14+ 新增）

**触发场景**：
```
Native 内存压力：
1. 业务代码分配大量 native 内存
2. 系统 native 内存使用率高
3. ART 主动触发 Java GC
4. 释放 Java 堆空间 → 为 native 让出空间
```

**特点**：
- 后台异步 GC
- 通常是 ConcurrentMajorGc
- 让 Java 堆使用软引用释放

### 7.1.5 `kGcCauseBackground`（最理想）

**触发场景**：
```
后台定时：
1. ART 启动 HeapTaskDaemon
2. HeapTaskDaemon 定期检查堆使用率
3. 当使用率 > 阈值（默认 75%）
4. 触发后台 GC
```

**特点**：
- 后台异步
- 不阻塞业务线程
- 用户感知不到

**频率**：默认 5 秒检查一次（ART 14+ 可调）

### 7.1.6 `kGcCauseExplicit`（System.gc()）

**触发场景**：
```java
// 业务代码
System.gc();  // 显式触发
// 或
Runtime.getRuntime().gc();
```

**特点**：
- 同步阻塞（业务线程等待）
- ART 14+ 可能是后台 GC（取决于 GC 策略）
- 通常不影响 Android App（建议不要用）

### 7.1.7 `kGcCauseForTrim`（内存压力应对）

**触发场景**：
```
1. 系统内存压力大（Lowmemorykiller 即将触发）
2. ART 主动 Trim 堆
3. 收缩堆，释放内存给系统
4. 调整 SoftReference 阈值
```

**特点**：
- 后台异步
- 释放内存给系统
- 配合 system_server 调度

### 7.1.8 `kGcCauseForInspect`（调试用）

**触发场景**：
```
调试模式：
1. dumpsys meminfo 触发
2. shell 命令触发
3. Heap Dump 触发
```

**特点**：
- 通常是同步阻塞
- 仅调试用
- 生产环境不出现

### 7.1.9 `kGcCauseJitArenaFull`（JIT 相关）

**触发场景**：
```
1. JIT 编译码占满 Arena 内存
2. ART 触发 GC 释放部分内存
3. 让 JIT 可以继续工作
```

**特点**：
- 后台异步
- ART 8+ 引入
- 与 JIT 编译相关

---

## 三、GcCause 的源码入口

### 7.1.10 GcCause 的字符串转换

```cpp
// art/runtime/gc/gc_cause.cc
const char* PrettyCause(GcCause cause) {
    switch (cause) {
        case kGcCauseForAlloc: return "kGcCauseForAlloc";
        case kGcCauseForNativeAlloc: return "kGcCauseForNativeAlloc";
        case kGcCauseBackground: return "kGcCauseBackground";
        case kGcCauseExplicit: return "kGcCauseExplicit";
        case kGcCauseForTrim: return "kGcCauseForTrim";
        case kGcCauseForInspect: return "kGcCauseForInspect";
        case kGcCauseJitArenaFull: return "kGcCauseJitArenaFull";
        default: return "UNKNOWN";
    }
}
```

### 7.1.11 GC 触发入口

```cpp
// art/runtime/gc/heap.cc
void Heap::CollectGarbage(GcCause cause, bool clear_soft_references) {
    // 1. 记录 GC 触发原因
    last_gc_cause_ = cause;
    
    // 2. 选择 GC 类型
    GcType gc_type = SelectGcType();
    
    // 3. 执行 GC
    switch (gc_type) {
        case kMinorGc:
            // Minor GC（GenCC）
            break;
        case kMajorGc:
            // Major GC
            break;
        case kConcurrentMajorGc:
            // 后台 GC
            break;
    }
}
```

---

## 四、GcCause 的工程监控

### 7.1.12 GcCause 监控命令

```bash
# 1. 看 GC 触发原因
adb logcat -d -s "art" | grep "Cause"
# 输出示例：
# art : Cause=kGcCauseForAlloc
# art : Cause=kGcCauseBackground
# art : Cause=kGcCauseForNativeAlloc

# 2. 统计各 GcCause 的频率
adb logcat -d -s "art" | grep "Cause=" | awk -F'Cause=' '{print $2}' | sort | uniq -c
# 输出示例：
#       3 kGcCauseBackground
#       2 kGcCauseForAlloc
#       1 kGcCauseExplicit
```

### 7.1.13 异常 GcCause 的诊断

| GcCause | 异常情况 | 根因 | 修复 |
|:---|:---|:---|:---|
| `kGcCauseForAlloc` | 频率 > 10/分钟 | 内存泄漏 / 堆太小 | 修复泄漏 + 调大堆 |
| `kGcCauseForNativeAlloc` | 频率 > 5/小时 | Native 内存泄漏 | 释放 native 内存 |
| `kGcCauseBackground` | STW > 100ms | 后台 GC 太重 | 调小堆 + 减少对象 |
| `kGcCauseExplicit` | 频率 > 1/分钟 | 业务代码滥用 System.gc() | 移除 System.gc() |
| `kGcCauseForTrim` | 频率 > 10/小时 | 系统内存压力 | 监听 onTrimMemory |
| `kGcCauseJitArenaFull` | 频率 > 5/分钟 | JIT 编译过多 | 调整 JIT 配置 |

### 7.1.14 GcCause 的 APM 监控

```java
public class GcCauseMonitor {
    @Scheduled(fixedRate = 30000)
    public void monitor() {
        // 1. 读取最近 1 分钟的 GC 日志
        List<GcEvent> events = readRecentGcEvents();
        
        // 2. 按 GcCause 统计
        Map<String, Integer> causeCount = events.stream()
            .collect(Collectors.groupingBy(
                GcEvent::getCause,
                Collectors.summingInt(GcEvent::getCount)));
        
        // 3. 上报到 APM
        causeCount.forEach((cause, count) -> {
            apmClient.report("gc.cause." + cause, count);
        });
        
        // 4. 告警
        int allocCount = causeCount.getOrDefault("kGcCauseForAlloc", 0);
        if (allocCount > 10) {
            apmClient.alert("gc.cause.alloc.high", "kGcCauseForAlloc > 10/min");
        }
    }
}
```

---

## 五、GcCause 与 GC 策略

### 7.1.15 GcCause → GC 策略的映射

```cpp
// art/runtime/gc/heap.cc
GcType Heap::SelectGcType() {
    switch (last_gc_cause_) {
        case kGcCauseForAlloc:
            // 同步 GC（业务线程等待）
            return kMajorGc;
        
        case kGcCauseForNativeAlloc:
        case kGcCauseBackground:
        case kGcCauseForTrim:
        case kGcCauseJitArenaFull:
            // 后台 GC
            return kConcurrentMajorGc;
        
        case kGcCauseExplicit:
            // ART 14+ 可能是后台 GC
            return kConcurrentMajorGc;
        
        default:
            return kNone;
    }
}
```

### 7.1.16 GcCause 的工程意义

```
9 种 GcCause 对应 9 类 GC 触发场景：

1. kGcCauseForAlloc：业务代码触发（最频繁）
2. kGcCauseForNativeAlloc：native 内存压力
3. kGcCauseBackground：后台定时（最理想）
4. kGcCauseExplicit：业务代码主动调用
5. kGcCauseForTrim：系统低内存
6. kGcCauseForInspect：调试用
7. kGcCauseJitArenaFull：JIT 编译触发
8. kGcCauseNone：默认值
9. kGcCauseMax：哨兵

→ 通过 GcCause 可以精准定位 GC 触发原因
→ 优化时针对具体 GcCause 调优
```

---

## 六、本节小结

1. **9 种 GcCause**：覆盖所有 GC 触发场景
2. **最频繁**：`kGcCauseForAlloc`（分配失败）
3. **最理想**：`kGcCauseBackground`（后台定时）
4. **关键区分**：同步 GC（阻塞业务）vs 后台 GC（不阻塞）
5. **APM 监控**：按 GcCause 统计频率，异常告警

→ **理解 GcCause，就理解了"GC 怎么被触发 + 怎么优化"**。

---

## 跨节引用

**本节被以下章节引用**：
- [7.4 GC_FOR_ALLOC 路径](./04-GC_FOR_ALLOC路径.md) —— kGcCauseForAlloc 详解
- [7.5 Native 触发 GC](./05-Native触发GC.md) —— kGcCauseForNativeAlloc 详解
- [7.6 Trim Heap](./06-Trim-Heap.md) —— kGcCauseForTrim 详解
- 09 篇诊断 —— GcCause 监控

**本节引用**：
- 02 篇 2.1 Heap 总览 —— Heap 类
- 04/05 篇 —— GC 算法
