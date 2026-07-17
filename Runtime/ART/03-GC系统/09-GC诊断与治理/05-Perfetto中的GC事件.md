# 9.5 Perfetto 中的 GC 事件

> **本节回答一个根本问题**：Perfetto 中怎么追踪 GC 事件？怎么关联 GC 与卡顿？
>
> **答案**：**Perfetto 的 dalvik / art track 包含 GC 事件** —— 用 track_event + GC 事件的关联分析。

---

## 一、Perfetto 概述

### 9.5.1 Perfetto 是什么

```
Perfetto：

- Google 开发的系统级 trace 工具
- Android 10+ 默认的 trace 工具
- 替代 Systrace
- 支持跨进程 / 跨线程的 trace
- 强大的 UI 分析界面
```

### 9.5.2 Perfetto vs Systrace

| 维度 | Perfetto | Systrace |
|:---|:---|:---|
| **开发方** | Google | Google（已废弃） |
| **当前状态** | 活跃维护 | 已废弃 |
| **Android 版本** | Android 10+ 默认 | Android 9 及之前 |
| **性能** | 高（可处理长时间 trace） | 一般 |
| **UI** | 现代化 | 简单 |
| **扩展性** | 高（自定义 track） | 低 |

---

## 二、Perfetto 的 GC track

### 9.5.3 ART / dalvik track

```
Perfetto 中的 GC 事件：

track: dalvik
  ├─ track: GC（Background GC）
  │  ├─ Marking
  │  ├─ Reclaim
  │  └─ ...
  ├─ track: GC（Concurrent GC）
  │  ├─ Initialize
  │  ├─ Concurrent Copying
  │  └─ Reclaim
  └─ track: GC（Foreground GC）
     ├─ Marking
     └─ Sweeping

track: art
  ├─ track: ConcurrentCopying
  │  └─ MarkObject / CopyObject
  ├─ track: ReadBarrier
  │  └─ SlowPath
  └─ track: WriteBarrier
     └─ MarkCard
```

### 9.5.4 Perfetto 中的 GC 事件名

```
常见的 GC 事件名：

1. ART::ConcurrentCopying::MarkingRoot
2. ART::ConcurrentCopying::MarkObject
3. ART::ConcurrentCopying::CopyingPhase
4. ART::ConcurrentCopying::ReclaimPhase
5. ART::ConcurrentCopying::InitializePhase
6. ART::WriteBarrier::MarkCard
7. ART::ReadBarrier::Barrier
8. HeapTaskDaemon::Run
9. ReferenceQueueDaemon::Run
10. FinalizerDaemon::Run
```

---

## 三、Perfetto 的使用

### 9.5.5 启用 ART track

```bash
# 启用 ART 调试
adb shell setprop dalvik.vm.image-dex2oat-flags --debug

# Perfetto 抓取（包含 dalvik + art）
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 30s sched freq idle am wm gfx view binder_driver hal dalvik

# 拉取 trace 文件
adb pull /data/local/tmp/trace.proto

# 用 Perfetto UI 打开
# https://ui.perfetto.dev/
```

### 9.5.6 Perfetto UI 分析 GC

```
Perfetto UI 的分析步骤：

1. 打开 trace 文件
   https://ui.perfetto.dev/

2. 找 GC 事件
   - 在 track 区域找 dalvik 或 art
   - 找 "GC" 或 "ConcurrentCopying" 字样

3. 展开 GC 详情
   - 鼠标悬停看详情
   - 看耗时、开始时间、结束时间

4. 关联业务线程
   - 看 GC 期间业务线程在做什么
   - 是否阻塞

5. 找 GC 卡顿
   - 看 GC 与 UI 卡顿的对应
   - 找"GC 导致卡顿"的证据
```

### 9.5.7 Perfetto 中的 GC trace 标记

```cpp
// ART 中 GC trace 的标记宏
TRACE_PHASE(InitialMark);
TRACE_PHASE(ConcurrentMark);
TRACE_PHASE(Remark);
TRACE_PHASE(ConcurrentSweep);

// CC GC 的 trace 标记
TRACE_PHASE(Initialize);
TRACE_PHASE(ConcurrentCopying);
TRACE_PHASE(Reclaim);

// 这些 trace 会出现在 Perfetto 中
```

---

## 四、Perfetto 分析 GC 卡顿

### 9.5.8 卡顿与 GC 的关联

```
卡顿分析的完整流程：

1. 抓取 trace（含 dalvik + art + main thread）
2. 在 UI 上找卡顿（main thread 红色）
3. 找卡顿时段的 GC 事件
4. 看 GC 详情（哪个阶段耗时多久）
5. 关联 GC 与卡顿（GC 期间 main thread 阻塞）
```

### 9.5.9 卡顿分析的具体操作

```
Perfetto UI 的具体操作：

1. 找卡顿
   - 找 main thread 的红色区域（> 16ms）
   
2. 找对应的 GC
   - 找同一时间段的 GC 事件
   - 看 GC 类型（Minor / Major）

3. 看 GC 详情
   - 哪个阶段耗时（Marking / Sweeping / Copying）
   - 哪个对象导致耗时

4. 看 GC 期间业务线程
   - 业务线程是否阻塞
   - 阻塞时长
```

