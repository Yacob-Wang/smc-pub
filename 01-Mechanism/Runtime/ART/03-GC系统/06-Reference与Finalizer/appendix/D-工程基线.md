# 附录 D：工程基线（Reference 与 Finalizer）（v2 升级版）

> **本附录定位**：**工程基线**—— 关键参数 + 监控指标 + 业务代码建议 + APM 监控代码 + 治理方案
>
> **基线版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS，2024-11-17 发布，EOL 2026-12）
>
> **v2 升级日期**：2026-07-18（v1 旧文按 v4 规范 + 新基线升级）

---

## 0. 本附录定位声明

| 维度 | 本附录承担 | 本附录不涉及 |
| :--- | :--- | :--- |
| 关键参数 | ✓ 完整参数表 + ART 17 新增 | — |
| 监控指标 | ✓ 完整指标 + 阈值 | — |
| 业务代码建议 | ✓ 7 条建议 | — |
| APM 监控代码 | ✓ 完整代码 | — |
| 治理方案 | ✓ 优先级矩阵 | — |
| **ART 17 工程基线** | ✓ FinalizerThreadPool + GenCC 软阈值 + 慢对象检测 | — |
| 源码索引 | — | [appendix/A-源码索引](A-源码索引.md) 详细 |
| 路径对账 | — | [appendix/B-路径对账](B-路径对账.md) 详细 |

**承接自**：本附录承接 [appendix/A-源码索引](A-源码索引.md)（重写为 v2 升级版）+ [appendix/B-路径对账](B-路径对账.md)（重写为 v2 升级版），提供工程落地基线。

**衔接去**：[appendix/A-源码索引](A-源码索引.md) 返回源码索引（重写为 v2 升级版）；[appendix/B-路径对账](B-路径对账.md) 返回路径对账（重写为 v2 升级版）；[10-ART17分代GC强化专章 v2](../10-ART17分代GC强化专章-v2.md) ART 17 分代 GC 强化。

---

## 校准决策日志（v2 升级 · 3 轮全跑）

### 第 1 轮：结构校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| v1 旧稿标记段 | 在（顶部 14 行） | **删**（v1 → v2 实质升级） | 内容已按 v4 规范重写，标记段失效 |
| 本附录定位声明 | 无 | **新增**（v4 §3 强制要求） | v1 后期已按 v4 写但缺本附录定位段 |
| 衔接去 | 无 | **新增 3 个附录/篇** | 跨篇引用矩阵要求显式关联 |

### 第 2 轮：硬伤校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 基线版本号 | AOSP 14 / Linux 5.10 | AOSP 17 / **Linux 6.18** | **2026-07-18 基线升级 |
| API 等级 | API 34 | **API 37** | 与 AOSP 17 配套 |
| **ART 17 关键参数** | 未覆盖 | **新增 §1.2 整节** | AOSP 17 新增 |
| **ART 17 监控指标** | 未覆盖 | **新增 §2.2 整节** | AOSP 17 新增 |

### 第 3 轮：锐度校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 业务代码建议 | 7 条 | **保留 + 增补 ART 17 相关 3 条** | 覆盖 v2 增量 |
| 治理方案 | 优先级矩阵 | **扩展为完整方案 + ART 17 治理** | 实战可查性 |

---

## 一、关键参数

### 1.1 AOSP 14/17 共用参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `dalvik.vm.softrefthreshold` | 0.25 | 软引用阈值 |
| `MAX_FINALIZE_TIME_MS` | 10 秒 | finalize 超时 |
| `INTERVAL_MS` (Watchdog) | 1 秒 | 检查间隔 |
| `MAX_FINALIZE_COUNT` | 2 次 | 复活次数 |

### 1.2 **ART 17 新增参数**

| 参数 | 默认值 | 备注 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `FINALIZER_THREAD_COUNT` | **4 线程** | Finalizer 线程池大小 | **AOSP 17 新增** |
| `SLOW_FINALIZE_THRESHOLD_MS` | **5 秒** | 慢对象检测阈值 | **AOSP 17 新增** |
| `FINALIZER_THREAD_PRIORITY` | **MIN_PRIORITY** | Finalizer 线程优先级 | **AOSP 17 新增** |
| `kSoftThresholdPercent` | **30%** | GenCC 软阈值 | **AOSP 17 新增** |

