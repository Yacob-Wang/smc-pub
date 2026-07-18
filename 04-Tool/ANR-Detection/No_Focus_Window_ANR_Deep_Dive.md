# No Focus Window ANR 深度解析

## 📋 概述

No Focus Window ANR 是 Android 系统中一种特殊的 ANR 类型。当系统无法找到可以接收输入事件的焦点窗口（Focus Window）时，会触发这种 ANR。这种情况通常发生在应用窗口管理异常、窗口焦点丢失或系统窗口状态异常时。

---

## 一、No Focus Window ANR 的基本概念

### 1.1 什么是 No Focus Window ANR

No Focus Window ANR 是指当系统无法找到可以接收输入事件的焦点窗口时，系统判定应用无响应而触发的 ANR。与普通的 Input Dispatch Timeout ANR 不同，No Focus Window ANR 不是因为主线程阻塞，而是因为窗口焦点管理异常。

### 1.2 No Focus Window ANR 的特点

- **窗口焦点问题**：不是主线程阻塞，而是窗口焦点管理异常
- **系统级问题**：通常涉及系统窗口管理和焦点分发机制
- **相对少见**：相比 Input Dispatch Timeout ANR，No Focus Window ANR 相对少见
- **影响范围广**：可能影响整个系统的输入事件处理

---

## 二、No Focus Window ANR 的触发条件

### 2.1 窗口焦点机制

#### 2.1.1 窗口焦点概念

在 Android 系统中，只有获得焦点的窗口（Focus Window）才能接收输入事件。系统通过 `WindowManagerService` 来管理窗口焦点：

- **焦点窗口**：当前可以接收输入事件的窗口
- **焦点分发**：系统将输入事件分发给焦点窗口
- **焦点切换**：当用户切换应用或窗口时，焦点会切换

#### 2.1.2 焦点窗口查找流程

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java

public class WindowManagerService {
    // 查找焦点窗口
    WindowState findFocusedWindow() {
        // 从窗口栈顶开始查找
        for (int i = mWindows.size() - 1; i >= 0; i--) {
            WindowState win = mWindows.get(i);
            
            // 检查窗口是否可以获得焦点
            if (win.canReceiveKeys()) {
                return win;
            }
        }
        
        // 没有找到焦点窗口
        return null;
    }
    
    // 检查窗口是否可以接收输入事件
    boolean canReceiveKeys(WindowState win) {
        // 窗口必须可见
        if (!win.isVisible()) {
            return false;
        }
        
        // 窗口必须可以接收输入
        if (!win.canReceiveInput()) {
            return false;
        }
        
        // 窗口必须处于活动状态
        if (!win.isActive()) {
            return false;
        }
        
        return true;
    }
}
```

### 2.2 触发条件

No Focus Window ANR 在以下情况下会被触发：

1. **没有焦点窗口**
   - 系统无法找到可以接收输入事件的窗口
   - 所有窗口都无法获得焦点（不可见、不可接收输入等）

2. **窗口焦点丢失**
   - 应用窗口意外失去焦点
   - 窗口状态异常，无法重新获得焦点

3. **系统窗口状态异常**
   - 系统窗口（如 StatusBar、NavigationBar）状态异常
   - 窗口管理服务异常

4. **窗口创建失败**
   - 应用尝试创建窗口但失败
   - 窗口创建后无法获得焦点

---

## 三、No Focus Window ANR 的检测机制

### 3.1 InputDispatcher 检测机制

#### 3.1.1 焦点窗口查找

```cpp
// frameworks/native/services/inputflinger/InputDispatcher.cpp

class InputDispatcher {
    // 查找焦点窗口
    sp<InputWindowHandle> findFocusedWindow() {
        // 从窗口列表查找焦点窗口
        for (size_t i = 0; i < mWindowHandles.size(); i++) {
            sp<InputWindowHandle> windowHandle = mWindowHandles[i];
            
            // 检查窗口是否可以接收输入
            if (windowHandle->getInfo()->hasFocus) {
                return windowHandle;
            }
        }
        
        // 没有找到焦点窗口
        return nullptr;
    }
    
