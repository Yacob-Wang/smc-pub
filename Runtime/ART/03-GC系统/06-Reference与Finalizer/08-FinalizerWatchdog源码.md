# ⚠️ v1 旧稿标记

> **本篇状态**：v1 后期已按 v4 规范写（含 A/B/D 附录），但 ART 17 硬变化未覆盖
>
> - **本篇基线**：AOSP `android-14.0.0_r1`（API 34）+ Linux `android14-5.10/5.15`（**v1 时代基线**）
> - **v2 新基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`
> - **ART 17 硬变化未覆盖**：分代 GC 强化 / 无锁 MessageQueue（API 37+）/ static final 不可变 / AppFunctions / AI Agent OS
>
> **v2 替代/补充篇**（已按 v4 规范 + AOSP 17 + 6.18 写完）：
>
> [10-ART17分代GC强化专章 v2](10-ART17分代GC强化专章-v2.md) · 分代 GC 强化（频繁低耗年轻代回收 + 软阈值 + 端侧 LLM 友好）· [README-ART系列-v2](../../README-ART系列-v2.md) 含 9 子模块 v2 全部链接
>
> **建议**：本篇读完后**必须结合 v2 篇一起看** —— v1 讲基础机制，v2 讲新基线变化。
>
> **当前文件名**：`08-FinalizerWatchdog源码.md`
> **标记时间**：2026-07-17（v2 全系列成稿后批量标）
>
> ---

# 6.8 FinalizerWatchdogDaemon 的 10 秒超时

> **本节回答一个根本问题**：FinalizerWatchdogDaemon 怎么监控 finalize() 是否超时？10 秒超时是怎么实现的？
>
> **答案**：**FinalizerWatchdogDaemon 定期检查 FinalizerDaemon 队列的最大等待时间，超时则输出警告**。
>
> **理解本节，就理解了"为什么 finalize() 卡死时 ART 只会警告不会 kill 进程"**。

---

## 一、FinalizerWatchdogDaemon 的定义

### 6.8.1 Daemons.java 的定义

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    // FinalizerWatchdogDaemon 单例
    public static final Daemon FinalizerWatchdogDaemon = new FinalizerWatchdogDaemon();
    
    private static class FinalizerWatchdogDaemon extends Daemon {
        // 监控间隔（默认 1 秒）
        private static final int INTERVAL_MS = 1000;
        
        @Override
        public void run() {
            while (isRunning()) {
                // 1. 等待 1 秒
                try {
                    Thread.sleep(INTERVAL_MS);
                } catch (InterruptedException e) {
                    continue;
                }
                
                // 2. 检查 finalize() 超时
                checkFinalizerTimeouts();
            }
        }
        
        private void checkFinalizerTimeouts() {
            // 1. 获取 FinalizerDaemon 状态
            long max_finalizer_time = FinalizerDaemon.INSTANCE.maxDuration();
            int finalizer_count = FinalizerDaemon.INSTANCE.count;
            
            // 2. 如果当前正在处理 finalize
            if (finalizer_count > 0 && max_finalizer_time > MAX_FINALIZE_TIME_MS) {
                // 3. 输出警告（但不 kill 进程）
                Log.w(TAG, "Finalizer watch dog timed out: " 
                    + max_finalizer_time + "ms, count=" + finalizer_count);
            }
        }
    }
}
```

### 6.8.2 10 秒超时的实现机制

```
FinalizerWatchdogDaemon 监控机制：

1. FinalizerWatchdogDaemon 每秒检查一次（INTERVAL_MS = 1000ms）
2. 检查 FinalizerDaemon 的状态：
   - maxDuration()：当前 finalize() 的执行时长
   - count：正在执行的 finalize() 数量
3. 如果 count > 0 且 maxDuration > 10 秒：
   - 输出警告："Finalizer watch dog timed out: Xms"
   - 但不 kill 进程（只是警告）
4. 业务层应该监控这个警告
```

---

## 二、FinalizerDaemon 状态追踪

### 6.8.3 FinalizerDaemon 的状态字段

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    private static class FinalizerDaemon extends Daemon {
        // 当前正在执行的 finalize() 数量
        private volatile int count;
        
        // 当前 finalize() 的开始时间
        private volatile long startTime;
        
        // 获取当前 finalize() 的最大执行时长
        public long maxDuration() {
            if (count == 0) return 0;
            return System.currentTimeMillis() - startTime;
        }
        
        private void finalizeReference(FinalizerReference<?> ref) {
            // 1. 记录开始时间
            startTime = System.currentTimeMillis();
            
            // 2. 增加计数
            count++;
            
            try {
                // 3. 执行 finalize()
                object.finalize();
            } finally {
                // 4. 减少计数
                count--;
            }
        }
    }
}
```

### 6.8.4 startTime 的维护

```java
// startTime 的维护逻辑
private void finalizeReference(FinalizerReference<?> ref) {
    startTime = System.currentTimeMillis();
    count++;
    try {
        object.finalize();
    } finally {
        count--;
    }
}
```

**注意**：startTime 只记录最后一个 finalize() 的开始时间，多个 finalize() 并行处理时不准确（但 FinalizerDaemon 是单线程，所以实际上只有一个）。

---

## 三、超时检测的源码

### 6.8.5 FinalizerWatchdogDaemon 的 checkFinalizerTimeouts

```java
private void checkFinalizerTimeouts() {
    // 1. 获取当前 FinalizerDaemon 状态
    long max_finalizer_time = FinalizerDaemon.INSTANCE.maxDuration();
    int finalizer_count = FinalizerDaemon.INSTANCE.count;
    
    // 2. 判定条件
    if (finalizer_count > 0 && max_finalizer_time > MAX_FINALIZE_TIME_MS) {
        // 3. 输出警告
        Log.w(TAG, "Finalizer watch dog timed out: " 
            + max_finalizer_time + "ms, count=" + finalizer_count);
    }
}
```

### 6.8.6 10 秒超时常量的定义

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
public final class Daemons {
    private static class FinalizerWatchdogDaemon extends Daemon {
        // 10 秒超时（硬编码）
        private static final long MAX_FINALIZE_TIME_MS = 10 * 1000;
    }
}
```

