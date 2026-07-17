# 附录 A：源码索引（GC 与其他子系统）

## 一、JNI 相关

```
art/runtime/jni/jni_internal.cc          # JNI 实现（含 Critical / Global Ref）
art/runtime/jni/indirect_reference_table.h  # JNI Ref 表
art/runtime/gc/heap.h                   # Heap 类（含 pin 计数）
```

## 二、Zygote 相关

```
art/runtime/runtime.cc                 # Runtime::DidForkFromZygote
art/runtime/gc/heap.cc                 # Heap::PostForkChildAction
frameworks/base/core/java/com/android/internal/os/ZygoteInit.java
```

## 三、Hook 相关

```
art/runtime/read_barrier.h              # ReadBarrier
art/runtime/art_method.h               # ArtMethod 类
art/runtime/entrypoints/entrypoint_utils.h  # EntryPoint 工具
external/lsposed/                       # LSPosed
external/frida/                         # Frida
```

## 四、APEX / System Server 相关

```
system/core/libartpalette/              # ART 模块配置
system/apex/com.android.art/           # ART 模块
frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java
```

## 五、输入法 / SurfaceFlinger

```
frameworks/base/core/java/android/inputmethodservice/  # 输入法
frameworks/native/services/surfaceflinger/             # SurfaceFlinger
```
