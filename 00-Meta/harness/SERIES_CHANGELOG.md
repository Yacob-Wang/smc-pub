# 系列更新流水 · SERIES_CHANGELOG

> **协议**：正文系列新增/重写/大改/规范升级必须追加。见 `.cursor/rules/02-series-changelog.mdc`。  
> **顺序**：最新在上。

## 最新

### 2026-08-04 · meta+cleanup · 章定位 MDC + 全库错位稿归档
- **路径**：`.cursor/rules/05-chapter-positioning.mdc`；`_archive/misplaced-by-chapter-boundary/2026-08-04/`
- **动作**：规范落地 + 错位正文迁出（归档，非丢内容）
- **摘要**：
  - 新增 alwaysApply 规则：卷/章定位硬边界；同步 AGENTS / 00/01/04 MDC / harness README
  - 归档：第6章已覆盖的 A02 综合稿；第21章中断/IO SOP；第35章 Git/Logcat/ftrace/Init.rc 等；第13.C 签名（应属第5章）
  - 归口：`E09` Hprof 案例 → 第 50 章
  - 第35章恢复为骨架（待写 35.1–35.6）
- **规范**：`05-chapter-positioning.mdc`
- **关联**：LT-004 继续扫剩余疑似串章（如第46章端侧 AI 深度 vs 调试定位）

### 2026-08-04 · structure · 第10章边界收紧：A01–A04 迁出
- **路径**：`02-卷2-系统启动/10-应用启动与首帧/A01`–`A04` → `_archive/vol2-A-module-superseded-by-ch6-9/`
- **动作**：归档迁移（写书职责切分，非内容作废）
- **摘要**：第 6–9 章已覆盖 Bootloader / Init / Zygote / SystemServer，第 10 章不得再放整机启动长文——
  - 章内仅留 A05（组件/Activity 链路）+ A06（首帧 / Choreographer）供拆 10.x
  - 第 10 / 卷 index / README 写明章边界；第 11 章与学习路线链接改指第 6–9 章
  - `缺口一览` / `LONG_TASKS` 同步「素材仅 A05/A06」
- **规范**：书章体严谨切分；禁止在第 10 章复述第 6–9 章主线
- **关联**：承接同日 Old/ 清理；下一步拆写 10.1–10.7

### 2026-08-04 · cleanup · 卷 2 无效 Old 归档清理
- **路径**：`02-卷2-系统启动/10-应用启动与首帧/Old/`（整夹删除，15 篇）
- **动作**：删除（v1 旧基线 / C 级骨架，已被 A01–A06 与第 6–9 章覆盖）
- **摘要**：统一清理卷 2 无效内容——
  - 删除 `Old/` 15 篇（源码目录 / 分区 / Bootloader / Init 等错位通识稿）
  - 同步 `10-.../index.md`、`02-.../README.md` §7.5、`06-.../index.md` 过期「0 篇章」元数据
  - 修正卷 `index.md` 第 8/9 章状态（与磁盘 8.x/9.x 一致）
  - 脚本：`delete_e_grade.py` 去掉已删路径；`book_mapping.py` 注明 Old 已删
  - 账本：`缺口一览.md` / `LONG_TASKS.md` 去掉「第 8–9 章仅骨架」，改为第 10 章待拆 10.x
- **规范**：不作读者入口；溯源靠 git 历史
- **关联**：质量清单中 Old 条目随之失效（TD-003 重跑时自然消失）
- **保留**：A01–A06、第 6 章 A02 综合稿、第 11 章 B/C/D（现行素材/正文，未删）

### 2026-08-04 · meta · v6.0 GA 正式生效(写作规范唯一)
- **路径**：`PROMPT-技术系列文章写作指南.md` v6.0 GA · `.cursor/rules/01-writing-standards.mdc` · `AGENTS.md` · `scripts/verify_v6/` · `00-Meta/v6.0-GA-切换记录.md`
- **动作**：规范升级(v6 草案 v0.1 → v6.0 GA,取代 v5 / v4-Binder 同期)
- **摘要**：v6.0 GA 正式生效——
  - 顶部加 v6.0 GA 声明(版本/生效日期/维护者/取代/实战基础)
  - §1 补多版本内核矩阵(借 v4,5 版本:5.10/5.15/6.1/6.6/6.18 LTS)
  - §5 反例库 #1-#12 错例全文补全(借 v4,4614 字符)
  - §8 破例适用场景明确列表(借 v4,横切型/演进型/总览型/诊断工具型 4 类)
  - 附录 B 切换流程标记已生效 + 附录 C 加 C.2 第 8/9 章 v6 落地数据
- **工程基线落地**：
  - `scripts/verify_v6/` 7 个工具(verify_marker / verify_strip / verify_colon / verify_paths / verify_bug6 / verify_control / verify_ai_words)+ run_all.py 入口 + README
  - 9.1 实测 ALL TOOLS PASS
  - 设计原则:每个工具独立可执行 + 统一退出码 + 用 chr() 拼字符串 + STRICT/WARN 双层
- **强制升级 3 个文件**：01-writing-standards.mdc / AGENTS.md / PROMPT 主文档
- **规范**：v6 唯一,后续所有写作任务强制 v6;_archive/ 历史快照只读
- **关联**：LT-000 完成,实战数据第 8/9 章 12 节 v6 落地 23564 中文字 / 12 个实战案例

### 2026-08-04 · archive · v4-Binder 同期 vs v6 规范对比样本
- **路径**：`_archive/v4-binder-同期-09-对照/9.1-...md` + `对比-v4-vs-v6-9.1.md`
- **动作**：新增（v4-Binder 同期规范下的 9.1 对照样本 + 对比报告）
- **摘要**：用同一章节 9.1 章首节作为样本，对比 v4（2026-07-18）与 v6（2026-07-22）两个版本的写作规范——
  - v4 9.1：5 段前言**内联**在正文 + AOSP 14 基线 + 5250 中文字
  - 对比报告：6 维度对比（基线/模板/质量/反例/工程基线/子线程协作）
  - 结论：新项目首选 v6；v4 风格的"适用场景列表 / 反例错例全文 / 破例适用列表"v6 应借鉴
- **规范**：v4 规范落地（用于对比），不是替代 v6
- **关联**：与 09-SystemServer v6 主线并存于仓库，可同时查阅

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
