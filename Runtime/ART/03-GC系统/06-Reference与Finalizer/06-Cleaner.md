# 6.6 Cleaner：JDK 8 引入的轻量析构

> **本节回答一个根本问题**：Cleaner 是什么？怎么用？它和 finalize() 有什么区别？
>
> **答案**：**Cleaner = PhantomReference + ReferenceQueue + Runnable + 后台线程** —— JDK 8 引入的轻量析构机制。
>
> **理解本节，就理解了"为什么 Cleaner 是 finalize() 的最佳替代"**。

---

## 一、Cleaner 的定义

### 6.6.1 Cleaner 的语义

```
Cleaner 的语义：

1. 关联一个对象（被引用的对象）和一个清理逻辑（Runnable）
2. 当关联的对象被 GC 回收时
3. 自动执行清理逻辑
4. 比 finalize() 更可控、更高效
```

### 6.6.2 Cleaner 与 finalize() 的对比

| 维度 | finalize() | Cleaner |
|:---|:---|:---|
| **JDK 版本** | JDK 1.0 | JDK 8+ |
| **实现机制** | FinalReference + FinalizerDaemon | PhantomReference + ReferenceQueueDaemon |
| **线程** | FinalizerDaemon 单线程 | ReferenceQueueDaemon 线程 |
| **阻塞影响** | 阻塞整个队列 | 阻塞 Cleaner 但不阻塞其他 Reference |
| **性能** | 差（每个对象都要 FinalizerDaemon 处理） | 较好（用 PhantomReference） |
| **可预测性** | 低 | 中 |
| **推荐** | ❌ 不推荐 | ✅ 推荐 |

### 6.6.3 Cleaner 的实现机制

```
Cleaner 的实现机制：

1. Cleaner extends PhantomReference<Object>
   → 继承 PhantomReference
   → get() 永远返回 null

2. Cleaner 关联一个 Runnable
   → thunk 字段存储清理逻辑

3. Cleaner 用静态 dummy queue
   → dummyQueue 不真正入队
   → Cleaner 通过 add() 和 remove() 维护双向链表

4. 对象被 GC 回收时
   → Cleaner 入队到 ReferenceQueue
   → 但 Cleaner 不直接消费 dummy queue
   → 而是通过 Cleaner 链表机制
```

---

## 二、Cleaner 的实现

### 6.6.4 Cleaner 源码

```java
// libcore/libart/src/main/java/jdk/internal/ref/Cleaner.java
public class Cleaner extends PhantomReference<Object> {
    // 静态 dummy queue
    private static final ReferenceQueue<Object> dummyQueue = new ReferenceQueue<>();
    
    // Cleaner 双向链表（全局）
    private static Cleaner first = null;
    
    // 实例字段
    private Cleaner next = null;
    private Cleaner prev = null;
    private final Runnable thunk;
    
    private Cleaner(Object referent, Runnable thunk) {
        super(referent, dummyQueue);
        this.thunk = thunk;
    }
    
    // 创建 Cleaner（关键 API）
    public static Cleaner create(Object referent, Runnable thunk) {
        if (thunk == null) return null;
        return add(new Cleaner(referent, thunk));
    }
    
    // 加入全局链表
    private static synchronized Cleaner add(Cleaner cl) {
        if (first != null) {
            cl.next = first;
            first.prev = cl;
        }
        first = cl;
        return cl;
    }
    
    // 从链表移除
    private static synchronized boolean remove(Cleaner cl) {
        if (cl.next == cl) {
            // 链表只有这一个
            first = null;
        } else {
            if (first == cl) {
                first = cl.next;
            }
            if (cl.next != null) {
                cl.next.prev = cl.prev;
            }
            if (cl.prev != null) {
                cl.prev.next = cl.next;
            }
            cl.next = cl;
            cl.prev = cl;
        }
        return true;
    }
    
    // 执行清理（由 ReferenceQueueDaemon 调用）
    public void clean() {
        if (!remove(this)) return;
        try {
            thunk.run();  // 执行清理逻辑
        } catch (Throwable t) {
            // 防止 thunk 异常影响其他 Cleaner
        }
    }
}
```

### 6.6.5 PhantomCleanable（Cleaner 子类）

