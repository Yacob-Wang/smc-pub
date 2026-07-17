# Service 基础篇：生命周期、启动方式与核心概念

## 📋 概述

Service 是 Android 四大组件之一，用于在后台执行长时间运行的操作，不提供用户界面。Service 可以在应用处于后台时继续运行，也可以被其他应用组件绑定以进行进程间通信（IPC）。本篇将深入讲解 Service 的核心概念、生命周期、启动方式以及各种使用场景。

---

## 一、 Service 的基本概念

### 1.1 什么是 Service

Service 是一种可以在后台执行长时间运行操作的应用组件，**不提供用户界面**。与 Activity 不同，Service 没有可见的 UI，主要用于：

- **后台任务**：下载文件、播放音乐、同步数据等
- **跨进程通信**：通过 Binder 机制与其他应用或系统服务通信
- **长期运行**：即使应用切换到后台，Service 仍可继续运行

### 1.2 Service 的分类

#### 1.2.1 按运行方式分类

| 类型 | 说明 | 使用场景 |
| :--- | :--- | :--- |
| **Started Service** | 通过 `startService()` 启动，独立运行 | 下载文件、上传数据、播放音乐 |
| **Bound Service** | 通过 `bindService()` 绑定，提供客户端-服务器接口 | 提供数据查询、方法调用接口 |
| **Foreground Service** | 前台服务，显示通知，系统不会轻易杀死 | 音乐播放、导航、文件下载 |

#### 1.2.2 按进程分类

| 类型 | 说明 | 特点 |
| :--- | :--- | :--- |
| **本地 Service** | 与调用方在同一进程 | 性能好，但无法跨进程 |
| **远程 Service** | 运行在独立进程 | 可跨进程，但性能开销大 |

---

## 二、 Service 的生命周期

Service 的生命周期取决于启动方式：**Started** 和 **Bound** 的生命周期完全不同。

### 2.1 Started Service 的生命周期

通过 `startService()` 启动的 Service 遵循以下生命周期：

```
onCreate() → onStartCommand() → [运行中] → onDestroy()
```

**生命周期方法详解**：

#### 2.1.1 onCreate()

```java
@Override
public void onCreate() {
    super.onCreate();
    // Service 创建时调用，只调用一次
    // 适合进行初始化操作：创建线程、初始化变量等
}
```

**调用时机**：
- Service 第一次创建时调用
- 如果 Service 已经运行，再次调用 `startService()` **不会**再次调用 `onCreate()`

**注意事项**：
- 如果 `onCreate()` 执行时间过长（超过 20 秒），可能触发 ANR
- 应该避免在 `onCreate()` 中执行耗时操作

#### 2.1.2 onStartCommand()

```java
@Override
public int onStartCommand(Intent intent, int flags, int startId) {
    // 每次调用 startService() 时都会调用
    // intent: 启动 Service 时传递的 Intent
    // flags: 启动标志
    // startId: 本次启动的唯一 ID
    
    // 返回值决定 Service 被杀死后的行为
    return START_STICKY;  // 或其他返回值
}
```

**返回值说明**：

| 返回值 | 说明 | 使用场景 |
| :--- | :--- | :--- |
| `START_STICKY` | Service 被杀死后自动重启，但 Intent 为 null | 音乐播放、下载任务 |
| `START_NOT_STICKY` | Service 被杀死后不重启 | 临时任务，不需要恢复 |
| `START_REDELIVER_INTENT` | Service 被杀死后重启，并重新传递最后一个 Intent | 文件上传，需要恢复状态 |
| `START_STICKY_COMPATIBILITY` | 兼容模式，行为类似 START_STICKY | 兼容旧版本 |

**flags 参数说明**：

| Flag | 说明 |
| :--- | :--- |
| `START_FLAG_REDELIVERY` | Intent 是重新传递的（之前启动失败） |
| `START_FLAG_RETRY` | 启动失败后重试 |

#### 2.1.3 onDestroy()

