# 06-Reference与Finalizer：被忽视的对象生命周期管理

> **本篇是 GC 系列的"专题篇 1"** —— 专门深潜 Java Reference 体系和 Finalizer 机制。
>
> **理解本篇，就理解了 LeakCanary / Cleaner / finalize() 的根** —— 所有内存敏感操作的根基。

---

## 一句话定位

**Reference 体系是 GC 与应用层交互的"钩子"** —— 通过 4 种引用类型，让应用代码影响 GC 行为。

**Finalizer 是对象的"析构函数"** —— 通过 FinalReference + FinalizerDaemon + FinalizerWatchdogDaemon 实现。

**06 篇完全补全 ART-05 缺失的 Reference 体系**，并把 Finalizer 机制深潜到源码级。

---

## 章节速览

| 章节 | 标题 | 字数 |
|:---|:---|:---|
| [6.1](./01-可达性状态机.md) | Java 引用的可达性状态机 | 1.0 万字 |
| [6.2](./02-SoftReference.md) | SoftReference：LRU 缓存的根基 | 1.2 万字 |
| [6.3](./03-WeakReference.md) | WeakReference：WeakHashMap 与内存泄漏排查 | 1.3 万字 |
| [6.4](./04-FinalReference.md) | FinalReference：finalize() 的本质 | 1.1 万字 |
| [6.5](./05-PhantomReference.md) | PhantomReference：真正的析构语义 | 1.2 万字 |
| [6.6](./06-Cleaner.md) | Cleaner：JDK 8 引入的轻量析构 | 1.0 万字 |
| [6.7](./07-FinalizerDaemon源码.md) | FinalizerDaemon 源码深潜 | 1.3 万字 |
| [6.8](./08-FinalizerWatchdog源码.md) | FinalizerWatchdogDaemon 的 10 秒超时 | 1.0 万字 |
| [6.9](./09-实战案例.md) | 实战案例：finalize() 链式阻塞的完整分析 | 1.4 万字 |

**本篇总字数预估：约 10.5 万字**。

---

## 阅读路径

| 你要解决的问题 | 优先看 |
|:---|:---|
| 理解 4 种引用类型 | 6.1 + 6.2 + 6.3 + 6.5 |
| LeakCanary 原理 | 6.3 WeakReference |
| DirectByteBuffer 释放 | 6.5 + 6.6 |
| finalize() 卡死 | 6.7 + 6.8 + 6.9 |
| 完全禁止 finalize() | 6.9 治理方案 |

---

## 跨篇引用

**本篇被引用**：09 篇诊断 → 6.9 finalize() 治理
**本篇引用**：
- 01 篇 1.1 可达性分析 —— Reference 的可达性
- 01 篇 1.6 Reference 体系 —— Reference 体系概览
- 04 篇 CC GC —— Reference 处理时机

---

## 下篇预告

**07-GC 调度与触发** —— 把 GC 触发机制讲透：
- 9 种 GcCause 详解
- HeapTaskDaemon 工作循环
- Native 触发 GC
- Trim Heap
