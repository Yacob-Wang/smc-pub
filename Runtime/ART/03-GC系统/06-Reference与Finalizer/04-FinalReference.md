# 6.4 FinalReference：finalize() 的本质

> **本节回答一个根本问题**：Java 的 finalize() 方法是怎么实现的？FinalReference + FinalizerDaemon + FinalizerWatchdogDaemon 三者怎么协作？
>
> **答案**：**FinalReference + FinalizerDaemon 异步执行 + FinalizerWatchdogDaemon 监控超时** —— 三方协作。
>
> **理解本节，就理解了"为什么 finalize() 应该被完全禁止"**。

---

## 一、finalize() 的本质

### 6.4.1 finalize() 的语义

```
finalize() 方法：
  - 在对象被 GC 回收前调用
  - 用于"析构"或释放资源
  - 类似 C++ 的析构函数（destructor）

但 finalize() 有严重问题：
  - 性能差（每个对象都要 FinalizerDaemon 处理）
  - 不确定性（何时执行不可控）
  - 可能阻塞（finalize() 阻塞导致队列堆积）
  - 已被 JDK 9+ 标记为 Deprecated

→ 推荐用 PhantomReference + Cleaner 替代
```

### 6.4.2 finalize() 的实现机制

```
finalize() 的实现机制：

1. 类重写 finalize() 时
   → ART 在类元数据中标记 has_finalizer = true
   
2. GC 判定对象不可达
   → ART 创建 FinalReference 指向该对象
   → FinalReference 加入 pending list
   
3. ReferenceProcessor 处理 FinalReference
   → FinalReference 加入 FinalizerDaemon 的队列
   
4. FinalizerDaemon 线程取出 FinalReference
   → 执行对象的 finalize() 方法
   → 对象被复活（finalize 中建立强引用）
   → 或 finalize 执行完毕 → 对象真正回收

5. FinalizerWatchdogDaemon 监控
   → 如果 finalize() 超过 10 秒
   → 输出警告（但不会终止）
```

---

## 二、FinalReference 的实现

### 6.4.3 FinalReference 源码

```java
// libcore/ojluni/src/main/java/java/lang/ref/FinalReference.java
public class FinalReference<T> extends Reference<T> {
    public FinalReference(T referent, ReferenceQueue<? super T> q) {
        super(referent, q);
    }
}

// libcore/ojluni/src/main/java/java/lang/ref/FinalizerReference.java
public final class FinalizerReference<T> extends FinalReference<T> {
    // 静态 dummy queue（不真正入队）
    private static final ReferenceQueue<Object> dummyQueue = new ReferenceQueue<>();
    
    public FinalizerReference(T referent, ReferenceQueue<? super T> queue) {
        super(referent, queue != null ? queue : dummyQueue);
    }
    
    @Override
    public T get() {
        return referent;  // FinalReference 不返回 null（让对象继续存活）
    }
}
```

### 6.4.4 类的 finalize 标记

```java
// libcore/ojluni/src/main/java/java/lang/Class.java
public class Class<T> {
    // 标记类是否有 finalize 方法
    private boolean hasFinalizer();
    
    // ART 在类元数据中记录这个标记
    // GC 用这个标记判断是否需要创建 FinalReference
}
```

### 6.4.5 ART 中 FinalReference 的创建

```cpp
// art/runtime/gc/reference_processor.cc
void ReferenceProcessor::HandleFinalReferences(...) {
    // 1. 收集所有 FinalReference
    FinalReferenceList final_refs = CollectFinalReferences();
    
    // 2. 加入 FinalizerDaemon 的队列
    for (FinalReference* ref : final_refs) {
        // 加入 daemon 的 pending list
        daemon->AddPendingReference(ref);
    }
}
```

---

## 三、FinalizerDaemon 的工作循环

### 6.4.6 FinalizerDaemon 的定义

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    // FinalizerDaemon：处理 finalize()
    private static class FinalizerDaemon extends Daemon {
        @Override
        public void run() {
            // 无限循环
            while (isRunning()) {
                // 1. 从 ReferenceQueue 取出 FinalReference
                FinalizerReference<?> ref = (FinalizerReference<?>) queue.remove();
                
                if (ref != null) {
                    // 2. 执行 finalize() 方法
                    finalizeReference(ref);
                }
            }
        }
        
        private void finalizeReference(FinalizerReference<?> ref) {
            // 1. 获取引用的对象
            Object object = ref.get();
            if (object == null) return;
            
            // 2. 调用对象的 finalize() 方法
            object.finalize();
            
            // 3. 清空 FinalReference 的 referent（让对象可以被 GC）
            ref.clear();
        }
    }
}
```

### 6.4.7 FinalizerDaemon 的启动

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    public static void start() {
        // 启动各种 daemon 线程
        FinalizerDaemon.INSTANCE.start();
        FinalizerWatchdogDaemon.INSTANCE.start();
        ReferenceQueueDaemon.INSTANCE.start();
    }
}
```

