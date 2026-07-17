# 附录 D：工程基线

> **本附录是 01 篇的"工程基线"** —— 关键参数、监控指标、排查 checklist 的完整清单。
>
> **目的**：把本篇的知识点转化为可直接使用的工程工具。

---

## 一、关键可调参数基线（ART GC 相关）

### 1.1 dalvik.vm.* 参数

| 参数 | 默认值 | 选用准则 | 踩坑提醒 |
|:---|:---|:---|:---|
| `dalvik.vm.heapgrowthlimit` | 256MB | 默认即可 | 误用 `largeHeap` 被 LMK 杀得更快 |
| `dalvik.vm.heapsize` | 512MB | 仅 `largeHeap=true` 生效 | 误用会让 GC 扫描更慢 |
| `dalvik.vm.softrefthreshold` | 0.25 | 调小 → SoftRef 保留更少 | 影响 Glide 缓存命中率 |
| `dalvik.vm.heaptargetutilization` | 0.75 | 调小 → 堆更早收缩 | 太低会触发频繁 Trim |
| `dalvik.vm.gc.max-relative-concurrent-start-threshold` | 0.05 | 调整 CC GC 启动时机 | 影响后台 GC 频率 |
| `dalvik.vm.dex2oat-Xms` | 64m | 默认即可 | 影响 dex2oat 启动速度 |
| `dalvik.vm.dex2oat-Xmx` | 512m | 默认即可 | 影响 dex2oat 最大内存 |
| `dalvik.vm.image-dex2oat-Xms` | 64m | 默认即可 | 影响 image dex2oat 启动速度 |
| `dalvik.vm.image-dex2oat-Xmx` | 64m | 默认即可 | 影响 image dex2oat 最大内存 |

### 1.2 ART 内部参数

| 参数 | 默认值 | 选用准则 | 踩坑提醒 |
|:---|:---|:---|:---|
| `ConcurrentCopying::kMaxMarkStackSize` | 64 KB | 默认即可 | 太大占用内存 |
| `CardTable::kCardSize` | 512 字节 | 默认即可 | ART 14+ 支持 128/256 |
| `ReferenceProcessor::kDefaultSoftRefThreshold` | 0.25 | 同 `dalvik.vm.softrefthreshold` | 一致性 |
| `Heap::kDefaultMaxRelativeConcurrentStartThreshold` | 0.05 | 同 `dalvik.vm.gc.max-relative-...` | 一致性 |

### 1.3 Kernel 相关参数

| 参数 | 默认值 | 选用准则 | 踩坑提醒 |
|:---|:---|:---|:---|
| `vm.lowmemkiller.minfree` | 厂商定制 | 默认即可 | 影响 LMK 杀进程时机 |
| `vm.vfs_cache_pressure` | 100 | 默认即可 | 影响文件系统缓存 |
| `vm.swappiness` | 60 | 调高 → 更积极 swap | 影响 zram 行为 |
| `vm.dirty_ratio` | 20 | 默认即可 | 影响脏页回写 |
| `vm.pressure_level` | 内核 4.20+ | 默认即可 | 内存压力通知 |

### 1.4 关键参数配置示例（custom.prop）

```properties
# 调优示例（仅供参考）
dalvik.vm.heapgrowthlimit=256m
dalvik.vm.heapsize=512m
dalvik.vm.softrefthreshold=0.25
dalvik.vm.heaptargetutilization=0.75
dalvik.vm.gc.max-relative-concurrent-start-threshold=0.05

# OEM 定制（小米/华为等）
ro.config.low_ram=false
```

---

## 二、监控指标基线

### 2.1 dumpsys meminfo 关键指标

