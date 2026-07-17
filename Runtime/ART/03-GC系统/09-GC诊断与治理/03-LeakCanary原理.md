# 9.3 LeakCanary 的实现原理

> **本节回答一个根本问题**：LeakCanary 怎么检测内存泄漏？完整工作流是什么？Shark 引擎怎么加速？
>
> **答案**：**WeakReference + ReferenceQueue + Heap Dump + 5 秒延迟检测** —— LeakCanary 的完整机制。

---

## 一、LeakCanary 概述

### 9.3.1 LeakCanary 的版本演进

```
LeakCanary 版本：

1.x（2019 之前）：
  - 基于 Heap Dump + MAT 分析
  - 慢（生成 hprof 慢，分析慢）
  - 仅 debug 启用

2.x（2019+）：
  - Shark 引擎（自定义 hprof 解析）
  - 快（解析比 MAT 快 10 倍）
  - 支持 Android 11+ Heap Dump API（无需 hprof 文件）

3.x（2023+）：
  - 进一步优化
  - 支持 LeakCanary Android Test
  - CI 友好
```

### 9.3.2 LeakCanary 的依赖

```groovy
// app/build.gradle
dependencies {
    // LeakCanary debug（仅 debug 启用）
    debugImplementation 'com.squareup.leakcanary:leakcanary-android:2.14'
    
    // LeakCanary Android Test（CI 友好）
    androidTestImplementation 'com.squareup.leakcanary:leakcanary-android-instrumentation:2.14'
}
```

### 9.3.3 LeakCanary 的核心原理

```
LeakCanary 检测内存泄漏的核心原理：

1. 监控对象销毁
   - Activity.onDestroy
   - Fragment.onDestroy
   - View.onDetachedFromWindow

2. 用 WeakReference 包装已销毁对象
   - 让 GC 能回收已销毁对象（如果正确清理）
   - 如果对象未被回收 → 泄漏

3. 延迟检测（5 秒后）
   - 手动触发 GC
   - 检查 WeakReference.get()
   - 还非 null → 泄漏

4. 触发 Heap Dump
   - 用 LeakCanary 的 HeapDumper
   - 或 Android 11+ 的 Heap Dump API

5. 分析 Heap Dump
   - Shark 引擎解析 hprof
   - 找出泄漏链（GC Root → 泄漏对象）

6. 报告 + 修复
   - Logcat 输出泄漏链
   - 通知开发者修复
```

---

## 二、LeakCanary 的详细工作流

### 9.3.4 完整工作流

```
Activity.onDestroy() 被调用
    ↓
1. LeakCanary 检测到 Activity 销毁
   │
   ↓
2. 创建 KeyedWeakReference 包装 Activity
   │  KeyedWeakReference 是 WeakReference 的子类
   │  添加到 retainedObjects 列表
   │
   ↓
3. 5 秒后检查（默认）
   │
   ↓
4. 触发 GC
   │  Runtime.getRuntime().gc()
   │  Thread.sleep(100)  // 等 GC 完成
   │
   ↓
5. 检查 WeakReference.get()
   │
   ├── null → 对象被正确回收 → OK
   │
   └── 非 null → 泄漏！
       │
       ↓
6. 触发 Heap Dump
       │
       ↓
7. Shark 引擎分析 hprof
   │  找出泄漏链（GC Root → 泄漏对象）
   │
   ↓
8. 报告泄漏
   │  Logcat 输出
   │  Notification 通知（可选）
   │
   ↓
9. 开发者修复
```

### 9.3.5 LeakCanary 的对象监控

```java
// LeakCanary 自动监控的对象：
// 1. Activity（通过 ActivityLifecycleCallbacks）
// 2. Fragment（通过 FragmentLifecycleCallbacks）
// 3. ViewModel（通过 ViewModelStore）
// 4. RootView（通过 Window）
// 5. Service（通过 ServiceConnection）

// 自定义监控：
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        
        // 监控自定义对象
        LeakCanary.INSTANCE.monitorObject("MyObject", myObject);
    }
}
```

