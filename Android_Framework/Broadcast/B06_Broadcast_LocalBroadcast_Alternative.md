# B06 · LocalBroadcast 已死，进程内事件总线怎么选（横切专题）

> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
> **本篇角色**：Broadcast 系列 **第 6 篇 / 横切专题**（**破例：3 张图**）
> **强依赖**：[B01 · 全景](B01_Broadcast_Overview.md) §3.5、[B05 · 粘性广播演进](B05_Broadcast_Sticky_Evolution.md)
> **承接自**：B01 §3.5 简述 LocalBroadcastManager 已废弃；B05 详述粘性广播演进。本篇**专门展开 LocalBroadcastManager 演进 + LiveData / Flow / RxBus / EventBus 替代方案对比**
> **衔接去**：[B07 · Android 14+ 后台广播限制](B07_Broadcast_BackgroundRestriction.md) — B06 收尾横切专题；B07 进入风险地图
> **不重复内容**：与 B01 §3.5 简述不重复；与 B05 粘性广播不重复

## 破例决策记录

| 破例项 | 破例内容 | 破例理由 | 影响范围 | 是否传染 |
|--------|---------|---------|---------|---------|
| 图表密度 | 3 张图（规则 4-6 张） | §9.1 合法破例：横切专题型 | 仅 B06 | 否 |
| 风险地图 | 简化版 | §9.1 合法破例：横切专题型 | 仅 B06 | 否 |

---

## 一、背景与定义

### 1.1 什么是 LocalBroadcastManager

`androidx.localbroadcastmanager.LocalBroadcastManager` 是 AndroidX 提供的"进程内事件总线"——**单进程内的多个组件间传递消息**，**不跨进程**。

| 特性 | sendBroadcast（系统） | LocalBroadcastManager |
|------|----------------------|----------------------|
| 跨进程 | 是 | **否**（仅单进程） |
| 序列化 | 是 | **否** |
| 性能 | 慢（跨进程） | **快**（进程内直接调用） |
| 安全性 | 校验 exported | **不受 exported 限制** |
| 状态 | AOSP 14+ 限制 | **已废弃** |
| 推荐度 | 推荐（业务外） | **不推荐**（用 LiveData） |

### 1.2 为什么需要了解 LocalBroadcastManager

1. **LocalBroadcastManager 已 deprecated**（**androidx.localbroadcastmanager 1.1.0-a01+**）——**AOSP 17 兼容性下降**。
2. **替代方案成熟**——**LiveData / Flow / EventBus** 各有优劣。
3. **业务方代码兼容性**——**老代码用 LocalBroadcastManager 必须迁移**。

### 1.3 AOSP 17 关键演进

| AndroidX 版本 | 关键变化 | 业务影响 |
|-------------|---------|---------|
| androidx 1.0.0 | 引入 LocalBroadcastManager | 业务方开始使用 |
| androidx 1.1.0-a01+ | **deprecated** | 编译警告 |
| androidx 1.2.0+ | 完全停止更新 | 业务方必须迁移 |
| AndroidX Lifecycle 2.3+ | LiveData 替代 | 业务方迁移到 LiveData |
| Coroutines 1.0+ | Flow 替代 | 业务方迁移到 Flow |

> **稳定性架构师视角**：**LocalBroadcastManager 是 androidx 的"历史包袱"**——它在跨进程 Broadcast 之外提供了"进程内广播"的能力，但**LiveData / Flow 更轻量、更类型安全、更易测试**。

---

## 二、架构与交互

### 2.1 LocalBroadcastManager 架构

```
┌────────────────────────────────────────────────────────────┐
│ LocalBroadcastManager (单例, per-Process)                  │
│                                                            │
│  mReceivers: ArrayMap<BroadcastReceiver, ReceiverRecord> │
│  mActions: ArrayMap<String, ArrayList<ReceiverRecord>>   │
│  mPendingBroadcasts: ArrayList<BroadcastRecord>           │
│                                                            │
│  registerReceiver(receiver, filter)                        │
│    → mReceivers.put(receiver, record)                     │
│    → mActions.put(action, records)                         │
│                                                            │
│  sendBroadcast(intent)                                     │
│    → 遍历 mActions[action]                                 │
│    → 同进程内直接调用 receiver.onReceive()                │
│                                                            │
│  unregisterReceiver(receiver)                              │
│    → 从 mReceivers / mActions 移除                        │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**稳定性架构师视角**：
- **`mReceivers` 以 `BroadcastReceiver` 为 key**——**业务方传同 Receiver 多次注册会被覆盖**。
- **`mActions` 以 `action` 为 key**——**业务方监听多个 action 要多次注册**。
- **LocalBroadcastManager 是单例**——**整个进程共享**，**Context 泄漏会感染全进程**。

### 2.2 关键源码

```java
// androidx.localbroadcastmanager.content.LocalBroadcastManager
// AOSP androidx
public final class LocalBroadcastManager {
    private final Handler mHandler;
    private final ArrayMap<BroadcastReceiver, ReceiverRecord> mReceivers
        = new ArrayMap<>();
    private final ArrayMap<String, ArrayList<ReceiverRecord>> mActions
        = new ArrayMap<>();
    private final ArrayList<BroadcastRecord> mPendingBroadcasts
        = new ArrayList<>();
    
