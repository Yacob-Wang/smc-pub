# 04-内存泄漏典型案例与排查 SOP

> **本篇定位**:系列第 4 篇(案例库 + SOP)。读完后能从现象一步步排到根因,覆盖 Java / Native / 系统级 三大类典型内存问题。
>
> **强依赖**:
> - [01-hprof 原理与文件格式](01-hprof原理与文件格式.md) §4 ROOT 记录
> - [02-hprof 解析工具链](02-hprof解析工具链.md) §3 LeakCanary + §4 MAT
> - [03-perfetto_hprof 详解](03-perfetto_hprof详解.md) §3 Native Heap Sampling
>
> **承接自**:前三篇的原理和工具,本篇把它们映射到真实问题
>
> **不重复内容**:
> - hprof 格式与工具 → 见 [01](01-hprof原理与文件格式.md) / [02](02-hprof解析工具链.md)
> - perfetto_hprof 内部实现 → 见 [03](03-perfetto_hprof详解.md)
> - 体系化监控 → 见 [05](05-实战：内存监控体系搭建.md)
>
> **基线**:AOSP `android-14.0.0_r1` + LeakCanary `2.14+` + 主流 app 经验
> **风格**:源码密度 ~15%,每个案例 4 段式(现象→分析→根因→修复)+ SOP 决策树
>
> **目录位置**:`Android_Framework/Hprof/`
> **上一篇**:[03-perfetto_hprof 详解](03-perfetto_hprof详解.md)
> **下一篇**:[05-实战：内存监控体系搭建](05-实战：内存监控体系搭建.md)

---

## 目录

