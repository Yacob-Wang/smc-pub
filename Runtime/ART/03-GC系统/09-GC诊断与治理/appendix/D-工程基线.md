# 附录 D：工程基线（验收标准 + 检查清单 + 工具链）

> **本附录提供 GC 诊断与治理的工程基线**：验收标准、部署检查清单、工具链依赖、监控告警配置、应急响应 SOP。

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
```

### D.1.2 工程基线分类

```
工程基线分类：

1. 验收基线：部署前的标准
2. 监控基线：部署后的持续监控
3. 应急基线：问题发生时的 SOP
4. 工具基线：使用的工具链
5. 性能基线：性能指标的标准
6. 培训基线：团队能力建设
```

---

## D.2 验收基线

### D.2.1 验收标准

```
GC 诊断治理验收标准：

1. 工具链
   - [ ] dumpsys meminfo 能在测试环境跑通
   - [ ] procrank / smaps 能获取详细信息
   - [ ] LeakCanary 能自动检测泄漏（debug）
   - [ ] MAT 能打开和解析 hprof
   - [ ] Perfetto 能抓取和查看 trace
   - [ ] JVMTI SDK 能编译和集成

2. 监控
   - [ ] GC 频率指标能上报
   - [ ] GC 时长指标能上报
   - [ ] 堆水位指标能上报
   - [ ] 告警规则能触发
   - [ ] 仪表盘能展示

3. 治理
   - [ ] GC 频率 < 30 次/分钟（静止）
   - [ ] GC 时长 p95 < 16ms
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
部署前检查清单：

□ 代码检查
  - [ ] 无静态引用 Activity
  - [ ] 无 finalizer 滥用
  - [ ] WeakReference 使用规范
  - [ ] 资源释放（Bitmap / Cursor / File）

□ 编译检查
  - [ ] LeakCanary 仅 debug 启用
  - [ ] APM SDK release 启用
  - [ ] 无 Native 内存泄漏

□ 测试检查
  - [ ] LeakCanary 测试通过
  - [ ] 压测无 OOM
  - [ ] GC 频率在阈值内

□ 监控检查
  - [ ] 上报接口连通
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
  - [ ] 告警正常触发

□ 性能验证
  - [ ] 启动时间在标准内
  - [ ] 滑动帧率达标
  - [ ] GC 频率在阈值内
  - [ ] 内存使用稳定

□ 监控验证
  - [ ] 数据上报完整
  - [ ] 告警规则触发
  - [ ] 仪表盘数据正确

□ 应急验证
  - [ ] 应急 SOP 可执行
  - [ ] 回滚方案可执行
  - [ ] 应急响应时间达标
```

---

## D.3 监控基线

### D.3.1 监控指标基线

```
GC 监控指标基线：

1. GC 频率
   - 静止应用：< 1 次/分钟
   - 轻度使用：1-5 次/分钟
   - 重度使用：5-20 次/分钟
   - 警戒阈值：20 次/分钟
   - 告警阈值：50 次/分钟
   - 紧急阈值：100 次/分钟

2. GC 时长
   - STW 平均：< 5ms
   - STW p95：< 16ms
   - STW p99：< 50ms
   - 警戒阈值：16ms（p95）
   - 告警阈值：50ms（p95）
   - 紧急阈值：100ms（最大）

3. 堆水位
   - Java 堆使用率：< 70%
   - Native 堆使用率：< 70%
   - 警戒阈值：70%
   - 告警阈值：85%
   - 紧急阈值：95%

4. OOM
   - 启动 OOM 率：< 0.1%
   - 严重 OOM 率：< 0.01%
   - 紧急阈值：> 0.1%（1 次/千次启动）

5. 内存泄漏
   - Activity 泄漏数：< 5
   - Fragment 泄漏数：< 5
   - ViewModel 泄漏数：< 0
```

### D.3.2 告警规则配置

```yaml
# Grafana / Prometheus 告警规则示例
groups:
- name: gc_alerts
  rules:
  # GC 频率告警
  - alert: HighGcFrequency
    expr: rate(gc_count[5m]) > 50
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "High GC frequency detected"

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

### D.3.3 仪表盘基线

