# 附录 D：工程基线（GC 调度与触发 · v2 升级版）

> **本附录定位**：**D 附录 · 工程基线**（4 附录之 4/4）——GC 调度与触发的工程参数 + 监控指标 + 业务优化建议 + APM 监控代码（含 ART 17 强化）
>
> **基线版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS，2024-11-17 发布，EOL 2026-12）
>
> **v2 升级日期**：2026-07-18（v1 旧文按 本规范 + 新基线 + ART 17 硬变化升级）

---

## 一、关键参数（AOSP 17 vs v1 对比）

### 1.1 Heap 核心参数

| 参数 | v1 默认（AOSP 14） | v2 默认（AOSP 17） | 选用准则 | 踩坑提醒 |
|:---|:---|:---|:---|:---|
| `dalvik.vm.heapgrowthlimit` | 256 MB | 256 MB | 通用 | 太小→频繁 GC |
| `dalvik.vm.heapsize` | 512 MB | 512 MB | largeHeap | — |
| `dalvik.vm.heaptargetutilization` | 0.75 | 0.75 | 通用 | — |
| `concurrent_start_threshold` | 0.5 | 0.5 | 通用 | — |
| `dalvik.vm.gc.threads` | 4 | 4 | 通用 | — |
| `dalvik.vm.gc.priority` | -19 | -19 | 通用 | — |
| **`dalvik.vm.heap-young-size`** | 4-8MB | **8-16MB（更大）** | 视 App 内存模式 | 太小→频繁 Minor |
| **`kSoftThresholdPercent`** | 不存在 | **30%** | AOSP 17 默认 | **老 App 卡顿** |
| **`kHardThresholdPercent`** | 10% | 10% | 不变 | — |
| **`kMinSleepMs`** | 固定 1s | **500ms** | AOSP 17 CPU 闲时 | — |
| **`kMaxSleepMs`** | 固定 1s | **2000ms** | AOSP 17 CPU 忙时 | — |

### 1.2 ★ ART 17 新增配置参数

| 参数 | 默认值 | 选用准则 | 踩坑提醒 |
|:---|:---|:---|:---|
| **`dalvik.vm.soft-threshold-percent`** | 30 | 内存敏感 App 调低（20）/ 性能敏感调高（40） | **老 App 不适应** |
| **`dalvik.vm.heap-task-daemon.min-sleep`** | 500 | AOSP 17 默认 | — |
| **`dalvik.vm.heap-task-daemon.max-sleep`** | 2000 | AOSP 17 默认 | — |
| **`dalvik.vm.heap-task-daemon.max-queue`** | 5 | 大量后台 GC 任务可调大 | > 20 异常 |
| **`dalvik.vm.native-alloc-throttle`** | 启用 | AOSP 17 限流 | 避免 GC 风暴 |
| **`dalvik.vm.minor-priority`** | 启用 | AOSP 17 Minor 优先 | — |

### 1.3 Linux 6.18 内核参数（跨系列基线）

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `kernel.slab_common.sheaves` | 启用 | Linux 6.18 新增（Native 堆 -15-20%） |
| `kernel.sched.cpu_util` | 启用 | HeapTaskDaemon 动态 sleep 依赖 |
| `kernel.io_uring` | 启用 | heap dump 写盘延迟 -30% |

---

## 二、监控指标（AOSP 17 完整版）

### 2.1 ★ GcCause 频率监控（v2 升级）

| GcCause | 正常 | 警告 | 严重 | AOSP 17 变化 |
|:---|:---|:---|:---|:---|
| `kGcCauseForAlloc` | < 1/min | 1-5/min | > 5/min | **★ 优先 Minor（< 1ms）** |
| `kGcCauseForNativeAlloc` | < 5/h | 5-20/h | > 20/h | 不变 |
| `kGcCauseBackground` | 1-5/min | 5-15/min | > 15/min | 不变 |
| **`kSoftThreshold`** ★ | **5-15/min** | **15-30/min** | **> 30/min** | **★ 新增** |
| **`kBackgroundGenCC`** ★ | **3-5/min** | **5-10/min** | **> 10/min** | **★ 新增** |
| `kGcCauseForTrim` | < 5/h | 5-20/h | > 20/h | 不变 |
| `kGcCauseExplicit` | 0/min | 1-5/min | > 5/min | 默认后台化 |
| `kGcCauseJitArenaFull` | < 5/h | 5-20/h | > 20/h | 不变 |
| **`kGcCauseForNativeAllocThrottled`** ★ | **< 5/h** | **5-20/h** | **> 20/h** | **★ 新增** |