### 1.3 ART 17 完整参数表

| 参数 | 默认值 | 调试命令 | 备注 |
|:---|:---|:---|:---|
| `dalvik.vm.softrefthreshold` | 0.25 | `getprop dalvik.vm.softrefthreshold` | 软引用阈值 |
| `dalvik.vm.softthresholdpercent` | **30** | `getprop dalvik.vm.softthresholdpercent` | **GenCC 软阈值（AOSP 17 新增）** |
| `dalvik.vm.finalizer.thread.count` | **4** | `getprop dalvik.vm.finalizer.thread.count` | **Finalizer 线程数（AOSP 17 新增）** |
| `dalvik.vm.finalizer.slow.threshold` | **5000** | `getprop dalvik.vm.finalizer.slow.threshold` | **慢对象阈值（AOSP 17 新增）** |
| `MAX_FINALIZE_TIME_MS` | 10 秒 | logcat | Watchdog 超时（AOSP 14/17 共用） |
| `INTERVAL_MS` | 1 秒 | logcat | Watchdog 检查间隔（AOSP 14/17 共用） |
| `MAX_FINALIZE_COUNT` | 2 次 | logcat | 复活次数（AOSP 14/17 共用） |

### 1.4 ART 17 vs ART 14 参数对比

| 参数 | AOSP 14 默认 | AOSP 17 默认 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `dalvik.vm.softrefthreshold` | 0.25 | 0.25 | 不变 |
| **`dalvik.vm.softthresholdpercent`** | **N/A** | **30** | **AOSP 17 新增** |
| Finalizer 线程数 | 1 线程 | **4 线程池** | **AOSP 17 池化** |
| 慢对象阈值 | N/A | **5 秒** | **AOSP 17 新增** |
| Finalizer 优先级 | NORM_PRIORITY | **MIN_PRIORITY** | **AOSP 17 强化** |
| Watchdog 超时 | 10 秒 | 10 秒 | 不变 |
| Watchdog 检查间隔 | 1 秒 | 1 秒 | 不变 |

---

## 二、监控指标

### 2.1 AOSP 14/17 共用监控指标

| 指标 | 正常 | 警告 | 严重 |
|:---|:---|:---|:---|
| finalize() 队列长度 | < 10 | 10-100 | > 100 |
| finalize() 执行时长 | < 1s | 1-10s | > 10s |
| Watchdog 警告频率 | 0 | > 5/h | > 30/h |
| DirectByteBuffer 数量 | < 100 | 100-500 | > 1000 |
| SoftReference 数量 | < 1000 | 1K-10K | > 10K |
| WeakReference 数量 | < 100 | 100-1K | > 10K |

### 2.2 **ART 17 新增监控指标**

| 指标 | 正常 | 警告 | 严重 | 备注 |
|:---|:---|:---|:---|:---|
| **Finalizer 线程数** | **4** | **< 4** | **1** | **AOSP 17 应为 4** |
| **Finalizer 队列长度（AOSP 17）** | **< 30** | **30-200** | **> 200** | **AOSP 17 阈值放宽** |
| **慢对象数量** | **0** | **1-10/h** | **> 10/h** | **AOSP 17 新增** |
| **Reference 处理时间** | **< 1ms** | **1-5ms** | **> 5ms** | **AOSP 17 强化后应 < 1ms** |
| **Heap Dump 时间** | **< 2s** | **2-5s** | **> 5s** | **AOSP 17 加速后应 < 2s** |
| **GenCC 软阈值触发频率** | **5-10/min** | **< 1/min 或 > 20/min** | **持续异常** | **AOSP 17 联动** |
| **Finalizer 优先级** | **MIN_PRIORITY** | **NORM_PRIORITY** | **MAX_PRIORITY** | **AOSP 17 应为 MIN** |

### 2.3 ART 17 监控指标总表

