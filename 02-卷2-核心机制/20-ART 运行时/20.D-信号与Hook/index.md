# 20.D 信号 / ANR / Hook

> 共 4 篇 · P0 第 20 章拆分子章

## 子节导航

### 20.D.1 信号机制（1 篇）
> SignalCatcher 与 ART 信号处理

### 20.D.2 ANR Trace 链路（1 篇）
> ANR 完整 trace 抓取链路（含 SIGQUIT 主路径、traces.txt 解读方法论）

### 20.D.3 Hook 框架与 ART（1 篇）
> ART 层的 Hook 实现

### 20.D.4 监控与诊断基础设施（1 篇）
> ART 层监控与诊断基础设施

## 5 大稳定性信号全景图（跨篇索引）

> **排查任何一个 Native 异常，先看这张表确定信号 → 再跳到对应章节。**

| 信号 | 编号 | 默认行为 | 触发场景 | ART 处理路径 | 详解章节 |
|:--|:--:|:--|:--|:--|:--|
| **SIGQUIT** | 3 | Core + Term | **ANR 主路径** | SignalCatcher 守护线程 → traces.txt | [02 §3-§5](02-ANR_Trace完整链路.md) |
| **SIGSEGV** | 11 | Core + Term | Native Crash 头号（~60%） | Crash handler → tombstone | [01 §4](01-SignalCatcher与信号机制.md) |
| **SIGBUS** | 7 | Core + Term | mmap 失败 / unaligned 访问 | Crash handler → tombstone | [01 §4](01-SignalCatcher与信号机制.md) |
| **SIGABRT** | 6 | Core + Term | abort() / fortify / double free | Crash handler → tombstone | [01 §4](01-SignalCatcher与信号机制.md) |
| **SIGFPE** | 8 | Core + Term | 除零 / FPU 异常 | Crash handler → tombstone | [01 §4](01-SignalCatcher与信号机制.md) |
| **SIGILL** | 4 | Core + Term | 非法指令 / hook 失败 | Crash handler → tombstone | [01 §5](01-SignalCatcher与信号机制.md) |
| **SIGTRAP** | 5 | Core + Term | 调试器断点 | debuggerd → gdb 接管 | [01 §5](01-SignalCatcher与信号机制.md) |
| **SIGPIPE** | 13 | Term | socket 关闭后写 | **静默忽略**（ART 默认） | [01 §2.1](01-SignalCatcher与信号机制.md) |
| **SIGCHLD** | 17 | Ignore | 父进程回收 | Zygote 默认 | [01 §2.1](01-SignalCatcher与信号机制.md) |
| **SIGTERM** | 15 | Term | 进程优雅退出 | ActivityManager.killProcess | — |
| **SIGKILL** | 9 | Term | OOM killer / 强制杀 | **不可捕获** | — |

**5 大实战信号 → 路径速查**：

```
ANR 触发         SIGQUIT  ──→  SignalCatcher 守护线程  → traces.txt
Native Crash     SIGSEGV  ──→  Crash handler           → tombstone
Native Crash     SIGBUS   ──→  Crash handler           → tombstone
abort() 异常     SIGABRT  ──→  Crash handler           → abort 路径 → tombstone
调试器断点       SIGTRAP  ──→  debuggerd               → gdb 接管
```

**ANR 链路（SIGQUIT 单信号路径）**：

```
InputDispatcher 检测超时
  ↓
Process.killProcessQuiet(pid)   // 源码里就是 kill(pid, SIGQUIT)
  ↓
目标进程 SignalCatcher 守护线程 sigwait 阻塞
  ↓
sigwait 返回 → SignalCatcher::HandleSigQuit
  ↓
逐线程 suspend / dump / resume（ART 非原子快照）
  ↓
traces.txt 落盘到 /data/anr/
  ↓
AppNotRespondingDialog 弹窗
```

## 文件清单

- [01-SignalCatcher与信号机制](01-SignalCatcher与信号机制.md) — ART 信号基础 + 9 种信号分类 + Async-Signal-Safety
- [02-ANR_Trace完整链路](02-ANR_Trace完整链路.md) — ANR 4 类型 + SIGQUIT 主路径 + traces.txt 解读方法论
- [03-Hook框架与ART](03-Hook框架与ART.md) — ART 层 Hook 实现
- [04-监控与诊断基础设施](04-监控与诊断基础设施.md) — ART 层监控与诊断基础设施

---

**返回**：[第 20 章 索引](../index.md)
