# Service 进阶篇：底层实现、Binder 通信与进程管理

## 📋 概述

在基础篇中我们了解了 Service 的使用方法和生命周期。本篇将深入 Android Framework 层，分析 Service 的底层实现机制，包括 `ActiveServices` 如何管理 Service、Binder 通信的完整流程、进程启动与绑定机制，以及 Service 与进程生命周期的关联。

---

## 一、 ActiveServices：Service 管理的核心组件

### 1.1 ActiveServices 的职责

`ActiveServices` 是 Android 系统中管理所有 Service 的核心类，位于 `ActivityManagerService` 中。

**核心职责**：
- 管理 Service 的启动、绑定、停止
- 监控 Service 的执行状态和超时
- 处理 Service 的进程启动和绑定
- 维护 Service 与进程的关联关系

### 1.2 关键数据结构

```java
// ActiveServices.java
public final class ActiveServices {
    // Service 记录表：key 是 ComponentName，value 是 ServiceRecord
    final ArrayMap<ComponentName, ServiceRecord> mServicesByName = new ArrayMap<>();
    
    // 按进程分组的 Service：key 是 ProcessRecord，value 是该进程的所有 Service
    final ArrayMap<ProcessRecord, ArrayList<ServiceRecord>> mServicesByProcess = new ArrayMap<>();
    
    // 正在执行的 Service（用于超时检测）
    final ArrayList<ServiceRecord> mExecutingServices = new ArrayList<>();
    
    // 等待启动的 Service（进程未就绪时）
    final ArrayList<ServiceRecord> mPendingServices = new ArrayList<>();
}
```

### 1.3 ServiceRecord：Service 的完整信息

```java
// ServiceRecord.java
final class ServiceRecord extends Binder {
    // Service 基本信息
    final ComponentName name;           // Service 组件名
    final ApplicationInfo appInfo;      // 应用信息
    final Intent.FilterComparison intent; // Intent
    
    // 进程信息
    ProcessRecord app;                  // 运行该 Service 的进程
    ProcessRecord isolatedProc;         // 隔离进程（如果使用）
    
    // 启动信息
    long createTime;                    // 创建时间
    long startingBgTimeout;             // 后台启动超时时间
    boolean startRequested;             // 是否已请求启动
    
    // 绑定信息
    final ArrayList<ConnectionRecord> connections = new ArrayList<>(); // 所有绑定连接
    int bindCount;                      // 绑定次数
    
    // 执行状态
    boolean executing;                  // 是否正在执行
    long executingStart;                // 开始执行时间
    int executeNesting;                 // 执行嵌套深度
    
    // 前台服务
    boolean isForeground;               // 是否为前台服务
    int foregroundId;                   // 通知 ID
    Notification foregroundNoti;        // 前台通知
}
```

---

## 二、 Service 启动的完整流程

### 2.1 startService() 的调用链

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

### 2.2 ActiveServices.startServiceLocked() 详解

```java
// ActiveServices.java
ComponentName startServiceLocked(IApplicationThread caller, Intent service,
        String resolvedType, int callingPid, int callingUid, ...) {
    
    // 1. 查找或创建 ServiceRecord
    ServiceLookupResult res = retrieveServiceLocked(service, resolvedType,
        callingPid, callingUid, ...);
    if (res == null) {
        return null;
    }
    
    ServiceRecord r = res.record;
    
    // 2. 检查权限
    if (!mAm.checkComponentPermission(r.permission, callingPid, callingUid, ...)) {
        return null;
    }
    
    // 3. 启动 Service
    return startServiceInnerLocked(r, service, ...);
}

ComponentName startServiceInnerLocked(ServiceRecord r, Intent service, ...) {
    // 1. 更新 Service 状态
    r.startRequested = true;
    r.lastActivity = SystemClock.uptimeMillis();
    r.startingBgTimeout = SystemClock.uptimeMillis() + SERVICE_BACKGROUND_TIMEOUT;
    
    // 2. 启动 Service（如果进程不存在，先启动进程）
    return bringUpServiceLocked(r, service.getFlags(), ...);
}
```

### 2.3 bringUpServiceLocked()：启动 Service 的核心方法

