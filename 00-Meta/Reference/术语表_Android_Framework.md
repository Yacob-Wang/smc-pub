# 全局术语表（Reference · 术语表）

> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
>
> **生效日期**：2026-07-18
>
> **维护规则**：按 [PROMPT §8.2](../../PROMPT-技术系列文章写作指南.md) 治理
>
> **覆盖系列**：Activity / Service / Broadcast / ContentProvider 四大组件

---

## 一、术语使用规则

1. **任何系列在引入新术语前，先查本表**——避免重复定义
2. **已有术语必须使用本表中的"中文名"**——禁止别名（除非本表"别名"列明确登记）
3. **跨系列文章发现术语漂移，立即开 issue 修复**——本表是术语的"唯一真相源"
4. **本表更新需要 v4 校准流程**——新增术语必须通过 3 轮校准（结构/硬伤/锐度）

---

## 二、四大组件核心术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 组件 | Component | n/a | AOSP 1 | Android 四大组件统称 |
| 活动 | Activity | n/a | AOSP 1 | UI 容器，完整生命周期 |
| 服务 | Service | n/a | AOSP 1 | 后台执行，无 UI |
| 广播接收者 | BroadcastReceiver | "Receiver" | AOSP 1 | 短生命周期回调 |
| 内容提供者 | ContentProvider | "Provider" | AOSP 1 | 跨进程数据共享 |
| 启动 | Start | n/a | AOSP 1 | startService / startActivity / sendBroadcast |
| 绑定 | Bind | n/a | AOSP 1 | bindService |
| 通知 | Notification | n/a | AOSP 1 | 系统通知栏 |

---

## 三、生命周期 / 状态术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 创建 | onCreate | "创建时" | AOSP 1 | Activity/Service/Receiver 入口 |
| 启动 | onStart | "启动时" | AOSP 1 | Activity 可见 |
| 恢复 | onResume | "恢复时" / "Resume 时" | AOSP 1 | Activity 获得焦点 |
| 暂停 | onPause | "暂停时" | AOSP 1 | 强约束：must be quick |
| 停止 | onStop | "停止时" | AOSP 1 | Activity 完全不可见 |
| 销毁 | onDestroy | "销毁时" | AOSP 1 | 资源清理点 |
| 重建 | Recreate | "重新创建" | AOSP 1 | 配置变化触发的销毁+创建 |
| 启动命令 | onStartCommand | n/a | AOSP 1 | Service 接收 Intent |
| 绑定回调 | onBind / onUnbind / onRebind | n/a | AOSP 1 | Service 绑定生命周期 |
| 接收 | onReceive | "收到时" | AOSP 1 | BroadcastReceiver 入口 |
| 任务移除 | onTaskRemoved | n/a | API 14 | 用户从最近任务列表移除 |
| 配置变化 | onConfigurationChanged | n/a | AOSP 1 | configChanges 触发 |
| 内存压力 | onTrimMemory | n/a | API 14 | 内存压力回调 |
| 状态保存 | onSaveInstanceState | n/a | AOSP 1 | 状态序列化 |
| 状态恢复 | onRestoreInstanceState | n/a | AOSP 1 | 状态反序列化 |

---

## 四、进程 / 任务术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 进程 | Process | n/a | AOSP 1 | 操作系统概念 |
| 进程优先级 | ProcessPriority / OomScoreAdj | "oom_adj" | AOSP 1 | 数字越小越不被杀 |
| 进程状态 | ProcessState | n/a | AOSP 1 | TOP/FOREGROUND/VISIBLE/CACHED |
| 任务 | Task | n/a | AOSP 1 | Activity 的逻辑容器 |
| 任务栈 | TaskStack | "Activity 栈" | AOSP 1 | Task 的栈结构 |
| 任务片段 | TaskFragment | n/a | AOSP 12 | Task 子结构，多窗口场景 |
| 任务组织者 | TaskFragmentOrganizer | n/a | AOSP 13 | TaskFragment 管理 API |
| 冷启动 | Cold Start | "冷启" | AOSP 1 | 进程从无到有 |
| 热启动 | Warm Start | "热启" | AOSP 1 | 进程已存在 |
| 后台进程 | Background Process | n/a | AOSP 1 | cached 级别 |
| 前台进程 | Foreground Process | n/a | AOSP 1 | top-app / visible |
| 系统服务 | System Service | "系统进程" | AOSP 1 | system_server 进程 |
| 进程间通信 | IPC | "跨进程" | AOSP 1 | Inter-Process Communication |
| 低内存杀手 | LMK | "Low Memory Killer" | AOSP 1 | 进程回收机制 |
| USAP 池 | Unused Zygote App Process | "预热池" | AOSP 17 | Zygote 预热 |

