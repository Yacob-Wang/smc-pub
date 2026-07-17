# 附录 D：工程基线

> **本附录是 02 篇的"工程基线"** —— 关键参数、监控指标、排查 checklist 的完整清单。
>
> **目的**：把本篇的知识点转化为可直接使用的工程工具。

---

## 一、关键可调参数基线

### 1.1 Heap 相关参数

| 参数 | 默认值 | 选用准则 | 踩坑提醒 |
|:---|:---|:---|:---|
| `dalvik.vm.heapgrowthlimit` | 256MB | 默认即可 | 误用 largeHeap 被 LMK 杀得更快 |
| `dalvik.vm.heapsize` | 512MB | 仅 `largeHeap=true` 生效 | 误用会让 GC 扫描更慢 |
| `dalvik.vm.heaptargetutilization` | 0.75 | 调小 → 堆更早收缩 | 太低会触发频繁 Trim |
| `dalvik.vm.heapminfree` | 2MB | 默认即可 | 影响堆扩展策略 |
| `dalvik.vm.heapmaxfree` | 8MB | 默认即可 | 影响堆收缩策略 |
| `dalvik.vm.softrefthreshold` | 0.25 | 调小 → SoftRef 保留更少 | 影响 Glide 缓存命中率 |
| `dalvik.vm.heap.region.size` | 256KB | ART 14+ 可调 | 影响 Minor GC 扫描 |
| `dalvik.vm.large-object-threshold` | 12KB | 默认即可 | 影响 LOS 划分 |

### 1.2 TLAB 相关参数

| 参数 | 默认值 | 选用准则 |
|:---|:---|:---|
| `TLAB::kTLABSize` (主线程) | 256KB | 主线程分配多 → 调大 |
| `TLAB::kTLABSize` (子线程) | 64KB | 子线程分配少 → 可调小 |
| `RosAlloc::kTLABSlotSize` | 16B-4KB | 按对象大小分桶 |

### 1.3 关键参数配置示例（custom.prop）

```properties
# 调优示例（仅供参考）
dalvik.vm.heapgrowthlimit=256m
dalvik.vm.heapsize=512m
dalvik.vm.heaptargetutilization=0.75
dalvik.vm.heapminfree=2m
dalvik.vm.heapmaxfree=8m
dalvik.vm.softrefthreshold=0.25

# ART 14+ 可选
dalvik.vm.heap.region.size=256k

# 激进 GC（适合低内存设备）
dalvik.vm.heaptargetutilization=0.6

# 保守 GC（适合高内存设备）
dalvik.vm.heaptargetutilization=0.85
```

---

## 二、监控指标基线

### 2.1 dumpsys meminfo 关键指标

| 指标 | 含义 | 正常范围 | 异常处理 |
|:---|:---|:---|:---|
| **Native Heap Size** | Native 堆总大小 | < 200MB | 检查 JNI / DirectByteBuffer |
| **Native Heap Alloc** | 已分配 Native 堆 | < Native Heap Size | 同上 |
| **Dalvik Heap Size** | Java 堆总大小 | < heapgrowthlimit | 检查 GC Root / 泄漏 |
| **Dalvik Heap Alloc** | 已分配 Java 堆 | < Dalvik Heap Size | 同上 |
| **Stack** | 线程栈 | < 5MB / thread | 检查线程数 |
| **Graphics** | 图形内存 | < 100MB | 检查 GL Texture |
| **Code** | 代码段 | < 100MB | 检查 DEX / OAT 大小 |
| **Other dev** | 其他设备 | < 20MB | — |
| **.so mmap** | .so 映射 | < 50MB | 检查 .so 泄漏 |
| **EGL mtrack** | EGL 内存追踪 | < 50MB | 检查 EGL 泄漏 |
| **GL mtrack** | GL 内存追踪 | < 50MB | 检查 GL Texture 泄漏 |
| **TOTAL** | 总计 | < 500MB（普通 App） | 综合判断 |

