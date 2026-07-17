# 9.9 实战案例 1：从 dumpsys 到 Heap Dump 完整诊断

> **本节回答一个根本问题**：线上 App 出现内存问题，怎么从零开始排查？完整诊断流程是什么？
>
> **答案**：**dumpsys 概览 → smaps 详细 → Heap Dump → MAT 分析** —— 四步定位法。

---

## 一、案例背景

### 9.9.1 案例描述

```
案例描述：

App：某社交 App（类微信）
问题：
- 用户反馈：进入聊天页面后，再回到首页，内存持续增长
- 多次进出后内存不释放，最终 OOM 闪退
- 发生时间：进入聊天页面 5 次以上

诊断目标：
- 找到内存增长的根本原因
- 定位泄漏的具体位置
- 提出修复方案
```

### 9.9.2 排查思路

```
排查思路（四步定位法）：

1. dumpsys meminfo：看内存概览（分类）
2. procrank / smaps：看进程级内存（详细）
3. LeakCanary：自动检测泄漏
4. Heap Dump + MAT：深度分析引用链

→ 四步递进，从概览到细节
```

---

## 二、第一步：dumpsys meminfo

### 9.9.3 抓取 dumpsys meminfo

```bash
# 抓取 dumpsys meminfo
adb shell dumpsys meminfo <package_name> > meminfo.txt

# 输出示例（简化）：
Applications Memory Usage (kB):
Uptime: 1234567 Realtime: 1234567

Total PSS by process:
    123456 kB: com.example.app (pid 12345)

Total PSS by OOM adjustment:
    ... ...

Total PSS by category:
    102400 kB: Dalvik
    204800 kB: Native
     51200 kB: .so mmap
    ... ...

Total Swap: 0 kB

Dalvik Heap:
   Pss Total:    102400 kB
   Heap Alloc:    81920 kB
   Heap Free:     20480 kB
   Heap Size:    102400 kB
   Heap Free %:    20.0%

Native Heap:
   Pss Total:    204800 kB
   Heap Alloc:   163840 kB
   Heap Free:     40960 kB
   Heap Size:    204800 kB
   Heap Free %:    20.0%

Views:    1234    ViewRootImpl:    12
AppContexts:    4    Activities:    5
Assets:    12    AssetManagers:    0
Local Binders:   34    Proxy Binders:    12
Parcel memory:    4 kB    Parcel count:    24
Death Recipients:    0    OpenSSL Sockets:    0

SQL:
    0 kB: MEMORY_USED
   12 kB: PAGECACHE_OVERFLOW
    ... ...
```

### 9.9.4 分析 dumpsys 输出

```
关键观察：

1. Activities: 5（异常！）
   - App 应该只显示 1 个 Activity（首页）
   - 5 个 Activity 都在内存中 → 泄漏

2. ViewRootImpl: 12（异常）
   - 应该与 Activity 数相同
   - 12 个 ViewRootImpl → 泄漏

3. Java Heap Alloc: 81920 kB（80MB）
   - 较大，可能有大量对象

4. Native Heap Alloc: 163840 kB（160MB）
   - 较大，可能有 native 泄漏或大图片
```

### 9.9.5 dumpsys 结论

```
dumpsys 阶段结论：

- Java 堆 80MB，native 堆 160MB
- Activities 数 = 5（异常，应为 1）
- ViewRootImpl 数 = 12（异常）
- 高度怀疑 Activity 泄漏

→ 下一步：Heap Dump + LeakCanary 验证
```

---

## 三、第二步：Heap Dump

### 9.10.6 抓取 Heap Dump

```bash
# 方法 1：通过 am dumpheap（Android 7+）
adb shell am dumpheap <pid> /data/local/tmp/heap.hprof
adb pull /data/local/tmp/heap.hprof

# 方法 2：Android Studio Profiler
# Memory 面板 → Dump Java Heap

# 方法 3：Debug.dumpHprofData()（应用内）
Debug.dumpHprofData("/data/local/tmp/heap.hprof");
```

### 9.10.7 hprof-conv 转换

```bash
# Android 格式 hprof → Java SE 格式（MAT 需要）
hprof-conv heap.hprof heap-conv.hprof
```