---

## 五、四大组件特有术语

### 5.1 Activity 特有

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 启动模式 | LaunchMode | "启动模式" | AOSP 1 | standard / singleTop / singleTask / singleInstance |
| 任务亲和性 | taskAffinity | n/a | AOSP 1 | Task 归属 |
| 标准模式 | standard | "标准" | AOSP 1 | 默认模式 |
| 栈顶复用 | singleTop | "顶部复用" | AOSP 1 | 栈顶复用 onNewIntent |
| 单任务 | singleTask | "Task 复用" | AOSP 1 | taskAffinity 范围内唯一 |
| 单实例 | singleInstance | "单例" | AOSP 1 | 独占 Task + 全局单例 |
| 启动窗口 | StartingWindow | n/a | API 5 | 冷启动时的临时 Window |
| 闪屏 | SplashScreen | "启动屏" | API 31+ | 强制 SplashScreen |
| Intent 解析 | Intent Resolution | "Intent 匹配" | AOSP 1 | PMS 端 IntentFilter 匹配 |
| IntentFilter 匹配 | IntentFilter matching | "匹配 Intent" | AOSP 1 | Action / Category / Data 匹配 |
| 包可见性 | Package Visibility | n/a | AOSP 11 | `<queries>` 声明 |
| setPackage | setPackage | "设置 Package" | AOSP 14+ | 显式 Intent 必填 |

### 5.2 Service 特有

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 前台服务 | FGS / Foreground Service | "前台 Service" | AOSP 1 | 必须显示通知 |
| 启动前台 | startForeground | n/a | API 5 | 启动前台服务 |
| 启动前台服务 | startForegroundService | n/a | API 26 | FGS 启动 |
| 后台启动 | Background Start | n/a | API 14+ | 收紧 |
| FGS 类型 | foregroundServiceType | n/a | API 29 | 16 种类型 |
| STICKY | START_STICKY | "粘性" | AOSP 1 | 系统重启传 null |
| 不可重启 | START_NOT_STICKY | "不粘性" | AOSP 1 | 系统不重启 |
| 重发 Intent | START_REDELIVER_INTENT | "重发" | AOSP 1 | 系统重启重发 |
| 服务连接 | ServiceConnection | n/a | AOSP 1 | bindService 回调 |
| 连接池 | Connection Pool | n/a | AOSP 1 | 多客户端 bind 状态 |
| 死亡链路 | Death Link | "死亡通知" | AOSP 1 | binderDied |
| 死亡接收 | DeathRecipient | n/a | AOSP 1 | 死亡回调接口 |
| 后台启动权限 | backgroundStartPrivileges | n/a | API 14+ | 后台启动 FGS 必填 |
| 短期服务 | SHORT_SERVICE | n/a | AOSP 17 | 3 分钟内完成 |
| WorkManager | WorkManager | "工作管理器" | AndroidX 1.0 | 后台任务推荐 |
| JobScheduler | JobScheduler | "任务调度" | API 21 | WorkManager 底层 |
| AppStartup | App Startup | "应用启动" | AndroidX 1.1 | ContentProvider 之前的初始化 |

