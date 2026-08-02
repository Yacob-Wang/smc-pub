# 05-Surface 管理与 SurfaceFlinger 交互

## 1. Surface 在 Window 架构中的位置

### 1.1 Window 与 Surface 的关系

在前几篇中我们已经知道，Window 是一个管理抽象——它由 `WindowState`、`LayoutParams`、`InputChannel` 三要素构成。但 Window 本身不能"显示"任何东西，真正承载像素数据的是 **Surface**。每个可见的 Window 都必须拥有一个 Surface，Surface 背后是 SurfaceFlinger 管理的图形缓冲区（GraphicBuffer）。

**用一句话概括：Window 是管理抽象，Surface 是绘制实体。WMS 管理 Window 的生命周期和属性，SurfaceFlinger 管理 Surface 的缓冲区和合成。**

### 1.2 全链路架构图

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                               App 进程                                       │
│                                                                              │
│  ViewRootImpl                                                                │
│    │ performTraversals()                                                     │
│    │   → relayoutWindow()       ← 获取 Surface                              │
│    │   → measure → layout → draw                                             │
│    │                                                                         │
│    │ draw 路径:                                                              │
│    │   Canvas (软件渲染) → Surface.lockCanvas() → 写入 GraphicBuffer         │
│    │   或                                                                    │
│    │   RenderThread (硬件加速) → EGL → GPU → 写入 GraphicBuffer              │
│    │                                                                         │
│    │ 绘制完成:                                                               │
│    │   Surface.unlockCanvasAndPost() / eglSwapBuffers()                      │
│    │   → BufferQueue.queueBuffer() → 通知 SurfaceFlinger                    │
│    │                                                                         │
├──────────── Binder IPC ──────────────────────────────────────────────────────┤
│                            system_server 进程                                 │
│                                                                              │
│  WindowManagerService                                                        │
│    │ 持有 SurfaceControl (每个 WindowState 一个)                              │
│    │   → SurfaceControl 是 SurfaceFlinger Layer 的句柄                       │
│    │                                                                         │
│    │ 通过 SurfaceControl.Transaction 批量操作:                                │
│    │   → setPosition / setLayer / setAlpha / show / hide / reparent          │
│    │   → Transaction.apply() → 原子提交到 SurfaceFlinger                     │
│    │                                                                         │
├──────────── Binder IPC ──────────────────────────────────────────────────────┤
│                           SurfaceFlinger 进程                                 │
│                                                                              │
│  Layer 树 (镜像 SurfaceControl 层级)                                          │
│    │                                                                         │
│    │ 每个 Layer:                                                             │
│    │   → BufferQueue (生产者-消费者模型)                                      │
│    │   → acquireBuffer() → 获取 App 最新帧                                   │
│    │                                                                         │
│    │ VSYNC-sf 信号到达:                                                      │
│    │   → latchBuffer (从每个 Layer 获取最新 Buffer)                           │
│    │   → computeVisibleRegion (计算可见区域)                                  │
│    │   → composite (HWC 硬件合成 或 GPU 合成)                                │
│    │   → presentDisplay → 输出到屏幕                                         │
│    │                                                                         │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 本篇覆盖范围

```
本篇深入以下五个核心主题:

  WMS 如何通过 SurfaceControl 控制 Layer?          → 第 2 节
  Transaction 如何保证操作原子性?                   → 第 3 节
  BufferQueue 的生产者-消费者模型如何运作?           → 第 4 节
  SurfaceFlinger 如何将所有 Layer 合成为最终画面?    → 第 5 节
  WMS 如何管理 Surface 的创建/显示/隐藏/销毁?       → 第 6 节
```

---

## 2. SurfaceControl — WMS 与 SurfaceFlinger 的桥梁

### 2.1 SurfaceControl 是什么

`SurfaceControl` 是 WMS 侧持有的一个句柄对象，它对应 SurfaceFlinger 中的一个 **Layer**。WMS 不直接操作 SurfaceFlinger 的 Layer，而是通过 `SurfaceControl` 提供的 API 间接控制 Layer 的位置、大小、透明度、层级、可见性等属性。

> 源码路径：`frameworks/base/core/java/android/view/SurfaceControl.java`

```java
// frameworks/base/core/java/android/view/SurfaceControl.java（简化）
public final class SurfaceControl implements Parcelable {
    // Native 侧 sp<SurfaceControl> 的指针
    long mNativeObject;

    // Layer 名称（用于调试，如 "com.example.app/MainActivity#0"）
    private String mName;

    // 宽高
    private int mWidth;
    private int mHeight;

    // 通过 Builder 模式创建
    public static class Builder {
        private SurfaceSession mSession;  // 与 SurfaceFlinger 的连接
        private String mName;
        private int mWidth;
        private int mHeight;
        private int mFormat = PixelFormat.OPAQUE;
        private int mFlags;
        private SurfaceControl mParent;   // 父 SurfaceControl（层级关系）

        public Builder setName(String name) { mName = name; return this; }
        public Builder setBufferSize(int w, int h) { mWidth = w; mHeight = h; return this; }
        public Builder setFormat(int format) { mFormat = format; return this; }
        public Builder setParent(SurfaceControl parent) { mParent = parent; return this; }

        public SurfaceControl build() {
            // → JNI → SurfaceComposerClient::createSurface()
            // → Binder → SurfaceFlinger::createLayer()
            return new SurfaceControl(mSession, mName, mWidth, mHeight,
                    mFormat, mFlags, mParent, /* ... */);
        }
    }
}
```

### 2.2 SurfaceControl 的层级映射

SurfaceControl 的层级结构与 WindowContainer 树一一对应。WMS 中每个 `WindowContainer` 节点都可能持有一个 `SurfaceControl`，这些 SurfaceControl 通过 `setParent()` 构成树形结构，最终映射到 SurfaceFlinger 的 Layer 树：

```
WindowContainer 树 (WMS)              SurfaceControl 树           SurfaceFlinger Layer 树
─────────────────────────             ──────────────────          ──────────────────────

RootWindowContainer                   SC("Root")                  Layer("Root")
 └── DisplayContent                    └── SC("Display 0")        └── Layer("Display 0")
      ├── TaskDisplayArea                   ├── SC("TDA")               ├── Layer("TDA")
      │    └── Task                         │    └── SC("Task#5")       │    └── Layer("Task#5")
      │         └── ActivityRecord          │         └── SC("Act")     │         └── Layer("Act")
      │              └── WindowState        │              └── SC(*)    │              └── Layer(*)
      └── DisplayArea(StatusBar)            └── SC("StatusBar")         └── Layer("StatusBar")
           └── WindowState                       └── SC(*)                   └── Layer(*)

*注：SC = SurfaceControl
```

