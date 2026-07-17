# 附录 D：工程基线（GenCC）

## 一、关键参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `kRegionSize` | 256 KB | Region 大小 |
| `kCardSize` | 512 byte | 卡表粒度 |
| `kPromotionThreshold` | 15 次 | 晋升阈值 |
| `Young Gen 比例` | ~25% | 可动态调整 |
| `Old Gen 比例` | ~75% | — |

## 二、监控指标

| 指标 | 优秀 | 良好 | 差 |
|:---|:---|:---|:---|
| Minor GC STW | < 0.5ms | 0.5-1ms | > 1ms |
| Major GC STW | < 50ms | 50-100ms | > 100ms |
| Minor GC 频率 | < 5/分钟 | 5-15/分钟 | > 30/分钟 |
| Major GC 频率 | < 1/小时 | 1-3/小时 | > 5/小时 |
| Young Gen 使用率 | < 70% | 70-85% | > 85% |
| Old Gen 使用率 | < 60% | 60-80% | > 85% |

## 三、业务代码建议

```
□ 1. 静态集合慎用：LRU / SoftReference / WeakHashMap
□ 2. 长寿对象集中管理：避免 Young Gen 中的长寿对象
□ 3. 批量处理：减少跨代引用频率
□ 4. 监听内存压力：onTrimMemory / onLowMemory
□ 5. 使用专业库：Glide / Fresco / LruCache
```

## 四、APM 监控代码示例

```java
public class GenCCMonitor {
    public void onMinorGCFinish(long pauseTime) {
        apmClient.report("gc.minor.pause", pauseTime);
        if (pauseTime > 1) {
            apmClient.alert("gc.minor.pause.high", "Minor GC > 1ms");
        }
    }
    
    public void onPromote(int count) {
        apmClient.report("gc.promote.count", count);
        if (count > 10000) {  // 阈值
            apmClient.alert("gc.promote.high", "Promote > 10000/min");
        }
    }
}
```
