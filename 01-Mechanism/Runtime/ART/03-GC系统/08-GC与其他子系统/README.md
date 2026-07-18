# 08-GC与其他子系统：横切专题

> **本篇是 GC 系列的"横切专题"** —— 把 GC 与其他子系统的交互讲透。
>
> **理解本篇，就理解了"GC 不是孤立的，而是与整个 Android 系统深度耦合"**。

---

## 一句话定位

**ART GC 与 Android 子系统的横切**：
- GC × JNI（Critical 区 / Global Ref）
- GC × Zygote（fork 后的 GC 状态）
- GC × Hook（兼容性问题）
- GC × APEX（Mainline 模块）
- GC × System Server（特殊 GC 策略）
- GC × SurfaceFlinger（高频 Native 分配）

---

## 章节速览

| 章节 | 标题 | 字数 |
|:---|:---|:---|
| [8.1](./01-GC与JNI.md) | GC × JNI：Critical 区的阻塞问题 | 1.2 万字 |
| [8.2](./02-GC与JNI-GlobalRef.md) | GC × JNI：Global Reference 的 GC 责任 | 1.0 万字 |
| [8.3](./03-GC与Zygote.md) | GC × Zygote：fork 后的 GC 状态 | 1.0 万字 |
| [8.4](./04-GC与Hook框架.md) | GC × Hook 框架 | 1.3 万字 |
| [8.5](./05-GC与APEX模块.md) | GC × APEX 模块 | 0.8 万字 |
| [8.6](./06-GC与SystemServer.md) | GC × System Server 进程 | 1.0 万字 |
| [8.7](./07-GC与输入法-SurfaceFlinger.md) | GC × 输入法 / SurfaceFlinger | 0.9 万字 |
| [8.8](./08-实战案例.md) | 实战案例：Hook 框架在 CC GC 下的 3 个崩溃 | 1.4 万字 |

**本篇总字数预估：约 8.6 万字**。

---

## 阅读路径

| 你要解决的问题 | 优先看 |
|:---|:---|
| JNI 与 GC 冲突 | 8.1 + 8.2 |
| Hook 框架兼容 | 8.4 + 8.8 |
| 进程间 GC 状态差异 | 8.3 + 8.6 |
| 模块化与 GC | 8.5 |

---

## 下篇预告

**09-GC 诊断与治理** —— 把 GC 诊断工具链讲透：
- dumpsys meminfo 全字段解读
- LeakCanary / MAT / Shark
- Perfetto / Systrace 追踪
- JVMTI 监控
- 完整监控体系搭建