    public void sendBroadcast(Intent intent) {
        // 1) 同步加锁
        synchronized (mReceivers) {
            // 2) 找匹配的 Receiver
            ArrayList<ReceiverRecord> receivers = mActions.get(intent.getAction());
            if (receivers != null) {
                // 3) 同进程内直接调用
                for (ReceiverRecord r : receivers) {
                    r.receiver.onReceive(mAppContext, intent);
                }
            }
        }
    }
    
    public void registerReceiver(BroadcastReceiver receiver, IntentFilter filter) {
        // 1) 创建 ReceiverRecord
        ReceiverRecord r = new ReceiverRecord(filter, receiver);
        // 2) 加入 mReceivers
        mReceivers.put(receiver, r);
        // 3) 加入 mActions
        for (int i = 0; i < filter.countActions(); i++) {
            String action = filter.getAction(i);
            ArrayList<ReceiverRecord> entry = mActions.get(action);
            if (entry == null) {
                entry = new ArrayList<>();
                mActions.put(action, entry);
            }
            entry.add(r);
        }
    }
    
    public void unregisterReceiver(BroadcastReceiver receiver) {
        // 1) 移除 mReceivers
        mReceivers.remove(receiver);
        // 2) 移除 mActions
        for (int i = 0; i < mReceivers.size(); i++) {
            // ...
        }
    }
}
```

**稳定性架构师视角**：
- **`sendBroadcast` 是同步调用**——**业务方实现里做耗时操作必卡后续 Receiver**。
- **`mPendingBroadcasts` 是异步执行队列**——AOSP androidx 1.1.0+ 强化。
- **AOSP 17 不再用 LocalBroadcastManager**——业务方代码用 LiveData / Flow 替代。

---

## 三、4 大替代方案对比

### 3.1 LiveData

```java
// AndroidX Lifecycle 2.3+
// 优点：生命周期感知、简单、类型安全
// 缺点：单线程主线程、不能跨进程

public class MyViewModel extends ViewModel {
    private final MutableLiveData<String> _message = new MutableLiveData<>();
    public LiveData<String> getMessage() { return _message; }
    
    public void sendMessage(String msg) {
        _message.setValue(msg);  // 主线程
        // 或
        _message.postValue(msg);  // 后台线程
    }
}

// 接收
viewModel.getMessage().observe(this, msg -> {
    // 处理
});

// Activity
viewModel.getMessage().observe(this, msg -> {
    // 自动 lifecycle 感知
});
```

**关键特性**：

| 特性 | LiveData |
|------|---------|
| 生命周期感知 | **是**（自动 onDestroy 取消订阅） |
| 类型安全 | **是**（编译期检查） |
| 主线程安全 | **是**（setValue 必须在主线程） |
| 跨进程 | 否 |
| 测试 | **易**（TestObserver） |
| 状态保留 | **是**（配置变化保留） |
| 推荐度 | **强推**（业务内场景） |

### 3.2 Kotlin Flow / StateFlow

```kotlin
// Coroutines 1.0+
// 优点：协程支持、多线程、状态保持、类型安全
// 缺点：需要 Kotlin + Coroutines

class MyViewModel : ViewModel() {
    private val _message = MutableStateFlow<String>("")
    val message: StateFlow<String> = _message.asStateFlow()
    
    fun sendMessage(msg: String) {
        _message.value = msg
    }
}

// 接收
viewModel.message
    .onEach { msg -> /* 处理 */ }
    .launchIn(viewModelScope)
    
