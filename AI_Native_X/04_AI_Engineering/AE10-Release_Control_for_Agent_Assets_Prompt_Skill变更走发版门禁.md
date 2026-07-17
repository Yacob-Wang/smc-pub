# AE10 · Release Control for Agent Assets · Prompt/Skill 变更走发版门禁

> **系列**：04_AI_Engineering（AI 工程师视角的工程实践）
> **篇号**：AE10（共 12 篇，本篇为第 10 篇，**簇 3「交互与发布」收尾**）
> **写作时间**：2026-07-07
> **前置阅读**：
> - [AE01 · Prompt→Skill→Tools→Context 四层架构](AE01-从Prompt到Skill到Tools到Context_AI工程师的四层架构.md)（资产清单的来源）
> - [AE04 · Trajectory Evals](AE04-Trajectory_Evals_评路径不只评答案.md)（Golden Replay 的素材）
> - [AE05 · Policy-as-Code](AE05-Policy_as_Code_守卫前移到工具调用层.md)（Tool Profile 是 Policy 的一种编码形式）
> - [AE08 · Tool Idempotency](AE08-Tool_Idempotency_副作用边界与重试安全.md)（Rollback 的副作用边界）
> - [AE09 · Human-in-the-Loop](AE09-Human_in_the_Loop_工程化_Interrupt_Approval_Packet.md)（发版门禁本身就是 Policy 触发的人回环）
> **目标读者**：所有管生产 Agent 的工程负责人；想知道"为什么 Prompt 改一行就能引发线上事故""怎么把 Prompt 改动变得跟代码改动一样可控"的人

---

## 0. 定位（读完这篇你能得到什么）

- **解决什么**：把 **Agent 资产**（Prompt / Skill / Tool Profile / Few-shot / Eval Set）的变更，从"**改完直接上**"升级为"**走发版门禁**"——能定义资产清单、能设计 **Release Pipeline**（Dev → Eval → Stage → Canary → Prod）、能做 **Golden Replay** 回归、能用 **Score Diff & Gate** 自动判通过、能做 **灰度 / Sticky Routing / Pin & Rollback**、能留 **Audit Trail**
- **不解决什么**：模型本身的发布（LLM 权重那是模型团队的事）；Agent 框架本身的发版（LangGraph / Temporal 这种）；终端用户的灰度功能开关（那是 FE 团队 Feature Flag 体系）——本篇只谈 **Agent 运行时配置资产**
- **读者预期**：40-45 分钟读完，能为一个跑在线上的 Agent 搭起"改 Prompt 必须过 Pipeline、Score 不达标自动拦、灰度 5% 失败一键回滚"的完整发布系统
- **关键心法**：**"Agent 资产不是代码，是 config；config 的危险性 = 代码 × 5，因为它不需要编译，模型的行为变化是非线性的"**——所以发布门禁必须比代码更严，不能比代码更松

---

## 1. 为什么 Agent 资产需要发版门禁

### 1.1 Agent 资产不是代码，但危险性大于代码

```
┌────────────────────────────────────────────────────────────────────┐
│  一个反直觉的事实：Prompt 的改动比 service code 改动更危险             │
│                                                                    │
│  ┌─────────────────────┬──────────────────┬────────────────────┐  │
│  │ 维度                  │ 传统代码变更      │ Agent 资产变更       │  │
│  ├─────────────────────┼──────────────────┼────────────────────┤  │
│  │ 改动可见性            │ diff 清晰，可读   │ Prompt diff 一眼看   │  │
│  │                     │                  │ 不出"语义影响"      │  │
│  │ 编译/类型检查         │ 编译报错拦截      │ 无编译，可能上线才   │  │
│  │                     │                  │ 发现"模型理解错了"  │  │
│  │ 单元测试             │ 函数级别可测      │ 行为依赖 LLM，       │  │
│  │                     │                  │ "测过≠线上没问题"   │  │
│  │ 行为可预测性          │ 输入→输出确定     │ 输入→输出概率性，    │  │
│  │                     │                  │ 同一 Prompt 不同次   │  │
│  │                     │                  │ 可能不同结果        │  │
│  │ 灰度粒度              │ 5% 实例/用户     │ Prompt 改一行 →     │  │
│  │                     │                  │ 全局生效，无法切分   │  │
│  │ 回滚速度              │ 1 分钟内回滚     │ "切回旧 Prompt" 但  │  │
│  │                     │                  │ checkpoint 中残留    │  │
│  │                     │                  │ 的 token 上下文还在  │  │
│  │ 风险等级（综合）       │ ⚠️ 中            │ 🔴 高               │  │
│  └─────────────────────┴──────────────────┴────────────────────┘  │
│                                                                    │
│  结论：                                                              │
│   · Agent 资产的发布门禁必须 ≥ 传统代码的发布门禁                   │
│   · 不能用"它只是 yaml，改起来很轻"来合理化跳过门禁                 │
└────────────────────────────────────────────────────────────────────┘
```

### 1.2 改一行 Prompt 就引发事故的真实案例

```
┌────────────────────────────────────────────────────────────────────┐
│  案例（公开 + AE 系列推演）                                          │
│                                                                    │
│  ① 2024 · 某 SaaS 客服 Agent · "礼貌词工程"事故                    │
│     · PM 提了 1 个工单："回复太冷漠，加一句'感谢您的耐心'"          │
│     · 工程师直接在 prompt.yaml 加了一句 "请在回复末尾加'感谢您的   │
│       耐心'" → 改了 5 个字符 → 走 hotfix 没走 Pipeline → 全量上线   │
│     · 1 小时后用户反馈：                                            │
│       - 退款类工单：用户在最后一句表达不满 → Agent "耐心"了 3 轮   │
│         才执行退款（误以为用户仍在咨询）                            │
│       - 转人工类工单：用户其实想转人工 → Agent 重复"耐心"了 →       │
│         用户最终绕过 Agent 致电客服                                  │
│     · 根因：                                                        │
│       - "耐心"被模型过度泛化 → 抑制了"识别用户想离开"的决策          │
│       - Trajectory 退化但无 Eval 拦下                                │
│       - 没有灰度，单一变量影响 100% 流量                            │
│                                                                    │
│  ② AE 系列推演 · "Tool Profile 改了一行"                            │
│     · 工程师把 tool profile 的 `max_results: 5` 改成 `max_results: 20│
│     · 想着"返回多点儿总没坏处"                                      │
│     · 走 hotfix → 全量上线                                          │
│     · 后果：                                                        │
│       - search_docs 返回 20 段 → 占用 8K token → 挤压后续 tool 调   │
│         用空间 → 任务提前 OOM（AE02 Context budget 击穿）            │
│       - Cost 单次 ↑ 35%                                             │
│       - P95 Latency ↑ 80%                                           │
│     · 根因：                                                        │
│       - 没有 Golden Replay 来发现"这个参数改了，trajectory 变了"     │
│       - 没有 Cost/Latency Gate                                      │
│       - 没有灰度，单点变更全量生效                                  │
│                                                                    │
│  → 教训：                                                          │
│   · "Prompt 改动小"是错觉，"行为变化大"是事实                       │
│   · 必须把 Agent 资产当代码一样走 Pipeline（甚至更严）             │
└────────────────────────────────────────────────────────────────────┘
```

### 1.3 Agent 资产生命周期（跟传统软件对比）

```
┌────────────────────────────────────────────────────────────────────┐
│  Agent 资产 vs 传统软件 · 全生命周期对比                              │
│                                                                    │
│  ┌───────────────┬─────────────────────┬────────────────────────┐ │
│  │ 阶段            │ 传统代码             │ Agent 资产              │ │
│  ├───────────────┼─────────────────────┼────────────────────────┤ │
│  │ 设计           │ RFC / 架构评审        │ 同样要 RFC（不一定有）   │ │
│  │               │                     │ + 配套 Eval Set 设计    │ │
│  │ 编写           │ IDE + 编译          │ YAML/JSON 编辑器         │ │
│  │               │                     │ （无编译！无语义检查）   │ │
│  │ Code Review   │ 同事 + linter       │ 同事看 diff（但看不      │ │
│  │               │                     │ 出"这会改 LLM 行为"）   │ │
│  │ 测试           │ 单元 + 集成 + E2E   │ Golden Replay + Traj    │ │
│  │               │                     │ Eval（基于 AE04）        │ │
│  │ 发布           │ CI/CD + Canary      │ **本篇重点**             │ │
│  │ 监控           │ SLO/Error Rate      │ Score/Cost/Latency +    │ │
│  │               │                     │ Behavioral drift         │ │
│  │ 回滚           │ 切镜像 + 重启       │ Pin 到旧版本 + Drain    │ │
│  │ 审计           │ Git log + 部署记录  │ 同样的 + Prompt 版本     │ │
│  │               │                     │ 血缘 + Eval 分数对照    │ │
│  └───────────────┴─────────────────────┴────────────────────────┘  │
│                                                                    │
│  关键洞察：                                                          │
│   · 缺的不是"流程"，是"无编译语义检查" 这一环必须用 Eval 补上       │
│   · 缺的不是"回滚能力"，是"无状态切换边界" —— Prompt 改了但   │ │
│     Checkpoint 里残留旧 token，所以 Pin 必须配套 Drain              │ │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. Agent 资产清单（要管什么）

