# 04-CC-GC：并发复制的读屏障革命

> **本篇是 GC 系列的"算法篇 2"** —— 把 ART Android 8.0-9.0 默认的 CC（Concurrent Copying）GC 算法讲透。
>
> **理解本篇，就理解了"为什么 Android 8.0+ 卡顿大幅减少"** —— CC GC 用读屏障革命把 STW 从 50ms 降到 < 1ms。

---

## 一句话定位

**CC = Concurrent Copying = 并发复制**。ART Android 8.0-9.0 的默认 GC 算法。
核心思想：**通过读屏障 + 自愈指针 + 标记-复制，并发完成对象移动，让 STW 时间降到 < 5ms**。

CC GC 的三大革命：
1. **并发移动对象**（不 STW）
2. **读屏障 + 自愈指针**（维护正确性）
3. **Region-based**（碎片化自动修复）

---

## 章节速览

| 章节 | 标题 | 字数 | 一句话定位 |
|:---|:---|:---|:---|
| [4.1](./01-CC核心思想.md) | CC GC 的核心思想：复制 vs 清除 | 1.2 万字 | 为什么"复制活对象"比"清除死对象"更优 |
| [4.2](./02-3阶段详解.md) | 3 阶段：Initialize / Copying / Reclaim | 1.4 万字 | 从-space / to-space 翻转 |
| [4.3](./03-读屏障机制.md) | 读屏障的实现机制 | 1.6 万字 | 编译器插入 vs 运行时检查 |
| [4.4](./04-Invariant不变式.md) | Invariant：不变量与正确性 | 1.2 万字 | 弱三色不变式 + GrayStatusImmuneWord |
| [4.5](./05-Region-Space角色.md) | Region Space 的角色 | 1.0 万字 | Region 状态机 + GC 按 Region 操作 |
| [4.6](./06-Thread-Roots栈扫描.md) | Thread Roots 与栈扫描 | 1.0 万字 | 栈帧引用的处理 |
| [4.7](./07-实战案例.md) | 实战案例：CC GC 下 Hook 框架的兼容性问题 | 1.2 万字 | SandHook / Epic 在 CC GC 下的崩溃 |

**本篇总字数预估：约 8.6 万字**。

---

## 阅读路径

### 速读（30 分钟）

1. 看完本文档（目录 + 速览 + 总结图）
2. 直接看 [4.1 核心思想](./01-CC核心思想.md) 和 [4.2 3 阶段详解](./02-3阶段详解.md)
3. 带着对照表去读 [4.3 读屏障机制](./03-读屏障机制.md)

### 精读（3-4 小时）

按 4.1 → 4.2 → 4.3 → 4.4 → 4.5 → 4.6 → 4.7 顺序读。

### 实战排查阅读

| 你要解决的问题 | 优先看 |
|:---|:---|
| 理解为什么升级到 Android 8+ 卡顿消失 | 4.1 + 4.2 |
| CC GC 下 Hook 框架崩溃 | 4.7 + 4.3 |
| 读屏障性能问题 | 4.3 + 4.4 |
| Region-based 分配问题 | 4.5 |

---

## 跨篇引用

**本篇被引用**：
- 05 篇 GenCC → 4.5（Region）+ 4.6（栈扫描）
- 06 篇 Reference → 4.4（不变式 + Reference 处理）
- 08 篇横切 → 4.7（Hook 兼容性）+ 4.3（读屏障）

**本篇引用**：
- 01 篇 1.2（三色不变式）—— 弱三色不变式
- 01 篇 1.4（读屏障）—— 读屏障原理
- 02 篇 2.5（Region-based）—— Region 分配器
- 03 篇 CMS —— CMS 三大硬伤的对比

---

## 附录索引

- [A-源码索引.md](./appendix/A-源码索引.md)
- [B-路径对账.md](./appendix/B-路径对账.md)
- [D-工程基线.md](./appendix/D-工程基线.md)

---

## 下篇预告

**05-Generational-CC：分代假说的 ART 实践** —— Android 10.0+ 默认 GC：
- 分代假说 + Region 布局
- Card Table + Remembered Set
- Minor GC vs Major GC
- 90% Minor GC < 0.5ms 的秘密