    // 分发输入事件
    void dispatchOnce() {
        // 查找焦点窗口
        sp<InputWindowHandle> focusedWindow = findFocusedWindow();
        
        if (focusedWindow == nullptr) {
            // 没有焦点窗口，触发 ANR
            onNoFocusWindowAnr();
            return;
        }
        
        // 分发事件到焦点窗口
        dispatchEventToWindow(focusedWindow, event);
    }
    
    // No Focus Window ANR 处理
    void onNoFocusWindowAnr() {
        // 构建 ANR 消息
        String8 reason = String8::format(
            "No focus window, but keys are being sent to it.  Make sure the input "
            "method is started and connected, and that the current activity has "
            "a window with input focus.");
        
        // 通知 ActivityManagerService
        mPolicy->notifyANR(nullptr, reason);
    }
}
```

#### 3.1.2 超时检测

```cpp
// InputDispatcher.cpp

void InputDispatcher::dispatchOnceInnerLocked(nsecs_t* nextWakeupTime) {
    // 检查是否有输入事件等待处理
    if (mPendingEvent == nullptr) {
        return;
    }
    
    // 查找焦点窗口
    sp<InputWindowHandle> focusedWindow = findFocusedWindow();
    
    if (focusedWindow == nullptr) {
        // 没有焦点窗口，检查超时
        nsecs_t currentTime = now();
        if (mNoFocusWindowTimeoutTime == 0) {
            // 第一次检测到没有焦点窗口，设置超时时间
            mNoFocusWindowTimeoutTime = currentTime + 
                DEFAULT_INPUT_DISPATCHING_TIMEOUT_NANOS;
        } else if (currentTime >= mNoFocusWindowTimeoutTime) {
            // 超时，触发 ANR
            onNoFocusWindowAnr();
            mNoFocusWindowTimeoutTime = 0;
        }
        return;
    }
    
    // 有焦点窗口，重置超时时间
    mNoFocusWindowTimeoutTime = 0;
    
    // 分发事件
    dispatchEventToWindow(focusedWindow, mPendingEvent);
}
```

### 3.2 Framework 层检测

#### 3.2.1 WindowManagerService 检测

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java

public class WindowManagerService {
    // 处理 No Focus Window ANR
    void notifyNoFocusWindowAnr(String reason) {
        // 查找可能相关的进程
        ProcessRecord proc = findProcessForNoFocusWindow();
        
        if (proc != null) {
            // 触发 ANR
            mActivityManagerService.mAnrHelper.appNotResponding(
                proc, 
                "No focus window: " + reason);
        }
    }
    
    // 查找可能相关的进程
    ProcessRecord findProcessForNoFocusWindow() {
        // 查找最近活动的应用进程
        // 或者查找窗口栈顶的应用进程
        for (int i = mWindows.size() - 1; i >= 0; i--) {
            WindowState win = mWindows.get(i);
            if (win.mAppToken != null) {
                return win.mAppToken.app;
            }
        }
        return null;
    }
}
```

### 3.3 关键源码位置

- **InputDispatcher.cpp**: `frameworks/native/services/inputflinger/InputDispatcher.cpp`
  - `findFocusedWindow()`: 查找焦点窗口
  - `onNoFocusWindowAnr()`: No Focus Window ANR 处理
  - `dispatchOnceInnerLocked()`: 输入事件分发和超时检测

- **WindowManagerService.java**: `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java`
  - `findFocusedWindow()`: 查找焦点窗口
  - `notifyNoFocusWindowAnr()`: No Focus Window ANR 处理

---

## 四、No Focus Window ANR 的常见原因

### 4.1 窗口创建失败

#### 4.1.1 Activity 窗口创建失败