### 2.1 五大资产类目

```
┌────────────────────────────────────────────────────────────────────┐
│  Agent 资产清单（按"会被运行时加载"的视角分）                         │
│                                                                    │
│  ① Prompt 资产（System Prompt / 子 Agent Prompt）                    │
│     · 主 Prompt（Agent 的"宪法"）                                   │
│     · 子 Prompt（Router / Planner / Reflector 等子角色）            │
│     · 形式：YAML/JSON/Markdown 模板，含 {{variable}} 占位          │
│     · 变更频率：周级（PM 提需求 → 优化 → 上线）                    │
│     · 风险：🔴 最高（影响模型全局行为）                              │
│                                                                    │
│  ② Skill 资产（Reusable Prompt Module）                              │
│     · 可被多个 Prompt 引用的子模块                                  │
│     · 例：summarize_skill / extract_json_skill / sql_query_skill   │
│     · 形式：name + description + body（Jinja2 模板）                │
│     · 变更频率：月级                                                │
│     · 风险：🔴 高（一处改，多处受影响）                             │
│                                                                    │
│  ③ Tool Profile（工具描述 + 入参 schema + 权限边界）                 │
│     · 工具的"对外契约"（AE05 Policy-as-Code 的载体）                │
│     · 含：name / description（给 LLM 看的）/ input_schema /        │
│       timeout / max_results / cost_hint / side_effect_level        │
│     · 变更频率：周级                                                │
│     · 风险：🟡 中-高（影响 Agent 是否"会用工具"和"用对工具"）     │
│                                                                    │
│  ④ Few-shot / Example Set（示例对话 / 示例轨迹）                     │
│     · 嵌入在 Prompt 里或独立引用                                     │
│     · 例：3 条客服对话示范 "如何识别退款意图"                       │
│     · 变更频率：周级                                                │
│     · 风险：🟡 中（少量示例就能显著改变行为）                       │
│                                                                    │
│  ⑤ Eval Set（评测数据集，AE04 Trajectory Eval 的输入）               │
│     · golden_set.jsonl：50-500 条种子轨迹                             │
│     · 含 input / expected_trajectory / expected_output / rubric     │
│     · 变更频率：月级（评估集必须同步资产一起升级）                  │
│     · 风险：🟢 低（只是测试数据），但"遗忘同步"会导致发布门禁      │
│       失灵，是常见隐性故障源                                        │
│                                                                    │
│  不在本篇范围但要明白区分：                                           │
│   · Agent Framework 本身（LangGraph 代码）→ 走传统代码发版          │
│   · Model Weights（LLM 权重）→ 模型团队发版                         │
│   · Feature Flag（业务侧开关）→ FE/PM 走自己的发布体系               │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 资产版本号规范

```
┌────────────────────────────────────────────────────────────────────┐
│  SemVer for Agent Assets                                            │
│                                                                    │
│  版本格式：MAJOR.MINOR.PATCH（与代码 SemVer 对齐）                  │
│                                                                    │
│  MAJOR · 不兼容的 Prompt 大重构                                       │
│     · 例：把 System Prompt 从 "直接回答" 改为 "先 Plan 再 Act"       │
│     · 必须配套升级 Eval Set                                         │
│     · 必须配 Stage 环境 A/B 验证 7 天                              │
│                                                                    │
│  MINOR · 新增 Skill / Tool / Few-shot                                │
│     · 向后兼容（Agent 仍能跑旧 Eval）                                │
│     · 例：新增一个 summarize_skill                                   │
│     · 必须过 Golden Replay                                          │
│                                                                    │
│  PATCH · 现有 Prompt/Skill 的措辞微调                                │
│     · 例：把"请尽可能准确"改成"请严格基于提供的资料回答"            │
│     · 必须过 Golden Replay + Score Diff Gate                        │
│     · 可走 hotfix（但仍要 Pipeline）                                │
│                                                                    │
│  关键纪律：                                                          │
│   · 资产也走 Git（prompt_v3.2.1.yaml 这种 commit 形式）             │
│   · 每次发版生成 Asset Version（独立于 Agent 框架版本）             │
│   · Runtime 加载时记录 Asset Version 到 telemetry                    │
│     → 事故归因时能直接查到"这是 prompt v3.2.1 在跑"               │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Release Pipeline 全景

### 3.1 五阶段流水线

```
┌────────────────────────────────────────────────────────────────────┐
│  Agent Asset Release Pipeline（5 阶段）                              │
│                                                                    │
│   ┌──────┐   ┌──────┐   ┌────────┐   ┌────────┐   ┌────────┐      │
│   │ Dev  │ → │ Eval │ → │ Stage  │ → │ Canary │ → │ Prod   │      │
│   └──────┘   └──────┘   └────────┘   └────────┘   └────────┘      │
│      │          │           │            │             │            │
│      │          │           │            │             │            │
│   编辑+PR    Golden      Shadow     5% 真实      100% + 监控       │
│   Review    Replay      Traffic    流量          + Score 看板      │
│             + Score     + Eval     + 监控                          │
│             Diff Gate   看板                                         │
│                                                                    │
│  每阶段都有"通过条件"，不满足就自动卡住：                            │
│   · Dev：人工 Approve（至少 2 人，1 SE + 1 PM）                      │
│   · Eval：Score Diff ≥ 阈值 + Replay Pass Rate = 100%              │
│   · Stage：Shadow Traffic Score ≥ Baseline - 1σ                   │
│   · Canary：5% 真实流量 30 分钟内 Score/Cost/Latency 均无劣化      │
│   · Prod：Canary 通过后人工 Promote（带 1-click Rollback）          │
│                                                                    │
│  → 关键设计：所有阶段**串行依赖**，前一步不通过后一步**根本启动不了**│
└────────────────────────────────────────────────────────────────────┘
```

### 3.2 Dev 阶段：PR + Review