### 9.5.10 卡顿分析的常见发现

```
卡顿分析的常见发现：

1. CMS 时代：Remark STW 50ms+
   - 找 dirty 对象多的代码
   - 减少 Concurrent Mark 期间的对象创建

2. CC GC 时代：Initialize STW 5ms+
   - 栈扫描慢
   - 减少线程数

3. GenCC 时代：Minor GC 频繁
   - Young Gen 太小
   - 调大 Young Gen

4. Hook 框架：崩溃或卡顿
   - 绕过读屏障
   - 升级 Hook 框架
```

---

## 五、Perfetto 实战

### 9.5.11 实战 1：滑动列表卡顿分析

```
场景：滑动 RecyclerView 时卡顿

分析步骤：
1. 抓取 trace（含 main thread + dalvik）
2. 在 main thread 找滑动期间的卡顿
3. 看同一时间是否有 GC 事件
4. 如果有 → GC 导致卡顿
5. 看 GC 详情：哪个阶段耗时
6. 优化：减少对象分配

输出示例：
- 卡顿时段：12:34:56.789 - 12:34:56.839 (50ms)
- GC 时段：12:34:56.789 - 12:34:56.839 (50ms)
- 阶段：CMS Remark
- 根因：dirty 对象多
```

### 9.5.12 实战 2：App 启动慢分析

```
场景：App 启动慢

分析步骤：
1. 抓取启动期间的 trace
2. 看 main thread 的执行轨迹
3. 找"等待 GC"的时间
4. 优化：避免启动期间大量对象分配

输出示例：
- 启动时长：2.5s
- 启动 GC：3 次（kGcCauseForAlloc）
- 优化：减少启动期间分配
- 优化后启动时长：1.5s
```

### 9.5.13 实战 3：频繁 GC 分析

```
场景：App 频繁 GC

分析步骤：
1. 抓取较长时间的 trace（5 分钟）
2. 统计 GC 事件数量
3. 看 GC 类型（Minor vs Major）
4. 看 GC 触发原因（kGcCauseBackground vs kGcCauseForAlloc）

输出示例：
- 5 分钟内 GC 次数：100 次
- Minor GC：90 次（每次 1ms）
- Major GC：10 次（每次 20ms）
- 优化：调大堆
```

---

## 六、Perfetto 的进阶用法

### 9.5.14 自定义 track

```cpp
// 自定义 Perfetto track
#include <perfetto.h>

PERFETTO_DEFINE_CATEGORIES(
    perfetto::Category("myapp.gc")
);

void MyApp::OnGCEvent(const std::string& phase) {
    TRACE_EVENT("myapp.gc", phase.c_str());
    // ...
}
```

### 9.5.15 跨进程 trace

```bash
# 抓取系统级 trace（跨进程）
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 30s sched freq idle am wm gfx view binder_driver hal dalvik
# 包含所有系统进程和 App 进程的 trace
```

### 9.5.16 Perfetto 配置

```python
# Perfetto 配置示例
perfetto_config = """
trace_config {
  buffers {
    primary { size_kb: 32768 }
  }
  data_sources {
    config {
      name: "android.sched"
    }
    config {
      name: "android.gpu.memory"
    }
  }
  duration_ms: 30000
}
"""
```

---

## 七、Perfetto 与其他工具的对比

### 9.5.17 Perfetto vs LeakCanary

| 维度 | Perfetto | LeakCanary |
|:---|:---|:---|
| **检测目标** | GC 事件 + 卡顿 | 内存泄漏 |
| **使用方式** | 手动 trace | 自动监控 |
| **深度** | 整体性能 | 泄漏点 |
| **生产环境** | 适合（不影响性能） | 适合（debug） |

### 9.5.18 Perfetto vs MAT

| 维度 | Perfetto | MAT |
|:---|:---|:---|
| **分析目标** | GC + 卡顿 | 内存对象 |
| **数据来源** | Trace | hprof 文件 |
| **使用方式** | 实时或事后 | 事后深度分析 |
| **性能影响** | 小 | 大 |

---

## 八、本节小结

1. **Perfetto 是 Android 10+ 默认的 trace 工具**
2. **GC 事件在 dalvik / art track 中**
3. **分析流程**：抓 trace → UI 找 GC → 关联卡顿 → 优化
4. **实战场景**：滑动卡顿 / 启动慢 / 频繁 GC
5. **与其他工具协作**：Perfetto（GC + 卡顿） + LeakCanary（泄漏） + MAT（深度）

→ **理解 Perfetto，就掌握了"GC 卡顿分析"的工具**。

---

## 跨节引用

**本节被以下章节引用**：
- [9.7 监控指标体系](./07-监控指标体系.md) —— 性能监控
- [9.10 实战案例 2](./10-实战案例2-APM搭建.md) —— APM 集成

**本节引用**：
- 03/04/05 篇 —— GC 算法的 trace 标记
- 07 篇调度 —— GC 触发时机