每个 `WindowState` 在创建 Surface 时（`createSurfaceLocked()`），会通过 `SurfaceControl.Builder` 创建一个 SurfaceControl，并将其 parent 设置为所属 `WindowContainer`（通常是 `ActivityRecord`）的 SurfaceControl。这保证了 SurfaceFlinger 侧的 Layer 层级与 WMS 的窗口层级始终一致。

### 2.3 JNI 桥梁

Java 层的 `SurfaceControl` 通过 JNI 调用到 Native 层的 `SurfaceComposerClient`：

```
Java:   SurfaceControl.Builder.build()
  ↓ JNI
Native: android_view_SurfaceControl.cpp
        → nativeCreate()
          ↓
        SurfaceComposerClient::createSurface()
          ↓ Binder IPC
        SurfaceFlinger::createLayer()
          → 创建 BufferLayer / ColorLayer / ContainerLayer
          → 返回 Layer Handle
```

> 源码路径：
> - JNI 桥梁：`frameworks/base/core/jni/android_view_SurfaceControl.cpp`
> - Native Client：`frameworks/native/libs/gui/SurfaceComposerClient.cpp`
> - SurfaceFlinger：`frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp`

### 2.4 SurfaceControl 的关键操作

| 操作 | API | 效果 | 典型调用场景 |
|:---|:---|:---|:---|
| 设置位置 | `setPosition(x, y)` | 改变 Layer 在屏幕上的偏移 | 窗口布局计算后 |
| 设置层级 | `setLayer(z)` | 改变 Layer 的 Z-order | `assignChildLayers()` |
| 设置透明度 | `setAlpha(alpha)` | 改变 Layer 的透明度 | 窗口动画、淡入淡出 |
| 设置变换矩阵 | `setMatrix(a, b, c, d)` | 缩放/旋转 Layer | 窗口动画、屏幕旋转 |
| 设置缓冲区大小 | `setBufferSize(w, h)` | 改变 Layer 的缓冲区尺寸 | 窗口大小变化 |
| 显示 | `show()` | 使 Layer 可见 | 窗口首次绘制完成后 |
| 隐藏 | `hide()` | 使 Layer 不可见 | 窗口最小化/遮挡 |
| 重新挂载 | `reparent(newParent)` | 移动到新的父 Layer | 窗口动画 Leash 机制 |
| 销毁 | `release()` | 释放 Layer 资源 | 窗口移除时 |

> **稳定性架构师视角：** SurfaceControl 是 Native 资源，其泄漏不会被 Java GC 检测到。如果 `WindowState` 被移除但 `SurfaceControl.release()` 未被调用，SurfaceFlinger 侧的 Layer 和关联的 GraphicBuffer 将持续占用显存。长时间运行的 Service 创建的悬浮窗（`TYPE_APPLICATION_OVERLAY`）是 SurfaceControl 泄漏的高发区——Service 生命周期远超 Activity，一旦遗忘释放就会持续积累。排查方法：`dumpsys SurfaceFlinger --list` 查看 Layer 数量趋势。

### 2.5 SurfaceControl 的 use-after-release

```java
// 危险示例：SurfaceControl 已 release 后仍被使用
SurfaceControl sc = new SurfaceControl.Builder().setName("test").build();
sc.release();  // 释放

SurfaceControl.Transaction t = new SurfaceControl.Transaction();
t.setAlpha(sc, 0.5f);  // ← Native crash! use-after-free
t.apply();
```

当 `SurfaceControl.release()` 被调用后，Native 侧的 `sp<SurfaceControl>` 被释放。此后任何对该 SurfaceControl 的操作都会触发 Native crash（SIGSEGV）。在 WMS 中，这种情况最常出现在窗口动画与窗口移除的竞态中——动画还在使用 SurfaceControl 设置 alpha/position，但 `removeImmediately()` 已经释放了它。

---

## 3. Transaction 机制

### 3.1 为什么需要 Transaction

想象这样一个场景：窗口需要同时改变位置和大小。如果逐个调用 `setPosition()` 和 `setBufferSize()`，用户可能在一帧内看到"位置已变、大小未变"的中间状态——窗口出现在新位置但仍是旧尺寸，下一帧才恢复正确。

**Transaction 机制解决了这个问题：将多个 Surface 操作打包成一个原子操作，要么全部生效，要么全部不生效。**

### 3.2 Transaction 的使用模式

> 源码路径：`frameworks/base/core/java/android/view/SurfaceControl.java`（Transaction 内部类）

```java
// frameworks/base/core/java/android/view/SurfaceControl.java（简化）
public static class Transaction implements Closeable {
    // Native 侧的 Parcel，存储所有待提交的操作
    long mNativeObject;

    // 批量操作方法——每个调用只是将操作记录到内部 buffer
    public Transaction setPosition(SurfaceControl sc, float x, float y) {
        nativeSetPosition(mNativeObject, sc.mNativeObject, x, y);
        return this;
    }

    public Transaction setLayer(SurfaceControl sc, int z) {
        nativeSetLayer(mNativeObject, sc.mNativeObject, z);
        return this;
    }

    public Transaction setAlpha(SurfaceControl sc, float alpha) {
        nativeSetAlpha(mNativeObject, sc.mNativeObject, alpha);
        return this;
    }

    public Transaction setBufferSize(SurfaceControl sc, int w, int h) {
        nativeSetSize(mNativeObject, sc.mNativeObject, w, h);
        return this;
    }

    public Transaction show(SurfaceControl sc) {
        nativeSetFlags(mNativeObject, sc.mNativeObject, 0, SURFACE_HIDDEN);
        return this;
    }

    public Transaction hide(SurfaceControl sc) {
        nativeSetFlags(mNativeObject, sc.mNativeObject, SURFACE_HIDDEN, SURFACE_HIDDEN);
        return this;
    }

    public Transaction reparent(SurfaceControl sc, SurfaceControl newParent) {
        nativeReparent(mNativeObject, sc.mNativeObject,
                newParent != null ? newParent.mNativeObject : 0);
        return this;
    }

    public Transaction setVisibility(SurfaceControl sc, boolean visible) {
        return visible ? show(sc) : hide(sc);
    }

    // ★ 核心方法：原子提交所有操作到 SurfaceFlinger
    public void apply() {
        apply(false /* sync */);
    }

    public void apply(boolean sync) {
        // → JNI → SurfaceComposerClient::Transaction::apply()
        // → Binder → SurfaceFlinger::setTransactionState()
        nativeApply(mNativeObject, sync);
    }
}
```