```java
// ❌ 错误示例：Activity 窗口创建失败
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        // 窗口创建失败（如内存不足、权限问题等）
        // 导致 Activity 没有窗口，无法获得焦点
        try {
            setContentView(R.layout.activity_main);
        } catch (Exception e) {
            // 窗口创建失败，但没有正确处理
            e.printStackTrace();
        }
    }
}
```

#### 4.1.2 Dialog 窗口创建失败

```java
// ❌ 错误示例：Dialog 窗口创建失败
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // Dialog 窗口创建失败
        Dialog dialog = new Dialog(this);
        try {
            dialog.setContentView(R.layout.dialog_layout);
            dialog.show();
        } catch (Exception e) {
            // Dialog 窗口创建失败，但没有正确处理
            e.printStackTrace();
        }
    }
}
```

### 4.2 窗口焦点丢失

#### 4.2.1 Activity 生命周期异常

```java
// ❌ 错误示例：Activity 生命周期异常导致焦点丢失
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onPause() {
        super.onPause();
        
        // 异常操作导致窗口状态异常
        // 如意外销毁窗口、修改窗口属性等
        getWindow().getDecorView().setVisibility(View.GONE);
    }
    
    @Override
    protected void onResume() {
        super.onResume();
        
        // 窗口可能无法重新获得焦点
        // 因为之前的异常操作
    }
}
```

#### 4.2.2 窗口属性设置错误

```java
// ❌ 错误示例：窗口属性设置错误
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 错误设置窗口属性，导致窗口无法获得焦点
        Window window = getWindow();
        window.setFlags(
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE);
    }
}
```

### 4.3 系统窗口状态异常

#### 4.3.1 系统服务异常

- **WindowManagerService 异常**：窗口管理服务异常，无法管理窗口焦点
- **InputManagerService 异常**：输入管理服务异常，无法分发输入事件
- **ActivityManagerService 异常**：活动管理服务异常，无法管理 Activity 状态

#### 4.3.2 系统窗口异常

- **StatusBar 异常**：状态栏窗口状态异常
- **NavigationBar 异常**：导航栏窗口状态异常
- **系统 Dialog 异常**：系统对话框窗口状态异常

### 4.4 多窗口模式异常

#### 4.4.1 分屏模式异常

```java
// ❌ 错误示例：分屏模式窗口管理异常
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 在分屏模式下，窗口管理可能异常
        // 如果应用不支持分屏，可能导致窗口无法获得焦点
        if (isInMultiWindowMode()) {
            // 处理不当可能导致焦点丢失
        }
    }
}
```

#### 4.4.2 Picture-in-Picture 模式异常

```java
// ❌ 错误示例：PIP 模式窗口管理异常
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 在 PIP 模式下，窗口管理可能异常
        if (isInPictureInPictureMode()) {
            // 处理不当可能导致焦点丢失
        }
    }
}
```

---

## 五、No Focus Window ANR 的分析方法

### 5.1 日志分析

#### 5.1.1 ANR 日志关键信息

```
ANR in com.example.app
PID: 12345
Reason: No focus window, but keys are being sent to it.  Make sure the input method is started and connected, and that the current activity has a window with input focus.
Load: 2.5 / 1.8 / 1.2
```

**关键字段**：
- **Reason**: 显示 "No focus window" 错误信息
- **PID**: 发生 ANR 的进程 ID
- **Load**: 系统负载（1分钟/5分钟/15分钟平均值）

**关键提示**：
- "Make sure the input method is started and connected": 确保输入法已启动并连接
- "current activity has a window with input focus": 当前 Activity 有获得焦点的窗口

#### 5.1.2 logcat 日志

```
E/ActivityManager: ANR in com.example.app
E/ActivityManager: PID: 12345
E/ActivityManager: Reason: No focus window, but keys are being sent to it.  Make sure the input method is started and connected, and that the current activity has a window with input focus.
E/ActivityManager: Load: 2.5 / 1.8 / 1.2
E/WindowManager: No focus window found
E/InputDispatcher: No focus window, dropping input event
```