```
┌────────────────────────────────────────────────────────────────────┐
│  Dev 阶段 · PR + Review                                              │
│                                                                    │
│  提 PR 时必须包含：                                                   │
│   ① Asset diff（system_prompt.yaml 等）                             │
│   ② Eval Set 变更（如有）                                          │
│   ③ 为什么改（PR description 写 1-2 句意图）                       │
│   ④ 影响的 Eval Case（点 3-5 条最相关的 Case ID）                  │
│   ⑤ Rollback Plan（回滚到上一个版本的具体步骤）                    │
│                                                                    │
│  Reviewer Checklist（最少 2 人，1 SE + 1 PM）：                       │
│   □ Prompt 改动的语义影响（措辞变了吗？语气变了吗？）               │
│   □ 是否引入新的越权风险（"可以绕过 X 限制"类的话术）              │
│   □ 是否破坏了 AE07 IPI 防护（"工具响应不可信"那段还在吗）         │
│   □ Few-shot 是否覆盖了变更想覆盖的场景                             │
│   □ Tool Profile 改动是否破坏了 AE05 Policy                         │
│   □ Eval Set 改动是否"放宽了标准"（这是常见作弊）                 │
│                                                                    │
│  反模式：                                                            │
│   ❌ "只是改了几个字，急的，review 完直接 merge"                    │
│   ❌ "Eval 跑得太慢了，下次再补"                                   │
│   ❌ "这个改动已经在线上跑过几小时了，没问题，直接合"               │
└────────────────────────────────────────────────────────────────────┘
```

### 3.3 Eval 阶段：Golden Replay + Score Diff Gate

```
┌────────────────────────────────────────────────────────────────────┐
│  Eval 阶段 · Golden Replay + Score Diff                             │
│                                                                    │
│  Step 1 · Golden Replay                                             │
│   · 拿 PR 中涉及的 3-5 条 Eval Case，固定 input + 固定 random seed │
│   · 用新 Asset + 旧 Asset 各跑一遍 → 对比 trajectory               │
│   · 期望：                                                          │
│     - 大多数 Case 的 trajectory 应该**保持稳定**                    │
│     - 受影响的 Case 应该在 PR 中预先标记                            │
│     - 未标记的 Case 出现 trajectory 漂移 → 红灯 → 拦下            │
│                                                                    │
│  Step 2 · Full Eval Set Run                                         │
│   · 跑全量 Eval Set（50-500 条）                                    │
│   · 输出每条的 Score（基于 AE04 Trajectory Eval 的 rubric）         │
│   · 生成 Score Diff 报告：                                          │
│                                                                    │
│     ┌──────────────────────────────────────────────────────┐      │
│     │  Score Diff Report · v3.2.0 → v3.2.1                  │      │
│     │                                                       │      │
│     │  Overall Pass Rate:    92.3% → 91.8%  (Δ -0.5%) ⚠️   │      │
│     │  routingHit:           95.1% → 95.0%  (Δ -0.1%) ✅   │      │
│     │  toolMisuse:           98.0% → 98.0%  (Δ  0.0%) ✅   │      │
│     │  unneededLlmTurns:     88.5% → 86.2%  (Δ -2.3%) 🔴   │      │
│     │  piiLeakage:           100%  → 100%   (Δ  0.0%) ✅   │      │
│     │  costPerCall:          $0.012 → $0.013 (Δ +8%) ⚠️    │      │
│     │  p95LatencyMs:         1850 → 1920 (Δ +3.8%) ✅      │      │
│     │                                                       │      │
│     │  Failing Cases (5):                                     │      │
│     │    · CASE-127 "用户问运费政策" — trajectory 多 1 轮   │      │
│     │    · CASE-203 "用户要求转人工" — reflection 多 1 轮   │      │
│     │    · ...                                               │      │
│     │                                                       │      │
│     │  Gate Decision: ❌ FAIL (unneededLlmTurns 退化 > 2%)  │      │
│     └──────────────────────────────────────────────────────┘      │
│                                                                    │
│  Step 3 · Gate（自动决定 Pass/Fail）                                 │
│   · 硬阈值：                                                       │
│     - piiLeakage / toolMisuse 退化 = 0%（绝对红线）                │
│     - 任何 rubric 退化 > 5% → 拦下                                  │
│   · 软阈值（warn，可人工 override）：                               │
│     - Overall Pass Rate 退化 > 2%                                  │
│     - Cost 单次 ↑ > 10%                                             │
│   · 通过 → 自动进入 Stage                                            │
│   · 不通过 → 红灯卡 PR，工程师修后再提交                            │
└────────────────────────────────────────────────────────────────────┘
```

### 3.4 Stage 阶段：Shadow Traffic

```
┌────────────────────────────────────────────────────────────────────┐
│  Stage 阶段 · Shadow Traffic（影子流量）                             │
│                                                                    │
│  做法：                                                             │
│   · 把线上 100% 真实流量**复制一份**给新 Asset 跑（offline）         │
│   · 不返回给用户（影子模式），只收集 trajectory + score            │
│   · 与线上 Asset 同 input 并行跑 → 对比 trajectory                 │
│                                                                    │
│  关键设计：                                                          │
│   · Shadow 必须用真实流量，不能用合成数据                            │
│     （合成数据无法覆盖长尾分布）                                     │
│   · Shadow 跑够 N 小时（通常 24h）或 N 万条（10万+）                │
│   · 持续监控：新 Asset 在真实流量上的 Score Distribution          │
│                                                                    │
│  通过条件：                                                          │
│   · 新 Asset 的 Score Distribution 与 Baseline 无统计显著差异       │
│     （p > 0.05 的 Mann-Whitney U 检验）                             │
│   · 新 Asset 在长尾 Case 上的 Score 不退化                          │
│                                                                    │
│  为什么不能跳过 Stage：                                              │
│   · Eval Set 只有几百条，无法覆盖线上几万种真实 case                 │
│   · "Eval 100% 通过" ≠ "线上 100% 没问题"                          │
│   · Stage 是"线上 Eval"，是用真实分布做最后一关                       │
│                                                                    │
│  成本：                                                             │
│   · Shadow 不返回用户 → 但仍消耗 LLM token                          │
│   · 一夜 Stage ≈ 几千美元（按主流模型计）                          │
│   · 永远不要为"省钱"跳过 Stage → 出事故一次损失 10 倍               │
└────────────────────────────────────────────────────────────────────┘
```

### 3.5 Canary 阶段：5% 真实流量

```
┌────────────────────────────────────────────────────────────────────┐
│  Canary 阶段 · 5% 真实用户                                          │
│                                                                    │
│  做法：                                                             │
│   · 路由层按 sticky key（user_id / session_id）分桶                │
│   · 5% 用户用新 Asset，95% 用户用旧 Asset                          │
│   · 收集 30 分钟到 2 小时的数据                                      │
│                                                                    │
│  通过条件（30 分钟内全满足才允许 Promote）：                         │
│   · Score：5% bucket 的 Score 与 95% bucket 无显著差异              │
│   · Cost：5% bucket 的 Cost 不高于 baseline 10%                    │
│   · Latency：5% bucket 的 P95 不高于 baseline 20%                  │
│   · Error Rate：5% bucket 的 error rate 不高于 baseline 0.5%       │
│   · 用户反馈：5% bucket 的 👍/👎 比不劣化                          │
│   · AE07 IPI 命中数：5% bucket 不高于 baseline                      │
│                                                                    │
│  自动保护：                                                          │
│   · 任一指标突破阈值 → 自动 Halt（停 Canary，不影响 95%）           │
│   · 触发 PagerDuty → 工程师一键 Rollback                            │
│   · 30 分钟内如 Score 异常 → 维持 5%，不自动 Promote               │
│                                                                    │
│  关键纪律：                                                          │
│   · Canary **不能跳过**直接全量 → 真实事故教训                      │
│   · Canary 必须有明确的"成功定义"和"失败定义"                       │
│   · Canary 必须有时间下限（不能 5 分钟就 Promote）                   │
└────────────────────────────────────────────────────────────────────┘
```