| 指标 | 含义 | 正常范围 | 异常处理 |
|:---|:---|:---|:---|
| **Native Heap** | Native 内存分配 | < 200MB | 检查 JNI / DirectByteBuffer |
| **Dalvik Heap** | Java 堆使用 | < heapgrowthlimit | 检查 GC Root / 泄漏 |
| **Dalvik Heap Alloc** | 已分配 Java 堆 | < Dalvik Heap Size | 同上 |
| **Stack** | 线程栈 | < 5MB / thread | 检查线程数 |
| **Cursor** | Cursor 内存 | < 10MB | 检查 Cursor 泄漏 |
| **Ashmem** | 共享内存 | < 50MB | 检查 Surface / Bitmap |
| **Graphics** | 图形内存 | < 100MB | 检查 GL Texture |
| **Code** | 代码段 | < 100MB | 检查 DEX / OAT 大小 |
| **Other dev** | 其他设备 | < 20MB | — |
| **.so mmap** | .so 映射 | < 50MB | 检查 .so 泄漏 |
| **.jar mmap** | .jar 映射 | < 20MB | — |
| **.apk mmap** | .apk 映射 | < 20MB | — |
| **.ttf mmap** | .ttf 映射 | < 10MB | — |
| **.dex mmap** | .dex 映射 | < 50MB | 检查 DEX 数量 |
| **Other mmap** | 其他映射 | < 50MB | — |
| **EGL mtrack** | EGL 内存追踪 | < 50MB | 检查 EGL 泄漏 |
| **GL mtrack** | GL 内存追踪 | < 50MB | 检查 GL Texture 泄漏 |
| **Unknown** | 未知 | < 10MB | — |
| **TOTAL** | 总计 | < 500MB（普通 App） | 综合判断 |
| **TOTAL PSS** | PSS 总计 | < 500MB | 综合判断 |
| **TOTAL RSS** | RSS 总计 | < 1GB | 综合判断 |
| **TOTAL SWAP PSS** | Swap PSS | < 100MB | 检查 Swap 使用 |

### 2.2 GC 关键指标

| 指标 | 含义 | 正常范围 | 异常处理 |
|:---|:---|:---|:---|
| **GC 频率** | 每分钟 GC 次数 | < 5 次/分钟 | 检查堆压力 |
| **GC STW 时间** | STW 暂停时间 | < 5ms（CC/GenCC） | 检查 GC Root 数量 |
| **Minor GC STW** | Minor GC 暂停时间 | < 0.5ms（GenCC） | 检查 Card Table |
| **Major GC STW** | Major GC 暂停时间 | < 10ms | 检查 Live Set 大小 |
| **Background GC 频率** | 后台 GC 频率 | 1-3 次/分钟 | 检查 `dalvik.vm.gc.max-relative-...` |
| **Finalizer 队列深度** | 待 finalize 的对象数 | < 100 | 检查 finalize() 阻塞 |
| **Reference 队列深度** | 待清理 Reference 数 | < 1000 | 检查 Reference 泄漏 |
| **Card Table dirty 比例** | dirty card 占比 | < 5% | 检查跨代引用频率 |
| **TLAB 分配成功率** | TLAB 分配占比 | > 95% | 检查分配竞争 |
| **Concurrent GC 标记速度** | 标记对象数/秒 | > 100K/秒 | 检查对象数 |

### 2.3 GC 日志关键字段（logcat）

```bash
# ART GC 日志
adb logcat -d -s "art" | grep -i "gc"

# 关键日志示例
art : Background concurrent copying GC freed 1048576(13MB) AllocSpace objects, 0(0B) LOS objects, 50% free, 13MB/26MB, paused 1.234ms total 50.5ms
#                                                              ↑                    ↑
#                                                              释放字节数           暂停时间

# 关键字段解读
# - freed：释放的字节数 + 对象数
# - LOS：Large Object Space
# - free：释放后空闲比例
# - AllocSpace：Allocation Space 大小
# - paused：STW 时间
# - total：GC 总耗时
```

### 2.4 Perfetto 关键 trace 字段

