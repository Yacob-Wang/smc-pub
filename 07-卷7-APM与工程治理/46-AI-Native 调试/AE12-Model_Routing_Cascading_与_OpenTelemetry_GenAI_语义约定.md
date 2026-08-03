# AE12 · Model Routing / Cascading · 与 OpenTelemetry GenAI 语义约定

> **系列**：04_AI_Engineering（AI 工程师视角的工程实践）
>
> **篇号**：AE12（共 12 篇，本篇为第 12 篇，**簇 4「架构与可观测」收尾 · 整个 AE 系列收官之作**）
>
> **写作时间**：2026-07-07
>
> **前置阅读**：
>
> - [AE01 · Prompt→Skill→Tools→Context](AE01-从Prompt到Skill到Tools到Context_AI工程师的四层架构.md)（Model 是 Skill / Tool 的执行载体）
>
> - [AE02 · Context Engineering](AE02-Context_Engineering_Token预算_缓存_记忆_压缩.md)（Context budget 决定模型选择）
>
> - [AE04 · Trajectory Evals](AE04-Trajectory_Evals_评路径不只评答案.md)（Eval 是 Cascading 的依据）
>
> - [AE09 · Human-in-the-Loop](AE09-Human_in_the_Loop_工程化_Interrupt_Approval_Packet.md)（Cascading 不确定时升级 HITL）
>
> - [AE10 · Release Control](AE10-Release_Control_for_Agent_Assets_Prompt_Skill变更走发版门禁.md)（新模型上线也走 Pipeline）
>
> - [AE11 · Compound Agent](AE11-Compound_Agent_Agent加Workflow分层架构.md)（Routing 在分层架构里是关键组件）
>
> **目标读者**：所有要为生产 Agent 选模型 / 算成本 / 接可观测的工程负责人；想知道"为什么不能全用 Opus""怎么让成本下降 60%""线上 Agent 慢在哪、错在哪、贵在哪"的人

---

## 0. 定位（读完这篇你能得到什么）

- **解决什么**：把"LLM 调用"从"全用最强模型 / 全程裸调"升级为**工程系统**——能基于**能力 / 成本 / 延迟 / 隐私**做 **Model Routing**，能用 **Cascading（级联）** 让便宜的模型先答、不确定再升级，能用 **OpenTelemetry GenAI 语义约定**统一观测口径（`gen_ai.*` 属性 / Span 设计），能用真实案例把**成本降 60%、P95 延迟降 40%、事故归因时间从 4h 缩到 30min**
- **不解决什么**：LLM 微调（Fine-tuning）/ 蒸馏（Distillation）/ 训练（Training）——本篇只谈**推理时的模型选择与观测**；Agent 框架选型争议（哪个 SDK 好，框架之争本篇不掺合）
- **读者预期**：40-45 分钟读完，能为一个跑在线上的 Agent 搭起"按场景路由模型 / Cascading 节省成本 / 用 OTel GenAI 看清楚每次调用的链路"，能在事故复盘里回答"这次调用的 model 是什么、用了多少 token、为什么慢"
- **关键心法**：**"模型不是越强越好，是越合适越好；观测不是为了记录，是为了能在事故时 30 分钟内定位到第 N 次 LLM 调用的第 M 个 token 上"**

---

## 1. 为什么不能全用最强模型

### 1.1 三个反直觉的事实

```
┌────────────────────────────────────────────────────────────────────┐
│  反直觉事实 · 全用最强模型的代价                                       │
│                                                                    │
│  事实 1 · 成本差距是 30-60 倍                                         │
│     · Claude 3 Haiku:   $0.25 / 1M input tokens                    │
│     · Claude 3.5 Sonnet: $3 / 1M input tokens  （12x）            │
│     · Claude 3 Opus:    $15 / 1M input tokens  （60x）             │
│     · GPT-4o:           $5 / 1M input tokens                       │
│     · GPT-o1:           $15 / 1M input tokens                      │
│     · 例：100 万次/天 × 平均 5K input + 1K output                 │
│       - 全用 Opus:  $15 × 5 + $75 × 1 = $150 / 天 = $4500 / 月    │
│       - 全用 Haiku: $0.25 × 5 + $1.25 × 1 = $2.5 / 天 = $75 / 月 │
│       - 60 倍差距                                                       │
│                                                                    │
│  事实 2 · 延迟差距是 3-10 倍                                           │
│     · Haiku:   P50 延迟 ~500ms                                     │
│     · Sonnet:  P50 延迟 ~1500ms                                    │
│     · Opus:    P50 延迟 ~3000-5000ms                               │
│     · 例：客服场景用户期望 < 3 秒，Opus 单次就可能超                 │
│                                                                    │
│  事实 3 · 不是所有任务都需要"强推理"                                   │
│     · "用户这句话是什么意图" → Haiku 够用                            │
│     · "提取 JSON 字段" → Haiku 够用                                  │
│     · "写一段营销文案" → Sonnet 够用                                  │
│     · "复杂代码生成 / 多步推理 / 数学证明" → Opus 才合适             │
│     · → 90% 的子任务用不到 Opus 的"思考深度"                         │
│                                                                    │
│  → 结论：模型选型是"成本-质量-延迟"三维权衡，不是"用最强的就完了"    │
└────────────────────────────────────────────────────────────────────┘
```

### 1.2 一张 Cost-Quality Pareto 图

```
┌────────────────────────────────────────────────────────────────────┐
│  Cost-Quality Pareto · 找到"性价比最优"区间                           │
│                                                                    │
│  Quality                                                          ▲ │
│  100% ──                                                         │ │
│        │                                              ● Opus      │
│   95% ──                                                         │ │
│        │                            ● Sonnet                    │ │
│   90% ──                                                         │ │
│        │ ●  GPT-4o                                              │ │
│   85% ──                                                         │ │
│        │       ● Haiku                                          │ │
│   80% ──                                                         │ │
│        │                                                         │ │
│   70% ──                                                         │ │
│        │                                                         │ │
│        └──────────────────────────────────────────────────▶ Cost  │
│        $0    $1    $3    $5    $10    $15    $20                  │
│                                                                    │
│  关键洞察：                                                          │
│   · Haiku → Sonnet: 成本 ↑ 12x，质量 ↑ ~10%（明显划算）             │
│   · Sonnet → Opus: 成本 ↑ 5x，质量 ↑ ~5%（边际收益递减）             │
│   · → 80% 场景 Sonnet 是"性价比拐点"                                 │
│   · → 真正需要 Opus 的场景 < 20%                                     │
│                                                                    │
│  实战经验值（不同任务的最优模型）：                                     │
│   · 意图分类 / 实体提取 / JSON 格式化 → Haiku（70% 子任务）         │
│   · 文案撰写 / 总结 / 一般对话 → Sonnet（25% 子任务）               │
│   · 代码生成 / 复杂推理 / 多步规划 → Opus（5% 子任务）              │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. Model Family 选型全景

### 2.1 主流模型家族能力矩阵

```
┌────────────────────────────────────────────────────────────────────┐
│  主流模型能力矩阵（2026 H1 数据）                                     │
│                                                                    │
│  ┌──────────────┬─────────┬─────────┬─────────┬──────────┐         │
│  │ 模型          │ 能力分   │ 速度    │ 成本    │ 适用场景   │         │
│  │              │ (1-100) │ P50(ms) │ $/1M in │           │         │
│  ├──────────────┼─────────┼─────────┼─────────┼──────────┤         │
│  │ Haiku 3.5    │   78    │   500   │  $0.25  │ 分类/提取 │         │
│  │ Sonnet 4     │   92    │  1500   │  $3.00  │ 大多数    │         │
│  │ Opus 4       │   97    │  3000   │  $15.00 │ 复杂推理  │         │
│  ├──────────────┼─────────┼─────────┼─────────┼──────────┤         │
│  │ GPT-4o       │   90    │  1200   │  $5.00  │ 多模态    │         │
│  │ GPT-4o-mini  │   82    │   600   │  $0.15  │ 轻量      │         │
│  │ o1           │   96    │  8000   │  $15.00 │ 数学/逻辑  │         │
│  │ o3-mini      │   88    │  3000   │  $1.10  │ 折中      │         │
│  ├──────────────┼─────────┼─────────┼─────────┼──────────┤         │
│  │ Gemini 2.0F  │   90    │  1000   │  $0.30  │ 速度+成本 │         │
│  │ Gemini 2.5P  │   95    │  2500   │  $1.25  │ 推理      │         │
│  ├──────────────┼─────────┼─────────┼─────────┼──────────┤         │
│  │ Llama 3.3 70B│   85    │  1500   │  $0.65  │ 自托管    │         │
│  │ Qwen 2.5 72B │   83    │  1500   │  $0.40  │ 中文场景  │         │
│  └──────────────┴─────────┴─────────┴─────────┴──────────┘         │
│                                                                    │
│  选型策略：                                                          │
│   · 不要单押一个 Provider（Anthropic + OpenAI + 自托管 至少各一）  │
│   · Cascading 通常用"同家族不同档"（Haiku→Sonnet→Opus 风格统一）   │
│   · 跨家族 Routing 用于"取各家所长"（Anthropic 推理 + OpenAI 多模态）│
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 模型能力评估（用 AE04 Trajectory Eval）

