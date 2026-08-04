# 技术债务 · TECH_DEBT

> **最后更新**：2026-08-04  
> **协议**：见 `.cursor/rules/03-tech-debt-long-tasks.mdc`  
> **状态枚举**：`open` | `in_progress` | `done` | `wontfix`

## 登记表

| ID | 优先级 | 类型 | 症状 | 偿还标准 | 状态 | 路径/备注 |
|:---|:---:|:---|:---|:---|:---:|:---|
| TD-001 | P0 | 工具 | `quality_audit.py` 写死他人机器路径 | `REPO` 改为仓库相对/`Path(__file__)` | done | `00-Meta/scripts/quality_audit.py`（2026-08-03 已修） |
| TD-002 | P0 | 账本 | 缺口一览停在 2026-07-24，P0 与磁盘不符 | 与现行 8 卷对齐并注明来源日期 | done | `00-Meta/缺口一览.md`（2026-08-03 已刷新） |
| TD-003 | P0 | 质量 | `_quality_audit.json` / 待替换清单含已删旧路径 | 修 TD-001 后重跑，归档旧 JSON | open | `00-Meta/scripts/_quality_audit.json` |
| TD-004 | P1 | 内容 | 14 章仅有骨架 `index.md` | 每章至少 5–6 节达标正文或降级合并 | open | 见缺口一览 §骨架章 |
| TD-005 | P1 | 规范 | 多篇仍标 v5 / AOSP 14 基线 | 升 v6 §0 + AOSP 17，或标废弃进 `_archive` | open | Perfetto/Watchdog/AI-Native 等 |
| TD-006 | P1 | 链接 | 正文残留 `01-Mechanism/`、`05-Governance/` 等 | 全库 grep 清零或改现行卷路径 | open | v6 §0.8 黑名单 |
| TD-007 | P2 | 元数据 | 系列 README 状态与正文不同步（如 APM README 仍写「占位」） | README 进度表与文件列表一致 | open | `07-卷7/.../43-APM/README.md` |
| TD-008 | P2 | 结构 | 卷 8 第 48/49 章空壳，案例挤在 47/50 | 按书籍目录归口或改目录说明 | open | `08-卷8-案例实战/` |
| TD-009 | P2 | 工具 | 写作质量未进 CI | 可选：PR 上对改动 md 跑 `verify_gc_publish.py` | open | `.github/workflows/pages.yml` |
| TD-010 | P3 | 债务 | archive 中旧「待替换清单」易被误用 | README 标明「仅历史；以重跑结果为准」 | open | `_archive/legacy-workdocs/待替换清单-v1.md` |
| TD-011 | P1 | 结构 | 仍有章内串题/系列 README 与书章入口并存 | 按 LT-004 扫尾；错位进 `_archive` 或归口正确章 | open | 见 `05-chapter-positioning.mdc` |

## 偿还日志

| 日期 | ID | 动作 |
|:---|:---|:---|
| 2026-08-04 | — | 落地 `05-chapter-positioning.mdc`；首批错位归档（ch6 A02 / ch21 / ch35 / ch13.C）；E09→ch50 |
| 2026-08-04 | — | 第 10 章 A01–A04 迁 `_archive/`（与第 6–9 章职责重叠）；章内仅留 A05/A06 |
| 2026-08-04 | — | 卷 2 删除 `10-.../Old/` 15 篇无效 v1 稿；修正卷/章 index 过期状态 |
| 2026-08-03 | TD-002 | 刷新 `缺口一览.md`，建立 harness 账本 |
| 2026-08-03 | TD-001 | `quality_audit.py` 的 `REPO` 改为 `Path(__file__).parents[2]` |
| 2026-08-03 | — | 建立本登记表与 MDC 约束 |

## 如何新增

复制一行到表顶（open 区），分配下一个 `TD-xxx`，优先级默认 P2，P0 仅用于「阻断发布或误导读者」的项。