### 2.2 详细 dumpsys meminfo（-d 参数）

```bash
$ adb shell dumpsys meminfo -d <package>

# 输出示例（按 Pss 排序）
#   1: com.example.app (pid 12345)
#   2: Native Heap     12345     6789     1234      100    15000   102400    87654    14746
#   3: Dalvik Heap     45678    40000     5678      200    51234    65536    45678    19858
#   4:   Stack         1500     1400      100        0     1700
#   5:   Cursor          50       40       10        0       60
#   ...
#   6: .so mmap         8900     6000     2900        0    11000
#   ...
```

### 2.3 Heap 关键指标

| 指标 | 含义 | 正常范围 | 警戒线 |
|:---|:---|:---|:---|
| **Heap Alloc / Heap Size** | 堆使用率 | < 70% | > 85% 警告 |
| **Heap Alloc / max_allowed_footprint** | 占配额比例 | < 60% | > 80% 严重 |
| **GC 频率（次/分钟）** | GC 触发频率 | < 5 | > 30 严重 |
| **GC STW 时间（ms）** | STW 暂停时间 | < 5ms（CC/GenCC） | > 50ms 严重 |
| **GC_FOR_ALLOC 频率** | 同步 GC 频率 | < 1/分钟 | > 5/分钟 严重 |
| **TLAB 命中率** | TLAB 分配占比 | > 95% | < 80% 异常 |
| **LOS 占用率** | LOS 占用 / 总 Java 堆 | < 30% | > 50% 警告 |

---

## 三、Heap 排查 Checklist

### 3.1 OOM 排查 Checklist

```markdown
□ 1. 确认 OOM 类型
  □ 1.1 Java heap OOM？（dumpsys meminfo 看 Dalvik Heap Size）
  □ 1.2 Native heap OOM？（dumpsys meminfo 看 Native Heap）
  □ 1.3 Graphics OOM？（dumpsys meminfo 看 Graphics）
  □ 1.4 Thread/Stack OOM？（dumpsys meminfo 看 Stack）
  □ 1.5 FD/Thread OOM？（dumpsys meminfo 看 FD）

□ 2. Java heap OOM 排查
  □ 2.1 Heap Alloc 是否 ≈ Heap Size？
    ├─── 是 → 真实 OOM（堆用完）→ 检查泄漏
    └─── 否 → 看 LOS
  □ 2.2 生成 hprof
  □ 2.3 用 MAT / Shark 分析
  □ 2.4 找出最大的 LOS 对象（> 12KB）
  □ 2.5 检查 LOS 是否有碎片化
    ├─── 大量空洞 → LOS 碎片化 → 业务代码未 recycle() Bitmap
    └─── 无碎片 → 真实 OOM

□ 3. Native heap OOM 排查
  □ 3.1 检查 JNI Global Ref 数量
  □ 3.2 检查 DirectByteBuffer 数量
  □ 3.3 检查第三方 .so 的 mmap
  □ 3.4 检查 Bitmap 分配（是否复用）

□ 4. Graphics OOM 排查
  □ 4.1 检查 EGL mtrack
  □ 4.2 检查 GL mtrack
  □ 4.3 检查 Surface 泄漏

□ 5. 修复方案
  □ 5.1 Java heap OOM：
    - 修复泄漏（Activity / Fragment / Handler）
    - 启用 Bitmap 复用（inBitmap）
    - 分块大 Bitmap
    - 减小缓存大小
  □ 5.2 Native heap OOM：复用 DirectByteBuffer + 复用 Bitmap
  □ 5.3 Graphics OOM：复用 Surface + 减少 GL Texture
```

### 3.2 LOS 碎片化排查 Checklist

