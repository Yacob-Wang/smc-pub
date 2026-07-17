# 07-启动流程：从 app_process 到第一行 Java 代码

> **本子模块**：07-启动流程（生命周期 · 7/9）——ART 怎么从无到有：init → Zygote → Runtime 初始化 → ClassLoader → ActivityThread.main 第一行 Java 代码

---

## 本子模块章节列表

| 章节 | 标题 | 行数目标 | 状态 |
| :--- | :--- | ---: | :---: |
| 01 | [从 app_process 到第一行 Java 代码](01-从app_process到第一行Java代码.md) | ~700 | ✅ |

---

## 子模块与全系列的依赖

```
00 → 01（字节码）→ 02（编译与执行）→ 03-类加载与链接 → 04-GC → 05-JNI → 06-信号与ANR-Trace → 07-启动流程（本子模块）→ 08-对比与演进
```

---

## 关键源码路径

| 路径 | AOSP 版本 | 角色 |
| :--- | :--- | :--- |
| `frameworks/base/core/jni/AndroidRuntime.cpp` | AOSP 14+ | AndroidRuntime::start() |
| `frameworks/base/core/java/com/android/internal/os/ZygoteInit.java` | AOSP 14+ | ZygoteInit.main() |
| `frameworks/base/core/java/com/android/internal/os/Zygote.java` | AOSP 14+ | Zygote fork 逻辑 |
| `frameworks/base/core/java/com/android/internal/os/RuntimeInit.java` | AOSP 14+ | RuntimeInit |
| `frameworks/base/core/java/android/app/ActivityThread.java` | AOSP 14+ | App 主线程入口 |
| `art/runtime/runtime.cc` | AOSP 14+ | ART Runtime 初始化 |
| `system/core/init/init.cpp` | AOSP 14+ | init 进程 |
| `frameworks/base/core/java/android/app/LoadedApk.java` | AOSP 14+ | App APK 加载 |

---

> **返回阅读**：[README-ART 系列](../README-ART系列.md)