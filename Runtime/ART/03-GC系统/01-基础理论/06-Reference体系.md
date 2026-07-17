# 1.6 Reference 体系

> **本节回答一个根本问题**：Java 的 `SoftReference`、`WeakReference`、`PhantomReference`、`FinalReference` 在 ART 里是怎么实现的？
>
> **答案**：通过 `Reference` 基类 + `ReferenceQueue` + 多种 ReferenceProcessor 守护线程的协作。
>
> **理解本节，就理解了 LeakCanary、PhantomReference、Cleaner、finalize() 的本质**——所有内存敏感操作的基础。

---

## 一、Java 引用的可达性等级

### 1.6.1 4 种引用的对比

```java
// 1. 强引用（Strong Reference）
Object obj = new Object();   // 强引用
// 只要 obj 还在被引用，永远不回收

// 2. 软引用（SoftReference）
SoftReference<Object> soft = new SoftReference<>(new Object());
// 内存不足时回收

// 3. 弱引用（WeakReference）
WeakReference<Object> weak = new WeakReference<>(new Object());
// 下一次 GC 一定回收

// 4. 虚引用（PhantomReference）
PhantomReference<Object> phantom = new PhantomReference<>(new Object(), new ReferenceQueue<>());
// get() 永远返回 null；对象被回收后入队
```

### 1.6.2 可达性等级图

```
   GC Roots
      │
      ▼
   强引用链
      │
      ├─── SoftReference（软引用）
      │         │
      │         └─── 软引用对象
      │
      ├─── WeakReference（弱引用）
      │         │
      │         └─── 弱引用对象
      │
      ├─── PhantomReference（虚引用）
      │         │
      │         └─── 虚引用对象（get() 永远 null）
      │
      └─── FinalReference（终结引用）
                │
                └─── 终结对象（待 finalize()）
```

### 1.6.3 4 种引用的回收时机对比

| 引用类型 | 回收时机 | ART 中的处理时机 |
|:---|:---|:---|
| **强引用** | 永远不回收（除非不可达） | 不处理 |
| **SoftReference** | 内存不足时回收 | `ReferenceProcessor::HandleSoftReferences` |
| **WeakReference** | 下一次 GC 一定回收 | `ReferenceProcessor::HandleWeakReferences` |
| **PhantomReference** | 对象 finalize 后入队 | `ReferenceProcessor::HandlePhantomReferences` |
| **FinalReference** | finalize() 执行时 | `FinalizerDaemon::Run` |

---

## 二、ART Reference 源码入口

### 1.6.4 Java 层 Reference 体系

```
libcore/ojluni/src/main/java/java/lang/ref/
├── Reference.java          # 基类（含 ReferenceQueue）
├── SoftReference.java      # 软引用
├── WeakReference.java      # 弱引用
├── PhantomReference.java   # 虚引用
├── FinalReference.java     # finalizer 专用
└── FinalizerReference.java # finalizer 注册的引用

libcore/libart/src/main/java/java/lang/
├── Daemons.java            # FinalizerDaemon / ReferenceQueueDaemon
└── ref/
    ├── Cleaner.java        # JDK 8 引入的轻量析构
    └── PhantomCleanable.java
```

### 1.6.5 Reference 基类源码

```java
// libcore/ojluni/src/main/java/java/lang/ref/Reference.java
public abstract class Reference<T> {
    // 内部字段
    private T referent;         // 引用的对象
    private ReferenceQueue<? super T> queue;  // 关联的 ReferenceQueue
    private Reference next;     // 链表下一个 Reference
    
    // 关键方法
    public T get() {
        return referent;  // 软/弱引用返回 referent；虚引用返回 null
    }
    
    public void clear() {
        // 清空 referent，让 GC 能回收对象
        synchronized (this) {
            if (referent != null) {
                referent = null;
                // 通知 ReferenceProcessor
            }
        }
    }
    
    public boolean enqueue() {
        // 把 Reference 加入 ReferenceQueue（由 GC 或业务线程触发）
        return queue.enqueue(this);
    }
}
```

### 1.6.6 SoftReference 源码

```java
// libcore/ojluni/src/main/java/java/lang/ref/SoftReference.java
public class SoftReference<T> extends Reference<T> {
    // 软引用的"时钟值"，由 GC 维护
    private static long clock;
    
    public SoftReference(T referent) {
        super(referent);
    }
    
    public SoftReference(T referent, ReferenceQueue<? super T> q) {
        super(referent, q);
    }
    
    @Override
    public T get() {
        // ART 中的实现：检查时钟值，决定是否返回
        T o = super.get();
        if (o != null && clock - timestamp > ...) {
            // 时钟值表明软引用应该被回收
            return null;
        }
        return o;
    }
}
```

