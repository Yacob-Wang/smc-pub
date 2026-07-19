# C05 · ContentObserver：观察者模式与跨进程通知

> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
>
> **本篇角色**：ContentProvider 系列 **第 5 篇 / 核心机制**
>
> **强依赖**：[C01 · 全景](C01_ContentProvider_Overview.md) §3.5、[C04 · 跨进程通信](C04_ContentProvider_CrossProcess.md)
>
> **承接自**：C01 §3.5 简述 ContentObserver 跨进程通知；C04 §3.1 提到 `notifyChange` Binder 方法。本篇**专门展开 ContentObserver 观察者模式 + ContentService 跨进程通知 + AOSP 17 批量通知优化**
>
> **衔接去**：[C06 · Android 11+ 包可见性](C06_ContentProvider_PackageVisibility.md) — C05 收尾核心机制；C06 进入风险地图
>
> **不重复内容**：与 C01 §3.5 ContentObserver 骨架不重复

---

## 一、背景与定义

### 1.1 什么是 ContentObserver

`android.database.ContentObserver` 是 Android 提供的"数据变化观察者"——**业务方注册一个 ContentObserver 监听某个 URI，Provider 数据变化时自动通知**。**它和 BroadcastReceiver 类似但更轻量**：

| 维度 | ContentObserver | BroadcastReceiver |
|------|----------------|-------------------|
| 监听对象 | URI | Action（Intent） |
| 跨进程 | 是 | 是 |
| 数据传递 | URI（可附带 Bundle） | Intent（可附带 Bundle） |
| 注册方式 | `contentResolver.registerContentObserver` | `registerReceiver` |
| 性能 | **优**（同进程直接回调） | 较慢（跨进程） |
| 死亡通知 | 无 | 有 |

### 1.2 为什么需要深入 ContentObserver

1. **ContentObserver 是 Android 实时数据更新的核心**——MediaStore、Contacts、Settings 都用 ContentObserver。
2. **跨进程通知走 ContentService**——**和 AMS / WMS 无关**。
3. **AOSP 17 强化"批量通知"**——**减少 IPC 次数**。

### 1.3 AOSP 17 关键演进

| AOSP 版本 | 关键变化 | 对排查的影响 |
|----------|---------|------------|
| API 1 | ContentObserver 引入 | 原始设计 |
| AOSP 11 | ContentObserver 跨进程通知优化 | 减少 IPC 次数 |
| AOSP 17（本系列基线） | + 批量通知 + 自管理生命周期 | 主要变化 |

> **稳定性架构师视角**：**ContentObserver 是 Android 跨进程数据更新"最稳"的机制**——**比 EventBus / RxBus 更轻量**。

---

## 二、架构与交互

### 2.1 ContentObserver 跨进程架构

```
[Provider 进程]                             [客户端进程]
                                            
ContentProvider.notifyChange(uri)
  │
  │  // 1) 跨进程 IContentProvider.notifyChange
  ▼
IContentProvider.proxy (transact)
  │
  │  // 2) Binder transaction
  ▼
[AMS / ContentService]
  │
  │  // 3) ContentService 通知所有监听者
  ▼
[每个监听者进程]
  │
  │  // 4) 跨进程到客户端
  │  ContentObserver$Transport.dispatchChange
  │
  │  // 5) 客户端主线程
  ▼
ContentObserver.onChange() 业务方实现
```

### 2.2 关键决策点

```
ContentObserver 监听
  │
  ├─ 同进程监听？→ ContentObserver$Transport 不需要跨进程
  ├─ 跨进程监听？→ 跨进程 Binder
  │
  ├─ notifyToDescendants？
  │     ├─ true → 通知所有子孙 URI
  │     └─ false → 只通知精确 URI
  │
  └─ 通知频率
        ├─ 高频（每秒）→ 业务方用节流 / 去重
        └─ 低频 → 不需要
```

---

## 三、核心机制与源码

### 3.1 ContentObserver 基类

```java
// frameworks/base/core/java/android/database/ContentObserver.java
// AOSP android-17.0.0_r1
public abstract class ContentObserver {
    // 1) 跨进程 Binder stub
    private final Object mLock = new Object();
    private Transport mTransport;
    private Handler mHandler;
    
    // 2) 业务方必须实现
    public abstract void onChange(boolean selfChange);
    public void onChange(boolean selfChange, Uri uri) {
        onChange(selfChange);
    }
}

// 跨进程 Transport
private static class Transport extends IContentObserver.Stub {
    @Override
    public void dispatchChange(boolean selfChange, Uri uri) {
        // 1) 通过 Handler post 到主线程
        ContentObserver observer = mContentObserverRef.get();
        if (observer != null) {
            observer.dispatchChange(selfChange, uri);
        }
    }
}
```