### 5.3 Broadcast 特有

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 广播 | Broadcast | n/a | AOSP 1 | 跨进程事件分发 |
| 普通广播 | Normal Broadcast | "普通" | AOSP 1 | 并行分发 |
| 有序广播 | Ordered Broadcast | "有序" | AOSP 1 | 串行分发 |
| 粘性广播 | Sticky Broadcast | "粘性" | API 1 | API 31 移除 |
| 进程内广播 | Local Broadcast | "本地广播" | AndroidX 1.0 | LocalBroadcastManager 已废弃 |
| 前台广播 | Foreground Broadcast | n/a | AOSP 1 | 10s ANR |
| 后台广播 | Background Broadcast | n/a | AOSP 1 | 60s ANR |
| 长广播 | Long Broadcast | n/a | AOSP 17 | BROADCAST_FG_LONG_TIMEOUT |
| 中止广播 | abortBroadcast | "中止" | AOSP 1 | 有序广播终止 |
| RECEIVER_EXPORTED | RECEIVER_EXPORTED | n/a | API 33+ | AOSP 14 强制 |
| RECEIVER_NOT_EXPORTED | RECEIVER_NOT_EXPORTED | n/a | API 33+ | 默认 |
| 开机完成 | BOOT_COMPLETED | "开机广播" | AOSP 1 | 系统广播 |
| 锁定启动 | LOCKED_BOOT_COMPLETED | "加密存储启动" | AOSP 7+ | directBootAware |
| 屏幕开关 | SCREEN_ON / SCREEN_OFF | n/a | AOSP 1 | 系统广播 |
| 时区变化 | TIMEZONE_CHANGED | n/a | AOSP 1 | 系统广播 |
| 语言变化 | LOCALE_CHANGED | n/a | AOSP 1 | 系统广播 |
| 网络变化 | CONNECTIVITY_CHANGE | n/a | AOSP 1 | 推荐用 NetworkCallback |
| 动态注册 | Dynamic Registration | "动态" | AOSP 1 | 代码 registerReceiver |
| 静态注册 | Static Registration | "静态" | AOSP 1 | manifest declare |
| 接收者分发器 | ReceiverDispatcher | n/a | AOSP 1 | 动态注册状态机 |

### 5.4 ContentProvider 特有

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 内容提供者 | ContentProvider | "Provider" | AOSP 1 | 跨进程数据共享 |
| URI | URI | "统一资源标识符" | AOSP 1 | content://authority/path |
| 授权方 | Authority | "授权" | AOSP 1 | URI 域名部分 |
| 客户端 | ContentResolver | n/a | AOSP 1 | 业务方调用入口 |
| 客户端 | ContentProviderClient | n/a | AOSP 11+ | AOSP 11+ 推荐 |
| 游标 | Cursor | n/a | AOSP 1 | query 返回 |
| 游标窗口 | CursorWindow | n/a | AOSP 1 | Cursor 内存 |
| 内容观察者 | ContentObserver | n/a | AOSP 1 | 观察者模式 |
| 跨进程 Binder | IContentProvider | n/a | AOSP 1 | Binder 接口 |
| 提供者映射 | ProviderMap | n/a | AOSP 1 | AMS 端 Provider 注册表 |
| 提供者辅助 | ContentProviderHelper | n/a | AOSP 12+ | 12+ 抽出独立类 |
| 提供者连接 | ContentProviderConnection | n/a | AOSP 1 | AMS 端连接 |
| 路径权限 | pathPermission | "URI 路径权限" | AOSP 1 | 局部 URI 权限 |
| 读权限 | readPermission | n/a | AOSP 1 | 全局读权限 |
| 写权限 | writePermission | n/a | AOSP 1 | 全局写权限 |
| 授予 URI 权限 | grantUriPermission | n/a | AOSP 1 | 临时授权 |
| 跨进程查询 | Cross-Process Query | "跨进程 query" | AOSP 1 | Binder 跨进程 |
| 批量插入 | bulkInsert | n/a | AOSP 8+ | 批量操作 |
| 通用调用 | call() | n/a | AOSP 11+ | 通用方法 |
| 事务 | Transaction | "事务" | AOSP 1 | Binder 事务 |
| 单次事务上限 | BINDER_VM_SIZE | "1MB" | AOSP 1 | Binder 1MB 限制 |
| 事务过大异常 | TransactionTooLargeException | n/a | AOSP 1 | > 1MB 抛 |
| 发布超时 | CONTENT_PROVIDER_PUBLISH_TIMEOUT | n/a | AOSP 1 | 10s |
| 最大查询结果 | MAX_QUERY_RESULTS | n/a | AOSP 17 | 1000 |

---

