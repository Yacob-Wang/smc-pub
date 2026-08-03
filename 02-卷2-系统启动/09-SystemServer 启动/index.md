# 第 9 章　SystemServer 启动

> **所属卷**：卷 2　系统启动
> **章定位**：50+ 系统服务的启动编排者——核心服务都在这里孵化。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 9.1 SystemServer 启动入口：SystemServer.java
- 9.2 服务启动三阶段：引导（Bootstrap）→ 核心（Core）→ 其他（Other）
- 9.3 核心服务详解：PMS → AMS → WMS → IMS 的启动依赖
- 9.4 ServiceManager 与 Binder 域：服务注册与跨进程查找
- 9.5 启动阶段统计：bootstat 与阶段耗时归因
- 9.6 SystemServer 启动慢 / 死锁 / crash 的调查

## 本章小结

SystemServer 死 = 整机不响应，连 SystemUI 一起挂——它是全系统的单点。

---

**状态**：📋 骨架完成，待撰写
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
