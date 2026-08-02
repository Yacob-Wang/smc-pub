# 11-Window 诊断工具与治理体系

作为 Window 系列的收官之篇，本文将系统化地构建一套完整的 Window 诊断工具链与治理体系。前 10 篇文章回答了"Window 系统是什么、怎么运转、会在哪里出问题"，本篇回答最后一个关键问题：**出了问题怎么查？查到了怎么治？治好了怎么防？**

对于稳定性架构师，工具链的熟练程度直接决定了排查效率。一个线上黑屏问题，如果知道在 `dumpsys window` 中检查 `mHasSurface`、在 `dumpsys SurfaceFlinger` 中检查 Layer 状态、在 Perfetto 中追踪 `relayoutWindow` 时序，5 分钟内即可定位根因层。如果不知道，可能花 2 天还在读日志猜原因。

---

## 1. 诊断工具全景

### 1.1 工具与层的对应关系

Window 系统横跨 App 进程、system_server（WMS）、SurfaceFlinger 三个进程四个层次。不同层的问题需要不同的诊断工具：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  层次             │  工具                              │  用途              │
├─────────────────────────────────────────────────────────────────────────────┤
│                   │  StrictMode                        │  检测主线程违规    │
│  App 层           │  LeakCanary                        │  检测 Window 泄漏  │
│  (ViewRootImpl)   │  Systrace / Perfetto (view tag)    │  追踪 traversals   │
│                   │  Choreographer FrameCallback       │  检测掉帧          │
├─────────────────────────────────────────────────────────────────────────────┤
│                   │  dumpsys window                    │  窗口状态全景      │
│  WMS 层           │  dumpsys window containers         │  WindowContainer树 │
│  (system_server)  │  wm trace (winscope)               │  窗口状态回放      │
│                   │  Systrace / Perfetto (wm tag)      │  WMS 操作时序      │
├─────────────────────────────────────────────────────────────────────────────┤
│  Input 层         │  dumpsys input                     │  焦点窗口验证      │
│  (InputDispatcher)│  Systrace / Perfetto (input tag)   │  事件分发时序      │
├─────────────────────────────────────────────────────────────────────────────┤
│  Surface 层       │  dumpsys SurfaceFlinger             │  Layer/Buffer 状态 │
│  (SurfaceFlinger) │  dumpsys SurfaceFlinger --list      │  Layer 列表        │
│                   │  Systrace / Perfetto (gfx/sf tag)  │  合成与帧时序      │
├─────────────────────────────────────────────────────────────────────────────┤
│                   │  Perfetto (全量 trace)              │  端到端时序分析    │
│  系统级           │  ANR traces (/data/anr/traces.txt) │  线程栈分析        │
│                   │  Watchdog traces                   │  system_server 锁  │
│                   │  dumpsys meminfo surfaceflinger     │  显存占用          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 工具选择决策树

排查 Window 问题时，按以下决策路径选择工具：

```
问题类型是什么？
    │
    ├── 窗口状态异常（黑屏/不显示/层级错误/焦点丢失）
    │     → 第一步：dumpsys window（查窗口状态）
    │     → 第二步：dumpsys input（交叉验证焦点）
    │     → 第三步：dumpsys SurfaceFlinger（查 Surface/Layer）
    │
    ├── 性能问题（启动慢/卡顿/掉帧/动画不流畅）
    │     → 第一步：Perfetto（wm + view + gfx + sf tag）
    │     → 第二步：dumpsys gfxinfo（帧统计）
    │     → 第三步：dumpsys window（窗口数量检查）
    │
    ├── ANR（Input ANR / no focused window）
    │     → 第一步：traces.txt（线程栈）
    │     → 第二步：dumpsys window + dumpsys input（焦点交叉验证）
    │     → 第三步：Perfetto（时序还原）
    │
    ├── Crash（BadTokenException / WindowLeaked / Surface 异常）
    │     → 第一步：堆栈分析（定位触发点）
    │     → 第二步：dumpsys window（窗口状态验证）
    │     → 第三步：logcat（WMS 日志）
    │
    ├── system_server Watchdog
    │     → 第一步：traces.txt（mGlobalLock 持有者）
    │     → 第二步：Perfetto（锁竞争时序）
    │     → 第三步：dumpsys window（窗口数量 / 动画状态）
    │
    └── 间歇性/难复现问题
          → winscope trace（窗口状态录制回放）
          → Perfetto 长时间录制
```

### 1.3 各层工具速查表

| 诊断场景 | 首选工具 | 命令 | 关键输出 |
|---------|---------|------|---------|
| 查看所有窗口状态 | dumpsys window | `adb shell dumpsys window windows` | 窗口列表、Surface 状态、可见性 |
| 查看焦点窗口 | dumpsys window | `adb shell dumpsys window displays` | mCurrentFocus、mFocusedApp |
| 查看窗口层级树 | dumpsys window | `adb shell dumpsys window containers` | WindowContainer 层级结构 |
| 验证 Input 焦点 | dumpsys input | `adb shell dumpsys input` | FocusedApplications、FocusedWindows |
| 查看 Layer 状态 | dumpsys SF | `adb shell dumpsys SurfaceFlinger` | Layer 树、Buffer 状态、合成方式 |
| 列出所有 Layer | dumpsys SF | `adb shell dumpsys SurfaceFlinger --list` | Layer 名称列表 |
| 查看显存占用 | dumpsys meminfo | `adb shell dumpsys meminfo surfaceflinger` | GraphicBuffer 内存 |
| 端到端时序分析 | Perfetto | `perfetto -c config.pbtx -o trace.pb` | WMS/SF/View 操作时序 |
| 窗口状态录制 | wm trace | `adb shell wm trace start` | WindowContainer 树快照序列 |
| 线程栈（ANR） | traces.txt | `adb pull /data/anr/traces.txt` | 所有线程的调用栈 |

---

## 2. dumpsys window

`dumpsys window` 是 Window 问题排查的**第一工具**。它直接输出 WMS 内部状态的快照，覆盖窗口列表、焦点信息、策略状态、动画状态等全部维度。

### 2.1 命令与子命令

```bash
# 完整输出（信息量大，建议重定向到文件）
adb shell dumpsys window > window_dump.txt

# 常用子命令（缩小范围）
adb shell dumpsys window windows        # 所有窗口状态
adb shell dumpsys window displays       # Display 信息和焦点
adb shell dumpsys window containers     # WindowContainer 层级树
adb shell dumpsys window tokens         # WindowToken 层级
adb shell dumpsys window policy         # DisplayPolicy 状态（SystemBar/IME）
adb shell dumpsys window animations     # 运行中的动画
adb shell dumpsys window trace          # wm trace 状态
```

### 2.2 关键段落解读

`dumpsys window` 的输出包含以下关键段落，每个段落对应一类排查需求：

**段落一：WINDOW MANAGER POLICY STATE**

```
WINDOW MANAGER POLICY STATE (dumpsys window policy)
    mFocusedApp=ActivityRecord{a1b2c3d u0 com.example.app/.MainActivity t5}
    mFocusedWindow=Window{e5f6g7h u0 com.example.app/com.example.app.MainActivity}
    mTopFullscreenOpaqueWindowState=Window{e5f6g7h ...}
    isStatusBarKeyguard=false
    mForceStatusBar=false
    mShowingDream=false
    mDreamingLockscreen=false
    mStatusBar=Window{1234abcd u0 StatusBar}
    mNavigationBar=Window{5678efgh u0 NavigationBar0}
```

- `mFocusedApp`：WMS 认为的当前焦点 Activity。由 AMS 通过 `setFocusedApp()` 设置。
- `mFocusedWindow`：WMS 认为的当前焦点窗口。由 `updateFocusedWindowLocked()` 计算。
- `mTopFullscreenOpaqueWindowState`：最顶层的全屏不透明窗口，影响 StatusBar 的可见性。
- `mStatusBar` / `mNavigationBar`：系统栏窗口引用，如果为 null 表示系统栏未创建。

> **稳定性架构师视角：** `mFocusedApp` 和 `mFocusedWindow` 是排查焦点 ANR 的两个关键字段。正常情况下两者指向同一个 Activity。如果 `mFocusedApp` 有值但 `mFocusedWindow` 为 null，说明 Activity 已被 AMS 设为焦点，但其窗口尚未完成创建/显示——这正是 "no focused window" ANR 的典型状态。

**段落二：WINDOW MANAGER WINDOWS**

