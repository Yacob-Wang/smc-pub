# 附录 D：工程基线（验收标准 + 检查清单 + 工具链 · v2 升级版）

> **本子模块**：03-GC 系统 / 09-GC 诊断与治理（诊断与治理 · 附录 D）
> **本附录定位**：**GC 诊断与治理的工程基线**——验收标准、部署检查清单、工具链依赖、监控告警配置、应急响应 SOP
> **基线版本**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`（6.18 LTS，2024-11-17 发布，EOL 2026-12）
> **v2 升级日期**：2026-07-18（v1 旧文按 v4 规范 + 新基线升级）

---

## 0. 本附录定位声明

| 维度 | 本附录承担 | 本附录不涉及 |
| :--- | :--- | :--- |
| 验收基线 | ✓ D.1 ~ D.2 | — |
| 监控基线 | ✓ D.3 | — |
| 应急基线 | ✓ D.4 | — |
| 工具基线 | ✓ D.5 | — |
| 性能基线 | ✓ D.6 | — |
| 培训基线 | ✓ D.7 | — |
| 持续改进基线 | ✓ D.8 | — |
| **AOSP 17 + Linux 6.18 增补基线** | ✓ **D.9**（GenCC + LeakCanary 3.x + MAT 1.14.0+ + Linux 6.18 sheaves/io_uring） | — |
| 源码索引 | — | [A-源码索引](A-源码索引.md)（v2 升级版） |
| 路径对账 | — | [B-路径对账](B-路径对账.md)（v2 升级版） |

**承接自**：本附录承接 [A-源码索引](A-源码索引.md) + [B-路径对账](B-路径对账.md)——A/B 提供"理论 + 路径"，D 提供"工程实施标准"。

**衔接去**：本附录是本子模块的最后一篇——读完 D 后可直接进入 [10-ART17分代GC强化专章 v2](../../03-GC系统/10-ART17分代GC强化专章-v2.md) 专章。

---

## 校准决策日志（v2 升级 · 3 轮全跑）

### 第 1 轮：结构校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| v1 旧稿标记段 | 在（顶部 14 行） | **删**（v1 → v2 实质升级） | 内容已按 v4 规范重写，标记段失效 |
| 本附录定位声明 | 无 | **新增**（v4 §3 强制要求） | v1 后期已按 v4 写但缺本附录定位段 |
| 衔接去 | 无 | **新增 2 附录**（A-源码索引 + B-路径对账） | 跨附录引用矩阵要求显式关联 |
| 4 附录 | A/B/D 完整 | A/B/C/D 完整 | v4 §4.6 强制要求 |

### 第 2 轮：硬伤校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 基线版本号 | AOSP 14 / Linux 5.10 | AOSP 17 / **Linux 6.18** | **2026-07-18 基线升级 |
| API 等级 | API 34 | **API 37** | 与 AOSP 17 配套 |
| **AOSP 17 增补基线未覆盖** | D.1 ~ D.8 | **新增 D.9（AOSP 17 + Linux 6.18 完整增补）** | v2 硬性要求 |
| LeakCanary 2.14 | 已列出 | **必须升级 3.x** | AOSP 17 适配 |
| MAT 1.13.0 | 已列出 | **必须升级 1.14.0+** | AOSP 17 适配 |

### 第 3 轮：锐度校准

| 检查项 | 调整前 | 调整后 | 决策理由 |
| :--- | :--- | :--- | :--- |
| 原有 D.1 ~ D.8 内容 | 完整 | **保留全部 + 加 AOSP 17 注释** | v1 精华保留 |
| 性能基线数值 | AOSP 14 时代 | **增补 AOSP 17 新数值** | GenCC 暂停 < 1ms |
| 工具基线版本 | 旧版本 | **强制升级版本** | AOSP 17 适配 |
| 量化自检 | 无 | **附录 C 量化数据自检表（新增 12 条）** | v2 量化要求 |

---

## D.1 工程基线概述

### D.1.1 什么是工程基线

```
工程基线（Engineering Baseline）：

- 工程实施的标准基线
- 包括：验收标准、检查清单、工具链、监控告警、应急 SOP
- 用于：
  1. 部署前验收
  2. 部署后检查
  3. 运维时参考
  4. 应急时执行

【v2 升级】AOSP 17 工程基线：
- 增加：GenCC + 类去重 + Finalizer 池化 + Hprof 新元数据 + ART 内部状态 API
- 修正：基线版本（AOSP 14 → AOSP 17 + android17-6.18）
- 升级：工具版本（LeakCanary 2.x → 3.x / MAT 1.13 → 1.14.0+）
```

### D.1.2 工程基线分类

```
工程基线分类：

1. 验收基线：部署前的标准（D.2）
2. 监控基线：部署后的持续监控（D.3）
3. 应急基线：问题发生时的 SOP（D.4）
4. 工具基线：使用的工具链（D.5）
5. 性能基线：性能指标的标准（D.6）
6. 培训基线：团队能力建设（D.7）
7. 持续改进基线：长期优化方向（D.8）
8.【v2 新增】AOSP 17 增补基线（D.9）
```

---

## D.2 验收基线

### D.2.1 验收标准

```
GC 诊断治理验收标准（AOSP 17 强化版）：

