# 3.7 稳定性：CMS 时代特有的 OOM 模式

> **本节回答一个根本问题**：CMS 时代（Android 5-7）的 OOM 与 CC GC 时代有什么不同？5 种 OOM 在 CMS 下分别怎么排查？
>
> **答案**：CMS 时代的 OOM 与碎片化强相关，需要结合 RosAlloc + LOS + 业务层综合分析。
>
> **理解本节，就掌握了 CMS 时代 OOM 的完整排查方法论**。

---

## 一、CMS 时代 OOM 的总体特征

### 3.7.1 CMS 时代 OOM 的 5 大模式

| 模式 | 占比 | 主要特征 | 排查难度 |
|:---|:---|:---|:---|
| **真实 OOM（堆用完）** | ~30% | Heap Alloc ≈ Heap Size | 简单 |
| **LOS 碎片化** | ~30% | Heap Alloc << Heap Size，但分配失败 | 中等 |
| **Allocation Space 碎片化** | ~15% | 单 size class 不够，其他 size class 有空闲 | 中等 |
| **GC 失败后 OOM** | ~10% | 触发 GC 但释放 0 字节 | 困难 |
| **混合 OOM** | ~15% | 多种碎片化叠加 | 极困难 |

### 3.7.2 CMS 时代 OOM 的总排查流程

```
Java heap OOM
    │
    ▼
1. dumpsys meminfo 看 Heap Alloc / Heap Size
    │
    ├─── Alloc ≈ Size → 真实 OOM → 检查泄漏
    │
    └─── Alloc << Size → 碎片化 OOM
         │
         ▼
        2. 生成 hprof
         │
         ├─── 3. 用 MAT 分析 LOS 大对象
         │      │
         │      ├─── 有大量大空洞 → LOS 碎片化
         │      │
         │      └─── 无明显空洞 → Allocation Space 碎片化
         │
         ├─── 4. 分析 Allocation Space 的 size class 分布
         │      │
         │      ├─── 单 size class 满 → RosAlloc 分桶碎片化
         │      │
         │      └─── 多 size class 都满 → 真实 OOM
         │
         └─── 5. 触发 GC，看释放量
                │
                ├─── GC 释放 > 0 → 真实 OOM
                │
                └─── GC 释放 = 0 → 严重碎片化
```

---

## 二、模式 1：真实 OOM（堆用完）

### 3.7.3 真实 OOM 的特征

**表现**：
```
dumpsys meminfo:
  Dalvik Heap: 250 MB / 256 MB (97.6% 使用)
  Heap Alloc ≈ Heap Size
```

**根因**：Java 堆真的满了，没有空闲空间。

### 3.7.4 真实 OOM 的常见原因

**原因 1：内存泄漏**

```java
// Activity 泄漏（最常见）
public class LeakyActivity extends Activity {
    private static LeakyActivity sInstance;  // 静态变量持有 Activity
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        sInstance = this;  // ❌ 泄漏
    }
}
```

**原因 2：长生命周期对象**

```java
// 单例持有 Activity Context
public class AppManager {
    private static Context sContext;  // ❌ 应该是 Application Context
    
    public static void init(Activity activity) {
        sContext = activity;  // ❌ 泄漏
    }
}
```

**原因 3：缓存无上限**

```java
// 无限制的缓存
private Map<String, Object> cache = new HashMap<>();
// 持续添加，永不清理 → 内存爆炸
```

### 3.7.5 真实 OOM 的排查

```bash
# 1. LeakCanary 自动检测
# 在 build.gradle 添加依赖
debugImplementation 'com.squareup.leakcanary:leakcanary-android:2.14'

# 2. 手动 heap dump
adb shell am dumpheap <pid> /data/local/tmp/oom.hprof
adb pull /data/local/tmp/oom.hprof
hprof-conv oom.hprof oom-conv.hprof

# 3. 用 MAT 分析
# - Leak Suspects 报告（自动找泄漏）
# - Histogram（按类统计）
# - Dominator Tree（找保留堆最大的对象）
```

### 3.7.6 真实 OOM 的修复

| 泄漏源 | 修复方案 |
|:---|:---|
| Activity 泄漏 | 用 Application Context |
| Handler 泄漏 | 用 WeakReference |
| 静态变量 | 用 Application Context |
| Listener 未注销 | 在 onDestroy 中注销 |
| Thread 未停止 | 在 onDestroy 中 interrupt |
| 缓存无上限 | 用 LRU 缓存 |
| Bitmap 未 recycle | 在 onDestroy 中 recycle |

---

## 三、模式 2：LOS 碎片化 OOM

### 3.7.7 LOS 碎片化 OOM 的特征

