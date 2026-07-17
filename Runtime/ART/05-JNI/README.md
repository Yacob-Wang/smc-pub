# 05-JNI：Java 与 Native 的边界战争

> **本子模块**：05-JNI（边界 · 5/9）——Java ↔ Native 跨语言调用的核心机制：JavaVM / JNIEnv / IndirectReferenceTable / 关键 JNI 函数 / CheckJNI / 线程状态切换

---

## 本子模块章节列表

| 章节 | 标题 | 行数目标 | 状态 |
| :--- | :--- | ---: | :---: |
| 01 | [JNI 完整解析](01-JNI完整解析.md) | ~700 | ✅ |

---

## 子模块与全系列的依赖

```
00 → 01（字节码）→ 02（编译与执行）→ 03-类加载与链接 → 04-GC → 05-JNI（本子模块）→ 06-信号 → 07-启动 → 08-对比
```

---

## 关键源码路径

| 路径 | AOSP 版本 | 角色 |
| :--- | :--- | :--- |
| `art/runtime/jni/jni.cc` | AOSP 14+ | JNI 核心实现 |
| `art/runtime/jni/jni_env.cc` | AOSP 14+ | JNIEnv 实现 |
| `art/runtime/jni/check_jni.cc` | AOSP 14+ | CheckJNI |
| `art/runtime/indirect_reference_table.cc` | AOSP 14+ | 引用表 |
| `libcore/ojluni/src/main/native/` | AOSP 14+ | Java native 方法实现 |

---

> **返回阅读**：[README-ART 系列](../README-ART系列.md)