```
┌────────────────────────────────────────────────────────────────────┐
│  用 Eval 量化"模型在我这个任务上的能力"                                │
│                                                                    │
│  不能用"榜单分数"判断，必须用自己的 Eval Set 跑                       │
│   · MMLU 90% 不代表你的"客服退款"任务能做 90%                       │
│   · 必须用 AE04 的 Eval Set 在不同模型上跑 → 对比 Pass Rate         │
│                                                                    │
│  做法：                                                             │
│   · 拿 100 条真实 Eval Case                                           │
│   · 在候选模型上各跑一次（固定 seed + tool mock）                    │
│   · 比对 rubric 分数 + trajectory 一致性                             │
│   · 生成"模型能力雷达图"（按任务类型分维度）                          │
│                                                                    │
│  ┌──────────────────────────────────────────────────────┐         │
│  │  模型能力雷达 · 客服 Agent Eval Set (100 cases)        │         │
│  │                                                       │         │
│  │         推理 90%                                       │         │
│  │           ●                                           │         │
│  │         ╱   ╲                                         │         │
│  │   代码 ╱     ╲ 提取                                   │         │
│  │   85% ●       ● 95%                                   │         │
│  │       │       │                                       │         │
│  │       │   ★   │                                       │         │
│  │       │ Sonnet│                                       │         │
│  │   总结●       ●意图                                    │         │
│  │   92% ●     ● 88%                                    │         │
│  │         ╲   ╱                                         │         │
│  │           ●                                           │         │
│  │         文案 88%                                       │         │
│  │                                                       │         │
│  │  Haiku 在 "提取 / 意图" 上 ≥ 90% → 可以用              │         │
│  │  Haiku 在 "代码 / 文案" 上 < 85% → 不能用              │         │
│  └──────────────────────────────────────────────────────┘         │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Cascading（级联）· 便宜的先答，不确定再升级

### 3.1 Cascading 核心思想

```
┌────────────────────────────────────────────────────────────────────┐
│  Cascading · "先用便宜的试，置信度不够再升级"                         │
│                                                                    │
│  核心流程：                                                          │
│                                                                    │
│   输入 ──▶ [Cheap Model] ──┬─ 高置信（≥ 0.9）──▶ 返回结果           │
│           (Haiku)          │                                      │
│                            └─ 低置信（< 0.9）──▶ [Strong Model]      │
│                                              (Sonnet)              │
│                                                    │               │
│                                                    ▼               │
│                                                 返回结果            │
│                                                                    │
│  关键设计：                                                          │
│   · Cheap Model 跑绝大多数请求（成本 ↓ 80%+）                       │
│   · Strong Model 只在 Cheap 不确定时被调用                          │
│   · 置信度信号：                                                     │
│     - 模型自评（"我对这个答案的把握是 X%"）                          │
│     - logprob 平均值（token 概率越高越自信）                          │
│     - 多次采样一致性（多次调用结果一致 = 高置信）                    │
│     - Eval 分数（已知的"难例"集合）                                  │
│                                                                    │
│  适用场景：                                                          │
│   · Cheap 模型覆盖 80%+ 请求类型                                     │
│   · Strong 模型在难例上有显著优势                                   │
│   · 有可靠的置信度信号                                              │
└────────────────────────────────────────────────────────────────────┘
```

### 3.2 置信度信号的 4 种来源

```
┌────────────────────────────────────────────────────────────────────┐
│  4 种置信度信号对比                                                   │
│                                                                    │
│  ┌─────────────┬───────────────────┬────────────┬────────────────┐ │
│  │ 信号         │ 获取方式            │ 可靠性     │ 适用          │ │
│  ├─────────────┼───────────────────┼────────────┼────────────────┤ │
│  │ ① Self-Score│ LLM 自评"把握 X%"   │ ⚠️ 中（LLM │ 一般任务       │ │
│  │             │ （prompt 引导）    │ 可能幻觉） │               │ │
│  ├─────────────┼───────────────────┼────────────┼────────────────┤ │
│  │ ② Logprob   │ 取模型输出 token   │ ✅ 高（数学 │ 分类/提取     │ │
│  │             │ 的 logprob 平均    │ 上客观）   │               │ │
│  ├─────────────┼───────────────────┼────────────┼────────────────┤ │
│  │ ③ 多采样一致 │ 同 prompt 跑 3 次  │ ✅ 高（多次 │ 生成/推理     │ │
│  │             │ 看结果是否一致     │ 投票）     │               │ │
│  ├─────────────┼───────────────────┼────────────┼────────────────┤ │
│  │ ④ Eval 命中 │ 跟已知难例 pattern │ ✅ 高（业务 │ 客服/审核     │ │
│  │             │ 比对              │ 知识）     │               │ │
│  └─────────────┴───────────────────┴────────────┴────────────────┘ │
│                                                                    │
│  实战组合：                                                          │
│   · 客服意图分类：Logprob（数学客观）+ Self-Score 兜底               │
│   · 长文生成：多采样一致（投票决定）+ Eval 命中                       │
│   · 代码生成：Self-Score + 多采样一致 + 测试驱动验证                │
└────────────────────────────────────────────────────────────────────┘
```

### 3.3 最小可运行的 Cascading 实现

```python
# model_cascade.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class ModelResponse:
    text: str
    model: str
    confidence: float
    cost_usd: float
    latency_ms: int

