# Service 面试题大全

## 📋 概述

本文档整理了 Android Service 相关的常见面试题，涵盖基础概念、生命周期、底层实现、性能优化等多个方面。每个问题都附有详细答案和代码示例。

---

## 一、 基础概念类

### Q1: Service 是什么？它和 Activity 有什么区别？

**答案**：

Service 是 Android 四大组件之一，用于在后台执行长时间运行的操作，**不提供用户界面**。

**主要区别**：

| 特性 | Service | Activity |
| :--- | :--- | :--- |
| **用户界面** | 无 UI | 有 UI |
| **生命周期** | 独立于调用方 | 受系统管理 |
| **使用场景** | 后台任务、跨进程通信 | 用户交互界面 |
| **启动方式** | `startService()` / `bindService()` | `startActivity()` |

**代码示例**：

```java
// Service：无 UI，后台执行
public class MyService extends Service {
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // 后台执行任务
        return START_STICKY;
    }
}

// Activity：有 UI，用户交互
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);  // 设置 UI
    }
}
```

---

### Q2: Service 有哪几种类型？它们有什么区别？

**答案**：

Service 可以从多个维度分类：

#### 1. 按启动方式分类

- **Started Service**：通过 `startService()` 启动，独立运行
- **Bound Service**：通过 `bindService()` 绑定，提供客户端-服务器接口
- **Foreground Service**：前台服务，显示通知，优先级高

#### 2. 按进程分类

- **本地 Service**：与调用方在同一进程
- **远程 Service**：运行在独立进程

**代码示例**：

```java
// Started Service
startService(new Intent(this, MyService.class));

// Bound Service
bindService(intent, mConnection, Context.BIND_AUTO_CREATE);

// Foreground Service
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
    startForegroundService(intent);
}
```

---

### Q3: Service 的生命周期是怎样的？

**答案**：

Service 的生命周期取决于启动方式：

#### Started Service 生命周期

```
onCreate() → onStartCommand() → [运行中] → onDestroy()
```

- `onCreate()`：Service 创建时调用，只调用一次
- `onStartCommand()`：每次调用 `startService()` 时调用
- `onDestroy()`：Service 销毁时调用

#### Bound Service 生命周期

```
onCreate() → onBind() → [运行中] → onUnbind() → onDestroy()
```

- `onCreate()`：Service 创建时调用
- `onBind()`：第一次绑定时调用，返回 IBinder
- `onUnbind()`：所有客户端解绑时调用
- `onDestroy()`：Service 销毁时调用

#### 混合模式（既 Started 又 Bound）

```
onCreate() → onStartCommand() → onBind() → [运行中] → onUnbind() → onDestroy()
```

**关键点**：
- Service 只有在**既没有 Started 又没有 Bound** 时才会被销毁
- 如果 Service 被 Started，即使所有客户端都解绑，Service 仍会继续运行

---

### Q4: onStartCommand() 的返回值有什么含义？

**答案**：

`onStartCommand()` 的返回值决定 Service 被系统杀死后的行为：

| 返回值 | 说明 | 使用场景 |
| :--- | :--- | :--- |
| `START_STICKY` | Service 被杀死后自动重启，但 Intent 为 null | 音乐播放、下载任务 |
| `START_NOT_STICKY` | Service 被杀死后不重启 | 临时任务，不需要恢复 |
| `START_REDELIVER_INTENT` | Service 被杀死后重启，并重新传递最后一个 Intent | 文件上传，需要恢复状态 |
| `START_STICKY_COMPATIBILITY` | 兼容模式，行为类似 START_STICKY | 兼容旧版本 |

**代码示例**：

```java
@Override
public int onStartCommand(Intent intent, int flags, int startId) {
    // 执行任务
    doWork();
    
    // 如果任务需要恢复，返回 START_REDELIVER_INTENT
    return START_REDELIVER_INTENT;
}
```

---

### Q5: startService() 和 bindService() 有什么区别？

**答案**：

| 特性 | startService() | bindService() |
| :--- | :--- | :--- |
| **生命周期** | 独立于调用方 | 与调用方绑定 |
| **通信方式** | 通过 Intent 传递数据 | 通过 IBinder 调用方法 |
| **销毁时机** | 调用 stopService() 或 stopSelf() | 所有客户端解绑后自动销毁 |
| **使用场景** | 后台任务、长期运行 | 提供接口、数据查询 |
| **性能** | 开销小 | 开销较大（Binder 通信） |