## 六、ANR / 稳定性术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 应用无响应 | ANR / Application Not Responding | n/a | AOSP 1 | 系统级 ANR |
| ANR 阈值 | ANR Timeout | n/a | AOSP 1 | 各组件 ANR 阈值 |
| 输入事件分发超时 | KEY_DISPATCHING_TIMEOUT | "分发超时" | AOSP 1 | 5s |
| 服务启动超时 | SERVICE_TIMEOUT | n/a | AOSP 1 | 20s 前台 |
| 后台服务超时 | SERVICE_BACKGROUND_TIMEOUT | n/a | AOSP 1 | 200s 后台 |
| 启动前台超时 | SERVICE_START_FOREGROUND_TIMEOUT | n/a | AOSP 26 | 10s |
| 短服务超时 | SHORT_SERVICE_TIMEOUT | n/a | AOSP 17 | 3 分钟 |
| 广播前台超时 | BROADCAST_FG_TIMEOUT | n/a | AOSP 1 | 10s |
| 广播后台超时 | BROADCAST_BG_TIMEOUT | n/a | AOSP 1 | 60s |
| 广播长前台 | BROADCAST_FG_LONG_TIMEOUT | n/a | AOSP 17 | 60s |
| 广播长后台 | BROADCAST_BG_LONG_TIMEOUT | n/a | AOSP 17 | 120s |
| 内容提供者发布超时 | CONTENT_PROVIDER_PUBLISH_TIMEOUT | n/a | AOSP 1 | 10s |
| 进程启动超时 | PROC_START_TIMEOUT | n/a | AOSP 1 | 10s |
| ANR 文件 | traces.txt | "anr 文件" | AOSP 1 | /data/anr/ |
| ANR 检测 | AnrHelper | n/a | AOSP 16+ | 异步 ANR 检测 |
| 早期检测 | Early Detection | n/a | AOSP 17 | 超时阈值一半检测 |

---

## 七、内存 / 性能术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 内存压力 | Memory Pressure | "内存" | AOSP 1 | onTrimMemory |
| 低内存 | onLowMemory | n/a | AOSP 1 | API < 14 |
| OomScore | OomScore | "OOM 分数" | AOSP 1 | /proc/<pid>/oom_score_adj |
| OomAdj | OomAdj | n/a | AOSP 1 | 进程优先级 |
| 缓存进程 | Cached Process | n/a | AOSP 1 | 优先杀 |
| 空进程 | Empty Process | n/a | AOSP 1 | 最高被杀优先级 |
| 泄漏 | Leak | n/a | AOSP 1 | 内存泄漏 |
| 静态分析 | Static Analysis | n/a | AOSP 1 | LeakCanary 等 |
| 内存快照 | HPROF | n/a | AOSP 1 | 内存分析文件 |
| GC 根 | GC Root | n/a | AOSP 1 | 不可回收对象 |
| 内存优化器 | OomAdjuster | n/a | AOSP 1 | 进程优先级调度 |
| 进程列表 | ProcessList | n/a | AOSP 1 | 进程管理 |

---

## 八、Binder / IPC 术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 进程间通信 | IPC | n/a | AOSP 1 | 跨进程 |
| Binder | Binder | n/a | AOSP 1 | Android IPC 机制 |
| Binder 事务 | Binder Transaction | n/a | AOSP 1 | 一次 IPC 调用 |
| Binder 线程池 | Binder Thread Pool | n/a | AOSP 1 | 默认 15 个 |
| 最大 Binder 线程 | MAX_BINDER_THREADS | n/a | AOSP 1 | 32 |
| Binder 死锁 | Binder Deadlock | n/a | AOSP 1 | 跨进程等待 |
| 客户端 | Proxy | n/a | AOSP 1 | BpBinder |
| 服务端 | Stub | n/a | AOSP 1 | BBinder |
| 事务完成回调 | onTransact | n/a | AOSP 1 | 服务端入口 |
| 死亡接收 | DeathRecipient | n/a | AOSP 1 | binderDied |
| 链接到死亡 | linkToDeath | n/a | AOSP 1 | 设置死亡接收 |
| 取消链接 | unlinkToDeath | n/a | AOSP 1 | 解除死亡接收 |
| 事务过大异常 | TransactionTooLargeException | n/a | AOSP 1 | > 1MB |
| Parcel | Parcel | n/a | AOSP 1 | Binder 数据载体 |
| AIDL | AIDL | n/a | AOSP 1 | 接口定义语言 |
| 跨进程服务 | Cross-Process Service | n/a | AOSP 1 | 跨进程通信 |

---