### 2.2 ★ GC 比例监控（v2 升级）

| 指标 | 正常 | 警告 | 严重 | AOSP 17 变化 |
|:---|:---|:---|:---|:---|
| Foreground GC 比例 | < 10% | 10-30% | > 30% | **★ Minor 优先** |
| Minor GC 比例（kGcCauseForAlloc） | **> 80%** | **50-80%** | **< 50%** | **★ 新增** |
| Major GC 比例（kGcCauseForAlloc） | **< 20%** | **20-50%** | **> 50%** | **★ 新增** |
| 软阈值占比（占总 GC） | 30-60% | < 30% 或 > 80% | — | **★ 新增** |
| 后台 GC 占比 | > 80% | 50-80% | < 50% | 不变 |

### 2.3 HeapTaskDaemon 监控

| 指标 | 正常 | 警告 | 严重 | AOSP 17 变化 |
|:---|:---|:---|:---|:---|
| HeapTaskDaemon 队列长度 | < 5 | 5-20 | > 20 | **★ 动态 sleep 缓解** |
| HeapTaskDaemon 动态 sleep 间隔 | 0.5-2s | 固定 1s | — | **★ 新增** |
| HeapTask 类型分布 | Normal:Soft = 1:3 | — | — | **★ 新增** |
| 软阈值触发频率 | 5-15/min | 15-30/min | > 30/min | **★ 新增** |

### 2.4 系统级监控

| 指标 | 正常 | 警告 | 严重 | AOSP 17 变化 |
|:---|:---|:---|:---|:---|
| GC 线程 CPU 占用 | < 20% | 20-50% | > 50% | **★ 动态 sleep -5-15%** |
| Trim Heap 频率 | < 5/h | 5-20/h | > 20/h | 不变 |
| NativeAlloc GC 频率 | < 5/h | 5-20/h | > 20/h | **★ 限流** |
| Native 内存占用（Linux 6.18 sheaves） | -15-20% | — | — | **★ 新增** |
| 续航影响 | 基线 | — | — | **★ +3-8%** |

### 2.5 ★ ART 17 STW 时间监控

| STW 类别 | 正常 | 警告 | 严重 | AOSP 17 变化 |
|:---|:---|:---|:---|:---|
| **kGcCauseForAlloc Minor STW** | **< 1ms** | **1-3ms** | **> 3ms** | **★ 新增（Minor 优先）** |
| **kGcCauseForAlloc Major STW** | **< 20ms** | **20-50ms** | **> 50ms** | **★ 罕见** |
| kGcCauseBackground STW | < 5ms | 5-10ms | > 10ms | 不变 |
| kSoftThreshold STW | < 1ms | 1-3ms | > 3ms | **★ 新增** |
| kBackgroundGenCC STW | < 1ms | 1-3ms | > 3ms | **★ 新增** |
| **总 STW 时间** | **< 1ms × N** | **1-5ms** | **> 5ms** | **★ Minor 优先** |

---

## 三、业务层 GC 优化建议

### 3.1 优化清单（v1 + v2 完整版）

```
□ 1. 减少对象分配（避免 GC_FOR_ALLOC）
□ 2. 主动管理内存（避免 Native 内存泄漏）
□ 3. 监听 onTrimMemory（配合系统 Trim）
□ 4. 不调用 System.gc()（除非必要）
□ 5. 不重写 finalize()（用 Cleaner 替代）
□ 6. 监控 GcCause 频率（APM 告警）

★ ART 17 新增：
□ 7. 监控软阈值触发频率（> 30/min 告警）
□ 8. 监控 Minor 比例（> 80% 正常，< 50% 异常）
□ 9. 适配 BackgroundGenCC（不用主动处理）
□ 10. 监控 HeapTaskDaemon 动态 sleep（CPU 忙时延后）
□ 11. 监控 Native 限流（避免 Native OOM）
□ 12. 利用软阈值（让 ART 17 自动处理 60% 的 GC）
```

