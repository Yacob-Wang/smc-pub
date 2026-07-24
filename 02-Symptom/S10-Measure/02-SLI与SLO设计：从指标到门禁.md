# S10-02 · 稳定性 SLI/SLO 设计：从指标到门禁的工程闭环

> **系列**：Stability S10-Measure · 02
>
> **位置**：S10-01（度量基础）→ **本篇（SLI/SLO 设计）** → S10-03（门禁 SOP）
>
> **基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18` LTS
>
> **完成时间**：2026-07-22（v1.0）

<!-- AUTHOR_ONLY:START -->

## 本篇定位

- S10 子系列的工程落地下篇（与 S10-01 配套）
- 强依赖：[S10-01](01-症状机制.md) / [学习路线 §7](../../00-Meta/学习路线-稳定性架构师.md)
- 衔接去：[S10-03 门禁 SOP](03-发布门禁SOP.md)

## 校准决策日志

| 轮次 | 决策 | 理由 |
|:-----|:-----|:-----|
| 1 | 单篇 350+ 行 | SLI/SLO 5 指标 + 4 阶段门禁 |
| 2 | 5 SLI 全给"分子分母 + 计算公式" | 反例 #4 |
| 3 | 删"建议"，改"必须" | 反例 #5 |

<!-- AUTHOR_ONLY:END -->

---

## 2. SLI 定义：5 个核心稳定性指标

> **铁律**：SLI = Service Level Indicator = **可测量的服务质量指标**
>
> 稳定性架构师只需要记 5 个 SLI，覆盖 90% 线上问题。

### 2.1 SLI 1 · 启动成功率

| 字段 | 定义 |
|:-----|:-----|
| **业务定义** | 用户点击 App 图标到首帧可见的成功率 |
| **分子** | 启动成功的事件数（首帧上屏 + 无 ANR/NE/REBOOT）|
| **分母** | 启动尝试事件数（含所有点击）|
| **采集点** | Application.onCreate / Activity.onResume / Choreographer.doFrame |
| **计算公式** | 启动成功率 = 首帧成功事件数 ÷ 启动尝试事件数 × 100% |
| **典型阈值** | ≥ 99.5% |
| **关联症状** | S11-Startup C01-C05 启动稳定性全系列 |
| **关联机制** | [S11-Startup A01 启动链路总览](../S11-Startup/A-启动机制/A01-启动链路总览.md) |

**代码示例（Java 层采集）**：

```java
// 在 Application.onCreate 起点 + 首帧后打点
public class StabilityApp extends Application {
    private long startTime;

    @Override
    public void onCreate() {
        super.onCreate();
        startTime = SystemClock.uptimeMillis();
    }

