# Input Dispatch Timeout ANR 深度解析

## 📋 概述

Input Dispatch Timeout ANR 是 Android 系统中最常见的 ANR 类型之一。当应用的主线程无法在规定时间内（通常为 5 秒）处理输入事件（如触摸、按键）时，系统会触发 ANR。这种 ANR 直接影响用户体验，因为用户无法与应用进行交互。

---

## 一、Input Dispatch Timeout ANR 的基本概念

### 1.1 什么是 Input Dispatch Timeout ANR

Input Dispatch Timeout ANR 是指当应用的主线程无法在规定时间内（通常为 5 秒）处理输入事件时，系统判定应用无响应而触发的 ANR。

### 1.2 Input Dispatch Timeout ANR 的特点

- **超时时间最短**：Input ANR 的超时时间通常为 5 秒（比 Broadcast 和 Service ANR 更短）
- **直接影响用户体验**：用户无法与应用交互，界面卡顿
- **最常见类型**：Input ANR 是 Android 系统中最常见的 ANR 类型
- **触发频率高**：用户每次交互都可能触发，如果主线程阻塞

---

## 二、Input Dispatch Timeout ANR 的触发条件

### 2.1 超时时间规则

Input Dispatch Timeout ANR 的超时时间取决于应用的前台/后台状态和输入事件类型：

| 应用状态 | 超时时间 | 说明 |
|---------|---------|------|
| 前台应用 | 5 秒 | 应用有可见的 Activity |
| 后台应用 | 通常不触发 | 后台应用一般不接收输入事件 |

**源码位置**：
- `InputDispatcher.cpp` 中的 `DEFAULT_INPUT_DISPATCHING_TIMEOUT_NANOS = 5 * 1000 * 1000 * 1000L`（5秒）
- `ActivityManagerService.java` 中的 `INPUT_DISPATCH_TIMEOUT = 5 * 1000`（5秒）

### 2.2 触发条件

Input Dispatch Timeout ANR 在以下情况下会被触发：

1. **主线程无法处理输入事件**
   - 主线程被阻塞（如死锁、等待锁、IO 阻塞）
   - 主线程执行耗时操作（如复杂计算、文件 IO、网络请求）

2. **输入事件分发超时**
   - InputDispatcher 发送输入事件给应用
   - 应用的主线程在 5 秒内没有处理完该事件
   - InputDispatcher 检测到超时，触发 ANR

3. **窗口无响应**
   - 应用的窗口（Window）无法响应输入事件
   - 窗口的 InputChannel 没有及时处理事件

---

## 三、Input Dispatch Timeout ANR 的检测机制

### 3.1 Input 事件分发流程

#### 3.1.1 InputDispatcher 机制

Android 系统通过 `InputDispatcher` 来管理输入事件的分发：

```cpp
// frameworks/native/services/inputflinger/InputDispatcher.cpp

class InputDispatcher {
    // 默认超时时间：5秒
    static constexpr nsecs_t DEFAULT_INPUT_DISPATCHING_TIMEOUT_NANOS = 5 * 1000 * 1000 * 1000L;
    
    // 分发输入事件
    void dispatchOnce() {
        // ... 获取输入事件
        
        // 分发事件
        dispatchEventLocked(currentTime, entry);
    }
    
    // 分发事件到目标窗口
    void dispatchEventLocked(nsecs_t currentTime, EventEntry* eventEntry) {
        // ... 查找目标窗口
        
        // 发送事件到应用
        dispatchEventToConnectionLocked(currentTime, eventEntry, connection);
    }
    
    // 发送事件到连接
    void dispatchEventToConnectionLocked(nsecs_t currentTime, 
            EventEntry* eventEntry, 
            sp<Connection> connection) {
        // ... 发送事件
        
        // 设置超时监控
        connection->inputTarget.waitDispatchTime = currentTime + 
            DEFAULT_INPUT_DISPATCHING_TIMEOUT_NANOS;
        
        // 发送超时消息
        onDispatchCycleStartedLocked(currentTime, connection);
    }
    
    // 检查超时
    void dispatchOnceInnerLocked(nsecs_t* nextWakeupTime) {
        // ... 处理事件
        
        // 检查是否有超时的事件
        nsecs_t currentTime = now();
        timeoutExpired = currentTime >= connection->inputTarget.waitDispatchTime;
        
        if (timeoutExpired) {
            // 触发 ANR
            onAnrLocked(connection);
        }
    }
    
    // ANR 处理
    void onAnrLocked(const sp<Connection>& connection) {
        // 构建 ANR 消息
        String8 reason = String8::format(
            "Input dispatching timed out (%s, %s)",
            connection->getWindowName().string(),
            connection->getStatusBarrier().string());
        
        // 通知 ActivityManagerService
        mPolicy->notifyANR(connection->inputWindowHandle, reason);
    }
}
```

