# 第 8 章　Zygote 与 ART 启动

> **所属卷**：卷 2　系统启动
> **章定位**：Java 进程工厂——所有 App 进程的模板。ART 的完整机制见卷 3 第 20 章，本章只讲**启动阶段**。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 8.1 Zygote 启动：fork + 预加载（preload classes / resources）
- 8.2 ART 启动：libart.so / ClassLinker / OAT 镜像加载
- 8.3 启动预优化：Profile Guided Compilation / Cloud Profile
- 8.4 启动类加载优化：deferred class load / lazy verification
- 8.5 Zygote fork 慢 / Zygote crash 的调查

## 本章小结

Zygote 是所有 App 启动的公共瓶颈——它慢 1 次，全系统慢 N 次。

---

**状态**：📋 骨架完成，待撰写
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
