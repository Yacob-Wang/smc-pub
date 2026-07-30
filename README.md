# smc-pub · 稳知库

> **Stability Matrix Course** —— 面向 Android 稳定性架构师的端到端知识库
>
> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS）
>
> **在线站点**：[https://yacob-wang.github.io/smc-pub/](https://yacob-wang.github.io/smc-pub/)
>
> 正文约 **<!-- CATALOG-TOTAL:START -->570<!-- CATALOG-TOTAL:END -->** 篇（由脚本统计）

---

## 项目定位

**smc-pub（稳知库）** 按双轴组织 Android 稳定性 / 性能 / 工具 / 案例内容：

- **机制轴**：Hardware → Kernel → Runtime → Framework → App（对齐 AOSP 分层）
- **工作流轴**：症状 → 取证 → 工具 → 治理 → 案例 → 基础（对齐 oncall 日常）

适合稳定性架构师、性能工程师、oncall、BSP / 系统集成工程师按角色选读。

## 怎么找到文章

文章太多时，不要一个个点目录。推荐路径：

1. 先看下面的 **一级模块总览** 和 **二级系列索引**，定位到系列文件夹
2. 需要一次扫完全库正文时，打开 **[文章总目录.md](文章总目录.md)**（一级 → 二级 → 三级表格，均可跳转）
3. 或使用站点搜索：[稳知库](https://yacob-wang.github.io/smc-pub/)

更新目录（新增/移动文章后）：

```bash
py -3.12 00-Meta/scripts/generate_article_catalog.py
```

## 一级模块总览

<!-- CATALOG-STATS:START -->

| 一级模块 | 角色 | 二级系列 | 文章数 | 目录 |
|:---------|:-----|--------:|-------:|:-----|
| **00-Meta** | 学习路线 · 阅读指南 · JD 匹配 · 缺口一览 · Reference | 3 | 24 | [00-Meta/](00-Meta/) |
| **01-Mechanism** | Hardware · Kernel · Runtime · Framework · App | 37 | 322 | [01-Mechanism/](01-Mechanism/) |
| **02-Symptom** | 11 大症状机制（ANR · JE · NE · SWT · HANG · REBOOT · KE 等） | 15 | 34 | [02-Symptom/](02-Symptom/) |
| **03-Forensics** | 8 大取证链（与症状编号一一对应） | 10 | 21 | [03-Forensics/](03-Forensics/) |
| **04-Tool** | Dumpsys · Watchdog · Perfetto · Hprof · AmCommand · ANR-Detection | 7 | 42 | [04-Tool/](04-Tool/) |
| **05-Governance** | APM · OEM-BSP · 跨平台 · 低端机 · AI Native · AI-Debug · 性能内存 · 安全 | 5 | 42 | [05-Governance/](05-Governance/) |
| **06-Case** | 启动场景案例 + 跨系列实战 | 2 | 11 | [06-Case/](06-Case/) |
| **06-Foundation** | Build-System · System-Integration · Dynamic-Updates · Tools | 14 | 74 | [06-Foundation/](06-Foundation/) |
| **合计** | | | **570** | [文章总目录](文章总目录.md) |

<!-- CATALOG-STATS:END -->

## 二级系列索引

每个系列对应一组正文；点目录进入后按文件名序号阅读。全量三级正文见 [文章总目录.md](文章总目录.md)。

<!-- CATALOG-SERIES:START -->

### 00-Meta · 元信息 / 地图

| 二级系列 | 文章数 | 目录 |
|:---------|-------:|:-----|
| （模块根） | 9 | [00-Meta/](00-Meta/) |
| Industry-Benchmark | 4 | [00-Meta/Industry-Benchmark/](00-Meta/Industry-Benchmark/) |
| Reference | 11 | [00-Meta/Reference/](00-Meta/Reference/) |

### 01-Mechanism · 机制（AOSP 分层）

| 二级系列 | 文章数 | 目录 |
|:---------|-------:|:-----|
| App / Handler-MessageQueue-Looper / Handler_MessageQueue_Looper | 11 | [01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/](01-Mechanism/App/Handler-MessageQueue-Looper/Handler_MessageQueue_Looper/) |
| App / Hook | 15 | [01-Mechanism/App/Hook/](01-Mechanism/App/Hook/) |
| Framework / Activity | 9 | [01-Mechanism/Framework/Activity/](01-Mechanism/Framework/Activity/) |
| Framework / Broadcast | 9 | [01-Mechanism/Framework/Broadcast/](01-Mechanism/Framework/Broadcast/) |
| Framework / ContentProvider | 9 | [01-Mechanism/Framework/ContentProvider/](01-Mechanism/Framework/ContentProvider/) |
| Framework / Input | 8 | [01-Mechanism/Framework/Input/](01-Mechanism/Framework/Input/) |
| Framework / Memory_Management | 11 | [01-Mechanism/Framework/Memory_Management/](01-Mechanism/Framework/Memory_Management/) |
| Framework / Process | 9 | [01-Mechanism/Framework/Process/](01-Mechanism/Framework/Process/) |
| Framework / Process_Exit | 4 | [01-Mechanism/Framework/Process_Exit/](01-Mechanism/Framework/Process_Exit/) |
| Framework / Service | 9 | [01-Mechanism/Framework/Service/](01-Mechanism/Framework/Service/) |
| Framework / Window | 11 | [01-Mechanism/Framework/Window/](01-Mechanism/Framework/Window/) |
| Hardware | 1 | [01-Mechanism/Hardware/](01-Mechanism/Hardware/) |
| Kernel / Binder | 13 | [01-Mechanism/Kernel/Binder/](01-Mechanism/Kernel/Binder/) |
| Kernel / cgroup | 6 | [01-Mechanism/Kernel/cgroup/](01-Mechanism/Kernel/cgroup/) |
| Kernel / DM | 10 | [01-Mechanism/Kernel/DM/](01-Mechanism/Kernel/DM/) |
| Kernel / epoll | 1 | [01-Mechanism/Kernel/epoll/](01-Mechanism/Kernel/epoll/) |
| Kernel / FileSystem | 26 | [01-Mechanism/Kernel/FileSystem/](01-Mechanism/Kernel/FileSystem/) |
| Kernel / GKI | 13 | [01-Mechanism/Kernel/GKI/](01-Mechanism/Kernel/GKI/) |
| Kernel / Input_Driver | 19 | [01-Mechanism/Kernel/Input_Driver/](01-Mechanism/Kernel/Input_Driver/) |
| Kernel / Interrupt | 7 | [01-Mechanism/Kernel/Interrupt/](01-Mechanism/Kernel/Interrupt/) |
| Kernel / IO | 11 | [01-Mechanism/Kernel/IO/](01-Mechanism/Kernel/IO/) |
| Kernel / Memory_Management | 15 | [01-Mechanism/Kernel/Memory_Management/](01-Mechanism/Kernel/Memory_Management/) |
| Kernel / Partition | 8 | [01-Mechanism/Kernel/Partition/](01-Mechanism/Kernel/Partition/) |
| Kernel / Process | 14 | [01-Mechanism/Kernel/Process/](01-Mechanism/Kernel/Process/) |
| Kernel / Program_Execution | 14 | [01-Mechanism/Kernel/Program_Execution/](01-Mechanism/Kernel/Program_Execution/) |
| Kernel / socket | 8 | [01-Mechanism/Kernel/socket/](01-Mechanism/Kernel/socket/) |
| Kernel / Syscalls | 12 | [01-Mechanism/Kernel/Syscalls/](01-Mechanism/Kernel/Syscalls/) |
| Runtime / ART / 00-总览 | 2 | [01-Mechanism/Runtime/ART/00-总览/](01-Mechanism/Runtime/ART/00-总览/) |
| Runtime / ART / 01-字节码与指令集 | 2 | [01-Mechanism/Runtime/ART/01-字节码与指令集/](01-Mechanism/Runtime/ART/01-字节码与指令集/) |
| Runtime / ART / 02-编译与执行 | 2 | [01-Mechanism/Runtime/ART/02-编译与执行/](01-Mechanism/Runtime/ART/02-编译与执行/) |
| Runtime / ART / 03-GC系统 | 11 | [01-Mechanism/Runtime/ART/03-GC系统/](01-Mechanism/Runtime/ART/03-GC系统/) |
| Runtime / ART / 03-类加载与链接 | 2 | [01-Mechanism/Runtime/ART/03-类加载与链接/](01-Mechanism/Runtime/ART/03-类加载与链接/) |
| Runtime / ART / 05-JNI | 2 | [01-Mechanism/Runtime/ART/05-JNI/](01-Mechanism/Runtime/ART/05-JNI/) |
| Runtime / ART / 06-信号与ANR-Trace | 3 | [01-Mechanism/Runtime/ART/06-信号与ANR-Trace/](01-Mechanism/Runtime/ART/06-信号与ANR-Trace/) |
| Runtime / ART / 07-启动流程 | 2 | [01-Mechanism/Runtime/ART/07-启动流程/](01-Mechanism/Runtime/ART/07-启动流程/) |
| Runtime / ART / 08-对比与演进 | 5 | [01-Mechanism/Runtime/ART/08-对比与演进/](01-Mechanism/Runtime/ART/08-对比与演进/) |
| Runtime / Native_Crash | 8 | [01-Mechanism/Runtime/Native_Crash/](01-Mechanism/Runtime/Native_Crash/) |

### 02-Symptom · 症状

| 二级系列 | 文章数 | 目录 |
|:---------|-------:|:-----|
| （模块根） | 1 | [02-Symptom/](02-Symptom/) |
| S01-ANR | 1 | [02-Symptom/S01-ANR/](02-Symptom/S01-ANR/) |
| S02-JE | 1 | [02-Symptom/S02-JE/](02-Symptom/S02-JE/) |
| S03-NE | 1 | [02-Symptom/S03-NE/](02-Symptom/S03-NE/) |
| S04-SWT | 1 | [02-Symptom/S04-SWT/](02-Symptom/S04-SWT/) |
| S05-HANG | 1 | [02-Symptom/S05-HANG/](02-Symptom/S05-HANG/) |
| S06-REBOOT | 1 | [02-Symptom/S06-REBOOT/](02-Symptom/S06-REBOOT/) |
| S07-KE | 1 | [02-Symptom/S07-KE/](02-Symptom/S07-KE/) |
| S08-AOSP17-K618 | 1 | [02-Symptom/S08-AOSP17-K618/](02-Symptom/S08-AOSP17-K618/) |
| S09-PerfVsStab | 1 | [02-Symptom/S09-PerfVsStab/](02-Symptom/S09-PerfVsStab/) |
| S10-Measure | 5 | [02-Symptom/S10-Measure/](02-Symptom/S10-Measure/) |
| S11-Startup / A-启动机制 | 6 | [02-Symptom/S11-Startup/A-启动机制/](02-Symptom/S11-Startup/A-启动机制/) |
| S11-Startup / B-启动性能 | 4 | [02-Symptom/S11-Startup/B-启动性能/](02-Symptom/S11-Startup/B-启动性能/) |
| S11-Startup / C-启动稳定性 | 5 | [02-Symptom/S11-Startup/C-启动稳定性/](02-Symptom/S11-Startup/C-启动稳定性/) |
| S11-Startup / D-启动工具 | 4 | [02-Symptom/S11-Startup/D-启动工具/](02-Symptom/S11-Startup/D-启动工具/) |

### 03-Forensics · 取证

| 二级系列 | 文章数 | 目录 |
|:---------|-------:|:-----|
| F00-Overview | 1 | [03-Forensics/F00-Overview/](03-Forensics/F00-Overview/) |
| F01-ANR | 1 | [03-Forensics/F01-ANR/](03-Forensics/F01-ANR/) |
| F02-SWT | 1 | [03-Forensics/F02-SWT/](03-Forensics/F02-SWT/) |
| F03-JE | 1 | [03-Forensics/F03-JE/](03-Forensics/F03-JE/) |
| F04-NE | 1 | [03-Forensics/F04-NE/](03-Forensics/F04-NE/) |
| F05-KE | 1 | [03-Forensics/F05-KE/](03-Forensics/F05-KE/) |
| F06-HANG-OOM | 1 | [03-Forensics/F06-HANG-OOM/](03-Forensics/F06-HANG-OOM/) |
| F07-Governance | 1 | [03-Forensics/F07-Governance/](03-Forensics/F07-Governance/) |
| Bugreport | 5 | [03-Forensics/Bugreport/](03-Forensics/Bugreport/) |
| Oncall | 8 | [03-Forensics/Oncall/](03-Forensics/Oncall/) |

### 04-Tool · 工具

| 二级系列 | 文章数 | 目录 |
|:---------|-------:|:-----|
| AmCommand | 6 | [04-Tool/AmCommand/](04-Tool/AmCommand/) |
| AmCommand / am_command_configs | 3 | [04-Tool/AmCommand/am_command_configs/](04-Tool/AmCommand/am_command_configs/) |
| ANR-Detection | 3 | [04-Tool/ANR-Detection/](04-Tool/ANR-Detection/) |
| Dumpsys | 12 | [04-Tool/Dumpsys/](04-Tool/Dumpsys/) |
| Hprof | 5 | [04-Tool/Hprof/](04-Tool/Hprof/) |
| Perfetto | 5 | [04-Tool/Perfetto/](04-Tool/Perfetto/) |
| Watchdog | 8 | [04-Tool/Watchdog/](04-Tool/Watchdog/) |

### 05-Governance · 治理

| 二级系列 | 文章数 | 目录 |
|:---------|-------:|:-----|
| AI-Native / 01_AI_Native_Runtime | 8 | [05-Governance/AI-Native/01_AI_Native_Runtime/](05-Governance/AI-Native/01_AI_Native_Runtime/) |
| AI-Native / 02_AI_Native_OS | 6 | [05-Governance/AI-Native/02_AI_Native_OS/](05-Governance/AI-Native/02_AI_Native_OS/) |
| AI-Native / 03_AI_for_Stability | 6 | [05-Governance/AI-Native/03_AI_for_Stability/](05-Governance/AI-Native/03_AI_for_Stability/) |
| AI-Native / 04_AI_Engineering | 12 | [05-Governance/AI-Native/04_AI_Engineering/](05-Governance/AI-Native/04_AI_Engineering/) |
| APM | 10 | [05-Governance/APM/](05-Governance/APM/) |

### 06-Case · 案例

| 二级系列 | 文章数 | 目录 |
|:---------|-------:|:-----|
| Cases-Extended | 8 | [06-Case/Cases-Extended/](06-Case/Cases-Extended/) |
| Startup | 3 | [06-Case/Startup/](06-Case/Startup/) |

### 06-Foundation · 基础

| 二级系列 | 文章数 | 目录 |
|:---------|-------:|:-----|
| Build-System | 12 | [06-Foundation/Build-System/](06-Foundation/Build-System/) |
| Build-System / Soong | 8 | [06-Foundation/Build-System/Soong/](06-Foundation/Build-System/Soong/) |
| Dynamic-Updates | 4 | [06-Foundation/Dynamic-Updates/](06-Foundation/Dynamic-Updates/) |
| Graphics | 7 | [06-Foundation/Graphics/](06-Foundation/Graphics/) |
| Network | 8 | [06-Foundation/Network/](06-Foundation/Network/) |
| Power | 4 | [06-Foundation/Power/](06-Foundation/Power/) |
| SELinux | 8 | [06-Foundation/SELinux/](06-Foundation/SELinux/) |
| System-Integration | 3 | [06-Foundation/System-Integration/](06-Foundation/System-Integration/) |
| Tools / Android_Tools | 6 | [06-Foundation/Tools/Android_Tools/](06-Foundation/Tools/Android_Tools/) |
| Tools / Filesystem-Cheat-Sheet | 1 | [06-Foundation/Tools/Filesystem-Cheat-Sheet/](06-Foundation/Tools/Filesystem-Cheat-Sheet/) |
| Tools / Filesystem-Cheat-Sheet / 01- | 1 | [06-Foundation/Tools/Filesystem-Cheat-Sheet/01-/](06-Foundation/Tools/Filesystem-Cheat-Sheet/01-/) |
| Tools / Git_Mastery | 5 | [06-Foundation/Tools/Git_Mastery/](06-Foundation/Tools/Git_Mastery/) |
| Tools / Memory_Analysis | 1 | [06-Foundation/Tools/Memory_Analysis/](06-Foundation/Tools/Memory_Analysis/) |
| Tools / Tracing | 6 | [06-Foundation/Tools/Tracing/](06-Foundation/Tools/Tracing/) |

<!-- CATALOG-SERIES:END -->

## 双轴设计

```
机制 (AOSP 分层)          症状    取证    工具    治理    案例    基础
┌──────────────┐         S01…   F00…   dumpsys  APM    E01…   Build
│ Hardware     │         ANR    ANR    Perfetto OEM    启动   SELinux
│ Kernel       │         JE     SWT    Hprof    AI…           Network
│ Runtime/ART  │         …      …      …
│ Framework    │
│ App          │
└──────────────┘
```

## 推荐阅读路径

| 角色 | 入口 |
|:-----|:-----|
| 所有人 | [`00-Meta/学习路线-稳定性架构师.md`](00-Meta/学习路线-稳定性架构师.md) |
| 通用开发者 | [`01-Mechanism/`](01-Mechanism/) → Framework / ART |
| 稳定性架构师 | [`02-Symptom/`](02-Symptom/) → [`03-Forensics/`](03-Forensics/) → [`05-Governance/APM/`](05-Governance/APM/) |
| oncall | 症状 → 取证 → [`04-Tool/`](04-Tool/) |
| BSP / 系统集成 | [`01-Mechanism/Kernel/`](01-Mechanism/Kernel/) → [`06-Foundation/`](06-Foundation/) |

跨系列引用见 [`00-Meta/引用矩阵.md`](00-Meta/引用矩阵.md)。

## 本地预览站点

```bash
pip install -r 00-Meta/scripts/requirements-docs.txt
py -3.12 00-Meta/scripts/generate_article_catalog.py
py -3.12 00-Meta/scripts/prepare_web_docs.py
mkdocs serve
```

`docs/` 由脚本生成，请勿手改。

## 质量约定

- 源码基线：AOSP 17 + android17-6.18
- 正文以文首 `#` 标题为准；系列内 `NN-标题.md` 递进
- 写作规范见仓库根目录 `PROMPT-技术系列文章写作指南.md`（作者向，不进站点）

---

**作者**：JacobKing · Stability Matrix Course  
**仓库**：[yacob-wang/smc-pub](https://github.com/yacob-wang/smc-pub)
