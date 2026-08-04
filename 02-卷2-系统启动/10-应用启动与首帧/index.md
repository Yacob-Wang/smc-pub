# 第 10 章　应用启动与首帧

> **所属卷**：卷 2　系统启动
> **章定位**：从 Launcher 点击到第一帧显示——**App 启动机制链路**。  
> **不写什么**：Bootloader / Init / Zygote / SystemServer 整机启动（见第 6–9 章）。优化实践见卷 6 第 38 章。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8
> **章强依赖**：[第 8 章 Zygote](../08-Zygote%20与%20ART%20启动/index.md) · [第 9 章 SystemServer](../09-SystemServer%20启动/index.md)
> **章衔接去**：[第 11 章 系统启动性能专项](../11-系统启动性能专项/index.md)（开机侧）· 卷 6 第 38 章（应用启动优化）

## 章边界（强制）

| 内容 | 归属 |
|:---|:---|
| Bootloader → Kernel | **第 6 章** |
| Init / init.rc | **第 7 章** |
| Zygote / ART 启动 | **第 8 章** |
| SystemServer / 四大服务孵化 | **第 9 章** |
| Launcher 点击 → ActivityThread → 首帧 | **本章** |
| 开机时间 / boot loop / 开机 ANR | **第 11 章** |

历史系列稿 A01–A04（整机启动链）已迁出本章，见 `_archive/vol2-A-module-superseded-by-ch6-9/`。

## 核心子节

- 10.1 Launcher 点击 → ActivityThread：Binder 跨进程调用
- 10.2 进程创建：Zygote fork 的特殊参数（**应用侧**；Zygote 机制本身见第 8 章）
- 10.3 Application 初始化：attachBaseContext / onCreate / ContentProvider 初始化
- 10.4 视图树构建：measure / layout / draw
- 10.5 Choreographer 调度：VSYNC 与 input / animation / traversal 回调
- 10.6 首帧定义：First Frame / First Image / Cold / Warm / Hot Start
- 10.7 启动时间测量：am start -W / logcat / Perfetto

## 本章小结

启动优化必须分段——Application、Activity、Window、View 各自的瓶颈成因完全不同。

---

**状态**：🚧 撰写中（目标书章 10.1–10.7 待拆写）
**素材（章内）**：
- [A05 · AMS/PMS/WMS 与组件启动链路](A05-AMS-PMS-WMS四大组件启动.md) → 供 10.1–10.3
- [A06 · 第一帧与 Choreographer](A06-第一帧与Choreographer.md) → 供 10.4–10.7
**清理**：
- 2026-08-04 删除 `Old/`（15 篇 v1）
- 2026-08-04 迁出 A01–A04（与第 6–9 章职责重叠）
**生成**：sync_book_index.py（源：00-Meta/书籍目录-v1.md）
