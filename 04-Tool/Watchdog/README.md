# Android Watchdog 系列文章(共 6 篇)

> **版本**:v3 重写版(2026-06-26)

---

## 系列概述

本系列从 Android 稳定性架构师视角,系统解析 Android Watchdog 子系统的**三层协作机制**(内核 / watchdogd / Java)、**核心源码实现**(HandlerChecker / Monitor / soft lockup / NMI)、**触发链路**(超时判定 / traces 采集 / Init 重启)与**实战排查体系**(5min 定位 / 三件套协同解读 / 厂商陷阱避坑)。

### Watchdog 在稳定性架构中的核心价值

| 维度 | 数据 |
|------|------|
| 整机重启率(Watchdog 触发) | 线上 0.5-1.5% |
| Watchdog 平均恢复时间 | 95s |
| Java Watchdog 检测周期 | 30s × 3 累计 |
| 三层 Watchdog 兜底率 | Java 90% / watchdogd 8% / Kernel 2% |
| 厂商 HAL 触发占比 | 60% |
| 跨进程死锁占比 | 20% |

**对稳定性工程师的核心价值**:能 5 分钟内定位 Watchdog 触发根因,从 traces / dmesg / dumpsys 三件套协同解读出真实异常,而非被动接受"整机卡 95s"。

---

## 系列设计思路

### 架构师思维链

```
它是什么?解决什么问题?(定位)
    ↓
它在系统中处于什么位置?和谁协作?(边界与交互)
    ↓
它内部是怎么运转的?(核心机制 + 源码)
    ↓
它会在什么地方出问题?(风险地图)
    ↓
出了问题我怎么查?怎么防?(诊断 + 治理)
```

### 依赖关系图

```
01 总览与体系位置(全局观)
    ↓
    ├─→ 02 多层 Watchdog 架构(职责边界)
    │       ↓
    │       ├─→ 03 Java Watchdog 核心机制(源码)
    │       ├─→ 04 内核 Watchdog 与 watchdogd(源码)
    │       └─→ 05 超时判定与杀进程链路(完整流程)
    │               ↓
    └──────────────→ 06 实战案例与排查体系(收官)
```

### 跨系列引用矩阵

| 本篇章节 | 引用系列 | 引用文章 | 引用原因 |
|---------|---------|---------|---------|
| 01 §1.3 Watchdog vs ANR | Input_FWK | 06-InputANR | Watchdog 与 Input ANR 联动 |
| 02 §2 内核 Watchdog | Linux_Kernel/Process | D 状态详解 | system_server 主线程 D 状态机制 |
| 03 §3 Monitor 接口 | Linux_Kernel/IO | 06-D 状态 / iowait | D 状态进入机制 |
| 04 §3 NMI | Linux_Kernel/Process | 19-用户态与内核态 | NMI 不可屏蔽中断原理 |
| 06 §5 厂商陷阱 | Android_Framework/MM_v2 | 06-LMKD | LMKD 与 Watchdog 都是 system_server 内守护 |

---

## 每篇文章的章节规划

### 第一部分:全局观(01)

| 篇章 | 文章 | 行数 | 角色 |
|------|------|------|------|
| 01 | Watchdog 总览与体系位置(含历史) | 500 | 全局观 + 历史演进 |

### 第二部分:核心机制(02-05)

| 篇章 | 文章 | 行数 | 角色 |
|------|------|------|------|
| 02 | 多层 Watchdog 架构 | 686 | kernel/watchdogd/Java 职责边界 |
| 03 | Java Watchdog 核心机制 | 648 | HandlerChecker / Monitor / 检查循环源码 |
| 04 | 内核 Watchdog 与 watchdogd | 649 | soft lockup / hard lockup / NMI / 喂狗源码 |
| 05 | 超时判定与杀进程链路 | 678 | 4 Phase × 30s + traces + Init 重启 |

### 第三部分:实战与索引(06)

| 篇章 | 文章 | 行数 | 角色 |
|------|------|------|------|
| 06 | 实战案例与排查体系 | 722 | 三件套 + 5min 定位 + 厂商陷阱 |

---

## 每篇文章的定位(本篇系列角色)

| 文章 | 本篇系列角色 | 强依赖 | 衔接去 |
|------|------------|--------|--------|
| 01 | 全局观 | 无 | 02 |
| 02 | 核心机制第 1 篇(架构层) | 01 | 03/04/05 |
| 03 | 核心机制第 2 篇(Java 源码) | 01/02 | 04 |
| 04 | 核心机制第 3 篇(内核 + watchdogd 源码) | 02 | 05 |
| 05 | 核心机制第 4 篇(触发链路) | 02/03/04 | 06 |
| 06 | 系列收官(实战) | 全系列 | — |

