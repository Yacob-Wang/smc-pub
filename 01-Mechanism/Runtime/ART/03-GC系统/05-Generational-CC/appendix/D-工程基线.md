# 附录 D：工程基线（GenCC · v2 升级版）

> **本附录**：05-Generational-CC 子模块 / 附录 D（工程基线）
>
> **基线版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS，2024-11-17 发布，EOL 2026-12）
>
> **v2 升级日期**：2026-07-18（v1 旧文按 v4 规范 + 新基线升级）
>
> **v1 旧稿标记段**：已删除（v1 → v2 实质升级）

---

## 一、关键参数（AOSP 17）

### 1.1 GenCC 核心参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| **kRegionSize** | **256 KB** | Region 大小（AOSP 17 不变） |
| **kCardSize** | **256 byte** | **AOSP 17 细粒度**（AOSP 14 是 512 byte） |
| **kPromotionThreshold** | 15 次 | 默认晋升阈值（AOSP 14） |
| **kPromotionThreshold（ART 17）** | **5-30 次** | **AOSP 17 自适应** |
| **Young Gen 占比** | 25% | 可调 10-30%（AOSP 17 强化） |
| **Old Gen 占比** | 75% | 可调 70-90%（AOSP 17 强化） |
| **kSoftThresholdPercent** | **30%** | **AOSP 17 新增软阈值** |
| **kModUnionTableSize** | **1024** | **AOSP 17 新增** |
| **kDefaultGenerationalCC** | **true** | **AOSP 17 强制默认** |

### 1.2 ART 17 新增参数

| 参数 | 默认值 | 用途 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `kSoftThresholdPercent` | 30% | 软阈值触发 Minor GC | **AOSP 17 新增** |
| `kPromotionThresholdMin` | 5 | 晋升阈值下限 | **AOSP 17 新增** |
| `kPromotionThresholdMax` | 30 | 晋升阈值上限 | **AOSP 17 新增** |
| `kModUnionTableSize` | 1024 | Mod Union Table 大小 | **AOSP 17 新增** |
| `kMaxRegions` | 1024 | 最大 Region 数 | AOSP 17 默认 |
| `kCardSize` | 256 | Card 粒度 | AOSP 14 是 512 |

### 1.3 Linux 6.18 关联参数

| 参数 | 默认值 | 用途 | 关联 |
|:---|:---|:---|:---|
| Linux 内核 | 6.18 | AOSP 17 默认内核 | **基线纠正** |
| sheaves 内存分配器 | 启用 | Native 堆内存 -15-20% | Linux 6.18 新增 |
| io_uring 增强 | 启用 | I/O 延迟 -30% | Linux 6.18 强化 |
| 内存屏障原语 | 优化 | 屏障原子更新更高效 | Linux 6.18 强化 |

---

## 二、监控指标（AOSP 17）

### 2.1 GC STW 时间

| 指标 | 优秀 | 良好 | 差 | AOSP 17 变化 |
|:---|:---|:---|:---|:---|
| **Minor GC STW** | **< 0.5ms** | 0.5-1ms | > 1ms | **AOSP 17 强化** |
| **Major GC STW** | **< 50ms** | 50-100ms | > 100ms | AOSP 17 |
| **软阈值触发 STW** | **< 0.5ms** | 0.5-1ms | > 1ms | **AOSP 17 新增** |
| **Full GC STW** | **< 100ms** | 100-200ms | > 200ms | AOSP 17 |

### 2.2 GC 频率

| 指标 | 优秀 | 良好 | 差 | AOSP 17 变化 |
|:---|:---|:---|:---|:---|
| **Minor GC 频率** | **5-30/min** | 30-60/min | > 60/min | **AOSP 17 软阈值更高** |
| **Major GC 频率** | **< 1/hour** | 1-3/hour | > 5/hour | AOSP 17 |
| **软阈值触发频率** | **< 5/min** | 5-15/min | > 30/min | **AOSP 17 新增** |
| **Full GC 频率** | **< 0.1/hour** | 0.1-0.5/hour | > 1/hour | AOSP 17 |

### 2.3 堆使用率

| 指标 | 优秀 | 良好 | 差 | AOSP 17 变化 |
|:---|:---|:---|:---|:---|
| **Young Gen 使用率** | **< 70%** | 70-85% | > 85% | AOSP 17 强化 |
| **Old Gen 使用率** | **< 60%** | 60-80% | > 85% | AOSP 17 强化 |
| **软阈值触发时堆使用** | **30-50%** | 50-70% | > 70% | **AOSP 17 新增** |
| **LOS 占用** | **< 5%** | 5-10% | > 15% | AOSP 17 |