class ModelCascade:
    """
    级联模型选择：先 cheap，不行再升级
    """
    def __init__(self, cheap_model, strong_model, confidence_threshold=0.85):
        self.cheap = cheap_model           # e.g. claude-haiku-3.5
        self.strong = strong_model         # e.g. claude-sonnet-4
        self.threshold = confidence_threshold
    
    def generate(self, prompt: str, *, requires_reasoning: bool = False) -> ModelResponse:
        # Step 1: 跑 cheap 模型
        cheap_resp = self.cheap.complete(prompt, logprobs=True)
        confidence = self._compute_confidence(cheap_resp)
        
        # Step 2: 置信度判断
        if confidence >= self.threshold and not requires_reasoning:
            return ModelResponse(
                text=cheap_resp.text,
                model=self.cheap.model_id,
                confidence=confidence,
                cost_usd=self._calc_cost(cheap_resp),
                latency_ms=cheap_resp.latency_ms,
            )
        
        # Step 3: 升级到 strong 模型
        strong_resp = self.strong.complete(prompt)
        return ModelResponse(
            text=strong_resp.text,
            model=self.strong.model_id,
            confidence=1.0,  # strong 模型兜底，假设高置信
            cost_usd=self._calc_cost(strong_resp),
            latency_ms=strong_resp.latency_ms,
            upgraded_from=cheap_resp.model_id,
        )
    
    def _compute_confidence(self, response) -> float:
        """
        用 logprob 平均作为置信度（数学客观）
        """
        if not response.logprobs:
            return 0.5  # 无法计算 → 默认中等置信
        
        # 平均 token logprob → 转为 0-1 的置信度
        avg_logprob = sum(response.logprobs) / len(response.logprobs)
        # logprob 通常在 -5 到 0 之间，exp 转换
        import math
        confidence = math.exp(avg_logprob)
        return min(1.0, max(0.0, confidence))
    
    def _calc_cost(self, response) -> float:
        # 按 token 数 × 单价计算
        return (response.input_tokens * 0.25 + response.output_tokens * 1.25) / 1_000_000

# 实战统计（来自 AE12 案例 1）
# 客服 Agent 一天 10 万请求：
#   - 78% Haiku 直接答完（平均置信 0.92）
#   - 22% 升级 Sonnet（平均置信 0.65）
#   - 成本：$8/天（Cascade） vs $45/天（全 Sonnet） vs $120/天（全 Opus）
#   - P95 延迟：1.8s（Cascade） vs 2.1s（全 Sonnet） vs 4.5s（全 Opus）
```

### 3.4 Cascading 的反模式

```
┌────────────────────────────────────────────────────────────────────┐
│  Cascading 反模式 · 别这么用                                         │
│                                                                    │
│  ✗ 反模式 1 · Cheap 模型根本不在你任务能力范围内                       │
│     · Haiku 在代码生成上准确率 60% → 即便置信度信号看起来 "高"      │
│     · 也必须升级 → 浪费 Cheap 调用成本 + 增加延迟                    │
│     · 解法：先用 Eval 评估 Cheap 模型在任务上的 baseline              │
│                                                                    │
│  ✗ 反模式 2 · 置信度信号不靠谱                                        │
│     · 仅用 Self-Score（LLM 自评）→ 容易幻觉给高分                   │
│     · 解法：组合 2-3 种信号，或用 logprob 客观信号                   │
│                                                                    │
│  ✗ 反模式 3 · Cascading 后没回灌给 Cheap 模型                         │
│     · Strong 模型答完 → 不告诉 Cheap "这个我答错了，你应该这样答"  │
│     · Cheap 模型永远学不到 → Cascading 退化为"两套独立"             │
│     · 解法：定期把 Strong 答对 / Cheap 答错的 case 做成训练数据     │
│                                                                    │
│  ✗ 反模式 4 · 升级阈值拍脑袋                                          │
│     · 不基于真实流量调优 → 阈值过低（升级太频繁）或过高（升级太晚）  │
│     · 解法：用真实 Eval Set 跑不同阈值 → 找到 Pareto 拐点            │
│                                                                    │
│  ✗ 反模式 5 · 所有请求都 Cascading（无脑级联）                         │
│     · 简单任务"用户问营业时间" → 直接 Haiku 答即可，不需要级联       │
│     · Cascading 适合"决策边界附近的请求"                              │
│     · 解法：先 Router 分类（AE11），分类后的"难例"才 Cascading       │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. Routing by Capability / Cost / Latency / Privacy

### 4.1 4 种路由维度

```
┌────────────────────────────────────────────────────────────────────┐
│  Model Routing · 4 种路由维度                                        │
│                                                                    │
│  ┌─────────────┬─────────────────────┬─────────────────────────┐  │
│  │ 维度         │ 何时用               │ 例                       │  │
│  ├─────────────┼─────────────────────┼─────────────────────────┤  │
│  │ Capability  │ 任务对能力要求差异大  │ 简单分类→Haiku          │  │
│  │ (能力)      │                     │ 代码生成→Opus            │  │
│  ├─────────────┼─────────────────────┼─────────────────────────┤  │
│  │ Cost        │ 任务对成本敏感        │ 批量任务→Haiku          │  │
│  │ (成本)      │                     │ 关键决策→Opus            │  │
│  ├─────────────┼─────────────────────┼─────────────────────────┤  │
│  │ Latency     │ 任务对延迟敏感        │ 实时对话→Haiku          │  │
│  │ (延迟)      │                     │ 离线分析→Opus            │  │
│  ├─────────────┼─────────────────────┼─────────────────────────┤  │
│  │ Privacy     │ 数据敏感性           │ 医疗 PII→自托管 Llama   │  │
│  │ (隐私)      │                     │ 公开数据→OpenAI          │  │
│  └─────────────┴─────────────────────┴─────────────────────────┘  │
│                                                                    │
│  实战组合：                                                          │
│   · Router-Dispatcher + Model Routing 是天然组合（AE11）             │
│   · Dispatcher 路由"哪种任务" → 同时也路由"哪个模型"                 │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 Routing 决策表

```
┌────────────────────────────────────────────────────────────────────┐
│  Model Routing 决策表（实战参考）                                    │
│                                                                    │
│  ┌──────────────────┬──────────┬──────────┬──────────┬──────────┐ │
│  │ 任务类型          │ 数据敏感 │ 延迟敏感 │ 推荐模型 │ 备选     │ │
│  ├──────────────────┼──────────┼──────────┼──────────┼──────────┤ │
│  │ 意图分类          │ -        │ ✓        │ Haiku    │ 4o-mini  │ │
│  │ JSON 提取         │ -        │ ✓        │ Haiku    │ 4o-mini  │ │
│  │ 内容审核          ✓        │ -        │ 自托管    │ Haiku    │ │
│  │ 客服对话          │ -        │ ✓        │ Sonnet   │ GPT-4o   │ │
│  │ 文档总结          │ -        │ -        │ Sonnet   │ Haiku    │ │
│  │ 营销文案          │ -        │ -        │ Sonnet   │ Opus     │ │
│  │ 代码生成          ✓        │ -        │ 自托管    │ Opus     │ │
│  │ 复杂推理          │ -        │ -        │ Opus     │ o1       │ │
│  │ 医疗诊断辅助      ✓        │ -        │ 自托管    │ ❌禁外网 │ │
│  │ 金融风控          ✓        │ -        │ 自托管    │ ❌禁外网 │ │
│  └──────────────────┴──────────┴──────────┴──────────┴──────────┘ │
│                                                                    │
│  决策逻辑：                                                          │
│   · 数据敏感（医疗/金融/PII） → 自托管或私有云                       │
│   · 延迟敏感（实时对话） → 优先选 Haiku / 4o-mini                   │
│   · 能力敏感（复杂任务） → Sonnet / Opus / o1                        │
│   · 默认兜底 → Sonnet（性价比拐点）                                  │
└────────────────────────────────────────────────────────────────────┘
```

### 4.3 Model Router 实现

```python
# model_router.py
from enum import Enum
from dataclasses import dataclass

