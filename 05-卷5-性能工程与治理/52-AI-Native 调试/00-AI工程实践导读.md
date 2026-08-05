# 04_AI_Engineering · AI 工程师视角的工程实践（12 篇）

> **本子系列**：v3 新增第 4 子系列。聚焦"**AI 工程本身怎么生产化**"——
> Prompt / Skill / Tools / Context / Eval / Harness / Durable / Policy / MCP / OTel GenAI / HITL / Release。
>
> **写作时间**：2026-06-30 开坑
> **系列归属**：`AI_Native_X/04_AI_Engineering/`

---

## 0. 为什么开这个子系列

### 0.1 已有 AI_Native_X 三大子系列的边界

| 子系列 | 解决什么 | 不解决什么 |
|---|---|---|
| **01_AI_Native_Runtime**（8 篇） | AI 在 Android 端**怎么跑起来**（HAL / NNAPI / TFLite / NPU / 端侧 LLM） | "AI 工程本身怎么生产化" |
| **02_AI_Native_OS**（6 篇） | AI **怎么重塑操作系统**（System Intelligence / AICore / AI Agent OS） | "AI 工程本身怎么生产化" |
| **03_AI_for_Stability**（6 篇） | AI **怎么治理稳定性**（智能归因 / 预测 ANR / 大模型日志分析） | "AI 工程本身怎么生产化" |

→ **三大子系列都聚焦"AI × 端侧 / OS / 稳定性"的垂直落地方向**，
缺的是"**AI 工程本身的语言基线**"——

- 用 LLM Coding 时怎么组织 Prompt / Skill / Tools / Context
- 生产 Agent 必备的 Eval / Harness / Durable / Policy / Release Control 怎么设计
- 2026 年工程圈已沉淀出哪些"能落地"的核心概念（Context Engineering / Trajectory Evals / MCP / OTel GenAI 等）

### 0.2 为什么现在必须补

2026 年工程圈的共识是：

> **Context 是首要架构资源**（要像管 CPU/内存一样管 Token）
> **Agent 是有状态进程**（不是一次 HTTP 请求，要支持 checkpoint / 幂等 / resume）
> **Prompt / Skill / Tool Profile 的变更要走发版门禁**（不是改完 yml 直接上线）

这些概念**与"Android 底层"无关**，但**与"AI 时代的工程师基本功"直接挂钩**——
对一个稳定性架构师 SE 来说：

- 用 LLM Coding 协作效率翻倍（Context Engineering + Skill 设计）
- 主导 AI APM / 智能归因项目时知道**评测什么 / 怎么发布 / 怎么守卫**（Trajectory Evals + Release Control + Policy-as-Code）
- 和 AI 算法团队对话有**共同语言**（MCP / OTel GenAI / Model Routing）

### 0.3 目标读者

| 读者类型 | 本系列价值 |
|---|---|
| 资深 Android / Kernel SE（你自己） | 补齐"AI 工程语言基线"，用 LLM Coding 协作提效 |
| AI 算法 / 端侧 SDK 工程师 | 看到"生产 Agent 必备的工程概念"全景 |
| 稳定性架构师（AI APM 主导者） | 智能归因 / 预测 ANR 项目落地时知道"评测、发布、守卫"怎么设计 |
| 技术 Lead（培养 SE） | 用本系列作为"AI 工程内训材料" |

---

## 1. 分篇大纲（AE01-AE12）

按"**由浅入深 + 主题聚合**"原则，12 篇分 4 个簇：

### 簇 1：基础四件套（AE01-AE04）—— 一切 Agent 的底座

| 编号 | 标题 | 核心议题 | 用户原文对应 |
|---|---|---|---|
| **AE01** | 从 Prompt 到 Skill 到 Tools 到 Context：AI 工程师的四层架构 | 四层职责边界 / 演进历史 / 一张认知地图 | 用户点名起点 |
| **AE02** | Context Engineering：Token 预算 / 缓存 / 记忆 / 压缩 | Context budget / Static-Dynamic 分界 / 三层记忆 / Context rot | 用户原文 §1 |
| **AE03** | Durable Execution：长任务的 Checkpoint / 幂等 / Resume | Replay 编排 + Resume 认知 / Checkpoint / Idempotent tools | 用户原文 §2 |
| **AE04** | Trajectory Evals：评路径不只评答案 | routingHit / tool misuse / 不必要 LLM 轮次 | 用户原文 §3 |

### 簇 2：策略与契约（AE05-AE08）—— 从软提示到硬约束