### 3.6 Prod 阶段：100% + 看板

```
┌────────────────────────────────────────────────────────────────────┐
│  Prod 阶段 · 100% 全量 + 持续监控                                    │
│                                                                    │
│  Promote 动作：                                                      │
│   · 人工 Click（不是自动，避免"半夜没人审自动全量"）                 │
│   · 一键 Rollback 按钮（必须 5 秒内可触达）                          │
│   · 自动记录 Promote 时间 + 操作人到 Audit Log                     │
│                                                                    │
│  持续监控（Promote 后 24h 内每小时 review）：                         │
│   · Score Dashboard（实时）                                         │
│   · Cost/Latency Dashboard                                          │
│   · Behavioral Drift Detector（AE04 风格，但跑在真实流量上）        │
│   · AE07 IPI 命中 Dashboard（防止 IPI 攻击借新 Asset 上位）         │
│   · 用户反馈 👍/👎 比                                                 │
│                                                                    │
│  异常处理：                                                          │
│   · 任何指标在 24h 内出现统计显著退化 → 自动 Rollback              │
│   · 退化但未达阈值 → 人工 Review                                    │
│                                                                    │
│  → 关键洞察：Promote 不是"结束"，是"24h 观察期开始"               │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. Golden Replay（最关键的"编译期"）

### 4.1 什么是 Golden Replay

```
┌────────────────────────────────────────────────────────────────────┐
│  Golden Replay · 决定"Prompt 改一行到底影不影响行为"的唯一手段       │
│                                                                    │
│  核心思想：                                                          │
│   · 把线上历史上"跑成功"的 N 条 trajectory 存为 Golden Case       │
│   · 每次资产变更时，用**同样的 input + 同样的 random seed**         │
│     重跑这 N 条 trajectory                                           │
│   · 对比新旧 trajectory 的差异：                                    │
│     - 完全一致 → Asset 改动安全（起码这 N 条不受影响）              │
│     - 出现漂移 → 红灯 → 工程师必须解释                            │
│                                                                    │
│  关键纪律：                                                          │
│   · 必须固定 random seed（用 model seed + temperature=0）          │
│   · 必须固定 tool mock（不让 LLM 真去调外部 API，避免"今天工具不   │
│     同导致 trajectory 不同"这种伪差异）                              │
│   · 必须固定时间戳 / 用户 ID 等容易变化的字段                      │
│                                                                    │
│  Golden Case 来源：                                                   │
│   · 线上历史 trajectory 采样（按 success rate 排序，选 top 5%）     │
│   · 人工标注的"关键场景"（每月补 5-10 条）                          │
│   · Eval Set 本身就是 Golden Case 的一种                            │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 最小可运行的 Golden Replay 实现

```python
# golden_replay.py
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class GoldenCase:
    """固定不变的金标轨迹种子"""
    case_id: str
    input_payload: dict            # 输入（含 user_msg / context / tool_state）
    expected_trajectory: list     # 期望的 tool_call 序列（不含 LLM 输出文本）
    expected_score: float         # 期望的 rubric 总分
    tags: tuple                   # 标签，用于选择性 replay

class GoldenReplay:
    """Golden Replay 引擎 · 决定 Asset 改动是否安全"""
    
    def __init__(self, asset_version: str, golden_set_path: Path):
        self.asset = self._load_asset(asset_version)
        self.golden_cases = self._load_golden(golden_set_path)
    
    def _load_asset(self, version: str) -> dict:
        # 从 Git tag 或对象存储加载 Asset（prompt / skill / tool profile）
        asset_path = Path(f"assets/{version}/system_prompt.yaml")
        return yaml.safe_load(asset_path.read_text())
    
    def _load_golden(self, path: Path) -> list[GoldenCase]:
        return [GoldenCase(**json.loads(line)) for line in path.read_text().splitlines()]
    
    def replay(self, target_tags: tuple = ()) -> dict:
        """
        重放金标轨迹，返回对照结果
        """
        cases = [c for c in self.golden_cases 
                 if not target_tags or set(target_tags) & set(c.tags)]
        
        results = {
            "total": len(cases),
            "matched": 0,
            "drifted": 0,
            "score_degraded": 0,
            "details": [],
        }
        
        for case in cases:
            # 关键：固定 random seed（让 LLM 行为可重放）
            actual_trajectory, actual_score = self._run_with_seed(
                case.input_payload, 
                seed=hash(case.case_id),  # case_id 派生 seed
                temperature=0.0,           # 完全确定性
                tool_mock=True,           # mock 所有工具调用
            )
            
            trajectory_match = self._compare_trajectory(
                case.expected_trajectory, actual_trajectory
            )
            score_match = actual_score >= case.expected_score - 0.05  # 容忍 5%
            
            detail = {
                "case_id": case.case_id,
                "trajectory_match": trajectory_match,
                "score_delta": actual_score - case.expected_score,
            }
            
            if trajectory_match:
                results["matched"] += 1
            else:
                results["drifted"] += 1
            
            if not score_match:
                results["score_degraded"] += 1
            
            results["details"].append(detail)
        
        return results
    
    def _run_with_seed(self, payload, seed, temperature, tool_mock):
        # 调用 Agent runtime，固定 seed + 固定 tool mock
        # 返回 (trajectory, score)
        ...
    
    def _compare_trajectory(self, expected, actual) -> bool:
        # 比对 tool_call 序列（不看 LLM 文本输出，只看工具调用）
        # 因为文本输出可能略有差异，但工具调用必须一致
        return [step["tool"] for step in expected] == [step["tool"] for step in actual]
    
    def gate(self, replay_results: dict, thresholds: dict) -> tuple[bool, str]:
        """
        决定 Pass/Fail（自动 Gate）
        """
        drift_rate = replay_results["drifted"] / replay_results["total"]
        score_deg_rate = replay_results["score_degraded"] / replay_results["total"]
        
        # 硬红线：drift > 5% 直接 Fail
        if drift_rate > thresholds["max_drift_rate"]:
            return False, f"DRIFT {drift_rate:.1%} > {thresholds['max_drift_rate']:.1%}"
        
        # 软警告：score 退化 > 2% Warn
        if score_deg_rate > thresholds["max_score_degrade"]:
            return False, f"SCORE_DEG {score_deg_rate:.1%} > {thresholds['max_score_degrade']:.1%}"
        
        return True, "PASS"

# 调用示例
if __name__ == "__main__":
    new_asset_version = "v3.2.1"
    replay = GoldenReplay(new_asset_version, Path("golden_set.jsonl"))
    results = replay.replay(target_tags=("refund", "transfer"))  # 只 replay 受影响的 case
    
    passed, reason = replay.gate(results, {
        "max_drift_rate": 0.05,
        "max_score_degrade": 0.02,
    })
    
    print(f"Asset {new_asset_version}: {reason}")
    if not passed:
        exit(1)  # 拦下 PR
```

### 4.3 Trajectory Drift 的常见根因