```markdown
□ 1. 抓取 hprof
  □ 1.1 adb shell am dumpheap <pid> /data/local/tmp/los.hprof
  □ 1.2 hprof-conv los.hprof los-conv.hprof

□ 2. 用 MAT 分析 LOS
  □ 2.1 Histogram → 过滤大小 > 12KB
  □ 2.2 找 Bitmap / byte[] / long[] 等大对象
  □ 2.3 按 retain size 排序
  □ 2.4 看 LOS 对象的 Retained Heap

□ 3. 判断是否碎片化
  □ 3.1 找 LOS 的空洞（free region）
  □ 3.2 看最大空洞大小
  □ 3.3 对比需要分配的对象大小
    ├─── 最大空洞 >= 需要 → 其他原因
    └─── 最大空洞 < 需要 → LOS 碎片化

□ 4. 检查业务代码
  □ 4.1 Bitmap 是否及时 recycle()？
  □ 4.2 大 byte[] 是否复用？
  □ 4.3 大对象是否分块？
  □ 4.4 Glide / Fresco 缓存大小是否合理？

□ 5. 修复方案
  □ 5.1 及时 recycle() Bitmap
  □ 5.2 使用 inBitmap 复用
  □ 5.3 分块大 Bitmap
  □ 5.4 主动管理 LOS（LRU 缓存）
```

### 3.3 慢速路径排查 Checklist

```markdown
□ 1. 抓取 systrace / Perfetto
  □ 1.1 抓取 trace 时长 ≥ 30 秒
  □ 1.2 包含 alloc 事件

□ 2. 分析分配路径
  □ 2.1 看 alloc 事件是 TLAB 还是 Slow Path
  □ 2.2 统计 TLAB 命中率
  □ 2.3 看 Region Pool 的使用情况

□ 3. 看 GC 日志
  □ 3.1 是否频繁触发 kGcCauseForAlloc？
  □ 3.2 GC STW 时间是否过长？
  □ 3.3 GC 后能否分配成功？

□ 4. 修复方案
  □ 4.1 减少对象分配（对象池 / 复用）
  □ 4.2 调整 TLAB 大小
  □ 4.3 调整 heaptargetutilization
  □ 4.4 考虑 largeHeap（如果真的需要）
```

---

## 四、Heap 监控代码示例

### 4.1 自建 APM 监控

```java
public class HeapMonitor {
    // 定时采样 Heap 状态
    @Scheduled(fixedRate = 30000)  // 30 秒
    public void sample() {
        Runtime runtime = Runtime.getRuntime();
        long totalMemory = runtime.totalMemory();
        long freeMemory = runtime.freeMemory();
        long usedMemory = totalMemory - freeMemory;
        long maxMemory = runtime.maxMemory();
        
        // 上报到 APM
        apmClient.report("heap.used", usedMemory / 1024 / 1024);  // MB
        apmClient.report("heap.total", totalMemory / 1024 / 1024);
        apmClient.report("heap.max", maxMemory / 1024 / 1024);
        apmClient.report("heap.usage", (double) usedMemory / totalMemory);
        
        // 告警
        if (usedMemory > maxMemory * 0.85) {
            apmClient.alert("heap.usage.high", "Heap usage > 85%");
        }
    }
    
    // 监听 GC 事件
    public void onGarbageCollectionFinish(long pauseTime) {
        apmClient.report("gc.pause", pauseTime);
        if (pauseTime > 50) {
            apmClient.alert("gc.pause.high", "GC pause > 50ms");
        }
    }
}
```

### 4.2 Debug API 使用

```java
// 获取 Java 堆详细信息
Debug.MemoryInfo memoryInfo = new Debug.MemoryInfo();
Debug.getMemoryInfo(memoryInfo);

// 关键字段
long dalvikPss = memoryInfo.dalvikPss;    // Dalvik PSS
long nativePss = memoryInfo.nativePss;    // Native PSS
long totalPss = memoryInfo.getTotalPss(); // 总 PSS

// 获取 Native 堆
long nativeHeapAlloc = Debug.getNativeHeapAllocatedSize();
long nativeHeapSize = Debug.getNativeHeapSize();

// 获取 Java 堆（粗粒度）
long javaHeapUsed = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
long javaHeapMax = Runtime.getRuntime().maxMemory();
```