```
# Perfetto trace 中的 GC 事件
ART::ConcurrentCopying::MarkingRoot
ART::ConcurrentCopying::MarkObject
ART::ConcurrentCopying::CopyingPhase
ART::ConcurrentCopying::ReclaimPhase
ART::Heap::VisitRoots
ART::WriteBarrier
ART::ReadBarrier
ART::FinalizerDaemon::Run
ART::ReferenceQueueDaemon::Run
```

---

## 三、排查 Checklist

### 3.1 OOM 排查 Checklist

```markdown
□ 1. 确认 OOM 类型
  □ 1.1 Java heap OOM？ (dumpsys meminfo 看 Dalvik Heap)
  □ 1.2 Native heap OOM？ (dumpsys meminfo 看 Native Heap)
  □ 1.3 Graphics OOM？ (dumpsys meminfo 看 Graphics)
  □ 1.4 Thread/Stack OOM？ (dumpsys meminfo 看 Stack)
  □ 1.5 FD/Thread OOM？ (dumpsys meminfo 看 FD)

□ 2. Java heap OOM 排查
  □ 2.1 检查 LeakCanary 报告（如果集成）
  □ 2.2 手动触发 heap dump (hprof)
  □ 2.3 用 MAT / Shark 分析
  □ 2.4 找出最大的 retained heap 对象
  □ 2.5 检查 GC Root 引用链
  □ 2.6 验证泄漏源（Activity / Fragment / Handler / Callback）

□ 3. Native heap OOM 排查
  □ 3.1 检查 JNI Global Ref 数量 (dumpsys meminfo | grep JNI)
  □ 3.2 检查 DirectByteBuffer 数量
  □ 3.3 检查第三方 .so 的 mmap (smaps)
  □ 3.4 检查 Bitmap 分配（是否复用）
  □ 3.5 检查 Surface 分配

□ 4. Graphics OOM 排查
  □ 4.1 检查 EGL mtrack (dumpsys meminfo | grep EGL)
  □ 4.2 检查 GL mtrack (dumpsys meminfo | grep GL)
  □ 4.3 检查 Surface 泄漏
  □ 4.4 检查 HWUI display list 泄漏

□ 5. 修复方案
  □ 5.1 Java heap OOM：修复泄漏 + 减小缓存 + 用 LRU 替代 WeakRef
  □ 5.2 Native heap OOM：复用 DirectByteBuffer + 复用 Bitmap
  □ 5.3 Graphics OOM：复用 Surface + 减少 GL Texture
```

### 3.2 GC 卡顿排查 Checklist

```markdown
□ 1. 抓取 systrace / Perfetto
  □ 1.1 抓取 trace 时长 ≥ 30 秒
  □ 1.2 包含 GC 事件（sched freq am wm gfx view binder_driver hal dalvik）
  □ 1.3 拉取 trace 到本地

□ 2. 找 GC 事件
  □ 2.1 找 ConcurrentCopying / MarkSweep 事件
  □ 2.2 看 STW 时间分布
  □ 2.3 看 GC 频率

□ 3. 分析 STW 时间
  □ 3.1 单次 STW > 10ms → 异常
  □ 3.2 GC 频率 > 10 次/分钟 → 异常
  □ 3.3 Major GC 频繁 → 分代假说失效

□ 4. CMS 卡顿排查
  □ 4.1 Remark 阶段长？Incremental Update 标脏过多？
  □ 4.2 Initial Mark 阶段长？GC Root 多？
  □ 4.3 升级到 CC GC？

□ 5. CC GC 卡顿排查
  □ 5.1 Initialize 阶段长？栈扫描慢？
  □ 5.2 Copy 阶段长？Live Set 大？
  □ 5.3 读屏障开销大？Hot path 太多？

□ 6. GenCC 卡顿排查
  □ 6.1 Minor GC 频繁？Card Table 频繁 dirty？
  □ 6.2 Major GC 频繁？分代假说失效？
  □ 6.3 跨代引用过多？长寿对象污染 Young Gen？

□ 7. 修复方案
  □ 7.1 减小堆大小（避免频繁 GC）
  □ 7.2 优化内存使用（对象池 / LRU 缓存）
  □ 7.3 升级到更新的 GC（CMS → CC → GenCC）
  □ 7.4 调整 GC 参数（参见附录 D-1）
```

