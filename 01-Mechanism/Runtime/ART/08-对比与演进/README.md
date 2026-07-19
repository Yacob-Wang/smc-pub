# 08-对比与演进：ART 为什么长成今天这样

> **本子模块**：08-对比与演进（横切对比 · 8/9）——ART 的演进史 + ART vs JVM 对比 + Mainline APEX 演进 + Hook 框架影响 + 监控基础设施
>
> **本子模块定位**：**横切对比**（8/9）

---

## 本子模块章节列表

| 章节 | 标题 | 行数目标 | 状态 |
| :--- | :--- | ---: | :---: |
| 01 | [ART vs JVM 设计哲学](01-ART_vs_JVM设计哲学.md) | ~700 | ✅ |
| 02 | [Mainline 与 APEX 演进](02-Mainline与APEX.md) | ~600 | ✅ |
| 03 | [Hook 框架与 ART 的兼容性](03-Hook框架与ART.md) | ~600 | ✅ |
| 04 | [监控与诊断基础设施](04-监控与诊断基础设施.md) | ~600 | ✅ |

**合计**：~2500 行

---

## 子模块与全系列的依赖

```
00 → 01-07（其他 7 个子模块）→ 08-对比与演进（本子模块）
```

---

## 关键源码路径

| 路径 | AOSP 版本 | 角色 |
| :--- | :--- | :--- |
| `art/runtime/` | AOSP 14+ | ART 核心 |
| `art/dex2oat/` | AOSP 14+ | AOT 编译 |
| `art/runtime/gc/` | AOSP 14+ | GC |
| `system/apex/com.android.runtime/` | AOSP 14+ | APEX 模块 |
| `frameworks/base/startop/view-compiler/` | AOSP 14+ | Baseline Profile |

---

> **返回阅读**：[README-ART 系列](../README-ART系列.md)