```java
@Override
public void destroy() {
    super.onDestroy();
    // Service 销毁时调用
    // 适合清理资源：停止线程、释放连接等
}
```

**调用时机**：
- 调用 `stopService()` 时
- 调用 `stopSelf()` 或 `stopSelfResult(startId)` 时
- 系统资源不足，杀死 Service 时

### 2.2 Bound Service 的生命周期

通过 `bindService()` 绑定的 Service 遵循以下生命周期：

```
onCreate() → onBind() → [运行中] → onUnbind() → onDestroy()
```

**生命周期方法详解**：

#### 2.2.1 onBind()

```java
@Override
public IBinder onBind(Intent intent) {
    // 返回 IBinder 对象，用于客户端与服务端通信
    return mBinder;  // 或返回 null（表示不支持绑定）
}
```

**返回值**：
- **非 null**：返回 `IBinder` 对象，客户端可以通过该对象调用 Service 的方法
- **null**：表示该 Service 不支持绑定，只能通过 `startService()` 启动

#### 2.2.2 onUnbind()

```java
@Override
public boolean onUnbind(Intent intent) {
    // 所有客户端都解绑时调用
    // 返回值决定下次绑定时是否调用 onRebind()
    return true;  // 返回 true 表示下次绑定时会调用 onRebind()
}
```

**返回值说明**：
- **true**：下次绑定时会调用 `onRebind()`（而不是 `onBind()`）
- **false**：下次绑定时仍然调用 `onBind()`

#### 2.2.3 onRebind()

```java
@Override
public void onRebind(Intent intent) {
    super.onRebind(intent);
    // 在 onUnbind() 返回 true 的情况下，再次绑定时调用
}
```

### 2.3 混合模式：既 Started 又 Bound

如果 Service 既通过 `startService()` 启动，又被 `bindService()` 绑定，生命周期会合并：

```
onCreate() → onStartCommand() → onBind() → [运行中] → onUnbind() → onDestroy()
```

**关键点**：
- Service 只有在**既没有 Started 又没有 Bound** 时才会被销毁
- 如果 Service 被 Started，即使所有客户端都解绑，Service 仍会继续运行
- 如果 Service 只被 Bound，所有客户端解绑后，Service 会被销毁

---

## 三、 Service 的启动方式

### 3.1 startService()：启动服务

#### 3.1.1 基本用法

```java
// 启动 Service
Intent intent = new Intent(this, MyService.class);
intent.putExtra("key", "value");
startService(intent);

// 停止 Service
stopService(intent);
// 或在 Service 内部调用
stopSelf();
stopSelfResult(startId);  // 只有 startId 匹配时才停止
```

#### 3.1.2 Service 内部停止

```java
public class MyService extends Service {
    private int mStartId;
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        mStartId = startId;
        
        // 执行任务
        doWork();
        
        // 任务完成后停止 Service
        stopSelfResult(startId);  // 只有当前 startId 匹配时才停止
        // 这样可以避免在并发启动时过早停止 Service
        
        return START_NOT_STICKY;
    }
}
```

### 3.2 bindService()：绑定服务

#### 3.2.1 基本用法

```java
// 绑定 Service
Intent intent = new Intent(this, MyService.class);
bindService(intent, mConnection, Context.BIND_AUTO_CREATE);

// ServiceConnection 回调
private ServiceConnection mConnection = new ServiceConnection() {
    @Override
    public void onServiceConnected(ComponentName name, IBinder service) {
        // 绑定成功，获取 IBinder 对象
        MyBinder binder = (MyBinder) service;
        mService = binder.getService();
    }
    
    @Override
    public void onServiceDisconnected(ComponentName name) {
        // 连接断开（Service 进程被杀死）
        mService = null;
    }
};

// 解绑
unbindService(mConnection);
```

#### 3.2.2 bindService() 的标志位

