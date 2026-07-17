# Service 高阶篇：系统服务、性能优化与高级特性

## 📋 概述

在掌握了 Service 的基础使用和底层实现后，我们需要了解更高级的话题：系统服务的实现机制、Service 性能优化策略、JobIntentService 与 WorkManager 的演进、进程保活技术，以及 Service 在大规模应用中的最佳实践。

---

## 一、 系统服务（System Service）深度解析

### 1.1 系统服务概述

系统服务是 Android 框架层的核心服务，运行在 `system_server` 进程中，为所有应用提供基础功能。

**常见的系统服务**：
- `ActivityManagerService` (AMS)：管理 Activity、Service、进程
- `WindowManagerService` (WMS)：管理窗口、输入事件
- `PackageManagerService` (PMS)：管理应用安装、权限
- `PowerManagerService`：管理电源、唤醒锁
- `LocationManagerService`：管理定位服务

### 1.2 系统服务的启动流程

系统服务在 `SystemServer` 进程中启动：

```java
// SystemServer.java
public static void main(String[] args) {
    new SystemServer().run();
}

private void run() {
    // 1. 创建系统上下文
    createSystemContext();
    
    // 2. 启动引导服务（Bootstrap Services）
    startBootstrapServices();
    
    // 3. 启动核心服务（Core Services）
    startCoreServices();
    
    // 4. 启动其他服务（Other Services）
    startOtherServices();
    
    // 5. 进入 Looper 循环
    Looper.loop();
}

private void startBootstrapServices() {
    // 启动 ActivityManagerService
    mActivityManagerService = mSystemServiceManager.startService(
        ActivityManagerService.Lifecycle.class).getService();
    
    // 启动 PowerManagerService
    mPowerManagerService = mSystemServiceManager.startService(PowerManagerService.class);
    
    // ...
}

private void startCoreServices() {
    // 启动 BatteryService
    mBatteryService = new BatteryService(context);
    ServiceManager.addService("batterymanager", mBatteryService);
    
    // ...
}
```

### 1.3 系统服务的注册机制

系统服务通过 `ServiceManager` 注册，应用可以通过 `getSystemService()` 获取：

```java
// ServiceManager.java (Native)
// 系统服务注册表
static struct {
    const char *name;
    void *service;
} gDefaultServiceTable[] = {
    { "activity", NULL },
    { "window", NULL },
    { "package", NULL },
    // ...
};

// 注册服务
void ServiceManager::addService(const String16& name, const sp<IBinder>& service) {
    // 添加到服务表
    mNameToService.add(name, service);
}

// 获取服务
sp<IBinder> ServiceManager::getService(const String16& name) {
    return mNameToService.valueFor(name);
}
```

### 1.4 应用获取系统服务

```java
// ContextImpl.java
@Override
public Object getSystemService(String name) {
    return SystemServiceRegistry.getSystemService(this, name);
}

// SystemServiceRegistry.java
static Object getSystemService(ContextImpl ctx, String name) {
    ServiceFetcher<?> fetcher = SYSTEM_SERVICE_FETCHERS.get(name);
    if (fetcher == null) {
        return null;
    }
    return fetcher.getService(ctx);
}

// 注册系统服务
static {
    registerService(Context.ACTIVITY_SERVICE, ActivityManager.class,
        new CachedServiceFetcher<ActivityManager>() {
            @Override
            public ActivityManager createService(ContextImpl ctx) {
                return new ActivityManager(ctx.getOuterContext(),
                    ctx.mMainThread.getHandler());
            }
        });
    
    registerService(Context.POWER_SERVICE, PowerManager.class,
        new CachedServiceFetcher<PowerManager>() {
            @Override
            public PowerManager createService(ContextImpl ctx) {
                IBinder b = ServiceManager.getService(Context.POWER_SERVICE);
                IPowerManager service = IPowerManager.Stub.asInterface(b);
                return new PowerManager(ctx.getOuterContext(), service,
                    ctx.mMainThread.getHandler());
            }
        });
}
```

### 1.5 自定义系统服务（ROM 定制）

在 ROM 开发中，可以添加自定义系统服务：

```java
// 1. 定义 AIDL 接口
// IMySystemService.aidl
interface IMySystemService {
    void doSomething();
}

// 2. 实现系统服务
public class MySystemService extends IMySystemService.Stub {
    @Override
    public void doSomething() {
        // 实现逻辑
    }
}

// 3. 在 SystemServer 中注册
private void startOtherServices() {
    MySystemService myService = new MySystemService();
    ServiceManager.addService("mysystemservice", myService);
}

// 4. 应用中使用
IBinder binder = ServiceManager.getService("mysystemservice");
IMySystemService service = IMySystemService.Stub.asInterface(binder);
service.doSomething();
```