### 3.3 内存泄漏排查 Checklist

```markdown
□ 1. 集成 LeakCanary
  □ 1.1 在 build.gradle 添加依赖
  □ 1.2 在 Application 初始化
  □ 1.3 测试泄漏检测是否生效

□ 2. 触发可疑代码路径
  □ 2.1 执行可疑操作（旋转屏幕 / 进入退出 Activity）
  □ 2.2 等待 LeakCanary 检测

□ 3. 分析 LeakCanary 报告
  □ 3.1 看泄漏链
  □ 3.2 找到 GC Root
  □ 3.3 找到泄漏对象
  □ 3.4 修复泄漏源

□ 4. 常见泄漏源
  □ 4.1 Activity / Fragment Context 泄漏
  □ 4.2 Handler / Runnable 引用泄漏
  □ 4.3 静态变量持有 Activity
  □ 4.4 Listener / Callback 未注销
  □ 4.5 Thread / TimerTask 未停止
  □ 4.6 WeakHashMap value 泄漏
  □ 4.7 JNI Global Ref 泄漏
  □ 4.8 第三方库泄漏（Glide / OkHttp / 推送 SDK）

□ 5. 修复方案
  □ 5.1 用 Application Context 替代 Activity Context
  □ 5.2 Handler 用 WeakReference 包裹
  □ 5.3 在 onDestroy 中清理静态引用
  □ 5.4 在 onDestroy 中注销 Listener
  □ 5.5 在 onDestroy 中停止 Thread / TimerTask
  □ 5.6 WeakHashMap 改用 LRU
  □ 5.7 JNI Global Ref 配对 DeleteGlobalRef
  □ 5.8 第三方库升级或反馈
```

---

## 四、APM 监控指标基线

### 4.1 应用层指标

```java
// 自建 APM 监控示例代码
public class GCMonitor {
    // GC 频率（次/分钟）
    private AtomicInteger gcCount = new AtomicInteger();
    
    // STW 时间累计（ms）
    private AtomicLong totalPauseTime = new AtomicLong();
    
    // GC 触发原因统计
    private ConcurrentHashMap<String, AtomicInteger> gcCauseMap;
    
    // JVMTI 回调
    public void onGarbageCollectionStart() {
        gcCount.incrementAndGet();
    }
    
    public void onGarbageCollectionFinish(long pauseTime) {
        totalPauseTime.addAndGet(pauseTime);
    }
    
    // 定时上报
    @Scheduled(fixedRate = 60000)
    public void report() {
        long pauseAvg = totalPauseTime.get() / Math.max(1, gcCount.get());
        // 上报到 APM 服务
        apmClient.report("gc.frequency", gcCount.get());
        apmClient.report("gc.pause.avg", pauseAvg);
    }
}
```

### 4.2 关键告警阈值

| 指标 | 警告阈值 | 严重阈值 | 紧急处理 |
|:---|:---|:---|:---|
| Java heap 使用率 | > 70% | > 85% | > 95% 立即报警 |
| Native heap 使用率 | > 80% | > 90% | > 95% 立即报警 |
| GC 频率（次/分钟） | > 10 | > 30 | > 60 立即报警 |
| GC STW 时间（ms） | > 10 | > 50 | > 200 立即报警 |
| Minor GC STW（ms） | > 1 | > 5 | > 10 立即报警 |
| Major GC STW（ms） | > 20 | > 100 | > 500 立即报警 |
| Finalizer 队列深度 | > 100 | > 1000 | > 10000 立即报警 |
| Reference 队列深度 | > 1000 | > 10000 | > 100000 立即报警 |
| Card Table dirty 比例 | > 5% | > 10% | > 20% 立即报警 |
| Thread 数 | > 200 | > 500 | > 1000 立即报警 |
| JNI Global Ref | > 100 | > 500 | > 1000 立即报警 |
| .so mmap | > 50MB | > 100MB | > 200MB 立即报警 |
| EGL mtrack | > 30MB | > 100MB | > 200MB 立即报警 |
| GL mtrack | > 30MB | > 100MB | > 200MB 立即报警 |

