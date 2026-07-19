# LowEnd · 低端机稳定性治理

> **状态**：🟡 占位（计划 2026-08 启动 P1）
>
> **目标读者**：海外市场稳定性工程师 / 入门机项目负责人
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`

## 计划内容（5-7 篇）

1. 低端机稳定性挑战总览
2. 内存压力下的 GC 调优（< 4GB RAM）
3. 启动期 IO 优化（f2fs 适配 + 慢盘策略）
4. 启动期 GC 抑制策略
5. ART 17 分代 GC 在低端机的表现
6. 案例：东南亚低端机项目治理

## 跨系列引用

- 上游：[01-Mechanism/Runtime/ART](../../01-Mechanism/Runtime/ART/) 99 篇 GC
- 上游：[01-Mechanism/Kernel/Memory_Management](../../01-Mechanism/Kernel/Memory_Management/) 内存
- 上游：[02-Symptom/S11-Startup](../../02-Symptom/S11-Startup/) 启动专项
- 配套：[05-Governance/PerfMem](../PerfMem/) 性能 vs 内存

