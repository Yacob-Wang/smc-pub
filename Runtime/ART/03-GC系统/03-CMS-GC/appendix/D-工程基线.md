# 附录 D：工程基线

> **本附录是 03 篇的"工程基线"** —— CMS 时代（Android 5-7）的关键参数、监控指标、排查 checklist 的完整清单。

---

## 一、关键可调参数基线

### 1.1 CMS 相关参数

| 参数 | 默认值 | 选用准则 | 踩坑提醒 |
|:---|:---|:---|:---|
| `dalvik.vm.gctype` | CMS（5-7） | Android 5-7 用 CMS | 8.0+ 改用 CC / GenCC |
| `dalvik.vm.heapgrowthlimit` | 256MB | 默认即可 | 误用 `largeHeap` 被 LMK 杀得更快 |
| `dalvik.vm.heapsize` | 512MB | 仅 `largeHeap=true` 生效 | 误用会让 GC 扫描更慢 |
| `dalvik.vm.heaptargetutilization` | 0.75 | 调小 → 更激进 GC | 太低会触发频繁 Trim |
| `dalvik.vm.softrefthreshold` | 0.25 | 调小 → SoftRef 保留更少 | 影响 Glide 缓存命中率 |
| `dalvik.vm.large-object-threshold` | 12KB | 默认即可 | 调小 → 更多对象进 LOS |
| `dalvik.vm.dex2oat-Xms` | 64m | 默认即可 | 影响 dex2oat 启动速度 |
| `dalvik.vm.dex2oat-Xmx` | 512m | 默认即可 | 影响 dex2oat 最大内存 |

### 1.2 CMS 内部参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `RosAlloc::kNumOfSizeBrackets` | 36 | size class 数量 |
| `RosAlloc::kMaxSizeBracketSize` | 4096 | 最大 size class |
| `RosAlloc::kLargeObjectThreshold` | 12 KB | 大对象阈值 |
| `MarkBitmap::kAlignment` | 8 字节 | 对象对齐 |
| `TLAB::kTLABSize` (主线程) | 256 KB | 主线程 TLAB |
| `TLAB::kTLABSize` (子线程) | 64 KB | 子线程 TLAB |

### 1.3 关键参数配置示例

```properties
# CMS 调优示例（仅供参考）
dalvik.vm.gctype=CMS
dalvik.vm.heapgrowthlimit=256m
dalvik.vm.heapsize=512m
dalvik.vm.heaptargetutilization=0.75
dalvik.vm.softrefthreshold=0.25

# 激进 GC（适合低内存设备）
dalvik.vm.heaptargetutilization=0.6

# 保守 GC（适合高内存设备）
dalvik.vm.heaptargetutilization=0.85

# 激进软引用回收（适合图片 App）
dalvik.vm.softrefthreshold=0.15
```

---

## 二、监控指标基线

### 2.1 CMS 4 阶段耗时指标

| 阶段 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|
| **Initial Mark** | < 3ms | 3-5ms | 5-10ms | > 10ms |
| **Concurrent Mark** | < 100ms | 100-200ms | 200-500ms | > 500ms |
| **Remark** | < 10ms | 10-30ms | 30-100ms | > 100ms |
| **Concurrent Sweep** | < 100ms | 100-200ms | 200-500ms | > 500ms |
| **总 STW** | < 15ms | 15-50ms | 50-150ms | > 150ms |

### 2.2 GC 频率指标

| 指标 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|
| **Background GC 频率** | < 1/分钟 | 1-3/分钟 | 3-10/分钟 | > 10/分钟 |
| **kGcCauseForAlloc GC 频率** | < 1/分钟 | 1-3/分钟 | 3-10/分钟 | > 10/分钟 |
| **总 GC 频率** | < 5/分钟 | 5-15/分钟 | 15-30/分钟 | > 30/分钟 |

### 2.3 内存使用指标

| 指标 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|
| **Heap Alloc / Heap Size** | < 50% | 50-70% | 70-85% | > 85% |
| **Heap Alloc / max_allowed_footprint** | < 60% | 60-80% | 80-90% | > 90% |
| **LOS 占用率** | < 20% | 20-40% | 40-60% | > 60% |
| **GC 释放字节数** | > 0 | = 0 | < 0 | < 0（碎片化） |

### 2.4 写屏障指标

| 指标 | 正常范围 | 异常处理 |
|:---|:---|:---|
| **写屏障次数/秒** | < 100 万/秒 | > 100 万 异常 |
| **写屏障总耗时** | < 10ms/秒 | > 50ms 异常 |
| **写屏障占比** | < 5% | > 10% 异常 |

### 2.5 Reference 指标