### 3.2 ★ ART 17 业务适配建议

#### 建议 1：让软阈值自动处理（推荐）

```java
// ✅ 好：让 ART 17 软阈值自动处理 GC
public class OptimizedApp {
    public void onCreate() {
        // 1. 正常初始化业务（不主动触发 GC）
        // 2. ART 17 软阈值 30% 会自动处理 60% 的 GC
        // 3. 业务层无需特殊处理
    }
}

// ❌ 坏：主动触发 GC（破坏 ART 17 优化）
public class BadApp {
    public void onCreate() {
        // 主动 GC（破坏软阈值机制）
        System.gc();  // ❌ 不推荐
    }
}
```

#### 建议 2：避免频繁小对象分配

```java
// ✅ 好：复用对象
public class OptimizedClass {
    private final StringBuilder sb = new StringBuilder(1024);
    private final Object[] cache = new Object[100];

    public void doSomething() {
        sb.setLength(0);  // 复用 StringBuilder
        sb.append("hello");
    }
}

// ❌ 坏：循环中频繁分配
public class BadClass {
    public void doSomething() {
        for (int i = 0; i < 1000; i++) {
            String s = new String("item" + i);  // ❌ 频繁分配
            process(s);
        }
    }
}
```

#### 建议 3：监控关键指标

```java
// ✅ 好：监控 ART 17 关键指标
public class Art17Monitor {
    // 1. 监控软阈值触发频率
    public void checkSoftThreshold() {
        int softCount = readSoftThresholdCount();
        if (softCount > 30) {
            // 告警：软阈值触发过于频繁
        }
    }

    // 2. 监控 Minor 比例
    public void checkMinorRatio() {
        double minorRatio = readMinorRatio();
        if (minorRatio < 0.5) {
            // 告警：Minor 比例过低，OOM 风险
        }
    }
}
```

#### 建议 4：避免 Native 内存泄漏

```java
// ✅ 好：用 Cleaner 替代 finalize
public class NativeResource implements AutoCloseable {
    private long nativePtr;

    public NativeResource() {
        this.nativePtr = allocateNative();
        Cleaner.create(this, new Deallocator(nativePtr));
    }

    @Override
    public void close() {
        // 主动释放（避免依赖 GC）
        releaseNative(nativePtr);
    }
}

// ❌ 坏：用 finalize
public class BadNativeResource {
    private long nativePtr;

    @Override
    protected void finalize() throws Throwable {
        // ❌ 不推荐（GC 不可控，ART 17 改进后仍有风险）
        releaseNative(nativePtr);
    }
}
```

### 3.3 ★ ART 17 OEM 升级建议

#### 建议 1：监控指标全面升级

```
升级前（v1 时代）：
  □ 监控 GcCause 频率
  □ 监控 HeapTaskDaemon 状态
  □ 监控 Foreground/Background GC 比例

★ 升级后（AOSP 17）：
  □ + 监控软阈值触发频率（kSoftThreshold）
  □ + 监控 BackgroundGenCC 频率
  □ + 监控 Minor 比例
  □ + 监控 Native 限流
  □ + 监控 HeapTaskDaemon 动态 sleep
```

#### 建议 2：4 大必回归测试项

```
□ 1. 老 App 软阈值兼容性
   - 大量小对象分配的老 App 可能卡顿
   - 测试：运行 1h，观察软阈值触发频率

□ 2. 第三方库 GC 兼容性
   - 部分老库可能不兼容 ART 17 GC
   - 测试：典型业务场景回归

□ 3. 端侧 LLM 加载性能
   - 1-10GB 模型加载期间频繁 GC
   - 测试：模型加载 5min，观察 GC 行为

□ 4. Heap 布局变化
   - ART 17 调整了 Space 大小比例
   - 测试：检查 OOM 边界
```