```
WINDOW MANAGER WINDOWS (dumpsys window windows)
  Window #0 Window{abcd1234 u0 com.example.app/com.example.app.MainActivity}:
    mDisplayId=0 stackId=5 mSession=Session{9876fedc 12345:u0a100}
    mOwnerUid=10100 showForAllUsers=false appop=NONE
    mAttrs={(0,0)(fillxfill) sim={adjust=resize} ty=BASE_APPLICATION fmt=TRANSPARENT
        fl=FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS
        pfl=FORCE_DRAW_STATUS_BAR_BACKGROUND}
    Requested w=1080 h=2340
    mHasSurface=true
    Surface: shown=true layer=0 alpha=1.0 rect=(0.0,0.0) 1080x2340
    mViewVisibility=0x0 mHaveFrame=true mObscured=false
    isVisible=true isVisibleLw=true isDisplayed=true
    mGivenContentInsets=[0,83][0,132] mGivenVisibleInsets=[0,0][0,0]
    isReadyForDisplay()=true
    WindowStateAnimator{...}:
      mSurface=Surface(name=com.example.app/...)/@0x...
      Surface
        mShown=true
```

关键字段解读：

| 字段 | 含义 | 排查价值 |
|------|------|---------|
| `mHasSurface` | 窗口是否持有有效 Surface | false → 黑屏的直接原因 |
| `isVisible` | 窗口是否可见 | false 但应该可见 → 窗口被错误隐藏 |
| `mViewVisibility` | App 端设置的可见性 | 0x0=VISIBLE, 0x4=INVISIBLE, 0x8=GONE |
| `isReadyForDisplay()` | 窗口是否就绪可显示 | false → 窗口在等待首帧绘制或 Surface |
| `mSurface` / `mShown` | Surface 对象及其显示状态 | Surface 存在但 mShown=false → 被隐藏 |
| `ty=` | 窗口类型 | 确认窗口类型是否符合预期 |
| `fl=` | 窗口 flags | 检查 FLAG_NOT_FOCUSABLE 等关键 flag |

**段落三：WINDOW MANAGER TOKENS**

```
WINDOW MANAGER TOKENS (dumpsys window tokens)
  Display #0:
    WindowToken{aaa111 android.os.BinderProxy@bbb222}:
      windows=[Window{ccc333 u0 com.example.app/...MainActivity}]
    WindowToken{ddd444 android.os.BinderProxy@eee555}:
      windows=[Window{fff666 u0 StatusBar}]
```

Token 层级展示了窗口与其 Token 的归属关系。Application 窗口的 Token 对应 `ActivityRecord`，System 窗口的 Token 由系统服务注册。

**段落四：WINDOW MANAGER FOCUS**

```
mCurrentFocus=Window{e5f6g7h u0 com.example.app/com.example.app.MainActivity}
mFocusedApp=ActivityRecord{a1b2c3d u0 com.example.app/.MainActivity t5}
mLastFocus=Window{e5f6g7h u0 com.example.app/com.example.app.MainActivity}
```

- `mCurrentFocus`：当前焦点窗口（与 Policy State 中的 `mFocusedWindow` 相同，但位置更易 grep）。
- `mFocusedApp`：当前焦点 Application。
- `mLastFocus`：上一个焦点窗口（焦点切换调试时有用）。

**段落五：WINDOW MANAGER ANIMATIONS**

```
WINDOW MANAGER ANIMATIONS (dumpsys window animations)
  Window #0 Window{abcd1234 u0 ...}:
    mAnimating=true
    mLocalAnimating=false
    Animation: ...
  mAppTransition=AppTransition{ state=IDLE }
```

正在执行动画的窗口列表和 AppTransition 状态。如果 `mAppTransition` 长时间处于非 `IDLE` 状态，说明转场动画卡住了。

### 2.3 焦点信息解读方法

焦点信息是排查 Input ANR 的核心。解读步骤如下：

```
Step 1: 提取焦点三元组
  $ adb shell dumpsys window | grep -E "mCurrentFocus|mFocusedApp|mFocusedWindow"

  期望输出:
  mCurrentFocus=Window{xxx com.example.app/.MainActivity}
  mFocusedApp=ActivityRecord{yyy com.example.app/.MainActivity}
  mFocusedWindow=Window{xxx com.example.app/.MainActivity}

Step 2: 验证一致性
  ✓ mCurrentFocus == mFocusedWindow → 正常
  ✗ mCurrentFocus == null 但 mFocusedApp 有值 → 焦点丢失风险
  ✗ mCurrentFocus 指向 ActivityA 但 mFocusedApp 指向 ActivityB → 焦点切换中

Step 3: 如果焦点为 null，检查所有窗口的 canReceiveKeys
  $ adb shell dumpsys window windows | grep -E "Window #|isVisible|canReceiveKeys"
  → 找到所有 isVisible=true 但 canReceiveKeys=false 的窗口
  → 检查是否设置了 FLAG_NOT_FOCUSABLE
```

### 2.4 实战排查模式

**模式一：Window 泄漏检测（窗口数量异常）**

```bash
# 统计每个包名的窗口数量
adb shell dumpsys window windows | grep "mOwnerUid" | sort | uniq -c | sort -rn

# 如果某个包名的窗口数量 > 20，大概率是泄漏
# 正常 Activity 应该只有 1-3 个窗口（主窗口 + Dialog + PopupWindow）
```

每个 Activity 通常持有 1 个主窗口。如果某个 Activity 类型的窗口数量持续增长（如每次操作多一个 Dialog 窗口），说明 `Dialog.dismiss()` 未被正确调用。通过 `dumpsys window windows` 输出中的 `mOwnerUid` 和窗口名称即可定位泄漏源。

**模式二：焦点问题定位**

```bash
# 快速检查焦点状态
adb shell dumpsys window displays | grep -E "mCurrentFocus|mFocusedApp"

# 如果 mCurrentFocus=null：
# 1. 检查是否有窗口正在 adding（还没完成 relayout）
adb shell dumpsys window windows | grep "isReadyForDisplay"

# 2. 检查是否所有可见窗口都设置了 FLAG_NOT_FOCUSABLE
adb shell dumpsys window windows | grep -E "Window #|fl=.*NOT_FOCUSABLE"
```

**模式三：Z-order 问题排查**

```bash
# 查看完整的窗口层级树
adb shell dumpsys window containers

# 输出形式：
#   #0 DefaultTaskDisplayArea
#     #1 Task=5
#       #0 ActivityRecord{...}
#         #0 Window{... com.example.app/.MainActivity}
#     #0 Task=1
#       #0 ActivityRecord{...}
#         #0 Window{... com.android.launcher3/.Launcher}
#   StatusBar container
#     #0 Window{... StatusBar}

# 数字越大，Z-order 越高。确认窗口在层级树中的位置是否符合预期。
```

### 2.5 核心 grep 模式速查

| grep 模式 | 用途 | 命令 |
|-----------|------|------|
| `mFocusedApp` | 查焦点 Activity | `dumpsys window \| grep mFocusedApp` |
| `mCurrentFocus` | 查焦点窗口 | `dumpsys window \| grep mCurrentFocus` |
| `mHasSurface` | 查 Surface 状态 | `dumpsys window windows \| grep -E "Window #\|mHasSurface"` |
| `isVisible` | 查窗口可见性 | `dumpsys window windows \| grep -E "Window #\|isVisible"` |
| `mSurface` | 查 Surface 对象 | `dumpsys window windows \| grep mSurface` |
| `mAppTransition` | 查转场状态 | `dumpsys window \| grep mAppTransition` |
| `mOwnerUid` | 按进程统计窗口 | `dumpsys window windows \| grep mOwnerUid` |
| `NOT_FOCUSABLE` | 查不可聚焦窗口 | `dumpsys window windows \| grep NOT_FOCUSABLE` |

---

## 3. dumpsys SurfaceFlinger

`dumpsys SurfaceFlinger` 输出 SurfaceFlinger 进程的完整状态，是排查 Surface 泄漏、合成异常、Buffer 问题的核心工具。

### 3.1 命令与子命令

```bash
# 完整输出
adb shell dumpsys SurfaceFlinger > sf_dump.txt

# 常用子命令
adb shell dumpsys SurfaceFlinger --list          # 仅列出所有 Layer 名称
adb shell dumpsys SurfaceFlinger --latency        # 帧延迟统计
adb shell dumpsys SurfaceFlinger --latency-clear   # 清除帧延迟统计
adb shell dumpsys SurfaceFlinger --timestats       # 帧时间统计
```