## 九、协程 / 异步术语（AndroidX）

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 协程 | Coroutine | "协程" | Kotlin 1.3 | 异步 |
| 实时数据 | LiveData | n/a | AndroidX 1.0 | 生命周期感知 |
| 状态流 | StateFlow | n/a | Kotlinx 1.3 | 状态保持 |
| 流 | Flow | n/a | Kotlinx 1.3 | 异步流 |
| 共享数据总线 | LiveDataBus | n/a | AndroidX 1.0 | 跨组件事件 |
| 异步结果 | PendingResult | n/a | AOSP 11+ | goAsync() |
| 异步处理 | goAsync() | n/a | AOSP 11+ | 异步 onReceive |

---

## 十、ART / Runtime 术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| Android 运行时 | ART | n/a | AOSP 5+ | Android Runtime |
| 即时编译 | JIT | n/a | AOSP 7+ | Just-In-Time |
| 预编译 | AOT | n/a | AOSP 7+ | Ahead-Of-Time |
| 字节码 | Bytecode | n/a | AOSP 1 | Java 字节码 |
| 快速字节码 | Quickened Bytecode | n/a | AOSP 17 | ART 17 优化 |
| 分代 GC | Generational GC | n/a | AOSP 17 | ART 17 强化 |
| 静态字面量 | static final | n/a | AOSP 17 | ART 17 优化 |
| 类去重 | Class Deduplication | n/a | AOSP 17 | ART 17 强化 |
| 类扩展 | Class Extent | n/a | AOSP 17 | ART 17 强化 |
| 无锁消息队列 | Lock-free MessageQueue | n/a | AOSP 17 | API 37+ |
| AppFunctions | AppFunctions | n/a | AOSP 17 | AI Agent OS 集成 |
| AI Agent OS | AI Agent OS | n/a | AOSP 17 | AI 集成 |
| 快速本地方法 | FastNative | n/a | AOSP 17 | ART 17 强化 |
| 槽池 | Slot Pool | n/a | AOSP 17 | JNI 优化 |
| 异常清理 | ExceptionClear | n/a | AOSP 17 | JNI 优化 |
| Crash 快速路径 | Crash Fast Path | n/a | AOSP 17 | ART 17 优化 |
| 异步信号安全 | Async-Signal-Safety | n/a | AOSP 17 | ART 17 强化 |

---

## 十一、Manifest 标签术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| 组件声明 | `<activity>` / `<service>` / `<receiver>` / `<provider>` | n/a | AOSP 1 | 四大组件 manifest |
| Intent 过滤器 | `<intent-filter>` | "Intent 过滤" | AOSP 1 | action / category / data |
| 权限声明 | `<uses-permission>` | n/a | AOSP 1 | 申请权限 |
| 自定义权限 | `<permission>` | n/a | AOSP 1 | 定义权限 |
| 强制权限 | `android:permission` | n/a | AOSP 1 | 跨组件权限 |
| 路径权限 | `<path-permission>` | n/a | AOSP 1 | URI 路径权限 |
| 授予权限 | `<grant-uri-permission>` | n/a | AOSP 1 | 临时 URI 授权 |
| 进程声明 | `android:process` | n/a | AOSP 1 | 独立进程 |
| 启动模式 | `android:launchMode` | n/a | AOSP 1 | Activity 启动模式 |
| 任务亲和性 | `android:taskAffinity` | n/a | AOSP 1 | Task 归属 |
| 导出标志 | `android:exported` | n/a | AOSP 12+ | 强制声明 |
| 前台服务类型 | `android:foregroundServiceType` | n/a | API 29+ | 16 种类型 |
| 直启感知 | `android:directBootAware` | n/a | AOSP 7+ | 加密存储启动 |
| 查询声明 | `<queries>` | n/a | AOSP 11+ | 包可见性 |

---

## 十二、Linux 内核术语（android17-6.18）

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| Linux 内核 | Linux Kernel | "内核" | AOSP 1 | OS 内核 |
| 进程 | Process | n/a | Linux | OS 概念 |
| 文件描述符 | File Descriptor | n/a | Linux | fd |
| 进程间通信 | IPC | n/a | Linux | 通用概念 |
| 控制组 | cgroup | n/a | Linux | 资源控制 |
| 内存控制组 | memory cgroup | n/a | Linux | 内存隔离 |
| 信号 | Signal | n/a | Linux | kill / trap |
| SIGKILL | SIGKILL | n/a | Linux | 强制杀进程 |
| pidfd | pidfd | n/a | Linux 5.4+ | 进程 fd |
| OomScore | OomScore | n/a | Linux | /proc/<pid>/oom_score_adj |
| Binder 驱动 | binder.c | n/a | AOSP | Linux 字符设备 |
| LowMemoryKiller | LMK | n/a | Linux | 内存回收 |

