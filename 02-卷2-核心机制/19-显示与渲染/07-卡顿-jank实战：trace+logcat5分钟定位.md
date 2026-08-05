# 06-Foundation/Graphics · 07 · 卡顿 / jank 实战：trace + logcat 5 分钟定位

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 卡顿实战排查
>
> **强依赖**：[01]-[06] 图形栈全系列

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 5 大卡顿类别的完整实战排查流程（perfetto + logcat + dumpsys）讲清楚——oncall 5 分钟定位"卡顿是哪个阶段慢"
- **不是**：不复述 [01]-[06] 任一篇（实战用）；不复述 [04-Tool/Perfetto/04-Perfetto定制化实战](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/04-Perfetto定制化实战：ANR后自动抓取trace.md)（trace 工具深入）
- **承接自**：[01]-[06] 6 篇方法论 → 本文实战
- **衔接去**：[02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md) / [06-Case/Cases-Extended/](../../../06-Case/Cases-Extended/)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 2 章 5 大类别 + 第 3-5 章实战 | 收官篇实战 |
| 2 | 第 6 章 5 真实 case | oncall 5 分钟 |
| 3 | 第 10 章 7 篇引用矩阵 | 系列收官 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**卡顿（jank）= 一帧 > 16ms 用户感知——5 大类别，3 大工具（perfetto + logcat + dumpsys）组合，5 分钟定位"卡在哪"。**

AOSP 17 图形栈 7 篇收官。本文给完整实战模板：**抓现场 → 跑工具 → 解读 → 修复**。

---

## 1. 5 大 jank 类别回顾

### 1.1 16.6ms budget 的 4 阶段

| 阶段 | 健康值 | 卡顿阈值 |
|:-----|:------|:--------|
| **Input** | < 1ms | > 4ms |
| **Animation** | < 2ms | > 4ms |
| **Draw** | < 2ms | > 4ms |
| **Commit** | < 1ms | > 4ms |
| **RenderThread** | < 8ms | > 12ms |
| **Compose (SF)** | < 8ms | > 12ms |

### 1.2 5 大卡顿类别

| 类别 | 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:-----|:--------|
| **J01 主线程卡** | 滑动掉帧 | Input/Animation/Draw 慢 | Choreographer#Skipped |
| **J02 渲染卡** | 动画跳帧 | GPU 渲染慢 | RenderThread 卡 |
| **J03 合成卡** | 屏幕卡 | SF/HWC 合成慢 | SF 主线程 |
| **J04 启动卡** | 启动 2-3s | 同步初始化 | am start -W |
| **J05 黑屏** | 显示黑 | Buffer 没来 | SurfaceFlinger#BufferQueue |

---

## 2. 5 大 jank 类别实战

### 2.1 J01 主线程卡

**症状**：滑动掉帧

**5 分钟排查**：

```bash
# 1. 看跳帧日志（5 秒）
$ adb logcat -d | grep "Choreographer.*Skipped"
# "Choreographer: Skipped 30 frames!"

# 2. 抓 perfetto（30 秒）
$ adb shell perfetto -o /data/local/tmp/jank.perfetto-trace \
    -t 30s -b 64mb sched freq idle am wm gfx view

# 3. 看哪个阶段 > 16ms（5 秒）
# 在 ui.perfetto.dev 看：
# - Input 阶段 25ms（慢）
# - Draw 阶段 30ms（慢）

# 4. 看主线程栈（5 秒）
# 看到 RecyclerView.bindViewHolder 在 Input/Draw 阶段

# 5. 修法（5 分钟）
- bindViewHolder 异步
- 用 DiffUtil
- 减少 onDraw 工作
```

### 2.2 J02 渲染卡

**症状**：动画卡顿

**5 分钟排查**：

```bash
# 1. 看 Choreographer（5 秒）
$ adb logcat -d | grep "Choreographer.*Skipped"

# 2. 抓 perfetto（30 秒）
# 同上

# 3. 看 RenderThread（5 秒）
# RenderThread 30+ ms / frame

# 4. 看 GPU（5 秒）
$ adb shell dumpsys gpu
# 看到 GPU 高占用

# 5. 修法（5 分钟）
- 减少 RenderNode
- 用 LAYER_TYPE_HARDWARE
- 减 overdraw
```

### 2.3 J03 合成卡

**症状**：整个屏幕卡

**5 分钟排查**：

