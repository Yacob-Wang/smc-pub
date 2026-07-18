# 05-Governance · Android 稳定性治理（8 大主题）

> **目标读者**：Android 稳定性架构师 / APM Lead / BSP 工程师 / 平台架构师
>
> **分类定位**：按 **运营治理视角**组织 8 大主题——APM 体系建设、OEM 适配、跨平台、低端机、AI Native、性能 vs 内存、安全、AI 辅助调试
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）

---

## 0. 分类总定位

### 0.1 一句话定位

**Governance 是 smc-pub 的"运营视角"——把 Android 稳定性从"机制 + 症状 + 取证 + 工具"延伸到"APM 体系建设 + 跨厂商适配 + 跨平台兼容 + AI 辅助"等运营级主题，让架构师能治理整个稳定性生态。**

### 0.2 与其他分类的关系

| 维度 | Governance | Mechanism | Symptom | Tool |
|:-----|:------------|:----------|:--------|:-----|
| **视角** | 治理（运营）| 机制（技术）| 症状（线上）| 工具（横向）|
| **核心问题** | "怎么治理整个生态" | "这层怎么工作" | "线上出问题怎么归类" | "用什么工具查" |
| **产出** | 治理框架 + 度量体系 | 源码 + 流程图 | 风险地图 + 排查剧本 | 工具子命令 |

> **本分类以"运营视角"统合所有技术细节**——给架构师"如何治理 1000 万设备稳定性"的整体方案。

### 0.3 8 大主题（P0/P1/P2/P3 优先级）

| # | 主题 | 优先级 | 状态 | 重点 |
|:--|:-----|:------:|:----:|:-----|
| 1 | **APM**（应用性能监控）| 🟢 P0 | 占位 | 度量体系 + 发布门禁 + 闭环治理 |
| 2 | **OEM-BSP**（OEM 适配）| 🟢 P0 | 占位 | 华为/小米/OPPO/vivo/三星 适配 |
| 3 | **CrossPlatform**（跨平台）| 🟢 P1 | 占位 | HarmonyOS / iOS / 嵌入式 Linux |
| 4 | **LowEnd**（低端机）| 🟢 P1 | 占位 | < 4GB RAM + MTK 6580 等 |
| 5 | **AI-Native**（AI Native 操作系统）| ✅ 完成 | 37 篇 | 4 子主题（Runtime/OS/Stability/Engineering）|
| 6 | **AI-Debug**（AI 辅助调试）| 🟡 P3 | 占位 | LLM + dump 解读 + 智能归因 |
| 7 | **PerfMem**（性能 vs 内存权衡）| 🟡 P2 | 占位 | 性能/内存/电量三角权衡 |
| 8 | **Security**（安全 + 稳定性）| 🟡 P2 | 占位 | PAC-BTI/ MTE + 漏洞利用稳定性影响 |

---

## 1. 子主题导览

### 1.1 APM/（🟢 P0 必写 · 占位）

- **核心问题**：如何搭建 APM 体系，从 0 到 1000 万设备
- **计划内容**（10 篇左右）：
  - APM 体系总览（指标 + 数据流 + 治理）
  - 5 大度量（MTBF / 崩溃率 / ANR 率 / 严重性 / 回归率）
  - 6 大门禁维度（崩溃 / ANR / 性能 / 兼容 / 安全 / 业务）
  - Stability Score 综合指数
  - 4 步闭环（度量 → 决策 → 行动 → 回归）
  - 案例：某电商 App 6 月治理闭环
  - 案例：某社交 App 春节跳过门禁（反面）
- **联动**：[02-Symptom/S10-Measure](../02-Symptom/S10-Measure/) 完整度量学 + 04-Tool/ 数据采集

### 1.2 OEM-BSP/（🟢 P0 必写 · 占位）

- **核心问题**：5 大 OEM 厂商的定制与适配
- **计划内容**（5-7 篇）：
  - 华为 HMS / HarmonyOS Next 适配
  - 小米 MIUI HyperOS 适配
  - OPPO ColorOS 适配
  - vivo OriginOS 适配
  - 三星 OneUI 适配
  - 5 大 OEM 启动器对比
- **联动**：[01-Mechanism/App/Hook](../01-Mechanism/App/Hook/) 5 大 OEM Hook 风格

### 1.3 CrossPlatform/（🟢 P1 · 占位）

- **核心问题**：跨 Android / HarmonyOS / iOS / 嵌入式 Linux
- **计划内容**（5-7 篇）：
  - 跨平台稳定性抽象层设计
  - HarmonyOS Next 兼容层
  - iOS Crash/ANR 体系对比
  - 嵌入式 Linux Yocto 适配
  - Rust 在 Android/HarmonyOS 的角色

### 1.4 LowEnd/（🟢 P1 · 占位）

- **核心问题**：低端机（< 4GB RAM / MTK 6580 / Android 8 以下）稳定性
- **计划内容**（5-7 篇）：
  - 低端机稳定性挑战总览
  - 内存压力下的 GC 调优
  - 启动期 IO 优化（f2fs 适配）
  - 启动期 GC 抑制策略
  - 案例：东南亚低端机项目治理