---

## 三、Reference 在 ART 中的处理

### 1.6.7 ReferenceProcessor 总览

```cpp
// art/runtime/gc/reference_processor.h
class ReferenceProcessor {
 public:
  // GC 阶段入口
  void ProcessReferences(...) {
    // 1. 处理软引用
    HandleSoftReferences(...);
    
    // 2. 处理弱引用
    HandleWeakReferences(...);
    
    // 3. 处理 Final 引用
    HandleFinalReferences(...);
    
    // 4. 处理虚引用
    HandlePhantomReferences(...);
  }
  
 private:
  // 软引用保留率 = (heap_used / heap_max - threshold) / (1 - threshold)
  // 当 heap_used > heap_max * threshold 时，软引用开始被回收
  void HandleSoftReferences(...) {
    if (heap_used_ratio_ > soft_ref_threshold_) {
      // 清空软引用的 referent
      ClearSoftReferences();
    }
  }
  
  // 弱引用全部入队
  void HandleWeakReferences(...) {
    EnqueuePendingReferences(weak_references_);
  }
  
  // FinalReference 加入 FinalizerDaemon 的队列
  void HandleFinalReferences(...) {
    EnqueueFinalReferences();
  }
  
  // 虚引用 finalize 后入队
  void HandlePhantomReferences(...) {
    EnqueuePendingReferences(phantom_references_);
  }
};
```

### 1.6.8 Reference 的 pending list

ART 维护一个 **pending list**（待处理 Reference 链表）：

```cpp
// art/runtime/gc/reference_processor.cc
void ReferenceProcessor::EnqueuePendingReferences(...) {
  // 1. 找到 pending list 里的所有 Reference
  for (Reference* ref : pending_list_) {
    // 2. 把 Reference 加入对应的 ReferenceQueue
    ReferenceQueue* queue = ref->queue_;
    if (queue != nullptr) {
      queue->enqueue(ref);
    }
    
    // 3. 标记为已处理
    ref->enqueued_ = true;
  }
  
  // 4. 清空 pending list
  pending_list_.clear();
}
```

### 1.6.9 ReferenceQueue 的实现

```java
// libcore/ojluni/src/main/java/java/lang/ref/ReferenceQueue.java
public class ReferenceQueue<T> {
    // 内部链表
    private Reference<? extends T> head;
    
    // 入队（GC 或 FinalizerDaemon 调用）
    boolean enqueue(Reference<? extends T> r) {
        synchronized (this) {
            r.queue = this;  // 反向引用
            r.next = head;
            head = r;
            return true;
        }
    }
    
    // 出队（业务线程调用）
    public Reference<? extends T> poll() {
        synchronized (this) {
            if (head == null) {
                return null;
            }
            Reference<? extends T> r = head;
            head = head.next;
            r.next = null;
            return r;
        }
    }
    
    // 阻塞出队（业务线程调用）
    public Reference<? extends T> remove(long timeout) throws InterruptedException {
        // ... 等待直到有 Reference 入队
    }
}
```

---

## 四、4 种引用的实战应用

### 1.6.10 SoftReference：内存敏感缓存

**典型场景**：Glide / Fresco 的 Bitmap 缓存

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

**ART 中的回收时机**：
- `dalvik.vm.softrefthreshold` 参数决定软引用何时开始被回收
- 默认值 = 0.25（heap 使用率超过 25% 后开始考虑软回收）

### 1.6.11 WeakReference：WeakHashMap 与泄漏检测

**WeakHashMap 的实现**：

```java
// libcore/ojluni/src/main/java/java/util/WeakHashMap.java
public class WeakHashMap<K, V> extends AbstractMap<K, V> implements Map<K, V> {
    // 用 WeakReference 包装 key
    Entry<K, V>[] table;
    
    static class Entry<K, V> extends WeakReference<K> implements Map.Entry<K, V> {
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
    
    // 每次操作都清理已被 GC 回收的 key
    private void expungeStaleEntries() {
        Reference<? extends K> ref;
        while ((ref = queue.poll()) != null) {
            Entry<K, V> entry = (Entry<K, V>) ref;
            // 从 table 中删除 entry
            removeMapping(entry);
        }
    }
}
```

