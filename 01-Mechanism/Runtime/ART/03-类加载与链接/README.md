# 03-类加载与链接：从 .dex 到 Class 对象

> **本子模块**：03-类加载与链接（核心机制 · 4/9）——类从磁盘到内存的完整路径：ClassLoader 体系 / ClassLinker / 链接三步骤 / 类初始化

---

## 本子模块章节列表

| 章节 | 标题 | 行数目标 | 状态 |
| :--- | :--- | ---: | :---: |
| 01 | [类加载完整流程](01-类加载完整流程.md) | ~700 | ✅ |

---

## 子模块与全系列的依赖

```
00 → 01（字节码）→ 02（编译与执行）→ 03-类加载与链接（本子模块）→ 04-GC → 05-JNI / 06-信号 / 07-启动 / 08-对比
```

---

## 关键源码路径

| 路径 | AOSP 版本 | 角色 |
| :--- | :--- | :--- |
| `art/runtime/class_linker.cc` | AOSP 14+ | ClassLinker 核心 |
| `libcore/ojluni/src/main/java/java/lang/ClassLoader.java` | AOSP 14+ | Java ClassLoader |
| `libcore/ojluni/src/main/java/java/lang/PathClassLoader.java` | AOSP 14+ | PathClassLoader |
| `libcore/ojluni/src/main/java/dalvik/system/PathClassLoader.java` | AOSP 14+ | Dalvik PathClassLoader |
| `libcore/ojluni/src/main/java/dalvik/system/DexClassLoader.java` | AOSP 14+ | DexClassLoader |
| `libcore/ojluni/src/main/java/dalvik/system/InMemoryDexClassLoader.java` | AOSP 14+ | 内存 DexClassLoader |

---

> **返回阅读**：[README-ART 系列](../README-ART系列.md)