    // 在第一帧绘制后调用（BaseActivity.attachBaseContext 等）
    public void onFirstFrame() {
        long cost = SystemClock.uptimeMillis() - startTime;
        StabilityReporter.reportStart(cost, "success");
    }
}
```

### 2.2 SLI 2 · Java 崩溃率（JE 率）

| 字段 | 定义 |
|:-----|:-----|
| **业务定义** | 每个 Session 中发生 Java 异常崩溃的比例 |
| **分子** | 发生未捕获 Java 异常的 Session 数 |
| **分母** | 总 Session 数 |
| **采集点** | Thread.setDefaultUncaughtExceptionHandler + 退后台 |
| **计算公式** | Crash-free Session = 1 - (异常 Session ÷ 总 Session) × 100% |
| **典型阈值** | Crash-free Session ≥ 99.95%（即崩溃率 ≤ 0.05%）|
| **关联症状** | [S02-JE](../S02-JE/01-症状机制.md) |
| **关联机制** | [01-Mechanism/Runtime/ART/06-信号与ANR-Trace](../01-Mechanism/Runtime/ART/06-信号与ANR-Trace/01-SignalCatcher与信号机制.md) |

### 2.3 SLI 3 · Native 崩溃率（NE 率）

| 字段 | 定义 |
|:-----|:-----|
| **业务定义** | 每个 Session 中发生 Native 崩溃（tombstone）的比例 |
| **分子** | 发生 NE 异常（SIGSEGV/SIGABRT/SIGBUS 等）的 Session 数 |
| **分母** | 总 Session 数 |
| **采集点** | debuggerd 回调 / tombstone 落盘 |
| **计算公式** | Crash-free Session = 1 - (NE Session ÷ 总 Session) × 100% |
| **典型阈值** | Crash-free Session ≥ 99.9%（Native 容忍度低于 Java，因为更难复现）|
| **关联症状** | [S03-NE](../S03-NE/01-症状机制.md) |
| **关联取证** | [03-Forensics/F04-NE](../03-Forensics/F04-NE/01-取证机制.md) |

### 2.4 SLI 4 · ANR 率

| 字段 | 定义 |
|:-----|:-----|
| **业务定义** | 每个 Session 中发生 ANR（Input dispatch / Service / Broadcast）的比例 |
| **分子** | 发生 ANR 的 Session 数 |
| **分母** | 总 Session 数 |
| **采集点** | InputDispatcher 5s 超时 / Service 20s 超时 / Broadcast 10s 超时 |
| **计算公式** | ANR-free Session = 1 - (ANR Session ÷ 总 Session) × 100% |
| **典型阈值** | ANR-free Session ≥ 99.9% |
| **关联症状** | [S01-ANR](../S01-ANR/01-症状机制.md) |
| **关联机制** | [04-Tool/ANR-Detection 系列](../04-Tool/ANR-Detection/) |

### 2.5 SLI 5 · 后台存活率

| 字段 | 定义 |
|:-----|:-----|
| **业务定义** | App 退后台后被系统回收前能存活的比例 |
| **分子** | 退后台 5 分钟内仍存活的进程数 |
| **分母** | 退后台的进程总数 |
| **采集点** | ProcessList 监听 / adj 变化 / am force-stop 监听 |
| **计算公式** | 后台存活率 = 5min 仍存活 ÷ 总退后台 × 100% |
| **典型阈值** | ≥ 95%（Android 默认会杀后台）|
| **关联机制** | [01-Mechanism/Framework/Process 系列](../01-Mechanism/Framework/Process/) + [01-Mechanism/Kernel/Memory_Management/09](../01-Mechanism/Kernel/Memory_Management/09-杀进程决策子系统：LMKD-MemoryLimiter-的协同.md) |

### 2.6 5 大 SLI 速查表

| # | SLI | 关键数字 | 监控工具 | 治理文章 |
|:-:|:----|:---------|:---------|:---------|
| 1 | 启动成功率 | ≥ 99.5% | Choreographer + APM | [S11-Startup C 系列](../S11-Startup/) |
| 2 | Java 崩溃率 | ≤ 0.05% | UncaughtExceptionHandler | [S02-JE](../S02-JE/) |
| 3 | Native 崩溃率 | ≤ 0.1% | debuggerd | [S03-NE](../S03-NE/) |
| 4 | ANR 率 | ≤ 0.1% | ANR-Detection | [S01-ANR](../S01-ANR/) |
| 5 | 后台存活率 | ≥ 95% | ProcessList 监听 | [Memory 09](../01-Mechanism/Kernel/Memory_Management/09-杀进程决策子系统：LMKD-MemoryLimiter-的协同.md) |

---

## 3. SLO 设计：把 SLI 变成承诺

> **铁律**：SLO = Service Level Objective = **内部或外部对 SLI 的承诺值**
>
> 稳定性架构师 = 给 SLO 定数字 + 写进合同

### 3.1 SLO 三要素

```
SLI (可测量)  +  目标值 (99.95%)  +  时间窗口 (30 天)  =  SLO
```

### 3.2 5 大 SLI 的 SLO 阶梯

> **SLO 阶梯**：基础 / 行业 / 卓越 —— 基础是底线，行业是平均，卓越是头部

| SLI | 基础 SLO（底线）| 行业 SLO（平均）| 卓越 SLO（头部）| 适用产品 |
|:----|:----------------|:----------------|:----------------|:---------|
| 启动成功率 | 99% | 99.5% | 99.9% | 所有 App |
| Java 崩溃率 | ≤ 0.1% | ≤ 0.05% | ≤ 0.01% | 所有 App |
| Native 崩溃率 | ≤ 0.2% | ≤ 0.1% | ≤ 0.02% | 重 Native App |
| ANR 率 | ≤ 0.2% | ≤ 0.1% | ≤ 0.05% | 强交互 App |
| 后台存活率 | ≥ 90% | ≥ 95% | ≥ 98% | 工具/通信类 App |

### 3.3 SLO 时间窗口：选 30 天还是 90 天？

| 时间窗口 | 优点 | 缺点 | 推荐场景 |
|:---------|:-----|:-----|:---------|
| **7 天** | 灵敏 | 太抖动 | 灰度期 |
| **30 天** ✅ | 平衡 | 主流 | **默认推荐** |
| **90 天** | 稳定 | 太迟钝 | 关键承诺（如 SLA 合同）|

### 3.4 SLO 制定 4 步法

```
Step 1：测基线（看过去 30 天真实 SLI）
   ↓
