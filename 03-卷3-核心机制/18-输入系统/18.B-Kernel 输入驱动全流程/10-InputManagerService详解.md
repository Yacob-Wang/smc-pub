# InputManagerService 详解

## 引言

InputManagerService (IMS) 是 Android Framework 层的输入管理服务，作为 Java 层与 Native 层 Input 系统的桥梁，负责系统输入策略、设备管理和事件拦截等功能。本文将深入分析 IMS 的架构与实现。

---

## 1. IMS 架构概览

### 1.1 在系统中的位置

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          应用进程                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ViewRootImpl → InputEventReceiver → InputChannel               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Binder / InputChannel
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        system_server 进程                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Framework 层 (Java)                          │   │
│  │  ┌─────────────────────────────────────────────────────────────┐│   │
│  │  │              InputManagerService (IMS)                       ││   │
│  │  │  ┌───────────────────────────────────────────────────────┐  ││   │
│  │  │  │  输入策略管理 (Policy)                                 │  ││   │
│  │  │  │  - 系统按键处理                                        │  ││   │
│  │  │  │  - 输入设备管理                                        │  ││   │
│  │  │  │  - 键盘布局管理                                        │  ││   │
│  │  │  │  - 指针速度设置                                        │  ││   │
│  │  │  └───────────────────────────────────────────────────────┘  ││   │
│  │  └─────────────────────────────────────────────────────────────┘│   │
│  │                              │ JNI                               │   │
│  │  ┌───────────────────────────▼─────────────────────────────────┐│   │
│  │  │              NativeInputManager                              ││   │
│  │  │  - InputReaderPolicy                                        ││   │
│  │  │  - InputDispatcherPolicy                                    ││   │
│  │  └─────────────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│  ┌─────────────────────────────────▼─────────────────────────────────┐ │
│  │                        Native 层 (C++)                            │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │ │
│  │  │  EventHub    │  │ InputReader  │  │  InputDispatcher     │   │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心职责

| 职责 | 描述 |
|-----|------|
| 服务管理 | 启动/停止 Native 层 InputManager |
| 策略实现 | InputReaderPolicy / InputDispatcherPolicy |
| 设备管理 | 输入设备信息查询和配置 |
| 按键拦截 | 系统按键 (电源、音量等) 处理 |
| 键盘管理 | 键盘布局和字符映射 |
| 指针配置 | 指针速度、加速度等设置 |

---

## 2. IMS 初始化

### 2.1 服务启动

```java
// frameworks/base/services/java/com/android/server/SystemServer.java

private void startOtherServices() {
    // 创建 InputManagerService
    InputManagerService inputManager = new InputManagerService(context);
    
    // 添加到 ServiceManager
    ServiceManager.addService(Context.INPUT_SERVICE, inputManager);
    
    // 设置回调
    inputManager.setWindowManagerCallbacks(wm.getInputManagerCallback());
    
    // 启动服务
    inputManager.start();
}
```

### 2.2 IMS 构造函数

```java
// frameworks/base/services/core/java/com/android/server/input/InputManagerService.java

public class InputManagerService extends IInputManager.Stub
        implements Watchdog.Monitor {
    
    private static final String TAG = "InputManager";
    
    // Native 指针
    private final long mPtr;
    
    // 上下文
    private final Context mContext;
    private final Handler mHandler;
    
    // WMS 回调
    private WindowManagerCallbacks mWindowManagerCallbacks;
    
    // 设备监听器
    private final ArrayList<InputDevicesChangedListenerRecord> 
        mInputDevicesChangedListeners = new ArrayList<>();
    
    // 输入设备信息
    private InputDevice[] mInputDevices = new InputDevice[0];
    
    public InputManagerService(Context context) {
        this.mContext = context;
        
        // 创建 Handler
        this.mHandler = new InputManagerHandler(
            DisplayThread.get().getLooper());
        
        // 初始化 Native 层
        mPtr = nativeInit(this, mContext, mHandler.getLooper().getQueue());
        
        // 注册设置观察者
        registerSettingsObservers();
        
        // 注册电池状态接收器
        registerBatteryReceiver();
    }
    
    public void start() {
        // 启动 Native 层
        nativeStart(mPtr);
        
        // 注册广播接收器
        registerInputDevicesChangedReceiver();
        
        // 注册 Watchdog
        Watchdog.getInstance().addMonitor(this);
    }
}
```