```java
// ActiveServices.java
private String bringUpServiceLocked(ServiceRecord r, int intentFlags, ...) {
    // 1. 检查进程是否已存在
    ProcessRecord app = mAm.getProcessRecordLocked(r.processName, r.appInfo.uid, true);
    
    if (app != null && app.thread != null) {
        // 进程已存在，直接启动 Service
        return realStartServiceLocked(r, app, ...);
    }
    
    // 2. 进程不存在，需要先启动进程
    if (app == null) {
        // 启动新进程
        app = mAm.startProcessLocked(r.processName, r.appInfo, ...);
        if (app == null) {
            return "Unable to launch app " + r.appInfo.packageName;
        }
    }
    
    // 3. 进程正在启动中，将 Service 加入待启动队列
    if (!mPendingServices.contains(r)) {
        mPendingServices.add(r);
    }
    
    // 4. 等待进程启动完成（在 attachApplicationLocked 中处理）
    return null;
}
```

### 2.4 realStartServiceLocked()：实际启动 Service

```java
// ActiveServices.java
private final void realStartServiceLocked(ServiceRecord r,
        ProcessRecord app, boolean execInFg) throws RemoteException {
    
    // 1. 更新 Service 状态
    r.app = app;
    r.appInfo = app.info;
    r.createTime = SystemClock.uptimeMillis();
    
    // 2. 将 Service 加入进程的 Service 列表
    app.services.add(r);
    
    // 3. 设置执行状态和超时监控
    bumpServiceExecutingLocked(r, execInFg, "create");
    
    // 4. 通过 Binder 调用应用进程，创建 Service
    app.thread.scheduleCreateService(r, r.serviceInfo,
        mAm.compatibilityInfoForPackageLocked(r.serviceInfo.applicationInfo),
        app.getReportedProcState());
    
    // 5. 如果 Service 已启动过，直接调用 onStartCommand
    requestServiceBindingLocked(r, ...);
}
```

### 2.5 应用进程侧：handleCreateService()

```java
// ActivityThread.java
private void handleCreateService(CreateServiceData data) {
    // 1. 加载 Service 类
    LoadedApk packageInfo = getPackageInfoNoCheck(
        data.info.applicationInfo, data.compatInfo);
    Service service = null;
    try {
        java.lang.ClassLoader cl = packageInfo.getClassLoader();
        service = (Service) cl.loadClass(data.info.name).newInstance();
    } catch (Exception e) {
        // 处理异常
    }
    
    // 2. 创建 Context
    ContextImpl context = ContextImpl.createAppContext(this, packageInfo);
    context.setOuterContext(service);
    
    // 3. 创建 Application（如果还没有）
    Application app = packageInfo.makeApplication(false, mInstrumentation);
    
    // 4. 调用 Service.onCreate()
    service.attach(context, this, data.info.name, data.token, app,
        ActivityManager.getService());
    service.onCreate();
    
    // 5. 通知系统 Service 创建完成
    ActivityManager.getService().serviceDoneExecuting(
        data.token, SERVICE_DONE_EXECUTING_ANON, 0, 0);
}
```

---

## 三、 Service 绑定的完整流程

### 3.1 bindService() 的调用链

```
Context.bindService()
  → ContextImpl.bindService()
    → ActivityManagerService.bindService()
      → ActiveServices.bindServiceLocked()
        → requestServiceBindingLocked()
          → app.thread.scheduleBindService()
            → ActivityThread.handleBindService()
              → Service.onBind()
                → ActivityManager.getService().publishService()
                  → ActiveServices.publishServiceLocked()
                    → ConnectionRecord.conn.connected()
                      → ServiceConnection.onServiceConnected()
```

### 3.2 ActiveServices.bindServiceLocked() 详解

