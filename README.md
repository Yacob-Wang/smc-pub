# smc-pub：Android 稳定性架构师知识库

> **Stability Matrix Course** —— Android 稳定性 / 性能 / 工具 / 案例 系列 v4 风格文章
>
> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）
>
> **最后更新**：2026-07-19

---

## 🎯 项目定位

**smc-pub** 是面向 **Android 稳定性架构师** 的端到端知识库——

- 30+ 内容系列，~3MB v4 风格文章
- 覆盖 **Android 系统分层 × 工作流** 双轴
- **强依赖** AOSP 官方架构（按系统分层组织）

## 📁 目录架构（6 大分类）

```
smc-pub/
├── 00-Meta/                  # 元信息 + 构建产物（地图）
├── 01-Mechanism/             # 机制（按 AOSP 系统分层）
├── 02-Symptom/               # 症状（按 S 编号）
├── 03-Forensics/              # 取证（按 F 编号对齐 S 编号）
├── 04-Tool/                  # 工具
├── 05-Governance/            # 治理（运营视角）
└── 06-Foundation/            # 基础（BSP / 构建 / 杂项）
```

### 6 大分类角色

| 分类 | 角色 | 读者 | 阅读时长 |
|:-----|:-----|:-----|:---------:|
| **00-Meta** | 项目地图 / 引用矩阵 / 术语表 / 版本基线 | 所有读者 | 1 小时 |
| **01-Mechanism** | 按 AOSP 分层理解原理 | 通用开发者 | 2-3 周 |
| **02-Symptom** | 7 大症状机制（S01-ANR ~ S10-Measure）| 稳定性架构师 | 1-2 周 |
| **03-Forensics** | 7 大症状取证（F00-F07，对齐 S 编号）| oncall 工程师 | 1 周 |
| **04-Tool** | dumpsys / perfetto / hprof 等 7 大工具 | 性能 + oncall | 1 周 |
| **05-Governance** | APM / OEM / AI / 治理 8 大主题 | 资深架构师 | 按需 |
| **06-Foundation** | BSP / 构建 / 系统集成 / 杂项 | BSP 工程师 | 按需 |

## 🎯 双轴设计：Android 系统分层 × 工作流

```
                            机制 (AOSP 分层)   症状    取证    工具    治理    案例
                            ┌──────────┐    ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐
                            │ Hardware │    │ S  │  │ F  │  │ T  │  │ G  │  │ C  │
                            │ Kernel   │    │ 0  │  │ 0  │  │ 0  │  │ 0  │  │ 0  │
                            │ Native   │    │ 1  │  │ 1  │  │ 4  │  │ 5  │  │ 6  │
                            │ Runtime  │    │ -  │  │ -  │  │    │  │    │  │    │
                            │ Framework│    │ 1  │  │ 0  │  │    │  │    │  │    │
                            │ App      │    │ 0  │  │ 7  │  │    │  │    │  │    │
                            └──────────┘    └────┘  └────┘  └────┘  └────┘  └────┘
```

## 📚 内容系列总览（按分类）

### 00-Meta/（元信息 + 构建产物）

- `00-Meta/README.md` - 项目首页
- `00-Meta/引用矩阵.md` - 跨系列引用矩阵
- `00-Meta/术语表.md` - 术语统一
- `00-Meta/版本基线.md` - AOSP 17 + 6.18 基线
- `00-Meta/案例索引.md` - 实战案例索引
- `00-Meta/reader/` - Android Studio 演示项目
- `00-Meta/web/` - Hugo 输出
- `00-Meta/overrides/` - Hugo 模板
- `00-Meta/scripts/` - 全局脚本

### 01-Mechanism/（机制 - 按 AOSP 分层）

#### Hardware/（硬件层）
- 待建设：Bootloader / Driver / HAL

