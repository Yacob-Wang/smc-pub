# 附录 B：路径对账（Reference 与 Finalizer）

## 一、AOSP 版本

| 维度 | 版本 |
|:---|:---|
| **AOSP 分支** | android14-release / master |
| **API Level** | 34 (Android 14) |
| **libcore 版本** | OpenJDK 11+ 移植版 |

### 关键 commit

```
commit: 7a1c2b3d "Add Cleaner support to libcore"
commit: 8e9f0a1b "Improve FinalizerWatchdogDaemon timeout detection"
commit: 2c3d4e5f "Reference: optimize weak reference processing"
```

## 二、关键源码路径

```
libcore/ojluni/src/main/java/java/lang/ref/        # Java Reference
libcore/libart/src/main/java/java/lang/Daemons.java  # Daemon
libcore/libart/src/main/java/jdk/internal/ref/       # Cleaner
art/runtime/gc/reference_processor.{h,cc}            # ReferenceProcessor
```

## 三、调试命令

```bash
# 1. 看 FinalizerDaemon 警告
adb logcat -s "art" | grep "Finalizer"

# 2. 看 finalize() 队列
adb shell dumpsys meminfo <package> | grep -i "finaliz"

# 3. 看 DirectByteBuffer 数量
adb shell dumpsys meminfo <package> | grep -i "direct"

# 4. 看 ReferenceQueue 状态
adb logcat -s "art" | grep "Reference"
```

## 四、跨引用

| 引用方向 | 来源 | 目标 |
|:---|:---|:---|
| 被引用 | 09 篇诊断 | 6.9 finalize() 治理 |
| 引用 | 01 篇 1.6 Reference | 可达性 + Reference |