| 标志 | 说明 |
| :--- | :--- |
| `BIND_AUTO_CREATE` | 如果 Service 不存在，自动创建 |
| `BIND_IMPORTANT` | 将 Service 标记为重要，提高优先级 |
| `BIND_ABOVE_CLIENT` | Service 优先级高于客户端 |
| `BIND_ALLOW_OOM_MANAGEMENT` | 允许系统在内存不足时杀死 Service |
| `BIND_WAIVE_PRIORITY` | 不提升 Service 优先级 |
| `BIND_NOT_FOREGROUND` | Service 不会提升到前台 |

### 3.3 两种启动方式的对比

| 特性 | startService() | bindService() |
| :--- | :--- | :--- |
| **生命周期** | 独立于调用方 | 与调用方绑定 |
| **通信方式** | 通过 Intent 传递数据 | 通过 IBinder 调用方法 |
| **销毁时机** | 调用 stopService() 或 stopSelf() | 所有客户端解绑后自动销毁 |
| **使用场景** | 后台任务、长期运行 | 提供接口、数据查询 |
| **性能** | 开销小 | 开销较大（Binder 通信） |

---

## 四、 本地 Service 与远程 Service

### 4.1 本地 Service（Local Service）

**特点**：
- Service 与调用方在同一进程
- 通过直接方法调用通信，性能好
- 无法跨进程

**实现方式**：

```java
// Service 实现
public class LocalService extends Service {
    private final IBinder mBinder = new LocalBinder();
    
    public class LocalBinder extends Binder {
        LocalService getService() {
            return LocalService.this;
        }
    }
    
    @Override
    public IBinder onBind(Intent intent) {
        return mBinder;
    }
    
    // 业务方法
    public void doSomething() {
        // ...
    }
}

// 客户端使用
private LocalService mService;
private ServiceConnection mConnection = new ServiceConnection() {
    @Override
    public void onServiceConnected(ComponentName name, IBinder service) {
        LocalService.LocalBinder binder = (LocalService.LocalBinder) service;
        mService = binder.getService();
        mService.doSomething();  // 直接调用方法
    }
    
    @Override
    public void onServiceDisconnected(ComponentName name) {
        mService = null;
    }
};
```

### 4.2 远程 Service（Remote Service）

**特点**：
- Service 运行在独立进程
- 通过 Binder 机制跨进程通信
- 性能开销较大

**实现方式**：

#### 4.2.1 在 AndroidManifest.xml 中声明独立进程

```xml
<service
    android:name=".RemoteService"
    android:process=":remote" />  <!-- 独立进程 -->
    <!-- 或 -->
    android:process="com.example.remote" />  <!-- 全局独立进程 -->
```

#### 4.2.2 使用 AIDL 定义接口

```java
// IMyService.aidl
interface IMyService {
    void doSomething();
    int getValue();
}
```

#### 4.2.3 Service 实现

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

#### 4.2.4 客户端使用

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

## 五、 前台 Service

前台 Service 会显示一个持续的通知，系统不会轻易杀死它。适用于需要用户感知的长期运行任务。

### 5.1 创建前台 Service

```java
public class ForegroundService extends Service {
    private static final int NOTIFICATION_ID = 1;
    private static final String CHANNEL_ID = "foreground_service";
    
    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // 创建通知
        Notification notification = createNotification();
        
        // 启动前台 Service（Android 8.0+ 必须使用 startForegroundService()）
        startForeground(NOTIFICATION_ID, notification);
        
        // 执行任务
        doWork();
        
        return START_STICKY;
    }
    
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
    
    private Notification createNotification() {
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Foreground Service")
            .setContentText("Service is running...")
            .setSmallIcon(R.drawable.ic_notification)
            .build();
    }
    
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
```

### 5.2 启动前台 Service

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
- 前台 Service 优先级高，系统不会轻易杀死

---

## 六、 IntentService（已废弃，了解即可）

`IntentService` 是 Service 的子类，在后台线程中处理异步请求。**Android 8.0+ 已废弃**，推荐使用 `JobIntentService` 或 `WorkManager`。

