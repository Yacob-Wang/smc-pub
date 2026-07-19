# PerfMem · 性能 vs 内存权衡

> **状态**：🟡 占位（计划 2026-08 启动 P2）
>
> **目标读者**：性能架构师 / 内存优化工程师
>
> **版本基线**：AOSP `android-17.0.0_r1`（API 37）+ Linux `android17-6.18`

## 计划内容（5-7 篇）

1. 性能 vs 内存总览（5 大红线）
2. ART 17 分代 GC 内存节省
3. 启动期内存压力优化
4. 后台进程电耗优化
5. Low Memory Killer 配置
6. 性能 / 内存 / 电量三角权衡框架

## 跨系列引用

- 上游：[01-Mechanism/Runtime/ART/03-GC系统](../../01-Mechanism/Runtime/ART/03-GC系统/) 99 篇
- 上游：[01-Mechanism/Kernel/Memory_Management](../../01-Mechanism/Kernel/Memory_Management/) 内存管理
- 上游：[02-Symptom/S05-HANG](../../02-Symptom/S05-HANG/) HANG 通用机制
- 配套：[05-Governance/LowEnd](../LowEnd/) 低端机治理

