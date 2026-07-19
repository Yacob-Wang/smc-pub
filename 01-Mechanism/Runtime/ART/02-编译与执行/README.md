# 02-编译与执行：从字节码到机器码

> **本子模块**：02-编译与执行（核心机制 · 3/9）——字节码怎么变成机器码并执行：解释器 / JIT / AOT / PGO / Baseline Profile
>
> **本子模块定位**：**核心机制**（3/9）

---

## 本子模块章节列表

| 章节 | 标题 | 行数目标 | 状态 |
| :--- | :--- | ---: | :---: |
| 01 | [编译路径全景：解释器 / JIT / AOT / PGO](01-编译路径全景.md) | ~700 | ✅ |

---

## 子模块与全系列的依赖

```
00-总览 → 01-字节码（理解字节码）→ 02-编译与执行（本子模块）→ 03-类加载 → 04-GC → 05-JNI / 06-信号 / 07-启动 / 08-对比
```

---

## 关键源码路径

| 路径 | AOSP 版本 | 角色 |
| :--- | :--- | :--- |
| `art/compiler/driver/compiler_driver.cc` | AOSP 14+ | 编译驱动 |
| `art/compiler/jit/jit_compiler.cc` | AOSP 14+ | JIT 编译 |
| `art/dex2oat/dex2oat.cc` | AOSP 14+ | AOT 编译入口 |
| `art/runtime/jit/jit.cc` | AOSP 14+ | JIT Runtime |
| `system/core/profcollectd/` | AOSP 14+ | Profile 收集 |

---

> **返回阅读**：[README-ART 系列](../README-ART系列.md)