**关键信息**：
- **No focus window found**: 系统无法找到焦点窗口
- **dropping input event**: 输入事件被丢弃

### 5.2 traces.txt 分析

#### 5.2.1 查看窗口管理相关线程

```bash
# 从 traces.txt 中查找 WindowManager 相关线程
"WindowManager" prio=5 tid=10 Blocked
  | group="main" sCount=1 dsCount=0 flags=1 obj=0x12c00000 self=0x7f8a4c00
  | sysTid=12346 nice=0 cgrp=default sched=0/0 handle=0x7f8a4c00
  | state=S schedstat=( 1000000000 500000000 1000 ) utm=100 stm=50 core=0 HZ=100
  | stack=0x7f8a4c00-0x7f8a4c00
  | held mutexes=
  at com.android.server.wm.WindowManagerService.findFocusedWindow(WindowManagerService.java:1234)
  at com.android.server.wm.WindowManagerService.dispatchInputEvent(WindowManagerService.java:2345)
```

**关键信息**：
- **at WindowManagerService.findFocusedWindow()**: 显示在查找焦点窗口
- **at WindowManagerService.dispatchInputEvent()**: 显示在分发输入事件

#### 5.2.2 查看应用主线程

```bash
# 查看应用主线程状态
"main" prio=5 tid=1 Blocked
  | group="main" sCount=1 dsCount=0 flags=1 obj=0x12c00000 self=0x7f8a4c00
  | sysTid=12345 nice=0 cgrp=default sched=0/0 handle=0x7f8a4c00
  | state=S schedstat=( 1000000000 500000000 1000 ) utm=100 stm=50 core=0 HZ=100
  | stack=0x7f8a4c00-0x7f8a4c00
  | held mutexes=
  at android.app.ActivityThread.handleResumeActivity(ActivityThread.java:3456)
  at android.app.ActivityThread$H.handleMessage(ActivityThread.java:1661)
```

**关键信息**：
- **at ActivityThread.handleResumeActivity()**: 显示 Activity 正在恢复
- 如果主线程正常，说明不是主线程阻塞导致的 ANR

### 5.3 窗口状态检查

#### 5.3.1 使用 dumpsys 检查窗口状态

```bash
# 检查窗口状态
adb shell dumpsys window windows

# 查找焦点窗口信息
# 应该能看到类似以下信息：
#   mCurrentFocus=Window{1234567 com.example.app/com.example.app.MainActivity}
#   如果 mCurrentFocus 为 null，说明没有焦点窗口
```

#### 5.3.2 检查窗口可见性

```bash
# 检查窗口可见性
adb shell dumpsys window windows | grep -A 10 "mCurrentFocus"

# 检查窗口是否可以接收输入
adb shell dumpsys window windows | grep "canReceiveKeys"
```

### 5.4 systrace/perfetto 分析

#### 5.4.1 查看窗口管理时间线

在 systrace 中查找：
- **WindowManager**: 窗口管理操作
- **InputDispatcher**: 输入事件分发
- **焦点窗口查找**: 查找焦点窗口的时间
- **窗口创建**: 窗口创建时间

#### 5.4.2 关键指标

- **焦点窗口查找时间**: 查看查找焦点窗口是否耗时
- **窗口创建时间**: 查看窗口创建是否失败或耗时
- **输入事件分发**: 查看输入事件是否被丢弃

---

## 六、No Focus Window ANR 的预防措施

### 6.1 正确管理窗口生命周期

#### 6.1.1 确保窗口正确创建

```java
// ✅ 正确示例：确保窗口正确创建
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        try {
            setContentView(R.layout.activity_main);
        } catch (Exception e) {
            // 窗口创建失败，正确处理
            Log.e(TAG, "Failed to create window", e);
            // 可以显示错误提示或重启 Activity
            finish();
            return;
        }
        
        // 确保窗口可以获得焦点
        getWindow().setFlags(
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            0); // 清除 FLAG_NOT_FOCUSABLE 标志
    }
}
```

#### 6.1.2 正确管理窗口可见性