```java
// libcore/libart/src/main/java/jdk/internal/ref/PhantomCleanable.java
public abstract class PhantomCleanable<T> extends PhantomReference<T> {
    // 显式链表（不依赖 dummy queue）
    private PhantomCleanable<T> next;
    private PhantomCleanable<T> prev;
    
    protected PhantomCleanable(T referent) {
        super(referent, null);  // 不使用 ReferenceQueue
        // 加入全局链表
        insert();
    }
    
    // 加入全局链表
    private void insert() {
        synchronized (PhantomCleanable.class) {
            if (first != null) {
                this.next = first;
                first.prev = this;
            }
            first = this;
        }
    }
    
    // 从链表移除
    private void remove() {
        synchronized (PhantomCleanable.class) {
            if (next == this) {
                first = null;
            } else {
                if (first == this) {
                    first = next;
                }
                next.prev = prev;
                prev.next = next;
            }
            this.next = this;
            this.prev = this;
        }
    }
    
    // 抽象方法：清理逻辑
    protected abstract void performCleanup();
    
    // 由 Reference 机制自动调用
    public void clear() {
        remove();
        super.clear();
    }
}
```

---

## 三、ReferenceQueueDaemon 处理 Cleaner

### 6.6.6 ReferenceQueueDaemon 的工作循环

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    private static class ReferenceQueueDaemon extends Daemon {
        @Override
        public void run() {
            while (isRunning()) {
                // 处理 ReferenceQueue 中的所有 Reference
                Reference<? extends Object> ref;
                while ((ref = queue.poll()) != null) {
                    // 处理 Reference
                    if (ref instanceof Cleaner) {
                        // Cleaner：执行清理逻辑
                        ((Cleaner) ref).clean();
                    } else {
                        // 其他 Reference
                        ref.enqueue();
                    }
                }
            }
        }
    }
}
```

### 6.6.7 Cleaner 的清理触发

```
Cleaner 清理触发的完整链路：

1. 对象被 GC 判定为不可达
2. ART 创建 FinalReference 指向对象（如果有 finalize）
   或直接进入 PhantomReference 处理
3. PhantomReference 加入 pending list
4. ReferenceProcessor 处理 PhantomReference
5. PhantomReference 入队到 ReferenceQueue
6. ReferenceQueueDaemon 线程 poll()
7. 发现是 Cleaner 实例
8. 调用 Cleaner.clean()
9. Cleaner.clean() 调用 thunk.run()
10. thunk.run() 执行清理逻辑（如释放 native 内存）
```

---

## 四、Cleaner 的工程应用

### 6.6.8 应用 1：DirectByteBuffer 释放 native 内存

```java
// DirectByteBuffer 用 Cleaner 释放
public class DirectByteBuffer extends MappedByteBuffer implements DirectBuffer {
    private final long address;
    private final Cleaner cleaner;
    
    DirectByteBuffer(long addr, int cap) {
        super(-1, 0, cap, cap, null);
        this.address = addr;
        this.cleaner = Cleaner.create(this, new Deallocator(addr));
    }
    
    private static class Deallocator implements Runnable {
        private long address;
        
        Deallocator(long address) {
            this.address = address;
        }
        
        public void run() {
            if (address != 0) {
                unsafe.freeMemory(address);
                address = 0;
            }
        }
    }
}
```

### 6.6.9 应用 2：自定义 native 资源清理

```java
public class NativeResource {
    private long handle;
    private final Cleaner cleaner;
    
    public NativeResource() {
        // 创建 native 资源
        this.handle = nativeCreate();
        
        // 创建 Cleaner
        this.cleaner = Cleaner.create(this, () -> {
            // 清理 native 资源
            if (handle != 0) {
                nativeRelease(handle);
                handle = 0;
            }
        });
    }
    
    private static native long nativeCreate();
    private static native void nativeRelease(long handle);
    
    // 主动释放（可选）
    public void close() {
        cleaner.clean();  // 主动调用 Cleaner.clean()
    }
}
```

### 6.6.10 应用 3：FileDescriptor 关闭

```java
// FileDescriptor 用 Cleaner 关闭 native fd
public final class FileDescriptor {
    private long descriptor;  // native fd
    private final Cleaner cleaner;
    
    FileDescriptor(long descriptor) {
        this.descriptor = descriptor;
        this.cleaner = Cleaner.create(this, () -> {
            // 关闭 native fd
            if (descriptor != -1) {
                nativeClose(descriptor);
                descriptor = -1;
            }
        });
    }
    
    private static native void nativeClose(long descriptor);
}
```

### 6.6.11 应用 4：Bitmap 回收（Android 平台）

```java
// Bitmap 内部 native 资源
public final class Bitmap {
    private final long mNativePtr;  // native bitmap 指针
    private final Cleaner cleaner;
    