1. 工具链
   - [ ] dumpsys meminfo 能在测试环境跑通
   - [ ] 【AOSP 17】dumpsys meminfo -d 能输出 ART 内部状态
   - [ ] 【AOSP 17】dumpsys meminfo -d 显示软阈值状态（kSoftThresholdPercent=30%）
   - [ ] procrank / smaps 能获取详细信息
   - [ ] 【Linux 6.18】smaps_rollup 能快速汇总
   - [ ] 【AOSP 17】LeakCanary 3.x（必须 3.x）能自动检测泄漏
   - [ ] 【AOSP 17】MAT 1.14.0+（必须 1.14+）能打开和解析 hprof
   - [ ] 【AOSP 17】MAT 能正确解析 Class Extent 元数据
   - [ ] Perfetto 能抓取和查看 trace
   - [ ] JVMTI SDK 能编译和集成

2. 监控
   - [ ] GC 频率指标能上报
   - [ ] GC 时长指标能上报
   - [ ] 【AOSP 17】Young/Old 代分代指标能上报
   - [ ] 【AOSP 17】JNI refs 指标能上报
   - [ ] 【AOSP 17】Distance to soft threshold 指标能上报
   - [ ] 堆水位指标能上报
   - [ ] 告警规则能触发
   - [ ] 仪表盘能展示

3. 治理（AOSP 17 调整阈值）
   - [ ] 【AOSP 17】GC 频率 < 50 次/分钟（静止，含 Young GC）
   - [ ] 【AOSP 17】Young GC 暂停 p95 < 1ms
   - [ ] 【AOSP 17】Full GC 暂停 p95 < 16ms
   - [ ] 【AOSP 17】Distance to soft threshold > 5%
   - [ ] 堆使用率 < 80%
   - [ ] OOM 频率 < 1 次/千次启动
   - [ ] 内存泄漏检测覆盖率 > 90%

4. 应急
   - [ ] 长 STW 应急 SOP 完备
   - [ ] OOM 应急 SOP 完备
   - [ ] 内存泄漏应急 SOP 完备
   - [ ] 应急联系人和流程明确
```

### D.2.2 部署前检查

```
部署前检查清单（AOSP 17 强化版）：

□ 代码检查
  - [ ] 无静态引用 Activity（用 Application Context 替代）
  - [ ] 无 finalizer 滥用（用 AutoCloseable 替代）
  - [ ] WeakReference 使用规范
  - [ ] 资源释放（Bitmap / Cursor / File）
  - [ ]【AOSP 17】JNI 配对使用（NewGlobalRef / DeleteGlobalRef）

□ 编译检查
  - [ ] 【AOSP 17】LeakCanary 3.x（必须 3.x）仅 debug 启用
  - [ ] APM SDK release 启用
  - [ ] 无 Native 内存泄漏
  - [ ] 【AOSP 17】适配类去重（LeakCanary 3.x + AndroidObjectInspectors）

□ 测试检查
  - [ ] LeakCanary 测试通过
  - [ ] LeakCanary Android Test 集成
  - [ ] 压测无 OOM
  - [ ] 【AOSP 17】GC 频率在阈值内（Young GC < 50 次/分钟）
  - [ ] 【AOSP 17】Young GC 暂停 < 1ms
  - [ ] 【AOSP 17】MAT 1.14.0+ 能正确解析 hprof

□ 监控检查
  - [ ] 上报接口连通
  - [ ] 【AOSP 17】ART 内部状态 API 集成
  - [ ] 告警规则生效
  - [ ] 仪表盘可访问

□ 应急检查
  - [ ] 应急 SOP 文档完备
  - [ ] 应急联系人明确
  - [ ] 回滚方案就绪
```

### D.2.3 部署后验证

```
部署后验证清单：

□ 功能验证
  - [ ] App 正常启动
  - [ ] App 正常使用
  - [ ] 监控数据正常上报
  - [ ] 【AOSP 17】ART 内部状态正常上报
  - [ ] 告警正常触发

□ 性能验证
  - [ ] 启动时间在标准内
  - [ ] 滑动帧率达标
  - [ ] 【AOSP 17】Young GC 暂停 < 1ms
  - [ ] 【AOSP 17】Full GC 暂停 < 16ms
  - [ ] 【AOSP 17】Distance to soft threshold > 5%
  - [ ] 内存使用稳定

□ 监控验证
  - [ ] 数据上报完整
  - [ ] 【AOSP 17】ART 内部状态完整
  - [ ] 告警规则触发
  - [ ] 仪表盘数据正确

□ 应急验证
  - [ ] 应急 SOP 可执行
  - [ ] 回滚方案可执行
  - 应急响应时间达标
```

---

## D.3 监控基线

### D.3.1 监控指标基线（AOSP 17 强化版）

```
GC 监控指标基线（AOSP 17 强化版）：

1. GC 频率（AOSP 17 调整）
   - 静止应用：< 5 次/分钟（含 Young GC）
   - 轻度使用：5-20 次/分钟
   - 重度使用：20-50 次/分钟
   - 警戒阈值：50 次/分钟
   - 告警阈值：100 次/分钟
   - 紧急阈值：200 次/分钟

2.【AOSP 17 新增】Young/Old 代分代
   - Young GC 频率：< 50 次/分钟（正常）
   - Old GC 频率：< 1 次/分钟（正常）
   - 警戒：Old GC > 5 次/分钟
   - 告警：Old GC > 10 次/分钟