```java
// ✅ 正确示例：正确管理窗口可见性
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onPause() {
        super.onPause();
        
        // 不要意外隐藏窗口
        // getWindow().getDecorView().setVisibility(View.GONE); // ❌ 不要这样做
    }
    
    @Override
    protected void onResume() {
        super.onResume();
        
        // 确保窗口可见
        getWindow().getDecorView().setVisibility(View.VISIBLE);
        
        // 确保窗口可以获得焦点
        getWindow().getDecorView().requestFocus();
    }
}
```

### 6.2 正确处理窗口属性

#### 6.2.1 避免设置错误的窗口标志

```java
// ❌ 错误示例：设置错误的窗口标志
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // ❌ 不要设置 FLAG_NOT_FOCUSABLE，除非有特殊需求
        Window window = getWindow();
        window.setFlags(
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE);
    }
}

// ✅ 正确示例：只在必要时设置窗口标志
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 只在必要时设置窗口标志
        // 例如：全屏模式
        if (isFullScreenMode()) {
            Window window = getWindow();
            window.setFlags(
                WindowManager.LayoutParams.FLAG_FULLSCREEN,
                WindowManager.LayoutParams.FLAG_FULLSCREEN);
        }
    }
}
```

### 6.3 正确处理多窗口模式

#### 6.3.1 支持分屏模式

```java
// ✅ 正确示例：正确处理分屏模式
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 检查是否在分屏模式
        if (isInMultiWindowMode()) {
            // 调整布局以适应分屏模式
            adjustLayoutForMultiWindow();
        }
    }
    
    @Override
    public void onMultiWindowModeChanged(boolean isInMultiWindowMode) {
        super.onMultiWindowModeChanged(isInMultiWindowMode);
        
        // 分屏模式改变时，调整布局
        if (isInMultiWindowMode) {
            adjustLayoutForMultiWindow();
        } else {
            adjustLayoutForFullScreen();
        }
        
        // 确保窗口可以获得焦点
        getWindow().getDecorView().requestFocus();
    }
}
```

#### 6.3.2 支持 Picture-in-Picture 模式

```java
// ✅ 正确示例：正确处理 PIP 模式
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 检查是否支持 PIP 模式
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.N) {
            if (packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)) {
                // 支持 PIP 模式
            }
        }
    }
    
    @Override
    public void onPictureInPictureModeChanged(boolean isInPictureInPictureMode) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode);
        
        // PIP 模式改变时，调整布局
        if (isInPictureInPictureMode) {
            adjustLayoutForPIP();
        } else {
            adjustLayoutForFullScreen();
        }
    }
}
```

### 6.4 确保输入法正确连接

#### 6.4.1 检查输入法状态

```java
// ✅ 正确示例：确保输入法正确连接
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        EditText editText = findViewById(R.id.edit_text);
        
        // 确保 EditText 可以获得焦点
        editText.setFocusable(true);
        editText.setFocusableInTouchMode(true);
        
        // 请求焦点
        editText.requestFocus();
        
        // 显示输入法
        InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
        imm.showSoftInput(editText, InputMethodManager.SHOW_IMPLICIT);
    }
}
```

### 6.5 性能优化建议

#### 6.5.1 快速创建窗口

- **减少布局复杂度**：减少布局层级和 View 数量，加快窗口创建
- **延迟加载**：非关键 View 延迟加载，加快窗口创建
- **优化资源加载**：优化资源加载，减少窗口创建时间

#### 6.5.2 正确管理窗口状态

- **及时释放资源**：窗口销毁时及时释放资源
- **避免内存泄漏**：避免窗口相关的内存泄漏
- **正确处理异常**：窗口创建或管理异常时正确处理

---

## 七、No Focus Window ANR 的典型案例

### 7.1 案例一：窗口创建失败

**问题描述**：
应用在低内存设备上创建窗口失败，导致 No Focus Window ANR。

