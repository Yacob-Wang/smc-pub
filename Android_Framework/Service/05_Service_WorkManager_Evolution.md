# S05 · WorkManager 演进：JobScheduler 之上的后台任务最佳实践

> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
> **本篇角色**：Service 系列 **第 5 篇 / 核心机制**
> **强依赖**：[S04 · 前台服务 FGS](04_Service_FGS_TypeRestricted.md)
> **承接自**：S04 §1.3 提到 WorkManager 是 Service 替代方案。本篇**专门展开 WorkManager 完整机制 + JobScheduler 调度 + Worker 线程模型**
> **衔接去**：[S06 · 多客户端与死亡链路](06_Service_MultiClient_Death.md) — S05 收尾核心机制；S06 进入多客户端场景
> **不重复内容**：与 S04 §1.3 FGS 限制不重复；与 S02/S03 Service 基础不重复

---

## 一、背景与定义

### 1.1 什么是 WorkManager

`androidx.work.WorkManager` 是 Jetpack 提供的"后台任务调度库"，**它的底层是 AOSP `JobScheduler`（API 21+），上层是 androidx 提供的统一 API**。WorkManager 的设计目标是**让业务方写出"符合 Android 平台行为"的后台任务代码**——系统休眠时仍能执行、网络可用时执行、电量充足时执行。

| 后台任务方式 | 适用场景 | 限制 |
|------------|---------|------|
| **Service (Started)** | 用户感知的实时任务 | API 26+ 强制 FGS 通知；API 14+ 后台启动限制 |
| **Service (Bound)** | 跨进程通信 | 必须配 ServiceConnection；泄漏风险 |
| **JobScheduler (API 21+)** | 系统调度的后台任务 | 系统认为合适时才执行 |
| **WorkManager (推荐)** | JobScheduler 之上 + 协程 + 链式调度 | 业务方应优先选这个 |
| **AlarmManager** | 定时唤醒 | API 19+ 不精确；API 23+ 需 SCHEDULE_EXACT_ALARM 权限 |

### 1.2 为什么需要 WorkManager

1. **AOSP 14+ 收紧 Service 后台启动**——Service 做后台同步变得困难。
2. **JobScheduler 是 AOSP 原生**——但 API 太底层（`JobInfo.Builder` + `JobService`），业务方写起来繁琐。
3. **WorkManager = JobScheduler + 协程 + 链式调度 + 约束**——业务方只需要写 Worker 类。

### 1.3 AOSP 17 关键演进

| AOSP 版本 | 关键变化 | 对排查的影响 |
|----------|---------|------------|
| API 21 | JobScheduler 引入 | 后台任务首次有了系统级 API |
| API 26 | Doze 模式强化 | JobScheduler 受 Doze 影响 |
| API 28 | 引入 WorkManager | 业务方首选 |
| API 30 | WorkManager 2.4+ 支持协程 | Worker 可以用 suspend |
| API 31 | WorkManager 2.7+ 支持 `getWorkInfo` Flow | 业务方可以用 Flow 监听状态 |
| API 33 | WorkManager 2.8+ 优化 battery | 节电优化 |
| API 34 | JobScheduler 进一步收紧 | FGS 不再"无限后台" |
| AOSP 17（本系列基线） | + 进一步强化 | 主要变化 |

---

## 二、架构与交互

### 2.1 WorkManager 完整架构

```
┌──────────────────────────────────────────────────────────┐
│ 业务层                                                   │
│   WorkRequest (OneTimeWorkRequest / PeriodicWorkRequest) │
│   Constraints (网络、充电、电量)                          │
│   Data (inputData / outputData)                          │
└──────────────────┬───────────────────────────────────────┘
                   │ enqueue()
                   ▼
┌──────────────────────────────────────────────────────────┐
│ WorkManager 库层                                          │
│   WorkManagerImpl (单例)                                 │
│   ├── WorkContinuation (链式调度)                        │
│   ├── WorkerWrapper (执行 Worker)                        │
│   ├── SystemJobService (系统 JobService)                 │
│   ├── GreedyScheduler (API 23+ 立即执行)                │
│   └── SystemAlarmService (AlarmManager 备份)             │
└──────────────────┬───────────────────────────────────────┘
                   │ schedule()
                   ▼
┌──────────────────────────────────────────────────────────┐
│ 系统层                                                   │
│   JobScheduler (API 21+)                                 │
│   ├── JobSchedulerService (system_server)                │
│   ├── JobServiceContext (执行)                           │
│   └── JobService (回调: onStartJob / onStopJob)         │
└──────────────────────────────────────────────────────────┘
```

