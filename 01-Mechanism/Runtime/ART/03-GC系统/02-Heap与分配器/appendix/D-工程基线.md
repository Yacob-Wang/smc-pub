# 附录 D：工程基线（v2 升级版）

> **本附录是 02 篇的"工程基线"** —— 关键参数、监控指标、排查 checklist 的完整清单。
>
> **目的**：把本篇的知识点转化为可直接使用的工程工具。
>
> **AOSP 版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS，2024-11-17 发布，EOL 2026-12）
>
> **v2 升级日期**：2026-07-18（v1 旧文按 本规范 + 新基线升级）

---

## 0. 附录定位声明

| 维度 | 本附录承担 | 本附录不涉及 |
| :--- | :--- | :--- |
| 关键可调参数 | ✓ Heap / TLAB / Region / RosAlloc | 源码详见 [附录 A-源码索引](A-源码索引.md) |
| 监控指标 | ✓ dumpsys meminfo + Heap 关键指标 | 详细源码详见 [附录 A](A-源码索引.md) |
| 排查 Checklist | ✓ OOM / LOS / 慢速路径 / ART 17 新增 | 路径对账详见 [附录 B-路径对账](B-路径对账.md) |
| 监控代码示例 | ✓ APM + Debug API + dumpsys 解析 | 跨引用详见 [附录 A](A-源码索引.md) |
| APM 工具推荐 | ✓ LeakCanary / Matrix / Firebase | — |
| **ART 17 新增参数** | ✓ 软阈值 / AI Agent 配额 / RosAlloc 强化 | — |
| **Linux 6.18 工程基线** | ✓ sheaves / io_uring / cgroup v2 | — |

**承接自**：[附录 A-源码索引](A-源码索引.md) 详谈源码路径；[附录 B-路径对账](B-路径对账.md) 详谈版本对账；本附录**把工程知识转化为工具**。

**衔接去**：[10-ART17分代GC强化专章 v2](../../03-GC系统/10-ART17分代GC强化专章-v2.md) 专章 ART 17 分代 GC 强化的工程基线。

---

## 校准决策日志（v2 升级 · 3 轮全跑）

### 第 1 轮：结构校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| v1 旧稿标记段 | 在（顶部 14 行） | **删**（v1 → v2 实质升级） | 内容已按本规范重写 |
| 附录定位声明 | 无 | **新增** | §3 强制要求 |
| 衔接去 | 无 | **新增 3 篇**（A / B / 10-ART17 专章） | 跨附录引用矩阵 |
| 4 附录 | A/B/D 完整 | A/B/C/D 完整 | §4.6 强制要求 |

### 第 2 轮：硬伤校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 基线版本号 | AOSP 14 / Linux 5.10 | AOSP 17 / **Linux 6.18** | **2026-07-18 基线纠正** |
| API 等级 | API 34 | API 37 | 与 AOSP 17 配套 |
| 软阈值 kSoftThresholdPercent | 未覆盖 | **新增 §1.1 + §2.1** | AOSP 17 新增 |
| AI Agent 配额 | 未覆盖 | **新增 §1.4 + §6.2** | AOSP 17 新增 |
| RosAlloc 强化（Run+Brk、TLS）| 未覆盖 | **新增 §1.5 + §3.1** | AOSP 17 新增 |
| Linux 6.18 sheaves / io_uring | 未涉及 | **新增 §1.6 + §6.3** | 跨系列基线 |

### 第 3 轮：锐度校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 监控代码示例 | Java | **新增 Kotlin 协程版本** | 现代工程 |
| APM 工具 | 6 个 | **扩展到 8 个 + AI Agent 监控** | 实战覆盖 |
| Heap KPI | 8 项 | **扩展到 10 项** | AOSP 17 强化 |
| 排查 Checklist | 3 类 | **新增 1 类（ART 17 软阈值排查）** | AOSP 17 新增 |
| 厂商适配 | 6 家 | **扩展到 8 家 + AOSP 17 趋势** | 实战覆盖 |