### 3.2 关键段落解读

**Layer 列表**

```
Visible layers (
  * Layer (Task=5#0)
    Region
      + (0, 0, 1080, 2340)
    State
      z= 0  layerStack= 0
      
  * Layer (com.example.app/com.example.app.MainActivity#0)
    Region
      + (0, 0, 1080, 2340)
    State
      activeBuffer=[1080x2340:1088, RGBA_8888]
      
      z= 0 layerStack= 0
      
    
  * Layer (StatusBar#0)
    Region
      + (0, 0, 1080, 83)
    State
      activeBuffer=[1080x83:1088, RGBA_8888]
      
      z= 0 layerStack= 0
)
```

每个 Layer 对应一个 `SurfaceControl`。关键信息包括：
- **Layer 名称**：与 `WindowState` 的名称对应，可以与 `dumpsys window` 交叉比对。
- **activeBuffer**：当前活跃的 GraphicBuffer 大小和格式。如果为空 `[0x0:0, UNKNOWN]`，说明该 Layer 没有有效 Buffer。
- **Region**：Layer 在屏幕上的可见区域。

**Buffer 状态（per Layer）**

```
+ BufferQueue (com.example.app/...MainActivity#0)
    mMaxAcquiredBufferCount=1
    mMaxDequeuedBufferCount=2
    mDequeueBufferCannotBlock=0
    Slots:
     [00:0x7f8a001000] state=ACQUIRED
     [01:0x7f8a002000] state=FREE
     [02:0x7f8a003000] state=FREE
    Queue:
     (empty)
```

Buffer 状态说明：
- `FREE`：Buffer 空闲，可被 App 端 `dequeueBuffer()` 获取。
- `DEQUEUED`：Buffer 已被 App 取出，正在绘制。
- `QUEUED`：Buffer 已被 App 提交（`queueBuffer()`），等待 SurfaceFlinger 消费。
- `ACQUIRED`：Buffer 已被 SurfaceFlinger 获取，正在合成或已在屏幕上显示。

| Buffer 状态异常 | 含义 | 可能原因 |
|----------------|------|---------|
| 所有 Slot 都是 DEQUEUED | App 取出了所有 Buffer 但未提交 | App 端绘制卡住或死锁 |
| 所有 Slot 都是 ACQUIRED | SurfaceFlinger 持有所有 Buffer 未释放 | SF 合成卡住或 HWC 驱动异常 |
| 所有 Slot 都是 FREE 但无 QUEUED | App 没有在绘制 | App 端 `performTraversals()` 未执行 |
| Queue 中积压多个 Buffer | Buffer 排队等待消费 | SurfaceFlinger 处理速度跟不上 App 产出速度 |

**HWC 合成信息**

```
h/w composer state:
  Display[0]:
    numHwLayers=5
    Layer 0: com.example.app/...MainActivity
      HWC: DEVICE
    Layer 1: StatusBar
      HWC: DEVICE
    Layer 2: NavigationBar
      HWC: CLIENT
```

- `DEVICE`：该 Layer 由硬件合成器（HWC）直接合成，效率最高。
- `CLIENT`：该 Layer 回退到 GPU 合成（Client composition），消耗 GPU 资源。

> **稳定性架构师视角：** 如果大量 Layer 回退到 `CLIENT` 合成，说明 HWC 无法处理（如 Layer 数量超过 HWC 支持上限、Layer 格式不支持、需要复杂变换）。GPU 合成增加会导致功耗上升和帧率下降。在低端设备上，`CLIENT` 合成过多是卡顿的常见原因。

### 3.3 Surface 泄漏检测

Surface 泄漏表现为：Layer 数量持续增长，且部分 Layer 不对应任何活跃窗口。

```bash
# Step 1: 列出所有 Layer
adb shell dumpsys SurfaceFlinger --list > layers.txt
wc -l layers.txt  # 正常系统应在 30-80 个 Layer

# Step 2: 列出所有窗口
adb shell dumpsys window windows | grep "Window #" > windows.txt

# Step 3: 交叉比对
# Layer 名称中应该能在 windows.txt 中找到对应窗口
# 如果存在大量 Layer 没有对应窗口 → Surface 泄漏

# Step 4: 监控 Layer 数量变化
while true; do
    echo "$(date): $(adb shell dumpsys SurfaceFlinger --list | wc -l) layers"
    sleep 10
done
# 如果 Layer 数量随时间单调递增 → 泄漏确认
```

**内存影响评估：**

```bash
# 查看 SurfaceFlinger 进程的内存占用
adb shell dumpsys meminfo surfaceflinger

# 关注 Graphics 和 EGL mtrack 项
# 每个 1080p RGBA_8888 三缓冲 Layer 占用:
# 1080 × 2340 × 4 bytes × 3 buffers ≈ 30MB
# 10 个泄漏的 Layer → 300MB 显存浪费
```

### 3.4 帧率与合成统计

```bash
# 帧时间统计
adb shell dumpsys SurfaceFlinger --timestats

# 输出示例：
# layerName = com.example.app/...MainActivity
# totalFrames = 1000
# droppedFrames = 15
# averageFPS = 59.2
# ...

# 帧延迟统计（每帧的 present timestamp）
adb shell dumpsys SurfaceFlinger --latency com.example.app/com.example.app.MainActivity#0
```

---

## 4. dumpsys input 中的窗口信息

`dumpsys input` 输出 InputManagerService 和 InputDispatcher 的完整状态。其中的窗口信息是从 WMS 通过 `InputMonitor` 同步过来的——它是 WMS 窗口状态在 Input 侧的"镜像"。

### 4.1 命令

```bash
adb shell dumpsys input > input_dump.txt
```

### 4.2 关键段落

**FocusedApplications（Input 侧的焦点 Application）**

```
FocusedApplications:
  displayId=0, name='ActivityRecord{a1b2c3d u0 com.example.app/.MainActivity t5}',
    dispatchingTimeout=5000ms
```

这是 InputDispatcher 认为的焦点 Application。当有 Key 事件到来但没有焦点窗口时，InputDispatcher 会等待这个 Application 的窗口出现，等待时长为 `dispatchingTimeout`（5000ms）。超时即触发 ANR。

**FocusedWindows（Input 侧的焦点窗口）**

```
FocusedWindows:
  displayId=0, name='e5f6g7h com.example.app/com.example.app.MainActivity'
```

这是 InputDispatcher 认为的焦点窗口。Key 事件会被发送到这个窗口。

**Input Windows（InputDispatcher 知道的所有窗口）**

```
Input windows (
  0: name='e5f6g7h com.example.app/com.example.app.MainActivity',
     id=42, displayId=0, portalToDisplayId=-1,
     paused=false, focusable=true, hasWallpaper=false,
     visible=true, alpha=1.00,
     flags=INPUT_FEATURE_NO_INPUT_CHANNEL: false,
     frame=[0,0][1080,2340],
     touchableRegion=[0,0][1080,2340],
     ownerPid=12345, ownerUid=10100,
     dispatchingTimeout=5000ms
  1: name='StatusBar',
     id=43, displayId=0,
     ...
)
```

Input Windows 列表是 WMS 通过 `InputMonitor.updateInputWindowsLw()` 同步给 InputDispatcher 的。它包含每个窗口的位置、大小、touchableRegion、focusable 属性等。InputDispatcher 用这些信息进行触摸事件的 Hit Test 和 Key 事件的焦点路由。

### 4.3 交叉验证技术：THE BRIDGE

**dumpsys window 和 dumpsys input 必须交叉验证。** 两者各自维护一份焦点状态，理论上应该一致。不一致说明 `InputMonitor` 同步延迟。

```
交叉验证步骤：

Step 1: 获取 WMS 侧焦点
  $ adb shell dumpsys window displays | grep mCurrentFocus
  → mCurrentFocus=Window{e5f6g7h ... com.example.app/.MainActivity}

Step 2: 获取 InputDispatcher 侧焦点
  $ adb shell dumpsys input | grep "FocusedWindows" -A 2
  → name='e5f6g7h com.example.app/com.example.app.MainActivity'

Step 3: 比对
  ✓ 两者一致 → 焦点同步正常
  ✗ WMS 有焦点但 Input 侧无焦点 → InputMonitor 同步延迟
  ✗ WMS 焦点 = WindowA 但 Input 焦点 = WindowB → 焦点更新未传播
```