**表现**：
```
dumpsys meminfo:
  Dalvik Heap: 150 MB / 256 MB (58% 使用)
  → 但分配 5 MB Bitmap 失败 → OOM

# 关键现象：Heap Alloc << Heap Size，但分配失败
```

**根因**：LOS 充满空洞，没有连续大空间。

### 3.7.8 LOS 碎片化的常见场景

**场景 1：图片加载 App**

```java
// Glide 加载不同大小图片
Glide.with(context).load(url_small).into(view_small);  // 2 MB
Glide.with(context).load(url_large).into(view_large);  // 8 MB
Glide.with(context).load(url_huge).into(view_huge);    // 12 MB

// 用户滑动列表
// → 不同大小的 Bitmap 进入 LOS
// → 释放时留下各种大小的空洞
// → 最终无法分配新的大 Bitmap
```

**场景 2：大 byte[] 缓存**

```java
// 缓存 protobuf 数据
byte[] data1 = new byte[5 * 1024 * 1024];  // 5 MB
byte[] data2 = new byte[8 * 1024 * 1024];  // 8 MB
// 释放 data1，留下 5 MB 空洞
// 分配 6 MB 失败
```

### 3.7.9 LOS 碎片化的排查

```bash
# 1. 生成 hprof
adb shell am dumpheap <pid> /data/local/tmp/los.hprof
adb pull /data/local/tmp/los.hprof
hprof-conv los.hprof los-conv.hprof

# 2. 用 MAT 分析 LOS 大对象
# MAT → Histogram → 过滤 size > 12 KB
# 看 Bitmap / byte[] / long[] 等大对象

# 3. 看 LOS 总占用
adb shell dumpsys meminfo <package> | grep -A 5 "LOS"
# （需要 ART 调试模式）
```

### 3.7.10 LOS 碎片化的修复

**修复 1：及时 recycle() Bitmap**

```java
// 优化前
public void onDestroy() {
    super.onDestroy();
    // 忘记 recycle
}

// 优化后
public void onDestroy() {
    super.onDestroy();
    if (bitmap != null && !bitmap.isRecycled()) {
        bitmap.recycle();  // 立即释放
    }
}
```

**修复 2：Bitmap inBitmap 复用**

```java
// Glide 自动启用 inBitmap
// Glide.with(context).load(url).into(view);

// 自定义 inBitmap
BitmapFactory.Options options = new BitmapFactory.Options();
options.inBitmap = reusableBitmap;
options.inMutable = true;
Bitmap bitmap = BitmapFactory.decodeFile(path, options);
```

**修复 3：分块大 Bitmap**

```java
// 把大 Bitmap 切成小块
Bitmap[] tiles = new Bitmap[16];
int tileSize = 256;
for (int i = 0; i < 16; i++) {
    tiles[i] = Bitmap.createBitmap(tileSize, tileSize, Bitmap.Config.ARGB_8888);
}
```

**修复 4：LRU 缓存 Bitmap**

```java
public class LRUBitmapCache {
    private LinkedHashMap<String, Bitmap> cache;
    private long maxLOSUsage;
    
    public void put(String key, Bitmap bitmap) {
        long size = bitmap.getByteCount();
        while (currentLOSUsage + size > maxLOSUsage && !cache.isEmpty()) {
            Bitmap oldest = cache.values().iterator().next();
            oldest.recycle();
            cache.remove(cache.keySet().iterator().next());
            currentLOSUsage -= oldest.getByteCount();
        }
        cache.put(key, bitmap);
        currentLOSUsage += size;
    }
}
```

---

## 四、模式 3：Allocation Space 碎片化 OOM

### 3.7.11 Allocation Space 碎片化的特征

**表现**：
```
dumpsys meminfo:
  Dalvik Heap: 100 MB / 256 MB (39% 使用)
  Heap Free: 156 MB
  → 但分配 24 字节对象失败 → OOM

# 现象：总空闲足够，但特定 size class 不够
```

**根因**：RosAlloc 分桶导致单 size class 满，其他 size class 有空闲。

### 3.7.12 Allocation Space 碎片化的常见场景

**场景：短时间大量同大小对象**

```java
// 业务代码
for (int i = 0; i < 100000; i++) {
    Object obj = new Object();  // 16 字节 → size class 0 (16B Run)
    list.add(obj);
}
// → Run 0 满了 → 申请新 Run
// → 堆增长 → 接近 max_allowed_footprint → OOM
```

**场景：短时间内大量不同大小对象**

```java
// 反序列化业务
for (Data data : dataList) {
    // 假设 Data 大小变化 50-100 字节
    // → 多个 size class 都接近满
    process(data);
}
```

### 3.7.13 Allocation Space 碎片化的排查