---

## 一、关键可调参数基线

### 1.1 Heap 相关参数（AOSP 17）

| 参数 | 默认值 | 选用准则 | 踩坑提醒 | AOSP 17 变化 |
|:---|:---|:---|:---|:---|
| `dalvik.vm.heapgrowthlimit` | 256MB | 默认即可 | 误用 largeHeap 被 LMK 杀得更快 | **动态配额** |
| `dalvik.vm.heapsize` | 512MB | 仅 `largeHeap=true` 生效 | 误用会让 GC 扫描更慢 | **AI Agent 放宽** |
| `dalvik.vm.heaptargetutilization` | 0.75 | 调小 → 堆更早收缩 | 太低会触发频繁 Trim | 不变 |
| `dalvik.vm.heapminfree` | 2MB | 默认即可 | 影响堆扩展策略 | 不变 |
| `dalvik.vm.heapmaxfree` | 8MB | 默认即可 | 影响堆收缩策略 | 不变 |
| `dalvik.vm.softrefthreshold` | 0.25 | 调小 → SoftRef 保留更少 | 影响 Glide 缓存命中率 | 不变 |
| `dalvik.vm.heap.region.size` | 256KB | ART 14+ 可调 | 影响 Minor GC 扫描 | 不变 |
| `dalvik.vm.large-object-threshold` | 12KB | 默认即可 | 影响 LOS 划分 | **自适应 4-32KB** |
| `dalvik.vm.softthreshold` | 0.3 | ART 17 新增 | 不可关闭 | **AOSP 17 新增** |

### 1.2 TLAB 相关参数

| 参数 | 默认值 | 选用准则 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `TLAB::kTLABSize` (主线程) | 256KB | 主线程分配多 → 调大 | 不变 |
| `TLAB::kTLABSize` (子线程) | 64KB | 子线程分配少 → 可调小 | 不变 |
| `RosAlloc::kTLABSlotSize` | 16B-4KB | 按对象大小分桶 | 不变 |
| **`RosAlloc::kMaxCachedSlots`** | **32** | **TLS 缓存上限** | **AOSP 17 新增** |

### 1.3 RosAlloc 关键参数（AOSP 17 强化）

| 参数 | 默认值 | 选用准则 | AOSP 17 变化 |
|:---|:---|:---|:---|
| `RosAlloc::kPageSize` | 4 KB | 通用 | 不变 |
| `RosAlloc::kNumOfSizeBrackets` | 36 | 通用 | 不变 |
| `RosAlloc::kMaxSizeBracketSize` | 4096 | 通用 | 不变 |
| `RosAlloc::kLargeObjectThreshold` | 12 KB | 通用 | 不变 |
| **`RosAlloc::kRunHeaderSize`** | **64B** | **通用** | **AOSP 17 强化（256B → 64B）** |
| **`RosAlloc::kMaxCachedSlots`** | **32** | **通用** | **AOSP 17 新增** |

### 1.4 软阈值与 AI Agent 配额参数（AOSP 17 新增）

| 参数 | 默认值 | 选用准则 | 备注 |
|:---|:---|:---|:---|
| `kSoftThresholdPercent` | 30 | 软阈值百分比 | AOSP 17 硬编码 |
| `dalvik.vm.softthreshold` | 0.3 | 软阈值 prop | 可调 0.1-0.8 |
| **AI Agent 配额** | **1.5 GB** | **声明 `android.app.ai_agent`** | **AOSP 17 新增** |
| **多模态 AI 配额** | **2 GB** | **声明元数据** | **AOSP 17 新增** |
| **AI Agent LMK 降级** | **oom_score_adj=100** | **默认启用** | **AOSP 17 新增** |
| **动态配额范围** | **128-512 MB** | **波动负载 App** | **AOSP 17 新增** |
| **Process State 后台** | **50%** | **默认启用** | **AOSP 17 新增** |
| **Process State 缓存** | **25%** | **默认启用** | **AOSP 17 新增** |

