# 06-Foundation/Graphics · 03 · BufferQueue：跨进程图形缓冲机制

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 · oncall 工程师 · 跨进程图形 / buffer 卡顿
>
> **强依赖**：[01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) · [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 BufferQueue 跨进程 buffer 队列讲清楚——oncall 5 秒定位"buffer 卡在 app 还是 SF"
- **不是**：不复述 [02 §5 BufferQueue 简述](02-SurfaceFlinger内部：合成-VSync-Layer树.md)（本文深入跨进程机制）；不复述 [04 HWUI](04-HWUI-RenderThread：硬件加速渲染.md) / [05 Choreographer](05-Choreographer-VSync：UI节奏协调.md)（下篇专题）
- **承接自**：[02 §5 BufferQueue 4 状态](02-SurfaceFlinger内部：合成-VSync-Layer树.md) → 本文深入跨进程 / 同步 / 分配
- **衔接去**：[04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md) / [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) / [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md)

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 第 2 章 5 大状态 + 转换 | 核心 |
| 2 | 第 3 章 双 / 三缓冲对比 | 实战 |
| 3 | 第 4-5 章 producer / consumer | 跨进程核心 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 一句话定位

**BufferQueue = app 进程 → SurfaceFlinger 进程的跨进程 buffer 队列——app 写，SF 读，共享内存 + Binder fence 同步。**

AOSP 17 上 BufferQueue 跑在 `frameworks/native/libs/gui/`。理解 BufferQueue = 5 秒定位"buffer 卡在 app 渲染 / SF 合成"。

---

## 1. BufferQueue 是什么

### 1.1 一句话定义

**BufferQueue = app 进程 producer 写 buffer，SF 进程 consumer 读 buffer——通过共享内存（ashmem / gralloc）实现零拷贝。**

### 1.2 4 大特性

| 特性 | 含义 | 性能影响 |
|:-----|:-----|:--------|
| **跨进程** | app + SF 两个进程 | 同步 / fence |
| **零拷贝** | 共享内存 | 不复制像素 |
| **异步** | producer / consumer 独立 | 流水线 |
| **可计数** | buffer 数可配 | 内存控制 |

### 1.3 BufferQueue 3 大组件

```
[Producer（app）]
    │ 写 buffer
    ▼
[BufferQueue]
    │ 1. FREE
    │ 2. DEQUEUED (producer 拿到)
    │ 3. QUEUED (producer 写完)
    │ 4. ACQUIRED (consumer 拿到)
    ▼
[Consumer（SF）]
    │ 读 buffer
    ▼
[Display / HWC]
```

### 1.4 关键源码

```
frameworks/native/libs/gui/
├── IGraphicBufferProducer.cpp      ← Producer 接口
├── IGraphicBufferConsumer.cpp      ← Consumer 接口
├── BufferQueue.cpp                  ← BufferQueue 核心
├── BufferQueueCore.cpp              ← 状态机
├── Surface.cpp                       ← Surface 类
├── SurfaceControl.cpp                ← SurfaceControl
├── ConsumerListener.cpp              ← Consumer 回调
├── ICameraConsumerListener.cpp
└── ...
```

### 1.5 AOSP 17 BufferQueue 关键变化

```
AOSP 8  → BufferQueue 2.0（HIDL / gralloc 4）
AOSP 11 → Buffer sync 优化
AOSP 12 → 减少 Buffer 数（4→3）
AOSP 13 → SharedBufferPool（多 consumer 共享）
AOSP 14 → Buffer 池共享增强
AOSP 15 → Vulkan Buffer 优化
AOSP 17 → Buffer Descriptor 增强（多 plane / 10-bit HDR）
```

---

## 2. 5 大状态 + 转换

### 2.1 5 大状态

| 状态 | 含义 | 数量 |
|:-----|:-----|:-----|
| **FREE** | 空闲可写 | N-1+ |
| **DEQUEUED** | producer 拿到，正在写 | 0-1 |
| **QUEUED** | 写完等 consumer | 0-N |
| **ACQUIRED** | consumer 拿到，正在读 | 0-1 |
| **RELEASE** | consumer 用完释放（变 FREE）| 0 |

### 2.2 完整状态转换

```
[初始状态]
全部 buffer = FREE
buffer_count = N (默认 3)

[1] producer 调 dequeueBuffer()
    → 1 个 buffer 从 FREE 变 DEQUEUED
    → 返回 buffer 句柄给 producer

[2] producer 写 buffer
    → 调 GraphicBuffer::lock()
    → GLES / Vulkan 写像素

[3] producer 调 queueBuffer()
    → buffer 从 DEQUEUED 变 QUEUED
    → 通知 consumer（BufferReleased signal）

[4] consumer 调 acquireBuffer()
    → 1 个 buffer 从 QUEUED 变 ACQUIRED
    → 返回 buffer 句柄给 consumer

[5] consumer 读 buffer
    → 调 GraphicBuffer::lock()
    → 读像素

[6] consumer 调 releaseBuffer()
    → buffer 从 ACQUIRED 变 FREE
    → buffer 可被 producer 再次 dequeue
```

### 2.3 5 大异常状态

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **大量 FREE** | consumer 慢 | `dumpsys SurfaceFlinger` |
| **大量 QUEUED** | consumer 阻塞 | 看 consumer 栈 |
| **DEQUEUED 卡** | producer 渲染慢 | 看 producer 栈 |
| **ACQUIRED 卡** | SF 合成慢 | 看 SF 栈 |
| **buffer 耗尽** | 泄漏 / 卡 | `dumpsys meminfo` |

### 2.4 真实 dumpsys 输出

```bash
$ adb shell dumpsys SurfaceFlinger | grep -A10 "BufferQueue"

BufferQueue 0x1234:
  mMaxBufferCount=3
  mMaxDequeuedBufferCount=1
  mMaxAcquiredBufferCount=1
  mMaxBufferCount=3
  mBufferCount=3 (FREE=2, DEQUEUED=0, QUEUED=1, ACQUIRED=0)

# 解读：3 个 buffer，2 个空闲，1 个等 SF
```

---

## 3. 双缓冲 vs 三缓冲

### 3.1 3 大缓冲模式

| 模式 | buffer 数 | 性能 | 适用 |
|:-----|:--------|:-----|:----|
| **单缓冲** | 1 | 差 | 不推荐 |
| **双缓冲** | 2 | 中 | 简单 UI |
| **三缓冲** | 3 | 优 | AOSP 12+ 默认 |
| **四缓冲** | 4 | 优 | 4K / 高刷 |

### 3.2 双缓冲 vs 三缓冲

| 维度 | 双缓冲 | 三缓冲 |
|:-----|:-------|:------|
| **buffer 数** | 2 | 3 |
| **延迟** | 1 vsync | 2 vsync |
| **掉帧概率** | 中（vsync 抖动易掉帧）| 低（双 buffer 空闲）|
| **内存** | 省（2x 单 buffer）| 费（3x）|
| **AOSP 17 默认** | - | ✅ 三缓冲 |

### 3.3 三缓冲时序

```
[vsync 1] producer 写 buffer A
[vsync 2] producer 写 buffer B
           consumer 读 buffer A
[vsync 3] producer 写 buffer C
           consumer 读 buffer B
           buffer A 可被 producer 重写
           (此时 buffer A = FREE, B = ACQUIRED, C = QUEUED)
[vsync 4] producer 写 buffer A
           consumer 读 buffer C
           ...
```

**关键**：
- 3 buffer 流水线
- producer 永远不用等 consumer
- consumer 永远不用等 producer
- 延迟 = 2 vsync（vsync 1 写，vsync 3 显示）

### 3.4 4 大缓冲数选择策略

```java
// app 端设置 buffer 数
Surface.setMaxFrameRate(120);  // 120Hz → 2 buffer
Surface.setMaxFrameRate(60);   // 60Hz → 3 buffer
Surface.setMaxFrameRate(30);   // 30Hz → 4 buffer
// buffer 数 = max(1, 2 * target_latency / vsync)
```

**关键洞察**：
- 高刷 (120Hz) → buffer 少（2 个）
- 低刷 (30Hz) → buffer 多（4 个）
- 平衡延迟 / 内存

### 3.5 5 大 buffer 异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **buffer 1 个** | 单缓冲 | 改成 3 |
| **buffer 5+ 个** | 泄漏 | 看 buffer 引用 |
| **buffer 切换频繁** | fence 失效 | 看 fence 状态 |
| **buffer 卡** | producer 慢 | 看 producer 栈 |
| **buffer 撕裂** | 同步失效 | 看同步机制 |

---

## 4. 4 大 Producer（写入方）

### 4.1 4 种 producer

| Producer | 进程 | 路径 | 用途 |
|:---------|:-----|:-----|:-----|
| **app HWUI** | app | `frameworks/base/libs/hwui/` | 普通 app 窗口 |
| **MediaCodec** | app / system | `frameworks/av/media/libstagefright/` | 视频解码 |
| **Camera2** | app / system | `frameworks/av/services/camera/` | 相机预览 |
| **SurfaceFlinger (合成)** | SF | `frameworks/native/services/surfaceflinger/` | 合成结果 |

### 4.2 app HWUI 写入时序

```
[1] HWUI 收到 VSync
[2] 触发 onDraw
[3] 生成 RenderNode 树
[4] RenderThread 跑 GLES / Vulkan
[5] 通过 EGL 写入 Surface
[6] Surface 内部调 eglSwapBuffers
[7] → BufferQueue::queueBuffer()
[8] → 通知 SF

[关键]: app producer 阻塞时，SF 也阻塞（同步机制）
```

### 4.3 MediaCodec 写入时序

```
[1] MediaCodec 收到 input buffer
[2] 解码器跑（VPU / DSP / CPU）
[3] 输出解码后 frame（NV12 / YUV）
[4] 通过 SurfaceTexture 写入
[5] → BufferQueue::queueBuffer()
[6] → 通知 SF

[关键]: 视频解码慢 = 整个 pipeline 慢
```

### 4.4 Producer 5 大异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **app producer 慢** | onDraw 重 | 看主线程 |
| **MediaCodec producer 慢** | 解码慢 | 看 codec |
| **Camera producer 慢** | 拍照慢 | 看 camera |
| **SF producer 慢** | 合成慢 | 看 SF |
| **producer 阻塞** | 同步机制卡 | 看 fence |

---

## 5. 4 大 Consumer（读取方）

### 5.1 4 种 consumer

| Consumer | 进程 | 路径 | 用途 |
|:---------|:-----|:-----|:-----|
| **SurfaceFlinger** | SF | `frameworks/native/services/surfaceflinger/` | 合成 |
| **MediaCodec (录屏)** | system | `frameworks/av/media/libstagefright/` | 录屏 |
| **TextureView** | app | `frameworks/base/core/java/android/view/TextureView.java` | 预览 |
| **Camera HAL** | system | `hardware/interfaces/camera/` | camera 拍照 |

### 5.2 SF 读取时序

```
[1] SF 主线程循环
[2] traverseLayers()
[3] 对每 Layer：
    - acquireBuffer()
    - 读 buffer
    - 合成（GLES / HWC）
    - releaseBuffer()
[4] HWC::present()
[5] 提交 Display

[关键]: SF 主线程卡 = 整个屏幕卡
```

### 5.3 SF 主线程周期（AOSP 17）

```
[1] 收到 VSync（来自 Display 控制器）
[2] preComposition() - 准备
[3] updateVisibleRegions() - 更新可见区域
[4] 遍历所有 Layer
[5] rebuildLayerStacks() - 重建 stack
[6] computeVisibleRegions() - 计算可见
[7] 调 HWC
[8] 等 Fence
[9] postComposition() - 收尾

总耗时需 < 16ms（60Hz）/ < 8.3ms（120Hz）
```

### 5.4 Consumer 5 大异常

| 现象 | 根因 | 5 秒定位 |
|:-----|:-----|:--------|
| **SF 消费慢** | 合成慢 | 看 perfetto |
| **MediaCodec 消费慢** | 编码慢 | 看 codec |
| **TextureView 慢** | GPU 读 | 看 GLES |
| **Fence 等** | 异步未完成 | `dumpsys SurfaceFlinger` |
| **Consumer 卡死** | 引用未释放 | 看 leak |

---

## 6. Buffer 分配策略

### 6.1 4 大分配参数

| 参数 | 默认 | 含义 |
|:-----|:-----|:-----|
| `minUndequeuedBuffers` | 1 | producer 至少保留 |
| `maxBufferCount` | 3 | 最大 buffer 数 |
| `minBufferCount` | 2 | 最小 buffer 数 |
| `bufferSize` | (W, H, format) | 单 buffer 大小 |

### 6.2 4 大 buffer 格式

| 格式 | 含义 | 用途 |
|:-----|:-----|:-----|
| **RGBA_8888** | 标准 | 普通 UI |
| **RGBX_8888** | 不透明 | 状态栏 |
| **BGRA_8888** | GPU 优化 | 视频 |
| **YUV_420_888** | 视频 | 相机 / 视频 |
| **NV21** | 视频 | 旧 API |
| **HAL_PIXEL_FORMAT_YCbCr_420_888** | HAL | 硬件 |

### 6.3 4 大 buffer 尺寸优化

```bash
# 1. 减小 buffer 尺寸
$ adb shell setprop debug.sf.shrink_buffer 0.5
# 50% 缩放

# 2. 减少 buffer 数
$ adb shell setprop debug.gr.num_buffers 2
# 默认 3 → 2

# 3. 启用 Secure buffer（DRM 内容）
$ adb shell setprop debug.sf.secure_buffer 1

# 4. 禁用 multi-buffer
$ adb shell setprop debug.sf.single_buffer 1
# 单 buffer（debug）
```

### 6.4 buffer 异常诊断

```bash
# 1. 看 buffer 分配
$ adb shell dumpsys SurfaceFlinger | grep -A5 "Allocated"
# mBufferCount: 3
# mBufferSize: 8294400 bytes (1920x1080 RGBA_8888)

# 2. 看 buffer 引用
$ adb shell lsof | grep "buffer"

# 3. 看 buffer 泄漏
$ adb shell dumpsys meminfo surfaceflinger
# Graphics: 30 MB (24 MB buffer)
# 30+ MB = 可能泄漏
```

---

## 7. 5 大实战 case

### 7.1 Case 1：滑动卡 buffer 耗尽

```
[症状] 滑动卡顿

[Step 1] 看 buffer 状态
$ adb shell dumpsys SurfaceFlinger | grep -A10 "BufferQueue"
# 全部 buffer 都 QUEUED

[Step 2] 看 SF 消费
# SF 合成慢 → buffer 累积

[Step 3] 抓 perfetto
# SF 主线程 20+ ms / frame

[Step 4] 看哪些 Layer 多
$ adb shell dumpsys SurfaceFlinger | grep "BufferLayer" | wc -l
# 50+ → 多

[Step 5] 修法
- 减少 Layer 数
- 合并 layer
- 强制 HWC 合成
```

### 7.2 Case 2：视频卡 producer 慢

```
[症状] 视频 app 卡顿

[Step 1] 看 MediaCodec
$ adb shell dumpsys media.player
# 或 dumpsys media.codec

[Step 2] 看 producer 端
# MediaCodec 输出 frame 慢

[Step 3] 抓 perfetto
# 视频解码 30+ ms

[Step 4] 看 codec 配置
# 分辨率 / 码率 / fps 过高

[Step 5] 修法
- 降码率
- 用硬件解码
- 减少并发解码
```

### 7.3 Case 3：黑屏 buffer 卡

```
[症状] app 启动后黑屏

[Step 1] 看 buffer
$ adb shell dumpsys SurfaceFlinger | grep -A5 "BufferQueue"
# 全部 FREE → app 没写

[Step 2] 看 app 状态
$ adb shell "dumpsys activity activities | grep MyApp"
# 期望：RESUMED

[Step 3] 看主线程
# 主线程卡 = 没绘制 = 没写 buffer

[Step 4] 抓 trace
# 找主线程阻塞点

[Step 5] 修法
- 主线程同步逻辑改异步
- 减少 onCreate 工作
```

### 7.4 Case 4：撕裂 buffer 同步失效

```
[症状] 屏幕有水平横线

[Step 1] 看 buffer 同步
$ adb shell dumpsys SurfaceFlinger | grep "Fence"
# FenceWait 100+ ms

[Step 2] 看 producer / consumer 同步
# 同步失效 = buffer 没等写完就被读

[Step 3] 强制 sync
$ adb shell setprop debug.sf.disable_async 1

[Step 4] 测
# 撕裂消失

[Step 5] 修法
- 用 GPU fence 同步
- 禁 async composition
```

### 7.5 Case 5：buffer 泄漏

```
[症状] 内存涨 100MB 不释放

[Step 1] 看 buffer 引用
$ adb shell lsof | grep "GraphicBuffer"
# 期望 < 10 个

[Step 2] 看 SurfaceFlinger 内存
$ adb shell dumpsys meminfo surfaceflinger
# Graphics: 100+ MB

[Step 3] 看 buffer 数
$ adb shell dumpsys SurfaceFlinger | grep "BufferCount"
# 总数过多

[Step 4] 找泄漏 app
# 按 app 分类

[Step 5] 修法
- app releaseBuffer
- 关闭不用的 Surface
```

---

## 8. oncall 5 分钟决策

```
[问题] BufferQueue 相关
  ↓
[1] 30 秒判断（5 秒）
  ├─ "buffer 耗尽" → dumpsys SurfaceFlinger | grep Buffer
  ├─ "producer 慢" → perfetto app 进程
  ├─ "consumer 慢" → perfetto SF 进程
  ├─ "Fence 等" → dumpsys SurfaceFlinger | grep Fence
  └─ "buffer 泄漏" → dumpsys meminfo
  ↓
[2] 抓现场（30-60 秒）
  ├─ dumpsys SurfaceFlinger
  ├─ perfetto 30s
  ├─ dumpsys meminfo
  └─ lsof
  ↓
[3] 5 分钟定位
  ├─ producer 慢 → 看 app 主线程
  ├─ consumer 慢 → 看 SF 主线程
  ├─ Fence 等 → 查 GPU
  └─ buffer 泄漏 → 查 Surface 引用
  ↓
[4] 出报告（5 分钟）
```

---

## 9. 5 大调优 case

### 9.1 Case 1：减少 buffer 数

```bash
# 改 buffer 数为 2
$ adb shell setprop debug.gr.num_buffers 2
# 重启 SF
```

### 9.2 Case 2：增大 buffer 数

```bash
# 改 buffer 数为 4
$ adb shell setprop debug.gr.num_buffers 4
# 高刷屏需要
```

### 9.3 Case 3：禁用 multi-buffer

```bash
# 单 buffer（debug 用）
$ adb shell setprop debug.sf.single_buffer 1
```

### 9.4 Case 4：启用 Secure buffer

```bash
# 启用 secure buffer
$ adb shell setprop debug.sf.secure_buffer 1
# 用于 DRM 内容
```

### 9.5 Case 5：禁用 buffer 缓存

```bash
# 禁用 buffer 缓存
$ adb shell setprop debug.sf.disable_buffer_cache 1
# 释放更多内存
```

---

## 10. 与 smc-pub 其他文章的对接

| smc-pub 已有文章 | 关系 |
|:----------------|:-----|
| [01 图形栈总览](01-图形栈总览：app-WindowManager-SurfaceFlinger-HWC-Display.md) | 上篇 |
| [02 SurfaceFlinger 内部](02-SurfaceFlinger内部：合成-VSync-Layer树.md) | 上篇 |
| [04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md) | 续篇 |
| [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) | 续篇 |
| [06 HWC](06-HWC（Hardware-Composer）：display-HAL抽象.md) | 续篇 |
| [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) | 续篇 |
| [01-Mechanism/Kernel/Memory_Management/02-一个byte的双重视角](../../../01-Mechanism/Kernel/Memory_Management/02-一个byte的双重视角：加载与运行的融会贯通.md) | 内存机制 |

---

## 11. 收官 + 自检

### 11.1 看完本文的自检

- [ ] 能说 BufferQueue 4 大特性
- [ ] 能说 5 大状态 + 转换
- [ ] 能区分双 / 三缓冲
- [ ] 能说 4 大 producer / consumer
- [ ] 能用 dumpsys SurfaceFlinger 5 秒看 buffer
- [ ] 知道 5 大实战 case 修法
- [ ] 知道 5 大调优 case

### 11.2 收官话

BufferQueue 在图形栈里属于**"传输层"**——app → SF 的跨进程 buffer 流水线。

下一步推荐读：
- [04 HWUI / RenderThread](04-HWUI-RenderThread：硬件加速渲染.md) — 渲染线程
- [05 Choreographer / VSync](05-Choreographer-VSync：UI节奏协调.md) — VSync 协调
- [07 jank 实战](07-卡顿-jank实战：trace+logcat5分钟定位.md) — 综合实战

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-27（v1，首发）
