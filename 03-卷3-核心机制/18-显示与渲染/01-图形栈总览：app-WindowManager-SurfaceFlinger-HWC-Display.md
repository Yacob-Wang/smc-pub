# 06-Foundation/Graphics · 01 · 图形栈总览：app → WindowManager → SurfaceFlinger → HWC → Display

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 卡顿 / jank 问题排查
>
> **强依赖**：[04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../05-卷5-调查方法论与工具链/31-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) · [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 Android 图形栈从 app 绘制 → WindowManager → SurfaceFlinger → HWC → Display 的完整链路讲清楚——oncall 5 秒定位"卡顿在哪一段"
- **不是**：不复述 [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md)（本文是总览，下篇深入）；不复述 [04 HWUI](04-HWUI-RenderThread：硬件加速渲染.md) / [05 Choreographer](05-Choreographer-VSync：UI节奏协调.md) / [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md)（这些是深入专题）
- **承接自**：[06-Foundation/Network/01 网络栈总览](../Network/01-网络栈总览：从app-socket到网卡的全链路.md) → 同样思路应用图形栈
- **衔接去**：[02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md) / [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) / [04-Tool/Perfetto/04-Perfetto定制化实战](../../../../05-卷5-调查方法论与工具链/31-Perfetto 全栈使用/04-Perfetto定制化实战：ANR后自动抓取trace.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 5 层架构（app / WM / SF / HWC / Display）| 跟 Linux 显示栈对齐 |
| 2 | 第 3 章 12 步全链路 | 不用示意图 |
| 3 | 第 5 章 5 类卡顿问题 | oncall 5 秒定位 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**Android 图形栈 = app HWUI 渲染 → SurfaceFlinger 合成 → HWC 送 Display——3 大阶段，5 类卡顿，oncall 5 秒定位"卡在哪一段"。**

AOSP 17 图形栈含 200+ 文件、5 大核心服务、3 大硬件加速机制。理解全链路 = 现场 5 秒判断"卡在 app 渲染 / SF 合成 / HWC 送显"。

---

## 1. 5 层架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│  Android 图形栈 5 层架构                                          │
└──────────────────────────────────────────────────────────────────┘

[1] App 层（应用层）
    ├─ app 进程 (UID 10000+)
    │   ├─ View / ViewGroup 体系
    │   ├─ Canvas / Paint 绘制 API
    │   ├─ HWUI (Native 渲染)
    │   │   ├─ RenderThread (硬件加速)
    │   │   └─ DisplayList / RenderNode
    │   └─ Choreographer 协调 vsync
    └─ system_server 进程
        ├─ WindowManager (WMS)
        │   └─ Window / SurfaceControl
        └─ ViewRootImpl (每个 window 1 个)
            └─ 跟 app 进程通信（Binder + Surface）

[2] WindowManager 层（system_server）
    ├─ WindowManagerService (WMS)
    │   └─ 管理所有 window 的 Z-order / 位置
    ├─ SurfaceControl
    │   └─ 创建 / 销毁 Surface (跨进程 buffer queue)
    └─ WindowAnimator
        └─ 动画 / 过渡

[3] SurfaceFlinger 层（native daemon）  ← 核心
    ├─ Layer 树管理
    ├─ VSync 同步
    ├─ BufferQueue 管理
    ├─ 合成 (Composition)
    │   ├─ GLES 合成
    │   ├─ Vulkan 合成
    │   └─ HWC 合成
    └─ SurfaceFlinger 主线程
        └─ 60Hz / 90Hz / 120Hz VSync 触发

[4] HWC 层（HAL）
    ├─ Hardware Composer HAL (HIDL/AIDL)
    │   └─ 决定哪些 layer 走 GPU / 哪些走硬件
    ├─ Display HAL
    │   └─ 控制显示硬件
    └─ Vendor Driver
        └─ SoC 特定的显示驱动

[5] Display 层（硬件）
    ├─ LCD / OLED 屏
    ├─ Display Controller (DPU)
    └─ 物理输出
```

**关键观察**：
- app 不能直接送 frame 到 Display，必须经 SF + HWC
- 跨进程 buffer 通过 BufferQueue（共享内存）
- 60Hz = 16.6ms / frame，120Hz = 8.3ms / frame

---

## 2. 帧时序：16.6ms vsync budget（AOSP 17 实测）

### 2.1 一帧的完整时间线

```
[目标] 60Hz 显示器（16.6ms / frame）
       120Hz = 8.3ms / frame
       90Hz = 11.1ms / frame

[t=0ms] VSync 信号
       ↓
[t=0-4ms] app 收到 VSync (Choreographer)
       ↓
[t=4-8ms] Input 阶段（input → app）
       ↓
[t=8-12ms] Animation 阶段（属性动画）
       ↓
[t=12-13ms] Draw 阶段（draw → RenderNode 树）
       ↓
[t=13-15ms] RenderThread 渲染（GLES 绘制）
       ↓
[t=15-16ms] SurfaceFlinger 合成
       ↓
[t=16ms] Display 显示

总耗时: 16ms（1 帧）
```

### 2.2 4 大阶段

| 阶段 | 谁负责 | 占用时间 | 卡顿检测 |
|:-----|:-------|:--------|:--------|
| **Input** | InputManager / ViewRootImpl | 1-2ms | Input event 阻塞 |
| **Animation** | Choreographer / ValueAnimator | 1-2ms | 动画复杂度过高 |
| **Draw** | app / HWUI | 1-2ms | View 层级深 / onDraw 重 |
| **Render** | RenderThread (GLES) | 1-3ms | GPU 渲染复杂 |
| **Compose** | SurfaceFlinger + HWC | 1-3ms | Layer 多 / 透明合成 |

**关键洞察**：
- 5 大阶段共需 16ms（60Hz）
- **任何一阶段 > 16ms = 丢帧** = 用户感知卡顿
- oncall 现场"卡顿" = 找出哪个阶段 > 16ms

---

## 3. 12 步全链路（以一帧为例）

```
[场景] 设备在显示 60Hz，app 收到 VSync，要画一帧

[1] VSync 信号从 Display 出来
    - 物理层：Display 控制器在每 16.6ms 发 vsync
    - 走到 kernel：vsync 中断
    - 走到 SurfaceFlinger：SF 收到 vsync

[2] SurfaceFlinger 通知 app
    - SF 通过 SurfaceControl 发 "Frame Callback"
    - 通知所有有 vsync 监听的 app

[3] app 收到 VSync
    - app 的 Choreographer 收到 VSync
    - 进入 Input → Animation → Draw 阶段

[4] app Input 阶段
    - 把 input 事件从 InputManager 拉到 ViewRootImpl
    - 调用 dispatchInputEvent()
    - 触发 view 的 onTouchEvent 等

[5] app Animation 阶段
    - ValueAnimator / ObjectAnimator 跑
    - 更新 View 的属性（位置 / alpha / scale）
    - 触发 view invalidate()

[6] app Draw 阶段
    - View.draw() 被调
    - 走 measure → layout → draw 三步
    - 生成 RenderNode 树（DisplayList）

[7] RenderThread 渲染
    - app 主线程把 RenderNode 树推给 RenderThread
    - RenderThread 走 GLES / Vulkan 命令
    - 把结果写到 GPU 纹理
    - 完成后调 eglSwapBuffers 提交到 BufferQueue

[8] BufferQueue buffer 传递
    - app 进程的 BufferQueue producer 写入
    - 通知 SurfaceFlinger 的 consumer
    - SF 接收 buffer

[9] SurfaceFlinger 合成
    - SF 遍历所有 Layer
    - 计算每个 Layer 的位置 / 透明 / 旋转
    - 决定 GLES 合成 vs HWC 合成

[10] HWC 决策
    - HWC 遍历每个 Layer
    - 决定哪些用 GPU 合成 / 哪些硬件直接送
    - 输出到 Display

[11] Display 接收
    - Display Controller 接收数据
    - DPU 扫描屏幕
    - 实际显示像素

[12] 一帧完成
    - 总耗时 ≤ 16ms = 60fps 流畅
    - 总耗时 > 16ms = 丢帧 = 卡顿
```

**关键观察**：
- app 只负责第 3-8 步（Input → Draw → Buffer）
- SF 负责第 9 步（合成）
- HWC 负责第 10 步（送显）
- **oncall 现场 5 秒判断"卡顿" = 看 perfetto trace，找哪步 > 16ms**

---

## 4. 3 大核心子系统

### 4.1 子系统速查

| 子系统 | 进程 | 关键服务 | 关键文件 |
|:-------|:-----|:--------|:-------|
| **app HWUI 渲染** | app 进程 | RenderThread | `frameworks/base/libs/hwui/` |
| **WindowManager** | system_server | WMS | `frameworks/base/services/wm/` |
| **SurfaceFlinger** | `/system/bin/surfaceflinger` | SF | `frameworks/native/services/surfaceflinger/` |
| **HWC HAL** | system_server (HIDL/AIDL) | HwServiceManager | `hardware/interfaces/graphics/composer/` |
| **Display HAL** | system_server | DisplayService | `hardware/interfaces/graphics/buffer/` |

### 4.2 关键源码路径

| 路径 | 干什么 |
|:-----|:------|
| `frameworks/base/libs/hwui/` | app HWUI native 渲染 |
| `frameworks/base/services/wm/` | WindowManager |
| `frameworks/native/services/surfaceflinger/` | SurfaceFlinger 全部 |
| `frameworks/native/libs/gui/` | BufferQueue |
| `frameworks/native/libs/ui/` | SurfaceControl |
| `hardware/interfaces/graphics/composer/` | HWC HAL |
| `frameworks/native/services/vr/flinger/` | VR Flinger（早期版本）|

### 4.3 AOSP 17 图形栈新变化

```
AOSP 8  → Project Treble + 独立 HAL
AOSP 9  → RenderThread 增强
AOSP 10 → Vulkan 集成
AOSP 11 → Buffer sync 优化
AOSP 12 → Multi-display 增强
AOSP 13 → HWUI 性能提升（HWUI pipeline）
AOSP 14 → Vulkan 后端增强
AOSP 15 → Privacy Sandbox 渲染
AOSP 16 → SkiaRenderer 优化
AOSP 17 → Multi-display + VSync source 增强
```

---

## 5. 5 类 oncall 卡顿问题

### 5.1 5 类问题分类

| 类别 | 现象 | 第一检查 | 5 秒定位 |
|:-----|:-----|:--------|:--------|
| **G01 启动慢** | app 启动卡 2-3s | traces.txt | Displayed 字段 |
| **G02 jank 帧** | 滑动卡顿、丢帧 | systrace / perfetto | RenderThread 慢 |
| **G03 动画卡** | 动画跳帧 | Choreographer | Skipped frames |
| **G04 黑屏** | 显示黑屏 | logcat SF | Display 失败 |
| **G05 撕裂** | 屏幕撕裂 | vsync 信号 | SF vsync 错 |

### 5.2 G01 启动慢的 5 秒定位

```bash
# 1. 抓 trace
$ adb shell am start -W -n com.example.app/.MainActivity
# 期望：
# Status: ok
# Activity: com.example.app/.MainActivity
# ThisTime: 850  ← 关键
# TotalTime: 1200
# WaitTime: 1300

# 2. 看 logcat
$ adb logcat -d | grep "ActivityTaskManager: Displayed"
# "Displayed com.example.app/.MainActivity for user 0: 8500ms"

# 3. > 1s = 启动慢
#   0.5-1s = 正常
#   < 0.5s = 优

# 4. 看 perfetto 启动 trace
$ adb shell perfetto -o /data/.../startup.perfetto-trace -t 5s ...
```

### 5.3 G02 jank 帧的 5 秒定位

```bash
# 1. 抓 trace
$ adb shell perfetto -o /data/.../jank.perfetto-trace -t 30s \
  -b 64mb sched freq idle am wm gfx view binder_driver hal input

# 2. 上传 https://ui.perfetto.dev
# 3. 找 > 16ms 的帧
# 4. 哪个阶段 > 16ms
```

**关键判断**：
- Input 阶段慢 = 主线程卡
- Render 阶段慢 = GPU 渲染慢
- Compose 阶段慢 = SF 合成慢

### 5.4 G03 动画卡的 5 秒定位

```bash
# 1. 看 Choreographer 跳帧
$ adb logcat -d | grep "Choreographer.*Skipped"
# "Choreographer: Skipped 32 frames! The application may be doing too much work on its main thread."

# 2. 跳帧数 = 卡顿数
# < 5 跳 = 优
# 5-30 跳 = 中
# > 30 跳 = 卡顿严重

# 3. 抓 trace 看具体阶段
$ adb shell perfetto -o /data/.../anim.perfetto-trace -t 10s ...
```

### 5.5 G04 黑屏的 5 秒定位

```bash
# 1. 看 logcat
$ adb logcat -d -b system | grep -E "SurfaceFlinger|Display"
# 关键：
# "SurfaceFlinger: Display 0 not found"
# "Display HWComposer: device gone"
# "SurfaceFlinger: hotplug"

# 2. 看 SF 状态
$ adb shell pidof surfaceflinger
# 期望：1234
# 无 → SF 死

# 3. 看 HWC 状态
$ adb shell dumpsys SurfaceFlinger | head -50
```

### 5.6 G05 撕裂的 5 秒定位

```bash
# 1. 看 vsync 错
$ adb logcat -d -b system | grep -E "vsync|tear"
# 关键：
# "VSync event received after frame"

# 2. 强制 vsync
$ adb shell service call SurfaceFlinger 1034 i32 1

# 3. 测 perfetto 看 frame
$ adb shell perfetto -o /data/.../tear.perfetto-trace -t 10s ...
```

---

## 6. 关键性能指标

### 6.1 4 大性能指标

| 指标 | 单位 | 健康值 | 含义 |
|:-----|:-----|:------|:-----|
| **Frame rate** | fps | 60+ | 帧率 |
| **Jank rate** | % | < 1% | 丢帧率 |
| **Latency** | ms | < 16.6 | 帧延迟 |
| **Render time** | ms | < 8 | 渲染时间 |

### 6.2 5 大 perf counter

```bash
# 1. Frame 统计
$ adb shell dumpsys gfxinfo
# Total frames rendered: 1234
# Janky frames: 12
# 50th percentile: 8ms
# 90th percentile: 12ms
# 99th percentile: 25ms

# 2. SF 帧统计
$ adb shell dumpsys SurfaceFlinger | grep "Frame"
# "Frames rendered: 12345"
# "Frame latency: 8ms"

# 3. Choreographer 跳帧
$ adb shell dumpsys SurfaceFlinger | grep "Skipped"
```

### 6.3 5 大告警阈值

| 指标 | 阈值 | 含义 |
|:-----|:-----|:-----|
| Jank rate | > 1% | 卡顿 |
| 50th latency | > 10ms | 慢 |
| 99th latency | > 33ms | 严重卡顿 |
| Frame rate | < 50fps | 不流畅 |
| Skipped frames | > 30 | 卡顿严重 |

---

## 7. oncall 5 分钟决策

```
[问题] 图形相关
  ↓
[1] 30 秒判断类型（5 秒）
  ├─ "启动慢" → G01 (am start -W)
  ├─ "滑动卡" → G02 (perfetto)
  ├─ "动画跳" → G03 (Choreographer)
  ├─ "黑屏" → G04 (logcat SF)
  └─ "撕裂" → G05 (vsync)
  ↓
[2] 抓现场（30-60 秒）
  ├─ G01 → am start -W
  ├─ G02 → perfetto 30s
  ├─ G03 → logcat Choreographer
  ├─ G04 → logcat SurfaceFlinger
  └─ G05 → perfetto frame
  ↓
[3] 5 分钟定位
  ├─ Input 阶段慢 → 主线程卡 → 看主线程栈
  ├─ Render 阶段慢 → GPU 卡 → 看 RenderThread
  ├─ Compose 阶段慢 → SF 卡 → 看 SF logcat
  └─ HWC 错 → 看 HWC logcat
  ↓
[4] 出报告（5 分钟）
```

---

## 8. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md) | 下篇 |
| [03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md) | 续篇 |
| [04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md) | 续篇 |
| [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) | 续篇 |
| [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) | 续篇 |
| [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) | 续篇 |
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../05-卷5-调查方法论与工具链/31-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) | trace 工具 |
| [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md) | jank 症状 |
| [06-Foundation/Network/01 网络栈总览](../Network/01-网络栈总览：从app-socket到网卡的全链路.md) | 姊妹篇 |

---

## 9. 下一篇预告 + 自检

### 9.1 下一篇

[02 SurfaceFlinger 内部：合成 / VSync / Layer 树](02-SurfaceFlinger内部：合成-VSync-Layer树.md) 讲清：
- SurfaceFlinger 启动时初始化
- VSync 事件如何分发到 app
- Layer 树怎么管理 100+ 窗口
- 合成 GLES vs HWC 决策逻辑
- AOSP 17 合成优化（async composition）

### 9.2 看完本文的自检

- [ ] 能说 5 层架构（app / WM / SF / HWC / Display）
- [ ] 能说 16.6ms 帧时序
- [ ] 能说 12 步全链路
- [ ] 能用 5 类问题分类 5 秒定位
- [ ] 知道 4 大性能指标 + 告警阈值
- [ ] 知道 oncall 5 分钟决策树

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