#### Kernel/（Linux Kernel 14 子系统）
- `01-Mechanism/Kernel/Binder/` - Linux Binder
- `01-Mechanism/Kernel/DM/` - Direct Memory
- `01-Mechanism/Kernel/FS/` - File System
- `01-Mechanism/Kernel/Input-Driver/` - Input Driver
- `01-Mechanism/Kernel/Interrupt/` - Interrupt
- `01-Mechanism/Kernel/IO/` - IO
- `01-Mechanism/Kernel/Memory-Management/` - 内存管理
- `01-Mechanism/Kernel/Process/` - Linux Process
- `01-Mechanism/Kernel/Syscalls/` - 系统调用
- 等 14 个子系统

#### Native/（Native C/C++ 层）
- 待建设：Init / Bionic / Linker

#### Runtime/（运行时 - ART）
- `01-Mechanism/Runtime/ART/` - ART（GC / dex2oat / 类加载）
- `01-Mechanism/Runtime/ClassLoader/` - 类加载器
- `01-Mechanism/Runtime/JNI/` - JNI
- `01-Mechanism/Runtime/Signal/` - 信号 + ANR

#### Framework/（Framework 层 - 7 大组件）
- 待建设：SystemServer / Activity / Service / Broadcast / ContentProvider / Window / Input / Process

#### App/（App 层）
- 待建设：Component / Handler / Hook

### 02-Symptom/（症状 - 11 篇）

- `02-Symptom/S01-ANR/` - ANR 卡死与 Input 响应
- `02-Symptom/S02-JE/` - Java 异常与 Crash
- `02-Symptom/S03-NE/` - Native 崩溃与 Tombstone
- `02-Symptom/S04-SWT/` - SWT 卡死与 Watchdog
- `02-Symptom/S05-HANG/` - HANG 与黑屏
- `02-Symptom/S06-REBOOT/` - 重启与 REBOOT
- `02-Symptom/S07-KE/` - KE 内核与硬件异常
- `02-Symptom/S08-AOSP17-K618/` - AOSP 17 + K 6.18 演进
- `02-Symptom/S09-PerfVsStab/` - 性能 vs 稳定性
- `02-Symptom/S10-Measure/` - 稳定性度量与发布门禁

### 03-Forensics/（取证 - 8 篇）

- `03-Forensics/F00-Overview/` - 取证体系总览
- `03-Forensics/F01-ANR/` (↔ 02-Symptom/S01)
- `03-Forensics/F02-SWT/` (↔ 02-Symptom/S04)
- `03-Forensics/F03-JE/` (↔ 02-Symptom/S02)
- `03-Forensics/F04-NE/` (↔ 02-Symptom/S03)
- `03-Forensics/F05-KE/` (↔ 02-Symptom/S07)
- `03-Forensics/F06-HANG-OOM/` (↔ 02-Symptom/S05)
- `03-Forensics/F07-Governance/` - 取证治理

### 04-Tool/（工具 - 7 大工具）

- `04-Tool/Dumpsys/` - dumpsys 总览 + 12 篇
- `04-Tool/Watchdog/` - Watchdog 9 篇
- `04-Tool/Perfetto/` - Perfetto 5 篇
- `04-Tool/Hprof/` - Hprof 5 篇
- `04-Tool/AmCommand/` - am 命令 6 篇
- `04-Tool/ANR-Detection/` - ANR 检测 3 篇
- `04-Tool/Tracing/` - Tracing 工具

### 05-Governance/（治理 - 8 大主题）

- `05-Governance/APM/` - APM 体系（8-10 篇，P0 必写）
- `05-Governance/OEM-BSP/` - OEM / BSP 视角（5-7 篇，P0 必写）
- `05-Governance/CrossPlatform/` - 跨平台稳定性（6-8 篇，P1）
- `05-Governance/LowEnd/` - 低端机 + 弱网（4-5 篇，P1）
- `05-Governance/AI-Native/` - AI Native Runtime / OS（已合并自 AI_Native_X/）
- `05-Governance/AI-Debug/` - AI 辅助调试（3-4 篇，P3 前沿）
- `05-Governance/PerfMem/` - 性能 vs 内存治理（2-3 篇，P2）
- `05-Governance/Security/` - 安全 + 稳定性（2-3 篇，P2）

