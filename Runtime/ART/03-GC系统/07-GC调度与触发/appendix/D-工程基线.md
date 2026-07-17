# 附录 D：工程基线（GC 调度与触发）

## 一、关键参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `dalvik.vm.heapgrowthlimit` | 256 MB | 堆增长上限 |
| `dalvik.vm.heapsize` | 512 MB | largeHeap |
| `dalvik.vm.heaptargetutilization` | 0.75 | 目标使用率 |
| `concurrent_start_threshold` | 0.5 | 后台 GC 触发阈值 |
| `dalvik.vm.gc.threads` | 4 | GC 工作线程数 |
| `dalvik.vm.gc.priority` | -19 | GC 线程优先级 |

## 二、监控指标

| 指标 | 正常 | 警告 | 严重 |
|:---|:---|:---|:---|
| Background GC 频率 | 5-10/分钟 | 10-30/分钟 | > 30/分钟 |
| Foreground GC 比例 | < 10% | 10-30% | > 30% |
| HeapTaskDaemon 队列长度 | < 5 | 5-20 | > 20 |
| GC 线程 CPU 占用 | < 20% | 20-50% | > 50% |
| Trim Heap 频率 | < 5/小时 | 5-20/小时 | > 20/小时 |
| NativeAlloc GC 频率 | < 5/小时 | 5-20/小时 | > 20/小时 |

## 三、业务层 GC 优化建议

```
□ 1. 减少对象分配（避免 GC_FOR_ALLOC）
□ 2. 主动管理内存（避免 Native 内存泄漏）
□ 3. 监听 onTrimMemory（配合系统 Trim）
□ 4. 不调用 System.gc()（除非必要）
□ 5. 不重写 finalize()（用 Cleaner 替代）
□ 6. 监控 GcCause 频率（APM 告警）
```

## 四、APM 监控

```java
public class GcSchedulingMonitor {
    @Scheduled(fixedRate = 60000)
    public void monitor() {
        // 1. 统计 GcCause 频率
        Map<String, Integer> causeCount = countCausesInLastMinute();
        causeCount.forEach((cause, count) -> {
            apmClient.report("gc.cause." + cause, count);
        });
        
        // 2. 计算 Foreground GC 比例
        int fgCount = causeCount.getOrDefault("kGcCauseForAlloc", 0);
        int bgCount = causeCount.getOrDefault("kGcCauseBackground", 0);
        double fgRatio = (double) fgCount / (fgCount + bgCount + 1);
        apmClient.report("gc.fg.ratio", fgRatio);
        
        // 3. 告警
        if (fgRatio > 0.3) {
            apmClient.alert("gc.fg.high", "Foreground GC > 30%");
        }
    }
}
```