3. GC 时长（AOSP 17 调整）
   -【AOSP 17】Young GC STW 平均：< 1ms
   -【AOSP 17】Young GC STW p95：< 1ms
   -【AOSP 17】Young GC STW p99：< 2ms
   -【AOSP 17】Full GC STW 平均：< 5ms
   -【AOSP 17】Full GC STW p95：< 16ms
   -【AOSP 17】Full GC STW p99：< 50ms
   - 紧急阈值：> 100ms（最大）

4.【AOSP 17 新增】软阈值状态
   - Distance to soft threshold > 5%：正常
   - Distance to soft threshold 0-5%：警戒
   - Distance to soft threshold < 0%：已越过
   - Distance to soft threshold < -10%：严重

5.【AOSP 17 新增】JNI refs
   - Global refs < 500：正常
   - Global refs 500-1000：警戒
   - Global refs > 1000：告警
   - Global refs > 5000：紧急（疑似 JNI 泄漏）

6. 堆水位
   - Java 堆使用率：< 70%
   - Native 堆使用率：< 70%
   - 警戒阈值：70%
   - 告警阈值：85%
   - 紧急阈值：95%

7. OOM
   - 启动 OOM 率：< 0.1%
   - 严重 OOM 率：< 0.01%
   - 紧急阈值：> 0.1%（1 次/千次启动）

8. 内存泄漏
   - Activity 泄漏数：< 5
   - Fragment 泄漏数：< 5
   - ViewModel 泄漏数：< 0

9.【AOSP 17 + Linux 6.18】sheaves 内存
   - sheaves PSS 占比 20-30%：正常
   - sheaves PSS 占比 < 10%：优化未生效
   - sheaves PSS 占比 > 40%：占用过多
```

### D.3.2 告警规则配置（AOSP 17 强化版）

```yaml
# Grafana / Prometheus 告警规则示例（AOSP 17 强化版）
groups:
- name: gc_alerts
  rules:
  # GC 频率告警
  - alert: HighGcFrequency
    expr: rate(gc_count[5m]) > 100
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "High GC frequency detected"

  # 【AOSP 17 新增】Young GC 暂停告警
  - alert: YoungGcPauseHigh
    expr: young_gc_pause_p95 > 2
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: "Young GC pause > 2ms (AOSP 17)"

  # 【AOSP 17 新增】软阈值已越过
  - alert: SoftThresholdExceeded
    expr: distance_to_soft_threshold < 0
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: "Soft threshold (30%) exceeded"

  # 【AOSP 17 新增】JNI Global refs 过高
  - alert: JniGlobalRefsHigh
    expr: jni_global_refs > 1000
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "JNI Global refs > 1000"

  # 长 STW 告警
  - alert: LongGcPause
    expr: gc_pause_max > 100
    for: 1m
    labels:
      severity: alert
    annotations:
      summary: "Long GC pause detected"

  # 堆使用率高
  - alert: HighHeapUsage
    expr: java_heap_usage > 0.85
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High heap usage"

  # OOM 紧急
  - alert: OomCrash
    expr: oom_count > 0
    for: 0m
    labels:
      severity: critical
    annotations:
      summary: "OOM crash detected"

  # 内存泄漏
  - alert: ActivityLeak
    expr: activity_leak_count > 5
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: "Activity leak detected"
```

### D.3.3 仪表盘基线（AOSP 17 强化版）

```
Grafana 仪表盘基线（AOSP 17 强化版）：

1. 总览仪表盘
   - GC 频率（最近 1 小时趋势）
   -【AOSP 17】Young/Old 代 GC 分代趋势
   -【AOSP 17】软阈值状态实时显示
   -【AOSP 17】JNI refs 趋势
   - GC 时长（最近 1 小时趋势）
   - 堆水位（最近 1 小时趋势）
   - OOM 次数（最近 1 天累计）
   - 当前告警数

2. 详细仪表盘
   - 各 GcCause 频率
   - STW 时长分布（Young / Old / Full 分别）
   - 堆分配速率
   - GC 暂停占比
   -【AOSP 17】类去重统计（去重 Class 数 / 总 Class 数）

3. 异常仪表盘
   - 告警事件列表（最近 24 小时）
   - OOM 事件列表（最近 7 天）
   - 长 STW 事件列表（最近 7 天）
   -【AOSP 17】JNI refs 异常事件列表

4. 业务关联仪表盘
   - GC 与启动时间
   - GC 与滑动帧率
   - GC 与崩溃率
   -【AOSP 17】ART 17 vs AOSP 14 性能对比
```

---

## D.4 应急基线

### D.4.1 长 STW 应急 SOP（AOSP 17 强化版）

```
长 STW 应急 SOP（AOSP 17 强化版）：

1. 触发条件
   -【AOSP 17】Full GC STW > 100ms（严重）
   -【AOSP 17】Full GC STW > 200ms（紧急）
   -【AOSP 17】Young GC STW > 5ms（异常，Young GC 应该 < 1ms）

2. 应急响应
   - 1 分钟内：触发告警，通知 on-call
   - 5 分钟内：抓 trace / hprof
   - 15 分钟内：初步定位
   - 1 小时内：修复方案

3. 排查步骤（AOSP 17 强化）
   - Perfetto trace 找 STW 阶段
   -【AOSP 17】检查软阈值状态（是否被频繁触发）
   -【AOSP 17】检查 Old GC 频率（异常增高？）
   -【AOSP 17】检查类去重是否生效
   -【AOSP 17】检查 Finalizer 队列大小
   - Heap Dump 分析
   - dumpsys meminfo 看分类
   - smaps 看 native 占用

