# JD 匹配矩阵（Reference · 稳定性架构师面试对位）

> **基线**：AOSP `android-17.0.0_r1`（API 37） + Linux `android17-6.18` LTS
>
> **配套**：[阅读指南-稳定性架构师.md](阅读指南-稳定性架构师.md) · [学习路线-稳定性架构师.md](../学习路线-稳定性架构师.md) · [缺口一览.md](../缺口一览.md)
>
> **最后更新**：2026-07-24

---

## 0. 怎么用本矩阵

本页把**典型 Android 稳定性架构师 JD** 的 13 个能力维度，映射到 smc-pub 已有系列，并标注：

| 列 | 含义 |
|:---|:-----|
| **覆盖度** | 高 / 中 / 低 / 缺失 —— 正文能否支撑面试叙述 |
| **面试优先级** | P0 必背 · P1 加分 · P2 稀缺项 |
| **推荐入口** | 从哪一系列开始读（链到仓库真实路径） |

**图例**：

- **高**：症状 + 取证 + 工具（或机制）三角闭环较完整
- **中**：机制有、治理/案例弱
- **低**：仅总览或 1–2 篇正文
- **缺失**：仅 README 占位或目录不存在

---

## 1. JD 维度定义（D1–D13）

| # | JD 维度 | 典型职责关键词 |
|:-:|:--------|:---------------|
| D1 | **Java Crash / JE** | UncaughtException、dropbox、堆栈解读 |
| D2 | **ANR** | Input/Service/Broadcast/Provider 四类、traces.txt |
| D3 | **Native Crash / NE** | tombstone、debuggerd、符号化 |
| D4 | **OOM / 内存** | LMKD、hprof、GC、memcg |
| D5 | **SWT / Watchdog** | SystemServer 杀、喂狗链路 |
| D6 | **Kernel / KE / 重启** | panic/oops、pstore、last_kmsg |
| D7 | **Framework 机制** | AMS/WMS/Input/Broadcast/Service |
| D8 | **IPC / Binder** | 阻塞、oneway 风暴、线程池 |
| D9 | **性能 / 启动** | 冷启动、丢帧、Perfetto |
| D10 | **工具 / 取证** | bugreport、dumpsys、trace |
| D11 | **APM / 治理 / 门禁** | SLI/SLO、灰度、监控体系 |
| D12 | **OEM / BSP / 跨平台** | 厂商定制、HAL、鸿蒙/跨端 |
| D13 | **AI for Stability** | 智能归因、异常检测、端侧 AI 风险 |

---

## 2. 维度 × 系列匹配矩阵

| JD 维度 | 覆盖度 | 面试优先级 | 推荐入口系列 / 路径 | 备注 |
|:--------|:------:|:----------:|:--------------------|:-----|
| **D1 Java Crash** | **高** | P0 | [S02-JE](../../02-Symptom/S02-JE/) → [F03-JE](../../03-Forensics/F03-JE/) → [Hprof](../../04-Tool/Hprof/) | 四大组件内嵌 40+ 案例见 [案例索引.md](案例索引.md) |
| **D2 ANR** | **高** | P0 | [S01-ANR](../../02-Symptom/S01-ANR/) → [F01-ANR](../../03-Forensics/F01-ANR/) → [ANR-Detection](../../04-Tool/ANR-Detection/) → [Input/06](../../01-Mechanism/Framework/Input/) → [Handler/06](../../01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/) | 约 80% P0 工单来源 |
| **D3 Native Crash** | **高** | P0 | [S03-NE](../../02-Symptom/S03-NE/) → [F04-NE](../../03-Forensics/F04-NE/) → [Native_Crash](../../01-Mechanism/Runtime/Native_Crash/)（8 篇） | Tombstone 16 段是面试高频 |
| **D4 OOM / 内存** | **高** | P0 | [Memory_Management](../../01-Mechanism/Kernel/Memory_Management/)（15）→ [ART/03-GC系统](../../01-Mechanism/Runtime/ART/03-GC系统/) → [Hprof](../../04-Tool/Hprof/) → [F06-HANG-OOM](../../03-Forensics/F06-HANG-OOM/) | 全库最厚子系列 |
| **D5 SWT / Watchdog** | **高** | P0 | [S04-SWT](../../02-Symptom/S04-SWT/) → [F02-SWT](../../03-Forensics/F02-SWT/) → [Watchdog](../../04-Tool/Watchdog/) | 区分 SWT vs ANR 是必考题 |
| **D6 Kernel / KE** | **高** | P1 | [S07-KE](../../02-Symptom/S07-KE/) → [F05-KE](../../03-Forensics/F05-KE/) → [Kernel/Process/11](../../01-Mechanism/Kernel/Process/) | Oncall OC07/OC08 待补，见 [Oncall/](../../03-Forensics/Oncall/) |
| **D7 Framework** | **高** | P0 | [Framework/](../../01-Mechanism/Framework/) 7 组件 + [Process_Exit/](../../01-Mechanism/Framework/Process_Exit/) | Activity/Input/Window 与 ANR 强相关 |
| **D8 Binder / IPC** | **高** | P0 | [Kernel/Binder/](../../01-Mechanism/Kernel/Binder/)（14）→ [Watchdog/BinderStarve](../../04-Tool/Watchdog/) → [ContentProvider/C07](../../01-Mechanism/Framework/ContentProvider/) | 案例 E08（oneway 风暴）待写 |
| **D9 性能 / 启动** | **高** | P1 | [S11-Startup/](../../02-Symptom/S11-Startup/) → [Startup 案例](../../06-Case/Startup/) → [ART/07-启动流程/](../../01-Mechanism/Runtime/ART/07-启动流程/) → [Perfetto/](../../04-Tool/Perfetto/) | 性能岗可主读此线 |
| **D10 工具 / 取证** | **高** | P0 | [F00-Overview/](../../03-Forensics/F00-Overview/) → [04-Tool/](../../04-Tool/) 7 系列 → [Tracing/](../../06-Foundation/Tools/Tracing/) | Dumpsys SOP 是 oncall 基本功 |
| **D11 APM / 治理** | **低** | P0（JD 高权重） | [S10-Measure/](../../02-Symptom/S10-Measure/)（**2/5**）→ [APM/](../../05-Governance/APM/)（**4/10**）→ [AI for Stability](../../05-Governance/AI-Native/03_AI_for_Stability/) | **最大 JD-内容错配**，见 [缺项规划 §1](../缺项规划-P0补全路线图.md) |
| **D12 OEM / BSP** | **缺失** | P1 | 机制侧：[App/Hook/](../../01-Mechanism/App/Hook/)（15）；治理侧：[OEM-BSP/](../../05-Governance/OEM-BSP/) **空** | Hook 可临时顶替；案例 E11 待写 |
| **D13 AI for Stability** | **高** | P2（加分） | [AI-Native/03_AI_for_Stability/](../../05-Governance/AI-Native/03_AI_for_Stability/) F01–F06 | AI-Debug 系列仍空 |

