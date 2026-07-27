# 06-Foundation/Graphics · 04 · HWUI / RenderThread：硬件加速渲染

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 渲染卡顿问题
>
> **强依赖**：[01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) · [03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md) · [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 HWUI native 渲染 + RenderThread 异步线程 + DisplayList / RenderNode 树讲清楚——oncall 5 秒定位"渲染慢在主线程还是 RenderThread"
- **不是**：不复述 [01 §1.1 app 层](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md)（本文深入 app native 渲染）；不复述 [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md)（本文讲 app 渲染）
- **承接自**：[03 §4.2 app HWUI producer 时序](03-BufferQueue：跨进程图形缓冲机制.md) → 本文深入 app 渲染
- **衔接去**：[05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) / [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) / [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章 HWUI 是什么 + 关键源码 | 必备 |
| 2 | 第 2 章 RenderThread 工作原理 | 核心 |
| 3 | 第 6 章 5 大实战 case | oncall 用 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**HWUI = app 进程的 native 渲染引擎 + RenderThread = 渲染线程——5 类渲染异常，oncall 5 秒定位"渲染慢在主线程还是 RenderThread"。**

AOSP 17 上 HWUI 跑在 `frameworks/base/libs/hwui/`，每个 app 进程 1 个 RenderThread 线程。理解 HWUI / RenderThread = 5 秒定位"渲染卡顿"。

---

## 1. HWUI 是什么

### 1.1 一句话定义

**HWUI = app 进程的 native 渲染引擎——把 Java 端 View 树转成 GLES / Vulkan 命令，在 GPU 上画。**

### 1.2 HWUI 4 大特性

| 特性 | 含义 | 性能影响 |
|:-----|:-----|:--------|
| **硬件加速** | GPU 渲染 | 10x 快 vs CPU |
| **native 实现** | C++ 渲染 | 减少 GC |
| **DisplayList 缓存** | 缓存 RenderNode | 减少重绘 |
| **RenderThread 异步** | 主线程不阻塞 | 流畅 |

### 1.3 关键源码

```
frameworks/base/libs/hwui/
├── HWUI.cpp                          ← HWUI 主类
├── renderthread/
│   ├── RenderThread.cpp              ← RenderThread 主类
│   ├── EglManager.cpp                ← EGL 管理
│   ├── CanvasContext.cpp             ← 画布上下文
│   ├── RenderPipeline.cpp            ← 渲染管线
│   └── CacheManager.cpp              ← 缓存管理
├── pipeline/
│   ├── skia/
│   │   └── SkiaPipeline.cpp          ← Skia 后端
│   └── (新后端)
├── RecordingCanvas.cpp                ← RecordingCanvas
├── RenderNode.cpp                    ← RenderNode
├── DisplayList.cpp                   ← DisplayList
├── SkiaCanvas.cpp                    ← Skia 实现
└── TreeInfo.h                        ← 树信息
```

### 1.4 AOSP 17 HWUI 关键变化

```
AOSP 8  → HWUI 增强
AOSP 10 → Vulkan 集成
AOSP 11 → SkiaRenderer 优化
AOSP 12 → RenderNode 增强
AOSP 13 → WebGL 支持
AOSP 14 → 性能优化（path rendering）
AOSP 15 → 性能优化（display list caching）
AOSP 16 → SkiaRenderer 优化
AOSP 17 → HWUI pipeline 重构
```

### 1.5 4 大渲染后端

| 后端 | 优势 | 适用 |
|:-----|:-----|:-----|
| **Skia** | 跨平台 | 普通 UI |
| **Vulkan** | 高性能 | 大块渲染 |
| **OpenGL ES** | 兼容 | 旧设备 |
| **HWUI Native** | 高效 | AOSP 17 |

---

## 2. RenderThread 工作原理

### 2.1 RenderThread 是什么

**RenderThread = app 进程内的"渲染线程"——专门跑 GLES / Vulkan 绘制，让主线程不阻塞。**

### 2.2 4 大线程分工

| 线程 | 角色 | 占用时间 |
|:-----|:-----|:--------|
| **Main (UI) 线程** | 处理 Input / Animation / 创建 RenderNode | Input + Animation + Draw |
| **RenderThread** | 跑 GLES / Vulkan 绘制 | Render 阶段 |
| **HWUI binder 线程** | 处理 IPC | 1-2ms |
| **GPU driver 线程** | 跑 GPU 命令 | GPU 占用 |

### 2.3 RenderThread 时序（AOSP 17）

```
[1] VSync 触发
    ↓
[2] 主线程 Input 阶段
    - 拉 input 事件
    - dispatch 到 View
    ↓
[3] 主线程 Animation 阶段
    - ValueAnimator 跑
    - 更新 View 属性
    ↓
[4] 主线程 Draw 阶段
    - View.draw() 走 measure → layout → draw
    - 生成 DisplayList
    - 把 RenderNode 推给 RenderThread
    ↓
[5] RenderThread 渲染
    - 接收 RenderNode
    - 跑 GLES / Vulkan 命令
    - 写入 Surface (BufferQueue)
    - eglSwapBuffers
    ↓
[6] 主线程可以继续下一帧

[关键]: 主线程在 [4] 推完 RenderNode 后可以立即返回
       RenderThread 异步渲染
```

### 2.4 RenderThread 5 大参数

| 参数 | 默认 | 含义 |
|:-----|:-----|:-----|
| `frametime` | 16.6ms (60Hz) | 帧时间 |
| `use_vsync` | true | VSync 同步 |
| `async_render` | true | 异步渲染 |
| `max_frame_skipped` | 3 | 最大跳帧 |
| `pipeline` | skia / vulkan | 渲染后端 |

### 2.5 5 大 RenderThread 异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **RenderThread 忙** | GPU 渲染慢 | `dumpsys gfxinfo` |
| **GPU 高占用** | 复杂 path | `dumpsys gpu` |
| **BufferQueue 卡** | fence 等 | `dumpsys SurfaceFlinger` |
| **RenderThread 不跑** | 渲染被关 | `dumpsys hwui` |
| **跳帧多** | RenderThread 跟不上 | `dumpsys gfxinfo` |

---

## 3. DisplayList / RenderNode

### 3.1 4 大概念

| 概念 | 含义 | 用途 |
|:-----|:-----|:-----|
| **View 树** | Java 端 View 层级 | 业务逻辑 |
| **RenderNode 树** | C++ 端渲染节点 | 渲染数据 |
| **DisplayList** | RenderNode 的命令列表 | GLES 命令 |
| **Canvas** | 绘制 API | 跨后端抽象 |

### 3.2 View → RenderNode 转换

```
[Java 端]
ViewGroup (LinearLayout)
├── TextView "Hello"
└── ImageView

[onDraw 调 Canvas 操作]
- canvas.drawText("Hello", x, y, paint)
- canvas.drawBitmap(bitmap, x, y, paint)

[RecordingCanvas 录制]
DisplayList:
  [0] DrawText("Hello", x=0, y=0, paint=red)
  [1] DrawBitmap(bitmap, x=10, y=10, paint=default)
  ...

[RenderNode]
  └─ DisplayList
  └─ Properties (alpha / transform / clip)
```

### 3.3 DisplayList 缓存机制

```java
// 关键优化：RenderNode 复用
RenderNode node = ...;
node.setRenderEffect(new RenderEffect.createBlurEffect(...));
// 下次绘制直接复用 RenderNode
// 不重新生成 DisplayList
```

**关键洞察**：
- 同一 View 多次绘制 → 复用 RenderNode
- invalidate 不破坏 RenderNode
- onDraw 内部简单 → RenderNode 复用率高

### 3.4 4 大 DisplayList 异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **RenderNode 太多** | 复杂 View 树 | `dumpsys gfxinfo \| grep "RenderNode"` |
| **DisplayList 重建** | 频繁 invalidate | `dumpsys gfxinfo` |
| **RenderNode 复用低** | onDraw 复杂 | 看 onDraw |
| **Cache miss** | 资源未缓存 | `dumpsys hwui` |

---

## 4. GLES / Vulkan 渲染

### 4.1 4 大渲染 API 对比

| API | 版本 | 性能 | 兼容性 | AOSP 17 |
|:---|:-----|:-----|:------|:------|
| **OpenGL ES 1.0** | 1.0 | 低 | 99% | 兼容 |
| **OpenGL ES 2.0** | 2.0 | 中 | 99% | 默认 |
| **OpenGL ES 3.0** | 3.0 | 中高 | 95% | 可用 |
| **Vulkan 1.x** | 1.0+ | 极高 | 80% | 可选 |

### 4.2 真实 GLES 渲染时序

```
[1] RenderThread 接收 RenderNode
[2] 解析 DisplayList
[3] 创建 SkiaCanvas
[4] 调 GLES 命令
   - glClear
   - glViewport
   - glDrawElements / glDrawArrays
   - glReadPixels (如需要)
[5] 写入 Surface (BufferQueue)
[6] eglSwapBuffers 提交
```

### 4.3 4 大 GLES 性能优化

```bash
# 1. 启用 GPU 调试
$ adb shell setprop debug.egl.profiler 1
# 性能分析

# 2. 启用 GPU inspector
$ adb shell setprop debug.hwui.profile 1
# 详细分析

# 3. 启用 Vulkan
$ adb shell setprop debug.hwui.renderer skiagl-vulkan
# 切换到 Vulkan 后端

# 4. 启用 RenderThread 高精度 timer
$ adb shell setprop debug.hwui.high_precision_timer 1
```

### 4.4 5 大 GLES 异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **GLES 错误** | driver bug | logcat -s EGL |
| **GLES 慢** | 复杂 path | `dumpsys gpu` |
| **driver crash** | 兼容 | `dumpsys gpu` |
| **资源泄漏** | glGen / glDelete 配对 | leak 检测 |
| **shader 编译慢** | 复杂 shader | 看 shader |

---

## 5. 4 大 GPU 渲染优化

### 5.1 优化 1：减少 onDraw 工作

```java
// 差：onDraw 复杂
@Override
protected void onDraw(Canvas canvas) {
    for (int i = 0; i < 100; i++) {
        canvas.drawLine(...);
    }
}

// 好：缓存到 RenderNode
private RenderNode renderNode;
@Override
protected void onDraw(Canvas canvas) {
    if (renderNode == null) {
        // 第一次构建
        RecordingCanvas rc = ...;
        for (int i = 0; i < 100; i++) {
            rc.drawLine(...);
        }
        renderNode = ...;
    }
    canvas.drawRenderNode(renderNode);
}
```

### 5.2 优化 2：使用 View Hardware Layer

```java
// 启用硬件层
view.setLayerType(View.LAYER_TYPE_HARDWARE, null);
// 启用 RenderNode 缓存
```

### 5.3 优化 3：避免 overdraw

```java
// 开启 overdraw 检测
view.setWillNotDraw(true);  // 告诉系统这个 View 不需要 draw
// 减少 overdraw
```

### 5.4 优化 4：减少内存分配

```java
// 差：每帧 new Paint
@Override
protected void onDraw(Canvas canvas) {
    Paint p = new Paint();
    canvas.drawText(..., p);
}

// 好：复用 Paint
private final Paint paint = new Paint();
@Override
protected void onDraw(Canvas canvas) {
    canvas.drawText(..., paint);
}
```

---

## 6. 5 大实战 case

### 6.1 Case 1：滑动卡 RenderThread 慢

```
[症状] 滑动卡顿

[Step 1] 看 gfxinfo
$ adb shell dumpsys gfxinfo | tail -50
# Render time: 30ms  (慢)
# Issue: vertices count too high

[Step 2] 抓 perfetto
# RenderThread 30+ ms / frame

[Step 3] 看哪个 View 复杂
# RecyclerView 复杂

[Step 4] 优化
- 减少 View 层级
- 用 viewType 分类
- 减少 onDraw 工作

[Step 5] 修法
- setHasFixedSize(true)
- setItemViewCacheSize(20)
- DiffUtil 替代 notifyDataSetChanged
```

### 6.2 Case 2：列表滚卡主线程忙

```
[症状] 列表滚动卡顿

[Step 1] 看 Choreographer
$ adb logcat -d | grep "Choreographer.*Skipped"
# Skipped 30 frames!

[Step 2] 看主线程
# Input 阶段 5ms + Animation 阶段 5ms + Draw 阶段 25ms = 35ms > 16ms

[Step 3] 抓 perfetto
# 看主线程在做什么
# 看到 RecyclerView onBindViewHolder 太重

[Step 4] 修法
- 异步 bind
- 用 ViewHolder pattern
- 减少 ImageView 解码
```

### 6.3 Case 3：app 启动卡渲染慢

```
[症状] app 启动慢

[Step 1] 看 am start -W
$ adb shell am start -W -n com.example.app/.MainActivity
# ThisTime: 3000ms (慢)

[Step 2] 抓 perfetto
# 看到 onCreate 跑 layoutInflate 太慢
# 看到 View 树构建 + measure / layout 慢

[Step 3] 修法
- 延迟初始化
- 异步 inflate
- 用 ViewStub
- ConstraintLayout 替代 LinearLayout 嵌套
```

### 6.4 Case 4：GPU 高占用

```
[症状] GPU 持续 90% 占用

[Step 1] 看 dumpsys gpu
$ adb shell dumpsys gpu
# 看到某些 app 持续占 GPU

[Step 2] 看 perfetto
# GPU 一直跑

[Step 3] 看哪个 app
# 游戏 / 视频 app

[Step 4] 修法
- 降低特效
- 减少 RenderNode
- 用低分辨率 buffer
```

### 6.5 Case 5：overdraw 严重

```
[症状] 滑动时 GPU 占用高 + 卡

[Step 1] 开 overdraw 检测
$ adb shell setprop debug.hwui.overdraw show

[Step 2] 看屏幕
# 颜色：白（1x）→ 蓝（2x）→ 绿（3x）→ 粉（4x）→ 红（5x+）
# 红 = 严重 overdraw

[Step 3] 修法
- 减少 view 层级
- 用 ConstraintLayout
- 用 ViewStub
- 隐藏不可见 View
```

---

## 7. 5 大调优 case

### 7.1 Case 1：启用 RenderThread

```bash
# 确保 RenderThread 启用
$ adb shell getprop debug.hwui.renderer
# skia
# 或 vulkan
```

### 7.2 Case 2：禁用 HW overlay

```bash
# 强制 GPU 渲染（debug）
$ adb shell setprop debug.sf.disable_hwc 1
# 强制 HWC（生产）
$ adb shell setprop debug.sf.disable_hwc 0
```

### 7.3 Case 3：启用 strict mode

```bash
# 严格模式（卡主线程 5s 报错）
$ adb shell setprop debug.hwui.always_draw 1
```

### 7.4 Case 4：关闭 overdraw

```bash
# 关闭 overdraw
$ adb shell setprop debug.hwui.overdraw false
```

### 7.5 Case 5：禁用 RenderThread

```bash
# 强制主线程渲染（debug 用）
$ adb shell setprop debug.hwui.disable_vsync 1
```

---

## 8. oncall 5 分钟决策

```
[问题] 渲染相关
  ↓
[1] 30 秒判断（5 秒）
  ├─ "主线程卡" → dumpsys gfxinfo | grep "Issue"
  ├─ "RenderThread 卡" → perfetto
  ├─ "GPU 高" → dumpsys gpu
  ├─ "overdraw" → debug.hwui.overdraw
  └─ "Buffer 卡" → dumpsys SurfaceFlinger
  ↓
[2] 抓现场（30-60 秒）
  ├─ dumpsys gfxinfo
  ├─ perfetto 30s
  ├─ dumpsys gpu
  └─ logcat | grep HWUI
  ↓
[3] 5 分钟定位
  ├─ 主线程卡 → Input/Animation/Draw 阶段
  ├─ RenderThread 卡 → GPU 渲染
  ├─ GPU 高 → overdraw / 复杂 shader
  └─ Buffer 卡 → SF 合成
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
| [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) | 续篇 |
| [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) | 续篇 |
| [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) | 续篇 |
| [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md) | jank 症状 |
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../04-Tool/Perfetto/01-Perfetto系统总览与架构设计.md) | trace 工具 |

---

## 10. 收官 + 自检

### 10.1 看完本文的自检

- [ ] 能说 HWUI 4 大特性
- [ ] 能说 RenderThread 4 大线程分工
- [ ] 能说 View → RenderNode → DisplayList 转换
- [ ] 能用 dumpsys gfxinfo 5 秒看渲染
- [ ] 知道 4 大 GLES / Vulkan 渲染 API
- [ ] 知道 5 大实战 case 修法
- [ ] 知道 5 大调优 case

### 10.2 收官话

HWUI / RenderThread 在图形栈里属于**"渲染层"**——app 进程的 native 渲染 + 异步线程。

下一步推荐读：
- [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) — VSync 协调
- [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) — 综合实战
- [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) — HWC 深入

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