### 4.3 dumpsys meminfo 解析脚本

```bash
#!/bin/bash
# parse_meminfo.sh - 解析 dumpsys meminfo 输出

PACKAGE=$1
if [ -z "$PACKAGE" ]; then
    echo "Usage: $0 <package>"
    exit 1
fi

echo "=== Heap 状态 ==="
adb shell dumpsys meminfo $PACKAGE | grep -E "Dalvik Heap|Native Heap|Graphics|TOTAL PSS"

echo ""
echo "=== Heap 详情 ==="
adb shell dumpsys meminfo -d $PACKAGE | head -30

echo ""
echo "=== GC 触发统计 ==="
adb logcat -d -s "art" | grep -E "kGcCauseForAlloc|kGcCauseBackground" | tail -20

echo ""
echo "=== LOS 大小 ==="
adb shell dumpsys meminfo $PACKAGE | grep -E "Heap.*Size|Heap.*Alloc|Heap.*Free"
```

---

## 五、APM 工具推荐

### 5.1 监控指标体系

| 指标类型 | 关键指标 | 采集频率 | 告警阈值 |
|:---|:---|:---|:---|
| **堆使用率** | `heap.used / heap.max` | 30s | > 85% |
| **Native 堆** | `native.used / native.max` | 30s | > 90% |
| **GC 频率** | `gc.count` | 1min | > 30/分钟 |
| **GC STW** | `gc.pause.avg` | 1min | > 50ms |
| **LOS 占用** | `los.size` | 1min | > 50MB |
| **Bitmap 数** | `bitmap.count` | 5min | > 100 |
| **Thread 数** | `thread.count` | 1min | > 500 |
| **JNI Ref** | `jni.global.ref` | 1min | > 1000 |

### 5.2 APM 工具对比

| 工具 | 平台 | Heap 监控 | 关键特性 |
|:---|:---|:---|:---|
| **LeakCanary** | Android | ✅ | 内存泄漏检测（开发） |
| **Matrix** | Android | ✅ | APM + GC 监控（生产） |
| **Firebase Performance** | 跨平台 | ✅ | 性能监控（海外） |
| **友盟 U-APM** | Android | ✅ | 崩溃 + 性能（国内） |
| **听云 App** | 跨平台 | ✅ | 真实用户体验 |
| **New Relic** | 跨平台 | ✅ | 全链路追踪 |
| **Sentry** | 跨平台 | ⚠️ | 崩溃监控为主 |

---

## 六、关键 KPI 基线

### 6.1 Heap 性能 KPI

| 指标 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|
| **Java 堆使用率** | < 50% | 50-70% | 70-85% | > 85% |
| **Native 堆使用率** | < 60% | 60-80% | 80-90% | > 90% |
| **总 PSS** | < 200MB | 200-400MB | 400-600MB | > 600MB |
| **内存增长率（24h）** | < 20% | 20-50% | 50-100% | > 100% |
| **GC 频率（次/分钟）** | < 2 | 2-5 | 5-10 | > 10 |
| **GC STW 时间（ms）** | < 1 | 1-5 | 5-50 | > 50 |
| **TLAB 命中率** | > 99% | 95-99% | 90-95% | < 90% |
| **LOS 占用率** | < 20% | 20-40% | 40-60% | > 60% |

### 6.2 Heap 配置推荐

| 场景 | `heapgrowthlimit` | `heapsize` | `largeHeap` | 备注 |
|:---|:---|:---|:---|:---|
| **普通 App** | 256MB | 512MB | false | 默认 |
| **图片编辑** | 256MB | 512MB | true | 处理大 Bitmap |
| **视频编辑** | 384MB | 768MB | true | 处理大视频帧 |
| **游戏** | 256MB | 512MB | 视情况 | 取决于资源大小 |
| **浏览器** | 384MB | 768MB | true | 多 Tab 内存需求 |
| **工具类** | 256MB | 512MB | false | 默认足够 |

---

## 七、关键工具链配置