### 4.3 APM 工具推荐

| 工具 | 平台 | 关键特性 | 适用场景 |
|:---|:---|:---|:---|
| **LeakCanary** | Android | 内存泄漏检测 | 调试 + 测试 |
| **Matrix** | Android | APM + GC 监控 | 生产环境 |
| **Firebase Performance** | 跨平台 | 性能监控 | 海外 App |
| **友盟 U-APM** | Android | 崩溃 + 性能 | 国内 App |
| **听云 App** | 跨平台 | 真实用户体验 | 国内 App |
| **New Relic** | 跨平台 | 全链路追踪 | 海外 App |
| **Sentry** | 跨平台 | 崩溃监控 | 调试 + 生产 |

---

## 五、工具链配置基线

### 5.1 开发环境

```bash
# 必备工具
Android Studio Hedgehog (2023.1.1) 或更新
JDK 17 (AGP 8.0+)
Gradle 8.0+
Android SDK 34
NDK r25c 或更新

# 推荐工具
LeakCanary 2.10+
Matrix 2.0+
Perfetto UI (https://ui.perfetto.dev/)
cs.android.com (AOSP 源码搜索)
```

### 5.2 调试命令清单

```bash
# 1. 内存相关
adb shell dumpsys meminfo <package>
adb shell procrank
adb shell run-as <package> cat /proc/self/smaps > smaps.txt
adb shell run-as <package> cat /proc/self/maps > maps.txt

# 2. GC 相关
adb logcat -d -s "art" | grep -i "gc"
adb shell setprop dalvik.vm.dex2oat-Xms 256m
adb shell setprop dalvik.vm.dex2oat-Xmx 512m

# 3. Trace 相关
adb shell perfetto --out /data/local/tmp/trace.proto \
  -t 10s \
  sched freq idle am wm gfx view binder_driver hal dalvik \
  camera input hal res
adb pull /data/local/tmp/trace.proto

# 4. Thread 相关
adb shell ps -T -p <pid>
adb shell kill -3 <pid>  # 触发 ANR / dump thread

# 5. Native crash
adb shell logcat -d -b crash
adb shell ls /data/tombstones/
```

### 5.3 关键 Gradle 配置

```groovy
// app/build.gradle
android {
    compileSdkVersion 34
    
    defaultConfig {
        // ... 
    }
    
    buildTypes {
        debug {
            // 调试时启用所有监控
            debuggable true
            minifyEnabled false
            shrinkResources false
        }
        release {
            // 发布时启用混淆 + R8
            minifyEnabled true
            shrinkResources true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
    
    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
    
    // 大堆配置（仅当需要时）
    // defaultConfig {
    //     manifestPlaceholders = [largeHeap: "true"]
    // }
}

dependencies {
    // LeakCanary 调试依赖
    debugImplementation 'com.squareup.leakcanary:leakcanary-android:2.14'
    
    // 监控 SDK（按需选择）
    implementation 'com.tencent.matrix:matrix-android:2.0.0'
}
```

### 5.4 AndroidManifest.xml 关键配置

```xml
<!-- 大堆配置（仅当真正需要时） -->
<application
    android:largeHeap="false"  <!-- 默认 false，避免被 LMK 杀 -->
    android:hardwareAccelerated="true"
    ...>

<!-- 调试时启用 strict mode -->
<!-- 在 Application.onCreate 中启用 -->
```