```bash
# 1. 看 SF 主线程（5 秒）
$ adb shell dumpsys SurfaceFlinger | grep "Main thread"
# 看到主线程跑 30+ ms

# 2. 看合成（5 秒）
$ adb shell dumpsys SurfaceFlinger | grep -E "GLES|HWC"
# 看到 GLES 合成多

# 3. 抓 perfetto（30 秒）
# SF 主线程 30+ ms

# 4. 看 HWC（5 秒）
$ adb shell dumpsys SurfaceFlinger | grep "HWC"
# HWC 异常

# 5. 修法（5 分钟）
- 减少 Layer 数
- 强制 HWC 合成
- 升级 vendor HWC 驱动
```

### 2.4 J04 启动卡

**症状**：app 启动 3 秒

**5 分钟排查**：

```bash
# 1. 看 am start -W（5 秒）
$ adb shell am start -W -n com.example.app/.MainActivity
# ThisTime: 3000ms (慢)

# 2. 看 Displayed 日志（5 秒）
$ adb logcat -d | grep "ActivityTaskManager: Displayed"
# "Displayed com.example.app/.MainActivity for user 0: 3000ms"

# 3. 抓 perfetto（30 秒）
$ adb shell perfetto -o /data/local/tmp/startup.perfetto-trace \
    -t 5s -b 64mb sched freq idle am wm gfx

# 4. 看哪个阶段（5 秒）
# 看到 onCreate 跑 2s
# 看到 layoutInflate 慢
# 看到 onCreateView 慢

# 5. 修法（5 分钟）
- 延迟初始化
- 异步 inflate
- 用 ViewStub
- ConstraintLayout 替代嵌套
```

### 2.5 J05 黑屏

**症状**：app 启动后黑屏

**5 分钟排查**：

```bash
# 1. 看 SF 状态（5 秒）
$ adb shell pidof surfaceflinger
# 1234
# SF 没死

# 2. 看 logcat（5 秒）
$ adb logcat -d -b system | grep -E "SurfaceFlinger|Display"
# 关键：
# "SurfaceFlinger: Display 0 hotplug"
# "Display HWComposer: device gone"

# 3. 看 buffer 状态（5 秒）
$ adb shell dumpsys SurfaceFlinger | grep "BufferQueue"
# 全部 FREE → app 没写

# 4. 强制重置（5 秒）
$ adb shell service call SurfaceFlinger 1034 i32 1

# 5. 修法（5 分钟）
- 强制 reset Display
- 检查 app 主线程
- 检查 BufferQueue
```

---

## 3. perfetto 实战模板

### 3.1 4 大 perfetto 数据源

| 数据源 | 抓什么 | 大小 | 何时用 |
|:-------|:-----|:-----|:----|
| **sched** | 线程调度 | 5MB | 通用 |
| **gfx** | 图形 / RenderThread | 1MB | jank |
| **view** | View 树 | 1MB | 卡顿 |
| **am** | ActivityManager | 0.5MB | 启动 |

### 3.2 标准 30 秒抓 trace

```bash
# 综合抓 trace
$ adb shell perfetto -o /data/local/tmp/jank.perfetto-trace \
    -t 30s -b 64mb \
    sched freq idle am wm gfx view binder_driver hal input

# 拉取
$ adb pull /data/local/tmp/jank.perfetto-trace

# 上传 https://ui.perfetto.dev
```

### 3.3 perfetto 4 大必看视图

#### 视图 1：CPU 调度

```
看：每个线程在不同 CPU 上的时间片
- 主线程 = 蓝色
- RenderThread = 红色
- SF 主线程 = 绿色
- HWUI binder 线程 = 黄色

判断：主线程占用率 > 80% = 主线程忙
```

#### 视图 2：Slice（关键阶段）

```
看：每个 slice 的时间
- doFrame
- doInput
- doAnimation
- doDraw
- doCommit
- recordRenderNode
- GPU 提交

判断：哪个 slice > 16ms = 慢的阶段
```

#### 视图 3：Buffer flow

```
看：BufferQueue 的 acquire / release
- acquireBuffer
- releaseBuffer
- queueBuffer

判断：fence 等待 = 同步慢
```

#### 视图 4：Frame timeline

```
看：每帧的预期 vs 实际时间
- vsync 1: expected 16.6ms, actual 16ms
- vsync 2: expected 16.6ms, actual 32ms  ← 慢

判断：每帧实际 > 16ms = 卡顿
```

### 3.4 5 大 perfetto 实战 case

#### Case 1：滑动卡主线程忙