#### 3.1.2 应用层接收事件

应用通过 `InputChannel` 接收输入事件：

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java

public final class ViewRootImpl {
    // 输入事件处理
    void dispatchInputEvent(InputEvent event) {
        // 发送到主线程的 MessageQueue
        mHandler.dispatchInputEvent(event);
    }
    
    // 主线程处理输入事件
    void doProcessInputEvents() {
        // 处理输入事件
        processInputEvent(event);
    }
    
    // 处理输入事件
    void processInputEvent(InputEvent event) {
        // 分发到 View 树
        mView.dispatchTouchEvent(event);
    }
}
```

### 3.2 Framework 层超时检测

#### 3.2.1 ActivityManagerService 检测

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

public class ActivityManagerService {
    // Input ANR 超时时间：5秒
    static final int INPUT_DISPATCH_TIMEOUT = 5 * 1000;
    
    // 处理 Input ANR
    void inputDispatchingTimedOut(ProcessRecord proc, 
            boolean aboveSystem, 
            String reason) {
        // 检查是否真的超时
        if (proc.inputDispatchingTimeout == 0) {
            return;
        }
        
        // 检查进程是否还在运行
        if (proc.thread == null) {
            return;
        }
        
        // 构建 ANR 消息
        String anrMessage = "Input dispatching timed out";
        if (reason != null) {
            anrMessage += " (" + reason + ")";
        }
        
        // 触发 ANR
        mAnrHelper.appNotResponding(proc, anrMessage);
    }
}
```

### 3.3 关键源码位置

- **InputDispatcher.cpp**: `frameworks/native/services/inputflinger/InputDispatcher.cpp`
  - `dispatchOnce()`: 输入事件分发主循环
  - `dispatchEventLocked()`: 分发事件到目标窗口
  - `onAnrLocked()`: ANR 检测和处理

- **ViewRootImpl.java**: `frameworks/base/core/java/android/view/ViewRootImpl.java`
  - `dispatchInputEvent()`: 分发输入事件到主线程
  - `doProcessInputEvents()`: 主线程处理输入事件

- **ActivityManagerService.java**: `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`
  - `INPUT_DISPATCH_TIMEOUT`: Input ANR 超时时间常量（5秒）
  - `inputDispatchingTimedOut()`: Input ANR 处理

---

## 四、Input Dispatch Timeout ANR 的常见原因

### 4.1 主线程阻塞

#### 4.1.1 死锁

```java
// ❌ 错误示例：主线程死锁
public class MainActivity extends AppCompatActivity {
    private static final Object lock1 = new Object();
    private static final Object lock2 = new Object();
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 主线程获取 lock1
        synchronized (lock1) {
            // 启动后台线程
            new Thread(new Runnable() {
                @Override
                public void run() {
                    // 后台线程获取 lock2
                    synchronized (lock2) {
                        // 尝试获取 lock1（等待主线程释放）
                        synchronized (lock1) {
                            // 死锁：主线程等待 lock2，后台线程等待 lock1
                        }
                    }
                }
            }).start();
            
            // 主线程尝试获取 lock2（等待后台线程释放）
            synchronized (lock2) {
                // 死锁发生
            }
        }
    }
}
```

#### 4.1.2 等待锁

```java
// ❌ 错误示例：主线程等待锁
public class MainActivity extends AppCompatActivity {
    private final Object lock = new Object();
    private boolean isReady = false;
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 主线程等待锁
        synchronized (lock) {
            while (!isReady) {
                try {
                    lock.wait(); // 如果 isReady 永远不变成 true，主线程永远阻塞
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
            }
        }
    }
}
```