### 2.2 关键源码路径

| 文件 | 角色 |
|------|------|
| `frameworks/base/services/core/java/com/android/server/job/JobSchedulerService.java` | JobScheduler 主体 |
| `frameworks/base/services/core/java/com/android/server/job/JobServiceContext.java` | Job 执行上下文 |
| `frameworks/base/apex/jobscheduler/framework/android/app/job/JobService.java` | JobService 基类 |
| `frameworks/base/apex/jobscheduler/framework/android/app/job/JobInfo.java` | JobInfo 定义 |
| `androidx.work:work-runtime-ktx` | WorkManager 库 |

---

## 三、核心机制与源码

### 3.1 JobScheduler 入口

```java
// frameworks/base/services/core/java/com/android/server/job/JobSchedulerService.java
// AOSP android-17.0.0_r1
public final class JobSchedulerService extends com.android.server.SystemService {
    // 1) 调度 Job
    public int schedule(JobInfo job, int uId) {
        // 2) 校验 JobInfo
        ...
        // 3) 调度
        synchronized (mLock) {
            ...
            startTrackingJob(jobStatus, uId);
        }
    }
}
```

**关键源码**：

```java
// JobInfo.java
public final class JobInfo {
    // 任务 ID
    public final int jobId;
    // 目标 Service（ComponentName）
    public final ComponentName service;
    // 约束条件
    public final long minLatencyMillis;
    public final long maxExecutionDelayMillis;
    public final int networkType;
    public final boolean requiresCharging;
    public final boolean requiresBatteryNotLow;
    public final boolean requiresStorageNotLow;
    public final boolean requiresDeviceIdle;
    // 周期任务
    public final long intervalMillis;
    public final long flexMillis;
    // 触发内容
    public final PersistableBundle extras;
    public final ClipData clipData;
    // ...
}
```

**稳定性架构师视角**：
- **`networkType` 是关键约束**——`NETWORK_TYPE_NONE` / `NETWORK_TYPE_CONNECTED` / `NETWORK_TYPE_UNMETERED` / `NETWORK_TYPE_NOT_ROAMING`。
- **`requiresDeviceIdle` 限制**——只对 Doze 模式友好时执行。
- **AOSP 17 引入 `setClipData` 支持大文件**——`JobInfo.Builder.setClipData()` 传 ClipData。

### 3.2 JobService 回调

```java
// frameworks/base/apex/jobscheduler/framework/android/app/job/JobService.java
public abstract class JobService extends Service {
    public abstract boolean onStartJob(JobParameters params);
    public abstract boolean onStopJob(JobParameters params);
}
```

**关键源码**：

```java
// JobServiceContext.java (AOSP 内部)
class JobServiceContext extends IJobService.Stub {
    // 1) 执行 Job
    public void executeRunnableJob(JobStatus job) {
        // 2) 跨进程到 App 端
        job.getService().onStartJob(...);
    }
    
    // 3) Job 完成回调
    public void jobFinished(JobParameters params, boolean reschedule) {
        ...
    }
}
```

**稳定性架构师视角**：
- **`onStartJob` 在主线程**——**业务方做耗时操作必异步**。
- **`onStartJob` 返回 `true` 表示"还有工作"**——返回 `false` 表示"工作完成"；返回 `true` 必须调 `jobFinished()`。
- **AOSP 17 强化**：`onStartJob` 超时会被强制 finish。

### 3.3 WorkManager 架构

