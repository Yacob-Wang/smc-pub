# 第 19 章　电源与续航

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：续航问题需要硬件 + 软件 + 行为三方联合排查。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 19.1 PowerManager 与 WakeLock：保持唤醒与休眠
- 19.2 Doze 模式：深度休眠机制
- 19.3 Battery Historian 与耗电分析
- 19.4 后台限制：JobScheduler / WorkManager / Firebase Job Dispatcher
- 19.5 异常掉电：内核 / Modem / 电池 / 充电 IC
- 19.6 续航优化方法

## 本章小结

续航问题需要硬件 + 软件 + 行为三方联合排查。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