### 7.1 开发环境配置

```groovy
// app/build.gradle
android {
    compileSdkVersion 34
    
    defaultConfig {
        // 大堆配置（仅当需要时）
        manifestPlaceholders = [largeHeap: "false"]
    }
    
    buildTypes {
        debug {
            debuggable true
            minifyEnabled false
        }
        release {
            minifyEnabled true
            shrinkResources true
        }
    }
}

dependencies {
    debugImplementation 'com.squareup.leakcanary:leakcanary-android:2.14'
    implementation 'com.tencent.matrix:matrix-android:2.0.0'
}
```

### 7.2 AndroidManifest.xml 关键配置

```xml
<application
    android:largeHeap="false"
    android:hardwareAccelerated="true"
    ...>
```

### 7.3 调试命令清单

```bash
# 1. 内存相关
adb shell dumpsys meminfo <package>
adb shell dumpsys meminfo -d <package>
adb shell procrank
adb shell run-as <package> cat /proc/self/smaps > smaps.txt

# 2. Heap 调试
adb shell am dumpheap <pid> /data/local/tmp/dump.hprof
adb pull /data/local/tmp/dump.hprof
hprof-conv dump.hprof dump-conv.hprof

# 3. 触发 GC
adb shell am gc

# 4. ART 调试
adb shell cmd activity dumpheap
adb shell cmd package compile -m verify <package>

# 5. Trace
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 10s sched freq idle am wm gfx view binder_driver hal dalvik

# 6. Thread
adb shell ps -T -p <pid>
adb shell kill -3 <pid>
```

---

## 八、Heap 配置的厂商适配

### 8.1 各厂商默认 Heap

| 厂商 | `heapgrowthlimit` | `heapsize` | `heaptargetutilization` |
|:---|:---|:---|:---|
| **Pixel** | 256 MB | 512 MB | 0.75 |
| **小米 MIUI** | 256 MB | 512 MB | 0.75 |
| **华为 EMUI** | 192 MB | 384 MB | 0.7 |
| **三星 OneUI** | 256 MB | 512 MB | 0.75 |
| **OPPO ColorOS** | 256 MB | 512 MB | 0.75 |
| **vivo OriginOS** | 256 MB | 512 MB | 0.75 |

### 8.2 适配建议

```java
// 运行时检测厂商，调整策略
if (isHuaweiEMUI()) {
    // 华为设备：Heap 较小，激进 GC
    setHeapUtilization(0.6);
    setBitmapCacheSize(MAX_HEAP / 4);
} else if (isXiaomiMIUI()) {
    // 小米设备：标准配置
    setHeapUtilization(0.75);
    setBitmapCacheSize(MAX_HEAP / 2);
}
```

---

## 九、附录小结

1. **关键参数基线**：Heap / TLAB / ART 内部参数完整
2. **监控指标基线**：dumpsys meminfo + Heap 关键指标
3. **排查 Checklist**：OOM / LOS 碎片化 / 慢速路径 三类问题
4. **APM 监控代码示例**：自建 Heap 监控
5. **关键 KPI 基线**：Heap 性能 + Heap 配置
6. **工具链配置**：开发环境 + 调试命令

→ **本附录是 02 篇的"工程工具箱"**——遇到任何 Heap 相关问题，都能在这里找到对应的工具和阈值。

---

## 十、后续篇目的工程基线

| 篇目 | 重点工程基线 |
|:---|:---|
| 03-CMS-GC | CMS 调优参数 + STW 优化 |
| 04-CC-GC | 读屏障优化 + 移动对象开销 |
| 05-Generational-CC | Minor GC 性能 + 分代假说验证 |
| 06-Reference与Finalizer | FinalizerDaemon 调优 + Cleaner 替代方案 |
| 07-GC调度与触发 | 9 种 GcCause 应对策略 |
| 08-GC与其他子系统 | GC × JNI / Hook / Zygote 横切调优 |
| 09-GC诊断与治理 | 完整工具链 + 监控体系搭建 |
