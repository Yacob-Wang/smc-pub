# 06-Foundation/Graphics · 02 · SurfaceFlinger 内部：合成 / VSync / Layer 树

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · SurfaceFlinger 卡顿问题
>
> **强依赖**：[01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) · [03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md) · [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 SurfaceFlinger 内部 4 大子系统（启动 / VSync / Layer 树 / 合成）讲清楚——oncall 5 秒定位"卡顿是 VSync 错 / Layer 错 / 合成慢"
- **不是**：不复述 [01 §1 5 层架构](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md)（本文深入 SF）；不复述 [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md)（下篇专门讲 HWC）
- **承接自**：[01 §3 12 步全链路](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) → 本文展开 SF 内部
- **衔接去**：[03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md) / [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) / [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 1 章 SF 启动 | 必备 |
| 2 | 第 2 章 VSync 5 大阶段 | 核心 |
| 3 | 第 4 章 GLES vs HWC 决策 | 5 秒定位关键 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**SurfaceFlinger = 图形栈的"调度中心"——管理 100+ Layer、协调 VSync、决策 GLES/HWC 合成——5 类卡顿，oncall 5 秒定位"哪一阶段慢"。**

AOSP 17 上 SF 跑在 `/system/bin/surfaceflinger`，主线程跑合成循环。理解 SF 内部 = 5 秒定位"合成阶段卡顿"。

---

## 1. SurfaceFlinger 启动

### 1.1 启动 5 大阶段

```
[1] main()
    └─ 命令行解析
    └─ 设置 thread name "surfaceflinger"
    └─ 创建 SurfaceFlinger 实例

[2] SurfaceFlinger 构造
    └─ 创建 Display 列表
    └─ 创建 Layer 工厂
    └─ 初始化 VSync 调度器
    └─ 创建 EventQueue / MessageQueue

[3] init()
    └─ 启动 VSync 线程
    └─ 启动 RenderEngine (GLES / Vulkan)
    └─ 注册 HWC HAL service
    └─ 注册 SurfaceFlinger service

[4] run()
    └─ 启动 main thread 主循环
    └─ 接收 MessageQueue 消息
    └─ 处理 VSync 事件

[5] 主循环（持续）
    └─ 监听 VSync
    └─ 处理 invalidate
    └─ 触发合成
    └─ 通知 Display
```

### 1.2 关键源码

```
frameworks/native/services/surfaceflinger/
├── main.cpp                    ← 入口
├── SurfaceFlinger.cpp           ← SF 核心类
├── SurfaceFlingerFactory.cpp     ← SF 工厂（生产 GLES / Vulkan 引擎）
├── DisplayDevice.cpp             ← Display 管理
├── Layer.cpp                     ← Layer 基类
├── BufferLayer.cpp               ← BufferLayer（app 提供的 buffer）
├── ColorLayer.cpp                ← ColorLayer（单色）
├── RenderEngine.cpp              ← 渲染引擎
├── Effects/
│   ├── GLESRenderEngine.cpp      ← GLES 合成
│   └── VulkanRenderEngine.cpp    ← Vulkan 合成
├── Scheduler/
│   ├── Scheduler.cpp              ← VSync 调度
│   ├── EventThread.cpp            ← 事件线程
│   └── DispSync.cpp               ← Display sync
├── CompositionEngine/           ← 合成引擎（AOSP 12+）
│   ├── CompositionEngine.cpp
│   ├── Output.cpp
│   └── LayerFE.cpp
└── Hwc2/                         ← HWC 2.x 集成
    └── Hwc2Composer.cpp
```

### 1.3 AOSP 17 SF 关键变化

```
AOSP 12 → CompositionEngine 替代旧合成（async composition）
AOSP 13 → Multi-display 增强
AOSP 14 → VSync 调度器重构（Scheduler::run）
AOSP 15 → HWC HAL 3.0（AIDL 替代 HIDL）
AOSP 16 → Vulkan 合成默认
AOSP 17 → Multi-display + Layer 树优化
```

---

## 2. VSync 事件分发（5 大阶段）

### 2.1 VSync 完整流程

```
[1] 物理 vsync 中断
    - Display 控制器在每 16.6ms（60Hz）发 vsync
    - kernel：vsync 中断
    - 走到 SF：SF 收到 HardwareVsync 信号

[2] VSync 调度
    - SF 主线程 VSync handler 触发
    - 通过 EventThread 分发
    - 调用所有注册的 VSyncCallback

[3] app 收到 VSync
    - Choreographer 的 VSync 监听器触发
    - app 主线程进入 Input → Animation → Draw 阶段

[4] RenderThread 渲染
    - app 主线程生成 RenderNode
    - RenderThread 跑 GLES / Vulkan
    - 把结果写入 Surface

[5] SF 合成
    - SF 收到 buffer ready 信号
    - 进入合成阶段
    - 决定 GLES / HWC 合成
    - 提交到 HWC / Display
```

### 2.2 5 大 VSync 调度参数

| 参数 | 默认值 | 含义 |
|:-----|:------|:-----|
| `vsync_period` | 16.6ms | vsync 周期 |
| `vsync_offset` | 0 | 偏移 |
| `vsync_event_filter` | 1 | 事件过滤（节流）|
| `vsync_min_interval` | 0 | 最小间隔 |
| `vsync_max_interval` | 1000 | 最大间隔 |

### 2.3 5 大异常场景

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **VSync 丢** | Display 没发 vsync | `dumpsys SurfaceFlinger \| grep VSync` |
| **VSync 抖动** | 时钟不稳 | `dumpsys SurfaceFlinger` |
| **VSync 错位** | offset 错 | `setprop debug.sf.vsync_offset` |
| **VSync 频繁** | 节流失效 | `setprop debug.sf.vsync_event_filter 0` |
| **VSync 少** | 显示器问题 | `dumpsys display` |

---

## 3. Layer 树管理

### 3.1 4 种 Layer

| Layer 类型 | 用途 | 例子 |
|:-----------|:-----|:-----|
| **BufferLayer** | app 提供的 buffer | 普通 app window |
| **ColorLayer** | 单色 | 启动背景、状态栏 |
| **ContainerLayer** | 容器 | 嵌套 layer |
| **DisplayLayer** | 显示器 | 内部 display layer |

### 3.2 Layer 真实例子

```
Layer 树（AOSP 17 phone）：
Display 0
├── Window Layer
│   ├── NavigationBar (ColorLayer)
│   ├── StatusBar (BufferLayer)
│   ├── Wallpaper (BufferLayer)
│   ├── Launcher (BufferLayer)
│   ├── SoftInput (BufferLayer) ← 键盘
│   └── ...
└── ...

每个 app window = 1 个 BufferLayer
总 Layer 数：50-200（视 app 数量）
```

### 3.3 Layer 关键属性

| 属性 | 含义 | 影响 |
|:-----|:-----|:----|
| **z** | Z-order | 上下叠放 |
| **alpha** | 透明度 | 透明合成 |
| **transform** | 旋转 / 缩放 | 矩阵计算 |
| **crop** | 裁剪 | 减少像素 |
| **dataspace** | 颜色空间 | 颜色转换 |
| **sideband** | 旁路 stream | Hardware overlay |
| **colorMatrix** | 颜色矩阵 | 特效 |
| **buffer** | 显示内容 | 主要数据 |

### 3.4 5 大 Layer 异常场景

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **Layer 太多** | 慢 | `dumpsys SurfaceFlinger \| grep Layer` |
| **Layer 漏** | 显示缺失 | 看 layer 列表 |
| **Layer 错位** | 几何错 | 看 transform |
| **Layer 黑屏** | buffer 没 ready | 看 buffer 状态 |
| **Layer 撕裂** | vsync 错 | 看 vsync |

### 3.5 Layer 性能优化

```bash
# 看 layer 数
$ adb shell dumpsys SurfaceFlinger | grep "BufferLayer\|ColorLayer" | wc -l
# 期望：50-200

# 看 layer 实际状态
$ adb shell dumpsys SurfaceFlinger | grep -A5 "BufferLayer.*MyApp"
```

---

## 4. 合成决策 GLES vs HWC

### 4.1 合成决策流程

```
[1] SF 收到所有 buffer ready 信号
[2] SF 遍历 Layer 树
[3] 对每个 Layer 调 HWC::present() 或 GLES 合成
[4] HWC 决定：
    ├─ USE_GEOMETRY_TRANSFORM：HWC 处理
    ├─ USE_HARDWARE：HWC 直接送显
    └─ 其它：GLES 合成
[5] 提交到 HWC
[6] HWC 送显
```

### 4.2 4 大合成类型

| 类型 | 性能 | 何时用 | 限制 |
|:-----|:-----|:----|:----|
| **HWC 直接** | 优 | 简单 layer（ColorLayer）| 不支持旋转/alpha |
| **HWC transform** | 优 | 旋转 / 镜像 | Vendor 实现 |
| **GLES 合成** | 中 | 复杂合成 | CPU / GPU 占用 |
| **Vulkan 合成** | 优 | 大块复杂合成 | 需要 Vulkan 支持 |

### 4.3 5 大合成异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **合成慢** | GLES 合成太多 | `dumpsys SurfaceFlinger \| grep GLES` |
| **GPU 高** | 复杂合成 | `dumpsys SurfaceFlinger \| grep GPU` |
| **Fence 等待** | 硬件同步 | `dumpsys SurfaceFlinger \| grep Fence` |
| **LayerReject** | 合成类型错 | `dumpsys SurfaceFlinger \| grep Reject` |
| **GPU 内存满** | buffer 多 | `dumpsys meminfo surfaceflinger` |

### 4.4 合成性能调优

```bash
# 1. 强制 GLES 合成（debug）
$ adb shell setprop debug.sf.disable_hwc 1
# → 所有 layer 走 GLES 合成

# 2. 强制 HWC 合成
$ adb shell setprop debug.sf.disable_glcomposition 1
# → 尽量走 HWC

# 3. 切换合成策略
$ adb shell setprop persist.sys.sf.color_saturation 1.0

# 4. 启用 Vulkan 合成
$ adb shell setprop ro.hwc.enable_vulkan 1

# 5. 限制 GLES 层数
$ adb shell setprop debug.gl.max_layers 8
```

---

## 5. BufferQueue（Buffer 队列）

### 5.1 BufferQueue 是什么

**BufferQueue = app → SF 跨进程 buffer 队列——app 写，SF 读。**

### 5.2 BufferQueue 4 大状态

| 状态 | 含义 | 数量 |
|:-----|:-----|:-----|
| **FREE** | 空闲可写 | N-1 |
| **DEQUEUED** | producer 正在写 | 1 |
| **QUEUED** | 写完等 SF | 1+ |
| **ACQUIRED** | SF 正在读 | 1 |

### 5.3 BufferQueue 关键参数

| 参数 | 默认 | 含义 |
|:-----|:-----|:-----|
| `min_undequeued` | 1 | producer 至少缓冲 |
| `max_buffer_count` | 3 | 最大 buffer 数（双 / 三缓冲）|
| `min_buffer_count` | 2 | 最小 buffer 数 |
| `buffer_size` | (W, H, format) | 单 buffer 大小 |

### 5.4 BufferQueue 异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **Buffer 耗尽** | SF 合成慢 | `dumpsys SurfaceFlinger \| grep Buffer` |
| **Buffer 撕裂** | 双 / 三缓冲失效 | `dumpsys SurfaceFlinger \| grep Triple` |
| **Buffer 卡** | producer 阻塞 | 看 producer 栈 |
| **Buffer 泄漏** | 引用未释放 | 看 fd 引用 |

### 5.5 AOSP 17 BufferQueue 关键变化

```
AOSP 8  → BufferQueue 2.0
AOSP 11 → Buffer sync 优化
AOSP 12 → 减少 Buffer 数（4→3）
AOSP 13 → SharedBufferPool（多 consumer）
AOSP 14 → Buffer 池共享增强
AOSP 17 → Vulkan Buffer 优化
```

---

## 6. SurfaceFlinger 主线程

### 6.1 SF 主线程跑什么

```
[1] EventQueue 循环
    └─ 接收消息
    └─ 处理消息

[2] VSync 处理
    └─ 监听 VSync
    └─ 分发到 app

[3] 合成循环
    └─ traverseLayers
    └─ rebuildLayerStacks
    └─ 合成

[4] 提交
    └─ 调 HWC::present()
    └─ 等 fence
    └─ 释放 buffer
```

### 6.2 5 大 SF 主线程卡顿原因

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **SF 主线程忙** | 处理消息多 | `dumpsys SurfaceFlinger \| grep "Main thread"` |
| **遍历 Layer 慢** | Layer 多 | `dumpsys SurfaceFlinger \| grep "Layer count"` |
| **合成慢** | GLES / HWC 慢 | 看 perfetto |
| **Fence 等待** | GPU 异步未完成 | `dumpsys SurfaceFlinger \| grep Fence` |
| **提交慢** | HWC 慢 | `dumpsys SurfaceFlinger \| grep HWC` |

### 6.3 SF 主线程 perfetto 关键

```bash
# 抓 SF trace
$ adb shell perfetto -o /data/.../sf.perfetto-trace -t 10s \
  -b 64mb sched freq idle gfx view

# 在 ui.perfetto.dev 看：
# - surfaceflinger 主线程（"surfaceflinger" tid）
# - 合成时间（Repaint / Compose）
# - Fence 等待（FenceWait）
```

---

## 7. 5 大实战 case

### 7.1 Case 1：滑动卡顿

```
[症状] 滑动列表掉帧

[Step 1] 看 Choreographer
$ adb logcat -d | grep "Choreographer.*Skipped"
# Skipped 50 frames!

[Step 2] 抓 perfetto
$ adb shell perfetto -o /data/.../jank.perfetto-trace -t 30s \
  -b 64mb sched freq idle am wm gfx view

[Step 3] 看哪个阶段 > 16ms
# Input 阶段 5ms（优）
# Animation 阶段 5ms（优）
# Draw 阶段 25ms（慢！主线程 onDraw 重）
# Render 阶段 10ms（优）
# Compose 阶段 8ms（优）

[Step 4] 看主线程栈
# onDraw 跑 RecyclerView.bindViewHolder 太重
# → onDraw 改异步 / 简化 view 结构

[Step 5] 修法
- 简化 RecyclerView adapter
- 用 viewholder pattern
- 加 RecyclerView.setHasFixedSize(true)
```

### 7.2 Case 2：动画卡顿

```
[症状] 启动动画掉帧

[Step 1] 看 Choreographer
$ adb logcat -d | grep "Choreographer.*Skipped"
# Skipped 100 frames!

[Step 2] 看动画复杂度
# 1. 是不是 Choreographer 多个 callback
$ adb shell dumpsys SurfaceFlinger | grep "Frame rate"

[Step 3] 抓 perfetto
# 看 Animation 阶段
# 30+ ms = 动画复杂度过高

[Step 4] 修法
- 用 ValueAnimator 替代 ObjectAnimator
- 用 Choreographer.FrameCallback 节流
- 用 Property Animation Hardware
```

### 7.3 Case 3：黑屏

```
[症状] 启动后黑屏 2 秒

[Step 1] 看 SF 状态
$ adb shell pidof surfaceflinger
# 1234
# SF 没死

[Step 2] 看 logcat
$ adb logcat -d -b system | grep "SurfaceFlinger"
# 关键："SurfaceFlinger: Display 0 hotplug"

[Step 3] 看 Display 状态
$ adb shell dumpsys display | head -30
# "mIsHdr: false"
# "mDisplayMode: ..."

[Step 4] 看 HWC
$ adb shell dumpsys SurfaceFlinger | grep "HWC"

[Step 5] 修法
- 强制重置 Display
- $ adb shell service call SurfaceFlinger 1034 i32 1
```

### 7.4 Case 4：撕裂

```
[症状] 屏幕有水平横线

[Step 1] 看 vsync
$ adb shell dumpsys SurfaceFlinger | grep "VSync"
# "VSync phase: 0.0"

[Step 2] 看 Phase
# phase 0 = 正常
# phase > 0 = 撕裂

[Step 3] 调整 phase
$ adb shell setprop debug.sf.vsync_offset 0.5

[Step 4] 测
# 撕裂消失

[Step 5] 修法
- 调 vsync offset
- 检查 Display 时钟
```

### 7.5 Case 5：合成慢

```
[症状] 视频 app 卡顿

[Step 1] 看 layer 数
$ adb shell dumpsys SurfaceFlinger | grep "BufferLayer" | wc -l
# 30（很多 video 字幕）

[Step 2] 看合成
$ adb shell dumpsys SurfaceFlinger | grep -E "GLES|HWC"

[Step 3] 强制 HWC
$ adb shell setprop debug.sf.disable_glcomposition 1

[Step 4] 测
# 卡顿消失

[Step 5] 修法
- 减少 layer 数
- 强制 HWC 合成
- 简化视频 player 实现
```

---

## 8. oncall 5 分钟决策

```
[问题] SurfaceFlinger 相关
  ↓
[1] 30 秒判断（5 秒）
  ├─ "SF 死" → pidof surfaceflinger
  ├─ "Layer 多" → dumpsys SurfaceFlinger | grep -c Layer
  ├─ "合成慢" → dumpsys SurfaceFlinger | grep GLES
  ├─ "VSync 错" → dumpsys SurfaceFlinger | grep VSync
  └─ "Fence 等待" → dumpsys SurfaceFlinger | grep Fence
  ↓
[2] 抓现场（30-60 秒）
  ├─ dumpsys SurfaceFlinger
  ├─ perfetto 30s
  ├─ logcat -b system | grep SF
  └─ dumpsys display
  ↓
[3] 5 分钟定位
  ├─ Layer 多 → 合并 / 隐藏
  ├─ 合成慢 → 强制 HWC
  ├─ VSync 错 → 调 offset
  └─ Fence 等 → 查 GPU
  ↓
[4] 出报告（5 分钟）
```

---

## 9. 5 大调优 case

### 9.1 Case 1：禁用 HWC

```bash
# 强制 GLES 合成（debug）
$ adb shell setprop debug.sf.disable_hwc 1
$ adb shell stop surfaceflinger
$ adb shell start surfaceflinger
```

### 9.2 Case 2：禁用 GLES 合成

```bash
# 强制 HWC 合成
$ adb shell setprop debug.sf.disable_glcomposition 1
$ adb shell stop surfaceflinger
$ adb shell start surfaceflinger
```

### 9.3 Case 3：启用 Vulkan 合成

```bash
# 启用 Vulkan 合成
$ adb shell setprop ro.hwc.enable_vulkan 1
# 重启 SF
```

### 9.4 Case 4：禁用 HW overlay

```bash
# 禁用 HW overlay（强制 GPU 合成）
$ adb shell setprop debug.sf.disable_hwc 1
```

### 9.5 Case 5：调整 vsync phase

```bash
# 调整 vsync phase（防撕裂）
$ adb shell setprop debug.sf.vsync_offset 0.5
$ adb shell setprop debug.sf.phase_offset 0
```

---

## 10. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) | 上篇 |
| [03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md) | 续篇 |
| [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) | 续篇 |
| [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) | 续篇 |
| [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) | 续篇 |
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../04-Tool/Perfetto/01-Perfetto系统总览与架构设计.md) | trace 工具 |
| [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md) | jank 症状 |

---

## 11. 收官 + 自检

### 11.1 看完本文的自检

- [ ] 能说 SF 启动 5 大阶段
- [ ] 能说 VSync 5 大分发阶段
- [ ] 能说 4 种 Layer + 真实 Layer 数
- [ ] 能说 GLES vs HWC 合成决策
- [ ] 能用 dumpsys SurfaceFlinger 5 秒看状态
- [ ] 知道 5 大实战 case 修法
- [ ] 知道 5 大调优 case

### 11.2 收官话

SurfaceFlinger 在图形栈里属于**"合成层"**——管 100+ Layer、VSync、合成。

下一步推荐读：
- [03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md) — 跨进程 buffer
- [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) — VSync 协调
- [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) — HWC 深入

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