**代码示例**：

```java
// startService()：独立运行
Intent intent = new Intent(this, MyService.class);
startService(intent);
// Service 会一直运行，直到调用 stopService()

// bindService()：绑定运行
bindService(intent, mConnection, Context.BIND_AUTO_CREATE);
// 所有客户端解绑后，Service 自动销毁
```

---

## 二、 生命周期与启动方式类

### Q6: Service 的 onCreate() 和 onStartCommand() 有什么区别？

**答案**：

| 方法 | 调用时机 | 调用次数 | 用途 |
| :--- | :--- | :--- | :--- |
| `onCreate()` | Service 第一次创建时 | 只调用一次 | 初始化操作：创建线程、初始化变量 |
| `onStartCommand()` | 每次调用 `startService()` 时 | 可能多次调用 | 处理启动请求：执行任务、处理 Intent |

**代码示例**：

```java
public class MyService extends Service {
    private ExecutorService mExecutor;
    
    @Override
    public void onCreate() {
        super.onCreate();
        // 只调用一次，适合初始化
        mExecutor = Executors.newCachedThreadPool();
    }
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // 每次 startService() 都会调用
        String action = intent.getAction();
        mExecutor.execute(() -> {
            // 处理任务
            doWork(action);
        });
        return START_NOT_STICKY;
    }
}
```

---

### Q7: 如何停止 Service？stopSelf() 和 stopSelfResult() 有什么区别？

**答案**：

停止 Service 的方式：

1. **外部停止**：`stopService(Intent intent)`
2. **内部停止**：`stopSelf()` 或 `stopSelfResult(int startId)`

**区别**：

- `stopSelf()`：立即停止 Service（可能不安全，如果同时有多个启动请求）
- `stopSelfResult(startId)`：只有当前 `startId` 匹配时才停止（更安全）

**代码示例**：

```java
public class MyService extends Service {
    private int mStartId;
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        mStartId = startId;
        
        new Thread(() -> {
            // 执行任务
            doWork();
            
            // 任务完成后停止（只有当前 startId 匹配时才停止）
            stopSelfResult(startId);
            // 这样可以避免在并发启动时过早停止 Service
        }).start();
        
        return START_NOT_STICKY;
    }
}
```

---

### Q8: onBind() 返回 null 和返回 IBinder 有什么区别？

**答案**：

| 返回值 | 说明 | 使用场景 |
| :--- | :--- | :--- |
| **null** | Service 不支持绑定，只能通过 `startService()` 启动 | Started Service |
| **非 null** | Service 支持绑定，返回 IBinder 用于通信 | Bound Service |

**代码示例**：

```java
// 只支持 Started 的 Service
public class StartedOnlyService extends Service {
    @Override
    public IBinder onBind(Intent intent) {
        return null;  // 不支持绑定
    }
}

// 支持 Bound 的 Service
public class BoundService extends Service {
    private final IBinder mBinder = new LocalBinder();
    
    @Override
    public IBinder onBind(Intent intent) {
        return mBinder;  // 返回 IBinder
    }
}
```

---

### Q9: onUnbind() 的返回值有什么含义？

**答案**：

`onUnbind()` 的返回值决定下次绑定时是否调用 `onRebind()`：

- **true**：下次绑定时会调用 `onRebind()`（而不是 `onBind()`）
- **false**：下次绑定时仍然调用 `onBind()`

**代码示例**：

```java
public class MyService extends Service {
    @Override
    public IBinder onBind(Intent intent) {
        Log.d("Service", "onBind called");
        return mBinder;
    }
    
    @Override
    public boolean onUnbind(Intent intent) {
        Log.d("Service", "onUnbind called");
        return true;  // 返回 true，下次绑定时会调用 onRebind()
    }
    
    @Override
    public void onRebind(Intent intent) {
        super.onRebind(intent);
        Log.d("Service", "onRebind called");  // 下次绑定时会调用这里
    }
}
```

---

## 三、 进程与通信类

### Q10: 本地 Service 和远程 Service 有什么区别？

**答案**：

| 特性 | 本地 Service | 远程 Service |
| :--- | :--- | :--- |
| **进程** | 与调用方在同一进程 | 运行在独立进程 |
| **通信方式** | 直接方法调用 | Binder 跨进程通信 |
| **性能** | 性能好，无 IPC 开销 | 性能开销大（Binder 调用） |
| **使用场景** | 同一应用内使用 | 跨应用或系统服务 |

