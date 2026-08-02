# 第 8 章　Zygote 与 ART 启动

> **所属卷**：卷 2　系统启动
> **章定位**：Zygote 是 App 启动的瓶颈点，它的健康决定所有 App 启动速度。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 8.1 Zygote 启动：fork + 预加载（preload classes/resources）
- 8.2 ART 启动：libart.so / ClassLinker / OAT 镜像加载
- 8.3 启动预优化：Profile Guided Compilation / Cloud Profile
- 8.4 启动类加载优化：deferred class load / lazy verification
- 8.5 Zygote fork 慢 / Zygote crash 调查

## 本章小结

Zygote 是 App 启动的瓶颈点，它的健康决定所有 App 启动速度。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