**为什么 value 可能内存泄漏**：
- **key 是 WeakReference**：GC 后 key 会被回收
- **value 是强引用**：但 value 还在 Entry 里，Entry 还被 queue 引用
- **要等 expungeStaleEntries() 调用时，value 才会被清理**

→ **WeakHashMap 的 value 仍可能内存泄漏**，必须正确使用。

### 1.6.12 PhantomReference 与 Cleaner

**Cleaner 的本质**：PhantomReference + ReferenceQueue + 守护线程

```java
// libcore/libart/src/main/java/jdk/internal/ref/Cleaner.java
public class Cleaner extends PhantomReference<Object> {
    // 静态的 dummy queue
    private static final ReferenceQueue<Object> dummyQueue = new ReferenceQueue<>();
    
    // Cleaner 链表（双向）
    private Cleaner next = null;
    private Cleaner prev = null;
    
    // 要执行的清理逻辑
    private final Runnable thunk;
    
    private Cleaner(Object referent, Runnable thunk) {
        super(referent, dummyQueue);
        this.thunk = thunk;
    }
    
    // 创建 Cleaner
    public static Cleaner create(Object referent, Runnable thunk) {
        if (thunk == null) return null;
        return new Cleaner(referent, thunk);
    }
    
    // 执行清理逻辑（由 ReferenceQueueDaemon 调用）
    public void clean() {
        if (!remove(this)) return;
        try {
            thunk.run();  // 释放 native 内存
        } catch (Throwable t) {
            // ...
        }
    }
}
```

**DirectByteBuffer 释放 native 内存**：

```java
// DirectByteBuffer 的清理逻辑
public class DirectByteBuffer extends MappedByteBuffer implements DirectBuffer {
    Cleaner cleaner;
    
    DirectByteBuffer(long addr, int cap) {
        super(-1, 0, cap, cap, null);
        this.address = addr;
        this.cleaner = Cleaner.create(this, new Deallocator(addr, cap));
    }
    
    // 当 DirectByteBuffer 被 GC 回收时
    // → Cleaner 触发 Deallocator.run()
    // → 释放 native 内存
    private static class Deallocator implements Runnable {
        private long address;
        private int capacity;
        
        Deallocator(long address, int capacity) {
            this.address = address;
            this.capacity = capacity;
        }
        
        public void run() {
            if (address == 0) return;
            // 释放 native 内存
            unsafe.freeMemory(address);
            address = 0;
        }
    }
}
```

**DirectByteBuffer 的 native 内存回收链路**：
1. Java 堆 DirectByteBuffer 对象 → 被 GC 回收
2. PhantomReference → 加入 ReferenceQueue
3. ReferenceQueueDaemon → 调用 Cleaner.clean()
4. Cleaner.clean() → 执行 Deallocator.run()
5. Deallocator.run() → unsafe.freeMemory() 释放 native 内存

→ **理解 PhantomReference，就理解 DirectByteBuffer 的 native 内存释放机制**。

### 1.6.13 FinalReference 与 finalize()

**finalize() 的本质**：

```java
// 任何重写 finalize() 的类，JVM 都会创建一个 FinalReference
public class Resource {
    @Override
    protected void finalize() throws Throwable {
        try {
            // 释放资源
            release();
        } finally {
            super.finalize();
        }
    }
}

// 内部机制：
// 1. Resource 对象被 GC 判定为不可达
// 2. ART 创建 FinalReference 指向 Resource
// 3. FinalReference 加入 pending list
// 4. ReferenceProcessor::HandleFinalReferences 把 FinalReference 加入 FinalizerDaemon 的队列
// 5. FinalizerDaemon 线程执行 Resource.finalize()
// 6. FinalizerWatchdogDaemon 监控 finalize() 是否超时（默认 10 秒）
```

**finalize() 的问题**（详见 06 篇）：
- 性能差（每个对象都要 FinalizerDaemon 处理）
- 不确定性（finalize() 何时执行不可控）
- 可能阻塞（finalize() 阻塞导致队列堆积）
- 已被 JDK 9+ 标记为 **Deprecated**

**06 篇详细讲**：FinalizerDaemon + FinalizerWatchdogDaemon 的源码深潜 + 完整案例。

---

## 五、Reference 与 LeakCanary

### 1.6.14 LeakCanary 的工作原理

