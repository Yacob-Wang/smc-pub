# 8.7 GC × 输入法 / SurfaceFlinger

> **本节回答一个根本问题**：高频 Native 内存分配的子系统（输入法、SurfaceFlinger）怎么影响 Java GC？跨进程协作导致的 GC 异常？
>
> **答案**：**高频 Native 分配反哺 Java GC** —— Native 内存压力触发 Java GC。

---

## 一、输入法与 GC

### 8.7.1 输入法的高频 Native 分配

```
输入法的特殊性：

1. 高频输入事件
   - 用户每输入一个字符 → 输入法触发事件
   - 候选词更新
   - 表情包 / 特殊符号

2. 高频 Native 内存分配
   - 渲染候选词
   - 加载表情包
   - 保存用户输入历史

3. 影响 Java 堆
   - 输入法是 Java App
   - 但有大量 Native 内存
   - Native 内存压力 → Java GC
```

### 8.7.2 输入法的 GC 影响

```
输入法的 GC 影响：

1. Native 内存压力
   - 输入法分配大量 Bitmap（表情包）
   - DirectByteBuffer（输入历史）
   - 触发 kGcCauseForNativeAlloc

2. Java 堆增长
   - 候选词列表
   - 输入历史记录
   - 触发 kGcCauseForBackground 或 kGcCauseForAlloc

3. 卡顿影响
   - 输入时 GC → 输入卡顿
   - 候选词更新延迟
```

### 8.7.3 输入法的优化

```java
// ✅ 优化 1：复用候选词 Bitmap
private final LruCache<String, Bitmap> candidateBitmapCache = new LruCache<>(100);

public Bitmap getCandidateBitmap(String word) {
    Bitmap cached = candidateBitmapCache.get(word);
    if (cached != null && !cached.isRecycled()) {
        return cached;
    }
    Bitmap bitmap = loadCandidateBitmap(word);
    candidateBitmapCache.put(word, bitmap);
    return bitmap;
}

// ✅ 优化 2：限制输入历史大小
private static final int MAX_HISTORY_SIZE = 100;
private final LinkedList<String> inputHistory = new LinkedList<>();

public void addToHistory(String word) {
    inputHistory.addFirst(word);
    while (inputHistory.size() > MAX_HISTORY_SIZE) {
        inputHistory.removeLast();
    }
}
```

---

## 二、SurfaceFlinger 与 GC

### 8.7.4 SurfaceFlinger 的特殊性

```
SurfaceFlinger：

- 系统级渲染服务
- 由 init 进程启动（不是 Zygote fork）
- 管理所有 App 的 Surface
- 高频 Native 内存分配

SurfaceFlinger 的高频 Native 分配：

1. GraphicBuffer
   - 每个 Surface 一个 GraphicBuffer
   - 大量屏幕像素数据

2. RenderThread 资源
   - 渲染线程的 FrameBuffer
   - 持续分配 / 释放

3. OpenGL 资源
   - Texture / Shader
   - GPU 资源
```

### 8.7.5 SurfaceFlinger 对 GC 的影响

```
SurfaceFlinger 对 GC 的影响：

1. Native 内存压力
   - GraphicBuffer 分配 / 释放频繁
   - 触发 Native 内存压力
   - 系统级 NativeAllocGCTask

2. 跨进程协作
   - App 的 Surface → SurfaceFlinger
   - App 分配 Buffer → SurfaceFlinger 渲染
   - SurfaceFlinger 内存压力 → 整个系统 GC

3. 系统级卡顿
   - SurfaceFlinger 卡顿 → 所有 App 卡顿
   - 包括 SystemUI、Launcher 等
```

### 8.7.6 SurfaceFlinger 的优化

```cpp
// SurfaceFlinger 的 Triple Buffering
// 减少 Buffer 分配 / 释放频率
class SurfaceFlinger {
    // 维护 3 个 Buffer
    // 轮流使用，避免频繁分配 / 释放
    static constexpr int NUM_BUFFERS = 3;
    sp<GraphicBuffer> buffers_[NUM_BUFFERS];
};
```

### 8.7.7 App 与 SurfaceFlinger 的协作

```java
// App 端
public class MyActivity extends Activity {
    private SurfaceView surfaceView;
    
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        // 创建 Surface
        surfaceView = new SurfaceView(this);
        setContentView(surfaceView);
        
        // SurfaceFlinger 自动管理 Buffer
    }
    
    @Override
    public void onPause() {
        super.onPause();
        // 释放 Surface
        surfaceView.setVisibility(View.GONE);
    }
}
```

---

## 三、跨进程协作导致的 GC 异常

### 8.7.8 跨进程内存压力传递

```
跨进程内存压力传递链：

App 1 高频分配 Native 内存
  ↓
App 1 触发 kGcCauseForNativeAlloc
  ↓
App 1 释放 Java 堆 → Native 内存
  ↓
App 2 同样的问题
  ↓
整个系统 Native 内存压力
  ↓
System Server 触发 NativeAllocGCTask
  ↓
System Server GC 影响所有 App
```