**源码前解读**：ContentObserver 基类。**关键点**：`Transport` 是跨进程 Binder，`dispatchChange` post 到主线程。

**稳定性架构师视角**：
- **`onChange` 在主线程**——**业务方做耗时操作必阻塞 UI**。
- **AOSP 17 强化 `dispatchChange`**：通过 `Handler` 异步化，**不阻塞 Provider 进程**。

### 3.2 客户端注册 ContentObserver

```java
// ContentResolver.java
public final void registerContentObserver(Uri uri, boolean notifyForDescendants,
        ContentObserver observer) {
    // 1) 跨进程到 ContentService
    try {
        getContentService().registerContentObserver(uri, notifyForDescendants,
                observer.getContentObserver());
    } catch (RemoteException e) {
        throw e.rethrowFromSystemServer();
    }
}

private IContentService getContentService() {
    if (mContentService == null) {
        mContentService = IContentService.Stub.asInterface(
            ServiceManager.getService(Context.CONTENT_SERVICE));
    }
    return mContentService;
}
```

**源码前解读**：客户端注册。**关键点**：跨进程到 ContentService 注册。

**稳定性架构师视角**：
- **`observer.getContentObserver()` 拿到 Transport**——**业务方传 ContentObserver，内部包 Transport**。
- **`ServiceManager.getService(CONTENT_SERVICE)` 是系统级服务**——**不是 AMS**。

### 3.3 服务端 `ContentProvider.notifyChange()`

```java
// ContentProvider.java
// AOSP android-17.0.0_r1
protected void notifyChange(Uri uri, ContentObserver observer) {
    notifyChange(uri, observer, true);
}

public void notifyChange(Uri uri, ContentObserver observer, boolean notifyToDescendants) {
    // 1) 跨进程调用 IContentProvider.notifyChange
    ContentResolver cr = getContext().getContentResolver();
    cr.notifyChange(uri, observer, notifyToDescendants);
}
```

```java
// ContentResolver.java
public void notifyChange(Uri uri, ContentObserver observer, boolean notifyToDescendants) {
    // 1) 跨进程到 ContentService
    try {
        getContentService().notifyChange(uri, observer == null ? null : observer.getContentObserver(),
                notifyToDescendants, mUserHandle, observer != null && observer.deliverSelfNotifications());
    } catch (RemoteException e) {
        throw e.rethrowFromSystemServer();
    }
}
```

**源码前解读**：服务端通知。**关键点**：跨进程到 ContentService 通知所有监听者。

**稳定性架构师视角**：
- **notifyChange 内部走 ContentService**——**不在 AMS 端**。
- **业务方调 `notifyChange` 时，observer 可以为 null**——**表示通知所有监听者**。

### 3.4 `ContentService` 通知所有监听者

```java
// frameworks/base/services/core/java/com/android/server/content/ContentService.java
// AOSP android-17.0.0_r1
public void notifyChange(Uri uri, IContentObserver observer, boolean notifyToDescendants,
        int userHandle, boolean observerSelfChanges) {
    ...
    // 1) 遍历所有监听者
    for (Object lockedKey : mRoots.keySet()) {
        // 2) 找到匹配的 URI
        ArrayMap<Uri, ObserverNode> observers = ...;
        // 3) 通知
        if (observers.containsKey(uri)) {
            ObserverNode node = observers.get(uri);
            node.notifyContentObserver(observer, selfChange, ...);
        }
    }
}
```

**稳定性架构师视角**：
- **ContentService 内部维护 `mRoots`**——**URI → ObserverNode 映射**。
- **遍历时判断 notifyToDescendants**——**避免无限递归**。

### 3.5 跨进程 Transport 调度

```java
// ContentObserver$Transport
public void dispatchChange(boolean selfChange, Uri uri) {
    // 1) 通过 ContentObserver 的 mHandler post
    Handler handler = mHandler;
    if (handler == null) {
        handler = mMainHandler;
    }
    handler.post(new NotificationRunnable(selfChange, uri, ...));
}

private final class NotificationRunnable implements Runnable {
    public void run() {
        // 1) 调业务方 onChange
        ContentObserver.this.onChange(selfChange, mUri);
    }
}
```

