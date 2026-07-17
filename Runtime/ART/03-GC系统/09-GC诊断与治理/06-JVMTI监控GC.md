# 9.6 JVMTI 监控 GC（Android 8+）

> **本节回答一个根本问题**：JVMTI 怎么监控 GC？Android 8+ 的 JVMTI GC 回调是什么？
>
> **答案**：**JVMTI 提供 GCStart / GCFinish 回调** —— 自建 APM 监控 GC 的标准方式。

---

## 一、JVMTI 概述

### 9.6.1 JVMTI 是什么

```
JVMTI（JVM Tool Interface）：

- JVM 提供的 native 调试 / 监控接口
- 可以订阅各种 JVM 事件
- 包括：方法进入 / 退出、GC、线程创建等
- Android 8+ 提供 GC 事件回调
```

### 9.6.2 Android 的 JVMTI

```
Android JVMTI 的版本：

- Android 8.0+ 引入完整 JVMTI 支持
- 之前只有部分支持（如 debugger）
- Android 8+ 可以订阅 GC 事件
```

---

## 二、JVMTI 的 GC 事件

### 9.6.3 GC 事件回调

```cpp
// JVMTI 的 GC 事件回调
typedef struct {
    // GC 开始事件
    void JNICALL (*GarbageCollectionStart)(jvmtiEnv* env);
    
    // GC 结束事件
    void JNICALL (*GarbageCollectionFinish)(jvmtiEnv* env);
    
    // 对象引用事件（Android 11+）
    void JNICALL (*ObjectFree)(jvmtiEnv* env, jlong tag);
    void JNICALL (*ObjectFreeImpl)(jvmtiEnv* env, jlong tag);
} jvmtiEventCallbacks;
```

### 9.6.4 启用 GC 事件回调

```cpp
// 1. 获取 JVMTI 环境
jvmtiEnv* jvmti = nullptr;
jvmti->GetEnv(reinterpret_cast<void**>(&jvmti), JVMTI_VERSION_1_2);

// 2. 设置 GC 事件回调
jvmtiEventCallbacks callbacks = {0};
callbacks.GarbageCollectionStart = OnGCStart;
callbacks.GarbageCollectionFinish = OnGCFinish;
jvmti->SetEventCallbacks(&callbacks, sizeof(callbacks));

// 3. 启用 GC 事件
jvmti->SetEventNotificationMode(JVMTI_EVENT_GARBAGE_COLLECTION_START, 
                                   JVMTI_ENABLED);
jvmti->SetEventNotificationMode(JVMTI_EVENT_GARBAGE_COLLECTION_FINISH, 
                                   JVMTI_ENABLED);
```

### 9.6.5 GC 回调的实现

```cpp
// GC 开始回调
void JNICALL OnGCStart(jvmtiEnv* env) {
    // 1. 记录 GC 开始时间
    g_gc_start_time = currentTimeMillis();
    
    // 2. 记录 GC 开始
    apmClient.report("gc.start", 1);
}

// GC 结束回调
void JNICALL OnGCFinish(jvmtiEnv* env) {
    // 1. 计算 STW 时间（粗略）
    long pause_time = currentTimeMillis() - g_gc_start_time;
    
    // 2. 上报到 APM
    apmClient.report("gc.finish", 1);
    apmClient.report("gc.pause", pause_time);
    
    // 3. 告警
    if (pause_time > 100) {
        apmClient.alert("gc.pause.high", "GC pause > 100ms: " + pause_time);
    }
}
```

---

## 三、JVMTI 的工程应用

### 9.6.6 自建 APM 监控

```java
public class JvmtiGcMonitor {
    static {
        // 加载 JVMTI 库
        System.loadLibrary("jvmti-gc-monitor");
    }
    
    // 启用 GC 事件
    public static native void enableGcEvents();
}
```

### 9.6.7 JVMTI 的优势

```
JVMTI 的优势：

1. 标准化
   - JVMTI 是 JVM 标准接口
   - 不依赖 ART 内部 API
   - 跨平台

2. 实时性
   - GC 开始 / 结束立即回调
   - 不需要轮询

3. 信息完整
   - 可以获取 GC 类型（虽然有限）
   - 可以获取 STW 时间
```

### 9.6.8 JVMTI 的限制

```
JVMTI 的限制：

1. Android 版本要求
   - Android 8.0+
   - 之前版本不支持 GC 事件

2. 信息有限
   - 不能获取 GC Cause
   - 不能获取 STW 时间精确值
   - 不能获取 GC 扫描范围

3. 性能影响
   - 每次 GC 都有回调
   - 大量 GC 会影响性能

4. ART 兼容性
   - ART 不是标准 JVM
   - 部分 JVMTI 事件不支持
```

---

## 四、JVMTI 实战

### 9.6.9 实战 1：GC 频率监控

```cpp
// 全局变量
static int gc_count = 0;
static long total_pause_time = 0;

void JNICALL OnGCStart(jvmtiEnv* env) {
    gc_count++;
    g_gc_start_time = currentTimeMillis();
}

void JNICALL OnGCFinish(jvmtiEnv* env) {
    long pause_time = currentTimeMillis() - g_gc_start_time;
    total_pause_time += pause_time;
    
    // 上报到 APM（每秒一次）
    static long last_report = 0;
    long now = currentTimeMillis();
    if (now - last_report > 1000) {
        apmClient.report("gc.count.per.sec", gc_count);
        apmClient.report("gc.pause.avg", total_pause_time / gc_count);
        gc_count = 0;
        total_pause_time = 0;
        last_report = now;
    }
}
```