- [1. 内存稳定性问题全景图](#1-内存稳定性问题全景图)
  - [1.1 四大类问题:OOM / Leak / Pressure / Native](#11-四大类问题oom--leak--pressure--native)
  - [1.2 案例覆盖矩阵](#12-案例覆盖矩阵)
- [2. Activity / Fragment 泄漏:5 大经典场景](#2-activity--fragment-泄漏5-大经典场景)
  - [2.1 场景 1:静态变量持有 Activity](#21-场景-1静态变量持有-activity)
  - [2.2 场景 2:Handler / Runnable 持有 Activity](#22-场景-2handler--runnable-持有-activity)
  - [2.3 场景 3:非静态内部类持有 Activity](#23-场景-3非静态内部类持有-activity)
  - [2.4 场景 4:WebView / TextureView 持有 Activity](#24-场景-4webview--textureview-持有-activity)
  - [2.5 场景 5:第三方 SDK 持有 Activity](#25-场景-5第三方-sdk-持有-activity)
- [3. Handler / Thread / Static 泄漏](#3-handler--thread--static-泄漏)
  - [3.1 Handler 消息未清空](#31-handler-消息未清空)
  - [3.2 Thread / TimerTask 未关闭](#32-thread--timertask-未关闭)
  - [3.3 Static 集合 / 缓存未清理](#33-static-集合--缓存未清理)
- [4. 系统级泄漏:注册未反注册 / Cursor / Receiver](#4-系统级泄漏注册未反注册--cursor--receiver)
  - [4.1 BroadcastReceiver / EventBus 未反注册](#41-broadcastreceiver--eventbus-未反注册)
  - [4.2 Cursor / FileDescriptor 未关闭](#42-cursor--filedescriptor-未关闭)
  - [4.3 SensorManager / LocationManager 未注销](#43-sensormanager--locationmanager-未注销)
- [5. Native 内存问题](#5-native-内存问题)
  - [5.1 Bitmap 像素泄漏(Java 引用 + Native 内存)](#51-bitmap-像素泄漏java-引用--native-内存)
  - [5.2 DirectByteBuffer 泄漏](#52-directbytebuffer-泄漏)
  - [5.3 JNI 全局引用未释放](#53-jni-全局引用未释放)
  - [5.4 so 库持续增长](#54-so-库持续增长)
- [6. 内存泄漏排查 SOP](#6-内存泄漏排查-sop)
  - [6.1 阶段 1:确认问题(线上报障 / dumpsys / meminfo)](#61-阶段-1确认问题线上报障--dumpsys--meminfo)
  - [6.2 阶段 2:触发 dump(Debug / 命令 / LeakCanary)](#62-阶段-2触发-dumpdebug--命令--leakcanary)
  - [6.3 阶段 3:工具分析(LeakCanary / MAT / Android Studio)](#63-阶段-3工具分析leakcanary--mat--android-studio)
  - [6.4 阶段 4:定位根因](#64-阶段-4定位根因)
  - [6.5 阶段 5:修复 + 验证](#65-阶段-5修复--验证)
- [7. 实战:3 个线上真实案例还原](#7-实战3-个线上真实案例还原)
  - [7.1 案例 A:电商首页瀑布流 OOM](#71-案例-a电商首页瀑布流-oom)
  - [7.2 案例 B:工具类页面 Native 持续增长](#72-案例-b工具类页面-native-持续增长)
  - [7.3 案例 C:Fragment 切换引发的连环泄漏](#73-案例-cfragment-切换引发的连环泄漏)
- [8. 总结:架构师视角的 5 条 Takeaway](#8-总结架构师视角的-5-条-takeaway)
- [附录 A:核心源码路径索引](#附录-a核心源码路径索引)
- [附录 B:LeakCanary 配置模板(`hprof_configs/leakcanary_config.gradle`)](#附录-bleakcanary-配置模板hprof_configsleakcanary_configgradle)
- [附录 C:量化数据自检表](#附录-c量化数据自检表)
- [附录 D:工程基线表](#附录-d工程基线表)
- [篇尾衔接](#篇尾衔接)

---

## 1. 内存稳定性问题全景图

### 1.1 四大类问题:OOM / Leak / Pressure / Native

```
                        内存稳定性问题
                              │
        ┌──────────┬───────────┼───────────┬──────────┐
        ↓          ↓           ↓           ↓          ↓
      OOM       Leak       Pressure     Native     其他
   (内存溢出)  (内存泄漏)  (内存压力)   (Native 增长)
        │          │           │           │
        │          │           │           └─ perfetto_heapprofd
        │          │           │              perfetto_hprof
        │          │           │              (见 03)
        │          │           │
        │          │           └─ onTrimMemory
        │          │              LMKD
        │          │
        │          └─ hprof(LeakCanary/MAT)
        │             (见 01-02)
        │
        └─ dumpsys meminfo
           (第一现场)
```

| 类型 | 现象 | 关键工具 |
|------|------|---------|
| **OOM** | `OutOfMemoryError` 异常 + 进程被杀 | dumpsys meminfo + hprof |
| **Leak** | 内存持续增长不释放 | LeakCanary + hprof |
| **Pressure** | 频繁 onTrimMemory / 后台被杀 | onTrimMemory + LMKD log |
| **Native** | native heap / graphics / .so 增长 | perfetto_heapprofd |

### 1.2 案例覆盖矩阵

本篇覆盖 13 个典型案例,按问题类型分布:

| 问题类型 | 案例数 | 章节 |
|---------|-------|------|
| **Activity/Fragment 泄漏** | 5 | §2 |
| **Handler/Thread/Static 泄漏** | 3 | §3 |
| **系统级泄漏** | 3 | §4 |
| **Native 内存问题** | 4 | §5 |
| **合计** | **13** + 1 个 SOP + 3 个真实案例 | §6-§7 |

---

## 2. Activity / Fragment 泄漏:5 大经典场景

### 2.1 场景 1:静态变量持有 Activity

**典型代码**:

```kotlin
object UserManager {
    var currentActivity: Activity? = null  // ❌ 静态持有 Activity
}

class ProfileActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        UserManager.currentActivity = this  // ❌
    }
}
```

**LeakCanary 报告**:

```
ProfileActivity has leaked:
  ↑ retained 45.2 MB
  ↑ static field UserManager.currentActivity
  ↑ UserManager (singleton)
  ↑ Activity = ProfileActivity ← 泄漏对象
```

**根因**:
- `UserManager` 是 object 单例,生命周期 = 进程
- 静态字段持有 Activity → Activity 永生 → 整个 View 树 + Bitmap + Fragment 全泄漏

**修复方案**:

```kotlin
// 方案 1:用 WeakReference
object UserManager {
    var currentActivity: WeakReference<Activity>? = null
}

// 方案 2:用 ApplicationContext(推荐)
object UserManager {
    lateinit var appContext: Context  // 初始化时 setApplicationContext()
}

// 方案 3:用 LiveData / Flow(架构组件方式)
class ProfileActivity : AppCompatActivity() {
    private val viewModel: ProfileViewModel by viewModels()
    // viewModel 持有 Activity 的方式由 ViewModelProvider 保证不泄漏
}
```

> **关键判断**:**真的需要 Activity 引用吗?** 90% 的场景改成 `ApplicationContext` 或 `WeakReference` 即可。

---

### 2.2 场景 2:Handler / Runnable 持有 Activity

**典型代码**:

```kotlin
class MainActivity : AppCompatActivity() {
    private val handler = Handler(Looper.getMainLooper())
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handler.postDelayed({
            // 5 秒后执行,如果期间 Activity 销毁 → 泄漏
            updateUI()
        }, 5000)
    }
}
```

**LeakCanary 报告**:

```
MainActivity has leaked:
  ↑ retained 12.8 MB
  ↑ MessageQueue (main)
  ↑ Message (callback = Runnable)
  ↑ Runnable (anonymous inner class) ← 持有外部类引用
  ↑ MainActivity ← 泄漏对象
```

**根因**:
- `Handler.postDelayed` 把 Runnable 放进 MessageQueue
- Runnable 是匿名内部类 → **持有外部 Activity 引用**
- 如果 5s 内 Activity 销毁 → Runnable 还在 MessageQueue → Activity 泄漏
- 即使 Runnable 执行完,Handler 仍是 Activity 字段,Activity 仍被 MessageQueue 持有

**修复方案**:

```kotlin
class MainActivity : AppCompatActivity() {
    private val handler = Handler(Looper.getMainLooper())
    private val updateRunnable = Runnable { updateUI() }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handler.postDelayed(updateRunnable, 5000)
    }
    
    // ✅ 关键修复
    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
```

> **关键操作**:Activity onDestroy 时 **必须** `removeCallbacksAndMessages(null)`。这是最容易被忽略的泄漏源之一。

---

### 2.3 场景 3:非静态内部类持有 Activity

**典型代码**:

```kotlin
class DownloadActivity : AppCompatActivity() {
    // ❌ 非静态内部类
    private val downloadTask = object : AsyncTask<Void, Void, Boolean>() {
        override fun doInBackground(vararg params: Void?): Boolean {
            // 耗时下载
            return true
        }
    }
    
    fun startDownload() {
        downloadTask.execute()
    }
}
```

**根因**:
- Kotlin 中 `object : AsyncTask` 默认是 **非静态内部类**
- 内部类隐式持有外部类引用 → Activity 泄漏
- AsyncTask 还被 `mExecutor` / `mHandler` 等系统类持有 → **泄漏路径更长**

**修复方案**:

```kotlin
// 方案 1:改静态内部类 + WeakReference(经典模式)
class DownloadActivity : AppCompatActivity() {
    private static class DownloadTask(activity: DownloadActivity) : AsyncTask<Void, Void, Boolean>() {
        private val activityRef = WeakReference(activity)  // 弱引用
        
        override fun doInBackground(vararg params: Void?): Boolean {
            // 不能直接用 activity.XXX,用 activityRef.get()
            return true
        }
    }
}

// 方案 2:用 Kotlin Coroutine(推荐,2024+ 项目标配)
class DownloadActivity : AppCompatActivity() {
    private val scope = CoroutineScope(Dispatchers.Main + Job())
    
    fun startDownload() {
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                downloadFile()
            }
            // 自动绑定 Lifecycle,Activity 销毁时取消
        }
    }
    
    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
```

> **关键判断**:**新项目直接上 Coroutine**。AsyncTask 已废弃(API 30),HandlerThread / RxJava 也逐渐被协程替代。

---

### 2.4 场景 4:WebView / TextureView 持有 Activity

**典型代码**:

```kotlin
class WebViewActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webView = WebView(this)
        setContentView(webView)
        webView.loadUrl("https://example.com")
    }
}
```

**LeakCanary 报告**:

```
WebViewActivity has leaked:
  ↑ retained 8.7 MB (主要在 native graphics)
  ↑ ViewRootImpl (mContext = WebViewActivity)
  ↑ WebView
  ↑ WebViewClassic / WebViewChromium (内部)
  ↑ ...持有 native graphics buffer
```

**根因**:
- WebView 内部有 Bug:Activity 销毁时 **未释放 native 图形缓冲区**
- 这是 [Android 长期未修复的已知 Bug](https://issuetracker.google.com/issues/36974740)
- 即使 Activity onDestroy → WebView native 部分仍存活 → **8-20MB 泄漏**

**修复方案**:

```kotlin
// 方案 1:独立进程跑 WebView(最稳)
<activity
    android:name=".WebViewActivity"
    android:process=":webview" />  <!-- 独立进程,泄漏不影响主进程 -->

// 方案 2:Activity onDestroy 时手动释放
class WebViewActivity : AppCompatActivity() {
    override fun onDestroy() {
        webView.stopLoading()
        webView.removeAllViews()
        webView.destroy()  // ✅ 释放 native
        (webView.parent as? ViewGroup)?.removeView(webView)
        super.onDestroy()
    }
}

// 方案 3:用系统 WebView 之外的方案(推荐)
//  - TWA(Trusted Web Activity)
//  - Chrome Custom Tabs
//  - 跳转系统浏览器
```

> **关键判断**:**如果 WebView 必须长时间打开 → 用独立进程**。这是 Android 工程师圈子里的"祖传方案"。

---

### 2.5 场景 5:第三方 SDK 持有 Activity

**典型场景**:

```kotlin
class SdkInit {
    fun init(activity: Activity, config: Config) {
        SomeThirdPartySdk.init(activity, config)  // ❌ SDK 内部把 Activity 存到 static
    }
}
```

**LeakCanary 报告**:

```
HomeActivity has leaked:
  ↑ retained 23.4 MB
  ↑ static field com.example.thirdparty.SdkManager.sActivity
  ↑ SdkManager (third party)
  ↑ HomeActivity ← 泄漏对象
```

**根因**:
- 第三方 SDK 内部有 Bug,static 持有 Activity
- 你的代码完全正确,但 SDK 不释放

**修复方案**:

```kotlin
// 方案 1:用 ApplicationContext 初始化
fun init(context: Context, config: Config) {  // ✅
    SomeThirdPartySdk.init(context.applicationContext, config)
}

// 方案 2:SDK 反注册(SDK 提供反注册 API)
override fun onDestroy() {
    SomeThirdPartySdk.unregister(this)
    super.onDestroy()
}

// 方案 3:包裹 try-catch + 反馈 SDK 提供方
//  - 临时方案:catch OOM,记录 SDK 名称
//  - 长期:推 SDK 升级 / 换 SDK

// 方案 4:独立进程(终极方案)
<activity android:process=":thirdparty" />
```

> **关键判断**:**无法修改第三方代码 → 用独立进程隔离**。这是工程上的"兜底方案"。

---

## 3. Handler / Thread / Static 泄漏

### 3.1 Handler 消息未清空

参见 §2.2,这里补充几个变种:

```kotlin
// 变种 1:View.postDelayed (View 也持有 Activity)
view.postDelayed({ ... }, 5000)

// 变种 2:rxjava subscribe 未取消(等同 Handler)
Disposable disposable = Observable.timer(5, TimeUnit.SECONDS)
    .subscribe { ... }
// ❌ 没在 onDestroy 调 disposable.dispose()

// 变种 3:WorkManager(系统调度,但持有 Context)
WorkManager.getInstance(context).enqueue(work)
// ⚠️ work 完成后会自动释放,但如果 work 长时间运行,Context 仍被持有
```

**统一修复模式**:

```kotlin
override fun onDestroy() {
    handler.removeCallbacksAndMessages(null)
    view.removeCallbacks(null)
    disposable?.dispose()
    workManager.cancelAllWorkByTag("xxx")
    super.onDestroy()
}
```

### 3.2 Thread / TimerTask 未关闭

**典型代码**:

```kotlin
class MonitorService {
    private val monitorThread = Thread {
        while (true) {  // ❌ 死循环,Activity 销毁也无法退出
            monitorSomething()
            Thread.sleep(1000)
        }
    }
    
    fun start() {
        monitorThread.start()
    }
    
    // ❌ 没提供 stop 方法
}
```

**修复方案**:

```kotlin
class MonitorService {
    @Volatile
    private var running = false
    private val monitorThread = Thread {
        while (running) {  // ✅ 检查标志位
            monitorSomething()
            Thread.sleep(1000)
        }
    }
    
    fun start() {
        running = true
        monitorThread.start()
    }
    
    fun stop() {  // ✅ 提供 stop 方法
        running = false
        monitorThread.interrupt()  // 打断 sleep
    }
}
```

**更现代的方式**:用 `ExecutorService` + `shutdown()`:

```kotlin
class MonitorService {
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    
    fun start() {
        executor.submit {
            while (!Thread.currentThread().isInterrupted) {
                monitorSomething()
                Thread.sleep(1000)
            }
        }
    }
    
    fun stop() {
        executor.shutdownNow()  // ✅ 标准 API
    }
}
```

### 3.3 Static 集合 / 缓存未清理

**典型代码**:

```kotlin
object ImageCache {
    private val cache = HashMap<String, Bitmap>()  // ❌ 永生 + 无上限
    private val listeners = mutableListOf<Listener>()  // ❌ 持有外部对象
    
    fun put(key: String, bitmap: Bitmap) {
        cache[key] = bitmap  // 持续涨
    }
    
    fun addListener(listener: Listener) {
        listeners.add(listener)  // listener 可能是 Activity!
    }
}
```

**修复方案**:

```kotlin
// 方案 1:用 LruCache(有上限 + 自动 LRU)
object ImageCache {
    private val cache = object : LruCache<String, Bitmap>(maxSize = 50 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap): Int = value.byteCount / 1024
    }
}

// 方案 2:用 WeakHashMap(自动 GC)
object ListenerManager {
    private val listeners = WeakHashMap<Listener, Boolean>()  // 自动清理
    
    fun addListener(listener: Listener) {
        listeners[listener] = true
    }
}

// 方案 3:用 Glide / Coil(图片缓存最佳实践)
//  - 自动管理内存 + 磁盘
//  - 支持 lifecycle(Activity 销毁自动取消)
//  - 内置 BitmapPool
```

> **关键判断**:**业务级缓存首选 Glide/Coil**;少量配置可用 `LruCache`;**不要自己写 static HashMap 缓存大对象**。

---

## 4. 系统级泄漏:注册未反注册 / Cursor / Receiver

### 4.1 BroadcastReceiver / EventBus 未反注册

**典型代码**:

```kotlin
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        EventBus.getDefault().register(this)  // ❌ 未反注册
        
        // 注册广播
        registerReceiver(networkReceiver, IntentFilter("NETWORK_CHANGED"))
    }
    // ❌ 没在 onDestroy 反注册
}
```

**根因**:
- EventBus 内部用 static Map 存储订阅者
- BroadcastReceiver 注册到 ActivityManager,Activity 销毁时未取消 → 持有 Activity

**修复方案**:

```kotlin
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        EventBus.getDefault().register(this)
        registerReceiver(networkReceiver, IntentFilter("NETWORK_CHANGED"))
    }
    
    override fun onDestroy() {
        EventBus.getDefault().unregister(this)  // ✅
        unregisterReceiver(networkReceiver)  // ✅
        super.onDestroy()
    }
}
```

**更安全的方式**:用 AndroidX 的 `LifecycleObserver`:

```kotlin
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onCreate(owner: LifecycleOwner) {
                EventBus.getDefault().register(this@MainActivity)
            }
            override fun onDestroy(owner: LifecycleOwner) {
                EventBus.getDefault().unregister(this@MainActivity)  // ✅ 自动
            }
        })
    }
}
```

### 4.2 Cursor / FileDescriptor 未关闭

**典型代码**:

```kotlin
fun queryUsers(): List<User> {
    val cursor = contentResolver.query(USER_URI, null, null, null, null)  // ❌
    return cursor.use {  // ✅ use 自动关闭
        cursor.toList()
    }
}

// ❌ 不 use 的版本 → cursor 泄漏
fun queryUsersBad(): List<User> {
    val cursor = contentResolver.query(USER_URI, null, null, null, null)
    val list = mutableListOf<User>()
    while (cursor.moveToNext()) {
        list.add(parseUser(cursor))
    }
    return list
    // ❌ cursor 没关,ContentProvider 端连接保持,占 native fd + Java heap
}
```

**统一修复模式**:

```kotlin
// ✅ Kotlin:用 .use {}
cursor?.use { ... }

// ✅ Java:用 try-with-resources
try (Cursor cursor = contentResolver.query(...)) {
    ...
}

// ✅ FileInputStream 同理
try (FileInputStream fis = new FileInputStream(file)) {
    ...
}
```

### 4.3 SensorManager / LocationManager 未注销

**典型代码**:

```kotlin
class SensorActivity : AppCompatActivity(), SensorEventListener {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        sensorManager.registerListener(this, sensor, SensorManager.SENSOR_DELAY_NORMAL)
        locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, this)
    }
    // ❌ 没在 onPause/onDestroy 反注册
}
```

**修复方案**:

```kotlin
class SensorActivity : AppCompatActivity(), SensorEventListener {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
    }
    
    override fun onResume() {
        super.onResume()
        sensorManager.registerListener(this, sensor, SensorManager.SENSOR_DELAY_NORMAL)
        locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, this)
    }
    
    override fun onPause() {
        sensorManager.unregisterListener(this)  // ✅
        locationManager.removeUpdates(this)     // ✅
        super.onPause()
    }
}
```

> **关键原则**:**配对使用 API** —— register / unregister,open / close,acquire / release。

---

## 5. Native 内存问题

### 5.1 Bitmap 像素泄漏(Java 引用 + Native 内存)

**特点**(引用 01 §7.2):
- Java 端:Bitmap 对象本身只有 16 字节引用
- Native 端:**实际像素数据(1920×1080 RGBA_F16 = 8MB)**
- hprof 中看 `byte[]` 大小可推测

**典型代码**:

```kotlin
object BitmapCache {
    val cache = HashMap<String, Bitmap>()
    
    fun loadBitmap(url: String): Bitmap {
        if (cache.containsKey(url)) return cache[url]!!
        
        val bitmap = Glide.with(context).asBitmap().load(url).submit().get()
        cache[url] = bitmap  // ❌ 缓存原图
        return bitmap
    }
}
```

**泄漏特征**:
- Java heap 涨幅小(<1%)
- Native heap 涨幅大(>30%)
- graphics 内存持续增长
- hprof 中有大 `byte[]`(像素数据)

**修复方案**:

```kotlin
// ✅ 强制缩放 + LRU + 弱引用
object BitmapCache {
    private val cache = object : LruCache<String, Bitmap>(maxSize = 50 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap): Int = value.byteCount / 1024
    }
    
    fun loadBitmap(context: Context, url: String): Bitmap {
        return Glide.with(context)
            .asBitmap()
            .load(url)
            .override(256, 256)  // ✅ 强制缩放
            .submit(256, 256)
            .get()
    }
}
```

> **关键判断**:**Java heap 没涨但 native 涨 → 99% 是 Bitmap 泄漏**。

### 5.2 DirectByteBuffer 泄漏

**典型代码**:

```kotlin
class NetworkBuffer {
    private val buffer = ByteBuffer.allocateDirect(1024 * 1024)  // ❌ 1MB direct memory
    
    fun release() {
        // ❌ 没显式释放,只能等 GC + Cleaner
    }
}
```

**修复方案**:

```kotlin
class NetworkBuffer : AutoCloseable {
    private val buffer = ByteBuffer.allocateDirect(1024 * 1024)
    
    override fun close() {
        // ✅ 显式释放
        if (buffer.isDirect) {
            DirectByteBufferHelper.clean(buffer)  // JDK 内部 API
        }
    }
}

// 使用
NetworkBuffer().use { buffer ->
    // 用完自动 close
}
```

**监控方式**:

```bash
# dumpsys meminfo 看 DirectByteBuffer
adb shell dumpsys meminfo com.example.app | grep -i "Direct"
# 输出: Direct:    12345 KB

# perfetto_heapprofd 看 native malloc 热点
# 配置 sampling_interval_bytes: 1024
# 找 ByteBuffer.allocateDirect 调用栈
```

### 5.3 JNI 全局引用未释放

**典型代码(JNI 侧)**:

```cpp
// ❌ 全局引用泄漏
static jobject g_callback_object = nullptr;

JNIEXPORT void JNICALL
Java_com_example_Native_setCallback(JNIEnv *env, jobject obj) {
    if (g_callback_object != nullptr) {
        env->DeleteGlobalRef(g_callback_object);  // 释放旧的
    }
    g_callback_object = env->NewGlobalRef(obj);  // 创建新的
}

// ❌ 释放时没清空 g_callback_object
JNIEXPORT void JNICALL
Java_com_example_Native_clearCallback(JNIEnv *env, jobject obj) {
    env->DeleteGlobalRef(g_callback_object);
    g_callback_object = nullptr;  // ✅ 必须置空
}
```

**监控方式**:

```bash
# dumpsys meminfo 看 "Other native" 持续增长 → 怀疑 JNI 泄漏
adb shell dumpsys meminfo com.example.app

# perfetto_heapprofd 配置采样,找 NewGlobalRef 调用栈
```

### 5.4 so 库持续增长

**典型场景**:
- 动态加载多个 so 库(`System.loadLibrary`)
- so 库代码段(text)占用几十 MB,加载多次就累加
- 常见:某些 SDK 每次 init 加载一次 so

**监控方式**:

```bash
# dumpsys meminfo 看 ".so mmap"
adb shell dumpsys meminfo com.example.app | grep -A 3 ".so"
# 输出: .so mmap:   87.4 MB

# 监控 so 加载
adb logcat | grep "loadLibrary\|dlopen"
```

**修复方案**:
- 单例化 so 加载(只加载一次)
- 用 `System.loadLibrary("xxx", ClassLoader)` 检查是否重复加载
- 升级 SDK / 联系 SDK 提供方

---

## 6. 内存泄漏排查 SOP

### 6.1 阶段 1:确认问题(线上报障 / dumpsys / meminfo)

```
线上报障:用户反馈"OOM / 卡顿 / 重启"
    ↓
[1] 看 dumpsys meminfo(分类占比)
    adb shell dumpsys meminfo com.example.app
    ↓
[2] 看 logcat(异常堆栈)
    adb logcat | grep -E "OutOfMemoryError|OOM"
    ↓
[3] 看 perfetto_heapprofd trace(增长曲线,如果是 Native)
    ↓
[确认问题类型]:
    ├── Java Heap 高 → Java 泄漏
    ├── Native 高 → Native 泄漏
    └── Graphics 高 → Bitmap 泄漏
```

### 6.2 阶段 2:触发 dump(Debug / 命令 / LeakCanary)

| 触发方式 | 命令 | 适用 |
|---------|------|------|
| **Debug 包** | `Debug.dumpHprofData(path)` | debug 自测 |
| **命令行** | `adb shell am dumpheap <pkg> /sdcard/dump.hprof` | 通用 |
| **kill 信号** | `adb shell kill -10 <pid>` | debuggable=true |
| **LeakCanary** | 自动(Activity onDestroy 后) | 开发 + 灰度 |
| **perfetto_heapprofd** | 配置触发 | 线上持续 |

### 6.3 阶段 3:工具分析(LeakCanary / MAT / Android Studio)

**自动化流水线**(配合 `scripts/leakcanary_report_parse.py`):

```bash
# 1. dump hprof
adb shell am dumpheap com.example.app /sdcard/dump.hprof
adb pull /sdcard/dump.hprof ./

# 2. hprof-conv 转换
hprof-conv dump.hprof dump_standard.hprof

# 3. LeakCanary 报告(如果有)→ 自动解析
python3 scripts/leakcanary_report_parse.py reports/

# 4. MAT 打开 dump_standard.hprof
#    用 OQL 查询大对象 / dominator tree

# 5. Android Studio 快速浏览
#    File → Open → dump.hprof(自动转换)
```

### 6.4 阶段 4:定位根因

**LeakCanary 自动报告**(90% 场景):
- 直接看引用链:从 GC Root 到泄漏对象
- retained size > 1MB 才值得修
- 静态字段 / 集合 / Handler 是最常见源头

**MAT 深度分析**(10% 复杂场景):
- Dominator Tree:谁真正占用大块内存
- OQL 查询:`SELECT * FROM instanceof byte[] WHERE sizeof > 1048576`
- Path to GC Roots:排除弱引用后的引用链

**perfetto_heapprofd**:
- 看 native malloc 热点调用栈
- 时间分布:哪段时间涨最快

### 6.5 阶段 5:修复 + 验证

**修复清单**:

```
[ ] 1. 静态变量 → WeakReference / ApplicationContext
[ ] 2. Handler → onDestroy removeCallbacksAndMessages
[ ] 3. 内部类 → 静态内部类 + WeakReference
[ ] 4. WebView → 独立进程 / onDestroy destroy()
[ ] 5. 第三方 SDK → ApplicationContext 初始化 / 独立进程
[ ] 6. Cursor / Stream → use{} / try-with-resources
[ ] 7. 注册 API → register/unregister 配对
[ ] 8. Bitmap → override(256,256) + LruCache
[ ] 9. JNI → DeleteGlobalRef + 置空
[ ] 10. DirectByteBuffer → close() + Cleaner
```

**验证**:
- LeakCanary 反复触发 3 次稳定
- perfetto_heapprofd 持续 1 小时无增长
- dumpsys meminfo 30 分钟稳定

---

## 7. 实战:3 个线上真实案例还原

### 7.1 案例 A:电商首页瀑布流 OOM

**现象**:
- 用户持续刷首页 30 分钟
- 内存从 200MB 涨到 800MB
- 偶现 OOM 弹窗,被系统杀掉

**排查过程**:

```
[1] dumpsys meminfo
    Java Heap:    180 MB (22%)
    Native Heap:  90 MB (11%)
    Graphics:     420 MB (52%)  ← Graphics 异常高!
    .so mmap:     50 MB (6%)
    Stack:        4 MB
    Code:        30 MB

[2] 抓 hprof(用户操作复现 + dump)
[3] LeakCanary 报告:
    HomeActivity has leaked:
      ↑ retained 234.5 MB
      ↑ static field ProductListAdapter.sBitmapPool
      ↑ ProductListAdapter (单例)
      ↑ BitmapPool.LruCache
      ↑ Bitmap entries (87 张)
```

**根因**:
- ProductListAdapter 单例,静态 LruCache 缓存商品大图
- 每张图原始 4096x4096(原图),每个 16-67MB
- 87 张图累计 234MB,永不释放

**修复**:

```kotlin
// 修复 1:改用 Glide(自动管理 + 缩略图)
Glide.with(view)
    .load(url)
    .override(256, 256)  // 缩略图
    .into(view)

// 修复 2:去掉 static 单例
class ProductListAdapter : RecyclerView.Adapter<...>() {
    private val bitmapCache = LruCache<String, Bitmap>(maxSize = 10 * 1024 * 1024)
    // ✅ 非 static,Activity 销毁时 GC
}
```

**验证**:
- 反复刷 1 小时,内存稳定 200-250MB
- LeakCanary 无 HomeActivity 泄漏

---

### 7.2 案例 B:工具类页面 Native 持续增长

**现象**:
- 工具类页面打开就涨内存,关闭不释放
- Java Heap 几乎不变(0-5%)
- Native Heap 持续涨(50MB → 200MB → 500MB)

**排查过程**:

```
[1] dumpsys meminfo
    Java Heap:    50 MB (10%)    ← 不高
    Native Heap:  320 MB (62%)   ← 异常高!
    Graphics:     100 MB (19%)

[2] 抓 perfetto_heapprofd trace(native sampling)
[3] trace_processor SQL 查询:
    SELECT 
      callsite.name,
      SUM(size) AS total_bytes
    FROM heap_profile_allocations
    WHERE callsite.name LIKE '%Bitmap%'
    GROUP BY callsite.name
    ORDER BY total_bytes DESC LIMIT 10;
    
    输出:
    BitmapFactory.decodeStream    180 MB  ← 热点!
    WebView.<init>                 60 MB
    Other                         80 MB

[4] 进一步看调用栈:
    BitmapFactory.decodeStream
      ↑ ImageUtil.loadFullImage  ← 自己写的工具类
        ↑ ToolActivity.onResume
```

**根因**:
- 工具类页面有个 "查看大图" 功能
- 用 `BitmapFactory.decodeStream` 加载**全分辨率原图**(不缩放)
- 4000x4000 原图 = 64MB,加载 3 次 = 192MB
- Activity 关闭后,工具类静态持有 Bitmap,永不释放

**修复**:

```kotlin
// ❌ 错误:加载原图
fun loadFullImage(context: Context, url: String): Bitmap {
    return Glide.with(context).asBitmap().load(url).submit().get()
}

// ✅ 正确:先获取尺寸,按需加载
fun loadFullImage(context: Context, url: String): Bitmap {
    // 1. 先读尺寸
    val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeStream(url.openStream(), null, opts)
    
    // 2. 算采样率
    val sampleSize = calculateInSampleSize(opts, 1080, 1920)
    
    // 3. 按采样率加载
    val loadOpts = BitmapFactory.Options().apply { inSampleSize = sampleSize }
    return BitmapFactory.decodeStream(url.openStream(), null, loadOpts)
    // ✅ 4000x4000 采样到 1080x1920 → 8MB
}
```

**验证**:
- 工具类页面反复打开关闭,Native Heap 稳定 50-80MB
- perfetto_heapprofd 无 decodeStream 热点

---

### 7.3 案例 C:Fragment 切换引发的连环泄漏

**现象**:
- 切换 Tab Fragment 50 次后 OOM
- 每个 Fragment 都报泄漏

**排查过程**:

```
[1] LeakCanary 报告:
    HomeFragment has leaked:
      ↑ retained 8.7 MB
      ↑ ViewModelStore (Fragment 持有)
      ↑ HomeViewModel
      ↑ HomeViewModel.mContext = HomeFragment  ← 关键!
      
    DetailFragment has leaked:
      ↑ retained 6.2 MB
      ↑ ...类似的 ViewModel → Context 引用

[2] 检查 ViewModel 代码:
class HomeViewModel : ViewModel() {
    lateinit var context: Context  // ❌ ViewModel 不应该持 Context
    
    fun init(context: Context) {
        this.context = context
    }
}
```

**根因**:
- ViewModel 设计上**生命周期长于 Fragment**(`onDestroy` 不会清空 ViewModel)
- ViewModel 持有 Context → ViewModel 跨 Fragment 复用 → Context 跨 Fragment 复用 → Fragment 泄漏
- 多次切换 → 多个泄漏的 Fragment + 多个泄漏的 Context

**修复**:

```kotlin
// ❌ 错误:ViewModel 持有 Context
class HomeViewModel : ViewModel() {
    lateinit var context: Context
}

// ✅ 正确:用 AndroidViewModel(自带 ApplicationContext)
class HomeViewModel(app: Application) : AndroidViewModel(app) {
    // ✅ getApplication() 拿到 ApplicationContext,不会泄漏
}

// ✅ 正确:完全不持 Context,用 SavedStateHandle
class HomeViewModel(savedState: SavedStateHandle) : ViewModel() {
    // 数据通过 SavedStateHandle 传递,不持 Context
}

// ✅ 正确:用 Hilt / Koin 注入
@HiltViewModel
class HomeViewModel @Inject constructor(
    @ApplicationContext private val context: Context  // ✅ ApplicationContext
) : ViewModel()
```

**验证**:
- Fragment 切换 100 次,无泄漏
- LeakCanary 无 HomeFragment / DetailFragment 泄漏

---

## 8. 总结:架构师视角的 5 条 Takeaway

### Takeaway 1:静态引用是泄漏的"头号杀手"
- 90% 的 Activity 泄漏源头是 **static field 持有 Activity**
- 修复原则:**能不持有就不持有,必须持有就 WeakReference / ApplicationContext**

### Takeaway 2:配对使用 API 是基本功
- register/unregister、open/close、acquire/release
- 用 LifecycleObserver 自动化反注册(Lifecycle 默认机制)

### Takeaway 3:Native 内存看 perfetto_heapprofd
- Java heap 不涨但 Native 涨 → 用 perfetto_heapprofd 看调用栈归因
- 这是传统 hprof 做不到的,perfetto_hprof 的**核心价值**

### Takeaway 4:第三方 SDK + WebView 用独立进程
- 改不了 SDK 代码?独立进程隔离
- WebView 是 Android 已知 Bug,独立进程是祖传方案

### Takeaway 5:SOP 比"猜"重要
- 5 阶段 SOP:确认问题 → 触发 dump → 工具分析 → 定位根因 → 修复验证
- 每阶段都有明确工具,避免"瞎试"

---

## 附录 A:核心源码路径索引

| 路径 | 作用 |
|------|------|
| `frameworks/base/core/java/android/os/AsyncTask.java` | AsyncTask 实现(已废弃) |
| `frameworks/base/core/java/android/os/Handler.java` | Handler 实现 |
| `frameworks/base/core/java/android/content/ContentResolver.java` | Cursor 分配 |
| `frameworks/base/core/java/android/location/LocationManager.java` | Location 注销 |
| `frameworks/base/core/java/android/hardware/SensorManager.java` | Sensor 注销 |
| `frameworks/base/core/java/android/webkit/WebView.java` | WebView 资源释放 |
| `art/runtime/native/java_lang_ref_FinalizerReference.cc` | DirectByteBuffer Cleaner |
| `libcore/luni/src/main/java/java/nio/DirectByteBuffer.java` | DirectByteBuffer 实现 |

## 附录 B:LeakCanary 配置模板(`hprof_configs/leakcanary_config.gradle`)

完整模板见 `hprof_configs/leakcanary_config.gradle`,包含:
- Debug 包默认配置
- 内部灰度包配置
- Release 排除规则
- 误报过滤(excludedActivities / excludedClasses)

## 附录 C:量化数据自检表

| 问题类型 | 典型 retained size | 影响 | 修复优先级 |
|---------|------------------|------|----------|
| Activity 静态引用 | 10-50MB | 中-高 | **P0** |
| Handler 未清空 | 5-20MB | 中 | P1 |
| 非静态内部类 | 5-15MB | 中 | P1 |
| WebView 泄漏 | 8-20MB | 中 | P1 |
| 第三方 SDK | 10-50MB | 高 | **P0** |
| Static 集合 | 50-500MB | **极高** | **P0** |
| Bitmap 泄漏 | 50-300MB | 高 | **P0** |
| DirectByteBuffer | 10-100MB | 中 | P1 |
| JNI 全局引用 | 5-30MB | 中 | P1 |

## 附录 D:工程基线表

| 项 | 版本/路径 |
|----|---------|
| LeakCanary | `2.14+` |
| Eclipse MAT | `1.12.0+` |
| Glide | `4.16+` |
| Coroutine | `1.7+` |
| Lifecycle | `2.7+` |

## 篇尾衔接

**下一篇**:[05-实战：内存监控体系搭建](05-实战：内存监控体系搭建.md) 是系列收官篇——把单次排查能力升级为体系化监控:**LeakCanary 接入实战、线上 OOM 监控 + hprof 上传、内存归因 dashboard、与 perfetto_hprof / statsd 协同**。

**强依赖本篇的章节**:
- 05 §3 会基于本篇 §2-§5 的案例设计监控规则
- 05 §4 会用本篇 §6 的 SOP 搭建自动化流水线

**本篇不覆盖**:
- 体系化监控架构 → [05](05-实战：内存监控体系搭建.md)
- 工具链深入 → [02](02-hprof解析工具链.md)
- perfetto_hprof 配置 → [03](03-perfetto_hprof详解.md)