### 4.2 主线程耗时操作

#### 4.2.1 文件 IO 操作

```java
// ❌ 错误示例：主线程执行文件 IO
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 主线程执行文件 IO
        File file = new File(getFilesDir(), "large_data.txt");
        try {
            FileInputStream fis = new FileInputStream(file);
            byte[] buffer = new byte[10 * 1024 * 1024]; // 10MB
            fis.read(buffer); // 可能阻塞主线程
            fis.close();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}
```

#### 4.2.2 网络请求

```java
// ❌ 错误示例：主线程执行同步网络请求
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 主线程执行同步网络请求
        try {
            URL url = new URL("https://api.example.com/data");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(10000);
            conn.connect(); // 可能阻塞主线程
            // ... 读取响应
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}
```

#### 4.2.3 复杂计算

```java
// ❌ 错误示例：主线程执行复杂计算
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 主线程执行复杂计算
        long result = 0;
        for (int i = 0; i < 1000000000; i++) {
            result += i * i; // 耗时计算，阻塞主线程
        }
    }
}
```

#### 4.2.4 数据库操作

```java
// ❌ 错误示例：主线程执行复杂数据库操作
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 主线程执行复杂数据库查询
        SQLiteDatabase db = DatabaseHelper.getInstance(this).getReadableDatabase();
        Cursor cursor = db.rawQuery("SELECT * FROM large_table WHERE ...", null);
        // 遍历大量数据
        while (cursor.moveToNext()) {
            // 处理数据，可能很耗时
        }
        cursor.close();
    }
}
```

### 4.3 View 绘制阻塞

#### 4.3.1 复杂布局

```java
// ❌ 错误示例：复杂布局导致绘制阻塞
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 如果布局非常复杂（嵌套层级深、View 数量多），
        // 可能导致 measure、layout、draw 过程耗时过长
    }
}
```

#### 4.3.2 自定义 View 绘制耗时

```java
// ❌ 错误示例：自定义 View 绘制耗时
public class MyCustomView extends View {
    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        
        // 在 onDraw 中执行耗时操作
        for (int i = 0; i < 100000; i++) {
            // 复杂绘制操作
            canvas.drawCircle(i, i, 10, paint);
        }
    }
}
```

### 4.4 系统资源压力

#### 4.4.1 CPU 负载高

- 系统 CPU 负载过高，主线程无法及时获得 CPU 时间片
- 多个进程竞争 CPU 资源

#### 4.4.2 IO 阻塞

- 系统 IO 压力大，主线程等待 IO 完成
- 存储设备性能差，IO 操作耗时

#### 4.4.3 内存压力

- 系统内存不足，频繁触发 GC
- GC 暂停导致主线程无法处理输入事件

---

## 五、Input Dispatch Timeout ANR 的分析方法

### 5.1 日志分析

#### 5.1.1 ANR 日志关键信息

```
ANR in com.example.app
PID: 12345
Reason: Input dispatching timed out (Window{1234567 com.example.app/com.example.app.MainActivity} is not responding. Waited 5001ms for MotionEvent)
Load: 2.5 / 1.8 / 1.2
```

**关键字段**：
- **Reason**: 显示触发的窗口和等待时间
- **PID**: 发生 ANR 的进程 ID
- **Load**: 系统负载（1分钟/5分钟/15分钟平均值）
- **Waited 5001ms**: 等待时间（超过 5 秒）

#### 5.1.2 logcat 日志

```
E/ActivityManager: ANR in com.example.app
E/ActivityManager: PID: 12345
E/ActivityManager: Reason: Input dispatching timed out (Window{1234567 com.example.app/com.example.app.MainActivity} is not responding. Waited 5001ms for MotionEvent)
E/ActivityManager: Load: 2.5 / 1.8 / 1.2
E/ActivityManager: CPU usage from 0ms to 5000ms later:
E/ActivityManager:   90% 12345/com.example.app: 80% user + 10% kernel
E/ActivityManager:   15% 12345/com.example.app: 0% user + 15% kernel (iowait)
```