    Bitmap(long nativePtr, int width, int height, ...) {
        mNativePtr = nativePtr;
        // 创建 Cleaner
        cleaner = Cleaner.create(this, () -> {
            nativeRecycle(mNativePtr);
        });
    }
    
    public void recycle() {
        // 主动回收（推荐）
        cleaner.clean();
    }
}
```

---

## 五、Cleaner 的工程坑点

### 6.6.12 坑点 1：Cleaner.clean() 必须幂等

```java
// ❌ 错误：clean() 不是幂等
public class Resource implements Runnable {
    private long handle;
    
    public Resource() {
        handle = createNative();
        Cleaner.create(this, this);  // Cleaner 关联清理
    }
    
    @Override
    public void run() {
        // 被多次调用会出问题
        releaseNative(handle);
        handle = 0;
    }
}

// ✅ 正确：clean() 幂等
public class Resource implements Runnable {
    private long handle;
    
    @Override
    public void run() {
        if (handle != 0) {
            releaseNative(handle);
            handle = 0;  // 防止重复释放
        }
    }
}
```

### 6.6.13 坑点 2：Cleaner 不能清理 this 对象

```java
// ❌ 错误：Cleaner 关联 this，但 this 又是 Cleaner 的字段
public class BadExample {
    private final Cleaner cleaner;
    
    public BadExample() {
        this.cleaner = Cleaner.create(this, () -> {
            // Cleaner 持有 this 的 PhantomReference
            // 但 Cleaner 也持有 thunk（this）的强引用
            // → this 永远不能被 GC
            // → Cleaner 永远不会被触发
            System.out.println("cleanup");
        });
    }
}

// ✅ 正确：Cleaner 关联外部对象
public class GoodExample {
    private final Cleaner cleaner;
    
    public GoodExample(SomeResource resource) {
        this.cleaner = Cleaner.create(resource, () -> {
            // resource 是被引用的对象
            // GoodExample 不持有 resource 的强引用
            // → resource 可以被 GC
            // → Cleaner 可以被触发
            resource.cleanup();
        });
    }
}
```

### 6.6.14 坑点 3：Cleaner 阻塞

```java
// ❌ 错误：Cleaner 阻塞
public class Resource implements Runnable {
    @Override
    public void run() {
        // 阻塞 10 秒
        Thread.sleep(10000);
    }
}

// ✅ 正确：异步释放
public class Resource implements Runnable {
    private final ExecutorService executor = Executors.newCachedThreadPool();
    
    @Override
    public void run() {
        // 异步释放
        executor.submit(() -> {
            // 异步释放逻辑
        });
    }
}
```

---

## 六、Cleaner 的源码索引

### 6.6.15 核心源码路径

```
libcore/libart/src/main/java/jdk/internal/ref/Cleaner.java         # Cleaner
libcore/libart/src/main/java/jdk/internal/ref/PhantomCleanable.java # PhantomCleanable
libcore/libart/src/main/java/java/lang/Daemons.java                # Daemon 线程
libcore/ojluni/src/main/java/java/nio/DirectByteBuffer.java         # DirectByteBuffer
art/runtime/gc/reference_processor.h                                # ReferenceProcessor
```

### 6.6.16 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Cleaner::create` | `Cleaner.java` | 创建 Cleaner |
| `Cleaner::clean` | `Cleaner.java` | 执行清理 |
| `Cleaner::add` | `Cleaner.java` | 加入链表 |
| `Cleaner::remove` | `Cleaner.java` | 从链表移除 |
| `ReferenceQueueDaemon::run` | `Daemons.java` | 处理 Reference |

---

## 七、本节小结

1. **Cleaner = PhantomReference + Runnable + 链表机制**：JDK 8 引入的轻量析构
2. **Cleaner 优于 finalize()**：可控、高效、可预测
3. **DirectByteBuffer / FileDescriptor / Bitmap 用 Cleaner**：自动释放 native 资源
4. **工程坑点**：clean() 幂等 / 不能清理 this / Cleaner 阻塞
5. **最佳实践**：完全替代 finalize()，统一用 Cleaner

→ **理解 Cleaner，就理解了"如何用 Java 正确释放 native 资源"**。

---

## 跨节引用

**本节被以下章节引用**：
- [6.9 实战案例](./09-实战案例.md) —— Cleaner 实战
- 09 篇诊断 —— DirectByteBuffer 内存诊断

**本节引用**：
- [6.5 PhantomReference](./05-PhantomReference.md) —— Cleaner 的基础
- [6.4 FinalReference](./04-FinalReference.md) —— finalize() 替代