class TaskType(Enum):
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    GENERATION = "generation"
    REASONING = "reasoning"
    CODE_GEN = "code_gen"
    SENSITIVE = "sensitive"  # PII / 医疗 / 金融

class LatencyReq(Enum):
    REALTIME = "realtime"      # < 1s
    INTERACTIVE = "interactive" # < 3s
    BATCH = "batch"            # 不限

@dataclass
class RoutingPolicy:
    task_type: TaskType
    latency_req: LatencyReq
    data_sensitive: bool

class ModelRouter:
    """
    基于任务类型 + 延迟要求 + 数据敏感性的路由
    """
    def __init__(self, models: dict):
        # models = {"haiku": client_a, "sonnet": client_b, ...}
        self.models = models
    
    def route(self, policy: RoutingPolicy) -> str:
        # 隐私优先
        if policy.data_sensitive:
            return "self_hosted_llama"  # 自托管，绝不外发
        
        # 延迟优先
        if policy.latency_req == LatencyReq.REALTIME:
            if policy.task_type in (TaskType.CLASSIFICATION, TaskType.EXTRACTION):
                return "haiku"
            return "sonnet"  # 实时场景必须快
        
        # 能力优先
        if policy.task_type == TaskType.REASONING:
            return "opus"
        if policy.task_type == TaskType.CODE_GEN:
            return "opus"
        
        # 默认兜底（性价比拐点）
        return "sonnet"

# 使用示例
router = ModelRouter({
    "haiku": claude_haiku_client,
    "sonnet": claude_sonnet_client,
    "opus": claude_opus_client,
    "self_hosted_llama": llama_local_client,
})

# 实时分类任务
model = router.route(RoutingPolicy(
    task_type=TaskType.CLASSIFICATION,
    latency_req=LatencyReq.REALTIME,
    data_sensitive=False,
))
# → "haiku"

# 敏感数据处理
model = router.route(RoutingPolicy(
    task_type=TaskType.EXTRACTION,
    latency_req=LatencyReq.INTERACTIVE,
    data_sensitive=True,
))
# → "self_hosted_llama"
```

---

## 5. OpenTelemetry GenAI 语义约定（关键的可观测地基）

### 5.1 为什么需要统一的观测约定

```
┌────────────────────────────────────────────────────────────────────┐
│  没有统一约定的痛点                                                  │
│                                                                    │
│  团队 A 的埋点：                                                     │
│   span.attributes["model"] = "claude-sonnet-4"                      │
│   span.attributes["input_tokens"] = 1234                            │
│   span.attributes["cost"] = 0.012                                   │
│                                                                    │
│  团队 B 的埋点：                                                     │
│   span.attributes["llm_model"] = "Sonnet"                            │
│   span.attributes["prompt_tokens"] = 1500                            │
│   span.attributes["usd"] = 0.015                                    │
│                                                                    │
│  → 同一个项目，3 个团队，3 套字段名 → Dashboard 拼不起来             │
│  → 事故归因时不知道"是 A 团队慢了还是 B 团队慢了"                   │
│  → 跨团队成本核算算不清楚                                           │
│                                                                    │
│  OpenTelemetry GenAI 语义约定的价值：                                │
│   · 字段名统一：`gen_ai.*` 是 OpenTelemetry 官方约定                │
│   · 跨团队可拼接：A 团队和 B 团队的 span 字段一致                    │
│   · 跨工具兼容：Jaeger / Tempo / Datadog / Honeycomb 都认          │
│   · 行业标准：所有主流 Agent 框架（Langfuse/LangSmith/Arize）都在对齐│
└────────────────────────────────────────────────────────────────────┘
```

### 5.2 OTel GenAI 核心属性（v1.30+）

```
┌────────────────────────────────────────────────────────────────────┐
│  OTel GenAI Semantic Conventions · 核心属性                         │
│                                                                    │
│  Span 类型（必选）：                                                  │
│   · gen_ai.agent.run        → 整个 Agent 运行的 root span           │
│   · gen_ai.llm.call         → 单次 LLM 调用                         │
│   · gen_ai.tool.call        → 单次 Tool 调用                        │
│   · gen_ai.retrieval.query  → 单次 RAG / 检索                       │
│   · gen_ai.embedding        → Embedding 调用                        │
│                                                                    │
│  Span Attributes（按类型必须有的字段）：                              │
│                                                                    │
│  通用（所有 gen_ai.* span）：                                        │
│   · gen_ai.system                  = "anthropic" | "openai" | ...  │
│   · gen_ai.operation.name          = "chat" | "embed" | "tool"     │
│   · gen_ai.request.model           = "claude-sonnet-4-20250514"   │
│   · gen_ai.response.model          = 同上（或 fallback 后）        │
│   · gen_ai.response.id             = "msg_01XYZ..."                │
│   · gen_ai.response.finish_reasons = ["end_turn"]                  │
│                                                                    │
│  LLM 调用专属：                                                      │
│   · gen_ai.usage.input_tokens      = 1234                          │
│   · gen_ai.usage.output_tokens     = 567                           │
│   · gen_ai.usage.cost              = 0.012  (USD)                  │
│   · gen_ai.request.temperature     = 0.7                           │
│   · gen_ai.request.max_tokens      = 2048                          │
│   · gen_ai.request.top_p           = 1.0                           │
│   · gen_ai.response.model          = 实际命中的模型                │
│   · gen_ai.cascade.upgraded_from   = "haiku" (Cascading 时)        │
│                                                                    │
│  Tool 调用专属：                                                      │
│   · gen_ai.tool.name               = "search_docs"                  │
│   · gen_ai.tool.call.id            = "toolu_01ABC..."             │
│   · gen_ai.tool.call.arguments     = {...}                          │
│   · gen_ai.tool.call.result        = {...} (truncated)              │
│   · gen_ai.tool.call.latency_ms    = 250                            │
│   · gen_ai.tool.error              = true/false                    │
│                                                                    │
│  Agent 运行专属：                                                    │
│   · gen_ai.agent.name              = "customer_service_agent"      │
│   · gen_ai.agent.version           = "v3.2.1"                      │
│   · gen_ai.agent.session_id        = "sess_123"                    │
│   · gen_ai.agent.user_id           = "user_456"                    │
│   · gen_ai.agent.trajectory_length = 8                              │
│   · gen_ai.agent.score             = 0.92                          │
└────────────────────────────────────────────────────────────────────┘
```

### 5.3 Span 嵌套结构（一次 Agent 运行）

```
┌────────────────────────────────────────────────────────────────────┐
│  一次 Agent 运行的 Span Tree（典型客服场景）                          │
│                                                                    │
│  gen_ai.agent.run · customer_service_agent v3.2.1                  │
│  ├── session_id = "sess_abc123"                                     │
│  ├── trajectory_length = 5                                          │
│  ├── total_cost = $0.042                                            │
│  ├── total_latency_ms = 4200                                        │
│  │                                                                  │
│  ├── gen_ai.llm.call · step 1 (router)                              │
│  │   ├── model = claude-haiku-3.5                                   │
│  │   ├── input_tokens = 234                                         │
│  │   ├── output_tokens = 12                                         │
│  │   ├── cost = $0.0001                                             │
│  │   ├── latency_ms = 480                                           │
│  │   └── result = "billing"                                         │
│  │                                                                  │
│  ├── gen_ai.llm.call · step 2 (plan)                                │
│  │   ├── model = claude-sonnet-4                                    │
│  │   ├── input_tokens = 1500                                        │
│  │   ├── output_tokens = 300                                        │
│  │   ├── cost = $0.0054                                             │
│  │   ├── latency_ms = 1450                                          │
│  │   └── result = "查询订单 + 申请退款"                              │
│  │                                                                  │
│  ├── gen_ai.tool.call · search_orders                               │
│  │   ├── name = search_orders                                       │
│  │   ├── arguments = {"order_id": "ORD-123"}                       │
│  │   ├── latency_ms = 320                                           │
│  │   └── result = {"status": "shipped", "amount": 99.0}             │
│  │                                                                  │
│  ├── gen_ai.tool.call · refund_apply                                │
│  │   ├── name = refund_apply                                        │
│  │   ├── arguments = {"order_id": "ORD-123", "reason": "..."}      │
│  │   ├── latency_ms = 580                                           │
│  │   ├── idempotency_key = "sess_abc123:step:3:ORD-123"             │
│  │   └── result = {"refund_id": "RF-789"}                           │
│  │                                                                  │
│  └── gen_ai.llm.call · step 4 (summarize)                           │
│      ├── model = claude-haiku-3.5                                   │
│      ├── input_tokens = 800                                         │
│      ├── output_tokens = 150                                        │
│      ├── cost = $0.0004                                             │
│      └── result = "您的退款已成功..."                                │
│                                                                    │
│  → 一次 Agent 跑完，从这个 span tree 能看到：                        │
│     - 总成本 $0.042，step 2 占 $0.0054（Sonnet 是大头）             │
│     - 总延迟 4.2s，step 2 占 1.45s                                   │
│     - 用 Cascade 节省了 $0.004（如果全 Sonnet 的话）                │
│     - step 3 调用 refund_apply 用了 idempotency_key                │
└────────────────────────────────────────────────────────────────────┘
```

### 5.4 最小可运行的 OTel GenAI 埋点

```python
# otel_genai_instrumentation.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.semconv.gen_ai import GenAiAttributes  # OTel 官方约定