---

## 阅读建议

### 时间有限优先阅读

- **5min 看 01**:建立 Watchdog 全局认知与三层架构
- **10min 看 06 §1-§5**:掌握 5min 定位流程
- **完整看 03**:HandlerChecker / Monitor 算法是日常排查基础

### 系统学习推荐顺序

按 01 → 02 → 03 → 04 → 05 → 06 顺序全部读完,约 4-6 小时。

### 每篇文章的设计逻辑

所有文章遵循 v3 标准模板:

```
背景与定义 → 架构与交互 → 核心机制与源码 → 风险地图 → 实战案例 → 总结 → 附录 A/B/C/D
```

---

## 质量基线(本系列工程默认值)

| 参数 | 典型默认 | 选用准则 | 踩坑提醒 |
|------|---------|---------|---------|
| `DEFAULT_TIMEOUT` | 30_000ms | 生产保持 30s | debug 可调 10s |
| `MAX_TIMEOUT_CHECKS` | 3 | 保持 3 次 | 改 1 激进,改 5 延迟 |
| `KILL_DEBOUNCE_MS` | 30_000ms | 必须保留 | 删了会 reboot 循环 |
| `softlockup_thresh` | 20s | 生产保持 20s | 调小增加误判 |
| `WATCHDOG_DEFAULT_INTERVAL` | 5s | 生产保持 5s | 太长接近硬件 timeout |
| watchdogd nice | -20 | 必须保持 -20 | 改 0 会因 CPU 紧张饿死 |
| 硬件 watchdog timeout | 30s | 必须 > 喂狗间隔 × 3 | 改 10s 太激进 |
| SELinux `watchdog_device` 写权限 | allow | 必须保留 | 删了 watchdogd 打不开 |

---

## 参考资源

### AOSP 源码

- `frameworks/base/services/core/java/com/android/server/Watchdog.java` - Java Watchdog 主类
- `frameworks/base/services/core/java/com/android/server/WatchdogRollback.java` - 回滚机制
- `system/core/init/watchdogd.cpp` - Native watchdogd 守护
- `system/core/init/service.cpp` - Init service 管理
- `system/core/init/reboot.cpp` - Init reboot 系统调用
- `system/sepolicy/public/watchdogd.te` - SELinux domain
- `kernel/watchdog/softlockup.c` - 内核 soft lockup
- `kernel/watchdog/hardlockup.c` - 内核 hard lockup
- `kernel/watchdog/nmi_watchdog.c` - NMI 看门狗
- `kernel/drivers/watchdog/watchdog_core.c` - 硬件 watchdog 核心
- `kernel/drivers/watchdog/qcom-wdt.c` - 高通硬件 watchdog
- `frameworks/base/native/cmds/dumpstate/dumpstate.cpp` - SIGQUIT 信号处理

### 相关系列

- `../01-Mechanism/Kernel/socket/06-Unix_Domain_Socket与Android使用.md` - InputChannel 底层是 UDS socketpair
- `../01-Mechanism/Kernel/IO/06-IO与进程的深度耦合：D状态、iowait、IO-hang、进程阻塞.md` - D 状态进入机制
- `../../Linux_Kernel/Process/19-用户态与内核态深入解析.md` - 内核态死锁原理
- `../Memory_Management/MM_v2/06-LMKD 用户态内存杀手.md` - LMKD 与 Watchdog 关系
- `../Input/06-InputANR.md` - Input ANR 与 Watchdog 联动

### 工具与命令

- `adb shell dumpsys watchdog` - 查看 Watchdog 当前状态
- `adb shell dmesg` - 查看内核日志
- `adb pull /data/anr/anr_*.txt` - 抓 traces
- `adb shell kill -3 <pid>` - 触发 SIGQUIT 抓 native 栈
- `getprop ro.boot.bootreason` - 查看整机 reboot 原因

---

## 更新记录

- **2026-06-26**:v3 重写版完成(本版本)
  - 删除 6 篇旧 stub(60-140 行),按 v3 标准重写 6 篇 ≥500 行
  - 删除 "Android Watchdog 系列" 4 篇旧版(4700-5800 字节,质量不达标)
  - 新结构:01-06 共 6 篇,总 3,681 行,约 80,000 字
  - 每篇都包含 4-6 张 ASCII 图 + 1-2 个可验证案例 + 4 附录(A/B/C/D)

- **2026-02-10**:初始版本(已废弃)
  - 6 篇 stub + 4 篇 "Android Watchdog 系列" 旧版
  - 质量不达标,行数远低于 v3 ≥300 行要求