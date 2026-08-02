# 第 22 章　ANR 深度

> **所属卷**：卷 4　稳定性症状诊断
> **章定位**：ANR 的根因永远不在 input/broadcast 本身——要找主线程为什么阻塞。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 22.1 ANR 类型：input / broadcast / service / contentprovider
- 22.2 ANR 检测机制：InputManager / AMS / Watchdog
- 22.3 ANR 现场采集：trace.txt / am_anr / data/anr/ / dropbox
- 22.4 ANR 调查方法论：主线程阻塞 / Binder 阻塞 / 死锁
- 22.5 ANR 案例库（5-10 个真实场景）
- 22.6 ANR 治理：监控、告警、防御

## 本章小结

ANR 的根因永远不在 input/broadcast 本身——要找主线程为什么阻塞。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