**不一致的根因分析：**

InputMonitor 的更新依赖 `mGlobalLock`。当 WMS 更新了焦点窗口后，需要通过 `InputMonitor.updateInputWindowsLw()` 将新的窗口列表提交到 InputDispatcher。这个提交通过 `SurfaceControl.Transaction` 完成，是异步的。如果：

1. `mGlobalLock` 被其他操作长时间持有（如 `performSurfacePlacement` 在处理大量窗口），`updateInputWindowsLw()` 被推迟。
2. `SurfaceControl.Transaction.apply()` 被延迟（如 SurfaceFlinger 繁忙），Input 侧的窗口更新也会延迟。

```java
// frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java
void updateInputWindowsLw(boolean force) {
    // 必须在持有 mGlobalLock 的情况下调用
    // 遍历所有窗口，构建 InputWindowHandle 列表
    // 通过 Transaction 提交给 InputDispatcher
    
    // 如果 mGlobalLock 被其他线程持有 → 本次更新被阻塞
    // 导致 InputDispatcher 使用过期的窗口/焦点信息
}
```

> **稳定性架构师视角：** 在排查 "no focused window" ANR 时，**必须同时抓取 `dumpsys window` 和 `dumpsys input`**。如果 `dumpsys window` 显示焦点窗口已就绪，但 `dumpsys input` 的 FocusedWindows 为空或指向旧窗口，就能确认是 InputMonitor 同步延迟。进一步排查需要检查 `traces.txt` 中 `mGlobalLock` 的持有者。

### 4.4 实战：诊断 no-focused-window ANR

```bash
# ANR 发生后，立即执行以下命令（越快越好，避免状态变化）

# 1. WMS 侧焦点
adb shell dumpsys window displays | grep -E "mCurrentFocus|mFocusedApp"
# 输出:
#   mCurrentFocus=Window{aaa com.example.app/.DialogActivity}
#   mFocusedApp=ActivityRecord{bbb com.example.app/.DialogActivity}

# 2. Input 侧焦点
adb shell dumpsys input | grep -E "FocusedApplications|FocusedWindows" -A 2
# 输出:
#   FocusedApplications:
#     displayId=0, name='com.example.app/.DialogActivity'
#   FocusedWindows:
#     <none>   ← 关键！Input 侧没有焦点窗口

# 3. 结论
# WMS 已计算出焦点窗口 = DialogActivity
# 但 InputDispatcher 的焦点窗口 = <none>
# → InputMonitor 同步延迟
# → 需要检查 mGlobalLock 在 ANR 时刻的持有者

# 4. 检查锁竞争（从 traces.txt）
adb pull /data/anr/traces.txt
# 搜索 "mGlobalLock" 找到锁持有者线程栈
```

---

## 5. Systrace/Perfetto 中的窗口与 Surface 分析

Systrace（已逐步被 Perfetto 取代）是分析 Window 系统**时序问题**的主力工具。与 `dumpsys` 提供的"快照"不同，Systrace/Perfetto 提供的是"影片"——完整的操作时序。

### 5.1 相关 Trace 分类

```bash
# Systrace 采集（旧版，仍可用）
python systrace.py -t 5 -b 32768 wm view gfx input sf am -o trace.html

# Perfetto 采集（推荐）
# 配置文件中启用以下 atrace 分类：
# wm      - WindowManager 操作
# view    - View 系统（performTraversals, measure, layout, draw）
# gfx     - 图形系统（dequeueBuffer, queueBuffer, 硬件加速）
# input   - Input 事件分发
# sf      - SurfaceFlinger
# am      - ActivityManager
```

| Trace 分类 | 涵盖的操作 | 典型 Trace 事件名 |
|-----------|-----------|------------------|
| `wm` | WMS 窗口操作 | `performSurfacePlacement`, `relayoutWindow`, `addWindow`, `removeWindow`, `updateFocusedWindow` |
| `view` | App 端 View 操作 | `performTraversals`, `measure`, `layout`, `draw`, `Choreographer#doFrame` |
| `gfx` | 图形渲染 | `dequeueBuffer`, `queueBuffer`, `eglSwapBuffers`, `RenderThread::draw` |
| `input` | Input 事件 | `dispatchOnce`, `deliverInputEvent`, `finishInputEvent` |
| `sf` | SurfaceFlinger 合成 | `onMessageReceived`, `latchBuffer`, `composite`, `postComposition` |
| `am` | Activity 生命周期 | `activityStart`, `activityResume`, `activityPause`, `activityDestroy` |

### 5.2 关键 Trace 事件解读

**WMS 侧关键 Trace 事件：**

```
┌─────────────────────────────────────────────────────────────────────┐
│  system_server: android.display 线程                                │
│                                                                     │
│  ├── performSurfacePlacement                                       │
│  │    整个 WMS 布局计算周期。耗时 > 10ms 说明窗口数量过多或          │
│  │    布局逻辑复杂。如果出现多次循环，搜索 "LOOP" 标记。             │
│  │                                                                  │
│  ├── relayoutWindow: com.example.app/...MainActivity               │
│  │    单个窗口的 relayout 操作。包含 Surface 创建（如果是首次）。     │
│  │    耗时 > 5ms 说明 Surface 创建慢或 SurfaceFlinger 响应慢。       │
│  │                                                                  │
│  ├── addWindow: com.example.app/...MainActivity                    │
│  │    窗口添加操作。从 Token 校验到 WindowState 创建到 InputChannel   │
│  │    注册。耗时 > 3ms 说明异常。                                    │
│  │                                                                  │
│  └── updateFocusedWindow                                           │
│       焦点更新。如果此 Trace 与 addWindow 之间间隔过长，说明           │
│       焦点更新被推迟——这是 ANR 的潜在信号。                          │
└─────────────────────────────────────────────────────────────────────┘
```

**SurfaceFlinger 侧关键 Trace 事件：**

```
┌─────────────────────────────────────────────────────────────────────┐
│  surfaceflinger 主线程                                              │
│                                                                     │
│  ├── onMessageReceived (INVALIDATE)                                │
│  │    SurfaceFlinger 的一次合成周期开始。                             │
│  │                                                                  │
│  ├── latchBuffer                                                   │
│  │    从 BufferQueue 获取 App 提交的新帧。如果某个 Layer 长时间        │
│  │    没有 latchBuffer，说明 App 没有在绘制。                         │
│  │                                                                  │
│  ├── composite (HWC/GPU)                                           │
│  │    执行合成。CLIENT 合成（GPU）比 DEVICE 合成（HWC）慢 2-5 倍。    │
│  │                                                                  │
│  └── postComposition                                               │
│       合成完成后的后处理（帧统计、fence 等待）。                      │
└─────────────────────────────────────────────────────────────────────┘
```

**BufferQueue 关键事件：**

```
App 端:
  dequeueBuffer → [获取空闲 Buffer] → draw → queueBuffer → [提交到 BufferQueue]

SurfaceFlinger 端:
  acquireBuffer → [从 BufferQueue 获取新帧] → composite → releaseBuffer → [归还 Buffer]

如果 dequeueBuffer 耗时 > 5ms:
  → BufferQueue 中没有空闲 Buffer
  → SurfaceFlinger 还没释放旧 Buffer
  → 可能是 SurfaceFlinger 合成慢或 HWC fence 未信号
```

### 5.3 TTID/TTFD 测量

在 Perfetto 中，启动性能的关键标记：

```
# TTID: Time To Initial Display
# 在 Perfetto 中搜索 "Displayed" 或 android.app.startup slice
# 时序:
#   activityStart → addWindow → relayoutWindow → performTraversals → draw
#   → reportDrawn → "Displayed com.example.app/.MainActivity: +Xms"
#
# Xms 即为 TTID

# TTFD: Time To Full Display
# 在 Perfetto 中搜索 "Fully drawn" 或 reportFullyDrawn slice
# App 调用 Activity.reportFullyDrawn() 后记录
# 时序:
#   Displayed (TTID) → ... 异步加载 ... → reportFullyDrawn
#   → "Fully drawn com.example.app/.MainActivity: +Yms"
#
# Yms 即为 TTFD
```

### 5.4 端到端窗口显示延迟测量

从 Activity 启动到首帧上屏的全链路：