4. 临时措施
   - 调大堆（缓解）
   - 减少 GC 期间业务
   - 关闭非核心功能
   -【AOSP 17】调大 kSoftThresholdPercent 阈值（紧急）

5. 后续行动
   - 修复代码
   -【AOSP 17】升级 GC（CC → GenCC / 调优软阈值）
   - 调整并发度
```

### D.4.2 OOM 应急 SOP

```
OOM 应急 SOP（AOSP 17 强化版）：

1. 触发条件
   - OOM crash 频率 > 0.1%
   - 单次 OOM 后用户投诉
   -【AOSP 17】Distance to hard threshold < 0% 持续 5 分钟

2. 应急响应
   - 5 分钟内：触发告警
   - 30 分钟内：分析崩溃日志
   - 2 小时内：初步方案
   - 24 小时内：彻底修复

3. 排查步骤
   - Crash log 看堆大小
   -【AOSP 17】ART 内部状态（Old GC 频率 / JNI refs）
   - Heap Dump + MAT 1.14.0+ 分析
   -【AOSP 17】检查类去重后 Class 数量
   - 大对象分析
   - Bitmap / List 优化

4. 临时措施
   - 降低图片质量
   - 限制缓存大小
   - 增加堆（紧急）
   - 灰度回滚

5. 后续行动
   - 优化图片加载
   - 优化数据结构
   - 排查泄漏
   -【AOSP 17】考虑升级 GenCC
```

### D.4.3 内存泄漏应急 SOP（AOSP 17 强化版）

```
内存泄漏应急 SOP（AOSP 17 强化版）：

1. 触发条件
   - LeakCanary 3.x 检测到泄漏
   - dumpsys 显示内存持续增长
   - 用户投诉卡顿
   -【AOSP 17】JNI Global refs 持续增长

2. 应急响应
   - 1 小时内：初步定位
   - 4 小时内：修复方案
   - 24 小时内：修复上线

3. 排查步骤
   -【AOSP 17】LeakCanary 3.x 看报告
   - Heap Dump + MAT 1.14.0+ 分析
   -【AOSP 17】处理类去重（用 `class.@deduplicated` 字段）
   -【AOSP 17】处理 GenCC Old 代泄漏（用 `obj.@youngGen=false`）
   - 找引用链
   - 定位代码
   -【AOSP 17】JNI 泄漏检查（Global refs 配对）

4. 临时措施
   - 主动释放引用
   - 关闭可疑页面
   - 灰度回滚

5. 后续行动
   - 修复代码
   -【AOSP 17】增加 LeakCanary 3.x 监控
   -【AOSP 17】增加 MAT 1.14.0+ 分析流程
   - 增加 LeakCanary Android Test
```

---

## D.5 工具基线

### D.5.1 工具链依赖（AOSP 17 强制升级版）

```
GC 诊断治理工具链（AOSP 17 强制升级版）：

1. dumpsys
   - Android SDK Platform Tools
   - 随 SDK 安装
   - 版本：>= 30.0.0
   -【AOSP 17】dumpsys meminfo -d 输出 ART 内部状态

2. procrank / smaps
   - AOSP 系统组件
   - 部分定制 ROM 不支持 procrank
   - smaps 通过 /proc 内核接口
   -【Linux 6.18】smaps_rollup（推荐使用，性能开销降低 100 倍）

3.【AOSP 17 强制升级】LeakCanary
   - Maven / Gradle 依赖
   - 【AOSP 17 强制】当前版本：3.x（2.x 在 AOSP 17 下大量误报）
   - 兼容：Android 8+
   -【AOSP 17】AndroidObjectInspectors 适配类去重

4.【AOSP 17 强制升级】MAT
   - Eclipse Memory Analyzer
   - 【AOSP 17 强制】当前版本：1.14.0+（1.13 解析 AOSP 17 hprof 报错）
   -【AOSP 17 强制】需要 Java 17+（Java 11 解析 AOSP 17 hprof 报错）

5. Perfetto
   - system/extras/perfetto
   - 抓取工具：perfetto cmd
   - UI：https://ui.perfetto.dev/
   - 兼容：Android 10+

6. JVMTI
   - 原生库（C++）
   - 需要 NDK 编译
   - 兼容：Android 8+

7. 自建 APM
   - APM SDK（自研）
   -【AOSP 17】集成 ART 内部状态 API（GetGcStats / GetCodeCacheStats / GetJNIRefsStats）
   - 服务端（Grafana + Prometheus）
   - 告警（AlertManager）
```

### D.5.2 工具链对比

| 工具 | 类型 | 速度 | 深度 | 适用场景 | AOSP 17 适配 |
|:---|:---|:---|:---|:---|:---|
| dumpsys meminfo | 系统命令 | 快 | 浅 | 内存概览 | 增强（ART 内部状态 + 软阈值） |
| procrank / smaps | 系统命令 | 快 | 中 | 进程级 | smaps_rollup 优化 |
| LeakCanary | 第三方库 | 自动 | 中 | 自动泄漏检测 | **必须 3.x** |
| MAT | 第三方工具 | 慢 | 深 | 深度分析 | **必须 1.14.0+ + Java 17+** |
| Perfetto | 系统工具 | 中 | 深 | 卡顿分析 | 适配 |
| JVMTI | 原生 API | 快 | 中 | APM 集成 | 适配 |
| 自建 APM | 自研 | 自动 | 全 | 生产监控 | 集成 ART 内部状态 API |

### D.5.3 工具链组合

```
工具链组合（推荐 · AOSP 17 强化版）：