```java
// ActiveServices.java
int bindServiceLocked(IApplicationThread caller, IBinder token,
        Intent service, String resolvedType, ...) {
    
    // 1. 查找或创建 ServiceRecord
    ServiceLookupResult res = retrieveServiceLocked(service, ...);
    ServiceRecord s = res.record;
    
    // 2. 检查 Service 是否已启动
    if (s.app == null) {
        // Service 未启动，先启动
        bringUpServiceLocked(s, service.getFlags(), ...);
    }
    
    // 3. 创建连接记录
    AppBindRecord b = s.retrieveAppBindingLocked(service, callerApp);
    ConnectionRecord c = new ConnectionRecord(b, activity,
        connection, flags, clientLabel, clientIntent);
    
    // 4. 将连接加入 Service 的连接列表
    b.connections.add(c);
    s.connections.add(c);
    
    // 5. 请求绑定
    if ((flags & Context.BIND_AUTO_CREATE) != 0) {
        s.lastActivity = SystemClock.uptimeMillis();
        if (bringUpServiceLocked(s, service.getFlags(), ...) != null) {
            return 0;
        }
    }
    
    // 6. 如果 Service 已启动，立即绑定
    if (s.app != null && s.app.thread != null) {
        requestServiceBindingLocked(s, b.intent, callerFg, true);
    }
    
    return 1;
}
```

### 3.3 requestServiceBindingLocked()：请求绑定

```java
// ActiveServices.java
private final boolean requestServiceBindingLocked(ServiceRecord r,
        IntentBindRecord i, boolean execInFg, boolean rebind) {
    
    // 1. 检查是否已经绑定
    if (r.app == null || r.app.thread == null) {
        return false;
    }
    
    // 2. 设置执行状态
    bumpServiceExecutingLocked(r, execInFg, "bind");
    
    // 3. 通过 Binder 调用应用进程，绑定 Service
    r.app.thread.scheduleBindService(r, i.intent.getIntent(), rebind,
        r.app.getReportedProcState());
    
    return true;
}
```

### 3.4 应用进程侧：handleBindService()

```java
// ActivityThread.java
private void handleBindService(BindServiceData data) {
    // 1. 获取 Service 实例
    Service s = mServices.get(data.token);
    if (s == null) {
        return;
    }
    
    // 2. 调用 Service.onBind()
    IBinder binder = s.onBind(data.intent);
    
    // 3. 通知系统绑定完成，发布 IBinder
    ActivityManager.getService().publishService(
        data.token, data.intent, binder);
}
```

### 3.5 publishServiceLocked()：发布 IBinder

```java
// ActiveServices.java
void publishServiceLocked(ServiceRecord r, Intent intent, IBinder service) {
    // 1. 查找所有等待该 Service 的连接
    IntentBindRecord b = r.bindings.get(intent.getFilter());
    if (b != null && !b.received) {
        b.binder = service;
        b.requested = true;
        b.received = true;
        
        // 2. 通知所有等待的客户端
        for (int conni = r.connections.size() - 1; conni >= 0; conni--) {
            ArrayList<ConnectionRecord> clist = r.connections.get(conni);
            for (int i = 0; i < clist.size(); i++) {
                ConnectionRecord c = clist.get(i);
                if (!c.binding.client.intent.getFilter().equals(intent.getFilter())) {
                    continue;
                }
                
                // 3. 通过 Binder 回调客户端
                try {
                    c.conn.connected(r.name, service);
                } catch (Exception e) {
                    // 处理异常
                }
            }
        }
    }
    
    // 4. 清除执行状态
    serviceDoneExecutingLocked(r, ...);
}
```

---

## 四、 Binder 通信机制深度解析

### 4.1 Binder 架构概述

Binder 是 Android 的进程间通信（IPC）机制，Service 的跨进程通信完全基于 Binder。

**Binder 架构**：
```
客户端进程                   系统进程                   服务端进程
    |                          |                          |
    |--- Binder 驱动 (内核) ---|                          |
    |                          |                          |
    |--- IBinder (代理) -------|------ IBinder (实现) ---|
```

### 4.2 IBinder 接口体系

```java
// IBinder.java
public interface IBinder {
    // 跨进程调用
    boolean transact(int code, Parcel data, Parcel reply, int flags);
    
    // 查询接口
    IInterface queryLocalInterface(String descriptor);
    
    // 检查进程是否存活
    boolean pingBinder();
    
    // 检查是否存活
    boolean isBinderAlive();
}
```

### 4.3 Binder 本地实现（服务端）

```java
// 本地 Service 的 Binder 实现
public class LocalService extends Service {
    private final IBinder mBinder = new LocalBinder();
    
    public class LocalBinder extends Binder {
        LocalService getService() {
            return LocalService.this;
        }
    }
    
    @Override
    public IBinder onBind(Intent intent) {
        return mBinder;  // 返回本地 Binder
    }
}
```