**原因分析**：
- 设备内存不足
- 窗口创建时内存分配失败
- 应用没有正确处理窗口创建失败的情况

**解决方案**：
```java
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        try {
            setContentView(R.layout.activity_main);
        } catch (OutOfMemoryError e) {
            // 内存不足，使用简化布局
            setContentView(R.layout.activity_main_simple);
        } catch (Exception e) {
            // 其他异常，显示错误提示
            Log.e(TAG, "Failed to create window", e);
            showErrorDialog();
            finish();
            return;
        }
        
        // 确保窗口可以获得焦点
        getWindow().getDecorView().requestFocus();
    }
}
```

### 7.2 案例二：窗口焦点丢失

**问题描述**：
应用在 onPause() 中意外隐藏窗口，导致窗口焦点丢失。

**原因分析**：
- onPause() 中错误地隐藏了窗口
- onResume() 时窗口无法重新获得焦点

**解决方案**：
```java
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onPause() {
        super.onPause();
        
        // 不要隐藏窗口
        // getWindow().getDecorView().setVisibility(View.GONE); // ❌ 不要这样做
    }
    
    @Override
    protected void onResume() {
        super.onResume();
        
        // 确保窗口可见
        getWindow().getDecorView().setVisibility(View.VISIBLE);
        
        // 确保窗口可以获得焦点
        getWindow().getDecorView().requestFocus();
    }
}
```

### 7.3 案例三：多窗口模式异常

**问题描述**：
应用不支持分屏模式，在分屏模式下窗口无法获得焦点。

**原因分析**：
- 应用没有正确处理分屏模式
- 窗口在分屏模式下状态异常

**解决方案**：
```java
public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        // 检查是否在分屏模式
        if (isInMultiWindowMode()) {
            // 调整布局以适应分屏模式
            adjustLayoutForMultiWindow();
        }
    }
    
    @Override
    public void onMultiWindowModeChanged(boolean isInMultiWindowMode) {
        super.onMultiWindowModeChanged(isInMultiWindowMode);
        
        // 分屏模式改变时，调整布局
        if (isInMultiWindowMode) {
            adjustLayoutForMultiWindow();
        } else {
            adjustLayoutForFullScreen();
        }
        
        // 确保窗口可以获得焦点
        getWindow().getDecorView().requestFocus();
    }
}
```

---

## 八、总结

### 8.1 关键要点

1. **窗口焦点问题**：不是主线程阻塞，而是窗口焦点管理异常
2. **系统级问题**：通常涉及系统窗口管理和焦点分发机制
3. **常见原因**：窗口创建失败、窗口焦点丢失、系统窗口状态异常、多窗口模式异常
4. **预防措施**：正确管理窗口生命周期、正确处理窗口属性、支持多窗口模式、确保输入法正确连接

### 8.2 最佳实践

- ✅ 确保窗口正确创建，处理创建失败的情况
- ✅ 正确管理窗口可见性和焦点
- ✅ 避免设置错误的窗口标志（如 FLAG_NOT_FOCUSABLE）
- ✅ 支持多窗口模式（分屏、PIP）
- ✅ 确保输入法正确连接
- ✅ 快速创建窗口，减少布局复杂度

---

## 🔗 相关资源

- **源码位置**：
  - `InputDispatcher.cpp`: `frameworks/native/services/inputflinger/InputDispatcher.cpp`
  - `WindowManagerService.java`: `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java`
  - `Activity.java`: `frameworks/base/core/java/android/app/Activity.java`

- **官方文档**：
  - [Android 窗口管理官方文档](https://developer.android.com/reference/android/view/WindowManager)
  - [Android 多窗口支持官方文档](https://developer.android.com/guide/topics/ui/multi-window)
  - [Android ANR 调试指南](https://developer.android.com/topic/performance/vitals/anr)

---

**提示**：分析 No Focus Window ANR 时，重点关注窗口状态和焦点管理，而不是主线程堆栈。使用 `dumpsys window windows` 命令检查窗口状态，确认是否有焦点窗口。