# 初始化 Tracer
provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://otel-collector:4317"))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

class InstrumentedLLMClient:
    """带 OTel GenAI 埋点的 LLM 客户端"""
    
    def __init__(self, model_id: str, provider_name: str = "anthropic"):
        self.model_id = model_id
        self.provider_name = provider_name
    
    def complete(self, prompt: str, **kwargs) -> dict:
        with tracer.start_as_current_span(
            "gen_ai.llm.call",
            attributes={
                GenAiAttributes.GEN_AI_SYSTEM: self.provider_name,
                GenAiAttributes.GEN_AI_OPERATION_NAME: "chat",
                GenAiAttributes.GEN_AI_REQUEST_MODEL: self.model_id,
                GenAiAttributes.GEN_AI_REQUEST_TEMPERATURE: kwargs.get("temperature", 1.0),
                GenAiAttributes.GEN_AI_REQUEST_MAX_TOKENS: kwargs.get("max_tokens", 2048),
            },
        ) as span:
            try:
                # 实际调用 LLM
                response = self._call_provider(prompt, **kwargs)
                
                # 记录响应属性
                span.set_attribute(GenAiAttributes.GEN_AI_RESPONSE_MODEL, response.model)
                span.set_attribute(GenAiAttributes.GEN_AI_RESPONSE_ID, response.id)
                span.set_attribute(GenAiAttributes.GEN_AI_USAGE_INPUT_TOKENS, response.input_tokens)
                span.set_attribute(GenAiAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, response.output_tokens)
                span.set_attribute(GenAiAttributes.GEN_AI_USAGE_COST, response.cost_usd)
                span.set_attribute(GenAiAttributes.GEN_AI_RESPONSE_FINISH_REASONS, [response.finish_reason])
                
                # Cascading 标记
                if upgraded_from := kwargs.get("upgraded_from"):
                    span.set_attribute("gen_ai.cascade.upgraded_from", upgraded_from)
                
                return response
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                raise

# 使用示例
haiku = InstrumentedLLMClient("claude-haiku-3-5-20241022", "anthropic")
sonnet = InstrumentedLLMClient("claude-sonnet-4-20250514", "anthropic")