---

## 3. 常见 JD 原文 ↔ 系列对位

| 常见 JD 原文 | 本库对位系列 | 匹配度 |
|:-------------|:-------------|:------:|
| 「Crash/ANR/OOM 核心负责人」 | `02-Symptom/` + `03-Forensics/` + `04-Tool/` | 高 |
| 「覆盖 Framework + Native + Kernel」 | `01-Mechanism/Framework` + `Runtime/Native_Crash` + `Kernel/` | 高 |
| 「建设 APM / 监控 / 门禁体系」 | `05-Governance/APM/` + `S10-Measure/` | **低**（正文未完成） |
| 「跨厂商 / BSP 稳定性」 | `App/Hook/`（有部分）+ `OEM-BSP/`（空） | 低 |
| 「性能与稳定性平衡」 | `S09-PerfVsStab/` + `S11/B-启动性能/` + `ART/GC` | 高 |
| 「AI 辅助诊断 / 智能运维」 | `AI-Native/03_AI_for_Stability/` | 中高 |
| 「7×24 oncall / 应急响应」 | `03-Forensics/Oncall/`（**6/8**）+ F01–F07 | 中 |

---

## 4. 按面试优先级的最小阅读包

| 优先级 | JD 维度组合 | 最小阅读包（约 40–60 小时） | 覆盖面试题比例（估） |
|:------:|:------------|:------------------------------|:--------------------:|
| **P0** | D2 + D7 + D10 | S00 → S01 → F01 → ANR-Detection → Input → Handler → Dumpsys SOP → Perfetto ANR 篇 | ~35% |
| **P0** | D3 + D4 | S03 → F04 → Native_Crash 5 篇必读 → Memory_Management 01/02/09 → Hprof SOP | ~25% |
| **P0** | D5 + D8 | S04 → F02 → Watchdog 4 篇必读 → Binder 01/03/07 | ~20% |
| **P1** | D9 | S11/A+B → Startup E01–E03 → ART/07 → Perfetto Boot Trace | ~10% |
| **P1** | D6 | S07 → F05 → Kernel Process 信号/调试 | ~5% |
| **P0** | D11 | S10-01/02 → APM A01–A04 → AI for Stability F01/F03 | 话术必备，正文需补缺口 |
| **P2** | D12 + D13 | Hook 01/02/04/06/13 → AI for Stability 全 6 篇 | 加分 ~5% |

---

## 5. 缺口对 JD 的影响（行动建议）

| 若 JD 强调… | 当前库能否支撑 | 补读 / 补写建议 |
|:------------|:-------------|:----------------|
| oncall / 7×24 响应 | **部分** | 先读 [Oncall/OC01–OC06](../../03-Forensics/Oncall/)；REBOOT/KE 对照 F02/F05 + S06/S07 |
| 架构师级 APM 设计 | **弱** | 必读 A01–A04 + S10-01/02；A05–A10 与 S10-03–05 是 P0 补全项 |
| OEM 厂商经验 | **弱** | 机制：[Hook/](../../01-Mechanism/App/Hook/)；治理：等 OEM-BSP/；案例：等 E11 |
| 面试案例叙述 | **中** | E01–E04 + [案例索引](案例索引.md)；缺跨系列 E05–E11 |
| 行业 SLO 对标 | **缺失** | 等 `Industry-Benchmark/`；临时用 [S10-02](../../02-Symptom/S10-Measure/02-SLI与SLO设计：从指标到门禁.md) |

---

## 6. 与补全规划的对应关系

| P0 补全主题 | 影响的 JD 维度 | 规划文档 |
|:------------|:---------------|:---------|
| APM A05–A10（6 篇） | D11 | [缺口一览 §1](../缺口一览.md) |
| S10-03–S10-05（3 篇） | D11 | [缺口一览 §1](../缺口一览.md) |
| Oncall OC07–OC08（2 篇） | D6 + D10 | [缺口一览 §1](../缺口一览.md) |
| Cases E05–E11（7 篇） | D2/D4/D5/D8/D12 | [缺口一览 §1](../缺口一览.md) |
| Industry-Benchmark（4 篇） | D11 | [缺口一览 §1](../缺口一览.md) |

---

**作者**：Mavis · Stability Matrix Course
**基线**：AOSP 17 + android17-6.18
