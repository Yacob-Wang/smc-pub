# 6.5 PhantomReference：真正的析构语义

> **本节回答一个根本问题**：PhantomReference 与 WeakReference 有什么区别？为什么 PhantomReference 是"真正的析构"？
>
> **答案**：**get() 永远返回 null + 对象被回收后才入队** —— PhantomReference 是最纯粹的"对象回收通知"。
>
> **理解本节，就理解了 Cleaner 和 DirectByteBuffer 释放 native 内存的本质**。

---

## 一、PhantomReference 的语义

### 6.5.1 PhantomReference 的定义

```
PhantomReference 语义：
  - 对象只有虚引用指向时，是"虚可达"
  - get() 永远返回 null
  - 对象被回收后才入队到 ReferenceQueue
  - 用于"对象回收后"的清理操作（如释放 native 内存）
```

### 6.5.2 PhantomReference 与 WeakReference 的对比

| 维度 | WeakReference | PhantomReference |
|:---|:---|:---|
| **get()** | 可能返回 referent | **永远返回 null** |
| **回收时机** | 下次 GC 回收 | finalize 后回收 |
| **入队时机** | GC 标记后入队 | GC 真正回收后入队 |
| **复活** | 可以（finalize 中建立强引用） | **不能** |
| **典型用途** | WeakHashMap、LeakCanary | Cleaner（资源清理） |

### 6.5.3 PhantomReference 的"复活"问题

```
WeakReference 的问题：

1. 对象不可达
2. WeakReference 阻止对象被回收
3. 但如果 finalize() 中建立强引用
4. → 对象被"复活"
5. → WeakReference.get() 重新非 null
6. → 不符合"对象应该被回收"的语义

PhantomReference 的解决：

1. 对象不可达
2. PhantomReference 不阻止对象被回收
3. 即使 finalize() 中建立强引用
4. → 对象已经被回收
5. → PhantomReference.get() 永远 null
6. → 符合"析构"的语义
```

---

## 二、PhantomReference 的实现

### 6.5.4 PhantomReference 源码

```java
// libcore/ojluni/src/main/java/java/lang/ref/PhantomReference.java
public class PhantomReference<T> extends Reference<T> {
    public PhantomReference(T referent, ReferenceQueue<? super T> q) {
        super(referent, q);
    }
    
    @Override
    public T get() {
        return null;  // 永远返回 null
    }
}
```

### 6.5.5 ART 中 PhantomReference 的处理

```cpp
// art/runtime/gc/reference_processor.cc
void ReferenceProcessor::HandlePhantomReferences(...) {
    // 1. 收集所有 PhantomReference
    PhantomReferenceList phantom_refs = CollectPhantomReferences();
    
    // 2. 遍历
    for (PhantomReference* ref : phantom_refs) {
        // 3. 检查 referent 是否被回收
        if (!IsMarked(ref->referent_)) {
            // 4. 已回收 → 入队
            ref->pending_next_ = pending_head_;
            pending_head_ = ref;
        }
    }
}
```

### 6.5.6 PhantomReference 的不可达性

```
PhantomReference 的特殊语义：

1. 对象不可达（被 GC 判定）
2. finalize() 已执行（如果重写了）
3. ART 回收对象内存
4. PhantomReference 入队到 ReferenceQueue
5. 业务线程 poll() → 知道对象已回收

注意：
  - PhantomReference.get() 永远返回 null
  - 即使对象还没真正被 GC 回收
  - → 业务线程无法访问 referent
  - → 必须通过其他方式持有 native 资源引用
```

---

## 三、Cleaner 的实现

### 6.5.7 Cleaner 的本质

```
Cleaner = PhantomReference + ReferenceQueue + Runnable

工作机制：
1. 创建 Cleaner 时，关联一个 Runnable（清理逻辑）
2. Cleaner 内部包装一个 PhantomReference
3. 当关联的对象被 GC 回收时
4. Cleaner 的 PhantomReference 入队
5. ReferenceQueueDaemon 触发 Cleaner.clean()
6. Runnable.run() 执行清理逻辑
```

### 6.5.8 Cleaner 源码

```java
// libcore/libart/src/main/java/jdk/internal/ref/Cleaner.java
public class Cleaner extends PhantomReference<Object> {
    // 静态 dummy queue
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

### 6.5.9 DirectByteBuffer 的 native 内存释放

```java
// libcore/ojluni/src/main/java/java/nio/DirectByteBuffer.java
public class DirectByteBuffer extends MappedByteBuffer implements DirectBuffer {
    private final long address;  // native 内存地址
    private final Cleaner cleaner;
    