| 类别 | 指标 | 监控命令 |
|:---|:---|:---|
| Finalizer | 队列长度 | `adb shell dumpsys meminfo <pkg> \| grep "Finalizer queue"` |
| Finalizer | 线程数 | `adb shell dumpsys meminfo <pkg> \| grep "Finalizer thread"` |
| Finalizer | 慢对象数量 | `adb logcat -s "art" \| grep "SlowFinalizer"` |
| Finalizer | Watchdog 警告 | `adb logcat -s "art" \| grep "Finalizer watch dog"` |
| Reference | SoftReference 数量 | `adb shell dumpsys meminfo <pkg> \| grep -i "soft"` |
| Reference | WeakReference 数量 | `adb shell dumpsys meminfo <pkg> \| grep -i "weak"` |
| Reference | Reference 处理时间 | `adb logcat -s "art" \| grep "Reference processing"` |
| DirectByteBuffer | 数量 | `adb shell dumpsys meminfo <pkg> \| grep -i "direct"` |
| Heap Dump | 时间 | `adb shell am dumpheap` + 计时 |
| GenCC | 软阈值触发 | `adb logcat -s "art" \| grep "softthreshold"` |

---

## 三、业务代码建议

### 3.1 AOSP 14/17 共用建议

```
□ 1. 不使用 finalize()（除了特殊场景）
□ 2. native 资源用 Cleaner 释放
□ 3. Java 资源用 AutoCloseable + try-with-resources
□ 4. Cursor / Bitmap / FileDescriptor 主动关闭
□ 5. DirectByteBuffer 用对象池复用
□ 6. 监控 Watchdog 警告
□ 7. 定期扫描 finalize() 用法
```

### 3.2 **ART 17 新增建议**

```
□ 8. 利用 Finalizer 线程池化（AOSP 17 自动收益）
  - 升级到 AOSP 17 后无需改代码，Finalizer 处理从单线程 → 4 线程
  - 但仍推荐迁移 finalize() 到 Cleaner（长期）

□ 9. 监控 GenCC 软阈值（联动软引用）
  - 堆占用达到 30% 触发 Young GC
  - 软引用缓存命中率应作为关键监控指标
  - 命中率 < 70% 需调优（调整 kSoftThresholdPercent）

□ 10. 利用 Heap Dump 加速（AOSP 17 增强）
  - 集成 LeakCanary 3.x 利用 Android 14+ Heap Dump API
  - 实时内存泄漏检测成为可能（5 秒间隔 + < 12 秒告警）
  - 减少 Heap Dump 对业务影响（增量 Heap Dump）
```

### 3.3 完整建议清单（10 条）

```
□ 1. 不使用 finalize()（除了特殊场景）
□ 2. native 资源用 Cleaner 释放
□ 3. Java 资源用 AutoCloseable + try-with-resources
□ 4. Cursor / Bitmap / FileDescriptor 主动关闭
□ 5. DirectByteBuffer 用对象池复用
□ 6. 监控 Watchdog 警告
□ 7. 定期扫描 finalize() 用法
□ 8. 利用 Finalizer 线程池化（AOSP 17 自动收益）
□ 9. 监控 GenCC 软阈值（联动软引用）
□ 10. 利用 Heap Dump 加速（AOSP 17 增强）
```

### 3.4 finalize() 迁移指南

**何时迁移**：

```
优先级 1（必须迁移）：
  - finalize() 阻塞（> 5s）
  - finalize() 频繁调用（> 100/h）
  - finalize() 释放 native 资源（DirectByteBuffer 等）

优先级 2（推荐迁移）：
  - finalize() 释放敏感资源（数据库连接等）
  - 监控告警频繁
  - 业务对延迟敏感

优先级 3（可选迁移）：
  - finalize() 简单清理（标记日志等）
  - 监控告警少
  - 业务对延迟不敏感
```

**迁移步骤**：

```java
// 步骤 1：识别 finalize() 用法
grep -rn "protected void finalize" src/main/java/

// 步骤 2：分类处理
// - 释放 native 资源：用 Cleaner 替代
// - 释放 Java 资源：用 AutoCloseable 替代
// - 简单清理：评估是否真正需要

// 步骤 3：实现 Cleaner 替代
public class NativeResource {
    private final long nativePtr;
    private final Cleaner cleaner;
    
    public NativeResource() {
        this.nativePtr = nativeAlloc();
        this.cleaner = Cleaner.create(this, () -> {
            if (nativePtr != 0) {
                nativeFree(nativePtr);
            }
        });
    }
}

// 步骤 4：验证
// - 单元测试
// - 集成测试
// - 灰度发布
// - 全量发布
```