### 3.3 WMS 中的 Transaction 使用

WMS 在 `performSurfacePlacement()` 结束时，通过 Transaction 将所有窗口的属性变化一次性提交给 SurfaceFlinger：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java（简化）
void prepareSurfaces() {
    SurfaceControl.Transaction t = getSyncTransaction();

    if (isVisibleRequested()) {
        t.show(mSurfaceControl);
        t.setPosition(mSurfaceControl,
                mWindowFrames.mFrame.left, mWindowFrames.mFrame.top);
        t.setBufferSize(mSurfaceControl,
                mWindowFrames.mFrame.width(), mWindowFrames.mFrame.height());
        t.setAlpha(mSurfaceControl, mAlpha);
    } else {
        t.hide(mSurfaceControl);
    }
}
```

```java
// frameworks/base/services/core/java/com/android/server/wm/RootWindowContainer.java（简化）
void performSurfacePlacementNoTrace() {
    // 1. 遍历所有 WindowContainer，调用 prepareSurfaces()
    //    每个节点将自己的变化写入 Transaction
    mWmService.openSurfaceTransaction();

    forAllDisplays(dc -> {
        dc.forAllWindows(w -> w.prepareSurfaces(), false);
    });

    // 2. 一次性提交所有变化
    mWmService.closeSurfaceTransaction("performSurfacePlacement");
    // → SurfaceControl.Transaction.apply()
    // → SurfaceFlinger 原子生效
}
```

### 3.4 同步 Transaction 与异步 Transaction

| 类型 | `apply(sync)` | 行为 | 使用场景 |
|:---|:---|:---|:---|
| 异步 | `apply(false)` | 提交后立即返回，SurfaceFlinger 在下一个 VSYNC 处理 | 常规布局更新 |
| 同步 | `apply(true)` | 提交后阻塞等待 SurfaceFlinger 处理完成 | 需要确保 Surface 状态已生效的场景（如截图） |

> **稳定性架构师视角：** Transaction 相关的稳定性风险主要有两类：
>
> 1. **Transaction 未 apply**：WMS 通过 `openSurfaceTransaction()` / `closeSurfaceTransaction()` 管理 Transaction 的生命周期。如果 `closeSurfaceTransaction` 因异常未被调用，Transaction 中的操作不会提交到 SurfaceFlinger，用户看到的窗口状态与 WMS 内部状态不一致——典型表现是窗口位置/大小/可见性不更新。
>
> 2. **Transaction 过大**：当屏幕上窗口数量很多（如大量悬浮窗、分屏模式下多 Task），单次 Transaction 中的操作数据量可能很大，`apply()` 的 Binder 传输耗时增加。极端情况下可能触发 `TransactionTooLargeException` 或 SurfaceFlinger 处理超时。

---

## 4. Buffer 与 BufferQueue

### 4.1 GraphicBuffer — 像素数据的载体

`GraphicBuffer` 是 Android 图形系统中承载像素数据的内存块。它由 Gralloc HAL 分配，可以在 CPU 和 GPU 之间共享。一个典型的 1080p RGBA_8888 Buffer 占用约 8MB（1920 × 1080 × 4 bytes）。

> 源码路径：
> - `frameworks/native/libs/ui/GraphicBuffer.cpp`
> - `frameworks/native/libs/gui/BufferQueueProducer.cpp`
> - `frameworks/native/libs/gui/BufferQueueConsumer.cpp`

### 4.2 BufferQueue — 生产者-消费者模型

每个可见的 Surface 背后都有一个 `BufferQueue`，它连接了 App（生产者）和 SurfaceFlinger（消费者）：

```
┌──────────────────────────────────────────────────────────────────────┐
│                        BufferQueue                                    │
│                                                                      │
│  App (Producer)                                  SurfaceFlinger      │
│  ──────────────                                  (Consumer)          │
│                                                  ──────────────     │
│  ① dequeueBuffer()                                                  │
│     → 从 Free 队列中获取一个空闲 Buffer                              │
│     → 如果没有空闲 Buffer → 阻塞等待                                 │
│                                                                      │
│  ② lock() (CPU渲染) 或 bindTexture() (GPU渲染)                      │
│     → App 获得对 Buffer 的写入权限                                   │
│                                                                      │
│  ③ 绘制内容到 Buffer                                                │
│     → Canvas 软件渲染 / OpenGL ES GPU 渲染                           │
│                                                                      │
│  ④ queueBuffer()                                                    │
│     → 将已绘制的 Buffer 放入 Queued 队列                             │
│     → 通知 SurfaceFlinger 有新帧可用                                 │
│                                                                      │
│                        ⑤ acquireBuffer()                             │
│                           → SF 从 Queued 队列获取最新 Buffer          │
│                                                                      │
│                        ⑥ 合成到最终画面                              │
│                           → HWC 或 GPU 合成                          │
│                                                                      │
│                        ⑦ releaseBuffer()                             │
│                           → 将 Buffer 归还到 Free 队列               │
│                           → App 可以再次 dequeue 使用                 │
│                                                                      │
│  Buffer 状态流转:                                                    │
│                                                                      │
│  ┌──────┐  dequeue  ┌──────────┐  queue  ┌────────┐  acquire  ┌────┐│
│  │ FREE │ ────────→ │ DEQUEUED │ ──────→ │ QUEUED │ ────────→ │ ACQ││
│  └──┬───┘           └──────────┘         └────────┘           └──┬─┘│
│     │                                                            │   │
│     └──────────────── release ◀──────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.3 三缓冲（Triple Buffering）

Android 默认使用三缓冲模式：BufferQueue 中最多有 3 个 GraphicBuffer 同时存在。三个 Buffer 在不同时刻分别扮演不同角色：

```
时刻 T:
  Buffer A: App 正在绘制 (DEQUEUED)
  Buffer B: 在 Queued 队列中等待 SF 取用 (QUEUED)
  Buffer C: SF 正在合成，或者在 Display 上扫描输出 (ACQUIRED)

时刻 T+1 (VSYNC 到达):
  Buffer A: App 绘制完成，放入 Queued 队列 (QUEUED)
  Buffer B: SF 取用开始合成 (ACQUIRED)
  Buffer C: 合成完成，归还到 Free 队列 (FREE)
  App dequeue Buffer C，开始绘制下一帧
```

三缓冲的优势是减少 App 等待 Buffer 释放的概率，降低掉帧风险。代价是多占一个 Buffer 的内存（约 8MB）。