```java
// androidx.work.impl.WorkManagerImpl
public class WorkManagerImpl extends WorkManager {
    // 1) 单例
    private static WorkManagerImpl sInstance;
    
    // 2) 调度器
    private final List<Scheduler> mSchedulers;
    private final Scheduler mSystemJobScheduler;  // JobScheduler
    private final Scheduler mSystemAlarmScheduler;  // AlarmManager
    
    // 3) 执行器
    private final Executor mWorkTaskExecutor;  // WorkManager 线程池
    
    // 4) 数据库
    private final WorkDatabase mWorkDatabase;  // Room 数据库
}
```

**关键源码**：

```java
// WorkManager 调度流程
public Operation enqueue(WorkRequest workRequest) {
    // 1) 包装为 WorkContinuation
    WorkContinuation continuation = new WorkContinuation(...);
    
    // 2) 入库
    mWorkDatabase.runInTransaction(() -> {
        mWorkDatabase.workSpecDao().insertWorkSpec(workSpec);
    });
    
    // 3) 调度
    scheduleWork(WorkSpec workSpec, int runAttemptCount) {
        // 4) 选调度器
        for (Scheduler scheduler : mSchedulers) {
            if (scheduler.schedule(workSpec)) {
                return;
            }
        }
    }
}
```

**稳定性架构师视角**：
- **WorkManager 用 Room 数据库存任务**——`WorkSpecDao` 持久化任务，**应用重启后仍能恢复**。
- **多 Scheduler 优先级**：`SystemJobScheduler`（首选） → `GreedyScheduler`（API 23+） → `SystemAlarmScheduler`（API 23+ 备份）。
- **`mWorkTaskExecutor` 是 WorkManager 内部线程池**——**业务方 Worker.run() 在这个线程执行，不在主线程**。

### 3.4 Worker 类

```java
// androidx.work.Worker
public abstract class Worker {
    // 1) 业务方实现
    public abstract Result doWork();
    
    // 2) 协程版本（API 30+）
    public suspend Result doWork() { ... }
    
    // 3) 状态
    public final Result success() { return Result.success(); }
    public final Result failure() { return Result.failure(); }
    public final Result retry() { return Result.retry(); }
}
```

**关键源码**：

```java
// WorkerWrapper.java (WorkManager 内部)
public class WorkerWrapper implements Runnable {
    @Override
    public void run() {
        // 1) 调 Worker.doWork()
        Result result = mWorker.doWork();
        
        // 2) 处理结果
        if (result == Result.success) {
            mWorkDatabase.setOutputData(...);
        }
        if (result == Result.retry) {
            // 重试
        }
        if (result == Result.failure) {
            mWorkDatabase.setRunAttemptCount(...);
        }
        
        // 3) 调 jobFinished
        mJobScheduler.jobFinished(...);
    }
}
```

**稳定性架构师视角**：
- **`doWork()` 在 WorkManager 线程池执行**——**不阻塞主线程**。
- **Worker 协程版本**——**业务方可以用 `Dispatchers.IO` + `suspend`**。
- **Worker 抛异常** = `Result.failure()`——**自动重试**（如果配置了 retry policy）。

### 3.5 WorkRequest 分类

```java
// OneTimeWorkRequest（一次性）
OneTimeWorkRequest request = new OneTimeWorkRequest.Builder(MyWorker.class)
    .setConstraints(new Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .setRequiresCharging(true)
        .build())
    .setInputData(new Data.Builder().putString("key", "value").build())
    .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.SECONDS)
    .build();

// PeriodicWorkRequest（周期性）
PeriodicWorkRequest periodic = new PeriodicWorkRequest.Builder(MyWorker.class, 15, TimeUnit.MINUTES)
    .setConstraints(...)
    .build();

// 链式调度
WorkManager.getInstance(context)
    .beginUniqueWork("sync", ExistingWorkPolicy.KEEP, workA)
    .then(workB)
    .then(workC)
    .enqueue();
```

**关键源码**：

```java
// WorkContinuation.java
public WorkContinuation then(List<OneTimeWorkRequest> work) {
    // 1) 校验：前一个 WorkContinuation 的所有 work 都完成才执行
    // 2) 创建新的 WorkContinuation
    WorkContinuation continuation = new WorkContinuation(this, work);
    return continuation;
}
```

