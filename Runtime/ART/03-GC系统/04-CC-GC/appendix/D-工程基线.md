# 附录 D：工程基线（CC GC）

## 一、关键参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `RegionSize` | 256 KB | 可通过 dalvik.vm.heap.region.size 调整 |
| `kGrayStatusImmuneWord` | 0xFEEDDEAD | Gray 状态对象标记 |
| 读屏障开销 | ~3ns (rbcc) | 自愈后 |

## 二、监控指标

| 指标 | 优秀 | 良好 | 差 |
|:---|:---|:---|:---|
| Initialize STW | < 2ms | 2-5ms | > 10ms |
| Copying 时间 | < 100ms | 100-300ms | > 500ms |
| Reclaim STW | < 1ms | 1-3ms | > 5ms |
| 总 STW | < 5ms | 5-10ms | > 20ms |
| 读屏障开销占比 | < 3% | 3-8% | > 15% |

## 三、Hook 兼容性 checklist

```
□ 1. 所有 ArtMethod 访问用 ReadBarrier::BarrierForRoot
□ 2. 所有字段修改用 WriteBarrier::WriteField
□ 3. JNI 用接口，不用直接内存访问
□ 4. 业务代码不缓存 Java 对象（用 WeakReference）
□ 5. Hook 框架升级到适配 ART 8+ 的版本
□ 6. 启用 ART Debug 模式监控 Invariant 违反
```

## 四、APM 监控

```java
public class CCGCMonitor {
    public void onGarbageCollectionFinish(long pauseTime, String phase) {
        apmClient.report("gc.cc.pause." + phase, pauseTime);
        if (pauseTime > 10) {
            apmClient.alert("gc.cc.pause.high", "CC GC pause > 10ms: " + pauseTime);
        }
    }
}
```

## 五、CC GC 时代的稳定性策略

| 策略 | 说明 |
|:---|:---|
| 升级到 ART 8.0+ | STW < 5ms |
| Hook 框架升级 | 适配读屏障 |
| LOS Bitmap 管理 | 仍需 recycle |
| 读屏障 hot path 优化 | ART 14+ rbcc |