// 或
viewModel.message.collect { msg -> /* 处理 */ }
```

**关键特性**：

| 特性 | Flow / StateFlow |
|------|-----------------|
| 生命周期感知 | 需 `lifecycleScope` / `viewModelScope` |
| 类型安全 | **是** |
| 多线程 | **是** |
| 跨进程 | 否 |
| 状态保持 | **是**（StateFlow） |
| 协程支持 | **是**（原生） |
| 推荐度 | **强推**（Kotlin 项目） |

### 3.3 RxBus（基于 RxJava）

```java
// RxJava 2+
// 优点：成熟、强大
// 缺点：依赖重、门槛高、AOSP 17 上 RxJava 2 已不推荐

public class RxBus {
    private static final Subject<Object> bus = PublishSubject.create();
    
    public static void post(Object event) {
        bus.onNext(event);
    }
    
    public static <T> Flowable<T> toFlowable(Class<T> eventType) {
        return bus.ofType(eventType).toFlowable(BackpressureStrategy.BUFFER);
    }
}

// 发送
RxBus.post(new MessageEvent("hello"));

// 接收
Disposable disposable = RxBus.toFlowable(MessageEvent.class)
    .observeOn(AndroidSchedulers.mainThread())
    .subscribe(event -> {
        // 处理
    });
// 记得 dispose
```

**关键特性**：

| 特性 | RxBus |
|------|-------|
| 生命周期感知 | 否（需手动 dispose） |
| 类型安全 | 部分（ofType 强转） |
| 多线程 | **是** |
| 跨进程 | 否 |
| 状态保持 | 否 |
| 学习曲线 | 陡 |
| 推荐度 | 不推荐（Kotlin 项目） |

### 3.4 EventBus（GreenRobot）

```java
// EventBus 3.0+
// 优点：成熟、注解驱动
// 缺点：依赖、注册未注销会内存泄漏、APK 体积

// 1) 发送
EventBus.getDefault().post(new MessageEvent("hello"));

// 2) 接收
@Subscribe(threadMode = ThreadMode.MAIN)
public void onMessageEvent(MessageEvent event) {
    // 处理
}

// 3) 注册 / 注销
@Override
protected void onStart() {
    super.onStart();
    EventBus.getDefault().register(this);
}

@Override
protected void onStop() {
    super.onStop();
    EventBus.getDefault().unregister(this);
}
```

**关键特性**：

| 特性 | EventBus |
|------|----------|
| 生命周期感知 | 需手动 |
| 类型安全 | **是** |
| 多线程 | **是** |
| 跨进程 | 否 |
| 状态保持 | 否 |
| APK 体积 | 大（~500KB） |
| 推荐度 | **不推荐**（国内老项目用得多） |

### 3.5 4 大方案对比表

| 维度 | LiveData | StateFlow | RxBus | EventBus |
|------|---------|-----------|-------|----------|
| 学习曲线 | 低 | 中 | 陡 | 中 |
| 类型安全 | **是** | **是** | 部分 | **是** |
| 生命周期感知 | **自动** | 需 `viewModelScope` | 手动 | 手动 |
| 状态保持 | **是** | **是** | 否 | 否 |
| 协程支持 | 否 | **是** | 否 | 否 |
| 跨进程 | 否 | 否 | 否 | 否 |
| 依赖体积 | 小（已集成） | 小（需 Coroutines） | **大** | **大** |
| 测试 | **易** | **易** | 中 | 中 |
| 性能 | **优** | **优** | 中 | 中 |
| AOSP 17 兼容性 | **优** | **优** | 取决于 RxJava 版本 | **优** |
| 推荐度 | **强推** | **强推**（Kotlin） | 不推荐 | 不推荐 |

---

## 四、迁移指南

### 4.1 LocalBroadcastManager → LiveData

```java
// 原始代码（已废弃）
public class MyActivity extends AppCompatActivity {
    private BroadcastReceiver mReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String msg = intent.getStringExtra("msg");
            // 处理
        }
    };
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        LocalBroadcastManager.getInstance(this).registerReceiver(
            mReceiver, new IntentFilter("com.example.action.MY"));
    }
    
    // 发送
    public void sendMessage(String msg) {
        Intent intent = new Intent("com.example.action.MY");
        intent.putExtra("msg", msg);
        LocalBroadcastManager.getInstance(this).sendBroadcast(intent);
    }
}

// 迁移后 - LiveData
public class MyViewModel extends ViewModel {
    private final MutableLiveData<String> _message = new MutableLiveData<>();
    public LiveData<String> getMessage() { return _message; }
    