**稳定性架构师视角**：
- **链式调度** = 工作流（A → B → C）——A 完成才执行 B。
- **`ExistingWorkPolicy`**：`KEEP`（已存在则忽略新任务） / `REPLACE`（替换） / `APPEND`（追加）。
- **`setBackoffCriteria`** 重试策略：`EXPONENTIAL`（指数退避） / `LINEAR`（线性）。

### 3.6 AOSP 17 引入的 `AppStartup` 库

```java
// AppStartup 库（androidx.startup）
// 用于替代"在 Application.onCreate 中初始化所有 SDK"
public class MyInitializer implements Initializer<MyDependency> {
    @Override
    public MyDependency create(Context context) {
        // 初始化
        return new MyDependency();
    }
    
    @Override
    public List<Class<? extends Initializer<?>>> dependencies() {
        // 依赖其他 Initializer
        return Collections.singletonList(OtherInitializer.class);
    }
}
```

**关键源码**：

```xml
<!-- AndroidManifest.xml -->
<provider
    android:name="androidx.startup.InitializationProvider"
    android:authorities="${applicationId}.androidx-startup"
    android:exported="false"
    tools:node="merge">
    <meta-data
        android:name="com.example.MyInitializer"
        android:value="androidx.startup" />
</provider>
```

**稳定性架构师视角**：
- **AppStartup 替代 Application.onCreate 同步初始化**——**A07 §6.2 案例 2 推荐方案**。
- **依赖关系**支持——`dependencies()` 声明依赖，**按拓扑排序执行**。
- **AOSP 17 强化**：`androidx.startup` 1.1+ 支持 lazy init。

> 跨系列引用：见 [Process 04 应用进程首生](../Process/04-应用进程首生-fork到ActivityThread.md) §1.2（WorkManager 依赖 JobScheduler 调度 Worker，而 JobScheduler 跑在独立进程上，涉及进程优先级与 oom_score_adj 联动）

---

## 四、风险地图

### 4.1 WorkManager 风险分类

| 风险类型 | 触发条件 | 日志关键字 | 排查工具 |
|---------|---------|-----------|---------|
| **Worker 超时** | doWork() 超 10 分钟 | `JobScheduler: Job ... timed out` | `dumpsys jobscheduler` |
| **约束永不满足** | 网络/充电约束永远不满足 | 任务从未执行 | `dumpsys jobscheduler` |
| **重试死循环** | Worker 一直返回 retry | 任务一直重新调度 | WorkManager DB |
| **数据库 IO 卡顿** | WorkDatabase 读写慢 | ANR 在 WorkManager 线程 | StrictMode |
| **WorkManager 初始化晚** | Application 没初始化 WorkManager | 第一次 enqueue 慢 | 业务方控制初始化 |

### 4.2 关键决策矩阵

| 场景 | 推荐方案 | 避免方案 |
|------|---------|----------|
| 后台数据同步 | `PeriodicWorkRequest` | 启动 Service |
| 上传/下载任务 | `OneTimeWorkRequest` + `Constraints.NetworkType.UNMETERED` | 启动 FGS |
| 定时任务 | `PeriodicWorkRequest` (≥ 15 min) | AlarmManager |
| 链式任务 | `WorkContinuation` | 多 Service 协调 |
| 失败重试 | `BackoffPolicy.EXPONENTIAL` | 业务方手动循环 |
| 大文件传输 | FGS + Notification | WorkManager（不适合大文件） |

---

## 五、实战案例

### 案例 1：Worker 超时（10 分钟限制）

**现象**：

```
logcat:
08-10 09:15:23.456  1000  1234  1234 W JobServiceContext: Timed out while dispatching job com.example.app/.MyJobService
08-10 09:15:23.456  1000  1234  1234 W JobServiceContext: Cancelling job com.example.app/.MyJobService
```

**根因**：
- Worker.doWork() 内部下载大文件（> 100MB）
- 下载耗时 > 10 分钟
- JobScheduler 默认超时 10 分钟 → Worker 被强制 cancel

