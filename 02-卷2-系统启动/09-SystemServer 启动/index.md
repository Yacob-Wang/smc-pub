# 第 9 章　SystemServer 启动

> **所属卷**：卷 2　系统启动
> **章定位**：SystemServer 死 = 整机不响应（SystemUI 也挂）。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 9.1 SystemServer 启动入口：SystemServer.java
- 9.2 50+ 服务启动顺序：引导阶段 → 核心阶段 → 其他阶段
- 9.3 核心服务详解：PMS → AMS → WMS → IMS 启动流程
- 9.4 ServiceManager 与 Binder 域：服务注册与跨进程查找
- 9.5 启动阶段统计：bootstat
- 9.6 SystemServer 启动慢 / 死锁 / crash 调查

## 本章小结

SystemServer 死 = 整机不响应（SystemUI 也挂）。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