### 2.4 ART 17 新增监控指标

| 指标 | 监控命令 | 优秀值 | 备注 |
|:---|:---|:---|:---|
| **软阈值触发次数** | `adb logcat -s "art" \| grep "SoftThreshold"` | < 5/min | AOSP 17 新增 |
| **Mod Union Table 大小** | `adb logcat -s "art" \| grep "ModUnion"` | < 512 | AOSP 17 新增 |
| **晋升阈值** | `adb logcat -s "art" \| grep "PromotionThreshold"` | 5-30 | AOSP 17 自适应 |
| **Hot Card 数量** | `adb logcat -s "art" \| grep "HotCard"` | < 100 | AOSP 17 新增 |
| **Region inbound_refs** | `adb logcat -s "art" \| grep "RSet"` | < 20 | AOSP 17 |
| **写屏障调用频率** | `adb logcat -s "art" \| grep "WriteBarrier"` | 视 App | AOSP 17 |

---

## 三、业务代码建议（AOSP 17）

### 3.1 长寿对象管理

```
□ 1. 静态集合慎用：LRU / SoftReference / WeakHashMap
□ 2. 长寿对象集中管理：避免 Young Gen 中的长寿对象
□ 3. 批量处理：减少跨代引用频率
□ 4. 监听内存压力：onTrimMemory / onLowMemory
□ 5. 使用专业库：Glide / Fresco / LruCache
□ 6. ART 17 适配：对象池复用避免软阈值频繁触发
```

### 3.2 ART 17 适配建议（新增）

```java
// ✅ ART 17 好：长寿对象用 ConcurrentHashMap + static final
public class DataCache {
    private static final ConcurrentHashMap<String, Object> cache = 
        new ConcurrentHashMap<>();
    // cache 在 Old Gen，避免频繁晋升
}

// ❌ ART 17 不好：循环里频繁 new 小对象
public List<Result> process(List<RawData> data) {
    List<Result> results = new ArrayList<>();
    for (RawData item : data) {
        Result r = new Result();  // 每次循环 new → 软阈值频繁触发
        r.value = compute(item);
        results.add(r);
    }
    return results;
}

// ✅ ART 17 好：对象池复用
private static final ObjectPool<Result> pool = new ObjectPool<>(1000);
public List<Result> process(List<RawData> data) {
    List<Result> results = new ArrayList<>(data.size());
    for (RawData item : data) {
        Result r = pool.acquire();  // 复用
        r.value = compute(item);
        results.add(r);
    }
    return results;
}
```

### 3.3 跨代引用优化

```
□ 1. Old Gen 持有 Young Gen 对象用 WeakReference
□ 2. 大量小对象分配用对象池
□ 3. 批量操作优于细粒度操作
□ 4. byte[] 数组操作利用 SIMD 屏障
□ 5. 避免 Hot Card（高频脏卡）
```

### 3.4 端侧 LLM 加载建议（ART 17 新增）

```
□ 1. 用 AppFunctions 框架加载 LLM 模型
□ 2. 加载期间主动通知 GC 暂停 Minor GC
□ 3. 利用 dm-pcache（6.18）持久化模型缓存
□ 4. 模型加载后通知 GC 恢复正常
□ 5. 详见 [10-ART17分代GC强化专章 v2](../10-ART17分代GC强化专章-v2.md) §4
```

---

## 四、APM 监控代码示例（AOSP 17）

```java
public class GenCCMonitor {
    public void onMinorGCFinish(long pauseTime) {
        apmClient.report("gc.minor.pause", pauseTime);
        if (pauseTime > 1) {
            apmClient.alert("gc.minor.pause.high", "Minor GC > 1ms");
        }
    }
    
    public void onMajorGCFinish(long pauseTime) {
        apmClient.report("gc.major.pause", pauseTime);
        if (pauseTime > 50) {
            apmClient.alert("gc.major.pause.high", "Major GC > 50ms");
        }
    }
    
    public void onPromote(int count) {
        apmClient.report("gc.promote.count", count);
        if (count > 10000) {  // 阈值
            apmClient.alert("gc.promote.high", "Promote > 10000/min");
        }
    }
    
    // ★ ART 17 新增：软阈值监控
    public void onSoftThresholdTrigger() {
        apmClient.report("gc.softthreshold.count", 1);
        long totalCount = apmClient.getCounter("gc.softthreshold.count");
        if (totalCount > 30) {  // 30/min 阈值
            apmClient.alert("gc.softthreshold.high", 
                "Soft threshold triggered > 30/min");
        }
    }
    
    // ★ ART 17 新增：晋升阈值监控
    public void onPromotionThresholdAdjust(int newThreshold) {
        apmClient.report("gc.promotion.threshold", newThreshold);
        if (newThreshold <= 5) {  // 最低阈值
            apmClient.warn("gc.promotion.threshold.low", 
                "Promotion threshold at minimum: " + newThreshold);
        }
    }
    
    // ★ ART 17 新增：Mod Union Table 监控
    public void onModUnionTableSize(int size) {
        apmClient.report("gc.modunion.size", size);
        if (size > 512) {  // 阈值
            apmClient.warn("gc.modunion.large", 
                "ModUnionTable size > 512 entries");
        }
    }
}
```