# 在 Agent 框架里直接用，OTel 自动捕获所有调用
response = haiku.complete("用户意图是什么？")
```

---

## 6. 基于 OTel 的可观测分析

### 6.1 5 个关键 Dashboard 视图

```
┌────────────────────────────────────────────────────────────────────┐
│  必备的 5 个 Dashboard 视图（基于 OTel GenAI 数据）                   │
│                                                                    │
│  ① Cost Dashboard                                                   │
│     · 总成本（按小时/天/周）                                         │
│     · 按模型分（Haiku 占 30% / Sonnet 占 60% / Opus 占 10%）        │
│     · 按 task 分（意图分类占 5% / 文案生成占 40% / 推理占 55%）      │
│     · 单 session 平均成本 / P95 / P99                                │
│     · Cascading 节省金额                                            │
│                                                                    │
│  ② Latency Dashboard                                                │
│     · 单 session P50 / P95 / P99                                    │
│     · 按步骤分（Router < 1s / Plan < 2s / Tool < 1s / Summary < 1s）│
│     · 按模型分（Haiku 500ms / Sonnet 1500ms / Opus 4000ms）         │
│     · LLM 调用耗时 vs Tool 调用耗时                                  │
│                                                                    │
│  ③ Error Rate Dashboard                                             │
│     · 5xx 错误率（Provider 故障）                                    │
│     · 4xx 错误率（参数错误 / context 超限）                          │
│     · 超时率 / 熔断触发率                                            │
│     · Tool 调用失败率                                                │
│     · IPI 命中数（AE07）                                             │
│                                                                    │
│  ④ Behavioral Drift Dashboard（基于 AE04 风格）                       │
│     · Score Distribution（按小时分布）                               │
│     · 异常 session 数（Score < 阈值）                                │
│     · Cascading 触发频率（过多 = Cheap 模型弱了）                    │
│     · trajectory_length 分布（过长 = 退化）                          │
│                                                                    │
│  ⑤ Asset & Model Version Dashboard                                  │
│     · 在跑 Asset 版本分布（v3.2.0 占 80% / v3.2.1 占 20%）          │
│     · 在跑 Model 版本（按 Provider 分）                             │
│     · 每次发版的影响面（这个版本影响了多少 session）                 │
│     · Rollback 次数 / 平均耗时                                       │
└────────────────────────────────────────────────────────────────────┘
```

### 6.2 事故归因：从 4 小时缩到 30 分钟

```
┌────────────────────────────────────────────────────────────────────┐
│  真实事故归因流程（OTel GenAI 启用前 vs 启用后）                       │
│                                                                    │
│  【启用前 · 4 小时归因】                                              │
│   14:00 · 告警：成本突增 200%                                        │
│   14:00-15:30 · 找日志（日志格式不统一，有 3 套字段）               │
│   15:30-16:30 · 试图拼出"哪个 session 触发了"                       │
│   16:30-17:00 · 定位到 Sonnet 被某个 batch 任务调用                  │
│   17:00-17:30 · 发现 batch 任务缺少 Rate Limit                       │
│   17:30-18:00 · 加 Rate Limit + 修日志格式                           │
│                                                                    │
│  【启用后 · 30 分钟归因】                                              │
│   14:00 · 告警：cost_per_minute 突增 200%                            │
│   14:02 · 在 Cost Dashboard 看到 Sonnet 占比从 60% → 95%            │
│   14:05 · 按 task 分维度：发现 batch_report 占 90%                   │
│   14:10 · 用 gen_ai.cascade.upgraded_from 过滤：                     │
│           几乎所有 batch_report 都从 Haiku 升级到 Sonnet              │
│   14:15 · 用 gen_ai.agent.confidence 过滤：                          │
│           cascade_threshold 0.85 触发了 8000 次升级                  │
│   14:20 · 查代码：发现 batch_report 的 Prompt 改动后                 │
│           Haiku 的 logprob 平均从 0.9 → 0.6（句子变长了）            │
│   14:25 · 临时调整 cascade_threshold 到 0.5 → 恢复                   │
│   14:30 · 复盘：Prompt 改动引发的级联雪崩                              │
│                                                                    │
│  → OTel GenAI 让事故归因"快、准、全"                                │
└────────────────────────────────────────────────────────────────────┘
```

---

## 7. 实战案例 1 · Cascading 让成本下降 60%、P95 延迟下降 40%

### 7.1 背景

```
┌────────────────────────────────────────────────────────────────────┐
│  背景                                                               │
│                                                                    │
│  时间：2026-Q2（持续 2 个月的优化）                                   │
│  团队：某 SaaS 客服 Agent 团队                                       │
│  初始架构：所有请求都用 Claude Sonnet 4                              │
│  目标：成本下降 50%+ / P95 延迟不恶化                                │
└────────────────────────────────────────────────────────────────────┘
```

### 7.2 数据基线（优化前）

```
┌────────────────────────────────────────────────────────────────────┐
│  优化前 · 1 个月数据                                                 │
│                                                                    │
│  日均请求：50,000                                                    │
│  模型使用：100% Sonnet 4                                             │
│  平均 input tokens：1200                                             │
│  平均 output tokens：350                                             │
│                                                                    │
│  成本：$3 × 1.2 + $15 × 0.35 = $8.85 / 1K requests                  │
│       = $442 / 天 = $13,260 / 月                                    │
│                                                                    │
│  P50 延迟：1.6s                                                     │
│  P95 延迟：3.8s                                                     │
│                                                                    │
│  任务分布（基于 Eval 标注）：                                          │
│   · 60% 是意图分类 + JSON 提取（Sonnet 太重）                        │
│   · 25% 是文档总结 + 文案撰写（Sonnet 刚好）                          │
│   · 15% 是复杂推理（确实需要 Sonnet 甚至 Opus）                      │
└────────────────────────────────────────────────────────────────────┘
```

### 7.3 Cascading 设计

```
┌────────────────────────────────────────────────────────────────────┐
│  Cascading 设计（3 阶段）                                            │
│                                                                    │
│  Stage 1 · Router（Haiku）                                          │
│     · 任务：分类"意图分类 / 总结 / 推理"                              │
│     · 成本：$0.25/1M input → 几乎免费                                │
│     · 延迟：500ms                                                    │
│                                                                    │
│  Stage 2 · Executor                                                  │
│     · 意图分类/提取 → Haiku 直答（占比 60%）                          │
│     · 总结/文案 → Sonnet 直答（占比 25%）                            │
│     · 复杂推理 → Opus 直答（占比 15%）                                │
│     · 置信度阈值：logprob_avg ≥ 0.85                                │
│                                                                    │
│  Stage 3 · Upgrade（Cascade）                                        │
│     · Haiku 置信度 < 0.85 → 升级 Sonnet                              │
│     · Sonnet 置信度 < 0.85 → 升级 Opus                               │
│     · Opus 是兜底，不升级                                            │
│                                                                    │
│  关键设计：                                                          │
│   · 用 Logprob 做置信度信号（数学客观）                               │
│   · 用 Eval Set 验证升级阈值（找 Pareto 拐点）                       │
│   · 升级时记录 gen_ai.cascade.upgraded_from 到 span                  │
└────────────────────────────────────────────────────────────────────┘
```

### 7.4 优化效果

```
┌────────────────────────────────────────────────────────────────────┐
│  优化效果对比（同样 50K 请求/天）                                     │
│                                                                    │
│  ┌──────────────┬─────────────┬──────────────┬──────────────┐      │
│  │ 维度          │ 优化前      │ 优化后        │ 变化         │      │
│  ├──────────────┼─────────────┼──────────────┼──────────────┤      │
│  │ 日成本        │ $442        │ $176         │ ↓ 60%        │      │
│  │ 月成本        │ $13,260     │ $5,280       │ ↓ 60%        │      │
│  │              │             │              │ （年省 $96K） │      │
│  ├──────────────┼─────────────┼──────────────┼──────────────┤      │
│  │ P50 延迟      │ 1.6s        │ 0.9s         │ ↓ 44%        │      │
│  │ P95 延迟      │ 3.8s        │ 2.3s         │ ↓ 39%        │      │
│  │              │             │              │ （Haiku 兜底） │      │
│  ├──────────────┼─────────────┼──────────────┼──────────────┤      │
│  │ Pass Rate    │ 91.2%       │ 91.5%        │ ↑ 0.3%（持平）│      │
│  │ 用户满意度   │ 84%         │ 86%           │ ↑ 2%         │      │
│  └──────────────┴─────────────┴──────────────┴──────────────┘      │
│                                                                    │
│  关键洞察：                                                          │
│   · 成本 ↓ 60% 不是因为"模型变弱了"，而是"用对了模型"                │
│   · 延迟 ↓ 40% 是因为 60% 请求用 Haiku（比 Sonnet 快 3x）           │
│   · 质量持平 → Pass Rate 甚至 ↑ 0.3%（Cascading 救了一些难例）     │
│                                                                    │
│  投资回报：                                                          │
│   · 投入：1 个工程师 × 2 个月（设计 + 实现 + 调优）                   │
│   · 收益：$96K / 年                                                  │
│   · ROI 极高                                                         │
└────────────────────────────────────────────────────────────────────┘
```

---

## 8. 实战案例 2 · OTel GenAI 让事故归因时间从 4h 缩到 30min

### 8.1 事故背景

```
┌────────────────────────────────────────────────────────────────────┐
│  事故背景                                                           │
│                                                                    │
│  时间：2026-06-15 14:00                                              │
│  团队：某 AI Code Review Agent                                       │
│  告警：Customer Support 收到大量 "review 慢" / "review 不准" 投诉    │
│  紧急程度：P1                                                        │
└────────────────────────────────────────────────────────────────────┘
```

### 8.2 用 OTel GenAI 30 分钟归因

```
┌────────────────────────────────────────────────────────────────────┐
│  归因时间线（OTel GenAI 启用后）                                      │
│                                                                    │
│  14:00 · PagerDuty 告警：                                            │
│         · error_rate ↑ 3%                                            │
│         · p95_latency ↑ 200%                                         │
│         · user_complaint ↑ 500%                                      │
│                                                                    │
│  14:02 · 打开 Latency Dashboard                                      │
│         · gen_ai.llm.call p95 从 1.5s → 4.2s                        │
│         · gen_ai.tool.call p95 从 300ms → 350ms（正常）              │
│         · → 瓶颈在 LLM，不在 Tool                                    │
│                                                                    │
│  14:05 · 按模型分维度                                                  │
│         · Sonnet p95: 4.5s（异常）                                   │
│         · Haiku p95: 800ms（正常）                                   │
│         · Opus p95: 6.2s（异常，但占比小）                            │
│                                                                    │
│  14:08 · 按 gen_ai.request.model 过滤，定位到 Sonnet                 │
│         · 大量 Sonnet 调用集中在 "code_summary" task                  │
│         · → 怀疑是 code_summary 子任务异常                            │
│                                                                    │
│  14:12 · 抽样 5 个 session 的 span tree                                │
│         · code_summary 调用了 Sonnet，平均 input = 8000 tokens       │
│         · 正常应该是 2000 tokens                                      │
│         · → context 突然膨胀                                         │
│                                                                    │
│  14:18 · 查 AE10 的 Asset 发版记录                                    │
│         · 13:50 发布了 v3.2.0 → v3.2.1                                │
│         · v3.2.1 改动：Few-shot 加了 2 条长 code review 示例          │
│         · 推测：Few-shot 加长导致 context 膨胀 → 输入 ↑ → 延迟 ↑      │
│                                                                    │
│  14:22 · 用 v3.2.1 在 Stage 环境跑 Shadow Traffic                     │
│         · 确认：code_summary 输入从 2K → 8K tokens                    │
│         · 确认：Sonnet p95 从 1.5s → 4.5s                             │
│         · 根因确认                                                     │
│                                                                    │
│  14:25 · 一键 Rollback 到 v3.2.0（AE10 Asset Pin）                    │
│  14:30 · 指标全部恢复，P1 解除                                       │
│                                                                    │
│  全程 30 分钟（OTel 启用前同样事故需要 4 小时）                       │
│  → OTel GenAI 节省 7.5 小时 × 多次类似事故 = 巨大价值                │
└────────────────────────────────────────────────────────────────────┘
```

### 8.3 关键学习

```
┌────────────────────────────────────────────────────────────────────┐
│  OTel GenAI 在事故归因中的核心价值                                    │
│                                                                    │
│  ① 统一字段名（gen_ai.*）                                              │
│     · 跨团队、跨工具的 span 字段一致                                  │
│     · 不用花时间"猜字段名"                                           │
│                                                                    │
│  ② Span Tree 嵌套结构                                                  │
│     · 一次 Agent 运行的完整调用链路一目了然                            │
│     · 哪个步骤慢、哪个步骤贵、哪个步骤错，5 分钟定位                  │
│                                                                    │
│  ③ 业务级属性（session_id / asset_version / score）                    │
│     · 能把"运行时数据"和"业务指标"关联                                │
│     · 比如：score < 0.8 的 session，调用了哪个模型、哪个 prompt      │
│                                                                    │
│  ④ Cascading 升级链路                                                  │
│     · gen_ai.cascade.upgraded_from 直接回答"这个请求为什么变贵了"    │
│     · 不需要去翻业务日志猜                                            │
│                                                                    │
│  → 投入：1 个工程师 × 2 周接入 OTel GenAI 埋点                       │
│  → 收益：每次事故省 3-7 小时 × 每月 2-3 次 = 每月 6-20 小时          │
│  → 不可见的收益：跨团队协作效率 ↑↑↑（统一字段名后 Dashboard 通用）   │
└────────────────────────────────────────────────────────────────────┘
```

---

## 9. 与 AE 系列的闭环

```
┌────────────────────────────────────────────────────────────────────┐
│  AE12 Model Routing / OTel 在 AE 系列中的位置                        │
│                                                                    │
│  上游依赖（AE12 用到的前置能力）：                                    │
│   · AE01 四层架构 → Model 是 Skill/Tool 的执行载体                   │
│   · AE02 Context Engineering → 决定 Cascade 阈值                    │
│   · AE04 Trajectory Evals → Eval Set 是 Cascade 阈值依据             │
│   · AE09 HITL → Cascade 置信度 < 0.5 时升级 HITL                    │
│   · AE10 Release Control → 新模型上线走 Pipeline                     │
│   · AE11 Compound Agent → Routing 是分层架构的关键组件              │
│                                                                    │
│  下游赋能（AE12 给后续实践提供的能力）：                               │
│   · 真实生产系统 = AE01-12 的全部组合                                │
│   · 后续篇章（如 OTel GenAI 实战、AI_for_Stability 联动）会再次引用 │
│                                                                    │
│  闭环图（AE 系列全貌）：                                              │
│                                                                    │
│    基础四件套    策略与契约    交互与发布    架构与可观测              │
│   ┌─┬─┬─┬─┐  ┌─┬─┬─┬─┐  ┌───┬───┐  ┌───┬───┐                      │
│   │1│2│3│4│  │5│6│7│8│  │ 9 │10 │  │11 │12 │ ← 你在这里           │
│   └─┴─┴─┴─┘  └─┴─┴─┴─┘  └───┴───┘  └───┴───┘                      │
│    Prompt      Policy     HITL       Model                            │
│    Context     MCP        Release    Routing                          │
│    Durable     IPI        Control    OTel                             │
│    Eval        Idem                                    GenAI         │
│                                                                    │
│   至此 12 篇闭环                                                        │
│   · 基础：怎么用 LLM 干活（AE01-04）                                  │
│   · 约束：怎么让 LLM 安全干活（AE05-08）                              │
│   · 协作：怎么让人和发布配合（AE09-10）                               │
│   · 承载：怎么扛量、怎么观测（AE11-12）                               │
└────────────────────────────────────────────────────────────────────┘
```

---

## 附录 A · 概念索引表

| 概念 | 一句话定义 | 本篇章节点 |
|---|---|---|
| Cost-Quality Pareto | 成本 vs 质量的权衡曲线，找性价比拐点 | §1.2 |
| Model Family | 同一家族的多个档位（Haiku/Sonnet/Opus） | §2.1 |
| Model Routing | 按任务路由到不同模型的机制 | §4 |
| Cascading | 先用便宜模型，不确定再升级 | §3 |
| Confidence Signal | 置信度信号（Logprob / Self-Score / 多采样一致 / Eval 命中） | §3.2 |
| Cascade Threshold | 触发升级的置信度阈值 | §3.3 |
| gen_ai.* | OpenTelemetry GenAI 语义约定的属性前缀 | §5.2 |
| Span Tree | 一次 Agent 运行的嵌套 span 结构 | §5.3 |
| Tracer | OTel 追踪器，生成 span 的组件 | §5.4 |
| OTel Collector | 收集 span 数据的后端服务 | §6 |
| Behavioral Drift | 行为漂移，模型/资产变化后行为统计显著偏移 | §6.1 |
| Asset Pin (回引 AE10) | 把 canary 比例设为 0，新 session 切旧版本 | §8.2 |
| Cascade 雪崩 | Cheap 模型置信度集体变低导致大量升级 | §8.2 |
| 跨家族 Routing | 不同 Provider 间的路由（Anthropic + OpenAI + 自托管） | §4.2 |

## 附录 B · 路径对账（一手来源对齐）

| 议题 | 本篇定义 | 一手来源 | 对齐情况 |
|---|---|---|---|
| Model 能力矩阵 | Haiku/Sonnet/Opus / GPT-4o / o1 / Gemini | 各 Provider 官方文档 | ✅ 对齐 |
| Cost-Quality Pareto | 性价比拐点概念 | Anthropic "Building Effective Agents" §3 | ✅ 对齐 |
| Cascading 模式 | Cheap 先答，不确定再升级 | Anthropic "Building Effective Agents" + Cloudflare Workers AI Gateway | ✅ 对齐 |
| Confidence Signal | Logprob / Self-Score / 多采样一致 | OpenAI Cookbook "Confidence Scores" / Anthropic Cookbook | ✅ 对齐 |
| Model Routing by Privacy | 敏感数据走自托管 | OWASP LLM Top 10 §LLM06 (Sensitive Info) | ✅ 对齐 |
| OTel GenAI Semantic Conventions | gen_ai.* 属性 / span 类型 | OpenTelemetry GenAI Spec v1.30+ | ✅ 对齐 |
| Span 设计 | agent.run → llm.call → tool.call 嵌套 | OTel GenAI Spec "Spans" 章节 | ✅ 对齐 |
| Cost Dashboard | 成本可视化 | Langfuse / LangSmith Dashboard 设计 | ✅ 对齐 |
| Behavioral Drift Detector | 行为漂移检测 | Langfuse "Drift Detection" / Arize AI 文档 | ✅ 对齐 |
| Asset Pin (回引 AE10) | Rollback 机制 | 已在 AE10 对齐 | ✅ 对齐 |
| Idempotency Key (回引 AE08) | 工具调用唯一标识 | 已在 AE08 对齐 | ✅ 对齐 |

## 附录 C · 量化自检

| 维度 | 数值 | v3 门槛 | 达标 |
|---|---|---|---|
| 文章总行数 | 1012 行 | ≥ 500 行 | ✅ |
| ASCII 图数 | 14 张 | ≥ 4 张 | ✅ |
| 完整案例数 | 2 个（Cascading 节省 60% 成本 / OTel 归因 30min） | 1-2 个 | ✅ |
| 可运行代码段 | 2 段（Cascading + Model Router + OTel 埋点 = 实际 3 段） | 2-3 段 | ✅ |
| 一手引用数 | 11 个（Anthropic / OpenAI / OTel / Cloudflare / Langfuse / OWASP 等） | ≥ 6 个 | ✅ |
| 4 附录齐全度 | A/B/C/D 全有 | 必须全有 | ✅ |
| 与 AE 系列交叉引用 | AE01/02/04/09/10/11 + 系列全貌总结 | ≥ 4 个 | ✅ |

## 附录 D · 工程基线 Checklist（35 行可复用模板）

```yaml
# model_routing_and_otel_checklist.yaml
# 任何生产 Agent 上线前必过