---

## 二、 JobIntentService 与 WorkManager

### 2.1 JobIntentService：IntentService 的现代化替代

`IntentService` 在 Android 8.0+ 已被废弃，`JobIntentService` 是其替代方案。

**JobIntentService 的优势**：
- 兼容 Android 8.0+ 的后台限制
- 自动使用 `JobScheduler` 或 `WorkManager` 调度
- 保持 `IntentService` 的简单 API

**实现示例**：

```java
public class MyJobIntentService extends JobIntentService {
    static final int JOB_ID = 1000;
    
    static void enqueueWork(Context context, Intent work) {
        enqueueWork(context, MyJobIntentService.class, JOB_ID, work);
    }
    
    @Override
    protected void onHandleWork(@NonNull Intent intent) {
        // 在后台线程执行（类似 IntentService.onHandleIntent）
        String action = intent.getAction();
        // 处理任务
    }
}

// 使用
Intent intent = new Intent(context, MyJobIntentService.class);
MyJobIntentService.enqueueWork(context, intent);
```

**底层实现**：

```java
// JobIntentService.java
public static void enqueueWork(Context context, Class<?> cls, int jobId, Intent work) {
    if (Build.VERSION.SDK_INT >= 26) {
        // Android 8.0+ 使用 JobScheduler
        JobScheduler js = context.getSystemService(JobScheduler.class);
        JobInfo.Builder b = new JobInfo.Builder(jobId, new ComponentName(context, cls));
        b.setRequiredNetworkType(JobInfo.NETWORK_TYPE_NONE);
        js.enqueue(b.build(), new JobWorkItem(work));
    } else {
        // 旧版本使用 IntentService 方式
        Intent intent = new Intent(context, cls);
        intent.putExtra(EXTRA_WORK_INTENT, work);
        context.startService(intent);
    }
}
```

### 2.2 WorkManager：Google 推荐的现代方案

`WorkManager` 是 Google 推荐的用于后台任务调度的现代 API，适用于需要保证执行的任务。

**WorkManager 的特点**：
- 自动处理 Android 版本差异（使用 JobScheduler、Firebase JobDispatcher 或 AlarmManager）
- 支持约束条件（网络、充电、存储空间等）
- 支持链式任务和周期性任务
- 保证任务最终会执行（即使应用被杀死）

**实现示例**：

```java
// 定义 Worker
public class MyWorker extends Worker {
    public MyWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }
    
    @NonNull
    @Override
    public Result doWork() {
        // 执行任务
        try {
            doSomething();
            return Result.success();
        } catch (Exception e) {
            return Result.retry();  // 失败重试
        }
    }
}

// 创建 WorkRequest
OneTimeWorkRequest workRequest = new OneTimeWorkRequest.Builder(MyWorker.class)
    .setConstraints(new Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .setRequiresCharging(true)
        .build())
    .setInitialDelay(10, TimeUnit.SECONDS)
    .build();

// 提交任务
WorkManager.getInstance(context).enqueue(workRequest);

// 链式任务
WorkManager.getInstance(context)
    .beginWith(workRequest1)
    .then(workRequest2)
    .then(workRequest3)
    .enqueue();
```

---

## 三、 Service 性能优化策略

### 3.1 避免在生命周期方法中执行耗时操作

```java
// ❌ 错误示例
@Override
public void onCreate() {
    super.onCreate();
    // 耗时操作，可能导致 ANR
    downloadLargeFile();
    processLargeData();
}

// ✅ 正确示例
@Override
public void onCreate() {
    super.onCreate();
    // 只做轻量级初始化
    mHandler = new Handler(Looper.getMainLooper());
    mExecutor = Executors.newCachedThreadPool();
}

@Override
public int onStartCommand(Intent intent, int flags, int startId) {
    // 耗时操作放到后台线程
    mExecutor.execute(() -> {
        downloadLargeFile();
        processLargeData();
        stopSelf(startId);
    });
    return START_NOT_STICKY;
}
```

### 3.2 合理使用线程池

```java
public class OptimizedService extends Service {
    // 使用线程池管理后台任务
    private final ExecutorService mExecutor = new ThreadPoolExecutor(
        2,  // 核心线程数
        4,  // 最大线程数
        60L, TimeUnit.SECONDS,  // 空闲线程存活时间
        new LinkedBlockingQueue<>(100),  // 任务队列
        new ThreadFactory() {
            @Override
            public Thread newThread(Runnable r) {
                Thread t = new Thread(r, "ServiceWorker");
                t.setDaemon(true);
                return t;
            }
        }
    );
    
    @Override
    public void onDestroy() {
        super.onDestroy();
        // 优雅关闭线程池
        mExecutor.shutdown();
        try {
            if (!mExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                mExecutor.shutdownNow();
            }
        } catch (InterruptedException e) {
            mExecutor.shutdownNow();
        }
    }
}
```

