# AGENTS

本仓库按 **harness 工程**管理写书工作。Agent 须遵守：

1. `.cursor/rules/00-smc-harness.mdc`（总则）
2. `.cursor/rules/01-writing-standards.mdc`（**写作强制**：AOSP 17 + GKI 6.18 + 真实源码 + **书章默认体例**）
3. `.cursor/rules/05-chapter-positioning.mdc`（**卷/章定位硬边界**：文章必须符合所属章定位，禁止串章）
4. `.cursor/rules/04-book-chapter.mdc`（卷内 `N.M-*.md` 续写约定）
5. 账本：`00-Meta/harness/`（GOALS / TECH_DEBT / LONG_TASKS / SERIES_CHANGELOG）
6. **详规/模板（按需）：`PROMPT-技术系列文章写作指南.md` v6.0 GA**（§1–§13 + 附录 A–C，14 章 44 KB，2026-08-04 生效）
7. **工程基线工具集（按需）：`scripts/verify_v6/`**（7 个工具 + run_all.py 入口，v6 §10.4 落地）
8. 正文大改后：**追加** `SERIES_CHANGELOG.md`；读者缺口：`00-Meta/缺口一览.md`

入口：`00-Meta/harness/README.md`。

## 规范版本（2026-08-04 锁定）

- **现行规范**：v6.0 GA（唯一）
- **取代**：v6 草案 v0.1 / v5 / v4-Binder 同期
- **历史快照（仅考古）**：`_archive/v4-binder-同期-09-对照/` / `_archive/PROMPT-技术系列文章写作指南-v5-final.md`（如存在）
- **v6 实战数据**：第 8/9 章 12 节 v6 规范落地（commit e4d9ca7 / 1cf5c00-7701809）+ 12 个实战案例 + 23564 中文字
- **未来工程基线**：
  - 新写/重写 → v6 唯一
  - 老系列 v5 维护 → 不强制升级 v6，但鼓励迁移
  - 历史快照（_archive/）→ 不再修改，仅作历史对照参考