#### 建议 3：配置参数迁移

```bash
# ★ v1 → v2 配置参数迁移

# v1 时代（保留）
adb shell setprop dalvik.vm.heapgrowthlimit 256m
adb shell setprop dalvik.vm.heapsize 512m
adb shell setprop dalvik.vm.heaptargetutilization 0.75

# v2 升级新增（AOSP 17）
adb shell setprop dalvik.vm.soft-threshold-percent 30
adb shell setprop dalvik.vm.heap-task-daemon.min-sleep 500
adb shell setprop dalvik.vm.heap-task-daemon.max-sleep 2000
adb shell setprop dalvik.vm.native-alloc-throttle enable
```

---

## 四、★ ART 17 APM 监控代码（升级版）

### 4.1 GcCause 监控（v2 升级版）

```java
public class GcCauseMonitorV17 {
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

        // 4. ★ ART 17 软阈值专项告警
        int softThresholdCount = causeCount.getOrDefault("kSoftThreshold", 0);
        if (softThresholdCount > 50) {
            apmClient.alert("gc.cause.soft.high",
                "kSoftThreshold > 50/min，可能老 App 不适应");
        }

        // 5. ★ ART 17 BackgroundGenCC 告警
        int backgroundGenCC = causeCount.getOrDefault("kBackgroundGenCC", 0);
        if (backgroundGenCC > 10) {
            apmClient.alert("gc.cause.background.gencc.high",
                "BackgroundGenCC > 10/min，可能内存压力");
        }

        // 6. ★ ART 17 Native 限流告警
        int nativeThrottled = causeCount.getOrDefault("kGcCauseForNativeAllocThrottled", 0);
        if (nativeThrottled > 20) {
            apmClient.alert("gc.cause.native.throttled.high",
                "Native 限流 > 20/h，可能 Native 内存压力");
        }

        // 7. 原有告警
        int allocCount = causeCount.getOrDefault("kGcCauseForAlloc", 0);
        if (allocCount > 10) {
            apmClient.alert("gc.cause.alloc.high",
                "kGcCauseForAlloc > 10/min，可能内存泄漏");
        }
    }
}
```

### 4.2 ★ ART 17 GC 比例监控（v2 升级版）

```java
public class GcRatioMonitorV17 {
    @Scheduled(fixedRate = 60000)
    public void monitor() {
        // 1. 读取最近 1 分钟的 GC 日志
        List<GcEvent> events = readRecentGcEvents();

        // 2. 统计 kGcCauseForAlloc 的 Minor / Major 比例
        int forAllocCount = 0;
        int minorCount = 0;
        int majorCount = 0;
        for (GcEvent e : events) {
            if (e.cause.equals("kGcCauseForAlloc")) {
                forAllocCount++;
                if (e.reason.equals("MinorGc")) {
                    minorCount++;
                } else if (e.reason.equals("MajorGc")) {
                    majorCount++;
                }
            }
        }

        // 3. 上报
        apmClient.report("gc.foralloc.count", forAllocCount);
        apmClient.report("gc.foralloc.minor.count", minorCount);
        apmClient.report("gc.foralloc.major.count", majorCount);

        // 4. ★ ART 17 Minor 比例告警
        if (forAllocCount > 0) {
            double minorRatio = (double) minorCount / forAllocCount;
            apmClient.report("gc.foralloc.minor.ratio", minorRatio);
            if (minorRatio < 0.5) {
                apmClient.alert("gc.foralloc.minor.low",
                    "Minor 比例 < 50%，可能 OOM 边界");
            }
        }

        // 5. ★ ART 17 计算软阈值占比
        int softThresholdCount = readSoftThresholdCount();
        int totalGcCount = events.size();
        if (totalGcCount > 0) {
            double softRatio = (double) softThresholdCount / totalGcCount;
            apmClient.report("gc.cause.soft.ratio", softRatio);
            // ART 17 正常范围：30-60%
            if (softRatio < 0.2) {
                apmClient.alert("gc.cause.soft.low",
                    "软阈值占比 < 20%，可能软阈值参数未生效");
            } else if (softRatio > 0.8) {
                apmClient.alert("gc.cause.soft.high",
                    "软阈值占比 > 80%，可能老 App 不适应");
            }
        }

        // 6. 原有 Foreground GC 比例
        int fgCount = readForegroundGcCount();
        int bgCount = readBackgroundGcCount();
        if ((fgCount + bgCount) > 0) {
            double fgRatio = (double) fgCount / (fgCount + bgCount);
            apmClient.report("gc.fg.ratio", fgRatio);
            if (fgRatio > 0.3) {
                apmClient.alert("gc.fg.high", "Foreground GC > 30%");
            }
        }
    }
}
```

