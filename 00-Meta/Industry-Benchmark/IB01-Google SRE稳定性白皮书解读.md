# IB01 · Google SRE 稳定性白皮书解读：SLO / Error Budget / Toil 三件套

> **基线**：参考 Google SRE Book（2016）+ SRE Workbook（2018）+ Google SRE 后续演讲（2020-2025）
>
> **目标读者**：稳定性架构师 / SRE Lead / 平台架构师
>
> **完成时间**：2026-07-24（v1.0 首版）

<!-- AUTHOR_ONLY:START -->

## 本篇定位

- 行业基线系列首篇（IB01）—— 把 Google SRE 的方法论本土化到 Android 稳定性治理
- 强依赖：[S10-02-SLI与SLO设计](../../02-Symptom/S10-Measure/02-SLI与SLO设计：从指标到门禁.md) / [A05-4 步闭环](../../05-Governance/APM/A05-4步闭环.md) / [A04-Stability Score](../../05-Governance/APM/A04-StabilityScore综合指数.md)
- 衔接去：[IB02-阿里/字节/腾讯对比](IB02-阿里字节腾讯稳定性对比.md)

## 校准决策日志

| 轮次 | 类别 | 决策 | 理由 |
|:-----|:-----|:-----|:-----|
| 1 | 结构 | 单篇 500+ 行（§8 破例）| SRE 3 件套 + 本土化必须展开 |
| 2 | 硬伤 | 3 件套必给具体 Android 例子 | 反例 #11 |
| 3 | 锐度 | 删"通常" | 反例 #5 |

<!-- AUTHOR_ONLY:END -->

---

# 1. SRE 三件套

> **SRE = Site Reliability Engineering = Google 在 2003 年提出的运维工程方法论**
>
> **3 大核心概念**：**SLI / SLO / Error Budget** —— 任何稳定性工程都绕不开

| 概念 | 含义 | 类比 |
|:-----|:-----|:-----|
| **SLI** | Service Level Indicator（可测量的服务质量指标）| 温度计读数 |
| **SLO** | Service Level Objective（对 SLI 的承诺值）| 36.5°C 是健康 |
| **Error Budget** | 1 - SLO 目标值的可消耗余量 | 38°C 容忍 0.5°C |

---

# 2. SLI 选型 4 大原则

## 2.1 原则 1：可测量

**坏 SLI**：`App 好用` （不可测量）
**好 SLI**：`Crash-free Session ≥ 99.95%`（可测量）

## 2.2 原则 2：用户感知

**坏 SLI**：`CPU 占用 < 80%`（用户不感知）
**好 SLI**：`首帧时间 < 2s`（用户感知）

## 2.3 原则 3：少而精

> **Google 经验**：**单个服务 ≤ 5 个 SLI**——多了失去焦点

Android 5 大 SLI（详见 [S10-02-SLI与SLO设计](../../02-Symptom/S10-Measure/02-SLI与SLO设计：从指标到门禁.md)）：
1. 启动成功率
2. Java 崩溃率
3. Native 崩溃率
4. ANR 率
5. 后台存活率

## 2.4 原则 4：分布而非平均

**坏 SLI**：`平均响应时间`（被长尾掩盖）
**好 SLI**：`P95 / P99 响应时间`（覆盖长尾）

---

# 3. SLO 制定的 4 步法

## Step 1：测基线

```
SLO 制定第一步：测过去 30 天真实 SLI
  → 取 95% 分位 = 略高于现状
```

**例**：
- 过去 30 天 Crash-free Session 真实值
- 99.96% / 99.92% / 99.95% / 99.98% / 99.97% ...
- 取 95% 分位 ≈ 99.97%

## Step 2：定目标

```
SLO 制定第二步：取基线的 95% 分位 = 略高于现状
```

**例**：基线 99.97% → SLO 99.95%（**略宽松**于现状，避免频繁超额）

## Step 3：写入契约

```
SLO 制定第三步：写入内部契约（对产品/对客户）
```

**内部契约**：
- Stability Score ≥ 90（4 个季度）
- Crash-free Session ≥ 99.95%
- ANR-free Session ≥ 99.9%

**客户契约**（如果做 SaaS）：
- 99.9% 在线率 = 每月 ≤ 43 分钟 downtime

## Step 4：定期 review

```
SLO 制定第四步：每季度 review 一次
```

---

# 4. Error Budget 实战

## 4.1 概念

**Error Budget = 1 - SLO** 的可消耗余量

**例**：
- SLO = 99.9% → Error Budget = 0.1%
- 1 个月 30 天 = 43200 分钟
- Error Budget = 43.2 分钟 downtime