### 2.3 Native 层初始化

```cpp
// frameworks/base/services/core/jni/com_android_server_input_InputManagerService.cpp

static jlong nativeInit(JNIEnv* env, jclass /* clazz */,
        jobject serviceObj, jobject contextObj, jobject messageQueueObj) {
    
    // 获取 MessageQueue 的 Looper
    sp<MessageQueue> messageQueue = 
        android_os_MessageQueue_getMessageQueue(env, messageQueueObj);
    sp<Looper> looper = messageQueue->getLooper();
    
    // 创建 NativeInputManager
    NativeInputManager* im = new NativeInputManager(contextObj, serviceObj, 
                                                     looper);
    im->incStrong(0);
    
    return reinterpret_cast<jlong>(im);
}

NativeInputManager::NativeInputManager(jobject contextObj, 
                                        jobject serviceObj,
                                        const sp<Looper>& looper)
    : mLooper(looper), mInteractive(true) {
    
    JNIEnv* env = jniEnv();
    
    // 保存 Java 对象引用
    mServiceObj = env->NewGlobalRef(serviceObj);
    
    // 创建 EventHub
    sp<EventHub> eventHub = new EventHub();
    
    // 创建 InputManager (包含 InputReader 和 InputDispatcher)
    mInputManager = new InputManager(eventHub, this, this);
}

void NativeInputManager::start() {
    // 启动 InputManager
    status_t result = mInputManager->start();
    if (result) {
        ALOGE("Could not start InputManager: %d", result);
    }
}
```

---

## 3. 策略实现

### 3.1 InputReaderPolicy

```cpp
class NativeInputManager : public InputReaderPolicyInterface,
                           public InputDispatcherPolicyInterface {
public:
    // ========== InputReaderPolicy ==========
    
    // 获取配置
    virtual void getReaderConfiguration(InputReaderConfiguration* outConfig) override {
        JNIEnv* env = jniEnv();
        
        // 获取指针速度
        jint pointerSpeed = env->CallIntMethod(mServiceObj,
            gInputManagerServiceClassInfo.getPointerSpeedSetting);
        outConfig->setPointerSpeed(pointerSpeed);
        
        // 获取显示视口
        std::vector<DisplayViewport> viewports;
        getDisplayViewports(viewports);
        outConfig->setDisplayViewports(viewports);
        
        // 获取设备配置
        getExcludedDeviceNames(outConfig->excludedDeviceNames);
    }
    
    // 通知输入设备变更
    virtual void notifyInputDevicesChanged(
            const std::vector<InputDeviceInfo>& inputDevices) override {
        JNIEnv* env = jniEnv();
        
        // 转换为 Java 数组
        jobjectArray devices = convertInputDevicesToJava(env, inputDevices);
        
        // 回调 Java 层
        env->CallVoidMethod(mServiceObj,
            gInputManagerServiceClassInfo.notifyInputDevicesChanged,
            devices);
    }
    
    // 获取键盘布局
    virtual std::shared_ptr<KeyCharacterMap> getKeyboardLayoutOverlay(
            const InputDeviceIdentifier& identifier) override {
        // 调用 Java 层获取键盘布局
        JNIEnv* env = jniEnv();
        // ...
    }
};
```

### 3.2 InputDispatcherPolicy