```bash
# 1. 看 Allocation Space 详情
adb shell dumpsys meminfo -d <package> | head -30

# 2. 看 GC 日志，看 size class 分布
adb logcat -s "art" | grep "size_class\|rosalloc"
# 输出示例：
# art : size_class[0]=95% full
# art : size_class[1]=80% full
# art : size_class[2]=85% full
```

### 3.7.14 Allocation Space 碎片化的修复

**修复 1：减少同大小对象创建**

```java
// 优化前：每次循环创建大量同大小对象
for (int i = 0; i < 10000; i++) {
    Object obj = new Object();
    list.add(obj);
}

// 优化后：复用对象
Object obj = new Object();
for (int i = 0; i < 10000; i++) {
    // 复用 obj，不创建新的
}
```

**修复 2：合理使用对象池**

```java
// 对象池
public class ObjectPool<T> {
    private Stack<T> pool = new Stack<>();
    
    public T acquire() {
        return pool.isEmpty() ? create() : pool.pop();
    }
    
    public void release(T obj) {
        pool.push(obj);
    }
}
```

**修复 3：减少对象大小变化**

```java
// 优化前：Data 大小变化大
class Data {
    String title;     // 字符串
    String subtitle;  // 字符串（可能为 null）
    int[] numbers;    // 大小变化
}

// 优化后：拆分成多个固定大小对象
class DataTitle {
    String title;
}
class DataSubtitle {
    String subtitle;
}
```

---

## 五、模式 4：GC 失败后 OOM

### 3.7.15 GC 失败 OOM 的特征

**表现**：
```
art : Background concurrent copying GC freed 0(0B) AllocSpace objects
art : OutOfMemoryError: Failed to allocate a 4194304 byte allocation

# 关键：GC 释放 0 字节
```

**根因**：CMS Sweep 后碎片化，触发 GC 但释放不出可用空间。

### 3.7.16 GC 失败 OOM 的常见场景

**场景 1：碎片化严重 + GC 触发**

```java
// 业务对象持续创建 + 释放
// → 碎片化持续累积
// → 堆使用率达到 80% 触发 GC
// → GC 后总空闲足够，但分配失败
// → 触发 kGcCauseForAlloc 同步 GC
// → 同步 GC 释放 0 字节
// → OOM
```

**场景 2：垃圾对象太多**

```java
// 业务大量创建临时对象
for (int i = 0; i < 1000000; i++) {
    Object obj = new Object();
    obj = null;
}
// → 临时对象堆积
// → GC 后释放大量空间
// → 但又有新的临时对象占满
// → GC 释放 < 新创建 → 净增长 → OOM
```

### 3.7.17 GC 失败 OOM 的排查

```bash
# 1. 看 GC 日志
adb logcat -s "art" | grep "GC"
# 输出示例：
# art : Background concurrent copying GC freed 0(0B) AllocSpace objects
# art : kGcCauseForAlloc triggered GC
# art : Concurrent Mark took 100ms
# art : Remark took 50ms
# art : Concurrent Sweep freed 0 bytes  ← 关键

# 2. 看 ART Trace
# Perfetto trace 中查找 GC 事件
# 看 GC 触发原因 + 释放字节数 + STW 时间
```

### 3.7.18 GC 失败 OOM 的修复

**修复 1：减少触发 GC**

```java
// 优化前：频繁创建对象
for (int i = 0; i < 100000; i++) {
    list.add(new Object());
}

// 优化后：复用对象池
ObjectPool pool = new ObjectPool();
for (int i = 0; i < 100000; i++) {
    Object obj = pool.acquire();
    list.add(obj);
    // 后续 release
}
```

**修复 2：调整 GC 触发阈值**

```bash
# 调高 heaptargetutilization → 更激进 GC
adb shell setprop dalvik.vm.heaptargetutilization 0.6
```

**修复 3：手动触发 GC**

```java
// 在合适时机主动 GC
public void onTrimMemory(int level) {
    super.onTrimMemory(level);
    if (level >= TRIM_MEMORY_RUNNING_CRITICAL) {
        System.gc();  // 主动 GC
    }
}
```

---

## 六、模式 5：混合 OOM

### 3.7.19 混合 OOM 的特征

**表现**：
```
dumpsys meminfo:
  Dalvik Heap: 220 MB / 256 MB
  LOS: 50 MB 总空闲，全是小空洞
  Allocation Space: 单 size class 都接近满

# 多种碎片化叠加
```

**根因**：Allocation Space + LOS + RosAlloc 同时碎片化。

### 3.7.20 混合 OOM 的排查

混合 OOM 需要 **全面排查**：