    DirectByteBuffer(long addr, int cap) {
        super(-1, 0, cap, cap, null);
        this.address = addr;
        // 创建 Cleaner，关联 Deallocator
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

### 6.5.10 DirectByteBuffer 的 native 内存回收链路

```
DirectByteBuffer 的 native 内存回收完整链路：

1. Java 堆 DirectByteBuffer 对象
   ↓
2. 对象变成不可达
   ↓
3. PhantomReference（Cleaner）加入 pending list
   ↓
4. ReferenceProcessor 处理 PhantomReference
   ↓
5. Cleaner 加入 ReferenceQueue
   ↓
6. ReferenceQueueDaemon 线程 poll() 出 Cleaner
   ↓
7. 调用 Cleaner.clean()
   ↓
8. 执行 Deallocator.run()
   ↓
9. unsafe.freeMemory() 释放 native 内存
   ↓
10. DirectByteBuffer 占用的 native 内存被释放
```

---

## 四、PhantomReference 的工程应用

### 6.5.11 应用 1：DirectByteBuffer 释放

```java
// 自动释放 native 内存
ByteBuffer buf = ByteBuffer.allocateDirect(1024 * 1024);  // 1 MB native 内存
// ... 使用 buf
buf = null;
// → GC 时自动释放 1 MB native 内存
```

### 6.5.12 应用 2：自定义资源清理

```java
public class NativeResource {
    private long handle;  // native 资源句柄
    private final Cleaner cleaner;
    
    public NativeResource() {
        this.handle = createNativeResource();
        // 创建 Cleaner，关联清理逻辑
        this.cleaner = Cleaner.create(this, () -> {
            // 清理 native 资源
            releaseNativeResource(handle);
        });
    }
    
    private static native long createNativeResource();
    private static native void releaseNativeResource(long handle);
}

// 使用
NativeResource res = new NativeResource();
// ... 使用 res
res = null;
// → GC 时自动调用 releaseNativeResource
```

### 6.5.13 应用 3：监控 native 内存

```java
public class NativeMemoryMonitor {
    private final List<WeakReference<ByteBuffer>> trackedBuffers = new ArrayList<>();
    
    public void track(ByteBuffer buf) {
        trackedBuffers.add(new WeakReference<>(buf));
    }
    
    // 定期检查 native 内存
    public void check() {
        for (WeakReference<ByteBuffer> ref : trackedBuffers) {
            ByteBuffer buf = ref.get();
            if (buf == null) {
                // DirectByteBuffer 已被 GC 回收
                // → Cleaner 已释放 native 内存
                trackedBuffers.remove(ref);
            }
        }
    }
}
```

---

## 五、PhantomReference 的工程坑点

### 6.5.14 坑点 1：get() 永远返回 null

```java
// ❌ 错误：尝试访问 PhantomReference 的 referent
PhantomReference<MyObject> ref = new PhantomReference<>(obj, queue);
MyObject value = ref.get();  // 永远是 null

// ✅ 正确：PhantomReference 不用于访问 referent
// PhantomReference 只用于"对象回收通知"
```

### 6.5.15 坑点 2：ReferenceQueue 阻塞

```java
// ❌ 错误：阻塞的 remove() 调用
ReferenceQueue<MyObject> queue = new ReferenceQueue<>();
MyObject obj = new MyObject();
PhantomReference<MyObject> ref = new PhantomReference<>(obj, queue);
MyObject value = queue.remove();  // 阻塞直到有 Reference 入队
// → 线程卡死

// ✅ 正确：用 poll() 或后台线程
MyObject value = (MyObject) queue.poll();  // 非阻塞
```

### 6.5.16 坑点 3：DirectByteBuffer 内存泄漏

```java
// ❌ 错误：DirectByteBuffer 不被 GC
ByteBuffer buf = ByteBuffer.allocateDirect(1024 * 1024);
byte[] holder = new byte[1024];  // 持有 buf 的引用
// holder 长期存活 → buf 不被 GC → native 内存不释放

// ✅ 正确：及时释放
ByteBuffer buf = ByteBuffer.allocateDirect(1024 * 1024);
// ... 使用 buf
buf = null;
// → GC 时释放 native 内存
```

---

## 六、PhantomReference 的源码索引

### 6.5.17 核心源码路径

```
libcore/ojluni/src/main/java/java/lang/ref/PhantomReference.java  # PhantomReference
libcore/libart/src/main/java/jdk/internal/ref/Cleaner.java         # Cleaner
libcore/ojluni/src/main/java/java/nio/DirectByteBuffer.java        # DirectByteBuffer
libcore/libart/src/main/java/jdk/internal/ref/PhantomCleanable.java # PhantomCleanable
art/runtime/gc/reference_processor.h                               # ReferenceProcessor
art/runtime/gc/reference_processor.cc                              # HandlePhantomReferences
```

### 6.5.18 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `ReferenceProcessor::HandlePhantomReferences` | `reference_processor.cc` | 处理虚引用 |
| `PhantomReference::get` | `PhantomReference.java` | 永远返回 null |
| `Cleaner::create` | `Cleaner.java` | 创建 Cleaner |
| `Cleaner::clean` | `Cleaner.java` | 执行清理逻辑 |
| `Deallocator::run` | `DirectByteBuffer.java` | 释放 native 内存 |

---

## 七、本节小结

1. **PhantomReference = 真正的析构语义**：get() 永远 null + 对象回收后入队
2. **Cleaner = PhantomReference + ReferenceQueue + Runnable**：自动资源清理
3. **DirectByteBuffer 用 Cleaner 释放 native 内存**：完整链路
4. **工程坑点**：get() null / ReferenceQueue 阻塞 / DirectByteBuffer 泄漏
5. **替代 finalize()**：完全用 Cleaner 替代

→ **理解 PhantomReference + Cleaner，就理解了"真正的析构语义"**。

---

## 跨节引用

**本节被以下章节引用**：
- [6.6 Cleaner](./06-Cleaner.md) —— Cleaner 详细
- [6.9 实战案例](./09-实战案例.md) —— Cleaner 实战

**本节引用**：
- [6.1 可达性状态机](./01-可达性状态机.md) —— 虚引用可达性
- [6.4 FinalReference](./04-FinalReference.md) —— finalize() 替代