```bash
# 抓 trace
# 在 ui.perfetto.dev 看：
# - 主线程蓝色块 25+ ms
# - 看到 onTouchEvent 跑 25ms

# 修法：
# - bindViewHolder 异步
```

#### Case 2：动画跳帧

```bash
# 抓 trace
# 看：
# - doAnimation 30+ ms
# - 复杂 ValueAnimator

# 修法：
# - 用 RenderNode 缓存
```

#### Case 3：合成卡

```bash
# 抓 trace
# 看：
# - SF 主线程 30+ ms
# - Compose 阶段慢

# 修法：
# - 减少 Layer 数
# - 强制 HWC 合成
```

#### Case 4：Buffer 卡

```bash
# 抓 trace
# 看：
# - FenceWait 100+ ms
# - acquireBuffer 等

# 修法：
# - 检查 GPU
```

#### Case 5：GPU 高

```bash
# 抓 trace
# 看：
# - GPU 持续占用
# - shader 编译

# 修法：
# - 减少 shader 复杂度
```

---

## 4. logcat 实战模板

### 4.1 5 大 logcat 过滤

```bash
# 1. 跳帧日志
$ adb logcat -d | grep "Choreographer.*Skipped"
# "Choreographer: Skipped 30 frames!"

# 2. SurfaceFlinger
$ adb logcat -d -b system | grep "SurfaceFlinger"
# SF 主线程 / Layer / BufferQueue

# 3. HWUI
$ adb logcat -d | grep -E "HWUI|hwui"
# HWUI native 渲染

# 4. HWC
$ adb logcat -d | grep -i "HWC\|composer"
# HWC 决策 / 异常

# 5. Input
$ adb logcat -d | grep "Input dispatching"
# "Input dispatching took 30ms"  ← 慢
```

### 4.2 5 大 logcat 异常解读

| 日志 | 含义 | 修法 |
|:-----|:-----|:-----|
| `Choreographer: Skipped 30 frames!` | 主线程卡 | 异步 |
| `Input dispatching took 30ms` | Input 慢 | 简化处理 |
| `BufferQueue: fence timeout` | Buffer 卡 | 看 GPU |
| `HWC: not supported` | HWC 不支持 | 改 GLES |
| `Display: hotplug` | 屏插拔 | 重建 display |

---

## 5. dumpsys 实战模板

### 5.1 5 大 dumpsys 命令

```bash
# 1. SurfaceFlinger 完整
$ adb shell dumpsys SurfaceFlinger
# - SF 状态
# - Layer 列表
# - BufferQueue
# - HWC 状态
# - VSync 状态

# 2. gfxinfo（app 渲染）
$ adb shell dumpsys gfxinfo
# - Total frames rendered
# - Janky frames
# - 50/90/99 percentile

# 3. display
$ adb shell dumpsys display
# - 所有 display
# - mode / refresh rate
# - HDR capability

# 4. SurfaceFlinger 简化（看 Layer）
$ adb shell dumpsys SurfaceFlinger | grep "BufferLayer\|ColorLayer" | head
# Layer 列表

# 5. window
$ adb shell dumpsys window
# - 所有 window
# - layer 状态
```

### 5.2 5 大 dumpsys 异常解读

| 命令 | 输出 | 含义 |
|:-----|:-----|:-----|
| `dumpsys SurfaceFlinger` | `mFrameRate: 60Hz` | 正常 |
| `dumpsys SurfaceFlinger` | `Jank rate > 1%` | 卡顿 |
| `dumpsys gfxinfo` | `Janky frames: 50` | app 卡 |
| `dumpsys display` | `Display 0: 1080x1920` | 正常 |
| `dumpsys display` | `Display 0: hotplug` | 屏插拔 |

---

## 6. 5 大真实 case 走查

### 6.1 Case 1：滑动卡顿（30 分钟到 5 秒）

```
[症状] RecyclerView 滑动卡

[5 秒]
$ adb logcat -d | grep "Choreographer.*Skipped"
# Skipped 30 frames!

[30 秒]
$ adb shell perfetto -o /tmp/jank.perfetto-trace \
    -t 30s -b 64mb sched freq idle am wm gfx view
$ adb pull /tmp/jank.perfetto-trace

[5 秒]
# ui.perfetto.dev 看：
# - onTouchEvent 25ms
# - bindViewHolder 跑 20ms
# - 主线程忙

[5 秒]
$ adb logcat -d | grep "MyApp"
# 看到 "MyApp: bindViewHolder took 20ms"

[修法]
- bindViewHolder 异步
- 用 DiffUtil
- viewType 分类
- 减少 ImageView
```