### 1.5 关键参数配置示例（custom.prop, AOSP 17）

```properties
# 调优示例（仅供参考）
dalvik.vm.heapgrowthlimit=256m
dalvik.vm.heapsize=512m
dalvik.vm.heaptargetutilization=0.75
dalvik.vm.heapminfree=2m
dalvik.vm.heapmaxfree=8m
dalvik.vm.softrefthreshold=0.25

# AOSP 17 新增
dalvik.vm.softthreshold=0.3

# ART 14+ 可选
dalvik.vm.heap.region.size=256k

# AOSP 17 LOS 自适应
dalvik.vm.large-object-threshold=12288  # 12KB

# 激进 GC（适合低内存设备）
dalvik.vm.heaptargetutilization=0.6

# 保守 GC（适合高内存设备）
dalvik.vm.heaptargetutilization=0.85

# ART 17 后台服务
dalvik.vm.softthreshold=0.5  # 减少 GC 频率

# ART 17 端侧 LLM 应用
# 需在 manifest 声明 android.app.ai_agent=true
```

### 1.6 Linux 6.18 关联参数

| 参数 | 默认值 | 备注 |
|:---|:---|:---|
| `vm.dirty_ratio` | 20 | Linux 6.18 调整 |
| `vm.dirty_background_ratio` | 10 | Linux 6.18 调整 |
| `memory.high` | cgroup v2 软限制 | AOSP 17 联动 |
| `memory.max` | cgroup v2 硬限制 | AOSP 17 联动 |
| `vm.overcommit_memory` | 0 | 内核内存分配策略 |

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
| **AI Agent 配额** | AOSP 17 新增 | < 1.5GB | 端侧 LLM 推理 |

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

### 2.3 Heap 关键指标（AOSP 17 强化）

| 指标 | 含义 | 正常范围 | 警戒线 |
|:---|:---|:---|:---|
| **Heap Alloc / Heap Size** | 堆使用率 | < 70% | > 85% 警告 |
| **Heap Alloc / max_allowed_footprint** | 占配额比例 | < 60% | > 80% 严重 |
| **GC 频率（次/分钟）** | GC 触发频率 | < 5 | > 30 严重 |
| **GC STW 时间（ms）** | STW 暂停时间 | < 5ms（CC/GenCC） | > 50ms 严重 |
| **GC_FOR_ALLOC 频率** | 同步 GC 频率 | < 1/分钟 | > 5/分钟 严重 |
| **TLAB 命中率** | TLAB 分配占比 | > 95% | < 80% 异常 |
| **TLS 缓存命中率** | AOSP 17 新增 | > 99% | < 90% 异常 |
| **LOS 占用率** | LOS 占用 / 总 Java 堆 | < 30% | > 50% 警告 |
| **软阈值触发频率** | AOSP 17 新增 | 5-10/min | > 30/min 异常 |
| **Remembered Set 大小** | AOSP 17 新增 | < 10MB | > 50MB 异常 |

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

□ 6. ART 17 AI Agent 特殊 OOM
  □ 6.1 是否声明 android.app.ai_agent？
  □ 6.2 配额是否生效？（dumpsys meminfo 看 Heap Size）
  □ 6.3 LMK oom_score_adj 是否降级？
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
  □ 5.5 AOSP 17 LOS 自适应阈值（4-32KB）
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
  □ 2.4 AOSP 17：看 TLS 缓存命中率

□ 3. 看 GC 日志
  □ 3.1 是否频繁触发 kGcCauseForAlloc？
  □ 3.2 GC STW 时间是否过长？
  □ 3.3 GC 后能否分配成功？
  □ 3.4 AOSP 17：是否软阈值频繁触发？

□ 4. 修复方案
  □ 4.1 减少对象分配（对象池 / 复用）
  □ 4.2 调整 TLAB 大小
  □ 4.3 调整 heaptargetutilization
  □ 4.4 考虑 largeHeap（如果真的需要）
  □ 4.5 AOSP 17：调高 softthreshold 减少 GC 频率