```
Grafana 仪表盘基线：

1. 总览仪表盘
   - GC 频率（最近 1 小时趋势）
   - GC 时长（最近 1 小时趋势）
   - 堆水位（最近 1 小时趋势）
   - OOM 次数（最近 1 天累计）
   - 当前告警数

2. 详细仪表盘
   - 各 GcCause 频率
   - STW 时长分布
   - 堆分配速率
   - GC 暂停占比

3. 异常仪表盘
   - 告警事件列表（最近 24 小时）
   - OOM 事件列表（最近 7 天）
   - 长 STW 事件列表（最近 7 天）

4. 业务关联仪表盘
   - GC 与启动时间
   - GC 与滑动帧率
   - GC 与崩溃率
```

---

## D.4 应急基线

### D.4.1 长 STW 应急 SOP

```
长 STW 应急 SOP：

1. 触发条件
   - STW > 100ms（严重）
   - STW > 200ms（紧急）

2. 应急响应
   - 1 分钟内：触发告警，通知 on-call
   - 5 分钟内：抓 trace / hprof
   - 15 分钟内：初步定位
   - 1 小时内：修复方案

3. 排查步骤
   - Perfetto trace 找 STW 阶段
   - Heap Dump 分析
   - dumpsys meminfo 看分类
   - smaps 看 native 占用

4. 临时措施
   - 调大堆（缓解）
   - 减少 GC 期间业务
   - 关闭非核心功能

5. 后续行动
   - 修复代码
   - 升级 GC（CC → GenCC）
   - 调整并发度
```

### D.4.2 OOM 应急 SOP

```
OOM 应急 SOP：

1. 触发条件
   - OOM crash 频率 > 0.1%
   - 单次 OOM 后用户投诉

2. 应急响应
   - 5 分钟内：触发告警
   - 30 分钟内：分析崩溃日志
   - 2 小时内：初步方案
   - 24 小时内：彻底修复

3. 排查步骤
   - Crash log 看堆大小
   - Heap Dump 分析
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
```

### D.4.3 内存泄漏应急 SOP

```
内存泄漏应急 SOP：

1. 触发条件
   - LeakCanary 检测到泄漏
   - dumpsys 显示内存持续增长
   - 用户投诉卡顿

2. 应急响应
   - 1 小时内：初步定位
   - 4 小时内：修复方案
   - 24 小时内：修复上线

3. 排查步骤
   - LeakCanary 看报告
   - Heap Dump + MAT 分析
   - 找引用链
   - 定位代码

4. 临时措施
   - 主动释放引用
   - 关闭可疑页面
   - 灰度回滚

5. 后续行动
   - 修复代码
   - 增加 LeakCanary 监控
   - 增加 LeakCanary Android Test
```

---

## D.5 工具基线

### D.5.1 工具链依赖

```
GC 诊断治理工具链：

1. dumpsys
   - Android SDK Platform Tools
   - 随 SDK 安装
   - 版本：>= 30.0.0

2. procrank / smaps
   - AOSP 系统组件
   - 部分定制 ROM 不支持 procrank
   - smaps 通过 /proc 内核接口

3. LeakCanary
   - Maven / Gradle 依赖
   - 当前版本：2.14+
   - 兼容：Android 5+

4. MAT
   - Eclipse Memory Analyzer
   - 当前版本：1.13.0
   - 需要 Java 11+

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
   - 服务端（Grafana + Prometheus）
   - 告警（AlertManager）
```

### D.5.2 工具链对比

| 工具 | 类型 | 速度 | 深度 | 适用场景 |
|:---|:---|:---|:---|:---|
| dumpsys meminfo | 系统命令 | 快 | 浅 | 内存概览 |
| procrank / smaps | 系统命令 | 快 | 中 | 进程级 |
| LeakCanary | 第三方库 | 自动 | 中 | 自动泄漏检测 |
| MAT | 第三方工具 | 慢 | 深 | 深度分析 |
| Perfetto | 系统工具 | 中 | 深 | 卡顿分析 |
| JVMTI | 原生 API | 快 | 中 | APM 集成 |
| 自建 APM | 自研 | 自动 | 全 | 生产监控 |

### D.5.3 工具链组合

