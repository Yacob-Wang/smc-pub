# 04-Tool · Android 稳定性调试工具（7 大工具）

> **目标读者**：Android 稳定性架构师 / APM 工程师 / oncall 工程师
>
> **分类定位**：按 **工具类型**组织 7 大调试工具——Dumpsys / Watchdog / Perfetto / Hprof / AmCommand / ANR-Detection / Tracing，每个工具讲透"子命令 + 实战脚本 + 性能开销"
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）

---

## 0. 分类总定位

### 0.1 一句话定位

**Tool 是 smc-pub 的"工具库"——把 Android 稳定性调试中用到的 7 大工具完整文档化，每个工具讲透"装在哪 + 怎么用 + 性能开销 + 适用场景"。**

### 0.2 与其他分类的关系

| 维度 | Tool | Mechanism | Symptom | Forensics |
|:-----|:-----|:----------|:--------|:----------|
| **视角** | 工具（横向）| 机制（自下而上）| 症状（自上而下）| 取证（事后）|
| **核心问题** | "用什么工具查" | "这层怎么工作的" | "线上出问题怎么归类" | "问题发生后怎么取证" |
| **产出** | 工具子命令清单 | 源码 + 流程图 | 风险地图 + 排查剧本 | dump 解读 + 抓取脚本 |

> **本分类与 Symptom / Forensics 强联动**——任何症状都需要工具取证，任何取证都靠工具支撑。

### 0.3 7 大工具一览

| # | 工具 | 篇数 | 核心场景 | AOSP 17 硬变化 |
|:--|:-----|:----:|:---------|:----------------|
| 1 | **Dumpsys** | 13 | 系统服务状态全查询 | meminfo 分代统计 + gfxinfo Choreographer 帧 |
| 2 | **Watchdog** | 9 | SWT 检测 + Looper 监控 | AnrHelper 增强 |
| 3 | **Perfetto** | 15 | 全栈 trace + 启动分析 | Boot Trace 抓全栈时序 |
| 4 | **Hprof** | 14 | 堆转储 + OOM 分析 | hprof Class Extent |
| 5 | **AmCommand** | 32 | am / cmd 子命令 | Activity Manager 命令全解 |
| 6 | **ANR-Detection** | 3 | ANR 检测 + 兜底 | AnrHelper 增强 + 进程优先级 |
| 7 | **Tracing** | 0（暂用 Foundation）| ftrace/atrace/systrace | 6.18 eBPF 签名 |

---

## 1. 子分类导览

### 1.1 Dumpsys/（13 篇 · 核心工具）

- **核心子命令**：`dumpsys meminfo` `dumpsys gfxinfo` `dumpsys activity` `dumpsys window` `dumpsys cpuinfo` `dumpsys batterystats`
- **v4 特色**：每篇 300+ 行 + 4 附录 + 3 轮校准
- **与 AOSP_Startup 联动**：D02 dumpsys+dropbox+bootstat 启动期三件套

### 1.2 Watchdog/（9 篇）

- **核心机制**：`Watchdog.java` 主线程心跳 + Looper 监控 + HandlerChecker
- **v4 特色**：ANR vs SWT 区别 + Watchdog 与 AnrHelper 协同
- **联动**：[03-Forensics/F02-SWT](../03-Forensics/F02-SWT/) + [02-Symptom/S04-SWT](../02-Symptom/S04-SWT/)

### 1.3 Perfetto/（15 篇 · 启动期必备）

- **核心能力**：boot trace + main thread + system_server + surfaceflinger
- **v4 特色**：配置 + sql + 实战脚本
- **联动**：[AOSP_Startup/D01 Perfetto Boot Trace](../02-Symptom/S11-Startup/D-启动工具/D01-Perfetto-Boot-Trace抓全栈启动时序.md)

### 1.4 Hprof/（14 篇）

- **核心能力**：堆转储 + LeetCode/LeakCanary 集成 + ART 17 Class Extent
- **v4 特色**：dumpsys meminfo + hprof 双视角
- **联动**：[02-Symptom/S06-HANG-OOM](../02-Symptom/S05-HANG/) OOM 取证

### 1.5 AmCommand/（32 篇 · 最大工具集）

- **核心子命令**：`am start` `am stop` `am broadcast` `am force-stop` `am profile` `am stack` 等
- **v4 特色**：每个子命令独立一篇 + 实战脚本
- **联动**：[01-Mechanism/Framework/Activity](../01-Mechanism/Framework/Activity/) AMS 实战

### 1.6 ANR-Detection/（3 篇 · ANR 专项）

- **核心机制**：[AnrHelper](https://cs.android.com/android/platform/superproject/main/+/main:frameworks/base/services/core/java/com/android/server/am/AnrHelper.java) + 进程优先级 + Input 通道
- **v4 特色**：AOSP 17 新增的 AnrHelper 增强 + 5s/20s/200s 阈值
- **联动**：[02-Symptom/S01-ANR](../02-Symptom/S01-ANR/) + [03-Forensics/F01-ANR](../03-Forensics/F01-ANR/)

### 1.7 Tracing/（0 篇 · 暂用 Foundation/Tools）

- **临时位置**：[06-Foundation/Tools/Tracing](../06-Foundation/Tools/Tracing/) 7 篇
- **v4 计划**：合并 04-Tool/Tracing/ 子分类
- **核心能力**：ftrace + atrace + systrace + perfetto

---

## 2. 文档统计

| 子分类 | 文件数 | 大小 | 重点标签 |
|:-------|:------:|:----:|:---------|
| Dumpsys/ | 13 | 0.50 MB | ✅ v4 化完成 |
| Watchdog/ | 9 | 0.35 MB | ✅ v4 化完成 |
| Perfetto/ | 15 | 0.45 MB | ✅ v4 化完成 |
| Hprof/ | 14 | 0.35 MB | ✅ v4 化完成 |
| AmCommand/ | 32 | 0.85 MB | ✅ v4 化完成 |
| ANR-Detection/ | 3 | 0.10 MB | ✅ v4 化完成 |
| Tracing/ | 0 | 0 | 🟡 占位（用 Foundation）|
| **总计** | **86** | **2.6 MB** | **核心工具就位** |

> 另 Foundation/Tools/Tracing 7 篇作为 Tracing 临时承载。

---

## 3. 强依赖 / 衔接

- **被依赖**：
  - [02-Symptom](../02-Symptom/) 引用 04-Tool/Dumpsys 等讲排查剧本
  - [03-Forensics](../03-Forensics/) 引用 04-Tool/Perfetto/Hprof 讲取证
  - [05-Governance/APM](../05-Governance/APM/) 引用 04-Tool/AmCommand 讲 APM 建设
- **依赖**：
  - [01-Mechanism/Framework](../01-Mechanism/Framework/) 讲工具实现原理
  - [01-Mechanism/Runtime](../01-Mechanism/Runtime/) ART 17 硬变化（如 AnrHelper）

---

## 4. 后续计划

- **Tracing/**：合并 Foundation/Tools/Tracing/7 篇到 04-Tool/Tracing/
- **Boot Trace 整合**：D01 Perfetto Boot Trace 与 Foundation/Tools 协同
- **eBPF 签名**：Linux 6.18 引入 eBPF 签名验证，需要新工具支持
- **AI 辅助诊断**：与 05-Governance/AI-Debug 联动，AI 解读 dumpsys 输出

---

**最后更新**：2026-07-19（阶段 3 完成）
**作者**：Mavis · Stability Matrix Course