### 3.3 减少 Binder 调用开销

**问题**：频繁的跨进程 Binder 调用会带来性能开销。

**优化策略**：

```java
// ❌ 错误示例：频繁调用
for (int i = 0; i < 1000; i++) {
    remoteService.processItem(i);  // 1000 次 Binder 调用
}

// ✅ 正确示例：批量处理
List<Integer> items = new ArrayList<>();
for (int i = 0; i < 1000; i++) {
    items.add(i);
}
remoteService.processBatch(items);  // 1 次 Binder 调用
```

### 3.4 使用本地 Service 避免跨进程开销

如果不需要跨进程，使用本地 Service 可以避免 Binder 开销：

```java
// 本地 Service（同一进程）
public class LocalService extends Service {
    // 直接方法调用，无 Binder 开销
}

// 远程 Service（独立进程）
// AndroidManifest.xml
<service
    android:name=".RemoteService"
    android:process=":remote" />  // 独立进程，有 Binder 开销
```

### 3.5 及时释放资源

```java
public class ResourceAwareService extends Service {
    private MediaPlayer mMediaPlayer;
    private FileInputStream mFileInputStream;
    private DatabaseHelper mDatabaseHelper;
    
    @Override
    public void onDestroy() {
        super.onDestroy();
        
        // 释放所有资源
        if (mMediaPlayer != null) {
            mMediaPlayer.release();
            mMediaPlayer = null;
        }
        
        if (mFileInputStream != null) {
            try {
                mFileInputStream.close();
            } catch (IOException e) {
                e.printStackTrace();
            }
            mFileInputStream = null;
        }
        
        if (mDatabaseHelper != null) {
            mDatabaseHelper.close();
            mDatabaseHelper = null;
        }
    }
}
```

---

## 四、 进程保活技术

### 4.1 前台 Service 保活

前台 Service 是系统允许的保活方式，优先级高，不易被杀死。

```java
public class KeepAliveService extends Service {
    private static final int NOTIFICATION_ID = 1;
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTIFICATION_ID, createNotification());
        return START_STICKY;  // 被杀死后自动重启
    }
    
    private Notification createNotification() {
        // 创建前台通知
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Keep Alive Service")
            .setContentText("Service is running...")
            .setSmallIcon(R.drawable.ic_notification)
            .build();
    }
}
```

### 4.2 双进程守护（已不推荐）

通过两个进程互相守护，一个进程被杀死时另一个进程重启它。**Android 8.0+ 已失效**。

```java
// 主进程 Service
public class MainService extends Service {
    @Override
    public void onCreate() {
        super.onCreate();
        // 启动守护进程
        startService(new Intent(this, GuardService.class));
    }
}

// 守护进程 Service
public class GuardService extends Service {
    @Override
    public void onCreate() {
        super.onCreate();
        // 监控主进程，如果被杀死则重启
        watchMainProcess();
    }
}
```

### 4.3 JobScheduler 保活（推荐）

使用 `JobScheduler` 定期唤醒应用，保持进程活跃。

```java
public class KeepAliveJobService extends JobService {
    @Override
    public boolean onStartJob(JobParameters params) {
        // 执行保活任务
        doKeepAliveWork();
        
        // 调度下一次执行
        scheduleNext();
        
        return false;  // 任务已完成
    }
    
    private void scheduleNext() {
        JobScheduler js = getSystemService(JobScheduler.class);
        JobInfo jobInfo = new JobInfo.Builder(1, new ComponentName(this, KeepAliveJobService.class))
            .setPeriodic(15 * 60 * 1000)  // 每 15 分钟执行一次
            .setPersisted(true)  // 重启后仍然有效
            .build();
        js.schedule(jobInfo);
    }
}
```

### 4.4 系统白名单（ROM 定制）

在 ROM 开发中，可以将应用加入系统白名单，防止被杀死：

```java
// ActivityManagerService.java (ROM 定制)
private boolean isWhitelisted(String packageName) {
    // 检查应用是否在白名单中
    return mWhitelistPackages.contains(packageName);
}

void killProcessLocked(ProcessRecord app, String reason, boolean noisy) {
    if (isWhitelisted(app.info.packageName)) {
        // 白名单应用，不杀死
        return;
    }
    // 正常杀死流程
}
```

---

## 五、 Service 在大规模应用中的最佳实践

### 5.1 Service 架构设计

**单一职责原则**：
- 每个 Service 只负责一个明确的任务
- 避免在 Service 中混合多种不相关的功能

**示例**：