---

## 十三、第三方 / AndroidX 库术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| Android 扩展库 | AndroidX | n/a | AndroidX 1.0 | 替代 support library |
| ViewModel | ViewModel | n/a | AndroidX 1.0 | UI 数据 |
| Lifecycle | Lifecycle | n/a | AndroidX 1.0 | 生命周期感知 |
| Room | Room | n/a | AndroidX 1.0 | SQLite ORM |
| DataStore | DataStore | n/a | AndroidX 1.0 | 替代 SharedPreferences |
| WorkManager | WorkManager | n/a | AndroidX 1.0 | 后台任务 |
| Hilt | Hilt | n/a | AndroidX 1.0 | DI |
| Coil | Coil | n/a | Coil 1.0 | 图片加载 |
| Glide | Glide | n/a | Glide 1.0 | 图片加载 |
| LeakCanary | LeakCanary | "泄漏金丝雀" | LeakCanary 1.0 | 内存泄漏检测 |
| EventBus | EventBus | n/a | EventBus 1.0 | 事件总线 |
| RxJava | RxJava | n/a | RxJava 1.0 | 响应式 |
| RxBus | RxBus | n/a | RxJava 1.0 | 事件总线 |
| LocalBroadcastManager | LocalBroadcastManager | "本地广播" | AndroidX 1.0 | **已废弃** |

---

## 十四、关键事件/动作术语（按字母序）

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| ACTION_VIEW | ACTION_VIEW | "查看" | AOSP 1 | 系统广播 |
| ACTION_SEND | ACTION_SEND | "分享" | AOSP 1 | 系统广播 |
| BOOT_COMPLETED | BOOT_COMPLETED | "开机广播" | AOSP 1 | 静态注册高频 |
| LOCKED_BOOT_COMPLETED | LOCKED_BOOT_COMPLETED | n/a | AOSP 7+ | directBootAware |
| MY_PACKAGE_REPLACED | MY_PACKAGE_REPLACED | "App 升级" | AOSP 1 | 自维护机会 |
| MY_PACKAGE_DATA_CLEARED | MY_PACKAGE_DATA_CLEARED | "数据清除" | AOSP 1 | 重新初始化 |
| PACKAGE_REPLACED | PACKAGE_REPLACED | n/a | AOSP 1 | 所有 App 都接收 |
| LOCALE_CHANGED | LOCALE_CHANGED | n/a | AOSP 1 | 语言变化 |
| TIMEZONE_CHANGED | TIMEZONE_CHANGED | n/a | AOSP 1 | 时区变化 |
| TIME_SET | TIME_SET | n/a | AOSP 1 | 时间变化 |
| BATTERY_CHANGED | BATTERY_CHANGED | n/a | AOSP 1 | 电量变化 |
| SCREEN_ON / OFF | SCREEN_ON / OFF | n/a | AOSP 1 | 屏幕开关 |
| USER_PRESENT | USER_PRESENT | n/a | AOSP 1 | 用户解锁 |
| CONNECTIVITY_ACTION | CONNECTIVITY_ACTION | n/a | AOSP 1 | 网络变化 |

---

## 十五、版本 / 平台术语

| 中文 | 英文 | 别名（禁止使用） | 首次定义于 | 备注 |
|------|------|----------------|-----------|------|
| Android | Android | n/a | 2008 | 移动 OS |
| Android 开源项目 | AOSP | n/a | 2008 | Android Open Source Project |
| API 等级 | API Level | n/a | 2008 | 1-37 |
| Android 17 | android-17 | "Android 17" | 2026 | API 37（本系列基线） |
| 平台 | Platform | n/a | AOSP | OS + 系统服务 |
| 厂商 GKI | GKI | n/a | AOSP 11+ | 通用内核 |
| Project Mainline | Mainline | "主线路" | AOSP 10 | 模块化 |
| APEX | APEX | n/a | AOSP 10 | 模块化格式 |
| Treble | Treble | n/a | AOSP 8 | HAL 分离 |