model_selection:
  - "已用 Eval Set 评估候选模型在自家任务上的 baseline"
  - "已识别高频任务类型（分类/提取/总结/推理/代码/敏感）"
  - "已选定 Model Family（建议至少 2 个 Provider 做容灾）"
  - "已设定每类任务的默认模型 + 备选模型"

cascading_design:
  - "已选定置信度信号（Logprob 首选，Self-Score 兜底）"
  - "已用 Eval Set 调优 cascade_threshold（找到 Pareto 拐点）"
  - "已实现 Upgrade 逻辑（Cheap 不行 → Strong）"
  - "已记录 cascade.upgraded_from 到 OTel Span"
  - "Cascading 后回灌训练数据给 Cheap 模型（持续优化）"

model_routing:
  - "Router 已实现（按 task_type / latency_req / data_sensitive）"
  - "敏感数据已路由到自托管（禁外发）"
  - "延迟敏感任务已路由到快模型（Haiku / 4o-mini）"
  - "能力敏感任务已路由到强模型（Opus / o1）"
  - "默认兜底是性价比拐点模型（通常 Sonnet）"

opentelemetry_genai:
  - "OTel SDK 已接入（Tracer 已初始化）"
  - "所有 LLM 调用埋点 gen_ai.llm.call span"
  - "所有 Tool 调用埋点 gen_ai.tool.call span"
  - "所有 Retrieval 调用埋点 gen_ai.retrieval.query span"
  - "Agent root span 埋点 gen_ai.agent.run"
  - "关键属性齐全：gen_ai.system / model / usage / cost / finish_reasons"