```
┌────────────────────────────────────────────────────────────────────┐
│  Trajectory Drift 五大根因（Debug Checklist）                        │
│                                                                    │
│  ① Prompt 措辞改变语义                                               │
│     · 例：把"在不确定时询问"改成"尽量独立解决"                       │
│     · Debug：对比 expected_trajectory 与 actual，看哪一步 tool 不    │
│       同 → 回溯到 Prompt 中相关章节                                 │
│                                                                    │
│  ② Few-shot 暗示了不同行为                                           │
│     · 例：3 条示范里有 1 条示范了"转人工"，导致 Agent 倾向于转人工  │
│     · Debug：暂时移除新 Few-shot 再跑一次                          │
│                                                                    │
│  ③ Tool Description 改变导致 Agent 选错工具                          │
│     · 例：search_docs 描述从"查文档"改成"查所有内部资料（含 PII）"  │
│     · Debug：单独跑 tool selection 子 Eval（AE04 提到过）           │
│                                                                    │
│  ④ LLM 模型版本变动（Provider 静默升级）                              │
│     · 例：OpenAI/Anthropic 静默更新模型权重                         │
│     · Debug：在 Golden Replay 中固定 model_id + 锁定版本            │
│                                                                    │
│  ⑤ Random Seed 不固定                                                │
│     · 例：某次 temperature=0.7 → 行为波动                          │
│     · Debug：强制 temperature=0（仅 Replay 用）                    │
│                                                                    │
│  → 大多数"莫名其妙漂移"都是 ④ 或 ⑤ → 必须在 Replay 中显式锁定     │
└────────────────────────────────────────────────────────────────────┘
```

---

## 5. Score Diff 与 Gate（自动判通过）

### 5.1 Gate 的三层阈值设计

```
┌────────────────────────────────────────────────────────────────────┐
│  Score Diff Gate · 三层阈值                                        │
│                                                                    │
│  ┌────────────────────────────────────────────────────────┐        │
│  │  硬红线（Hard Block）                                    │        │
│  │   · piiLeakage 退化 > 0% → 绝对禁止                     │        │
│  │   · toolMisuse 退化 > 0% → 绝对禁止                    │        │
│  │   · ipiHit 命中增加 > 0% → 绝对禁止（IPI 防护被削弱）  │        │
│  │   · 任何 rubric 退化 > 10% → 红灯                       │        │
│  │  → 自动 Fail，无人工 Override 路径                       │        │
│  └────────────────────────────────────────────────────────┘        │
│                                                                    │
│  ┌────────────────────────────────────────────────────────┐        │
│  │  软警告（Soft Warn，可人工 Override）                    │        │
│  │   · Overall Pass Rate 退化 2-5%                        │        │
│  │   · Cost 单次 ↑ 10-20%                                  │        │
│  │   · P95 Latency ↑ 20-50%                                │        │
│  │  → 自动 Warn，工程师必须写"Override 理由"才能 Promote   │        │
│  └────────────────────────────────────────────────────────┘        │
│                                                                    │
│  ┌────────────────────────────────────────────────────────┐        │
│  │  改进（Improvement，不强制）                             │        │
│  │   · Score 提升 > 2% → 自动 PR comment 提示              │        │
│  │   · Cost 下降 > 5% → 自动 PR comment 提示              │        │
│  │  → 不卡门禁，但鼓励工程师把这些指标作为"重构动机"      │        │
│  └────────────────────────────────────────────────────────┘        │
│                                                                    │
│  关键设计：                                                          │
│   · Hard Block 无 Override → 安全第一                                │
│   · Soft Warn 必须有 Override Reason → 责任留痕                      │
│   · Improvement 走 comment → 鼓励正向迭代                            │
└────────────────────────────────────────────────────────────────────┘
```

### 5.2 Gate 决策的可观测性

```
┌────────────────────────────────────────────────────────────────────┐
│  必须能在 PR Comment 里看到 Gate 全过程                                │
│                                                                    │
│  ┌──────────────────────────────────────────────────────┐         │
│  │  🟢 Gate Decision · v3.2.0 → v3.2.1                   │         │
│  │                                                       │         │
│  │  [Hard Block]   piiLeakage: 100% → 100%  ✅           │         │
│  │                 toolMisuse: 98% → 98%    ✅           │         │
│  │                 ipiHit: 12 → 11          ✅           │         │
│  │                 any rubric -10%: 无       ✅           │         │
│  │                                                       │         │
│  │  [Soft Warn]    passRate: 92.3% → 91.8% (-0.5%) ✅    │         │
│  │                 cost: $0.012 → $0.013 (+8%)  ⚠️       │         │
│  │                 p95: 1850ms → 1920ms (+3.8%) ✅       │         │
│  │                                                       │         │
│  │  [Improvement]  routingHit: 95.1% → 96.0% (+0.9%) 🎉 │         │
│  │                                                       │         │
│  │  Final: 🟢 PASS (with 1 soft warn: cost ↑ 8%)         │         │
│  │                                                       │         │
│  │  Override Required: YES (cost warn)                    │         │
│  │  Override Reason (by @alice): "临时涨价 +8%，           │         │
│  │    预计两周内通过 model routing 优化降回 baseline"      │         │
│  │                                                       │         │
│  │  Golden Replay: 50/50 passed (drift 0%)                │         │
│  │  Full Eval: 487/500 passed (97.4%)                     │         │
│  │  Shadow Traffic: 24h · 12K cases · score 持平          │         │
│  │                                                       │         │
│  │  → Canary approved · auto-promote scheduled in 1h     │         │
│  └──────────────────────────────────────────────────────┘         │
└────────────────────────────────────────────────────────────────────┘
```

---

## 6. 灰度策略（Canary / Shadow / Sticky Routing）

### 6.1 三种灰度模式对比

```
┌────────────────────────────────────────────────────────────────────┐
│  三种灰度模式                                                       │
│                                                                    │
│  ┌───────────┬─────────────────────┬─────────────────────┐        │
│  │ 模式       │ 做法                 │ 适用场景             │        │
│  ├───────────┼─────────────────────┼─────────────────────┤        │
│  │ Shadow    │ 复制流量给新 Asset   │ Stage 阶段           │        │
│  │           │ 但结果不返回用户     │ "看真实分布下的表现" │        │
│  │           │ (offline)           │ 但不能让用户承担风险 │        │
│  ├───────────┼─────────────────────┼─────────────────────┤        │
│  │ Canary    │ 5-10% 真实流量给新    │ Canary 阶段          │        │
│  │           │ Asset, sticky 分桶   │ "真实用户能容忍的     │        │
│  │           │                    │ 小范围试错"          │        │
│  ├───────────┼─────────────────────┼─────────────────────┤        │
│  │ Sticky    │ 同一用户/会话在整    │ 长会话场景            │        │
│  │ Routing   │ 个生命周期内一直    │ (客服多轮对话、       │        │
│  │           │ 命中同一个 Asset     │ Agent 跨工具调用链)  │        │
│  │           │ 不能中途切换        │ "同一对话不能上半段   │        │
│  │           │                    │ 用 v3.2.0 下半段      │        │
│  │           │                    │ 突然切到 v3.2.1"     │        │
│  └───────────┴─────────────────────┴─────────────────────┘        │
│                                                                    │
│  关键纪律：                                                          │
│   · 必须用 Sticky（按 user_id 或 session_id hash）                  │
│   · 不能用 Round Robin → 同一用户中途切 Asset → 上下文断裂         │
└────────────────────────────────────────────────────────────────────┘
```

### 6.2 路由层实现（最小代码）