```cpp
class NativeInputManager : ... {
    // ========== InputDispatcherPolicy ==========
    
    // 按键入队前拦截
    virtual void interceptKeyBeforeQueueing(
            const KeyEvent* keyEvent,
            uint32_t& policyFlags) override {
        
        // 交互状态影响 wake/brightness 标志
        bool interactive = mInteractive.load();
        if (!interactive) {
            policyFlags |= POLICY_FLAG_PASS_TO_USER;
        }
        
        // 调用 Java 层处理
        JNIEnv* env = jniEnv();
        
        jint wmActions = env->CallIntMethod(mServiceObj,
            gInputManagerServiceClassInfo.interceptKeyBeforeQueueing,
            keyEvent->getKeyCode(),
            keyEvent->getAction(),
            policyFlags,
            interactive ? JNI_TRUE : JNI_FALSE);
        
        // 处理返回的动作
        handleInterceptActions(wmActions, keyEvent->getEventTime(), policyFlags);
    }
    
    // 按键分发前拦截
    virtual nsecs_t interceptKeyBeforeDispatching(
            const sp<IBinder>& token,
            const KeyEvent* keyEvent,
            uint32_t policyFlags) override {
        
        JNIEnv* env = jniEnv();
        
        // 转换 KeyEvent
        jobject keyEventObj = android_view_KeyEvent_fromNative(env, keyEvent);
        
        // 调用 Java 层
        jlong delay = env->CallLongMethod(mServiceObj,
            gInputManagerServiceClassInfo.interceptKeyBeforeDispatching,
            token, keyEventObj, policyFlags);
        
        return delay;
    }
    
    // 触摸入队前拦截
    virtual void interceptMotionBeforeQueueing(
            int32_t displayId,
            nsecs_t when,
            uint32_t& policyFlags) override {
        
        // 触摸事件通常用于唤醒设备
        bool interactive = mInteractive.load();
        if (!interactive) {
            policyFlags |= POLICY_FLAG_PASS_TO_USER;
        }
    }
    
    // 通知 ANR
    virtual void notifyNoFocusedWindowAnr(
            const std::shared_ptr<InputApplicationHandle>& appHandle) override {
        
        JNIEnv* env = jniEnv();
        
        // 调用 Java 层处理 ANR
        env->CallVoidMethod(mServiceObj,
            gInputManagerServiceClassInfo.notifyNoFocusedWindowAnr,
            appHandle->getApplicationHandleToken());
    }
    
    // 通知窗口无响应
    virtual void notifyWindowUnresponsive(
            const sp<IBinder>& token,
            const std::string& reason) override {
        
        JNIEnv* env = jniEnv();
        jstring reasonStr = env->NewStringUTF(reason.c_str());
        
        env->CallVoidMethod(mServiceObj,
            gInputManagerServiceClassInfo.notifyWindowUnresponsive,
            token, reasonStr);
    }
};
```

---

## 4. Java 层按键拦截

### 4.1 interceptKeyBeforeQueueing

```java
// frameworks/base/services/core/java/com/android/server/input/InputManagerService.java

// Native 回调
private int interceptKeyBeforeQueueing(int keyCode, int action, 
                                       int policyFlags, boolean isScreenOn) {
    // 委托给 WindowManagerService
    return mWindowManagerCallbacks.interceptKeyBeforeQueueing(
        keyCode, action, policyFlags, isScreenOn);
}
```

```java
// frameworks/base/services/core/java/com/android/server/wm/InputManagerCallback.java

@Override
public int interceptKeyBeforeQueueing(int keyCode, int action, 
                                       int policyFlags, boolean isScreenOn) {
    // 委托给 PhoneWindowManager
    return mService.mPolicy.interceptKeyBeforeQueueing(keyCode, action, 
                                                        policyFlags, isScreenOn);
}
```