| 编号 | 标题 | 核心议题 | 用户原文对应 |
|---|---|---|---|
| **AE05** | Policy-as-Code：守卫前移到工具调用层 | Autonomy budget / Tool allowlist / Deny-first | 用户原文 §4 |
| **AE06** | MCP 与工具标准化契约 | Anthropic MCP / 懒加载 MCP Server / 边界（连工具 ≠ 替代 Harness） | 用户原文 §5 |
| **AE07** | Indirect Prompt Injection 与可信上下文 | RAG 召回 / 日志 / wiki 不可信输入 / 检索层 sanitization | 用户原文 §6 |
| **AE08** | Tool Idempotency 与副作用边界 | idempotency key / at-most-once / exactly-once / 读写分离 | 用户原文 §7 |

### 簇 3：交互与发布（AE09-AE10）—— 人怎么介入 / 资产怎么发版

| 编号 | 标题 | 核心议题 | 用户原文对应 |
|---|---|---|---|
| **AE09** | Human-in-the-Loop 工程化：Interrupt / Approval Packet | Interrupt & steer / checkpoint 暂停 / Approval packet 数据结构 | 用户原文 §8 |
| **AE10** | Release Control for Agent Assets：Prompt/Skill 变更走发版门禁 | Golden Replay / Score diff / Gate / 灰度 / 全量 | 用户原文 §9 |

### 簇 4：架构与可观测（AE11-AE12）—— 怎么扛、怎么挑、怎么量

| 编号 | 标题 | 核心议题 | 用户原文对应 |
|---|---|---|---|
| **AE11** | Compound Agent：Agent + Workflow 分层架构 | Agent 想 / Workflow 扛 / 万级并发 / 退避重试 / 跨天等待 | 用户原文 §10 |
| **AE12** | Model Routing / Cascading 与 OpenTelemetry GenAI 语义约定 | Haiku vs Opus / Cost-quality Pareto / OTel Span / gen_ai.* | 用户原文 §11+12 |

---

## 2. 阅读路径建议

```
┌──────────────────────────────────────────────────────────────────┐
│  第一次读（按顺序）：                                             │
│    AE01 → AE02 → AE03 → AE04 → AE05 → AE06 → AE07 → AE08         │
│    → AE09 → AE10 → AE11 → AE12                                    │
│    总计 12 篇 ≈ 6-8 万字，1-2 周读完                              │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  第二次查（按角色）：                                             │
│    · 主导 AI APM → 重读 AE03 / AE04 / AE05 / AE10                │
│    · 用 LLM Coding 协作 → 重读 AE01 / AE02 / AE05                │
│    · 跨团队 AI 架构评审 → 重读 AE06 / AE07 / AE11 / AE12         │
│    · 培养 SE 内训 → 按簇顺序讲，每簇配 1 个实战演练              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 与已有三大子系列的关系

```
                  ┌─────────────────────────────────────┐
                  │  01_AI_Native_Runtime（8 篇）       │
                  │  「AI 在端侧怎么跑起来」              │
                  └────────────────┬────────────────────┘
                                   │
                                   ▼
                  ┌─────────────────────────────────────┐
                  │  02_AI_Native_OS（6 篇）            │
                  │  「AI 怎么重塑操作系统」              │
                  └────────────────┬────────────────────┘
                                   │
                                   ▼
                  ┌─────────────────────────────────────┐
                  │  03_AI_for_Stability（6 篇）        │
                  │  「AI 怎么治理稳定性」                │
                  └────────────────┬────────────────────┘
                                   │
                                   ▼
                  ┌─────────────────────────────────────┐
                  │  04_AI_Engineering（12 篇）         │  ← 本系列
                  │  「AI 工程本身怎么生产化」            │
                  │  Prompt / Skill / Tools / Context   │
                  │  Eval / Harness / Durable / Policy  │
                  │  MCP / OTel GenAI / HITL / Release  │
                  └─────────────────────────────────────┘