1. 开发阶段：
   -【AOSP 17】LeakCanary 3.x（debug 自动检测）
   -【AOSP 17】dumpsys meminfo -d（ART 内部状态）
   - Android Studio Profiler（实时分析）
   - dumpsys（快速验证）

2. 测试阶段：
   -【AOSP 17】LeakCanary 3.x Android Test（自动化）
   -【AOSP 17】MAT 1.14.0+（深度分析）
   - Perfetto（性能分析）

3. 生产阶段：
   -【AOSP 17】JVMTI + 自建 APM（集成 ART 内部状态 API）
   -【AOSP 17】dumpsys meminfo -d（远程触发）
   -【AOSP 17】smaps_rollup（轻量监控）
   - Perfetto（按需抓取）

→ 工具链覆盖完整生命周期
→ AOSP 17 工具链必须升级到支持 ART 内部状态的版本
```

---

## D.6 性能基线

### D.6.1 GC 性能指标（AOSP 17 强化版）

```
GC 性能基线（AOSP 17 强化版）：

1.【AOSP 17 调整】GC 频率
   - 静止（Young GC）：< 5 次/分钟（AOSP 17 含 Young GC）
   - 静止（Full GC）：< 0.05 次/分钟（3 次/小时）
   - 轻度：Young GC 5-20 次/分钟，Full GC < 0.1 次/分钟
   - 重度：Young GC 20-50 次/分钟，Full GC < 0.5 次/分钟
   - 异常：Full GC > 1 次/分钟

2.【AOSP 17 调整】STW 时间
   -【AOSP 17】Young GC STW 优秀：< 0.5ms
   -【AOSP 17】Young GC STW 良好：0.5-1ms
   -【AOSP 17】Young GC STW 一般：1-2ms
   -【AOSP 17】Young GC STW 差：> 2ms（异常）
   -【AOSP 17】Full GC STW 优秀：< 5ms
   -【AOSP 17】Full GC STW 良好：5-10ms
   -【AOSP 17】Full GC STW 一般：10-30ms
   -【AOSP 17】Full GC STW 差：> 30ms
   -【AOSP 17】Full GC STW 严重：> 100ms

3.【AOSP 17 调整】GC 暂停占比
   - 优秀：< 1%
   - 良好：1-3%
   - 一般：3-5%
   - 差：5-10%
   - 严重：> 10%

4. 堆使用率
   - 优秀：< 50%
   - 良好：50-70%
   - 一般：70-85%
   - 差：85-95%
   - 严重：> 95%

5.【AOSP 17】GC 分配速率
   - 优秀：< 10 MB/s
   - 良好：10-30 MB/s
   - 一般：30-50 MB/s
   - 差：50-100 MB/s
   - 严重：> 100 MB/s
```

### D.6.2 OOM 性能指标

```
OOM 性能基线：

1. OOM 率
   - 优秀：< 0.01%（万分之一）
   - 良好：0.01-0.05%
   - 一般：0.05-0.1%
   - 差：0.1-0.5%
   - 严重：> 0.5%

2.【AOSP 17】OOM 场景细分
   - 启动 OOM：< 0.01%
   - 滑动 OOM：< 0.05%
   - 拍照 OOM：< 0.1%
   - 后台 OOM：< 0.1%
   -【AOSP 17 新增】JNI 泄漏导致 OOM：< 0.01%

3. OOM 恢复
   - 自动恢复率：> 99%
   - 用户投诉率：< 1%
```

### D.6.3 内存泄漏指标

```
内存泄漏基线：

1. 泄漏数（每次启动周期）
   - Activity：< 0 个
   - Fragment：< 0 个
   - ViewModel：< 0 个
   - Custom：< 5 个
   -【AOSP 17 新增】JNI Global refs 持续增长：< 0

2. 泄漏恢复
   - 自动恢复：< 100ms（GC 触发）
   - 主动恢复：< 1s（finish）
   -【AOSP 17】Young GC 恢复：< 1ms

3. 泄漏影响
   - 单次泄漏大小：< 10MB
   - 总泄漏大小：< 50MB
```

---

## D.7 培训基线

### D.7.1 培训目标

```
培训目标：

1. 初级工程师
   - 能用 dumpsys meminfo 看内存
   - 能读懂 GC 日志
   - 能用 LeakCanary 排查基础泄漏
   - 了解 GC 基础概念

2. 中级工程师
   - 能用 Perfetto 分析 GC 事件
   - 能用 MAT 深度分析 hprof
   - 能设计监控指标
   - 理解 ART GC 实现

3. 高级工程师
   - 能优化 GC 参数
   - 能设计 APM 系统
   - 能排查疑难杂症
   - 理解 ART 17 + Linux 6.18 硬变化

4.【AOSP 17 新增】架构师
   - 能设计 AOSP 17 升级方案
   - 能评估 GenCC 收益
   - 能设计类去重 / Finalizer 池化适配方案
   - 能主导 LeakCanary 3.x + MAT 1.14.0+ 升级
```

### D.7.2 培训内容（AOSP 17 强化版）

```
培训内容（AOSP 17 强化版）：