```java
// frameworks/base/services/core/java/com/android/server/policy/PhoneWindowManager.java

@Override
public int interceptKeyBeforeQueueing(int keyCode, int action, 
                                       int policyFlags, boolean isScreenOn) {
    int result = 0;
    boolean down = (action == KeyEvent.ACTION_DOWN);
    
    // 检查是否需要传递给用户
    boolean isWakeKey = (policyFlags & WindowManagerPolicy.FLAG_WAKE) != 0;
    
    switch (keyCode) {
        case KeyEvent.KEYCODE_POWER: {
            // 电源键处理
            result &= ~ACTION_PASS_TO_USER;
            if (down) {
                interceptPowerKeyDown(interactive);
            } else {
                interceptPowerKeyUp(interactive);
            }
            break;
        }
        
        case KeyEvent.KEYCODE_VOLUME_DOWN:
        case KeyEvent.KEYCODE_VOLUME_UP:
        case KeyEvent.KEYCODE_VOLUME_MUTE: {
            // 音量键处理
            if (down) {
                handleVolumeKey(keyCode);
            }
            // 音量键通常不传递给用户
            if (mUseTvRouting) {
                result |= ACTION_PASS_TO_USER;
            }
            break;
        }
        
        case KeyEvent.KEYCODE_HOME: {
            // Home 键处理
            if (!interactive) {
                // 屏幕关闭时, 唤醒
                result |= ACTION_WAKE_UP;
            }
            // Home 键需要传递
            result |= ACTION_PASS_TO_USER;
            break;
        }
        
        default:
            // 其他按键传递给用户
            result |= ACTION_PASS_TO_USER;
            break;
    }
    
    return result;
}
```

### 4.2 interceptKeyBeforeDispatching

```java
// frameworks/base/services/core/java/com/android/server/policy/PhoneWindowManager.java

@Override
public long interceptKeyBeforeDispatching(IBinder focusedToken,
                                          KeyEvent event, int policyFlags) {
    final int keyCode = event.getKeyCode();
    final int action = event.getAction();
    final int repeatCount = event.getRepeatCount();
    
    // 已处理的按键不再分发
    if ((policyFlags & WindowManagerPolicy.FLAG_PASS_TO_USER) == 0) {
        return -1;  // 不分发
    }
    
    // 处理快捷键
    if (action == KeyEvent.ACTION_DOWN && repeatCount == 0) {
        // 截屏快捷键: 电源 + 音量减
        if (keyCode == KeyEvent.KEYCODE_VOLUME_DOWN) {
            if (mScreenshotChordVolumeDownKeyTriggered && !mScreenshotChordVolumeDownKeyConsumed) {
                // 触发截屏
                takeScreenshot();
                return -1;
            }
        }
    }
    
    // 处理系统对话框
    if (keyCode == KeyEvent.KEYCODE_BACK) {
        if (action == KeyEvent.ACTION_DOWN && repeatCount == 0) {
            // 检查是否有系统对话框
        }
    }
    
    return 0;  // 正常分发
}
```

---

## 5. 设备管理

### 5.1 获取输入设备

```java
// frameworks/base/services/core/java/com/android/server/input/InputManagerService.java

@Override
public InputDevice[] getInputDevices() {
    synchronized (mInputDevicesLock) {
        return mInputDevices.clone();
    }
}

@Override
public InputDevice getInputDevice(int deviceId) {
    synchronized (mInputDevicesLock) {
        for (InputDevice device : mInputDevices) {
            if (device.getId() == deviceId) {
                return device;
            }
        }
    }
    return null;
}

// Native 回调 - 设备变更通知
private void notifyInputDevicesChanged(InputDevice[] devices) {
    synchronized (mInputDevicesLock) {
        mInputDevices = devices;
    }
    
    // 通知监听器
    mHandler.post(() -> {
        for (InputDevicesChangedListenerRecord listener : mInputDevicesChangedListeners) {
            listener.notifyInputDevicesChanged(devices);
        }
    });
}
```

### 5.2 设备监听

```java
@Override
public void registerInputDevicesChangedListener(
        IInputDevicesChangedListener listener) {
    if (listener == null) {
        throw new IllegalArgumentException("listener must not be null");
    }
    
    synchronized (mInputDevicesLock) {
        // 检查是否已注册
        for (InputDevicesChangedListenerRecord record : mInputDevicesChangedListeners) {
            if (record.mListener.asBinder() == listener.asBinder()) {
                return;
            }
        }
        
        // 添加监听器
        InputDevicesChangedListenerRecord record = 
            new InputDevicesChangedListenerRecord(listener);
        mInputDevicesChangedListeners.add(record);
        
        // 注册死亡通知
        try {
            listener.asBinder().linkToDeath(record, 0);
        } catch (RemoteException ex) {
            mInputDevicesChangedListeners.remove(record);
        }
    }
}
```

---

## 6. 窗口管理接口

### 6.1 InputChannel 注册