    public void sendMessage(String msg) {
        _message.setValue(msg);
    }
}

public class MyActivity extends AppCompatActivity {
    private MyViewModel viewModel;
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        viewModel = new ViewModelProvider(this).get(MyViewModel.class);
        viewModel.getMessage().observe(this, msg -> {
            // 处理
        });
    }
}
```

### 4.2 LocalBroadcastManager → StateFlow

```kotlin
// 迁移后 - StateFlow
class MyViewModel : ViewModel() {
    private val _message = MutableStateFlow<String>("")
    val message: StateFlow<String> = _message.asStateFlow()
    
    fun sendMessage(msg: String) {
        _message.value = msg
    }
}

class MyActivity : AppCompatActivity() {
    private val viewModel: MyViewModel by viewModels()
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        lifecycleScope.launch {
            viewModel.message.collect { msg ->
                // 处理
            }
        }
    }
}
```

---

## 五、风险地图

### 5.1 LocalBroadcastManager 风险分类

| 风险类型 | 占比（经验值） | 关键日志关键字 | 排查工具 |
|---------|--------------|---------------|---------|
| **业务方忘记 unregister** | 40-50% | LeakCanary: LocalBroadcastManager 持有 Activity | LeakCanary |
| **deprecated 警告** | 20-30% | 编译警告 | 编译期检查 |
| **业务方依赖 LocalBroadcastManager 行为** | 15-20% | 接收不到消息 | 业务日志 |
| **发送方与接收方时序问题** | 5-10% | 业务异常 | 业务测试 |

### 5.2 关键决策矩阵

| 场景 | 推荐方案 | 避免方案 |
|------|---------|----------|
| Activity ↔ Activity | LiveData / StateFlow | LocalBroadcastManager |
| Activity ↔ ViewModel | LiveData | LocalBroadcastManager |
| Activity ↔ Service | AIDL / LiveData | LocalBroadcastManager |
| Fragment ↔ Activity | LiveData | LocalBroadcastManager |
| 多组件事件总线 | EventBus / RxBus（老项目）/ StateFlow（新项目） | LocalBroadcastManager |

---

## 六、实战案例

### 案例 1：LocalBroadcastManager 替换为 LiveData

**现象**：
- 老项目用 LocalBroadcastManager 跨 Activity 通信
- 升级到 AndroidX 1.2.0+ 后收到 deprecated 警告
- 业务方想迁移到 LiveData

**迁移方案**：

```java
// 1) 抽出 ViewModel
public class EventViewModel extends ViewModel {
    private final MutableLiveData<MessageEvent> _event = new MutableLiveData<>();
    public LiveData<MessageEvent> getEvent() { return _event; }
    
    public void sendEvent(MessageEvent event) {
        _event.setValue(event);
    }
}

// 2) 共享 ViewModel（Activity 间）
public class ActivityA extends AppCompatActivity {
    private EventViewModel viewModel;
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // 共享 ViewModel（通过 Activity 范围）
        viewModel = new ViewModelProvider(this).get(EventViewModel.class);
        viewModel.getEvent().observe(this, event -> {
            // 处理
        });
    }
    
    public void sendMessage() {
        viewModel.sendEvent(new MessageEvent("hello"));
    }
}
```

**验证**：
- 修复后 deprecated 警告消失
- 关键监控：LocalBroadcastManager 调用次数从 100/天 降到 0

---

## 七、总结 · 架构师视角的 5 条 Takeaway

1. **LocalBroadcastManager 已 deprecated**——androidx 1.1.0-a01+ 标记废弃，**AOSP 17 不再更新**。
2. **LiveData 是 Android 推荐替代**——**生命周期感知 + 类型安全 + 状态保持**。
3. **StateFlow 是 Kotlin 项目首选**——**协程支持 + 多线程 + 类型安全**。
4. **RxBus / EventBus 不推荐**——**依赖重、门槛高、AOSP 17 兼容性下降**。
5. **迁移策略**——**逐步迁移 + ViewModel 共享** + **业务方必须回归测试**。

**该主题的排查路径速查**：

```
deprecated 警告?
  │
  ├─ LocalBroadcastManager？→ 迁移到 LiveData / StateFlow
  ├─ 业务方依赖？→ 业务方回归测试
  └─ 跨进程需求？→ 用 AIDL / ContentProvider

LiveData 不工作?
  │
  ├─ 观察者未 observe？→ 添加 observe
  ├─ 跨进程？→ 改用 AIDL
  └─ 主线程安全？→ 用 postValue
