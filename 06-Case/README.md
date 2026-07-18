# 06-Case · 跨系列案例库

> **目标读者**：Android 稳定性架构师 / 性能架构师 / oncall 工程师
>
> **分类定位**：按 **场景维度**组织跨系列案例——同一场景下从机制 → 症状 → 取证 → 工具 → 治理的完整闭环
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）

---

## 0. 分类总定位

### 0.1 一句话定位

**Case 是 smc-pub 的"实战案例库"——把跨系列的案例集中归档，避免"案例散落在 02-Symptom/03-Forensics/05-Governance 各处"，让架构师能"按场景查案例"。**

### 0.2 与其他分类的关系

| 维度 | Case | Symptom | Forensics | Governance |
|:-----|:-----|:--------|:----------|:------------|
| **视角** | 场景（实战）| 症状（线上）| 取证（事后）| 治理（运营）|
| **核心问题** | "线上怎么修" | "线上怎么归类" | "事后怎么取证" | "怎么治理" |
| **产出** | 案例 + 排查剧本 | 风险地图 + 排查路径 | dump 解读 | 治理框架 |

> **本分类是 Symptom + Forensics 的"实战延伸"**——讲清楚"线上出问题后，整个 oncall 流程怎么走"。

### 0.3 2 子分类

| 子分类 | 状态 | 重点 |
|:-------|:----:|:-----|
| **Startup/** | ✅ E01-E03 + README | AOSP_Startup 22 篇 v4 中的 E01-E03 实战案例 |
| **Cases-Extended/** | 🟡 占位 | 后续跨系列案例扩展（如 OEM/AI/CrossPlatform）|

---

## 1. 子分类导览

### 1.1 Startup/（✅ 已就位 · 4 文件）

- **位置**：[Startup/README.md](Startup/README.md)
- **完成**：E01-E03 启动场景案例已从兼容层 Android_Framework/AOSP_Startup/ 迁移到 06-Case/Startup/

| 案例 | 主题 | 涉及模块 |
|:-----|:-----|:---------|
| E01 | 冷启动 8s → 1s 优化全过程 | A + B + D |
| E02 | 启动卡死 SystemServer 60% 进度 | A + C + D |
| E03 | 开机黑屏 30s SurfaceFlinger 卡死 | A + C + D |

- **后续计划**（E04-E11 占位）：
  - E04 启动期 ANR：5s vs 20s vs 200s 阈值案例
  - E05 启动崩溃：SystemServer crash + BootLoop
  - E06 启动期 IO 卡顿：f2fs / ext4 fsync
  - E07 启动期 GC 卡顿：分代 GC 启动期表现
  - E08 OEM 启动定制：小米/华为/OPPO 启动器对比
  - E09 启动期权限弹窗：弹窗流程耗时
  - E10 启动期 32/64 位切换：ART 17 优化
  - E11 启动期 AI Agent OS 集成：AOSP 17 AppFunctions

### 1.2 Cases-Extended/（🟡 占位）

- **状态**：未开始
- **计划方向**：
  - OEM 案例：华为/小米/OPPO/vivo/三星 的真实稳定性事故
  - 性能案例：抖音/微信/支付宝 的启动优化
  - 跨平台案例：HarmonyOS Next 兼容层问题
  - AI 案例：端侧 LLM 推理导致的稳定性问题
  - 安全案例：漏洞利用导致的崩溃

---

## 2. 文档统计

| 子分类 | 文件数 | 状态 |
|:-------|:------:|:----:|
| Startup/ | 4 | ✅ E01-E03 + README |
| Cases-Extended/ | 0 | 🟡 占位 |
| **总计** | **4** | **启动案例就位 + 扩展待写** |

---

## 3. 强依赖 / 衔接

- **被依赖**：
  - 暂无（案例是"消费者"）
- **依赖**：
  - [02-Symptom/S11-Startup](../02-Symptom/S11-Startup/) 启动机制 + 性能 + 稳定性 + 工具
  - [04-Tool/Dumpsys](../04-Tool/Dumpsys/) + [04-Tool/Perfetto](../04-Tool/Perfetto/) 案例配套工具
  - [05-Governance/OEM-BSP](../05-Governance/OEM-BSP/) 后续 OEM 案例

---

## 4. 后续计划

1. **E04-E11 启动场景案例**：先写 E04/E05/E06（最常见的 3 类启动故障）
2. **Cases-Extended 跨系列案例**：
   - 阶段 1：OEM 案例（5-10 篇）
   - 阶段 2：性能 + 稳定性综合案例（5-10 篇）
   - 阶段 3：AI + 安全案例（5-10 篇）

---

**最后更新**：2026-07-19（阶段 3 完成）
**作者**：Mavis · Stability Matrix Course
