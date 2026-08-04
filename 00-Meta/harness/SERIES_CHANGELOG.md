# 系列更新流水 · SERIES_CHANGELOG

> **协议**：正文系列新增/重写/大改/规范升级必须追加。见 `.cursor/rules/02-series-changelog.mdc`。  
> **顺序**：最新在上。

## 最新

### 2026-08-04 · web · 系列列表标题以文件名为准
- **路径**：`00-Meta/scripts/feed_cards.py` · `00-Meta/scripts/prepare_web_docs.py` · `00-Meta/scripts/test_feed_cards.py`
- **动作**：大改（构建脚本）
- **摘要**：系列总览篇名不再取正文首个 `#`（曾把 Init 壳注释当成标题）；改为文件名（支持 `7.1-` / `A02-` 前缀），index/README 仍用 H1
- **规范**：n/a
- **关联**：修复 Init 系列 Pages 列表错名

### 2026-08-03 · writing-standards · 规范升级
- **路径**：`.cursor/rules/01-writing-standards.mdc` · `PROMPT-技术系列文章写作指南.md` · `AGENTS.md`
- **动作**：规范升级（§0 硬约束转为 always-on MDC）
- **摘要**：明确写作基线 AOSP android-17.0.0_r1 + GKI android17-6.18；强制真实源码路径/对账表；废止「AOSP 14 可发布」旧 B 级口径；PROMPT 改为详规+方法论
- **规范**：MDC 为准
- **关联**：与 harness 写作入口对齐

### 2026-08-03 · harness · 基建
- **路径**：`.cursor/rules/*.mdc` · `00-Meta/harness/*` · `00-Meta/缺口一览.md` · `00-Meta/scripts/quality_audit.py`
- **动作**：新增（工程约束 + 账本）+ 缺口账本刷新 + 修审计脚本路径
- **摘要**：以 harness 方式管理写书工程；强制系列变更记账；对齐缺口与 8 卷现状
- **规范**：n/a（元工程）
- **关联**：长任务 `LT-000` done；债务 `TD-001`/`TD-002` done

---

## 历史摘要（harness 建立前 · 不完整）

以下为建立账本时的已知大批量产出，**非逐篇流水**；之后必须逐条追加。

| 约略日期 | 系列 | 说明 |
|:---|:---|:---|
| 2026-07-24 | APM A01–A10 | 卷7 第43章体系文基本齐 |
| 2026-07-24 | Oncall OC01–OC08 | 卷5 第36章剧本齐 |
| 2026-07-24 | Cases E01–E11 | 多在卷8 第47/50章 |
| 2026-07-24 | Industry-Benchmark IB01–IB04 | `00-Meta/Industry-Benchmark/` |
| 2026-07-24+ | S10 / 性能基线 03–05 | 卷6 第37章门禁/预算/行业基线 |
| 2026-07 | IO / FileSystem 系列 | v6 审计 ALL PASS（见章内 AUDIT_REPORT） |

---

## 条目模板

```markdown
### YYYY-MM-DD · <系列短名> · <动作>
- **路径**：`...`
- **动作**：新增 | 重写 | 大改 | 规范升级 | 删除/合并 | 结构
- **摘要**：
- **规范**：v6 §0 自检 □ / verify □
- **关联**：LT-xxx / TD-xxx / 缺口 □
```