```java
// LeakCanary 的核心逻辑（简化版）
public class LeakCanary {
    public static void watch(Object watchedObject, String description) {
        // 1. 创建 KeyedWeakReference
        KeyedWeakReference ref = new KeyedWeakReference(watchedObject);
        
        // 2. 5 秒后检查
        Handler.postDelayed(() -> {
            // 3. 手动触发 GC
            Runtime.getRuntime().gc();
            Thread.sleep(100);  // 等 GC 完成
            
            // 4. 检查 WeakReference.get()
            if (ref.get() != null) {
                // 5. 还非 null → 泄漏！
                // 6. 触发 Heap Dump
                File heapDump = HeapDumper.dumpHeap();
                
                // 7. 用 Shark 库分析 hprof 文件
                HeapAnalysisResult result = SharkAnalyzer.analyze(heapDump);
                
                // 8. 找出泄漏路径
                Log.e("LeakCanary", "Leak found: " + result.leakTrace);
            }
        }, 5000);
    }
    
    private static class KeyedWeakReference extends WeakReference<Object> {
        private final String key;
        
        KeyedWeakReference(Object referent) {
            super(referent);
            this.key = UUID.randomUUID().toString();
        }
    }
}
```

**LeakCanary 的关键设计**：
- 用 **WeakReference** 包裹要监控的对象
- 触发 GC 后检查 **WeakReference.get()**
- 如果还非 null → **泄漏**
- 触发 Heap Dump + 分析泄漏路径

→ **不理解 WeakReference，就不懂 LeakCanary**。

---

## 六、Reference 与 ART 守护线程

### 1.6.15 ART 的 Reference 守护线程

```cpp
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    // 1. FinalizerDaemon：处理 finalize()
    private static class FinalizerDaemon extends Daemon {
        @Override
        public void run() {
            while (isRunning()) {
                // 从 FinalReferenceQueue 取出 Reference
                FinalizerReference<?> ref = (FinalizerReference<?>) queue.remove();
                if (ref != null) {
                    // 执行 finalize()
                    finalizeReference(ref);
                }
            }
        }
    }
    
    // 2. FinalizerWatchdogDaemon：监控 finalize() 是否超时
    private static class FinalizerWatchdogDaemon extends Daemon {
        @Override
        public void run() {
            while (isRunning()) {
                // 检查 finalize() 是否超过 10 秒
                // 如果超时，记录警告
                checkFinalizerTimeouts();
            }
        }
    }
    
    // 3. ReferenceQueueDaemon：处理 ReferenceQueue
    private static class ReferenceQueueDaemon extends Daemon {
        @Override
        public void run() {
            while (isRunning()) {
                // 处理 ReferenceQueue 里的软/弱/虚引用
                Reference<? extends Object> ref;
                while ((ref = queue.poll()) != null) {
                    cleanupReference(ref);
                }
            }
        }
    }
}
```

### 1.6.16 守护线程的协作时序图

```
业务线程                    FinalizerDaemon           GC 线程
   │                              │                    │
   │  Object obj = new Object()   │                    │
   │  obj = null                  │                    │
   │                              │                    │
   │                              │      GC 开始       │
   │                              │ ◄────────────────── │
   │                              │                    │
   │                              │ 1. 处理 FinalRef   │
   │                              │ 加入 pending list  │
   │                              │                    │
   │                              │ 2. 加入 FinalizerDaemon 队列
   │                              │                    │
   │                              │ 3. GC 完成         │
   │                              │ ──────────────────►│
   │                              │                    │
   │                              │ 4. 执行 finalize()│
   │                              │                    │
   │                              │ 5. 清理           │
   │                              ▼                    │
```

---

## 七、稳定性排查实战

### 1.6.17 案例 1：WeakHashMap 的 value 内存泄漏

**场景**：
```java
public class Cache {
    // 用 WeakHashMap 做缓存
    private Map<String, Object> cache = new WeakHashMap<>();
    
    public void put(String key, Object value) {
        cache.put(key, value);
    }
}

// 业务代码
Cache cache = new Cache();
String key = "key1";  // 局部变量，强引用
Object value = new Object();
cache.put(key, value);

key = null;  // 释放 key 的强引用
// 此时 key 在 WeakHashMap 里是弱引用 → 下次 GC 后 key 被回收
// 但 value 是强引用 → 仍被 Entry 引用
// → Entry 还被 queue 引用 → value 泄漏
```

**修复**：
```java
// 1. 手动清理
public void clear() {
    cache.clear();
}

// 2. 改用 LRU 缓存
private LruCache<String, Object> cache = new LruCache<>(100);

// 3. 改用 ConcurrentHashMap + 手动管理
private Map<String, Object> cache = new ConcurrentHashMap<>();
```

### 1.6.18 案例 2：finalize() 阻塞导致 OOM