**关键信息**：
- **iowait**: 如果 iowait 高，说明主线程被 IO 阻塞
- **user/kernel**: 查看 CPU 使用情况，判断是计算密集型还是 IO 密集型

### 5.2 traces.txt 分析

#### 5.2.1 查看主线程堆栈

```bash
# 从 traces.txt 中查找主线程（main）
"main" prio=5 tid=1 Blocked
  | group="main" sCount=1 dsCount=0 flags=1 obj=0x12c00000 self=0x7f8a4c00
  | sysTid=12345 nice=0 cgrp=default sched=0/0 handle=0x7f8a4c00
  | state=S schedstat=( 5000000000 500000000 1000 ) utm=500 stm=50 core=0 HZ=100
  | stack=0x7f8a4c00-0x7f8a4c00
  | held mutexes=
  at java.io.FileInputStream.read(FileInputStream.java:123)
  at com.example.app.MainActivity.onCreate(MainActivity.java:45)
  at android.app.Activity.performCreate(Activity.java:7148)
  at android.app.Activity.performCreate(Activity.java:7139)
  at android.app.Instrumentation.callActivityOnCreate(Instrumentation.java:1271)
  at android.app.ActivityThread.performLaunchActivity(ActivityThread.java:2931)
  at android.app.ActivityThread.handleLaunchActivity(ActivityThread.java:3086)
  at android.app.servertransaction.LaunchActivityItem.execute(LaunchActivityItem.java:78)
  at android.app.servertransaction.TransactionExecutor.executeCallbacks(TransactionExecutor.java:108)
  at android.app.servertransaction.TransactionExecutor.execute(TransactionExecutor.java:68)
  at android.app.ActivityThread$H.handleMessage(ActivityThread.java:1816)
  at android.os.Handler.dispatchMessage(Handler.java:106)
  at android.os.Looper.loop(Looper.java:193)
  at android.app.ActivityThread.main(ActivityThread.java:6718)
```

**关键信息**：
- **state=S**: 线程处于 Sleeping 状态（可能被 IO 阻塞）
- **at java.io.FileInputStream.read()**: 显示阻塞的具体操作（文件 IO）
- **at com.example.app.MainActivity.onCreate()**: 显示 ANR 发生在哪个方法

#### 5.2.2 查找等待锁的线程

```bash
# 查找等待锁的主线程
"main" prio=5 tid=1 Blocked
  | state=S schedstat=( ... ) utm=100 stm=0 core=0 HZ=100
  | stack=0x7f8a4c00-0x7f8a4c00
  | held mutexes=
  at java.lang.Object.wait(Object.java:422)
  - waiting on <0x12345678> (a java.lang.Object)
  at com.example.app.MainActivity.onCreate(MainActivity.java:50)
```

**关键信息**：
- **waiting on <0x12345678>**: 显示等待的锁对象
- **at java.lang.Object.wait()**: 显示线程在等待锁

#### 5.2.3 查找 IO 阻塞

```bash
# 查找 IO 阻塞的主线程
"main" prio=5 tid=1 Blocked
  | state=D schedstat=( ... ) utm=100 stm=0 core=0 HZ=100
  | stack=0x7f8a4c00-0x7f8a4c00
  | held mutexes=
  at java.io.FileInputStream.read(FileInputStream.java:123)
  - locked <0x12345678> (a java.io.FileInputStream)
```

**关键信息**：
- **state=D**: 线程处于 Uninterruptible Sleep 状态（IO 阻塞）
- **at java.io.FileInputStream.read()**: 显示 IO 操作

### 5.3 systrace/perfetto 分析

#### 5.3.1 查看输入事件处理时间线

在 systrace 中查找：
- **InputDispatcher**: 输入事件分发时间
- **Choreographer**: UI 绘制时间
- **主线程阻塞**: 主线程在某个操作上的耗时
- **IO 等待**: IO 操作等待时间

#### 5.3.2 关键指标

- **输入事件处理时间**: 应该 < 5 秒
- **主线程阻塞时间**: 查看主线程在哪个操作上阻塞
- **IO 等待时间**: 查看是否有 IO 阻塞
- **绘制时间**: 查看 View 绘制是否耗时

