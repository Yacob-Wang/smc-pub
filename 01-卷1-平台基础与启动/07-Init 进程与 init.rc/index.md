# 第 7 章　Init 进程与 init.rc

> **所属卷**：卷 2　系统启动
> **章定位**：第一个用户态进程——整个 Android 系统的「启动管家」。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 7.1 Init 进程（system/core/init）启动流程
- 7.2 init.rc 语法：service / action / import / on
- 7.3 启动阶段：early-init / init / post-fs / post-fs-data / late-start
- 7.4 属性服务（Property Service）：跨进程配置传递
- 7.5 SELinux 上下文加载与策略执行时机
- 7.6 init 阶段慢与卡死的常见原因

## 本章小结

init 阶段慢会 gating 后续所有服务——这里省 1 秒，整机启动省的往往不止 1 秒。

---

**状态**：🚧 已有 6 篇，撰写中
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）