```java
// ❌ 错误：一个 Service 做多件事
public class UniversalService extends Service {
    void downloadFile() { }
    void playMusic() { }
    void syncData() { }
}

// ✅ 正确：职责分离
public class DownloadService extends Service { }
public class MusicService extends Service { }
public class SyncService extends Service { }
```

### 5.2 使用依赖注入

```java
// 使用 Dagger 或 Hilt 注入依赖
@AndroidEntryPoint
public class MyService extends Service {
    @Inject
    DataRepository mRepository;
    
    @Inject
    NetworkManager mNetworkManager;
    
    @Override
    public void onCreate() {
        super.onCreate();
        // 依赖已自动注入
    }
}
```

### 5.3 状态管理

```java
public class StatefulService extends Service {
    private enum State {
        IDLE,
        RUNNING,
        PAUSED,
        ERROR
    }
    
    private State mState = State.IDLE;
    private final Object mStateLock = new Object();
    
    private void setState(State newState) {
        synchronized (mStateLock) {
            State oldState = mState;
            mState = newState;
            onStateChanged(oldState, newState);
        }
    }
    
    private void onStateChanged(State oldState, State newState) {
        // 处理状态变化
    }
}
```

### 5.4 错误处理与重试机制

```java
public class RobustService extends Service {
    private static final int MAX_RETRIES = 3;
    private static final long RETRY_DELAY = 5000;  // 5 秒
    
    private void executeWithRetry(Runnable task) {
        int retries = 0;
        while (retries < MAX_RETRIES) {
            try {
                task.run();
                return;  // 成功，退出
            } catch (Exception e) {
                retries++;
                if (retries >= MAX_RETRIES) {
                    // 达到最大重试次数，记录错误
                    logError(e);
                    return;
                }
                // 等待后重试
                try {
                    Thread.sleep(RETRY_DELAY);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }
}
```

### 5.5 监控与日志

```java
public class MonitoredService extends Service {
    private static final String TAG = "MonitoredService";
    
    @Override
    public void onCreate() {
        super.onCreate();
        logEvent("onCreate");
        recordMetric("service_create", System.currentTimeMillis());
    }
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        long startTime = System.currentTimeMillis();
        logEvent("onStartCommand", "startId=" + startId);
        
        try {
            // 执行任务
            doWork();
            
            long duration = System.currentTimeMillis() - startTime;
            recordMetric("service_execution_time", duration);
            
            return START_NOT_STICKY;
        } catch (Exception e) {
            logError("onStartCommand failed", e);
            recordMetric("service_error", 1);
            return START_NOT_STICKY;
        }
    }
    
    private void logEvent(String event, String... params) {
        Log.d(TAG, event + " " + Arrays.toString(params));
        // 发送到分析平台
        Analytics.logEvent(event, params);
    }
    
    private void recordMetric(String name, long value) {
        // 记录指标
        Metrics.record(name, value);
    }
}
```

---

## 六、 Service 与 Android 版本适配

### 6.1 Android 8.0+ 后台限制

**变化**：
- 后台应用无法启动 Service（除了前台 Service）
- 必须使用 `startForegroundService()` 启动前台 Service
- 必须在 5 秒内调用 `startForeground()`

**适配方案**：

```java
public class CompatibleService extends Service {
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // Android 8.0+ 必须启动前台 Service
            startForeground(NOTIFICATION_ID, createNotification());
        }
        
        // 执行任务
        doWork();
        
        return START_STICKY;
    }
}

// 启动 Service
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
    context.startForegroundService(intent);
} else {
    context.startService(intent);
}
```

### 6.2 Android 12+ 前台服务限制

**变化**：
- 前台 Service 需要声明前台服务类型
- 需要申请 `FOREGROUND_SERVICE` 权限

**适配方案**：

```xml
<!-- AndroidManifest.xml -->
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />

<service
    android:name=".MyForegroundService"
    android:foregroundServiceType="mediaPlayback"
    android:exported="false" />
```

```java
// Android 12+
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
    startForeground(NOTIFICATION_ID, notification,
        FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
} else {
    startForeground(NOTIFICATION_ID, notification);
}
```

---

## 七、 总结

1. **系统服务**：运行在 `system_server` 进程，为所有应用提供基础功能
2. **现代化方案**：`JobIntentService` 和 `WorkManager` 是 `IntentService` 的替代方案
3. **性能优化**：避免在生命周期方法中执行耗时操作，合理使用线程池，减少 Binder 调用
4. **进程保活**：前台 Service 是系统允许的方式，双进程守护已失效
5. **最佳实践**：单一职责、依赖注入、状态管理、错误处理、监控日志
6. **版本适配**：Android 8.0+ 和 12+ 对 Service 有新的限制，需要适配

---
**本系列完结。**
