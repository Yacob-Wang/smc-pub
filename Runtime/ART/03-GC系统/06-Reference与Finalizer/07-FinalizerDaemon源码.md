# 6.7 FinalizerDaemon 源码深潜

> **本节回答一个根本问题**：FinalizerDaemon 的源码级实现细节是什么？它怎么处理阻塞、超时、对象复活？
>
> **答案**：**FinalizerDaemon 是单线程 daemon，从 ReferenceQueue 取出 FinalReference，调用 finalize()，处理对象复活**。
>
> **理解本节，就理解了"为什么 finalize() 会阻塞 GC 队列"**。

---

## 一、FinalizerDaemon 的源码入口

### 6.7.1 Daemons.java 的定义

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    // FinalizerDaemon 单例
    public static final Daemon FinalizerDaemon = new FinalizerDaemon();
    
    private static class FinalizerDaemon extends Daemon {
        // ReferenceQueue：FinalReference 入队的目标
        private final ReferenceQueue<Object> queue = new ReferenceQueue<Object>() {
            @Override
            void enqueueInternal(Reference<?> list) {
                // 同步入队
                synchronized (lock) {
                    list.next = head;
                    head = list;
                }
            }
        };
        
        @Override
        public void run() {
            while (isRunning()) {
                // 1. 从 ReferenceQueue 取出 FinalReference
                FinalizerReference<?> ref;
                try {
                    ref = (FinalizerReference<?>) queue.remove();
                } catch (InterruptedException e) {
                    continue;
                }
                
                // 2. 处理 FinalReference
                if (ref != null) {
                    finalizeReference(ref);
                }
            }
        }
        
        private void finalizeReference(FinalizerReference<?> ref) {
            // 1. 取出被引用的对象
            Object object = ref.get();
            if (object == null) return;
            
            // 2. 增加 finalize 计数（用于 FinalizerWatchdogDaemon）
            FinalizerDaemon.INSTANCE.count++;
            
            // 3. 调用对象的 finalize() 方法
            try {
                object.finalize();
            } catch (Throwable t) {
                // 捕获 Throwable 防止 daemon 线程崩溃
                // 但不处理（业务层应避免 finalize 抛异常）
            } finally {
                // 4. 减少 finalize 计数
                FinalizerDaemon.INSTANCE.count--;
                
                // 5. 清空 FinalReference 的 referent
                //    让对象可以被 GC 回收
                ref.clear();
            }
        }
    }
}
```

### 6.7.2 FinalizerReference 的定义

```java
// libcore/ojluni/src/main/java/java/lang/ref/FinalizerReference.java
public final class FinalizerReference<T> extends FinalReference<T> {
    // 静态 dummy queue
    private static final ReferenceQueue<Object> dummyQueue = new ReferenceQueue<>();
    
    public FinalizerReference(T referent, ReferenceQueue<? super T> queue) {
        super(referent, queue != null ? queue : dummyQueue);
    }
    
    @Override
    public T get() {
        // FinalReference.get() 永远返回 referent
        // 让对象在 finalize() 期间继续存活
        return referent;
    }
}
```

---

## 二、FinalizerDaemon 的启动

### 6.7.3 FinalizerDaemon 的启动

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    public static void start() {
        // 1. 启动 FinalizerDaemon 线程
        FinalizerDaemon.INSTANCE.start();
        
        // 2. 启动 FinalizerWatchdogDaemon 线程
        FinalizerWatchdogDaemon.INSTANCE.start();
        
        // 3. 启动 ReferenceQueueDaemon 线程
        ReferenceQueueDaemon.INSTANCE.start();
    }
}
```

### 6.7.4 FinalizerDaemon 启动时机

```
FinalizerDaemon 在以下时机启动：

1. 系统启动时：
   - ZygoteInit 中启动 ART 运行时
   - ART 启动时创建 Daemons
   - Daemons.start() 启动 FinalizerDaemon

2. 第一个 finalize() 调用前：
   - 类加载时如果类有 finalize 方法
   - ART 创建 FinalizerDaemon 实例（懒加载）
   - FinalizerDaemon 开始处理 finalize 队列
```