**代码示例**：

```java
// 本地 Service（默认）
public class LocalService extends Service {
    // 与调用方在同一进程
}

// 远程 Service（在 AndroidManifest.xml 中声明）
<service
    android:name=".RemoteService"
    android:process=":remote" />  <!-- 独立进程 -->
```

---

### Q11: 什么是 Binder？Service 如何使用 Binder 通信？

**答案**：

**Binder** 是 Android 的进程间通信（IPC）机制，Service 的跨进程通信完全基于 Binder。

**Binder 架构**：
```
客户端进程                   系统进程                   服务端进程
    |                          |                          |
    |--- Binder 驱动 (内核) ---|                          |
    |                          |                          |
    |--- IBinder (代理) -------|------ IBinder (实现) ---|
```

**代码示例**：

```java
// 服务端：返回 IBinder
public class MyService extends Service {
    private final IBinder mBinder = new LocalBinder();
    
    public class LocalBinder extends Binder {
        MyService getService() {
            return MyService.this;
        }
    }
    
    @Override
    public IBinder onBind(Intent intent) {
        return mBinder;
    }
}

// 客户端：获取 IBinder 并调用方法
private ServiceConnection mConnection = new ServiceConnection() {
    @Override
    public void onServiceConnected(ComponentName name, IBinder service) {
        LocalBinder binder = (LocalBinder) service;
        MyService myService = binder.getService();
        myService.doSomething();  // 调用服务端方法
    }
    
    @Override
    public void onServiceDisconnected(ComponentName name) {
        // 连接断开
    }
};
```

---

### Q12: AIDL 是什么？如何使用 AIDL 实现跨进程通信？

**答案**：

**AIDL**（Android Interface Definition Language）是 Android 的接口定义语言，用于定义跨进程通信的接口。

**使用步骤**：

1. **定义 AIDL 接口**

```java
// IMyService.aidl
interface IMyService {
    void doSomething();
    int getValue();
}
```

2. **实现 Service**

```java
public class RemoteService extends Service {
    private final IMyService.Stub mBinder = new IMyService.Stub() {
        @Override
        public void doSomething() {
            // 实现方法
        }
        
        @Override
        public int getValue() {
            return 42;
        }
    };
    
    @Override
    public IBinder onBind(Intent intent) {
        return mBinder;
    }
}
```

3. **客户端使用**

```java
private IMyService mService;
private ServiceConnection mConnection = new ServiceConnection() {
    @Override
    public void onServiceConnected(ComponentName name, IBinder service) {
        mService = IMyService.Stub.asInterface(service);
        try {
            mService.doSomething();  // 跨进程调用
        } catch (RemoteException e) {
            e.printStackTrace();
        }
    }
    
    @Override
    public void onServiceDisconnected(ComponentName name) {
        mService = null;
    }
};
```

---

## 四、 前台服务与通知类

### Q13: 什么是前台 Service？如何创建前台 Service？

**答案**：

**前台 Service** 会显示一个持续的通知，系统不会轻易杀死它。适用于需要用户感知的长期运行任务。

**创建步骤**：

1. **创建通知渠道**（Android 8.0+）

```java
private void createNotificationChannel() {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Foreground Service",
            NotificationManager.IMPORTANCE_LOW
        );
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(channel);
    }
}
```

2. **创建通知并启动前台 Service**

```java
@Override
public int onStartCommand(Intent intent, int flags, int startId) {
    Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
        .setContentTitle("Foreground Service")
        .setContentText("Service is running...")
        .setSmallIcon(R.drawable.ic_notification)
        .build();
    
    startForeground(NOTIFICATION_ID, notification);
    
    return START_STICKY;
}
```

3. **启动前台 Service**

```java
// Android 8.0+ 必须使用 startForegroundService()
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
    startForegroundService(intent);
} else {
    startService(intent);
}
```

**注意事项**：
- Android 8.0+ 必须在调用 `startForegroundService()` 后 5 秒内调用 `startForeground()`，否则会崩溃
- 前台 Service 必须显示通知，用户可以看到

---

### Q14: Android 8.0+ 对 Service 有什么限制？如何适配？

**答案**：

**Android 8.0+ 的限制**：

1. **后台应用无法启动 Service**（除了前台 Service）
2. **必须使用 `startForegroundService()` 启动前台 Service**
3. **必须在 5 秒内调用 `startForeground()`**

**适配方案**：