Step 2：定目标（取基线 95% 分位 = 略高于现状）
   ↓
Step 3：写入契约（内部对产品/外部对客户）
   ↓
Step 4：定期 review（每季度 review 一次）
```

---

## 4. Error Budget：SLO 失败时的扣分机制

> **铁律**：Error Budget = **1 - SLO 目标值** 的可消耗余量
>
> 例：SLO = 99.9%，则 Error Budget = 0.1% = 每月 1000 次请求中允许 1 次失败

### 4.1 Error Budget 的 3 个核心动作

| 动作 | 触发条件 | 负责人 | 影响 |
|:-----|:---------|:-------|:-----|
| **扣分** | 线上 SLO 失败被记录 | 自动（APM）| 累计扣分 |
| **告警** | 消耗 ≥ 50% | oncall | 团队知晓 |
| **暂停变更** | 消耗 ≥ 100% | 架构师 | **冻结发版**，专项治理 |

### 4.2 Error Budget 实战模板

```
月份：2026-07
SLO：启动成功率 99.5%
Error Budget：0.5% × 30 天
消耗进度：
  Week 1：0.05%  （绿灯）
  Week 2：0.15%  （绿灯）
  Week 3：0.30%  （黄灯，告警）
  Week 4：0.48%  （红灯，接近耗尽）
  → 触发"暂停变更"，启动专项治理
```

### 4.3 Error Budget 用完怎么办？

**绝对不能做的 3 件事**：
- ❌ 改 SLO（把 99.5% 改成 99% 凑数）
- ❌ 改 SLI 计算口径（修改分子分母凑数据）
- ❌ 删除历史数据（"假装没发生"）

**必须做的 3 件事**：
- ✅ 冻结发版（停止所有 feature 变更）
- ✅ 启动专项治理（拉 P0 级 PM + Tech Lead + oncall）
- ✅ 输出 postmortem（写 [postmortem 模板](#6-postmortem-模板)）

---

## 5. 门禁 SOP：4 阶段发布守护神

> **铁律**：门禁 = **在发版前/中/后**自动检查 SLO 达成度，不通过则阻断

### 5.1 4 阶段门禁流程

```
   准入          准出          灰度          全量
   (Pre)         (Gate)        (Canary)      (GA)
   ↓             ↓             ↓             ↓
  代码准入      集成完成        1% / 10% / 50%   100%
  Lint + 单测   端到端测试       观察 SLO        持续观察
  + 静态扫描    + 性能基线     满足后放量       触发回滚则立即回
