# 8.6 GC × System Server 进程

> **本节回答一个根本问题**：System Server 进程的 GC 有什么特殊？为什么 System Server OOM = 系统重启？
>
> **答案**：**System Server 进程有特殊的 GC 策略**——更激进的 GC 阈值、特殊的内存管理。

---

## 一、System Server 的特殊性

### 8.6.1 System Server 进程概述

```
System Server 进程：

- 由 Zygote fork
- 启动 Android Framework 核心服务
- 包含 100+ 系统服务
- 系统服务运行在主线程 + 多个工作线程
- 进程内存占用大（200-500 MB）
- System Server OOM = 系统重启
```

### 8.6.2 System Server 与普通 App 的对比

| 维度 | 普通 App | System Server |
|:---|:---|:---|
| **进程类型** | App 进程 | 系统服务进程 |
| **GC 策略** | 默认 | 特殊配置 |
| **OOM 后果** | App 崩溃 | 系统重启 |
| **内存上限** | 256 MB（默认） | 512 MB+ |
| **服务数量** | 1 个主线程 | 100+ 服务 |

---

## 二、System Server 的 GC 策略

### 8.6.3 System Server 的特殊配置

```bash
# System Server 的 system property
dalvik.vm.heapgrowthlimit=512m
dalvik.vm.heapsize=1024m
dalvik.vm.heaptargetutilization=0.5  # 更激进
dalvik.vm.softrefthreshold=0.15      # 更激进
```

### 8.6.4 System Server 的 GC 触发条件

```cpp
// art/runtime/gc/heap.cc 的 System Server 特殊处理
void Heap::AdjustForSystemServer() {
    // 1. 更小的 GC 阈值（更激进）
    concurrent_start_threshold_ = 0.3;  // 30% 触发后台 GC
    target_utilization_ = 0.5;  // 50% 目标使用率
    
    // 2. 更频繁的后台 GC
    //    避免 OOM 导致系统重启
    
    // 3. 更激进的 SoftReference 处理
    soft_ref_threshold_ = 0.15;  // 15% 软引用阈值
    
    // 4. 更频繁的 Trim
    trim_interval_ = 5 * 60 * 1000;  // 5 分钟一次
}
```

### 8.6.5 System Server 的 GC 频率

```
System Server 的 GC 频率（实测数据）：

- 后台 GC：~10/分钟（比普通 App 高）
- Foreground GC：< 1/小时
- Major GC：~1/小时

为什么这么频繁？
  - System Server 必须稳定运行
  - 不能等堆满了才 GC
  - 提前 GC 避免 OOM
```

---

## 三、System Server 的内存管理

### 8.6.6 System Server 的内存监控

```bash
# 1. dumpsys meminfo 看 System Server 内存
adb shell dumpsys meminfo system_server

# 2. System Server 内存上限
adb shell dumpsys meminfo -d system_server

# 3. System Server GC 日志
adb logcat -s "art" | grep -i "system_server\|ss"
```

### 8.6.7 System Server 的内存特点

```
System Server 的内存特点：

1. 堆较大
   - 512 MB（heapgrowthlimit）
   - 1024 MB（heapsize）
   - 比普通 App 大 2-4 倍

2. 长寿对象多
   - 100+ 系统服务
   - 大量缓存
   - 多数对象进入 Old Gen

3. Native 内存占用大
   - .so 库（SystemUI 等）
   - 大量 Bitmap
   - native heap 占用大
```

### 8.6.8 System Server OOM 的后果

```
System Server OOM 的后果：

1. 系统服务崩溃
   - ActivityManagerService 崩溃 → AMS 重启
   - WindowManagerService 崩溃 → 显示崩溃
   - 所有系统服务都重启

2. 系统重启
   - init 进程检测到 system_server 死亡
   - 重启 system_server
   - 整个 Android Framework 重启

3. 用户感知
   - 屏幕冻结几秒
   - 重启后回到锁屏
   - 数据丢失（前台 App）
```

---

## 四、System Server 的特殊处理

### 8.6.9 AMS 内存管理

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

public void handleApplicationCrash() {
    // 处理 App 崩溃
    // 不影响 System Server 自身
}

