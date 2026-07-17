# 00-总览：ART 是什么

> **本子模块定位**：ART 系列的**全局观**（1/9）——从稳定性架构师视角建立 ART 的全景认知：演进史、架构位置、五大核心能力、源码目录
> **本子模块角色**：系列开篇，其他 8 个子模块（M1-M8）的"导航地图"
> **基线版本**：AOSP android-14.0.0_r1（ART 主线）；Linux 内核 android14-5.10 / 5.15

---

## 本子模块章节列表

| 章节 | 标题 | 行数目标 | 状态 |
| :--- | :--- | ---: | :---: |
| 01 | [ART 总览：稳定性架构师的全局视角](01-ART总览：稳定性架构师的全局视角.md) | ~700 | ✅ |

**合计**：~700 行 / 4-6 张 ASCII 图 / 1-2 个实战案例 / 4 个完整附录

---

## 子模块与全系列的依赖关系

```
00-总览（本子模块，全局观）
    │
    ├─ 01-字节码与指令集（M1，基础层）
    │     └─ 解释器执行字节码
    │
    ├─ 02-编译与执行（M2，核心机制）
    │     └─ 字节码 → 机器码
    │
    ├─ 03-类加载与链接（M3，核心机制）
    │     └─ ClassLoader / ClassLinker
    │
    ├─ 04-内存与GC（M4，★ 已完稿 9 篇）
    │     └─ GC 系统 / Heap / 引用
    │
    ├─ 05-JNI（M5，边界）
    │     └─ Java ↔ Native
    │
    ├─ 06-信号与ANR-Trace（M6，横切）
    │     └─ SIGQUIT / ANR 链路
    │
    ├─ 07-启动流程（M7，生命周期）
    │     └─ Zygote → 第一行 Java
    │
    └─ 08-对比与演进（M8，横切）
        └─ ART vs JVM / Mainline / Hook / 监控
```

---

## 子模块与稳定性视角的对应

| 稳定性问题 | 对应子模块 | 备注 |
| :--- | :--- | :--- |
| **OOM** | 04-内存与GC | 核心战场 |
| **ANR** | 06-信号与ANR-Trace + 02-编译与执行 | 解释器慢 + GC 阻塞主线程 |
| **冷启动慢** | 07-启动流程 + 02-编译与执行 | PGO / 启动期 GC |
| **Hook 崩溃** | 08-对比与演进 + 04-CC-GC | 读屏障与 Hook 框架的兼容性 |
| **内存泄漏** | 04-GC 01/06 + 04-GC 09（LeakCanary） | 可达性 + Reference |
| **JNI 崩溃** | 05-JNI + 06-信号 | JNI Critical 与 Native Crash |

---

## 与 v2.1 主干的耦合

| 引用系列 | 引用主题 |
| :--- | :--- |
| [Linux_Kernel/Process](../../Linux_Kernel/Process/) | 进程 / fork / 信号 |
| [Linux_Kernel/Memory_Management](../../Linux_Kernel/Memory_Management/) | 虚拟内存 / VMA |
| [Linux_Kernel/FS](../../Linux_Kernel/FS/) | mmap / Dex / OAT 加载 |
| [Linux_Kernel/Binder](../../Linux_Kernel/Binder/) | ART Service 通信 |
| [Android_Framework/AMS](../../Android_Framework/AMS/) | ANR 检测 |
| [Runtime/Native_Crash](../../Runtime/Native_Crash/) | Native 信号 / Tombstone |

---

## 阅读建议

**时间有限优先读本子模块**：本子模块是全局观，1-2 小时读完，建立 ART 全景认知。
**系统学习**：按编号顺序 00 → 08。

---

> **返回阅读**：[README-ART 系列](../README-ART系列.md) 包含全系列目录与阅读建议。