```
Activity.onCreate()  [am tag]
    ↓
addView()            [view tag]
    ↓ Binder IPC
addWindow()          [wm tag]
    ↓
relayoutWindow()     [wm tag]    ← Surface 创建
    ↓ 返回
performTraversals()  [view tag]
  ├── measure        [view tag]
  ├── layout         [view tag]
  └── draw           [view tag]
    ↓
queueBuffer          [gfx tag]   ← 帧提交
    ↓
latchBuffer          [sf tag]    ← SF 获取帧
    ↓
composite            [sf tag]    ← 合成
    ↓
Display              [sf tag]    ← 上屏

总延迟 = Display 时间 - Activity.onCreate() 时间
```

### 5.5 实战排查模式

**模式一：找布局循环**

在 Perfetto 中搜索 `performSurfacePlacement`。如果在一个时间段内看到 6 次连续的 `performSurfacePlacement`（达到 WMS 的循环上限），说明存在布局循环——某个窗口的布局变化触发了其他窗口的重新布局，循环往复。

```
时间线:
  [performSurfacePlacement] [performSurfacePlacement] [performSurfacePlacement]
  [performSurfacePlacement] [performSurfacePlacement] [performSurfacePlacement]
  ← 6 次，达到上限，强制跳出 →

根因: 通常是 IME 弹出/隐藏与 adjustResize 的窗口之间的循环依赖
```

**模式二：找合成 Jank**

在 Perfetto 中查看 SurfaceFlinger 主线程。正常情况下每个 VSYNC 周期应有一次 `composite`。如果某次 `composite` 耗时超过 VSYNC 周期（16.6ms@60Hz），后续帧会被推迟——这就是 Jank。

```
正常:
  |composite 8ms| |composite 7ms| |composite 9ms|
  |←── 16.6ms ──→|←── 16.6ms ──→|←── 16.6ms ──→|

Jank:
  |composite 8ms| |    composite 25ms     | |composite 7ms|
  |←── 16.6ms ──→|←── 16.6ms ──→|← missed→|←── 16.6ms ──→|
                                   ↑ 这帧被跳过
```

**模式三：找 relayoutWindow 慢**

搜索 `relayoutWindow` trace 事件，检查其耗时。正常情况下首次 relayout（包含 Surface 创建）耗时 5-15ms，后续 relayout 耗时 1-3ms。如果首次 relayout 超过 30ms，排查：
1. SurfaceFlinger 是否繁忙（检查 `createLayer` 的延迟）
2. `mGlobalLock` 是否被竞争（检查 WMS 线程是否有锁等待）

---

## 6. WindowManager Trace（winscope）

### 6.1 概述

Android 11 开始，WMS 支持录制窗口状态 Trace（WindowManager Trace）。它在每次 `SurfaceControl.Transaction` 提交时捕获完整的 `WindowContainer` 树状态，形成一系列快照。配合 winscope 工具回放，可以逐帧查看窗口层级变化。

这是排查**间歇性窗口问题**（如偶发黑屏、焦点偶发丢失、窗口层级偶发错乱）的终极工具。

### 6.2 录制与获取

```bash
# 开始录制
adb shell wm trace start

# 复现问题...

# 停止录制
adb shell wm trace stop

# 获取 trace 文件
adb pull /data/misc/wmtrace/wm_trace.winscope

# 也可以同时录制 SurfaceFlinger transaction trace
adb shell su root service call SurfaceFlinger 1025 i32 1  # 开始
adb shell su root service call SurfaceFlinger 1025 i32 0  # 停止
adb pull /data/misc/wmtrace/layers_trace.winscope
```

### 6.3 Winscope 工具使用

Winscope 是一个 Web 工具，用于可视化 WindowManager Trace：

- **在线版**：https://winscope.googlesource.com/（或 AOSP 源码中 `development/tools/winscope/`）
- **使用方式**：在浏览器中打开 Winscope → 拖入 `.winscope` 文件 → 可视化回放

Winscope 的核心功能：

| 功能 | 说明 | 排查场景 |
|------|------|---------|
| 层级树可视化 | 以树形结构展示 WindowContainer 层级 | 窗口层级异常排查 |
| 属性面板 | 点击任意节点查看其所有属性 | 检查 isVisible、mHasSurface 等 |
| 时间线导航 | 逐帧前进/后退 | 找到问题发生的精确时刻 |
| Diff 视图 | 对比相邻两帧的差异 | 发现哪个属性在哪一帧变化 |
| 搜索/过滤 | 按名称或属性搜索窗口 | 快速定位目标窗口 |

### 6.4 Trace 内容

WM Trace 在每次 Transaction 提交时记录完整的 WindowContainer 树，包括：

```
每帧快照包含:
├── RootWindowContainer
│    └── DisplayContent (displayId=0)
│         ├── 所有 TaskDisplayArea
│         │    └── 所有 Task
│         │         └── 所有 ActivityRecord
│         │              └── 所有 WindowState
│         │                   ├── mHasSurface
│         │                   ├── isVisible
│         │                   ├── isReadyForDisplay
│         │                   ├── mAttrs (type, flags)
│         │                   ├── mRequestedWidth/Height
│         │                   ├── mFrame
│         │                   └── ...
│         ├── 所有系统窗口容器
│         └── ImeContainer
├── mCurrentFocus
├── mFocusedApp
└── mAppTransition state
```

### 6.5 焦点调试实战

使用 WM Trace 排查焦点丢失的步骤：

```
Step 1: 在 Winscope 中搜索 "mCurrentFocus"
Step 2: 在时间线上拖动，观察 mCurrentFocus 的变化
Step 3: 找到 mCurrentFocus 从 "有值" 变为 "null" 的那一帧
Step 4: 检查该帧中发生了什么变化（Diff 视图）
        → 可能是某个窗口的 isVisible 从 true 变为 false
        → 或某个窗口被 removeWindow
        → 或某个窗口设置了 FLAG_NOT_FOCUSABLE
Step 5: 根据变化的窗口名称定位到业务代码
```

### 6.6 实战：诊断间歇性黑屏

**场景：** Activity 切换过程中偶发黑屏（1% 复现率），持续约 500ms 后恢复。

```
Step 1: 开启 WM Trace，反复执行 Activity 切换直到黑屏复现
Step 2: 在 Winscope 中加载 trace
Step 3: 在时间线上找到黑屏时刻（新 Activity 的窗口 isVisible 应为 true）
Step 4: 检查黑屏帧的窗口状态:

  正常帧 (T=100):
    ActivityRecord (com.example.app/.ActivityB)
      WindowState: mHasSurface=true, isVisible=true ✓

  黑屏帧 (T=120):
    ActivityRecord (com.example.app/.ActivityB)
      WindowState: mHasSurface=true, isVisible=true
      但 Surface 的 mShown=false ← 异常！

  恢复帧 (T=150):
    ActivityRecord (com.example.app/.ActivityB)
      WindowState: mHasSurface=true, isVisible=true, Surface mShown=true ✓

Step 5: 分析 Diff:
  T=100 → T=120: Surface mShown 从 true 变为 false
  → 可能原因: 转场动画结束时 Surface 被短暂隐藏
  → 进一步检查: mAppTransition 状态在 T=120 附近的变化

Step 6: 根因:
  转场动画的 Leash Surface 在动画结束时被移除，
  但新窗口的 Surface show 操作被延迟了一个 Transaction 周期。
  → 在动画结束与窗口 Surface show 之间存在一帧的间隙 → 黑屏闪烁。
```

---

## 7. 监控与治理最佳实践

从"能查"（掌握工具）到"能治"（解决问题）到"能防"（建立监控），这是稳定性工程的三个层次。本节介绍如何建立 Window 系统的监控与治理体系。

### 7.1 Window 泄漏检测

```
┌─────────────────────────────────────────────────────────────┐
│  监控项: Window 泄漏检测                                     │
│                                                              │
│  监控指标: 每个 Activity 实例的窗口数量                        │
│                                                              │
│  采集方式:                                                    │
│    App 端: WindowManagerGlobal.mViews.size()                 │
│    系统端: dumpsys window windows | grep mOwnerUid           │
│                                                              │
│  告警阈值:                                                    │
│    单个 Activity 窗口数 > 5 → Warning                        │
│    单个进程窗口数 > 30 → Critical                            │
│    窗口数持续增长（每分钟 +2 以上）→ Critical                 │
│                                                              │
│  治理方案:                                                    │
│    1. Activity.onDestroy() 中遍历 dismiss 所有 Dialog         │
│    2. 使用 Lifecycle-aware Dialog 封装                        │
│    3. 框架层: hook WindowManagerGlobal.addView() 监控增长     │
└─────────────────────────────────────────────────────────────┘
```

