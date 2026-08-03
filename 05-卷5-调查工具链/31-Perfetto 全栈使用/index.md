# 第 31 章　Perfetto 全栈使用

> **所属卷**：卷 5　调查工具链
> **章定位**：AOSP 17 的默认 tracing 工具——本卷第一优先级，必须掌握。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 31.1 Perfetto 架构：Producer / Consumer / traced
- 31.2 抓取实战：ftrace / atrace / heap profiler / 配置模板
- 31.3 trace 判读：UI 操作 / Trace Processor SQL
- 31.4 场景实战：ANR / 启动 / 掉帧 / 内存
- 31.5 高级用法：自定义事件 / 长时抓取 / 自动触发
- 31.6 与 Systrace 的差异与迁移

## 本章小结

Perfetto 是 AOSP 17 稳定性调查的默认入口——不会 SQL 查询就只用到了它三成能力。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
