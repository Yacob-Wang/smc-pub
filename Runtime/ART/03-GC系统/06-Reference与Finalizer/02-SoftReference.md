# 6.2 SoftReference：LRU 缓存的根基

> **本节回答一个根本问题**：SoftReference 在什么时机被回收？为什么 Glide / Fresco 用 SoftReference 做 Bitmap 缓存？
>
> **答案**：**内存不足时回收** —— 软引用保留率公式 `retain_ratio = (heap_used/heap_max - threshold) / (1 - threshold)`。
>
> **理解本节，就理解了"Glide Bitmap 缓存为什么能自动释放"**。

---

## 一、SoftReference 的定义

### 6.2.1 SoftReference 的语义

```
SoftReference 语义：
  - 对象只有软引用指向时，是"软可达"
  - GC 在内存充足时保留
  - 内存不足时回收
  - "内存压力驱动"的回收策略
```

### 6.2.2 SoftReference 的回收时机

```
堆使用率 < threshold（默认 0.25）：
  - 所有软引用都被保留
  - GC 不回收软引用

堆使用率 > threshold：
  - 软引用开始被回收
  - 保留率 = f(堆使用率)
  - 使用率越高，保留率越低

堆使用率 = 100%：
  - 几乎所有软引用都被回收
  - 释放最大内存
```

### 6.2.3 软引用保留率公式

```
保留率公式：
  retain_ratio = (heap_used / heap_max - threshold) / (1 - threshold)

其中：
  heap_used：当前堆使用量
  heap_max：当前堆上限
  threshold：dalvik.vm.softrefthreshold（默认 0.25）

示例：
  heap_used = 100 MB
  heap_max = 200 MB
  threshold = 0.25
  
  heap_used / heap_max = 0.5
  retain_ratio = (0.5 - 0.25) / (1 - 0.25) = 0.33
  
  → 软引用对象有 33% 概率被保留
```

---

## 二、SoftReference 的实现

### 6.2.4 SoftReference 源码

```java
// libcore/ojluni/src/main/java/java/lang/ref/SoftReference.java
public class SoftReference<T> extends Reference<T> {
    // 静态时钟值（由 GC 维护）
    private static long clock;
    
    // 实例时间戳（对象创建时间）
    private long timestamp;
    
    public SoftReference(T referent) {
        super(referent);
        timestamp = clock;
    }
    
    public SoftReference(T referent, ReferenceQueue<? super T> q) {
        super(referent, q);
        timestamp = clock;
    }
    
    @Override
    public T get() {
        // ART 中的实现：检查时钟值
        T o = super.get();
        if (o != null && clock - timestamp > 0) {
            // 时钟值表明软引用应该被回收
            return null;
        }
        return o;
    }
}
```

### 6.2.5 ART 中软引用的处理

```cpp
// art/runtime/gc/reference_processor.cc
void ReferenceProcessor::HandleSoftReferences(...) {
    // 1. 计算保留率
    double heap_used_ratio = (double)heap_used_ / heap_max_;
    double threshold = soft_ref_threshold_;  // 默认 0.25
    double retain_ratio = (heap_used_ratio - threshold) / (1 - threshold);
    
    // 2. 遍历所有软引用
    for (SoftReference* ref : soft_references_) {
        // 3. 决定保留或回收
        if (Random() < retain_ratio) {
            // 保留
            ref->Keep();
        } else {
            // 回收（清空 referent）
            ref->Clear();
        }
    }
}
```

### 6.2.6 时钟值机制

```
ART 用时钟值（clock）控制软引用回收：

每次 GC 后：
  clock += 1

软引用 get() 时：
  if (clock - timestamp > 0):
    return null  # 对象应该被回收
  else:
    return referent  # 对象可以保留
```

**优势**：通过时钟值机制，ART 可以在多次 GC 之间渐进式回收软引用。

---

## 三、SoftReference 的工程应用

### 6.3.7 Glide Bitmap 缓存（经典场景）

```java
// Glide 的内存缓存（简化版）
public class BitmapPool {
    private final Map<String, SoftReference<Bitmap>> cache = new HashMap<>();
    
    public Bitmap get(String key) {
        SoftReference<Bitmap> ref = cache.get(key);
        if (ref != null) {
            Bitmap bitmap = ref.get();
            if (bitmap != null && !bitmap.isRecycled()) {
                return bitmap;  // 缓存命中
            }
        }
        return loadBitmap(key);  // 缓存未命中，重新加载
    }
    
    public void put(String key, Bitmap bitmap) {
        cache.put(key, new SoftReference<>(bitmap));
    }
}
```

**为什么用 SoftReference**：
- 内存充足时：缓存不回收，提升性能
- 内存不足时：自动回收，腾出内存
- 不需要手动管理缓存大小（LRU 等）

### 6.3.8 自实现的 SoftReference 缓存

```java
public class SoftCache<K, V> {
    private final LinkedHashMap<K, SoftReference<V>> map;
    
    public SoftCache(int initialCapacity) {
        // 按访问顺序排列（LRU）
        map = new LinkedHashMap<>(initialCapacity, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<K, SoftReference<V>> eldest) {
                // 自动淘汰
                return size() > SoftCache.this.maxSize;
            }
        };
    }
    
    public V get(K key) {
        SoftReference<V> ref = map.get(key);
        return ref != null ? ref.get() : null;
    }
    
    public void put(K key, V value) {
        map.put(key, new SoftReference<>(value));
    }
}
```