实现示例（App 端监控）：

```java
// frameworks/base/core/java/android/view/WindowManagerGlobal.java
// 可通过反射或字节码插桩监控 mViews 列表
public class WindowLeakMonitor {
    private static final int WINDOW_COUNT_THRESHOLD = 5;

    public static void checkLeaks(Activity activity) {
        try {
            WindowManagerGlobal wmg = WindowManagerGlobal.getInstance();
            // 反射获取 mViews
            Field mViewsField = WindowManagerGlobal.class.getDeclaredField("mViews");
            mViewsField.setAccessible(true);
            ArrayList<View> views = (ArrayList<View>) mViewsField.get(wmg);

            int count = 0;
            for (View v : views) {
                if (v.getContext() == activity) {
                    count++;
                }
            }

            if (count > WINDOW_COUNT_THRESHOLD) {
                // 上报告警: Activity 持有过多窗口
                reportWindowLeak(activity.getClass().getName(), count);
            }
        } catch (Exception e) {
            // 反射失败，降级处理
        }
    }
}
```

### 7.2 黑屏率监控

```
┌─────────────────────────────────────────────────────────────┐
│  监控项: 黑屏率                                              │
│                                                              │
│  监控指标:                                                    │
│    1. mHasSurface=false 但窗口应该可见的持续时间              │
│    2. SurfaceFlinger 帧统计中连续空帧数                      │
│    3. 截图分析黑屏比例                                        │
│                                                              │
│  采集方式:                                                    │
│    App 端: 监控 ViewRootImpl 的 Surface 有效性               │
│            Window.Callback 中检查 onWindowFocusChanged        │
│    系统端: dumpsys SurfaceFlinger --timestats 分析帧间隔      │
│                                                              │
│  告警阈值:                                                    │
│    窗口 Surface 无效时间 > 500ms → Warning                   │
│    连续 3 帧无新 Buffer → Warning                            │
│    黑屏持续 > 2s → Critical                                  │
│                                                              │
│  治理方案:                                                    │
│    1. Surface 无效时主动 requestLayout() 触发重试             │
│    2. 配置变更时使用 Retained Fragment 保持状态               │
│    3. 启动窗口（SplashScreen）确保过渡期有内容显示            │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 TTID/TTFD 统计与告警

```
┌─────────────────────────────────────────────────────────────┐
│  监控项: TTID/TTFD 启动性能                                  │
│                                                              │
│  监控指标:                                                    │
│    TTID: Activity 启动到首帧显示的耗时                        │
│    TTFD: Activity 启动到内容完全就绪的耗时                    │
│                                                              │
│  采集方式:                                                    │
│    系统: ActivityMetricsLogger（Android 内置）                │
│          logcat 中 "Displayed" / "Fully drawn" 日志           │
│    App:  Perfetto android.app.startup slice                  │
│          自定义埋点 (onCreate → 首帧 Callback)                │
│                                                              │
│  告警阈值:                                                    │
│    TTID P50 > 500ms → Warning                                │
│    TTID P95 > 2000ms → Critical                              │
│    TTFD P50 > 1500ms → Warning                               │
│    TTFD P95 > 5000ms → Critical                              │
│                                                              │
│  治理方案:                                                    │
│    1. 减少 onCreate 中同步初始化（延迟到首帧后）              │
│    2. 减少首帧 View 层级复杂度                               │
│    3. 预创建 Activity 窗口（Starting Window / SplashScreen）  │
│    4. 异步加载数据，先展示骨架屏                              │
└─────────────────────────────────────────────────────────────┘
```

采集 TTID 的参考实现：

```java
public class TTIDTracker {
    private long mStartTime;

    public void onActivityCreate(Activity activity) {
        mStartTime = SystemClock.uptimeMillis();

        activity.getWindow().getDecorView().getViewTreeObserver()
            .addOnPreDrawListener(new ViewTreeObserver.OnPreDrawListener() {
                @Override
                public boolean onPreDraw() {
                    long ttid = SystemClock.uptimeMillis() - mStartTime;
                    reportTTID(activity.getClass().getSimpleName(), ttid);
                    activity.getWindow().getDecorView().getViewTreeObserver()
                        .removeOnPreDrawListener(this);
                    return true;
                }
            });
    }
}
```

### 7.4 无焦点窗口 ANR 率监控

```
┌─────────────────────────────────────────────────────────────┐
│  监控项: 无焦点窗口 ANR                                      │
│                                                              │
│  监控指标: "Input dispatching timed out" 中包含               │
│           "no focused window" 的 ANR 次数和比例               │
│                                                              │
│  采集方式:                                                    │
│    解析 ANR 日志中的 reason 字段                              │
│    关键模式: "Waiting because no window has focus"            │
│    或: "reason=noFocusedWindow"                              │
│                                                              │
│  告警阈值:                                                    │
│    no-focused-window ANR 占总 ANR 比例 > 30% → Warning       │
│    绝对数量: 日均 > 50 次 → Critical                         │
│                                                              │
│  治理方案:                                                    │
│    1. 优化 Activity 启动速度（减少 TTID）                     │
│    2. 减少 mGlobalLock 竞争（减少窗口数量和动画复杂度）       │
│    3. 避免在 Activity 切换时执行耗时操作                      │
│    4. 参考 [07-WMS 与 Input 焦点管理](07-WMS与Input焦点管理.md) │
│       中的焦点异常四种场景逐一排查                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.5 窗口创建耗时统计

```
┌─────────────────────────────────────────────────────────────┐
│  监控项: 窗口创建耗时                                        │
│                                                              │
│  监控指标:                                                    │
│    addWindow 耗时（WMS 侧）                                  │
│    relayoutWindow 耗时（含 Surface 创建）                    │
│    performTraversals 耗时（App 侧）                          │
│                                                              │
│  采集方式:                                                    │
│    Perfetto (wm + view tag)                                  │
│    App 端: ViewRootImpl 插桩                                  │
│    系统端: WMS 中对 addWindow/relayoutWindow 计时             │
│                                                              │
│  告警阈值:                                                    │
│    addWindow P95 > 10ms → Warning                            │
│    relayoutWindow（首次）P95 > 20ms → Warning                │
│    performTraversals P95 > 30ms → Warning                    │
│                                                              │
│  治理方案:                                                    │
│    addWindow 慢: 检查窗口数量（窗口越多 assignWindowLayers    │
│                  越慢），检查 mGlobalLock 竞争                │
│    relayout 慢: 检查 Surface 创建（SurfaceFlinger 响应慢）    │
│    traversals 慢: 检查 View 树复杂度、减少嵌套层级            │
└─────────────────────────────────────────────────────────────┘
```

### 7.6 Surface 内存预警

```
┌─────────────────────────────────────────────────────────────┐
│  监控项: Surface 内存占用                                    │
│                                                              │
│  监控指标:                                                    │
│    SurfaceFlinger 进程的 Graphics 内存                       │
│    Layer 数量                                                │
│                                                              │
│  采集方式:                                                    │
│    dumpsys meminfo surfaceflinger (Graphics 段)              │
│    dumpsys SurfaceFlinger --list | wc -l                     │
│                                                              │
│  告警阈值:                                                    │
│    Graphics 内存 > 500MB → Warning                           │
│    Graphics 内存 > 800MB → Critical                          │
│    Layer 数量 > 100 → Warning                                │
│    Layer 数量 > 200 → Critical                               │
│    Layer 数量持续增长 → Critical（泄漏）                     │
│                                                              │
│  治理方案:                                                    │
│    1. 检查 SurfaceView/TextureView 是否正确释放              │
│    2. 检查 WindowState 清理是否完整（DeathRecipient 回调）   │
│    3. 定期 dumpsys SurfaceFlinger --list 对比 Layer 变化     │
└─────────────────────────────────────────────────────────────┘
```

### 7.7 WMS 锁等待时间监控

