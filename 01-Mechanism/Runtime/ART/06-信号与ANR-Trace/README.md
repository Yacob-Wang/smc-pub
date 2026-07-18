# 06-信号与ANR-Trace：从 SIGQUIT 到 traces.txt

> **本子模块**：06-信号与ANR-Trace（横切 · 6/9）——ANR 时堆栈怎么 dump 出来：SIGQUIT 语义、SignalCatcher 线程、ANR 完整链路、线程挂起机制、Java 栈 dump、traces.txt 格式解读

---

## 本子模块章节列表

| 章节 | 标题 | 行数目标 | 状态 |
| :--- | :--- | ---: | :---: |
| 01 | [SignalCatcher 与信号机制](01-SignalCatcher与信号机制.md) | ~700 | ✅ |
| 02 | [ANR Trace 完整链路](02-ANR_Trace完整链路.md) | ~700 | ✅ |

**合计**：~1400 行

---

## 子模块与全系列的依赖

```
00 → 01（字节码）→ 02（编译与执行）→ 03-类加载与链接 → 04-GC → 05-JNI → 06-信号与ANR-Trace（本子模块）→ 07-启动 → 08-对比
```

---

## 关键源码路径

| 路径 | AOSP 版本 | 角色 |
| :--- | :--- | :--- |
| `art/runtime/signal_catcher.cc` | AOSP 14+ | SignalCatcher 线程 |
| `art/runtime/runtime.cc` | AOSP 14+ | Runtime 启动 SignalCatcher |
| `art/runtime/thread_list.cc` | AOSP 14+ | 线程挂起（SuspendAll） |
| `art/runtime/stack_walker.cc` | AOSP 14+ | Java 栈展开 |
| `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` | AOSP 14+ | ANR 检测 + sendSignal |
| `frameworks/base/services/core/java/com/android/server/Watchdog.java` | AOSP 14+ | Watchdog ANR 兜底 |

---

> **返回阅读**：[README-ART 系列](../README-ART系列.md)