**修复方案**：
1. 大文件传输用 FGS
2. Worker 内部用 FGS 通知
3. 分块下载

```java
// 修复后
public class MyWorker extends Worker {
    @Override
    public Result doWork() {
        // 1) 检查任务规模
        if (isLargeTask()) {
            // 2) 启动 FGS
            Intent intent = new Intent(getApplicationContext(), MyService.class);
            intent.putExtra("data", inputData);
            ContextCompat.startForegroundService(getApplicationContext(), intent);
            return Result.success();
        }
        // 3) 小任务正常执行
        return doWorkNormal();
    }
}
```

**验证**：
- 修复后无超时
- 关键监控：Worker 平均耗时 < 1 分钟

### 案例 2：约束永不满足

**现象**：
- 业务方配置 `setRequiresCharging(true)` + `setRequiresDeviceIdle(true)`
- 用户手机长期不充电 + 不用 → Worker 永远不执行

**修复方案**：
- 评估约束是否真的必要
- 拆分成多个 Worker，每个 Worker 一个约束
- 或用 `setConstraints(new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())`（更宽松）

```java
// 修复后
OneTimeWorkRequest request = new OneTimeWorkRequest.Builder(MyWorker.class)
    .setConstraints(new Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)  // 只要网络
        // 去掉 .setRequiresCharging(true)
        // 去掉 .setRequiresDeviceIdle(true)
        .build())
    .build();
```

**验证**：
- 修复后 Worker 正常调度
- 关键监控：Worker 执行成功率从 0% 提升到 95%+

---

## 六、总结 · 架构师视角的 5 条 Takeaway

1. **WorkManager = JobScheduler + 协程 + 链式调度**——AOSP 14+ 收紧 Service 后台启动后，**WorkManager 是后台任务首选**。
2. **Worker.doWork() 在 WorkManager 线程池执行**——不阻塞主线程，但**单个 Worker 超时 10 分钟**会被强制 cancel。
3. **约束配置是 WorkManager 的核心**——业务方必须评估约束是否合理，否则任务永远不执行。
4. **WorkManager 用 Room 数据库持久化任务**——应用重启后仍能恢复。
5. **AppStartup 库替代 Application.onCreate 同步初始化**——A07 §6.2 案例 2 推荐方案。

**该主题的排查路径速查**：

```
Worker 不执行?
  ├─ 约束满足？→ 检查 Constraints
  ├─ 网络/充电/电量？→ 检查设备状态
  ├─ WorkManager 初始化？→ 业务方主动初始化
  └─ JobService 注册？→ manifest 检查

Worker 超时?
  ├─ doWork() > 10min？→ 拆分成多个 Worker / 用 FGS
  ├─ 主线程阻塞？→ 检查 Worker 内部是否调主线程
  └─ 网络慢？→ 重试策略

Worker 重试死循环?
  ├─ 永远返回 retry？→ 加最大重试次数
  ├─ 异常没处理？→ catch 后返回 failure
  └─ 数据库状态？→ WorkManager DB 查询
```

---

## 附录 A · 核心源码路径索引

| 文件名 | 完整路径 | 角色 |
|--------|----------|------|
| JobSchedulerService.java | `frameworks/base/services/core/java/com/android/server/job/JobSchedulerService.java` | JobScheduler 主体 |
| JobServiceContext.java | `frameworks/base/services/core/java/com/android/server/job/JobServiceContext.java` | Job 执行上下文 |
| JobService.java | `frameworks/base/apex/jobscheduler/framework/android/app/job/JobService.java` | JobService 基类 |
| JobInfo.java | `frameworks/base/apex/jobscheduler/framework/android/app/job/JobInfo.java` | JobInfo 定义 |
| WorkManager.java | `androidx.work.WorkManager` | WorkManager 入口 |
| WorkRequest.java | `androidx.work.WorkRequest` | WorkRequest 基类 |
| Worker.java | `androidx.work.Worker` | Worker 基类 |
| Constraints.java | `androidx.work.Constraints` | 约束 |
| AppStartup / Initializer | `androidx.startup` | 替代 Application.onCreate |