**关键点**：
- 本地 Binder 直接返回对象引用，不经过 Binder 驱动
- `queryLocalInterface()` 返回非 null，表示是本地对象

### 4.4 Binder 代理实现（客户端）

```java
// 客户端获取的 Binder 代理
IBinder binder = ...;  // 从 ServiceConnection 获取

// 检查是否是本地对象
IInterface local = binder.queryLocalInterface(descriptor);
if (local != null) {
    // 本地对象，直接转换
    MyService service = (MyService) local;
} else {
    // 远程对象，使用代理
    MyService service = MyService.Stub.asInterface(binder);
}
```

### 4.5 AIDL 生成的 Binder 代码

```java
// IMyService.aidl 生成的代码
public interface IMyService extends IInterface {
    void doSomething() throws RemoteException;
    
    // Stub：服务端实现基类
    public static abstract class Stub extends Binder implements IMyService {
        public static IMyService asInterface(IBinder obj) {
            if (obj == null) {
                return null;
            }
            IInterface iin = obj.queryLocalInterface(DESCRIPTOR);
            if (iin != null && iin instanceof IMyService) {
                return (IMyService) iin;  // 本地对象
            }
            return new Proxy(obj);  // 远程对象，返回代理
        }
        
        @Override
        public boolean onTransact(int code, Parcel data, Parcel reply, int flags) {
            switch (code) {
                case TRANSACTION_doSomething:
                    data.enforceInterface(DESCRIPTOR);
                    doSomething();  // 调用服务端方法
                    reply.writeNoException();
                    return true;
            }
            return super.onTransact(code, data, reply, flags);
        }
    }
    
    // Proxy：客户端代理类
    private static class Proxy implements IMyService {
        private IBinder mRemote;
        
        Proxy(IBinder remote) {
            mRemote = remote;
        }
        
        @Override
        public void doSomething() throws RemoteException {
            Parcel data = Parcel.obtain();
            Parcel reply = Parcel.obtain();
            try {
                data.writeInterfaceToken(DESCRIPTOR);
                // 通过 Binder 驱动调用服务端
                mRemote.transact(TRANSACTION_doSomething, data, reply, 0);
                reply.readException();
            } finally {
                reply.recycle();
                data.recycle();
            }
        }
    }
}
```

### 4.6 Binder 调用流程

```
客户端调用 service.doSomething()
  → Proxy.doSomething()
    → mRemote.transact(TRANSACTION_doSomething, data, reply, 0)
      → Binder 驱动（内核）
        → 服务端进程的 Binder 线程池
          → Stub.onTransact()
            → Service.doSomething() [实际执行]
              → reply.writeNoException()
                → Binder 驱动返回结果
                  → 客户端收到 reply
```

**关键点**：
- 客户端调用是**同步阻塞**的，会等待服务端返回
- 服务端方法在**Binder 线程池**中执行，不会阻塞主线程
- 如果服务端方法执行时间过长，客户端会一直阻塞，可能导致客户端 ANR

---

## 五、 Service 与进程生命周期的关联

### 5.1 进程优先级提升

当 Service 启动或绑定时，系统会提升进程的优先级：

```java
// ProcessRecord.java
void updateProcessState(int newState) {
    int oldState = curProcState;
    curProcState = newState;
    
    // 根据进程状态设置 OOM 调整值
    setOomAdj();
}

void setOomAdj() {
    int adj;
    if (curProcState == PROCESS_STATE_SERVICE) {
        adj = ProcessList.SERVICE_ADJ;  // 提升优先级
    } else if (curProcState == PROCESS_STATE_TOP) {
        adj = ProcessList.FOREGROUND_APP_ADJ;  // 前台优先级
    }
    // ...
}
```

### 5.2 Service 对进程保活的影响

**Service 启动对进程的影响**：
- 进程优先级提升（从 CACHED 提升到 SERVICE）
- 进程不会被轻易杀死（除非内存严重不足）
- 前台 Service 优先级更高，几乎不会被杀死