### 9.6.10 实战 2：GC 卡顿告警

```cpp
// 检测长 STW
void JNICALL OnGCFinish(jvmtiEnv* env) {
    long pause_time = currentTimeMillis() - g_gc_start_time;
    
    if (pause_time > 100) {
        // 长 STW 告警
        apmClient.alert("gc.pause.long", "GC pause > 100ms: " + pause_time);
        
        // 抓取 trace 便于分析
        // （异步触发）
    }
}
```

### 9.6.11 实战 3：GC 与卡顿关联

```cpp
// 关联 GC 与 UI 卡顿
void JNICALL OnGCFinish(jvmtiEnv* env) {
    long pause_time = currentTimeMillis() - g_gc_start_time;
    
    // 关联 Choreographer（UI 帧）
    // 如果 GC 期间有 UI 帧被卡 → 标记为 GC 导致卡顿
    
    if (pause_time > 16) {  // 超过一帧
        // 关联 Choreographer 的 doFrame 事件
        // 找出被卡的帧
    }
}
```

---

## 五、JVMTI 与其他监控方式对比

### 9.6.12 JVMTI vs Perfetto

| 维度 | JVMTI | Perfetto |
|:---|:---|:---|
| **接入方式** | C/C++ native | 用户态 |
| **数据来源** | JVMTI 回调 | Trace 事件 |
| **实时性** | 实时 | 事后 |
| **CPU 开销** | 低 | 中 |
| **使用场景** | 生产 APM | 性能分析 |

### 9.6.13 JVMTI vs dumpsys meminfo

| 维度 | JVMTI | dumpsys meminfo |
|:---|:---|:---|
| **数据来源** | JVMTI 回调 | dumpsys |
| **实时性** | 实时 | 快照 |
| **信息** | GC 频率 / STW 时间 | 内存分类 |
| **生产环境** | 适合 | 不适合 |

---

## 六、JVMTI 的集成方案

### 9.6.14 JVMTI native 库的创建

```cpp
// jvmti-gc-monitor.cpp
#include <jvmti.h>

static jlong g_gc_start_time = 0;

void JNICALL OnGCStart(jvmtiEnv* env) {
    g_gc_start_time = currentTimeMillis();
}

void JNICALL OnGCFinish(jvmtiEnv* env) {
    long pause_time = currentTimeMillis() - g_gc_start_time;
    // 上报到 APM
}

// JNI 入口
JNIEXPORT void JNICALL
Java_com_example_JvmtiGcMonitor_enableGcEvents(JNIEnv* env, jclass clazz) {
    jvmtiEnv* jvmti = nullptr;
    env->GetEnv(reinterpret_cast<void**>(&jvmti), JVMTI_VERSION_1_2);
    
    jvmtiEventCallbacks callbacks = {0};
    callbacks.GarbageCollectionStart = OnGCStart;
    callbacks.GarbageCollectionFinish = OnGCFinish;
    jvmti->SetEventCallbacks(&callbacks, sizeof(callbacks));
    
    jvmti->SetEventNotificationMode(JVMTI_EVENT_GARBAGE_COLLECTION_START, JVMTI_ENABLED);
    jvmti->SetEventNotificationMode(JVMTI_EVENT_GARBAGE_COLLECTION_FINISH, JVMTI_ENABLED);
}
```

### 9.6.15 编译

```cmake
# CMakeLists.txt
add_library(jvmti-gc-monitor SHARED jvmti-gc-monitor.cpp)
target_link_libraries(jvmti-gc-monitor log android)
```

---

## 七、JVMTI 的工程建议

### 9.6.16 何时使用 JVMTI

```
JVMTI 的适用场景：

1. 生产环境 GC 监控
   - JVMTI 是标准方式
   - 不依赖 ART 内部 API

2. 自建 APM
   - JVMTI 提供 GC 事件
   - 适合 APM SDK 集成

3. 不适用场景
   - 需要详细的 GC 信息（用 Perfetto）
   - 需要对象级分析（用 MAT）
```

### 9.6.17 JVMTI 的最佳实践

```
JVMTI 的最佳实践：

1. 异步上报
   - JVMTI 回调中不要做耗时操作
   - 异步队列 + 后台线程上报

2. 采样上报
   - 不是每次 GC 都上报
   - 采样（如 1/10）

3. 过滤重要 GC
   - 只上报长 STW（> 50ms）
   - 过滤 Minor GC（除非异常）
```

---

## 八、本节小结

1. **JVMTI 是 JVM 标准接口**：Android 8+ 支持 GC 事件
2. **GC 事件回调**：GarbageCollectionStart / GarbageCollectionFinish
3. **自建 APM**：用 JVMTI 监控 GC 频率和 STW 时间
4. **限制**：信息有限，不能获取 GC Cause
5. **适用场景**：生产环境 APM 集成

→ **理解 JVMTI，就掌握了"自建 GC 监控"的标准化方式**。

---

## 跨节引用

**本节被以下章节引用**：
- [9.7 监控指标体系](./07-监控指标体系.md) —— APM 集成
- [9.10 实战案例 2](./10-实战案例2-APM搭建.md) —— 自建 APM

**本节引用**：
- 07 篇 GC 调度 —— GC 触发时机
- 04 篇 CC GC —— STW 时间