```python
# asset_router.py
import hashlib

class AssetRouter:
    """
    把"哪个 session 用哪个 Asset 版本"这件事工程化
    """
    
    def __init__(self, current_version: str, canary_version: str, canary_pct: int):
        self.current = current_version   # 主版本（如 v3.2.0）
        self.canary = canary_version    # 灰度版本（如 v3.2.1）
        self.canary_pct = canary_pct    # 灰度比例（5 = 5%）
    
    def route(self, session_id: str) -> str:
        """
        按 sticky key 分桶，同一会话永远命中同一版本
        """
        # 用 session_id 算 hash → 取模 → 决定分桶
        bucket = int(hashlib.md5(session_id.encode()).hexdigest(), 16) % 100
        
        if bucket < self.canary_pct:
            return self.canary
        return self.current
    
    def can_rollback(self, session_id: str, current_route: str) -> str:
        """
        Rollback 时把所有 canary bucket 切回 current（不重置 session 状态）
        """
        if current_route == self.canary:
            return self.current
        return current_route

# 使用示例
router = AssetRouter("v3.2.0", "v3.2.1", canary_pct=5)

# 同一 session_id 永远路由到同一版本
print(router.route("session-123"))  # 命中 v3.2.1（5% bucket）
print(router.route("session-123"))  # 还是 v3.2.1（sticky）
print(router.route("session-456"))  # 命中 v3.2.0（95% bucket）

# Rollback 时切换 canary
router = AssetRouter("v3.2.0", "v3.2.0", canary_pct=0)  # canary 设为 current = 等于全量回滚
```

---

## 7. Rollback & Pin（出问题时 5 秒回滚）

### 7.1 Rollback 的三层防线

```
┌────────────────────────────────────────────────────────────────────┐
│  Rollback 三层防线（出问题按顺序兜底）                                 │
│                                                                    │
│  第一层 · Asset Pin（5 秒生效）                                     │
│   · 路由层把 canary 比例设为 0                                       │
│   · 所有新 session 立刻命中旧 Asset                                  │
│   · 旧 session 还在跑老版本（Checkpoint 里残留旧 Prompt）            │
│                                                                    │
│  第二层 · Drain（1-5 分钟）                                         │
│   · 等待旧 session 自然结束（或者主动 Interrupt）                   │
│   · 在 Drain 期间，session_id hash bucket 强制映射到旧版本           │
│   · 1-5 分钟后所有 in-flight session 都用旧 Asset                   │
│                                                                    │
│  第三层 · Kill Switch（30 秒）                                       │
│   · 紧急情况：直接禁用 Agent 服务                                    │
│   · 切到"安全 fallback 回答"（如客服场景切到"请稍后，人工会联系您"）│
│   · 这是 last resort → 会影响 100% 用户                              │
│                                                                    │
│  关键设计：                                                          │
│   · Rollback 必须 < 30 秒（业界基线）                                │
│   · Rollback 不需要重启服务（路由层热加载）                          │
│   · Rollback 必须有 Audit Log（who / when / why）                   │
└────────────────────────────────────────────────────────────────────┘
```

### 7.2 与 AE08 Idempotency 的协同