```
┌─────────────────────────────────────────────────────────────┐
│  监控项: mGlobalLock 等待时间                                │
│                                                              │
│  监控指标:                                                    │
│    Binder 线程获取 mGlobalLock 的等待时间                    │
│    android.display 线程持有 mGlobalLock 的时间               │
│                                                              │
│  采集方式:                                                    │
│    Perfetto: 搜索 "Lock contention" 或 monitor contention    │
│    WMS 插桩: 在 synchronized(mGlobalLock) 前后计时            │
│    系统端: Watchdog 检测（阈值 30s / 60s）                    │
│                                                              │
│  告警阈值:                                                    │
│    P95 锁等待时间 > 50ms → Warning                           │
│    P99 锁等待时间 > 200ms → Critical                         │
│    单次锁持有时间 > 500ms → Critical                         │
│    Watchdog 触发 → Fatal                                     │
│                                                              │
│  治理方案:                                                    │
│    1. 减少窗口数量（每个窗口的 add/remove/relayout 都竞争锁） │
│    2. 优化 performSurfacePlacement（减少循环次数）            │
│    3. 减少转场动画复杂度                                      │
│    4. 避免在持有 mGlobalLock 时做耗时操作（如 Binder 回调）   │
│    5. 参考 [10-WMS 锁竞争与 Watchdog](10-WMS锁竞争与Watchdog.md) │
└─────────────────────────────────────────────────────────────┘
```

### 7.8 监控体系总览

| # | 监控项 | 采集层 | 关键指标 | Warning 阈值 | Critical 阈值 | 对应系列文章 |
|---|--------|--------|---------|-------------|--------------|-------------|
| 1 | Window 泄漏 | App/WMS | 窗口数量/增长率 | 单 Activity > 5 | 进程 > 30 | [02-创建与添加](02-Window的创建与添加.md) |
| 2 | 黑屏率 | App/SF | Surface 无效时长 | > 500ms | > 2s | [05-Surface 管理](05-Surface管理与SurfaceFlinger交互.md) |
| 3 | TTID/TTFD | App/System | 启动耗时 | P95 > 2s | P95 > 5s | [08-显示性能](08-窗口显示性能TTID与TTFD.md) |
| 4 | 无焦点 ANR | System | ANR 比例 | > 30% 占比 | 日均 > 50 | [07-焦点管理](07-WMS与Input焦点管理.md) |
| 5 | 窗口创建耗时 | WMS | add/relayout 耗时 | P95 > 20ms | P95 > 50ms | [02-创建与添加](02-Window的创建与添加.md) |
| 6 | Surface 内存 | SF | Graphics 内存/Layer 数 | > 500MB / > 100 | > 800MB / > 200 | [05-Surface 管理](05-Surface管理与SurfaceFlinger交互.md) |
| 7 | WMS 锁等待 | WMS | 锁等待/持有时间 | P99 > 200ms | > 500ms / Watchdog | [10-锁竞争](10-WMS锁竞争与Watchdog.md) |

---

## 8. 实战案例

### Case 1：dumpsys window + dumpsys input 交叉验证——诊断间歇性 Input ANR

**现象**

线上某机型报告间歇性 ANR，ANR 信息为 `Input dispatching timed out (Waiting because no window has focus but there is a focused application)`。复现率约 3%，发生在从 Activity A 弹出 Dialog 的过程中。

**排查过程**

**第一步：获取 ANR 时的系统状态**

ANR 发生后立即抓取 dump（通过后台脚本自动触发）：

```bash
# WMS 侧
adb shell dumpsys window displays > wms_dump.txt
adb shell dumpsys window windows >> wms_dump.txt

# Input 侧
adb shell dumpsys input > input_dump.txt
```

**第二步：分析 WMS 侧焦点**

```
# wms_dump.txt 中:
mCurrentFocus=Window{aaa111 u0 com.example.app/com.example.app.MyDialog}
mFocusedApp=ActivityRecord{bbb222 u0 com.example.app/.ActivityA t5}
```

WMS 认为焦点窗口是 `MyDialog`，焦点 Application 是 `ActivityA`。两者一致（Dialog 属于 ActivityA）。

**第三步：分析 Input 侧焦点**

```
# input_dump.txt 中:
FocusedApplications:
  displayId=0, name='ActivityRecord{bbb222 u0 com.example.app/.ActivityA t5}'

FocusedWindows:
  <none>    ← 关键！Input 侧焦点窗口为空！
```

**交叉比对结果：**

| 维度 | WMS 侧 | Input 侧 | 一致？ |
|------|--------|----------|--------|
| FocusedApp | ActivityA | ActivityA | 一致 |
| FocusedWindow | MyDialog | `<none>` | **不一致** |

WMS 已经计算出焦点窗口为 `MyDialog`，但 InputDispatcher 还没收到更新。

**第四步：检查 InputMonitor 同步延迟原因**

分析 ANR 时刻的 `traces.txt`：

```
"Binder:system_server/1234" tid=1234
  - waiting to lock <0x12345678> (a com.android.server.wm.WindowManagerGlobalLock)
  - held by thread "android.display" tid=15

"android.display" tid=15
  at com.android.server.wm.WindowSurfacePlacer.performSurfacePlacement()
  at com.android.server.wm.WindowAnimator.animate()
  at com.android.server.wm.WindowAnimator.lambda$new$0()
  ...
```

**根因：**

1. 用户操作触发了 Dialog 的显示（`Dialog.show()` → `addView()` → `addWindow()`）。
2. `addWindow()` 成功创建了 `WindowState`，WMS 计算出新的焦点窗口为 `MyDialog`。
3. 焦点更新需要通过 `InputMonitor.updateInputWindowsLw()` 同步到 InputDispatcher。
4. 但此时 `android.display` 线程正在执行 `performSurfacePlacement()`（由窗口动画触发），长时间持有 `mGlobalLock`。
5. `updateInputWindowsLw()` 需要在 `mGlobalLock` 内执行，被阻塞。
6. 在阻塞期间，用户按了 Key（如返回键），InputDispatcher 发现没有焦点窗口，开始等待。
7. 等待 5000ms 后超时 → ANR。

```
时间线:
T=0ms      Dialog.show() → addView() → Binder → WMS.addWindow()
T=5ms      WMS: WindowState 创建成功, mCurrentFocus = MyDialog
T=5ms      WMS: 触发 updateFocusedWindowLocked()
T=5ms      WMS: 需要调用 InputMonitor.updateInputWindowsLw()
T=5ms      但 mGlobalLock 被 android.display 线程持有（动画中）
           → updateInputWindowsLw() 被阻塞

T=100ms    用户按返回键
T=100ms    InputDispatcher: 收到 KEY_BACK
T=100ms    InputDispatcher: FocusedWindow = <none> (还没更新!)
T=100ms    InputDispatcher: "Waiting because no window has focus..."
           → 开始 5000ms 等待

T=3000ms   android.display 线程完成动画,释放 mGlobalLock
T=3001ms   InputMonitor.updateInputWindowsLw() 执行
T=3002ms   InputDispatcher: FocusedWindow = MyDialog (更新了!)
T=3003ms   InputDispatcher: 分发 KEY_BACK 到 MyDialog (成功)

           但 ANR 计时器已经运行了 2903ms...
           如果在 T=5100ms 之前没有分发完成 → ANR

T=5100ms   ANR! (100ms 延迟 + 5000ms 等待)
```

**修复方案：**

1. **App 层**：减少 Dialog 弹出时的动画复杂度，降低 `performSurfacePlacement` 耗时。
2. **系统层**：优化 `performSurfacePlacement()` 中的布局计算，减少持锁时间。确保焦点更新路径的优先级高于布局计算。
3. **监控层**：对 `mGlobalLock` 持有时间 > 100ms 的情况上报告警，作为 ANR 的前兆信号。

> **稳定性架构师视角：** 这个案例完美展示了 `dumpsys window` + `dumpsys input` 交叉验证的价值。仅看 `dumpsys window` 会认为焦点正常（MyDialog 已就位），仅看 `dumpsys input` 只知道焦点为空但不知为什么。两者结合才能精确定位到 InputMonitor 同步延迟这个根因。

### Case 2：winscope 回放——定位 Activity 转场黑屏

**现象**

某 App 从 Activity A 切换到 Activity B 时，偶发 300-500ms 的黑屏闪烁。在高端设备上几乎不出现，在中端设备上复现率约 5%。

**排查过程**

**第一步：录制 WM Trace**

```bash
adb shell wm trace start
# 反复执行 A → B 切换约 50 次
adb shell wm trace stop
adb pull /data/misc/wmtrace/wm_trace.winscope
```

**第二步：在 Winscope 中回放**