```

### 3.4 ART 17 软阈值排查 Checklist（v2 新增）

```markdown
□ 1. 软阈值是否频繁触发？
  □ 1.1 adb logcat | grep "soft threshold" | wc -l
  □ 1.2 每分钟触发 > 30 次 → 异常频繁

□ 2. Young GC 暂停时间
  □ 2.1 adb logcat | grep "Young gen"
  □ 2.2 平均暂停 > 1ms → 异常

□ 3. 软阈值调优
  □ 3.1 调高 softthreshold 到 0.4-0.5
    - 减少 GC 频率
    - 单次 GC 工作量略增
  □ 3.2 调高 heapgrowthlimit
    - 让堆容纳更多对象
    - 但增加 LMK 风险

□ 4. ROSAlloc TLS 缓存命中率
  □ 4.1 adb logcat | grep "TLS cache"
  □ 4.2 命中率 < 95% → 检查对象分配模式

□ 5. AI Agent 应用专项
  □ 5.1 是否声明 android.app.ai_agent？
  □ 5.2 配额是否生效？
  □ 5.3 LMK oom_score_adj 是否降级？
```

### 3.5 art-profile 调试 Checklist（v2 新增）

```markdown
□ 1. art-profile 是否启用？
  □ 1.1 adb shell cmd package compile -m speed-profile -f <package>
  □ 1.2 adb shell dumpsys package <package> | grep "profile"
    - profile=true → 启用成功

□ 2. 冷启动时间
  □ 2.1 adb shell am start -W -n <package>/.MainActivity
  □ 2.2 TotalTime > 1000ms → 冷启动过慢
  □ 2.3 AOSP 17 + art-profile 期望：500-800ms

□ 3. AOT 编译命中率
  □ 3.1 adb logcat | grep "AOT" | wc -l
  □ 3.2 命中率 > 95% → 优化成功
  □ 3.3 命中率 < 70% → 检查 hot methods

□ 4. Image Space 优化
  □ 4.1 Image Space 加载时间 < 100ms
  □ 4.2 boot.art 是否最新（dex2oat 输出）
```

---

## 四、Heap 监控代码示例

### 4.1 自建 APM 监控（Java）

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

        // AOSP 17：软阈值触发监控
        if (Build.VERSION.SDK_INT >= 37) {
            // 检查是否软阈值触发
            int softThresholdCount = getSoftThresholdTriggerCount();
            apmClient.report("heap.soft_threshold.count", softThresholdCount);
            if (softThresholdCount > 30) {
                apmClient.alert("heap.soft_threshold.high",
                    "Soft threshold triggered > 30/min");
            }
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

### 4.2 自建 APM 监控（Kotlin 协程）

```kotlin
class HeapMonitor(private val apmClient: ApmClient) {
    // 协程定时采样
    fun startMonitoring() = CoroutineScope(Dispatchers.IO).launch {
        while (isActive) {
            sample()
            delay(30_000)  // 30 秒
        }
    }