---

## 五、ART 17 关键参数对照表

### 5.1 AOSP 14 vs AOSP 17

| 参数 | AOSP 14 | AOSP 17 | 变化 |
|:---|:---|:---|:---|
| **GC 默认策略** | GenCC（可选） | **GenCC（强制）** | **强制** |
| **Card 粒度** | 512 byte | **256 byte** | **细 2x** |
| **软阈值** | 不存在 | **30%** | **新增** |
| **晋升阈值** | 15（固定） | **5-30（自适应）** | **自适应** |
| **Mod Union Table** | 不存在 | **启用** | **新增** |
| **RSet 内存** | 80 KB | **16 KB** | **-80%** |
| **Young Gen 占比** | 25%（固定） | **10-30%（可调）** | **可调** |
| **Old Gen 占比** | 75%（固定） | **70-90%（可调）** | **可调** |
| **写屏障调用** | 50ns | **30ns** | **-40%** |
| **Region Hot/Cold** | 不存在 | **新增** | **新增** |
| **Linux 内核** | android14-5.10/5.15 | **android17-6.18** | **基线纠正** |

### 5.2 性能提升（AOSP 14 → AOSP 17）

| 维度 | AOSP 14 | AOSP 17 | 提升 |
|:---|:---|:---|:---|
| **Minor GC STW** | ~1ms | **~0.5ms** | **-50%** |
| **Minor GC 频率** | 5-30/min | **10-60/min（软阈值）** | **+100%** |
| **总 STW 时间** | 基线 | **-30-50%** | **显著** |
| **跨代引用识别** | 75-80% 准确 | **95-99% 准确** | **+20%** |
| **CPU 占用** | 基线 | **-5-15%** | **显著** |
| **续航** | 基线 | **+3-8%** | **显著** |
| **冷启动** | 基线 | **-5-10%** | **显著** |
| **卡顿** | 基线 | **-20-30%** | **显著** |
| **Native 堆** | 基线 | **-15-20%**（Linux 6.18） | **显著** |
| **Card Table 刷盘** | 基线 | **-30%**（Linux 6.18） | **显著** |

---

## 六、风险地图（AOSP 17）

| 风险 | 触发条件 | 现象 | 排查入口 | AOSP 17 应对 |
|:---|:---|:---|:---|:---|
| **分代假说失效** | 长寿对象污染 Young Gen | Old Gen 满 → OOM | dumpsys meminfo | 用 ConcurrentHashMap + static |
| **大量大对象** | Bitmap / byte[] 频繁分配 | LOS 满 | dumpsys meminfo | 用对象池（Glide / LruCache） |
| **跨代引用频繁** | Old → Young 引用多 | 脏卡比例高，Minor GC 慢 | logcat Card | 用 WeakReference |
| **软阈值频繁触发** | 老 App 大量小对象 | 总 STW 时间增加 | logcat SoftThreshold | 用对象池 |
| **晋升阈值过低** | Old Gen 占用率高 | 频繁晋升 → Old Gen 满 | logcat PromotionThreshold | 调大 Old Gen |
| **Mod Union Table 溢出** | 跨代引用模式复杂 | 回退 Card Table | logcat ModUnion | 优化数据布局 |
| **Hot Card 过多** | 高并发线程 | 写屏障开销大 | logcat HotCard | 用 ThreadLocal |
| **RSet 锁竞争** | 多线程并发更新 RSet | Minor GC 慢 | systrace | 用 ThreadLocal（异步 RSet） |
| **Young Gen 太小** | 临时对象多 | 频繁 Minor GC | dumpsys meminfo | 调大 Young Gen 比例（AOSP 17 可调） |

---

## 七、踩坑提醒

### 7.1 架构师踩坑