### 6.4.8 FinalizerDaemon 的性能

```
FinalizerDaemon 的性能特征：

1. 单线程：
   - FinalizerDaemon 是单线程 daemon
   - 所有 finalize() 串行执行
   - 一个 finalize() 阻塞 → 所有 finalize() 等待

2. 不确定性：
   - finalize() 何时执行不可控
   - 取决于 GC 频率和 FinalizerDaemon 负载

3. 性能开销：
   - 每个 finalize() 都要走一遍 Reference 机制
   - 大量 finalize() → 严重性能问题
```

---

## 四、FinalizerWatchdogDaemon 的 10 秒超时

### 6.4.9 FinalizerWatchdogDaemon 的定义

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    private static class FinalizerWatchdogDaemon extends Daemon {
        @Override
        public void run() {
            while (isRunning()) {
                // 检查 finalize() 是否超时
                checkFinalizerTimeouts();
            }
        }
        
        private void checkFinalizerTimeouts() {
            // 1. 检查 finalize() 队列中的最大时间
            long max_finalizer_time = getMaxFinalizerTime();
            
            // 2. 如果超过 10 秒
            if (max_finalizer_time > 10 * 1000) {
                // 3. 输出警告
                Log.w(TAG, "Finalizer watch dog timed out: " + max_finalizer_time + "ms");
            }
        }
    }
}
```

### 6.4.10 10 秒超时的意义

```
FinalizerWatchdogDaemon 的 10 秒超时：

含义：
  - FinalizerDaemon 处理单个 finalize() 不应超过 10 秒
  - 超过 10 秒 → 输出警告
  - 但 ART 不会 kill 进程（只是警告）

问题：
  - 警告没有强制力
  - 一个卡死的 finalize() 阻塞整个队列
  - 后续 finalize() 都无法执行
```

### 6.4.11 finalize() 卡死的真实案例

```java
public class Resource {
    private FileInputStream fis;
    
    @Override
    protected void finalize() throws Throwable {
        // 假设这里阻塞 30 秒
        fis.close();  // 文件被占用 → 阻塞
        super.finalize();
    }
}

// 创建 1000 个 Resource 对象
List<Resource> list = new ArrayList<>();
for (int i = 0; i < 1000; i++) {
    list.add(new Resource());
}
list = null;  // 释放引用

// GC 时：
// - 1000 个 Resource 进入 FinalizerDaemon 队列
// - 第一个 finalize() 阻塞 30 秒
// - 后续 999 个 finalize() 都等待
// - 总耗时 30000 秒 ≈ 8 小时
// - 应用 OOM
```

---

## 五、Finalizer 的工程问题

### 6.4.12 问题 1：性能差

```java
// ❌ 错误：每个对象都重写 finalize()
public class User {
    private long id;
    private String name;
    
    @Override
    protected void finalize() throws Throwable {
        super.finalize();
        // 即使只是清理，也要做 Reference 机制的开销
    }
}

// ✅ 正确：避免 finalize()
public class User {
    private long id;
    private String name;
    // 不重写 finalize() → 没有 Reference 开销
}
```

### 6.4.13 问题 2：不确定性

```java
// finalize() 何时执行不可控
public class HeavyResource {
    @Override
    protected void finalize() {
        // 释放 native 资源
        closeNativeHandle();
    }
}

// 问题：finalize() 可能在最后一次使用后很久才执行
// → native 资源长期占用
// → 资源泄漏

// ✅ 修复：用 AutoCloseable + try-with-resources
public class HeavyResource implements AutoCloseable {
    @Override
    public void close() {
        closeNativeHandle();  // 显式释放
    }
}

// 使用
try (HeavyResource res = new HeavyResource()) {
    // 业务逻辑
}  // close() 自动调用
```

### 6.4.14 问题 3：阻塞队列

```java
// ❌ 错误：finalize() 阻塞
@Override
protected void finalize() {
    try {
        Thread.sleep(10000);  // 阻塞 10 秒
    } catch (InterruptedException e) {
        // ...
    }
}