```java
// 启动 Service
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
    startForegroundService(intent);
} else {
    startService(intent);
}

// Service 中
@Override
public int onStartCommand(Intent intent, int flags, int startId) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        // 必须在 5 秒内调用 startForeground()
        startForeground(NOTIFICATION_ID, createNotification());
    }
    
    // 执行任务
    doWork();
    
    return START_STICKY;
}
```

**替代方案**：

- 使用 `JobIntentService`（AndroidX）
- 使用 `WorkManager`（Google 推荐）

---

## 五、 性能优化类

### Q15: 为什么不能在 Service 的生命周期方法中执行耗时操作？

**答案**：

Service 的生命周期方法（`onCreate()`、`onStartCommand()`、`onBind()`）都在**主线程**中执行，如果执行耗时操作会导致：

1. **ANR（Application Not Responding）**：主线程被阻塞，应用无响应
2. **用户体验差**：界面卡顿，操作无响应

**超时时间**：
- 前台 Service：20 秒
- 后台 Service：200 秒

**正确做法**：

```java
// ❌ 错误示例
@Override
public void onCreate() {
    super.onCreate();
    // 耗时操作，可能导致 ANR
    downloadLargeFile();
}

// ✅ 正确示例
@Override
public void onCreate() {
    super.onCreate();
    // 只做轻量级初始化
    mExecutor = Executors.newCachedThreadPool();
}

@Override
public int onStartCommand(Intent intent, int flags, int startId) {
    // 耗时操作放到后台线程
    mExecutor.execute(() -> {
        downloadLargeFile();
        stopSelf(startId);
    });
    return START_NOT_STICKY;
}
```

---

### Q16: 如何优化 Service 的性能？

**答案**：

**优化策略**：

1. **避免在生命周期方法中执行耗时操作**

```java
// 使用线程池处理任务
private final ExecutorService mExecutor = new ThreadPoolExecutor(
    2, 4, 60L, TimeUnit.SECONDS,
    new LinkedBlockingQueue<>(100)
);
```

2. **减少 Binder 调用开销**

```java
// ❌ 错误：频繁调用
for (int i = 0; i < 1000; i++) {
    remoteService.processItem(i);  // 1000 次 Binder 调用
}

// ✅ 正确：批量处理
List<Integer> items = new ArrayList<>();
for (int i = 0; i < 1000; i++) {
    items.add(i);
}
remoteService.processBatch(items);  // 1 次 Binder 调用
```

3. **使用本地 Service 避免跨进程开销**

```java
// 如果不需要跨进程，使用本地 Service
// 避免在 AndroidManifest.xml 中声明 android:process
```

4. **及时释放资源**

```java
@Override
public void onDestroy() {
    super.onDestroy();
    // 释放所有资源
    if (mMediaPlayer != null) {
        mMediaPlayer.release();
        mMediaPlayer = null;
    }
}
```

---

## 六、 底层实现类

### Q17: Service 的启动流程是怎样的？

**答案**：

**完整调用链**：

```
Context.startService()
  → ContextImpl.startService()
    → ActivityManagerService.startService()
      → ActiveServices.startServiceLocked()
        → bringUpServiceLocked()
          → startProcessLocked() [如果进程不存在]
          → realStartServiceLocked() [进程已存在]
            → app.thread.scheduleCreateService()
              → ActivityThread.handleCreateService()
                → Service.onCreate()
```

**关键步骤**：

1. **查找或创建 ServiceRecord**：系统维护一个 ServiceRecord 表
2. **检查进程**：如果进程不存在，先启动进程
3. **启动 Service**：通过 Binder 调用应用进程，创建 Service 实例
4. **调用生命周期方法**：`onCreate()` → `onStartCommand()`

---

### Q18: ActiveServices 是什么？它的作用是什么？

**答案**：

**ActiveServices** 是 Android 系统中管理所有 Service 的核心类，位于 `ActivityManagerService` 中。

**核心职责**：

1. **管理 Service 的启动、绑定、停止**
2. **监控 Service 的执行状态和超时**
3. **处理 Service 的进程启动和绑定**
4. **维护 Service 与进程的关联关系**

**关键数据结构**：

```java
// Service 记录表
final ArrayMap<ComponentName, ServiceRecord> mServicesByName;

// 按进程分组的 Service
final ArrayMap<ProcessRecord, ArrayList<ServiceRecord>> mServicesByProcess;

// 正在执行的 Service（用于超时检测）
final ArrayList<ServiceRecord> mExecutingServices;
```

