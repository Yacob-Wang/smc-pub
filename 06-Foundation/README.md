# 06-Foundation · 基础能力入口：读源码 / 改源码 / 抓问题前的必备底座

> **基线**：AOSP 17.0.0_r1（API 37）+ Linux 6.18 LTS
>
> **角色**：稳定性架构师 Phase 0 必读入口
>
> **强依赖**：[学习路线 §3 Phase 0](../00-Meta/学习路线-稳定性架构师.md) · [承接/衔接清单](#6-与-smc-pub-全分类的关系)

<!-- AUTHOR_ONLY:START -->
## 本篇定位

- **目的**：把 smc-pub 散落在 Build-System / System-Integration / Dynamic-Updates / Tools 4 个子目录的"基础能力"收口为**按使用场景**的入口：读源码 / 改源码 / 抓问题
- **不是**：不复述子目录的逐篇导览（看各子目录 README）
- **承接自**：无（顶层入口）
- **衔接去**：[01-Mechanism](../01-Mechanism/) 机制 / [04-Tool](../04-Tool/) 取证工具 / [05-Governance/Security](../05-Governance/Security/) SELinux 治理

## 校准决策日志

| 轮次 | 决策 | 原因 |
|:----:|:-----|:-----|
| 1 | 升 README 维度"4 子分类"→"3 维场景" | Phase 0 新人关心"我现在要做 X，先看哪几篇"，不关心"文件在哪个目录" |
| 2 | 顶部 blockquote 5 行 → 3 行 | v6 §3.3 块引用 ≤3 行硬性；"承接自/衔接去"并入 AUTHOR_ONLY 段本篇定位 |
| 3 | 把 M1-M6 新系列规划显式纳入"后续计划" | SELinux / Android.bp / Bugreport 不再"散在元信息"，在 Foundation 入口就能看到 |
<!-- AUTHOR_ONLY:END -->

---

## 0. 3 维定位：Foundation 不是"基础库"，是"3 类使用场景的入口集合"

```
            ┌────────────────────────────────────────┐
            │  Foundation = 读源码 / 改源码 / 抓问题  │
            │  3 个场景的入口导航,不是"基础库"        │
            └────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   读源码前必看        改源码前必看         抓问题前必看
   ─────────────      ──────────────       ─────────────
   System-Integration Build-System          Tools/Tracing
   System-Composition Build/Soong           Tools/Android_Tools
   init.rc 解析        Android.bp            Tools/Memory_Analysis
   System Calls        SELinux 策略定制      logcat / bugreport
```

**为什么改"按使用场景"组织**：Phase 0 新人打开 Foundation 第一反应是"我下一步要做 X，先看哪几篇"，而不是"目录里有啥"。原 README 的"4 子分类"只是把文件位置做了一次镜子，没有导航价值。

---

## 1. 读源码前必看（5 篇）

**问题**：打开 AOSP 源码，第一步要看什么？

| # | 文章 | 重点 | 看完能做什么 |
|:-:|:-----|:-----|:------------|
| 1 | [System-Integration/01_System_Composition_And_Boot](../06-Foundation/System-Integration/01_System_Composition_And_Boot.md) | 系统组成 + 启动链 | 能从 boot.img 顺到 zygote |
| 2 | [Tools/Android_Tools/Init_RC_Complete_Guide](../../05-卷5-调查工具链/35-断点与 Native 调试/Init_RC_Complete_Guide.md) | init.rc 语法 + section + trigger | 能读懂 service / on / trigger |
| 3 | [02-Symptom/S11-Startup/A-启动机制/A03-Init进程与init.rc](../../../02-卷2-系统启动/A-启动机制/A03-Init进程与init.rc.md) | Init 进程源码视角 | 能从 init.cpp 顺到 first stage |
| 4 | [System-Integration/02_Partition_Mount_And_Usage](../06-Foundation/System-Integration/02_Partition_Mount_And_Usage.md) | fstab + 挂载时机 | 能解释 vendor / system / product 挂载关系 |
| 5 | [System-Integration/03_System_Initialization_Flow](../06-Foundation/System-Integration/03_System_Initialization_Flow.md) | rc 文件解析 + 服务启动顺序 | 能解释 service 之间的依赖 |

**读完去**：[01-Mechanism/Kernel/Process](../01-Mechanism/Kernel/Process/) 读进程子系统深挖。

---

## 2. 改源码前必看（6 篇）

**问题**：我要加一个 module / 改一个 service，先学什么？

| # | 文章 | 重点 | 看完能做什么 |
|:-:|:-----|:-----|:------------|
| 1 | [Build-System/01_AOSP_Build_Environment](../../01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/01_AOSP_Build_Environment.md) | AOSP 17 编译环境搭建 | 能 source build/envsetup.sh + lunch |
| 2 | [Build-System/02_Partition_Build_Process](../../01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/02_Partition_Build_Process.md) | 分区编译流程 | 能 m system / m vendor / m product |
| 3 | [Build-System/03_Image_Generation_And_Packaging](../../01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/03_Image_Generation_And_Packaging.md) | 镜像生成 + 打包 | 能解释 system.img 怎么来 |
| 4 | [Build-System/04_Build_Configuration_And_Options](../../01-卷1-Android系统基础与平台/02-AOSP 源码结构与构建系统/04_Build_Configuration_And_Options.md) | BoardConfig.mk + 编译选项 | 能改 BOARD_SYSTEM_IMAGE_FILE_SYSTEM_TYPE |
| 5 | [Tools/Android_Tools/Init_RC_Complete_Guide](../../05-卷5-调查工具链/35-断点与 Native 调试/Init_RC_Complete_Guide.md) | init.rc 自定义 service | 能写自己的 init.<device>.rc |
| 6 | [Tools/Git_Mastery/Git_Expert_Tutorial](../../05-卷5-调查工具链/35-断点与 Native 调试/Git_Expert_Tutorial.md) | AOSP 多仓 git 操作 | 能 repo forall + git push 到自己的分支 |

**读完去**：M3 新系列 [Android.bp / Soong / Blueprint 系列](#m3-m4-新系列androidbp--soong) 深入编译系统。

---

## 3. 抓问题前必看（8 篇）

**问题**：线上 bug，我抓 trace / 看 logcat / 读 dumpsys，先查什么？

| # | 文章 | 重点 | 看完能做什么 |
|:-:|:-----|:-----|:------------|
| 1 | [Tools/Tracing/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto](../../05-卷5-调查工具链/35-断点与 Native 调试/20-Trace抓取方法全面指南：ftrace-atrace-systrace-perfetto.md) | 4 类 trace 全景 | 知道哪种场景用哪个 |
| 2 | [Tools/Tracing/Android设备如何抓取trace](../../05-卷5-调查工具链/35-断点与 Native 调试/Android设备如何抓取trace.md) | 抓 trace 的 6 种方法 | 任何设备都能抓到 |
| 3 | [Tools/Tracing/ftrace的语法解析](../../05-卷5-调查工具链/35-断点与 Native 调试/ftrace的语法解析.md) | ftrace 语法 | 能读懂 ftrace log |
| 4 | [Tools/Android_Tools/Logcat_Complete_Guide](../../05-卷5-调查工具链/35-断点与 Native 调试/Logcat_Complete_Guide.md) | logcat 完整指南 | 能用 logcat -d -t -s 过滤 |
| 5 | [Tools/Tracing/block_bio_complete 与 block_rq_complete 核心区别](../../05-卷5-调查工具链/35-断点与 Native 调试/block_bio_complete 与 block_rq_complete 核心区别.md) | IO trace 关键事件 | 能区分 bio 级别 vs rq 级别 |
| 6 | [Tools/Tracing/ftrace-QA](../../05-卷5-调查工具链/35-断点与 Native 调试/ftrace-QA.md) | ftrace 常见 Q&A | 能解答"为什么 trace 抓不到" |
| 7 | [Tools/Memory_Analysis/PSI_Memory_Pressure_Analysis](../../05-卷5-调查工具链/35-断点与 Native 调试/PSI_Memory_Pressure_Analysis.md) | PSI 内存压力 | 能读懂 /proc/pressure/memory |
| 8 | [Dynamic-Updates/04_Update_Verification_And_Rollback](../../01-卷1-Android系统基础与平台/05-安全基础（SELinux · AVB）/Dynamic-Updates/04_Update_Verification_And_Rollback.md) | AVB 验证 + 回滚 | 能解释 bootloop 时的回滚链路 |

**读完去**：M4 新系列 [Bugreport 完整解析系列](#m4-m5-新系列bugreport-完整解析) 抓现场证据。

---

## 4. 4 子目录速查（保留原维度，便于按文件位置找）

> **使用时机**：上面 3 维找不到时，回到这里按"目录"找。

| 子目录 | 篇数 | 重点 | 何时进 |
|:-------|:----:|:-----|:------|
| **Build-System/** | 13 | 编译环境 + 分区 + 镜像 + 签名 | 改源码时 |
| **System-Integration/** | 3 | 系统组成 + 挂载 + 初始化 | 读源码时 |
| **Dynamic-Updates/** | 4 | OTA + A/B + 回滚 | 抓问题时 |
| **Tools/** | 17 | Init_RC + Logcat + Git + PSI + Tracing | 全场景通用 |

子目录详情见各子目录下的 README。

---

## 5. 后续计划：M1-M6 新系列接入 Foundation

按 [00-Meta/缺项规划-P0补全路线图 §1.1-1.4](../00-Meta/缺项规划-P0补全路线图.md) 的 6 个月排期，3 个新系列将挂在本目录下：

### M1-M2 新系列：SELinux 基础

挂 `06-Foundation/SELinux/`（8 篇，P0）

| # | 标题 | 重点 |
|:-:|:-----|:-----|
| 01 | SELinux 总览：MAC 机制在 Android 的落地 | 与 DAC 区别 + 稳定性视角 |
| 02 | 策略文件体系：sepolicy / .te / .cil / 编译产物 | 怎么从 .te 编译成 binary policy |
| 03 | Context 与 Label：四大主体的标签从哪来 | subject/object/... 标签怎么生成 |
| 04 | AVC 与 avc_denied：从一次 denied 反推策略 | 看 logcat 反推 |
| 05 | init 进程与 SELinux：分阶段加载 | kernel → init → vendor 三阶段 |
| 06 | 常见稳定性问题 | service crash / neverallow / build 失败 |
| 07 | 实战：定制 SELinux 策略排错 5 例 | 真实案例 |
| 08 | AOSP 17 演进：Treble + CIL + userspace 加载 | AOSP 17 变化 |

### M3-M4 新系列：Android.bp / Soong / Blueprint

挂 `06-Foundation/Build-System/Soong/`（8 篇，P0）

| # | 标题 | 重点 |
|:-:|:-----|:-----|
| 01 | 从 Make 到 Soong：AOSP 编译系统演进 | Make → Kati → Soong |
| 02 | Android.bp 语法精要 | module 类型 / 属性 / 依赖 |
| 03 | Blueprint：Soong 的中间表示与解析 | Blueprint 文件结构 |
| 04 | Soong 架构：plugin / provider / mutator | 内部运行机制 |
| 05 | Ninja 生成与 ninja 文件解读 | out/soong/build.ninja |
| 06 | 编译产物全梳理：out/ 目录结构 | .intermediates / .gen |
| 07 | 常见编译错误速查 | undefined ref / 循环依赖 |
| 08 | 实战：写一个自己的 Android.bp module | 含排错 |

### M4-M5 新系列：Bugreport 完整解析

挂 `03-Forensics/Bugreport/`（5 篇，P0，跨 Foundation + Forensics 双重引用）

| # | 标题 | 重点 |
|:-:|:-----|:-----|
| 01 | 总览与生成/解析 | `bugreport` 命令 + 解压 |
| 02 | 目录结构全梳理 | dumpstate / dumpsys / logcat / traces |
| 03 | 关键文件速查 | 每个文件"看什么 / 不看什么" |
| 04 | 实战 5 类典型案例 | ANR / NE / OOM / HANG / KE |
| 05 | bugreport vs perfetto trace | 工具边界 |

### M5-M6 取证补全

- `06-Foundation/Tools/Filesystem-Cheat-Sheet/` 2 篇（/proc /sys 字典）
- `../05-卷5-调查工具链/35-断点与 Native 调试/Logcat_Complete_Guide.md` 扩展 3 篇
- `01-Mechanism/Framework/Service/` 加 1 篇 dropbox / crash buffer

---

## 6. 与 smc-pub 全分类的关系

| 分类 | 视角 | 与 Foundation 的关系 |
|:-----|:-----|:-------------------|
| 01-Mechanism | 机制（自下而上）| **依赖**：所有源码路径引用 Foundation 的"读源码"维度 |
| 02-Symptom | 症状（自上而下）| **承接**：症状分析后定位到机制，需 Foundation 的"读源码"维度去查 |
| 03-Forensics | 取证 | **承接**：抓 bugreport / trace 依赖 Foundation 的"抓问题"维度 |
| 04-Tool | 工具（横向）| **平行**：dumpsys / perfetto / am 与 Foundation/Tools 互引 |
| 05-Governance | 治理 | **承接**：APM / 度量 / SELinux 治理依赖 Foundation 的"改源码"维度 |

---

**最后更新**：2026-07-27（重写为 3 维场景入口）
**作者**：Mavis · Stability Matrix Course