### 1.5 AI-Native/（✅ 已完成 · 37 篇）

- **4 子主题**：

| 子主题 | 篇数 | 重点 |
|:-------|:----:|:-----|
| 01_AI_Native_Runtime | 8 + README | NNAPI / TFLite / ONNX / GPU Delegate / NPU / 端侧 LLM |
| 02_AI_Native_OS | 6 + README | AI Native OS 范式 + System Intelligence + AICore + AI Agent OS + Gemini Nano + 智能服务 |
| 03_AI_for_Stability | 6 + README | 时序异常检测 + 智能归因 + AI 预测 ANR + 大模型日志分析 + 智能 APM |
| 04_AI_Engineering | 12 + README | Prompt/Skill/Context + Token 预算 + Durable Execution + Evals + Policy as Code + MCP + 信任边界 + 副作用 + HITL + Release Control + Compound Agent + Model Routing |

- **v4 特色**：每篇 300+ 行 + 4 附录 + 3 轮校准
- **联动**：[02-Symptom/S08-AOSP17-K618](../02-Symptom/S08-AOSP17-K618/) AOSP 17 AppFunctions 集成

### 1.6 AI-Debug/（🟡 P3 · 占位）

- **核心问题**：LLM 解读 dump + 智能归因
- **计划内容**（5-7 篇）：
  - LLM 解读 traces.txt
  - LLM 解读 tombstone
  - LLM 智能归因
  - 智能 APM 升级路径
- **联动**：[AI-Native/03_AI_for_Stability](../05-Governance/AI-Native/03_AI_for_Stability/)

### 1.7 PerfMem/（🟡 P2 · 占位）

- **核心问题**：性能 / 内存 / 电量三角权衡
- **计划内容**（5-7 篇）：
  - 性能 vs 内存总览（5 大红线）
  - ART 17 分代 GC 内存节省
  - 启动期内存压力优化
  - 后台进程电耗优化
  - Low Memory Killer 配置
- **联动**：[01-Mechanism/Runtime/ART/03-GC系统](../01-Mechanism/Runtime/ART/03-GC系统/) 99 篇

### 1.8 Security/（🟡 P2 · 占位）

- **核心问题**：安全漏洞利用对稳定性的影响
- **计划内容**（5-7 篇）：
  - PAC-BTI 防护对性能影响
  - MTE 内存标签扩展
  - SELinux 与稳定性
  - 漏洞利用导致的崩溃
  - Rust 化对安全与稳定性的双重收益
- **联动**：[01-Mechanism/Kernel](../01-Mechanism/Kernel/) Linux 6.18 Rust Binder

---

## 2. 文档统计

| 子主题 | 文件数 | 状态 | 重点 |
|:-------|:------:|:----:|:-----|
| APM/ | 0 | 🟡 占位 | 必写 P0 |
| OEM-BSP/ | 0 | 🟡 占位 | 必写 P0 |
| CrossPlatform/ | 0 | 🟡 占位 | P1 |
| LowEnd/ | 0 | 🟡 占位 | P1 |
| AI-Native/ | 37 | ✅ 完成 | v2 化 + 4 子主题 |
| AI-Debug/ | 0 | 🟡 占位 | P3 |
| PerfMem/ | 0 | 🟡 占位 | P2 |
| Security/ | 0 | 🟡 占位 | P2 |
| **总计** | **37** | **1 大完成 + 7 占位** | **AI-Native 是核心** |

---

## 3. 强依赖 / 衔接

- **被依赖**：
  - [02-Symptom](../02-Symptom/) S08-S10 引用 Governance 讲演进 + 横切 + 治理
  - [06-Case/Startup](../06-Case/Startup/) 引用 OEM-BSP 讲案例
- **依赖**：
  - [01-Mechanism](../01-Mechanism/) 所有机制层
  - [02-Symptom](../02-Symptom/) 所有症状
  - [03-Forensics](../03-Forensics/) 所有取证
  - [04-Tool](../04-Tool/) 所有工具

---

## 4. 后续计划（P0 → P1 → P2 → P3 顺序）

1. **APM 10 篇**（🟢 P0 必写）— 度量 + 门禁 + 闭环
2. **OEM-BSP 5-7 篇**（🟢 P0 必写）— 5 大厂商适配
3. **CrossPlatform 5-7 篇**（🟢 P1）— 跨平台稳定性
4. **LowEnd 5-7 篇**（🟢 P1）— 低端机治理
5. **PerfMem 5-7 篇**（🟡 P2）— 性能内存权衡
6. **Security 5-7 篇**（🟡 P2）— 安全 + 稳定性
7. **AI-Debug 5-7 篇**（🟡 P3）— LLM 调试

---

**最后更新**：2026-07-19（阶段 3 完成）
**作者**：Mavis · Stability Matrix Course