### 8.7.9 跨进程协作的 GC 监控

```bash
# 1. 看所有进程的内存
adb shell dumpsys meminfo

# 2. 看 System Server 的 GC 频率
adb logcat -s "art" | grep "system_server\|GC" | tail -20

# 3. 看 Native 内存压力
adb shell cat /proc/meminfo | grep -i "cached\|available"
```

### 8.7.10 跨进程协作的优化

```
跨进程协作的优化：

1. App 层
   - 减少 Native 内存分配
   - 复用 Bitmap / Buffer
   - 监听 onTrimMemory

2. Framework 层
   - 优化 SurfaceFlinger
   - 优化输入法的内存管理
   - 减少全局缓存

3. System 层
   - 优化 LMK 策略
   - 监控 Native 内存压力
   - 触发 NativeAllocGCTask
```

---

## 四、高频 Native 分配的系统级影响

### 8.7.11 高频 Native 分配场景

| 场景 | 频率 | Native 内存 |
|:---|:---|:---|
| 输入法输入 | ~10/秒 | ~1 MB / 次 |
| SurfaceFlinger 渲染 | ~60/秒 | ~5 MB / 帧 |
| 视频播放 | ~30/秒 | ~10 MB / 帧 |
| 相机预览 | ~30/秒 | ~10 MB / 帧 |
| 游戏渲染 | ~60/秒 | ~10 MB / 帧 |

### 8.7.12 高频 Native 分配的 GC 影响

```
高频 Native 分配对 GC 的影响：

1. Native 内存快速增长
   - 10 MB / 帧 × 60 fps = 600 MB / 秒（理论）
   - 实际受 Buffer Pool 复用

2. Native 内存压力
   - 触发 NativeAllocGCTask
   - Java 堆也要释放空间

3. 系统卡顿
   - Native 分配本身耗时
   - GC 释放 Java 堆耗时
   - 用户感知卡顿
```

### 8.7.13 高频 Native 分配的优化

```
高频 Native 分配的优化：

1. 使用 Buffer Pool
   - Triple Buffering
   - 对象池复用

2. 减少分配频率
   - 缓存常用资源
   - 延迟加载

3. 异步释放
   - 不阻塞主线程
   - 用后台线程释放

4. 监控 Native 内存
   - 实时监控
   - 异常告警
```

---

## 五、输入法 / SurfaceFlinger 与 GC 的工程实践

### 8.7.14 输入法开发的工程建议

```
输入法开发的工程建议：

1. Native 内存管理
   - 用 Buffer Pool
   - 及时释放 native 资源
   - 用 Cleaner 替代 finalize

2. Java 堆管理
   - 缓存候选词 + LRU
   - 限制历史大小
   - 监听 onTrimMemory

3. GC 监控
   - 监控 GC 频率
   - 监控 STW 时间
   - 异常告警
```

### 8.7.15 SurfaceFlinger 开发的工程建议

```
SurfaceFlinger 开发的工程建议：

1. Buffer Pool
   - Triple Buffering
   - 避免频繁分配

2. 渲染优化
   - 减少 overdraw
   - 缓存渲染结果

3. 跨进程协作
   - App 与 SurfaceFlinger 协调
   - 避免 Buffer 浪费
```

---

## 六、输入法 / SurfaceFlinger 与 GC 的源码索引

### 8.7.16 核心源码路径

```
frameworks/base/core/java/android/inputmethodservice/  # 输入法
frameworks/native/services/surfaceflinger/            # SurfaceFlinger
art/runtime/gc/heap.cc                                 # Heap 类
art/runtime/gc/heap_task.h                             # NativeAllocGCTask
```

### 8.7.17 关键源码

| 组件 | 文件 |
|:---|:---|
| 输入法 | `frameworks/base/core/java/android/inputmethodservice/` |
| SurfaceFlinger | `frameworks/native/services/surfaceflinger/` |
| Heap | `art/runtime/gc/heap.cc` |
| NativeAllocGCTask | `art/runtime/gc/heap_task.h` |

---

## 七、本节小结

1. **输入法高频 Native 分配**：触发 kGcCauseForNativeAlloc
2. **SurfaceFlinger 高频 Buffer 分配**：系统级 Native 压力
3. **跨进程协作导致 GC 异常**：App 触发 System Server GC
4. **优化方向**：Buffer Pool + 缓存复用 + 主动清理
5. **监控**：Native 内存 + 跨进程 GC 频率

→ **理解输入法 / SurfaceFlinger 与 GC，就理解了"高频 Native 分配的系统级影响"**。

---

## 跨节引用

**本节被以下章节引用**：
- 09 篇诊断 —— 跨进程 GC 异常诊断

**本节引用**：
- [7.5 Native 触发 GC](../07-GC调度与触发/05-Native触发GC.md) —— kGcCauseForNativeAlloc
- [8.6 GC × System Server](./06-GC与SystemServer.md) —— 跨进程协作
- Android_Framework 的相关模块