---

## 四、APM 监控代码

### 4.1 基础监控（AOSP 14/17 共用）

```java
public class ReferenceMonitor {
    @Scheduled(fixedRate = 30000)
    public void monitor() {
        // 1. 看 finalize() 队列长度（debug 模式）
        int finalizeQueueSize = getFinalizeQueueSize();
        apmClient.report("finalize.queue.size", finalizeQueueSize);
        
        if (finalizeQueueSize > 100) {
            apmClient.alert("finalize.queue.high", "Finalize queue > 100");
        }
        
        // 2. 看 DirectByteBuffer 数量
        int directBufferCount = countDirectByteBuffers();
        apmClient.report("directbuffer.count", directBufferCount);
        
        // 3. 看 SoftReference 数量
        int softRefCount = countSoftReferences();
        apmClient.report("softref.count", softRefCount);
    }
}
```

### 4.2 **ART 17 增强监控**

```java
public class ART17ReferenceMonitor {
    @Scheduled(fixedRate = 30000)
    public void monitor() {
        // 1. 监控 Finalizer 线程数
        int finalizerThreadCount = getFinalizerThreadCount();
        apmClient.report("finalizer.thread.count", finalizerThreadCount);
        if (finalizerThreadCount != 4) {
            apmClient.alert("finalizer.thread.count.anomaly", 
                "Expected 4 threads, got " + finalizerThreadCount);
        }
        
        // 2. 监控慢对象数量
        int slowObjectCount = getSlowFinalizerCount();
        apmClient.report("finalizer.slow.count", slowObjectCount);
        if (slowObjectCount > 10) {
            apmClient.alert("finalizer.slow.high", 
                "Slow finalizer count > 10");
        }
        
        // 3. 监控 Reference 处理时间
        long referenceProcessTime = getReferenceProcessTime();
        apmClient.report("reference.process.time", referenceProcessTime);
        if (referenceProcessTime > 5) {
            apmClient.alert("reference.process.slow", 
                "Reference processing > 5ms");
        }
        
        // 4. 监控 GenCC 软阈值触发
        int softThresholdTriggerCount = getSoftThresholdTriggerCount();
        apmClient.report("softthreshold.trigger.count", softThresholdTriggerCount);
        if (softThresholdTriggerCount < 1) {
            apmClient.alert("softthreshold.trigger.low", 
                "GenCC soft threshold not triggering");
        }
        
        // 5. 监控 Heap Dump 时间
        long lastHeapDumpTime = getLastHeapDumpTime();
        apmClient.report("heapdump.time", lastHeapDumpTime);
        if (lastHeapDumpTime > 5000) {
            apmClient.alert("heapdump.slow", 
                "Heap dump time > 5s");
        }
    }
}
```

### 4.3 完整监控代码