```

**关键差异**：前三系列讲**"AI 作为技术对象怎么和 Android 集成"**；
本系列讲**"AI 作为生产系统的工程方法论"**——两者互补，不重叠。

---

## 4. 篇章状态

| 编号 | 标题 | 行数 | 状态 | commit |
|---|---|---|---|---|
| AE01 | 从 Prompt 到 Skill 到 Tools 到 Context：AI 工程师的四层架构 | 691 | ✅ 2026-06-30 | `4bba328` |
| AE02 | Context Engineering：Token 预算 / 缓存 / 记忆 / 压缩 | 927 | ✅ 2026-06-30 | `4bba328` |
| AE03 | Durable Execution：长任务的 Checkpoint / 幂等 / Resume | 773 | ✅ 2026-06-30 | `9a58f39` |
| AE04 | Trajectory Evals：评路径不只评答案 | 778 | ✅ 2026-06-30 | `9a58f39` |
| AE05 | Policy-as-Code：守卫前移到工具调用层 | 835 | ✅ 2026-06-30 | `aca7341` |
| AE06 | MCP 与工具标准化契约 | 760 | ✅ 2026-06-30 | `aca7341` |
| AE07 | Indirect Prompt Injection 与可信上下文 | 1099 | ✅ 2026-06-30 | `aca7341` |
| AE08 | Tool Idempotency 与副作用边界 | 1217 | ✅ 2026-06-30 | `aca7341` |
| AE09 | Human-in-the-Loop 工程化：Interrupt / Approval Packet | 1080 | ✅ 2026-07-07 | `cf06d0f` |
| **AE10** | **Release Control for Agent Assets：Prompt/Skill 变更走发版门禁** | **1053** | **✅ 2026-07-07** | **本次提交** |
| **AE11** | **Compound Agent：Agent + Workflow 分层架构** | **984** | **✅ 2026-07-07** | **本次提交** |
| **AE12** | **Model Routing / Cascading 与 OpenTelemetry GenAI 语义约定** | **1032** | **✅ 2026-07-07** | **本次提交** |

> **完成度**：**12/12 = 100%** 🎉🎉🎉
> - 簇 1「基础四件套」AE01-AE04 全部完成 ✅
> - 簇 2「策略与契约」AE05-AE08 全部完成 ✅
> - 簇 3「交互与发布」AE09-AE10 全部完成 ✅
> - 簇 4「架构与可观测」AE11-AE12 全部完成 ✅
>
> **总计**：12 篇 / ~10,800 行 / ~7.2 万字 / 4 簇闭环
>
> **本批次（AE10-AE12）净增**：3 篇 / 3,069 行 / 16.7 万字符
> - AE10：把 Prompt/Skill 变更从"改完直接上"升级为"Dev→Eval→Stage→Canary→Prod" 5 阶段流水线 + Golden Replay + Score Diff Gate + 5 秒 Rollback
> - AE11：把单一 Agent 升级为 Compound Agent（4 种分层模式 + Queue/Worker Pool + 退避重试 + 熔断 + Timer/Signal 跨天任务）
> - AE12：用 Cascading 让成本 ↓ 60% / P95 延迟 ↓ 40% + 用 OTel GenAI 让事故归因 4h → 30min

---

## 5. 每篇结构

1. **定位段**：这篇解决什么、不解决什么、读者预期
2. **演进历史**：从早期到现状的关键节点
3. **核心机制**：分层架构 / 数据流 / 状态机
4. **关键代码示例**：最小可运行 / 反例 / 正例对比
5. **稳定性视角**：与 Android / Kernel / ART 主干的关联点
6. **排查/落地案例**：现象 → 分析 → 根因 → 解法
7. **附录**：概念索引、路径对账、工程 checklist

---

## 6. 引用源（必须对齐）

本系列所有论述必须对齐以下一手来源：

| 概念 | 一手来源 |
|---|---|
| Context Engineering | Anthropic Engineering Blog "Effective context engineering for AI agents" (2025-04) |
| Durable Execution | Temporal.io 官方文档 / LangGraph Checkpointer 文档 |
| Trajectory Evals | LangSmith / Braintrust / Langfuse 官方文档 |
| Policy-as-Code | Anthropic Permission 文档 / Cloudflare Workers AI Gateway 文档 |
| MCP | Anthropic MCP 规范 v2025-06-18 / MCP Server 官方仓库 |
| Indirect Prompt Injection | OWASP LLM Top 10 / Anthropic Safety 文档 |
| OTel GenAI | OpenTelemetry GenAI Semantic Conventions v1.30+ |
| Human-in-the-Loop | Claude Code Interrupt 机制 / LangGraph interrupt() API |
| Model Routing | Anthropic 模型家族文档 / OpenAI Cascade 模式白皮书 |

> **原则**：所有"概念定义 / 数据指标 / 工具调用方式"必须有上述一手引用；
> 没有引用的"我的观点"必须明确标注 `[作者观点]`。

---

---

> **一句话总结**：
> 前 3 个 AI 子系列回答"**AI 在 Android 怎么落地**"；
> 本系列回答"**AI 工程本身怎么生产化**"——
> 是从"AI 用户"走向"AI 工程师"的语言基线。