```

### 5.2 准入门禁（Pre-Gate）

| 检查项 | 工具 | 阈值 | 失败处理 |
|:-------|:-----|:-----|:---------|
| Lint 错误 | Android Lint | 0 error | 阻断 |
| 单元测试 | JUnit | 100% 通过 | 阻断 |
| 静态扫描 | SonarQube | 0 critical | 阻断 |
| Crash 关键字 | 自研脚本 | 0 命中 | 阻断 |
| 性能基线 | benchmark | < 1.05x 基线 | 警告 |

### 5.3 准出门禁（Gate）

| 检查项 | 工具 | 阈值 | 失败处理 |
|:-------|:-----|:-----|:---------|
| 端到端测试 | UI Automator | 100% 通过 | 阻断 |
| 兼容性测试 | Firebase Test Lab | 通过率 ≥ 95% | 阻断 |
| 启动时间 | Choreographer | ≤ 基线 × 1.1 | 阻断 |
| 内存基线 | LeakCanary | 0 leak | 警告 |
| 功耗基线 | Battery Historian | ≤ 基线 × 1.2 | 警告 |

### 5.4 灰度门禁（Canary Gate）

| 阶段 | 比例 | 观察时长 | 放行条件 | 回滚条件 |
|:-----|:----:|:--------:|:---------|:---------|
| **1% 灰度** | 1% | 24h | SLO 未恶化 | SLO 恶化 ≥ 10% 立即回滚 |
| **10% 灰度** | 10% | 48h | 启动/ANR/NE 三项 SLO 持平 | 任一 SLO 恶化 ≥ 5% 回滚 |
| **50% 灰度** | 50% | 72h | 全量 SLO 持平 | 全量 SLO 恶化 ≥ 3% 回滚 |
| **全量** | 100% | 持续 | 维持 | Error Budget 耗尽则冻结 |

### 5.5 自动回滚（最关键）

```
监控检测到 SLO 恶化
   ↓ (30 秒内自动触发)
自动回滚到上一个稳定版本
   ↓
告警 oncall + Tech Lead
   ↓
72h 内出 postmortem
```

**强制要求**：每个发布必须支持**一键回滚**（< 5 分钟回滚完成）。

---

## 6. postmortem 模板

> **postmortem = 故障复盘文档** = 不追责，只为下次不犯

### 6.1 标准模板

```markdown
# Postmortem · [故障标题]

## TL;DR
- 故障时间：[开始时间] ~ [结束时间]
- 影响范围：[用户数 / 比例]
- 根因：[一句话总结]
- SLO 影响：[哪个 SLI 触线 / Error Budget 消耗 %]

## 时间线
- HH:MM 监控告警触发
- HH:MM oncall 介入
- HH:MM 定位根因
- HH:MM 启动回滚
- HH:MM 恢复完成
- HH:MM 完整恢复

## 根因分析（5 Whys）
- Why 1：[第一层]
- Why 2：[第二层]
- Why 3：[第三层]
- Why 4：[第四层]
- Why 5：[根本原因]

## 损失评估
- 业务影响：[订单损失 / 用户投诉]
- SLO 影响：[Error Budget 消耗]
- 团队影响：[oncall 时长 / 心理影响]

## 改进措施（Action Items）
- [ ] 短期：72h 内 [P0 项]
- [ ] 中期：2 周内 [P1 项]
- [ ] 长期：本季度 [P2 项]
- [ ] 永久：自动化门禁 [P3 项]