---

## 三、FinalizerDaemon 的工作流程

### 6.7.5 FinalizerDaemon 的完整流程

```
业务线程：创建有 finalize() 的对象
  ↓
1. ART 在对象头标记 has_finalizer = true
  ↓
2. 对象被使用一段时间
  ↓
3. 对象不可达（引用全部释放）
  ↓
4. GC 标记阶段：
   - 对象被标记为可达（有 FinalReference 引用）
   - 但对象原本应该被回收
  ↓
5. ReferenceProcessor 处理：
   - 发现对象 has_finalizer = true
   - 创建 FinalReference 指向对象
   - FinalReference 加入 FinalizerDaemon 的队列
  ↓
6. FinalizerDaemon.run() 处理：
   - 从队列取出 FinalReference
   - 调用 object.finalize()
   - 清空 FinalReference.referent
  ↓
7. 对象真正被 GC 回收（下次 GC）
```

### 6.7.6 finalize() 中的对象复活

```java
public class ReanimatedObject {
    private static final ReanimatedObject INSTANCE = new ReanimatedObject();
    
    @Override
    protected void finalize() throws Throwable {
        // 在 finalize() 中建立强引用 → 对象被"复活"
        INSTANCE.references(this);
    }
}
```

**复活机制**：
```
1. 对象不可达
2. FinalizerDaemon 取出 FinalReference
3. 调用 finalize()
4. finalize() 中执行 INSTANCE.references(this)
5. INSTANCE 持有 this 的强引用 → this 不再不可达
6. this 被"复活"
7. 清空 FinalReference.referent（但对象已被复活）
8. 下次 GC → 对象被判定为可达 → 不回收
```

**问题**：
- 复活对象"逃脱"了 GC
- 但下次 GC 后可能再次不可达
- 反复触发 finalize()（最多 2 次，因为 FinalReference 会清空）

### 6.7.7 ART 限制 finalize() 次数

```cpp
// art/runtime/gc/reference_processor.cc
void ReferenceProcessor::HandleFinalReferences(...) {
    // 1. 限制 finalize() 最多 2 次
    if (obj->finalize_count_ >= 2) {
        // 超过 2 次 → 不再调用 finalize()
        ref->Clear();
        return;
    }
    
    // 2. 增加计数
    obj->finalize_count_++;
    
    // 3. 加入 FinalizerDaemon 队列
    daemon->AddPendingReference(ref);
}
```

---

## 四、FinalizerDaemon 的性能特征

### 6.7.8 单线程的限制

```
FinalizerDaemon 是单线程 daemon：

优点：
  - 简单实现
  - 无并发问题
  - 顺序处理

缺点：
  - 一个 finalize() 阻塞 → 所有 finalize() 等待
  - 无法利用多核 CPU
  - 高 finalize() 频率时性能差
```

### 6.7.9 阻塞的影响

```java
// ❌ 错误：finalize() 阻塞
public class BlockingResource {
    @Override
    protected void finalize() throws Throwable {
        // 阻塞 10 秒
        Thread.sleep(10000);
    }
}

// 创建 1000 个 BlockingResource
List<BlockingResource> list = new ArrayList<>();
for (int i = 0; i < 1000; i++) {
    list.add(new BlockingResource());
}
list = null;

// GC 时：
// - 1000 个 BlockingResource 进入 FinalizerDaemon 队列
// - 第一个阻塞 10 秒
// - 后续 999 个 finalize() 等待
// - 总耗时 10000 秒 ≈ 2.7 小时
// → 应用 OOM
```

### 6.7.10 ART 14+ 的 FinalizerDaemon 优化