---

## 三、KeyedWeakReference 的实现

### 9.3.6 KeyedWeakReference 的定义

```java
// LeakCanary 的 KeyedWeakReference 类
public class KeyedWeakReference extends WeakReference<Object> {
    private final String key;
    private final String name;
    private final long watchUptimeMillis;
    
    KeyedWeakReference(Object referent, String key, String name, long watchUptimeMillis) {
        super(referent);
        this.key = key;
        this.name = name;
        this.watchUptimeMillis = watchUptimeMillis;
    }
    
    public String getKey() {
        return key;
    }
}
```

### 9.3.7 KeyedWeakReference 的工作原理

```
KeyedWeakReference 的工作原理：

1. 包装已销毁对象
   KeyedWeakReference ref = new KeyedWeakReference(activity, "Activity#1", "Activity", ...);

2. 加入 retainedObjects
   retainedObjects.add(ref);

3. 5 秒后检查
   if (ref.get() != null) {
       // 泄漏！
   }

4. 触发 Heap Dump
   // 找出所有 KeyedWeakReference
   // 通过 key 匹配具体泄漏对象

5. 分析泄漏链
   // Shark 引擎找出 GC Root → KeyedWeakReference → LeakActivity 的路径
```

---

## 四、Shark 引擎

### 9.3.4 Shark 引擎的原理

```
Shark 引擎（Heap Dump 分析引擎）：

1. 解析 hprof
   - 自定义的 hprof 解析器（比 MAT 快 10 倍）
   - 支持 Android 11+ Heap Dump API（无需生成 hprof 文件）

2. 构建对象图
   - 找出所有对象的引用关系
   - 计算 Retained Heap（保留堆）

3. 找泄漏链
   - 从 GC Root 出发
   - 找出到泄漏对象的路径
   - 输出最短路径

4. 性能优化
   - 增量分析
   - 内存映射文件
   - 多线程并行
```

### 9.3.5 Shark 引擎 vs MAT

| 维度 | Shark 引擎 | MAT |
|:---|:---|:---|
| **解析速度** | 快（10x） | 慢 |
| **内存占用** | 小（流式处理） | 大（一次性加载） |
| **分析能力** | 找泄漏链 | 全功能（OQL、Retained Heap 等） |
| **使用方式** | 集成在 LeakCanary | 独立工具 |
| **适用场景** | 自动监控 | 深度分析 |

### 9.3.6 Shark 引擎的输出

```log
# LeakCanary 检测到泄漏的 Logcat 输出示例
# 示例输出（简化）：
====================================
HEAP ANALYSIS RESULT
====================================
1 Application instances found.
0 Activity instances found.

┬───
│ GC Root: System class
│
├─ com.example.MyApplication instance
│   Leaking: NO (regular instance)
│
├─ com.example.StaticHelper class
│   Leaking: UNKNOWN
│
└─ android.app.ActivityThread instance
    Leaking: NO (regular instance)

┬───
│ GC Root: Local variable in native code
│
├─ java.lang.Thread instance
│   Leaking: NO (regular instance)
│
└─ android.os.HandlerThread instance
    Leaking: YES (Object was never GCed)
    Retained Heap: 5.2 MB
====================================
```

---

## 五、Android 11+ Heap Dump API

### 9.3.7 Heap Dump API 的演进

```
Heap Dump API 的演进：

Android 11 之前：
  - 必须生成 hprof 文件
  - 文件可能很大（数十 MB）
  - 需要写入磁盘

Android 11+：
  - 提供 Heap Dump API
  - 不需要生成 hprof 文件
  - 直接在内存中读取
  - LeakCanary 2.6+ 支持
```

### 9.3.8 Heap Dump API 的使用

```java
// Android 11+ 的 Heap Dump API
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
    // 直接获取 Heap Dump
    HeapDump heapDump = Debug.dumpHeap();
    
    // LeakCanary 使用这个 API
    // Shark 引擎解析 HeapDump
}
```