## 经验教训
- 做对了：[N 项]
- 做错了：[N 项]
- 学到的：[N 项]
```

### 6.2 文化红线（绝对不能犯）

- ❌ **追责个人**：postmortem 是"对事不对人"，目的是改进流程
- ❌ **隐瞒问题**：小问题不报 = 下次变成大问题
- ❌ **不写 postmortem**：所有 SLO 触线必须有 postmortem
- ❌ **只写不改**：Action Items 必须有 owner + deadline

---

## 7. 行业基线（参考数据 2026）

> **注意**：行业数据持续变化，本数据基于 2026 Q2 公开数据

| 维度 | 国内大厂 | 海外大厂 | 来源 |
|:-----|:---------|:---------|:-----|
| 启动成功率 | 99.5-99.8% | 99.7-99.95% | 公开演讲 |
| Crash-free Session | 99.9-99.95% | 99.95-99.99% | 公开演讲 |
| ANR-free Session | 99.85-99.95% | 99.9-99.99% | Google Firebase |
| 后台存活率 | 80-95% | 85-95% | 自测 |

> **稳定性架构师必须**定期拉一次自家数据和行业基线对比，发现差距 = 治理机会。

---

## 8. 与 smc-pub 其他系列的对接

| 本篇概念 | 已有内容 | 引用 |
|:---------|:---------|:-----|
| 启动 SLI | [S11-Startup A01](../S11-Startup/A-启动机制/A01-启动链路总览.md) | 启动机制 |
| 启动 SLI | [S11-Startup B01-B04](../S11-Startup/B-启动性能/) | 启动性能 |
| 启动 SLI | [S11-Startup C01-C05](../S11-Startup/C-启动稳定性/) | 启动稳定性 |
| 崩溃 SLI | [S02-JE](../S02-JE/01-症状机制.md) / [S03-NE](../S03-NE/01-症状机制.md) | 症状机制 |
| ANR SLI | [S01-ANR](../S01-ANR/01-症状机制.md) / [ANR-Detection](../04-Tool/ANR-Detection/) | 症状 + 工具 |
| 后台 SLI | [Memory 09](../01-Mechanism/Kernel/Memory_Management/09-杀进程决策子系统：LMKD-MemoryLimiter-的协同.md) | 杀进程机制 |
| 治理体系 | [S10-01 症状机制](01-症状机制.md) | 度量基础 |
| 治理体系 | [F07-Governance](../03-Forensics/F07-Governance/01-取证机制.md) | 取证治理 |
| 治理体系 | [APM A01](../../05-Governance/APM/A01-APM体系总览.md) | APM 总览 |
| AI 辅助 | [AI for Stability F01-F06](../../05-Governance/AI-Native/03_AI_for_Stability/) | AI 治理 |

---

## 9. 5 条 Takeaway

1. **5 个核心 SLI 必须立住**：启动成功率 / Java 崩溃率 / Native 崩溃率 / ANR 率 / 后台存活率 —— 5 个数字就是稳定性架构师的"仪表盘"
2. **SLO 必须给具体数字**：99.x% 是底线，30 天窗口是默认，季度 review 是制度
3. **Error Budget 是 SLO 的刹车**：消耗 50% 告警，100% 冻结发版 —— 不能改 SLO 凑数
4. **4 阶段门禁是工程的护城河**：准入 → 准出 → 灰度 → 全量，每一关都不能省
5. **postmortem 是文化的基石**：不追责、必须写、Action Items 必须 owner+deadline —— 三条铁律缺一不可

---

## 10. 附录

### 附录 A：源码索引

| 模块 | 路径 | 关键类/方法 |
|:-----|:-----|:-------------|
| APM 上报 | 04-Tool/AmCommand/06 | StabilityReporter |
| ANR 检测 | 04-Tool/ANR-Detection/01 | InputDispatcher |
| NE 检测 | 01-Mechanism/Runtime/Native_Crash/04 | debuggerd |
| 启动耗时 | 02-Symptom/S11-Startup/B-启动性能 | Choreographer |

### 附录 B：路径对账

无新增模块（纯治理方法论）。

### 附录 C：量化自检

- 5 个核心 SLI 全部给出分子分母 ✅
- 5 个核心 SLI 全部给出计算公式 ✅
- 5 个 SLO 阶梯全部给出 3 档目标值 ✅
- 4 阶段门禁全部给出检查项 + 阈值 + 失败处理 ✅
- 3 个 Error Budget 核心动作全部给出 ✅

### 附录 D：工程基线

- AOSP 17.0.0_r1（API 37）
- Linux android17-6.18 LTS
- 工具链：apkanalyzer + Perfetto + Choreographer
- 监控栈：[05-Governance/APM](../../05-Governance/APM/)（待补完整）

---

**作者**：Mavis · Stability Matrix Course
**基线**：AOSP 17 + android17-6.18
**最后更新**：2026-07-22（v1.0）
