# 第 23 章　ANR 深度

> **所属卷**：卷 4　诊断方法论与稳定性症状
> **章定位**：最高频的稳定性问题——input / broadcast / service / ContentProvider 四类 ANR 全解。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8
> **完整案例**：卷 8 第 48 章

## 核心子节

- 23.1 四类 ANR 的触发条件与超时阈值
- 23.2 ANR 检测机制：InputDispatcher / AMS / Watchdog 各自的判定
- 23.3 现场采集：trace.txt / am_anr / data/anr / DropBox
- 23.4 ANR trace 判读：主线程状态 / Binder 等待 / 锁持有链
- 23.5 三大根因族：主线程阻塞 / Binder 阻塞 / 死锁
- 23.6 ANR 治理：线上监控、阈值告警、防御性设计

## 本章小结

ANR 的根因永远不在 input / broadcast 本身——真正的问题是「主线程为什么没能及时返回」。

---

**状态**：🚧 已有 5 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