### 4.4 BufferQueue 的源码结构

```cpp
// frameworks/native/libs/gui/BufferQueueProducer.cpp（简化）
status_t BufferQueueProducer::dequeueBuffer(int* outSlot, sp<Fence>* outFence,
        uint32_t width, uint32_t height, PixelFormat format, uint64_t usage,
        FrameEventHistoryDelta* outTimestamps) {
    // 在 mSlots 数组中寻找 FREE 状态的 slot
    // 如果找不到 → 等待 Consumer 释放（阻塞或返回 WOULD_BLOCK）
    for (int i = 0; i < BufferQueueDefs::NUM_BUFFER_SLOTS; i++) {
        if (mSlots[i].mBufferState.isFree()) {
            *outSlot = i;
            mSlots[i].mBufferState.dequeue();
            return OK;
        }
    }
    // 没有可用 Buffer → 阻塞等待
    mDequeueCondition.wait(mMutex);
    // ...
}

status_t BufferQueueProducer::queueBuffer(int slot,
        const QueueBufferInput& input, QueueBufferOutput* output) {
    // 将 DEQUEUED 状态的 Buffer 转为 QUEUED
    mSlots[slot].mBufferState.queue();
    // 通知 Consumer (SurfaceFlinger) 有新帧
    frameAvailableListener->onFrameAvailable(item);
    return OK;
}
```

```cpp
// frameworks/native/libs/gui/BufferQueueConsumer.cpp（简化）
status_t BufferQueueConsumer::acquireBuffer(BufferItem* outBuffer,
        nsecs_t expectedPresent) {
    // 从 Queued 队列取出最新的 Buffer
    // 如果有多帧排队，可能跳过旧帧（仅取最新）
    mSlots[slot].mBufferState.acquire();
    return OK;
}

status_t BufferQueueConsumer::releaseBuffer(int slot, ...) {
    // 将 ACQUIRED 状态的 Buffer 归还为 FREE
    mSlots[slot].mBufferState.release();
    // 通知 Producer 有 Buffer 可用
    mDequeueCondition.broadcast();
    return OK;
}
```

### 4.5 Buffer 与稳定性

> **稳定性架构师视角：** BufferQueue 是掉帧和 ANR 的关键路径。两类典型问题：
>
> **1. Buffer 耗尽（dequeueBuffer 阻塞）：** 当 App 绘制速度远慢于 VSYNC 频率时，3 个 Buffer 全部处于 DEQUEUED 或 ACQUIRED 状态，`dequeueBuffer()` 会阻塞 App 的渲染线程。如果阻塞发生在主线程（软件渲染路径），会直接导致 `finishInputEvent()` 无法及时回复 → Input ANR。Systrace 中的特征是 `dequeueBuffer` 耗时异常长（正常 <1ms，异常可达 16ms+）。
>
> **2. Buffer 泄漏：** 如果 App dequeue 了 Buffer 但从未 queue 回去（如渲染线程异常退出），该 Buffer 将永远处于 DEQUEUED 状态，无法被回收。多次泄漏后 BufferQueue 中所有 Buffer 耗尽，后续 dequeue 永久阻塞。排查方法：`dumpsys SurfaceFlinger` 中查看 Layer 的 Buffer 状态。

---

## 5. SurfaceFlinger 合成流程概要

### 5.1 SurfaceFlinger 的核心职责

SurfaceFlinger 是 Android 的合成引擎——它将所有可见 Layer 的内容合成为一帧完整的画面，然后输出到屏幕。

> 源码路径：
> - `frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp`
> - `frameworks/native/services/surfaceflinger/CompositionEngine/src/CompositionEngine.cpp`

### 5.2 合成流程时序

```
VSYNC-sf 信号到达
      │
      ▼
SurfaceFlinger::onMessageInvalidate()
      │
      ├── ① handleTransaction()
      │      → 处理来自 WMS / App 的 Transaction 请求
      │      → 更新 Layer 属性（position, size, alpha, z-order）
      │      → 添加/移除 Layer
      │
      ├── ② handleMessageRefresh()
      │      │
      │      ├── preComposition()
      │      │      → 检查每个 Layer 是否有新 Buffer 可用
      │      │
      │      ├── latchBuffer()
      │      │      → 对每个有新帧的 Layer：
      │      │        acquireBuffer() → 获取最新 GraphicBuffer
      │      │        更新 Layer 的显示内容
      │      │
      │      ├── computeVisibleRegion()
      │      │      → 计算每个 Layer 的可见区域
      │      │      → 被上层 Layer 完全遮挡的区域不需要合成
      │      │
      │      ├── chooseCompositionType()
      │      │      → 决定每个 Layer 使用 HWC 还是 GPU 合成
      │      │      → HWC 优先（功耗低、性能好）
      │      │      → 无法 HWC 合成的 Layer fallback 到 GPU
      │      │
      │      ├── doComposition()
      │      │      → HWC 合成：将 Layer 信息提交给 HWC HAL
      │      │      → GPU 合成：通过 OpenGL ES 将 Layer 画到 framebuffer
      │      │
      │      └── presentDisplay()
      │             → 将合成结果提交到 Display HAL
      │             → 等待 Display 扫描输出
      │
      └── 完成，等待下一个 VSYNC-sf
```

### 5.3 HWC 与 GPU 合成

| 合成方式 | 执行者 | 优势 | 劣势 | 适用场景 |
|:---|:---|:---|:---|:---|
| HWC（Hardware Composer） | Display 硬件 | 功耗极低、不占 GPU | 支持的 Layer 数量和效果有限 | 简单窗口布局（大多数场景） |
| GPU 合成 | GPU (OpenGL ES) | 支持任意数量和效果的 Layer | 消耗 GPU 算力和功耗 | 复杂动画、圆角、模糊等 |
| 混合模式 | HWC + GPU | 大部分 Layer 走 HWC，少部分走 GPU | 需要 SurfaceFlinger 协调 | 实际生产中最常见 |

SurfaceFlinger 通过 `HWComposer::prepare()` 询问 HWC HAL 每个 Layer 是否可以硬件合成。HWC HAL 返回每个 Layer 的合成类型：`HWC2::Composition::Device`（硬件合成）或 `HWC2::Composition::Client`（GPU 合成）。

### 5.4 Layer 类型

| Layer 类型 | 说明 | 对应场景 |
|:---|:---|:---|
| `BufferLayer` | 持有 BufferQueue，显示 App 渲染的内容 | Activity 窗口、Dialog、SurfaceView |
| `ColorLayer` | 纯色填充，不需要 Buffer | 窗口背景色、Dim 层 |
| `ContainerLayer` | 容器节点，不显示内容，只组织子 Layer | `DisplayContent`、`Task` 等 WindowContainer 对应的容器 |