---

### Q19: Service 的超时检测机制是怎样的？

**答案**：

**超时时间**：
- 前台 Service：20 秒
- 后台 Service：200 秒

**检测机制**：

```java
// ActiveServices.java
void bumpServiceExecutingLocked(ServiceRecord r, boolean fg, String why) {
    // 1. 更新执行状态
    r.executing = true;
    r.executingStart = SystemClock.uptimeMillis();
    
    // 2. 加入执行列表
    mExecutingServices.add(r);
    
    // 3. 设置超时监控
    scheduleServiceTimeoutLocked(r.app);
}

void scheduleServiceTimeoutLocked(ProcessRecord proc) {
    // 计算超时时间
    long timeout = proc.processState >= PROCESS_STATE_IMPORTANT_BACKGROUND
        ? SERVICE_BACKGROUND_TIMEOUT  // 200 秒
        : SERVICE_TIMEOUT;  // 20 秒
    
    // 发送超时消息
    mAm.mHandler.sendMessageDelayed(msg, timeout);
}
```

**超时触发**：

如果 Service 在超时时间内没有完成（没有调用 `serviceDoneExecuting()`），系统会触发 ANR。

---

## 七、 高级特性类

### Q20: IntentService 和 JobIntentService 有什么区别？

**答案**：

| 特性 | IntentService | JobIntentService |
| :--- | :--- | :--- |
| **状态** | Android 8.0+ 已废弃 | AndroidX 推荐使用 |
| **后台限制** | 不兼容 Android 8.0+ | 兼容 Android 8.0+ |
| **调度方式** | 直接启动 | 自动使用 JobScheduler 或 WorkManager |
| **API** | 简单 | 保持简单 API |

**代码示例**：

```java
// IntentService（已废弃）
public class MyIntentService extends IntentService {
    @Override
    protected void onHandleIntent(Intent intent) {
        // 在后台线程执行
    }
}

// JobIntentService（推荐）
public class MyJobIntentService extends JobIntentService {
    static void enqueueWork(Context context, Intent work) {
        enqueueWork(context, MyJobIntentService.class, JOB_ID, work);
    }
    
    @Override
    protected void onHandleWork(@NonNull Intent intent) {
        // 在后台线程执行
    }
}
```

---

### Q21: WorkManager 和 Service 有什么区别？什么时候使用 WorkManager？

**答案**：

| 特性 | Service | WorkManager |
| :--- | :--- | :--- |
| **使用场景** | 需要立即执行的任务 | 可以延迟执行的任务 |
| **执行保证** | 可能被系统杀死 | 保证最终会执行 |
| **约束支持** | 不支持 | 支持（网络、充电等） |
| **版本兼容** | 需要手动适配 | 自动处理版本差异 |

**使用场景**：

- **Service**：音乐播放、文件下载、实时同步
- **WorkManager**：数据同步、日志上传、定期任务

**代码示例**：

```java
// WorkManager
OneTimeWorkRequest workRequest = new OneTimeWorkRequest.Builder(MyWorker.class)
    .setConstraints(new Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .setRequiresCharging(true)
        .build())
    .build();

WorkManager.getInstance(context).enqueue(workRequest);
```

---

### Q22: 如何实现进程保活？有哪些方式？

**答案**：

**合法方式**：

1. **前台 Service**（推荐）

```java
// 启动前台 Service，显示通知
startForeground(NOTIFICATION_ID, notification);
```

2. **JobScheduler 保活**

```java
JobScheduler js = getSystemService(JobScheduler.class);
JobInfo jobInfo = new JobInfo.Builder(1, new ComponentName(this, KeepAliveJobService.class))
    .setPeriodic(15 * 60 * 1000)  // 每 15 分钟执行一次
    .setPersisted(true)
    .build();
js.schedule(jobInfo);
```

**不推荐方式**（Android 8.0+ 已失效）：

- 双进程守护
- 1 像素 Activity
- 监听系统广播

---

## 八、 系统服务类

### Q23: 系统服务（System Service）是什么？如何获取系统服务？

**答案**：

**系统服务**是 Android 框架层的核心服务，运行在 `system_server` 进程中，为所有应用提供基础功能。

**常见系统服务**：
- `ActivityManagerService` (AMS)
- `WindowManagerService` (WMS)
- `PackageManagerService` (PMS)
- `PowerManagerService`

**获取方式**：

