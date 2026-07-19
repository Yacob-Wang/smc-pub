# 启动场景案例（06-Case/Startup/）

> **位置**：06-Case/Startup/（启动场景案例库，跨分类）
>
> **承接自**：[02-Symptom/S11-Startup/](../../02-Symptom/S11-Startup/)（AOSP_Startup 22 篇 v4）
>
> **完成日期**：2026-07-19

## 当前状态

✅ **E01-E03 已就位**。所有 AOSP_Startup 22 篇 v4 中的实战案例 E01-E03 已从兼容层 Android_Framework/AOSP_Startup/ 迁移到 06-Case/Startup/，作为独立的"启动场景案例库"。

| 篇 | 案例主题 | 涉及模块 | 强依赖 | 状态 |
|:--|:---------|:---------|:-------|:----:|
| E01 | 冷启动 8s → 1s 优化全过程 | A + B + D | [B02 启动时间优化](../../02-Symptom/S11-Startup/B-启动性能/B02-启动时间优化.md) | ✅ |
| E02 | 启动卡死 SystemServer 60% 进度 | A + C + D | [C02 启动死锁](../../02-Symptom/S11-Startup/C-启动稳定性/C02-启动死锁.md) | ✅ |
| E03 | 开机黑屏 30s SurfaceFlinger 卡死 | A + C + D | [C03 启动黑屏](../../02-Symptom/S11-Startup/C-启动稳定性/C03-启动黑屏.md) | ✅ |

## 后续计划（E04-E11）

待新增（可在 [Cases-Extended/](../Cases-Extended/) 或本目录下扩写）：

| 篇 | 案例主题 | 强依赖 |
|:--|:---------|:-------|
| E04 | 启动期 ANR：5s vs 20s vs 200s 阈值案例 | [C01 启动 ANR](../../02-Symptom/S11-Startup/C-启动稳定性/C01-启动ANR.md) |
| E05 | 启动崩溃：SystemServer crash + BootLoop | [C04 启动崩溃](../../02-Symptom/S11-Startup/C-启动稳定性/C04-启动崩溃.md) |
| E06 | 启动期 IO 卡顿：f2fs / ext4 fsync 案例 | [D02 dumpsys + dropbox](../../02-Symptom/S11-Startup/D-启动工具/D02-dumpsys+dropbox+bootstat联用.md) |
| E07 | 启动期 GC 卡顿：分代 GC 启动期表现 | [S02 JE 案例](../../02-Symptom/S02-JE/) |
| E08 | OEM 启动定制：小米/华为/OPPO 启动器对比 | [A03 Init 进程](../../02-Symptom/S11-Startup/A-启动机制/A03-Init进程与init.rc.md) |
| E09 | 启动期权限弹窗：弹窗流程耗时案例 | [A05 AMS](../../02-Symptom/S11-Startup/A-启动机制/A05-AMS-PMS-WMS四大组件启动.md) |
| E10 | 启动期 32/64 位切换：ART 17 优化 | [A04 Zygote](../../02-Symptom/S11-Startup/A-启动机制/A04-Zygote+SystemServer.md) |
| E11 | 启动期 AI Agent OS 集成：AOSP 17 AppFunctions | [A06 第一帧](../../02-Symptom/S11-Startup/A-启动机制/A06-第一帧与Choreographer.md) |

## 跨系列引用

- **上游（机制）**：[02-Symptom/S11-Startup/A-启动机制](../../02-Symptom/S11-Startup/A-启动机制/)
- **上游（性能）**：[02-Symptom/S11-Startup/B-启动性能](../../02-Symptom/S11-Startup/B-启动性能/)
- **上游（稳定性）**：[02-Symptom/S11-Startup/C-启动稳定性](../../02-Symptom/S11-Startup/C-启动稳定性/)
- **上游（工具）**：[02-Symptom/S11-Startup/D-启动工具](../../02-Symptom/S11-Startup/D-启动工具/)
- **配套（取证）**：[04-Tool/Dumpsys](../../04-Tool/Dumpsys/) D02/D04/D05
- **配套（性能工具）**：[04-Tool/Perfetto](../../04-Tool/Perfetto/)

## 维护说明

- E01-E03 与 02-Symptom/S11-Startup/ 4 大模块（A-D）一一对应
- 新增案例请在 E04-E11 占位后写
- 案例文件命名格式：`EXX-主题简写.md`（如 E01-冷启动8s-1s.md）