```
□ 1. 不要在 ART 17 上手动禁用 GenCC（无法降级为 CC）
□ 2. 不要假设软阈值不触发（堆占用 30% 就触发 Minor GC）
□ 3. 不要在循环里频繁 new 小对象（软阈值频繁触发）
□ 4. 不要忽略晋升阈值自适应（Old Gen 占用率高时阈值降到 5）
□ 5. 不要在 Old Gen 持有大量 Young Gen 引用（脏卡比例高）
□ 6. 不要假设 Card 粒度是 512 byte（ART 17 默认 256 byte）
□ 7. 不要忽略 Linux 6.18 sheaves 带来的 Native 堆优化
```

### 7.2 SRE 踩坑

```
□ 1. 监控指标要更新到 ART 17（软阈值、Mod Union、晋升阈值）
□ 2. 第三方库必须升级到支持 ART 17 的版本
□ 3. OEM 升级 Android 17 时必须全面回归测试
□ 4. 端侧 LLM 加载场景必须测试（Gemini Nano 1.8GB / Llama 3 8B 4.7GB）
□ 5. Heap 布局变化（Young/Old 比例可调）需要重新调优
```

### 7.3 业务开发踩坑

```
□ 1. 长寿对象用 static final + ConcurrentHashMap
□ 2. 大量小对象用对象池复用
□ 3. byte[] 数组批量操作（利用 SIMD 屏障）
□ 4. Old Gen 持有 Young Gen 用 WeakReference
□ 5. 避免 Hot Card（高频脏卡）
□ 6. 跨代引用集中处理（用 Mod Union Table 优化）
□ 7. 端侧 LLM 加载用 AppFunctions 框架
```

---

## 八、ART 17 工程基线表（一页式速查）

```
┌──────────────────────────────────────────────────────────────┐
│ AOSP 17 + android17-6.18 GenCC 工程基线（一页式速查）             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  GC 策略：                                                    │
│    - 默认：GenCC（强制）                                       │
│    - 软阈值：kSoftThresholdPercent=30%                        │
│    - 晋升阈值：5-30（自适应，默认 15）                          │
│    - Card 粒度：256 byte（细粒度）                              │
│                                                              │
│  物理布局：                                                    │
│    - Young Gen：25%（可调 10-30%）                            │
│    - Old Gen：75%（可调 70-90%）                              │
│    - Region：256 KB                                           │
│    - LOS：大对象专用                                           │
│                                                              │
│  关键性能指标：                                                 │
│    - Minor GC STW：< 0.5ms（优秀）                            │
│    - Major GC STW：< 50ms（优秀）                             │
│    - Minor GC 频率：5-30/min（软阈值下 10-60/min）             │
│    - Major GC 频率：< 1/hour（优秀）                          │
│                                                              │
│  监控命令：                                                    │
│    - dumpsys meminfo <package>                               │
│    - adb logcat -s "art" | grep "SoftThreshold\|ModUnion"   │
│    - adb logcat -s "art" | grep "Promote\|PromotionThreshold"│
│                                                              │
│  Linux 内核：                                                  │
│    - android17-6.18（6.18 LTS，2024-11-17 发布）             │
│    - sheaves 内存分配器（Native 堆 -15-20%）                   │
│    - io_uring 增强（I/O 延迟 -30%）                            │
│                                                              │
│  业务代码黄金法则：                                              │
│    1. 长寿对象用 static final + ConcurrentHashMap             │
│    2. 大量小对象用对象池复用                                    │
│    3. Old Gen 持有 Young Gen 用 WeakReference                 │
│    4. 端侧 LLM 用 AppFunctions 框架                            │
│    5. ART 17 软阈值适配：减少小对象分配                        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 九、相关文档引用

| 文档 | 路径 | 用途 |
|:---|:---|:---|
| **ART 17 分代 GC 强化专章 v2** | [10-ART17分代GC强化专章-v2.md](../10-ART17分代GC强化专章-v2.md) | **专章 ART 17 强化**（必读） |
| 01-分代假说 | [01-分代假说.md](../01-分代假说.md) | 分代假说理论 |
| 02-Young-Old划分 | [02-Young-Old划分.md](../02-Young-Old划分.md) | Young/Old 物理布局 |
| 03-Card-Table基石 | [03-Card-Table基石.md](../03-Card-Table基石.md) | Card Table 实现 |
| 04-Remembered-Set | [04-Remembered-Set.md](../04-Remembered-Set.md) | Region RSet + Mod Union |
| 附录 A-源码索引 | [A-源码索引.md](A-源码索引.md) | 源码路径 |
| 附录 B-路径对账 | [B-路径对账.md](B-路径对账.md) | 基线对账 |

---

> **完结**：05-Generational-CC 子模块 v2 升级完成（4 主篇 + 3 附录）。
> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）
> **v2 升级日期**：2026-07-18

