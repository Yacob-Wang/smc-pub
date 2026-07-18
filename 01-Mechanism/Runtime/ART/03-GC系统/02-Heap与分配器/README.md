# 02-Heap 与分配器：5 Space 划分与分配路径

> **本篇是 ART 堆的"地图"** —— 不讲清空间划分，所有 OOM 排查都靠猜。
>
> **本篇不讲具体 GC 算法**（CMS / CC / GenCC 在 03/04/05 篇）。只讲 **所有 GC 算法共享的堆结构 + 分配器**。

---

## 一句话定位

**ART 的 Java 堆不是一整块内存**，而是 **5 个 Space** 的组合：
- **Image Space**：只读的 OAT 镜像
- **Zygote Space**：Zygote 进程 fork 时共享的预加载类
- **Allocation Space**：常规对象分配（CMS 用 RosAlloc，CC/GenCC 用 Region）
- **Large Object Space (LOS)**：大对象（≥ 12KB / Region Size）
- **Non-Moving Space**：永久不移动的对象（CC GC 早期版本）

每个 Space 有 **不同的分配器、不同的 GC 策略、不同的回收时机**。

---

## 章节速览

| 章节 | 标题 | 字数 | 一句话定位 |
|:---|:---|:---|:---|
| [2.1](./01-Heap总览.md) | Heap 总览：为什么 ART 不用一整块内存 | 1.2 万字 | ART 堆的整体架构 + 设计权衡 |
| [2.2](./02-5Space详解.md) | 5 Space 详解 | 1.6 万字 | 每种 OOM 对应不同 Space 的根源 |
| [2.3](./03-内存配额.md) | 内存配额：growth_limit vs max_heap vs largeHeap | 1.0 万字 | largeHeap 的代价：被 LMK 杀得更快 |
| [2.4](./04-RosAlloc分配器.md) | 分配器 1：RosAlloc（CMS 时代） | 1.4 万字 | Run-of-Slots + TLAB + 大小分桶 |
| [2.5](./05-Region-based分配器.md) | 分配器 2：Region-based（CC 时代） | 1.3 万字 | Region 状态机 + bump pointer + TLAB |
| [2.6](./06-Concurrent分配器.md) | 分配器 3：Concurrent Allocator | 1.0 万字 | Region Space 的并发分配 |
| [2.7](./07-慢速路径与碎片化.md) | 慢速路径与碎片化 | 1.2 万字 | "堆里还有 100MB 为什么 OOM"的根因 |
| [2.8](./08-实战案例.md) | 实战案例：LOS 碎片化导致大 Bitmap 分配失败 | 1.0 万字 | 完整 case + logcat + dumpsys meminfo + 修复 diff |

**本篇总字数预估：约 9.7 万字**（含代码与图表）。

---

## 阅读路径

### 速读（30 分钟）

1. 看完本文档（目录 + 速览 + 总结图）
2. 直接看 [2.2 5 Space 详解](./02-5Space详解.md) 的对照表
3. 带着对照表去读后续 GC 算法篇（03/04/05）

### 精读（3-4 小时）

按 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7 → 2.8 顺序读，每章节跟随源码索引（附录 A）对照 AOSP 源码。

### 实战排查阅读

| 你要解决的问题 | 优先看 |
|:---|:---|
| OOM 排查 | 2.2（5 Space）→ 2.3（配额）→ 2.7（碎片化） |
| 分配慢 / 性能差 | 2.4（RosAlloc）→ 2.5（Region）→ 2.6（Concurrent） |
| 大对象分配失败 | 2.2（LOS）→ 2.7（碎片化） |
| `largeHeap` 是否启用 | 2.3（内存配额） |
| 升级 CC GC 后分配变慢 | 2.5（Region-based） |

---

## 跨篇引用

**本篇被引用**：
- 03 篇 CMS → 2.4（RosAlloc）+ 2.7（碎片化）
- 04 篇 CC → 2.5（Region-based）+ 2.6（Concurrent）
- 05 篇 GenCC → 2.5（Region-based）+ Minor GC 扫描范围
- 07 篇调度 → 2.3（growth_limit 触发 GC）
- 09 篇诊断 → 2.2（dumpsys meminfo 解读）+ 2.7（碎片化判断）

**本篇引用**：
- 01 篇 1.1（可达性分析）—— GC Root 的来源依赖 Heap 布局
- ART 大模块的 `02-类加载与链接`（Image Space 的来源）

---

## 附录索引

- [A-源码索引.md](./appendix/A-源码索引.md) —— 本篇涉及的所有 AOSP 源码路径（AOSP 14 / master）
- [B-路径对账.md](./appendix/B-路径对账.md) —— AOSP 版本号 / Kernel 版本 / 关键 commit hash
- [D-工程基线.md](./appendix/D-工程基线.md) —— 默认参数 / 监控指标 / 排查 checklist

---

## 下篇预告

**03-CMS GC** —— 把"标记-清除"算法在 ART 中的实现讲透：

- CMS 4 阶段：Initial Mark → Concurrent Mark → Remark → Concurrent Sweep
- 写屏障的正确性保证（Incremental Update）
- 内存碎片化的根本原因（不压缩的代价）
- CMS 时代的 OOM 模式与治理

→ 理解 CMS 是理解 CC 的"反面教材"。