```cpp
// art/runtime/gc/collector/concurrent_copying.cc 的 FinalizerDaemon 优化
void FinalizerDaemon::processFinalReferences() {
    // 1. 批量处理多个 FinalReference
    std::vector<FinalReference*> batch;
    while (batch.size() < kBatchSize && !queue.empty()) {
        batch.push_back(queue.pop());
    }
    
    // 2. 批量调用 finalize()
    for (FinalReference* ref : batch) {
        finalizeReference(ref);
    }
}
```

---

## 五、FinalizerDaemon 的工程影响

### 6.7.11 finalize() 阻塞的检测

```bash
# 1. 看 FinalizerDaemon 状态
adb shell ps -T -p <pid> | grep "FinalizerDaemon"
# 输出示例：
# 12345 12346 12345 1 -19 0 0 0 finalizer

# 2. 看 FinalizerWatchdogDaemon 警告
adb logcat -s "art" | grep "Finalizer watch dog"
# 输出示例：
# art : Finalizer watch dog timed out: 15000ms

# 3. 看 finalize() 队列长度
adb shell dumpsys meminfo <package> | grep "Finalizer"
```

### 6.7.12 finalize() 阻塞的处理

```java
// 方案 1：用 AutoCloseable 替代
public class Resource implements AutoCloseable {
    @Override
    public void close() {
        // 显式释放
    }
}

// 使用
try (Resource res = new Resource()) {
    // 业务逻辑
}  // close() 自动调用

// 方案 2：用 Cleaner 替代
public class Resource {
    private final Cleaner cleaner;
    
    public Resource() {
        this.cleaner = Cleaner.create(this, () -> {
            // 异步释放
        });
    }
}

// 方案 3：异步 finalize()
@Override
protected void finalize() throws Throwable {
    executor.submit(this::releaseAsync);  // 异步释放
}
```

---

## 六、FinalizerDaemon 的源码索引

### 6.7.13 核心源码路径

```
libcore/libart/src/main/java/java/lang/Daemons.java                   # Daemon 线程
libcore/ojluni/src/main/java/java/lang/ref/FinalReference.java       # FinalReference
libcore/ojluni/src/main/java/java/lang/ref/FinalizerReference.java   # FinalizerReference
art/runtime/gc/reference_processor.h                                  # ReferenceProcessor
art/runtime/gc/reference_processor.cc                                 # HandleFinalReferences
```

### 6.7.14 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `FinalizerDaemon::run` | `Daemons.java` | FinalizerDaemon 主循环 |
| `FinalizerDaemon::finalizeReference` | `Daemons.java` | 执行 finalize() |
| `FinalizerReference::get` | `FinalizerReference.java` | 返回 referent |
| `ReferenceProcessor::HandleFinalReferences` | `reference_processor.cc` | 处理 FinalReference |

### 6.7.15 关键常量

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
private static final int MAX_FINALIZE_COUNT = 2;  // finalize() 最多 2 次
private static final long MAX_FINALIZE_TIME_MS = 10 * 1000;  // 10 秒超时
```

---

## 七、本节小结

1. **FinalizerDaemon 是单线程 daemon**：从 ReferenceQueue 取出 FinalReference
2. **finalize() 最多 2 次**：避免无限复活
3. **阻塞影响整个队列**：一个 finalize() 卡死 → 全部等待
4. **工程替代**：AutoCloseable / Cleaner
5. **FinalizerWatchdogDaemon 监控 10 秒超时**：警告但不强制

→ **理解 FinalizerDaemon 源码，就理解了"为什么 finalize() 应该被禁止"**。

---

## 跨节引用

**本节被以下章节引用**：
- [6.8 FinalizerWatchdogDaemon 源码](./08-FinalizerWatchdog源码.md) —— Watchdog 监控
- [6.9 实战案例](./09-实战案例.md) —— finalize() 阻塞案例

**本节引用**：
- [6.4 FinalReference](./04-FinalReference.md) —— FinalReference 机制
- [01 篇 1.6 Reference 体系](../01-基础理论/06-Reference体系.md) —— Reference 概览
