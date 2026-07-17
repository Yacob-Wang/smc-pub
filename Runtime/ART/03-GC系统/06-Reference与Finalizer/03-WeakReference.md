# 6.3 WeakReference：WeakHashMap 与内存泄漏排查

> **本节回答一个根本问题**：WeakReference 的回收时机是什么？WeakHashMap 为什么能"自动清理"？为什么 LeakCanary 用 WeakReference 检测泄漏？
>
> **答案**：**下次 GC 一定回收** —— 不管内存压力如何。
>
> **理解本节，就理解了 LeakCanary / WeakHashMap / 内存泄漏检测的本质**。

---

## 一、WeakReference 的语义

### 6.3.1 WeakReference 的定义

```
WeakReference 语义：
  - 对象只有弱引用指向时，是"弱可达"
  - 下一次 GC 一定回收（无论内存是否充足）
  - 比 SoftReference 更激进的回收策略
```

### 6.3.2 WeakReference 与 SoftReference 的对比

| 维度 | SoftReference | WeakReference |
|:---|:---|:---|
| **回收时机** | 内存不足时 | 下次 GC 一定 |
| **激进度** | 保守 | 激进 |
| **典型用途** | 内存敏感缓存 | WeakHashMap、LeakCanary |
| **命中率高** | 高（保留更多） | 低（更早回收） |

### 6.3.3 WeakReference 的回收时机

```
每次 GC：
  1. 标记所有存活对象
  2. 对于只有弱引用指向的对象
     → 直接加入 pending list
     → 入队到 ReferenceQueue
     → 清空 referent
  3. 下次 GC 后
     → weak.get() 返回 null
```

---

## 二、WeakReference 的实现

### 6.3.4 WeakReference 源码

```java
// libcore/ojluni/src/main/java/java/lang/ref/WeakReference.java
public class WeakReference<T> extends Reference<T> {
    public WeakReference(T referent) {
        super(referent);
    }
    
    public WeakReference(T referent, ReferenceQueue<? super T> q) {
        super(referent, q);
    }
    
    // WeakReference 没有重写 get()
    // 直接继承 Reference.get()，返回 referent
    // 但 GC 会清空 referent
}
```

### 6.3.5 ART 中弱引用的处理

```cpp
// art/runtime/gc/reference_processor.cc
void ReferenceProcessor::HandleWeakReferences(...) {
    // 1. 遍历所有弱引用
    for (WeakReference* ref : weak_references_) {
        // 2. 检查对象是否被标记（存活）
        if (!IsMarked(ref->referent_)) {
            // 3. 未被标记 → 入队
            ref->pending_next_ = pending_head_;
            pending_head_ = ref;
        }
    }
}
```

### 6.3.6 弱引用的不可达性判定

```
判断对象是否"只弱可达"：

1. GC 标记阶段：
   - 从 GC Roots 出发
   - 标记所有可达对象
   - 对象 X 如果被标记 → 强可达或软可达

2. 对象 X 如果没被标记：
   - 但 X 还有弱引用指向 → 弱可达
   - 弱可达对象在 GC 后被回收

3. 例外：
   - 如果 X 还被软引用指向 → 软可达（不回收）
   - 如果 X 还被强引用指向 → 强可达（不回收）
```

---

## 三、WeakHashMap 的实现

### 6.3.7 WeakHashMap 的核心思想

```
WeakHashMap：
  - key 是 WeakReference
  - value 是普通强引用
  - 当 key 被 GC 回收时，entry 也失效
  - 下次访问 map 时清理失效 entry
```

### 6.3.8 WeakHashMap 源码

```java
// libcore/ojluni/src/main/java/java/util/WeakHashMap.java
public class WeakHashMap<K, V> extends AbstractMap<K, V> implements Map<K, V> {
    // 内部 Entry：key 是 WeakReference
    private static class Entry<K, V> extends WeakReference<K> implements Map.Entry<K, V> {
        V value;
        int hash;
        Entry<K, V> next;
        
        Entry(K key, V value, ReferenceQueue<K> queue, int hash, Entry<K, V> next) {
            super(key, queue);  // key 是弱引用
            this.value = value;
            this.hash = hash;
            this.next = next;
        }
    }
    
    // ReferenceQueue：key 被 GC 回收时入队
    private final ReferenceQueue<K> queue = new ReferenceQueue<>();
    
    // 每次操作前清理失效 entry
    private void expungeStaleEntries() {
        Reference<? extends K> ref;
        while ((ref = queue.poll()) != null) {
            Entry<K, V> entry = (Entry<K, V>) ref;
            // 从 table 中删除 entry
            removeMapping(entry);
        }
    }
    
    public V get(Object key) {
        // 1. 清理失效 entry
        expungeStaleEntries();
        
        // 2. 查找 key
        // ...
    }
    
    public V put(K key, V value) {
        // 1. 清理失效 entry
        expungeStaleEntries();
        
        // 2. 插入 key-value
        // ...
    }
}
```

