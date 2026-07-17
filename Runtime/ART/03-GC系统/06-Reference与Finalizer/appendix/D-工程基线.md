# 附录 D：工程基线（Reference 与 Finalizer）

## 一、关键参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `dalvik.vm.softrefthreshold` | 0.25 | 软引用阈值 |
| `MAX_FINALIZE_TIME_MS` | 10 秒 | finalize 超时 |
| `INTERVAL_MS` (Watchdog) | 1 秒 | 检查间隔 |
| `MAX_FINALIZE_COUNT` | 2 次 | 复活次数 |

## 二、监控指标

| 指标 | 正常 | 警告 | 严重 |
|:---|:---|:---|:---|
| finalize() 队列长度 | < 10 | 10-100 | > 100 |
| finalize() 执行时长 | < 1s | 1-10s | > 10s |
| Watchdog 警告频率 | 0 | > 5/h | > 30/h |
| DirectByteBuffer 数量 | < 100 | 100-500 | > 1000 |
| SoftReference 数量 | < 1000 | 1K-10K | > 10K |
| WeakReference 数量 | < 100 | 100-1K | > 10K |

## 三、业务代码建议

```
□ 1. 不使用 finalize()（除了特殊场景）
□ 2. native 资源用 Cleaner 释放
□ 3. Java 资源用 AutoCloseable + try-with-resources
□ 4. Cursor / Bitmap / FileDescriptor 主动关闭
□ 5. DirectByteBuffer 用对象池复用
□ 6. 监控 Watchdog 警告
□ 7. 定期扫描 finalize() 用法
```

## 四、APM 监控代码

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

## 五、治理方案

| 优先级 | 治理项 | 收益 |
|:---|:---|:---|
| **高** | 禁用 finalize() | 消除 Watchdog 警告 |
| **高** | 用 Cleaner 替代 finalize() | native 资源正确释放 |
| **中** | 用 AutoCloseable 替代手动 close | 资源管理统一 |
| **中** | DirectByteBuffer 对象池 | 减少 native 内存 |
| **低** | 监控 finalize() 队列 | 提前发现问题 |