## 4.2 Error Budget 用完怎么办？

### 4 大红线（绝对不能做）

| # | 行为 | 后果 |
|:-:|:-----|:-----|
| 1 | **改 SLO**（把 99.9% 改成 99%）| 失去用户信任 |
| 2 | **改 SLI 计算口径**（分子分母凑数）| 自欺欺人 |
| 3 | **删除历史数据**（假装没发生）| 故障复现 |
| 4 | **继续发版**（无视 Error Budget）| 雪上加霜 |

### 4 件必做

| # | 行为 | 时限 |
|:-:|:-----|:-----|
| 1 | **冻结发版**（停止所有 feature 变更）| 立即 |
| 2 | **启动专项治理**（拉 PM + TL + oncall）| 24h |
| 3 | **输出 postmortem**（5 Whys + Action Items）| 24h |
| 4 | **门禁更新**（加新检查项）| 1 周 |

## 4.3 Error Budget 治理 SOP

```yaml
# 月度 Error Budget 监控
budget:
  slo: 99.9%
  total_minutes: 43200
  consumed_minutes: 35
  consumption_rate: 0.08%
  status: green  # < 50% = 绿
  
# 状态机
states:
  - green: < 50%    # 正常
  - yellow: 50-80%  # 告警
  - red: 80-100%    # 升级
  - exhausted: > 100%  # 冻结发版
```

---

# 5. Toil 自动化

## 5.1 什么是 Toil？

> **Toil = 重复性、手动、无长期价值的工作**

**Toil 例子**：
- 每天手动重启服务
- 手动跑 lint
- 手动看 logcat
- 手动发版

## 5.2 Toil 的危害

| 问题 | 数据 |
|:-----|:-----|
| Toil 占比 | Google SRE 团队 Toil ≤ 50% 时间（超过就出问题）|
| 工程师倦怠 | 高 Toil = 倦怠 = 离职 |
| 错误率 | 手动操作错误率 1-5% |
| 扩展性 | 手动不可扩展 |

## 5.3 Toil 自动化优先级

```
P0（必自动化）：
  - oncall 应急 SOP（OC01 提到的工具栈）
  - 4 阶段门禁（[A03 6 大门禁](../../05-Governance/APM/A03-6大门禁维度.md)）
  - 自动回滚（[S10-03 §4.3](../../02-Symptom/S10-Measure/03-发布门禁SOP.md)）

P1（应自动化）：
  - 性能基线对比
  - 告警分级
  - 看板自动出报表

P2（可自动化）：
  - 文档生成
  - 周报/月报
```

## 5.4 Toil 度量

```python
def toil_score(time_spent_on_toil):
    """
    Google 标准：Toil ≤ 50% 工程师时间
    """
    if time_spent_on_toil < 0.3:
        return "excellent"
    elif time_spent_on_toil < 0.5:
        return "good"
    elif time_spent_on_toil < 0.7:
        return "warning"
    else:
        return "burnout"
```

---

# 6. SRE 3 件套 vs Android 稳定性

| SRE 概念 | Android 对应 | 已有 |
|:---------|:------------|:-----|
| **SLI** | 5 大 SLI | [S10-02 §2](../../02-Symptom/S10-Measure/02-SLI与SLO设计：从指标到门禁.md) |
| **SLO** | SLO 阶梯 | [S10-02 §3](../../02-Symptom/S10-Measure/02-SLI与SLO设计：从指标到门禁.md) |
| **Error Budget** | 月度预算监控 | [S10-02 §4](../../02-Symptom/S10-Measure/02-SLI与SLO设计：从指标到门禁.md) |
| **4 步闭环** | 度量/决策/行动/回归 | [A05-4 步闭环](../../05-Governance/APM/A05-4步闭环.md) |
| **Stability Score** | 综合分 | [A04-Stability Score](../../05-Governance/APM/A04-StabilityScore综合指数.md) |
| **Toil 自动化** | CI/CD + 自动化测试 | [S10-03 发布门禁 SOP](../../02-Symptom/S10-Measure/03-发布门禁SOP.md) |

---

# 7. Google SRE 的 3 大经验

## 7.1 经验 1：SLO 是给"用户"定的，不是给"系统"定的

> **铁律**：**SLO 必须反映用户感知**——不能定成"CPU < 80%"（用户不感知）

| 错的 SLO | 对的 SLO |
|:---------|:---------|
| `CPU < 80%` | `首帧时间 P95 < 2s` |
| `内存峰值 < 500MB` | `OOM-free Session > 99.5%` |
| `网络重试率 < 1%` | `网络成功率 > 99.9%` |