### 4.3 ★ ART 17 HeapTaskDaemon 监控（v2 升级版）

```java
public class HeapTaskDaemonMonitorV17 {
    @Scheduled(fixedRate = 30000)
    public void monitor() {
        // 1. ★ ART 17 动态 sleep 监控
        long currentSleepMs = readHeapTaskDaemonSleepMs();
        apmClient.report("heap.task.daemon.sleep.ms", currentSleepMs);
        if (currentSleepMs == 1000) {
            // 仍是固定 1s，可能未升级到 ART 17
            apmClient.alert("heap.task.daemon.sleep.fixed",
                "HeapTaskDaemon sleep 固定 1s，可能未启用 ART 17 优化");
        }

        // 2. ★ ART 17 任务队列长度
        int queueLength = readHeapTaskQueueLength();
        apmClient.report("heap.task.queue.length", queueLength);
        if (queueLength > 20) {
            apmClient.alert("heap.task.queue.high", "任务队列 > 20");
        }

        // 3. ★ ART 17 任务类型分布
        Map<String, Integer> taskTypeCount = readTaskTypeDistribution();
        taskTypeCount.forEach((type, count) -> {
            apmClient.report("heap.task.type." + type, count);
        });

        // 4. ★ ART 17 软阈值触发任务数
        int softThresholdTasks = taskTypeCount.getOrDefault("SoftThresholdGCTask", 0);
        if (softThresholdTasks > 50) {
            apmClient.alert("heap.task.soft.high",
                "SoftThresholdGCTask > 50/min");
        }
    }
}
```

### 4.4 ★ ART 17 综合监控（v2 升级版）

```java
public class Art17GcSchedulingMonitor {
    @Scheduled(fixedRate = 30000)
    public void monitor() {
        // 1. GcCause 监控
        GcCauseMonitorV17 causeMonitor = new GcCauseMonitorV17();
        causeMonitor.monitor();

        // 2. GC 比例监控
        GcRatioMonitorV17 ratioMonitor = new GcRatioMonitorV17();
        ratioMonitor.monitor();

        // 3. HeapTaskDaemon 监控
        HeapTaskDaemonMonitorV17 daemonMonitor = new HeapTaskDaemonMonitorV17();
        daemonMonitor.monitor();

        // 4. ★ ART 17 综合健康度评分
        int healthScore = calculateArt17HealthScore();
        apmClient.report("art17.gc.health.score", healthScore);

        if (healthScore < 60) {
            apmClient.alert("art17.gc.health.low",
                "ART 17 GC 健康度 < 60，建议检查");
        }
    }

    private int calculateArt17HealthScore() {
        int score = 100;

        // 1. 软阈值触发频率扣分
        int softCount = readSoftThresholdCount();
        if (softCount > 50) score -= 20;
        else if (softCount > 30) score -= 10;

        // 2. Minor 比例扣分
        double minorRatio = readMinorRatio();
        if (minorRatio < 0.5) score -= 30;
        else if (minorRatio < 0.8) score -= 10;

        // 3. HeapTaskDaemon 队列扣分
        int queueLength = readHeapTaskQueueLength();
        if (queueLength > 20) score -= 20;
        else if (queueLength > 5) score -= 10;

        // 4. Native 限流扣分
        int nativeThrottled = readNativeThrottledCount();
        if (nativeThrottled > 20) score -= 15;

        return Math.max(score, 0);
    }
}
```