### 9.10.8 MAT 分析

```
MAT 分析步骤：

1. File → Open Heap Dump → heap-conv.hprof
2. 等待解析（5 分钟）
3. Leak Suspects → 查看自动报告
4. Dominator Tree → 按 Retained Heap 排序
5. Histogram → 按类统计实例数
```

### 9.10.9 MAT 发现

```
MAT 关键发现：

1. Activities: 5 个
   - 5 个 com.example.app.ChatActivity
   - 应该是 0 个（已 finish）
   - 全部是泄漏对象

2. Dominator Tree:
   - 顶层是一个 ChatManager 单例
   - Retained Heap 50MB
   - 包含：5 个 ChatActivity + Bitmap + ...

3. OQL 查询：
   SELECT a FROM com.example.app.ChatActivity a
   - 5 个实例
   - 全部被 ChatManager 持有
```

### 9.10.10 引用链

```
MAT 引用链（GC Root → ChatActivity）：

ChatManager（静态单例）
  → List<ChatSession> mSessions
    → ChatSession
      → Context（ContextImpl）
        → ChatActivity（泄漏）

→ ChatManager 是单例，静态引用 ChatSession，ChatSession 持有 Context
→ Activity finish 后仍被持有 → 泄漏
```

---

## 四、第三步：LeakCanary 验证

### 9.10.11 LeakCanary 自动检测

```java
// LeakCanary 自动监控 ChatActivity
public class ChatActivity extends Activity {
    @Override
    protected void onDestroy() {
        super.onDestroy();
        // LeakCanary 自动通过 ActivityLifecycleCallbacks 监控
    }
}
```

### 9.10.12 LeakCanary 输出

```
LeakCanary Logcat 输出：

====================================
HEAP ANALYSIS RESULT
====================================
2  ChatActivity instances found.
0  ChatActivity instances are kept alive.

┬───
│ GC Root: Static field
│
├─ com.example.app.ChatManager class
│   Leaking: NO (a class is never leaking)
│
├─ ChatManager INSTANCE
│   Leaking: UNKNOWN
│
├─ ChatManager.mSessions
│   Leaking: YES (ArrayList retained)
│
└─ java.util.ArrayList instance
    Leaking: YES (Object was never GCed)
    Retained Heap: 50 MB

┬───
│ GC Root: Static field
│
├─ com.example.app.ChatSession class
│
└─ ChatSession instance
    Leaking: YES
    Retained Heap: 10 MB
====================================
```

### 9.10.13 LeakCanary 结论

```
LeakCanary 阶段结论：

- ChatActivity 泄漏 → 被 ChatManager 静态单例持有
- 通过 ChatSession.mContext 引用
- 泄漏链：ChatManager (static) → mSessions → ChatSession → mContext → ChatActivity

→ 与 MAT 分析一致 → 定位成功
```

---

## 五、第四步：定位代码

### 9.10.14 代码定位

```java
// 找到泄漏的代码
public class ChatManager {
    private static ChatManager INSTANCE;
    
    public static ChatManager getInstance() {
        if (INSTANCE == null) {
            INSTANCE = new ChatManager();
        }
        return INSTANCE;
    }
    
    // 泄漏点 1：静态单例
    private final List<ChatSession> mSessions = new ArrayList<>();
    
    public void onSessionCreate(ChatSession session) {
        // 泄漏点 2：ChatSession 持有 Activity Context
        mSessions.add(session);  // session.mContext = ChatActivity
    }
}

public class ChatSession {
    // 泄漏点 3：保存 Activity Context
    public final Context mContext;
    
    public ChatSession(Context context) {
        mContext = context;  // 持有了 Activity Context
    }
}
```

### 9.10.15 泄漏原因

```
泄漏原因：

1. ChatManager 是静态单例
   - 生命周期 = 应用进程
   - 持有的对象不会随 Activity 销毁

2. mSessions 持有 ChatSession
   - ChatSession 持有 Activity Context
   - Context 持有 Activity

3. Activity finish 后无法被回收
   - 因为静态单例 → ChatManager → mSessions → ChatSession → Context → Activity

→ 经典的"static 持有 Activity"泄漏
```

---

## 六、第五步：修复