---

## 六、Input Dispatch Timeout ANR 的预防措施

### 6.1 避免主线程阻塞

#### 6.1.1 使用后台线程处理耗时操作

```java
// ✅ 正确示例：使用后台线程处理文件 IO
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 在后台线程处理文件 IO
        new Thread(new Runnable() {
            @Override
            public void run() {
                File file = new File(getFilesDir(), "large_data.txt");
                try {
                    FileInputStream fis = new FileInputStream(file);
                    byte[] buffer = new byte[10 * 1024 * 1024];
                    fis.read(buffer);
                    fis.close();
                    
                    // 更新 UI 需要在主线程
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            // 更新 UI
                        }
                    });
                } catch (IOException e) {
                    e.printStackTrace();
                }
            }
        }).start();
    }
}
```

#### 6.1.2 使用 AsyncTask（已废弃，建议使用其他方式）

```java
// ⚠️ 注意：AsyncTask 已废弃，建议使用其他方式
// ✅ 正确示例：使用 ExecutorService
public class MainActivity extends AppCompatActivity {
    private ExecutorService executorService;
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        executorService = Executors.newCachedThreadPool();
        
        executorService.execute(new Runnable() {
            @Override
            public void run() {
                // 耗时操作
                String result = performHeavyWork();
                
                // 更新 UI
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        // 更新 UI
                    }
                });
            }
        });
    }
}
```

### 6.2 使用异步 API

#### 6.2.1 使用 Retrofit/OkHttp 异步网络请求

```java
// ✅ 正确示例：使用 Retrofit 异步网络请求
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 异步网络请求
        ApiService apiService = RetrofitClient.getApiService();
        Call<ResponseData> call = apiService.getData();
        call.enqueue(new Callback<ResponseData>() {
            @Override
            public void onResponse(Call<ResponseData> call, Response<ResponseData> response) {
                // 在主线程回调，更新 UI
                updateUI(response.body());
            }
            
            @Override
            public void onFailure(Call<ResponseData> call, Throwable t) {
                // 处理错误
            }
        });
    }
}
```

#### 6.2.2 使用 Room 异步数据库操作

```java
// ✅ 正确示例：使用 Room 异步数据库操作
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 异步数据库查询
        AppDatabase db = Room.databaseBuilder(getApplicationContext(),
                AppDatabase.class, "database-name").build();
        
        db.userDao().getAllUsers()
            .observeOn(AndroidSchedulers.mainThread())
            .subscribe(new Observer<List<User>>() {
                @Override
                public void onSubscribe(Disposable d) {
                }
                
                @Override
                public void onNext(List<User> users) {
                    // 在主线程更新 UI
                    updateUI(users);
                }
                
                @Override
                public void onError(Throwable e) {
                    // 处理错误
                }
                
                @Override
                public void onComplete() {
                }
            });
    }
}
```

### 6.3 优化 View 绘制

#### 6.3.1 减少布局层级

```xml
<!-- ❌ 错误示例：嵌套层级过深 -->
<LinearLayout>
    <LinearLayout>
        <LinearLayout>
            <LinearLayout>
                <TextView />
            </LinearLayout>
        </LinearLayout>
    </LinearLayout>
</LinearLayout>

<!-- ✅ 正确示例：使用 ConstraintLayout 减少嵌套 -->
<androidx.constraintlayout.widget.ConstraintLayout>
    <TextView
        app:layout_constraintTop_toTopOf="parent"
        app:layout_constraintStart_toStartOf="parent" />
</androidx.constraintlayout.widget.ConstraintLayout>
```

#### 6.3.2 优化自定义 View 绘制

```java
// ✅ 正确示例：优化自定义 View 绘制
public class MyCustomView extends View {
    private Bitmap cachedBitmap; // 缓存绘制结果
    
    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        
        // 使用缓存，避免重复绘制
        if (cachedBitmap == null) {
            cachedBitmap = Bitmap.createBitmap(getWidth(), getHeight(), Bitmap.Config.ARGB_8888);
            Canvas cacheCanvas = new Canvas(cachedBitmap);
            // 在缓存 Canvas 上绘制
            drawContent(cacheCanvas);
        }
        
        // 直接绘制缓存
        canvas.drawBitmap(cachedBitmap, 0, 0, null);
    }
    
    private void drawContent(Canvas canvas) {
        // 复杂绘制操作
    }
}
```

