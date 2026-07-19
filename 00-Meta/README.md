# smc-pub · Android 稳定性 / 性能 / 启动 / 治理 系列大本营

> **项目**：Android 稳定性架构师实战大本营（smc-pub = Stability Matrix Course Pub）
>
> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）
>
> **目标读者**：Android 稳定性架构师 / 性能架构师 / BSP 工程师
>
> **完成日期**：2026-07-19

---

## 项目地图

本仓库按 **AOSP 系统分层 + oncall 工作流**双轴设计 8 大分类：

| 分类 | 角色 | 子模块 | 文件数 |
|:-----|:-----|:-------|:------:|
| **00-Meta/** | 项目地图 + 构建产物 | Reference/ + reader/ + web/ + scripts/ + overrides/ | 86 |
| **01-Mechanism/** | 机制（按 AOSP 分层）| Hardware/ + Kernel/ + Native/ + Runtime/ + Framework/ + App/ | 441 |
| **02-Symptom/** | 症状（11 大类 S01-S11）| S00 总览 + S01-ANR ~ S10-Measure + S11-Startup 4 子分类 | 49 |
| **03-Forensics/** | 取证（8 大类 F00-F07）| F00-Overview + F01-ANR ~ F06-HANG-OOM + F07-Governance | 9 |
| **04-Tool/** | 7 大工具 | Dumpsys/ + Watchdog/ + Perfetto/ + Hprof/ + AmCommand/ + ANR-Detection/ + Tracing/ | 90 |
| **05-Governance/** | 8 大治理主题 | APM/ + OEM-BSP/ + CrossPlatform/ + LowEnd/ + AI-Native/ + AI-Debug/ + PerfMem/ + Security/ | 37 |
| **06-Case/** | 案例库（跨分类）| Startup/（E01-E11 占位）| 4 |
| **06-Foundation/** | 4 大基础主题 | Build-System/ + System-Integration/ + Dynamic-Updates/ + Tools/ | 37 |

**总文档量**：753 个 md 文件 / 169 个子目录 / 20.29 MB

---

## 核心索引（按阅读顺序）

### 0. 项目入口（先看这个）

1. **[README.md](../../README.md)**（仓库根）— 一页纸项目介绍
2. **[迁移日志.md](迁移日志.md)** — 2026-07-19 目录重构全记录
3. **[引用矩阵.md](引用矩阵.md)** — 跨系列引用全景 + 21 项映射表

### 1. 元信息（项目级）

4. **[版本基线.md](版本基线.md)** — AOSP 17 + android17-6.18 基线声明
5. **[术语表.md](术语表.md)** — Stability / Performance / Hook / ART 17 / K 6.18 关键术语
6. **[案例索引.md](案例索引.md)** — 跨系列案例索引（CASE-STAB-01 ~ CASE-STAB-10）

### 2. 核心入口（按需深读）

- **症状总览**：[02-Symptom/S00-症状总览.md](../02-Symptom/S00-症状总览.md)
- **取证总览**：[03-Forensics/README.md](../03-Forensics/README.md)
- **学习路线**：[02-Symptom/README-学习路线.md](../02-Symptom/README-学习路线.md)
- **启动专项**：[02-Symptom/S11-Startup/README.md](../02-Symptom/S11-Startup/README.md)
- **启动案例**：[06-Case/Startup/README.md](../06-Case/Startup/README.md)

---

## 阅读路径建议

### 路径 A：稳定性架构师（推荐）

```
L00 学习路线 → S00 总览 → S01-S07 7 大症状 → F01-F06 对应取证 → 04-Tool 工具链 → 案例索引
```

### 路径 B：性能架构师

```
AOSP_Startup 22 篇 → 01-Mechanism/Runtime/ART (99 篇) → 04-Tool/Perfetto → 02-Symptom/S11-Startup/B 性能
```

### 路径 C：BSP 工程师

```
01-Mechanism/Kernel (14 子系统) → 01-Mechanism/Hardware → 02-Symptom/S07-KE → 05-Governance/OEM-BSP
```

### 路径 D：AI Native 工程师

```
05-Governance/AI-Native (37 篇) → 05-Governance/AI-Debug → 02-Symptom/S08-AOSP17-K618
```

---

## 6 大分类设计原则

1. **AOSP 分层（机制维度）**：`01-Mechanism/` 按 Hardware → Kernel → Native → Runtime → Framework → App 分层
2. **症状/取证对齐（oncall 维度）**：`02-Symptom/S01-ANR` ↔ `03-Forensics/F01-ANR` 一一对应
3. **工具独立（专业维度）**：`04-Tool/` 不混症状 / 不混机制，独立成类
4. **治理统一（运营维度）**：`05-Governance/` 装 APM / OEM / 跨平台 / 低端机 / AI / 安全 等
5. **案例分离（场景维度）**：`06-Case/` 跨系列案例库，不重复症状内的实战段
6. **基础后置（依赖维度）**：`06-Foundation/` 装 BSP / 构建 / 杂项，最后查

---

## 维护与更新

- **添加新文档**：参考 v4 写作规范（`PROMPT-技术系列文章写作指南-v4.md`）
- **跨系列引用**：参考 [引用矩阵.md](引用矩阵.md) 的 21 项映射
- **目录重构**：参考 [迁移日志.md](迁移日志.md) 的 3 阶段模板
- **质量门**：单篇 300 行 / 9 项硬指标 / 4 附录 / 3 轮校准决策日志

---

## 联系与反馈

- **作者**：Mavis · Stability Matrix Course
- **最后更新**：2026-07-19（阶段 3 完成）