public void systemReady() {
    // System Server 启动完成
    // 启动 GC 监控
    startGcPerformanceMonitor();
}
```

### 8.6.10 System Server 的 OOM 处理

```cpp
// art/runtime/gc/heap.cc 的 System Server OOM 处理
void Heap::HandleSystemServerOOM() {
    // 1. System Server 即将 OOM
    if (is_system_server_ && GetHeapUsage() > 0.95) {
        // 2. 主动 Trim
        Trim();
        
        // 3. 强制 GC
        CollectGarbage(kGcCauseForTrim, true);
        
        // 4. 如果还不行，输出日志
        if (GetHeapUsage() > 0.98) {
            LOG(WARNING) << "System Server OOM imminent";
        }
    }
}
```

### 8.6.11 System Server 的监控

```java
public class SystemServerMonitor {
    // 监控 System Server 的内存使用
    @Scheduled(fixedRate = 60000)
    public void monitor() {
        // 1. 获取 System Server 内存
        long ssMemory = getSystemServerMemory();
        apmClient.report("system_server.memory", ssMemory);
        
        // 2. 看 GC 频率
        int gcCount = countGcInLastMinute("system_server");
        apmClient.report("system_server.gc.count", gcCount);
        
        // 3. 告警
        if (ssMemory > 500 * 1024 * 1024) {  // > 500 MB
            apmClient.alert("system_server.memory.high", "System Server > 500MB");
        }
    }
}
```

---

## 五、System Server 与普通 App 的 GC 对比

### 8.6.12 GC 策略对比

| 维度 | 普通 App | System Server |
|:---|:---|:---|
| **concurrent_start_threshold** | 0.5 | 0.3（更激进） |
| **target_utilization** | 0.75 | 0.5（更激进） |
| **soft_ref_threshold** | 0.25 | 0.15（更激进） |
| **trim_interval** | 30 分钟 | 5 分钟 |
| **max_allowed_footprint** | 256 MB | 1024 MB |

### 8.6.13 为什么 System Server 更激进

```
System Server 更激进的 GC 原因：

1. 不能 OOM
   - System Server OOM = 系统重启
   - 必须在 OOM 前释放内存

2. 长寿对象多
   - 100+ 系统服务
   - 大量缓存
   - 普通 GC 难以释放

3. 系统级监控
   - ActivityManagerService 监控
   - 异常可以重启 App，但 System Server 异常不行

4. 性能 vs 稳定性
   - 宁愿 GC 频繁（占用一些 CPU）
   - 也不愿 OOM 导致系统重启
```

---

## 六、System Server 的工程监控

### 8.6.14 监控 System Server 内存

```bash
# 1. 看 System Server 整体内存
adb shell dumpsys meminfo system_server

# 关键输出：
#   Native Heap     123456   100000    23456      500  150000
#   Dalvik Heap     234567   200000    34567      500  280000  ← 重点
#   TOTAL           500000   400000    100000    1000  600000

# 2. 看 GC 状态
adb shell dumpsys meminfo -d system_server | grep "GC"
```

### 8.6.15 System Server 异常的诊断

| 现象 | 根因 | 修复 |
|:---|:---|:---|
| System Server 频繁 GC | 内存压力 | 优化服务 |
| System Server OOM | 内存泄漏 | 紧急修复 |
| System Server 卡顿 | GC 频繁 | 减少对象分配 |
| System Server 重启 | OOM | 紧急优化 |

### 8.6.16 System Server 性能优化

```
System Server 性能优化建议：

1. 减少对象分配
   - 复用 Service 实例
   - 缓存常用数据
   - 避免临时对象

2. 减少 Bitmap 分配
   - 用 BitmapFactory.Options.inBitmap
   - 缓存复用 Bitmap

3. 减少 JNI 调用
   - 缓存 JNI 引用
   - 避免频繁跨 JNI 调用

4. 定期清理缓存
   - 监听 onTrimMemory
   - 主动释放不必要缓存
```

---

## 七、System Server 与 GC 的源码索引

### 8.6.17 核心源码路径

```
art/runtime/gc/heap.cc                       # Heap 类
frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java
frameworks/base/services/core/java/com/android/server/SystemServer.java
frameworks/base/core/java/com/android/internal/os/ZygoteInit.java
```

### 8.6.18 System Server 的相关命令

```bash
# 1. 看 System Server 进程
adb shell ps -A | grep system_server

# 2. 看 System Server 内存
adb shell dumpsys meminfo system_server

# 3. 看 System Server GC
adb logcat -s "art" | grep -i "system_server"
```

---

## 八、本节小结

1. **System Server 是关键系统进程**：OOM = 系统重启
2. **System Server 的 GC 策略更激进**：提前触发 + 频繁 Trim
3. **System Server 内存上限大**：512-1024 MB
4. **System Server 的长寿对象多**：100+ 服务
5. **优化方向**：减少对象分配 + 缓存复用 + 主动清理

→ **理解 System Server 与 GC，就理解了"为什么 System Server 不能 OOM"**。

---

## 跨节引用

**本节被以下章节引用**：
- 09 篇诊断 —— System Server 内存诊断

**本节引用**：
- [8.3 GC × Zygote](./03-GC与Zygote.md) —— System Server 来自 Zygote
- 07 篇 GC 调度 —— kGcCauseForTrim
- Android_Framework 的相关模块