```java
public class ComprehensiveReferenceMonitor {
    @Scheduled(fixedRate = 30000)
    public void monitor() {
        // ============ AOSP 14/17 共用监控 ============
        
        // 1. Finalizer 队列长度
        int finalizeQueueSize = getFinalizeQueueSize();
        apmClient.report("finalize.queue.size", finalizeQueueSize);
        
        // 2. DirectByteBuffer 数量
        int directBufferCount = countDirectByteBuffers();
        apmClient.report("directbuffer.count", directBufferCount);
        
        // 3. SoftReference 数量
        int softRefCount = countSoftReferences();
        apmClient.report("softref.count", softRefCount);
        
        // 4. WeakReference 数量
        int weakRefCount = countWeakReferences();
        apmClient.report("weakref.count", weakRefCount);
        
        // ============ ART 17 增强监控 ============
        
        // 5. Finalizer 线程数
        int finalizerThreadCount = getFinalizerThreadCount();
        apmClient.report("finalizer.thread.count", finalizerThreadCount);
        
        // 6. 慢对象数量
        int slowObjectCount = getSlowFinalizerCount();
        apmClient.report("finalizer.slow.count", slowObjectCount);
        
        // 7. Reference 处理时间
        long referenceProcessTime = getReferenceProcessTime();
        apmClient.report("reference.process.time", referenceProcessTime);
        
        // 8. GenCC 软阈值触发
        int softThresholdTriggerCount = getSoftThresholdTriggerCount();
        apmClient.report("softthreshold.trigger.count", softThresholdTriggerCount);
        
        // 9. Heap Dump 时间
        long lastHeapDumpTime = getLastHeapDumpTime();
        apmClient.report("heapdump.time", lastHeapDumpTime);
        
        // ============ 告警逻辑 ============
        
        if (finalizeQueueSize > 100) {
            apmClient.alert("finalize.queue.high", "Finalize queue > 100");
        }
        if (directBufferCount > 1000) {
            apmClient.alert("directbuffer.count.high", "DirectByteBuffer > 1000");
        }
        if (softRefCount > 10000) {
            apmClient.alert("softref.count.high", "SoftReference > 10K");
        }
        if (weakRefCount > 10000) {
            apmClient.alert("weakref.count.high", "WeakReference > 10K");
        }
        if (finalizerThreadCount != 4) {
            apmClient.alert("finalizer.thread.count.anomaly", 
                "Expected 4 threads, got " + finalizerThreadCount);
        }
        if (slowObjectCount > 10) {
            apmClient.alert("finalizer.slow.high", "Slow finalizer count > 10");
        }
        if (referenceProcessTime > 5) {
            apmClient.alert("reference.process.slow", "Reference processing > 5ms");
        }
        if (lastHeapDumpTime > 5000) {
            apmClient.alert("heapdump.slow", "Heap dump time > 5s");
        }
    }
}
```

### 4.4 监控数据可视化

```
┌────────────────────────────────────────────────────────┐
│ Reference 与 Finalizer 监控面板（AOSP 17）                 │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Finalizer 线程数：4 (期望 4) ✓                          │
│  Finalizer 队列长度：45 (警告 30-200)                    │
│  Watchdog 警告频率：0/h (正常) ✓                        │
│  Reference 处理时间：0.8ms (正常 < 1ms) ✓                │
│  Heap Dump 时间：1.5s (正常 < 2s) ✓                    │
│  GenCC 软阈值触发：5/min (正常 5-10/min) ✓              │
│  DirectByteBuffer 数量：85 (正常 < 100) ✓               │
│  SoftReference 数量：4500 (正常 < 10K) ✓                │
│  WeakReference 数量：120 (正常 < 1K) ✓                  │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## 五、治理方案

### 5.1 治理优先级矩阵（AOSP 14/17 共用）

| 优先级 | 治理项 | 收益 |
|:---|:---|:---|
| **高** | 禁用 finalize() | 消除 Watchdog 警告 |
| **高** | 用 Cleaner 替代 finalize() | native 资源正确释放 |
| **中** | 用 AutoCloseable 替代手动 close | 资源管理统一 |
| **中** | DirectByteBuffer 对象池 | 减少 native 内存 |
| **低** | 监控 finalize() 队列 | 提前发现问题 |

### 5.2 **ART 17 治理方案扩展**

| 优先级 | 治理项 | 收益 | ART 17 变化 |
|:---|:---|:---|:---|
| **高** | 升级到 AOSP 17 | Finalizer 4 线程池化 | **AOSP 17 自动收益** |
| **高** | 监控慢对象 | 避免单个慢对象阻塞 | **AOSP 17 新增监控** |
| **中** | 调优 GenCC 软阈值 | 软引用缓存命中率提升 | **AOSP 17 新增** |
| **中** | 集成 LeakCanary 3.x | 实时内存泄漏检测 | **AOSP 17 Heap Dump 加速** |
| **低** | 跟进 ART 17 小版本 | 持续优化 | **AOSP 17 持续演进** |

### 5.3 完整治理方案（10 条）

| 优先级 | 治理项 | 收益 | 实施难度 |
|:---|:---|:---|:---|
| **高** | 升级到 AOSP 17 | Finalizer 4 线程池化 + Heap Dump 加速 | 低（系统升级） |
| **高** | 禁用 finalize() | 消除 Watchdog 警告 | 中（代码迁移） |
| **高** | 用 Cleaner 替代 finalize() | native 资源正确释放 | 中（代码迁移） |
| **高** | 监控慢对象 | 避免单个慢对象阻塞 | 低（接入监控） |
| **中** | 用 AutoCloseable 替代手动 close | 资源管理统一 | 中（代码迁移） |
| **中** | DirectByteBuffer 对象池 | 减少 native 内存 | 中（代码改造） |
| **中** | 调优 GenCC 软阈值 | 软引用缓存命中率提升 | 低（参数调整） |
| **中** | 集成 LeakCanary 3.x | 实时内存泄漏检测 | 低（依赖升级） |
| **低** | 监控 finalize() 队列 | 提前发现问题 | 低（接入监控） |
| **低** | 跟进 ART 17 小版本 | 持续优化 | 低（版本跟进） |

### 5.4 治理时间表

```
第 1 周：基线检查
  - 监控指标建立
  - 基线数据收集