### 6.3.9 WeakHashMap 的 value 内存泄漏问题

```
WeakHashMap 的内存泄漏陷阱：

Map<String, Bitmap> map = new WeakHashMap<>();
map.put("key1", bitmap);
// ↑ bitmap 在 value 字段
//   Entry 持有 bitmap（强引用）
//   即使 key 被 GC 回收
//   bitmap 仍被 Entry 强引用

map.put("key2", bitmap2);
// ↑ bitmap2 类似

// 1 小时后：
// - 所有 key 被 GC 回收（弱引用失效）
// - 但 value（bitmap）仍被 Entry 强引用
// - map 仍然占用大量内存（bitmap）
// - 只有调用 expungeStaleEntries() 时才清理
// - 如果不调用 → value 一直泄漏
```

### 6.3.10 WeakHashMap 的工程使用

**场景 1：作为缓存**

```java
// ✅ 正确：用 LruCache（更可预测）
private final LruCache<String, Bitmap> cache = new LruCache<>(100);

// ❌ 错误：用 WeakHashMap（value 可能泄漏）
private final Map<String, Bitmap> cache = new WeakHashMap<>();
```

**场景 2：作为弱缓存**

```java
// ✅ 正确：手动管理（避免 value 泄漏）
public class WeakCache<K, V> {
    private final Map<K, WeakReference<V>> cache = new HashMap<>();
    private final ReferenceQueue<V> queue = new ReferenceQueue<>();
    
    public V get(K key) {
        // 清理失效
        cleanup();
        
        WeakReference<V> ref = cache.get(key);
        return ref != null ? ref.get() : null;
    }
    
    public void put(K key, V value) {
        cleanup();
        cache.put(key, new WeakReference<>(value, queue));
    }
    
    private void cleanup() {
        Reference<? extends V> ref;
        while ((ref = queue.poll()) != null) {
            // 找到对应的 key 并删除
            // ...
        }
    }
}
```

---

## 四、LeakCanary 的实现原理

### 6.3.11 LeakCanary 的工作流程

```
LeakCanary 检测内存泄漏：

1. 在 Application.onCreate() 中初始化
2. 注册 ActivityLifecycleCallbacks
3. 在 Activity.onDestroy() 后：
   - 创建一个 KeyedWeakReference 包裹 Activity
   - 5 秒后手动触发 GC
   - 检查 KeyedWeakReference.get()
   - 如果还非 null → 内存泄漏
4. 触发 Heap Dump
5. 用 Shark 库分析 hprof 文件
6. 找出泄漏链（GC Root → 泄漏对象）
```

### 6.3.12 LeakCanary 核心代码

```java
// LeakCanary 核心（简化版）
public class LeakCanary {
    public static void watch(Object watchedObject) {
        // 1. 创建 KeyedWeakReference
        String key = UUID.randomUUID().toString();
        KeyedWeakReference ref = new KeyedWeakReference(watchedObject, key);
        
        // 2. 5 秒后检查
        Handler.postDelayed(() -> {
            // 3. 手动触发 GC
            Runtime.getRuntime().gc();
            Thread.sleep(100);
            
            // 4. 检查是否泄漏
            if (ref.get() != null) {
                // 5. 触发 Heap Dump
                File hprof = HeapDumper.dumpHeap();
                
                // 6. 分析 hprof
                HeapAnalysisResult result = SharkAnalyzer.analyze(hprof);
                
                // 7. 找出泄漏链
                Log.e("LeakCanary", "Leak: " + result.leakTrace);
            }
        }, 5000);
    }
    
    private static class KeyedWeakReference extends WeakReference<Object> {
        private final String key;
        
        KeyedWeakReference(Object referent, String key) {
            super(referent);
            this.key = key;
        }
    }
}
```

### 6.3.13 LeakCanary 用 WeakReference 的原因

