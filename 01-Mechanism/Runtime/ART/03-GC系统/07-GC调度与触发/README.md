# 07-GC调度与触发：HeapTaskDaemon 的工作循环

> **本篇是 GC 系列的"调度篇"** —— 把 GC 触发机制、HeapTaskDaemon、9 种 GcCause 讲透。
>
> **理解本篇，就理解了"GC 是怎么被调度、并发执行的"** —— 是 ART GC 调优的基础。

---

## 一句话定位

**GC 调度 = 触发条件 + 调度策略 + 执行方式**。

ART 通过 **HeapTaskDaemon** 异步执行 GC，通过 **9 种 GcCause** 标记触发原因，通过 **Concurrent / Blocking 两种执行方式** 区分 GC 类型。

---

## 章节速览

| 章节 | 标题 | 字数 |
|:---|:---|:---|
| [7.1](./01-9种GcCause.md) | GC 触发的 9 种原因 | 1.2 万字 |
| [7.2](./02-HeapTaskDaemon.md) | GC 调度：HeapTaskDaemon 线程 | 1.4 万字 |
| [7.3](./03-ConcurrentGCTask.md) | ConcurrentGCTask 的提交与执行 | 1.0 万字 |
| [7.4](./04-GC_FOR_ALLOC路径.md) | 分配触发的 GC：GC_FOR_ALLOC 路径 | 1.2 万字 |
| [7.5](./05-Native触发GC.md) | Native 内存触发的 GC | 1.1 万字 |
| [7.6](./06-Trim-Heap.md) | Trim Heap：系统低内存时的主动缩容 | 1.0 万字 |
| [7.7](./07-Background-Foreground.md) | Background GC 与前台 GC 的优先级 | 0.8 万字 |
| [7.8](./08-GC线程模型.md) | GC 线程模型总图 | 1.0 万字 |

**本篇总字数预估：约 8.7 万字**。

---

## 阅读路径

| 你要解决的问题 | 优先看 |
|:---|:---|
| GC 触发原因排查 | 7.1 + 7.4 |
| GC 调度优化 | 7.2 + 7.7 |
| Native 内存与 Java GC 关系 | 7.5 |
| 系统低内存应对 | 7.6 |
| 完整 GC 线程模型 | 7.8 |

---

## 跨篇引用

**本篇被引用**：09 篇诊断 → 7.1 9 种 GcCause

**本篇引用**：
- 02 篇 Heap（5 Space）
- 03/04/05 篇（GC 算法）
- 06 篇 Reference

---

## 下篇预告

**08-GC 与其他子系统** —— 把 GC 与其他子系统的横切讲透：
- GC × JNI（Critical 区 / Global Ref）
- GC × Zygote（fork 后的 GC 状态）
- GC × Hook（兼容性问题）
- GC × APEX（Mainline 模块）
- GC × System Server