### 6.2 Case 2：启动卡顿（30 分钟到 5 分钟）

```
[症状] app 启动 3 秒

[5 秒]
$ adb shell am start -W -n com.example.app/.MainActivity
# ThisTime: 3000ms

[5 秒]
$ adb logcat -d | grep "Displayed"
# Displayed com.example.app/.MainActivity for user 0: 3000ms

[30 秒]
$ adb shell perfetto -o /tmp/startup.perfetto-trace \
    -t 5s -b 64mb sched freq idle am wm gfx
$ adb pull /tmp/startup.perfetto-trace

[5 秒]
# ui.perfetto.dev 看：
# - onCreate 1.5s
# - layoutInflate 1s
# - measure / layout 500ms

[修法]
- 延迟初始化
- 异步 inflate
- 用 ViewStub
- ConstraintLayout
```

### 6.3 Case 3：动画卡顿（5 分钟定位）

```
[症状] 启动动画跳帧

[5 秒]
$ adb logcat -d | grep "Choreographer.*Skipped"
# Skipped 50 frames!

[30 秒]
$ adb shell perfetto -o /tmp/anim.perfetto-trace \
    -t 10s -b 64mb sched freq idle gfx view
$ adb pull /tmp/anim.perfetto-trace

[5 秒]
# 看 doAnimation 30+ ms
# 复杂 ObjectAnimator

[修法]
- 减动画复杂度
- 用 RenderNode 缓存
- 改 LayoutAnimationController
```

### 6.4 Case 4：黑屏（5 分钟定位）

```
[症状] 黑屏

[5 秒]
$ adb shell pidof surfaceflinger
# 1234 (在)

[5 秒]
$ adb logcat -d -b system | grep "SurfaceFlinger\|Display"
# 关键：Display hotplug

[5 秒]
$ adb shell dumpsys SurfaceFlinger | grep "BufferQueue"
# 全部 FREE

[5 秒]
$ adb shell service call SurfaceFlinger 1034 i32 1
# 强制 reset

[修法]
- 强制 reset
- vendor HWC 升级
```

### 6.5 Case 5：合成卡顿（5 分钟定位）

```
[症状] 屏幕卡

[5 秒]
$ adb shell dumpsys SurfaceFlinger | grep "Main thread"
# 主线程 30+ ms

[5 秒]
$ adb shell dumpsys SurfaceFlinger | grep "GLES\|HWC"
# 看到 GLES 合成多

[30 秒]
$ adb shell perfetto -o /tmp/compose.perfetto-trace \
    -t 10s -b 64mb sched freq idle gfx view
$ adb pull /tmp/compose.perfetto-trace

[5 秒]
# 看 SF 主线程 30+ ms / 合成慢

[修法]
- 减少 Layer 数
- 强制 HWC 合成
$ adb shell setprop debug.sf.disable_glcomposition 1
```

---

## 7. oncall 5 分钟实战模板

```
[1] 30 秒判断（5 秒）
  ├─ "滑动卡" → J01
  ├─ "动画卡" → J02
  ├─ "屏幕卡" → J03
  ├─ "启动卡" → J04
  └─ "黑屏" → J05
  ↓
[2] 抓现场（30-60 秒）
  ├─ logcat | grep Choreographer  (5 秒)
  ├─ perfetto 30s                (30 秒)
  ├─ dumpsys SurfaceFlinger       (5 秒)
  └─ dumpsys gfxinfo              (5 秒)
  ↓
[3] 5 分钟定位
  ├─ Choreographer 跳帧 → 主线程忙
  │   └─ perfetto 看 Input/Draw 阶段
  ├─ RenderThread 卡 → GPU 渲染
  │   └─ perfetto 看 RenderThread
  ├─ SF 主线程卡 → 合成慢
  │   └─ perfetto 看 SF 主线程
  └─ HWC 错 → 显示异常
      └─ dumpsys SurfaceFlinger
  ↓
[4] 出报告（5 分钟）
  5 行：
  - 症状
  - 现场
  - 根因
  - 修复
  - 预防
```

---

## 8. 5 大调优 case

### 8.1 Case 1：启用 hardware layer

```java
// 启用 RenderNode 缓存
view.setLayerType(View.LAYER_TYPE_HARDWARE, null);
```

### 8.2 Case 2：减 overdraw

```java
// 隐藏不可见 View
view.setVisibility(View.GONE);

// 用 ViewStub 延迟 inflate
viewStub.inflate();
```

### 8.3 Case 3：异步 bind