## 7.2 经验 2：Error Budget 必触发"行动"

> **铁律**：**Error Budget 不是"看板装饰"**——用完必冻结发版

| 阶段 | 触发 | 行动 |
|:-----|:-----|:-----|
| 0-50% | - | 正常 |
| 50-80% | 告警 | 团队知晓 |
| 80-100% | 升级 | TL 介入 |
| > 100% | **冻结** | **暂停发版** |

## 7.3 经验 3：自动化优于流程

> **铁律**：**Toil 自动化比 SOP 重要**——SOP 是"懒人自动化"

| 类型 | 价值 | 优先级 |
|:-----|:-----|:------:|
| 自动化脚本 | 极高 | P0 |
| 标准化 SOP | 高 | P0 |
| 人工 review | 中 | P1 |
| 文档手册 | 低 | P2 |

---

# 8. 案例：某 App 实施 SRE 3 件套

## 8.1 起点

| 指标 | 数值 |
|:-----|:-----|
| Crash-free Session | 99.85% |
| ANR-free Session | 99.6% |
| Stability Score | 78 |
| Toil 占比 | 60% |

## 8.2 实施（3 个月）

| 月份 | 动作 |
|:-----|:-----|
| M1 | 制定 5 大 SLI + SLO 阶梯 + Error Budget |
| M2 | 4 阶段门禁自动化（CI/CD） |
| M3 | Toil 自动化（oncall 工具栈 + 看板） |

## 8.3 终态

| 指标 | 起点 | 终态 |
|:-----|:-----|:-----|
| Crash-free Session | 99.85% | 99.95% |
| ANR-free Session | 99.6% | 99.85% |
| Stability Score | 78 | 91 |
| Toil 占比 | 60% | 35% |
| MTTR | 2h | 25min |

---

# 9. 7 反例

| # | 反例 | 错误做法 | 正确做法 |
|:-:|:-----|:---------|:---------|
| 1 | **SLO 不反映用户** | "CPU < 80%" | "首帧 P95 < 2s" |
| 2 | **Error Budget 不冻结** | 用完继续发 | **必冻结** |
| 3 | **改 SLO 凑数** | 99.9% 改 99% | **绝不允许** |
| 4 | **Toil 占比 70%+** | 手动为主 | **自动化优先** |
| 5 | **SLO 不 review** | 1 年不动 | **季度 review** |
| 6 | **Toil 不度量** | 凭感觉 | **必度量** |
| 7 | **postmortem 走过场** | 不写 5 Whys | **必写** |

---

# 10. 5 条 Takeaway

1. **SRE 3 件套 = SLI + SLO + Error Budget** —— 任何稳定性工程的基础
2. **SLO 必须反映用户感知** —— 不是"CPU < 80%"，是"首帧 P95 < 2s"
3. **Error Budget 用完 = 冻结发版** —— 绝对不能改 SLO 凑数
4. **Toil 自动化优先于 SOP** —— Toil ≤ 50% 工程师时间
5. **季度 review SLO** —— 业务变了 SLO 要变

---

# 11. 附录

## A 源码索引

| 模块 | 路径 | 关键 |
|:-----|:-----|:-----|
| SLI/SLO | [S10-02-SLI与SLO设计](../../02-Symptom/S10-Measure/02-SLI与SLO设计：从指标到门禁.md) | 5 SLI |
| 4 步闭环 | [A05-4 步闭环](../../05-Governance/APM/A05-4步闭环.md) | 闭环 |
| Stability Score | [A04-Stability Score](../../05-Governance/APM/A04-StabilityScore综合指数.md) | 6 维 |
| 门禁 | [A03-6 大门禁维度](../../05-Governance/APM/A03-6大门禁维度.md) | 6 维度 |
| 行业对比 | [IB02-阿里/字节/腾讯对比](IB02-阿里字节腾讯稳定性对比.md) | 三大厂 |

## B 路径对账

无新增模块。

## C 量化自检

- 3 件套 4 大原则 ✅
- Error Budget 4 大红线 + 4 件必做 ✅
- Toil 度量 + 优先级 ✅
- 案例：78 → 91 治理全过程 ✅
- 7 反例清单 ✅
- 5 条 Takeaway ✅

## D 工程基线

AOSP 17 + 6.18 LTS / 参考 Google SRE Book + SRE Workbook

---

**作者**：Mavis · Stability Matrix Course
**最后更新**：2026-07-24（v1.0）