在 Winscope 中加载 trace，使用搜索功能定位 Activity B 的窗口。在时间线上逐帧检查窗口状态变化。

**第三步：定位异常帧**

在某次切换中，发现以下状态序列：

```
帧 #1234 (T=0ms, 切换开始):
  ActivityRecord(A): WindowState → isVisible=true, mHasSurface=true
  ActivityRecord(B): (不存在)
  mAppTransition: state=READY, transit=TRANSIT_OPEN

帧 #1240 (T=50ms):
  ActivityRecord(A): WindowState → isVisible=true, mHasSurface=true
  ActivityRecord(B): WindowState → isVisible=false, mHasSurface=false  ← 窗口已创建但还没 Surface
  mAppTransition: state=RUNNING

帧 #1255 (T=120ms):
  ActivityRecord(A): WindowState → isVisible=false, mHasSurface=true  ← A 被标记为不可见
  ActivityRecord(B): WindowState → isVisible=true, mHasSurface=false  ← B 可见但没 Surface!
  mAppTransition: state=IDLE
  ← 这就是黑屏帧! A 已隐藏,B 还没有 Surface

帧 #1260 (T=180ms):
  ActivityRecord(A): WindowState → isVisible=false, mHasSurface=false
  ActivityRecord(B): WindowState → isVisible=true, mHasSurface=true  ← B 的 Surface 就绪
  ← 黑屏结束

黑屏时长 = 180ms - 120ms = 60ms (本次较短)
极端情况下 Surface 创建更慢 → 黑屏时长可达 300-500ms
```

**第四步：根因分析**

```
正常流程:
  A 隐藏时间 = B 的 Surface 就绪时间 (原子切换)
  → 用户看不到黑屏

异常流程:
  A 隐藏时间 < B 的 Surface 就绪时间
  → A 已经不可见, 但 B 还没有可显示的内容
  → 屏幕上没有任何有效 Layer → 黑屏

根因: 转场动画结束时 (mAppTransition → IDLE),
      WMS 立即将 A 标记为 isVisible=false,
      但 B 的 Surface 创建 (relayoutWindow → createSurfaceLocked)
      在中端设备上因 SurfaceFlinger 响应慢而延迟。
```

**修复方案：**

1. **系统层**（AOSP 已在后续版本优化）：转场动画结束时不立即隐藏旧窗口，而是等到新窗口的 `isReadyForDisplay()` 返回 true 后再隐藏旧窗口。
2. **App 层**：确保 Activity B 的首帧尽可能简单，减少 Surface 创建到首帧绘制的时间差。使用 Starting Window（SplashScreen）作为过渡。

---

## 总结

### 诊断工具链总览表

| 工具 | 输出类型 | 适用场景 | 核心命令 |
|------|---------|---------|---------|
| `dumpsys window` | 快照 | 窗口状态、焦点、层级、策略 | `adb shell dumpsys window [subcommand]` |
| `dumpsys SurfaceFlinger` | 快照 | Layer/Buffer/合成/帧统计 | `adb shell dumpsys SurfaceFlinger [--list\|--timestats]` |
| `dumpsys input` | 快照 | Input 侧焦点与窗口验证 | `adb shell dumpsys input` |
| Perfetto/Systrace | 时序 | 端到端时序分析、性能排查 | Perfetto config 或 `systrace.py` |
| WM Trace (winscope) | 录制回放 | 间歇性窗口问题、状态变迁 | `adb shell wm trace start/stop` |
| ANR traces | 线程栈 | ANR/Watchdog 根因分析 | `adb pull /data/anr/traces.txt` |
| `dumpsys meminfo` | 快照 | 内存/显存泄漏 | `adb shell dumpsys meminfo surfaceflinger` |

### 从"能查"到"能治"到"能防"

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Level 1: 能查 (Diagnose)                                                 │
│    掌握 dumpsys window / SurfaceFlinger / input / Perfetto / winscope     │
│    能在问题发生后快速定位根因层                                            │
│    目标: 5 分钟内确认问题属于 App 层 / WMS 层 / Surface 层 / Input 层     │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│  Level 2: 能治 (Fix)                                                      │
│    理解 Window 系统的核心机制和风险点                                      │
│    能根据根因制定修复方案                                                  │
│    目标: 每类问题有标准化的修复路径                                        │
│    参考: 本系列 01-10 篇的核心机制与实战案例                              │
│                                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│  Level 3: 能防 (Prevent)                                                  │
│    建立 7 项监控指标（泄漏/黑屏/TTID/ANR/耗时/内存/锁等待）              │
│    问题在影响用户之前被监控系统发现并告警                                  │
│    目标: 将 Window 稳定性问题从"被动救火"转为"主动防御"                  │
└────────────────────────────────────────────────────────────────────────────┘
```

作为稳定性架构师，排查 Window 系统问题时需要记住以下关键点：

1. **dumpsys window + dumpsys input 交叉验证是焦点 ANR 排查的标准动作。** 两者各自维护焦点信息，不一致就能锁定 InputMonitor 同步延迟。

2. **dumpsys SurfaceFlinger 是 Surface 问题的终审法庭。** Layer 数量、Buffer 状态、合成方式、帧统计——Surface 相关的一切问题都能从这里找到线索。Layer 数量持续增长是泄漏的确定信号。

3. **Perfetto 是时序问题的唯一武器。** `dumpsys` 只能提供快照，无法回答"先后顺序"和"耗时分布"。性能问题和竞态问题必须用 Perfetto 分析。

4. **winscope 是间歇性问题的终极手段。** 对于 1% 复现率的窗口状态异常，只有录制 WM Trace 并逐帧回放才能找到确切的异常时刻和状态变迁。

5. **监控体系的七项指标覆盖了 Window 系统的全部风险面。** 从 App 层的窗口泄漏到 SurfaceFlinger 层的显存增长，从性能指标（TTID/TTFD）到稳定性指标（ANR/Watchdog），建立完整的监控闭环。

---

## 附录：核心源码路径索引

本篇涉及的核心源码文件一览：

| 文件名 | 完整路径 | 说明 |
|--------|---------|------|
| WindowManagerService.java | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | WMS 主入口，dumpsys window 的输出源 |
| WindowState.java | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | 窗口核心抽象，承载 mHasSurface 等关键状态 |
| InputMonitor.java | `frameworks/base/services/core/java/com/android/server/wm/InputMonitor.java` | WMS→InputDispatcher 窗口信息同步 |
| WindowSurfacePlacer.java | `frameworks/base/services/core/java/com/android/server/wm/WindowSurfacePlacer.java` | 全局布局计算，Perfetto 中 `performSurfacePlacement` 的来源 |
| DisplayContent.java | `frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java` | 焦点计算 `findFocusedWindow()` |
| WindowContainer.java | `frameworks/base/services/core/java/com/android/server/wm/WindowContainer.java` | 窗口容器层级基类，winscope 树的数据来源 |
| DisplayPolicy.java | `frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java` | SystemBar/IME 策略，dumpsys window policy 的来源 |
| WindowManagerGlobal.java | `frameworks/base/core/java/android/view/WindowManagerGlobal.java` | App 端窗口管理，窗口泄漏检测的切入点 |
| ViewRootImpl.java | `frameworks/base/core/java/android/view/ViewRootImpl.java` | performTraversals / relayoutWindow 的 App 端入口 |
| ActivityRecord.java | `frameworks/base/services/core/java/com/android/server/wm/ActivityRecord.java` | TTID/TTFD 统计的系统端入口 |
| AppTransition.java | `frameworks/base/services/core/java/com/android/server/wm/AppTransition.java` | 转场动画状态机 |
| WindowAnimator.java | `frameworks/base/services/core/java/com/android/server/wm/WindowAnimator.java` | 窗口动画执行 |
| InputDispatcher.cpp | `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` | dumpsys input 输出源，焦点管理 |
| SurfaceFlinger.cpp | `frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp` | dumpsys SurfaceFlinger 输出源 |
| Layer.cpp | `frameworks/native/services/surfaceflinger/Layer.cpp` | SurfaceFlinger 的 Layer 管理 |
| SurfaceControl.java | `frameworks/base/core/java/android/view/SurfaceControl.java` | Surface 操作，Transaction 提交 |
| Watchdog.java | `frameworks/base/services/core/java/com/android/server/Watchdog.java` | system_server 看门狗 |

---

本篇是 Window 系列的最后一篇。完整系列请参阅 [README-Window 系列](README-Window系列.md)。
