# 卷 4　稳定性症状诊断

> **本卷定位**：核心战场——8 大症状，每类从机制到案例到工具全链路。

## 章节目录

| 章号 | 标题 | 状态 |
|---|---|---|
| 第 22 章 | ANR 深度 | 🚧 撰写中 |
| 第 23 章 | Java 异常 | 🚧 撰写中 |
| 第 24 章 | Native 异常 | 🚧 撰写中 |
| 第 25 章 | 系统无响应（SWT / Watchdog） | 🚧 撰写中 |
| 第 26 章 | HANG 与死锁 | 🚧 撰写中 |
| 第 27 章 | REBOOT | 🚧 撰写中 |
| 第 28 章 | Kernel Exception | 🚧 撰写中 |
| 第 29 章 | 性能退化与稳定性边界 | 🚧 撰写中 |

---

## 章节目录（详细）

### 第 22 章　ANR 深度

- 22.1 ANR 类型：input / broadcast / service / contentprovider
- 22.2 ANR 检测机制：InputManager / AMS / Watchdog
- 22.3 ANR 现场采集：trace.txt / am_anr / data/anr/ / dropbox
- 22.4 ANR 调查方法论：主线程阻塞 / Binder 阻塞 / 死锁
- 22.5 ANR 案例库（5-10 个真实场景）
- 22.6 ANR 治理：监控、告警、防御

> **本章小结**：ANR 的根因永远不在 input/broadcast 本身——要找主线程为什么阻塞。

### 第 23 章　Java 异常

- 23.1 常见 Java 异常类型：NPE / ClassCast / ConcurrentModification / OOM / ANR 触发
- 23.2 Tombstone 与 Java 堆栈解析
- 23.3 启动期崩溃特殊排查
- 23.4 主线程异常恢复策略
- 23.5 第三方库异常的定位与治理
- 23.6 Java Crash 监控体系

> **本章小结**：90% Java 异常 = 空指针 + 状态错乱 + 第三方库兼容性。

### 第 24 章　Native 异常

- 24.1 信号处理：SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL
- 24.2 Tombstone 解析：寄存器 / 栈回溯 / 内存映射 / 共享库
- 24.3 so 库加载与符号化：addr2line / ndk-stack / symbolicator
- 24.4 AddressSanitizer / HWASan / UBSan / GWP-ASan
- 24.5 Native 案例库（5-10 个真实场景）
- 24.6 Native Crash 治理：crashpad / breakpad

> **本章小结**：Native 崩溃 80% 是内存问题——踩栈 / use-after-free / double-free。

### 第 25 章　系统无响应（SWT / Watchdog）

- 25.1 Watchdog 原理：30s 主线程 / 60s 总体
- 25.2 卡死 vs 慢：slow operation 阈值
- 25.3 调查方法：systrace / stack sampling / Handler sampling
- 25.4 卡死期间的现场保留
- 25.5 SWT 案例库（3-5 个）
- 25.6 SWT 治理

> **本章小结**：SWT 的根因 90% 是 SystemServer 内部某个服务卡死。

### 第 26 章　HANG 与死锁

- 26.1 死锁类型：自死锁 / 互锁 / 活锁 / 饥饿 / 顺序死锁
- 26.2 死锁检测：lockdep / 死锁线程 dump
- 26.3 死锁恢复策略：超时 / watchdog / 强制 kill
- 26.4 活锁：CPU 跑满但不响应
- 26.5 HANG 案例库

> **本章小结**：死锁排查需要线程 dump + 锁顺序分析双向验证。

### 第 27 章　REBOOT

- 27.1 重启类型分类：kernel panic / native restart / 异常掉电 / 用户操作
- 27.2 kernel panic：分析流程
- 27.3 native restart：watchdog / panic 重启
- 27.4 异常掉电：under-voltage / 异常关机 / 死机
- 27.5 重启栈分析：last_kmsg / pstore / ramoops / console-ramoops
- 27.6 重启率治理：监控 / 告警 / 防御

> **本章小结**：重启栈是唯一能告诉你为什么重启的证据，必须保留。

### 第 28 章　Kernel Exception

- 28.1 Kernel panic：触发条件、分析流程
- 28.2 Oops 与 BUG：模块 bug 的常见形式
- 28.3 WARN：内核告警机制
- 28.4 hung_task / RCU stall / softlockup
- 28.5 内核日志工具：pstore / ramoops / dmesg / syslog
- 28.6 内核问题调查方法

> **本章小结**：内核异常 = 必须有 last_kmsg，否则无法定位。

### 第 29 章　性能退化与稳定性边界

- 29.1 性能基线：冷启动 / 滑动帧率 / 内存水位
- 29.2 性能回归定位
- 29.3 稳定性指标：ANR 率 / Crash 率 / 用户感知率
- 29.4 性能与稳定性的张力（取舍）
- 29.5 性能治理 vs 稳定性治理

> **本章小结**：性能是稳定性的一部分，但治理策略不同。