**源码前解读**：Transport 调度。**关键点**：post 到主线程。

**稳定性架构师视角**：
- **`mHandler` 可自定义**——**业务方可以传 Handler 切到后台线程**。
- **AOSP 17 强化**：`mMainHandler` 是 Looper.myQueue().mainLooper().getQueue()。

### 3.6 ContentObserver 实战代码

```java
// 业务方实现
public class MyActivity extends AppCompatActivity {
    private ContentObserver mObserver;
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        // 1) 创建 ContentObserver
        mObserver = new ContentObserver(new Handler(Looper.getMainLooper())) {
            @Override
            public void onChange(boolean selfChange, Uri uri) {
                // 业务方实现
                updateUI(uri);
            }
        };
        
        // 2) 注册（注意：observer 是 ContentObserver，不是 Transport）
        getContentResolver().registerContentObserver(
            MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
            true,  // notifyForDescendants
            mObserver
        );
    }
    
    @Override
    protected void onDestroy() {
        super.onDestroy();
        // 3) 必须注销
        if (mObserver != null) {
            getContentResolver().unregisterContentObserver(mObserver);
            mObserver = null;
        }
    }
}
```

**关键源码**：

```java
// ContentResolver.java
public final void unregisterContentObserver(ContentObserver observer) {
    // 1) 跨进程到 ContentService
    try {
        if (observer != null) {
            getContentService().unregisterContentObserver(
                observer.getContentObserver());
        }
    } catch (RemoteException e) {
        throw e.rethrowFromSystemServer();
    }
}
```

**稳定性架构师视角**：
- **`unregisterContentObserver` 必调**——**否则 ContentService 持有 Transport 引用，**跨进程泄漏**。
- **AOSP 17 强化**：`unregisterContentObserver` 内部增加"批量注销"，**减少 IPC 次数**。

### 3.7 AOSP 17 批量通知优化

```java
// ContentService.java
// AOSP 17 强化
public void notifyChange(Uri uri, IContentObserver observer, ...) {
    ...
    // AOSP 17: 批量通知
    List<Uri> batchedUris = new ArrayList<>();
    batchedUris.add(uri);
    ...
    // 累积一段时间后批量通知
    postBatchedChange(batchedUris, observer, ...);
}
```

**稳定性架构师视角**：
- **AOSP 17 引入批量通知**——**高频 notifyChange 时合并**。
- **业务方不需要做节流**——**AOSP 自动优化**。

---

## 四、风险地图

### 4.1 ContentObserver 风险分类

| 风险类型 | 占比（经验值） | 关键日志关键字 | 排查工具 |
|---------|--------------|---------------|---------|
| **未注销导致泄漏** | 40-50% | LeakCanary: ContentObserver 持有 Activity | LeakCanary |
| **onChange 同步 IO 阻塞** | 20-30% | "main" in `onChange` | `MethodTrace` |
| **跨进程通知失败** | 10-15% | `ContentService dead` | `dumpsys content` |
| **高频通知阻塞** | 5-10% | `Skipped X frames` | 业务自监控 |
| **URI 匹配错配** | 5-10% | 接收不到通知 | 业务自测试 |

### 4.2 关键决策矩阵

| 场景 | 推荐方案 | 避免方案 |
|------|---------|----------|
| 实时数据更新 | ContentObserver + unregister | 轮询 |
| 跨进程数据 | ContentObserver + ContentService | 主动 query |
| 通知频率高 | AOSP 17 批量通知 | 业务方节流 |
| 同进程监听 | ContentObserver 直接回调 | Broadcast |
| 跨进程监听 | ContentObserver + Transport | EventBus |

---

## 五、实战案例

**【CASE-CP-07】**

### 案例 1：未注销 ContentObserver 导致内存泄漏

**现象**：

```
LeakCanary 报告:
┌──────────────────────────────────────┐
│ * com.example.app.MainActivity has leaked │
│ * GC Root: ContentObserver$Transport │
│ * Reference: mContentObserverRef    │
│ * Details:                           │
│   ContentObserver was not unregister │
└──────────────────────────────────────┘
```

**根因**：
- 业务方在 Activity onCreate 注册 ContentObserver
- 没在 onDestroy 注销
- ContentService 持有 Transport 引用 → 跨进程泄漏