```java
// 通过 Context.getSystemService()
ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
```

**底层实现**：

```java
// SystemServiceRegistry.java
static {
    registerService(Context.ACTIVITY_SERVICE, ActivityManager.class,
        new CachedServiceFetcher<ActivityManager>() {
            @Override
            public ActivityManager createService(ContextImpl ctx) {
                return new ActivityManager(ctx.getOuterContext(), ...);
            }
        });
}
```

---

## 九、 实战场景类

### Q24: 如何实现一个音乐播放 Service？

**答案**：

```java
public class MusicService extends Service {
    private MediaPlayer mMediaPlayer;
    private static final int NOTIFICATION_ID = 1;
    
    @Override
    public void onCreate() {
        super.onCreate();
        mMediaPlayer = new MediaPlayer();
        createNotificationChannel();
    }
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent.getAction();
        
        if ("PLAY".equals(action)) {
            playMusic();
        } else if ("PAUSE".equals(action)) {
            pauseMusic();
        } else if ("STOP".equals(action)) {
            stopMusic();
        }
        
        // 启动前台 Service
        startForeground(NOTIFICATION_ID, createNotification());
        
        return START_STICKY;
    }
    
    private void playMusic() {
        if (!mMediaPlayer.isPlaying()) {
            mMediaPlayer.start();
        }
    }
    
    private void pauseMusic() {
        if (mMediaPlayer.isPlaying()) {
            mMediaPlayer.pause();
        }
    }
    
    private void stopMusic() {
        if (mMediaPlayer.isPlaying()) {
            mMediaPlayer.stop();
        }
        stopSelf();
    }
    
    @Override
    public void onDestroy() {
        super.onDestroy();
        if (mMediaPlayer != null) {
            mMediaPlayer.release();
            mMediaPlayer = null;
        }
    }
    
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
```

---

### Q25: 如何实现一个文件下载 Service？

**答案**：

```java
public class DownloadService extends Service {
    private ExecutorService mExecutor;
    private static final int NOTIFICATION_ID = 1;
    
    @Override
    public void onCreate() {
        super.onCreate();
        mExecutor = Executors.newCachedThreadPool();
        createNotificationChannel();
    }
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String url = intent.getStringExtra("url");
        String filePath = intent.getStringExtra("filePath");
        
        // 启动前台 Service
        startForeground(NOTIFICATION_ID, createNotification("Downloading..."));
        
        // 在后台线程下载
        mExecutor.execute(() -> {
            try {
                downloadFile(url, filePath);
                updateNotification("Download completed");
            } catch (Exception e) {
                updateNotification("Download failed");
            } finally {
                stopSelf(startId);
            }
        });
        
        return START_NOT_STICKY;
    }
    
    private void downloadFile(String url, String filePath) throws IOException {
        // 下载逻辑
        URL downloadUrl = new URL(url);
        HttpURLConnection conn = (HttpURLConnection) downloadUrl.openConnection();
        
        try (InputStream input = conn.getInputStream();
             FileOutputStream output = new FileOutputStream(filePath)) {
            
            byte[] buffer = new byte[4096];
            int bytesRead;
            while ((bytesRead = input.read(buffer)) != -1) {
                output.write(buffer, 0, bytesRead);
                // 更新进度
                updateProgress(bytesRead);
            }
        }
    }
    
    @Override
    public void onDestroy() {
        super.onDestroy();
        mExecutor.shutdown();
    }
    
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
```

---

## 十、 总结

本文档涵盖了 Service 相关的常见面试题，包括：

1. **基础概念**：Service 的定义、类型、生命周期
2. **启动方式**：startService() 和 bindService() 的区别
3. **进程通信**：Binder 机制、AIDL 使用
4. **前台服务**：创建前台 Service、Android 8.0+ 适配
5. **性能优化**：避免 ANR、优化策略
6. **底层实现**：启动流程、ActiveServices、超时检测
7. **高级特性**：IntentService、WorkManager、进程保活
8. **系统服务**：系统服务的获取和使用
9. **实战场景**：音乐播放、文件下载等实际应用

掌握这些知识点，可以应对大部分 Service 相关的面试问题。

---

**相关文档**：
- [基础篇：生命周期、启动方式与核心概念](01_Basics_Service.md)
- [进阶篇：底层实现、Binder 通信与进程管理](02_Advanced_Service.md)
- [高阶篇：系统服务、性能优化与高级特性](03_Expert_Service.md)