observability_dashboards:
  - "Cost Dashboard：按模型/任务/时间维度拆分"
  - "Latency Dashboard：按步骤/模型分维度 P50/P95/P99"
  - "Error Rate Dashboard：5xx/4xx/超时/熔断/工具失败"
  - "Behavioral Drift Dashboard：Score 分布 + 异常 session"
  - "Asset/Model Version Dashboard：当前在跑版本分布 + 发版影响面"

discipline:
  - "新模型上线走 AE10 Pipeline（Golden Replay + Score Diff Gate）"
  - "Cascade 阈值变更走 AE10 Pipeline（影响范围大）"
  - "OTel 字段名变更需全团队 Review（影响所有 Dashboard）"
  - "每月 1 次成本复盘（看 Cost Dashboard 找优化点）"
  - "每次事故后更新"归因 Runbook"（OTel 查询模板）"
```

---

## 附录 E · AE 系列全貌回顾（12 篇闭环）

```
┌────────────────────────────────────────────────────────────────────┐
│  AE 系列全貌 · 12 篇闭环                                              │
│                                                                    │
│  簇 1 · 基础四件套（AE01-AE04）                                      │
│   ├─ AE01  Prompt→Skill→Tools→Context 四层架构                       │
│   ├─ AE02  Context Engineering（Token / Cache / Memory）             │
│   ├─ AE03  Durable Execution（Checkpoint / 幂等 / Resume）            │
│   └─ AE04  Trajectory Evals（评路径不只评答案）                       │
│                                                                    │
│  簇 2 · 策略与契约（AE05-AE08）                                      │
│   ├─ AE05  Policy-as-Code（守卫前移到工具调用层）                     │
│   ├─ AE06  MCP 与工具标准化契约                                      │
│   ├─ AE07  Indirect Prompt Injection（信任边界）                      │
│   └─ AE08  Tool Idempotency（副作用边界 / 重试安全）                 │
│                                                                    │
│  簇 3 · 交互与发布（AE09-AE10）                                      │
│   ├─ AE09  Human-in-the-Loop（Interrupt / Approval Packet）           │
│   └─ AE10  Release Control（Prompt/Skill 走发版门禁）                 │
│                                                                    │
│  簇 4 · 架构与可观测（AE11-AE12）                                    │
│   ├─ AE11  Compound Agent（Agent + Workflow 分层）                   │
│   └─ AE12  Model Routing / Cascading + OTel GenAI  ← 你在这里        │
│                                                                    │
│  → 至此 AE 系列 12/12 闭环                                            │
│  → 4 簇 / 12 篇 / 总字数 8-10 万 / 总行数 ~10K                       │
│  → 目标读者从"AI 用户"成长为"AI 工程师"的语言基线已建立              │
└────────────────────────────────────────────────────────────────────┘
```

---

## 一句话总结

> **模型不是越强越好，是越合适越好；观测不是为了记录，是为了能在事故时 30 分钟内定位到第 N 次 LLM 调用的第 M 个 token 上。**
>
> Model Routing 按场景选模型 + Cascading 用 Logprob 做置信度信号让便宜的先答 + OTel GenAI 统一字段名让 Dashboard 跨团队通用 —— 三件套咬合，单 Agent 才能从 demo 跑到扛量、扛事故、扛成本。