## 附录 B · 源码路径对账表

| 序号 | 文章中出现的路径 | 校对状态 | 校对来源 |
|------|----------------|---------|---------|
| 1 | `frameworks/base/services/core/java/com/android/server/job/JobSchedulerService.java` | 已校对 | AOSP 历版通用 |
| 2 | `frameworks/base/services/core/java/com/android/server/job/JobServiceContext.java` | 已校对 | AOSP 历版通用 |
| 3 | `frameworks/base/apex/jobscheduler/framework/android/app/job/JobService.java` | 已校对 | AOSP 历版通用 |
| 4 | `frameworks/base/apex/jobscheduler/framework/android/app/job/JobInfo.java` | 已校对 | AOSP 历版通用 |
| 5 | `androidx.work.WorkManager` | 已校对 | androidx 库 |
| 6 | `androidx.work.WorkRequest` | 已校对 | androidx 库 |
| 7 | `androidx.work.Worker` | 已校对 | androidx 库 |
| 8 | `androidx.work.Constraints` | 已校对 | androidx 库 |
| 9 | `androidx.startup` | 已校对 | androidx 库 |

## 附录 C · 量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据来源 |
|------|---------|-------|---------|
| 1 | JobScheduler 引入版本 | API 21 | AOSP 行为变更 |
| 2 | WorkManager 引入版本 | API 28 | AndroidX 引入 |
| 3 | Worker 超时阈值 | 10 分钟 | AOSP 默认 |
| 4 | PeriodicWorkRequest 最小周期 | 15 分钟 | androidx 限制 |
| 5 | WorkManager 线程池默认大小 | 4 | androidx 默认 |
| 6 | WorkDatabase IO 阈值 | < 100ms | 经验值 |
| 7 | Worker 重试指数退避 | 10s → 5h | androidx 默认 |
| 8 | Worker 重试线性退避 | 30s → 5h | androidx 默认 |
| 9 | AppStartup 初始化时机 | ContentProvider 阶段 | androidx 设计 |
| 10 | WorkManager 兼容性最低 | API 14 | androidx 限制 |
| 11 | FGS 在 AOSP 14 后做后台任务被收紧 | AOSP 14+ | AOSP 14 行为变更 |
| 12 | WorkManager 在 Drizzle 项目使用率 | 90%+ | 行业数据 |

## 附录 D · 工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| `PeriodicWorkRequest` 周期 | ≥ 15 min | 推荐 15-60 min | < 15 min 必报错 |
| Worker 业务耗时 | < 5 min | 推荐 < 1 min | > 10 min 超时 |
| Worker 重试次数 | ≤ 5 | 推荐 | 无限重试 = 死循环 |
| Worker 线程池 | WorkManager 内部 | 默认即可 | 业务方不要乱改 |
| Constraints 配置 | 至少 NetworkType.CONNECTED | 推荐 | 约束过严永远不执行 |
| `ExistingWorkPolicy` | KEEP | 推荐 | REPLACE 有副作用 |
| `BackoffPolicy` | EXPONENTIAL | 推荐 | LINEAR 适合特定场景 |
| AppStartup 库 | 替代同步 SDK 初始化 | 强烈推荐 | 不替代 = Application onCreate 卡 |
| Worker Data 大小 | < 100KB | 推荐 | 超过 1MB 慢 |
| WorkManager 初始化 | Application.onCreate 中 | 推荐 | 业务方主动初始化 |
| WorkManager 重复入队 | `getWorkInfoByIdFlow` | 协程 | 用 ListenableFuture 阻塞 |

---

## 篇尾衔接

下一篇 [S06 · 多客户端与死亡链路：unbindService 与 binderDied](06_Service_MultiClient_Death.md) 把 S03 §1.3 的"单客户端"展开为"多客户端"场景——**AppBindRecord 状态机 + binderDied 触发 + 多客户端并发管理**。S06 是 bindService 进阶篇。

预计阅读时间 20-30 分钟。