### 6.8.7 超时警告的输出

```bash
# 当 finalize() 超过 10 秒时
adb logcat -s "art" | grep "Finalizer"
# 输出示例：
# W art : Finalizer watch dog timed out: 15000ms, count=1
```

---

## 四、超时检测的局限

### 6.8.9 警告但无强制

```
FinalizerWatchdogDaemon 的关键限制：

1. 只输出警告，不 kill 进程
   - 业务层应该主动响应警告
   - ART 不会主动恢复卡死的 finalize()

2. 检测粒度是 1 秒
   - 可能在 11 秒才检测到
   - 实际可能是 10.5 秒就超时

3. 单线程 FinalizerDaemon
   - 一个卡死 → 后续所有 finalize() 都等待
   - 无法通过清理队列恢复
```

### 6.8.10 警告的工程意义

```java
// 监控 FinalizerWatchdogDaemon 警告
public class FinalizerWatchdogMonitor {
    public void onFinalizerTimeout(long timeout) {
        // 1. 上报到 APM
        apmClient.alert("finalizer.timeout", "Finalizer timeout: " + timeout + "ms");
        
        // 2. 主动 GC（不一定有效）
        Runtime.getRuntime().gc();
        
        // 3. 记录堆栈（用于排查）
        Thread.dumpStack();
    }
}
```

---

## 五、FinalizerWatchdogDaemon 的工程影响

### 6.8.11 真实案例：Cursor finalize() 阻塞

```java
// Cursor 在 finalize() 中关闭
// 但如果 Cursor 在 native 层有未完成的查询 → 阻塞

public class DatabaseHelper {
    public Cursor query() {
        Cursor cursor = sqliteDatabase.rawQuery("SELECT ...", null);
        return cursor;
        // cursor 在 finalize() 中关闭
        // 如果查询未完成 → finalize() 阻塞
    }
}

// 业务代码
Cursor cursor = databaseHelper.query();
cursor.close();  // 显式关闭
// 如果忘记 close() → finalize() 关闭 → 阻塞

// → FinalizerWatchdogDaemon 警告
```

### 6.8.12 真实案例：Theme finalize() 阻塞

```java
// Theme 在 finalize() 中释放资源
public class Theme {
    @Override
    protected void finalize() throws Throwable {
        super.finalize();
        // native 资源释放
        nativeDestroy();
        // 如果 native 资源被占用 → 阻塞
    }
}
```

### 6.8.13 监控 FinalizerWatchdogDaemon

```bash
# 1. 实时监控警告
adb logcat -s "art" | grep "Finalizer"

# 2. 看 FinalizerDaemon 状态
adb shell dumpsys meminfo <package> | grep "Finalizer"

# 3. 看 finalize() 队列长度
adb shell dumpsys meminfo <package> | grep "Finalize"
```

---

## 六、FinalizerWatchdogDaemon 的源码索引

### 6.8.14 核心源码路径

```
libcore/libart/src/main/java/java/lang/Daemons.java                    # Daemon 线程
libcore/ojluni/src/main/java/java/lang/ref/FinalizerReference.java     # FinalizerReference
art/runtime/gc/reference_processor.h                                   # ReferenceProcessor
art/runtime/gc/reference_processor.cc                                  # HandleFinalReferences
```

### 6.8.15 关键函数清单

| 函数 | 文件 | 功能 |
|:---|:---|:---|
| `FinalizerWatchdogDaemon::run` | `Daemons.java` | 监控主循环 |
| `FinalizerWatchdogDaemon::checkFinalizerTimeouts` | `Daemons.java` | 检查超时 |
| `FinalizerDaemon::maxDuration` | `Daemons.java` | 获取当前执行时长 |
| `FinalizerDaemon::finalizeReference` | `Daemons.java` | 执行 finalize() |

### 6.8.16 关键常量

```java
// libcore/libart/src/main/java/java/lang/Daemons.java
private static final int INTERVAL_MS = 1000;  // 1 秒检查间隔
private static final long MAX_FINALIZE_TIME_MS = 10 * 1000;  // 10 秒超时
```

---

## 七、本节小结

1. **FinalizerWatchdogDaemon 每秒检查一次**：INTERVAL_MS = 1000ms
2. **10 秒超时**：MAX_FINALIZE_TIME_MS = 10000ms
3. **只警告不强制**：ART 不 kill 进程
4. **业务层应主动响应**：监控警告 + 主动修复
5. **真实场景**：Cursor / Theme / DirectByteBuffer 的 finalize 可能阻塞

→ **理解 FinalizerWatchdogDaemon，就理解了"如何监控 finalize() 卡死"**。

---

## 跨节引用

**本节被以下章节引用**：
- [6.9 实战案例](./09-实战案例.md) —— Finalizer 卡死完整案例

**本节引用**：
- [6.7 FinalizerDaemon 源码](./07-FinalizerDaemon源码.md) —— FinalizerDaemon 实现
- [6.4 FinalReference](./04-FinalReference.md) —— FinalReference 机制