| 指标 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|
| **SoftReference 数** | < 1K | 1K-10K | 10K-100K | > 100K |
| **WeakReference 数** | < 100 | 100-1K | 1K-10K | > 10K |
| **FinalReference 数** | < 100 | 100-500 | 500-1K | > 1K |
| **PhantomReference 数** | < 10 | 10-100 | 100-1K | > 1K |

### 2.6 ART Trace 关键字段

```bash
# ART Trace 中 CMS 关键事件
art : Background concurrent copying GC freed 1048576(13MB) AllocSpace objects
art : Concurrent Mark took 102.3ms
art : Remark took 50.4ms
art : Concurrent Sweep took 98.7ms
art : 0(0B) LOS objects
art : 50% free, 13MB/26MB
art : paused 1.234ms total 50.5ms  ← STW 时间
```

---

## 三、CMS 时代 OOM 排查 Checklist

### 3.1 OOM 排查总 Checklist

```markdown
□ 1. 确认 OOM 类型
  □ 1.1 Java heap OOM？（dumpsys meminfo 看 Dalvik Heap）
  □ 1.2 Native heap OOM？（dumpsys meminfo 看 Native Heap）
  □ 1.3 Graphics OOM？（dumpsys meminfo 看 Graphics）

□ 2. Java heap OOM 排查
  □ 2.1 Heap Alloc 是否 ≈ Heap Size？
    ├─── 是 → 真实 OOM（堆用完）→ 检查泄漏
    └─── 否 → 可能是碎片化
  □ 2.2 生成 hprof
  □ 2.3 用 MAT / Shark 分析
  □ 2.4 找出最大的 LOS 对象（> 12KB）
  □ 2.5 检查 LOS 是否有碎片化
  □ 2.6 检查 Allocation Space 的 size class 分布

□ 3. 5 大 OOM 模式分类
  □ 3.1 真实 OOM（堆用完）→ 修复泄漏
  □ 3.2 LOS 碎片化 → Bitmap 严格管理
  □ 3.3 Allocation Space 碎片化 → 减少对象创建
  □ 3.4 GC 失败 → 优化 GC 触发
  □ 3.5 混合 OOM → 综合优化

□ 4. 修复方案
  □ 4.1 升级到 CC GC（最有效）
  □ 4.2 业务层综合优化
  □ 4.3 Heap 参数调优
```

### 3.2 LOS 碎片化排查 Checklist

```markdown
□ 1. 抓取 hprof
  □ 1.1 adb shell am dumpheap <pid> /data/local/tmp/los.hprof
  □ 1.2 hprof-conv los.hprof los-conv.hprof

□ 2. 用 MAT 分析 LOS
  □ 2.1 Histogram → 过滤 size > 12KB
  □ 2.2 找 Bitmap / byte[] / long[] 等大对象
  □ 2.3 按 retain size 排序
  □ 2.4 看 LOS 对象的 Retained Heap

□ 3. 判断是否碎片化
  □ 3.1 找 LOS 的空洞（free region）
  □ 3.2 看最大空洞大小
  □ 3.3 对比需要分配的对象大小

□ 4. 修复方案
  □ 4.1 及时 recycle() Bitmap
  □ 4.2 使用 inBitmap 复用
  □ 4.3 分块大 Bitmap
  □ 4.4 LRU 缓存 Bitmap
```

### 3.3 Remark STW 优化 Checklist

```markdown
□ 1. 监控 Remark STW
  □ 1.1 ART Trace 看 Remark 耗时
  □ 1.2 找出 Remark > 50ms 的 GC 事件

□ 2. 分析 dirty 对象来源
  □ 2.1 看业务线程在 Concurrent Mark 期间的行为
  □ 2.2 找出高频创建对象的代码
  □ 2.3 找出高频修改引用的代码

□ 3. 优化策略
  □ 3.1 减少 Concurrent Mark 期间的对象创建
  □ 3.2 复用对象（StringBuilder / Buffer）
  □ 3.3 使用对象池
  □ 3.4 控制堆大小（256MB 是推荐值）

□ 4. 终极解决方案
  □ 4.1 升级到 Android 8.0+ CC GC
  □ 4.2 STW 从 50ms+ 降到 < 1ms
```

---

## 四、APM 监控代码示例

### 4.1 GC 监控