```
混合 OOM 排查清单：
□ 1. 全面 hprof 分析（不仅看 LOS 大对象）
□ 2. 看 Allocation Space 的 size class 分布
□ 3. 看 GC 日志，分析 GC 效率
□ 4. 看业务代码，分析对象生命周期
□ 5. 看 Perfetto trace，分析 GC 期间业务线程行为
```

### 3.7.21 混合 OOM 的修复

**策略 1：升级到 CC GC（最有效）**

```xml
<!-- Android 8.0+ 默认 CC GC -->
<!-- 只需升级 targetSdkVersion 即可 -->
<uses-sdk android:targetSdkVersion="26" />
```

**策略 2：业务层综合优化**

```java
// 1. Bitmap 严格管理
public void onDestroy() {
    super.onDestroy();
    if (bitmap != null) bitmap.recycle();
}

// 2. 缓存使用 LRU
private LruCache<String, Bitmap> cache = new LruCache<>(MAX_SIZE);

// 3. 对象池
private ObjectPool<Object> pool = new ObjectPool<>();

// 4. 避免泄漏
// Application Context 替代 Activity Context
// WeakReference 替代强引用
```

**策略 3：Heap 参数调优**

```bash
# 调高 heaptargetutilization → 更激进 GC
adb shell setprop dalvik.vm.heaptargetutilization 0.6

# 调大 softrefthreshold → 软引用更早释放
adb shell setprop dalvik.vm.softrefthreshold 0.15
```

---

## 七、CMS 时代 OOM 的稳定性总结

### 3.7.22 CMS 时代的稳定性挑战

| 挑战 | 表现 | 严重程度 |
|:---|:---|:---|
| **碎片化 OOM** | 堆空闲但分配失败 | 高 |
| **Remark STW** | 50-100ms 卡顿 | 高 |
| **写屏障开销** | 性能损耗 5-10% | 中 |
| **GC 频率** | 每分钟 5-30 次 | 中 |
| **LOS 泄漏** | 大量 Bitmap 占内存 | 高 |

### 3.7.23 CMS 时代的优化策略

**策略 1：升级到 CC GC（最有效）**

Android 8.0+ 默认 CC GC：
- STW 从 50ms+ 降到 < 1ms
- 碎片化自动修复（Allocation Space）
- 写屏障变读屏障（更高效）

**策略 2：业务层综合优化**

- 严格管理 Bitmap 生命周期
- 使用 LRU 缓存
- 使用对象池
- 避免泄漏

**策略 3：Heap 参数调优**

- 合理设置 `heapgrowthlimit`
- 合理设置 `heaptargetutilization`
- 合理设置 `softrefthreshold`

### 3.7.24 CMS 时代的监控指标

| 指标 | 监控方式 | 告警阈值 |
|:---|:---|:---|
| GC 频率 | ART Trace | > 30/分钟 |
| Remark STW | ART Trace | > 50ms |
| LOS 占用 | dumpsys meminfo | > 50MB |
| Heap 使用率 | dumpsys meminfo | > 80% |
| Bitmap 数 | hprof | > 100 |
| Thread 数 | jstack | > 500 |

### 3.7.25 CMS 时代的工具链

**开发期**：
- LeakCanary（内存泄漏）
- Android Studio Memory Profiler（实时监控）
- StrictMode（严格模式）

**测试期**：
- dumpsys meminfo（内存信息）
- procrank（进程排名）
- Perfetto（trace 分析）

**生产期**：
- APM 工具（Matrix / Firebase / 友盟）
- 自建监控（基于 ART Trace）
- 用户反馈（卡顿 / 崩溃）

---

## 八、本节小结

1. **CMS 时代 5 大 OOM 模式**：真实 OOM / LOS 碎片化 / Allocation Space 碎片化 / GC 失败 / 混合 OOM
2. **LOS 碎片化占比最高**（30%），是 CMS 时代的主要 OOM 根因
3. **真实 OOM 最容易排查**，LOS 碎片化最隐蔽
4. **混合 OOM 最难排查**，需要综合分析
5. **升级到 CC GC 是根本解决方案**

→ **理解 5 大 OOM 模式，就掌握了 CMS 时代 OOM 的完整排查方法论**。

---

## 跨节引用

**本节被以下章节引用**：
- 09 篇诊断 —— dumpsys meminfo 的深度解读
- 04 篇 CC GC —— CMS 时代 vs CC 时代的 OOM 对比

**本节引用**：
- [2.7 慢速路径与碎片化](../02-Heap与分配器/07-慢速路径与碎片化.md) —— 碎片化的分配器视角
- [3.5 STW 时间分析](./05-STW时间分析.md) —— GC 频率与 STW 时间
- [3.6 内存碎片化](./06-内存碎片化.md) —— 碎片化的根源
