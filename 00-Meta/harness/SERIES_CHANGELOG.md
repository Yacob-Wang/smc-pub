# 系列更新流水 · SERIES_CHANGELOG

> **协议**：正文系列新增/重写/大改/规范升级必须追加。见 `.cursor/rules/02-series-changelog.mdc`。  
> **顺序**：最新在上。

## 最新

### 2026-08-04 · boot · 第 9 章 SystemServer 启动
- **路径**：`02-卷2-系统启动/09-SystemServer 启动/9.1-...md` ~ `9.6-...md` + `09-.../index.md`
- **动作**：新增（从骨架完成到全章 6 节 v6 规范落地）
- **摘要**：第 9 章 6 节全部按 v6 规范完成——
  - 9.1 章首节 SystemServer 启动入口（SystemServer.java + run() 5 大步 + 事件链）
  - 9.2 服务启动三阶段（Bootstrap→Core→Other + 阶段内并行 + BootPhase）
  - 9.3 4 大服务详解（PMS/AMS/WMS/IMS 启动依赖 + 锁与死锁）
  - 9.4 ServiceManager + 4 类 Binder 域（SYSTEM/vendor/isolated/contextHub）
  - 9.5 bootstat 与阶段耗时归因（10+ 个 ro.boottime.* 差值实战）
  - 9.6 SystemServer 启动慢/死锁/crash 调查（5+3+4=12 类根因 + 30 秒定位 SOP）
- **规范**：v6 §0 自检 ■ + verify 6/6 全 PASS（0 子线程 6 类 bug / 0 控制字符 / 0 半角冒号 / 0 rogue marker / 2 START + 2 END 配对）
- **字数**：7 个文件 / 192 KB / 23564 中文字（章首页 1256 + 9.1-9.6 合计 22308）
- **关联**：调整前后承接（与 7.1-7.3 / 8.1-8.6 / 10-12 / 11 章边界已重新声明），跨卷引用卷 3 第 12 章 Binder IPC 深度

### 2026-08-04 · meta · 恢复 Binder 同期写作指南 v4 快照
- **路径**：`PROMPT-技术系列文章写作指南-v4-Binder同期.md` · `00-Meta/harness/snapshots/PROMPT-…-v4-Binder同期-2026-07-18.md`
- **动作**：新增（历史快照，不覆盖现行 PROMPT/MDC）
- **摘要**：从提交 `877e9d5`（2026-07-18）取出根目录 `PROMPT-…-v4.md`；对应 Binder `01-Binder总览` v2 成稿所依规范
- **规范**：n/a（考古）；现行仍以 MDC + 根目录 PROMPT 为准
- **关联**：质量样板系列 `12-Binder IPC 深度`

### 2026-08-04 · writing-standards · 书章体例写入 MDC
- **路径**：`.cursor/rules/01-writing-standards.mdc` · `.cursor/rules/04-book-chapter.mdc` · `AGENTS.md`
- **动作**：规范升级
- **摘要**：明确 8 卷默认书章体（YAML+H1+开场）；禁止续写时串用 A02 系列长前言；样板指向 6.1/7.1
- **规范**：MDC 为准
- **关联**：供 Cursor / Minimax 等 Agent 统一遵守

### 2026-08-04 · boot · 第 8 章 Zygote 与 ART 启动
- **路径**：`02-卷2-系统启动/08-Zygote 与 ART 启动/8.1-...md` ~ `8.6-...md` + `08-.../index.md` + `02-卷2-系统启动/index.md`
- **动作**：新增（从骨架完成到全章 6 节 v6 规范落地）
- **摘要**：第 8 章 6 节全部按 v6 规范完成——
  - 8.1 章首节 Zygote fork + 预加载机制（全局观 + 6 步流水线）
  - 8.2 ART 启动（libart.so / ClassLinker / OAT 镜像加载 + Runtime::Init 4 大步）
  - 8.3 启动预优化（PGC + Cloud Profile + dex2oat 触发链）
  - 8.4 启动类加载优化（preload vs lazy 判定准则）
  - 8.5 Zygote fork 慢 / crash 调查（收窄到内因 3+4）
  - 8.6 **本卷新增节** Zygote 内存治理（fork COW + RSS 控制 + LMKD 联动）
- **规范**：v6 §0 自检 ■ + verify 6/6 全 PASS
- **关联**：调整前后承接（与 7.2/7.3/9/10/11 边界已重新声明），新增节 8.6 填补"Zygote 内存治理"稳定性痛点

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