### 9.3.9 Heap Dump API 的优势

```
Heap Dump API 的优势：

1. 速度快
   - 不需要写磁盘
   - 直接内存中读取

2. 占用少
   - 不需要 hprof 文件
   - 内存占用低

3. 实时性
   - 不需要等待文件生成
   - 分析可以实时进行
```

---

## 六、LeakCanary 的工程配置

### 9.3.10 LeakCanary 的配置

```java
public class MyApplication extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        
        // 自定义 LeakCanary 配置
        LeakCanary.INSTANCE.setConfig(new LeakCanary.Config()
            .dumpHeap(BuildConfig.DEBUG)  // 是否 dump heap
            .leakWatcher(new LeakWatcher() {
                @Override
                public void watch(Object watchedObject, String description) {
                    // 自定义监控逻辑
                }
            })
        );
    }
}
```

### 9.3.11 LeakCanary 的发布构建

```groovy
// build.gradle
buildTypes {
    debug {
        // Debug 启用 LeakCanary
        // 自动通过依赖添加
    }
    release {
        // Release 不启用 LeakCanary
        // 但可以通过 LeakCanary Android Test 监控
    }
}
```

### 9.3.12 LeakCanary Android Test（CI 友好）

```java
// LeakCanary Android Test 示例
@RunWith(AndroidJUnit4.class)
public class MyLeakTest {
    @Test
    public void testNoLeaks() {
        Activity activity = startActivity();
        activity.finish();
        
        // LeakCanary 检测泄漏
        LeakCanary.verifyNoLeaks(activity);
    }
}
```

---

## 七、LeakCanary 的工程实践

### 9.3.13 LeakCanary 的常见误报

```
LeakCanary 的常见误报：

1. Activity 被系统持有
   - 系统在某些场景下持有 Activity
   - LeakCanary 误判为泄漏

2. Fragment 在 ViewModel 中持有
   - ViewModel 保存 Fragment 引用
   - 误判为泄漏

3. 静态字段持有 Context
   - 静态字段引用 Activity Context
   - 误判为泄漏（实际可能是故意的）

→ LeakCanary 提供"忽略规则"，避免误报
```

### 9.3.14 LeakCanary 的忽略规则

```java
// 忽略特定的泄漏
LeakCanary.INSTANCE.setConfig(new LeakCanary.Config()
    .leakIgnoredFilters(new IgnoringFilter[] {
        // 忽略系统类
        IgnoringFilter.ofClass("android.app.ActivityThread"),
        IgnoringFilter.ofClass("com.example.LegacyLeakyClass"),
    })
);
```

### 9.3.15 LeakCanary 与 CI 集成

```yaml
# CI 配置示例
- name: Run LeakCanary tests
  run: ./gradlew :app:connectedLeakCanaryDebugAndroidTest
```

---

## 八、本节小结

1. **LeakCanary 用 WeakReference 检测泄漏**：5 秒后检查
2. **完整工作流**：监控对象销毁 → WeakReference → 5 秒检查 → Heap Dump → Shark 分析 → 报告
3. **Shark 引擎比 MAT 快 10 倍**：流式处理 + 自定义 hprof 解析
4. **Android 11+ Heap Dump API**：无需生成 hprof 文件
5. **CI 友好**：LeakCanary Android Test 集成

→ **理解 LeakCanary，就掌握了"自动内存泄漏检测"的工具**。

---

## 跨节引用

**本节被以下章节引用**：
- [9.4 MAT](./04-MAT使用指南.md) —— 深度分析工具
- [9.10 实战案例 2](./10-实战案例2-APM搭建.md) —— 集成到 APM
- 06 篇 6.3 WeakReference —— LeakCanary 的基础

**本节引用**：
- 06 篇 6.3 WeakReference —— WeakReference
- 02 篇 2.2 5 Space 详解 —— Image / Zygote