### 6.3.9 软引用 vs LRU 缓存

| 维度 | SoftReference | LRU 缓存 |
|:---|:---|:---|
| **回收触发** | 内存不足 | 容量满 |
| **回收粒度** | 系统级（所有软引用） | 单个缓存 |
| **可预测性** | 低（依赖系统内存压力） | 高（LRU 规则明确） |
| **性能** | 自动（无需手动管理） | 高（命中率高） |
| **适用场景** | 图片缓存 / 数据缓存 | 高频访问数据 |

**实践建议**：
- 纯图片缓存：用 Glide / Fresco（内部用 SoftReference）
- 自定义缓存：用 LruCache（更可预测）
- 关键数据：用 SoftReference + LRU 双重保护

---

## 四、软引用回收的监控

### 6.2.10 软引用数量监控

```bash
# 1. 看软引用数量
adb shell dumpsys meminfo <package> | grep "Soft"
# （ART 调试模式）

# 2. 看软引用回收事件
adb logcat -s "art" | grep "SoftReference"
# 输出示例：
# art : SoftReference cleared 1234 objects
# art : SoftReference retained 5678 objects
```

### 6.2.11 软引用配置调优

```bash
# 默认：0.25
adb shell getprop dalvik.vm.softrefthreshold
# 输出：0.25

# 调小 → 软引用更早被回收（更激进 GC）
adb shell setprop dalvik.vm.softrefthreshold 0.15

# 调大 → 软引用更晚被回收（更保守 GC）
adb shell setprop dalvik.vm.softrefthreshold 0.5
```

### 6.2.12 软引用的内存压力监控

```java
public class SoftReferenceMonitor {
    public void monitorMemoryPressure() {
        Runtime runtime = Runtime.getRuntime();
        long maxMemory = runtime.maxMemory();
        long totalMemory = runtime.totalMemory();
        long freeMemory = runtime.freeMemory();
        long usedMemory = totalMemory - freeMemory;
        
        double usageRatio = (double) usedMemory / maxMemory;
        
        if (usageRatio > 0.8) {
            // 内存压力大 → 软引用即将被回收
            Log.w(TAG, "Memory pressure high: " + usageRatio);
        }
    }
}
```

---

## 五、软引用的工程坑点

### 6.2.13 坑点 1：软引用缓存命中率低

```
场景：图片缓存命中率低
原因：内存压力大时软引用频繁被回收
解决：调小 softrefthreshold
```

### 6.2.14 坑点 2：软引用 + LRU 双重淘汰

```java
// ❌ 错误：双重淘汰可能丢失数据
private final LruCache<String, SoftReference<Bitmap>> cache = new LruCache<>(100);
// LRU 淘汰 → SoftReference.get() null → 缓存丢失

// ✅ 正确：只用一种淘汰策略
private final LruCache<String, Bitmap> cache = new LruCache<>(100);
// LRU 自动淘汰，无需 SoftReference
```

### 6.2.15 坑点 3：软引用与 Bitmap 复用

```java
// 软引用 Bitmap 复用：注意 isRecycled()
SoftReference<Bitmap> ref = cache.get(key);
Bitmap bitmap = ref.get();
if (bitmap != null && bitmap.isRecycled()) {
    // Bitmap 已被回收，从 cache 移除
    cache.remove(key);
    return null;
}
return bitmap;
```

---

## 六、软引用的源码索引

### 6.2.16 核心源码路径

```
libcore/ojluni/src/main/java/java/lang/ref/SoftReference.java  # SoftReference
libcore/ojluni/src/main/java/java/lang/ref/Reference.java     # Reference 基类
art/runtime/gc/reference_processor.h                           # ReferenceProcessor
art/runtime/gc/reference_processor.cc                          # HandleSoftReferences
```

### 6.2.17 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `ReferenceProcessor::HandleSoftReferences` | `reference_processor.cc` | 处理软引用 |
| `SoftReference::get` | `SoftReference.java` | 软引用 get |
| `SoftReference::clock` | `SoftReference.java` | 时钟值机制 |

### 6.2.18 关键常量

```cpp
// art/runtime/gc/reference_processor.h
static constexpr double kDefaultSoftRefThreshold = 0.25;
```

---

## 七、本节小结

1. **SoftReference = 内存不足时回收**：堆使用率 > threshold 时开始回收
2. **保留率公式**：`retain_ratio = (heap_used/heap_max - threshold) / (1 - threshold)`
3. **典型应用**：Glide / Fresco 的 Bitmap 缓存
4. **配置调优**：通过 `dalvik.vm.softrefthreshold` 控制
5. **工程建议**：纯图片缓存用 Glide；自定义缓存用 LruCache

→ **理解 SoftReference，就理解了"内存敏感缓存"的工程实现**。

---

## 跨节引用

**本节被以下章节引用**：
- [6.9 实战案例](./09-实战案例.md) —— 软引用配置实战
- 09 篇诊断 —— SoftReference 监控

**本节引用**：
- [6.1 可达性状态机](./01-可达性状态机.md) —— 软引用可达性
- [01 篇 1.6 Reference 体系](../01-基础理论/06-Reference体系.md) —— Reference 概览
