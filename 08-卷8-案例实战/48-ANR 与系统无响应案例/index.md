# 第 48 章　ANR 与系统无响应案例

> **所属卷**：卷 8　案例实战
> **章定位**：卷 4 第 23 / 27 / 28 章的落地。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 48.1 主线程 Binder 阻塞导致的 input ANR
- 48.2 ContentProvider 跨进程死锁
- 48.3 广播串行队列超时
- 48.4 Binder oneway 风暴引发的系统级卡顿
- 48.5 InputDispatcher 卡死与无焦点窗口
- 48.6 方法论小结：trace 判读 → 锁链还原 → 根因修复

## 本章小结

ANR 案例训练的是「五秒内从 trace 中锁定阻塞点」的直觉。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