### 6.4 性能优化建议

#### 6.4.1 减少主线程工作量

- **快速响应**: 主线程应该快速响应输入事件
- **避免耗时操作**: 不要在主线程执行 IO、网络、数据库等耗时操作
- **异步处理**: 耗时操作放到后台线程处理

#### 6.4.2 优化应用启动

- **延迟初始化**: 非关键资源延迟初始化
- **减少启动时间**: 减少 Application.onCreate() 和 Activity.onCreate() 的执行时间

---

## 七、Input Dispatch Timeout ANR 的典型案例

### 7.1 案例一：主线程文件 IO 阻塞

**问题描述**：
应用在 Activity.onCreate() 中读取大文件，导致 Input ANR。

**原因分析**：
- 主线程执行文件 IO
- 文件较大，读取时间超过 5 秒

**解决方案**：
```java
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 在后台线程读取文件
        new Thread(new Runnable() {
            @Override
            public void run() {
                readLargeFile();
            }
        }).start();
    }
}
```

### 7.2 案例二：主线程网络请求阻塞

**问题描述**：
应用在按钮点击事件中执行同步网络请求，导致 Input ANR。

**原因分析**：
- 主线程执行同步网络请求
- 网络延迟较高，请求时间超过 5 秒

**解决方案**：
```java
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        Button button = findViewById(R.id.button);
        button.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                // 使用异步网络请求
                ApiService apiService = RetrofitClient.getApiService();
                Call<ResponseData> call = apiService.getData();
                call.enqueue(new Callback<ResponseData>() {
                    @Override
                    public void onResponse(Call<ResponseData> call, Response<ResponseData> response) {
                        updateUI(response.body());
                    }
                    
                    @Override
                    public void onFailure(Call<ResponseData> call, Throwable t) {
                        // 处理错误
                    }
                });
            }
        });
    }
}
```

### 7.3 案例三：系统 IO 压力导致 ANR

**问题描述**：
系统 IO 压力大，主线程等待 IO 完成，导致 Input ANR。

**原因分析**：
- 系统 IO 压力大（IO PSI 高）
- 主线程等待 IO 完成，无法处理输入事件

**解决方案**：
- 优化应用 IO 操作，减少 IO 频率和大小
- 使用异步 IO，避免阻塞主线程
- 监控系统 IO 压力，在 IO 压力大时减少 IO 操作

---

## 八、总结

### 8.1 关键要点

1. **超时时间**：前台应用 5 秒
2. **执行线程**：输入事件在主线程处理
3. **常见原因**：主线程阻塞、主线程耗时操作、系统资源压力
4. **预防措施**：使用后台线程、异步 API、优化 View 绘制

### 8.2 最佳实践

- ✅ 快速响应输入事件，耗时操作放到后台
- ✅ 使用后台线程或异步 API 处理 IO、网络、数据库操作
- ✅ 优化 View 绘制，减少布局层级和绘制复杂度
- ✅ 避免在主线程执行耗时操作
- ✅ 监控系统资源压力（CPU、IO、内存）

---

## 🔗 相关资源

- **源码位置**：
  - `InputDispatcher.cpp`: `frameworks/native/services/inputflinger/InputDispatcher.cpp`
  - `ViewRootImpl.java`: `frameworks/base/core/java/android/view/ViewRootImpl.java`
  - `ActivityManagerService.java`: `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`

- **官方文档**：
  - [Android Input 事件处理官方文档](https://developer.android.com/guide/topics/ui/ui-events)
  - [Android ANR 调试指南](https://developer.android.com/topic/performance/vitals/anr)

---

**提示**：分析 Input Dispatch Timeout ANR 时，重点关注 traces.txt 中的主线程堆栈，查找阻塞的具体操作（IO、网络、锁等）。同时关注系统资源压力（CPU、IO、内存 PSI），判断是否是系统级问题。