1. 基础培训（1 周）
   - GC 基础概念
   - dumpsys meminfo 基础（【AOSP 17】含 ART 内部状态）
   - LeakCanary 基础（【AOSP 17】LeakCanary 3.x）
   - 内存泄漏基础

2. 中级培训（2 周）
   - Perfetto 分析
   - MAT 深度分析（【AOSP 17】MAT 1.14.0+）
   - 监控设计
   - ART GC 实现（【AOSP 17】GenCC + 软阈值 + 类去重）

3. 高级培训（1 月）
   - GC 调优
   - APM 设计（【AOSP 17】ART 内部状态 API）
   - 疑难杂症
   - ART 17 + Linux 6.18 完整硬变化

4. 应急培训（1 天）
   - 应急 SOP（D.4）
   -【AOSP 17】GenCC 软阈值应急
   - 故障复盘
```

### D.7.3 培训考核（AOSP 17 强化版）

```
培训考核（AOSP 17 强化版）：

1. 理论考核（笔试）
   - GC 原理（【AOSP 17】含 GenCC + 类去重 + Finalizer 池化）
   - 监控指标（【AOSP 17】含 ART 内部状态）
   - 治理方案

2. 工具考核（上机）
   - dumpsys 抓取（【AOSP 17】dumpsys meminfo -d）
   - LeakCanary 3.x 集成
   - MAT 1.14.0+ 分析（【AOSP 17】Class Extent / GenCC 元数据）
   - Perfetto 分析

3. 实战考核（项目）
   - 排查一个真实问题
   - 设计一个监控方案（【AOSP 17】含 ART 内部状态）
   - 制定一个应急 SOP（【AOSP 17】含 GenCC 软阈值应急）
```

---

## D.8 持续改进基线

### D.8.1 监控指标优化（AOSP 17 强化版）

```
监控指标优化方向（AOSP 17 强化版）：

1. 增加维度
   - 按页面分
   - 按业务分
   - 按用户分
   -【AOSP 17】按 Young/Old 代分

2. 增加指标
   - GC 与业务关联
   - GC 与网络关联
   - GC 与电量关联
   -【AOSP 17】软阈值状态实时监控
   -【AOSP 17】JNI refs 监控
   -【AOSP 17】类去重效率监控

3. 优化算法
   - 智能告警（机器学习）
   - 异常检测
   - 自动归因
```

### D.8.2 治理工具优化

```
治理工具优化方向：

1. 自动化
   - 自动 dump
   - 自动分析
   - 自动修复（部分）

2. 智能化
   - 智能推荐治理方案
   - 智能识别泄漏模式
   - 智能预测 OOM

3. 一体化
   - 工具链集成
   - 端到端监控
   - 全链路追踪
   -【AOSP 17】集成 ART 内部状态 API
```

### D.8.3 应急响应优化

```
应急响应优化方向：

1. SOP 优化
   - 详细化
   - 自动化
   - 工具化

2. 响应速度
   - 自动化检测
   - 自动化通知
   - 自动化定位

3. 复盘机制
   - RCA 模板
   - 改进措施
   - 跟踪验证
```

---

## D.9 【v2 新增】AOSP 17 + Linux 6.18 增补基线

> **本节为 v2 升级新增**——列出 AOSP 17 + Linux 6.18 相对 AOSP 14 + Linux 5.10 的基线变化。

### D.9.1 AOSP 17 必升级工具

| 工具 | AOSP 14 版本 | **AOSP 17 必须升级版本** | 升级原因 |
|:---|:---|:---|:---|
| **LeakCanary** | 2.x | **3.x**（必须） | 类去重、FinalReference、GenCC 适配 |
| **MAT** | 1.13.0 | **1.14.0+**（必须） | 解析 AOSP 17 hprof 格式 |
| **Java** | Java 11+ | **Java 17+**（必须） | 解析 AOSP 17 hprof |
| **Android Studio** | Hedgehog | **Ladybug+（2024+）** | 适配 AOSP 17 |
| **dumpsys meminfo** | 基础 | **增强版（-d）** | 输出 ART 内部状态 |
| **smaps** | 全量 | **smaps_rollup（推荐）** | 性能开销降低 100 倍 |
| **Perfetto** | 适配 | **AOSP 17 适配版** | 适配 GenCC 事件 |

### D.9.2 AOSP 17 必集成 API

| API | 位置 | 用途 |
|:---|:---|:---|
| **GetGcStats** | `art/runtime/gc/heap.h` | GC 状态监控 |
| **GetCodeCacheStats** | `art/runtime/jit/jit_code_cache.h` | JIT Code Cache 监控 |
| **GetJNIRefsStats** | `art/runtime/jni/jni_env_ext.h` | JNI refs 监控 |
| **GetClassLoaderStats** | `art/runtime/class_linker.h` | ClassLoader + 类去重监控 |
| **dumpsys meminfo -d** | （命令） | ART 内部状态 |
| **WriteClassExtent** | `art/runtime/hprof/hprof.cc` | hprof 类去重元数据 |
| **WriteGenInfo** | `art/runtime/hprof/hprof.cc` | hprof GenCC 元数据 |
| **WriteGCRootIndex** | `art/runtime/hprof/hprof.cc` | hprof GC Root 索引 |

### D.9.3 AOSP 17 必调整阈值

| 阈值 | AOSP 14 | **AOSP 17** | 调整原因 |
|:---|:---|:---|:---|
| **GC 频率（Young GC）** | < 5 次/分钟 | **< 50 次/分钟** | GenCC 让 Young GC 频繁 |
| **GC 频率（Full GC）** | < 1 次/分钟 | **< 0.05 次/分钟** | GenCC 减少 Full GC |
| **Young GC STW p95** | < 5ms | **< 1ms** | GenCC 让 Young GC 暂停 < 1ms |
| **Full GC STW p95** | < 16ms | **< 16ms** | 不变 |
| **软阈值触发距离** | 不存在 | **> 5%** | **AOSP 17 新增** |
| **JNI Global refs** | 不监控 | **< 1000** | **AOSP 17 新增监控** |
| **sheaves 内存占比** | 不存在 | **20-30%** | **Linux 6.18 新增** |

### D.9.4 AOSP 17 必避免的错误

```
AOSP 17 必避免的错误：