### 5.5 帧时间线

```
  App 进程 (VSYNC-app)           SurfaceFlinger (VSYNC-sf)         Display
  ────────────────────           ─────────────────────────         ──────────

  VSYNC-app N                     
    │                             
    │ dequeueBuffer               
    │ draw (CPU/GPU)              
    │ queueBuffer                 
    │                             
    │                             VSYNC-sf N+1
    │                               │
    │                               │ latchBuffer (获取 App 帧)
    │                               │ composite (合成)
    │                               │ presentDisplay
    │                               │
    │                               │                              VSYNC N+2
    │                               │                                │
    │                               │                                │ 扫描输出
    │                               │                                │ 用户看到
    │                               │
  整个链路延迟: 约 2 个 VSYNC 周期 (33ms @60Hz, 16.6ms @120Hz)
```

> **稳定性架构师视角：** SurfaceFlinger 合成阶段的稳定性风险主要有：
>
> - **合成超时**：当 Layer 数量过多或 GPU 合成负载高时，单帧合成时间超过 VSYNC 周期（16.6ms @60Hz），导致掉帧。Systrace 中的特征是 SurfaceFlinger 的 `onMessageRefresh` 块超过 VSYNC 边界。
>
> - **Layer 泄漏**：SurfaceControl 未释放导致 SurfaceFlinger 的 Layer 数量持续增长。每个 BufferLayer 至少占用 3 个 GraphicBuffer 的显存。100 个泄漏的 1080p Layer 将消耗约 2.4GB 显存。`dumpsys SurfaceFlinger --list | wc -l` 可以监控 Layer 数量。
>
> - **HWC 错误降级**：HWC HAL 出错时，SurfaceFlinger 将所有 Layer fallback 到 GPU 合成，GPU 负载骤增，可能导致全局掉帧和功耗飙升。日志特征：`HWComposer: validate failed` 或 `falling back to client composition`。

---

## 6. WMS 的 Surface 生命周期管理

### 6.1 Surface 创建

Surface 不在 `addWindow()` 中创建（[02 篇](02-Window的创建与添加.md)已详述），而是在首次 `relayoutWindow()` 时创建：

```
App 调用 ViewRootImpl.requestLayout()
    ↓
ViewRootImpl.performTraversals()
    ↓ Binder IPC
WMS.relayoutWindow()
    ↓
createSurfaceControl()
    ↓
WindowStateAnimator.createSurfaceLocked()
    ↓
new WindowSurfaceController()
    ↓
SurfaceControl.Builder
    .setName("com.example.app/MainActivity#0")
    .setBufferSize(width, height)
    .setFormat(PixelFormat.RGBA_8888)
    .setParent(activityRecord.getSurfaceControl())
    .build()
    ↓ JNI → Binder → SurfaceFlinger
SurfaceFlinger.createLayer() → 创建 BufferLayer + BufferQueue
    ↓
WindowState.mHasSurface = true
```

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java（简化）
WindowSurfaceController createSurfaceLocked() {
    final WindowState w = mWin;

    if (mSurfaceController != null) {
        return mSurfaceController;
    }

    w.setHasSurface(false);

    int width = w.mRequestedWidth;
    int height = w.mRequestedHeight;

    mSurfaceController = new WindowSurfaceController(
            w.makeSurfaceTag(), width, height,
            w.mAttrs.format, 0 /* flags */, this, w.getWindowingMode());

    w.setHasSurface(true);
    return mSurfaceController;
}
```

### 6.2 Surface 显示

Surface 创建后不会立即显示。WMS 等待 App 完成首帧绘制后，才通过 `SurfaceControl.show()` 使其可见：

```
App 完成首帧绘制
    ↓
ViewRootImpl → Session.finishDrawing() → WMS
    ↓
WindowState.finishDrawingLocked()
    ↓
WindowStateAnimator.commitFinishDrawingLocked()
    → SurfaceControl.Transaction.show(surfaceControl)
    ↓
performSurfacePlacement()
    → Transaction.apply()
    → SurfaceFlinger: Layer 变为可见
```

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java（简化）
boolean finishDrawingLocked(SurfaceControl.Transaction
        postDrawTransaction) {
    if (!mDrawPending) {
        return false;
    }
    mDrawPending = false;
    // 标记已完成绘制，等待 commitFinishDrawing 使 Surface 可见
    return true;
}
```

### 6.3 Surface 隐藏

当窗口不再可见时（被完全遮挡、最小化、Activity 进入 STOPPED 状态），WMS 通过 `SurfaceControl.hide()` 隐藏 Surface：

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowState.java（简化）
void prepareSurfaces() {
    SurfaceControl.Transaction t = getSyncTransaction();

    if (isVisibleRequested()) {
        t.show(mSurfaceControl);
        // ... 设置 position, size, alpha
    } else {
        t.hide(mSurfaceControl);
    }
}
```

隐藏 Surface 不会销毁 Buffer——Layer 和 BufferQueue 仍然存在，只是不参与合成。这使得窗口重新可见时可以快速恢复，无需重新创建 Surface。

### 6.4 Surface 销毁

Surface 在窗口移除时销毁：

```
WMS.removeWindow()
    ↓
WindowState.removeIfPossible()
    ↓
WindowState.removeImmediately()
    ↓
destroySurface(false, false)
    ↓
WindowStateAnimator.destroySurfaceLocked()
    → mSurfaceController.destroy()
      → SurfaceControl.release()
        → JNI → SurfaceComposerClient::destroySurface()
          → Binder → SurfaceFlinger::destroyLayer()
            → 释放 BufferQueue
            → 释放 GraphicBuffer
            → 从 Layer 树中移除
    ↓
WindowState.mHasSurface = false
```

```java
// frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java（简化）
void destroySurfaceLocked(SurfaceControl.Transaction t) {
    if (mSurfaceController == null) {
        return;
    }

    mSurfaceController.hide(t);
    mSurfaceController.destroy(t);
    mSurfaceController = null;
    mWin.setHasSurface(false);
}
```

### 6.5 Surface 生命周期与 View 绘制的时序陷阱

Surface 的销毁与 View 的绘制之间存在一个危险的时序窗口：

```
时序竞态: Surface 已销毁但 View 仍在尝试绘制

T=0ms   Activity.onStop() 触发
T=5ms   WMS 决定回收 Surface → destroySurfaceLocked()
        → SurfaceControl.release()
        → mHasSurface = false
