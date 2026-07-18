# Android Framework（Java API 框架层）

> **作者角色**：Android 稳定性架构师
> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
> **写作规范**：[PROMPT-技术系列文章写作指南-v4.md](../../PROMPT-技术系列文章写作指南-v4.md)
> **本目录规划**：[三系列重写规划-2026-07-18.md](三系列重写规划-2026-07-18.md)
> **最后更新**：2026-07-18（M5.5 校验后 4 项硬伤全部处理）

---

## 一、目录结构

```
Android_Framework/
├── Activity/             # 四大组件 · Activity 系列（9 篇 · ~257KB · 5,802 行）
├── Service/              # 四大组件 · Service 系列（9 篇 · ~200KB · 5,041 行）
├── Broadcast/            # 四大组件 · Broadcast 系列（9 篇 · ~150KB · 4,395 行）
├── ContentProvider/      # 四大组件 · ContentProvider 系列（9 篇 · ~200KB · 4,364 行）
├── Stability/            # 症状维度 11 篇（总 ~9,000 行 · 22 锚点案例 · 五维闭环）
├── Stability-Forensics/  # 取证维度 8 篇（F00-F07 · ~282KB · 5,889 行）
├── AmCommand/            # 高频命令（am/pm/dumpsys 等）
├── ANR_Detection/        # ANR 检测机制深潜
├── AOSP_Startup/         # AOSP 启动流程（init → zygote → system_server）
├── Build_System/         # 编译系统
├── Dumpsys/              # dumpsys 工具全景
├── Hprof/                # hprof 内存快照分析
├── Input/                # Input 事件分发系统
├── Perfetto/             # Perfetto 追踪体系
├── Process/              # 应用进程首生
├── System_Integration/   # 系统集成
├── Watchdog/             # Watchdog 系统挂死监控
├── Window/               # Window 窗口系统
└── Dynamic_Updates/      # 动态更新机制
```

---

## 二、四大组件系列（M1-M4 · 2026-07-18 完成）

四大组件系列是本目录的**核心**，每个系列 9 篇正文 + 1 篇 README + 3-4 配套索引。

| 系列 | 篇数 | 总字数 | README | 索引 |
|------|------|--------|--------|------|
| [Activity](Activity/) | 9 + README | ~290KB / 5,802 行 | [Activity/README.md](Activity/README.md) | [Reference/案例索引.md](Reference/案例索引.md) §二 |
| [Service](Service/) | 9 + README | ~247KB / 5,041 行 | [Service/README.md](Service/README.md) | [Reference/案例索引.md](Reference/案例索引.md) §三 |
| [Broadcast](Broadcast/) | 9 + README | ~200KB / 4,395 行 | [Broadcast/README.md](Broadcast/README.md) | [Reference/案例索引.md](Reference/案例索引.md) §四 |
| [ContentProvider](ContentProvider/) | 9 + README | ~200KB / 4,364 行 | [ContentProvider/README.md](ContentProvider/README.md) | [Reference/案例索引.md](Reference/案例索引.md) §五 |
| **合计** | **36 + 4** | **~920KB / 19,602 行** | 4 个 | 1 个 |

---

## 三、稳定性系列（Stability 11 篇 · Stability-Forensics 8 篇 · 2026-07-18 完成）

**Stability 系列** 11 篇 ——"症状 + 取证 + 演进 + 横切 + 治理"五维闭环：

| # | 篇号 | 标题 | 角色 |
|---|------|------|------|
| 1 | S00 | 稳定性症状总览：7 类问题分类法 + 系统栈映射 | 全局观 |
| 2 | S01 | ANR：4 类 ANR 的症状区分 + 主线程为啥会卡 | 症状专题 1/7 |
| 3 | S02 | JE：未捕获 Throwable 全景 + 监控盲区 | 症状专题 2/7 |
| 4 | S03 | NE：6 种信号 → 症状 → tombstone 解读路径 | 症状专题 3/7 |
| 5 | S04 | SWT：SystemServer 卡死与 watchdog 触发的症状链 | 症状专题 4/7 |
| 6 | S05 | HANG：未被捕获的卡死（主线程 / IO / Binder / Kernel） | 症状专题 5/7 |
| 7 | S06 | REBOOT：重启源分类、cascade 链路、pstore / dump 体系 | 症状专题 6/7 |
| 8 | S07 | KE：Kernel 异常的用户空间可见信号 + 排查路径 | 症状专题 7/7 |
| 9 | **S08** | **AOSP 17 + K 6.18 稳定性机制全景**（6 ART 硬变化 + 8 K 硬变化 + 5 联动） | 演进对比专题（v4 §9 破例）|
| 10 | **S09** | **性能 vs 稳定性 5 大横向专题**（Binder 死锁 / IO 调度 / GC 卡顿 / 渲染卡顿 / 锁竞争）| 横切专题（v4 §9 破例）|
| 11 | **S10** | **稳定性度量学 + 发布门禁**（MTBF / 崩溃率 / ANR率 / 严重性 / 回归率 / Stability Score）| 总览篇 / 治理度量（v4 §9 破例）|

