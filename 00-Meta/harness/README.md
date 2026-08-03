# Harness · 工程控制面

> **定位**：把「写书」按 harness 工程管理——目标、债务、长任务、系列变更均有单一账本。  
> **约束**：`.cursor/rules/*.mdc`（随仓库入库）强制 Agent 同步本目录。  
> **基线**：AOSP `android-17.0.0_r1` + Linux `android17-6.18`  
> **建立**：2026-08-03

## 账本索引

| 文件 | 作用 |
|:---|:---|
| [GOALS.md](GOALS.md) | 工程目标与里程碑 |
| [TECH_DEBT.md](TECH_DEBT.md) | 技术债务登记与偿还 |
| [LONG_TASKS.md](LONG_TASKS.md) | 跨会话长任务 |
| [SERIES_CHANGELOG.md](SERIES_CHANGELOG.md) | 系列正文更新流水（追加） |

读者向缺口进度仍用：[../缺口一览.md](../缺口一览.md)（须与本 harness 一致）。

写作规范真相源：[../../PROMPT-技术系列文章写作指南.md](../../PROMPT-技术系列文章写作指南.md) §0。

## Agent / 作者工作流（最短）

```
开干 → 读 LONG_TASKS（in_progress）+ TECH_DEBT（P0）
     → 按 v6 §0 写/改正文
     → 追加 SERIES_CHANGELOG
     → 必要时更新 缺口一览 / TECH_DEBT / LONG_TASKS
     → 结束（默认不 commit，除非用户要求）
```

## MDC 规则

| 规则 | 作用 |
|:---|:---|
| `.cursor/rules/00-smc-harness.mdc` | 总则（always） |
| `.cursor/rules/01-writing-standards.mdc` | 卷内正文写作 |
| `.cursor/rules/02-series-changelog.mdc` | 强制变更记录 |
| `.cursor/rules/03-tech-debt-long-tasks.mdc` | 债务与长任务协议 |