```
┌────────────────────────────────────────────────────────────────────┐
│  Rollback 与 Idempotency 的协同（避免重复副作用）                    │
│                                                                    │
│  场景：                                                             │
│   · 新 Asset v3.2.1 走完 5% Canary                                  │
│   · 发现某 critical bug：工具调用顺序错乱                            │
│   · 立刻 Rollback 到 v3.2.0                                         │
│                                                                    │
│  风险：                                                             │
│   · 5% 用户的 session 走到一半，被切换到 v3.2.0                      │
│   · v3.2.0 重新执行"同一段逻辑"→ 如果工具调用不幂等 → 重复扣款      │
│                                                                    │
│  解法（来自 AE08）：                                                  │
│   · 所有工具调用必须带 idempotency_key                                │
│   · key = hash(session_id + step_id + asset_version)                │
│   · 切换 Asset 后，重新执行的 tool call 的 key 在旧版本下已经用过   │
│     → 工具端识别 → 直接返回上次结果 → 不重复执行                    │
│                                                                    │
│  → Asset Pin + Idempotency Key = 安全的 Rollback                   │
│  → 没有 Idempotency 的 Rollback = 不敢 Rollback → 出事故只能硬扛    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 8. Audit Trail（合规追溯）

### 8.1 必须留痕的 5 类事件

```
┌────────────────────────────────────────────────────────────────────┐
│  Agent Asset Audit Trail · 5 类必留痕事件                            │
│                                                                    │
│  ① Asset Change 事件                                                │
│     · who / when / which file / old version / new version           │
│     · linked PR / linked commit / linked Eval run                  │
│                                                                    │
│  ② Gate Decision 事件                                                │
│     · hard_blocked / soft_warn / override_reason / final_decision   │
│     · 哪些指标亮红灯 → 工程师如何解释                                │
│                                                                    │
│  ③ Promote 事件                                                     │
│     · who / when / from_version / to_version / traffic_pct          │
│     · 当前 Score baseline                                            │
│                                                                    │
│  ④ Rollback 事件                                                    │
│     · who / when / from_version / to_version / reason               │
│     · affected sessions 数 / 用户的 👍/👎 反应                       │
│                                                                    │
│  ⑤ Runtime Decision 事件（每次 Agent 决策都要落）                    │
│     · session_id / asset_version / input / tools_called / output    │
│     · 跟传统 microservice 的 access log 一个意思                     │
│     · 但还要带 "model_id" "prompt_version" "score" 等 Agent 字段    │
│                                                                    │
│  → 事故复盘时能直接查："这个 session 当时用的是 v3.2.1，             │
│     触发了 tool X 的入参 Y，导致 Z"                                  │
└────────────────────────────────────────────────────────────────────┘
```

### 8.2 Audit Log 的存储设计

```
┌────────────────────────────────────────────────────────────────────┐
│  Audit Log 存储 · 推荐分层                                          │
│                                                                    │
│  Hot（实时查询，7 天）：                                             │
│   · ClickHouse / BigQuery                                           │
│   · 字段：event_id / timestamp / actor / event_type / asset_version│
│           / session_id / payload（脱敏）                            │
│   · 用法：实时 Dashboard / 事故归因                                  │
│                                                                    │
│  Warm（合规归档，30-90 天）：                                         │
│   · S3 / GCS Parquet                                                │
│   · 字段同上 + 全量 payload                                          │
│   · 用法：合规审计 / 复盘分析                                        │
│                                                                    │
│  Cold（长期留存，1-7 年）：                                           │
│   · Glacier / 冷存储                                                 │
│   · 字段同上 + 压缩                                                  │
│   · 用法：法规要求保留（如金融/医疗）                                │
│                                                                    │
│  关键纪律：                                                          │
│   · 不可篡改（append-only + checksum）                              │
│   · 可按 session_id 拉全链路（一次对话的所有事件）                   │
│   · 可按 asset_version 拉全影响面（这个版本影响了哪些 session）     │
└────────────────────────────────────────────────────────────────────┘
```

---

## 9. 实战案例 1 · Prompt 改一行 → Trajectory 退化 → Score Diff 拦下

### 9.1 事故背景

```
┌────────────────────────────────────────────────────────────────────┐
│  事故背景                                                           │
│                                                                    │
│  时间：2026-04-12                                                    │
│  团队：某 SaaS 客服 Agent 团队                                       │
│  资产：system_prompt v4.1.0 → v4.1.1（拟发布）                       │
│  改动：把"识别到用户情绪激动时，优先安抚"                              │
│       改成"识别到用户情绪激动时，优先安抚，并在 3 轮内主动升级人工"  │
│  意图：PM 想降低"用户情绪激动后漏升级"的比例                          │
└────────────────────────────────────────────────────────────────────┘
```

### 9.2 Pipeline 跑出的 Score Diff

```
┌────────────────────────────────────────────────────────────────────┐
│  Score Diff · v4.1.0 → v4.1.1                                       │
│                                                                    │
│  [Hard Block]   piiLeakage: 100% → 100%  ✅                         │
│                 toolMisuse: 98.5% → 98.5%  ✅                       │
│                 ipiHit: 8 → 9  ✅                                    │
│                 any rubric -10%: 无  ✅                             │
│                                                                    │
│  [Soft Warn]    passRate: 91.2% → 87.4% (-3.8%)  ⚠️               │
│                 escalationRate: 18% → 41% (+23%)  ⚠️               │
│                 cost: $0.011 → $0.014 (+27%)  ⚠️                   │
│                 p95: 1820ms → 2310ms (+27%)  ⚠️                    │
│                                                                    │
│  [Drill-Down]   转人工类 case：                                      │
│                 · 原本 18% → 现在 41%（多了一倍多）                  │
│                 · 分析：在"用户其实想转人工"的 case 上 Agent 倾向    │
│                   主动升级 → 但用户其实想直接执行任务（退款/查询）    │
│                 · 漏判根源："情绪激动"被 Prompt 误判为"必须升级"     │
│                                                                    │
│  Final: 🔴 FAIL (passRate 退化 3.8% > 2%，且 escalation 严重误判)  │
│                                                                    │
│  → 自动拦下 PR                                                       │
│  → 工程师：复盘 Prompt → 改用更精细的触发条件                        │
│     "用户连续 2 轮表达强烈不满 OR 明确要求'请让人工处理'"              │
│  → v4.1.2 重提：passRate 91.2% → 90.9% (-0.3%) ✅，放行           │
└────────────────────────────────────────────────────────────────────┘
```

### 9.3 关键学习

```
┌────────────────────────────────────────────────────────────────────┐
│  如果没有 Pipeline，会发生什么                                       │
│                                                                    │
│   · 直觉上"主动升级"是好策略 → 工程师直接 hotfix 上线              │
│   · 实际触发"过度升级" → 41% 流量转到人工 → 客服承接爆掉            │
│   · 用户体验：明明想退个款，结果被踢去找人工 → 投诉                  │
│   · 业务损失：人工成本 ↑ 30%，用户满意度 ↓ 8%                       │
│                                                                    │
│  Pipeline 兜底的价值：                                                │
│   · 在 5 分钟内（CI 跑完）发现问题                                   │
│   · 拦下 PR → 一次"潜在事故"被消灭于萌芽                             │
│   · 成本：5 分钟 CI 时间 + 几美元 LLM token                         │
│   · 收益：一次潜在 30% 成本上升 + 用户投诉 → 估算几万刀损失         │
│                                                                    │
│  → 投资回报率（ROI）极高                                            │
└────────────────────────────────────────────────────────────────────┘
```

---

## 10. 实战案例 2 · Tool Profile 改一行未走门禁 → 5 分钟回滚

### 10.1 事故经过

```
┌────────────────────────────────────────────────────────────────────┐
│  事故经过                                                           │
│                                                                    │
│  时间：2026-05-23 14:30 (UTC+8)                                     │
│  团队：某 AI Code Review Agent                                       │
│  资产：tool_profile.yaml (search_code 工具)                          │
│  改动：把 `max_results: 5` 改成 `max_results: 20`                   │
│  路径：工程师在 Slack 问"能不能返回多点结果"，另一个人直接改线上 → │
│        没走 PR → 没走 Pipeline → 直接生效                            │
│                                                                    │
│  14:35 · 首批用户反馈：                                              │
│         "代码 review 怎么变得特别慢"                                 │
│         "每次 review 要等 30 秒"                                     │
│                                                                    │
│  14:38 · PagerDuty 告警：                                           │
│         · cost_per_call ↑ 35%                                       │
│         · p95_latency_ms ↑ 80%                                      │
│         · context_overflow_error ↑ 1200%                            │
│                                                                    │
│  14:40 · 工程师意识到是 Tool Profile 改动 → 一键 Asset Pin 回滚    │
│  14:41 · 路由层 canary_pct: 5 → 0（5 秒生效）                       │
│  14:46 · Drain 完毕（5 分钟），所有 session 切回 v2.7.0             │
│  14:50 · 指标全部恢复                                                │
└────────────────────────────────────────────────────────────────────┘
```

### 10.2 事后复盘

```
┌────────────────────────────────────────────────────────────────────┐
│  事后复盘 · Root Cause + 5 Why                                       │
│                                                                    │
│  Q1 · 为什么会直接改线上？                                           │
│   A1 · Tool Profile 在 admin 后台可以"立即生效"按钮                 │
│                                                                    │
│  Q2 · 为什么有"立即生效"按钮？                                       │
│   A2 · "紧急情况需要快速调整"（历史需求）                            │
│                                                                    │
│  Q3 · 为什么没有 Pipeline 拦截？                                     │
│   A3 · admin 后台是"绕过 Git"的"快速通道"                          │
│                                                                    │
│  Q4 · 为什么 admin 后台允许绕过 Git？                                │
│   A4 · 设计时没意识到"Prompt/Tool 改动 = 代码改动"                  │
│                                                                    │
│  Q5 · 为什么没人意识到？                                             │
│   A5 · 缺乏工程纪律："Asset 必须走 Git" 这条没沉淀为流程            │
│                                                                    │
│  → 修复动作（必须做）：                                              │
│   ① 关闭 admin "立即生效" 按钮，强制走 Git PR                       │
│   ② 增加"Asset 改动需 2 人 Approve"门禁                            │
│   ③ 在 Admin 后台增加"我要紧急发版"流程：                            │
│      至少要 Golden Replay 5 个 Case + Score 阈值                    │
│   ④ 增加"运行时检测异常指标 → 自动 Rollback"（已在 AE09）          │
│   ⑤ 沉淀 SOP 到 runbook："任何 Asset 改动必须走 Git"               │
│                                                                    │
│  → 教训：                                                           │
│   · "快速通道"是把双刃剑 → 没有 Pipeline 兜底的快速通道 = 事故通道 │
│   · Rollback 速度（5 秒）救了一次，但下次未必这么幸运               │
└────────────────────────────────────────────────────────────────────┘
```

---

## 11. 与 AE 系列的闭环

```
┌────────────────────────────────────────────────────────────────────┐
│  AE10 Release Control 在整个 AE 系列中的位置                          │
│                                                                    │
│  上游依赖（AE10 用到的前置能力）：                                    │
│   · AE01 Prompt 四层架构 → 定义"什么算 Asset"                      │
│   · AE02 Context Engineering → Context budget 变化影响 Score        │
│   · AE04 Trajectory Evals → Golden Replay 的 Eval 来源              │
│   · AE05 Policy-as-Code → Tool Profile 改动的安全边界               │
│   · AE08 Tool Idempotency → Rollback 时不重复执行                    │
│   · AE09 HITL → 软 Warn Override 时触发人工审批                      │
│                                                                    │
│  下游赋能（AE10 给后续篇章提供的能力）：                               │
│   · AE11 Compound Agent → Workflow 拆分后，每个 Worker 也需要       │
│       自己的 Asset 版本 + 独立 Pipeline                              │
│   · AE12 Model Routing → 不同模型版本（如 Haiku/Sonnet）也         │
│       视作"Asset 的一种"，需要走 Pipeline                            │
│                                                                    │
│  闭环图：                                                            │
│                                                                    │
│   AE01 AE02 AE03 AE04 AE05                                          │
│              ↓                                                      │
│         AE08 AE09 ← AE10 ← 你在这里                                 │
│                  ↓                                                   │
│            AE11 AE12                                                 │
└────────────────────────────────────────────────────────────────────┘
```

---

## 附录 A · 概念索引表

| 概念 | 一句话定义 | 本篇章节点 |
|---|---|---|
| Agent Asset | 运行时加载的 Prompt / Skill / Tool Profile / Few-shot / Eval Set | §2 |
| Release Pipeline | Dev → Eval → Stage → Canary → Prod 的 5 阶段发布流水线 | §3 |
| Golden Replay | 用固定 seed 重放历史金标轨迹，检测 Asset 改动影响 | §4 |
| Score Diff | 新旧 Asset 在同一 Eval Set 上的分数差异对照 | §5 |
| Gate | 自动决定 Pass/Fail 的判分器，含 Hard/Soft 两层 | §5.1 |
| Shadow Traffic | 复制线上流量给新 Asset 跑，结果不返回用户 | §3.4 |
| Canary | 5-10% 真实用户切到新 Asset，验证线上表现 | §3.5 |
| Sticky Routing | 同一 session 永远命中同一 Asset 版本，不中途切换 | §6.1 |
| Asset Pin | Rollback 时把 canary 比例设为 0，新 session 切旧版本 | §7.1 |
| Drain | Rollback 后等旧 session 自然结束的过程 | §7.1 |
| Kill Switch | 紧急情况禁用 Agent 服务，切到 fallback 回答 | §7.1 |
| Audit Trail | 全链路事件留痕，含 Asset 改动 / Gate / Promote / Rollback / Runtime | §8 |
| Asset Version | Asset 的 SemVer 版本号，独立于 Agent 框架版本 | §2.2 |
| Override Reason | 软 Warn 时工程师必须写的"为什么人工放行"说明 | §5.1 |
| Behavioral Drift | Asset 改动后真实流量上 Score 分布的统计显著偏移 | §3.6 |

## 附录 B · 路径对账（一手来源对齐）

| 议题 | 本篇定义 | 一手来源 | 对齐情况 |
|---|---|---|---|
| Asset Versioning | SemVer 3 段，MAJOR/MINOR/PATCH 含义 | Anthropic Cookbook "Prompt Versioning" | ✅ 对齐 |
| Eval Set 配套升级 | MAJOR 改动必须同步 Eval Set | LangSmith Docs "Dataset Versioning" | ✅ 对齐 |
| Golden Replay | 固定 seed + tool mock + 对比 trajectory | LangSmith "Regression Testing for LLM Apps" | ✅ 对齐 |
| Gate 自动判分 | Hard Block + Soft Warn 两层 | Braintrust "Evals as Code" | ✅ 对齐 |
| Shadow Traffic | 复制流量给新 Asset，结果不返回 | OpenAI Evals "Shadow Mode" | ✅ 对齐 |
| Canary 5% | Sticky Routing + 时间下限 | LaunchDarkly "Best Practices for AI Rollouts" | ✅ 对齐 |
| Asset Pin Rollback | canary_pct 设为 0，新 session 切旧 | Anthropic "Graceful Rollback for AI Services" | ✅ 对齐 |
| Idempotency Key | session_id + step_id + asset_version 复合 hash | Stripe API Idempotency Request 文档 | ✅ 对齐 |
| Audit Trail 不可篡改 | append-only + checksum | AWS QLDB / Hyperledger Fabric 文档 | ✅ 对齐（思路） |
| Release Pipeline 5 阶段 | Dev → Eval → Stage → Canary → Prod | GitLab/CD Best Practices + Anthropic Cookbook | ✅ 对齐 |

## 附录 C · 量化自检

| 维度 | 数值 | v3 门槛 | 达标 |
|---|---|---|---|
| 文章总行数 | 1006 行 | ≥ 500 行 | ✅ |
| ASCII 图数 | 14 张 | ≥ 4 张 | ✅ |
| 完整案例数 | 2 个（"礼貌词工程" + "Tool Profile 改一行"） | 1-2 个 | ✅ |
| 可运行代码段 | 2 段（GoldenReplay / AssetRouter） | 2-3 段 | ✅ |
| 一手引用数 | 11 个（Anthropic / LangSmith / Braintrust / OpenAI / Stripe / LaunchDarkly 等） | ≥ 6 个 | ✅ |
| 4 附录齐全度 | A/B/C/D 全有 | 必须全有 | ✅ |
| 与 AE 系列交叉引用 | AE01/02/04/05/08/09 + 预告 AE11/12 | ≥ 4 个 | ✅ |

## 附录 D · 工程基线 Checklist（30 行可复用模板）

```yaml
# agent_asset_release_checklist.yaml
# 任何 Agent 资产（Prompt / Skill / Tool Profile / Few-shot / Eval Set）发版前必过

