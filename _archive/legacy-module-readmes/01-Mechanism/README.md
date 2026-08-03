# 01-Mechanism · Android 系统机制（按 AOSP 分层）

> **目标读者**：Android 性能架构师 / 稳定性架构师 / BSP 工程师
>
> **分类定位**：按 **AOSP 系统分层**组织 Android 机制——从硬件到 App，每层讲透"原理 + 源码 + 工程基线"
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）

---

## 0. 分类总定位

### 0.1 一句话定位

**Mechanism 是 smc-pub 最大的分类（441 文件 / 14.62 MB）——按 AOSP 系统分层（Hardware → Kernel → Native → Runtime → Framework → App）组织，让架构师能"自下而上"完整理解 Android 的工作原理。**

### 0.2 与其他分类的关系

| 维度 | Mechanism | Symptom | Forensics | Tool |
|:-----|:----------|:--------|:----------|:-----|
| **视角** | 机制（自下而上）| 症状（自上而下）| 取证（事后）| 工具（横向）|
| **核心问题** | "这层怎么工作的" | "线上出问题怎么归类" | "问题发生后怎么取证" | "用什么工具查" |
| **产出** | 源码 + 流程图 + 工程基线 | 风险地图 + 排查剧本 | dump 解读 + 抓取脚本 | 工具子命令清单 |

> **本分类是 Symptom / Forensics / Tool 的底层依赖**——任何症状、取证、工具都最终落到机制源码。

### 0.3 6 子分类（AOSP 分层）

```
Hardware  ─── 硬件抽象（HIDL/HAL）
   ↓
Kernel    ─── Linux 6.18 LTS + 14 子系统
   ↓
Native    ─── C/C++ 运行时（init/bootanim/surfaceflinger）
   ↓
Runtime   ─── ART + Native_Crash
   ↓
Framework ─── 7 大组件 + SystemServer
   ↓
App       ─── Handler/Looper + OEM Hook + App 层
```

---

## 1. 子分类导览

### 1.1 Hardware/（硬件层 · 占位）

- **状态**：🟡 占位（待 AOSP 17 HAL 完整文档化）
- **计划**：HIDL/AIDL HAL 定义、Display/Audio/Sensor HAL 实现

### 1.2 Kernel/（内核层 · 14 子系统 · 185 文件）

- **核心内容**：Linux `android17-6.18` 内核 + 14 个 Android 关键子系统
- **14 子系统**：

| 子系统 | 主题 | 重点 |
|:-------|:-----|:-----|
| Binder | 进程间通信 | AIDL + oneway + 死锁检测 |
| DM | 设备映射 | crypto + lvm |
| epoll | IO 多路复用 | LT/ET 模式 + LT vs ET |
| FS | 文件系统 | ext4 + f2fs + 挂载机制 |
| GKI | 通用内核 | vendor hook + 符号导出 |
| Input_Driver | 输入子系统 | 20 文件覆盖 evdev/input |
| Interrupt | 中断 | softirq / tasklet / workqueue |
| IO | IO 调度 | mq-deadline + bfq + cfq |
| Memory_Management | 内存管理 | MM_v2 系列 + 守护进程 |
| Partition | 分区 | super / vendor / system_a-b |
| Process | 进程 | cgroup freezer + cgroup v2 |
| Program_Execution | 程序执行 | ELF + linker + seccomp |
| socket | 网络 | TCP/UDP + zero-copy |
| Syscalls | 系统调用 | strace + ltrace |

### 1.3 Native/（Native 层 · 占位）

- **状态**：🟡 占位（待 AOSP_Startup A02-A03 Native 部分展开）
- **计划**：init 进程（C++ 部分）、surfaceflinger、bootanim

### 1.4 Runtime/（运行时层 · 150 文件）

- **ART 子系统（核心）**：