### 6.1 IntentService 的特点

- 自动创建后台线程
- 自动处理多个请求（串行执行）
- 执行完毕后自动停止

### 6.2 实现示例

```java
public class MyIntentService extends IntentService {
    public MyIntentService() {
        super("MyIntentService");
    }
    
    @Override
    protected void onHandleIntent(Intent intent) {
        // 在后台线程执行
        String action = intent.getAction();
        // 处理任务
    }
}
```

---

## 七、 Service 的权限与安全

### 7.1 声明 Service

```xml
<service
    android:name=".MyService"
    android:enabled="true"
    android:exported="false"  <!-- 是否允许其他应用访问 -->
    android:permission="com.example.PERMISSION" />  <!-- 访问权限 -->
```

### 7.2 exported 属性

| 值 | 说明 |
| :--- | :--- |
| `true` | 其他应用可以访问（需要声明权限） |
| `false` | 只有同一应用可以访问 |
| 未设置 | 如果有 Intent-Filter，默认为 `true`；否则为 `false` |

### 7.3 权限保护

```xml
<!-- 声明权限 -->
<permission
    android:name="com.example.USE_MY_SERVICE"
    android:protectionLevel="normal" />

<!-- Service 使用权限 -->
<service
    android:name=".MyService"
    android:permission="com.example.USE_MY_SERVICE" />
```

---

## 八、 常见使用场景

### 8.1 音乐播放

```java
public class MusicService extends Service {
    private MediaPlayer mMediaPlayer;
    
    @Override
    public void onCreate() {
        super.onCreate();
        mMediaPlayer = new MediaPlayer();
    }
    
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent.getAction();
        if ("PLAY".equals(action)) {
            playMusic();
        } else if ("PAUSE".equals(action)) {
            pauseMusic();
        }
        return START_STICKY;
    }
    
    private void playMusic() {
        // 播放音乐
    }
    
    private void pauseMusic() {
        // 暂停音乐
    }
}
```

### 8.2 文件下载

```java
public class DownloadService extends Service {
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String url = intent.getStringExtra("url");
        
        // 在后台线程下载
        new Thread(() -> {
            downloadFile(url);
            stopSelf(startId);
        }).start();
        
        return START_NOT_STICKY;
    }
    
    private void downloadFile(String url) {
        // 下载逻辑
    }
}
```

### 8.3 数据同步

```java
public class SyncService extends Service {
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // 定期同步数据
        syncData();
        return START_STICKY;
    }
    
    private void syncData() {
        // 同步逻辑
    }
}
```

---

## 九、 最佳实践

### 9.1 避免在生命周期方法中执行耗时操作

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
    // 启动后台线程
    new Thread(() -> {
        downloadLargeFile();
    }).start();
}
```

### 9.2 及时停止 Service

```java
// 任务完成后及时停止
@Override
public int onStartCommand(Intent intent, int flags, int startId) {
    new Thread(() -> {
        doWork();
        stopSelfResult(startId);  // 完成后停止
    }).start();
    return START_NOT_STICKY;
}
```

### 9.3 使用前台 Service 提升优先级

对于需要长期运行的任务，使用前台 Service 可以避免被系统杀死。

### 9.4 合理选择启动方式

- **独立任务**：使用 `startService()`
- **需要通信**：使用 `bindService()`
- **既需要独立运行又需要通信**：同时使用两种方式

---

## 十、 总结

1. **Service 类型**：Started Service、Bound Service、Foreground Service
2. **生命周期**：Started 和 Bound 的生命周期不同，需要分别理解
3. **启动方式**：`startService()` 用于独立任务，`bindService()` 用于提供接口
4. **进程分类**：本地 Service 性能好，远程 Service 可跨进程
5. **前台 Service**：显示通知，优先级高，适合长期运行的任务

---
**下一篇：** [进阶篇：Service 底层实现与 Binder 通信机制](02_Advanced_Service.md)