```java
public class CMSMonitor {
    // JVMTI 回调
    public void onGarbageCollectionStart() {
        gcStartTime = System.nanoTime();
    }
    
    public void onGarbageCollectionFinish(String cause) {
        long pauseTime = (System.nanoTime() - gcStartTime) / 1_000_000;
        
        // 上报 STW 时间
        apmClient.report("gc.pause", pauseTime);
        apmClient.report("gc.cause", cause);
        
        // 区分阶段
        if ("Concurrent Mark".equals(cause)) {
            apmClient.report("gc.concurrent_mark.pause", pauseTime);
        } else if ("Remark".equals(cause)) {
            apmClient.report("gc.remark.pause", pauseTime);
        }
        
        // 告警
        if (pauseTime > 50) {
            apmClient.alert("gc.pause.high", "GC pause > 50ms: " + pauseTime);
        }
    }
}
```

### 4.2 OOM 监控

```java
public class OOMMonitor {
    public void onOutOfMemoryError(OutOfMemoryError e) {
        // 上报 OOM 事件
        Map<String, Object> context = new HashMap<>();
        context.put("heap_alloc", getHeapAlloc());
        context.put("heap_size", getHeapSize());
        context.put("max_heap", getMaxHeap());
        context.put("los_used", getLOSUsed());
        context.put("thread_count", getThreadCount());
        
        apmClient.report("oom.event", e.getMessage(), context);
        
        // 触发 heap dump
        triggerHeapDump();
        
        // 主动 GC（不一定有效，但值得一试）
        System.gc();
    }
}
```

### 4.3 Fragmentation 监控

```java
public class FragmentationMonitor {
    @Scheduled(fixedRate = 60000)
    public void monitor() {
        Runtime runtime = Runtime.getRuntime();
        long total = runtime.totalMemory();
        long free = runtime.freeMemory();
        long used = total - free;
        long max = runtime.maxMemory();
        
        // 碎片化指标
        double fragRatio = (double) free / total;  // 空闲率
        double usageRatio = (double) used / total; // 使用率
        
        apmClient.report("heap.usage.ratio", usageRatio);
        apmClient.report("heap.free.ratio", fragRatio);
        
        // 告警
        if (usageRatio > 0.85 && fragRatio > 0.3) {
            apmClient.alert("heap.fragmented", "Heap > 85% used with > 30% free");
        }
    }
}
```

---

## 五、CMS 时代的工具链

### 5.1 开发期工具

| 工具 | 用途 |
|:---|:---|
| LeakCanary | 内存泄漏检测 |
| Android Studio Memory Profiler | 实时内存监控 |
| StrictMode | 严格模式（debug 开启） |
| Layout Inspector | UI 层级检查 |

### 5.2 测试期工具

| 工具 | 用途 |
|:---|:---|
| dumpsys meminfo | 内存信息 |
| procrank | 进程排名 |
| smaps | VMA 详情 |
| Perfetto | trace 分析 |

### 5.3 生产期工具

| 工具 | 用途 |
|:---|:---|
| Matrix | APM（推荐） |
| Firebase Performance | 性能监控（海外） |
| 友盟 U-APM | 性能监控（国内） |
| 自建监控 | 自定义告警 |

### 5.4 调试命令清单

```bash
# 1. 内存相关
adb shell dumpsys meminfo <package>
adb shell dumpsys meminfo -d <package>
adb shell procrank
adb shell run-as <package> cat /proc/self/smaps

# 2. GC 相关
adb logcat -s "art" | grep "GC"
adb shell setprop dalvik.vm.image-dex2oat-flags --debug
adb shell setprop dalvik.vm.gctype CMS

# 3. Heap 转储
adb shell am dumpheap <pid> /data/local/tmp/dump.hprof
adb pull /data/local/tmp/dump.hprof
hprof-conv dump.hprof dump-conv.hprof

# 4. Trace
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 30s sched freq idle am wm gfx view binder_driver hal dalvik

# 5. Thread
adb shell ps -T -p <pid>
adb shell kill -3 <pid>

# 6. Native crash
adb shell logcat -d -b crash
adb shell ls /data/tombstones/
```

---

## 六、CMS 时代的关键 KPI

### 6.1 性能 KPI

| 指标 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|
| **Java 堆使用率** | < 50% | 50-70% | 70-85% | > 85% |
| **Native 堆使用率** | < 60% | 60-80% | 80-90% | > 90% |
| **总 PSS** | < 200MB | 200-400MB | 400-600MB | > 600MB |
| **GC 频率** | < 5/分钟 | 5-15/分钟 | 15-30/分钟 | > 30/分钟 |
| **GC STW 时间** | < 15ms | 15-50ms | 50-150ms | > 150ms |
| **Remark STW** | < 10ms | 10-30ms | 30-100ms | > 100ms |
| **LOS 占用率** | < 20% | 20-40% | 40-60% | > 60% |
| **写屏障开销** | < 5% | 5-10% | 10-20% | > 20% |

### 6.2 业务 KPI