第 2-4 周：高优先级治理
  - 升级到 AOSP 17
  - 迁移 finalize() 到 Cleaner
  - 监控慢对象

第 5-8 周：中优先级治理
  - 用 AutoCloseable 替代手动 close
  - DirectByteBuffer 对象池
  - 调优 GenCC 软阈值
  - 集成 LeakCanary 3.x

第 9-12 周：低优先级治理
  - 持续监控
  - 跟进 ART 17 小版本
  - 优化治理策略
```

---

## 六、ART 17 工程基线速查

### 6.1 ART 17 关键参数

```
Finalizer 线程数：4（默认）
慢对象阈值：5 秒（默认）
GenCC 软阈值：30%（默认）
Finalizer 优先级：MIN_PRIORITY
软引用阈值：0.25（与 GenCC 30% 联动）
```

### 6.2 ART 17 关键监控

```
必监控：
  - Finalizer 队列长度（应 < 30）
  - Finalizer 线程数（应 = 4）
  - Watchdog 警告（应 = 0）
  - Heap Dump 时间（应 < 2s）

推荐监控：
  - 慢对象数量（应 = 0）
  - Reference 处理时间（应 < 1ms）
  - GenCC 软阈值触发（应 5-10/min）
  - DirectByteBuffer 数量（应 < 100）
```

### 6.3 ART 17 关键建议

```
新代码：
  - ✅ 用 Cleaner 替代 finalize()
  - ✅ 用 AutoCloseable + try-with-resources
  - ✅ 监控关键指标
  - ✅ 集成 LeakCanary 3.x

遗留代码：
  - 阶段 1：升级到 AOSP 17（自动收益）
  - 阶段 2：监控慢对象（识别问题）
  - 阶段 3：分阶段迁移到 Cleaner
  - 阶段 4：完全替代 finalize()
```

---

## 七、跨附录引用

| 引用方向 | 来源 | 目标 |
|:---|:---|:---|
| 引用 | [appendix/A-源码索引](A-源码索引.md) | 完整源码路径 |
| 引用 | [appendix/B-路径对账](B-路径对账.md) | AOSP 17 版本对账 + 调试命令 |
| 引用 | [01-可达性状态机](../01-可达性状态机.md) | Reference 状态机 |
| 引用 | [02-SoftReference](../02-SoftReference.md) | 软引用保留率 |
| 引用 | [03-WeakReference](../03-WeakReference.md) | 弱引用 + LeakCanary |
| 引用 | [04-FinalReference](../04-FinalReference.md) | Finalizer 线程池化 |
| 引用 | [10-ART17分代GC强化专章 v2](../10-ART17分代GC强化专章-v2.md) | ART 17 分代 GC 强化 |

---

> **本附录结束**。Reference 与 Finalizer 子模块 v2 升级版全部完成（4 篇正文 + 3 篇附录），全部按 v4 规范 + AOSP 17 + Linux 6.18 基线重写。

