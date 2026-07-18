# 05-Generational-CC：分代假说的 ART 实践

> **本篇是 GC 系列的"算法篇 3"** —— 把 ART Android 10.0+ 默认的 GenCC（Generational CC）GC 算法讲透。
>
> **理解本篇，就理解了"为什么 90% 的 Minor GC < 0.5ms"** —— 分代假说 + Card Table 的工程胜利。

---

## 一句话定位

**GenCC = Generational Concurrent Copying = 分代并发复制**。ART Android 10.0+ 默认 GC。
核心思想：**基于"绝大多数对象朝生夕灭"的分代假说，把 Java 堆分成 Young/Old 两代，只对 Young 做高频 Minor GC，对 Old 做低频 Major GC**。

GenCC 的三大创新：
1. **分代假说**（Generational Hypothesis）—— 90% 对象朝生夕灭
2. **Card Table**（卡表）—— 1 byte / 512 byte 粒度记录跨代引用
3. **Minor GC + Major GC** 分工 —— Minor < 0.5ms，Major 偶尔

---

## 章节速览

| 章节 | 标题 | 字数 |
|:---|:---|:---|
| [5.1](./01-分代假说.md) | 分代假说（Generational Hypothesis） | 1.0 万字 |
| [5.2](./02-Young-Old划分.md) | Young Gen vs Old Gen 划分 | 1.2 万字 |
| [5.3](./03-Card-Table基石.md) | Card Table：分代 GC 的基石 | 1.4 万字 |
| [5.4](./04-Remembered-Set.md) | Remembered Set 的 ART 实现 | 1.2 万字 |
| [5.5](./05-Minor-Major-GC.md) | Minor GC vs Major GC | 1.3 万字 |
| [5.6](./06-对象晋升.md) | 对象晋升（Promotion） | 1.0 万字 |
| [5.7](./07-写屏障双重角色.md) | 写屏障在分代 GC 中的双重角色 | 1.0 万字 |
| [5.8](./08-实战案例.md) | 实战案例：分代假说失效的"长寿对象"场景 | 1.2 万字 |

**本篇总字数预估：约 9.3 万字**。

---

## 阅读路径

| 你要解决的问题 | 优先看 |
|:---|:---|
| 理解 GenCC 怎么把 Minor GC 做到 < 0.5ms | 5.1 + 5.3 + 5.5 |
| 排查 Minor GC 频繁问题 | 5.5 + 5.8 |
| 理解对象晋升机制 | 5.6 |
| 写屏障维护 Card Table | 5.7 |

---

## 跨篇引用

**本篇被引用**：07 篇调度 → 5.5 Minor/Major GC；08 篇横切 → 5.3 Card Table

**本篇引用**：
- 01 篇 1.5（卡表）—— 1 byte / 512 byte 原理
- 01 篇 1.3（写屏障）—— Post-Write Barrier
- 02 篇 2.5（Region-based）—— Region 在分代中的角色
- 04 篇 CC GC —— CC 在分代中的应用

---

## 下篇预告

**06-Reference 与 Finalizer**——Java 引用体系的完整深潜：
- SoftReference / WeakReference / PhantomReference
- LeakCanary / Cleaner / finalize() 的根
- FinalizerDaemon / FinalizerWatchdogDaemon 源码深潜