1.【必避免】使用 LeakCanary 2.x
   - AOSP 17 类去重后会大量误报"Class 泄漏"
   - 必须升级到 LeakCanary 3.x

2.【必避免】使用 MAT 1.13.0
   - 解析 AOSP 17 hprof 报错
   - 必须升级到 MAT 1.14.0+

3.【必避免】使用 Java 11 解析 AOSP 17 hprof
   - 报错或部分元数据丢失
   - 必须升级到 Java 17+

4.【必避免】把类去重误判为"内存泄漏已修复"
   - Linux 6.18 sheaves 也会让 Native 堆降 15-20%
   - 两者叠加可能让 PSS 降 25-30%，**不是泄漏已修复**

5.【必避免】用 `Object.finalize()`
   - AOSP 17 池化也救不了慢 finalize
   - 用 `AutoCloseable` + try-with-resources 替代

6.【必避免】用 Activity Context 做 static
   - 静态字段持有 Activity Context 是泄漏的根因
   - 用 Application Context 替代

7.【必避免】配对缺失的 JNI NewGlobalRef / DeleteGlobalRef
   - AOSP 17 dumpsys meminfo -d 能看到 JNI Global refs
   - Global refs > 1000 即视为可疑
```

### D.9.5 AOSP 17 升级检查清单

```
AOSP 17 升级检查清单：

□ 工具升级
  - [ ] LeakCanary 2.x → 3.x
  - [ ] MAT 1.13.0 → 1.14.0+
  - [ ] Java 11 → 17+
  - [ ] Android Studio Hedgehog → Ladybug+

□ 集成新 API
  - [ ] dumpsys meminfo -d 集成
  - [ ] ART 内部状态 API 集成（GetGcStats 等）
  - [ ] smaps_rollup 集成
  - [ ] Linux 6.18 sheaves 监控

□ 阈值调整
  - [ ] GC 频率阈值调整（Young GC < 50 次/分钟）
  - [ ] Young GC 暂停阈值调整（< 1ms）
  - [ ] 软阈值监控集成
  - [ ] JNI refs 监控集成

□ 代码适配
  - [ ] 处理类去重（避免 Class 泄漏误判）
  - [ ] 处理 GenCC 分代（用 OQL `obj.@youngGen`）
  - [ ] JNI 配对检查
  - [ ] finalizer → AutoCloseable 迁移

□ 测试
  - [ ] LeakCanary 3.x 跑通
  - [ ] MAT 1.14.0+ 跑通
  - [ ] dumpsys meminfo -d 输出 ART 内部状态
  - [ ] 类去重 / GenCC / Finalizer 池化全部生效
```

---

## D.10 总结（v2 升级总览）

### D.10.1 v1 → v2 增补总览

```
D.1：工程基线概述（保留 + AOSP 17 注释）
D.2：验收基线（保留 + AOSP 17 强化 + 软阈值 + JNI refs + 类去重适配检查）
D.3：监控基线（保留 + AOSP 17 强化 + Young/Old 代 + 软阈值 + JNI refs）
D.4：应急基线（保留 + AOSP 17 强化 + GenCC 软阈值应急）
D.5：工具基线（保留 + 强制升级 LeakCanary 3.x / MAT 1.14.0+ / Java 17+）
D.6：性能基线（保留 + AOSP 17 调整 Young GC 阈值）
D.7：培训基线（保留 + AOSP 17 强化培训内容 + 考核）
D.8：持续改进基线（保留 + AOSP 17 强化）

【v2 新增】
D.9：AOSP 17 + Linux 6.18 增补基线（必升级工具 + 必集成 API + 必调整阈值 + 必避免错误 + 升级检查清单）
D.10：v2 升级总览（本节）
```

### D.10.2 工程基线核心数字

```
AOSP 17 工程基线核心数字：

1. GC 频率
   - Young GC：< 50 次/分钟（正常）
   - Full GC：< 0.05 次/分钟（正常）

2. GC 暂停
   - Young GC p95：< 1ms
   - Full GC p95：< 16ms

3. 软阈值
   - kSoftThresholdPercent=30%（AOSP 17 默认）
   - Distance to soft > 5%（警戒）

4. JNI refs
   - Global refs < 1000（警戒）

5. 堆使用率
   - < 70%（正常）
   - < 80%（警戒）
   - < 95%（紧急）

6. 工具版本
   - LeakCanary 3.x（必须）
   - MAT 1.14.0+（必须）
   - Java 17+（必须）

7. sheaves 内存（Linux 6.18）
   - 占比 20-30%（正常）
   - Native 堆节省 15-20%