| 指标 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|
| **冷启动时间** | < 1s | 1-2s | 2-3s | > 3s |
| **滑动 FPS** | 60 fps | 50-60 fps | 30-50 fps | < 30 fps |
| **卡顿率** | < 1% | 1-3% | 3-10% | > 10% |
| **OOM 崩溃率** | 0 | < 0.1% | 0.1-1% | > 1% |
| **Bitmap 数量** | < 50 | 50-200 | 200-500 | > 500 |

---

## 七、CMS 时代的稳定性策略

### 7.1 升级到 CC GC（最有效）

```xml
<!-- Android 8.0+ 自动使用 CC GC -->
<uses-sdk android:targetSdkVersion="26" />

<!-- 或显式指定 -->
<application>
    <!-- 系统自动选择 CC GC -->
</application>
```

**升级效果**：
- STW 从 50ms+ 降到 < 1ms
- 碎片化自动修复（Allocation Space）
- 写屏障变读屏障（更高效）

### 7.2 业务层优化

```java
// 1. Bitmap 严格管理
public class BitmapManager {
    public void releaseBitmap(Bitmap bitmap) {
        if (bitmap != null && !bitmap.isRecycled()) {
            bitmap.recycle();
        }
    }
}

// 2. LRU 缓存
private LruCache<String, Bitmap> cache = new LruCache<>(MAX_SIZE);

// 3. 对象池
public class ObjectPool<T> {
    private Stack<T> pool = new Stack<>();
    
    public T acquire() {
        return pool.isEmpty() ? create() : pool.pop();
    }
    
    public void release(T obj) {
        pool.push(obj);
    }
}

// 4. 避免内存泄漏
// Application Context 替代 Activity Context
// WeakReference 替代强引用
// 在 onDestroy 中清理
```

### 7.3 Heap 参数调优

```bash
# 调高 heaptargetutilization → 更激进 GC
adb shell setprop dalvik.vm.heaptargetutilization 0.6

# 调大 softrefthreshold → 软引用更早释放
adb shell setprop dalvik.vm.softrefthreshold 0.15

# 减小堆大小 → CMS 扫描范围小
adb shell setprop dalvik.vm.heapgrowthlimit 192m
```

---

## 八、关键监控告警配置

### 8.1 关键告警指标

```java
public class GCAlertConfig {
    // CMS Remark STW > 50ms 告警
    @Alert(threshold = 50, severity = "high")
    private long gcRemarkPause;
    
    // GC 频率 > 30/分钟 告警
    @Alert(threshold = 30, severity = "medium")
    private int gcFrequency;
    
    // Heap 使用率 > 85% 告警
    @Alert(threshold = 0.85, severity = "high")
    private double heapUsage;
    
    // LOS 占用 > 50MB 告警
    @Alert(threshold = 50 * 1024 * 1024, severity = "medium")
    private long losUsage;
    
    // OOM 发生告警
    @Alert(threshold = 1, severity = "critical")
    private int oomCount;
}
```

### 8.2 告警分级处理

| 告警级别 | 触发条件 | 处理方式 |
|:---|:---|:---|
| **Info** | GC 频率 > 15/分钟 | 优化提醒 |
| **Warning** | GC Remark > 30ms | 性能优化 |
| **Error** | GC Remark > 50ms | 紧急优化 |
| **Critical** | OOM 发生 | 立即处理 |

---

## 九、附录小结

1. **关键参数基线**：CMS / Heap / ART 内部参数完整
2. **监控指标基线**：4 阶段 / GC 频率 / 内存使用 / 写屏障 / Reference
3. **排查 Checklist**：OOM / LOS 碎片化 / Remark STW 三类问题
4. **APM 监控代码示例**：GC / OOM / Fragmentation 监控
5. **CMS 时代工具链**：开发期 / 测试期 / 生产期
6. **关键 KPI**：性能 + 业务
7. **稳定性策略**：升级 CC GC / 业务优化 / 参数调优
8. **告警配置**：分级处理

→ **本附录是 03 篇的"工程工具箱"**——遇到任何 CMS 相关问题，都能在这里找到对应的工具和阈值。

---

## 十、后续篇目的工程基线

| 篇目 | 重点工程基线 |
|:---|:---|
| 04-CC-GC | 读屏障优化 + 移动对象开销 + 切换到-space |
| 05-Generational-CC | Minor GC 性能 + 分代假说验证 + Card Table |
| 06-Reference与Finalizer | FinalizerDaemon 调优 + Cleaner 替代方案 |
| 07-GC调度与触发 | 9 种 GcCause 应对策略 + HeapTaskDaemon |
| 08-GC与其他子系统 | GC × JNI / Hook / Zygote 横切调优 |
| 09-GC诊断与治理 | 完整工具链 + 监控体系搭建 |