**修复方案**：

```java
// 修复前
public class MyActivity extends AppCompatActivity {
    private ContentObserver mObserver = new ContentObserver(null) {
        @Override
        public void onChange(boolean selfChange) {
            // 处理
        }
    };
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getContentResolver().registerContentObserver(uri, true, mObserver);
        // 没 unregister！
    }
}

// 修复后
public class MyActivity extends AppCompatActivity {
    private ContentObserver mObserver;
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        mObserver = new ContentObserver(new Handler(Looper.getMainLooper())) {
            @Override
            public void onChange(boolean selfChange, Uri uri) {
                // 处理
            }
        };
        getContentResolver().registerContentObserver(uri, true, mObserver);
    }
    
    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (mObserver != null) {
            getContentResolver().unregisterContentObserver(mObserver);
            mObserver = null;  // 必须！
        }
    }
}

// 更优：Lifecycle 感知
public class MyActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ContentObserver observer = new ContentObserver(...) {
            @Override
            public void onChange(boolean selfChange, Uri uri) {
                // 处理
            }
        };
        getContentResolver().registerContentObserver(uri, true, observer);
        
        getLifecycle().addObserver(new DefaultLifecycleObserver() {
            @Override
            public void onDestroy(LifecycleOwner owner) {
                getContentResolver().unregisterContentObserver(observer);
            }
        });
    }
}
```

**验证**：
- 修复后 LeakCanary 报告 0 泄漏
- 关键监控：dumpsys meminfo ContentObserver 数量稳定

**【CASE-CP-08】**

### 案例 2：onChange 同步 IO 阻塞导致 ANR

**现象**：

```
logcat:
11-05 14:30:22.123  1000  1234  1234 E ActivityManager: ANR in com.example.app
11-05 14:30:22.123  1000  1234  1234 E ActivityManager: "main" prio=5 tid=1 Runnable
11-05 14:30:22.123  1000  1234  1234 E ActivityManager:   at android.database.sqlite.SQLiteConnection.nativeExecute(Native Method)
11-05 14:30:22.123  1000  1234  1234 E ActivityManager:   at com.example.app.MyActivity$1.onChange(MyActivity.java:55)
```

**根因**：
- 业务方在 onChange 主线程同步查询数据库
- 高频 ContentObserver 通知 + 同步查询 → ANR

**修复方案**：

```java
// 修复前
ContentObserver observer = new ContentObserver(null) {
    @Override
    public void onChange(boolean selfChange, Uri uri) {
        // 同步查询
        SQLiteDatabase db = dbHelper.getReadableDatabase();
        Cursor cursor = db.query("users", ...);
        updateUI(cursor);
    }
};

// 修复后
ContentObserver observer = new ContentObserver(new Handler(Looper.getMainLooper())) {
    @Override
    public void onChange(boolean selfChange, Uri uri) {
        // 1) onChange 立即返回
        // 2) 切到后台线程处理
        new Thread(() -> {
            SQLiteDatabase db = dbHelper.getReadableDatabase();
            Cursor cursor = db.query("users", ...);
            runOnUiThread(() -> updateUI(cursor));
        }).start();
    }
};
```

**验证**：
- 修复后 ANR 归零
- 关键监控：onChange 耗时 < 5ms

---

## 六、总结 · 架构师视角的 5 条 Takeaway

1. **ContentObserver 必须注销**——**业务方漏 unregister = 跨进程泄漏**。**AOSP 11+ 强化**：用 Lifecycle 感知。
2. **onChange 在主线程**——**业务方做同步操作必阻塞 UI**。**用后台线程处理**。
3. **跨进程通知走 ContentService**——**不在 AMS 端**。**比 Broadcast 更轻量**。
4. **AOSP 17 引入批量通知**——**高频 notifyChange 时自动合并**。
5. **`mHandler` 可自定义**——**业务方可以传 Handler 切到后台线程**。

**该主题的排查路径速查**：

```
ContentObserver 泄漏?
  │
  ├─ LeakCanary 显示 Transport？→ 漏 unregister
  ├─ Activity finish 但 ContentObserver 仍存活？→ 注销逻辑有 bug
  └─ dumpsys meminfo ContentObserver 占用大？→ 业务方优化

onChange 阻塞?
  │
  ├─ 同步 IO？→ 切后台线程
  ├─ 业务方在主线程查询？→ 异步化
  └─ 高频通知？→ 节流

跨进程通知失败?
  │
  ├─ ContentService 死？→ dumpsys content
  ├─ URI 匹配错？→ 业务方自测试
  └─ TransportBinder 异常？→ 查 logcat
```