```

---

## 附录 C：量化数据自检表

| # | 量化描述 | 数量级 | 备注 |
| :-- | :--- | :--- | :--- |
| 1 | 工程基线分类数 | 8 类（D.1 ~ D.8） + 1 类（v2 新增 D.9） | v1 7 类 + v2 1 类 |
| 2 | 验收标准检查项 | 20+ 项 | D.2.1 |
| 3 | 部署前检查项 | 20+ 项 | D.2.2 |
| 4 | 部署后验证项 | 15+ 项 | D.2.3 |
| 5 | 监控指标 | 9 类 | D.3.1 |
| 6 | 告警规则 | 8 条 | D.3.2 |
| 7 | 仪表盘 | 4 类 | D.3.3 |
| 8 | 应急 SOP | 3 类（长 STW / OOM / 泄漏） | D.4 |
| 9 | 工具链 | 7 类 | D.5.1 |
| 10 | **AOSP 17 必升级工具** | **7 类** | **D.9.1** |
| 11 | **AOSP 17 必集成 API** | **8 个** | **D.9.2** |
| 12 | **AOSP 17 必调整阈值** | **7 个** | **D.9.3** |
| 13 | **AOSP 17 必避免错误** | **7 类** | **D.9.4** |
| 14 | **AOSP 17 升级检查清单** | **5 类** | **D.9.5** |
| 15 | 培训等级 | 4 级（初级 / 中级 / 高级 / 架构师） | D.7.1 |
| 16 | 培训内容周数 | 5 周 | D.7.2 |
| 17 | 培训考核类目 | 3 类（理论 / 工具 / 实战） | D.7.3 |
| 18 | 持续改进方向 | 3 类（监控 / 工具 / 应急） | D.8 |

---

## 附录 A：核心源码路径索引

| 文件 | 完整路径 | AOSP 版本 |
| :--- | :--- | :--- |
| Heap 主类 | `art/runtime/gc/heap.h` | AOSP 17 |
| **软阈值** | `art/runtime/options.h#kSoftThresholdPercent=30` | **AOSP 17 新增** |
| GenCC | `art/runtime/gc/collector/generational_cc.h` | AOSP 17 |
| SMS | `art/runtime/gc/collector/sticky_mark_sweep.h` | AOSP 17 |
| 类去重 | `art/runtime/gc/class_linker.cc#ClassDeduplication` | AOSP 17 |
| Finalizer 池化 | `art/runtime/thread.cc#CreateFinalizerThread` | AOSP 17 |
| Hprof Class Extent | `art/runtime/hprof/hprof.cc#WriteClassExtent` | AOSP 17 |
| dumpsys meminfo | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java#dumpApplicationMemoryUsage` | AOSP 17 |
| ART 内部状态 API | `art/runtime/gc/heap.h#GetGcStats` | **AOSP 17 新增** |
| sheaves | `kernel/mm/slab_common.c` | **Linux 6.18** |
| smaps_rollup | `fs/proc/task_mmu.c` | **Linux 6.18** |
| LeakCanary 3.x | `external/leakcanary/leakcanary-android/` | LeakCanary 3.x |
| MAT 1.14.0+ | `external/eclipse-memory-analyzer/` | MAT 1.14.0+ |

---

## 附录 B：核心变更速查

### B.1 AOSP 14 → AOSP 17 关键变化

| 维度 | AOSP 14 | **AOSP 17** |
|:---|:---|:---|
| GC 策略 | PMS | GenCC |
| 软阈值 | 不存在 | kSoftThresholdPercent=30% |
| 类去重 | 不存在 | ClassDeduplication |
| Finalizer 线程 | 1 线程 | 4 线程池化 |
| Hprof 元数据 | 基础 | Class Extent + GenInfo + GCRootIndex |
| ART 内部状态 API | 不存在 | GetGcStats 等 |
| Linux 内核 | 5.10/5.15 | **android17-6.18** |
| LeakCanary | 2.x | **必须 3.x** |
| MAT | 1.13.0 | **必须 1.14.0+** |
| Java | Java 11+ | **必须 Java 17+** |
| sheaves 内存 | 不存在 | Linux 6.18 sheaves |
| smaps_rollup | 不存在 | Linux 6.18 新增 |

### B.2 AOSP 17 性能阈值速查

| 指标 | 阈值 | 备注 |
|:---|:---|:---|
| Young GC 频率 | < 50 次/分钟 | GenCC 频繁 |
| Full GC 频率 | < 0.05 次/分钟 | 罕见 |
| Young GC STW p95 | < 1ms | GenCC 强化 |
| Full GC STW p95 | < 16ms | 不变 |
| 软阈值触发距离 | > 5% | AOSP 17 新增 |
| JNI Global refs | < 1000 | AOSP 17 新增 |
| sheaves 内存占比 | 20-30% | Linux 6.18 新增 |
| Native 堆内存节省 | 15-20% | Linux 6.18 新增 |
| heap dump 写盘延迟 | -30% | Linux 6.18 io_uring |
| hprof-conv 转换加速 | 3 倍 | AOSP 17 + Linux 6.18 |
| GC Root 路径查找加速 | 5-10 倍 | AOSP 17 GCRootIndex |

---

> **本子模块（09-GC 诊断与治理）v2 升级完成**。下一篇：[10-ART17分代GC强化专章 v2](../../03-GC系统/10-ART17分代GC强化专章-v2.md) 专章 ART 17 分代 GC 强化。
