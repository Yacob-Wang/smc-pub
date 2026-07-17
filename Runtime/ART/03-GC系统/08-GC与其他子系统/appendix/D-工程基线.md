# 附录 D：工程基线（GC 与其他子系统）

## 一、JNI 工程原则

```
□ 1. Critical 区尽可能短（< 1ms）
□ 2. 不在 Critical 区内分配 Java 对象
□ 3. NewGlobalRef 必配对 DeleteGlobalRef
□ 4. 用 Smart Pointer 管理 Global Ref
□ 5. JNI Ref 数量监控（> 1000 警告）
```

## 二、Hook 工程原则

```
□ 1. ART 8+ 用 ReadBarrier::BarrierForRoot
□ 2. ART 字段修改用 WriteBarrier
□ 3. 升级 ART 时同步升级 Hook 框架
□ 4. 推荐 LSPosed / Frida 14+ / Whalebook
□ 5. 监控 ART Invariant 违反
```

## 三、System Server 监控

| 指标 | 监控方式 | 告警阈值 |
|:---|:---|:---|
| System Server 内存 | dumpsys meminfo | > 500 MB |
| System Server GC 频率 | ART Trace | > 30/分钟 |
| System Server OOM 风险 | 自定义监控 | > 95% 使用率 |

## 四、输入法 / SurfaceFlinger 优化

```
□ 1. Buffer Pool + Triple Buffering
□ 2. 缓存候选词 + LRU
□ 3. 监听 onTrimMemory
□ 4. 减少 Native 内存分配
□ 5. 用 Cleaner 替代 finalize
```