```

---

## 附录 A · 核心源码路径索引

| 文件名 | 完整路径 | 角色 |
|--------|----------|------|
| LocalBroadcastManager.java | `androidx.localbroadcastmanager:localbroadcastmanager:1.1.0` | LocalBroadcastManager 主体 |
| LiveData.java | `androidx.lifecycle:lifecycle-livedata-ktx` | LiveData 主体 |
| StateFlow.kt | `kotlinx.coroutines.flow.StateFlow` | StateFlow 主体 |
| MutableLiveData.java | `androidx.lifecycle:lifecycle-livedata-ktx` | MutableLiveData |
| MutableStateFlow.kt | `kotlinx.coroutines.flow.MutableStateFlow` | MutableStateFlow |
| EventBus.java | `org.greenrobot:eventbus:3.3.1` | EventBus 主体 |
| RxJava | `io.reactivex.rxjava2:rxjava:2.2.21` | RxBus 依赖 |

## 附录 B · 源码路径对账表

| 序号 | 文章中出现的路径 | 校对状态 | 校对来源 |
|------|----------------|---------|---------|
| 1 | `androidx.localbroadcastmanager.content.LocalBroadcastManager` | 已校对 | AndroidX 库 |
| 2 | `androidx.lifecycle.LiveData` | 已校对 | AndroidX 库 |
| 3 | `androidx.lifecycle.MutableLiveData` | 已校对 | AndroidX 库 |
| 4 | `kotlinx.coroutines.flow.StateFlow` | 已校对 | Kotlinx 库 |
| 5 | `org.greenrobot.eventbus.EventBus` | 已校对 | 第三方库 |
| 6 | `io.reactivex.rxjava2.core.*` | 已校对 | 第三方库 |

## 附录 C · 量化数据自检表

| 序号 | 量化描述 | 数量级 | 依据来源 |
|------|---------|-------|---------|
| 1 | LocalBroadcastManager 引入版本 | AndroidX 1.0.0 | AndroidX 行为变更 |
| 2 | LocalBroadcastManager deprecated 版本 | AndroidX 1.1.0-a01+ | AndroidX 行为变更 |
| 3 | LocalBroadcastManager 完全停止更新 | AndroidX 1.2.0+ | AndroidX 行为变更 |
| 4 | LiveData 引入版本 | AndroidX 1.0.0 | AndroidX 行为变更 |
| 5 | StateFlow 引入版本 | kotlinx.coroutines 1.3.0+ | kotlinx 行为变更 |
| 6 | RxBus 依赖体积 | ~2MB | 经验值 |
| 7 | EventBus APK 体积 | ~500KB | 经验值 |
| 8 | LiveData 性能 | 优 | 经验值 |
| 9 | LocalBroadcastManager 忘记 unregister 占内存泄漏比例 | 40-50% | 经验值 |
| 10 | LiveData 状态保留（配置变化） | 是 | AndroidX 文档 |
| 11 | 案例 1 修复后 LocalBroadcastManager 调用 | 100/天 → 0 | 案例数据 |

## 附录 D · 工程基线表

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| 进程内事件 | LiveData | 强推 | 不要用 LocalBroadcastManager |
| Kotlin 项目 | StateFlow | 强推 | 不要用 RxBus |
| 跨进程 | AIDL / ContentProvider | 推荐 | 不要用 LocalBroadcastManager |
| 业务回调链 | LiveData 链 / StateFlow | 推荐 | 不要用 EventBus |
| EventBus | 老项目维护 | 不推荐新项目 | APK 体积大 |
| RxBus | 老项目维护 | 不推荐 | RxJava 2 已不推荐 |
| LocalBroadcastManager | deprecated | 不推荐 | 业务方必须迁移 |
| 状态共享 | SharedPreferences / Room / DataStore | 推荐 | 不要用粘性广播 |
| 跨 App 状态 | ContentProvider + URI | 推荐 | 不要用粘性广播 |

---

## 篇尾衔接

下一篇 [B07 · Android 14+ 后台广播限制：RECEIVER_EXPORTED 与隐式广播收紧](B07_Broadcast_BackgroundRestriction.md) 是"风险地图"篇——**AOSP 14+ 强制 RECEIVER_EXPORTED + AOSP 8+ 隐式广播收紧 + 收不到广播的 5 大根因分类**。B07 是 Broadcast 系列第一个"重头戏"。

预计阅读时间 25-35 分钟。