```
工具链组合（推荐）：

1. 开发阶段：
   - LeakCanary（debug 自动检测）
   - Android Studio Profiler（实时分析）
   - dumpsys（快速验证）

2. 测试阶段：
   - LeakCanary Android Test（自动化）
   - Perfetto（性能分析）
   - MAT（深度分析）

3. 生产阶段：
   - JVMTI + 自建 APM（持续监控）
   - dumpsys（远程触发）
   - Perfetto（按需抓取）

→ 工具链覆盖完整生命周期
```

---

## D.6 性能基线

### D.6.1 GC 性能指标

```
GC 性能基线：

1. GC 频率（每秒）
   - 静止：< 0.05 次/s（3 次/分钟）
   - 轻度：0.05 - 0.5 次/s
   - 重度：0.5 - 1 次/s
   - 异常：> 1 次/s

2. STW 时间（每次）
   - 优秀：< 5ms
   - 良好：5-10ms
   - 一般：10-30ms
   - 差：30-100ms
   - 严重：> 100ms

3. GC 暂停占比（占总运行时间）
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

5. GC 分配速率（每秒分配）
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

2. OOM 场景
   - 启动 OOM：< 0.01%
   - 滑动 OOM：< 0.05%
   - 拍照 OOM：< 0.1%
   - 后台 OOM：< 0.1%

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

2. 泄漏恢复
   - 自动恢复：< 100ms（GC 触发）
   - 主动恢复：< 1s（finish）

3. 泄漏影响
   - 单次泄漏大小：< 10MB
   - 总泄漏大小：< 50MB
```

---

## D.7 培训基线

### D.7.1 培训目标

```
GC 诊断治理培训目标：

1. 基础能力
   - 理解 GC 原理（参考 01-08 文章）
   - 掌握 dumpsys / procrank 使用
   - 能看懂 Heap Dump

2. 中级能力
   - 使用 MAT 分析 Heap Dump
   - 使用 Perfetto 分析卡顿
   - 能识别常见泄漏

3. 高级能力
   - 集成 JVMTI SDK
   - 自建 APM 监控
   - 设计 GC 治理方案

4. 专家能力
   - 优化 GC 性能
   - 设计监控指标体系
   - 制定应急 SOP
```

### D.7.2 培训内容

```
培训内容：

1. 理论培训（2-3 天）
   - GC 原理（01-04）
   - GC 调度（07）
   - GC 与其他子系统（08）

2. 工具培训（2-3 天）
   - dumpsys / procrank（9.1-9.2）
   - LeakCanary / MAT（9.3-9.4）
   - Perfetto / JVMTI（9.5-9.6）

3. 监控培训（1-2 天）
   - 监控指标体系（9.7）
   - APM 集成（9.10）

4. 治理培训（1-2 天）
   - 治理工具箱（9.8）
   - 实战案例（9.9-9.10）

5. 应急培训（1 天）
   - 应急 SOP（D.4）
   - 故障复盘
```

### D.7.3 培训考核

```
培训考核：

1. 理论考核（笔试）
   - GC 原理
   - 监控指标
   - 治理方案

2. 工具考核（上机）
   - dumpsys 抓取
   - LeakCanary 集成
   - MAT 分析
   - Perfetto 分析

3. 实战考核（项目）
   - 排查一个真实问题
   - 设计一个监控方案
   - 制定一个应急 SOP
```

---

## D.8 持续改进基线

### D.8.1 监控指标优化

```
监控指标优化方向：

1. 增加维度
   - 按页面分
   - 按业务分
   - 按用户分

2. 增加指标
   - GC 与业务关联
   - GC 与网络关联
   - GC 与电量关联

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

## D.9 总结

```
工程基线总结：

1. 验收基线：工具 + 监控 + 治理 + 应急（D.2）
2. 监控基线：指标 + 告警 + 仪表盘（D.3）
3. 应急基线：长 STW / OOM / 泄漏 SOP（D.4）
4. 工具基线：依赖 + 对比 + 组合（D.5）
5. 性能基线：GC / OOM / 泄漏（D.6）
6. 培训基线：目标 + 内容 + 考核（D.7）
7. 持续改进：监控 + 治理 + 应急（D.8）

→ 工程基线覆盖部署 / 监控 / 应急 / 培训 / 改进
→ 可直接用于生产环境的 GC 诊断治理
```

---

## 跨节引用

**本附录引用**：
- 9.1 ~ 9.10 全部章节
- 附录 A（源码索引）
- 附录 B（路径对账）
- 附录 C（量化自检）