| 子模块 | 篇数 | 重点 |
|:-------|:----:|:-----|
| 00-总览 | 1 | ART 全局视角 |
| 01-字节码与指令集 | 2 | Dex + ART 17 解释器优化 |
| 02-编译与执行 | 2 | 编译路径全景 + ART 17 无锁 MQ + static final |
| 03-GC系统 | 99 | 9 子系统（基础理论/Heap/CMS/CC/GenCC/Reference/调度/其他/诊断） |
| 03-类加载与链接 | 2 | 类加载 + ART 17 优化 |
| 05-JNI | 2 | JNI 完整解析 + ART 17 JNI 优化 |
| 06-信号与ANR-Trace | 3 | SignalCatcher + ANR Trace + ART 17 兜底 |
| 07-启动流程 | 2 | app_process + ART 17 AppFunctions |
| 08-对比与演进 | 5 | ART vs JVM + Mainline + ART 17 演进 |

- **Native_Crash 子系统（8 篇）**：
  - NativeCrash 总览 + Linux 信号 + 内存保护 + debuggerd + 栈回溯 + Tombstone + 检测工具 + APM 集成

### 1.5 Framework/（框架层 · 73 文件）

- **7 大组件 + SystemServer**：

| 子模块 | 篇数 | 重点 |
|:-------|:----:|:-----|
| Activity | 10 | 生命周期 + 启动模式 + 任务栈 |
| Broadcast | 10 | 静态/动态注册 + ANR 风险 |
| Service | 10 | startService + bindService + 前台服务 |
| ContentProvider | 10 | 跨进程数据访问 + 权限 |
| Input | 9 | InputManager + 事件分发 |
| Window | 12 | WMS + SurfaceFlinger + Choreographer |
| Process | 9 | 进程架构 + AMS + Zygote |
| SystemServer | 1-2 | A04 启动链路 + A05 四大组件启动 |

### 1.6 App/（应用层 · 30 文件）

- **Handler-MessageQueue-Looper**：12 + HandlerThread + handler 笔记 + LooperPrinter + 2 张图
- **Hook/（OEM Hook）**：15 篇覆盖 Kernel/HAL/Native/ART/Framework/UI 6 层 Hook + 5 场景 + 5 大 OEM 对比

---

## 2. 文档统计

| 子分类 | 文件数 | 大小 | 重点标签 |
|:-------|:------:|:----:|:---------|
| Hardware/ | 0 | 0 | 🟡 占位 |
| Kernel/ | 185 | 6.16 MB | ✅ AOSP 17 完整 |
| Native/ | 0 | 0 | 🟡 占位 |
| Runtime/ | 150 | 4.07 MB | ✅ ART v2 完整 |
| Framework/ | 73 | 1.5 MB | ✅ 7 组件完整 |
| App/ | 30 | 1.3 MB | ✅ Handler + Hook 完整 |
| **总计** | **441** | **14.62 MB** | **smc-pub 最大分类** |

---

## 3. 强依赖 / 衔接

- **被依赖**：
  - [02-Symptom](../02-Symptom/) 引用 Kernel/Runtime/Framework 讲症状根因
  - [03-Forensics](../03-Forensics/) 引用 Kernel/Runtime/Framework 讲 dump 解读
  - [04-Tool](../04-Tool/) 引用 Kernel/Framework 讲工具实现
- **依赖**：
  - [06-Foundation](../06-Foundation/) Build-System 讲编译机制
  - [00-Meta/Reference/版本基线](../00-Meta/版本基线.md) 统一基线声明

---

## 4. 后续计划

- **Hardware/**：补 AOSP 17 HIDL/AIDL HAL 完整文档
- **Native/**：从 AOSP_Startup A02-A03 拆出 Native 部分
- **Framework/SystemServer/**：补 SystemServer 完整源码解析（参考 A04 + A05）
- **App/Hook/**：持续更新 5 大 OEM 风格对比（华为/小米/OPPO/vivo/三星）

---

**最后更新**：2026-07-19（阶段 3 完成）
**作者**：Mavis · Stability Matrix Course