```java
// StrictMode 配置（调试时）
if (BuildConfig.DEBUG) {
    StrictMode.setThreadPolicy(new StrictMode.ThreadPolicy.Builder()
        .detectAll()
        .penaltyLog()
        .build());
    StrictMode.setVmPolicy(new StrictMode.VmPolicy.Builder()
        .detectLeakedClosableObjects()
        .detectLeakedRegistrationObjects()
        .penaltyLog()
        .build());
}
```

---

## 六、关键 KPI 基线

### 6.1 应用启动 KPI

| 指标 | 启动类型 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|:---|
| **冷启动时间** | 冷启动 | < 1s | 1-2s | 2-3s | > 3s |
| **温启动时间** | 温启动 | < 500ms | 500ms-1s | 1-2s | > 2s |
| **热启动时间** | 热启动 | < 100ms | 100-300ms | 300-500ms | > 500ms |
| **首帧绘制时间** | 冷启动 | < 1.5s | 1.5-2.5s | 2.5-4s | > 4s |
| **可交互时间** | 冷启动 | < 2s | 2-3s | 3-5s | > 5s |

### 6.2 内存 KPI

| 指标 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|
| **Java 堆使用率** | < 50% | 50-70% | 70-85% | > 85% |
| **Native 堆使用率** | < 60% | 60-80% | 80-90% | > 90% |
| **总 PSS** | < 200MB | 200-400MB | 400-600MB | > 600MB |
| **内存增长率（24h）** | < 20% | 20-50% | 50-100% | > 100% |
| **内存泄漏率（7d）** | 0 | < 5% | 5-20% | > 20% |

### 6.3 GC 性能 KPI

| 指标 | 优秀 | 良好 | 一般 | 差 |
|:---|:---|:---|:---|:---|
| **GC 频率（次/分钟）** | < 2 | 2-5 | 5-10 | > 10 |
| **Minor GC 频率** | < 5/分钟 | 5-15/分钟 | 15-30/分钟 | > 30/分钟 |
| **Major GC 频率** | < 1/小时 | 1-3/小时 | 3-10/小时 | > 10/小时 |
| **Minor GC STW** | < 0.3ms | 0.3-0.5ms | 0.5-2ms | > 2ms |
| **Major GC STW** | < 5ms | 5-15ms | 15-50ms | > 50ms |
| **Background GC 占比** | > 50% | 30-50% | 10-30% | < 10% |
| **GC 吞吐率** | > 99% | 95-99% | 90-95% | < 90% |

---

## 七、附录小结

1. **关键参数基线**：完整 dalvik.vm.* / ART / Kernel 参数表
2. **监控指标基线**：dumpsys meminfo + GC 指标 + Perfetto trace 字段
3. **排查 Checklist**：OOM / GC 卡顿 / 内存泄漏 三类问题的完整 checklist
4. **APM 监控指标基线**：关键告警阈值 + 工具推荐
5. **工具链配置基线**：开发环境 + 调试命令 + Gradle 配置
6. **关键 KPI 基线**：启动 / 内存 / GC 性能的全套 KPI

→ **本附录是 01 篇的"工程工具箱"**——遇到任何 GC 相关问题，都能在这里找到对应的工具和阈值。

---

## 八、后续篇目的工程基线

| 篇目 | 重点工程基线 |
|:---|:---|
| 02-Heap 与分配器 | 5 Space 内存基线 + 分配器性能 |
| 03-CMS-GC | CMS 调优参数 + STW 优化 |
| 04-CC-GC | 读屏障优化 + 移动对象开销 |
| 05-Generational-CC | Minor GC 性能 + 分代假说验证 |
| 06-Reference与Finalizer | FinalizerDaemon 调优 + Cleaner 替代方案 |
| 07-GC调度与触发 | 9 种 GcCause 应对策略 + Native 触发优化 |
| 08-GC与其他子系统 | GC × JNI / Hook / Zygote 横切调优 |
| 09-GC诊断与治理 | 完整工具链 + 监控体系搭建 |