T=10ms  App 端 VSYNC 回调到达
        → ViewRootImpl.performTraversals()
        → performDraw()
        → Surface.lockCanvas()  ← Surface 已无效!
        → 抛出 IllegalArgumentException:
          "Surface has been released"
```

> **稳定性架构师视角：** "draw after Surface destroy"是 Surface 相关 Crash 的经典场景。当 Activity 快速在 STOPPED 和 RESUMED 状态之间切换时（如快速按 Home 再返回），WMS 可能在 App 的 `performTraversals` 执行之前就销毁了 Surface。App 端的 `ViewRootImpl` 在 `performDraw` 前会检查 `mSurface.isValid()`，但检查与实际使用之间仍存在窗口。
>
> 相反的问题也存在：Surface 未被正确销毁 → 资源泄漏。当 App 进程被 LMK 杀死后，WMS 依赖 `Binder.DeathRecipient` 回调来触发 `removeWindow()` → `destroySurface()`。如果 DeathRecipient 回调延迟，Surface 和对应的 GraphicBuffer 将在 SurfaceFlinger 中残留。

> 源码路径：
> - `frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java`
> - `frameworks/base/services/core/java/com/android/server/wm/WindowState.java`

---

## 7. 稳定性风险总结

### 7.1 风险速查表

| 风险类型 | 根因 | 典型表现 | 日志/诊断关键字 | 排查入口 | 影响等级 |
|:---|:---|:---|:---|:---|:---|
| SurfaceControl 泄漏 | `release()` 未调用 | Native 内存持续增长 | `dumpsys SurfaceFlinger --list` 中 Layer 数量异常 | 比较不同时间点的 Layer 列表 | 内存泄漏 → OOM |
| SurfaceControl use-after-release | 动画与窗口移除竞态 | Native Crash (SIGSEGV) | `tombstone` 中 `SurfaceControl` 相关栈 | 检查动画是否引用已释放 SC | App/system_server Crash |
| Transaction 未 apply | `closeSurfaceTransaction` 异常跳过 | 窗口状态不刷新 | 窗口位置/大小与预期不符 | Systrace 查看 Transaction 提交时机 | 视觉异常 |
| BufferQueue 耗尽 | App 渲染过慢或 Buffer 泄漏 | 掉帧、dequeueBuffer 阻塞 | Systrace 中 `dequeueBuffer` 耗时长 | `dumpsys SurfaceFlinger` 查看 Buffer 状态 | 卡顿 → ANR |
| 合成超时 | Layer 过多或 GPU 合成负载高 | 全局掉帧 | Systrace 中 SF `onMessageRefresh` 超长 | `dumpsys SurfaceFlinger --latency` | 卡顿 |
| HWC 降级 | HWC HAL 错误 | GPU 负载骤增、功耗上升 | `HWComposer: validate failed` | `dumpsys SurfaceFlinger` 查看合成类型 | 性能劣化 |
| Surface 创建失败 | fd 耗尽 / 显存不足 | 窗口黑屏 | `createLayer failed` / `alloc failed` | `dumpsys meminfo surfaceflinger` | 黑屏 |
| Surface 提前销毁 | WMS 回收过早 | `IllegalArgumentException: Surface has been released` | 堆栈中 `Surface.lockCanvas` | 检查 Activity 生命周期与 Surface 时序 | App Crash |
| Surface 未及时销毁 | DeathRecipient 延迟 | 显存持续增长 | 进程死亡后 Layer 仍存在 | `dumpsys SurfaceFlinger --list` 对比活跃进程 | 资源泄漏 |

### 7.2 各层风险分布

```
┌────────────────────────────────────────────────────────────────────────┐
│  App 层                                                                │
│   • Surface.lockCanvas 失败 → IllegalArgumentException                 │
│   • dequeueBuffer 阻塞（Buffer 耗尽）→ 渲染线程卡住 → 掉帧/ANR        │
│   • Surface 无效时仍尝试绘制 → Crash                                   │
├────────────────────────────────────────────────────────────────────────┤
│  WMS 层                                                                │
│   • SurfaceControl 泄漏 → Native 内存增长                              │
│   • Transaction 未提交 → 窗口状态不更新                                │
│   • Surface 创建/销毁时序与 View 绘制竞态 → Crash 或黑屏               │
│   • destroySurface 未执行 → 资源残留                                   │
├────────────────────────────────────────────────────────────────────────┤
│  SurfaceFlinger 层                                                     │
│   • Layer 数量过多 → 合成耗时增加 → 全局掉帧                           │
│   • HWC 合成失败 → fallback GPU → 性能劣化                             │
│   • GraphicBuffer 分配失败 → 新窗口黑屏                                │
│   • Buffer 泄漏 → 显存持续增长                                         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 实战案例

### Case 1：SurfaceControl 未销毁导致 Native 内存泄漏

**（典型模式：长生命周期 Service + 悬浮窗）**

**问题现象**

运维监控发现某设备的 `surfaceflinger` 进程内存在 3 天内从 80MB 增长到 450MB。`dumpsys SurfaceFlinger --list` 显示 Layer 数量从正常的 ~30 个增长到 ~800 个。设备开始出现间歇性界面卡顿和应用黑屏。

**排查过程**

**第一步：确认 Layer 泄漏来源**

```bash
$ adb shell dumpsys SurfaceFlinger --list | sort | uniq -c | sort -rn | head
    780 com.example.monitor/OverlayWindow#0
     12 StatusBar
      8 NavigationBar
      5 com.android.launcher3/...
      ...
```

780 个 Layer 都来自 `com.example.monitor` 的 `OverlayWindow`——一个后台监控 Service 创建的悬浮窗。

**第二步：分析业务代码**

```java
// com.example.monitor.MonitorService.java（问题代码）
public class MonitorService extends Service {

    private void showOverlay(String message) {
        WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        View overlay = LayoutInflater.from(this).inflate(R.layout.overlay, null);
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.TRANSLUCENT);

        wm.addView(overlay, params);

        // 3 秒后移除悬浮窗
        new Handler().postDelayed(() -> {
            wm.removeView(overlay);
        }, 3000);
    }

    // 每次收到监控事件就弹一个悬浮窗
    public void onMonitorEvent(MonitorEvent event) {
        showOverlay(event.getMessage());
    }
}
```

表面上看，每个悬浮窗在 3 秒后被 `removeView()` 移除。但实际上存在一个致命缺陷：

**第三步：定位泄漏原因**