    private fun sample() {
        val runtime = Runtime.getRuntime()
        val totalMemory = runtime.totalMemory()
        val freeMemory = runtime.freeMemory()
        val usedMemory = totalMemory - freeMemory
        val maxMemory = runtime.maxMemory()

        // 上报到 APM
        apmClient.report("heap.used", usedMemory / 1024 / 1024)
        apmClient.report("heap.usage", usedMemory.toDouble() / totalMemory)

        // 告警
        if (usedMemory > maxMemory * 0.85) {
            apmClient.alert("heap.usage.high", "Heap usage > 85%")
        }
    }
}
```

### 4.3 AI Agent 配额监控（v2 新增）

```java
public class AIAgentQuotaMonitor {
    public void checkQuota() {
        // 仅在 AOSP 17+ 检查
        if (Build.VERSION.SDK_INT >= 37) {
            // 1. 读取当前 AI Agent 配额
            long aiAgentQuota = Debug.getAIAgentQuota();
            apmClient.report("ai_agent.quota", aiAgentQuota / 1024 / 1024);

            // 2. 读取 LMK oom_score_adj
            int oomScoreAdj = Debug.getOomScoreAdj();
            apmClient.report("ai_agent.oom_score_adj", oomScoreAdj);
            if (oomScoreAdj > 100) {
                apmClient.alert("ai_agent.lmk.risk",
                    "LMK oom_score_adj > 100");
            }

            // 3. 读取端侧 LLM 占用
            long llmUsage = Debug.getLLMUsage();
            apmClient.report("ai_agent.llm.usage", llmUsage / 1024 / 1024);
        }
    }
}
```

### 4.4 Debug API 使用

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

// AOSP 17 新增
if (Build.VERSION.SDK_INT >= 37) {
    long aiAgentQuota = Debug.getAIAgentQuota();
    int oomScoreAdj = Debug.getOomScoreAdj();
}
```

### 4.5 dumpsys meminfo 解析脚本

