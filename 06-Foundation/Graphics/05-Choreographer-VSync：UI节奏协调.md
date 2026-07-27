# 06-Foundation/Graphics · 05 · Choreographer / VSync：UI 节奏协调

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · UI 跳帧 / 卡顿问题
>
> **强依赖**：[01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) · 04 HWUI/RenderThread · 05 Choreographer

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Choreographer 这个 app 端的"UI 节拍器" + VSync 协调机制讲清楚——oncall 5 秒定位"跳帧是不是 VSync 错"
- **不是**：不复述 [02 §2 VSync 事件分发](02-SurfaceFlinger内部：合成-VSync-Layer树.md)（本文深入 app 端 Choreographer）；不复述 [04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md)（本文是节拍器，不是渲染）
- **承接自**：[04 §2.3 RenderThread 时序](04-HWUI-RenderThread：硬件加速渲染.md) → 本文展开 VSync → Choreographer
- **衔接去**：[06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) / [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章 Choreographer 是什么 | 必备 |
| 2 | 第 3 章 FramePipeline 4 阶段 | 核心 |
| 3 | 第 4 章 Choreographer 调度 | 实战 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Choreographer = app 端的"UI 节拍器"——监听 VSync，调度 Input / Animation / Draw / Commit 4 大阶段——5 类跳帧，oncall 5 秒定位"跳帧是哪个阶段慢"。**

AOSP 17 上 Choreographer 跑在 `frameworks/base/core/java/android/view/Choreographer.java`。理解 Choreographer = 5 秒定位"app 跳帧"。

---

## 1. Choreographer 是什么

### 1.1 一句话定义

**Choreographer = app 进程的"VSync 调度器"——每个 VSync 触发一次 doFrame()，跑 Input → Animation → Draw → Commit 4 阶段。**

### 1.2 4 大特性

| 特性 | 含义 | 性能影响 |
|:-----|:-----|:--------|
| **VSync 同步** | 跟随 Display vsync | 16.6ms 节拍 |
| **4 阶段调度** | Input / Animation / Draw / Commit | 流水线 |
| **FrameCallback** | 注册回调 | 灵活 |
| **跳帧检测** | 自动 skip | 实时 |

### 1.3 关键源码

```
frameworks/base/core/java/android/view/
├── Choreographer.java                 ← Choreographer 主类
├── ViewRootImpl.java                   ← Choreographer 用户
├── Window.java                         ← Choreographer 入口
├── FrameInfo.java                       ← FrameInfo
└── ...

frameworks/native/libs/gui/
├── FrameTimeline.cpp                   ← Frame timeline
└── ...

frameworks/native/services/surfaceflinger/
├── Scheduler/
│   ├── EventThread.cpp                 ← VSync 事件线程
│   └── DispSync.cpp                    ← Display sync
└── ...
```

### 1.4 AOSP 17 Choreographer 关键变化

```
AOSP 8  → Choreographer API 完整
AOSP 10 → VSync source 增强
AOSP 12 → Choreographer / SF 协同优化
AOSP 14 → FrameTimeline 优化
AOSP 16 → Surface sync 增强
AOSP 17 → Multi-display VSync source
```

### 1.5 5 大 Choreographer 状态

| 状态 | 含义 | 何时 |
|:-----|:-----|:-----|
| **IDLE** | 空闲 | 启动前 / 一帧完成 |
| **PROCESSING** | 处理中 | doFrame 跑 |
| **SCHEDULED** | 已调度下一帧 | VSync 已收到 |
| **WAITING_FOR_CALLBACKS** | 等待 callback | input 阶段 |
| **DRAW_PENDING** | 等 draw | draw 阶段 |

---

## 2. VSync 信号

### 2.1 VSync 是什么

**VSync = Display 控制器每 16.6ms（60Hz）发一次的"垂直同步"信号——是图形栈的"节拍器"。**

### 2.2 VSync 6 大参数

| 参数 | 默认 | 含义 |
|:-----|:-----|:-----|
| **频率** | 60Hz / 90Hz / 120Hz | 每秒 VSync 次数 |
| **相位** | 0 | 偏移 |
| **timestamp** | ns | 精确时间 |
| **period** | 16.6ms | 周期 |
| **frame** | 自增序号 | 当前帧号 |
| **deadline** | ns | frame deadline |

### 2.3 VSync 3 大信号源

| 来源 | 周期 | 适用 |
|:-----|:-----|:-----|
| **HW_VSYNC** | 16.6ms (60Hz) | 默认 |
| **VSYNC_BY_SF** | 16.6ms | SF 模拟 |
| **VSYNC_BY_APP** | 16.6ms | app 模拟 |

### 2.4 5 大 VSync 异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **VSync 丢** | Display 没发 | `dumpsys SurfaceFlinger` |
| **VSync 抖动** | 时钟不稳 | `dumpsys SurfaceFlinger` |
| **phase 错** | offset 错 | `dumpsys SurfaceFlinger` |
| **频率错** | 设错 | `wm density` |
| **VSync 频繁** | 节流失效 | `dumpsys SurfaceFlinger` |

---

## 3. FramePipeline 4 阶段

### 3.1 4 阶段时序

```
[VSync 到来]
    ↓
[t=0ms] Input 阶段
    ├─ Choreographer.doInput()
    ├─ 拉 input 事件
    ├─ dispatch 到 View
    └─ View.onTouchEvent 等
    ↓
[t=1-2ms] Animation 阶段
    ├─ Choreographer.doAnimation()
    ├─ ValueAnimator 跑
    ├─ 更新 View 属性（位置 / alpha / scale）
    └─ 触发 view invalidate()
    ↓
[t=2-4ms] Draw 阶段
    ├─ Choreographer.doDraw()
    ├─ View.draw() 走 measure → layout → draw
    ├─ 生成 RenderNode 树
    ├─ 推给 RenderThread
    └─ 触发 RenderThread 渲染
    ↓
[t=4-12ms] RenderThread 渲染
    ├─ 跑 GLES / Vulkan
    └─ 写入 BufferQueue
    ↓
[t=12-16ms] Commit 阶段
    ├─ Choreographer.doCommit()
    ├─ 等 RenderThread 完成
    └─ 提交

[总] ≤ 16ms = 60fps
```

### 3.2 4 阶段时间预算

| 阶段 | 健康值 | 卡顿阈值 | 影响 |
|:-----|:------|:--------|:----|
| **Input** | < 1ms | > 4ms | 输入延迟 |
| **Animation** | < 2ms | > 4ms | 动画跳帧 |
| **Draw** | < 2ms | > 4ms | 渲染慢 |
| **Commit** | < 1ms | > 4ms | 提交慢 |

### 3.3 4 阶段异常信号

```bash
# 1. Input 阶段慢
$ adb logcat -d | grep "Input dispatching"
# "Input dispatching took 30ms"  ← 慢

# 2. Animation 阶段慢
# 抓 perfetto 看 Choreographer#doAnimation 跑多久

# 3. Draw 阶段慢
$ adb logcat -d | grep "Choreographer.*Skipped"
# "Skipped 50 frames!"

# 4. Commit 阶段慢
# 抓 perfetto 看 RenderThread 完成 → Choreographer 等待
```

---

## 4. Choreographer 调度

### 4.1 4 大 Callback 类型

| Callback | 触发时机 | 用途 |
|:---------|:--------|:----|
| **INPUT** | Input 阶段 | 输入处理 |
| **ANIMATION** | Animation 阶段 | 动画 |
| **TRAVERSAL** | Draw 阶段 | View 树测量/布局/绘制 |
| **COMMIT** | Commit 阶段 | 提交 |

### 4.2 FrameCallback 注册

```java
// 注册
Choreographer.getInstance().postFrameCallback(
    new Choreographer.FrameCallback() {
        @Override
        public void doFrame(long frameTimeNanos) {
            // 在 doFrame 调时执行
        }
    }
);

// 取消
Choreographer.getInstance().removeFrameCallback(callback);
```

### 4.3 doFrame() 完整逻辑

```java
// Choreographer.doFrame() 简化版
void doFrame(long frameTimeNanos, int frame) {
    // 1. 收集 input 事件
    mInputEventQueue.consumeEvents(...);
    
    // 2. 计算 frame 信息
    mFrameInfo.set(...);
    
    // 3. Animation 阶段
    doAnimation(frameTimeNanos, frame);
    
    // 4. Input 阶段
    doInput(frameTimeNanos, frame);
    
    // 5. Traversal 阶段
    doTraversal(frameTimeNanos, frame);
    
    // 6. Commit 阶段
    doCommit(frameTimeNanos, frame);
}
```

### 4.4 4 大调优参数

```bash
# 1. 跳帧容忍度
$ adb shell setprop debug.hwui.skipped_frames_warning 50
# 跳 50 帧报 warning

# 2. 强制 GPU 模式
$ adb shell setprop debug.hwui.renderer skiagl

# 3. View 调试
$ adb shell setprop debug.hwui.profile 1
# 详细分析

# 4. Animator 调试
$ adb shell setprop debug.animator 1
```

---

## 5. 4 大跳帧原因

### 5.1 跳帧的本质

**跳帧（frame skip）= Choreographer 收到 VSync，但 doFrame() 跑不完 16ms，下一帧被跳过。**

### 5.2 5 大跳帧原因

| 原因 | 现象 | 5 秒定位 |
|:-----|:-----|:--------|
| **主线程 Input 慢** | 输入卡 | 看 InputEventReceiver |
| **主线程 Animation 慢** | 动画跳 | Choreographer#doAnimation |
| **主线程 Draw 慢** | 渲染慢 | View.onDraw |
| **RenderThread 慢** | GPU 慢 | RenderThread |
| **VSync 错** | 节拍错 | `dumpsys SurfaceFlinger` |

### 5.3 跳帧 4 大类日志

```bash
# 1. 经典跳帧日志
$ adb logcat -d | grep "Choreographer.*Skipped"
# "Choreographer: Skipped 50 frames!  The application may be doing too much work on its main thread."

# 2. 系统跳帧
$ adb logcat -d -b system | grep "Skipped"
# 期望：< 30 / minute

# 3. app 跳帧
$ adb logcat -d | grep "Skipped"
# 跳帧多的 app = 卡顿 app

# 4. VSync 错位
$ adb logcat -d -b system | grep "VSync phase"
# phase > 0 = 撕裂
```

### 5.4 跳帧与卡顿关系

```
跳帧数 = 卡顿次数（用户感知）

[阈值]
< 5 跳 / 分钟  → 优
5-30 跳 / 分钟 → 中
> 30 跳 / 分钟 → 卡顿严重

[测量]
$ adb shell dumpsys gfxinfo | grep "Janky frames"
```

---

## 6. 5 大实战 case

### 6.1 Case 1：滑动卡 Input 慢

```
[症状] 滑动卡

[Step 1] 看 Choreographer
$ adb logcat -d | grep "Choreographer.*Skipped"
# Skipped 30 frames!

[Step 2] 看 Input 阶段
# 抓 perfetto 看 Input 处理时间
# 25+ ms

[Step 3] 看主线程
# 看到 RecyclerView.onTouchEvent 处理慢
# → 因为 bindViewHolder 在 onTouchEvent 内

[Step 4] 修法
- bindViewHolder 异步
- 用 DiffUtil
- 减少 RecyclerView 复杂度
```

### 6.2 Case 2：动画卡 Animation 慢

```
[症状] 启动动画跳帧

[Step 1] 看跳帧
$ adb logcat -d | grep "Choreographer.*Skipped"
# Skipped 50 frames!

[Step 2] 抓 perfetto
# Animation 阶段 30+ ms

[Step 3] 看动画
# 复杂 ObjectAnimator / ValueAnimator

[Step 4] 修法
- 用 RenderNode 缓存
- 减动画复杂度
- 用 LayoutAnimationController
```

### 6.3 Case 3：app 启动卡 Draw 慢

```
[症状] 启动慢 3 秒

[Step 1] 看 am start -W
$ adb shell am start -W -n com.example.app/.MainActivity
# ThisTime: 3000ms

[Step 2] 抓 perfetto
# Draw 阶段长 = onCreate 跑慢
# View 树构建慢

[Step 3] 修法
- ConstraintLayout 替代嵌套
- 异步 inflate
- 用 ViewStub
```

### 6.4 Case 4：VSync 错位

```
[症状] 撕裂

[Step 1] 看 VSync
$ adb shell dumpsys SurfaceFlinger | grep "VSync phase"
# 0.5  ← 错位

[Step 2] 调整 phase
$ adb shell setprop debug.sf.vsync_offset 0.0

[Step 3] 测
# 撕裂消失

[Step 4] 修法
- 调 vsync offset
- 重新校准 Display
```

### 6.5 Case 5：多 app 跳帧

```
[症状] 整个手机卡

[Step 1] 看所有 app
$ adb shell dumpsys gfxinfo | grep "Profile"
# 看每个 app 跳帧数

[Step 2] 找最卡 app
# 100+ 跳帧

[Step 3] 看主线程
# app 主线程忙

[Step 4] 修法
- 找出最卡 app
- 升级 / 卸载 / 限制
```

---

## 7. 5 大调优 case

### 7.1 Case 1：启用 RenderNode 缓存

```java
// View 启用硬件层
view.setLayerType(View.LAYER_TYPE_HARDWARE, null);
// 启用 RenderNode 缓存
```

### 7.2 Case 2：减少 overdraw

```java
// 隐藏不可见 View
view.setVisibility(View.GONE);

// 用 ViewStub 延迟 inflate
viewStub.inflate();
```

### 7.3 Case 3：异步 bind

```java
// 异步 RecyclerView bind
recyclerView.setHasFixedSize(true);
recyclerView.setItemViewCacheSize(20);
```

### 7.4 Case 4：减少 GC

```java
// 复用 Paint / Matrix
private final Paint paint = new Paint();
// 不要每帧 new
```

### 7.5 Case 5：调跳帧警告

```bash
# 默认 30 跳 → 警告
$ adb shell setprop debug.hwui.skipped_frames_warning 50
# 50 跳才警告（减少 log 噪音）
```

---

## 8. oncall 5 分钟决策

```
[问题] UI 跳帧 / 卡顿
  ↓
[1] 30 秒判断（5 秒）
  ├─ "Choreographer 跳帧" → logcat | grep Skipped
  ├─ "Input 慢" → perfetto Input 阶段
  ├─ "Animation 慢" → perfetto Animation 阶段
  ├─ "Draw 慢" → perfetto Draw 阶段
  └─ "VSync 错" → dumpsys SurfaceFlinger
  ↓
[2] 抓现场（30-60 秒）
  ├─ logcat | grep Choreographer
  ├─ perfetto 30s
  ├─ dumpsys gfxinfo
  └─ logcat -b system | grep VSync
  ↓
[3] 5 分钟定位
  ├─ Input 慢 → 主线程 input 处理
  ├─ Animation 慢 → 复杂动画
  ├─ Draw 慢 → View 树复杂
  └─ VSync 错 → Display 时钟
  ↓
[4] 出报告（5 分钟）
```

---

## 9. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) | 上篇 |
| [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md) | 上篇 |
| [03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md) | 上篇 |
| [04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md) | 上篇 |
| [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) | 续篇 |
| [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) | 续篇 |
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../04-Tool/Perfetto/01-Perfetto系统总览与架构设计.md) | trace 工具 |

---

## 10. 收官 + 自检

### 10.1 看完本文的自检

- [ ] 能说 Choreographer 4 大特性
- [ ] 能说 VSync 6 大参数
- [ ] 能说 FramePipeline 4 阶段
- [ ] 能用 logcat | grep Choreographer 5 秒看跳帧
- [ ] 知道 4 大 Callback 类型
- [ ] 知道 5 大跳帧原因
- [ ] 知道 5 大实战 case 修法

### 10.2 收官话

Choreographer / VSync 在图形栈里属于**"节拍层"**——app 端的 VSync 调度器。

下一步推荐读：
- [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) — HWC 深入
- [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) — 综合实战
- [04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md) — 渲染回看

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