---

## 十六、术语映射速查表（按 AOSP 子系统）

### 16.1 AMS（ActivityManagerService）相关

| 子系统 | 关键类 | 角色 |
|--------|--------|------|
| 进程管理 | ProcessList / ProcessRecord | 进程管理 |
| 任务管理 | RootWindowContainer / Task / TaskFragment | Task 模型 |
| Activity 管理 | ActivityTaskManagerService / ActivityStarter / ActivityStarter | 启动 Activity |
| Service 管理 | ActiveServices / ServiceRecord | 启动 Service |
| Broadcast 管理 | BroadcastQueue / BroadcastRecord | 广播分发 |
| Provider 管理 | ProviderMap / ContentProviderRecord | Provider 调度 |
| 进程优先级 | OomAdjuster | OomScoreAdj |
| ANR 检测 | AnrHelper（AOSP 16+） | 异步 ANR |

### 16.2 PMS（PackageManagerService）相关

| 子系统 | 关键类 | 角色 |
|--------|--------|------|
| 包管理 | PackageManagerService | PMS 主体 |
| 组件解析 | ComponentResolver（AOSP 12+） | 解析 Receiver/Provider |
| 包可见性 | VisibleComponentsRetriever（AOSP 12+） | AOSP 11+ 引入 |

### 16.3 进程端相关

| 子系统 | 关键类 | 角色 |
|--------|--------|------|
| 主线程 | ActivityThread | 进程主入口 |
| 消息循环 | H Handler / Looper | 主线程消息 |
| 资源加载 | LoadedApk | APK 加载 + Application 初始化 |
| Receiver 调度 | ReceiverDispatcher | 动态注册状态机 |
| Service 调度 | ServiceDispatcher | bindService 状态机 |
| ClassLoader | ClassLoader | 类加载 |

---

## 十七、术语禁用列表（强制）

| 禁止使用 | 正确术语 | 理由 |
|---------|---------|------|
| "UI 线程" | 主线程 / main thread | "UI 线程"易与渲染混淆 |
| "分代收集" | 分代回收 | 统一"回收" |
| "粘性" (Broadcast) | 粘性广播 / Sticky Broadcast | "粘性"单独使用歧义 |
| "静态" (启动模式) | standard 模式 | "静态"易误解 |
| "单例" (启动模式) | singleInstance | "单例"易与单例模式混淆 |
| "Provider" (单独使用) | ContentProvider | "Provider"歧义大 |
| "Receiver" (单独使用) | BroadcastReceiver | "Receiver"歧义大 |
| "Service" (单独使用) | Service (组件) | "Service"歧义大 |
| "前端" (中文混用) | 前台 / foreground | "前端"易与 Web 前端混淆 |
| "本地" (LocalBroadcast) | 进程内 | "本地"易误解 |
| "回收" (分代) | 分代回收 | 统一用"回收" |
| "冷启" / "热启" | 冷启动 / 热启动 | 统一完整写法 |
| "分发超时" | 输入事件分发超时 | 统一完整写法 |

---

## 十八、术语更新流程

1. **新术语添加**：
   - 业务方发现新概念 → 提交 PR
   - PR 必须包含：中文名 / 英文名 / 别名（如有）/ 首次定义于 / 备注
   - 3 轮校准（结构 / 硬伤 / 锐度）

2. **术语修改**：
   - 业务方发现歧义 → 提交 issue
   - 必须保持向后兼容（旧术语至少保留 1 个版本）
   - 3 轮校准

3. **术语废弃**：
   - 业务方发现废弃概念 → 标记 deprecated
   - 至少保留 2 个版本
   - 3 轮校准

---

## 附录 · 变更日志

| 日期 | 版本 | 变更 | 影响 |
|------|------|------|------|
| 2026-07-18 | v1.0 | 初始版本，覆盖四大组件 9 篇 × 4 系列 = 36 篇文章的所有术语 | 全部新写 |

---

> **本表维护规则**：任何对术语的修改都必须经过 [PROMPT §8.2](../../PROMPT-技术系列文章写作指南.md) 治理流程。**违反本表的文章必须重写**。

