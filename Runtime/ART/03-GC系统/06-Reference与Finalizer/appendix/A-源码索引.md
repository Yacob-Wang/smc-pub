# 附录 A：源码索引（Reference 与 Finalizer）

## 一、Java 层 Reference 体系

```
libcore/ojluni/src/main/java/java/lang/ref/
├── Reference.java              # Reference 基类
├── SoftReference.java          # 软引用
├── WeakReference.java          # 弱引用
├── PhantomReference.java       # 虚引用
├── FinalReference.java         # 终结引用
├── FinalizerReference.java     # Finalizer 专用引用
└── ReferenceQueue.java         # 引用队列

libcore/ojluni/src/main/java/java/util/WeakHashMap.java  # WeakHashMap
```

## 二、ART 层 Daemon 体系

```
libcore/libart/src/main/java/java/lang/Daemons.java      # Daemon 线程定义
├── FinalizerDaemon           # 处理 finalize()
├── FinalizerWatchdogDaemon   # 监控 finalize() 超时
└── ReferenceQueueDaemon      # 处理 ReferenceQueue
```

## 三、ART 层 Reference 处理

```
art/runtime/gc/reference_processor.h    # ReferenceProcessor
art/runtime/gc/reference_processor.cc   # Reference 处理实现
```

## 四、Cleaner 体系

```
libcore/libart/src/main/java/jdk/internal/ref/
├── Cleaner.java              # Cleaner（基于 PhantomReference）
└── PhantomCleanable.java     # PhantomCleanable 子类
```

## 五、关键函数

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `Reference::get` | `Reference.java` | 获取 referent |
| `Reference::clear` | `Reference.java` | 清空 referent |
| `Reference::enqueue` | `Reference.java` | 入队 |
| `SoftReference::get` | `SoftReference.java` | 软引用 get |
| `WeakReference::get` | `WeakReference.java` | 弱引用 get |
| `PhantomReference::get` | `PhantomReference.java` | 永远返回 null |
| `Cleaner::create` | `Cleaner.java` | 创建 Cleaner |
| `Cleaner::clean` | `Cleaner.java` | 执行清理 |
| `FinalizerDaemon::run` | `Daemons.java` | FinalizerDaemon 主循环 |
| `FinalizerDaemon::finalizeReference` | `Daemons.java` | 执行 finalize |
| `FinalizerWatchdogDaemon::run` | `Daemons.java` | Watchdog 主循环 |
| `FinalizerWatchdogDaemon::checkFinalizerTimeouts` | `Daemons.java` | 检查超时 |
| `ReferenceQueueDaemon::run` | `Daemons.java` | 处理 ReferenceQueue |
| `ReferenceProcessor::HandleSoftReferences` | `reference_processor.cc` | 处理软引用 |
| `ReferenceProcessor::HandleWeakReferences` | `reference_processor.cc` | 处理弱引用 |
| `ReferenceProcessor::HandleFinalReferences` | `reference_processor.cc` | 处理 Final |
| `ReferenceProcessor::HandlePhantomReferences` | `reference_processor.cc` | 处理虚引用 |

## 六、关键常量

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
private static final int INTERVAL_MS = 1000;  // Watchdog 1 秒检查
private static final long MAX_FINALIZE_TIME_MS = 10 * 1000;  // 10 秒超时
private static final int MAX_FINALIZE_COUNT = 2;  // 最多 2 次

// dalvik.vm.softrefthreshold = 0.25
```

## 七、版本演进

| 版本 | 变更 |
|:---|:---|
| JDK 1.0 | Reference 体系引入（finalize） |
| JDK 8 | Cleaner 引入（基于 PhantomReference） |
| JDK 9 | finalize() Deprecated |
| AOSP 5.0 | Daemon 线程（Finalizer / Watchdog） |
| AOSP 8.0 | Cleaner 在 Android 中完整支持 |