```java
// 异步 RecyclerView bind
recyclerView.setHasFixedSize(true);
recyclerView.setItemViewCacheSize(20);
```

### 8.4 Case 4：减少 GC

```java
// 复用 Paint
private final Paint paint = new Paint();
// 不要每帧 new
```

### 8.5 Case 5：禁用 GLES 合成

```bash
# 强制 HWC 合成
$ adb shell setprop debug.sf.disable_glcomposition 1
```

---

## 9. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) | 系列起点 |
| [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md) | 合成决策 |
| [03 BufferQueue](03-BufferQueue：跨进程图形缓冲机制.md) | 跨进程 buffer |
| [04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md) | 渲染 |
| [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) | 节拍器 |
| [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) | HWC HAL |
| [04-Tool/Perfetto/01-Perfetto系统总览与架构设计](../../../../03-卷3-调查工具/22-Perfetto 全栈使用/01-Perfetto系统总览与架构设计.md) | trace 工具 |
| [02-Symptom/S09-jank/01-症状机制](../../../02-Symptom/S09-jank/01-症状机制.md) | jank 症状 |
| [06-Case/Cases-Extended/](../../../06-Case/Cases-Extended/) | 实战案例 |

---

## 10. 收官 + 7 篇引用矩阵

### 10.1 7 篇引用矩阵

```
┌─────────────────────────────────────────────────────────────┐
│  图形栈 7 篇全引用矩阵                                        │
└─────────────────────────────────────────────────────────────┘

[01] 图形栈总览 (你正在看)
  ↓ 引用 → [02-07] 全部
  ↑ 引用 ← 全部

[02] SurfaceFlinger 内部
  ↓ 引用 → [03] Buffer / [06] HWC
  ↑ 引用 ← [01] [03] [04] [07]

[03] BufferQueue
  ↓ 引用 → [04] HWUI
  ↑ 引用 ← [01] [02] [04] [07]

[04] HWUI / RenderThread
  ↓ 引用 → [05] Choreographer
  ↑ 引用 ← [01] [03] [05] [07]

[05] Choreographer / VSync
  ↓ 引用 → [07] jank 实战
  ↑ 引用 ← [01] [04] [07]

[06] HWC
  ↑ 引用 ← [01] [02] [07]

[07] jank 实战（你正在读）
  ↑ 引用 ← 全部 6 篇
```

### 10.2 7 篇核心 takeaway

- **01 总览**：5 层架构 + 16.6ms 帧时序 + 5 类问题
- **02 SF**：4 大子系统（启动 / VSync / Layer / 合成）
- **03 BufferQueue**：5 状态 + 双/三缓冲 + 4 producer / 4 consumer
- **04 HWUI**：RenderThread + DisplayList + GLES / Vulkan
- **05 Choreographer**：4 阶段 + 4 Callback + 5 大跳帧
- **06 HWC**：4 HAL 接口 + 4 capability + 5 合成类型
- **07 实战**：5 大 case + 3 工具组合（perfetto + logcat + dumpsys）

### 10.3 7 篇统一资源

- **真实工具**：perfetto / logcat / dumpsys
- **真实命令**：`adb shell perfetto`、`dumpsys SurfaceFlinger`、`dumpsys gfxinfo`
- **真实场景**：滑动 / 启动 / 动画 / 黑屏 / 合成
- **真实耗时**：5 大 case × 5 分钟 = 25 分钟定位

---

## 11. 收官 + 自检

### 11.1 看完 7 篇全系列的自检

- [ ] 能说 5 层架构（app / WM / SF / HWC / Display）
- [ ] 能说 16.6ms 帧时序 4 阶段
- [ ] 能说 5 大卡顿类别
- [ ] 能用 perfetto + logcat + dumpsys 5 分钟定位
- [ ] 能说 SF 4 大子系统
- [ ] 能说 BufferQueue 5 状态
- [ ] 能说 RenderThread 4 线程分工
- [ ] 能说 Choreographer 4 Callback
- [ ] 能说 HWC 4 capability
- [ ] 能用 5 大实战 case 走查

### 11.2 收官话

图形栈 7 篇在稳定性架构师的能力模型里属于**"机制理解" + "取证落地"两层交集**——oncall 卡顿问题的完整工具箱。

下一步推荐读：
- **P0 next**：PowerManager / 唤醒锁系列（3-5 篇）
- **P1**：启动链完整系列（5-7 篇）
- **P1**：PackageManager 完整系列（4-6 篇）

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，**图形栈 7 篇收官**）