---

## 五、★ ART 17 vs v1 工程基线对账

### 5.1 参数变化

| 参数 | v1 时代（AOSP 14） | v2 升级（AOSP 17） | 变化 |
|:---|:---|:---|:---|
| GcCause 数量 | 9 | **11** | **+2** |
| HeapTask 数量 | 3 | **5** | **+2** |
| HeapTaskDaemon sleep | 固定 1s | **0.5-2s 动态** | **核心升级** |
| kGcCauseForAlloc 默认策略 | kMajorGc | **kMinorGc** | **核心升级** |
| 后台 GC 路径 | ConcurrentMajorGc | **BackgroundGenCC** | **核心升级** |
| kSoftThresholdPercent | 不存在 | **30%** | **★ 新增** |
| Native 限流 | 不存在 | **启用** | **★ 新增** |
| urgency_level | 不存在 | **0-3** | **★ 新增** |
| 监控指标 | 6 个 | **11+ 个** | **+83%** |
| APM 代码 | 基础版 | **ART 17 升级版** | **核心升级** |

### 5.2 性能提升

| 指标 | v1 时代 | v2 升级 | 提升 |
|:---|:---|:---|:---|
| kGcCauseForAlloc STW | 5-50ms | **< 1ms（大多数）** | **-80%** |
| CPU 占用 | 基线 | **-5-15%** | **降低** |
| 续航 | 基线 | **+3-8%** | **改善** |
| Full GC 频率 | 高 | **-70%** | **降低** |
| 软阈值提前处理 | 不支持 | **~50-60%** | **★ 新增** |
| Native 内存（Linux 6.18） | -15-20% | -15-20% | 跨系列 |

### 5.3 工程价值

```
★ ART 17 升级的核心价值：

1. STW 时间降低 80%
   - kGcCauseForAlloc 从 5-50ms 降至 < 1ms
   - 用户感知卡顿大幅降低

2. CPU 占用降低 5-15%
   - HeapTaskDaemon 动态 sleep
   - BackgroundGenCC 更轻量
   - 续航改善 3-8%

3. Full GC 罕见化（-70%）
   - Minor GC 优先
   - 软阈值提前处理 60%

4. 监控精细化
   - 11 个 GcCause 监控
   - Minor 比例监控
   - 软阈值触发监控
   - 紧急程度监控
```

---

## 六、★ ART 17 风险地图

| 风险 | 影响 | 触发条件 | 修复 |
|:---|:---|:---|:---|
| **老 App 软阈值不适** | 卡顿 | 大量小对象 | 调高软阈值（30→40） |
| **第三方库 GC 兼容** | 异常 | 老库不兼容 | 升级到 ART 17 兼容版 |
| **端侧 LLM 加载压力** | 频繁 GC | 1-10GB 模型 | 调大堆 + 软阈值调优 |
| **Heap 布局变化** | OOM 边界 | Space 大小变化 | 调整 heapgrowthlimit |
| **Reference 处理变化** | 软引用释放时机 | 微调 | 监听 Reference 行为 |
| **监控指标未升级** | 漏报 | 仍用 v1 监控 | 升级到 ART 17 监控 |

---

## 七、★ ART 17 Takeaway

1. **GcCause 11 种 + HeapTask 5 种 + urgency_level** —— AOSP 17 调度精细化。**监控指标必须升级**。
2. **kGcCauseForAlloc 优先 Minor（< 1ms STW）** —— Full GC 罕见化（-70%）。**STW 时间降低 80%**。
3. **HeapTaskDaemon 动态 sleep（0.5-2s）** —— CPU 占用降低 5-15%。**续航改善 3-8%**。
4. **软阈值 kSoftThresholdPercent=30%** —— 提前处理 60% GC。**避免 OOM 边界被动 GC**。
5. **OEM 升级必回归测试 4 项** —— 软阈值 / 第三方库 / 端侧 LLM / Heap 布局。

---

> **本附录完结**。07 子模块 4 篇正文 + 3 个附录（4 附录之 3/4）v2 升级版全部完成。