**场景**：
```java
public class HeavyResource {
    private FileInputStream fis;
    
    @Override
    protected void finalize() throws Throwable {
        // 假设这里阻塞（如等待锁）
        fis.close();  // 阻塞 10 秒
        super.finalize();
    }
}

// 创建大量 HeavyResource
List<HeavyResource> list = new ArrayList<>();
for (int i = 0; i < 10000; i++) {
    list.add(new HeavyResource());
}
list = null;  // 释放引用

// GC 时：FinalizerDaemon 一个个调用 finalize()
// 但每个 finalize() 阻塞 10 秒
// 10 × 10000 = 10 万秒 → 永远处理不完
// → OOM
```

**修复**：
- 完全禁止 finalize()，改用 PhantomReference + Cleaner
- 或改用 try-with-resources + AutoCloseable

```java
public class HeavyResource implements AutoCloseable {
    private FileInputStream fis;
    
    @Override
    public void close() throws IOException {
        fis.close();  // 显式关闭，不依赖 finalize()
    }
}

// 使用
try (HeavyResource res = new HeavyResource()) {
    // 业务逻辑
}
```

### 1.6.19 案例 3：DirectByteBuffer 内存泄漏

**场景**：
```java
// 创建大量 DirectByteBuffer，分配 native 内存
List<ByteBuffer> buffers = new ArrayList<>();
for (int i = 0; i < 100000; i++) {
    buffers.add(ByteBuffer.allocateDirect(1024 * 1024));  // 1 MB × 100000 = 100 GB
}
buffers = null;  // 释放引用

// 期望：GC 回收 DirectByteBuffer → Cleaner 释放 native 内存
// 实际：native 内存持续增长 → OOM
```

**根因**：
- DirectByteBuffer 被 GC 回收了
- 但 Cleaner 的清理逻辑还没执行（ReferenceQueueDaemon 处理慢）
- 或者 ReferenceQueue 被业务线程的 remove() 阻塞

**修复**：
- 业务代码用 `DirectByteBuffer` 的 `cleaner().clean()` 手动释放
- 或用池化技术复用 DirectByteBuffer

---

## 八、ART Reference 的源码索引

### 1.6.20 核心源码路径

```
libcore/ojluni/src/main/java/java/lang/ref/Reference.java          # Reference 基类
libcore/ojluni/src/main/java/java/lang/ref/SoftReference.java     # SoftReference
libcore/ojluni/src/main/java/java/lang/ref/WeakReference.java     # WeakReference
libcore/ojluni/src/main/java/java/lang/ref/PhantomReference.java  # PhantomReference
libcore/ojluni/src/main/java/java/lang/ref/FinalReference.java    # FinalReference
libcore/ojluni/src/main/java/java/lang/ref/ReferenceQueue.java    # ReferenceQueue

libcore/libart/src/main/java/java/lang/Daemons.java               # Daemon 线程
libcore/libart/src/main/java/jdk/internal/ref/Cleaner.java        # Cleaner
libcore/libart/src/main/java/jdk/internal/ref/PhantomCleanable.java

art/runtime/gc/reference_processor.h                              # ART ReferenceProcessor
art/runtime/gc/reference_processor.cc                             # Reference 处理实现
```

---

## 九、本节小结

1. **4 种引用类型**：强/软/弱/虚，回收时机不同
2. **ART Reference 体系**：Reference 基类 + ReferenceQueue + ReferenceProcessor + 守护线程
3. **软引用 = 内存敏感缓存**（Glide Bitmap 缓存）
4. **弱引用 = 弱缓存 / 泄漏检测**（WeakHashMap / LeakCanary）
5. **虚引用 + Cleaner = 真正的析构**（DirectByteBuffer native 内存释放）
6. **finalize() = 终结引用 + FinalizerDaemon**（06 篇详细讲）

→ **理解 Reference 体系，就理解了 LeakCanary / Cleaner / DirectByteBuffer / finalize() 的本质**。

---

## 06 篇预告

**06-Reference 与 Finalizer**——专门深潜 Reference 体系和 FinalizerDaemon：

- SoftReference 的软回收阈值（`dalvik.vm.softrefthreshold`）
- WeakHashMap 的实现细节 + value 内存泄漏分析
- PhantomReference 与 Cleaner 的源码深潜
- FinalizerDaemon / FinalizerWatchdogDaemon 的源码
- finalize() 链式阻塞的完整分析（升级版 ART-05 案例 2）
- 治理方案：完全禁止 finalize()
