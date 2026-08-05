# 第 21 章　电源与续航

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：稳定性的横切主题——后台耗电、待机掉电、充电异常都需要「硬件 + 软件 + 用户行为」三方联合排查。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 21.1 PowerManager 与 WakeLock
- 21.2 Doze 与 App Standby：深度休眠机制
- 21.3 后台执行限制：JobScheduler / WorkManager / 前台服务
- 21.4 耗电分析：Battery Historian / batterystats
- 21.5 异常掉电：内核 / Modem / 电池 / 充电 IC
- 21.6 续航优化与稳定性的取舍

## 本章小结

续航问题极少是单一原因——必须同时看唤醒源、后台任务与硬件状态。

---

**状态**：🚧 撰写中（保留 PowerManager/WakeLock/Doze/耗电实战 4 篇）
**清理**：2026-08-04 迁出中断教材/IO SOP 等错位稿 → `_archive/misplaced-by-chapter-boundary/2026-08-04/vol3-ch21-offtopic/`
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