// ✅ 正确：异步释放
@Override
protected void finalize() {
    executor.submit(this::releaseAsync);  // 异步释放
}
```

---

## 六、Finalizer 的替代方案

### 6.4.15 替代方案 1：AutoCloseable + try-with-resources

```java
public class Resource implements AutoCloseable {
    private FileInputStream fis;
    
    @Override
    public void close() throws IOException {
        fis.close();
    }
}

// 使用
try (Resource res = new Resource()) {
    // 业务逻辑
}  // 自动调用 close()
```

### 6.4.16 替代方案 2：PhantomReference + Cleaner（推荐）

```java
// DirectByteBuffer 用 Cleaner 释放 native 内存
public class DirectByteBuffer extends MappedByteBuffer implements DirectBuffer {
    private final Cleaner cleaner;
    
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
        
        Deallocator(long address) {
            this.address = address;
        }
        
        public void run() {
            unsafe.freeMemory(address);
        }
    }
}
```

### 6.4.17 替代方案 3：ReferenceQueue + 自定义清理

```java
public class ManagedResource {
    private final ReferenceQueue<ManagedResource> queue = new ReferenceQueue<>();
    private final List<CustomWeakReference> refs = new ArrayList<>();
    
    public void track(ManagedResource resource) {
        CustomWeakReference ref = new CustomWeakReference(resource, queue);
        refs.add(ref);
    }
    
    // 定期清理
    public void cleanup() {
        CustomWeakReference ref;
        while ((ref = (CustomWeakReference) queue.poll()) != null) {
            // 执行清理逻辑
            ref.cleanup();
            refs.remove(ref);
        }
    }
    
    private static class CustomWeakReference extends WeakReference<ManagedResource> {
        // 自定义清理逻辑
        public void cleanup() {
            // ...
        }
    }
}
```

---

## 七、Finalizer 的源码索引

### 6.4.18 核心源码路径

```
libcore/ojluni/src/main/java/java/lang/ref/FinalReference.java       # FinalReference
libcore/ojluni/src/main/java/java/lang/ref/FinalizerReference.java   # FinalizerReference
libcore/libart/src/main/java/java/lang/Daemons.java                   # Daemon 线程定义
art/runtime/gc/reference_processor.h                                  # ReferenceProcessor
art/runtime/gc/reference_processor.cc                                 # HandleFinalReferences
art/runtime/mirror/class.h                                            # 类元数据（has_finalizer 标记）
```

### 6.4.19 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `FinalizerDaemon::run` | `Daemons.java` | FinalizerDaemon 主循环 |
| `FinalizerDaemon::finalizeReference` | `Daemons.java` | 执行 finalize() |
| `FinalizerWatchdogDaemon::run` | `Daemons.java` | FinalizerWatchdogDaemon 主循环 |
| `ReferenceProcessor::HandleFinalReferences` | `reference_processor.cc` | 处理 FinalReference |
| `mirror::Class::HasFinalizer` | `class.h` | 类是否重写 finalize() |

### 6.4.20 关键常量

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
private static final long MAX_FINALIZE_TIME_MS = 10 * 1000;  // 10 秒超时
```

---

## 八、本节小结

1. **FinalReference + FinalizerDaemon + FinalizerWatchdogDaemon 三方协作**
2. **finalize() 三大问题**：性能差、不确定性、阻塞队列
3. **FinalizerWatchdogDaemon 监控 10 秒超时**：警告但不强制
4. **替代方案**：AutoCloseable + PhantomReference + Cleaner
5. **建议**：完全禁止 finalize()，用 Cleaner 替代

→ **理解 Finalizer 机制，就理解了"为什么 finalize() 应该被禁止"**。

---

## 跨节引用

**本节被以下章节引用**：
- [6.7 FinalizerDaemon 源码](./07-FinalizerDaemon源码.md) —— FinalizerDaemon 详细源码
- [6.8 FinalizerWatchdogDaemon 源码](./08-FinalizerWatchdog源码.md) —— FinalizerWatchdogDaemon 详细源码
- [6.9 实战案例](./09-实战案例.md) —— finalize() 链式阻塞完整案例

**本节引用**：
- [6.1 可达性状态机](./01-可达性状态机.md) —— Reference 状态
- [01 篇 1.6 Reference 体系](../01-基础理论/06-Reference体系.md) —— Reference 概览