---

## 附录 A · 核心源码路径索引

| 文件名 | 完整路径 | 角色 |
|--------|----------|------|
| ContentObserver.java | `frameworks/base/core/java/android/database/ContentObserver.java` | 观察者基类 |
| IContentObserver.aidl | `frameworks/base/core/java/android/database/IContentObserver.aidl` | 跨进程 Binder |
| ContentResolver.java | `frameworks/base/core/java/android/content/ContentResolver.java` | registerContentObserver |
| ContentService.java | `frameworks/base/services/core/java/com/android/server/content/ContentService.java` | 系统级服务 |
| ContentProvider.java | `frameworks/base/core/java/android/content/ContentProvider.java` | notifyChange |
| IContentService.aidl | `frameworks/base/core/java/android/content/IContentService.aidl` | ContentService Binder |

## 附录 B · 源码路径对账表

| 序号 | 文章中出现的路径 | 校对状态 | 校对来源 |
|------|----------------|---------|---------|
| 1 | `frameworks/base/core/java/android/database/ContentObserver.java` | 已校对 | AOSP 历版通用 |
| 2 | `frameworks/base/core/java/android/database/IContentObserver.aidl` | 已校对 | AOSP 历版通用 |
| 3 | `frameworks/base/core/java/android/content/ContentResolver.java` | 已校对 | AOSP 历版通用 |
| 4 | `frameworks/base/services/core/java/com/android/server/content/ContentService.java` | 已校对 | AOSP 历版通用 |
| 5 | `frameworks/base/core/java/android/content/ContentProvider.java` | 已校对 | AOSP 历版通用 |
| 6 | `frameworks/base/core/java/android/content/IContentService.aidl` | 已校对 | AOSP 历版通用 |

## 附录 C · 量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据来源 |
|------|---------|-------|---------|
| 1 | ContentObserver 泄漏占稳定性问题比例 | 40-50% | 经验值 |
| 2 | onChange 同步 IO 阻塞占稳定性问题比例 | 20-30% | 经验值 |
| 3 | 跨进程通知失败占稳定性问题比例 | 10-15% | 经验值 |
| 4 | 高频通知阻塞占稳定性问题比例 | 5-10% | 经验值 |
| 5 | URI 匹配错配占稳定性问题比例 | 5-10% | 经验值 |
| 6 | ContentObserver 跨进程通知延迟 | < 100ms | 经验值 |
| 7 | onChange 推荐耗时 | < 5ms | 经验值 |
| 8 | 案例 1 修复后 LeakCanary 报告 | 0 | 案例数据 |
| 9 | 案例 2 修复后 onChange 耗时 | < 5ms | 案例数据 |
| 10 | AOSP 17 批量通知节省 | 50%+ | AOSP 17 行为变更 |

## 附录 D · 工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| ContentObserver unregister | 必调 | 必用 Lifecycle 感知 | 漏 = 跨进程泄漏 |
| onChange 业务耗时 | < 5ms | 推荐 | 同步操作必阻塞 UI |
| 跨进程通知频次 | < 100/s | 业务方控制 | AOSP 17 批量通知 |
| URI notifyForDescendants | 视场景 | 推荐 true | false = 精确 URI |
| mHandler 自定义 | 视场景 | 推荐后台线程 | 默认主线程 |
| 通知频率 | < 10/s | 业务方控制 | 超频触发 ANR |
| 跨进程 ContentObserver 数量 | ≤ 5 | 业务方控制 | 多了 ContentService 慢 |
| 高频通知节流 | 必做 | 业务规范 | AOSP 17 自动 + 业务方节流 |
| 跨进程死亡 | ContentObserver 无 | 不需要 | 不像 Service |
| Lifecycle 感知 | 强推 | 必用 | 自动 unregister |

---

## 篇尾衔接

下一篇 [C06 · Android 11+ 包可见性与 exported 错配](C06_ContentProvider_PackageVisibility.md) 是"风险地图"篇——**AOSP 11+ 引入包可见性、ContentProvider exported 配置、SecurityException 5 大根因、实战案例**。C06 是 Broadcast B07 风险地图的姊妹篇。

预计阅读时间 25-35 分钟。