### 06-Foundation/（基础 - 4 大主题）

- `06-Foundation/Build-System/` - AOSP 构建系统
- `06-Foundation/System-Integration/` - 系统集成
- `06-Foundation/Dynamic-Updates/` - OTA / A/B 分区
- `06-Foundation/Tools/` - Android Tools / Git / Memory Analysis

### 06-Case/（案例 - 待建设在 06-Case/ 下）

- `06-Case/Startup/` - 启动场景案例（E01-E03）
- `06-Case/Cases-Extended/` - 扩展案例（E04-E11 占位）

## 🔗 跨系列引用矩阵

详见 `00-Meta/引用矩阵.md`。

## 📖 阅读路径（按角色）

### 通用 Android 开发者
1. `00-Meta/README.md`（项目首页）
2. `00-Meta/引用矩阵.md`（跨系列引用）
3. `01-Mechanism/Framework/Activity/`（7 大组件）
4. `01-Mechanism/Runtime/ART/`（ART 运行时）

### 性能架构师
1. `01-Mechanism/Framework/`（Framework 层）
2. `01-Mechanism/Runtime/ART/`（ART 17 硬变化）
3. `02-Symptom/S08-AOSP17-K618/`（演进全景）
4. `02-Symptom/S09-PerfVsStab/`（性能 vs 稳定性）

### 稳定性架构师
1. `02-Symptom/S00-Overview/`（7 大症状总览）
2. `02-Symptom/S01-ANR/ ~ S07-KE/`（7 大症状）
3. `03-Forensics/F01-F07/`（7 大症状取证）
4. `02-Symptom/S10-Measure/`（度量门禁）

### oncall 工程师
1. `02-Symptom/`（症状识别）
2. `03-Forensics/`（取证剧本）
3. `04-Tool/Dumpsys/ + Perfetto/ + Hprof/`（工具）
4. `05-Governance/APM/`（监控告警）

### BSP / 系统集成工程师
1. `01-Mechanism/Hardware/`（Bootloader / Driver / HAL）
2. `01-Mechanism/Kernel/`（Linux Kernel 14 子系统）
3. `06-Foundation/Build-System/ + System-Integration/ + Dynamic-Updates/`
4. `05-Governance/OEM-BSP/`（OEM 视角）

## 📊 质量基线（本规范）

- 单篇 300 行（破例最多 1000+ 行）
- 9 项硬指标：本篇定位 / 校准决策日志 / 角色设定 / 写作标准 / 附录 A 源码索引 / 附录 B 路径对账【强制】/ 附录 C 量化自检 / 附录 D 工程基线 / 5 条 Takeaway
- 12 反例清单：无代码堆砌 / AI 自嗨 / 路径幻觉 / 版本混用 / 跨篇重复等
- 基线：AOSP 17 + 6.18

## 🗓️ 迁移路线图

| 阶段 | 内容 | 状态 |
|:----:|:-----|:----:|
| **阶段 1** | 创建 6 大分类 + 移动构建产物 + 移动新系列 | ✅ 完成 |
| **阶段 2** | 移动 AOSP_Startup / Runtime / Hook / Linux_Kernel 到 01-Mechanism/ | ✅ 完成 |
| **阶段 3** | 拆分 Stability/ 到 02-Symptom/ + 拆分 Stability-Forensics/ 到 03-Forensics/ + 拆分 7 大组件 + 清理兼容层（650 文件 / 19.18 MB 回收站）| ✅ 完成（2026-07-19）|

> **设计文档**：`00-Meta/引用矩阵.md`（包含完整的迁移映射表）

---

**作者**：Mavis · Stability Matrix Course  
**基线**：AOSP 17 + android17-6.18  
**最后更新**：2026-07-19（v3.0 目录重构）