### 9.10.16 修复方案 1：Activity Context → Application Context

```java
// 修复：使用 Application Context 而非 Activity Context
public class ChatSession {
    // 修改前：public final Context mContext;
    // 修改后：
    private final Context mAppContext;
    
    public ChatSession(Context context) {
        // 修改前：mContext = context;
        // 修改后：
        mAppContext = context.getApplicationContext();
    }
}
```

### 9.10.17 修复方案 2：WeakReference

```java
// 修复：用 WeakReference 持有 Activity
public class ChatSession {
    private final WeakReference<Context> mContextRef;
    
    public ChatSession(Context context) {
        mContextRef = new WeakReference<>(context);
    }
    
    public Context getContext() {
        return mContextRef.get();
    }
}
```

### 9.10.18 修复方案 3：移除 Session

```java
// 修复：Activity finish 时移除 Session
public class ChatManager {
    public void onSessionDestroy(ChatSession session) {
        // 在 Activity.onDestroy 时调用
        mSessions.remove(session);
    }
}

public class ChatActivity extends Activity {
    @Override
    protected void onDestroy() {
        super.onDestroy();
        ChatManager.getInstance().onSessionDestroy(session);
    }
}
```

### 9.10.19 修复方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|:---|:---|:---|:---|
| Application Context | 简单 | 可能丢失 Activity 特性（如 Theme） | 中 |
| WeakReference | 安全 | 需要 null 检查 | 高 |
| 主动移除 | 明确语义 | 需要手动调用 | 高 |

### 9.10.20 最终修复方案

```java
// 最佳实践：WeakReference + 主动移除
public class ChatManager {
    private final List<WeakReference<ChatSession>> mSessions = new ArrayList<>();
    
    public void onSessionCreate(ChatSession session) {
        mSessions.add(new WeakReference<>(session));
    }
    
    public void onSessionDestroy(ChatSession session) {
        // 主动移除
        mSessions.removeIf(ref -> ref.get() == session || ref.get() == null);
    }
    
    // 清理失效引用
    public void cleanUp() {
        mSessions.removeIf(ref -> ref.get() == null);
    }
}
```

---

## 七、第六步：验证

### 9.10.21 修复验证

```bash
# 1. 重新编译 + 安装
./gradlew installDebug

# 2. LeakCanary 自动检测
# - 进入聊天页面 → 退出
# - LeakCanary 不再报错

# 3. Heap Dump 验证
# - 多次进入退出
# - Heap Dump 中 ChatActivity = 0

# 4. dumpsys meminfo
# - Activities 数 = 1（首页）
# - Java Heap Alloc 稳定（不增长）
```

### 9.10.22 验证结果

```
修复后效果：

1. LeakCanary：
   - 不再检测到 ChatActivity 泄漏

2. Heap Dump：
   - ChatActivity 实例数：0
   - ChatSession 实例数：0（被 GC）

3. dumpsys meminfo：
   - Activities：1（稳定）
   - Java Heap：60-70MB（稳定）

4. 用户反馈：
   - 不再出现 OOM 闪退
   - 不再出现内存持续增长
```

---

## 八、本节小结

1. **四步定位法**：dumpsys → Heap Dump → LeakCanary → MAT
2. **典型泄漏**：static 单例持有 Activity Context
3. **修复方案**：Application Context / WeakReference / 主动移除
4. **修复验证**：LeakCanary + Heap Dump + dumpsys 双重验证
5. **效果量化**：泄漏消失 + 内存稳定 + 用户反馈良好

→ **理解完整诊断流程，就掌握了"线上 GC 问题排查"的方法论**。

---

## 跨节引用

**本节被以下章节引用**：
- [9.10 实战案例 2](./10-实战案例2-APM搭建.md) —— 自动化监控

**本节引用**：
- [9.1 dumpsys meminfo](./01-dumpsys-meminfo详解.md) —— 第一步
- [9.2 procrank / smaps](./02-procrank-smaps.md) —— 详细
- [9.3 LeakCanary](./03-LeakCanary原理.md) —— 自动检测
- [9.4 MAT](./04-MAT使用指南.md) —— 深度分析
- 06 篇 6.3 WeakReference —— 修复手段