入口：[Android_Framework/Stability/README-Stability系列.md](Stability/README-Stability系列.md)

**Stability-Forensics 系列** 8 篇（F00-F07）—— 取证维度配套：
- F00 体系总览 / F01 ANR / F02 SWT / F03 JE / F04 NE / F05 KE / F06 HANG+OOM / F07 治理
- 总 ~282KB / 5,889 行 / 22 张 ASCII 时序图
- 入口：[Android_Framework/Stability-Forensics/README-Forensics系列.md](Stability-Forensics/README-Forensics系列.md)

**五维闭环**（"症状 + 取证 + 演进 + 横切 + 治理"）：
- **症状**（S00-S07 按 7 大症状切分）
- **取证**（Forensics F00-F07 配套）
- **演进**（S08 AOSP 17 + K 6.18 全景）
- **横切**（S09 5 大根因映射）
- **治理**（S10 度量 + 门禁 + 闭环）

---

## 四、Reference 索引（M5 配套 · 4 个文档）

| 索引 | 用途 | 状态 |
|------|------|------|
| [Reference/术语表.md](Reference/术语表.md) | 全局术语统一（禁止别名漂移，16 大类 300+ 术语）| 18.4KB |
| [Reference/案例索引.md](Reference/案例索引.md) | 4 大组件 40+ 实战案例（按症状/组件双维度）| 19.0KB |
| [Reference/引用矩阵.md](Reference/引用矩阵.md) | 4 大组件 22 条跨系列引用 + 65 条正文 inline 引用 | 11.1KB |
| [Reference/版本基线.md](Reference/版本基线.md) | AOSP 17 + android17-6.18 + 决策日志（含图表密度破例）| 8.5KB |

---

## 五、2026-07-18 M5.5 校验后状态

本目录在 2026-07-18 完成 M5.5 校验 + 修复，**4 项硬伤全部处理**：

| 硬伤 | 状态 | 关键数据 |
|------|------|---------|
| #1 ASCII 框图密度（11/36 篇 < 3 张）| 🟢 接受为 v4 §9 破例 | 11/36 接受破例 + 决策登记 |
| #2 基线跨系列不统一 | 🟢 修复 | 1936+ 处 6.12 → 6.18 回滚 |
| #3 案例 ID 锚点缺失 | 🟢 修复 | **46 个** CASE-XXX-NN 锚点（ACT 13 + SVC 11 + BC 10 + CP 12）|
| #4 跨系列引用不足 | 🟢 修复 | **65 条** inline 引用（ACT 20 + SVC 15 + BC 14 + CP 16）|

**校验报告**：[Android_Framework/校验报告-2026-07-18.md](校验报告-2026-07-18.md)（13.8KB / 26 项清单 / 4 项硬伤 / 3 轮校准）

**今日 commit 历史**（9 个 commit）：
```
7dcf258 fix(report): 硬伤 #1 接受为 v4 §9 破例，4 项硬伤全部处理
0baeee8 feat(Stability-S09): 子代理额外产出 - 性能 vs 稳定性 5 大横向专题
2d25fcf feat(案例ID锚点): CP 12 + Service 11 案例 ID 锚点回灌
b917c70 Broadcast 系列 10 案例 ID 锚点回灌
2329225 Activity 系列 13 案例 ID 锚点回灌
eb722a9 feat(Stability-S08): 子代理额外产出 - AOSP 17 + K 6.18 稳定性机制全景
e9452e9 feat(引用回灌): 4 大组件系列 65 条跨系列 inline 引用回灌
78955b6 fix(baseline): GC 系统附录 + Reference 文档基线回滚
554759f fix(baseline): rollback 6.12 → 6.18 跨系列基线回滚（撤销 verifier 误判）
```

---

## 六、剩余 backlog（下轮 v2 升级）

| 编号 | 内容 | 影响范围 |
|------|------|---------|
| B-1 | S08/S09 补 4 附录 + 破例决策记录段 | 2 篇正文（57KB + 37KB）|
| B-2 | C08 内部 5 处简写 `CASE-C-01~05` 规范化为 `CASE-CP-XX`（其中 04/05 对应 `CASE-CP-13/14`）| C08 案例集 |
| B-3 | S10 终稿已完成，纳入 v2 升级 | S10（已落档）|

---

## 七、版本与基线声明

- **AOSP 基线**：`android-17.0.0_r1`（API 37）
- **Linux 内核基线**：`android17-6.18` LTS（**AOSP 17 官方 GKI 内核**）
- **生效日期**：2026-07-18
- **基线升级规则**：按 [PROMPT v4 §8.3](../../PROMPT-技术系列文章写作指南-v4.md) 升级流程
- **跨系列一致性**：v4 §8 强制（术语表 / 案例索引 / 引用矩阵 / 版本基线 四件套）

---

## 八、对应 Android 架构层级

本目录对应 **Android 系统架构的 Java API Framework 层**：
- 上承应用层（App / AI Native X）
- 下接 Runtime（ART / Native Crash）
- 横连 Linux 内核（Linux_Kernel/）
- 配套工具（Tools / Perfetto / Dumpsys / Hprof / Hook）
