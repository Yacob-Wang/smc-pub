# APM · 应用性能监控体系建设

> **状态**：🟡 占位（计划 2026-07 启动 P0 必写）
>
> **目标读者**：Android 稳定性架构师 / APM Lead / 平台架构师
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`

## 计划内容（10 篇左右）

1. APM 体系总览（指标 + 数据流 + 治理）
2. 5 大度量（MTBF / 崩溃率 / ANR 率 / 严重性 / 回归率）
3. 6 大门禁维度（崩溃 / ANR / 性能 / 兼容 / 安全 / 业务）
4. Stability Score 综合指数
5. 4 步闭环（度量 → 决策 → 行动 → 回归）
6. 数据采集层（dumpsys / Perfetto / Watchdog / dropbox）
7. 度量后端设计（Kafka + Flink + ClickHouse）
8. 告警分级（Critical / High / Medium / Low）
9. 案例 A：某电商 App 6 月治理闭环
10. 案例 B：某社交 App 春节跳过门禁（反面）

## 跨系列引用

- 上游：[02-Symptom/S10-Measure](../../02-Symptom/S10-Measure/) 度量学
- 上游：[04-Tool/Dumpsys](../../04-Tool/Dumpsys/) + [04-Tool/Perfetto](../../04-Tool/Perfetto/) 数据采集
- 上游：[04-Tool/AmCommand](../../04-Tool/AmCommand/) 32 篇 am 命令
- 配套：[05-Governance/AI-Native/03_AI_for_Stability](../AI-Native/03_AI_for_Stability/) 智能 APM