```java
// frameworks/base/services/core/java/com/android/server/input/InputManagerService.java

public void registerInputChannel(InputChannel inputChannel) {
    if (inputChannel == null) {
        throw new IllegalArgumentException("inputChannel must not be null");
    }
    
    nativeRegisterInputChannel(mPtr, inputChannel);
}

public void unregisterInputChannel(InputChannel inputChannel) {
    if (inputChannel == null) {
        throw new IllegalArgumentException("inputChannel must not be null");
    }
    
    nativeUnregisterInputChannel(mPtr, inputChannel);
}
```

### 6.2 焦点设置

```java
public void setInputWindows(InputWindowHandle[] windowHandles, int displayId) {
    nativeSetInputWindows(mPtr, windowHandles, displayId);
}

public void setFocusedApplication(int displayId,
        InputApplicationHandle application) {
    nativeSetFocusedApplication(mPtr, displayId, application);
}

public void setFocusedWindow(InputWindowHandle windowHandle) {
    nativeSetFocusedWindow(mPtr, windowHandle);
}
```

---

## 7. 指针速度配置

### 7.1 设置观察者

```java
private void registerSettingsObservers() {
    ContentResolver resolver = mContext.getContentResolver();
    
    // 监听指针速度设置
    resolver.registerContentObserver(
        Settings.System.getUriFor(Settings.System.POINTER_SPEED),
        true, mSettingsObserver, UserHandle.USER_ALL);
    
    // 监听显示模式
    resolver.registerContentObserver(
        Settings.System.getUriFor(Settings.System.SHOW_TOUCHES),
        true, mSettingsObserver, UserHandle.USER_ALL);
    
    mSettingsObserver.onChange(true);
}

private final ContentObserver mSettingsObserver = new ContentObserver(mHandler) {
    @Override
    public void onChange(boolean selfChange) {
        // 更新指针速度
        updatePointerSpeedFromSettings();
        
        // 更新触摸显示
        updateShowTouchesFromSettings();
    }
};

private void updatePointerSpeedFromSettings() {
    int speed = Settings.System.getIntForUser(
        mContext.getContentResolver(),
        Settings.System.POINTER_SPEED,
        0, // default
        UserHandle.USER_CURRENT);
    
    nativeSetPointerSpeed(mPtr, speed);
}
```

### 7.2 Native 实现

```cpp
static void nativeSetPointerSpeed(JNIEnv* env, jclass /* clazz */,
        jlong ptr, jint speed) {
    NativeInputManager* im = reinterpret_cast<NativeInputManager*>(ptr);
    
    im->setPointerSpeed(speed);
}

void NativeInputManager::setPointerSpeed(int32_t speed) {
    { // acquire lock
        AutoMutex _l(mLock);
        
        if (mLocked.pointerSpeed == speed) {
            return;
        }
        
        mLocked.pointerSpeed = speed;
    } // release lock
    
    // 更新配置
    mInputManager->getReader()->requestRefreshConfiguration(
        InputReaderConfiguration::CHANGE_POINTER_SPEED);
}
```

---

## 8. 本章小结

InputManagerService 是 Framework 层的输入管理核心：

| 功能 | 实现 |
|-----|------|
| 服务启动 | 初始化 Native InputManager |
| 策略实现 | NativeInputManager 实现 Policy 接口 |
| 按键拦截 | 系统按键由 PhoneWindowManager 处理 |
| 设备管理 | 查询和监听输入设备 |
| 窗口接口 | 为 WMS 提供输入相关接口 |

关键交互：
1. IMS 初始化时创建 Native InputManager
2. Native 层通过 Policy 回调 Java 层
3. PhoneWindowManager 处理系统按键
4. WMS 通过 IMS 接口设置窗口信息

下一篇将介绍焦点窗口与焦点应用管理。

---

## 参考资料

1. `frameworks/base/services/core/java/com/android/server/input/InputManagerService.java`
2. `frameworks/base/services/core/jni/com_android_server_input_InputManagerService.cpp`
3. `frameworks/base/services/core/java/com/android/server/policy/PhoneWindowManager.java`