**进程被杀死时 Service 的行为**：
- 如果 `onStartCommand()` 返回 `START_STICKY`，进程重启后 Service 会自动重启
- 如果返回 `START_NOT_STICKY`，Service 不会自动重启
- Bound Service 的连接会断开，`onServiceDisconnected()` 会被调用

### 5.3 进程启动完成后的 Service 恢复

```java
// ActivityManagerService.java
final void attachApplicationLocked(IApplicationThread thread, long startTime) {
    ProcessRecord app = getProcessRecordLocked(processName, pid, true);
    
    // ... 进程绑定逻辑 ...
    
    // 恢复待启动的 Service
    if (!mServices.mPendingServices.isEmpty()) {
        for (int i = mServices.mPendingServices.size() - 1; i >= 0; i--) {
            ServiceRecord r = mServices.mPendingServices.get(i);
            if (r.app == app) {
                mServices.realStartServiceLocked(r, app, ...);
                mServices.mPendingServices.remove(i);
            }
        }
    }
}
```

---

## 六、 Service 超时检测机制

### 6.1 超时时间设置

```java
// ActiveServices.java
static final int SERVICE_TIMEOUT = 20 * 1000;  // 前台 Service：20 秒
static final int SERVICE_BACKGROUND_TIMEOUT = 200 * 1000;  // 后台 Service：200 秒
```

### 6.2 超时监控设置

```java
// ActiveServices.java
void bumpServiceExecutingLocked(ServiceRecord r, boolean fg, String why) {
    // 1. 更新执行状态
    r.executing = true;
    r.executingStart = SystemClock.uptimeMillis();
    r.executeNesting++;
    
    // 2. 加入执行列表
    if (!mExecutingServices.contains(r)) {
        mExecutingServices.add(r);
    }
    
    // 3. 设置超时监控
    scheduleServiceTimeoutLocked(r.app);
}

void scheduleServiceTimeoutLocked(ProcessRecord proc) {
    if (proc.executingServices.size() == 0 || proc.thread == null) {
        return;
    }
    
    // 计算超时时间
    long timeout = SERVICE_TIMEOUT;
    if (proc.executingServices.size() > 0) {
        ServiceRecord r = proc.executingServices.get(0);
        if (r.app != null && r.app.processState >= ActivityManager.PROCESS_STATE_IMPORTANT_BACKGROUND) {
            timeout = SERVICE_BACKGROUND_TIMEOUT;  // 后台进程：200 秒
        }
    }
    
    // 发送超时消息
    Message msg = mAm.mHandler.obtainMessage(
        ActivityManagerService.SERVICE_TIMEOUT_MSG);
    msg.obj = proc;
    mAm.mHandler.sendMessageDelayed(msg, timeout);
}
```

### 6.3 超时检测与 ANR 触发

```java
// ActivityManagerService.java
final void serviceTimeout(ProcessRecord proc) {
    // 1. 检查是否真的超时
    long now = SystemClock.uptimeMillis();
    if (proc.executingServices.size() == 0) {
        return;
    }
    
    // 2. 检查每个 Service 是否超时
    for (int i = proc.executingServices.size() - 1; i >= 0; i--) {
        ServiceRecord r = proc.executingServices.get(i);
        if (now - r.executingStart < SERVICE_TIMEOUT) {
            continue;  // 还没超时
        }
        
        // 3. 确实超时，触发 ANR
        String anrMessage = "Executing service " + r.shortInstanceName;
        mAnrHelper.appNotResponding(proc, anrMessage);
    }
}
```

---

## 七、 总结

1. **ActiveServices**：管理所有 Service 的核心组件，维护 ServiceRecord 和进程关联
2. **启动流程**：`startService()` → `bringUpServiceLocked()` → `realStartServiceLocked()` → 应用进程 `onCreate()`
3. **绑定流程**：`bindService()` → `requestServiceBindingLocked()` → 应用进程 `onBind()` → `publishService()` → 客户端回调
4. **Binder 通信**：基于 Binder 驱动，客户端通过代理调用，服务端在 Binder 线程池执行
5. **进程关联**：Service 启动会提升进程优先级，进程被杀死后 Service 可能自动重启

---
**下一篇：** [高阶篇：系统服务、性能优化与高级特性](03_Expert_Service.md)