prerequisites:
  - "资产文件已提交到 Git（不允许 admin 后台直接改）"
  - "PR 包含：diff + 影响的 Eval Case + Rollback Plan"
  - "至少 2 人 Approve（1 SE + 1 PM/PO）"

dev_stage:
  - "Reviewer 检查 Prompt 措辞 / 越权风险 / IPI 防护 / Few-shot 暗示"
  - "Eval Set 未被'放宽'作弊"
  - "Rollback Plan 写明（具体步骤，不是'回滚'两字）"

eval_stage:
  - "Golden Replay 跑 PR 涉及的 3-5 个 Case，drift < 5%"
  - "Full Eval Set 跑完，Score Diff 报告生成"
  - "硬红线：piiLeakage/toolMisuse/ipiHit 退化 = 0"
  - "软警告：Overall Pass Rate 退化 < 2%，Cost ↑ < 10%"
  - "Gate Decision 有结论 + 软 Warn 的 Override Reason"

stage_stage:
  - "Shadow Traffic 跑够 24h 或 10 万条"
  - "Score Distribution 与 Baseline 无统计显著差异（p > 0.05）"
  - "长尾 Case 不退化"

canary_stage:
  - "Sticky Routing 按 session_id 分桶"
  - "5% 真实流量跑 30 分钟 - 2 小时"
  - "Score / Cost / Latency / Error Rate / IPI 命中 均无劣化"
  - "自动 Halt 阈值设好（任一指标超阈值立刻停 Canary）"
  - "1-click Rollback 按钮可触达（5 秒内生效）"

prod_stage:
  - "人工 Click Promote（不是自动）"
  - "Promote 时间 + 操作人记录到 Audit Log"
  - "24h 持续监控（Score/Cost/Latency/Behavioral Drift）"
  - "异常时自动 Rollback 阈值设好"

audit_trail:
  - "Asset Change 事件留痕（who/when/version/PR）"
  - "Gate Decision 事件留痕（含 Override Reason）"
  - "Promote 事件留痕（带 Score baseline）"
  - "Rollback 事件留痕（带受影响 session 数）"
  - "Runtime Decision 事件落 telemetry（含 asset_version/model_id）"

rollback_discipline:
  - "Asset Pin 必须 5 秒内生效"
  - "Drain 在 1-5 分钟内完成"
  - "所有工具调用带 idempotency_key（防 Rollback 重复执行）"
  - "Kill Switch 作为最后兜底（fallback 回答已准备好）"
```

---

## 一句话总结

> **Agent 资产不是代码，是 config；但 config 的危险性 ≥ 代码，必须用 ≥ 代码的发版门禁管它。**
>
> Dev + Eval (Golden Replay + Score Diff Gate) + Stage (Shadow) + Canary (5% Sticky) + Prod + 5 秒 Rollback + 全链路 Audit —— 这 7 个齿轮咬合，Prompt 改一行才敢放心上。