通过在 `removeView` 前后添加日志，发现当监控事件高频触发（每秒 2-3 次）时，`Handler.postDelayed` 的 `Runnable` 可能在 Service 被系统临时回收后执行失败。更关键的是，当 `MonitorService` 被 `stopService()` 后重新启动时，**旧的 Handler 和 View 引用丢失，但对应的 WindowState 和 SurfaceControl 仍在 WMS 和 SurfaceFlinger 中存活**。

```
Service 生命周期:
  T=0    Service.onCreate() → 创建 Handler
  T=1s   onMonitorEvent → showOverlay() → addView() → WMS.addWindow()
  T=2s   onMonitorEvent → showOverlay() → addView() → WMS.addWindow()
  T=3s   系统内存紧张 → Service.onDestroy()
         → Handler 中的 postDelayed Runnable 被取消
         → 但 WMS 中的 WindowState 和 SurfaceControl 未被移除!
  T=10s  Service 重新创建 → onCreate() → 新的 Handler
         → 旧的 View 引用已丢失，无法 removeView
         → SurfaceFlinger 中残留 2 个泄漏的 Layer
```

每次 Service 被回收并重建，就会泄漏若干个 Layer。3 天后积累到 780 个。

**根因**

Service 的 `onDestroy()` 中没有清理所有已创建的悬浮窗。`Handler.postDelayed` 的延迟移除机制不可靠——Service 销毁后 Handler 消息队列被清空，延迟 `removeView` 不会执行。

**修复方案**

```java
// 修复后的 MonitorService
public class MonitorService extends Service {
    private final List<View> mActiveOverlays = new ArrayList<>();

    private void showOverlay(String message) {
        WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        View overlay = LayoutInflater.from(this).inflate(R.layout.overlay, null);
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.TRANSLUCENT);

        wm.addView(overlay, params);
        mActiveOverlays.add(overlay);

        new Handler().postDelayed(() -> {
            removeOverlay(overlay);
        }, 3000);
    }

    private void removeOverlay(View overlay) {
        if (mActiveOverlays.remove(overlay)) {
            try {
                WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
                wm.removeView(overlay);
            } catch (IllegalArgumentException e) {
                // View 已经被移除
            }
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        for (View overlay : mActiveOverlays) {
            try {
                wm.removeView(overlay);
            } catch (IllegalArgumentException e) {
                // ignore
            }
        }
        mActiveOverlays.clear();
    }
}
```

> **稳定性架构师视角：** SurfaceControl 泄漏是 Native 内存泄漏中最隐蔽的类型之一——Java 侧的 `SurfaceControl` 对象可能已被 GC 回收，但 Native 侧的 Layer 因为引用计数未归零而残留。长时间运行的 Service 创建的悬浮窗是此类泄漏的重灾区。防御策略：① 在 `Service.onDestroy()` 中必须清理所有悬浮窗；② 建立 Layer 数量监控（`dumpsys SurfaceFlinger --list | wc -l`），超过阈值告警；③ 在 CI 中加入 monkey test + Layer 泄漏检测。

---

### Case 2：BufferQueue 耗尽导致界面卡顿与掉帧

**（典型模式：App 渲染耗时 + 三缓冲耗尽）**

**问题现象**

某视频编辑 App 在预览页面出现严重卡顿，帧率从 60fps 降至 15-20fps。用户反馈"画面一顿一顿的"。logcat 中无 Crash 日志，但 Systrace 显示大量掉帧。

**排查过程**

**第一步：Systrace 初步分析**

```
Systrace 观察:
  App 主线程:
    performTraversals: 48ms (应在 16.6ms 内完成)
    其中:
      dequeueBuffer: 32ms  ← 异常! 正常应 <1ms
      draw: 15ms
      
  RenderThread:
    DrawFrame: 正常 (~8ms)
    但 dequeueBuffer 等待占据了大部分时间
```

`dequeueBuffer` 耗时 32ms 意味着 BufferQueue 中没有可用的 FREE Buffer，App 线程被阻塞等待 SurfaceFlinger 释放 Buffer。

**第二步：分析 BufferQueue 状态**

```bash
$ adb shell dumpsys SurfaceFlinger
  Layer: com.example.videoeditor/PreviewActivity#0
    Slots:
      [0] state=ACQUIRED
      [1] state=ACQUIRED
      [2] state=DEQUEUED
    NumPendingBuffers: 0
    NumQueuedBuffers: 0
```

3 个 Buffer 全部处于非 FREE 状态：2 个被 SurfaceFlinger ACQUIRED（正在合成或等待 Display 扫描），1 个被 App DEQUEUED（正在渲染）。没有可用 Buffer 给下一帧使用。

**第三步：分析根因**

该 App 的预览页面同时在做两件事：

1. **主线程**：通过 `SurfaceView` 显示视频预览帧（软件渲染路径，使用 `Surface.lockCanvas()`）
2. **预览帧来自 MediaCodec**：解码器输出帧的速率不稳定，偶尔出现"突发"——短时间内连续输出多帧

当解码器突发输出时，App 快速连续调用 `lockCanvas()` → 绘制 → `unlockCanvasAndPost()`，将所有 Buffer 填满。SurfaceFlinger 以 60fps 的速率消费，但消费速度跟不上突发的生产速度，导致 3 个 Buffer 全部占满，后续的 `dequeueBuffer()` 阻塞。

```
正常流程 (@60fps, 三缓冲):
  VSYNC 0: dequeue B0, draw, queue B0    SF: acquire B2, release B1
  VSYNC 1: dequeue B1, draw, queue B1    SF: acquire B0, release B2
  VSYNC 2: dequeue B2, draw, queue B2    SF: acquire B1, release B0
  → 流畅循环

突发场景 (解码器一次输出 4 帧):
  T=0ms:   dequeue B0, draw, queue B0    SF 还没来得及 acquire
  T=2ms:   dequeue B1, draw, queue B1    B0 在 Queued, SF 还没消费
  T=4ms:   dequeue B2, draw, queue B2    B0/B1 在 Queued, B2 刚 queue
  T=6ms:   dequeue ??? → 没有 FREE Buffer! → 阻塞等待 32ms
           直到 SF 在下一个 VSYNC acquire B0 并 release 旧 Buffer
```

**修复方案**

```java
// 修复: 控制渲染速率，不超过 VSYNC 频率
private final Choreographer.FrameCallback mRenderCallback = frameTimeNanos -> {
    if (mPendingFrame != null) {
        renderFrame(mPendingFrame);
        mPendingFrame = null;
    }
    if (!mStopped) {
        Choreographer.getInstance().postFrameCallback(mRenderCallback);
    }
};

// 解码器回调只保留最新帧，不立即渲染
public void onFrameDecoded(VideoFrame frame) {
    mPendingFrame = frame;  // 仅保留最新帧，旧帧丢弃
}
```