```
为什么用 WeakReference 而不是 SoftReference？

WeakReference：
  - 下次 GC 一定回收
  - 5 秒后手动 GC → 立即回收
  - 如果还非 null → 100% 是泄漏

SoftReference：
  - 内存不足时回收
  - 5 秒后内存可能充足 → 不回收
  - 即使泄漏也可能 SoftReference.get() 非 null（被 GC 保护）

→ WeakReference 更适合"检测泄漏"的场景
```

### 6.3.14 LeakCanary v2 的改进（Shark 引擎）

```
LeakCanary 1.x：
  - 基于 Heap Dump + MAT 分析
  - 慢（生成 hprof 慢，分析慢）
  - 内存占用大

LeakCanary 2.x：
  - 用 Shark 引擎（自定义 hprof 解析）
  - 快（解析比 MAT 快 10 倍）
  - 内存占用小
  - 支持 Android 11+ 的 Heap Dump API（无需 hprof 文件）
```

---

## 五、WeakReference 的工程应用

### 6.3.15 弱引用的典型场景

| 场景 | 是否用 WeakReference | 原因 |
|:---|:---|:---|
| 图片缓存 | ❌ 否 | 用 Glide / LruCache |
| 数据缓存 | ❌ 否 | 用 LruCache |
| Activity 泄漏检测 | ✅ 是 | LeakCanary |
| WeakHashMap | ⚠️ 慎用 | value 容易泄漏 |
| ThreadLocal 清理 | ✅ 是 | 防止 key 泄漏 |

### 6.3.16 WeakReference 在 Handler 中的应用

```java
// 问题：Handler 默认持有外部 Activity（内存泄漏）
public class LeakyHandler extends Handler {
    private final Activity activity;
    
    public LeakyHandler(Activity activity) {
        this.activity = activity;
    }
    
    @Override
    public void handleMessage(Message msg) {
        // activity 被 Handler 强引用 → 内存泄漏
    }
}

// ✅ 修复：用 WeakReference
public class SafeHandler extends Handler {
    private final WeakReference<Activity> activityRef;
    
    public SafeHandler(Activity activity) {
        activityRef = new WeakReference<>(activity);
    }
    
    @Override
    public void handleMessage(Message msg) {
        Activity activity = activityRef.get();
        if (activity != null && !activity.isFinishing()) {
            // 处理消息
        }
    }
}
```

### 6.3.17 弱引用的监控

```bash
# 1. 看弱引用数量
adb shell dumpsys meminfo <package> | grep "Weak"

# 2. 看弱引用清理事件
adb logcat -s "art" | grep "WeakReference"
# 输出示例：
# art : WeakReference cleared 1234 objects
```

---

## 六、WeakReference 的源码索引

### 6.3.18 核心源码路径

```
libcore/ojluni/src/main/java/java/lang/ref/WeakReference.java   # WeakReference
libcore/ojluni/src/main/java/java/util/WeakHashMap.java         # WeakHashMap
libcore/ojluni/src/main/java/java/lang/ref/Reference.java       # Reference 基类
art/runtime/gc/reference_processor.h                             # ReferenceProcessor
art/runtime/gc/reference_processor.cc                            # HandleWeakReferences
```

### 6.3.19 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `ReferenceProcessor::HandleWeakReferences` | `reference_processor.cc` | 处理弱引用 |
| `WeakReference::get` | `WeakReference.java` | 弱引用 get |
| `WeakHashMap::expungeStaleEntries` | `WeakHashMap.java` | 清理失效 entry |

---

## 七、本节小结

1. **WeakReference = 下次 GC 一定回收**：无论内存压力
2. **WeakHashMap 价值内存泄漏**：value 强引用 → Entry 持有
3. **LeakCanary 用 WeakReference 检测泄漏**：5 秒后 GC + 检查
4. **业务建议**：图片缓存用 Glide，泄漏检测用 WeakReference
5. **WeakHashMap 慎用**：value 容易泄漏

→ **理解 WeakReference，就理解了 LeakCanary 和内存泄漏检测的本质**。

---

## 跨节引用

**本节被以下章节引用**：
- [6.9 实战案例](./09-实战案例.md) —— 内存泄漏实战
- 09 篇诊断 —— LeakCanary 完整使用

**本节引用**：
- [6.1 可达性状态机](./01-可达性状态机.md) —— 弱引用可达性
- [01 篇 1.6 Reference 体系](../01-基础理论/06-Reference体系.md) —— Reference 概览
