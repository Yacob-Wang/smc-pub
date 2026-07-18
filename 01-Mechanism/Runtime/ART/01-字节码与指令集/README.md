# 01-字节码与指令集：Dex 文件的骨骼

> **本子模块**：01-字节码与指令集（ART 系列基础层 · 2/9）
> **本子模块定位**：**基础层**（2/9）——字节码是 ART 执行的"对象"，不懂字节码就读不懂 ART 的执行机制和崩溃堆栈
> **基线版本**：AOSP android-14.0.0_r1（libdexfile）；dex2oat 工具链

---

## 本子模块章节列表

| 章节 | 标题 | 行数目标 | 状态 |
| :--- | :--- | ---: | :---: |
| 01 | [Dex 文件与 Dalvik 指令集](01-Dex文件与Dalvik指令集.md) | ~700 | ✅ |

**合计**：~700 行 / 4-6 张 ASCII 图 / 1-2 个实战案例 / 4 个完整附录

---

## 子模块与全系列的依赖关系

```
00-总览（全局观）
    ↓
01-字节码与指令集（本子模块，基础层）
    │  └─ 解释器如何执行字节码
    ↓
02-编译与执行（M2，核心机制）
    │  └─ 字节码 → 机器码
    ↓
03-类加载与链接（M3，核心机制）
    │  └─ 字节码加载到内存
    ↓
04-内存与GC（★ 已完稿 9 篇）
05-JNI / 06-信号 / 07-启动 / 08-对比
```

---

## 与稳定性视角的对应

| 稳定性问题 | 与本子模块的关联 |
| :--- | :--- |
| **冷启动慢** | 字节码大小直接影响解释器启动时间 |
| **VerifyError** | Dex 字节码验证失败 → 应用崩溃 |
| **NoClassDefFoundError** | 字节码引用了不存在的类 |
| **StackOverflow** | 字节码递归深度超限 |
| **JIT 卡顿** | 字节码热点识别 + JIT 编译 |

---

## 关键源码路径

| 路径 | AOSP 版本 | 角色 |
| :--- | :--- | :--- |
| `art/libdexfile/dex/dex_file.h` | AOSP 14+ | Dex 文件核心 |
| `art/libdexfile/dex/dex_file.cc` | AOSP 14+ | Dex 解析 |
| `art/libdexfile/dex/code_item.h` | AOSP 14+ | CodeItem（方法字节码） |
| `art/runtime/interpreter/interpreter.cc` | AOSP 14+ | 解释器执行 |
| `art/runtime/interpreter/interpreter_switch_impl.cc` | AOSP 14+ | Switch 解释器 |

---

> **返回阅读**：[README-ART 系列](../README-ART系列.md) 包含全系列目录与阅读建议。