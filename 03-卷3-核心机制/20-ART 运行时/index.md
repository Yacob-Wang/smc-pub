# 第 20 章　ART 运行时

> **所属卷**：卷 3　核心机制（横跨 AOSP 分层）
> **章定位**：ART 是 Java 性能与稳定性的核心——20% 的内容对应 50% 的问题。
> **工程基线**：AOSP 17.0.0_r1 + Linux 6.18 GKI + Pixel 7/8

## 核心子节

- 20.1 Dex 编译：AOT / JIT / 解释器 / Cloud Profile
- 20.2 类加载与反射：ClassLoader / Method / Field
- 20.3 垃圾回收：标记清除 / 并发 / 引用类型 / Finalize
- 20.4 JNI 与 Native 桥接：JNIEnv / RegisterNatives
- 20.5 启动类加载优化：Profile / Baseline Profile / dex2oat
- 20.6 ART 内部崩溃调查（AOSP 17 ART17）

## 本章小结

ART 是 Java 性能与稳定性的核心——20% 的内容对应 50% 的问题。

## 本章素材（待补全映射）

> 本章现有素材映射见 `00-Meta/章节-素材映射表-v1.md` 表格。
> 内容审计已通过（30 个无效文件已清），剩 651 篇。
> 详细写作计划见 `00-Meta/补全系列文章计划-v1.md`（待出）。

---

**状态**：🚧 骨架完成，内容撰写中
**生成**：build_book_skeleton.py