核心思想：将渲染频率与 VSYNC 对齐，解码器的突发输出不直接触发渲染，而是通过 `Choreographer` 在下一个 VSYNC 时渲染最新帧，丢弃中间帧。

> **稳定性架构师视角：** BufferQueue 耗尽是视频/相机/游戏类 App 的高发问题。防御策略：① 渲染速率必须与 VSYNC 对齐（通过 Choreographer），不允许"自由渲染"；② 使用 `dequeueBuffer` 的非阻塞模式（传入 `BUFFER_QUEUE_TRY_DEQUEUE`），如果没有空闲 Buffer 则跳帧而不是阻塞；③ 在 Systrace 中监控 `dequeueBuffer` 耗时，超过 5ms 应视为异常。

---

## 总结

Surface 是 Android 窗口系统中"看得见"的部分——它是连接 WMS 管理逻辑与 SurfaceFlinger 图形合成的桥梁。作为稳定性架构师，需要掌握以下核心要点：

1. **SurfaceControl 是 WMS 控制 SurfaceFlinger 的唯一接口**。每个可见窗口在 SurfaceFlinger 中对应一个 Layer，WMS 通过 SurfaceControl 管理 Layer 的属性。SurfaceControl 泄漏 = Layer 泄漏 = Native 内存持续增长。排查关键命令：`dumpsys SurfaceFlinger --list`。

2. **Transaction 保证了多个 Surface 操作的原子性**。WMS 将一帧内所有窗口的变化打包到一个 Transaction 中提交，避免用户看到中间状态。Transaction 未提交 → 窗口状态不更新；Transaction 过大 → 提交延迟。

3. **BufferQueue 是 App 与 SurfaceFlinger 之间的数据管道**。三缓冲机制平衡了吞吐量与延迟。Buffer 耗尽 → `dequeueBuffer` 阻塞 → 掉帧甚至 ANR。渲染速率必须与 VSYNC 对齐。

4. **SurfaceFlinger 的合成流程决定了最终画面**。HWC 优先、GPU 兜底。Layer 数量直接影响合成耗时。Layer 泄漏是全局掉帧的隐性杀手。

5. **Surface 的生命周期必须与 Window 的生命周期严格对齐**。Surface 创建（`createSurfaceLocked`）在 `relayoutWindow` 时触发，Surface 销毁（`destroySurfaceLocked`）在 `removeWindow` 时触发。两者之间的时序竞态是黑屏和 Crash 的常见根因。

**排查路径速查：**

```
问题现象 → 排查入口
─────────────────────────
SurfaceControl 泄漏     → dumpsys SurfaceFlinger --list (Layer 数量)
                         → dumpsys meminfo surfaceflinger (显存)
窗口黑屏               → dumpsys window (mHasSurface)
                         → dumpsys SurfaceFlinger (Layer 是否存在)
全局掉帧               → Systrace (SF onMessageRefresh 耗时)
                         → dumpsys SurfaceFlinger --latency
dequeueBuffer 卡顿      → Systrace (dequeueBuffer 耗时)
                         → dumpsys SurfaceFlinger (Buffer 状态)
Surface Crash           → tombstone / logcat (Surface has been released)
                         → 检查 Surface 销毁与 View 绘制的时序
Transaction 不生效      → Systrace (Transaction apply 时机)
                         → 确认 closeSurfaceTransaction 被调用
```

---

## 附录：核心源码路径索引

| 文件名 | 完整路径 | 说明 |
|:---|:---|:---|
| `SurfaceControl.java` | `frameworks/base/core/java/android/view/SurfaceControl.java` | SurfaceControl Java 封装，含 Transaction 内部类 |
| `Surface.java` | `frameworks/base/core/java/android/view/Surface.java` | Surface Java 封装，App 端绘制入口 |
| `android_view_SurfaceControl.cpp` | `frameworks/base/core/jni/android_view_SurfaceControl.cpp` | SurfaceControl JNI 桥梁 |
| `SurfaceComposerClient.cpp` | `frameworks/native/libs/gui/SurfaceComposerClient.cpp` | Native 层 SF Client，createSurface/Transaction |
| `SurfaceControl.cpp` | `frameworks/native/libs/gui/SurfaceControl.cpp` | Native 层 SurfaceControl 实现 |
| `Surface.cpp` | `frameworks/native/libs/gui/Surface.cpp` | Native 层 Surface 实现，持有 BufferQueue Producer |
| `BufferQueueProducer.cpp` | `frameworks/native/libs/gui/BufferQueueProducer.cpp` | BufferQueue 生产者端（dequeueBuffer / queueBuffer） |
| `BufferQueueConsumer.cpp` | `frameworks/native/libs/gui/BufferQueueConsumer.cpp` | BufferQueue 消费者端（acquireBuffer / releaseBuffer） |
| `GraphicBuffer.cpp` | `frameworks/native/libs/ui/GraphicBuffer.cpp` | 图形缓冲区（像素数据载体） |
| `SurfaceFlinger.cpp` | `frameworks/native/services/surfaceflinger/SurfaceFlinger.cpp` | SurfaceFlinger 合成引擎主入口 |
| `CompositionEngine.cpp` | `frameworks/native/services/surfaceflinger/CompositionEngine/src/CompositionEngine.cpp` | 合成引擎核心逻辑 |
| `Layer.cpp` | `frameworks/native/services/surfaceflinger/Layer.cpp` | SF Layer 基类 |
| `BufferLayer.cpp` | `frameworks/native/services/surfaceflinger/BufferLayer.cpp` | 持有 BufferQueue 的 Layer |
| `WindowStateAnimator.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowStateAnimator.java` | createSurfaceLocked / destroySurfaceLocked |
| `WindowState.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowState.java` | prepareSurfaces / finishDrawingLocked |
| `WindowSurfaceController.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowSurfaceController.java` | WMS 侧 Surface 控制器 |
| `WindowManagerService.java` | `frameworks/base/services/core/java/com/android/server/wm/WindowManagerService.java` | relayoutWindow / openSurfaceTransaction / closeSurfaceTransaction |

---

下一篇 [06-窗口动画与转场](06-窗口动画与转场.md) 将深入 WMS 的窗口动画框架，分析 Activity 转场动画的状态机、RemoteAnimation 机制、窗口动画期间 SurfaceControl 的操作模式，以及动画过程中的 Surface 泄漏和性能问题。
