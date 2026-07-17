# 附录 B：路径对账（GC 调度与触发）

## 一、AOSP 版本

| 维度 | 版本 |
|:---|:---|
| **AOSP 分支** | android14-release / master |
| **API Level** | 34 |

## 二、关键 commit

```
AOSP 8.0: HeapTaskDaemon 引入
AOSP 10.0: GenCC 引入（Minor/Major 分工）
AOSP 14.0: kGcCauseForNativeAlloc 引入
```

## 三、调试命令

```bash
# 看 GcCause
adb logcat -s "art" | grep "Cause="

# 看 HeapTaskDaemon 状态
adb shell ps -T -p <pid> | grep "HeapTask"

# 看 GC 线程
adb shell ps -T -p <pid> | grep "GC\|Daemon"

# 触发 GC
adb shell am gc
```

## 四、跨引用

| 引用方向 | 来源 | 目标 |
|:---|:---|:---|
| 被引用 | 09 篇诊断 | 7.1 9 种 GcCause |