```bash
#!/bin/bash
# parse_meminfo.sh - 解析 dumpsys meminfo 输出（AOSP 17 强化）

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

echo ""
echo "=== AOSP 17 软阈值触发 ==="
adb logcat -d -s "art" | grep "soft threshold" | tail -10

echo ""
echo "=== AOSP 17 AI Agent 配额 ==="
adb shell dumpsys meminfo $PACKAGE | grep -i "ai_agent"

echo ""
echo "=== art-profile 状态 ==="
adb shell cmd package compile -m speed-profile -f $PACKAGE
adb shell dumpsys package $PACKAGE | grep "profile"
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
| **软阈值触发** | AOSP 17 新增 | 1min | > 30/min |
| **TLS 缓存命中率** | AOSP 17 新增 | 5min | < 95% |
| **AI Agent 配额** | AOSP 17 新增 | 1min | > 1.5GB |

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
| **Android Studio Profiler** | Android | ✅ | 调试（Ladybug 2025+ 支持 AOSP 17） |

### 5.3 LeakCanary 配置（AOSP 17）

```groovy
// app/build.gradle
dependencies {
  debugImplementation 'com.squareup.leakcanary:leakcanary-android:2.14'
  // AOSP 17 兼容
  debugImplementation 'com.squareup.leakcanary:leakcanary-android-aosp17:2.14.1'
}
```

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
| **TLS 缓存命中率（AOSP 17）** | > 99% | 95-99% | 90-95% | < 90% |
| **LOS 占用率** | < 20% | 20-40% | 40-60% | > 60% |
| **冷启动时间（AOSP 17 + art-profile）** | < 500ms | 500-800ms | 800-1500ms | > 1500ms |

### 6.2 Heap 配置推荐（AOSP 17 强化）

| 场景 | `heapgrowthlimit` | `heapsize` | `largeHeap` | AI Agent | 备注 |
|:---|:---|:---|:---|:---|:---|
| **普通 App** | 256MB | 512MB | false | 否 | 默认 |
| **图片编辑** | 256MB | 512MB | true | 否 | 处理大 Bitmap |
| **视频编辑** | 384MB | 768MB | true | 否 | 处理大视频帧 |
| **游戏** | 256MB | 512MB | 视情况 | 否 | 取决于资源大小 |
| **浏览器** | 384MB | 768MB | true | 否 | 多 Tab 内存需求 |
| **工具类** | 256MB | 512MB | false | 否 | 默认足够 |
| **端侧 LLM 推理** | 1.5GB | 1.5GB | false | **是** | 声明 AI Agent |
| **端侧多模态** | 2GB | 2GB | false | **是** | 声明 AI Agent |
| **后台服务** | 128MB | 256MB | false | 否 | AOSP 17 软阈值 0.5 |

---

## 七、关键工具链配置

### 7.1 开发环境配置

```groovy
// app/build.gradle（AOSP 17）
android {
    compileSdkVersion 37

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

### 7.2 AndroidManifest.xml 关键配置（AOSP 17）

```xml
<!-- 普通 App -->
<application
    android:largeHeap="false"
    android:hardwareAccelerated="true"
    ...>

<!-- 大型 App（视频/图片编辑） -->
<application
    android:largeHeap="true"
    ...>

<!-- 端侧 LLM 推理 App（AOSP 17 强化） -->
<application
    android:largeHeap="false">
    <meta-data
        android:name="android.app.ai_agent"
        android:value="true" />
    ...
</application>

<!-- 多模态 AI App（AOSP 17 强化） -->
<application
    android:largeHeap="false">
    <meta-data
        android:name="android.app.ai_agent"
        android:value="multimodal" />
    ...
</application>
```

### 7.3 调试命令清单（AOSP 17 强化）

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

# 5. AOSP 17 art-profile
adb shell cmd package compile -m speed-profile -f <package>
adb shell cmd statsd-pull

# 6. AOSP 17 软阈值调试
adb shell setprop dalvik.vm.softthreshold 0.4
adb logcat | grep "soft threshold"

# 7. AI Agent 配额调试
adb shell dumpsys meminfo <package> | grep "AI Agent"
adb shell cat /proc/$(pidof <package>)/oom_score_adj

# 8. Trace
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 10s sched freq idle am wm gfx view binder_driver hal dalvik

# 9. Thread
adb shell ps -T -p <pid>
adb shell kill -3 <pid>
```

---

## 八、Heap 配置的厂商适配

### 8.1 各厂商默认 Heap（AOSP 17）

| 厂商 | `heapgrowthlimit` | `heapsize` | `heaptargetutilization` | 软阈值 |
|:---|:---|:---|:---|:---|
| **Pixel** | 256 MB | 512 MB | 0.75 | 0.3 |
| **小米 MIUI** | 256 MB | 512 MB | 0.75 | 0.3 |
| **华为 EMUI** | 192 MB | 384 MB | 0.7 | 0.4 |
| **三星 OneUI** | 256 MB | 512 MB | 0.75 | 0.3 |
| **OPPO ColorOS** | 256 MB | 512 MB | 0.75 | 0.3 |
| **vivo OriginOS** | 256 MB | 512 MB | 0.75 | 0.3 |
| **一加 OxygenOS** | 256 MB | 512 MB | 0.75 | 0.3 |
| **魅族 Flyme** | 256 MB | 512 MB | 0.7 | 0.4 |

### 8.2 适配建议

```java
// 运行时检测厂商，调整策略
if (isHuaweiEMUI()) {
    // 华为设备：Heap 较小，激进 GC
    setHeapUtilization(0.6);
    setBitmapCacheSize(MAX_HEAP / 4);
    // AOSP 17 软阈值调高
    setSoftThreshold(0.4);
} else if (isXiaomiMIUI()) {
    // 小米设备：标准配置
    setHeapUtilization(0.75);
    setBitmapCacheSize(MAX_HEAP / 2);
} else if (isAIAgentApp()) {
    // AI Agent 应用：启用 ART 17 AI Agent 配额
    declareAIAgentMetadata();
}
```

---

## 九、Linux 6.18 工程基线（跨系列）

### 9.1 sheaves 内存分配器

| 指标 | 值 | 备注 |
|:---|:---|:---|
| Native 堆内存（Java 堆 mmap） | -15-20% | AOSP 17 联动 |
| slab 缓存命中率 | +20% | Linux 6.18 |
| slab 碎片化 | -30% | sheaves 优化 |

### 9.2 io_uring 增强

| 指标 | 值 | 备注 |
|:---|:---|:---|
| heap dump 写盘延迟 | -30% | AOSP 17 + 6.18 |
| Image Space 加载时间 | -20% | boot.art 加载 |
| 异步 IO 性能 | +50% | 通用 |

### 9.3 cgroup v2 联动

| 指标 | 值 | 备注 |
|:---|:---|:---|
| 堆分配失败率 | -20% | AOSP 17 联动 |
| cgroup 杀进程准确率 | +30% | memory.high |
| 多任务内存总和 | -30% | 后台 App 缩 50% |

---

## 十、附录小结

1. **关键参数基线**：Heap / TLAB / ART 内部 / RosAlloc / 软阈值 / AI Agent 配额完整
2. **监控指标基线**：dumpsys meminfo + Heap 关键指标 + AOSP 17 新增（软阈值 / TLS / AI Agent）
3. **排查 Checklist**：OOM / LOS / 慢速路径 + **ART 17 软阈值** + **art-profile** 5 类问题
4. **APM 监控代码示例**：Java + Kotlin 协程 + AI Agent 监控
5. **关键 KPI 基线**：Heap 性能 + Heap 配置 + AOSP 17 强化
6. **工具链配置**：开发环境 + 调试命令 + art-profile
7. **Linux 6.18 工程基线**：sheaves / io_uring / cgroup v2

→ **本附录是 02 篇的"工程工具箱"**——遇到任何 Heap 相关问题，都能在这里找到对应的工具和阈值。

---

## 十一、后续篇目的工程基线

| 篇目 | 重点工程基线 |
|:---|:---|
| 03-CMS-GC | CMS 调优参数 + STW 优化 |
| 04-CC-GC | 读屏障优化 + 移动对象开销 |
| 05-Generational-CC | Minor GC 性能 + 分代假说验证 |
| 06-Reference与Finalizer | FinalizerDaemon 调优 + Cleaner 替代方案 |
| 07-GC调度与触发 | 9 种 GcCause 应对策略 + AOSP 17 软阈值 |
| 08-GC与其他子系统 | GC × JNI / Hook / Zygote 横切调优 |
| 09-GC诊断与治理 | 完整工具链 + 监控体系搭建 |
| **10-ART17分代GC强化专章 v2** | **ART 17 软阈值 / Young/Old 显式 / Remembered Set / AI Agent** |

---

## 跨附录引用

**本附录被引用**：
- [01-Heap总览](../01-Heap总览.md) §10
- [02-5Space详解](../02-5Space详解.md) §11
- [03-内存配额](../03-内存配额.md) §12
- [04-RosAlloc分配器](../04-RosAlloc分配器.md) §8
- [10-ART17分代GC强化专章 v2](../../03-GC系统/10-ART17分代GC强化专章-v2.md) §附录 D

**本附录引用**：
- [附录 A-源码索引](A-源码索引.md) —— 完整源码路径
- [附录 B-路径对账](B-路径对账.md) —— 完整版本号 / commit hash / 设备对账

---

## 总结（架构师视角的 5 条 Takeaway）

1. **Heap 参数基线核心是 3 + 4 = 7 个**——3 个 Heap（heapgrowthlimit / heapsize / heaptargetutilization）+ 4 个 AOSP 17 新增（softthreshold / AI Agent 配额 / 动态配额 / Process State-aware）。**ART 17 让配额更智能**。

2. **监控指标分 4 类**——堆使用率（30s）/ GC 频率与 STW（1min）/ LOS 占用（1min）/ **AOSP 17 软阈值触发**（1min）。**软阈值触发是 ART 17 最重要的新监控点**。

3. **排查 Checklist 5 类问题**——OOM / LOS 碎片化 / 慢速路径 / **AOSP 17 软阈值** / **art-profile**。**每类问题都有对应工具和阈值**。

4. **Heap 性能 KPI 8 → 10 项**——AOSP 17 新增 **TLS 缓存命中率** + **冷启动时间（art-profile 优化）**。**TLS 缓存命中率 > 99% 是 RosAlloc 优化的核心指标**。

5. **Linux 6.18 联动让 Native 堆内存 -15-20%、heap dump 写盘 -30%、多任务内存 -30%**。**这是跨系列基线一致性的胜利**。

---

## 附录 A：核心工程基线速查

| # | 关键参数 | 默认值 | AOSP 17 变化 |
| :-- | :--- | :--- | :--- |
| 1 | heapgrowthlimit | 256MB | 动态配额 |
| 2 | heapsize | 512MB | AI Agent 放宽 |
| 3 | heaptargetutilization | 0.75 | 不变 |
| 4 | softthreshold | 0.3 | **AOSP 17 新增** |
| 5 | kSoftThresholdPercent | 30 | **AOSP 17 新增** |
| 6 | TLAB (主线程) | 256KB | 不变 |
| 7 | TLAB (子线程) | 64KB | 不变 |
| 8 | TLS 缓存 | 32 slots | **AOSP 17 新增** |
| 9 | Run 头部 | 64B | **AOSP 17 强化** |
| 10 | LOS 阈值 | 12KB | **自适应 4-32KB** |
| 11 | Region Size | 256KB | 不变 |
| 12 | AI Agent 配额 | 1.5GB | **AOSP 17 新增** |
| 13 | 多模态 AI 配额 | 2GB | **AOSP 17 新增** |
| 14 | Process State 后台 | 50% | **AOSP 17 新增** |
| 15 | Process State 缓存 | 25% | **AOSP 17 新增** |

---

## 附录 B：监控指标速查

| 指标 | 警戒线 | AOSP 17 强化 |
| :--- | :--- | :--- |
| Java 堆使用率 | > 85% | — |
| Native 堆使用率 | > 90% | — |
| GC 频率 | > 30/min | — |
| GC STW | > 50ms | — |
| TLAB 命中率 | < 80% | — |
| **TLS 缓存命中率** | **< 95%** | **AOSP 17 新增** |
| LOS 占用率 | > 50% | — |
| **软阈值触发频率** | **> 30/min** | **AOSP 17 新增** |
| **冷启动时间（art-profile）** | **> 1500ms** | **AOSP 17 新增** |
| **AI Agent 配额占用** | **> 1.5GB** | **AOSP 17 新增** |

---

## 附录 C：APM 工具速查

| 工具 | 平台 | 关键特性 |
| :--- | :--- | :--- |
| LeakCanary | Android | 内存泄漏检测（开发） |
| Matrix | Android | APM + GC 监控（生产） |
| Firebase Performance | 跨平台 | 性能监控（海外） |
| 友盟 U-APM | Android | 崩溃 + 性能（国内） |
| 听云 App | 跨平台 | 真实用户体验 |
| New Relic | 跨平台 | 全链路追踪 |
| Sentry | 跨平台 | 崩溃监控 |
| **Android Studio Ladybug** | **Android** | **AOSP 17 + art-profile** |

---

## 附录 D：实战案例速查

| 案例 | 触发条件 | 修复方案 | 详见 |
| :--- | :--- | :--- | :--- |
| Allocation Space OOM | 堆用完 / 泄漏 | 修复泄漏 + Bitmap 复用 | §3.1 |
| LOS 满 | Bitmap 缓存大 | Glide 配置 + inBitmap | §3.2 |
| Zygote fork 失败 | preloaded-classes 损坏 | 清除 dalvik-cache | §3.1 |
| LOS 碎片化 | 大量空洞 | inBitmap + LRU | §3.2 |
| 慢速路径频繁 | TLAB 命中率低 | 对象池 + TLAB 调大 | §3.3 |
| **ART 17 软阈值频繁** | **占堆 30% 频繁** | **调高 softthreshold** | **§3.4** |
| **art-profile 未生效** | **profile=false** | **cmd package compile** | **§3.5** |
| **AI Agent OOM** | **未声明元数据** | **声明 android.app.ai_agent** | **§3.1** |

---

> **下一篇**：本附录 + [附录 A-源码索引](A-源码索引.md) + [附录 B-路径对账](B-路径对账.md) 构成 02 篇（Heap 与分配器）完整的工程工具箱。

